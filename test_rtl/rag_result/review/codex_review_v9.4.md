# Codex Review: RAG v9.4 정답지 비교 분석

**작성일:** 2026-05-15  
**리뷰어:** Codex  
**비교 대상:** `test_rtl/rag_result/v9.4/v9.4_N1B0_HDD.md` 중심, `test_rtl/rag_result/v9.4/` 전체 산출물 보조 비교  
**저장 위치:** `test_rtl/rag_result/review/codex_review_v9.4.md`  

---

## 0. 결론

v9.4는 v9.3에서 기대했던 "graph evidence 본문 승격"보다는, **KB-only 구조 요약을 다시 넓게 뽑고 EDC/DFX/NoC/Overlay topic을 분리 정리한 버전**에 가깝다. 가장 좋은 산출물은 통합 HDD가 아니라 `v9.4_chip_no_grounding.md`와 `v9.4_edc.md`다. KB-only 문서는 512 lines / 264 table rows로 v9.3 KB-only보다 훨씬 풍부하고, EDC topic도 node ID, BIU register map, instance path, security binding까지 확장됐다.

하지만 최종 통합본 `v9.4_N1B0_HDD.md`는 323 lines / 130 table rows로 v9.3 통합본의 493 lines / 216 table rows보다 크게 줄었다. 통합본이 비교 대상으로 `N1B0_NPU_HDD_v0.1.md`를 명시했지만, 실제 내용은 NPU 정답지의 핵심인 **DFX 4-wrapper chain, clock routing exception, PRTN/ISO_EN 실명, dispatch feedthrough, NOC2AXI_ROUTER dual-row wiring, EDC flat array exception**을 충분히 담지 못한다.

한 문장으로 요약하면:

> **v9.4는 원천 검색 산출물의 폭은 회복했지만, 최종 HDD merge가 너무 공격적으로 압축되어 정답지형 문서로는 v9.3보다 후퇴했다. 특히 통합본 기준 평가는 하락, 폴더 전체 best-of 기준은 v9.3과 비슷하거나 소폭 개선이다.**

점수는 기준을 분리해야 한다.

| 평가 기준 | 점수 | 해석 |
|---|---:|---|
| `v9.4_N1B0_HDD.md` 단독, `N1B0_NPU_HDD_v0.1.md` 기준 | **55~58%** | NPU 정답지를 대체하기에는 깊이 부족 |
| `v9.4_N1B0_HDD.md` 단독, 기본 `N1B0_HDD_v0.1.md` 기준 | **64~67%** | EP/NIU/EDC 요약은 있으나 wiring detail 누락 |
| v9.4 폴더 전체 best-of 기준 | **74~77%** | KB-only + EDC topic까지 함께 보면 사용 가능 |
| KB-only strict 기준 | **70~73%** | v9.3 KB-only보다 크게 개선 |

---

## 1. 참고한 파일

### 정답지

| 파일 | 역할 |
|---|---|
| `test_rtl/Sample/ORG/N1B0_HDD_v0.1.md` | 기본 N1B0 top-level 정답지 |
| `test_rtl/Sample/ORG/N1B0_NPU_HDD_v0.1.md` | v9.4 통합본이 명시한 비교 대상. NPU/Overlay/DFX 확장 정답지 |
| `test_rtl/Sample/ORG/N1B0_DFX_HDD_v0.1.md` | DFX wrapper chain 및 IJTAG 조건 비교 기준 |
| `test_rtl/Sample/ORG/N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` | composite NIU/router dual-row wiring 비교 기준 |

### v9.4 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v9.4/v9.4_N1B0_HDD.md` | 최종 통합 HDD. 이번 리뷰의 핵심 대상 |
| `test_rtl/rag_result/v9.4/v9.4_chip_no_grounding.md` | KB-only raw output. v9.4에서 가장 정보량이 큼 |
| `test_rtl/rag_result/v9.4/v9.4_chip_grounded.md` | KB + LLM grounded 문서. DFX/clock/EDC 보강 포함 |
| `test_rtl/rag_result/v9.4/v9.4_edc.md` | EDC topic result. v9.4의 가장 좋은 topic 문서 |
| `test_rtl/rag_result/v9.4/v9.4_noc.md` | NoC topic result. Endpoint map과 NoC register package 중심 |
| `test_rtl/rag_result/v9.4/v9.4_overlay.md` | Overlay topic result. v9.3 대비 짧아짐 |

---

## 2. 정량 비교

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[FROM LLM]` | `[NOT IN KB]` | `[TBC]` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 정답지 `N1B0_HDD_v0.1.md` | 514 | 22330 | 40 | 186 | 24 | 0 | 0 | 0 |
| 정답지 `N1B0_NPU_HDD_v0.1.md` | 1291 | 58380 | 105 | 303 | 52 | 0 | 0 | 0 |
| 정답지 `N1B0_DFX_HDD_v0.1.md` | 253 | 10353 | 12 | 52 | 12 | 0 | 0 | 0 |
| 정답지 `N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` | 279 | 13815 | 18 | 61 | 12 | 0 | 0 | 0 |
| v9.3 `v9.3_N1B0_HDD.md` | 493 | 18750 | 46 | 216 | 2 | 0 | 0 | 0 |
| **v9.4 `v9.4_N1B0_HDD.md`** | **323** | **8955** | **38** | **130** | **6** | **3** | **1** | **0** |
| v9.4 `chip_no_grounding` | 512 | 18103 | 51 | 264 | 6 | 0 | 0 | 0 |
| v9.4 `chip_grounded` | 483 | 17202 | 50 | 205 | 10 | 22 | 4 | 5 |
| v9.4 `edc` | 398 | 14084 | 41 | 121 | 10 | 2 | 0 | 3 |
| v9.4 `noc` | 200 | 5825 | 20 | 68 | 4 | 5 | 0 | 1 |
| v9.4 `overlay` | 138 | 4635 | 17 | 44 | 4 | 1 | 0 | 0 |

해석:

- 최종 통합본은 v9.3보다 **170 lines / 86 table rows 감소**했다.
- `chip_no_grounding`은 512 lines / 264 rows로 매우 좋아졌다. 즉 retrieval 자체가 완전히 나쁜 것은 아니다.
- `edc`는 398 lines로 v9.3 EDC topic보다 더 깊다.
- `overlay`는 138 lines로 v9.3의 220 lines보다 줄었다.
- 통합본이 `N1B0_NPU_HDD_v0.1.md`를 비교 대상으로 선언했지만, 정답지의 1291 lines / 303 table rows / 52 code fences 대비 정보량이 현저히 부족하다.

---

## 3. v9.3 -> v9.4 핵심 변화

| 축 | v9.3 | v9.4 | 판정 |
|---|---|---|---|
| 통합 HDD 크기 | 493 lines / 216 rows | 323 lines / 130 rows | 회귀 |
| KB-only 산출물 | 215 lines / 29 rows | 512 lines / 264 rows | 대폭 개선 |
| EDC topic | 251 lines / 88 rows | 398 lines / 121 rows | 개선 |
| NoC topic | 178 lines / 61 rows | 200 lines / 68 rows | 소폭 개선, 단 port binding 약화 |
| Overlay topic | 220 lines / 57 rows | 138 lines / 44 rows | 회귀 |
| DFX wrapper 노출 | 거의 없음 | `tt_overlay_wrapper_dfx`, `tt_t6_l1_partition_dfx` 일부 노출 | 부분 개선 |
| Port Binding | clock/reset/endpoint_id binding 표 있음 | 통합본에는 거의 없음 | 회귀 |
| CONNECTS_TO path evidence | 기능 언급 수준 | 없음 | 미개선 |
| NOC2AXI_ROUTER dual-row | 일부 module/binding | 통합본은 요약만 | 미개선 |
| SFR/PRTN 실명 | 약함 | 여전히 약함 | 미해결 |

v9.4의 문제는 "검색 결과가 없다"가 아니라 **좋은 검색 결과가 최종 통합 HDD로 충분히 승격되지 않았다**는 쪽이다.

---

## 4. 섹션별 정답지 비교

### 4.1 Overview

정답지 핵심:

- N1B0은 baseline Trinity에서 `trinity_noc2axi_n_opt + trinity_router` separate pair를 `trinity_noc2axi_router_ne/nw_opt` composite HPDF tile로 대체한 변형이다.
- composite tile은 Y=4 NOC2AXI와 Y=3 router logic을 한 RTL module 안에 담는다.
- per-column clock/reset, PRTN, ISO_EN, NoC repeater additions가 N1B0 핵심이다.

v9.4:

- 4x5 grid, 20 endpoints, 12 Tensix, 2 Dispatch, 4 NIU, 2 Router placeholders는 잘 유지한다.
- `trinity_router -- NOT INSTANTIATED` note도 들어 있다.
- `N1B0 vs Baseline Differences` table이 통합본 말미에 생겼다.

부족:

- Overview 본문에는 여전히 composite HPDF replacement의 의미가 약하다.
- `trinity_noc2axi_n_opt + trinity_router`가 `_router_*_opt`로 합쳐진 이유와 dual-row span이 첫 화면에서 설명되지 않는다.
- NoC repeater 4/6-stage, PRTN/ISO_EN은 baseline diff table에 일부만 있고 본문 핵심 설명으로 승격되지 않았다.

판정: **기본 HDD 기준 약 68%, NPU 정답지 기준 약 55%**

### 4.2 Package Constants and Grid

v9.4:

- EP index table 20개는 정확하다.
- `chip_grounded`에는 Tile Type Summary도 있다.
- `v9.4_noc.md`에는 endpoint map ASCII가 있다.

부족:

- 통합본에는 `GridConfig[y][x]` ASCII map이 없다.
- helper functions가 빠졌다:
  - `getTensixIndex`
  - `getNoc2AxiIndex`
  - `getApbIndex`
  - `getDmIndex`
  - `isEastEdge`, `isNorthEdge`
- `ROUTER` enum이 placeholder이며 실제 logic은 composite tile 내부라는 note가 package section에 없다.

판정: **통합본 약 72%, folder best-of 약 80%**

### 4.3 Top-Level Ports

v9.4:

- 통합본은 AXI/clock/reset/register group 수준으로만 표시한다.
- `chip_no_grounding`은 top-level instance binding 중심으로 일부 복구한다.

부족:

- 정답지의 top module parameter table이 없다:
  - `AXI_SLV_OUTSTANDING_READS=64`
  - `AXI_SLV_OUTSTANDING_WRITES=32`
  - `AXI_SLV_RD_RDATA_FIFO_DEPTH=512`
  - `NPU_DATA_W=512`
  - `NPU_IN_ADDR_W=56`
  - `NPU_OUT_ADDR_W=56`
- PRTN 12+ ports 실명 table이 통합본에 없다.
- `ISO_EN[11:0]`는 Known Gaps에만 나타나고, 포트 섹션에는 없다.
- APB, SFR memory config, reset vector dimensions가 정답지 수준으로 풀리지 않았다.

판정: **약 52~56%**

### 4.4 Module Hierarchy

v9.4 개선:

- `chip_no_grounding`과 `chip_grounded`에서 hierarchy가 v9.3보다 더 정리됐다.
- `trinity_noc2axi_router_ne_opt`와 `_nw_opt`가 각각 `tt_noc2axi` / `trinity_noc2axi_n_opt`를 가진다고 적었다.
- `tt_t6_l1_partition_dfx`, `tt_overlay_wrapper_dfx`가 일부 노출됐다.

부족:

- 통합본은 `gen_x[1] gen_y[4]: gen_noc2axi_router_ne_opt` 같은 generate hierarchy를 복구하지 못한다.
- 정답지의 핵심인 dual-row note가 약하다:
  - Y=4: `trinity_noc2axi_n_opt`
  - Y=3: embedded `trinity_router`
- `tt_noc_niu_router_dfx`와 `tt_instrn_engine_wrapper_dfx`가 통합 hierarchy에 없다.
- `tt_t6_l1_partition_dfx`도 통합본에는 빠지고 KB-only/grounded 문서에만 있다.

판정: **통합본 약 60%, folder best-of 약 68%**

### 4.5 Compute Tile / Tensix / Overlay

v9.4 개선:

- `chip_no_grounding`의 `tt_riscv_core` parameter table은 v9.3보다 좋다:
  - `THREAD_COUNT`
  - `MAILBOX_COUNT`
  - `TDMA_UNPACK_COUNT`
  - `DMEM_ECC_ENABLE`
  - `TRISC_CACHE_ENTRIES`
  - `LARGE_TRISC_ICACHE`
  - `MAX_L1_REQ`
  - `LOCAL_MEM_SIZE_BYTES`
- memory map도 꽤 구체적으로 들어왔다.
- `overlay` topic은 CPU cluster, iDMA, FDS, RoCC, L2 directory, harvest bypass, CDC를 짧게 정리한다.

부족:

- 정답지 `N1B0_NPU_HDD_v0.1.md`의 TRISC/BRISC, FPU G/M tile, DEST/SRCA/SRCB, L1 16-bank detail, instruction engine hierarchy는 여전히 통합본에서 약하다.
- CPU 8x RV64GC 같은 중요한 claim은 `[FROM LLM]`다.
- v9.4 통합본의 compute section은 v9.4 KB-only보다 훨씬 축약되어 있다.

판정:

- **통합본 단독:** 약 58%
- **folder best-of:** 약 66~69%

### 4.6 Dispatch Engine

v9.4:

- East/West dispatch EP3/EP18과 42 port classification은 유지한다.
- FDS bus expression을 유지한다.

부족:

- 정답지의 핵심 dispatch feedthrough가 거의 없다:
  - `de_to_t6_coloumn[SizeX][SizeY-1][2]`
  - `de_to_t6_east/west[SizeX]`
  - `t6_to_de[SizeX][SizeY-2]`
  - `t6_to_de_accross_east/west[SizeX][SizeX]`
- v9.3에서 문제였던 dimension 회귀를 해결한 증거가 v9.4에는 없다. 아예 관련 내용을 빼버린 형태다.
- `NOC2AXI_ROUTER_*_OPT`가 dispatch feedthrough를 carry한다는 port-level mapping이 없다.

판정: **약 45~50%**

### 4.7 NoC Fabric

v9.4 개선:

- `v9.4_noc.md`가 router flit ports, NoC register packages, endpoint map ASCII, security registers를 담는다.
- `chip_no_grounding`은 NoC package/register package/file reference를 잘 모은다.

부족:

- 통합본은 NoC section을 4x5 mesh, routing algorithm, SRAM 정도로 압축한다.
- routing algorithm과 flit header는 대부분 `[FROM LLM]`이다.
- 정답지의 manual X-axis connection과 4개 repeater instance가 없다:
  - `noc_east2west_req_repeaters_between_noc2axi`
  - `noc_west2east_req_repeaters_between_noc2axi`
  - `noc_east2west_req_repeaters_between_router`
  - `noc_west2east_req_repeaters_between_router`
- 4-stage at Y=4, 6-stage at Y=3 count가 없다.
- v9.3에 있던 port binding evidence가 v9.4에서는 약해졌다.

판정:

- **NoC inventory 기준:** 약 62%
- **N1B0 topology 기준:** 약 50%

### 4.8 NIU / NOC2AXI_ROUTER_OPT

v9.4 개선:

- all 4 NIU instances는 잘 잡는다.
- `chip_no_grounding`은 `trinity_noc2axi_router_ne_opt`와 `_nw_opt` 아래에 `tt_noc2axi` / `trinity_noc2axi_n_opt`를 표시한다.
- DFT submodules와 FBLC parameter 일부가 나온다.

부족:

- 정답지 `N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md`의 core가 거의 없다:
  - `noc2axi_i_*` / `noc2axi_o_*` = Y=4
  - `router_i_*` / `router_o_*` = Y=3
  - internal flit cross-wires
  - `noc2axi_clock_routing_out -> router_clock_routing_in`
  - EDC forward/loopback internal chain
  - `REP_DEPTH_LOOPBACK=6`, `REP_DEPTH_OUTPUT=4`
  - west/south repeater counts
- 통합본은 "Composite NIU+Router"라고 부르지만, 왜 composite인지 설명하지 못한다.
- AXI parameter forwarding과 APB CSR inheritance도 없다.

판정: **통합본 약 40%, folder best-of 약 48%**

### 4.9 Clock / Reset

v9.4 개선:

- clock domains는 6개로 잘 정리한다.
- `chip_grounded`와 `overlay`는 `tt_overlay_wrapper_dfx` clock splitter evidence를 보여준다.
- CDC module inventory는 유지한다.

부족:

- 정답지의 `trinity_clock_routing_t` struct가 없다.
- `clock_routing_in[SizeX][SizeY]` / `clock_routing_out[SizeX][SizeY]` arrays가 없다.
- entry point가 없다:
  - `clock_routing_in[x][4].ai_clk = i_ai_clk[x]`
  - `clock_routing_in[x][4].dm_clk = i_dm_clk[x]`
  - `clock_routing_in[x][4].power_good = i_edc_reset_n`
- `NOC2AXI_ROUTER_*_OPT` exception이 없다:
  - Y=4 output 없음
  - `router_o_*`가 `clock_routing_out[x][3]`을 drive
- reset packing semantics도 빠졌다.

판정: **통합본 약 50%, folder best-of 약 60%**

### 4.10 EDC

v9.4 개선:

- v9.4에서 가장 좋은 영역이다.
- `v9.4_edc.md`가 다음을 잘 담았다:
  - serial bus interface: `req_tgl`, `ack_tgl`, `data`, `data_p`, `async_init`
  - BIU register map: `HEADER1`, `PAYLOAD`, `CTRL`, `IRQ_EN`
  - node ID encoding
  - EDC nodes in Tensix, L1, FPU, NIU
  - EDC security controller bindings
  - RTL file index
- `chip_no_grounding`도 EDC package parameters와 node ID assignment를 잘 담았다.

부족:

- 통합본 EDC section은 topic 문서의 깊이를 거의 흡수하지 못했다.
- 정답지의 flat arrays가 없다:
  - `edc_ingress_intf[SizeX*SizeY]`
  - `edc_egress_intf[SizeX*SizeY]`
  - `loopback_edc_ingress_intf`
  - `loopback_edc_egress_intf`
- `NOC2AXI_ROUTER_*_OPT` EDC exception이 없다:
  - Y=4 position에는 EDC interface 없음
  - Y=3 index만 외부 ring에 연결
- U-shape ring은 유용하지만 일부가 `[FROM LLM]`이고 exact indexing은 부족하다.

판정:

- **통합본 단독:** 약 68%
- **EDC topic 포함:** 약 84~87%

### 4.11 Power / PRTN / ISO_EN

v9.4:

- 통합본 Known Gaps에 `Power management ISO_EN details`가 있다.
- reset section에 PRTN 4-column daisy-chain이 `[FROM LLM]`로 한 줄 있다.

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
- dispatch tiles are not in PRTN chain이라는 정답지 핵심이 없다.

판정: **약 30~35%**

### 4.12 SRAM / SFR

v9.4 개선:

- SRAM macro table은 v9.3과 유사하게 유지된다.
- `chip_no_grounding`은 memory map과 일부 macro source를 더 많이 보여준다.

부족:

- NPU 정답지의 per-tile SRAM inventory, L1 bank count, context switch SRAM, L2 directory SRAM detail은 없다.
- SFR memory config 13개 category는 숫자만 있고 실명 signal table은 없다.
- selftest macro dimension 표기가 일부 "512x138 -> 512x516"처럼 혼합되어 있어 실제 macro dimension과 logical width를 구분해야 한다.

판정: **약 50~55%**

### 4.13 DFX

v9.4 개선:

- v9.4는 DFX keyword visibility가 v9.3보다 나아졌다.
- `chip_no_grounding`은 NIU DFT submodules를 잘 모은다:
  - `EDT_WRAP`
  - `STI_WRAP`
  - `SRI_WRAP`
  - `SDUMP_INTF`
  - `FB_INTF`
  - `FBLC`
  - `DFT_CLOCK_SPLITTER_SINGLE/DUAL`
  - `BDA_RST_CTRL`
- `chip_grounded`와 `overlay`는 `tt_overlay_wrapper_dfx` clock splitters를 보여준다.
- `tt_t6_l1_partition_dfx`도 일부 노출됐다.

부족:

- 정답지의 4-wrapper chain은 여전히 완성되지 않았다:
  - `tt_noc_niu_router_dfx`
  - `tt_overlay_wrapper_dfx`
  - `tt_instrn_engine_wrapper_dfx`
  - `tt_t6_l1_partition_dfx`
- 통합본 DFX section은 iJTAG/MBIST/Scan module 이름만 있고 wrapper placement가 없다.
- clock pass-through counts가 없다:
  - NIU/router 5 clocks
  - overlay 5 clocks
  - instruction engine 1 clock
  - L1 partition 2->3 clocks
- IJTAG absent/ifdef condition도 없다.
- `chip_grounded`의 KB Coverage Matrix가 DFX를 "High"로 보는 것은 과대평가다. DFT infrastructure는 높지만 N1B0 DFX hierarchy fidelity는 중간 이하다.

판정:

- **통합본 단독:** 약 35%
- **folder best-of:** 약 50~55%

---

## 5. v9.4의 좋은 점

### 5.1 KB-only 산출물 회복

v9.3의 `chip_no_grounding`은 215 lines / 29 rows로 너무 빈약했다. v9.4는 512 lines / 264 rows로 늘었고, RISC-V parameters, memory map, EDC nodes, NoC packages, NIU DFT submodules, RTL file reference가 들어왔다. strict KB 관점에서는 v9.4가 분명히 좋아졌다.

### 5.2 EDC topic 품질 상승

`v9.4_edc.md`는 독립 문서로는 매우 쓸 만하다. 특히 BIU register map, register bridge, security controller binding, instance paths가 v9.3보다 훨씬 낫다. EDC만 따로 보면 정답지형 문서에 가장 근접했다.

### 5.3 DFT/DFX visibility 일부 개선

v9.3에서는 거의 안 보이던 DFT wrapper/utility 이름이 v9.4에는 꽤 나온다. 다만 이것이 정답지의 "DFX wrapper chain"으로 구조화되지는 않았다.

---

## 6. 주요 회귀 / 위험 포인트

| 항목 | v9.3 | v9.4 | 영향 |
|---|---|---|---|
| 통합 HDD 밀도 | 493 lines / 216 rows | 323 lines / 130 rows | 최종 산출물 기준 명백한 회귀 |
| Port Binding evidence | clock/reset/endpoint_id binding 표 있음 | 통합본에는 없음 | graph evidence 약화 |
| CONNECTS_TO / graph path | 신규 기능 언급 | 없음 | v9.4 목표 미달 |
| Overlay topic | 220 lines | 138 lines | NPU 정답지 대비 약화 |
| DFX coverage label | 약하지만 보수적 | High/Full처럼 보이는 matrix | 과대평가 위험 |
| `[FROM LLM]` | 통합본 0 | 통합본 3, grounded 22 | 사실/추론 경계 관리 필요 |

특히 v9.4 통합본은 "Merged from 5 search_rtl queries"라고 되어 있지만, 실제로는 `chip_no_grounding`과 `edc`에 있는 좋은 정보가 상당히 버려졌다. merge rule이 핵심 병목이다.

---

## 7. 남은 핵심 Gap

| # | Gap | 정답지 위치 | v9.4 상태 | 해결 경로 | 예상 효과 |
|---|---|---|---|---|---:|
| 1 | 통합본 merge 손실 | 전체 | KB-only/EDC의 좋은 정보가 통합본에 미반영 | section별 required evidence checklist | +8~12pp |
| 2 | DFX 4-wrapper chain | NPU §14, DFX HDD | 일부 wrapper만 산발 노출 | `used_in_n1/rtl/dfx/*` 전용 parser + DFX section template | +5~7pp |
| 3 | NOC2AXI_ROUTER dual-row wiring | Router OPT HDD | composite name만 있고 wiring 없음 | port-prefix parser + internal wire extraction | +5~7pp |
| 4 | Clock routing exception | HDD §6, NPU §9 | clock domains만 있음 | `trinity_clock_routing_t` struct/assign parser | +3~5pp |
| 5 | Dispatch feedthrough dimensions | HDD §8 | 거의 누락 | multi-dim array resolver + feedthrough template | +3~4pp |
| 6 | NoC 4 repeater instances/counts | HDD §5/7 | generic repeaters만 있음 | instance-name exact retrieval + count extraction | +3~4pp |
| 7 | PRTN/ISO_EN 실명 | HDD §3/9, NPU §12 | Known gap 수준 | top port table compression 금지 | +3~5pp |
| 8 | EDC flat array/router exception | HDD §7, NPU §11 | EDC topic은 좋으나 통합본 미반영 | EDC topic -> HDD merge rule | +3~4pp |
| 9 | NPU deep compute hierarchy | NPU §4/5/15 | RISC-V params 중심 | Tensix core HDD targeted retrieval | +4~6pp |
| 10 | Provenance preservation | grounded -> integrated | 통합본에서 경계 일부 사라짐 | `[KB]`, `[FROM LLM]`, `[TBC]` tag 유지 | 품질 관리 |

---

## 8. 종합 점수

| 기준 | v9.3 Codex | v9.4 Codex | 변화 |
|---|---:|---:|---|
| 통합 HDD 단독, 기본 N1B0 HDD 기준 | 72~74% | **64~67%** | 하락 |
| 통합 HDD 단독, NPU HDD 기준 | 미평가 | **55~58%** | 목표 대비 부족 |
| 산출물 전체 best-of | 79~81% | **74~77%** | 소폭 하락 |
| KB-only strict | 58~62% | **70~73%** | 개선 |
| EDC topic 단독 | 약 82% | **84~87%** | 개선 |

왜 이런 역전이 생겼나:

- retrieval raw output은 좋아졌다.
- topic 문서, 특히 EDC는 좋아졌다.
- 그러나 최종 통합 HDD가 지나치게 짧아졌고, 정답지 핵심 evidence를 본문으로 가져오지 않았다.
- 그래서 "pipeline retrieval 성능"은 개선된 면이 있지만 "최종 HDD 산출물 품질"은 하락했다.

---

## 9. v9.5 권장 방향

### 9.1 통합본을 `chip_no_grounding`보다 작게 만들지 말 것

v9.4의 가장 큰 문제는 최종 HDD가 KB-only 문서보다 훨씬 빈약하다는 점이다. 통합본은 최소한 다음 조건을 만족해야 한다.

| 조건 | 권장 기준 |
|---|---|
| 통합본 lines | `chip_no_grounding`의 80% 이상 |
| table rows | `chip_no_grounding`의 70% 이상 |
| code fences | 정답지형 snippet 10개 이상 |
| topic merge | EDC/NoC/Overlay 핵심 table은 통합본에 직접 반영 |

### 9.2 정답지형 required evidence checklist

N1B0 HDD 생성 시 다음 항목이 없으면 merge fail로 보는 것이 좋다.

| Section | Required evidence |
|---|---|
| Overview | baseline -> N1B0 replacement table |
| Grid | `GridConfig[y][x]` ASCII + EP table |
| Ports | PRTNUN + ISO_EN + top parameter table |
| Hierarchy | `gen_x/gen_y` generate tree |
| NOC2AXI_ROUTER | port-prefix table + internal flit/clock/EDC chain |
| NoC | four repeater instances + 4/6-stage counts |
| Clock | `trinity_clock_routing_t`, entry point, router exception |
| Dispatch | `de_to_t6_coloumn[SizeX][SizeY-1][2]` and feedthrough snippet |
| EDC | flat arrays + router exception + node ID |
| DFX | 4-wrapper chain + clock pass-through counts + IJTAG condition |

### 9.3 Graph/CONNECTS_TO를 실제 문서 evidence로 넣기

v9.3에서 예고한 graph 기능이 v9.4 통합본에는 보이지 않는다. v9.5에서는 다음 같은 path table이 직접 들어가야 한다.

| Target | Example evidence |
|---|---|
| NoC repeater | `flit_out_req[1][4] -> noc_east2west_req_repeaters_between_noc2axi -> flit_in_req[2][4]` |
| Clock | `i_ai_clk[x] -> clock_routing_in[x][4] -> router_o_ai_clk -> clock_routing_out[x][3]` |
| EDC | `noc2axi_edc_egress_intf -> router_edc_ingress_intf -> edc_egress_intf[x*5+3]` |
| Dispatch | `de_to_t6_east[x] -> router feedthrough -> de_to_t6_east[x+1]` |

### 9.4 DFX 전용 parser

DFX는 keyword retrieval로는 부족하다. 다음 4개 파일/모듈을 한 세트로 보는 parser가 필요하다.

- `tt_noc_niu_router_dfx`
- `tt_overlay_wrapper_dfx`
- `tt_instrn_engine_wrapper_dfx`
- `tt_t6_l1_partition_dfx`

추출해야 할 필드는 module name, file path, clocks in/out, pass-through assign, IJTAG ifdef, placement parent, chain order다.

---

## 10. 버전 흐름 정리

| 버전 | 핵심 변화 | 점수 (통합본, Codex 기준) | 성격 |
|---|---|---:|---|
| v8 | max_results 50, port 전체 노출 | ~68% | visibility 극대화 |
| v9 | Hybrid tag + 6-file split | ~67% | 측정 인프라 도입, merge 회귀 |
| v9.1 | dedup + 실명 노출 + KB coverage | ~57% Codex / folder ~70% | 회귀 치유 |
| v9.2 | EP/dispatch/flit/clock 구조 회수 | ~68~70% | 구조 이해 도약 |
| v9.3 | Port Binding + CDC + EDC/Overlay 보강 | ~72~74% | graph evidence 도입 초기 |
| **v9.4** | **KB-only 회복 + EDC 개선, 통합본 압축 회귀** | **~64~67%** | **retrieval은 개선, final merge는 후퇴** |
| v9.5 목표 | Required evidence checklist + graph path 본문 삽입 | 80%+ 가능 | 정답지형 merge |

---

*End of Review — Codex Review v9.4 (2026-05-15)*
