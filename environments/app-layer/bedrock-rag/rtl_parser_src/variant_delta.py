"""
Variant delta extraction for RTL auto-analysis pipeline.

Compares baseline and variant module sets to identify added/removed
modules, parameter value changes, and instance additions/removals.

Requirements validated: 9.2
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_variant_delta(
    baseline_modules: list[dict[str, Any]],
    variant_modules: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract differences between baseline and variant module sets.

    Compares two lists of module dicts (keyed by ``module_name``) and
    identifies:
        - Modules added in the variant but absent from the baseline.
        - Modules removed from the variant (present in baseline only).
        - Parameter value changes for modules present in both sets.
        - Instance list additions/removals for modules present in both.

    Args:
        baseline_modules: List of module dicts from the baseline build.
        variant_modules: List of module dicts from the variant build.

    Returns:
        Dict with keys ``added_modules``, ``removed_modules``,
        ``parameter_changes``, ``instance_changes``.
    """
    if not isinstance(baseline_modules, list):
        baseline_modules = []
    if not isinstance(variant_modules, list):
        variant_modules = []

    # Index by module_name
    baseline_map: dict[str, dict[str, Any]] = {}
    for mod in baseline_modules:
        if isinstance(mod, dict):
            name = mod.get("module_name", "")
            if name:
                baseline_map[name] = mod

    variant_map: dict[str, dict[str, Any]] = {}
    for mod in variant_modules:
        if isinstance(mod, dict):
            name = mod.get("module_name", "")
            if name:
                variant_map[name] = mod

    baseline_names = set(baseline_map.keys())
    variant_names = set(variant_map.keys())

    # Added / removed modules
    added = sorted(variant_names - baseline_names)
    removed = sorted(baseline_names - variant_names)

    # Parameter and instance changes for common modules
    parameter_changes: list[dict[str, Any]] = []
    instance_changes: list[dict[str, Any]] = []

    common = sorted(baseline_names & variant_names)
    for name in common:
        base_mod = baseline_map[name]
        var_mod = variant_map[name]

        # Compare parameter_list
        base_params = base_mod.get("parameter_list", "")
        var_params = var_mod.get("parameter_list", "")
        if base_params != var_params:
            parameter_changes.append({
                "module_name": name,
                "baseline_parameters": base_params,
                "variant_parameters": var_params,
            })

        # Compare instance_list
        base_instances = base_mod.get("instance_list", "")
        var_instances = var_mod.get("instance_list", "")
        if base_instances != var_instances:
            base_set = _parse_instance_names(base_instances)
            var_set = _parse_instance_names(var_instances)
            added_inst = sorted(var_set - base_set)
            removed_inst = sorted(base_set - var_set)
            if added_inst or removed_inst:
                instance_changes.append({
                    "module_name": name,
                    "added_instances": added_inst,
                    "removed_instances": removed_inst,
                })

    return {
        "added_modules": added,
        "removed_modules": removed,
        "parameter_changes": parameter_changes,
        "instance_changes": instance_changes,
    }


def _parse_instance_names(instance_list_str: str) -> set[str]:
    """Parse comma-separated instance list into a set of instance names."""
    if not instance_list_str or not isinstance(instance_list_str, str):
        return set()
    names: set[str] = set()
    for entry in instance_list_str.split(","):
        entry = entry.strip()
        if not entry:
            continue
        # Format: "inst_name: module_type" or just "inst_name"
        inst_name = entry.split(":")[0].strip()
        if inst_name:
            names.add(inst_name)
    return names
