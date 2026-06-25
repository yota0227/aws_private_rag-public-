"""Deterministic ``belongs_to`` relation resolution (pure core).

This module implements **step 3** ("관계 결정") of the parser pipeline described
in design.md C2: given the start-sorted, contiguously-tiling
:class:`~blockscan.ParsedObject` list produced by :func:`~blockscan.scan_blocks`,
it assigns a ``belongs_to`` reference to each ``option`` block that falls within
a ``command``'s scope, and preserves every other option as an INDEPENDENT object
with ``belongs_to = None`` (R2.3 / R2.4).

Pure and deterministic (R2.2 / R2.7): no external state, no wall-clock, no
randomness. Identical input always yields an identical result (same length, same
order, same ``belongs_to`` values). This is the relation half of Property 1 and
the whole of Property 5 (verified by task 2.6).

Containment rule (documented & deterministic)
----------------------------------------------
The :mod:`blockscan` boundary model makes every header begin a block that runs
until the *next* header. Consequently a ``command`` block and a following
``option`` block are **siblings by offset, not physically nested** — the option
never lies *inside* the command's ``[start, end)`` interval. We therefore define
containment by **scope** rather than by literal interval nesting:

    An ``option`` block belongs to the **most recent preceding ``command``**
    block, provided no *scope-breaking* block appears between that command and
    the option. A scope-breaking block ends the command's option list.

* A ``command`` block opens a new scope (and is the owner candidate for the
  options that follow it). Commands themselves never have a ``belongs_to``.
* ``flow_step`` and ``section`` blocks are **scope-breakers**: encountering one
  closes the current command's scope, so any option after it (with no new
  command in between) is an orphan / independent object (``belongs_to = None``).
* ``example`` blocks are **scope-neutral**: an example commonly appears inside a
  command's documentation (``Command:`` -> ``Options:`` -> ``Example:``), so it
  neither owns options nor closes the current command's scope. Options after an
  example still belong to the command that preceded the example.
* An ``option`` block consumes the current scope but does not change it (multiple
  options under one command all link to that command).

This rule is label/structure based only — no LLM, no heuristics, no
non-determinism — consistent with Property 1.

Command identity
----------------
``belongs_to`` references the owning command by a **stable structural identity**
available at this stage: the command block's ``start_offset`` (an ``int``).
Full canonical ids (:func:`~identifiers.make_object_id`) need metadata
(``tool_name`` / ``doc_version`` / object name) that only becomes available in
the object-building stage (task 3.x). Keeping the reference as the command's
``start_offset`` is deterministic, unique within a single parse (every block has
positive length, so starts are strictly increasing), and trivially mappable to
the real command id in 3.x: build ``{command.start_offset -> command.id}`` and
substitute. ``belongs_to = None`` always means "independent / orphan option".

Relation preservation
----------------------
The returned list has exactly one :class:`RelatedObject` per input
:class:`~blockscan.ParsedObject`, in the same start-sorted order. **No object is
ever dropped** — orphan options are preserved with ``belongs_to = None`` (R2.4).
The original frozen ``ParsedObject`` values are not mutated; each is wrapped in a
new ``RelatedObject`` record.

Flat-module convention (mirrors blockscan.py / schema.py): absolute import, no
package.

Requirements validated: 2.3, 2.4
"""

from dataclasses import dataclass

from blockscan import ParsedObject

# Block types that, when encountered, close the current command's option-list
# scope. An option appearing after one of these (with no intervening command)
# is an independent object. ``command`` opens a new scope and is handled
# explicitly; ``example`` is scope-neutral; ``option`` consumes but does not
# change the scope.
_SCOPE_BREAKERS: frozenset[str] = frozenset({"flow_step", "section"})


@dataclass(frozen=True)
class RelatedObject:
    """A :class:`~blockscan.ParsedObject` paired with its ``belongs_to`` ref.

    Attributes:
        obj: The wrapped parsed block (unmodified; the frozen original).
        belongs_to: Stable structural identity (``start_offset``) of the owning
            ``command`` block, or ``None`` when the object is independent. Only
            ``option`` blocks can carry a non-``None`` value; all other types are
            always ``None``. Task 3.x maps this ``start_offset`` reference to the
            owning command's canonical ``id``.

    Frozen (immutable + hashable) to keep the result deterministic and safe to
    use as a key in later pipeline stages.
    """

    obj: ParsedObject
    belongs_to: int | None = None


def resolve_belongs_to(objects: list[ParsedObject]) -> list[RelatedObject]:
    """Assign ``belongs_to`` per the documented containment rule (R2.3 / R2.4).

    Pure and deterministic. For each input block (processed in start-sorted
    order) the rule is:

    * ``command`` — opens / replaces the current scope; ``belongs_to = None``.
    * ``flow_step`` / ``section`` — closes the current scope; ``belongs_to =
      None``.
    * ``example`` — scope-neutral; ``belongs_to = None`` (current scope kept).
    * ``option`` — ``belongs_to`` = the current command's ``start_offset`` if a
      command scope is open, else ``None`` (orphan / independent, R2.4).

    The returned list has exactly one :class:`RelatedObject` per input object in
    the same order, so **no object is ever lost** and the count is preserved.
    The input is not mutated.

    Args:
        objects: Blocks from :func:`~blockscan.scan_blocks` (start-sorted,
            contiguously tiling). The function defensively re-sorts by
            ``start_offset`` (stable) so the result is order-independent of the
            caller and fully deterministic.

    Returns:
        One :class:`RelatedObject` per input block, start-sorted, with
        ``belongs_to`` assigned to options inside a command scope and ``None``
        for everything else.
    """
    # Defensive stable sort by start_offset: scan_blocks already guarantees this
    # ordering, but resolving by scope depends on order, so we make the contract
    # explicit and robust (and keep determinism regardless of caller order).
    ordered = sorted(objects, key=lambda o: o.start_offset)

    related: list[RelatedObject] = []
    current_command_start: int | None = None

    for obj in ordered:
        object_type = obj.object_type
        if object_type == "command":
            # A new command opens (replaces) the current option-list scope.
            current_command_start = obj.start_offset
            related.append(RelatedObject(obj, None))
        elif object_type in _SCOPE_BREAKERS:
            # flow_step / section end the command's option-list scope.
            current_command_start = None
            related.append(RelatedObject(obj, None))
        elif object_type == "option":
            # Belongs to the open command scope, or independent when none.
            related.append(RelatedObject(obj, current_command_start))
        else:
            # example: scope-neutral — keep current scope, no belongs_to.
            related.append(RelatedObject(obj, None))

    return related
