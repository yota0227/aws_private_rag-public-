"""Unit tests for handler.py — ingestion handler, IngestStore, transaction logic.

Tests cover:
- handler() normal success path
- Idempotence: same event ingested twice → same doc_id, same object set, no duplicates
- Empty document → error:empty_document, no writes
- Unsupported format → error:unsupported_format, no writes
- Missing content argument → error:missing_content, no writes
- Partial write failure → rollback → no partial results persisted
- doc_id determinism with case/whitespace variants (R3.6)
- InMemoryIngestStore transaction semantics (begin/commit/rollback)
- _FailAfterNStore rollback verification

Requirements validated: 1.4, 1.6, 2.8
"""

import pytest

from handler import (
    InMemoryIngestStore,
    _FailAfterNStore,
    handler,
)
from identifiers import make_doc_id
from schema import Evidence, ToolGuideMetadata, ToolGuideObject


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_MD = """\
# VCS User Guide

Command: elaborate
  Elaborates the design hierarchy.

Options:
  -f <file>   Specify the file list.
"""

SAMPLE_EVENT = {
    "bucket": "bos-ai-toolguide-docs-seoul",
    "key": "VCS/2023.12/vcs_user_guide.md",
    "tool_name": "VCS",
    "doc_version": "2023.12",
    "filename": "vcs_user_guide.md",
}


def _make_store() -> InMemoryIngestStore:
    return InMemoryIngestStore()


def _run(event: dict, text: str, store: InMemoryIngestStore | None = None):
    """Convenience: call handler with pre-loaded Markdown text.

    Returns ``(result_dict, store)`` so callers can inspect store state.
    """
    s = store or _make_store()
    result = handler(event, store=s, markdown_text=text)
    return result, s


def _make_dummy_object(obj_id: str = "toolguide#vcs#1.0#command#test") -> ToolGuideObject:
    """Return a minimal valid ToolGuideObject for IngestStore unit tests."""
    return ToolGuideObject(
        id=obj_id,
        object_type="command",
        canonical_text="Command 'test': test command.",
        metadata=ToolGuideMetadata(tool_name="vcs", object_type="command"),
        evidence=Evidence(source_file="f.md", doc_version="1.0", section="S1"),
    )


# ---------------------------------------------------------------------------
# Normal success path
# ---------------------------------------------------------------------------


def test_handler_success_returns_ok_status():
    result, _ = _run(SAMPLE_EVENT, SAMPLE_MD)
    assert result["status"] == "ok"


def test_handler_success_returns_nonzero_object_count():
    result, _ = _run(SAMPLE_EVENT, SAMPLE_MD)
    assert result["object_count"] > 0


def test_handler_success_returns_correct_doc_id():
    result, _ = _run(SAMPLE_EVENT, SAMPLE_MD)
    expected = make_doc_id(
        SAMPLE_EVENT["tool_name"],
        SAMPLE_EVENT["doc_version"],
        SAMPLE_EVENT["filename"],
    )
    assert result["doc_id"] == expected


def test_handler_success_persists_objects_in_store():
    result, store = _run(SAMPLE_EVENT, SAMPLE_MD)
    doc_id = result["doc_id"]
    ids = store.list_ids_for_doc(doc_id)
    assert len(ids) == result["object_count"]
    assert len(ids) > 0


# ---------------------------------------------------------------------------
# Idempotence (R1.6)
# ---------------------------------------------------------------------------


def test_handler_idempotent_same_doc_id():
    """Two runs of the same event yield the same doc_id."""
    result1, store = _run(SAMPLE_EVENT, SAMPLE_MD)
    result2 = handler(SAMPLE_EVENT, store=store, markdown_text=SAMPLE_MD)
    assert result1["doc_id"] == result2["doc_id"]


def test_handler_idempotent_no_duplicate_objects():
    """Two ingestions of the same document must not create duplicate objects."""
    result1, store = _run(SAMPLE_EVENT, SAMPLE_MD)
    handler(SAMPLE_EVENT, store=store, markdown_text=SAMPLE_MD)
    ids_after_two = store.list_ids_for_doc(result1["doc_id"])
    # Object count must be the same as after the first ingestion (upsert, not insert).
    assert len(ids_after_two) == result1["object_count"]


def test_handler_idempotent_same_object_id_set():
    """Object id sets are identical across two ingestions."""
    result1, store = _run(SAMPLE_EVENT, SAMPLE_MD)
    ids_first = set(store.list_ids_for_doc(result1["doc_id"]))
    handler(SAMPLE_EVENT, store=store, markdown_text=SAMPLE_MD)
    ids_second = set(store.list_ids_for_doc(result1["doc_id"]))
    assert ids_first == ids_second


# ---------------------------------------------------------------------------
# doc_id determinism with case/whitespace normalization (R3.6)
# ---------------------------------------------------------------------------


def test_doc_id_case_insensitive():
    """Tool_name/doc_version/filename differing only in case produce the same doc_id."""
    id_upper = make_doc_id("VCS", "2023.12", "VCS_USER_GUIDE.MD")
    id_lower = make_doc_id("vcs", "2023.12", "vcs_user_guide.md")
    assert id_upper == id_lower


def test_doc_id_whitespace_trimmed():
    """Surrounding whitespace in key fields does not change doc_id."""
    id_plain = make_doc_id("VCS", "2023.12", "guide.md")
    id_padded = make_doc_id("  VCS  ", "  2023.12  ", "  guide.md  ")
    assert id_plain == id_padded


def test_handler_case_variant_replaces_not_duplicates():
    """Ingesting the same document with different case produces same doc_id (upsert)."""
    store = _make_store()
    event_a = {**SAMPLE_EVENT, "tool_name": "VCS"}
    event_b = {**SAMPLE_EVENT, "tool_name": "vcs"}
    r1 = handler(event_a, store=store, markdown_text=SAMPLE_MD)
    r2 = handler(event_b, store=store, markdown_text=SAMPLE_MD)
    # Same doc_id → upsert, not duplicate insert.
    assert r1["doc_id"] == r2["doc_id"]
    ids = store.list_ids_for_doc(r1["doc_id"])
    # Count unchanged after second run (idempotent).
    assert len(ids) == r1["object_count"]


# ---------------------------------------------------------------------------
# Empty document → error, no writes (R2.8, R1.4)
# ---------------------------------------------------------------------------


def test_handler_empty_document_returns_error_status():
    result, _ = _run(SAMPLE_EVENT, "")
    assert result["status"] == "error:empty_document"


def test_handler_whitespace_only_returns_error_status():
    result, _ = _run(SAMPLE_EVENT, "   \n\t  ")
    assert result["status"] == "error:empty_document"


def test_handler_empty_document_zero_object_count():
    result, _ = _run(SAMPLE_EVENT, "")
    assert result["object_count"] == 0


def test_handler_empty_document_no_writes():
    result, store = _run(SAMPLE_EVENT, "")
    assert store.total_object_count() == 0


def test_handler_empty_document_preserves_existing_data():
    """Empty-document error must not corrupt previously stored objects."""
    store = _make_store()
    # First: a valid ingestion.
    r1 = handler(SAMPLE_EVENT, store=store, markdown_text=SAMPLE_MD)
    count_before = store.total_object_count()
    # Second: an empty document for the same event → should fail and preserve.
    handler(SAMPLE_EVENT, store=store, markdown_text="")
    assert store.total_object_count() == count_before


# ---------------------------------------------------------------------------
# Unsupported format → error, no writes (R1.4)
# ---------------------------------------------------------------------------


def test_handler_unsupported_format_returns_error_status():
    event_bad = {**SAMPLE_EVENT, "filename": "guide.docx"}
    result, _ = _run(event_bad, SAMPLE_MD)
    assert result["status"] == "error:unsupported_format"


def test_handler_unsupported_format_zero_object_count():
    event_bad = {**SAMPLE_EVENT, "filename": "guide.docx"}
    result, _ = _run(event_bad, SAMPLE_MD)
    assert result["object_count"] == 0


def test_handler_unsupported_format_no_writes():
    event_bad = {**SAMPLE_EVENT, "filename": "guide.docx"}
    _, store = _run(event_bad, SAMPLE_MD)
    assert store.total_object_count() == 0


# ---------------------------------------------------------------------------
# Missing content argument → error, no writes
# ---------------------------------------------------------------------------


def test_handler_missing_markdown_text_returns_error():
    """Passing a .md filename but no markdown_text (None) should return an error."""
    store = _make_store()
    # Do NOT pass markdown_text — default is None, which textualize_document
    # will reject with a ValueError.
    result = handler(SAMPLE_EVENT, store=store)
    assert result["status"].startswith("error:")


def test_handler_missing_markdown_text_no_writes():
    store = _make_store()
    handler(SAMPLE_EVENT, store=store)
    assert store.total_object_count() == 0


# ---------------------------------------------------------------------------
# Transactional rollback on store failure (R2.8)
# ---------------------------------------------------------------------------


def test_handler_rollback_on_first_write_failure():
    """If the very first upsert fails, no objects must be stored."""
    store = _FailAfterNStore(fail_after=0)
    result = handler(SAMPLE_EVENT, store=store, markdown_text=SAMPLE_MD)
    assert result["status"] == "error:store_failure"
    assert result["object_count"] == 0
    assert store.total_object_count() == 0


def test_handler_rollback_on_mid_failure():
    """If a mid-way upsert fails, ALL previously written objects are rolled back."""
    store = _FailAfterNStore(fail_after=1)
    result = handler(SAMPLE_EVENT, store=store, markdown_text=SAMPLE_MD)
    assert result["status"] == "error:store_failure"
    # No partial results should survive.
    assert store.total_object_count() == 0


def test_handler_rollback_returns_zero_object_count():
    """Rollback path must report object_count=0."""
    store = _FailAfterNStore(fail_after=0)
    result = handler(SAMPLE_EVENT, store=store, markdown_text=SAMPLE_MD)
    assert result["object_count"] == 0


# ---------------------------------------------------------------------------
# InMemoryIngestStore transaction semantics
# ---------------------------------------------------------------------------


class TestInMemoryIngestStore:
    def test_commit_makes_writes_visible(self):
        store = _make_store()
        obj = _make_dummy_object()
        store.begin_transaction()
        store.upsert_object("doc1", obj)
        store.commit()
        assert obj.id in store.list_ids_for_doc("doc1")

    def test_rollback_undoes_writes(self):
        store = _make_store()
        obj = _make_dummy_object()
        store.begin_transaction()
        store.upsert_object("doc1", obj)
        store.rollback()
        assert store.list_ids_for_doc("doc1") == []

    def test_rollback_outside_transaction_is_noop(self):
        """rollback() outside a transaction must not raise and must be a no-op."""
        store = _make_store()
        store.rollback()  # must not raise
        assert store.total_object_count() == 0

    def test_upsert_outside_transaction_raises(self):
        store = _make_store()
        obj = _make_dummy_object()
        with pytest.raises(RuntimeError):
            store.upsert_object("doc", obj)

    def test_double_begin_raises(self):
        store = _make_store()
        store.begin_transaction()
        with pytest.raises(RuntimeError):
            store.begin_transaction()
        store.rollback()  # cleanup

    def test_commit_outside_transaction_raises(self):
        store = _make_store()
        with pytest.raises(RuntimeError):
            store.commit()

    def test_upsert_replaces_existing_on_same_id(self):
        """Upserting the same obj.id twice overwrites, not appends."""
        store = _make_store()
        obj_v1 = _make_dummy_object("toolguide#vcs#1.0#command#test")
        obj_v2 = ToolGuideObject(
            id="toolguide#vcs#1.0#command#test",  # same id
            object_type="command",
            canonical_text="Updated canonical text.",
            metadata=ToolGuideMetadata(tool_name="vcs", object_type="command"),
            evidence=Evidence(source_file="f.md", doc_version="1.0", section="S2"),
        )
        store.begin_transaction()
        store.upsert_object("doc1", obj_v1)
        store.upsert_object("doc1", obj_v2)
        store.commit()
        # Should still be just one record.
        ids = store.list_ids_for_doc("doc1")
        assert ids == ["toolguide#vcs#1.0#command#test"]
        # The stored object should be the second version.
        stored = store.get_objects_for_doc("doc1")[0]
        assert stored.canonical_text == "Updated canonical text."

    def test_rollback_preserves_pre_existing_data(self):
        """A failed transaction must not wipe out data committed in a prior run."""
        store = _make_store()
        # Commit a first object.
        obj_prior = _make_dummy_object("toolguide#vcs#1.0#command#prior")
        store.begin_transaction()
        store.upsert_object("doc1", obj_prior)
        store.commit()
        ids_before = store.list_ids_for_doc("doc1")

        # Begin a second transaction, write something, then rollback.
        obj_new = _make_dummy_object("toolguide#vcs#1.0#command#new")
        store.begin_transaction()
        store.upsert_object("doc1", obj_new)
        store.rollback()

        # Prior data must be intact.
        assert store.list_ids_for_doc("doc1") == ids_before
