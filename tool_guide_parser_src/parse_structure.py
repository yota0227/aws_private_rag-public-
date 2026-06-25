"""Pure structural parse pipeline: ``parse_structure`` (LLM-independent core).

design.md C2 describes the parser core as the composition of the deterministic
block scanner and the deterministic relation resolver:

    text --scan_blocks--> [ParsedObject]  (start/end offsets, object_type)
         --resolve_belongs_to--> [RelatedObject]  (+ belongs_to)

This module exposes that composition as a single pure function
:func:`parse_structure` so the **LLM-independent** determinism property
(Property 1) can be expressed against one entry point. It deliberately covers
*only* object boundaries / ``object_type`` / ``belongs_to`` — metadata,
``canonical_text`` (task 3.x) and any LLM assistance are out of scope and are
NOT touched here. design.md is explicit that determinism tests target this pure
``parse_structure``, not the LLM-assisted ``canonical_text``.

Purity / determinism (R2.2 / R2.7): both composed steps are pure (no external
state, no wall-clock, no randomness), so identical input always yields an
identical result — same object count, same ``[start, end)`` boundaries, same
``object_type`` sequence, same ``belongs_to`` sequence.

Flat-module convention (mirrors blockscan.py / relations.py): absolute import,
no package.

Requirements validated: 2.2, 2.7
"""

from blockscan import scan_blocks
from relations import RelatedObject, resolve_belongs_to


def parse_structure(text: str) -> list[RelatedObject]:
    """Run the pure structural parse: scan blocks, then resolve relations.

    Pure and deterministic. The returned list has exactly one
    :class:`~relations.RelatedObject` per detected block, start-sorted, each
    carrying its ``[start, end)`` bounds, ``object_type`` and ``belongs_to``
    (``None`` for non-options or orphan options). An empty / non-tiling input
    (empty string) yields an empty list.

    Args:
        text: The unified document text (from :mod:`textualize`).

    Returns:
        The structurally parsed objects with relations resolved.
    """
    return resolve_belongs_to(scan_blocks(text))
