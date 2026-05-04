"""Package-level parser for SystemVerilog package files.

Extracts localparam, typedef enum, typedef struct, function, and task
definitions from *_pkg.sv files and converts them to structured claims
for RAG indexing.

v6 addition — addresses the gap where module_parse only captures
module declarations but misses package constants like SizeX, SizeY,
tile_t enum, etc.

v7 addition — Package Function Extractor: extracts function/task
signatures (name, return type, arguments, automatic/static qualifiers)
and optional 1-line body summaries for short functions (≤ 20 lines).

v8 addition — Flit Struct Field-Level Parsing: extends _extract_structs()
to extract per-field bitwidth (logic [N:0]), inline comments (// comment),
and type references (tile_t dest_tile). Generates per-field claims and
flit layout claims for *_flit_t, *_header_t, *_payload_t types.

v9 addition — Nested Struct Support: extends _extract_structs() to detect
when a struct field's type references another typedef struct in the same
package. Generates hierarchical nested relationship claims. Tracks nesting
up to 3 levels deep; exceeding 3 levels triggers a truncation warning.
"""

import re
import hashlib
import logging

logger = logging.getLogger(__name__)


def is_package_file(file_path: str) -> bool:
    """Check if a file is a SystemVerilog package file."""
    return file_path.endswith("_pkg.sv") or file_path.endswith("_pkg.v")


def extract_package_constants(rtl_content: str, file_path: str = "",
                               pipeline_id: str = "") -> list:
    """Extract localparam, typedef enum, and typedef struct from package content.

    Returns a list of claim-format dicts ready for OpenSearch indexing.
    """
    content = re.sub(r"//[^\n]*", "", rtl_content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

    claims = []
    pkg_match = re.search(r"\bpackage\s+(\w+)\s*;", content)
    pkg_name = pkg_match.group(1) if pkg_match else ""

    claims.extend(_extract_localparams(content, pkg_name, file_path, pipeline_id))
    claims.extend(_extract_enums(content, pkg_name, file_path, pipeline_id))
    claims.extend(_extract_structs(content, pkg_name, file_path, pipeline_id,
                                    rtl_content=rtl_content))
    claims.extend(_extract_parameters(content, pkg_name, file_path, pipeline_id))
    claims.extend(_extract_functions(rtl_content, pkg_name, file_path, pipeline_id))
    claims.extend(_extract_tasks(rtl_content, pkg_name, file_path, pipeline_id))

    return claims


def _extract_localparams(content, pkg_name, file_path, pipeline_id):
    """Extract localparam declarations."""
    claims = []
    # Match: localparam [type] [packed_dim] NAME = VALUE;
    # Types: int, integer, logic, bit, string, shortint, longint, byte, or omitted
    pattern = re.compile(
        r"\blocalparam\s+(?:int\b|integer\b|logic\b|bit\b|string\b|shortint\b|longint\b|byte\b)?\s*"
        r"(?:unsigned\s+)?"
        r"(?:\[[^\]]*\]\s*)?"
        r"(\w+)\s*=\s*([^;]+);",
        re.MULTILINE
    )
    params = {}
    for m in pattern.finditer(content):
        params[m.group(1)] = m.group(2).strip()

    if params:
        param_lines = [f"{k} = {v}" for k, v in params.items()]
        claim_text = (
            f"Package '{pkg_name}' defines {len(params)} localparam constants: "
            + ", ".join(param_lines[:30])
        )
        if len(params) > 30:
            claim_text += f" ... and {len(params) - 30} more"
        claims.append(_make_claim(claim_text, "structural", pkg_name,
                                   "PackageConfig", file_path, pipeline_id))

        # Create individual claims for ALL localparams (not just pure numeric)
        for name, value in params.items():
            claims.append(_make_claim(
                f"Package '{pkg_name}' defines localparam {name} = {value}",
                "structural", pkg_name, "PackageConfig", file_path, pipeline_id,
            ))
    return claims


def _extract_enums(content, pkg_name, file_path, pipeline_id):
    """Extract typedef enum declarations."""
    claims = []
    pattern = re.compile(
        r"typedef\s+enum\s+(?:logic|bit|int)?\s*(?:\[[^\]]*\]\s*)?"
        r"\{([^}]+)\}\s*(\w+)\s*;",
        re.DOTALL
    )
    for m in pattern.finditer(content):
        body = m.group(1)
        enum_name = m.group(2)
        members = []
        for line in body.split(","):
            line = line.strip()
            if not line:
                continue
            member_match = re.match(r"(\w+)\s*(?:=\s*([^,\s]+))?", line)
            if member_match:
                mname = member_match.group(1)
                mval = member_match.group(2)
                members.append(f"{mname}={mval}" if mval else mname)

        if members:
            claims.append(_make_claim(
                f"Package '{pkg_name}' defines typedef enum '{enum_name}' "
                f"with {len(members)} members: {', '.join(members)}",
                "structural", pkg_name, "PackageConfig", file_path, pipeline_id,
            ))
    return claims


def _extract_structs(content, pkg_name, file_path, pipeline_id,
                     rtl_content=""):
    """Extract typedef struct declarations with field-level detail.

    Extracts per-field bitwidth, inline comments, and type references.
    For flit-related types (*_flit_t, *_header_t, *_payload_t), generates
    an additional layout claim with fields sorted by bit position.
    Detects nested structs (field type referencing another struct in the
    same package) and generates hierarchical relationship claims up to
    3 levels deep (Req 21.1–21.4).

    Args:
        content: comment-stripped RTL content (for struct body matching)
        pkg_name: package name
        file_path: source file path
        pipeline_id: pipeline identifier
        rtl_content: original RTL content with comments (for inline comment extraction)
    """
    claims = []
    pattern = re.compile(
        r"typedef\s+struct\s+(?:packed\s*)?\{([^}]+)\}\s*(\w+)\s*;",
        re.DOTALL
    )

    # Also find struct bodies in the original content (with comments) for
    # inline comment extraction.  We build a mapping from struct_name to
    # the raw body text that still contains // comments.
    raw_struct_bodies = {}
    if rtl_content:
        raw_pattern = re.compile(
            r"typedef\s+struct\s+(?:packed\s*)?\{([^}]+)\}\s*(\w+)\s*;",
            re.DOTALL
        )
        for rm in raw_pattern.finditer(rtl_content):
            raw_struct_bodies[rm.group(2)] = rm.group(1)

    # --- First pass: collect all struct names and their parsed fields ---
    # This is needed to detect nested structs (Req 21.1).
    struct_info = {}  # struct_name -> {"body": str, "fields": list}
    for m in pattern.finditer(content):
        body = m.group(1)
        struct_name = m.group(2)
        parsed_fields = _parse_struct_fields(body, raw_struct_bodies.get(struct_name, ""))
        struct_info[struct_name] = {
            "body": body,
            "fields": parsed_fields,
        }

    all_struct_names = set(struct_info.keys())

    # --- Second pass: generate claims for each struct ---
    for struct_name, info in struct_info.items():
        parsed_fields = info["fields"]

        # Keep existing summary claim (field count + names) for backward compat
        field_names = [f["name"] for f in parsed_fields]
        if field_names:
            claims.append(_make_claim(
                f"Package '{pkg_name}' defines typedef struct '{struct_name}' "
                f"with {len(field_names)} fields: {', '.join(field_names)}",
                "structural", pkg_name, "PackageConfig", file_path, pipeline_id,
                parser_source="package_struct_parser",
            ))

        # --- Per-field claims (Req 20.1, 20.2, 20.4, 20.5) ---
        for field in parsed_fields:
            claim_text = (
                f"Package '{pkg_name}' defines struct '{struct_name}' "
                f"field '{field['name']}' with width {field['bit_width']}"
            )
            if field.get("ref_type"):
                claim_text += f", type reference '{field['ref_type']}'"
            if field.get("comment"):
                claim_text += f" ({field['comment']})"

            claims.append(_make_claim(
                claim_text, "structural", pkg_name,
                "PackageConfig", file_path, pipeline_id,
                parser_source="package_struct_parser",
            ))

        # --- Nested struct relationship claims (Req 21.1, 21.2, 21.3) ---
        for field in parsed_fields:
            child_struct = field.get("ref_type", "")
            if not child_struct or child_struct not in all_struct_names:
                continue

            claim_text = (
                f"Package '{pkg_name}' struct '{struct_name}' contains "
                f"nested struct field '{field['name']}' of type '{child_struct}'"
            )

            # Req 21.3: Check if this relationship exceeds 3-level depth.
            # Compute the longest ancestor chain leading to struct_name,
            # then check if the child has further struct-type fields.
            ancestor_depth = _max_ancestor_depth(
                struct_name, all_struct_names, struct_info,
            )
            # ancestor_depth=0 means struct_name is a root (not nested in anything)
            # ancestor_depth=1 means struct_name is nested 1 level deep, etc.
            # The current relationship is at depth = ancestor_depth + 1
            relationship_depth = ancestor_depth + 1
            if relationship_depth >= 3:
                child_fields = struct_info.get(child_struct, {}).get("fields", [])
                has_deeper = any(
                    f.get("ref_type", "") in all_struct_names
                    for f in child_fields
                )
                if has_deeper:
                    claim_text += " (nested depth exceeds 3, truncated)"

            claims.append(_make_claim(
                claim_text, "structural", pkg_name,
                "PackageConfig", file_path, pipeline_id,
                parser_source="package_struct_parser",
            ))

        # --- Flit layout claim (Req 20.3) ---
        if _is_flit_type(struct_name) and parsed_fields:
            layout_claim = _build_flit_layout_claim(
                struct_name, parsed_fields, pkg_name, file_path, pipeline_id,
            )
            if layout_claim:
                claims.append(layout_claim)

    return claims


def _max_ancestor_depth(struct_name, all_struct_names, struct_info,
                        visited=None):
    """Compute the longest ancestor chain leading to struct_name.

    Returns 0 if struct_name is a root (not nested inside any other struct).
    Returns 1 if struct_name is directly nested in one struct, etc.

    Uses visited set to prevent infinite loops from circular references.
    """
    if visited is None:
        visited = set()
    if struct_name in visited:
        return 0
    visited = visited | {struct_name}

    max_depth = 0
    for other_name, other_info in struct_info.items():
        if other_name == struct_name:
            continue
        for field in other_info["fields"]:
            if field.get("ref_type") == struct_name:
                parent_depth = _max_ancestor_depth(
                    other_name, all_struct_names, struct_info, visited,
                )
                max_depth = max(max_depth, parent_depth + 1)
    return max_depth


def _parse_struct_fields(body, raw_body=""):
    """Parse struct body into a list of field dicts with bitwidth and metadata.

    Each returned dict has:
        name: field identifier
        bit_width: integer bit width (e.g. 8 for logic [7:0])
        msb: most significant bit index (e.g. 7)
        lsb: least significant bit index (e.g. 0)
        ref_type: referenced typedef name if field uses a custom type, else ""
        comment: inline comment text if present, else ""

    Args:
        body: comment-stripped struct body text
        raw_body: original struct body with inline comments
    """
    fields = []

    # Build a mapping of field_name -> inline comment from the raw body
    comment_map = {}
    if raw_body:
        # Match lines like:  logic [3:0] x_dest;  // destination X coordinate
        # or:                 tile_t dest_tile;    // destination tile
        comment_line_pattern = re.compile(
            r"(\w+)\s*;\s*//\s*(.+?)$", re.MULTILINE
        )
        for cm in comment_line_pattern.finditer(raw_body):
            comment_map[cm.group(1)] = cm.group(2).strip()

    # Known built-in types that are NOT typedef references
    builtin_types = {
        "logic", "bit", "int", "integer", "wire", "reg",
        "byte", "shortint", "longint", "string", "real",
    }

    # Pattern 1: built-in type with optional packed dimension
    #   logic [N:M] field_name;
    #   bit [7:0] field_name;
    #   logic field_name;  (1-bit)
    builtin_field_pattern = re.compile(
        r"(logic|bit|int|integer|wire|reg|byte|shortint|longint)"
        r"\s*(?:\[([^\]]*)\]\s*)?(\w+)\s*;",
    )

    # Pattern 2: custom type reference (typedef name)
    #   tile_t dest_tile;
    #   endpoint_id_t ep_id;
    # Must NOT match built-in types.  We match: word word ;
    # where the first word is not a built-in type.
    custom_field_pattern = re.compile(
        r"(\w+)\s+(\w+)\s*;",
    )

    # Track which field names we've already captured (avoid duplicates)
    seen_names = set()

    # First pass: built-in typed fields
    for fm in builtin_field_pattern.finditer(body):
        type_name = fm.group(1)
        dim_str = fm.group(2)  # e.g. "7:0" or "N:0" or None
        field_name = fm.group(3)

        if field_name in seen_names:
            continue
        seen_names.add(field_name)

        msb, lsb, bit_width = _parse_dimension(dim_str, type_name)

        fields.append({
            "name": field_name,
            "bit_width": bit_width,
            "msb": msb,
            "lsb": lsb,
            "ref_type": "",
            "comment": comment_map.get(field_name, ""),
        })

    # Second pass: custom type references
    for fm in custom_field_pattern.finditer(body):
        type_name = fm.group(1)
        field_name = fm.group(2)

        if field_name in seen_names:
            continue
        if type_name in builtin_types:
            continue
        # Skip keywords that look like type+name but aren't fields
        if type_name in ("typedef", "struct", "packed", "unsigned", "signed"):
            continue
        seen_names.add(field_name)

        fields.append({
            "name": field_name,
            "bit_width": 0,  # unknown width for typedef references
            "msb": 0,
            "lsb": 0,
            "ref_type": type_name,
            "comment": comment_map.get(field_name, ""),
        })

    return fields


def _parse_dimension(dim_str, type_name="logic"):
    """Parse a packed dimension string like '7:0' or 'N-1:0' into (msb, lsb, width).

    Returns (msb, lsb, bit_width).
    For single-bit types (no dimension), returns (0, 0, 1).
    For non-numeric expressions, attempts best-effort integer parsing.
    """
    if dim_str is None:
        # No dimension — single bit for logic/bit, or type-dependent
        if type_name in ("int", "integer"):
            return (31, 0, 32)
        if type_name in ("byte",):
            return (7, 0, 8)
        if type_name in ("shortint",):
            return (15, 0, 16)
        if type_name in ("longint",):
            return (63, 0, 64)
        return (0, 0, 1)

    dim_str = dim_str.strip()
    parts = dim_str.split(":")
    if len(parts) == 2:
        try:
            msb = int(parts[0].strip())
            lsb = int(parts[1].strip())
            return (msb, lsb, abs(msb - lsb) + 1)
        except ValueError:
            # Non-numeric expression (e.g. "SizeX-1:0") — return 0 width
            return (0, 0, 0)
    # Single number dimension (rare)
    try:
        val = int(dim_str)
        return (val - 1, 0, val)
    except ValueError:
        return (0, 0, 0)


def _is_flit_type(struct_name):
    """Check if a struct name is a flit-related type.

    Matches patterns: *_flit_t, *_header_t, *_payload_t
    """
    return bool(re.search(r"(?:_flit_t|_header_t|_payload_t)$", struct_name))


def _build_flit_layout_claim(struct_name, parsed_fields, pkg_name,
                              file_path, pipeline_id):
    """Build a flit layout claim with fields sorted by bit position.

    Generates claim_text like:
        "Flit structure 'noc_flit_t' layout: field1[31:24], field2[23:16], ..."

    Fields are sorted by MSB descending (highest bit first).
    Fields with unknown bit positions (width 0) are appended at the end.
    """
    # Separate fields with known vs unknown bit positions
    known = [f for f in parsed_fields if f["bit_width"] > 0]
    unknown = [f for f in parsed_fields if f["bit_width"] == 0]

    # Sort known fields by MSB descending
    known.sort(key=lambda f: f["msb"], reverse=True)

    layout_parts = []
    for f in known:
        layout_parts.append(f"{f['name']}[{f['msb']}:{f['lsb']}]")
    for f in unknown:
        ref_info = f"({f['ref_type']})" if f.get("ref_type") else "(unknown width)"
        layout_parts.append(f"{f['name']}{ref_info}")

    if not layout_parts:
        return None

    claim_text = (
        f"Flit structure '{struct_name}' layout: "
        + ", ".join(layout_parts)
    )

    return _make_claim(
        claim_text, "structural", pkg_name,
        "PackageConfig", file_path, pipeline_id,
        parser_source="package_struct_parser",
    )


def _extract_parameters(content, pkg_name, file_path, pipeline_id):
    """Extract top-level parameter declarations in package."""
    claims = []
    pattern = re.compile(
        r"\bparameter\s+(?:int|integer|logic|bit|string)?\s*"
        r"(?:\[[^\]]*\]\s*)?"
        r"(\w+)\s*=\s*([^;]+);",
        re.MULTILINE
    )
    for m in pattern.finditer(content):
        claims.append(_make_claim(
            f"Package '{pkg_name}' defines parameter {m.group(1)} = {m.group(2).strip()}",
            "structural", pkg_name, "PackageConfig", file_path, pipeline_id,
        ))
    return claims


def _extract_functions(rtl_content, pkg_name, file_path, pipeline_id):
    """Extract function declarations from package content.

    Parses function name, return type, argument list (name + type),
    and automatic/static qualifiers. For functions with body <= 20 lines,
    adds a 1-line summary of the main logic pattern.

    Uses the original rtl_content (with comments) so that body line
    counting is accurate. Comment stripping is done internally for
    regex matching of the declaration header.
    """
    claims = []
    # Strip comments for declaration matching
    clean = re.sub(r"//[^\n]*", "", rtl_content)
    clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL)

    # Match function declarations:
    #   [automatic|static] function [return_type] func_name ( args );
    #     ... body ...
    #   endfunction
    # The return type may include packed dimensions like [N:0].
    func_pattern = re.compile(
        r"\b(automatic\s+|static\s+)?"
        r"function\s+"
        r"((?:(?:void|int|integer|logic|bit|byte|shortint|longint|string|real)"
        r"(?:\s+(?:unsigned|signed))?"
        r"(?:\s*\[[^\]]*\])*"
        r"|(?:\w+))"  # custom return type (typedef name)
        r")\s+"
        r"(\w+)"      # function name
        r"\s*\(([^)]*)\)\s*;",  # argument list
        re.DOTALL
    )

    for m in func_pattern.finditer(clean):
        qualifier = m.group(1).strip() if m.group(1) else ""
        return_type = re.sub(r"\s+", " ", m.group(2).strip())
        func_name = m.group(3)
        raw_args = m.group(4).strip()

        # Skip nested function declarations (inside module/class bodies)
        # by checking if we're inside a module/class scope
        pre_text = clean[:m.start()]
        module_opens = len(re.findall(r"\bmodule\b", pre_text))
        module_closes = len(re.findall(r"\bendmodule\b", pre_text))
        if module_opens > module_closes:
            continue

        # Parse arguments
        args = _parse_function_args(raw_args)
        args_str = ", ".join(
            f"{a['type']} {a['name']}" for a in args
        ) if args else ""

        # Build claim_text
        claim_text = (
            f"Package '{pkg_name}' defines function "
            f"'{func_name}({args_str}) \u2192 {return_type}'"
        )
        if qualifier:
            claim_text += f" [{qualifier}]"

        # Extract body for short-function summary (<= 20 lines)
        body = _extract_function_body(clean, m.end())
        if body is not None:
            body_lines = [ln for ln in body.split("\n") if ln.strip()]
            if 0 < len(body_lines) <= 20:
                summary = _summarize_body(body)
                if summary:
                    claim_text += f". Summary: {summary}"

        claims.append(_make_claim(
            claim_text, "structural", pkg_name,
            "PackageFunction", file_path, pipeline_id,
            parser_source="package_function_extractor",
        ))

    logger.info(
        "Extracted %d function claims from package '%s' in %s",
        len(claims), pkg_name, file_path,
    )
    return claims


def _extract_tasks(rtl_content, pkg_name, file_path, pipeline_id):
    """Extract task declarations from package content.

    Parses task name and argument list (name + direction + type).
    """
    claims = []
    clean = re.sub(r"//[^\n]*", "", rtl_content)
    clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL)

    # Match task declarations:
    #   [automatic|static] task task_name ( args );
    #     ... body ...
    #   endtask
    task_pattern = re.compile(
        r"\b(automatic\s+|static\s+)?"
        r"task\s+"
        r"(\w+)"      # task name
        r"\s*\(([^)]*)\)\s*;",  # argument list
        re.DOTALL
    )

    for m in task_pattern.finditer(clean):
        qualifier = m.group(1).strip() if m.group(1) else ""
        task_name = m.group(2)
        raw_args = m.group(3).strip()

        # Skip nested task declarations inside module/class bodies
        pre_text = clean[:m.start()]
        module_opens = len(re.findall(r"\bmodule\b", pre_text))
        module_closes = len(re.findall(r"\bendmodule\b", pre_text))
        if module_opens > module_closes:
            continue

        # Parse arguments with direction
        args = _parse_task_args(raw_args)
        args_str = ", ".join(
            f"{a['direction']} {a['type']} {a['name']}" for a in args
        ) if args else ""

        # Build claim_text — tasks have no return type
        claim_text = (
            f"Package '{pkg_name}' defines task "
            f"'{task_name}({args_str})'"
        )
        if qualifier:
            claim_text += f" [{qualifier}]"

        claims.append(_make_claim(
            claim_text, "structural", pkg_name,
            "PackageFunction", file_path, pipeline_id,
            parser_source="package_function_extractor",
        ))

    logger.info(
        "Extracted %d task claims from package '%s' in %s",
        len(claims), pkg_name, file_path,
    )
    return claims


def _parse_function_args(raw_args):
    """Parse function argument list into structured dicts.

    Handles forms like:
        input logic [7:0] data, input int count
        logic [3:0] addr, int size
    Returns list of {'name': str, 'type': str}.
    """
    if not raw_args.strip():
        return []

    args = []
    # Split by comma, but be careful with packed dimensions containing commas
    parts = re.split(r",(?![^\[]*\])", raw_args)
    current_type = "logic"  # default type if omitted

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Remove direction keywords for function args (input is default)
        part = re.sub(r"^\s*(?:input|output|inout|ref)\s+", "", part)

        # Try to match: [type] [packed_dim] name
        arg_match = re.match(
            r"(?:(int|integer|logic|bit|byte|shortint|longint|string|real|"
            r"(?:unsigned|signed\s+)?(?:int|integer|logic|bit|byte|shortint|longint)|"
            r"\w+)"  # custom type
            r"(?:\s+(?:unsigned|signed))?"
            r"(?:\s*\[[^\]]*\])*"
            r"\s+)?"
            r"(\w+)\s*$",
            part,
        )
        if arg_match:
            type_str = arg_match.group(1)
            name = arg_match.group(2)
            if type_str:
                current_type = re.sub(r"\s+", " ", type_str.strip())
            args.append({"name": name, "type": current_type})
        else:
            # Fallback: try extracting just the last word as name
            words = part.split()
            if words:
                name = words[-1]
                if len(words) > 1:
                    current_type = " ".join(words[:-1])
                args.append({"name": name, "type": current_type})

    return args


def _parse_task_args(raw_args):
    """Parse task argument list into structured dicts with direction.

    Handles forms like:
        input logic [7:0] data, output int result, inout wire flag
    Returns list of {'name': str, 'direction': str, 'type': str}.
    """
    if not raw_args.strip():
        return []

    args = []
    parts = re.split(r",(?![^\[]*\])", raw_args)
    current_direction = "input"  # default direction
    current_type = "logic"       # default type

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Extract direction if present
        dir_match = re.match(r"^\s*(input|output|inout|ref)\s+(.*)", part)
        if dir_match:
            current_direction = dir_match.group(1)
            part = dir_match.group(2).strip()

        # Try to match: [type] [packed_dim] name
        arg_match = re.match(
            r"(?:(int|integer|logic|bit|byte|shortint|longint|string|real|wire|reg|"
            r"\w+)"  # type including custom types
            r"(?:\s+(?:unsigned|signed))?"
            r"(?:\s*\[[^\]]*\])*"
            r"\s+)?"
            r"(\w+)\s*$",
            part,
        )
        if arg_match:
            type_str = arg_match.group(1)
            name = arg_match.group(2)
            if type_str:
                current_type = re.sub(r"\s+", " ", type_str.strip())
            args.append({
                "name": name,
                "direction": current_direction,
                "type": current_type,
            })
        else:
            # Fallback
            words = part.split()
            if words:
                name = words[-1]
                if len(words) > 1:
                    current_type = " ".join(words[:-1])
                args.append({
                    "name": name,
                    "direction": current_direction,
                    "type": current_type,
                })

    return args


def _extract_function_body(content, decl_end_pos):
    """Extract the body text between function declaration and endfunction.

    Args:
        content: comment-stripped content
        decl_end_pos: position right after the function declaration semicolon

    Returns:
        Body text string, or None if endfunction not found.
    """
    rest = content[decl_end_pos:]
    end_match = re.search(r"\bendfunction\b", rest)
    if not end_match:
        return None
    return rest[:end_match.start()].strip()


def _summarize_body(body):
    """Generate a 1-line summary of a short function body.

    Identifies the main logic pattern: loop count, conditional branch,
    index calculation, return expression, assignment, etc.
    """
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    if not lines:
        return ""

    # Count patterns
    loop_count = len(re.findall(r"\b(?:for|while|foreach|repeat)\b", body))
    cond_count = len(re.findall(r"\b(?:if|case|casex|casez)\b", body))
    assign_count = len(re.findall(r"(?:<=|=(?!=))", body))
    return_match = re.search(r"\breturn\b\s+(.+?)\s*;", body)
    has_ternary = "?" in body and ":" in body

    parts = []
    if loop_count:
        parts.append(f"{loop_count} loop(s)")
    if cond_count:
        parts.append(f"{cond_count} conditional(s)")
    if has_ternary and not cond_count:
        parts.append("ternary expression")
    if return_match:
        ret_expr = return_match.group(1).strip()
        if len(ret_expr) <= 60:
            parts.append(f"returns {ret_expr}")
        else:
            parts.append("returns computed value")
    if not parts:
        if assign_count:
            parts.append(f"{assign_count} assignment(s)")
        else:
            parts.append(f"{len(lines)} statement(s)")

    return "; ".join(parts)


def _make_claim(claim_text, claim_type, module_name, topic,
                file_path, pipeline_id, parser_source=""):
    """Create a claim dict in the standard format for OpenSearch indexing."""
    claim_id = hashlib.sha256(
        f"{pipeline_id}:{file_path}:{claim_text[:100]}".encode()
    ).hexdigest()[:16]
    claim = {
        "analysis_type": "claim",
        "claim_id": claim_id,
        "claim_type": claim_type,
        "claim_text": claim_text,
        "module_name": module_name,
        "topic": topic,
        "pipeline_id": pipeline_id,
        "file_path": file_path,
        "confidence_score": 1.0,
        "source_files": [file_path],
    }
    if parser_source:
        claim["parser_source"] = parser_source
    return claim
