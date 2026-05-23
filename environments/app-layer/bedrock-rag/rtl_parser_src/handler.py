"""
RTL Parser Lambda Handler
- S3 Event Notification으로 트리거
- RTL 파일을 정규식 기반으로 파싱하여 메타데이터 추출
- Titan Embeddings v2로 벡터 임베딩 변환 후 RTL OpenSearch Index에 인덱싱
- 파싱 결과를 Neptune Graph DB에 노드/엣지로 적재 (Phase 6)
- 향후 PyVerilog/AST 통합 시 parse_rtl_to_ast 내부 구현만 교체
"""

import json
import logging
import os
import re
import hashlib
import time
from datetime import datetime, timezone
from typing import Optional

import boto3

from pipeline_utils import extract_pipeline_id
from package_extractor import is_package_file, extract_package_constants, extract_module_parameters
from port_classifier import classify_ports
from generate_block_parser import extract_generate_blocks
from always_block_parser import extract_clock_domains
from bitwidth_evaluator import evaluate_bitwidth
from wire_declaration_parser import extract_wire_declarations
from port_binding_parser import extract_port_bindings
from port_binding_parser import _find_all_port_bindings as _extract_raw_port_bindings
from port_binding_parser import _strip_comments as _strip_rtl_comments
from signal_path_graph import extract_signal_path_edges

# tiktoken은 Linux Lambda 환경에서만 정상 동작 (Windows 빌드 바이너리 비호환)
try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 환경 변수
RTL_S3_BUCKET = os.environ.get("RTL_S3_BUCKET", "")
ERROR_TABLE_NAME = os.environ.get("ERROR_TABLE_NAME", "bos-ai-rtl-parse-errors")
DYNAMODB_EXTRACTION_TABLE = os.environ.get("DYNAMODB_EXTRACTION_TABLE", "rag-extraction-tasks")
CLAIM_DB_TABLE = os.environ.get("CLAIM_DB_TABLE", "")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
NEPTUNE_ENDPOINT = os.environ.get("NEPTUNE_ENDPOINT", "")
TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
MAX_TOKENS = 8000

# 파서별 Feature Flag 환경 변수 이름 (Requirements 26.1, 26.2)
# 기본값 모두 "true" — 모든 파서가 기본 활성화
_PARSER_FEATURE_FLAGS = {
    "PARSER_PACKAGE_ENABLED": "true",
    "PARSER_PORT_CLASSIFIER_ENABLED": "true",
    "PARSER_GENERATE_BLOCK_ENABLED": "true",
    "PARSER_ALWAYS_BLOCK_ENABLED": "true",
    "PARSER_FUNCTION_EXTRACTOR_ENABLED": "true",
    "PARSER_SIGNAL_PATH_ENABLED": "true",
}


def _is_parser_enabled(env_var_name: str) -> bool:
    """환경 변수 feature flag를 읽어 파서 활성화 여부를 반환.

    Args:
        env_var_name: 환경 변수 이름 (예: "PARSER_PACKAGE_ENABLED")

    Returns:
        True if the parser is enabled, False otherwise.
    """
    default = _PARSER_FEATURE_FLAGS.get(env_var_name, "true")
    return os.environ.get(env_var_name, default).lower() == "true"


# 모듈 레벨 캐시 (기존 코드 호환)
PARSER_PACKAGE_ENABLED = _is_parser_enabled("PARSER_PACKAGE_ENABLED")
PARSER_PORT_CLASSIFIER_ENABLED = _is_parser_enabled("PARSER_PORT_CLASSIFIER_ENABLED")
PARSER_GENERATE_BLOCK_ENABLED = _is_parser_enabled("PARSER_GENERATE_BLOCK_ENABLED")
PARSER_ALWAYS_BLOCK_ENABLED = _is_parser_enabled("PARSER_ALWAYS_BLOCK_ENABLED")
PARSER_FUNCTION_EXTRACTOR_ENABLED = _is_parser_enabled("PARSER_FUNCTION_EXTRACTOR_ENABLED")
PARSER_EP_TABLE_ENABLED = _is_parser_enabled("PARSER_EP_TABLE_ENABLED")
PARSER_WIRE_DECLARATION_ENABLED = _is_parser_enabled("PARSER_WIRE_DECLARATION_ENABLED")
PARSER_PORT_BINDING_ENABLED = _is_parser_enabled("PARSER_PORT_BINDING_ENABLED")
PARSER_SIGNAL_PATH_ENABLED = _is_parser_enabled("PARSER_SIGNAL_PATH_ENABLED")

# AWS 클라이언트
s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
bedrock_runtime = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)


# ---------------------------------------------------------------------------
# DFX 자동 추출 (Requirements 4.1, 4.2, 4.3)
# ---------------------------------------------------------------------------

def _is_dfx_module(module_name: str) -> bool:
    """모듈명이 DFX wrapper 패턴(*_dfx)에 매치되는지 확인.

    Args:
        module_name: RTL 모듈 이름

    Returns:
        True if module name ends with '_dfx'
    """
    return module_name.endswith("_dfx")


def _count_clock_ports(port_list: list) -> dict:
    """포트 목록에서 clock 관련 포트 수를 카운트.

    Clock 포트 판별: 포트 이름에 'clk' 또는 'clock'이 포함된 경우.

    Args:
        port_list: 포트 문자열 목록 (예: ["input clk", "output o_scan_clk"])

    Returns:
        {"clock_in": int, "clock_out": int} — input/inout clock 수, output clock 수
    """
    clock_in = 0
    clock_out = 0
    for port_entry in port_list:
        port_lower = port_entry.lower()
        if "clk" in port_lower or "clock" in port_lower:
            if port_lower.startswith("output"):
                clock_out += 1
            else:
                # input 또는 inout → clock_in
                clock_in += 1
    return {"clock_in": clock_in, "clock_out": clock_out}


def _detect_ijtag_ifdef(rtl_content: str) -> bool:
    """RTL 콘텐츠에서 IJTAG ifdef 존재 여부를 감지.

    패턴: `ifdef IJTAG` 또는 `ifdef DFX_IJTAG`

    Args:
        rtl_content: RTL 소스 코드 문자열

    Returns:
        True if IJTAG ifdef is present
    """
    return bool(re.search(r'`ifdef\s+(?:DFX_)?IJTAG', rtl_content))


def extract_dfx_module_claims(
    rtl_content: str,
    module_name: str,
    file_path: str,
    pipeline_id: str,
) -> list:
    """DFX wrapper 모듈에서 구조적 정보를 자동 추출하여 claims를 생성.

    추출 대상:
    - module name, file path
    - clock in/out port count
    - IJTAG ifdef presence

    Manual claim과 충돌 시 manual이 우선 (confidence_score 비교).
    Auto claim은 confidence_score=0.9으로 생성.

    Args:
        rtl_content: RTL 소스 코드 문자열
        module_name: 모듈 이름 (이미 *_dfx 패턴 확인됨)
        file_path: S3 파일 경로
        pipeline_id: 파이프라인 ID

    Returns:
        list of claim dicts
    """
    claims = []
    now = datetime.now(timezone.utc).isoformat()

    # 포트 목록 추출 (간단한 정규식 — parse_rtl_to_ast와 동일 패턴)
    content_no_comments = re.sub(r"//[^\n]*", "", rtl_content)
    content_no_comments = re.sub(r"/\*.*?\*/", "", content_no_comments, flags=re.DOTALL)

    port_pattern = re.compile(
        r"\b(input|output|inout)\s+(?:wire|reg|logic)?\s*((?:\[[^\]]+\]\s*)*)(\w+)",
        re.MULTILINE,
    )
    port_list = []
    for m in port_pattern.finditer(content_no_comments):
        direction = m.group(1)
        bit_width = m.group(2).strip()
        name = m.group(3)
        if bit_width:
            port_list.append(f"{direction} {bit_width} {name}")
        else:
            port_list.append(f"{direction} {name}")

    # Clock port count
    clock_counts = _count_clock_ports(port_list)

    # IJTAG ifdef detection
    has_ijtag = _detect_ijtag_ifdef(rtl_content)

    # Claim 생성: DFX module structural info
    ijtag_text = "IJTAG ifdef present" if has_ijtag else "no IJTAG ifdef detected"
    claim_text = (
        f"Module '{module_name}' is a DFX wrapper (auto-detected). "
        f"Clock ports: {clock_counts['clock_in']} in, {clock_counts['clock_out']} out. "
        f"{ijtag_text}."
    )

    claim_id = f"auto_dfx_{module_name}_{pipeline_id}"

    claims.append({
        "claim_id": claim_id,
        "claim_type": "structural",
        "claim_text": claim_text,
        "topic": "DFX",
        "module_name": module_name,
        "confidence_score": 0.9,
        "source": "auto_extracted",
        "pipeline_id": pipeline_id,
        "file_path": file_path,
        "analysis_type": "claim",
        "status": "auto_verified",
        "created_at": now,
        "dfx_metadata": {
            "clock_in": clock_counts["clock_in"],
            "clock_out": clock_counts["clock_out"],
            "has_ijtag": has_ijtag,
        },
    })

    logger.info(json.dumps({
        "event": "dfx_auto_extraction",
        "module_name": module_name,
        "clock_in": clock_counts["clock_in"],
        "clock_out": clock_counts["clock_out"],
        "has_ijtag": has_ijtag,
        "pipeline_id": pipeline_id,
    }))

    return claims


def resolve_dfx_claim_conflict(auto_claims: list, manual_claims: list) -> list:
    """Manual claim과 auto claim 충돌 시 manual 우선 (confidence_score 비교).

    동일 module_name에 대해 manual claim(confidence_score=1.0)이 존재하면
    auto claim(confidence_score=0.9)을 제외한다.

    Args:
        auto_claims: 자동 추출된 DFX claims
        manual_claims: 수동 삽입된 DFX claims

    Returns:
        충돌 해소된 최종 claims 목록 (manual 우선)
    """
    manual_modules = set()
    for claim in manual_claims:
        if claim.get("topic") == "DFX" and claim.get("source") == "manual_claim":
            manual_modules.add(claim.get("module_name", ""))

    resolved = []
    for claim in auto_claims:
        module_name = claim.get("module_name", "")
        if module_name in manual_modules:
            logger.info(json.dumps({
                "event": "dfx_claim_conflict_resolved",
                "module_name": module_name,
                "resolution": "manual_claim_priority",
                "auto_confidence": claim.get("confidence_score"),
            }))
            continue
        resolved.append(claim)

    return resolved


# ---------------------------------------------------------------------------
# 핸들러
# ---------------------------------------------------------------------------

def handler(event, context):
    """S3 Event Notification 핸들러 + RTL 인덱스 검색 (action: search)"""
    # Step Functions에서 호출하는 분석 파이프라인 요청
    if event.get("stage"):
        from analysis_handler import analysis_handler
        return analysis_handler(event, context)

    # RTL 인덱스 검색 요청 처리
    if event.get("action") == "search":
        return _search_rtl(event)

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        # rtl-sources/ 경로만 파싱 대상 — rtl-parsed/ 등 결과 경로는 무시 (재귀 루프 방지)
        if not key.startswith("rtl-sources/"):
            logger.info(json.dumps({
                "event": "rtl_parse_skip_non_source",
                "bucket": bucket,
                "key": key,
            }))
            continue

        # 처리 대상 확장자 분류
        if key.endswith((".v", ".sv", ".svh")):
            # Phase 1: RTL 파서 (기존)
            logger.info(json.dumps({"event": "rtl_parse_start", "bucket": bucket, "key": key}))
            _process_rtl_file(bucket, key)
        elif key.endswith((".json", ".svd", ".h", ".hpp", ".c", ".cpp",
                           ".md", ".rst", ".txt", ".sdc", ".dts", ".csv",
                           ".py", ".tcl", ".yaml", ".yml")):
            # Phase 2: 텍스트 기반 보조 파일 — chunking + embedding
            logger.info(json.dumps({"event": "text_file_start", "bucket": bucket, "key": key}))
            _process_text_file(bucket, key)
        elif key.endswith(".f"):
            # Phase 3: Filelist — hierarchy 추출
            logger.info(json.dumps({"event": "filelist_start", "bucket": bucket, "key": key}))
            _process_filelist(bucket, key)
        else:
            continue
    return {"statusCode": 200}


# ---------------------------------------------------------------------------
# 질의 유형 분류 및 동적 Boost (v9)
# ---------------------------------------------------------------------------

# 질의 유형별 키워드 패턴
_QUERY_TYPE_KEYWORDS = {
    "port_query": ["포트", "port", "input", "output", "인터페이스", "AXI", "APB", "clock", "reset", "clk"],
    "hierarchy_query": ["인스턴스", "계층", "hierarchy", "instantiate", "모듈 트리", "instance", "sub-module"],
    "config_query": ["파라미터", "parameter", "localparam", "설정", "크기", "size", "SizeX", "SizeY"],
    "connectivity_query": ["연결", "topology", "ring", "chain", "routing", "generate", "feedthrough"],
}

# 질의 유형별 동적 boost 가중치
_DYNAMIC_BOOST_MAP = {
    "port_query": {"claim": 4.0, "module_parse": 0.5, "hdd_section": 2.0},
    "hierarchy_query": {"claim": 1.5, "module_parse": 3.0, "hdd_section": 2.0},
    "config_query": {"claim": 4.0, "module_parse": 1.0, "hdd_section": 2.0},
    "connectivity_query": {"claim": 4.0, "module_parse": 1.0, "hdd_section": 2.0},
    "general_query": {"claim": 3.0, "module_parse": 1.0, "hdd_section": 2.0},
}


def classify_query_type(query: str) -> str:
    """사용자 질의를 키워드 패턴 매칭으로 5가지 유형 중 하나로 분류.

    Args:
        query: 사용자 질의 문자열

    Returns:
        질의 유형 문자열: port_query, hierarchy_query, config_query,
        connectivity_query, 또는 general_query (폴백)
    """
    if not query:
        return "general_query"

    query_lower = query.lower()
    for query_type, keywords in _QUERY_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in query_lower:
                return query_type

    return "general_query"


def get_dynamic_boosts(query_type: str) -> dict:
    """질의 유형에 따른 analysis_type별 boost 가중치 반환.

    Args:
        query_type: classify_query_type()이 반환한 질의 유형

    Returns:
        {"claim": float, "module_parse": float, "hdd_section": float}
    """
    return _DYNAMIC_BOOST_MAP.get(query_type, _DYNAMIC_BOOST_MAP["general_query"])


def _search_rtl(event):
    """RTL OpenSearch 인덱스 검색 — Main Lambda에서 동기 invoke로 호출.

    Supports both text search (query) and filtered search
    (pipeline_id, topic, analysis_type parameters).
    v9: 질의 유형별 동적 boost 적용.
    v9.5: Qdrant 기반 검색으로 전환 (AOSS 종료)
    """
    from qdrant_client import search as qdrant_search

    query = event.get("query", "")
    max_results = int(event.get("max_results", 20))

    # 필터링 파라미터
    pipeline_id = event.get("pipeline_id", "")
    topic = event.get("topic", "")
    analysis_type = event.get("analysis_type", "")

    # 텍스트 검색도 필터 파라미터도 없으면 빈 결과
    if not query and not pipeline_id and not topic and not analysis_type:
        return {"results": [], "total_hits": 0, "query": query}

    # v9: 질의 유형 분류
    query_type = classify_query_type(query) if query else "general_query"

    # 임베딩 벡터 생성 (시맨틱 검색)
    query_vector = None
    if query:
        query_vector = _generate_embedding(query)

    result = qdrant_search(
        query_vector=query_vector,
        query_text=query,
        max_results=max_results * 3,  # Over-fetch for dedup
        pipeline_id=pipeline_id,
        topic=topic,
        analysis_type=analysis_type,
    )

    results = result.get("results", [])
    total_hits = result.get("total_hits", 0)

    # v9: Dedup
    results = _dedup_search_results(results, max_results)

    return {
        "results": results,
        "total_hits": total_hits,
        "query": query,
        "metadata": {"query_type": query_type},
    }


# ---------------------------------------------------------------------------
# 검색 결과 중복 제거 (v9 dedup)
# ---------------------------------------------------------------------------

def _dedup_search_results(results, max_results):
    """Remove duplicate search results based on content fingerprint.

    Dedup strategy (ordered by priority):
    - claim: deduplicate by claim_text (same claim indexed from multiple file paths)
    - hdd_section: deduplicate by hdd_section_title + topic
    - module_parse / module_parse_chunk: deduplicate by module_name + analysis_type + sub_record_type
    - other: deduplicate by module_name + file_path basename

    Results are already sorted by score (descending). First occurrence wins.
    Returns at most max_results unique items.
    """
    seen = set()
    deduped = []

    for r in results:
        analysis_type = r.get("analysis_type", "")
        fingerprint = _get_result_fingerprint(r, analysis_type)

        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(r)

        if len(deduped) >= max_results:
            break

    if len(deduped) < len(results):
        logger.info(json.dumps({
            "event": "search_dedup",
            "before": len(results),
            "after": len(deduped),
            "removed": len(results) - len(deduped),
        }))

    return deduped


def _get_result_fingerprint(result, analysis_type):
    """Generate a dedup fingerprint for a search result."""
    if analysis_type == "claim":
        claim_text = result.get("claim_text", "")
        return f"claim:{claim_text[:200]}"

    elif analysis_type == "hdd_section":
        title = result.get("hdd_section_title", "")
        topic = result.get("topic", "")
        return f"hdd:{topic}:{title}"

    elif analysis_type in ("module_parse", "module_parse_chunk"):
        module_name = result.get("module_name", "")
        sub_type = result.get("sub_record_type", "")
        return f"mp:{module_name}:{analysis_type}:{sub_type}"

    elif analysis_type == "signal_path_edge":
        edge_type = result.get("edge_type", "")
        src = result.get("src", "")
        dst = result.get("dst", "")
        return f"spe:{edge_type}:{src}:{dst}"

    else:
        module_name = result.get("module_name", "")
        file_path = result.get("file_path", "")
        basename = file_path.rsplit("/", 1)[-1] if file_path else ""
        return f"other:{module_name}:{basename}"


# ---------------------------------------------------------------------------
# CloudWatch 메트릭 발행 (Requirements 26.4, 26.5)
# ---------------------------------------------------------------------------

def _get_cloudwatch_client():
    """CloudWatch 클라이언트 초기화 (VPC Endpoint 의존, graceful degradation)."""
    try:
        from botocore.config import Config
        cw_config = Config(connect_timeout=5, read_timeout=10, retries={'max_attempts': 1})
        return boto3.client('cloudwatch', region_name='ap-northeast-2', config=cw_config)
    except Exception:
        return None


def _publish_parser_metric(metric_name, value, unit, parser_name, cloudwatch=None):
    """파서별 CloudWatch 메트릭 발행 (BOS-AI/RTLParser 네임스페이스).

    Requirements: 26.4, 26.5
    """
    if cloudwatch is None:
        cloudwatch = _get_cloudwatch_client()
    if not cloudwatch:
        return
    try:
        cloudwatch.put_metric_data(
            Namespace='BOS-AI/RTLParser',
            MetricData=[{
                'MetricName': metric_name,
                'Value': float(value),
                'Unit': unit,
                'Dimensions': [
                    {'Name': 'parser_name', 'Value': parser_name},
                ],
                'Timestamp': datetime.now(timezone.utc),
            }]
        )
    except Exception as e:
        logger.warning(json.dumps({
            "event": "parser_metric_publish_failed",
            "metric_name": metric_name,
            "parser_name": parser_name,
            "error": str(e),
        }))


# ---------------------------------------------------------------------------
# Batch Embed + Index (v9.5 — 성능 최적화)
# ---------------------------------------------------------------------------

EMBED_CONCURRENCY = 5  # Bedrock Titan TPS 한도 내 병렬 호출 수
QDRANT_BATCH_SIZE = 50  # Qdrant batch upsert 크기


def _batch_embed_and_index(items: list):
    """여러 문서를 병렬 임베딩 + 배치 인덱싱으로 처리.

    Args:
        items: List of (metadata_dict, summary_text) tuples.
               summary_text는 임베딩할 텍스트.

    기존: N건 × (1초 embed + 0.5초 index) = 순차 N×1.5초
    개선: (N/10 × 1초) + (N/50 × 0.5초) = ~N/10초
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from qdrant_client import batch_index_documents

    if not items:
        return

    # Phase 1: 병렬 임베딩
    def _embed(text):
        truncated = truncate_to_tokens(text, MAX_TOKENS)
        return _generate_embedding(truncated)

    embeddings = [None] * len(items)
    with ThreadPoolExecutor(max_workers=EMBED_CONCURRENCY) as executor:
        futures = {}
        for i, (metadata, summary) in enumerate(items):
            futures[executor.submit(_embed, summary)] = i
        for future in as_completed(futures):
            idx = futures[future]
            try:
                embeddings[idx] = future.result()
            except Exception as e:
                logger.warning(f"Embedding failed for item {idx}: {e}")
                embeddings[idx] = None

    # Phase 2: 배치 Qdrant 인덱싱
    batch = []
    indexed_total = 0
    for i, (metadata, _) in enumerate(items):
        if embeddings[i]:
            batch.append((metadata, embeddings[i]))
        if len(batch) >= QDRANT_BATCH_SIZE:
            indexed_total += batch_index_documents(batch)
            batch = []
    if batch:
        indexed_total += batch_index_documents(batch)

    # DynamoDB claim 저장 (기존 호환)
    for metadata, _ in items:
        _store_claim_to_dynamodb(metadata)

    logger.info(json.dumps({
        "event": "batch_embed_index_complete",
        "total_items": len(items),
        "indexed": indexed_total,
    }))


# ---------------------------------------------------------------------------
# Phase 2: 텍스트 기반 보조 파일 처리 (v9.5)
# ---------------------------------------------------------------------------

TEXT_CHUNK_SIZE = 2000  # 문자 수 기준 청킹


def _process_text_file(bucket: str, key: str):
    """텍스트 기반 보조 파일을 chunking + embedding하여 Qdrant에 인덱싱.

    대상: .json, .svd, .h, .c, .cpp, .md, .rst, .txt, .sdc, .dts, .csv, .py, .tcl, .yaml
    """
    _INDEX_BUFFER.clear()

    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.error(json.dumps({"event": "text_file_read_error", "key": key, "error": str(e)}))
        return

    pipeline_info = extract_pipeline_id(key)
    file_ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""

    # 파일 타입별 analysis_type 분류
    analysis_type_map = {
        "json": "config_data", "svd": "register_map", "csv": "structured_data",
        "h": "firmware_header", "hpp": "firmware_header", "c": "firmware_source",
        "cpp": "firmware_source", "md": "documentation", "rst": "documentation",
        "txt": "documentation", "sdc": "design_constraint", "dts": "device_tree",
        "py": "script", "tcl": "script", "yaml": "config_data", "yml": "config_data",
    }
    analysis_type = analysis_type_map.get(file_ext, "text_file")

    # 청킹: 2000자씩 분할 (줄 단위로 자르기)
    chunks = _chunk_text(content, TEXT_CHUNK_SIZE)

    for i, chunk in enumerate(chunks):
        metadata = {
            "file_path": key,
            "pipeline_id": pipeline_info["pipeline_id"],
            "chip_type": pipeline_info["chip_type"],
            "analysis_type": analysis_type,
            "module_name": key.rsplit("/", 1)[-1],  # 파일명
            "parsed_summary": chunk[:500],
            "claim_text": "",
            "claim_id": f"{hashlib.sha256(key.encode()).hexdigest()[:12]}_chunk{i}",
            "topic": file_ext,
            "sub_record_type": f"chunk_{i}",
        }
        summary = chunk
        embedding = _generate_embedding(truncate_to_tokens(summary, MAX_TOKENS))
        if embedding:
            _index_to_opensearch(metadata, embedding)

    _flush_index_buffer()

    logger.info(json.dumps({
        "event": "text_file_success",
        "key": key,
        "chunks": len(chunks),
        "analysis_type": analysis_type,
        "pipeline_id": pipeline_info["pipeline_id"],
    }))


def _chunk_text(text: str, chunk_size: int) -> list:
    """텍스트를 줄 단위로 chunk_size 이내로 분할."""
    chunks = []
    current = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        if current_len + len(line) > chunk_size and current:
            chunks.append("".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)

    if current:
        chunks.append("".join(current))
    return chunks


# ---------------------------------------------------------------------------
# Phase 3: Filelist hierarchy 추출 (v9.5)
# ---------------------------------------------------------------------------

def _process_filelist(bucket: str, key: str):
    """Filelist (.f) 파일에서 컴파일 계층 구조를 추출하여 인덱싱.

    Filelist 구조:
      +incdir+./include
      ./rtl/top_module.sv
      ./rtl/sub_module.sv
      -f other_filelist.f
    """
    _INDEX_BUFFER.clear()

    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.error(json.dumps({"event": "filelist_read_error", "key": key, "error": str(e)}))
        return

    pipeline_info = extract_pipeline_id(key)

    # 파일 목록 파싱
    file_entries = []
    include_dirs = []
    sub_filelists = []

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        if line.startswith("+incdir+"):
            include_dirs.append(line.replace("+incdir+", "").strip())
        elif line.startswith("-f ") or line.startswith("-F "):
            sub_filelists.append(line[3:].strip())
        elif line.startswith("+") or line.startswith("-"):
            continue  # 기타 옵션 무시
        else:
            file_entries.append(line)

    # Hierarchy 추출: 파일 경로에서 디렉토리 구조 → 모듈 계층 추론
    hierarchy_tree = {}
    for entry in file_entries:
        parts = entry.replace("\\", "/").strip("./").split("/")
        if len(parts) >= 2:
            parent_dir = parts[-2] if len(parts) >= 2 else ""
            filename = parts[-1]
            module_name = filename.rsplit(".", 1)[0] if "." in filename else filename
            hierarchy_tree.setdefault(parent_dir, []).append(module_name)

    # 인덱싱: filelist 전체 구조를 하나의 문서로
    hierarchy_text = f"Filelist '{key.rsplit('/', 1)[-1]}' defines compilation order:\n"
    hierarchy_text += f"Total files: {len(file_entries)}, Include dirs: {len(include_dirs)}\n"
    hierarchy_text += f"Sub-filelists: {sub_filelists}\n\n"

    for parent, children in sorted(hierarchy_tree.items()):
        hierarchy_text += f"[{parent}] ({len(children)} modules): {', '.join(children[:20])}"
        if len(children) > 20:
            hierarchy_text += f" ... (+{len(children)-20} more)"
        hierarchy_text += "\n"

    metadata = {
        "file_path": key,
        "pipeline_id": pipeline_info["pipeline_id"],
        "chip_type": pipeline_info["chip_type"],
        "analysis_type": "filelist_hierarchy",
        "module_name": key.rsplit("/", 1)[-1],
        "parsed_summary": hierarchy_text[:2000],
        "instance_list": " ".join(file_entries[:100]),
        "claim_text": f"Filelist contains {len(file_entries)} RTL files in {len(hierarchy_tree)} directories",
        "claim_id": hashlib.sha256(key.encode()).hexdigest()[:16],
        "topic": "Hierarchy",
    }

    embedding = _generate_embedding(truncate_to_tokens(hierarchy_text, MAX_TOKENS))
    if embedding:
        _index_to_opensearch(metadata, embedding)

    # 개별 디렉토리별 claim도 생성 (검색 가능하도록)
    for parent_dir, modules in hierarchy_tree.items():
        if len(modules) >= 3:  # 3개 이상 모듈이 있는 디렉토리만
            claim_text = (
                f"Directory '{parent_dir}' in filelist contains {len(modules)} modules: "
                f"{', '.join(modules[:10])}"
            )
            dir_metadata = {
                "file_path": key,
                "pipeline_id": pipeline_info["pipeline_id"],
                "analysis_type": "filelist_hierarchy",
                "module_name": parent_dir,
                "claim_text": claim_text,
                "claim_id": hashlib.sha256(f"{key}:{parent_dir}".encode()).hexdigest()[:16],
                "topic": "Hierarchy",
                "instance_list": " ".join(modules),
            }
            dir_embedding = _generate_embedding(truncate_to_tokens(claim_text, MAX_TOKENS))
            if dir_embedding:
                _index_to_opensearch(dir_metadata, dir_embedding)

    _flush_index_buffer()

    logger.info(json.dumps({
        "event": "filelist_success",
        "key": key,
        "file_entries": len(file_entries),
        "directories": len(hierarchy_tree),
        "include_dirs": len(include_dirs),
        "pipeline_id": pipeline_info["pipeline_id"],
    }))


def _process_rtl_file(bucket: str, key: str):
    """RTL 파일 처리 메인 로직"""
    # Buffer 초기화 (이전 invoke 잔여 방지)
    _INDEX_BUFFER.clear()

    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        rtl_content = response["Body"].read().decode("utf-8")
    except Exception as e:
        _record_error(key, f"S3 GetObject 실패: {e}")
        raise

    # CloudWatch 메트릭 클라이언트 (graceful degradation)
    cw_client = _get_cloudwatch_client()

    # Pipeline_ID 추출
    pipeline_info = extract_pipeline_id(key)

    # Phase 6b: PyVerilog AST 파서 점진적 롤아웃 (환경 변수 기반 feature flag)
    use_pyverilog = os.environ.get("USE_PYVERILOG", "false").lower() == "true"
    if use_pyverilog:
        metadata = _parse_rtl_pyverilog(rtl_content)
    else:
        metadata = parse_rtl_to_ast(rtl_content)
    metadata["file_path"] = key

    # Pipeline_ID 메타데이터 추가
    metadata["pipeline_id"] = pipeline_info["pipeline_id"]
    metadata["chip_type"] = pipeline_info["chip_type"]
    metadata["snapshot_date"] = pipeline_info["snapshot_date"]
    metadata["analysis_type"] = "module_parse"

    # parsed JSON 저장
    parsed_key = key.replace("rtl-sources/", "rtl-parsed/") + ".parsed.json"
    s3_client.put_object(
        Bucket=bucket,
        Key=parsed_key,
        Body=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )

    # 임베딩 생성 및 OpenSearch 인덱싱
    summary = generate_parsed_summary(metadata)
    truncated = truncate_to_tokens(summary, MAX_TOKENS)
    _index_to_opensearch(metadata, truncated)

    # Neptune Graph DB 관계 적재 (Phase 6)
    _load_to_neptune(metadata)

    # v6: Package file → extract localparam/enum/struct as claims
    if is_package_file(key):
        if not PARSER_PACKAGE_ENABLED:
            logger.info(json.dumps({"event": "parser_disabled_skip", "parser_name": "package_extractor"}))
        else:
            pkg_start = time.time()
            pkg_claims = extract_package_constants(
                rtl_content, file_path=key,
                pipeline_id=pipeline_info["pipeline_id"],
            )
            pkg_elapsed_ms = int((time.time() - pkg_start) * 1000)
            for claim in pkg_claims:
                claim.setdefault("parser_source", "package_extractor")
                claim_summary = claim.get("claim_text", "")
                claim_truncated = truncate_to_tokens(claim_summary, MAX_TOKENS)
                _index_to_opensearch(claim, claim_truncated)
            logger.info(json.dumps({
                "event": "parser_execution_result",
                "parser_name": "package_extractor",
                "claims_generated": len(pkg_claims),
                "execution_time_ms": pkg_elapsed_ms,
                "files_processed": 1,
                "key": key,
                "pipeline_id": pipeline_info["pipeline_id"],
            }))
            _publish_parser_metric("ParserClaimCount", len(pkg_claims), "Count", "package_extractor", cw_client)
            _publish_parser_metric("ParserExecutionTime", pkg_elapsed_ms, "Milliseconds", "package_extractor", cw_client)
    else:
        # v9.4: Non-package module files → extract top-level module parameters (Req 7.1, 7.4)
        if PARSER_PACKAGE_ENABLED:
            mod_param_start = time.time()
            mod_name_for_params = metadata.get("module_name", "")
            if mod_name_for_params:
                mod_param_claims = extract_module_parameters(
                    rtl_content, module_name=mod_name_for_params,
                    file_path=key, pipeline_id=pipeline_info["pipeline_id"],
                )
                mod_param_elapsed_ms = int((time.time() - mod_param_start) * 1000)
                for claim in mod_param_claims:
                    claim.setdefault("parser_source", "package_extractor")
                    claim_summary = claim.get("claim_text", "")
                    claim_truncated = truncate_to_tokens(claim_summary, MAX_TOKENS)
                    _index_to_opensearch(claim, claim_truncated)
                if mod_param_claims:
                    logger.info(json.dumps({
                        "event": "parser_execution_result",
                        "parser_name": "module_parameter_extractor",
                        "claims_generated": len(mod_param_claims),
                        "execution_time_ms": mod_param_elapsed_ms,
                        "files_processed": 1,
                        "key": key,
                        "module_name": mod_name_for_params,
                        "pipeline_id": pipeline_info["pipeline_id"],
                    }))
                    _publish_parser_metric("ParserClaimCount", len(mod_param_claims), "Count", "module_parameter_extractor", cw_client)
                    _publish_parser_metric("ParserExecutionTime", mod_param_elapsed_ms, "Milliseconds", "module_parameter_extractor", cw_client)

    # DynamoDB 파싱 완료 이벤트 기록
    module_name = metadata.get("module_name", "unknown")

    # v7: Port classification — large modules get per-category port claims
    port_list = metadata.get("port_list", [])
    if len(port_list) >= 10:
        if not PARSER_PORT_CLASSIFIER_ENABLED:
            logger.info(json.dumps({"event": "parser_disabled_skip", "parser_name": "port_classifier"}))
            port_claims = []
        else:
            port_start = time.time()
            port_claims = classify_ports(
                port_list, module_name=module_name,
                file_path=key, pipeline_id=pipeline_info["pipeline_id"],
            )
            port_elapsed_ms = int((time.time() - port_start) * 1000)
            for claim in port_claims:
                claim.setdefault("parser_source", "port_classifier")
                claim_summary = claim.get("claim_text", "")
                claim_truncated = truncate_to_tokens(claim_summary, MAX_TOKENS)
                _index_to_opensearch(claim, claim_truncated)
            if port_claims:
                logger.info(json.dumps({
                    "event": "parser_execution_result",
                    "parser_name": "port_classifier",
                    "claims_generated": len(port_claims),
                    "execution_time_ms": port_elapsed_ms,
                    "files_processed": 1,
                    "key": key,
                    "module_name": module_name,
                }))
                _publish_parser_metric("ParserClaimCount", len(port_claims), "Count", "port_classifier", cw_client)
                _publish_parser_metric("ParserExecutionTime", port_elapsed_ms, "Milliseconds", "port_classifier", cw_client)
    else:
        port_claims = []

    # v9 Phase 7: Generate Block Parser (Requirements 18.5, 26.1)
    if PARSER_GENERATE_BLOCK_ENABLED:
        gen_start = time.time()
        gen_claims = extract_generate_blocks(
            rtl_content, module_name=module_name,
            file_path=key, pipeline_id=pipeline_info["pipeline_id"],
        )
        # Also extract module-level repeaters (outside generate blocks)
        from generate_block_parser import _extract_noc_repeaters
        module_level_repeater_claims = _extract_noc_repeaters(
            rtl_content, "", {},
            module_name, key, pipeline_info["pipeline_id"],
        )
        gen_claims.extend(module_level_repeater_claims)
        gen_elapsed_ms = int((time.time() - gen_start) * 1000)
        for claim in gen_claims:
            claim.setdefault("parser_source", "generate_block_parser")
            claim_summary = claim.get("claim_text", "")
            claim_truncated = truncate_to_tokens(claim_summary, MAX_TOKENS)
            _index_to_opensearch(claim, claim_truncated)
        if gen_claims:
            logger.info(json.dumps({
                "event": "parser_execution_result",
                "parser_name": "generate_block_parser",
                "claims_generated": len(gen_claims),
                "execution_time_ms": gen_elapsed_ms,
                "files_processed": 1,
                "key": key,
                "module_name": module_name,
            }))
            _publish_parser_metric("ParserClaimCount", len(gen_claims), "Count", "generate_block_parser", cw_client)
            _publish_parser_metric("ParserExecutionTime", gen_elapsed_ms, "Milliseconds", "generate_block_parser", cw_client)
    else:
        logger.info(json.dumps({"event": "parser_disabled_skip", "parser_name": "generate_block_parser"}))

    # v9 Phase 7: Always Block Parser — clock domain extraction (Requirements 19.5, 26.1)
    if PARSER_ALWAYS_BLOCK_ENABLED:
        always_start = time.time()
        always_claims = extract_clock_domains(
            rtl_content, module_name=module_name,
            file_path=key, pipeline_id=pipeline_info["pipeline_id"],
        )
        always_elapsed_ms = int((time.time() - always_start) * 1000)
        for claim in always_claims:
            claim.setdefault("parser_source", "always_block_parser")
            claim_summary = claim.get("claim_text", "")
            claim_truncated = truncate_to_tokens(claim_summary, MAX_TOKENS)
            _index_to_opensearch(claim, claim_truncated)
        if always_claims:
            logger.info(json.dumps({
                "event": "parser_execution_result",
                "parser_name": "always_block_parser",
                "claims_generated": len(always_claims),
                "execution_time_ms": always_elapsed_ms,
                "files_processed": 1,
                "key": key,
                "module_name": module_name,
            }))
            _publish_parser_metric("ParserClaimCount", len(always_claims), "Count", "always_block_parser", cw_client)
            _publish_parser_metric("ParserExecutionTime", always_elapsed_ms, "Milliseconds", "always_block_parser", cw_client)
    else:
        logger.info(json.dumps({"event": "parser_disabled_skip", "parser_name": "always_block_parser"}))

    # v9 Phase 7: Bitwidth evaluation — resolve parametric port widths (Requirements 22.5)
    param_context = {}
    for param_entry in metadata.get("parameter_list", []):
        if "=" in param_entry:
            p_name, p_val = param_entry.split("=", 1)
            try:
                param_context[p_name.strip()] = int(p_val.strip())
            except ValueError:
                pass
    if param_context:
        for i, port_entry in enumerate(port_list):
            # Extract bitwidth expression from port like "input [SizeX-1:0] data"
            bw_match = re.search(r"\[([^\]]+):([^\]]+)\]", port_entry)
            if bw_match:
                high_expr = bw_match.group(1)
                low_expr = bw_match.group(2)
                high_val = evaluate_bitwidth(high_expr, param_context)
                low_val = evaluate_bitwidth(low_expr, param_context)
                if isinstance(high_val, int) and isinstance(low_val, int):
                    resolved = port_entry[:bw_match.start()] + f"[{high_val}:{low_val}]" + port_entry[bw_match.end():]
                    port_list[i] = resolved

    # v9.2 Phase 8: Wire Declaration Parser (Gap 4-5)
    if PARSER_WIRE_DECLARATION_ENABLED:
        wire_start = time.time()
        # Pass known struct types from package extraction if available
        wire_known_structs = None
        if is_package_file(key):
            # Package files may have struct definitions already extracted
            wire_known_structs = None  # Will be populated from pkg_claims if available
        wire_claims = extract_wire_declarations(
            rtl_content, module_name=module_name,
            file_path=key, pipeline_id=pipeline_info["pipeline_id"],
            known_structs=wire_known_structs,
        )
        wire_elapsed_ms = int((time.time() - wire_start) * 1000)
        for claim in wire_claims:
            claim.setdefault("parser_source", "wire_declaration_parser")
            claim_summary = claim.get("claim_text", "")
            claim_truncated = truncate_to_tokens(claim_summary, MAX_TOKENS)
            _index_to_opensearch(claim, claim_truncated)
        if wire_claims:
            logger.info(json.dumps({
                "event": "parser_execution_result",
                "parser_name": "wire_declaration_parser",
                "claims_generated": len(wire_claims),
                "execution_time_ms": wire_elapsed_ms,
                "files_processed": 1,
                "key": key,
                "module_name": module_name,
            }))
            _publish_parser_metric("ParserClaimCount", len(wire_claims), "Count", "wire_declaration_parser", cw_client)
            _publish_parser_metric("ParserExecutionTime", wire_elapsed_ms, "Milliseconds", "wire_declaration_parser", cw_client)
    else:
        logger.info(json.dumps({"event": "parser_disabled_skip", "parser_name": "wire_declaration_parser"}))

    # v9.3 Phase 8: Port Binding Parser + Neptune CONNECTS_TO 적재 (Requirements 31.1~31.8)
    if PARSER_PORT_BINDING_ENABLED:
        pb_start = time.time()
        # RTL 콘텐츠에서 포트 바인딩 추출 (claims for OpenSearch)
        pb_claims = extract_port_bindings(
            rtl_content, module_name=module_name,
            file_path=key, pipeline_id=pipeline_info["pipeline_id"],
        )
        # Raw 바인딩 데이터 추출 (Neptune 적재용)
        clean_content = _strip_rtl_comments(rtl_content)
        raw_bindings = _extract_raw_port_bindings(clean_content, key)
        pb_elapsed_ms = int((time.time() - pb_start) * 1000)

        # OpenSearch 인덱싱
        for claim in pb_claims:
            claim.setdefault("parser_source", "port_binding_parser")
            claim_summary = claim.get("claim_text", "")
            claim_truncated = truncate_to_tokens(claim_summary, MAX_TOKENS)
            _index_to_opensearch(claim, claim_truncated)

        # Neptune CONNECTS_TO 엣지 적재
        _load_port_bindings_to_neptune(raw_bindings, module_name)

        if pb_claims:
            logger.info(json.dumps({
                "event": "parser_execution_result",
                "parser_name": "port_binding_parser",
                "claims_generated": len(pb_claims),
                "bindings_extracted": len(raw_bindings),
                "execution_time_ms": pb_elapsed_ms,
                "files_processed": 1,
                "key": key,
                "module_name": module_name,
            }))
            _publish_parser_metric("ParserClaimCount", len(pb_claims), "Count", "port_binding_parser", cw_client)
            _publish_parser_metric("ParserExecutionTime", pb_elapsed_ms, "Milliseconds", "port_binding_parser", cw_client)
    else:
        logger.info(json.dumps({"event": "parser_disabled_skip", "parser_name": "port_binding_parser"}))

    # v9.4: DFX 자동 추출 — *_dfx 패턴 모듈 자동 감지 (Requirements 4.1, 4.2, 4.3)
    if _is_dfx_module(module_name):
        dfx_start = time.time()
        dfx_claims = extract_dfx_module_claims(
            rtl_content,
            module_name=module_name,
            file_path=key,
            pipeline_id=pipeline_info["pipeline_id"],
        )
        dfx_elapsed_ms = int((time.time() - dfx_start) * 1000)
        for claim in dfx_claims:
            claim.setdefault("parser_source", "dfx_auto_extractor")
            claim_summary = claim.get("claim_text", "")
            claim_truncated = truncate_to_tokens(claim_summary, MAX_TOKENS)
            _index_to_opensearch(claim, claim_truncated)
        if dfx_claims:
            logger.info(json.dumps({
                "event": "parser_execution_result",
                "parser_name": "dfx_auto_extractor",
                "claims_generated": len(dfx_claims),
                "execution_time_ms": dfx_elapsed_ms,
                "files_processed": 1,
                "key": key,
                "module_name": module_name,
            }))
            _publish_parser_metric("ParserClaimCount", len(dfx_claims), "Count", "dfx_auto_extractor", cw_client)
            _publish_parser_metric("ParserExecutionTime", dfx_elapsed_ms, "Milliseconds", "dfx_auto_extractor", cw_client)

    # v9.5: Signal Path Graph — assign/port/wire edges for signal flow tracing
    if PARSER_SIGNAL_PATH_ENABLED:
        sp_start = time.time()
        sp_edges = extract_signal_path_edges(
            rtl_content,
            module_name=module_name,
            file_path=key,
            pipeline_id=pipeline_info["pipeline_id"],
        )
        sp_elapsed_ms = int((time.time() - sp_start) * 1000)
        for edge in sp_edges:
            edge.setdefault("parser_source", "signal_path_graph")
            edge_summary = (
                f"{edge.get('edge_type', '')} in {module_name}: "
                f"{edge.get('src', '')} -> {edge.get('dst', '')} "
                f"[{edge.get('category', 'general')}]"
            )
            edge_truncated = truncate_to_tokens(edge_summary, MAX_TOKENS)
            _index_to_opensearch(edge, edge_truncated)
        if sp_edges:
            logger.info(json.dumps({
                "event": "parser_execution_result",
                "parser_name": "signal_path_graph",
                "claims_generated": len(sp_edges),
                "execution_time_ms": sp_elapsed_ms,
                "files_processed": 1,
                "key": key,
                "module_name": module_name,
                "pipeline_id": pipeline_info["pipeline_id"],
            }))
            _publish_parser_metric("ParserClaimCount", len(sp_edges), "Count", "signal_path_graph", cw_client)
            _publish_parser_metric("ParserExecutionTime", sp_elapsed_ms, "Milliseconds", "signal_path_graph", cw_client)
    else:
        logger.info(json.dumps({"event": "parser_disabled_skip", "parser_name": "signal_path_graph"}))

    # v9: 대형 모듈 청킹 — 포트 50개 이상 모듈을 Sub_Record로 분할
    if len(port_list) >= 50:
        sub_records = _create_sub_records(metadata, port_claims)
        for sub_record in sub_records:
            sub_summary = sub_record.get("parsed_summary", "")
            sub_truncated = truncate_to_tokens(sub_summary, MAX_TOKENS)
            _index_to_opensearch(sub_record, sub_truncated)
        if sub_records:
            logger.info(json.dumps({
                "event": "sub_records_indexed",
                "key": key,
                "sub_record_count": len(sub_records),
                "module_name": module_name,
            }))

    _record_parse_event(pipeline_info["pipeline_id"], module_name, key)

    # v9.5: Buffer에 쌓인 모든 문서를 Qdrant에 배치 인덱싱
    _flush_index_buffer()

    logger.info(json.dumps({
        "event": "rtl_parse_success",
        "key": key,
        "module_name": metadata.get("module_name", ""),
        "pipeline_id": pipeline_info["pipeline_id"],
        "port_count": len(metadata.get("port_list", [])),
        "instance_count": len(metadata.get("instance_list", [])),
    }))


# ---------------------------------------------------------------------------
# 대형 모듈 청킹 (v9 — Sub_Record 분할)
# ---------------------------------------------------------------------------

def _create_sub_records(metadata: dict, port_claims: list) -> list:
    """대형 모듈(포트 50개 이상)을 기능별 Sub_Record로 분할.

    3가지 Sub_Record 유형:
    - port_summary: Port_Classifier 카테고리별 포트 요약
    - instance_hierarchy: 인스턴스 목록 + 모듈 타입
    - parameter_config: 파라미터 목록 + 값

    Args:
        metadata: 원본 모듈 파싱 메타데이터
        port_claims: classify_ports()가 생성한 포트 카테고리 claim 목록

    Returns:
        Sub_Record dict 목록 (각각 개별 임베딩 + OpenSearch 인덱싱 대상)
    """
    module_name = metadata.get("module_name", "")
    file_path = metadata.get("file_path", "")
    pipeline_id = metadata.get("pipeline_id", "")

    sub_records = []

    # (1) port_summary: Port_Classifier 카테고리별 Sub_Record
    for claim in port_claims:
        claim_text = claim.get("claim_text", "")
        sub_record = {
            "module_name": module_name,
            "parent_module_name": module_name,
            "sub_record_type": "port_summary",
            "analysis_type": "module_parse_chunk",
            "file_path": file_path,
            "pipeline_id": pipeline_id,
            "parsed_summary": claim_text,
            "port_list": "",
            "parameter_list": "",
            "instance_list": "",
            "parent_module": metadata.get("parent_module", ""),
        }
        sub_records.append(sub_record)

    # (2) instance_hierarchy: 인스턴스 목록 + 모듈 타입
    instance_list = metadata.get("instance_list", [])
    if instance_list:
        instance_summary = f"Module '{module_name}' instance hierarchy: " + ", ".join(instance_list)
        sub_records.append({
            "module_name": module_name,
            "parent_module_name": module_name,
            "sub_record_type": "instance_hierarchy",
            "analysis_type": "module_parse_chunk",
            "file_path": file_path,
            "pipeline_id": pipeline_id,
            "parsed_summary": instance_summary,
            "port_list": "",
            "parameter_list": "",
            "instance_list": " ".join(instance_list) if isinstance(instance_list, list) else instance_list,
            "parent_module": metadata.get("parent_module", ""),
        })

    # (3) parameter_config: 파라미터 목록 + 값
    parameter_list = metadata.get("parameter_list", [])
    if parameter_list:
        param_summary = f"Module '{module_name}' parameter configuration: " + ", ".join(parameter_list)
        sub_records.append({
            "module_name": module_name,
            "parent_module_name": module_name,
            "sub_record_type": "parameter_config",
            "analysis_type": "module_parse_chunk",
            "file_path": file_path,
            "pipeline_id": pipeline_id,
            "parsed_summary": param_summary,
            "port_list": "",
            "parameter_list": " ".join(parameter_list) if isinstance(parameter_list, list) else parameter_list,
            "instance_list": "",
            "parent_module": metadata.get("parent_module", ""),
        })

    return sub_records


# ---------------------------------------------------------------------------
# RTL 파싱 (정규식 기반 — 향후 PyVerilog/AST로 교체 가능)
# ---------------------------------------------------------------------------

def parse_rtl_to_ast(rtl_content: str) -> dict:
    """RTL 파일을 정규식 기반으로 파싱하여 메타데이터 추출.
    향후 PyVerilog/AST 통합 시 함수 시그니처 변경 없이 내부 구현만 교체.

    Returns:
        {
            "module_name": str,
            "parent_module": str,   # 없으면 ""
            "port_list": list[str],
            "parameter_list": list[str],
            "instance_list": list[str],
            "file_path": str        # 호출 후 외부에서 설정
        }
    """
    result = {
        "module_name": "",
        "parent_module": "",
        "port_list": [],
        "parameter_list": [],
        "instance_list": [],
        "file_path": "",
    }

    # 주석 제거 (// 한 줄, /* */ 블록)
    content = re.sub(r"//[^\n]*", "", rtl_content)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

    # 모듈명 추출
    module_match = re.search(
        r"\bmodule\s+(\w+)\s*(?:#\s*\(|[\(\;])", content
    )
    if module_match:
        result["module_name"] = module_match.group(1)

    # 포트 목록 추출 (input/output/inout 선언 + 비트폭 캡처)
    port_pattern = re.compile(
        r"\b(input|output|inout)\s+(?:wire|reg|logic)?\s*((?:\[[^\]]+\]\s*)*)(\w+)", re.MULTILINE
    )
    ports = []
    for m in port_pattern.finditer(content):
        direction = m.group(1)
        bit_width = m.group(2).strip()
        name = m.group(3)
        if bit_width:
            ports.append(f"{direction} {bit_width} {name}")
        else:
            ports.append(f"{direction} {name}")
    result["port_list"] = list(dict.fromkeys(ports))  # 중복 제거

    # 파라미터 목록 추출
    param_pattern = re.compile(
        r"\bparameter\s+(?:integer|real|string)?\s*(\w+)\s*=\s*([^,;\)]+)", re.MULTILINE
    )
    params = []
    for m in param_pattern.finditer(content):
        params.append(f"{m.group(1)}={m.group(2).strip()}")
    result["parameter_list"] = list(dict.fromkeys(params))

    # 인스턴스 목록 추출 (모듈 인스턴스화)
    instance_pattern = re.compile(
        r"^\s*(\w+)\s+(?:#\s*\([^)]*\)\s*)?(\w+)\s*\(", re.MULTILINE
    )
    # 키워드 제외
    keywords = {
        "module", "endmodule", "input", "output", "inout", "wire", "reg",
        "logic", "always", "initial", "assign", "begin", "end", "if", "else",
        "case", "endcase", "for", "while", "function", "task", "parameter",
        "localparam", "generate", "endgenerate", "integer", "real",
    }
    instances = []
    for m in instance_pattern.finditer(content):
        module_type = m.group(1)
        instance_name = m.group(2)
        if module_type not in keywords and instance_name not in keywords:
            instances.append(f"{instance_name}: {module_type}")
    result["instance_list"] = list(dict.fromkeys(instances))

    return result


# ---------------------------------------------------------------------------
# Phase 6b: PyVerilog AST 파서 스텁 (ECR 컨테이너 전환 후 활성화)
# ---------------------------------------------------------------------------

def _parse_rtl_pyverilog(rtl_content: str) -> dict:
    """PyVerilog AST 기반 RTL 파서 — Phase 6b 플레이스홀더.

    현재 정규식 기반 parse_rtl_to_ast()를 대체할 예정이며,
    ECR 컨테이너 이미지 배포 전환 후 PyVerilog 의존성을 활성화하여
    AST 수준의 정밀한 RTL 구조 분석을 수행한다.

    추가 분석 항목 (Phase 6b 구현 예정):
    - always_ff/always_comb 블록 분석 → 클럭 도메인 식별
    - assign 문 분석 → 신호 구동 관계(DRIVES) 추출

    현재는 기존 parse_rtl_to_ast() 폴백 + 확장 필드 빈 값 반환.

    Args:
        rtl_content: RTL 소스 코드 문자열

    Returns:
        parse_rtl_to_ast() 결과에 다음 필드를 추가한 dict:
        - clock_domains: list[dict]   — 클럭 도메인 정보 (Phase 6b)
        - signal_drives: list[dict]   — 신호 구동 관계 (Phase 6b)
        - assign_statements: list[dict] — assign 문 분석 결과 (Phase 6b)
    """
    # TODO: Phase 6b — PyVerilog AST 파서로 교체
    # from pyverilog.vparser.parser import parse as pyverilog_parse
    # from pyverilog.dataflow.dataflow_analyzer import VerilogDataflowAnalyzer

    # TODO: always_ff/always_comb 블록 분석 → 클럭 도메인 식별
    # AST에서 always 블록의 sensitivity list를 파싱하여
    # posedge/negedge 클럭 신호를 추출하고 ClockDomain 노드 생성

    # TODO: assign 문 분석 → 신호 구동 관계(DRIVES) 추출
    # continuous assignment의 LHS/RHS를 파싱하여
    # Signal→Signal DRIVES 엣지를 Neptune에 적재

    # 현재는 기존 정규식 파서를 폴백으로 사용
    result = parse_rtl_to_ast(rtl_content)

    # Phase 6b 확장 필드 (빈 값으로 초기화)
    result["clock_domains"] = []       # list[dict]: {"name": str, "frequency": str, "signals": list[str]}
    result["signal_drives"] = []       # list[dict]: {"source": str, "target": str, "type": str}
    result["assign_statements"] = []   # list[dict]: {"lhs": str, "rhs": str, "line": int}

    return result


# ---------------------------------------------------------------------------
# 텍스트 요약 생성
# ---------------------------------------------------------------------------

def generate_parsed_summary(metadata: dict) -> str:
    """파싱된 메타데이터를 텍스트 요약으로 변환.
    모듈 선언부 + 포트 선언부만 포함 (원본 RTL 소스 전체 미포함).
    """
    lines = []
    module_name = metadata.get("module_name", "unknown")
    lines.append(f"module {module_name}")

    params = metadata.get("parameter_list", [])
    if params:
        lines.append("parameters: " + ", ".join(params))

    ports = metadata.get("port_list", [])
    if ports:
        lines.append("ports: " + ", ".join(ports))

    instances = metadata.get("instance_list", [])
    if instances:
        lines.append("instances: " + ", ".join(instances))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 토큰 Truncation (tiktoken BPE 기반)
# ---------------------------------------------------------------------------

def truncate_to_tokens(text: str, max_tokens: int = MAX_TOKENS) -> str:
    """Titan Embeddings v2 입력 제한(8,192 토큰) 대응.
    tiktoken 사용 가능 시 BPE 기반, 불가 시 문자 수 기반 fallback.
    """
    if _TIKTOKEN_AVAILABLE:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            tokens = enc.encode(text)
            if len(tokens) <= max_tokens:
                return text
            return enc.decode(tokens[:max_tokens])
        except Exception as e:
            logger.warning(json.dumps({"event": "truncation_fallback", "error": str(e)}))
    # fallback: 문자 수 기반 (보수적 추정: 1 토큰 ≈ 3.5자)
    char_limit = max_tokens * 3
    return text[:char_limit]


# ---------------------------------------------------------------------------
# Titan Embeddings v2 호출
# ---------------------------------------------------------------------------

def _generate_embedding(text: str) -> Optional[list]:
    """Titan Embeddings v2로 벡터 임베딩 생성 (1024 dim)."""
    try:
        body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
        response = bedrock_runtime.invoke_model(
            modelId=TITAN_MODEL_ID,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result.get("embedding")
    except Exception as e:
        logger.error(json.dumps({"event": "embedding_error", "error": str(e)}))
        return None


# ---------------------------------------------------------------------------
# OpenSearch 인덱싱
# ---------------------------------------------------------------------------

# Global buffer for batch processing within a single file
_INDEX_BUFFER = []  # List of (metadata, embed_text) — embedding은 flush에서 병렬 생성


def _index_to_opensearch(metadata: dict, embedding_or_text):
    """문서를 buffer에 추가. flush에서 병렬 임베딩 + 배치 인덱싱.

    Args:
        metadata: 문서 메타데이터
        embedding_or_text: 이미 생성된 embedding(list) 또는 임베딩할 텍스트(str).
                          str이면 flush에서 병렬로 임베딩 생성.
                          list이면 그대로 사용.
                          None이면 skip.
    """
    if embedding_or_text is None:
        return
    _INDEX_BUFFER.append((metadata, embedding_or_text))


def _flush_index_buffer():
    """Buffer의 문서들을 병렬 임베딩 + Qdrant 배치 인덱싱.

    v9.5: ThreadPoolExecutor로 Bedrock embedding 10개 병렬 호출.
    500건 순차 500초 → 병렬 50초.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from qdrant_client import batch_index_documents

    if not _INDEX_BUFFER:
        return

    # Phase 1: 임베딩 생성 (병렬)
    # embedding_or_text가 str이면 embed 필요, list이면 이미 완료
    items_to_embed = []  # (index, text)
    embeddings = [None] * len(_INDEX_BUFFER)

    for i, (metadata, eot) in enumerate(_INDEX_BUFFER):
        if isinstance(eot, list):
            embeddings[i] = eot  # 이미 embedding
        elif isinstance(eot, str) and eot:
            items_to_embed.append((i, eot))
        # None or empty → skip

    if items_to_embed:
        with ThreadPoolExecutor(max_workers=EMBED_CONCURRENCY) as executor:
            futures = {}
            for idx, text in items_to_embed:
                truncated = truncate_to_tokens(text, MAX_TOKENS)
                futures[executor.submit(_generate_embedding, truncated)] = idx
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    embeddings[idx] = future.result()
                except Exception:
                    embeddings[idx] = None

    # Phase 2: 배치 Qdrant 인덱싱
    indexed_total = 0
    for i in range(0, len(_INDEX_BUFFER), QDRANT_BATCH_SIZE):
        batch_slice = _INDEX_BUFFER[i:i + QDRANT_BATCH_SIZE]
        points_batch = []
        for j, (metadata, _) in enumerate(batch_slice):
            emb = embeddings[i + j]
            if not emb:
                continue
            payload = {
                "module_name": metadata.get("module_name", ""),
                "parent_module": metadata.get("parent_module", ""),
                "port_list": " ".join(metadata.get("port_list", [])) if isinstance(metadata.get("port_list"), list) else metadata.get("port_list", ""),
                "parameter_list": " ".join(metadata.get("parameter_list", [])) if isinstance(metadata.get("parameter_list"), list) else metadata.get("parameter_list", ""),
                "instance_list": " ".join(metadata.get("instance_list", [])) if isinstance(metadata.get("instance_list"), list) else metadata.get("instance_list", ""),
                "file_path": metadata.get("file_path", ""),
                "parsed_summary": metadata.get("parsed_summary", "") or "",
                "pipeline_id": metadata.get("pipeline_id", ""),
                "analysis_type": metadata.get("analysis_type", "module_parse"),
                "claim_text": metadata.get("claim_text", ""),
                "claim_type": metadata.get("claim_type", ""),
                "claim_id": metadata.get("claim_id", ""),
                "topic": metadata.get("topic", ""),
                "parent_module_name": metadata.get("parent_module_name", ""),
                "sub_record_type": metadata.get("sub_record_type", ""),
                "parser_source": metadata.get("parser_source", ""),
                "edge_type": metadata.get("edge_type", ""),
                "src": metadata.get("src", ""),
                "dst": metadata.get("dst", ""),
                "category": metadata.get("category", ""),
                "raw_text": metadata.get("raw_text", ""),
            }
            points_batch.append((payload, emb))
        if points_batch:
            indexed_total += batch_index_documents(points_batch)

    # DynamoDB claim 저장
    for metadata, _ in _INDEX_BUFFER:
        _store_claim_to_dynamodb(metadata)

    logger.info(json.dumps({
        "event": "flush_index_buffer",
        "total_items": len(_INDEX_BUFFER),
        "indexed": indexed_total,
        "parallel_embeds": len(items_to_embed),
    }))
    _INDEX_BUFFER.clear()


def _store_claim_to_dynamodb(metadata: dict):
    """Claim을 DynamoDB Claim DB에 저장 (status=verified, approval_status=approved).

    HDD 자동 생성 시 verified+approved claim만 사용하므로,
    파서가 생성한 structural claim은 자동 승인 처리한다.
    """
    if not CLAIM_DB_TABLE:
        return

    # claim 필드가 없으면 저장하지 않음 (module_parse 레코드는 제외)
    claim_text = metadata.get("claim_text", "")
    if not claim_text:
        return

    try:
        from datetime import datetime, timezone
        from botocore.config import Config
        import uuid

        # DynamoDB VPC endpoint 미설정 환경 대비: 짧은 timeout (graceful degradation)
        ddb_config = Config(connect_timeout=3, read_timeout=5, retries={'max_attempts': 0})
        ddb_resource = boto3.resource('dynamodb', region_name='ap-northeast-2', config=ddb_config)
        table = ddb_resource.Table(CLAIM_DB_TABLE)
        now = datetime.now(timezone.utc).isoformat()

        claim_id = metadata.get("claim_id") or str(uuid.uuid4())
        item = {
            "claim_id": claim_id,
            "version": 1,
            "is_latest": True,
            "claim_text": claim_text,
            "claim_type": metadata.get("claim_type", "structural"),
            "topic": metadata.get("topic", ""),
            "module_name": metadata.get("module_name", ""),
            "file_path": metadata.get("file_path", ""),
            "pipeline_id": metadata.get("pipeline_id", ""),
            "parser_source": metadata.get("parser_source", ""),
            "status": "verified",
            "approval_status": "approved",
            "approved_by": "system:auto_approve",
            "approved_at": now,
            "last_verified_at": now,
            "created_at": now,
            "created_by": "system:rtl_parser",
        }

        table.put_item(Item=item)
    except Exception as e:
        logger.warning(json.dumps({
            "event": "claim_db_write_error",
            "error": str(e),
            "claim_id": metadata.get("claim_id", ""),
        }))


# ---------------------------------------------------------------------------
# Neptune Graph DB 관계 적재
# ---------------------------------------------------------------------------

def _load_to_neptune(metadata: dict):
    """파싱된 메타데이터에서 관계를 추출하여 Neptune Graph DB에 노드/엣지로 적재.

    노드 타입: Module, Port, Signal, Parameter, ClockDomain
    엣지 타입: INSTANTIATES, HAS_PORT, CONNECTS_TO, DRIVES, PROPAGATES_TO, BELONGS_TO_DOMAIN

    SigV4 IAM DB 인증을 사용하며, Neptune 엔드포인트 미설정 또는 연결 실패 시
    경고 로그만 남기고 파이프라인을 중단하지 않는다.
    """
    # Neptune 엔드포인트 미설정 시 조용히 건너뜀
    if not NEPTUNE_ENDPOINT:
        logger.debug("NEPTUNE_ENDPOINT not set, skipping Neptune loading")
        return

    try:
        import requests
        from requests_aws4auth import AWS4Auth

        session = boto3.Session()
        credentials = session.get_credentials().get_frozen_credentials()
        region = session.region_name or "ap-northeast-2"
        auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region,
            "neptune-db",
            session_token=credentials.token,
        )

        neptune_url = f"https://{NEPTUNE_ENDPOINT}:8182/openCypher"
        module_name = metadata.get("module_name", "")
        file_path = metadata.get("file_path", "")

        if not module_name:
            logger.warning("module_name이 비어있어 Neptune 적재를 건너뜁니다")
            return

        # openCypher 쿼리 배치 구성
        queries = []

        # (a) Module 노드 생성 (MERGE로 중복 방지)
        queries.append({
            "query": (
                "MERGE (m:Module {name: $name}) "
                "SET m.file_path = $file_path"
            ),
            "parameters": {"name": module_name, "file_path": file_path},
        })

        # (b) Port 노드 + HAS_PORT 엣지 생성
        for port_entry in metadata.get("port_list", []):
            # port_entry 형식: "direction name" (예: "input clk")
            parts = port_entry.split(None, 1)
            if len(parts) == 2:
                direction, port_name = parts
            else:
                direction, port_name = "", port_entry
            queries.append({
                "query": (
                    "MERGE (m:Module {name: $module_name}) "
                    "MERGE (p:Port {name: $port_name, module: $module_name}) "
                    "SET p.direction = $direction "
                    "MERGE (m)-[:HAS_PORT]->(p)"
                ),
                "parameters": {
                    "module_name": module_name,
                    "port_name": port_name,
                    "direction": direction,
                },
            })

        # (c) Parameter 노드 + PROPAGATES_TO 엣지 준비
        for param_entry in metadata.get("parameter_list", []):
            # param_entry 형식: "NAME=VALUE" (예: "DATA_WIDTH=32")
            if "=" in param_entry:
                param_name, default_value = param_entry.split("=", 1)
            else:
                param_name, default_value = param_entry, ""
            queries.append({
                "query": (
                    "MERGE (m:Module {name: $module_name}) "
                    "MERGE (p:Parameter {name: $param_name, module: $module_name}) "
                    "SET p.default_value = $default_value "
                    "MERGE (m)-[:HAS_PORT]->(p)"
                ),
                "parameters": {
                    "module_name": module_name,
                    "param_name": param_name.strip(),
                    "default_value": default_value.strip(),
                },
            })

        # (d) Instance → INSTANTIATES 엣지 생성
        for inst_entry in metadata.get("instance_list", []):
            # inst_entry 형식: "instance_name: module_type" (예: "u_phy: UCIE_PHY")
            if ": " in inst_entry:
                _inst_name, inst_module_type = inst_entry.split(": ", 1)
            else:
                continue
            queries.append({
                "query": (
                    "MERGE (m:Module {name: $module_name}) "
                    "MERGE (t:Module {name: $target_module}) "
                    "MERGE (m)-[:INSTANTIATES {instance_name: $instance_name}]->(t)"
                ),
                "parameters": {
                    "module_name": module_name,
                    "target_module": inst_module_type.strip(),
                    "instance_name": _inst_name.strip(),
                },
            })

        # 배치 실행 — 개별 쿼리 실패 시 나머지 계속 처리
        success_count = 0
        fail_count = 0
        for q in queries:
            try:
                resp = requests.post(
                    neptune_url,
                    auth=auth,
                    json=q,
                    timeout=10,
                )
                resp.raise_for_status()
                success_count += 1
            except Exception as qe:
                fail_count += 1
                logger.warning(json.dumps({
                    "event": "neptune_query_error",
                    "query": q.get("query", "")[:100],
                    "error": str(qe),
                }))

        logger.info(json.dumps({
            "event": "neptune_load_complete",
            "module_name": module_name,
            "queries_success": success_count,
            "queries_failed": fail_count,
        }))

    except Exception as e:
        # Neptune 적재 실패는 파이프라인을 중단하지 않음
        logger.error(json.dumps({
            "event": "neptune_load_error",
            "module_name": metadata.get("module_name", ""),
            "error": str(e),
        }))


# ---------------------------------------------------------------------------
# Neptune CONNECTS_TO 엣지 적재 — Port Binding (v9.3, Requirements 31.1~31.8)
# ---------------------------------------------------------------------------

def _load_port_bindings_to_neptune(bindings: list, module_name: str):
    """포트 바인딩 데이터를 Neptune Graph DB에 CONNECTS_TO 엣지로 적재.

    각 바인딩에 대해:
    - Port 노드 생성/MERGE: {instance_name}.{port_name}
    - Signal 노드 생성/MERGE: signal_expr
    - CONNECTS_TO 엣지 생성: Port → Signal
    - concatenation 바인딩: 대표 Signal + constituent_signals 보조 엣지

    SigV4 IAM DB 인증을 사용하며, Neptune 엔드포인트 미설정 또는 연결 실패 시
    경고 로그만 남기고 S3/OpenSearch 인덱싱은 계속 수행한다.

    Args:
        bindings: _find_all_port_bindings()가 반환한 바인딩 dict 목록
        module_name: 현재 파싱 중인 모듈명 (Signal scope로 사용)
    """
    if not NEPTUNE_ENDPOINT:
        logger.debug("NEPTUNE_ENDPOINT not set, skipping port binding Neptune loading")
        return

    if not bindings:
        return

    try:
        import requests
        from requests_aws4auth import AWS4Auth

        session = boto3.Session()
        credentials = session.get_credentials().get_frozen_credentials()
        region = session.region_name or "ap-northeast-2"
        auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region,
            "neptune-db",
            session_token=credentials.token,
        )

        neptune_url = f"https://{NEPTUNE_ENDPOINT}:8182/openCypher"

        # openCypher 쿼리 배치 구성
        queries = []

        for binding in bindings:
            instance_name = binding.get("instance_name", "")
            module_type = binding.get("module_type", "")
            port_name = binding.get("port_name", "")
            signal_expr = binding.get("signal_expr", "")
            bit_range = binding.get("bit_range")
            is_unconnected = binding.get("is_unconnected", False)
            is_concatenation = binding.get("is_concatenation", False)
            constituent_signals = binding.get("constituent_signals", [])
            source_file = binding.get("source_file", "")
            line_number = binding.get("line_number", 0)

            # Unconnected 포트는 CONNECTS_TO 엣지 불필요
            if is_unconnected:
                continue

            # Port 노드 ID: {instance_name}.{port_name}
            port_node_id = f"{instance_name}.{port_name}"

            # (a) Port 노드 생성/MERGE (Req 31.2, 31.8)
            queries.append({
                "query": (
                    "MERGE (p:Port {name: $port_node_id}) "
                    "SET p.instance_name = $instance_name, "
                    "p.module_type = $module_type, "
                    "p.port_name = $port_name, "
                    "p.direction = $direction, "
                    "p.width = $width"
                ),
                "parameters": {
                    "port_node_id": port_node_id,
                    "instance_name": instance_name,
                    "module_type": module_type,
                    "port_name": port_name,
                    "direction": "unknown",
                    "width": bit_range if bit_range else "",
                },
            })

            # (b) Signal 노드 생성/MERGE (Req 31.3)
            queries.append({
                "query": (
                    "MERGE (s:Signal {name: $signal_name, scope: $scope}) "
                    "SET s.width = $width"
                ),
                "parameters": {
                    "signal_name": signal_expr,
                    "scope": module_name,
                    "width": bit_range if bit_range else "",
                },
            })

            # (c) CONNECTS_TO 엣지 생성: Port → Signal (Req 31.1, 31.4)
            queries.append({
                "query": (
                    "MATCH (p:Port {name: $port_node_id}) "
                    "MATCH (s:Signal {name: $signal_name, scope: $scope}) "
                    "MERGE (p)-[r:CONNECTS_TO]->(s) "
                    "SET r.bit_range = $bit_range, "
                    "r.source_file = $source_file, "
                    "r.line_number = $line_number, "
                    "r.is_concatenation = $is_concatenation"
                ),
                "parameters": {
                    "port_node_id": port_node_id,
                    "signal_name": signal_expr,
                    "scope": module_name,
                    "bit_range": bit_range if bit_range else "",
                    "source_file": source_file,
                    "line_number": line_number,
                    "is_concatenation": is_concatenation,
                },
            })

            # (d) Concatenation 바인딩: constituent_signals 보조 엣지 (Req 31.5)
            if is_concatenation and constituent_signals:
                for constituent in constituent_signals:
                    # 보조 Signal 노드 생성/MERGE
                    queries.append({
                        "query": (
                            "MERGE (s:Signal {name: $signal_name, scope: $scope}) "
                            "SET s.width = $width"
                        ),
                        "parameters": {
                            "signal_name": constituent,
                            "scope": module_name,
                            "width": "",
                        },
                    })
                    # 보조 CONNECTS_TO 엣지 (is_constituent=true)
                    queries.append({
                        "query": (
                            "MATCH (p:Port {name: $port_node_id}) "
                            "MATCH (s:Signal {name: $signal_name, scope: $scope}) "
                            "MERGE (p)-[r:CONNECTS_TO]->(s) "
                            "SET r.bit_range = $bit_range, "
                            "r.source_file = $source_file, "
                            "r.line_number = $line_number, "
                            "r.is_concatenation = $is_concatenation, "
                            "r.is_constituent = $is_constituent"
                        ),
                        "parameters": {
                            "port_node_id": port_node_id,
                            "signal_name": constituent,
                            "scope": module_name,
                            "bit_range": "",
                            "source_file": source_file,
                            "line_number": line_number,
                            "is_concatenation": True,
                            "is_constituent": True,
                        },
                    })

        # 배치 실행 — 개별 쿼리 실패 시 나머지 계속 처리
        success_count = 0
        fail_count = 0
        for q in queries:
            try:
                resp = requests.post(
                    neptune_url,
                    auth=auth,
                    json=q,
                    timeout=10,
                )
                resp.raise_for_status()
                success_count += 1
            except Exception as qe:
                fail_count += 1
                logger.warning(json.dumps({
                    "event": "neptune_port_binding_query_error",
                    "query": q.get("query", "")[:100],
                    "error": str(qe),
                }))

        logger.info(json.dumps({
            "event": "neptune_port_bindings_load_complete",
            "module_name": module_name,
            "bindings_processed": len([b for b in bindings if not b.get("is_unconnected", False)]),
            "queries_success": success_count,
            "queries_failed": fail_count,
        }))

    except Exception as e:
        # Neptune 적재 실패 시 graceful degradation (Req 31.6)
        # S3/OpenSearch 인덱싱은 계속 수행
        logger.error(json.dumps({
            "event": "neptune_port_bindings_load_error",
            "neptune_load_failed": True,
            "module_name": module_name,
            "error": str(e),
        }))


# ---------------------------------------------------------------------------
# DynamoDB 파싱 완료 이벤트 기록
# ---------------------------------------------------------------------------

def _record_parse_event(pipeline_id: str, module_name: str, file_path: str):
    """DynamoDB rag-extraction-tasks 테이블에 파싱 완료 이벤트 기록."""
    try:
        table = dynamodb.Table(DYNAMODB_EXTRACTION_TABLE)
        task_id = f"parse_{pipeline_id}_{module_name}"
        table.put_item(Item={
            "task_id": task_id,
            "pipeline_id": pipeline_id,
            "status": "parsed",
            "module_name": module_name,
            "file_path": file_path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.error(json.dumps({
            "event": "parse_event_record_failed",
            "pipeline_id": pipeline_id,
            "module_name": module_name,
            "error": str(e),
        }))


# ---------------------------------------------------------------------------
# 에러 기록
# ---------------------------------------------------------------------------

def _record_error(file_path: str, reason: str):
    """파싱 실패 에러를 DynamoDB 에러 테이블에 기록."""
    try:
        table = dynamodb.Table(ERROR_TABLE_NAME)
        table.put_item(Item={
            "file_path": file_path,
            "error_time": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        })
    except Exception as e:
        logger.error(json.dumps({"event": "error_record_failed", "error": str(e)}))
    logger.error(json.dumps({
        "event": "rtl_parse_error",
        "file_path": file_path,
        "reason": reason,
    }))
