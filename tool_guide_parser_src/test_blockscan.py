"""Tests for the deterministic block-scanning core (task 2.2).

Covers:
  * detection of each label type (command / option / flow_step / example) (R2.1)
  * residual regions wrapped as ``section`` objects (R2.5)
  * the tiling / coverage invariant: union of ``[start, end)`` == ``[0, len)``,
    contiguous and non-overlapping (R2.5, the basis of Property 2)
  * stable ordering by ``start_offset`` ascending (R2.2)
  * determinism across repeated calls (R2.2 / R2.7, the basis of Property 1)
  * closed ``object_type`` set + ParsedObject validation (R3.2)

These are example-based unit tests; the Hypothesis property tests for
determinism (Property 1) and coverage (Property 2) arrive in tasks 2.4 / 2.5.
"""

import pytest

from blockscan import ParsedObject, scan_blocks
from schema import OBJECT_TYPES


# ---------------------------------------------------------------------------
# Coverage / tiling helpers
# ---------------------------------------------------------------------------


def _assert_tiles_fully(objects, text):
    """Assert objects tile ``[0, len(text))`` contiguously with no gaps/overlaps."""
    if len(text) == 0:
        assert objects == []
        return
    # Sorted by start_offset (the public contract).
    starts = [o.start_offset for o in objects]
    assert starts == sorted(starts)
    # Contiguous tiling: first starts at 0, each end meets the next start,
    # last ends exactly at len(text).
    assert objects[0].start_offset == 0
    for prev, nxt in zip(objects, objects[1:]):
        assert prev.end_offset == nxt.start_offset  # no gap, no overlap
    assert objects[-1].end_offset == len(text)


def _covered_offsets(objects):
    """Return the set of character offsets covered by all object intervals."""
    covered: set[int] = set()
    for o in objects:
        covered.update(range(o.start_offset, o.end_offset))
    return covered


# ---------------------------------------------------------------------------
# Detection of each label type (R2.1)
# ---------------------------------------------------------------------------


def test_detect_command_label():
    text = "Command: elaborate\ncompiles the design\n"
    objects = scan_blocks(text)
    assert [o.object_type for o in objects] == ["command"]
    _assert_tiles_fully(objects, text)


def test_detect_command_syntax_and_usage_headers():
    text = "SYNTAX\nfoo bar\nUsage: foo [opts]\nmore\n"
    objects = scan_blocks(text)
    assert [o.object_type for o in objects] == ["command", "command"]


def test_detect_option_label_and_dash_definitions():
    text = (
        "Options:\n"
        "-v verbose\n"
        "--output FILE write output\n"
    )
    objects = scan_blocks(text)
    # "Options:" then two dash-definition lines -> three option blocks.
    assert [o.object_type for o in objects] == ["option", "option", "option"]
    _assert_tiles_fully(objects, text)


def test_dash_bullet_and_horizontal_rule_are_not_options():
    # "- item" (dash + space) and "---" must NOT be detected as options; with no
    # other label they fall into a single residual section.
    text = "- a bullet item\n--- not a rule header\nplain line\n"
    objects = scan_blocks(text)
    assert [o.object_type for o in objects] == ["section"]
    _assert_tiles_fully(objects, text)


def test_detect_flow_step_headers():
    text = "Flow:\ndo this\nStep 2 build\nMethodology overview\n"
    objects = scan_blocks(text)
    assert [o.object_type for o in objects] == ["flow_step", "flow_step", "flow_step"]


def test_detect_example_label():
    text = "Example: run it\nfoo --bar\n"
    objects = scan_blocks(text)
    assert objects[0].object_type == "example"


def test_detect_example_fenced_code_block():
    text = "intro\n```sh\nCommand: not a header inside fence\n```\ntrailing\n"
    objects = scan_blocks(text)
    types = [o.object_type for o in objects]
    # Leading "intro" residual section, then the example fence block. The block
    # swallows the inner "Command:" line (fenced) AND the post-fence "trailing"
    # text, because the closing fence opens no new header and every block runs
    # until the next header (or end of text).
    assert types == ["section", "example"]
    _assert_tiles_fully(objects, text)


def test_fence_hides_inner_labels():
    # The inner "Options:" line must not create an option block while fenced.
    text = "```\nOptions:\n-x\n```\n"
    objects = scan_blocks(text)
    assert [o.object_type for o in objects] == ["example"]
    _assert_tiles_fully(objects, text)


# ---------------------------------------------------------------------------
# Residual handling -> section objects (R2.5)
# ---------------------------------------------------------------------------


def test_residual_prefix_becomes_section():
    text = "free prose with no labels\nstill prose\nCommand: go\n"
    objects = scan_blocks(text)
    assert objects[0].object_type == "section"
    assert objects[0].start_offset == 0
    assert objects[1].object_type == "command"
    _assert_tiles_fully(objects, text)


def test_no_labels_entire_text_is_one_section():
    text = "just paragraphs\nnothing structural here\n"
    objects = scan_blocks(text)
    assert len(objects) == 1
    assert objects[0].object_type == "section"
    assert objects[0].start_offset == 0
    assert objects[0].end_offset == len(text)


def test_header_at_offset_zero_has_no_prefix_section():
    text = "Command: first\nbody\n"
    objects = scan_blocks(text)
    assert objects[0].object_type == "command"
    assert objects[0].start_offset == 0


# ---------------------------------------------------------------------------
# Precision guard: keyword label + long prose is NOT a header (register manuals)
# ---------------------------------------------------------------------------


def test_long_prose_starting_with_keyword_is_not_a_header():
    # A register-manual sentence that begins with "Command"/"Usage" but runs on
    # as prose must NOT be classified as a command block; it stays in a section.
    text = (
        "Command mode is PCI Express, this field is permitted to be hardwired "
        "to 000b. If 001b, PCIe protocol only with vendor extensions applies.\n"
    )
    objects = scan_blocks(text)
    assert [o.object_type for o in objects] == ["section"]
    _assert_tiles_fully(objects, text)


def test_short_keyword_headers_still_detected_alongside_long_prose():
    # Short real headers keep working even when long prose lines are present.
    text = (
        "Command: elaborate\n"
        "Usage notes: this register field controls the operating mode and is "
        "permitted to be hardwired depending on the configured protocol stack.\n"
    )
    objects = scan_blocks(text)
    # "Command: elaborate" -> command header; the long "Usage notes: ..." line is
    # prose (> max header length) so it is absorbed into the command block, not
    # a new header. Result: a single command block tiling the whole text.
    assert [o.object_type for o in objects] == ["command"]
    _assert_tiles_fully(objects, text)


# ---------------------------------------------------------------------------
# Coverage invariant (R2.5, basis of Property 2)
# ---------------------------------------------------------------------------


def test_union_covers_full_text_contiguously():
    text = (
        "Overview paragraph.\n"
        "Command: elaborate\n"
        "Options:\n"
        "-y assume yes\n"
        "Example:\n"
        "elaborate -y\n"
        "trailing notes\n"
    )
    objects = scan_blocks(text)
    _assert_tiles_fully(objects, text)
    # Explicitly: every offset in [0, len) is covered exactly once.
    assert _covered_offsets(objects) == set(range(len(text)))


def test_coverage_includes_all_non_whitespace_characters():
    text = "  \n\nCommand: go\n  trailing  \n"
    objects = scan_blocks(text)
    covered = _covered_offsets(objects)
    non_ws = {i for i, ch in enumerate(text) if not ch.isspace()}
    assert non_ws.issubset(covered)
    _assert_tiles_fully(objects, text)


def test_empty_text_returns_empty_list():
    assert scan_blocks("") == []


# ---------------------------------------------------------------------------
# Stable ordering by start_offset (R2.2)
# ---------------------------------------------------------------------------


def test_objects_sorted_by_start_offset_ascending():
    text = "Usage: a\nOptions:\n-x\nFlow:\nstep\nExample:\nrun\n"
    objects = scan_blocks(text)
    starts = [o.start_offset for o in objects]
    assert starts == sorted(starts)
    # Strictly increasing because each block has positive length.
    assert all(b > a for a, b in zip(starts, starts[1:]))


# ---------------------------------------------------------------------------
# Determinism across repeated calls (R2.2 / R2.7, basis of Property 1)
# ---------------------------------------------------------------------------


def test_repeated_calls_produce_identical_objects():
    text = (
        "preamble\n"
        "Command: build\n"
        "Options:\n"
        "--jobs N\n"
        "```\ncode\n```\n"
        "Methodology\n"
        "tail\n"
    )
    first = scan_blocks(text)
    second = scan_blocks(text)
    # Same count, same boundaries, same type ordering — value equality on frozen
    # dataclasses captures all three.
    assert first == second
    assert [o.object_type for o in first] == [o.object_type for o in second]
    assert [(o.start_offset, o.end_offset) for o in first] == [
        (o.start_offset, o.end_offset) for o in second
    ]


# ---------------------------------------------------------------------------
# Closed object_type set + ParsedObject validation (R3.2)
# ---------------------------------------------------------------------------


def test_all_object_types_in_allowed_set():
    text = "p\nCommand: c\nOptions:\n-x\nFlow:\ns\nExample:\ne\n"
    objects = scan_blocks(text)
    for o in objects:
        assert o.object_type in OBJECT_TYPES


def test_parsed_object_rejects_unknown_type():
    with pytest.raises(ValueError):
        ParsedObject(0, 5, "banana")


def test_parsed_object_rejects_nonpositive_length():
    with pytest.raises(ValueError):
        ParsedObject(5, 5, "section")
    with pytest.raises(ValueError):
        ParsedObject(7, 3, "section")


def test_parsed_object_rejects_negative_start():
    with pytest.raises(ValueError):
        ParsedObject(-1, 3, "section")


def test_parsed_object_length_property():
    obj = ParsedObject(2, 9, "command")
    assert obj.length == 7
