"""
Overlay deep analysis for RTL auto-analysis pipeline.

Analyzes Overlay (RISC-V subsystem) internal structure including
CPU cluster parameters, submodule roles, L1 cache configuration,
and APB slave register maps.

Requirements validated: 15.1, 15.2, 15.3, 15.4
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OVERLAY_SUBMODULE_ROLES: dict[str, str] = {
    "tt_overlay_cpu_wrapper": "cpu_cluster",
    "tt_idma_wrapper": "idma",
    "tt_rocc_accel": "rocc_accelerator",
    "tt_overlay_tile_counters": "llk_counter",
    "tt_overlay_smn_wrapper": "smn",
    "tt_fds_wrapper": "fds",
    "tt_overlay_edc_wrapper": "edc",
    "tt_overlay_memory_wrapper": "memory",
    "tt_overlay_noc_wrap": "noc_interface",
}

# CPU cluster parameter keywords
_CPU_PARAM_KEYWORDS = [
    "num_cluster_cpus", "num_interrupts", "reset_vector_width",
    "num_harts", "num_cores", "isa_extensions",
]

# L1 cache parameter keywords
_L1_CACHE_KEYWORDS = [
    "num_banks", "bank_width", "ecc_type", "sram_type",
    "cache_size", "line_size", "associativity",
    "num_ways", "num_sets",
]

# Regex for localparam/parameter extraction
_PARAM_RE = re.compile(
    r"(?:localparam|parameter)\s+(?:(?:integer|real|string|logic\s*(?:\[.*?\])?)\s+)?(\w+)\s*=\s*([^;,\)]+)",
    re.IGNORECASE,
)

# APB slave decode pattern (localparam with slave/slv in name)
_APB_ADDR_RE = re.compile(
    r"(?:localparam|parameter)\s+\w*\s*(\w*(?:slave|slv)\w*)\s*=\s*([^;]+);",
    re.IGNORECASE,
)


def extract_cpu_cluster_params(pkg_content: str) -> dict[str, Any]:
    """Extract CPU cluster parameters from tt_overlay_pkg.sv.

    Searches for parameters related to CPU cluster configuration
    (NUM_CLUSTER_CPUS, NUM_INTERRUPTS, RESET_VECTOR_WIDTH, etc.).

    Args:
        pkg_content: Raw content of tt_overlay_pkg.sv.

    Returns:
        A dict mapping parameter name -> value (str or int).
    """
    if not pkg_content or not isinstance(pkg_content, str):
        logger.warning("extract_cpu_cluster_params: empty or invalid input")
        return {}

    result: dict[str, Any] = {}

    for match in _PARAM_RE.finditer(pkg_content):
        name = match.group(1)
        value = match.group(2).strip()
        lower_name = name.lower()

        for keyword in _CPU_PARAM_KEYWORDS:
            if keyword in lower_name:
                # Try to parse as integer
                try:
                    result[name] = int(value, 0)
                except (ValueError, TypeError):
                    result[name] = value
                break

    logger.info("Extracted %d CPU cluster params", len(result))
    return result


def identify_submodule_roles(modules: list[dict[str, Any]]) -> dict[str, str]:
    """Identify Overlay submodule roles from module list.

    Matches module names against the known OVERLAY_SUBMODULE_ROLES
    mapping to assign functional roles.

    Args:
        modules: List of module dicts with ``module_name`` key.

    Returns:
        A dict mapping module_name -> role string.
    """
    if not modules or not isinstance(modules, list):
        logger.warning("identify_submodule_roles: empty or invalid input")
        return {}

    roles: dict[str, str] = {}

    for mod in modules:
        if not isinstance(mod, dict):
            continue
        module_name = mod.get("module_name", "")
        if not module_name:
            continue

        # Check exact match first
        if module_name in OVERLAY_SUBMODULE_ROLES:
            roles[module_name] = OVERLAY_SUBMODULE_ROLES[module_name]
            continue

        # Check prefix match (module_name may have suffix)
        for pattern, role in OVERLAY_SUBMODULE_ROLES.items():
            if module_name.startswith(pattern):
                roles[module_name] = role
                break

    logger.info("Identified %d submodule roles", len(roles))
    return roles


def extract_l1_cache_params(module_content: str) -> dict[str, Any]:
    """Extract L1 cache parameters from tt_overlay_memory_wrapper.

    Searches for parameters related to L1 cache configuration
    (num_banks, bank_width, ecc_type, sram_type, etc.).

    Args:
        module_content: Raw content of tt_overlay_memory_wrapper module.

    Returns:
        A dict mapping parameter name -> value.
    """
    if not module_content or not isinstance(module_content, str):
        logger.warning("extract_l1_cache_params: empty or invalid input")
        return {}

    result: dict[str, Any] = {}

    for match in _PARAM_RE.finditer(module_content):
        name = match.group(1)
        value = match.group(2).strip()
        lower_name = name.lower()

        for keyword in _L1_CACHE_KEYWORDS:
            if keyword in lower_name:
                # Try to parse as integer
                try:
                    result[name] = int(value, 0)
                except (ValueError, TypeError):
                    # Remove quotes for string values
                    result[name] = value.strip("\"'")
                break

    logger.info("Extracted %d L1 cache params", len(result))
    return result


def extract_apb_slaves(xbar_content: str) -> list[dict[str, Any]]:
    """Extract APB slave list from tt_overlay_reg_xbar_slave_decode.

    Parses the crossbar decode module to identify APB slave entries
    with their names and base addresses.

    Args:
        xbar_content: Raw content of tt_overlay_reg_xbar_slave_decode module.

    Returns:
        List of dicts with ``name``, ``base_address``, and ``size`` keys.
    """
    if not xbar_content or not isinstance(xbar_content, str):
        logger.warning("extract_apb_slaves: empty or invalid input")
        return []

    slaves: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    # Strategy 1: Look for localparam/parameter with slave/slv in name
    for match in _APB_ADDR_RE.finditer(xbar_content):
        name = match.group(1)
        value = match.group(2).strip()
        if name.lower() not in seen_names:
            seen_names.add(name.lower())
            slaves.append({
                "name": name,
                "base_address": value,
                "size": "0x1000",
            })

    # Strategy 2: Look for case/if patterns with address decoding
    case_pattern = re.compile(
        r"(\d+)\s*:\s*(?:begin)?[^;]*?(\w*addr\w*)\s*(?:<=|=)\s*([^;]+);",
        re.IGNORECASE,
    )
    for match in case_pattern.finditer(xbar_content):
        idx = match.group(1)
        addr_val = match.group(3).strip()
        name = f"slave_{idx}"
        if name.lower() not in seen_names:
            seen_names.add(name.lower())
            slaves.append({
                "name": name,
                "base_address": addr_val,
                "size": "0x1000",
            })

    # Strategy 3: Look for numbered slave parameters
    numbered_pattern = re.compile(
        r"(?:localparam|parameter)\s+\w*(?:SLAVE|SLV)_?(\d+)\w*\s*=\s*([^;]+);",
        re.IGNORECASE,
    )
    for match in numbered_pattern.finditer(xbar_content):
        idx = match.group(1)
        value = match.group(2).strip()
        name = f"slave_{idx}"
        if name.lower() not in seen_names:
            seen_names.add(name.lower())
            slaves.append({
                "name": name,
                "base_address": value,
                "size": "0x1000",
            })

    logger.info("Extracted %d APB slaves", len(slaves))
    return slaves
