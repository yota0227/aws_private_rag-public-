# Codex Review: RAG v9.1 정답지 비교 분석

**작성일:** 2026-05-06  
**리뷰어:** Codex  
**비교 대상:** `test_rtl/rag_result/v9.1/v9.1_N1B0_HDD.md` 중심, `test_rtl/rag_result/v9.1/` 전체 산출물 보조 비교  
**저장 위치:** `test_rtl/rag_result/review/codex_review_v9.1.md`  

---

## 0. 결론

v9.1은 v9에서 지적했던 final merge 회귀를 일부 회복한 hotfix 성격의 개선판이다. 특히 최종 통합 HDD에 `tile_t` enum, baseline enum, `isNorthEdge`, Instruction Engine submodules, SFR memory family, SRAM inventory, DFX/JTAG section이 들어오면서 v9의 "너무 짧은 architecture brief" 느낌은 많이 줄었다.

하지만 정답지 `N1B0_HDD_v0.1.md`의 핵심인 `GridConfig`, EndpointIndex 20-row table, helper functions, `NOC2AXI_ROUTER_*_OPT` dual-row wiring, NoC repeater placement, `clock_routing_in/out`, EDC flat interface arrays, dispatch feedthrough는 여전히 빠져 있다. 즉 v9.1은 **summary 병합 품질은 개선했지만 generate/wiring/topology 추출 병목은 아직 해결하지 못했다.**

점수는 두 기준으로 분리하는 것이 맞다.

- **통합 HDD 단독 기준:** `v9.1_N1B0_HDD.md`만 정답지 대체물로 보면 약 **57%**
- **v9.1 산출물 전체 best-of 기준:** `chip_no_grounding`, `chip_grounded`, `edc`, `noc`, `overlay`까지 함께 읽으면 약 **70~72%**

한 문장으로 요약하면:

> **v9.1은 v9의 final-merge 회귀를 상당 부분 수복해 folder-level 품질을 70% 근처까지 회복했지만, 정답지의 후반부를 구성하는 wiring/topology 계층은 아직 미해결이다.**

---

## 1. 참고한 파일

### 정답지

| 파일 | 역할 |
|---|---|
| `test_rtl/Sample/N1B0_HDD_v0.1.md` | 주 비교 기준. N1B0 4x5 variant HDD |
| `test_rtl/Sample/N1B0_NPU_HDD_v0.1.md` | 보조 비교 기준. NPU 관점 확장 HDD |

### v9.1 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v9.1/v9.1_N1B0_HDD.md` | v9.1 통합 HDD. 이번 리뷰의 핵심 대상 |
| `test_rtl/rag_result/v9.1/v9.1_chip_no_grounding.md` | raw RAG full-chip HDD. 상세 port/category 정보 보유 |
| `test_rtl/rag_result/v9.1/v9.1_chip_grounded.md` | hybrid grounding output. KB/LLM/NOT IN KB 태그 및 coverage matrix 포함 |
| `test_rtl/rag_result/v9.1/v9.1_edc.md` | EDC topic result. EDC APB 16-port table 포함 |
| `test_rtl/rag_result/v9.1/v9.1_noc.md` | NoC topic result. NoC module/CDC/arbitration 설명 확장 |
| `test_rtl/rag_result/v9.1/v9.1_overlay.md` | Overlay/RISC-V topic result |

### 비교 기준 리뷰

| 파일 | 참고 포인트 |
|---|---|
| `test_rtl/rag_result/review/codex_review_v9.md` | v9의 final HDD 단독 vs folder-level 점수 분리 기준 |
| `test_rtl/rag_result/review/claude_review_v9.md` | v9 전체 산출물 best-of 관점 |
| `test_rtl/rag_result/v8/v8_N1B0_HDD.md` | v8에서 확보했던 상세 섹션 회귀/복구 비교 |

---

## 2. 정량 비교

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[FROM LLM]` | `[NOT IN KB]` |
|---|---:|---:|---:|---:|---:|---:|---:|
| 정답지 `N1B0_HDD_v0.1.md` | 513 | 22330 | 40 | 186 | 24 | 0 | 0 |
| 정답지 `N1B0_NPU_HDD_v0.1.md` | 1290 | 58380 | 105 | 303 | 52 | 0 | 0 |
| v8 `v8_N1B0_HDD.md` | 480 | 17951 | 43 | 212 | 6 | 0 | 0 |
| v9 `v9_N1B0_HDD.md` | 252 | 8229 | 22 | 92 | 4 | 0 | 0 |
| v9.1 `v9.1_N1B0_HDD.md` | 331 | 11274 | 27 | 117 | 4 | 0 | 0 |
| v9.1 `chip_no_grounding` | 358 | 13790 | 34 | 135 | 2 | 0 | 0 |
| v9.1 `chip_grounded` | 389 | 16852 | 34 | 177 | 2 | 11 | 7 |
| v9.1 `edc` | 159 | 5479 | 15 | 33 | 4 | 0 | 0 |
| v9.1 `noc` | 225 | 7194 | 30 | 42 | 8 | 0 | 0 |
| v9.1 `overlay` | 160 | 5215 | 19 | 15 | 2 | 0 | 0 |

해석:

- v9.1 통합 HDD는 v9 대비 252 → 331 lines, 92 → 117 table rows로 증가했다.
- `chip_grounded`는 389 lines / 177 table rows로 정답지 `N1B0_HDD_v0.1.md`의 표 밀도에 근접한다.
- v9.1은 v9에서 축약됐던 SFR/DFX/Instruction Engine/grounding matrix를 일부 복구했다.
- 반면 정답지의 code fence 24개 대비 v9.1 통합 HDD는 4개뿐이다. 이는 여전히 pseudo-code, wiring, topology diagram 재현이 약하다는 신호다.

### 2.1 점수 기준

| 평가 관점 | 포함 파일 | 장점 인정 방식 | 결과 |
|---|---|---|---:|
| 통합 HDD 단독 | `v9.1_N1B0_HDD.md` | 최종 문서에 직접 남은 내용만 인정 | ~57% |
| v9.1 산출물 전체 best-of | `v9.1/` 6개 문서 전체 | topic 문서와 grounded/no-grounding 상세 정보를 함께 인정 | ~70~72% |

주의:

- `v9.1_chip_grounded.md`의 KB Coverage Matrix는 자체 기준으로 **89%**를 제시한다.
- 이 89%는 "문서 안의 주장 중 KB-confirmed로 표시된 비율"에 가깝고, **정답지 fidelity 89%가 아니다.**
- 정답지 fidelity는 빠진 핵심 구조물까지 고려해야 하므로 70% 초반 이상으로 보긴 어렵다.

---

## 3. 섹션별 정답지 비교

### 3.1 Overview

정답지 핵심:

- N1B0은 baseline Trinity에서 `trinity_noc2axi_n_opt + trinity_router` tile pair를 `trinity_noc2axi_router_ne/nw_opt` HPDF tile로 교체한 변형이다.
- 통합 HPDF tile은 Y=4 NOC2AXI와 Y=3 router logic을 함께 담는 dual-row 구조다.
- per-column AI/DM clock/reset, PRTN, ISO_EN, NoC repeater buffers가 N1B0 addition이다.

v9.1:

- 4x5 mesh, 20 nodes, 12 Tensix, 4 NIU, 2 Dispatch, 14 DM complexes, EDC, dynamic routing을 포함한다.
- `trinity_router`가 N1B0에서 EMPTY by design이라는 note가 Overview에 올라왔다.

부족:

- HPDF replacement story가 아직 Overview에 없다.
- `trinity_noc2axi_router_ne/nw_opt`가 baseline pair를 대체했다는 핵심 delta가 없다.
- baseline vs N1B0 차이 table도 없다.

판정: **v9 대비 소폭 개선. 약 64%**

### 3.2 Package Constants and Grid

v9.1 개선:

| 항목 | v9 | v9.1 | 판정 |
|---|---|---|---|
| 13 localparams | 있음 | 있음 | 유지 |
| N1B0 `tile_t` enum | 없음 | 있음 | 개선 |
| baseline `tile_t` enum | 없음 | 있음 | 개선 |
| `isEastEdge` | 있음 | 있음 | 유지 |
| `isNorthEdge` | 없음 | 있음 | 개선 |

좋은 점:

- `TENSIX`, `NOC2AXI_NE_OPT`, `NOC2AXI_ROUTER_NE_OPT`, `NOC2AXI_ROUTER_NW_OPT`, `NOC2AXI_NW_OPT`, `DISPATCH_E`, `DISPATCH_W`, `ROUTER` encoding이 최종 통합 HDD에 복구됐다.
- baseline enum까지 함께 제시해 N1B0 enum delta를 이해할 단서가 생겼다.

부족:

- 정답지의 `GridConfig[y][x]` 4x5 tile map이 없다.
- `EndpointIndex = x*5+y` 공식과 20-row endpoint table이 없다.
- `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex` helper functions가 없다.
- `ROUTER` placeholder가 EndpointIndex 8/13을 reserve한다는 설명은 없다.
- `NOC2AXI_ROUTER_NE/NW_OPT`가 Y=4와 Y=3을 동시에 점유한다는 package-level 해석이 약하다.

판정: **v9 대비 크게 개선. 약 65%**

### 3.3 Top-Level Ports

v9.1:

- 106 total ports를 유지한다.
- baseline 75 total ports를 새로 함께 제시한다.
- category count와 key signals가 v9보다 더 촘촘하다.
- `SFR_Memory_Config`는 `RF_2P_HSC`, `RA1_HS`, `RF1_HS`, `RF1_HD` family를 명시한다.
- `PRTN_Power`는 `FC2UN/UN2FC + ISO_EN[11:0]`를 유지한다.

부족:

- 정답지의 top module parameters가 없다:
  - `AXI_SLV_OUTSTANDING_READS=64`
  - `AXI_SLV_OUTSTANDING_WRITES=32`
  - `AXI_SLV_RD_RDATA_FIFO_DEPTH=512`
  - `NPU_DATA_W=512`
  - `NPU_IN_ADDR_W=56`
  - `NPU_OUT_ADDR_W=56`
- AXI 39개는 아직 full table이 아니라 key-signal summary다.
- APB register ports는 `[NumApbNodes]` array dimension이 명확하지 않다.
- EDC APB는 통합 HDD에서 5 IRQ summary만 있고, 16-port table은 `v9.1_edc.md`에 있다.
- PRTN은 `chip_no_grounding`에서도 category row 중심이라, 정답지처럼 signal별 width/direction table은 약하다.

판정:

- **통합 HDD 단독:** 약 72%
- **v9.1 folder best-of:** 약 78%

### 3.4 Module Hierarchy

v9.1 개선:

- `tt_tensix_with_l1 x12` 아래에 FPU/SFPU/TDMA뿐 아니라 Instruction Engine이 추가됐다.
- `unpack_srca`, `tt_sfpu_wrapper`, `tt_fpu_v2`, `jtag_csr_intf`, `tt_sync3`, `tt_tensix_jtag`가 들어왔다.
- Clock Infrastructure와 Overlay section도 tree에 포함됐다.
- v9에서 사라졌던 DFX/JTAG 관련 내용이 최소 수준으로 복구됐다.

부족:

- 정답지의 generate block hierarchy는 아직 없다:
  - `gen_x[0] gen_y[4]: gen_noc2axi_ne_opt`
  - `gen_x[1] gen_y[4]: gen_noc2axi_router_ne_opt`
  - `gen_x[2] gen_y[4]: gen_noc2axi_router_nw_opt`
  - `gen_dispatch_e/w`, `gen_tensix`
- NIU tile positions와 EP=4/9/14/19가 없다.
- `NOC2AXI_ROUTER_*_OPT` dual-row span과 internal router/NOC2AXI logic이 없다.
- `router_o_*`, `noc2axi_i_*`, `router_i_*`, `i_de_to_t6_*` port group mapping이 없다.
- `trinity_router` 설명이 "baseline only"라고 되어 있는데, 정답지 기준으로는 N1B0 top에서 standalone instance가 없고 internal router가 composite tile에 들어간다는 설명까지 필요하다.

판정: **v9 대비 개선. 약 55%**

### 3.5 Compute Tile - Tensix

v9.1:

- FPU/SFPU/TDMA table이 v9보다 풍부하다.
- Instruction Engine section이 생겼다.
- JTAG 관련 submodule까지 일부 들어왔다.
- `tt_idma_wrapper` L1 clock domain fact가 들어왔다.

부족:

- 정답지/확장 정답지 수준의 TRISC/BRISC, G-Tile/M-Tile, DEST/SRCA/SRCB data path는 여전히 약하다.
- L1 partition, SRAM banking, EDC sram modport 연결은 없다.
- "3 clusters total"은 `12 / TensixPerCluster=4`에서 나온 추론으로 보이며, grounded에서는 `[FROM LLM]`로 표시된다.

판정: **v9 대비 개선. 약 55%**

### 3.6 Dispatch Engine

정답지 핵심:

- East/West dispatch 위치와 EP.
- `de_to_t6_coloumn[SizeX][SizeY-1][2]`
- `de_to_t6_east/west[SizeX]`
- `t6_to_de[SizeX][SizeY-2]`
- `t6_to_de_accross_east/west[SizeX][SizeX]`
- `NOC2AXI_ROUTER_*_OPT` tiles carry feedthroughs.

v9.1:

- `tt_dispatch_top_inst_east`, `tt_dispatch_top_inst_west`만 유지한다.
- `NumDispatch=2`가 추가됐지만 구조적 개선은 작다.

부족:

- 위치 `(X=0,Y=3)`, `(X=3,Y=3)`와 EP=3/18이 없다.
- feedthrough arrays와 port mapping은 여전히 전무하다.

판정: **거의 미개선. 약 24%**

### 3.7 NoC Fabric

v9.1:

- NoC topic 문서가 v9보다 훨씬 길어졌다.
- SECDED details, CDC architecture, arbiter tree, NIU timeout, baseline `trinity_router` port list가 추가됐다.
- `NOC2AXI_ROUTER_NE/NW_OPT` tile types를 NoC 문서에서 언급한다.

부족:

- 정답지의 핵심인 manual X-axis connection과 repeater placement가 없다.
- Y=4 NOC2AXI row의 4-stage repeaters, Y=3 router row의 6-stage repeaters가 없다.
- `noc_east2west_req_repeaters_between_noc2axi`, `noc_west2east_req_repeaters_between_router` instance names가 없다.
- row별 direct/repeated connection, edge tie-off 설명이 없다.
- "Repeaters between columns"는 너무 일반적이다.

판정:

- **module inventory 기준:** 좋아짐
- **N1B0 topology 기준:** 아직 낮음
- 종합 **약 43~45%**

### 3.8 NIU / AXI Bridge Tiles

v9.1:

- `NumNoc2Axi=4`, `tt_niu_mst_timeout`, AXI bridge role을 유지한다.
- NoC topic에 N1B0 AXI bridge tile type table이 있다.

부족:

- 정답지의 corner NIU vs composite NIU+Router distinction이 약하다.
- tile position이 "Northeast" / "Northwest" 수준이고 `(X,Y)`와 EP가 없다.
- `trinity_noc2axi_router_ne/nw_opt`의 `noc2axi_i_*`, `router_i_*`, `router_o_*`, AXI in/out mapping이 없다.

판정: **v9 대비 소폭 개선. 약 55%**

### 3.9 EDC

v9.1:

- `v9.1_edc.md`에 EDC APB 16-port table이 명확히 들어왔다.
- BIU, NoC security block, serial repeater, connector hierarchy가 v9보다 정돈됐다.
- U-shape ring diagram과 direct/loopback table이 추가됐다.
- IRQ severity table이 새로 들어왔다.

부족:

- 정답지의 flat arrays가 없다:
  - `edc_ingress_intf[SizeX*SizeY]`
  - `edc_egress_intf[SizeX*SizeY]`
  - `loopback_edc_ingress_intf[SizeX*SizeY]`
  - `loopback_edc_egress_intf[SizeX*SizeY]`
- endpoint index와 EDC array index가 같다는 설명이 없다.
- `NOC2AXI_ROUTER_*_OPT`에서 Y=4 EDC interface가 없고 Y=3 index만 연결된다는 예외가 없다.
- harvest bypass는 grounded에서 일부 `[FROM LLM]`로 남는다.

판정:

- **통합 HDD 단독:** 약 62%
- **v9.1 folder best-of:** 약 70%

### 3.10 Clock and Reset

v9.1:

- clock/reset width table은 v9와 유사하게 유지된다.
- clock infra modules가 조금 더 정리됐다.
- reset active-low 설명이 추가됐다.

부족:

- `trinity_clock_routing_t` struct가 없다.
- `clock_routing_in[SizeX][SizeY]`, `clock_routing_out[SizeX][SizeY]` arrays가 없다.
- Y=4 clock entry point와 `power_good = i_edc_reset_n` 설명이 없다.
- reset packing with `getTensixIndex`가 없다.
- `NOC2AXI_ROUTER_*_OPT`의 Y=4 output unused, Y=3 `router_o_*` drive exception이 없다.
- `noc_clk` bypass observation이 없다.

판정: **v9 대비 소폭 개선. 약 48%**

### 3.11 Power Management / PRTN / ISO

v9.1:

- `ISO_EN[11:0]`, `PRTNUN` protocol, `TIEL_DFT_MODESCAN`은 유지된다.
- `chip_grounded`는 power-on sequence와 retention strategy를 `[NOT IN KB]`로 명시한다.

좋은 점:

- v9보다 grounding honesty가 좋아졌다.
- `FC2UN`/`UN2FC` signal families가 `chip_no_grounding`에 비교적 잘 나열된다.

부족:

- 정답지처럼 port별 width/direction table은 없다.
- per-column chain `external -> [x][2] -> [x][1] -> [x][0] -> output`이 없다.
- `w_left_prtnun_*[x][2]` tap detail이 없다.

판정: **약 60%**

### 3.12 Memory Config / SRAM

v9.1 개선:

- v9에서 사라졌던 SFR family 4종이 통합 HDD와 chip 문서에 복구됐다:
  - `RF_2P_HSC`
  - `RA1_HS`
  - `RF1_HS`
  - `RF1_HD`
- `chip_no_grounding`에는 각 family의 signal list가 들어 있다.
- `chip_grounded`는 total SRAM count를 `[NOT IN KB]`로 명시한다.

부족:

- 정답지의 Memory Config table처럼 "어떤 family가 TENSIX/DISPATCH/NOC2AXI 중 어디에 적용되는지"가 없다.
- primary macro `RF_2P_HSC_LVT_32X136M1FB1WM0DR0` 외 macro inventory는 약하다.
- `tt_mem_wrap_32x1024_2p_nomask` ATT SRAM 정보가 통합 HDD에 없다.

판정: **v9 대비 대폭 개선. 약 55~60%**

### 3.13 DFX

v9.1 개선:

- v9 통합 HDD에는 없던 DFX section이 복구됐다.
- `tt_tensix_jtag`, `tt_sync3`, `jtag_csr_intf`, `TIEL_DFT_MODESCAN`, `tt_fpu_gtile_SDUMP_INTF`가 들어왔다.
- `chip_grounded`는 scan chain topology와 BIST controllers를 `[NOT IN KB]`로 명시한다.

부족:

- v8에서 있었던 DFX 4-node iJTAG chain은 아직 복구되지 않았다:
  - `tt_instrn_engine_wrapper_dfx`
  - `tt_disp_eng_noc_niu_router_dfx`
  - `tt_disp_eng_l1_partition_dfx`
  - `tt_disp_eng_overlay_wrapper_dfx`
- ATT BIST / DFX SRAM relation은 약하다.
- 정답지/DFX 정답지 수준의 scan topology는 없다.

판정: **v9 대비 회복, v8 대비는 부족. 약 40~45%**

### 3.14 RTL File Reference

v9.1:

- baseline `rtl/trinity.sv`, N1B0 `used_in_n1/rtl/trinity.sv`, mem_port, legacy, `trinity_router.sv`를 포함한다.

부족:

- 정답지의 N1B0-specific files가 빠졌다:
  - `trinity_noc2axi_router_ne_opt.sv`
  - `trinity_noc2axi_router_nw_opt.sv`
  - `trinity_noc2axi_ne_opt.sv`
  - `trinity_noc2axi_nw_opt.sv`
  - `tt_tensix_with_l1`
  - `tt_dispatch_top_east/west`
  - `tt_noc_repeaters`
  - `tt_edc1_intf_connector`

판정: **v9와 유사. 약 42%**

---

## 4. v9 -> v9.1 변화 분석

| 항목 | v9 | v9.1 | 변화 |
|---|---|---|---|
| 통합 HDD 크기 | 252 lines / 8.2KB | 331 lines / 11.3KB | 증가 |
| 통합 HDD table rows | 92 | 117 | 증가 |
| `tile_t` enum | 없음 | N1B0 + baseline enum | 복구 |
| Package functions | `isEastEdge` only | `isEastEdge`, `isNorthEdge` | 개선 |
| Top ports | category summary | category + more key signals + baseline 75 ports | 개선 |
| SFR family | summary | 4 families restored | 복구 |
| Instruction Engine | 없음/약함 | submodules 포함 | 개선 |
| DFX | final HDD에 없음 | DFX/JTAG section 복구 | 개선 |
| SRAM Inventory | final HDD에 없음 | primary macro + SFR family | 개선 |
| EDC APB table | topic에 있음 | topic에 더 명확 | 개선 |
| KB Coverage Matrix | 있음 | count/coverage % 포함 | 개선 |
| GridConfig | 없음 | 없음 | 미해결 |
| Endpoint table | 없음 | 없음 | 미해결 |
| Helper functions | 없음 | 없음 | 미해결 |
| NoC repeater placement | 없음 | 없음 | 미해결 |
| Clock routing arrays | 없음 | 없음 | 미해결 |
| Dispatch feedthrough | 없음 | 없음 | 미해결 |

v9.1의 의미:

- v9.1은 v9에서 권고한 "final merge template 복구"를 일부 반영했다.
- 특히 v9에서 빠진 `tile_t`, SFR, DFX, SRAM이 최종 통합 HDD에 다시 올라온 점은 좋다.
- 그러나 v8 이후 계속 남아 있던 P0 wiring/topology gap은 해결되지 않았다.

---

## 5. 종합 점수

`N1B0_HDD_v0.1.md` 기준 Codex 보수 평가:

| 섹션 | 가중치 | v9 통합본 | v9.1 통합본 | v9.1 가중 점수 |
|---|---:|---:|---:|---:|
| Overview / N1B0 identity | 8% | 60% | 64% | 5.1 |
| Package constants / `tile_t` / endpoint | 22% | 48% | 65% | 14.3 |
| Top-level ports | 14% | 62% | 72% | 10.1 |
| Module hierarchy | 12% | 45% | 55% | 6.6 |
| NoC fabric connections | 10% | 40% | 44% | 4.4 |
| Clock/reset routing | 10% | 45% | 48% | 4.8 |
| EDC ring/interface | 8% | 58% | 62% | 5.0 |
| Dispatch feedthrough | 5% | 22% | 24% | 1.2 |
| PRTN/ISO/power | 5% | 55% | 60% | 3.0 |
| Memory config / SRAM | 3% | 35% | 58% | 1.7 |
| RTL file map / DFX / verification | 3% | 30% | 43% | 1.3 |
| **합계** | **100%** | **~48.5%** | — | **~57.5%** |

위 표는 **통합 HDD 단독 기준**이다. v9.1 전체 산출물을 best-of로 보면 다음 항목이 추가 인정된다.

| 추가 인정 항목 | 근거 파일 | 효과 |
|---|---|---:|
| EDC 16-port APB/IRQ full table | `v9.1_edc.md` | +3~4pp |
| NoC CDC/arbitration/SECDED 상세 | `v9.1_noc.md` | +2~3pp |
| Overlay APB/register signal flow | `v9.1_overlay.md` | +2pp |
| Grounding coverage matrix | `v9.1_chip_grounded.md` | +2~3pp |
| SFR family detailed signal list | `v9.1_chip_no_grounding.md` | +2~3pp |
| `[NOT IN KB]` explicit gaps | `v9.1_chip_grounded.md` | +1~2pp |

따라서 **v9.1 folder-level 품질은 약 70~72%**로 보는 것이 균형적이다.

정성 판정:

- 정답지 "핵심 좌표계" 기준: **중**
- 정답지 "top-level signal category" 기준: **상**
- 정답지 "상세 port table" 기준: **중**
- 정답지 "wiring/topology 설명" 기준: **하**
- 실사용 초안 가치: **중상**
- 그대로 정답지 대체 가능성: **아직 낮음**
- v9.1 산출물 전체의 전략적/파이프라인 가치: **상**

---

## 6. 남은 핵심 Gap

### 6.1 P0: 정답지 fidelity를 올리려면 반드시 필요한 항목

| Gap | 정답지 위치 | v9.1 상태 | 권장 source/query |
|---|---|---|---|
| `GridConfig[y][x]` tile map | Section 2.3 | 없음 | `GridConfig`, `TENSIX`, `DISPATCH_E`, `NOC2AXI_ROUTER` |
| EndpointIndex table | Section 2.4 | 없음 | `EndpointIndex`, `x * SizeY + y`, `localparam` |
| helper functions | Section 2.5 | 없음 | `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex` |
| Level-1 generate hierarchy | Section 4.1 | 없음 | `gen_x`, `gen_y`, `gen_noc2axi_router_ne_opt`, `gen_dispatch_e` |
| `NOC2AXI_ROUTER_*_OPT` dual-row wiring | Section 4.2/4.3 | enum only | `router_o_*`, `noc2axi_i_*`, `router_i_*`, `y-1` |
| NoC repeater placement | Section 5 | generic repeater only | `repeaters_between_noc2axi`, `repeaters_between_router`, `NUM_REPEATERS=4/6` |
| `clock_routing_in/out` arrays | Section 6 | 없음 | `trinity_clock_routing_t`, `clock_routing_in`, `clock_routing_out` |
| EDC flat arrays | Section 7 | 없음 | `edc_ingress_intf`, `edc_egress_intf`, `loopback_edc_ingress_intf` |
| Dispatch feedthrough | Section 8 | 없음 | `de_to_t6_coloumn`, `de_to_t6_east`, `t6_to_de` |
| PRTN internal chain taps | Section 9 | summary only | `w_left_prtnun_*[x][2]` |

### 6.2 P1: merge/reporting 보정

| Issue | 설명 | 권장 |
|---|---|---|
| 통합 HDD가 topic tables를 압축 | EDC APB full table은 `edc.md`에만 있고 통합본에는 없음 | final merge에서 critical tables preserve |
| N1B0 identity 약화 | HPDF replacement story 누락 | Overview 첫 문단에 baseline delta 강제 |
| NoC topology 일반론 과다 | "repeaters between columns"는 정답지 detail 부족 | row/instance/count 기반 table 필요 |
| Grounding matrix 오해 가능 | KB coverage 89%가 정답지 fidelity로 오해될 수 있음 | "claim coverage vs answer fidelity" 분리 표기 |
| DFX section은 복구됐지만 얕음 | v8의 4-node iJTAG chain 미복구 | DFX topic 생성 또는 v8 DFX facts 회수 |
| file map 축소 | N1B0-specific RTL files 부족 | 정답지 Section 11 file map 기준 template화 |

---

## 7. 권장 다음 단계

### 7.1 v9.2 목표: topology-required facts checklist

v9.1은 summary merge 회복에는 성공했다. 다음은 checklist 기반으로 정답지 핵심 구조물을 강제해야 한다.

필수 checklist:

- `GridConfig` 4x5 map
- EndpointIndex formula + 20-row table
- helper functions 4개
- `NOC2AXI_ROUTER_*_OPT` dual-row span
- router/noc2axi port prefix mapping
- NoC repeater summary 4 rows
- `trinity_clock_routing_t` struct
- `clock_routing_in/out` arrays
- EDC flat arrays + router exception
- dispatch feedthrough arrays
- PRTN internal chain

예상 효과:

- 통합 HDD 단독 57% → 68~72%
- folder-level 70~72% → 76~80%

### 7.2 merge 정책 개선

| 개선 | 이유 |
|---|---|
| Critical table preservation | topic 문서의 EDC/port table이 통합본에서 사라지는 문제 방지 |
| Grounded/no-grounding best-of merge | KB direct detail과 grounding tag 장점을 함께 살림 |
| Answer-template section requirements | 정답지 주요 구조물 무음 누락 방지 |
| Claim coverage와 answer fidelity 분리 | 89% self coverage와 정답지 점수 혼동 방지 |
| Regression facts suite | v8/v9.1에서 확보한 SFR/DFX/tile_t 재유실 방지 |

---

## 8. 최종 판정

v9.1은 v9보다 낫다. v9에서 가장 눈에 띄던 final merge 축약 문제를 어느 정도 복구했고, `tile_t`, SFR family, DFX/JTAG, Instruction Engine, KB Coverage Matrix가 최종 통합 HDD 또는 grounded 문서에 들어왔다. 이 점에서 v9.1은 "품질 선언 체계"였던 v9를 실제 문서 품질 회복 쪽으로 한 걸음 끌고 왔다.

하지만 아직 정답지를 대체할 수준은 아니다. 정답지의 강점은 단순 모듈/포트 목록이 아니라, `GridConfig`, EndpointIndex, generate hierarchy, NOC2AXI_ROUTER dual-row semantics, NoC repeater placement, clock routing, EDC interface arrays, dispatch feedthrough 같은 **구조적 wiring fact**에 있다. v9.1은 이 영역을 거의 건드리지 못했다.

버전 흐름으로 보면:

- **v8:** top-level port surface 대폭 복구
- **v9:** grounding/tag/통합 HDD 체계를 도입했지만 final merge가 축약됨
- **v9.1:** `tile_t`/SFR/DFX/SRAM/Instruction Engine을 복구한 merge hotfix
- **다음 목표:** topology-required facts checklist와 generate/wiring extraction

따라서 v9.1은 **통합 HDD 단독 기준 약 57%**, **v9.1 산출물 전체 best-of 기준 약 70~72%**로 평가한다. 다음 버전은 새로운 "일반 설명"을 더 넣기보다, 정답지와 1:1로 대응되는 wiring/topology fact를 강제로 채우는 쪽이 가장 효율적이다.

---

*End of Review - Codex Review v9.1*
