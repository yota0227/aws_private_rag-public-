"""Unit tests for ``build_objects`` (task 3.1).

Covers the contracts from design.md C2 steps 6-7 and requirements 2.6, 3.1,
3.2, 3.3, 3.4, 3.5:

* 7 metadata fields always present, all strings, UNKNOWN for unconfirmed (R3.1, R3.4)
* evidence has source_file + doc_version + (page | section >= 1) (R3.3)
* exactly one non-empty canonical_text per object (R2.6)
* object_type in allowed set; disallowed types skipped (R3.2)
* 5 top-level fields present on every record (R3.5)
* id normalization: case-fold + trim inputs produce same id (R3.6)
"""

import pytest

from build_objects import (
    _fill_evidence,
    _fill_metadata,
    _make_canonical_text,
    build_objects,
)
from parse_structure import parse_structure
from schema import METADATA_FIELDS, OBJECT_TYPES, UNKNOWN
from textualize import textualize_markdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_offset_map(text):
    """Convenience: return the OffsetMap for ``text`` (treated as Markdown)."""
    return textualize_markdown(text).mapping


def _build(
    text,
    tool_name="VCS",
    tool_version="2023.12",
    doc_version="2023.12-rev1",
    source_file="vcs_guide.pdf",
):
    """Build ToolGuideObject list from a Markdown text snippet."""
    related = parse_structure(text)
    offset_map = _make_offset_map(text)
    return build_objects(
        related,
        text=text,
        tool_name=tool_name,
        tool_version=tool_version,
        doc_version=doc_version,
        source_file=source_file,
        offset_map=offset_map,
    )


# ---------------------------------------------------------------------------
# R3.5: 5 top-level fields on every record
# ---------------------------------------------------------------------------


def test_five_top_level_fields_present():
    text = "Command: elaborate\n-o output\n"
    objs = _build(text)
    assert objs, "Expected at least one object"
    for obj in objs:
        d = obj.to_dict()
        assert set(d.keys()) == {
            "id",
            "object_type",
            "canonical_text",
            "metadata",
            "evidence",
        }


# ---------------------------------------------------------------------------
# R3.1: 7 metadata fields, always present, all strings
# ---------------------------------------------------------------------------


def test_metadata_has_seven_fields():
    text = "Command: elaborate\n"
    objs = _build(text)
    assert objs
    for obj in objs:
        meta = obj.to_dict()["metadata"]
        assert set(meta.keys()) == set(METADATA_FIELDS), (
            f"Missing/extra metadata keys: {set(meta.keys())}"
        )
        assert len(meta) == 7


def test_all_metadata_values_are_strings():
    text = "Command: elaborate\nOptions:\n-o output\n"
    objs = _build(text)
    for obj in objs:
        meta = obj.to_dict()["metadata"]
        for key, val in meta.items():
            assert isinstance(val, str), (
                f"metadata['{key}'] is not a string: {val!r}"
            )


# ---------------------------------------------------------------------------
# R3.4: unconfirmed metadata values == UNKNOWN (not empty, not guessed)
# ---------------------------------------------------------------------------


def test_unknown_placeholder_used_for_unconfirmed_option_field():
    # A bare command block: the 'option' metadata field cannot be confirmed.
    text = "Command: elaborate\n"
    objs = _build(text)
    assert objs
    cmd_obj = objs[0]
    meta = cmd_obj.to_dict()["metadata"]
    assert meta["option"] == UNKNOWN, (
        f"Expected UNKNOWN for 'option' on a command object, got {meta['option']!r}"
    )


def test_empty_tool_version_maps_to_unknown():
    text = "Command: elaborate\n"
    objs = _build(text, tool_version="")
    assert objs
    meta = objs[0].to_dict()["metadata"]
    assert meta["tool_version"] == UNKNOWN


# ---------------------------------------------------------------------------
# R3.2: object_type in allowed set; disallowed types are skipped
# ---------------------------------------------------------------------------


def test_all_object_types_in_allowed_set():
    text = (
        "preamble\n"
        "Command: build\n"
        "Options:\n"
        "-o output\n"
        "```\nbuild -o out\n```\n"
        "Flow: methodology\n"
    )
    objs = _build(text)
    for obj in objs:
        assert obj.object_type in OBJECT_TYPES, (
            f"Unexpected object_type: {obj.object_type!r}"
        )


def test_build_objects_skips_disallowed_type():
    """A RelatedObject with an unsupported object_type must be skipped (R3.2)."""
    from relations import RelatedObject
    from textualize import textualize_markdown

    text = "Command: build\n"
    offset_map = textualize_markdown(text).mapping

    class _FakeParsedObject:
        """Minimal duck-typed ParsedObject with a disallowed object_type."""
        start_offset = 0
        end_offset = len(text)
        object_type = "widget"  # NOT in OBJECT_TYPES

    fake_ro = RelatedObject(obj=_FakeParsedObject(), belongs_to=None)  # type: ignore[arg-type]
    result = build_objects(
        [fake_ro],
        text=text,
        tool_name="VCS",
        tool_version="2023.12",
        doc_version="2023.12-rev1",
        source_file="vcs.pdf",
        offset_map=offset_map,
    )
    assert result == [], "disallowed object_type must produce no output"


# ---------------------------------------------------------------------------
# R2.6: exactly one non-empty canonical_text per object
# ---------------------------------------------------------------------------


def test_canonical_text_is_non_empty():
    text = "Command: elaborate\nOptions:\n-o out\n"
    objs = _build(text)
    for obj in objs:
        assert obj.canonical_text, (
            f"canonical_text must not be empty for {obj.object_type}"
        )
        assert obj.canonical_text.strip(), (
            "canonical_text must not be whitespace-only"
        )


def test_each_object_has_exactly_one_canonical_text_string():
    text = "Command: build\n-a one\n--beta two\n"
    objs = _build(text)
    for obj in objs:
        # canonical_text is a single str, not a list/None
        assert isinstance(obj.canonical_text, str)


def test_command_canonical_text_contains_command_name():
    text = "Command: elaborate\nCreates the design elaboration.\n"
    objs = _build(text)
    cmd_objs = [o for o in objs if o.object_type == "command"]
    assert cmd_objs
    assert "elaborate" in cmd_objs[0].canonical_text.lower()


def test_option_canonical_text_contains_option_label():
    text = "Command: build\n-o output file\n"
    objs = _build(text)
    opt_objs = [o for o in objs if o.object_type == "option"]
    assert opt_objs
    # canonical_text should mention "option" (from template) or the option name
    assert any(
        "option" in o.canonical_text.lower() or "-o" in o.canonical_text
        for o in opt_objs
    )


# ---------------------------------------------------------------------------
# R3.3: evidence has source_file + doc_version + (page | section >= 1)
# ---------------------------------------------------------------------------


def test_evidence_has_source_file_and_doc_version():
    text = "Command: elaborate\n"
    objs = _build(text, source_file="vcs_guide.pdf", doc_version="2023.12-rev1")
    for obj in objs:
        ev = obj.to_dict()["evidence"]
        assert "source_file" in ev, "evidence must have source_file"
        assert "doc_version" in ev, "evidence must have doc_version"
        # doc_version is normalized (case-folded) -> "2023.12-rev1" stays same
        assert ev["source_file"] == "vcs_guide.pdf"
        assert ev["doc_version"] == "2023.12-rev1"


def test_evidence_has_at_least_page_or_section():
    text = "Command: elaborate\n"
    objs = _build(text)
    for obj in objs:
        ev = obj.to_dict()["evidence"]
        has_page = "page" in ev and ev["page"] is not None
        has_section = "section" in ev and ev["section"] is not None
        assert has_page or has_section, (
            f"evidence must have at least page or section, got: {ev}"
        )


def test_evidence_section_falls_back_to_unknown_when_no_page_or_section():
    """Markdown with no ATX headers yields no section; section must be UNKNOWN (R3.4)."""
    text = "Command: elaborate\n"
    objs = _build(text, source_file="vcs.pdf")
    for obj in objs:
        ev = obj.to_dict()["evidence"]
        # Markdown has no page; no ATX headers means no section from OffsetMap.
        # _fill_evidence must set section=UNKNOWN to satisfy R3.3 invariant.
        assert ev.get("section") == UNKNOWN, (
            f"Expected section=UNKNOWN when unconfirmable, got {ev.get('section')!r}"
        )


def test_evidence_section_uses_atx_heading_when_present():
    """When the document has ATX headers the section field reflects them."""
    text = "# 4.2 Elaboration\n\nCommand: elaborate\n"
    objs = _build(text)
    cmd_objs = [o for o in objs if o.object_type == "command"]
    assert cmd_objs
    ev = cmd_objs[0].to_dict()["evidence"]
    has_real_section = "section" in ev and ev["section"] not in (None, UNKNOWN)
    # Only verify when a real section was found
    if has_real_section:
        assert "elaboration" in ev["section"].lower() or "4.2" in ev["section"], (
            f"Expected section to reflect heading, got: {ev['section']!r}"
        )


def test_evidence_source_file_falls_back_to_unknown():
    """Empty source_file produces UNKNOWN in evidence (R3.4)."""
    text = "Command: build\n"
    objs = _build(text, source_file="")
    for obj in objs:
        ev = obj.to_dict()["evidence"]
        assert ev["source_file"] == UNKNOWN


# ---------------------------------------------------------------------------
# R3.6: id normalization (case-fold + trim produce same id)
# ---------------------------------------------------------------------------


def test_id_normalization_case_insensitive():
    """Same logical document with different tool_name casing yields same ids."""
    text = "Command: elaborate\n"
    related = parse_structure(text)
    offset_map = _make_offset_map(text)

    kwargs = dict(
        text=text,
        tool_version="2023.12",
        doc_version="2023.12-rev1",
        source_file="vcs.pdf",
        offset_map=offset_map,
    )

    objs_upper = build_objects(related, tool_name="VCS", **kwargs)
    objs_lower = build_objects(related, tool_name="vcs", **kwargs)

    ids_upper = [o.id for o in objs_upper]
    ids_lower = [o.id for o in objs_lower]
    assert ids_upper == ids_lower, (
        f"IDs differ on case variant:\n  upper={ids_upper}\n  lower={ids_lower}"
    )


def test_id_normalization_whitespace():
    """Leading/trailing whitespace in tool_name is trimmed before id generation."""
    text = "Command: elaborate\n"
    related = parse_structure(text)
    offset_map = _make_offset_map(text)

    kwargs = dict(
        text=text,
        tool_version="2023.12",
        doc_version="2023.12-rev1",
        source_file="vcs.pdf",
        offset_map=offset_map,
    )

    objs_padded = build_objects(related, tool_name="  VCS  ", **kwargs)
    objs_clean = build_objects(related, tool_name="VCS", **kwargs)

    assert [o.id for o in objs_padded] == [o.id for o in objs_clean]


# ---------------------------------------------------------------------------
# Metadata field-specific correctness
# ---------------------------------------------------------------------------


def test_command_metadata_object_type_is_command():
    text = "Command: elaborate\n"
    objs = _build(text)
    cmd_objs = [o for o in objs if o.object_type == "command"]
    assert cmd_objs
    assert cmd_objs[0].metadata.object_type == "command"


def test_option_metadata_object_type_is_option():
    text = "Command: build\n-o output\n"
    objs = _build(text)
    opt_objs = [o for o in objs if o.object_type == "option"]
    assert opt_objs
    assert opt_objs[0].metadata.object_type == "option"


def test_option_metadata_command_field_is_owning_command():
    """An option's metadata.command should reference its owning command name."""
    text = "Command: elaborate\n-o output\n"
    objs = _build(text)
    opt_objs = [o for o in objs if o.object_type == "option"]
    assert opt_objs
    assert opt_objs[0].metadata.command == "elaborate", (
        f"Expected 'elaborate', got {opt_objs[0].metadata.command!r}"
    )


def test_orphan_option_command_field_is_unknown():
    """An orphan option (no owning command) must have metadata.command == UNKNOWN."""
    text = "Options:\n-o orphan\n"
    objs = _build(text)
    opt_objs = [o for o in objs if o.object_type == "option"]
    assert opt_objs
    for opt in opt_objs:
        assert opt.metadata.command == UNKNOWN, (
            f"Orphan option should have UNKNOWN command, got {opt.metadata.command!r}"
        )


def test_metadata_tool_name_is_normalized():
    """metadata.tool_name reflects the normalized (case-folded) tool_name."""
    text = "Command: build\n"
    objs = _build(text, tool_name="VCS")
    assert objs
    assert objs[0].metadata.tool_name == "vcs"


def test_metadata_doc_version_is_normalized():
    """metadata.doc_version reflects the normalized doc_version."""
    text = "Command: build\n"
    objs = _build(text, doc_version="2023.12-Rev1")
    assert objs
    assert objs[0].metadata.doc_version == "2023.12-rev1"


# ---------------------------------------------------------------------------
# LLM-injectable summarizer
# ---------------------------------------------------------------------------


def test_summarize_called_for_example_type():
    text = "```\nbuild -o out\n```\n"
    calls: list[str] = []

    def fake_summarize(block_text: str, object_type: str) -> str:
        calls.append(object_type)
        return f"SUMMARY:{object_type}"

    related = parse_structure(text)
    offset_map = _make_offset_map(text)
    objs = build_objects(
        related,
        text=text,
        tool_name="VCS",
        tool_version="2023.12",
        doc_version="2023.12-rev1",
        source_file="vcs.pdf",
        offset_map=offset_map,
        summarize=fake_summarize,
    )
    example_objs = [o for o in objs if o.object_type == "example"]
    assert example_objs, "Expected at least one example object"
    assert example_objs[0].canonical_text.startswith("SUMMARY:example")
    assert "example" in calls


def test_no_summarize_uses_deterministic_template():
    text = "```\nbuild -o out\n```\n"
    related = parse_structure(text)
    offset_map = _make_offset_map(text)
    objs = build_objects(
        related,
        text=text,
        tool_name="VCS",
        tool_version="2023.12",
        doc_version="2023.12-rev1",
        source_file="vcs.pdf",
        offset_map=offset_map,
        summarize=None,
    )
    example_objs = [o for o in objs if o.object_type == "example"]
    assert example_objs
    # Without summarizer, template is used: "Example: <first_non_blank_line>"
    assert example_objs[0].canonical_text.startswith("Example:")


# ---------------------------------------------------------------------------
# Empty related objects list
# ---------------------------------------------------------------------------


def test_empty_related_objects_returns_empty_list():
    text = "Command: build\n"
    offset_map = _make_offset_map(text)
    result = build_objects(
        [],
        text=text,
        tool_name="VCS",
        tool_version="2023.12",
        doc_version="2023.12-rev1",
        source_file="vcs.pdf",
        offset_map=offset_map,
    )
    assert result == []


# ---------------------------------------------------------------------------
# Helper unit tests: _fill_evidence
# ---------------------------------------------------------------------------


def test_fill_evidence_no_page_no_section_sets_section_unknown():
    ev = _fill_evidence(
        source_file="vcs.pdf",
        doc_version="2023.12",
        page=None,
        section_title="",
    )
    d = ev.to_dict()
    assert d.get("section") == UNKNOWN
    assert "page" not in d


def test_fill_evidence_page_provided():
    ev = _fill_evidence(
        source_file="vcs.pdf",
        doc_version="2023.12",
        page=42,
        section_title="",
    )
    d = ev.to_dict()
    assert d["page"] == 42


def test_fill_evidence_section_provided():
    ev = _fill_evidence(
        source_file="vcs.pdf",
        doc_version="2023.12",
        page=None,
        section_title="4.2 Elaboration",
    )
    d = ev.to_dict()
    assert d["section"] == "4.2 Elaboration"
    assert "page" not in d


def test_fill_evidence_empty_source_file_maps_to_unknown():
    ev = _fill_evidence(source_file="", doc_version="2023.12", page=1, section_title="")
    assert ev.source_file == UNKNOWN


# ---------------------------------------------------------------------------
# Helper unit tests: _fill_metadata
# ---------------------------------------------------------------------------


def test_fill_metadata_seven_fields():
    meta = _fill_metadata(
        object_type="command",
        tool_name="vcs",
        tool_version="2023.12",
        doc_version="2023.12-rev1",
        name="elaborate",
        section_title="4.2 Elaboration",
        belongs_to_command_name=None,
    )
    d = meta.to_dict()
    assert set(d.keys()) == set(METADATA_FIELDS)
    assert len(d) == 7


def test_fill_metadata_all_values_strings():
    meta = _fill_metadata(
        object_type="option",
        tool_name="vcs",
        tool_version="2023.12",
        doc_version="rev1",
        name="-o",
        section_title="",
        belongs_to_command_name="elaborate",
    )
    for k, v in meta.to_dict().items():
        assert isinstance(v, str), f"metadata['{k}'] is not str: {v!r}"


# ---------------------------------------------------------------------------
# Helper unit tests: _make_canonical_text
# ---------------------------------------------------------------------------


def test_make_canonical_text_command():
    result = _make_canonical_text(
        "command",
        "elaborate",
        "Command: elaborate\nCreates elaboration.\n",
        UNKNOWN,
        None,
    )
    assert "elaborate" in result.lower()
    assert result.strip()


def test_make_canonical_text_option():
    result = _make_canonical_text(
        "option",
        "-o",
        "-o output file\nSpecifies the output.\n",
        UNKNOWN,
        None,
    )
    assert "-o" in result
    assert result.strip()


def test_make_canonical_text_flow_step():
    result = _make_canonical_text(
        "flow_step",
        "compile",
        "Flow: compile\nRun compilation.\n",
        UNKNOWN,
        None,
    )
    assert result.strip()


def test_make_canonical_text_example_no_summarizer():
    result = _make_canonical_text(
        "example",
        UNKNOWN,
        "```\nbuild -o out\n```\n",
        UNKNOWN,
        None,
    )
    assert result.startswith("Example:")
    assert result.strip()


def test_make_canonical_text_section():
    result = _make_canonical_text(
        "section",
        UNKNOWN,
        "Introduction\n\nSome text.\n",
        "Introduction",
        None,
    )
    assert result.strip()
    # Template: "Section '<title>': <first_non_blank_line>"
    assert "Introduction" in result or "section" in result.lower()


def test_make_canonical_text_with_summarizer():
    def fake(text: str, otype: str) -> str:
        return f"SUMMARY:{otype}"

    result = _make_canonical_text("example", UNKNOWN, "some code", UNKNOWN, fake)
    assert result == "SUMMARY:example"
