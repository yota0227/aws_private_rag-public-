"""Tool_Guide_Parser Lambda handler — ingestion entry point.

Implements the ``handler(event) -> dict`` interface specified in design.md C2:

    handler(event) -> { doc_id: str, object_count: int, status: str }

Where ``status`` is ``"ok"`` on success or ``"error:<reason>"`` on failure
(e.g. ``"error:empty_document"``, ``"error:unsupported_format"``).

Key contracts (Requirements 1.4, 1.6, 2.8)
-------------------------------------------
**Idempotence (R1.6):**
  ``doc_id = sha1(normalize(tool_name) + normalize(doc_version) + normalize(filename))``
  is deterministic.  A second ingestion of the same logical document produces
  the same ``doc_id`` and the same object ``id``\\s, so the store upsert
  replaces existing records — no duplicates.

**Transaction (R2.8):**
  If ANY store write fails, the handler calls :meth:`IngestStore.rollback` to
  undo all writes made in this run, then returns ``"error:store_failure"``
  without persisting partial results.  The two-phase interface
  (``begin_transaction`` / ``commit`` / ``rollback``) lets the store
  implementation decide how to implement atomicity.

**Empty / unsupported input (R1.4, R2.8):**
  :func:`textualize_document` raises a typed :class:`~textualize.TextualizationError`
  for these cases.  The handler catches it, returns ``"error:<reason>"``, and
  writes nothing to the store.

**Source immutability:**
  The handler never modifies the S3 object; it only reads (via the injectable
  ``markdown_text`` / ``pdf_path`` paths).

IngestStore protocol (abstraction for testing)
-----------------------------------------------
Real production code uses a concrete store that talks to Qdrant and DynamoDB;
unit tests inject a fake/mock implementation.  The protocol is defined via
:class:`IngestStore` and the reference in-memory implementation
:class:`InMemoryIngestStore` is provided for testing.

Design.md C2 interface:
    parse_structure(text)          -> list[RelatedObject]   (pure, task 2.x)
    build_objects(parsed, meta)    -> list[ToolGuideObject] (task 3.x)
    handler(event)                 -> { doc_id, object_count, status }

Flat-module convention (mirrors other modules in tool_guide_parser_src):
absolute import, no package.

Requirements validated: 1.4, 1.6, 2.8
"""

from __future__ import annotations

import os
import sys

# Make bundled third-party packages importable in Lambda. Dependencies that are
# not in the Lambda runtime (notably pymupdf/fitz for PDF text extraction) are
# shipped under ``vendor/`` in the deployment package; add it to sys.path so
# ``import fitz`` resolves. No-op for local dev where pymupdf is pip-installed.
_VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

import logging
from typing import Any, Protocol, runtime_checkable

from build_objects import build_objects
from identifiers import make_doc_id
from parse_structure import parse_structure
from reference_chunker import chunk_reference
from schema import ToolGuideObject
from textualize import (
    OffsetMap,
    TextualizationError,
    textualize_document,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IngestStore protocol — abstraction so unit tests never need Qdrant/DDB
# ---------------------------------------------------------------------------


@runtime_checkable
class IngestStore(Protocol):
    """Abstract store interface consumed by :func:`handler`.

    Implementations must be safe to call repeatedly (idempotent upsert).
    ``begin_transaction`` / ``commit`` / ``rollback`` bracket a single
    ingestion run so any partial writes can be undone if a later write fails.

    Production code would connect to Qdrant (collection ``tool-guide-knowledge-base``)
    and DynamoDB (claim-db, partition ``pipeline_id=tool-guide``).  Unit tests
    inject :class:`InMemoryIngestStore` (or any other compatible object).
    """

    def begin_transaction(self) -> None:
        """Mark the start of an ingestion run; record the rollback checkpoint."""
        ...

    def upsert_object(self, doc_id: str, obj: ToolGuideObject) -> None:
        """Upsert a single object record, replacing any existing record with the same id.

        Must be called only between ``begin_transaction`` and
        ``commit``/``rollback``. Raises on write failure (exception propagates
        to the handler which then calls ``rollback``).
        """
        ...

    def commit(self) -> None:
        """Make all writes from this transaction durable.

        Called only when ALL ``upsert_object`` calls succeeded.
        """
        ...

    def rollback(self) -> None:
        """Undo all writes made since ``begin_transaction``.

        Called when ANY ``upsert_object`` call raised an exception.
        Implementations must be idempotent (safe to call even if no writes
        were made).
        """
        ...

    def list_ids_for_doc(self, doc_id: str) -> list[str]:
        """Return the object ids currently stored for ``doc_id``.

        Used to verify idempotence in tests; not required by production logic
        (the upsert contract ensures deduplication).
        """
        ...


# ---------------------------------------------------------------------------
# In-memory reference implementation (for unit/property tests)
# ---------------------------------------------------------------------------


class InMemoryIngestStore:
    """Simple in-memory :class:`IngestStore` implementation for tests.

    Provides full transaction semantics via a copy-on-write snapshot:
    ``begin_transaction`` takes a snapshot; ``rollback`` restores it.

    All methods are synchronous and raise ``RuntimeError`` on illegal call
    ordering so tests catch misuse early.
    """

    def __init__(self) -> None:
        # Primary store: doc_id -> {obj_id -> ToolGuideObject}
        self._store: dict[str, dict[str, ToolGuideObject]] = {}
        # Transaction snapshot — None means no active transaction.
        self._snapshot: dict[str, dict[str, ToolGuideObject]] | None = None
        self._in_transaction: bool = False

    # --- Transaction control ---

    def begin_transaction(self) -> None:
        """Start a new transaction; snapshot the current state for rollback."""
        if self._in_transaction:
            raise RuntimeError(
                "begin_transaction called while already in a transaction"
            )
        # Deep copy: each doc_id bucket is a fresh dict.
        self._snapshot = {doc: dict(objs) for doc, objs in self._store.items()}
        self._in_transaction = True

    def commit(self) -> None:
        """Commit the transaction: discard the snapshot."""
        if not self._in_transaction:
            raise RuntimeError("commit called outside of a transaction")
        self._snapshot = None
        self._in_transaction = False

    def rollback(self) -> None:
        """Roll back to the snapshot taken at ``begin_transaction``.

        Safe to call even when no transaction is active (no-op in that case),
        so the handler's ``except`` block can always call this safely.
        """
        if not self._in_transaction:
            # Defensive: rollback on a non-transacted store is a no-op.
            # The handler may call rollback in an except handler that fires
            # before begin_transaction succeeds; we tolerate this.
            return
        if self._snapshot is not None:
            self._store = self._snapshot
        self._snapshot = None
        self._in_transaction = False

    # --- Data operations ---

    def upsert_object(self, doc_id: str, obj: ToolGuideObject) -> None:
        """Insert or replace the object record, keyed by ``obj.id``."""
        if not self._in_transaction:
            raise RuntimeError("upsert_object called outside of a transaction")
        if doc_id not in self._store:
            self._store[doc_id] = {}
        self._store[doc_id][obj.id] = obj

    def list_ids_for_doc(self, doc_id: str) -> list[str]:
        """Return sorted list of object ids stored for ``doc_id``."""
        return sorted(self._store.get(doc_id, {}).keys())

    # --- Inspection helpers (tests only) ---

    def get_objects_for_doc(self, doc_id: str) -> list[ToolGuideObject]:
        """Return all objects stored for ``doc_id`` (sorted by id for stability)."""
        return sorted(self._store.get(doc_id, {}).values(), key=lambda o: o.id)

    def total_object_count(self) -> int:
        """Return the total number of records across all documents."""
        return sum(len(objs) for objs in self._store.values())


# ---------------------------------------------------------------------------
# Store write error (used by test helpers)
# ---------------------------------------------------------------------------


class StoreWriteError(Exception):
    """Raised by a store implementation when a write fails.

    The handler catches any exception during ``upsert_object`` and triggers
    rollback; this subclass provides a clearly identifiable test signal.
    """


# ---------------------------------------------------------------------------
# Test helper: store that fails after N successful upserts
# ---------------------------------------------------------------------------


class _FailAfterNStore(InMemoryIngestStore):
    """Test helper: raises :class:`StoreWriteError` after ``n`` successful upserts.

    Useful to verify that the handler rolls back partial writes on failure.
    """

    def __init__(self, fail_after: int) -> None:
        super().__init__()
        self._fail_after = fail_after
        self._upsert_count = 0

    def upsert_object(self, doc_id: str, obj: ToolGuideObject) -> None:
        if self._upsert_count >= self._fail_after:
            raise StoreWriteError(
                f"Simulated write failure after {self._fail_after} upserts"
            )
        super().upsert_object(doc_id, obj)
        self._upsert_count += 1


# ---------------------------------------------------------------------------
# Public handler entry point
# ---------------------------------------------------------------------------


def handler(
    event: dict[str, Any],
    *,
    store: IngestStore | None = None,
    markdown_text: str | None = None,
    pdf_path: str | None = None,
    head: bytes | None = None,
    tool_version: str = "",
    parse_mode: str = "tool_guide",
    vision_describe: Any = None,
) -> dict[str, Any]:
    """Process a single tool guide document ingestion event.

    This is the Lambda entry point (and the unit-testable pure-logic core when
    ``store`` / ``markdown_text`` / ``pdf_path`` are injected).

    Event schema (mirrors design.md C2 + C1 trigger payload)::

        {
            "bucket":      str,   # S3 bucket name (informational)
            "key":         str,   # Object key: <tool_name>/<doc_version>/<filename>
            "tool_name":   str,   # Extracted from the key path
            "doc_version": str,   # Extracted from the key path
            "filename":    str,   # Bare file name (last path segment)
        }

    Returns::

        {
            "doc_id":       str,  # sha1(norm(tool_name)+norm(doc_version)+norm(filename))
            "object_count": int,  # Number of objects stored on success; 0 on error
            "status":       str,  # "ok" | "error:<reason>"
        }

    Contracts
    ---------
    * **Idempotence (R1.6):** ``doc_id`` and all object ``id``\\s are derived
      deterministically from the normalized key path; re-ingesting the same
      logical document replaces existing records via upsert.
    * **Transaction (R2.8):** if any store write raises, ``store.rollback()``
      is called and ``status`` is ``"error:store_failure"``.  No partial results
      are persisted.
    * **Empty/unsupported (R1.4, R2.8):** a :class:`~textualize.TextualizationError`
      causes an immediate return of ``"error:<reason>"`` with zero writes.
    * **Source immutability:** the handler never modifies the S3 object.

    Args:
        event: Ingestion event dict (see schema above).
        store: :class:`IngestStore` implementation.  Production code passes a
            real Qdrant+DDB store; tests inject :class:`InMemoryIngestStore`.
            When ``None`` a new :class:`InMemoryIngestStore` is used (allows
            calling without injection for smoke tests).
        markdown_text: Pre-loaded Markdown content (required when the document
            is a Markdown file).  In Lambda, the caller downloads from S3 first.
        pdf_path: Local path to the PDF (required when the document is a PDF).
        head: Optional first bytes for format magic-byte detection.
        tool_version: Optional tool version override (when not derivable from
            the key path). Falls back to ``event["doc_version"]`` when empty.

    Returns:
        A ``dict`` with ``doc_id``, ``object_count``, and ``status``.
    """
    if store is None:
        store = InMemoryIngestStore()

    # --- Extract event fields ---
    tool_name: str = event.get("tool_name", "")
    doc_version: str = event.get("doc_version", "")
    filename: str = event.get("filename", "")

    # ``tool_version`` is separate from ``doc_version`` but often the same for
    # simple deployments.  The override kwarg lets callers supply it explicitly.
    effective_tool_version: str = tool_version or doc_version

    # --- Compute deterministic doc_id (R1.6, R3.6) ---
    doc_id = make_doc_id(tool_name, doc_version, filename)

    # --- Textualize: format detection + empty detection (R1.4, R2.8) ---
    try:
        textualize_result = textualize_document(
            filename,
            markdown_text=markdown_text,
            pdf_path=pdf_path,
            head=head,
            vision_describe=vision_describe,
        )
    except TextualizationError as exc:
        logger.warning("Textualization failed: %s", exc.status)
        # No writes at all — original content untouched (R1.4, R2.8).
        return {"doc_id": doc_id, "object_count": 0, "status": exc.status}
    except ValueError as exc:
        # Missing required argument (e.g. markdown_text not provided for .md).
        logger.warning("Textualization argument error: %s", exc)
        return {
            "doc_id": doc_id,
            "object_count": 0,
            "status": "error:missing_content",
        }

    text: str = textualize_result.text
    offset_map: OffsetMap = textualize_result.mapping

    # --- Parse + build records, by mode ---
    if parse_mode == "reference":
        # IP register databooks / reference manuals: size-based content chunking
        # with NO label heuristics (avoids command/option false positives) and
        # the chunk's real text as canonical_text (rich retrieval). R3.x preserved.
        objects = chunk_reference(
            text,
            tool_name=tool_name,
            tool_version=effective_tool_version,
            doc_version=doc_version,
            source_file=filename,
            offset_map=offset_map,
        )
    else:
        # "tool_guide" (default): label-based command/option extraction for
        # man-page-style EDA tool command references.
        # --- Pure structural parse (R2.2, R2.7) ---
        related_objects = parse_structure(text)

        # --- Build fully-populated records (R3.1–R3.6) ---
        objects = build_objects(
            related_objects,
            text=text,
            tool_name=tool_name,
            tool_version=effective_tool_version,
            doc_version=doc_version,
            source_file=filename,
            offset_map=offset_map,
        )

    # --- Transactional store writes (R2.8, R1.6) ---
    # begin_transaction snapshots the current state; any exception in the
    # upsert loop triggers rollback so no partial writes survive.
    try:
        store.begin_transaction()
    except Exception as exc:  # noqa: BLE001
        # begin_transaction itself failed (e.g. already in a transaction).
        # No writes have occurred yet, so no rollback needed.
        logger.error("begin_transaction failed: %s", exc)
        return {
            "doc_id": doc_id,
            "object_count": 0,
            "status": "error:store_failure",
        }

    try:
        if parse_mode == "reference" and hasattr(store, "bulk_upsert"):
            # Idempotent replace: drop any prior points for this doc first so a
            # changed parse (e.g. Vision rewriting page text, shifting chunk
            # offsets/ids) replaces cleanly instead of leaving stale duplicates.
            if hasattr(store, "delete_doc_points"):
                store.delete_doc_points(doc_id)
            # Bulk path: parallel embed + batched Qdrant upsert (large docs).
            store.bulk_upsert(doc_id, objects)
        else:
            for obj in objects:
                store.upsert_object(doc_id, obj)
        store.commit()
    except Exception as exc:  # noqa: BLE001
        # ANY write failure → rollback all writes made in this run.
        logger.error("Store write failed; rolling back. Error: %s", exc)
        store.rollback()
        return {
            "doc_id": doc_id,
            "object_count": 0,
            "status": "error:store_failure",
        }

    return {
        "doc_id": doc_id,
        "object_count": len(objects),
        "status": "ok",
    }

# ---------------------------------------------------------------------------
# Lambda entrypoint — AWS Lambda calls lambda_handler(event, context)
# ---------------------------------------------------------------------------

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint for S3-triggered Tool Guide document ingestion.

    Receives S3 ObjectCreated events, downloads the document from S3,
    extracts tool_name/doc_version/filename from the S3 key path, then
    delegates to the core ``handler()`` function.

    Expected S3 key layout:  <tool_name>/<doc_version>/<filename>
    Example: Atlas/ARM_CORTEX-A720AE/ver.1/vcs_user_guide.pdf

    Uses AwsIngestStore (Qdrant + DynamoDB + S3 published) for production.
    Falls back to error response on any unexpected exception without crashing.
    """
    import os
    import tempfile
    import urllib.parse
    import boto3

    logger_lh = logging.getLogger(__name__ + ".lambda_handler")

    # --- Search action (Tool Guide MCP query path) ---
    # The MCP bridge invokes this Lambda with {action: "search", query, ...}
    # instead of an S3 event. Branch here before the S3 ingestion loop.
    if event.get("action") == "search":
        query = event.get("query", "")
        tool_name = event.get("tool_name") or None
        tool_version = event.get("tool_version") or None
        top_k = int(event.get("max_results", 20))

        if not query or not query.strip():
            return {"error": "error:input_length", "results": [],
                    "message": "query must not be empty"}

        try:
            from aws_ingest_store import AwsIngestStore
            store = AwsIngestStore(
                s3_bucket=os.environ.get("TOOL_GUIDE_S3_BUCKET", ""),
                qdrant_endpoint=os.environ.get("QDRANT_ENDPOINT", ""),
                qdrant_api_key=None,
                bedrock_region=os.environ.get("BEDROCK_REGION", "us-east-1"),
                ddb_table_name=os.environ.get("CLAIM_DB_TABLE", "bos-ai-claim-db-dev"),
            )
            search_results = store.search(
                query=query,
                tool_name=tool_name,
                tool_version=tool_version,
                top_k=top_k,
            )
            if not search_results:
                msg = ("일치하는 객체 없음" if (tool_name or tool_version)
                       else "현재 index에서 확인 불가")
                return {"status": "ok", "results": [], "message": msg,
                        "total_hits": 0}
            return {"status": "ok", "results": search_results,
                    "total_hits": len(search_results)}
        except Exception as exc:
            logger_lh.exception("Search failed: %s", exc)
            return {"error": f"error:search_failed:{type(exc).__name__}",
                    "results": [], "message": str(exc)}

    # R7: build the Vision describer once per invocation when enabled (R7.5).
    vision_describe = None
    if os.environ.get("ENABLE_VISION_PARSING", "false").lower() == "true":
        try:
            from vision import make_bedrock_vision_describer
            vision_describe = make_bedrock_vision_describer()
            logger_lh.info("Vision parsing ENABLED")
        except Exception as exc:  # noqa: BLE001
            logger_lh.warning("Vision init failed; disabling Vision: %s", exc)
            vision_describe = None

    results = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        # Skip published/ artifacts written by this Lambda — prevents recursive loop
        if key.startswith("published/"):
            logger_lh.debug("Skipping Lambda-generated published artifact: %s", key)
            continue

        # Parse S3 key: <tool_name_path>/<doc_version>/<filename>
        # e.g. Atlas/ARM_CORTEX-A720AE/ver.1/guide.pdf
        parts = key.split("/")
        if len(parts) < 3:
            logger_lh.warning("Unexpected key format (need at least 3 parts): %s", key)
            results.append({"key": key, "status": "error:unexpected_key_format"})
            continue

        filename = parts[-1]
        doc_version = parts[-2]
        tool_name = "/".join(parts[:-2])  # e.g. "Atlas/ARM_CORTEX-A720AE"

        logger_lh.info(
            "Processing: bucket=%s key=%s tool=%s ver=%s file=%s",
            bucket, key, tool_name, doc_version, filename,
        )

        # Download object from S3
        s3_client = boto3.client("s3")
        try:
            s3_obj = s3_client.get_object(Bucket=bucket, Key=key)
            file_bytes = s3_obj["Body"].read()
        except Exception as exc:
            logger_lh.error("S3 download failed: %s/%s — %s", bucket, key, exc)
            results.append({"key": key, "status": "error:s3_download_failed"})
            continue

        # Determine format and prepare arguments for handler()
        fn_lower = filename.lower()
        markdown_text: str | None = None
        pdf_path: str | None = None
        tmp_file = None

        try:
            if fn_lower.endswith(".md"):
                markdown_text = file_bytes.decode("utf-8", errors="replace")
            elif fn_lower.endswith(".pdf"):
                tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp_file.write(file_bytes)
                tmp_file.flush()
                tmp_file.close()
                pdf_path = tmp_file.name
            else:
                logger_lh.warning("Unsupported format: %s", filename)
                results.append({"key": key, "status": "error:unsupported_format"})
                continue

            # Build the production store
            from aws_ingest_store import AwsIngestStore
            store = AwsIngestStore(
                s3_bucket=os.environ.get("TOOL_GUIDE_S3_BUCKET", bucket),
                qdrant_endpoint=os.environ.get("QDRANT_ENDPOINT", ""),
                qdrant_api_key=None,
                bedrock_region=os.environ.get("BEDROCK_REGION", "us-east-1"),
                ddb_table_name=os.environ.get("CLAIM_DB_TABLE", "bos-ai-claim-db-dev"),
            )

            ingestion_event = {
                "bucket": bucket,
                "key": key,
                "tool_name": tool_name,
                "doc_version": doc_version,
                "filename": filename,
            }

            result = handler(
                ingestion_event,
                store=store,
                markdown_text=markdown_text,
                pdf_path=pdf_path,
                parse_mode=os.environ.get("PARSE_MODE", "reference"),
                vision_describe=vision_describe,
            )
            logger_lh.info("Ingestion result: %s", result)
            results.append({"key": key, **result})

        except Exception as exc:
            logger_lh.exception("Unhandled error processing %s: %s", key, exc)
            results.append({
                "key": key,
                "status": f"error:unhandled:{type(exc).__name__}",
            })
        finally:
            if tmp_file is not None and os.path.exists(tmp_file.name):
                os.unlink(tmp_file.name)

    return {"results": results}
