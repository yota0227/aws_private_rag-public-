"""
HDD (Hardware Design Document) section generator for RTL auto-analysis pipeline.

Calls Bedrock Claude 3 Haiku to auto-generate HDD document sections
from RTL analysis results. Supports three HDD types: chip-level,
subsystem-level, and block-level.

Requirements validated: 2.1, 2.2, 2.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 10.6
"""

import json
import logging
import os
import re
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


# Default EP Table coordinate mapping for dispatch directions
EP_TABLE_DISPATCH_COORDS = {
    "east": 3,   # East dispatch → X=3
    "west": 0,   # West dispatch → X=0
}

# EP Table Y-axis coordinate mapping for overlay rows
EP_TABLE_Y_COORDS = {
    "noc2axi": 4,       # NOC2AXI row → Y=4
    "tensix_row0": 0,   # Tensix row 0 → Y=0
    "tensix_row1": 1,   # Tensix row 1 → Y=1
    "tensix_row2": 2,   # Tensix row 2 → Y=2
    "tensix_row3": 3,   # Tensix row 3 → Y=3
}

# Valid Y coordinate ranges
EP_TABLE_Y_VALID_RANGE = range(0, 5)  # Y=0..4
EP_TABLE_Y_NOC2AXI = 4
EP_TABLE_Y_TENSIX_RANGE = range(0, 4)  # Y=0..3

# Composite tile row_span: tiles that span Y=3 and Y=4
EP_TABLE_COMPOSITE_TILE_ROWS = {3, 4}  # Y=3 (Tensix top) + Y=4 (NOC2AXI)

# Pattern to detect [FROM LLM] inference blocks
_FROM_LLM_PATTERN = re.compile(r"\[FROM LLM\]", re.IGNORECASE)

# Pattern to detect coordinate references (e.g., X=3, X=0, x=2)
_COORD_PATTERN = re.compile(
    r"\b([Xx])\s*=\s*(\d+)\b"
)

# Pattern to detect Y coordinate references (e.g., Y=4, Y=0, y=3)
_Y_COORD_PATTERN = re.compile(
    r"\b([Yy])\s*=\s*(\d+)\b"
)

# Pattern to detect dispatch direction references
_DISPATCH_DIR_PATTERN = re.compile(
    r"\b(east|west)\s+(dispatch|direction)\b", re.IGNORECASE
)

# Pattern to detect overlay/NOC2AXI row references
_OVERLAY_ROW_PATTERN = re.compile(
    r"\b(noc2axi|overlay)\s+(row|layer)\b", re.IGNORECASE
)

# Pattern to detect Tensix row references
_TENSIX_ROW_PATTERN = re.compile(
    r"\b(tensix)\s+(row|layer)\b", re.IGNORECASE
)

# Pattern to detect composite tile / row_span references
_COMPOSITE_TILE_PATTERN = re.compile(
    r"\b(composite\s+tile|row_span|row\s+span)\b", re.IGNORECASE
)


def _validate_dispatch_coordinates(
    inference_text: str,
    ep_table: dict[str, int] | None = None,
) -> str:
    """Validate [FROM LLM] inferences against EP Table dispatch coordinates.

    Checks that East/West dispatch assignments in LLM-generated text are
    consistent with the EP Table coordinates (East=X=3, West=X=0).

    If a contradiction is found:
      1. Remove only the coordinate-related parts of the inference.
      2. If the remaining text is contextually incomplete (forms an
         incomplete sentence), discard the entire paragraph.
      3. Emit a warning log with event=dispatch_coord_conflict.

    Args:
        inference_text: Text containing [FROM LLM] inferences to validate.
        ep_table: Optional EP Table coordinate mapping. Defaults to
            EP_TABLE_DISPATCH_COORDS (East=X=3, West=X=0).

    Returns:
        Validated text with contradictions removed or paragraphs discarded.

    Requirements validated: 2.1, 2.2
    """
    if not inference_text:
        return inference_text

    if ep_table is None:
        ep_table = EP_TABLE_DISPATCH_COORDS

    paragraphs = inference_text.split("\n\n")
    validated_paragraphs: list[str] = []

    for paragraph in paragraphs:
        # Only validate paragraphs containing [FROM LLM] inferences
        if not _FROM_LLM_PATTERN.search(paragraph):
            validated_paragraphs.append(paragraph)
            continue

        conflict_found = False
        conflicting_values: dict[str, Any] = {}

        # Check each sentence in the paragraph for coordinate contradictions
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        cleaned_sentences: list[str] = []

        for sentence in sentences:
            sentence_has_conflict = False

            # Find dispatch direction mentions
            dir_matches = _DISPATCH_DIR_PATTERN.finditer(sentence)
            for dir_match in dir_matches:
                direction = dir_match.group(1).lower()

                # Find coordinate assignments in the same sentence
                coord_matches = _COORD_PATTERN.finditer(sentence)
                for coord_match in coord_matches:
                    coord_value = int(coord_match.group(2))
                    expected_value = ep_table.get(direction)

                    if expected_value is not None and coord_value != expected_value:
                        sentence_has_conflict = True
                        conflict_found = True
                        conflicting_values[direction] = {
                            "found": coord_value,
                            "expected": expected_value,
                        }

            if sentence_has_conflict:
                # Remove coordinate-related parts from the sentence
                cleaned = _COORD_PATTERN.sub("", sentence).strip()
                # Remove dangling punctuation/connectors after removal
                cleaned = re.sub(r"\s{2,}", " ", cleaned)
                cleaned = re.sub(r"^\s*[,;]\s*", "", cleaned)
                cleaned = re.sub(r"\s*[,;]\s*$", "", cleaned)

                # Check if remaining text is contextually complete
                if _is_sentence_complete(cleaned):
                    cleaned_sentences.append(cleaned)
                else:
                    # Sentence is incomplete after removal — will discard paragraph
                    cleaned_sentences = []
                    break
            else:
                cleaned_sentences.append(sentence)

        if conflict_found:
            # Log the conflict warning
            logger.warning(json.dumps({
                "event": "dispatch_coord_conflict",
                "conflicting_values": conflicting_values,
                "original_paragraph": paragraph[:200],
            }))

            if cleaned_sentences:
                # Reconstruct paragraph from cleaned sentences
                validated_paragraphs.append(" ".join(cleaned_sentences))
            else:
                # Entire paragraph discarded — incomplete after removal
                logger.info(json.dumps({
                    "event": "dispatch_coord_paragraph_discarded",
                    "reason": "incomplete_after_coordinate_removal",
                }))
        else:
            validated_paragraphs.append(paragraph)

    return "\n\n".join(validated_paragraphs)


def _is_sentence_complete(text: str) -> bool:
    """Check if text forms a contextually complete sentence.

    A sentence is considered incomplete if:
    - It's empty or only whitespace
    - It's shorter than 5 characters (too short to be meaningful)
    - It ends with a dangling connector/preposition (and, or, but, at, etc.)
    - It ends with a preposition followed only by punctuation

    Returns:
        True if the sentence appears complete, False otherwise.
    """
    if not text or len(text.strip()) < 5:
        return False

    stripped = text.strip()

    # Remove trailing punctuation for content analysis
    content = re.sub(r"[.!?]+$", "", stripped).strip()

    if not content or len(content) < 5:
        return False

    # Check for dangling connectors/prepositions at the end of content
    dangling_end = re.compile(
        r"\b(and|or|but|with|to|for|from|at|in|is|are|was|were|the|a|an)\s*$",
        re.IGNORECASE,
    )
    if dangling_end.search(content):
        return False

    # Check for sentences that are just fragments (no verb-like structure)
    # Very short content is likely incomplete
    if len(content) < 10:
        return False

    return True


def _validate_y_coordinates_in_sentence(
    sentence: str,
    y_coords: dict[str, int] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Validate Y-axis coordinates in a sentence against EP Table.

    Checks:
    - NOC2AXI/overlay references must use Y=4
    - Tensix row references must use Y=0..3
    - Composite tile row_span must span Y=3 and Y=4

    Args:
        sentence: A single sentence to validate.
        y_coords: Optional Y coordinate mapping. Defaults to EP_TABLE_Y_COORDS.

    Returns:
        Tuple of (has_conflict, conflicting_values_dict).
    """
    if y_coords is None:
        y_coords = EP_TABLE_Y_COORDS

    conflicting_values: dict[str, Any] = {}
    has_conflict = False

    # Find Y coordinate assignments in the sentence
    y_matches = list(_Y_COORD_PATTERN.finditer(sentence))
    if not y_matches:
        return False, {}

    # Check overlay/NOC2AXI row references
    overlay_matches = list(_OVERLAY_ROW_PATTERN.finditer(sentence))
    for _ in overlay_matches:
        for y_match in y_matches:
            y_value = int(y_match.group(2))
            expected_y = EP_TABLE_Y_NOC2AXI  # Y=4
            if y_value != expected_y:
                has_conflict = True
                conflicting_values["noc2axi_y"] = {
                    "found": y_value,
                    "expected": expected_y,
                }

    # Check Tensix row references
    tensix_matches = list(_TENSIX_ROW_PATTERN.finditer(sentence))
    for _ in tensix_matches:
        for y_match in y_matches:
            y_value = int(y_match.group(2))
            if y_value not in EP_TABLE_Y_TENSIX_RANGE:
                has_conflict = True
                conflicting_values["tensix_y"] = {
                    "found": y_value,
                    "expected": "0..3",
                }

    # Check composite tile row_span references
    composite_matches = list(_COMPOSITE_TILE_PATTERN.finditer(sentence))
    for _ in composite_matches:
        # Composite tile must span Y=3 and Y=4
        found_y_values = {int(m.group(2)) for m in y_matches}
        if found_y_values and not found_y_values.issubset(EP_TABLE_COMPOSITE_TILE_ROWS):
            has_conflict = True
            conflicting_values["composite_tile_row_span"] = {
                "found": sorted(found_y_values),
                "expected": sorted(EP_TABLE_COMPOSITE_TILE_ROWS),
            }

    return has_conflict, conflicting_values


def _validate_coordinates(
    inference_text: str,
    ep_table: dict[str, int] | None = None,
    y_coords: dict[str, int] | None = None,
) -> str:
    """Validate [FROM LLM] inferences against EP Table coordinates (X and Y axes).

    Generalized version of _validate_dispatch_coordinates() that validates both:
    - X-axis: East dispatch=X=3, West dispatch=X=0
    - Y-axis: NOC2AXI row=Y=4, Tensix rows=Y=0..3
    - Composite tile: row_span spanning Y=3 and Y=4

    If a contradiction is found:
      1. Remove only the coordinate-related parts of the inference.
      2. If the remaining text is contextually incomplete (forms an
         incomplete sentence), discard the entire paragraph.
      3. Emit a warning log with event=coord_conflict.

    Args:
        inference_text: Text containing [FROM LLM] inferences to validate.
        ep_table: Optional EP Table X-axis coordinate mapping. Defaults to
            EP_TABLE_DISPATCH_COORDS (East=X=3, West=X=0).
        y_coords: Optional EP Table Y-axis coordinate mapping. Defaults to
            EP_TABLE_Y_COORDS.

    Returns:
        Validated text with contradictions removed or paragraphs discarded.

    Requirements validated: 2.1, 2.2
    """
    if not inference_text:
        return inference_text

    if ep_table is None:
        ep_table = EP_TABLE_DISPATCH_COORDS
    if y_coords is None:
        y_coords = EP_TABLE_Y_COORDS

    paragraphs = inference_text.split("\n\n")
    validated_paragraphs: list[str] = []

    for paragraph in paragraphs:
        # Only validate paragraphs containing [FROM LLM] inferences
        if not _FROM_LLM_PATTERN.search(paragraph):
            validated_paragraphs.append(paragraph)
            continue

        conflict_found = False
        conflicting_values: dict[str, Any] = {}

        # Check each sentence in the paragraph for coordinate contradictions
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        cleaned_sentences: list[str] = []

        for sentence in sentences:
            sentence_has_conflict = False

            # --- X-axis validation (dispatch E/W) ---
            dir_matches = list(_DISPATCH_DIR_PATTERN.finditer(sentence))
            for dir_match in dir_matches:
                direction = dir_match.group(1).lower()
                coord_matches = list(_COORD_PATTERN.finditer(sentence))
                for coord_match in coord_matches:
                    coord_value = int(coord_match.group(2))
                    expected_value = ep_table.get(direction)
                    if expected_value is not None and coord_value != expected_value:
                        sentence_has_conflict = True
                        conflict_found = True
                        conflicting_values[f"dispatch_{direction}_x"] = {
                            "found": coord_value,
                            "expected": expected_value,
                        }

            # --- Y-axis validation (overlay/tensix/composite) ---
            y_conflict, y_conflicts = _validate_y_coordinates_in_sentence(
                sentence, y_coords,
            )
            if y_conflict:
                sentence_has_conflict = True
                conflict_found = True
                conflicting_values.update(y_conflicts)

            if sentence_has_conflict:
                # Remove coordinate-related parts from the sentence (both X and Y)
                cleaned = _COORD_PATTERN.sub("", sentence)
                cleaned = _Y_COORD_PATTERN.sub("", cleaned).strip()
                # Remove dangling punctuation/connectors after removal
                cleaned = re.sub(r"\s{2,}", " ", cleaned)
                cleaned = re.sub(r"^\s*[,;]\s*", "", cleaned)
                cleaned = re.sub(r"\s*[,;]\s*$", "", cleaned)

                # Check if remaining text is contextually complete
                if _is_sentence_complete(cleaned):
                    cleaned_sentences.append(cleaned)
                else:
                    # Sentence is incomplete after removal — will discard paragraph
                    cleaned_sentences = []
                    break
            else:
                cleaned_sentences.append(sentence)

        if conflict_found:
            # Log the conflict warning
            logger.warning(json.dumps({
                "event": "coord_conflict",
                "conflicting_values": conflicting_values,
                "original_paragraph": paragraph[:200],
            }))

            if cleaned_sentences:
                # Reconstruct paragraph from cleaned sentences
                validated_paragraphs.append(" ".join(cleaned_sentences))
            else:
                # Entire paragraph discarded — incomplete after removal
                logger.info(json.dumps({
                    "event": "coord_paragraph_discarded",
                    "reason": "incomplete_after_coordinate_removal",
                }))
        else:
            validated_paragraphs.append(paragraph)

    return "\n\n".join(validated_paragraphs)


def _get_graph_evidence_provider():
    """Get or create a GraphEvidenceProvider instance.

    Returns None if the module cannot be imported (should not happen in
    normal operation since graph_evidence_provider.py is in the same package).
    """
    try:
        from graph_evidence_provider import GraphEvidenceProvider
        return GraphEvidenceProvider()
    except ImportError:
        logger.debug("graph_evidence_provider module not available")
        return None
    except Exception as e:
        logger.warning(f"Failed to initialize GraphEvidenceProvider: {e}")
        return None


def _build_hdd_prompt(
    pipeline_id: str,
    topic: str,
    hdd_type: str,
    hierarchy: dict[str, Any],
    clock_domains: list[dict[str, Any]],
    dataflow: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    deep_analysis: dict[str, Any] | None = None,
    graph_evidence_provider=None,
) -> str:
    """Build the LLM prompt for HDD section generation.

    Args:
        pipeline_id: Pipeline identifier.
        topic: Topic category for the HDD section.
        hdd_type: One of 'chip', 'subsystem', 'block'.
        hierarchy: Hierarchy tree dict.
        clock_domains: Clock domain analysis results.
        dataflow: Dataflow tracking results.
        claims: Generated claims for this topic.
        deep_analysis: Optional deep analysis results.
        graph_evidence_provider: Optional GraphEvidenceProvider instance.
            If None, attempts to create one automatically.
            Neptune 미접속 시 기존 claim-only 모드로 동작.
    """
    hierarchy_str = json.dumps(hierarchy, ensure_ascii=False, default=str)[:3000]
    clock_str = json.dumps(clock_domains, ensure_ascii=False, default=str)[:1500]
    dataflow_str = json.dumps(dataflow, ensure_ascii=False, default=str)[:1500]
    claims_str = json.dumps(claims, ensure_ascii=False, default=str)[:1500]

    section_guide = {
        "chip": (
            "Generate a chip-level HDD with these sections:\n"
            "1. Overview\n2. Package Constants and Grid\n3. Module Hierarchy\n"
            "4. Block Diagram (ASCII art)\n5. Functional Details\n"
            "6. Clock/Reset Structure\n7. Key Parameters\n"
            "8. SRAM Inventory\n9. Verification Checklist"
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

    prompt = (
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
    )

    # --- Graph Evidence injection (Requirements 13.2, 13.3) ---
    # Retrieve graph evidence from Neptune for the current topic.
    # When Neptune is unavailable, format_evidence_for_prompt returns ""
    # and the prompt falls back to claim-only mode.
    module_name = ""
    if isinstance(hierarchy, dict):
        module_name = hierarchy.get("module_name", "")

    evidence_text = ""
    provider = graph_evidence_provider
    if provider is None:
        provider = _get_graph_evidence_provider()

    if provider is not None and topic:
        try:
            evidence_text = provider.format_evidence_for_prompt(topic, module_name)
        except Exception as e:
            logger.warning(
                f"Graph evidence retrieval failed for topic='{topic}', "
                f"module='{module_name}': {e} — continuing in claim-only mode"
            )
            evidence_text = ""

    if evidence_text:
        prompt += f"{evidence_text}\n\n"

    # Append deep analysis data based on topic/hdd_type
    if deep_analysis:
        topic_lower = topic.lower() if topic else ""

        if hdd_type == "chip" and "chip_config" in deep_analysis:
            prompt += (
                "Package Constants (from chip_config analysis):\n"
                f"{json.dumps(deep_analysis['chip_config'], ensure_ascii=False, default=str)[:2000]}\n\n"
            )
        if hdd_type == "chip" and "sram_inventory" in deep_analysis:
            prompt += (
                "SRAM Inventory:\n"
                f"{json.dumps(deep_analysis['sram_inventory'], ensure_ascii=False, default=str)[:2000]}\n\n"
            )
        if topic_lower == "edc" and "edc_topology" in deep_analysis:
            prompt += (
                "EDC Topology (ring topology, serial bus, harvest bypass, node ID table):\n"
                f"{json.dumps(deep_analysis['edc_topology'], ensure_ascii=False, default=str)[:2000]}\n\n"
            )
        if topic_lower == "noc" and "noc_protocol" in deep_analysis:
            prompt += (
                "NoC Protocol (routing algorithms, flit structure, AXI address gasket, security fence):\n"
                f"{json.dumps(deep_analysis['noc_protocol'], ensure_ascii=False, default=str)[:2000]}\n\n"
            )
        if topic_lower == "overlay" and "overlay_deep" in deep_analysis:
            prompt += (
                "Overlay Deep Analysis (CPU cluster, L1 cache, APB slaves):\n"
                f"{json.dumps(deep_analysis['overlay_deep'], ensure_ascii=False, default=str)[:2000]}\n\n"
            )

    prompt += (
        "Output the HDD section in Markdown. Use ## for section headers. "
        "Include all required sections listed above.\n\n"
        "EP Table의 좌표를 참조하여 [FROM LLM] 추론을 검증하라. "
        "East dispatch는 X=3, West dispatch는 X=0이다. "
        "Overlay NOC2AXI row는 Y=4, Tensix rows는 Y=0..3이다. "
        "Composite tile은 Y=3과 Y=4에 걸쳐 있다 (row_span). "
        "좌표 관련 추론이 EP Table과 모순되면 해당 부분을 제거하라."
    )
    return prompt


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

            # 토큰 사용량 로깅
            usage = result.get("usage", {})
            logger.info(json.dumps({
                "event": "claude_hdd_token_usage",
                "model": CLAUDE_MODEL_ID,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "prompt_length": len(prompt),
            }))

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
    deep_analysis: dict[str, Any] | None = None,
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
        deep_analysis: Optional dict of deep analysis results keyed by
            analysis_type (chip_config, edc_topology, noc_protocol,
            overlay_deep, sram_inventory).

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
        deep_analysis=deep_analysis,
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
