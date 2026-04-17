"""
Analysis pipeline handler for RTL auto-analysis.

Invoked by Step Functions with a ``stage`` parameter to dispatch
the appropriate analysis function. Each stage reads from OpenSearch/S3,
runs analysis logic, writes results back, and updates DynamoDB status.

Requirements validated: 1.2, 1.3, 1.4, 2.1–2.5, 3.1–3.5, 4.1–4.5, 5.1–5.5, 11.7
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

from hierarchy import build_hierarchy, serialize_hierarchy_json, serialize_hierarchy_csv
from clock_domain import extract_clock_domains, classify_clock_domain, detect_cdc_boundary
from dataflow import build_dataflow_connections
from topic_classifier import classify_topic, suggest_inherited_topic
from claim_generator import generate_claims
from hdd_generator import generate_hdd_section
from variant_delta import extract_variant_delta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# 환경 변수
# ---------------------------------------------------------------------------
RTL_S3_BUCKET = os.environ.get("RTL_S3_BUCKET", "")
OPENSEARCH_ENDPOINT = os.environ.get("RTL_OPENSEARCH_ENDPOINT", "")
OPENSEARCH_INDEX = os.environ.get("RTL_OPENSEARCH_INDEX", "rtl-knowledge-base-index")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
DYNAMODB_EXTRACTION_TABLE = os.environ.get("DYNAMODB_EXTRACTION_TABLE", "rag-extraction-tasks")

s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

BATCH_SIZE = 100


# ---------------------------------------------------------------------------
# 공통 유틸리티
# ---------------------------------------------------------------------------

def _get_opensearch_auth():
    """OpenSearch AOSS SigV4 인증 객체 생성."""
    import requests
    from requests_aws4auth import AWS4Auth

    session = boto3.Session()
    credentials = session.get_credentials()
    aoss_region = BEDROCK_REGION
    auth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        aoss_region,
        "aoss",
        session_token=credentials.token,
    )
    return auth


def _opensearch_scroll_query(
    pipeline_id: str, analysis_type: str, max_docs: int = 10000,
) -> list[dict]:
    """OpenSearch에서 pipeline_id + analysis_type으로 문서를 페이지네이션 조회.

    AOSS는 scroll API를 지원하지 않으므로 search_after 방식으로 페이지네이션한다.
    _id 기준 정렬 후 마지막 _id를 search_after로 전달하여 다음 페이지를 조회한다.
    """
    import requests

    if not OPENSEARCH_ENDPOINT:
        logger.warning("OPENSEARCH_ENDPOINT not set, returning empty results")
        return []

    auth = _get_opensearch_auth()
    url = f"{OPENSEARCH_ENDPOINT}/{OPENSEARCH_INDEX}/_search"
    results: list[dict] = []
    search_after: list[str] | None = None

    while len(results) < max_docs:
        search_body: dict[str, Any] = {
            "size": BATCH_SIZE,
            "sort": [{"_id": "asc"}],
            "query": {
                "bool": {
                    "must": [
                        {"term": {"pipeline_id": pipeline_id}},
                        {"term": {"analysis_type": analysis_type}},
                    ],
                },
            },
        }
        if search_after is not None:
            search_body["search_after"] = search_after

        try:
            resp = requests.post(
                url, auth=auth, json=search_body,
                headers={"Content-Type": "application/json"}, timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])

            if not hits:
                break

            for hit in hits:
                doc = hit.get("_source", {})
                doc["_id"] = hit.get("_id", "")
                results.append(doc)

            # search_after: 마지막 hit의 sort 값
            search_after = hits[-1].get("sort")
            if not search_after:
                break

            logger.info(json.dumps({
                "event": "scroll_page",
                "pipeline_id": pipeline_id,
                "analysis_type": analysis_type,
                "page_size": len(hits),
                "total_so_far": len(results),
            }))

            # 배치 크기보다 적으면 마지막 페이지
            if len(hits) < BATCH_SIZE:
                break

        except Exception as e:
            logger.error(json.dumps({
                "event": "opensearch_scroll_error",
                "pipeline_id": pipeline_id,
                "error": str(e),
            }))
            break

    return results


def _index_document(doc: dict[str, Any]) -> bool:
    """단일 문서를 OpenSearch에 인덱싱."""
    import requests

    if not OPENSEARCH_ENDPOINT:
        return False

    auth = _get_opensearch_auth()
    url = f"{OPENSEARCH_ENDPOINT}/{OPENSEARCH_INDEX}/_doc"
    try:
        resp = requests.post(
            url, auth=auth, json=doc,
            headers={"Content-Type": "application/json"}, timeout=30,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(json.dumps({
            "event": "opensearch_index_error",
            "error": str(e),
        }))
        return False


def _update_document(doc_id: str, update_fields: dict[str, Any]) -> bool:
    """OpenSearch 문서의 특정 필드를 업데이트."""
    import requests

    if not OPENSEARCH_ENDPOINT:
        return False

    auth = _get_opensearch_auth()
    url = f"{OPENSEARCH_ENDPOINT}/{OPENSEARCH_INDEX}/_doc/{doc_id}"
    try:
        resp = requests.post(
            url, auth=auth, json={"doc": update_fields},
            headers={"Content-Type": "application/json"}, timeout=30,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(json.dumps({
            "event": "opensearch_update_error",
            "doc_id": doc_id,
            "error": str(e),
        }))
        return False


def _update_dynamodb_status(
    pipeline_id: str, stage: str, status: str,
    error_message: str | None = None,
    extra: dict[str, Any] | None = None,
):
    """DynamoDB rag-extraction-tasks 테이블에 분석 상태 업데이트."""
    try:
        table = dynamodb.Table(DYNAMODB_EXTRACTION_TABLE)
        item: dict[str, Any] = {
            "task_id": f"analysis_{pipeline_id}_{stage}",
            "pipeline_id": pipeline_id,
            "stage": stage,
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if status == "in_progress":
            item["started_at"] = datetime.now(timezone.utc).isoformat()
        if error_message:
            item["error_message"] = error_message
        if extra:
            item.update(extra)
        table.put_item(Item=item)
    except Exception as e:
        logger.error(json.dumps({
            "event": "dynamodb_status_update_error",
            "pipeline_id": pipeline_id,
            "stage": stage,
            "error": str(e),
        }))


# ---------------------------------------------------------------------------
# Task 5.2: Hierarchy Extraction
# ---------------------------------------------------------------------------

def handle_hierarchy_extraction(event: dict[str, Any]) -> dict[str, Any]:
    """계층 트리 추출 핸들러.

    1. OpenSearch에서 pipeline_id의 모든 module_parse 문서 조회
    2. build_hierarchy() 호출
    3. JSON/CSV를 S3에 저장
    4. 계층 노드를 OpenSearch에 analysis_type=hierarchy로 인덱싱
    5. DynamoDB 상태 업데이트
    """
    pipeline_id = event["pipeline_id"]
    stage = "hierarchy_extraction"
    _update_dynamodb_status(pipeline_id, stage, "in_progress")

    try:
        # 1. OpenSearch에서 파싱된 모듈 조회
        parsed_docs = _opensearch_scroll_query(pipeline_id, "module_parse")
        if not parsed_docs:
            _update_dynamodb_status(pipeline_id, stage, "completed",
                                   extra={"modules_processed": 0})
            return {"status": "completed", "modules_processed": 0}

        # 모듈 데이터를 build_hierarchy 입력 형식으로 변환
        modules = []
        for doc in parsed_docs:
            modules.append({
                "module_name": doc.get("module_name", ""),
                "instance_list": doc.get("instance_list", ""),
                "port_list": doc.get("port_list", ""),
                "parameter_list": doc.get("parameter_list", ""),
                "file_path": doc.get("file_path", ""),
            })

        # 2. 계층 트리 구축
        tree = build_hierarchy(modules)

        # 3. S3에 JSON/CSV 저장
        if RTL_S3_BUCKET:
            json_key = f"rtl-parsed/hierarchy/{pipeline_id}/hierarchy_tree.json"
            csv_key = f"rtl-parsed/hierarchy/{pipeline_id}/hierarchy_tree.csv"
            s3_client.put_object(
                Bucket=RTL_S3_BUCKET, Key=json_key,
                Body=serialize_hierarchy_json(tree).encode("utf-8"),
                ContentType="application/json",
            )
            s3_client.put_object(
                Bucket=RTL_S3_BUCKET, Key=csv_key,
                Body=serialize_hierarchy_csv(tree).encode("utf-8"),
                ContentType="text/csv",
            )

        # 4. 계층 노드를 OpenSearch에 인덱싱
        indexed_count = 0

        def _index_nodes(nodes: list[dict], depth: int = 0):
            nonlocal indexed_count
            for node in nodes:
                doc = {
                    "pipeline_id": pipeline_id,
                    "analysis_type": "hierarchy",
                    "module_name": node.get("module_name", ""),
                    "instance_name": node.get("instance_name", ""),
                    "hierarchy_path": node.get("hierarchy_path", ""),
                    "hierarchy_depth": depth,
                    "clock_signals": node.get("clock_signals", []),
                    "reset_signals": node.get("reset_signals", []),
                    "memory_instances": node.get("memory_instances", []),
                    "children_modules": [
                        c.get("module_name", "") for c in node.get("children", [])
                    ],
                }
                _index_document(doc)
                indexed_count += 1
                _index_nodes(node.get("children", []), depth + 1)

        _index_nodes(tree)

        # 5. DynamoDB 상태 업데이트
        _update_dynamodb_status(pipeline_id, stage, "completed",
                               extra={"modules_processed": indexed_count})

        logger.info(json.dumps({
            "event": "hierarchy_extraction_complete",
            "pipeline_id": pipeline_id,
            "modules_processed": indexed_count,
        }))
        return {"status": "completed", "modules_processed": indexed_count}

    except Exception as e:
        _update_dynamodb_status(pipeline_id, stage, "failed",
                               error_message=str(e))
        logger.error(json.dumps({
            "event": "hierarchy_extraction_error",
            "pipeline_id": pipeline_id,
            "error": str(e),
        }))
        raise


# ---------------------------------------------------------------------------
# Task 5.3: Clock Domain Analysis
# ---------------------------------------------------------------------------

def handle_clock_domain_analysis(event: dict[str, Any]) -> dict[str, Any]:
    """클럭 도메인 분석 핸들러.

    1. S3에서 RTL 소스 파일을 배치로 읽기
    2. extract_clock_domains() + classify_clock_domain() + detect_cdc_boundary()
    3. OpenSearch에 analysis_type=clock_domain 문서로 인덱싱
    4. DynamoDB 상태 업데이트
    """
    pipeline_id = event["pipeline_id"]
    stage = "clock_domain_analysis"
    _update_dynamodb_status(pipeline_id, stage, "in_progress")

    try:
        s3_prefix = event.get("s3_prefix", f"rtl-sources/{pipeline_id}/")
        files_processed = 0
        cdc_modules = 0

        # S3에서 RTL 파일 목록 조회 (배치 처리)
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=RTL_S3_BUCKET, Prefix=s3_prefix)

        batch: list[dict[str, str]] = []
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith((".v", ".sv", ".svh")):
                    batch.append({"key": key})

                    if len(batch) >= BATCH_SIZE:
                        processed, cdc = _process_clock_batch(
                            pipeline_id, batch,
                        )
                        files_processed += processed
                        cdc_modules += cdc
                        batch = []

        # 남은 배치 처리
        if batch:
            processed, cdc = _process_clock_batch(pipeline_id, batch)
            files_processed += processed
            cdc_modules += cdc

        _update_dynamodb_status(pipeline_id, stage, "completed",
                               extra={"modules_processed": files_processed,
                                      "cdc_modules": cdc_modules})

        logger.info(json.dumps({
            "event": "clock_domain_analysis_complete",
            "pipeline_id": pipeline_id,
            "files_processed": files_processed,
            "cdc_modules": cdc_modules,
        }))
        return {"status": "completed", "files_processed": files_processed,
                "cdc_modules": cdc_modules}

    except Exception as e:
        _update_dynamodb_status(pipeline_id, stage, "failed",
                               error_message=str(e))
        logger.error(json.dumps({
            "event": "clock_domain_analysis_error",
            "pipeline_id": pipeline_id,
            "error": str(e),
        }))
        raise


def _process_clock_batch(
    pipeline_id: str, batch: list[dict[str, str]],
) -> tuple[int, int]:
    """클럭 도메인 분석 배치 처리."""
    processed = 0
    cdc_count = 0

    for item in batch:
        key = item["key"]
        try:
            resp = s3_client.get_object(Bucket=RTL_S3_BUCKET, Key=key)
            content = resp["Body"].read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(json.dumps({
                "event": "clock_s3_read_error", "key": key, "error": str(e),
            }))
            continue

        clocks = extract_clock_domains(content)
        if not clocks:
            processed += 1
            continue

        # 각 클럭 신호를 도메인으로 분류
        domain_entries: list[dict[str, Any]] = []
        domain_set: dict[str, list[str]] = {}
        for clk in clocks:
            domain = classify_clock_domain(clk)
            domain_set.setdefault(domain, []).append(clk)

        for domain, signals in domain_set.items():
            domain_entries.append({"domain": domain, "signals": signals})

        cdc_result = detect_cdc_boundary(domain_entries)

        # 파일명에서 모듈명 추정
        module_name = key.rsplit("/", 1)[-1].rsplit(".", 1)[0]

        doc = {
            "pipeline_id": pipeline_id,
            "analysis_type": "clock_domain",
            "module_name": module_name,
            "file_path": key,
            "clock_domains": domain_entries,
            "is_cdc_boundary": cdc_result["is_cdc_boundary"],
            "cdc_pairs": cdc_result["cdc_pairs"],
        }
        _index_document(doc)
        processed += 1
        if cdc_result["is_cdc_boundary"]:
            cdc_count += 1

    return processed, cdc_count


# ---------------------------------------------------------------------------
# Task 5.4: Dataflow Tracking
# ---------------------------------------------------------------------------

def handle_dataflow_tracking(event: dict[str, Any]) -> dict[str, Any]:
    """데이터 흐름 추적 핸들러.

    1. S3에서 RTL 소스 파일을 배치로 읽기
    2. build_dataflow_connections() 호출
    3. OpenSearch에 analysis_type=dataflow 문서로 인덱싱
    4. DynamoDB 상태 업데이트
    """
    pipeline_id = event["pipeline_id"]
    stage = "dataflow_tracking"
    _update_dynamodb_status(pipeline_id, stage, "in_progress")

    try:
        s3_prefix = event.get("s3_prefix", f"rtl-sources/{pipeline_id}/")
        files_processed = 0
        total_connections = 0

        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=RTL_S3_BUCKET, Prefix=s3_prefix)

        batch: list[dict[str, str]] = []
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith((".v", ".sv", ".svh")):
                    batch.append({"key": key})

                    if len(batch) >= BATCH_SIZE:
                        processed, conns = _process_dataflow_batch(
                            pipeline_id, batch,
                        )
                        files_processed += processed
                        total_connections += conns
                        batch = []

        if batch:
            processed, conns = _process_dataflow_batch(pipeline_id, batch)
            files_processed += processed
            total_connections += conns

        _update_dynamodb_status(pipeline_id, stage, "completed",
                               extra={"modules_processed": files_processed,
                                      "total_connections": total_connections})

        logger.info(json.dumps({
            "event": "dataflow_tracking_complete",
            "pipeline_id": pipeline_id,
            "files_processed": files_processed,
            "total_connections": total_connections,
        }))
        return {"status": "completed", "files_processed": files_processed,
                "total_connections": total_connections}

    except Exception as e:
        _update_dynamodb_status(pipeline_id, stage, "failed",
                               error_message=str(e))
        logger.error(json.dumps({
            "event": "dataflow_tracking_error",
            "pipeline_id": pipeline_id,
            "error": str(e),
        }))
        raise


def _process_dataflow_batch(
    pipeline_id: str, batch: list[dict[str, str]],
) -> tuple[int, int]:
    """데이터 흐름 분석 배치 처리."""
    processed = 0
    conn_count = 0

    for item in batch:
        key = item["key"]
        try:
            resp = s3_client.get_object(Bucket=RTL_S3_BUCKET, Key=key)
            content = resp["Body"].read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(json.dumps({
                "event": "dataflow_s3_read_error", "key": key, "error": str(e),
            }))
            continue

        connections = build_dataflow_connections(content)
        if not connections:
            processed += 1
            continue

        module_name = key.rsplit("/", 1)[-1].rsplit(".", 1)[0]

        doc = {
            "pipeline_id": pipeline_id,
            "analysis_type": "dataflow",
            "module_name": module_name,
            "file_path": key,
            "dataflow_connections": connections,
        }
        _index_document(doc)
        processed += 1
        conn_count += len(connections)

    return processed, conn_count


# ---------------------------------------------------------------------------
# Task 5.5: Topic Classification
# ---------------------------------------------------------------------------

def handle_topic_classification(event: dict[str, Any]) -> dict[str, Any]:
    """토픽 분류 핸들러.

    1. OpenSearch에서 pipeline_id의 모든 module_parse 문서 조회
    2. classify_topic() 호출
    3. OpenSearch 문서에 topic 필드 업데이트
    4. DynamoDB 상태 업데이트
    """
    pipeline_id = event["pipeline_id"]
    stage = "topic_classification"
    _update_dynamodb_status(pipeline_id, stage, "in_progress")

    try:
        parsed_docs = _opensearch_scroll_query(pipeline_id, "module_parse")
        if not parsed_docs:
            _update_dynamodb_status(pipeline_id, stage, "completed",
                                   extra={"modules_processed": 0})
            return {"status": "completed", "modules_processed": 0}

        classified_count = 0
        unclassified_count = 0

        for doc in parsed_docs:
            module_name = doc.get("module_name", "")
            file_path = doc.get("file_path", "")
            doc_id = doc.get("_id", "")

            topics = classify_topic(file_path, module_name)

            # OpenSearch 문서에 topic 필드 추가 (기존 문서 업데이트)
            if doc_id:
                _update_document(doc_id, {"topic": topics, "topics": topics})

            # 별도 analysis_type=topic 문서도 인덱싱
            topic_doc = {
                "pipeline_id": pipeline_id,
                "analysis_type": "topic",
                "module_name": module_name,
                "file_path": file_path,
                "topic": topics,
                "topics": topics,
            }
            _index_document(topic_doc)

            classified_count += 1
            if topics == ["unclassified"]:
                unclassified_count += 1

        _update_dynamodb_status(pipeline_id, stage, "completed",
                               extra={"modules_processed": classified_count,
                                      "unclassified_count": unclassified_count})

        logger.info(json.dumps({
            "event": "topic_classification_complete",
            "pipeline_id": pipeline_id,
            "classified": classified_count,
            "unclassified": unclassified_count,
        }))
        return {"status": "completed", "classified": classified_count,
                "unclassified": unclassified_count}

    except Exception as e:
        _update_dynamodb_status(pipeline_id, stage, "failed",
                               error_message=str(e))
        logger.error(json.dumps({
            "event": "topic_classification_error",
            "pipeline_id": pipeline_id,
            "error": str(e),
        }))
        raise


# ---------------------------------------------------------------------------
# Task 7.4: Claim Generation
# ---------------------------------------------------------------------------

def handle_claim_generation(event: dict[str, Any]) -> dict[str, Any]:
    """Claim 생성 핸들러.

    module_parse 문서에서 직접 classify_topic()을 호출하여 토픽별로 그룹화한 뒤
    generate_claims()로 Claim을 생성한다. topic 문서에 의존하지 않는다.

    event에 ``topic`` 파라미터가 있으면 해당 토픽만 처리한다.
    없으면 전체 토픽을 처리하되, 300초 타임아웃 내에서 가능한 만큼만.
    """
    pipeline_id = event["pipeline_id"]
    target_topic = event.get("topic", "")  # 단일 토픽 지정 시
    stage = "claim_generation"
    _update_dynamodb_status(pipeline_id, stage, "in_progress")

    try:
        parsed_docs = _opensearch_scroll_query(pipeline_id, "module_parse")

        # 분석 결과 수집 (hierarchy만 — 가볍게)
        hierarchy_docs = _opensearch_scroll_query(pipeline_id, "hierarchy", max_docs=100)
        analysis_results: dict[str, Any] = {
            "hierarchy": hierarchy_docs[0] if hierarchy_docs else {},
            "clock_domains": [],
            "dataflow": [],
        }

        # module_parse 문서에서 직접 토픽 분류 → 토픽별 그룹화
        topic_groups: dict[str, list[dict[str, Any]]] = {}
        for doc in parsed_docs:
            name = doc.get("module_name", "")
            file_path = doc.get("file_path", "")
            if not name:
                continue
            topics = classify_topic(file_path, name)
            for t in topics:
                if t != "unclassified":
                    topic_groups.setdefault(t, []).append(doc)

        logger.info(json.dumps({
            "event": "claim_topic_groups",
            "pipeline_id": pipeline_id,
            "target_topic": target_topic or "all",
            "topics": {t: len(mods) for t, mods in topic_groups.items()},
        }))

        # 단일 토픽 지정 시 해당 토픽만 처리
        if target_topic:
            topics_to_process = {target_topic: topic_groups.get(target_topic, [])}
        else:
            topics_to_process = topic_groups

        total_claims = 0
        for topic, modules in topics_to_process.items():
            if not modules:
                continue
            modules_subset = modules[:20]
            claims = generate_claims(pipeline_id, topic, modules_subset, analysis_results)

            for claim in claims:
                _index_document(claim)
                total_claims += 1

        _update_dynamodb_status(pipeline_id, stage, "completed",
                               extra={"claims_generated": total_claims})

        logger.info(json.dumps({
            "event": "claim_generation_complete",
            "pipeline_id": pipeline_id,
            "claims_generated": total_claims,
        }))
        return {"status": "completed", "claims_generated": total_claims}

    except Exception as e:
        _update_dynamodb_status(pipeline_id, stage, "failed",
                               error_message=str(e))
        logger.error(json.dumps({
            "event": "claim_generation_error",
            "pipeline_id": pipeline_id,
            "error": str(e),
        }))
        raise


# ---------------------------------------------------------------------------
# Task 7.4: HDD Generation
# ---------------------------------------------------------------------------

def handle_hdd_generation(event: dict[str, Any]) -> dict[str, Any]:
    """HDD 섹션 생성 핸들러.

    1. 분석 결과 수집 (hierarchy, clock_domains, dataflow, claims)
    2. generate_hdd_section() 호출
    3. S3에 Markdown 저장 + OpenSearch 인덱싱
    """
    pipeline_id = event["pipeline_id"]
    stage = "hdd_generation"
    _update_dynamodb_status(pipeline_id, stage, "in_progress")

    try:
        # 분석 결과 수집
        hierarchy_docs = _opensearch_scroll_query(pipeline_id, "hierarchy")
        clock_docs = _opensearch_scroll_query(pipeline_id, "clock_domain")
        dataflow_docs = _opensearch_scroll_query(pipeline_id, "dataflow")
        topic_docs = _opensearch_scroll_query(pipeline_id, "topic")

        # 토픽 목록 추출
        topics: set[str] = set()
        for doc in topic_docs:
            t_list = doc.get("topics", doc.get("topic", []))
            if isinstance(t_list, str):
                t_list = [t_list]
            for t in t_list:
                if t != "unclassified":
                    topics.add(t)

        hierarchy = hierarchy_docs[0] if hierarchy_docs else {}
        sections_generated = 0

        for topic in sorted(topics):
            claim_docs = [
                d for d in _opensearch_scroll_query(pipeline_id, "claim")
                if d.get("topic") == topic
            ]

            try:
                result = generate_hdd_section(
                    pipeline_id, topic, hierarchy,
                    clock_docs, dataflow_docs, claim_docs,
                )
            except RuntimeError as e:
                logger.error("HDD generation failed for topic=%s: %s", topic, e)
                continue

            # S3에 Markdown 저장
            if RTL_S3_BUCKET:
                s3_key = f"rtl-parsed/hdd/{pipeline_id}/{topic}_HDD.md"
                s3_client.put_object(
                    Bucket=RTL_S3_BUCKET, Key=s3_key,
                    Body=result["hdd_content"].encode("utf-8"),
                    ContentType="text/markdown",
                )

            # OpenSearch 인덱싱
            _index_document(result)
            sections_generated += 1

        _update_dynamodb_status(pipeline_id, stage, "completed",
                               extra={"sections_generated": sections_generated})

        logger.info(json.dumps({
            "event": "hdd_generation_complete",
            "pipeline_id": pipeline_id,
            "sections_generated": sections_generated,
        }))
        return {"status": "completed", "sections_generated": sections_generated}

    except Exception as e:
        _update_dynamodb_status(pipeline_id, stage, "failed",
                               error_message=str(e))
        logger.error(json.dumps({
            "event": "hdd_generation_error",
            "pipeline_id": pipeline_id,
            "error": str(e),
        }))
        raise


# ---------------------------------------------------------------------------
# Task 9.1: Variant Delta Analysis
# ---------------------------------------------------------------------------

def handle_variant_delta(event: dict[str, Any]) -> dict[str, Any]:
    """Variant delta 분석 핸들러.

    1. event에서 variant_baseline_id 파라미터 읽기
    2. 베이스라인과 variant의 module_parse 문서를 OpenSearch에서 조회
    3. extract_variant_delta() 호출
    4. 결과를 OpenSearch에 analysis_type=variant_delta 문서로 인덱싱
    """
    pipeline_id = event["pipeline_id"]
    variant_baseline_id = event.get("variant_baseline_id", "")
    stage = "variant_delta"
    _update_dynamodb_status(pipeline_id, stage, "in_progress")

    try:
        if not variant_baseline_id:
            _update_dynamodb_status(pipeline_id, stage, "completed",
                                   extra={"skipped": True,
                                          "reason": "no variant_baseline_id"})
            return {"status": "completed", "skipped": True}

        # 베이스라인과 variant 모듈 조회
        baseline_docs = _opensearch_scroll_query(variant_baseline_id, "module_parse")
        variant_docs = _opensearch_scroll_query(pipeline_id, "module_parse")

        delta = extract_variant_delta(baseline_docs, variant_docs)

        # OpenSearch에 인덱싱
        delta_doc: dict[str, Any] = {
            "pipeline_id": pipeline_id,
            "analysis_type": "variant_delta",
            "variant_baseline_id": variant_baseline_id,
            "added_modules": delta["added_modules"],
            "removed_modules": delta["removed_modules"],
            "parameter_changes": delta["parameter_changes"],
            "instance_changes": delta["instance_changes"],
        }
        _index_document(delta_doc)

        summary = {
            "added": len(delta["added_modules"]),
            "removed": len(delta["removed_modules"]),
            "param_changes": len(delta["parameter_changes"]),
            "instance_changes": len(delta["instance_changes"]),
        }

        _update_dynamodb_status(pipeline_id, stage, "completed", extra=summary)

        logger.info(json.dumps({
            "event": "variant_delta_complete",
            "pipeline_id": pipeline_id,
            "baseline_id": variant_baseline_id,
            **summary,
        }))
        return {"status": "completed", **summary}

    except Exception as e:
        _update_dynamodb_status(pipeline_id, stage, "failed",
                               error_message=str(e))
        logger.error(json.dumps({
            "event": "variant_delta_error",
            "pipeline_id": pipeline_id,
            "error": str(e),
        }))
        raise


# ---------------------------------------------------------------------------
# Backfill: 기존 문서에 pipeline_id, analysis_type 필드 추가
# ---------------------------------------------------------------------------

def handle_backfill_pipeline_id(event: dict[str, Any]) -> dict[str, Any]:
    """기존 OpenSearch 문서에 pipeline_id, analysis_type 필드를 백필.

    AOSS는 _update_by_query를 지원하지 않으므로:
    1. pipeline_id 필드가 없는 문서를 검색 (must_not exists)
    2. 각 문서에 pipeline_id, chip_type, snapshot_date, analysis_type 추가
    3. 새 문서로 다시 인덱싱 (POST /_doc)

    배치 처리: 100건씩

    Args:
        event: 백필 이벤트.
            필수: ``pipeline_id`` (str)
            선택: ``analysis_type`` (str, 기본값 "module_parse")

    Returns:
        백필 결과 dict.
    """
    import requests

    pipeline_id = event.get("pipeline_id", "tt_20260221")
    analysis_type = event.get("analysis_type", "module_parse")
    stage = "backfill_pipeline_id"
    _update_dynamodb_status(pipeline_id, stage, "in_progress")

    # pipeline_id에서 chip_type, snapshot_date 추출
    if "_" in pipeline_id:
        chip_type, snapshot_date = pipeline_id.split("_", 1)
    else:
        chip_type, snapshot_date = pipeline_id, "unknown"

    total_backfilled = 0
    total_failed = 0

    try:
        if not OPENSEARCH_ENDPOINT:
            logger.warning("OPENSEARCH_ENDPOINT not set, skipping backfill")
            _update_dynamodb_status(pipeline_id, stage, "completed",
                                   extra={"backfilled": 0, "skipped": True})
            return {"status": "completed", "backfilled": 0, "failed": 0,
                    "skipped": True}

        auth = _get_opensearch_auth()
        url = f"{OPENSEARCH_ENDPOINT}/{OPENSEARCH_INDEX}/_search"

        while True:
            # pipeline_id 필드가 없는 문서를 배치로 검색
            search_body: dict[str, Any] = {
                "size": BATCH_SIZE,
                "query": {
                    "bool": {
                        "must_not": [
                            {"exists": {"field": "pipeline_id"}},
                        ],
                    },
                },
            }

            resp = requests.post(
                url, auth=auth, json=search_body,
                headers={"Content-Type": "application/json"}, timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])

            if not hits:
                break

            for hit in hits:
                source = hit.get("_source", {})
                # 기존 문서에 새 필드 추가
                source["pipeline_id"] = pipeline_id
                source["chip_type"] = chip_type
                source["snapshot_date"] = snapshot_date
                source["analysis_type"] = analysis_type

                if _index_document(source):
                    total_backfilled += 1
                else:
                    total_failed += 1

            logger.info(json.dumps({
                "event": "backfill_batch_complete",
                "pipeline_id": pipeline_id,
                "batch_size": len(hits),
                "total_backfilled": total_backfilled,
            }))

        _update_dynamodb_status(pipeline_id, stage, "completed",
                               extra={"backfilled": total_backfilled,
                                      "failed": total_failed})

        logger.info(json.dumps({
            "event": "backfill_pipeline_id_complete",
            "pipeline_id": pipeline_id,
            "total_backfilled": total_backfilled,
            "total_failed": total_failed,
        }))
        return {"status": "completed", "backfilled": total_backfilled,
                "failed": total_failed}

    except Exception as e:
        _update_dynamodb_status(pipeline_id, stage, "failed",
                               error_message=str(e))
        logger.error(json.dumps({
            "event": "backfill_pipeline_id_error",
            "pipeline_id": pipeline_id,
            "error": str(e),
        }))
        raise


# ---------------------------------------------------------------------------
# Clear Index: OpenSearch 인덱스 삭제 후 재생성
# ---------------------------------------------------------------------------

def handle_clear_index(event: dict[str, Any]) -> dict[str, Any]:
    """OpenSearch 인덱스를 삭제하고 재생성.

    AOSS는 ``_delete_by_query``를 지원하지 않으므로,
    인덱스를 삭제(DELETE)한 뒤 동일 매핑으로 재생성(PUT)한다.

    Args:
        event: ``pipeline_id`` (str) 필수.

    Returns:
        ``{"status": "completed"}`` 또는 에러 시 raise.
    """
    import requests

    pipeline_id = event["pipeline_id"]
    stage = "clear_index"
    _update_dynamodb_status(pipeline_id, stage, "in_progress")

    try:
        if not OPENSEARCH_ENDPOINT:
            logger.warning("OPENSEARCH_ENDPOINT not set, skipping clear_index")
            _update_dynamodb_status(pipeline_id, stage, "completed",
                                   extra={"skipped": True})
            return {"status": "completed", "skipped": True}

        auth = _get_opensearch_auth()
        index_url = f"{OPENSEARCH_ENDPOINT}/{OPENSEARCH_INDEX}"

        # 1. DELETE /{index}
        del_resp = requests.delete(
            index_url, auth=auth,
            headers={"Content-Type": "application/json"}, timeout=30,
        )
        # 404 = 인덱스가 이미 없음 → 무시
        if del_resp.status_code not in (200, 404):
            del_resp.raise_for_status()
        logger.info(json.dumps({
            "event": "clear_index_deleted",
            "index": OPENSEARCH_INDEX,
            "status_code": del_resp.status_code,
        }))

        # 2. PUT /{index} — 매핑 재생성
        index_body: dict[str, Any] = {
            "settings": {
                "index": {
                    "knn": True,
                },
            },
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1024,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "faiss",
                        },
                    },
                    "module_name": {"type": "keyword"},
                    "parent_module": {"type": "keyword"},
                    "file_path": {"type": "keyword"},
                    "port_list": {"type": "text"},
                    "parameter_list": {"type": "text"},
                    "instance_list": {"type": "text"},
                    "parsed_summary": {"type": "text"},
                    "pipeline_id": {"type": "keyword"},
                    "chip_type": {"type": "keyword"},
                    "snapshot_date": {"type": "keyword"},
                    "analysis_type": {"type": "keyword"},
                    "hierarchy_path": {"type": "keyword"},
                    "clock_domains": {"type": "nested"},
                    "is_cdc_boundary": {"type": "boolean"},
                    "topic": {"type": "keyword"},
                    "topics": {"type": "keyword"},
                    "claim_id": {"type": "keyword"},
                    "claim_type": {"type": "keyword"},
                    "claim_text": {"type": "text"},
                    "hdd_content": {"type": "text"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                },
            },
        }

        put_resp = requests.put(
            index_url, auth=auth, json=index_body,
            headers={"Content-Type": "application/json"}, timeout=30,
        )
        put_resp.raise_for_status()
        logger.info(json.dumps({
            "event": "clear_index_recreated",
            "index": OPENSEARCH_INDEX,
            "status_code": put_resp.status_code,
        }))

        _update_dynamodb_status(pipeline_id, stage, "completed")
        return {"status": "completed"}

    except Exception as e:
        _update_dynamodb_status(pipeline_id, stage, "failed",
                               error_message=str(e))
        logger.error(json.dumps({
            "event": "clear_index_error",
            "pipeline_id": pipeline_id,
            "error": str(e),
        }))
        raise


# ---------------------------------------------------------------------------
# Reparse All: S3 파일 목록으로 Lambda 재트리거
# ---------------------------------------------------------------------------

def handle_reparse_all(event: dict[str, Any]) -> dict[str, Any]:
    """S3의 RTL 파일 목록을 읽어서 각 파일에 대해 Lambda를 비동기 invoke.

    1. ``list_objects_v2``로 ``s3_prefix`` 경로의 ``.v/.sv/.svh`` 파일 목록 조회
    2. 각 파일에 대해 S3 Event 형식의 payload 구성
    3. Lambda를 비동기(``InvocationType=Event``)로 invoke
    4. 배치 처리: 100개씩

    Args:
        event: ``pipeline_id`` (str) 필수, ``s3_prefix`` (str) 선택.

    Returns:
        ``{"status": "completed", "files_triggered": int, "errors": int}``
    """
    pipeline_id = event["pipeline_id"]
    s3_prefix = event.get("s3_prefix", f"rtl-sources/{pipeline_id}/")
    stage = "reparse_all"
    _update_dynamodb_status(pipeline_id, stage, "in_progress")

    bucket_name = RTL_S3_BUCKET or "bos-ai-rtl-src-533335672315"
    function_name = os.environ.get(
        "AWS_LAMBDA_FUNCTION_NAME", "lambda-rtl-parser-seoul-dev",
    )
    lambda_client = boto3.client("lambda", region_name="ap-northeast-2")

    files_triggered = 0
    errors = 0

    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name, Prefix=s3_prefix)

        batch: list[str] = []
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith((".v", ".sv", ".svh")):
                    batch.append(key)

                    if len(batch) >= BATCH_SIZE:
                        triggered, errs = _invoke_reparse_batch(
                            lambda_client, function_name, bucket_name, batch,
                        )
                        files_triggered += triggered
                        errors += errs
                        batch = []

        # 남은 배치 처리
        if batch:
            triggered, errs = _invoke_reparse_batch(
                lambda_client, function_name, bucket_name, batch,
            )
            files_triggered += triggered
            errors += errs

        _update_dynamodb_status(pipeline_id, stage, "completed",
                               extra={"files_triggered": files_triggered,
                                      "errors": errors})

        logger.info(json.dumps({
            "event": "reparse_all_complete",
            "pipeline_id": pipeline_id,
            "files_triggered": files_triggered,
            "errors": errors,
        }))
        return {"status": "completed", "files_triggered": files_triggered,
                "errors": errors}

    except Exception as e:
        _update_dynamodb_status(pipeline_id, stage, "failed",
                               error_message=str(e))
        logger.error(json.dumps({
            "event": "reparse_all_error",
            "pipeline_id": pipeline_id,
            "error": str(e),
        }))
        raise


def _invoke_reparse_batch(
    lambda_client: Any,
    function_name: str,
    bucket_name: str,
    keys: list[str],
) -> tuple[int, int]:
    """배치 내 각 파일에 대해 Lambda를 비동기 invoke."""
    triggered = 0
    errs = 0
    for key in keys:
        s3_event = {
            "Records": [{
                "s3": {
                    "bucket": {"name": bucket_name},
                    "object": {"key": key},
                },
            }],
        }
        try:
            lambda_client.invoke(
                FunctionName=function_name,
                InvocationType="Event",
                Payload=json.dumps(s3_event).encode(),
            )
            triggered += 1
        except Exception as e:
            errs += 1
            logger.warning(json.dumps({
                "event": "reparse_invoke_error",
                "key": key,
                "error": str(e),
            }))
    return triggered, errs


# ---------------------------------------------------------------------------
# Task 5.6: Main Dispatcher
# ---------------------------------------------------------------------------

# Stage → handler mapping
_STAGE_HANDLERS = {
    "hierarchy_extraction": handle_hierarchy_extraction,
    "clock_domain_analysis": handle_clock_domain_analysis,
    "dataflow_tracking": handle_dataflow_tracking,
    "topic_classification": handle_topic_classification,
    "claim_generation": handle_claim_generation,
    "hdd_generation": handle_hdd_generation,
    "variant_delta": handle_variant_delta,
    "backfill_pipeline_id": handle_backfill_pipeline_id,
    "clear_index": handle_clear_index,
    "reparse_all": handle_reparse_all,
}


def analysis_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Step Functions에서 호출하는 분석 파이프라인 핸들러.

    event에서 ``stage``와 ``pipeline_id``를 읽어 적절한 분석 함수를 디스패치한다.
    공통 에러 처리로 DynamoDB 상태 업데이트와 CloudWatch 로그 기록을 수행한다.

    Args:
        event: Step Functions에서 전달하는 이벤트.
            필수: ``stage`` (str), ``pipeline_id`` (str)
            선택: ``s3_prefix`` (str)
        context: Lambda context (사용하지 않음).

    Returns:
        분석 결과 dict (stage별 상이).

    Raises:
        ValueError: stage 또는 pipeline_id가 누락된 경우.
    """
    stage = event.get("stage")
    pipeline_id = event.get("pipeline_id")

    if not pipeline_id:
        error_msg = "pipeline_id is required"
        logger.error(json.dumps({"event": "analysis_handler_error", "error": error_msg}))
        raise ValueError(error_msg)

    if not stage:
        error_msg = "stage is required"
        logger.error(json.dumps({
            "event": "analysis_handler_error",
            "pipeline_id": pipeline_id,
            "error": error_msg,
        }))
        raise ValueError(error_msg)

    handler_fn = _STAGE_HANDLERS.get(stage)
    if handler_fn is None:
        error_msg = f"unknown stage: {stage}"
        logger.error(json.dumps({
            "event": "analysis_handler_error",
            "pipeline_id": pipeline_id,
            "error": error_msg,
        }))
        raise ValueError(error_msg)

    logger.info(json.dumps({
        "event": "analysis_handler_start",
        "pipeline_id": pipeline_id,
        "stage": stage,
    }))

    try:
        result = handler_fn(event)
        logger.info(json.dumps({
            "event": "analysis_handler_complete",
            "pipeline_id": pipeline_id,
            "stage": stage,
            "result": result,
        }))
        return result
    except Exception as e:
        logger.error(json.dumps({
            "event": "analysis_handler_failed",
            "pipeline_id": pipeline_id,
            "stage": stage,
            "error": str(e),
        }))
        raise
