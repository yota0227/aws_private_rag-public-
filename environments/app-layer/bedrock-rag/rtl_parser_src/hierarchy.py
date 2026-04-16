"""
Hierarchy tree builder for RTL auto-analysis pipeline.

Builds a parent->child relationship graph from parsed RTL module data,
identifies root modules, performs DFS traversal to generate hierarchy paths,
and provides JSON/CSV serialization.

Requirements validated: 2.1, 2.2, 2.3, 2.4, 2.5
"""

import csv
import io
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Patterns for identifying memory instances (case-insensitive)
_MEMORY_PATTERNS = re.compile(
    r"(mem|sram|ram|rom|fifo|reg_bank|latch)", re.IGNORECASE
)

# Patterns for clock/reset signal extraction from port_list
_CLOCK_PATTERN = re.compile(r"(clk|clock)", re.IGNORECASE)
_RESET_PATTERN = re.compile(r"(reset|rst)", re.IGNORECASE)


def _parse_instance_list(instance_list_str: str) -> list[tuple[str, str]]:
    """Parse comma-separated instance list into (instance_name, module_type) pairs.

    Expected format: ``inst1: module_type1, inst2: module_type2``
    """
    if not instance_list_str or not instance_list_str.strip():
        return []
    pairs: list[tuple[str, str]] = []
    for entry in instance_list_str.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ": " in entry:
            inst_name, mod_type = entry.split(": ", 1)
            pairs.append((inst_name.strip(), mod_type.strip()))
    return pairs


def _extract_signals(port_list_str: str, pattern: re.Pattern) -> list[str]:
    """Extract signal names from port_list string matching a regex pattern."""
    if not port_list_str or not port_list_str.strip():
        return []
    signals: list[str] = []
    for entry in port_list_str.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split()
        signal_name = parts[-1] if parts else ""
        if signal_name and pattern.search(signal_name):
            signals.append(signal_name)
    return signals


def _identify_memory_instances(instance_list_str: str) -> list[str]:
    """Identify memory instances from instance_list string."""
    if not instance_list_str or not instance_list_str.strip():
        return []
    memories: list[str] = []
    for entry in instance_list_str.split(","):
        entry = entry.strip()
        if not entry:
            continue
        inst_name = entry.split(": ", 1)[0].strip() if ": " in entry else entry
        if _MEMORY_PATTERNS.search(inst_name):
            memories.append(inst_name)
    return memories


def build_hierarchy(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build hierarchy tree from a list of parsed module dicts.

    Each module dict is expected to have:
        - module_name: str
        - instance_list: str  (comma-separated "inst: type" pairs)
        - port_list: str      (comma-separated "direction signal" entries)
        - parameter_list: str
        - file_path: str

    Returns a list of root hierarchy nodes. Each node contains:
        module_name, instance_name, hierarchy_path, clock_signals,
        reset_signals, memory_instances, children.

    Circular references are detected and the offending branch is cut
    with a warning logged.
    """
    if not modules:
        return []

    # Index modules by name for quick lookup
    module_map: dict[str, dict[str, Any]] = {}
    for mod in modules:
        name = mod.get("module_name", "")
        if name:
            module_map[name] = mod

    # Build parent->child edges
    children_of: dict[str, list[tuple[str, str]]] = {}
    instantiated: set[str] = set()

    for mod in modules:
        parent_name = mod.get("module_name", "")
        if not parent_name:
            continue
        inst_str = mod.get("instance_list", "")
        pairs = _parse_instance_list(inst_str)
        children_of[parent_name] = pairs
        for _, child_type in pairs:
            instantiated.add(child_type)

    # Root modules: defined but not instantiated by any other
    all_defined = set(module_map.keys())
    roots = all_defined - instantiated
    if not roots:
        roots = all_defined

    sorted_roots = sorted(roots)

    def _build_node(
        module_name: str,
        instance_name: str,
        parent_path: str,
        visited: set[str],
    ) -> dict[str, Any]:
        hierarchy_path = (
            f"{parent_path}.{instance_name}" if parent_path else module_name
        )
        mod_data = module_map.get(module_name, {})
        port_list_str = mod_data.get("port_list", "")
        inst_list_str = mod_data.get("instance_list", "")

        node: dict[str, Any] = {
            "module_name": module_name,
            "instance_name": instance_name,
            "hierarchy_path": hierarchy_path,
            "clock_signals": _extract_signals(port_list_str, _CLOCK_PATTERN),
            "reset_signals": _extract_signals(port_list_str, _RESET_PATTERN),
            "memory_instances": _identify_memory_instances(inst_list_str),
            "children": [],
        }

        for child_inst, child_type in children_of.get(module_name, []):
            if child_type in visited:
                logger.warning(
                    "Circular reference detected: %s -> %s (instance %s). "
                    "Cutting branch.",
                    module_name, child_type, child_inst,
                )
                continue
            visited.add(child_type)
            child_node = _build_node(
                child_type, child_inst, hierarchy_path, visited
            )
            node["children"].append(child_node)
            visited.discard(child_type)

        return node

    tree: list[dict[str, Any]] = []
    for root_name in sorted_roots:
        visited: set[str] = {root_name}
        root_node = _build_node(root_name, root_name, "", visited)
        tree.append(root_node)

    return tree


def serialize_hierarchy_json(tree: list[dict[str, Any]]) -> str:
    """Serialize hierarchy tree to a JSON string.

    The output is deterministic (sorted keys) and can be deserialized
    back to an identical structure via ``json.loads``.
    """
    return json.dumps(tree, ensure_ascii=False, indent=2, sort_keys=True)


def _flatten_tree(
    nodes: list[dict[str, Any]], rows: list[dict[str, str]]
) -> None:
    """Recursively flatten hierarchy tree into CSV-ready row dicts."""
    for node in nodes:
        rows.append({
            "Hierarchy": node.get("hierarchy_path", ""),
            "Module": node.get("module_name", ""),
            "Clock": "/".join(node.get("clock_signals", [])),
            "Reset": "/".join(node.get("reset_signals", [])),
            "Memory_Instances": "/".join(node.get("memory_instances", [])),
        })
        _flatten_tree(node.get("children", []), rows)


def serialize_hierarchy_csv(tree: list[dict[str, Any]]) -> str:
    """Serialize hierarchy tree to CSV string.

    Columns: Hierarchy, Module, Clock, Reset, Memory_Instances.
    Clock/reset/memory values are slash-separated, matching
    the trinity_hierarchy.csv style.
    """
    rows: list[dict[str, str]] = []
    _flatten_tree(tree, rows)

    output = io.StringIO()
    fieldnames = ["Hierarchy", "Module", "Clock", "Reset", "Memory_Instances"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
