"""
EDC topology analysis for RTL auto-analysis pipeline.

Analyzes EDC subsystem ring topology, serial bus protocol,
harvest bypass mechanisms, and node ID structures from
tt_edc1_* module instantiation patterns.

Requirements validated: 13.1, 13.2, 13.3, 13.4
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for EDC analysis
# ---------------------------------------------------------------------------

# Serial bus interface signals in tt_edc1_pkg.sv
_SERIAL_BUS_SIGNAL_RE = re.compile(
    r"(?:logic|wire|reg)\s*(?:\[.*?\])?\s*(\w+)\s*[;,]",
    re.IGNORECASE,
)

_SERIAL_BUS_KEYWORDS = {"req_tgl", "ack_tgl", "data", "data_p", "async_init"}

# Node ID fields
_NODE_ID_RE = re.compile(
    r"(?:localparam|parameter)\s+(?:\w+\s+)?(\w*node_id\w*)\s*=\s*([^;]+);",
    re.IGNORECASE,
)

# Mux/demux module patterns for harvest bypass
_MUX_DEMUX_RE = re.compile(
    r"(tt_edc1_serial_bus_(?:mux|demux))",
    re.IGNORECASE,
)


def build_edc_topology(edc_modules: list[dict[str, Any]]) -> dict[str, Any]:
    """Reconstruct ring topology from tt_edc1_* module instantiation patterns.

    Analyzes module instance lists to identify EDC node connections and
    reconstructs the U-shape ring topology (Segment A down -> U-turn ->
    Segment B up).

    Args:
        edc_modules: List of module dicts with at least ``module_name``
            and ``instance_list`` keys.

    Returns:
        A dict with:
            - ``nodes``: list of node names in ring order
            - ``segment_a``: list of nodes in segment A (downward)
            - ``u_turn``: the U-turn node (or empty string)
            - ``segment_b``: list of nodes in segment B (upward)
            - ``connections``: list of {from, to} dicts
    """
    if not edc_modules or not isinstance(edc_modules, list):
        logger.warning("build_edc_topology: empty or invalid input")
        return {
            "nodes": [], "segment_a": [], "u_turn": "",
            "segment_b": [], "connections": [],
        }

    # Collect EDC node modules
    edc_nodes: list[str] = []
    connections: list[dict[str, str]] = []

    for mod in edc_modules:
        if not isinstance(mod, dict):
            continue
        module_name = mod.get("module_name", "")
        instance_list = mod.get("instance_list", "")

        if not module_name:
            continue

        # Identify EDC node modules
        if re.match(r"tt_edc1_", module_name, re.IGNORECASE):
            if module_name not in edc_nodes:
                edc_nodes.append(module_name)

        # Parse instance list for connections
        if instance_list:
            for inst_entry in instance_list.split(","):
                inst_entry = inst_entry.strip()
                if ":" in inst_entry:
                    _, inst_type = inst_entry.split(":", 1)
                    inst_type = inst_type.strip()
                    if re.match(r"tt_edc1_", inst_type, re.IGNORECASE):
                        connections.append({
                            "from": module_name,
                            "to": inst_type,
                        })

    # Build ring topology (U-shape heuristic)
    nodes_sorted = sorted(edc_nodes)
    mid = len(nodes_sorted) // 2

    segment_a = nodes_sorted[:mid] if nodes_sorted else []
    u_turn = nodes_sorted[mid] if len(nodes_sorted) > mid else ""
    segment_b = nodes_sorted[mid + 1:] if len(nodes_sorted) > mid + 1 else []

    logger.info(
        "Built EDC topology: %d nodes, %d connections",
        len(nodes_sorted), len(connections),
    )
    return {
        "nodes": nodes_sorted,
        "segment_a": segment_a,
        "u_turn": u_turn,
        "segment_b": segment_b,
        "connections": connections,
    }


def identify_harvest_bypass(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identify harvest bypass paths from mux/demux instantiation patterns.

    Searches for ``tt_edc1_serial_bus_mux`` and ``tt_edc1_serial_bus_demux``
    instances to identify bypass paths.

    Args:
        modules: List of module dicts with ``module_name`` and
            ``instance_list`` keys.

    Returns:
        List of bypass path dicts with ``from``, ``to``, ``type``,
        and ``bypass_module`` keys.
    """
    if not modules or not isinstance(modules, list):
        logger.warning("identify_harvest_bypass: empty or invalid input")
        return []

    bypass_paths: list[dict[str, Any]] = []

    for mod in modules:
        if not isinstance(mod, dict):
            continue
        module_name = mod.get("module_name", "")
        instance_list = mod.get("instance_list", "")

        if not instance_list:
            continue

        for inst_entry in instance_list.split(","):
            inst_entry = inst_entry.strip()
            match = _MUX_DEMUX_RE.search(inst_entry)
            if match:
                bypass_module = match.group(1)
                if "demux" in bypass_module.lower():
                    bypass_type = "demux_bypass"
                else:
                    bypass_type = "mux_bypass"
                bypass_paths.append({
                    "from": module_name,
                    "to": bypass_module,
                    "type": bypass_type,
                    "bypass_module": bypass_module,
                })

    logger.info("Identified %d harvest bypass paths", len(bypass_paths))
    return bypass_paths


def extract_serial_bus_interface(pkg_content: str) -> dict[str, Any]:
    """Extract serial bus interface definition from tt_edc1_pkg.sv.

    Looks for known serial bus signals (req_tgl, ack_tgl, data, data_p,
    async_init) in the package content.

    Args:
        pkg_content: Raw content of tt_edc1_pkg.sv.

    Returns:
        A dict with:
            - ``signals``: list of identified serial bus signal names
            - ``all_signals``: list of all signal declarations found
    """
    if not pkg_content or not isinstance(pkg_content, str):
        logger.warning("extract_serial_bus_interface: empty or invalid input")
        return {"signals": [], "all_signals": []}

    all_signals: list[str] = []
    bus_signals: list[str] = []

    for match in _SERIAL_BUS_SIGNAL_RE.finditer(pkg_content):
        sig_name = match.group(1)
        all_signals.append(sig_name)
        if sig_name.lower() in _SERIAL_BUS_KEYWORDS:
            bus_signals.append(sig_name)

    # Also search for keywords in broader context
    for keyword in _SERIAL_BUS_KEYWORDS:
        pattern = re.compile(r"\b(" + keyword + r")\b", re.IGNORECASE)
        for m in pattern.finditer(pkg_content):
            found = m.group(1)
            if found not in bus_signals:
                bus_signals.append(found)

    logger.info("Extracted %d serial bus signals", len(bus_signals))
    return {"signals": sorted(set(bus_signals)), "all_signals": all_signals}


def build_node_id_table(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build node ID decoding table from (part/subp/inst) fields.

    Extracts node_id_part, node_id_subp, node_id_inst parameters from
    module declarations to build a decoding table.

    Args:
        modules: List of module dicts with ``module_name`` and
            ``parameter_list`` keys.

    Returns:
        List of dicts with ``node``, ``part``, ``subp``, ``inst`` keys.
    """
    if not modules or not isinstance(modules, list):
        logger.warning("build_node_id_table: empty or invalid input")
        return []

    table: list[dict[str, Any]] = []

    for mod in modules:
        if not isinstance(mod, dict):
            continue
        module_name = mod.get("module_name", "")
        param_list = mod.get("parameter_list", "")

        if not param_list:
            continue

        part = _extract_node_id_field(param_list, "part")
        subp = _extract_node_id_field(param_list, "subp")
        inst = _extract_node_id_field(param_list, "inst")

        if part is not None or subp is not None or inst is not None:
            table.append({
                "node": module_name,
                "part": part if part is not None else 0,
                "subp": subp if subp is not None else 0,
                "inst": inst if inst is not None else 0,
            })

    logger.info("Built node ID table with %d entries", len(table))
    return table


def _extract_node_id_field(param_list: str, field: str) -> int | None:
    """Extract a node_id field value from parameter list text."""
    pattern = re.compile(
        r"node_id_" + field + r"\s*=\s*(\d+)",
        re.IGNORECASE,
    )
    match = pattern.search(param_list)
    if match:
        try:
            return int(match.group(1))
        except (ValueError, TypeError):
            return None
    return None
