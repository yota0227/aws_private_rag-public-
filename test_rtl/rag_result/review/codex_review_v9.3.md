# Codex Review: RAG v9.3 정답지 비교 분석

**작성일:** 2026-05-12  
**리뷰어:** Codex  
**비교 대상:** `test_rtl/rag_result/v9.3/v9.3_N1B0_HDD.md` 중심, `test_rtl/rag_result/v9.3/` 전체 산출물 보조 비교  
**저장 위치:** `test_rtl/rag_result/review/codex_review_v9.3.md`  

---

## 0. 결론

v9.3는 v9.2에서 확보한 EP table, dispatch/flit/clock array, L1 EDC daisy-chain을 유지하면서 **Port Binding Parser**, **Neptune `CONNECTS_TO`**, **Graph Export API**, **always block CDC boundary**를 추가한 버전이다. 최종 통합 HDD 기준으로는 v9.2의 407 lines / 172 table rows에서 v9.3의 492 lines / 216 table rows로 증가했고, 문서 밀도만 보면 정답지 `N1B0_HDD_v0.1.md`의 513 lines / 186 table rows에 거의 도달했다.

가장 의미 있는 개선은 세 가지다.

1. `noc_east2west_req_repeaters_between_noc2axi.i_clk -> i_noc_clk`, `i_reset_n -> i_noc_reset_n`, `trinity_noc2axi_router_ne_opt.noc2axi_i_nocclk -> i_noc_clk`, `i_noc_endpoint_id -> EndpointIndex` 같은 **실제 `.port(signal)` 바인딩 증거**가 처음으로 HDD에 들어왔다.
2. `v9.3_edc.md`가 EDC toggle handshake, APB4 port table, U-shape ASCII, connector paths, file paths를 포함하면서 v9.2보다 훨씬 정답지형 산출물에 가까워졌다.
3. `v9.3_overlay.md`가 `tt_overlay_wrapper` hierarchy, `TTTrinityConfig_TilePRCIDomain`, L1 EDC generate elements, iDMA modules, NIU register CDC 등 overlay/topic 보강을 꽤 잘 수행했다.

하지만 v9.3는 아직 "graph RAG가 성능을 끌어올린 버전"이라고 보기에는 이르다. Port binding이 실제로 들어왔지만 대부분 clock/reset/endpoint_id에 국한되어 있고, 정답지의 핵심인 **dual-row `NOC2AXI_ROUTER_*_OPT`의 full port group mapping**, **NoC four repeater instance/count**, **manual X-axis assign topology**, **EDC flat array exception**, **DFX 4-wrapper chain**까지는 최종 HDD에 충분히 반영되지 못했다. 즉 graph/CONNECTS_TO 인프라는 생겼지만, 그 결과가 아직 "evidence path 기반 문서 생성"으로 완전히 연결되지는 않았다.

점수는 두 기준으로 분리하는 것이 맞다.

- **통합 HDD 단독 기준:** `v9.3_N1B0_HDD.md`만 정답지 대체물로 보면 약 **72~74%**
- **v9.3 산출물 전체 best-of 기준:** `chip_grounded`, `edc`, `noc`, `overlay`까지 함께 읽으면 약 **79~81%**

한 문장으로 요약하면:

> **v9.3는 v9.2의 구조 회수 성과 위에 port binding과 CDC evidence를 얹은 의미 있는 개선판이지만, 아직 graph가 "검색 결과"가 아니라 "문서 말미의 신규 기능 표시" 수준에 머문다. 다음 병목은 CONNECTS_TO path를 hierarchy/wiring/DFX 섹션의 주 evidence로 승격하는 것이다.**

---

## 1. 참고한 파일

### 정답지

| 파일 | 역할 |
|---|---|
| `test_rtl/Sample/ORG/N1B0_HDD_v0.1.md` | 주 비교 기준. N1B0 4x5 variant HDD |
| `test_rtl/Sample/ORG/N1B0_NPU_HDD_v0.1.md` | 보조 비교 기준. NPU 관점 확장 HDD |
| `test_rtl/Sample/ORG/N1B0_DFX_HDD_v0.1.md` | DFX wrapper chain 비교 기준 |
| `test_rtl/Sample/ORG/N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` | composite NIU/router 상세 비교 기준 |

### v9.3 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v9.3/v9.3_N1B0_HDD.md` | v9.3 통합 HDD. 이번 리뷰의 핵심 대상 |
| `test_rtl/rag_result/v9.3/v9.3_chip_no_grounding.md` | KB-only raw output. v9.3 신규 claim 확인용 |
| `test_rtl/rag_result/v9.3/v9.3_chip_grounded.md` | Hybrid grounding output. `[FROM LLM]`, `[NOT IN KB]`, `[TBC]` 포함 |
| `test_rtl/rag_result/v9.3/v9.3_edc.md` | EDC topic result. v9.3에서 가장 많이 보강된 topic 문서 |
| `test_rtl/rag_result/v9.3/v9.3_noc.md` | NoC topic result. Port binding, endpoint map, TBC bit range 포함 |
| `test_rtl/rag_result/v9.3/v9.3_overlay.md` | Overlay/RISC-V topic result. hierarchy와 CDC 보강 |

### 비교 기준 리뷰

| 파일 | 참고 포인트 |
|---|---|
| `test_rtl/rag_result/review/codex_review_v9.2.md` | v9.2 미해결 gap 및 보수적 점수 기준 |
| `test_rtl/rag_result/review/kiro_review_v9.2.md` | v9.3 예상 목표: DFX, 실명 복구, merge 개선 |
| `test_rtl/rag_result/review/claude_review_v9.2.md` | v9.2 구조 개선 vs 실명 회귀 관점 |

---

## 2. 정량 비교

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[FROM LLM]` | `[NOT IN KB]` | `[TBC]` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 정답지 `N1B0_HDD_v0.1.md` | 513 | 22330 | 40 | 186 | 24 | 0 | 0 | 0 |
| 정답지 `N1B0_NPU_HDD_v0.1.md` | 1290 | 58380 | 105 | 303 | 52 | 0 | 0 | 0 |
| v8 `v8_N1B0_HDD.md` | 480 | 17951 | 43 | 212 | 6 | 0 | 0 | 0 |
| v9.1 `v9.1_N1B0_HDD.md` | 331 | 11274 | 27 | 117 | 4 | 0 | 0 | 0 |
| v9.2 `v9.2_N1B0_HDD.md` | 407 | 13887 | 41 | 172 | 2 | 0 | 0 | 0 |
| **v9.3 `v9.3_N1B0_HDD.md`** | **492** | **18750** | **46** | **216** | **2** | **0** | **0** | **0** |
| v9.3 `chip_no_grounding` | 215 | 9206 | 17 | 29 | 0 | 0 | 0 | 0 |
| v9.3 `chip_grounded` | 354 | 14554 | 30 | 113 | 2 | 16 | 3 | 1 |
| v9.3 `edc` | 251 | 9445 | 20 | 88 | 4 | 0 | 0 | 2 |
| v9.3 `noc` | 178 | 6634 | 15 | 61 | 2 | 0 | 0 | 2 |
| v9.3 `overlay` | 220 | 9483 | 19 | 57 | 4 | 0 | 0 | 0 |

해석:

- v9.3 통합 HDD는 v9.2 대비 407 -> 492 lines, 172 -> 216 table rows로 증가했다.
- table row 수는 정답지 `N1B0_HDD_v0.1.md`를 넘어섰다. 단, 많은 row가 topic 보강/port binding/CDC summary에서 온 것이며, 정답지의 pseudo-code/wiring snippet을 대체하지는 못한다.
- code fence는 여전히 2개뿐이다. 정답지 24개 대비 매우 적어서 generate hierarchy, assign snippet, topology diagram 재현력은 아직 부족하다.
- `chip_no_grounding`은 v9.2의 376 lines에서 v9.3의 215 lines로 줄었다. KB-only 산출물만 보면 오히려 덜 완성된 문서이고, 최종 통합본 품질은 `chip_grounded`, `edc`, `noc`, `overlay`에서 흡수한 정보에 많이 의존한다.
- `chip_grounded`의 `[FROM LLM]` 16개, `[NOT IN KB]` 3개, `[TBC]` 1개는 v9.2보다 보강 설명이 늘었지만, grounding된 fact와 LLM 보완의 경계가 최종 통합 HDD에서는 사라진다는 점을 주의해야 한다.

### 2.1 점수 기준

| 평가 관점 | 포함 파일 | 장점 인정 방식 | 결과 |
|---|---|---|---:|
| 통합 HDD 단독 | `v9.3_N1B0_HDD.md` | 최종 문서에 직접 남은 내용만 인정 | ~72~74% |
| v9.3 산출물 전체 best-of | `v9.3/` 6개 문서 전체 | topic 문서와 grounded/no-grounding 상세 정보를 함께 인정 | ~79~81% |
| KB-only strict | `v9.3_chip_no_grounding.md` 중심 | `[KB]`로 직접 노출된 claim만 인정 | ~58~62% |

---

## 3. v9.2 -> v9.3 핵심 변화

| 축 | v9.2 | v9.3 | 판정 |
|---|---|---|---|
| 통합 HDD 크기 | 407 lines / 172 rows | 492 lines / 216 rows | 개선 |
| EP Index Table | 20행 완전 | 20행 완전 | 유지 |
| Dispatch wiring | 6종 wire | 6종 wire 유지, 단 `de_to_t6_coloumn` 차원 표기가 `[SizeX][SizeX]`로 흔들림 | 유지+부분 회귀 |
| Flit 4D array | 4x5x2x2 | 4x5x2x2 | 유지 |
| Clock routing mesh | 4x5 | 4x5 + CDC boundaries | 개선 |
| Port Binding | 없음 | clock/reset/endpoint_id binding 표 추가 | 신규 |
| Neptune CONNECTS_TO | 없음 | delta로 표시. 실제 path table은 없음 | 인프라 수준 |
| Graph Export API | 없음 | delta로 표시. 문서 evidence로는 미반영 | 인프라 수준 |
| EDC topic | 149 lines / 42 rows | 251 lines / 88 rows | 대폭 개선 |
| Overlay topic | 152 lines / 40 rows | 220 lines / 57 rows | 개선 |
| SFR/PRTN 실명 | 와일드카드 회귀 | 통합본은 여전히 와일드카드/요약 | 미해결 |
| DFX 4-wrapper chain | 미반영 | 통합본은 여전히 미반영, DFT path만 추가 | 미해결 |

---

## 4. 섹션별 정답지 비교

### 4.1 Overview

정답지 핵심:

- N1B0은 baseline Trinity에서 `trinity_noc2axi_n_opt + trinity_router` tile pair를 `trinity_noc2axi_router_ne/nw_opt` HPDF/composite tile로 교체한 변형이다.
- composite tile은 Y=4 NOC2AXI와 Y=3 router logic을 함께 담는 dual-row 구조다.
- per-column AI/DM clock/reset, PRTN, ISO_EN, NoC repeater buffers가 N1B0 addition이다.

v9.3:

- 4x5 mesh, 20 nodes, 12 Tensix, 4 NIU, 2 Dispatch, 14 DM complexes, EDC, dynamic routing을 안정적으로 유지한다.
- `trinity_router`가 N1B0에서 standalone으로 instantiation되지 않는다는 note도 유지한다.

부족:

- Overview 첫 문단이 여전히 generic NPU 설명으로 시작한다.
- `trinity_noc2axi_n_opt + trinity_router`가 composite tile로 교체됐다는 N1B0 identity가 Overview에는 없다.
- baseline vs N1B0 difference table이 통합본에 없다. 정답지의 §13 차이표와 §1.1 table은 여전히 빠져 있다.

판정: **v9.2와 유사. 약 66%**

### 4.2 Package Constants, Grid, Endpoint

v9.3:

- 13 localparams, `tile_t`, EndpointIndex formula, 20-row EP table, helper functions, `trinity_clock_routing_t`를 유지한다.
- EP table은 정답지와 사실상 일치한다.

좋은 점:

- v9.2에서 회복한 좌표계 anchor가 안정적으로 유지됐다.
- `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex`, `isEastEdge`, `isNorthEdge`가 통합본에 남아 있다.

부족:

- 정답지의 `GridConfig[y][x]` ASCII map은 여전히 통합본에 없다. `v9.3_noc.md`에는 endpoint map ASCII가 있지만 통합 HDD §2에는 merge되지 않았다.
- helper functions의 scan order와 count semantics가 없다.
- `ROUTER` placeholder가 EP 8/13을 reserve하고 실제 router logic이 composite tile 내부에 있다는 package-level note가 부족하다.
- `NOC2AXI_ROUTER_NE/NW_OPT`가 Y=4와 Y=3을 동시에 점유한다는 설명이 hierarchy/NIU 쪽에 일부만 있고 package section에는 없다.

판정: **v9.2와 유사. 약 79%**

### 4.3 Top-Level Ports

v9.3:

- 106 total ports와 category count는 유지한다.
- EDC top-level ports 16개는 §11.4에서 실명으로 복구됐다.
- reset/clock dimensions는 안정적으로 표시된다.

부족:

- 정답지의 top module parameter table이 아직 없다:
  - `AXI_SLV_OUTSTANDING_READS=64`
  - `AXI_SLV_OUTSTANDING_WRITES=32`
  - `AXI_SLV_RD_RDATA_FIFO_DEPTH=512`
  - `NPU_DATA_W=512`
  - `NPU_IN_ADDR_W=56`
  - `NPU_OUT_ADDR_W=56`
- AXI 39개는 full channel signal table이 아니라 `npu_out_*`, `npu_in_*` 요약이다.
- APB register ports는 `[NumApbNodes]` array dimension이 통합본 §3에서는 구체적으로 풀리지 않는다.
- SFR 17개와 PRTN 14개 실명은 v9.1 수준으로 복구되지 않았다. 통합본은 `SRAM timing/margin controls`, `PRTNUN protocol` 요약으로 남는다.
- `chip_no_grounding`은 "상세 포트 테이블은 KB 커버리지 부족"이라고 명시해 strict KB 관점에서는 오히려 약하다.

판정:

- **통합 HDD 단독:** 약 75%
- **v9.3 folder best-of:** EDC ports까지 포함하면 약 81%

### 4.4 Module Hierarchy

v9.3 개선:

- hierarchy tree에 `noc_east2west_req_repeaters_between_noc2axi`, `trinity_noc2axi_nw_opt`, `trinity_noc2axi_router_ne_opt`, `tt_overlay_wrapper`, `TTTrinityConfig_TilePRCIDomain`, overlay CDC/BIST modules가 추가됐다.
- `v9.3_overlay.md`는 `tt_overlay_wrapper` 하위 구조를 v9.2보다 훨씬 잘 보여준다.

부족:

- 정답지의 Level-1 generate hierarchy는 여전히 통합본에 없다:
  - `gen_x[0] gen_y[4]: gen_noc2axi_ne_opt`
  - `gen_x[1] gen_y[4]: gen_noc2axi_router_ne_opt`
  - `gen_x[2] gen_y[4]: gen_noc2axi_router_nw_opt`
  - `gen_x[3] gen_y[4]: gen_noc2axi_nw_opt`
  - `gen_dispatch_e/w`, `gen_tensix`
- composite tile 내부의 `trinity_noc2axi_n_opt logic` + `trinity_router logic` dual-row 설명이 통합본 hierarchy에는 없다.
- `trinity_noc2axi_router_nw_opt`가 hierarchy tree에 빠져 있고, Port Binding도 `_router_ne_opt` 중심이다.
- `router_o_*`, `noc2axi_i_*`, `router_i_*`, `i_de_to_t6_*`, `i/o_noc2axi_*`, `i/o_axi2noc_*` port prefix mapping은 정답지 수준으로 들어오지 않았다.

판정: **v9.2 대비 개선. 약 63%**

### 4.5 Compute Tile - Tensix

v9.3 개선:

- FPU submodule table이 v9.2보다 깊어졌다:
  - `tt_fp_int_rnd`
  - `tt_multiop_adder`
  - `tt_aux_sop_add_5_1`
  - `tt_cla_shift_amnt`
  - `tt_barrel_rshift`
  - `tt_sfpu_lregs` parameter
- `v9.3_overlay.md`가 CPU cluster, TileLink, RoCC, L1 cache, iDMA, FDS, APB interface를 보강한다.

부족:

- 정답지 `N1B0_NPU_HDD_v0.1.md`의 TRISC/BRISC, G-Tile/M-Tile, FP lane, DEST/SRCA/SRCB, L1 bank, instruction engine hierarchy는 통합본에서 여전히 약하다.
- `chip_grounded`의 BRISC/TRISC와 DEST/SRCB는 `[FROM LLM]`이다.
- v9.1에서 있었던 Instruction Engine 6-sub table은 v9.3 통합본에서도 복구되지 않았다.

판정:

- **통합 HDD 단독:** 약 58%
- **v9.3 folder best-of:** overlay 포함 시 약 64%

### 4.6 Dispatch Engine

v9.3:

- East/West dispatch EP 3/18과 6종 feedthrough wire를 유지한다.
- type이 `tt_chip_global_pkg::de_to_t6_t`, `tt_chip_global_pkg::t6_to_de_t`로 명시되어 v9.2보다 타입 출처는 좋아졌다.

주의할 점:

- `de_to_t6_coloumn` 차원이 v9.3 통합본과 grounded에서 `[SizeX][SizeX]`로 표기된다. 정답지는 `de_to_t6_coloumn[SizeX][SizeY-1][2]`이고, v9.2는 적어도 `[SizeX][SizeY-1]`로 더 올바른 방향이었다. 4x4 숫자는 우연히 같지만 의미는 다르다.
- 마지막 `[2]` dimension은 여전히 빠져 있다.
- `NOC2AXI_ROUTER_*_OPT` tiles가 feedthrough를 carry한다는 port-level mapping snippet은 통합본에 없다.
- 정답지의 `.i_de_to_t6_east_feedthrough`, `.o_de_to_t6_east_feedthrough`, `.i_t6_to_de_south` 같은 connection snippet이 없다.

판정: **v9.2와 유사하되 차원 표기 회귀 있음. 약 62%**

### 4.7 NoC Fabric

v9.3 개선:

- NoC topic에 Port Binding table이 추가됐다.
- `noc_east2west_req_repeaters_between_noc2axi.i_clk -> i_noc_clk`, `i_reset_n -> i_noc_reset_n`은 명확한 connectivity evidence다.
- AXI 56-bit gasket은 `[TBC]` bit boundary를 명시해 알 수 없는 값을 구분한다.
- endpoint map ASCII는 `v9.3_noc.md`에 유지된다.

부족:

- 통합본에는 endpoint map ASCII가 없다.
- 정답지 핵심인 manual X-axis connection은 통합본에 없다.
- repeater instance는 `noc_east2west_req_repeaters_between_noc2axi` 하나만 명시적으로 올라왔다. 정답지의 4개 핵심 instance가 모두 들어오지는 않았다:
  - `noc_east2west_req_repeaters_between_noc2axi`
  - `noc_west2east_req_repeaters_between_noc2axi`
  - `noc_east2west_req_repeaters_between_router`
  - `noc_west2east_req_repeaters_between_router`
- Y=4 4-stage / Y=3 6-stage count는 통합본에 없다.
- Port Binding은 clock/reset/endpoint_id 중심이며, flit east/west/south path까지 추적하지 못한다.

판정:

- **NoC signal inventory 기준:** 개선
- **N1B0 topology 기준:** 아직 중간
- 종합 **약 58%**

### 4.8 NIU / AXI Bridge Tiles

v9.3 개선:

- Port Binding이 `trinity_noc2axi_router_ne_opt.noc2axi_i_nocclk -> i_noc_clk`, `noc2axi_i_axiclk -> i_axi_clk`, `i_noc_endpoint_id -> EndpointIndex`를 확인한다.
- `trinity_noc2axi_nw_opt.i_axiclk -> i_axi_clk`, `i_noc_endpoint_id -> EndpointIndex`도 들어왔다.
- NIU section이 "endpoint_id per instance"를 언급한다.

부족:

- `trinity_noc2axi_router_nw_opt` 쪽 binding은 통합본에 없다.
- `NOC2AXI_ROUTER_NE/NW_OPT`의 dual-row internal structure가 아직 약하다.
- AXI in/out mapping과 `i/o_noc2axi_*`, `i/o_axi2noc_*` port group이 없다.
- ATT는 여전히 grounded에서 `[FROM LLM]`이고 entry count/bit width는 `[NOT IN KB]`이다.
- 정답지의 `N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` 수준의 parameter/repeater/internal port mapping과는 거리가 있다.

판정: **v9.2 대비 소폭 개선. 약 43%**

### 4.9 Clock / Reset

v9.3 개선:

- `clock_routing_in/out` 4x5 mesh는 유지된다.
- CDC Modules list가 더 구체화됐다:
  - `apb_cdc_n2a_src / apb_cdc_n2a_dst`
  - `tt_async_fifo`
  - `tt_noc_sync3_pulse`
  - `tt_smn_clkdiv`
  - `axi_dynamic_delay_buffer`
- v9.3 always block parser 결과로 CDC boundaries가 추가됐다:
  - NoC <-> gated_noc (`tt_noc_overlay_intf`)
  - NoC <-> core (`BDAed_tt_fds`)
  - NoC <-> uncore (`tt_overlay_niu_reg_cdc`)

부족:

- 정답지의 clock entry point와 propagation snippet은 없다:
  - `clock_routing_in[x][4].ai_clk = i_ai_clk[x]`
  - `clock_routing_in[x][4].dm_clk = i_dm_clk[x]`
  - `clock_routing_in[x][4].power_good = i_edc_reset_n`
- `NOC2AXI_ROUTER_*_OPT` exception, 즉 Y=4 output이 아니라 `router_o_*`로 Y=3 `clock_routing_out[x][y-1]`을 drive한다는 설명이 통합본에는 없다.
- reset packing semantics는 아직 얕다.

판정: **v9.2 대비 개선. 약 72%**

### 4.10 EDC

v9.3 개선:

- `v9.3_edc.md`는 v9.3에서 가장 크게 좋아진 topic 문서다.
- toggle handshake (`req_tgl`, `ack_tgl`), `data[15:0]`, `data_p`, `async_init`가 들어왔다.
- `tt_edc1_biu_soc_apb4_wrap` APB4 port table과 5 IRQ가 상세해졌다.
- U-shape ASCII diagram이 생겼다.
- `edc_direct_conn_nodes`, `edc_loopback_conn_nodes` instance paths와 EDC file paths가 들어왔다.
- top-level EDC 16 ports도 통합본 §11.4에 실명으로 포함됐다.

부족:

- 정답지의 flat arrays `edc_ingress_intf[SizeX*SizeY]`, `edc_egress_intf`, `loopback_*`와 EndpointIndex 공유 설명은 통합본에 없다.
- `NOC2AXI_ROUTER_*_OPT` tiles의 EDC exception, 즉 Y=4 tile position에 EDC interface가 없고 Y=3 index만 연결되는 설명이 없다.
- harvest bypass와 toggle protocol 일부는 `chip_grounded`에서 `[FROM LLM]`로 보강된다.
- `v9.3_edc.md`의 U-shape ASCII는 유용하지만 정답지의 exact ring indexing과 동일하다고 보기는 어렵다.

판정:

- **통합 HDD 단독:** 약 72%
- **v9.3 EDC topic 포함:** 약 82%

### 4.11 Power / PRTN

v9.3:

- 4-column daisy-chain, `ISO_EN[11:0]`, FC2UN/UN2FC protocol, `TIEL_DFT_MODESCAN`은 유지한다.

부족:

- v9.1에서 확보했던 PRTN 14 신호명 실명 table은 통합본에 복구되지 않았다.
- 정답지의 per-column chain detail:
  - external -> `[x][2]` -> `[x][1]` -> `[x][0]` -> output
  - `PRTNUN_UN2FC_DATA_OUT[x]`, `PRTNUN_UN2FC_INTR_OUT[x]` tapped from Y=2
  - dispatch tiles are not in PRTN chain
  는 통합본에 없다.
- `chip_grounded`의 reset/power sequencing은 `[FROM LLM]`이다.

판정: **v9.2와 유사. 약 60%**

### 4.12 SRAM / SFR

v9.3 개선:

- memory wrap variants가 통합본에 들어왔다.
- `tt_mem_parity_decoder`와 `INPUT_WIDTH -> DATA_WIDTH + o_parity_err`가 추가됐다.
- `v9.3_chip_grounded`에는 `ERR_INDEX_WIDTH` 일부가 보인다.

부족:

- 정답지 `N1B0_NPU_HDD_v0.1.md`의 per-tile SRAM inventory, L1 banks, TRISC I-cache/LDM, NoC VC input FIFO, L2 data/dir, context switch SRAM count는 없다.
- SFR 실명은 여전히 family 수준이다. 통합본은 `RF_2P_HSC`, `RA1_HS`, `RF1_HS`, `RF1_HD` timing/margin controls까지만 말한다.
- `chip_grounded`도 total SRAM instance count per tile을 `[NOT IN KB]`로 둔다.

판정: **v9.2 대비 소폭 개선. 약 48%**

### 4.13 DFX

v9.3:

- 통합본에는 `tt_tensix_jtag`, `tt_sync3`, `tt_fpu_gtile_SDUMP_INTF`, `TIEL_DFT_MODESCAN`, DFTed RTL path가 있다.
- DFT path가 새로 들어온 것은 작은 개선이다.

부족:

- v9.2에서 최우선 gap으로 남긴 4-node wrapper chain은 여전히 통합본에 없다:
  - `tt_noc_niu_router_dfx`
  - `tt_overlay_wrapper_dfx`
  - `tt_instrn_engine_wrapper_dfx`
  - `tt_t6_l1_partition_dfx`
- 정답지의 clock pass-through counts, IJTAG absent/ifdef condition, wrapper placement in Tensix tile이 없다.
- `chip_grounded`는 DFX coverage를 "Full"로 표시하지만 실제 본문은 file path + generic JTAG 수준이라 과대평가다.
- `v9.3_overlay.md`에도 DFX wrapper chain은 들어오지 않는다.

판정: **v9.2 대비 거의 미개선. 약 35~40%**

---

## 5. v9.3 신규 기능의 실제 효과

### 5.1 Port Binding Parser

효과 있음. 특히 clock/reset/endpoint_id처럼 검색 키워드만으로는 "어느 인스턴스의 어느 포트가 top signal에 묶이는지" 확인하기 어려운 항목을 구조화했다.

대표 evidence:

| Instance | Port | Connected Signal | 의미 |
|---|---|---|---|
| `noc_east2west_req_repeaters_between_noc2axi` | `i_clk` | `i_noc_clk` | repeater clock binding |
| `noc_east2west_req_repeaters_between_noc2axi` | `i_reset_n` | `i_noc_reset_n` | repeater reset binding |
| `trinity_noc2axi_router_ne_opt` | `noc2axi_i_nocclk` | `i_noc_clk` | composite NIU NoC clock |
| `trinity_noc2axi_router_ne_opt` | `noc2axi_i_axiclk` | `i_axi_clk` | composite NIU AXI clock |
| `trinity_noc2axi_router_ne_opt` | `i_noc_endpoint_id` | `EndpointIndex` | EP assignment evidence |

한계:

- clock/reset/endpoint_id에 치우쳐 있다.
- flit, EDC, dispatch feedthrough, AXI channel binding까지 확장되어야 정답지의 wiring 설명을 대체할 수 있다.
- `router_ne_opt` 중심이고 `router_nw_opt` symmetry가 충분히 안 보인다.

### 5.2 Neptune CONNECTS_TO

문서상으로는 "지원됨"이라고 표시되지만, 최종 HDD에는 실제 graph path table이 없다. 예를 들어 다음 같은 path가 들어와야 v9.3의 성능 향상으로 강하게 인정할 수 있다.

| 필요한 path | 현재 상태 |
|---|---|
| `i_noc_clk -> repeater.i_clk -> repeater output path` | 일부 binding만 있음 |
| `flit_out_req[1][4] -> repeater -> flit_in_req[2][4]` | 없음 |
| `dispatch_e -> de_to_t6_* -> tensix tile` | wire declaration만 있음 |
| `clock_routing_in[x][4] -> router_o_* -> clock_routing_out[x][3]` | 없음 |
| `edc_egress_intf[ep] -> connector -> edc_ingress_intf[ep-1]` | 없음 |

즉 CONNECTS_TO는 인프라로는 큰 방향이 맞지만, v9.3 산출물 기준으로는 아직 "retrieval quality jump"보다 "future potential"에 가깝다.

### 5.3 Graph Export API

통합본 Appendix에 `chip/module/signal scope` 지원으로 표시되지만, 산출물에는 graph export 결과를 기반으로 한 schematic path, subgraph table, hierarchy consistency table이 없다. Viewer와 HDD 생성이 같은 graph evidence를 공유하면 다음 버전에서 큰 상승 여지가 있다.

### 5.4 always_block_parser CDC

실사용 가치가 있다. `NoC <-> gated_noc`, `NoC <-> core`, `NoC <-> uncore` boundary가 topic/통합본에 들어왔다. 다만 정답지의 clock architecture는 CDC inventory보다 clock propagation/exception을 더 중시하므로 점수 상승은 제한적이다.

---

## 6. 주요 회귀 / 위험 포인트

| 항목 | v9.2 | v9.3 | 영향 |
|---|---|---|---|
| `chip_no_grounding` 밀도 | 376 lines / 163 rows | 215 lines / 29 rows | KB-only 검증 문서로는 약화 |
| `de_to_t6_coloumn` dimension | `[SizeX][SizeY-1] = 4x4` | `[SizeX][SizeX]` | 의미상 회귀. 정답지는 `[SizeX][SizeY-1][2]` |
| SFR/PRTN 실명 | 와일드카드 회귀 | 여전히 미복구 | DV 실사용성 제한 |
| DFX coverage label | Partial/weak | `chip_grounded`에서 Full로 표시 | coverage matrix 과대평가 위험 |
| 통합본 grounding tag | 없음 | 없음 | `[FROM LLM]` origin이 통합본에서 사라짐 |

특히 `chip_grounded`의 KB Coverage Matrix는 다음 두 이유로 정답지 fidelity 지표로 쓰면 안 된다.

- DFX를 "Full"로 표시하지만 정답지의 4-wrapper chain은 빠져 있다.
- Reset/EDC/Power 일부는 `[FROM LLM]` 보강이면서 coverage가 Full/Partial로만 표시된다.

---

## 7. 남은 핵심 Gap

| # | Gap | 정답지 위치 | v9.3 상태 | 해결 경로 | 예상 효과 |
|---|---|---|---|---|---:|
| 1 | DFX 4-wrapper chain | NPU §14, DFX HDD | DFT path만 추가, wrapper chain 없음 | `*_dfx.sv` 전용 parser + merge rule | +5~7pp |
| 2 | SFR/PRTN 실명 복구 | HDD §3, §9/12 | 통합본은 여전히 wildcard/summary | signal list compression 금지 + CI | +3~5pp |
| 3 | `NOC2AXI_ROUTER_*_OPT` dual-row full mapping | HDD §4/8, router-opt HDD | 일부 module name + binding만 | composite tile parser + port-prefix template | +4~6pp |
| 4 | NoC repeater 4-instance/count | HDD §5/7 | 1개 instance 중심, NUM 4/6 없음 | repeater parser + graph path export | +3~4pp |
| 5 | CONNECTS_TO path evidence | HDD wiring sections | delta만 있고 path table 없음 | graph traversal result를 HDD 섹션에 삽입 | +4~6pp |
| 6 | Dispatch feedthrough exact dimensions | HDD §8 | `[SizeX][SizeX]` 오표기, `[2]` 누락 | wire dimension resolver 개선 | +1~2pp |
| 7 | Clock propagation exception | HDD §6/9 | 4x5 mesh만 있음 | `clock_routing_in/out` assign parser | +2~3pp |
| 8 | EDC flat arrays + router exception | HDD §7/11 | EDC topic은 개선, flat array exception 없음 | EDC top-level graph traversal | +2~3pp |
| 9 | Instruction Engine 6-sub 복구 | NPU §4/5 | 여전히 통합본 누락 | overlay/tensix merge rule | +2~4pp |
| 10 | AXI gasket exact bit ranges | NPU §7/16 | `[TBC]` 유지 | Spec RAG 또는 package expression parser | +1~2pp |

---

## 8. 종합 점수

| 기준 | v9.2 Codex | v9.3 Codex | 변화 |
|---|---:|---:|---|
| 통합 HDD 단독 | 68~70% | **72~74%** | +3~5pp |
| 산출물 전체 best-of | 76~78% | **79~81%** | +2~4pp |
| KB-only strict | 약 70% 수준 추정 | **58~62%** | 산출물 축소로 하락 |

왜 통합 HDD 점수는 올랐지만 KB-only strict 점수는 낮게 보는가:

- 통합본은 grounded/topic 문서에서 많은 보강을 흡수해 문서 밀도가 좋아졌다.
- 반면 `v9.3_chip_no_grounding.md` 자체는 "KB에서 검색된 내용만 사용"이라는 조건 아래 빈 섹션/제한적 노출을 명확히 드러낸다.
- 따라서 v9.3의 실제 시스템 평가는 "raw KB retrieval"보다 "topic merge + grounded synthesis"에 의존한다.

---

## 9. 권장 다음 단계

### v9.4: Graph evidence를 문서의 본문으로 승격

1. **CONNECTS_TO path table을 HDD 섹션에 직접 삽입**
   - NoC §7에는 flit path.
   - Clock §9에는 clock path.
   - Dispatch §6에는 feedthrough path.
   - EDC §11에는 ring path.

2. **Port Binding 범위를 clock/reset에서 data/control path로 확장**
   - `flit_*`
   - `edc_*_intf`
   - `de_to_t6_*`, `t6_to_de_*`
   - `i/o_noc2axi_*`, `i/o_axi2noc_*`

3. **DFX wrapper chain 전용 파서**
   - `tt_noc_niu_router_dfx`
   - `tt_overlay_wrapper_dfx`
   - `tt_instrn_engine_wrapper_dfx`
   - `tt_t6_l1_partition_dfx`
   - clock pass-through count와 IJTAG ifdef 여부까지 claim화.

4. **정답지형 merge rule**
   - topic ASCII map을 통합본 §2/§7로 전파.
   - 실명 signal list는 wildcard로 압축하지 않기.
   - `[FROM LLM]`, `[NOT IN KB]`, `[TBC]` provenance를 통합 HDD에도 유지.

5. **dimension resolver regression test**
   - `de_to_t6_coloumn[SizeX][SizeY-1][2]` 같은 multi-dim array를 golden test로 고정.
   - `SizeX == SizeY-1 == 4`처럼 값이 우연히 같아도 symbolic dimension을 보존해야 한다.

---

## 10. 버전 흐름 정리

| 버전 | 핵심 변화 | 점수 (통합본, Codex 기준) | 성격 |
|---|---|---:|---|
| v8 | max_results 50, port 전체 노출 | ~68% | visibility 극대화 |
| v9 | Hybrid tag + 6-file split | ~67% | 측정 인프라 도입, merge 회귀 |
| v9.1 | dedup + 실명 노출 + KB coverage | ~57% Codex / folder ~70% | 회귀 치유 |
| v9.2 | EP/dispatch/flit/clock 구조 회수 | ~68~70% | 구조 이해 도약 |
| **v9.3** | **Port Binding + CDC + EDC/Overlay 보강** | **~72~74%** | **graph evidence 도입 초기** |
| v9.4 목표 | CONNECTS_TO path 본문 반영 + DFX + 실명 복구 | 80%+ 가능 | semantic graph retrieval |

---

*End of Review — Codex Review v9.3 (2026-05-12)*
