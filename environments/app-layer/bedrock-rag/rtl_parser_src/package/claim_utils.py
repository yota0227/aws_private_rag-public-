"""
Claim schema validation and token splitting for RTL auto-analysis pipeline.

Provides claim validation against the required schema and module group
splitting to respect LLM token limits.

Requirements validated: 6.2, 6.4
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = (
    "claim_id",
    "module_name",
    "topic",
    "claim_type",
    "claim_text",
    "confidence_score",
    "source_files",
)

_VALID_CLAIM_TYPES = frozenset({
    "structural",
    "behavioral",
    "connectivity",
    "timing",
})


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text string.

    Uses a simple heuristic of ``len(text) / 4`` which provides a
    rough approximation suitable for pre-flight token budget checks.

    Args:
        text: Input text string.

    Returns:
        Estimated token count (integer, minimum 0).
    """
    if not text or not isinstance(text, str):
        return 0
    return max(0, len(text) // 4)


def validate_claim(claim: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a claim dict against the required schema.

    Checks:
        - All required fields are present and non-empty.
        - ``claim_type`` is one of: structural, behavioral, connectivity, timing.
        - ``confidence_score`` is a float in [0.0, 1.0].
        - ``source_files`` is a non-empty list.

    Args:
        claim: Claim dictionary to validate.

    Returns:
        Tuple of ``(is_valid, errors)`` where *errors* is a list of
        human-readable error strings.  Empty when valid.
    """
    if not claim or not isinstance(claim, dict):
        return False, ["claim must be a non-empty dict"]

    errors: list[str] = []

    # Check required fields
    for field in _REQUIRED_FIELDS:
        if field not in claim:
            errors.append(f"missing required field: {field}")
        elif claim[field] is None:
            errors.append(f"field '{field}' must not be None")

    # Validate claim_type
    claim_type = claim.get("claim_type")
    if claim_type is not None and claim_type not in _VALID_CLAIM_TYPES:
        errors.append(
            f"invalid claim_type '{claim_type}'; "
            f"must be one of {sorted(_VALID_CLAIM_TYPES)}"
        )

    # Validate confidence_score
    score = claim.get("confidence_score")
    if score is not None:
        if not isinstance(score, (int, float)):
            errors.append("confidence_score must be a number")
        elif not (0.0 <= float(score) <= 1.0):
            errors.append(
                f"confidence_score {score} out of range [0.0, 1.0]"
            )

    # Validate source_files
    source_files = claim.get("source_files")
    if source_files is not None:
        if not isinstance(source_files, list):
            errors.append("source_files must be a list")
        elif len(source_files) == 0:
            errors.append("source_files must not be empty")

    return (len(errors) == 0, errors)


def split_module_groups(
    modules: list[dict[str, Any]],
    max_tokens: int = 100_000,
) -> list[list[dict[str, Any]]]:
    """Split modules into chunks that fit within a token budget.

    Each module's token count is estimated from its ``parsed_summary``
    field using ``estimate_tokens``.  Modules are packed greedily into
    chunks so that each chunk's total tokens does not exceed
    *max_tokens*.  Every module appears in exactly one chunk.

    A single module whose estimated tokens exceed *max_tokens* is placed
    alone in its own chunk (with a warning logged).

    Args:
        modules: List of module dicts, each expected to have a
            ``parsed_summary`` string field.
        max_tokens: Maximum token budget per chunk (default 100 000).

    Returns:
        List of chunks, where each chunk is a list of module dicts.
        Returns empty list for empty input.
    """
    if not modules or not isinstance(modules, list):
        return []

    if max_tokens <= 0:
        logger.warning("max_tokens must be positive; using default 100000")
        max_tokens = 100_000

    chunks: list[list[dict[str, Any]]] = []
    current_chunk: list[dict[str, Any]] = []
    current_tokens = 0

    for mod in modules:
        summary = mod.get("parsed_summary", "") if isinstance(mod, dict) else ""
        mod_tokens = estimate_tokens(summary)

        if mod_tokens > max_tokens:
            logger.warning(
                "Module '%s' has ~%d tokens, exceeding max_tokens=%d. "
                "Placing in its own chunk.",
                mod.get("module_name", "unknown") if isinstance(mod, dict) else "unknown",
                mod_tokens,
                max_tokens,
            )
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0
            chunks.append([mod])
            continue

        if current_tokens + mod_tokens > max_tokens and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(mod)
        current_tokens += mod_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
