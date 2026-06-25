# Implementation Plan: MCP Tool-Layer Optimization

> **Created:** 2026-06-16
> **Updated:** 2026-06-16
> **Purpose:** 승인된 design.md를 구현하기 위한 코딩 작업 체크리스트 — `mcp-bridge/` Node.js 브리지에 lib 모듈·withTool 래퍼·신규 도구·비동기 job·관측성을 가산적으로 추가하고 기존 17개 도구 계약을 보존한다.
> **Spec / Project:** `.kiro/specs/mcp-tool-optimization/`
> **Status:** Draft
> **Owner:** Infra/DevOps + RAG MCP

## Overview

본 계획은 운영 중인 단일 Node.js MCP 브리지(`mcp-bridge/server.js`, CommonJS)의 도구 계층을 **가산적으로** 진화시킨다. 구현 언어는 JavaScript(Node.js, CommonJS)로 `server.js`와 동일하다. 테스트는 내장 `node:test` + `fast-check`를 `mcp-bridge/tests/` 아래에서 실행한다.

구현 순서는 design.md의 진화 전략을 따른다: ① 테스트 하니스 → ② Open Question 해소(게이팅 스파이크) → ③ 횡단 lib 모듈(`uri`→`errors`→`envelope`→`logging`→`metrics`) → ④ `withTool()` 래퍼 wiring → ⑤ 도구 설명/스키마 명확화 → ⑥ 기존 검색 도구를 그룹 단위로 재배선(계약 불변) → ⑦ evidence-first → ⑧ 신규 운영 도구 → ⑨ 비동기 job 프레임워크 → ⑩ 하우스키핑 → ⑪ 엔드유저 가이드. 각 단계는 17개 기존 도구의 이름·시그니처·`content[].text` 출력 형식을 깨지 않으며, 신규 필드는 텍스트 말미 구조화 블록으로만 덧붙고 신규 파라미터는 모두 optional이다.

모든 도구 핸들러 코드 변경은 `mcp-bridge/server.js`와 `mcp-bridge/lib/`에 한정한다. 인프라(Go/gopter, `tests/`)와 Lambda(Python, `rtl_parser_src/`) 테스트는 본 spec 범위 밖이며 변경하지 않는다.

## Tasks

- [x] 1. 테스트 하니스 및 lib 디렉토리 골격 설정
  - `mcp-bridge/package.json`에 `"test": "node --test"` 스크립트 추가(watch 모드 아님, 1회 실행)
  - `fast-check`를 `devDependencies`에 추가하고 `node:test`로 동작하는 최소 smoke 테스트 1건(`mcp-bridge/tests/harness.test.js`)으로 러너 동작 확인
  - `mcp-bridge/lib/` 및 `mcp-bridge/tests/` 디렉토리 생성, 속성 테스트 태그 주석 컨벤션(`// Feature: mcp-tool-optimization, Property N: ...`) 문서화
  - 기존 `start → server.js` 스크립트는 변경하지 않음(보존)
  - _Requirements: 7.2_

- [ ] 2. Open Question 해소 (게이팅 스파이크 — envelope/jobs 결정 입력)
  - [ ]* 2.1 OQ-1 백엔드 index_version/resolved_snapshot 지원 조사 스파이크
    - `lambda-document-processor-seoul-prod` 및 `lambda-rtl-parser-seoul-dev` 응답에 `index_version`/`resolved_snapshot` 필드 존재 여부를 `ragApi` 응답 형태로 확인
    - 부재 시 envelope fallback 정확 규칙(`index_version: "unknown"`, snapshot 채움 규칙)을 짧은 결정 노트로 design Open Question 1에 연계 기록
    - 결과가 `lib/envelope.js`(Task 5) 채움 규칙을 확정함
    - _Requirements: 2.3, 2.4_
  - [ ]* 2.2 OQ-2/OQ-3 Job 저장소 및 SDK Tasks 지원 결정 스파이크
    - Job 상태 저장소 선택(신규 DynamoDB `bos-ai-mcp-jobs` vs 기존 claim DB 테이블 재사용)을 폐쇄망·Terraform·비용 기준으로 비교
    - `@modelcontextprotocol/sdk` 버전의 비동기 task 기능 유무 확인 → 커스텀 `Job_Dispatcher` 유지 여부 결정
    - 결과가 `lib/jobs/store.js`(Task 16) 구현 방식을 확정함
    - _Requirements: 5.1, 5.2_

- [x] 3. Resource_URI 모듈 (`lib/uri.js`) 구현
  - 닫힌 6개 스킴 집합(`rag`, `rtl`, `graph`, `claim`, `job`, `index`) 정의
  - `parseUri(uri)`(미지원 스킴/빈·공백 식별자 시 InvalidUriError throw), `buildUri(scheme, id)`(검증 후 `<scheme>://<id>` 생성), `isWellFormed(uri)` 구현
  - 라운드트립 보장: well-formed `u`에 대해 `buildUri(parseUri(u))` 동일성
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 3.2 `lib/uri.js` 라운드트립 속성 테스트
    - **Property 4: Resource_URI 라운드트립** (`job://<job_id>` 복원 포함)
    - **Validates: Requirements 8.4, 5.5**

  - [ ]* 3.3 `lib/uri.js` well-formed 판정 속성 테스트
    - **Property 5: well-formed 판정 규칙**
    - **Validates: Requirements 8.1, 8.2**

- [x] 4. Error_Schema 모듈 (`lib/errors.js`) 구현
  - `ERROR_CODES`(invalid_uri/not_found/upstream_error), `makeError(code, message)`(정확히 1개 코드 + 비어있지 않은 메시지)
  - `classify(err)`: URI 위반→invalid_uri, 자원/job/claim 부재→not_found, 그 외 일체→upstream_error
  - `renderError(errObj)`: 기존 `isError: true` + `content[].text` 형식 유지, 부분 Resource_URI/index_version/resolved_snapshot 미부착
  - `lib/uri.js`의 InvalidUriError를 invalid_uri로 매핑
  - _Requirements: 2.7, 2.8, 2.9, 4.4, 4.5, 4.7, 4.8_

  - [ ]* 4.2 `lib/errors.js` 에러 분류 속성 테스트
    - **Property 11: 에러 분류 단일성**
    - **Validates: Requirements 2.7, 2.8, 4.8**

  - [ ]* 4.3 `lib/errors.js` invalid_uri 신호 속성 테스트
    - **Property 6: 잘못된 URI는 invalid_uri로 신호되고 반환되지 않음**
    - **Validates: Requirements 8.5, 8.6, 4.4**

- [x] 5. 출력 envelope 모듈 (`lib/envelope.js`) 구현
  - `appendEnvelope(text, meta)`: 기존 텍스트를 prefix로 보존하고 말미에 `--- structured ---` JSON 블록(index_version/resolved_snapshot/resource_uris/request_id) 추가
  - addressable 결과만 well-formed Resource_URI 부착(`lib/uri.js` 검증), non-addressable은 `resource_uris` 항목 생략(빈/null/placeholder 금지)
  - `index_version` 비어있지 않게 보장(백엔드 미지원 시 OQ-1 결정에 따른 fallback `"unknown"`)
  - `resolved_snapshot` 해석: latest/미지정→백엔드 해석 구체값, 명시 스냅샷→echo, 어느 경우든 리터럴 `"latest"` 금지(불변식 위반 시 upstream_error)
  - 에러 경로에서는 envelope 부가필드를 부착하지 않음(`lib/errors.js`와 연계)
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.10, 2.11_

  - [ ]* 5.2 `lib/envelope.js` index_version 속성 테스트
    - **Property 9: 모든 retrieval 결과에 비어있지 않은 index_version**
    - **Validates: Requirements 2.3**

  - [ ]* 5.3 `lib/envelope.js` resolved_snapshot 해석 속성 테스트
    - **Property 10: resolved_snapshot 해석 — 절대 "latest" 아님**
    - **Validates: Requirements 2.4, 2.5, 2.6**

  - [ ]* 5.4 `lib/envelope.js` non-addressable URI 생략 속성 테스트
    - **Property 8: non-addressable 결과는 URI 필드를 생략**
    - **Validates: Requirements 2.2**

  - [ ]* 5.5 `lib/envelope.js` 반환 URI 안정·유일 속성 테스트
    - **Property 7: 반환되는 URI는 항상 well-formed이고 자원에 대해 안정·유일**
    - **Validates: Requirements 8.3, 2.1**

  - [ ]* 5.6 `lib/envelope.js` 형식 불변·가산성 속성 테스트
    - **Property 13: 응답 형식 불변성 + 가산성**
    - **Validates: Requirements 2.10, 2.11, 4.9, 8.8**

  - [ ]* 5.7 에러 응답 부분필드 금지 속성 테스트
    - **Property 12: 에러 응답은 Error_Schema만 포함**
    - **Validates: Requirements 2.9**

- [x] 6. 구조화 로깅 모듈 (`lib/logging.js`) 구현
  - CloudWatch Logs로 호출당 정확히 1건의 JSON 레코드 방출(request_id/tool/latency_ms/outcome∈{success,failure}/timestamp UTC ISO 8601, 실패 시 error_category)
  - `newRequestId()`(crypto.randomUUID, 프로세스 수명 내 유일), 들어온 request_id 재사용 헬퍼
  - 사용자/팀 식별자 및 corpus allowed/denied 필드 화이트리스트 배제
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.8, 6.9_

  - [ ]* 6.2 `lib/logging.js` request_id 재사용/생성 속성 테스트
    - **Property 25: request_id 재사용/생성 유일성**
    - **Validates: Requirements 6.3, 6.4**

  - [ ]* 6.3 `lib/logging.js` 관측성 필드 화이트리스트 속성 테스트
    - **Property 27: 관측성 출력 필드 화이트리스트 (식별자-free)**
    - **Validates: Requirements 6.8, 6.9**

- [x] 7. latency 메트릭 모듈 (`lib/metrics.js`) 구현
  - rolling 5분 윈도우 latency(ms) 적재, 윈도우 밖 샘플 만료
  - `record(tool, latency_ms)`, `percentiles(tool) -> { p50, p95, p99 }`(ms) 구현, 식별자 불필요
  - _Requirements: 6.6_

  - [ ]* 7.2 `lib/metrics.js` 백분위 단조성·윈도우 속성 테스트
    - **Property 26: latency 백분위 단조성 + 윈도우**
    - **Validates: Requirements 6.6**

- [x] 8. `withTool()` 래퍼 wiring (`server.js`)
  - [x] 8.1 `withTool(toolName, handler)` 래퍼를 `server.js`에 구현
    - request_id 확보(헤더 재사용 또는 `logging.newRequestId()` 생성), `process.hrtime` 기반 latency 측정
    - 성공/실패 모두 `metrics.record` + `logging.emit` 1건, 미처리 예외를 `errors.classify`→`renderError`로 변환
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7_
  - [x] 8.2 기존 핸들러의 `console.log`/인라인 `Date.now()` 제거하고 `withTool`로 일괄 래핑
    - 17개 도구 등록부를 `withTool`로 감싸 호출 경로에서 `console.log` 제거(Lambda invoke 오류 로그 등 비-호출경로는 별도 판단)
    - 도구 이름·입력 시그니처·텍스트 출력은 불변 유지
    - _Requirements: 6.7, 1.7, 7.6_

  - [ ]* 8.3 `withTool` 구조화 로그 속성 테스트
    - **Property 24: 호출당 정확히 1건의 구조화 로그**
    - **Validates: Requirements 6.1, 6.2, 6.5**

- [x] 9. Checkpoint — lib 기반 및 wiring 검증
  - `npm test`(`node --test`) 실행하여 Task 3~8의 모든 통과 테스트 확인, 기존 17개 도구가 변경 없이 등록되는지 확인. 의문 발생 시 사용자에게 질문.

- [x] 10. 도구 설명·스키마 명확화 (`lib/tool-descriptions.js`)
  - [x] 10.1 `lib/tool-descriptions.js`에 도구별 설명 상수 정의
    - 각 설명에 (a) 목적, (b) 각 입력 의미, (c) 최소 1개 구체 예시, (d) 겹치는 입력 disambiguation("이 도구를 쓸 때 / 다른 도구를 쓸 때", 정확한 등록명 인용) 포함
    - `rag_query`/`search_rtl`/`search_archive`는 형제 도구를 정확한 등록명으로 상호 참조
    - design.md의 Tool-selection guidance 표를 코드 주석/상수로 참조
    - _Requirements: 1.1, 1.2, 1.5, 1.6, 1.8_
  - [x] 10.2 기존 17개 도구의 description/zod 스키마를 `tool-descriptions.js`로 재배선
    - 모든 zod 파라미터에 타입 + `.describe()` + required/optional 명시
    - 도구 이름·파라미터 시그니처 불변, 신규 파라미터는 없음(이 단계)
    - _Requirements: 1.3, 1.4, 1.7, 7.6_

  - [ ]* 10.3 도구 설명 완전성 속성 테스트
    - **Property 1: 도구 설명 완전성** (기존 17 + 신규 4)
    - **Validates: Requirements 1.1, 1.8**

  - [ ]* 10.4 zod 스키마 계약 완전성 속성 테스트
    - **Property 2: zod 스키마 계약 완전성**
    - **Validates: Requirements 1.3, 1.4, 1.8**

  - [ ]* 10.5 기존 시그니처 보존 속성 테스트
    - **Property 3: 기존 시그니처 보존 + 신규 파라미터 optional**
    - **Validates: Requirements 1.7, 7.6**

- [x] 11. 기존 검색 도구 재배선 — 그룹 A (`rag_query`, `search_rtl`, `search_archive`)
  - 각 핸들러가 결과를 `lib/envelope.js`로 감싸 Resource_URI(`search_archive`의 기존 `uri` / `search_rtl`의 `file_path`·`module_name` / `rag_query`의 citations 기반) + index_version + resolved_snapshot를 텍스트 말미에 부착
  - 기존 사람이 읽는 텍스트 본문과 `execution_time_ms` 동작은 보존(prefix 유지)
  - non-addressable 결과는 URI 생략, 에러는 `lib/errors.js` 경로로만 반환
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.10, 2.11, 8.3, 8.8_

- [x] 12. 기존 도구 재배선 — 그룹 B (그래프·claim 도구)
  - `trace_signal_path`, `find_instantiation_tree`, `find_clock_crossings`, `graph_export`, `list_verified_claims`에 envelope 적용(`graph://`/`claim://` Resource_URI + index_version + resolved_snapshot)
  - 텍스트 출력·시그니처 보존, 에러는 `lib/errors.js` 경로
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.10, 2.11, 8.3, 8.8_

- [x] 13. Evidence-first 컴포넌트
  - [x] 13.1 `lib/evidence.js` get_evidence 정규화 구현
    - 백엔드 필드(`source_document_id`/`source_type`/`source_chunk`/`page_number`/`source_path`/`line_start`/`line_end`)를 정규 스키마(`source_uri`/`source_type`/`support_level`/`confidence` 0..1 클램프/`span`)로 매핑
    - evidence 0건이면 빈 리스트 반환(Error_Schema 아님), `get_evidence` 핸들러를 정규화 출력으로 재배선
    - _Requirements: 3.1, 3.2_
  - [ ]* 13.2 evidence 정규화 속성 테스트
    - **Property 14: Evidence 정규화**
    - **Validates: Requirements 3.1, 3.2**
  - [x] 13.3 `rag_validate_answer` 신규 도구 구현
    - 입력 `{ answer: string }`(zod required), 문장 분할 → 문장별 evidence 연결 수 계산(0이면 unsupported)
    - per-sentence supported/unsupported 라벨 + unsupported 문장 text/position 목록을 구조화 블록에 포함
    - 빈/공백 answer는 Error_Schema 반환, `tool-descriptions.js`에 설명·스키마 등록
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 4.9_
  - [ ]* 13.4 답변 검증 coverage 속성 테스트
    - **Property 15: 답변 검증 coverage**
    - **Validates: Requirements 3.3, 3.4, 3.5**
  - [ ]* 13.5 빈/공백 답변 거부 속성 테스트
    - **Property 16: 빈/공백 답변 거부**
    - **Validates: Requirements 3.6**
  - [x] 13.6 `generate_hdd_section` verified-only 모드 추가
    - optional 파라미터 `allow_unverified_inference: boolean` 추가(기본 동작 보존), `false`일 때 지원 evidence 0 세그먼트를 `content[].text`에 마커 "확실하지 않음"으로 표기
    - 기존 파라미터·출력 유지(가산)
    - _Requirements: 3.7, 1.7_
  - [ ]* 13.7 verified-only HDD 표기 속성 테스트
    - **Property 17: verified-only HDD 표기**
    - **Validates: Requirements 3.7**
  - [x] 13.8 `publish_markdown` pre-save 가드 추가
    - 백엔드 저장 호출 **이전**에 콘텐츠 검사: 미지원 문장 1개 이상 또는 미해석 `latest` 참조 시 발행 거부 + Error_Schema, 어떤 부분도 저장하지 않음
    - 기존 시그니처·정상 경로 출력 보존
    - _Requirements: 3.8, 3.9, 1.7_
  - [ ]* 13.9 publish 가드 속성 테스트
    - **Property 18: publish 가드**
    - **Validates: Requirements 3.8, 3.9**

- [x] 14. Checkpoint — evidence-first 검증
  - `npm test` 실행하여 Task 11~13 테스트 통과 및 기존 도구 텍스트 출력 보존 확인. 의문 발생 시 사용자에게 질문.

- [x] 15. 신규 운영 도구
  - [x] 15.1 `rag_index_status` 신규 도구 구현
    - 입력 없음, 인덱스별 `{ index_version, last_updated_at(ISO 8601 UTC), embedding_model }` 리스트 반환, 인덱스 없으면 빈 리스트(Error 아님)
    - `tool-descriptions.js` 등록, `content[].text` 가산 형식
    - _Requirements: 4.1, 4.2, 4.9_
  - [ ]* 15.2 index_status 필드 완전성 속성 테스트
    - **Property 19: index_status 필드 완전성**
    - **Validates: Requirements 4.1, 4.2**
  - [x] 15.3 `rag_read_resource` 신규 도구 구현
    - 입력 `{ resource_uri: string }`(required), `lib/uri.js`로 검증 후 원문/스팬 반환
    - malformed→invalid_uri(부분 콘텐츠 없음), well-formed지만 부재→not_found, 그 외→upstream_error
    - _Requirements: 4.3, 4.4, 4.5, 4.8, 4.9_
  - [ ]* 15.4 read_resource 존재/부재 속성 테스트
    - **Property 20: read_resource 존재/부재 처리**
    - **Validates: Requirements 4.3, 4.5**

- [x] 16. 비동기 Job 프레임워크
  - [x] 16.1 `lib/jobs/store.js` 저장소 추상화 구현
    - `put(job)`/`get(job_id)`(없으면 null)/`update(job_id, patch)` 인터페이스를 저장소 무관하게 구현(OQ-2 결정 반영)
    - Job 레코드 스키마(job_id/type/status/created_at/updated_at/result/error) 정의
    - _Requirements: 5.3, 5.4_
  - [x] 16.2 `lib/jobs/dispatcher.js` Job_Dispatcher 구현
    - `createJob(type, payload)`: job_id=randomUUID, `store.put(status=queued)`, 백그라운드 `runJob()` 시작(await 안 함), `status_uri = buildUri("job", job_id)` 반환(2초 이내)
    - `runJob(job)`: running→done(result)/failed(error) 상태 전이
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 5.8_
  - [ ]* 16.3 Job 비블로킹 속성 테스트
    - **Property 22: Job 디스패치 비블로킹** (지연 mock으로 검증)
    - **Validates: Requirements 5.1, 5.2**
  - [ ]* 16.4 Job lifecycle 일관성 속성 테스트
    - **Property 23: Job lifecycle 일관성**
    - **Validates: Requirements 4.6, 5.3, 5.4, 5.6, 5.7, 5.8**
  - [x] 16.5 `rag_task_status` 신규 도구 구현
    - 입력 `{ job_id: string }`(required), 알려진 job→`queued|running|done|failed` 중 하나(done이면 result, failed면 error indication), queued/running이면 최종 결과 없이 현재 상태
    - 미지 job→not_found, 그 외→upstream_error, `tool-descriptions.js` 등록
    - _Requirements: 4.6, 4.7, 4.8, 4.9, 5.6, 5.7, 5.8_
  - [ ]* 16.6 미지 job not_found 속성 테스트
    - **Property 21: 미지 job은 not_found**
    - **Validates: Requirements 4.7**
  - [x] 16.7 `regenerate_stale_hdd`와 reindex를 비동기 job으로 전환
    - `regenerate_stale_hdd` 핸들러를 `dispatcher.createJob`로 전환하여 2초 내 job_id + `job://` URI 반환(입력 없음 → 시그니처 보존 자명)
    - reindex 동작도 동일하게 job 반환으로 전환
    - _Requirements: 5.1, 5.2, 1.7_

- [x] 17. Checkpoint — 신규 도구·job 검증
  - `npm test` 실행하여 Task 15~16 테스트 통과 및 신규 4개 도구 등록 확인. 의문 발생 시 사용자에게 질문.

- [x] 18. 하우스키핑 — 단일 진실 원천 통합
  - [x] 18.1 `server.mjs` drift 해소 및 단일 entrypoint 확정
    - `server.mjs`의 고유 정의 유무 판단 → QuickSight 외 고유 도구 있으면 `server.js`로 이관 후 `server.mjs` 제거, 없으면 바로 제거
    - 통합 후 `server.js`의 기존 등록 도구를 이름·시그니처 불변으로 보존, `package.json` `start`는 `server.js` 유지
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.6_
  - [x] 18.2 QuickSight 도구 처분 결정 구현 및 의존성 정리
    - 결정 문서(`docs/` 하위 decision 문서)에 `quick_dashboard_list`/`quick_dashboard_data` 유지/제거 결정과 근거 기록(design 권고: 제거)
    - 제거 결정 시 두 도구를 `server.js`에 등록하지 않고 `package.json`의 `@aws-sdk/client-quicksight` 의존성 제거; 유지 결정 시 `server.js`에 등록
    - _Requirements: 7.5, 7.7, 7.8_

- [x] 19. 엔드유저 가이드 작성 (다운스트림 산출물)
  - `docs/` 하위에 MCP 도구 사용 가이드 문서 작성(doc-template 메타데이터 헤더 포함)
  - 내용: Tool-selection 가이드(특히 `rag_query` vs `search_rtl` vs `search_archive`), 신규 4개 도구(`rag_validate_answer`/`rag_index_status`/`rag_read_resource`/`rag_task_status`) 사용법, Resource_URI 6스킴과 `rag_read_resource` 재조회법(접근제어 아님 명시), 비동기 job polling 흐름, 에러 코드(`invalid_uri`/`not_found`/`upstream_error`) 해석
  - _Requirements: 1.6_

- [x] 20. Final Checkpoint — 전체 테스트 스위트
  - `npm test`(`node --test`) 전체 실행하여 27개 속성 테스트 및 예시/스모크 테스트 통과 확인, 기존 17개 도구 계약 무손상 확인. 의문 발생 시 사용자에게 질문.

## Notes

- **JS 테스트 실행:** `cd mcp-bridge && npm test` (= `node --test`, 1회 실행). watch 모드 사용 금지. 속성 테스트는 `fast-check`로 최소 `{ numRuns: 100 }`.
- **하위 호환 불변식:** 모든 단계에서 기존 17개 도구 이름·입력 시그니처·`content[].text` 텍스트 출력을 보존한다. 신규 필드는 텍스트 말미 구조화 블록으로만 추가하고, 신규 파라미터는 모두 optional이다.
- `*` 표시 sub-task(속성/스파이크)는 optional이며 빠른 MVP에서 건너뛸 수 있다. 핵심 구현 sub-task와 가이드(Task 19)는 필수다.
- **영향받지 않는 테스트:** 인프라 Go/gopter 테스트(`tests/`)와 Lambda Python 테스트(`rtl_parser_src/`)는 변경하지 않는다. OQ-1 백엔드 필드 채택 시에만 별도 spec으로 Lambda 테스트가 갱신된다.
- **Terraform validate 가이드:** Job 저장소로 신규 DynamoDB 테이블(`bos-ai-mcp-jobs`)을 택하면(OQ-2) 해당 리소스는 `environments/app-layer/bedrock-rag/`에서 Terraform으로 관리하고 `terraform validate` + `tflint`로 검증한다(required tags: Project/Environment/ManagedBy). 본 spec의 코드 작업은 저장소 인터페이스(`lib/jobs/store.js`)에 한정한다.
- 각 속성 테스트는 대응 설계 속성을 주석으로 태깅한다: `// Feature: mcp-tool-optimization, Property N: ...`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "3", "4", "6", "7", "10.1", "16.1"] },
    { "id": 2, "tasks": ["5", "16.2", "3.2", "3.3", "4.2", "4.3", "6.2", "6.3", "7.2"] },
    { "id": 3, "tasks": ["8.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "16.3", "16.4"] },
    { "id": 4, "tasks": ["8.2"] },
    { "id": 5, "tasks": ["10.2", "8.3"] },
    { "id": 6, "tasks": ["11"] },
    { "id": 7, "tasks": ["12"] },
    { "id": 8, "tasks": ["13.1"] },
    { "id": 9, "tasks": ["13.3", "13.2"] },
    { "id": 10, "tasks": ["13.6", "13.4", "13.5"] },
    { "id": 11, "tasks": ["13.8", "13.7"] },
    { "id": 12, "tasks": ["15.1", "13.9"] },
    { "id": 13, "tasks": ["15.3", "15.2"] },
    { "id": 14, "tasks": ["16.5", "15.4"] },
    { "id": 15, "tasks": ["16.7", "16.6"] },
    { "id": 16, "tasks": ["18.1"] },
    { "id": 17, "tasks": ["18.2"] },
    { "id": 18, "tasks": ["10.3", "10.4", "10.5", "19"] }
  ]
}
```
