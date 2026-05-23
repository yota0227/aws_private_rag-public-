# RTL RAG 파이프라인 아키텍처

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-04-29 | 초판. 파이프라인 전체 구조, 버전 이력(v1~v8), MCP Bridge 설정, 품질 현황 |
| v1.0.1 | 2026-05-04 | AI Engineer / SoC Engineer 편으로 분리. 이 문서는 아카이브 |

> **⚠️ 이 문서는 아카이브 상태입니다.** 대상별 최신 문서를 참조하세요:
> - AI Engineer → [rtl-rag-pipeline-architecture-ai-engineer.md](rtl-rag-pipeline-architecture-ai-engineer.md)
> - SoC Engineer → [rtl-rag-pipeline-architecture-soc-engineer.md](rtl-rag-pipeline-architecture-soc-engineer.md)

**대상:** 설계 엔지니어
**목적:** 파이프라인 구조 공유 + 보완 필요 영역 피드백 수집

---

## 1. 파이프라인 개요

RTL 소스 코드를 자동 분석하여 HDD(Hardware Design Document) 초안을 생성하는 시스템이다.

**핵심 흐름:**
```
RTL 소스 (.sv/.v/.svh)
    ↓ S3 업로드
정규식 기반 파싱 (모듈명, 포트, 파라미터, 인스턴스)
    ↓
추가 파서 (Package Parser, Port Classifier)
    ↓
벡터 임베딩 (Titan Embeddings v2, 1024d)
    ↓
OpenSearch 인덱싱 (벡터 + 키워드 검색)
    ↓
MCP Bridge → Obot/Kiro에서 자연어 검색 → HDD 초안 생성
```

**현재 대상:** Trinity/N1B0 RTL (`tt_20260221`, 9,465개 파일, 539MB)
**정답지 대비 품질:** 68% (v8 기준)

---

## 2. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                      On-Premises (사내)                          │
│                                                                  │
│  엔지니어 ──→ Obot (obot.corp.bos-semi.com)                     │
│                 │                                                │
│                 ▼                                                │
│  MCP Bridge (server02:3100/mcp)                                  │
│  ┌───────────────────────────────────────┐                       │
│  │ search_rtl     → RTL 파싱 데이터 검색  │                       │
│  │ search_archive → Archive 문서 검색     │                       │
│  │ rag_query      → 일반 RAG 질의         │                       │
│  │ + 13개 추가 도구                        │                       │
│  └────────────┬──────────────────────────┘                       │
│               │ HTTPS (VPN → TGW → VPC Endpoint)                 │
└───────────────┼──────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  AWS Seoul (ap-northeast-2)                       │
│                                                                  │
│  API Gateway (Private REST) → Main Lambda                        │
│                                    │ Lambda invoke (동기)        │
│                                    ▼                             │
│  RTL Parser Lambda (lambda-rtl-parser-seoul-dev)                 │
│  ┌───────────────────────────────────────┐                       │
│  │ ① 정규식 모듈 파싱        (v1~)       │                       │
│  │ ② Package Parser          (v5~)       │                       │
│  │ ③ Port Classifier         (v6~)       │                       │
│  │ ④ Titan Embeddings v2     (v1~)       │                       │
│  │ ⑤ OpenSearch 인덱싱       (v1~)       │                       │
│  │ ⑥ Neptune Graph DB 적재   (준비 중)   │                       │
│  └────────────┬──────────────────────────┘                       │
└───────────────┼──────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────┐
│                 AWS Virginia (us-east-1)                          │
│                                                                  │
│  OpenSearch Serverless (AOSS)                                    │
│  ┌───────────────────────────────────────┐                       │
│  │ rtl-knowledge-base-index              │                       │
│  │ - module_parse  ~10,000건             │                       │
│  │ - claim         ~140건                │                       │
│  │ - hdd_section   ~12건                 │                       │
│  └───────────────────────────────────────┘                       │
│                                                                  │
│  Bedrock: Titan Embed v2 + Claude 3 Haiku                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 파이프라인 진화 과정 (v1 → v8)

13일간 8회 반복 튜닝을 거쳤다. 매 버전마다 **다른 레이어**를 개선했다.

### 3.1 버전별 변경 이력

| 버전 | 날짜 | 변경 레이어 | 핵심 변경 | 정답지 대비 |
|------|------|-----------|----------|------------|
| **v1** | 4/17 | 인프라 구축 | 정규식 파서 + Titan 임베딩 + OpenSearch 인덱싱 + MCP Bridge 첫 구축 | **12%** |
| v2 | 4/20 | 프롬프트 | 토픽별 프롬프트 분할 (칩 전체 / EDC / NoC / Overlay / NIU) | 15% |
| v2.5 | 4/22 | KB 데이터 | chip_config, edc_topology, noc_protocol, overlay_deep, sram_inventory 심화 분석 추가 | 17% |
| v3 | 4/24 | 파서 + 검색 | 포트 비트폭 추출, 토픽 확장(NIU/Power/Memory), Claim 귀속 정확성 개선, MCP max_results=20 | 18% |
| v3.1 | 4/24 | KB 품질 | Claim 필터: `_wrap` 패턴 제거, 기능 블록 화이트리스트. Claim 85→99건 | 18% |
| **v4** | 4/27 | 검색 랭킹 | analysis_type 패스스루, claim/hdd boost 가중치 (claim 3.0, hdd 2.0, module_parse 0.3) | 18% |
| **v4.1** | 4/27 | 검색 랭킹 | module_parse boost 0.3→1.5 복원. **과조정 교훈 → 리밸런싱** | **45%** |
| **v5** | 4/28 | **파서 (공급)** | **Package Parser 추가** — localparam/enum/struct 추출. SizeX=4, SizeY=5, tile_t 8종 | 45% |
| v5.1 | 4/28 | 파서 (공급) | Package Parser 정규식 수정: `localparam int` 지원. 13개 상수 전부 추출 | 45% |
| **v6** | 4/28 | **파서 (공급)** | **Port Classifier 추가** — 9개 카테고리별 포트 claim. MCP 응답 200→800자 확대 | **55%** |
| **v7** | 4/29 | **검색 (소비)** | **max_results 20→50** — 파서 변경 없이 PRTN/AXI/SFR/EDC IRQ 전부 노출 | **68%** |

### 3.2 개선 레이어 변천

```
v1~v3:   인프라 구축 + 초기 실험                    12% → 18%
v4~v4.1: 검색 랭킹 튜닝 (boost 가중치)              18% → 45%  ← 리밸런싱 도약
v5~v5.1: KB 공급 확대 (Package Parser)              45% → 45%  ← 범주 신설
v6:      KB 밀도 증가 (Port Classifier + MCP 확대)  45% → 55%  ← 기존 범주 두껍게
v7:      검색 소비 확대 (max_results 50)             55% → 68%  ← 축적된 KB 해금
```

**핵심 교훈:** "공급(parser)"과 "소비(retrieval)"는 독립 축이다. v6에서 Port Classifier가 106포트를 전부 분류해놨지만, v7 전까지는 검색 상위 20건 cutoff에 가려져 31개만 보였다. max_results=50 하나로 나머지 75개가 한 번에 노출됐다.

### 3.3 품질 궤적

```
v1(12%) → v2(15%) → v3(18%) → v4.1(45%) → v6(55%) → v7(68%)
                                    ↑              ↑           ↑
                              boost 리밸런싱   Port Classifier  max_results 50
```

---

## 4. 파서 컴포넌트 상세

### 4.1 기본 모듈 파서 (v1~, handler.py → parse_rtl_to_ast)

모든 RTL 파일에 대해 정규식 기반으로 추출:

| 추출 항목 | 예시 | 도입 버전 |
|-----------|------|----------|
| 모듈명 | `trinity` | v1 |
| 포트 목록 (방향 + 비트폭 + 이름) | `input [SizeX-1:0] i_ai_clk` | v1 (비트폭: v3) |
| 파라미터 | `DATA_WIDTH=32` | v1 |
| 인스턴스 (인스턴스명: 모듈타입) | `u_dispatch: tt_dispatch_top` | v1 |

**추출하지 않는 것:**
- `always_ff`/`always_comb` 블록 → 클럭 도메인, 동작 로직
- `assign` 문 → 신호 구동 관계
- `generate` 블록 내부 → wiring topology, feedthrough

### 4.2 Package Parser (v5~, package_extractor.py)

`*_pkg.sv` 파일 전용. 칩 구성 상수와 타입 정의를 추출:

| 추출 대상 | 예시 | claim 형태 |
|-----------|------|-----------|
| localparam | `localparam int SizeX = 4;` | `Package 'trinity_pkg' defines localparam SizeX = 4` |
| typedef enum | `typedef enum logic [2:0] {...} tile_t;` | `...defines typedef enum 'tile_t' with 8 members: TENSIX=3'd0, ...` |
| typedef struct | `typedef struct packed {...} trinity_clock_routing_t;` | `...defines typedef struct 'trinity_clock_routing_t' with 8 fields` |
| parameter | `parameter int X = 10;` | `...defines parameter X = 10` |

**지원 타입:** `int`, `integer`, `logic`, `bit`, `string`, `shortint`, `longint`, `byte`, `unsigned`

**추출하지 않는 것:**
- `function`/`task` (예: `getTensixIndex`, `getNoc2AxiIndex`)
- 중첩 struct
- 복잡한 표현식 평가 (문자열 그대로 저장)

### 4.3 Port Classifier (v6~, port_classifier.py)

포트 10개 이상 모듈에 대해 기능 카테고리별 claim 생성:

| 카테고리 | 매칭 패턴 | trinity.sv 결과 |
|----------|----------|----------------|
| PRTN_Power | `PRTNUN_`, `ISO_EN`, `TIEL_DFT`, `power_good` | 14 ports |
| EDC_APB | `edc_apb_`, `edc_.*irq`, `i_edc_`, `o_edc_` | 16 ports |
| AXI_Interface | `npu_out_`, `npu_in_`, `axi_`, `i_axi_clk` | 39 ports |
| APB_Register | `i_reg_`, `o_reg_` | 8 ports |
| DM_Clock_Reset | `i_dm_clk`, `i_dm_core_reset`, `i_dm_uncore_reset` | 3 ports |
| AI_Clock_Reset | `i_ai_clk`, `i_ai_reset` | 2 ports |
| NoC_Clock_Reset | `i_noc_clk`, `i_noc_reset` | 2 ports |
| Tensix_Reset | `i_tensix_reset` | 1 port |
| SFR_Memory_Config | `SFR_`, `sfr_` | 17 ports |
| **합계** | | **102 + 4 Other = 106** |

**목적:** LLM이 106개 포트를 한꺼번에 보면 중요한 포트가 묻히는 "Lost in the Middle" 문제 해결.

---

## 5. 검색 엔진

### 5.1 OpenSearch 인덱스 스키마

| 필드 | 타입 | 설명 |
|------|------|------|
| `embedding` | vector(1024) | Titan Embeddings v2 벡터 |
| `module_name` | keyword | 모듈명 |
| `port_list` | text | 포트 목록 (공백 구분) |
| `parameter_list` | text | 파라미터 목록 |
| `instance_list` | text | 인스턴스 목록 |
| `file_path` | keyword | S3 경로 |
| `pipeline_id` | keyword | 파이프라인 ID (예: `tt_20260221`) |
| `analysis_type` | keyword | `module_parse` / `claim` / `hdd_section` |
| `topic` | keyword | 토픽 (예: `TopLevelPorts`, `PackageConfig`, `EDC`) |
| `claim_text` | text | claim 본문 |
| `claim_type` | keyword | `structural` / `behavioral` / `connectivity` / `timing` |
| `hdd_content` | text | HDD 섹션 본문 |

### 5.2 검색 가중치 (v4.1~)

| 대상 | boost | 이유 |
|------|-------|------|
| `analysis_type=claim` | 3.0 | 구조화된 설계 사실 — 가장 유용 |
| `analysis_type=hdd_section` | 2.0 | 자동 생성 HDD — 문맥 풍부 |
| `analysis_type=module_parse` | 1.0 | 원본 파싱 — 기본 |
| `module_name` wildcard | 1.5 | 모듈명 정확 매칭 |
| `claim_text`, `hdd_content` | 2.0 | 본문 매칭 |
| `parsed_summary` | 1.2 | 요약 텍스트 |

### 5.3 검색 파라미터 (v7~)

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `query` | (필수) | 검색어 |
| `pipeline_id` | — | 파이프라인 필터 (예: `tt_20260221`) |
| `topic` | — | 토픽 필터 (예: `EDC`, `NoC`) |
| `analysis_type` | — | 문서 타입 필터 |
| `max_results` | **50** (v7에서 20→50) | 최대 결과 수 |

### 5.4 KB 데이터 현황 (tt_20260221)

| 카테고리 | 건수 | 도입 버전 |
|----------|------|----------|
| module_parse | ~10,000 | v1 |
| claim (LLM 생성) | ~99 | v1 |
| claim (Package Parser) | ~30 | v5 |
| claim (Port Classifier) | ~11 | v6 |
| hdd_section | ~12 | v1 |

---

## 6. MCP Bridge 설정

### 6.1 서버 정보

| 항목 | 값 |
|------|-----|
| 서버 | `server02` (온프레미스) |
| 포트 | 3100 |
| 프로토콜 | Streamable HTTP + Legacy SSE |
| MCP 엔드포인트 | `http://server02:3100/mcp` |
| SSE 엔드포인트 (레거시) | `http://server02:3100/sse` |
| Health Check | `http://server02:3100/health` |
| 서비스 관리 | `systemctl restart bos-ai-rag-mcp.service` |
| 소스 파일 | `/root/bos-ai-rag-mcp-bridge/server.js` (CommonJS) |
| Node.js | v22.16.0 |

### 6.2 Kiro IDE에서 연결

Kiro는 MCP 설정을 `~/.kiro/settings/mcp.json` (사용자 레벨) 또는 `.kiro/settings/mcp.json` (워크스페이스 레벨)에서 관리한다.

**설정 파일 위치:**
- Windows: `C:\Users\{username}\.kiro\settings\mcp.json`
- macOS/Linux: `~/.kiro/settings/mcp.json`

**설정 내용:**
```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "url": "https://obot.corp.bos-semi.com/mcp-connect/{connection_id}",
      "autoApprove": [
        "search_rtl",
        "search_archive",
        "rag_query",
        "get_evidence",
        "list_verified_claims"
      ]
    }
  }
}
```

**설정 후:**
1. Kiro 좌측 패널 → MCP Servers 뷰에서 `bos-ai-rag` 서버가 `Connected` 상태인지 확인
2. 연결 실패 시 Command Palette (`Ctrl+Shift+P`) → `MCP: Reconnect Server` 실행
3. 도구 목록이 안 보이면 Command Palette → `MCP: List Tools`로 확인

### 6.3 VS Code에서 연결 (GitHub Copilot Agent Mode)

VS Code에서 MCP 도구를 사용하려면 GitHub Copilot Chat의 Agent Mode를 활용한다.

**방법 1: 워크스페이스 설정 (권장)**

프로젝트 루트에 `.vscode/mcp.json` 파일 생성:

```json
{
  "servers": {
    "bos-ai-rag": {
      "type": "sse",
      "url": "http://server02:3100/sse"
    }
  }
}
```

> **참고:** VS Code MCP는 SSE 프로토콜을 사용한다. Streamable HTTP(`/mcp`)가 아닌 Legacy SSE(`/sse`) 엔드포인트를 지정해야 한다.

**방법 2: 사용자 설정 (전역)**

VS Code `settings.json` (`Ctrl+,` → JSON 편집):

```json
{
  "github.copilot.chat.mcp.servers": {
    "bos-ai-rag": {
      "type": "sse",
      "url": "http://server02:3100/sse"
    }
  }
}
```

**설정 후:**
1. Copilot Chat 패널 열기 (`Ctrl+Alt+I`)
2. 채팅 모드를 **Agent** (`@`)로 전환 (채팅 입력창 좌측 드롭다운)
3. 도구 아이콘(🔧)을 클릭하여 `bos-ai-rag` 서버의 도구 목록 확인
4. 채팅에서 자연어로 질문하면 Agent가 자동으로 MCP 도구를 호출

**사용 예시 (VS Code Copilot Chat):**
```
@workspace trinity 모듈의 top-level 포트를 검색해줘
→ Copilot Agent가 search_rtl 도구를 자동 호출

@workspace EDC 서브시스템의 모듈 계층을 보여줘
→ find_instantiation_tree 도구 호출
```

### 6.4 Claude Code에서 연결

Claude Code(Anthropic CLI 에이전트)는 MCP를 네이티브로 지원한다. Streamable HTTP를 직접 사용하므로 SSE 폴백이 필요 없다.

**방법 1: 프로젝트 설정 (권장)**

프로젝트 루트에 `.mcp.json` 파일 생성:

```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "url": "http://server02:3100/mcp"
    }
  }
}
```

**방법 2: 사용자 설정 (전역)**

`~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "url": "http://server02:3100/mcp"
    }
  }
}
```

**설정 후:**
1. `claude` 명령으로 Claude Code 실행
2. `/mcp` 명령으로 연결된 MCP 서버 확인
3. 자연어로 질문하면 자동으로 MCP 도구 호출

**사용 예시:**
```
> trinity 모듈의 PRTN 포트를 검색해줘
→ search_rtl(query="PRTN", pipeline_id="tt_20260221") 자동 호출

> NoC arbiter 모듈의 인스턴스 트리를 보여줘
→ find_instantiation_tree(module_name="noc_arbiter_tree") 자동 호출
```

> **VS Code + Claude Code 확장:** VS Code에서 Claude Code 확장을 설치하면 위 `.mcp.json` 설정을 자동으로 읽어서 에디터 내에서 MCP 도구를 사용할 수 있다.

### 6.5 연결 확인 (공통)

MCP Bridge가 정상 동작하는지 확인:

```bash
# Health Check
curl http://server02:3100/health

# 기대 응답:
# {"status":"ok","uptime":...,"rag_api":"https://r0qa9lzhgi.execute-api..."}
```

**VPN 연결 필수:** server02는 사내 네트워크에 있으므로 VPN이 연결된 상태에서만 접근 가능하다.

### 6.4 MCP 도구 목록 (16개)

**검색 도구:**

| 도구 | 설명 | 주요 파라미터 |
|------|------|-------------|
| `search_rtl` | RTL 파싱 데이터 검색 | `query`, `pipeline_id`, `topic`, `max_results`(50) |
| `search_archive` | Archive/Bedrock KB 검색 | `query`, `topic`, `source`, `max_results`(5) |
| `rag_query` | 일반 RAG 질의 | `query` |

**그래프 도구:**

| 도구 | 설명 | 주요 파라미터 |
|------|------|-------------|
| `find_instantiation_tree` | 모듈 인스턴스 계층 조회 | `module_name`, `depth` |
| `trace_signal_path` | 신호 전파 경로 추적 | `module_name`, `signal_name` |
| `find_clock_crossings` | 클럭 도메인 크로싱 조회 | `module_name` |

**Claim/HDD 도구:**

| 도구 | 설명 | 주요 파라미터 |
|------|------|-------------|
| `get_evidence` | Claim 근거 조회 | `claim_id` |
| `list_verified_claims` | 검증된 Claim 목록 | `topic` |
| `generate_hdd_section` | HDD 섹션 자동 생성 | `topic`, `section_title` |
| `publish_markdown` | 마크다운 출판 (S3) | `content`, `filename` |

**관리 도구:**

| 도구 | 설명 |
|------|------|
| `rag_categories` | 등록된 카테고리 조회 |
| `rag_list_documents` | 업로드된 문서 목록 |
| `rag_delete_document` | 문서 삭제 |
| `rag_extract_status` | 압축 해제 상태 |
| `rag_upload_status` | 업로드 상태 |

### 6.5 사용 예시

```
# 칩 전체 검색 — 106개 포트 카테고리 전부 노출
search_rtl(query="trinity chip package", pipeline_id="tt_20260221", max_results=50)

# EDC 토픽만 필터링
search_rtl(query="EDC serial bus", pipeline_id="tt_20260221", topic="EDC")

# 모듈 계층 조회
find_instantiation_tree(module_name="trinity", depth=3)

# 신호 경로 추적
trace_signal_path(module_name="trinity", signal_name="i_ai_clk")
```

---

## 7. 품질 현황 (v8 기준)

### 7.1 정답지 대비 섹션별 커버리지

정답지: `N1B0_NPU_HDD_v0.1.md` (엔지니어 수동 작성, 1,291줄, 57KB)

| # | 섹션 | v1 | v4.1 | v6 | **v7** | 비고 |
|---|------|-----|------|-----|--------|------|
| 1 | Overview | 10% | 60% | 75% | **78%** | N1B0 vs Baseline 차이 테이블 부족 |
| 2 | Package Constants / Grid | 0% | 0% | 90% | **94%** | 13 localparams + tile_t + EP 테이블 |
| 3 | Top-Level Ports | 5% | 20% | 60% | **84%** | **106/106 포트 전부 인식** |
| 4 | Module Hierarchy | 10% | 40% | 64% | **67%** | generate 블록 구조 부족 |
| 5 | Compute Tile (Tensix) | 5% | 15% | 45% | **46%** | FPU G-Tile/M-Tile, DEST/SRCB 부족 |
| 6 | Dispatch Engine | 5% | 10% | 24% | **25%** | feedthrough 구조 부족 |
| 7 | NoC Fabric | 5% | 20% | 41% | **42%** | 라우팅 알고리즘, flit 구조 부족 |
| 8 | NIU / AXI Bridge | 5% | 25% | 52% | **61%** | Corner vs Composite 차이 부족 |
| 9 | Clock Architecture | 5% | 30% | 67% | **68%** | clock_routing_in/out 배열 부족 |
| 10 | Reset Architecture | 5% | 25% | 65% | **65%** | — |
| 11 | Power Management | 0% | 0% | 0% | **78%** | **v7에서 신설** (PRTN + ISO_EN) |
| 12 | EDC | 5% | 40% | 75% | **81%** | ring topology 부족 |
| 13 | SRAM / Memory Config | 0% | 5% | 32% | **68%** | **SFR 4개 family** |
| 14 | DFX | 0% | 20% | 55% | **60%** | iJTAG 4-node chain |
| 15 | RTL File Reference | 5% | 30% | 50% | **50%** | — |
| | **가중 합계** | **12%** | **45%** | **55%** | **68%** | |

### 7.2 아직 부족한 영역

| 영역 | 부족한 내용 | 원인 | 해결 방향 |
|------|-----------|------|----------|
| **Compute Tile 내부** | FPU G-Tile/M-Tile, DEST/SRCB 데이터패스 | 깊은 hierarchy | Behavior 파서 |
| **Dispatch feedthrough** | `de_to_t6_coloumn`, `t6_to_de` 배선 | generate 블록 | Generate 파서 |
| **NoC 알고리즘** | DOR/Tendril/Dynamic, flit 구조 | pkg struct 미추출 | Package Parser 확장 |
| **EDC Ring Topology** | U-shape ring, harvest bypass | generate 블록 | Generate 파서 |
| **Clock Routing** | `clock_routing_in/out[SizeX][SizeY]` | trinity.sv wiring | Generate 파서 |
| **N1B0 vs Baseline** | 비교 테이블 | Spec 영역 | Spec RAG |

---

## 8. 다음 단계

| 버전 | 핵심 변경 | 기대 품질 |
|------|----------|----------|
| v8.1 | Hybrid 그라운딩 (`[GROUNDED]`/`[INFERRED]` 태그) | 72~75% |
| v8.2 | Generate 블록 파서 + noc_pkg struct 파서 | 75~78% |
| v9 | **Spec RAG 합류** (RTL + Spec 교차 검색) | **80%+** |

**장기:** Neptune Knowledge Graph 활성화 → 관계 기반 탐색으로 검색 한계 근본 해결

---

## 9. 피드백 요청

### 파싱 관련
1. **포트 분류 9개 카테고리가 적절한가?** 추가/수정 필요한 카테고리?
2. **Package Parser가 놓치는 중요한 정의?** `function`, `task`, `interface` 중 우선 추가할 것?
3. **비트폭 `[SizeX-1:0]`을 수치로 평가해야 하는가?**

### 검색 관련
4. **검색 시 가장 자주 빠지는 정보는?**
5. **토픽 12개 분류가 적절한가?** 추가 필요한 토픽?

### HDD 품질 관련
6. **자동 생성 HDD에서 "반드시 있어야 하는데 없는" 내용은?**
7. **정답지 대비 가장 먼저 보완할 부분의 우선순위?**

### 사용성 관련
8. **Obot에서 가장 자주 하는 RTL 관련 질문은?**
9. **MCP 도구 중 가장 유용한 것 / 개선 필요한 것?**

---

*피드백: Confluence 댓글 또는 Slack #bos-ai-rag*
