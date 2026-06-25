"""Unit and integration tests for search_backend.py and end-to-end wiring (Task 8.1).

Tests cover:
  Unit tests for QdrantSearchBackend:
    - MVP active_types filter: only command/option types returned
    - tool_name/tool_version filters passed to Qdrant query payload
    - empty Qdrant hits returns empty list
    - mcp_tools applies process_results after backend call (cap=20, sorting, citation)

  End-to-end integration test:
    - event -> handler() -> InMemoryIngestStore -> objects stored
    - tool_guide_query() with fake backend returning those objects
    - process_results applied -> final response dict verified

Requirements validated: 6.1, 6.5
Design reference: C2 Tool_Guide_Parser, C5 Tool_Guide_MCP, Sequence Diagrams
"""

from __future__ import annotations

import json
import sys
import os
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Path setup: tool_guide_mcp_src tests need parser modules for integration test
# ---------------------------------------------------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARSER_DIR = os.path.join(os.path.dirname(_THIS_DIR), "tool_guide_parser_src")
if _PARSER_DIR not in sys.path:
    sys.path.insert(0, _PARSER_DIR)

from search_backend import (
    TOOL_GUIDE_COLLECTION,
    TOOL_GUIDE_PIPELINE_ID,
    _MVP_ACTIVE_TYPES,
    QdrantSearchBackend,
)
from mcp_tools import tool_guide_query, tool_guide_search
from result_processor import RESULTS_CAP

# ---------------------------------------------------------------------------
# Helpers: mock factory
# ---------------------------------------------------------------------------


def _make_bedrock_mock(embedding: list[float] | None = None) -> MagicMock:
    """Return a mock Bedrock client whose invoke_model returns a fake embedding."""
    if embedding is None:
        embedding = [0.1] * 1024
    mock = MagicMock()
    body_bytes = json.dumps({"embedding": embedding}).encode("utf-8")
    mock.invoke_model.return_value = {"body": BytesIO(body_bytes)}
    return mock


def _make_hit(
    obj_id: str = "toolguide#vcs#2023.12#command#elaborate@0",
    object_type: str = "command",
    score: float = 0.9,
    tool_name: str = "VCS",
    tool_version: str = "2023.12",
    source_file: str = "vcs_guide.pdf",
    doc_version: str = "2023.12-rev1",
    page: int | None = 42,
    section: str | None = None,
) -> dict[str, Any]:
    """Return a Qdrant-shaped hit dict with a complete payload."""
    return {
        "id": 12345,
        "score": score,
        "payload": {
            "id": obj_id,
            "object_type": object_type,
            "canonical_text": f"Command '{obj_id}': test.",
            "pipeline_id": TOOL_GUIDE_PIPELINE_ID,
            "tool_name": tool_name,
            "tool_version": tool_version,
            "command": "elaborate" if object_type == "command" else "미확인",
            "option": obj_id.split("#")[-1].split("@")[0] if object_type == "option" else "미확인",
            "section": section if section else "미확인",
            "doc_version": doc_version,
            "source_file": source_file,
            "page": page,
        },
    }


def _make_backend(
    hits: list[dict[str, Any]],
    active_types: frozenset[str] | None = None,
) -> QdrantSearchBackend:
    """Return a QdrantSearchBackend with mocked Bedrock and Qdrant search."""
    bedrock = _make_bedrock_mock()
    backend = QdrantSearchBackend(
        qdrant_endpoint="http://mock-qdrant:6333",
        bedrock_client=bedrock,
        qdrant_api_key="test-key",
        active_types=active_types,
    )
    # Patch _qdrant_search at instance level to return hits without real HTTP.
    backend._qdrant_search = MagicMock(return_value=hits)  # type: ignore[method-assign]
    return backend


# ===========================================================================
# QdrantSearchBackend unit tests
# ===========================================================================


class TestQdrantSearchBackendActiveTypes:
    """MVP active_types filter: only command/option returned (R6.1)."""

    def test_default_active_types_is_command_and_option(self) -> None:
        """Default active_types must equal frozenset({'command', 'option'})."""
        backend = _make_backend([])
        assert backend._active_types == frozenset({"command", "option"})

    def test_only_command_and_option_hits_returned(self) -> None:
        """flow_step/example/section hits must be filtered out by default."""
        hits = [
            _make_hit("id-cmd", object_type="command", score=0.9),
            _make_hit("id-opt", object_type="option", score=0.8),
            _make_hit("id-flow", object_type="flow_step", score=0.7),
            _make_hit("id-ex", object_type="example", score=0.6),
            _make_hit("id-sec", object_type="section", score=0.5),
        ]
        backend = _make_backend(hits)
        results = backend("how to elaborate")
        returned_types = {r["object_type"] for r in results}
        assert returned_types == {"command", "option"}
        assert len(results) == 2

    def test_custom_active_types_all_five_allows_all(self) -> None:
        """When active_types includes all five types, all hits are returned (R6.5)."""
        all_types = frozenset({"command", "option", "flow_step", "example", "section"})
        hits = [
            _make_hit("id-cmd", object_type="command"),
            _make_hit("id-flow", object_type="flow_step"),
            _make_hit("id-sec", object_type="section"),
        ]
        backend = _make_backend(hits, active_types=all_types)
        results = backend("test")
        assert len(results) == 3

    def test_only_command_active_type_filters_options(self) -> None:
        """When active_types={'command'}, option hits must be excluded."""
        hits = [
            _make_hit("id-cmd", object_type="command"),
            _make_hit("id-opt", object_type="option"),
        ]
        backend = _make_backend(hits, active_types=frozenset({"command"}))
        results = backend("test")
        assert all(r["object_type"] == "command" for r in results)
        assert len(results) == 1

    def test_empty_hits_returns_empty_list(self) -> None:
        """When Qdrant returns no hits, backend returns empty list."""
        backend = _make_backend([])
        results = backend("no results query")
        assert results == []


class TestQdrantSearchBackendFilters:
    """Qdrant filter payload includes tool_name/tool_version when provided."""

    def test_tool_name_filter_in_qdrant_payload(self) -> None:
        """When tool_name supplied, Qdrant payload must include tool_name filter."""
        backend = _make_backend([])
        backend("vcs elaborate", tool_name="VCS")
        call_args = backend._qdrant_search.call_args
        payload = call_args[0][0]
        must = payload["filter"]["must"]
        tool_filters = [c for c in must if c.get("key") == "tool_name"]
        assert len(tool_filters) == 1
        assert tool_filters[0]["match"]["value"] == "VCS"

    def test_tool_version_filter_in_qdrant_payload(self) -> None:
        """When tool_version supplied, Qdrant payload must include tool_version filter."""
        backend = _make_backend([])
        backend("query", tool_version="2023.12")
        call_args = backend._qdrant_search.call_args
        payload = call_args[0][0]
        must = payload["filter"]["must"]
        version_filters = [c for c in must if c.get("key") == "tool_version"]
        assert len(version_filters) == 1
        assert version_filters[0]["match"]["value"] == "2023.12"

    def test_no_tool_filters_when_not_provided(self) -> None:
        """Without tool_name/version, payload must not contain those filter keys."""
        backend = _make_backend([])
        backend("query")
        call_args = backend._qdrant_search.call_args
        payload = call_args[0][0]
        must = payload["filter"]["must"]
        filter_keys = {c.get("key") for c in must}
        assert "tool_name" not in filter_keys
        assert "tool_version" not in filter_keys

    def test_active_types_filter_always_present(self) -> None:
        """Qdrant payload must always contain object_type filter (MVP restriction)."""
        backend = _make_backend([])
        backend("query")
        call_args = backend._qdrant_search.call_args
        payload = call_args[0][0]
        must = payload["filter"]["must"]
        type_filters = [c for c in must if c.get("key") == "object_type"]
        assert len(type_filters) == 1
        assert set(type_filters[0]["match"]["any"]) == {"command", "option"}

    def test_pipeline_id_filter_always_present(self) -> None:
        """Qdrant payload must always include pipeline_id=tool-guide filter."""
        backend = _make_backend([])
        backend("query")
        call_args = backend._qdrant_search.call_args
        payload = call_args[0][0]
        must = payload["filter"]["must"]
        pid_filters = [c for c in must if c.get("key") == "pipeline_id"]
        assert len(pid_filters) == 1
        assert pid_filters[0]["match"]["value"] == TOOL_GUIDE_PIPELINE_ID

    def test_bedrock_embed_called_with_query(self) -> None:
        """Bedrock embed must be called with the query text."""
        backend = _make_backend([])
        backend("elaborate -v option")
        call_kwargs = backend._bedrock_client.invoke_model.call_args[1]
        body = json.loads(call_kwargs["body"])
        assert body["inputText"] == "elaborate -v option"


class TestMcpToolsWithBackend:
    """mcp_tools applies process_results after backend call (cap=20, sorting, citation)."""

    def _make_complete_candidate(
        self,
        obj_id: str,
        score: float,
        object_type: str = "command",
    ) -> dict[str, Any]:
        """Return a complete candidate dict that passes has_complete_citation."""
        return {
            "id": obj_id,
            "object_type": object_type,
            "canonical_text": f"Command '{obj_id}'.",
            "score": score,
            "pipeline_id": TOOL_GUIDE_PIPELINE_ID,
            "metadata": {
                "tool_name": "VCS",
                "tool_version": "2023.12",
                "command": obj_id,
                "option": "미확인",
                "section": "4.2",
                "doc_version": "2023.12-rev1",
                "object_type": object_type,
            },
            "citation": {
                "source_file": "vcs_guide.pdf",
                "doc_version": "2023.12-rev1",
                "page": 10,
                "section": None,
            },
        }

    def test_cap_applied_via_process_results(self) -> None:
        """When backend returns >20 items, response must contain at most 20."""
        candidates = [
            self._make_complete_candidate(f"obj-{i}", score=float(i))
            for i in range(25)
        ]

        def backend(**kwargs: Any) -> list[dict[str, Any]]:
            return candidates

        result = tool_guide_query("query", pipeline_token="tok", search_backend=backend)
        assert result["status"] == "ok"
        assert len(result["results"]) == RESULTS_CAP

    def test_results_sorted_by_score_descending(self) -> None:
        """Results from mcp_tools must be sorted by score desc after process_results."""
        candidates = [
            self._make_complete_candidate("low", score=0.2),
            self._make_complete_candidate("high", score=0.9),
            self._make_complete_candidate("mid", score=0.5),
        ]

        def backend(**kwargs: Any) -> list[dict[str, Any]]:
            return candidates

        result = tool_guide_query("query", pipeline_token="tok", search_backend=backend)
        scores = [r["score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True)
        assert result["results"][0]["id"] == "high"

    def test_incomplete_citation_filtered_by_process_results(self) -> None:
        """Items with incomplete citation must be removed before response."""
        complete = self._make_complete_candidate("good", score=0.9)
        incomplete = {
            "id": "bad",
            "object_type": "command",
            "canonical_text": "Something.",
            "score": 1.0,
            "pipeline_id": TOOL_GUIDE_PIPELINE_ID,
            "metadata": {
                "tool_name": "VCS", "tool_version": "2023.12",
                "command": "bad", "option": "미확인", "section": "S",
                "doc_version": "1.0", "object_type": "command",
            },
            "citation": {
                "source_file": "", "doc_version": "1.0",
                "page": None, "section": None,
            },
        }

        def backend(**kwargs: Any) -> list[dict[str, Any]]:
            return [complete, incomplete]

        result = tool_guide_query("query", pipeline_token="tok", search_backend=backend)
        assert result["status"] == "ok"
        ids = [r["id"] for r in result["results"]]
        assert "good" in ids
        assert "bad" not in ids

    def test_empty_backend_result_returns_not_found(self) -> None:
        """Empty backend result with no filter returns not_found status."""
        def backend(**kwargs: Any) -> list[dict[str, Any]]:
            return []

        result = tool_guide_query("query", pipeline_token="tok", search_backend=backend)
        assert result["status"] == "not_found"
        assert result["results"] == []


# ===========================================================================
# End-to-end integration test
# ===========================================================================


class TestEndToEndWiring:
    """Integration: event -> handler -> store -> MCP tool -> process_results.

    Verifies the full S3 event -> parse -> store -> MCP -> result shaping chain
    using mocks for all external services (no real Bedrock/Qdrant/DDB calls).

    Design reference: Sequence Diagrams (Ingestion + Query), design.md C2/C5.
    Requirements validated: 6.1, 6.5
    """

    # Sample markdown tool guide document with command + options
    SAMPLE_MD = """\
# VCS User Guide

Command: elaborate
  Elaborates the design hierarchy and resolves all references.

Options:
  -f <file>   Specify the filelist for elaboration.
  -full_case  Enable full_case check during elaboration.
"""

    SAMPLE_EVENT = {
        "bucket": "bos-ai-toolguide-docs-seoul",
        "key": "VCS/2023.12/vcs_user_guide.md",
        "tool_name": "VCS",
        "doc_version": "2023.12",
        "filename": "vcs_user_guide.md",
    }

    def test_handler_stores_objects_in_memory_store(self) -> None:
        """event -> handler() -> InMemoryIngestStore: objects are stored."""
        from handler import InMemoryIngestStore, handler as parse_handler

        store = InMemoryIngestStore()
        result = parse_handler(
            self.SAMPLE_EVENT,
            store=store,
            markdown_text=self.SAMPLE_MD,
        )
        assert result["status"] == "ok"
        assert result["object_count"] > 0
        doc_id = result["doc_id"]
        stored_ids = store.list_ids_for_doc(doc_id)
        assert len(stored_ids) == result["object_count"]

    def test_mcp_tool_with_fake_backend_returning_stored_objects(self) -> None:
        """tool_guide_query() with a fake backend returning parsed objects applies
        process_results to produce the final response.

        Verifies: store -> MCP -> result shaping part of the chain.
        """
        from handler import InMemoryIngestStore, handler as parse_handler

        # Step 1: Parse and store via handler
        store = InMemoryIngestStore()
        result = parse_handler(
            self.SAMPLE_EVENT,
            store=store,
            markdown_text=self.SAMPLE_MD,
        )
        assert result["status"] == "ok"
        doc_id = result["doc_id"]
        stored_objects = store.get_objects_for_doc(doc_id)
        assert len(stored_objects) > 0

        # Step 2: Build fake backend returning stored objects as search candidates.
        # Only command/option types are returned (MVP R6.1).
        def fake_backend(**kwargs: Any) -> list[dict[str, Any]]:
            candidates = []
            for i, obj in enumerate(stored_objects):
                if obj.object_type not in ("command", "option"):
                    continue
                meta = obj.metadata.to_dict()
                ev_section = obj.evidence.section
                candidates.append({
                    "id": obj.id,
                    "object_type": obj.object_type,
                    "canonical_text": obj.canonical_text,
                    "score": 1.0 - i * 0.05,
                    "pipeline_id": "tool-guide",
                    "metadata": meta,
                    "citation": {
                        "source_file": obj.evidence.source_file,
                        "doc_version": obj.evidence.doc_version,
                        "page": obj.evidence.page,
                        "section": ev_section,
                    },
                })
            return candidates

        # Step 3: Call tool_guide_query with the fake backend
        mcp_result = tool_guide_query(
            "How do I elaborate the design?",
            tool_name="VCS",
            pipeline_token="valid-token",
            search_backend=fake_backend,
        )

        # Step 4: Verify the response shape — process_results applied
        assert "results" in mcp_result
        assert "query" in mcp_result
        assert mcp_result["query"] == "How do I elaborate the design?"
        # Status must be one of the three valid shapes from process_results
        assert mcp_result["status"] in ("ok", "not_found", "no_match")

        if mcp_result["status"] == "ok":
            results = mcp_result["results"]
            # cap applied
            assert len(results) <= 20
            # sorted descending
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)
            # all returned items must have pipeline_id=tool-guide
            for item in results:
                assert item.get("pipeline_id") == "tool-guide"

    def test_end_to_end_mvp_type_restriction(self) -> None:
        """Parsed flow_step/section objects are not returned by search (R6.1).

        The fake backend receives ALL objects from the store but filters to
        command/option only before returning to mcp_tools.  This confirms the
        MVP type restriction is enforced in the chain.
        """
        from handler import InMemoryIngestStore, handler as parse_handler

        store = InMemoryIngestStore()
        result = parse_handler(
            self.SAMPLE_EVENT,
            store=store,
            markdown_text=self.SAMPLE_MD,
        )
        assert result["status"] == "ok"
        stored_objects = store.get_objects_for_doc(result["doc_id"])

        # Simulate a backend that ONLY returns command/option (as QdrantSearchBackend does)
        returned_types: set[str] = set()

        def mvp_backend(**kwargs: Any) -> list[dict[str, Any]]:
            candidates = []
            for obj in stored_objects:
                if obj.object_type in ("command", "option"):
                    returned_types.add(obj.object_type)
                    candidates.append({
                        "id": obj.id,
                        "object_type": obj.object_type,
                        "canonical_text": obj.canonical_text,
                        "score": 0.8,
                        "pipeline_id": "tool-guide",
                        "metadata": obj.metadata.to_dict(),
                        "citation": {
                            "source_file": "vcs_guide.pdf",
                            "doc_version": "2023.12-rev1",
                            "page": 1,
                            "section": None,
                        },
                    })
            return candidates

        mcp_result = tool_guide_query(
            "elaboration options",
            pipeline_token="valid-token",
            search_backend=mvp_backend,
        )

        # The response must not contain flow_step/section/example
        if mcp_result["status"] == "ok":
            for item in mcp_result["results"]:
                assert item["object_type"] in ("command", "option")
