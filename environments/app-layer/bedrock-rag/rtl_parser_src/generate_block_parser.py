"""Generate Block Parser for SystemVerilog generate for/if blocks.

Extracts generate block topology patterns (daisy-chain, ring, feedthrough,
2D array) from RTL files and converts them to structured claims for RAG
indexing.

v9 Phase 7 — addresses the gap where module_parse captures module
declarations but misses generate block wiring topology such as EDC
U-shape ring, dispatch feedthrough, and clock routing 2D array.

Recognized topology patterns:
  - daisy-chain: signal[i+1] = signal[i] sequential chaining
  - ring: circular connection where signal[N-1] connects back to signal[0]
  - feedthrough: signal[y] = (y==0) ? source : signal[y-1]
  - 2D array: double nested for (genvar x...) for (genvar y...) with signal[x][y]

Also detects conditional bypass patterns:
  if (condition) begin ... end else begin assign bypass; end
"""

import re
import hashlib
import logging

logger = logging.getLogger(__name__)


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



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_generate_blocks(rtl_content, module_name="", file_path="",
                            pipeline_id=""):
    """Extract generate for/if blocks and identify topology patterns.

    Scans RTL content for generate blocks, identifies wiring topology
    patterns (daisy-chain, ring, feedthrough, 2D array), detects
    conditional bypass patterns, and produces structured claims.

    Args:
        rtl_content: Raw RTL source code string.
        module_name: Name of the module being parsed.
        file_path: Source file path for claim metadata.
        pipeline_id: Pipeline identifier for claim metadata.

    Returns:
        List of claim dicts ready for OpenSearch indexing.
    """
    claims = []

    # Strip comments for reliable pattern matching
    clean = _strip_comments(rtl_content)

    # Extract module name from content if not provided
    if not module_name:
        mod_match = re.search(r"\bmodule\s+(\w+)\s*(?:#\s*\(|[\(\;])", clean)
        module_name = mod_match.group(1) if mod_match else "unknown"

    # Find all generate blocks (generate ... endgenerate)
    gen_blocks = _find_generate_blocks(clean)

    if not gen_blocks:
        logger.debug(
            "No generate blocks found in %s (%s)", module_name, file_path,
        )
        return claims

    for block_text in gen_blocks:
        block_claims = _analyze_generate_block(
            block_text, module_name, file_path, pipeline_id,
        )
        claims.extend(block_claims)

    logger.info(
        "Extracted %d generate block claims from module '%s' in %s",
        len(claims), module_name, file_path,
    )
    return claims


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_comments(content):
    """Remove single-line and block comments from RTL content."""
    content = re.sub(r"//[^\n]*", "", content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return content


def _find_generate_blocks(clean_content):
    """Find top-level generate ... endgenerate block bodies.

    Returns a list of block body strings (content between generate
    and endgenerate keywords).
    """
    blocks = []
    # Match generate ... endgenerate pairs (non-greedy)
    pattern = re.compile(
        r"\bgenerate\b(.*?)\bendgenerate\b",
        re.DOTALL,
    )
    for m in pattern.finditer(clean_content):
        body = m.group(1).strip()
        if body:
            blocks.append(body)
    return blocks


def _analyze_generate_block(block_text, module_name, file_path, pipeline_id):
    """Analyze a single generate block and produce claims.

    Extracts for-loop structures, identifies topology patterns,
    detects bypass conditions, and generates claims.
    """
    claims = []

    # Find all for-loop headers in this block
    for_loops = _extract_for_loops(block_text)

    if not for_loops:
        # Generate block without for loops (e.g., generate if only)
        if_claims = _extract_generate_if_claims(
            block_text, module_name, file_path, pipeline_id,
        )
        claims.extend(if_claims)
        return claims

    # Check for nested (2D) generate loops
    nested_loops = _find_nested_loops(block_text)

    if nested_loops:
        for nested in nested_loops:
            nested_claims = _analyze_nested_generate(
                nested, block_text, module_name, file_path, pipeline_id,
            )
            claims.extend(nested_claims)
    else:
        # Single-level for loops
        for loop_info in for_loops:
            loop_claims = _analyze_single_loop(
                loop_info, block_text, module_name, file_path, pipeline_id,
            )
            claims.extend(loop_claims)

    return claims


def _extract_for_loops(block_text):
    """Extract for-loop header information from a generate block.

    Returns list of dicts with keys:
        genvar: genvar name (e.g., 'x', 'y')
        start: start value string (e.g., '0')
        limit: upper limit string (e.g., 'SizeX')
        label: block label if present (e.g., 'gen_edc_col')
        body_start: character position where the loop body starts
    """
    loops = []
    # Match: for (genvar <var> = <start>; <var> < <limit>; <var>++) begin : <label>
    pattern = re.compile(
        r"\bfor\s*\(\s*genvar\s+(\w+)\s*=\s*(\w+)\s*;\s*\w+\s*<\s*(\w+)\s*;"
        r"\s*\w+\s*\+\+\s*\)\s*begin\s*(?::\s*(\w+))?",
    )
    for m in pattern.finditer(block_text):
        loops.append({
            "genvar": m.group(1),
            "start": m.group(2),
            "limit": m.group(3),
            "label": m.group(4) or "",
            "body_start": m.end(),
        })
    return loops


def _find_nested_loops(block_text):
    """Find nested (2-level) for-loop structures.

    Returns list of dicts with outer and inner loop info:
        outer_genvar, outer_limit, outer_label,
        inner_genvar, inner_limit, inner_label,
        body: the inner loop body text
    """
    nested = []
    # Match outer for ... begin : label  inner for ... begin : label ... end end
    pattern = re.compile(
        r"\bfor\s*\(\s*genvar\s+(\w+)\s*=\s*\w+\s*;\s*\w+\s*<\s*(\w+)\s*;"
        r"\s*\w+\s*\+\+\s*\)\s*begin\s*(?::\s*(\w+))?"
        r"\s+"
        r"for\s*\(\s*genvar\s+(\w+)\s*=\s*\w+\s*;\s*\w+\s*<\s*(\w+)\s*;"
        r"\s*\w+\s*\+\+\s*\)\s*begin\s*(?::\s*(\w+))?"
        r"(.*?)"
        r"\bend\b\s*\bend\b",
        re.DOTALL,
    )
    for m in pattern.finditer(block_text):
        nested.append({
            "outer_genvar": m.group(1),
            "outer_limit": m.group(2),
            "outer_label": m.group(3) or "",
            "inner_genvar": m.group(4),
            "inner_limit": m.group(5),
            "inner_label": m.group(6) or "",
            "body": m.group(7).strip(),
            "full_match": m.group(0),
        })
    return nested


def _analyze_nested_generate(nested, block_text, module_name,
                             file_path, pipeline_id):
    """Analyze a nested (2D) generate block and produce claims."""
    claims = []
    outer_var = nested["outer_genvar"]
    inner_var = nested["inner_genvar"]
    outer_limit = nested["outer_limit"]
    inner_limit = nested["inner_limit"]
    label = nested["outer_label"] or nested["inner_label"] or "unnamed"
    body = nested["body"]

    dimension = f"2D {outer_var}×{inner_var}"
    size = f"{outer_limit}×{inner_limit}"

    # Detect topology pattern from the body
    pattern_type, signal_name = _detect_topology_pattern(
        body, inner_var, outer_var,
    )

    # Detect bypass condition
    bypass_info = _detect_bypass(body)

    # Build claim text
    claim_text = (
        f"Module '{module_name}' has generate block '{label}' "
        f"with {pattern_type} topology connecting {signal_name} "
        f"across {dimension} ({size} elements)"
    )

    if bypass_info:
        claim_text += (
            f". Conditional bypass: when {bypass_info['condition']}, "
            f"{bypass_info['bypass_signal']} is bypassed"
        )

    claims.append(_make_claim(
        claim_text, "structural", module_name,
        "GenerateTopology", file_path, pipeline_id,
        parser_source="generate_block_parser",
    ))

    return claims


def _analyze_single_loop(loop_info, block_text, module_name,
                         file_path, pipeline_id):
    """Analyze a single-level generate for loop and produce claims."""
    claims = []
    genvar = loop_info["genvar"]
    limit = loop_info["limit"]
    label = loop_info["label"] or "unnamed"

    # Extract the loop body (from body_start to matching 'end')
    body = _extract_loop_body(block_text, loop_info["body_start"])

    if not body:
        return claims

    dimension = genvar
    size = limit

    # Detect topology pattern
    pattern_type, signal_name = _detect_topology_pattern(body, genvar)

    # Detect bypass condition
    bypass_info = _detect_bypass(body)

    # Build claim text
    claim_text = (
        f"Module '{module_name}' has generate block '{label}' "
        f"with {pattern_type} topology connecting {signal_name} "
        f"across {dimension} ({size} elements)"
    )

    if bypass_info:
        claim_text += (
            f". Conditional bypass: when {bypass_info['condition']}, "
            f"{bypass_info['bypass_signal']} is bypassed"
        )

    claims.append(_make_claim(
        claim_text, "structural", module_name,
        "GenerateTopology", file_path, pipeline_id,
        parser_source="generate_block_parser",
    ))

    return claims


def _extract_loop_body(block_text, body_start):
    """Extract the body of a for loop starting at body_start position.

    Finds the matching 'end' for the 'begin' at body_start by counting
    begin/end nesting levels.
    """
    if body_start >= len(block_text):
        return ""

    rest = block_text[body_start:]
    depth = 1
    # Tokenize begin/end keywords
    token_pattern = re.compile(r"\b(begin|end)\b")
    for m in token_pattern.finditer(rest):
        if m.group(1) == "begin":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return rest[:m.start()].strip()
    # If no matching end found, return everything
    return rest.strip()


def _detect_topology_pattern(body, primary_var, secondary_var=None):
    """Detect the wiring topology pattern in a generate block body.

    Checks for feedthrough, ring, daisy-chain, and 2D array patterns
    in order of specificity.

    Args:
        body: The generate block body text.
        primary_var: The primary genvar name (e.g., 'y').
        secondary_var: The secondary genvar name for nested loops (e.g., 'x').

    Returns:
        Tuple of (pattern_type, signal_name).
    """
    # 1. Feedthrough pattern: signal[var] = (var==0) ? source : signal[var-1]
    feedthrough_match = re.search(
        r"(?:assign\s+)?(\w+)"
        r"\s*\[" + re.escape(primary_var) + r"\]"
        r"\s*=\s*\(" + re.escape(primary_var) + r"\s*==\s*0\s*\)"
        r"\s*\?\s*(\w+)\s*:\s*(\w+)\[" + re.escape(primary_var) + r"\s*-\s*1\]",
        body,
    )
    if feedthrough_match:
        signal_name = feedthrough_match.group(1)
        return ("feedthrough", signal_name)

    # 2. Ring pattern: signal[N-1] connects back to signal[0]
    ring_match = re.search(
        r"(\w+)\s*\[\s*\w+\s*-\s*1\s*\].*?(\w+)\s*\[\s*0\s*\]",
        body, re.DOTALL,
    )
    if ring_match:
        signal_name = ring_match.group(1)
        return ("ring", signal_name)

    # 3. Daisy-chain pattern: signal[var+1] = signal[var]
    #    Check before 2D array because nested loops may have both
    #    2D-indexed signals and daisy-chain wiring (e.g., edc_chain[x][y+1])
    #    Also handles multi-dimensional: signal[x][var+1] = signal[x][var]
    daisy_match = re.search(
        r"(\w+)"
        r"(?:\[[^\]]*\])*"  # optional preceding indices like [x]
        r"\s*\[\s*" + re.escape(primary_var) + r"\s*\+\s*1\s*\]"
        r"\s*=\s*(\w+)"
        r"(?:\[[^\]]*\])*"  # optional preceding indices
        r"\s*\[" + re.escape(primary_var) + r"\]",
        body,
    )
    if daisy_match:
        signal_name = daisy_match.group(1)
        return ("daisy-chain", signal_name)

    # Also check for instance port connections that form a daisy chain:
    # .o_serial_out(signal[x][var+1]), .i_serial_in(signal[x][var])
    daisy_port_match = re.search(
        r"(\w+)"
        r"(?:\[[^\]]*\])*"  # optional preceding indices
        r"\s*\[\s*" + re.escape(primary_var) + r"\s*\+\s*1\s*\]",
        body,
    )
    if daisy_port_match:
        same_signal = daisy_port_match.group(1)
        also_base = re.search(
            re.escape(same_signal)
            + r"(?:\[[^\]]*\])*"  # optional preceding indices
            + r"\s*\[\s*" + re.escape(primary_var) + r"\s*\]",
            body,
        )
        if also_base:
            return ("daisy-chain", same_signal)

    # 4. 2D array pattern: signal[x][y] with two genvars
    if secondary_var:
        twod_match = re.search(
            r"(\w+)\s*\[" + re.escape(secondary_var) + r"\]"
            r"\s*\[" + re.escape(primary_var) + r"\]",
            body,
        )
        if not twod_match:
            twod_match = re.search(
                r"(\w+)\s*\[" + re.escape(primary_var) + r"\]"
                r"\s*\[" + re.escape(secondary_var) + r"\]",
                body,
            )
        if twod_match:
            signal_name = twod_match.group(1)
            return ("2D array", signal_name)

    # 5. Check for 2D array with dot access: signal[x][y].field
    if secondary_var:
        twod_dot_match = re.search(
            r"(\w+)\s*\[\s*" + re.escape(secondary_var) + r"\s*\]"
            r"\s*\[\s*" + re.escape(primary_var) + r"\s*\]\s*\.\s*\w+",
            body,
        )
        if not twod_dot_match:
            twod_dot_match = re.search(
                r"(\w+)\s*\[\s*" + re.escape(primary_var) + r"\s*\]"
                r"\s*\[\s*" + re.escape(secondary_var) + r"\s*\]\s*\.\s*\w+",
                body,
            )
        if twod_dot_match:
            signal_name = twod_dot_match.group(1)
            return ("2D array", signal_name)

    # Fallback: try to find any indexed signal
    any_signal = re.search(
        r"(\w+)\s*\[\s*" + re.escape(primary_var) + r"[^\]]*\]",
        body,
    )
    signal_name = any_signal.group(1) if any_signal else "unknown_signal"

    return ("unknown", signal_name)


def _detect_bypass(body):
    """Detect conditional bypass patterns in a generate block body.

    Looks for patterns like:
        if (condition) begin ... end else begin assign signal = signal; end

    Returns:
        Dict with 'condition' and 'bypass_signal' keys, or None.
    """
    # Extract the condition from if (...) begin, handling nested brackets
    # in conditions like tile_type[x][y] != HARVESTED
    if_match = re.search(r"\bif\s*\(", body)
    if not if_match:
        return None

    # Find the matching closing paren by counting depth
    start = if_match.end()
    depth = 1
    pos = start
    while pos < len(body) and depth > 0:
        if body[pos] == "(":
            depth += 1
        elif body[pos] == ")":
            depth -= 1
        pos += 1

    if depth != 0:
        return None

    condition = body[start:pos - 1].strip()

    # Now look for the else begin ... assign pattern after the if block
    rest_after_if = body[pos:]
    else_assign_match = re.search(
        r"\belse\s*begin\b"
        r"\s*assign\s+(\w+)"
        r"(?:\[[^\]]*\])*"  # zero or more bracket indices
        r"\s*=\s*(\w+)"
        r"(?:\[[^\]]*\])*"  # zero or more bracket indices
        r"\s*;",
        rest_after_if, re.DOTALL,
    )
    if else_assign_match:
        bypass_target = else_assign_match.group(1)
        return {
            "condition": condition,
            "bypass_signal": bypass_target,
            "bypass_source": else_assign_match.group(2),
        }

    return None


def _extract_generate_if_claims(block_text, module_name, file_path,
                                pipeline_id):
    """Extract claims from generate-if blocks (without for loops).

    Handles standalone generate if/else blocks.
    """
    claims = []
    # Match: if (condition) begin : label ... end
    pattern = re.compile(
        r"\bif\s*\(([^)]+)\)\s*begin\s*(?::\s*(\w+))?"
        r"(.*?)"
        r"\bend\b",
        re.DOTALL,
    )
    for m in pattern.finditer(block_text):
        condition = m.group(1).strip()
        label = m.group(2) or "unnamed"
        body = m.group(3).strip()

        if not body:
            continue

        # Try to find what signal/instance is conditionally created
        inst_match = re.search(r"(\w+)\s+(\w+)\s*\(", body)
        signal_match = re.search(r"assign\s+(\w+)", body)

        target = "conditional logic"
        if inst_match:
            target = f"instance {inst_match.group(2)}: {inst_match.group(1)}"
        elif signal_match:
            target = f"signal {signal_match.group(1)}"

        claim_text = (
            f"Module '{module_name}' has generate block '{label}' "
            f"with conditional instantiation: when ({condition}), "
            f"{target} is created"
        )

        claims.append(_make_claim(
            claim_text, "structural", module_name,
            "GenerateTopology", file_path, pipeline_id,
            parser_source="generate_block_parser",
        ))

    return claims
