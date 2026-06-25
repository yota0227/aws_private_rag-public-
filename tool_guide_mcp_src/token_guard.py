"""Token limit guard for Tool_Guide_MCP input validation.

Implements the cheap character-proxy check described in Design C3 and
Requirements R4.10:

  * The binding token limit is the Bedrock Titan Embed Text v2 input token
    window of **8,192 tokens**.
  * A character-length proxy ``len(query) > 8192 * 4 = 32,768 chars`` is
    used as a low-cost pre-flight guard — computing actual token counts for
    every query would be expensive and unnecessary for the vast majority of
    inputs.
  * A WARNING is logged when the query length reaches >= 75 % of the proxy
    threshold (>= 24,576 chars), mirroring the behaviour in
    ``aws_ingest_store.py::_check_token_limit``.
  * If the proxy check fails, :class:`TokenLimitError` is raised with
    ``status = "error:token_limit"`` and **no partial result is returned**.

Flat-module convention: no package prefix, mirrors other modules in this dir.

Requirements validated: 4.10
Design reference: C3 Embedding & Index (토큰 하드 리밋), C5 Tool_Guide_MCP
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (identical to aws_ingest_store.py — single source of truth for
# the proxy ratio is the design document; both modules implement the same rule)
# ---------------------------------------------------------------------------

#: Titan Embed v2 token window x char-per-token proxy factor (4 chars ~= 1 token).
TOKEN_LIMIT_CHAR_PROXY: int = 8192 * 4  # 32 768 chars

#: Warn threshold: 75 % of the hard proxy limit (= 24 576 chars).
TOKEN_WARN_THRESHOLD: int = int(TOKEN_LIMIT_CHAR_PROXY * 0.75)  # 24 576 chars


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TokenLimitError(ValueError):
    """Raised when a query exceeds the embedding token-limit proxy.

    Attributes
    ----------
    status:
        Always ``"error:token_limit"`` — the machine-readable error code
        defined in the design Error Handling table (R4.10).
    char_len:
        Actual character length of the rejected query.
    """

    status: str = "error:token_limit"

    def __init__(self, message: str, char_len: int) -> None:
        super().__init__(message)
        self.char_len = char_len


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_token_limit(query: str, context: str = "") -> None:
    """Check that *query* does not exceed the embedding token-limit proxy.

    This function is the MCP-layer equivalent of
    ``AwsIngestStore._check_token_limit`` used in the ingestion path.  Both
    enforce the same proxy formula and warning threshold so the guard is
    consistent across the entire pipeline.

    Parameters
    ----------
    query:
        The query string to check (already passed the character length gate in
        :func:`tool_guide_search` / :func:`tool_guide_query`).
    context:
        Optional caller context string included in log messages for
        traceability (e.g. ``"tool_guide_query"``).

    Raises
    ------
    TokenLimitError
        When ``len(query) > TOKEN_LIMIT_CHAR_PROXY``.  No partial result is
        produced or returned (R4.10).
    """
    char_len = len(query)

    if char_len >= TOKEN_WARN_THRESHOLD:
        logger.warning(
            "token_limit_approaching: context=%r char_len=%d threshold=%d hard_limit=%d",
            context,
            char_len,
            TOKEN_WARN_THRESHOLD,
            TOKEN_LIMIT_CHAR_PROXY,
        )

    if char_len > TOKEN_LIMIT_CHAR_PROXY:
        raise TokenLimitError(
            f"Query exceeds token-limit proxy: {char_len} chars > "
            f"{TOKEN_LIMIT_CHAR_PROXY} (context={context!r}). "
            "Shorten the query.",
            char_len=char_len,
        )
