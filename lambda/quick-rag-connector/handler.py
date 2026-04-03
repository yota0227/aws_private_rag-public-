"""
QuickSight RAG Connector Lambda

QuickSight SPICE 새로고침 시 RAG API를 호출하여 데이터를 가져옵니다.
S3 캐싱(TTL 1시간)으로 Lambda 호출 횟수를 최소화합니다.

환경 변수:
  RAG_API_ENDPOINT  - RAG API Gateway 엔드포인트 (예: https://rag.corp.bos-semi.com)
  CACHE_BUCKET      - S3 캐시 버킷명
  CACHE_TTL_SECONDS - 캐시 유효 시간 (기본 3600초)
  LOG_LEVEL         - 로그 레벨 (기본 INFO)
"""

import hashlib
import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

RAG_API_ENDPOINT = os.environ.get("RAG_API_ENDPOINT", "https://rag.corp.bos-semi.com")
CACHE_BUCKET = os.environ.get("CACHE_BUCKET", "")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "3600"))

s3 = boto3.client("s3", region_name="ap-northeast-2")
cloudwatch = boto3.client("cloudwatch", region_name="ap-northeast-2")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """QuickSight SPICE 새로고침 요청 처리."""
    logger.info(f"Event: {json.dumps(event)}")
    query_pattern = event.get("query_pattern", "rag_usage_stats")

    try:
        data = get_data_with_cache(query_pattern)
        return {"statusCode": 200, "data": data, "count": len(data)}
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        _publish_metric("ConnectorError", 1)
        return {"statusCode": 500, "data": [], "error": str(e)}


# ──────────────────────────────────────────────
# 캐시 로직 (S3)
# ──────────────────────────────────────────────

def get_data_with_cache(query_pattern: str) -> List[Dict[str, Any]]:
    """S3 캐시 확인 후 히트 시 반환, 미스 시 RAG API 호출."""
    cache_key = _cache_key(query_pattern)

    cached = _read_cache(cache_key)
    if cached is not None:
        logger.info(f"Cache hit: {cache_key}")
        _publish_metric("CacheHit", 1)
        return cached

    logger.info(f"Cache miss: {cache_key}")
    _publish_metric("CacheMiss", 1)
    data = _fetch_from_rag_api(query_pattern)
    _write_cache(cache_key, data)
    return data


def _cache_key(query_pattern: str) -> str:
    h = hashlib.md5(query_pattern.encode()).hexdigest()
    return f"cache/{h}/data.json"


def _read_cache(key: str) -> Optional[List[Dict[str, Any]]]:
    """TTL 내 캐시 데이터 반환. 만료 또는 없으면 None."""
    if not CACHE_BUCKET:
        return None
    try:
        resp = s3.get_object(Bucket=CACHE_BUCKET, Key=key)
        payload = json.loads(resp["Body"].read())
        if time.time() - payload.get("cached_at", 0) > CACHE_TTL_SECONDS:
            logger.info("Cache expired")
            return None
        return payload.get("data", [])
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return None
        logger.warning(f"Cache read error (ignored): {e}")
        return None


def _write_cache(key: str, data: List[Dict[str, Any]]) -> None:
    """S3에 캐시 저장. 실패해도 Lambda는 계속 진행."""
    if not CACHE_BUCKET:
        return
    try:
        payload = {"cached_at": time.time(), "ttl_seconds": CACHE_TTL_SECONDS, "data": data}
        s3.put_object(
            Bucket=CACHE_BUCKET,
            Key=key,
            Body=json.dumps(payload),
            ContentType="application/json",
        )
        logger.info(f"Cache written: {key}")
    except ClientError as e:
        logger.warning(f"Cache write error (ignored): {e}")


# ──────────────────────────────────────────────
# RAG API 호출
# ──────────────────────────────────────────────

def _fetch_from_rag_api(query_pattern: str) -> List[Dict[str, Any]]:
    """RAG API 호출 후 QuickSight JSON 배열 형식으로 변환. 최대 3회 지수 백오프 재시도."""
    url = f"{RAG_API_ENDPOINT}/dev/rag/stats"
    max_retries = 3

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({"query_pattern": query_pattern}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=55) as resp:
                body = json.loads(resp.read())
                data = _transform_response(body, query_pattern)
                _publish_metric("RAGAPISuccess", 1)
                return data

        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            logger.error(f"RAG API error (attempt {attempt+1}): {e}")
            if attempt == max_retries - 1:
                _publish_metric("RAGAPIError", 1)
                raise
            time.sleep(2 ** attempt)

    return []


def _transform_response(body: Dict[str, Any], query_pattern: str) -> List[Dict[str, Any]]:
    """
    RAG API 응답을 QuickSight SPICE JSON 배열로 변환.
    필드: query_id, query_text, response_time_ms, citation_count, search_type, timestamp
    """
    items = body.get("items", body.get("data", []))
    return [
        {
            "query_id":         str(item.get("query_id", "")),
            "query_text":       str(item.get("query_text", "")),
            "response_time_ms": int(item.get("response_time_ms", 0)),
            "citation_count":   int(item.get("citation_count", 0)),
            "search_type":      str(item.get("search_type", "semantic")),
            "timestamp":        str(item.get("timestamp", "")),
            "query_pattern":    query_pattern,
        }
        for item in items
    ]


def _publish_metric(name: str, value: float) -> None:
    try:
        cloudwatch.put_metric_data(
            Namespace="QuickSight/RAGConnector",
            MetricData=[{"MetricName": name, "Value": value, "Unit": "Count"}],
        )
    except Exception as e:
        logger.warning(f"Metric publish failed (ignored): {e}")
