"""Property-based tests for Req 18 (used_in_n1 scope & boost).

Property 15: used_in_n1 Path Determinism — _is_used_in_n1(key)는 '/used_in_n1/'
             세그먼트 포함 여부와 정확히 일치 (Req 18.1, 18.2).
Property 16: used_in_n1 Boost Monotonicity — 동일 base relevance에서
             used_in_n1=true 후보 최종 점수 >= false 후보 (Req 18.3, 18.4).
"""
from hypothesis import given, strategies as st

import handler


# ---------------------------------------------------------------------------
# Property 15: used_in_n1 Path Determinism (Req 18.1, 18.2)
# ---------------------------------------------------------------------------

_segment = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_.",
    min_size=0,
    max_size=12,
)
_key_strategy = st.lists(_segment, min_size=0, max_size=8).map(lambda parts: "/".join(parts))


@given(key=_key_strategy)
def test_p15_is_used_in_n1_matches_segment(key):
    """_is_used_in_n1는 '/used_in_n1/' 부분문자열 포함 여부와 정확히 일치."""
    assert handler._is_used_in_n1(key) == ("/used_in_n1/" in key)


@given(prefix=_key_strategy, suffix=_key_strategy)
def test_p15_positive_when_segment_present(prefix, suffix):
    """경로에 /used_in_n1/ 세그먼트가 명시적으로 있으면 항상 True."""
    key = f"{prefix}/used_in_n1/{suffix}"
    assert handler._is_used_in_n1(key) is True


def test_p15_none_and_empty():
    """None/빈 문자열 엣지 케이스는 False."""
    assert handler._is_used_in_n1("") is False
    assert handler._is_used_in_n1(None) is False


def test_p15_basename_match_not_used():
    """파일명에 문자열이 들어가도 세그먼트(/used_in_n1/)가 아니면 False (basename 매칭 금지)."""
    assert handler._is_used_in_n1("rtl-sources/tt_20260516/tt_rtl/used_in_n1_notes.sv") is False


# ---------------------------------------------------------------------------
# Property 16: used_in_n1 Boost Monotonicity (Req 18.3, 18.4)
# ---------------------------------------------------------------------------

@given(
    base=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    boost=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
def test_p16_boost_monotonicity(base, boost):
    """동일 base score에서 used_in_n1=true 후보 최종 점수 >= false 후보."""
    original = handler.USED_IN_N1_BOOST
    handler.USED_IN_N1_BOOST = boost
    try:
        results = [
            {"used_in_n1": False, "score": base, "analysis_type": "claim", "claim_text": "a"},
            {"used_in_n1": True, "score": base, "analysis_type": "claim", "claim_text": "b"},
        ]
        boosted = handler._apply_used_in_n1_boost(results)
        by_flag = {r["used_in_n1"]: r["score"] for r in boosted}
        assert by_flag[True] >= by_flag[False]
    finally:
        handler.USED_IN_N1_BOOST = original


@given(base=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_p16_used_in_n1_ranked_first_on_tie(base):
    """동일 base relevance에서 used_in_n1=true 후보가 먼저 정렬된다 (Req 18.4)."""
    original = handler.USED_IN_N1_BOOST
    handler.USED_IN_N1_BOOST = 2.0
    try:
        results = [
            {"used_in_n1": False, "score": base, "analysis_type": "claim", "claim_text": "a"},
            {"used_in_n1": True, "score": base, "analysis_type": "claim", "claim_text": "b"},
        ]
        boosted = handler._apply_used_in_n1_boost(results)
        assert boosted[0]["used_in_n1"] is True
    finally:
        handler.USED_IN_N1_BOOST = original


def test_p16_empty_results_noop():
    """빈 결과는 그대로 반환 (엣지 케이스)."""
    assert handler._apply_used_in_n1_boost([]) == []
