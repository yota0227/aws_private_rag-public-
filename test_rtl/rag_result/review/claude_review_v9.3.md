# Claude Review — RAG v9.3 산출물 vs 정답지

**리뷰 일자:** 2026-05-12
**리뷰어:** Claude (Opus 4.7)
**대상 산출물:** `test_rtl/rag_result/v9.3/` (6개 문서)
**정답지:** `test_rtl/Sample/ORG/` (N1B0_NPU_HDD_v0.1.md, EDC_HDD_V0.3.md, overlay_HDD_v0.3.md 등)

---

## 0. 한줄 평가

**v9.3는 "구조는 정확, 디테일은 여전히 공백"** — EP Table·Port Binding·Wire Topology 등 RTL 그래프에서 뽑히는 사실 데이터는 거의 완벽히 재현하는데, 정답지에 있는 **알고리즘적 설명·파라미터 값·물리적 수치·SW 프로그래밍 가이드**는 대부분 비어있거나 [FROM LLM]으로 추정한 수준. v9.2 대비 **Port Binding 확장이 실제 data point를 늘린 건 확인**했지만 KB 자체의 knowledge depth 한계가 본질적 병목.

---

## 1. 산출물 인벤토리

| 파일 | 타입 | 길이(줄) | 정답지 매핑 |
|------|------|---------|------------|
| `v9.3_chip_grounded.md` | Chip HDD (Hybrid Grounding) | 355 | N1B0_NPU_HDD_v0.1.md |
| `v9.3_chip_no_grounding.md` | Chip HDD (KB only) | 216 | N1B0_NPU_HDD_v0.1.md |
| `v9.3_N1B0_HDD.md` | Integrated HDD | 492 | N1B0_NPU_HDD_v0.1.md |
| `v9.3_edc.md` | EDC Topic HDD | 252 | EDC_HDD_V0.3.md |
| `v9.3_noc.md` | NoC Topic HDD | 179 | Router_Address_Decoding_HDD.md + NIU_HDD_v0.1.md |
| `v9.3_overlay.md` | Overlay Topic HDD | 221 | overlay_HDD_v0.3.md |

정답지 분량 대비 산출물 분량 비율:
- N1B0_NPU_HDD: 1291줄 → v9.3 492줄 (**38%**)
- EDC_HDD_V0.3: 1000+줄 추정 → v9.3 252줄 (**25% 이하**)
- overlay_HDD_v0.3: 500+줄 추정 → v9.3 221줄 (**40%**)

---

## 2. 섹션별 정확도 (N1B0 Chip HDD 기준)

### ✅ 2.1 Package Constants & EP Table — **정답 수준**

| 항목 | v9.3 | 정답지 | 판정 |
|------|------|-------|------|
| SizeX/SizeY/NumNodes | 4/5/20 | 4/5/20 | ✅ |
| NumTensix | 12 | 12 | ✅ |
| EnableDynamicRouting | 1'b1 | 1 | ✅ |
| EP Table (20개 모든 항목) | 완전 | 완전 | ✅ |
| tile_t enum 8개 | 정확한 나열 | 동일 | ✅ |
| Helper functions | getTensixIndex 등 나열 | 동일 + 반환값 설명 | ⚠️ (함수는 맞지만 반환값 부연 없음) |

**우수.** v9.2 EP Table이 v9.3에서도 그대로 유지되며 RAG의 근간 데이터로 기능함이 확인됨.

### ✅ 2.2 Top-Level Ports — **카운트 맞음, 세부 부족**

- v9.3: "106 total ports" + 카테고리별 집계 (AXI 39, NoC 2, AI 2, ...)
- 정답지: 카테고리별 + **각 포트의 폭·용도·N1B0 고유 변경점 (AI per-column, ISO_EN[11:0], PRTN 10개 등) 세부**

**Gap:**
- `AXI_SLV_OUTSTANDING_READS=64` 등 AXI 파라미터 3개 **누락**
- `awuser/aruser` 내부 `noc2axi_tlbs_a_regmap_t` 구조체 **누락**
- PRTN 10개 포트의 실제 신호명 (`PRTNUN_FC2UN_DATA_IN` 등) **누락**
- `[3:0]`/`[11:0]`/`[13:0][7:0]` 등 **비트 배열 차원 일부만 맞음**

### ⚠️ 2.3 Module Hierarchy — **레벨-1은 맞으나 내부 계층 얕음**

- v9.3: `trinity → {tt_tensix_with_l1 ×12, tt_dispatch_top_*, NoC modules, NIU modules, ...}` 1-2 레벨만
- 정답지: Tensix → overlay_noc_wrap → overlay_noc_niu_router → neo_overlay_wrapper → overlay_wrapper → {clock_reset_ctrl, cpu_wrapper → DigitalTop → RocketTile[*], memory_wrapper → L1 partition → ..., edc_wrapper, tt_instrn_engine_wrapper → ...} **5-6 레벨 완전 전개**

**Gap의 원인:** RAG KB의 module_parse claim이 인스턴스명-모듈명 쌍만 뽑아주고, 내부 instantiation tree를 traversal하는 기능이 약함. v9.3 Port Binding은 최상위 trinity의 포트 바인딩만 잡았을 뿐 내부 계층까지 내려가지 못함.

### ⚠️ 2.4 Compute Tile (Tensix) — **FPU 파라미터는 정확, 서브시스템 설명은 공백**

| 항목 | v9.3 | 정답지 |
|------|------|-------|
| FPU 모듈명/파라미터 | tt_fp_int_rnd IN_PREC=9, tt_multiop_adder WIDTH=9 등 | 동일 |
| TRISC/BRISC 4-core 구조 | [FROM LLM] 한 줄 | BRISC + TRISC0/1/2 역할 분담, Rocket 파이프라인 5-stage, 스레드 assignment 상세 |
| G-Tile vs M-Tile 구조 | 언급 없음 | **"2×G-Tile × 8 lanes = 16 lanes/tile", Booth mult + Wallace compressor** |
| DEST/SRCB 레지스터 파일 | [FROM LLM] 한 줄 | **4096×16 latch array, tt_clkgater ICG, MOVD2A path** |
| 숫자 포맷 14개 | 언급 없음 | BF16/FP16/FP8E4M3/FP8E5M2/TF32/INT32 등 **14개 나열** |
| Stochastic rounding | 언급 없음 | Galois LFSR 32b 설명 |
| SFPU 함수 목록 | 이름만 | EXP/LOG/SQRT/RECIP/GELU/SIGMOID/TANH/RELU 등 **8+개 나열** |

**Gap의 본질:** 이건 RTL 파서로 뽑을 수 있는 영역이 아니라 **설계 지식(spec/docs)에서 와야 함**. Spec RAG가 붙어야 해결될 부분.

### ⚠️ 2.5 Dispatch Engine — **Wire 정확, 내부 구조 공백**

- v9.3: Wire Topology 6개 완벽 (de_to_t6_column/east/west, t6_to_de/accross_east/accross_west) ✅
- v9.3 `[FROM LLM]`: East가 0-1 columns, West가 2-3 columns 담당 — **틀림**
  - 정답지: DISPATCH_E는 X=3(Y=3) / DISPATCH_W는 X=0(Y=3) — 즉 "East=X=3, West=X=0" 기준
  - v9.3는 "East=columns 0-1"라고 거꾸로 썼음 ❌
- Dispatch 내부 계층 (tt_dispatch_engine → tt_disp_eng_l1_partition, overlay_noc_wrap_inst → disp_eng_overlay_noc_niu_router → tt_disp_eng_overlay_wrapper, ATT SRAMs 1024×12 + 32×1024) **누락**
- Auto-dispatch FIFO, FDS 역할 **누락**

### ⚠️ 2.6 NoC Fabric — **Port Binding은 우수, 구조·VC는 공백**

| 항목 | v9.3 | 정답지 |
|------|------|-------|
| 라우팅 알고리즘 이름 | DIM_ORDER/TENDRIL/DYNAMIC | DOR/Tendril/Dynamic routing |
| DOR "X first, then Y" | ✅ | ✅ |
| Tendril "2-hop indirect" | [FROM LLM] 한 줄 | 동일 |
| Dynamic routing bit width | 언급 없음 | **928-bit carried list, 16 slots × 58 bits {x,y,EP,force_dim[2:0]}** |
| Flit 4D wiring [4][5][2][2] | ✅ | ✅ |
| Flit header 필드 | [FROM LLM] 5개 | `noc_header_address_t` 128b 완전 나열 + path_squash, flit_type[2:0] enum 6값 |
| AXI 56b gasket | 필드만 나열, 비트 경계 [TBC] | **[55:52]/[51:48]/[47:40]/[39:36]/[35:0] 모두 명시** |
| X-axis repeater (N1B0 수동) | Y=3/Y=4 언급 | **Y=3 6-stage, Y=4 4-stage ×2 (E↔W) 명시** |
| VC 입력 버퍼 | 언급 없음 | **mem_wrap_72×2048 (N1B0), per-direction (N/E/S/W)** |

**v9.3 Port Binding 성과:** NOC2AXI_ROUTER clock/EP 연결은 정답지와 동일 수준으로 잘 추출됨. 이 부분은 **v9.2 → v9.3 업그레이드의 실질 가치가 검증된** 영역.

### ⚠️ 2.7 NIU — **인스턴스 카운트는 맞음, AXI/ATT는 공백**

- v9.3: 4 인스턴스 위치 (EP 4/9/14/19) ✅, Port Binding 매핑 ✅
- 정답지의 추가 정보 **누락**:
  - Corner NIU (NE_OPT/NW_OPT) vs 복합 타일 (ROUTER_NE/NW_OPT)의 **2-row span 구조**
  - Cross-row internal wires (`router_i_flit_in_req_north = noc2axi_o_flit_out_req_south`)
  - ID offset applied to router (`i_local_nodeid_y - 1`, `i_noc_endpoint_id - 1`)
  - Router parameter 6개 (`REP_DEPTH_LOOPBACK=6`, `REP_DEPTH_OUTPUT=4` 등)
  - AXI geometry (data 512b, addr 56b, AW/W/B/AR/R 채널)
  - RDATA FIFO depth 32-1024 configurable, N1B0 default=512
  - ATT: 1024×12 endpoint SRAM + 32×1024 routing SRAM
  - SMN: 8 programmable ranges per NIU, {base, mask, allow_mask, deny_mask}

### ⚠️ 2.8 Clock Architecture — **도메인 구조 맞음, trinity_clock_routing_t 부정확**

v9.3: `trinity_clock_routing_t` 8 fields로 기술
- 정답지: **9 fields** (ai_clk, noc_clk, dm_clk, ai_clk_reset_n, noc_clk_reset_n, **dm_uncore_clk_reset_n[SizeY-1:0], dm_core_clk_reset_n[SizeY-1:0][DMCoresPerCluster-1:0], tensix_reset_n[SizeY-1:0]**, power_good)

v9.3 기술 (줄 86): "8 fields" + `tensix_reset_n` 단일 신호처럼 나열 → **정답은 `[SizeY-1:0]` 배열**
→ **Struct 필드 개수와 패킹된 배열 차원 둘 다 잘못 추출됨**

CDC 테이블:
- v9.3 3개 (NoC↔gated_noc, NoC↔core, NoC↔uncore) — 정확하지만
- 정답지: Tensix 내부 CDC 8개 (TDMA L1→NoC ack, NoC flit→L1 write, FDS timer→flit inject, FDS input filter, reset sync noc/ai, JTAG→internal, SMN interrupt) **완전히 다른 층위의 상세함**

### ⚠️ 2.9 Reset Architecture — **포트만 맞음**

- v9.3: 6개 reset 포트 나열 + "all active-low (_n suffix)" 한 줄 ✅
- 정답지:
  - Reset tree (어떤 reset이 어디로 가는지 분기 트리)
  - Reset synchronizer (`tt_libcell_sync3r` 3-stage, SDC MCP setup=4 hold=3)
  - Harvest reset sequence (tensix_reset_n + ISO_EN)
  - `clock_routing_in[x][4].tensix_reset_n[4-y] = i_tensix_reset_n[getTensixIndex(x,y)]` 같은 **정확한 packing 식**

### ✅ 2.10 EDC (Topic HDD 별도 파일) — **링 구조 맞음, Node ID 인코딩 틀림**

| 항목 | v9.3 | 정답지 |
|------|------|-------|
| U-shape ring 토폴로지 | ✅ | ✅ |
| Toggle handshake (req_tgl/ack_tgl) | ✅ | ✅ |
| 16-bit data + parity | ✅ | ✅ |
| BIU APB4 slave | ✅ | ✅ |
| 5 IRQ 라인 | ✅ (fatal, critical, correctable, pkt_sent, pkt_rcvd) | ✅ |
| Node ID 3-field 구조 | `node_id_part/subp/inst` 언급, 비트폭 [TBC] | **part[4:0] + subp[2:0] + inst[7:0] = 16b** |
| Per-column ring (4 rings) | 언급 없음 (single ring처럼 서술) | **각 column이 독립 EDC ring** ❗ |
| Harvest bypass 구체 모듈 | `edc_mux_demux_sel` 언급만 | **tt_edc1_serial_bus_mux / tt_edc1_serial_bus_demux + edc_egress_t6_byp_intf** 구체 와이어명 |
| Composite tile 2 EDC nodes | 언급 없음 | **NOC2AXI_ROUTER에 Y=4 node + Y=3 node = 2 노드/모듈** |
| Harvest boot sequence | 언급 없음 | eFuse → boot ROM → `edc_mux_demux_sel[x][y]` 정적 설정, 재부팅 전까지 고정 |
| MAX_FRGS | [TBC] | **MAX_FRGS=12** |
| SUPER/MAJOR/MINOR 버전 | 언급 없음 | **SUPER=1, MAJOR=1, MINOR=0** |

**가장 큰 오류:** v9.3는 "1 ring for chip"처럼 서술했는데 정답은 "**4 rings, one per column, independent**". 이건 SW programming·harvest 모델에 본질적 영향.

### ⚠️ 2.11 Overlay (Topic HDD 별도 파일)

| 항목 | v9.3 | 정답지 |
|------|------|-------|
| 8 cores per DM complex | ✅ (DMCoresPerCluster=8) | 정답지에서는 **8× RISC-V per tile** (per-tile, not per-complex) |
| NumDmComplexes=14 | ✅ | ✅ |
| iDMA 6 protocols | ✅ AXI/OBI/AXILITE/TILELINK/INIT/AXI_STREAM | ✅ |
| TileLink TL-C | [FROM LLM] | ✅ |
| L1 bank ×16 | 언급 없음 | **16 banks × 3072×128 (N1B0)**, 768 KB/tile, **9.216 MB total** |
| 4 context-switch SRAMs | 언급 없음 | 32×1024 + 8×1024 |
| FDS port counts | ✅ (tensixneo 106/41, dispatch 68/41) | 동일 |
| Cluster ctrl CSR | ✅ (38/97) | 동일 |
| Dispatch overlay (IS_DISPATCH=1, HAS_SMN_INST=0) | 언급 없음 | 정답지에 명시 |

**Grid placement 혼선:**
- v9.3 `v9.3_overlay.md` §2: 정답지의 `Y=0=NOC2AXI, Y=1-4=TENSIX` 배치를 그대로 따왔는데, **N1B0 실제 배치는 `Y=4=NOC2AXI, Y=0-2=TENSIX`** (EP table 기준).
- 즉 정답지 overlay_HDD_v0.3.md 자체가 **baseline Trinity 기준** (Y=0 top)이고, N1B0_NPU_HDD_v0.1.md는 **N1B0 기준** (Y=4 top)이어서, v9.3이 두 좌표계를 혼용함. RAG 문제라기보다 정답지 불일치가 전파된 것.

---

## 3. v9.3 신규 기능의 실질 가치 (v9.2 → v9.3 delta)

| v9.3 신규 기능 | KB에 데이터 추출 성공? | 산출물 반영 | 정답지 대비 가치 |
|----------------|-------------------|-------------|-----------------|
| **Port Binding Parser** | ✅ (8개 binding 추출) | ✅ (NoC/NIU 섹션) | **High** — 정답지의 "clock/EP wiring" 정보를 RTL 그래프에서 직접 추출. 이건 v9.2엔 없었던 영역. |
| **Neptune CONNECTS_TO edges** | ✅ (Graph Export API 언급) | ⚠️ (명시적 활용은 없음) | **Medium** — 산출물에서 "어떤 신호가 어디로 간다"는 trace 결과가 거의 보이지 않음. API는 있는데 HDD 생성 프롬프트가 활용 안 함. |
| **always_block_parser CDC** | ✅ (3 boundary 추출) | ✅ (Clock §9.3) | **Medium** — 정답지 대비 턱없이 얕지만 (정답 8개 vs v9.3 3개), 없던 게 생긴 건 맞음. |
| **Graph Export API** | 메타데이터로만 언급 | ❌ | **Low** — HDD 생성 툴이 아직 API를 consume하지 않음. 파이프라인 다음 단계 과제. |

**결론:** v9.2 대비 **"Port Binding 섹션"이 추가된 것이 가장 실질적인 진전.** CDC와 Neptune은 infra는 깔렸으나 HDD 생성 프롬프트가 그 value를 아직 뽑아내지 못함.

---

## 4. 치명적 오류 (팩트가 틀린 곳)

아래는 정답지와 **반대되거나 잘못된** 진술:

| 위치 | v9.3 진술 | 정답 |
|------|----------|------|
| `v9.3_chip_grounded.md` §6 | "East dispatch handles columns 0-1, West dispatch handles columns 2-3" [FROM LLM] | **East=X=3(Y=3), West=X=0(Y=3)** — LLM 추정이 거꾸로. |
| `v9.3_edc.md` §3.1 ASCII diagram | Y=4 row에 `NIU_NE / NIU_RNE / NIU_RNW / NIU_NW` + "Segment B upward return" 단일 링처럼 | **각 column이 독립 ring** — per-column U-turn. 다이어그램이 전체 chip 1 ring으로 오도. |
| `v9.3_chip_grounded.md` §2.5, `v9.3_N1B0_HDD.md` §2.5 | `trinity_clock_routing_t` (8 fields) | **9 fields**, 그리고 `tensix_reset_n[SizeY-1:0]` 등 **배열**. 단일 신호로 썼음. |
| `v9.3_overlay.md` §2 diagram | Y=0이 NOC2AXI, Y=1-4가 TENSIX | N1B0 EP Table과 반대 좌표계. |

---

## 5. 빠진 영역 (정답지에만 있는 항목)

정답지에 있는데 v9.3 전 문서에 **흔적도 없는** 주요 섹션:

- **P&R / Physical guide** (§15): Synthesis partitions 15개, Tensix tile floorplan (top-to-bottom 10단 층), critical placement rules, CDC crossings 8개, SDC path groups
- **SW Programming Guide** (§16): APB address map, EDC CSR programming, harvest configuration 5-step sequence, NoC routing configuration, AXI interface 사용법, TRISC/BRISC C code 예시, SFR 목록, perf monitor/delay buffer 시뮬 가이드
- **N1B0 vs Baseline 차이표** (§1.1): 10개 feature difference
- **L1 용량 수치**: 16 banks × 3072×128 = 768 KB/tile → **9.216 MB NPU-local L1**
- **12,288 DEST latch instances** 같은 full chip 집계 수치
- **SRAM Inventory 상세 테이블**: 8 종류 매크로 (RA1_UHD/HS, RF1_UHD, RF2_HS, RD2_UHD, VROM_HD)와 per-tile count × 12 tiles 총계
- **DFX 4개 모듈 pass-through 구조 + IJTAG chain**
- **Reference HDDs 크로스 레퍼런스 표** (9개 subdocument 링크)

---

## 6. 정량 스코어카드

| 평가 축 | 점수 (100) | 근거 |
|--------|-----------|------|
| RTL-extractable structural fact (EP, ports, wires, hierarchy L1) | **85** | Port Binding으로 향상. 계층 L2+ 깊이는 부족. |
| Parameter extraction (FPU params, bit widths) | **60** | FPU 파라미터는 추출, AXI/Router 파라미터 누락. |
| Topology / physical layout | **35** | Grid은 맞으나 N1B0 고유 repeater stage count, 좌표계 혼동. |
| Algorithm / protocol spec (VC, routing carried list, EDC Node ID, PRTN) | **25** | 전반적으로 [TBC] 또는 [FROM LLM] 추정 수준. |
| SW programming / firmware guide | **5** | 거의 전무. |
| 수치적 정확성 (L1 KB, latch count, FIFO depth) | **10** | 대부분 누락. |
| 정답 대비 치명적 오류 개수 | **4건** | East/West, EDC 링 구조, clock_routing 필드, overlay 좌표계. |
| **전체 가중 평균 (structural 40% + parametric 20% + algo 20% + SW 10% + 수치 10%)** | **≈ 48/100** | **"KB가 구조는 알지만 설계 knowledge는 모른다"** 수준. |

---

## 7. v9.4를 위한 우선순위 권고

### P0 (즉시)
1. **Dispatch East/West column 매핑 수정** — 현재 [FROM LLM] 추정이 역방향. Port Binding으로 EP3/EP18의 X 좌표를 claim으로 고정해 프롬프트에 주입.
2. **trinity_clock_routing_t 9 fields로 정정** — struct 파싱에서 배열 차원 인식 버그. `wire_declaration_parser` 확장으로 struct field의 packed dimension을 추출해야 함.
3. **EDC per-column ring 모델 반영** — "1 chip = 4 independent rings" 사실을 KB claim으로 추가. 이건 harvest 모델에도 영향.

### P1 (v9.4 이내)
4. **Module hierarchy L2-L5 확장** — `tt_tensix_with_l1 → tt_overlay_noc_wrap → ... → tt_overlay_wrapper` 까지 재귀 traversal. 현재는 L1만.
5. **Router/NIU 내부 파라미터 claim 추가** — `REP_DEPTH_LOOPBACK`, `REP_DEPTH_OUTPUT`, `NUM_REPEATERS_*_WEST/EAST/NORTH/SOUTH` 6개. 이미 v9.2 package_parser가 있으므로 확장 쉬움.
6. **Composite tile 2-row span 표현** — NOC2AXI_ROUTER가 Y=4+Y=3 걸친다는 사실을 EP Table claim에 확장 필드로.

### P2 (중장기, Spec RAG와 연계)
7. **Algorithm description은 Spec RAG로 위임** — dynamic routing 928-bit carried list, Tendril 2-hop, Stochastic rounding LFSR 등은 RTL에서 뽑을 수 있는 게 아님. v10 Spec RAG와 크로스 임베딩 필요.
8. **SW Programming Guide는 템플릿화** — APB map, harvest sequence는 구조화된 메타데이터에서 자동 생성 가능하게 프롬프트 설계.
9. **수치 집계 post-process** — L1 KB, latch count 같은 총계는 RTL 파서가 count × dimension × instance 곱셈으로 post-process 가능.

---

## 8. 메모 (다음 대화에 유용할 정보)

- **v9.3 Port Binding은 "실제 가치"를 처음 증명한 feature.** NE_OPT / NW_OPT의 `i_noc_endpoint_id = EndpointIndex`, `i_axiclk = i_axi_clk` 바인딩 8개는 정답지와 완전히 일치. 이 방향으로 더 깊게 파면 RTL-grounded HDD는 더 풍부해짐.
- **Hybrid Grounding tag 전략은 잘 작동함.** `[FROM LLM]`/`[NOT IN KB]`/`[TBC]` 구분 덕에 리뷰어가 어디를 의심해야 할지 바로 보임. 이 UX는 v10 이후에도 유지 권장.
- **정답지 자체의 불일치가 RAG 출력에 전파됨** (overlay 좌표계 Y=0 vs Y=4). Spec/HDD 정답지 정규화가 v9.4 선행 조건.
- **분량 비율 (25-40%)이 곧 "coverage"가 아님.** v9.3가 RTL-extractable은 80%+ 맞추지만, 정답지 문서 자체가 50% 이상 설계 지식/SW 가이드로 구성되어 있음. → **RAG만으로는 논리적으로 도달 불가능한 천장**이 있음.

---

*End of Review — Claude (Opus 4.7), 2026-05-12*
