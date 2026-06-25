"""Textualization layer + offset→(page, section) mapping for Tool_Guide_Parser.

This module implements **step 1** of the parser pipeline (design.md C2 step 1):

    "텍스트화: PDF는 pdftotext -layout, Markdown은 그대로.
     문자 오프셋 ↔ 페이지/섹션 매핑 테이블 구축."

Responsibilities (this task only — block scanning / object boundaries belong to
task 2.2):

1. Convert an input document into a single unified text string plus an
   :class:`OffsetMap` that, given a character offset into the unified text,
   returns the enclosing ``(page, section)``.

   * **Markdown** — the raw text is used verbatim. ``page`` is not meaningful
     for Markdown and is reported as ``None`` (consistent with the schema's
     ``Evidence.page: int | None``). Sections are derived from ATX headers
     (``#``, ``##`` …) so any offset maps to its enclosing section.
   * **PDF** — the external ``pdftotext -layout`` binary is invoked behind the
     small, injectable :func:`run_pdftotext_layout` function so unit tests never
     need ``pdftotext`` installed. Page boundaries are derived from form-feed
     (``\\f``) page breaks emitted by ``pdftotext``; sections are detected
     heuristically.

2. Detection primitives for the two error preconditions that let the later
   handler (task 4.1) stop extraction and persist *no* partial result:

   * empty / whitespace-only input  → :class:`ErrorReason.EMPTY_DOCUMENT`
   * unsupported format (not PDF/MD) → :class:`ErrorReason.UNSUPPORTED_FORMAT`

   These are surfaced as a typed :class:`TextualizationError` (and via the pure
   predicates :func:`detect_format` / :func:`is_empty_or_whitespace`). This task
   implements only the *detection* primitive; the transactional stop/rollback
   that guarantees no partial write lives in task 4.1.

Everything here is pure and deterministic (no randomness, no wall-clock, no
global state) except :func:`run_pdftotext_layout`, which is the single isolated
boundary to the external process.

Flat-module convention (mirrors rtl_parser_src / schema.py): absolute import,
no package.

Requirements validated: 2.1, 1.3, 1.4, 2.8
"""

import bisect
import functools
import logging
import re
import subprocess
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum

from schema import UNKNOWN

logger = logging.getLogger(__name__)

# An injectable Vision describer: maps rendered page PNG bytes to a text
# description (Requirement 7). ``None`` means Vision is disabled (default).
VisionDescriber = Callable[[bytes], str]

# Default text-sparse threshold (non-whitespace chars). Pages below this are
# candidates for Vision description (R7.1).
VISION_SPARSE_THRESHOLD: int = 100

# Secondary "label-dump diagram" detection (R7, refined): floorplan / block
# diagram pages are not text-sparse (they carry many short labels) but extract
# as a jumble. They are characterized by very short average line length AND
# heavy vector-drawing content. Calibrated from real UCIe PHY databook pages
# (floorplan label-dump: avg line ~5.5 chars, >800 drawings; register tables
# and prose stay well above the line-length threshold).
DIAGRAM_MAX_AVG_LINE_LEN: float = 12.0
DIAGRAM_MIN_DRAWINGS: int = 200

# Hard cap on Vision pages per document. Bounds total Vision work (render +
# Converse + the get_cdrawings detection cost) so even diagram/figure-saturated
# documents (e.g. ISA specs, full register maps with thousands of figure pages)
# finish within the Lambda timeout. Pages beyond the cap stay text-only — the
# document is still fully indexed, just without Vision on the overflow pages.
VISION_MAX_PAGES_PER_DOC: int = 200

# ---------------------------------------------------------------------------
# Format / error signalling (detection primitives)
# ---------------------------------------------------------------------------

# Recognised file extensions. Anything else is unsupported (R1.3 / R1.4).
_MARKDOWN_EXTENSIONS: frozenset[str] = frozenset({".md", ".markdown", ".mdown"})
_PDF_EXTENSIONS: frozenset[str] = frozenset({".pdf"})

# Magic bytes used only when the extension is unknown/missing.
_PDF_MAGIC: bytes = b"%PDF"

# Form-feed character that ``pdftotext`` emits at page breaks.
_FORM_FEED: str = "\f"


class InputFormat(Enum):
    """Supported input formats, plus the catch-all ``UNSUPPORTED`` (R1.3/R1.4)."""

    MARKDOWN = "markdown"
    PDF = "pdf"
    UNSUPPORTED = "unsupported"


class ErrorReason(Enum):
    """Identifiable error reasons for the textualization preconditions.

    Values align with design.md "Error Handling" status strings: the handler
    records ``error:<value>`` (e.g. ``error:empty_document``).
    """

    EMPTY_DOCUMENT = "empty_document"
    UNSUPPORTED_FORMAT = "unsupported_format"


class TextualizationError(Exception):
    """Raised when input cannot be textualized (empty or unsupported).

    Carries a machine-readable :class:`ErrorReason` so the caller (task 4.1)
    can stop extraction, return an identifiable error, and persist no partial
    result — without this module ever writing to any store.
    """

    def __init__(self, reason: ErrorReason, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or f"error:{reason.value}")

    @property
    def status(self) -> str:
        """The ``error:<reason>`` status string used by the handler."""
        return f"error:{self.reason.value}"


def _extension(filename: str) -> str:
    """Return the lowercased file extension including the dot (``""`` if none)."""
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    dot = base.rfind(".")
    if dot <= 0:  # no dot, or leading-dot dotfile with no real extension
        return ""
    return base[dot:].lower()


def detect_format(filename: str, head: bytes | None = None) -> InputFormat:
    """Determine the input format from extension, falling back to content.

    Determination considers the file extension first (cheap, deterministic). If
    the extension is unknown/missing and ``head`` (the first bytes of the file)
    is provided, PDF magic bytes are sniffed. Anything that is neither Markdown
    nor PDF is :attr:`InputFormat.UNSUPPORTED` (R1.3/R1.4).

    Args:
        filename: Source file name (may include a path; only the basename's
            extension matters).
        head: Optional leading bytes of the file content for magic sniffing.

    Returns:
        The detected :class:`InputFormat`.
    """
    ext = _extension(filename)
    if ext in _MARKDOWN_EXTENSIONS:
        return InputFormat.MARKDOWN
    if ext in _PDF_EXTENSIONS:
        return InputFormat.PDF
    if head is not None and head[: len(_PDF_MAGIC)] == _PDF_MAGIC:
        return InputFormat.PDF
    return InputFormat.UNSUPPORTED


def is_empty_or_whitespace(text: str) -> bool:
    """Return True if ``text`` is empty or contains only whitespace (R2.8).

    Form feeds and other whitespace count as empty: a PDF that extracts to only
    page breaks is treated as an empty document.
    """
    return text.strip() == ""


# ---------------------------------------------------------------------------
# Offset → (page, section) mapping structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionSpan:
    """A section that begins at ``start`` (inclusive) in the unified text."""

    start: int
    title: str


@dataclass(frozen=True)
class PageSpan:
    """A page (1-based) that begins at ``start`` (inclusive) in the unified text."""

    start: int
    page: int


@dataclass(frozen=True)
class OffsetMap:
    """Maps a character offset in the unified text to its ``(page, section)``.

    ``section_spans`` and ``page_spans`` are kept sorted by ``start`` ascending.
    ``page_spans`` is empty for Markdown (page is not meaningful → ``page_at``
    returns ``None``). Lookups are pure and use binary search for determinism.
    """

    section_spans: tuple[SectionSpan, ...]
    page_spans: tuple[PageSpan, ...]
    text_length: int

    def _check_offset(self, offset: int) -> None:
        if not 0 <= offset <= self.text_length:
            raise ValueError(
                f"offset {offset} out of range [0, {self.text_length}]"
            )

    def section_at(self, offset: int) -> str:
        """Return the title of the section enclosing ``offset``.

        Offsets before the first section header (or when no headers exist) map
        to the fixed :data:`~schema.UNKNOWN` placeholder (R3.4) — never guessed.
        """
        self._check_offset(offset)
        starts = [s.start for s in self.section_spans]
        idx = bisect.bisect_right(starts, offset) - 1
        if idx < 0:
            return UNKNOWN
        return self.section_spans[idx].title

    def page_at(self, offset: int) -> int | None:
        """Return the 1-based page enclosing ``offset``, or ``None`` for Markdown."""
        self._check_offset(offset)
        if not self.page_spans:
            return None
        starts = [p.start for p in self.page_spans]
        idx = bisect.bisect_right(starts, offset) - 1
        if idx < 0:
            # Defensive: page_spans always starts at 0, so this should not happen.
            return self.page_spans[0].page
        return self.page_spans[idx].page

    def locate(self, offset: int) -> tuple[int | None, str]:
        """Return ``(page, section)`` for ``offset`` in a single call."""
        return self.page_at(offset), self.section_at(offset)


@dataclass(frozen=True)
class TextualizationResult:
    """Unified text plus its offset→(page, section) mapping."""

    text: str
    mapping: OffsetMap
    input_format: InputFormat


# ---------------------------------------------------------------------------
# Section header detection (pure)
# ---------------------------------------------------------------------------

# ATX Markdown header: 1-6 leading '#', a space, then the title text.
_MD_HEADER_RE = re.compile(r"^(#{1,6})[ \t]+(\S.*?)[ \t]*$")

# Heuristic PDF section headers:
#   - numbered headings:  "4.2 Elaboration", "10  Overview"
#   - "Chapter N ..." / "Section N ..." / "Appendix ..." style headings
_PDF_NUMBERED_RE = re.compile(r"^[ \t]*(\d+(?:\.\d+)*)[ \t]+(\S.*?)[ \t]*$")
_PDF_KEYWORD_RE = re.compile(
    r"^[ \t]*(?:chapter|section|appendix)\b.*$", re.IGNORECASE
)


def _iter_lines_with_offsets(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line_start_offset, line)`` splitting strictly on ``\\n``.

    Deterministic. Splitting only on ``\\n`` (not the full Unicode line-boundary
    set used by :meth:`str.splitlines`) avoids splitting on form-feed page
    breaks. The yielded line has a trailing ``\\r`` removed for convenience; the
    start offset is the absolute position of the line in ``text`` so a detected
    header maps back to its exact location.
    """
    offset = 0
    for piece in text.split("\n"):
        yield offset, piece.rstrip("\r")
        offset += len(piece) + 1  # +1 for the consumed '\n'


def _find_markdown_sections(text: str) -> tuple[SectionSpan, ...]:
    """Detect ATX Markdown headers as section spans (deterministic)."""
    spans: list[SectionSpan] = []
    for start, line in _iter_lines_with_offsets(text):
        m = _MD_HEADER_RE.match(line)
        if m:
            spans.append(SectionSpan(start=start, title=m.group(2).strip()))
    return tuple(spans)


def _find_pdf_sections(text: str) -> tuple[SectionSpan, ...]:
    """Heuristically detect section headers in pdftotext output (deterministic).

    Form feeds are stripped from each line before matching so a header adjacent
    to a page break is still recognised; the section span still starts at the
    line's true offset.
    """
    spans: list[SectionSpan] = []
    for start, raw_line in _iter_lines_with_offsets(text):
        line = raw_line.strip("\f").strip()
        if not line:
            continue
        match_line = raw_line.strip("\f")
        if _PDF_NUMBERED_RE.match(match_line) or _PDF_KEYWORD_RE.match(match_line):
            spans.append(SectionSpan(start=start, title=line))
    return tuple(spans)


def _build_page_spans(text: str) -> tuple[PageSpan, ...]:
    """Build page spans from form-feed page breaks (page 1 starts at offset 0).

    The form-feed character that terminates page *N* belongs to page *N*; the
    character immediately after it begins page *N+1*.
    """
    spans: list[PageSpan] = [PageSpan(start=0, page=1)]
    page = 1
    for i, ch in enumerate(text):
        if ch == _FORM_FEED:
            page += 1
            spans.append(PageSpan(start=i + 1, page=page))
    return tuple(spans)


# ---------------------------------------------------------------------------
# Textualization (pure cores)
# ---------------------------------------------------------------------------


def textualize_markdown(text: str) -> TextualizationResult:
    """Textualize Markdown: the raw text is used as-is (design.md C2 step 1).

    Sections come from ATX headers; ``page`` is ``None`` (not meaningful for MD).

    Raises:
        TextualizationError: If the text is empty or whitespace-only (R2.8).
    """
    if is_empty_or_whitespace(text):
        raise TextualizationError(ErrorReason.EMPTY_DOCUMENT)
    mapping = OffsetMap(
        section_spans=_find_markdown_sections(text),
        page_spans=(),  # page not meaningful for Markdown
        text_length=len(text),
    )
    return TextualizationResult(
        text=text, mapping=mapping, input_format=InputFormat.MARKDOWN
    )


def textualize_pdf_output(pdftotext_text: str) -> TextualizationResult:
    """Textualize already-extracted ``pdftotext -layout`` output (pure core).

    Page mapping is derived from form-feed (``\\f``) page breaks; sections are
    detected heuristically. Separating this pure function from the external call
    lets the page/section mapping be tested without ``pdftotext`` installed.

    Raises:
        TextualizationError: If the extracted text is empty/whitespace-only.
    """
    if is_empty_or_whitespace(pdftotext_text):
        raise TextualizationError(ErrorReason.EMPTY_DOCUMENT)
    mapping = OffsetMap(
        section_spans=_find_pdf_sections(pdftotext_text),
        page_spans=_build_page_spans(pdftotext_text),
        text_length=len(pdftotext_text),
    )
    return TextualizationResult(
        text=pdftotext_text, mapping=mapping, input_format=InputFormat.PDF
    )


# ---------------------------------------------------------------------------
# External-command boundary (isolated, injectable)
# ---------------------------------------------------------------------------


def _should_use_vision(
    text: str, drawing_count: int, sparse_threshold: int
) -> bool:
    """Return True if a page should be sent to Vision (R7 detection).

    Two independent signals:
    * **text-sparse** — fewer than ``sparse_threshold`` non-whitespace chars
      (near-empty diagram page; original R7.1), or no real lines at all.
    * **label-dump diagram** — very short average line length
      (< :data:`DIAGRAM_MAX_AVG_LINE_LEN`) AND heavy vector drawing
      (``drawing_count`` >= :data:`DIAGRAM_MIN_DRAWINGS`). Catches floorplan /
      block-diagram pages that carry many short labels (so they are not
      text-sparse) yet extract as a jumble. Register tables and prose have
      longer average lines and are not matched.
    """
    stripped = text.strip()
    if len(stripped) < sparse_threshold:
        return True
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    avg_len = sum(len(ln) for ln in lines) / len(lines)
    return avg_len < DIAGRAM_MAX_AVG_LINE_LEN and drawing_count >= DIAGRAM_MIN_DRAWINGS


def _resolve_page_text(
    raw_text: str,
    *,
    render_png: Callable[[], bytes],
    vision_describe: VisionDescriber | None,
    sparse_threshold: int,
    drawing_count: int = 0,
) -> str:
    """Return a page's text, substituting a Vision description when the page is
    a diagram (text-sparse or label-dump; see :func:`_should_use_vision`).

    Requirement 7 (with R7.4 fallback safety). Pure except for the two injected
    callables, so it is unit-testable without pymupdf or AWS:

    * ``vision_describe is None``  -> return ``raw_text`` (Vision disabled, R7.5).
    * not a diagram page -> return ``raw_text``.
    * diagram page + describer -> render the page and return the description;
      on ANY failure or empty result, fall back to ``raw_text`` (R7.4) so
      parsing never stops.
    """
    if vision_describe is None:
        return raw_text
    if not _should_use_vision(raw_text, drawing_count, sparse_threshold):
        return raw_text
    try:
        png = render_png()
        desc = vision_describe(png)
        if desc and desc.strip():
            return desc
    except Exception as exc:  # noqa: BLE001 — R7.4: never stop parsing on Vision error
        logger.warning("Vision describe failed; using original page text: %s", exc)
    return raw_text


def _page_drawing_count(page: object, text: str) -> int:
    """Count vector drawings, but only for label-dense pages (cost pre-filter).

    ``get_cdrawings()`` can be costly on large pages, so it is only computed
    when the page's average line length is short enough to *possibly* be a
    label-dump diagram; prose/table pages (longer lines) return 0 immediately.
    Falls back gracefully to 0 on any pymupdf error.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 0
    avg_len = sum(len(ln) for ln in lines) / len(lines)
    if avg_len >= DIAGRAM_MAX_AVG_LINE_LEN:
        return 0
    try:
        return len(page.get_cdrawings())  # type: ignore[attr-defined]
    except Exception:
        try:
            return len(page.get_drawings())  # type: ignore[attr-defined]
        except Exception:
            return 0


def run_pdftotext_layout(
    pdf_path: str,
    *,
    vision_describe: VisionDescriber | None = None,
    sparse_threshold: int = VISION_SPARSE_THRESHOLD,
) -> str:
    """Extract text from a PDF file using pymupdf (fitz), falling back to
    the ``pdftotext -layout`` external binary when pymupdf is unavailable.

    pymupdf is the preferred backend because it is a pure-Python package that
    can be bundled in the Lambda deployment zip without installing system
    binaries.  Pages are separated by form-feed (``\\f``) to match the
    ``pdftotext -layout`` output that the rest of the pipeline expects.

    When ``vision_describe`` is provided (Requirement 7), pages whose extracted
    text is sparse (< ``sparse_threshold`` non-whitespace chars) are rendered to
    a PNG and replaced by a Vision-generated description. Vision failures fall
    back to the original page text (R7.4). ``vision_describe=None`` (default)
    disables Vision entirely with no added cost (R7.5).

    Args:
        pdf_path: Path to the source PDF file.
        vision_describe: Optional ``(png_bytes) -> str`` describer (R7).
        sparse_threshold: Non-whitespace char threshold for sparse pages (R7.1).

    Returns:
        The extracted text (form-feed separated pages) decoded as UTF-8.

    Raises:
        RuntimeError: If neither pymupdf nor pdftotext is available, or if
            extraction fails.
    """
    # --- Attempt 1: pymupdf (bundled Python package, preferred in Lambda) ---
    try:
        # PyMuPDF >= 1.24 exposes the canonical module as ``pymupdf``; the legacy
        # ``fitz`` alias re-exports via ``from pymupdf import *`` and may omit
        # ``open`` (not in pymupdf.__all__), so import ``pymupdf`` directly and
        # fall back to ``fitz`` only for older builds.
        try:
            import pymupdf as _pymupdf  # type: ignore[import]
        except ImportError:
            import fitz as _pymupdf  # type: ignore[import]

        doc = _pymupdf.open(pdf_path)
        # Phase 1 (sequential, cheap): extract each page's text and, for pages
        # that need Vision (R7), pre-render the page to PNG. Page objects cannot
        # outlive doc.close(), so all rendering happens here.
        page_texts: list[str] = []
        vision_jobs: dict[int, bytes] = {}  # page index -> rendered PNG
        for idx, page in enumerate(doc):
            text = page.get_text("text")  # preserves whitespace layout
            page_texts.append(text)
            # Stop Vision detection once the per-doc cap is reached — bounds the
            # render/Converse/get_cdrawings cost so figure-saturated docs (ISA
            # specs, full register maps) cannot exceed the Lambda timeout.
            if vision_describe is not None and len(vision_jobs) < VISION_MAX_PAGES_PER_DOC:
                drawing_count = _page_drawing_count(page, text)
                if _should_use_vision(text, drawing_count, sparse_threshold):
                    try:
                        vision_jobs[idx] = page.get_pixmap(dpi=200).tobytes("png")
                    except Exception as exc:  # noqa: BLE001 — R7.4 fallback
                        logger.warning("page render failed (idx %d): %s", idx, exc)
        doc.close()

        # Phase 2 (parallel): describe the diagram pages via Vision. Bedrock
        # calls are I/O-bound and independent, so a thread pool keeps even
        # diagram-heavy documents well within the Lambda timeout. Any failure or
        # empty result keeps the original page text (R7.4 — never stop parsing).
        if vision_jobs:
            def _describe(item: tuple[int, bytes]) -> tuple[int, str | None]:
                page_idx, png = item
                try:
                    desc = vision_describe(png)  # type: ignore[misc]
                    return page_idx, (desc if desc and desc.strip() else None)
                except Exception as exc:  # noqa: BLE001 — R7.4 fallback
                    logger.warning("Vision describe failed (idx %d): %s", page_idx, exc)
                    return page_idx, None

            with ThreadPoolExecutor(max_workers=8) as executor:
                for page_idx, desc in executor.map(_describe, list(vision_jobs.items())):
                    if desc:
                        page_texts[page_idx] = desc

        # Join pages with form-feed to match pdftotext -layout output format.
        return "\f".join(page_texts)
    except ImportError:
        pass  # pymupdf not installed — fall through to pdftotext
    except Exception as exc:
        raise RuntimeError(f"pymupdf extraction failed: {exc}") from exc

    # --- Attempt 2: pdftotext external binary (fallback for local dev) ---
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as exc:  # pdftotext not installed
        raise RuntimeError(
            "PDF extraction failed: pymupdf (fitz) is not installed and "
            "pdftotext binary was not found. Install pymupdf: pip install pymupdf"
        ) from exc
    except subprocess.CalledProcessError as exc:  # non-zero exit
        raise RuntimeError(
            f"pdftotext failed (exit {exc.returncode}): {exc.stderr!r}"
        ) from exc
    return completed.stdout.decode("utf-8", errors="replace")


# Type alias for an injectable pdftotext runner.
PdfTextRunner = Callable[[str], str]


def textualize_pdf(
    pdf_path: str,
    *,
    runner: PdfTextRunner = run_pdftotext_layout,
) -> TextualizationResult:
    """Textualize a PDF by running ``pdftotext -layout`` (runner is injectable).

    Args:
        pdf_path: Path to the source PDF.
        runner: Callable that extracts text from a PDF path. Defaults to
            :func:`run_pdftotext_layout`; tests inject a fake.

    Raises:
        TextualizationError: If extracted text is empty/whitespace-only (R2.8).
    """
    return textualize_pdf_output(runner(pdf_path))


# ---------------------------------------------------------------------------
# Unified entry point (detection + dispatch)
# ---------------------------------------------------------------------------


def textualize_document(
    filename: str,
    *,
    markdown_text: str | None = None,
    pdf_path: str | None = None,
    head: bytes | None = None,
    pdftotext_runner: PdfTextRunner = run_pdftotext_layout,
    vision_describe: VisionDescriber | None = None,
    sparse_threshold: int = VISION_SPARSE_THRESHOLD,
) -> TextualizationResult:
    """Detect format and textualize, raising a typed error for the stop paths.

    This is the detection-and-dispatch primitive the handler (task 4.1) builds
    its transactional stop/rollback on. It performs **no** persistence.

    Args:
        filename: Source file name (drives format detection).
        markdown_text: Raw Markdown text (required when the format is Markdown).
        pdf_path: Path to the PDF (required when the format is PDF).
        head: Optional leading bytes for magic-byte sniffing of unknown
            extensions.
        pdftotext_runner: Injectable PDF text extractor (for PDF inputs).
        vision_describe: Optional Vision describer (R7). When set, sparse PDF
            pages are described via Vision; ``None`` disables Vision (R7.5).
        sparse_threshold: Non-whitespace char threshold for sparse pages (R7.1).

    Returns:
        A :class:`TextualizationResult`.

    Raises:
        TextualizationError: With :attr:`ErrorReason.UNSUPPORTED_FORMAT` for
            non-PDF/Markdown input (R1.4), or :attr:`ErrorReason.EMPTY_DOCUMENT`
            for empty/whitespace-only content (R2.8).
        ValueError: If the source argument for the detected format is missing.
    """
    fmt = detect_format(filename, head=head)
    if fmt is InputFormat.MARKDOWN:
        if markdown_text is None:
            raise ValueError("markdown_text is required for Markdown input")
        return textualize_markdown(markdown_text)
    if fmt is InputFormat.PDF:
        if pdf_path is None:
            raise ValueError("pdf_path is required for PDF input")
        runner = pdftotext_runner
        # R7: bind Vision into the runner only when enabled, so injected test
        # runners (Vision disabled) keep their simple (pdf_path) signature.
        if vision_describe is not None:
            runner = functools.partial(
                pdftotext_runner,
                vision_describe=vision_describe,
                sparse_threshold=sparse_threshold,
            )
        return textualize_pdf(pdf_path, runner=runner)
    raise TextualizationError(ErrorReason.UNSUPPORTED_FORMAT)
