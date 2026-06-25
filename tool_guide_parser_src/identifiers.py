"""Deterministic identifier helpers for Tool_Guide_Object records.

Implements the ``id`` generation rule
``toolguide#<tool>#<ver>#<type>#<name>`` and
``doc_id = sha1(normalize(tool_name) + normalize(doc_version) + normalize(filename))``.

R3.6 — identifier inputs (``tool_name``, ``doc_version``, ``filename``, and the
object ``name``) are normalized deterministically immediately before identifier
construction: case-folding (case unification) + trimming (leading/trailing
whitespace removal). As a result, re-ingesting the same logical document with
case/whitespace variants (e.g. ``VCS`` vs `` vcs ``) yields identical ``id``
and ``doc_id``. This reinforces Property 1 (parser determinism) and Property 6
(ingestion idempotence) across identifier-input variants.

Flat-module convention (mirrors rtl_parser_src): absolute import, no package.

Requirements validated: 3.6 (plus 3.5 id shape)
"""

import hashlib

from schema import is_allowed_object_type

# Prefix that namespaces Tool Guide object ids.
_ID_PREFIX = "toolguide"
_ID_SEP = "#"


def normalize_identifier(value: str) -> str:
    """Deterministically normalize an identifier-input value (R3.6).

    Normalization = trim leading/trailing whitespace, then case-fold. This is
    pure and deterministic: the same logical value with different case or
    surrounding whitespace maps to the same normalized form.

    Args:
        value: Raw identifier input (e.g. tool_name, doc_version, filename).

    Returns:
        The normalized string.

    Raises:
        TypeError: If ``value`` is not a string.
    """
    if not isinstance(value, str):
        raise TypeError(f"identifier input must be str, got {type(value).__name__}")
    return value.strip().casefold()


def make_object_id(
    tool_name: str,
    doc_version: str,
    object_type: str,
    name: str,
) -> str:
    """Build the deterministic object ``id``: ``toolguide#<tool>#<ver>#<type>#<name>``.

    Inputs ``tool_name``, ``doc_version``, and ``name`` are normalized
    (case-fold + trim) before assembly so case/whitespace variants of the same
    logical object yield the same id (R3.6). ``object_type`` must be in the
    closed allowed set (R3.2) and is used verbatim (it is already a controlled
    vocabulary value).

    Args:
        tool_name: Tool name (e.g. ``"VCS"``).
        doc_version: Document version string.
        object_type: One of the closed allowed object types.
        name: Object name (e.g. command/option name).

    Returns:
        The assembled id string.

    Raises:
        ValueError: If ``object_type`` is not in the allowed set.
    """
    if not is_allowed_object_type(object_type):
        raise ValueError(
            f"object_type {object_type!r} not in allowed set; cannot build id"
        )
    parts = (
        _ID_PREFIX,
        normalize_identifier(tool_name),
        normalize_identifier(doc_version),
        object_type,
        normalize_identifier(name),
    )
    return _ID_SEP.join(parts)


def make_doc_id(tool_name: str, doc_version: str, filename: str) -> str:
    """Build the deterministic ``doc_id`` for a source document (R3.6).

    ``doc_id = sha1(normalize(tool_name) + normalize(doc_version) +
    normalize(filename))`` where ``normalize`` is case-fold + trim. Re-ingesting
    the same logical document under case/whitespace variants produces the same
    ``doc_id``, enabling idempotent replacement (R1.6).

    Args:
        tool_name: Tool name from the upload key path.
        doc_version: Document version from the upload key path.
        filename: Source file name.

    Returns:
        The SHA-1 hex digest string.
    """
    payload = (
        normalize_identifier(tool_name)
        + normalize_identifier(doc_version)
        + normalize_identifier(filename)
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
