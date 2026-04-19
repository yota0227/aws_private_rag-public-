"""
NoC protocol analysis for RTL auto-analysis pipeline.

Extracts routing algorithms, flit header structures, AXI address
gasket definitions, and security fence mechanisms from NoC-related
RTL package and module files.

Requirements validated: 14.1, 14.2, 14.3, 14.4
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for NoC analysis
# ---------------------------------------------------------------------------

# Routing algorithm enum extraction (route in type name)
_ROUTING_ENUM_RE = re.compile(
    r"typedef\s+enum\s*(?:logic\s*\[.*?\])?\s*\{([^}]+)\}\s*(\w*route\w*)\s*;",
    re.IGNORECASE | re.DOTALL,
)

# Generic typedef enum (fallback)
_TYPEDEF_ENUM_RE = re.compile(
    r"typedef\s+enum\s*(?:logic\s*\[.*?\])?\s*\{([^}]+)\}\s*(\w+)\s*;",
    re.IGNORECASE | re.DOTALL,
)

# Struct definition extraction
_STRUCT_RE = re.compile(
    r"typedef\s+struct\s+packed\s*\{([^}]+)\}\s*(\w+)\s*;",
    re.IGNORECASE | re.DOTALL,
)

# Struct field extraction (logic [N:M] field_name;)
_STRUCT_FIELD_RE = re.compile(
    r"(?:logic|bit|reg|wire)\s*(\[.*?\])?\s*(\w+)\s*;",
    re.IGNORECASE,
)

# Security fence module pattern
_SEC_FENCE_RE = re.compile(
    r"(tt_noc_sec_fence\w*)",
    re.IGNORECASE,
)

# AXI address gasket fields
_AXI_GASKET_KEYWORDS = [
    "target_index", "endpoint_id", "tlb_index", "address",
]


def extract_routing_algorithms(pkg_content: str) -> list[dict[str, Any]]:
    """Extract routing algorithm enums from tt_noc_pkg.sv.

    Searches for typedef enum declarations with 'route' in the type name
    and extracts individual routing algorithm entries with their values.

    Args:
        pkg_content: Raw content of tt_noc_pkg.sv.

    Returns:
        List of dicts with ``name``, ``enum_value``, and ``parameters`` keys.
    """
    if not pkg_content or not isinstance(pkg_content, str):
        logger.warning("extract_routing_algorithms: empty or invalid input")
        return []

    algorithms: list[dict[str, Any]] = []

    # Try specific routing enum pattern first
    for match in _ROUTING_ENUM_RE.finditer(pkg_content):
        body = match.group(1)
        _parse_routing_enum_body(body, algorithms)

    # If no route-specific enum found, look for known routing keywords
    if not algorithms:
        known_routes = ["DIM_ORDER", "TENDRIL", "DYNAMIC", "XY_ROUTING", "YX_ROUTING"]
        for match in _TYPEDEF_ENUM_RE.finditer(pkg_content):
            body = match.group(1)
            for item in body.split(","):
                item = item.strip()
                name = re.sub(r"//.*", "", item).strip()
                name = re.sub(r"/\*.*?\*/", "", name).strip()
                if "=" in name:
                    name = name.split("=")[0].strip()
                if name in known_routes:
                    _parse_routing_enum_body(body, algorithms)
                    break
            if algorithms:
                break

    logger.info("Extracted %d routing algorithms", len(algorithms))
    return algorithms


def _parse_routing_enum_body(
    body: str, algorithms: list[dict[str, Any]],
) -> None:
    """Parse enum body and append routing algorithm entries."""
    index = 0
    for item in body.split(","):
        item = item.strip()
        if not item:
            continue
        item = re.sub(r"//.*", "", item).strip()
        item = re.sub(r"/\*.*?\*/", "", item).strip()
        if not item:
            continue

        if "=" in item:
            parts = item.split("=", 1)
            name = parts[0].strip()
            val_str = parts[1].strip()
            try:
                val = int(val_str, 0)
            except (ValueError, TypeError):
                val = index
            index = val + 1
        else:
            name = item.strip()
            val = index
            index += 1

        if name and re.match(r"^\w+$", name):
            algorithms.append({
                "name": name,
                "enum_value": val,
                "parameters": {},
            })


def extract_flit_structure(pkg_content: str) -> dict[str, Any]:
    """Extract flit header fields from noc_header_address_t struct.

    Searches for a struct named ``noc_header_address_t`` (or similar)
    and extracts its field names and bit widths.

    Args:
        pkg_content: Raw content of tt_noc_pkg.sv.

    Returns:
        A dict with:
            - ``header_fields``: list of field name strings
            - ``field_details``: list of {name, bit_width} dicts
            - ``total_bits``: estimated total bit width
    """
    if not pkg_content or not isinstance(pkg_content, str):
        logger.warning("extract_flit_structure: empty or invalid input")
        return {"header_fields": [], "field_details": [], "total_bits": 0}

    fields: list[dict[str, Any]] = []

    # Look for noc_header or flit_header struct
    for struct_match in _STRUCT_RE.finditer(pkg_content):
        struct_name = struct_match.group(2)
        if any(t in struct_name.lower() for t in ["noc_header", "flit_header"]):
            body = struct_match.group(1)
            fields = _parse_struct_fields(body)
            break

    # Fallback: search for any struct with known flit field names
    if not fields:
        flit_keywords = {"x_dest", "y_dest", "endpoint_id", "flit_type"}
        for struct_match in _STRUCT_RE.finditer(pkg_content):
            body = struct_match.group(1)
            if any(kw in body for kw in flit_keywords):
                fields = _parse_struct_fields(body)
                break

    header_fields = [f["name"] for f in fields]
    total_bits = sum(f.get("bit_width", 1) for f in fields)

    logger.info("Extracted flit structure: %d fields, %d bits", len(fields), total_bits)
    return {
        "header_fields": header_fields,
        "field_details": fields,
        "total_bits": total_bits,
    }


def extract_struct_fields(rtl_content: str, struct_name: str) -> list[dict[str, Any]]:
    """Extract fields from a named struct definition.

    Generic struct field extractor that finds the specified struct and
    returns all its fields with name and bit width.

    Args:
        rtl_content: Raw RTL source text.
        struct_name: Name of the struct to find.

    Returns:
        List of dicts with ``name`` and ``bit_width`` keys.
    """
    if not rtl_content or not isinstance(rtl_content, str):
        logger.warning("extract_struct_fields: empty or invalid rtl_content")
        return []
    if not struct_name or not isinstance(struct_name, str):
        logger.warning("extract_struct_fields: empty or invalid struct_name")
        return []

    for struct_match in _STRUCT_RE.finditer(rtl_content):
        found_name = struct_match.group(2)
        if found_name == struct_name:
            body = struct_match.group(1)
            fields = _parse_struct_fields(body)
            logger.info(
                "Extracted %d fields from struct '%s'",
                len(fields), struct_name,
            )
            return fields

    logger.warning("Struct '%s' not found in content", struct_name)
    return []


def _parse_struct_fields(body: str) -> list[dict[str, Any]]:
    """Parse struct body into field list with bit widths."""
    fields: list[dict[str, Any]] = []
    for match in _STRUCT_FIELD_RE.finditer(body):
        bit_range = match.group(1)
        name = match.group(2)
        bit_width = _calc_bit_width(bit_range)
        fields.append({"name": name, "bit_width": bit_width})
    return fields


def _calc_bit_width(bit_range: str | None) -> int:
    """Calculate bit width from [MSB:LSB] range string."""
    if not bit_range:
        return 1
    # Match [N:M] pattern
    m = re.match(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", bit_range)
    if m:
        msb = int(m.group(1))
        lsb = int(m.group(2))
        return abs(msb - lsb) + 1
    # Match [N] pattern
    m = re.match(r"\[\s*(\d+)\s*\]", bit_range)
    if m:
        return int(m.group(1)) + 1
    return 1


def extract_axi_address_gasket(pkg_content: str) -> dict[str, Any]:
    """Extract AXI address gasket structure from package content.

    Looks for address gasket struct or parameter definitions containing
    target_index, endpoint_id, tlb_index, address fields.

    Args:
        pkg_content: Raw content of tt_noc_pkg.sv.

    Returns:
        A dict with:
            - ``total_bits``: total address width
            - ``fields``: list of field names found
            - ``field_details``: list of {name, bit_width} dicts
    """
    if not pkg_content or not isinstance(pkg_content, str):
        logger.warning("extract_axi_address_gasket: empty or invalid input")
        return {"total_bits": 0, "fields": [], "field_details": []}

    # Search for AXI address struct
    for struct_match in _STRUCT_RE.finditer(pkg_content):
        struct_name = struct_match.group(2)
        if "axi" in struct_name.lower() or "address" in struct_name.lower():
            body = struct_match.group(1)
            fields = _parse_struct_fields(body)
            if fields:
                total_bits = sum(f.get("bit_width", 1) for f in fields)
                logger.info("Extracted AXI gasket: %d fields, %d bits", len(fields), total_bits)
                return {
                    "total_bits": total_bits,
                    "fields": [f["name"] for f in fields],
                    "field_details": fields,
                }

    # Fallback: search for known AXI gasket keywords as parameters
    found_fields: list[dict[str, Any]] = []
    for keyword in _AXI_GASKET_KEYWORDS:
        pattern = re.compile(
            r"(?:localparam|parameter)\s+\w*\s*" + keyword + r"\w*\s*=\s*(\d+)",
            re.IGNORECASE,
        )
        match = pattern.search(pkg_content)
        if match:
            found_fields.append({"name": keyword, "bit_width": int(match.group(1))})

    if found_fields:
        total_bits = sum(f["bit_width"] for f in found_fields)
        logger.info("Extracted AXI gasket (fallback): %d fields", len(found_fields))
        return {
            "total_bits": total_bits,
            "fields": [f["name"] for f in found_fields],
            "field_details": found_fields,
        }

    logger.warning("No AXI address gasket structure found")
    return {"total_bits": 0, "fields": [], "field_details": []}


def identify_security_fence(modules: list[dict[str, Any]]) -> dict[str, Any]:
    """Identify security fence mechanism from module list.

    Searches for ``tt_noc_sec_fence_*`` modules and identifies the
    access control mechanism (SMN group-based).

    Args:
        modules: List of module dicts with ``module_name`` key.

    Returns:
        A dict with:
            - ``module``: security fence module name (or empty)
            - ``mechanism``: identified mechanism type
            - ``found``: bool indicating if fence was found
    """
    if not modules or not isinstance(modules, list):
        logger.warning("identify_security_fence: empty or invalid input")
        return {"module": "", "mechanism": "", "found": False}

    for mod in modules:
        if not isinstance(mod, dict):
            continue
        module_name = mod.get("module_name", "")
        if _SEC_FENCE_RE.match(module_name):
            mechanism = "smn_group_access_control"
            instance_list = mod.get("instance_list", "")
            if "smn" in instance_list.lower():
                mechanism = "smn_group_access_control"
            elif "firewall" in instance_list.lower():
                mechanism = "firewall_access_control"

            logger.info("Found security fence: %s (%s)", module_name, mechanism)
            return {
                "module": module_name,
                "mechanism": mechanism,
                "found": True,
            }

    logger.info("No security fence module found")
    return {"module": "", "mechanism": "", "found": False}
