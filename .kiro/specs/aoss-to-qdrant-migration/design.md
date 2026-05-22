# Design Document: AOSS → Qdrant Migration Bugfix

## Overview

AOSS(OpenSearch Serverless) 종료 후 Qdrant(EC2)로 벡터 DB를 전환하는 과정에서 남아있는 잔류 의존성을 제거하고, Lambda에서 Qdrant EC2로의 네트워크 경로를 확보하며, 기존 RTL 데이터를 재인덱싱하는 작업의 설계 문서.

---

## 1. Network Fix (Requirement 2.1)

Lambda(Seoul VPC `10.10.0.0/16`) → Qdrant EC2(Virginia VPC `10.20.1.217:6333`) 네트워크 경로 확보.

### 1.1 현재 상태

- Lambda(`lambda-rtl-parser-seoul-dev`, `lambda-document-processor-seoul-prod`)는 Seoul VPC(`10.10.0.0/16`) 내 Private Subnet에 배치
- Qdrant EC2는 Virginia VPC(`10.20.0.0/16`) 내 `10.20.1.217`에서 port 6333으로 서비스
- VPC Peering은 Seoul ↔ Virginia 간 설정되어 있으나, Route Table/SG가 Qdrant 트래픽에 대해 미설정

### 1.2 수정 사항

| 항목 | 설정 | 비고 |
|------|------|------|
| Seoul VPC Route Table | `10.20.0.0/16` → VPC Peering Connection | Lambda Subnet의 Route Table에 추가 |
| Virginia VPC Route Table | `10.10.0.0/16` → VPC Peering Connection | Qdrant EC2 Subnet의 Route Table에 추가 |
| Qdrant EC2 Security Group (Inbound) | TCP 6333, Source: `10.10.0.0/16` | Lambda에서 Qdrant REST API 접근 허용 |
| Lambda Security Group (Outbound) | TCP 6333, Destination: `10.20.0.0/16` (또는 `0.0.0.0/0`) | 기본 all-outbound 허용이면 추가 불필요 |

### 1.3 검증 방법

- Lambda 내부에서 `10.20.1.217:6333`으로 HTTP GET `/collections` 요청 → 200 응답 확인
- VPC Flow Logs로 Seoul → Virginia 방향 6333 트래픽 ACCEPT 확인

### 1.4 Terraform 변경 (environments/network-layer/)

```hcl
# Seoul VPC Route Table에 Virginia CIDR 추가
resource "aws_route" "seoul_to_virginia_qdrant" {
  route_table_id            = aws_route_table.seoul_private.id
  destination_cidr_block    = "10.20.0.0/16"
  vpc_peering_connection_id = aws_vpc_peering_connection.seoul_virginia.id
}

# Qdrant EC2 SG — Lambda CIDR inbound 허용
resource "aws_security_group_rule" "qdrant_from_lambda" {
  type              = "ingress"
  from_port         = 6333
  to_port           = 6333
  protocol          = "tcp"
  cidr_blocks       = ["10.10.0.0/16"]
  security_group_id = aws_security_group.qdrant_ec2.id
  description       = "Allow Qdrant REST API from Seoul Lambda VPC"
}
```

---

## 2. Code Migration — index.py (Requirements 2.2, 2.3)

`lambda_src/index.py` (Document Processor Lambda)에서 AOSS 직접 호출 함수들을 RTL Parser Lambda invoke로 대체.

### 2.1 `_get_pipeline_coverage()` 수정 (Line ~4394)

**Before:** `RTL_OPENSEARCH_ENDPOINT`를 확인하고 `requests_aws4auth`로 AOSS에 직접 aggregation 쿼리

**After:** RTL Parser Lambda를 invoke하여 `action=search` + `analysis_type` 필터로 파이프라인 커버리지 조회

```python
def _get_pipeline_coverage(event):
    """파이프라인 커버리지 조회 — RTL Parser Lambda invoke (Qdrant 기반)"""
    pipeline_id = event.get('pipeline_id', '')
    if not pipeline_id:
        return {'error': 'pipeline_id is required'}

    try:
        rtl_lambda_name = os.environ.get('RTL_PARSER_LAMBDA_NAME', 'lambda-rtl-parser-seoul-dev')
        invoke_payload = {
            'action': 'search',
            'query': f'pipeline_id:{pipeline_id}',
            'filter': {'pipeline_id': pipeline_id},
            'max_results': 100,
            'include_aggregations': True,
        }
        invoke_resp = lambda_client.invoke(
            FunctionName=rtl_lambda_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(invoke_payload),
        )
        data = json.loads(invoke_resp['Payload'].read().decode('utf-8'))
        # aggregation 결과에서 parser_source별 통계 추출
        return _format_coverage_response(data, pipeline_id)
    except Exception as e:
        logger.error(f"Pipeline coverage query failed: {e}")
        return {'error': str(e), 'pipeline_id': pipeline_id}
```

### 2.2 이름 복구 함수 Source ② 수정 (Line ~2268)

**Before:** `if not resolved_name and RTL_OPENSEARCH_ENDPOINT:` 조건으로 AOSS 활성 시에만 검색

**After:** `RTL_OPENSEARCH_ENDPOINT` 조건 제거 → 항상 RTL Parser Lambda invoke 실행

```python
        # Source ②: Qdrant 검색 (RTL Parser Lambda invoke)
        if not resolved_name:
            try:
                rtl_lambda_name = os.environ.get('RTL_PARSER_LAMBDA_NAME', 'lambda-rtl-parser-seoul-dev')
                search_query = token_id.replace('_', ' ')
                invoke_payload = {
                    'action': 'search',
                    'query': search_query,
                    'max_results': 3,
                }
                invoke_resp = lambda_client.invoke(
                    FunctionName=rtl_lambda_name,
                    InvocationType='RequestResponse',
                    Payload=json.dumps(invoke_payload),
                )
                # ... (기존 결과 파싱 로직 유지)
```

### 2.3 제거 대상 import/변수

| 항목 | 파일 | 조치 |
|------|------|------|
| `RTL_OPENSEARCH_ENDPOINT` 변수 선언 | index.py L87 | 삭제 |
| `RTL_OPENSEARCH_INDEX` 변수 선언 | index.py L88 | 삭제 |
| `from requests_aws4auth import AWS4Auth` | index.py L3038, L4400 | 삭제 (Neptune용은 유지) |
| AOSS NOTE 주석 (L83-86) | index.py | 삭제 |

> **주의:** `requests_aws4auth`는 Neptune SigV4 인증에서도 사용 중. Neptune 호출 함수 내부의 `import`는 유지하되, AOSS 전용 호출 함수 내부의 것만 제거.

---

## 3. Re-indexing (Requirement 2.4)

기존 AOSS에 인덱싱되었던 9465건의 RTL 데이터를 Qdrant에 재인덱싱.

### 3.1 재인덱싱 전략

- 기존 `scripts/reindex_all_rtl.py` 스크립트 사용
- S3(`bos-ai-documents-seoul-v3`)에 저장된 RTL 파일을 순회하며 RTL Parser Lambda를 batch invoke
- Lambda timeout 900초 유지 (배치당 50건, 총 ~190 배치)

### 3.2 실행 절차

```bash
# 1. 네트워크 확보 후 Qdrant 연결 테스트
py scripts/test_qdrant_connectivity.py

# 2. 전체 재인덱싱 실행
py scripts/reindex_all_rtl.py --pipeline-id tt_20260221 --batch-size 50

# 3. 인덱싱 완료 확인 (약 10~20분 소요)
# MCP search_rtl 또는 직접 Qdrant API로 document count 확인
```

### 3.3 검증 기준

- Qdrant collection의 point count ≥ 9465
- `search_rtl` 도구로 기존 검색어에 대해 유효한 결과 반환
- Lambda 로그에 `"RTL_OPENSEARCH_ENDPOINT not set, skipping indexing"` 경고 없음

---

## 4. Terraform Cleanup (Requirement 2.5)

AOSS 관련 불필요한 리소스를 제거/비활성화하고, Qdrant 네트워크 설정을 추가.

### 4.1 제거/비활성화 대상

| 리소스 | 파일 | 조치 |
|--------|------|------|
| `RTL_OPENSEARCH_ENDPOINT` Lambda 환경변수 | `environments/app-layer/bedrock-rag/` (Lambda tf) | 삭제 |
| AOSS VPC Endpoint | `environments/network-layer/` 또는 모듈 | 삭제 또는 주석 처리 |
| AOSS IAM Policy (`aoss:APIAccessAll`) | `bedrock-kb.tf` L109 | 검토 후 Bedrock KB 전용이면 유지, RTL 전용이면 삭제 |
| AOSS Collection 관련 리소스 | `modules/ai-workload/bedrock-rag/opensearch.tf` | Bedrock KB가 여전히 AOSS 사용하면 유지; RTL 인덱스 전용 부분만 제거 |

### 4.2 추가 대상

| 리소스 | 파일 | 조치 |
|--------|------|------|
| Qdrant SG ingress rule (6333, 10.10.0.0/16) | `environments/network-layer/` | 추가 (§1.4 참조) |
| Seoul → Virginia route (10.20.0.0/16) | `environments/network-layer/` | 추가 (§1.4 참조) |
| `QDRANT_HOST` Lambda 환경변수 | `environments/app-layer/bedrock-rag/` | 추가 확인 (`10.20.1.217`) |
| `QDRANT_PORT` Lambda 환경변수 | `environments/app-layer/bedrock-rag/` | 추가 확인 (`6333`) |

### 4.3 주의사항

- **Bedrock KB는 여전히 AOSS를 벡터 스토어로 사용** (문서 임베딩/RAG 검색). Bedrock KB 관련 AOSS 리소스는 절대 삭제하지 않는다.
- 제거 대상은 **RTL 인덱싱/검색 전용**으로 사용되던 AOSS 접근 경로에 한정.

---

## 5. handler.py AOSS 잔류 코드 정리

RTL Parser Lambda(`rtl_parser_src/handler.py`)에서 AOSS 잔류 참조 정리.

### 5.1 제거 대상

| 항목 | 위치 | 조치 |
|------|------|------|
| `RTL_OPENSEARCH_ENDPOINT` 환경변수 참조 | handler.py L46 | 삭제 |
| `RTL_OPENSEARCH_INDEX` 환경변수 참조 | handler.py L47 | 삭제 |
| AOSS 직접 호출 함수 (있는 경우) | handler.py | 이미 Qdrant 전환 완료 확인, dead code만 제거 |

### 5.2 유지 대상

| 항목 | 이유 |
|------|------|
| `from requests_aws4auth import AWS4Auth` (Neptune 함수 내부) | Neptune Graph DB는 IAM SigV4 인증 사용 — AOSS와 무관 |
| `NEPTUNE_ENDPOINT` 환경변수 | Neptune 기능 유지 |

### 5.3 확인 사항

- handler.py의 `_index_to_opensearch()` 함수명은 이미 Qdrant 호출로 구현 전환됨 (v9.5 주석 확인)
- 함수명 리네이밍(`_index_to_qdrant`)은 이번 스코프에서 선택 사항 — 기능에 영향 없음

---

## Regression Prevention

변경 후 아래 동작이 영향받지 않음을 검증:

| 검증 항목 | 방법 |
|-----------|------|
| S3 이벤트 → RTL 파싱 → Qdrant 인덱싱 | 새 RTL 파일 업로드 후 Lambda 로그 확인 |
| search-archive RTL 분기 | MCP `search_rtl` 호출로 결과 반환 확인 |
| Neptune Signal Path / Instantiation Tree | `trace_signal_path`, `find_instantiation_tree` API 호출 |
| Bedrock KB S3 → KB 파이프라인 | `trigger_kb_sync()` 정상 동작 확인 |
| API Gateway → Document Processor → RTL Parser 체인 | `/rag/search-archive` 엔드 투 엔드 테스트 |

---

## Implementation Order

1. **Phase 1 — Network** (§1): Route Table + SG 설정 → 연결 테스트
2. **Phase 2 — Code** (§2, §5): index.py AOSS 제거 + handler.py 정리
3. **Phase 3 — Re-index** (§3): 전체 9465건 재인덱싱
4. **Phase 4 — Terraform** (§4): 불필요 리소스 정리 + `terraform plan` 확인
5. **Phase 5 — E2E Test**: 전체 파이프라인 검증
