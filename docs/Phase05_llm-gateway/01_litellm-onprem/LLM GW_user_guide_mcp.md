# LLM Gateway 사용자 가이드 (MCP) — RAG 도구 연결

> **Created:** 2026-06-08
> **Updated:** 2026-06-08
> **Purpose:** 사용자가 본인 API 키로 BOS-AI RAG MCP 도구(RTL 검색/신호 추적/HDD 생성 등)를 AI 클라이언트에 연결하는 방법. Codex CLI 우선, 이후 다른 환경 확장.
> **Spec / Project:** 운영 LiteLLM On-Prem
> **Status:** In Review
> **Owner:** IT/DevOps

---

## 0. 시작 전 확인

MCP(Model Context Protocol) 도구는 LLM 게이트웨이를 통해 제공됩니다. 연결 전 다음을 확인하세요.

- **본인 API 키(`sk-...`)** — 발급 방법은 `LITELLM_USER_GUIDE_CODEX.md` 참조. (LLM 키와 동일한 키 사용)
- **팀에 MCP 권한이 부여돼 있어야 함** — 관리자가 팀 단위로 MCP 서버를 연결합니다. 안 되면 IT/DevOps에 "우리 팀에 RAG MCP 연결해달라"고 요청.
- **사내망(VPN) 연결**.

> 키가 **살아있어야** 합니다. 삭제·만료된 키는 MCP 연결 시 `500` 또는 핸드셰이크 실패가 납니다.
> UI `Virtual Keys` 에서 본인 키가 Active 인지 확인하세요.

### 공통 접속 정보

| 항목 | 값 |
|------|-----|
| **MCP 엔드포인트** | `http://llm.corp.bos-semi.com/mcp/`  ← **끝의 슬래시(`/`) 필수** |
| **인증 헤더** | `x-litellm-api-key: Bearer sk-본인키` |
| **Transport** | Streamable HTTP |

> ⚠️ **슬래시 필수:** `/mcp` (슬래시 없음)로 보내면 `307 리다이렉트`가 발생해 일부 클라이언트가 연결에 실패합니다. 반드시 `/mcp/` 로 끝내세요.

---

## 1. Codex CLI 연결

`~/.codex/config.toml` 에 MCP 서버 블록을 추가합니다 (기존 LLM 설정은 그대로 두고 아래를 추가):

```toml
[mcp_servers.bos_ai_rag]
url = "http://llm.corp.bos-semi.com/mcp/"
http_headers = { "x-litellm-api-key" = "Bearer sk-여기에_본인_키" }
startup_timeout_sec = 60
tool_timeout_sec = 120
```

저장 후 `codex` 실행 → 시작 시 MCP 도구가 로드됩니다. `/mcp` 명령으로 도구 목록 확인.

### 정상 동작 예시
```
$ codex
...
(MCP 시작 실패 경고 없이 정상 기동되면 연결 성공)
> /mcp        # 사용 가능한 RAG 도구 목록 표시
```

### 참고 — 전체 config.toml 예시 (LLM + MCP)
```toml
model = "gpt-5.1-codex-mini"
model_provider = "litellm"
model_reasoning_effort = "medium"

[model_providers.litellm]
name = "litellm"
base_url = "http://llm.corp.bos-semi.com/v1"
wire_api = "responses"

[mcp_servers.bos_ai_rag]
url = "http://llm.corp.bos-semi.com/mcp/"
http_headers = { "x-litellm-api-key" = "Bearer sk-여기에_본인_키" }
startup_timeout_sec = 60
tool_timeout_sec = 120
```

---

## 2. 제공 도구 (RAG / RTL 분석)

| 도구 | 설명 |
|------|------|
| `rag_query` | RAG 지식베이스 자연어 검색 |
| `search_rtl` | RTL/firmware/문서/레지스터맵 검색 |
| `search_archive` | 아카이브 벡터 검색 |
| `trace_signal_path` | 신호 전파 경로 추적 |
| `find_instantiation_tree` | 모듈 인스턴스 트리 |
| `find_clock_crossings` | CDC 신호 식별 |
| `graph_export` | Neptune 그래프 JSON 내보내기 |
| `generate_hdd_section` | HDD 섹션 자동 생성 |
| `get_evidence` / `list_verified_claims` | Claim 근거/목록 |
| `publish_markdown` / `regenerate_stale_hdd` | 문서 출판/재생성 |
| `rag_list_documents` / `rag_categories` / `rag_upload_status` / `rag_extract_status` / `rag_delete_document` | 문서 관리 |

> 실제 노출되는 도구는 팀에 부여된 권한에 따라 다를 수 있습니다.

---

## 3. 자주 묻는 질문 / 에러

| 증상 | 원인 | 해결 |
|------|------|------|
| `handshaking ... error decoding response body` | URL에 슬래시 없음(307) **또는 죽은 키** | URL을 `/mcp/` 로, 키가 Active 인지 확인 |
| `500 MCP request failed` | 삭제·만료된 키 사용 | UI에서 살아있는 키로 교체 |
| 도구 목록이 비어있음 | 팀에 MCP 권한 없음 | IT/DevOps에 팀 MCP 연결 요청 |
| `401 / not allowed` | 키-팀-MCP 권한 매칭 안 됨 | 관리자에게 access group 확인 요청 |
| 연결 자체 안 됨 | VPN 미연결 / 헤더명 오타 | VPN 확인, 헤더는 `x-litellm-api-key` |

> 진단 팁: 연결 안 되면 아래로 게이트웨이 직접 테스트 (본인 키로):
> ```bash
> curl -si -X POST http://llm.corp.bos-semi.com/mcp/ \
>   -H "Content-Type: application/json" \
>   -H "Accept: application/json, text/event-stream" \
>   -H "x-litellm-api-key: Bearer sk-본인키" \
>   -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head
> ```
> `200` + 도구 JSON 이면 게이트웨이 정상 → 클라이언트 설정 문제. `500/4xx` 면 키/권한 문제(IT/DevOps 문의).

---

## 4. 다른 환경 (추후 추가 예정)

> 아래 환경별 연결법은 검증되는 대로 추가합니다. 현재는 **Codex CLI(§1)** 만 공식 지원.

### 4.1 VS Code — *(작성 예정)*
### 4.2 Claude Code / Claude Desktop — *(작성 예정)*
### 4.3 Cursor IDE — *(작성 예정)*

공통 원칙(어느 환경이든 동일):
- 엔드포인트: `http://llm.corp.bos-semi.com/mcp/` (슬래시 필수)
- 인증 헤더: `x-litellm-api-key: Bearer sk-본인키`
- Transport: Streamable HTTP
- 살아있는 키 + 팀 MCP 권한 필요

---

## 5. 보안 수칙

- MCP도 LLM과 **동일한 본인 키**를 씁니다. 키는 개인 전용, 공유 금지.
- 키 노출 시 즉시 UI에서 삭제 후 재발급하고, config의 키도 교체하세요.
