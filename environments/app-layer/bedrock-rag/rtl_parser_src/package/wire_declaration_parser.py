"""Wire Declaration Parser for RTL files.

Extracts wire/logic/reg declarations with struct types and array dimensions.
Targets: clock_routing arrays, dispatch feedthrough wires.

parser_source: "wire_declaration_parser"
Feature flag: PARSER_WIRE_DECLARATION_ENABLED
"""
import re
import os
import logging
import hashlib

logger = logging.getLogger(__name__)

# Purpose inference heuristics
PURPOSE_HEURISTICS = {
    'clock_routing': 'clock distribution',
    'de_to_t6': 'dispatch-to-tensix feedthrough',
    't6_to_de': 'tensix-to-dispatch feedthrough',
    'edc_': 'EDC ring connection',
    'noc_': 'NoC interconnect',
    'axi_': 'AXI bus connection',
    'apb_': 'APB bus connection',
    'prtn': 'power partition chain',
}

# Feature flag
PARSER_WIRE_DECLARATION_ENABLED = os.environ.get(
    'PARSER_WIRE_DECLARATION_ENABLED', 'true'
).lower() == 'true'


def _make_claim(claim_text, claim_type, module_name, topic,
                file_path, pipeline_id, parser_source=""):
    """Create claim dict (same pattern as other parsers)."""
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


def extract_wire_declarations(rtl_content, module_name="", file_path="",
                              pipeline_id="", known_structs=None):
    """Extract wire/logic declarations with struct types and array dimensions.

    Matches three patterns:
      A: wire/logic struct_type signal_name[dim1][dim2];
      B: logic [N:0] signal_name[dims];
      C: type_name_t signal_name[dims]; (implicit wire, type ends with _t)

    Args:
        rtl_content: Raw RTL source code string.
        module_name: Name of the module being parsed.
        file_path: Source file path for claim metadata.
        pipeline_id: Pipeline identifier for claim metadata.
        known_structs: Optional set/list of known struct type names.

    Returns:
        List of claim dicts ready for OpenSearch indexing.
    """
    if not PARSER_WIRE_DECLARATION_ENABLED:
        return []

    if not rtl_content:
        return []

    claims = []
    known_structs = set(known_structs) if known_structs else set()

    # Strip comments for reliable matching
    clean = _strip_comments(rtl_content)

    # Extract module name if not provided
    if not module_name:
        mod_match = re.search(r"\bmodule\s+(\w+)\s*(?:#\s*\(|[\(\;])", clean)
        module_name = mod_match.group(1) if mod_match else "unknown"

    # Pattern A: wire/logic struct_type signal_name[dims];
    # e.g.: wire trinity_clock_routing_t clock_routing_in[SizeX][SizeY];
    #        logic some_struct_t my_signal[4][8];
    #        wire trinity_pkg::trinity_clock_routing_t clock_routing_in[...];
    pattern_a = re.compile(
        r'\b(wire|logic|reg)\s+'
        r'((?:\w+::)?\w+)\s+'  # struct type with optional pkg:: prefix
        r'(\w+)\s*'             # signal name
        r'((?:\[[^\]]+\])+)\s*;',  # one or more dimensions
    )

    # Pattern B: logic [N:0] signal_name[dims];
    # e.g.: logic [31:0] some_signal[4];
    pattern_b = re.compile(
        r'\b(logic|wire|reg)\s+'
        r'\[([^\]]+)\]\s+'  # bit range [N:0]
        r'(\w+)\s*'         # signal name
        r'((?:\[[^\]]+\])+)\s*;',  # one or more dimensions
    )

    # Pattern C: pkg::type_name signal_name[dims]; (no wire/logic keyword)
    # e.g.: trinity_pkg::trinity_clock_routing_t clock_routing_out[SizeX][SizeY];
    #        tt_chip_global_pkg::de_to_t6_t [...] de_to_t6_coloumn[...];
    pattern_c = re.compile(
        r'^[ \t]*((?:\w+::)?\w+_t)\s+'  # type with optional pkg:: prefix, ending with _t
        r'(?:\[[^\]]+\]\s*)?'            # optional packed dimension (e.g., [NumDispatchCorners-1:0])
        r'(\w+)\s*'                      # signal name
        r'((?:\[[^\]]+\])+)\s*;',        # one or more array dimensions
        re.MULTILINE,
    )

    # Process Pattern A matches
    for m in pattern_a.finditer(clean):
        wire_type = m.group(1)  # wire/logic/reg
        struct_type = m.group(2)
        signal_name = m.group(3)
        dim_str = m.group(4)

        if not signal_name:
            continue

        # Skip if struct_type is actually a bit range keyword
        if struct_type in ('signed', 'unsigned'):
            continue

        dims = _parse_dimensions(dim_str)
        purpose = _infer_purpose(signal_name)
        evaluated = "\u00d7".join(dims) if dims else "unknown"

        # Check if it's a real struct type (ends with _t or has :: or in known_structs)
        is_struct = struct_type.endswith('_t') or '::' in struct_type or struct_type in known_structs

        if is_struct:
            claim_text = (
                f"Wire '{signal_name}' of type '{struct_type}' "
                f"with dimensions [{', '.join(dims)}] "
                f"({evaluated} array) for {purpose}"
            )
            if struct_type in known_structs:
                claim_text += f" [references struct {struct_type}]"
        else:
            claim_text = (
                f"Wire '{signal_name}' with dimensions [{', '.join(dims)}] "
                f"({evaluated} array) connects {purpose}"
            )

        claims.append(_make_claim(
            claim_text, "structural", module_name,
            "WireTopology", file_path, pipeline_id,
            parser_source="wire_declaration_parser",
        ))

    # Process Pattern B matches
    for m in pattern_b.finditer(clean):
        wire_type = m.group(1)
        bit_range = m.group(2)
        signal_name = m.group(3)
        dim_str = m.group(4)

        if not signal_name:
            continue

        dims = _parse_dimensions(dim_str)
        purpose = _infer_purpose(signal_name)
        evaluated = "\u00d7".join(dims) if dims else "unknown"

        claim_text = (
            f"Wire '{signal_name}' with dimensions [{', '.join(dims)}] "
            f"({evaluated} array) connects {purpose}"
        )

        claims.append(_make_claim(
            claim_text, "structural", module_name,
            "WireTopology", file_path, pipeline_id,
            parser_source="wire_declaration_parser",
        ))

    # Process Pattern C matches (implicit wire with _t type)
    for m in pattern_c.finditer(clean):
        struct_type = m.group(1)
        signal_name = m.group(2)
        dim_str = m.group(3)

        if not signal_name:
            continue

        dims = _parse_dimensions(dim_str)
        purpose = _infer_purpose(signal_name)
        evaluated = "\u00d7".join(dims) if dims else "unknown"

        claim_text = (
            f"Wire '{signal_name}' of type '{struct_type}' "
            f"with dimensions [{', '.join(dims)}] "
            f"({evaluated} array) for {purpose}"
        )
        if struct_type in known_structs:
            claim_text += f" [references struct {struct_type}]"

        claims.append(_make_claim(
            claim_text, "structural", module_name,
            "WireTopology", file_path, pipeline_id,
            parser_source="wire_declaration_parser",
        ))

    # Deduplicate claims by signal name (Pattern A and C may overlap)
    seen_signals = set()
    deduped = []
    for claim in claims:
        # Extract signal name from claim text
        sig_match = re.search(r"Wire '(\w+)'", claim["claim_text"])
        if sig_match:
            sig = sig_match.group(1)
            if sig in seen_signals:
                continue
            seen_signals.add(sig)
        deduped.append(claim)

    if deduped:
        logger.info(
            "Extracted %d wire declaration claims from module '%s' in %s",
            len(deduped), module_name, file_path,
        )

    return deduped


def _strip_comments(content):
    """Remove single-line and block comments from RTL content."""
    content = re.sub(r"//[^\n]*", "", content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return content


def _parse_dimensions(dim_str):
    """Parse '[SizeX][SizeY-1][2]' → ['SizeX', 'SizeY-1', '2']"""
    dims = re.findall(r'\[([^\]]+)\]', dim_str)
    return [d.strip() for d in dims]


def _infer_purpose(signal_name):
    """Infer connection purpose from signal name using heuristics."""
    if not signal_name:
        return "general interconnect"
    name_lower = signal_name.lower()
    for pattern, purpose in PURPOSE_HEURISTICS.items():
        if pattern in name_lower:
            return purpose
    return "general interconnect"
