# Enhanced RAG Optimization 테스트 리포트

**테스트일**: 2026년 4월 10일
**브랜치**: `feature/enhanced-rag-optimization`
**환경**: dev (ap-northeast-2 / us-east-1)
**테스터**: Kiro + seungil.woo

---

## 1. 인프라 배포 (Terraform Apply)

| 항목 | 결과 | 비고 |
|------|------|------|
| `terraform init` | ✅ 성공 | backend.tf에서 `profile = "default"` 제거 필요 (SSO 호환) |
| `terraform plan` | ✅ 성공 | SG 이름 `sg-` prefix 제거 필요 (`rtl-parser-lambda-sg-dev`) |
| `terraform apply` | ⚠️ 부분 성공 | 71 add, 10 change — 4개 에러 발생 후 재적용 완료 |

### Apply 에러 및 해결

| 에러 | 원인 | 해결 |
|------|------|------|
| OpenSearch Access Policy 형식 | `Principal`이 Rules 내부에 있었음 | 최상위 레벨로 이동 |
| RTL S3 버킷 정책 AccessDenied | `DenyNonVPCEndpointAccess`가 Terraform 자신도 차단 | Deny 구문 제거 + 버킷 이름 변경 (`rtl-codes` → `rtl-src`) |
| S3 Replication 대상 버킷 없음 | Virginia RTL 버킷 미생성 | `count = 0`으로 비활성화 |
| IAM Policy ARN 형식 오류 | `foundation_model_arn`이 inference profile ID였음 | 정식 ARN으로 수정 |

### 잠긴 S3 버킷

`bos-ai-rtl-codes-533335672315` — VPC Endpoint 전용 Deny 정책으로 루트 계정 포함 모든 접근 차단됨.
Terraform state에서 제거 후 새 버킷(`bos-ai-rtl-src-533335672315`)으로 대체.
잠긴 버킷은 비어있으며 비용 없음. 루트 계정으로 추후 정리 필요.

---

## 2. Phase 1: RTL 파이프라인 테스트

### 테스트 파일
```verilog
module BLK_UCIE #(parameter DATA_WIDTH = 32, ADDR_WIDTH = 8)(
    input clk, rst_n, [DATA_WIDTH-1:0] tx_data, tx_valid,
    output tx_ready, [DATA_WIDTH-1:0] rx_data, rx_valid, input rx_ready
);
    UCIE_PHY u_phy (...);
    RX_BUFFER u_rx_buf (...);
endmodule
```

| 테스트 | 결과 | 비고 |
|--------|------|------|
| S3 업로드 (`rtl-sources/blk_ucie_test.v`) | ✅ 성공 | |
| Lambda 자동 트리거 (S3 Event) | ✅ 성공 | Duration: 2114ms, Memory: 112MB/2048MB |
| RTL 파싱 결과 | ✅ 성공 | module_name=BLK_UCIE, port_count=8, instance_count=2 |
| Parsed JSON 저장 (`rtl-parsed/`) | ✅ 성공 | 358 bytes |
| OpenSearch 인덱싱 | ❌ 403 Forbidden | AOSS 데이터 액세스 정책 권한 확인 필요 |
| Neptune 적재 | ⏭️ 스킵 | Neptune 미배포 |

### 파싱 결과 JSON
```json
{
  "module_name": "BLK_UCIE",
  "port_list": ["input clk", "input rst_n", "input tx_data", "input tx_valid",
                "output tx_ready", "output rx_data", "output rx_valid", "input rx_ready"],
  "parameter_list": ["DATA_WIDTH=32", "ADDR_WIDTH=8"],
  "instance_list": ["u_phy: UCIE_PHY", "u_rx_buf: RX_BUFFER"],
  "file_path": "rtl-sources/blk_ucie_test.v"
}
```

---

## 3. Phase 2: Claim DB 테스트

| 테스트 | 결과 | 비고 |
|--------|------|------|
| Claim 생성 (POST /rag/claims) | ✅ 201 | claim_id=cc003ca0..., version=1, status=draft |
| 상태 전이 (draft → verified) | ✅ 200 | version=2, status=verified |
| DynamoDB Claim DB 테이블 | ✅ 정상 | bos-ai-claim-db-dev, 5 GSI, PITR, KMS |

---

## 4. Phase 3: MCP Tool + Verification Pipeline 테스트

| 테스트 | 결과 | 비고 |
|--------|------|------|
| Health Check (GET /rag/health) | ✅ 200 | version=2.0.0, healthy |
| list-verified-claims | ✅ 200 | ucie/phy topic, 1건 반환 |
| get-evidence | ✅ 200 | evidence 배열 + chunk_hash 정상 |
| Verification Pipeline (POST /rag/query) | ❌ 504 Timeout | Bedrock API 호출 타임아웃 |

---

## 5. Phase 4~6: 미테스트 (Bedrock 연결 + Neptune 배포 후 진행 예정)

---

## 6. 발견된 이슈 및 TODO

### 코드 수정 완료
1. `handler.py` tiktoken import try/except ✅
2. `index.py` UpdateExpression 중복 제거 ✅
3. `index.py` version sort key → put_item 방식 ✅

### Terraform 반영 필요
4. Lambda SG DynamoDB egress 규칙 추가
5. Virginia RTL 대상 버킷 생성 → Replication 활성화
6. OpenSearch AOSS 권한 확인
7. Lambda VPC → Bedrock VPC Endpoint 네트워크 확인

### 인프라 정리
8. 잠긴 S3 버킷 `bos-ai-rtl-codes-533335672315` 루트 계정으로 삭제

---

## 7. 테스트 요약

| Phase | 성공 | 실패 | 스킵 |
|-------|------|------|------|
| Phase 1 RTL 파이프라인 | 4 | 1 | 1 |
| Phase 2 Claim DB | 3 | 0 | 0 |
| Phase 3 MCP Tool | 3 | 1 | 1 |
| Phase 4~6 | 0 | 0 | 14 |
| **합계** | **10** | **2** | **16** |


---

## 8. 추가 디버깅 (2026-04-13)

### Verification Pipeline 504 원인 분석

| 단계 | 문제 | 해결 |
|------|------|------|
| 1. DNS 해석 | `bedrock-runtime` 포워딩 규칙 없음 | Route53 Resolver Rule 추가 ✅ |
| 2. VPC Endpoint 정책 | inference profile 리소스 미허용 | 정책 Resource `*`로 확장 ✅ |
| 3. 모델 비활성화 | `claude-3-5-haiku-20241022-v1:0` Legacy (30일 미사용) | ❌ 활성 모델로 업데이트 필요 |

### 다음 액션
- Bedrock Console에서 활성 모델 확인
- Lambda `FOUNDATION_MODEL_ARN` 환경변수 업데이트
- Verification Pipeline 재테스트
