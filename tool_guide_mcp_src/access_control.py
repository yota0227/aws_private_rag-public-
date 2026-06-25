"""Access control and pipeline isolation for Tool_Guide_MCP (Task 7.2).

Implements:
  - Pipeline identifier constant ``PIPELINE_ID = "tool-guide"`` (R5.3)
  - Known RTL MCP tool name set ``RTL_TOOL_NAMES`` (R5.2)
  - Tool Guide tool name set ``TOOL_GUIDE_TOOL_NAMES`` (R5.2)
  - ``AccessDeniedError`` — raised when pipeline access is denied (R5.5)
  - ``check_pipeline_access(pipeline_token)`` — MVP boundary-level gate (R5.4)
  - ``assert_no_tool_name_overlap()`` — design-time assertion (R5.2)

Pipeline access model (MVP)
---------------------------
Full LiteLLM/ACL integration is a Non-Goal for this spec
(``requirements.md`` Non-Goals section).  The MVP gate is:

  * Any non-empty, non-whitespace string token → access **granted**.
  * ``None`` or empty string → access **denied** → :class:`AccessDeniedError`.

This mirrors the high-level boundary check described in Design C6 and is
intentionally simple so that the rest of the MCP logic can be tested and
deployed before the full ACL layer is available.

Tool-name isolation (R5.2)
--------------------------
``TOOL_GUIDE_TOOL_NAMES`` and ``RTL_TOOL_NAMES`` are defined as frozen sets.
``assert_no_tool_name_overlap()`` asserts their intersection is empty.  This
function is called at import time to catch naming collisions as early as
possible (fail-fast design pattern).

Requirements validated: 5.2, 5.3, 5.4, 5.5, 5.6
Design reference: C5 Tool_Guide_MCP, C6 접근 경계, Property 12
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline identifier constant (R5.3)
# ---------------------------------------------------------------------------

#: Single, unique pipeline identifier for Tool Guide RAG.
#: Must not coincide with any other pipeline (e.g. ``"rtl"``).
PIPELINE_ID: str = "tool-guide"


# ---------------------------------------------------------------------------
# Tool name sets (R5.2)
# ---------------------------------------------------------------------------

#: Known RTL MCP tool names.  Tool Guide tool names MUST NOT appear here.
RTL_TOOL_NAMES: frozenset[str] = frozenset(
    [
        "search_rtl",
        "rag_query",
        "search_archive",
        "get_evidence",
        "list_verified_claims",
        "rag_validate_answer",
        "generate_hdd_section",
        "publish_markdown",
        "trace_signal_path",
        "find_instantiation_tree",
        "find_clock_crossings",
        "graph_export",
        "rag_list_documents",
        "rag_categories",
        "rag_upload_status",
        "rag_extract_status",
        "rag_delete_document",
        "rag_index_status",
        "rag_read_resource",
        "rag_task_status",
    ]
)

#: Tool Guide MCP tool names.  These MUST NOT overlap with ``RTL_TOOL_NAMES``.
TOOL_GUIDE_TOOL_NAMES: frozenset[str] = frozenset(
    [
        "tool_guide_search",
        "tool_guide_query",
    ]
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AccessDeniedError(PermissionError):
    """Raised when pipeline access is denied due to missing or invalid token.

    Attributes
    ----------
    status:
        Always ``"error:access_denied"`` — the machine-readable error code
        used in the MCP response (R5.5).
    """

    status: str = "error:access_denied"

    def __init__(
        self, message: str = "Access denied: missing or invalid pipeline token."
    ) -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_pipeline_access(pipeline_token: str | None) -> None:
    """Verify that the caller holds a valid ``pipeline=tool-guide`` token.

    MVP policy: any non-empty, non-whitespace string is accepted.
    ``None`` or empty string raises :class:`AccessDeniedError` (R5.4, R5.5).

    Full LiteLLM/ACL integration is out of scope per Non-Goals.

    Parameters
    ----------
    pipeline_token:
        Token supplied by the MCP caller.  ``None`` or ``""`` → denied.

    Raises
    ------
    AccessDeniedError
        When ``pipeline_token`` is ``None`` or an empty (or whitespace-only)
        string.
    """
    if not pipeline_token or not pipeline_token.strip():
        logger.warning(
            "access_denied: pipeline_token=%r pipeline_id=%r",
            pipeline_token,
            PIPELINE_ID,
        )
        raise AccessDeniedError(
            f"Access denied: pipeline_token must be a non-empty string "
            f"to access pipeline '{PIPELINE_ID}'."
        )

    logger.debug(
        "access_granted: pipeline_id=%r token_length=%d",
        PIPELINE_ID,
        len(pipeline_token),
    )


def assert_no_tool_name_overlap() -> None:
    """Assert that Tool Guide tool names do not overlap with RTL tool names.

    This function implements the R5.2 invariant: Tool_Guide_MCP tool names
    must be disjoint from RTL MCP tool names.  It is called at module import
    time and is also available for explicit testing.

    Raises
    ------
    AssertionError
        If ``TOOL_GUIDE_TOOL_NAMES ∩ RTL_TOOL_NAMES ≠ ∅``.
    """
    overlap = TOOL_GUIDE_TOOL_NAMES & RTL_TOOL_NAMES
    assert overlap == frozenset(), (
        f"R5.2 violation: Tool Guide tool names overlap with RTL tool names: "
        f"{overlap!r}. Each pipeline must expose a disjoint set of tool names."
    )


# ---------------------------------------------------------------------------
# Module-level invariant check (fail-fast at import time)
# ---------------------------------------------------------------------------

assert_no_tool_name_overlap()
