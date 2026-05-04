"""Package-level parser for SystemVerilog package files.

Extracts localparam, typedef enum, and typedef struct definitions
from *_pkg.sv files and converts them to structured claims for
RAG indexing.

v6 addition — addresses the gap where module_parse only captures
module declarations but misses package constants like SizeX, SizeY,
tile_t enum, etc.
"""

import re
import hashlib
import logging

logger = logging.getLogger(__name__)


def is_package_file(file_path: str) -> bool:
    """Check if a file is a SystemVerilog package file."""
    return file_path.endswith("_pkg.sv") or file_path.endswith("_pkg.v")


def extract_package_constants(rtl_content: str, file_path: str = "",
                               pipeline_id: str = "") -> list:
    """Extract localparam, typedef enum, and typedef struct from package content.

    Returns a list of claim-format dicts ready for OpenSearch indexing.
    """
    content = re.sub(r"//[^\n]*", "", rtl_content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

    claims = []
    pkg_match = re.search(r"\bpackage\s+(\w+)\s*;", content)
    pkg_name = pkg_match.group(1) if pkg_match else ""

    claims.extend(_extract_localparams(content, pkg_name, file_path, pipeline_id))
    claims.extend(_extract_enums(content, pkg_name, file_path, pipeline_id))
    claims.extend(_extract_structs(content, pkg_name, file_path, pipeline_id))
    claims.extend(_extract_parameters(content, pkg_name, file_path, pipeline_id))

    return claims


def _extract_localparams(content, pkg_name, file_path, pipeline_id):
    """Extract localparam declarations."""
    claims = []
    # Match: localparam [type] [packed_dim] NAME = VALUE;
    # Types: int, integer, logic, bit, string, shortint, longint, byte, or omitted
    pattern = re.compile(
        r"\blocalparam\s+(?:int\b|integer\b|logic\b|bit\b|string\b|shortint\b|longint\b|byte\b)?\s*"
        r"(?:unsigned\s+)?"
        r"(?:\[[^\]]*\]\s*)?"
        r"(\w+)\s*=\s*([^;]+);",
        re.MULTILINE
    )
    params = {}
    for m in pattern.finditer(content):
        params[m.group(1)] = m.group(2).strip()

    if params:
        param_lines = [f"{k} = {v}" for k, v in params.items()]
        claim_text = (
            f"Package '{pkg_name}' defines {len(params)} localparam constants: "
            + ", ".join(param_lines[:30])
        )
        if len(params) > 30:
            claim_text += f" ... and {len(params) - 30} more"
        claims.append(_make_claim(claim_text, "structural", pkg_name,
                                   "PackageConfig", file_path, pipeline_id))

        # Create individual claims for ALL localparams (not just pure numeric)
        for name, value in params.items():
            claims.append(_make_claim(
                f"Package '{pkg_name}' defines localparam {name} = {value}",
                "structural", pkg_name, "PackageConfig", file_path, pipeline_id,
            ))
    return claims


def _extract_enums(content, pkg_name, file_path, pipeline_id):
    """Extract typedef enum declarations."""
    claims = []
    pattern = re.compile(
        r"typedef\s+enum\s+(?:logic|bit|int)?\s*(?:\[[^\]]*\]\s*)?"
        r"\{([^}]+)\}\s*(\w+)\s*;",
        re.DOTALL
    )
    for m in pattern.finditer(content):
        body = m.group(1)
        enum_name = m.group(2)
        members = []
        for line in body.split(","):
            line = line.strip()
            if not line:
                continue
            member_match = re.match(r"(\w+)\s*(?:=\s*([^,\s]+))?", line)
            if member_match:
                mname = member_match.group(1)
                mval = member_match.group(2)
                members.append(f"{mname}={mval}" if mval else mname)

        if members:
            claims.append(_make_claim(
                f"Package '{pkg_name}' defines typedef enum '{enum_name}' "
                f"with {len(members)} members: {', '.join(members)}",
                "structural", pkg_name, "PackageConfig", file_path, pipeline_id,
            ))
    return claims


def _extract_structs(content, pkg_name, file_path, pipeline_id):
    """Extract typedef struct declarations."""
    claims = []
    pattern = re.compile(
        r"typedef\s+struct\s+(?:packed\s*)?\{([^}]+)\}\s*(\w+)\s*;",
        re.DOTALL
    )
    for m in pattern.finditer(content):
        body = m.group(1)
        struct_name = m.group(2)
        fields = []
        field_pattern = re.compile(
            r"(?:logic|bit|int|integer|wire|reg)\s*(?:\[[^\]]*\]\s*)?(\w+)\s*;",
        )
        for fm in field_pattern.finditer(body):
            fields.append(fm.group(1))

        if fields:
            claims.append(_make_claim(
                f"Package '{pkg_name}' defines typedef struct '{struct_name}' "
                f"with {len(fields)} fields: {', '.join(fields)}",
                "structural", pkg_name, "PackageConfig", file_path, pipeline_id,
            ))
    return claims


def _extract_parameters(content, pkg_name, file_path, pipeline_id):
    """Extract top-level parameter declarations in package."""
    claims = []
    pattern = re.compile(
        r"\bparameter\s+(?:int|integer|logic|bit|string)?\s*"
        r"(?:\[[^\]]*\]\s*)?"
        r"(\w+)\s*=\s*([^;]+);",
        re.MULTILINE
    )
    for m in pattern.finditer(content):
        claims.append(_make_claim(
            f"Package '{pkg_name}' defines parameter {m.group(1)} = {m.group(2).strip()}",
            "structural", pkg_name, "PackageConfig", file_path, pipeline_id,
        ))
    return claims


def _make_claim(claim_text, claim_type, module_name, topic,
                file_path, pipeline_id):
    """Create a claim dict in the standard format for OpenSearch indexing."""
    claim_id = hashlib.sha256(
        f"{pipeline_id}:{file_path}:{claim_text[:100]}".encode()
    ).hexdigest()[:16]
    return {
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
