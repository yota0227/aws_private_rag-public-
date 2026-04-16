"""Tests for claim_utils module — validation, token estimation, splitting."""

from claim_utils import estimate_tokens, split_module_groups, validate_claim


def _valid_claim() -> dict:
    """Return a minimal valid claim dict."""
    return {
        "claim_id": "clm_tt_001",
        "module_name": "tt_noc_router",
        "topic": "NoC",
        "claim_type": "connectivity",
        "claim_text": "Router has 4 ports",
        "confidence_score": 0.95,
        "source_files": ["noc/tt_noc_router.sv"],
    }


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    """Tests for estimate_tokens."""

    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_none_input(self):
        assert estimate_tokens(None) == 0

    def test_short_text(self):
        assert estimate_tokens("abcd") == 1

    def test_longer_text(self):
        text = "a" * 400
        assert estimate_tokens(text) == 100

    def test_integer_input(self):
        assert estimate_tokens(123) == 0


# ---------------------------------------------------------------------------
# validate_claim
# ---------------------------------------------------------------------------

class TestValidateClaim:
    """Tests for validate_claim."""

    def test_valid_claim(self):
        is_valid, errors = validate_claim(_valid_claim())
        assert is_valid is True
        assert errors == []

    def test_missing_claim_id(self):
        claim = _valid_claim()
        del claim["claim_id"]
        is_valid, errors = validate_claim(claim)
        assert is_valid is False
        assert any("claim_id" in e for e in errors)

    def test_missing_multiple_fields(self):
        claim = _valid_claim()
        del claim["claim_id"]
        del claim["topic"]
        is_valid, errors = validate_claim(claim)
        assert is_valid is False
        assert len(errors) >= 2

    def test_invalid_claim_type(self):
        claim = _valid_claim()
        claim["claim_type"] = "invalid_type"
        is_valid, errors = validate_claim(claim)
        assert is_valid is False
        assert any("claim_type" in e for e in errors)

    def test_confidence_score_too_high(self):
        claim = _valid_claim()
        claim["confidence_score"] = 1.5
        is_valid, errors = validate_claim(claim)
        assert is_valid is False
        assert any("confidence_score" in e for e in errors)

    def test_confidence_score_negative(self):
        claim = _valid_claim()
        claim["confidence_score"] = -0.1
        is_valid, errors = validate_claim(claim)
        assert is_valid is False

    def test_confidence_score_boundary_zero(self):
        claim = _valid_claim()
        claim["confidence_score"] = 0.0
        is_valid, _ = validate_claim(claim)
        assert is_valid is True

    def test_confidence_score_boundary_one(self):
        claim = _valid_claim()
        claim["confidence_score"] = 1.0
        is_valid, _ = validate_claim(claim)
        assert is_valid is True

    def test_empty_source_files(self):
        claim = _valid_claim()
        claim["source_files"] = []
        is_valid, errors = validate_claim(claim)
        assert is_valid is False
        assert any("source_files" in e for e in errors)

    def test_none_input(self):
        is_valid, errors = validate_claim(None)
        assert is_valid is False

    def test_empty_dict(self):
        is_valid, errors = validate_claim({})
        assert is_valid is False


# ---------------------------------------------------------------------------
# split_module_groups
# ---------------------------------------------------------------------------

class TestSplitModuleGroups:
    """Tests for split_module_groups."""

    def test_empty_list(self):
        assert split_module_groups([]) == []

    def test_single_small_module(self):
        modules = [{"module_name": "a", "parsed_summary": "x" * 40}]
        result = split_module_groups(modules, max_tokens=100)
        assert len(result) == 1
        assert len(result[0]) == 1

    def test_split_into_two_chunks(self):
        # Each module ~25 tokens (100 chars / 4), max_tokens=30
        modules = [
            {"module_name": "a", "parsed_summary": "x" * 100},
            {"module_name": "b", "parsed_summary": "x" * 100},
        ]
        result = split_module_groups(modules, max_tokens=30)
        assert len(result) == 2

    def test_all_modules_included(self):
        modules = [
            {"module_name": f"m{i}", "parsed_summary": "x" * 40}
            for i in range(10)
        ]
        result = split_module_groups(modules, max_tokens=50)
        all_names = {m["module_name"] for chunk in result for m in chunk}
        expected = {f"m{i}" for i in range(10)}
        assert all_names == expected

    def test_oversized_module_gets_own_chunk(self):
        modules = [
            {"module_name": "big", "parsed_summary": "x" * 500},
            {"module_name": "small", "parsed_summary": "x" * 40},
        ]
        result = split_module_groups(modules, max_tokens=50)
        assert len(result) == 2
