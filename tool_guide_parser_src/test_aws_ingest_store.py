"""Unit tests for aws_ingest_store.py -- AwsIngestStore concrete IngestStore.

All AWS / Qdrant I/O is mocked so no real services are needed.

Tests verify:
- Bedrock invoke_model called with correct model_id (amazon.titan-embed-text-v2:0)
- Qdrant upsert goes to collection ``tool-guide-knowledge-base`` (NOT rtl-knowledge-base)
- Qdrant upsert payload contains all 7 metadata fields + pipeline_id="tool-guide"
- DynamoDB put_item item includes pipeline_id="tool-guide"
- S3 put_object writes both .md and .metadata.json
- Token limit guard: text > 32 768 chars raises TokenLimitError (error:token_limit)
- Token limit warning: text >= 24 576 chars logs a warning (no exception)
- Transaction semantics: begin / commit / rollback ordering
- Rollback calls delete on Qdrant, DDB, and S3 (best-effort, swallows errors)

Requirements validated: 1.5, 3.5, 5.1 (+ R4.10)
"""

from __future__ import annotations

import io
import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from aws_ingest_store import (
    BEDROCK_EMBED_MODEL_ID,
    CLAIM_DB_TABLE,
    TOOL_GUIDE_COLLECTION,
    TOOL_GUIDE_PIPELINE_ID,
    AwsIngestStore,
    StoreWriteError,
    TokenLimitError,
    _TOKEN_LIMIT_CHAR_PROXY,
    _TOKEN_WARN_THRESHOLD,
)
from schema import Evidence, ToolGuideMetadata, ToolGuideObject


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_EMBEDDING = [0.1] * 1024  # 1024-dim fake vector


def _make_obj(
    obj_id: str = "toolguide#vcs#2023.12#command#elaborate",
    canonical_text: str = "Command 'elaborate': compiles and elaborates the design.",
) -> ToolGuideObject:
    """Return a minimal but fully-populated ToolGuideObject."""
    return ToolGuideObject(
        id=obj_id,
        object_type="command",
        canonical_text=canonical_text,
        metadata=ToolGuideMetadata(
            tool_name="VCS",
            tool_version="2023.12",
            command="elaborate",
            option="미확인",
            section="4.2",
            doc_version="2023.12-rev1",
            object_type="command",
        ),
        evidence=Evidence(
            source_file="vcs_user_guide.pdf",
            doc_version="2023.12-rev1",
            page=42,
            section="4.2",
        ),
    )


def _fake_bedrock_response(embedding: list = None) -> MagicMock:
    """Return a mock boto3 bedrock-runtime client whose invoke_model responds correctly."""
    if embedding is None:
        embedding = _FAKE_EMBEDDING
    body_bytes = json.dumps({"embedding": embedding}).encode("utf-8")
    mock_body = io.BytesIO(body_bytes)
    mock_response = {"body": mock_body}
    client = MagicMock()
    client.invoke_model.return_value = mock_response
    return client


def _fake_ddb_resource(table_mock: MagicMock = None) -> MagicMock:
    """Return a mock boto3 DynamoDB resource."""
    resource = MagicMock()
    if table_mock is None:
        table_mock = MagicMock()
    resource.Table.return_value = table_mock
    return resource


def _fake_s3_client() -> MagicMock:
    """Return a mock boto3 S3 client."""
    return MagicMock()


def _make_store(
    *,
    bedrock_client: MagicMock = None,
    ddb_resource: MagicMock = None,
    s3_client: MagicMock = None,
    ddb_table: MagicMock = None,
):
    """Create an AwsIngestStore with all AWS clients mocked.

    Returns (store, bedrock_mock, ddb_table_mock, s3_mock).
    """
    bc = bedrock_client or _fake_bedrock_response()
    ddb_tbl = ddb_table or MagicMock()
    ddb_res = ddb_resource or _fake_ddb_resource(ddb_tbl)
    s3 = s3_client or _fake_s3_client()
    store = AwsIngestStore(
        s3_bucket="bos-ai-toolguide-docs-seoul",
        qdrant_endpoint="http://qdrant.test:6333",
        qdrant_api_key="test-key",
        bedrock_client=bc,
        ddb_resource=ddb_res,
        s3_client=s3,
    )
    return store, bc, ddb_tbl, s3


# ---------------------------------------------------------------------------
# Bedrock embedding model verification
# ---------------------------------------------------------------------------


def test_bedrock_invoke_model_uses_correct_model_id():
    """Bedrock must be called with amazon.titan-embed-text-v2:0 (R1.5)."""
    store, bedrock, _, _ = _make_store()
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    bedrock.invoke_model.assert_called_once()
    call_kwargs = bedrock.invoke_model.call_args
    assert call_kwargs.kwargs.get("modelId") == BEDROCK_EMBED_MODEL_ID, (
        f"Expected modelId={BEDROCK_EMBED_MODEL_ID!r}, "
        f"got {call_kwargs.kwargs.get('modelId')!r}"
    )


def test_bedrock_constant_is_titan_embed_v2():
    """Constant sanity-check: the model ID must not silently change."""
    assert BEDROCK_EMBED_MODEL_ID == "amazon.titan-embed-text-v2:0"


# ---------------------------------------------------------------------------
# Qdrant collection name verification (must NOT use rtl-knowledge-base)
# ---------------------------------------------------------------------------


def test_qdrant_upsert_targets_tool_guide_collection():
    """Qdrant PUT must go to tool-guide-knowledge-base, not rtl-knowledge-base."""
    store, _, _, _ = _make_store()
    obj = _make_obj()
    captured_urls = []

    def capture_request(url, body, method):
        captured_urls.append(url)

    with patch.object(store, "_qdrant_request", side_effect=capture_request):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    assert len(captured_urls) >= 1, "Expected at least one Qdrant request"
    upsert_url = captured_urls[0]
    assert TOOL_GUIDE_COLLECTION in upsert_url, (
        f"Expected URL to contain {TOOL_GUIDE_COLLECTION!r}, got {upsert_url!r}"
    )
    assert "rtl-knowledge-base" not in upsert_url, (
        "Qdrant URL must NOT target rtl-knowledge-base"
    )


def test_qdrant_collection_constant_value():
    """Constant sanity-check."""
    assert TOOL_GUIDE_COLLECTION == "tool-guide-knowledge-base"


# ---------------------------------------------------------------------------
# Qdrant payload verification (7 metadata fields + pipeline_id)
# ---------------------------------------------------------------------------


def test_qdrant_payload_contains_all_7_metadata_fields():
    """Qdrant payload must include all 7 required metadata fields (R3.1)."""
    store, _, _, _ = _make_store()
    obj = _make_obj()
    captured_bodies = []

    def capture_request(url, body, method):
        if method == "PUT":
            captured_bodies.append(json.loads(body.decode("utf-8")))

    with patch.object(store, "_qdrant_request", side_effect=capture_request):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    assert captured_bodies, "No Qdrant PUT request captured"
    payload = captured_bodies[0]["points"][0]["payload"]
    required_fields = [
        "tool_name", "tool_version", "command", "option",
        "section", "doc_version", "object_type",
    ]
    for field in required_fields:
        assert field in payload, f"Missing metadata field {field!r} in Qdrant payload"


def test_qdrant_payload_contains_pipeline_id_tool_guide():
    """Qdrant payload must contain pipeline_id='tool-guide' (R5.1, Design C3)."""
    store, _, _, _ = _make_store()
    obj = _make_obj()
    captured_bodies = []

    def capture_request(url, body, method):
        if method == "PUT":
            captured_bodies.append(json.loads(body.decode("utf-8")))

    with patch.object(store, "_qdrant_request", side_effect=capture_request):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    payload = captured_bodies[0]["points"][0]["payload"]
    assert payload.get("pipeline_id") == TOOL_GUIDE_PIPELINE_ID, (
        f"Expected pipeline_id={TOOL_GUIDE_PIPELINE_ID!r}, got {payload.get('pipeline_id')!r}"
    )


def test_qdrant_payload_metadata_values_match_object():
    """Qdrant payload metadata values must match the ToolGuideObject metadata."""
    store, _, _, _ = _make_store()
    obj = _make_obj()
    captured_bodies = []

    def capture_request(url, body, method):
        if method == "PUT":
            captured_bodies.append(json.loads(body.decode("utf-8")))

    with patch.object(store, "_qdrant_request", side_effect=capture_request):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    payload = captured_bodies[0]["points"][0]["payload"]
    meta = obj.metadata.to_dict()
    for field, expected in meta.items():
        assert payload[field] == expected, (
            f"Payload field {field!r}: expected {expected!r}, got {payload[field]!r}"
        )


def test_qdrant_payload_contains_evidence_source_file_and_page():
    """Payload must carry evidence source_file + page so search() can render a
    real citation instead of falling back source_file -> doc_version (R3.3)."""
    store, _, _, _ = _make_store()
    obj = _make_obj()  # evidence: source_file="vcs_user_guide.pdf", page=42
    captured_bodies = []

    def capture_request(url, body, method):
        if method == "PUT":
            captured_bodies.append(json.loads(body.decode("utf-8")))

    with patch.object(store, "_qdrant_request", side_effect=capture_request):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    payload = captured_bodies[0]["points"][0]["payload"]
    assert payload.get("source_file") == obj.evidence.source_file
    assert payload.get("page") == obj.evidence.page


# ---------------------------------------------------------------------------
# DynamoDB verification
# ---------------------------------------------------------------------------


def test_ddb_put_item_called():
    """DynamoDB put_item must be invoked for each upserted object."""
    store, _, ddb_table, _ = _make_store()
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    ddb_table.put_item.assert_called_once()


def test_ddb_put_item_includes_pipeline_id_tool_guide():
    """DynamoDB item must include pipeline_id='tool-guide' (R5.1)."""
    store, _, ddb_table, _ = _make_store()
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    item = ddb_table.put_item.call_args.kwargs["Item"]
    assert item.get("pipeline_id") == TOOL_GUIDE_PIPELINE_ID, (
        f"Expected pipeline_id={TOOL_GUIDE_PIPELINE_ID!r} in DDB item, "
        f"got {item.get('pipeline_id')!r}"
    )


def test_ddb_put_item_includes_doc_id():
    """DynamoDB item must include doc_id."""
    store, _, ddb_table, _ = _make_store()
    obj = _make_obj()
    doc_id = "deadbeef01"

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object(doc_id, obj)
        store.commit()

    item = ddb_table.put_item.call_args.kwargs["Item"]
    assert item.get("doc_id") == doc_id


def test_ddb_put_item_uses_existing_table_not_new():
    """Store must use the existing CLAIM_DB_TABLE, not create a new one (R1.5)."""
    ddb_table = MagicMock()
    ddb_resource = _fake_ddb_resource(ddb_table)
    store = AwsIngestStore(
        s3_bucket="bucket",
        qdrant_endpoint="http://qdrant.test:6333",
        bedrock_client=_fake_bedrock_response(),
        ddb_resource=ddb_resource,
        s3_client=MagicMock(),
    )
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    ddb_resource.Table.assert_called_with(CLAIM_DB_TABLE)


# ---------------------------------------------------------------------------
# S3 artifact verification
# ---------------------------------------------------------------------------


def test_s3_put_object_called_twice_per_upsert():
    """S3 put_object must be called twice: once for .md and once for .metadata.json."""
    store, _, _, s3 = _make_store()
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    assert s3.put_object.call_count == 2, (
        f"Expected 2 S3 put_object calls, got {s3.put_object.call_count}"
    )


def test_s3_puts_md_artifact():
    """One of the S3 put_object calls must write a .md file."""
    store, _, _, s3 = _make_store()
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    keys_written = [c.kwargs["Key"] for c in s3.put_object.call_args_list]
    md_keys = [k for k in keys_written if k.endswith(".md")]
    assert md_keys, f"No .md key found in S3 calls: {keys_written}"


def test_s3_puts_metadata_json_artifact():
    """One of the S3 put_object calls must write a .metadata.json file."""
    store, _, _, s3 = _make_store()
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    keys_written = [c.kwargs["Key"] for c in s3.put_object.call_args_list]
    json_keys = [k for k in keys_written if k.endswith(".metadata.json")]
    assert json_keys, f"No .metadata.json key found in S3 calls: {keys_written}"


def test_s3_artifact_keys_under_published_prefix():
    """Both S3 artifacts must be written under published/<doc_id>/."""
    store, _, _, s3 = _make_store()
    obj = _make_obj()
    doc_id = "deadbeef01"

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object(doc_id, obj)
        store.commit()

    for c in s3.put_object.call_args_list:
        key = c.kwargs["Key"]
        assert key.startswith(f"published/{doc_id}/"), (
            f"S3 key {key!r} must be under published/{doc_id}/"
        )


def test_s3_md_body_is_canonical_text():
    """The .md file body must equal canonical_text encoded as UTF-8."""
    store, _, _, s3 = _make_store()
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    md_call = next(
        c for c in s3.put_object.call_args_list if c.kwargs["Key"].endswith(".md")
    )
    assert md_call.kwargs["Body"] == obj.canonical_text.encode("utf-8")


def test_s3_metadata_json_body_contains_pipeline_id():
    """The .metadata.json body must contain pipeline_id='tool-guide'."""
    store, _, _, s3 = _make_store()
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object("deadbeef01", obj)
        store.commit()

    json_call = next(
        c for c in s3.put_object.call_args_list
        if c.kwargs["Key"].endswith(".metadata.json")
    )
    payload = json.loads(json_call.kwargs["Body"].decode("utf-8"))
    assert payload.get("pipeline_id") == TOOL_GUIDE_PIPELINE_ID


# ---------------------------------------------------------------------------
# Token limit guard (R4.10)
# ---------------------------------------------------------------------------


def test_token_limit_raises_for_text_exceeding_proxy():
    """Text longer than 32 768 chars must raise TokenLimitError before Bedrock."""
    store, bedrock, _, _ = _make_store()
    long_text = "a" * (_TOKEN_LIMIT_CHAR_PROXY + 1)
    obj = _make_obj(canonical_text=long_text)

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        with pytest.raises(TokenLimitError):
            store.upsert_object("deadbeef01", obj)
        store.rollback()

    # Bedrock must NOT have been called
    bedrock.invoke_model.assert_not_called()


def test_token_limit_does_not_raise_at_exactly_proxy():
    """Text of exactly _TOKEN_LIMIT_CHAR_PROXY chars must NOT raise TokenLimitError."""
    store, _, _, _ = _make_store()
    exact_text = "a" * _TOKEN_LIMIT_CHAR_PROXY
    obj = _make_obj(canonical_text=exact_text)

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        # Should not raise; may log a warning but must succeed.
        store.upsert_object("deadbeef01", obj)
        store.commit()


def test_token_warning_logged_for_text_near_limit(caplog):
    """Text >= 24 576 chars must trigger a warning log (no exception)."""
    store, _, _, _ = _make_store()
    near_limit_text = "a" * _TOKEN_WARN_THRESHOLD
    obj = _make_obj(canonical_text=near_limit_text)

    with patch.object(store, "_qdrant_request"):
        with caplog.at_level(logging.WARNING):
            store.begin_transaction()
            store.upsert_object("deadbeef01", obj)
            store.commit()

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("token_limit_approaching" in m for m in warning_messages), (
        "Expected 'token_limit_approaching' warning for text near the limit"
    )


# ---------------------------------------------------------------------------
# Transaction semantics
# ---------------------------------------------------------------------------


def test_begin_commit_cycle_succeeds():
    """begin_transaction + upsert + commit must not raise."""
    store, _, _, _ = _make_store()
    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.upsert_object("doc1", _make_obj())
        store.commit()


def test_double_begin_raises():
    """Calling begin_transaction twice without commit/rollback must raise."""
    store, _, _, _ = _make_store()
    store.begin_transaction()
    with pytest.raises(RuntimeError):
        store.begin_transaction()
    store.rollback()


def test_commit_outside_transaction_raises():
    """commit() without begin_transaction must raise."""
    store, _, _, _ = _make_store()
    with pytest.raises(RuntimeError):
        store.commit()


def test_upsert_outside_transaction_raises():
    """upsert_object() without begin_transaction must raise."""
    store, _, _, _ = _make_store()
    with pytest.raises(RuntimeError):
        store.upsert_object("doc1", _make_obj())


def test_rollback_outside_transaction_is_noop():
    """rollback() outside a transaction must not raise (R2.8 safeguard)."""
    store, _, _, _ = _make_store()
    store.rollback()  # Must not raise


# ---------------------------------------------------------------------------
# Rollback behavior
# ---------------------------------------------------------------------------


def test_rollback_calls_qdrant_delete():
    """Rollback must attempt to delete the Qdrant point."""
    store, _, _, _ = _make_store()
    obj = _make_obj()
    delete_urls = []

    def capture_request(url, body, method):
        if method == "POST" and "delete" in url:
            delete_urls.append(url)

    with patch.object(store, "_qdrant_request", side_effect=capture_request):
        store.begin_transaction()
        # Add to journal directly to isolate rollback from upsert
        store._written_this_tx.append(("doc1", obj.id))
        store.rollback()

    assert any(TOOL_GUIDE_COLLECTION in u for u in delete_urls), (
        f"Expected Qdrant delete URL with {TOOL_GUIDE_COLLECTION!r}, got: {delete_urls}"
    )


def test_rollback_calls_ddb_delete_item():
    """Rollback must attempt to delete the DynamoDB record."""
    store, _, ddb_table, _ = _make_store()
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store._written_this_tx.append(("doc1", obj.id))
        store.rollback()

    ddb_table.delete_item.assert_called_once()


def test_rollback_calls_s3_delete_object():
    """Rollback must attempt to delete both S3 artifacts."""
    store, _, _, s3 = _make_store()
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store._written_this_tx.append(("doc1", obj.id))
        store.rollback()

    assert s3.delete_object.call_count == 2, (
        f"Expected 2 S3 delete_object calls during rollback, "
        f"got {s3.delete_object.call_count}"
    )


def test_rollback_does_not_raise_when_deletes_fail():
    """Rollback must swallow delete errors (best-effort)."""
    ddb_table = MagicMock()
    ddb_table.delete_item.side_effect = RuntimeError("DDB is down")
    store, _, _, s3 = _make_store(ddb_table=ddb_table)
    s3.delete_object.side_effect = RuntimeError("S3 is down")
    obj = _make_obj()

    with patch.object(store, "_qdrant_request", side_effect=StoreWriteError("Qdrant down")):
        store.begin_transaction()
        store._written_this_tx.append(("doc1", obj.id))
        # Must not raise despite all deletes failing
        store.rollback()


# ---------------------------------------------------------------------------
# Bedrock failure propagation
# ---------------------------------------------------------------------------


def test_bedrock_failure_raises_store_write_error():
    """A Bedrock exception must be converted to StoreWriteError."""
    bedrock = MagicMock()
    bedrock.invoke_model.side_effect = RuntimeError("Bedrock unavailable")
    store = AwsIngestStore(
        s3_bucket="bucket",
        qdrant_endpoint="http://qdrant.test:6333",
        bedrock_client=bedrock,
        ddb_resource=_fake_ddb_resource(),
        s3_client=MagicMock(),
    )
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        with pytest.raises(StoreWriteError):
            store.upsert_object("doc1", obj)
        store.rollback()


# ---------------------------------------------------------------------------
# Missing configuration safety
# ---------------------------------------------------------------------------


def test_missing_qdrant_endpoint_raises_store_write_error():
    """Missing QDRANT_ENDPOINT must raise StoreWriteError."""
    store = AwsIngestStore(
        s3_bucket="bucket",
        qdrant_endpoint="",  # explicitly empty
        bedrock_client=_fake_bedrock_response(),
        ddb_resource=_fake_ddb_resource(),
        s3_client=MagicMock(),
    )
    obj = _make_obj()
    store.begin_transaction()
    with pytest.raises(StoreWriteError, match="QDRANT_ENDPOINT"):
        store.upsert_object("doc1", obj)
    store.rollback()


def test_missing_s3_bucket_raises_store_write_error():
    """Missing S3 bucket must raise StoreWriteError when writing artifacts."""
    ddb_table = MagicMock()
    store = AwsIngestStore(
        s3_bucket="",  # explicitly empty
        qdrant_endpoint="http://qdrant.test:6333",
        bedrock_client=_fake_bedrock_response(),
        ddb_resource=_fake_ddb_resource(ddb_table),
        s3_client=MagicMock(),
    )
    obj = _make_obj()

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        with pytest.raises(StoreWriteError, match="S3_BUCKET"):
            store.upsert_object("doc1", obj)
        store.rollback()


# ---------------------------------------------------------------------------
# bulk_upsert: parallel embed + batched Qdrant, skips DDB + S3
# ---------------------------------------------------------------------------


def _fresh_bedrock():
    """Bedrock mock returning a FRESH response body per call (parallel-safe)."""
    client = MagicMock()
    client.invoke_model.side_effect = lambda **kw: {
        "body": io.BytesIO(json.dumps({"embedding": _FAKE_EMBEDDING}).encode("utf-8"))
    }
    return client


def _bulk_objs(n):
    return [
        _make_obj(
            obj_id=f"toolguide#atlas#ver.1#section#offset{i}",
            canonical_text=f"register field chunk number {i}",
        )
        for i in range(n)
    ]


def test_bulk_upsert_embeds_all_and_batches_qdrant():
    store, _, _, _ = _make_store(bedrock_client=_fresh_bedrock())
    objs = _bulk_objs(5)
    captured = []

    def cap(url, body, method):
        if method == "PUT":
            captured.append(json.loads(body.decode("utf-8")))

    with patch.object(store, "_qdrant_request", side_effect=cap):
        store.begin_transaction()
        store.bulk_upsert("docid", objs, qdrant_batch=2)
        store.commit()

    # 5 objects / batch 2 => 3 PUTs covering all 5 points.
    assert len(captured) == 3
    assert sum(len(b["points"]) for b in captured) == 5
    # Payload carries evidence provenance.
    p0 = captured[0]["points"][0]["payload"]
    assert p0["source_file"] == "vcs_user_guide.pdf"
    assert p0["page"] == 42
    assert p0["pipeline_id"] == TOOL_GUIDE_PIPELINE_ID


def test_bulk_upsert_skips_ddb_and_s3():
    store, _, ddb_tbl, s3 = _make_store(bedrock_client=_fresh_bedrock())
    objs = _bulk_objs(3)

    with patch.object(store, "_qdrant_request"):
        store.begin_transaction()
        store.bulk_upsert("docid", objs)
        store.commit()

    # Bulk path is Qdrant-only: no claim-db rows, no S3 sidecars.
    ddb_tbl.put_item.assert_not_called()
    ddb_tbl.update_item.assert_not_called()
    s3.put_object.assert_not_called()


def test_bulk_upsert_empty_is_noop():
    store, _, _, _ = _make_store(bedrock_client=_fresh_bedrock())
    with patch.object(store, "_qdrant_request") as q:
        store.begin_transaction()
        store.bulk_upsert("docid", [])
        store.commit()
    q.assert_not_called()


def test_bulk_upsert_outside_transaction_raises():
    store, _, _, _ = _make_store(bedrock_client=_fresh_bedrock())
    with pytest.raises(RuntimeError):
        store.bulk_upsert("docid", _bulk_objs(1))


# ---------------------------------------------------------------------------
# delete_doc_points + doc_id payload (idempotent re-ingestion, R1.6)
# ---------------------------------------------------------------------------


def test_bulk_upsert_payload_includes_doc_id():
    store, _, _, _ = _make_store(bedrock_client=_fresh_bedrock())
    objs = _bulk_objs(2)
    captured = []

    def cap(url, body, method):
        if method == "PUT":
            captured.append(json.loads(body.decode("utf-8")))

    with patch.object(store, "_qdrant_request", side_effect=cap):
        store.begin_transaction()
        store.bulk_upsert("docid-xyz", objs)
        store.commit()

    payload = captured[0]["points"][0]["payload"]
    assert payload["doc_id"] == "docid-xyz"


def test_delete_doc_points_posts_filter_by_doc_id():
    store, _, _, _ = _make_store()
    captured = {}

    def cap(url, body, method):
        captured["url"] = url
        captured["method"] = method
        captured["body"] = json.loads(body.decode("utf-8"))

    with patch.object(store, "_qdrant_request", side_effect=cap):
        store.delete_doc_points("docid-xyz")

    assert captured["method"] == "POST"
    assert "/points/delete" in captured["url"]
    must = captured["body"]["filter"]["must"]
    assert {"key": "doc_id", "match": {"value": "docid-xyz"}} in must
    assert {"key": "pipeline_id", "match": {"value": TOOL_GUIDE_PIPELINE_ID}} in must
