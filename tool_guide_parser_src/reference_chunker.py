"""Reference-document chunking (size-based) for IP register databooks.

Why this module exists
----------------------
The label-based parser (:mod:`blockscan` / :mod:`build_objects`) was designed
for man-page-style EDA tool *command* guides (``Command:``, ``Options:``,
``SYNTAX`` ...). The Atlas corpus, however, is dominated by **IP register
databooks / reference manuals** which have no "commands" in that sense. Running
the label heuristics on them produces garbage ``command`` objects (e.g. a
register-table column literally named "Command") and, worse, embeds only a
one-line template as ``canonical_text`` — so the actual register/field prose
never reaches the vector.

``chunk_reference`` is the corpus-appropriate strategy (design: PARSE_MODE
``reference``):

* **No label heuristics** — every chunk is ``object_type="section"``; the
  ``command``/``flow_step``/``example`` false positives disappear entirely.
* **Content-bearing ``canonical_text``** — the chunk's *real text* is embedded
  (size-bounded), so register/field descriptions are retrievable.
* **Citations preserved** — ``source_file`` + ``page`` + section title come
  from the :class:`~textualize.OffsetMap` at the chunk's start offset, exactly
  like :mod:`build_objects` (R3.3).

Chunking is size-based (Standard RAG): a target window in characters, broken at
the nearest line boundary, with a small overlap so a concept split across a
boundary is still captured by one chunk. It is fully deterministic (R2.2 / R2.7)
— no LLM, no randomness — identical input yields an identical chunk list.

Defaults: ``chunk_size=2000`` chars (~500 tokens, far under the Titan Embed v2
8192-token limit), ``overlap=200`` chars (10%). The existing token-length guard
in :mod:`aws_ingest_store` remains the backstop.

Flat-module convention: absolute imports, no package.

Requirements validated: 2.7, 3.1, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

from identifiers import make_object_id, normalize_identifier
from schema import (
    UNKNOWN,
    Evidence,
    ToolGuideMetadata,
    ToolGuideObject,
)
from textualize import OffsetMap

# Default size-based chunking parameters (chars).
DEFAULT_CHUNK_SIZE: int = 3000
DEFAULT_OVERLAP: int = 200

# How far back from the hard cut we look for a clean newline boundary.
_LINE_BREAK_WINDOW: int = 300


def _clean_break_end(text: str, start: int, hard_end: int) -> int:
    """Return a chunk end <= ``hard_end`` that prefers a line boundary.

    Looks for the last ``\\n`` in ``[hard_end - _LINE_BREAK_WINDOW, hard_end)``
    and breaks just after it (so lines are not split mid-sentence). Falls back
    to ``hard_end`` (a hard cut) when no newline is found in the window. The
    returned end is always ``> start`` and ``<= hard_end`` (never moves
    forward), so chunks never exceed ``chunk_size`` characters.
    """
    if hard_end >= len(text):
        return len(text)
    window_start = max(start + 1, hard_end - _LINE_BREAK_WINDOW)
    nl = text.rfind("\n", window_start, hard_end)
    if nl != -1 and nl > start:
        return nl + 1
    return hard_end


def chunk_reference(
    text: str,
    *,
    tool_name: str,
    tool_version: str,
    doc_version: str,
    source_file: str,
    offset_map: OffsetMap,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[ToolGuideObject]:
    """Chunk ``text`` into size-based, content-bearing ``section`` objects.

    Pure and deterministic. Whitespace-only chunks are skipped. Each emitted
    object carries the chunk's real text as ``canonical_text`` and a citation
    (``source_file`` + ``page`` + section title) resolved from ``offset_map`` at
    the chunk start (R3.3). IDs are deterministic per (tool, doc_version, start
    offset) so re-ingesting the same document is idempotent (R1.6 / R3.6).

    Args:
        text: Unified document text (from :mod:`textualize`).
        tool_name: Tool/IP name from the upload key path; normalized (R3.6).
        tool_version: Tool version from the key path; normalized.
        doc_version: Document version from the key path; normalized.
        source_file: Bare source file name for the citation.
        offset_map: :class:`~textualize.OffsetMap` for page/section lookup.
        chunk_size: Target chunk length in characters.
        overlap: Overlap in characters between consecutive chunks.

    Returns:
        A list of :class:`~schema.ToolGuideObject` (all ``object_type="section"``)
        in document order. An empty/blank document yields an empty list.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be > 0, got {chunk_size}")
    if not (0 <= overlap < chunk_size):
        raise ValueError(
            f"overlap must satisfy 0 <= overlap < chunk_size, got {overlap}"
        )

    norm_tool = normalize_identifier(tool_name) if tool_name else UNKNOWN
    norm_version = normalize_identifier(tool_version) if tool_version else UNKNOWN
    norm_doc_ver = normalize_identifier(doc_version) if doc_version else UNKNOWN
    sf = source_file if source_file else UNKNOWN

    n = len(text)
    objects: list[ToolGuideObject] = []
    start = 0

    while start < n:
        hard_end = min(start + chunk_size, n)
        end = _clean_break_end(text, start, hard_end)

        chunk = text[start:end]
        stripped = chunk.strip()
        if stripped:
            page, section_raw = offset_map.locate(start)
            section_title = section_raw if section_raw else UNKNOWN

            obj_id = make_object_id(
                tool_name=norm_tool,
                doc_version=norm_doc_ver,
                object_type="section",
                name=f"offset{start}",
            )

            metadata = ToolGuideMetadata(
                tool_name=norm_tool,
                tool_version=norm_version,
                command=UNKNOWN,
                option=UNKNOWN,
                section=section_title,
                doc_version=norm_doc_ver,
                object_type="section",
            )

            ev_section: str | None = (
                section_title if section_title != UNKNOWN else None
            )
            # R3.3 invariant: at least one of page / section must be present.
            if page is None and ev_section is None:
                ev_section = UNKNOWN
            evidence = Evidence(
                source_file=sf,
                doc_version=norm_doc_ver,
                page=page,
                section=ev_section,
            )

            objects.append(
                ToolGuideObject(
                    id=obj_id,
                    object_type="section",
                    canonical_text=stripped,
                    metadata=metadata,
                    evidence=evidence,
                )
            )

        # Stop once the chunk reaches end-of-text; advancing by overlap here
        # would only re-emit the tail as a spurious extra chunk.
        if end >= n:
            break

        # Advance with overlap; guarantee forward progress.
        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start

    return objects
