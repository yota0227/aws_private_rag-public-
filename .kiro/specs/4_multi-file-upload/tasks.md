# 구현 계획: 다중 파일/디렉토리 업로드

## 개요

Terraform IaC 변경 → Lambda 백엔드 핸들러 → 웹 UI → MCP 브릿지 순서로 의존성 기반 구현을 진행한다. 각 단계는 이전 단계의 인프라/API에 의존하므로 순차적으로 진행하되, 테스트는 각 구현 직후에 배치하여 조기 검증한다.

## Tasks

- [x] 1. Terraform IaC 변경 — DynamoDB, S3 CORS, Lambda 설정
  - [x] 1.1 DynamoDB `rag-extraction-tasks` 테이블 생성
    - `aws_dynamodb_table` 리소스 추가 (PAY_PER_REQUEST, hash_key=task_id, TTL 활성화)
    - CMK 암호화 설정 (기존 `rag_kms` 키 참조)
    - 공통 태그 적용
    - _Requirements: 7.2_
    - _Design: 5.1_

  - [x] 1.2 S3 버킷 CORS 설정 추가
    - `aws_s3_bucket_cors_configuration` 리소스 추가
    - PUT, GET, HEAD 메서드 허용, API Gateway 오리진 지정
    - _Requirements: 10.4_
    - _Design: 5.2_

  - [x] 1.3 Lambda ephemeral_storage 3072MB 설정
    - 기존 Lambda 리소스에 `ephemeral_storage { size = 3072 }` 추가
    - _Requirements: 3.4_
    - _Design: 5.3_

  - [x] 1.4 Lambda event_invoke_config 설정 (max_retry=0)
    - `aws_lambda_function_event_invoke_config` 리소스 추가
    - `maximum_retry_attempts = 0`, `maximum_event_age_in_seconds = 300`
    - _Requirements: 7.3_
    - _Design: 5.4_

  - [x] 1.5 Lambda IAM 정책 추가
    - DynamoDB PutItem/GetItem/UpdateItem/Query 정책 추가
    - Lambda 자기 자신 비동기 호출(lambda:InvokeFunction) 정책 추가
    - 기존 S3 정책에 `s3:DeleteObject` 액션 추가
    - _Requirements: 7.3, 7.4, 7.5_
    - _Design: 5.5_

  - [x] 1.6 API Gateway 새 라우트 4개 추가
    - `POST /rag/documents/presign` 리소스 + 메서드 + Lambda 통합
    - `POST /rag/documents/confirm` 리소스 + 메서드 + Lambda 통합
    - `POST /rag/documents/extract` 리소스 + 메서드 + Lambda 통합
    - `GET /rag/documents/extract-status` 리소스 + 메서드 + Lambda 통합
    - Deployment triggers에 새 리소스 ID 추가
    - _Requirements: 7.1, 7.6, 10.1_
    - _Design: 5.6_

- [x] 2. Checkpoint — Terraform 검증
  - `terraform validate` 및 `terraform plan`으로 IaC 변경 검증
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Lambda 핸들러 — Pre-signed URL 및 업로드 확인
  - [x] 3.1 `presign_upload()` 함수 구현
    - 요청 본문에서 filename, team, category, content_type 추출
    - 필수 필드 누락 시 HTTP 400 + missing_fields 반환
    - team/category 유효성 검증 (VALID_CATEGORIES 확인)
    - S3 키 생성: `documents/{team}/{category}/{filename}`
    - `s3_client.generate_presigned_url('put_object', ...)` 호출 (유효기간 3600초)
    - _Requirements: 10.1, 10.2, 10.3, 10.7_
    - _Design: 1.1, 2_

  - [x] 3.2 `confirm_upload()` 함수 구현
    - 요청 본문에서 s3_key, filename, team, category, skip_sync 추출
    - `head_object`로 S3 파일 존재 여부 확인 (미존재 시 404)
    - `skip_sync=false`이면 `trigger_kb_sync()` 호출
    - 응답에 kb_sync 상태 포함
    - _Requirements: 5.1, 5.2, 5.3, 10.5, 10.6_
    - _Design: 1.2, 2_

  - [x] 3.3 handler 라우팅에 `/documents/presign`, `/documents/confirm` 추가
    - 기존 handler 함수에 새 경로 분기 추가
    - _Requirements: 10.1_
    - _Design: 2_

  - [ ]* 3.4 Property 테스트: presign_upload 입력 검증
    - **Property 11: Pre-signed URL 입력 검증**
    - hypothesis로 filename/team/category 조합 생성, 누락 시 400 응답 검증
    - **Validates: Requirements 10.7**

  - [ ]* 3.5 Property 테스트: Pre-signed URL S3 키 경로 생성
    - **Property 10: Pre-signed URL S3 키 경로 생성**
    - hypothesis로 유효한 filename/team/category 조합 생성, s3_key 형식 검증
    - **Validates: Requirements 10.2**

  - [ ]* 3.6 Property 테스트: skip_sync에 의한 KB Sync 제어
    - **Property 8: skip_sync 파라미터에 의한 KB Sync 제어**
    - hypothesis로 skip_sync boolean 생성, KB Sync 호출 여부 검증
    - **Validates: Requirements 5.1, 5.2, 5.4**

- [x] 4. Lambda 핸들러 — 비동기 압축 해제
  - [x] 4.1 `flatten_path()` 유틸리티 함수 구현
    - `/` 구분자를 `_`로 변환하여 단일 파일명 생성
    - 숨김 파일(`.` 시작) 및 시스템 파일 필터링 로직 포함
    - _Requirements: 3.3_
    - _Design: 데이터 모델 — 압축 해제 시 파일명 변환 규칙_

  - [ ]* 4.2 Property 테스트: 경로 평탄화 변환
    - **Property 5: 경로 평탄화 변환**
    - hypothesis로 다양한 경로 문자열 생성, `/` → `_` 변환 및 구성 요소 보존 검증
    - **Validates: Requirements 3.3**

  - [x] 4.3 `start_extraction()` 함수 구현
    - 요청 본문에서 s3_key, team, category 추출
    - task_id 생성: `ext-{YYYYMMDD}-{uuid4[:8]}`
    - DynamoDB에 초기 레코드 생성 (status="대기중", created_at, ttl)
    - `boto3.client('lambda').invoke(InvocationType='Event', ...)` 비동기 호출
    - HTTP 202 + task_id 즉시 반환
    - _Requirements: 7.1, 7.2, 7.3_
    - _Design: 1.3, 2_

  - [x] 4.4 `process_extraction()` 함수 구현
    - DynamoDB 상태를 "처리중"으로 갱신
    - S3에서 Archive 다운로드 → `/tmp`에 압축 해제
    - zip/tar.gz 형식 분기 처리
    - 지원 파일만 S3 업로드, 비지원 파일은 skipped_files에 기록
    - `flatten_path()`로 파일명 변환
    - 원본 Archive S3 삭제
    - DynamoDB 상태를 "완료"로 갱신 + results 기록
    - `trigger_kb_sync()` 호출
    - 전체 try/except로 감싸서 실패 시 DynamoDB status="실패" + /tmp 정리
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.4, 7.4, 7.5_
    - _Design: 1.3, 2_

  - [x] 4.5 `get_extraction_status()` 함수 구현
    - query parameter에서 task_id 추출 (누락 시 400)
    - DynamoDB GetItem으로 상태 조회
    - 미존재 시 404 반환
    - 존재 시 status, results, created_at, updated_at 반환
    - _Requirements: 7.6, 7.7, 7.8_
    - _Design: 1.4, 2_

  - [x] 4.6 handler 라우팅에 `/documents/extract`, `/documents/extract-status` 및 비동기 action 분기 추가
    - `event.get('action') == 'process_extraction'` 분기 추가
    - 기존 handler에 새 경로 분기 추가
    - _Requirements: 7.1, 7.6_
    - _Design: 2_

  - [ ]* 4.7 Property 테스트: Extraction Task 상태 머신
    - **Property 9: Extraction Task 상태 머신**
    - hypothesis로 상태 전이 시퀀스 생성, 유효한 전이만 허용되는지 검증
    - **Validates: Requirements 3.1, 7.2, 7.3, 7.4, 7.5**

  - [ ]* 4.8 Property 테스트: 비지원 파일 건너뛰기
    - **Property 6: 비지원 파일 건너뛰기**
    - hypothesis로 지원/비지원 파일 혼합 목록 생성, 건너뛰기 동작 검증
    - **Validates: Requirements 3.5**

  - [ ]* 4.9 Property 테스트: 압축 해제 결과 카운트 불변식
    - **Property 7: 압축 해제 결과 카운트 불변식**
    - hypothesis로 다양한 파일 조합 생성, success + skipped + error == total 검증
    - **Validates: Requirements 3.6**

  - [ ]* 4.10 Property 테스트: Extraction 상태 조회 라운드트립
    - **Property 12: Extraction 상태 조회 라운드트립**
    - hypothesis로 DynamoDB 레코드 생성 후 GET 조회, 데이터 일치 검증
    - **Validates: Requirements 7.7**

- [x] 5. Checkpoint — Lambda 백엔드 검증
  - Lambda 핸들러 단위 테스트 실행
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 웹 UI — 파일 선택 및 유효성 검증
  - [x] 6.1 다중 파일 선택 + 디렉토리 선택 UI 구현
    - `<input type="file" multiple>` 다중 파일 선택 버튼
    - `<input type="file" webkitdirectory>` 디렉토리 선택 버튼 (별도)
    - 드래그 앤 드롭 영역 구현 (`DataTransferItem.webkitGetAsEntry()` 사용)
    - 파일 대기 목록 UI (파일명, 크기, 상태, 제거 버튼)
    - 파일 유형 아이콘 표시
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 2.1, 6.5_
    - _Design: 3.1_

  - [x] 6.2 디렉토리 재귀 탐색 함수 구현
    - `traverseDirectory()` — `entry.isFile`/`entry.isDirectory` 분기 재귀 탐색
    - 숨김 파일(`.` 시작) 및 시스템 파일(`__MACOSX`, `Thumbs.db`, `.DS_Store`) 필터링
    - 상대 경로를 파일명에 포함하여 표시
    - _Requirements: 2.2, 2.3, 2.4, 2.5_
    - _Design: 3.5_

  - [x] 6.3 파일 유효성 검증 함수 구현
    - `validateFile()` — 확장자 검증 (pdf, txt, docx, csv, html, md, zip, tar.gz)
    - 일반 파일 100MB, 압축 파일 500MB 크기 제한
    - 비유효 파일 시 경고 메시지 표시
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
    - _Design: 3.2_

  - [x] 6.4 파일 큐 관리 함수 구현
    - `addFiles()` — 기존 대기 목록에 새 파일 병합, 동일 파일명 중복 방지
    - `removeFile()` — 대기 목록에서 개별 파일 제거
    - _Requirements: 1.3, 1.5_
    - _Design: 3.1_

  - [ ]* 6.5 Property 테스트: 파일 큐 병합 시 중복 방지
    - **Property 1: 파일 큐 병합 시 중복 방지**
    - fast-check로 두 파일 목록 생성, 병합 후 중복 없음 + 모든 고유 파일 존재 검증
    - **Validates: Requirements 1.2, 1.3**

  - [ ]* 6.6 Property 테스트: 파일 제거 후 큐 무결성
    - **Property 2: 파일 제거 후 큐 무결성**
    - fast-check로 큐 + 유효 인덱스 생성, 제거 후 길이 감소 + 파일 부재 검증
    - **Validates: Requirements 1.5**

  - [ ]* 6.7 Property 테스트: 디렉토리 재귀 탐색 및 필터링
    - **Property 3: 디렉토리 재귀 탐색 및 필터링**
    - fast-check로 파일 트리 구조 생성, 숨김/시스템 파일 제외 검증
    - **Validates: Requirements 2.2, 2.3, 2.4**

  - [ ]* 6.8 Property 테스트: 파일 유효성 검증
    - **Property 4: 파일 유효성 검증 (형식 + 크기)**
    - fast-check로 다양한 파일명/크기 생성, 허용/거부 판정 검증
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

- [x] 7. 웹 UI — Pre-signed URL 업로드 플로우 및 진행률
  - [x] 7.1 Pre-signed URL 업로드 함수 구현
    - `uploadFilePresigned()` — presign → S3 PUT → confirm 순차 호출
    - XMLHttpRequest `upload.onprogress`로 개별 파일 진행률 추적
    - `skip_sync` 파라미터: 마지막 파일만 `false`
    - 압축 파일인 경우 confirm 후 `/documents/extract` 호출
    - Pre-signed URL 만료(403) 시 자동 재요청 + 재시도
    - _Requirements: 4.1, 4.2, 4.4, 5.1, 5.2, 5.3, 10.4, 10.5, 10.8_
    - _Design: 3.3_

  - [x] 7.2 전체 업로드 오케스트레이션 구현
    - 대기 목록 파일 순차 업로드 루프
    - 전체 진행 상황 "N/M 파일 완료" 표시
    - 개별 파일 오류 시 상태를 "오류"로 표시하고 나머지 계속 진행
    - 전체 완료 시 결과 요약 토스트 메시지 (성공 수, 실패 수)
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6_
    - _Design: 3.3, 3.4_

  - [x] 7.3 압축 해제 상태 폴링 UI 구현
    - `startPolling()` — 5초 간격으로 `GET /extract-status` 호출
    - 상태 표시: 대기중 → 처리중 → 완료/실패
    - 완료 시 문서 목록 자동 갱신
    - 폴링 중 네트워크 오류 시 계속 시도 (최대 60회 = 5분)
    - _Requirements: 9.2, 9.4_
    - _Design: 3.4_

  - [x] 7.4 업로드 완료 후 문서 목록 갱신
    - 모든 파일 업로드 완료 시 문서 목록 자동 재조회
    - 현재 선택된 팀/카테고리 필터 유지
    - _Requirements: 9.1, 9.3_
    - _Design: 3.4_

  - [ ]* 7.5 Property 테스트: 업로드 오류 복원력
    - **Property 13: 업로드 오류 복원력**
    - fast-check로 성공/실패 파일 목록 생성, 실패 시에도 나머지 계속 진행 + 성공수+실패수==전체수 검증
    - **Validates: Requirements 4.5**

- [x] 8. Checkpoint — 웹 UI 검증
  - 웹 UI JavaScript 단위 테스트 실행
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. MCP 브릿지 도구 추가
  - [x] 9.1 `rag_upload_status` 도구 구현
    - `server.js`의 `createMcpServer()`에 도구 등록
    - team/category 선택적 필터 파라미터
    - `GET /documents` 엔드포인트 호출하여 최근 업로드 파일 목록 + KB Sync 상태 반환
    - _Requirements: 8.1, 8.2_
    - _Design: 4.1_

  - [x] 9.2 `rag_extract_status` 도구 구현
    - `server.js`의 `createMcpServer()`에 도구 등록
    - task_id 필수 파라미터
    - `GET /rag/documents/extract-status?task_id=` 엔드포인트 호출하여 상태 반환
    - _Requirements: 8.3, 8.4_
    - _Design: 4.2_

- [x] 10. 최종 Checkpoint — 전체 통합 검증
  - 전체 테스트 스위트 실행 (Python + JavaScript)
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- `*` 표시된 태스크는 선택적이며 빠른 MVP를 위해 건너뛸 수 있음
- 각 태스크는 추적 가능성을 위해 특정 요구사항을 참조함
- Checkpoint에서 점진적 검증을 수행함
- Property 테스트는 보편적 정확성 속성을 검증하고, 단위 테스트는 구체적 예시와 엣지 케이스에 집중함
