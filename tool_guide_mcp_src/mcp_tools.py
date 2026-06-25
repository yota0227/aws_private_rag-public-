"""Tool_Guide_MCP entry points -- input validation + access control layer.

Defines the two MCP tool entry points for Tool Guide RAG:

``tool_guide_search(query, ...)``
    Symbol / command-name search.  Query must be 1..256 chars (R4.1, R6.4).

``tool_guide_query(query, ...)``
    Natural-language query.  Query must be 1..8192 chars (R4.2, R6.4).

Both functions (in order):
  1. Validate character length -- reject empty queries and queries exceeding
     the limit with :class:`InputLengthError` (``error:input_length``).
  2. Apply the embedding token-limit hard guard via
     :func:`token_guard.check_token_limit` -- reject oversized queries with
     :class:`~token_guard.TokenLimitError` (``error:token_limit``, R4.10).
  3. **Check pipeline access** via
     :func:`access_control.check_pipeline_access` -- catch
     :class:`~access_control.AccessDeniedError` and return a zero-result
     error response (R5.4, R5.5, Task 7.2).
  4. Invoke the search backend (if wired) and assert that every result item's
     ``pipeline_id`` is ``"tool-guide"`` to guard against RTL corpus
     cross-contamination (R5.6, Task 7.2).
  5. Return ``{"status": "ok", "query": query, ...}`` on success.

Access-denied response shape
-----------------------------
When :class:`~access_control.AccessDeniedError` is caught, the response is::

    {
        "error": "error:access_denied",
        "results": [],
        "message": "<human-readable explanation>",
    }

This matches the design Error Handling table (R5.5) and Property 12.

Flat-module convention: no package prefix, mirrors ``tool_guide_parser_src/``.

Requirements validated: 4.1, 4.2, 4.10, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4
Design reference: C5 Tool_Guide_MCP, C6 접근 경계, Property 11, Property 12
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from access_control import (  # noqa: F401
    PIPELINE_ID as _PIPELINE_ID,
    AccessDeniedError,
    check_pipeline_access,
)
from result_processor import process_results  # noqa: F401
from token_guard import TokenLimitError, check_token_limit  # noqa: F401

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum query length for ``tool_guide_search`` (symbol search, R4.1).
SEARCH_QUERY_MAX_CHARS: int = 256

#: Maximum query length for ``tool_guide_query`` (natural-language, R4.2).
QUERY_MAX_CHARS: int = 8192

#: Minimum query length (both tools): 1 character -- empty queries rejected (R6.4).
QUERY_MIN_CHARS: int = 1


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InputLengthError(ValueError):
    """Raised when a query violates the character-length rules.

    Attributes
    ----------
    status:
        Always ``"error:input_length"`` -- the machine-readable error code
        defined in the design Error Handling table (R6.4, R4.1, R4.2).
    char_len:
        Actual character length of the rejected query.
    limit:
        The applicable character limit (``SEARCH_QUERY_MAX_CHARS`` or
        ``QUERY_MAX_CHARS``).
    """

    status: str = "error:input_length"

    def __init__(self, message: str, char_len: int, limit: int) -> None:
        super().__init__(message)
        self.char_len = char_len
        self.limit = limit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_char_length(query: str, max_chars: int, tool_name: str) -> None:
    """Validate that *query* satisfies 1 <= len(query) <= max_chars.

    Parameters
    ----------
    query:
        The raw query string supplied by the caller.
    max_chars:
        Tool-specific upper bound (256 for search, 8192 for query).
    tool_name:
        Human-readable tool identifier used in error messages and logs.

    Raises
    ------
    InputLengthError
        When the query is empty (length 0) or exceeds *max_chars*.
    """
    char_len = len(query)

    # Reject empty queries AND whitespace-only queries (R6.4).
    # A query composed entirely of whitespace carries no information and must
    # be refused with the same error as an empty query.
    if char_len < QUERY_MIN_CHARS or not query.strip():
        raise InputLengthError(
            f"{tool_name}: query must not be empty or whitespace-only "
            f"(received {char_len} chars, minimum {QUERY_MIN_CHARS} non-whitespace).",
            char_len=char_len,
            limit=max_chars,
        )

    if char_len > max_chars:
        raise InputLengthError(
            f"{tool_name}: query length {char_len} exceeds the {max_chars}-char limit.",
            char_len=char_len,
            limit=max_chars,
        )


def _assert_pipeline_id_clean(results: list[Any], tool_name: str) -> None:
    """Assert that every result item's ``pipeline_id`` equals ``"tool-guide"``.

    This guard prevents RTL corpus results from leaking into Tool Guide
    responses (R5.6).  It is applied to every result item that carries a
    ``pipeline_id`` key.  Items without the key are left to the filter layer
    in Task 7.3.

    Parameters
    ----------
    results:
        List of result dicts returned by the search backend.
    tool_name:
        Human-readable tool identifier for the assertion message.

    Raises
    ------
    AssertionError
        If any result dict contains a ``pipeline_id`` value that is not
        ``"tool-guide"``.
    """
    for item in results:
        if isinstance(item, dict) and "pipeline_id" in item:
            pid = item["pipeline_id"]
            assert pid == _PIPELINE_ID, (
                f"R5.6 violation in {tool_name}: result item has "
                f"pipeline_id={pid!r}, expected {_PIPELINE_ID!r}. "
                "RTL corpus results must not appear in Tool Guide responses."
            )


# ---------------------------------------------------------------------------
# MCP tool entry points
# ---------------------------------------------------------------------------


def tool_guide_search(
    query: str,
    tool_name: str | None = None,
    tool_version: str | None = None,
    pipeline_token: str | None = None,
    search_backend: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Symbol / command-name search tool entry point.

    Validates the query (1..256 chars), applies the token-limit guard,
    checks pipeline access, then invokes the search backend (if wired).

    Parameters
    ----------
    query:
        Symbol or command name to search.  Must be 1..256 characters.
    tool_name:
        Optional EDA tool filter (e.g. ``"VCS"``).
    tool_version:
        Optional tool version filter (e.g. ``"2023.12"``).
    pipeline_token:
        Pipeline access token.  ``None`` or empty → access denied (R5.4, R5.5).
    search_backend:
        Injectable callable for the search logic.  ``None`` when no backend
        is wired (returns empty results list).

    Returns
    -------
    dict
        On success: ``{"status": "ok", "query": query, "tool_name": tool_name,
        "tool_version": tool_version, "results": [...]}``.
        On access denied: ``{"error": "error:access_denied", "results": [],
        "message": "..."}``.

    Raises
    ------
    InputLengthError
        If the query is empty or exceeds 256 characters.
    ~token_guard.TokenLimitError
        If the query passes the char gate but exceeds the token-limit proxy.
    """
    # Step 1: character length validation (R4.1, R6.4)
    _validate_char_length(query, SEARCH_QUERY_MAX_CHARS, "tool_guide_search")

    # Step 2: token-limit hard guard (R4.10) -- char gate already passed
    check_token_limit(query, context="tool_guide_search")

    # Step 3: pipeline access check (R5.4, R5.5) -- catch and return error dict
    try:
        check_pipeline_access(pipeline_token)
    except AccessDeniedError as exc:
        logger.warning("tool_guide_search: %s", exc)
        return {
            "error": AccessDeniedError.status,
            "results": [],
            "message": str(exc),
        }

    logger.debug(
        "tool_guide_search: query_len=%d tool_name=%r tool_version=%r",
        len(query),
        tool_name,
        tool_version,
    )

    # Step 4: invoke search backend when wired
    if search_backend is not None:
        raw_candidates = search_backend(
            query=query,
            tool_name=tool_name,
            tool_version=tool_version,
            pipeline_token=pipeline_token,
        )

        # Step 5: assert no RTL cross-contamination (R5.6)
        _assert_pipeline_id_clean(raw_candidates, "tool_guide_search")

        # Step 6: apply result shaping (filter, sort, cap, citation, empty msg)
        processed = process_results(
            raw_candidates, tool_name=tool_name, tool_version=tool_version
        )
        # Merge the shaped response with query context fields.
        return {
            **processed,
            "query": query,
            "tool_name": tool_name,
            "tool_version": tool_version,
        }

    # No backend wired (validation-only path)
    return {
        "status": "ok",
        "query": query,
        "tool_name": tool_name,
        "tool_version": tool_version,
        "results": [],
    }


def tool_guide_query(
    query: str,
    tool_name: str | None = None,
    tool_version: str | None = None,
    pipeline_token: str | None = None,
    search_backend: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Natural-language query tool entry point.

    Validates the query (1..8192 chars), applies the token-limit guard,
    checks pipeline access, then invokes the search backend (if wired).

    Parameters
    ----------
    query:
        Natural-language question.  Must be 1..8192 characters.
    tool_name:
        Optional EDA tool filter.
    tool_version:
        Optional tool version filter.
    pipeline_token:
        Pipeline access token.  ``None`` or empty → access denied (R5.4, R5.5).
    search_backend:
        Injectable callable for the search logic.  ``None`` when no backend
        is wired (returns empty results list).

    Returns
    -------
    dict
        On success: ``{"status": "ok", "query": query, "tool_name": tool_name,
        "tool_version": tool_version, "results": [...]}``.
        On access denied: ``{"error": "error:access_denied", "results": [],
        "message": "..."}``.

    Raises
    ------
    InputLengthError
        If the query is empty or exceeds 8192 characters.
    ~token_guard.TokenLimitError
        If the query passes the char gate but exceeds the token-limit proxy.
    """
    # Step 1: character length validation (R4.2, R6.4)
    _validate_char_length(query, QUERY_MAX_CHARS, "tool_guide_query")

    # Step 2: token-limit hard guard (R4.10) -- char gate already passed
    check_token_limit(query, context="tool_guide_query")

    # Step 3: pipeline access check (R5.4, R5.5) -- catch and return error dict
    try:
        check_pipeline_access(pipeline_token)
    except AccessDeniedError as exc:
        logger.warning("tool_guide_query: %s", exc)
        return {
            "error": AccessDeniedError.status,
            "results": [],
            "message": str(exc),
        }

    logger.debug(
        "tool_guide_query: query_len=%d tool_name=%r tool_version=%r",
        len(query),
        tool_name,
        tool_version,
    )

    # Step 4: invoke search backend when wired
    if search_backend is not None:
        raw_candidates = search_backend(
            query=query,
            tool_name=tool_name,
            tool_version=tool_version,
            pipeline_token=pipeline_token,
        )

        # Step 5: assert no RTL cross-contamination (R5.6)
        _assert_pipeline_id_clean(raw_candidates, "tool_guide_query")

        # Step 6: apply result shaping (filter, sort, cap, citation, empty msg)
        processed = process_results(
            raw_candidates, tool_name=tool_name, tool_version=tool_version
        )
        # Merge the shaped response with query context fields.
        return {
            **processed,
            "query": query,
            "tool_name": tool_name,
            "tool_version": tool_version,
        }

    # No backend wired (validation-only path)
    return {
        "status": "ok",
        "query": query,
        "tool_name": tool_name,
        "tool_version": tool_version,
        "results": [],
    }
