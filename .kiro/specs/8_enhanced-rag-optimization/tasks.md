# Implementation Plan: Enhanced RAG Optimization

## Overview

BOS-AI Private RAG 시스템을 검증된 지식 단위(Claim) 기반 답변 시스템으로 확장한다. 9개 Phase로 나누어 점진적으로 구현하며, 각 Phase는 이전 Phase의 결과물에 의존한다. Terraform IaC로 AWS 리소스를 관리하고, Python 3.12 Lambda 함수, Node.js MCP Bridge, Go 1.21 + gopter 속성 기반 테스트를 사용한다. Phase 7은 v9 RTL Parser Pipeline Enhancement로, Supply Side 파서 6종 확장, Consumption Side 검색 개선, Generation Side Hybrid Grounding, Quality Infrastructure 파서 기여도 측정을 포함한다. Phase 8은 v9.2 RTL Wiring & Topology Parser로, v9.1 리뷰에서 식별된 5개 잔여 갭(EP Index Table, NOC2AXI dual-row, NoC repeater, clock_routing array, dispatch feedthrough wire)을 해소하여 Content Fidelity 80%+ 달성을 목표로 한다. Phase 9는 v9.3 Port Binding Parser + Schematic Viewer + Merge 개선으로, 포트 바인딩 파서(.port(signal) 매핑 추출), Neptune CONNECTS_TO 엣지 적재, Graph Export API(Neptune → JSON), Interactive Schematic Viewer(3-view: Chip/Module/Signal), HDD merge 개선(실명 복구 + topic→통합본 전파)을 포함하여 Content Fidelity 85~88% 달성을 목표로 한다.

## Tasks

- [x] 1. Phase 1: RTL 파이프라인 및 인프라 격리
  - [x] 1.1 RTL 전용 S3 버킷 Terraform 구성 (`environments/app-layer/bedrock-rag/rtl-s3.tf`)
    - `aws_s3_bucket.rtl_codes` 리소스 생성 (버킷명: `bos-ai-rtl-codes-${account_id}`, Seoul 리전)
    - `object_lock_enabled = true` + Governance 모드 365일 retention
    - 버전 관리(versioning) 활성화
    - KMS CMK 암호화 (기존 BOS-AI KMS 키)
    - Block Public Access 4개 설정 모두 true
    - VPC Endpoint 전용 버킷 정책
    - S3 Event Notification: `rtl-sources/` 접두사 → RTL_Parser_Lambda 트리거
    - Cross-Region Replication: Seoul → Virginia RTL 전용 버킷
    - 필수 태그: Project=BOS-AI, Environment=prod, ManagedBy=terraform, Layer=app
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 12.2_

  - [x]* 1.2 Property 23 테스트 작성: RTL S3 버킷 보안 구성
    - **Property 23: RTL S3 보안 구성**
    - **Validates: Requirements 1.1, 1.2, 1.5, 1.6, 12.2**
    - `tests/properties/enhanced_rag_optimization_test.go`에 작성
    - Object Lock Governance 모드, KMS CMK 암호화, Block Public Access 4개 true, 필수 태그 검증

  - [x] 1.3 RTL Parser Lambda Terraform 구성 (`environments/app-layer/bedrock-rag/rtl-parser-lambda.tf`)
    - Lambda 함수 리소스: Python 3.12, 메모리 2048MB, 타임아웃 300초
    - VPC 구성: BOS-AI Frontend VPC (10.10.0.0/16) 내 실행
    - IAM 역할: RTL_S3_Bucket GetObject(`rtl-sources/*`)/PutObject(`rtl-parsed/*`), OpenSearch 인덱싱, CloudWatch Logs, KMS, Bedrock InvokeModel, DynamoDB PutItem(에러 테이블)
    - 환경 변수 KMS 암호화
    - 필수 태그 적용
    - _Requirements: 2.1, 2.8, 2.10, 13.1, 13.2, 13.4, 13.5, 13.6_

  - [x]* 1.4 Property 24 테스트 작성: RTL Parser Lambda Terraform 구성
    - **Property 24: RTL Parser Lambda 구성**
    - **Validates: Requirements 2.8, 13.1, 13.2**
    - Python 3.12 런타임, 2048MB 메모리, 300초 타임아웃, Frontend VPC, IAM 최소 권한 검증

  - [x] 1.5 RTL Parser Lambda 소스 코드 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/handler.py`)
    - `handler(event, context)`: S3 Event Notification 핸들러
    - `parse_rtl_to_ast(rtl_content: str) -> dict`: 정규식 기반 RTL 파싱 (module_name, parent_module, port_list, parameter_list, instance_list, file_path)
    - `generate_parsed_summary(metadata: dict) -> str`: 메타데이터 텍스트 요약 (모듈 선언부 + 포트 선언부만, 원본 RTL 소스 전체 미포함)
    - `truncate_to_tokens(text: str, max_tokens: int = 8000) -> str`: 8,000 토큰 truncation + 방어적 길이 검사
    - 파싱 결과 JSON을 `rtl-parsed/{원본파일명}.parsed.json`으로 S3 저장
    - Titan Embeddings v2로 벡터 임베딩 변환 후 RTL_OpenSearch_Index에 인덱싱
    - 파싱 실패 시 CloudWatch ERROR 로그 + DynamoDB 에러 테이블에 에러 레코드 저장
    - 원본 RTL 소스 코드 전체를 로그에 기록하지 않음 (파일명과 요약만)
    - 모듈화 구조 유지 (향후 PyVerilog/AST 교체 대비, ECR 컨테이너 마이그레이션 준비)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.10, 2.11, 13.7_

  - [x]* 1.6 Property 1 테스트 작성: RTL 파싱 라운드트립
    - **Property 1: RTL 파싱 라운드트립**
    - **Validates: Requirements 2.2, 2.4, 2.9**
    - 유효한 Verilog/SystemVerilog 모듈 선언에 대해 parse → serialize → re-parse 동일 결과 검증

  - [x]* 1.7 Property 2 테스트 작성: 토큰 Truncation 상한
    - **Property 2: 토큰 Truncation 상한**
    - **Validates: Requirements 2.11**
    - 임의 텍스트에 대해 truncate_to_tokens 출력이 8,000 토큰 이하, 짧은 입력은 동일 출력 검증

  - [x]* 1.8 Property 3 테스트 작성: RTL 파싱 실패 에러 레코드
    - **Property 3: RTL 파싱 실패 에러 레코드**
    - **Validates: Requirements 2.6, 2.7**
    - 파싱 불가 콘텐츠에 대해 에러 레코드 생성 + parsed_summary에 원본 전체 미포함 검증

  - [x] 1.9 OpenSearch 데이터 액세스 정책 Terraform 구성 (`environments/app-layer/bedrock-rag/opensearch.tf` 수정)
    - RTL_Parser_Lambda IAM 역할에 인덱싱 권한 부여
    - Bedrock_KB 서비스 프린시펄에 검색 권한 부여
    - 기존 문서 인덱스와 RTL 인덱스 독립 유지
    - _Requirements: 3.1, 3.5, 3.6_

  - [x] 1.10 RTL OpenSearch 인덱스 생성 스크립트 (`scripts/create-opensearch-index.py`)
    - SigV4 인증(`requests-aws4auth`)으로 OpenSearch Serverless 접근
    - `rtl-knowledge-base-index` 인덱스 생성
    - 필드 매핑: embedding(knn_vector, 1024, faiss, l2), module_name(keyword), parent_module(keyword), port_list(text), parameter_list(text), instance_list(text), file_path(keyword), parsed_summary(text)
    - _Requirements: 3.2, 3.3, 3.4_

  - [x]* 1.11 Property 4 테스트 작성: RTL OpenSearch 인덱스 매핑 완전성
    - **Property 4: OpenSearch 인덱스 매핑 완전성**
    - **Validates: Requirements 3.3, 3.4**
    - 8개 필드 존재 및 올바른 타입, knn_vector dimension=1024, engine=faiss, space_type=l2 검증

  - [x] 1.12 IAM Explicit Deny 정책 구성 (`environments/app-layer/bedrock-rag/lambda.tf` 수정)
    - Lambda_Handler IAM 역할에 Explicit Deny 정책 추가
    - Seoul_S3 `documents/*` 접두사에 대한 `s3:PutObject`, `s3:DeleteObject`, `s3:DeleteObjectVersion`, `s3:BypassGovernanceRetention`, `s3:PutObjectRetention` 거부
    - RTL_S3_Bucket `rtl-sources/*` 접두사에 대한 동일 5개 액션 거부
    - _Requirements: 12.1, 13.9_

  - [x]* 1.13 Property 22 테스트 작성: IAM Explicit Deny
    - **Property 22: IAM Explicit Deny로 Source of Truth 보호**
    - **Validates: Requirements 13.9**
    - Lambda_Handler IAM 정책에 Source of Truth 버킷 PutObject/DeleteObject/DeleteObjectVersion/BypassGovernanceRetention/PutObjectRetention Explicit Deny 존재 검증

- [x] 2. Phase 1 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - `cd environments/app-layer/bedrock-rag && terraform validate`
  - `cd tests && go test -v ./properties/ -run TestEnhancedRagOptimization -count=1` (Phase 1 관련 테스트)


- [x] 3. Phase 2: Claim DB 구축 및 Ingestion 파이프라인
  - [x] 3.1 Claim DB DynamoDB 테이블 Terraform 구성 (`environments/app-layer/bedrock-rag/claim-db.tf`)
    - 테이블명: `bos-ai-claim-db-prod`, 파티션 키: `claim_id`(S), 정렬 키: `version`(N)
    - 5개 GSI: `topic-index`, `status-index`, `topic-variant-index`, `source-document-index`, `family-index`
    - PAY_PER_REQUEST 과금 모드
    - Point-in-Time Recovery(PITR) 활성화
    - KMS CMK 암호화
    - Claim_DB 접근을 Lambda_Handler IAM 역할로만 제한 (PutItem/GetItem/UpdateItem/Query/Scan)
    - 필수 태그 적용
    - _Requirements: 4.1, 4.2, 4.5, 4.6, 4.7, 13.3, 13.4, 13.6_

  - [x]* 3.2 Property 5 테스트 작성: Claim_DB Terraform 구성 완전성
    - **Property 5: Claim_DB Terraform 구성 완전성**
    - **Validates: Requirements 4.1, 4.2, 4.5, 4.6, 4.7**
    - PK/SK, 5 GSI 키 스키마, PAY_PER_REQUEST, PITR, KMS CMK 검증

  - [x] 3.3 Claim CRUD 함수 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `create_claim()`: evidence 최소 1개 검증(HTTP 400), confidence 0.0~1.0 검증(HTTP 400), topic 계층적 형식 검증, statement 10~500자 검증, source_chunk 10~1000자 검증, chunk_hash SHA-256 생성, status=draft/version=1 초기화, optimistic locking
    - `update_claim_status()`: 6가지 허용 전이만 수행(불허 시 HTTP 409), optimistic locking(`version = :expected_version`), ConditionalCheckFailedException 최대 3회 재시도, deprecated 전이 시 하위 claim cascading(status→conflicted)
    - `get_evidence()`: claim_id로 evidence 배열 반환
    - `list_verified_claims()`: topic-index GSI 사용, status=verified 필터
    - 동일 topic verified claim과 contradiction_score 계산, 0.7 이상 시 기존 claim status→conflicted + derived_from 기록
    - approval_status 필드 지원: verified 전이 시 pending_review 설정
    - _Requirements: 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 14.1, 14.2_

  - [x]* 3.4 Property 6 테스트 작성: Claim 필드 유효성 검증
    - **Property 6: Claim 필드 유효성 검증**
    - **Validates: Requirements 5.1, 5.6, 5.7, 7.2**
    - evidence 빈 배열 거부, confidence 범위, topic 형식, statement 길이, source_chunk 길이 검증

  - [x]* 3.5 Property 7 테스트 작성: Claim 상태 전이 규칙
    - **Property 7: Claim 상태 전이 규칙**
    - **Validates: Requirements 5.2, 5.3**
    - 6가지 허용 전이 성공, 불허 전이 HTTP 409, 초기 status=draft 검증

  - [x]* 3.6 Property 8 테스트 작성: Claim 버전 불변성
    - **Property 8: Claim 버전 불변성**
    - **Validates: Requirements 5.4**
    - 업데이트 시 version+1, 이전 version 레코드 유지(삭제 안 됨) 검증

  - [x]* 3.7 Property 9 테스트 작성: Optimistic Locking 동시성 제어
    - **Property 9: Optimistic Locking 동시성 제어**
    - **Validates: Requirements 5.9, 5.10**
    - ConditionExpression 포함, ConditionalCheckFailedException 시 최대 3회 재시도 검증

  - [x]* 3.8 Property 10 테스트 작성: Contradiction Score 기반 상태 변경
    - **Property 10: Contradiction Score 기반 상태 변경**
    - **Validates: Requirements 5.5, 5.8**
    - contradiction_score >= 0.7 시 기존 claim conflicted + derived_from 기록, deprecated cascading 검증

  - [x] 3.9 문서 Ingestion 분리 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - 문서 업로드 시 `topic`, `variant`(기본값 "default"), `doc_version`(기본값 "1.0") 파라미터 수용
    - 메타데이터 파일에 topic/variant/doc_version/source 필드 추가
    - 동일 topic+variant에 새 doc_version 업로드 시 이전 버전 메타데이터에 `superseded_by` 추가
    - topic 필터 질의 시 해당 topic 문서만 검색, 최신 doc_version 우선
    - `source` 필드 허용 값: archive_md, rtl_parsed, codebeamer, manual_upload, system_generated
    - 파일 경로에서 topic 자동 추출 (예: `documents/soc/ucie/phy_spec.md` → `ucie/phy`)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x]* 3.10 Property 13 테스트 작성: 문서 메타데이터 확장 구조
    - **Property 13: 문서 메타데이터 확장 구조**
    - **Validates: Requirements 6.2, 6.5**
    - topic/variant/doc_version/source 필드 존재 및 기본값, source 허용 값 검증

  - [x]* 3.11 Property 14 테스트 작성: 파일 경로에서 Topic 자동 추출
    - **Property 14: 파일 경로에서 Topic 자동 추출**
    - **Validates: Requirements 6.6**
    - documents/{team}/{category}/{filename} 형식에서 유효한 계층적 topic 생성 검증

  - [x] 3.12 Claim Ingestion 파이프라인 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `ingest_claims()`: Lambda Event 비동기 호출, S3 문서 → Foundation_Model로 claim 분해
    - statement: LLM 재구성 정규화 1문장(10~500자), evidence.source_chunk: 원본 정확 인용(10~1000자)
    - 각 claim을 Claim_DB에 status=draft, version=1로 저장
    - 1회 최대 100건 문서 처리, has_more + continuation_token 페이지네이션
    - 개별 문서 LLM 실패 시 건너뛰고 계속 처리, documents_failed 증가
    - 응답: documents_processed, claims_created, documents_failed
    - `handler()` 라우팅에 `action == 'ingest_claims'` 분기 추가
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x]* 3.13 Property 15 테스트 작성: Claim Ingestion 페이지네이션 및 카운팅
    - **Property 15: Ingestion 페이지네이션 및 카운팅**
    - **Validates: Requirements 7.3, 7.4, 7.7**
    - 100건 상한, 응답 필드 존재, has_more 시 continuation_token, 신규 claim status=draft/version=1 검증

- [x] 4. Phase 2 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - `terraform validate` 실행
  - Claim CRUD 함수 및 Ingestion 파이프라인 동작 확인


- [x] 5. Phase 3: MCP Tool 분리 및 Verification Pipeline
  - [x] 5.1 MCP Tool API 엔드포인트 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `search_archive()`: query(필수) + topic/source/max_results(선택) → Bedrock_KB 검색 + 필터
    - `handler()` 라우팅에 POST `/rag/search-archive`, `/rag/get-evidence`, `/rag/list-verified-claims` 추가
    - 잘못된 파라미터 시 HTTP 400 + 누락/잘못된 파라미터 명시
    - API Gateway에 3개 라우트 추가 (`environments/app-layer/bedrock-rag/api-gateway.tf` 수정)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 5.2 MCP Bridge 도구 확장 (`mcp-bridge/server.js` 수정)
    - `search_archive` 도구 추가: query(필수), topic/source/max_results(선택) → POST /rag/search-archive
    - `get_evidence` 도구 추가: claim_id(필수) → POST /rag/get-evidence
    - `list_verified_claims` 도구 추가: topic(필수) → POST /rag/list-verified-claims
    - 모든 도구 응답에 `execution_time_ms` 필드 포함
    - _Requirements: 8.1, 8.2, 8.3, 8.6_

  - [x]* 5.3 Property 21 테스트 작성: MCP Tool 응답 실행 시간 포함
    - **Property 21: MCP Tool 응답 실행 시간 포함**
    - **Validates: Requirements 8.6**
    - 모든 MCP Tool 응답에 execution_time_ms 존재 및 양의 정수 검증

  - [x] 5.4 Verification Pipeline 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `verification_pipeline(query, variant=None)`: 8단계 순차 실행
    - (1) 질문 수신 → (2) Foundation_Model로 topic 식별(최대 3개) → (3) topic-index GSI로 verified claim 조회 → (4) evidence 근거 추적 → (5) 충돌 검사(conflicted claim 존재 시 경고) → (6) 버전 확인(is_latest=true) → (7) Foundation_Model로 답변 생성 → (8) evidence 첨부
    - variant 파라미터 포함 시 topic-variant-index GSI 사용
    - Claim_DB에 관련 claim 없으면 Bedrock_KB 폴백 (fallback=true)
    - 응답에 verification_metadata 포함: claims_used, topics_identified, has_conflicts, pipeline_execution_time_ms, fallback
    - 각 단계 실행 시간 CloudWatch 구조화 로그 기록
    - 기존 `handle_query()` 수정: Verification Pipeline 우선 실행, 폴백 시 기존 Bedrock_KB 검색
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_

  - [x]* 5.5 Property 16 테스트 작성: Verification Pipeline 응답 구조
    - **Property 16: Verification Pipeline 응답 구조**
    - **Validates: Requirements 9.2, 9.3, 9.6, 9.7**
    - verification_metadata 필드 존재, topics_identified 최대 3개, claim 없으면 fallback=true, verified claim만 사용 검증

  - [x]* 5.6 Property 17 테스트 작성: 충돌 경고 포함
    - **Property 17: 충돌 경고 포함**
    - **Validates: Requirements 9.4**
    - conflicted claim 존재 시 has_conflicts=true + 답변에 충돌 경고 메시지 포함 검증

  - [x] 5.7 3계층 RAG 분리 IAM 역할 구성 (`environments/app-layer/bedrock-rag/lambda.tf` 수정)
    - RTL_Parser_Lambda: RTL_S3_Bucket 읽기 + RTL_OpenSearch_Index 쓰기만
    - Lambda_Handler: Seoul_S3 읽기/쓰기 + Claim_DB 읽기/쓰기 + Bedrock_KB 호출만
    - CloudWatch PutMetricData 권한 추가 (BOS-AI/ClaimDB 네임스페이스)
    - 단방향 데이터 흐름 보장: Source_of_Truth → Verified_Knowledge → Serving
    - _Requirements: 12.3, 12.4, 12.5, 12.6, 15.8_

- [x] 6. Phase 3 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - MCP Bridge 도구 3개 + Verification Pipeline 통합 동작 확인


- [x] 7. Phase 4: 문서 생성 및 Human Review Gate
  - [x] 7.1 Human Review Gate 함수 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `approve_claim()`: claim_id + version + approved_by → approval_status='approved', approved_at 설정
    - `reject_claim()`: claim_id + version + rejected_by + rejection_reason(선택) → approval_status='rejected'
    - `handler()` 라우팅에 POST `/rag/claims/approve`, `/rag/claims/reject` 추가
    - API Gateway에 2개 라우트 추가 (`environments/app-layer/bedrock-rag/api-gateway.tf` 수정)
    - publishable 계산: status='verified' AND approval_status='approved'인 경우만 true
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.6_

  - [x]* 7.2 Property 18 테스트 작성: Human Review Gate 승인 생명주기
    - **Property 18: Human Review Gate 승인 생명주기**
    - **Validates: Requirements 14.2, 14.3, 14.4, 14.5, 14.6, 14.7**
    - verified 전이 시 pending_review, approve 시 approved, reject 시 rejected, publishable 조건, 미승인 claim HTTP 403 검증

  - [x] 7.3 HDD 섹션 생성 및 마크다운 출판 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `generate_hdd_section()`: topic의 verified+approved claim 조회 → Foundation_Model로 HDD 마크다운 생성
    - evidence 각주 포함 (include_evidence=true), 면책 조항 자동 포함
    - `publish_markdown()`: Seoul_S3 `published/` 접두사에 저장, 메타데이터 자동 생성(source='system_generated')
    - critical topic claim은 approval_status='approved'만 사용, 미승인 시 HTTP 403
    - `handler()` 라우팅에 POST `/rag/generate-hdd`, `/rag/publish-markdown` 추가
    - API Gateway에 2개 라우트 추가
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 14.5, 14.7_

  - [x] 7.4 MCP Bridge 문서 생성 도구 확장 (`mcp-bridge/server.js` 수정)
    - `generate_hdd_section` 도구 추가: topic(필수), section_title(필수), include_evidence(선택, 기본 true) → POST /rag/generate-hdd
    - `publish_markdown` 도구 추가: content(필수), filename(필수), topic(선택) → POST /rag/publish-markdown
    - 모든 도구 응답에 `execution_time_ms` 포함
    - _Requirements: 10.1, 10.4_

- [x] 8. Phase 4 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - Human Review Gate + HDD 생성 + 마크다운 출판 통합 동작 확인


- [x] 9. Phase 5: Cross-Check 파이프라인 및 KPI 모니터링
  - [x] 9.1 Cross-Check 파이프라인 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `cross_check_claims()`: Lambda Event 비동기 호출, 지정 topic의 draft claim 대상
    - 1차: Foundation_Model로 claim 정확성 평가 → score_1 (0.0~1.0)
    - 2차: 다른 프롬프트 템플릿으로 재검증 → score_2 (0.0~1.0)
    - 3차: rule-based checker → score_3 (evidence S3 존재 확인, statement 10~500자, topic 형식 유효)
    - `validation_risk_score = 1.0 - (score_1 * 0.4 + score_2 * 0.4 + score_3 * 0.2)`
    - < 0.3 → verified + confidence 업데이트, 0.3~0.7 → draft 유지 + 수동 검토 경고, >= 0.7 → conflicted + ERROR 로그
    - 동일 topic verified claim 간 유사도 0.9 이상 → 중복 판정, 최신만 verified 유지, 이전 deprecated
    - 응답: claims_verified, claims_conflicted, claims_pending, total_processed
    - `handler()` 라우팅에 `action == 'cross_check_claims'` 분기 추가
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10_

  - [x]* 9.2 Property 11 테스트 작성: Validation Risk Score 계산 및 상태 전이
    - **Property 11: Validation Risk Score 계산 및 상태 전이**
    - **Validates: Requirements 11.5, 11.6, 11.7, 11.8**
    - 공식 정확성, 임계값별 상태 전이(< 0.3 verified, 0.3~0.7 draft, >= 0.7 conflicted) 검증

  - [x]* 9.3 Property 12 테스트 작성: Rule-Based Checker 검증
    - **Property 12: Rule-Based Checker 검증**
    - **Validates: Requirements 11.4**
    - S3 존재 확인, statement 길이, topic 형식 검증 → 모두 통과 시 score_3=1.0, 실패 시 < 1.0 검증

  - [x]* 9.4 Property 19 테스트 작성: Cross-Check 결과 카운팅 일관성
    - **Property 19: Cross-Check 결과 카운팅 일관성**
    - **Validates: Requirements 11.9**
    - claims_verified + claims_conflicted + claims_pending == total_processed 검증

  - [x] 9.5 KPI Metrics 발행 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `publish_kpi_metrics()`: CloudWatch 커스텀 메트릭 발행 (네임스페이스: BOS-AI/ClaimDB)
    - ClaimIngestionSuccessRate: ingest_claims 완료 시 발행
    - ClaimVerificationPassRate + ContradictionDetectionRate: cross_check_claims 완료 시 발행
    - BedrockKBFallbackRate: Verification Pipeline 폴백 시 증가
    - AvgEvidenceCountPerAnswer: Verification Pipeline 답변 생성 시 발행
    - StaleClaimRatio: 30일 미검증 verified claim 비율 (질의 처리 시 또는 스케줄)
    - TopicCoverageRatio: verified claim 존재 topic 비율 (질의 처리 시 또는 스케줄)
    - ingest_claims, cross_check_claims, verification_pipeline 함수에 메트릭 발행 호출 통합
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7_

  - [x]* 9.6 Property 20 테스트 작성: KPI 메트릭 계산 공식
    - **Property 20: KPI 메트릭 계산 공식**
    - **Validates: Requirements 15.2, 15.3, 15.4, 15.5, 15.6, 15.7**
    - 7개 메트릭 계산 공식 정확성, BOS-AI/ClaimDB 네임스페이스 발행 검증

  - [x] 9.7 Terraform 변수 및 IAM 최종 정리 (`environments/app-layer/bedrock-rag/variables.tf` 수정)
    - Claim DB 테이블명, RTL S3 버킷명 등 신규 변수 추가
    - Lambda_Handler IAM에 `cloudwatch:PutMetricData` 권한 추가 (BOS-AI/ClaimDB 네임스페이스)
    - 모든 신규 리소스 필수 태그 최종 확인
    - _Requirements: 13.6, 15.8_

- [x] 10. Final Checkpoint - 전체 테스트 통과 확인
  - Ensure all tests pass, ask the user if questions arise.
  - `cd environments/app-layer/bedrock-rag && terraform validate`
  - `cd tests && go test -v ./properties/ -run TestEnhancedRagOptimization -count=1`
  - 전체 5 Phase 통합 동작 확인


- [x] 11. Phase 6: RTL Knowledge Graph (Neptune Graph DB)
  - [x] 11.1 Neptune Terraform 모듈 구현 (`modules/ai-workload/graph-knowledge/`)
    - `neptune.tf`: aws_neptune_cluster + aws_neptune_cluster_instance (db.t4g.medium)
    - `security_group.tf`: Inbound TCP 8182를 RTL_Parser_Lambda SG와 Lambda_Handler SG에서만 허용 (내부망 전체 허용 금지)
    - `variables.tf`, `outputs.tf`
    - KMS CMK 암호화 (`storage_encrypted = true`)
    - 필수 태그 적용
    - _Requirements: 16.1, 16.2, 16.3, 16.14_

  - [x] 11.2 Neptune 환경 배포 구성 (`environments/app-layer/knowledge-graph/`)
    - `remote_state.tf`: network-layer 상태 참조 (VPC ID, Subnet ID)
    - `main.tf`: modules/ai-workload/graph-knowledge 호출, vpc_security_group_ids와 neptune_subnet_group_name은 terraform_remote_state 참조
    - `iam_readonly.tf`: LLM/MCP용 Read-Only Role (neptune-db:ReadDataViaQuery만)
    - `iam_write.tf`: RTL_Parser_Lambda용 Write Role (neptune-db:WriteDataViaQuery) — 태스크 1.3의 RTL Parser Lambda IAM에 추가
    - `variables.tf`, `outputs.tf`
    - VPC Endpoint 네트워크 격리
    - _Requirements: 16.4, 16.5, 16.15_

  - [x] 11.3 RTL Parser Lambda → Neptune 관계 적재 확장 (`rtl_parser_src/handler.py` 수정)
    - 파싱 결과에서 관계 추출: Module→Module(INSTANTIATES), Module→Port(HAS_PORT), Port→Port(CONNECTS_TO), Parameter→Parameter(PROPAGATES_TO)
    - Neptune에 노드/엣지로 적재 (Gremlin 또는 openCypher)
    - 노드 타입: Module, Port, Signal, Parameter, ClockDomain
    - 엣지 타입: INSTANTIATES, HAS_PORT, CONNECTS_TO, DRIVES, PROPAGATES_TO, BELONGS_TO_DOMAIN
    - _Requirements: 16.6, 16.7, 16.8_

  - [x] 11.4 MCP Bridge Graph 도구 추가 (`mcp-bridge/server.js` 수정)
    - `trace_signal_path`: module_name(필수) + signal_name(필수) → 신호 전파 경로 반환
    - `find_instantiation_tree`: module_name(필수) + depth(선택, 기본3) → 인스턴스화 트리 반환
    - `find_clock_crossings`: module_name(필수) → 클럭 도메인 크로싱 신호 목록 반환
    - _Requirements: 16.9, 16.10, 16.11_

  - [x] 11.5 3저장소 통합 질의 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - Verification Pipeline 확장: asyncio를 사용하여 Graph DB(Neptune) + Claim DB + OpenSearch 3개 DB를 병렬 비동기 호출
    - 개별 DB 쿼리 Timeout: 30초 제한
    - Neptune 쿼리 실패/Timeout 시 Fallback: OpenSearch + Claim DB 결과만으로 답변 생성 (시스템 중단 없음)
    - Neptune Fallback 발생 시 `verification_metadata.neptune_fallback = true` 설정
    - _Requirements: 16.12_

  - [x]* 11.7 Property 25 테스트 작성: Neptune 통합 질의 Fallback 및 병렬 호출
    - **Property 25: Neptune 통합 질의 Fallback 및 병렬 호출**
    - **Validates: Requirements 16.3, 16.5, 16.12, 16.15**
    - 3개 DB 병렬 비동기 호출, 개별 Timeout 30초, Neptune 실패 시 Fallback + neptune_fallback=true, Neptune SG 8182 포트 제한 검증

  - [x] 11.6 PyVerilog AST 파서 교체 준비 (`rtl_parser_src/handler.py`)
    - Phase 6b: always_ff/always_comb 블록 분석 → 클럭 도메인 식별
    - assign 문 분석 → 신호 구동 관계(DRIVES) 추출
    - ECR 컨테이너 이미지 배포 전환
    - _Requirements: 16.13_

- [x] 12. Phase 6 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - Neptune Cluster + 관계 추출 + 3저장소 통합 질의 동작 확인
  - `terraform validate` (knowledge-graph 환경)

- [x] 13. Final Checkpoint - 전체 6 Phase 통합 테스트
  - 전체 시스템 통합 동작 확인
  - `cd environments/app-layer/bedrock-rag && terraform validate`
  - `cd environments/app-layer/knowledge-graph && terraform validate`
  - `cd tests && go test -v ./properties/ -run TestEnhancedRagOptimization -count=1`


- [x] 14. Phase 7: Supply Side 파서 확장 — Package Function Extractor + Flit Struct + 중첩 Struct
  - [x] 14.1 Package Function/Task Extractor 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/package_extractor.py` 수정)
    - `_extract_functions()` 함수 추가: `function` 선언에서 함수명, 반환 타입, 인자 목록(이름 + 타입), automatic/static 한정자 파싱
    - `_extract_tasks()` 함수 추가: `task` 선언에서 태스크명, 인자 목록(이름 + 방향 + 타입) 파싱
    - 본문 20줄 이하인 경우 1줄 요약(주요 로직 패턴)을 claim_text에 추가
    - claim_text 형식: `"Package '{pkg_name}' defines function '{func_name}({args}) → {return_type}'"`
    - 모든 claim에 `parser_source='package_function_extractor'` 설정
    - `extract_package_constants()` 함수 내에서 `_extract_functions()`, `_extract_tasks()` 호출 통합
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7_

  - [x]* 14.2 Property 26 테스트 작성: Function/Task 추출 라운드트립
    - **Property 26: Function/Task 추출 라운드트립**
    - **Validates: Requirements 17.1, 17.2, 17.3, 17.6**
    - 유효한 SystemVerilog function/task 선언에 대해 추출 후 claim_text 파싱으로 원본 시그니처 복원 검증

  - [x] 14.3 Flit Struct 필드 레벨 파싱 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/package_extractor.py` 수정)
    - `_extract_structs()` 함수 확장: 필드별 비트폭(`logic [N:0]`), 인라인 주석(`// comment`), 타입 참조(`tile_t dest_tile`) 추출
    - claim_text 형식: `"Package '{pkg_name}' defines struct '{struct_name}' field '{field_name}' with width {bit_width}"`
    - flit 관련 타입(`*_flit_t`, `*_header_t`, `*_payload_t`)에 대해 비트 위치 순서 정렬 레이아웃 claim 추가 생성
    - 모든 claim에 `parser_source='package_struct_parser'` 설정
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_

  - [x]* 14.4 Property 30 테스트 작성: Struct 필드 비트폭 추출
    - **Property 30: Struct 필드 비트폭 추출**
    - **Validates: Requirements 20.1, 20.2, 20.4, 20.5**
    - typedef struct 정의에서 필드 비트폭, 인라인 주석, 타입 참조가 claim에 포함되는지 검증

  - [x] 14.5 중첩 Struct 지원 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/package_extractor.py` 수정)
    - `_extract_structs()` 함수 확장: struct 내부에 다른 struct 타입 필드 인식 + 계층적 claim 생성
    - claim_text 형식: `"Package '{pkg_name}' struct '{parent_struct}' contains nested struct field '{field_name}' of type '{child_struct}'"`
    - 최대 3단계 깊이까지 추적, 초과 시 `"nested depth exceeds 3, truncated"` 경고 포함
    - 부모/자식 struct 모두에 대해 claim 생성
    - _Requirements: 21.1, 21.2, 21.3, 21.4_

  - [x]* 14.6 Property 31 테스트 작성: 중첩 Struct 완전성
    - **Property 31: 중첩 Struct 완전성**
    - **Validates: Requirements 21.1, 21.2, 21.3, 21.4**
    - 부모/자식 struct claim 모두 생성, 관계 추적 가능, 3단계 초과 시 truncation 경고 검증

- [x] 15. Phase 7: Supply Side 파서 확장 — Generate Block Parser + Always Block Parser
  - [x] 15.1 Generate Block Parser 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/generate_block_parser.py` — 신규)
    - `extract_generate_blocks(rtl_content, module_name, file_path, pipeline_id)` 함수 구현
    - `generate for`/`generate if` 블록 범위(begin~end) 정규식 식별
    - 4가지 토폴로지 패턴 인식: daisy-chain, ring, feedthrough, 2D array
    - 조건부 bypass 패턴 감지 및 claim 포함
    - genvar 범위에서 반복 차원/크기 추출, 파라미터 참조 문자열 보존
    - 중첩 generate(2중 for) → `"2D {outer_dim}×{inner_dim}"` 형식 기록
    - claim_text 형식: `"Module '{module_name}' has generate block '{label}' with {pattern_type} topology connecting {signal_name} across {dimension} ({size} elements)"`
    - 모든 claim에 `parser_source='generate_block_parser'` 설정
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7_

  - [x]* 15.2 Property 27 테스트 작성: Generate 블록 토폴로지 패턴 인식
    - **Property 27: Generate 블록 토폴로지 패턴 인식**
    - **Validates: Requirements 18.1, 18.2, 18.4, 18.6**
    - generate for/if 블록에서 올바른 토폴로지 유형 식별, claim_text에 패턴/신호/차원/크기 포함, 파라미터 참조 보존 검증

  - [x] 15.3 Always Block Parser 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/always_block_parser.py` — 신규)
    - `extract_clock_domains(rtl_content, module_name, file_path, pipeline_id)` 함수 구현
    - `always_ff` 블록 sensitivity list(`@(posedge <clk>)`, `@(negedge <clk>)`) 정규식 추출
    - `always_comb` 블록 제외
    - 클럭 신호명 → 도메인 매핑: `i_ai_clk` → AI, `i_noc_clk` → NoC, `i_dm_clk` → DM, 기타 `*_clk` → 신호명 기반
    - 모듈당 클럭 도메인 요약 claim 생성: `"Module '{module_name}' operates in {N} clock domains: {domain_list}"`
    - 2개 이상 도메인 감지 시 CDC 경고 claim 추가: `"Module '{module_name}' has potential clock domain crossing between {domain_A} and {domain_B}"`
    - 리셋 신호(`posedge reset`, `negedge reset_n`) claim 포함
    - 모든 claim에 `parser_source='always_block_parser'` 설정
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7_

  - [x]* 15.4 Property 28 테스트 작성: 클럭 도메인 추출 및 집계
    - **Property 28: 클럭 도메인 추출 및 집계**
    - **Validates: Requirements 19.1, 19.2, 19.3, 19.6**
    - always_ff에서만 클럭 도메인 추출(always_comb 제외), 모듈당 집계, 도메인 매핑 정확성 검증

  - [x]* 15.5 Property 29 테스트 작성: 클럭 도메인 크로싱 감지
    - **Property 29: 클럭 도메인 크로싱 감지**
    - **Validates: Requirements 19.4**
    - 2개 이상 도메인 시 CDC claim 생성, 1개 이하 시 CDC claim 미생성 검증

- [x] 16. Phase 7 Checkpoint — Supply Side 파서 기본 검증
  - Ensure all tests pass, ask the user if questions arise.
  - `package_extractor.py` 함수/태스크 추출 + flit 구조 + 중첩 struct 동작 확인
  - `generate_block_parser.py` 토폴로지 패턴 인식 동작 확인
  - `always_block_parser.py` 클럭 도메인 추출 동작 확인


- [x] 17. Phase 7: Supply Side 파서 확장 — Bitwidth Evaluator
  - [x] 17.1 Bitwidth Evaluator 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/bitwidth_evaluator.py` — 신규)
    - `SafeIntEvaluator` 클래스 구현: `ast.NodeVisitor` 기반 안전한 정수 산술 파서
    - 지원 연산: `+`, `-`, `*`, `/`, `$clog2()`
    - `evaluate_bitwidth(expr, param_context)` 함수: 비트폭 표현식을 정수로 평가
    - 파라미터 해석 순서: 로컬 파라미터 → 패키지 파라미터
    - 해석 불가능한 파라미터 포함 시 원본 표현식 유지 + DEBUG 로그
    - 악의적 입력(함수 호출, import, exec 등) 거부 → ValueError 발생
    - Python `eval()` 사용 금지 (코드 인젝션 방지)
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6_

  - [x]* 17.2 Property 32 테스트 작성: 비트폭 표현식 평가
    - **Property 32: 비트폭 표현식 평가**
    - **Validates: Requirements 22.1, 22.2, 22.3, 22.4**
    - 순수 정수 산술식 + 해석 가능 파라미터 → 수학적 올바른 결과, 미해석 파라미터 → 원본 유지 검증

  - [x]* 17.3 Property 33 테스트 작성: 안전한 비트폭 평가 (코드 인젝션 방지)
    - **Property 33: 안전한 비트폭 평가**
    - **Validates: Requirements 22.6**
    - 정수 리터럴/지원 연산자/파라미터 참조 외 구문 거부, 악의적 입력 시 ValueError 검증


- [x] 18. Phase 7: Consumption Side — 대형 모듈 청킹 + 질의 유형별 동적 Boost
  - [x] 18.1 대형 모듈 청킹 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/handler.py` 수정)
    - `_process_rtl_file()` 함수 확장: 포트 50개 이상 모듈 감지 시 Sub_Record 분할
    - 3가지 Sub_Record 유형 생성: `port_summary`(Port_Classifier 카테고리별), `instance_hierarchy`(인스턴스 목록 + 모듈 타입), `parameter_config`(파라미터 목록 + 값)
    - 각 Sub_Record에 `parent_module_name`, `sub_record_type`, `analysis_type='module_parse_chunk'` 필드 포함
    - 기존 전체 모듈 레코드(`analysis_type: module_parse`) 유지 (하위 호환)
    - 각 Sub_Record를 개별 임베딩 + OpenSearch 인덱싱
    - _Requirements: 23.1, 23.2, 23.3, 23.4, 23.5_

  - [x]* 18.2 Property 34 테스트 작성: 대형 모듈 청킹 불변식
    - **Property 34: 대형 모듈 청킹 불변식**
    - **Validates: Requirements 23.1, 23.2, 23.3**
    - 50+ 포트 → 3가지 Sub_Record 생성 + 필드 포함 + 기존 레코드 유지, 50 미만 → Sub_Record 미생성 검증

  - [x] 18.3 질의 유형별 동적 Boost 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/handler.py` 수정)
    - `classify_query_type(query)` 함수 추가: 키워드 패턴 매칭으로 5가지 유형 분류
    - `get_dynamic_boosts(query_type)` 함수 추가: 유형별 boost 가중치 반환
    - 질의 유형: port_query(claim 4.0, module_parse 0.5), hierarchy_query(claim 1.5, module_parse 3.0), config_query(claim 4.0, module_parse 1.0), connectivity_query(claim 4.0, module_parse 1.0), general_query(claim 3.0, module_parse 1.0)
    - `_search_rtl()` 함수 수정: 동적 boost 적용
    - 미매칭 시 `general_query` 폴백 (기존 고정 가중치)
    - 응답 `metadata.query_type`에 분류 결과 포함
    - _Requirements: 24.1, 24.2, 24.3, 24.4, 24.5, 24.6, 24.7, 24.8_

  - [x]* 18.4 Property 35 테스트 작성: 질의 유형별 동적 Boost 매핑
    - **Property 35: 질의 유형별 동적 Boost 매핑**
    - **Validates: Requirements 24.1, 24.2, 24.3, 24.4, 24.5, 24.6, 24.8**
    - classify_query_type 5가지 유형 분류, get_dynamic_boosts 가중치 정확성, 미매칭 시 general_query 폴백 검증


- [x] 19. Phase 7: Generation Side — Hybrid Grounding
  - [x] 19.1 Hybrid Grounding 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `generate_hdd_section()` 함수 확장: `grounding_mode` 파라미터 수용 (strict/hybrid/free, 기본값 hybrid)
    - Foundation_Model 프롬프트에 Hybrid_Grounding 지시 포함
    - `[GROUNDED from claim:{claim_id}]` 태그 + claim_id 각주 첨부
    - `[INFERRED]` 태그 + `"※ Spec 확인 필요"` 경고 자동 추가
    - 응답에 `grounded_ratio`, `inferred_ratio` 포함 (합계 1.0)
    - `inferred_ratio > 0.5` 시 KB 커버리지 경고 메시지 추가
    - `strict` 모드: GROUNDED만, KB 부족 시 `[NOT IN KB]` 메시지
    - `free` 모드: 태그 없이 자유 서술
    - `rag_query` API에서도 `grounding_mode` 수용
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7, 25.8_

  - [x]* 19.2 Property 36 테스트 작성: Hybrid Grounding 태그 일관성
    - **Property 36: Hybrid Grounding 태그 일관성**
    - **Validates: Requirements 25.2, 25.3, 25.4, 25.5**
    - GROUNDED 태그에 claim_id 각주, INFERRED 태그에 경고, grounded_ratio + inferred_ratio = 1.0, inferred > 0.5 시 경고 검증

  - [x]* 19.3 Property 37 테스트 작성: Grounding 모드 동작
    - **Property 37: Grounding 모드 동작**
    - **Validates: Requirements 25.6, 25.8**
    - strict 모드 GROUNDED만 + KB 부족 시 NOT IN KB, hybrid 모드 양쪽 태그, free 모드 태그 없음 검증


- [x] 20. Phase 7: Quality Infrastructure — 파서별 기여도 측정
  - [x] 20.1 파서 Feature Flag 및 parser_source 필드 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/handler.py` 수정)
    - 환경 변수 feature flag 추가: `PARSER_PACKAGE_ENABLED`, `PARSER_PORT_CLASSIFIER_ENABLED`, `PARSER_GENERATE_BLOCK_ENABLED`, `PARSER_ALWAYS_BLOCK_ENABLED`, `PARSER_FUNCTION_EXTRACTOR_ENABLED` (기본값 모두 `true`)
    - 비활성화된 파서 건너뛰기 + 로그 기록 (INFO)
    - 각 파서 실행 결과를 CloudWatch 구조화 로그에 기록: parser_name, claims_generated, execution_time_ms, files_processed
    - 기존 `_make_claim()` 및 각 파서의 claim 생성에 `parser_source` 필드 추가
    - _Requirements: 26.1, 26.2, 26.3, 26.6_

  - [x]* 20.2 Property 38 테스트 작성: 파서 Feature Flag 제어
    - **Property 38: 파서 Feature Flag 제어**
    - **Validates: Requirements 26.1, 26.2**
    - feature flag false → 파서 미실행 + claim 미인덱싱, true → 정상 실행 검증

  - [x]* 20.3 Property 39 테스트 작성: 파서 출처 귀속
    - **Property 39: 파서 출처 귀속**
    - **Validates: Requirements 26.6**
    - 모든 파서 생성 claim에 parser_source 필드 존재 + 빈 문자열 아님 검증

  - [x] 20.4 파서 기여도 측정 API 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/handler.py` + `environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `handler.py`: CloudWatch `BOS-AI/RTLParser` 네임스페이스에 `ParserClaimCount`, `ParserExecutionTime`, `ParserHitRatio` 메트릭 발행
    - `index.py`: `parser_contribution` 액션 추가 — pipeline_id(필수) 입력, 파서별 claims_total, claims_hit_in_search, hit_ratio, avg_search_score 집계 반환
    - `handler()` 라우팅에 `action == 'parser_contribution'` 분기 추가
    - _Requirements: 26.4, 26.5, 26.8_


- [x] 21. Phase 7: OpenSearch 인덱스 필드 확장 + Handler 통합 배선
  - [x] 21.1 OpenSearch 인덱스 스크립트 업데이트 (`scripts/create-opensearch-index.py` 수정)
    - `parent_module_name`(keyword) 필드 매핑 추가
    - `sub_record_type`(keyword) 필드 매핑 추가
    - `parser_source`(keyword) 필드 매핑 추가
    - _Requirements: 23.6, 26.7_

  - [x] 21.2 Handler 통합 배선 (`environments/app-layer/bedrock-rag/rtl_parser_src/handler.py` 수정)
    - `_process_rtl_file()` 함수에 Phase 7 파서 호출 통합:
      - `from generate_block_parser import extract_generate_blocks`
      - `from always_block_parser import extract_clock_domains`
      - `from bitwidth_evaluator import evaluate_bitwidth`
    - 파서 호출 순서: 기본 모듈 파싱 → Package 함수/태스크 추출 → Generate 블록 파싱 → Always 블록 파싱 → 비트폭 평가 → 대형 모듈 청킹
    - 각 파서 호출을 feature flag로 게이팅
    - 각 파서 생성 claim을 개별 임베딩 + OpenSearch 인덱싱
    - 파서 실행 시간 CloudWatch 구조화 로그 기록
    - _Requirements: 17.5, 18.5, 19.5, 22.5, 23.1, 26.1, 26.3_


- [x] 22. Phase 7 Final Checkpoint — 전체 Phase 7 통합 테스트
  - Ensure all tests pass, ask the user if questions arise.
  - Supply Side: package_extractor.py (함수/태스크 + flit + 중첩 struct), generate_block_parser.py, always_block_parser.py, bitwidth_evaluator.py 동작 확인
  - Consumption Side: 대형 모듈 청킹 + 질의 유형별 동적 Boost 동작 확인
  - Generation Side: Hybrid Grounding 3모드 동작 확인
  - Quality Infrastructure: 파서 feature flag + parser_source + 기여도 메트릭 동작 확인
  - `cd tests && go test -v ./properties/ -run TestEnhancedRagOptimization -count=1` (Phase 7 Property 26~39 포함)


- [x] 23. Phase 7 Final Checkpoint - 전체 7 Phase 통합 테스트
  - 전체 시스템 통합 동작 확인 (Phase 1~7)
  - `cd environments/app-layer/bedrock-rag && terraform validate`
  - `cd environments/app-layer/knowledge-graph && terraform validate`
  - `cd tests && go test -v ./properties/ -run TestEnhancedRagOptimization -count=1`

## Notes

- `*` 표시된 태스크는 선택적이며 빠른 MVP를 위해 건너뛸 수 있음
- 각 태스크는 이전 태스크의 결과물에 의존하여 점진적으로 구현
- Property 테스트는 `tests/properties/enhanced_rag_optimization_test.go`에 Go 1.21 + gopter로 작성
- 테스트 실행: `cd tests && go test -v ./properties/ -run TestEnhancedRagOptimization -count=1`
- Terraform 변경은 `terraform validate`로 검증
- Lambda 코드 변경은 기존 `index.py` 수정 + 신규 `rtl_parser_src/handler.py` 생성
- MCP Bridge 변경은 기존 `server.js` 수정
- OpenSearch 인덱스 생성은 `scripts/create-opensearch-index.py` 별도 실행 (Terraform local-exec 미사용)
- DynamoDB 모든 쓰기 작업에 optimistic locking 적용
- IAM Explicit Deny로 Source of Truth 버킷 보호
- Phase 7 신규 파일 3개: `generate_block_parser.py`, `always_block_parser.py`, `bitwidth_evaluator.py`
- Phase 7 수정 파일: `package_extractor.py`, `handler.py`, `index.py`, `create-opensearch-index.py`
- Phase 7 Property 테스트 14개 추가 (Property 26~39)
- 파서별 feature flag로 A/B 테스트 가능 (환경 변수 `PARSER_*_ENABLED`)
- 비트폭 평가에 Python `eval()` 사용 금지 — `ast.NodeVisitor` 기반 안전한 파서 사용
- 품질 목표: v8 68% → v9 75~78% Content Fidelity (RTL 단독 천장)
- Confluence/Jira는 Cloud 환경이므로 별도 연동 방식 검토 (이 스펙 범위 외)
- Codebeamer 연동은 Spec 6 (codebeamer-aspice-rag-integration)에서 처리
- Phase 9 신규 파일 1개: `port_binding_parser.py`
- Phase 9 수정 파일: `handler.py`, `index.py`, `server.js`, `api-gateway.tf`, `interactive_schematic.html`
- Phase 9 Property 테스트 5개 추가 (Property 40~44)
- Phase 9 요구사항 5개 추가 (요구사항 30~34)
- 포트 바인딩 파서는 `#(…)` 파라미터 블록과 `(…)` 포트 블록을 구분하여 포트만 추출
- Graph Export API는 Read-Only Neptune IAM Role 사용 (기존 Phase 6 인프라 재활용)
- Schematic Viewer는 온프렘 네트워크 없이도 내장 데이터로 동작 (API 호출은 선택적)
- HDD merge 실명 복구는 3단계 소스 우선순위로 placeholder를 실제 이름으로 치환
- Topic 전파 재생성은 max_propagation_depth=5로 무한 루프 방지




- [x] 24. Phase 8: EP Index Table 계산 및 Package Helper Function 확장 (Gap 1)
  - [x] 24.1 EP Index Table 계산 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/package_extractor.py` 수정)
    - `_compute_ep_index_table(constants, enums, pkg_name, file_path, pipeline_id)` 함수 추가
    - `extract_package_constants()` 함수 내에서 SizeX, SizeY, tile_t 추출 직후 호출
    - 계산 공식: `EndpointIndex = x * SizeY + y` (x: 0..SizeX-1, y: 0..SizeY-1)
    - 각 EP에 대해 개별 claim 생성: `"Endpoint EP={ep} at position (X={x}, Y={y}) is tile type {tile_t_member}"`
    - EP Table 전체 요약 claim 1건 추가 생성
    - tile_t enum → Y 좌표 매핑 테이블 (`TILE_TYPE_Y_MAPPING` 딕셔너리)
    - tile_t 매핑 불가 시 "UNKNOWN" 타입으로 기록 + WARNING 로그
    - SizeX/SizeY 미추출 시 EP Table 생성 건너뛰기 + WARNING 로그
    - `PARSER_EP_TABLE_ENABLED` 환경 변수 feature flag (기본값 `true`)
    - `parser_source` 필드를 `"ep_index_table"` 로 설정
    - _Requirements: 27.1, 27.2, 27.3, 27.4, 27.6_

  - [x] 24.2 Package Helper Function 추출 범위 확장 (`package_extractor.py` 수정)
    - 기존 함수 추출 로직의 검색 범위를 패키지 파일 전체로 확장
    - `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex` 등 인덱스 계산 헬퍼 함수 누락 없이 추출
    - 함수 검색 정규식 개선: 패키지 스코프 외부 함수도 포함
    - _Requirements: 27.5_

  - [x] 24.3 EP Index Table 단위 테스트 작성 (`environments/app-layer/bedrock-rag/rtl_parser_src/test_ep_table.py` — 신규)
    - SizeX=4, SizeY=5 → 20개 EP claim 생성 검증 (인덱스 0~19 연속)
    - tile_t 매핑 검증: TENSIX(Y=0~2), NOC2AXI_ROUTER_NE_OPT(Y=3+4)
    - EP Table 요약 claim 존재 검증
    - PARSER_EP_TABLE_ENABLED=false → claim 0건 검증
    - SizeX/SizeY 미추출 시 graceful skip 검증
    - tile_t 미추출 시 "UNKNOWN" 타입 폴백 검증
    - EP 공식 라운드트립: claim_text에서 EP, X, Y 파싱 → EP = X * SizeY + Y 성립 검증
    - Helper function 4개 추출 검증 (getTensixIndex, getNoc2AxiIndex, getApbIndex, getDmIndex)
    - _Requirements: 27.1, 27.2, 27.3, 27.4, 27.5, 27.6, 27.7_


- [x] 25. Phase 8: Generate Block Instance-Position Mapping 확장 (Gap 2-3)
  - [x] 25.1 Instance-Position Mapping 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/generate_block_parser.py` 수정)
    - `_extract_instance_positions(block_content, block_label, genvar_ranges, module_name, file_path, pipeline_id)` 함수 추가
    - `extract_generate_blocks()` 함수 내에서 각 generate 블록 파싱 후 호출
    - 인스턴스화 패턴 정규식: `r'(\w+)\s+(\w+)\s*\('` (module_type instance_name)
    - 위치(X,Y) 유추: genvar 변수 또는 상수에서 추론
    - Dual-row 감지: 2개 Y 좌표에 걸치는 블록 → `Y={y1}+{y2}` 형식
    - EP ID 추출 패턴: `r'\.ep_id\s*\(\s*(\d+|[\w\*\+\-]+)\s*\)'`
    - claim_text 형식: `"Generate block '{label}' at (X={x}, Y={y_range}) instantiates '{module_name}' with EP={ep_id} ({tile_type})"`
    - 위치 유추 불가 시 "UNKNOWN" 기록 + WARNING 로그
    - _Requirements: 28.1, 28.2, 28.3, 28.5, 28.6, 28.7_

  - [x] 25.2 NoC Repeater 추출 구현 (`generate_block_parser.py` 수정)
    - `_extract_noc_repeaters(block_content, block_label, genvar_ranges, module_name, file_path, pipeline_id)` 함수 추가
    - `tt_noc_repeaters` 등 repeater 인스턴스 인식
    - 파라미터 추출: `#(.NUM(4))` 패턴에서 NUM 값 추출
    - 배치 위치 유추: inter-column (X 좌표 간) 위치
    - claim_text 형식: `"NoC repeater '{instance_name}' with NUM={num} stages placed at Y={y} between X={x1}↔X={x2}"`
    - _Requirements: 28.4_

  - [x] 25.3 Instance-Position Mapping 단위 테스트 작성 (`environments/app-layer/bedrock-rag/rtl_parser_src/test_instance_position.py` — 신규)
    - NOC2AXI dual-row 검증: Y=4+3 형식, EP 2개 명시
    - NoC repeater NUM 파라미터 검증: NUM=4, NUM=6 추출
    - NoC repeater inter-column 위치 검증: X=1↔X=2
    - Instance EP ID 추출 검증: .ep_id(9) → EP=9
    - Instance 위치 UNKNOWN 폴백 검증: genvar 미유추 시
    - 인스턴스명/모듈명 비어있지 않음 검증
    - generate 블록 라벨 → 모듈명 매핑 정확성 검증
    - _Requirements: 28.1, 28.2, 28.3, 28.4, 28.5, 28.7, 28.8_


- [x] 26. Phase 8: Wire Declaration Parser 구현 (Gap 4-5)
  - [x] 26.1 Wire Declaration Parser 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/wire_declaration_parser.py` — 신규)
    - `extract_wire_declarations(rtl_content, module_name, file_path, pipeline_id, known_structs)` 메인 함수
    - 3가지 wire 선언 패턴 정규식 (Pattern A/B/C)
    - `_parse_dimensions(dim_str)`: `[SizeX][SizeY-1][2]` → `['SizeX', 'SizeY-1', '2']`
    - `_evaluate_dimensions(dims, params)`: bitwidth_evaluator.py SafeIntEvaluator 재사용하여 숫자 평가
    - `_infer_purpose(signal_name)`: wire 이름에서 연결 목적 유추 (PURPOSE_HEURISTICS 딕셔너리)
    - struct 타입 wire claim_text: `"Wire '{signal_name}' of type '{struct_type}' with dimensions [{dims}] ({evaluated} array) for {purpose}"`
    - 비-struct wire claim_text: `"Wire '{signal_name}' with dimensions [{dims}] ({evaluated} array) connects {purpose}"`
    - known_structs에 존재하는 struct 타입 참조 시 claim에 참조 정보 포함
    - `parser_source` 필드를 `"wire_declaration_parser"` 로 설정
    - `PARSER_WIRE_DECLARATION_ENABLED` 환경 변수 feature flag (기본값 `true`)
    - _Requirements: 29.1, 29.2, 29.3, 29.4, 29.5, 29.6, 29.7, 29.8, 29.9, 29.11_

  - [x] 26.2 Handler 통합 배선 (`environments/app-layer/bedrock-rag/rtl_parser_src/handler.py` 수정)
    - `from wire_declaration_parser import extract_wire_declarations` import 추가
    - `PARSER_EP_TABLE_ENABLED` feature flag 변수 추가
    - `PARSER_WIRE_DECLARATION_ENABLED` feature flag 변수 추가
    - `_process_rtl_file()` 함수 내에서 wire_declaration_parser 호출 (기존 파서 호출 후)
    - known_structs를 package_extractor 결과에서 전달
    - _Requirements: 29.6, 29.7_

  - [x] 26.3 OpenSearch 인덱스 필드 확장 (`scripts/create-opensearch-index.py` 수정)
    - `wire_type`(keyword) 필드 매핑 추가
    - `array_dimensions`(keyword) 필드 매핑 추가
    - `struct_type_ref`(keyword) 필드 매핑 추가
    - `inferred_purpose`(text) 필드 매핑 추가
    - _Requirements: 29.3, 29.4_

  - [x] 26.4 Wire Declaration Parser 단위 테스트 작성 (`environments/app-layer/bedrock-rag/rtl_parser_src/test_wire_declaration_parser.py` — 신규)
    - Pattern A 파싱: `wire trinity_clock_routing_t clock_routing_in[SizeX][SizeY];` → struct type + dims 추출
    - Pattern B 파싱: `logic [31:0] some_signal[SizeX];` → bit_range + dims 추출
    - Pattern C 파싱: `trinity_clock_routing_t clock_routing_out[SizeX][SizeY];` → implicit wire 추출
    - 배열 차원 파싱: `[SizeX][SizeY-1][2]` → `['SizeX', 'SizeY-1', '2']`
    - 차원 평가: SizeX=4, SizeY=5 → "4×5 array" (bitwidth_evaluator 연동)
    - 목적 유추: `de_to_t6_coloumn` → "dispatch-to-tensix feedthrough"
    - 목적 유추: `clock_routing_in` → "clock distribution"
    - Feature flag off: PARSER_WIRE_DECLARATION_ENABLED=false → claim 0건
    - struct 참조 연결: known_structs에 `trinity_clock_routing_t` 존재 시 참조 포함
    - 신호명 비어있지 않음 + 차원/struct 정보 최소 1개 존재 검증
    - 차원 라운드트립: _parse_dimensions → 재조합 → 원본 일치
    - _Requirements: 29.1, 29.2, 29.3, 29.4, 29.5, 29.7, 29.8, 29.9, 29.10_


- [x] 27. Phase 8 Checkpoint — 전체 Phase 8 통합 테스트
  - Ensure all tests pass, ask the user if questions arise.
  - EP Index Table: `package_extractor.py` EP 계산 + tile_t 매핑 동작 확인
  - Instance-Position Mapping: `generate_block_parser.py` dual-row + repeater 추출 동작 확인
  - Wire Declaration Parser: `wire_declaration_parser.py` 3가지 패턴 + 차원 평가 동작 확인
  - Handler 통합: feature flag 제어 + OpenSearch 인덱싱 동작 확인
  - `cd environments/app-layer/bedrock-rag/rtl_parser_src && py -m pytest -v`


- [x] 28. Final Checkpoint - 전체 8 Phase 통합 테스트
  - 전체 시스템 통합 동작 확인 (Phase 1~8)
  - `cd environments/app-layer/bedrock-rag && terraform validate`
  - Content Fidelity 목표: v9.1 74% → v9.2 80%+ 달성 여부 확인
  - 5개 갭 해소 확인: EP Table (+3pp), NOC2AXI+repeater (+5pp), clock_routing+dispatch (+5pp)


- [x] 29. Phase 9: Port Binding Parser + Neptune CONNECTS_TO 엣지 적재
  - [x] 29.1 Port Binding Parser 구현 (`environments/app-layer/bedrock-rag/rtl_parser_src/port_binding_parser.py` — 신규)
    - `extract_port_bindings(rtl_content, module_name, file_path, pipeline_id)` 메인 함수
    - 인스턴스화 구문 식별: `module_type [#(params)] instance_name (port_connections);` 패턴
    - `#(…)` 블록(파라미터)과 `(…)` 블록(포트) 분리 → 포트 블록만 파싱
    - `.port_name(signal_expr)` 정규식 추출: port_name, signal_expr, bit_range 분리
    - `.port_name()` (unconnected) 감지 → `is_unconnected=true`
    - concatenation 바인딩 `.port({sig_a, sig_b})` 인식 → `constituent_signals` 배열 분해
    - 동일 instance 내 동일 port_name 중복 시 첫 번째만 채택 + WARNING 로그
    - claim_text 형식: `"Instance '{instance_name}' of module '{module_type}' binds port '{port_name}' to signal '{signal_expr}'"`
    - `parser_source='port_binding_parser'` 설정
    - `PARSER_PORT_BINDING_ENABLED` 환경 변수 feature flag (기본값 `true`)
    - _Requirements: 30.1, 30.2, 30.3, 30.4, 30.5, 30.6, 30.7, 30.8, 30.9_

  - [x] 29.2 Neptune CONNECTS_TO 엣지 적재 확장 (`environments/app-layer/bedrock-rag/rtl_parser_src/handler.py` 수정)
    - `_load_port_bindings_to_neptune(bindings, module_name)` 함수 추가
    - 각 바인딩에 대해 Port 노드 생성/MERGE: `{instance_name}.{port_name}` (속성: instance_name, module_type, port_name, direction, width)
    - Signal 노드 생성/MERGE: `signal_expr` (속성: name, scope=module_name, width)
    - CONNECTS_TO 엣지 생성: Port → Signal (속성: bit_range, source_file, line_number, is_concatenation)
    - concatenation 바인딩: 대표 Signal 노드 + constituent_signals 각각에 보조 CONNECTS_TO 엣지 (`is_constituent=true`)
    - 동일 `(instance_name, port_name)` 노드 MERGE로 중복 방지 (openCypher MERGE)
    - Neptune 적재 실패 시 graceful degradation: S3/OpenSearch 인덱싱 계속 + `neptune_load_failed: true` 로그
    - `_process_rtl_file()` 함수에서 port_binding_parser 호출 후 Neptune 적재 호출 통합
    - _Requirements: 31.1, 31.2, 31.3, 31.4, 31.5, 31.6, 31.7, 31.8_

  - [x]* 29.3 Property 40 테스트 작성: Port Binding 추출 완전성
    - **Property 40: Port Binding 추출 완전성**
    - **Validates: Requirements 30.1, 30.2, 30.4, 30.8**
    - `.port(signal)` 패턴 추출, 파라미터 블록 제외, is_unconnected=false 시 signal_expr 비어있지 않음, port_name 비어있지 않음 검증

  - [x]* 29.4 Property 41 테스트 작성: Neptune CONNECTS_TO 적재 보존
    - **Property 41: Neptune CONNECTS_TO 적재 보존**
    - **Validates: Requirements 31.1, 31.7, 31.8**
    - is_unconnected=false 바인딩 수 == CONNECTS_TO 엣지 수, MERGE로 중복 미생성, Neptune 실패 시 OpenSearch 인덱싱 계속 검증

  - [x] 29.5 Port Binding Parser 단위 테스트 작성 (`environments/app-layer/bedrock-rag/rtl_parser_src/test_port_binding_parser.py` — 신규)
    - 기본 `.port(signal)` 추출 검증
    - `.port(signal[3:0])` bit_range 추출 검증
    - `.port()` unconnected 감지 검증
    - `.port({a, b, c})` concatenation 분해 검증
    - `#(.PARAM(val))` 파라미터 블록 제외 검증
    - 동일 port_name 중복 시 첫 번째만 채택 검증
    - feature flag off → claim 0건 검증
    - claim_text 형식 정확성 검증
    - _Requirements: 30.1, 30.2, 30.3, 30.4, 30.5, 30.8, 30.9_


- [x] 30. Phase 9: Graph Export API + Interactive Schematic Viewer
  - [x] 30.1 Graph Export API 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `graph_export(event)` 함수 추가
    - 입력 파라미터: `scope`(필수, "chip"/"module"/"signal"), `root_module`(필수), `depth`(선택, 기본3), `signal_filter`(선택, scope="signal" 시 필수)
    - `scope="chip"`: root_module의 직접 자식 인스턴스 + 모듈 간 CONNECTS_TO 엣지 aggregation
    - `scope="module"`: root_module 내부 인스턴스/포트/바인딩 상세 그래프
    - `scope="signal"`: signal_filter 매칭 신호의 전파 경로 (trace_signal_path 로직 재사용)
    - 응답 JSON: `{nodes: [{id, label, type, properties}], edges: [{id, source, target, label, properties}], metadata: {scope, root_module, depth, node_count, edge_count, generated_at, neptune_fallback, truncated}}`
    - 노드 상한 1,000개 (degree 기준 상위), 초과 시 `truncated=true`
    - Neptune 타임아웃/실패 시 빈 그래프 + `neptune_fallback=true` 반환 (HTTP 200)
    - Read-Only Neptune IAM Role 사용
    - `handler()` 라우팅에 POST `/rag/graph-export` 추가
    - _Requirements: 32.1, 32.2, 32.3, 32.4, 32.5, 32.6, 32.7, 32.8_

  - [x] 30.2 API Gateway 라우트 추가 (`environments/app-layer/bedrock-rag/api-gateway.tf` 수정)
    - `/rag/graph-export` POST 라우트 추가
    - `/rag/hdd/regenerate-stale` POST 라우트 추가 (Task 31.3용)
    - _Requirements: 32.9_

  - [x] 30.3 MCP Bridge graph_export 도구 추가 (`mcp-bridge/server.js` 수정)
    - `graph_export` 도구 추가: scope(필수), root_module(필수), depth(선택), signal_filter(선택) → POST /rag/graph-export
    - 응답에 `execution_time_ms` 포함
    - _Requirements: 32.1, 32.5_

  - [x] 30.4 Interactive Schematic Viewer 확장 (`docs/diagrams/interactive_schematic.html` 수정)
    - 상단 컨트롤 바 추가: API Endpoint 입력, root_module, scope 선택(chip/module/signal), depth, signal_filter, "Load from API" 버튼
    - 3-view 모드 전환: Chip View / Module View / Signal View
    - 노드 타입별 색상: Module(white), Port(yellow), Signal(blue), ClockDomain(purple), Parameter(green)
    - 포트 방향별 테두리 스타일: input(실선), output(점선), inout(이중선)
    - 노드 클릭 → 연결 하이라이트 + tooltip에 properties 전체 표시
    - `neptune_fallback=true` / `truncated=true` 시 경고 배너 표시
    - 초기 로드: 내장 프로토타입 데이터로 렌더링 (기존 nodes/links 유지)
    - D3.js 로컬 복사본 선택적 참조 구조 (`docs/diagrams/vendor/d3.v7.min.js` fallback)
    - _Requirements: 33.1, 33.2, 33.3, 33.4, 33.5, 33.6, 33.7, 33.8, 33.9_

  - [x]* 30.5 Property 42 테스트 작성: Graph Export API 응답 구조
    - **Property 42: Graph Export API 응답 구조**
    - **Validates: Requirements 32.1, 32.5, 32.6, 32.7**
    - 응답에 nodes/edges/metadata 필드 존재, scope 유효값 검증, 노드 상한 1000개, Neptune 실패 시 neptune_fallback=true + 빈 그래프 검증


- [x] 31. Phase 9: HDD Merge 개선 — 실명 복구 + Topic 전파
  - [x] 31.1 HDD Merger 실명 복구 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `_resolve_placeholders(markdown_text, claims_used, topic)` 함수 추가
    - placeholder 토큰 정규식: `r'\{(MODULE|INSTANCE|SIGNAL|PORT)_[A-Z0-9_]+\}'`
    - 복구 소스 우선순위: ① claim의 parser_source별 원본 이름 → ② RTL_OpenSearch_Index 검색 → ③ Claim_DB statement 원본
    - 동일 토큰 다중 후보 시: confidence 최고 → 동률 시 최신 created_at 선택
    - 복구 불가 시 HTML 주석 `<!-- NAME_RESOLUTION_FAILED: {TOKEN} -->` 삽입
    - 응답 metadata에 `unresolved_placeholders` 배열 포함
    - `generate_hdd_section()` 함수 내에서 마크다운 생성 후 `_resolve_placeholders()` 호출 통합
    - _Requirements: 34.1, 34.2, 34.3_

  - [x] 31.2 HDD Topic 전파 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `generate_hdd_section()` 함수 확장: 생성된 HDD 섹션에 `parent_topics` 메타데이터 저장
    - `_mark_stale_parents(topic)` 함수 추가: 해당 topic을 parent_topics에 포함하는 상위 섹션의 `stale=true` + `last_child_update_at` 설정
    - `approve_claim()` 함수 확장: claim approve 시 해당 topic의 HDD 섹션 stale 마킹 호출
    - `max_propagation_depth=5` 상한 적용 (무한 루프 방지)
    - 전파 체인 CloudWatch 구조화 로그: `{event: "hdd_propagation", root_topic, propagated_to, depth, duration_ms}`
    - _Requirements: 34.4, 34.5, 34.7, 34.10_

  - [x] 31.3 Stale HDD 일괄 재생성 엔드포인트 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `regenerate_stale_hdd(event)` 함수 추가
    - Seoul_S3 `published/` 접두사에서 `stale=true` 메타데이터를 가진 섹션 스캔
    - 각 stale 섹션에 대해 `generate_hdd_section()` 재호출 + `_resolve_placeholders()` 적용
    - 응답: `{sections_regenerated, sections_skipped, unresolved_placeholder_count, execution_time_ms}`
    - `handler()` 라우팅에 POST `/rag/hdd/regenerate-stale` 추가
    - _Requirements: 34.6, 34.9_

  - [x] 31.4 MCP Bridge regenerate_stale_hdd 도구 추가 (`mcp-bridge/server.js` 수정)
    - `regenerate_stale_hdd` 도구 추가: 파라미터 없음 → POST /rag/hdd/regenerate-stale
    - 응답에 `execution_time_ms`, `sections_regenerated`, `sections_skipped`, `unresolved_placeholder_count` 포함
    - _Requirements: 34.8_

  - [x]* 31.5 Property 43 테스트 작성: Placeholder 복구 완전성
    - **Property 43: Placeholder 복구 완전성**
    - **Validates: Requirements 34.1, 34.2, 34.9**
    - 재생성 후 마크다운에 `{MODULE_*}`/`{INSTANCE_*}`/`{SIGNAL_*}`/`{PORT_*}` 패턴 미존재 또는 HTML 주석 형태만 존재, unresolved_placeholders 배열 정확성 검증

  - [x]* 31.6 Property 44 테스트 작성: Topic 전파 무한 루프 방지
    - **Property 44: Topic 전파 무한 루프 방지**
    - **Validates: Requirements 34.5, 34.7**
    - 순환 parent_topics 구조에서 max_propagation_depth=5 초과 시 재생성 건너뛰기 + WARNING 로그, stale 마킹 정확성 검증


- [x] 32. Phase 9 Checkpoint — 전체 Phase 9 통합 테스트
  - Ensure all tests pass, ask the user if questions arise.
  - Port Binding Parser: `.port(signal)` 추출 + concatenation + unconnected 동작 확인
  - Neptune CONNECTS_TO: 포트 바인딩 → 엣지 적재 + MERGE 중복 방지 동작 확인
  - Graph Export API: 3가지 scope 모드 + 노드 상한 + fallback 동작 확인
  - Schematic Viewer: 3-view 전환 + API 연동 + 경고 배너 동작 확인
  - HDD Merge: placeholder 복구 + topic 전파 + stale 재생성 동작 확인
  - `cd environments/app-layer/bedrock-rag/rtl_parser_src && py -m pytest -v`
  - `cd environments/app-layer/bedrock-rag && terraform validate`


- [ ] 33. Final Checkpoint - 전체 9 Phase 통합 테스트
  - 전체 시스템 통합 동작 확인 (Phase 1~9)
  - `cd environments/app-layer/bedrock-rag && terraform validate`
  - `cd environments/app-layer/knowledge-graph && terraform validate`
  - Content Fidelity 목표: v9.2 80% → v9.3 85~88% 달성 여부 확인
  - 포트 바인딩 기반 신호 추적 정확도 확인 (trace_signal_path 개선)
