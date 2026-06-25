"""Deterministic block scanning + object boundary detection (pure core).

This module implements **step 2** ("블록 스캔 (결정론적)") and **step 4**
("잔여 구간 처리") of the parser pipeline described in design.md C2, and is the
heart of the future ``parse_structure``. It consumes the *unified text* produced
by :mod:`textualize` and returns a list of :class:`ParsedObject` whose
``[start_offset, end_offset)`` half-open intervals **tile the entire text**
contiguously with no gaps and no overlaps.

Detection is label/structure based only — no LLM, no external state, no
wall-clock, no randomness — so the function is pure and deterministic (R2.2 /
R2.7): identical input always yields an identical object list (same count, same
boundaries, same ``object_type`` ordering). This is the property Property 1
later verifies.

Rules (design.md C2 step 2 examples):

* **command** — header labels ``Command:``, ``SYNTAX``, ``Usage:``
* **option**  — ``Options:`` / ``Arguments:`` blocks and ``-opt`` / ``--opt``
  definition lines
* **flow_step** — methodology / flow step headers (``Flow:``, ``Methodology``,
  ``Step N``, ``Procedure``)
* **example** — fenced code blocks (```` ``` ```` / ``~~~``) and ``Example``
  labels

Every region not captured by a rule-matched block is wrapped into a
``section`` object so the union of all objects covers 100% of the text (R2.5,
Property 2). The result is stable-sorted by ``start_offset`` ascending.

Scope note: ``belongs_to`` relations (task 2.3), metadata / canonical_text
(task 3.x) and persistence are intentionally **out of scope** here. All five
``object_type`` values are classified structurally even though MVP indexing
(R6.1) only activates ``command``/``option``; later activation needs no schema
or pipeline change (R6.5).

Flat-module convention (mirrors schema.py / textualize.py): absolute import,
no package.

Requirements validated: 2.1, 2.2, 2.5
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from schema import OBJECT_TYPES, is_allowed_object_type

# Form-feed character that ``pdftotext`` emits at page breaks; stripped from a
# line before label matching so a header adjacent to a page break still matches.
_FORM_FEED: str = "\f"


# ---------------------------------------------------------------------------
# Parsed object (block) data structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedObject:
    """A detected block with half-open text bounds and a structural type.

    Attributes:
        start_offset: Inclusive start offset into the unified text.
        end_offset: Exclusive end offset (``[start, end)`` half-open, matching
            textualize / Property 2's convention).
        object_type: One of the closed :data:`~schema.OBJECT_TYPES` set.

    Frozen (immutable + hashable) to support use as a deterministic key and to
    make accidental mutation impossible during later pipeline stages.
    """

    start_offset: int
    end_offset: int
    object_type: str

    def __post_init__(self) -> None:
        if not is_allowed_object_type(self.object_type):
            raise ValueError(
                f"object_type {self.object_type!r} not in allowed set "
                f"{sorted(OBJECT_TYPES)}"
            )
        if self.start_offset < 0:
            raise ValueError(f"start_offset {self.start_offset} must be >= 0")
        if self.end_offset <= self.start_offset:
            raise ValueError(
                f"end_offset {self.end_offset} must be > start_offset "
                f"{self.start_offset}"
            )

    @property
    def length(self) -> int:
        """Number of characters spanned by this block."""
        return self.end_offset - self.start_offset


# ---------------------------------------------------------------------------
# Label / structure rules (data-driven, ordered by priority)
# ---------------------------------------------------------------------------

# A fenced code block opener/closer line: ``` or ~~~ (optionally indented, with
# an optional info string). Handled with explicit open/close state so code
# *content* is never mis-classified as a header.
_FENCE_RE = re.compile(r"^[ \t]*(?:`{3,}|~{3,})")

# command headers: "Command:", "SYNTAX", "Usage:" (line-anchored, case-insensitive).
_COMMAND_RE = re.compile(r"^[ \t]*(?:command|syntax|usage)\b[ \t]*:?", re.IGNORECASE)

# option labels: "Options:", "Arguments:".
_OPTION_LABEL_RE = re.compile(
    r"^[ \t]*(?:options|arguments)\b[ \t]*:?", re.IGNORECASE
)
# option definition line: "-o", "--flag" (a dash run immediately followed by a
# letter — excludes "- bullet" items and "---" horizontal rules).
_OPTION_DASH_RE = re.compile(r"^[ \t]*-{1,2}[A-Za-z]")

# flow / methodology headers: "Flow:", "Methodology", "Step N", "Procedure".
_FLOW_RE = re.compile(
    r"^[ \t]*(?:flow|methodology|procedure|step)\b[ \t]*:?", re.IGNORECASE
)

# example label: "Example", "Examples:".
_EXAMPLE_LABEL_RE = re.compile(r"^[ \t]*examples?\b[ \t]*:?", re.IGNORECASE)

# Ordered (regex, object_type) table. First match wins, giving deterministic
# classification. Fenced code blocks are handled separately (stateful) before
# this table is consulted.
_LABEL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (_COMMAND_RE, "command"),
    (_OPTION_LABEL_RE, "option"),
    (_OPTION_DASH_RE, "option"),
    (_FLOW_RE, "flow_step"),
    (_EXAMPLE_LABEL_RE, "example"),
)

# Precision guard: maximum length (chars, stripped) for a keyword-label line to
# still count as a header. Real tool-guide headers are short ("SYNTAX",
# "Options:", "Step 2 build"); a keyword followed by a long run of prose
# (common in register-reference manuals) is body text, not a header. The
# dash-option rule is exempt (option definitions carry long inline descriptions).
_MAX_HEADER_LINE_LEN: int = 80


def _iter_lines_with_offsets(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line_start_offset, line)`` splitting strictly on ``\\n``.

    Deterministic. Splitting only on ``\\n`` (not the full Unicode line-boundary
    set) avoids splitting on form-feed page breaks; each yielded offset is the
    absolute position of the line so a detected header maps to its exact start.
    A trailing ``\\r`` is removed for convenience.
    """
    offset = 0
    for piece in text.split("\n"):
        yield offset, piece.rstrip("\r")
        offset += len(piece) + 1  # +1 for the consumed '\n'


def _classify_line(line: str) -> str | None:
    """Return the ``object_type`` a non-fence line begins, or ``None``.

    The line is matched against :data:`_LABEL_RULES` in priority order; the
    first matching rule wins (deterministic).

    Precision guard (register-reference manuals): a keyword label (command /
    syntax / usage / options / flow / step / example ...) followed by a long
    run of prose on the same line is **not** a header — real headers are short.
    Without this guard, sentences like "Command ... permitted to be hardwired
    to 000b ..." in register manuals are mis-classified as ``command`` blocks.
    The dash-defined option rule (``-o``) is exempt because option definition
    lines legitimately carry a long inline description.
    """
    stripped = line.strip()
    for pattern, object_type in _LABEL_RULES:
        if pattern.match(line):
            if pattern is _OPTION_DASH_RE or len(stripped) <= _MAX_HEADER_LINE_LEN:
                return object_type
            # Keyword label but the line is long prose, not a header.
            return None
    return None


def _detect_headers(text: str) -> list[tuple[int, str]]:
    """Detect block-header offsets and their types, in ascending offset order.

    Fenced code blocks are tracked with explicit open/close state: the opening
    fence line starts an ``example`` block and, until the matching closing fence,
    no inner line is classified as a header (so code content cannot masquerade
    as a label). The closing fence line stays part of the example block and does
    not open a new block.
    """
    headers: list[tuple[int, str]] = []
    in_fence = False
    for start, raw_line in _iter_lines_with_offsets(text):
        line = raw_line.strip(_FORM_FEED)
        if _FENCE_RE.match(line):
            if not in_fence:
                headers.append((start, "example"))
                in_fence = True
            else:
                in_fence = False
            continue
        if in_fence:
            continue
        object_type = _classify_line(line)
        if object_type is not None:
            headers.append((start, object_type))
    return headers


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def scan_blocks(text: str) -> list[ParsedObject]:
    """Scan ``text`` and return fully-tiled, start-sorted :class:`ParsedObject`.

    Pure and deterministic (R2.2 / R2.7). The returned objects:

    * tile ``[0, len(text))`` contiguously — no gaps, no overlaps — so their
      union covers 100% of the text (and thus every non-whitespace character),
      satisfying the coverage invariant (R2.5, Property 2);
    * carry an ``object_type`` from the closed :data:`~schema.OBJECT_TYPES` set;
    * are stable-sorted by ``start_offset`` ascending.

    Boundary model: each detected header begins a block that runs until the next
    header (or end of text). Any region preceding the first header — i.e. text
    matched by no rule — is wrapped as a ``section`` object so nothing is lost.

    Args:
        text: The unified document text (from :mod:`textualize`).

    Returns:
        The detected blocks. An empty string yields an empty list (the union of
        no intervals trivially equals the empty range ``[0, 0)``).
    """
    length = len(text)
    if length == 0:
        return []

    headers = _detect_headers(text)
    objects: list[ParsedObject] = []

    # Step 4 — residual handling: the region before the first header (or the
    # whole text when no header matched) is preserved as a ``section`` object so
    # the tiling starts at offset 0 with no gap (R2.5).
    first_header_start = headers[0][0] if headers else length
    if first_header_start > 0:
        objects.append(ParsedObject(0, first_header_start, "section"))

    # Each header's block runs until the next header start (or end of text),
    # making the blocks tile contiguously to ``length``.
    for i, (start, object_type) in enumerate(headers):
        end = headers[i + 1][0] if i + 1 < len(headers) else length
        objects.append(ParsedObject(start, end, object_type))

    # Stable sort by start_offset ascending (R2.2). Detection already yields
    # ascending offsets, so this is a guaranteed-stable no-op that makes the
    # ordering contract explicit and robust to future changes.
    objects.sort(key=lambda obj: obj.start_offset)
    return objects
