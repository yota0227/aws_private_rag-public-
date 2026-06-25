# Requirements Document

> **Title:** MCP Corpus Routing & ACL
> **Created:** 2026-07-29
> **Updated:** 2026-06-16
> **Purpose:** 승인된 design.md에서 도출한 EARS 요구사항 — corpus 라우팅·2단계 인가·resource URI·재현성·evidence-first·비동기 작업·관측·하위 호환을 검증 가능한 수용 기준으로 정의.
> **Spec / Project:** `.kiro/specs/mcp-corpus-routing-acl/`
> **Status:** Deferred — Multi-RAG 단계 보류. 2번째 RAG 도입 시 MCP 서버 분리와 함께 구현.
> **Owner:** Infra/DevOps + RAG MCP

## Introduction

본 문서는 단일 BOS-AI RAG MCP 브리지를 다중 RTL 도메인(NPU + SoC)으로 확장하기 위한 요구사항을 정의한다. 요구사항은 승인된 설계 문서(`design.md`)에서 도출되었으며, 설계의 핵심 결정(단일 MCP 서버 유지 + 백엔드 corpus 분리, 4계층 내부 구조, deny-by-default 2단계 인가, resource URI 체계, 재현성, evidence-first 워크플로, 비동기 작업, 공통 입출력 envelope, 관측/감사, 점진적 하위 호환 마이그레이션)과 일관성을 유지한다.

시스템은 폐쇄망 AWS 아키텍처(Seoul frontend + Virginia backend, Lambda direct invoke, OpenSearch Serverless/Qdrant 벡터, Neptune 그래프, Bedrock KB, DynamoDB claim DB, 인터넷 게이트웨이 없음)에 맞춘다. 모든 요구사항은 기존 17개 도구 계약을 깨지 않는 하위 호환을 전제로 한다.

설계가 "확실하지 않음"으로 표기했거나 가정에 의존하는 항목(Open Design Questions OQ-1~OQ-9)은 실환경 능력을 단정하지 않고 **발견·검증·폴백(discovery/validation/fallback)** 형태의 요구사항으로 표현한다.

## Glossary

- **MCP_Server**: 단일 `bos-ai-rag-mcp` 브리지 서버. Tool/Routing/Policy/Evidence/Observability 계층을 포함한다.
- **Tool_Layer**: MCP 도구 등록, 공통 input/output envelope 적용, 인자 검증을 담당하는 계층.
- **Routing_Layer**: `corpus_ids`를 백엔드 adapter로 dispatch하고, default corpus 추론, cross-domain 병합, snapshot/index 해석을 담당하는 계층.
- **Policy_Layer**: corpus/document/resource/action 인가를 deny-by-default로 수행하는 계층.
- **Evidence_Layer**: 응답 정규화(resource_uri, evidence span, support_level, index_version 부착)를 담당하는 계층.
- **Observability_Component**: 구조화 로그와 감사(audit) 기록을 생성하는 계층.
- **Corpus**: 도메인/데이터 타입 단위의 RAG 데이터 집합. 백엔드 adapter 선택 키이자 ACL 단위. `corpus_id`로 식별한다.
- **Corpus_Registry**: corpus 메타데이터(domain, data_type, security_level, index_version, backend 매핑)를 보관·조회하고 `latest` snapshot을 해석하는 구성요소.
- **LiteLLM_Gateway**: MCP 서버 앞단의 외부 게이트웨이. virtual key/team 정책, budget, tool 노출, user/team metadata 전달을 담당한다(외부 의존).
- **Default_Corpus_Inference**: corpus 필드 누락 시 `pipeline_id`/`topic`/`source`/`team`/`category`로부터 corpus를 추론하는 로직.
- **Resource_URI**: `rag://`, `rtl://`, `graph://`, `claim://`, `job://`, `index://` 스킴을 가진 자원 식별자.
- **URI_Parser**: Resource_URI를 parse/validate/build하는 구성요소.
- **Admin_Action**: `publish`/`delete`/`reindex`/`regenerate` 등 파괴적·생성적 동작.
- **Admin_Tool**: `rag_delete_document`, `publish_markdown`, `regenerate_stale_hdd`, `rag_reindex_document`, `rag_reindex_corpus` 등 Admin_Action을 수행하는 도구.
- **Job_Dispatcher**: 장기 실행 작업을 enqueue하고 상태를 조회하는 비동기 작업 구성요소.
- **Common_Input**: 모든 도구가 받는 공통 입력 구조(corpus 지정, request_id, user_context, project, rtl_snapshot, options).
- **Common_Output**: 모든 도구가 반환하는 공통 출력 구조(request_id, resolved_scope, resolved_index, results, denied_corpus_ids, evidence, warnings, execution_time_ms).
- **Audit_Record**: 도구 호출당 1건 생성되는 구조화 감사 레코드.
- **rtl_snapshot**: RTL 스냅샷 식별자. `"latest"` 입력 허용, 응답에는 해석된 구체 버전을 반환한다.
- **index_version**: corpus의 인덱스 버전 식별자(예: `idx_soc_20260615_001`).

## Requirements

### Requirement 1: Corpus 모델 & 라우팅

**User Story:** As a RAG 플랫폼 운영자, I want corpus 단위로 도메인을 표준화하고 라우팅하기를, so that NPU와 SoC를 포함한 다중 도메인 데이터를 구분·격리하면서 기존 호출을 깨지 않고 처리할 수 있다.

#### Acceptance Criteria

1. WHEN 도구 호출에 `corpus_id` 또는 `corpus_ids`가 없는 legacy 호출이 수신되면, THE Routing_Layer SHALL `pipeline_id`/`topic`/`source`/`team`/`category`로부터 유효한 `corpus_ids`를 추론하여 오류 없이 처리한다.
2. IF Default_Corpus_Inference가 후보 corpus를 결정하지 못하면, THEN THE Routing_Layer SHALL 도구별 보수적 기본 corpus를 선택하고 `warnings`에 추론 사실을 기록한다.
3. WHEN 도구 호출에 `corpus_id` 또는 `corpus_ids`가 명시되면, THE Routing_Layer SHALL 명시된 corpus를 추론보다 우선하여 사용한다.
4. THE Corpus_Registry SHALL 각 corpus에 대해 `domain`, `data_type`, `security_level`, `index_version`, `embedding_model`, `last_indexed_at`, 백엔드 매핑(`backend.target`, `pipeline_id`, `topic_filter`, `source_filter`)을 제공한다.
5. IF 호출이 등록되지 않은 `corpus_id`를 지정하면, THEN THE MCP_Server SHALL `corpus_not_found` 오류와 유효 corpus 목록을 반환한다.
6. WHEN 호출이 복수 corpus(`corpus_ids`)를 지정하면, THE Routing_Layer SHALL 허용된 corpus별로 백엔드를 dispatch하고 결과를 병합하면서 각 결과의 출처 corpus 구분을 유지한다.

### Requirement 2: 2단계 인가 (Two-Tier Authorization)

**User Story:** As a 보안 담당자, I want LiteLLM tool-level 통제와 MCP 내부 corpus/document/resource ACL을 deny-by-default로 적용하기를, so that 현재 MCP 계층 무인증 보안 공백을 닫고 파괴적 admin 도구를 보호할 수 있다.

#### Acceptance Criteria

1. WHEN 도구 호출 컨텍스트(user/team/key)와 요청 corpus·action이 Policy_Layer 정책에 명시적으로 허용되지 않으면, THE Policy_Layer SHALL 해당 corpus 또는 action을 거부한다(deny-by-default).
2. WHILE 일부 요청 corpus가 거부된 상태에서, THE Routing_Layer SHALL 거부된 corpus를 백엔드 dispatch 입력 단계에서 제외하여 거부된 corpus의 결과·evidence·resource_uri가 응답 어디에도 포함되지 않도록 한다.
3. IF Admin_Action을 수행하는 Admin_Tool(`rag_delete_document`, `publish_markdown`, `regenerate_stale_hdd`, `rag_reindex_document`, `rag_reindex_corpus`)이 admin 권한 없는 컨텍스트에서 호출되면, THEN THE Policy_Layer SHALL `action_not_permitted` 오류를 반환하고 호출을 차단한다.
4. WHEN corpus가 정책상 거부되면, THE MCP_Server SHALL 응답의 `denied_corpus_ids`에 해당 corpus와 거부 사유를 포함한다.
5. WHEN `rag_read_resource`로 Resource_URI에 직접 접근하면, THE Policy_Layer SHALL 해당 URI가 가리키는 corpus/document 권한을 재검증한 후에만 내용을 반환한다.
6. WHERE Policy_Layer가 log-only(audit) 모드로 구성된 경우, THE Policy_Layer SHALL 비admin action을 거부하지 않고 기록만 하되, Admin_Tool에 대해서는 모드와 무관하게 즉시 거부를 적용한다.

### Requirement 3: Resource URI 체계

**User Story:** As an MCP 클라이언트 개발자, I want 일관된 resource URI 체계와 검증 가능한 parser를, so that 검색 결과의 출처를 안정적으로 식별하고 자원에 직접 접근할 수 있다.

#### Acceptance Criteria

1. WHEN 유효한 Resource_URI가 `parse` 후 `build`로 재구성되면, THE URI_Parser SHALL 의미적으로 동일한 URI를 산출한다(round-trip).
2. IF 형식을 위반한 URI 문자열이 입력되면, THEN THE URI_Parser SHALL `validate`에서 false를 반환하고 `parse`에서 `invalid_uri` 오류를 발생시킨다.
3. THE URI_Parser SHALL `rag`, `rtl`, `graph`, `claim`, `job`, `index` 6개 스킴과 선택적 fragment(예: `section=8.2`, `L120-L180`)를 지원한다.
4. WHEN 검색 또는 조회 결과가 반환되면, THE Evidence_Layer SHALL 각 결과에 해당 corpus 기준의 `resource_uri`를 부착한다.

### Requirement 4: 재현성 (Reproducibility)

**User Story:** As an RTL 분석 엔지니어, I want 모든 응답에 해석된 snapshot과 index version이 표기되기를, so that 동일 질의를 동일 데이터 버전으로 재현하고 stale 데이터를 식별할 수 있다.

#### Acceptance Criteria

1. WHEN 도구 호출이 완료되면, THE Routing_Layer SHALL 응답의 `resolved_scope.rtl_snapshot`을 `"latest"`가 아닌 구체 버전 값으로 반환한다.
2. WHEN `rtl_snapshot`이 `"latest"` 또는 누락이면, THE Corpus_Registry SHALL 해당 corpus의 구체 snapshot 버전으로 해석한다.
3. THE Evidence_Layer SHALL 응답의 `resolved_index[]`에 요청된 모든 허용 corpus의 `index_version`(및 존재 시 `graph_version`)을 포함한다.
4. IF HDD와 RTL의 snapshot이 불일치하면, THEN THE MCP_Server SHALL 결과를 반환하되 `warnings`에 stale 표시를 추가한다.

### Requirement 5: Evidence-First HDD 워크플로

**User Story:** As an HDD 작성자, I want 근거 기반으로만 문서가 생성·검증되기를, so that 근거 없는 추론이 산출물에 들어가지 않도록 보장할 수 있다.

#### Acceptance Criteria

1. WHILE `generate_hdd_section`이 `allow_unverified_inference=false`로 호출된 상태에서, THE MCP_Server SHALL 생성된 HDD의 모든 문장이 하나 이상의 evidence(`source_uri`)로 뒷받침되도록 하거나, 근거가 부족한 문장을 "확실하지 않음/추가 확인 필요"로 표시한다.
2. WHEN `get_evidence`가 호출되면, THE Evidence_Layer SHALL evidence를 `source_uri`, `source_type`, `support_level`, `confidence`, 선택적 `span`/`quote`를 포함한 정규화된 구조로 반환한다.
3. WHEN `rag_validate_answer`가 호출되면, THE MCP_Server SHALL 문장별 evidence coverage를 평가하고 근거 없는(unsupported) 문장 목록을 반환한다.
4. IF `publish_markdown` 대상 콘텐츠가 `source_uri` 없는 문장 또는 해석되지 않은 `latest` 응답을 포함하면, THEN THE MCP_Server SHALL publish를 거부한다.

### Requirement 6: 신규 운영 도구

**User Story:** As an RAG 운영자, I want index 상태·resource 조회·답변 검증·작업 상태·재인덱싱 도구를, so that 다중 corpus 환경을 운영·진단·갱신할 수 있다.

#### Acceptance Criteria

1. WHEN `rag_index_status`가 호출되면, THE MCP_Server SHALL 요청된 corpus별 `index_version`, `last_indexed_at`, `embedding_model`, freshness를 반환한다.
2. WHEN `rag_read_resource`가 유효 Resource_URI와 함께 호출되면, THE MCP_Server SHALL 권한 재검증 후 해당 URI의 원문/스팬을 반환한다.
3. WHEN `rag_validate_answer`가 호출되면, THE MCP_Server SHALL 답변의 문장별 evidence coverage와 unsupported 문장 목록을 반환한다.
4. WHEN `rag_reindex_document` 또는 `rag_reindex_corpus`가 admin 권한으로 호출되면, THE MCP_Server SHALL 작업을 enqueue하고 `job_id`와 `job://` 상태 URI를 반환한다.
5. WHEN `rag_task_status`가 `job_id`와 함께 호출되면, THE MCP_Server SHALL `queued`/`running`/`done`/`failed` 상태와 완료 시 결과 `resource_uri`를 반환한다.

### Requirement 7: 비동기 Job/Task 프레임워크

**User Story:** As an MCP 클라이언트, I want 장기 실행 작업을 비동기 job으로 처리하고 상태를 폴링하기를, so that 동기 호출 timeout 없이 재인덱싱·재생성 같은 작업을 수행할 수 있다.

#### Acceptance Criteria

1. WHEN 장기 실행 동작(reindex/regenerate)이 요청되면, THE Job_Dispatcher SHALL 작업을 enqueue하고 `job_id`, 초기 상태 `queued`, `job://` 형식 `status_uri`를 반환한다.
2. WHEN `rag_task_status`로 기존 `job_id`가 조회되면, THE Job_Dispatcher SHALL 현재 상태(`queued`/`running`/`done`/`failed`)를 반환한다.
3. WHEN job이 `done` 상태가 되면, THE Job_Dispatcher SHALL 결과 `result_uri`(Resource_URI)를 상태 응답에 포함한다.
4. IF 동기 도구 호출이 장기 작업으로 판단되면, THEN THE MCP_Server SHALL 동기 결과 대신 `job_id`와 `job://` URI를 반환하여 비동기 처리로 전환한다.
5. IF job이 실패하면, THEN THE Job_Dispatcher SHALL 상태를 `failed`로 설정하고 `error` 정보를 반환한다.

### Requirement 8: Statelessness & 공통 입출력 Envelope

**User Story:** As a 시스템 아키텍트, I want 서버가 무상태로 동작하고 모든 호출이 공통 envelope를 사용하기를, so that 호출 순서·세션과 무관하게 결정적으로 라우팅되고 응답 구조가 일관된다.

#### Acceptance Criteria

1. WHEN 동일한 입력(corpus_ids 포함)으로 도구가 호출되면, THE MCP_Server SHALL 서버 세션 상태와 무관하게 동일한 corpus 범위로 라우팅하며 selected corpus를 세션에 저장하지 않는다.
2. THE Tool_Layer SHALL 모든 도구 호출에 대해 `request_id`, `user_context`, `project`, `rtl_snapshot`, `options`를 포함하는 Common_Input을 수용한다.
3. WHEN `request_id`가 입력에 없으면, THE Tool_Layer SHALL 호출마다 고유한 `request_id`를 생성한다.
4. THE Tool_Layer SHALL 모든 응답을 `request_id`, `resolved_scope`, `resolved_index`, `results`, `denied_corpus_ids`, `warnings`, `execution_time_ms`를 포함하는 Common_Output으로 반환한다.

### Requirement 9: 관측 & 감사 (Observability & Audit)

**User Story:** As a 보안·운영 담당자, I want 모든 호출에 대한 구조화 감사 로그를, so that 누가 어떤 corpus를 요청·허용·거부받았고 어떤 mutation을 수행했는지 추적할 수 있다.

#### Acceptance Criteria

1. WHEN 도구 호출이 처리되면, THE Observability_Component SHALL `request_id`, `tool`, `action`, `corpus_requested`, `corpus_allowed`, `corpus_denied`, `index_version`을 포함한 Audit_Record를 1건 생성한다.
2. WHEN mutation(publish/delete/reindex/regenerate)이 수행되면, THE Observability_Component SHALL Audit_Record의 `mutation` 필드에 mutation 종류와 대상을 기록한다.
3. WHEN corpus 또는 resource 접근이 거부되면, THE Observability_Component SHALL 거부된 corpus 및 `denied_resources`를 Audit_Record에 기록한다.
4. THE Observability_Component SHALL 감사 레코드를 구조화 JSON 로그로 CloudWatch Logs에 송출하고 latency(p50/p95/p99) 및 evidence coverage 지표를 산출 가능하게 한다.

### Requirement 10: 하위 호환 & 마이그레이션

**User Story:** As an 기존 MCP 클라이언트 사용자, I want 기존 17개 도구 계약이 유지되고 점진적으로 전환되기를, so that 신규 기능 도입이 현재 운영을 중단시키지 않는다.

#### Acceptance Criteria

1. WHEN corpus 필드 없는 기존 호출(예: `{query, pipeline_id}`)이 수신되면, THE MCP_Server SHALL 기존과 동일한 도구 계약으로 오류 없이 처리한다.
2. THE MCP_Server SHALL 기존 클라이언트에 대해 사람이 읽는 텍스트 응답(`content[].text`) 형식을 유지하면서 신규 구조화 필드를 텍스트 요약으로 포함한다.
3. THE MCP_Server SHALL 신규 corpus 필드(`corpus_id`, `corpus_ids`)를 optional로 유지하여 누락 시 추론으로 대체한다.
4. WHERE `server.mjs`가 활성 진입점(`package.json`이 가리키는 `server.js`)과 drift된 stale 변형으로 존재하는 경우, THE MCP_Server SHALL single source of truth로 일원화한다(중복 파일 제거 또는 통합).
5. IF `server.mjs`의 QuickSight 도구(`quick_dashboard_list`, `quick_dashboard_data`)가 향후 불필요하다고 확인되면, THEN THE MCP_Server SHALL 해당 도구를 drift 정리 시 제거한다.

### Requirement 11: Open Design Questions 해소 (발견·검증·폴백)

**User Story:** As a 설계 검증 담당자, I want 환경 의존적이고 미확인인 가정들을 실환경에서 검증하고 폴백을 정의하기를, so that 미확인 능력을 단정하지 않고 안전하게 구현 범위를 확정할 수 있다.

#### Acceptance Criteria

1. THE MCP_Server SHALL 현 LiteLLM 배포의 MCP server/tool 노출 제어 및 tool-level 권한 전담 가능 범위를 검증하고, 미지원 기능이 확인되면 해당 통제를 Policy_Layer로 이관한다(OQ-1).
2. THE MCP_Server SHALL LiteLLM이 user/team/key를 전달하는 헤더/메타데이터 경로를 검증하고, IF 전달이 불가능하면 THEN Policy_Layer가 사용할 식별 주체 대안을 정의한다(OQ-2).
3. THE MCP_Server SHALL 현 OpenSearch/Qdrant 인덱스의 corpus 단위 필터/ACL 지원 여부를 검증하고, IF 미지원이면 THEN index 분리를 선행 조건으로 명시한다(OQ-3).
4. THE MCP_Server SHALL Neptune 그래프의 NPU↔SoC cross-domain edge 표현 가능 여부를 검증하고, IF 미지원이면 THEN 애플리케이션 레벨 병합으로 cross-domain trace를 대체한다(OQ-4).
5. THE Corpus_Registry SHALL SoC RTL과 NPU RTL의 보안 등급 차이를 corpus `security_level` 및 Policy_Layer 정책으로 반영한다(OQ-5).
6. THE MCP_Server SHALL 현 `@modelcontextprotocol/sdk` 버전의 stateless core/Tasks 지원 범위를 검증하여 async job 구현 방식을 선택한다(OQ-6).
7. THE Job_Dispatcher SHALL 폐쇄망 제약 하에서 job 상태 저장소(DynamoDB 또는 기존 claim DB 별도 테이블)를 선택하여 상태를 영속화한다(OQ-7).
8. THE Policy_Layer SHALL log-only에서 enforce로의 전환 기준을 정의하고, Admin_Tool에 대해서는 전환 기준과 무관하게 즉시 enforce를 적용한다(OQ-9).
