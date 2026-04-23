# RAG HDD 생성 품질 저하 — 근본 원인 분석 및 개선 로드맵

**문서 ID:** REVIEW-RAG-HDD-001  
**버전:** v0.1  
**작성일:** 2026-04-22  
**분석 대상:**
- 정답지: `test_rtl/Sample/N1B0_HDD_v0.1.md` (엔지니어 수동 작성)
- 생성본 v1: `test_rtl/rag_result/v1/Trinity_N1B0_HDD_Complete_v1.md`
- 생성본 v2: `test_rtl/rag_result/v2/01~06_*_v2.md` (6개 파일)
- 보조 자료: `test_rtl/rag_result/Compare_Report_01_vs_Sample_HDD.md`, `prompt.md`

---

## 목차

1. [문제 정의 및 정량 측정](#1-문제-정의-및-정량-측정)
2. [시스템 파이프라인 구조 (현재 상태)](#2-시스템-파이프라인-구조-현재-상태)
3. [근본 원인 분석 (RCA) — 7계층](#3-근본-원인-분석-rca--7계층)
   - [Layer 1: 데이터 수집 계층](#layer-1-데이터-수집-계층)
   - [Layer 2: Claim 추출 계층](#layer-2-claim-추출-계층)
   - [Layer 3: 인덱싱 및 검색 계층](#layer-3-인덱싱-및-검색-계층)
   - [Layer 4: 생성 계층](#layer-4-생성-계층)
   - [Layer 5: 툴링 및 MCP 계층](#layer-5-툴링-및-mcp-계층)
   - [Layer 6: 프롬프트 설계 계층](#layer-6-프롬프트-설계-계층)
   - [Layer 7: 평가 계층](#layer-7-평가-계층)
4. [실패 메커니즘 종합 다이어그램](#4-실패-메커니즘-종합-다이어그램)
5. [개선 로드맵](#5-개선-로드맵)
6. [평가 프레임워크](#6-평가-프레임워크)

---

## 1. 문제 정의 및 정량 측정

### 1.1 현재 품질 지표 (v2 기준, Compare_Report_01 분석)

| 측정 항목 | 정답지 | RAG v1 | RAG v2 | 목표 |
|-----------|--------|--------|--------|------|
| 섹션 커버리지 | 17/17 (100%) | ~7/17 (41%) | 10/17 (59%) | ≥ 85% |
| 구체적 수치/파라미터 정확도 | 높음 | 낮음 | ~25% | ≥ 70% |
| 서브모듈 상세도 | 중간 | 일부 높음 | ~40% | ≥ 60% |
| 아키텍처 시스템 레벨 관점 | 높음 | 낮음 | ~30% | ≥ 65% |
| Hallucination (정답지에 없는 내용) | 0% | ~40% | ~20% | ≤ 5% |
| N1B0-specific 정보 비율 | 100% | ~40% | ~55% | ≥ 90% |

### 1.2 섹션별 누락/오류 현황

| 섹션 | v1 | v2 | 누락 원인 (선행 분석) |
|------|----|----|----------------------|
| Package Constants & Grid | ❌ | ❌ | Claim 추출에 `parameter`/`enum` 미포함 |
| Top-Level Ports (정확한 폭) | ⚠️ 오류 | ⚠️ 부분 | per-column 배열 `[SizeX-1:0]` 미반영 |
| Module Hierarchy (N1B0 specific) | ❌ 오류 | ⚠️ 부분 | `trinity_router` 미사용 사실 역전 기술 |
| NoC Connections (manual assign) | ❌ | ⚠️ 부분 | X축 manual assign 청크 미리트리브 |
| Clock Routing Structure | ❌ | ⚠️ 부분 | `trinity_clock_routing_t` 구조체 누락 |
| Dispatch Feedthrough | ❌ | ⚠️ 부분 | de_to_t6 관련 Claim 미추출 |
| PRTN Daisy Chain | ❌ | ❌ | Power Management topic Claim 없음 |
| Memory Config (SFR Ports) | ❌ | ❌ | SFR 신호 Claim 미추출 |
| SRAM Inventory | ❌ | ❌ | `analysis_type: sram_inventory` 파이프라인 미포함 |
| RTL File Map | ❌ | ⚠️ 부분 | 파일 경로 메타데이터 미보존 |
| Hierarchy Verification (pkg↔RTL) | ❌ | ❌ | 교차 파일 검증 Claim 없음 |
| Diff vs Baseline Trinity | ❌ | ❌ | 버전 비교 분석 Claim 없음 |

---

## 2. 시스템 파이프라인 구조 (현재 상태)

```
[RTL 소스 파일들]
    ├── used_in_n1/rtl/trinity.sv          (N1B0 Top)
    ├── used_in_n1/rtl/targets/4x5/        (N1B0 Package)
    ├── rtl/trinity.sv                     (Baseline)
    └── tt_rtl/tt_*/...                    (Generic Trinity Submodules)
         │
         ▼  [S3 Upload → Lambda RTL Parser]
    [Claim DB (DynamoDB)]
         ├── module_parse Claims           — 모듈 포트, 파라미터
         ├── hdd_section Claims            — 블록 레벨 설명
         ├── hierarchy Claims              — 인스턴스 관계
         └── (누락) package_constants, variant_diff, sram_inventory
         │
         ▼  [Lambda → OpenSearch 인덱싱]
    [OpenSearch Serverless]
         ├── 벡터: Titan Embeddings (1536-dim)
         └── 메타데이터: {topic, analysis_type, ...} ← 파일 경로, chip_variant 없음
         │
         ▼  [Obot → MCP Bridge → search_rtl 도구]
    [검색: topic/query 기반 단일 쿼리]
         │  ← 한 번에 1회 호출 강제 (JSON parse 버그)
         ▼
    [Claude 3.5 Haiku — 컨텍스트: top-k Claims]
         │
         ▼
    [HDD 생성 — 1회 생성]
         │  ← 언어 지시 없음, grounding 제약 없음
         ▼
    Trinity_N1B0_HDD_Complete_v1.md
    (Generic 60% + N1B0 40% + Hallucination)
```

---

## 3. 근본 원인 분석 (RCA) — 7계층

---

### Layer 1: 데이터 수집 계층

#### RCA-1-A: 파일 경로 컨텍스트 손실 — chip variant 식별 불가

**위치:** S3 오브젝트 메타데이터 → Lambda 파서

**현재 메타데이터 스키마:**
```json
{
  "x-amz-meta-document-type": "rtl",
  "x-amz-meta-source-system": "string"
}
```

**문제:**  
N1B0를 baseline Trinity 및 Generic 서브모듈과 구분하는 유일한 단서는 파일 경로입니다:

```
used_in_n1/rtl/trinity.sv           → N1B0 Top
used_in_n1/rtl/targets/4x5/...     → N1B0 4×5 variant
rtl/trinity.sv                      → Baseline
tt_rtl/tt_tensix_neo/...            → Generic (모든 variant 공유)
```

`chip_variant` 메타데이터가 없으므로 Claim이 OpenSearch에 저장될 때 N1B0와 baseline이 같은 의미 공간에 혼합 인덱싱됩니다. 쿼리 시 필터링 근거가 없어 Generic content가 구조적으로 더 많이 리트리브됩니다.

**영향도:** Critical — 모든 하위 계층의 품질을 결정

**개선안:**
```json
{
  "x-amz-meta-document-type": "rtl",
  "x-amz-meta-chip-variant": "N1B0",
  "x-amz-meta-rtl-path": "used_in_n1/rtl/",
  "x-amz-meta-pipeline-id": "tt_20260221",
  "x-amz-meta-file-role": "top|package|submodule|library",
  "x-amz-meta-baseline-relation": "override|extend|new|unchanged"
}
```

---

#### RCA-1-B: 다중 버전 파일 혼재 — 동일 모듈명 충돌

**현재 문제:**  
`trinity.sv`가 최소 4개 버전 존재합니다 (prompt.md Appendix A.1.5 확인):

| RTL 소스 | `i_dm_clk` | `i_ai_clk` 폭 |
|----------|------------|----------------|
| `rtl/trinity.sv` (Baseline) | Single | Single |
| `used_in_n1/rtl/trinity.sv` (N1B0) | Per-column `[SizeX-1:0]` | Per-column `[SizeX-1:0]` |
| `used_in_n1/mem_port/rtl/trinity.sv` | Per-column | Per-column |
| `used_in_n1/legacy/no_mem_port/rtl/trinity.sv` | ❌ 없음 | Single |

모두 `module trinity`로 시작하므로, 모듈명 기반 인덱싱 시 동일 키(`module=trinity`)로 충돌합니다. 검색 결과에 구버전 포트 정보가 혼입되어 `i_ai_clk`가 단일 비트(1-bit)로 잘못 기술됩니다.

**개선안:**  
인덱스 키를 `module_name`이 아닌 `{chip_variant}:{module_name}:{rtl_path_hash}`로 구성합니다.

---

### Layer 2: Claim 추출 계층

#### RCA-2-A: RTL 파라미터/상수 타입 미추출

**위치:** Lambda RTL Parser → Claim DB

**현재 추출 대상 (추정):**
```
✅ module ports (이름, 방향)
✅ module instantiation (계층 관계)
✅ hdd_section (블록 설명 텍스트)
❌ parameter / localparam 값
❌ typedef enum 정의
❌ localparam 배열 (GridConfig)
❌ typedef struct packed (trinity_clock_routing_t)
```

**실제 영향:**  
`trinity_pkg.sv`의 핵심 정보가 전혀 Claim으로 추출되지 않습니다:

```systemverilog
// trinity_pkg.sv — 이 파일 전체가 Claim에서 누락
parameter SizeX = 4;
parameter SizeY = 5;
localparam NumNodes = SizeX * SizeY;   // 20
localparam NumTensix = 12;

typedef enum logic [2:0] {
    TENSIX                = 3'd0,
    NOC2AXI_NE_OPT        = 3'd1,
    NOC2AXI_ROUTER_NE_OPT = 3'd2,
    ...
} tile_t;

// GridConfig[y][x] = ...  ← 20개 엔트리 전체 누락
// EndpointIndex = x*SizeY + y  ← 공식 누락
```

이것이 섹션 2 (Package Constants & Grid) 완전 누락의 직접 원인입니다.

**개선안:**  
`analysis_type: package_constants` 신규 파서 추가:
```python
def extract_package_constants(sv_file_content):
    claims = []

    # parameter / localparam 추출
    for match in re.finditer(r'(parameter|localparam)\s+(\w+)\s*=\s*([^;]+)', content):
        claims.append({
            "claim_type": "package_constant",
            "name": match.group(2),
            "value": match.group(3).strip(),
            "kind": match.group(1)
        })

    # typedef enum 추출
    for match in re.finditer(r'typedef enum.*?\{([^}]+)\}\s*(\w+)', content, re.DOTALL):
        entries = parse_enum_entries(match.group(1))
        claims.append({
            "claim_type": "enum_definition",
            "type_name": match.group(2),
            "entries": entries
        })

    # typedef struct 추출
    for match in re.finditer(r'typedef struct packed\s*\{([^}]+)\}\s*(\w+)', content, re.DOTALL):
        claims.append({
            "claim_type": "struct_definition",
            "type_name": match.group(2),
            "fields": parse_struct_fields(match.group(1))
        })

    return claims
```

---

#### RCA-2-B: 포트 폭(비트 수) 추출 누락

**현재 상태:**  
모듈 포트 Claim에 방향(`input`/`output`)과 이름만 추출되고, 비트 폭과 배열 인덱스가 없습니다.

**영향:**
```
현재 Claim: { "port": "i_ai_clk", "direction": "input" }
실제 정보:  { "port": "i_ai_clk", "direction": "input",
             "width": 1, "array": "[SizeX-1:0]", "N1B0_change": "was single-bit" }
```

per-column 배열(`[SizeX-1:0] = [3:0]`)이 단일 비트로 잘못 기술되는 원인입니다.

**개선안:**  
포트 파서에 `logic [W:0]`, `[PARAM-1:0]`, 배열 `[N]` 패턴 파싱 추가:
```python
def parse_port_width(port_declaration):
    # "[SizeX-1:0]"  → {"msb": "SizeX-1", "lsb": "0", "resolved_width": 4}
    # "[NumDmComplexes-1:0][DMCoresPerCluster-1:0]" → 2D array
    # "1"            → scalar
```

---

#### RCA-2-C: 교차 파일 관계 Claim 미생성

**위치:** Lambda RTL Parser

**핵심 문제:**  
N1B0의 가장 중요한 사실들은 단일 파일에 없고 **파일 간 관계**에서만 도출됩니다.

**예시 1 — `trinity_router` 미사용:**
```
trinity_pkg.sv:                  GridConfig[3][1] = ROUTER   ← "ROUTER 타입 존재"
trinity.sv:                      gen_router: begin /* EMPTY */ end  ← "실제 인스턴스 없음"
trinity_noc2axi_router_ne_opt.sv: // Y=3 router logic embedded here  ← "실제 위치"
```
→ 3개 파일을 동시에 분석해야 "N1B0에서 trinity_router는 인스턴스화되지 않는다"는 사실이 도출됨

**예시 2 — dual-row span:**
```
trinity.sv:                      gen_noc2axi_router_ne_opt: if (GridConfig[4][1] == ...)
trinity_noc2axi_router_ne_opt.sv: // noc2axi_i_* = Y=4, router_o_* = Y=3
```
→ 단일 모듈이 Y=4와 Y=3 두 물리적 행을 차지한다는 사실은 두 파일 교차 분석에서만 도출됨

**현재 파이프라인의 한계:**  
각 파일을 독립적으로 파싱하므로 이런 "inter-file reasoning" 결과가 Claim DB에 없습니다.

**개선안:**  
`analysis_type: cross_file_relationship` Claim 신규 추가:
```json
{
  "claim_type": "cross_file_relationship",
  "relationship": "override_unused",
  "subject_module": "trinity_router",
  "subject_file": "used_in_n1/rtl/trinity_router.sv",
  "evidence_file": "used_in_n1/rtl/trinity.sv",
  "evidence": "gen_router generate block is empty in N1B0",
  "superseded_by": "trinity_noc2axi_router_ne/nw_opt",
  "chip_variant": "N1B0"
}
```

---

#### RCA-2-D: SRAM Inventory 분석 타입 파이프라인 미포함

**현재 상태:**  
Compare_Report에서 "analysis_type이 파이프라인에 미포함"으로 명시된 항목입니다.

SRAM 인스턴스는 RTL 내에 다음 패턴으로 존재합니다:
```systemverilog
SFR_RF_2P_HSC_*  // 2-port HS SRAM
SFR_RA1_HS_*     // RA1 HS SRAM
SFR_RF1_HS_*     // RF1 HS SRAM
SFR_RF1_HD_*     // RF1 HD SRAM
```

파이프라인에 `analysis_type: sram_inventory` 분석기가 없어 메모리 구성 정보가 완전히 누락됩니다.

---

#### RCA-2-E: N1B0 vs Baseline 차이(diff) Claim 미생성

**현재 상태:**  
N1B0 특이사항(변경 목록)을 자동으로 추출하는 파이프라인이 없습니다.

정답지 Section 13은 이런 구조:
```
| Aspect                    | Baseline Trinity           | N1B0                          |
|---------------------------|----------------------------|-------------------------------|
| AI/DM clock               | Single                     | Per-column [SizeX]            |
| X-axis NoC                | Generate loop              | Manual assigns                |
| Inter-column repeaters    | None                       | 4-stage Y=4, 6-stage Y=3      |
| PRTN chain                | Not present                | 4-column daisy-chain          |
```

이 비교표는 baseline과 N1B0 파일을 **동시에** 파싱하고 diff 분석을 해야만 생성됩니다.

---

### Layer 3: 인덱싱 및 검색 계층

#### RCA-3-A: Generic content가 구조적으로 높은 유사도 획득

**메커니즘:**  
Titan Embeddings 벡터 공간에서, 여러 문서에 반복 등장하는 개념일수록 해당 임베딩이 공간의 더 중심적 위치를 차지합니다.

```
"trinity N1B0 clock architecture" 쿼리 시:

Generic tt_noc2axi.sv 청크:
  "i_axiclk, i_nocclk AXI/NoC clock domains..."
  → 수십 개 문서에 반복 → 임베딩 공간 중심 → cosine score: 0.78

N1B0 trinity.sv 청크:
  "i_ai_clk[SizeX-1:0] per-column clock array..."
  → 1개 파일에만 존재 → 임베딩 공간 외곽 → cosine score: 0.71
```

N1B0-specific 희귀 정보가 Generic 반복 정보에 의해 검색 순위에서 지속적으로 밀려납니다.

**개선안:**  
`chip_variant=N1B0` 메타데이터 필터를 검색 쿼리에 의무 적용:
```python
def search_rtl(query, topic=None, pipeline_id=None, chip_variant=None):
    filter_conditions = []
    if chip_variant:
        filter_conditions.append({"term": {"chip_variant": chip_variant}})
    # OpenSearch pre-filter로 N1B0 전용 문서만 검색
```

---

#### RCA-3-B: 단일 쿼리로 HDD 전체 커버 불가능

**현재 쿼리 전략:**
```
쿼리: "Trinity N1B0 HDD 전체"
top-k: ~10 청크
→ Claude에 전달 → 1,570줄 문서 생성
```

**문제:**  
HDD 17개 섹션이 각각 다른 종류의 질문에 답합니다:

| 섹션 | 필요한 검색 쿼리 유형 |
|------|----------------------|
| Package Constants | `"trinity_pkg SizeX SizeY GridConfig enum"` |
| Module Hierarchy | `"trinity.sv generate block instantiation"` |
| NoC X-axis Connections | `"manual assign repeater Y=3 Y=4"` |
| PRTN Chain | `"PRTNUN_FC2UN daisy chain power"` |
| Diff vs Baseline | `"N1B0 change per-column clock HPDF"` |

단일 `top-k=10` 쿼리로는 이 다양한 정보를 동시에 커버할 수 없습니다.

---

#### RCA-3-C: 검색 결과에 파일 경로 정보 미포함

**현재 상태:**  
`search_rtl` 결과로 반환되는 Claim에 소스 파일 경로가 없거나 있어도 LLM 컨텍스트에 전달되지 않습니다.

**영향:**  
Claude가 "이 정보가 N1B0 파일에서 온 것인가, Baseline 파일에서 온 것인가"를 구분할 수 없어 Generic 정보를 N1B0 정보로 오판합니다.

---

### Layer 4: 생성 계층

#### RCA-4-A: Knowledge Gap Filling — 사전 학습 지식으로 섹션 채우기

**메커니즘:**  
Claude 3.5 Haiku는 RAG에서 받은 컨텍스트에 정보가 없어도, "HDD에 있어야 할 것 같은" 섹션을 사전 학습 지식으로 생성합니다.

```
리트리브 결과에 "tt_fpu_v2"라는 모듈명 단 1회 언급
→ Claude: "FPU 섹션이 HDD에 필요하다"
→ FPU v2 상세 섹션을 사전 학습 기반으로 전체 생성
→ N1B0에 존재하지 않을 수 있는 내용이 HDD에 삽입됨
```

v1에 등장한 근거 없는 내용들:
- UCIe 블록 (N1B0 RTL에 존재 여부 미확인)
- TDMA 서브시스템 (Sample에 없음)
- P&R 수치 `3,519,581 포트`, `2.0 GHz`, `52.73% 활용률` (다른 Trinity 변형의 PD 보고서에서 혼입 추정)
- Appendix B, C, D 내용 대부분 "추정"으로 표시

**현재 시스템 프롬프트에 grounding 제약이 없습니다.** 이것이 Hallucination의 직접 원인입니다.

---

#### RCA-4-B: 사실 오류 — `trinity_router` 계층 역전

**오류 내용 (v1 Section 4):**
```
trinity (Top Module)
│
├── trinity_router   # NoC 라우터 (타일 레벨)  ← 잘못됨
│   └── (NoC 라우터 인스턴스들)
```

**정답:**
```
trinity (Top Module)
│
├── gen_router[x=1,2][y=3]: EMPTY  ← 인스턴스 없음
├── gen_noc2axi_router_ne_opt:
│   └── trinity_noc2axi_router_ne_opt  ← Y=4+Y=3 통합 (여기에 router 내장)
```

**이 오류의 원인:**  
`trinity_router.sv` 파일이 KB에 존재 → 청크 리트리브됨 → Claude가 "이 모듈이 trinity에 instantiate된다"고 판단. `gen_router` 블록이 비어있다는 정보가 동시에 리트리브되지 않았습니다.

---

#### RCA-4-C: 클럭 포트 배열 크기 오류

**오류 내용 (v1 Appendix A):**
```
i_ai_clk  Input  1  AI 연산 클럭
i_dm_clk  Input  1  Data Mover 클럭
```

**N1B0 정확한 정보:**
```
i_ai_clk  [SizeX-1:0] = [3:0]  Input  AI clock per column (4개)
i_dm_clk  [SizeX-1:0] = [3:0]  Input  DM clock per column (4개)
```

**원인:**  
RCA-2-B (포트 폭 미추출) + RCA-1-B (다중 버전 혼재)의 결합 효과. Baseline 버전의 `single i_ai_clk` Claim이 리트리브되어 N1B0 정보를 덮어씁니다.

---

### Layer 5: 툴링 및 MCP 계층

#### RCA-5-A: MCP 병렬 호출 JSON 파싱 버그

**위치:** Obot → MCP Bridge (`mcp-bridge/server.js`)

**증상 (prompt.md 기록):**
```
failed to unmarshal input: invalid character '{' after top-level value
```

**메커니즘:**  
Claude가 HDD의 여러 섹션을 위해 `search_rtl`을 여러 번 호출하려 할 때, Obot이 이를 동시에 실행하면서 JSON 스트림이 충돌합니다. 현재 임시 해결책으로 프롬프트에 "도구를 **한 번만** 호출해"를 명시하고 있습니다.

**영향:**  
단일 쿼리 강제로 인해 RCA-3-B (검색 전략 부재)가 해결되더라도 적용할 수 없습니다. 멀티-쿼리 전략의 기술적 전제 조건입니다.

**개선안:**
```javascript
// mcp-bridge/server.js 개선
// 순차 처리 큐 구현
const callQueue = [];
async function enqueueToolCall(toolName, args) {
    return new Promise((resolve) => {
        callQueue.push({ toolName, args, resolve });
        if (callQueue.length === 1) processQueue();
    });
}
```

---

#### RCA-5-B: `search_rtl` 도구 인터페이스 설계 한계

**현재 인터페이스:**
```
search_rtl(pipeline_id, topic?, query?)
→ Returns: Claims[]
```

**문제:**
1. `chip_variant` 파라미터 없음 → N1B0 전용 필터링 불가
2. `file_path` 파라미터 없음 → 특정 파일 직접 지정 불가
3. `exclude_variants` 파라미터 없음 → baseline/legacy 결과 제외 불가
4. 반환 결과에 소스 파일 경로 미포함 → LLM의 출처 구분 불가

**개선된 인터페이스:**
```
search_rtl(
    pipeline_id,           // 기존
    topic?,                // 기존
    query?,                // 기존
    chip_variant?,         // 신규: "N1B0" | "baseline" | "all"
    file_path?,            // 신규: 특정 파일 직접 지정
    claim_types?,          // 신규: ["package_constant", "port", "hierarchy"]
    include_source_path?   // 신규: 결과에 파일 경로 포함
)
```

---

### Layer 6: 프롬프트 설계 계층

#### RCA-6-A: 생성 언어 지시 부재

**현재 상태:**  
HDD 생성 프롬프트에 언어 지시가 없어, Obot 사용 언어(한국어)로 문서가 생성됩니다.

**영향:**  
HDD는 전사 엔지니어링 문서 표준으로 영어가 요구됩니다. 한국어로 생성된 문서는 RTL 시그널명, EDA 도구명과 뒤섞여 가독성이 저하되고 팀 외부 공유가 불가합니다.

**개선안:**
```
You MUST generate the HDD in English regardless of the query language.
RTL signal names, module names, and file paths must be quoted exactly as-is.
```

---

#### RCA-6-B: Grounding 제약 부재 — Hallucination 허용 구조

**현재 상태:**  
시스템 프롬프트에 리트리브된 컨텍스트 범위 내에서만 생성하라는 지시가 없습니다.

**영향:**  
Claude가 빈 섹션을 사전 학습 지식으로 채웁니다. "Complete HDD"라는 지시가 이 행동을 가속합니다.

**개선안:**
```
STRICT GROUNDING RULES:
1. Only include information explicitly present in the retrieved Claims.
2. If a section cannot be filled from the retrieved data, write:
   "⚠️ [NOT IN KB] — This section requires additional RTL parsing."
3. Do NOT infer or extrapolate from general semiconductor knowledge.
4. Every table entry must cite its source Claim ID.
5. Module instantiation hierarchy must be verified against
   actual 'generate block' analysis, not assumed from file existence.
```

---

#### RCA-6-C: 섹션 우선순위 및 의무 항목 미지정

**현재 상태:**  
프롬프트에 섹션 목록을 나열하지만, 어떤 섹션이 N1B0-specific이고 어떤 것이 공통인지 구분이 없습니다.

**영향:**  
Claude가 쉽게 채울 수 있는 섹션(Generic NoC, FPU 등)을 과도하게 기술하고, N1B0-specific 섹션(PRTN, HPDF 타일, per-column clock 변경사항)은 부실하게 처리합니다.

**개선안:**  
섹션을 3등급으로 분류:
```
[CRITICAL — N1B0 specific, must be accurate]
  - Package Constants & Grid (trinity_pkg.sv 기반)
  - N1B0 Module Hierarchy (HPDF 통합 타일)
  - Clock per-column 변경사항
  - PRTN Daisy Chain
  - NoC Repeater 배치 (Y=3: 6개, Y=4: 4개)
  - Diff vs Baseline Trinity

[IMPORTANT — shared but needs N1B0 values]
  - Top-Level Ports (정확한 비트 폭)
  - EDC Ring 토폴로지
  - Memory Config (SFR Ports)

[SUPPLEMENTARY — can use generic knowledge if KB empty]
  - Tensix 내부 구조 (FPU, SFPU)
  - DFX 개요
```

---

### Layer 7: 평가 계층

#### RCA-7-A: 자동화된 품질 검증 프레임워크 부재

**현재 상태:**  
생성된 HDD의 품질을 자동으로 검증하는 메커니즘이 없습니다. 엔지니어가 수동으로 Compare Report를 작성하고 있습니다.

**필요한 자동 검증 항목:**

| 검증 유형 | 방법 | 기준 |
|-----------|------|------|
| 필수 섹션 존재 여부 | 정규식 섹션 헤더 검사 | 17개 섹션 중 ≥14개 |
| 파라미터 수치 정확도 | RTL 파싱 결과와 대조 | SizeX=4, SizeY=5 등 |
| 모듈명 유효성 | KB의 알려진 모듈명 목록 대조 | 존재하지 않는 모듈명 검출 |
| Hallucination 탐지 | 생성 내용 → RTL KB 역검색 | "⚠️ NOT IN KB" 비율 |
| 언어 일관성 | 언어 감지 | 영어 비율 ≥ 95% |
| N1B0 특이성 | N1B0 키워드 밀도 | "per-column", "HPDF", "PRTN" 등 |

---

## 4. 실패 메커니즘 종합 다이어그램

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    RTL 소스 파일들
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  used_in_n1/rtl/trinity.sv (N1B0)
  used_in_n1/rtl/targets/4x5/trinity_pkg.sv (N1B0)
  rtl/trinity.sv (Baseline)
  tt_rtl/**/*.sv (Generic, 다수)
         │
         │  [RCA-1-A] chip_variant 메타데이터 없음
         │  [RCA-1-B] 동일 모듈명 다중 버전 충돌
         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                   Claim 추출 (Lambda Parser)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [RCA-2-A] parameter/enum/struct → ❌ 미추출
  [RCA-2-B] 포트 비트 폭/배열 → ❌ 미추출
  [RCA-2-C] 교차 파일 관계 → ❌ Claim 없음
  [RCA-2-D] SRAM Inventory → ❌ analysis_type 없음
  [RCA-2-E] N1B0 vs Baseline diff → ❌ 파이프라인 없음
         │
         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              OpenSearch 인덱싱 및 검색
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [RCA-3-A] Generic content > N1B0-specific score
            (반복 등장 → 임베딩 공간 중심 위치)
  [RCA-3-B] 단일 쿼리 → 17섹션 커버 불가
  [RCA-3-C] 소스 파일 경로 검색 결과에 미포함
         │
         │ top-k Claims (N1B0: 소수, Generic: 다수)
         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
               MCP Bridge / Tooling
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [RCA-5-A] 병렬 호출 JSON 파싱 버그
            → 단일 쿼리 강제 (임시 해결)
  [RCA-5-B] chip_variant 필터 파라미터 없음
            → Generic Claims 필터링 불가
         │
         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Claude 3.5 Haiku (생성)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  컨텍스트: Generic Claims 다수 + N1B0 Claims 소수
  프롬프트: "Complete HDD 작성" + 언어 지시 없음 + Grounding 없음

  [RCA-4-A] Knowledge Gap Filling
            → FPU, UCIe, TDMA 섹션 사전학습 기반 생성
            → P&R 수치 다른 변형에서 혼입
  [RCA-4-B] trinity_router 미사용 사실 역전 오류
  [RCA-4-C] i_ai_clk 단일 비트로 잘못 기술
  [RCA-6-A] 한국어로 생성 (언어 지시 없음)
  [RCA-6-B] Grounding 제약 없음 → Hallucination
  [RCA-6-C] N1B0-specific 섹션 우선순위 없음
         │
         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              생성된 HDD (현재 품질)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  N1B0-specific: ~40%    ← 목표: ≥ 90%
  Generic Trinity: ~40%  ← 목표: ≤ 5%
  Hallucination: ~20%    ← 목표: ≤ 5%
  섹션 커버리지: 41%     ← 목표: ≥ 85%

  [RCA-7-A] 자동 품질 검증 없음 → 수동 비교만 가능
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 5. 개선 로드맵

### Phase 0 — 즉시 적용 (1주 이내, 코드 변경 최소)

| ID | 항목 | 변경 위치 | 기대 효과 |
|----|------|-----------|-----------|
| F0-1 | 생성 프롬프트에 grounding 제약 추가 | Obot 시스템 프롬프트 | Hallucination ~20% → ~8% |
| F0-2 | 생성 언어 영어 강제 | Obot 시스템 프롬프트 | 언어 오류 제거 |
| F0-3 | 섹션별 분할 쿼리 적용 | prompt.md 개선 | 섹션 커버리지 +15% |
| F0-4 | "N1B0" 키워드를 모든 쿼리에 포함 | prompt.md | Generic 리트리브 감소 |
| F0-5 | `trinity_router` 미사용 명시 지시 | HDD 생성 프롬프트 | 계층 오류 제거 |

**F0-3 구체적 실행 (섹션별 순차 쿼리):**
```
프롬프트 1: "search_rtl으로 'trinity_pkg N1B0 SizeX SizeY GridConfig' 검색 후
             Package Constants 섹션만 작성해줘"
프롬프트 2: "search_rtl으로 'trinity.sv N1B0 generate block instantiation' 검색 후
             Module Hierarchy 섹션만 작성해줘"
프롬프트 3: "search_rtl으로 'PRTNUN FC2UN N1B0 daisy chain' 검색 후
             PRTN Chain 섹션만 작성해줘"
...
```

---

### Phase 1 — 단기 (2~4주, 인프라 변경 필요)

#### P1-1: MCP 병렬 호출 버그 수정 (RCA-5-A)
```
파일: mcp-bridge/server.js
변경: 도구 호출 순차 처리 큐 구현
검증: 2회 연속 search_rtl 호출 → JSON 파싱 오류 없음
```

#### P1-2: S3 메타데이터 스키마 확장 (RCA-1-A, RCA-1-B)
```
파일: environments/app-layer/bedrock-rag/lambda.tf
변경: S3 업로드 시 chip_variant, rtl_path, file_role 태그 추가
Lambda: document-processor에서 파일 경로 파싱 → 메타데이터 자동 태깅
```

#### P1-3: `search_rtl` 도구 chip_variant 파라미터 추가 (RCA-5-B)
```
파일: mcp-bridge/server.js, Lambda rag query handler
변경: chip_variant 필터를 OpenSearch 쿼리에 pre-filter 조건으로 추가
```

#### P1-4: 포트 비트 폭 Claim 추출 추가 (RCA-2-B)
```
파일: lambda/document-processor/handler.py
변경: 포트 선언 파서에 width/array 패턴 추가
      "[SizeX-1:0]", "[NumTensix-1:0]", "logic [W:0]" 추출
```

---

### Phase 2 — 중기 (1~2개월, 파이프라인 확장)

#### P2-1: package_constants 분석 타입 추가 (RCA-2-A)
```
신규 파서: extract_package_constants()
추출 대상: parameter, localparam, typedef enum, typedef struct packed
저장 형식: Claim {claim_type: "package_constant", name, value, chip_variant}
```

#### P2-2: 교차 파일 관계 Claim 생성 (RCA-2-C)
```
신규 분석: cross_file_relationship_analyzer()
분석 방법:
  1. 모든 N1B0 파일의 인스턴스 목록 추출
  2. 파일로 존재하는데 인스턴스화되지 않는 모듈 탐지
  3. generate block이 비어있는 케이스 탐지
  4. "X는 Y에 의해 대체되었다" 관계 Claim 생성
```

#### P2-3: variant_diff 분석 추가 (RCA-2-E)
```
신규 분석: variant_diff_analyzer(baseline_path, variant_path)
출력: Claim {claim_type: "variant_diff", aspect, baseline_value, variant_value}
예시: {aspect: "ai_clk_width", baseline: "1-bit single",
       N1B0: "[SizeX-1:0] per-column array"}
```

#### P2-4: sram_inventory 분석 추가 (RCA-2-D)
```
신규 파서: extract_sram_inventory()
추출 대상: SFR_RF_2P_*, SFR_RA1_*, SFR_RF1_* 등 SRAM 매크로 인스턴스
저장 형식: Claim {claim_type: "sram_instance", macro_type, location, width, depth}
```

#### P2-5: 멀티-쿼리 HDD 생성 파이프라인 (RCA-3-B)
```
신규 Lambda: hdd_generator_lambda
동작: 섹션별 search_rtl 순차 호출 → 각 섹션 생성 → 통합
섹션별 쿼리 전략 템플릿:
  {
    "package_constants": {
      "query": "trinity_pkg SizeX SizeY GridConfig enum",
      "chip_variant": "N1B0"
    },
    "module_hierarchy": {
      "query": "trinity.sv generate block N1B0 instantiation",
      "chip_variant": "N1B0"
    },
    "clock_structure": {
      "query": "per-column clock i_ai_clk array N1B0 change",
      "chip_variant": "N1B0"
    },
    "prtn_chain": {
      "query": "PRTNUN FC2UN daisy chain power management",
      "chip_variant": "N1B0"
    },
    "noc_connections": {
      "query": "manual assign repeater Y=3 Y=4 N1B0",
      "chip_variant": "N1B0"
    },
    "variant_diff": {
      "query": "N1B0 vs baseline Trinity change HPDF",
      "chip_variant": "N1B0"
    }
  }
```

---

### Phase 3 — 장기 (2~3개월, 검증 시스템 구축)

#### P3-1: HDD 자동 품질 검증 (RCA-7-A)
```
신규 Lambda: hdd_quality_validator
검증 항목:
  □ 섹션 커버리지 (정규식 기반)
  □ 필수 파라미터 존재 (SizeX=4, SizeY=5, NumTensix=12)
  □ 모듈명 유효성 (KB 역검색)
  □ Hallucination 탐지 (생성 내용 → RTL KB 역검색 후 미매칭 비율)
  □ 언어 일관성
  □ N1B0 특이성 키워드 밀도
출력: quality_score (0~100) + 상세 리포트
```

#### P3-2: 피드백 루프 — Claim 품질 자동 개선
```
구조: HDD 생성 → 엔지니어 리뷰 → 오류/누락 태그 → Claim DB 보강
     오류 패턴 누적 → Lambda 파서 자동 개선 제안 생성
```

---

## 6. 평가 프레임워크

### 6.1 섹션별 채점 기준

| 섹션 | 가중치 | 채점 기준 |
|------|--------|----------|
| Package Constants & Grid | 15% | SizeX/Y, NumTensix, tile_t enum 8종, GridConfig 20개, EndpointIndex 공식 |
| Top-Level Ports | 10% | 핵심 포트 비트 폭, per-column 배열 명시 |
| Module Hierarchy (N1B0) | 15% | trinity_router 미사용 명시, HPDF 통합 타일, dual-row span |
| NoC Connections | 10% | manual assign 명시, Y=3 6-stage, Y=4 4-stage 리피터 |
| Clock Routing | 10% | trinity_clock_routing_t, per-column 구조, NOC2AXI_ROUTER_*_OPT 예외 |
| PRTN Chain | 10% | 4-column daisy-chain, 포트 목록 |
| Memory Config (SFR) | 5% | SFR_RF_2P_*, SFR_RA1_* 타입별 수신 타일 |
| EDC Ring | 5% | flat array, index 공식, column-wise chain |
| Dispatch Feedthrough | 5% | de_to_t6 구조 |
| RTL File Map | 5% | 모듈↔파일 매핑 |
| Diff vs Baseline | 10% | 8개 이상 변경사항 기술 |

### 6.2 Hallucination 탐지 기준

```
HIGH RISK (즉시 플래그):
  - trinity 상위 모듈에 UCIe 블록 인스턴스 (N1B0 RTL 미확인)
  - TDMA 서브시스템 (Sample에 없음)
  - P&R 수치 (다른 변형 PD 보고서 혼입)
  - "추정" 레지스터 맵 오프셋

MEDIUM RISK (검증 필요):
  - trinity_router가 trinity에 직접 instantiate됨
  - i_ai_clk 단일 비트 선언
  - 5개를 초과하는 독립 클럭 도메인 기술
```

### 6.3 목표 품질 지표 (Phase 완료 시점별)

| 항목 | 현재 (v2) | Phase 1 목표 | Phase 2 목표 |
|------|-----------|--------------|--------------|
| 섹션 커버리지 | 59% | 70% | 85% |
| 파라미터 정확도 | ~25% | ~45% | ≥ 70% |
| Hallucination 비율 | ~20% | ~10% | ≤ 5% |
| N1B0 특이성 | ~55% | ~70% | ≥ 90% |
| 언어 일관성 | ~60% | 100% | 100% |
| 자동 검증 커버리지 | 0% | 30% | 80% |

---

## 부록: RCA 요약 테이블

| RCA ID | 계층 | 원인 | 영향 섹션 | 우선순위 |
|--------|------|------|-----------|----------|
| RCA-1-A | 데이터 수집 | chip_variant 메타데이터 없음 | 전체 | P0 |
| RCA-1-B | 데이터 수집 | 다중 버전 모듈명 충돌 | 포트, 계층 | P1 |
| RCA-2-A | Claim 추출 | parameter/enum/struct 미추출 | Package Constants | P0 |
| RCA-2-B | Claim 추출 | 포트 비트 폭 미추출 | Top-Level Ports | P1 |
| RCA-2-C | Claim 추출 | 교차 파일 관계 Claim 없음 | 계층, trinity_router | P1 |
| RCA-2-D | Claim 추출 | SRAM Inventory 파이프라인 없음 | SRAM Inventory | P2 |
| RCA-2-E | Claim 추출 | variant diff 분석 없음 | Diff vs Baseline | P2 |
| RCA-3-A | 검색 | Generic > N1B0 유사도 | 전체 N1B0 특이성 | P1 |
| RCA-3-B | 검색 | 단일 쿼리 전략 | 전체 섹션 커버리지 | P1 |
| RCA-3-C | 검색 | 소스 경로 미포함 | 출처 혼동, 오류 | P1 |
| RCA-4-A | 생성 | Knowledge Gap Filling | Hallucination | P0 |
| RCA-4-B | 생성 | trinity_router 계층 역전 | Module Hierarchy | P0 |
| RCA-4-C | 생성 | 클럭 배열 폭 오류 | Clock Architecture | P0 |
| RCA-5-A | MCP | 병렬 호출 JSON 버그 | 멀티-쿼리 전략 차단 | P1 |
| RCA-5-B | MCP | chip_variant 필터 파라미터 없음 | Generic 필터링 불가 | P1 |
| RCA-6-A | 프롬프트 | 언어 지시 없음 | 한국어 생성 | P0 |
| RCA-6-B | 프롬프트 | Grounding 제약 없음 | Hallucination | P0 |
| RCA-6-C | 프롬프트 | 섹션 우선순위 없음 | N1B0 특이성 희석 | P0 |
| RCA-7-A | 평가 | 자동 품질 검증 없음 | 수동 의존 | P2 |

---

*작성: Claude Sonnet 4.6 (1M context) — 2026-04-22*  
*기반 분석 자료: N1B0_HDD_v0.1.md, Trinity_N1B0_HDD_Complete_v1.md, Compare_Report_01_vs_Sample_HDD.md, prompt.md*
