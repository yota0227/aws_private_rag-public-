# Requirements Document

> **Title:** MCP Tool-Layer Optimization
> **Created:** 2026-06-16
> **Updated:** 2026-06-16
> **Purpose:** 단일 BOS-AI RAG MCP 브리지(`mcp-bridge/server.js`)의 도구 계층 품질을 개선한다 — 도구 선택 명확성, 출력 품질(resource URI·index version·일관 에러), evidence-first, 신규 운영 도구, 비동기 job, 관측성, server.js/server.mjs drift 정리. corpus/도메인 분리와 무관한 도구 계층 작업만 다룬다.
> **Spec / Project:** `.kiro/specs/mcp-tool-optimization/`
> **Status:** Draft
> **Owner:** Infra/DevOps + RAG MCP

## Introduction

본 spec은 운영 중인 단일 Node.js MCP 브리지(`mcp-bridge/server.js`, Streamable HTTP `/mcp` + 레거시 SSE `/sse`, `lambda-document-processor-seoul-prod` 및 `lambda-rtl-parser-seoul-dev` 직접 invoke, 17개 도구, OAuth discovery 의도적 404)의 **도구 계층(tool-layer) 최적화**를 정의한다. 백엔드는 폐쇄망 AWS(OpenSearch/Qdrant 벡터, Neptune 그래프, Bedrock KB, DynamoDB claim DB)이다.

이 spec의 모든 요구사항은 **corpus(도메인) 분리와 독립적**이다. corpus 라우팅·2단계 ACL·cross-domain merge·MCP 서버 분리 작업은 별도의 보류(parked) spec `mcp-corpus-routing-acl`에 있으며, 본 spec에서 **중복 정의하지 않는다**. 그 작업이 보류된 이유는 사내 LiteLLM access group이 **MCP 서버 단위**로 강제되기 때문이며, 따라서 도메인별 접근 제어는 2번째 RAG(예: CPU/SoC)가 실제로 도입될 때 **MCP 서버를 분리**하여 처리한다(in-server corpus ACL이 아님).

### In Scope (정확히 다음 7개 영역)

1. **도구 계약 명확성** — `rag_query` / `search_rtl` / `search_archive` 등 도구 간 LLM 오선택을 줄이기 위한 명확하고 상호 배타적인 도구 설명과 zod 입력 스키마, "언제 어느 도구를 쓰는가" 가이드.
2. **출력 품질** — 결과에 resource identifier/URI 부착, 응답에 `index_version`과 resolved snapshot 포함, 일관된 에러 스키마(`invalid_uri`, `not_found`, `upstream_error` 등). 단, 기존의 사람이 읽는 `content[].text` 응답 형식은 **보존**(하위 호환).
3. **Evidence-first** — `get_evidence` 출력 정규화(`source_uri`/`source_type`/`support_level`/`confidence`/`span`), 신규 `rag_validate_answer` 도구(문장별 evidence coverage, unsupported 문장 목록), `generate_hdd_section` verified-only 모드(`allow_unverified_inference=false`일 때 미지원 텍스트를 "확실하지 않음"으로 표기), `publish_markdown` 가드(미지원 문장 또는 미해석 `latest` 포함 콘텐츠 거부).
4. **신규 운영 도구** — `rag_index_status`(index별 version/freshness/embedding model), `rag_read_resource`(resource URI로 원문/스팬 조회), `rag_task_status`(비동기 작업 상태 polling).
5. **비동기 job 프레임워크** — 장시간 작업(`regenerate_stale_hdd`, 모든 reindex)은 블로킹 대신 `job_id` + job 상태 URI 반환, `rag_task_status`로 polling, 상태 `queued`/`running`/`done`/`failed`.
6. **관측성** — 호출별 구조화 로깅(`request_id`, 도구명, latency), latency 메트릭(p50/p95/p99), 임시 `console.log` 대체. **사용자/팀 식별자 전파나 corpus allowed/denied 감사는 요구하지 않는다**(보류된 ACL 작업 의존). 식별자 전파 없이 가능한 관측성으로 한정한다.
7. **하우스키핑** — `server.js`/`server.mjs` drift를 단일 진실 원천으로 통합(`package.json`은 `server.js`를 가리킴; `server.mjs`는 QuickSight 도구 `quick_dashboard_list`/`quick_dashboard_data`를 포함한 stale 변형). QuickSight 도구를 유지(`server.js`로 이관)할지 제거할지 결정·문서화.

### Out of Scope (보류 — Multi-RAG 단계)

다음 항목은 본 spec에서 **명시적으로 제외**되며 `mcp-corpus-routing-acl` spec(보류)에서 다룬다:

- `corpus_id`/`corpus_ids` 표준화, corpus 레지스트리, corpus 라우팅
- 2단계/corpus/document ACL, deny-by-default 인가
- cross-domain merge, MCP 서버 분리
- LiteLLM 식별자/도구 단위(tool-grain) 권한 작업

**resource URI 스킴**(`rag://`, `rtl://`, `graph://`, `claim://`, `job://`, `index://`)은 **출력/식별자 규약**으로 본 spec에서 요구할 수 있으나(도구 계층이며 라우팅이 아님), corpus 기반 접근 제어를 함의해서는 안 된다.

### 하위 호환 원칙

기존 17개 도구 계약은 깨지지 않는다. 신규 필드/도구는 **가산적(additive)**이다. corpus 필드는 본 spec에서 도입하지 않는다.

## Glossary

- **MCP_Bridge**: 운영 중인 단일 Node.js 서버 `mcp-bridge/server.js`. Streamable HTTP `/mcp`와 레거시 SSE `/sse`를 노출하고, `ragApi` 헬퍼로 `lambda-document-processor-seoul-prod` 및 `lambda-rtl-parser-seoul-dev`를 직접 invoke한다. 현재 17개 도구를 등록한다.
- **Tool**: MCP_Bridge가 `mcp.tool(name, description, schema, handler)`로 등록한 호출 가능 단위. 기존 17개: `rag_query`, `rag_list_documents`, `rag_categories`, `rag_upload_status`, `rag_extract_status`, `rag_delete_document`, `search_rtl`, `search_archive`, `get_evidence`, `list_verified_claims`, `generate_hdd_section`, `publish_markdown`, `trace_signal_path`, `find_instantiation_tree`, `find_clock_crossings`, `graph_export`, `regenerate_stale_hdd`.
- **Resource_URI**: 결과/근거를 식별·재조회하기 위한 출력 규약 문자열. 스킴은 `rag://`, `rtl://`, `graph://`, `claim://`, `job://`, `index://`. 식별자 규약일 뿐 corpus 기반 접근 제어를 함의하지 않는다.
- **index_version**: 결과가 도출된 검색 인덱스의 버전 식별자(예: `idx_20260615_001`). 재현성과 디버깅을 위해 응답에 포함한다.
- **resolved_snapshot**: 요청이 `latest`(또는 미지정)인 경우, MCP_Bridge가 응답에 반환하는 구체적·해석된 데이터 스냅샷 버전. 응답의 resolved_snapshot은 절대 `latest`가 아니다.
- **Evidence**: 답변/문장을 뒷받침하는 근거 단위. 정규화 필드: `source_uri`(Resource_URI), `source_type`, `support_level`, `confidence`(0..1), `span`(line_start/line_end).
- **Job**: 동기 호출로 완료하기 어려운 장시간 작업의 비동기 실행 단위. `job_id`, `status`(`queued`/`running`/`done`/`failed`), job 상태 URI(`job://...`)를 가진다.
- **rag_validate_answer**: (신규 Tool) 주어진 답변/문서 텍스트를 문장 단위로 evidence coverage를 검사하고 미지원(unsupported) 문장 목록을 반환하는 도구.
- **rag_index_status**: (신규 Tool) 인덱스별 version/freshness/embedding model을 조회하는 운영 도구.
- **rag_read_resource**: (신규 Tool) Resource_URI로 원문 텍스트/스팬을 조회하는 도구.
- **rag_task_status**: (신규 Tool) Job 상태를 polling하는 도구.
- **Error_Schema**: 모든 도구가 오류 시 반환하는 일관된 구조. 표준 `error_code`(`invalid_uri`, `not_found`, `upstream_error` 등)와 사람이 읽는 메시지를 포함하며, 기존 `content[].text` 형식 안에서 표현된다.

## Requirements

### Requirement 1: 도구 계약 명확성 (Tool Contract Clarity)

**User Story:** As an MCP client LLM, I want clearly disjoint tool descriptions and input schemas, so that I select the correct tool among `rag_query` / `search_rtl` / `search_archive` and others without misrouting.

#### Acceptance Criteria

1. THE MCP_Bridge SHALL provide for each Tool a non-empty description that states the Tool's purpose, each input it expects, and at least one concrete example use case.
2. THE MCP_Bridge SHALL provide descriptions for `rag_query`, `search_rtl`, and `search_archive` that each name, by exact registered Tool name, which sibling Tool to use for inputs that do not belong to the current Tool.
3. THE MCP_Bridge SHALL define every Tool input parameter with a zod schema that specifies the parameter type and a human-readable description.
4. THE MCP_Bridge SHALL mark every Tool input parameter in its zod schema as explicitly required or optional.
5. WHERE two Tools accept overlapping query inputs, THE MCP_Bridge SHALL include in each of their descriptions an explicit "use this Tool when / use the other Tool when" disambiguation statement.
6. THE MCP_Bridge SHALL document, in the spec design artifact, Tool-selection guidance that maps each supported question type to exactly one recommended Tool.
7. THE MCP_Bridge SHALL preserve the existing names and input-parameter signatures of the 17 existing Tools, SHALL NOT rename or remove any existing Tool or parameter, and SHALL make any newly added parameter optional.
8. WHERE this spec introduces a new Tool, THE MCP_Bridge SHALL provide that Tool with the same description and zod-schema contract required of existing Tools.

### Requirement 2: 출력 품질 (Output Quality)

**User Story:** As an MCP client, I want results to carry a resource identifier, an index version, a resolved snapshot, and a consistent error format, so that I can re-fetch, reproduce, and handle errors uniformly.

#### Acceptance Criteria

1. WHEN a Tool returns a retrieval result that maps to an addressable resource, THE MCP_Bridge SHALL attach a non-empty Resource_URI to that result that stably and uniquely identifies the resource for subsequent re-fetching.
2. IF a Tool returns a retrieval result that does not map to an addressable resource, THEN THE MCP_Bridge SHALL omit the Resource_URI field rather than emit an empty, null, or placeholder value.
3. WHEN a Tool returns a retrieval result, THE MCP_Bridge SHALL include a non-empty index_version that identifies the index state which produced the result.
4. WHEN a request specifies `latest` or omits the snapshot, THE MCP_Bridge SHALL include the resolved_snapshot in the response.
5. WHEN a request specifies an explicit concrete snapshot, THE MCP_Bridge SHALL echo that same snapshot value as the resolved_snapshot in the response.
6. THE MCP_Bridge SHALL ensure that every resolved_snapshot value in responses is a concrete version identifier and is never the literal string `latest`.
7. IF a Tool encounters an error, THEN THE MCP_Bridge SHALL return an Error_Schema containing exactly one error_code drawn from the defined set {`invalid_uri`, `not_found`, `upstream_error`} and a non-empty human-readable message indicating the cause.
8. IF a Tool encounters an error that does not correspond to `invalid_uri` or `not_found`, THEN THE MCP_Bridge SHALL classify it as `upstream_error`.
9. IF a Tool encounters an error, THEN THE MCP_Bridge SHALL return only the Error_Schema and SHALL NOT attach partial Resource_URI, index_version, or resolved_snapshot fields for the failed result.
10. THE MCP_Bridge SHALL emit all responses, including the added Resource_URI, index_version, and resolved_snapshot fields and the Error_Schema, within the existing `content[].text` response format.
11. THE MCP_Bridge SHALL keep all new output fields additive so that responses for the existing 17 Tools remain parseable by current clients and existing field names and contracts remain unchanged.

### Requirement 3: Evidence-first

**User Story:** As a design engineer, I want evidence-grounded outputs and validation, so that generated HDD content is traceable and unsupported claims are flagged.

#### Acceptance Criteria

1. WHEN `get_evidence` returns evidence, THE MCP_Bridge SHALL provide each Evidence item with `source_uri` (non-empty Resource_URI), `source_type` (non-empty), `support_level` (non-empty), `confidence` (a number in the inclusive range 0..1), and `span` (line_start/line_end), within the `content[].text` response format.
2. WHEN `get_evidence` finds no evidence for the request, THE MCP_Bridge SHALL return an empty evidence list without returning an Error_Schema.
3. THE MCP_Bridge SHALL provide a `rag_validate_answer` Tool that accepts an answer text, segments it into sentences, and returns a per-sentence supported/unsupported label.
4. THE MCP_Bridge SHALL treat a sentence as unsupported when it has zero associated Evidence items.
5. WHEN `rag_validate_answer` detects unsupported sentences, THE MCP_Bridge SHALL return the list of unsupported sentences including each sentence's text and position.
6. IF `rag_validate_answer` receives empty or whitespace-only answer text, THEN THE MCP_Bridge SHALL return an Error_Schema.
7. WHERE `generate_hdd_section` is invoked with `allow_unverified_inference=false`, THE MCP_Bridge SHALL label any generated segment having zero supporting evidence with the marker "확실하지 않음" in the `content[].text` output.
8. IF `publish_markdown` receives content containing one or more unsupported sentences, THEN THE MCP_Bridge SHALL reject the publish request, return an Error_Schema, and persist no part of the content.
9. IF `publish_markdown` receives content containing an unresolved `latest` reference, THEN THE MCP_Bridge SHALL reject the publish request, return an Error_Schema, and persist no part of the content.

### Requirement 4: 신규 운영 도구 (New Operational Tools)

**User Story:** As an operator, I want tools to inspect index state, read a resource by URI, and poll job status, so that I can verify freshness, trace evidence, and track long operations.

#### Acceptance Criteria

1. THE MCP_Bridge SHALL provide a `rag_index_status` Tool that returns, per index, the index_version, an ISO 8601 UTC last-successful-update timestamp, and the embedding model identifier.
2. WHEN no indexes exist, THE MCP_Bridge SHALL have `rag_index_status` return an empty list without returning an Error_Schema.
3. WHEN `rag_read_resource` receives a well-formed Resource_URI that addresses an existing resource, THE MCP_Bridge SHALL return the original text or span addressed by that Resource_URI.
4. IF `rag_read_resource` receives a malformed Resource_URI, THEN THE MCP_Bridge SHALL return an Error_Schema with error_code `invalid_uri` and SHALL return no partial resource content.
5. IF `rag_read_resource` receives a well-formed Resource_URI that addresses a non-existent resource, THEN THE MCP_Bridge SHALL return an Error_Schema with error_code `not_found`.
6. WHEN `rag_task_status` receives a known job_id, THE MCP_Bridge SHALL return the Job status as exactly one of `queued`, `running`, `done`, or `failed`.
7. IF `rag_task_status` receives an unknown job_id, THEN THE MCP_Bridge SHALL return an Error_Schema with error_code `not_found`.
8. IF any of `rag_index_status`, `rag_read_resource`, or `rag_task_status` fails for a reason other than `invalid_uri` or `not_found`, THEN THE MCP_Bridge SHALL return an Error_Schema with error_code `upstream_error`.
9. THE MCP_Bridge SHALL emit all `rag_index_status`, `rag_read_resource`, and `rag_task_status` responses within the existing `content[].text` response format as additive, backward-compatible tools.

### Requirement 5: 비동기 Job 프레임워크 (Async Job Framework)

**User Story:** As an MCP client, I want long-running operations to return a job handle instead of blocking, so that the connection is not held open and I can poll for completion.

#### Acceptance Criteria

1. WHEN `regenerate_stale_hdd` is invoked, THE MCP_Bridge SHALL create a Job and return, within 2 seconds and inside the `content[].text` format, a job_id and a Job status URI instead of blocking until completion.
2. WHEN a reindex operation is invoked, THE MCP_Bridge SHALL create a Job and return, within 2 seconds and inside the `content[].text` format, a job_id and a Job status URI instead of blocking until completion.
3. WHEN the MCP_Bridge creates a Job, THE MCP_Bridge SHALL set the initial Job status to `queued`.
4. THE MCP_Bridge SHALL represent every Job status as exactly one of `queued`, `running`, `done`, or `failed`.
5. WHEN a Job status URI is returned, THE MCP_Bridge SHALL format it using the `job://` Resource_URI scheme and embed the associated job_id so that the Job is resolvable via `rag_task_status`.
6. WHEN a Job is in `queued` or `running` state and is polled via `rag_task_status`, THE MCP_Bridge SHALL return the current status without a final result.
7. WHEN a Job completes successfully, THE MCP_Bridge SHALL set its status to `done` and make the Job result retrievable via `rag_task_status`.
8. IF a Job fails, THEN THE MCP_Bridge SHALL set its status to `failed` and return an error indication via `rag_task_status`.

### Requirement 6: 관측성 (Observability)

**User Story:** As an operator, I want per-call structured logging and latency metrics, so that I can monitor and troubleshoot the MCP_Bridge without depending on deferred identity work.

#### Acceptance Criteria

1. WHEN a Tool invocation completes, whether successful or failed, THE MCP_Bridge SHALL emit exactly one structured log record to CloudWatch Logs.
2. WHEN the MCP_Bridge emits a structured log record for a Tool invocation, THE record SHALL contain a request_id, the Tool name, the call latency measured in milliseconds, the invocation outcome as one of {success, failure}, and a UTC timestamp.
3. IF an incoming Tool invocation does not already carry a request_id, THEN THE MCP_Bridge SHALL generate a request_id that is unique across all invocations within a single process lifetime and use it for that invocation's log record.
4. WHEN an incoming Tool invocation already carries a request_id, THE MCP_Bridge SHALL reuse that request_id in the log record without generating a new one.
5. IF a Tool invocation fails, THEN THE MCP_Bridge SHALL emit a structured log record with outcome set to failure and an error indication identifying the failure category, without preventing the request_id, Tool name, and latency fields from being recorded.
6. THE MCP_Bridge SHALL compute and report Tool-invocation latency metrics at the p50, p95, and p99 percentiles, expressed in milliseconds, over a rolling 5-minute window.
7. THE MCP_Bridge SHALL emit all per-call diagnostic output exclusively through the structured logging mechanism and SHALL contain no `console.log` statements in its invocation path.
8. THE MCP_Bridge SHALL restrict the fields in every structured log record to data available without user or team identity propagation.
9. THE MCP_Bridge SHALL exclude corpus allowed and corpus denied audit fields from all observability output, including structured log records and latency metrics.

### Requirement 7: 하우스키핑 (Housekeeping — Single Source of Truth)

**User Story:** As a maintainer, I want a single source of truth for the server entrypoint, so that disk source and the deployed artifact do not drift and stale variants do not cause confusion.

#### Acceptance Criteria

1. THE MCP_Bridge SHALL maintain exactly one server entrypoint file on disk that is referenced by the `start` script in `package.json`.
2. THE MCP_Bridge SHALL designate `server.js` as the active entrypoint, and the `start` script in `package.json` SHALL invoke `server.js`.
3. WHEN `npm start` is executed, THE MCP_Bridge SHALL launch from `server.js`.
4. THE MCP_Bridge SHALL resolve the `server.mjs` stale variant such that, after resolution, `server.mjs` no longer exists as an independent server entrypoint and `server.js` remains the only entrypoint, achieved either by removing `server.mjs` or by porting its unique tool definitions into `server.js` and then removing `server.mjs`.
5. THE MCP_Bridge SHALL record, in a project decision document, an explicit decision stating whether the QuickSight Tools `quick_dashboard_list` and `quick_dashboard_data` are retained (ported into `server.js`) or removed, including the rationale for the chosen option.
6. WHEN the entrypoint is consolidated, THE MCP_Bridge SHALL preserve every tool already registered in `server.js` with unchanged tool name and input signature, so that existing clients continue to function without modification.
7. WHERE the documented decision is to retain the QuickSight Tools, THE MCP_Bridge SHALL register `quick_dashboard_list` and `quick_dashboard_data` in `server.js` such that each tool is invocable through the active entrypoint.
8. WHERE the documented decision is to remove the QuickSight Tools, THE MCP_Bridge SHALL ensure that neither `quick_dashboard_list` nor `quick_dashboard_data` is registered in `server.js` and that neither is exposed by the active entrypoint.

### Requirement 8: Resource URI 규약 (Output Identifier Convention)

**User Story:** As an MCP client, I want a consistent resource URI scheme on outputs, so that results and evidence are addressable and re-fetchable without implying any corpus-based access control.

#### Acceptance Criteria

1. THE MCP_Bridge SHALL define a Resource_URI scheme as a closed set of exactly six scheme prefixes: `rag://`, `rtl://`, `graph://`, `claim://`, `job://`, and `index://`.
2. THE MCP_Bridge SHALL treat a Resource_URI as well-formed only when it has one of the six defined scheme prefixes followed by a non-empty, whitespace-free identifier component.
3. WHEN the MCP_Bridge is about to return a Resource_URI in a response, THE MCP_Bridge SHALL validate it as well-formed first.
4. WHEN the MCP_Bridge parses then rebuilds a well-formed Resource_URI, THE MCP_Bridge SHALL produce a Resource_URI with an identical scheme prefix and identical identifier component (round-trip property).
5. IF a Resource_URI uses an unknown or unsupported scheme prefix, THEN THE MCP_Bridge SHALL signal an error with error_code `invalid_uri` and SHALL NOT return the Resource_URI.
6. IF a Resource_URI has an empty or whitespace-only identifier component, THEN THE MCP_Bridge SHALL signal an error with error_code `invalid_uri` and SHALL NOT return the Resource_URI.
7. THE MCP_Bridge SHALL treat Resource_URI values as identifier and output conventions only and SHALL NOT use the scheme prefix or identifier to derive corpus-based access control.
8. WHEN Resource_URI values are added to a response, THE MCP_Bridge SHALL leave existing response fields unchanged so that current clients remain compatible.
