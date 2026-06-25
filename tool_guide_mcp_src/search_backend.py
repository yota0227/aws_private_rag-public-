"""Concrete Qdrant search backend for Tool_Guide_MCP (Task 8.1).

Implements :class:`QdrantSearchBackend`, a callable that:

  1. Embeds the query via Bedrock Titan Embed v2 (same model as
     ``aws_ingest_store.py``, R1.5).
  2. Queries the Qdrant ``tool-guide-knowledge-base`` collection with an
     optional metadata filter (``tool_name``, ``tool_version``,
     ``active_types``).
  3. Returns raw candidate dicts shaped for :func:`result_processor.process_results`.

**MVP active_types restriction (R6.1, R6.5)**:
The constructor accepts ``active_types`` defaulting to
``frozenset(["command", "option"])``. Only objects whose ``object_type``
matches an active type are returned. Adding a new type in the future only
requires changing this set — no schema or pipeline changes.

**Injectable clients (for testing)**:
All Bedrock and Qdrant clients are constructor arguments so unit tests can
inject mocks without any monkey-patching.

Wire-up with ``mcp_tools.py``:
``tool_guide_search`` and ``tool_guide_query`` accept a ``search_backend``
callable, and now call ``process_results(backend_results, tool_name,
tool_version)`` after the backend returns raw candidates.  This completes
the S3 event -> parse -> store -> MCP -> result-shaping chain (design.md
Sequence Diagrams -- Query path).

Flat-module convention: no package prefix, mirrors other modules in this dir.

Requirements validated: 6.1, 6.5 (MVP type restriction)
Design reference: C3 Embedding & Index, C5 Tool_Guide_MCP
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (kept in sync with aws_ingest_store.py -- same model, same collection)
# ---------------------------------------------------------------------------

#: Qdrant collection dedicated to Tool Guide vectors (R5.1, Design C3).
TOOL_GUIDE_COLLECTION: str = "tool-guide-knowledge-base"

#: Pipeline identifier; every Qdrant payload carries this for corpus isolation.
TOOL_GUIDE_PIPELINE_ID: str = "tool-guide"

#: Bedrock Titan Embed v2 model (reused from ingestion, R1.5).
BEDROCK_EMBED_MODEL_ID: str = "amazon.titan-embed-text-v2:0"

#: Maximum Qdrant search hits to retrieve before post-processing.
#: Retrieve more than the final cap (20) so filtering (citation, type, metadata)
#: has room to work without running short.
_QDRANT_TOP_K: int = 50

#: MVP active object types (R6.1). Only these are included in search results.
_MVP_ACTIVE_TYPES: frozenset[str] = frozenset({"command", "option"})


# ---------------------------------------------------------------------------
# QdrantSearchBackend
# ---------------------------------------------------------------------------


class QdrantSearchBackend:
    """Callable search backend that embeds queries and queries Qdrant.

    Constructor
    -----------
    qdrant_endpoint : str
        Qdrant REST base URL (e.g. ``"http://qdrant:6333"``).
    qdrant_collection : str
        Collection name; defaults to ``"tool-guide-knowledge-base"``.
    bedrock_client : Any | None
        Injectable ``boto3`` ``bedrock-runtime`` client.  When ``None`` a real
        client is created lazily on first use (Lambda cold-start path).
    qdrant_api_key : str | None
        Qdrant API key.  When ``None`` the ``QDRANT_API_KEY`` env-var is read.
    active_types : frozenset[str] | None
        Object types included in search results.  Defaults to
        ``frozenset({"command", "option"})`` -- the MVP restriction (R6.1).
        Set to ``None`` or a larger set to activate additional types (R6.5).

    Callable interface
    ------------------
    ``backend(query, tool_name=None, tool_version=None, pipeline_token=None)``
    Returns a list of raw candidate dicts shaped for
    :func:`result_processor.process_results`.

    Each candidate dict has the shape::

        {
            "id":             str,
            "object_type":    str,
            "canonical_text": str,
            "score":          float,
            "pipeline_id":    "tool-guide",
            "metadata": {
                "tool_name":    str,
                "tool_version": str,
                "command":      str,
                "option":       str,
                "section":      str,
                "doc_version":  str,
                "object_type":  str,
            },
            "citation": {
                "source_file": str,
                "doc_version": str,
                "page":        int | None,
                "section":     str | None,
            }
        }
    """

    def __init__(
        self,
        qdrant_endpoint: str,
        qdrant_collection: str = TOOL_GUIDE_COLLECTION,
        bedrock_client: Any = None,
        qdrant_api_key: str | None = None,
        active_types: frozenset[str] | None = None,
    ) -> None:
        self._qdrant_endpoint = qdrant_endpoint
        self._qdrant_collection = qdrant_collection
        self._bedrock_client = bedrock_client
        self._qdrant_api_key = qdrant_api_key
        self._active_types: frozenset[str] = (
            active_types if active_types is not None else _MVP_ACTIVE_TYPES
        )

    # ------------------------------------------------------------------
    # Callable interface
    # ------------------------------------------------------------------

    def __call__(
        self,
        query: str,
        tool_name: str | None = None,
        tool_version: str | None = None,
        pipeline_token: str | None = None,
    ) -> list[dict[str, Any]]:
        """Embed *query* and search Qdrant; return raw candidate dicts.

        Parameters
        ----------
        query:
            The search or natural-language query string (already validated
            by :func:`mcp_tools.tool_guide_search` /
            :func:`mcp_tools.tool_guide_query`).
        tool_name:
            Optional filter; when supplied, Qdrant is asked to match
            ``payload.tool_name``.
        tool_version:
            Optional filter; when supplied, Qdrant is asked to match
            ``payload.tool_version``.
        pipeline_token:
            Not used by the backend directly (access check has already
            passed in ``mcp_tools``); accepted for API symmetry.

        Returns
        -------
        list[dict]
            Raw candidate dicts -- zero or more, each shaped for
            :func:`result_processor.process_results`.
        """
        # 1. Embed the query
        embedding = self._embed(query)

        # 2. Build Qdrant query payload with optional filters
        qdrant_payload = self._build_qdrant_payload(
            embedding=embedding,
            tool_name=tool_name,
            tool_version=tool_version,
        )

        # 3. Execute Qdrant search
        hits = self._qdrant_search(qdrant_payload)

        # 4. Convert Qdrant hits -> candidate dicts (apply active_types MVP filter)
        candidates = self._hits_to_candidates(hits)

        logger.debug(
            "QdrantSearchBackend: query_len=%d hits=%d candidates_after_filter=%d "
            "active_types=%r tool_name=%r tool_version=%r",
            len(query),
            len(hits),
            len(candidates),
            sorted(self._active_types),
            tool_name,
            tool_version,
        )
        return candidates

    # ------------------------------------------------------------------
    # Bedrock embedding
    # ------------------------------------------------------------------

    def _get_bedrock(self) -> Any:
        """Return the Bedrock runtime client, initializing lazily if needed."""
        if self._bedrock_client is None:
            import boto3  # type: ignore[import]
            bedrock_region = os.environ.get("BEDROCK_REGION", "us-east-1")
            self._bedrock_client = boto3.client(
                "bedrock-runtime", region_name=bedrock_region
            )
        return self._bedrock_client

    def _embed(self, text: str) -> list[float]:
        """Embed *text* via Bedrock Titan Embed v2; returns a 1024-dim vector.

        Raises
        ------
        RuntimeError
            If the Bedrock call fails.
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
            return result["embedding"]
        except Exception as exc:
            logger.error(
                "QdrantSearchBackend._embed failed: model=%r error=%s",
                BEDROCK_EMBED_MODEL_ID,
                exc,
            )
            raise RuntimeError(f"Bedrock embed failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Qdrant search
    # ------------------------------------------------------------------

    def _get_qdrant_api_key(self) -> str:
        """Return the Qdrant API key, reading from env-var if not injected."""
        if self._qdrant_api_key is None:
            self._qdrant_api_key = os.environ.get("QDRANT_API_KEY", "")
        return self._qdrant_api_key

    def _qdrant_headers(self) -> dict[str, str]:
        """Build HTTP headers for Qdrant requests."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._get_qdrant_api_key()
        if api_key:
            headers["api-key"] = api_key
        return headers

    def _build_qdrant_payload(
        self,
        embedding: list[float],
        tool_name: str | None,
        tool_version: str | None,
    ) -> dict[str, Any]:
        """Build the Qdrant ``/points/search`` request body.

        Applies metadata filters for ``tool_name``, ``tool_version``, AND the
        MVP ``active_types`` restriction in a single Qdrant filter so only
        relevant vectors are retrieved.

        Parameters
        ----------
        embedding:
            Query vector.
        tool_name:
            Optional exact-match filter on ``payload.tool_name``.
        tool_version:
            Optional exact-match filter on ``payload.tool_version``.

        Returns
        -------
        dict
            Qdrant search request body ready for JSON serialization.
        """
        # Build the must-conditions list
        must_conditions: list[dict[str, Any]] = [
            # Always restrict to this pipeline's corpus
            {
                "key": "pipeline_id",
                "match": {"value": TOOL_GUIDE_PIPELINE_ID},
            },
            # MVP: only active types (R6.1)
            {
                "key": "object_type",
                "match": {"any": sorted(self._active_types)},
            },
        ]

        if tool_name is not None:
            must_conditions.append(
                {"key": "tool_name", "match": {"value": tool_name}}
            )

        if tool_version is not None:
            must_conditions.append(
                {"key": "tool_version", "match": {"value": tool_version}}
            )

        return {
            "vector": embedding,
            "limit": _QDRANT_TOP_K,
            "with_payload": True,
            "filter": {"must": must_conditions},
        }

    def _qdrant_search(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """POST to Qdrant ``/points/search`` and return the hits list.

        Parameters
        ----------
        payload:
            Pre-built Qdrant search request body.

        Returns
        -------
        list[dict]
            The ``result`` array from the Qdrant response (may be empty).

        Raises
        ------
        RuntimeError
            On HTTP error or connection failure.
        """
        url = (
            f"{self._qdrant_endpoint}/collections/"
            f"{self._qdrant_collection}/points/search"
        )
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        for k, v in self._qdrant_headers().items():
            req.add_header(k, v)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                return raw.get("result", [])
        except urllib.error.HTTPError as exc:
            logger.error(
                "QdrantSearchBackend._qdrant_search HTTP error: %s %s",
                exc.code,
                exc.reason,
            )
            raise RuntimeError(
                f"Qdrant search failed: HTTP {exc.code} {exc.reason}"
            ) from exc
        except Exception as exc:
            logger.error(
                "QdrantSearchBackend._qdrant_search failed: %s", exc
            )
            raise RuntimeError(f"Qdrant search failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Hit conversion
    # ------------------------------------------------------------------

    def _hits_to_candidates(
        self, hits: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert raw Qdrant hits to candidate dicts for ``process_results``.

        Applies the MVP ``active_types`` filter as a client-side guard
        (Qdrant filter already restricts; this is a defensive double-check).
        Items without a payload or with a disallowed ``object_type`` are
        silently skipped.

        Parameters
        ----------
        hits:
            Raw entries from the Qdrant ``result`` array. Each hit has::

                {
                    "id":      int,       # Qdrant point id
                    "score":   float,
                    "payload": { ... }    # 7 metadata fields + pipeline_id etc.
                }

        Returns
        -------
        list[dict]
            Candidate dicts shaped for :func:`result_processor.process_results`.
        """
        candidates: list[dict[str, Any]] = []
        for hit in hits:
            payload: dict[str, Any] = hit.get("payload") or {}
            score: float = float(hit.get("score", 0.0))

            object_type: str = payload.get("object_type", "")

            # MVP active_types filter (R6.1) -- defensive client-side check
            if object_type not in self._active_types:
                continue

            # Extract 7 metadata fields
            metadata: dict[str, str] = {
                "tool_name": payload.get("tool_name", "미확인"),
                "tool_version": payload.get("tool_version", "미확인"),
                "command": payload.get("command", "미확인"),
                "option": payload.get("option", "미확인"),
                "section": payload.get("section", "미확인"),
                "doc_version": payload.get("doc_version", "미확인"),
                "object_type": object_type,
            }

            # Build citation from evidence fields stored in the payload.
            # aws_ingest_store writes source_file / doc_version / page / section
            # into the Qdrant payload (via the Evidence dataclass fields).
            citation: dict[str, Any] = {
                "source_file": payload.get("source_file", "미확인"),
                "doc_version": payload.get("doc_version", "미확인"),
                "page": payload.get("page"),       # int or None
                "section": payload.get("section"), # str or None
            }

            candidate: dict[str, Any] = {
                "id": payload.get("id", str(hit.get("id", ""))),
                "object_type": object_type,
                "canonical_text": payload.get("canonical_text", ""),
                "score": score,
                "pipeline_id": payload.get("pipeline_id", TOOL_GUIDE_PIPELINE_ID),
                "metadata": metadata,
                "citation": citation,
            }
            candidates.append(candidate)

        return candidates
