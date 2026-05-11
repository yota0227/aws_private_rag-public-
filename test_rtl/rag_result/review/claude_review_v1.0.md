# RAG HDD 자동 생성 품질 저하 — 통합 근본 원인 분석 및 개선 로드맵

**문서 ID:** REVIEW-RAG-HDD-INTEGRATED-001  
**버전:** v1.0  
**작성일:** 2026-04-22  
**이전 버전:** claude_review_v0.1, kiro_review_v0.1, obot_review_v0.1 통합

---

## 분석 플랫폼 및 관점

이 문서는 **동일한 LLM(Claude 3.5 Haiku/Sonnet)**을 사용하되, 서로 다른 접근 방식으로 수행된 3건의 독립 리뷰를 통합한 것이다.

| 플랫폼 | 리뷰 파일 | 접근 방식 | 고유 관찰 |
|--------|-----------|-----------|-----------|
| **Claude Code** (CLI) | `claude_review_v0.1.md` | RTL 파일 직접 읽기, 코드 구조 분석, 시스템 아키텍처 전체 조망 | MCP 병렬 호출 버그, S3 메타데이터 설계, 7계층 RCA 구조화 |
| **Kiro** (IDE) | `kiro_review_v0.1.md` | 실제 파서 코드 열람, 이미 해결된 항목 파악, 개발 환경 통합 관점 | chip_config 분석 완료 상태 반영, PyVerilog AST 전환 가능성 식별 |
| **Obot** (챗봇) | `obot_review_v0.1.md` | search_rtl 도구 직접 실행, 8회 검색 실험, 실제 운영 데이터 수집 | Claim 모듈 귀속 오류 발견, 검색 건수 5건 제한, 실험 기반 커버리지 측정 |

세 플랫폼의 리뷰가 **서로 다른 각도에서 동일한 근본 문제를 가리키고 있다**는 것이 핵심 발견이다.

---

## 목차

1. [핵심 진단 (Executive Summary)](#1-핵심-진단)
2. [현황 정량 지표](#2-현황-정량-지표)
3. [시스템 파이프라인 현재 상태](#3-시스템-파이프라인-현재-상태)
4. [근본 원인 분석 — 8계층 21개 항목](#4-근본-원인-분석--8계층-21개-항목)
5. [플랫폼별 고유 발견 사항](#5-플랫폼별-고유-발견-사항)
6. [실험 기반 근거 데이터](#6-실험-기반-근거-데이터)
7. [통합 개선 로드맵](#7-통합-개선-로드맵)
8. [평가 프레임워크](#8-평가-프레임워크)
9. [RCA 요약 테이블](#9-rca-요약-테이블)

---

## 1. 핵심 진단

### 1.1 한 문장 요약

> 현재 RAG 시스템은 **"RTL에 대해 이야기하는"** 수준이지, **"RTL을 정밀하게 분석하는"** 수준이 아니다. 엔지니어 원본의 80% 이상은 `trinity_pkg.sv`와 `trinity.sv` 두 파일을 직접 파싱해야만 추출되는 정보인데, 현재 파이프라인은 이 수준의 구조적 파싱을 지원하지 않는다.

### 1.2 3개 리뷰의 공통 결론

3개 플랫폼이 서로 독립적으로 도달한 동일한 결론:

```
[Claude Code 결론]  RTL 파서가 parameter/enum/struct/generate/assign을 추출하지 못함
[Kiro 결론]        RTL 파싱 가능성 85%이나 현재 커버리지 50% — 파서 확장이 핵심
[Obot 결론]        8회 검색, 유효 Claim ~15건 / 필요 데이터 200+ — 데이터 자체가 없음

                           ↓ 공통 결론
      "Claim 추출 계층이 RTL 구조의 핵심 정보를 파싱하지 못하는 것이 1차 원인"
```

### 1.3 플랫폼이 추가로 발견한 고유 문제

- **Claude Code만 발견**: MCP 병렬 호출 JSON 버그 → 멀티-쿼리 전략 구조적 차단
- **Kiro만 발견**: chip_config 분석이 이미 완료됨 → Package Constants 일부 해결 가능 상태
- **Obot만 발견**: Claim이 `trinity_noc2axi_router_ne_opt_FBLC` 모듈에 **오귀속**되어 FPU/Overlay 위치 왜곡

---

## 2. 현황 정량 지표

### 2.1 품질 측정 (3개 리뷰 통합)

| 측정 항목 | 정답지 | v1 (Obot) | v2 (Obot) | Kiro 평가 | 목표 |
|-----------|--------|-----------|-----------|-----------|------|
| 섹션 커버리지 | 13~17/17 | ~7/17 (41%) | 10/17 (59%) | 50% (chip_config 반영) | ≥ 85% |
| 파라미터/수치 정확도 | 높음 | 낮음 | ~25% | ~40% (일부 해결) | ≥ 70% |
| N1B0-specific 정보 비율 | 100% | ~40% | ~55% | ~55% | ≥ 90% |
| Hallucination 비율 | 0% | ~40% | ~20% | ~15% | ≤ 5% |
| Claim 모듈 귀속 정확도 | — | ~50% | ~50% | ~50% | ≥ 95% |
| 실제 검색 데이터 커버리지 | — | — | ~7~13% | — | ≥ 60% |

> **Obot 실험 수치**: 8회 검색으로 유효 Claim ~15건 획득. 정답지 재현에 필요한 데이터포인트 200+. 실질 데이터 커버리지 **7.5%**.

### 2.2 섹션별 커버리지 매트릭스 (3개 리뷰 통합)

| # | 정답지 섹션 | v1 | v2 | Kiro | Obot 심각도 | 1차 원인 |
|---|-----------|----|----|------|-------------|----------|
| §1 | Overview | ⚠️ | ✅ | ✅ | 🟢 | 일부 완성 |
| §2 | Package Constants & Grid | ❌ | ❌ | ✅* | 🔴 | enum/struct 파싱 미지원 |
| §3 | Top-Level Ports (정확한 폭) | ❌ | ⚠️ | ⚠️ | 🔴 | 포트 비트폭 추출 없음 |
| §4 | Module Hierarchy | ❌오류 | ⚠️ | ⚠️ | 🔴 | generate 블록 분석 없음 |
| §5 | NoC Fabric Connections | ❌ | ⚠️ | ⚠️ | 🔴 | assign 추적 없음 |
| §6 | Clock Routing Structure | ❌ | ⚠️ | ⚠️ | 🔴 | struct 파싱 + assign 추적 없음 |
| §7 | EDC Ring | ❌ | ⚠️ | ✅* | 🔴 | assign 인덱스 매핑 없음 |
| §8 | Dispatch Feedthrough | ❌ | ⚠️ | ⚠️ | 🔴 | assign 추적 없음 |
| §9 | PRTN Daisy Chain | ❌ | ❌ | ❌ | 🔴 | Power 토픽/Claim 없음 |
| §10 | Memory Config (SFR) | ❌ | ❌ | ❌ | 🔴 | SFR 포트 추출 없음 |
| §11 | RTL File Map | ❌ | ⚠️ | ✅ | 🟡 | 파일 경로 일부 미포함 |
| §12 | Hierarchy Verification | ❌ | ❌ | ❌ | 🔴 | 교차 파일 검증 없음 |
| §13 | Diff vs Baseline | ❌ | ❌ | ⚠️* | 🔴 | variant_diff 파이프라인 없음 |

*Kiro ✅: chip_config 분석으로 이미 해결됨  
*Kiro ⚠️*: variant_delta 구현됨, baseline RTL 업로드 필요

---

## 3. 시스템 파이프라인 현재 상태

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RTL 소스 파일 (S3 업로드)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  used_in_n1/rtl/trinity.sv         — N1B0 Top
  used_in_n1/rtl/targets/4x5/       — N1B0 Package (trinity_pkg.sv)
  rtl/trinity.sv                    — Baseline (모듈명 동일!)
  tt_rtl/tt_*/...                   — Generic Trinity (다수)
        │
        │  chip_variant 메타데이터 없음 → 모두 같은 namespace로 혼합 인덱싱
        ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Lambda RTL Parser → Claim DB (DynamoDB)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  현재 추출 가능:
    ✅ module_parse  — 포트 이름/방향 (비트폭 없음)
    ✅ hdd_section   — 블록 설명 (86건, 단일 모듈 편중)
    ✅ hierarchy     — 1단계 인스턴스 관계
    ✅ chip_config   — pkg 파라미터 (Kiro: 일부 해결)
    ✅ edc_topology  — EDC 링 (Kiro: 해결)
    ✅ noc_protocol  — NoC Claim

  현재 추출 불가:
    ❌ generate 블록 조건부 인스턴스화 (핵심 누락)
    ❌ assign 문 기반 와이어 연결 추적
    ❌ typedef struct packed 내부 필드
    ❌ 포트 배열 비트폭 ([SizeX-1:0] 등)
    ❌ PRTN/ISO_EN 포트 그룹
    ❌ SFR 포트 그룹
    ❌ sram_inventory
    ❌ variant_diff (N1B0 vs Baseline)
    ❌ cross_file_relationship
        │
        ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  OpenSearch Serverless (벡터 인덱스)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - Titan Embeddings (1536-dim)
  - 메타데이터: {topic, analysis_type} — chip_variant 없음
  - Generic content가 구조적으로 더 높은 cosine score 획득
  - 반환 건수: top-k=5 고정 (전체의 7~13%만 조회 가능)
        │
        ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  MCP Bridge (mcp-bridge/server.js)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - search_rtl(pipeline_id, topic?, query?) — chip_variant 파라미터 없음
  - 병렬 호출 시 JSON 파싱 버그 → 단일 쿼리 강제
  - 결과에 소스 파일 경로 미포함
        │
        ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Obot → Claude 3.5 Haiku (HDD 생성)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - 언어 지시 없음 → 한국어 생성
  - Grounding 제약 없음 → Knowledge Gap Filling (Hallucination)
  - 섹션 우선순위 없음 → Generic 내용으로 부풀려짐
  - 단일 쿼리 강제 → 17섹션 커버 불가
        │
        ▼
  생성된 HDD: N1B0-specific ~40% / Generic ~40% / Hallucination ~20%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 4. 근본 원인 분석 — 8계층 21개 항목

---

### Layer 1: 데이터 수집 계층

#### RCA-1-A: chip_variant 메타데이터 없음 — N1B0 식별 불가
**플랫폼:** Claude Code 주도 발견

**현재:**
```json
{ "x-amz-meta-document-type": "rtl", "x-amz-meta-source-system": "string" }
```

**문제:** N1B0와 Baseline을 구분하는 유일한 단서는 파일 경로인데, 이 정보가 메타데이터에 없어 OpenSearch에서 N1B0 전용 필터링이 불가능하다. 모든 Trinity variant의 Claims가 동일한 벡터 공간에 혼합 인덱싱된다.

**개선안:**
```json
{
  "x-amz-meta-chip-variant": "N1B0",
  "x-amz-meta-rtl-path": "used_in_n1/rtl/",
  "x-amz-meta-pipeline-id": "tt_20260221",
  "x-amz-meta-file-role": "top|package|submodule|library",
  "x-amz-meta-baseline-relation": "override|extend|new|unchanged"
}
```

---

#### RCA-1-B: 동일 모듈명 다중 버전 충돌
**플랫폼:** Claude Code + Obot 교차 확인

`trinity.sv`가 최소 4개 버전으로 존재하며 모두 `module trinity`로 시작:

| RTL 소스 | i_ai_clk 폭 | i_dm_clk |
|----------|-------------|----------|
| `rtl/trinity.sv` (Baseline) | Single (1-bit) | Single |
| `used_in_n1/rtl/trinity.sv` (N1B0) | `[SizeX-1:0]` (4-bit) | Per-column |
| `used_in_n1/mem_port/rtl/trinity.sv` | Per-column | Per-column |
| `used_in_n1/legacy/no_mem_port/rtl/trinity.sv` | Single | ❌ 없음 |

Baseline의 `single i_ai_clk` Claim이 N1B0 Claim을 덮어써서 v1에서 `i_ai_clk Input 1`로 잘못 기술된다.

**개선안:** 인덱스 키를 `{chip_variant}:{module_name}:{rtl_path_hash}`로 구성

---

### Layer 2: Claim 추출 계층 — RTL 구조 파싱의 핵심 갭

#### RCA-2-A: parameter/localparam/enum/struct 미추출
**플랫폼:** Claude Code + Kiro + Obot 3개 일치

**현재 추출 대상:**
```
✅ module ports (이름, 방향만)
✅ module instantiation
✅ hdd_section (설명 텍스트)
❌ parameter / localparam 값
❌ typedef enum 정의 (tile_t 8종)
❌ typedef struct packed (trinity_clock_routing_t)
❌ GridConfig 2D 배열 (20개 엔트리)
```

**직접 영향:** `trinity_pkg.sv` 전체가 사실상 Claim DB에 없는 상태. 정답지 §2 완전 누락의 직접 원인.

```systemverilog
// 이 모든 정보가 Claim으로 추출되지 않음
parameter SizeX = 4;
localparam NumTensix = 12;
typedef enum logic [2:0] { TENSIX=3'd0, NOC2AXI_NE_OPT=3'd1, ... } tile_t;
typedef struct packed { logic ai_clk; logic noc_clk; ... } trinity_clock_routing_t;
```

**개선안:** `analysis_type: package_parse` 신규 파서:
```python
def extract_package_constants(sv_content):
    # parameter/localparam 추출
    # typedef enum { ... } type_name 추출
    # typedef struct packed { ... } type_name 추출
    # GridConfig 2D 배열 파싱
```

---

#### RCA-2-B: 포트 비트폭/배열 인덱스 미추출
**플랫폼:** Claude Code + Obot 2개 일치

**현재 Claim vs 필요 정보:**

| 포트 | 현재 Claim | 필요 정보 |
|------|-----------|-----------|
| `i_ai_clk` | `input i_ai_clk` | `input [SizeX-1:0] i_ai_clk` → 4-bit per-column |
| `i_tensix_reset_n` | `input i_tensix_reset_n` | `input [NumTensix-1:0]` → 12-bit per-tile |
| `i_dm_core_reset_n` | 미출력 | `input [NumDmComplexes-1:0][DMCoresPerCluster-1:0]` → 14×8 2D |
| `ISO_EN` | 미출력 | `input [11:0] ISO_EN` |

**Obot 개선안 (구조화된 JSON 형태):**
```json
{
  "name": "i_ai_clk",
  "direction": "input",
  "type": "logic",
  "width": "[SizeX-1:0]",
  "resolved_width": 4,
  "description": "AI clock per column (N1B0 change from single-bit)"
}
```

---

#### RCA-2-C: generate 블록 분석 미지원
**플랫폼:** Obot 주도 발견, Claude Code 보강

**핵심 문제:**  
`trinity.sv`의 `generate for`/`generate case` 블록이 어떤 조건에서 어떤 모듈을 인스턴스화하는지 추출할 수 없다. **N1B0의 핵심 설계 의도가 generate 블록의 비어있는 case에서 드러난다.**

```systemverilog
// RAG가 이 구조를 분석하지 못함:
generate
  for (genvar x = 0; x < SizeX; x++) begin
    for (genvar y = 0; y < SizeY; y++) begin
      case (GridConfig[y][x])
        NOC2AXI_ROUTER_NE_OPT: begin : gen_noc2axi_router_ne_opt
          trinity_noc2axi_router_ne_opt #(...) u_inst (...);
          // Y=4 AND Y=3 ports connected here (dual-row span)
        end
        ROUTER: begin : gen_router
          // EMPTY — router logic inside NOC2AXI_ROUTER_*_OPT
          // 이것이 N1B0의 핵심 변경사항
        end
      endcase
    end
  end
endgenerate
```

**이 분석 없이 발생하는 오류:** v1에서 `trinity_router`가 trinity에 직접 instantiate되는 것으로 역전 기술.

**개선안:** `analysis_type: generate_analysis`:
- generate 조건(case/if) + 인스턴스 모듈명 + 좌표(x,y) 매핑
- **EMPTY generate block 감지** (설계 의도 보존)
- dual-row span 자동 탐지 (`y`와 `y-1` 포트 동시 연결 패턴)

---

#### RCA-2-D: assign 문 / 와이어 연결 추적 미지원
**플랫폼:** Obot 주도 발견

**영향 범위:** 정답지 §5~§8 총 4개 섹션 (~30%)이 이 정보로 구성된다.

```systemverilog
// 이 패턴들을 RAG가 추적하지 못함:

// NoC Y축 연결
assign flit_in_req[x][y][POSITIVE][Y_AXIS] = flit_out_req[x][y+1][NEGATIVE][Y_AXIS];

// 클럭 전파
assign clock_routing_in[x][y] = clock_routing_out[x][y+1];

// N1B0 X축 manual assign (기존 generate loop를 교체)
// Y=4: [0][4]↔[1][4] direct, [1][4]↔[2][4] via 4-stage repeaters
// Y=3: [0][3]↔[1][3] direct, [1][3]↔[2][3] via 6-stage repeaters
assign flit_in_req[1][4][NEGATIVE][X_AXIS] = ...repeater_output...;

// EDC 체인
tt_edc1_intf_connector edc_direct_conn_nodes[...] (...);
```

**개선안:** `analysis_type: connectivity_trace`:
- 배열 인덱스 기반 연결 패턴 추출 (`[x][y]` → `[x][y+1]`)
- **manual assign vs generate loop 차이 탐지** (N1B0 변경 식별의 핵심)
- Repeater 삽입 위치 자동 감지

---

#### RCA-2-E: Claim 모듈 귀속 오류
**플랫폼:** Obot 단독 발견 (실험으로만 확인 가능)

**현상:**
- FPU Claim이 `trinity_noc2axi_router_ne_opt_FBLC` 모듈에 귀속
- Overlay Claim도 동일 모듈에 귀속
- 실제 FPU(`tt_fpu_v2`)는 Tensix 코어 내부 → NIU/Router와 무관

**결과:** v2 문서에서 FPU가 NIU 내부 서브시스템으로 잘못 기술되는 직접 원인.

**원인 추정:** HDD 자동 생성 시 `trinity_noc2axi_router_ne_opt_FBLC`를 anchor 모듈로 삼아 모든 토픽의 HDD를 생성한 것으로 보인다. 토픽과 실제 모듈의 매핑 검증 단계가 없다.

**올바른 귀속 구조:**
```
tt_fpu_v2 → topic: FPU, parent: tt_instrn_engine → tt_tensix_with_l1 → trinity
tt_sfpu_wrapper → topic: SFPU, parent: tt_instrn_engine
trinity_noc2axi_router_ne_opt → topic: NIU, parent: trinity (Y=4 row)
```

**개선안:** Claim 생성 시 실제 모듈 계층 위치 기반 귀속 + HDD 섹션 생성 시 모듈-토픽 매핑 검증 단계 추가

---

#### RCA-2-F: 누락된 분석 타입 — PRTN, SFR, SRAM, variant_diff
**플랫폼:** 3개 리뷰 일치

| 누락 analysis_type | 영향 섹션 | 현재 상태 |
|-------------------|-----------|-----------|
| `prtn_power` | §9 PRTN Daisy Chain | 토픽/Claim 전혀 없음 |
| `sfr_port_group` | §10 Memory Config | 검색 결과에 미등장 |
| `sram_inventory` | §13 (별도 섹션) | 파이프라인 미포함 |
| `variant_diff` | §13 Diff vs Baseline | 구현됨, baseline RTL 업로드 필요 |

---

### Layer 3: 인덱싱 및 검색 계층

#### RCA-3-A: Generic content 구조적 우위 — 빈도 편향
**플랫폼:** Claude Code 주도 발견

Titan Embeddings 벡터 공간에서 반복 등장하는 Generic 내용이 임베딩 공간의 중심에 위치해 N1B0-specific 희귀 내용보다 cosine score가 높다.

```
"trinity N1B0 clock" 쿼리 예시:
  Generic 청크 (수십 파일 반복) → cosine score ~0.78
  N1B0 전용 청크 (1개 파일만) → cosine score ~0.71
```

N1B0-specific 정보가 구조적으로 Generic에 밀려나는 벡터 공간 문제다.

---

#### RCA-3-B: 검색 반환 건수 5건 제한
**플랫폼:** Obot 단독 발견 (실험 데이터 기반)

**실험 결과:**

| 토픽 | 전체 Claim 수 | 반환 수 | 실제 커버리지 |
|------|-------------|---------|-------------|
| EDC | 37건 | 5건 | 13.5% |
| NoC | 40건 | 5건 | 12.5% |
| Dispatch | 76건 | 5건 | 6.6% |
| noc2axi (query) | 711건 | 5건 | 0.7% |

단일 토픽에서도 전체의 7~13%만 접근 가능하다. HDD 17개 섹션에 필요한 데이터포인트 200+를 top-k=5로는 절대 커버할 수 없다.

**개선안:** `top_k` 파라미터 추가 (5 → 20), 모듈별/claim_type별 균등 샘플링 옵션

---

#### RCA-3-C: 토픽 분류 체계 불완전
**플랫폼:** Obot 주도 발견

**현재 확인된 토픽:** EDC, NoC, Overlay, DFX, Dispatch, FPU  
**누락된 토픽:** Tensix, PRTN/Power, SRAM/Memory, Clock, Reset, NIU (NoC와 분리 필요)

`topic=NIU`로 검색 시 **0건** 반환. `query=noc2axi`로 우회 필요하며, 이 경우 711건 중 5건 반환.

---

#### RCA-3-D: 검색 결과에 소스 파일 경로 미포함
**플랫폼:** Claude Code + Obot

`search_rtl` 결과에 소스 파일 경로가 없어 LLM이 "이 Claim이 N1B0에서 온 것인가, Baseline에서 온 것인가"를 구분할 수 없다. Generic 정보를 N1B0 정보로 오판하는 직접 원인.

---

### Layer 4: 생성 계층

#### RCA-4-A: Knowledge Gap Filling — Hallucination의 직접 원인
**플랫폼:** 3개 리뷰 일치

시스템 프롬프트에 grounding 제약이 없어 Claude가 "HDD에 있어야 할 것 같은" 섹션을 사전 학습 지식으로 채운다.

**v1에서 실제로 발생한 Hallucination:**
- UCIe 블록 (N1B0 RTL 존재 미확인)
- TDMA 서브시스템 (정답지에 없음)
- P&R 수치 `3,519,581 포트`, `2.0 GHz`, `52.73% 활용률` (타 Trinity 변형 PD 보고서에서 혼입)
- Appendix B/C/D "추정" 레지스터 맵 오프셋

**개선안 (즉시 적용 가능):**
```
STRICT GROUNDING RULES:
1. Only include information explicitly present in the retrieved Claims.
2. If data is missing, write: "⚠️ [NOT IN KB] — Requires additional RTL parsing."
3. Do NOT extrapolate from general semiconductor knowledge.
4. Module hierarchy must be verified against generate block analysis,
   not assumed from file existence alone.
```

---

#### RCA-4-B: trinity_router 계층 역전 — 가장 심각한 사실 오류
**플랫폼:** Claude Code 주도 발견

**v1 오류:**
```
trinity → trinity_router (직접 instantiate) ← 완전히 잘못됨
```

**정답:**
```
trinity → gen_router[x=1,2][y=3]: EMPTY (N1B0에서 미사용)
trinity → trinity_noc2axi_router_ne_opt (Y=4+Y=3 내부에 router 내장)
```

N1B0의 핵심 변경사항(HPDF 통합 타일)이 정반대로 기술된 것. `trinity_router.sv` 파일이 KB에 존재한다는 이유만으로 instantiate된다고 판단한 결과다. RCA-2-C(generate 분석 없음)와 RCA-4-A(Grounding 없음)의 복합 효과.

---

### Layer 5: 툴링 및 MCP 계층

#### RCA-5-A: MCP 병렬 호출 JSON 파싱 버그
**플랫폼:** Claude Code 단독 발견

**증상:**
```
failed to unmarshal input: invalid character '{' after top-level value
```

Claude가 `search_rtl`을 여러 번 호출하려 할 때 Obot이 동시 실행하면서 JSON 스트림이 충돌한다. 현재 임시 해결책: 프롬프트에 "도구를 **한 번만** 호출해" 명시.

**이것이 중요한 이유:** 이 버그가 존재하는 한, 멀티-쿼리 전략(섹션별 순차 검색)을 기술적으로 구현할 수 없다. 모든 다른 개선이 완료되어도 이 버그가 병목이 된다.

**개선안:**
```javascript
// mcp-bridge/server.js — 순차 처리 큐
const callQueue = [];
async function enqueueToolCall(toolName, args) {
    return new Promise((resolve) => {
        callQueue.push({ toolName, args, resolve });
        if (callQueue.length === 1) processQueue();
    });
}
```

---

#### RCA-5-B: search_rtl 도구 인터페이스 설계 한계
**플랫폼:** Claude Code + Obot

**현재:** `search_rtl(pipeline_id, topic?, query?)`  
**문제:** chip_variant, file_path, claim_types, top_k, include_source_path 파라미터 없음

**개선된 인터페이스:**
```
search_rtl(
    pipeline_id,           // 기존
    topic?,                // 기존
    query?,                // 기존
    chip_variant?,         // 신규: "N1B0" | "baseline" | "all"
    claim_types?,          // 신규: ["package_constant", "port", "hierarchy", "generate"]
    top_k?,                // 신규: 5~50 (기본 5)
    include_source_path?   // 신규: 소스 파일 경로 포함
)
```

---

### Layer 6: 프롬프트 설계 계층

#### RCA-6-A: 생성 언어 지시 부재
**플랫폼:** Claude Code 주도 발견

Obot 사용 언어(한국어)로 HDD가 생성된다. RTL 시그널명, EDA 도구명과 한국어 설명이 혼재하여 팀 외부 공유 불가.

**즉시 적용 가능:**
```
You MUST generate the HDD in English regardless of the query language.
RTL signal names, module names, and file paths must be quoted exactly as-is.
```

---

#### RCA-6-B: 섹션 우선순위 미지정
**플랫폼:** Claude Code 주도 발견

N1B0-specific 섹션과 Generic 공통 섹션의 구분이 없어 Claude가 생성하기 쉬운 Generic 내용으로 문서가 부풀려진다.

**섹션 3등급 분류:**
```
[CRITICAL — N1B0 specific, KB 데이터 필수]
  Package Constants & Grid, HPDF 통합 모듈 계층,
  per-column clock 변경, PRTN Chain, NoC Repeater 배치,
  Diff vs Baseline Trinity

[IMPORTANT — shared, N1B0 수치 사용]
  Top-Level Ports (정확한 비트폭), EDC Ring, SFR Memory Config

[SUPPLEMENTARY — KB 없을 시 generic 허용]
  Tensix 내부 (FPU, SFPU), DFX 개요
```

---

### Layer 7: 평가 계층

#### RCA-7-A: 자동 품질 검증 프레임워크 부재
**플랫폼:** Claude Code 주도 발견

엔지니어가 매번 수동으로 Compare Report를 작성 중. 자동화 없이는 개선-검증 사이클이 지속적으로 느리다.

**필요한 자동 검증:**

| 검증 유형 | 방법 | 기준 |
|-----------|------|------|
| 섹션 커버리지 | 정규식 헤더 검사 | ≥ 14/17 섹션 |
| 파라미터 정확도 | RTL 파싱 결과 대조 | SizeX=4, SizeY=5, NumTensix=12 |
| 모듈명 유효성 | KB 역검색 | 미존재 모듈명 플래그 |
| Hallucination 탐지 | 생성 내용 → KB 역검색 | "⚠️ NOT IN KB" 비율 |
| 언어 일관성 | 언어 감지 | 영어 ≥ 95% |
| N1B0 특이성 | 키워드 밀도 | "per-column", "HPDF", "PRTN" 포함 여부 |

---

### Layer 8: 인프라 설계 계층 (통합 신규 식별)

#### RCA-8-A: RTL 파서 아키텍처 한계 — 정규식 기반의 구조적 한계
**플랫폼:** Kiro 주도 발견

현재 파서는 정규식 기반으로 `[SizeX-1:0]` 같은 파라미터 참조 폭을 리터럴로만 처리하고 실제 값으로 해석하지 못한다. `SizeX-1=3`이므로 `[3:0]=4-bit`임을 알려면 패키지 파라미터를 먼저 파싱해야 하는 의존성이 있다.

**Kiro 제안 개선안:** PyVerilog AST 기반 파서로 전환
- AST를 통해 파라미터 참조 자동 해석
- generate 블록 조건 정확한 파싱
- struct/enum 내부 구조 완전 추출

---

## 5. 플랫폼별 고유 발견 사항

### 5.1 Claude Code만 발견

1. **MCP 병렬 호출 JSON 버그** — 코드 직접 분석으로만 발견 가능. Obot/Kiro에서는 증상(단일 쿼리 강제)만 관찰되고 원인은 미확인.

2. **S3 메타데이터 스키마 구체적 설계** — 인프라 코드(`environments/app-layer/bedrock-rag/lambda.tf`) 직접 열람으로 현재 스키마 확인, 개선안 설계.

3. **multi-version trinity.sv 충돌 메커니즘** — RTL 파일 직접 읽기로 4개 버전 확인 및 인덱스 충돌 메커니즘 추적.

### 5.2 Kiro만 발견

1. **chip_config 분석 이미 완료** — Package Constants 일부가 이미 해결된 상태임. 다른 리뷰들은 이 항목을 "미해결"로 분류.

2. **PyVerilog AST 전환 가능성** — IDE에서 실제 파서 코드 열람 후 정규식 방식의 구조적 한계와 AST 전환 비용/효과 평가.

3. **variant_delta 이미 구현됨** — Diff vs Baseline 기능이 파이프라인에 존재하나 baseline RTL이 업로드되지 않아 미동작 상태.

### 5.3 Obot만 발견

1. **Claim 모듈 귀속 오류** — 실제 검색 실험으로만 발견 가능. FPU/Overlay가 `trinity_noc2axi_router_ne_opt_FBLC`에 잘못 귀속됨. 코드 분석으로는 파악 불가능한 런타임 데이터 문제.

2. **검색 건수 5건 제한의 실제 영향** — 토픽별 전체 Claim 수 측정 후 커버리지 계산. `noc2axi` 쿼리: 711건 존재, 5건만 반환 (0.7%).

3. **hdd_section 86건이 단일 모듈에 편중** — 86건 중 대부분이 `trinity_noc2axi_router_ne_opt_FBLC` 대상. 다른 모듈의 HDD 섹션은 사실상 없음.

---

## 6. 실험 기반 근거 데이터

Obot 8회 검색 실험 결과 (실제 운영 데이터):

| # | 검색 조건 | 전체/반환 | 유용성 | 핵심 발견 |
|---|----------|----------|--------|-----------|
| 1 | `query="EDC"` | 101/5건 | 중간 | hdd_section 중복 다수 |
| 2 | `analysis=hdd_section` | 86/5건 | 낮음 | 모두 noc2axi_router 대상 (귀속 오류 발견) |
| 3 | `topic=EDC` | 37/5건 | 높음 | Claim 3종 혼합 — 구조 분석 가능 |
| 4 | `topic=EDC` (2차) | 35/5건 | 높음 | Claim 기반 구조 분석 확인 |
| 5 | `topic=NoC` | 40/5건 | 중간 | Repeater/Arbiter Claim 확보 |
| 6 | `topic=Dispatch` | 76/5건 | 낮음 | hdd_section만 5건, Claim 0건 |
| 7 | `query=noc2axi` | 711/5건 | 중간 | FPU/Overlay 토픽 발견, 귀속 오류 확인 |
| 8 | `topic=NIU` | 0건 | 없음 | NIU 토픽 미존재 확인 |

**결론:** 총 8회, 유효 Claim ~15건 획득. 정답지 재현 필요 데이터포인트 200+ 대비 **실질 커버리지 7.5%**.

---

## 7. 통합 개선 로드맵

### Phase 0 — 즉시 적용 (1주 이내, 코드 변경 없음)

| ID | 항목 | 변경 위치 | 기대 효과 |
|----|------|-----------|-----------|
| F0-1 | Grounding 제약 시스템 프롬프트 추가 | Obot 설정 | Hallucination ~20% → ~8% |
| F0-2 | 생성 언어 영어 강제 | Obot 시스템 프롬프트 | 언어 오류 제거 |
| F0-3 | 섹션별 분할 쿼리 (prompt.md 개선) | prompt.md | 섹션 커버리지 +15% |
| F0-4 | N1B0 키워드를 모든 쿼리에 명시 | prompt.md | Generic 리트리브 감소 |
| F0-5 | trinity_router 미사용 명시 지시 | 생성 프롬프트 | 계층 역전 오류 제거 |
| F0-6 | top_k=20 요청 명시 | prompt.md | 데이터 커버리지 4배 |

**F0-3 섹션별 순차 쿼리 예시:**
```
프롬프트 1: "search_rtl으로 'trinity_pkg N1B0 SizeX SizeY GridConfig enum' 검색 후
             Package Constants & Grid 섹션만 작성. ⚠️ KB에 없으면 NOT IN KB로 표기."
프롬프트 2: "search_rtl으로 'trinity.sv N1B0 generate block NOC2AXI_ROUTER EMPTY' 검색 후
             Module Hierarchy 섹션만 작성. ROUTER placeholder 비어있음 반드시 명시."
프롬프트 3: "search_rtl으로 'PRTNUN FC2UN N1B0 daisy chain power management' 검색 후
             PRTN Chain 섹션만 작성."
```

---

### Phase 1 — 단기 (2~4주, 인프라 변경)

| ID | 항목 | 파일 | RCA |
|----|------|------|-----|
| P1-1 | MCP 병렬 호출 버그 수정 | `mcp-bridge/server.js` | RCA-5-A |
| P1-2 | S3 메타데이터 chip_variant 추가 | `lambda.tf`, `handler.py` | RCA-1-A |
| P1-3 | search_rtl top_k + chip_variant 파라미터 | `server.js`, rag handler | RCA-5-B, RCA-3-B |
| P1-4 | 포트 비트폭/배열 Claim 추출 | `handler.py` 포트 파서 | RCA-2-B |
| P1-5 | 토픽 분류 확대 (Tensix, Power, Memory, NIU) | RTL 파서 토픽 매핑 | RCA-3-C |
| P1-6 | Claim 귀속 모듈 검증 로직 | Claim 생성 로직 | RCA-2-E |

---

### Phase 2 — 중기 (1~2개월, 파이프라인 확장)

| ID | 신규 analysis_type | 커버 섹션 | 비고 |
|----|-------------------|-----------|------|
| P2-1 | `package_parse` | §2 Constants, enum, struct | PyVerilog AST 도입 검토 (Kiro 권고) |
| P2-2 | `generate_analysis` | §4 계층, §12 검증 | EMPTY block 탐지 필수 |
| P2-3 | `connectivity_trace` | §5 NoC, §6 Clock, §7 EDC, §8 Dispatch | manual assign vs generate loop 구분 |
| P2-4 | `prtn_power` | §9 PRTN Chain | prefix 기반 포트 그룹 분류 |
| P2-5 | `sfr_port_group` | §10 SFR Memory Config | SRAM 설정 포트 타일 매핑 |
| P2-6 | `sram_inventory` | §13 (추가 섹션) | 메모리 인스턴스 목록 |
| P2-7 | 멀티-쿼리 HDD 생성 Lambda | 전체 17섹션 | P1-1 (MCP 버그 수정) 선행 필요 |

**P2-7 섹션별 쿼리 전략 템플릿:**
```json
{
  "package_constants": {"query": "trinity_pkg SizeX GridConfig enum", "chip_variant": "N1B0"},
  "module_hierarchy":  {"query": "generate block EMPTY ROUTER N1B0", "chip_variant": "N1B0"},
  "clock_routing":     {"query": "clock_routing_t per-column i_ai_clk N1B0 change", "chip_variant": "N1B0"},
  "prtn_chain":        {"query": "PRTNUN FC2UN daisy chain power N1B0", "chip_variant": "N1B0"},
  "noc_connections":   {"query": "manual assign repeater Y=3 Y=4 N1B0 inter-column", "chip_variant": "N1B0"},
  "variant_diff":      {"query": "N1B0 vs baseline Trinity change HPDF per-column", "chip_variant": "N1B0"}
}
```

---

### Phase 3 — 장기 (2~3개월, 검증 시스템)

| ID | 항목 | 내용 |
|----|------|------|
| P3-1 | HDD 자동 품질 검증 Lambda | 섹션 커버리지, 파라미터 정확도, Hallucination 탐지, 언어 일관성 |
| P3-2 | RTL Diff 자동화 | baseline RTL 업로드 후 variant_delta 활성화 (Kiro: 이미 구현됨) |
| P3-3 | Cross-file 추적 | pkg 선언 ↔ RTL 인스턴스 교차 검증 |
| P3-4 | 피드백 루프 | 엔지니어 리뷰 → Claim DB 보강 → 파서 자동 개선 제안 |

---

## 8. 평가 프레임워크

### 8.1 섹션별 채점 기준 (가중치)

| 섹션 | 가중치 | 핵심 채점 기준 |
|------|--------|---------------|
| Package Constants & Grid | 15% | SizeX/Y, NumTensix, tile_t enum 8종, GridConfig 20개, EndpointIndex 공식 |
| Top-Level Ports | 10% | 핵심 포트 비트폭, per-column 배열 [SizeX-1:0] 명시 |
| Module Hierarchy (N1B0) | 15% | trinity_router 미사용, HPDF 통합, EMPTY generate block |
| NoC Connections | 10% | manual assign, Y=3 6-stage, Y=4 4-stage 리피터 |
| Clock Routing | 10% | trinity_clock_routing_t, per-column, NOC2AXI_ROUTER 예외 |
| PRTN Chain | 10% | 4-column daisy-chain, PRTNUN_FC2UN 포트 |
| EDC Ring | 5% | flat array, x*SizeY+y 인덱스, column-wise chain |
| Dispatch Feedthrough | 5% | de_to_t6 구조, horizontal/vertical feedthrough |
| Memory Config (SFR) | 5% | SFR_RF_2P_*, SFR_RA1_* 타입별 수신 타일 |
| RTL File Map | 5% | 모듈↔파일 매핑, used_in_n1 경로 |
| Diff vs Baseline | 10% | 8개 이상 변경사항, per-column/repeater/PRTN/ISO_EN |

### 8.2 Hallucination 탐지 기준

```
HIGH RISK (즉시 플래그):
  - trinity에 UCIe 블록 인스턴스
  - TDMA 서브시스템
  - P&R 수치 (포트 수, 주파수, 활용률)
  - "추정" 레지스터 오프셋
  - FPU/Overlay가 NIU/Router 내부로 귀속

MEDIUM RISK (검증 필요):
  - trinity_router가 trinity에 직접 instantiate
  - i_ai_clk 단일 비트 선언
  - 5개 초과 독립 클럭 도메인
```

### 8.3 목표 지표 (Phase별)

| 항목 | 현재 | Phase 1 | Phase 2 | Phase 3 |
|------|------|---------|---------|---------|
| 섹션 커버리지 | ~50% | 65% | 85% | 95% |
| 파라미터 정확도 | ~25% | 45% | 70% | 90% |
| Hallucination 비율 | ~20~40% | ~10% | ≤ 5% | ≤ 2% |
| N1B0 특이성 | ~40~55% | 70% | 90% | 95% |
| 언어 일관성 | ~60% | 100% | 100% | 100% |
| 연결 정보 커버리지 | 0% | 0% | ~60% | ~85% |
| 자동 검증 커버리지 | 0% | 30% | 60% | 90% |

---

## 9. RCA 요약 테이블

| RCA ID | 계층 | 원인 | 발견 플랫폼 | 우선순위 |
|--------|------|------|------------|----------|
| RCA-1-A | 데이터 수집 | chip_variant 메타데이터 없음 | Claude | P1 |
| RCA-1-B | 데이터 수집 | 다중 버전 모듈명 충돌 | Claude+Obot | P1 |
| RCA-2-A | Claim 추출 | parameter/enum/struct 미추출 | **3개 일치** | P1 |
| RCA-2-B | Claim 추출 | 포트 비트폭/배열 미추출 | Claude+Obot | P1 |
| RCA-2-C | Claim 추출 | generate 블록 분석 없음 | Obot+Claude | P1 |
| RCA-2-D | Claim 추출 | assign 연결 추적 없음 | Obot | P2 |
| RCA-2-E | Claim 추출 | Claim 모듈 귀속 오류 | **Obot 단독** | P1 |
| RCA-2-F | Claim 추출 | PRTN/SFR/SRAM/diff 분석 없음 | **3개 일치** | P1~P2 |
| RCA-3-A | 검색 | Generic > N1B0 유사도 (빈도 편향) | Claude | P1 |
| RCA-3-B | 검색 | 검색 반환 건수 5건 제한 | **Obot 단독** | P1 |
| RCA-3-C | 검색 | 토픽 분류 체계 불완전 | Obot | P1 |
| RCA-3-D | 검색 | 소스 파일 경로 결과에 미포함 | Claude+Obot | P1 |
| RCA-4-A | 생성 | Knowledge Gap Filling (Grounding 없음) | **3개 일치** | **P0** |
| RCA-4-B | 생성 | trinity_router 계층 역전 오류 | Claude | **P0** |
| RCA-5-A | MCP | 병렬 호출 JSON 버그 | **Claude 단독** | P1 |
| RCA-5-B | MCP | chip_variant/top_k 파라미터 없음 | Claude+Obot | P1 |
| RCA-6-A | 프롬프트 | 생성 언어 지시 없음 | Claude | **P0** |
| RCA-6-B | 프롬프트 | Grounding 제약 없음 | **3개 일치** | **P0** |
| RCA-6-C | 프롬프트 | N1B0 섹션 우선순위 없음 | Claude | **P0** |
| RCA-7-A | 평가 | 자동 품질 검증 없음 | Claude | P2 |
| RCA-8-A | 인프라 | 정규식 파서 구조적 한계 | **Kiro 단독** | P2 |

**P0 (즉시): RCA-4-A, RCA-4-B, RCA-6-A, RCA-6-B, RCA-6-C → 프롬프트 수정으로 즉시 적용 가능**  
**P1 (단기): RCA-2-A~C, RCA-3-B~D, RCA-5-A~B 등 → 인프라/파서 수정 필요**  
**P2 (중기): RCA-2-D, RCA-8-A 등 → 신규 analysis_type 개발**

---

*작성: Claude Sonnet 4.6 (1M context) — 2026-04-22*  
*통합 출처: claude_review_v0.1.md (Claude Code CLI), kiro_review_v0.1.md (Kiro IDE), obot_review_v0.1.md (Obot 챗봇)*  
*분석 기준 문서: test_rtl/Sample/N1B0_HDD_v0.1.md, test_rtl/rag_result/v1/Trinity_N1B0_HDD_Complete_v1.md*
