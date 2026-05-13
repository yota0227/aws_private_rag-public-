# Kiro Review — RAG v9.3 산출물 정답지 비교

**리뷰 일자:** 2026-05-12
**리뷰어:** Kiro (Claude Opus 4.6)
**대상:** `test_rtl/rag_result/v9.3/` 전체 산출물 (7개 파일)
**정답지:** `test_rtl/Sample/ORG/` (N1B0_NPU_HDD_v0.1.md 중심)
**선행 리뷰 참조:** claude_review_v9.3.md (48/100), codex_review_v9.3.md (72-74% 통합본)

---

## 0. 한줄 요약

**v9.3는 Port Binding이라는 "RTL connectivity evidence"를 처음 HDD에 넣은 의미 있는 버전이지만, 정답지의 핵심 가치인 "왜 이렇게 연결되는가"와 "어떤 파라미터로 동작하는가"는 여전히 빈칸이다.**

---

## 1. 점수 (독립 산정)

| 기준 | 점수 | 근거 |
|------|------|------|
| 구조적 사실 (EP, hierarchy L1, wire topology) | 82/100 | EP Table 완벽, Port Binding 추가, hierarchy L1 안정 |
| 파라미터/수치 (bit width, FIFO depth, SRAM size) | 30/100 | FPU 일부만. AXI/Router/L1 파라미터 전무 |
| 토폴로지/물리 (repeater count, dual-row, ring model) | 40/100 | 4x5 mesh 맞음. repeater stage count, per-column ring 틀림 |
| 알고리즘/프로토콜 (routing, EDC protocol, VC) | 25/100 | 이름만 나열. 928-bit carried list, MAX_FRGS=12 등 핵심 수치 없음 |
| SW/FW 가이드 | 5/100 | 거의 전무 |
| **가중 평균** (구조 35% + 파라미터 20% + 토폴로지 15% + 알고리즘 20% + SW 10%) | **~44/100** | |

**통합 HDD 문서 완성도 (정답지 대체 가능성):** ~38% (정답지 1291줄 vs v9.3 492줄, 내용 밀도 차이 고려)

> Claude 48점, Codex 72-74%와의 차이 설명: Claude는 "전체 가중 평균"으로 구조 비중을 40%로 잡았고, Codex는 "문서 밀도 + table row 수" 기준으로 산정. 내 점수는 **"정답지를 읽은 엔지니어가 v9.3만 보고 같은 수준의 이해에 도달할 수 있는가"** 기준이라 더 보수적.

---

## 2. 두 선행 리뷰가 놓친 포인트

### 2.1 DISPATCH_E/W 위치 오류의 근본 원인

Claude와 Codex 모두 "East=columns 0-1이 틀렸다"고 지적했지만, **더 근본적인 문제**가 있다:

정답지 §2.2 tile_t enum:
- `DISPATCH_E` = (X=**3**, Y=3) — **East edge**
- `DISPATCH_W` = (X=**0**, Y=3) — **West edge**

v9.3 EP Table은 이걸 **정확히** 기술한다 (EP3=(0,3)=DISPATCH_E, EP18=(3,3)=DISPATCH_W). 그런데 v9.3_chip_grounded.md §6에서 `[FROM LLM]`으로 "East dispatch handles columns 0-1"이라고 쓴 건 **EP Table 자체와 모순**이다.

→ **프롬프트 레벨 fix:** "EP Table의 좌표를 참조하여 [FROM LLM] 추론을 검증하라"는 self-consistency check를 프롬프트에 추가해야 함.

### 2.2 정답지의 "per-column ×4" 패턴을 v9.3가 완전히 놓침

정답지 §3.4를 보면 EDC APB/IRQ가 **`[3:0]` 배열** (per-column)이다:
```
i_edc_apb_psel[3:0]     — 4개 column 각각 독립 APB
o_edc_fatal_err_irq[3:0] — 4개 column 각각 독립 IRQ
```

v9.3_edc.md §11 Top-Level EDC Ports는 이걸 **단일 신호**처럼 나열한다:
```
i_edc_apb_psel | in | APB select
o_edc_fatal_err_irq | out | Fatal error IRQ
```

이건 "16 ports"라고 카운트는 맞추면서 **배열 차원을 누락**한 것. 정답지는 "×4 columns"를 명시하고 있어서, v9.3의 EDC 포트 테이블은 **per-column 독립성을 표현하지 못함**.

### 2.3 Composite Tile의 "dual-row" 본질을 v9.3가 이해 못함

정답지 §8.2의 핵심:
```
trinity_noc2axi_router_ne_opt (X=1, Y=4+Y=3)
├── trinity_noc2axi_n_opt    ← Y=4 NOC2AXI bridge
└── trinity_router            ← Y=3 mesh router (EP=8)
```

v9.3는 이걸 "Composite: router + NIU"라고만 쓰고, **내부에 `trinity_noc2axi_n_opt` + `trinity_router`가 별도 인스턴스로 존재한다는 사실**을 기술하지 않는다. 이건 단순 누락이 아니라 **N1B0의 identity** (baseline에서 분리됐던 두 모듈을 하나로 합친 것)를 놓친 것.

### 2.4 Clock Routing의 "exception" 패턴

정답지 §8.2:
> The router's buffered clock outputs (`router_o_ai_clk`, etc.) drive `clock_routing_out[x][y-1]` (Y=3) at trinity top.

즉 composite tile은 Y=4 위치에 있지만 **Y=3의 clock_routing_out을 drive**한다. 이 "exception"이 v9.3 어디에도 없다. Clock mesh가 단순 4×5 uniform이 아니라 composite tile에서 깨진다는 사실이 빠져있음.

### 2.5 `de_to_t6_coloumn` 차원 회귀

Codex가 지적했지만 강조 부족. 정답지 실제 차원:
```
de_to_t6_coloumn[SizeX][SizeY-1][2]  = [4][4][2]
```

v9.3: `[SizeX][SizeX]` — 마지막 `[2]` (East/West 방향 구분)가 빠짐. 이건 wire_declaration_parser가 packed dimension의 마지막 차원을 drop하는 버그일 가능성.

---

## 3. 섹션별 정밀 비교 (선행 리뷰 보완)

### 3.1 Overview — 정답지 §1.1 "N1B0 vs Baseline" 테이블 부재

정답지에는 10-row 차이표가 있다. v9.3에는 "trinity_router is NOT instantiated" 한 줄만. 이 테이블은 **N1B0 HDD의 존재 이유**를 설명하는 핵심 섹션인데 완전 누락.

### 3.2 Top-Level Ports — AXI 파라미터 3개 누락

| 파라미터 | 정답지 값 | v9.3 |
|----------|-----------|------|
| AXI_SLV_OUTSTANDING_READS | 64 | ❌ 없음 |
| AXI_SLV_OUTSTANDING_WRITES | 32 | ❌ 없음 |
| AXI_SLV_RD_RDATA_FIFO_DEPTH | 512 | ❌ 없음 |

이 3개는 RTL top module의 `parameter` 선언에서 직접 추출 가능. package_parser 확장으로 해결 가능.

### 3.3 Module Hierarchy — generate block 이름 누락

정답지는 `gen_noc2axi_ne_opt`, `gen_noc2axi_router_ne_opt`, `gen_dispatch_e`, `gen_tensix_neo` 같은 **generate block 이름**을 명시. v9.3는 인스턴스명만 있고 generate block context가 없음. 이건 RTL 파서가 `generate for/if` 블록을 추적하지 않기 때문.

### 3.4 Tensix — 정답지 대비 가장 큰 gap

정답지 §5는 **7개 서브섹션** (TRISC/BRISC, FPU G-Tile/M-Tile, SFPU, TDMA, L1, DEST, SRCB)으로 구성되며 각각 2-3 페이지 분량. v9.3는 모듈명 + 파라미터 나열 수준.

특히 누락된 핵심 수치:
- L1: 16 banks × 3072×128 = **768 KB/tile**, 12 tiles = **9.216 MB**
- DEST: 4096×16 latch array, **12,288 instances** total
- FP lanes: 2×G-Tile × 8 lanes = **16 lanes/tile**
- INT8 mode: **512 MACs/cycle/tile**

이건 RTL 파서로 뽑을 수 있는 영역이 아님. Spec RAG 또는 수동 claim 주입 필요.

### 3.5 NoC — AXI 56-bit gasket 비트 경계

정답지:
```
[55:52] reserved (4b)
[51:48] target_index (4b)
[47:40] endpoint_id (8b)
[39:36] tlb_index (4b)
[35:0]  address (36b)
```

v9.3: `[TBC]`로 표기. 이건 `tt_noc_pkg.sv`의 struct 정의에서 추출 가능한데 현재 파서가 못 뽑고 있음.

### 3.6 EDC — "4 independent rings" vs "1 chip ring"

정답지 §2.1:
> Each column (X=0..3) has its own independent EDC ring.

v9.3_edc.md의 ASCII diagram은 **전체 칩을 하나의 ring**처럼 그림. 이건 factual error.

추가로 정답지의 핵심 수치:
- MAX_FRGS = 12
- SUPER=1, MAJOR=1, MINOR=0
- node_id: part[4:0] + subp[2:0] + inst[7:0] = 16b

v9.3: 모두 `[TBC]` 또는 누락.

### 3.7 DFX — 4-wrapper chain 완전 누락

정답지 `N1B0_DFX_HDD_v0.1.md`:
| Module | Clocks in→out | IJTAG |
|--------|--------------|-------|
| tt_noc_niu_router_dfx | 5→5 | ifdef |
| tt_overlay_wrapper_dfx | 5→5 | no |
| tt_instrn_engine_wrapper_dfx | 1→1 | ifdef |
| tt_t6_l1_partition_dfx | 2→3 | ifdef |

v9.3: "tt_tensix_jtag, tt_sync3, SDUMP_INTF, TIEL_DFT_MODESCAN" — **완전히 다른 모듈을 나열**. 정답지의 4개 DFX wrapper는 하나도 안 나옴.

---

## 4. v9.3 Port Binding의 실질 가치 (독립 검증)

정답지 §8.2에서 확인 가능한 port binding:
```systemverilog
.i_local_nodeid_y  (i_local_nodeid_y - 1)
.i_noc_endpoint_id (i_noc_endpoint_id - 1)
```

v9.3가 추출한 것:
```
trinity_noc2axi_router_ne_opt.i_noc_endpoint_id ↔ EndpointIndex
```

**차이:** 정답지는 `-1` offset을 명시. v9.3는 `EndpointIndex`만 기록하고 offset 연산을 놓침. 이건 Port Binding Parser가 `.port(expression)` 형태에서 expression의 산술 연산을 파싱하지 못하기 때문.

→ **v9.4 개선점:** Port Binding Parser에 expression evaluation 추가 (최소한 `±1` 수준).

---

## 5. 치명적 오류 목록 (4+2건)

Claude가 4건 지적. 추가 2건:

| # | 위치 | 오류 | 정답 |
|---|------|------|------|
| 1 | chip_grounded §6 | "East handles columns 0-1" | East=X=3, West=X=0 |
| 2 | edc.md ASCII | 전체 칩 1 ring | **4 independent rings (per-column)** |
| 3 | chip_grounded §2.5 | trinity_clock_routing_t 8 fields | **9 fields**, 배열 차원 포함 |
| 4 | overlay.md §2 | Y=0=NOC2AXI 좌표계 | N1B0는 Y=4=NOC2AXI |
| **5** | edc.md §11 | EDC ports 단일 신호 | **[3:0] per-column 배열** |
| **6** | N1B0_HDD §14 | DFX = tt_tensix_jtag 등 | **4-wrapper chain (dfx 모듈 4개)** |

---

## 6. v9.4 우선순위 (실행 가능성 기준)

### 즉시 (프롬프트/데이터 수정만으로 해결)

| # | 작업 | 효과 | 난이도 |
|---|------|------|--------|
| 1 | EDC "per-column ring" claim 추가 | 치명적 오류 수정 | 낮음 (수동 claim 1개) |
| 2 | Dispatch E/W 좌표 self-check 프롬프트 | [FROM LLM] 오류 방지 | 낮음 |
| 3 | EDC port `[3:0]` 배열 차원 반영 | 포트 정확도 | 낮음 |
| 4 | DFX 4-wrapper 모듈명 수동 claim | DFX 섹션 정확도 | 낮음 |

### 파서 확장 (v9.4 개발)

| # | 작업 | 효과 | 난이도 |
|---|------|------|--------|
| 5 | Port Binding expression eval (`±1`) | NIU EP offset 정확도 | 중간 |
| 6 | generate block name 추출 | Hierarchy 정확도 | 중간 |
| 7 | Top module parameter 추출 | AXI 파라미터 3개 | 낮음 |
| 8 | wire dimension `[a][b][c]` 3차원 보존 | Dispatch wire 정확도 | 중간 |
| 9 | struct field packed dimension 추출 | clock_routing_t 9 fields | 중간 |

### 중장기 (Spec RAG / Neptune)

| # | 작업 | 효과 |
|---|------|------|
| 10 | Neptune ingestion pipeline | Schematic Map 실데이터 |
| 11 | Spec RAG (설계 문서 임베딩) | Tensix 상세, SW guide |
| 12 | N1B0 vs Baseline 차이표 자동 생성 | Overview 완성 |

---

## 7. 결론

v9.3는 **"RTL 그래프에서 뽑을 수 있는 구조적 사실"의 천장에 거의 도달**했다. EP Table, Wire Topology, Port Binding은 정답지와 일치하거나 근접한다. 하지만 정답지의 **50% 이상은 설계 지식** (알고리즘, 파라미터, SW 가이드, 물리 가이드)으로 구성되어 있어서, RTL 파서만으로는 논리적으로 도달 불가능한 영역이 존재한다.

다음 단계는 두 갈래:
1. **즉시 수정 가능한 factual error 4-6건 제거** → 정확도 신뢰 확보
2. **Neptune + Spec RAG** → 구조 너머의 knowledge depth 확보

---

*End of Review — Kiro (Claude Opus 4.6), 2026-05-12*
