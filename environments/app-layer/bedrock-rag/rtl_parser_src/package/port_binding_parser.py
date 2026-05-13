"""Port Binding Parser for RTL files.

Extracts .port(signal) bindings from module instantiation statements in
SystemVerilog/Verilog RTL code. Distinguishes between #(…) parameter blocks
and (…) port blocks, handles concatenation bindings, unconnected ports,
and bit ranges.

parser_source: "port_binding_parser"
Feature flag: PARSER_PORT_BINDING_ENABLED
"""
import re
import os
import logging
import hashlib

logger = logging.getLogger(__name__)

# Feature flag
PARSER_PORT_BINDING_ENABLED = os.environ.get(
    'PARSER_PORT_BINDING_ENABLED', 'true'
).lower() == 'true'

# Port binding pattern: .port_name(signal_expr)
PORT_BINDING_PATTERN = re.compile(r'\.(\w+)\s*\(\s*(.*?)\s*\)')

# Concatenation pattern: {sig_a, sig_b, ...}
CONCAT_PATTERN = re.compile(r'^\{(.+)\}$')

# Bit range pattern: signal[N:M] or signal[N]
BIT_RANGE_PATTERN = re.compile(r'^(\w+)\s*(\[[\w\s:+\-*/$]+\])$')

# Keywords that cannot be module types in instantiation
_KEYWORDS = frozenset({
    "if", "for", "begin", "end", "assign", "always", "always_ff",
    "always_comb", "always_latch", "initial", "generate",
    "endgenerate", "module", "endmodule", "wire", "logic", "reg",
    "input", "output", "inout", "parameter", "localparam", "genvar",
    "else", "case", "endcase", "function", "endfunction", "task",
    "endtask", "typedef", "struct", "enum", "union", "interface",
    "endinterface", "package", "endpackage", "import", "export",
    "class", "endclass", "virtual", "extends", "implements",
    "return", "void", "integer", "real", "time", "string",
    "bit", "byte", "shortint", "int", "longint", "signed",
    "unsigned", "assert", "property", "sequence", "covergroup",
})


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


def extract_port_bindings(rtl_content, module_name="", file_path="",
                          pipeline_id=""):
    """Extract port bindings from module instantiation statements in RTL code.

    Parsing strategy:
    1. Identify instantiation statements: module_type [#(params)] instance_name (ports);
    2. Separate #(…) parameter block from (…) port block
    3. Extract .port_name(signal_expr) from port block only
    4. Decompose concatenation {a, b} into constituent_signals

    Args:
        rtl_content: Raw RTL source code string.
        module_name: Name of the module being parsed.
        file_path: Source file path for claim metadata.
        pipeline_id: Pipeline identifier for claim metadata.

    Returns:
        List of claim dicts ready for OpenSearch indexing.
    """
    if not PARSER_PORT_BINDING_ENABLED:
        return []

    if not rtl_content:
        return []

    # Strip comments for reliable matching
    clean = _strip_comments(rtl_content)

    # Extract module name if not provided
    if not module_name:
        mod_match = re.search(r"\bmodule\s+(\w+)\s*(?:#\s*\(|[\(\;])", clean)
        module_name = mod_match.group(1) if mod_match else "unknown"

    # Find all instantiation statements and extract port bindings
    bindings = _find_all_port_bindings(clean, file_path)

    if not bindings:
        return []

    # Convert bindings to claims
    claims = []
    for binding in bindings:
        instance_name = binding["instance_name"]
        module_type = binding["module_type"]
        port_name = binding["port_name"]
        signal_expr = binding["signal_expr"]

        claim_text = (
            f"Instance '{instance_name}' of module '{module_type}' "
            f"binds port '{port_name}' to signal '{signal_expr}'"
        )

        claims.append(_make_claim(
            claim_text, "structural", module_name,
            "PortBinding", file_path, pipeline_id,
            parser_source="port_binding_parser",
        ))

    if claims:
        logger.info(
            "Extracted %d port binding claims from module '%s' in %s",
            len(claims), module_name, file_path,
        )

    return claims


def _find_all_port_bindings(clean_content, file_path):
    """Find all module instantiation statements and extract port bindings.

    Returns list of binding dicts with keys:
        instance_name, module_type, port_name, signal_expr,
        bit_range, is_unconnected, is_concatenation,
        constituent_signals, source_file, line_number
    """
    bindings = []

    # Find instantiation statements
    instances = _find_instantiation_statements(clean_content)

    for inst in instances:
        module_type = inst["module_type"]
        instance_name = inst["instance_name"]
        port_block = inst["port_block"]
        line_number = inst["line_number"]

        # Extract .port_name(signal_expr) from port block
        port_bindings = _extract_port_bindings_from_block(port_block)

        # Track seen port names for duplicate detection
        seen_ports = set()

        for pb in port_bindings:
            port_name = pb["port_name"]
            signal_expr = pb["signal_expr"]

            # Duplicate port detection: first one wins
            if port_name in seen_ports:
                logger.warning(
                    "Duplicate port binding '.%s' in instance '%s' of "
                    "module '%s' in %s — keeping first occurrence",
                    port_name, instance_name, module_type, file_path,
                )
                continue
            seen_ports.add(port_name)

            # Determine if unconnected
            is_unconnected = (signal_expr == "")

            # Parse bit range from signal expression
            bit_range = None
            if not is_unconnected and not signal_expr.startswith("{"):
                bit_range_match = BIT_RANGE_PATTERN.match(signal_expr)
                if bit_range_match:
                    bit_range = bit_range_match.group(2)

            # Detect concatenation
            is_concatenation = False
            constituent_signals = []
            if not is_unconnected:
                concat_match = CONCAT_PATTERN.match(signal_expr)
                if concat_match:
                    is_concatenation = True
                    inner = concat_match.group(1)
                    constituent_signals = [
                        s.strip() for s in inner.split(",") if s.strip()
                    ]

            bindings.append({
                "instance_name": instance_name,
                "module_type": module_type,
                "port_name": port_name,
                "signal_expr": signal_expr,
                "bit_range": bit_range,
                "is_unconnected": is_unconnected,
                "is_concatenation": is_concatenation,
                "constituent_signals": constituent_signals,
                "source_file": file_path,
                "line_number": line_number,
            })

    return bindings


def _find_instantiation_statements(content):
    """Find module instantiation statements in RTL content.

    Identifies patterns: module_type [#(params)] instance_name (ports)
    Handles nested parentheses in both parameter and port blocks.

    Returns list of dicts with keys:
        module_type, instance_name, port_block, line_number
    """
    instances = []

    # Build line number lookup
    line_starts = [0]
    for i, ch in enumerate(content):
        if ch == '\n':
            line_starts.append(i + 1)

    def _char_to_line(pos):
        """Convert character position to 1-based line number."""
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    # Use regex to find candidate instantiation starts:
    # word whitespace [#(...)] word whitespace (
    # We find "word whitespace" then check what follows
    candidate_pattern = re.compile(r'\b(\w+)\s+')

    pos = 0
    while pos < len(content):
        m = candidate_pattern.search(content, pos)
        if not m:
            break

        module_type = m.group(1)
        start_pos = m.start()

        # Skip keywords
        if module_type in _KEYWORDS:
            pos = m.end()
            continue

        after_type = m.end()

        # Check for optional #(params) block
        param_end = after_type
        remaining = content[after_type:]

        hash_match = re.match(r'#\s*\(', remaining)
        if hash_match:
            # Found #( — find matching closing paren
            paren_start = after_type + hash_match.end() - 1
            param_close = _find_matching_paren(content, paren_start)
            if param_close < 0:
                pos = after_type
                continue
            param_end = param_close + 1
            # Skip whitespace after params
            ws_match = re.match(r'\s*', content[param_end:])
            if ws_match:
                param_end += ws_match.end()

        # Now expect instance_name (identifier)
        inst_match = re.match(r'(\w+)', content[param_end:])
        if not inst_match:
            pos = after_type
            continue

        instance_name = inst_match.group(1)
        if instance_name in _KEYWORDS:
            pos = after_type
            continue

        after_inst = param_end + inst_match.end()

        # Skip whitespace after instance name
        ws_match = re.match(r'\s*', content[after_inst:])
        if ws_match:
            after_inst += ws_match.end()

        # Expect opening paren for port connections
        if after_inst >= len(content) or content[after_inst] != '(':
            pos = after_type
            continue

        # Find matching closing paren for port block
        port_close = _find_matching_paren(content, after_inst)
        if port_close < 0:
            pos = after_type
            continue

        # Extract port block content (between parens)
        port_block = content[after_inst + 1:port_close]

        # Validate: port block should contain at least one .port_name( pattern
        if not re.search(r'\.\w+\s*\(', port_block):
            pos = after_type
            continue

        line_number = _char_to_line(start_pos)

        instances.append({
            "module_type": module_type,
            "instance_name": instance_name,
            "port_block": port_block,
            "line_number": line_number,
        })

        # Move past this instantiation
        pos = port_close + 1

    return instances


def _find_matching_paren(content, open_pos):
    """Find the matching closing parenthesis for an opening paren.

    Handles nested parentheses. Returns the position of the matching
    closing paren, or -1 if not found.
    """
    if open_pos >= len(content) or content[open_pos] != '(':
        return -1

    depth = 1
    pos = open_pos + 1
    while pos < len(content) and depth > 0:
        ch = content[pos]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        pos += 1

    if depth == 0:
        return pos - 1
    return -1


def _extract_port_bindings_from_block(port_block):
    """Extract .port_name(signal_expr) bindings from a port block string.

    Handles nested parentheses in signal expressions and concatenation.

    Returns list of dicts with keys: port_name, signal_expr
    """
    bindings = []

    # Find all .port_name( patterns and extract their signal expressions
    # using parenthesis matching for robustness
    pos = 0
    while pos < len(port_block):
        # Find next .identifier(
        dot_match = re.search(r'\.(\w+)\s*\(', port_block[pos:])
        if not dot_match:
            break

        port_name = dot_match.group(1)
        paren_start = pos + dot_match.end() - 1  # position of '('

        # Find matching closing paren
        paren_close = _find_matching_paren(port_block, paren_start)
        if paren_close < 0:
            pos += dot_match.end()
            continue

        # Extract signal expression between parens
        signal_expr = port_block[paren_start + 1:paren_close].strip()

        bindings.append({
            "port_name": port_name,
            "signal_expr": signal_expr,
        })

        pos = paren_close + 1

    return bindings


def _strip_comments(content):
    """Remove single-line and block comments from RTL content."""
    content = re.sub(r"//[^\n]*", "", content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return content
