"""
Package parameter extraction for RTL auto-analysis pipeline.

Extracts localparam, parameter, and typedef enum declarations from
SystemVerilog package files (*_pkg.sv). Identifies chip configuration
parameters (SizeX, SizeY, NumTensix, etc.) and builds tile-type
enum-to-module mappings.

Requirements validated: 12.1, 12.3
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_LOCALPARAM_RE = re.compile(
    r"localparam\s+(?:logic\s*(?:\[.*?\])?\s+)?(\w+)\s*=\s*([^;]+);",
    re.IGNORECASE,
)

_PARAMETER_RE = re.compile(
    r"parameter\s+(?:integer|real|string|logic\s*(?:\[.*?\])?)?\s*(\w+)\s*=\s*([^;,\)]+)",
    re.IGNORECASE,
)

_TYPEDEF_ENUM_RE = re.compile(
    r"typedef\s+enum\s*(?:logic\s*\[.*?\])?\s*\{([^}]+)\}\s*(\w+)\s*;",
    re.IGNORECASE | re.DOTALL,
)

# Chip configuration keywords (case-insensitive match)
_CHIP_CONFIG_KEYWORDS = [
    "sizex", "sizey", "numtensix", "numnoc2axi", "numdispatch",
    "numniu", "numedc", "numoverlay", "numfpu", "numsfpu",
    "gridwidth", "gridheight", "numrows", "numcols",
    "numendpoints", "numtiles",
]


def extract_package_params(rtl_content: str) -> dict[str, Any]:
    """Extract localparam, parameter, and typedef enum from *_pkg.sv content.

    Scans *rtl_content* for ``localparam``, ``parameter``, and
    ``typedef enum`` declarations and returns a structured dict.

    Args:
        rtl_content: Raw SystemVerilog package source text.

    Returns:
        A dict with keys:
            - ``localparams``: dict mapping name -> value (str)
            - ``parameters``: dict mapping name -> value (str)
            - ``enums``: dict mapping enum type name -> list of enum values
    """
    if not rtl_content or not isinstance(rtl_content, str):
        logger.warning("extract_package_params: empty or invalid input")
        return {"localparams": {}, "parameters": {}, "enums": {}}

    localparams: dict[str, str] = {}
    parameters: dict[str, str] = {}
    enums: dict[str, list[str]] = {}

    # Extract localparams
    for match in _LOCALPARAM_RE.finditer(rtl_content):
        name = match.group(1)
        value = match.group(2).strip()
        localparams[name] = value

    # Extract parameters
    for match in _PARAMETER_RE.finditer(rtl_content):
        name = match.group(1)
        value = match.group(2).strip()
        parameters[name] = value

    # Extract typedef enums
    for match in _TYPEDEF_ENUM_RE.finditer(rtl_content):
        body = match.group(1)
        enum_name = match.group(2)
        values = _parse_enum_body(body)
        enums[enum_name] = values

    logger.info(
        "Extracted %d localparams, %d parameters, %d enums",
        len(localparams), len(parameters), len(enums),
    )
    return {"localparams": localparams, "parameters": parameters, "enums": enums}


def _parse_enum_body(body: str) -> list[str]:
    """Parse enum body text into a list of enum value names."""
    values: list[str] = []
    for item in body.split(","):
        item = item.strip()
        if not item:
            continue
        # Remove assignment (e.g., "TENSIX = 0")
        name = item.split("=")[0].strip()
        # Remove inline comments
        name = re.sub(r"//.*", "", name).strip()
        name = re.sub(r"/\*.*?\*/", "", name).strip()
        if name and re.match(r"^\w+$", name):
            values.append(name)
    return values


def identify_chip_config(params: dict[str, Any]) -> dict[str, Any]:
    """Identify chip configuration parameters from extracted params.

    Searches localparams and parameters for known chip configuration
    keywords (SizeX, SizeY, NumTensix, etc.) and returns a filtered dict.

    Args:
        params: Output of ``extract_package_params()``.

    Returns:
        A dict with keys:
            - ``chip_params``: dict mapping param name -> {value, type}
            - ``grid_size``: dict with x/y if found
    """
    if not params or not isinstance(params, dict):
        logger.warning("identify_chip_config: empty or invalid input")
        return {"chip_params": {}, "grid_size": {}}

    chip_params: dict[str, dict[str, str]] = {}
    grid_size: dict[str, str] = {}

    all_params: list[tuple[str, str, str]] = []
    for name, value in params.get("localparams", {}).items():
        all_params.append((name, value, "localparam"))
    for name, value in params.get("parameters", {}).items():
        all_params.append((name, value, "parameter"))

    for name, value, param_type in all_params:
        lower_name = name.lower()
        for keyword in _CHIP_CONFIG_KEYWORDS:
            if keyword in lower_name:
                chip_params[name] = {"value": value, "type": param_type}
                break

        # Identify grid size
        if lower_name in ("sizex", "gridwidth", "numcols"):
            grid_size["x"] = value
        elif lower_name in ("sizey", "gridheight", "numrows"):
            grid_size["y"] = value

    logger.info("Identified %d chip config params", len(chip_params))
    return {"chip_params": chip_params, "grid_size": grid_size}


def extract_enum_mapping(rtl_content: str) -> dict[str, Any]:
    """Extract tile type -> value mapping from typedef enum declarations.

    Parses typedef enum declarations and builds a mapping of enum value
    names to their assigned integer values (if present).

    Args:
        rtl_content: Raw SystemVerilog package source text.

    Returns:
        A dict mapping enum type name -> dict of {value_name: assigned_value}.
        If no explicit assignment, the value is the positional index.
    """
    if not rtl_content or not isinstance(rtl_content, str):
        logger.warning("extract_enum_mapping: empty or invalid input")
        return {}

    result: dict[str, dict[str, Any]] = {}

    for match in _TYPEDEF_ENUM_RE.finditer(rtl_content):
        body = match.group(1)
        enum_name = match.group(2)
        mapping: dict[str, Any] = {}
        index = 0

        for item in body.split(","):
            item = item.strip()
            if not item:
                continue
            # Remove inline comments
            item = re.sub(r"//.*", "", item).strip()
            item = re.sub(r"/\*.*?\*/", "", item).strip()
            if not item:
                continue

            if "=" in item:
                parts = item.split("=", 1)
                name = parts[0].strip()
                val = parts[1].strip()
                if name and re.match(r"^\w+$", name):
                    mapping[name] = val
                    # Try to parse as int for next index
                    try:
                        index = int(val, 0) + 1
                    except (ValueError, TypeError):
                        index += 1
            else:
                name = item.strip()
                if name and re.match(r"^\w+$", name):
                    mapping[name] = index
                    index += 1

        if mapping:
            result[enum_name] = mapping

    logger.info("Extracted enum mappings for %d types", len(result))
    return result
