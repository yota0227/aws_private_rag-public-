# RTL 코드 대량 업로드 및 임베딩 가이드

**작성일**: 2026-04-07  
**대상**: 반도체 설계 엔지니어, DevOps 팀  
**전제 조건**: enhanced-rag-optimization 스펙 Phase 1 구현 완료

---

## 1. 개요

RTL 소스 코드를 BOS-AI RAG 시스템에 업로드하면, 자동으로 구조적 메타데이터가 추출되고 벡터 임베딩으로 변환되어 AI 검색이 가능해집니다.

기존 일반 문서(md, pdf 등)와 달리, RTL 코드는 **전용 파이프라인**을 통해 처리됩니다:

```
RTL 파일 업로드
    ↓
RTL 전용 S3 버킷 (bos-ai-rtl-codes-533335672315)
    ↓ S3 Event Notification (자동)
RTL Parser Lambda (정규식 기반 파싱)
    ├─ 메타데이터 추출: module_name, port_list, parameter_list, instance_list
    ├─ 파싱 결과 저장: rtl-parsed/{파일명}.parsed.json
    └─ Titan Embeddings v2로 벡터 임베딩 생성
        ↓
RTL 전용 OpenSearch 인덱스 (rtl-knowledge-base-index)
    ↓
AI 검색 가능 상태
```

**일반 문서 업로드와의 차이:**

| 항목 | 일반 문서 | RTL 코드 |
|------|----------|---------|
| 업로드 방법 | 웹 UI | AWS CLI (S3 직접 업로드) |
| S3 버킷 | bos-ai-documents-seoul-v3 | bos-ai-rtl-codes-533335672315 |
| 처리 방식 | Bedrock KB 자동 임베딩 | RTL Parser Lambda → OpenSearch |
| 메타데이터 | 팀/카테고리 | module_name, port_list 등 구조적 메타데이터 |
| 검색 인덱스 | bedrock-knowledge-base-default-index | rtl-knowledge-base-index |
| 보안 | S3 버전 관리 | Object Lock (Governance 모드) |

---

## 2. 업로드 방법

### 2.1 사전 준비

RTL 업로드는 웹 UI가 아닌 **AWS CLI**를 사용합니다. 사내 네트워크(VPN)에 연결된 상태에서 진행하세요.

```bash
# AWS CLI 설치 확인
aws --version

# 자격 증명 확인
aws sts get-caller-identity
```

### 2.2 단일 파일 업로드

```bash
aws s3 cp ./blk_ucie.v \
  s3://bos-ai-rtl-codes-533335672315/rtl-sources/blk_ucie.v \
  --region ap-northeast-2
```

업로드 즉시 S3 Event가 발생하여 RTL Parser Lambda가 자동 트리거됩니다.

### 2.3 디렉토리 단위 대량 업로드

```bash
# Verilog/SystemVerilog 파일만 업로드
aws s3 cp ./rtl-codes/ \
  s3://bos-ai-rtl-codes-533335672315/rtl-sources/ \
  --recursive \
  --exclude "*" \
  --include "*.v" --include "*.sv" --include "*.svh" --include "*.vh" \
  --region ap-northeast-2

# 신규/변경 파일만 동기화 (권장)
aws s3 sync ./rtl-codes/ \
  s3://bos-ai-rtl-codes-533335672315/rtl-sources/ \
  --exclude "*" \
  --include "*.v" --include "*.sv" --include "*.svh" --include "*.vh" \
  --region ap-northeast-2
```

### 2.4 하위 디렉토리 구조 유지

프로젝트 디렉토리 구조를 그대로 유지하면서 업로드할 수 있습니다:

```
로컬:                              S3:
rtl-codes/                         rtl-sources/
├── ucie/                          ├── ucie/
│   ├── blk_ucie.v                 │   ├── blk_ucie.v
│   ├── ucie_phy.v                 │   ├── ucie_phy.v
│   └── ucie_ctrl.v                │   └── ucie_ctrl.v
├── ahb/                           ├── ahb/
│   ├── ahb_master.v               │   ├── ahb_master.v
│   └── ahb_slave.v                │   └── ahb_slave.v
└── top/                           └── top/
    └── soc_top.v                      └── soc_top.v
```

### 2.5 업로드 진행 상황 확인

```bash
# 업로드된 파일 수
aws s3 ls s3://bos-ai-rtl-codes-533335672315/rtl-sources/ \
  --recursive --region ap-northeast-2 | wc -l

# 파싱 완료된 파일 수
aws s3 ls s3://bos-ai-rtl-codes-533335672315/rtl-parsed/ \
  --recursive --region ap-northeast-2 | wc -l

# 두 숫자가 같으면 모든 파일의 파싱이 완료된 것
```

---

## 3. 파싱 결과 확인

### 3.1 파싱된 JSON 확인

```bash
aws s3 cp \
  s3://bos-ai-rtl-codes-533335672315/rtl-parsed/blk_ucie.v.parsed.json \
  - --region ap-northeast-2 | jq .
```

출력 예시:
```json
{
  "module_name": "BLK_UCIE",
  "parent_module": "",
  "port_list": ["clk", "rst_n", "haddr", "hwdata", "hrdata"],
  "parameter_list": ["DATA_WIDTH=32", "ADDR_WIDTH=16"],
  "instance_list": ["u_phy: UCIE_PHY", "u_ctrl: UCIE_CTRL"],
  "file_path": "rtl-sources/blk_ucie.v",
  "parsed_summary": "module BLK_UCIE (clk, rst_n, haddr[15:0], ...);"
}
```

### 3.2 파싱 실패 확인

```bash
# RTL Parser Lambda ERROR 로그 확인 (최근 1시간)
aws logs filter-log-events \
  --log-group-name /aws/lambda/lambda-rtl-parser-seoul-prod \
  --start-time $(date -v-1H +%s000) \
  --filter-pattern "ERROR" \
  --region ap-northeast-2 \
  --query 'events[*].message' \
  --output text
```

---

## 4. 대량 업로드 시 주의사항

### 4.1 Lambda 동시 실행 제한

S3 Event는 파일 하나당 Lambda 1회 호출을 트리거합니다. 수천 개 파일을 한번에 올리면 Lambda 동시 실행 제한(기본 1000)에 걸릴 수 있습니다.

**권장: 배치 단위로 나눠서 업로드**

```bash
# 500개씩 나눠서 업로드
find ./rtl-codes -name "*.v" -o -name "*.sv" | split -l 500 - /tmp/batch_

for batch in /tmp/batch_*; do
  echo "=== Uploading batch: $batch ==="
  while IFS= read -r file; do
    rel_path="${file#./rtl-codes/}"
    aws s3 cp "$file" \
      "s3://bos-ai-rtl-codes-533335672315/rtl-sources/$rel_path" \
      --region ap-northeast-2 --quiet
  done < "$batch"
  echo "=== Batch done. Waiting 5 minutes... ==="
  sleep 300
done
```

### 4.2 제한 사항

| 항목 | 제한 |
|------|------|
| 단일 파일 최대 크기 | 5GB (S3 제한) |
| Lambda 처리 타임아웃 | 300초 (5분) / 파일 |
| 임베딩 토큰 제한 | 8,000 토큰 (초과 시 자동 truncation) |
| Lambda 메모리 | 2048MB (약 1.2 vCPU) |
| Lambda 동시 실행 | 1000 (기본, 상향 요청 가능) |

### 4.3 지원 파일 형식

| 확장자 | 언어 | 지원 |
|--------|------|------|
| `.v` | Verilog | O |
| `.sv` | SystemVerilog | O |
| `.svh` | SystemVerilog Header | O |
| `.vh` | Verilog Header | O |
| `.vhd` / `.vhdl` | VHDL | X (향후 추가 예정) |

### 4.4 추출되는 메타데이터

| 필드 | 설명 | 예시 |
|------|------|------|
| `module_name` | 모듈명 | `BLK_UCIE` |
| `parent_module` | 상위 모듈명 (없으면 빈 문자열) | `SOC_TOP` |
| `port_list` | 포트 목록 | `["clk", "rst_n", "haddr[15:0]"]` |
| `parameter_list` | 파라미터 목록 | `["DATA_WIDTH=32"]` |
| `instance_list` | 인스턴스 목록 | `["u_phy: UCIE_PHY"]` |
| `file_path` | 원본 S3 경로 | `rtl-sources/ucie/blk_ucie.v` |

원본 RTL 소스 코드 전체는 벡터 DB에 저장되지 않습니다. 모듈 선언부와 포트 선언부의 요약만 임베딩됩니다.

---

## 5. 업로드 후 검색 테스트

업로드 후 약 1~5분이면 검색 가능합니다.

### 5.1 Obot 챗봇에서 테스트

```
질의 예시:
- "BLK_UCIE 모듈의 입력 포트 목록을 알려줘"
- "UCIE_PHY를 인스턴스화하는 모듈은?"
- "DATA_WIDTH 파라미터를 사용하는 모듈 목록"
- "AHB 마스터 모듈의 포트 구성은?"
```

### 5.2 API로 직접 테스트

```bash
curl -X POST http://localhost:3100/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "rag_query",
      "arguments": {
        "query": "BLK_UCIE 모듈의 입력 포트 목록"
      }
    }
  }'
```

---

## 6. Claim 기반 지식 분해 (Phase 2 이후, 선택적)

Phase 2가 구현되면, 파싱된 RTL 메타데이터를 **검증된 지식 단위(Claim)**로 추가 분해할 수 있습니다.

```bash
# Claim ingestion 실행 (Lambda 비동기 호출)
aws lambda invoke \
  --function-name lambda-document-processor-seoul-prod \
  --invocation-type Event \
  --payload '{"action": "ingest_claims", "s3_prefix": "rtl-parsed/"}' \
  --region ap-northeast-2 \
  response.json
```

1회 최대 100건 문서를 처리합니다. `has_more: true`이면 `continuation_token`으로 다음 배치를 실행하세요:

```bash
aws lambda invoke \
  --function-name lambda-document-processor-seoul-prod \
  --invocation-type Event \
  --payload '{
    "action": "ingest_claims",
    "s3_prefix": "rtl-parsed/",
    "continuation_token": "rtl-parsed/last_file.v.parsed.json"
  }' \
  --region ap-northeast-2 \
  response.json
```

---

## 7. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| parsed JSON이 생성되지 않음 | Lambda 트리거 실패 | S3 Event Notification 설정 확인 |
| module_name이 빈 값 | 비표준 모듈 선언 | 정규식 파서 한계, 향후 PyVerilog 통합 예정 |
| CloudWatch에 ERROR 로그 | 파싱 불가능한 구문 | 로그에서 상세 사유 확인 |
| 검색 결과에 안 나옴 | OpenSearch 인덱싱 실패 | 인덱스 상태 확인 |
| Lambda throttling | 동시 실행 제한 초과 | 배치 단위로 나눠서 업로드 |

---

## 8. Quick Reference

```bash
# 업로드
aws s3 sync ./rtl/ s3://bos-ai-rtl-codes-533335672315/rtl-sources/ \
  --exclude "*" --include "*.v" --include "*.sv" --region ap-northeast-2

# 파싱 완료 확인
aws s3 ls s3://bos-ai-rtl-codes-533335672315/rtl-parsed/ --recursive --region ap-northeast-2 | wc -l

# 파싱 결과 확인
aws s3 cp s3://bos-ai-rtl-codes-533335672315/rtl-parsed/module.v.parsed.json - --region ap-northeast-2 | jq .

# 에러 확인
aws logs filter-log-events --log-group-name /aws/lambda/lambda-rtl-parser-seoul-prod \
  --filter-pattern "ERROR" --region ap-northeast-2
```

---

**문의**: IT/DevOps 팀
