"""
SRAM Inventory Extractor for RTL auto-analysis pipeline.

Identifies memory instances (SRAM, register file, ROM) from the hierarchy
tree and builds an inventory with type classification and parameter extraction.

Requirements validated: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6
"""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_PATTERNS = ["sram", "ram", "rf_", "reg_file", "rom", "memory", "mem_"]

# Pattern to extract depth x width from instance/module names like u_sram_256x64
_DIM_PATTERN = re.compile(r"(\d+)\s*x\s*(\d+)", re.IGNORECASE)


def is_memory_instance(instance_name: str, module_name: str) -> bool:
    """Check if an instance is a memory based on name patterns."""
    combined = f"{instance_name}_{module_name}".lower()
    return any(pat in combined for pat in MEMORY_PATTERNS)


def classify_memory_type(instance_name: str, module_name: str) -> str:
    """Classify memory type as SRAM, RF, or ROM."""
    combined = f"{instance_name}_{module_name}".lower()
    if "rom" in combined:
        return "ROM"
    if "rf_" in combined or "reg_file" in combined:
        return "RF"
    return "SRAM"


def extract_memory_params(instance_name: str) -> dict[str, str]:
    """Extract depth and width from instance name pattern {depth}x{width}."""
    m = _DIM_PATTERN.search(instance_name)
    if m:
        return {"depth": m.group(1), "width": m.group(2), "ecc": "unknown"}
    return {"depth": "unknown", "width": "unknown", "ecc": "unknown"}


def _classify_subsystem(hierarchy_path: str, topic: str) -> str:
    """Classify which subsystem a memory belongs to based on hierarchy path."""
    path_lower = hierarchy_path.lower()
    if "tensix" in path_lower or "fpu" in path_lower or "sfpu" in path_lower:
        return "Tensix"
    if "overlay" in path_lower:
        return "Overlay"
    if "noc" in path_lower or "niu" in path_lower:
        return "NoC"
    if "edc" in path_lower:
        return "EDC"
    if "dispatch" in path_lower:
        return "Dispatch"
    if topic and topic != "unclassified":
        return topic
    return "Other"


def build_sram_inventory(
    hierarchy_docs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build SRAM inventory from hierarchy documents.

    Scans hierarchy nodes for memory instances and builds a summary.

    Args:
        hierarchy_docs: List of hierarchy documents from OpenSearch.

    Returns:
        Dict with ``memory_instances`` list and ``summary`` dict.
    """
    memory_instances: list[dict[str, Any]] = []

    for doc in hierarchy_docs:
        module_name = doc.get("module_name", "")
        hierarchy_path = doc.get("hierarchy_path", "")
        topic = ""
        topics = doc.get("topics", doc.get("topic", []))
        if isinstance(topics, list) and topics:
            topic = topics[0]
        elif isinstance(topics, str):
            topic = topics

        # Check memory_instances field (already tagged by hierarchy extractor)
        mem_list = doc.get("memory_instances", [])
        if isinstance(mem_list, str):
            mem_list = mem_list.split() if mem_list.strip() else []

        for mem_inst in mem_list:
            if not mem_inst:
                continue
            mem_type = classify_memory_type(mem_inst, "")
            params = extract_memory_params(mem_inst)
            memory_instances.append({
                "instance_name": mem_inst,
                "memory_type": mem_type,
                "parent_module": module_name,
                "hierarchy_path": f"{hierarchy_path}.{mem_inst}" if hierarchy_path else mem_inst,
                "parameters": params,
            })

        # Also scan instance_list for memory patterns
        inst_list = doc.get("instance_list", "")
        if isinstance(inst_list, str):
            entries = inst_list.split() if inst_list.strip() else []
        else:
            entries = inst_list if isinstance(inst_list, list) else []

        for entry in entries:
            # entry format: "instance_name: module_type" or just "instance_name"
            if ": " in entry:
                inst_name, mod_type = entry.split(": ", 1)
            else:
                inst_name, mod_type = entry, ""

            if is_memory_instance(inst_name.strip(), mod_type.strip()):
                mem_type = classify_memory_type(inst_name.strip(), mod_type.strip())
                params = extract_memory_params(inst_name.strip())
                memory_instances.append({
                    "instance_name": inst_name.strip(),
                    "memory_type": mem_type,
                    "parent_module": module_name,
                    "hierarchy_path": f"{hierarchy_path}.{inst_name.strip()}" if hierarchy_path else inst_name.strip(),
                    "parameters": params,
                })

    # Deduplicate by (instance_name, parent_module)
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for m in memory_instances:
        key = (m["instance_name"], m["parent_module"])
        if key not in seen:
            seen.add(key)
            unique.append(m)
    memory_instances = unique

    # Build summary
    by_type: dict[str, int] = {}
    by_subsystem: dict[str, int] = {}
    for m in memory_instances:
        mt = m["memory_type"]
        by_type[mt] = by_type.get(mt, 0) + 1
        ss = _classify_subsystem(m["hierarchy_path"], "")
        by_subsystem[ss] = by_subsystem.get(ss, 0) + 1

    return {
        "memory_instances": memory_instances,
        "summary": {
            "total_count": len(memory_instances),
            "by_type": by_type,
            "by_subsystem": by_subsystem,
        },
    }
