"""Tests for deterministic ``belongs_to`` relation resolution (task 2.3).

Covers the documented containment rule in :mod:`relations`:
  * an ``option`` inside a ``command``'s scope gets ``belongs_to`` = that
    command's ``start_offset`` (R2.3)
  * an orphan ``option`` (no preceding/containing command) stays independent
    with ``belongs_to = None`` and is NOT dropped (R2.4)
  * multiple options under one command all link to that command (R2.3)
  * options after a scope-breaking block (flow_step / section) become
    independent (R2.4)
  * ``example`` is scope-neutral (options after it still belong to the command)
  * determinism across repeated calls, and order-independence (R2.2 / R2.7)
  * no object is ever lost (count + identity preserved), input not mutated

These are example-based unit tests; the Hypothesis property test for relation
preservation (Property 5) arrives in task 2.6. Both feed the end-to-end parser.

Note on ``section`` blocks: :func:`~blockscan.scan_blocks` only emits a
``section`` as the residual *prefix* before the first header (mid-document prose
is absorbed into the preceding block). A mid-document ``section`` scope-breaker
is therefore exercised with a hand-constructed object list.
"""

from blockscan import ParsedObject, scan_blocks
from relations import RelatedObject, resolve_belongs_to


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _types(related):
    return [r.obj.object_type for r in related]


def _belongs(related):
    return [r.belongs_to for r in related]


def _command_start(related, index=0):
    """Return the start_offset of the ``index``-th command in ``related``."""
    commands = [r.obj.start_offset for r in related if r.obj.object_type == "command"]
    return commands[index]


# ---------------------------------------------------------------------------
# Option inside a command's scope -> belongs_to (R2.3)
# ---------------------------------------------------------------------------


def test_option_after_command_belongs_to_it():
    text = "Command: build\nOptions:\n-x flag\n"
    related = resolve_belongs_to(scan_blocks(text))
    assert _types(related) == ["command", "option", "option"]
    cmd_start = _command_start(related)
    # Both the "Options:" label block and the "-x" dash block belong to command.
    assert _belongs(related) == [None, cmd_start, cmd_start]


def test_multiple_options_under_one_command_all_link():
    text = (
        "Command: build\n"
        "Options:\n"
        "-a one\n"
        "--beta two\n"
        "-c three\n"
    )
    related = resolve_belongs_to(scan_blocks(text))
    cmd_start = _command_start(related)
    option_refs = [r.belongs_to for r in related if r.obj.object_type == "option"]
    assert option_refs == [cmd_start, cmd_start, cmd_start, cmd_start]
    assert all(ref == cmd_start for ref in option_refs)


def test_command_itself_never_has_belongs_to():
    text = "Command: build\nOptions:\n-x\n"
    related = resolve_belongs_to(scan_blocks(text))
    for r in related:
        if r.obj.object_type == "command":
            assert r.belongs_to is None


def test_options_link_to_their_own_command_not_an_earlier_one():
    text = (
        "Command: build\n"
        "-a for build\n"
        "Command: clean\n"
        "-b for clean\n"
    )
    related = resolve_belongs_to(scan_blocks(text))
    assert _types(related) == ["command", "option", "command", "option"]
    first_cmd = _command_start(related, 0)
    second_cmd = _command_start(related, 1)
    assert first_cmd != second_cmd
    assert _belongs(related) == [None, first_cmd, None, second_cmd]


# ---------------------------------------------------------------------------
# Orphan option -> independent, belongs_to=None, never dropped (R2.4)
# ---------------------------------------------------------------------------


def test_orphan_option_before_any_command_is_independent():
    text = "Options:\n-x orphaned\n"
    related = resolve_belongs_to(scan_blocks(text))
    assert _types(related) == ["option", "option"]
    assert _belongs(related) == [None, None]


def test_orphan_option_is_not_dropped():
    text = "Options:\n-x orphaned\n"
    objects = scan_blocks(text)
    related = resolve_belongs_to(objects)
    # Count preserved and the orphan option survives with belongs_to=None.
    assert len(related) == len(objects)
    assert any(
        r.obj.object_type == "option" and r.belongs_to is None for r in related
    )


def test_option_after_scope_breaking_section_is_independent():
    # scan_blocks only emits a ``section`` as the residual *prefix* before the
    # first header, so a mid-document section is constructed directly here to
    # exercise the section scope-breaker rule: an option after a section (with
    # no new command in between) is independent (R2.4).
    objects = [
        ParsedObject(0, 15, "command"),
        ParsedObject(15, 25, "option"),  # belongs to command @0
        ParsedObject(25, 40, "section"),  # scope-breaker
        ParsedObject(40, 50, "option"),  # orphaned now
    ]
    related = resolve_belongs_to(objects)
    assert _types(related) == ["command", "option", "section", "option"]
    assert _belongs(related) == [None, 0, None, None]


def test_option_after_flow_step_is_independent():
    text = (
        "Command: build\n"
        "-a belongs\n"
        "Flow: methodology\n"
        "-b orphaned now\n"
    )
    related = resolve_belongs_to(scan_blocks(text))
    assert _types(related) == ["command", "option", "flow_step", "option"]
    cmd_start = _command_start(related)
    assert _belongs(related) == [None, cmd_start, None, None]


# ---------------------------------------------------------------------------
# example is scope-neutral
# ---------------------------------------------------------------------------


def test_example_does_not_break_command_scope():
    # Command -> option -> example -> option : the trailing option still belongs
    # to the command because an example is scope-neutral.
    text = (
        "Command: build\n"
        "-a first\n"
        "Example:\n"
        "build -a\n"
        "-b still belongs\n"
    )
    related = resolve_belongs_to(scan_blocks(text))
    assert _types(related) == ["command", "option", "example", "option"]
    cmd_start = _command_start(related)
    assert _belongs(related) == [None, cmd_start, None, cmd_start]


# ---------------------------------------------------------------------------
# Determinism + order independence (R2.2 / R2.7)
# ---------------------------------------------------------------------------


def test_repeated_calls_are_identical():
    text = (
        "preamble\n"
        "Command: build\n"
        "Options:\n"
        "--jobs N\n"
        "Flow: next\n"
        "-orphan\n"
    )
    objects = scan_blocks(text)
    first = resolve_belongs_to(objects)
    second = resolve_belongs_to(objects)
    assert first == second
    assert _belongs(first) == _belongs(second)


def test_result_is_independent_of_input_order():
    text = "Command: build\nOptions:\n-x\nFlow: f\n-orphan\n"
    objects = scan_blocks(text)
    shuffled = list(reversed(objects))
    from_sorted = resolve_belongs_to(objects)
    from_shuffled = resolve_belongs_to(shuffled)
    # Defensive sort inside resolve_belongs_to makes the result order-independent.
    assert from_sorted == from_shuffled


# ---------------------------------------------------------------------------
# No object is ever lost; input not mutated
# ---------------------------------------------------------------------------


def test_count_and_identity_preserved_for_all_types():
    text = (
        "intro prose\n"
        "Command: build\n"
        "Options:\n"
        "-x\n"
        "Example:\n"
        "build -x\n"
        "Flow: deploy\n"
        "-orphan\n"
    )
    objects = scan_blocks(text)
    related = resolve_belongs_to(objects)
    # Exactly one RelatedObject per input object, same objects, same order.
    assert len(related) == len(objects)
    assert [r.obj for r in related] == sorted(objects, key=lambda o: o.start_offset)
    # Every option is preserved (none dropped).
    in_options = sum(1 for o in objects if o.object_type == "option")
    out_options = sum(1 for r in related if r.obj.object_type == "option")
    assert in_options == out_options


def test_input_list_not_mutated():
    text = "Command: build\nOptions:\n-x\n"
    objects = scan_blocks(text)
    snapshot = list(objects)
    resolve_belongs_to(objects)
    assert objects == snapshot  # same order, same elements, untouched


def test_empty_input_returns_empty_list():
    assert resolve_belongs_to([]) == []


def test_only_options_no_command_all_independent():
    objects = [
        ParsedObject(0, 5, "option"),
        ParsedObject(5, 10, "option"),
    ]
    related = resolve_belongs_to(objects)
    assert [r.belongs_to for r in related] == [None, None]
    assert all(isinstance(r, RelatedObject) for r in related)
