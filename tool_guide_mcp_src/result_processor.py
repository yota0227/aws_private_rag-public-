"""Result-shaping module for Tool_Guide_MCP (Task 7.3).

This module is a **pure result-shaping layer** — it takes a raw list of
candidate result dicts (as returned by a vector/keyword search backend) and
transforms them into the final MCP response.

All functions are pure (no I/O, no external calls):
  * :func:`has_complete_citation`  — R4.4, R4.5
  * :func:`filter_by_metadata`     — R4.8
  * :func:`process_results`        — R4.3, R4.5, R4.6, R4.8, R4.9, R6.2, R6.3

Data contract
-------------
Each raw *candidate* item is a dict with at least::

    {
      "id":           str,
      "object_type":  str,
      "canonical_text": str,
      "score":        float,            # relevance score, higher = better
      "pipeline_id":  str,              # must be "tool-guide"
      "metadata": {
        "tool_name":    str,
        "tool_version": str,
        ...
      },
      "citation": {                     # evidence / citation fields
        "source_file":  str,
        "doc_version":  str,
        "page":         int | None,     # at least one of page/section required
        "section":      str | None
      }
    }

Citation completeness rules (R4.4, R4.5)
-----------------------------------------
An item has a **complete citation** iff:

* ``citation.source_file`` is non-empty AND not ``"미확인"``
* ``citation.doc_version`` is non-empty AND not ``"미확인"``
* At least one of:
    - ``citation.page`` is an integer (not ``None``)
    - ``citation.section`` is non-empty AND not ``"미확인"``

Items that fail this check are filtered out **before** the response is built.

Metadata filter rules (R4.8)
-----------------------------
* If ``tool_name`` is given, keep only items where
  ``metadata.tool_name`` matches case-insensitively.
* If ``tool_version`` is given, keep only items where
  ``metadata.tool_version`` matches case-insensitively.
* Both filters can be combined (intersection).
* When both are ``None``, all items pass.

Response shapes (R4.3, R4.6, R4.9, R6.2, R6.3)
-------------------------------------------------
After filtering and sorting the results:

* ``len > 0`` →
  ``{"status": "ok", "results": [top-20 sorted by score desc]}``
* ``len == 0`` AND ``tool_name`` **or** ``tool_version`` was given →
  ``{"status": "no_match", "message": "일치하는 객체 없음", "results": []}``
* ``len == 0`` AND no filter →
  ``{"status": "not_found", "message": "현재 index에서 확인 불가", "results": []}``

The maximum number of items in the ``"results"`` list is **20** (R4.3, R6.2).

Flat-module convention: no package prefix, mirrors other modules in this dir.

Requirements validated: 4.3, 4.4, 4.5, 4.6, 4.8, 4.9, 6.2, 6.3
Design reference: C5 Tool_Guide_MCP (공통 응답 규칙), Property 8, 9, 10
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum number of result items returned by any MCP tool (R4.3, R6.2).
RESULTS_CAP: int = 20

#: Fixed string representing an unknown / unconfirmed metadata value (R3.4).
_UNKNOWN: str = "미확인"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_blank(value: str | None) -> bool:
    """Return True when *value* is None, empty, whitespace-only, or ``"미확인"``."""
    if value is None:
        return True
    stripped = value.strip()
    return stripped == "" or stripped == _UNKNOWN


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def has_complete_citation(item: dict[str, Any]) -> bool:
    """Return True iff *item* has a complete, usable citation.

    A citation is **complete** when:

    1. ``citation.source_file`` is non-empty and not ``"미확인"``.
    2. ``citation.doc_version`` is non-empty and not ``"미확인"``.
    3. At least one of:
       - ``citation.page`` is a non-``None`` integer value, or
       - ``citation.section`` is non-empty and not ``"미확인"``.

    Items missing any of these are filtered out before the response is built
    so that all returned results carry trustworthy evidence (R4.4, R4.5).

    Parameters
    ----------
    item:
        A raw candidate result dict (see module docstring for schema).

    Returns
    -------
    bool
        ``True`` when the citation is complete, ``False`` otherwise.
    """
    citation: dict[str, Any] = item.get("citation") or {}

    # 1. source_file must be present and meaningful
    if _is_blank(citation.get("source_file")):
        return False

    # 2. doc_version must be present and meaningful
    if _is_blank(citation.get("doc_version")):
        return False

    # 3. At least one location anchor: page (int) OR section (non-blank str)
    page = citation.get("page")
    section = citation.get("section")

    has_page = page is not None  # any integer value (including 0) is valid
    has_section = not _is_blank(section)

    return has_page or has_section


def filter_by_metadata(
    items: list[dict[str, Any]],
    tool_name: str | None,
    tool_version: str | None,
) -> list[dict[str, Any]]:
    """Filter *items* by optional ``tool_name`` and ``tool_version`` metadata.

    Filtering is applied to ``item["metadata"]["tool_name"]`` and
    ``item["metadata"]["tool_version"]``.  Comparisons are
    **case-insensitive** (R4.8).

    When a filter value is ``None``, that dimension is not applied (all items
    pass for that dimension).  When both are ``None``, all items are returned
    unchanged.

    Parameters
    ----------
    items:
        Raw candidate list (see module docstring for schema).
    tool_name:
        Optional tool name filter.  ``None`` means "no filter on tool_name".
    tool_version:
        Optional tool version filter.  ``None`` means "no filter on
        tool_version".

    Returns
    -------
    list[dict]
        Filtered list — order preserved.
    """
    if tool_name is None and tool_version is None:
        return list(items)  # copy to avoid mutating caller's list

    name_lower = tool_name.lower() if tool_name is not None else None
    version_lower = tool_version.lower() if tool_version is not None else None

    result: list[dict[str, Any]] = []
    for item in items:
        meta: dict[str, Any] = item.get("metadata") or {}

        if name_lower is not None:
            item_name = (meta.get("tool_name") or "").lower()
            if item_name != name_lower:
                continue

        if version_lower is not None:
            item_version = (meta.get("tool_version") or "").lower()
            if item_version != version_lower:
                continue

        result.append(item)

    return result


def process_results(
    candidates: list[dict[str, Any]],
    tool_name: str | None = None,
    tool_version: str | None = None,
) -> dict[str, Any]:
    """Full result-shaping pipeline for Tool_Guide_MCP responses.

    Applies, in order:

    1. **Metadata filter** — :func:`filter_by_metadata` with ``tool_name``
       and ``tool_version`` (R4.8).
    2. **Citation completeness filter** — exclude items where
       :func:`has_complete_citation` is ``False`` (R4.5).
    3. **Sort** — by ``score`` descending (R4.3).
    4. **Cap** — keep at most :data:`RESULTS_CAP` (20) items (R4.3, R6.2).
    5. **Build response** — choose shape based on result count and whether
       a filter was applied (R4.6, R4.9, R6.3).

    Parameters
    ----------
    candidates:
        Raw candidate result dicts from the search backend.
    tool_name:
        Optional tool name filter passed through to :func:`filter_by_metadata`.
    tool_version:
        Optional tool version filter passed through to
        :func:`filter_by_metadata`.

    Returns
    -------
    dict
        One of three response shapes (see module docstring).
    """
    # Step 1: metadata filter (R4.8)
    filtered = filter_by_metadata(candidates, tool_name, tool_version)

    # Step 2: citation completeness filter (R4.5)
    filtered = [item for item in filtered if has_complete_citation(item)]

    # Step 3: sort by score descending (R4.3)
    filtered.sort(key=lambda item: item.get("score", 0.0), reverse=True)

    # Step 4: cap at RESULTS_CAP (R4.3, R6.2)
    filtered = filtered[:RESULTS_CAP]

    # Step 5: build response
    filter_applied = (tool_name is not None) or (tool_version is not None)

    if len(filtered) == 0:
        if filter_applied:
            # tool_name / tool_version filter produced no matches (R4.9)
            return {
                "status": "no_match",
                "message": "일치하는 객체 없음",
                "results": [],
            }
        else:
            # No corpus evidence at all (R4.6, R6.3)
            return {
                "status": "not_found",
                "message": "현재 index에서 확인 불가",
                "results": [],
            }

    # Normal result with 1..20 items (R4.3, R6.2)
    return {
        "status": "ok",
        "results": filtered,
    }
