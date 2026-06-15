"""Qdrant REST API client for RTL knowledge base.

Provides index and search operations compatible with the existing
OpenSearch-based pipeline. Uses urllib (no external dependencies).
"""
import hashlib
import json
import logging
import os
import time
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

QDRANT_ENDPOINT = os.environ.get("QDRANT_ENDPOINT", "")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "rtl-knowledge-base")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", "")

SCROLL_PAGE_SIZE = 100  # scroll 페이지당 문서 수 (analysis_handler 마이그레이션용)


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
        "used_in_n1": bool(metadata.get("used_in_n1", False)),
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


def scroll_query(pipeline_id: str = "", analysis_type: str = "",
                 max_docs: int = 10000, extra_must: list = None) -> list:
    """Scroll documents by payload filter (pipeline_id + analysis_type).

    OpenSearch `_opensearch_scroll_query`의 Qdrant 등가물.
    pipeline_id/analysis_type 필터로 페이지네이션 조회하여 payload dict 리스트를 반환한다.
    각 dict에는 Qdrant point id가 ``_id`` 키로 포함된다 (downstream set_payload 호환).

    Args:
        pipeline_id: pipeline_id 필터 (빈 문자열이면 미적용)
        analysis_type: analysis_type 필터 (빈 문자열이면 미적용)
        max_docs: 최대 반환 문서 수
        extra_must: 추가 must 조건 리스트 (호출부에서 구성)

    Returns:
        payload dict 리스트 (각 dict에 ``_id`` 포함)
    """
    if not QDRANT_ENDPOINT:
        logger.warning("QDRANT_ENDPOINT not set, returning empty results")
        return []

    must_conditions = []
    if pipeline_id:
        must_conditions.append({"key": "pipeline_id", "match": {"value": pipeline_id}})
    if analysis_type:
        must_conditions.append({"key": "analysis_type", "match": {"value": analysis_type}})
    if extra_must:
        must_conditions.extend(extra_must)

    results: list = []
    next_offset = None
    url = f"{QDRANT_ENDPOINT}/collections/{QDRANT_COLLECTION}/points/scroll"

    while len(results) < max_docs:
        page_limit = min(SCROLL_PAGE_SIZE, max_docs - len(results))
        scroll_body = {
            "limit": page_limit,
            "with_payload": True,
            "with_vector": False,
        }
        if must_conditions:
            scroll_body["filter"] = {"must": must_conditions}
        if next_offset is not None:
            scroll_body["offset"] = next_offset

        body = json.dumps(scroll_body).encode()
        req = _make_request(url, body, "POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            logger.error(json.dumps({
                "event": "qdrant_scroll_error",
                "pipeline_id": pipeline_id,
                "analysis_type": analysis_type,
                "error": str(e),
            }))
            break

        result = data.get("result", {})
        points = result.get("points", [])
        if not points:
            break

        for p in points:
            payload = dict(p.get("payload", {}))
            payload["_id"] = p.get("id")
            results.append(payload)

        next_offset = result.get("next_page_offset")
        if next_offset is None:
            break

    return results


def set_payload(point_id, fields: dict) -> bool:
    """단일 point의 payload 필드를 업데이트.

    OpenSearch `_update_document`의 Qdrant 등가물.
    """
    if not QDRANT_ENDPOINT or point_id is None:
        return False

    body = json.dumps({
        "payload": fields,
        "points": [point_id],
    }).encode()
    url = f"{QDRANT_ENDPOINT}/collections/{QDRANT_COLLECTION}/points/payload?wait=true"
    req = _make_request(url, body, "POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status in (200, 201, 202):
                return True
            logger.error(json.dumps({"event": "qdrant_set_payload_error", "status": resp.status}))
            return False
    except Exception as e:
        logger.error(json.dumps({"event": "qdrant_set_payload_error", "error": str(e)}))
        return False


def delete_by_filter(pipeline_id: str = "", analysis_type: str = "",
                     extra_must: list = None) -> bool:
    """payload 필터에 매칭되는 point들을 삭제 (clear_index 용).

    OpenSearch _delete_by_query / 인덱스 삭제의 Qdrant 등가물.
    pipeline_id/analysis_type 중 지정된 것으로 must 필터를 구성한다.

    안전장치: 아무 필터 조건도 없으면 (전체 컬렉션 삭제 위험) 거부하고 False 반환.
    """
    if not QDRANT_ENDPOINT:
        logger.warning("QDRANT_ENDPOINT not set, skipping delete")
        return False

    must_conditions = []
    if pipeline_id:
        must_conditions.append({"key": "pipeline_id", "match": {"value": pipeline_id}})
    if analysis_type:
        must_conditions.append({"key": "analysis_type", "match": {"value": analysis_type}})
    if extra_must:
        must_conditions.extend(extra_must)

    if not must_conditions:
        # 필터 없는 delete는 컬렉션 전체 삭제 → 사고 방지를 위해 거부
        logger.error(json.dumps({"event": "qdrant_delete_refused_no_filter"}))
        return False

    body = json.dumps({"filter": {"must": must_conditions}}).encode()
    url = f"{QDRANT_ENDPOINT}/collections/{QDRANT_COLLECTION}/points/delete?wait=true"
    req = _make_request(url, body, "POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status in (200, 201, 202):
                logger.info(json.dumps({
                    "event": "qdrant_delete_by_filter",
                    "pipeline_id": pipeline_id,
                    "analysis_type": analysis_type,
                }))
                return True
            logger.error(json.dumps({"event": "qdrant_delete_error", "status": resp.status}))
            return False
    except Exception as e:
        logger.error(json.dumps({"event": "qdrant_delete_error", "error": str(e)}))
        return False


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
        "used_in_n1": bool(payload.get("used_in_n1", False)),
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
            "used_in_n1": bool(metadata.get("used_in_n1", False)),
        }
        points.append({"id": point_id, "vector": embedding, "payload": payload})

    if not points:
        return 0

    # Batch upsert (Qdrant accepts multiple points in one PUT)
    body = json.dumps({"points": points}).encode()
    url = f"{QDRANT_ENDPOINT}/collections/{QDRANT_COLLECTION}/points?wait=false"

    # broken pipe 등 일시적 연결 오류에 대비한 재시도 (최대 3회).
    # 매 시도마다 새 Request 생성 (urllib Request는 재사용 시 body 소비 문제 발생).
    last_error = None
    for attempt in range(3):
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
        except urllib.error.HTTPError as he:
            # HTTP 4xx/5xx는 재시도해도 동일하므로 즉시 실패 (401 등)
            logger.error(json.dumps({"event": "qdrant_batch_error", "status": he.code, "error": str(he)}))
            return 0
        except Exception as e:
            # broken pipe, timeout, connection reset 등 일시적 오류 → 재시도
            last_error = str(e)
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
                continue

    logger.error(json.dumps({"event": "qdrant_batch_error", "error": last_error, "retries_exhausted": True}))
    return 0
