# 구현 계획: RTL 자동 분석 파이프라인

## 개요

RTL 자동 분석 파이프라인의 구현을 5단계로 진행한다: (1) 순수 로직 함수 + PBT 테스트, (2) Terraform 인프라, (3) Lambda 코드 확장, (4) LLM 통합, (5) 통합 테스트. Python 3.12(Lambda), Go 1.21 + gopter(PBT), Terraform(인프라)을 사용한다.

## 배포 및 E2E 검증 결과 (2026-04-17)

| 항목 | 결과 |
|------|------|
| RTL 재파싱 | ✅ 8,107건 (pipeline_id=tt_20260221, analysis_type=module_parse) |
| Hierarchy Extraction | ✅ 80개 계층 노드 |
| Topic Classification | ✅ 11개 토픽, 530개 모듈 (Overlay 124, FPU 140, NoC 84, TDMA 54, EDC 30 등) |
| Claim Generation | ✅ 78건 (Bedrock Claude 자동 생성, 11개 토픽별 분할 실행) |
| HDD Generation | ✅ 66개 섹션 (11개 토픽 × 6개 섹션) |
| MCP search_rtl | ✅ Obot E2E 동작 확인 (analysis_type=claim 필터로 Claim 검색 성공) |
| Clock Domain | ⏱️ 300초 타임아웃 (S3 9,465개 파일 → 배치 분할 필요) |
| Dataflow | ⏱️ 미실행 (동일 이슈) |

### 배포 중 발견된 이슈 및 해결

1. **AOSS 제약**: `_update_by_query`, `_delete_by_query` 미지원 → 인덱스 삭제/재생성 방식으로 우회
2. **AOSS 문서 ID PUT 미지원**: POST /_doc (ID 자동 생성) 사용
3. **OpenSearch 페이지네이션**: AOSS scroll API 미지원 → search_after 방식 구현
4. **Lambda 300초 타임아웃**: 토픽별 분할 실행으로 해결 (Claim/HDD), S3 파일 배치 처리는 추가 최적화 필요
5. **IAM 권한 누락**: s3:ListBucket, lambda:InvokeFunction(self), bedrock:InvokeModel(Claude) 수동 추가
6. **MCP Bridge**: 온프레미스 server.js에 search_rtl 도구 + analysis_type 파라미터 추가

### v3 R2 테스트 발견 이슈 (2026-04-23)

| 이슈 | 설명 | 영향 | 해결 태스크 |
|------|------|------|------------|
| #1 MCP Bridge max_results 하드코딩 | server.js가 max_results: 5 하드코딩, Lambda는 20으로 올렸지만 MCP Bridge가 항상 5로 전송 | 검색 결과 5건 제한 | Task 22 |
| #2 Claim 귀속 오류 | HDD 86건이 전부 trinity_noc2axi_router_ne_opt_FBLC 단일 모듈에 편중. _reg_inner/_wrap 레지스터 모듈에서만 claim 생성 | HDD 품질 저하, 토픽별 다양성 없음 | Task 21 |
| #3 토픽 분류 불완전 | NIU 토픽 0건(NoC에 포함), Power/Memory 토픽 없음 | 토픽 커버리지 부족 | Task 20 |
| #4 포트 비트폭 미추출 | parse_rtl_to_ast()가 [SizeX-1:0] 같은 배열 폭을 추출 안 함 | 포트 정보 불완전 | Task 19 |
| #5 MCP Bridge 파라미터 미전달 | analysis_type, pipeline_id 파라미터가 Lambda에 전달되지 않음 | 필터링 검색 불가 | Task 22 |
| #6 토픽 재분류 300초 타임아웃 | handle_topic_classification()이 8,107건 × (_update_document + _index_document) = ~16,000 HTTP 요청으로 300초 초과 | 토픽 재분류 불가 | Task 23.3 |

## Tasks

- [x] 1. 순수 로직 함수 구현 및 속성 기반 테스트
  - [x] 1.1 Pipeline_ID 파싱 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/pipeline_utils.py` 생성
    - `extract_pipeline_id(s3_key)` 함수: S3 키 `rtl-sources/{chip_type}_{date}/...`에서 `pipeline_id`, `chip_type`, `snapshot_date` 추출
    - 무효한 경로 시 `unknown_unknown` 기본값 반환
    - _Requirements: 1.6, 10.1_

  - [ ]* 1.2 Pipeline_ID 파싱 속성 테스트 작성
    - `tests/properties/rtl_pipeline_id_properties_test.go` 생성
    - **Property 1: Pipeline_ID 파싱 정확성**
    - **Validates: Requirements 1.6, 10.1**
    - gopter로 랜덤 chip_type + date 조합의 S3 키를 생성하여 추출 결과 검증

  - [x] 1.3 계층 트리 구축 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/hierarchy.py` 생성
    - `build_hierarchy(modules)` 함수: 모듈 리스트에서 parent-child 관계 그래프 구축, 루트 모듈 식별, DFS로 hierarchy_path 생성
    - 각 노드에 module_name, instance_name, hierarchy_path, clock_signals, reset_signals, memory_instances 필드 포함
    - 순환 참조 감지 및 해당 브랜치 절단 로직 포함
    - `serialize_hierarchy_json(tree)`, `serialize_hierarchy_csv(tree)` 직렬화 함수 구현
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 1.4 계층 트리 속성 테스트 작성
    - `tests/properties/rtl_hierarchy_properties_test.go` 생성
    - **Property 2: 계층 트리 라운드트립** — 트리에서 역추출한 parent-child 관계가 원본과 동일
    - **Validates: Requirements 2.1, 2.6**
    - **Property 3: 계층 노드 완전성** — 모든 노드에 필수 필드(module_name, instance_name, hierarchy_path, clock_signals, reset_signals) 존재
    - **Validates: Requirements 2.2, 2.3**
    - **Property 4: 계층 직렬화 라운드트립** — JSON 직렬화/역직렬화 동일성, CSV/JSON 모듈 집합 동일
    - **Validates: Requirements 2.5**

  - [x] 1.5 클럭 도메인 분석 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/clock_domain.py` 생성
    - `extract_clock_domains(rtl_content)` 함수: `always_ff @(posedge <clock>)` 및 `always @(posedge <clock>)` 패턴에서 클럭 신호 추출
    - `classify_clock_domain(signal_name)` 함수: 클럭 신호를 도메인 그룹으로 분류 (ai_clock_domain, noc_clock_domain, dm_clock_domain, ref_clock_domain, unclassified_clock)
    - `detect_cdc_boundary(clock_domains)` 함수: 2개 이상 도메인 감지 시 CDC 경계 표시
    - _Requirements: 3.1, 3.2, 3.3, 3.5_

  - [ ]* 1.6 클럭 도메인 속성 테스트 작성
    - `tests/properties/rtl_clock_domain_properties_test.go` 생성
    - **Property 5: 클럭 추출 및 도메인 분류** — always 블록에서 클럭 추출 정확성 + 도메인 분류 정확성
    - **Validates: Requirements 3.1, 3.2, 3.5**
    - **Property 6: CDC 경계 감지** — 도메인 2개 이상이면 true, 1개 이하이면 false
    - **Validates: Requirements 3.3**

  - [x] 1.7 데이터 흐름 추적 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/dataflow.py` 생성
    - `extract_port_mappings(rtl_content)` 함수: `.port_name(signal_name)` 패턴 파싱, 비트 폭 `[MSB:LSB]` 추출
    - `detect_width_mismatch(parent_width, child_width)` 함수: 비트 폭 불일치 감지
    - 각 연결에 parent_signal, child_module, child_port, direction, bit_width, width_mismatch 필드 포함
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [ ]* 1.8 데이터 흐름 속성 테스트 작성
    - `tests/properties/rtl_dataflow_properties_test.go` 생성
    - **Property 7: 데이터 흐름 연결 추출 완전성** — 모든 포트 매핑 추출 + 필수 필드 존재
    - **Validates: Requirements 4.1, 4.2, 4.3**
    - **Property 8: 비트 폭 불일치 감지** — 불일치 시 true, 일치 시 false
    - **Validates: Requirements 4.5**

  - [x] 1.9 토픽 분류 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/topic_classifier.py` 생성
    - `classify_topic(file_path, module_name)` 함수: TOPIC_RULES 딕셔너리 기반 파일 경로 + 모듈명 패턴 매칭
    - 12개 토픽 카테고리 지원 (NoC, FPU, SFPU, TDMA, Overlay, EDC, Dispatch, L1_Cache, Clock_Reset, DFX, NIU, SMN)
    - 복수 토픽 매칭 시 모두 반환, 미매칭 시 `unclassified` 반환
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 1.10 토픽 분류 속성 테스트 작성
    - `tests/properties/rtl_topic_classifier_properties_test.go` 생성
    - **Property 9: 토픽 분류 정확성** — 패턴 매칭 시 올바른 토픽, 복수 매칭 시 모두 할당, 미매칭 시 unclassified
    - **Validates: Requirements 5.1, 5.3, 5.4**

  - [x] 1.11 Claim 스키마 검증 및 토큰 분할 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/claim_utils.py` 생성
    - `validate_claim(claim)` 함수: 필수 필드 존재 + confidence_score 범위(0.0~1.0) + claim_type 유효성 검증
    - `split_module_groups(modules, max_tokens=100000)` 함수: 모듈 그룹을 토큰 제한 이하로 분할, 모든 모듈이 정확히 하나의 청크에 포함
    - _Requirements: 6.2, 6.4_

  - [ ]* 1.12 Claim 스키마 및 토큰 분할 속성 테스트 작성
    - `tests/properties/rtl_claim_properties_test.go` 생성
    - **Property 10: Claim 스키마 유효성** — 필수 필드 존재 + 값 범위 검증
    - **Validates: Requirements 6.2**
    - **Property 11: LLM 입력 토큰 분할** — 모든 청크 100K 토큰 이하 + 모든 모듈 포함
    - **Validates: Requirements 6.4**

  - [x] 1.13 검색 쿼리 빌더 및 Variant Delta 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/search_utils.py` 생성
    - `build_search_query(params)` 함수: topic, clock_domain, hierarchy_path, pipeline_id 파라미터로 OpenSearch 쿼리 생성, 빈 파라미터 제외
    - `environments/app-layer/bedrock-rag/rtl_parser_src/variant_delta.py` 생성
    - `extract_variant_delta(baseline_modules, variant_modules)` 함수: 모듈 추가/삭제, 파라미터 변경, 인스턴스 추가/삭제 식별
    - _Requirements: 8.3, 9.2_

  - [ ]* 1.14 검색 쿼리 및 Variant Delta 속성 테스트 작성
    - `tests/properties/rtl_search_variant_properties_test.go` 생성
    - **Property 14: 검색 쿼리 구성 정확성** — 유효한 OpenSearch 쿼리 + 빈 파라미터 제외
    - **Validates: Requirements 8.3**
    - **Property 15: Variant Delta 추출 정확성** — 변경 항목 정확 식별 + 미변경 항목 미포함
    - **Validates: Requirements 9.2**

- [x] 2. Checkpoint - 순수 로직 함수 및 PBT 테스트 검증
  - 모든 테스트 통과 확인, 문제 발생 시 사용자에게 질문

- [x] 3. Terraform 인프라 구성
  - [x] 3.1 Step Functions 상태 머신 Terraform 리소스 생성
    - `environments/app-layer/bedrock-rag/step-functions.tf` 생성
    - `aws_sfn_state_machine.analysis_orchestrator` 리소스: Standard Workflow, 6단계 분석 파이프라인 정의
    - 각 단계별 최대 2회 재시도 + 실패 시 건너뛰기 로직 포함
    - Step Functions 실행 이름에 Pipeline_ID 포함
    - _Requirements: 1.2, 1.3, 1.4, 1.7_

  - [x] 3.2 Step Functions IAM 역할 및 정책 생성
    - `step-functions.tf`에 IAM 리소스 추가
    - `aws_iam_role.sfn_analysis`: Step Functions 실행 역할
    - `aws_iam_role_policy.sfn_lambda_invoke`: Lambda invoke 권한
    - `aws_iam_role_policy.sfn_dynamodb`: DynamoDB 상태 기록 권한
    - 최소 권한 원칙 준수
    - _Requirements: 11.1, 11.6_

  - [x] 3.3 RTL Parser Lambda IAM 정책 확장
    - `environments/app-layer/bedrock-rag/rtl-parser-lambda.tf` 수정
    - `aws_iam_role_policy.rtl_parser_dynamodb` 확장: PutItem + UpdateItem + Query 권한 추가
    - `aws_iam_role_policy.rtl_parser_bedrock` 확장: Claude 모델 InvokeModel 권한 추가
    - `aws_iam_role_policy.rtl_parser_sfn` 신규: Step Functions StartExecution 권한
    - _Requirements: 11.2, 11.4, 11.5_

  - [x] 3.4 RTL Parser Lambda 환경 변수 확장
    - `environments/app-layer/bedrock-rag/rtl-parser-lambda.tf`의 `aws_lambda_function.rtl_parser` 수정
    - 환경 변수 추가: STEP_FUNCTIONS_ARN, ANALYSIS_PIPELINE_ID, CLAUDE_MODEL_ID, CLAIM_DB_TABLE
    - _Requirements: 1.6, 6.1, 11.2_

  - [x] 3.5 CloudWatch 로그 그룹 및 알람 생성
    - `environments/app-layer/bedrock-rag/step-functions.tf`에 추가
    - `aws_cloudwatch_log_group.sfn_analysis`: Step Functions 실행 로그
    - `aws_cloudwatch_metric_alarm.analysis_error_rate`: 분석 에러율 10% 초과 알람
    - _Requirements: 1.3, 11.6_

  - [ ]* 3.6 Terraform 리소스 태깅 속성 테스트 작성
    - `tests/properties/rtl_pipeline_infra_properties_test.go` 생성
    - **Property 17: Terraform 리소스 태깅** — 모든 리소스에 Project, Environment, ManagedBy 태그 존재
    - **Validates: Requirements 11.6**
    - step-functions.tf, rtl-parser-lambda.tf의 리소스 블록 검증

- [x] 4. Checkpoint - Terraform 인프라 검증
  - `terraform validate` 및 `tflint` 통과 확인, 문제 발생 시 사용자에게 질문

- [x] 5. Lambda 코드 확장 — 분석 파이프라인 핸들러
  - [x] 5.1 RTL Parser Lambda에 Pipeline_ID 추출 통합
    - `environments/app-layer/bedrock-rag/rtl_parser_src/handler.py` 수정
    - `_process_rtl_file()` 함수에 `extract_pipeline_id()` 호출 추가
    - 파싱 결과에 `pipeline_id`, `chip_type`, `snapshot_date` 메타데이터 포함
    - OpenSearch 문서에 `pipeline_id`, `analysis_type=module_parse` 필드 추가
    - DynamoDB `rag-extraction-tasks` 테이블에 파싱 완료 이벤트 기록
    - _Requirements: 1.1, 1.6, 8.1, 8.4_

  - [x] 5.2 분석 단계 핸들러 구현 — Hierarchy Extractor
    - `environments/app-layer/bedrock-rag/rtl_parser_src/analysis_handler.py` 생성
    - `handle_hierarchy_extraction(event)` 함수: OpenSearch에서 Pipeline_ID의 모든 파싱 결과 조회 → `build_hierarchy()` 호출 → JSON/CSV를 S3 `rtl-parsed/hierarchy/{pipeline_id}/`에 저장 → OpenSearch에 `analysis_type=hierarchy` 문서 인덱싱
    - DynamoDB 상태 업데이트 (in_progress → completed/failed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 5.3 분석 단계 핸들러 구현 — Clock Domain Analyzer
    - `analysis_handler.py`에 `handle_clock_domain_analysis(event)` 함수 추가
    - S3에서 RTL 소스 파일 배치 읽기 (100개씩) → `extract_clock_domains()` + `classify_clock_domain()` + `detect_cdc_boundary()` 호출
    - 결과를 OpenSearch에 `analysis_type=clock_domain` 문서로 인덱싱
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 5.4 분석 단계 핸들러 구현 — Dataflow Tracker
    - `analysis_handler.py`에 `handle_dataflow_tracking(event)` 함수 추가
    - 계층 트리의 각 parent 모듈에서 `extract_port_mappings()` 호출 → 신호 연결 그래프 생성
    - 결과를 OpenSearch에 `analysis_type=dataflow` 문서로 인덱싱
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 5.5 분석 단계 핸들러 구현 — Topic Classifier
    - `analysis_handler.py`에 `handle_topic_classification(event, context)` 함수 추가
    - 모든 모듈에 대해 `classify_topic()` 호출 → OpenSearch에 `analysis_type=topic` 문서 인덱싱
    - `_update_document()` 제거 (AOSS 부분 업데이트 비효율 + claim_generation이 직접 classify_topic 호출)
    - `batch_offset` 파라미터로 분할 실행 지원, 남은 시간 < 30초 시 비동기 Lambda 호출로 위임
    - 미분류 모듈에 대해 상위 모듈 토픽 상속 후보 제안
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 5.6 분석 오케스트레이터 Lambda 엔트리포인트 구현
    - `analysis_handler.py`에 `analysis_handler(event, context)` 메인 핸들러 추가
    - Step Functions에서 전달하는 `stage` 파라미터에 따라 적절한 분석 함수 디스패치
    - 공통 에러 처리: DynamoDB 상태 업데이트, CloudWatch 로그 기록
    - Lambda 300초 타임아웃 준수를 위한 배치 처리 로직
    - _Requirements: 1.2, 1.3, 1.4, 11.7_

- [x] 6. Checkpoint - Lambda 코드 확장 검증
  - 모든 테스트 통과 확인, 문제 발생 시 사용자에게 질문

- [x] 7. LLM 통합 — Claim Generator 및 HDD Section Generator
  - [x] 7.1 Claim Generator 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/claim_generator.py` 생성
    - `generate_claims(pipeline_id, topic, modules, analysis_results)` 함수: Bedrock Claude 3 Haiku 호출
    - 토픽별 모듈 그룹 단위로 LLM 호출, `split_module_groups()` 활용하여 100K 토큰 제한 준수
    - 타임아웃 60초, 최대 1회 재시도
    - 생성된 claim을 DynamoDB `bos-ai-claim-db` 테이블에 저장 + OpenSearch에 Titan Embeddings 벡터와 함께 인덱싱
    - `validate_claim()` 으로 스키마 검증 후 저장
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 7.2 HDD Section Generator 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/hdd_generator.py` 생성
    - `generate_hdd_section(pipeline_id, topic, hierarchy, clock_domains, dataflow, claims)` 함수: Bedrock Claude 3 Haiku 호출
    - 3가지 HDD 유형 지원: 칩 전체 HDD (N1B0_NPU_HDD 스타일), 서브시스템 HDD (EDC_HDD 스타일), 블록 HDD (overlay_HDD 스타일)
    - 생성된 HDD를 Markdown으로 S3 `rtl-parsed/hdd/{pipeline_id}/`에 저장
    - OpenSearch에 `analysis_type=hdd_section` 문서로 Titan Embeddings 벡터와 함께 인덱싱
    - 메타데이터 포함: source_rtl_files, generation_date, pipeline_version, pipeline_id
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 10.6_

  - [ ]* 7.3 HDD 섹션 완전성 및 참조 무결성 속성 테스트 작성
    - `tests/properties/rtl_hdd_properties_test.go` 생성
    - **Property 12: HDD 섹션 완전성** — 필수 구조(개요, 모듈 계층, 기능 상세, 클럭/리셋 구조, 주요 파라미터, 검증 체크리스트) + 메타데이터 존재
    - **Validates: Requirements 7.2, 7.5, 10.6**
    - **Property 13: HDD 참조 무결성** — 참조 모듈명이 계층 트리 모듈명의 부분집합
    - **Validates: Requirements 7.6**

  - [x] 7.4 Claim Generator 및 HDD Generator를 analysis_handler에 통합
    - `analysis_handler.py`에 `handle_claim_generation(event)`, `handle_hdd_generation(event)` 함수 추가
    - Step Functions Stage 2 (Knowledge Generation) 단계에서 호출
    - _Requirements: 1.2, 6.1, 7.1_

- [x] 8. Checkpoint - LLM 통합 검증
  - 모든 테스트 통과 확인, 문제 발생 시 사용자에게 질문

- [x] 9. Variant Delta 분석 및 검색 통합
  - [x] 9.1 Variant Delta 분석 핸들러 구현
    - `analysis_handler.py`에 `handle_variant_delta(event)` 함수 추가
    - 베이스라인과 variant Pipeline_ID를 입력받아 `extract_variant_delta()` 호출
    - 결과를 OpenSearch에 `analysis_type=variant_delta` 문서로 인덱싱
    - variant 전용 HDD 섹션 생성을 위해 `generate_hdd_section()`에 delta 정보 전달
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 9.2 OpenSearch 검색 통합 확장
    - `environments/app-layer/bedrock-rag/rtl_parser_src/handler.py`의 `_search_rtl()` 함수 확장
    - pipeline_id, topic, analysis_type, clock_domain, hierarchy_path 필터링 검색 지원
    - `build_search_query()` 함수 활용
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 10.3_

  - [ ]* 9.3 Pipeline_ID 격리 속성 테스트 작성
    - `tests/properties/rtl_pipeline_isolation_properties_test.go` 생성
    - **Property 16: Pipeline_ID 격리** — 하나의 Pipeline_ID로 필터링한 쿼리에 다른 Pipeline_ID 문서 미포함
    - **Validates: Requirements 1.7, 10.2, 10.5**

- [x] 10. 통합 와이어링 및 최종 검증
  - [x] 10.1 Step Functions 상태 머신 정의와 Lambda 핸들러 연결
    - `step-functions.tf`의 상태 머신 정의에서 각 단계가 `analysis_handler.py`의 올바른 핸들러를 호출하도록 연결
    - Step Functions 입력/출력 매핑 검증
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

  - [x] 10.2 Lambda 배포 패키지 업데이트
    - `environments/app-layer/bedrock-rag/rtl_parser_src/` 디렉토리의 모든 새 Python 모듈을 배포 패키지에 포함
    - `requirements.txt` 업데이트 (추가 의존성 없음 — boto3 + requests만 사용)
    - _Requirements: 11.2_

  - [ ]* 10.3 통합 테스트 작성
    - `tests/integration/rtl_pipeline_integration_test.go` 생성
    - S3 업로드 → Lambda 트리거 → OpenSearch 인덱싱 E2E 검증
    - Step Functions 실행 → DynamoDB 상태 업데이트 검증
    - OpenSearch 필터링 검색 (pipeline_id, topic, analysis_type) 검증
    - _Requirements: 1.1, 1.2, 8.3, 10.3_

- [x] 11. 서브시스템 심화 분석 — 패키지 파라미터, EDC, NoC, Overlay
  - [x] 11.1 패키지 파라미터 추출 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/package_extractor.py` 생성
    - `extract_package_params(rtl_content)` 함수: `localparam`, `parameter`, `typedef enum` 정규식 추출
    - `identify_chip_config(params)` 함수: SizeX, SizeY, NumTensix 등 칩 구성 파라미터 식별
    - `extract_enum_mapping(enums)` 함수: 타일 타입 enum에서 타일 타입 → RTL 모듈 매핑 추출
    - _Requirements: 12.1, 12.3_

  - [x] 11.2 패키지 파라미터 추출 핸들러 통합
    - `analysis_handler.py`에 `handle_chip_config(event)` 함수 추가
    - RTL Parser Lambda에서 `*_pkg.sv` 파일 감지 시 전용 파싱 경로 진입
    - 결과를 OpenSearch에 `analysis_type=chip_config` 문서로 인덱싱
    - `_STAGE_HANDLERS`에 `"chip_config": handle_chip_config` 등록
    - HDD_Section_Generator에 칩 구성 정보 전달 로직 추가
    - _Requirements: 12.2, 12.4, 12.5_

  - [ ]* 11.3 패키지 파라미터 추출 속성 테스트 작성
    - `tests/properties/rtl_package_params_properties_test.go` 생성
    - **Property 18: 패키지 파라미터 추출 라운드트립** — 모든 선언 추출 + 원본 역검색 일치
    - **Validates: Requirements 12.1, 12.3, 13.3, 14.1, 15.1, 15.3**

  - [x] 11.4 EDC 토폴로지 분석 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/edc_analyzer.py` 생성
    - `build_edc_topology(edc_modules)` 함수: tt_edc1_* 모듈 인스턴스화 패턴에서 링 토폴로지 재구성
    - `identify_harvest_bypass(modules)` 함수: mux/demux 패턴에서 하베스트 바이패스 경로 식별
    - `extract_serial_bus_interface(pkg_content)` 함수: tt_edc1_pkg.sv에서 시리얼 버스 인터페이스 정의 추출
    - `build_node_id_table(modules)` 함수: 노드 ID 구조 (part/subp/inst) 디코딩 테이블 생성
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 11.5 EDC 토폴로지 분석 핸들러 통합
    - `analysis_handler.py`에 `handle_edc_topology(event)` 함수 추가
    - `_STAGE_HANDLERS`에 `"edc_topology": handle_edc_topology` 등록
    - 결과를 OpenSearch에 `analysis_type=edc_topology` 문서로 인덱싱
    - DynamoDB 상태 추적 (in_progress → completed/failed)
    - HDD_Section_Generator에 EDC 토폴로지 정보 전달 (링 다이어그램, 바이패스 흐름도, 노드 ID 테이블)
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

  - [ ]* 11.6 EDC 토폴로지 속성 테스트 작성
    - `tests/properties/rtl_edc_topology_properties_test.go` 생성
    - **Property 20: EDC 토폴로지 분석 정확성** — 토폴로지 라운드트립 + 노드 ID 고유성
    - **Validates: Requirements 13.1, 13.2, 13.4**

  - [x] 11.7 NoC 프로토콜 분석 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/noc_analyzer.py` 생성
    - `extract_routing_algorithms(pkg_content)` 함수: tt_noc_pkg.sv에서 라우팅 enum 추출
    - `extract_flit_structure(pkg_content)` 함수: noc_header_address_t 구조체에서 flit 헤더 필드 추출
    - `extract_struct_fields(rtl_content, struct_name)` 함수: 범용 구조체 필드 추출
    - `extract_axi_address_gasket(pkg_content)` 함수: AXI 주소 가스켓 구조 추출
    - `identify_security_fence(modules)` 함수: 보안 펜스 메커니즘 식별
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [x] 11.8 NoC 프로토콜 분석 핸들러 통합
    - `analysis_handler.py`에 `handle_noc_protocol(event)` 함수 추가
    - `_STAGE_HANDLERS`에 `"noc_protocol": handle_noc_protocol` 등록
    - 결과를 OpenSearch에 `analysis_type=noc_protocol` 문서로 인덱싱
    - HDD_Section_Generator에 NoC 프로토콜 정보 전달 (라우팅 비교 테이블, flit 구조, AXI 주소 매핑)
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [ ]* 11.9 구조체 필드 추출 속성 테스트 작성
    - `tests/properties/rtl_struct_fields_properties_test.go` 생성
    - **Property 19: 구조체 필드 추출 완전성** — 모든 필드명/비트폭 추출 + 필드 수 동일
    - **Validates: Requirements 14.2, 14.3**

  - [x] 11.10 Overlay 심화 분석 함수 구현
    - `environments/app-layer/bedrock-rag/rtl_parser_src/overlay_analyzer.py` 생성
    - `extract_cpu_cluster_params(pkg_content)` 함수: tt_overlay_pkg.sv에서 CPU 클러스터 파라미터 추출
    - `identify_submodule_roles(modules)` 함수: Overlay 서브모듈 역할 식별 (cpu_wrapper, idma, rocc, llk, smn, fds)
    - `extract_l1_cache_params(module_content)` 함수: tt_overlay_memory_wrapper에서 L1 캐시 파라미터 추출
    - `extract_apb_slaves(xbar_content)` 함수: tt_overlay_reg_xbar_slave_decode에서 APB 슬레이브 목록 추출
    - _Requirements: 15.1, 15.2, 15.3, 15.4_

  - [x] 11.11 Overlay 심화 분석 핸들러 통합
    - `analysis_handler.py`에 `handle_overlay_deep_analysis(event)` 함수 추가
    - `_STAGE_HANDLERS`에 `"overlay_deep_analysis": handle_overlay_deep_analysis` 등록
    - 결과를 OpenSearch에 `analysis_type=overlay_deep` 문서로 인덱싱
    - HDD_Section_Generator에 Overlay 심화 정보 전달 (CPU-to-NoC 경로, L1 캐시 테이블, 레지스터 맵)
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [ ]* 11.12 Overlay 구조 분석 속성 테스트 작성
    - `tests/properties/rtl_overlay_deep_properties_test.go` 생성
    - **Property 21: Overlay 구조 분석 완전성** — 알려진 패턴 역할 할당 + APB 슬레이브 추출
    - **Validates: Requirements 15.2, 15.4**

- [x] 12. Checkpoint - 서브시스템 심화 분석 검증
  - 모든 새 핸들러가 `_STAGE_HANDLERS`에 등록되었는지 확인
  - 새 analysis_type별 OpenSearch 인덱싱 검증
  - 기존 파이프라인과의 호환성 확인
  - 문제 발생 시 사용자에게 질문

- [x] 13. Final Checkpoint - 전체 파이프라인 검증
  - 모든 테스트 통과 확인, 문제 발생 시 사용자에게 질문

- [x] 14. HDD Generator 심화 분석 결과 통합
  - [x] 14.1 hdd_generator.py의 generate_hdd_section() 함수에서 심화 분석 결과 조회 로직 추가
    - `generate_hdd_section()` 함수 시그니처에 `deep_analysis: dict[str, Any] | None = None` 파라미터 추가
    - OpenSearch에서 `chip_config`, `edc_topology`, `noc_protocol`, `overlay_deep`, `sram_inventory` analysis_type 문서를 조회하는 헬퍼 로직 추가
    - 조회된 심화 분석 결과를 `_build_hdd_prompt()`에 전달
    - _Requirements: 7.7, 7.8, 7.9, 7.10, 7.11_

  - [x] 14.2 analysis_handler.py의 handle_hdd_generation() 함수에서 심화 분석 결과 5종 조회 및 전달
    - `handle_hdd_generation()` 내에서 `_opensearch_scroll_query(pipeline_id, "chip_config")`, `_opensearch_scroll_query(pipeline_id, "edc_topology")`, `_opensearch_scroll_query(pipeline_id, "noc_protocol")`, `_opensearch_scroll_query(pipeline_id, "overlay_deep")`, `_opensearch_scroll_query(pipeline_id, "sram_inventory")` 호출 추가
    - 조회된 결과를 `deep_analysis` dict로 구성하여 `generate_hdd_section()`에 전달
    - 토픽별 매핑: chip/top → chip_config + sram_inventory, EDC → edc_topology, NoC → noc_protocol, Overlay → overlay_deep
    - _Requirements: 7.7, 7.8, 7.9, 7.10, 7.11_

  - [x] 14.3 hdd_generator.py의 _build_hdd_prompt() 함수 확장 — 토픽별 심화 데이터를 LLM 프롬프트에 포함
    - `_build_hdd_prompt()` 함수 시그니처에 `deep_analysis: dict[str, Any] | None = None` 파라미터 추가
    - chip HDD: `chip_config`에서 Package Constants (SizeX/SizeY, NumTensix, tile_t enum, Endpoint Index Table) + `sram_inventory`에서 메모리 타입별 수량/총 용량/서브시스템별 분포를 프롬프트에 추가
    - EDC HDD: `edc_topology`에서 링 토폴로지 다이어그램, 시리얼 버스 인터페이스 사양, 하베스트 바이패스 흐름도, 노드 ID 테이블을 프롬프트에 추가
    - NoC HDD: `noc_protocol`에서 라우팅 알고리즘 3종 비교 테이블, flit 헤더 구조, AXI 주소 가스켓 매핑을 프롬프트에 추가
    - Overlay HDD: `overlay_deep`에서 CPU 클러스터 파라미터, L1 캐시 구성 테이블, APB 슬레이브 레지스터 맵을 프롬프트에 추가
    - 각 심화 데이터는 JSON 직렬화 후 2000자로 truncate
    - _Requirements: 7.7, 7.8, 7.9, 7.10, 7.11_

  - [x] 14.4 심화 분석 결과 조회 실패 시 기본 HDD 생성으로 폴백하는 에러 처리
    - 각 심화 분석 결과 조회(`_opensearch_scroll_query`) 실패 시 빈 dict로 폴백
    - `deep_analysis`가 None이거나 빈 경우 기존 방식(hierarchy + clock + dataflow + claims만)으로 HDD 생성 진행
    - 조회 실패 시 경고 로그 기록 (`logger.warning`)
    - _Requirements: 7.7_

  - [ ]* 14.5 단위 테스트 — 심화 분석 데이터가 프롬프트에 포함되는지 검증
    - `_build_hdd_prompt()`에 `deep_analysis` 전달 시 chip_config/edc_topology/noc_protocol/overlay_deep/sram_inventory 데이터가 프롬프트 문자열에 포함되는지 검증
    - `deep_analysis`가 None일 때 기존 프롬프트와 동일한 결과 생성 검증
    - 심화 데이터 없을 때 기본 HDD 생성 폴백 검증
    - _Requirements: 7.7, 7.8, 7.9, 7.10, 7.11_

- [x] 15. chip_config 분석 타임아웃 해결
  - [x] 15.1 analysis_handler.py의 handle_chip_config() 함수에서 *_pkg.sv 파일만 선별적으로 S3에서 읽는 로직 구현
    - OpenSearch에서 `pipeline_id`로 `module_parse` 문서를 조회한 후, `file_path` 필드에서 `_pkg.sv`로 끝나는 파일만 추출
    - 추출된 파일 목록으로 S3 GetObject 호출 (S3 ListObjects 호출 최소화)
    - 기존 `paginator.paginate()` 기반 전체 파일 순회 로직을 대체
    - _Requirements: 12.6, 12.8_

  - [x] 15.2 OpenSearch module_parse 문서의 file_path에서 *_pkg.sv 패턴 필터링으로 S3 ListObjects 호출 최소화
    - `_opensearch_scroll_query(pipeline_id, "module_parse")` 결과에서 `file_path` 필드 추출
    - `file_path.endswith("_pkg.sv")` 조건으로 패키지 파일만 필터링
    - 필터링된 파일 경로 목록으로 직접 `s3_client.get_object()` 호출
    - S3 ListObjects paginator 호출 제거
    - _Requirements: 12.6, 12.8_

  - [x] 15.3 300초 타임아웃 임박 시 미처리 토픽을 별도 Lambda로 분할 실행하는 로직 구현
    - `handle_chip_config()`에 `context` 파라미터 활용 (`context.get_remaining_time_in_millis()`)
    - 남은 시간 < 30초일 때 미처리 pkg 파일을 토픽별(`PKG_TOPIC_PREFIXES`: noc, edc, overlay, dispatch, general)로 그룹화
    - 각 미처리 토픽 그룹에 대해 `lambda_client.invoke(InvocationType="Event")` 비동기 호출로 분할 실행
    - event에 `topic_filter` 파라미터 추가하여 분할 실행 시 해당 토픽만 처리
    - _Requirements: 12.7_

  - [ ]* 15.4 단위 테스트 — *_pkg.sv 파일 필터링 정확성 검증
    - `_pkg.sv`로 끝나는 파일만 선택되는지 검증
    - 비매칭 파일(`*.sv`, `*_pkg.v`, `*pkg.sv` 등)이 제외되는지 검증
    - 빈 파일 목록 처리 검증
    - _Requirements: 12.6, 12.8_

- [x] 16. SRAM Inventory Extractor 구현
  - [x] 16.1 sram_inventory.py 모듈 생성 — 메모리 패턴 매칭 함수
    - `environments/app-layer/bedrock-rag/rtl_parser_src/sram_inventory.py` 생성
    - `MEMORY_PATTERNS` 상수 정의: `["sram", "ram", "rf_", "reg_file", "rom", "memory", "mem_"]`
    - `is_memory_instance(instance_name, module_name)` 함수: 인스턴스명 또는 모듈명에 메모리 키워드 포함 여부 판별
    - `classify_memory_type(instance_name, module_name)` 함수: SRAM/RF/ROM 타입 분류
    - _Requirements: 16.1, 16.5_

  - [x] 16.2 메모리 인스턴스 파라미터(depth, width, ECC) 추출 함수 구현
    - `extract_memory_params(instance_name)` 함수: 인스턴스명에서 `{depth}x{width}` 패턴 추출 (예: `u_sram_256x64` → depth=256, width=64)
    - 파라미터 추출 불가 시 `"unknown"` 기본값 설정
    - `build_sram_inventory(hierarchy_docs)` 함수: 계층 트리 문서에서 메모리 인스턴스를 식별하고 인벤토리 생성
    - 서브시스템별 분포 집계 (`by_type`, `by_subsystem`) 및 `summary` dict 생성
    - _Requirements: 16.2, 16.6_

  - [x] 16.3 analysis_handler.py에 handle_sram_inventory() 핸들러 추가 + _STAGE_HANDLERS 등록
    - `analysis_handler.py`에 `from sram_inventory import is_memory_instance, build_sram_inventory` import 추가
    - `handle_sram_inventory(event)` 함수 구현: OpenSearch에서 hierarchy 문서 조회 → `build_sram_inventory()` 호출 → S3에 `rtl-parsed/sram_inventory/{pipeline_id}/sram_inventory.json` 저장
    - `_STAGE_HANDLERS`에 `"sram_inventory": handle_sram_inventory` 등록
    - DynamoDB 상태 추적 (in_progress → completed/failed)
    - _Requirements: 16.1, 16.3_

  - [x] 16.4 OpenSearch에 analysis_type=sram_inventory 문서 인덱싱
    - `handle_sram_inventory()` 내에서 `_index_document()` 호출로 SRAM Inventory 결과를 OpenSearch에 인덱싱
    - 문서 필드: `pipeline_id`, `analysis_type=sram_inventory`, `memory_instances` (nested), `sram_summary` (object)
    - Titan Embeddings 벡터 생성은 선택 사항 (텍스트 검색 우선)
    - _Requirements: 16.3, 16.4_

  - [ ]* 16.5 단위 테스트 — 메모리 패턴 매칭, 파라미터 추출, unknown 기본값 처리
    - `is_memory_instance()`: sram, ram, rf_, reg_file, rom, memory, mem_ 패턴 매칭 검증
    - `classify_memory_type()`: SRAM/RF/ROM 타입 분류 정확성 검증
    - `extract_memory_params()`: `{depth}x{width}` 패턴 추출 검증, 추출 불가 시 "unknown" 기본값 검증
    - `build_sram_inventory()`: 빈 계층 트리, 메모리 인스턴스 없는 경우, summary 집계 정확성 검증
    - _Requirements: 16.1, 16.2, 16.5, 16.6_

- [x] 17. Lambda 배포 및 E2E 검증
  - [x] 17.1 수정된 hdd_generator.py, analysis_handler.py, 신규 sram_inventory.py를 Lambda 배포 패키지에 포함
    - `environments/app-layer/bedrock-rag/rtl_parser_src/` 디렉토리에 `sram_inventory.py` 추가 확인
    - `hdd_generator.py`의 `generate_hdd_section()`, `_build_hdd_prompt()` 시그니처 변경 반영
    - `analysis_handler.py`의 `handle_hdd_generation()`, `handle_chip_config()`, `handle_sram_inventory()` 변경 반영
    - `_STAGE_HANDLERS`에 `sram_inventory` 등록 확인
    - Lambda 배포 패키지 빌드 및 업로드
    - _Requirements: 11.2_

  - [x] 17.2 chip_config 분석 재실행 — *_pkg.sv 선별 읽기로 타임아웃 해결 확인
    - `stage=chip_config`으로 Lambda invoke 실행
    - S3 ListObjects 호출 대신 OpenSearch module_parse 기반 파일 필터링 동작 확인
    - 300초 타임아웃 내 완료 확인
    - OpenSearch에 `analysis_type=chip_config` 문서 인덱싱 확인
    - _Requirements: 12.6, 12.7, 12.8_

  - [x] 17.3 SRAM Inventory 분석 실행
    - `stage=sram_inventory`로 Lambda invoke 실행
    - OpenSearch에 `analysis_type=sram_inventory` 문서 인덱싱 확인
    - S3 `rtl-parsed/sram_inventory/{pipeline_id}/sram_inventory.json` 저장 확인
    - memory_instances 목록 및 summary (total_count, by_type, by_subsystem) 정확성 확인
    - _Requirements: 16.1, 16.2, 16.3, 16.4_

  - [x] 17.4 HDD 재생성 — 심화 분석 결과 반영 확인
    - `stage=hdd_generation`으로 Lambda invoke 실행
    - 칩 전체 HDD에 Package Constants + SRAM Inventory 섹션 포함 확인
    - EDC HDD에 링 토폴로지, 시리얼 버스 인터페이스, 하베스트 바이패스 정보 포함 확인
    - NoC HDD에 라우팅 알고리즘 비교, flit 구조, AXI 주소 매핑 포함 확인
    - Overlay HDD에 CPU 클러스터, L1 캐시, APB 슬레이브 정보 포함 확인
    - _Requirements: 7.7, 7.8, 7.9, 7.10, 7.11_

  - [x] 17.5 Obot에서 search_rtl로 개선된 HDD 검색 검증
    - MCP bridge의 `search_rtl` 도구로 `analysis_type=hdd_section` 검색 실행
    - 심화 분석 데이터가 반영된 HDD 콘텐츠가 검색 결과에 포함되는지 확인
    - `analysis_type=sram_inventory` 검색으로 SRAM Inventory 데이터 조회 확인
    - _Requirements: 8.1, 8.3, 10.3_

- [x] 18. Final Checkpoint - 신규 기능 전체 검증
  - 모든 신규 태스크(14~17) 완료 확인
  - chip_config 분석이 300초 타임아웃 내 완료되는지 확인
  - SRAM Inventory가 OpenSearch에 정상 인덱싱되는지 확인
  - HDD 재생성 시 심화 분석 결과 5종이 프롬프트에 반영되는지 확인
  - 기존 파이프라인(Task 1~13)과의 호환성 확인
  - 문제 발생 시 사용자에게 질문

- [x] 19. v3 R2 이슈 수정 — 포트 비트폭 추출 (이슈 #4)
  - [x] 19.1 handler.py의 parse_rtl_to_ast() 포트 정규식 확장 — 비트폭 캡처 그룹 추가
    - `environments/app-layer/bedrock-rag/rtl_parser_src/handler.py` 수정
    - 기존 포트 정규식 `\b(input|output|inout)\s+(?:wire|reg|logic)?\s*(?:\[[\w\s:\-]+\])?\s*(\w+)` 수정
    - 비트폭 캡처 그룹 추가: `((?:\[[^\]]+\]\s*)*)` — 다차원 배열 `[A:B][C:D]` 지원
    - 출력 형식: `direction [bit_width] port_name` (비트폭 있을 때) 또는 `direction port_name` (비트폭 없을 때)
    - 예: `input [SizeX-1:0] i_ai_clk`, `input i_rst_n`, `output [3:0][7:0] data`
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_

  - [x] 19.2 포트 비트폭 추출 단위 테스트 작성
    - 비트폭 있는 포트: `input [7:0] data` → `input [7:0] data`
    - 파라미터 기반 비트폭: `input [SizeX-1:0] i_ai_clk` → `input [SizeX-1:0] i_ai_clk`
    - 비트폭 없는 포트: `input clk` → `input clk`
    - 다차원 배열: `input [3:0][7:0] data` → `input [3:0][7:0] data`
    - wire/reg/logic 키워드 포함: `output logic [15:0] result` → `output [15:0] result`
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_

- [x] 20. v3 R2 이슈 수정 — 토픽 분류 확장 (이슈 #3)
  - [x] 20.1 topic_classifier.py의 TOPIC_RULES에 Power, Memory 토픽 추가 및 NIU 접두사 확장
    - `environments/app-layer/bedrock-rag/rtl_parser_src/topic_classifier.py` 수정
    - NIU 토픽에 `tt_noc2axi_` 접두사 추가
    - Power 토픽 신규 추가: path `[/\\]power[/\\]`, `[/\\]prtn[/\\]`, prefix `tt_prtn_`, `prtn_`, `iso_en_`
    - Memory 토픽 신규 추가: path `[/\\]memory[/\\]`, `[/\\]sram[/\\]`, prefix `sfr_`, `tt_mem_`, `mem_`
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5_

  - [x] 20.2 토픽 분류 확장 단위 테스트 작성
    - `tt_noc2axi_router` → NIU 토픽 포함 검증
    - `tt_prtn_chain` → Power 토픽 검증
    - `sfr_register_block` → Memory 토픽 검증
    - 기존 12개 토픽 분류가 깨지지 않는지 회귀 테스트
    - 14개 토픽 카테고리 전체 지원 검증
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5_

- [x] 21. v3 R2 이슈 수정 — Claim 귀속 정확성 개선 (이슈 #2)
  - [x] 21.1 claim_generator.py에 레지스터 래퍼 필터링 및 다양성 검증 함수 추가
    - `environments/app-layer/bedrock-rag/rtl_parser_src/claim_generator.py` 수정
    - `REGISTER_WRAPPER_PATTERNS = ["_reg_inner", "_wrap", "_reg_top"]` 상수 추가
    - `_filter_claim_targets(modules, topic)` 함수 추가: 레지스터 래퍼 제외, 데이터패스 모듈 우선 포함. 데이터패스 모듈 3개 미만 시 레지스터 모듈도 포함
    - `_validate_claim_diversity(claims, topic)` 함수 추가: 단일 모듈 80% 이상 편중 시 False 반환 + 경고 로그
    - `generate_claims()` 함수에서 `_filter_claim_targets()` 호출하여 claim 대상 모듈 필터링
    - _Requirements: 18.1, 18.3, 18.4_

  - [x] 21.2 analysis_handler.py의 handle_hdd_generation()에 토픽-모듈 교차 검증 추가
    - `environments/app-layer/bedrock-rag/rtl_parser_src/analysis_handler.py` 수정
    - `_filter_claims_by_topic_hierarchy(claims, topic, hierarchy_modules)` 함수 추가: claim의 module_name이 해당 토픽의 실제 모듈 계층에 속하는지 검증, 불일치 claim 제외
    - `handle_hdd_generation()` 내에서 토픽별 HDD 생성 전 `_filter_claims_by_topic_hierarchy()` 호출
    - `handle_claim_generation()` 내에서 `classify_topic()` 결과와 hierarchy 위치 교차 검증 로직 추가
    - _Requirements: 18.2, 18.5_

  - [x] 21.3 Claim 귀속 정확성 단위 테스트 작성
    - `_filter_claim_targets()`: 레지스터 래퍼 모듈 제외 검증, 데이터패스 모듈 3개 미만 시 폴백 검증
    - `_validate_claim_diversity()`: 단일 모듈 80% 이상 편중 시 False, 다양한 분포 시 True 검증
    - `_filter_claims_by_topic_hierarchy()`: 토픽 불일치 claim 제외 검증, 빈 계층 트리 처리 검증
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5_

- [ ] 22. v3 R2 이슈 수정 — MCP Bridge search_rtl 파라미터 패스스루 (이슈 #1, #5)
  - [ ] 22.1 온프레미스 MCP Bridge server.js의 search_rtl 도구 파라미터 스키마 수정
    - 온프레미스 `server.js`의 search_rtl 도구 수정 (코드 변경 가이드 작성)
    - max_results: `z.number().optional().default(20)` (기존 하드코딩 5 → 기본값 20)
    - analysis_type: `z.string().optional()` 파라미터 추가
    - pipeline_id: `z.string().optional()` 파라미터 추가
    - topic: `z.string().optional()` 파라미터 추가
    - Lambda invoke 요청 본문에 모든 파라미터를 조건부 포함 (제공된 파라미터만)
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 21.1, 21.2, 21.3, 21.4_

  - [ ] 22.2 MCP Bridge search_rtl 파라미터 전달 검증 테스트 가이드 작성
    - Obot에서 `search_rtl` 호출 시 `max_results=20` 전달 확인
    - `analysis_type=hdd_section` 필터 전달 확인
    - `pipeline_id=tt_20260221` 필터 전달 확인
    - 파라미터 미제공 시 Lambda 요청에서 생략 확인
    - _Requirements: 17.1, 17.2, 17.3, 17.5_

- [x] 23. v3 R2 이슈 수정 — 배포 및 E2E 검증
  - [x] 23.1 수정된 handler.py, topic_classifier.py, claim_generator.py, analysis_handler.py Lambda 배포
    - `environments/app-layer/bedrock-rag/rtl_parser_src/` 디렉토리의 수정된 파일 배포
    - handler.py: 포트 비트폭 추출 정규식 변경 반영
    - topic_classifier.py: Power, Memory 토픽 추가 + NIU 접두사 확장 반영
    - claim_generator.py: 레지스터 래퍼 필터링 + 다양성 검증 반영
    - analysis_handler.py: 토픽-모듈 교차 검증 반영
    - Lambda 배포 패키지 빌드 및 업로드
    - _Requirements: 11.2_

  - [ ] 23.2 RTL 재파싱 실행 — 포트 비트폭 포함 확인
    - 샘플 RTL 파일 재파싱 실행
    - OpenSearch에서 port_list에 비트폭 정보(`[MSB:LSB]`)가 포함되는지 확인
    - 기존 파싱 결과와의 호환성 확인 (비트폭 없는 포트는 기존 형식 유지)
    - _Requirements: 20.1, 20.3_

  - [ ] 23.3 토픽 재분류 실행 — NIU, Power, Memory 토픽 확인
    - `stage=topic_classification`으로 Lambda invoke 실행
    - NIU 토픽에 `tt_noc2axi_*` 모듈이 분류되는지 확인
    - Power 토픽에 `tt_prtn_*` 모듈이 분류되는지 확인
    - Memory 토픽에 `sfr_*` 모듈이 분류되는지 확인
    - 기존 12개 토픽 분류가 깨지지 않는지 확인
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5_

  - [ ] 23.4 Claim 재생성 실행 — 모듈 다양성 확인
    - `stage=claim_generation`으로 Lambda invoke 실행
    - 토픽별 claim의 module_name 분포 확인 (단일 모듈 80% 미만)
    - 레지스터 래퍼(`_reg_inner`, `_wrap`) 모듈 claim 비율 감소 확인
    - 데이터패스 모듈 claim 비율 증가 확인
    - _Requirements: 18.1, 18.3, 18.4_

  - [ ] 23.5 HDD 재생성 실행 — 토픽-모듈 매핑 검증 확인
    - `stage=hdd_generation`으로 Lambda invoke 실행
    - 각 토픽 HDD에 해당 토픽의 실제 모듈만 참조되는지 확인
    - 5개 토픽이 동일 모듈에 편중되지 않는지 확인
    - _Requirements: 18.2, 18.5_

  - [ ] 23.6 온프레미스 MCP Bridge 업데이트 및 Obot E2E 검증
    - 온프레미스 server.js에 수정된 search_rtl 도구 배포
    - Obot에서 `search_rtl(query="NoC router", max_results=20)` 호출 시 20건 반환 확인
    - Obot에서 `search_rtl(query="EDC", analysis_type="hdd_section")` 호출 시 필터링 동작 확인
    - _Requirements: 17.1, 17.2, 17.4, 21.1, 21.2_

- [ ] 24. Final Checkpoint - v3 R2 이슈 수정 전체 검증
  - 모든 신규 태스크(19~23) 완료 확인
  - 포트 비트폭이 OpenSearch port_list에 포함되는지 확인
  - 14개 토픽 카테고리(NIU, Power, Memory 포함) 분류 정상 동작 확인
  - Claim 귀속이 토픽별 다양한 모듈에 분산되는지 확인
  - MCP Bridge search_rtl이 max_results, analysis_type 파라미터를 정확히 전달하는지 확인
  - 기존 파이프라인(Task 1~18)과의 호환성 확인
  - 문제 발생 시 사용자에게 질문

## Notes

- `*` 표시된 태스크는 선택 사항이며 빠른 MVP를 위해 건너뛸 수 있음
- 각 태스크는 특정 요구사항을 참조하여 추적 가능
- Checkpoint에서 점진적 검증 수행
- 속성 테스트는 설계 문서의 Correctness Properties를 검증
- 단위 테스트는 구체적 예시와 엣지 케이스를 검증
- Python 순수 로직 함수는 Go PBT에서 JSON 입출력 기반으로 검증 (Lambda invoke 또는 subprocess 호출)
- 기존 인프라 리소스(S3, OpenSearch, DynamoDB, Lambda)는 재사용하며 새로 생성하지 않음
