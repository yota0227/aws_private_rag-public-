# RAG v9.5 Addendum A 배포 런북 (used_in_n1 boost + OpenSearch→Qdrant 단일화)

> **Created:** 2026-06-12
> **Updated:** 2026-06-12
> **Purpose:** v9.5 Addendum A(Req 18 used_in_n1 임베딩 boost, Req 19 RTL OpenSearch 제거+Qdrant 단일화+Full 재인덱싱) 코드 변경을 운영 환경에 안전하게 배포하기 위한 순서·검증·롤백 절차.
> **Spec / Project:** `.kiro/specs/rag-v9.5-knowledge-import/` (Addendum A)
> **Status:** In Review
> **Owner:** Infra/DevOps

## 0. 코드 반영 현황 (배포 전 — 완료)

| 영역 | 파일 | 변경 | 검증 |
|------|------|------|------|
| RTL 파서 | `rtl_parser_src/handler.py` | `_index_to_qdrant` 리네이밍, `_is_used_in_n1` 태깅, `USED_IN_N1_BOOST` 2.0x boost | 79+ passed |
| Qdrant 클라이언트 | `rtl_parser_src/qdrant_client.py` | payload 3곳 `used_in_n1`, `delete_by_filter` 추가 | — |
| 분석 핸들러 | `rtl_parser_src/analysis_handler.py` | backfill→no-op, clear_index→`delete_by_filter`, chip_config→`_scroll_query` (NameError 버그 수정) | 41 passed |
| PBT | `rtl_parser_src/test_used_in_n1_pbt.py` | Property 15/16 | 7 passed |
| terraform | `lambda.tf`, `opensearch.tf` | KEEP/DECOMMISSION 주석 (fmt 정규화) | fmt OK |
| 빌드 | `scripts/build_rtl_parser_package.ps1` | 소스→zip 동기화 스크립트 (임시 .tmp_update_zip.ps1 폐기) | 26 files synced |

- **배포 패키지:** `rtl-parser-deployment-package.zip` 소스 동기화 완료 (analysis_handler/handler/qdrant_client 모두 마이그레이션 버전 확인).
- **RTL python 경로 raw OpenSearch 코드 = 0.**

## 1. 배포 순서 (배포 창에서 실행)

### Step 1 — Lambda 코드 배포 (rtl-parser)
```powershell
# (코드 재변경 시) 소스→zip 동기화
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_rtl_parser_package.ps1
```
```bash
cd environments/app-layer/bedrock-rag
terraform plan -target="aws_lambda_function.rtl_parser"
# plan diff 확인: rtl_parser 함수의 source_code_hash 변경만 기대 (env/IAM 변경 없음)
terraform apply -target="aws_lambda_function.rtl_parser" -auto-approve
```
- **확인:** Lambda 콘솔에서 코드 갱신 시각, env에 `QDRANT_ENDPOINT`/`USED_IN_N1_BOOST`(미설정 시 기본 2.0) 확인.
- `USED_IN_N1_BOOST`를 조정하려면 rtl-parser-lambda.tf env에 추가 (선택).

### Step 2 — terraform 주석/정렬 반영 (선택, 무위험)
```bash
terraform plan   # lambda.tf/opensearch.tf 는 주석+fmt만 → 리소스 변경 0 기대
terraform apply  # 변경 없음이면 skip 가능
```

### Step 3 — Full 재인덱싱 (Task 29, 비용 주의)
```bash
# 비용 제어: reserved concurrency 10~20, batch 15 (handler 기본값)
py scripts/reindex_all_rtl.py --pipeline-id tt_20260516 --batch-size 50
# 완료 후
py scripts/reindex_all_rtl.py --pipeline-id tt_20260221 --batch-size 50
```
- **목표:** 전 레코드에 `used_in_n1` 필드 채워짐. `tt_20260516`(N1 대상) 우선.
- **모니터:** CloudWatch `flush_index_buffer` 로그의 `used_in_n1_count`, `reindex_progress` files_done==files_total.
- **재시작 안전:** idempotent upsert(claim_id sha256) — 중단 후 재실행 가능.

### Step 4 — Qdrant 단독 동작 검증 (Task 30 게이트)
- MCP `search_rtl`로 대표 질의 (module/port/signal). 결과가 Qdrant 소스인지 확인.
- `used_in_n1` boost 동작: N1 부분집합 모듈(예: `used_in_n1/` 경로 모듈)이 상위 랭크되는지 샘플 확인.
- 잔존 OpenSearch RTL 참조 grep = 0 재확인.
- **게이트:** 이 검증 통과 전 Step 5 진행 금지.

### Step 5 — RTL AOSS 인프라 decommission (Task 31, 비가역 — 게이트 통과 후)
```bash
# opensearch.tf 의 aws_opensearchserverless_access_policy.rtl_index 제거
terraform plan   # rtl_index 정책 destroy + Bedrock KB/document-processor 리소스 무변경 확인
terraform apply
```
- **반드시 확인:** `bos-ai-vectors` 컬렉션, `bos-ai-documents` 인덱스, document-processor `lambda_opensearch` IAM 은 **destroy 대상 아님**.
- AOSS `rtl-knowledge-base-index` 자체 삭제는 데이터플레인 작업 (정책 제거 후 별도).

## 2. 롤백

| 단계 | 롤백 방법 |
|------|----------|
| Step 1 (Lambda 코드) | 이전 zip으로 복원 후 `terraform apply -target`, 또는 git revert 후 재빌드 |
| Step 3 (재인덱싱) | Qdrant는 idempotent — 부분 적재는 재실행으로 수렴. 데이터 손상 시 해당 pipeline_id `delete_by_filter` 후 재인덱싱 |
| Step 5 (decommission) | **비가역** — 게이트(Step 4) 통과 전 절대 실행 금지. 정책은 terraform 재적용으로 복구 가능하나 인덱스 데이터는 복구 불가 |

## 3. 검증 경계 (정직 고지)

- 현재까지 **단위 테스트만 통과**. 실제 Qdrant 적재·boost 효과는 Step 1+3 후 Step 4에서 최초 확인된다.
- `terraform plan`은 AWS 자격증명·backend 접근이 필요하며 본 런북 작성 시점엔 미실행. 배포 창에서 plan diff를 반드시 눈으로 확인할 것.
