# Implementation Plan: RAG 검색 성능 최적화

## Overview

BOS-AI Private RAG 시스템의 검색 품질을 Phase 1으로 개선한다. Lambda Handler에 Hybrid Search, 메타데이터 자동 생성, 필터링, 모니터링 기능을 추가하고, Terraform 변수 및 CloudWatch 메트릭 필터를 구성하며, MCP Bridge에 필터 파라미터를 전달한다. 구현은 기반 유틸리티 함수부터 시작하여 점진적으로 상위 기능을 통합하는 순서로 진행한다.

## Tasks

- [x] 1. Terraform 변수 및 Lambda 환경 변수 구성
  - [x] 1.1 `variables.tf`에 `search_type` 변수 추가
    - `string` 타입, 기본값 `"HYBRID"`, `HYBRID`/`SEMANTIC` validation 블록 포함
    - 변수 설명에 허용 값 명시
    - _Requirements: 2.1, 2.4_
  - [x] 1.2 `variables.tf`에 `search_results_count` 변수 추가
    - `number` 타입, 기본값 `5`
    - _Requirements: 2.2_
  - [x] 1.3 `lambda.tf` Lambda 환경 변수에 `SEARCH_TYPE`, `SEARCH_RESULTS_COUNT` 추가
    - `environment.variables` 블록에 `SEARCH_TYPE = var.search_type`, `SEARCH_RESULTS_COUNT = tostring(var.search_results_count)` 추가
    - _Requirements: 2.3_
  - [ ]* 1.4 Property 2 테스트 작성: Terraform 검색 변수 정의
    - **Property 2: Terraform 검색 변수 정의**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    - `tests/properties/rag_search_optimization_test.go`에 작성
    - `search_type`이 string 타입이고 기본값 HYBRID이며 validation 포함, `search_results_count`가 number 타입이고 기본값 5인지 검증

- [x] 2. Lambda 기반 유틸리티 함수 구현
  - [x] 2.1 `create_metadata_file()` 함수 추가
    - `environments/app-layer/bedrock-rag/lambda_src/index.py`에 신규 함수 추가
    - `DOCUMENT_TYPE_MAP` 상수 정의 (`.pdf`→`"pdf"`, `.txt`→`"text"`, `.md`→`"markdown"`, 그 외→`"other"`)
    - `metadataAttributes` 객체에 `team`, `category`, `document_type`, `upload_date`(ISO 8601) 포함
    - team/category가 None이거나 빈 값이면 빈 문자열 설정
    - `Content-Type: application/json`, UTF-8 인코딩으로 S3 저장
    - 메타데이터 키는 원본 S3 키 + `.metadata.json`
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6_
  - [ ]* 2.2 Property 3 테스트 작성: 메타데이터 파일 구조 및 내용
    - **Property 3: 메타데이터 파일 구조 및 내용**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    - 임의의 S3 키와 team/category 값에 대해 메타데이터 구조, 필드 존재, document_type 매핑, 빈 값 처리 검증
  - [x] 2.3 `build_bedrock_filter()` 함수 추가
    - team만 → `{"equals": {"key": "team", "value": "<값>"}}`
    - category만 → `{"equals": {"key": "category", "value": "<값>"}}`
    - 둘 다 → `{"andAll": [team필터, category필터]}`
    - 둘 다 없거나 빈 값 → `None`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [ ]* 2.4 Property 4 테스트 작성: Bedrock 필터 구문 변환
    - **Property 4: Bedrock 필터 구문 변환**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**
    - 임의의 filter 객체에 대해 변환 규칙 정확성 검증
  - [x] 2.5 `parse_team_category_from_key()` 함수 추가
    - `documents/{team}/{category}/{filename}` 형식에서 `(team, category)` 튜플 반환
    - 경로 깊이 3 미만이면 `('', '')` 반환
    - _Requirements: 8.2_
  - [ ]* 2.6 Property 8 테스트 작성: S3 키 경로 team/category 파싱
    - **Property 8: S3 키 경로 team/category 파싱**
    - **Validates: Requirements 8.2**
    - 다양한 깊이의 S3 키에 대해 파싱 정확성 검증

- [x] 3. Checkpoint - 기반 함수 검증
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. `handle_query()` Hybrid Search 및 응답 구조 개선
  - [x] 4.1 `handle_query()` 수정: Hybrid Search 설정 적용
    - 환경 변수 `SEARCH_TYPE`(기본값 `HYBRID`), `SEARCH_RESULTS_COUNT`(기본값 `5`)에서 검색 설정 읽기
    - `vectorSearchConfiguration`에 `searchType`, `numberOfResults` 설정
    - `filter` 객체가 요청에 포함되면 `build_bedrock_filter()`로 변환하여 전달
    - _Requirements: 1.1, 1.2, 4.1_
  - [ ]* 4.2 Property 1 테스트 작성: 검색 설정 구성
    - **Property 1: 검색 설정 구성 (Search Config Construction)**
    - **Validates: Requirements 1.1, 1.2**
    - 유효한 검색 유형과 결과 수에 대해 vectorSearchConfiguration 구성 정확성 검증
  - [x] 4.3 `handle_query()` 수정: 응답 구조 개선
    - 응답에서 `retrievedReferences`의 `score` 필드 추출하여 `references[].score`에 포함
    - 응답에 `metadata` 객체 추가 (`search_type`, `results_count`, `query_length`)
    - `answer`, `citations`, `metadata` 필드 포함하는 응답 구조
    - 기존 응답 형식과 하위 호환성 유지
    - _Requirements: 1.3, 5.1, 5.2, 5.3, 5.4_
  - [ ]* 4.4 Property 5 테스트 작성: 질의 응답 구조 완전성
    - **Property 5: 질의 응답 구조 완전성**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    - 성공적인 Bedrock 응답에 대해 응답 필드 존재 및 타입 검증
  - [x] 4.5 `handle_query()` 수정: 에러 처리 분기
    - `ValidationException` → HTTP 400 + ERROR 로그
    - `ThrottlingException` → HTTP 429 + WARNING 로그
    - 기타 에러 → HTTP 500 + ERROR 로그
    - _Requirements: 1.4, 1.5_
  - [x] 4.6 `handle_query()` 수정: 구조화 로그 및 모니터링
    - 응답 시간 측정 (`time.time()` 기반)
    - CloudWatch 구조화 로그: `query_length`, `search_type`, `citation_count`, `response_time_ms`, `has_filter`
    - 인용 0건 시 `no_citation_query` 경고 로그
    - 응답 시간 30초 초과 시 `slow_query` 경고 로그
    - _Requirements: 7.1, 7.2, 7.4_
  - [ ]* 4.7 Property 7 테스트 작성: 구조화 로그 필드 완전성
    - **Property 7: 구조화 로그 필드 완전성**
    - **Validates: Requirements 7.1**
    - 질의 처리 시 구조화 로그에 필수 필드가 모두 포함되는지 검증

- [x] 5. `trigger_kb_sync()` ConflictException 처리 추가
  - 기존 `trigger_kb_sync()` 함수에 `ConflictException` 처리 추가
  - 동시 실행 시 WARNING 로그 기록 후 정상 종료
  - _Requirements: 설계 결정 사항 (ConflictException 처리)_

- [x] 6. 문서 업로드 메타데이터 통합
  - [x] 6.1 `confirm_upload()` 수정: 메타데이터 생성 + fire-and-forget KB Sync
    - 요청 body에서 `team`, `category` 파라미터 읽기
    - `create_metadata_file()` 호출하여 메타데이터 파일 생성
    - CRR 복제 대기 없이 즉시 `trigger_kb_sync()` 호출 (Eventual Consistency)
    - 응답에 `metadata_created: true` 포함
    - _Requirements: 3.1, 3.2, 3.3, 3.7_
  - [x] 6.2 `process_extraction()` 수정: 압축 해제 시 개별 파일 메타데이터 생성
    - 각 파일 S3 업로드 성공 후 `create_metadata_file()` 호출
    - 메타데이터 생성 실패 시 WARNING 로그 기록, 파일 업로드는 성공으로 처리
    - `team`, `category`는 압축 해제 요청 시 전달된 값 사용
    - _Requirements: 3.4, 3.5_

- [x] 7. Checkpoint - 질의 및 업로드 흐름 검증
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. 기존 문서 메타데이터 일괄 생성 (Backfill)
  - [x] 8.1 `backfill_metadata()` 함수 추가
    - Seoul_S3의 `documents/` 접두사 아래 모든 객체 조회
    - `.metadata.json` 파일이 없는 문서 식별
    - `parse_team_category_from_key()`로 team/category 파싱하여 메타데이터 생성
    - 개별 문서 실패 시 건너뛰고 계속 처리 (`error_count` 증가)
    - 1회 요청당 최대 500건 처리
    - `context.get_remaining_time_in_millis()` 30초 미만 시 중단
    - `has_more: true` + `continuation_token` 포함 응답
    - 처리 완료 후 `trigger_kb_sync()` 1회 실행
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_
  - [x] 8.2 `handler()` 라우팅에 `backfill_metadata` 액션 분기 추가
    - `event.get('action') == 'backfill_metadata'` 분기로 `backfill_metadata(event, context)` 호출
    - API Gateway 미경유, Lambda Event 비동기 호출 전용
    - _Requirements: 8.1_
  - [ ]* 8.3 Property 9 테스트 작성: Backfill 페이지네이션 및 카운팅
    - **Property 9: Backfill 페이지네이션 및 카운팅**
    - **Validates: Requirements 8.3, 8.6, 8.7**
    - `processed_count + skipped_count + error_count`가 실제 처리 수와 일치하고 500건 미초과 검증
    - `has_more` 시 `continuation_token` 존재 검증

- [x] 9. CloudWatch 메트릭 필터 Terraform 구성
  - `lambda.tf`에 `aws_cloudwatch_log_metric_filter` 리소스 추가
  - `no_citation_query` 로그 패턴 감지 → `RAGNoCitationCount` 커스텀 메트릭 발행
  - 네임스페이스: `BOS-AI/RAG`
  - _Requirements: 7.3_

- [x] 10. MCP Bridge 필터 파라미터 전달
  - [x] 10.1 `server.js` `rag_query` 도구에 `team`, `category` 파라미터 추가
    - Zod 스키마에 `z.string().optional()` 타입으로 추가
    - team 또는 category 제공 시 요청 본문에 `filter` 객체 포함
    - 둘 다 미제공 시 `filter` 객체 미포함
    - 응답의 references에 score 표시 추가
    - _Requirements: 6.1, 6.2, 6.3_
  - [ ]* 10.2 Property 6 테스트 작성: MCP Bridge 필터 요청 구성
    - **Property 6: MCP Bridge 필터 요청 구성**
    - **Validates: Requirements 6.2, 6.3**
    - 임의의 team/category 조합에 대해 filter 객체 포함/미포함 규칙 검증

- [x] 11. Final checkpoint - 전체 테스트 통과 확인
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 각 태스크는 이전 태스크의 결과물에 의존하여 점진적으로 구현
- Property 테스트는 `tests/properties/rag_search_optimization_test.go`에 Go 1.21 + gopter로 작성
- 테스트 실행: `cd tests && go test -v ./properties/ -run TestRagSearchOptimization -count=1`
- Terraform 변경은 `terraform validate`로 검증
- Lambda 코드 변경은 기존 `index.py` 파일 내에서 수행 (신규 파일 생성 없음)
