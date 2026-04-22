"""
Claim generator for RTL auto-analysis pipeline.

Calls Bedrock Claude 3 Haiku to generate structured claims from
RTL analysis results. Validates claims against the schema and stores
them in DynamoDB and OpenSearch with Titan Embeddings vectors.

Requirements validated: 6.1, 6.2, 6.3, 6.4, 6.5
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3

from claim_utils import validate_claim, split_module_groups

logger = logging.getLogger(__name__)

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
CLAUDE_MODEL_ID = os.environ.get(
    "CLAUDE_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0",
)
CLAIM_DB_TABLE = os.environ.get("CLAIM_DB_TABLE", "bos-ai-claim-db")
TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"

_INVOKE_TIMEOUT = 60
_MAX_RETRIES = 1


def _build_claim_prompt(
    pipeline_id: str,
    topic: str,
    modules: list[dict[str, Any]],
    analysis_results: dict[str, Any],
) -> str:
    """Build the LLM prompt for claim generation."""
    module_summaries = []
    for mod in modules:
        name = mod.get("module_name", "unknown")
        ports = mod.get("port_list", "")
        instances = mod.get("instance_list", "")
        params = mod.get("parameter_list", "")
        module_summaries.append(
            f"- {name}: ports=[{ports}], instances=[{instances}], params=[{params}]"
        )

    hierarchy_info = json.dumps(
        analysis_results.get("hierarchy", {}), ensure_ascii=False, default=str,
    )[:2000]
    clock_info = json.dumps(
        analysis_results.get("clock_domains", []), ensure_ascii=False, default=str,
    )[:1000]
    dataflow_info = json.dumps(
        analysis_results.get("dataflow", []), ensure_ascii=False, default=str,
    )[:1000]

    return (
        "You are an RTL design analysis expert. Analyze the following RTL "
        "modules and generate structured claims.\n\n"
        f"Pipeline ID: {pipeline_id}\n"
        f"Topic: {topic}\n\n"
        "Modules:\n" + "\n".join(module_summaries) + "\n\n"
        f"Hierarchy Info:\n{hierarchy_info}\n\n"
        f"Clock Domain Info:\n{clock_info}\n\n"
        f"Dataflow Info:\n{dataflow_info}\n\n"
        "Generate a JSON array of claims. Each claim must have:\n"
        '- "claim_type": one of "structural", "behavioral", "connectivity", "timing"\n'
        '- "claim_text": a concise technical description of the claim\n'
        '- "confidence_score": float between 0.0 and 1.0\n'
        '- "module_name": the primary module this claim is about\n'
        '- "source_files": list of relevant source file paths\n\n'
        "Respond ONLY with a valid JSON array. No markdown, no explanation."
    )


def _invoke_claude(prompt: str) -> str:
    """Invoke Bedrock Claude 3 Haiku and return the text response.

    Retries up to ``_MAX_RETRIES`` times on failure.
    Timeout per call: ``_INVOKE_TIMEOUT`` seconds.
    """
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
                "event": "claude_claim_token_usage",
                "model": CLAUDE_MODEL_ID,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }))

            # Claude response: {"content": [{"type": "text", "text": "..."}]}
            return result["content"][0]["text"]
        except Exception as e:
            last_error = e
            logger.warning(
                "Claude invocation attempt %d failed: %s", attempt + 1, e,
            )

    raise RuntimeError(
        f"Claude invocation failed after {_MAX_RETRIES + 1} attempts: {last_error}"
    )


def _generate_embedding(text: str) -> list[float] | None:
    """Generate Titan Embeddings v2 vector for claim text."""
    try:
        bedrock_client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
        body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
        response = bedrock_client.invoke_model(
            modelId=TITAN_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result.get("embedding")
    except Exception as e:
        logger.error("Titan embedding generation failed: %s", e)
        return None


def _parse_claims_response(response_text: str) -> list[dict[str, Any]]:
    """Parse the JSON array from Claude's response text."""
    text = response_text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        return []
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Claude response as JSON: %s", e)
        return []


def generate_claims(
    pipeline_id: str,
    topic: str,
    modules: list[dict[str, Any]],
    analysis_results: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate structured claims from RTL analysis results using Bedrock Claude.

    1. split_module_groups() splits modules to fit token limits.
    2. For each chunk, invoke Bedrock Claude with the analysis prompt.
    3. validate_claim() checks each generated claim against the schema.
    4. Valid claims are stored in DynamoDB claim_db table.
    5. Claims are indexed in OpenSearch with Titan Embeddings vectors.

    Args:
        pipeline_id: Pipeline identifier (e.g. ``tt_20260221``).
        topic: Topic category (e.g. ``NoC``).
        modules: List of module dicts with parsed metadata.
        analysis_results: Dict with ``hierarchy``, ``clock_domains``,
            ``dataflow`` keys from prior analysis stages.

    Returns:
        List of validated claim dicts that were successfully stored.
    """
    if not modules:
        return []

    chunks = split_module_groups(modules)
    all_claims: list[dict[str, Any]] = []
    seq = 0

    for chunk in chunks:
        prompt = _build_claim_prompt(pipeline_id, topic, chunk, analysis_results)

        try:
            response_text = _invoke_claude(prompt)
        except RuntimeError as e:
            logger.error(
                "Claim generation failed for topic=%s chunk: %s", topic, e,
            )
            continue

        raw_claims = _parse_claims_response(response_text)

        for raw in raw_claims:
            seq += 1
            claim_id = f"clm_{pipeline_id}_{topic}_{seq:03d}"

            # Determine source files from the chunk modules if not provided
            source_files = raw.get("source_files")
            if not source_files or not isinstance(source_files, list):
                source_files = [
                    m.get("file_path", "") for m in chunk if m.get("file_path")
                ]
                if not source_files:
                    source_files = ["unknown"]

            claim: dict[str, Any] = {
                "claim_id": claim_id,
                "pipeline_id": pipeline_id,
                "module_name": raw.get("module_name", chunk[0].get("module_name", "")),
                "topic": topic,
                "claim_type": raw.get("claim_type", "structural"),
                "claim_text": raw.get("claim_text", ""),
                "confidence_score": float(raw.get("confidence_score", 0.5)),
                "source_files": source_files,
                "version": 1,
                "status": "auto_generated",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            is_valid, errors = validate_claim(claim)
            if not is_valid:
                logger.warning(
                    "Claim %s failed validation: %s", claim_id, errors,
                )
                continue

            all_claims.append(claim)

    return all_claims
