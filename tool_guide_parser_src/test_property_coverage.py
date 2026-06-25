"""Property-based test for the text coverage invariant (task 2.5).

Feature: eda-tool-guide-rag, Property 2: 텍스트 100% 커버리지 (Coverage Invariant)
-----------------------------------------------------------------------------
design.md "Correctness Properties" — Property 2:

    *For any* 유효한 입력 문서에 대해, 추출된 모든 Tool_Guide_Object의 텍스트 경계
    ``[start, end)`` 구간들의 합집합이 원문 텍스트의 비공백 문자 전체(100%)를
    빠짐없이 커버해야 한다(미파싱 구간은 section 객체로 보존되어 누락이 없어야 한다).

    **Validates: Requirements 2.1, 2.5**

The block scanner :func:`blockscan.scan_blocks` tiles ``[0, len(text))``
contiguously (no gaps / overlaps) and wraps any rule-unmatched residual region
as a ``section`` object, so nothing is lost. This test generalises that
guarantee to arbitrary synthetic tool-guide input — a mix of rule-matched
blocks (command / option / flow / example labels and fenced code), unparsed
residual prose regions, and non-ASCII / special characters — and asserts:

  1. (Property 2, the requirement) every **non-whitespace** character offset of
     the input is contained in the union of the returned objects' ``[start,
     end)`` intervals; and
  2. (the stronger guarantee the implementation actually provides) for any
     non-empty input the union is exactly ``[0, len(text))`` — a contiguous,
     gap-free, non-overlapping tiling.

Empty / whitespace handling follows the parser contract:
  * ``scan_blocks("") == []`` (the union of no intervals is the empty range);
  * for whitespace-only input the set of non-whitespace offsets is empty, so the
    coverage invariant is trivially satisfied.

Run: ``py -m pytest test_property_coverage.py -v`` inside ``tool_guide_parser_src``.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from blockscan import scan_blocks

# ---------------------------------------------------------------------------
# Generator: synthetic tool-guide text
#
# A document is a list of lines joined by "\n". Each line is drawn from a menu
# that deliberately mixes:
#   * rule-matched header lines (command / option / flow / example labels),
#   * fenced-code-block delimiters (open/close an ``example`` block),
#   * blank lines and whitespace-only lines,
#   * free-form residual prose that no rule matches (the "unparsed residual
#     regions" the task asks the generator to include), and
#   * non-ASCII / special-character text (CJK, accented, arrows, symbols).
#
# Coverage (Property 2) must hold regardless of how any given line happens to be
# classified, so the generator is free-form by design.
# ---------------------------------------------------------------------------

# Header lines that the block scanner's label rules recognise (design.md C2).
_LABEL_LINES: tuple[str, ...] = (
    "Command: elaborate",
    "SYNTAX",
    "Usage: foo [opts]",
    "Options:",
    "Arguments:",
    "-v",
    "--output FILE",
    "Flow:",
    "Methodology",
    "Step 2 build",
    "Procedure",
    "Example:",
    "Examples:",
)

# Free-form residual prose: any single line (no embedded newline). Excludes
# surrogate code points to keep the text a well-formed Python str.
_residual_prose = st.text(
    alphabet=st.characters(blacklist_characters="\n", blacklist_categories=("Cs",)),
    max_size=60,
)

# Non-ASCII / special characters: CJK, accented Latin, arrows, symbols, plus
# some interleaved whitespace/tabs to exercise the non-whitespace coverage edge.
_non_ascii_prose = st.text(
    alphabet="옵션설명명령어例示説明café résumé→←★☆✓merge \t",
    min_size=1,
    max_size=30,
)

# A single line of the synthetic document.
_line = st.one_of(
    st.sampled_from(_LABEL_LINES),
    st.just("```"),          # fence open/close delimiter -> example block
    st.just("```sh"),        # fence with info string
    st.just(""),             # blank line
    st.just("   \t  "),      # whitespace-only line
    _residual_prose,         # unparsed residual region
    _non_ascii_prose,        # non-ASCII / special chars
)

# Whole document: 0..40 lines joined by newlines (0 lines -> "" empty doc).
_tool_guide_text = st.lists(_line, max_size=40).map("\n".join)


def _covered_offsets(objects) -> set[int]:
    """Return the set of character offsets covered by all object intervals."""
    covered: set[int] = set()
    for obj in objects:
        covered.update(range(obj.start_offset, obj.end_offset))
    return covered


# ---------------------------------------------------------------------------
# Property 2 — text 100% coverage (Coverage Invariant)
# Validates: Requirements 2.1, 2.5
# Feature: eda-tool-guide-rag, Property 2
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(_tool_guide_text)
def test_property_2_coverage_invariant(text: str) -> None:
    """Union of extracted objects' [start, end) covers 100% of non-ws chars.

    Feature: eda-tool-guide-rag, Property 2: 텍스트 100% 커버리지 (Coverage Invariant)
    Validates: Requirements 2.1, 2.5
    """
    objects = scan_blocks(text)

    # Empty document: the parser contract is scan_blocks("") == [] and the
    # non-whitespace coverage requirement is vacuously satisfied.
    if len(text) == 0:
        assert objects == []
        return

    covered = _covered_offsets(objects)

    # --- Property 2 (the requirement): every non-whitespace offset is covered.
    non_whitespace = {i for i, ch in enumerate(text) if not ch.isspace()}
    assert non_whitespace.issubset(covered), (
        "non-whitespace characters left uncovered: "
        f"{sorted(non_whitespace - covered)}"
    )

    # --- Stronger guarantee the implementation provides: contiguous tiling of
    # the WHOLE text, so unparsed residual regions are preserved (as section
    # objects) and nothing — whitespace or not — is dropped.
    assert objects, "non-empty text must yield at least one object"
    starts = [obj.start_offset for obj in objects]
    assert starts == sorted(starts), "objects must be start-sorted ascending"
    assert objects[0].start_offset == 0, "tiling must start at offset 0"
    for prev, nxt in zip(objects, objects[1:]):
        assert prev.end_offset == nxt.start_offset, "gap/overlap between objects"
    assert objects[-1].end_offset == len(text), "tiling must end at len(text)"
    assert covered == set(range(len(text))), "union must equal [0, len(text))"


@settings(max_examples=100)
@given(st.text(alphabet=" \t\f\r\n\v", max_size=50))
def test_property_2_whitespace_only_is_trivially_covered(text: str) -> None:
    """Whitespace-only (or empty) input has no non-ws chars to cover.

    Feature: eda-tool-guide-rag, Property 2: 텍스트 100% 커버리지 (Coverage Invariant)
    Validates: Requirements 2.1, 2.5

    The set of non-whitespace offsets is empty, so the coverage invariant holds
    trivially; for non-empty whitespace the residual region is still preserved
    as a tiling that covers ``[0, len(text))``.
    """
    objects = scan_blocks(text)
    if len(text) == 0:
        assert objects == []
        return
    covered = _covered_offsets(objects)
    non_whitespace = {i for i, ch in enumerate(text) if not ch.isspace()}
    assert non_whitespace == set()
    assert non_whitespace.issubset(covered)
    # Residual whitespace is still fully tiled (preserved, not dropped).
    assert covered == set(range(len(text)))
