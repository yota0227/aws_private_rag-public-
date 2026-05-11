# Codex Review: RAG v6c 정답지 비교 분석

**작성일:** 2026-04-28  
**리뷰어:** Codex  
**비교 대상:** `test_rtl/rag_result/v6c/`  
**저장 위치:** `test_rtl/rag_result/review/codex_review_v6.md`  

---

## 0. 결론

v6c는 v5.1에서 가장 크게 틀어졌던 **N1B0의 기본 좌표계**를 성공적으로 복구했다. `SizeX=4`, `SizeY=5`, `NumTensix=12`, `NumNoc2Axi=4`, `NumDispatch=2`, `NumApbNodes=4`, `tile_t` 8종, `EndpointIndex=x*5+y` 전체 20개 표가 살아났다. 이건 작은 개선이 아니라, 정답지 재현 관점에서 버전의 성격이 바뀐 수준의 개선이다.

다만 v6c는 아직 "완성 HDD"라기보다 **정답지의 package/grid 골격을 정확히 잡은 compact HDD**에 가깝다. 정답지 `N1B0_HDD_v0.1.md`의 513줄 대비 v6c 통합 문서 `v6c_N1B0_HDD.md`는 270줄이고, Top-Level Ports, NoC fabric connection, clock propagation, EDC ring detail, dispatch feedthrough, PRTN daisy chain, memory config SFR가 여전히 얇거나 빠져 있다.

한 문장으로 요약하면:

> **v6c는 v5.1의 factual drift를 package parser v2로 크게 잡았고, 정답지 핵심 좌표계는 거의 복구했다. 남은 과제는 `trinity.sv` full port/generate-level 구조와 spec성 동작 설명을 채우는 것이다.**

---

## 1. 참고한 파일

### 정답지

| 파일 | 역할 |
|---|---|
| `test_rtl/Sample/N1B0_HDD_v0.1.md` | 주 비교 기준. Trinity N1B0 4x5 variant HDD |
| `test_rtl/Sample/N1B0_NPU_HDD_v0.1.md` | 보조 비교 기준. NPU 관점 확장 HDD |

### v6c 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v6c/v6c_N1B0_HDD.md` | v6c 통합 HDD. 이번 리뷰의 핵심 대상 |
| `test_rtl/rag_result/v6c/v6c_chip_no_grounding.md` | package/grid/top module seed |
| `test_rtl/rag_result/v6c/v6c_chip_grounded.md` | KB-only chip fact 목록 |
| `test_rtl/rag_result/v6c/v6c_edc.md` | EDC topic result |
| `test_rtl/rag_result/v6c/v6c_noc.md` | NoC topic result |
| `test_rtl/rag_result/v6c/v6c_overlay.md` | Overlay/SFPU/TDMA/SMN topic result |

### 참고 리뷰

| 파일 | 참고 포인트 |
|---|---|
| `test_rtl/rag_result/review/codex_review_v5.1.md` | v5.1의 factual drift와 개선 필요점 |
| `test_rtl/rag_result/review/kiro_review_v6c.md` | v6c의 package parser 개선 평가 |

---

## 2. 정량 비교

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[NOT IN KB]` |
|---|---:|---:|---:|---:|---:|---:|
| 정답지 `N1B0_HDD_v0.1.md` | 513 | 22330 | 40 | 186 | 24 | 0 |
| 정답지 `N1B0_NPU_HDD_v0.1.md` | 1290 | 58380 | 105 | 303 | 52 | 0 |
| v6c `v6c_N1B0_HDD.md` | 270 | 8018 | 21 | 92 | 4 | 0 |
| v6c `chip_no_grounding` | 40 | 1510 | 9 | 0 | 0 | 0 |
| v6c `chip_grounded` | 22 | 799 | 3 | 9 | 0 | 2 |
| v6c `edc` | 22 | 769 | 4 | 6 | 0 | 1 |
| v6c `noc` | 27 | 902 | 4 | 11 | 0 | 1 |
| v6c `overlay` | 40 | 1082 | 8 | 5 | 0 | 1 |

해석:

- v6c 통합 문서는 정답지 `N1B0_HDD_v0.1.md` 대비 줄 수 약 53%, table rows 약 49%다.
- v5.1 `chip_no_grounding`은 494줄로 길었지만 factual drift가 컸다. 반대로 v6c는 270줄로 짧아졌지만 핵심 package/grid 정확도가 크게 좋아졌다.
- v6c의 topic별 보조 파일은 매우 짧다. 따라서 subsystem detail은 통합 문서에서도 compact summary 수준에 머문다.

---

## 3. 섹션별 정답지 비교

### 3.1 Overview

정답지 핵심:

- N1B0은 baseline Trinity 변형이다.
- 핵심 변경은 `trinity_noc2axi_n_opt + trinity_router` 분리 tile pair를 `trinity_noc2axi_router_ne/nw_opt` 통합 HPDF tile로 바꾼 것이다.
- grid는 `SizeX=4`, `SizeY=5`, 20 tiles다.
- per-column AI/DM clock/reset, PRTN, ISO_EN, NoC repeaters가 N1B0 addition이다.

v6c:

- `trinity` top module이 4x5 mesh를 구현한다고 정확히 적었다.
- tile type/count/module/position table이 정답지와 매우 가깝다.
- `ROUTER placeholder empty by design`도 잡았다.
- 다만 HPDF replacement story, baseline 대비 변경점 요약은 짧다.

판정: **좋음. 약 75%**

남은 gap:

- `trinity_noc2axi_n_opt + trinity_router` → `trinity_noc2axi_router_ne/nw_opt` 변경의 설계 의도가 더 명시되어야 한다.
- PRTN, ISO_EN, NoC repeater buffers 같은 N1B0 addition이 overview에는 충분히 반영되지 않았다.

### 3.2 Package Constants and Grid

정답지 핵심:

| Constant | 정답지 |
|---|---:|
| `SizeX` | 4 |
| `SizeY` | 5 |
| `NumNodes` | 20 |
| `NumTensix` | 12 |
| `NumNoc2Axi` | 4 |
| `NumDispatch` | 2 |
| `NumApbNodes` | 4 |
| `NumDmComplexes` | 14 |
| `DMCoresPerCluster` | 8 |
| `TensixPerCluster` | 4 |
| `EnableDynamicRouting` | 1 |

v6c:

- 13개 localparam을 추출했다.
- 정답지의 핵심 constants를 거의 모두 맞췄다.
- `NumAxes=2`, `NumDirections=2`, NoC enum도 추가로 잡았다.
- `tile_t` 8 members와 endpoint table 20행이 모두 있다.
- v5.1의 `GridSizeX=5`, `GridSizeY=4`, ARC/DRAM/ETH/PCI drift가 사라졌다.

판정: **v6c 최대 성과. 약 90~95%**

주의점:

- 정답지의 `EnableDynamicRouting` 표기는 `1`, v6c는 `1'b1`이다. 의미상 동일하므로 문제 없음.
- helper functions `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex`는 v6c에 없다. package section 완성도를 더 올리려면 추가해야 한다.

### 3.3 Tile Map and Endpoint Index

정답지 핵심:

- `EndpointIndex = x * SizeY + y = x*5 + y`
- 20개 endpoint table
- `ROUTER` at `(1,3)`, `(2,3)`는 placeholder이며 standalone `trinity_router`가 instantiated되지 않는다.
- `NOC2AXI_ROUTER_NE/NW_OPT`는 Y=4에서 generate되지만 내부적으로 Y=4 NOC2AXI와 Y=3 router 역할을 함께 담당한다.

v6c:

- endpoint table 20행을 완성했다.
- `NOC2AXI_ROUTER_NE_OPT` EP=9/8, `NOC2AXI_ROUTER_NW_OPT` EP=14/13 표현이 들어갔다.
- `ROUTER placeholder [x2] — EMPTY`를 명시했다.

판정: **매우 좋음. 약 90%**

주의점:

- 정답지 내부에 `DISPATCH_E/W` 좌표 표기가 일부 섹션에서 서로 충돌한다. v6c는 `DISPATCH_E=(X=0,Y=3)`, `DISPATCH_W=(X=3,Y=3)`로 적었고, 이는 `N1B0_HDD_v0.1.md`의 GridConfig/Module Hierarchy 일부와 일치한다. 다만 `N1B0_NPU_HDD_v0.1.md`와 `N1B0_HDD_v0.1.md`의 일부 table은 E/W를 반대로 적는다.
- 따라서 v6c의 Dispatch E/W 좌표는 단순 오답으로 보기보다, 정답지 내부 불일치에 대한 reconciliation 대상이다. 다음 버전에서는 source line 기준으로 어느 표기를 canonical로 삼을지 정해야 한다.

### 3.4 Top-Level Ports

정답지 핵심:

| Port group | 정답지 내용 |
|---|---|
| Clock/reset | `i_axi_clk`, `i_noc_clk`, `i_noc_reset_n`, `i_ai_clk[SizeX-1:0]`, `i_ai_reset_n[SizeX-1:0]`, `i_tensix_reset_n[NumTensix-1:0]`, `i_edc_reset_n`, `i_dm_clk[SizeX-1:0]`, DM core/uncore resets |
| APB register | `i_reg_*[NumApbNodes]`, `o_reg_*[NumApbNodes]` |
| EDC APB + IRQ | `i_edc_apb_*[4]`, `o_edc_*_irq[4]` |
| AXI | `npu_out_*[SizeX]`, `npu_in_*[SizeX]`, 512b data, 56b address |
| Memory config | `SFR_RF_2P_HSC_*`, `SFR_RA1_HS_*`, `SFR_RF1_HS_*`, `SFR_RF1_HD_*` |
| PRTN/ISO | `PRTNUN_*`, `ISO_EN[11:0]`, `TIEL_DFT_MODESCAN` |

v6c:

- clock/reset 핵심 일부를 잡았다.
- `i_ai_clk[SizeX-1:0]`, `i_ai_reset_n[SizeX-1:0]`, `i_tensix_reset_n[NumTensix-1:0]`, `i_edc_apb_*`가 들어갔다.
- 하지만 `i_dm_clk[SizeX-1:0]`, DM core/uncore reset, APB register arrays, full EDC APB signals/IRQs, AXI in/out, SFR memory config, PRTN, ISO_EN, DFT scan mode가 빠졌다.

판정: **부분 개선. 약 35~40%**

핵심 gap:

- `trinity.sv` port truncation이 아직 해결되지 않은 것으로 보인다.
- v6c가 package constants는 잘 가져왔지만, top module의 full signature는 아직 충분히 복원하지 못했다.

### 3.5 Module Hierarchy

정답지 핵심:

```text
trinity
├── gen_x[0] gen_y[4] trinity_noc2axi_ne_opt EP=4
├── gen_x[1] gen_y[4] trinity_noc2axi_router_ne_opt EP=9/8
├── gen_x[2] gen_y[4] trinity_noc2axi_router_nw_opt EP=14/13
├── gen_x[3] gen_y[4] trinity_noc2axi_nw_opt EP=19
├── gen_x[0] gen_y[3] tt_dispatch_top_east EP=3
├── gen_x[3] gen_y[3] tt_dispatch_top_west EP=18
└── gen_x[0..3] gen_y[0..2] tt_tensix_with_l1
```

v6c:

- top-level active blocks는 잘 잡았다.
- EP도 대부분 붙었다.
- `NOC2AXI_ROUTER_*_OPT`의 dual EP 표현도 좋다.
- EDC, NoC, Clock, SMN module list가 통합되어 있다.

부족:

- 정답지의 generate block level hierarchy가 없다.
- `NOC2AXI_ROUTER_*_OPT` 내부 port group, Y=4/Y=3 split, `router_o_*` clock/reset propagation이 없다.
- Tensix deep hierarchy는 SFPU/TDMA/L1/FDS 일부만 짧게 들어갔다.

판정: **상위 hierarchy는 좋음, deep/generate hierarchy는 부족. 약 55~60%**

### 3.6 Compute Tile — Tensix

정답지 및 보조 정답지 핵심:

- `tt_tensix_with_l1` x12
- FPU, SFPU, TDMA, L1, DEST/SRCB/SRCA register files
- `tt_t6_l1_partition`
- dispatch/private L1 and DFX-related components

v6c:

- `tt_sfpu_lregs`
- `tt_sfpu_instrn_resources_used`
- `tt_tdma_thread_context`
- `tt_t6_l1_partition`
- FDS register blocks

판정: **module fact는 개선, HDD detail은 부족. 약 30~40%**

좋은 점:

- v5.1보다 generic hallucination이 줄고 실제 module fact 중심이다.
- SFPU/TDMA/SMN topic search의 효과가 보인다.

부족:

- FPU G-Tile/M-Tile, DEST/SRCB/SRCA data path, L1 bank/port 구조, verification detail이 부족하다.

### 3.7 Dispatch Engine

정답지 핵심:

- East/West dispatch top 위치와 EP
- dispatch feedthrough: `de_to_t6_coloumn`, `de_to_t6_east/west`, `t6_to_de`, `t6_to_de_accross_east/west`
- `NOC2AXI_ROUTER_*_OPT` tiles also carry dispatch feedthroughs
- dispatch-private L1 and internal hierarchy

v6c:

- `tt_dispatch_top_east`, `tt_dispatch_top_west`, coordinates, EP만 있다.
- internal command path와 feedthrough가 없다.

판정: **상위 위치만 충족. 약 20~25%**

### 3.8 NoC Fabric

정답지 핵심:

- Y-axis north/south connections
- X-axis manual connections
- Row Y=4 NOC2AXI repeaters: 4 repeaters between X=1 and X=2
- Row Y=3 Router repeaters: 6 repeaters between X=1 and X=2
- repeater names and direction table

v6c:

- `tt_noc_repeaters_cardinal`, `noc_arbiter_tree`, `tt_noc_secded_chk_corr_116_10`, `tt_upf_async_fifo`, `tt_noc_sync3_pulse`, `tt_skid_buffer_new_assertion_off`, `tt_harvest_robust_sync`, `tt_niu_mst_timeout` 등 module fact가 좋다.
- `EnableDynamicRouting=1`, `NumAxes=2`, `NumDirections=2`도 들어갔다.
- 하지만 routing algorithms, flit header, AXI gasket, VC buffers, endpoint map, repeater placement가 `v6c_noc.md`에서 `[NOT IN KB]`로 남았다.

판정: **module fact는 좋고 topology는 부족. 약 35~40%**

### 3.9 NIU / AXI Bridge Tiles

정답지 핵심:

- corner NIU vs composite NIU+Router 구분
- `trinity_noc2axi_ne_opt`, `trinity_noc2axi_nw_opt`
- `trinity_noc2axi_router_ne_opt`, `trinity_noc2axi_router_nw_opt`
- AXI master output to DRAM, EDC APB naming differences, router port groups

v6c:

- 4개 NIU/bridge tile과 EP를 정확히 잡았다.
- `noc2axi_router_nw_opt + tt_mem_wrap_32x1024_2p_nomask + selftest`도 잡았다.
- 하지만 corner vs composite 내부 차이, port groups, AXI width/address, EDC APB naming difference가 없다.

판정: **tile identity는 좋음, interface detail은 부족. 약 50%**

### 3.10 Clock and Reset

정답지 핵심:

- `trinity_clock_routing_t` fields
- `clock_routing_in[SizeX][SizeY]`, `clock_routing_out[SizeX][SizeY]`
- clock entry at Y=4
- per-column `i_ai_clk[x]`, `i_dm_clk[x]`
- `NOC2AXI_ROUTER_*_OPT` exception: Y=4 output not exposed, drives Y=3 via `router_o_*`
- reset packing with `getTensixIndex`

v6c:

- `trinity_clock_routing_t` 8 fields를 잡았다.
- `i_noc_reset_n`, `i_ai_reset_n[3:0]`, `i_tensix_reset_n[11:0]`, `i_edc_reset_n`를 잡았다.
- `tt_clkdiv2`, `tt_clkbuf`, `tt_clkgater`, `tt_smn_clkdiv` module fact가 있다.

부족:

- `i_dm_clk[SizeX-1:0]`가 top ports에 빠졌다.
- `clock_routing_in/out` array structure와 Y=4 entry point가 없다.
- router tile clock propagation exception이 없다.
- DM core/uncore reset detail이 없다.

판정: **clock struct는 크게 개선, routing behavior는 부족. 약 55~60%**

### 3.11 EDC

정답지 핵심:

- EDC interface arrays indexed by `x*SizeY+y`
- direct/loopback connector nodes
- NOC2AXI_ROUTER tiles의 EDC APB routing
- EDC ring concept

v6c:

- `tt_edc_pkg.sv` modports: ingress/egress/edc_node/sram
- `req_tgl`, `ack_tgl`
- `tt_edc1_biu_soc_apb4_wrap`, `tt_edc1_noc_sec_block_reg`, `tt_edc1_serial_bus_repeater`, `tt_edc1_intf_connector`
- APB4 + 5 IRQs

부족:

- EDC flat arrays `[SizeX*SizeY]`와 endpoint index relation은 없다.
- ring topology, harvest bypass, CDC는 `v6c_edc.md`에서 `[NOT IN KB]`.
- APB port names/widths are summarized, not full.

판정: **module/interface facts는 좋음, topology는 부족. 약 65~75%**

### 3.12 PRTN Daisy Chain and ISO_EN

정답지 핵심:

- PRTN is N1B0 addition.
- `PRTNUN_FC2UN_*` input/output and `PRTNUN_UN2FC_*` signals.
- 4-column daisy chain topology.
- `ISO_EN[11:0]` isolation enable.

v6c:

- PRTN과 ISO_EN이 통합 문서에 없다.
- `v6c_chip_grounded.md`에서도 Power management가 `[NOT IN KB]`로 남았다.

판정: **미충족. 0%**

이 부분은 v6c의 가장 중요한 남은 gap 중 하나다.

### 3.13 Memory Config and SRAM Inventory

정답지 핵심:

- Memory Config SFR ports: `SFR_RF_2P_HSC_*`, `SFR_RA1_HS_*`, `SFR_RF1_HS_*`, `SFR_RF1_HD_*`
- SFR groups are used by TENSIX, DISPATCH, NOC2AXI, dispatch only cases.

v6c:

- `tt_mem_wrap_32x1024_2p_nomask` ATT SRAM만 있다.
- L1/SFR/VC/other SRAM inventory는 없다.

판정: **ATT SRAM만 충족. 약 10~15%**

### 3.14 RTL File Reference

정답지 핵심:

- `used_in_n1/rtl/targets/4x5/trinity_pkg.sv`
- `used_in_n1/rtl/trinity.sv`
- `trinity_noc2axi_router_ne_opt.sv`
- `trinity_noc2axi_router_nw_opt.sv`
- `trinity_noc2axi_ne_opt.sv`
- `trinity_noc2axi_nw_opt.sv`
- `tt_dispatch_top_east/west`, `tt_tensix_with_l1`, EDC package files

v6c:

- package and top files are present.
- mem_port/legacy variants and `tt_edc_pkg.sv` variants are present.
- specific `trinity_noc2axi_router_*` source files are not fully listed.

판정: **부분 충족. 약 45~50%**

---

## 4. v5.1 → v6c 변화

| 항목 | v5.1 | v6c | 변화 |
|---|---|---|---|
| Grid | `GridSizeX=5`, `GridSizeY=4`, ARC/DRAM/ETH/PCI drift | `SizeX=4`, `SizeY=5`, NOC2AXI/DISPATCH/TENSIX grid | 대폭 개선 |
| Package constants | 사실상 실패 또는 `[NOT IN KB]` | 13 localparams | 대폭 개선 |
| `tile_t` enum | 없음 | 8 members | 대폭 개선 |
| Endpoint table | 없음 | 20 rows | 대폭 개선 |
| `ROUTER` placeholder | 일부 언급 | EP 8/13 empty로 명확 | 개선 |
| Top ports | generic 또는 `[NOT IN KB]` | 주요 clock/reset + EDC APB 일부 | 개선이나 아직 부족 |
| NoC | module fact 중심 | module fact 유지 + package NoC enum | 소폭 개선 |
| EDC | modport/module fact | 유지 | 동등~소폭 개선 |
| PRTN/ISO | 누락 | 누락 | 미해결 |
| 문서 길이 | 길지만 drift 큼 | 짧지만 정확한 anchor | 방향 전환 |

v6c의 의미:

- v5.1은 "형태는 좋지만 anchor가 약한 버전"이었다.
- v6c는 "anchor는 좋아졌지만 detail이 아직 얇은 버전"이다.
- 따라서 v6c는 v5.1보다 정답지 재현 pipeline으로서 훨씬 건강한 방향이다.

---

## 5. 종합 점수

`N1B0_HDD_v0.1.md`를 기준으로 한 Codex 보수 평가:

| 섹션 | 가중치 | v6c 충족도 | 가중 점수 |
|---|---:|---:|---:|
| Overview / N1B0 identity | 8% | 75% | 6.0 |
| Package constants / `tile_t` / endpoint | 22% | 92% | 20.2 |
| Top-level ports | 14% | 38% | 5.3 |
| Module hierarchy | 12% | 58% | 7.0 |
| NoC fabric connections | 10% | 38% | 3.8 |
| Clock/reset routing | 10% | 58% | 5.8 |
| EDC ring/interface | 8% | 70% | 5.6 |
| Dispatch feedthrough | 5% | 22% | 1.1 |
| PRTN/ISO/power | 5% | 0% | 0.0 |
| Memory config / SRAM | 3% | 12% | 0.4 |
| RTL file map / verification | 3% | 48% | 1.4 |
| **합계** | **100%** | — | **~56.6%** |

정성 판정:

- 정답지 "핵심 좌표계" 기준: **상**
- 정답지 "완성 HDD 전체 재현" 기준: **중**
- 실사용 초안 가치: **높음**
- 그대로 정답지 대체 가능성: **아직 낮음**

---

## 6. 개선 권장사항

### 6.1 P0: 다음 버전에서 반드시 보강

| 항목 | 이유 | 권장 query/source |
|---|---|---|
| Full top-level port extraction | v6c 최대 남은 구조 gap | `trinity.sv module trinity ports`, `i_dm_clk`, `npu_out`, `npu_in`, `PRTNUN`, `ISO_EN` |
| PRTN / ISO_EN | 정답지 핵심 N1B0 addition인데 v6c 0% | `PRTNUN_FC2UN`, `PRTNUN_UN2FC`, `ISO_EN` |
| `clock_routing_in/out` arrays | clock struct는 잡았지만 propagation이 없음 | `trinity_clock_routing_t clock_routing_in clock_routing_out` |
| `NOC2AXI_ROUTER_*_OPT` port groups | dual-row HPDF tile 설명의 핵심 | `router_o_ai_clk`, `noc2axi_i_flit`, `router_i_flit`, `i_de_to_t6` |
| Dispatch feedthrough | 정답지 section 8이 거의 빠짐 | `de_to_t6_coloumn`, `t6_to_de`, `de_to_t6_east`, `de_to_t6_west` |

### 6.2 P1: HDD 품질 개선

| 항목 | 기대 효과 |
|---|---|
| Helper functions extraction: `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex` | package section을 정답지 100%에 가깝게 보강 |
| NoC repeater placement query | 정답지 NoC Fabric Connections 재현 |
| Memory Config SFR query | SFR section 공백 해소 |
| RTL File Map expansion | `trinity_noc2axi_router_*`, dispatch, tensix files 명시 |
| Dispatch E/W coordinate reconciliation | 정답지 내부 불일치에 대한 canonical rule 확보 |

### 6.3 P2: Spec-level detail

| 항목 | 이유 |
|---|---|
| FPU/SFPU/TDMA/L1 detailed behavior | RTL claim만으로는 compute tile HDD가 얇음 |
| NoC algorithm/flit/VC/security fence | `v6c_noc.md`에 `[NOT IN KB]`로 남음 |
| EDC ring topology/harvest bypass/CDC | `v6c_edc.md`에 `[NOT IN KB]`로 남음 |
| Verification checklist | 정답지/확장 정답지 수준의 사용 가능 HDD로 가려면 필요 |

---

## 7. 최종 판정

v6c는 v5.1 대비 명확한 진전이다. 특히 package parser v2 효과로 정답지의 가장 중요한 기반인 `trinity_pkg.sv` 정보가 살아났다. 이 덕분에 이전 버전의 가장 위험한 오류였던 `5x4 grid + ARC/DRAM/ETH/PCI` drift가 제거됐다.

하지만 아직 정답지 전체를 재현했다고 보기는 어렵다. v6c는 package/grid/endpoint 중심으로 강하고, `trinity.sv` full port와 generate-level wiring, PRTN/ISO, dispatch feedthrough, NoC repeater topology, memory config SFR 쪽이 약하다.

버전 흐름으로 보면:

- **v5.1:** 길고 보기 좋지만 정답지 anchor가 약해 factual drift가 큼
- **v6c:** 짧아졌지만 정답지 anchor가 강해짐
- **다음 목표:** v6c의 정확한 package/grid anchor 위에 `trinity.sv` full ports and wiring을 얹기

따라서 다음 개발 방향은 "더 길게 생성"이 아니라 **v6c의 정확한 골격을 유지한 채, missing structural facts를 targeted search로 채우는 것**이 맞다.

---

*End of Review — Codex Review v6*
