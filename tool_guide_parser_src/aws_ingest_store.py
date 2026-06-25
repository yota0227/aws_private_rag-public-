"""AWS-backed concrete IngestStore for Tool Guide RAG.

Implements the :class:`~handler.IngestStore` protocol defined in ``handler.py``
using real AWS services:

* **Bedrock** (``amazon.titan-embed-text-v2:0``) — embed ``canonical_text``
* **Qdrant** collection ``tool-guide-knowledge-base`` — upsert vector + payload
* **DynamoDB** ``bos-ai-claim-db-prod`` — upsert object record with
  ``pipeline_id=tool-guide`` partition key
* **S3** ``published/<doc_id>/<obj_id>.md`` +
  ``published/<doc_id>/<obj_id>.metadata.json`` — write canonical text sidecar

Design principles (Requirements 1.5, 3.5, 5.1)
-----------------------------------------------
* **No new model / table / index** — re-uses the existing Bedrock Titan Embed
  v2 model, the existing Qdrant engine (a different collection only), and the
  existing DynamoDB claim-db table (a different logical partition only).
* **Injectable clients** — all AWS / Qdrant clients are accepted as constructor
  arguments (default ``None`` for lazy init in Lambda cold start).  This makes
  unit tests trivial: pass mock objects and every real I/O call is intercepted.
* **Transaction semantics** — ``begin_transaction`` records a snapshot of
  object IDs written so far; ``rollback`` issues delete/put inverse operations
  to undo them.  Because real distributed systems can fail midway through a
  delete-undo pass, the implementation logs each undo step and swallows errors
  to avoid secondary failures during rollback.
* **Token guard (R4.10 / Design C3)** — before calling Bedrock embed, the
  character-length proxy check ``len(canonical_text) > 8192 * 4`` is applied.
  Titan Embed v2's binding token limit is 8 192 tokens; the 4x char proxy is a
  cheap pre-flight that catches grossly oversized inputs.  A warning is also
  logged when the text is close to the limit (>= 75 % of the proxy threshold).

Usage (production Lambda)::

    from aws_ingest_store import AwsIngestStore

    store = AwsIngestStore(
        s3_bucket="bos-ai-toolguide-docs-seoul",
        qdrant_endpoint=os.environ["QDRANT_ENDPOINT"],
        qdrant_api_key=secret_value,
        bedrock_region="us-east-1",
    )
    result = handler(event, store=store, markdown_text=text)

Flat-module convention: no package prefix, mirrors other modules in this dir.

Requirements validated: 1.5, 3.5, 5.1 (+ R4.10 token guard)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from schema import ToolGuideObject

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: The Qdrant collection for Tool Guide vectors (NOT the RTL collection).
TOOL_GUIDE_COLLECTION = "tool-guide-knowledge-base"

#: Pipeline identifier written to every record/payload so queries can filter
#: by pipeline without touching the RTL corpus.
TOOL_GUIDE_PIPELINE_ID = "tool-guide"

#: Bedrock model ID -- same model as RTL RAG (R1.5).
BEDROCK_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"

#: DynamoDB table -- existing table, different logical partition (R1.5).
CLAIM_DB_TABLE = "bos-ai-claim-db-prod"

#: Character-length proxy for 8 192-token limit  (4 chars ~= 1 token on average).
_TOKEN_LIMIT_CHAR_PROXY = 8192 * 4  # 32 768 chars
_TOKEN_WARN_THRESHOLD = int(_TOKEN_LIMIT_CHAR_PROXY * 0.75)  # 75 % ~= 24 576 chars


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TokenLimitError(ValueError):
    """Raised when ``canonical_text`` exceeds the Bedrock token-limit proxy.

    Corresponds to ``error:token_limit`` in the design error-handling table.
    """


class StoreWriteError(RuntimeError):
    """Raised when a write to an AWS service fails and cannot be retried."""


# ---------------------------------------------------------------------------
# AwsIngestStore
# ---------------------------------------------------------------------------


class AwsIngestStore:
    """Concrete IngestStore that writes to Qdrant / DDB / S3 via real AWS calls.

    All AWS and Qdrant clients are injected via the constructor so unit tests
    can pass mock objects without any monkey-patching.  When a parameter is
    ``None``, the client is created lazily on first use (production Lambda
    cold-start path).

    Transaction semantics
    ---------------------
    ``begin_transaction`` records the start of a write batch (doc_id snapshot).
    ``commit`` discards the checkpoint (all writes are already durable).
    ``rollback`` attempts to delete/undo every object written since
    ``begin_transaction``.  Rollback is best-effort: individual delete failures
    are logged but do not raise so the handler can always return cleanly.

    Parameters
    ----------
    s3_bucket:
        S3 bucket where published artifacts are written (e.g.
        ``"bos-ai-toolguide-docs-seoul"``).  When ``None`` the ``S3_BUCKET``
        env-var is read at first use.
    qdrant_endpoint:
        Qdrant REST endpoint URL.  When ``None`` the ``QDRANT_ENDPOINT``
        env-var is read at first use.
    qdrant_api_key:
        Qdrant API key.  When ``None`` the ``QDRANT_API_KEY`` env-var is read
        at first use.
    bedrock_region:
        AWS region for Bedrock (Virginia, ``us-east-1``).
    ddb_table_name:
        DynamoDB table name (default: :data:`CLAIM_DB_TABLE`).
    bedrock_client:
        Injectable ``boto3`` bedrock-runtime client (for tests).
    ddb_resource:
        Injectable ``boto3`` DynamoDB resource (for tests).
    s3_client:
        Injectable ``boto3`` S3 client (for tests).
    """

    def __init__(
        self,
        *,
        s3_bucket: str | None = None,
        qdrant_endpoint: str | None = None,
        qdrant_api_key: str | None = None,
        bedrock_region: str = "us-east-1",
        ddb_table_name: str = CLAIM_DB_TABLE,
        bedrock_client: Any = None,
        ddb_resource: Any = None,
        s3_client: Any = None,
    ) -> None:
        self._s3_bucket = s3_bucket
        self._qdrant_endpoint = qdrant_endpoint
        self._qdrant_api_key = qdrant_api_key
        self._bedrock_region = bedrock_region
        self._ddb_table_name = ddb_table_name

        # Injected clients (None -> lazy-init in Lambda)
        self._bedrock_client = bedrock_client
        self._ddb_resource = ddb_resource
        self._s3_client = s3_client

        # Transaction state
        self._in_transaction: bool = False
        # List of (doc_id, obj_id) tuples written since begin_transaction.
        self._written_this_tx: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # Lazy client initializers (production Lambda only -- tests inject mocks)
    # ------------------------------------------------------------------

    def _get_bedrock(self) -> Any:
        if self._bedrock_client is None:
            import boto3
            from botocore.config import Config

            # Adaptive retries: bulk embedding fires many concurrent Titan calls,
            # so throttling is expected under load. Adaptive mode backs off and
            # retries automatically instead of failing the whole document.
            self._bedrock_client = boto3.client(
                "bedrock-runtime",
                region_name=self._bedrock_region,
                config=Config(retries={"max_attempts": 8, "mode": "adaptive"}),
            )
        return self._bedrock_client

    def _get_ddb_resource(self) -> Any:
        if self._ddb_resource is None:
            import boto3
            self._ddb_resource = boto3.resource(
                "dynamodb", region_name="ap-northeast-2"
            )
        return self._ddb_resource

    def _get_s3(self) -> Any:
        if self._s3_client is None:
            import boto3
            self._s3_client = boto3.client("s3", region_name="ap-northeast-2")
        return self._s3_client

    def _get_qdrant_endpoint(self) -> str:
        if self._qdrant_endpoint is None:
            self._qdrant_endpoint = os.environ.get("QDRANT_ENDPOINT", "")
        return self._qdrant_endpoint

    def _get_qdrant_api_key(self) -> str:
        if self._qdrant_api_key is None:
            # First try plain env var (local dev / direct injection)
            direct = os.environ.get("QDRANT_API_KEY", "")
            if direct:
                self._qdrant_api_key = direct
            else:
                # Fall back to Secrets Manager ARN (Lambda production path)
                secret_arn = os.environ.get("QDRANT_API_KEY_SECRET_ARN", "")
                if secret_arn:
                    try:
                        import boto3
                        sm = boto3.client(
                            "secretsmanager",
                            region_name=os.environ.get("AWS_REGION", "ap-northeast-2"),
                        )
                        resp = sm.get_secret_value(SecretId=secret_arn)
                        self._qdrant_api_key = resp.get("SecretString", "")
                    except Exception as exc:
                        logger.warning(
                            "Failed to fetch Qdrant API key from Secrets Manager: %s", exc
                        )
                        self._qdrant_api_key = ""
                else:
                    self._qdrant_api_key = ""
        return self._qdrant_api_key

    def _get_s3_bucket(self) -> str:
        if self._s3_bucket is None:
            self._s3_bucket = os.environ.get("S3_BUCKET", "")
        return self._s3_bucket

    # ------------------------------------------------------------------
    # IngestStore protocol implementation
    # ------------------------------------------------------------------

    def begin_transaction(self) -> None:
        """Start a transaction: reset the rollback journal."""
        if self._in_transaction:
            raise RuntimeError(
                "begin_transaction called while already in a transaction"
            )
        self._written_this_tx = []
        self._in_transaction = True

    def commit(self) -> None:
        """Commit: discard the journal (writes are already durable)."""
        if not self._in_transaction:
            raise RuntimeError("commit called outside of a transaction")
        self._written_this_tx = []
        self._in_transaction = False

    def rollback(self) -> None:
        """Best-effort rollback: delete all records written this transaction.

        Individual delete failures are logged but swallowed -- rollback must
        never raise so the handler's except clause can always return cleanly.
        """
        if not self._in_transaction:
            return  # No-op; tolerates rollback outside transaction (R2.8).

        for doc_id, obj_id in self._written_this_tx:
            # Attempt to delete the Qdrant point
            try:
                self._qdrant_delete_by_obj_id(obj_id)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    json.dumps({
                        "event": "rollback_qdrant_delete_failed",
                        "obj_id": obj_id,
                        "error": str(exc),
                    })
                )
            # Attempt to delete the DynamoDB item
            try:
                self._ddb_delete(obj_id)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    json.dumps({
                        "event": "rollback_ddb_delete_failed",
                        "obj_id": obj_id,
                        "error": str(exc),
                    })
                )
            # Attempt to delete S3 artifacts
            try:
                safe_obj_id = obj_id.replace("#", "_")
                s3_md_key = f"published/{doc_id}/{safe_obj_id}.md"
                s3_meta_key = f"published/{doc_id}/{safe_obj_id}.metadata.json"
                s3 = self._get_s3()
                bucket = self._get_s3_bucket()
                if bucket:
                    s3.delete_object(Bucket=bucket, Key=s3_md_key)
                    s3.delete_object(Bucket=bucket, Key=s3_meta_key)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    json.dumps({
                        "event": "rollback_s3_delete_failed",
                        "obj_id": obj_id,
                        "error": str(exc),
                    })
                )

        self._written_this_tx = []
        self._in_transaction = False

    def upsert_object(self, doc_id: str, obj: ToolGuideObject) -> None:
        """Embed, upsert to Qdrant, DynamoDB, and S3 for one ToolGuideObject.

        Raises :class:`StoreWriteError` on any write failure so the handler can
        trigger rollback.

        Parameters
        ----------
        doc_id:
            Document-level identifier (sha1 digest from :func:`make_doc_id`).
        obj:
            Fully-populated :class:`~schema.ToolGuideObject`.
        """
        if not self._in_transaction:
            raise RuntimeError("upsert_object called outside of a transaction")

        # 1. Token guard (R4.10 / Design C3): fast char-proxy check before Bedrock call.
        self._check_token_limit(obj.canonical_text, obj.id)

        # 2. Embed canonical_text -> 1024-dim vector.
        embedding = self._embed(obj.canonical_text)

        # 3. Upsert to Qdrant (collection tool-guide-knowledge-base).
        self._qdrant_upsert(obj, embedding)

        # 4. Upsert to DynamoDB (pipeline_id=tool-guide partition).
        self._ddb_upsert(doc_id, obj)

        # 5. Write S3 published artifacts.
        self._s3_write(doc_id, obj)

        # Record in rollback journal.
        self._written_this_tx.append((doc_id, obj.id))

        logger.info(
            json.dumps({
                "event": "tool_guide_object_upserted",
                "obj_id": obj.id,
                "doc_id": doc_id,
                "object_type": obj.object_type,
                "pipeline_id": TOOL_GUIDE_PIPELINE_ID,
            })
        )

    def bulk_upsert(
        self,
        doc_id: str,
        objects: list[ToolGuideObject],
        *,
        max_workers: int = 32,
        qdrant_batch: int = 128,
    ) -> None:
        """Bulk-embed and batch-upsert many objects to Qdrant (Qdrant-only path).

        Optimized for large reference documents (hundreds–thousands of chunks):

        * embeds ``canonical_text`` in parallel (:class:`ThreadPoolExecutor`),
        * upserts to Qdrant in batches (``qdrant_batch`` points per request),
        * **skips** the per-object DynamoDB + S3 sidecar writes that
          :meth:`upsert_object` performs.  The Tool Guide search path reads
          Qdrant only; writing ~430k claim-db rows and ~860k S3 sidecar objects
          would add no retrieval value and would bloat the shared claim-db.

        Order is preserved. Any embed/Qdrant failure raises (the handler then
        calls :meth:`rollback`, which deletes the Qdrant points written so far).

        Args:
            doc_id: Document-level identifier.
            objects: Fully-populated objects to index.
            max_workers: Parallel embedding worker threads.
            qdrant_batch: Points per Qdrant upsert request.

        Raises:
            StoreWriteError / TokenLimitError: On any write failure.
        """
        if not self._in_transaction:
            raise RuntimeError("bulk_upsert called outside of a transaction")
        if not objects:
            return

        endpoint = self._get_qdrant_endpoint()
        if not endpoint:
            raise StoreWriteError("QDRANT_ENDPOINT is not configured")

        # Pre-init shared clients/keys once so worker threads don't race on
        # lazy initialization (boto3 clients are thread-safe once created).
        self._get_bedrock()
        self._get_qdrant_api_key()

        # 1. Parallel embed (executor.map preserves input order). Token-check first.
        def _embed_one(obj: ToolGuideObject) -> tuple[ToolGuideObject, list[float]]:
            self._check_token_limit(obj.canonical_text, obj.id)
            return obj, self._embed(obj.canonical_text)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            embedded = list(executor.map(_embed_one, objects))

        # 2. Batched Qdrant upsert (many points per PUT).
        url = f"{endpoint}/collections/{TOOL_GUIDE_COLLECTION}/points?wait=true"
        for i in range(0, len(embedded), qdrant_batch):
            batch = embedded[i : i + qdrant_batch]
            points = [self._qdrant_point(o, e, doc_id=doc_id) for o, e in batch]
            body = json.dumps({"points": points}).encode("utf-8")
            self._qdrant_request(url, body, "PUT")
            for o, _ in batch:
                self._written_this_tx.append((doc_id, o.id))

        logger.info(
            json.dumps({
                "event": "tool_guide_bulk_upserted",
                "doc_id": doc_id,
                "object_count": len(embedded),
                "pipeline_id": TOOL_GUIDE_PIPELINE_ID,
            })
        )

    def list_ids_for_doc(self, doc_id: str) -> list[str]:
        """Return object ids stored for *doc_id* (reads from DynamoDB).

        Performs a DynamoDB query using a ``doc_id-index`` GSI when available.
        Falls back to empty list on error (test mocks override this method).
        """
        try:
            table = self._get_ddb_resource().Table(self._ddb_table_name)
            response = table.query(
                IndexName="doc_id-index",
                KeyConditionExpression="doc_id = :did",
                ExpressionAttributeValues={":did": doc_id},
            )
            return sorted(item["id"] for item in response.get("Items", []))
        except Exception as exc:
            logger.warning(
                json.dumps({
                    "event": "list_ids_for_doc_error",
                    "doc_id": doc_id,
                    "error": str(exc),
                })
            )
            return []

    # ------------------------------------------------------------------
    # Internal helpers -- Bedrock embedding
    # ------------------------------------------------------------------

    @staticmethod
    def _check_token_limit(text: str, obj_id: str = "") -> None:
        """Raise :class:`TokenLimitError` if *text* is too long.

        Also emits a WARNING when the text is close to the limit (>= 75 %).
        This is the cheap character-proxy guard described in Design C3 (R4.10).

        Args:
            text: The ``canonical_text`` to check.
            obj_id: Object identifier for log context.

        Raises:
            TokenLimitError: If ``len(text) > _TOKEN_LIMIT_CHAR_PROXY``.
        """
        char_len = len(text)
        if char_len >= _TOKEN_WARN_THRESHOLD:
            logger.warning(
                json.dumps({
                    "event": "token_limit_approaching",
                    "obj_id": obj_id,
                    "char_len": char_len,
                    "threshold": _TOKEN_WARN_THRESHOLD,
                    "hard_limit": _TOKEN_LIMIT_CHAR_PROXY,
                })
            )
        if char_len > _TOKEN_LIMIT_CHAR_PROXY:
            raise TokenLimitError(
                f"canonical_text for {obj_id!r} exceeds token-limit proxy "
                f"({char_len} chars > {_TOKEN_LIMIT_CHAR_PROXY}). "
                "Shorten canonical_text or check the parser output."
            )

    def _embed(self, text: str) -> list[float]:
        """Call Bedrock Titan Embed v2 and return a 1024-dim float vector.

        Args:
            text: The text to embed (already token-limit-checked).

        Returns:
            A list of 1024 floats.

        Raises:
            StoreWriteError: If the Bedrock call fails.
        """
        client = self._get_bedrock()
        body = json.dumps({"inputText": text})
        try:
            response = client.invoke_model(
                modelId=BEDROCK_EMBED_MODEL_ID,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            embedding = result["embedding"]
            logger.debug(
                json.dumps({
                    "event": "bedrock_embed_ok",
                    "model": BEDROCK_EMBED_MODEL_ID,
                    "dim": len(embedding),
                })
            )
            return embedding
        except Exception as exc:
            logger.error(
                json.dumps({
                    "event": "bedrock_embed_error",
                    "model": BEDROCK_EMBED_MODEL_ID,
                    "error": str(exc),
                })
            )
            raise StoreWriteError(f"Bedrock embed failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal helpers -- Qdrant
    # ------------------------------------------------------------------

    @staticmethod
    def _qdrant_point_id(obj_id: str) -> int:
        """Deterministic Qdrant point ID from ``obj_id`` (non-negative int)."""
        digest = hashlib.sha256(obj_id.encode("utf-8")).hexdigest()[:16]
        return int(digest, 16) % (2**63)

    def _qdrant_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._get_qdrant_api_key()
        if api_key:
            headers["api-key"] = api_key
        return headers

    def _qdrant_request(self, url: str, body: bytes, method: str) -> None:
        """Execute a Qdrant REST request.

        Raises:
            StoreWriteError: On HTTP error or connection failure.
        """
        req = urllib.request.Request(url, data=body, method=method)
        for k, v in self._qdrant_headers().items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status not in (200, 201, 202):
                    raise StoreWriteError(
                        f"Qdrant returned HTTP {resp.status} for {url}"
                    )
        except urllib.error.HTTPError as exc:
            raise StoreWriteError(
                f"Qdrant HTTP error {exc.code}: {exc.reason}"
            ) from exc
        except StoreWriteError:
            raise
        except Exception as exc:
            raise StoreWriteError(f"Qdrant request failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Search (query path — used by the Tool Guide MCP search action)
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        tool_name: str | None = None,
        tool_version: str | None = None,
        top_k: int = 20,
    ) -> list[dict]:
        """Embed *query* and search the Tool Guide Qdrant collection.

        Returns a list of result dicts (already capped at *top_k*, sorted by
        relevance score descending). Each result carries the 7 metadata fields,
        ``canonical_text``, ``score``, and a ``citation`` block so the MCP layer
        can render evidence.

        Args:
            query: Natural-language or symbol query string.
            tool_name: Optional metadata filter (exact match against the stored
                ``tool_name`` payload value).
            tool_version: Optional metadata filter.
            top_k: Maximum number of results to return.

        Raises:
            StoreWriteError: On embed or Qdrant failure.
        """
        endpoint = self._get_qdrant_endpoint()
        if not endpoint:
            raise StoreWriteError("QDRANT_ENDPOINT is not configured")

        # 1. Embed the query (reuses the same Titan model as ingestion).
        embedding = self._embed(query)

        # 2. Build Qdrant search body with optional metadata filters.
        must: list[dict[str, Any]] = [
            {"key": "pipeline_id", "match": {"value": TOOL_GUIDE_PIPELINE_ID}}
        ]
        if tool_name:
            must.append({"key": "tool_name", "match": {"value": tool_name}})
        if tool_version:
            must.append({"key": "tool_version", "match": {"value": tool_version}})

        # Retrieve more than top_k so citation filtering has headroom.
        search_body = {
            "vector": embedding,
            "limit": max(top_k * 3, top_k),
            "with_payload": True,
            "filter": {"must": must},
        }
        body = json.dumps(search_body).encode("utf-8")
        url = f"{endpoint}/collections/{TOOL_GUIDE_COLLECTION}/points/search"

        req = urllib.request.Request(url, data=body, method="POST")
        for k, v in self._qdrant_headers().items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise StoreWriteError(
                f"Qdrant search HTTP error {exc.code}: {exc.reason}"
            ) from exc
        except Exception as exc:
            raise StoreWriteError(f"Qdrant search failed: {exc}") from exc

        hits = raw.get("result", [])

        # 3. Convert hits → result dicts with citation, drop incomplete citations.
        results: list[dict] = []
        for hit in hits:
            payload = hit.get("payload") or {}
            citation = {
                "source_file": payload.get("source_file", payload.get("doc_version", "")),
                "doc_version": payload.get("doc_version", ""),
                "page": payload.get("page"),
                "section": payload.get("section"),
            }
            # Citation completeness: need source_file + doc_version + (page|section)
            has_src = citation["source_file"] not in (None, "", "미확인")
            has_ver = citation["doc_version"] not in (None, "", "미확인")
            has_loc = (citation["page"] is not None) or (
                citation["section"] not in (None, "", "미확인")
            )
            if not (has_src and has_ver and has_loc):
                continue

            results.append({
                "id": payload.get("id", str(hit.get("id", ""))),
                "object_type": payload.get("object_type", ""),
                "canonical_text": payload.get("canonical_text", ""),
                "score": float(hit.get("score", 0.0)),
                "pipeline_id": payload.get("pipeline_id", TOOL_GUIDE_PIPELINE_ID),
                "tool_name": payload.get("tool_name", ""),
                "tool_version": payload.get("tool_version", ""),
                "command": payload.get("command", ""),
                "option": payload.get("option", ""),
                "citation": citation,
            })

        # 4. Sort by score desc, cap at top_k.
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    def _qdrant_point(
        self,
        obj: ToolGuideObject,
        embedding: list[float],
        doc_id: str | None = None,
    ) -> dict[str, Any]:
        """Build a single Qdrant point dict (id + vector + payload) for ``obj``.

        Shared by :meth:`_qdrant_upsert` (single) and :meth:`bulk_upsert`
        (batched). The payload includes all 7 metadata fields, ``pipeline_id``,
        the object ``id``, ``canonical_text``, the evidence provenance
        (``source_file`` + ``page``) needed for citation rendering (R3.3), and
        ``doc_id`` when provided (so a document's points can be deleted as a
        unit before re-ingestion — idempotent replacement, R1.6).
        """
        meta = obj.metadata.to_dict()  # All 7 fields guaranteed by schema
        ev = obj.evidence  # source provenance (R3.3): source_file + page/section

        payload: dict[str, Any] = {
            # --- 7 metadata fields (R3.1) ---
            "tool_name": meta["tool_name"],
            "tool_version": meta["tool_version"],
            "command": meta["command"],
            "option": meta["option"],
            "section": meta["section"],
            "doc_version": meta["doc_version"],
            "object_type": meta["object_type"],
            # --- pipeline identifier (R5.1, Design C3) ---
            "pipeline_id": TOOL_GUIDE_PIPELINE_ID,
            # --- convenience / search fields ---
            "id": obj.id,
            "canonical_text": obj.canonical_text,
            # --- evidence provenance for citation rendering (R3.3) ---
            # source_file + page live in evidence, not metadata; they MUST be
            # written here or search() falls back source_file -> doc_version.
            "source_file": ev.source_file,
            "page": ev.page,
        }
        if doc_id is not None:
            payload["doc_id"] = doc_id
        return {
            "id": self._qdrant_point_id(obj.id),
            "vector": embedding,
            "payload": payload,
        }

    def delete_doc_points(self, doc_id: str) -> None:
        """Delete all Qdrant points of one document (by ``doc_id`` payload).

        Called before re-ingesting a document so a changed parse (e.g. Vision
        rewriting page text, which shifts chunk offsets and thus point ids)
        replaces the document cleanly instead of leaving stale duplicate points
        (idempotent re-ingestion, R1.6). No-op if Qdrant is not configured.

        Raises:
            StoreWriteError: If the Qdrant delete call fails.
        """
        endpoint = self._get_qdrant_endpoint()
        if not endpoint:
            return
        body = json.dumps({
            "filter": {
                "must": [
                    {"key": "pipeline_id", "match": {"value": TOOL_GUIDE_PIPELINE_ID}},
                    {"key": "doc_id", "match": {"value": doc_id}},
                ]
            }
        }).encode("utf-8")
        url = f"{endpoint}/collections/{TOOL_GUIDE_COLLECTION}/points/delete?wait=true"
        self._qdrant_request(url, body, "POST")
        logger.info(
            json.dumps({"event": "tool_guide_doc_points_deleted", "doc_id": doc_id})
        )

    def _qdrant_upsert(self, obj: ToolGuideObject, embedding: list[float]) -> None:
        """Upsert one point to Qdrant collection ``tool-guide-knowledge-base``.

        Args:
            obj: Fully-populated ToolGuideObject.
            embedding: 1024-dim float vector.

        Raises:
            StoreWriteError: If the Qdrant call fails.
        """
        endpoint = self._get_qdrant_endpoint()
        if not endpoint:
            raise StoreWriteError("QDRANT_ENDPOINT is not configured")

        point = self._qdrant_point(obj, embedding)
        body = json.dumps({"points": [point]}).encode("utf-8")

        url = f"{endpoint}/collections/{TOOL_GUIDE_COLLECTION}/points?wait=true"
        self._qdrant_request(url, body, "PUT")

        logger.info(
            json.dumps({
                "event": "qdrant_upsert_ok",
                "collection": TOOL_GUIDE_COLLECTION,
                "obj_id": obj.id,
                "point_id": point["id"],
            })
        )

    def _qdrant_delete_by_obj_id(self, obj_id: str) -> None:
        """Delete a Qdrant point by its derived integer ID (best-effort rollback).

        Args:
            obj_id: The ToolGuideObject id string.

        Raises:
            StoreWriteError: On failure (caller catches and logs).
        """
        endpoint = self._get_qdrant_endpoint()
        if not endpoint:
            return  # Nothing to roll back if endpoint isn't configured.

        point_id = self._qdrant_point_id(obj_id)
        body = json.dumps({"points": [point_id]}).encode("utf-8")
        url = f"{endpoint}/collections/{TOOL_GUIDE_COLLECTION}/points/delete?wait=true"
        self._qdrant_request(url, body, "POST")

    # ------------------------------------------------------------------
    # Internal helpers -- DynamoDB
    # ------------------------------------------------------------------

    def _ddb_upsert(self, doc_id: str, obj: ToolGuideObject) -> None:
        """Upsert the object record to DynamoDB with ``pipeline_id=tool-guide``.

        The record shape is compatible with the existing claim-db usage patterns
        (R3.5, R1.5) -- same table, different logical partition.

        Args:
            doc_id: Document-level sha1 identifier.
            obj: Fully-populated ToolGuideObject.

        Raises:
            StoreWriteError: If the DynamoDB call fails.
        """
        table = self._get_ddb_resource().Table(self._ddb_table_name)
        item = obj.to_dict()  # {id, object_type, canonical_text, metadata, evidence}
        item["pipeline_id"] = TOOL_GUIDE_PIPELINE_ID
        item["doc_id"] = doc_id
        # claim-db table uses claim_id (HASH) + version (RANGE) as primary key
        item["claim_id"] = obj.id
        item["version"] = 1
        try:
            table.put_item(Item=item)
            logger.info(
                json.dumps({
                    "event": "ddb_upsert_ok",
                    "table": self._ddb_table_name,
                    "obj_id": obj.id,
                    "pipeline_id": TOOL_GUIDE_PIPELINE_ID,
                })
            )
        except Exception as exc:
            logger.error(
                json.dumps({
                    "event": "ddb_upsert_error",
                    "obj_id": obj.id,
                    "error": str(exc),
                })
            )
            raise StoreWriteError(
                f"DynamoDB put_item failed for {obj.id}: {exc}"
            ) from exc

    def _ddb_delete(self, obj_id: str) -> None:
        """Delete a DynamoDB record by ``id`` (best-effort rollback).

        Args:
            obj_id: The ToolGuideObject id string (DDB primary key ``id``).

        Raises:
            StoreWriteError: On failure (caller catches and logs).
        """
        table = self._get_ddb_resource().Table(self._ddb_table_name)
        try:
            table.delete_item(
                Key={"id": obj_id, "pipeline_id": TOOL_GUIDE_PIPELINE_ID}
            )
        except Exception as exc:
            raise StoreWriteError(
                f"DynamoDB delete_item failed for {obj_id}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers -- S3 published artifacts
    # ------------------------------------------------------------------

    def _s3_write(self, doc_id: str, obj: ToolGuideObject) -> None:
        """Write ``.md`` and ``.metadata.json`` artifacts to S3.

        Paths::

            published/<doc_id>/<safe_obj_id>.md
            published/<doc_id>/<safe_obj_id>.metadata.json

        The ``.md`` file contains ``canonical_text`` (UTF-8).
        The ``.metadata.json`` file contains the full serialized record
        including metadata, evidence, ``pipeline_id``, and ``doc_id``.

        ``#`` characters in ``obj_id`` are replaced with ``_`` to produce a
        valid S3 key component.

        Args:
            doc_id: Document-level sha1 identifier.
            obj: Fully-populated ToolGuideObject.

        Raises:
            StoreWriteError: If either S3 put_object call fails.
        """
        s3 = self._get_s3()
        bucket = self._get_s3_bucket()
        if not bucket:
            raise StoreWriteError("S3_BUCKET is not configured")

        # Sanitise obj_id for use in an S3 key: '#' -> '_'
        safe_obj_id = obj.id.replace("#", "_")

        md_key = f"published/{doc_id}/{safe_obj_id}.md"
        meta_key = f"published/{doc_id}/{safe_obj_id}.metadata.json"

        # .md -- canonical text
        try:
            s3.put_object(
                Bucket=bucket,
                Key=md_key,
                Body=obj.canonical_text.encode("utf-8"),
                ContentType="text/markdown; charset=utf-8",
            )
            logger.info(
                json.dumps({"event": "s3_put_ok", "key": md_key, "bucket": bucket})
            )
        except Exception as exc:
            logger.error(
                json.dumps({"event": "s3_put_error", "key": md_key, "error": str(exc)})
            )
            raise StoreWriteError(
                f"S3 put_object failed for {md_key}: {exc}"
            ) from exc

        # .metadata.json -- full record (metadata + evidence + pipeline tags)
        meta_payload = obj.to_dict()
        meta_payload["pipeline_id"] = TOOL_GUIDE_PIPELINE_ID
        meta_payload["doc_id"] = doc_id
        try:
            s3.put_object(
                Bucket=bucket,
                Key=meta_key,
                Body=json.dumps(meta_payload, ensure_ascii=False, indent=2).encode("utf-8"),
                ContentType="application/json; charset=utf-8",
            )
            logger.info(
                json.dumps({"event": "s3_put_ok", "key": meta_key, "bucket": bucket})
            )
        except Exception as exc:
            logger.error(
                json.dumps({"event": "s3_put_error", "key": meta_key, "error": str(exc)})
            )
            raise StoreWriteError(
                f"S3 put_object failed for {meta_key}: {exc}"
            ) from exc
