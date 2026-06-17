# BOS-AI RAG MCP 도구 사용 가이드

> **Created:** 2026-06-16
> **Updated:** 2026-06-16
> **Purpose:** BOS-AI RAG MCP 도구 사용 가이드 — 도구 선택, 신규 도구, Resource_URI, 비동기 job, 에러 코드.
> **Spec / Project:** `.kiro/specs/mcp-tool-optimization/`
> **Status:** Stable
> **Owner:** Infra/DevOps + RAG MCP

## 1. 개요

BOS-AI RAG MCP 브리지는 폐쇄망 RAG 시스템을 자연어로 다루기 위한 **21개 도구** 모음입니다. 두 종류의 지식을 다룹니다.

- **RTL/SoC 설계 데이터** — 모듈·포트·신호·인스턴스·레지스터맵·계층구조, Neptune 그래프(신호 경로·인스턴스 트리·클럭 도메인 크로싱), 검증된 claim과 HDD 산출물.
- **문서 RAG** — 업로드한 스펙 PDF·설계 문서·주간 보고서·아카이브 문서.

### 응답을 읽는 법

모든 도구 응답은 지금까지와 동일하게 **사람이 읽는 텍스트**로 옵니다. 변하지 않았습니다. 다만 텍스트 **맨 끝**에 기계가 파싱할 수 있는 **구조화 요약 블록**이 한 덩어리 덧붙습니다.

```
(여기까지는 사람이 읽는 기존 텍스트 — 그대로 읽으면 됩니다)

--- structured ---
{"index_version":"idx_20260615_001","resolved_snapshot":"snap_20260615_0930","resource_uris":["rtl://module/tt_noc_router"],"request_id":"a1b2c3-…"}
```

- 텍스트만 필요하면 `--- structured ---` 위쪽만 읽으면 됩니다.
- 재조회·재현·디버깅이 필요하면 아래 블록의 `resource_uris`, `index_version`, `resolved_snapshot`을 활용하세요(자세한 내용은 4·6절).
- **에러가 나면** 이 블록은 붙지 않고, 대신 에러 스키마(`error_code` + `message`)만 텍스트로 반환됩니다(7절).

이 블록은 가산적(additive)입니다. 기존 클라이언트는 앞쪽 텍스트를 그대로 읽고, 새 클라이언트는 끝 블록을 파싱하면 됩니다.

---

## 2. 도구 선택 가이드 — "이 질문엔 이 도구"

LLM/사용자가 가장 자주 헷갈리는 부분이 **검색 3종**입니다. 먼저 이 셋의 차이를 분명히 하세요.

### 2.1 검색 3종 오선택 방지 (가장 중요)

| 무엇을 찾는가 | ✅ 써야 할 도구 | ❌ 쓰면 안 되는 도구 / 이유 |
|---|---|---|
| RTL/SoC 설계 데이터 — 모듈명, 포트, 신호, 인스턴스, 레지스터맵, 계층구조 | **`search_rtl`** | `rag_query` — RTL은 색인되지 않아 **"근거 없음"** 으로 답할 수 있음 · `search_archive` — 아카이브 전용 |
| 사람이 올린 스펙 PDF·설계 문서·주간 보고서에 대한 **자연어 질의** | **`rag_query`** | `search_rtl` — RTL 전용 · `search_archive` — KB 아카이브 메타필터 전용 |
| Archive 문서를 **topic/source 메타데이터로 필터링** 검색 | **`search_archive`** | `rag_query` — 아카이브 필터 미지원 · `search_rtl` — RTL 전용 |

기억 규칙:
- 모듈·신호·포트 얘기가 나오면 **무조건 `search_rtl` 먼저**.
- "올린 문서/스펙/보고서 내용 알려줘"는 `rag_query`.
- topic이나 source(예: `archive_md`)로 좁히는 건 `search_archive`.

### 2.2 전체 도구 선택 표

| 질문 유형 / 입력 | ✅ 권장 도구 | ❌ 피해야 할 도구와 이유 |
|---|---|---|
| RTL/SoC 설계 데이터(모듈·포트·신호·인스턴스·레지스터맵·계층구조) | `search_rtl` | `rag_query`(RTL 미색인 → 근거 없음), `search_archive`(아카이브 전용) |
| 업로드된 스펙 PDF·설계 문서·주간 보고서 자연어 질의 | `rag_query` | `search_rtl`(RTL 전용), `search_archive`(KB 아카이브 메타필터 전용) |
| Archive 문서 topic/source 메타데이터 필터 검색 | `search_archive` | `rag_query`(아카이브 필터 미지원), `search_rtl`(RTL 전용) |
| 특정 claim의 근거 조회 | `get_evidence` | `search_*`/`rag_query`(검색이지 근거 조회 아님) |
| 특정 topic의 검증된 claim 목록 | `list_verified_claims` | `search_archive`(검증 상태 필터 아님) |
| 답변 텍스트의 **문장별** 근거 검증 | `rag_validate_answer` (신규) | `get_evidence`(claim 단위이지 답변 문장 단위 아님) |
| Resource_URI로 원문/스팬 재조회 | `rag_read_resource` (신규) | `search_*`/`rag_query`(검색이지 URI 직접 조회 아님) |
| 인덱스 version/freshness/embedding model | `rag_index_status` (신규) | `rag_upload_status`(문서 KB sync 상태이지 인덱스 상태 아님) |
| 비동기 job 진행 상태 polling | `rag_task_status` (신규) | `rag_extract_status`(압축 해제 작업 전용) |
| 신호 전파 경로 | `trace_signal_path` | `graph_export`(부분그래프 추출이지 경로 추적 아님) |
| 인스턴스화 트리 | `find_instantiation_tree` | `graph_export`(특정 질의 전용이 아님) |
| 클럭 도메인 크로싱(CDC) | `find_clock_crossings` | `search_rtl`(CDC 전용 그래프 질의가 아님) |
| 그래프 부분집합 JSON 추출 | `graph_export` | `trace_signal_path`/`find_instantiation_tree`(특정 질의 전용) |
| 검증 claim 기반 HDD 섹션 생성 | `generate_hdd_section` | `rag_query`(생성이지 질의 아님) |
| 검증 콘텐츠 출판 | `publish_markdown` | — |
| 문서 목록 조회 | `rag_list_documents` | 내용 검색은 `rag_query` |
| 팀/카테고리 목록 조회 | `rag_categories` | — |
| 업로드/KB Sync 상태 조회 | `rag_upload_status` | `rag_index_status`(인덱스 상태이지 문서 sync 아님) |
| 압축 해제(Extraction) 작업 상태 | `rag_extract_status` | `rag_task_status`(비동기 job 전용) |
| 문서 삭제 | `rag_delete_document` | 삭제 전 `rag_list_documents`로 s3_key 확인 |
| stale HDD 일괄 재생성(장시간) | `regenerate_stale_hdd` → 이후 `rag_task_status` | **동기 결과를 기대하지 말 것** — job 반환 후 polling |

> 21개 도구 = 기존 17개 + 신규 4개(`rag_validate_answer`, `rag_index_status`, `rag_read_resource`, `rag_task_status`).

---

## 3. 신규 도구 4종 사용법

### 3.1 `rag_validate_answer` — 답변의 문장별 근거 검증

생성된 답변 텍스트를 **문장 단위로 쪼개서** 각 문장에 근거(evidence)가 있는지 검사합니다. 근거가 0건인 문장은 `unsupported`로 표기되고, 미지원 문장의 텍스트와 위치 목록을 돌려줍니다. 환각(hallucination) 점검에 씁니다.

- **입력**: `answer`(필수, 문자열). 빈 문자열/공백뿐이면 에러를 반환합니다.
- **출력**: 문장별 `supported`/`unsupported` 라벨 + 미지원 문장 목록(text, position).

호출 예:

```json
{ "answer": "UCIE는 최대 32 lane을 지원한다. 초기화는 LTSSM 상태 머신으로 수행된다." }
```

응답(요지):

```
2개 문장 중 1개 unsupported.
- 문장 1 "UCIE는 최대 32 lane을 지원한다." → supported (근거 2건)
- 문장 2 "초기화는 LTSSM 상태 머신으로 수행된다." → unsupported (근거 0건)

--- structured ---
{"sentences":[{"index":0,"supported":true},{"index":1,"supported":false}],
 "unsupported":[{"position":1,"text":"초기화는 LTSSM 상태 머신으로 수행된다."}],
 "index_version":"idx_20260615_001","resolved_snapshot":"snap_20260615_0930","request_id":"…"}
```

> 비교: 특정 claim **한 건**의 근거를 보고 싶으면 `get_evidence`(claim 단위)를 쓰세요. `rag_validate_answer`는 답변 **문장 단위**입니다.

### 3.2 `rag_index_status` — 인덱스 상태 조회

인덱스별 버전·신선도·임베딩 모델을 확인합니다. 검색 결과가 최신인지, 어느 스냅샷에서 나온 것인지 추적할 때 첫 도구입니다.

- **입력**: 없음.
- **출력**: 인덱스마다 `index_version`, `last_updated_at`(ISO 8601 UTC), `embedding_model`. **인덱스가 없으면 빈 리스트**(에러 아님).

응답(요지):

```
인덱스 2개.
- rtl-knowledge-base-index : idx_20260615_001 / 2026-06-15T09:30:00Z / amazon.titan-embed-text-v2
- archive-index            : idx_20260614_007 / 2026-06-14T22:10:00Z / amazon.titan-embed-text-v2

--- structured ---
{"indexes":[
  {"index_version":"idx_20260615_001","last_updated_at":"2026-06-15T09:30:00Z","embedding_model":"amazon.titan-embed-text-v2"},
  {"index_version":"idx_20260614_007","last_updated_at":"2026-06-14T22:10:00Z","embedding_model":"amazon.titan-embed-text-v2"}
 ],"index_version":"idx_20260615_001","resolved_snapshot":"snap_20260615_0930","request_id":"…"}
```

> 비교: 방금 올린 **문서**가 KB에 동기화됐는지는 `rag_upload_status`입니다. `rag_index_status`는 **인덱스** 자체의 상태입니다.

### 3.3 `rag_read_resource` — Resource_URI로 원문 재조회

검색 결과나 근거에 붙은 **Resource_URI**를 그대로 넣어 원문/스팬을 다시 가져옵니다. 검색을 다시 돌릴 필요 없이 정확히 그 자원을 재조회합니다.

- **입력**: `resource_uri`(필수). 6개 스킴(rag/rtl/graph/claim/job/index) 중 하나의 well-formed URI.
- **동작**:
  - well-formed + 존재 → 원문/스팬 반환.
  - malformed(스킴 미지원 또는 식별자 비었/공백) → `invalid_uri`, 부분 콘텐츠 없음.
  - well-formed지만 부재 → `not_found`.

호출 예:

```json
{ "resource_uri": "rag://doc/ucie_spec#L10-L20" }
```

응답(요지):

```
rag://doc/ucie_spec#L10-L20 원문:
(문서 10~20행 텍스트…)

--- structured ---
{"resource_uris":["rag://doc/ucie_spec#L10-L20"],"index_version":"…","resolved_snapshot":"…","request_id":"…"}
```

### 3.4 `rag_task_status` — 비동기 job 상태 polling

장시간 작업이 돌려준 `job_id`로 진행 상태를 조회합니다(5절 흐름).

- **입력**: `job_id`(필수). `regenerate_stale_hdd` 등이 반환한 `job://<job_id>`의 식별자 부분.
- **동작**:
  - 알려진 job → `queued` | `running` | `done` | `failed` 중 **정확히 하나**. `done`이면 결과 포함.
  - 미지의 job_id → `not_found`.

호출 예:

```json
{ "job_id": "a1b2c3-uuid" }
```

응답(요지, 진행 중):

```
job a1b2c3-uuid 상태: running

--- structured ---
{"job_id":"a1b2c3-uuid","status":"running","request_id":"…"}
```

> 비교: 압축 해제(zip) 작업 상태는 `rag_extract_status`입니다. `rag_task_status`는 비동기 **job**(재생성·재색인) 전용입니다.

---

## 4. Resource_URI 사용법

Resource_URI는 결과·근거를 **식별하고 재조회**하기 위한 출력 규약 문자열입니다. 형식은 `<scheme>://<id>`이며, 스킴은 아래 **6개 닫힌 집합**만 허용합니다.

| 스킴 | 의미 | 예 |
|---|---|---|
| `rag://` | 업로드 문서 RAG 자원(문서/스팬) | `rag://doc/ucie_spec#L10-L20` |
| `rtl://` | RTL/SoC 설계 자원(모듈·신호 등) | `rtl://module/tt_noc_router` |
| `graph://` | Neptune 그래프 자원(노드·경로) | `graph://node/BLK_UCIE` |
| `claim://` | 검증 claim 단위 | `claim://b1f9-uuid` |
| `job://` | 비동기 job 핸들(5절) | `job://a1b2c3-uuid` |
| `index://` | 인덱스 식별자 | `index://rtl-knowledge-base-index` |

### 재조회 흐름

1. `search_rtl`/`search_archive`/`rag_query`/`get_evidence` 등을 호출한다.
2. 응답 끝 `--- structured ---` 블록의 `resource_uris`(또는 evidence의 `source_uri`)에서 URI를 얻는다.
3. 그 URI를 `rag_read_resource`의 `resource_uri`에 넣어 원문/스팬을 재조회한다.

```
search_rtl → structured.resource_uris: ["rtl://module/tt_noc_router"]
          → rag_read_resource({ "resource_uri": "rtl://module/tt_noc_router" }) → 원문
```

### well-formed 규칙

- 스킴이 6개 중 하나여야 함. 그 외 스킴은 `invalid_uri`.
- 식별자(`<id>`)는 **비어있지 않고 공백이 없어야** 함. 비었거나 공백 포함이면 `invalid_uri`.
- 자원이 addressable하지 않으면 응답에 URI 필드를 **아예 생략**합니다(빈 문자열/null/placeholder를 넣지 않음).

> ⚠️ **중요**: Resource_URI는 **식별자/출력 규약일 뿐 접근제어가 아닙니다.** 스킴이나 식별자로부터 corpus·권한을 유도하지 않습니다. URI를 안다고 권한이 생기는 것이 아니며, 권한은 별도 계층(MCP 서버 단위)에서 다룹니다.

---

## 5. 비동기 Job 흐름

`regenerate_stale_hdd`(및 향후 reindex)는 오래 걸리므로 **연결을 붙잡지 않습니다.** 호출하면 **2초 안에** `job_id`와 `job://` 상태 URI를 돌려주고, 실제 작업은 백그라운드에서 진행됩니다. 진행 상태는 `rag_task_status`로 polling합니다.

상태는 항상 `queued` → `running` → `done`(성공) 또는 `failed`(실패) 중 하나입니다.

### 절차

1. **작업 시작** — `regenerate_stale_hdd` 호출(입력 없음).

   응답(요지):
   ```
   재생성 작업을 시작했습니다. job_id로 상태를 확인하세요.

   --- structured ---
   {"job_id":"a1b2c3-uuid","status":"queued","status_uri":"job://a1b2c3-uuid","request_id":"…"}
   ```

2. **상태 polling** — 반환된 `job_id`로 `rag_task_status`를 주기적으로 호출.
   ```json
   { "job_id": "a1b2c3-uuid" }
   ```
   - `queued`/`running` → 현재 상태만(최종 결과 없음). 잠시 후 다시 조회.
   - `done` → 상태 `done`과 함께 **결과**를 받음.
   - `failed` → 상태 `failed`와 함께 **에러 표시**를 받음.
   - 모르는 job_id → `not_found`(7절).

3. **완료 처리** — `done`이면 결과를 사용하고, `failed`면 에러 메시지를 보고 재시도/조치.

> `status_uri`의 `job://a1b2c3-uuid`에서 `a1b2c3-uuid` 부분이 곧 `rag_task_status`에 넣는 `job_id`입니다.

---

## 6. 출력 품질 필드 — 재현성

성공 응답의 구조화 블록에는 재현성을 위한 두 필드가 들어갑니다.

- **`index_version`** — 결과가 나온 검색 인덱스의 버전(예: `idx_20260615_001`). 같은 질의라도 인덱스가 갱신되면 값이 달라집니다. 디버깅·재현 시 "어느 인덱스에서 나온 결과인가"를 알려줍니다. 백엔드가 값을 주지 않으면 `"unknown"`으로 채워집니다.
- **`resolved_snapshot`** — 요청이 `latest`이거나 스냅샷을 생략했을 때, 실제로 해석된 **구체 스냅샷 버전**(예: `snap_20260615_0930`). 구체 스냅샷을 명시하면 그 값이 그대로 echo됩니다.

> ⚠️ `resolved_snapshot`은 **절대 리터럴 `"latest"`가 아닙니다.** 응답에서 `latest`를 보게 되는 일은 없습니다. 항상 구체 버전으로 해석되어 돌아오므로, 그 값을 기록해 두면 같은 스냅샷으로 재현 조회를 할 수 있습니다.

---

## 7. 에러 코드 해석

에러가 나면 구조화 블록 대신 **에러 스키마만** 텍스트로 반환됩니다. 부분적인 Resource_URI/index_version/resolved_snapshot은 붙지 않습니다. 형태:

```
{ "error_code": "...", "message": "비어있지 않은 사유" }
```

`error_code`는 정확히 다음 3개 중 하나입니다.

| error_code | 의미 | 사용자 대응 |
|---|---|---|
| `invalid_uri` | Resource_URI 형식이 잘못됨 — 스킴이 6개(rag/rtl/graph/claim/job/index) 밖이거나, 식별자가 비었/공백 포함 | URI 철자·스킴 확인. 검색 결과의 `resource_uris`에서 그대로 복사해 사용. 임의로 만들지 말 것 |
| `not_found` | 형식은 맞으나 가리키는 자원이 없음 — 없는 resource, 없는 job_id, 없는 claim 등 | URI/ID가 최신인지 확인. job이면 너무 이르게/오래 뒤에 조회한 건 아닌지 확인. 삭제됐을 수 있음 |
| `upstream_error` | 위 둘에 해당하지 않는 모든 실패 — Lambda invoke 실패, 타임아웃, 백엔드 5xx 등 | 일시적 문제일 수 있으니 재시도. 반복되면 운영팀에 `request_id`와 함께 문의 |

규칙: `invalid_uri`나 `not_found`로 분류되지 않는 모든 에러는 `upstream_error`입니다. 빈 결과는 에러가 아닙니다 — 예를 들어 `get_evidence`에 근거가 없거나 `rag_index_status`에 인덱스가 없으면 **빈 리스트**가 정상 반환됩니다(에러 스키마 아님).

---

## 8. (선택) Evidence-first 사용

근거 기반으로 산출물을 만들고 검증하는 흐름입니다.

### 8.1 `get_evidence` 정규화 필드

`get_evidence`가 돌려주는 각 근거 항목은 다음 정규 필드를 가집니다.

| 필드 | 의미 |
|---|---|
| `source_uri` | 근거 원문을 가리키는 well-formed Resource_URI(`rag://` 또는 `rtl://`) — `rag_read_resource`로 재조회 가능 |
| `source_type` | 근거 출처 유형(예: pdf, rtl, claim) — 비어있지 않음 |
| `support_level` | 뒷받침 강도(예: strong/weak) — 비어있지 않음 |
| `confidence` | 신뢰도, 0..1 범위로 정규화 |
| `span` | `{ line_start, line_end }` 위치 |

근거가 0건이면 **빈 리스트**가 반환됩니다(에러 아님).

### 8.2 `generate_hdd_section` verified-only 모드

옵션 `allow_unverified_inference`(선택, 기본 동작은 기존 보존)를 **`false`**로 주면, 지원 근거가 0인 생성 세그먼트를 출력 텍스트에 마커 **"확실하지 않음"** 으로 표기합니다. 검증된 claim만으로 채워진 부분과 추론 부분을 한눈에 구분할 수 있습니다.

```json
{ "topic": "ucie/phy/ltssm", "section_title": "LTSSM 상태 머신", "allow_unverified_inference": false }
```

### 8.3 `publish_markdown` 가드

출판 전 콘텐츠를 검사하여, 다음이 있으면 **출판을 거부**하고 에러 스키마를 반환하며 **어떤 부분도 저장하지 않습니다**(원자성).

- 미지원(unsupported) 문장이 1개 이상 포함 → 거부.
- 미해석 `latest` 참조 포함 → 거부.

따라서 보통 `generate_hdd_section`(가능하면 `allow_unverified_inference=false`)으로 만들고 → `rag_validate_answer`로 점검한 뒤 → `publish_markdown`으로 출판하는 순서를 권장합니다.

---

## 참고

- 도구 설명·disambiguation 원문: `mcp-bridge/lib/tool-descriptions.js`
- 출력 envelope/스냅샷 규칙: `mcp-bridge/lib/envelope.js`
- 설계 문서: `.kiro/specs/mcp-tool-optimization/design.md`

> 본 가이드는 도구 계층 사용법만 다룹니다. corpus(도메인) 분리·접근제어는 본 범위가 아니며 별도 spec(`mcp-corpus-routing-acl`, 보류) 소관입니다.
