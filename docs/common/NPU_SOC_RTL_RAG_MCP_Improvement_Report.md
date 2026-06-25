# NPU/SOC RTL RAG MCP 개선 방향 검토 보고서

## 0. 문서 목적

본 문서는 현재 운영 중인 **NPU RTL 코드 분석용 RAG MCP**와 향후 추가 예정인 **SoC RTL RAG MCP**를 어떤 구조로 확장할지 정리한 구현 방향 보고서입니다.

주요 목적은 다음과 같습니다.

| 항목 | 내용 |
|---|---|
| 대상 시스템 | NPU RTL RAG, SoC RTL RAG, HDD/Spec 문서 RAG, RTL Graph 분석 Tool |
| 연동 방식 | MCP Server를 통해 RAG/RTL 분석 Tool 호출 |
| 권한/예산 관리 | MCP Client와 MCP Server 사이에 **LiteLLM** 배치 |
| 향후 확장 | RAG Backend는 클러스터 형태로 확장 |
| 구현 전달 대상 | Kiro 또는 MCP/RAG 구현 담당 Agent |

---

# 1. 핵심 결론

## 1.1 최종 추천 구조

> **MCP Server는 초기에는 하나로 유지하고, 내부 RAG Backend를 NPU/SOC/공통 문서/Graph 단위로 분리한다.**  
> **LiteLLM은 외부 권한·예산·Tool 노출 Gateway 역할을 맡고, MCP Server는 RAG Tool Gateway 및 Domain Router 역할을 맡는다.**

권장 아키텍처는 다음과 같습니다.

```text
[MCP Client / Codex / Agent / Chatbot]
        |
        | MCP call
        v
[LiteLLM]
  - virtual key
  - user/team/org policy
  - model budget
  - rate limit
  - allowed MCP server/tool control
        |
        v
[bos-ai-rag-mcp]
  - stable MCP tool contract
  - corpus routing
  - corpus/document ACL
  - evidence/resource URI normalization
  - RAG/Graph orchestration
        |
        +--> [npu-rag-cluster]
        |      - NPU vector index
        |      - NPU graph index
        |      - NPU doc store
        |
        +--> [soc-rag-cluster]
        |      - SoC vector index
        |      - SoC graph index
        |      - SoC doc store
        |
        +--> [common-doc-rag-cluster]
        |      - HDD
        |      - Spec
        |      - EDA guide
        |      - verification guide
        |
        +--> [rtl-graph-service]
               - signal path trace
               - hierarchy traversal
               - CDC path query
               - graph export
```

---

## 1.2 한 줄 요약

```text
LiteLLM = 외부 Gateway
현재 MCP Server = RAG Tool Gateway + NPU/SOC Router
RAG Cluster = 도메인별 확장 Backend
```

---

# 2. 배경 및 현재 상황

## 2.1 현재 구성

현재 MCP Server에는 다음 성격의 Tool들이 이미 등록되어 있습니다.

| Tool 그룹 | 대표 Tool | 역할 |
|---|---|---|
| 일반 RAG 질의 | `rag_query` | 업로드된 문서 기반 자연어 질의 |
| 문서 운영 | `rag_list_documents`, `rag_upload_status`, `rag_delete_document`, `rag_categories` | 문서 목록/상태/삭제/카테고리 관리 |
| Extraction 상태 | `rag_extract_status` | PDF/Markdown extraction task 상태 확인 |
| RTL 검색 | `search_rtl`, `search_archive` | RTL/SoC 설계 데이터 및 Archive 문서 검색 |
| Evidence 관리 | `get_evidence`, `list_verified_claims` | claim 기반 근거 조회 및 검증 claim 목록 조회 |
| HDD 생성 | `generate_hdd_section`, `publish_markdown`, `regenerate_stale_hdd` | HDD 섹션 생성/게시/재생성 |
| RTL Graph 분석 | `trace_signal_path`, `find_instantiation_tree`, `find_clock_crossings`, `graph_export` | 신호 경로, 인스턴스 트리, CDC, Graph export |

현재 구조는 단순 문서 RAG가 아니라 다음에 가깝습니다.

```text
RTL-aware Evidence RAG MCP
= 문서 RAG
+ RTL 검색
+ Graph traversal
+ Claim/Evidence 검증
+ HDD 생성 자동화
```

이 방향은 좋습니다. 다만 NPU RAG에 SoC RAG를 추가하면 **MCP Server를 분리할지, 하나로 유지할지**가 중요한 설계 포인트가 됩니다.

---

# 3. MCP 최신 방향에서 고려해야 할 점

MCP 2026-07-28 Release Candidate는 stateless core, Extensions framework, Tasks, MCP Apps, authorization hardening, deprecation policy를 포함합니다. 아직 RC 성격이므로 최종 스펙과 SDK 지원 시점은 확인이 필요하지만, 설계 방향에는 충분히 반영할 가치가 있습니다.

참고 링크:

- https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
- https://docs.litellm.ai/docs/mcp
- https://docs.litellm.ai/docs/proxy/virtual_keys

## 3.1 MCP Server는 상태를 숨기지 않는 방향이 유리

MCP 최신 방향에서는 session state에 의존하지 않는 구조가 중요합니다.

피해야 할 구조:

```text
사용자가 NPU corpus를 선택
→ MCP Server session에 selected_corpus 저장
→ 다음 질의에서 session state 사용
```

권장 구조:

```json
{
  "tool": "search_rtl",
  "arguments": {
    "corpus_ids": ["npu-rtl"],
    "project": "n1b0",
    "rtl_snapshot": "20250301",
    "query": "trace noc2axi router path",
    "top_k": 10
  }
}
```

즉, 모든 Tool 호출은 가능한 한 다음 정보를 명시적으로 받아야 합니다.

| 필드 | 목적 |
|---|---|
| `corpus_id` 또는 `corpus_ids` | NPU/SOC/공통 문서 범위 지정 |
| `project` | `n1b0`, `n1-soc`, `trinity` 등 프로젝트 구분 |
| `rtl_snapshot` | RTL 버전 또는 릴리즈 기준 |
| `query` | 검색/분석 질문 |
| `scope` | module/path/signal/clock domain 등 분석 범위 |
| `top_k` | 검색 결과 개수 |
| `include_evidence` | evidence 포함 여부 |
| `include_graph` | graph path 포함 여부 |

---

## 3.2 장기 작업은 job/task 기반으로 분리

다음 작업은 synchronous Tool call로 오래 잡고 있으면 안 됩니다.

| 작업 | 권장 처리 |
|---|---|
| 대규모 RTL ingest | `job_id` 반환 |
| PDF/Markdown extraction | `job_id` 반환 |
| 전체 corpus reindex | `job_id` 반환 |
| HDD stale section 재생성 | `job_id` 또는 `task_id` 반환 |
| 대형 Graph export | `job_id` 반환 |

권장 패턴:

```json
{
  "tool": "rag_reindex_corpus",
  "arguments": {
    "corpus_id": "soc-rtl",
    "rtl_snapshot": "20260601"
  }
}
```

응답:

```json
{
  "job_id": "job_reindex_soc_20260601_001",
  "status": "queued",
  "status_uri": "job://rag/reindex/job_reindex_soc_20260601_001"
}
```

상태 확인:

```json
{
  "tool": "rag_task_status",
  "arguments": {
    "job_id": "job_reindex_soc_20260601_001"
  }
}
```

---

# 4. LiteLLM과 MCP Server의 역할 분리

LiteLLM은 MCP server 등록, MCP transport 지원, virtual key 기반 접근 제어 등에 사용할 수 있습니다. LiteLLM 문서상 MCP server 추가와 Streamable HTTP, SSE, stdio transport 지원이 설명되어 있고, virtual key는 spend tracking 및 model access control에 사용됩니다.

## 4.1 역할 정의

| 계층 | 역할 | 책임 |
|---|---|---|
| MCP Client | Tool 호출 주체 | Codex, IDE, Agent, Chatbot |
| LiteLLM | 외부 Gateway | key, team/org, budget, rate limit, allowed MCP server/tool |
| MCP Server | RAG Tool Gateway | Tool contract, corpus routing, evidence normalization |
| RAG Orchestrator | 검색 조합 | vector search, graph search, rerank, answer validation |
| RAG Cluster | 실제 검색 Backend | NPU/SOC/Common별 index, doc store, graph DB |
| Policy Store | 권한 정책 | user/team → corpus/document 권한 |

---

## 4.2 LiteLLM에서 처리할 권한

LiteLLM은 coarse-grained 권한에 적합합니다.

| 권한 대상 | 예시 |
|---|---|
| MCP Server 노출 | `bos-ai-rag-mcp` 허용 여부 |
| MCP Tool 노출 | `search_rtl` 허용, `rag_delete_document` 차단 |
| 모델 접근 | 특정 모델 사용 가능 여부 |
| 예산 | 팀별 월 budget |
| Rate limit | 사용자/팀별 RPM/TPM |
| 사용량 추적 | key/team/org 단위 spend tracking |

예시 정책:

| Team/Key | 허용 Tool |
|---|---|
| `npu-readonly` | `rag_query`, `search_rtl`, `get_evidence`, `find_instantiation_tree` |
| `npu-poweruser` | 위 + `trace_signal_path`, `find_clock_crossings`, `graph_export` |
| `soc-readonly` | `rag_query`, `search_rtl`, `get_evidence` |
| `doc-admin` | 위 + `rag_delete_document`, `publish_markdown`, `regenerate_stale_hdd` |

---

## 4.3 MCP Server 내부에서 처리할 권한

LiteLLM만으로는 부족합니다. 이유는 `search_rtl` Tool 호출 권한과 **어떤 RTL corpus에 접근 가능한지**는 별개이기 때문입니다.

따라서 MCP Server 내부에서 fine-grained 권한을 다시 확인해야 합니다.

| 권한 대상 | 예시 |
|---|---|
| corpus 접근 | `npu-rtl`, `soc-rtl`, `soc-spec`, `released-hdd-only` |
| document 접근 | 특정 spec, 특정 RTL snapshot |
| resource URI 접근 | `rtl://...`, `rag://...`, `claim://...` |
| action 권한 | `read`, `search`, `trace`, `export`, `publish`, `delete` |
| cross-domain 권한 | NPU+SOC 동시 검색 허용 여부 |

예시:

```json
{
  "user": "vinh",
  "team": "npu-readonly",
  "tool": "search_rtl",
  "corpus_ids": ["npu-rtl", "soc-rtl"],
  "action": "search"
}
```

MCP Server 내부 authorization 결과:

```json
{
  "allowed_corpus_ids": ["npu-rtl"],
  "denied_corpus_ids": [
    {
      "corpus_id": "soc-rtl",
      "reason": "team npu-readonly has no soc-rtl access"
    }
  ]
}
```

---

# 5. 하나의 MCP Server vs 여러 MCP Server

## 5.1 추천: 초기에는 MCP Server 하나

초기에는 다음 구조를 추천합니다.

```text
LiteLLM
  |
  v
bos-ai-rag-mcp
  |
  +-- npu-rag-cluster
  +-- soc-rag-cluster
  +-- common-doc-rag
  +-- rtl-graph-service
```

## 5.2 하나의 MCP Server가 유리한 이유

| 이유 | 설명 |
|---|---|
| Cross-domain 질문 처리 | NPU와 SoC를 함께 봐야 하는 질문이 많을 가능성이 높음 |
| Tool contract 안정성 | client 입장에서 Tool set이 하나로 유지됨 |
| Evidence 일관성 | citation/resource URI/claim schema를 통일 가능 |
| 권한 관리 단순화 | LiteLLM은 Tool 단위, MCP는 corpus 단위로 분리 가능 |
| 사용자 경험 | 사용자가 NPU MCP/SOC MCP를 직접 고르지 않아도 됨 |
| Orchestration 품질 | client가 아니라 MCP Server가 NPU/SOC 결과 merge 가능 |

Cross-domain 질문 예시:

```text
NPU AXI master가 SoC interconnect로 나가는 경로 찾아줘.
NPU interrupt가 SoC GIC까지 어떻게 연결되는지 추적해줘.
NPU reset/clock이 SoC wrapper에서 어떻게 들어오는지 확인해줘.
NPU register map이 SoC address map에 어떻게 반영되어 있는지 비교해줘.
NPU power/ISO/PRTN control이 SoC PMU와 어떻게 연결되는지 찾아줘.
```

이런 질문은 NPU RAG와 SoC RAG를 동시에 조회해야 하므로, 하나의 MCP Server가 유리합니다.

---

## 5.3 MCP Server를 분리해야 하는 조건

아래 조건이 실제로 발생하면 MCP Server 분리를 검토합니다.

| 조건 | 판단 |
|---|---|
| NPU와 SoC 접근 권한이 완전히 다름 | 분리 검토 |
| SoC RTL이 별도 감사/승인 체계 필요 | 분리 권장 |
| Tool set이 50% 이상 달라짐 | 분리 검토 |
| 하나의 Tool 목록이 너무 커져 Tool selection 품질 저하 | namespace 분리 또는 MCP 분리 |
| 장애 격리가 반드시 필요 | 분리 가능 |
| 배포 주기가 완전히 다름 | backend 우선 분리, 필요 시 MCP 분리 |
| 외부 협력사에 일부만 노출 | 별도 MCP 또는 별도 LiteLLM policy |

---

## 5.4 장기적으로 가능한 구조

초기:

```text
LiteLLM
  |
  v
bos-ai-rag-mcp
```

성장 후:

```text
LiteLLM
  |
  +--> bos-ai-rag-mcp        # cross-domain gateway
  +--> bos-npu-rag-mcp       # NPU 전용
  +--> bos-soc-rag-mcp       # SoC 전용
```

하지만 이 경우에도 `bos-ai-rag-mcp`는 cross-domain 질문용으로 남기는 것이 좋습니다.

---

# 6. 권장 논리 아키텍처

## 6.1 Component View

```text
+---------------------------------------------------+
| MCP Client / Codex / Kiro / Chatbot               |
+------------------------+--------------------------+
                         |
                         v
+---------------------------------------------------+
| LiteLLM                                           |
| - Virtual Key                                    |
| - Team/Org Policy                                |
| - Budget / Rate Limit                            |
| - Allowed MCP Server / Tool                      |
+------------------------+--------------------------+
                         |
                         v
+---------------------------------------------------+
| bos-ai-rag-mcp                                    |
|                                                   |
| Tool Layer                                        |
| - rag_query                                      |
| - search_rtl                                     |
| - trace_signal_path                              |
| - find_instantiation_tree                        |
| - find_clock_crossings                           |
| - get_evidence                                   |
| - generate_hdd_section                           |
| - publish_markdown                               |
| - graph_export                                   |
|                                                   |
| Routing Layer                                     |
| - corpus_id / corpus_ids routing                 |
| - NPU/SOC/Common dispatch                        |
| - cross-domain query merge                       |
|                                                   |
| Policy Layer                                      |
| - corpus ACL                                     |
| - document ACL                                   |
| - resource URI ACL                               |
|                                                   |
| Evidence Layer                                    |
| - claim mapping                                  |
| - source span mapping                            |
| - citation/resource normalization                |
+-------------+-------------------+-----------------+
              |                   |
              v                   v
+----------------------+  +-------------------------+
| npu-rag-cluster      |  | soc-rag-cluster         |
| - vector DB          |  | - vector DB             |
| - graph DB           |  | - graph DB              |
| - doc store          |  | - doc store             |
| - reranker           |  | - reranker              |
+----------------------+  +-------------------------+
              |
              v
+----------------------+
| common-doc-rag       |
| - HDD                |
| - spec               |
| - EDA guide          |
| - verification docs  |
+----------------------+
```

---

# 7. Corpus 설계

## 7.1 Corpus ID 표준화

`corpus_id`는 반드시 표준화해야 합니다.

권장 예시:

| Corpus ID | 설명 |
|---|---|
| `npu-rtl` | NPU RTL source |
| `npu-hdd` | NPU HDD 문서 |
| `npu-graph` | NPU RTL graph index |
| `soc-rtl` | SoC RTL source |
| `soc-spec` | SoC spec 문서 |
| `soc-register-map` | SoC address/register map |
| `soc-graph` | SoC graph index |
| `common-eda-docs` | EDA guide, coding guide, verification guide |
| `released-hdd-only` | 외부/제한 사용자용 release 문서 |

---

## 7.2 Corpus Metadata

각 corpus는 다음 metadata를 가져야 합니다.

```json
{
  "corpus_id": "npu-rtl",
  "domain": "npu",
  "project": "n1b0",
  "data_type": "rtl",
  "rtl_snapshot": "20250301",
  "security_level": "internal",
  "index_version": "idx_20260615_001",
  "embedding_model": "text-embedding-model-name",
  "graph_version": "graph_20260615_001",
  "last_indexed_at": "2026-06-15T09:00:00+09:00"
}
```

---

# 8. Resource URI 설계

## 8.1 왜 Resource URI가 필요한가

RAG 결과가 단순 텍스트로만 나오면 다음 문제가 생깁니다.

| 문제 | 영향 |
|---|---|
| 검색 결과 재조회 어려움 | evidence 검증이 어려움 |
| 후속 Tool 연결 어려움 | `get_evidence`, `generate_hdd_section`과 연결 약함 |
| 권한 검증 어려움 | document/chunk 단위 ACL 처리 어려움 |
| cross-domain merge 어려움 | NPU/SOC source 구분이 불명확 |

따라서 모든 결과는 가능한 한 URI를 가져야 합니다.

---

## 8.2 URI Scheme 권장안

| URI Scheme | 대상 |
|---|---|
| `rag://` | 문서 chunk, HDD section, spec section |
| `rtl://` | RTL file, module, line span |
| `graph://` | Graph node, edge, path |
| `claim://` | verified claim |
| `job://` | async job/task |
| `index://` | index/corpus version |

예시:

```text
rag://npu-hdd/docs/N1B0_NPU_HDD_v0.1.md#section=8.2
rtl://npu-rtl/used_in_n1/rtl/trinity_noc2axi_router_ne_opt.sv#L120-L180
graph://npu-graph/path/signal/npu_irq/path_001
claim://npu-hdd/claim/claim_noc2axi_router_001
job://rag/reindex/job_soc_20260601_001
index://soc-rtl/idx_20260615_001
```

---

# 9. Tool 설계 개선안

## 9.1 Tool 분류

### 사용자-facing Tool

| Tool | 역할 |
|---|---|
| `rag_query` | 일반 자연어 문서 질의 |
| `search_rtl` | RTL/SoC 설계 데이터 검색 |
| `trace_signal_path` | signal path 추적 |
| `find_instantiation_tree` | module instance tree 조회 |
| `find_clock_crossings` | CDC 후보 조회 |
| `generate_hdd_section` | evidence 기반 HDD section 생성 |

### 검증/Evidence Tool

| Tool | 역할 |
|---|---|
| `get_evidence` | claim별 근거 조회 |
| `list_verified_claims` | 검증 claim 목록 조회 |
| `rag_validate_answer` | 답변/문서 섹션이 evidence로 support되는지 검증 |
| `rag_compare_sources` | RTL/HDD/spec 간 충돌 비교 |

### 운영 Tool

| Tool | 역할 |
|---|---|
| `rag_list_documents` | 문서 목록 |
| `rag_categories` | 카테고리 |
| `rag_upload_status` | 업로드 상태 |
| `rag_extract_status` | extraction 상태 |
| `rag_delete_document` | 문서 삭제 |
| `publish_markdown` | Markdown publish |
| `regenerate_stale_hdd` | stale HDD 재생성 |
| `rag_index_status` | index 상태 |
| `rag_task_status` | 장기 작업 상태 |
| `rag_reindex_document` | 특정 문서 재색인 |
| `rag_reindex_corpus` | corpus 재색인 |

---

## 9.2 추가 권장 Tool

현재 목록에 없는 Tool 중 Kiro 구현 대상으로 추천하는 항목입니다.

| 추가 Tool | 우선순위 | 설명 |
|---|---:|---|
| `rag_index_status` | 높음 | corpus/index version, last sync, embedding version 확인 |
| `rag_read_resource` | 높음 | `rag://`, `rtl://`, `graph://` URI 원문 조회 |
| `rag_validate_answer` | 높음 | generated answer/HDD section이 evidence로 support되는지 검증 |
| `rag_compare_sources` | 중간 | RTL/HDD/spec 간 상충 여부 확인 |
| `rag_reindex_document` | 중간 | 특정 문서만 재색인 |
| `rag_reindex_corpus` | 중간 | 특정 corpus 전체 재색인 |
| `rag_task_status` | 높음 | ingest/extract/reindex/generate 작업 상태 조회 |
| `rag_explain_result` | 낮음 | 검색 결과가 왜 선택됐는지 설명 |

---

# 10. Tool Schema 권장안

## 10.1 공통 Input Envelope

모든 Tool에 공통적으로 적용할 수 있는 envelope입니다.

```json
{
  "request_id": "req_20260615_001",
  "user_context": {
    "user_id": "optional_if_forwarded",
    "team_id": "optional_if_forwarded"
  },
  "corpus_ids": ["npu-rtl", "soc-rtl"],
  "project": "n1",
  "rtl_snapshot": "latest",
  "query": "NPU AXI master path to SoC interconnect",
  "options": {
    "top_k": 20,
    "include_evidence": true,
    "include_resource_links": true,
    "include_graph_paths": false
  }
}
```

주의:

| 항목 | 권장 |
|---|---|
| `user_context` | LiteLLM이 header/metadata로 넘길 수 있으면 MCP Server에서 사용 |
| `corpus_ids` | 명시 필수 |
| `rtl_snapshot` | `latest` 허용 가능하지만 응답에는 실제 resolved version을 반환 |
| `include_evidence` | HDD 생성/검증 계열에서는 기본값 `true` 권장 |

---

## 10.2 `search_rtl`

```json
{
  "query": "AXI master path from NPU to SoC interconnect",
  "corpus_ids": ["npu-rtl", "soc-rtl"],
  "scope": {
    "project": "n1",
    "rtl_snapshot": "latest",
    "module": null,
    "path_prefix": null
  },
  "retrieval": {
    "mode": "hybrid",
    "top_k": 20,
    "rerank": true
  },
  "output": {
    "include_evidence": true,
    "include_resource_links": true,
    "include_snippets": true
  }
}
```

응답:

```json
{
  "resolved_scope": {
    "corpus_ids": ["npu-rtl", "soc-rtl"],
    "rtl_snapshot": "20260601"
  },
  "results": [
    {
      "rank": 1,
      "score": 0.87,
      "resource_uri": "rtl://soc-rtl/path/to/soc_top.sv#L200-L260",
      "title": "soc_top.sv NPU AXI connection",
      "snippet": "...",
      "evidence_type": "rtl_span",
      "source": {
        "corpus_id": "soc-rtl",
        "file": "soc_top.sv",
        "line_start": 200,
        "line_end": 260
      }
    }
  ],
  "denied_corpus_ids": []
}
```

---

## 10.3 `trace_signal_path`

```json
{
  "signal": "npu_irq",
  "start_scope": "npu_top",
  "target_scope": "soc_top",
  "corpus_ids": ["npu-rtl", "soc-rtl"],
  "max_depth": 30,
  "options": {
    "include_intermediate_ports": true,
    "include_module_instances": true,
    "include_evidence": true
  }
}
```

응답:

```json
{
  "paths": [
    {
      "path_id": "path_001",
      "confidence": "exact",
      "start": "npu_top.npu_irq",
      "end": "soc_top.gic_irq",
      "nodes": [
        {
          "type": "port",
          "name": "npu_irq",
          "module": "npu_top",
          "resource_uri": "rtl://npu-rtl/path/npu_top.sv#L88-L90"
        }
      ],
      "edges": [
        {
          "from": "npu_top.npu_irq",
          "to": "soc_top.u_npu.npu_irq",
          "edge_type": "instance_port_connection"
        }
      ],
      "evidence_resources": [
        "rtl://npu-rtl/path/npu_top.sv#L88-L90",
        "rtl://soc-rtl/path/soc_top.sv#L200-L230"
      ]
    }
  ],
  "warnings": []
}
```

---

## 10.4 `get_evidence`

```json
{
  "claim_id": "claim_soc_npu_axi_001",
  "include_sources": true,
  "include_rtl_spans": true,
  "include_confidence": true
}
```

응답:

```json
{
  "claim_id": "claim_soc_npu_axi_001",
  "claim_text": "NPU AXI master connects to SoC interconnect through ...",
  "status": "verified",
  "evidence": [
    {
      "source_uri": "rtl://soc-rtl/path/soc_interconnect.sv#L300-L350",
      "source_type": "rtl_span",
      "support_level": "direct",
      "confidence": 0.93,
      "quote": "short extracted snippet",
      "span": {
        "line_start": 300,
        "line_end": 350
      }
    }
  ]
}
```

---

## 10.5 `generate_hdd_section`

이 Tool은 반드시 evidence-first로 제한해야 합니다.

```json
{
  "topic": "NPU AXI integration into SoC interconnect",
  "corpus_ids": ["npu-rtl", "soc-rtl", "soc-spec"],
  "claim_ids": [
    "claim_soc_npu_axi_001",
    "claim_soc_npu_axi_002"
  ],
  "section_type": "architecture_detail",
  "style": "hdd",
  "constraints": {
    "require_all_claims_cited": true,
    "allow_unverified_inference": false,
    "include_open_questions": true,
    "include_verification_checklist": true
  }
}
```

응답:

```json
{
  "section_markdown": "...",
  "used_claim_ids": [
    "claim_soc_npu_axi_001",
    "claim_soc_npu_axi_002"
  ],
  "evidence_coverage": {
    "total_claims": 2,
    "covered_claims": 2,
    "uncovered_claims": 0
  },
  "open_questions": [],
  "resource_links": [
    "claim://soc-hdd/claim/claim_soc_npu_axi_001",
    "rtl://soc-rtl/path/soc_interconnect.sv#L300-L350"
  ]
}
```

중요 정책:

```text
allow_unverified_inference=false 인 경우:
- evidence 없는 문장 생성 금지
- 근거 부족 부분은 "확실하지 않음" 또는 "추가 확인 필요"로 표시
- 추측 문장은 "추측입니다"로 표시
```

---

# 11. Evidence-first HDD 생성 Workflow

## 11.1 권장 Workflow

```text
1. search_rtl / rag_query
   ↓
2. claim 후보 생성
   ↓
3. list_verified_claims
   ↓
4. get_evidence
   ↓
5. generate_hdd_section
   ↓
6. rag_validate_answer
   ↓
7. publish_markdown
```

## 11.2 HDD 생성 시 금지 사항

| 금지 항목 | 이유 |
|---|---|
| evidence 없는 설계 설명 생성 | hallucination 위험 |
| RTL과 HDD가 충돌하는데 HDD만 기준으로 작성 | stale 문서 위험 |
| source URI 없는 문장 publish | 검증 불가 |
| `latest` snapshot을 응답에 그대로 남김 | 재현성 부족 |
| session state 기반 corpus 선택 | stateless 구조 위반 |

---

# 12. NPU/SOC Cross-domain Query 처리

## 12.1 Query Router 동작

MCP Server 내부에 Query Router를 둡니다.

```text
사용자 질의
  |
  v
Query Classifier
  |
  +-- NPU only
  +-- SoC only
  +-- Common docs
  +-- Cross-domain NPU + SoC
  +-- Graph traversal required
  +-- Evidence/HDD generation required
```

## 12.2 Cross-domain 처리 예시

질문:

```text
NPU AXI master가 SoC interconnect까지 어떻게 연결되는지 찾아줘.
```

실행 계획:

```text
1. search_rtl(corpus_ids=["npu-rtl"], query="NPU AXI master port")
2. search_rtl(corpus_ids=["soc-rtl"], query="NPU AXI connection in SoC top")
3. trace_signal_path(corpus_ids=["npu-rtl","soc-rtl"], start_scope="npu_top", target_scope="soc_top")
4. get_evidence(claims)
5. answer merge with resource URIs
```

응답에는 반드시 다음이 포함되어야 합니다.

| 항목 | 설명 |
|---|---|
| NPU side evidence | NPU RTL source span |
| SoC side evidence | SoC RTL source span |
| 연결 path | module/instance/port graph |
| 확실하지 않음 | graph가 끊기거나 alias가 불명확한 지점 |
| follow-up action | 필요한 경우 추가 graph index/reindex 제안 |

---

# 13. 권한 모델

## 13.1 2단계 권한 모델

```text
1차: LiteLLM
  - user/key/team이 어떤 MCP Server/Tool을 호출할 수 있는가?

2차: MCP Server
  - 해당 Tool 호출 안에서 어떤 corpus/document/resource에 접근 가능한가?
```

## 13.2 권한 예시

| 사용자 그룹 | LiteLLM Tool 권한 | MCP Corpus 권한 |
|---|---|---|
| NPU 설계자 | `search_rtl`, `trace_signal_path`, `get_evidence` | `npu-rtl`, `npu-hdd` |
| SoC 설계자 | `search_rtl`, `trace_signal_path`, `get_evidence` | `soc-rtl`, `soc-spec`, 일부 `npu-interface` |
| Cross-domain Architect | 대부분 read/trace Tool | `npu-rtl`, `soc-rtl`, `soc-spec`, `common-eda-docs` |
| Verification Team | `rag_query`, `get_evidence`, `find_clock_crossings` | release된 HDD, 일부 RTL |
| Doc Admin | publish/delete/regenerate | 관리 대상 corpus |
| External Vendor | 제한 Tool | `released-hdd-only` |

---

# 14. Index 및 Cluster 확장 설계

## 14.1 Backend 분리 원칙

RAG Backend는 다음 기준으로 분리합니다.

| 분리 단위 | 이유 |
|---|---|
| NPU vs SoC | 도메인, 권한, 색인 주기 분리 |
| RTL vs HDD/Spec | chunking/search 전략 다름 |
| Vector vs Graph | 질의 방식 다름 |
| Snapshot별 index | 재현성 및 release 비교 |
| Public/released vs internal | 권한 및 보안 정책 다름 |

---

## 14.2 권장 Cluster 구조

```text
npu-rag-cluster
  |
  +-- npu-vector-index
  +-- npu-graph-index
  +-- npu-doc-store
  +-- npu-reranker

soc-rag-cluster
  |
  +-- soc-vector-index
  +-- soc-graph-index
  +-- soc-doc-store
  +-- soc-reranker

common-rag-cluster
  |
  +-- hdd-vector-index
  +-- spec-vector-index
  +-- guide-doc-store
```

---

## 14.3 Index Version 관리

모든 응답은 index version을 반환해야 합니다.

```json
{
  "resolved_index": {
    "corpus_id": "soc-rtl",
    "index_version": "idx_soc_20260615_001",
    "rtl_snapshot": "20260601",
    "graph_version": "graph_soc_20260615_001"
  }
}
```

이유:

| 이유 | 설명 |
|---|---|
| 재현성 | 같은 질문을 나중에 재검증 가능 |
| Debug | 잘못된 답변이 어떤 index에서 나왔는지 추적 |
| Stale 감지 | HDD와 RTL snapshot 불일치 감지 |
| 품질 평가 | index version별 retrieval 성능 비교 |

---

# 15. Observability 및 Audit

## 15.1 반드시 남겨야 할 로그

| 로그 항목 | 목적 |
|---|---|
| `request_id` | end-to-end trace |
| `user_id/team_id/key_id` | 권한 및 감사 |
| `tool_name` | 사용량 분석 |
| `corpus_ids requested/allowed/denied` | 권한 검증 |
| `query` | 품질 분석 |
| `index_version` | 재현성 |
| `retrieval_latency` | 성능 |
| `rerank_latency` | 병목 분석 |
| `graph_query_latency` | graph service 병목 분석 |
| `evidence_count` | answer grounding 확인 |
| `denied_resources` | 보안 audit |
| `publish_action` | 문서 변경 audit |

---

## 15.2 Metric

| Metric | 설명 |
|---|---|
| Tool call count | Tool별 호출 수 |
| Query latency p50/p95/p99 | 응답 성능 |
| Retrieval hit ratio | 검색 품질 |
| Evidence coverage ratio | 답변 근거 충족률 |
| Cross-domain query ratio | NPU/SOC 동시 검색 비율 |
| Denied corpus access count | 권한 위반 시도 |
| Stale HDD regeneration count | 문서 유지보수 지표 |
| Index freshness | 마지막 색인 시점 |
| Graph traversal failure rate | graph 품질 지표 |

---

# 16. Kiro 구현 작업 목록

## 16.1 Phase 1 — Schema/Contract 정리

| Task | 설명 | 완료 기준 |
|---|---|---|
| Tool input 공통 필드 정의 | `corpus_id(s)`, `project`, `rtl_snapshot`, `options` | 모든 주요 Tool schema에 반영 |
| Tool output 공통 필드 정의 | `resource_uri`, `evidence`, `index_version`, `warnings` | 응답 schema 통일 |
| `corpus_id` registry 구현 | NPU/SOC/Common corpus 목록 관리 | `rag_categories` 또는 신규 registry API에서 조회 가능 |
| Resource URI scheme 정의 | `rag://`, `rtl://`, `graph://`, `claim://`, `job://` | URI parser/validator 포함 |
| Error schema 정의 | 권한 거부, corpus 없음, index stale 등 | 표준 error code 반환 |

---

## 16.2 Phase 2 — LiteLLM 연동 권한

| Task | 설명 | 완료 기준 |
|---|---|---|
| LiteLLM virtual key 정책 정의 | team/key별 Tool 허용 | test key로 Tool 노출 차이 확인 |
| MCP Server에 user/team metadata 전달 | header 또는 metadata 방식 | MCP Server log에서 식별 가능 |
| MCP 내부 corpus ACL 구현 | Tool 권한과 corpus 권한 분리 | 허용/거부 corpus가 응답에 반영 |
| Admin Tool 보호 | delete/publish/regenerate 제한 | 일반 key로 호출 시 거부 |
| Audit log 구현 | key/team/tool/corpus/action 기록 | 검색 가능한 audit log 생성 |

---

## 16.3 Phase 3 — NPU/SOC Backend 분리

| Task | 설명 | 완료 기준 |
|---|---|---|
| NPU RAG cluster adapter | 기존 NPU RAG 연결 | `corpus_id=npu-rtl` 검색 정상 |
| SoC RAG cluster adapter | 신규 SoC RAG 연결 | `corpus_id=soc-rtl` 검색 정상 |
| Cross-domain router | `corpus_ids=["npu-rtl","soc-rtl"]` 처리 | 결과 merge 및 source 구분 |
| Index status Tool | `rag_index_status` 추가 | corpus별 version/freshness 반환 |
| Snapshot resolver | `latest` → 실제 snapshot 변환 | 응답에 resolved snapshot 표시 |

---

## 16.4 Phase 4 — Evidence/Validation 강화

| Task | 설명 | 완료 기준 |
|---|---|---|
| `get_evidence` output schema 정리 | source URI, span, confidence | evidence 재조회 가능 |
| `rag_read_resource` 구현 | URI 원문/스팬 조회 | `rtl://...#Lx-Ly` read 가능 |
| `rag_validate_answer` 구현 | 답변 문장별 evidence coverage 확인 | unsupported sentence 검출 |
| `generate_hdd_section` 제한 강화 | verified claim only 모드 | evidence 없는 문장 생성 금지 |
| `rag_compare_sources` 구현 | RTL/HDD/spec 충돌 탐지 | conflict report 반환 |

---

## 16.5 Phase 5 — Graph Tool 고도화

| Task | 설명 | 완료 기준 |
|---|---|---|
| `trace_signal_path` schema 정리 | nodes/edges/evidence_resources | path 재현 가능 |
| `find_instantiation_tree` 개선 | up/down/both traversal | module hierarchy 안정 출력 |
| `find_clock_crossings` 개선 | source/dest clock, synchronizer evidence | CDC 후보와 근거 반환 |
| `graph_export` URI 기반화 | graph subset resource 생성 | `graph://...` URI 반환 |
| Graph index version 관리 | graph_version 응답 포함 | index mismatch 감지 가능 |

---

## 16.6 Phase 6 — Job/Task 비동기화

| Task | 설명 | 완료 기준 |
|---|---|---|
| `rag_task_status` 추가 | job 상태 조회 | queued/running/done/failed |
| ingest/reindex job화 | 긴 작업 비동기 처리 | timeout 없이 상태 확인 |
| `regenerate_stale_hdd` job화 | HDD 재생성 비동기 처리 | job_id 반환 |
| job resource URI | `job://...` 제공 | job 결과 재조회 가능 |
| retry/cancel 정책 | 실패 작업 재시도/취소 | 운영 가능 |

---

# 17. Acceptance Criteria

## 17.1 기능 기준

| 항목 | 기준 |
|---|---|
| NPU 검색 | `corpus_id=npu-rtl`로 기존 NPU RTL 검색 가능 |
| SoC 검색 | `corpus_id=soc-rtl`로 신규 SoC RTL 검색 가능 |
| Cross-domain 검색 | `corpus_ids=["npu-rtl","soc-rtl"]`로 양쪽 결과 merge |
| 권한 제어 | 허용되지 않은 corpus 결과는 검색/응답/evidence에 노출되지 않음 |
| Evidence | 주요 답변은 source URI와 span 포함 |
| HDD 생성 | verified claim/evidence 기반으로만 생성 가능 |
| Resource read | `rag://`, `rtl://`, `claim://` URI 재조회 가능 |
| Index status | corpus별 index/snapshot/freshness 확인 가능 |
| Audit | 누가 어떤 Tool/corpus를 호출했는지 추적 가능 |

---

## 17.2 보안 기준

| 항목 | 기준 |
|---|---|
| LiteLLM Tool 권한 | team/key별 Tool 노출 제한 가능 |
| MCP Corpus ACL | Tool 호출 가능해도 unauthorized corpus 차단 |
| Resource ACL | URI 직접 요청 시에도 권한 재검증 |
| Admin Tool 보호 | delete/publish/regenerate는 admin만 가능 |
| Deny by default | 권한 미정 corpus/tool은 기본 거부 |
| Audit log | 권한 거부 및 publish/delete 기록 유지 |

---

## 17.3 품질 기준

| 항목 | 기준 |
|---|---|
| Unsupported claim 방지 | `rag_validate_answer`에서 unsupported 문장 검출 |
| Snapshot 재현성 | 모든 결과에 resolved snapshot/index version 포함 |
| Stale 감지 | HDD index와 RTL snapshot 불일치 표시 |
| Cross-domain consistency | NPU/SOC source가 분리 표기됨 |
| Tool selection 안정성 | Tool 설명과 schema가 명확함 |
| Latency 관측 | Tool별 latency metric 수집 가능 |

---

# 18. 구현 시 주의사항

## 18.1 확실하지 않음

다음 항목은 실제 환경 확인이 필요합니다.

| 항목 | 상태 |
|---|---|
| 현재 LiteLLM 배포 버전의 MCP Gateway 기능 범위 | 확실하지 않음 |
| LiteLLM에서 MCP request header/user metadata를 어떤 방식으로 MCP Server에 전달할지 | 확실하지 않음 |
| 현재 MCP Server SDK가 2026-07-28 RC 방향을 어느 정도 지원하는지 | 확실하지 않음 |
| 현재 RAG index가 corpus 단위 ACL을 지원하는지 | 확실하지 않음 |
| 현재 Graph DB가 NPU/SOC cross-domain edge를 표현할 수 있는지 | 확실하지 않음 |
| SoC RTL RAG의 보안 등급과 NPU RTL RAG의 보안 등급 차이 | 확실하지 않음 |

---

## 18.2 반드시 피해야 할 구조

| 피해야 할 구조 | 이유 |
|---|---|
| Client가 NPU MCP/SOC MCP를 직접 조합 | orchestration 품질 저하 |
| LiteLLM 권한만 믿고 MCP 내부 ACL 생략 | corpus/document 누출 위험 |
| `rag_query` 하나에 모든 기능 몰아넣기 | Tool contract 모호 |
| session state에 selected corpus 저장 | stateless 확장성 저하 |
| evidence 없는 HDD 생성 | hallucination 위험 |
| search 후 나중에 unauthorized result 제거 | reranker/LLM 입력 단계에서 이미 누출 가능 |
| `latest` snapshot만 기록 | 재현성 부족 |

---

# 19. 최종 권고안

## 19.1 Architecture Decision

```text
Decision:
  MCP Server는 초기에는 하나로 유지한다.

Reason:
  NPU와 SoC는 cross-domain 질문 가능성이 높고,
  evidence/resource/corpus schema를 통일하는 것이 중요하다.

Implementation:
  LiteLLM을 외부 Gateway로 사용한다.
  bos-ai-rag-mcp는 RAG Tool Gateway + Domain Router로 구현한다.
  내부 RAG Backend는 NPU/SOC/Common/Graph 단위로 클러스터 분리한다.

Security:
  LiteLLM에서 Tool-level 권한을 제어한다.
  MCP Server 내부에서 corpus/document/resource-level 권한을 재검증한다.

Future:
  Tool set, 권한 체계, 장애 격리 요구가 커지면
  bos-npu-rag-mcp, bos-soc-rag-mcp를 별도 노출하되,
  cross-domain용 bos-ai-rag-mcp는 유지한다.
```

---

## 19.2 Kiro에게 전달할 핵심 구현 메시지

```text
Implement bos-ai-rag-mcp as a unified MCP Server for NPU/SOC RTL RAG.

Do not split MCP Servers at this stage.
Instead, split backend RAG clusters by corpus/domain:
- npu-rtl
- npu-hdd
- soc-rtl
- soc-spec
- soc-register-map
- common-eda-docs

LiteLLM sits in front of MCP Server and handles:
- virtual keys
- team/org policy
- budget/rate limit
- allowed MCP server/tool exposure

The MCP Server must still enforce:
- corpus ACL
- document ACL
- resource URI ACL
- action-level permission

All tools must be stateless:
- no hidden selected corpus in server session
- every call must include corpus_id or corpus_ids
- latest snapshot must be resolved and returned

All retrieval/generation outputs must include:
- resource_uri
- evidence
- index_version
- resolved rtl_snapshot
- warnings for uncertain or unsupported results

HDD generation must be evidence-first:
- generate_hdd_section must use verified claims/evidence only
- unsupported claims must be blocked or marked as uncertain
- add rag_validate_answer before publish_markdown

Add missing operational tools:
- rag_index_status
- rag_read_resource
- rag_validate_answer
- rag_task_status
- rag_reindex_document
- rag_reindex_corpus
```

---

# 20. 우선순위 요약

| 우선순위 | 작업 |
|---:|---|
| P0 | `corpus_id/corpus_ids` schema 표준화 |
| P0 | LiteLLM Tool 권한 + MCP 내부 corpus ACL 분리 |
| P0 | Resource URI 체계 도입 |
| P0 | NPU/SOC backend routing 구현 |
| P1 | `rag_index_status`, `rag_read_resource`, `rag_task_status` 추가 |
| P1 | `get_evidence` output schema 강화 |
| P1 | `generate_hdd_section` evidence-only 모드 |
| P1 | `rag_validate_answer` 추가 |
| P2 | cross-domain query router 개선 |
| P2 | graph tool output schema 통일 |
| P2 | async job/task framework |
| P3 | 필요 시 MCP Server 분리 구조 검토 |

---

# 21. 최종 요약

두목님 환경에서는 **LiteLLM이 이미 Gateway 역할을 하므로 MCP Server를 보안 Gateway처럼 쪼갤 필요가 줄어듭니다.**

가장 균형 잡힌 방향은 다음입니다.

```text
LiteLLM:
  외부 권한, 예산, Tool 노출 제어

bos-ai-rag-mcp:
  통합 MCP Server
  NPU/SOC/Common RAG routing
  corpus/document/resource ACL
  evidence/resource URI 통일
  HDD 생성 검증

RAG Cluster:
  NPU/SOC/Common/Graph 단위로 분리 확장
```

즉:

> **MCP는 하나로 시작하고, RAG는 도메인별 클러스터로 분리한다.**  
> **LiteLLM에서 Tool-level 권한을 잡고, MCP Server에서 corpus-level 권한을 다시 잡는다.**  
> **모든 결과는 evidence/resource URI/index version 중심으로 재현 가능하게 만든다.**

---

# 22. Hallucination / Uncertainty Note

본 문서는 이전 대화에서 합의한 방향성을 바탕으로 작성되었습니다. LiteLLM 및 MCP RC 관련 기능은 공식 문서 기준으로 참고했지만, 현재 사내 배포 버전 및 SDK 지원 수준은 별도 확인이 필요합니다.

**할루시네이션 등급: 0.02**
