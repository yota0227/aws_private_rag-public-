"""Qdrant REST API client for RTL knowledge base.

Provides index and search operations compatible with the existing
OpenSearch-based pipeline. Uses urllib (no external dependencies).
"""
import hashlib
import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

QDRANT_ENDPOINT = os.environ.get("QDRANT_ENDPOINT", "")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "rtl-knowledge-base")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")


def _make_request(url: str, data: bytes, method: str) -> urllib.request.Request:
    """Create a urllib Request with Content-Type and optional API key header."""
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if QDRANT_API_KEY:
        req.add_header("api-key", QDRANT_API_KEY)
    return req


def index_document(metadata: dict, embedding: list) -> bool:
    """Index a document to Qdrant.

    Args:
        metadata: Document metadata (module_name, port_list, etc.)
        embedding: 1024-dim vector from Titan Embeddings v2

    Returns:
        True if successful, False otherwise
    """
    if not QDRANT_ENDPOINT:
        logger.warning("QDRANT_ENDPOINT not set, skipping indexing")
        return False

    doc_id = hashlib.sha256(metadata.get("file_path", "").encode()).hexdigest()[:16]
    # Convert hex to int for Qdrant point ID
    point_id = int(doc_id, 16) % (2**63)

    payload = {
        "module_name": metadata.get("module_name", ""),
        "parent_module": metadata.get("parent_module", ""),
        "port_list": _to_text(metadata.get("port_list", "")),
        "parameter_list": _to_text(metadata.get("parameter_list", "")),
        "instance_list": _to_text(metadata.get("instance_list", "")),
        "file_path": metadata.get("file_path", ""),
        "parsed_summary": metadata.get("parsed_summary", ""),
        "pipeline_id": metadata.get("pipeline_id", ""),
        "analysis_type": metadata.get("analysis_type", "module_parse"),
        "claim_text": metadata.get("claim_text", ""),
        "claim_type": metadata.get("claim_type", ""),
        "claim_id": metadata.get("claim_id", ""),
        "topic": metadata.get("topic", ""),
        "hdd_content": metadata.get("hdd_content", ""),
        "hdd_section_title": metadata.get("hdd_section_title", ""),
        "parent_module_name": metadata.get("parent_module_name", ""),
        "sub_record_type": metadata.get("sub_record_type", ""),
        "edge_type": metadata.get("edge_type", ""),
        "src": metadata.get("src", ""),
        "dst": metadata.get("dst", ""),
        "category": metadata.get("category", ""),
        "raw_text": metadata.get("raw_text", ""),
        "parser_source": metadata.get("parser_source", ""),
    }

    body = json.dumps({
        "points": [{
            "id": point_id,
            "vector": embedding,
            "payload": payload,
        }]
    }).encode()

    url = f"{QDRANT_ENDPOINT}/collections/{QDRANT_COLLECTION}/points?wait=false"
    req = _make_request(url, body, "PUT")

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201):
                logger.info(json.dumps({"event": "qdrant_indexed", "file_path": metadata.get("file_path", "")}))
                return True
            else:
                logger.error(json.dumps({"event": "qdrant_index_error", "status": resp.status}))
                return False
    except Exception as e:
        logger.error(json.dumps({"event": "qdrant_index_error", "error": str(e)}))
        return False


def search(query_vector: list = None, query_text: str = "", max_results: int = 20,
           pipeline_id: str = "", topic: str = "", analysis_type: str = "") -> dict:
    """Search Qdrant collection.

    Supports vector search (with query_vector) and/or payload filtering.

    Args:
        query_vector: 1024-dim query vector (optional, for semantic search)
        query_text: Text query for payload full-text match (optional)
        max_results: Maximum results to return
        pipeline_id: Filter by pipeline_id
        topic: Filter by topic
        analysis_type: Filter by analysis_type

    Returns:
        Dict with 'results' list and 'total_hits' count
    """
    if not QDRANT_ENDPOINT:
        return {"results": [], "total_hits": 0, "query": query_text}

    # Build filter
    must_conditions = []
    if pipeline_id:
        must_conditions.append({"key": "pipeline_id", "match": {"value": pipeline_id}})
    if topic:
        must_conditions.append({"key": "topic", "match": {"value": topic}})
    if analysis_type:
        must_conditions.append({"key": "analysis_type", "match": {"value": analysis_type}})

    if query_vector:
        # Vector similarity search
        search_body = {
            "vector": query_vector,
            "limit": max_results,
            "with_payload": True,
        }
        if must_conditions:
            search_body["filter"] = {"must": must_conditions}

        body = json.dumps(search_body).encode()
        url = f"{QDRANT_ENDPOINT}/collections/{QDRANT_COLLECTION}/points/search"
        req = _make_request(url, body, "POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                points = data.get("result", [])
                results = [_point_to_result(p) for p in points]
                return {"results": results, "total_hits": len(results), "query": query_text}
        except Exception as e:
            logger.error(json.dumps({"event": "qdrant_search_error", "error": str(e)}))
            return {"results": [], "total_hits": 0, "query": query_text, "error": str(e)}

    else:
        # Scroll with filter (text match or filter-only)
        filter_body = {}
        if query_text:
            # Full-text search on payload fields
            should_conditions = [
                {"key": "module_name", "match": {"text": query_text}},
                {"key": "parsed_summary", "match": {"text": query_text}},
                {"key": "claim_text", "match": {"text": query_text}},
                {"key": "hdd_content", "match": {"text": query_text}},
                {"key": "port_list", "match": {"text": query_text}},
                {"key": "instance_list", "match": {"text": query_text}},
                {"key": "src", "match": {"text": query_text}},
                {"key": "dst", "match": {"text": query_text}},
                {"key": "edge_type", "match": {"text": query_text}},
                {"key": "category", "match": {"text": query_text}},
                {"key": "raw_text", "match": {"text": query_text}},
            ]
            if must_conditions:
                filter_body = {"must": must_conditions, "should": should_conditions}
            else:
                filter_body = {"should": should_conditions}
        elif must_conditions:
            filter_body = {"must": must_conditions}
        else:
            return {"results": [], "total_hits": 0, "query": query_text}

        body = json.dumps({
            "filter": filter_body,
            "limit": max_results,
            "with_payload": True,
            "with_vector": False,
        }).encode()

        url = f"{QDRANT_ENDPOINT}/collections/{QDRANT_COLLECTION}/points/scroll"
        req = _make_request(url, body, "POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                points = data.get("result", {}).get("points", [])
                results = [_point_to_result(p) for p in points]
                return {"results": results, "total_hits": len(results), "query": query_text}
        except Exception as e:
            logger.error(json.dumps({"event": "qdrant_search_error", "error": str(e)}))
            return {"results": [], "total_hits": 0, "query": query_text, "error": str(e)}


def _point_to_result(point: dict) -> dict:
    """Convert Qdrant point to result dict matching OpenSearch format."""
    payload = point.get("payload", {})
    return {
        "module_name": payload.get("module_name", ""),
        "port_list": payload.get("port_list", ""),
        "parameter_list": payload.get("parameter_list", ""),
        "instance_list": payload.get("instance_list", ""),
        "file_path": payload.get("file_path", ""),
        "parsed_summary": payload.get("parsed_summary", ""),
        "pipeline_id": payload.get("pipeline_id", ""),
        "topic": payload.get("topic", ""),
        "analysis_type": payload.get("analysis_type", ""),
        "claim_text": payload.get("claim_text", ""),
        "claim_type": payload.get("claim_type", ""),
        "claim_id": payload.get("claim_id", ""),
        "hdd_content": payload.get("hdd_content", ""),
        "hdd_section_title": payload.get("hdd_section_title", ""),
        "parent_module_name": payload.get("parent_module_name", ""),
        "sub_record_type": payload.get("sub_record_type", ""),
        "edge_type": payload.get("edge_type", ""),
        "src": payload.get("src", ""),
        "dst": payload.get("dst", ""),
        "category": payload.get("category", ""),
        "raw_text": payload.get("raw_text", ""),
        "score": point.get("score", 0),
    }


def _to_text(value) -> str:
    """Convert list or string to text for payload storage."""
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value) if value else ""


def batch_index_documents(items: list) -> int:
    """Batch index multiple documents to Qdrant in a single API call.

    Args:
        items: List of (metadata_dict, embedding_list) tuples

    Returns:
        Number of successfully indexed items
    """
    if not QDRANT_ENDPOINT or not items:
        return 0

    points = []
    for metadata, embedding in items:
        if not embedding:
            continue
        doc_id = hashlib.sha256(
            (metadata.get("file_path", "") + metadata.get("claim_id", "") +
             metadata.get("edge_id", "")).encode()
        ).hexdigest()[:16]
        point_id = int(doc_id, 16) % (2**63)

        payload = {
            "module_name": metadata.get("module_name", ""),
            "parent_module": metadata.get("parent_module", ""),
            "port_list": _to_text(metadata.get("port_list", "")),
            "parameter_list": _to_text(metadata.get("parameter_list", "")),
            "instance_list": _to_text(metadata.get("instance_list", "")),
            "file_path": metadata.get("file_path", ""),
            "parsed_summary": metadata.get("parsed_summary", ""),
            "pipeline_id": metadata.get("pipeline_id", ""),
            "analysis_type": metadata.get("analysis_type", "module_parse"),
            "claim_text": metadata.get("claim_text", ""),
            "claim_type": metadata.get("claim_type", ""),
            "claim_id": metadata.get("claim_id", ""),
            "topic": metadata.get("topic", ""),
            "hdd_content": metadata.get("hdd_content", ""),
            "hdd_section_title": metadata.get("hdd_section_title", ""),
            "parent_module_name": metadata.get("parent_module_name", ""),
            "sub_record_type": metadata.get("sub_record_type", ""),
            "edge_type": metadata.get("edge_type", ""),
            "src": metadata.get("src", ""),
            "dst": metadata.get("dst", ""),
            "category": metadata.get("category", ""),
            "raw_text": metadata.get("raw_text", ""),
            "parser_source": metadata.get("parser_source", ""),
        }
        points.append({"id": point_id, "vector": embedding, "payload": payload})

    if not points:
        return 0

    # Batch upsert (Qdrant accepts multiple points in one PUT)
    body = json.dumps({"points": points}).encode()
    url = f"{QDRANT_ENDPOINT}/collections/{QDRANT_COLLECTION}/points?wait=false"
    req = _make_request(url, body, "PUT")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status in (200, 201):
                logger.info(json.dumps({
                    "event": "qdrant_batch_indexed",
                    "count": len(points),
                }))
                return len(points)
            else:
                logger.error(json.dumps({"event": "qdrant_batch_error", "status": resp.status}))
                return 0
    except Exception as e:
        logger.error(json.dumps({"event": "qdrant_batch_error", "error": str(e)}))
        return 0
