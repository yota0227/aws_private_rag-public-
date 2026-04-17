"""
Data flow tracking for RTL auto-analysis pipeline.

Extracts port mappings from Verilog module instantiations,
detects bit-width mismatches, and builds dataflow connection graphs.

Requirements validated: 4.1, 4.2, 4.3, 4.5
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Regex to match Verilog module instantiation header:
#   module_name #(...) instance_name (
# or without parameters:
#   module_name instance_name (
_INSTANCE_HEADER_RE = re.compile(
    r"(\w+)\s+"                   # module_name
    r"(?:#\s*\((?:[^()]*|\([^()]*\))*\)\s*)?"  # optional #(params) with nesting
    r"(\w+)\s*\(",                # instance_name (
    re.DOTALL,
)

# Regex to match port mapping: .port_name(signal_name)
# signal_name may include bit-select like signal[7:0] or signal[MSB:LSB]
_PORT_MAPPING_RE = re.compile(
    r"\.\s*(\w+)\s*\(\s*"         # .port_name(
    r"([^)]*?)"                   # signal expression (non-greedy)
    r"\s*\)",                     # )
)

# Regex to extract bit width [MSB:LSB] from a signal expression
_BIT_WIDTH_RE = re.compile(
    r"\[\s*(\d+)\s*:\s*(\d+)\s*\]"
)

# Verilog keywords that should not be treated as module names
_VERILOG_KEYWORDS = frozenset({
    "module", "endmodule", "input", "output", "inout",
    "wire", "reg", "logic", "assign", "always", "always_ff",
    "always_comb", "initial", "begin", "end", "if", "else",
    "case", "for", "generate", "function", "task",
})


def extract_port_mappings(rtl_content: str) -> list[dict[str, Any]]:
    """Extract port mappings from Verilog module instantiations.

    Scans *rtl_content* for module instantiation patterns and extracts
    ``.port_name(signal_name)`` connections, including optional bit-width
    information ``[MSB:LSB]``.

    Args:
        rtl_content: Raw RTL (Verilog/SystemVerilog) source text.

    Returns:
        List of dicts, each containing:
            - ``module_name``: instantiated module type
            - ``instance_name``: instance identifier
            - ``child_port``: port name on the child module
            - ``parent_signal``: signal name in the parent module
            - ``bit_width``: integer bit width if ``[MSB:LSB]`` found, else None
    """
    if not rtl_content or not isinstance(rtl_content, str):
        return []

    results: list[dict[str, Any]] = []

    for inst_match in _INSTANCE_HEADER_RE.finditer(rtl_content):
        module_name = inst_match.group(1)
        instance_name = inst_match.group(2)

        # Skip Verilog keywords that look like instantiations
        if module_name in _VERILOG_KEYWORDS:
            continue

        # Find the matching closing parenthesis for the port list
        start_pos = inst_match.end() - 1  # position of '('
        depth = 1
        pos = start_pos + 1
        end_pos = len(rtl_content)
        while pos < end_pos and depth > 0:
            if rtl_content[pos] == '(':
                depth += 1
            elif rtl_content[pos] == ')':
                depth -= 1
            pos += 1

        port_block = rtl_content[start_pos:pos]

        for port_match in _PORT_MAPPING_RE.finditer(port_block):
            child_port = port_match.group(1)
            parent_signal_raw = port_match.group(2).strip()

            # Extract bit width if present
            bit_width = None
            bw_match = _BIT_WIDTH_RE.search(parent_signal_raw)
            if bw_match:
                msb = int(bw_match.group(1))
                lsb = int(bw_match.group(2))
                bit_width = abs(msb - lsb) + 1

            # Clean signal name (remove bit-select for the name)
            parent_signal = re.sub(r"\[.*?\]", "", parent_signal_raw).strip()
            if not parent_signal:
                parent_signal = parent_signal_raw

            results.append({
                "module_name": module_name,
                "instance_name": instance_name,
                "child_port": child_port,
                "parent_signal": parent_signal,
                "bit_width": bit_width,
            })

    return results


def detect_width_mismatch(parent_width: int, child_width: int) -> bool:
    """Detect bit-width mismatch between parent signal and child port.

    Args:
        parent_width: Bit width of the parent module signal.
        child_width: Bit width of the child module port.

    Returns:
        True if widths differ, False if they match.
    """
    if not isinstance(parent_width, int) or not isinstance(child_width, int):
        logger.warning(
            "Invalid width values: parent_width=%r, child_width=%r",
            parent_width, child_width,
        )
        return False
    return parent_width != child_width


def build_dataflow_connections(rtl_content: str) -> list[dict[str, Any]]:
    """Build dataflow connection list from RTL source content.

    Combines ``extract_port_mappings`` results into a structured
    connection list with direction inference and width-mismatch flags.

    Args:
        rtl_content: Raw RTL (Verilog/SystemVerilog) source text.

    Returns:
        List of connection dicts, each containing:
            - ``parent_signal``: signal in the parent module
            - ``child_module``: instantiated module type
            - ``child_port``: port on the child module
            - ``direction``: inferred direction (``input`` if port starts
              with ``i_`` or ``in_``, ``output`` if ``o_`` or ``out_``,
              otherwise ``unknown``)
            - ``bit_width``: integer bit width or None
            - ``width_mismatch``: always False here (requires external
              child port width info for real comparison)
    """
    if not rtl_content or not isinstance(rtl_content, str):
        return []

    mappings = extract_port_mappings(rtl_content)
    connections: list[dict[str, Any]] = []

    for mapping in mappings:
        child_port = mapping["child_port"]

        # Infer direction from port naming convention
        if child_port.startswith(("i_", "in_")):
            direction = "input"
        elif child_port.startswith(("o_", "out_")):
            direction = "output"
        else:
            direction = "unknown"

        connections.append({
            "parent_signal": mapping["parent_signal"],
            "child_module": mapping["module_name"],
            "child_port": child_port,
            "direction": direction,
            "bit_width": mapping["bit_width"],
            "width_mismatch": False,
        })

    return connections
