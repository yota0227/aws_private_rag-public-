"""
HDD (Hardware Design Document) section generator for RTL auto-analysis pipeline.

Calls Bedrock Claude 3 Haiku to auto-generate HDD document sections
from RTL analysis results. Supports three HDD types: chip-level,
subsystem-level, and block-level.

Requirements validated: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 10.6
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

logger = logging.getLogger(__name__)

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
CLAUDE_MODEL_ID = os.environ.get(
    "CLAUDE_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0",
)
TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"

_INVOKE_TIMEOUT = 60
_MAX_RETRIES = 1

# Required HDD sections for completeness validation
HDD_REQUIRED_SECTIONS = [
    "Overview",
    "Module Hierarchy",
    "Functional Details",
    "Clock/Reset Structure",
    "Key Parameters",
    "Verification Checklist",
]


def _determine_hdd_type(topic: str, hierarchy: dict[str, Any]) -> str:
    """Determine HDD type based on topic and hierarchy scope.

    Returns one of: ``chip``, ``subsystem``, ``block``.
    """
    if not topic or topic.lower() in ("all", "chip", "top"):
        return "chip"
    # If hierarchy has many top-level children, treat as subsystem
    children = hierarchy.get("children", []) if isinstance(hierarchy, dict) else []
    if len(children) > 3:
        return "subsystem"
    return "block"


def _build_hdd_prompt(
    pipeline_id: str,
    topic: str,
    hdd_type: str,
    hierarchy: dict[str, Any],
    clock_domains: list[dict[str, Any]],
    dataflow: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> str:
    """Build the LLM prompt for HDD section generation."""
    hierarchy_str = json.dumps(hierarchy, ensure_ascii=False, default=str)[:3000]
    clock_str = json.dumps(clock_domains, ensure_ascii=False, default=str)[:1500]
    dataflow_str = json.dumps(dataflow, ensure_ascii=False, default=str)[:1500]
    claims_str = json.dumps(claims, ensure_ascii=False, default=str)[:1500]

    section_guide = {
        "chip": (
            "Generate a chip-level HDD with these sections:\n"
            "1. Overview\n2. Module Hierarchy\n3. Block Diagram (ASCII art)\n"
            "4. Functional Details\n5. Clock/Reset Structure\n"
            "6. Key Parameters\n7. Verification Checklist"
        ),
        "subsystem": (
            "Generate a subsystem-level HDD with these sections:\n"
            "1. Overview\n2. Architecture\n3. Module Hierarchy\n"
            "4. Functional Details\n5. Clock/Reset Structure\n"
            "6. Key Parameters\n7. Verification Checklist"
        ),
        "block": (
            "Generate a block-level HDD with these sections:\n"
            "1. Overview\n2. Sub-module Hierarchy\n3. Functional Details\n"
            "4. Control Path\n5. Clock/Reset Structure\n"
            "6. Key Parameters\n7. Verification Checklist"
        ),
    }

    return (
        "You are a semiconductor design documentation expert. "
        "Generate a Hardware Design Document (HDD) section in Markdown format.\n\n"
        f"Pipeline ID: {pipeline_id}\n"
        f"Topic: {topic}\n"
        f"HDD Type: {hdd_type}\n\n"
        f"{section_guide.get(hdd_type, section_guide['block'])}\n\n"
        f"Hierarchy:\n{hierarchy_str}\n\n"
        f"Clock Domains:\n{clock_str}\n\n"
        f"Dataflow:\n{dataflow_str}\n\n"
        f"Claims:\n{claims_str}\n\n"
        "Output the HDD section in Markdown. Use ## for section headers. "
        "Include all required sections listed above."
    )


def _invoke_claude(prompt: str) -> str:
    """Invoke Bedrock Claude 3 Haiku and return the text response."""
    bedrock_client = boto3.client(
        "bedrock-runtime",
        region_name=BEDROCK_REGION,
        config=boto3.session.Config(
            read_timeout=_INVOKE_TIMEOUT,
            connect_timeout=_INVOKE_TIMEOUT,
        ),
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    })

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = bedrock_client.invoke_model(
                modelId=CLAUDE_MODEL_ID,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            return result["content"][0]["text"]
        except Exception as e:
            last_error = e
            logger.warning(
                "Claude HDD invocation attempt %d failed: %s", attempt + 1, e,
            )

    raise RuntimeError(
        f"Claude HDD invocation failed after {_MAX_RETRIES + 1} attempts: {last_error}"
    )


def _generate_embedding(text: str) -> list[float] | None:
    """Generate Titan Embeddings v2 vector for HDD content."""
    try:
        bedrock_client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
        body = json.dumps({"inputText": text[:8000], "dimensions": 1024, "normalize": True})
        response = bedrock_client.invoke_model(
            modelId=TITAN_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result.get("embedding")
    except Exception as e:
        logger.error("Titan embedding generation for HDD failed: %s", e)
        return None


def _collect_source_files(
    hierarchy: dict[str, Any],
) -> list[str]:
    """Collect source RTL file paths from hierarchy tree nodes."""
    files: list[str] = []

    def _walk(node: dict[str, Any]) -> None:
        fp = node.get("file_path", "")
        if fp:
            files.append(fp)
        for child in node.get("children", []):
            if isinstance(child, dict):
                _walk(child)

    if isinstance(hierarchy, dict):
        _walk(hierarchy)
    return files


def generate_hdd_section(
    pipeline_id: str,
    topic: str,
    hierarchy: dict[str, Any],
    clock_domains: list[dict[str, Any]],
    dataflow: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate an HDD document section using Bedrock Claude.

    Supports three HDD types:
    - chip: Full chip HDD (all hierarchy + topic summaries)
    - subsystem: Subsystem HDD (specific topic module group)
    - block: Block HDD (single block module + sub-hierarchy)

    Args:
        pipeline_id: Pipeline identifier.
        topic: Topic category for the HDD section.
        hierarchy: Hierarchy tree dict from hierarchy extraction.
        clock_domains: Clock domain analysis results.
        dataflow: Dataflow tracking results.
        claims: Generated claims for this topic.

    Returns:
        Dict with ``hdd_content`` (Markdown), ``hdd_type``,
        ``hdd_metadata``, and ``topic``.
    """
    if not isinstance(hierarchy, dict):
        hierarchy = {}
    if not isinstance(clock_domains, list):
        clock_domains = []
    if not isinstance(dataflow, list):
        dataflow = []
    if not isinstance(claims, list):
        claims = []

    hdd_type = _determine_hdd_type(topic, hierarchy)
    prompt = _build_hdd_prompt(
        pipeline_id, topic, hdd_type, hierarchy, clock_domains, dataflow, claims,
    )

    hdd_content = _invoke_claude(prompt)

    source_files = _collect_source_files(hierarchy)

    metadata: dict[str, Any] = {
        "source_rtl_files": source_files,
        "generation_date": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "1.0",
        "pipeline_id": pipeline_id,
    }

    return {
        "pipeline_id": pipeline_id,
        "topic": topic,
        "hdd_type": hdd_type,
        "hdd_content": hdd_content,
        "hdd_section_title": f"{topic} HDD",
        "hdd_section_type": hdd_type,
        "hdd_metadata": metadata,
        "analysis_type": "hdd_section",
    }
