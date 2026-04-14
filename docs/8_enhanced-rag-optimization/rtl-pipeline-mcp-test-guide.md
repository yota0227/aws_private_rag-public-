# RTL 파이프라인 + MCP 연결 테스트 가이드

**작성일**: 2026-04-14
**대상 환경**: dev (ap-northeast-2 / us-east-1)
**Account**: 533335672315

---

## 인프라 현황

| 항목 | 리소스명 | 상태 |
|------|---------|------|
| RTL S3 버킷 | `bos-ai-rtl-src-533335672315` | ✅ 배포됨 |
| RTL Parser Lambda | `lambda-rtl-parser-seoul-dev` (2048MB, 300s) | ✅ 배포됨 |
| S3 Event Notification | `rtl-sources/` → Lambda 트리거 | ✅ 동작 확인 |
| RTL 파싱 + parsed JSON | `rtl-parsed/*.parsed.json` | ✅ 동작 확인 |
| Titan Embeddings v2 | 1024 dim 벡터 생성 | ✅ 동작 확인 |
| OpenSearch 인덱싱 | `rtl-knowledge-base-index` (AOSS us-east-1) | ✅ 동작 확인 (4/14 수정) |
| Main Lambda | `lambda-document-processor-seoul-prod` | ✅ 배포됨 |
| API Gateway | `r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag` | ✅ 배포됨 |
| Claim DB | `bos-ai-claim-db-dev` (DynamoDB, 5 GSI) | ✅ 배포됨 |
| MCP Bridge | `mcp-bridge/server.js` (localhost:3100) | ✅ 코드 준비됨 |
| Neptune | 미배포 | ⏭️ Phase 6 |
| CloudWatch Monitoring VPC Endpoint | 미배포 | ⚠️ graceful degradation 중 |

### 4/14 수정 사항 (OpenSearch 403 → 성공)

| 문제 | 원인 | 수정 |
|------|------|------|
| 403 Forbidden | SigV4 서명 리전이 `ap-northeast-2` (Lambda 실행 리전)였음 | `BEDROCK_REGION` 환경변수(`us-east-1`)로 변경 |
| 400 Bad Request | AOSS는 `PUT /{index}/_doc/{id}` (문서 ID 지정) 미지원 | `POST /{index}/_doc` (ID 자동 생성)으로 변경 |
| AOSS 데이터 액세스 정책 | `seungil.woo` IAM 사용자 미포함 | `rtl-index-access-dev` 정책에 추가 |

---

## Step 1: RTL 코드 업로드

### 단일 파일

```bash
aws s3 cp your_module.v \
  s3://bos-ai-rtl-src-533335672315/rtl-sources/your_module.v \
  --region ap-northeast-2
```

### 디렉토리 일괄 업로드

```bash
aws s3 sync ./rtl_codes/ \
  s3://bos-ai-rtl-src-533335672315/rtl-sources/ \
  --region ap-northeast-2 \
  --exclude "*" --include "*.v" --include "*.sv"
```

- `./rtl_codes/` 하위의 모든 서브디렉토리 구조가 그대로 유지되며 `.v`, `.sv` 파일만 업로드됨
- 예: `./rtl_codes/ucie/blk_ucie.v` → `s3://.../rtl-sources/ucie/blk_ucie.v`
- 업로드 즉시 S3 Event → `lambda-rtl-parser-seoul-dev` 자동 트리거

### 주의사항

- `rtl-sources/` 접두사 필수 (이 접두사에만 S3 Event Notification 설정됨)
- Object Lock(Governance 모드) 적용 — 업로드 후 365일간 삭제/덮어쓰기 보호
- 동일 파일 재업로드 시 새 버전 생성 + Lambda 재트리거 (OpenSearch에 중복 문서 생성될 수 있음)

---

## Step 2: 파싱 결과 확인

### Lambda 실행 로그

```bash
aws logs tail /aws/lambda/lambda-rtl-parser-seoul-dev \
  --since 5m --region ap-northeast-2 --format short
```

성공 시 로그:
```
{"event": "rtl_parse_start", "bucket": "bos-ai-rtl-src-533335672315", "key": "rtl-sources/blk_ucie.v"}
{"event": "opensearch_indexed", "file_path": "rtl-sources/blk_ucie.v"}
{"event": "rtl_parse_success", "key": "rtl-sources/blk_ucie.v", "module_name": "BLK_UCIE", "port_count": 8, "instance_count": 2}
```

### parsed JSON 확인

```bash
# 목록
aws s3 ls s3://bos-ai-rtl-src-533335672315/rtl-parsed/ --region ap-northeast-2

# 내용 확인
aws s3 cp s3://bos-ai-rtl-src-533335672315/rtl-parsed/blk_ucie.v.parsed.json - \
  --region ap-northeast-2
```

### 파싱 결과 예시

```json
{
  "module_name": "BLK_UCIE",
  "port_list": ["input clk", "input rst_n", "input tx_data", ...],
  "parameter_list": ["DATA_WIDTH=32", "ADDR_WIDTH=8"],
  "instance_list": ["u_phy: UCIE_PHY", "u_rx_buf: RX_BUFFER"],
  "file_path": "rtl-sources/blk_ucie.v"
}
```

---

## Step 3: MCP Bridge 실행

온프레미스 Obot 서버(192.128.20.241)에서:

```bash
cd mcp-bridge
npm install          # 최초 1회
export RAG_API_BASE="https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag"
npm start            # localhost:3100
```

### 등록된 MCP 도구 목록

| 도구 | 설명 | API 엔드포인트 |
|------|------|---------------|
| `rag_query` | RAG 질의 (Verification Pipeline 우선) | POST /rag/query |
| `rag_list_documents` | 업로드된 문서 목록 | GET /rag/documents |
| `search_archive` | Archive 검색 (topic/source 필터) | POST /rag/search-archive |
| `get_evidence` | Claim evidence 조회 | POST /rag/get-evidence |
| `list_verified_claims` | 검증된 Claim 목록 | POST /rag/list-verified-claims |
| `generate_hdd_section` | HDD 섹션 자동 생성 | POST /rag/generate-hdd |
| `publish_markdown` | 마크다운 출판 | POST /rag/publish-markdown |
| `rag_delete_document` | 문서 삭제 | POST /rag/documents/delete |

---

## Step 4: API 직접 테스트 (curl)

### 헬스체크

```bash
curl -s https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag/health | jq .
```

### RAG 질의 (Verification Pipeline)

```bash
curl -s -X POST \
  https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "BLK_UCIE 모듈의 입력 포트 목록은?"}' | jq .
```

응답에서 확인:
- `verification_metadata.claims_used` — 사용된 claim ID
- `verification_metadata.fallback` — `true`면 Bedrock KB 폴백
- `verification_metadata.has_conflicts` — 충돌 여부

### Claim 생성

```bash
curl -s -X POST \
  https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag/claims \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "ucie/phy",
    "statement": "BLK_UCIE 모듈은 DATA_WIDTH=32, ADDR_WIDTH=8 파라미터를 가진다",
    "evidence": [{
      "source_document_id": "rtl-sources/blk_ucie.v",
      "source_chunk": "module BLK_UCIE #(parameter DATA_WIDTH = 32, ADDR_WIDTH = 8)",
      "extraction_date": "2026-04-14T00:00:00Z",
      "source_type": "rtl",
      "source_path": "module declaration",
      "chunk_hash": ""
    }],
    "confidence": 0.95
  }' | jq .
```

### 검증된 Claim 목록

```bash
curl -s -X POST \
  https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag/list-verified-claims \
  -H "Content-Type: application/json" \
  -d '{"topic": "ucie/phy"}' | jq .
```

### Archive 검색

```bash
curl -s -X POST \
  https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag/search-archive \
  -H "Content-Type: application/json" \
  -d '{"query": "UCIE PHY module ports", "topic": "ucie/phy"}' | jq .
```

---

## Step 5: Obot MCP 도구 테스트

Obot 채팅에서 자연어로 테스트:

| 테스트 | 질의 예시 | 기대 도구 |
|--------|----------|----------|
| 기본 RAG 질의 | "BLK_UCIE 모듈의 입력 포트 목록 알려줘" | `rag_query` |
| Archive 검색 | "ucie/phy topic의 문서 검색해줘" | `search_archive` |
| Claim 조회 | "ucie/phy topic의 검증된 claim 목록 보여줘" | `list_verified_claims` |
| Evidence 조회 | "claim ID cc003ca0의 근거 보여줘" | `get_evidence` |
| 문서 목록 | "업로드된 문서 목록 보여줘" | `rag_list_documents` |
| HDD 생성 | "ucie/phy topic으로 HDD 섹션 생성해줘" | `generate_hdd_section` |

---

## 남은 이슈

| # | 이슈 | 우선순위 | 상태 |
|---|------|---------|------|
| 1 | OpenSearch 인덱싱 403/400 | 높음 | ✅ 해결 (4/14) |
| 2 | CloudWatch Monitoring VPC Endpoint | 중간 | ⚠️ graceful degradation 중 |
| 3 | Neptune 미배포 | 낮음 | ⏭️ Phase 6 |
| 4 | 잠긴 S3 버킷 정리 (`bos-ai-rtl-codes-533335672315`) | 낮음 | 루트 계정으로 삭제 필요 |
| 5 | Virginia RTL 대상 버킷 미생성 → CRR 비활성 | 낮음 | `count = 0` 상태 |
| 6 | 동일 파일 재업로드 시 OpenSearch 중복 문서 | 낮음 | AOSS 제약 (file_path 필드로 관리) |

---

## 파이프라인 전체 흐름

```
엔지니어
  ↓ aws s3 cp *.v s3://bos-ai-rtl-src-.../rtl-sources/
RTL S3 Bucket (Seoul)
  ↓ S3 Event Notification
RTL Parser Lambda (Seoul, 2048MB)
  ├→ parse_rtl_to_ast() 정규식 파싱
  ├→ rtl-parsed/*.parsed.json 저장 (S3)
  ├→ Titan Embeddings v2 벡터 생성 (Virginia Bedrock)
  ├→ OpenSearch Serverless 인덱싱 (Virginia AOSS)
  └→ [Phase 6] Neptune Graph DB 적재

사용자 (Obot)
  ↓ MCP SSE (localhost:3100)
MCP Bridge (Node.js)
  ↓ HTTPS
API Gateway (Seoul, Private REST)
  ↓
Lambda Handler (Seoul)
  ├→ Verification Pipeline (Claim DB 우선)
  ├→ Bedrock KB 폴백 (overrideSearchType)
  └→ 답변 + verification_metadata + citations
```
