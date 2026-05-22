# LLM Gateway — 사용자 가이드

## 개요

LLM Gateway를 통해 GPT-4o, Claude 3.5 Sonnet 등 AI 모델을 사내에서 안전하게 사용할 수 있습니다.
인터넷 접근 없이 회사 VPN을 통해 접속하며, 개인 Virtual Key로 인증합니다.

---

## 1. 시작하기

### 1.1 Virtual Key 받기

관리자(DevOps팀)에게 요청하면 아래 형태의 키를 발급받습니다:
```
sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

이 키는 OpenAI API Key와 동일한 형식으로, 모든 AI 도구에서 사용 가능합니다.

### 1.2 접속 정보

| 용도 | 엔드포인트 |
|------|-----------|
| LLM API (GPT, Claude) | `https://llm.corp.bos-semi.com/prod/llm` |
| MCP Server (RAG 도구) | `https://mcp.corp.bos-semi.com/prod/mcp` |
| Squid Proxy (Kiro/Claude Code 인증용) | `<관리자에게 IP 문의>:3128` |

> ⚠️ VPN 연결 상태에서만 접근 가능합니다.

---

## 2. Codex CLI 설정

Codex CLI에서 GPT-4o를 사용하려면:

### Windows (PowerShell)

```powershell
$env:OPENAI_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
$env:OPENAI_BASE_URL = "https://llm.corp.bos-semi.com/prod/llm"
```

### Linux/Mac

```bash
export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export OPENAI_BASE_URL="https://llm.corp.bos-semi.com/prod/llm"
```

### 사용 예시

```bash
codex "파일 정렬하는 Python 스크립트 만들어줘"
```

사용 가능한 모델: `gpt-4o`, `gpt-4o-mini`, `o3-mini`

---

## 3. Claude Code 설정

### 방법 A: LiteLLM 경유 (권장 — 예산 추적됨)

```bash
export ANTHROPIC_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export ANTHROPIC_BASE_URL="https://llm.corp.bos-semi.com/prod/llm"
```

### 방법 B: Squid 프록시 경유 (직접 Anthropic API)

```bash
export HTTPS_PROXY="http://<squid-ip>:3128"
export ANTHROPIC_API_KEY="<실제 Anthropic API Key>"
```

> 방법 A 권장 — 예산 관리 및 사용량 추적이 됩니다.

---

## 4. Kiro CLI 설정

Kiro는 인증 시 `*.kiro.dev`에 접근해야 하므로 Squid 프록시를 사용합니다:

```bash
export HTTPS_PROXY="http://<squid-ip>:3128"
```

또는 Kiro 설정 파일에서:
```json
{
  "proxy": "http://<squid-ip>:3128"
}
```

---

## 5. MCP 클라이언트 등록 가이드

BOS-AI RAG MCP 서버에 접속하면 RTL 구조 검색, 신호 추적, 문서 검색 등 17개 도구를 AI 어시스턴트에서 직접 사용할 수 있습니다.

### 5.1 접속 정보

| 항목 | 값 |
|------|-----|
| **Streamable HTTP** | `https://mcp.corp.bos-semi.com/mcp` |
| **Legacy SSE** | `https://mcp.corp.bos-semi.com/sse` |
| **인증** | `x-api-key` 헤더 (관리자에게 발급 요청) |
| **프로토콜** | MCP (Model Context Protocol) |

> ⚠️ 사내 VPN 연결 필수. 도메인은 사내 DNS에서 resolve됩니다.

### 5.2 Kiro 설정

`~/.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "url": "https://mcp.corp.bos-semi.com/mcp"
    }
  }
}
```

### 5.3 VS Code (Copilot MCP) 설정

`.vscode/mcp.json` (워크스페이스) 또는 `settings.json`:

```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "url": "https://mcp.corp.bos-semi.com/mcp"
    }
  }
}
```

### 5.4 Claude Desktop 설정

`~/AppData/Roaming/Claude/claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.corp.bos-semi.com/sse"]
    }
  }
}
```

### 5.5 SSH 터널 사용 (MCP 서버 직접 접근 불가 시)

사내 DNS가 resolve되지 않는 환경에서:

```bash
# SSH 터널 (로컬 3100 → server02:3100)
ssh -L 3100:localhost:3100 user@server02.corp.bos-semi.com

# 설정에서 URL을 localhost로:
# "url": "http://localhost:3100/mcp"
```

### 5.6 사용 가능한 도구 (17개)

| 도구 | 설명 | 예시 질의 |
|------|------|-----------|
| `rag_query` | RAG 지식베이스 자연어 검색 | "UCIe PHY의 LTSSM 상태머신 설명해줘" |
| `search_rtl` | RTL/firmware/문서/레지스터맵 검색 | "trinity noc2axi clock routing" |
| `search_archive` | 아카이브 벡터 검색 | "ATLAS weekly report" |
| `trace_signal_path` | 신호 전파 경로 추적 | module=trinity, signal=npu_out_araddr |
| `find_instantiation_tree` | 모듈 인스턴스 트리 | module=trinity, depth=3 |
| `find_clock_crossings` | CDC 신호 식별 | module=BLK_UCIE |
| `graph_export` | Neptune 그래프 JSON 내보내기 | scope=chip, root=trinity |
| `generate_hdd_section` | HDD 섹션 자동 생성 | topic=ucie/phy/ltssm |
| `get_evidence` | Claim 근거 조회 | claim_id=... |
| `list_verified_claims` | 검증된 Claim 목록 | topic=ucie/phy/ltssm |
| `publish_markdown` | 마크다운 S3 출판 | filename=hdd.md |
| `regenerate_stale_hdd` | Stale HDD 재생성 | - |
| `rag_list_documents` | 업로드 문서 목록 | team=soc |
| `rag_categories` | 팀/카테고리 조회 | - |
| `rag_upload_status` | 업로드 상태 확인 | - |
| `rag_extract_status` | 압축 해제 상태 | task_id=... |
| `rag_delete_document` | 문서 삭제 | s3_key=... |

### 5.7 파이프라인 ID 가이드

RTL 검색 시 `pipeline_id`로 코드 버전을 필터링합니다:

| Pipeline ID | 날짜 | 설명 |
|-------------|------|------|
| `tt_20260221` | 2026-02-21 | N1B0 초기 RTL 스냅샷 |
| `tt_20260516` | 2026-05-16 | N1B0 최신 RTL (DFT/firmware/docs 포함) |

---

## 6. 사용량 확인

```bash
curl "https://llm.corp.bos-semi.com/prod/llm/key/info" \
  -H "Authorization: Bearer sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

응답 예시:
```json
{
  "key": "sk-xxx...xxx",
  "spend": 5.23,
  "max_budget": 20.0,
  "budget_duration": "1mo",
  "models": ["gpt-4o", "claude-3-5-sonnet"],
  "expires": "2026-08-17T00:00:00Z"
}
```

---

## 7. 모델 선택 가이드

| 모델 | 용도 | 비용 | 속도 |
|------|------|------|------|
| gpt-4o-mini | 간단한 코드, 일상 질문 | $ | ⚡ 빠름 |
| gpt-4o | 복잡한 코드, 분석 | $$ | 보통 |
| o3-mini | 추론 집약 작업 | $$ | 보통 |
| claude-3-haiku | 빠른 응답, 요약 | $ | ⚡ 빠름 |
| claude-3-5-sonnet | 코드 작성, 분석 | $$ | 보통 |
| claude-3-opus | 최고 품질, 긴 문서 | $$$ | 느림 |

---

## 8. 에러 해결

| HTTP 코드 | 의미 | 해결 |
|-----------|------|------|
| 401 | 키 무효/만료 | 관리자에게 키 재발급 요청 |
| 429 | 예산 초과 | 관리자에게 예산 증액 또는 다음달 대기 |
| 400 | 잘못된 모델명 | 허용된 모델 목록 확인 |
| 503 | 서비스 장애 | DevOps팀에 보고 |

---

## 9. FAQ

**Q: 키를 분실했어요.**
A: 관리자에게 기존 키 삭제 + 새 키 발급 요청하세요.

**Q: 예산이 언제 리셋되나요?**
A: 매월 1일 자동 리셋됩니다.

**Q: VPN 없이 사용 가능한가요?**
A: 불가능합니다. 모든 접근은 사내 VPN 필수입니다.

**Q: MCP 도구는 별도 키가 필요한가요?**
A: 네. MCP Server API Key는 LiteLLM Virtual Key와 별개입니다. 관리자에게 문의하세요.

**Q: 어떤 모델을 쓸 수 있나요?**
A: 키 발급 시 허용된 모델만 사용 가능합니다. 사용량 조회 API로 확인하세요.
