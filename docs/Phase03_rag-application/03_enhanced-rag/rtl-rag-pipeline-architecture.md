# RTL RAG 파이프라인 아키텍처

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-04-29 | 초판. 파이프라인 전체 구조, 버전 이력(v1~v8), MCP Bridge 설정, 품질 현황 |
| v1.0.1 | 2026-05-04 | AI Engineer / SoC Engineer 편으로 분리. 이 문서는 아카이브 |
| v2.0 | 2026-05-29 | **v9.4a 기준 전면 업데이트.** AOSS→Qdrant 전환, Signal Path Graph, LLM Gateway, 21종 파일 지원, Neptune Ingestion Pipeline, Lambda 비용 최적화 반영 |

**대상:** 설계 엔지니어 + AI Engineer
**목적:** 파이프라인 구조 공유 + 보완 필요 영역 피드백 수집

> **관련 문서:**
> - AI Engineer 상세 → [rtl-rag-pipeline-architecture-ai-engineer.md](rtl-rag-pipeline-architecture-ai-engineer.md)
> - SoC Engineer 상세 → [rtl-rag-pipeline-architecture-soc-engineer.md](rtl-rag-pipeline-architecture-soc-engineer.md)

---

## 1. 파이프라인 개요

RTL 소스 코드를 자동 분석하여 HDD(Hardware Design Document) 초안을 생성하는 시스템이다.

**핵심 흐름:**
```
RTL 소스 (.sv/.v/.svh) + 보조 파일 (21종 확장자)
    ↓ S3 업로드
10종 파서 파이프라인 (정규식 + AST 기반)
    ↓
벡터 임베딩 (Titan Embeddings v2, 1024d, 병렬 5 concurrent)
    ↓
Qdrant 인덱싱 (벡터 검색 + 동적 Boost)
    ↓
Neptune Graph DB 적재 (인스턴스 트리, 신호 경로, CDC)
    ↓
MCP Server → Codex/Claude Code/Kiro에서 자연어 검색 → HDD 초안 생성
```

**현재 대상:** Trinity/N1B0 RTL
- `tt_20260221`: 9,465개 파일, 539MB
- `tt_20260516`: 5,306개 파일, 945MB

---

## 2. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      On-Premises (192.128.0.0/16)                         │
│                                                                          │
│  엔지니어 ──→ Codex CLI / Claude Code / Kiro / VS Code                   │
│                 │                                                         │
│                 ▼                                                         │
│  DNS: llm.corp.bos-semi.com / mcp.corp.bos-semi.com → 10.10.1.62        │
│                 │ HTTPS (VPN → TGW → Frontend VPC)                       │
└─────────────────┼────────────────────────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  AWS Seoul — Frontend VPC (10.10.0.0/16)                  │
│                                                                          │
│  Nginx Proxy (10.10.1.62:443, t3.micro)                                  │
│  ┌───────────────────────────────────────────────────────┐               │
│  │ llm.corp.bos-semi.com → API GW /prod/llm/             │               │
│  │ mcp.corp.bos-semi.com → API GW /prod/mcp/             │               │
│  └────────────┬──────────────────────────────────────────┘               │
│               ▼                                                          │
│  API Gateway (Private REST, r0qa9lzhgi)                                  │
│  ┌───────────────────────────────────────────────────────┐               │
│  │ /rag/*        → Main Lambda (document-processor)       │               │
│  │ /llm/{proxy+} → LiteLLM EC2 (10.200.1.113:4000)       │               │
│  │ /mcp/{proxy+} → MCP Server EC2 (10.10.1.10:3000)      │               │
│  └────────────┬──────────────────────────────────────────┘               │
│               │                                                          │
│  MCP Server EC2 (10.10.1.10, t3.small)                                   │
│  ┌───────────────────────────────────────────────────────┐               │
│  │ 17개 MCP 도구 (Streamable HTTP + Legacy SSE)           │               │
│  │ → Lambda invoke → RAG API                              │               │
│  └───────────────────────────────────────────────────────┘               │
│                                                                          │
│  RTL Parser Lambda (lambda-rtl-parser-seoul-dev)                         │
│  ┌───────────────────────────────────────────────────────┐               │
│  │ ① 기본 모듈 파서        ⑥ Wire Declaration Parser      │               │
│  │ ② Package Parser        ⑦ Port Binding Parser          │               │
│  │ ③ Port Classifier       ⑧ Signal Path Graph            │               │
│  │ ④ Generate Block Parser ⑨ DFX Auto Extractor           │               │
│  │ ⑤ Always Block Parser   ⑩ Module Parameter Extractor   │               │
│  │                                                         │               │
│  │ 512MB / 300초 / Concurrency 20                          │               │
│  └────────────┬──────────────────────────────────────────┘               │
└───────────────┼──────────────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  AWS Seoul — Logging VPC (10.200.0.0/16)                  │
│                                                                          │
│  LiteLLM Proxy (10.200.1.113, t3.medium)                                 │
│  ┌───────────────────────────────────────────────────────┐               │
│  │ OpenAI-compatible API (GPT + Bedrock 모델 통합)        │               │
│  │ Virtual Key 기반 팀별 예산 관리                         │               │
│  │ → NAT → IGW → api.openai.com                          │               │
│  │ → TGW → Frontend VPC → VPC Peering → Bedrock          │               │
│  └───────────────────────────────────────────────────────┘               │
│                                                                          │
│  Squid Forward Proxy (t3.micro, port 3128)                               │
│  ┌───────────────────────────────────────────────────────┐               │
│  │ 도메인 화이트리스트: *.kiro.dev, api.openai.com 등     │               │
│  └───────────────────────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────────────────────┘
                ▼ (VPC Peering)
┌─────────────────────────────────────────────────────────────────────────┐
│                 AWS Virginia — Backend VPC (10.20.0.0/16)                 │
│                                                                          │
│  Qdrant EC2 (10.20.1.217:6333)                                           │
│  ┌───────────────────────────────────────────────────────┐               │
│  │ Collection: rtl-knowledge-base                         │               │
│  │ RTL 벡터 인덱스 (module_parse + claim + signal_path)   │               │
│  └───────────────────────────────────────────────────────┘               │
│                                                                          │
│  Bedrock: Titan Embed v2 + Claude 3 Haiku/Sonnet                         │
│  Neptune Graph DB (인스턴스 트리, 신호 경로, CDC)                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 파이프라인 진화 과정 (v1 → v9.4a)

### 3.1 버전별 변경 이력

| 버전 | 날짜 | 핵심 변경 | 정답지 대비 |
|------|------|----------|------------|
| **v1** | 4/17 | 정규식 파서 + Titan 임베딩 + AOSS 인덱싱 + MCP Bridge 첫 구축 | **12%** |
| v2~v3 | 4/20~24 | 프롬프트 분할, 토픽 확장, Claim 필터 | 18% |
| **v4.1** | 4/27 | boost 리밸런싱 (module_parse 0.3→1.5) | **45%** |
| **v5** | 4/28 | Package Parser 추가 (localparam/enum/struct) | 45% |
| **v6** | 4/28 | Port Classifier 추가 (9개 카테고리) | **55%** |
| **v7** | 4/29 | max_results 20→50 | **68%** |
| **v9** | 5/08 | Generate Block Parser + Always Block Parser + Wire Declaration Parser + Bitwidth Evaluator + 대형 모듈 청킹 | **75%** |
| **v9.2** | 5/10 | EP Table 계산, NoC repeater, 동적 Boost (5가지 질의 유형) | **78%** |
| **v9.3** | 5/15 | Port Binding Parser + Neptune Ingestion Pipeline + DFX 자동 추출 | **80%** |
| **v9.4** | 5/20 | ExpressionPreserver, generate block label, instantiation param override, Graph Evidence Provider | **82%** |
| **v9.4a** | 5/25 | **AOSS→Qdrant 전환**, Signal Path Graph, 21종 파일 지원, LLM Gateway 구축, Lambda 비용 최적화 | **82%** |

### 3.2 v9.4a 주요 변경 사항

| 영역 | v9.2 (이전 문서) | v9.4a (현재) |
|------|-----------------|-------------|
| 벡터 DB | AOSS (OpenSearch Serverless) | **Qdrant on EC2** (Virginia, 10.20.1.217:6333) |
| 파일 지원 | .v, .sv, .svh (3종) | **21종** (RTL + firmware + docs + config + filelist) |
| Signal Path | 미지원 | **signal_path_graph** (assign/port/wire edges) |
| LLM Gateway | 없음 (server02 직접 연결) | **4 EC2** (LiteLLM + MCP + Squid + Nginx) |
| 임베딩 | 순차 1건씩 | **병렬 5 concurrent** + batch upsert 50건 |
| Lambda | 2048MB / 900초 | **512MB / 300초 / concurrency 20** |
| Neptune | Read-only | **Full Ingestion** (3-tier instance model, 8 edge types) |
| HDD 생성 | Claim-only evidence | **Graph Evidence Provider** (Neptune → HDD) |
| DFX | Manual claims only | **Auto-extraction** (*_dfx 패턴) + manual 우선 |
| 검색 | 고정 boost | **질의 유형 분류** + 동적 boost + content dedup |

---

## 4. 파서 컴포넌트 (10종)

### 4.1 파서 목록

| # | 파서 | 파일 | 대상 | 추출 내용 | Feature Flag |
|---|------|------|------|----------|-------------|
| ① | 기본 모듈 파서 | handler.py | 모든 .sv/.v/.svh | 모듈명, 포트, 파라미터, 인스턴스 | (항상 활성) |
| ② | Package Parser | package_extractor.py | *_pkg.sv | localparam, enum, struct, function, EP Table | PARSER_PACKAGE_ENABLED |
| ③ | Port Classifier | port_classifier.py | 포트 10개+ 모듈 | 9개 기능 카테고리 분류 | PARSER_PORT_CLASSIFIER_ENABLED |
| ④ | Generate Block Parser | generate_block_parser.py | generate 포함 모듈 | 토폴로지, 인스턴스 위치, NoC repeater, label | PARSER_GENERATE_BLOCK_ENABLED |
| ⑤ | Always Block Parser | always_block_parser.py | always_ff 포함 모듈 | 클럭 도메인, CDC 경고 | PARSER_ALWAYS_BLOCK_ENABLED |
| ⑥ | Wire Declaration Parser | wire_declaration_parser.py | wire/logic 선언 | 배열 차원(3D+), struct 참조, 목적 유추 | PARSER_WIRE_DECLARATION_ENABLED |
| ⑦ | Port Binding Parser | port_binding_parser.py | 인스턴스 포함 모듈 | .port(signal) 바인딩, param override | PARSER_PORT_BINDING_ENABLED |
| ⑧ | Signal Path Graph | signal_path_graph.py | 모든 RTL | assign/port/wire edges (신호 흐름) | PARSER_SIGNAL_PATH_ENABLED |
| ⑨ | DFX Auto Extractor | handler.py 내장 | *_dfx 모듈 | clock in/out 수, IJTAG ifdef | (자동 감지) |
| ⑩ | Module Parameter Extractor | package_extractor.py | 비-패키지 모듈 | Top-level parameter 정의 | PARSER_FUNCTION_EXTRACTOR_ENABLED |

### 4.2 파일 타입별 처리

| Phase | 확장자 | 처리 방식 |
|-------|--------|----------|
| Phase 1 (RTL) | .sv, .v, .svh, .vh | 10종 파서 전체 파이프라인 |
| Phase 2 (Text) | .json, .svd, .h, .hpp, .c, .cpp, .md, .rst, .txt, .sdc, .dts, .csv, .py, .tcl, .yaml, .yml | 텍스트 청킹 + 임베딩 |
| Phase 3 (Filelist) | .f | 디렉토리별 모듈 hierarchy 추출 |

---

## 5. 검색 엔진

### 5.1 벡터 DB: Qdrant

| 항목 | 값 |
|------|-----|
| 엔진 | Qdrant (EC2, Virginia VPC) |
| 엔드포인트 | 10.20.1.217:6333 |
| Collection | rtl-knowledge-base |
| 벡터 차원 | 1024 (Titan Embeddings v2) |
| 거리 함수 | Cosine |
| 네트워크 | Seoul Lambda → VPC Peering → Virginia Qdrant |

### 5.2 동적 Boost (질의 유형별)

| 질의 유형 | claim boost | module_parse boost | 매칭 키워드 |
|-----------|------------|-------------------|------------|
| port_query | 4.0 | 0.5 | port, pin, signal, interface |
| hierarchy_query | 1.5 | 3.0 | instance, hierarchy, tree, sub-module |
| config_query | 4.0 | 1.0 | parameter, config, constant, setting |
| connectivity_query | 4.0 | 1.0 | connect, wire, route, topology |
| general_query | 3.0 | 1.0 | (default fallback) |

### 5.3 검색 파라미터

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `query` | (필수) | 검색어 |
| `pipeline_id` | — | 파이프라인 필터 (예: `tt_20260221`) |
| `topic` | — | 토픽 필터 |
| `analysis_type` | — | 문서 타입 필터 |
| `max_results` | **50** | 최대 결과 수 |

### 5.4 KB 데이터 현황

| 카테고리 | 건수 | 생성 주체 |
|----------|------|----------|
| module_parse | ~10,000 | 기본 파서 |
| module_parse_chunk | ~500 | 대형 모듈 청킹 |
| claim (Package) | ~80 | Package Parser |
| claim (Port) | ~11 | Port Classifier |
| claim (Generate) | ~20 | Generate Block Parser |
| claim (Always) | ~15 | Always Block Parser |
| claim (Wire) | ~10 | Wire Declaration Parser |
| claim (DFX) | ~8 | DFX Auto Extractor |
| signal_path_edge | ~500 | Signal Path Graph |
| text_chunk | ~2,000 | 보조 파일 (Phase 2) |
| filelist_hierarchy | ~50 | Filelist (Phase 3) |
| hdd_section | ~12 | LLM 생성 |

---

## 6. LLM Gateway

### 6.1 컴포넌트

| 컴포넌트 | 위치 | IP | 인스턴스 | 포트 | 용도 |
|----------|------|-----|---------|------|------|
| LiteLLM Proxy | **On-Prem** | 192.128.10.102 | 물리 서버 | 4000 | OpenAI-compatible API (GPT + Bedrock) |
| Nginx Proxy | AWS Frontend VPC | 10.10.1.62 | t3.micro | 443 | TLS 종단 + API GW 프록시 (MCP 전용) |
| MCP Server | AWS Frontend VPC | 10.10.1.10 | t3.small | 3000 | 17개 MCP 도구 |

> **변경 이력 (2026-05-29):** LiteLLM은 AWS Logging VPC에서 On-Prem(192.128.10.102)으로 이전.
> MVP 테스트는 server01(192.128.20.240)에서 완료. AWS LiteLLM EC2 terminate 완료.

### 6.2 DNS

사내 BIND zone 파일 (`/var/cache/bind/corp.bos-semi.com.zone`):
```
llm  IN  A  192.128.10.102    ; On-Prem LiteLLM (직접 접근)
mcp  IN  A  10.10.1.62        ; AWS Nginx → API GW → MCP EC2
```

### 6.3 네트워크 경로

```
LiteLLM: On-prem client → llm.corp.bos-semi.com(192.128.10.102:4000) → 직접 접근
MCP:     On-prem client → mcp.corp.bos-semi.com(10.10.1.62:443) → VPN → TGW → Nginx → API GW → MCP EC2
```

---

## 7. MCP 도구 (17개)

### 7.1 검색 도구

| 도구 | 설명 | 주요 파라미터 |
|------|------|-------------|
| `search_rtl` | RTL/SoC 데이터 검색 (Qdrant 벡터 + dedup) | `query`, `pipeline_id`, `topic`, `max_results` |
| `search_archive` | Archive/Bedrock KB 검색 | `query`, `topic`, `source`, `max_results` |
| `rag_query` | 일반 RAG 질의 | `query` |
| `get_evidence` | Claim 근거 조회 | `claim_id` |

### 7.2 그래프 도구

| 도구 | 설명 | 주요 파라미터 |
|------|------|-------------|
| `find_instantiation_tree` | 모듈 인스턴스 계층 조회 | `module_name`, `depth` |
| `trace_signal_path` | 신호 전파 경로 추적 | `module_name`, `signal_name` |
| `find_clock_crossings` | 클럭 도메인 크로싱 조회 | `module_name` |
| `graph_export` | 그래프 서브셋 JSON 내보내기 | `scope`, `root_module` |

### 7.3 Claim/HDD 도구

| 도구 | 설명 |
|------|------|
| `list_verified_claims` | 검증된 Claim 목록 |
| `generate_hdd_section` | HDD 섹션 자동 생성 |
| `publish_markdown` | 마크다운 S3 출판 |
| `regenerate_stale_hdd` | Stale HDD 일괄 재생성 |

### 7.4 관리 도구

| 도구 | 설명 |
|------|------|
| `rag_categories` | 카테고리 조회 |
| `rag_list_documents` | 문서 목록 |
| `rag_delete_document` | 문서 삭제 |
| `rag_extract_status` | 압축 해제 상태 |
| `rag_upload_status` | 업로드 상태 |

---

## 8. 클라이언트 연결 설정

### 8.1 Codex CLI (폐쇄망)

`~/.codex/config.toml`:
```toml
[mcp_servers.bos-ai-rag]
url = "https://mcp.corp.bos-semi.com/mcp"
startup_timeout_sec = 60
tool_timeout_sec = 120
```

### 8.2 Claude Code

`.mcp.json` (프로젝트 루트):
```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "url": "https://mcp.corp.bos-semi.com/mcp"
    }
  }
}
```

### 8.3 Kiro IDE

`.kiro/settings/mcp.json`:
```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "url": "http://localhost:3100/mcp",
      "autoApprove": ["search_rtl", "search_archive", "rag_query", "get_evidence"]
    }
  }
}
```
> Kiro는 SSH 터널(`localhost:3100` → MCP Server) 경유.

### 8.4 VS Code (Copilot Agent Mode)

`.vscode/mcp.json`:
```json
{
  "servers": {
    "bos-ai-rag": {
      "type": "sse",
      "url": "https://mcp.corp.bos-semi.com/sse"
    }
  }
}
```

### 8.5 LiteLLM 경유 (MCP Gateway)

LiteLLM UI에서 MCP Server 등록:
- Name: `bos_ai_rag`
- Transport: Streamable HTTP
- URL: `https://mcp.corp.bos-semi.com/mcp`

클라이언트에서 LiteLLM MCP Gateway 사용:
```
http://192.128.10.102:4000/bos_ai_rag/mcp
```

---

## 9. 운영 정보

### 9.1 Lambda 설정

| 항목 | 값 |
|------|-----|
| 함수명 | lambda-rtl-parser-seoul-dev |
| 메모리 | 512MB |
| Timeout | 300초 |
| Reserved Concurrency | 20 |
| 환경변수 | QDRANT_HOST, QDRANT_PORT, BEDROCK_REGION, CLAIM_DB_TABLE |

### 9.2 재인덱싱

```bash
py scripts/reindex_all_rtl.py --pipeline-id tt_20260516 --batch-size 10 --batch-delay 5
```

### 9.3 Health Check

```bash
# MCP Server
curl -k https://mcp.corp.bos-semi.com/health

# LiteLLM (On-Prem)
curl -H "Authorization: Bearer <KEY>" http://192.128.10.102:4000/health
```

---

## 10. 다음 단계

| 항목 | 설명 | 상태 |
|------|------|------|
| tt_20260516 재인덱싱 | QDRANT_ENDPOINT 영구 등록 후 실행 | 대기 |
| Terraform provider 수정 | LiteLLM/MCP EC2 SG에 provider=aws.seoul 추가 | 대기 |
| LiteLLM MCP 연결 | LiteLLM에서 MCP Server 등록 완료 | 진행 중 |
| v10 (장기) | Slang AST-first RAG, RTL2Vec, 15+ Neptune edge types | 설계 중 |

---