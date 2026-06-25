"""Unit tests for result_processor.py (Task 7.3).

Covers all acceptance criteria from the task spec:

has_complete_citation
~~~~~~~~~~~~~~~~~~~~~
  - complete item → True
  - missing source_file → False
  - missing doc_version → False
  - both page and section None / empty / "미확인" → False
  - page=42, no section → True
  - section="S1", no page → True

filter_by_metadata
~~~~~~~~~~~~~~~~~~
  - no filter → all items returned
  - tool_name filter → only matching items
  - tool_version filter → only matching items
  - both → intersection
  - case-insensitive match

process_results
~~~~~~~~~~~~~~~
  - >20 candidates → capped at 20
  - sorted by score desc
  - items with incomplete citation excluded
  - 0 results with tool_name filter → "일치하는 객체 없음" (no_match)
  - 0 results no filter → "현재 index에서 확인 불가" (not_found)
  - mixed complete/incomplete citations → only complete returned
  - monotone non-increasing score invariant

Requirements validated: 4.3, 4.4, 4.5, 4.6, 4.8, 4.9, 6.2, 6.3
Design reference: C5 Tool_Guide_MCP, Property 8, 9, 10
"""

from __future__ import annotations

import pytest

from result_processor import (
    RESULTS_CAP,
    filter_by_metadata,
    has_complete_citation,
    process_results,
)


# ===========================================================================
# Fixtures / helpers
# ===========================================================================


def _make_item(
    *,
    id: str = "obj-001",
    score: float = 0.9,
    tool_name: str = "VCS",
    tool_version: str = "2023.12",
    source_file: str = "vcs_guide.pdf",
    doc_version: str = "2023.12-rev1",
    page: int | None = 42,
    section: str | None = None,
) -> dict:
    """Return a minimal candidate item dict with sane defaults."""
    return {
        "id": id,
        "object_type": "command",
        "canonical_text": "Command 'elaborate' compiles the design.",
        "score": score,
        "pipeline_id": "tool-guide",
        "metadata": {
            "tool_name": tool_name,
            "tool_version": tool_version,
            "command": "elaborate",
            "option": "미확인",
            "section": "4.2",
            "doc_version": doc_version,
            "object_type": "command",
        },
        "citation": {
            "source_file": source_file,
            "doc_version": doc_version,
            "page": page,
            "section": section,
        },
    }


def _make_items(n: int, base_score: float = 1.0) -> list[dict]:
    """Return *n* distinct complete candidate items with descending scores."""
    return [
        _make_item(id=f"obj-{i:03d}", score=base_score - i * 0.01)
        for i in range(n)
    ]


# ===========================================================================
# has_complete_citation
# ===========================================================================


class TestHasCompleteCitation:
    """Unit tests for has_complete_citation."""

    def test_complete_item_returns_true(self) -> None:
        """A fully populated citation must return True."""
        item = _make_item(source_file="guide.pdf", doc_version="1.0", page=10)
        assert has_complete_citation(item) is True

    def test_missing_source_file_returns_false(self) -> None:
        """Missing (empty) source_file must return False."""
        item = _make_item(source_file="", page=5)
        assert has_complete_citation(item) is False

    def test_none_source_file_returns_false(self) -> None:
        """None source_file must return False."""
        item = _make_item()
        item["citation"]["source_file"] = None
        assert has_complete_citation(item) is False

    def test_unknown_source_file_returns_false(self) -> None:
        """source_file='미확인' must return False."""
        item = _make_item(source_file="미확인", page=1)
        assert has_complete_citation(item) is False

    def test_missing_doc_version_returns_false(self) -> None:
        """Missing (empty) doc_version must return False."""
        item = _make_item(doc_version="", page=5)
        assert has_complete_citation(item) is False

    def test_unknown_doc_version_returns_false(self) -> None:
        """doc_version='미확인' must return False."""
        item = _make_item(doc_version="미확인", page=1)
        assert has_complete_citation(item) is False

    def test_none_doc_version_returns_false(self) -> None:
        """None doc_version must return False."""
        item = _make_item()
        item["citation"]["doc_version"] = None
        assert has_complete_citation(item) is False

    def test_both_page_and_section_none_returns_false(self) -> None:
        """page=None and section=None must return False."""
        item = _make_item(page=None, section=None)
        assert has_complete_citation(item) is False

    def test_page_none_empty_section_returns_false(self) -> None:
        """page=None and section='' must return False."""
        item = _make_item(page=None, section="")
        assert has_complete_citation(item) is False

    def test_page_none_unknown_section_returns_false(self) -> None:
        """page=None and section='미확인' must return False."""
        item = _make_item(page=None, section="미확인")
        assert has_complete_citation(item) is False

    def test_page_42_no_section_returns_true(self) -> None:
        """page=42 with section=None must return True (page alone sufficient)."""
        item = _make_item(page=42, section=None)
        assert has_complete_citation(item) is True

    def test_page_zero_returns_true(self) -> None:
        """page=0 must return True — zero is a valid page number."""
        item = _make_item(page=0, section=None)
        assert has_complete_citation(item) is True

    def test_section_only_returns_true(self) -> None:
        """section='S1' with page=None must return True (section alone sufficient)."""
        item = _make_item(page=None, section="S1")
        assert has_complete_citation(item) is True

    def test_both_page_and_section_present_returns_true(self) -> None:
        """Both page and section present must return True."""
        item = _make_item(page=5, section="4.2 Elaboration")
        assert has_complete_citation(item) is True

    def test_missing_citation_key_entirely_returns_false(self) -> None:
        """Item without 'citation' key at all must return False."""
        item = _make_item()
        del item["citation"]
        assert has_complete_citation(item) is False

    def test_citation_is_none_returns_false(self) -> None:
        """Item with citation=None must return False."""
        item = _make_item()
        item["citation"] = None
        assert has_complete_citation(item) is False


# ===========================================================================
# filter_by_metadata
# ===========================================================================


class TestFilterByMetadata:
    """Unit tests for filter_by_metadata."""

    def _items(self) -> list[dict]:
        return [
            _make_item(id="a", tool_name="VCS", tool_version="2023.12"),
            _make_item(id="b", tool_name="VCS", tool_version="2024.01"),
            _make_item(id="c", tool_name="Verdi", tool_version="2023.12"),
            _make_item(id="d", tool_name="Verdi", tool_version="2024.01"),
        ]

    def test_no_filter_returns_all_items(self) -> None:
        """Both filters None → all items returned."""
        items = self._items()
        result = filter_by_metadata(items, None, None)
        assert len(result) == 4
        assert {r["id"] for r in result} == {"a", "b", "c", "d"}

    def test_tool_name_filter_returns_only_matching(self) -> None:
        """tool_name='VCS' → only VCS items returned."""
        items = self._items()
        result = filter_by_metadata(items, "VCS", None)
        assert len(result) == 2
        assert all(r["metadata"]["tool_name"] == "VCS" for r in result)

    def test_tool_version_filter_returns_only_matching(self) -> None:
        """tool_version='2023.12' → only 2023.12 items returned."""
        items = self._items()
        result = filter_by_metadata(items, None, "2023.12")
        assert len(result) == 2
        assert all(r["metadata"]["tool_version"] == "2023.12" for r in result)

    def test_both_filters_returns_intersection(self) -> None:
        """tool_name='VCS' AND tool_version='2023.12' → exactly one item."""
        items = self._items()
        result = filter_by_metadata(items, "VCS", "2023.12")
        assert len(result) == 1
        assert result[0]["id"] == "a"

    def test_tool_name_filter_case_insensitive(self) -> None:
        """Filter is case-insensitive: 'vcs' must match 'VCS' items."""
        items = self._items()
        result = filter_by_metadata(items, "vcs", None)
        assert len(result) == 2
        assert all(r["metadata"]["tool_name"] == "VCS" for r in result)

    def test_tool_version_filter_case_insensitive(self) -> None:
        """Filter is case-insensitive: version comparison ignores case."""
        items = [_make_item(id="x", tool_name="MyTool", tool_version="V2.0")]
        result = filter_by_metadata(items, None, "v2.0")
        assert len(result) == 1

    def test_both_filters_case_insensitive(self) -> None:
        """Both filters case-insensitive simultaneously."""
        items = self._items()
        result = filter_by_metadata(items, "VERDI", "2024.01")
        assert len(result) == 1
        assert result[0]["id"] == "d"

    def test_no_match_returns_empty_list(self) -> None:
        """Non-existing tool name → empty list."""
        items = self._items()
        result = filter_by_metadata(items, "Calibre", None)
        assert result == []

    def test_original_list_not_mutated_when_no_filter(self) -> None:
        """No-filter case returns a copy, not the original list."""
        items = self._items()
        result = filter_by_metadata(items, None, None)
        result.append(_make_item(id="extra"))
        assert len(items) == 4  # original unchanged


# ===========================================================================
# process_results
# ===========================================================================


class TestProcessResults:
    """Unit tests for process_results."""

    # --- cap ---

    def test_more_than_cap_items_returns_exactly_cap(self) -> None:
        """25 complete candidates → result count capped at RESULTS_CAP (20)."""
        candidates = _make_items(25)
        response = process_results(candidates)
        assert response["status"] == "ok"
        assert len(response["results"]) == RESULTS_CAP

    def test_exactly_cap_items_returns_all(self) -> None:
        """Exactly 20 complete candidates → all 20 returned."""
        candidates = _make_items(RESULTS_CAP)
        response = process_results(candidates)
        assert response["status"] == "ok"
        assert len(response["results"]) == RESULTS_CAP

    def test_fewer_than_cap_items_returns_all(self) -> None:
        """5 complete candidates → all 5 returned."""
        candidates = _make_items(5)
        response = process_results(candidates)
        assert response["status"] == "ok"
        assert len(response["results"]) == 5

    # --- sorting ---

    def test_results_sorted_by_score_descending(self) -> None:
        """Results must be in descending score order."""
        # Provide items out of score order on purpose
        candidates = [
            _make_item(id="low", score=0.3),
            _make_item(id="high", score=0.9),
            _make_item(id="mid", score=0.6),
        ]
        response = process_results(candidates)
        scores = [r["score"] for r in response["results"]]
        assert scores == sorted(scores, reverse=True)
        assert response["results"][0]["id"] == "high"
        assert response["results"][-1]["id"] == "low"

    def test_monotone_non_increasing_score_invariant(self) -> None:
        """score[i] >= score[i+1] for all consecutive pairs in returned results."""
        candidates = _make_items(15, base_score=0.99)
        # Reverse to ensure sorting logic is actually exercised
        candidates_shuffled = candidates[::-1]
        response = process_results(candidates_shuffled)
        results = response["results"]
        for i in range(len(results) - 1):
            assert results[i]["score"] >= results[i + 1]["score"], (
                f"Score not non-increasing at index {i}: "
                f"{results[i]['score']} < {results[i + 1]['score']}"
            )

    # --- citation filtering ---

    def test_incomplete_citation_items_excluded(self) -> None:
        """Items with incomplete citations must not appear in results."""
        complete = _make_item(id="good", score=0.8, page=10, section=None)
        incomplete = _make_item(id="bad", score=0.95, page=None, section=None)
        response = process_results([complete, incomplete])
        assert response["status"] == "ok"
        ids = [r["id"] for r in response["results"]]
        assert "good" in ids
        assert "bad" not in ids

    def test_mixed_citations_only_complete_returned(self) -> None:
        """Mix of complete/incomplete → only complete items in output."""
        items = [
            _make_item(id="ok1", score=0.9, page=1),
            _make_item(id="bad1", score=1.0, page=None, section=None),
            _make_item(id="ok2", score=0.7, page=None, section="3.1"),
            _make_item(id="bad2", score=0.85, source_file="", page=5),
            _make_item(id="ok3", score=0.5, page=99),
        ]
        response = process_results(items)
        assert response["status"] == "ok"
        ids = {r["id"] for r in response["results"]}
        assert ids == {"ok1", "ok2", "ok3"}

    def test_all_incomplete_citations_no_filter_returns_not_found(self) -> None:
        """All candidates with incomplete citations, no filter → not_found."""
        candidates = [
            _make_item(id="x", page=None, section=None),
            _make_item(id="y", source_file=""),
        ]
        response = process_results(candidates)
        assert response["status"] == "not_found"
        assert response["message"] == "현재 index에서 확인 불가"
        assert response["results"] == []

    # --- empty result responses ---

    def test_zero_results_no_filter_returns_not_found(self) -> None:
        """Empty candidates, no filter → not_found with Korean message (R4.6, R6.3)."""
        response = process_results([])
        assert response["status"] == "not_found"
        assert response["message"] == "현재 index에서 확인 불가"
        assert response["results"] == []

    def test_zero_results_with_tool_name_filter_returns_no_match(self) -> None:
        """Empty candidates, tool_name given → no_match with Korean message (R4.9)."""
        response = process_results([], tool_name="NonExistentTool")
        assert response["status"] == "no_match"
        assert response["message"] == "일치하는 객체 없음"
        assert response["results"] == []

    def test_zero_results_with_tool_version_filter_returns_no_match(self) -> None:
        """Empty candidates, tool_version given → no_match (R4.9)."""
        response = process_results([], tool_version="9.9.9")
        assert response["status"] == "no_match"
        assert response["message"] == "일치하는 객체 없음"
        assert response["results"] == []

    def test_zero_results_with_both_filters_returns_no_match(self) -> None:
        """Empty after both filters applied → no_match (R4.9)."""
        response = process_results([], tool_name="VCS", tool_version="2099.01")
        assert response["status"] == "no_match"
        assert response["message"] == "일치하는 객체 없음"
        assert response["results"] == []

    def test_candidates_exist_but_filtered_to_zero_by_tool_name_returns_no_match(
        self,
    ) -> None:
        """Candidates present but none match tool_name filter → no_match (R4.9)."""
        candidates = [_make_item(tool_name="Verdi")]
        response = process_results(candidates, tool_name="VCS")
        assert response["status"] == "no_match"
        assert response["message"] == "일치하는 객체 없음"

    # --- combined filter + cap + sort ---

    def test_tool_name_filter_reduces_results_before_cap(self) -> None:
        """Metadata filter applied before cap: only filtered items counted."""
        # 15 VCS items + 10 Verdi items = 25 total but only 15 VCS match
        vcs_items = [
            _make_item(id=f"vcs-{i}", tool_name="VCS", score=float(i))
            for i in range(15)
        ]
        verdi_items = [
            _make_item(id=f"verdi-{i}", tool_name="Verdi", score=float(i + 100))
            for i in range(10)
        ]
        response = process_results(vcs_items + verdi_items, tool_name="VCS")
        assert response["status"] == "ok"
        assert len(response["results"]) == 15
        assert all(r["metadata"]["tool_name"] == "VCS" for r in response["results"])

    def test_cap_applied_after_all_filtering(self) -> None:
        """When filtered count > 20, cap still applies."""
        # 25 VCS items, all with complete citations
        vcs_items = [
            _make_item(id=f"vcs-{i}", tool_name="VCS", score=float(i))
            for i in range(25)
        ]
        response = process_results(vcs_items, tool_name="VCS")
        assert response["status"] == "ok"
        assert len(response["results"]) == RESULTS_CAP

    def test_successful_response_has_status_ok_and_results_key(self) -> None:
        """Successful response must have 'status': 'ok' and 'results' list."""
        response = process_results([_make_item()])
        assert response["status"] == "ok"
        assert "results" in response
        assert isinstance(response["results"], list)

    def test_successful_response_has_no_message_key(self) -> None:
        """Successful response must NOT include a 'message' key."""
        response = process_results([_make_item()])
        assert "message" not in response

    # --- score tie-breaking stability ---

    def test_equal_scores_results_capped_correctly(self) -> None:
        """Even with equal scores, cap must not exceed RESULTS_CAP."""
        candidates = [_make_item(id=f"x-{i}", score=0.5) for i in range(30)]
        response = process_results(candidates)
        assert len(response["results"]) == RESULTS_CAP
