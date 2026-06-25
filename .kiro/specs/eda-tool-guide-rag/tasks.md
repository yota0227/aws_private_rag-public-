# Implementation Plan: EDA Tool Guide 자산화 (Tool Guide RAG)

> **Created:** 2026-06-17
> **Updated:** 2026-06-18
> **Purpose:** requirements.md·design.md 기반으로 Tool Guide RAG MVP를 점진적으로 구현하기 위한 코딩 작업 체크리스트. 결정론적 파서(Python 3.12/Hypothesis)와 MCP 결과 가공 로직을 핵심 대상으로 한다.
> **Spec / Project:** `.kiro/specs/eda-tool-guide-rag/`
> **Status:** Draft
> **Owner:** BOS-AI Private RAG

## Overview

구현 접근은 design.md의 제1원칙("새 임베딩 스택을 만들지 않고 기존 RTL RAG 파이프라인 메커니즘에 문서 파서를 끼운다")을 따른다. 신규 코드 작업은 (1) `Tool_Guide_Parser` 결정론적 추출 로직(순수 함수 `parse_structure` + 객체 빌더), (2) 공통 객체 스키마/메타데이터 채움, (3) 임베딩·인덱스 적재 연동, (4) `Tool_Guide_MCP` 결과 가공 로직(길이 검증·권한 검사·필터·cap·citation)에 집중한다.

언어: 파서·MCP 결과 가공 로직은 모두 **Python 3.12**(로컬 테스트는 Python 3.13 + `py -m pytest`, tech.md 규약). 속성 테스트는 **Hypothesis**로 작성하며 design.md "Correctness Properties"의 12개 속성을 각각 단일 속성 테스트로 구현한다. S3 전용 버킷/CRR, Qdrant collection, DynamoDB 파티션, 별도 포트(:3101) MCP 서비스 기동은 IaC/구성·외부 서비스 영역으로 본 코딩 작업의 단위/속성 테스트 대상이 아니라 통합/스모크 검증으로 다룬다.

각 단계는 이전 단계 위에 점진적으로 쌓이며, 마지막에 서로 wiring한다. 고아 코드는 두지 않는다.

## Tasks

- [x] 1. 파서 모듈 골격과 공통 객체 스키마 정의
  - [x] 1.1 디렉토리·스키마·상수·식별자 헬퍼 정의
    - `tool_guide_parser_src/` 디렉토리 생성, 패키지 초기화 및 `py -m pytest` 테스트 골격 구성
    - 공통 5필드 레코드(`id`, `object_type`, `canonical_text`, `metadata`, `evidence`)와 7개 metadata 필드(`tool_name`, `tool_version`, `command`, `option`, `section`, `doc_version`, `object_type`)를 표현하는 데이터 구조(dataclass/TypedDict) 정의
    - `object_type` 허용 집합 상수 `{command, option, flow_step, example, section}` 및 고정 문자열 `"미확인"` 상수 정의
    - 결정론적 `id` 생성 규칙 `toolguide#<tool>#<ver>#<type>#<name>` 및 `doc_id = sha1(tool_name + doc_version + filename)` 헬퍼 정의
    - 식별자 헬퍼는 `id`/`doc_id` 구성 입력값(`tool_name`, `doc_version`, `filename`)을 식별자 생성 직전에 결정론적으로 정규화(대소문자 통일=case-folding + 앞뒤 공백 제거=trimming)한 뒤 사용하여, 동일 논리 문서를 입력 대소문자·공백 변형과 무관하게 반복 수집해도 동일한 `id`/`doc_id`를 산출
    - _Requirements: 3.1, 3.5, 3.6, 6.5_

- [x] 2. 결정론적 구조 파서 `parse_structure` 구현
  - [x] 2.1 텍스트화 및 오프셋↔페이지/섹션 매핑 구현
    - PDF는 `pdftotext -layout`, Markdown은 원문 사용; 문자 오프셋과 페이지/섹션 매핑 테이블 구축
    - 빈/공백뿐 입력 및 미지원 형식 감지 경로 구현(부분 결과 미저장 보장의 전제)
    - _Requirements: 2.1, 1.3, 1.4, 2.8_

  - [x] 2.2 블록 스캔 및 객체 경계 검출 (순수 함수)
    - command/option/flow/example 라벨·구조 규칙 기반 경계 검출, `start/end` 오프셋·`object_type` 결정
    - 외부 상태·시각·난수 미사용(순수 함수), `start_offset` 오름차순 안정 정렬
    - 규칙 미매칭 잔여 구간을 `section` 객체로 포장하여 누락 방지
    - _Requirements: 2.1, 2.2, 2.5_

  - [x] 2.3 belongs_to 관계 결정 구현
    - option 블록이 command 텍스트 범위 내부면 `belongs_to=command_id`, 어느 command에도 안 속하면 독립 객체로 보존
    - _Requirements: 2.3, 2.4_

  - [x]* 2.4 파서 결정론 속성 테스트
    - **Property 1: 파서 결정론 (Determinism)** — `parse_structure` 2회 이상 호출 시 객체 개수·경계 오프셋·`object_type`·`belongs_to`가 모든 호출에서 동일
    - **Validates: Requirements 2.2, 2.7**
    - 식별자 입력 정규화 커버리지: 생성기가 동일 논리 문서의 대소문자·공백 변형(예: `VCS` vs ` vcs `)을 공급하여 정규화 후 `id`/`doc_id`가 동일함을 함께 확인 (R3.6 보강)
    - 태그: `Feature: eda-tool-guide-rag, Property 1`, `@settings(max_examples=100)` 이상, 합성 툴 가이드 생성기 사용

  - [x]* 2.5 텍스트 커버리지 속성 테스트
    - **Property 2: 텍스트 100% 커버리지 (Coverage Invariant)** — 추출 객체 `[start,end)` 합집합이 원문 비공백 문자 100% 커버
    - **Validates: Requirements 2.1, 2.5**
    - 태그: `Feature: eda-tool-guide-rag, Property 2`, 미파싱 잔여 구간 포함 생성기 사용

  - [x]* 2.6 belongs_to 관계 보존 속성 테스트
    - **Property 5: belongs_to 관계 보존 (Relation Preservation)** — command 범위 내 option은 belongs_to 보유, 범위 밖 option은 독립 보존(누락 없음)
    - **Validates: Requirements 2.3, 2.4**
    - 태그: `Feature: eda-tool-guide-rag, Property 5`, command 내부/고아 option 생성기 사용

- [x] 3. 객체 빌더 `build_objects` 및 메타데이터 채움 구현
  - [x] 3.1 메타데이터·evidence 채움 및 canonical_text 생성
    - 7개 metadata 필드 채움, 원문 미확인 값은 고정 문자열 `"미확인"`(추정/기본값 금지)
    - `evidence`에 `source_file`·`doc_version` 필수 + `page` 또는 `section` 중 ≥1 포함
    - 객체당 1개 비어있지 않은 `canonical_text` 생성(결정론적 템플릿 우선)
    - `object_type` 허용 집합 검증, 허용 외 type 객체는 생성하지 않음
    - _Requirements: 2.6, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 3.2 객체 레코드 정합성 속성 테스트
    - **Property 3: 객체 레코드 정합성 (Record Well-formedness)** — 5필드+7 metadata 문자열 존재, 미확인은 정확히 `"미확인"`, canonical_text 1개 비어있지 않음, evidence 규칙 충족
    - **Validates: Requirements 2.6, 3.1, 3.3, 3.4, 3.5**
    - 태그: `Feature: eda-tool-guide-rag, Property 3`

  - [x]* 3.3 object_type 허용 집합 속성 테스트
    - **Property 4: object_type 허용 집합 (Closed Type Set)** — 모든 객체 `object_type`은 허용 집합 중 하나, 허용 외 type 객체 미생성
    - **Validates: Requirements 3.2**
    - 태그: `Feature: eda-tool-guide-rag, Property 4`

  - [x]* 3.4 Vision 다이어그램 파서 구현 (선택, ENABLE_VISION_PARSING)
    - pymupdf(fitz)로 PDF 페이지 이미지 렌더링 구현, 텍스트 희소 페이지 감지(< 100자 임계값)
    - Bedrock Converse API(Claude) Vision 호출 래퍼 구현 — injectable summarize 콜백으로 build_objects에 주입
    - ENABLE_VISION_PARSING 환경 변수 제어 구현(기본 false, 비활성 시 기존 동작)
    - Vision 실패 시 폴백: 원문 텍스트 section 객체 유지, 파싱 계속
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x]* 3.5 Vision 폴백 안정성 속성 테스트
    - **Property 13: Vision 폴백 안정성 (Vision Fallback Safety)** — Vision 실패 또는 비활성화 시 폴백 경로가 항상 유효한 section 객체 생성, 파싱 미중단
    - **Validates: Requirements 7.4, 7.5**
    - 태그: `Feature: eda-tool-guide-rag, Property 13`

- [x] 4. 파서 핸들러·멱등성·오류 트랜잭션 구현
  - [x] 4.1 handler 및 적재 트랜잭션 구현
    - `handler(event) -> { doc_id, object_count, status }` 구현, 동일 키→동일 `doc_id` 매핑으로 기존 레코드 교체(멱등), 중복 생성 금지
    - 빈/미지원 입력 시 추출 중단·오류 반환·부분 결과 미저장(전체 commit 트랜잭션), 원본 불변 보존
    - 적재 중 실패 시 전체 롤백(부분 인덱싱 방지)
    - _Requirements: 1.4, 1.6, 2.8_

  - [x]* 4.2 재수집 멱등성 속성 테스트
    - **Property 6: 재수집 멱등성 (Ingestion Idempotence)** — 동일 prefix+파일명 2회 이상 처리 시 객체 `id` 집합·레코드 개수가 1회 결과와 동일
    - **Validates: Requirements 1.6**
    - 식별자 입력 정규화 커버리지: 생성기가 같은 논리 문서를 대소문자·공백 변형으로 반복 수집해도 정규화 결과 동일 `id`/`doc_id`로 멱등 교체됨을 확인 (R3.6 보강)
    - 태그: `Feature: eda-tool-guide-rag, Property 6`

  - [x]* 4.3 미지원·빈 입력 오류 처리 속성 테스트
    - **Property 7: 미지원·빈 입력 오류 처리 (Error Condition)** — 빈/공백·미지원 형식 입력은 추출 중단·오류 반환·부분 결과 미저장·원본 불변
    - **Validates: Requirements 1.4, 2.8**
    - 태그: `Feature: eda-tool-guide-rag, Property 7`

- [x] 5. 임베딩·인덱스 적재 연동 (재사용 + 분리)
  - [x] 5.1 Qdrant/DynamoDB 적재 클라이언트 연동
    - 각 객체 `canonical_text`를 Titan Embed v2로 임베딩(객체 1개=벡터 1개) 호출 래퍼
    - Qdrant collection `tool-guide-knowledge-base`에 upsert, payload에 7 metadata + `pipeline_id=tool-guide` 포함
    - DynamoDB claim-db에 `pipeline_id=tool-guide` 파티션으로 객체 레코드 upsert, S3 published(`.md` + `.metadata.json`) 작성
    - 신규 임베딩 모델/차원/테이블 도입 없음(기존 메커니즘 재사용)
    - _Requirements: 1.5, 3.5, 5.1_

  - [x]* 5.2 적재 페이로드 단위 테스트
    - 임베딩/Qdrant/DDB 클라이언트를 mock하여 payload에 7 metadata + `pipeline_id=tool-guide`가 포함되고 RTL collection을 건드리지 않음을 검증
    - _Requirements: 1.5, 5.1_

- [x] 6. Checkpoint - 파서·적재 경로 테스트 통과 확인
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Tool_Guide_MCP 결과 가공 로직 구현
  - [x] 7.1 입력 길이 검증 및 도구 진입점 구현
    - `tool_guide_search`(query ≤256자), `tool_guide_query`(query ≤8192자), MVP 자연어 질의(1~8192자) 길이 규칙 구현
    - 빈 질의·한도 초과는 거부 + 길이 위반 오류(`error:input_length`)
    - 임베딩 토큰 하드 리밋 가드 구현: 저비용 문자 길이 검사 통과 후, 토큰화 길이가 임베딩 모델 입력 토큰 윈도(Titan Embed v2, 8,192 토큰)를 초과하는 질의는 식별 가능한 토큰 한도 초과 오류(`error:token_limit`)로 거부하고 부분 결과를 반환하지 않음
    - _Requirements: 4.1, 4.2, 4.10, 6.4_

  - [x] 7.2 권한 검사 및 파이프라인 격리 구현
    - 호출 시 `pipeline=tool-guide` 접근 권한 검사, 권한 없으면 결과 0 + 권한 오류
    - 권한 보유 시 Tool Guide corpus 결과만 반환(RTL 혼입 금지), 반환 결과 `pipeline_id`는 모두 `tool-guide`
    - Tool_Guide_MCP 도구 이름이 RTL MCP 도구와 겹치지 않음(R5.2), 파이프라인 식별자 `tool-guide`가 다른 파이프라인과 중복되지 않는 단일·고유 값임(R5.3) 보장
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 7.3 필터·citation·cap·정렬·빈 결과 처리 구현
    - `tool_name`/`tool_version` 지정 시 메타 필터로 범위 한정, 무매칭 시 빈 결과 + "일치하는 객체 없음"
    - evidence(문서명·doc_version·page|section) 불완전 항목은 반환 전 제외
    - 관련도 내림차순 정렬 + 최대 20건 cap, 근거 0건이면 "현재 index에서 확인 불가"(생성 텍스트 없음)
    - _Requirements: 4.3, 4.4, 4.5, 4.6, 4.8, 4.9, 6.2, 6.3_

  - [x]* 7.4 결과 개수 상한·정렬 속성 테스트
    - **Property 8: 결과 개수 상한과 정렬 (Cap & Ordering)** — 반환 결과 ≤20건, 관련도 점수 단조 비증가 정렬
    - **Validates: Requirements 4.3, 6.2**
    - 태그: `Feature: eda-tool-guide-rag, Property 8`, 결과 수 0~50+ 생성기 사용

  - [x]* 7.5 인용 완전성 속성 테스트
    - **Property 9: 인용 완전성 (Citation Completeness)** — 반환 모든 항목은 완전한 출처 인용 포함, 불완전 인용 항목은 제외
    - **Validates: Requirements 4.4, 4.5**
    - 태그: `Feature: eda-tool-guide-rag, Property 9`, 일부 evidence 누락 생성기 사용

  - [x]* 7.6 필터 범위 한정 속성 테스트
    - **Property 10: 필터 범위 한정 (Filter Scoping)** — `tool_name`/`tool_version` 지정 질의의 모든 결과 메타데이터 값이 필터와 일치
    - **Validates: Requirements 4.8**
    - 태그: `Feature: eda-tool-guide-rag, Property 10`

  - [x]* 7.7 입력 길이 검증 속성 테스트
    - **Property 11: 입력 길이 검증 (Input Length Validation)** — 자연어 질의는 1~8,192자만 수용되고 그 외(빈 질의 또는 8,192자 초과)에는 길이 위반 오류로 거부; 심볼 검색 질의는 동일 규칙을 256자 한도로 적용
    - 추가로, 문자 길이 검사는 통과했으나 토큰화 결과가 임베딩 모델 입력 토큰 윈도(8,192 토큰)를 초과하는 경로는 토큰 한도 초과 오류로 거부되고 부분 결과를 반환하지 않음을 검증
    - **Validates: Requirements 4.1, 4.2, 4.10, 6.4**
    - 태그: `Feature: eda-tool-guide-rag, Property 11`

  - [x]* 7.8 파이프라인 권한 격리 속성 테스트
    - **Property 12: 파이프라인 권한 격리 (Access Isolation)** — 권한 없으면 결과 0 + 권한 오류, 권한 있으면 모든 결과 `pipeline_id=tool-guide`이고 RTL 결과 0건
    - **Validates: Requirements 5.4, 5.5, 5.6**
    - 태그: `Feature: eda-tool-guide-rag, Property 12`, 권한 상태 + corpus 혼합 생성기 사용

- [x] 8. 통합 및 wiring
  - [x] 8.1 파서 핸들러 ↔ 적재 ↔ MCP 결과 가공 연결
    - S3 event → `handler` → `parse_structure`/`build_objects` → 적재(5.1) 경로를 end-to-end로 연결
    - MCP 도구(7.1~7.3)가 Qdrant `tool-guide-knowledge-base` collection + DDB 파티션을 조회하도록 wiring, MVP는 `command`/`option` type만 활성
    - _Requirements: 6.1, 6.5_

  - [x]* 8.2 MVP·확장성 통합 테스트
    - 단일 문서 + command/option만으로 자연어 검색 처리(6.1, 6.2), 0건 정상 응답(6.3), 신규 type 추가 시 스키마/파이프라인 골격 불변(6.5) 회귀 검증
    - 분리 검증: 별도 MCP 서비스/포트(:3101) + 고유 `pipeline_id=tool-guide`(R5.3), RTL MCP와 비중첩 도구명(R5.2) 확인
    - _Requirements: 5.2, 5.3, 6.1, 6.2, 6.3, 6.5_

- [x] 9. Final checkpoint - 전체 테스트 통과 확인
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- `*`로 표시된 sub-task는 선택(테스트)이며 빠른 MVP를 위해 건너뛸 수 있다.
- 12개 Correctness Property는 각각 단일 Hypothesis 속성 테스트로 구현하고, 구현 코드 가까이에 배치하여 오류를 조기에 잡는다.
- 자연어 질의 길이 한도는 **8,192자로 통일**(심볼 검색은 256자)되며, 문자 길이 검사는 저비용 사전 가드일 뿐 구속 한도는 임베딩 모델(Titan Embed v2) 입력 토큰 윈도(8,192 토큰)다. 문자 검사 통과 후 토큰 윈도 초과 질의는 `error:token_limit`로 거부한다(R4.10, Task 7.1/7.7).
- `id`/`doc_id` 식별자는 입력값(`tool_name`, `doc_version`, `filename`)을 결정론적으로 정규화(대소문자 통일 + 앞뒤 공백 제거)한 뒤 생성하여, 입력 대소문자·공백 변형과 무관하게 동일 식별자를 산출한다(R3.6, Task 1.1; Property 1/6 테스트가 정규화 커버리지 포함).
- 인프라(전용 S3 버킷+전용 CRR, Qdrant collection 분리, DDB 파티션, 별도 포트 :3101 MCP 서비스 기동·SSH 터널 매핑, 10초 latency, 신규 모델/인덱스/테이블 미생성)는 PBT 대상이 아니며 통합/스모크 테스트 및 Terraform/OPA 검증으로 다룬다(design.md Testing Strategy "비-PBT 항목").
- 각 task는 추적성을 위해 특정 requirements 절을 참조한다.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4", "2.5", "2.6"] },
    { "id": 4, "tasks": ["3.1", "3.4"] },
    { "id": 5, "tasks": ["3.2", "3.3", "3.5", "4.1"] },
    { "id": 6, "tasks": ["4.2", "4.3", "5.1"] },
    { "id": 7, "tasks": ["5.2", "7.1"] },
    { "id": 8, "tasks": ["7.2", "7.3"] },
    { "id": 9, "tasks": ["7.4", "7.5", "7.6", "7.7", "7.8", "8.1"] },
    { "id": 10, "tasks": ["8.2"] }
  ]
}
```
