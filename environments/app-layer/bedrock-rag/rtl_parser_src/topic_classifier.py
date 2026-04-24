"""
Topic classification for RTL auto-analysis pipeline.

Classifies RTL modules into topic categories based on file path
and module name pattern matching.  Supports 12 predefined topics
and inherited topic suggestion from hierarchy trees.

Requirements validated: 5.1, 5.2, 5.3, 5.4
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Topic classification rules.
# Each topic maps to path regex patterns and module-name prefixes.
TOPIC_RULES: dict[str, dict[str, list[str]]] = {
    "NoC":         {"path": [r"[/\\]noc[/\\]"],
                    "prefix": ["tt_noc_", "noc_"]},
    "FPU":         {"path": [r"[/\\]fpu[/\\]"],
                    "prefix": ["tt_fpu_", "fpu_"]},
    "SFPU":        {"path": [r"[/\\]sfpu[/\\]"],
                    "prefix": ["tt_sfpu", "sfpu_"]},
    "TDMA":        {"path": [r"[/\\]tdma[/\\]"],
                    "prefix": ["tt_tdma_", "tdma_"]},
    "Overlay":     {"path": [r"[/\\]overlay[/\\]"],
                    "prefix": ["tt_overlay_", "overlay_"]},
    "EDC":         {"path": [r"[/\\]edc[/\\]"],
                    "prefix": ["tt_edc", "edc_"]},
    "Dispatch":    {"path": [r"[/\\]dispatch[/\\]"],
                    "prefix": ["tt_dispatch_", "dispatch_"]},
    "L1_Cache":    {"path": [r"[/\\]l1[/\\]", r"[/\\]cache[/\\]"],
                    "prefix": ["tt_l1_", "l1_"]},
    "Clock_Reset": {"path": [r"[/\\]clk[/\\]", r"[/\\]reset[/\\]"],
                    "prefix": ["tt_clk_", "clk_", "rst_"]},
    "DFX":         {"path": [r"[/\\]dfx[/\\]"],
                    "prefix": ["tt_dfx_", "dfx_"]},
    "NIU":         {"path": [r"[/\\]niu[/\\]"],
                    "prefix": ["tt_niu_", "niu_", "tt_noc2axi_"]},
    "SMN":         {"path": [r"[/\\]smn[/\\]"],
                    "prefix": ["tt_smn_", "smn_"]},
    "Power":       {"path": [r"[/\\]power[/\\]", r"[/\\]prtn[/\\]"],
                    "prefix": ["tt_prtn_", "prtn_", "iso_en_"]},
    "Memory":      {"path": [r"[/\\]memory[/\\]", r"[/\\]sram[/\\]"],
                    "prefix": ["sfr_", "tt_mem_", "mem_"]},
}


def classify_topic(file_path: str, module_name: str) -> list[str]:
    """Classify an RTL module into topic categories.

    Matches *file_path* against path patterns and *module_name* against
    prefix patterns defined in ``TOPIC_RULES``.  Multiple topics may
    match; all are returned.  When nothing matches, ``["unclassified"]``
    is returned.

    Args:
        file_path: File path of the RTL source (forward or back slashes).
        module_name: RTL module name.

    Returns:
        Sorted list of matched topic strings, or ``["unclassified"]``.
    """
    if not isinstance(file_path, str):
        file_path = ""
    if not isinstance(module_name, str):
        module_name = ""

    matched: set[str] = set()

    for topic, rules in TOPIC_RULES.items():
        # Check path patterns
        for pattern in rules.get("path", []):
            if re.search(pattern, file_path, re.IGNORECASE):
                matched.add(topic)
                break

        # Check module name prefixes
        lower_name = module_name.lower()
        for prefix in rules.get("prefix", []):
            if lower_name.startswith(prefix.lower()):
                matched.add(topic)
                break

    if not matched:
        return ["unclassified"]

    return sorted(matched)


def suggest_inherited_topic(
    module_name: str,
    hierarchy_tree: dict[str, Any],
) -> list[str]:
    """Suggest topics inherited from the nearest classified ancestor.

    Walks the *hierarchy_tree* to find the closest ancestor of
    *module_name* that has a non-``unclassified`` topic, and returns
    that ancestor's topics.

    The hierarchy tree is expected to follow the structure produced by
    ``hierarchy.build_hierarchy``: each node has ``module_name``,
    ``children`` (list of child nodes), and optionally ``topics``.

    Args:
        module_name: Name of the module to find inherited topics for.
        hierarchy_tree: A single root node dict from the hierarchy tree.

    Returns:
        List of inherited topic strings, or ``["unclassified"]`` if no
        classified ancestor is found.
    """
    if not module_name or not isinstance(module_name, str):
        return ["unclassified"]
    if not hierarchy_tree or not isinstance(hierarchy_tree, dict):
        return ["unclassified"]

    # Build path from root to target module using DFS
    def _find_path(
        node: dict[str, Any], target: str, path: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        path.append(node)
        if node.get("module_name") == target:
            return list(path)
        for child in node.get("children", []):
            result = _find_path(child, target, path)
            if result is not None:
                return result
        path.pop()
        return None

    path = _find_path(hierarchy_tree, module_name, [])
    if not path:
        return ["unclassified"]

    # Walk ancestors from nearest to farthest (exclude the target itself)
    for ancestor in reversed(path[:-1]):
        topics = ancestor.get("topics", [])
        if topics and topics != ["unclassified"]:
            return list(topics)

    return ["unclassified"]
