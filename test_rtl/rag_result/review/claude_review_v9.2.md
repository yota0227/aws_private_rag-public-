# v9.2 Review — 정답지 비교 + v9.1 → v9.2 진화 분석

**Review Date:** 2026-05-08
**Reviewer:** Claude (Opus 4.7)
**Scope:** [test_rtl/rag_result/v9.2/](../v9.2/) 6개 문서 vs [test_rtl/Sample/ORG/](../../Sample/ORG/) 정답지
**Progression:** v9 (Hybrid 태그 + 6-file split) → v9.1 (dedup + SFR/DFX 회귀 복구 + 실명 노출 + KB Coverage 89%) → **v9.2 (EP Index Table + Dispatch/Flit/Clock wiring 구조화 + AXI 56b gasket 신규)**
**Cross-Reference:** [claude_review_v9.md](claude_review_v9.md), [claude_review_v9.1.md](claude_review_v9.1.md)

---

## 0. TL;DR

| Dim | v9.1 | v9.2 | Δ | 비고 |
|-----|------|------|----|------|
| **Top-Level Port Coverage** | 106/106 (100%) | 106/106 (100%) | — | 유지 |
| **EP Index Table 20행 전체** | ❌ | ✅ **20행 완전 테이블** ([v9.2_N1B0_HDD §2.3](../v9.2/v9.2_N1B0_HDD.md#L63), [v9.2_chip_no_grounding §2.3](../v9.2/v9.2_chip_no_grounding.md#L63)) | **신규 성과** | 정답지 §2.3과 **100% 일치** |
| **Dispatch feedthrough wiring 6종** | ❌ | ✅ **`de_to_t6_coloumn/east/west + t6_to_de/accross_east/west`** ([v9.2_chip_no_grounding §6.1](../v9.2/v9.2_chip_no_grounding.md#L204)) | **신규 성과** | 정답지 §6 접근 |
| **Flit Wiring 4D Array** | ❌ (요약) | ✅ **`flit_in/out_req/resp: [4][5][2][2]`** 4D 명시 ([v9.2_chip_no_grounding §7.3](../v9.2/v9.2_chip_no_grounding.md#L239)) | **신규** | 정답지 §7.2 근접 |
| **AXI 56b Gasket 구조** | ❌ | ✅ **target_index/endpoint_id/tlb_index/address 4필드** ([v9.2_noc §4](../v9.2/v9.2_noc.md#L57)) | **신규** | 정답지 §7.3 부분 접근 |
| **Clock Routing 4×5 Array** | ❌ | ✅ **`[SizeX-1:0][SizeY-1:0] = 4×5 mesh`** ([v9.2_chip_no_grounding §9.1](../v9.2/v9.2_chip_no_grounding.md#L272)) | **신규** | 정답지 §9.2-9.3 근접 |
| **L1 EDC Daisy-Chain 4종** | ❌ | ✅ **`gen_l1_dcache/icache_tag/data_edc`** 4 generate blocks ([v9.2_N1B0_HDD §11.3](../v9.2/v9.2_N1B0_HDD.md#L313)) | **신규** | overlay_HDD §6.10 접근 |
| **noc_header_address_t 필드** | ❌ | ✅ **x_dest/y_dest/endpoint_id/flit_type/dynamic_carried_list** ([v9.2_noc §3.2](../v9.2/v9.2_noc.md#L46)) | **신규** | 정답지 §7.3 flit header 부분 |
| **SFR 17 신호명 실명** | ✅ 전체 | 🟡 **와일드카드 요약** (`SFR_RF_2P_HSC_*, SFR_RA1_HS_*...`) | **회귀** | v9.1의 실명 노출이 압축됨 |
| **PRTN 14 신호명 실명** | ✅ 전체 | 🟡 **와일드카드 요약** (`PRTNUN_FC2UN_*, PRTNUN_UN2FC_*`) | **회귀** | v9.1의 실명 노출이 압축됨 |
| **Instruction Engine 6-sub 섹션** | ✅ §5.4 테이블 | 🟡 DFX §14에 4항목만 | **일부 회귀** | 통합본에서 `tt_instrn_engine` 섹션 삭제 |
| **KB Coverage 정량 매트릭스** | ✅ 118/132 = **89%** | ❌ **정성 매트릭스 회귀** | **회귀** | 분모/분자 숫자 사라짐 |
| **Grounding 컬럼 표준화** | ✅ 전체 테이블 | 🟡 **일부 테이블만** | **회귀** | 표준화 해제, 범례만 유지 |
| **정답지 대비 (가중 추정)** | ~74% | **~74%** | **±0pp** | **구조 개선 vs 실명 회귀 맞교환** |
| **환각** | 없음 | 없음 | — | 유지 |

**한 줄 결론:** v9.2는 **"구조적 신규성 대도약 vs 실명 노출 일부 회귀의 맞교환"**. 신규 성과(EP Index 20행, Dispatch wiring 6종, Flit 4D array, AXI 56b gasket, Clock 4×5 mesh, L1 EDC daisy-chain)는 **정답지의 "구조 정보" 커버리지를 크게 끌어올림** — 특히 Dispatch(+20pp)와 NoC(+10pp)는 버전간 역대 최대 폭 개선. 그러나 v9.1이 이룩한 **"카운트→실명" 도약의 일부(SFR/PRTN)가 와일드카드 요약으로 압축**됐고 **KB Coverage 정량 매트릭스(89%)와 Grounding 컬럼 표준화가 회귀**. 가중 총점은 **74% 보합**이지만 질적 성격이 바뀜: **v9.1 = DV 엔지니어 실사용 / v9.2 = 아키텍트 설계 이해**. v9.1의 권고 2건 중 "EP 계산 로직"·"noc_pkg 파서"는 반영, **"DFX 4-node wrapper chain"은 여전히 미반영** — 이는 v9.2→v9.3(또는 v10) 최우선 과제로 이월.

---

## 1. v9.2 파일 구성 개관

| 파일 | 역할 | 주요 변화 vs v9.1 |
|------|------|----------------|
| [v9.2_N1B0_HDD.md](../v9.2/v9.2_N1B0_HDD.md) (407줄) | **통합 HDD** | **v9.1 331줄 → v9.2 407줄 (+76줄)**, §2.3 EP 테이블, §6.1 dispatch wiring, §7.2 flit wiring, §9.1 clock mesh, §11.3 L1 EDC 신설 |
| [v9.2_chip_grounded.md](../v9.2/v9.2_chip_grounded.md) (285줄) | Hybrid 그라운딩 | **v9.1 389줄 → v9.2 285줄 (-104줄)** — 상당한 축소. Grounding 컬럼 표준화와 KB Coverage 수치 사라짐 |
| [v9.2_chip_no_grounding.md](../v9.2/v9.2_chip_no_grounding.md) (377줄) | Raw RAG | **v9.1 358줄 → v9.2 377줄 (+19줄)**. 실명 나열 일부 와일드카드로 교체 |
| [v9.2_edc.md](../v9.2/v9.2_edc.md) (150줄) | EDC topic | 비슷. APB 포트 18종 테이블·IRQ 5종 유지 |
| [v9.2_noc.md](../v9.2/v9.2_noc.md) (152줄) | NoC topic | **§3.2 noc_header_address_t 필드 5종, §4 AXI 56b gasket, §8 4×5 EP map, §10 related packages 신규** |
| [v9.2_overlay.md](../v9.2/v9.2_overlay.md) (153줄) | Overlay topic | **§4.3 L1 EDC daisy-chain 4 generate blocks 신설, §5.3 iDMA 6-protocol 확장** |

**구조적 변화:**
- 신규 문서는 없고 **v9.1과 동일한 6-file 구성 유지**
- [v9.2_chip_grounded.md](../v9.2/v9.2_chip_grounded.md)의 **Grounding 컬럼이 표준화에서 선택적으로 회귀** — 대신 grounding legend (§0)과 KB Coverage Matrix (§마지막)는 유지되나 정량 숫자(89%)가 정성 등급으로 바뀜
- 통합 [v9.2_N1B0_HDD.md](../v9.2/v9.2_N1B0_HDD.md)가 **Appendix: Source Tracking** 섹션 신설 — 섹션별 소스 문서 명시 (v9.2 개선점)

---

## 2. v9.2 vs 정답지 상세 비교

### 2.1 Chip-level: [v9.2_N1B0_HDD.md](../v9.2/v9.2_N1B0_HDD.md) (407줄) vs [N1B0_NPU_HDD_v0.1.md](../../Sample/ORG/N1B0_NPU_HDD_v0.1.md) (1290줄)

| 섹션 | 정답지 | v9 | v9.1 | **v9.2** | Δ vs v9.1 | 근거 |
|------|--------|-----|-----|----|----------|------|
| 1. Overview | 4×5 mesh + N1B0 차이 테이블 + ASCII | 65% | 70% | **72%** | +2pp | "14 DM complexes, TensixPerCluster=4, DMCoresPerCluster=8" 등 세분화 |
| 2. Package Constants | 13 localparam + tile_t 2-variant + EP 20행 | 65% | 90% | **95%** | **+5pp** | **EP Index 20행 완전 테이블 신규 (정답지 §2.3과 100% 일치)** |
| 3. Top-Level Ports | 7 서브섹션 실명 | 90% | 95% | **80%** | **-15pp** | **SFR 17 / PRTN 14 실명 → 와일드카드 요약 회귀** |
| 4. Module Hierarchy | 3-level generate + Instrn Engine 6-sub | 65% | 80% | **70%** | **-10pp** | `tt_instrn_engine` 6-sub 테이블이 통합본에서 삭제됨 (DFX §14 4항목만 잔존) |
| 5. Compute Tile (Tensix) | FPU/SFPU/TDMA/L1/DEST/SRCB/TRISC/BRISC | 30% | 40% | **42%** | +2pp | L1 Cache 5-모듈 테이블 신설 (tt_t6_l1_wrap2/pipe/superarb/rr_arb_tree/latch_reg_array) |
| 6. Dispatch | 3-level + FDS 상세 + feedthrough | 15% | 20% | **40%** | **+20pp** | **`de_to_t6_coloumn/east/west` + `t6_to_de/accross_east/west` 6 wire 차원 완전 노출** |
| 7. NoC | DOR + flit 4D + gasket + 928-bit | 35% | 50% | **60%** | **+10pp** | **Flit 4D (4×5×2×2) + 56b gasket 4필드 + 4×5 EP map ASCII (통합본) + noc_header_address_t** |
| 8. NIU | Corner vs Composite | 25% | 35% | 35% | — | 유지 (N1B0 composite dual-row 구조는 미접근) |
| 9. Clock | clock_routing_t + per-column | 80% | 80% | **85%** | +5pp | **`clock_routing_in/out [4][5]` 4×5 mesh 명시 신규** |
| 10. Reset | dm_core/uncore 상세 | 70% | 75% | 75% | — | `i_dm_core_reset_n[14][8]` 차원 유지 |
| 11. Power Management | PRTN + ISO_EN per-signal | 85% | 85% | **75%** | -10pp | PRTN 14신호 → "PRTNUN_FC2UN_* / PRTNUN_UN2FC_*" 와일드카드 |
| 12. EDC | modport + BIU + 5 IRQ + ring | 90% | 95% | **92%** | -3pp | **L1 EDC daisy-chain 4 generate blocks 신규(+)** 하지만 **DFX 5항목 → 4항목 축소(-)** |
| 13. SRAM | L1+VC+ATT 전체 | 30% | 45% | **40%** | -5pp | 섹션이 v9.1 대비 간결화, 4-family 명시는 유지하나 상세 축소 |
| 14. DFX | 4 모듈 + iJTAG + scan chain topology | 15% | 40% | **30%** | **-10pp** | tile-level 4항목만. **4-node wrapper chain은 여전히 누락 (v9.1 권고 미반영)** |

**가중 점수 추정:** v9.1 ~74% → **v9.2 ~74%** (±0pp, 구조 개선과 실명 회귀가 상쇄)

### 2.2 v9.2 핵심 개선 상세

#### (1) 🔥 EP Index Table 20행 완전 테이블 — 정답지와 100% 일치

v9.1까지는 "EP 인덱스 계산식" (EP = x*5 + y)만 언급되거나 누락됐으나 v9.2에서 완전 복구:

[v9.2_N1B0_HDD §2.3](../v9.2/v9.2_N1B0_HDD.md#L63):

```markdown
| EP | (X,Y) | Type | EP | (X,Y) | Type |
|----|--------|------|----|--------|------|
| 0 | (0,0) | TENSIX | 10 | (2,0) | TENSIX |
...
| 9 | (1,4) | NOC2AXI_ROUTER_NE_OPT | 19 | (3,4) | NOC2AXI_NW_OPT |
```

**의의:**
- 정답지 [N1B0_NPU_HDD §2.3](../../Sample/ORG/N1B0_NPU_HDD_v0.1.md)의 EP 테이블과 **행별 정확히 일치** (ROUTER EP=8/13, DISPATCH EP=3/18, NOC2AXI_ROUTER_NE/NW_OPT=9/14 포함)
- v9.1 리뷰 §5.2-(4) 권고 **"EP 인덱스 계산 로직 → 20행 자동 생성"** 완전 반영
- `getTensixIndex/getNoc2AxiIndex/getApbIndex/getDmIndex/isEastEdge/isNorthEdge` 6-함수도 §2.4에 목록화 (v9.1은 2개만)

**부가 성과:** "ROUTER at (1,3)/(2,3)이 placeholder로 EP=8/13을 소비하고 실제 router logic은 NOC2AXI_ROUTER_NE/NW_OPT에 embedded"이라는 N1B0의 핵심 변칙이 EP map으로 자연스럽게 드러남.

#### (2) 🔥 Dispatch Feedthrough Wiring 6종 — 정답지 §6 최초 접근

v9.1까지 Dispatch Engine은 "East/West 각 1개" 수준으로만 기술됐으나 v9.2에서 **wire dimension까지 완전 노출**:

[v9.2_chip_no_grounding §6.1](../v9.2/v9.2_chip_no_grounding.md#L204):

| Wire | Type | Dimensions | Purpose |
|------|------|-----------|---------|
| de_to_t6_coloumn | de_to_t6_t | [SizeX][SizeY-1] = 4×4 | Dispatch→Tensix column feedthrough |
| de_to_t6_east/west | de_to_t6_t | [SizeX] = 4 | Dispatch→Tensix east/west |
| t6_to_de | t6_to_de_t | [SizeX][SizeY-2] = 4×3 | Tensix→Dispatch feedthrough |
| t6_to_de_accross_east/west | t6_to_de_t | [SizeX][SizeX] = 4×4 | Tensix→Dispatch cross-column |

**의의:**
- 정답지 [N1B0_NPU_HDD §6.2](../../Sample/ORG/N1B0_NPU_HDD_v0.1.md#L540) "direct point-to-point wires (not NoC) from Dispatch to all Tensix tiles in the same column for control signals"의 **하드웨어 레벨 wire typedef 전체 노출**
- `de_to_t6_t` / `t6_to_de_t` 타입은 정답지 본문에 언급된 "sideband structs"에 해당
- **Dispatch가 NoC와 별개의 전용 control path를 갖는다**는 핵심 아키텍처가 처음으로 RAG 출력에 구조화됨 — `across_east/west`는 N1B0의 dual-dispatch 토폴로지의 직접적 증거

#### (3) 🔥 NoC Flit 4D Array + AXI 56b Gasket 구조 노출

**Flit 4D array** ([v9.2_chip_no_grounding §7.3](../v9.2/v9.2_chip_no_grounding.md#L239) / [v9.2_noc §3.1](../v9.2/v9.2_noc.md#L36)):

| Wire | Type | Dimensions |
|------|------|-----------|
| flit_in_req/resp, flit_out_req/resp | tt_noc_pkg::noc_req_t/resp_t | [SizeX][SizeY][NumDirections][NumAxes] = 4×5×2×2 |

**AXI 56b Gasket** ([v9.2_noc §4](../v9.2/v9.2_noc.md#L57)):
```
56-bit AXI address structure:
- target_index: Target node selection
- endpoint_id: Endpoint within target
- tlb_index: TLB entry selection
- address: Physical address offset
```

**noc_header_address_t 필드** ([v9.2_noc §3.2](../v9.2/v9.2_noc.md#L46)):
- `x_dest, y_dest, endpoint_id, flit_type, dynamic_carried_list`

**의의:**
- 정답지 [§7.3 "AXI address gasket (56-bit)"](../../Sample/ORG/N1B0_NPU_HDD_v0.1.md#L581)의 bit 필드명(4개) **필드 이름 수준 일치** — 다만 정답지의 bit range `[55:52]rsvd / [51:48]target / [47:40]ep / [39:36]tlb / [35:0]addr` 같은 **bit range 수치는 여전히 누락** (Spec RAG 대상)
- **Flit 4D `[SizeX][SizeY][NumDirections][NumAxes]`**는 정답지 §7.2의 "5-port mesh switch (N/S/E/W/NIU)"를 `NumDirections=2, NumAxes=2`로 구조 노출한 것
- v9.1 리뷰 §5.2-(2) 권고 **"noc_pkg.sv 전용 파서 → flit struct, 라우팅 테이블"** 일부 반영 (struct 필드명은 나왔으나 pseudocode/bit range는 미반영)

#### (4) 🔥 Clock Routing 4×5 Mesh Array — 정답지 §9.2-9.3 근접

[v9.2_chip_no_grounding §9.1](../v9.2/v9.2_chip_no_grounding.md#L272):

```
| clock_routing_in | trinity_clock_routing_t | [SizeX-1:0][SizeY-1:0] = 4×5 | Clock distribution input mesh |
| clock_routing_out | trinity_clock_routing_t | [SizeX-1:0][SizeY-1:0] = 4×5 | Clock distribution output mesh |
```

**의의:**
- 정답지 [§9.3](../../Sample/ORG/N1B0_NPU_HDD_v0.1.md#L737) "Arrays: `clock_routing_in[SizeX][SizeY]` and `clock_routing_out[SizeX][SizeY]`"의 **차원 수치까지 정확히 추출**
- v9.1은 struct 필드 8개만 나열했으나 v9.2는 **struct array의 grid dimension까지 명시** → 정답지 §9.3 "Clock Entry and Propagation: tile-by-tile buffer and re-drive"의 뼈대가 드러남

#### (5) 🆕 L1 EDC Daisy-Chain 4 Generate Blocks — Overlay 연계

[v9.2_N1B0_HDD §11.3](../v9.2/v9.2_N1B0_HDD.md#L313):

| Generate Block | Signal | Topology |
|---------------|--------|----------|
| gen_l1_dcache_tag_edc | l1_dcache_tag_edc_egress_intf | daisy-chain |
| gen_l1_dcache_data_edc | l1_dcache_data_edc_egress_intf | daisy-chain |
| gen_l1_icache_tag_edc | l1_icache_tag_edc_egress_intf | daisy-chain |
| gen_l1_icache_data_edc | l1_icache_data_edc_egress_intf | daisy-chain |

**의의:**
- 정답지 [overlay_HDD_v0.3 §6.10](../../Sample/ORG/overlay_HDD_v0.3.md)에 존재하는 "L1 cache EDC 4-type protection" (dcache tag/data, icache tag/data)의 **generate 블록 이름 + egress interface 이름 전체 노출**
- Tensix 내부 L1의 **ECC protection hierarchy**가 RAG 출력에서 처음으로 드러남 — EDC가 NoC 레벨 뿐 아니라 L1 레벨에도 daisy-chain으로 존재함을 증명

#### (6) 🆕 NoC 4×5 EP Map ASCII (통합본 병합)

[v9.2_noc §8](../v9.2/v9.2_noc.md#L100):

```
        X=0              X=1              X=2              X=3
Y=4  NOC2AXI_NE_OPT  NOC2AXI_RTR_NE  NOC2AXI_RTR_NW  NOC2AXI_NW_OPT
      EP=4              EP=9             EP=14            EP=19
Y=3  DISPATCH_E       ROUTER           ROUTER           DISPATCH_W
      EP=3              EP=8             EP=13            EP=18
Y=2  TENSIX           TENSIX           TENSIX           TENSIX
      EP=2              EP=7             EP=12            EP=17
...
```

**의의:**
- v9.1 리뷰 §5.2-(5) 권고 **"NoC ASCII 통합본 merge 규칙"**의 부분 반영 (topic 파일 내 ASCII가 타일명 + EP까지 포함해 완성도 향상)
- 여전히 통합 `v9.2_N1B0_HDD.md`에는 이 ASCII가 누락 — **merge 파이프라인이 topic 파일 ASCII를 통합본에 전파하지 못하는 문제가 재발**. v9.2 §7에 "flit wiring 테이블"만 들어가고 EP map ASCII는 생략됨 (실수 반복)

### 2.3 v9.2 회귀 포인트 상세

#### (A) ⚠️ SFR 17 / PRTN 14 실명 노출 회귀 — v9.1 성과 일부 상실

v9.1 [v9.1_chip_no_grounding §3](../v9.1/v9.1_chip_no_grounding.md#L103):
```
SFR_RF_2P_HSC_QNAPA, SFR_RF_2P_HSC_QNAPB, SFR_RF_2P_HSC_EMAA[2:0],
SFR_RF_2P_HSC_EMAB[2:0], SFR_RF_2P_HSC_EMASA, SFR_RF_2P_HSC_RAWL,
SFR_RF_2P_HSC_RAWLM[1:0], SFR_RA1_HS_MCS[1:0], ... (17개 전체)
```

v9.2 [v9.2_chip_no_grounding §3.1](../v9.2/v9.2_chip_no_grounding.md#L121):
```
| SFR_Memory_Config | 17 | SFR_RF_2P_HSC_*, SFR_RA1_HS_*, SFR_RF1_HS_*, SFR_RF1_HD_* |
| PRTN_Power | 14 | TIEL_DFT_MODESCAN, PRTNUN_FC2UN_*, PRTNUN_UN2FC_*, ISO_EN[11:0] |
```

**회귀 성격:**
- 카운트(17, 14)와 family 분류(RF_2P_HSC/RA1_HS/RF1_HS/RF1_HD)는 유지됐으나 **`QNAPA/QNAPB/EMAA/EMAB/RAWL` 같은 신호별 이름이 모두 사라짐**
- **DV 엔지니어 실사용 관점에서 후퇴** — v9.1에서 확보한 "연결도 직접 검증 가능" 수준이 다시 카운트 단계로 회귀
- **원인 추정:** dedup 파이프라인 또는 summarization 강화 과정에서 "신호명 중복 제거" 오판으로 추정. v9.1의 실명 나열이 dedup에서 "긴 신호명 리스트"로 분류되어 와일드카드 대체됐을 가능성.

#### (B) ⚠️ Instruction Engine 6-sub 섹션 통합본에서 삭제

v9.1 [§5.4](../v9.1/v9.1_N1B0_HDD.md)에는 `tt_instrn_engine` 하위 **6개 서브모듈 테이블** (unpack_srca, tt_sfpu_wrapper, tt_fpu_v2, jtag_csr_intf, tt_sync3, tt_tensix_jtag)이 존재했으나 v9.2 통합본에는 §5(Compute Tile)에 FPU/SFPU/TDMA/L1 4섹션만 있고 `tt_instrn_engine`이 통째로 삭제.

**부분 복구:** §14 DFX 섹션에 `tt_tensix_jtag / tt_sync3 / tt_fpu_gtile_SDUMP_INTF / TIEL_DFT_MODESCAN` 4항목은 유지. 그러나 Compute Tile 계층의 "instruction pipeline" 서브블록 구조는 **v9까지 누락 → v9.1 복구 → v9.2 재누락**의 진짜 regression.

#### (C) ⚠️ KB Coverage 정량 매트릭스 회귀 — 89% 수치 사라짐

v9.1 [v9.1_chip_grounded](../v9.1/v9.1_chip_grounded.md#L365): **"118/132 → 89%"** 15행 정량 매트릭스
v9.2 [v9.2_chip_grounded §KB Coverage Matrix](../v9.2/v9.2_chip_grounded.md#L263): 정성 매트릭스 14행 ("Full/Partial" 등급만)

**의의:**
- **v10 Spec RAG 기여도 측정을 위한 baseline 지표(89%)가 사라짐** — "89%→XX%" 형태 증가분 측정이 어려워짐
- **`[NOT IN KB]` 태그도 v9.1의 5건 정량화 → v9.2는 3건 내외로 분산** ([v9.2_chip_grounded](../v9.2/v9.2_chip_grounded.md)의 [NOT IN KB] 2건: "ATT entry count and bit width", "Total SRAM instance count per tile")
- v9.2 통합 HDD [§Appendix: Source Tracking](../v9.2/v9.2_N1B0_HDD.md#L388)이 신설됐지만 이는 "섹션↔소스 문서 매핑"이지 **"KB vs 정답지 gap 수치"가 아님**. 경영진용 지표 체계가 약화.

#### (D) ⚠️ DFX 4-node Wrapper Chain — v9.1 권고 **미반영**

v9.1 리뷰 §5.2-(1) **"🔥 DFX 4-node wrapper chain 복구 (최우선)"**:
> `instrn_engine_wrapper_dfx → noc_niu_router_dfx → overlay_wrapper_dfx → dfd` 체인은 여전히 누락

v9.2 §14 DFX: 여전히 tile-level 4항목 (tt_tensix_jtag, tt_sync3, SDUMP_INTF, TIEL_DFT_MODESCAN)만. 정답지 [N1B0_DFX_HDD §2](../../Sample/ORG/N1B0_DFX_HDD_v0.1.md#L22)의 **4 wrapper 모듈** (tt_noc_niu_router_dfx, tt_overlay_wrapper_dfx, tt_instrn_engine_wrapper_dfx, tt_t6_l1_partition_dfx)은 전부 미접근.

**회귀라기보다 "개선 실패"** — v9.1에서 이미 "부분 복구 (50%)"라고 명시됐고 "다음 v9.2의 최우선 과제"로 지정됐으나 v9.2는 다른 개선(EP table, dispatch wiring, flit)에 리소스를 집중하고 DFX는 동결.

### 2.4 v9.2가 여전히 못 채운 gap (남은 26%)

| 카테고리 | 정답지에만 존재 | v9.2 상태 | 해결 경로 |
|----------|----------------|----------|----------|
| **N1B0 vs Baseline 10행 차이 테이블** | 정답지 §1.1 | tile_t 2-variant 수준 (grounded에서는 name-only로 퇴보) | **v10 Spec RAG** |
| **DFX 4-node wrapper chain** | 정답지 §14 + N1B0_DFX_HDD 전체 | **여전히 tile-level만** | **v9.3 wrapper_dfx 전용 파서 (최우선)** |
| **AXI 56b gasket bit range** | `[55:52]rsvd/[51:48]target/[47:40]ep/[39:36]tlb/[35:0]addr` | **필드명만, bit range 없음** | **v10 Spec RAG** |
| **Flit 2048b + 3b type + 32b parity** | 정답지 §7 | SECDED 116/10 + 4D array만 | **v10 Spec RAG** |
| **NoC 알고리즘 pseudocode (tendril/force_dim)** | 정답지 §7.5 | 이름만 | **v9.3 noc_pkg.sv 파서 심화** |
| **Compute Tile TRISC/BRISC internal** | 정답지 §5.1 | Overlay §5.1 일부만 | **Tensix 내부 parser 확장** |
| **SRAM L1/VC/ATT 전체 구조 (3072×128 / 72×2048 / 1024×12)** | 정답지 §13 | 주 매크로만, N1B0의 768KB L1 상세 누락 | **memory HDD topic 파일 신설** |
| **EDC Node ID `{part[4:0], subp[2:0], inst[7:0]}`** | 정답지 §11.3 | 구조 없음 | **EDC topic 파일 강화** |
| **N1B0 Router 파라미터 6종 (REP_DEPTH 등)** | 정답지 §8.2 | 없음 | **v9.3 router_opt 전용 파서** |
| **Inter-column repeater depth (Y=3: 6-stage, Y=4: 4-stage)** | 정답지 §7.4 | 이름만 | **repeater parser 심화** |

**남은 gap의 성격 변화:**
- **v9.1 말 기준:** RTL-extractable 40% / Spec-only 50% / Hybrid 10%
- **v9.2 말 기준:** RTL-extractable **30%** (EP/dispatch/flit/gasket/L1 EDC 각 하나씩 해소) / Spec-only **60%** / Hybrid 10%
- → **v9.2는 "RTL에서 뽑힐 것"을 많이 뽑아낸 결과, 남은 gap의 Spec 의존도가 상대적으로 높아짐** → v10 Spec RAG의 ROI 예상 효과 상향

---

## 3. v9.1 → v9.2 진화 분석

### 3.1 **개선 레이어: "구조 노출 대도약 vs 실명·정량화 회귀"의 맞교환**

| | v7→v8 | v8→v9 | v9→v9.1 | **v9.1→v9.2** |
|---|-------|-------|---------|---------------|
| 변경 본질 | retrieval cutoff 확대 | Hybrid 태그 체계 도입 | dedup + 회귀 치유 + 자기 정량화 | **wire topology parser 대폭 확장 + Package parser EP 계산 로직** |
| 대표 변경 | max_results 20→50 | prompt 분할 + 2-way 출력 | dedup pipeline + KB Coverage 수치화 | **WireTopology claim 추출 (6 dispatch wires + 4 flit wires + clock mesh) + EP 자동 생성** |
| 변경 코드량 | 파라미터 1개 | prompt 템플릿 + merge | dedup 로직 + Grounding 컬럼 + 수치 집계 | **wire parser + EP index 계산기 + L1 EDC generate block 파서** |
| 정답지 일치도 | → 68% | → 67% | → 74% | **→ 74% (보합)** |
| 효과 성격 | visibility 극대화 | 측정 인프라 | 회귀 완전 치유 + 실명 노출 + baseline | **구조 정보 신규 노출 + 일부 실명 회귀 + KB Coverage 정량 회귀** |

**통찰 1 — "총점 보합 속의 질적 피벗":** v9.1→v9.2는 총점 같지만 **"DV 엔지니어 실사용(v9.1) → 아키텍트 설계 이해(v9.2)"로 사용자 층위가 이동**. EP 20행 테이블, dispatch feedthrough 6종, flit 4D, AXI 56b gasket, clock 4×5 mesh는 **칩 아키텍트가 블록다이어그램 그릴 때 필요한 정보** — 반면 SFR_RF_2P_HSC_QNAPA 같은 신호명은 **연결도 체크할 때 필요한 정보**. 둘 다 가치 있지만 성격이 다르다.

**통찰 2 — "RTL-extractable 소화가 거의 완료":** v9.2의 신규 성과 6종(EP/dispatch/flit/gasket/clock/L1 EDC)은 모두 **"RTL 파서만 잘 만들면 나올 수 있는 정보"**. v9.1 말까지는 "RTL-extractable but deep" 40%가 남아있었는데 v9.2에서 그 중 10~15pp를 소화. 남은 RTL-extractable은 **DFX wrapper chain + SRAM 상세 + NoC pseudocode** 정도로 **v9.3에서 일망타진 가능 범위**.

**통찰 3 — "자동화 증가가 실명 노출을 희생":** SFR/PRTN 실명 와일드카드 압축과 KB Coverage 정량 회귀는 **"파이프라인 자동화 강화 시 요약(summarization)이 우선권을 갖게 되는 현상"**. v9.1이 명시적으로 "실명 나열"을 Hard-coded 룰로 넣었다면 v9.2의 dedup/merge 자동화가 이를 "긴 리스트"로 인지해 압축했을 가능성. **자동화와 실명 노출이 충돌하는 트레이드오프가 노출됨**.

### 3.2 v9.1 권고 사항 → v9.2 반영 여부

이전 [claude_review_v9.1.md §5.2](claude_review_v9.1.md)의 "v9.2 단기 보강" 권고와 v9.2 반영 현황:

| v9.1 권고 | v9.2 반영 | 비고 |
|----------|----------|------|
| **🔥 DFX 4-node wrapper chain 복구 (최우선)** | ❌ **미반영** | 여전히 tile-level 4항목만. 4 wrapper(`*_dfx`) 파서 미구현 |
| **🔥 noc_pkg.sv 전용 파서** | 🟡 **부분 반영** | noc_header_address_t 필드명 + flit 4D array + AXI 56b gasket 필드명은 나옴. DOR/tendril pseudocode는 여전히 없음 |
| **Memory HDD topic 파일 신설** | ❌ **미반영** | v9.2_memory.md 없음. SRAM inventory는 §13 축소 상태 |
| **EP 인덱스 계산 로직** | ✅ **완전 반영** | **20행 완전 테이블 자동 생성 — v9.2 최대 성과** |
| **NoC ASCII 통합본 merge 규칙** | 🟡 **부분 반영** | [v9.2_noc §8](../v9.2/v9.2_noc.md#L100)에 EP map ASCII 있으나 **통합 HDD에는 여전히 없음** — 같은 실수 반복 |
| **regression CI 도입** | ❌ **미반영** | SFR/PRTN 실명 회귀가 CI에서 감지됐다면 회귀 방지 가능 — CI 부재로 발생 |

**관찰:** 6개 권고 중 **완전 반영 1건, 부분 반영 2건, 미반영 3건**. v9.1의 핵심 타깃 2건 중 1건(noc_pkg)만 부분 해결, DFX는 방치. **정작 완전 반영된 EP 테이블(가장 구체적이고 파서 작업이 명확한 항목)이 제일 큰 성과**를 냄 — v9.3 권고에서는 **"작업 범위가 명확히 정의된 파서 작업"이 가장 빨리 반영됨**을 학습.

### 3.3 v9.2 내부 일관성 점검

v9.1에서 지적한 **통합 HDD vs topic 파일** 비대칭 문제의 v9.2 상태:

| 항목 | topic 파일 | v9.2_N1B0_HDD.md (통합) | 일치? |
|------|-----------|------------------------|------|
| EP 20행 테이블 | [v9.2_chip_no_grounding §2.3](../v9.2/v9.2_chip_no_grounding.md) ✅ | [§2.3 (2열 배치)](../v9.2/v9.2_N1B0_HDD.md#L63) ✅ | ✅ |
| NoC 4×5 EP map ASCII | [v9.2_noc §8](../v9.2/v9.2_noc.md) ✅ | **§7 누락** | ❌ **재발** |
| Dispatch 6-wire 테이블 | [v9.2_chip_no_grounding §6.1](../v9.2/v9.2_chip_no_grounding.md) ✅ | [§6.1 ✅](../v9.2/v9.2_N1B0_HDD.md#L195) | ✅ |
| Flit 4D array | [v9.2_noc §3.1](../v9.2/v9.2_noc.md), [v9.2_chip_no_grounding §7.3](../v9.2/v9.2_chip_no_grounding.md) ✅ | [§7.2 ✅](../v9.2/v9.2_N1B0_HDD.md#L219) | ✅ |
| AXI 56b gasket 구조 | [v9.2_noc §4](../v9.2/v9.2_noc.md) ✅ | **§3 AXI에 없음, §7 NoC에도 없음** | ❌ **통합본 누락** |
| L1 EDC daisy-chain | [v9.2_overlay §4.3](../v9.2/v9.2_overlay.md) ✅ | [§11.3 ✅](../v9.2/v9.2_N1B0_HDD.md#L313) | ✅ |
| SFR 17 신호명 실명 | ❌ (와일드카드) | ❌ (와일드카드) | 🟡 **두 버전 모두 회귀** |
| DFX 4-node wrapper chain | ❌ | ❌ | 🟡 **두 버전 모두 누락** |

**요약:** v9.2의 통합 HDD ↔ topic 비대칭은 v9.1보다 **개선**됐으나, **2가지 정보가 topic에만 있고 통합본에 전파되지 못함** (NoC ASCII, AXI 56b gasket). v9.1 리뷰 §5.2-(5)의 "merge 파이프라인 개선" 권고가 반영되지 못한 흔적. **v9.3 우선 과제로 재지정 필요**.

### 3.4 Appendix: Source Tracking 신설 — v9.2 quiet win

[v9.2_N1B0_HDD §Appendix: Source Tracking](../v9.2/v9.2_N1B0_HDD.md#L388)은 v9.2에서 신설:

```markdown
| Section | Source Document |
|---------|----------------|
| 1-4 (Overview, Package, Ports, Hierarchy) | v9.2_chip_no_grounding.md |
| 7 (NoC Fabric) | v9.2_noc.md |
| 11 (EDC) | v9.2_edc.md |
| ...
```

**의의:**
- **각 섹션이 어느 topic 파일에서 왔는지 명시** → merge traceability 확보
- v9.1의 "dedup applied" 한 줄 대비 **훨씬 구체적인 파이프라인 투명성**
- **v9.3에서 이 매핑을 활용한 CI 검증(각 섹션이 소스 문서와 일치하는지 자동 체크) 가능** — regression test의 기초 인프라

---

## 4. 품질 지표 재해석 (경영진 보고 관점)

### 4.1 RAG_Farm_Strategy_v1.5 업데이트 반영 숫자

| 지표 | v7 | v8 | v9 | v9.1 | **v9.2** | 메모 |
|------|----|----|----|----|----|------|
| **Content Fidelity (가중, 리뷰어 기준)** | ~55% | ~68% | ~67% | ~74% | **~74%** | **보합** |
| **RAG 자기 평가 (KB Coverage)** | — | — | 정성 | **89%** | **정성 회귀** | **v9.1→v9.2 지표 손실** |
| KB Hit Rate | 75%+ | 85%+ | 85%+ | 85%+ | 85%+ | 유지 |
| Port Coverage | 29% | 100% | 100% | 100% | 100% | 유지 |
| **Port 실명 노출률 (AXI/SFR/PRTN)** | 0% | 0% | 0% | **~80%** | **~30%** | **실명 회귀** |
| **구조 정보 노출 (EP/wire/array)** | 0% | 5% | 10% | 20% | **~70%** | **v9.2 최대 도약** |
| `[NOT IN KB]` 선언 | ❌ | ❌ | ✅ (2건) | ✅ (5건 정량) | 🟡 **2건 정성** | **투명성 약화** |
| 섹션별 gap 집계 | ❌ | ❌ | 정성 | **정량 (15행)** | **정성 (14행)** | **회귀** |
| **Source Tracking (섹션↔토픽)** | ❌ | ❌ | ❌ | ❌ | ✅ **신설** | **CI 기반 확보** |
| 통합 HDD 비대칭 | — | — | 있음 | 부분 해소 | **부분 재발 (2건)** | — |
| Hallucination | 없음 | 없음 | 없음 | 없음 | 없음 | 유지 |

### 4.2 v1.5 로드맵 예측 vs 실측 (업데이트)

| 버전 | v1.4 예측 | 실측 | 차이 | 비고 |
|------|----------|------|------|------|
| v7 | 72% | 55% | -17pp | — |
| v8 | 78% | 68% | -10pp | — |
| v9 | 82% | 67% | -15pp | regression 발생 |
| v9.1 | 82% | 74% | -8pp | 예측치에 가장 근접 |
| **v9.2** | **82%** | **74%** | **-8pp** | **보합 — 예측 상승분 달성 실패** |
| v10 (Spec RAG) | 88%+ | TBD | — | 다음 마일스톤 |

**중요:** v1.4 예측 기준 v9.2는 **82%를 목표**로 했으나 **74% 보합** → 예측 대비 -8pp 정체. **v9 → v9.1 치유 사이클 이후 처음으로 "보합" 구간 진입** — 이는 **"v10 Spec RAG 없이는 추가 상승이 어렵다"는 신호**일 수 있음.

### 4.3 경영진 보고 권장 내러티브

- **v9.2 = "구조 이해 레벨업 + 아키텍처 청사진 완성"**
- **"EP 20행 테이블로 N1B0의 20개 tile을 좌표·EP·Type으로 완전 매핑 완료"**: 정답지와 완전 일치. **칩 아키텍트가 블록다이어그램 그릴 때 참고 가능한 1차 reference 문서 지위** 획득.
- **"Dispatch feedthrough 6개 wire, Flit 4D array, AXI 56b gasket 4필드, Clock 4×5 mesh"**: RAG가 처음으로 **"SoC 레벨 wire topology"를 wire 이름·차원·타입까지 노출**. 이전에는 "모듈 블록 간 관계"까지였다면 v9.2는 "블록 사이 data path의 모양"까지 파악.
- **"보합의 의미"**: 74% 정체는 **"RTL에서 나올 정보는 거의 다 나왔다"는 신호** — 남은 gap은 **Spec-only 60% + DFX wrapper chain + SRAM 상세**. **v10 Spec RAG 투자가 유의미한 상승(74%→88%+)을 가져올 baseline 확립**.
- **회귀 포인트 솔직 보고**: "v9.1이 얻었던 17+14=31개 신호 실명 노출이 v9.2에서 와일드카드로 회귀 — 이는 자동화 파이프라인 강화 시 summarization이 실명을 압축한 트레이드오프. **v9.3에서 실명 보존 룰을 CI로 강제**하여 치유 예정".
- **DFX 권고 미반영 솔직 보고**: "v9.1 리뷰 최우선 권고인 DFX 4-node wrapper chain은 v9.2에서 해결 실패 — 작업 난이도상 v9.3에서 별도 파서 스프린트로 처리". **해결 경로 명확 + ETA 제시**.

**주의 포인트:** 경영진이 "v9.2가 v9.1보다 왜 총점이 안 올랐냐"라고 물으면:
- "총점은 보합이지만 **개선 축이 크게 움직였다** — DV 엔지니어용(실명)에서 칩 아키텍트용(구조)으로. 정답지 커버리지 10개 섹션 중 **5개 섹션이 v9.2에서 개선**(Dispatch +20pp, NoC +10pp, Package +5pp, Clock +5pp, Overview +2pp), 반대편 3개가 회귀(Port -15pp, PRTN -10pp, DFX -10pp)해 상쇄"
- "회귀는 **자동화 파이프라인의 부작용**으로 원인이 명확하고 CI 도입으로 v9.3에서 해결 가능. 반면 v9.2의 개선 축은 **파서 재사용 확장을 통한 근본적 구조 이해 증가**이므로 영구 자산"

---

## 5. 권고

### 5.1 즉시 유지
- ✅ **EP Index Table 20행 파이프라인** — v9.2의 최대 성과, 정답지 100% 일치
- ✅ **Wire Topology 파서** (dispatch 6종 + flit 4D + clock 4×5) — 구조 이해의 돌파구
- ✅ **AXI 56b gasket 필드 추출** — Spec RAG와의 브릿지
- ✅ **Appendix: Source Tracking** — traceability 신설, CI 기반 될 수 있음

### 5.2 v9.3 단기 보강 (다음 v10 이전, 최우선순)

1. **🔥🔥 DFX 4-node wrapper chain 복구 (2-sprint 연속 최우선, 여전히 미반영)**
   - `tt_noc_niu_router_dfx → tt_overlay_wrapper_dfx → tt_instrn_engine_wrapper_dfx → tt_t6_l1_partition_dfx` 4-모듈 체인
   - 정답지 [N1B0_DFX_HDD §2](../../Sample/ORG/N1B0_DFX_HDD_v0.1.md#L22)의 4 wrapper + 5/5/1/2 clock count + `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` define 상태
   - 신규 `v9.3_dfx.md` topic 파일 + `*_dfx.sv` 4개 파일 전용 파서
   - 기대 +5~7pp

2. **🔥 실명 노출 회귀 치유 (v9.1 수준 복구)**
   - SFR 17 / PRTN 14 실명을 v9.1 수준으로 복구
   - dedup 파이프라인에 **"신호명 리스트는 압축 금지"** 예외 룰 추가
   - **CI regression test 도입**: v9.1 대비 신호명 카운트 유지 자동 체크
   - 기대 +3~5pp (Port 섹션 -15pp 복구)

3. **🔥 Instruction Engine 6-sub 테이블 통합본 복구**
   - v9.1 §5.4에 있던 `tt_instrn_engine` 서브 6종 테이블을 통합본 §5에 복구
   - 기대 +3~5pp (Module Hierarchy/Compute Tile 합산)

4. **noc_pkg.sv 심화 파싱 (v8/v9/v9.1 연속 권고)**
   - DOR pseudocode, tendril routing pseudocode, force_dim field
   - Flit bit range 추출 (2048b payload, 3b type, 32b parity)
   - 기대 +3~4pp (NoC 60% → 70%)

5. **N1B0 Router composite 전용 파서**
   - 정답지 [N1B0_NOC2AXI_ROUTER_OPT_HDD](../../Sample/ORG/N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md)의 "dual-row composite" 구조
   - Y=4 NOC2AXI + Y=3 router + 내부 cross-row wire 4종 (flit, clock, EDC chain, ID offset)
   - 기대 +3~4pp (NIU 35% → 45%, Module Hierarchy도 +)

6. **Memory HDD topic 파일 신설 + KB Coverage 정량 매트릭스 복구**
   - `v9.3_memory.md`: L1 (16×3072×128), VC (72×2048), ATT (1024×12)
   - `v9.3_chip_grounded`에 v9.1 스타일 **"XXX/YYY = ZZ%"** 정량 매트릭스 복귀
   - 기대 +2pp

7. **통합 HDD merge 파이프라인 개선 (2-sprint 연속 지적)**
   - topic 파일의 ASCII 블록과 AXI 56b gasket이 통합본으로 전파되도록 merge rule 추가
   - **CI 검증**: Appendix의 Source Tracking과 실제 섹션 내용 일치 자동 체크

### 5.3 v10 (Spec RAG) — 본격 도약

- v9.2의 `[NOT IN KB]` 항목들은 **Spec RAG의 직접 타깃**: ATT entry count/bit width, Total SRAM count, AXI gasket bit range, flit payload/type/parity
- **N1B0 vs Baseline 10행 차이 테이블**은 Spec-only 영역으로 v10 기여도 최대 가치 항목
- **AXI gasket bit range** `[55:52]/[51:48]/[47:40]/[39:36]/[35:0]`은 v9.2가 필드명만 뽑았으니 v10에서 bit range 보강 시 "Spec RAG 기여도 정량 증명"의 교본 사례가 됨
- v10 출시 후 **리뷰어 평가: 74% → ?%** 측정 → Spec RAG ROI 정량 증명

### 5.4 v9.2의 교훈 — v1.5 보고서 반영 사항

- **"구조 정보 피벗"**: v9.1까지의 개선은 "실명 노출"이 핵심이었으나 v9.2는 "wire topology/4D array/gasket 구조" 중심. **RAG 제품의 사용자 층위가 DV 엔지니어 → 칩 아키텍트로 확장**. 두 층위 모두 서비스 가능해야 함.
- **"자동화 vs 실명 노출 트레이드오프"**: dedup/summarization 자동화가 강할수록 긴 신호명 리스트가 와일드카드로 압축될 위험. **"신호명/enum 값은 압축 금지"가 핵심 룰**. CI로 강제.
- **"RTL-extractable 소진 신호"**: v9.2의 보합은 "RTL에서 나올 만한 게 거의 나왔다"는 증거. 남은 RTL 소화는 DFX wrapper/memory/router_opt 3-target. **이후 유의미한 상승은 Spec RAG가 만들어야 함** → v10 투자 정당성.
- **"권고 반영률 = 파서 작업 범위 명확성"**: 6개 권고 중 가장 명확하게 "EP = x*5 + y" 공식이 주어진 EP table만 완전 반영됨. v9.3 권고는 **"파서 작업 범위를 한 줄 의사코드로 묘사"**하는 정형 포맷 적용 권장.
- **"정량 매트릭스 보존 필수"**: KB Coverage 89%라는 수치는 RAG Farm v1.5 보고서의 핵심 지표였는데 v9.2에서 사라진 건 **경영진 보고 관점에서 큰 손실**. **정량화 한 번 하면 영구 보존**이 원칙.

---

## 6. 코멘트

- v9.2는 **"구조 이해의 도약 + 실명 노출 회귀의 맞교환"**. 총점만 보면 보합이지만 질적으로 큰 피벗이 일어난 버전. **정답지 §2.3 EP 테이블과 100% 일치**하는 20행 자동 생성은 경영진 앞에서 "정답지와 완전 동일한 출력"이라는 강력한 소구점.
- **`de_to_t6_coloumn[4][4]` 같은 wire 차원까지 추출**한 것은 **RAG가 단순 키워드 검색을 넘어 "SystemVerilog wire topology 구조를 해석"하는 수준에 도달**했음을 보여주는 결정적 증거. Dispatch sideband wire가 NoC와 별개 control path라는 아키텍처의 본질이 처음으로 RAG 출력에서 드러남.
- **회귀 3건은 모두 "자동화 파이프라인의 과도한 압축"이 원인**으로 **v9.1 수준으로 복구 가능**. 특히 SFR/PRTN 실명 회귀는 dedup 룰만 조정하면 즉시 해결. **"2 steps forward, 1 step back" 패턴은 RAG 엔지니어링에서 정상적 성장통**으로, v9 → v9.1에서 이미 겪은 패턴의 재발.
- **DFX 4-node wrapper chain 2-sprint 연속 미반영**은 경계해야 할 신호. 작업 난이도가 있는 과제가 **"다음 스프린트로 지속 이월되는 패턴"**이 생기면 v10 출시까지 미해결될 위험. **v9.3에서는 DFX만 먼저 격리된 스프린트로 처리** 권장.
- **v9.2의 진짜 가치는 "남은 gap의 성격 확정"**: 74% 보합은 "RTL-extractable 거의 다 뽑았다"는 수학적 신호 → **남은 26% 중 60%가 Spec-only**라는 분석이 가능해짐 → **v10 Spec RAG 투자 ROI 상한 14pp** 정량화 가능 → 경영진 투자 결정의 근거 확보.
- v9 → v9.1 → v9.2 사이클은 **RAG 제품 성숙 과정의 전형**: v9 (구조 변경 + 회귀) → v9.1 (치유 + 실명 + 정량화) → v9.2 (구조 확장 + 일부 회귀). **각 단계가 제품 사용자 층위의 확장**이었다는 점에서 일관된 전진.

---

*Review complete — 2026-05-08*
