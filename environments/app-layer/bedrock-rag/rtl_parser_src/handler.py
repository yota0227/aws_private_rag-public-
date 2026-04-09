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
import tiktoken

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 환경 변수
RTL_S3_BUCKET = os.environ.get("RTL_S3_BUCKET", "")
RTL_OPENSEARCH_ENDPOINT = os.environ.get("RTL_OPENSEARCH_ENDPOINT", "")
RTL_OPENSEARCH_INDEX = os.environ.get("RTL_OPENSEARCH_INDEX", "rtl-knowledge-base-index")
ERROR_TABLE_NAME = os.environ.get("ERROR_TABLE_NAME", "bos-ai-rtl-parse-errors")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
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
    """S3 Event Notification 핸들러"""
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        logger.info(json.dumps({"event": "rtl_parse_start", "bucket": bucket, "key": key}))
        _process_rtl_file(bucket, key)
    return {"statusCode": 200}


def _process_rtl_file(bucket: str, key: str):
    """RTL 파일 처리 메인 로직"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        rtl_content = response["Body"].read().decode("utf-8")
    except Exception as e:
        _record_error(key, f"S3 GetObject 실패: {e}")
        raise

    metadata = parse_rtl_to_ast(rtl_content)
    metadata["file_path"] = key

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

    logger.info(json.dumps({
        "event": "rtl_parse_success",
        "key": key,
        "module_name": metadata.get("module_name", ""),
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

    # 포트 목록 추출 (input/output/inout 선언)
    port_pattern = re.compile(
        r"\b(input|output|inout)\s+(?:wire|reg|logic)?\s*(?:\[[\w\s:\-]+\])?\s*(\w+)", re.MULTILINE
    )
    ports = []
    for m in port_pattern.finditer(content):
        direction = m.group(1)
        name = m.group(2)
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
    RTL 코드는 특수문자([31:0], _, 기호)가 빈번하여 단어 기반 근사는 부정확.
    tiktoken cl100k_base BPE 토크나이저를 보수적 근사로 사용.
    임베딩 API 호출 전 방어적 길이 검사.
    """
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        if len(tokens) <= max_tokens:
            return text
        truncated_tokens = tokens[:max_tokens]
        return enc.decode(truncated_tokens)
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
        region = session.region_name or "us-east-1"
        auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region,
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
        }

        url = f"{RTL_OPENSEARCH_ENDPOINT}/{RTL_OPENSEARCH_INDEX}/_doc/{doc_id}"
        response = requests.put(url, auth=auth, json=doc, timeout=30)
        response.raise_for_status()
        logger.info(json.dumps({"event": "opensearch_indexed", "doc_id": doc_id}))
    except Exception as e:
        logger.error(json.dumps({"event": "opensearch_error", "error": str(e)}))


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
