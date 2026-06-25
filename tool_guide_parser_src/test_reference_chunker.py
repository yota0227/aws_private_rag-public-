"""Tests for size-based reference-document chunking (PARSE_MODE=reference).

Covers:
  * every object is object_type="section" (no command/option/flow false positives)
  * canonical_text carries the chunk's REAL text (content-bearing, not a template)
  * chunks never exceed chunk_size; non-whitespace content is fully covered
  * citation invariant R3.3: source_file + (page | section) present
  * metadata command/option are UNKNOWN (no extraction in reference mode)
  * determinism (R2.7): identical input -> identical chunk list
  * argument validation; empty input -> []
"""

import pytest

from reference_chunker import chunk_reference
from schema import UNKNOWN
from textualize import textualize_markdown


def _omap(text):
    return textualize_markdown(text).mapping


def _chunk(text, **kw):
    return chunk_reference(
        text,
        tool_name="Atlas/Synopsys IIPs",
        tool_version="ver.1",
        doc_version="ver.1",
        source_file="DWC_pcie_ctl_rp_databook.pdf",
        offset_map=_omap(text),
        **kw,
    )


def test_all_objects_are_section_type():
    text = "Command: build\nOptions:\n-x\n" * 50  # would be commands in tool_guide mode
    objs = _chunk(text, chunk_size=200, overlap=20)
    assert objs, "expected at least one chunk"
    assert all(o.object_type == "section" for o in objs)


def test_canonical_text_is_real_content_not_template():
    text = "The PL32G_CONTROL_REG field is hardwired to 000b for PCI Express mode.\n"
    objs = _chunk(text, chunk_size=200, overlap=20)
    assert len(objs) == 1
    # Real content, not a "Section '...': ..." template.
    assert "PL32G_CONTROL_REG" in objs[0].canonical_text
    assert not objs[0].canonical_text.startswith("Section '")


def test_chunks_never_exceed_chunk_size():
    text = "x" * 5000 + "\n" + "y" * 5000
    objs = _chunk(text, chunk_size=1000, overlap=100)
    for o in objs:
        assert len(o.canonical_text) <= 1000


def test_nonwhitespace_content_fully_covered():
    text = "alpha beta gamma\n" * 200
    objs = _chunk(text, chunk_size=300, overlap=50)
    joined = "".join(o.canonical_text for o in objs)
    # Every non-whitespace token of the source appears in some chunk.
    for token in ("alpha", "beta", "gamma"):
        assert token in joined


def test_citation_invariant_source_file_and_location():
    text = "# Heading\n\nSome register description text that is meaningful.\n"
    objs = _chunk(text, chunk_size=200, overlap=20)
    for o in objs:
        ev = o.evidence
        assert ev.source_file == "DWC_pcie_ctl_rp_databook.pdf"
        # R3.3: at least one of page / section present (page may be None for md).
        assert (ev.page is not None) or (ev.section not in (None, ""))


def test_metadata_command_option_unknown():
    text = "Command: build\n" * 30
    objs = _chunk(text, chunk_size=200, overlap=20)
    for o in objs:
        assert o.metadata.command == UNKNOWN
        assert o.metadata.option == UNKNOWN
        assert o.metadata.object_type == "section"


def test_determinism_identical_input_identical_output():
    text = "register field description line\n" * 100
    first = _chunk(text, chunk_size=250, overlap=30)
    second = _chunk(text, chunk_size=250, overlap=30)
    assert [o.id for o in first] == [o.id for o in second]
    assert [o.canonical_text for o in first] == [o.canonical_text for o in second]


def test_ids_are_unique():
    text = "line of register text\n" * 100
    objs = _chunk(text, chunk_size=200, overlap=20)
    ids = [o.id for o in objs]
    assert len(ids) == len(set(ids))


def test_empty_text_returns_empty_list():
    # textualize rejects empty/whitespace before chunk_reference is reached in
    # production; here we pass a valid offset_map (from dummy text) to exercise
    # chunk_reference's own empty/whitespace handling directly.
    omap = textualize_markdown("dummy content for a valid offset map").mapping

    def call(t):
        return chunk_reference(
            t,
            tool_name="Atlas/Synopsys IIPs",
            tool_version="ver.1",
            doc_version="ver.1",
            source_file="x.pdf",
            offset_map=omap,
        )

    assert call("") == []
    assert call("   \n\n  \n") == []


def test_invalid_chunk_size_raises():
    with pytest.raises(ValueError):
        _chunk("abc", chunk_size=0)


def test_invalid_overlap_raises():
    with pytest.raises(ValueError):
        _chunk("abc", chunk_size=100, overlap=100)
    with pytest.raises(ValueError):
        _chunk("abc", chunk_size=100, overlap=-1)
