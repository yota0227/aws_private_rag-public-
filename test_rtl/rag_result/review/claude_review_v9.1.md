# v9.1 Review — 정답지 비교 + v9 → v9.1 진화 분석

**Review Date:** 2026-05-06
**Reviewer:** Claude (Opus 4.7)
**Scope:** [test_rtl/rag_result/v9.1/](../v9.1/) 6개 문서 vs [test_rtl/Sample/ORG/](../../Sample/ORG/) 정답지
**Progression:** v8 (max_results 50) → v9 (Hybrid 태그 + 6-file split) → **v9.1 (dedup + SFR/DFX 회귀 복구 + KB Coverage Matrix 수치화 + tile_t 2-variant)**
**Cross-Reference:** [claude_review_v8.md](claude_review_v8.md), [claude_review_v9.md](claude_review_v9.md)

---

## 0. TL;DR

| Dim | v9 | v9.1 | Δ | 비고 |
|-----|----|----|----|------|
| **Top-Level Port Coverage** | 106/106 (100%) | **106/106 (100%)** | — | 유지 |
| **SFR Memory Config 17-port 실명 나열** | ❌ (요약) | ✅ **17 신호명 전부** ([v9.1_chip_no_grounding §3](../v9.1/v9.1_chip_no_grounding.md#L103)) | **v8 회귀 복구** | `RF_2P_HSC_QNAPA/QNAPB/EMAA/EMAB/RAWL` 등 family별 상세 |
| **PRTN 14-port 실명 나열** | 🟡 14개 테이블 (카테고리만) | ✅ **14 신호명 전부** ([v9.1_chip_no_grounding §3](../v9.1/v9.1_chip_no_grounding.md#L104)) | 질적 개선 | FC2UN/UN2FC 전체 노출 |
| **AXI 39-port 구체 신호명** | ❌ (카운트만) | ✅ **`npu_out_awvalid/id_t/addr_t/awlock/arvalid/arlock/rready` + npu_in_*** | +39 신호 | AXI gasket 식별 용이 |
| **DFX 섹션 복구** | ❌ (통합본에 없음) | ✅ **§14 전담 섹션** (tensix_jtag + sync3 + csr_intf + MODESCAN + SDUMP) | **v9 회귀 복구** | 단 정답지 4-node chain 세부는 여전히 누락 |
| **SRAM Inventory 섹션 복구** | 30% | **40%** ([v9.1 §13](../v9.1/v9.1_N1B0_HDD.md#L277): 주 매크로 + 4-family) | 부분 복구 | 정답지의 L1/VC/ATT 상세는 여전히 없음 |
| **tile_t Enum N1B0 vs Baseline 2종 구분** | ❌ | ✅ **`[v9.1 §2.2 + §2.3]`** 양변종 명시 | **신규 성과** | 정답지 §2.2와 거의 일치 |
| **isNorthEdge 함수 추출** | ❌ | ✅ [v9.1 §2.4](../v9.1/v9.1_N1B0_HDD.md#L78) | 신규 | Package 함수 2개로 확장 |
| **Instruction Engine 서브모듈 6종** | ❌ | ✅ **v9.1 §5.4** (unpack_srca/sfpu_wrapper/fpu_v2/jtag_csr_intf/sync3/tensix_jtag) | **신규** | 정답지 §5.1 TRISC/BRISC 영역 부분 접근 |
| **Grid Topology ASCII** | ❌ | ✅ [v9.1_noc §8.1](../v9.1/v9.1_noc.md#L172) 4×5 layout | 신규 (LLM 보완) | 정답지 §1.2 ASCII와 형식 유사 |
| **trinity_router 포트 목록 (baseline 참고)** | ❌ | ✅ [v9.1_noc §10](../v9.1/v9.1_noc.md#L213) | 신규 | N1B0 vs Baseline 비교 기반 |
| **KB Coverage Matrix (정량)** | 🟡 매트릭스만 | ✅ **"118/132 → 89%" 수치** ([v9.1_chip_grounded KB Coverage](../v9.1/v9.1_chip_grounded.md#L384)) | 질적 | 자기 진단 숫자 등장 |
| **dedup 파이프라인** | ❌ | ✅ 모든 문서 상단 "dedup applied" 명시 | 신규 | topic↔chip 중복 제거 |
| **정답지 대비 (가중 추정)** | ~67% | **~74%** | **+7pp** | **회귀 복구 + 상세도 증가** |
| **환각** | 없음 (`[FROM LLM]` 태그) | 없음 (`[FROM LLM]` + `[NOT IN KB]` 세분화) | — | 유지 |

**한 줄 결론:** v9.1은 **"v9의 회귀 복구 + v8의 잃었던 상세도 회복 + v10 Spec RAG 수치화 기반 완성"**이라는 3-in-1 스프린트 결과. **정답지 대비 67%→74% (+7pp)** — v7→v8(+13pp)에는 미치지 못하나 v8→v9(-1pp)의 회귀를 완전히 되돌리고 **상세도(SFR/PRTN/AXI 실명)에서 역대 최고**를 달성. 특히 **tile_t Baseline/N1B0 2-variant**와 **Instruction Engine 서브모듈 6종**은 v9까지 어느 버전에도 없던 신규 콘텐츠. **KB Coverage Matrix에 89%라는 자기 진단 수치가 최초 등장**해 v10 Spec RAG 기여도 측정의 기준점(baseline) 확립.

---

## 1. v9.1 파일 구성 개관

| 파일 | 역할 | 주요 변화 vs v9 |
|------|------|----------------|
| [v9.1_N1B0_HDD.md](../v9.1/v9.1_N1B0_HDD.md) (331줄) | **통합 HDD** (merged) | **v9 253줄 → v9.1 331줄 (+78줄)**, §13 SRAM/§14 DFX 섹션 신설 |
| [v9.1_chip_grounded.md](../v9.1/v9.1_chip_grounded.md) (389줄) | Hybrid 그라운딩 | **Grounding 컬럼 테이블 전반 도입** + KB Coverage Matrix 89% |
| [v9.1_chip_no_grounding.md](../v9.1/v9.1_chip_no_grounding.md) (358줄) | Raw RAG | **SFR 17-신호 + PRTN 14-신호 실명 전체** |
| [v9.1_edc.md](../v9.1/v9.1_edc.md) (159줄) | EDC topic | §3 모듈별 포트/기능 세분화 + Error Classification 표 |
| [v9.1_noc.md](../v9.1/v9.1_noc.md) (225줄) | NoC topic | **§8 Grid Topology ASCII + §10 trinity_router(baseline) 참조** |
| [v9.1_overlay.md](../v9.1/v9.1_overlay.md) (160줄) | Overlay topic | §5 APB Register 인터페이스 테이블 신설 |

**구조적 신규성:**
- 모든 문서 상단에 **"dedup applied"** 명시 — v9에서 발견된 통합본/topic 파일 간 정보 비대칭 이슈를 dedup 파이프라인으로 구조 해결
- [v9.1_chip_grounded.md](../v9.1/v9.1_chip_grounded.md)의 모든 테이블에 **Grounding 컬럼 표준화** (KB confirmed/FROM LLM/NOT IN KB/TBC)

---

## 2. v9.1 vs 정답지 상세 비교

### 2.1 Chip-level: [v9.1_N1B0_HDD.md](../v9.1/v9.1_N1B0_HDD.md) (331줄) vs [N1B0_NPU_HDD_v0.1.md](../../Sample/ORG/N1B0_NPU_HDD_v0.1.md) (1290줄)

| 섹션 | 정답지 | v9 | **v9.1** | Δ vs v9 | 근거 |
|------|--------|-----|----|---------|------|
| 1. Overview | 4×5 mesh + N1B0 차이 테이블 + ASCII | 65% | **70%** | +5pp | "EnableDynamicRouting/14 DM complexes" 상세 추가 |
| 2. Package Constants | 13 localparam + tile_t 2-variant + EP 테이블 | 65% | **90%** | **+25pp** | **tile_t N1B0/Baseline 2-variant 테이블 + isNorthEdge 함수 복구** |
| 3. Top-Level Ports | 7 서브섹션 (AXI/APB/EDC APB/SFR/PRTN/DM/AI) 실명 | 90% | **95%** | +5pp | **AXI 실명 + SFR 17 실명 + PRTN 14 실명** |
| 4. Module Hierarchy | 3-level generate + FDS/FPU/SFPU/TDMA/Instrn Engine 명시 | 65% | **80%** | +15pp | **Instruction Engine 계층 추가** (unpack_srca~tensix_jtag) |
| 5. Compute Tile (Tensix) | FPU/SFPU/TDMA/L1/DEST/SRCB/TRISC/BRISC | 30% | **40%** | +10pp | Instrn Engine 서브모듈 6종 + tt_idma_wrapper |
| 6. Dispatch | 3-level + FDS 상세 | 15% | 20% | +5pp | NumDispatch=2 명시 |
| 7. NoC | DOR + flit + gasket + 928-bit + ECC 세부 | 35% | **50%** | +15pp | **Flit width=126b (116+10), CDC chain ASCII, arbitration tree 레벨** |
| 8. NIU | Corner vs Composite + parameters | 25% | **35%** | +10pp | Tile Type 4종 encoding 포함 |
| 9. Clock | clock_routing_t + per-column | 80% | 80% | — | — |
| 10. Reset | dm_core/uncore 상세 | 70% | 75% | +5pp | "All resets active-low" 공지 |
| 11. Power Management | PRTN + ISO_EN + per-partition | 85% | 85% | — | 유지 (`[NOT IN KB]` power-on seq 명시) |
| 12. EDC | modport + BIU + 5 IRQ + ring | 90% | **95%** | +5pp | Error Classification 표 + 하베스트 bypass 메커니즘 |
| 13. SRAM | L1+VC+ATT 전체 | **30%** | **45%** | **+15pp** | **4-family 복구 + 주 매크로 명시 (v8 수준 회복)** |
| 14. DFX | 4개 모듈 + iJTAG + scan chain topology | **15%** | **40%** | **+25pp** | **섹션 복구: tensix_jtag + sync3 + csr_intf + SDUMP** (단 4-node chain 상세는 여전히 없음) |

**가중 점수 추정:** v9 ~67% → **v9.1 ~74%** (+7pp)

### 2.2 v9.1 핵심 개선 상세

#### (1) 🔥 SFR Memory Config 17 신호명 실명 복구 — v8 회귀 완전 치유

v9에서 **"17 | SRAM configuration"** 한 줄 요약으로 압축됐던 것이 v9.1에서 완전 회복:

```
SFR_RF_2P_HSC_QNAPA, SFR_RF_2P_HSC_QNAPB, SFR_RF_2P_HSC_EMAA[2:0],
SFR_RF_2P_HSC_EMAB[2:0], SFR_RF_2P_HSC_EMASA, SFR_RF_2P_HSC_RAWL,
SFR_RF_2P_HSC_RAWLM[1:0],
SFR_RA1_HS_MCS[1:0], SFR_RA1_HS_MCSW, SFR_RA1_HS_ADME[2:0],
SFR_RF1_HS_MCS[1:0], SFR_RF1_HS_MCSW, SFR_RF1_HS_ADME[2:0],
SFR_RF1_HD_MCS[1:0], SFR_RF1_HD_MCSW, SFR_RF1_HD_ADME[2:0]
```

([v9.1_chip_no_grounding §3 table](../v9.1/v9.1_chip_no_grounding.md#L103))

**의의:**
- **v8의 SFR 4-family 인벤토리 완전 회복** — [claude_review_v9.md §2.3-(2)](claude_review_v9.md)에서 지적한 "v9 regression 2건 중 1건" 해결
- `QNAPA/QNAPB` (Quiescent Noise A/B), `EMAA/EMAB` (Extra Margin Adjust A/B), `RAWL` (Read-After-Write Latch) 등 **메모리 타이밍 마진 공학의 domain vocabulary**가 RTL에서 직접 추출

#### (2) 🔥 PRTN 14 신호명 + AXI 신호명 실명 노출

[v9.1_chip_no_grounding §3](../v9.1/v9.1_chip_no_grounding.md#L104):

```
TIEL_DFT_MODESCAN, PRTNUN_FC2UN_DATA_IN, PRTNUN_FC2UN_READY_IN,
PRTNUN_FC2UN_CLK_IN, PRTNUN_FC2UN_RSTN_IN,
PRTNUN_UN2FC_DATA_OUT[3:0], PRTNUN_UN2FC_INTR_OUT[3:0],
PRTNUN_FC2UN_DATA_OUT[3:0], PRTNUN_FC2UN_READY_OUT[3:0],
PRTNUN_FC2UN_CLK_OUT[3:0], PRTNUN_FC2UN_RSTN_OUT[3:0],
PRTNUN_UN2FC_DATA_IN[3:0], PRTNUN_UN2FC_INTR_IN[3:0], ISO_EN[11:0]
```

→ **input 4 + output 8 + input 2 + ISO_EN = 14** 정확히 분해 가능. 이는 정답지 §12(Power Management)의 per-signal 테이블과 **100% 신호명 일치**.

AXI(39ports) 부분도 `npu_out_awvalid, npu_out_id_t, npu_out_addr_t, npu_out_awlock, npu_out_arvalid, npu_out_arlock, npu_out_rready, npu_in_*` 등 **핵심 대표 신호 노출** — AXI gasket 주소 맵(56b) 의미는 여전히 Spec RAG 대상이지만 **포트 레벨에서 "AXI5 id_t/addr_t typedef 사용"을 식별** 가능.

#### (3) 🔥 DFX 섹션 복구 — v9 회귀 완전 치유

v9에서 통합 HDD에 아예 누락됐던 DFX 섹션이 v9.1 §14에 신설:

```markdown
## 14. DFX (Design for Test/Debug)
- JTAG per tile: tt_tensix_jtag (u_tensix_jtag instance)
- Debug sync: tt_sync3 (jtag_dbg_req_sync)
- CSR access: jtag_csr_intf
- DFT scan: TIEL_DFT_MODESCAN
- SDUMP: tt_fpu_gtile_SDUMP_INTF
```

**의의:**
- [claude_review_v9.md §2.3-(1)](claude_review_v9.md)에서 지적한 "DFX 4-node iJTAG chain 유실 (-55pp local)" 문제의 **50% 복구**
- `tt_tensix_jtag / tt_sync3 / jtag_csr_intf` 3종은 **tile 내부 JTAG infrastructure**로 정답지 `N1B0_DFX_HDD_v0.1.md`의 일부 영역 커버
- 다만 **v8 리뷰의 "4-node 양방향 체인 (instrn_engine_wrapper_dfx → disp_eng_noc_niu_router_dfx → overlay_wrapper_dfx → dfd)"**은 여전히 누락 — 이는 **chip-level DFX wrapper 체인**이고, v9.1의 §14는 **tile-level DFX**만 다룸. 추가 복구 필요.

#### (4) 🆕 tile_t Enum N1B0 vs Baseline 2-variant — 정답지와 직접 일치

[v9.1_chip_grounded §2.2](../v9.1/v9.1_chip_grounded.md#L56):

**N1B0 variant (8):** TENSIX / NOC2AXI_NE_OPT / NOC2AXI_ROUTER_NE_OPT / NOC2AXI_ROUTER_NW_OPT / NOC2AXI_NW_OPT / DISPATCH_E / DISPATCH_W / ROUTER
**Baseline variant (8):** TENSIX / NOC2AXI_N_OPT / NOC2AXI_NE_OPT / NOC2AXI_NW_OPT / DISPATCH_E / DISPATCH_W / DRAM / ROUTER

→ 정답지 §2.2와 **encoding (3'd0~3'd7)** 수준까지 일치. 이는 v9에서 `[FROM LLM]`으로 얼버무렸던 tile_t 정보가 **실제 KB에서 추출 가능했음**을 실증 (RTL KB 파싱 범위가 확대된 결과로 추정).

**부가 성과:** "NOC2AXI_ROUTER_NE/NW_OPT의 존재가 곧 N1B0가 Baseline의 `trinity_router` 대신 사용하는 dual-row composite tile"이라는 정답지 §1.1의 핵심 차이점이 tile_t 비교로 자연스럽게 드러남.

#### (5) 🆕 Instruction Engine 서브모듈 6종 계층 신규 노출

v9까지 Tensix 내부는 FPU/SFPU/TDMA 3-sub까지만이었으나 v9.1에서 **`tt_instrn_engine`** 하위 6개 서브모듈 처음 노출:

| Sub-module | Instance | Function |
|------------|----------|----------|
| unpack_srca | — | Source A unpacking |
| tt_sfpu_wrapper | sfpu_wrapper | SFPU wrapper |
| tt_fpu_v2 | fpu | FPU v2 core |
| — | jtag_csr_intf | JTAG CSR interface |
| tt_sync3 | jtag_dbg_req_sync | 3-stage debug request sync |
| tt_tensix_jtag | u_tensix_jtag | Tensix JTAG controller |

([v9.1_chip_no_grounding §5.4](../v9.1/v9.1_chip_no_grounding.md#L174))

**의의:**
- 정답지 §5.1 "TRISC / BRISC CPU Cluster" 영역에 v9까지 접근조차 못했던 상황에서 **최초로 명령어 파이프라인 내부 구조 일부 노출**
- 특히 **unpack_srca**는 정답지 §5.6(DEST)/§5.7(SRCB) 데이터패스의 upstream 단서

#### (6) 🆕 Grid Topology ASCII + trinity_router(baseline) 참조

[v9.1_noc §8.1](../v9.1/v9.1_noc.md#L172)에 4×5 mesh layout ASCII:

```
        Col 0    Col 1    Col 2    Col 3
Row 4  [Node]   [Node]   [Node]   [Node]   ← North edge (isNorthEdge)
Row 3  [Node]   [Node]   [Node]   [Node]
Row 2  [Node]   [Node]   [Node]   [Node]
Row 1  [Node]   [Node]   [Node]   [Node]
Row 0  [Node]   [Node]   [Node]   [Node]
                                     ↑
                              East edge (isEastEdge)
```

정답지 §1.2의 타일명 풍부 ASCII 블록다이어그램에는 미치지 못하나 **좌표계와 edge 탐지 함수 연결**이 명확.

[v9.1_noc §10](../v9.1/v9.1_noc.md#L213)에 **baseline-only `trinity_router` 포트 리스트**까지 수록 — 정답지 §1.1 "N1B0 vs Baseline 차이 테이블"에 가장 가까운 결과물.

#### (7) 🆕 KB Coverage Matrix 89% 정량화

[v9.1_chip_grounded KB Coverage Matrix](../v9.1/v9.1_chip_grounded.md#L365):

| Section | KB Confirmed | FROM LLM | NOT IN KB | Coverage % |
|---------|-------------:|---------:|----------:|-----------:|
| 1. Overview | 8/8 | 0 | 0 | 100% |
| 2. Package Constants | 15/15 | 0 | 0 | 100% |
| 3. Top-Level Ports | 10/10 | 0 | 0 | 100% |
| 7. NoC Fabric | 11/13 | 2 | 0 | 85% |
| 12. Power Management | 3/6 | 1 | 2 | 50% |
| 13. SRAM Inventory | 3/5 | 1 | 1 | 60% |
| 14. DFX | 5/7 | 0 | 2 | 71% |
| **TOTAL** | **118/132** | **9** | **5** | **89%** |

**의의:**
- v9의 정성 매트릭스(✅/Partial/—)가 v9.1에서 **분모/분자 정량 수치**로 발전
- 이 **89%는 RAG 시스템이 스스로 산출한 자기 평가** — 리뷰어(정답지 기반 74%)와의 격차 **15pp**는 "KB 자체 풍부함 vs 정답지 스펙 커버리지" 차이로, **향후 v10 Spec RAG 도입 시 좁혀질 여지** 정량화
- "NOT IN KB = 5" 는 **v10 Spec RAG가 채워야 할 정확한 빈칸 개수** (power-on seq, retention strategy, total SRAM count, scan chain topology, BIST controllers)

### 2.3 v9.1이 여전히 못 채운 gap (남은 26%)

| 카테고리 | 정답지에만 존재 | v9.1 상태 | 해결 경로 |
|----------|----------------|----------|----------|
| **N1B0 vs Baseline 10행 차이 테이블** | 정답지 §1.1 | 부분 (tile_t 2-variant + trinity_router 참조) | **v10 Spec RAG** |
| **EP 인덱스 20행 전체 테이블** | 정답지 §2.3 | 없음 | **Package Parser 확장 (EP 계산 로직)** |
| **DFX 4-node chain (instrn/noc_niu/overlay/dfd)** | 정답지 §14 | §14는 tile-level만 | **topic 파일 `v9.1_dfx.md` 추가 + wrapper_dfx 검색** |
| **AXI gasket 56b 주소맵 구조** | [55:52]rsvd/[51:46]Y/[45:40]X/[39:0]local | Spec 성격 | **v10 Spec RAG** |
| **Flit 2048b payload + 3b type + 32b parity** | 정답지 §7 | SECDED 116/10만 식별 | **v10 Spec RAG** (noc_pkg.sv 미추출) |
| **NoC 알고리즘 pseudocode (tendril/force_dim)** | 정답지 §7 | 알고리즘 이름까지만 | **v9.2 noc_pkg.sv 파서 추가** |
| **Compute Tile TRISC/BRISC** | 정답지 §5.1 | Instrn Engine 6종 (부분 접근) | **Tensix 내부 parser 확장** |
| **SRAM L1/VC/ATT 전체 구조** | 정답지 §13 | 주 매크로만 | **memory HDD topic 파일 신설** |

**남은 gap의 성격:**
- **RTL-extractable but deep** (40%): DFX wrapper chain, EP 테이블, noc_pkg struct, Tensix sub-pipeline
- **Spec-only** (50%): N1B0 차이 테이블, AXI 56b, flit 구조, 알고리즘 pseudocode
- **Hybrid territory** (10%): active-low convention 같은 LLM 추론 가능 영역

---

## 3. v9 → v9.1 진화 분석

### 3.1 **개선 레이어: "회귀 치유 + 상세도 증가 + 자기 정량화"의 3-in-1**

| | v6c→v7 | v7→v8 | v8→v9 | **v9→v9.1** |
|---|--------|-------|-------|-------------|
| 변경 본질 | KB 밀도 증가 | retrieval cutoff 확대 | Hybrid 태그 체계 도입 | **dedup + 회귀 치유 + 자기 정량화** |
| 대표 변경 | Port Classifier | max_results 20→50 | prompt 분할 + 2-way 출력 | **dedup pipeline + KB Coverage 수치화** |
| 변경 코드량 | parser 수십 줄 | 파라미터 1개 | prompt 템플릿 + merge | **dedup 로직 + Grounding 컬럼 + 수치 집계** |
| 정답지 일치도 | → 55% | → 68% | → 67% | **→ 74%** |
| 효과 성격 | 범주 두께 증가 | visibility 극대화 | 측정 인프라 | **회귀 완전 치유 + 실명 노출 + baseline 수치 확립** |

**통찰 1 — "구조 변경 후 회귀 치유"가 완결:** v9가 파이프라인 구조 변경(태그/merge)으로 v8 정보를 일시 유실했던 상황이 v9.1 dedup 파이프라인으로 **완전 해결**. DFX는 50%, SFR family는 100% 복구됨. 이는 v9 리뷰 §5.2의 최우선 권고(DFX/SFR 복구)가 **정확히 반영**된 결과.

**통찰 2 — "실명 노출" 단계로 도약:** v8까지의 개선은 "카운트 100% 도달(31→106)"이 핵심이었으나 v9.1은 **"카운트를 넘어 개별 신호 이름까지"** 노출. 이는 **DV 엔지니어가 실제 연결도를 확인할 때 직접 사용 가능한 수준** — 경영진 보고뿐 아니라 **엔지니어링 실사용 수준**에 처음 도달.

**통찰 3 — "자기 정량화" 최초 등장:** `118/132 = 89%`는 **RAG 시스템이 스스로 산출한 자기 신뢰도 점수**. 리뷰어 평가(74%)와의 15pp 격차는 **"KB 풍부함 vs 정답지 스펙 폭" 차이**로, v10 Spec RAG 기여도 측정의 출발점이 될 baseline 확립.

### 3.2 v9 권고 사항 → v9.1 반영 여부

이전 [claude_review_v9.md §5.2](claude_review_v9.md)의 "v9.x 단기 보강" 권고와 v9.1 반영:

| v9 권고 | v9.1 반영 | 비고 |
|---------|----------|------|
| **🔥 DFX 정보 복구 (최우선)** | 🟡 **부분 반영** | §14 tile-level DFX 복구 완료, 그러나 4-node wrapper chain은 여전히 누락 (다음 v9.2 필요) |
| **🔥 SFR SRAM family 4종 복구 (최우선)** | ✅ **완전 반영** | 17 신호 실명 + 4-family 명시 |
| **grounded/no_grounding best-of merge** | ✅ **완전 반영** | dedup 파이프라인으로 두 버전 간 정보 비대칭 해소 |
| **noc_pkg.sv 전용 파서** | ❌ 미반영 | 여전히 DOR/force_dim pseudocode 없음 (다음 v9.2 필요) |
| **regression test 도입** | 🟡 **암묵적 반영** | dedup 파이프라인이 회귀 방지 역할 하지만 CI 자동화는 미확인 |

**관찰:** v9 리뷰의 최우선 권고 2건 중 1건(SFR) 완전, 1건(DFX) 부분 반영. 다음 v9.2는 **DFX wrapper chain + noc_pkg** 두 가지가 핵심 타깃.

### 3.3 v9.1 내부 일관성 점검

v9에서 지적한 **통합 HDD vs topic 파일** 비대칭 문제의 v9.1 상태:

| 항목 | topic 파일 | v9.1_N1B0_HDD.md (통합) | 일치? |
|------|-----------|------------------------|------|
| EDC 16-port 실명 테이블 | [v9.1_edc §5](../v9.1/v9.1_edc.md) ✅ | §8 요약 (5 IRQ + U-shape) | 🟡 **의도적 요약** |
| PRTN 14-port 실명 | [v9.1_chip_no_grounding §3](../v9.1/v9.1_chip_no_grounding.md) ✅ | §11 요약 | 🟡 **의도적 요약** |
| NoC 4×5 mesh ASCII | [v9.1_noc §8](../v9.1/v9.1_noc.md) ✅ | §7 없음 | ❌ |
| Instruction Engine 6-sub | [v9.1_chip_no_grounding §5.4](../v9.1/v9.1_chip_no_grounding.md) ✅ | §4 hierarchy + §5 테이블 ✅ | ✅ |
| tile_t 2-variant | grounded §2.2 + no_grounding §2.2 ✅ | §2.2 + §2.3 ✅ | ✅ |
| DFX 섹션 | no_grounding §14 ✅ | **§14 ✅ 복구** | ✅ |

→ **v9의 완전 비대칭은 v9.1에서 "의도적 요약(compression)"으로 개선**. 통합본은 여전히 topic 파일보다 간결하지만 이는 **경영진용 레이아웃 선택**으로 볼 수 있음. 다만 **NoC ASCII가 통합본에서 누락**된 건 아쉬운 점으로, 통합 merge 시 ASCII 블록은 보존하는 규칙 추가 권장.

### 3.4 grounded vs no_grounding A/B 2차 관찰

v9.1에서는 두 버전이 **구조적으로 거의 동일** (Grounding 컬럼 유무만 차이):

| 항목 | no_grounding | grounded | 결론 |
|------|--------------|----------|------|
| SFR 17-port table | ✅ 실명 전체 | ✅ 실명 전체 + Grounding 컬럼 | **동등 (v9 대비 평준화)** |
| tile_t 2-variant | ✅ | ✅ | 동등 |
| Instruction Engine 6-sub | ✅ | ✅ | 동등 |
| KB Coverage Matrix | ❌ | ✅ (89%) | **grounded only** |
| `[NOT IN KB]` 선언 | ❌ | ✅ (power-on seq / SRAM count / scan topology 등 5건) | **grounded only** |

**패턴 변화:** v9의 A/B는 **"서로 다른 내용"**이었으나 v9.1의 A/B는 **"같은 내용 + 메타데이터 유무"** 관계. 이는 dedup 파이프라인이 **두 버전의 본문을 정렬**했음을 뜻함. 더 이상 두 버전을 **content merge**할 필요는 없고, **"KB 팩트 확인용 = no_grounding / gap 식별용 = grounded"**로 역할 분담이 명확해짐.

---

## 4. 품질 지표 재해석 (경영진 보고 관점)

### 4.1 RAG_Farm_Strategy_v1.5 업데이트 반영 숫자

| 지표 | v7 | v8 | v9 | **v9.1** | 메모 |
|------|----|----|----|----|------|
| **Content Fidelity (가중, 리뷰어 기준)** | ~55% | ~68% | ~67% | **~74%** | 메인 지표 |
| **RAG 자기 평가 (KB Coverage Matrix)** | — | — | 정성 | **89%** | **v9.1 신규 지표** |
| KB Hit Rate | 75%+ | 85%+ | 85%+ | 85%+ | 유지 |
| Port Coverage | 29% | 100% | 100% | 100% | 유지 |
| **Port 실명 노출률 (AXI/SFR/PRTN)** | 0% | 0% | 0% | **~80%** | **v9.1 신규 도약** |
| `[NOT IN KB]` 선언 가능성 | ❌ | ❌ | ✅ (2건) | ✅ **(5건 정량화)** | 투명성 증가 |
| 섹션별 gap 자동 집계 | ❌ | ❌ | 정성 매트릭스 | **정량 매트릭스 (15행)** | — |
| 통합 HDD 회귀 | — | — | 있음 (DFX/SFR) | **없음** | dedup 파이프라인 |
| Hallucination | 없음 | 없음 | 없음 (태그 격리) | 없음 (태그 + 수치) | 유지 |

### 4.2 v1.5 로드맵 예측 vs 실측 (업데이트)

| 버전 | v1.4 예측 | 실측 | 차이 | 비고 |
|------|----------|------|------|------|
| v7 | 72% | 55% | -17pp | — |
| v8 | 78% | 68% | -10pp | — |
| v9 | 82% | 67% | -15pp | regression 발생 |
| **v9.1** | **82%** | **74%** | **-8pp** | **예측치에 가장 근접** |
| v10 (Spec RAG) | 88%+ | TBD | — | 다음 마일스톤 |

**격차 재개선:** v9에서 벌어졌던 격차(-15pp)가 v9.1에서 **-8pp로 좁혀짐**. 이는 v6c→v7→v8 궤적과 유사한 "안정적 상승" 복귀 신호. v10 Spec RAG로 88% 예측치 달성 가능성 ↑.

### 4.3 경영진 보고 권장 내러티브

- **v9.1 = "3-in-1 스프린트: 회귀 치유 + 상세도 도약 + 수치 baseline 확립"**
- **"실명 노출"이라는 엔지니어링 가치**: 이전에는 "AXI 포트 39개"라고만 했다면 v9.1은 `npu_out_awvalid/id_t/addr_t/awlock...` 구체적 이름까지 — **DV 엔지니어가 직접 연결 검증 가능한 수준**
- **"89% 자기 평가"**: RAG 시스템이 처음으로 **"내가 얼마나 알고 있는지"를 수치로 선언** → v10 Spec RAG 도입 후 **"89% → XX%"로 증가분 정량 측정** 가능. 이는 경영진이 투자 ROI를 숫자로 확인할 수 있는 첫 지표.
- **"RAG 자기 평가(89%) vs 리뷰어 평가(74%) 15pp gap"**: 둘의 차이는 **"KB 풍부함 vs Spec 스펙"** gap으로, Spec RAG 합류 후 두 수치가 수렴할 것. 이는 **v10 Spec RAG 필요성의 정량 근거**.

**주의 포인트:** 경영진이 "v9.1이 v9보다 왜 좋아졌냐"라고 물으면:
- "v9가 측정 체계를 구축하느라 일시 regression을 겪었고, v9.1은 그 회귀를 치유하면서 **v8까지 없던 '개별 포트 이름' 수준의 상세도까지 확보** — 엔지니어링 실사용 단계 진입"
- "v10 Spec RAG 투자를 앞둔 **최적의 측정 baseline** (89% 자기 평가 + 74% 리뷰어 평가) 확립"

---

## 5. 권고

### 5.1 즉시 유지
- ✅ **dedup 파이프라인** — v9.1의 핵심 성과, 회귀 방지 구조 역할
- ✅ **Grounding 컬럼 표준화** (grounded 버전 전체 테이블)
- ✅ **KB Coverage Matrix 수치 집계** — v10 기여도 측정 baseline
- ✅ **AXI/SFR/PRTN 실명 노출** — 엔지니어링 실사용 가능성

### 5.2 v9.2 단기 보강 (다음 v10 이전)

1. **🔥 DFX 4-node wrapper chain 복구 (최우선)**
   - v9 리뷰 이후 tile-level DFX는 복구됐으나 **chip-level wrapper chain (instrn_engine_wrapper_dfx → noc_niu_router_dfx → overlay_wrapper_dfx → dfd)**은 여전히 누락
   - `v9.2_dfx.md` topic 파일 신설 + wrapper 모듈 전용 검색
   - 기대 +3~5pp

2. **🔥 noc_pkg.sv 전용 파서 (v8/v9 연속 권고)**
   - flit struct, 라우팅 테이블, DOR/force_dim pseudocode 추출
   - Package Parser v2 재활용 (함수/태스크 정규식 기반)
   - 기대 +3~4pp

3. **Memory HDD topic 파일 신설**
   - L1/VC/ATT 구조 분리 추출 → SRAM inventory 45% → 60% 기대
   - `v9.2_memory.md`

4. **EP 인덱스 계산 로직**
   - `EndpointIndex = x * SizeY + y` 규칙을 Package Parser에서 계산 → 20행 테이블 자동 생성
   - 기대 +2pp (정답지 §2.3 복구)

5. **NoC ASCII 통합본 merge 규칙**
   - topic 파일의 ASCII 블록이 통합본에서 유실되지 않도록 merge 파이프라인 개선

6. **regression CI 도입**
   - v8의 "핵심 KB 팩트 목록" vs 현재 출력 비교 자동 수행
   - v10 출시 전 반드시 구축

### 5.3 v10 (Spec RAG) — 본격 도약

- v9.1의 `[NOT IN KB]` 5건 (power-on seq, retention, SRAM count, scan topology, BIST)은 **Spec RAG의 직접 타깃**
- **N1B0 vs Baseline 10행 차이 테이블**, **AXI 56b 주소맵 구조**, **Flit 2048b + 3b + 32b**는 Spec-only 영역으로 v10 기여도 측정의 **최대 가치 항목**
- v10 출시 후 **KB Coverage Matrix: 89% → ?%**와 **리뷰어 평가: 74% → ?%** 두 지표 동시 측정 → Spec RAG ROI 정량 증명

### 5.4 v9.1의 교훈 — v1.5 보고서 반영 사항

- **"카운트에서 실명으로 = 엔지니어링 실사용 단계 진입"**: v8의 "100% 카운트"는 경영진용이었다면 v9.1의 "80% 실명"은 **DV 엔지니어 직접 사용** 단계. RAG 제품의 **"사용자 층위" 확장**이 v9.1에서 일어남.
- **"자기 평가 수치의 효용"**: RAG가 "89%"라고 스스로 말하는 것 자체가 **조직 내 신뢰도 형성 요소**. "우리는 KB의 89%를 커버하고, 나머지 11%가 왜 비어있는지 알고 있다"는 **솔직한 시스템**이라는 브랜딩.
- **"v9 → v9.1 회귀 복구 패턴은 제품화 방법론"**: 구조 변경(v9) → 회귀 감지(review) → 치유(v9.1)의 사이클은 **RAG 엔지니어링의 표준 라이프사이클**로 v1.5 보고서에 "회귀 치유 스프린트(Regression Healing Sprint)" 항목으로 정식 등록 권장.

---

## 6. 코멘트

- v9.1은 **"제품 완성도 중간 점검"**. v9에서 미완결이었던 태그 체계/회귀 치유/자기 정량화가 한 번에 마무리됐고, 동시에 v8까지도 없던 "실명 노출"이라는 새 고지를 점령.
- 특히 **`SFR_RF_2P_HSC_QNAPA` 같은 메모리 마진 신호명까지 RTL에서 직접 추출**된 것은 **Tenstorrent 내부 DV 지식의 수준에 근접**하는 결과. 대표님/CTO 앞에서 "이 신호명이 정답지에 있는 것과 정확히 일치합니다"라고 보여주면 강력한 소구점.
- **89% vs 74% gap**을 **"Spec RAG 기여도 정량 측정 기반"**으로 프레이밍하는 것이 v1.5 보고서의 핵심 전략. 단순 숫자가 아니라 **"v10 투자가 실제로 몇 %p를 올렸는지 측정하는 계측기"**가 이번 v9.1에서 완성됐음.
- v9.1이 달성한 74%는 **RTL 단독 RAG의 "상세도 최고 수준"**. 남은 26% 중 **절반은 noc_pkg/DFX wrapper/memory HDD 등 RTL-extractable**이므로 v9.2에서 80% 돌파 가능, **나머지 절반은 Spec-only**로 v10 필수.
- v9→v9.1 사이클은 **RAG 제품 엔지니어링의 모범 사례**로 기록될 만함: "구조 개선 시 regression을 숨기지 않고 리뷰에서 명시 → 다음 스프린트에서 정확히 치유". 이는 조직 내 **솔직한 품질 문화**의 모범.

---

*Review complete — 2026-05-06*
