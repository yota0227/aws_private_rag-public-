# Codex Review: RAG v9.4a 정답지 비교 분석

**작성일:** 2026-05-19  
**리뷰어:** Codex  
**비교 대상:** `test_rtl/rag_result/v9.4a/v9.4a_N1B0_HDD.md` 중심, `v9.4a_schematic_map.md` 및 topic 문서 보조 비교  
**저장 위치:** `test_rtl/rag_result/review/codex_review_v9.4a.md`  

---

## 0. 결론

v9.4a는 v9.4의 가장 큰 문제였던 **최종 통합 HDD 압축 회귀**를 크게 복구했다. v9.4 통합본은 323 lines / 130 table rows에 불과했지만, v9.4a 통합본은 1240 lines / 435 table rows로 증가했다. 정답지 `N1B0_NPU_HDD_v0.1.md`의 1291 lines / 303 table rows와 거의 같은 체급까지 올라왔다.

이번 버전의 핵심 변화는 **Neptune Graph DB 기반 계층 정보**와 **Semantic/Schematic map**이다. 이 추가는 효과가 있다. 특히 다음 항목은 v9.4 대비 명확히 좋아졌다.

1. `trinity_noc2axi_router_ne/nw_opt -> trinity_noc2axi_n_opt + trinity_router` composite 구조가 통합본 본문에 직접 들어왔다.
2. `tt_noc_repeaters [x4]`, top-level `tt_edc1_intf_connector [x2]`, `tt_noc2axi` 내부 14개 submodule, `tt_neo_overlay_wrapper`의 EDC mux/repeater, dispatch 내부 hierarchy가 Neptune evidence로 추가됐다.
3. `v9.4a_schematic_map.md`가 grid, Tensix, NIU, Dispatch, EDC ring, clock domain, data flow를 시각적으로 분리해서 보여준다. 설계자 온보딩/리뷰용으로는 v9.4보다 훨씬 읽기 쉽다.

하지만 정답지와 비교하면 아직 결정적인 gap이 남아 있다. v9.4a는 **module hierarchy와 subsystem map은 좋아졌지만, signal-level wiring은 여전히 부족**하다. 특히 정답지의 핵심인 `clock_routing_in/out`, `router_o_*`, `noc2axi_i_*`, `de_to_t6/t6_to_de`, `PRTNUN_*`, `ISO_EN[11:0]`, exact NoC repeater instance names/counts, DFX 4-wrapper chain은 최종 HDD에 충분히 복구되지 않았다.

한 문장으로 요약하면:

> **v9.4a는 v9.4에서 무너진 final merge를 회복하고 Semantic map으로 구조 이해력을 크게 올린 버전이다. 다만 "정답지형 HDD"가 되려면 Neptune hierarchy를 넘어서 exact port binding / signal path evidence를 본문에 넣어야 한다.**

점수는 다음처럼 본다.

| 평가 기준 | v9.4 | v9.4a | 판정 |
|---|---:|---:|---|
| 통합 HDD 단독, 기본 `N1B0_HDD_v0.1.md` 기준 | 64~67% | **76~79%** | 크게 개선 |
| 통합 HDD 단독, `N1B0_NPU_HDD_v0.1.md` 기준 | 55~58% | **68~72%** | 개선, 단 NPU deep detail 부족 |
| v9.4a 폴더 전체 best-of 기준 | 74~77% | **80~84%** | 개선 |
| KB/Neptune strict 구조 기준 | 70~73% | **82~86%** | 크게 개선 |
| Semantic/Schematic map 유용성 | 없음 | **온보딩/구조 이해 80%+, exact wiring 55~60%** | 신규 가치 있음 |

---

## 1. 참고한 파일

### 정답지

| 파일 | 역할 |
|---|---|
| `test_rtl/Sample/ORG/N1B0_HDD_v0.1.md` | 기본 N1B0 top-level 정답지 |
| `test_rtl/Sample/ORG/N1B0_NPU_HDD_v0.1.md` | NPU/Overlay/DFX 확장 정답지 |
| `test_rtl/Sample/ORG/N1B0_DFX_HDD_v0.1.md` | DFX wrapper chain 및 IJTAG 조건 비교 기준 |
| `test_rtl/Sample/ORG/N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` | composite NIU/router dual-row wiring 비교 기준 |

### v9.4a 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v9.4a/v9.4a_N1B0_HDD.md` | 최종 통합 HDD |
| `test_rtl/rag_result/v9.4a/v9.4a_chip_no_grounding.md` | KB + Neptune 중심 raw output |
| `test_rtl/rag_result/v9.4a/v9.4a_chip_grounded.md` | grounded 보강 문서 |
| `test_rtl/rag_result/v9.4a/v9.4a_edc.md` | EDC topic |
| `test_rtl/rag_result/v9.4a/v9.4a_noc.md` | NoC topic |
| `test_rtl/rag_result/v9.4a/v9.4a_overlay.md` | Overlay topic |
| `test_rtl/rag_result/v9.4a/v9.4a_schematic_map.md` | Semantic/Schematic map 문서 |
| `test_rtl/rag_result/v9.4a/v9.4a_grid.dot` / `.png` | Graphviz grid visualization |

---

## 2. 정량 비교

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[FROM LLM]` | `[NOT IN KB]` | `[TBC]` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 정답지 `N1B0_HDD_v0.1.md` | 514 | 22330 | 40 | 186 | 24 | 0 | 0 | 0 |
| 정답지 `N1B0_NPU_HDD_v0.1.md` | 1291 | 58380 | 105 | 303 | 52 | 0 | 0 | 0 |
| 정답지 `N1B0_DFX_HDD_v0.1.md` | 253 | 10353 | 12 | 52 | 12 | 0 | 0 | 0 |
| 정답지 `N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` | 279 | 13815 | 18 | 61 | 12 | 0 | 0 | 0 |
| v9.4 `v9.4_N1B0_HDD.md` | 323 | 8955 | 38 | 130 | 6 | 3 | 1 | 0 |
| **v9.4a `v9.4a_N1B0_HDD.md`** | **1240** | **47721** | **130** | **435** | **44** | **12** | **0** | **0** |
| v9.4a `chip_no_grounding` | 702 | 25466 | 64 | 279 | 24 | 0 | 0 | 0 |
| v9.4a `chip_grounded` | 432 | 16024 | 39 | 103 | 14 | 13 | 0 | 0 |
| v9.4a `edc` | 261 | 8994 | 32 | 71 | 18 | 0 | 0 | 0 |
| v9.4a `noc` | 265 | 8961 | 35 | 82 | 6 | 0 | 0 | 0 |
| v9.4a `overlay` | 226 | 7436 | 31 | 56 | 6 | 0 | 0 | 0 |
| v9.4a `schematic_map` | 352 | 13217 | 13 | 20 | 18 | 0 | 0 | 0 |

해석:

- v9.4a 통합본은 v9.4 대비 약 **3.8배** 길어졌고, table rows는 **130 -> 435**로 늘었다.
- 통합본이 `chip_no_grounding`보다 더 크다. v9.4에서 지적한 "raw KB보다 final HDD가 빈약한 문제"는 해소됐다.
- code fence 44개는 정답지 `N1B0_NPU_HDD_v0.1.md`의 52개에 근접한다. hierarchy/map/flow snippet의 가시성이 좋아졌다.
- `[FROM LLM]`은 통합본 12개로 남아 있으나, v9.4보다 출처 태그가 더 잘 보존된다.
- `[FROM NEPTUNE]` 태그가 대량 추가되어 hierarchy와 map의 provenance가 분리된 점은 좋은 변화다.

---

## 3. v9.4 -> v9.4a 핵심 변화

| 축 | v9.4 | v9.4a | 판정 |
|---|---|---|---|
| 통합 HDD 크기 | 323 lines / 130 rows | 1240 lines / 435 rows | 대폭 개선 |
| KB-only 산출물 | 512 lines / 264 rows | 702 lines / 279 rows | 개선 |
| Neptune hierarchy | 없음 | depth 3 instantiation tree | 신규 |
| Semantic/Schematic map | 없음 | grid, Tensix, NIU, Dispatch, EDC, clock, data flow | 신규 |
| EDC topic | 398 lines / 121 rows | 261 lines / 71 rows | topic 단독은 축소, 통합본 흡수 |
| NoC topic | 200 lines / 68 rows | 265 lines / 82 rows | 개선 |
| Overlay topic | 138 lines / 44 rows | 226 lines / 56 rows | 개선 |
| `tt_noc_repeaters [x4]` | 없음 | Neptune evidence | 개선 |
| `tt_noc2axi` 내부 hierarchy | 제한적 | 14 submodules | 개선 |
| DFX | generic DFT 중심 | noc2axi DFX partition 추가 | 부분 개선 |
| exact signal wiring | 약함 | 여전히 약함 | 미해결 |

---

## 4. Semantic/Schematic Map 평가

### 4.1 좋아진 점

`v9.4a_schematic_map.md`는 이전 버전 대비 실제 리뷰/온보딩 가치가 있다.

| Map | 좋은 점 |
|---|---|
| Chip-Level Grid | 20 EP layout, empty router placeholder, 4 AXI exits를 한눈에 보여줌 |
| Tensix Tile | overlay, L1 partition, instruction engine, EDC nodes를 한 그림에 배치 |
| NIU Tile | `tt_noc2axi` 내부 router/NIU/AXI clock/CDC/DFX/EDC 구조를 보여줌 |
| Dispatch Tile | dispatch L1 partition, DFX, overlay wrap, FDS를 분리 |
| EDC Ring | top/NIU/Tensix/Overlay/Dispatch/NoC repeater segment를 통합 |
| Clock Domain Map | `ai_clk`, `noc_clk`, `axi_clk`, `ref_clk`, `dm_clk`를 분리 |
| Data Flow | External AXI, NoC mesh, Tensix, Dispatch, Overlay 관계를 요약 |

특히 `tt_noc2axi` 내부 그림은 v9.4 이전에는 문장으로만 흩어져 있던 정보를 하나의 구조로 묶었다. BHRC나 SOC 엔지니어에게 설명할 때는 이 map이 큰 도움이 된다.

### 4.2 주의할 점

다만 이 map을 "정답지 수준의 wiring map"으로 보면 안 된다.

| 이슈 | 설명 |
|---|---|
| X/Y 축 관례 혼동 | 그림은 X를 행(row), Y를 열(column)처럼 배치한다. 정답지는 보통 `GridConfig[y][x]` 형태라 Y row / X column 관례로 읽힌다. |
| Empty router를 링크 중간에 그림 | EP8/EP13을 dashed empty로 표시한 것은 좋지만, NoC mesh link가 empty router box를 지나가는 것처럼 보일 수 있다. 실제로는 composite router logic 안에서 처리된다는 주석이 더 필요하다. |
| AXI arrow overlap | `v9.4a_grid.png`는 빨간 AXI 화살표와 label이 겹쳐 가독성이 떨어진다. |
| signal-level path 없음 | `clock_routing`, `de_to_t6`, `edc_ingress/egress`, NoC flit repeater 경로가 exact signal path로 표시되지 않는다. |
| semantic vs schematic 용어 | 파일명은 schematic map이고, 사용자는 Semantic map이라고 부른다. 둘을 혼용하지 않도록 다음 버전에서 명칭을 고정하는 것이 좋다. |

판정:

- **구조 이해/온보딩:** 80~85%
- **정답지 exact wiring 재현:** 55~60%
- **다음 단계:** module box map에서 signal path map으로 확장 필요

---

## 5. 섹션별 정답지 비교

### 5.1 Overview

v9.4a:

- Trinity N1B0, 4x5 mesh, 20 endpoints, 12 Tensix, top module, RTL source를 정확히 유지한다.
- Neptune/KB/LLM provenance convention을 문서 첫머리에 둔 점이 좋다.
- v9.4보다 문서 전체가 N1B0-specific 구조를 더 많이 담는다.

부족:

- Overview 자체에는 아직 정답지의 첫 문장에 해당하는 핵심이 부족하다:
  - baseline `trinity_noc2axi_n_opt + trinity_router` pair가
  - N1B0에서 `trinity_noc2axi_router_ne/nw_opt` composite tile로 교체됨
  - composite tile이 Y=4 + Y=3 두 물리 row를 span함
- 이 내용은 §4와 §7에 분산되어 있으나 Overview에서 바로 보여야 한다.

판정: **약 75%**

### 5.2 Package Constants and Grid

v9.4a:

- EP index table은 정확하다.
- grid layout과 schematic map이 추가되어 v9.4 대비 훨씬 좋다.
- EP8/EP13 ROUTER placeholder와 `trinity_router` not instantiated note가 유지된다.

부족:

- `GridConfig[y][x]` 정답지형 ASCII가 아니라 X를 행으로 둔 전치 형태다. 사람이 읽을 때 물리 방향을 헷갈릴 수 있다.
- helper functions가 여전히 빠졌다:
  - `getTensixIndex`
  - `getNoc2AxiIndex`
  - `getApbIndex`
  - `getDmIndex`
  - `isEastEdge`, `isNorthEdge`
- `ROUTER` enum이 placeholder이고 실제 router logic이 composite 내부의 Y=3 역할을 수행한다는 설명은 있으나, package section에서 더 명시할 필요가 있다.

판정: **통합본 약 82%, map 포함 약 86%**

### 5.3 Top-Level Ports

v9.4a:

- instance binding 일부와 top-level port categories를 유지한다.
- `edc_apb_penable`, `o_reg_prdata` 같은 일부 binding이 v9.4보다 낫다.

부족:

- 여전히 정답지의 top-level port list를 복구하지 못했다.
- 특히 다음이 없다:
  - `PRTNUN_FC2UN_*`
  - `PRTNUN_UN2FC_*`
  - `ISO_EN[11:0]`
  - full AXI channel list with widths
  - APB register interface dimensions
  - reset vectors and DM reset dimensions
- Top-Level Port Categories는 `[FROM LLM]`이며, 실명 pinout 대체물로는 부족하다.

판정: **약 55~60%**

### 5.4 Module Hierarchy

v9.4a 개선:

- 이번 버전의 가장 큰 성과 중 하나다.
- Neptune hierarchy가 다음을 직접 보여준다:
  - `trinity_noc2axi_router_ne_opt -> trinity_noc2axi_n_opt + trinity_router`
  - `trinity_noc2axi_router_nw_opt -> trinity_noc2axi_n_opt + trinity_router`
  - corner NIU의 `tt_edc1_noc_sec_controller`, `tt_noc2axi`, `tt_noc_overlay_edc_repeater`, `tt_edc1_biu_soc_apb4_wrap`
  - `tt_noc_repeaters [x4]`
  - top-level `tt_edc1_intf_connector [x2]`
  - dispatch internal `tt_disp_eng_l1_partition_dfx`
  - overlay internal `tt_edc1_serial_bus_mux`

부족:

- 정답지의 `gen_x[1] gen_y[4]: gen_noc2axi_router_ne_opt` 같은 generate hierarchy는 아직 없다.
- "top-level `trinity_router`는 not instantiated"와 "composite 내부에는 `trinity_router`가 있다"가 동시에 나오므로, 표현을 더 엄밀하게 해야 한다.
  - 좋은 표현: "standalone `gen_router` block is empty; `trinity_router` logic/module is instantiated inside `trinity_noc2axi_router_*_opt`."
- `NOC2AXI_ROUTER_*_OPT` dual-row physical mapping은 언급되지만 signal-level port group table이 부족하다.

판정: **통합본 약 80%, 정답지 generate detail 기준 약 72%**

### 5.5 Compute Tile / Tensix / Overlay

v9.4a 개선:

- RISC-V parameters와 memory map은 v9.4 수준을 유지한다.
- Tensix tile map에 overlay, L1 partition, instruction engine, EDC nodes가 같이 들어왔다.
- Overlay topic이 v9.4보다 회복됐다.
- `tt_trin_noc_niu_router_wrap`, `tt_edc1_serial_bus_mux`, overlay EDC repeaters가 Neptune evidence로 추가됐다.

부족:

- 정답지 NPU HDD의 deep compute hierarchy는 아직 부족하다:
  - BRISC/TRISC/NCRISC 세부 hierarchy
  - FPU G-Tile/M-Tile
  - DEST/SRCA/SRCB register implementation
  - L1 SRAM 16-bank detail
  - instruction engine DFX placement
- "5 RISC-V cores" 같은 execution model은 `[FROM LLM]`이며, KB/Neptune fact와 분리해야 한다.

판정:

- **통합본 단독:** 약 68~72%
- **NPU 정답지 deep hierarchy 기준:** 약 62~66%

### 5.6 Dispatch Engine

v9.4a 개선:

- dispatch internal hierarchy가 추가됐다:
  - `tt_dispatch_engine`
  - `tt_disp_eng_l1_partition`
  - `tt_disp_eng_l1_partition_dfx`
  - `tt_disp_eng_l1_wrap2`
  - `tt_edc1_serial_bus_repeater [x4]`
  - `tt_disp_eng_overlay_noc_wrap`
  - `tt_disp_eng_overlay_noc_niu_router`
- FDS module table이 들어왔다.

부족:

- 정답지의 dispatch feedthrough signal arrays는 여전히 없다:
  - `de_to_t6_coloumn[SizeX][SizeY-1][2]`
  - `de_to_t6_east/west[SizeX]`
  - `t6_to_de[SizeX][SizeY-2]`
  - `t6_to_de_accross_east/west[SizeX][SizeX]`
- `NOC2AXI_ROUTER_*_OPT`가 feedthrough를 carry한다는 exact port mapping도 없다.
- v9.3에서 문제였던 symbolic dimension regression을 v9.4a가 고쳤다는 증거가 없다.

판정: **구조 기준 약 70%, 정답지 feedthrough 기준 약 45~50%**

### 5.7 NoC Fabric

v9.4a 개선:

- `tt_noc_repeaters [x4]`가 Neptune evidence로 추가됐다.
- `tt_noc2axi` 내부 hierarchy가 매우 좋아졌다:
  - `tt_router`
  - `tt_noc2axi_niu`
  - `tt_noc2axi_axiclk_domain`
  - `tt_noc2axi_dfx_axi_clk`
  - `tt_noc2axi_dfx_noc_clk`
  - `tt_upf_async_fifo`
  - `tt_noc_sync3_pulse [x3]`
  - `tt_sync_reset_powergood [x3]`
  - `tt_noc_reset_clk_tracker`
- Semantic map에서 NoC mesh와 AXI exits가 가시화됐다.

부족:

- 정답지의 exact repeater instance names가 없다:
  - `noc_east2west_req_repeaters_between_noc2axi`
  - `noc_west2east_req_repeaters_between_noc2axi`
  - `noc_east2west_req_repeaters_between_router`
  - `noc_west2east_req_repeaters_between_router`
- 4-stage at Y=4, 6-stage at Y=3 count가 없다.
- manual X-axis assign topology와 exact flit path가 없다.
- "tt_router embedded in each tt_noc2axi" 설명은 유용하지만, N1B0 composite router tile의 Y=3/Y=4 port split을 대체하지는 못한다.

판정:

- **NoC module inventory:** 약 80%
- **N1B0 exact topology:** 약 62~66%

### 5.8 NIU / NOC2AXI_ROUTER_OPT

v9.4a 개선:

- `trinity_noc2axi_router_ne/nw_opt`가 `trinity_noc2axi_n_opt + trinity_router`로 구성된다는 점이 본문에 들어왔다.
- `tt_noc2axi` 내부 block decomposition은 매우 좋아졌다.
- NE/NW asymmetry, EDC repeater count, NoC/AXI clock domain separation이 추가됐다.

부족:

- 정답지 `N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md`의 핵심 signal-level table은 아직 없다:
  - `noc2axi_i_*` / `noc2axi_o_*` = Y=4
  - `router_i_*` / `router_o_*` = Y=3
  - internal flit cross-wires
  - `noc2axi_clock_routing_out -> router_clock_routing_in`
  - EDC forward path / loopback path
  - `REP_DEPTH_LOOPBACK=6`, `REP_DEPTH_OUTPUT=4`
  - west/south repeater counts
- `router_o_*`와 `noc2axi_i_*` 문자열이 통합본에 사실상 없다. 이는 정답지의 router-opt 세부 설명을 아직 회수하지 못했다는 강한 신호다.

판정:

- **module composition:** 약 78%
- **router-opt HDD exact wiring:** 약 45~50%

### 5.9 Clock / Reset

v9.4a 개선:

- clock domain separation이 좋아졌다.
- `tt_noc2axi` 내부 NoC/AXI domain, CDC modules, `tt_noc_reset_clk_tracker`가 Neptune evidence로 추가됐다.
- clock domain map은 이해에 도움이 된다.

부족:

- 정답지의 `trinity_clock_routing_t` struct가 없다.
- `clock_routing_in[SizeX][SizeY]` / `clock_routing_out[SizeX][SizeY]`가 없다.
- clock entry point가 없다:
  - `clock_routing_in[x][4].ai_clk = i_ai_clk[x]`
  - `clock_routing_in[x][4].dm_clk = i_dm_clk[x]`
  - `clock_routing_in[x][4].power_good = i_edc_reset_n`
- `NOC2AXI_ROUTER_*_OPT` clock exception이 없다:
  - Y=4 middle tile has no `clock_routing_out[x][4]`
  - `router_o_*` drives `clock_routing_out[x][3]`
- reset packing semantics도 없다.

판정:

- **clock domain inventory:** 약 76%
- **N1B0 clock routing 정답지 기준:** 약 50~55%

### 5.10 EDC

v9.4a 개선:

- 통합본에 EDC full-chip segment view가 들어왔다.
- Neptune evidence가 다음을 보여준다:
  - top-level `tt_edc1_intf_connector [x2]`
  - `apb_cdc_n2a`
  - `tt_axi_err`
  - NIU EDC segment
  - Tensix L1 EDC connectors
  - Overlay `tt_edc1_serial_bus_mux`
  - Dispatch EDC repeaters
  - NoC repeater EDC connectors
- EDC coverage summary table은 v9.4보다 훨씬 좋다.

부족:

- 정답지의 flat array names가 없다:
  - `edc_ingress_intf[SizeX*SizeY]`
  - `edc_egress_intf[SizeX*SizeY]`
  - `loopback_edc_ingress_intf`
  - `loopback_edc_egress_intf`
- `NOC2AXI_ROUTER_*_OPT` EDC exception이 없다:
  - Y=4 position에는 EDC interface 없음
  - Y=3 index만 외부 ring에 연결
- EDC path가 high-level subsystem map으로는 좋지만, exact connector indexing은 부족하다.

판정:

- **subsystem map 기준:** 약 85%
- **정답지 exact ring/index 기준:** 약 68~72%

### 5.11 Power / PRTN / ISO_EN

v9.4a:

- v9.4 대비 큰 개선이 없다.
- Known gaps에 power domain map이 남아 있다.

부족:

- 정답지의 PRTN port 실명이 없다:
  - `PRTNUN_FC2UN_DATA_IN`
  - `PRTNUN_FC2UN_READY_IN`
  - `PRTNUN_FC2UN_CLK_IN`
  - `PRTNUN_FC2UN_RSTN_IN`
  - `PRTNUN_UN2FC_DATA_OUT[3:0]`
  - `PRTNUN_UN2FC_INTR_OUT[3:0]`
- `ISO_EN[11:0]` bit mapping이 없다:
  - `ISO_EN[x + 4*y]`
  - Y=0 `[3:0]`, Y=1 `[7:4]`, Y=2 `[11:8]`
- dispatch tiles are not in PRTN chain이라는 정답지 핵심도 없다.

판정: **약 30~35%**

### 5.12 SRAM / SFR

v9.4a:

- SRAM macro table은 유지된다.
- NoC router/NIU SRAMs는 어느 정도 설명된다.

부족:

- NPU 정답지의 per-tile SRAM inventory, L1 16-bank, context SRAM, L2 directory SRAM detail은 부족하다.
- SFR memory config 13개 category는 있지만 실명 signal table은 없다.
- memory macro physical dimension과 logical width 표현이 혼재될 수 있어 주의가 필요하다.

판정: **약 55~60%**

### 5.13 DFX

v9.4a 개선:

- `tt_noc2axi_dfx_axi_clk`, `tt_noc2axi_dfx_noc_clk`가 Neptune evidence로 들어왔다.
- DFX clock-domain partitioning 설명은 v9.4보다 낫다.
- dispatch side `tt_disp_eng_l1_partition_dfx`도 보인다.

부족:

- 정답지의 N1B0 DFX 4-wrapper chain은 아직 아니다:
  - `tt_noc_niu_router_dfx`
  - `tt_overlay_wrapper_dfx`
  - `tt_instrn_engine_wrapper_dfx`
  - `tt_t6_l1_partition_dfx`
- 통합본에는 위 네 이름이 거의 나오지 않는다.
- clock pass-through counts가 없다:
  - NIU/router 5 clocks
  - overlay 5 clocks
  - instruction engine 1 clock
  - L1 partition 2->3 clocks
- IJTAG absent/ifdef condition도 없다.

판정:

- **generic DFT/DFX inventory:** 약 60%
- **N1B0 DFX 정답지 기준:** 약 42~48%

---

## 6. 주요 개선점

| 개선 | 의미 |
|---|---|
| Final HDD size 회복 | v9.4의 압축 회귀를 해결 |
| Neptune provenance | hierarchy와 inferred text를 구분 가능 |
| `tt_noc2axi` internal hierarchy | NoC/AXI/CDC/DFX/EDC block decomposition이 명확해짐 |
| `tt_noc_repeaters [x4]` | 기존 NoC repeater gap 일부 해소 |
| top-level EDC connectors | EDC full-chip map이 좋아짐 |
| Semantic/Schematic map | SOC 엔지니어가 구조를 빠르게 이해 가능 |
| Source Traceability / Delta Summary | 리뷰와 디버깅에 도움 |

---

## 7. 주요 위험 / 회귀 / 과대평가 포인트

| 항목 | 위험 |
|---|---|
| `trinity_router` 표현 | "not instantiated"와 "inside composite"가 같이 나오므로 standalone vs internal instantiation을 분리해야 함 |
| Semantic map axis | X/Y가 정답지 관례와 다르게 보일 수 있음 |
| Empty router drawing | EP8/EP13 empty box를 mesh link가 통과하는 것처럼 보여 실제 path 오해 가능 |
| `FROM LLM` execution model | 5 RISC-V cores, architecture purpose 등은 검증 태그가 필요 |
| DFX confidence | generic DFT는 늘었지만 정답지의 4-wrapper chain은 아직 없음 |
| Signal-level gap | 문서량은 늘었지만 `clock_routing`, `de_to_t6`, `PRTNUN`, `ISO_EN`이 거의 없음 |

---

## 8. 남은 핵심 Gap

| # | Gap | 정답지 위치 | v9.4a 상태 | 해결 경로 | 예상 효과 |
|---|---|---|---|---|---:|
| 1 | `clock_routing_in/out` exact routing | HDD §6, NPU §9 | clock domain map은 있으나 routing struct 없음 | struct/assign parser + clock template | +4~6pp |
| 2 | `NOC2AXI_ROUTER_*_OPT` signal wiring | Router OPT HDD | hierarchy는 있음, port prefix/wire 없음 | port binding + internal assign extraction | +5~7pp |
| 3 | Dispatch feedthrough | HDD §8 | hierarchy만 있음 | `de_to_t6/t6_to_de` array parser | +3~5pp |
| 4 | PRTN/ISO_EN 실명 | HDD §3/9, NPU §12 | 거의 미반영 | top port full extraction + no-compress rule | +3~5pp |
| 5 | DFX 4-wrapper chain | DFX HDD, NPU §14 | noc2axi DFX 중심, Tensix 4-wrapper 미흡 | `used_in_n1/rtl/dfx/*` parser | +5~7pp |
| 6 | NoC repeater exact names/counts | HDD §5/7 | `tt_noc_repeaters [x4]`만 있음 | instance-name preserving extraction | +2~4pp |
| 7 | EDC flat arrays/router exception | HDD §7, NPU §11 | subsystem map은 좋음, flat array 없음 | EDC array/index parser | +3~4pp |
| 8 | Semantic map signal overlay | 신규 | module box 중심 | signal path layer 추가 | +4~6pp |
| 9 | X/Y convention normalization | map | 전치 표현 위험 | `GridConfig[y][x]` canonical map 병기 | 품질/가독성 |
| 10 | LLM claims gating | 전체 | 12개 LLM tag | CI에서 ungrounded claims 제한 | 신뢰도 |

---

## 9. v9.4a 종합 점수

| 기준 | v9.4 Codex | v9.4a Codex | 변화 |
|---|---:|---:|---|
| 통합 HDD 단독, 기본 N1B0 HDD 기준 | 64~67% | **76~79%** | +12pp 내외 |
| 통합 HDD 단독, NPU HDD 기준 | 55~58% | **68~72%** | +13pp 내외 |
| 산출물 전체 best-of | 74~77% | **80~84%** | +6pp 내외 |
| KB/Neptune strict 구조 기준 | 70~73% | **82~86%** | +12pp 내외 |
| DFX 정답지 기준 | 35~50% | **42~48%** | 소폭 개선 |
| Router OPT exact wiring 기준 | 40~48% | **45~50%** | 소폭 개선 |

왜 점수가 크게 올랐나:

- 최종 통합본이 다시 정답지 체급으로 커졌다.
- Neptune hierarchy가 module-level 구조 gap을 많이 메웠다.
- Semantic map이 grid/subsystem understanding을 크게 개선했다.

왜 80% 중후반까지는 못 주나:

- 정답지의 핵심은 단순 계층이 아니라 **정확한 RTL signal wiring**이다.
- v9.4a는 hierarchy/map 중심이며, port binding/path extraction은 아직 부족하다.
- PRTN/ISO_EN/DFX/router-opt/clock-routing 같은 v9.3부터 남은 hard gap이 여전히 남아 있다.

---

## 10. v9.5 권장 방향

### 10.1 Semantic map을 signal-path map으로 확장

현재 map은 module box 중심이다. 다음 버전에서는 별도 layer로 exact signal path를 올려야 한다.

| Map Layer | 필요한 예 |
|---|---|
| Clock | `i_ai_clk[x] -> clock_routing_in[x][4] -> router_o_ai_clk -> clock_routing_out[x][3]` |
| Dispatch | `de_to_t6_east[x] -> router feedthrough -> de_to_t6_east[x+1]` |
| NoC | `noc_east2west_req_repeaters_between_noc2axi` / router repeater paths |
| EDC | `edc_egress_intf[x*5+y] -> edc_ingress_intf[...]`, loopback path |
| DFX | `tt_noc_niu_router_dfx -> tt_t6_l1_partition_dfx -> tt_instrn_engine_wrapper_dfx` IJTAG chain |

### 10.2 `NOC2AXI_ROUTER_OPT` 전용 문서 생성

v9.4a가 module composition을 찾았으므로 다음은 exact wiring이다.

필수 table:

| Prefix | Physical row | Meaning |
|---|---|---|
| `noc2axi_i_*` / `noc2axi_o_*` | Y=4 | NOC2AXI bridge |
| `router_i_*` / `router_o_*` | Y=3 | embedded router |
| `i/o_noc2axi_*` | Y=4 | AXI master |
| `i/o_axi2noc_*` | Y=4 | AXI slave |
| `edc_egress_intf`, `loopback_edc_ingress_intf` | Y=3 | EDC router index |
| `i/o_de_to_t6_*`, `i_t6_to_de_*` | Y=3 | dispatch feedthrough |

### 10.3 DFX parser 추가

Neptune이 generic DFX domain을 찾은 것은 좋지만, 정답지는 Tensix-side wrapper chain을 요구한다.

필수 추출 대상:

- `tt_noc_niu_router_dfx`
- `tt_overlay_wrapper_dfx`
- `tt_instrn_engine_wrapper_dfx`
- `tt_t6_l1_partition_dfx`

필수 필드:

- file path
- parent placement
- clocks in/out
- pass-through assign
- IJTAG ifdef
- chain order

### 10.4 X/Y canonical map 병기

현재 map은 유용하지만 정답지 관례와 혼동 가능성이 있다. 다음을 같이 넣으면 좋다.

```text
GridConfig[y][x]:
      X=0                  X=1                     X=2                     X=3
Y=4   NOC2AXI_NE_OPT       NOC2AXI_ROUTER_NE_OPT   NOC2AXI_ROUTER_NW_OPT   NOC2AXI_NW_OPT
Y=3   DISPATCH_E           ROUTER (placeholder)    ROUTER (placeholder)    DISPATCH_W
Y=2   TENSIX               TENSIX                  TENSIX                  TENSIX
Y=1   TENSIX               TENSIX                  TENSIX                  TENSIX
Y=0   TENSIX               TENSIX                  TENSIX                  TENSIX
```

---

## 11. 버전 흐름 정리

| 버전 | 핵심 변화 | 점수 (통합본, Codex 기준) | 성격 |
|---|---|---:|---|
| v8 | max_results 50, port 전체 노출 | ~68% | visibility 극대화 |
| v9 | Hybrid tag + 6-file split | ~67% | 측정 인프라 도입, merge 회귀 |
| v9.1 | dedup + 실명 노출 + KB coverage | ~57% Codex / folder ~70% | 회귀 치유 |
| v9.2 | EP/dispatch/flit/clock 구조 회수 | ~68~70% | 구조 이해 도약 |
| v9.3 | Port Binding + CDC + EDC/Overlay 보강 | ~72~74% | graph evidence 도입 초기 |
| v9.4 | KB-only 회복 + EDC 개선, 통합본 압축 회귀 | ~64~67% | retrieval은 개선, final merge 후퇴 |
| **v9.4a** | **Neptune hierarchy + Semantic map + final merge 회복** | **~76~79%** | **module-level graph RAG 성공 초기** |
| v9.5 목표 | signal-path map + DFX/parser-opt/clock exact wiring | 84%+ 가능 | 정답지형 graph RAG |

---

*End of Review — Codex Review v9.4a (2026-05-19)*
