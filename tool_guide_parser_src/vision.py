"""Optional Vision describer for text-sparse PDF pages (Requirement 7).

EDA tool-guide PDFs contain diagram / block-diagram / floorplan / register-map
pages whose extractable text is sparse (mostly figure labels). Plain text
extraction yields a jumble of disconnected labels that cannot answer questions
like "what is signal PClkBufIn". This module renders such a page to an image
and asks Bedrock Claude (Converse API) to describe its components, signal flow,
interfaces, and labels, producing a content-bearing description that the
reference chunker embeds like any other page text.

Design (design.md C2 "Vision 다이어그램 처리", R7):
  * Gated by ``ENABLE_VISION_PARSING`` (handled by the caller); this module is
    only invoked when Vision is enabled.
  * Embedding is unchanged (Titan Embed v2, R1.5) — Vision only produces text.
  * Reuses Bedrock (no new model family; Converse with a configured Claude id).

The public surface is :func:`make_bedrock_vision_describer`, which returns a
``Callable[[bytes], str]`` mapping PNG image bytes to a description string.
Keeping it as an injectable callable lets the textualize layer stay testable
(unit tests inject a fake describer; no AWS needed).

Flat-module convention: absolute imports, no package.

Requirements validated: 7.2, 7.3, 7.6
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Default Claude model for Vision (overridable via env). Converse API is
# model-agnostic; the account must have access to the chosen model. Uses a
# cross-region inference profile id (us. prefix).
DEFAULT_VISION_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# Prompt steering the description toward EDA diagram semantics (design.md C2).
VISION_PROMPT = (
    "You are reading a page from an EDA / semiconductor IP tool guide or "
    "databook. This page is a diagram, block diagram, floorplan, or "
    "register-map figure with little body text. Describe its content as "
    "searchable prose: list the blocks/components, the signals and their "
    "directions (input/output/bidirectional), interfaces, clock/reset lines, "
    "and any labels or signal names shown (e.g. module names, pin names). "
    "Preserve exact label and signal names verbatim. Do not invent details "
    "that are not visible. Respond in plain text."
)

VisionDescriber = Callable[[bytes], str]


def make_bedrock_vision_describer(
    *,
    bedrock_client: object | None = None,
    region: str | None = None,
    model_id: str | None = None,
    max_tokens: int = 1200,
) -> VisionDescriber:
    """Build a describer ``(png_bytes) -> description`` backed by Bedrock Converse.

    The Bedrock client is created lazily on first call (Lambda cold-start safe)
    unless one is injected. Region/model default to env vars then sensible
    constants. The returned callable raises on Bedrock failure; the caller
    (textualize) is responsible for the R7.4 fallback to original page text.

    Args:
        bedrock_client: Optional injected boto3 ``bedrock-runtime`` client.
        region: Bedrock region (defaults to ``BEDROCK_REGION`` or us-east-1).
        model_id: Claude model id (defaults to ``VISION_MODEL_ID`` env or
            :data:`DEFAULT_VISION_MODEL_ID`).
        max_tokens: Max tokens for the generated description.

    Returns:
        A callable mapping PNG bytes to a description string.
    """
    resolved_region = region or os.environ.get("BEDROCK_REGION", "us-east-1")
    resolved_model = (
        model_id or os.environ.get("VISION_MODEL_ID") or DEFAULT_VISION_MODEL_ID
    )

    state: dict[str, object] = {"client": bedrock_client}

    def _client() -> object:
        if state["client"] is None:
            import boto3
            from botocore.config import Config

            state["client"] = boto3.client(
                "bedrock-runtime",
                region_name=resolved_region,
                config=Config(retries={"max_attempts": 4, "mode": "adaptive"}),
            )
        return state["client"]

    def describe(png_bytes: bytes) -> str:
        client = _client()
        resp = client.converse(
            modelId=resolved_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"text": VISION_PROMPT},
                        {"image": {"format": "png", "source": {"bytes": png_bytes}}},
                    ],
                }
            ],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0},
        )
        parts = resp["output"]["message"]["content"]
        text = "".join(p.get("text", "") for p in parts).strip()
        logger.debug("vision_describe ok: model=%s chars=%d", resolved_model, len(text))
        return text

    return describe
