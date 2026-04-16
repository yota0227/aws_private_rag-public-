# 구현 계획: RTL 자동 분석 파이프라인

## 개요

RTL 자동 분석 파이프라인의 구현을 5단계로 진행한다: (1) 순수 로직 함수 + PBT 테스트, (2) Terraform 인프라, (3) Lambda 코드 확장, (4) LLM 통합, (5) 통합 테스트. Python 3.12(Lambda), Go 1.21 + gopter(PBT), Terraform(인프라)을 사용한다.

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
    - `analysis_handler.py`에 `handle_topic_classification(event)` 함수 추가
    - 모든 모듈에 대해 `classify_topic()` 호출 → OpenSearch 문서에 `topic` 필드 업데이트
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

- [x] 11. Final Checkpoint - 전체 파이프라인 검증
  - 모든 테스트 통과 확인, 문제 발생 시 사용자에게 질문

## Notes

- `*` 표시된 태스크는 선택 사항이며 빠른 MVP를 위해 건너뛸 수 있음
- 각 태스크는 특정 요구사항을 참조하여 추적 가능
- Checkpoint에서 점진적 검증 수행
- 속성 테스트는 설계 문서의 Correctness Properties를 검증
- 단위 테스트는 구체적 예시와 엣지 케이스를 검증
- Python 순수 로직 함수는 Go PBT에서 JSON 입출력 기반으로 검증 (Lambda invoke 또는 subprocess 호출)
- 기존 인프라 리소스(S3, OpenSearch, DynamoDB, Lambda)는 재사용하며 새로 생성하지 않음
