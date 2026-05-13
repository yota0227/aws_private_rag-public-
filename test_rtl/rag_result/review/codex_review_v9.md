# Codex Review: RAG v9 정답지 비교 분석

**작성일:** 2026-05-06  
**리뷰어:** Codex  
**비교 대상:** `test_rtl/rag_result/v9/v9_N1B0_HDD.md` 중심, `test_rtl/rag_result/v9/` 전체 산출물 보조 비교  
**저장 위치:** `test_rtl/rag_result/review/codex_review_v9.md`  

---

## 0. 결론

v9 통합 HDD는 정답지 `N1B0_HDD_v0.1.md`와 비교하면 **v8 대비 회귀가 있다**. v8에서 확보했던 106-port category, PRTN/ISO, AXI/SFR/EDC IRQ 같은 핵심 top-level port coverage는 요약 형태로 유지됐지만, 정답지의 실질적인 가치를 만드는 `tile_t`, `GridConfig`, Endpoint table, helper functions, `NOC2AXI_ROUTER_*_OPT` dual-row 구조, NoC repeater placement, `clock_routing_in/out`, dispatch feedthrough, EDC flat interface arrays가 최종 통합 문서에서 대부분 빠졌다.

v9의 가장 큰 문제는 "RAG가 아무것도 못 찾은 것"이 아니다. `v9_chip_no_grounding.md`와 topic별 문서에는 일부 근거가 남아 있지만, 최종 HDD가 이를 충분히 병합하지 못하고 **짧은 summary 문서**로 수렴했다. 결과적으로 정답지 대체 문서라기보다는 architecture brief에 가깝다.

다만 점수 해석은 범위에 따라 달라진다.

- **통합 HDD 단독 기준:** `v9_N1B0_HDD.md`만 정답지 대체물로 보면 약 **49%**
- **v9 산출물 전체 best-of 기준:** `chip_no_grounding`, `chip_grounded`, `edc`, `noc`, `overlay`까지 함께 읽으면 약 **65~67%**

Claude `claude_review_v9.md`의 약 67% 평가는 후자에 가깝다. 특히 PRTN 14-port table, EDC 16-port table, grounding tag, KB Coverage Matrix 같은 성과를 topic/grounded 문서까지 포함해서 인정했다. 반대로 이 리뷰의 기존 49%는 최종 통합 HDD 단독 품질을 엄격히 본 숫자였다.

한 문장으로 요약하면:

> **v9는 final HDD 단독으로는 약 49% 수준의 축약판이지만, v9 폴더 전체 산출물을 best-of로 평가하면 약 65~67% 수준이다. 문제는 retrieval 자체보다 final merge가 topic 문서의 상세 정보를 충분히 보존하지 못한 데 있다.**

---

## 1. 참고한 파일

### 정답지

| 파일 | 역할 |
|---|---|
| `test_rtl/Sample/N1B0_HDD_v0.1.md` | 주 비교 기준. N1B0 4x5 variant HDD |
| `test_rtl/Sample/N1B0_NPU_HDD_v0.1.md` | 보조 비교 기준. NPU 관점 확장 HDD |

### v9 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v9/v9_N1B0_HDD.md` | v9 통합 HDD. 이번 리뷰의 핵심 대상 |
| `test_rtl/rag_result/v9/v9_chip_no_grounding.md` | raw RAG output. 상세 port table 일부 존재 |
| `test_rtl/rag_result/v9/v9_chip_grounded.md` | hybrid grounding output. `[FROM LLM]`, `[NOT IN KB]` 태그 포함 |
| `test_rtl/rag_result/v9/v9_edc.md` | EDC topic result |
| `test_rtl/rag_result/v9/v9_noc.md` | NoC topic result |
| `test_rtl/rag_result/v9/v9_overlay.md` | Overlay/RISC-V topic result |

### 비교 기준 리뷰

| 파일 | 참고 포인트 |
|---|---|
| `test_rtl/rag_result/review/codex_review_v8.md` | v8의 성과와 남은 P0 gap |
| `test_rtl/rag_result/v8/v8_N1B0_HDD.md` | v8 통합 HDD. v9 회귀 여부 비교 기준 |

---

## 2. 정량 비교

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[NOT IN KB]` |
|---|---:|---:|---:|---:|---:|---:|
| 정답지 `N1B0_HDD_v0.1.md` | 513 | 22330 | 40 | 186 | 24 | 0 |
| 정답지 `N1B0_NPU_HDD_v0.1.md` | 1290 | 58380 | 105 | 303 | 52 | 0 |
| v8 `v8_N1B0_HDD.md` | 480 | 17951 | 43 | 212 | 6 | 0 |
| v9 `v9_N1B0_HDD.md` | 252 | 8229 | 22 | 92 | 4 | 0 |
| v9 `chip_no_grounding` | 217 | 8801 | 17 | 84 | 2 | 0 |
| v9 `chip_grounded` | 224 | 6956 | 19 | 79 | 2 | 3 |
| v9 `edc` | 108 | 3228 | 9 | 19 | 2 | 0 |
| v9 `noc` | 103 | 3022 | 11 | 28 | 0 | 0 |
| v9 `overlay` | 71 | 1953 | 8 | 4 | 2 | 0 |

해석:

- v9 통합 문서는 정답지 대비 line count 약 49%, table rows 약 49%다.
- v8 대비 line count는 480에서 252로 줄었고, table rows는 212에서 92로 줄었다.
- v9는 별도 topic 문서까지 합치면 원천 정보량은 더 있지만, 최종 통합 HDD 기준으로는 정답지에 필요한 구조 정보가 크게 줄었다.
- `v9_chip_grounded.md`에는 `[FROM LLM]` 항목과 KB Coverage Matrix가 있다. 이는 v9의 구조적 개선점이다.
- 그런데 최종 `v9_N1B0_HDD.md`는 provenance tag와 topic별 상세 표를 제거/압축해, 통합본 단독 품질은 topic 묶음 기준보다 낮게 보인다.

### 2.1 점수 기준 차이: Codex 49% vs Claude 67%

| 평가 관점 | 포함 파일 | 장점 인정 방식 | 결과 |
|---|---|---|---:|
| 통합 HDD 단독 | `v9_N1B0_HDD.md` | 최종 문서에 직접 남은 내용만 인정 | ~49% |
| v9 산출물 전체 best-of | `v9/` 6개 문서 전체 | topic 문서와 grounded/no-grounding의 상세 정보를 함께 인정 | ~65~67% |

차이가 난 핵심 이유:

- Claude 리뷰는 `test_rtl/rag_result/v9/` 전체를 scope로 두고, `v9_chip_no_grounding.md`의 PRTN/EDC 상세 table과 `v9_chip_grounded.md`의 grounding tag를 v9 성과로 인정했다.
- 이 리뷰의 기존 49%는 `v9_N1B0_HDD.md`를 "최종 납품 HDD"로 보고, 그 안에 병합되지 않은 상세 정보는 감점했다.
- 따라서 두 점수는 모순이라기보다 **문서 단독 품질 vs 산출물 묶음 품질**의 차이다.

---

## 3. 섹션별 정답지 비교

### 3.1 Overview

정답지 핵심:

- N1B0은 baseline Trinity에서 `trinity_noc2axi_n_opt + trinity_router` tile pair를 `trinity_noc2axi_router_ne/nw_opt` HPDF tile로 교체한 변형이다.
- 통합 HPDF tile은 Y=4 NOC2AXI와 Y=3 router logic을 함께 담는 dual-row 구조다.
- per-column AI/DM clock/reset, PRTN, ISO_EN, NoC repeater buffers가 N1B0 addition이다.

v9:

- 4x5 mesh, 20 nodes, 12 Tensix, 4 NIU, 2 Dispatch, EDC, multi-clock domain은 포함한다.
- 하지만 N1B0의 핵심 변경인 HPDF replacement story가 Overview에 없다.
- baseline Trinity와 N1B0 차이도 설명하지 않는다.

판정: **보통. 약 60%**

### 3.2 Package Constants and Grid

v9는 다음 package constants를 유지한다:

| 항목 | 정답지 | v9 |
|---|---:|---:|
| `SizeX` | 4 | 4 |
| `SizeY` | 5 | 5 |
| `NumNodes` | 20 | 20 |
| `NumTensix` | 12 | 12 |
| `NumNoc2Axi` | 4 | 4 |
| `NumDispatch` | 2 | 2 |
| `NumApbNodes` | 4 | 4 |
| `NumDmComplexes` | 14 | 14 |
| `EnableDynamicRouting` | 1 | `1'b1` |
| `TensixPerCluster` | 4 | 4 |
| `DMCoresPerCluster` | 8 | 8 |

좋은 점:

- 13 parameter/localparam 수준의 기본 숫자는 안정적이다.
- `isEastEdge(int x)` package function을 새로 언급했다.

부족:

- 정답지의 `tile_t` 8-member enum이 최종 통합 문서에서 빠졌다.
- `GridConfig[y][x]` 4x5 tile map이 없다.
- `EndpointIndex = x*5+y` 공식과 20-row endpoint table이 없다.
- `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex` helper functions가 없다.
- `NOC2AXI_ROUTER_NE/NW_OPT`가 Y=4와 Y=3을 동시에 점유한다는 package-level 해석이 없다.

판정: **v8 대비 회귀. 약 48%**

### 3.3 Top-Level Ports

v9의 가장 쓸 만한 부분이다.

좋은 점:

- N1B0 variant의 **106 total ports** count를 유지한다.
- category별 count를 유지한다:
  - AXI 39
  - EDC APB 16
  - APB register 8
  - SFR memory config 17
  - PRTN power 14
  - DM/AI/NoC/Tensix reset groups
- `i_ai_clk[3:0]`, `i_dm_clk[3:0]`, `i_tensix_reset_n[11:0]`, `i_dm_core_reset_n[13:0][7:0]` 같은 key widths는 유지한다.

부족:

- 정답지의 top module parameters가 빠졌다:
  - `AXI_SLV_OUTSTANDING_READS=64`
  - `AXI_SLV_OUTSTANDING_WRITES=32`
  - `AXI_SLV_RD_RDATA_FIFO_DEPTH=512`
  - `NPU_DATA_W=512`
  - `NPU_IN_ADDR_W=56`
  - `NPU_OUT_ADDR_W=56`
- `npu_out_*`와 `npu_in_*` full AXI channel 설명이 없다.
- APB register ports는 category만 있고 `[NumApbNodes]` array dimension detail이 없다.
- EDC APB는 IRQ 5개만 요약되어 있고 `[4]` array dimension 및 APB field table이 최종 통합 HDD에 없다.
- SFR memory config 17 ports는 category만 있고 family별 signal table이 없다.
- PRTN 14 ports도 최종 HDD에서는 signal별 width/direction table이 아니라 요약 문장이다.

참고:

- `v9_chip_no_grounding.md`에는 EDC APB와 PRTN table이 더 자세히 있다. 하지만 최종 통합 HDD에는 반영되지 않았다.

판정: **category coverage는 좋지만 상세도 부족. 약 62%**

### 3.4 Module Hierarchy

v9:

- `tt_tensix_with_l1 x12`, dispatch east/west, EDC connector, NoC module list, NIU timeout module을 나열한다.
- `trinity_router`가 N1B0에서 instantiated되지 않는다는 note는 유지한다.

부족:

- 정답지의 Level-1 generate instantiation map이 없다:
  - `gen_x[0] gen_y[4]: gen_noc2axi_ne_opt`
  - `gen_x[1] gen_y[4]: gen_noc2axi_router_ne_opt`
  - `gen_x[2] gen_y[4]: gen_noc2axi_router_nw_opt`
  - `gen_x[3] gen_y[4]: gen_noc2axi_nw_opt`
  - `gen_dispatch_e/w`, `gen_tensix`
- `NOC2AXI_ROUTER_*_OPT` dual-row span과 internal `trinity_noc2axi_n_opt` + `trinity_router` logic 설명이 없다.
- `router_o_*`, `noc2axi_i_*`, `router_i_*`, `i_de_to_t6_*` port group mapping이 없다.
- v8에 있던 DFX hierarchy가 최종 v9에서 사라졌다.
- v9 hierarchy는 actual generate hierarchy라기보다 topic별 module keyword list에 가깝다.

판정: **낮음. 약 45%**

### 3.5 Compute Tile - Tensix

v9:

- FPU, SFPU, TDMA, L1 cache를 언급한다.
- `tt_fp_max_array`, `tt_dual_align`, `tt_fpu_gtile_SDUMP_INTF`, `tt_sfpu_lregs`, `tt_tdma_*` 등 일부 module명을 유지한다.

부족:

- 정답지/보조 정답지의 compute tile 내부 구조에 비해 operation/data path 설명이 얕다.
- TRISC/BRISC, G-Tile/M-Tile, DEST/SRCA/SRCB, L1 partition detail은 거의 없다.
- L1/SRAM/EDC modport 연결도 빠졌다.

판정: **v8과 유사하거나 소폭 하락. 약 45%**

### 3.6 Dispatch Engine

정답지 핵심:

- Dispatch East/West 위치와 endpoint.
- `de_to_t6_coloumn[SizeX][SizeY-1][2]`
- `de_to_t6_east/west[SizeX]`
- `t6_to_de[SizeX][SizeY-2]`
- `t6_to_de_accross_east/west[SizeX][SizeX]`
- `NOC2AXI_ROUTER_*_OPT` tile이 dispatch feedthrough를 carry한다는 점.

v9:

- `tt_dispatch_top_inst_east`, `tt_dispatch_top_inst_west` 두 instance만 표로 제시한다.

부족:

- 위치 `(X=0,Y=3)`, `(X=3,Y=3)`와 EP=3/18이 없다.
- feedthrough array와 port mapping이 전부 없다.
- dispatch-private L1, overlay, NoC/NIU/router wrapper relationship도 없다.

판정: **매우 낮음. 약 22%**

### 3.7 NoC Fabric

v9:

- DIM_ORDER, TENDRIL, DYNAMIC routing algorithms를 언급한다.
- `tt_noc_repeaters_cardinal`, `noc_arbiter_tree`, SECDED, CDC, async FIFO, skid buffer, harvest sync, timeout module을 나열한다.

부족:

- 정답지의 핵심인 X-axis manual assignment와 repeater placement가 없다.
- Y=3 router row 6 repeaters, Y=4 NOC2AXI row 4 repeaters가 없다.
- `noc_east2west_req_repeaters_between_noc2axi`, `noc_west2east_req_repeaters_between_router` 같은 instance naming이 없다.
- row별 direct/repeated connection 구분이 없다.
- south/east/west edge tie-off 설명이 없다.

판정: **module keyword coverage는 있으나 N1B0 topology coverage는 낮음. 약 40%**

### 3.8 EDC

v9:

- EDC module hierarchy는 비교적 괜찮다.
- `tt_edc1_biu_soc_apb4_wrap`, `edc1_biu_soc_apb4_inner`, `tt_edc1_noc_sec_block_reg`, `tt_edc1_serial_bus_repeater`, `tt_edc1_intf_connector`를 포함한다.
- U-shape ring, direct + loopback connection, harvest bypass, 5 IRQ outputs를 언급한다.

부족:

- 정답지의 flat arrays가 없다:
  - `edc_ingress_intf[SizeX*SizeY]`
  - `edc_egress_intf[SizeX*SizeY]`
  - `loopback_edc_ingress_intf[SizeX*SizeY]`
  - `loopback_edc_egress_intf[SizeX*SizeY]`
- endpoint index와 EDC array index가 같다는 설명이 없다.
- `NOC2AXI_ROUTER_*_OPT`에서 Y=4 EDC interface가 없고 Y=3 index만 연결된다는 예외가 없다.
- EDC APB `[4]` array dimension이 최종 통합 HDD에는 빠졌다.

판정: **중간. 약 58%**

### 3.9 Clock and Reset

v9:

- `i_axi_clk`, `i_noc_clk`, `i_ai_clk[3:0]`, `i_dm_clk[3:0]` clock table은 있다.
- reset width table도 있다.
- `tt_clkbuf`, `tt_clkgater`/`tt_clk_gater`는 언급한다.

부족:

- `trinity_clock_routing_t` struct가 없다.
- `clock_routing_in[SizeX][SizeY]`, `clock_routing_out[SizeX][SizeY]` arrays가 없다.
- Y=4 entry point와 `power_good = i_edc_reset_n` 설명이 없다.
- reset packing with `getTensixIndex`가 없다.
- `NOC2AXI_ROUTER_*_OPT`의 Y=4 output unused, Y=3 `router_o_*` drive exception이 없다.
- `noc_clk` bypass observation이 없다.

판정: **낮음. 약 45%**

### 3.10 Power Management / PRTN / ISO

v9:

- 4-column daisy-chain, `ISO_EN[11:0]`, PRTNUN protocol, `TIEL_DFT_MODESCAN`을 언급한다.

부족:

- 최종 통합 HDD에는 PRTN port별 width/direction table이 없다.
- per-column chain `external -> [x][2] -> [x][1] -> [x][0] -> output`이 없다.
- `PRTNUN_UN2FC_DATA_OUT[x]`와 `PRTNUN_UN2FC_INTR_OUT[x]`가 `w_left_prtnun_*[x][2]`에서 tap된다는 detail이 없다.

판정: **요약 수준. 약 55%**

### 3.11 Memory Config / SRAM

v9:

- Top-level category에서 SFR memory config 17 ports를 언급한다.
- Overlay section에 FDS/CSR register modules를 둔다.

부족:

- 정답지의 Memory Config table이 없다.
- `SFR_RF_2P_HSC_*`, `SFR_RA1_HS_*`, `SFR_RF1_HS_*`, `SFR_RF1_HD_*` family별 width와 적용 tile 정보가 없다.
- v8에 있던 SRAM inventory section이 최종 v9에서 빠졌다.
- `tt_mem_wrap_32x1024_2p_nomask`, `RF_2P_HSC_LVT_32X136M1FB1WM0DR0` 같은 SRAM macro inventory가 없다.

판정: **낮음. 약 35%**

### 3.12 DFX

v9 통합 HDD에는 DFX section이 없다.

v8에는 다음이 있었다:

- `tt_instrn_engine_wrapper_dfx`
- `tt_disp_eng_noc_niu_router_dfx`
- `tt_disp_eng_l1_partition_dfx`
- `tt_disp_eng_overlay_wrapper_dfx`
- ATT BIST
- DFX SRAM macro relation

v9에서는 `v9_chip_grounded.md`에 DFX가 `[FROM LLM]`/`[NOT IN KB]` 수준으로만 남고, 최종 통합 HDD에는 병합되지 않았다.

판정: **거의 없음. 약 15%**

### 3.13 RTL File Reference

v9:

- `rtl/trinity.sv`, `rtl/targets/4x5/trinity_pkg.sv`, `used_in_n1/rtl/trinity.sv`, `mem_port`, legacy variant를 포함한다.

부족:

- 정답지의 N1B0-specific file map이 부족하다:
  - `trinity_noc2axi_router_ne_opt.sv`
  - `trinity_noc2axi_router_nw_opt.sv`
  - `trinity_noc2axi_ne_opt.sv`
  - `trinity_noc2axi_nw_opt.sv`
  - `trinity_router.sv`
  - `tt_tensix_with_l1`
  - `tt_dispatch_top_east/west`
  - `tt_noc_repeaters`
  - `tt_edc1_intf_connector`
- `v9_chip_no_grounding.md`에도 file reference가 제한적이다.

판정: **낮음. 약 40%**

---

## 4. v8 -> v9 변화 분석

| 항목 | v8 | v9 | 변화 |
|---|---|---|---|
| 문서 크기 | 480 lines / 17.9KB | 252 lines / 8.2KB | 대폭 감소 |
| Table rows | 212 | 92 | 대폭 감소 |
| Package constants | 13 constants + enum + EP table | 13 constants only | 회귀 |
| `tile_t` enum | 있음 | 없음 | 회귀 |
| Endpoint table | 20 rows | 없음 | 회귀 |
| Top ports | category + detailed tables | category summary | 회귀 |
| AXI | partial table + npu_in summary | category only | 회귀 |
| SFR memory config | 17-port table | category only | 회귀 |
| PRTN/ISO | full port table + section | summary only | 회귀 |
| Module hierarchy | detailed module tree, NIU EPs, DFX | short generic tree | 회귀 |
| NoC topology | module list only, weak | module list only, weak | 동등/소폭 회귀 |
| Clock routing arrays | 부족 | 없음 | 동등/회귀 |
| Dispatch feedthrough | 부족 | 없음 | 동등 |
| EDC | module facts + APB/IRQ | module facts + generic topology | 비슷하나 array detail 없음 |
| DFX | section 있음 | 없음 | 회귀 |
| Source traceability | appendix | appendix | 유지 |

v9의 의미:

- v9는 v8의 다음 개선판이 아니라, 다른 merge/reporting 정책으로 만들어진 **축약형 통합 HDD**로 보인다.
- `chip_no_grounding`에는 detailed table이 일부 살아 있는데, 최종 통합 문서가 이를 버렸다.
- `chip_grounded`에는 `[FROM LLM]` 기반 내용이 있는데, 최종 통합 문서는 grounding provenance를 유지하지 않는다.
- 따라서 v9의 병목은 parser보다 **final synthesis/merge 단계**에 더 가깝다.

---

## 5. 종합 점수

`N1B0_HDD_v0.1.md` 기준 Codex 보수 평가:

| 섹션 | 가중치 | v8 충족도 | v9 충족도 | v9 가중 점수 |
|---|---:|---:|---:|---:|
| Overview / N1B0 identity | 8% | 78% | 60% | 4.8 |
| Package constants / `tile_t` / endpoint | 22% | 94% | 48% | 10.6 |
| Top-level ports | 14% | 84% | 62% | 8.7 |
| Module hierarchy | 12% | 67% | 45% | 5.4 |
| NoC fabric connections | 10% | 42% | 40% | 4.0 |
| Clock/reset routing | 10% | 68% | 45% | 4.5 |
| EDC ring/interface | 8% | 81% | 58% | 4.6 |
| Dispatch feedthrough | 5% | 25% | 22% | 1.1 |
| PRTN/ISO/power | 5% | 78% | 55% | 2.8 |
| Memory config / SRAM | 3% | 68% | 35% | 1.1 |
| RTL file map / DFX / verification | 3% | 50% | 30% | 0.9 |
| **합계** | **100%** | **~72.9%** | — | **~48.5%** |

위 표는 **통합 HDD 단독 기준**이다. v9 전체 산출물을 best-of로 보면 다음 항목이 추가 인정된다.

| 추가 인정 항목 | 근거 파일 | 효과 |
|---|---|---:|
| PRTN 14-port 상세 table | `v9_chip_no_grounding.md` | +3~5pp |
| EDC 16-port APB/IRQ table | `v9_chip_no_grounding.md`, `v9_edc.md` | +3~4pp |
| Hybrid grounding tag 체계 | `v9_chip_grounded.md` | +3~5pp |
| KB Coverage Matrix | `v9_chip_grounded.md` | +2~3pp |
| grounded/no-grounding A/B 산출 구조 | `v9_chip_grounded.md`, `v9_chip_no_grounding.md` | +2~3pp |

따라서 **v9 folder-level 품질은 약 65~67%**로 보는 것이 더 균형적이다. 이 경우 Claude 리뷰의 `~67%`와 거의 같은 결론이다.

정성 판정:

- 정답지 "핵심 좌표계" 기준: **중하**
- 정답지 "top-level signal category" 기준: **중상**
- 정답지 "상세 port table" 기준: **중하**
- 정답지 "wiring/topology 설명" 기준: **하**
- 실사용 초안 가치: **요약 자료로는 가능**
- 그대로 정답지 대체 가능성: **낮음**
- v9 산출물 전체의 전략적/파이프라인 가치: **중상**

---

## 6. 남은 핵심 Gap

### 6.1 P0: v9 최종 통합 문서에서 즉시 복구해야 할 항목

| Gap | 정답지 위치 | v9 상태 | 권장 source |
|---|---|---|---|
| `tile_t` enum + `GridConfig` | Section 2.2/2.3 | 없음 | `trinity_pkg.sv`, v8 document |
| Endpoint table 20 rows | Section 2.4 | 없음 | `EndpointIndex = x*SizeY+y` |
| helper functions | Section 2.5 | 없음 | `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex` |
| AXI/SFR/PRTN detailed port tables | Section 3.2 | category only | `v9_chip_no_grounding.md`, v8 detail |
| `NOC2AXI_ROUTER_*_OPT` dual-row hierarchy | Section 4.1-4.3 | 없음 | `trinity_noc2axi_router_ne/nw_opt` |
| NoC repeater placement | Section 5 | 없음 | `repeaters_between_noc2axi`, `repeaters_between_router` |
| `clock_routing_in/out` arrays | Section 6 | 없음 | `clock_routing_in`, `clock_routing_out`, `router_o_ai_clk` |
| EDC flat arrays and router exception | Section 7 | 없음 | `edc_ingress_intf`, `loopback_edc_ingress_intf` |
| Dispatch feedthrough | Section 8 | 없음 | `de_to_t6_*`, `t6_to_de_*` |
| PRTN internal chain taps | Section 9 | 없음 | `w_left_prtnun_*[x][2]` |

### 6.2 P1: 품질/표현 보정

| Issue | 설명 | 권장 |
|---|---|---|
| Grounding provenance 손실 | `chip_grounded`에는 `[FROM LLM]`가 있는데 최종 문서에는 태그 없음 | final merge에 provenance column/tag 유지 |
| Topic 문서 내용 미병합 | `chip_no_grounding`의 port tables가 최종 HDD에 빠짐 | final synthesis가 상세 표를 우선 채택 |
| N1B0 identity 약화 | HPDF replacement story가 Overview에서 빠짐 | Overview 첫 문단에 baseline delta 복구 |
| Overlay section 위치 | 정답지 N1B0 HDD의 핵심 섹션은 아님 | Appendix 또는 NPU 확장 섹션으로 분리 |
| DFX 삭제 | v8의 DFX section이 v9 final에서 사라짐 | `chip_grounded` 기반으로 최소 DFX section 복구 |
| File map 축소 | N1B0-specific RTL files가 빠짐 | 정답지 Section 11 수준으로 확장 |

---

## 7. 권장 다음 단계

### 7.1 v9.1 hotfix: final merge template 복구

v9는 parser보다 final merge 단계가 문제로 보인다. 다음 항목을 template 필수 섹션으로 강제하는 것이 가장 빠른 개선이다.

필수 섹션:

- Package constants + `tile_t` enum + `GridConfig` + Endpoint table
- Top-level parameters
- Full top-level port groups:
  - AXI
  - APB register
  - EDC APB + IRQ
  - SFR memory config
  - PRTN/ISO
- Level-1 generate hierarchy
- `NOC2AXI_ROUTER_*_OPT` critical details
- NoC manual X-axis connection + repeater summary
- Clock/reset routing arrays
- EDC arrays
- Dispatch feedthrough
- PRTN daisy chain
- Memory config table
- RTL file map

예상 효과:

- v9 final score 49% -> 65% 이상 가능
- `v9_chip_no_grounding.md`에 이미 있는 port detail만 재병합해도 top-level port section은 62% -> 75% 수준까지 회복 가능
- v8 문서 구조를 template로 재사용하면 v9 회귀 대부분을 줄일 수 있음

### 7.2 다음 retrieval/parser 목표

v8 리뷰의 다음 목표는 여전히 유효하다. v9도 이 부분은 해결하지 못했다.

| 목표 | Query/source |
|---|---|
| Clock routing | `clock_routing_in`, `clock_routing_out`, `router_o_ai_clk`, `router_o_dm_clk` |
| Dispatch feedthrough | `de_to_t6_coloumn`, `de_to_t6_east`, `de_to_t6_west`, `t6_to_de`, `t6_to_de_accross` |
| NoC repeaters | `repeaters_between_noc2axi`, `repeaters_between_router`, `NUM_REPEATERS` |
| EDC arrays | `edc_ingress_intf`, `edc_egress_intf`, `loopback_edc_ingress_intf` |
| Helper functions | `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex` |
| PRTN internals | `w_left_prtnun`, `PRTNUN_FC2UN`, `PRTNUN_UN2FC` |

---

## 8. 최종 판정

v9는 v8에서 기대했던 "generate/wiring topology extraction" 단계로 나아가지 못했다. 오히려 최종 통합 HDD만 보면 v8이 확보했던 상세 정보까지 잃은 상태다. 특히 정답지의 핵심인 tile map, endpoint index, helper functions, NOC2AXI_ROUTER dual-row semantics, NoC repeater placement, clock routing, EDC arrays, dispatch feedthrough가 빠진 것은 큰 회귀다.

다만 완전히 나쁜 결과는 아니다. 106-port category count, 기본 package constants, EDC/NoC/Overlay module keywords, PRTN/ISO summary는 남아 있다. 즉 v9는 "아키텍처 브리프"로는 읽을 수 있지만, 정답지급 HDD로는 부족하다.

버전 흐름으로 보면:

- **v6c:** package/grid anchor 복구
- **v7:** DM/APB/EDC APB, TDMA/SRAM/DFX fact 확장
- **v8:** AXI/SFR/PRTN/ISO/EDC IRQ 등 top-level port surface 대폭 복구
- **v9:** final merge가 축약형으로 바뀌며 상세 정보 회귀

따라서 v9는 **통합 HDD 단독으로는 정답지 재현도 약 49% 수준**, **v9 산출물 전체 best-of 기준으로는 약 65~67% 수준**으로 평가한다. Claude 리뷰의 67%는 후자 기준이므로 타당하다. v9.1에서는 새 parser를 추가하기 전에, 우선 v8 수준의 final merge template와 상세 표 병합 정책을 복구하는 것이 가장 효율적이다.

---

*End of Review - Codex Review v9*
