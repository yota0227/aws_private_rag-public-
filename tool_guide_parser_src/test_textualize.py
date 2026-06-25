"""Tests for the textualization layer + offset→(page, section) mapping.

Covers (task 2.1 scope):
  * Markdown section mapping at various offsets (R2.1)
  * pdftotext page-break mapping with the external call mocked (R2.1)
  * empty/whitespace-only detection (R2.8)
  * unsupported-format detection (R1.3/R1.4)

The PDF external command (`pdftotext`) is never invoked: tests use the pure
`textualize_pdf_output` core or inject a fake runner, so these run without
`pdftotext` installed.
"""

import pytest

from schema import UNKNOWN
from textualize import (
    ErrorReason,
    InputFormat,
    OffsetMap,
    PageSpan,
    SectionSpan,
    TextualizationError,
    detect_format,
    is_empty_or_whitespace,
    run_pdftotext_layout,
    textualize_document,
    textualize_markdown,
    textualize_pdf,
    textualize_pdf_output,
)


# ---------------------------------------------------------------------------
# Format detection (R1.3 / R1.4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("guide.md", InputFormat.MARKDOWN),
        ("GUIDE.MD", InputFormat.MARKDOWN),
        ("notes.markdown", InputFormat.MARKDOWN),
        ("vcs_user_guide.pdf", InputFormat.PDF),
        ("Report.PDF", InputFormat.PDF),
        ("vcs/2023.12/guide.pdf", InputFormat.PDF),
        ("guide.txt", InputFormat.UNSUPPORTED),
        ("archive.tar.gz", InputFormat.UNSUPPORTED),
        ("guide.docx", InputFormat.UNSUPPORTED),
        ("noext", InputFormat.UNSUPPORTED),
        (".env", InputFormat.UNSUPPORTED),
    ],
)
def test_detect_format_by_extension(filename, expected):
    assert detect_format(filename) == expected


def test_detect_format_pdf_magic_when_extension_unknown():
    # Unknown extension but PDF magic bytes -> PDF.
    assert detect_format("mystery.bin", head=b"%PDF-1.7\n...") == InputFormat.PDF


def test_detect_format_unknown_extension_without_magic_is_unsupported():
    assert detect_format("mystery.bin", head=b"plain text") == InputFormat.UNSUPPORTED


def test_detect_format_extension_wins_over_missing_head():
    # Known extension does not require content sniffing.
    assert detect_format("guide.md", head=None) == InputFormat.MARKDOWN


# ---------------------------------------------------------------------------
# Empty / whitespace detection (R2.8)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n\t  \r\n", "\f\f", " \f \n "])
def test_is_empty_or_whitespace_true(text):
    assert is_empty_or_whitespace(text) is True


@pytest.mark.parametrize("text", ["x", "  hello  ", "\n# Title\n"])
def test_is_empty_or_whitespace_false(text):
    assert is_empty_or_whitespace(text) is False


def test_textualize_markdown_empty_raises_empty_document():
    with pytest.raises(TextualizationError) as exc:
        textualize_markdown("   \n\t ")
    assert exc.value.reason is ErrorReason.EMPTY_DOCUMENT
    assert exc.value.status == "error:empty_document"


def test_textualize_pdf_output_empty_raises_empty_document():
    with pytest.raises(TextualizationError) as exc:
        textualize_pdf_output("\f\f\n   ")
    assert exc.value.reason is ErrorReason.EMPTY_DOCUMENT


def test_textualize_document_unsupported_format_raises():
    with pytest.raises(TextualizationError) as exc:
        textualize_document("guide.txt", markdown_text="anything")
    assert exc.value.reason is ErrorReason.UNSUPPORTED_FORMAT
    assert exc.value.status == "error:unsupported_format"


# ---------------------------------------------------------------------------
# Markdown section mapping at various offsets (R2.1)
# ---------------------------------------------------------------------------


def test_markdown_section_mapping_at_various_offsets():
    text = (
        "intro text before any header\n"  # offsets in the pre-header region
        "# Top Title\n"
        "body of top\n"
        "## 4.2 Elaboration\n"
        "elaborate body\n"
        "### Deep\n"
        "deep body"
    )
    result = textualize_markdown(text)
    assert result.input_format is InputFormat.MARKDOWN

    # Pre-header region maps to the UNKNOWN placeholder, page is None for MD.
    page, section = result.mapping.locate(0)
    assert page is None
    assert section == UNKNOWN

    # Offset inside "body of top" -> enclosing section is "Top Title".
    off_top_body = text.index("body of top") + 2
    assert result.mapping.section_at(off_top_body) == "Top Title"

    # Offset inside "elaborate body" -> "4.2 Elaboration".
    off_elab = text.index("elaborate body") + 3
    assert result.mapping.section_at(off_elab) == "4.2 Elaboration"

    # Offset inside "deep body" -> "Deep".
    off_deep = text.index("deep body") + 1
    assert result.mapping.section_at(off_deep) == "Deep"

    # Page is always None for Markdown regardless of offset.
    assert result.mapping.page_at(off_deep) is None


def test_markdown_header_boundary_is_inclusive_at_header_start():
    text = "# Alpha\naaa\n## Beta\nbbb"
    result = textualize_markdown(text)
    beta_start = text.index("## Beta")
    # At the exact start offset of the header line, we are already "in" Beta.
    assert result.mapping.section_at(beta_start) == "Beta"
    # Just before it, still in Alpha.
    assert result.mapping.section_at(beta_start - 1) == "Alpha"


def test_markdown_no_headers_all_unknown():
    text = "just a paragraph\nwith two lines"
    result = textualize_markdown(text)
    assert result.mapping.section_spans == ()
    assert result.mapping.section_at(0) == UNKNOWN
    assert result.mapping.section_at(len(text)) == UNKNOWN


def test_markdown_hash_without_space_is_not_a_header():
    # "#notaheader" (no space) must not be treated as an ATX header.
    text = "#notaheader\ncontent"
    result = textualize_markdown(text)
    assert result.mapping.section_spans == ()


# ---------------------------------------------------------------------------
# PDF page-break mapping with the external call mocked (R2.1)
# ---------------------------------------------------------------------------


def test_pdf_page_mapping_from_form_feeds():
    # Three pages separated by form feeds.
    page1 = "1 Introduction\nintro body\n"
    page2 = "2 Setup\nsetup body\n"
    page3 = "3 Usage\nusage body\n"
    text = page1 + "\f" + page2 + "\f" + page3

    def fake_runner(path: str) -> str:
        assert path == "/tmp/guide.pdf"
        return text

    result = textualize_pdf("/tmp/guide.pdf", runner=fake_runner)
    assert result.input_format is InputFormat.PDF
    assert result.text == text

    # Offset within page 1 content.
    assert result.mapping.page_at(text.index("intro body")) == 1
    # Offset within page 2 content (after first form feed).
    assert result.mapping.page_at(text.index("setup body")) == 2
    # Offset within page 3 content (after second form feed).
    assert result.mapping.page_at(text.index("usage body")) == 3


def test_pdf_form_feed_char_belongs_to_terminating_page():
    text = "alpha\fbravo"
    result = textualize_pdf_output(text)
    ff_index = text.index("\f")
    # The form-feed itself terminates page 1.
    assert result.mapping.page_at(ff_index) == 1
    # The char right after the form-feed begins page 2.
    assert result.mapping.page_at(ff_index + 1) == 2


def test_pdf_section_and_page_combined_locate():
    text = "1 Introduction\nintro body\n\f4.2 Elaboration\nelaborate body\n"
    result = textualize_pdf_output(text)

    page, section = result.mapping.locate(text.index("intro body"))
    assert page == 1
    assert section == "1 Introduction"

    page, section = result.mapping.locate(text.index("elaborate body"))
    assert page == 2
    assert section == "4.2 Elaboration"


def test_pdf_keyword_section_headers_detected():
    text = "Chapter 1 Overview\nsome text\nSECTION notes\nmore"
    result = textualize_pdf_output(text)
    titles = [s.title for s in result.mapping.section_spans]
    assert "Chapter 1 Overview" in titles
    assert "SECTION notes" in titles


def test_pdf_offset_before_first_section_is_unknown():
    text = "preamble line with no header\n1 Real Section\nbody"
    result = textualize_pdf_output(text)
    assert result.mapping.section_at(0) == UNKNOWN
    assert result.mapping.section_at(text.index("body")) == "1 Real Section"


def test_textualize_document_pdf_uses_injected_runner():
    text = "1 Title\nbody\n\f2 Second\nmore body\n"
    result = textualize_document(
        "vcs/2023.12/guide.pdf",
        pdf_path="/data/guide.pdf",
        pdftotext_runner=lambda _p: text,
    )
    assert result.input_format is InputFormat.PDF
    assert result.mapping.page_at(text.index("more body")) == 2


# ---------------------------------------------------------------------------
# OffsetMap robustness / determinism
# ---------------------------------------------------------------------------


def test_offset_map_out_of_range_raises():
    omap = OffsetMap(section_spans=(), page_spans=(), text_length=5)
    with pytest.raises(ValueError):
        omap.section_at(-1)
    with pytest.raises(ValueError):
        omap.page_at(6)


def test_offset_map_lookup_is_deterministic_across_repeated_calls():
    text = "# A\naaa\n## B\nbbb\n\fccc"
    first = textualize_pdf_output(text)
    second = textualize_pdf_output(text)
    # Same structure both times (pure / deterministic).
    assert first.mapping == second.mapping
    for off in range(len(text) + 1):
        assert first.mapping.locate(off) == second.mapping.locate(off)


def test_markdown_textualization_is_deterministic():
    text = "# A\nbody a\n## B\nbody b"
    r1 = textualize_markdown(text)
    r2 = textualize_markdown(text)
    assert r1 == r2


def test_dataclasses_are_frozen_hashable():
    # Frozen dataclasses are hashable, supporting use as deterministic keys.
    assert hash(SectionSpan(0, "x")) == hash(SectionSpan(0, "x"))
    assert hash(PageSpan(0, 1)) == hash(PageSpan(0, 1))


# ---------------------------------------------------------------------------
# External boundary (missing-binary path; does not require pdftotext installed)
# ---------------------------------------------------------------------------


def test_run_pdftotext_layout_missing_binary_raises_runtimeerror(monkeypatch):
    import textualize as mod

    def boom(*_args, **_kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(mod.subprocess, "run", boom)
    with pytest.raises(RuntimeError):
        run_pdftotext_layout("/nonexistent.pdf")


# ---------------------------------------------------------------------------
# Property 13: Vision fallback safety (R7.4 / R7.5) — _resolve_page_text
# ---------------------------------------------------------------------------

from textualize import _resolve_page_text, VISION_SPARSE_THRESHOLD


def _render_ok():
    return b"\x89PNG fake-bytes"


def _render_should_not_be_called():
    raise AssertionError("render_png must not be called for non-sparse/disabled")


def test_vision_disabled_returns_raw_text():
    # R7.5: vision_describe=None -> original text, describer never built.
    raw = "x"  # sparse, but Vision disabled
    out = _resolve_page_text(
        raw, render_png=_render_should_not_be_called,
        vision_describe=None, sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_skips_dense_page():
    # A page with enough text is never sent to Vision.
    raw = "a" * (VISION_SPARSE_THRESHOLD + 5)
    out = _resolve_page_text(
        raw, render_png=_render_should_not_be_called,
        vision_describe=lambda png: "SHOULD NOT BE USED",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_describes_sparse_page():
    raw = "PClkBufIn"  # sparse floorplan label
    out = _resolve_page_text(
        raw, render_png=_render_ok,
        vision_describe=lambda png: "Block diagram: PClkBufIn is an input clock buffer pin.",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert "input clock buffer" in out
    assert out != raw


def test_vision_failure_falls_back_to_raw():
    # R7.4: any Vision exception -> original text, parsing continues.
    raw = "sparse"

    def boom(png):
        raise RuntimeError("bedrock throttled")

    out = _resolve_page_text(
        raw, render_png=_render_ok, vision_describe=boom,
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_empty_result_falls_back_to_raw():
    raw = "sparse"
    out = _resolve_page_text(
        raw, render_png=_render_ok, vision_describe=lambda png: "   ",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_render_failure_falls_back_to_raw():
    raw = "sparse"

    def render_boom():
        raise RuntimeError("pixmap failed")

    out = _resolve_page_text(
        raw, render_png=render_boom,
        vision_describe=lambda png: "desc",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


# ---------------------------------------------------------------------------
# Property 13: Vision fallback safety (R7.4 / R7.5) — _resolve_page_text
# ---------------------------------------------------------------------------

from textualize import _resolve_page_text, VISION_SPARSE_THRESHOLD


def _render_ok():
    return b"\x89PNG fake-bytes"


def _render_should_not_be_called():
    raise AssertionError("render_png must not be called for non-sparse/disabled")


def test_vision_disabled_returns_raw_text():
    # R7.5: vision_describe=None -> original text, describer never invoked.
    raw = "x"  # sparse, but Vision disabled
    out = _resolve_page_text(
        raw, render_png=_render_should_not_be_called,
        vision_describe=None, sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_skips_dense_page():
    # A page with enough text is never sent to Vision.
    raw = "a" * (VISION_SPARSE_THRESHOLD + 5)
    out = _resolve_page_text(
        raw, render_png=_render_should_not_be_called,
        vision_describe=lambda png: "SHOULD NOT BE USED",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_describes_sparse_page():
    raw = "PClkBufIn"  # sparse floorplan label
    out = _resolve_page_text(
        raw, render_png=_render_ok,
        vision_describe=lambda png: "Block diagram: PClkBufIn is an input clock buffer pin.",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert "input clock buffer" in out
    assert out != raw


def test_vision_failure_falls_back_to_raw():
    # R7.4: any Vision exception -> original text, parsing continues.
    raw = "sparse"

    def boom(png):
        raise RuntimeError("bedrock throttled")

    out = _resolve_page_text(
        raw, render_png=_render_ok, vision_describe=boom,
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_empty_result_falls_back_to_raw():
    raw = "sparse"
    out = _resolve_page_text(
        raw, render_png=_render_ok, vision_describe=lambda png: "   ",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_render_failure_falls_back_to_raw():
    raw = "sparse"

    def render_boom():
        raise RuntimeError("pixmap failed")

    out = _resolve_page_text(
        raw, render_png=render_boom,
        vision_describe=lambda png: "desc",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


# ---------------------------------------------------------------------------
# R7 refined detection: _should_use_vision (label-dump diagram pages)
# ---------------------------------------------------------------------------

from textualize import (
    _should_use_vision,
    DIAGRAM_MIN_DRAWINGS,
)


def test_should_vision_text_sparse_page():
    # Near-empty page: char-sparse signal (original R7.1).
    assert _should_use_vision("PClkBufIn", 0, VISION_SPARSE_THRESHOLD) is True


def test_should_vision_label_dump_floorplan():
    # Many short labels (avg line ~5) + heavy vector drawings -> diagram.
    text = "\n".join(["RX", "TX", "MX64", "PClkBufIn", "PClkBufOut"] * 60)
    assert _should_use_vision(text, DIAGRAM_MIN_DRAWINGS + 50, VISION_SPARSE_THRESHOLD) is True


def test_should_vision_label_dump_but_few_drawings_is_false():
    # Short lines but little vector content -> not treated as a diagram
    # (avoids over-triggering on short-line text that is not a figure).
    text = "\n".join(["RX", "TX", "MX64", "PClkBufIn", "PClkBufOut"] * 60)
    assert _should_use_vision(text, 5, VISION_SPARSE_THRESHOLD) is False


def test_should_vision_register_table_is_false():
    # Register-table-like page: medium line length (~33), many drawings -> NOT
    # a diagram (text extraction is fine), must not trigger Vision.
    line = "0x1C00 GICD_ICACTIVERnE RW 0x0 32"  # ~33 chars
    text = "\n".join([line] * 40)
    assert _should_use_vision(text, 400, VISION_SPARSE_THRESHOLD) is False


def test_should_vision_prose_is_false():
    para = ("The GIC provides the local_chip_addr configuration parameter that "
            "controls cross-chip addressing across the multichip system.")
    text = "\n".join([para] * 20)
    assert _should_use_vision(text, 500, VISION_SPARSE_THRESHOLD) is False


# ---------------------------------------------------------------------------
# Property 13: Vision fallback safety (R7.4 / R7.5) — _resolve_page_text
# ---------------------------------------------------------------------------

from textualize import _resolve_page_text, VISION_SPARSE_THRESHOLD


def _render_ok():
    return b"\x89PNG fake-bytes"


def _render_should_not_be_called():
    raise AssertionError("render_png must not be called for non-sparse/disabled")


def test_vision_disabled_returns_raw_text():
    # R7.5: vision_describe=None -> original text, page never rendered.
    raw = "x"  # sparse, but Vision disabled
    out = _resolve_page_text(
        raw, render_png=_render_should_not_be_called,
        vision_describe=None, sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_skips_dense_page():
    # A page with enough text is never sent to Vision.
    raw = "a" * (VISION_SPARSE_THRESHOLD + 5)
    out = _resolve_page_text(
        raw, render_png=_render_should_not_be_called,
        vision_describe=lambda png: "SHOULD NOT BE USED",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_describes_sparse_page():
    raw = "PClkBufIn"  # sparse floorplan label
    out = _resolve_page_text(
        raw, render_png=_render_ok,
        vision_describe=lambda png: "Block diagram: PClkBufIn is an input clock buffer pin.",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert "input clock buffer" in out
    assert out != raw


def test_vision_failure_falls_back_to_raw():
    # R7.4: any Vision exception -> original text, parsing continues.
    raw = "sparse"

    def boom(png):
        raise RuntimeError("bedrock throttled")

    out = _resolve_page_text(
        raw, render_png=_render_ok, vision_describe=boom,
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_empty_result_falls_back_to_raw():
    raw = "sparse"
    out = _resolve_page_text(
        raw, render_png=_render_ok, vision_describe=lambda png: "   ",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw


def test_vision_render_failure_falls_back_to_raw():
    raw = "sparse"

    def render_boom():
        raise RuntimeError("pixmap failed")

    out = _resolve_page_text(
        raw, render_png=render_boom,
        vision_describe=lambda png: "desc",
        sparse_threshold=VISION_SPARSE_THRESHOLD,
    )
    assert out == raw
