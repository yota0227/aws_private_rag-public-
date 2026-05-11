# Codex Review: RAG v9.2 정답지 비교 분석

**작성일:** 2026-05-08  
**리뷰어:** Codex  
**비교 대상:** `test_rtl/rag_result/v9.2/v9.2_N1B0_HDD.md` 중심, `test_rtl/rag_result/v9.2/` 전체 산출물 보조 비교  
**저장 위치:** `test_rtl/rag_result/review/codex_review_v9.2.md`  

---

## 0. 결론

v9.2는 v9.1에서 목표로 잡았던 topology-required facts를 실제로 일부 회복한 버전이다. 특히 최종 통합 HDD에 Endpoint Index 20-row table, package helper functions, dispatch feedthrough wire topology, `clock_routing_in/out` 4x5 mesh, flit 4D array가 들어오면서 v9.1의 가장 큰 약점이던 "좌표계/배선 구조가 빠진 요약본" 문제를 꽤 줄였다.

정량적으로도 통합 HDD가 v9.1의 331 lines / 117 table rows에서 v9.2의 407 lines / 172 table rows로 커졌다. 정답지 `N1B0_HDD_v0.1.md`의 513 lines / 186 table rows에 가까워졌고, 단순 문서 밀도만 보면 v8 이후 가장 정답지 형태에 가까운 통합본이다.

하지만 아직 정답지 대체물로 보기는 이르다. v9.2가 회복한 항목은 대부분 "이름과 배열 차원" 수준이고, 정답지가 강한 부분인 `GridConfig` 4x5 ASCII map, `NOC2AXI_ROUTER_*_OPT` dual-row generate hierarchy, router/noc2axi port prefix mapping, NoC repeater instance/count, EDC flat arrays와 router exception, PRTN tap detail은 통합본에서 없거나 얕다.

점수는 두 기준으로 분리하는 것이 맞다.

- **통합 HDD 단독 기준:** `v9.2_N1B0_HDD.md`만 정답지 대체물로 보면 약 **68~70%**
- **v9.2 산출물 전체 best-of 기준:** `chip_no_grounding`, `chip_grounded`, `edc`, `noc`, `overlay`까지 함께 읽으면 약 **76~78%**

한 문장으로 요약하면:

> **v9.2는 v9.1의 summary-merge 회복을 넘어 좌표계/배선 fact를 실제로 끌어올린 의미 있는 개선판이지만, 아직 정답지의 generate/wiring 예외 설명까지는 도달하지 못했다.**

---

## 1. 참고한 파일

### 정답지

| 파일 | 역할 |
|---|---|
| `test_rtl/Sample/N1B0_HDD_v0.1.md` | 주 비교 기준. N1B0 4x5 variant HDD |
| `test_rtl/Sample/N1B0_NPU_HDD_v0.1.md` | 보조 비교 기준. NPU 관점 확장 HDD |

### v9.2 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v9.2/v9.2_N1B0_HDD.md` | v9.2 통합 HDD. 이번 리뷰의 핵심 대상 |
| `test_rtl/rag_result/v9.2/v9.2_chip_no_grounding.md` | raw RAG full-chip HDD. EP/wire/clock array 상세 일부 보유 |
| `test_rtl/rag_result/v9.2/v9.2_chip_grounded.md` | hybrid grounding output. `[FROM LLM]`, `[NOT IN KB]`, coverage matrix 포함 |
| `test_rtl/rag_result/v9.2/v9.2_edc.md` | EDC topic result. EDC APB/IRQ table 포함 |
| `test_rtl/rag_result/v9.2/v9.2_noc.md` | NoC topic result. flit 4D array와 endpoint map 포함 |
| `test_rtl/rag_result/v9.2/v9.2_overlay.md` | Overlay/RISC-V topic result. L1 EDC daisy-chain 정보 포함 |

### 비교 기준 리뷰

| 파일 | 참고 포인트 |
|---|---|
| `test_rtl/rag_result/review/codex_review_v9.1.md` | v9.1의 미해결 P0 gap 및 v9.2 목표 |
| `test_rtl/rag_result/review/codex_review_v9.md` | 통합 HDD 단독 vs folder-level 점수 분리 기준 |
| `test_rtl/rag_result/v8/v8_N1B0_HDD.md` | v8에서 확보했던 상세 섹션과 회귀/복구 비교 |

---

## 2. 정량 비교

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[FROM LLM]` | `[NOT IN KB]` |
|---|---:|---:|---:|---:|---:|---:|---:|
| 정답지 `N1B0_HDD_v0.1.md` | 513 | 22330 | 40 | 186 | 24 | 0 | 0 |
| 정답지 `N1B0_NPU_HDD_v0.1.md` | 1290 | 58380 | 105 | 303 | 52 | 0 | 0 |
| v8 `v8_N1B0_HDD.md` | 480 | 17951 | 43 | 212 | 6 | 0 | 0 |
| v9.1 `v9.1_N1B0_HDD.md` | 331 | 11274 | 27 | 117 | 4 | 0 | 0 |
| v9.2 `v9.2_N1B0_HDD.md` | 407 | 13887 | 41 | 172 | 2 | 0 | 0 |
| v9.2 `chip_no_grounding` | 376 | 14338 | 35 | 163 | 2 | 0 | 0 |
| v9.2 `chip_grounded` | 284 | 9887 | 27 | 86 | 2 | 9 | 3 |
| v9.2 `edc` | 149 | 4849 | 16 | 42 | 2 | 0 | 0 |
| v9.2 `noc` | 151 | 5120 | 14 | 36 | 2 | 0 | 0 |
| v9.2 `overlay` | 152 | 4908 | 17 | 40 | 0 | 0 | 0 |

해석:

- v9.2 통합 HDD는 v9.1 대비 331 -> 407 lines, 117 -> 172 table rows로 증가했다.
- table row 수는 정답지 186 rows의 약 92%까지 올라왔다.
- headings는 정답지와 거의 같은 수준이지만, code fence는 정답지 24개 대비 2개뿐이다. 즉 표/요약은 늘었지만 RTL-style pseudo-code, wiring snippet, topology diagram은 여전히 약하다.
- `chip_grounded`의 `[FROM LLM]` 9개, `[NOT IN KB]` 3개는 v9.1보다 더 압축된 grounding 문서라는 뜻이다. coverage matrix는 유용하지만 정답지 fidelity와 동일하게 보면 안 된다.

### 2.1 점수 기준

| 평가 관점 | 포함 파일 | 장점 인정 방식 | 결과 |
|---|---|---|---:|
| 통합 HDD 단독 | `v9.2_N1B0_HDD.md` | 최종 문서에 직접 남은 내용만 인정 | ~68~70% |
| v9.2 산출물 전체 best-of | `v9.2/` 6개 문서 전체 | topic 문서와 grounded/no-grounding 상세 정보를 함께 인정 | ~76~78% |

---

## 3. 섹션별 정답지 비교

### 3.1 Overview

정답지 핵심:

- N1B0은 baseline Trinity에서 `trinity_noc2axi_n_opt + trinity_router` tile pair를 `trinity_noc2axi_router_ne/nw_opt` HPDF tile로 교체한 변형이다.
- 통합 HPDF tile은 Y=4 NOC2AXI와 Y=3 router logic을 함께 담는 dual-row 구조다.
- per-column AI/DM clock/reset, PRTN, ISO_EN, NoC repeater buffers가 N1B0 addition이다.

v9.2:

- 4x5 mesh, 20 nodes, 12 Tensix, 4 NIU, 2 Dispatch, 14 DM complexes, EDC, dynamic routing은 안정적으로 포함한다.
- `trinity_router`가 N1B0에서 EMPTY by design이라는 note도 유지한다.

부족:

- HPDF replacement story가 Overview에 아직 없다.
- baseline pair를 combined dual-row tile로 대체했다는 N1B0 identity가 첫 문단에서 약하다.
- baseline vs N1B0 difference table은 없다.

판정: **v9.1과 유사. 약 65%**

### 3.2 Package Constants, Grid, Endpoint

v9.2 개선:

| 항목 | v9.1 | v9.2 | 판정 |
|---|---|---|---|
| 13 localparams | 있음 | 있음 | 유지 |
| `tile_t` enum | 있음 | 있음 | 유지 |
| EndpointIndex formula | 없음 | 있음 | 개선 |
| 20-row EP table | 없음 | 있음 | 대폭 개선 |
| helper functions | 없음 | 있음 | 대폭 개선 |
| `isNorthEdge` | 있음 | 있음 | 유지 |
| `trinity_clock_routing_t` | 없음/약함 | 있음 | 개선 |

좋은 점:

- v9.2의 가장 큰 개선은 EndpointIndex 20-row table이다. 정답지의 좌표계 anchor가 최종 통합 HDD에 들어왔다.
- `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex`가 명시됐다.
- `trinity_clock_routing_t`가 package section에 들어와 clock/reset section과 연결된다.

부족:

- 정답지의 `GridConfig[y][x]` 4x5 ASCII tile map은 통합본에 없다.
- helper functions의 scan order와 count semantics가 얕다.
- `ROUTER` placeholder가 EP 8/13을 reserve한다는 설명이 없다.
- `NOC2AXI_ROUTER_NE/NW_OPT`가 Y=4와 Y=3을 동시에 점유한다는 package-level note가 부족하다.

판정: **v9.1 대비 대폭 개선. 약 78%**

### 3.3 Top-Level Ports

v9.2:

- 106 total ports를 유지한다.
- AXI 39, EDC APB 16, APB register 8, SFR 17, PRTN 14 등 category count가 안정적이다.
- `chip_no_grounding`에는 key signal list가 v9.1과 비슷하게 남아 있다.

부족:

- 정답지의 top module parameter table이 없다:
  - `AXI_SLV_OUTSTANDING_READS=64`
  - `AXI_SLV_OUTSTANDING_WRITES=32`
  - `AXI_SLV_RD_RDATA_FIFO_DEPTH=512`
  - `NPU_DATA_W=512`
  - `NPU_IN_ADDR_W=56`
  - `NPU_OUT_ADDR_W=56`
- AXI는 여전히 full channel table이 아니라 `npu_out_*`, `npu_in_*` 요약이다.
- APB register ports는 `[NumApbNodes]` dimension이 통합본에서 명확하지 않다.
- EDC APB `[4]` array dimension은 `edc.md`에 더 잘 남고 통합본은 16-count summary에 가깝다.
- PRTN은 category count만 있고 정답지의 signal별 width/direction table이 없다.

판정:

- **통합 HDD 단독:** 약 74%
- **v9.2 folder best-of:** 약 80%

### 3.4 Module Hierarchy

v9.2:

- top hierarchy tree는 v9.1과 비슷한 수준이다.
- NIU, NoC, Clock Infrastructure, Overlay를 함께 묶어 보여준다.
- `trinity_router` baseline-only note는 유지한다.

부족:

- 정답지의 Level-1 generate hierarchy가 없다:
  - `gen_x[0] gen_y[4]: gen_noc2axi_ne_opt`
  - `gen_x[1] gen_y[4]: gen_noc2axi_router_ne_opt`
  - `gen_x[2] gen_y[4]: gen_noc2axi_router_nw_opt`
  - `gen_dispatch_e/w`, `gen_tensix`
- `NOC2AXI_ROUTER_*_OPT` dual-row span이 NIU section에서 암시만 되고 hierarchy section에는 없다.
- `router_o_*`, `noc2axi_i_*`, `router_i_*`, `i_de_to_t6_*` port prefix mapping이 없다.
- repeater instances가 hierarchy tree에 없다.

판정: **v9.1 대비 소폭 개선 이하. 약 58%**

### 3.5 Compute Tile - Tensix

v9.2:

- FPU/SFPU/TDMA/L1 module table을 유지한다.
- `overlay.md`가 L1 cache와 iDMA, FDS, cluster control을 보조한다.
- `chip_grounded`는 DEST/SRCB, BRISC/TRISC를 `[FROM LLM]`으로 명확히 분리한다.

부족:

- 정답지/확장 정답지의 TRISC/BRISC, G-Tile/M-Tile, DEST/SRCA/SRCB, L1 partition detail은 아직 약하다.
- `v9.2_N1B0_HDD.md`에는 Instruction Engine section이 v9.1보다 오히려 덜 보인다.
- compute tile deep hierarchy는 정답지 `N1B0_NPU_HDD_v0.1.md` 대비 매우 요약적이다.

판정: **v9.1과 유사. 약 55%**

### 3.6 Dispatch Engine

v9.2 개선:

- `de_to_t6_coloumn`, `de_to_t6_east`, `de_to_t6_west`, `t6_to_de`, `t6_to_de_accross_east`, `t6_to_de_accross_west`가 최종 통합 HDD에 들어왔다.
- wire type과 dimensions가 정답지에 가까워졌다.
- dispatch EP 3/18도 통합본에 명시됐다.

부족:

- `de_to_t6_coloumn[SizeX][SizeY-1][2]`의 마지막 `[2]` dimension이 통합본에서는 빠져 있다.
- `NOC2AXI_ROUTER_*_OPT` tiles가 feedthrough를 carry한다는 port-level mapping이 없다.
- 정답지의 `.i_de_to_t6_east_feedthrough`, `.o_de_to_t6_east_feedthrough`, `.i_t6_to_de_south` 같은 connection snippet은 없다.

판정: **v9.1 대비 대폭 개선. 약 62%**

### 3.7 NoC Fabric

v9.2 개선:

- flit 4D array가 명시됐다:
  - `flit_in_req`
  - `flit_in_resp`
  - `flit_out_req`
  - `flit_out_resp`
- `v9.2_noc.md`에 endpoint map이 ASCII 형태로 들어왔다.
- routing algorithms, SECDED, CDC, arbiter module list는 유지된다.

부족:

- 정답지의 핵심인 manual X-axis connection은 없다.
- Y=4 NOC2AXI row의 4-stage repeaters와 Y=3 router row의 6-stage repeaters가 통합본에는 없다.
- `v9.2_noc.md`도 "Located at Y=3, Y=4" 수준이고, instance names와 direction table은 없다.
- `noc_east2west_req_repeaters_between_noc2axi`, `noc_west2east_req_repeaters_between_router` 등 정답지 핵심 instance names가 없다.
- row별 direct/repeated connection과 edge tie-off 설명이 없다.

판정:

- **NoC signal inventory 기준:** 개선
- **N1B0 topology 기준:** 아직 중간 이하
- 종합 **약 52%**

### 3.8 NIU / AXI Bridge Tiles

v9.2:

- 4 NIU instances와 EP 4/9/14/19를 명시한다.
- `tt_niu_mst_timeout`, `tt_noc2axi_local_reg`, `tt_noc2axi_cfg`를 유지한다.
- corner NIU vs router NIU type 이름은 나온다.

부족:

- `NOC2AXI_ROUTER_NE/NW_OPT`가 Y=4 NOC2AXI와 Y=3 router를 결합한다는 구조가 NIU section에서 충분히 풀리지 않는다.
- AXI in/out mapping과 `i/o_noc2axi_*`, `i/o_axi2noc_*` port group 설명이 없다.
- ATT는 grounded에서 `[FROM LLM]`로 남고 entry count/bit width는 `[NOT IN KB]`이다.

판정: **v9.1 대비 소폭 개선. 약 60%**

### 3.9 EDC

v9.2:

- `v9.2_edc.md`에 EDC APB 16-port table과 IRQ table이 유지된다.
- 통합 HDD에는 U-shape, direct/loopback connector, harvest bypass, module hierarchy가 요약되어 있다.
- overlay topic에는 L1 EDC daisy-chain generate blocks가 추가됐다.

부족:

- 정답지의 flat arrays가 없다:
  - `edc_ingress_intf[SizeX*SizeY]`
  - `edc_egress_intf[SizeX*SizeY]`
  - `loopback_edc_ingress_intf[SizeX*SizeY]`
  - `loopback_edc_egress_intf[SizeX*SizeY]`
- endpoint index와 EDC array index가 같다는 설명이 없다.
- `NOC2AXI_ROUTER_*_OPT`에서 Y=4 EDC interface가 없고 Y=3 index만 연결된다는 예외가 없다.
- `edc.md`의 serial bus interface는 port list가 너무 짧아 toggle protocol 세부 재현은 약하다.

판정:

- **통합 HDD 단독:** 약 64%
- **v9.2 folder best-of:** 약 72%

### 3.10 Clock and Reset

v9.2 개선:

- `clock_routing_in/out` 4x5 mesh가 최종 통합 HDD에 들어왔다.
- `trinity_clock_routing_t` 필드가 package/clock section 양쪽에 반영됐다.
- reset width table도 유지된다.

부족:

- 정답지의 struct는 `dm_core_clk_reset_n` 등 nested reset fields를 포함하는데, v9.2는 8-field summary라 세부가 얕다.
- Y=4 clock entry point와 `power_good = i_edc_reset_n` 설명이 없다.
- reset packing with `getTensixIndex`가 없다.
- `NOC2AXI_ROUTER_*_OPT`의 Y=4 output unused, Y=3 `router_o_*` drive exception이 없다.
- `noc_clk` bypass observation이 없다.

판정: **v9.1 대비 대폭 개선. 약 68%**

### 3.11 Power Management / PRTN / ISO

v9.2:

- 4-column daisy-chain, `ISO_EN[11:0]`, PRTNUN protocol, `TIEL_DFT_MODESCAN`은 유지된다.

부족:

- 정답지처럼 port별 width/direction table은 없다.
- per-column chain `external -> [x][2] -> [x][1] -> [x][0] -> output`이 통합본에는 없다.
- `w_left_prtnun_*[x][2]` tap detail이 없다.
- grounded의 "per-tile power gating with retention"은 `[FROM LLM]`이다.

판정: **v9.1과 유사. 약 60%**

### 3.12 Memory Config / SRAM

v9.2:

- SFR family 4종은 유지된다:
  - `RF_2P_HSC`
  - `RA1_HS`
  - `RF1_HS`
  - `RF1_HD`
- primary macro `RF_2P_HSC_LVT_32X136M1FB1WM0DR0`도 유지된다.

부족:

- 정답지의 Memory Config table처럼 family별 적용 tile이 충분하지 않다.
- `SFR_RF_2P_HSC_QNAPA/B`, `EMAA/B`, `RAWL`, `RAWLM`, `SFR_RF1_HS_MCS`, `SFR_RA1_HS_MCS` 등 signal-level table이 없다.
- total SRAM instance count는 grounded에서 `[NOT IN KB]`이다.
- NPU 확장 정답지의 SRAM inventory와는 차이가 크다.

판정: **v9.1과 유사. 약 58%**

### 3.13 DFX

v9.2:

- `tt_tensix_jtag`, `tt_sync3`, `tt_fpu_gtile_SDUMP_INTF`, `TIEL_DFT_MODESCAN`을 유지한다.

부족:

- v8/정답지 확장 수준의 4-node DFX wrapper chain은 없다:
  - `tt_noc_niu_router_dfx`
  - `tt_overlay_wrapper_dfx`
  - `tt_instrn_engine_wrapper_dfx`
  - `tt_t6_l1_partition_dfx`
- IJTAG absent/pass-through status도 없다.
- DFX는 v9.2의 주요 개선 영역이 아니다.

판정: **v9.1과 유사. 약 43%**

### 3.14 RTL File Reference

v9.2:

- baseline top, 4x5 package, N1B0 top, `trinity_router.sv`, NIU/EDC/overlay/idma paths를 포함한다.

부족:

- 통합 HDD의 file map에는 정답지의 N1B0-specific RTL files가 여전히 빠져 있다:
  - `trinity_noc2axi_router_ne_opt.sv`
  - `trinity_noc2axi_router_nw_opt.sv`
  - `trinity_noc2axi_ne_opt.sv`
  - `trinity_noc2axi_nw_opt.sv`
  - `tt_tensix_with_l1`
  - `tt_dispatch_top_east/west`
  - `tt_noc_repeaters`
  - `tt_edc1_intf_connector`
- `chip_no_grounding` file reference도 v9.1과 비슷하게 제한적이다.

판정: **약 45%**

---

## 4. v9.1 -> v9.2 변화 분석

| 항목 | v9.1 | v9.2 | 변화 |
|---|---|---|---|
| 통합 HDD 크기 | 331 lines / 11.3KB | 407 lines / 13.9KB | 증가 |
| 통합 HDD table rows | 117 | 172 | 대폭 증가 |
| Headings | 27 | 41 | 정답지 수준 회복 |
| `tile_t` enum | 있음 | 있음 | 유지 |
| Endpoint table | 없음 | 20-row table | 대폭 개선 |
| Helper functions | 없음 | 4개 명시 | 대폭 개선 |
| `clock_routing_in/out` | 없음 | 4x5 mesh | 대폭 개선 |
| Dispatch feedthrough | 거의 없음 | 6-wire topology | 대폭 개선 |
| Flit wiring dimensions | 없음/약함 | 4D arrays | 개선 |
| L1 EDC daisy-chain | 없음/약함 | overlay topic에 있음 | 개선 |
| GridConfig ASCII map | 없음 | 없음 | 미해결 |
| Level-1 generate hierarchy | 없음 | 없음 | 미해결 |
| NOC2AXI_ROUTER port mapping | 없음 | 없음 | 미해결 |
| NoC repeater instance/count | 없음 | 없음/매우 얕음 | 미해결 |
| EDC flat arrays | 없음 | 없음 | 미해결 |
| PRTN chain taps | 없음 | 없음 | 미해결 |
| Top parameters | 없음 | 없음 | 미해결 |

v9.2의 의미:

- v9.2는 v9.1에서 제안했던 checklist 중 "찾기 쉬운 structural identifiers"를 실제로 회수했다.
- 특히 EP table, helper functions, clock routing, dispatch wires는 정답지 fidelity를 실질적으로 끌어올렸다.
- 다만 "배열 이름"과 "실제 generate/port connection 의미" 사이의 마지막 간극은 아직 남아 있다.

---

## 5. 종합 점수

`N1B0_HDD_v0.1.md` 기준 Codex 보수 평가:

| 섹션 | 가중치 | v9.1 통합본 | v9.2 통합본 | v9.2 가중 점수 |
|---|---:|---:|---:|---:|
| Overview / N1B0 identity | 8% | 64% | 65% | 5.2 |
| Package constants / `tile_t` / endpoint | 22% | 65% | 78% | 17.2 |
| Top-level ports | 14% | 72% | 74% | 10.4 |
| Module hierarchy | 12% | 55% | 58% | 7.0 |
| NoC fabric connections | 10% | 44% | 52% | 5.2 |
| Clock/reset routing | 10% | 48% | 68% | 6.8 |
| EDC ring/interface | 8% | 62% | 64% | 5.1 |
| Dispatch feedthrough | 5% | 24% | 62% | 3.1 |
| PRTN/ISO/power | 5% | 60% | 60% | 3.0 |
| Memory config / SRAM | 3% | 58% | 58% | 1.7 |
| RTL file map / DFX / verification | 3% | 43% | 45% | 1.4 |
| **합계** | **100%** | **~57.5%** | — | **~66~68%** |

위 표는 보수적인 **통합 HDD 단독 기준**이다. v9.2의 table density와 EP/dispatch/clock 복구를 조금 더 후하게 보면 **68~70%**까지 인정 가능하다.

v9.2 전체 산출물을 best-of로 보면 다음 항목이 추가 인정된다.

| 추가 인정 항목 | 근거 파일 | 효과 |
|---|---|---:|
| EDC APB 16-port table | `v9.2_edc.md` | +2~3pp |
| NoC endpoint map + flit 4D arrays | `v9.2_noc.md` | +2~3pp |
| L1 EDC daisy-chain generate blocks | `v9.2_overlay.md` | +1~2pp |
| Grounding coverage matrix | `v9.2_chip_grounded.md` | +1~2pp |
| raw full-chip EP/wire/clock table | `v9.2_chip_no_grounding.md` | +2~3pp |

따라서 **v9.2 folder-level 품질은 약 76~78%**로 보는 것이 균형적이다.

정성 판정:

- 정답지 "핵심 좌표계" 기준: **중상**
- 정답지 "top-level signal category" 기준: **상**
- 정답지 "상세 port table" 기준: **중**
- 정답지 "wiring/topology 설명" 기준: **중하**
- 실사용 초안 가치: **상**
- 그대로 정답지 대체 가능성: **아직 중간**
- v9.2 산출물 전체의 전략적/파이프라인 가치: **상**

---

## 6. 남은 핵심 Gap

### 6.1 P0: 정답지 fidelity를 더 올리려면 반드시 필요한 항목

| Gap | 정답지 위치 | v9.2 상태 | 권장 source/query |
|---|---|---|---|
| `GridConfig[y][x]` tile map | Section 2.3 | 없음 | `GridConfig`, `TENSIX`, `NOC2AXI_ROUTER` |
| helper function semantics | Section 2.5 | 이름만 있음 | `getTensixIndex`, `getNoc2AxiIndex`, scan order |
| top module parameter table | Section 3.1 | 없음 | `AXI_SLV_OUTSTANDING_READS`, `NPU_DATA_W` |
| Level-1 generate hierarchy | Section 4.1 | 없음 | `gen_x`, `gen_y`, `gen_noc2axi_router_ne_opt` |
| `NOC2AXI_ROUTER_*_OPT` dual-row wiring | Section 4.2/4.3 | type/EP만 있음 | `router_o_*`, `noc2axi_i_*`, `router_i_*`, `y-1` |
| NoC repeater placement | Section 5 | generic only | `repeaters_between_noc2axi`, `repeaters_between_router`, `NUM_REPEATERS=4/6` |
| clock entry/exception detail | Section 6 | array만 있음 | `clock_routing_in[x][4]`, `power_good`, `router_o_ai_clk` |
| EDC flat arrays | Section 7 | 없음 | `edc_ingress_intf`, `edc_egress_intf`, `loopback_edc_ingress_intf` |
| Dispatch port mapping | Section 8 | wire names만 있음 | `i_de_to_t6_east_feedthrough`, `o_de_west_to_t6_south` |
| PRTN internal chain taps | Section 9 | summary only | `w_left_prtnun_*[x][2]` |

### 6.2 P1: merge/reporting 보정

| Issue | 설명 | 권장 |
|---|---|---|
| 통합 HDD가 정답지 핵심 snippet을 아직 압축 | table은 늘었지만 code fence가 2개뿐 | critical wiring snippet preserve |
| Overview identity 약함 | HPDF replacement story 누락 | 첫 문단에 baseline delta 강제 |
| NoC repeater가 generic | Y=3/Y=4, 6/4 stage, instance names 없음 | repeater summary table 필수화 |
| EDC topic과 Trinity EDC arrays 분리 | EDC subsystem 문서는 있으나 top flat array는 없음 | top-level EDC array query 별도 |
| Grounding matrix 오해 가능 | KB coverage가 정답지 fidelity로 보일 수 있음 | claim coverage와 answer fidelity 분리 표기 |
| file map 축소 | N1B0-specific files 부족 | 정답지 Section 11 기준 template화 |

---

## 7. 권장 다음 단계

### 7.1 v9.3 목표: "이름 회수"에서 "connection 의미 회수"로

v9.2는 구조물 이름 회수에 성공했다. 다음 버전은 같은 항목을 더 많이 추가하기보다, 이미 잡힌 구조물의 연결 의미를 정답지 수준으로 풀어야 한다.

필수 checklist:

- `GridConfig` 4x5 ASCII map
- helper functions의 scan/count semantics
- top module parameters 6개
- Level-1 generate hierarchy
- `NOC2AXI_ROUTER_*_OPT` dual-row span + port prefix mapping
- NoC repeater summary 4 rows with instance names and `NUM_REPEATERS`
- clock entry point + Y=4/Y=3 exception
- EDC flat arrays + router exception
- dispatch feedthrough port connection snippet
- PRTN internal chain and `w_left_prtnun_*[x][2]` tap
- N1B0-specific RTL file map

예상 효과:

- 통합 HDD 단독 68~70% -> 76~80%
- folder-level 76~78% -> 82~85%

### 7.2 merge 정책 개선

| 개선 | 이유 |
|---|---|
| Critical snippet preservation | 정답지는 table만이 아니라 wiring pseudo-code가 핵심 |
| Answer-template section requirements | `GridConfig`, generate hierarchy, repeater table 무음 누락 방지 |
| Topic best-of merge | `edc.md`, `noc.md`, `overlay.md`의 상세 table을 통합본에 흡수 |
| Claim coverage와 fidelity 분리 | grounded coverage와 정답지 점수 혼동 방지 |
| Regression facts suite | v9.2에서 확보한 EP/helper/dispatch/clock fact 재유실 방지 |

---

## 8. 최종 판정

v9.2는 좋다. v9.1이 "final merge hotfix"였다면, v9.2는 실제 정답지 gap을 겨냥한 구조적 개선판이다. EndpointIndex table, helper functions, dispatch feedthrough, clock routing array, flit 4D dimensions가 최종 통합 HDD에 들어온 것은 확실한 진전이다.

다만 아직 정답지의 본질인 generate/wiring 설명까지는 부족하다. 정답지는 단순히 EP table을 제공하는 문서가 아니라, 왜 `ROUTER`가 placeholder인지, composite `NOC2AXI_ROUTER_*_OPT`가 어떻게 Y=4/Y=3을 동시에 담당하는지, NoC repeaters가 어느 row와 direction에 몇 stage로 들어가는지, EDC/dispatch/clock 예외가 어떤 port에 걸리는지를 설명한다. v9.2는 이 중 일부 이름을 회수했지만, 연결 의미는 아직 요약 수준이다.

버전 흐름으로 보면:

- **v8:** top-level port surface 대폭 복구
- **v9:** grounding/tag/통합 HDD 체계를 도입했지만 final merge가 축약됨
- **v9.1:** `tile_t`/SFR/DFX/SRAM/Instruction Engine을 복구한 merge hotfix
- **v9.2:** EP/helper/dispatch/clock/flit 구조물을 회수한 topology checklist 1차 성공
- **다음 목표:** generate hierarchy와 port-level wiring semantics 회수

따라서 v9.2는 **통합 HDD 단독 기준 약 68~70%**, **v9.2 산출물 전체 best-of 기준 약 76~78%**로 평가한다. 다음 버전은 새로운 일반 설명보다, 정답지와 1:1 대응되는 connection snippet과 exception table을 강제로 보존하는 쪽이 가장 효율적이다.

---

*End of Review - Codex Review v9.2*
