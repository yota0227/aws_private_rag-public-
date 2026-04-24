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
from datetime import datetime, timezone
from typing import Optional

import boto3

from pipeline_utils import extract_pipeline_id

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
RTL_OPENSEARCH_ENDPOINT = os.environ.get("RTL_OPENSEARCH_ENDPOINT", "")
RTL_OPENSEARCH_INDEX = os.environ.get("RTL_OPENSEARCH_INDEX", "rtl-knowledge-base-index")
ERROR_TABLE_NAME = os.environ.get("ERROR_TABLE_NAME", "bos-ai-rtl-parse-errors")
DYNAMODB_EXTRACTION_TABLE = os.environ.get("DYNAMODB_EXTRACTION_TABLE", "rag-extraction-tasks")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
NEPTUNE_ENDPOINT = os.environ.get("NEPTUNE_ENDPOINT", "")
TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
MAX_TOKENS = 8000

# AWS 클라이언트
s3_client = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
bedrock_runtime = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)


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

        # RTL 파일만 처리 (.v, .sv, .svh)
        if not key.endswith((".v", ".sv", ".svh")):
            continue

        logger.info(json.dumps({"event": "rtl_parse_start", "bucket": bucket, "key": key}))
        _process_rtl_file(bucket, key)
    return {"statusCode": 200}


def _search_rtl(event):
    """RTL OpenSearch 인덱스 검색 — Main Lambda에서 동기 invoke로 호출.

    Supports both text search (query) and filtered search
    (pipeline_id, topic, analysis_type parameters).
    """
    import requests
    from requests_aws4auth import AWS4Auth

    query = event.get("query", "")
    max_results = int(event.get("max_results", 20))

    # 필터링 파라미터
    pipeline_id = event.get("pipeline_id", "")
    topic = event.get("topic", "")
    analysis_type = event.get("analysis_type", "")

    if not RTL_OPENSEARCH_ENDPOINT:
        return {"results": [], "total_hits": 0, "query": query}

    # 텍스트 검색도 필터 파라미터도 없으면 빈 결과
    if not query and not pipeline_id and not topic and not analysis_type:
        return {"results": [], "total_hits": 0, "query": query}

    session = boto3.Session()
    credentials = session.get_credentials()
    aoss_region = os.environ.get("BEDROCK_REGION", "us-east-1")
    auth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        aoss_region,
        "aoss",
        session_token=credentials.token,
    )

    url = f"{RTL_OPENSEARCH_ENDPOINT}/{RTL_OPENSEARCH_INDEX}/_search"

    # 필터 조건 구축 (build_search_query 활용)
    from search_utils import build_search_query

    filter_params = {}
    if pipeline_id:
        filter_params["pipeline_id"] = pipeline_id
    if topic:
        filter_params["topic"] = topic
    if analysis_type:
        filter_params["analysis_type"] = analysis_type

    filter_clauses = []
    if filter_params:
        built = build_search_query(filter_params)
        filter_clauses = built.get("query", {}).get("bool", {}).get("must", [])
        # Remove match_all if present
        filter_clauses = [c for c in filter_clauses if "match_all" not in c]

    if query:
        # 텍스트 검색 + 필터
        should_clauses = [
            {"wildcard": {"module_name": f"*{query}*"}},
            {"wildcard": {"module_name": f"*{query.lower()}*"}},
            {"match": {"parsed_summary": query}},
            {"match": {"port_list": query}},
            {"match": {"instance_list": query}},
            {"match": {"claim_text": query}},
            {"match": {"hdd_content": query}},
        ]
        bool_query: dict = {
            "should": should_clauses,
            "minimum_should_match": 1,
        }
        if filter_clauses:
            bool_query["filter"] = filter_clauses
        search_body = {
            "size": max_results,
            "query": {"bool": bool_query},
            "_source": [
                "module_name", "port_list", "parameter_list",
                "instance_list", "file_path", "parsed_summary",
                "pipeline_id", "topic", "analysis_type",
                "claim_text", "claim_type", "claim_id",
                "hdd_content", "hdd_section_title",
            ],
        }
    else:
        # 필터 전용 검색
        search_body = {
            "size": max_results,
            "query": {"bool": {"must": filter_clauses}} if filter_clauses else {"match_all": {}},
            "_source": [
                "module_name", "port_list", "parameter_list",
                "instance_list", "file_path", "parsed_summary",
                "pipeline_id", "topic", "analysis_type",
                "claim_text", "claim_type", "claim_id",
                "hdd_content", "hdd_section_title",
            ],
        }

    try:
        resp = requests.post(url, auth=auth, json=search_body,
                             headers={"Content-Type": "application/json"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for hit in data.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            results.append({
                "module_name": src.get("module_name", ""),
                "port_list": src.get("port_list", ""),
                "parameter_list": src.get("parameter_list", ""),
                "instance_list": src.get("instance_list", ""),
                "file_path": src.get("file_path", ""),
                "parsed_summary": src.get("parsed_summary", ""),
                "pipeline_id": src.get("pipeline_id", ""),
                "topic": src.get("topic", ""),
                "analysis_type": src.get("analysis_type", ""),
                "claim_text": src.get("claim_text", ""),
                "claim_type": src.get("claim_type", ""),
                "claim_id": src.get("claim_id", ""),
                "hdd_content": src.get("hdd_content", ""),
                "hdd_section_title": src.get("hdd_section_title", ""),
                "score": hit.get("_score", 0),
            })

        total_hits = data.get("hits", {}).get("total", {}).get("value", 0)
        return {"results": results, "total_hits": total_hits, "query": query}

    except Exception as e:
        logger.error(json.dumps({"event": "rtl_search_error", "error": str(e)}))
        return {"results": [], "total_hits": 0, "query": query, "error": str(e)}


def _process_rtl_file(bucket: str, key: str):
    """RTL 파일 처리 메인 로직"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        rtl_content = response["Body"].read().decode("utf-8")
    except Exception as e:
        _record_error(key, f"S3 GetObject 실패: {e}")
        raise

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
    embedding = _generate_embedding(truncated)
    if embedding:
        _index_to_opensearch(metadata, embedding)

    # Neptune Graph DB 관계 적재 (Phase 6)
    _load_to_neptune(metadata)

    # DynamoDB 파싱 완료 이벤트 기록
    module_name = metadata.get("module_name", "unknown")
    _record_parse_event(pipeline_info["pipeline_id"], module_name, key)

    logger.info(json.dumps({
        "event": "rtl_parse_success",
        "key": key,
        "module_name": metadata.get("module_name", ""),
        "pipeline_id": pipeline_info["pipeline_id"],
        "port_count": len(metadata.get("port_list", [])),
        "instance_count": len(metadata.get("instance_list", [])),
    }))


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

def _index_to_opensearch(metadata: dict, embedding: list):
    """파싱된 메타데이터와 임베딩을 RTL OpenSearch Index에 인덱싱."""
    if not RTL_OPENSEARCH_ENDPOINT:
        logger.warning("RTL_OPENSEARCH_ENDPOINT not set, skipping indexing")
        return

    try:
        import requests
        from requests_aws4auth import AWS4Auth

        session = boto3.Session()
        credentials = session.get_credentials()
        # AOSS 컬렉션이 us-east-1에 있으므로 SigV4 서명도 us-east-1로 해야 함
        # Lambda는 ap-northeast-2에서 실행되므로 session.region_name은 사용 불가
        aoss_region = os.environ.get("BEDROCK_REGION", "us-east-1")
        auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            aoss_region,
            "aoss",
            session_token=credentials.token,
        )

        doc_id = hashlib.sha256(metadata["file_path"].encode()).hexdigest()[:16]
        doc = {
            "embedding": embedding,
            "module_name": metadata.get("module_name", ""),
            "parent_module": metadata.get("parent_module", ""),
            "port_list": " ".join(metadata.get("port_list", [])),
            "parameter_list": " ".join(metadata.get("parameter_list", [])),
            "instance_list": " ".join(metadata.get("instance_list", [])),
            "file_path": metadata.get("file_path", ""),
            "parsed_summary": generate_parsed_summary(metadata),
            "pipeline_id": metadata.get("pipeline_id", ""),
            "chip_type": metadata.get("chip_type", ""),
            "snapshot_date": metadata.get("snapshot_date", ""),
            "analysis_type": metadata.get("analysis_type", "module_parse"),
        }

        # AOSS는 PUT /{index}/_doc/{id} (문서 ID 지정)를 지원하지 않음
        # POST /{index}/_doc 사용 (ID 자동 생성)
        url = f"{RTL_OPENSEARCH_ENDPOINT}/{RTL_OPENSEARCH_INDEX}/_doc"
        response = requests.post(url, auth=auth, json=doc, timeout=30)
        if response.status_code not in (200, 201):
            logger.error(json.dumps({
                "event": "opensearch_error_detail",
                "status_code": response.status_code,
                "response_body": response.text[:500],
                "url": url,
            }))
        response.raise_for_status()
        logger.info(json.dumps({"event": "opensearch_indexed", "file_path": metadata.get("file_path", "")}))
    except Exception as e:
        logger.error(json.dumps({"event": "opensearch_error", "error": str(e)}))


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
