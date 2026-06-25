"""Object builder: ``build_objects`` — metadata, evidence, and canonical_text.

This module implements **design.md C2 steps 6 and 7**:

    Step 6: canonical_text 생성 — 각 객체 1개당 1문장(임베딩 단위).
            결정론적 템플릿 우선, 서술 요약이 필요한 section/example만 LLM 보조.
    Step 7: 메타데이터 채움 — 7개 필드. 원문 미확인 값은 "미확인" (R3.4).
            object_type 허용집합 검증 (R3.2).

``build_objects`` is the second half of the parser pipeline: it consumes the
:class:`~relations.RelatedObject` list from :func:`~parse_structure.parse_structure`
together with document-level metadata (tool_name, doc_version, source_file) and
the :class:`~textualize.OffsetMap`, and produces a :class:`~schema.ToolGuideObject`
list (the fully-populated ``claim-db``-shaped records).

Design contracts enforced here
-------------------------------
* R3.2 — ``object_type`` must be in ``OBJECT_TYPES``; any block with a
  disallowed type is **silently skipped** (not produced). In practice
  :func:`~blockscan.scan_blocks` never emits an out-of-set type, but
  ``build_objects`` acts as the last enforcement gate.
* R3.4 — a field value that cannot be determined from the source text
  (origin text of the block, the document key path, etc.) is set to the
  fixed placeholder :data:`~schema.UNKNOWN` (``"미확인"``). No inference,
  no defaults, no guessing.
* R3.3 — every :class:`~schema.Evidence` record must carry ``source_file``,
  ``doc_version`` **and** at least one of ``page`` / ``section``. If neither
  can be determined from the :class:`~textualize.OffsetMap` the section field
  falls back to :data:`~schema.UNKNOWN` (making the section field present and
  non-None) so the invariant is always satisfied.
* R2.6 / R3.5 — exactly one non-empty ``canonical_text`` per object.
* R3.5 — the resulting dict has the 5 top-level fields required by the
  shared ``claim-db`` schema.
* R3.6 — ``id`` generation uses :func:`~identifiers.make_object_id` whose
  inputs are normalized (case-fold + trim) before assembly.

Canonical-text templates (deterministic, LLM-free)
----------------------------------------------------
All five object types have a fully deterministic template that produces a
non-empty sentence. Section / example blocks can optionally receive an LLM
summary via the injectable ``summarize`` callback; if the callback is ``None``
(the default, and required for determinism tests) the template fallback is
always used, so tests remain LLM-independent and repeatable.

    command    -> "Command '<name>': <synopsis_line>."
    option     -> "Option '<name>': <description_first_line>."
    flow_step  -> "Flow step '<name>': <first_line>."
    example    -> "Example: <first_non_empty_line>."
    section    -> "Section '<section_title>': <first_non_empty_line>."

``<first_non_empty_line>`` is the first non-blank line of the block text (so
the template is never empty even for sparse blocks).

Flat-module convention (mirrors blockscan / relations / schema): absolute import,
no package.

Requirements validated: 2.6, 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

import re
from collections.abc import Callable

from identifiers import make_object_id, normalize_identifier
from relations import RelatedObject
from schema import (
    OBJECT_TYPES,
    UNKNOWN,
    Evidence,
    ToolGuideMetadata,
    ToolGuideObject,
    is_allowed_object_type,
)
from textualize import OffsetMap

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# An injectable LLM summarizer: given the raw block text and its object_type,
# returns a short descriptive sentence. Defaults to None (deterministic mode).
Summarizer = Callable[[str, str], str] | None

# Regex to strip common command header label prefixes from the first line.
_COMMAND_LABEL_RE = re.compile(
    r"^(?:command|syntax|usage)\b\s*:?\s*",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers: block name extraction (deterministic, LLM-free)
# ---------------------------------------------------------------------------


def _first_nonblank_line(text: str) -> str:
    """Return the first non-blank line of ``text``, stripped.

    Falls back to :data:`~schema.UNKNOWN` when the text is completely blank.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return UNKNOWN


def _extract_name(block_text: str, object_type: str) -> str:
    """Extract a short name/label for an object from its block text (deterministic).

    The name feeds :func:`~identifiers.make_object_id` (``<name>`` segment) and
    also appears in the ``canonical_text`` template. Extraction is purely
    structural (first non-blank line, stripped) — no LLM, no inference.

    For ``command`` blocks the first line often contains the full ``Command: <name>``
    label; we strip the label prefix to get just the command name.

    Returns:
        A non-empty string (max 128 chars); falls back to :data:`~schema.UNKNOWN`
        if nothing can be extracted.
    """
    first = _first_nonblank_line(block_text)
    if object_type == "command":
        cleaned = _COMMAND_LABEL_RE.sub("", first).strip()
        # If stripping emptied it (header-only line with no name), keep original.
        if cleaned:
            first = cleaned
    if not first or first == UNKNOWN:
        return UNKNOWN
    # Truncate to a sane length to keep IDs manageable.
    return first[:128]


# ---------------------------------------------------------------------------
# Helpers: canonical_text templates (deterministic)
# ---------------------------------------------------------------------------


def _canonical_text_command(name: str, block_text: str) -> str:
    """Deterministic canonical_text template for ``command`` objects."""
    lines = [line.strip() for line in block_text.splitlines() if line.strip()]
    # Use the second non-blank line as a synopsis when available.
    synopsis = lines[1] if len(lines) >= 2 else ""
    if synopsis:
        return f"Command '{name}': {synopsis}"
    return f"Command '{name}'."


def _canonical_text_option(name: str, block_text: str) -> str:
    """Deterministic canonical_text template for ``option`` objects."""
    lines = [line.strip() for line in block_text.splitlines() if line.strip()]
    # Use the second non-blank line as a description when available.
    desc = lines[1] if len(lines) >= 2 else (lines[0] if lines else "")
    if desc and desc != name:
        return f"Option '{name}': {desc}"
    return f"Option '{name}'."


def _canonical_text_flow_step(name: str, block_text: str) -> str:
    """Deterministic canonical_text template for ``flow_step`` objects."""
    lines = [line.strip() for line in block_text.splitlines() if line.strip()]
    desc = lines[1] if len(lines) >= 2 else ""
    if desc:
        return f"Flow step '{name}': {desc}"
    return f"Flow step '{name}'."


def _canonical_text_example(block_text: str, summarize: Summarizer) -> str:
    """Canonical_text for ``example`` objects.

    Uses the LLM summarizer when available; otherwise falls back to
    ``"Example: <first_non_blank_line>."`` (deterministic, no LLM).
    """
    if summarize is not None:
        return summarize(block_text, "example")
    first = _first_nonblank_line(block_text)
    return f"Example: {first}"


def _canonical_text_section(
    section_title: str, block_text: str, summarize: Summarizer
) -> str:
    """Canonical_text for ``section`` objects.

    Uses the LLM summarizer when available; otherwise falls back to
    ``"Section '<title>': <first_non_blank_line>."`` (deterministic, no LLM).
    """
    if summarize is not None:
        return summarize(block_text, "section")
    first = _first_nonblank_line(block_text)
    return f"Section '{section_title}': {first}"


def _make_canonical_text(
    object_type: str,
    name: str,
    block_text: str,
    section_title: str,
    summarize: Summarizer,
) -> str:
    """Dispatch to the per-type canonical_text builder (R2.6).

    Guarantees a non-empty string is always returned. Falls back through two
    levels of safety nets to ensure the contract holds even for edge-case inputs.
    """
    if object_type == "command":
        result = _canonical_text_command(name, block_text)
    elif object_type == "option":
        result = _canonical_text_option(name, block_text)
    elif object_type == "flow_step":
        result = _canonical_text_flow_step(name, block_text)
    elif object_type == "example":
        result = _canonical_text_example(block_text, summarize)
    elif object_type == "section":
        result = _canonical_text_section(section_title, block_text, summarize)
    else:
        # Defensive: build_objects filters out disallowed types before calling
        # this helper, so this branch should be unreachable.
        result = _first_nonblank_line(block_text)

    # Safety net 1: empty result from template (e.g. summarizer returned "").
    if not result or not result.strip():
        result = _first_nonblank_line(block_text)

    # Safety net 2: block was completely blank (upstream textualize should have
    # caught this; we still produce a valid non-empty string).
    if not result or not result.strip():
        result = f"{object_type} object"

    return result


# ---------------------------------------------------------------------------
# Metadata filling (R3.1, R3.4)
# ---------------------------------------------------------------------------


def _fill_metadata(
    *,
    object_type: str,
    tool_name: str,
    tool_version: str,
    doc_version: str,
    name: str,
    section_title: str,
    belongs_to_command_name: str | None,
) -> ToolGuideMetadata:
    """Populate the 7 metadata fields, using UNKNOWN for unconfirmed values (R3.4).

    All values come from deterministic extraction (block text, key path); nothing
    is inferred or guessed. :data:`~schema.UNKNOWN` is the explicit value for any
    field that cannot be confirmed from the source.
    """
    # ``command`` metadata field:
    #   - for command objects: the command name extracted from the block
    #   - for option objects: the owning command name (via belongs_to), if known
    #   - for all other types: UNKNOWN (cannot confirm from block alone)
    if object_type == "command":
        command_val = name if name and name != UNKNOWN else UNKNOWN
    elif object_type == "option" and belongs_to_command_name:
        command_val = belongs_to_command_name
    else:
        command_val = UNKNOWN

    # ``option`` metadata field: the option name for option objects only.
    option_val = name if object_type == "option" and name and name != UNKNOWN else UNKNOWN

    return ToolGuideMetadata(
        tool_name=tool_name if tool_name and tool_name != UNKNOWN else UNKNOWN,
        tool_version=tool_version if tool_version and tool_version != UNKNOWN else UNKNOWN,
        command=command_val,
        option=option_val,
        section=section_title if section_title and section_title != UNKNOWN else UNKNOWN,
        doc_version=doc_version if doc_version and doc_version != UNKNOWN else UNKNOWN,
        object_type=object_type,
    )


# ---------------------------------------------------------------------------
# Evidence filling (R3.3, R3.4)
# ---------------------------------------------------------------------------


def _fill_evidence(
    *,
    source_file: str,
    doc_version: str,
    page: int | None,
    section_title: str,
) -> Evidence:
    """Build an Evidence record satisfying R3.3.

    ``source_file`` and ``doc_version`` are required (R3.3); if unavailable
    they are set to :data:`~schema.UNKNOWN` (R3.4). At least one of ``page`` /
    ``section`` must be present (R3.3): if ``page`` is ``None`` and
    ``section_title`` is empty/UNKNOWN, section is set to :data:`~schema.UNKNOWN`
    — the explicit "confirmed unknown" value, not an inference (R3.4).
    """
    sf = source_file if source_file else UNKNOWN
    dv = doc_version if doc_version else UNKNOWN

    # Determine evidence section: use the title when it is a real string (not
    # empty and not UNKNOWN already). If it IS UNKNOWN but we still want the
    # field present, we keep it as None only when page is provided.
    ev_page = page  # int or None
    ev_section: str | None = (
        section_title if section_title and section_title != "" else None
    )

    # R3.3 invariant: at least one of page / section must be present.
    if ev_page is None and ev_section is None:
        # Neither page nor section could be determined from the source.
        # Set section to UNKNOWN (the explicit confirmed-unknown value, R3.4).
        ev_section = UNKNOWN

    return Evidence(
        source_file=sf,
        doc_version=dv,
        page=ev_page,
        section=ev_section,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_objects(
    related_objects: list[RelatedObject],
    *,
    text: str,
    tool_name: str,
    tool_version: str,
    doc_version: str,
    source_file: str,
    offset_map: OffsetMap,
    summarize: Summarizer = None,
) -> list[ToolGuideObject]:
    """Convert structural parse results into fully-populated ToolGuideObject records.

    This is the second half of the parser pipeline (design.md C2 steps 6 and 7).
    It consumes the :class:`~relations.RelatedObject` list from
    :func:`~parse_structure.parse_structure` together with document-level
    metadata and the :class:`~textualize.OffsetMap`, and emits a
    :class:`~schema.ToolGuideObject` list.

    Contract (enforced here, not just documented):
    * R3.2 — objects whose ``object_type`` is not in ``OBJECT_TYPES`` are
      **skipped** (not produced). Final enforcement gate.
    * R3.4 — unconfirmable fields are :data:`~schema.UNKNOWN` — no inference.
    * R2.6 — each returned object has exactly one non-empty ``canonical_text``.
    * R3.3 — each Evidence has source_file + doc_version + (page | section ≥ 1).
    * R3.5 — 5 top-level fields present on every returned object.
    * R3.6 — ``id`` inputs normalized (case-fold + trim) before assembly.

    Args:
        related_objects: Output of :func:`~parse_structure.parse_structure` —
            one :class:`~relations.RelatedObject` per detected block, start-sorted.
        text: The unified document text (from :mod:`textualize`). Used to slice
            out block text for each object.
        tool_name: Tool name from the upload key path (e.g. ``"VCS"``). Normalized
            per R3.6. May be empty string when unknown; becomes UNKNOWN.
        tool_version: Tool version from the upload key path. Normalized per R3.6.
            May be empty string when unknown; becomes UNKNOWN.
        doc_version: Document version from the upload key path. Normalized per R3.6.
        source_file: Source file name (e.g. ``"vcs_user_guide_2023.12.pdf"``).
        offset_map: :class:`~textualize.OffsetMap` for ``text``, providing
            page/section lookups for any character offset.
        summarize: Optional LLM summarizer ``(block_text, object_type) -> str``.
            When ``None`` (default) canonical_text uses deterministic templates
            only (LLM-free; required for property/determinism tests).

    Returns:
        A list of :class:`~schema.ToolGuideObject` records in input order
        (start-sorted). Objects with disallowed ``object_type`` values are
        excluded silently.
    """
    # Normalize document-level identifier inputs once (R3.6).
    norm_tool = normalize_identifier(tool_name) if tool_name else UNKNOWN
    norm_version = normalize_identifier(tool_version) if tool_version else UNKNOWN
    norm_doc_ver = normalize_identifier(doc_version) if doc_version else UNKNOWN

    # First pass: build a lookup from command start_offset → extracted command
    # name, so option objects can find their owning command's name for the
    # ``command`` metadata field.
    command_start_to_name: dict[int, str] = {}
    for ro in related_objects:
        if ro.obj.object_type == "command":
            block_text = text[ro.obj.start_offset : ro.obj.end_offset]
            cmd_name = _extract_name(block_text, "command")
            command_start_to_name[ro.obj.start_offset] = cmd_name

    objects_out: list[ToolGuideObject] = []

    for ro in related_objects:
        obj = ro.obj

        # R3.2 — skip objects with disallowed object_type (final gate).
        if not is_allowed_object_type(obj.object_type):
            continue

        block_text = text[obj.start_offset : obj.end_offset]
        object_type = obj.object_type

        # --- Name extraction (deterministic, LLM-free) ---
        name = _extract_name(block_text, object_type)

        # Build a unique id_name that incorporates the start_offset so the id
        # is unique within a document even when multiple blocks share the same
        # extracted name (e.g. several unnamed section blocks).  This is
        # deterministic (same offset ↔ same position in the same document) and
        # satisfies R2.7 (repeatable output for the same input).
        id_name = (
            f"{name}@{obj.start_offset}"
            if name != UNKNOWN
            else f"offset{obj.start_offset}"
        )

        # --- Object ID (R3.6 normalization applied inside make_object_id) ---
        object_id = make_object_id(
            tool_name=norm_tool,
            doc_version=norm_doc_ver,
            object_type=object_type,
            name=id_name,
        )

        # --- Page / section from OffsetMap ---
        page, section_title_raw = offset_map.locate(obj.start_offset)
        # textualize.OffsetMap.section_at returns UNKNOWN when no section found.
        section_title = section_title_raw if section_title_raw else UNKNOWN

        # --- Owning command name for option metadata ---
        owning_command_name: str | None = None
        if object_type == "option" and ro.belongs_to is not None:
            owning_command_name = command_start_to_name.get(ro.belongs_to)

        # --- Canonical text (R2.6) ---
        canonical = _make_canonical_text(
            object_type=object_type,
            name=name,
            block_text=block_text,
            section_title=section_title,
            summarize=summarize,
        )

        # --- Metadata (R3.1, R3.4) ---
        metadata = _fill_metadata(
            object_type=object_type,
            tool_name=norm_tool,
            tool_version=norm_version,
            doc_version=norm_doc_ver,
            name=name,
            section_title=section_title,
            belongs_to_command_name=owning_command_name,
        )

        # --- Evidence (R3.3, R3.4) ---
        evidence = _fill_evidence(
            source_file=source_file,
            doc_version=norm_doc_ver,
            page=page,
            section_title=section_title if section_title != UNKNOWN else "",
        )

        objects_out.append(
            ToolGuideObject(
                id=object_id,
                object_type=object_type,
                canonical_text=canonical,
                metadata=metadata,
                evidence=evidence,
            )
        )

    return objects_out
