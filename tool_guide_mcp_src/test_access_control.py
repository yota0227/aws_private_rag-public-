"""Unit tests for access_control module (Task 7.2).

Covers all acceptance criteria from the task spec:

  1. check_pipeline_access(None) → AccessDeniedError
  2. check_pipeline_access("") → AccessDeniedError
  3. check_pipeline_access("valid-token") → no error
  4. tool_guide_search with no token → {"error": "error:access_denied"}, results == []
  5. tool_guide_query with no token → {"error": "error:access_denied"}, results == []
  6. tool_guide_search with valid token + fake backend → results returned, all pipeline_id == "tool-guide"
  7. assert_no_tool_name_overlap() passes
  8. TOOL_GUIDE_TOOL_NAMES ∩ RTL_TOOL_NAMES == ∅
  9. PIPELINE_ID == "tool-guide" (R5.3 constant check)

Requirements validated: 5.2, 5.3, 5.4, 5.5, 5.6
Design reference: C5 Tool_Guide_MCP, C6 접근 경계, Property 12
"""

import pytest

from access_control import (
    PIPELINE_ID,
    RTL_TOOL_NAMES,
    TOOL_GUIDE_TOOL_NAMES,
    AccessDeniedError,
    assert_no_tool_name_overlap,
    check_pipeline_access,
)
from mcp_tools import tool_guide_query, tool_guide_search


# ===========================================================================
# check_pipeline_access: unit tests
# ===========================================================================


class TestCheckPipelineAccess:
    """check_pipeline_access: MVP gate — None/empty → denied, non-empty → granted."""

    def test_none_token_raises_access_denied(self) -> None:
        """None token must raise AccessDeniedError (R5.4, R5.5)."""
        with pytest.raises(AccessDeniedError) as exc_info:
            check_pipeline_access(None)
        err = exc_info.value
        assert err.status == "error:access_denied"
        assert isinstance(err, PermissionError)

    def test_empty_string_token_raises_access_denied(self) -> None:
        """Empty string token must raise AccessDeniedError."""
        with pytest.raises(AccessDeniedError) as exc_info:
            check_pipeline_access("")
        err = exc_info.value
        assert err.status == "error:access_denied"

    def test_whitespace_only_token_raises_access_denied(self) -> None:
        """Whitespace-only token has no information and must be rejected."""
        with pytest.raises(AccessDeniedError) as exc_info:
            check_pipeline_access("   ")
        err = exc_info.value
        assert err.status == "error:access_denied"

    def test_valid_token_does_not_raise(self) -> None:
        """Non-empty string token must be accepted without exception (MVP policy)."""
        # Should not raise any exception
        check_pipeline_access("valid-token")

    def test_arbitrary_non_empty_token_does_not_raise(self) -> None:
        """Any non-empty token string must be accepted (MVP: no cryptographic check)."""
        check_pipeline_access("t")
        check_pipeline_access("token-abc-123")
        check_pipeline_access("Bearer eyJhbGciOiJIUzI1NiJ9.example")


# ===========================================================================
# AccessDeniedError: exception contract
# ===========================================================================


class TestAccessDeniedError:
    """AccessDeniedError must be a PermissionError subclass with status attribute."""

    def test_is_permission_error_subclass(self) -> None:
        """AccessDeniedError must subclass PermissionError (design contract)."""
        exc = AccessDeniedError()
        assert isinstance(exc, PermissionError)

    def test_status_attribute(self) -> None:
        """status class attribute must be 'error:access_denied'."""
        assert AccessDeniedError.status == "error:access_denied"
        exc = AccessDeniedError()
        assert exc.status == "error:access_denied"

    def test_custom_message(self) -> None:
        """Custom message must be preserved."""
        exc = AccessDeniedError("custom message")
        assert "custom message" in str(exc)

    def test_default_message(self) -> None:
        """Default message must be non-empty."""
        exc = AccessDeniedError()
        assert str(exc)  # truthy — non-empty default message


# ===========================================================================
# tool_guide_search: access denied path
# ===========================================================================


class TestToolGuideSearchAccessDenied:
    """tool_guide_search: access-denied response when token is missing/empty."""

    def test_no_token_returns_access_denied_dict(self) -> None:
        """tool_guide_search with no token must return error:access_denied dict (R5.5)."""
        result = tool_guide_search("elaborate")  # pipeline_token defaults to None
        assert result.get("error") == "error:access_denied"
        assert result.get("results") == []
        assert "message" in result
        assert result["message"]  # non-empty message

    def test_empty_token_returns_access_denied_dict(self) -> None:
        """tool_guide_search with empty token must return error:access_denied."""
        result = tool_guide_search("elaborate", pipeline_token="")
        assert result.get("error") == "error:access_denied"
        assert result.get("results") == []

    def test_none_token_returns_access_denied_dict(self) -> None:
        """tool_guide_search with None token must return error:access_denied."""
        result = tool_guide_search("elaborate", pipeline_token=None)
        assert result.get("error") == "error:access_denied"
        assert result.get("results") == []

    def test_access_denied_backend_never_called(self) -> None:
        """Backend must NOT be invoked when access is denied (R5.5: no corpus exposure)."""
        invoked = {"count": 0}

        def spy_backend(**kwargs):  # noqa: ANN001, ANN202
            invoked["count"] += 1
            return []

        tool_guide_search("elaborate", pipeline_token=None, search_backend=spy_backend)
        assert invoked["count"] == 0, "Backend must not be called when access is denied"


# ===========================================================================
# tool_guide_query: access denied path
# ===========================================================================


class TestToolGuideQueryAccessDenied:
    """tool_guide_query: access-denied response when token is missing/empty."""

    def test_no_token_returns_access_denied_dict(self) -> None:
        """tool_guide_query with no token must return error:access_denied dict (R5.5)."""
        result = tool_guide_query("How do I run elaborate?")  # pipeline_token=None
        assert result.get("error") == "error:access_denied"
        assert result.get("results") == []
        assert "message" in result
        assert result["message"]  # non-empty message

    def test_empty_token_returns_access_denied_dict(self) -> None:
        """tool_guide_query with empty token must return error:access_denied."""
        result = tool_guide_query("How do I run elaborate?", pipeline_token="")
        assert result.get("error") == "error:access_denied"
        assert result.get("results") == []

    def test_none_token_returns_access_denied_dict(self) -> None:
        """tool_guide_query with None token must return error:access_denied."""
        result = tool_guide_query("How do I run elaborate?", pipeline_token=None)
        assert result.get("error") == "error:access_denied"
        assert result.get("results") == []

    def test_access_denied_backend_never_called(self) -> None:
        """Backend must NOT be invoked when access is denied (R5.5: no corpus exposure)."""
        invoked = {"count": 0}

        def spy_backend(**kwargs):  # noqa: ANN001, ANN202
            invoked["count"] += 1
            return []

        tool_guide_query("How do I run elaborate?", pipeline_token=None,
                         search_backend=spy_backend)
        assert invoked["count"] == 0, "Backend must not be called when access is denied"


# ===========================================================================
# tool_guide_search: valid token + fake backend → pipeline_id assertion
# ===========================================================================


class TestToolGuideSearchWithValidToken:
    """tool_guide_search: with valid token, results are returned and pipeline_id clean."""

    def test_valid_token_returns_results(self) -> None:
        """With a valid token and fake backend, results must be returned (R5.6)."""
        fake_results = [
            {
                "id": "toolguide#vcs#2023#command#elaborate",
                "object_type": "command",
                "canonical_text": "Command 'elaborate'.",
                "score": 0.95,
                "pipeline_id": "tool-guide",
                "metadata": {
                    "tool_name": "VCS", "tool_version": "2023.12",
                    "command": "elaborate", "option": "미확인",
                    "section": "4.2", "doc_version": "2023.12-rev1",
                    "object_type": "command",
                },
                "citation": {
                    "source_file": "vcs_guide.pdf",
                    "doc_version": "2023.12-rev1",
                    "page": 42,
                    "section": None,
                },
            },
            {
                "id": "toolguide#vcs#2023#option#full_case",
                "object_type": "option",
                "canonical_text": "Option '-full_case'.",
                "score": 0.88,
                "pipeline_id": "tool-guide",
                "metadata": {
                    "tool_name": "VCS", "tool_version": "2023.12",
                    "command": "elaborate", "option": "full_case",
                    "section": "4.2", "doc_version": "2023.12-rev1",
                    "object_type": "option",
                },
                "citation": {
                    "source_file": "vcs_guide.pdf",
                    "doc_version": "2023.12-rev1",
                    "page": 45,
                    "section": None,
                },
            },
        ]

        def fake_backend(**kwargs):  # noqa: ANN001, ANN202
            return fake_results

        result = tool_guide_search("elaborate", pipeline_token="valid-token",
                                   search_backend=fake_backend)
        assert result["status"] == "ok"
        assert len(result["results"]) == 2

    def test_all_results_have_tool_guide_pipeline_id(self) -> None:
        """All returned results must have pipeline_id == 'tool-guide' (R5.6)."""
        fake_results = [
            {
                "id": f"obj{i}", "object_type": "command",
                "canonical_text": f"Command 'cmd{i}'.",
                "score": 1.0 - i * 0.1, "pipeline_id": "tool-guide",
                "metadata": {
                    "tool_name": "VCS", "tool_version": "2023.12",
                    "command": f"cmd{i}", "option": "미확인",
                    "section": "S1", "doc_version": "1.0",
                    "object_type": "command",
                },
                "citation": {
                    "source_file": "guide.pdf", "doc_version": "1.0",
                    "page": i + 1, "section": None,
                },
            }
            for i in range(3)
        ]

        def fake_backend(**kwargs):  # noqa: ANN001, ANN202
            return fake_results

        result = tool_guide_search("vcs command", pipeline_token="valid-token",
                                   search_backend=fake_backend)
        assert result["status"] == "ok"
        for item in result["results"]:
            assert item["pipeline_id"] == "tool-guide"

    def test_rtl_pipeline_id_in_results_raises_assertion(self) -> None:
        """If backend returns rtl pipeline_id, _assert_pipeline_id_clean must raise."""
        rtl_contaminated = [
            {"id": "rtl-obj", "score": 0.9, "pipeline_id": "rtl"},
        ]

        def bad_backend(**kwargs):  # noqa: ANN001, ANN202
            return rtl_contaminated

        with pytest.raises(AssertionError, match="R5.6 violation"):
            tool_guide_search("vcs", pipeline_token="valid-token",
                              search_backend=bad_backend)

    def test_valid_token_query_returns_results(self) -> None:
        """tool_guide_query with valid token + fake backend must return results (R5.6)."""
        fake_results = [
            {
                "id": "toolguide#vcs#2023#command#compile",
                "object_type": "command",
                "canonical_text": "Command 'compile': compiles the design.",
                "score": 0.92,
                "pipeline_id": "tool-guide",
                "metadata": {
                    "tool_name": "VCS", "tool_version": "2023.12",
                    "command": "compile", "option": "미확인",
                    "section": "3.1", "doc_version": "2023.12-rev1",
                    "object_type": "command",
                },
                "citation": {
                    "source_file": "vcs_guide.pdf",
                    "doc_version": "2023.12-rev1",
                    "page": 30,
                    "section": None,
                },
            },
        ]

        def fake_backend(**kwargs):  # noqa: ANN001, ANN202
            return fake_results

        result = tool_guide_query("How do I compile the design?",
                                  pipeline_token="valid-token",
                                  search_backend=fake_backend)
        assert result["status"] == "ok"
        assert len(result["results"]) == 1
        assert result["results"][0]["pipeline_id"] == "tool-guide"


# ===========================================================================
# Tool name isolation: R5.2
# ===========================================================================


class TestToolNameIsolation:
    """Tool name sets must be disjoint (R5.2)."""

    def test_assert_no_tool_name_overlap_passes(self) -> None:
        """assert_no_tool_name_overlap() must not raise (R5.2)."""
        # Should not raise AssertionError
        assert_no_tool_name_overlap()

    def test_tool_guide_names_not_in_rtl_names(self) -> None:
        """TOOL_GUIDE_TOOL_NAMES ∩ RTL_TOOL_NAMES must be empty (R5.2)."""
        overlap = TOOL_GUIDE_TOOL_NAMES & RTL_TOOL_NAMES
        assert overlap == frozenset(), (
            f"Tool name overlap detected: {overlap!r}. "
            "Tool Guide and RTL tool names must be disjoint."
        )

    def test_tool_guide_search_not_in_rtl_names(self) -> None:
        """'tool_guide_search' must not appear in RTL_TOOL_NAMES."""
        assert "tool_guide_search" not in RTL_TOOL_NAMES

    def test_tool_guide_query_not_in_rtl_names(self) -> None:
        """'tool_guide_query' must not appear in RTL_TOOL_NAMES."""
        assert "tool_guide_query" not in RTL_TOOL_NAMES

    def test_tool_guide_names_contains_expected_tools(self) -> None:
        """TOOL_GUIDE_TOOL_NAMES must contain the two expected tool names."""
        assert "tool_guide_search" in TOOL_GUIDE_TOOL_NAMES
        assert "tool_guide_query" in TOOL_GUIDE_TOOL_NAMES


# ===========================================================================
# Pipeline identifier: R5.3
# ===========================================================================


class TestPipelineIdentifier:
    """PIPELINE_ID must be 'tool-guide' — unique, single value (R5.3)."""

    def test_pipeline_id_value(self) -> None:
        """PIPELINE_ID constant must equal 'tool-guide' (R5.3)."""
        assert PIPELINE_ID == "tool-guide"

    def test_pipeline_id_is_string(self) -> None:
        """PIPELINE_ID must be a string type."""
        assert isinstance(PIPELINE_ID, str)

    def test_pipeline_id_not_rtl(self) -> None:
        """PIPELINE_ID must differ from the RTL pipeline identifier."""
        assert PIPELINE_ID != "rtl"
        assert PIPELINE_ID != "rtl-knowledge-base"
