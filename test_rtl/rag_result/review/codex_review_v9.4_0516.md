# Codex Review: RAG v9.4_0516 정답지 비교 분석

**작성일:** 2026-06-01  
**리뷰어:** Codex  
**비교 대상:** `test_rtl/rag_result/v9.4_0516/` 산출물 전체, 특히 `v9.4_0516_N1B0_HDD.md`와 `v9.4_0516_schematic_map.md`  
**저장 위치:** `test_rtl/rag_result/review/codex_review_v9.4_0516.md`  

---

## 0. 결론

v9.4_0516은 점수만 보면 v9.4a보다 내려갔다. 그러나 실패 빌드로 보기는 어렵다. 성격이 다르다.

v9.4a는 `tt_20260221`에 Neptune graph가 붙어 hierarchy와 EDC/NoC 구조가 두꺼웠던 빌드이고, v9.4_0516은 `tt_20260516` 새 RTL 스냅샷으로 넘어가면서 **Qdrant 검색은 살아 있지만 Neptune graph가 아직 붙지 않은 중간 빌드**에 가깝다.

핵심 성과는 분명하다.

1. 정답지에서 계속 중요했던 **SFR memory config 실명**이 복구됐다.
2. **PRTN chain 실명**도 13개까지 복구됐다.
3. `v9.4_0516_schematic_map.md`와 `.html`이 추가되어 RTL map을 사람이 훨씬 빨리 읽을 수 있게 됐다.
4. `tt_20260516`이라는 다른 RTL snapshot에서도 pipeline이 돌아간다는 범용성은 확인됐다.

반대로 가장 큰 손실은 이것이다.

1. Neptune 미적재 때문에 v9.4a의 강점이던 instantiation tree, EDC ring, DFX wrapper chain이 대부분 빠졌다.
2. 통합 HDD가 1239 lines에서 271 lines로 줄어 정답지형 HDD의 밀도가 크게 떨어졌다.
3. 정답지의 N1B0 핵심 구조인 `NOC2AXI_ROUTER_NE_OPT / NOC2AXI_ROUTER_NW_OPT` dual-row composite tile이 0516 산출물에서는 `NOC2AXI_N_OPT x2`로 표현된다.
4. `ISO_EN[11:0]`가 PRTN/Power port set에서 빠져 top-level port 수가 정답지 106개가 아니라 105개로 나온다.

한 줄로 요약하면:

> **v9.4_0516은 SFR/PRTN 검색성은 크게 좋아졌지만, Neptune이 빠져서 정답지의 구조적 깊이를 잃은 빌드다. Semantic/Schematic map은 유용하지만 아직 exact wiring map은 아니다.**

점수는 다음처럼 본다.

| 평가 기준 | v9.4a | v9.4_0516 | 판정 |
|---|---:|---:|---|
| 통합 HDD 단독, `N1B0_HDD_v0.1.md` 기준 | 76~79% | **63~66%** | 하락 |
| 통합 HDD 단독, `N1B0_NPU_HDD_v0.1.md` 기준 | 68~72% | **55~59%** | 하락 |
| v9.4_0516 폴더 전체 best-of 기준 | 80~84% | **68~72%** | Schematic map 포함 시 일부 회복 |
| KB-only strict 구조 기준 | 82~86% | **65~70%** | Neptune 미적재 영향 |
| Semantic/Schematic map 유용성 | 구조 80%+, wiring 55~60% | **구조 78~82%, wiring 45~50%** | HTML은 좋지만 exact path 부족 |
| Neptune 적재 후 예상 | - | **74~78%** | SFR/PRTN 유지 시 회복 가능 |

---

## 1. 비교한 파일

### 정답지

| 파일 | 비교 기준 |
|---|---|
| `test_rtl/Sample/ORG/N1B0_HDD_v0.1.md` | N1B0 top-level, grid, ports, NOC2AXI_ROUTER 구조 |
| `test_rtl/Sample/ORG/N1B0_NPU_HDD_v0.1.md` | NPU/Overlay/NoC/EDC/DFX 확장 정답 |
| `test_rtl/Sample/ORG/N1B0_DFX_HDD_v0.1.md` | DFX 4-wrapper chain |
| `test_rtl/Sample/ORG/N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` | dual-row composite router tile exact wiring |

### v9.4_0516 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v9.4_0516/v9.4_0516_N1B0_HDD.md` | 최종 통합 HDD |
| `test_rtl/rag_result/v9.4_0516/v9.4_0516_schematic_map.md` | Semantic/Schematic map |
| `test_rtl/rag_result/v9.4_0516/v9.4_0516_schematic_map.html` | Interactive map prototype |
| `test_rtl/rag_result/v9.4_0516/v9.4_0516_chip_no_grounding.md` | KB-only evidence 중심 |
| `test_rtl/rag_result/v9.4_0516/v9.4_0516_chip_grounded.md` | grounded summary |
| `test_rtl/rag_result/v9.4_0516/v9.4_0516_noc.md` | NoC topic |
| `test_rtl/rag_result/v9.4_0516/v9.4_0516_edc.md` | EDC topic |
| `test_rtl/rag_result/v9.4_0516/v9.4_0516_overlay.md` | Overlay topic |

---

## 2. 정량 비교

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[FROM LLM]` | `[FROM NEPTUNE]` |
|---|---:|---:|---:|---:|---:|---:|---:|
| 정답지 `N1B0_HDD_v0.1.md` | 513 | 22330 | 40 | 186 | 24 | 0 | 0 |
| 정답지 `N1B0_NPU_HDD_v0.1.md` | 1290 | 58380 | 105 | 303 | 52 | 0 | 0 |
| 정답지 `N1B0_DFX_HDD_v0.1.md` | 252 | 10353 | 12 | 52 | 12 | 0 | 0 |
| 정답지 `N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` | 278 | 13815 | 18 | 61 | 12 | 0 | 0 |
| v9.4a `v9.4a_N1B0_HDD.md` | 1239 | 47721 | 130 | 435 | 44 | 12 | 44 |
| v9.4a `v9.4a_schematic_map.md` | 351 | 13217 | 13 | 29 | 18 | 0 | 5 |
| **v9.4_0516 `N1B0_HDD`** | **271** | **9992** | **36** | **43** | **4** | **6** | **0** |
| **v9.4_0516 `schematic_map`** | **328** | **11471** | **13** | **19** | **18** | **1** | **0** |
| v9.4_0516 `chip_no_grounding` | 255 | 9143 | 24 | 41 | 2 | 0 | 0 |
| v9.4_0516 `chip_grounded` | 223 | 8503 | 17 | 38 | 4 | 15 | 0 |
| v9.4_0516 `noc` | 182 | 5888 | 23 | 15 | 6 | 0 | 0 |
| v9.4_0516 `edc` | 169 | 5871 | 12 | 43 | 2 | 0 | 0 |
| v9.4_0516 `overlay` | 166 | 4666 | 16 | 19 | 4 | 0 | 0 |

해석:

- v9.4a 통합본은 정답지 `N1B0_NPU_HDD_v0.1.md`와 비슷한 체급까지 올라갔지만, v9.4_0516 통합본은 다시 요약본 체급으로 내려갔다.
- `[FROM NEPTUNE]`가 44개에서 0개로 사라진 것이 가장 큰 구조 손실이다.
- schematic map은 line 수는 유지됐지만, Neptune evidence가 빠져 exact hierarchy보다는 Qdrant 기반 conceptual map 성격이 강하다.
- topic 문서들이 전반적으로 축소됐다. 전체 folder best-of로 봐도 v9.4a만큼의 정보 밀도는 아니다.

---

## 3. 가장 큰 개선: SFR/PRTN 실명 복구

이번 버전의 최고 성과는 top-level port 검색이다.

### 3.1 SFR Memory Config

v9.4_0516은 `SFR_RF_2P_HSC_*`, `SFR_RA1_HS_*`, `SFR_RF1_HS/HD_*` 계열을 실명으로 복구했다. 정답지의 memory config section과 비교했을 때 큰 방향은 맞다.

복구된 축:

| 계열 | 정답지 기대 | v9.4_0516 |
|---|---|---|
| `SFR_RF_2P_HSC_QNAPA/B` | 있음 | 있음 |
| `SFR_RF_2P_HSC_EMAA/B[2:0]` | 있음 | 있음 |
| `SFR_RF_2P_HSC_EMASA`, `RAWL`, `RAWLM[1:0]` | 있음 | 있음 |
| `SFR_RA1_HS_MCS/MCSW/ADME` | 있음 | 있음 |
| `SFR_RF1_HS_MCS/MCSW/ADME` | 있음 | 있음 |
| `SFR_RF1_HD_MCS/MCSW/ADME` | 있음 | 있음 |

이건 중요하다. RTL RAG에서 포트 실명 복구는 문서 품질을 체감으로 끌어올린다. 추상 설명보다 DV/bring-up 엔지니어가 바로 쓸 수 있는 검색 결과에 가깝다.

### 3.2 PRTN Power Chain

v9.4_0516은 다음 PRTN 계열도 복구했다.

| 계열 | 정답지 기대 | v9.4_0516 |
|---|---|---|
| `PRTNUN_FC2UN_DATA_IN` | 있음 | 있음 |
| `PRTNUN_FC2UN_READY_IN` | 있음 | 있음 |
| `PRTNUN_FC2UN_CLK_IN` | 있음 | 있음 |
| `PRTNUN_FC2UN_RSTN_IN` | 있음 | 있음 |
| `PRTNUN_UN2FC_DATA_OUT[3:0]` | 있음 | 있음 |
| `PRTNUN_UN2FC_INTR_OUT[3:0]` | 있음 | 있음 |
| `PRTNUN_FC2UN_DATA_OUT[3:0]` | 있음 | 있음 |
| `PRTNUN_FC2UN_READY_OUT[3:0]` | 있음 | 있음 |
| `PRTNUN_FC2UN_CLK_OUT[3:0]` | 있음 | 있음 |
| `PRTNUN_FC2UN_RSTN_OUT[3:0]` | 있음 | 있음 |
| `PRTNUN_UN2FC_DATA_IN[3:0]` | 있음 | 있음 |
| `PRTNUN_UN2FC_INTR_IN[3:0]` | 있음 | 있음 |
| `ISO_EN[11:0]` | 있음 | **누락** |

남은 문제는 `ISO_EN[11:0]`다. 정답지는 `ISO_EN`을 N1B0 addition으로 강하게 다루며, 12개 Tensix tile isolation bit로 설명한다. v9.4_0516은 PRTN count를 13으로 잡고 `ISO_EN[11:0]`를 빠뜨린다. 그래서 top-level ports도 105 total이 된다.

정답지 기준으로는 **top-level port count가 106이어야 할 가능성이 높다.** 만약 `tt_20260516` RTL에서 실제로 `ISO_EN`이 제거됐다면 이건 RAG 오류가 아니라 snapshot 차이다. 하지만 산출물이 N1B0 HDD를 표방하고 정답지와 비교하는 맥락에서는 누락으로 표시해야 한다.

---

## 4. 가장 큰 회귀: NOC2AXI_ROUTER composite 구조

정답지의 핵심 문장은 다음 구조다.

- Baseline Trinity: `trinity_noc2axi_n_opt + trinity_router`
- N1B0: `trinity_noc2axi_router_ne_opt` / `trinity_noc2axi_router_nw_opt`
- 이 composite module은 Y=4 NOC2AXI와 Y=3 Router를 함께 span한다.
- X=1, X=2의 standalone `gen_router`는 empty placeholder다.

v9.4_0516의 통합본과 schematic map은 다음처럼 말한다.

```text
Row 0: NOC2AXI_NE_OPT  NOC2AXI_N_OPT  NOC2AXI_N_OPT  NOC2AXI_NW_OPT
Row 1: DISPATCH_E      ROUTER         ROUTER         DISPATCH_W
```

그리고 hierarchy에서는:

```text
trinity_noc2axi_n_opt x2
[FROM LLM] trinity_router는 N1B0에서 독립 인스턴스화되지 않고
NOC2AXI 내부 통합형(trinity_noc2axi_router_ne_opt)으로 존재
```

여기에는 두 가지 문제가 있다.

1. **표현이 내부적으로 충돌한다.** Grid는 `NOC2AXI_N_OPT x2`라고 하고, 설명은 `trinity_noc2axi_router_ne_opt` 내부 통합형이라고 한다.
2. **정답지의 N1B0 enum과 다르다.** 정답지는 X=1/X=2에 `NOC2AXI_ROUTER_NE_OPT`와 `NOC2AXI_ROUTER_NW_OPT`가 와야 한다.

가능한 해석은 둘 중 하나다.

| 가능성 | 판정 |
|---|---|
| `tt_20260516`에서 RTL이 실제로 baseline-like `NOC2AXI_N_OPT x2`로 바뀌었다 | snapshot 차이. 정답지와 직접 비교 불가. 산출물은 snapshot diff를 명시해야 함 |
| RAG가 `NOC2AXI_ROUTER_*_OPT`를 놓치고 `NOC2AXI_N_OPT`로 일반화했다 | 정답지 기준 major miss |

현재 문서만으로는 두 가능성을 구분할 evidence가 부족하다. 특히 Neptune이 없어서 instantiation tree로 확정할 수 없다. 그래서 이 항목은 v9.4_0516의 **최우선 검증 포인트**다.

---

## 5. Semantic/Schematic map 평가

사용자가 말한 "Symantic map"은 산출물에서는 `schematic_map`으로 제공된다. 이 리뷰에서는 같은 축으로 본다.

### 5.1 좋은 점

`v9.4_0516_schematic_map.md`는 실사용 가치가 있다.

| Map section | 좋은 점 |
|---|---|
| Chip-Level Grid | 4x5 layout, NOC2AXI row, dispatch/router row, Tensix rows를 한눈에 보여줌 |
| Mermaid/DOT | 문서와 시각화 양쪽으로 재사용 가능 |
| NIU Tile | `tt_noc2axi`, ATT/routing, mst_rd/wr, slv_wr, AXI clock domain, CDC, DFX, EDC bypass를 한 block으로 묶음 |
| Dispatch Tile | dispatch engine, L1 partition, overlay NOC wrap, FDS를 묶어 보여줌 |
| Tensix Tile | GPR, LLK/CB, compute, L1/LDM, EDC BIU를 개념적으로 정리 |
| NoC Fabric | dynamic routing, flit header, repeater, security fence를 한 map에 배치 |
| EDC Subsystem | APB, BIU, IRQ, mux/demux, register block 관계를 빠르게 보여줌 |
| Clock Domain Map | AI/NOC/AXI/DM clock domain을 분리해서 설명 |
| HTML | Interactive viewer로 발전시킬 수 있는 artifact가 생김 |

이 map은 설계 온보딩, 리뷰 회의, 검색 결과 브라우징에는 좋다. 특히 “RTL을 모르는 사람이 큰 그림을 잡는” 용도에서는 통합 HDD보다 더 유용할 수 있다.

### 5.2 부족한 점

아직 정답지형 exact schematic은 아니다.

| 부족한 점 | 설명 |
|---|---|
| EP index 없음 | 정답지는 EP=4/9/14/19, router EP=8/13 같은 endpoint index를 강하게 다룸 |
| composite tile 표현 불명확 | `NOC2AXI_N_OPT x2`와 router 내부 통합 설명이 충돌 |
| signal path 없음 | `clock_routing_out[x][y-1]`, `router_o_*`, `noc2axi_i/o_*_south`, `edc_egress/loopback`, `de_to_t6/t6_to_de`가 선으로 표현되지 않음 |
| Neptune provenance 없음 | `[FROM NEPTUNE]` 없이 Qdrant 추론 위주 |
| EDC ring topology 없음 | U-shape, segment A/B, per-column traversal order가 빠짐 |
| DFX wrapper chain 없음 | `tt_noc_niu_router_dfx -> tt_overlay_wrapper_dfx -> tt_instrn_engine_wrapper_dfx -> tt_t6_l1_partition_dfx`가 map에 없음 |
| NoC repeater 불완전 | NOC2AXI row NUM=4 repeaters만 보이고 router row NUM=6 repeaters가 빠짐 |

판정:

| 기준 | 점수 |
|---|---:|
| 구조 이해/온보딩 | 78~82% |
| 정답지 exact wiring 재현 | 45~50% |
| 시각화 artifact 가치 | 80% 내외 |
| DV/debug 실사용성 | 55~60% |

다음 단계는 module-level box map에서 **evidence-backed signal path map**으로 올라가는 것이다.

---

## 6. 섹션별 정답지 비교

### 6.1 Overview

v9.4_0516은 4x5 grid, 20 nodes, 12 Tensix, 4 NOC2AXI, 2 Dispatch, 2 Router를 맞춘다. 하지만 N1B0의 정체성인 `NOC2AXI_ROUTER_*_OPT` replacement가 Overview에서 빠져 있다.

판정: **70~73%**

### 6.2 Package Constants and Grid

SizeX/SizeY/NumNodes/NumTensix/NumNoc2Axi/NumDispatch 등 기본 상수는 좋다. 다만 정답지는 `GridConfig[y][x]`와 endpoint index table을 함께 제공한다. v9.4_0516은 Row/Col map은 있으나 EP table이 없다.

또한 정답지 기준 grid는:

```text
Y=4: NOC2AXI_NE_OPT  NOC2AXI_ROUTER_NE_OPT  NOC2AXI_ROUTER_NW_OPT  NOC2AXI_NW_OPT
Y=3: DISPATCH_E      ROUTER                 ROUTER                 DISPATCH_W
```

v9.4_0516은:

```text
Row 0: NOC2AXI_NE_OPT  NOC2AXI_N_OPT  NOC2AXI_N_OPT  NOC2AXI_NW_OPT
Row 1: DISPATCH_E      ROUTER         ROUTER         DISPATCH_W
```

이 차이는 snapshot 변화일 수도 있지만, 정답지 비교에서는 큰 mismatch다.

판정: **기본 상수 90%+, N1B0-specific grid 55~60%**

### 6.3 Top-Level Ports

이번 버전의 가장 좋은 섹션이다. SFR/PRTN 실명이 돌아왔다.

좋은 점:

- AXI/APB/EDC/SFR/PRTN/clock/reset category가 잡힌다.
- SFR 17 category가 정답지와 거의 맞는다.
- PRTN 실명이 대부분 복구됐다.

부족:

- 전체 count가 105로 나온다. 정답지 기준 `ISO_EN[11:0]` 포함 시 106이 맞다.
- EDC APB port는 category로는 좋지만 `[3:0]` per-column dimension과 각 width가 정답지처럼 완전하지 않다.
- AXI channel list는 요약형이라 ID/ADDR/DATA/USER width와 channel별 grouping이 부족하다.
- APB register interface도 8개 category 수준이지 정답지형 pinout은 아니다.

판정: **78~83%**

### 6.4 Module Hierarchy

v9.4a의 강점이 크게 빠진 부분이다.

v9.4_0516은 top-level children 정도는 말한다.

- `trinity_noc2axi_ne_opt`
- `trinity_noc2axi_n_opt x2`
- `trinity_noc2axi_nw_opt`
- `tt_dispatch_top_east/west`
- dispatch NIU router east/west
- `tt_trin_noc_niu_router_wrap`
- 12x Tensix

하지만 정답지의 핵심 hierarchy는 빠졌다.

- `trinity_noc2axi_router_ne_opt -> trinity_noc2axi_n_opt + trinity_router`
- `trinity_noc2axi_router_nw_opt -> trinity_noc2axi_n_opt + trinity_router`
- `trinity_router` internal `tt_router`
- router input/output IF
- `mem_wrap_*_router_input_*` VC buffers
- EDC node EP=8/13 and EP=9/14 split
- top-level EDC connector chain

판정: **55~62%**

### 6.5 NoC Fabric

좋은 점:

- `EnableDynamicRouting=1'b1`를 잡았다.
- Dynamic + Force DIM/DOR command relation을 잡았다.
- ATT mask/endpoint table 개념을 잡았다.
- `tt_noc2axi` 내부 block을 어느 정도 잡았다.
- inter-column repeater NUM=4 두 개를 잡았다.

부족:

- 정답지의 router row repeaters NUM=6 두 개가 빠졌다.
- EP index map이 빠졌다.
- dynamic routing header bit layout과 route slot 구조가 부족하다.
- `REQ_VCS`와 VC buffer SRAM macro detail이 부족하다.
- composite router internal north/south flit wiring이 빠졌다.

판정: **60~65%**

### 6.6 NIU / AXI Bridge

v9.4_0516은 NOC2AXI 4개와 `tt_noc2axi` block을 잡지만, 정답지의 `NOC2AXI_ROUTER_OPT` 특수성이 약하다.

특히 정답지의 핵심은:

- corner NOC2AXI와 middle composite NOC2AXI_ROUTER의 차이
- `noc2axi_*` prefix와 `router_*` prefix가 각각 Y=4/Y=3을 가리킴
- `router_o_ai_clk`, `router_o_dm_clk`, `router_o_nocclk`가 `clock_routing_out[x][y-1]`로 나감
- internal NOC2AXI south to Router north flit path

이 부분은 거의 빠져 있다.

판정: **45~52%**

### 6.7 Clock and Reset

clock domain 분류는 좋다. AI/NOC/DM/AXI를 분리했고, `clock_routing_in/out[x][y]`도 언급한다.

하지만 정답지는 clock routing exact behavior가 중요하다.

- `trinity_clock_routing_t` field 전체
- NOC2AXI_ROUTER middle tile exception
- Y=4 output이 직접 나가지 않고 Y=3 router output으로 내려가는 구조
- dispatch/tensix feedthrough chain
- reset vector dimensions

v9.4_0516은 이 중 일부만 잡았다.

판정: **65~70%**

### 6.8 EDC

v9.4_0516의 EDC topic은 APB/IRQ/status/BIU CSR는 괜찮다. 하지만 정답지의 EDC ring은 topology 문서다.

부족한 것:

- EDC ring traversal order
- column별 segment
- composite NOC2AXI_ROUTER tile의 Y=4/Y=3 two EDC node 구조
- `noc2axi_edc_egress_intf -> router_edc_ingress_intf`
- `router_loopback_edc_egress_intf -> noc2axi_loopback_edc_ingress_intf`
- external EDC port가 Y=3 router level로 exit하는 detail
- mesh config node id 192

판정: **60~68%**

### 6.9 Overlay / Compute / Dispatch

Overlay 문서는 firmware/API/DTS 쪽 인덱싱이 좋아진 느낌이 있다. 8x Rocket, FDS, command buffer, RoCC, LDM 주소 같은 내용은 유용하다.

정답지 `N1B0_NPU_HDD_v0.1.md` 기준으로는 아직 부족하다.

- Tensix datapath deep hierarchy 부족
- instruction engine / unpacker / packer / SFPU detail 부족
- dispatch feedthrough와 NOC NIU router detail 부족
- tile coordinate와 iDMA/L2 cache detail 부족

판정: **50~58%**

### 6.10 DFX

DFX는 이번 버전에서 가장 약하다.

정답지 기대:

- `tt_noc_niu_router_dfx`
- `tt_overlay_wrapper_dfx`
- `tt_instrn_engine_wrapper_dfx`
- `tt_t6_l1_partition_dfx`
- pass-through status
- IJTAG conditional absence
- wrapper chain placement

v9.4_0516:

- `TIEL_DFT_MODESCAN`
- DFTed RTL DEV07
- MBIST
- FB_INTF
- BDAed modules

이건 DFT/scan keyword는 잡았지만 N1B0 DFX hierarchy는 놓친 상태다.

판정: **25~35%**

---

## 7. v9.4a 대비 변화

| 항목 | v9.4a | v9.4_0516 | 판정 |
|---|---|---|---|
| Pipeline | `tt_20260221` | `tt_20260516` | 새 snapshot |
| 최종 HDD 분량 | 1239 lines | 271 lines | 크게 축소 |
| Neptune | 있음 | 없음 | 큰 회귀 |
| SFR 실명 | 약함 | 강함 | 개선 |
| PRTN 실명 | 약함 | 강함, 단 `ISO_EN` 누락 | 개선 |
| Semantic/Schematic map | `.md` | `.md` + `.html` | artifact 개선 |
| exact hierarchy | 강함 | 약함 | 회귀 |
| DFX | 부분 복구 | 거의 미복구 | 회귀 |
| EDC ring | Neptune 기반 일부 존재 | topology gap 명시 | 회귀 |
| NoC repeater | 더 풍부 | NOC2AXI row 위주 | 회귀 |
| hallucination | 낮음 | 낮음 | 유지 |

v9.4_0516의 품질 저하는 모델이 갑자기 나빠졌다기보다 **graph evidence가 빠진 상태에서 final merge가 요약형으로 돌아간 것**에 가깝다.

---

## 8. 리스크와 해석상 주의

### 8.1 정답지와 snapshot mismatch

정답지는 `tt_20260221` 또는 기존 `used_in_n1` N1B0 해석에 맞춰져 있고, v9.4_0516은 `tt_20260516`을 사용한다. 따라서 grid row 표기와 module name이 실제 RTL 변경일 수 있다.

하지만 산출물이 `Trinity N1B0 NPU`를 표방하고 정답지와 비교되는 이상, 다음 둘은 반드시 별도 diff로 확정해야 한다.

1. `NOC2AXI_ROUTER_NE/NW_OPT`가 실제로 `tt_20260516`에서 사라졌는가?
2. `ISO_EN[11:0]`가 실제로 top port에서 제거됐는가?

이 두 개가 snapshot 변화라면 정답지를 업데이트해야 하고, RAG 누락이라면 parser/graph를 고쳐야 한다.

### 8.2 Schematic map은 "정답"이 아니라 "index map"

현재 map은 검색 결과를 사람이 읽기 좋게 만든 index map이다. DV/debug 용도라면 signal-level path가 필요하다.

필수 보강:

- node마다 RTL file, instance path, source line, confidence
- edge마다 `CONNECTS_TO` evidence, port binding, signal name
- composite module은 collapsed/expanded view 둘 다 제공
- EP index와 coordinate transform 표시
- snapshot id와 graph load status 표시

---

## 9. v9.5 권고

우선순위는 명확하다.

### 9.1 tt_20260516 Neptune 적재

가장 먼저 해야 한다. 현재 산출물의 약점 대부분은 graph absence에서 나온다.

복구 예상:

- `trinity_noc2axi_router_ne/nw_opt` instantiation 확정
- `tt_noc2axi` 내부 submodule tree
- EDC ring connector/mux/repeater hierarchy
- DFX wrapper chain
- NoC repeater instance count
- dispatch/tensix internal hierarchy

예상 효과: **+8~10pp**

### 9.2 Composite tile verifier 추가

N1B0에서 가장 중요한 구조는 composite tile이다. 별도 rule로 검증해야 한다.

체크:

- GridConfig에 `NOC2AXI_ROUTER_NE_OPT` / `NOC2AXI_ROUTER_NW_OPT` 존재 여부
- `trinity_noc2axi_router_*_opt` module 존재 여부
- 내부 `trinity_noc2axi_n_opt` + `trinity_router` instantiation 여부
- `router_o_*` clock/reset outputs가 `clock_routing_out[x][y-1]`로 연결되는지
- EP 9/14와 EP 8/13 split 여부

이건 generic RAG query보다 deterministic verifier로 푸는 게 낫다.

### 9.3 Top port count gate

final HDD 생성 전에 top port table을 gate로 검증해야 한다.

체크:

- total port count
- category count
- `SFR_*` 실명 count
- `PRTNUN_*` 실명 count
- `ISO_EN[11:0]` presence
- APB/EDC/AXI width and array dimensions

이번 버전은 SFR/PRTN이 좋아졌으니, 여기에 `ISO_EN`만 잡으면 top port 품질이 한 단계 올라간다.

### 9.4 Semantic map을 signal map으로 확장

현재 map은 box diagram이다. 다음에는 graph export와 연결해서 edge evidence를 넣어야 한다.

필수 edge:

- NOC2AXI south to Router north flit path
- Router north to NOC2AXI south return path
- `clock_routing_in/out` cascade
- `router_o_*` to `clock_routing_out[x][y-1]`
- EDC egress/ingress/loopback
- PRTN column daisy chain
- dispatch to Tensix feedthrough

이게 들어가면 schematic map은 단순 부록이 아니라 RAG 검색 성능 자체를 끌어올리는 index가 된다.

### 9.5 Final merge density guard

v9.4a에서 통합본이 1239 lines였고, v9.4_0516은 271 lines다. 통합본이 너무 얇아지면 topic 문서가 좋아도 최종 산출물 점수가 떨어진다.

권장 guard:

- final HDD minimum table rows
- required sections minimum content
- topic-to-final propagation checklist
- Known gaps와 evidence coverage matrix 동시 출력
- final HDD에서 schematic map summary 자동 삽입

---

## 10. 최종 판정

v9.4_0516은 **검색성 개선의 씨앗은 확실히 보이지만, 최종 HDD 품질은 v9.4a보다 낮다.**

가장 긍정적인 신호는 SFR/PRTN 실명 복구다. 이건 "RTL RAG가 진짜 RTL 이름을 찾아준다"는 사용감으로 바로 연결된다. 반대로 가장 큰 약점은 Neptune 미적재와 composite tile 불확정이다. 정답지의 N1B0 핵심은 `NOC2AXI_ROUTER_NE/NW_OPT`인데, 이걸 확정하지 못하면 아무리 map이 예뻐도 정답지 점수는 올라가기 어렵다.

v9.5의 승부처는 명확하다.

1. `tt_20260516`을 Neptune에 적재한다.
2. `NOC2AXI_ROUTER_*_OPT` composite verifier를 추가한다.
3. `ISO_EN[11:0]`를 포함한 top port gate를 만든다.
4. schematic map을 source-backed signal map으로 확장한다.
5. final merge가 topic 문서의 detail을 잃지 않도록 density guard를 둔다.

이 5개가 들어가면, v9.4_0516의 SFR/PRTN 개선 위에 v9.4a의 graph hierarchy가 다시 붙는다. 그 경우 정답지 기준 **74~78%**, folder best-of 기준 **80% 전후**까지는 현실적이다.
