# Implementation Plan: Enhanced RAG Optimization

## Overview

BOS-AI Private RAG 시스템을 검증된 지식 단위(Claim) 기반 답변 시스템으로 확장한다. 5개 Phase로 나누어 점진적으로 구현하며, 각 Phase는 이전 Phase의 결과물에 의존한다. Terraform IaC로 AWS 리소스를 관리하고, Python 3.12 Lambda 함수, Node.js MCP Bridge, Go 1.21 + gopter 속성 기반 테스트를 사용한다.

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

  - [ ]* 1.2 Property 23 테스트 작성: RTL S3 버킷 보안 구성
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

  - [ ]* 1.4 Property 24 테스트 작성: RTL Parser Lambda Terraform 구성
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

  - [ ]* 1.6 Property 1 테스트 작성: RTL 파싱 라운드트립
    - **Property 1: RTL 파싱 라운드트립**
    - **Validates: Requirements 2.2, 2.4, 2.9**
    - 유효한 Verilog/SystemVerilog 모듈 선언에 대해 parse → serialize → re-parse 동일 결과 검증

  - [ ]* 1.7 Property 2 테스트 작성: 토큰 Truncation 상한
    - **Property 2: 토큰 Truncation 상한**
    - **Validates: Requirements 2.11**
    - 임의 텍스트에 대해 truncate_to_tokens 출력이 8,000 토큰 이하, 짧은 입력은 동일 출력 검증

  - [ ]* 1.8 Property 3 테스트 작성: RTL 파싱 실패 에러 레코드
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

  - [ ]* 1.11 Property 4 테스트 작성: RTL OpenSearch 인덱스 매핑 완전성
    - **Property 4: OpenSearch 인덱스 매핑 완전성**
    - **Validates: Requirements 3.3, 3.4**
    - 8개 필드 존재 및 올바른 타입, knn_vector dimension=1024, engine=faiss, space_type=l2 검증

  - [x] 1.12 IAM Explicit Deny 정책 구성 (`environments/app-layer/bedrock-rag/lambda.tf` 수정)
    - Lambda_Handler IAM 역할에 Explicit Deny 정책 추가
    - Seoul_S3 `documents/*` 접두사에 대한 `s3:PutObject`, `s3:DeleteObject`, `s3:DeleteObjectVersion`, `s3:BypassGovernanceRetention`, `s3:PutObjectRetention` 거부
    - RTL_S3_Bucket `rtl-sources/*` 접두사에 대한 동일 5개 액션 거부
    - _Requirements: 12.1, 13.9_

  - [ ]* 1.13 Property 22 테스트 작성: IAM Explicit Deny
    - **Property 22: IAM Explicit Deny로 Source of Truth 보호**
    - **Validates: Requirements 13.9**
    - Lambda_Handler IAM 정책에 Source of Truth 버킷 PutObject/DeleteObject/DeleteObjectVersion/BypassGovernanceRetention/PutObjectRetention Explicit Deny 존재 검증

- [ ] 2. Phase 1 Checkpoint
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

  - [ ]* 3.2 Property 5 테스트 작성: Claim_DB Terraform 구성 완전성
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

  - [ ]* 3.4 Property 6 테스트 작성: Claim 필드 유효성 검증
    - **Property 6: Claim 필드 유효성 검증**
    - **Validates: Requirements 5.1, 5.6, 5.7, 7.2**
    - evidence 빈 배열 거부, confidence 범위, topic 형식, statement 길이, source_chunk 길이 검증

  - [ ]* 3.5 Property 7 테스트 작성: Claim 상태 전이 규칙
    - **Property 7: Claim 상태 전이 규칙**
    - **Validates: Requirements 5.2, 5.3**
    - 6가지 허용 전이 성공, 불허 전이 HTTP 409, 초기 status=draft 검증

  - [ ]* 3.6 Property 8 테스트 작성: Claim 버전 불변성
    - **Property 8: Claim 버전 불변성**
    - **Validates: Requirements 5.4**
    - 업데이트 시 version+1, 이전 version 레코드 유지(삭제 안 됨) 검증

  - [ ]* 3.7 Property 9 테스트 작성: Optimistic Locking 동시성 제어
    - **Property 9: Optimistic Locking 동시성 제어**
    - **Validates: Requirements 5.9, 5.10**
    - ConditionExpression 포함, ConditionalCheckFailedException 시 최대 3회 재시도 검증

  - [ ]* 3.8 Property 10 테스트 작성: Contradiction Score 기반 상태 변경
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

  - [ ]* 3.10 Property 13 테스트 작성: 문서 메타데이터 확장 구조
    - **Property 13: 문서 메타데이터 확장 구조**
    - **Validates: Requirements 6.2, 6.5**
    - topic/variant/doc_version/source 필드 존재 및 기본값, source 허용 값 검증

  - [ ]* 3.11 Property 14 테스트 작성: 파일 경로에서 Topic 자동 추출
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

  - [ ]* 3.13 Property 15 테스트 작성: Claim Ingestion 페이지네이션 및 카운팅
    - **Property 15: Ingestion 페이지네이션 및 카운팅**
    - **Validates: Requirements 7.3, 7.4, 7.7**
    - 100건 상한, 응답 필드 존재, has_more 시 continuation_token, 신규 claim status=draft/version=1 검증

- [ ] 4. Phase 2 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - `terraform validate` 실행
  - Claim CRUD 함수 및 Ingestion 파이프라인 동작 확인


- [ ] 5. Phase 3: MCP Tool 분리 및 Verification Pipeline
  - [ ] 5.1 MCP Tool API 엔드포인트 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `search_archive()`: query(필수) + topic/source/max_results(선택) → Bedrock_KB 검색 + 필터
    - `handler()` 라우팅에 POST `/rag/search-archive`, `/rag/get-evidence`, `/rag/list-verified-claims` 추가
    - 잘못된 파라미터 시 HTTP 400 + 누락/잘못된 파라미터 명시
    - API Gateway에 3개 라우트 추가 (`environments/app-layer/bedrock-rag/api-gateway.tf` 수정)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 5.2 MCP Bridge 도구 확장 (`mcp-bridge/server.js` 수정)
    - `search_archive` 도구 추가: query(필수), topic/source/max_results(선택) → POST /rag/search-archive
    - `get_evidence` 도구 추가: claim_id(필수) → POST /rag/get-evidence
    - `list_verified_claims` 도구 추가: topic(필수) → POST /rag/list-verified-claims
    - 모든 도구 응답에 `execution_time_ms` 필드 포함
    - _Requirements: 8.1, 8.2, 8.3, 8.6_

  - [ ]* 5.3 Property 21 테스트 작성: MCP Tool 응답 실행 시간 포함
    - **Property 21: MCP Tool 응답 실행 시간 포함**
    - **Validates: Requirements 8.6**
    - 모든 MCP Tool 응답에 execution_time_ms 존재 및 양의 정수 검증

  - [ ] 5.4 Verification Pipeline 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `verification_pipeline(query, variant=None)`: 8단계 순차 실행
    - (1) 질문 수신 → (2) Foundation_Model로 topic 식별(최대 3개) → (3) topic-index GSI로 verified claim 조회 → (4) evidence 근거 추적 → (5) 충돌 검사(conflicted claim 존재 시 경고) → (6) 버전 확인(is_latest=true) → (7) Foundation_Model로 답변 생성 → (8) evidence 첨부
    - variant 파라미터 포함 시 topic-variant-index GSI 사용
    - Claim_DB에 관련 claim 없으면 Bedrock_KB 폴백 (fallback=true)
    - 응답에 verification_metadata 포함: claims_used, topics_identified, has_conflicts, pipeline_execution_time_ms, fallback
    - 각 단계 실행 시간 CloudWatch 구조화 로그 기록
    - 기존 `handle_query()` 수정: Verification Pipeline 우선 실행, 폴백 시 기존 Bedrock_KB 검색
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_

  - [ ]* 5.5 Property 16 테스트 작성: Verification Pipeline 응답 구조
    - **Property 16: Verification Pipeline 응답 구조**
    - **Validates: Requirements 9.2, 9.3, 9.6, 9.7**
    - verification_metadata 필드 존재, topics_identified 최대 3개, claim 없으면 fallback=true, verified claim만 사용 검증

  - [ ]* 5.6 Property 17 테스트 작성: 충돌 경고 포함
    - **Property 17: 충돌 경고 포함**
    - **Validates: Requirements 9.4**
    - conflicted claim 존재 시 has_conflicts=true + 답변에 충돌 경고 메시지 포함 검증

  - [ ] 5.7 3계층 RAG 분리 IAM 역할 구성 (`environments/app-layer/bedrock-rag/lambda.tf` 수정)
    - RTL_Parser_Lambda: RTL_S3_Bucket 읽기 + RTL_OpenSearch_Index 쓰기만
    - Lambda_Handler: Seoul_S3 읽기/쓰기 + Claim_DB 읽기/쓰기 + Bedrock_KB 호출만
    - CloudWatch PutMetricData 권한 추가 (BOS-AI/ClaimDB 네임스페이스)
    - 단방향 데이터 흐름 보장: Source_of_Truth → Verified_Knowledge → Serving
    - _Requirements: 12.3, 12.4, 12.5, 12.6, 15.8_

- [ ] 6. Phase 3 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - MCP Bridge 도구 3개 + Verification Pipeline 통합 동작 확인


- [ ] 7. Phase 4: 문서 생성 및 Human Review Gate
  - [ ] 7.1 Human Review Gate 함수 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `approve_claim()`: claim_id + version + approved_by → approval_status='approved', approved_at 설정
    - `reject_claim()`: claim_id + version + rejected_by + rejection_reason(선택) → approval_status='rejected'
    - `handler()` 라우팅에 POST `/rag/claims/approve`, `/rag/claims/reject` 추가
    - API Gateway에 2개 라우트 추가 (`environments/app-layer/bedrock-rag/api-gateway.tf` 수정)
    - publishable 계산: status='verified' AND approval_status='approved'인 경우만 true
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.6_

  - [ ]* 7.2 Property 18 테스트 작성: Human Review Gate 승인 생명주기
    - **Property 18: Human Review Gate 승인 생명주기**
    - **Validates: Requirements 14.2, 14.3, 14.4, 14.5, 14.6, 14.7**
    - verified 전이 시 pending_review, approve 시 approved, reject 시 rejected, publishable 조건, 미승인 claim HTTP 403 검증

  - [ ] 7.3 HDD 섹션 생성 및 마크다운 출판 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `generate_hdd_section()`: topic의 verified+approved claim 조회 → Foundation_Model로 HDD 마크다운 생성
    - evidence 각주 포함 (include_evidence=true), 면책 조항 자동 포함
    - `publish_markdown()`: Seoul_S3 `published/` 접두사에 저장, 메타데이터 자동 생성(source='system_generated')
    - critical topic claim은 approval_status='approved'만 사용, 미승인 시 HTTP 403
    - `handler()` 라우팅에 POST `/rag/generate-hdd`, `/rag/publish-markdown` 추가
    - API Gateway에 2개 라우트 추가
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 14.5, 14.7_

  - [ ] 7.4 MCP Bridge 문서 생성 도구 확장 (`mcp-bridge/server.js` 수정)
    - `generate_hdd_section` 도구 추가: topic(필수), section_title(필수), include_evidence(선택, 기본 true) → POST /rag/generate-hdd
    - `publish_markdown` 도구 추가: content(필수), filename(필수), topic(선택) → POST /rag/publish-markdown
    - 모든 도구 응답에 `execution_time_ms` 포함
    - _Requirements: 10.1, 10.4_

- [ ] 8. Phase 4 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - Human Review Gate + HDD 생성 + 마크다운 출판 통합 동작 확인


- [ ] 9. Phase 5: Cross-Check 파이프라인 및 KPI 모니터링
  - [ ] 9.1 Cross-Check 파이프라인 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
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

  - [ ]* 9.2 Property 11 테스트 작성: Validation Risk Score 계산 및 상태 전이
    - **Property 11: Validation Risk Score 계산 및 상태 전이**
    - **Validates: Requirements 11.5, 11.6, 11.7, 11.8**
    - 공식 정확성, 임계값별 상태 전이(< 0.3 verified, 0.3~0.7 draft, >= 0.7 conflicted) 검증

  - [ ]* 9.3 Property 12 테스트 작성: Rule-Based Checker 검증
    - **Property 12: Rule-Based Checker 검증**
    - **Validates: Requirements 11.4**
    - S3 존재 확인, statement 길이, topic 형식 검증 → 모두 통과 시 score_3=1.0, 실패 시 < 1.0 검증

  - [ ]* 9.4 Property 19 테스트 작성: Cross-Check 결과 카운팅 일관성
    - **Property 19: Cross-Check 결과 카운팅 일관성**
    - **Validates: Requirements 11.9**
    - claims_verified + claims_conflicted + claims_pending == total_processed 검증

  - [ ] 9.5 KPI Metrics 발행 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - `publish_kpi_metrics()`: CloudWatch 커스텀 메트릭 발행 (네임스페이스: BOS-AI/ClaimDB)
    - ClaimIngestionSuccessRate: ingest_claims 완료 시 발행
    - ClaimVerificationPassRate + ContradictionDetectionRate: cross_check_claims 완료 시 발행
    - BedrockKBFallbackRate: Verification Pipeline 폴백 시 증가
    - AvgEvidenceCountPerAnswer: Verification Pipeline 답변 생성 시 발행
    - StaleClaimRatio: 30일 미검증 verified claim 비율 (질의 처리 시 또는 스케줄)
    - TopicCoverageRatio: verified claim 존재 topic 비율 (질의 처리 시 또는 스케줄)
    - ingest_claims, cross_check_claims, verification_pipeline 함수에 메트릭 발행 호출 통합
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7_

  - [ ]* 9.6 Property 20 테스트 작성: KPI 메트릭 계산 공식
    - **Property 20: KPI 메트릭 계산 공식**
    - **Validates: Requirements 15.2, 15.3, 15.4, 15.5, 15.6, 15.7**
    - 7개 메트릭 계산 공식 정확성, BOS-AI/ClaimDB 네임스페이스 발행 검증

  - [ ] 9.7 Terraform 변수 및 IAM 최종 정리 (`environments/app-layer/bedrock-rag/variables.tf` 수정)
    - Claim DB 테이블명, RTL S3 버킷명 등 신규 변수 추가
    - Lambda_Handler IAM에 `cloudwatch:PutMetricData` 권한 추가 (BOS-AI/ClaimDB 네임스페이스)
    - 모든 신규 리소스 필수 태그 최종 확인
    - _Requirements: 13.6, 15.8_

- [ ] 10. Final Checkpoint - 전체 테스트 통과 확인
  - Ensure all tests pass, ask the user if questions arise.
  - `cd environments/app-layer/bedrock-rag && terraform validate`
  - `cd tests && go test -v ./properties/ -run TestEnhancedRagOptimization -count=1`
  - 전체 5 Phase 통합 동작 확인


- [ ] 11. Phase 6: RTL Knowledge Graph (Neptune Graph DB)
  - [ ] 11.1 Neptune Terraform 모듈 구현 (`modules/ai-workload/graph-knowledge/`)
    - `neptune.tf`: aws_neptune_cluster + aws_neptune_cluster_instance (db.t4g.medium)
    - `security_group.tf`: Inbound TCP 8182를 RTL_Parser_Lambda SG와 Lambda_Handler SG에서만 허용 (내부망 전체 허용 금지)
    - `variables.tf`, `outputs.tf`
    - KMS CMK 암호화 (`storage_encrypted = true`)
    - 필수 태그 적용
    - _Requirements: 16.1, 16.2, 16.3, 16.14_

  - [ ] 11.2 Neptune 환경 배포 구성 (`environments/app-layer/knowledge-graph/`)
    - `remote_state.tf`: network-layer 상태 참조 (VPC ID, Subnet ID)
    - `main.tf`: modules/ai-workload/graph-knowledge 호출, vpc_security_group_ids와 neptune_subnet_group_name은 terraform_remote_state 참조
    - `iam_readonly.tf`: LLM/MCP용 Read-Only Role (neptune-db:ReadDataViaQuery만)
    - `iam_write.tf`: RTL_Parser_Lambda용 Write Role (neptune-db:WriteDataViaQuery) — 태스크 1.3의 RTL Parser Lambda IAM에 추가
    - `variables.tf`, `outputs.tf`
    - VPC Endpoint 네트워크 격리
    - _Requirements: 16.4, 16.5, 16.15_

  - [ ] 11.3 RTL Parser Lambda → Neptune 관계 적재 확장 (`rtl_parser_src/handler.py` 수정)
    - 파싱 결과에서 관계 추출: Module→Module(INSTANTIATES), Module→Port(HAS_PORT), Port→Port(CONNECTS_TO), Parameter→Parameter(PROPAGATES_TO)
    - Neptune에 노드/엣지로 적재 (Gremlin 또는 openCypher)
    - 노드 타입: Module, Port, Signal, Parameter, ClockDomain
    - 엣지 타입: INSTANTIATES, HAS_PORT, CONNECTS_TO, DRIVES, PROPAGATES_TO, BELONGS_TO_DOMAIN
    - _Requirements: 16.6, 16.7, 16.8_

  - [ ] 11.4 MCP Bridge Graph 도구 추가 (`mcp-bridge/server.js` 수정)
    - `trace_signal_path`: module_name(필수) + signal_name(필수) → 신호 전파 경로 반환
    - `find_instantiation_tree`: module_name(필수) + depth(선택, 기본3) → 인스턴스화 트리 반환
    - `find_clock_crossings`: module_name(필수) → 클럭 도메인 크로싱 신호 목록 반환
    - _Requirements: 16.9, 16.10, 16.11_

  - [ ] 11.5 3저장소 통합 질의 구현 (`environments/app-layer/bedrock-rag/lambda_src/index.py` 수정)
    - Verification Pipeline 확장: asyncio를 사용하여 Graph DB(Neptune) + Claim DB + OpenSearch 3개 DB를 병렬 비동기 호출
    - 개별 DB 쿼리 Timeout: 30초 제한
    - Neptune 쿼리 실패/Timeout 시 Fallback: OpenSearch + Claim DB 결과만으로 답변 생성 (시스템 중단 없음)
    - Neptune Fallback 발생 시 `verification_metadata.neptune_fallback = true` 설정
    - _Requirements: 16.12_

  - [ ]* 11.7 Property 25 테스트 작성: Neptune 통합 질의 Fallback 및 병렬 호출
    - **Property 25: Neptune 통합 질의 Fallback 및 병렬 호출**
    - **Validates: Requirements 16.3, 16.5, 16.12, 16.15**
    - 3개 DB 병렬 비동기 호출, 개별 Timeout 30초, Neptune 실패 시 Fallback + neptune_fallback=true, Neptune SG 8182 포트 제한 검증

  - [ ] 11.6 PyVerilog AST 파서 교체 준비 (`rtl_parser_src/handler.py`)
    - Phase 6b: always_ff/always_comb 블록 분석 → 클럭 도메인 식별
    - assign 문 분석 → 신호 구동 관계(DRIVES) 추출
    - ECR 컨테이너 이미지 배포 전환
    - _Requirements: 16.13_

- [ ] 12. Phase 6 Checkpoint
  - Ensure all tests pass, ask the user if questions arise.
  - Neptune Cluster + 관계 추출 + 3저장소 통합 질의 동작 확인
  - `terraform validate` (knowledge-graph 환경)

- [ ] 13. Final Checkpoint - 전체 6 Phase 통합 테스트
  - 전체 시스템 통합 동작 확인
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
- Confluence/Jira는 Cloud 환경이므로 별도 연동 방식 검토 (이 스펙 범위 외)
- Codebeamer 연동은 Spec 6 (codebeamer-aspice-rag-integration)에서 처리

