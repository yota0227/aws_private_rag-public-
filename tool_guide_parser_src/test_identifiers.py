"""Tests for deterministic id/doc_id helpers with input normalization (R3.6).

The core guarantee: case/whitespace variants of the same logical identifier
inputs produce identical ``id`` and ``doc_id``.
"""

import hashlib

import pytest

from identifiers import make_doc_id, make_object_id, normalize_identifier


# --- normalize_identifier ---------------------------------------------------


def test_normalize_trims_and_casefolds():
    assert normalize_identifier("  VCS  ") == "vcs"
    assert normalize_identifier("Vcs") == "vcs"
    assert normalize_identifier("vcs") == "vcs"


def test_normalize_is_idempotent():
    once = normalize_identifier("  Design_Compiler ")
    twice = normalize_identifier(once)
    assert once == twice == "design_compiler"


def test_normalize_rejects_non_str():
    with pytest.raises(TypeError):
        normalize_identifier(123)  # type: ignore[arg-type]


# --- make_object_id ---------------------------------------------------------


def test_object_id_shape():
    obj_id = make_object_id("VCS", "2023.12", "command", "elaborate")
    assert obj_id == "toolguide#vcs#2023.12#command#elaborate"


def test_object_id_invariant_to_case_and_whitespace():
    a = make_object_id("VCS", "2023.12", "command", "Elaborate")
    b = make_object_id("  vcs ", " 2023.12  ", "command", " elaborate ")
    assert a == b


def test_object_id_rejects_disallowed_type():
    with pytest.raises(ValueError):
        make_object_id("vcs", "2023.12", "widget", "elaborate")


# --- make_doc_id ------------------------------------------------------------


def test_doc_id_is_sha1_of_normalized_concat():
    expected = hashlib.sha1("vcs2023.12vcs_user_guide.pdf".encode("utf-8")).hexdigest()
    assert make_doc_id("VCS", "2023.12", "vcs_user_guide.pdf") == expected


def test_doc_id_invariant_to_case_and_whitespace():
    a = make_doc_id("VCS", "2023.12", "VCS_User_Guide.pdf")
    b = make_doc_id("  vcs", "2023.12 ", " vcs_user_guide.pdf ")
    assert a == b


def test_doc_id_distinguishes_different_documents():
    a = make_doc_id("vcs", "2023.12", "guide.pdf")
    b = make_doc_id("vcs", "2024.03", "guide.pdf")
    assert a != b
