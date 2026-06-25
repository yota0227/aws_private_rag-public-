# Implementation Plan: MCP Corpus Routing & ACL

> **Created:** 2026-07-29
> **Updated:** 2026-07-29
> **Updated:** 2026-06-16
> **Purpose:** 승인된 design.md/requirements.md를 단일 Node.js MCP 브리지(`mcp-bridge/server.js`)에 점진적으로 구현하기 위한 코딩 작업 체크리스트 — 4계층(Tool/Routing/Policy/Evidence) + 비동기 Job + 관측을 기존 17개 도구 계약을 깨지 않고 추가한다.
> **Spec / Project:** `.kiro/specs/mcp-corpus-routing-acl/`
> **Status:** Deferred — Multi-RAG 단계 보류. 2번째 RAG 도입 시 MCP 서버 분리와 함께 구현.
> **Owner:** Infra/DevOps + RAG MCP

## Overview

구현은 점진적·하위 호환 원칙을 따른다. 먼저 환경 의존 가정(Open Design Questions)을 검증하는 spike로 후속 분기를 확정하고, 이어서 server.js와 독립된 라이브러리 모듈(`mcp-bridge/lib/*`)로 4계층 토대를 만든 뒤, 기존 도구를 한 번에 하나씩 새 파이프라인으로 재배선한다. 모든 단계에서 corpus 필드는 optional로 유지되고 응답은 기존 `content[].text` 형식을 보존하므로, 어떤 시점에 멈춰도 17개 도구 계약은 동작한다.

구현 언어는 **JavaScript (Node.js)** 이다 — 활성 진입점이 `mcp-bridge/server.js`(CommonJS, Express + `@modelcontextprotocol/sdk` + `zod`)이며, 설계의 Testing Strategy가 도구 계층 속성 검증 라이브러리로 **fast-check**를 지정한다. 인프라 PBT(Go/gopter)와 Lambda(Python)는 변경하지 않는다.

설계는 9개 correctness property를 정의한다(Property 1~9). 각 property는 별도의 optional(`*`) 속성 테스트 sub-task로 구현에 인접 배치된다.

## Tasks

- [ ] 1. Open Design Question 검증 spike (후속 설계 분기 확정)
  - [ ]* 1.1 LiteLLM MCP gateway 능력 검증 probe 작성
    - `scripts/spikes/litellm_mcp_probe.js`에 현 LiteLLM 배포의 MCP server/tool 노출 제어·tool-level 권한 전담 가능 범위를 확인하는 검증 스크립트를 작성하고 결과를 `mcp-bridge/lib/oq-findings.js` 상수에 기록한다
    - 미지원 기능 확인 시 해당 통제를 Policy_Layer로 이관한다는 결정을 findings에 명시
    - _Requirements: 11.1_
  - [ ]* 1.2 user/team/key metadata 전달 경로 probe 작성
    - `scripts/spikes/metadata_probe.js`로 LiteLLM이 MCP 서버로 전달하는 헤더/메타데이터 경로를 캡처하고, 전달 불가 시 Policy_Layer가 사용할 식별 주체 대안을 `mcp-bridge/lib/oq-findings.js`에 정의
    - _Requirements: 11.2_
  - [ ]* 1.3 OpenSearch/Qdrant corpus-level ACL/필터 지원 probe 작성
    - `scripts/spikes/index_acl_probe.js`로 corpus 단위 필터/ACL 지원 여부를 확인하고, 미지원 시 index 분리를 선행 조건으로 findings에 명시
    - _Requirements: 11.3_
  - [ ]* 1.4 Neptune cross-domain edge 표현 probe 작성
    - `scripts/spikes/neptune_xdomain_probe.js`로 NPU↔SoC cross-domain edge 표현 가능 여부를 확인하고, 미지원 시 애플리케이션 레벨 병합 대체 경로를 findings에 명시
    - _Requirements: 11.4_
  - [ ]* 1.5 `@modelcontextprotocol/sdk` Tasks/stateless 지원 probe 작성
    - `scripts/spikes/sdk_capability_probe.js`로 설치된 SDK 버전의 stateless core/Tasks 지원 범위를 확인하고 async job 구현 방식(SDK Tasks vs 자체 dispatcher) 선택을 findings에 기록
    - _Requirements: 11.6_

- [ ] 2. 토대 유틸리티 (URI / Registry / Inference / Envelope / Errors)
  - [ ] 2.1 Resource URI parser/validator/builder 구현
    - `mcp-bridge/lib/uri.js`에 `parse`/`validate`/`build`를 구현한다. `rag`, `rtl`, `graph`, `claim`, `job`, `index` 6개 scheme와 선택적 fragment(`section=8.2`, `L120-L180`) 지원
    - 형식 위반 시 `validate=false`, `parse`는 `invalid_uri` 오류 throw
    - JS 테스트 러너 설정(`mcp-bridge/package.json`에 `node:test` + `fast-check` devDependency 및 `test` 스크립트 추가)
    - _Requirements: 3.1, 3.2, 3.3_
  - [ ]* 2.2 URI round-trip 속성 테스트 작성
    - **Property 6: URI round-trip** — 임의의 유효 URI는 `parse`→`build` 후 의미적으로 동일하고, 잘못된 URI는 `validate=false`
    - `mcp-bridge/tests/uri.property.test.js` (fast-check)
    - **Validates: Requirements 3.1**
  - [ ] 2.3 Corpus Registry + corpus_id 스키마 + snapshot 해석 구현
    - `mcp-bridge/lib/registry.js`에 `list`/`get`/`resolveSnapshot`과 `CorpusMetadata`(domain, data_type, security_level, index_version, graph_version?, embedding_model, last_indexed_at, backend 매핑)를 코드 상수로 구현
    - `resolveSnapshot("latest")`는 항상 구체 버전 반환, SoC/NPU 보안 등급 차이를 `security_level`로 반영
    - _Requirements: 1.4, 1.5, 4.2, 11.5_
  - [ ] 2.4 Default corpus inference 구현
    - `mcp-bridge/lib/inference.js`에 `inferDefaultCorpus(args)` 구현 — `corpus_ids`/`corpus_id` 우선, 없으면 `pipeline_id`(registry backend 역참조)→`topic`/`source`/`team`/`category`→도구별 보수적 기본값 순으로 추론하고 추론 시 warning 추가
    - _Requirements: 1.1, 1.2, 1.3_
  - [ ]* 2.5 backward-compatibility inference 속성 테스트 작성
    - **Property 5: Backward compatibility** — corpus 필드 없는 legacy 호출은 항상 유효 `corpus_ids`로 추론되며 오류 없이 처리(실패 시 보수적 기본값 + warning)
    - `mcp-bridge/tests/inference.property.test.js`
    - **Validates: Requirements 1.1**
  - [ ] 2.6 Common Input/Output envelope + request_id + 오류 스키마 구현
    - `mcp-bridge/lib/envelope.js`에 Common_Input 수용, `request_id` 자동 생성, Common_Output(`request_id`, `resolved_scope`, `resolved_index`, `results`, `denied_corpus_ids`, `warnings`, `execution_time_ms`) 빌더와 텍스트 직렬화 헬퍼(기존 형식 보존) 구현
    - `mcp-bridge/lib/errors.js`에 `corpus_not_found`(유효 목록 포함), `action_not_permitted`, `invalid_uri` 오류 스키마 구현
    - _Requirements: 8.2, 8.3, 8.4, 1.5_
  - [ ]* 2.7 토대 모듈 단위 테스트 작성
    - registry(`resolveSnapshot`/미등록 corpus undefined), envelope(request_id 생성/직렬화), errors 스키마 테스트
    - `mcp-bridge/tests/foundation.unit.test.js`
    - _Requirements: 1.4, 1.5, 8.3, 8.4_

- [ ] 3. Checkpoint — 토대 검증
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Routing Layer (dispatch / merge / snapshot 해석 / 첫 도구 배선)
  - [ ] 4.1 Backend adapter 추상화 구현
    - `mcp-bridge/lib/adapters.js`에 기존 `ragApi`(Lambda direct invoke + HTTP fallback)를 감싸는 `BackendAdapter`(corpus별 `search`/`readResource`)를 구현하고 registry의 backend 매핑으로 함수/필터 선택
    - _Requirements: 1.6_
  - [ ] 4.3 Snapshot & index 해석기 구현
    - `mcp-bridge/lib/scope.js`에 `resolveScope(corpus_ids, rtl_snapshot)`를 구현 — `resolved_scope.rtl_snapshot`은 절대 `"latest"`가 아니며, `resolved_index[]`는 모든 corpus의 `index_version`(및 `graph_version`)을 포함, HDD↔RTL 불일치는 `warnings` stale 표시
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [ ]* 4.4 snapshot resolution 속성 테스트 작성
    - **Property 4: Snapshot resolution** — 모든 응답의 `resolved_scope.rtl_snapshot`은 구체 버전, `resolved_index[]`는 요청된 모든 allowed corpus 포함
    - `mcp-bridge/tests/scope.property.test.js`
    - **Validates: Requirements 4.1**
  - [ ] 4.2 Corpus dispatch + cross-domain merge 구현
    - `mcp-bridge/lib/routing.js`에 `dispatch(corpusIds, op, input)`를 구현 — 허용 corpus별 adapter 호출 후 결과 병합 시 각 결과의 출처 corpus 구분 유지
    - _Requirements: 1.6_
  - [ ] 4.5 첫 도구(`search_rtl`)를 envelope+routing 파이프라인으로 재배선
    - `mcp-bridge/server.js`의 `search_rtl` 핸들러를 envelope/inference/routing/scope 경유로 교체하되 기존 `content[].text` 출력과 corpus optional 동작을 보존하고 구조화 요약을 텍스트에 포함
    - _Requirements: 1.1, 8.1, 10.1, 10.2, 10.3_
  - [ ]* 4.6 Statelessness 속성 테스트 작성
    - **Property 1: Statelessness** — 임의 호출 순서에서 동일 입력은 세션 상태와 무관하게 동일 corpus 범위로 라우팅, selected corpus 세션 미저장
    - `mcp-bridge/tests/statelessness.property.test.js`
    - **Validates: Requirements 8.1**

- [ ] 5. Policy (ACL) Layer (deny-by-default / no-leak / admin 보호 / resource 재검증)
  - [ ] 5.1 정책 저장소 + `authorize` deny-by-default 구현
    - `mcp-bridge/lib/policy.js`에 `PolicyRule`(team→corpus+action) 저장과 `authorize(req)` 구현 — 미정의 (team,corpus)/(team,action) 거부, `allowed_corpus_ids`/`denied_corpus_ids`(사유) 분리, SoC/NPU security_level 반영
    - _Requirements: 2.1, 2.4, 11.5_
  - [ ]* 5.2 deny-by-default 속성 테스트 작성
    - **Property 2: Deny-by-default** — 정책 미명시 (team,corpus)/(team,action)은 항상 거부되고 결과에 미노출
    - `mcp-bridge/tests/policy-deny.property.test.js`
    - **Validates: Requirements 2.1**
  - [ ] 5.5 Admin-tool 보호 + log-only→enforce 모드 구현
    - `mcp-bridge/lib/policy.js`에 admin action(`publish`/`delete`/`reindex`/`regenerate`) 권한 검사와 `action_not_permitted` 차단, log-only(audit) 모드(비admin action은 기록만)와 모드 무관 admin 즉시 enforce, enforce 전환 기준을 구현
    - _Requirements: 2.3, 2.6, 11.8_
  - [ ]* 5.6 Admin protection 속성 테스트 작성
    - **Property 7: Admin protection** — admin action 도구는 admin 권한 없는 컨텍스트에서 항상 거부
    - `mcp-bridge/tests/admin-protection.property.test.js`
    - **Validates: Requirements 2.3**
  - [ ] 5.7 Resource 직접 접근 권한 재검증 함수 구현
    - `mcp-bridge/lib/policy.js`에 `authorizeResource(user_context, resource_uri)`를 추가 — URI가 가리키는 corpus/document 권한을 재검증한 후에만 통과(`rag_read_resource`에서 사용)
    - _Requirements: 2.5, 6.2_
  - [ ] 5.3 denied corpus를 backend dispatch 이전 단계에서 제외
    - `mcp-bridge/lib/routing.js`에 authorize 결과를 적용해 거부된 corpus를 dispatch 입력에서 제거하고 `denied_corpus_ids`를 Common_Output에 채운다(사후 필터 금지)
    - _Requirements: 2.2, 2.4_
  - [ ]* 5.4 No-leak 속성 테스트 작성
    - **Property 3: No-leak** — denied corpus의 결과/evidence/resource_uri가 출력 envelope 어디에도 미포함
    - `mcp-bridge/tests/no-leak.property.test.js`
    - **Validates: Requirements 2.2**

- [ ] 6. Checkpoint — 라우팅·정책 검증
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Evidence Layer (resource_uri 부착 / evidence 정규화)
  - [ ] 7.1 결과 resource_uri 부착 구현
    - `mcp-bridge/lib/evidence.js`에 `attachResourceUri(result, corpus)`를 구현 — 검색/조회 결과마다 corpus 기준 `resource_uri`를 부착(uri 빌더 사용)
    - _Requirements: 3.4_
  - [ ] 7.2 `get_evidence` 정규화 구현
    - `mcp-bridge/lib/evidence.js`에 `normalizeEvidence(raw, corpus)`를 구현 — `source_uri`, `source_type`, `support_level`, `confidence`, 선택 `span`/`quote`를 포함한 정규화 구조 반환
    - _Requirements: 5.2_
  - [ ]* 7.3 Evidence Layer 단위 테스트 작성
    - resource_uri 부착·evidence 정규화 매핑·verbatim 인용 길이 제한 테스트
    - `mcp-bridge/tests/evidence.unit.test.js`
    - _Requirements: 3.4, 5.2_

- [ ] 8. 신규 운영 도구 (handler 모듈 + 서버 등록)
  - [ ] 8.1 `rag_index_status` 핸들러 구현
    - `mcp-bridge/lib/tools/index_status.js`에 corpus별 `index_version`, `last_indexed_at`, `embedding_model`, freshness 반환 로직 구현
    - _Requirements: 6.1_
  - [ ] 8.3 `rag_validate_answer` 핸들러 구현
    - `mcp-bridge/lib/tools/validate_answer.js`에 문장별 evidence coverage 평가와 unsupported 문장 목록 반환 로직 구현
    - _Requirements: 5.3, 6.3_
  - [ ] 8.4 `generate_hdd_section` verified-only 모드 구현
    - `mcp-bridge/lib/tools/hdd_verified.js`에 `allow_unverified_inference=false`일 때 모든 문장이 evidence(`source_uri`)로 뒷받침되거나 "확실하지 않음/추가 확인 필요"로 표시되도록 하는 로직 구현
    - _Requirements: 5.1_
  - [ ]* 8.5 Evidence integrity 속성 테스트 작성
    - **Property 8: Evidence integrity** — verified-only 모드 생성 HDD의 모든 문장은 evidence로 뒷받침되거나 "확실하지 않음"으로 표시
    - `mcp-bridge/tests/evidence-integrity.property.test.js`
    - **Validates: Requirements 5.1**
  - [ ] 8.6 `publish_markdown` guard 구현
    - `mcp-bridge/lib/tools/publish_guard.js`에 `source_uri` 없는 문장 또는 미해석 `latest` 포함 콘텐츠의 publish 거부 로직 구현
    - _Requirements: 5.4_
  - [ ] 8.2 `rag_read_resource` 핸들러 구현
    - `mcp-bridge/lib/tools/read_resource.js`에 URI parse → `authorizeResource` 재검증 → 원문/스팬 반환 로직 구현
    - _Requirements: 6.2, 2.5_
  - [ ] 8.7 신규 read 도구를 server.js에 등록
    - `mcp-bridge/server.js`에 `rag_index_status`, `rag_read_resource`, `rag_validate_answer`를 zod 스키마와 함께 등록하고, `generate_hdd_section`/`publish_markdown`을 verified-only·guard 핸들러로 재배선(텍스트 응답 형식 보존)
    - _Requirements: 5.1, 5.4, 6.1, 6.2, 6.3_

- [ ] 9. 비동기 Job/Task 프레임워크
  - [ ] 9.1 Job 상태 저장소 구현 (OQ-7 결정 반영)
    - `mcp-bridge/lib/jobs/store.js`에 폐쇄망 제약 하 job 상태 영속화(DynamoDB 또는 기존 claim DB 별도 테이블)를 1.5/OQ-7 findings에 따라 구현
    - _Requirements: 11.7_
  - [ ] 9.2 Job_Dispatcher (enqueue/status + job:// URI) 구현
    - `mcp-bridge/lib/jobs/dispatcher.js`에 `enqueue`(→`job_id`, status `queued`, `job://` status_uri)와 `status`(`queued`/`running`/`done`/`failed`, 완료 시 `result_uri`, 실패 시 `error`) 구현
    - _Requirements: 7.1, 7.2, 7.3, 7.5_
  - [ ] 9.3 `rag_reindex_document`/`rag_reindex_corpus` 핸들러 구현
    - `mcp-bridge/lib/tools/reindex.js`에 admin 권한 검사 후 job enqueue → `job_id` + `job://` 반환 로직 구현
    - _Requirements: 6.4, 7.1_
  - [ ] 9.4 `rag_task_status` 핸들러 구현
    - `mcp-bridge/lib/tools/task_status.js`에 `job_id`로 상태 조회 및 완료 시 결과 `resource_uri` 반환 구현
    - _Requirements: 6.5, 7.2, 7.3_
  - [ ] 9.5 async 도구 server.js 등록 + 장기작업 전환 배선
    - `mcp-bridge/server.js`에 `rag_reindex_document`/`rag_reindex_corpus`/`rag_task_status`를 등록하고, `regenerate_stale_hdd`를 async job화하며 동기 호출이 장기작업으로 판단되면 `job_id`+`job://`로 전환
    - _Requirements: 7.4_

- [ ] 10. Checkpoint — evidence·신규 도구·async 검증
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. 관측 & 감사 (Observability & Audit)
  - [ ] 11.1 Audit_Record 스키마 + 구조화 JSON 로깅 구현
    - `mcp-bridge/lib/audit.js`에 호출당 1건 Audit_Record(`request_id`, `tool`, `action`, `corpus_requested`/`allowed`/`denied`, `index_version`, mutation, `denied_resources`) 생성과 CloudWatch Logs용 구조화 JSON 송출(기존 `console.log` 대체) 구현
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - [ ]* 11.2 Audit completeness 속성 테스트 작성
    - **Property 9: Audit completeness** — 모든 도구 호출은 corpus requested/allowed/denied + request_id audit 생성, 모든 mutation은 mutation 필드 기록
    - `mcp-bridge/tests/audit.property.test.js`
    - **Validates: Requirements 9.1**
  - [ ] 11.3 latency/evidence 지표 산출 구현
    - `mcp-bridge/lib/metrics.js`에 latency(p50/p95/p99) 및 evidence coverage 지표를 audit 레코드에서 산출 가능하게 emit
    - _Requirements: 9.4_

- [ ] 12. 하위 호환 마무리 & drift 정리
  - [ ] 12.1 나머지 기존 도구를 통합 파이프라인으로 재배선
    - `mcp-bridge/server.js`의 잔여 기존 도구(rag_query, rag_list_documents, rag_categories, rag_upload_status, rag_extract_status, rag_delete_document, search_archive, get_evidence, list_verified_claims, trace_signal_path, find_instantiation_tree, find_clock_crossings, graph_export)를 envelope/inference/routing/policy/evidence/audit 파이프라인 경유로 재배선하되 corpus 필드 optional·텍스트 응답 형식 보존·구조화 요약 포함
    - _Requirements: 10.1, 10.2, 10.3_
  - [ ]* 12.2 하위 호환 통합 테스트 작성
    - corpus 필드 없는 17개 도구 legacy 호출이 오류 없이 동작하고 텍스트 형식이 유지되는지 검증
    - `mcp-bridge/tests/backward-compat.integration.test.js`
    - _Requirements: 10.1, 10.2, 10.3_
  - [ ] 12.3 `server.mjs` drift 일원화 + QuickSight 정리
    - `package.json`이 가리키는 `server.js`를 single source of truth로 확정하고 stale `server.mjs`를 제거하거나 통합하며, QuickSight 도구(`quick_dashboard_list`/`quick_dashboard_data`)를 제거
    - _Requirements: 10.4, 10.5_

- [ ] 13. 최종 Checkpoint — 전체 테스트 통과 확인
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- `*` 표시 sub-task는 optional(속성/단위/통합 테스트·spike)로, 빠른 MVP에서는 건너뛸 수 있으나 dependency graph에는 포함된다.
- 각 task는 추적성을 위해 특정 요구사항 절을 참조한다. 속성 테스트 task는 design.md의 Property 번호와 검증 대상 requirement를 함께 명시한다.
- **테스트 실행 (MCP 브리지, JS):** `cd mcp-bridge && npm install && npm test` — 속성 테스트는 fast-check, 러너는 `node:test`(task 2.1에서 설정). 인프라 PBT(Go/gopter, `tests/properties/`)와 Lambda(`py -m pytest`)는 본 spec에서 변경하지 않는다.
- **하위 호환 불변식:** corpus 필드(`corpus_id`/`corpus_ids`)는 모든 단계에서 optional로 유지되며, 누락 시 inference로 대체되고 응답은 기존 `content[].text` 형식을 보존한다. 따라서 어느 task 경계에서 멈춰도 17개 도구 계약은 깨지지 않는다.
- **보안 불변식:** denied corpus는 backend dispatch 이전(task 5.3)에 제거된다 — 검색 후 사후 필터 금지(No-leak, Property 3).
- **인프라 변경 시:** job 상태 저장소(DynamoDB/claim DB 테이블)나 CloudWatch 로그 그룹이 Terraform 관리 대상으로 신규/변경되면 해당 환경 디렉토리에서 `terraform validate` + `tflint`를 수행한다(저장소 인프라 확정은 후속 Terraform spec 범위).
- spike(task 1)의 findings(`mcp-bridge/lib/oq-findings.js`)는 Policy_Layer 식별 주체(OQ-2), index 분리 선행 여부(OQ-3), cross-domain 병합 대체(OQ-4), async 구현 방식(OQ-6), job 저장소(OQ-7) 분기를 확정한다 — 후속 구현 task가 이 결과를 전제로 한다.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"] },
    { "id": 1, "tasks": ["2.1", "2.3", "2.6"] },
    { "id": 2, "tasks": ["2.4", "2.2", "2.7", "4.1", "4.3", "5.1", "7.1", "11.1"] },
    { "id": 3, "tasks": ["2.5", "4.2", "4.4", "5.2", "5.5", "7.2", "8.1", "8.3", "8.4", "8.6", "9.1", "11.3", "11.2"] },
    { "id": 4, "tasks": ["4.5", "4.6", "5.3", "5.6", "5.7", "7.3", "8.5", "9.2"] },
    { "id": 5, "tasks": ["5.4", "8.2", "9.3", "9.4"] },
    { "id": 6, "tasks": ["8.7"] },
    { "id": 7, "tasks": ["9.5"] },
    { "id": 8, "tasks": ["12.1"] },
    { "id": 9, "tasks": ["12.2", "12.3"] }
  ]
}
```
