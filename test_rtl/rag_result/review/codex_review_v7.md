# Codex Review: RAG v7 정답지 비교 분석

**작성일:** 2026-04-28  
**리뷰어:** Codex  
**비교 대상:** `test_rtl/rag_result/v7/`  
**저장 위치:** `test_rtl/rag_result/review/codex_review_v7.md`  

---

## 0. 결론

v7은 v6c에서 이미 복구한 **package/grid anchor**를 유지하면서, v6c의 가장 큰 구조 gap 중 하나였던 **Top-Level Ports**를 꽤 크게 보강했다. 특히 `i_dm_clk[SizeX-1:0]`, `i_dm_core_reset_n[NumDmComplexes-1:0][DMCoresPerCluster-1:0]`, `i_dm_uncore_reset_n[NumDmComplexes-1:0]`, APB register ports, EDC APB ports가 새로 들어온 점은 정답지 대비 실질적인 진전이다.

또한 TDMA sub-module이 1개에서 3개로 늘었고, `RF_2P_HSC_LVT_32X136M1FB1WM0DR0` SRAM macro, DFX iJTAG chain 일부가 새로 잡혔다. v6c가 "정확한 좌표계의 compact HDD"였다면, v7은 그 골격 위에 **port/deep-module fact를 얹기 시작한 버전**이다.

다만 아직 완성 HDD는 아니다. 정답지의 핵심인 `PRTNUN_*`, `ISO_EN[11:0]`, `npu_out_*`, `npu_in_*`, `clock_routing_in/out`, `NOC2AXI_ROUTER_*_OPT` port group, dispatch feedthrough, NoC repeater placement, Memory Config SFR는 여전히 빠져 있다. 또한 v7 문서 metadata의 `Generated: 2026-05-01`은 현재 작업일인 **2026-04-28** 기준 미래 날짜이므로 생성일 메타데이터 정합성도 확인이 필요하다.

한 문장으로 요약하면:

> **v7은 v6c의 package/grid 성공을 유지한 채 top-level port와 TDMA/SRAM/DFX fact를 보강한 의미 있는 개선판이다. 그러나 PRTN/ISO, AXI, clock routing, feedthrough/topology가 남아 있어 정답지 전체 재현도는 아직 중상 단계다.**

---

## 1. 참고한 파일

### 정답지

| 파일 | 역할 |
|---|---|
| `test_rtl/Sample/N1B0_HDD_v0.1.md` | 주 비교 기준. Trinity N1B0 4x5 variant HDD |
| `test_rtl/Sample/N1B0_NPU_HDD_v0.1.md` | 보조 비교 기준. NPU 관점 확장 HDD |

### v7 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v7/v7_N1B0_HDD.md` | v7 통합 HDD. 이번 리뷰의 핵심 대상 |
| `test_rtl/rag_result/v7/v7_chip_no_grounding.md` | package/top ports/port classifier seed |
| `test_rtl/rag_result/v7/v7_chip_grounded.md` | EDC pkg, DFX, SRAM macro fact |
| `test_rtl/rag_result/v7/v7_edc.md` | EDC topic result |
| `test_rtl/rag_result/v7/v7_noc.md` | NoC topic result |
| `test_rtl/rag_result/v7/v7_overlay.md` | Overlay/SFPU/TDMA/SMN topic result |

### 비교 기준 리뷰

| 파일 | 참고 포인트 |
|---|---|
| `test_rtl/rag_result/review/codex_review_v6.md` | v6c의 성과와 남은 P0 gap |
| `test_rtl/rag_result/review/claude_review_v6.md` | v6c의 package parser 성과와 다음 단계 제안 |

---

## 2. 정량 비교

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[NOT IN KB]` |
|---|---:|---:|---:|---:|---:|---:|
| 정답지 `N1B0_HDD_v0.1.md` | 513 | 22330 | 40 | 186 | 24 | 0 |
| 정답지 `N1B0_NPU_HDD_v0.1.md` | 1290 | 58380 | 105 | 303 | 52 | 0 |
| v6c `v6c_N1B0_HDD.md` | 270 | 8018 | 21 | 92 | 4 | 0 |
| v7 `v7_N1B0_HDD.md` | 404 | 14729 | 37 | 145 | 4 | 0 |
| v7 `chip_no_grounding` | 23 | 1434 | 7 | 0 | 0 | 0 |
| v7 `chip_grounded` | 15 | 390 | 5 | 0 | 0 | 0 |
| v7 `edc` | 22 | 648 | 6 | 0 | 0 | 1 |
| v7 `noc` | 15 | 489 | 5 | 0 | 0 | 1 |
| v7 `overlay` | 21 | 629 | 6 | 0 | 0 | 1 |

해석:

- v7 통합 문서는 v6c 대비 270줄 → 404줄로 50% 가까이 커졌다.
- table rows도 92 → 145로 증가했다. 증가분 대부분은 top-level port, reset, SRAM inventory, traceability/delta table이다.
- 정답지 `N1B0_HDD_v0.1.md` 대비로는 줄 수 약 79%, table rows 약 78% 수준이다. 양적인 면에서는 이제 정답지 compact reproduction에 근접했다.
- 다만 code fences는 4개로 정답지 24개보다 훨씬 적다. 정답지의 clock routing, feedthrough, module hierarchy pseudo-code/diagram 재현은 아직 부족하다.

---

## 3. 섹션별 정답지 비교

### 3.1 Overview

정답지 핵심:

- N1B0은 baseline Trinity 변형이다.
- 핵심 변경은 `trinity_noc2axi_n_opt + trinity_router` 분리 tile pair를 `trinity_noc2axi_router_ne/nw_opt` 통합 HPDF tile로 바꾼 것이다.
- grid는 `SizeX=4`, `SizeY=5`, 20 tiles다.
- per-column AI/DM clock/reset, PRTN, ISO_EN, NoC repeater buffers가 N1B0 addition이다.

v7:

- 4x5 mesh, `SizeX=4`, `SizeY=5`, 20 tiles를 유지했다.
- tile type/count/module/position table도 v6c 수준으로 정확하다.
- `ROUTER placeholder empty by design`도 유지했다.
- 하지만 HPDF replacement story와 baseline 대비 변경점 표는 여전히 짧다.

판정: **좋음. 약 75%**

v6c 대비:

- 거의 동등하다. v7의 주요 개선은 overview가 아니라 ports/deep facts 쪽이다.

### 3.2 Package Constants and Grid

v7은 v6c에서 확보한 package parser v2 성과를 유지한다.

| 항목 | 정답지 | v7 |
|---|---|---|
| `SizeX` | 4 | 4 |
| `SizeY` | 5 | 5 |
| `NumNodes` | 20 | 20 |
| `NumTensix` | 12 | 12 |
| `NumNoc2Axi` | 4 | 4 |
| `NumDispatch` | 2 | 2 |
| `NumApbNodes` | 4 | 4 |
| `NumDmComplexes` | 14 | 14 |
| `DMCoresPerCluster` | 8 | 8 |
| `TensixPerCluster` | 4 | 4 |
| `EnableDynamicRouting` | 1 | `1'b1` |

좋은 점:

- 13 localparams 유지.
- `tile_t` 8 members 유지.
- endpoint table 20 rows 유지.
- v5.1의 `5x4 + ARC/DRAM/ETH/PCI` drift는 재발하지 않았다.

부족:

- `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex` helper functions는 아직 없다.

판정: **매우 좋음. 약 92~95%**

### 3.3 Tile Map and Endpoint Index

정답지 핵심:

- `EndpointIndex = x * SizeY + y = x*5 + y`
- 20 endpoint rows.
- `ROUTER` at `(1,3)`, `(2,3)` is placeholder.
- `NOC2AXI_ROUTER_NE/NW_OPT` spans Y=4 and Y=3.

v7:

- endpoint table과 dual EP notation `EP=9/8`, `EP=14/13`을 유지한다.
- `ROUTER placeholder [x2] — EMPTY`를 유지한다.

판정: **매우 좋음. 약 90%**

주의:

- v6c 리뷰와 동일하게, 정답지 내부에 `DISPATCH_E/W` 좌표 표기 불일치가 있다. v7은 `DISPATCH_E=(X=0,Y=3)`, `DISPATCH_W=(X=3,Y=3)`를 유지한다. 이는 `N1B0_HDD_v0.1.md`의 GridConfig/Module Hierarchy 일부와 맞지만, 일부 table과는 충돌한다.

### 3.4 Top-Level Ports

정답지 핵심:

| Port group | 정답지 내용 |
|---|---|
| Clock/reset | `i_axi_clk`, `i_noc_clk`, `i_noc_reset_n`, `i_ai_clk[SizeX-1:0]`, `i_ai_reset_n[SizeX-1:0]`, `i_tensix_reset_n[NumTensix-1:0]`, `i_edc_reset_n`, `i_dm_clk[SizeX-1:0]`, DM core/uncore resets |
| APB register | `i_reg_*[NumApbNodes]`, `o_reg_*[NumApbNodes]` |
| EDC APB + IRQ | `i_edc_apb_*[4]`, `o_edc_apb_*[4]`, `o_edc_*_irq[4]` |
| AXI | `npu_out_*[SizeX]`, `npu_in_*[SizeX]`, 512b data, 56b address |
| Memory config | `SFR_RF_2P_HSC_*`, `SFR_RA1_HS_*`, `SFR_RF1_HS_*`, `SFR_RF1_HD_*` |
| PRTN/ISO | `PRTNUN_*`, `ISO_EN[11:0]`, `TIEL_DFT_MODESCAN` |

v7 개선:

- v6c에서 빠졌던 `i_dm_clk[SizeX-1:0]`가 들어왔다.
- `i_dm_core_reset_n[NumDmComplexes-1:0][DMCoresPerCluster-1:0]`와 `i_dm_uncore_reset_n[NumDmComplexes-1:0]`가 들어왔다.
- APB register ports가 추가됐다.
- EDC APB input/output ports가 더 자세히 들어왔다.
- Port Classifier claims로 AI, Tensix, DM clock/reset grouping이 생겼다.

남은 문제:

- APB register ports가 정답지처럼 `[NumApbNodes]` array로 표현되지 않고 scalar처럼 보인다. 정답지는 `i_reg_psel[NumApbNodes]`, `i_reg_paddr[NumApbNodes]` 등이다.
- EDC APB도 정답지처럼 `[4]` array가 빠져 있다.
- EDC IRQ outputs `o_edc_fatal_err_irq[4]`, `o_edc_crit_err_irq[4]`, `o_edc_cor_err_irq[4]`, `o_edc_pkt_sent_irq[4]`, `o_edc_pkt_rcvd_irq[4]`가 top-level ports table에는 없다.
- AXI `npu_out_*`, `npu_in_*`가 없다.
- memory config SFR ports, PRTN, ISO_EN, DFT scan mode가 없다.

판정: **v6c 대비 큰 개선. 약 58~62%**

v6c 대비:

- v6c top-level ports는 약 35~40%였고, v7은 약 60%까지 올라왔다고 본다.
- 다만 array dimension과 missing port groups 때문에 아직 full signature는 아니다.

### 3.5 Module Hierarchy

v7 유지/개선:

- top-level active blocks, EP, `ROUTER` placeholder는 v6c 수준으로 유지된다.
- TDMA submodules가 `tt_tdma_thread_context` 1개에서 3개로 확장됐다.
- SRAM macro가 EDC/NoC/DFX 쪽에 연결되어 hierarchy에 들어왔다.
- DFX `tt_disp_eng_l1_partition_dfx`와 iJTAG chain relation이 추가됐다.

부족:

- 정답지의 generate block level hierarchy는 아직 없다.
- `gen_x`, `gen_y`, `gen_noc2axi_router_*`, `gen_dispatch_*`, `gen_tensix_neo` 구조가 없다.
- `NOC2AXI_ROUTER_*_OPT` 내부 Y=4/Y=3 split과 `router_o_*` mapping이 없다.
- `tt_tensix_with_l1` deep hierarchy는 아직 요약 수준이다.

판정: **상위 + 일부 deep facts 개선. 약 62~65%**

### 3.6 Compute Tile — Tensix

v7 개선:

- SFPU facts 유지: `tt_sfpu_lregs`, `tt_sfpu_instrn_resources_used`.
- TDMA가 3 submodules로 확장:
  - `tt_tdma_xy_address_controller`
  - `tt_tdma_thread_context`
  - `tt_tdma_rts_rtr_pipe_stage`
- L1: `tt_t6_l1_partition` 유지.
- FDS register facts 유지.

부족:

- FPU G-Tile/M-Tile, DEST/SRCB/SRCA data path가 없다.
- L1 bank/port detail은 `16-bank SRAM` 정도로만 나온다.
- 정답지/확장 정답지의 compute tile section과 비교하면 동작 설명, data path, verification detail이 부족하다.

판정: **v6c 대비 개선. 약 42~48%**

### 3.7 Dispatch Engine

정답지 핵심:

- East/West dispatch top 위치와 EP.
- dispatch feedthrough:
  - `de_to_t6_coloumn[SizeX][SizeY-1][2]`
  - `de_to_t6_east/west[SizeX]`
  - `t6_to_de[SizeX][SizeY-2]`
  - `t6_to_de_accross_east/west[SizeX][SizeX]`
- `NOC2AXI_ROUTER_*_OPT` tiles carry feedthroughs.
- dispatch-private L1 and internal hierarchy.

v7:

- v6c와 거의 동일하게 `tt_dispatch_top_east`, `tt_dispatch_top_west`, coordinates, EP만 있다.
- FDS dispatch register and DFX dispatch partition은 다른 섹션에 보강됐지만, 정답지의 feedthrough section은 여전히 없다.

판정: **거의 미개선. 약 22~25%**

### 3.8 NoC Fabric

v7 유지/개선:

- NoC 9 module list 유지.
- `RF_2P_HSC_LVT_32X136M1FB1WM0DR0` SRAM macro가 NoC 쪽에 추가됐다.

부족:

- Routing algorithms, flit header, AXI gasket, VC buffers, security fence, endpoint map은 `v7_noc.md`에서도 `[NOT IN KB]`.
- 정답지의 Y=3/Y=4 repeater placement, 4/6 repeater count, `noc_east2west_req_repeaters_between_*` naming이 없다.

판정: **module fact 소폭 개선, topology는 여전히 부족. 약 40~42%**

### 3.9 NIU / AXI Bridge Tiles

v7:

- 4개 NIU/bridge tile과 EP는 유지.
- ATT SRAM/BIST bridge는 유지.

부족:

- Corner vs composite 내부 차이 부족.
- `NOC2AXI_ROUTER_*_OPT` port groups 부족.
- AXI width/address, `npu_out_*`, `npu_in_*` 없음.
- EDC APB naming difference는 top-level EDC APB list가 좋아졌지만, router tile specific note는 없다.

판정: **v6c와 거의 동등. 약 50~52%**

### 3.10 Clock and Reset

v7 개선:

- `i_dm_clk[SizeX-1:0]`가 들어왔다.
- `i_dm_core_reset_n[13:0][7:0]`, `i_dm_uncore_reset_n[13:0]`가 들어왔다.
- reset table이 분리되어 가독성이 좋아졌다.
- Port Classifier mapping이 들어왔다.

부족:

- `clock_routing_in[SizeX][SizeY]`, `clock_routing_out[SizeX][SizeY]` arrays가 없다.
- Y=4 clock entry point가 없다.
- reset packing with `getTensixIndex`가 없다.
- `NOC2AXI_ROUTER_*_OPT` exception: Y=4 output unused, Y=3 driven by `router_o_*`가 없다.
- `noc_clk bypass` observation이 없다.

판정: **v6c 대비 확실히 개선. 약 65~68%**

### 3.11 EDC

v7 개선:

- `tt_edc_pkg.sv` modports 유지.
- BIU APB4 full-ish signal list가 좋아졌다.
- `tt_edc1_biu_soc_apb4_wrap`, `tt_edc1_noc_sec_block_reg`, `tt_edc1_serial_bus_repeater`, `tt_edc1_intf_connector` 유지.
- `RF_2P_HSC_LVT_32X136M1FB1WM0DR0` x2가 EDC SRAM macro로 추가됐다.

부족:

- 정답지의 EDC interface arrays `[SizeX*SizeY]`와 endpoint index relation이 없다.
- ring topology, harvest bypass, CDC는 여전히 `[NOT IN KB]`.
- Top-level EDC IRQ outputs are summarized as "5 IRQs" but not fully listed in the top-level port table.

판정: **소폭 개선. 약 72~78%**

### 3.12 SRAM Inventory

v7 개선:

- `tt_mem_wrap_32x1024_2p_nomask` 유지.
- `RF_2P_HSC_LVT_32X136M1FB1WM0DR0` SRAM macro가 추가됐다.
- EDC/NoC/DFX across-subsystem inventory로 묶었다.

정답지 대비 주의:

- 정답지 `N1B0_HDD_v0.1.md`의 Memory Config section은 SRAM macro inventory보다는 `SFR_RF_2P_HSC_*`, `SFR_RA1_HS_*`, `SFR_RF1_HS_*`, `SFR_RF1_HD_*` SFR ports 중심이다.
- 따라서 v7의 SRAM macro discovery는 가치 있지만, 정답지 section 10을 그대로 채운 것은 아니다.

판정: **v6c 대비 개선, 정답지 Memory Config와는 부분 불일치. 약 30~35%**

### 3.13 DFX

v7 개선:

- `tt_instrn_engine_wrapper_dfx` 유지.
- `tt_disp_eng_l1_partition_dfx` iJTAG chain이 추가됐다.
- `noc_niu_router_dfx → tt_disp_eng_l1_partition_dfx → dfd` chain relation이 새로 들어왔다.
- DFX SRAM macro가 추가됐다.

부족:

- 정답지/확장 정답지의 DFX hierarchy 전체와 verification 관점은 아직 부족하다.
- DFX file references and scan/iJTAG details are still summarized.

판정: **개선. 약 50~55%**

### 3.14 PRTN, ISO_EN, Power

정답지 핵심:

- `PRTNUN_FC2UN_*`
- `PRTNUN_UN2FC_*`
- 4-column daisy chain topology.
- `ISO_EN[11:0]`

v7:

- 여전히 없다.

판정: **미충족. 0%**

v6c 리뷰의 P0 권고 중 이 항목은 아직 해결되지 않았다.

### 3.15 RTL File Reference

v7:

- v6c와 동일하게 package/top/variants/router placeholder/EDC package variants가 있다.

부족:

- `trinity_noc2axi_router_ne_opt.sv`, `trinity_noc2axi_router_nw_opt.sv`, `trinity_noc2axi_ne_opt.sv`, `trinity_noc2axi_nw_opt.sv` 등 정답지 file map의 주요 entries가 아직 full로 없다.
- dispatch/tensix/NoC/clock/DFX files도 부족하다.

판정: **v6c와 거의 동등. 약 48~50%**

---

## 4. v6c → v7 변화 분석

| 항목 | v6c | v7 | 변화 |
|---|---|---|---|
| 문서 크기 | 270 lines / 8.0KB | 404 lines / 14.7KB | 크게 증가 |
| Package/grid | 정확 | 정확 유지 | 유지 |
| Top ports | clock/reset 일부 | DM clock/reset + APB + EDC APB 확장 | 대폭 개선 |
| Port classifier | 없음 | AI/Tensix/DM clock-reset claims | 개선 |
| TDMA | `tt_tdma_thread_context` 중심 | 3 submodules | 개선 |
| SRAM | ATT SRAM 중심 | RF_2P macro 추가 | 개선 |
| DFX | 3개 모듈 수준 | iJTAG chain relation 추가 | 개선 |
| NoC topology | 부족 | 여전히 부족 | 미해결 |
| Dispatch feedthrough | 부족 | 여전히 부족 | 미해결 |
| PRTN/ISO | 없음 | 없음 | 미해결 |
| AXI `npu_in/out` | 없음 | 없음 | 미해결 |
| Generated date | 2026-04-28 | 2026-05-01 | 메타데이터 확인 필요 |

v7의 의미:

- v6c는 package parser v2의 승리였다.
- v7은 port classifier + MCP 800char expansion의 효과가 나타난 버전이다.
- 특히 v6c 리뷰에서 P0로 지적했던 "Full top-level port extraction" 중 clock/reset/APB/EDC APB 일부가 실제로 개선됐다.
- 하지만 P0 중 `PRTN/ISO`, `NOC2AXI_ROUTER_*_OPT port groups`, `dispatch feedthrough`는 아직 남아 있다.

---

## 5. 종합 점수

`N1B0_HDD_v0.1.md` 기준 Codex 보수 평가:

| 섹션 | 가중치 | v6c 충족도 | v7 충족도 | v7 가중 점수 |
|---|---:|---:|---:|---:|
| Overview / N1B0 identity | 8% | 75% | 75% | 6.0 |
| Package constants / `tile_t` / endpoint | 22% | 92% | 94% | 20.7 |
| Top-level ports | 14% | 38% | 60% | 8.4 |
| Module hierarchy | 12% | 58% | 64% | 7.7 |
| NoC fabric connections | 10% | 38% | 41% | 4.1 |
| Clock/reset routing | 10% | 58% | 67% | 6.7 |
| EDC ring/interface | 8% | 70% | 75% | 6.0 |
| Dispatch feedthrough | 5% | 22% | 24% | 1.2 |
| PRTN/ISO/power | 5% | 0% | 0% | 0.0 |
| Memory config / SRAM | 3% | 12% | 32% | 1.0 |
| RTL file map / verification | 3% | 48% | 50% | 1.5 |
| **합계** | **100%** | **~56.6%** | — | **~63.3%** |

정성 판정:

- 정답지 "핵심 좌표계" 기준: **상**
- 정답지 "top-level signal 재현" 기준: **중상**
- 정답지 "동작/토폴로지 설명" 기준: **중하**
- 실사용 초안 가치: **높음**
- 그대로 정답지 대체 가능성: **아직 낮음~중간**

---

## 6. 남은 핵심 Gap

### 6.1 P0: 아직 반드시 보강해야 할 것

| Gap | 정답지 위치 | 현재 v7 상태 | 권장 query/source |
|---|---|---|---|
| PRTN chain | Section 3.2, 9, 13 | 없음 | `PRTNUN_FC2UN`, `PRTNUN_UN2FC`, `w_left_prtnun` |
| `ISO_EN[11:0]` | Section 3.2, 13 | 없음 | `ISO_EN`, `isolation enable` |
| AXI `npu_out_*`, `npu_in_*` | Section 3.2 | 없음 | `npu_out_aw`, `npu_in_ar`, `NPU_DATA_W`, `NPU_IN_ADDR_W`, `NPU_OUT_ADDR_W` |
| `clock_routing_in/out` | Section 6 | 없음 | `clock_routing_in`, `clock_routing_out`, `router_o_ai_clk` |
| Dispatch feedthrough | Section 8 | 없음 | `de_to_t6_coloumn`, `de_to_t6_east`, `t6_to_de`, `t6_to_de_accross` |
| NoC repeater placement | Section 5 | 없음 | `repeaters_between_noc2axi`, `repeaters_between_router` |
| EDC IRQ outputs in top port table | Section 3.2 | partial only | `o_edc_fatal_err_irq`, `o_edc_pkt_rcvd_irq` |

### 6.2 P1: 정확도 보정

| Issue | 설명 | 권장 |
|---|---|---|
| APB arrays | v7은 scalar처럼 표기. 정답지는 `[NumApbNodes]` arrays | port classifier에서 dimension preservation 강화 |
| EDC APB arrays | v7은 scalar처럼 표기. 정답지는 `[4]` arrays | EDC APB group dimension extraction |
| Generated date | v7 document says `Generated: 2026-05-01`, but current work date is 2026-04-28 | generation metadata source 확인 |
| Dispatch E/W coordinate canonicalization | 정답지 내부 표기 충돌 존재 | canonical source rule 명시 |
| SFR vs SRAM | v7의 SRAM macro inventory와 정답지 Memory Config SFR가 다른 layer | 별도 `Memory Config SFR Ports` section 추가 |

---

## 7. 권장 다음 단계

### 7.1 v8 후보: `trinity.sv` structure pass

v7까지는 package + port가 좋아졌다. 다음 가장 큰 점수 상승은 `trinity.sv` 내부 wiring/generate pass다.

필수 extraction 대상:

- `clock_routing_in[SizeX][SizeY]`
- `clock_routing_out[SizeX][SizeY]`
- `gen_noc2axi_router_ne_opt`, `gen_noc2axi_router_nw_opt`
- `router_o_*`, `noc2axi_i_*`
- `de_to_t6_*`, `t6_to_de_*`
- `PRTNUN_*`, `ISO_EN`
- `npu_out_*`, `npu_in_*`

예상 효과:

- Top-level ports 60% → 80%+
- Clock/reset routing 67% → 85%+
- Dispatch feedthrough 24% → 60%+
- PRTN/ISO 0% → 70%+
- 전체 점수 63% → 72~78% 가능

### 7.2 Retrieval/reporting 개선

| 개선 | 이유 |
|---|---|
| Missing required facts checklist를 v7 output 끝에 자동 생성 | PRTN/ISO 같은 무음 누락 방지 |
| array dimension preservation | APB/EDC APB가 scalar처럼 보이는 문제 방지 |
| source trace line or file anchor 추가 | generated fact 검증성 강화 |
| metadata date validation | 미래 날짜/잘못된 생성일 방지 |
| SFR와 SRAM macro를 별도 category로 분리 | 정답지 Memory Config section과 macro inventory 혼동 방지 |

---

## 8. 최종 판정

v7은 v6c 대비 명확한 개선이다. v6c가 package/grid anchor를 복구했다면, v7은 그 위에 port classifier와 800-char expanded retrieval을 통해 top-level port 사실을 상당히 보강했다. 특히 `i_dm_clk`, DM core/uncore reset, APB register, EDC APB는 정답지에서 실제로 중요했던 항목이라 단순한 분량 증가가 아니라 구조적 품질 개선이다.

하지만 v7은 아직 "signal list가 풍부해진 compact HDD"에 가깝다. 정답지의 진짜 고밀도 부분인 routing/wiring/topology, PRTN chain, dispatch feedthrough, AXI interface, memory config SFR가 남아 있다.

버전 흐름으로 보면:

- **v6c:** package/grid anchor 복구
- **v7:** top-level port and deep fact 확장
- **다음 목표:** `trinity.sv` generate/wiring pass로 PRTN, AXI, clock routing, feedthrough, NoC repeater placement를 채우기

따라서 v7은 **정답지 재현도 약 63% 수준의 유의미한 진전**으로 평가한다. 다음 개선은 더 많은 일반 검색보다, `trinity.sv` 내부 구조를 겨냥한 targeted parser/search가 가장 효과적이다.

---

*End of Review — Codex Review v7*
