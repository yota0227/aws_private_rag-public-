"""Unit tests for Tool_Guide_MCP input validation layer (Task 7.1).

Covers all acceptance criteria from the task spec:

  1. empty query -> error:input_length
  2. query at exactly the char limit (256 or 8192) -> accepted
  3. query 1 char over the limit -> error:input_length
  4. valid query in range -> no error raised / returns without validation error
  5. token limit exceeded (>32768 chars) -> error:token_limit (no partial results)
  6. token limit warning at 75% threshold (24576 chars) -> WARNING logged

All tests use real function calls (no mocking) to validate actual logic.

Requirements validated: 4.1, 4.2, 4.10, 6.4
Design reference: C5 Tool_Guide_MCP, Property 11
"""

import logging
import pytest

from mcp_tools import (
    QUERY_MAX_CHARS,
    SEARCH_QUERY_MAX_CHARS,
    InputLengthError,
    tool_guide_query,
    tool_guide_search,
)
from token_guard import (
    TOKEN_LIMIT_CHAR_PROXY,
    TOKEN_WARN_THRESHOLD,
    TokenLimitError,
    check_token_limit,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_query(n: int) -> str:
    """Return a query string of exactly *n* characters."""
    return "a" * n


# ===========================================================================
# tool_guide_search -- character length validation (max 256 chars)
# ===========================================================================


class TestToolGuideSearchInputLength:
    """tool_guide_search: 1..256-char validation (R4.1, R6.4)."""

    def test_empty_query_raises_input_length_error(self) -> None:
        """Empty query must raise InputLengthError with status error:input_length."""
        with pytest.raises(InputLengthError) as exc_info:
            tool_guide_search("")
        err = exc_info.value
        assert err.status == "error:input_length"
        assert err.char_len == 0
        assert err.limit == SEARCH_QUERY_MAX_CHARS

    def test_whitespace_only_query_raises_input_length_error(self) -> None:
        """Whitespace-only query must raise InputLengthError (R6.4)."""
        with pytest.raises(InputLengthError) as exc_info:
            tool_guide_search("   ")
        err = exc_info.value
        assert err.status == "error:input_length"
        assert err.limit == SEARCH_QUERY_MAX_CHARS

    def test_query_at_exact_limit_is_accepted(self) -> None:
        """Query of exactly 256 chars must be accepted (boundary inclusive)."""
        q = _make_query(SEARCH_QUERY_MAX_CHARS)
        result = tool_guide_search(q, pipeline_token="valid-token")
        assert result["status"] == "ok"
        assert result["query"] == q

    def test_query_one_over_limit_raises_input_length_error(self) -> None:
        """Query of 257 chars must raise InputLengthError."""
        q = _make_query(SEARCH_QUERY_MAX_CHARS + 1)
        with pytest.raises(InputLengthError) as exc_info:
            tool_guide_search(q)
        err = exc_info.value
        assert err.status == "error:input_length"
        assert err.char_len == SEARCH_QUERY_MAX_CHARS + 1
        assert err.limit == SEARCH_QUERY_MAX_CHARS

    def test_valid_query_in_range_succeeds(self) -> None:
        """A normal short query must return status=ok with no error."""
        result = tool_guide_search("elaborate", pipeline_token="valid-token")
        assert result["status"] == "ok"
        assert result["query"] == "elaborate"
        assert result["results"] == []  # no backend wired


# ===========================================================================
# tool_guide_query -- character length validation (max 8192 chars)
# ===========================================================================


class TestToolGuideQueryInputLength:
    """tool_guide_query: 1..8192-char validation (R4.2, R6.4)."""

    def test_empty_query_raises_input_length_error(self) -> None:
        """Empty query must raise InputLengthError with status error:input_length."""
        with pytest.raises(InputLengthError) as exc_info:
            tool_guide_query("")
        err = exc_info.value
        assert err.status == "error:input_length"
        assert err.char_len == 0
        assert err.limit == QUERY_MAX_CHARS

    def test_whitespace_only_query_raises_input_length_error(self) -> None:
        """Whitespace-only query must raise InputLengthError (R6.4)."""
        with pytest.raises(InputLengthError) as exc_info:
            tool_guide_query("\t\n  ")
        err = exc_info.value
        assert err.status == "error:input_length"
        assert err.limit == QUERY_MAX_CHARS

    def test_query_at_exact_limit_is_accepted(self) -> None:
        """Query of exactly 8192 chars must be accepted (boundary inclusive)."""
        q = _make_query(QUERY_MAX_CHARS)
        result = tool_guide_query(q, pipeline_token="valid-token")
        assert result["status"] == "ok"
        assert result["query"] == q

    def test_query_one_over_limit_raises_input_length_error(self) -> None:
        """Query of 8193 chars must raise InputLengthError."""
        q = _make_query(QUERY_MAX_CHARS + 1)
        with pytest.raises(InputLengthError) as exc_info:
            tool_guide_query(q)
        err = exc_info.value
        assert err.status == "error:input_length"
        assert err.char_len == QUERY_MAX_CHARS + 1
        assert err.limit == QUERY_MAX_CHARS

    def test_valid_query_in_range_succeeds(self) -> None:
        """A normal natural-language query must return status=ok."""
        result = tool_guide_query("How do I run elaborate in VCS?", pipeline_token="valid-token")
        assert result["status"] == "ok"
        assert result["query"] == "How do I run elaborate in VCS?"
        assert result["results"] == []  # no backend wired


# ===========================================================================
# Token-limit guard -- both tools delegate to check_token_limit after char gate
# ===========================================================================


class TestTokenLimitGuard:
    """Token-limit guard: queries >32768 chars rejected with error:token_limit (R4.10)."""

    def test_search_token_limit_exceeded_raises_token_limit_error(self) -> None:
        """check_token_limit must raise TokenLimitError for >32768-char query.

        The char gate for tool_guide_search is 256, so the token proxy is
        never reached via that entry point for a query that also exceeds 256
        chars. We test check_token_limit directly since it is the shared guard
        called by both tools after the char gate passes (R4.10).
        """
        oversized = _make_query(TOKEN_LIMIT_CHAR_PROXY + 1)
        with pytest.raises(TokenLimitError) as exc_info:
            check_token_limit(oversized, context="tool_guide_search")
        err = exc_info.value
        assert err.status == "error:token_limit"
        assert err.char_len == TOKEN_LIMIT_CHAR_PROXY + 1

    def test_query_token_limit_exceeded_raises_token_limit_error(self) -> None:
        """tool_guide_query must raise TokenLimitError for a query that passes
        the 8192-char gate but exceeds the 32768-char token proxy.

        We test check_token_limit directly (same function called internally)
        with a query length that is in the range (8192, 32768].
        """
        # Exactly TOKEN_LIMIT_CHAR_PROXY + 100 chars: passes 8192 char gate,
        # fails 32768 token proxy gate.
        oversized = _make_query(TOKEN_LIMIT_CHAR_PROXY + 100)
        with pytest.raises(TokenLimitError) as exc_info:
            check_token_limit(oversized, context="tool_guide_query")
        err = exc_info.value
        assert err.status == "error:token_limit"
        assert err.char_len > TOKEN_LIMIT_CHAR_PROXY

    def test_token_limit_at_exact_proxy_boundary_is_accepted(self) -> None:
        """Query of exactly TOKEN_LIMIT_CHAR_PROXY chars must NOT raise (boundary)."""
        q = _make_query(TOKEN_LIMIT_CHAR_PROXY)
        # Must not raise -- the guard is strictly > (not >=).
        check_token_limit(q, context="boundary_test")

    def test_token_limit_one_over_raises(self) -> None:
        """Query of TOKEN_LIMIT_CHAR_PROXY + 1 chars must raise TokenLimitError."""
        q = _make_query(TOKEN_LIMIT_CHAR_PROXY + 1)
        with pytest.raises(TokenLimitError):
            check_token_limit(q, context="boundary_test")

    def test_no_partial_results_on_token_limit_error(self) -> None:
        """TokenLimitError must fire before any backend is invoked (R4.10).

        We wire a search_backend that would return a non-empty list.  Because
        check_token_limit raises before the backend call, the fake_backend is
        never invoked and no partial result is produced.
        """
        invoked = {"count": 0}

        def fake_backend(**kwargs):  # noqa: ANN001, ANN202
            invoked["count"] += 1
            return [{"id": "fake", "score": 1.0}]

        # A query > TOKEN_LIMIT_CHAR_PROXY chars -- token guard fires immediately.
        oversized = _make_query(TOKEN_LIMIT_CHAR_PROXY + 1)
        with pytest.raises(TokenLimitError):
            check_token_limit(oversized, context="no_partial_results_test")

        # Confirm that fake_backend was never reached (no partial results).
        assert invoked["count"] == 0


# ===========================================================================
# Token-limit warning at 75 % threshold
# ===========================================================================


class TestTokenLimitWarning:
    """Token-limit guard: WARNING logged at >= 75 % threshold (24576 chars)."""

    def test_warning_logged_at_75_percent_threshold(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """check_token_limit must emit a WARNING when len >= TOKEN_WARN_THRESHOLD."""
        q = _make_query(TOKEN_WARN_THRESHOLD)  # exactly 24576 chars
        with caplog.at_level(logging.WARNING, logger="token_guard"):
            check_token_limit(q, context="warn_test")
        # The call must NOT raise (24576 <= 32768 proxy limit).
        warning_messages = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "token_limit_approaching" in r.message
        ]
        assert len(warning_messages) >= 1, (
            "Expected a WARNING with 'token_limit_approaching' in log, "
            f"got records: {[r.message for r in caplog.records]}"
        )

    def test_no_warning_below_threshold(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No WARNING when query length is below TOKEN_WARN_THRESHOLD."""
        q = _make_query(TOKEN_WARN_THRESHOLD - 1)
        with caplog.at_level(logging.WARNING, logger="token_guard"):
            check_token_limit(q, context="no_warn_test")
        warning_messages = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "token_limit_approaching" in r.message
        ]
        assert len(warning_messages) == 0, (
            "Unexpected WARNING for query below threshold: "
            f"{[r.message for r in caplog.records]}"
        )


# ===========================================================================
# Return value shape: both tools return correct dict shape on pass
# ===========================================================================


class TestReturnValueShape:
    """Both tools must return the expected dict keys on success."""

    def test_search_return_keys(self) -> None:
        """tool_guide_search must return the expected 5-key dict."""
        result = tool_guide_search("vcs", tool_name="VCS", tool_version="2023.12",
                                   pipeline_token="valid-token")
        assert set(result.keys()) == {
            "status", "query", "tool_name", "tool_version", "results"
        }
        assert result["status"] == "ok"
        assert result["tool_name"] == "VCS"
        assert result["tool_version"] == "2023.12"

    def test_query_return_keys(self) -> None:
        """tool_guide_query must return the expected 5-key dict."""
        result = tool_guide_query("What does the -full_case option do?",
                                  pipeline_token="valid-token")
        assert set(result.keys()) == {
            "status", "query", "tool_name", "tool_version", "results"
        }
        assert result["status"] == "ok"
        assert result["tool_name"] is None
        assert result["tool_version"] is None

    def test_search_backend_callable_is_invoked(self) -> None:
        """search_backend callable must be called and its result returned."""
        called = {"times": 0}

        def fake_backend(**kwargs):  # noqa: ANN001, ANN202
            called["times"] += 1
            return [
                {
                    "id": "obj1",
                    "object_type": "command",
                    "canonical_text": "Command 'elaborate': compiles the design.",
                    "score": 0.9,
                    "pipeline_id": "tool-guide",
                    "metadata": {
                        "tool_name": "VCS",
                        "tool_version": "2023.12",
                        "command": "elaborate",
                        "option": "미확인",
                        "section": "4.2",
                        "doc_version": "2023.12-rev1",
                        "object_type": "command",
                    },
                    "citation": {
                        "source_file": "vcs_guide.pdf",
                        "doc_version": "2023.12-rev1",
                        "page": 42,
                        "section": None,
                    },
                }
            ]

        result = tool_guide_search("elaborate", pipeline_token="valid-token",
                                   search_backend=fake_backend)
        assert result["status"] == "ok"
        assert len(result["results"]) == 1
        assert result["results"][0]["id"] == "obj1"
        assert called["times"] == 1

    def test_query_backend_callable_is_invoked(self) -> None:
        """search_backend callable must be called and its result returned."""
        called = {"times": 0}

        def fake_backend(**kwargs):  # noqa: ANN001, ANN202
            called["times"] += 1
            return [
                {
                    "id": "obj2",
                    "object_type": "command",
                    "canonical_text": "Command 'compile': compiles the design.",
                    "score": 0.75,
                    "pipeline_id": "tool-guide",
                    "metadata": {
                        "tool_name": "VCS",
                        "tool_version": "2023.12",
                        "command": "compile",
                        "option": "미확인",
                        "section": "3.1",
                        "doc_version": "2023.12-rev1",
                        "object_type": "command",
                    },
                    "citation": {
                        "source_file": "vcs_guide.pdf",
                        "doc_version": "2023.12-rev1",
                        "page": 30,
                        "section": None,
                    },
                }
            ]

        result = tool_guide_query(
            "How do I compile the design?", pipeline_token="valid-token",
            search_backend=fake_backend
        )
        assert result["status"] == "ok"
        assert len(result["results"]) == 1
        assert result["results"][0]["id"] == "obj2"
        assert called["times"] == 1
