# Codex Review: RAG v8 정답지 비교 분석

**작성일:** 2026-04-29  
**리뷰어:** Codex  
**비교 대상:** `test_rtl/rag_result/v8/`  
**저장 위치:** `test_rtl/rag_result/review/codex_review_v8.md`  

---

## 0. 결론

v8은 v7에서 남아 있던 가장 큰 P0 gap 중 다수를 실제로 해결했다. 특히 `PRTNUN_*`, `ISO_EN[11:0]`, `npu_out_*`/`npu_in_*`, SFR memory config ports, EDC IRQ outputs가 새로 들어오면서, 정답지 `N1B0_HDD_v0.1.md`의 Top-Level Ports, Power Management, Memory Config 쪽 재현도가 크게 올라갔다.

v7이 "package/grid anchor + port/deep-module fact 확장"이었다면, v8은 **max_results=50 retrieval로 top-level port surface를 거의 전면 복구한 버전**이다. v7에서 0%였던 PRTN/ISO와 AXI/SFR port group이 v8에서 한 번에 살아났기 때문에, 개선 폭은 작지 않다.

다만 v8도 아직 정답지 전체를 대체할 수준은 아니다. 남은 핵심 gap은 이제 단순 port 목록보다는 `trinity.sv` 내부 generate/wiring 구조다. 즉 `clock_routing_in/out`, `NOC2AXI_ROUTER_*_OPT`의 `router_o_*`/`noc2axi_i_*` port group, dispatch feedthrough, NoC repeater placement, EDC ring topology, helper functions가 아직 빠져 있다.

한 문장으로 요약하면:

> **v8은 v7의 port coverage를 크게 확장해 정답지 재현도를 70%대 초반까지 끌어올린 의미 있는 개선판이다. 이제 남은 병목은 포트 추출이 아니라 generate/wiring/topology 추출이다.**

---

## 1. 참고한 파일

### 정답지

| 파일 | 역할 |
|---|---|
| `test_rtl/Sample/N1B0_HDD_v0.1.md` | 주 비교 기준. Trinity N1B0 4x5 variant HDD |
| `test_rtl/Sample/N1B0_NPU_HDD_v0.1.md` | 보조 비교 기준. NPU 관점 확장 HDD |

### v8 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v8/v8_N1B0_HDD.md` | v8 통합 HDD. 이번 리뷰의 핵심 대상 |
| `test_rtl/rag_result/v8/v8_chip_no_grounding.md` | full 106 ports, PRTN/AXI/SFR/EDC/APB category source |
| `test_rtl/rag_result/v8/v8_chip_grounded.md` | DFX iJTAG chain, SRAM macro source |
| `test_rtl/rag_result/v8/v8_edc.md` | EDC topic result |
| `test_rtl/rag_result/v8/v8_noc.md` | NoC topic result |
| `test_rtl/rag_result/v8/v8_overlay.md` | Overlay/SFPU/TDMA/SMN topic result |

### 비교 기준 리뷰

| 파일 | 참고 포인트 |
|---|---|
| `test_rtl/rag_result/review/codex_review_v7.md` | v7의 성과와 남은 P0 gap |
| `test_rtl/rag_result/review/claude_review_v7.md` | v7의 port classifier/MCP 800char 평가 |

---

## 2. 정량 비교

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[NOT IN KB]` |
|---|---:|---:|---:|---:|---:|---:|
| 정답지 `N1B0_HDD_v0.1.md` | 513 | 22330 | 40 | 186 | 24 | 0 |
| 정답지 `N1B0_NPU_HDD_v0.1.md` | 1290 | 58380 | 105 | 303 | 52 | 0 |
| v7 `v7_N1B0_HDD.md` | 404 | 14729 | 37 | 145 | 4 | 0 |
| v8 `v8_N1B0_HDD.md` | 480 | 17951 | 43 | 212 | 6 | 0 |
| v8 `chip_no_grounding` | 36 | 2967 | 5 | 12 | 0 | 0 |
| v8 `chip_grounded` | 54 | 1651 | 9 | 0 | 2 | 0 |
| v8 `edc` | 31 | 1257 | 5 | 0 | 0 | 1 |
| v8 `noc` | 30 | 1429 | 5 | 11 | 0 | 1 |
| v8 `overlay` | 37 | 1323 | 7 | 5 | 0 | 0 |

해석:

- v8 통합 문서는 정답지 `N1B0_HDD_v0.1.md` 대비 line count 약 94%, table rows 약 114%다.
- v7 대비 line count는 404 → 480, table rows는 145 → 212로 증가했다.
- 증가분은 대부분 Top-Level Ports, PRTN Power, SFR Memory Config, Power Management, DFX chain, delta summary에서 온다.
- code fences는 여전히 정답지보다 적다. 이는 v8이 port list 재현에는 강하지만 wiring/diagram/pseudo-code 재현은 아직 약하다는 신호다.

---

## 3. 섹션별 정답지 비교

### 3.1 Overview

정답지 핵심:

- N1B0은 baseline Trinity 변형이다.
- 핵심 변경은 `trinity_noc2axi_n_opt + trinity_router` 분리 tile pair를 `trinity_noc2axi_router_ne/nw_opt` 통합 HPDF tile로 바꾼 것이다.
- grid는 `SizeX=4`, `SizeY=5`, 20 tiles다.
- per-column AI/DM clock/reset, PRTN, ISO_EN, NoC repeater buffers가 N1B0 addition이다.

v8:

- 4x5 mesh, `SizeX=4`, `SizeY=5`, 20 tiles를 유지했다.
- `106 top-level ports`가 overview에 추가됐다.
- tile type/count/module/position table은 v7과 동일하게 안정적이다.
- `ROUTER placeholder empty by design`도 유지된다.

부족:

- HPDF replacement story는 아직 짧다.
- baseline vs N1B0 차이 table은 없다.

판정: **좋음. 약 78%**

### 3.2 Package Constants and Grid

v8은 v6c/v7에서 확보한 package parser 성과를 유지한다.

| 항목 | 정답지 | v8 |
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
- `noc_axis_t`, `noc_direction_t`, `trinity_clock_routing_t`도 같이 정리했다.

부족:

- helper functions `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex`는 아직 없다.

판정: **매우 좋음. 약 94%**

### 3.3 Tile Map and Endpoint Index

정답지 핵심:

- `EndpointIndex = x * SizeY + y = x*5 + y`
- 20 endpoint rows.
- `ROUTER` at `(1,3)`, `(2,3)` is placeholder.
- `NOC2AXI_ROUTER_NE/NW_OPT` spans Y=4 and Y=3.

v8:

- endpoint table과 dual EP notation `EP=9/8`, `EP=14/13`을 유지한다.
- placeholder router fact도 유지한다.

판정: **매우 좋음. 약 90%**

주의:

- 이전 리뷰와 동일하게, 정답지 내부에 `DISPATCH_E/W` 좌표 표기 불일치가 있다. v8은 v7과 동일하게 `DISPATCH_E=(X=0,Y=3)`, `DISPATCH_W=(X=3,Y=3)`를 유지한다.

### 3.4 Top-Level Ports

v8의 가장 큰 성과다. v7 리뷰에서 P0로 남겼던 다음 항목들이 상당수 해결됐다.

| Port group | 정답지 | v7 | v8 |
|---|---|---|---|
| Clock/reset | 핵심 대부분 필요 | DM clock/reset까지 복구 | 유지 |
| APB register | `i_reg_*[NumApbNodes]`, `o_reg_*[NumApbNodes]` | scalar-like partial | 8 ports category 유지 |
| EDC APB + IRQ | APB + 5 IRQ | APB partial, IRQ table 부족 | APB + `o_edc_*_irq` 5개 복구 |
| AXI | `npu_out_*`, `npu_in_*` | 없음 | 39 ports category 복구 |
| SFR Memory Config | `SFR_RF_2P_HSC_*`, `SFR_RA1_HS_*`, `SFR_RF1_HS_*`, `SFR_RF1_HD_*` | 없음 | 17 ports category 복구 |
| PRTN/ISO | `PRTNUN_*`, `ISO_EN[11:0]`, `TIEL_DFT_MODESCAN` | 없음 | 14 ports 복구 |

좋은 점:

- `npu_out_*`/`npu_in_*` AXI group이 처음으로 들어왔다.
- SFR memory config가 별도 section으로 들어왔다.
- PRTN/ISO가 드디어 복구됐다.
- EDC IRQ outputs가 top-level ports에 명시됐다.
- total 106 top-level ports라는 category-level summary가 생겼다.

주의할 점:

- AXI는 `npu_out_*` 일부 signal만 explicit table로 나오고 `npu_in_*`는 summary 처리됐다. 정답지 대체 수준으로는 full expansion이 더 필요하다.
- APB register ports는 여전히 `[NumApbNodes]` array dimension이 table에 직접 보이지 않는다.
- EDC APB도 정답지의 `[4]` array dimension이 table에서 빠져 있다.
- SFR list는 정답지보다 더 넓게 나온 부분도 있지만, count가 "17 ports"라고 되어 있는 반면 상세 table은 family grouping과 실제 signal count를 재점검할 필요가 있다.

판정: **대폭 개선. 약 82~86%**

v7 대비:

- v7 약 60% → v8 약 84%로 상승.
- v8 개선의 핵심은 parser 변경보다는 `max_results=50`로 더 많은 port classifier result가 retrieval된 점으로 보인다.

### 3.5 Module Hierarchy

v8 유지/개선:

- top-level active blocks, EP, `ROUTER` placeholder는 유지된다.
- TDMA 3 submodules 유지.
- DFX hierarchy가 v7보다 조금 더 강화됐다:
  - `tt_disp_eng_overlay_wrapper_dfx` 추가
  - `tt_instrn_engine_wrapper_dfx` upstream source: `tt_t6_l1_partition`, `tt_fpu_gtile_0/1`
  - `tt_disp_eng_noc_niu_router_dfx` relation 정리

부족:

- 정답지의 generate block hierarchy가 아직 없다.
- `gen_x`, `gen_y`, `gen_noc2axi_router_*`, `gen_dispatch_*`, `gen_tensix_neo` 구조가 없다.
- `NOC2AXI_ROUTER_*_OPT` 내부 Y=4/Y=3 split과 `router_o_*` mapping이 없다.

판정: **v7 대비 소폭 개선. 약 66~68%**

### 3.6 Compute Tile — Tensix

v8:

- SFPU facts 유지.
- TDMA 3 submodules 유지.
- `tt_t6_l1_partition` 유지.
- FDS register facts 유지.
- SRAM macro가 x12 Tensix에도 연결된 것으로 inventory에 포함된다.

부족:

- FPU G-Tile/M-Tile, DEST/SRCB/SRCA data path는 아직 없다.
- L1 internals는 `16-bank SRAM` 수준에 머문다.
- compute tile 동작 설명과 verification detail은 아직 부족하다.

판정: **v7과 거의 동등. 약 45~48%**

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

v8:

- `tt_dispatch_top_east`, `tt_dispatch_top_west`, coordinates, EP만 있다.
- DFX쪽 dispatch wrapper 정보는 늘었지만, 정답지의 dispatch feedthrough section은 여전히 없다.

판정: **거의 미개선. 약 24~25%**

### 3.8 NoC Fabric

v8:

- NoC 9 module list 유지.
- `v8_noc.md`는 명시적으로 "No new NoC claims from parser. Coverage unchanged."라고 한다.
- ATT SRAM/BIST 유지.

부족:

- Routing algorithms, flit header, AXI gasket, VC buffers, security fence는 `[NOT IN KB]`.
- 정답지의 Y=3/Y=4 repeater placement, 4/6 repeater count, `noc_east2west_req_repeaters_between_*` naming이 없다.

판정: **v7과 거의 동등. 약 40~42%**

### 3.9 NIU / AXI Bridge Tiles

v8 개선:

- `npu_out_*`/`npu_in_*` AXI interface category가 들어오면서 NIU/AXI bridge section을 뒷받침할 top-level port evidence가 생겼다.
- NIU tile table은 유지된다.

부족:

- corner NIU vs composite NIU+Router 내부 차이는 아직 얕다.
- `NOC2AXI_ROUTER_*_OPT` port groups, `noc2axi_i_*`, `router_o_*`, AXI address width detail은 부족하다.

판정: **v7 대비 개선. 약 60~62%**

### 3.10 Clock and Reset

v8:

- v7에서 복구한 `i_dm_clk`, DM core/uncore reset을 유지한다.
- clock domain table이 정리됐다.
- `trinity_clock_routing_t` fields 유지.

부족:

- `clock_routing_in[SizeX][SizeY]`, `clock_routing_out[SizeX][SizeY]` arrays가 없다.
- Y=4 clock entry point가 없다.
- reset packing with `getTensixIndex`가 없다.
- `NOC2AXI_ROUTER_*_OPT` exception: Y=4 output unused, Y=3 driven by `router_o_*`가 없다.
- `noc_clk bypass` observation이 없다.

판정: **v7과 거의 동등. 약 67~68%**

### 3.11 Power Management / PRTN / ISO

정답지 핵심:

- `PRTNUN_FC2UN_*`
- `PRTNUN_UN2FC_*`
- 4-column daisy chain topology.
- `ISO_EN[11:0]`
- `TIEL_DFT_MODESCAN`

v8:

- 14 PRTN/Power ports를 모두 category로 가져왔다.
- `TIEL_DFT_MODESCAN` 포함.
- `ISO_EN[11:0]` 포함.
- Power Management section이 새로 생겼다.
- 4-column daisy-chain 요약도 들어갔다.

부족:

- 정답지처럼 per-column topology를 `[x][2] → [x][1] → [x][0]` 형태로 구체화하진 않았다.
- `w_left_prtnun_*[x][2]` tap detail은 없다.

판정: **v7 0% → v8 약 75~80%**

### 3.12 EDC

v8 개선:

- EDC APB + IRQ top-level ports가 확실히 좋아졌다.
- `o_edc_fatal_err_irq`, `o_edc_crit_err_irq`, `o_edc_cor_err_irq`, `o_edc_pkt_sent_irq`, `o_edc_pkt_rcvd_irq`가 명시됐다.
- EDC module facts는 유지된다.

부족:

- 정답지의 EDC interface arrays `[SizeX*SizeY]`와 endpoint index relation이 없다.
- ring topology, harvest bypass, CDC는 여전히 `[NOT IN KB]`.
- EDC APB `[4]` array dimension은 table에서 빠져 있다.

판정: **v7 대비 개선. 약 78~82%**

### 3.13 SRAM Inventory and Memory Config

v8 개선:

- `tt_mem_wrap_32x1024_2p_nomask` 유지.
- `RF_2P_HSC_LVT_32X136M1FB1WM0DR0` 유지.
- SFR Memory Config ports가 새로 들어왔다.
- SFR family가 별도 subsection으로 분리되어 v7의 "SRAM macro vs SFR" 혼동이 줄었다.

정답지 대비:

- 정답지의 Memory Config section은 SFR ports 중심이므로, v8은 이 섹션을 v7보다 훨씬 잘 채운다.
- 다만 정답지는 "어떤 SFR family가 TENSIX/DISPATCH/NOC2AXI 중 어디에 적용되는지"를 표로 구분한다. v8은 family 설명은 있지만 적용 대상 표는 없다.

판정: **대폭 개선. 약 65~70%**

### 3.14 DFX

v8 개선:

- `tt_disp_eng_overlay_wrapper_dfx`가 새로 들어왔다.
- `tt_instrn_engine_wrapper_dfx` upstream source가 추가됐다.
- iJTAG chain topology가 v7보다 더 완성됐다.

부족:

- 정답지/확장 정답지 수준의 DFX hierarchy 전체와 scan/iJTAG verification detail은 아직 부족하다.

판정: **개선. 약 58~62%**

### 3.15 RTL File Reference

v8:

- package/top/variants/router placeholder/EDC package variants는 유지된다.

부족:

- `trinity_noc2axi_router_ne_opt.sv`, `trinity_noc2axi_router_nw_opt.sv`, `trinity_noc2axi_ne_opt.sv`, `trinity_noc2axi_nw_opt.sv` 등 정답지 file map의 주요 entries가 아직 full로 없다.
- dispatch/tensix/NoC/clock/DFX file references도 부족하다.

판정: **v7과 거의 동등. 약 50%**

---

## 4. v7 → v8 변화 분석

| 항목 | v7 | v8 | 변화 |
|---|---|---|---|
| 문서 크기 | 404 lines / 14.7KB | 480 lines / 17.9KB | 증가 |
| Generated date | 2026-05-01, 미래 날짜 | 2026-04-29, 현재 날짜와 정합 | 개선 |
| Package/grid | 정확 | 정확 유지 | 유지 |
| Top ports | 약 31개 수준, partial | 106 total categories | 대폭 개선 |
| AXI | 없음 | 39 ports category | 해결 |
| SFR Memory Config | 없음 | 17 ports category | 해결 |
| PRTN/ISO | 없음 | 14 ports + Power section | 해결 |
| EDC IRQ | partial | 5 IRQ explicit | 해결 |
| TDMA | 3 submodules | 유지 | 동등 |
| DFX | iJTAG chain partial | overlay wrapper/upstream 보강 | 개선 |
| NoC topology | 부족 | 부족 | 미해결 |
| Dispatch feedthrough | 부족 | 부족 | 미해결 |
| Clock routing arrays | 부족 | 부족 | 미해결 |
| Helper functions | 없음 | 없음 | 미해결 |

v8의 의미:

- v7은 port classifier/MCP 800char의 첫 효과였다.
- v8은 같은 pipeline에서 `max_results=50`을 통해 숨은 port categories를 더 끌어낸 버전이다.
- parser 자체의 새 범주보다는 retrieval depth 증가의 효과가 크다.
- v7 리뷰에서 P0로 남겼던 PRTN/ISO, AXI, SFR, EDC IRQ가 해결되었다.

---

## 5. 종합 점수

`N1B0_HDD_v0.1.md` 기준 Codex 보수 평가:

| 섹션 | 가중치 | v7 충족도 | v8 충족도 | v8 가중 점수 |
|---|---:|---:|---:|---:|
| Overview / N1B0 identity | 8% | 75% | 78% | 6.2 |
| Package constants / `tile_t` / endpoint | 22% | 94% | 94% | 20.7 |
| Top-level ports | 14% | 60% | 84% | 11.8 |
| Module hierarchy | 12% | 64% | 67% | 8.0 |
| NoC fabric connections | 10% | 41% | 42% | 4.2 |
| Clock/reset routing | 10% | 67% | 68% | 6.8 |
| EDC ring/interface | 8% | 75% | 81% | 6.5 |
| Dispatch feedthrough | 5% | 24% | 25% | 1.3 |
| PRTN/ISO/power | 5% | 0% | 78% | 3.9 |
| Memory config / SRAM | 3% | 32% | 68% | 2.0 |
| RTL file map / verification | 3% | 50% | 50% | 1.5 |
| **합계** | **100%** | **~63.3%** | — | **~72.9%** |

정성 판정:

- 정답지 "핵심 좌표계" 기준: **상**
- 정답지 "top-level signal 재현" 기준: **상**
- 정답지 "power/memory config 재현" 기준: **중상**
- 정답지 "wiring/topology 설명" 기준: **중하**
- 실사용 초안 가치: **높음**
- 그대로 정답지 대체 가능성: **중간**

---

## 6. 남은 핵심 Gap

### 6.1 P0: 다음 버전의 핵심 병목

| Gap | 정답지 위치 | v8 상태 | 권장 query/source |
|---|---|---|---|
| `clock_routing_in/out` arrays | Section 6 | 없음 | `clock_routing_in`, `clock_routing_out`, `router_o_ai_clk`, `router_o_dm_clk` |
| `NOC2AXI_ROUTER_*_OPT` port groups | Section 4.2/4.3 | 없음 | `noc2axi_i_*`, `router_i_*`, `router_o_*`, `i_de_to_t6_*` |
| Dispatch feedthrough | Section 8 | 없음 | `de_to_t6_coloumn`, `de_to_t6_east`, `de_to_t6_west`, `t6_to_de`, `t6_to_de_accross` |
| NoC repeater placement | Section 5 | 없음 | `repeaters_between_noc2axi`, `repeaters_between_router` |
| Helper functions | Section 2.5 | 없음 | `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex` |
| EDC ring arrays/topology | Section 7 | module facts only | `edc_ingress_intf`, `edc_egress_intf`, `loopback_edc_ingress_intf`, `x*SizeY+y` |

### 6.2 P1: 정확도/표현 보정

| Issue | 설명 | 권장 |
|---|---|---|
| AXI full expansion | `npu_out_*` 일부만 table, `npu_in_*`는 summary | 39 ports full table로 확장 |
| APB array dimensions | `i_reg_*[NumApbNodes]` dimension이 table에 직접 없음 | dimension preservation 강화 |
| EDC APB array dimensions | 정답지는 `[4]`, v8 table은 scalar-like | group dimension extraction |
| SFR count 검증 | "17 ports" count와 detailed list/family grouping 재검증 필요 | classifier count audit |
| PRTN topology detail | v8은 요약 topology, 정답지는 per-column `[x][2]→[x][1]→[x][0]` | `w_left_prtnun_*` extraction |
| RTL file map | NOC2AXI router/corner files, dispatch/tensix files 부족 | file reference search 확장 |

---

## 7. 권장 다음 단계

### 7.1 v9 후보: `trinity.sv` generate/wiring pass

v8까지는 package와 top-level ports가 상당히 좋아졌다. 다음 점수 상승은 더 많은 max_results가 아니라 `trinity.sv` 내부 wiring/generate parser가 만든다.

필수 extraction 대상:

- `clock_routing_in[SizeX][SizeY]`
- `clock_routing_out[SizeX][SizeY]`
- `gen_noc2axi_router_ne_opt`, `gen_noc2axi_router_nw_opt`
- `noc2axi_i_*`, `router_i_*`, `router_o_*`
- `de_to_t6_*`, `t6_to_de_*`
- `edc_ingress_intf`, `edc_egress_intf`, loopback EDC arrays
- `repeaters_between_noc2axi`, `repeaters_between_router`
- helper functions in `trinity_pkg.sv`

예상 효과:

- Clock/reset routing 68% → 85%+
- Dispatch feedthrough 25% → 65%+
- NoC fabric connections 42% → 60%+
- EDC topology 81% → 88%+
- 전체 점수 73% → 78~82% 가능

### 7.2 Retrieval/reporting 개선

| 개선 | 이유 |
|---|---|
| Full port table export | AXI `npu_in_*` summary 문제 제거 |
| Array dimension preservation | APB/EDC APB 정확도 개선 |
| Required facts checklist | 무음 누락 방지 |
| Count audit | 106 total, category counts, detailed rows 정합성 검증 |
| Source trace line/file anchor | generated fact 검증성 강화 |
| Wiring facts와 port facts 분리 | 앞으로 남은 gap의 성격을 더 명확히 표현 |

---

## 8. 최종 판정

v8은 v7 대비 명확한 진전이다. v7에서 남아 있던 큰 P0 gap인 `PRTN/ISO`, AXI interface, SFR memory config, EDC IRQ outputs가 해결되면서, 정답지의 Top-Level Ports와 Power/Memory Config 재현도가 확 올라갔다.

이번 개선은 "새로운 parser 범주"라기보다는 **max_results=50으로 retrieval depth를 늘렸더니 이미 존재하던 port classifier facts가 드러난 것**에 가깝다. 그래서 v8의 성공은 단순 분량 증가가 아니라, 이전 버전에서 검색 상위에 못 올라오던 핵심 port facts를 회수한 데 있다.

하지만 남은 gap은 더 어려운 영역이다. 이제 부족한 것은 포트 목록이 아니라 wiring and topology다. 정답지의 핵심 후반부인 clock routing propagation, dispatch feedthrough, NoC repeater placement, EDC array topology는 `trinity.sv` generate/wiring 구조를 직접 읽어야 채워진다.

버전 흐름으로 보면:

- **v6c:** package/grid anchor 복구
- **v7:** DM/APB/EDC APB, TDMA/SRAM/DFX fact 확장
- **v8:** AXI/SFR/PRTN/ISO/EDC IRQ 등 top-level port surface 대폭 복구
- **다음 목표:** generate/wiring topology extraction

따라서 v8은 **정답지 재현도 약 73% 수준의 큰 개선판**으로 평가한다. 다음 단계에서 `trinity.sv` generate/wiring pass가 들어가면, 80% 근처까지 올라갈 가능성이 있다.

---

*End of Review — Codex Review v8*
