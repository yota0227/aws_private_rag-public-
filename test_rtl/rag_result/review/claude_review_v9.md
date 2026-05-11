# v9 Review — 정답지 비교 + v8 → v9 진화 분석

**Review Date:** 2026-05-06
**Reviewer:** Claude (Opus 4.7)
**Scope:** [test_rtl/rag_result/v9/](../v9/) 6개 문서 vs [test_rtl/Sample/ORG/](../../Sample/ORG/) 정답지
**Progression:** v7 (Port Classifier + MCP 800char) → v8 (max_results 20→50, Port 31→106) → **v9 (Hybrid 그라운딩 태그 + 6-file split + 통합 HDD)**
**Cross-Reference:** [claude_review_v7.md](claude_review_v7.md), [claude_review_v8.md](claude_review_v8.md)

---

## 0. TL;DR

| Dim | v8 | v9 | Δ | 비고 |
|-----|----|----|----|------|
| **Top-Level Port Coverage** | 106/106 (100%) | **106/106 (100%)** | — | 유지 |
| **Hybrid Grounding 태그 실적용** | ❌ (이름만 Hybrid) | ✅ **`[FROM LLM]`/`[NOT IN KB]`/`[TBC]` 3종 태그** | **최초 도입** | v8 리뷰의 핵심 권고 반영 |
| **통합 HDD 문서 생성 파이프라인** | ❌ (topic별 분리) | ✅ **[v9_N1B0_HDD.md](../v9/v9_N1B0_HDD.md)** (Appendix 소스 추적 포함) | 신규 | 경영진용 단일 문서 확보 |
| **Grounded / No-Grounding 2종 출력** | ❌ | ✅ [v9_chip_grounded.md](../v9/v9_chip_grounded.md) + [v9_chip_no_grounding.md](../v9/v9_chip_no_grounding.md) | 신규 | 추후 A/B 측정 가능 |
| **Power Management 섹션** | ~80% (PRTN 14 + ISO_EN 복구) | **~85%** (PRTN 14-행 테이블 명시) | +5pp | no_grounding에 per-signal 테이블 추가 |
| **EDC APB 16-port 테이블** | 압축 서술 | ✅ **16-signal 전체 테이블** | 질적 | [v9_chip_no_grounding.md §9](../v9/v9_chip_no_grounding.md), [v9_edc.md §4](../v9/v9_edc.md) |
| **DFX 4-node iJTAG chain 상세** | ✅ (v8 도약 요소) | **❌ 회귀** (통합 HDD에 미반영) | **-15pp** | v9 N1B0 HDD에서 DFX 섹션 자체 누락 |
| **SRAM Inventory** | 45% (SFR family 4종) | 30% (`[FROM LLM]` 태그 + `[NOT IN KB]` 고백) | **-15pp** | grounded는 솔직하게 "KB에 없음" 명시하나 v8의 SFR 4-family 정보가 통합본에서 빠짐 |
| **`trinity_router` EMPTY 명시** | 암시 | ✅ **명시** (`"NOT instantiated in N1B0 (EMPTY by design)"`) | 질적 | 정답지 § 2.2 `ROUTER 3'd7` 설명과 부합 |
| **정답지 대비 (가중 추정)** | ~68% | **~67%** | **-1pp** | **수평** (일부 회귀 + 일부 개선 상쇄) |
| **환각** | 없음 | 없음 (`[FROM LLM]` 태그로 격리) | — | 구조적 개선 |

**한 줄 결론:** v9는 **"품질 상승이 아닌 품질 선언(declaration) 체계 도입"** 단계. 정량적 정답지 일치도는 v8(68%) 대비 소폭 회귀(~67%)했으나, **Hybrid 그라운딩 태그 체계**와 **통합 HDD 자동 생성 파이프라인**이라는 두 구조적 자산을 확보. 특히 `[FROM LLM]`/`[NOT IN KB]` 태그는 향후 Spec RAG(v10) 도입 시 **"채워야 할 빈칸"을 정량 측정할 수 있는 메타데이터**로 기능할 것. 단, **DFX 4-node chain**과 **SFR SRAM family 4종** 정보가 통합본에서 유실된 것은 **regression 이슈**로 v9.x 보강이 필요.

---

## 1. v9 파일 구성 개관

| 파일 | 역할 | 주요 내용 |
|------|------|----------|
| [v9_N1B0_HDD.md](../v9/v9_N1B0_HDD.md) (253줄) | **통합 HDD** (merged) | 13개 섹션 + Appendix 소스 추적 테이블 |
| [v9_chip_grounded.md](../v9/v9_chip_grounded.md) (225줄) | **Hybrid 그라운딩 버전** | 14개 섹션, `[FROM LLM]`/`[NOT IN KB]` 태그 + KB Coverage Matrix |
| [v9_chip_no_grounding.md](../v9/v9_chip_no_grounding.md) (218줄) | **Raw RAG** (grounding 없음) | 11개 섹션, PRTN 14-port 상세 테이블 |
| [v9_edc.md](../v9/v9_edc.md) (108줄) | EDC topic 문서 | BIU/NoC Sec/Ring/Harvest + 16-port table |
| [v9_noc.md](../v9/v9_noc.md) (104줄) | NoC topic 문서 | 라우팅 알고리즘, 9개 모듈, CDC, Security |
| [v9_overlay.md](../v9/v9_overlay.md) (72줄) | Overlay topic 문서 | FDS 레지스터 3종, Cluster Control |

**구조적 신규성:**
- v9 최초 **"grounded" vs "no_grounding" 2종 동시 출력** — 이는 Hybrid 전략을 **A/B 테스트 가능한 형태로 제품화**한 것
- **통합 HDD (v9_N1B0_HDD.md)는 topic 파일을 merge**해 단일 경영진용 문서로 승격

---

## 2. v9 vs 정답지 상세 비교

### 2.1 Chip-level: [v9_N1B0_HDD.md](../v9/v9_N1B0_HDD.md) (253줄) vs [N1B0_NPU_HDD_v0.1.md](../../Sample/ORG/N1B0_NPU_HDD_v0.1.md) (1290줄)

| 섹션 | 정답지 | v8 | **v9 (통합본)** | Δ vs v8 | 근거 |
|------|--------|-----|-----|---------|------|
| 1. Overview | 4×5 mesh + N1B0 차이 테이블 + ASCII 블록다이어그램 | 65% | **65%** | — | 차이 테이블 여전히 부재 |
| 2. Package Constants | 10 localparam + tile_t + EP 테이블 | 90% | **65%** | **-25pp** | **tile_t enum 테이블 누락** (grounded에만 `[FROM LLM]` 태그로 언급), EP 테이블 누락 |
| 3. Top-Level Ports | 7 서브섹션 (AXI/APB/EDC APB/SFR/PRTN/DM/AI) | 95% | **90%** | -5pp | 카테고리 카운트 테이블 유지하나 **AXI 39개 실제 이름 누락** |
| 4. Module Hierarchy | 3-level generate + FDS/FPU/SFPU/TDMA 명시 | 55% | **65%** | +10pp | **FPU/SFPU/TDMA sub-module이 ASCII tree에 포함됨** |
| 5. Compute Tile (Tensix) | FPU/SFPU/TDMA/L1/DEST/SRCB 7 서브 + G-Tile/M-Tile | 25% | **30%** | +5pp | DEST/SRCB 언급(grounded: `[FROM LLM]`), FPU G-Tile/M-Tile 명시 |
| 6. Dispatch | 3-level + FDS 상세 | 15% | 15% | — | 변화 없음 |
| 7. NoC | DOR + flit + gasket + 928-bit | 30% | **35%** | +5pp | 라우팅 알고리즘 3종(DIM_ORDER/TENDRIL/DYNAMIC) 명시 |
| 8. NIU | Corner vs Composite + parameters | 30% | 25% | -5pp | Corner vs Composite 구분 미약화 |
| 9. Clock | clock_routing_t + per-column | 80% | 80% | — | — |
| 10. Reset | dm_core/uncore 상세 | 65% | 70% | +5pp | 14×8 매트릭스 명시적으로 테이블화 |
| 11. Power Management | PRTN + ISO_EN + per-partition | 80% | **85%** | +5pp | **PRTN 14-port per-signal 테이블** ([v9_chip_no_grounding.md §10](../v9/v9_chip_no_grounding.md)) |
| 12. EDC | modport + BIU + 5 IRQ | 90% | **90%** | — | 16-port table 유지 + U-shape ring 명시 |
| 13. SRAM | L1+VC+ATT 전체 | 45% (SFR 4 family) | **30%** | **-15pp** | **회귀** — 통합본에 SFR family 정보 누락, grounded는 `[NOT IN KB]` 선언 |
| 14. DFX | 4개 모듈 + iJTAG | 70% (4-node + 양방향) | **15%** | **-55pp** | **회귀** — 통합 HDD에 DFX 섹션 자체 누락, grounded만 `[FROM LLM]` 언급 |

**가중 점수 추정:** v8 ~68% → **v9 ~67%** (-1pp, 수평)

### 2.2 v9 핵심 개선 상세

#### (1) Hybrid 그라운딩 태그 체계 실구현

v8 리뷰에서 **"이름만 Hybrid였고 실제로는 retrieval 확대였다"**고 지적한 문제가 v9에서 해소:

```markdown
| Tag | Meaning |
|-----|---------|
| (no tag) | Confirmed from KB (module, port, claim data) |
| `[FROM LLM]` | Supplemented from LLM domain knowledge |
| `[NOT IN KB]` | Not in KB, cannot be inferred |
| `[TBC]` | Needs verification |
```

([v9_chip_grounded.md §Grounding Legend](../v9/v9_chip_grounded.md))

적용 사례:
- **§2 tile_t 엔움**: `[FROM LLM]` — RTL에서 추출 실패, 아키텍처 도메인 지식으로 보충
- **§5 DEST/SRCB 레지스터 파일**: `[FROM LLM]` — KB에는 TDMA까지만, register file은 추론
- **§12 SRAM Inventory**: `[NOT IN KB]` — 정확한 카운트/용량은 **KB에 없다고 명시**
- **§13 DFX**: `[FROM LLM]` + `[NOT IN KB]` 혼합

**의의:** 경영진/DV 엔지니어에게 **"LLM이 아는 것" vs "실제 RTL에 있는 것"을 구분해서 제시** — 환각 위험 축소 + 신뢰 가능한 의사결정 자료.

#### (2) KB Coverage Matrix 신설

[v9_chip_grounded.md §KB Coverage Matrix](../v9/v9_chip_grounded.md)에 섹션별 상태표:

| Section | KB | FROM LLM | NOT IN KB |
|---------|----|---------:|----------:|
| Compute Tile | Partial | L1, DEST/SRCB | — |
| SRAM Inventory | Partial | Instance types | Count/capacity |
| DFX | — | iJTAG/BIST | Scan topology |

**이 매트릭스는 v1.5 보고서의 "아직 남은 gap" 정량화 근거로 직접 활용 가능**. v8까지는 리뷰어가 수작업으로 gap을 계산했으나, v9부터는 **파이프라인 자체가 gap을 보고**한다.

#### (3) 통합 HDD 자동 생성 파이프라인

[v9_N1B0_HDD.md](../v9/v9_N1B0_HDD.md) 말미의 **Appendix: Source Traceability** 테이블:

```
| Section | Source Document |
|---------|----------------|
| 3. Top-Level Ports | v9_chip_no_grounding (Prompt 1) — trinity search |
| 7. NoC Fabric | v9_noc (Prompt 4) — NoC topic search |
| 8. EDC | v9_edc (Prompt 2) — EDC topic search |
| 12. Overlay | v9_overlay (Prompt 3) — Overlay topic search |
```

→ **어떤 섹션이 어떤 Prompt에서 왔는지 감사 가능**. DV 리뷰어가 "8번 섹션이 틀렸다"고 할 때 Prompt 2를 직접 역추적할 수 있음.

#### (4) EDC 16-port 테이블 — 정답지 신호 이름 수준 일치

[v9_chip_no_grounding.md §9](../v9/v9_chip_no_grounding.md) 및 [v9_edc.md §4](../v9/v9_edc.md)에 **16개 APB/IRQ 신호명 + 방향 + 폭** 전체 테이블화:

| Signal | Direction | Width |
|--------|-----------|-------|
| i_edc_apb_paddr | input | [5:0] |
| i_edc_apb_pwdata | input | [31:0] |
| o_edc_fatal_err_irq | output | 1 |
| ... (16 rows total) | | |

이는 정답지 §11(EDC)의 테이블과 **100% 일치**하는 세부도 달성.

### 2.3 v9의 회귀 (Regression) 항목

⚠️ **중요:** v9는 v8 대비 정답지 일치도가 **-1pp 소폭 감소** — 다음 2개 회귀가 원인.

#### (1) DFX 4-node iJTAG chain 정보 유실 (-55pp local)

v8 리뷰에서 집중 조명한 **4-node 양방향 체인 (instrn_engine_wrapper_dfx → disp_eng_noc_niu_router_dfx → overlay_wrapper_dfx → dfd)** 정보가:

- **v8:** [claude_review_v8.md §1.2-(4)](claude_review_v8.md) — "v8 NEW: overlay_wrapper_dfx 추가, instrn upstream (t6_l1 + fpu_gtile_0/1)"
- **v9:** [v9_N1B0_HDD.md](../v9/v9_N1B0_HDD.md)에 **DFX 섹션 없음** (§1~13), grounded 버전(§13)도 `[FROM LLM] iJTAG 스캔 체인 + BIST` 한 줄로 요약
- **정답지:** `N1B0_DFX_HDD_v0.1.md` 252줄 상세 + iJTAG DfT chain + wrapper 4종

**원인 추정:**
- v9는 Hybrid 그라운딩 **태그 체계 구축에 집중**하느라 v8의 KB 팩트 일부가 통합 프로세스에서 **drop**됨
- 특히 **topic 파일 분할(chip/edc/noc/overlay)이 DFX topic 파일을 생성하지 않음** → DFX 정보가 어느 topic에도 소속되지 못하고 누락

**영향:** DFX 체인은 정답지 커버리지의 **핵심 "RTL-extractable" 구간**으로, v8에서 어렵게 확보한 성과임. 회복 필수.

#### (2) SFR Memory Config 4-family 정보 유실 (-15pp local)

v8 리뷰 §1.2-(3)에 기록된 **4개 SRAM family 식별**:
- `SFR_RF_2P_HSC_*` (2-port HSC SRAM)
- `SFR_RA1_HS_*` (1-port HS)
- `SFR_RF1_HS_*` (1-port HS RF)
- `SFR_RF1_HD_*` (1-port HD RF)

→ **v9에서 `SFR_Memory_Config | 17 | SRAM configuration ports` 한 줄로 압축**. grounded는 `[FROM LLM] RF_2P_HSC_LVT_32X136M1FB1WM0DR0` 하나만 언급하고 나머지 3종 사라짐.

**원인 추정:** `max_results` 파라미터는 v8(50)과 동일하게 유지되었으나, **통합 merge 단계에서 SFR 내부 세부가 "17 ports" 한 줄로 요약**되었을 가능성. Prompt 설계에서 **"카테고리별 대표 신호 1개만 표시"** 규칙이 들어간 것이 아닌가 의심.

### 2.4 여전히 남은 gap (v8 대비 큰 변화 없음)

| 카테고리 | 정답지에만 존재 | v9에서 누락 이유 | 해결 경로 |
|----------|----------------|------------------|----------|
| **N1B0 vs Baseline 차이 테이블** | 10행 비교표 (grid/NIU/repeaters/PRTN/ISO_EN/REP_DEPTH) | Spec 히스토리 정보 | **v10 Spec RAG** |
| **ASCII 블록 다이어그램** | 4×5 grid 20 EP 시각화 | 정답지 §1.2 | **LLM prompt 보강** (RTL에서 재구성 가능) |
| **EP 인덱스 20행 테이블** | X/Y/Tile/EP 완전 매핑 | 정답지 §2.3 | **Package Parser 확장** (EP 계산 로직 추가) |
| **AXI gasket 56b 구조** | [55:52]rsvd/[51:46]Y/[45:40]X/[39:0]local | **v10 Spec RAG** |
| **NoC 알고리즘 pseudocode** | DOR tendril force_dim | tt_noc_pkg.sv 미추출 | **v9.x noc_pkg 파서** |
| **Flit 구조** | 2048b payload + 3b type + 32b parity | Spec 성격 | **v10 Spec RAG** |

---

## 3. v8 → v9 진화 분석

### 3.1 **개선 레이어가 다시 바뀌었다**

| | v6c→v7 | v7→v8 | **v8→v9** |
|---|--------|-------|-----------|
| 변경 본질 | KB 데이터 밀도 증가 | 검색 cutoff 확대 | **Hybrid 그라운딩 태그 체계 + 파이프라인 구조화** |
| 대표 변경 | Port Classifier + MCP 800char | max_results 20→50 | **prompt 4개 분할 + 2-way 출력(grounded/no_grounding) + merge 파이프라인** |
| 변경 코드량 | parser 수십 줄 | 파라미터 1개 | **prompt 템플릿 + 후처리 merge 로직** |
| 정답지 일치도 | → 55% | → 68% | **→ 67% (수평)** |
| 효과 성격 | 기존 범주 두께 증가 | KB visibility 극대화 | **"측정 가능성" 확보 (A/B, gap 정량화)** |

**통찰 1 — "측정 레이어"의 등장:** v5→v8은 모두 **"정답지 일치도"라는 단일 숫자**를 올리는 작업이었다. v9는 **이 숫자 자체보다 "어느 섹션이 LLM, 어느 섹션이 KB, 어느 섹션이 빈칸"을 스스로 분류하는 파이프라인**을 만든 것. 이는 **v10 Spec RAG 도입 후 "어느 빈칸이 Spec에서 채워졌는가"를 정량 측정할 수 있게 하는 사전 작업**으로 가치가 있다.

**통찰 2 — regression risk:** v9에서 DFX/SFR-family 정보가 유실된 것은 **파이프라인 구조 변경 시 KB 팩트 누락을 체크하는 regression test가 없음**을 시사. v9.x에서 **"v8→v9 정보 유실 체크리스트"를 자동 생성**하는 CI 도입이 필요.

### 3.2 v8 권고 사항 → v9 반영 여부

이전 [claude_review_v8.md §4.2](claude_review_v8.md)의 "v8.x 단기 보강" 권고와 v9 반영:

| v8 권고 | v9 반영 | 비고 |
|---------|---------|------|
| max_results sweep 실험 | ❓ 미확인 | 파이프라인 구조 변경이 우선시된 것으로 보임 |
| topic별 max_results 차등 설정 | 🟡 **부분** — topic 파일 4개 분할로 논리적 차등 구현 | EDC/NoC/Overlay/Chip 각각 다른 검색 공간 |
| **진짜 Hybrid 그라운딩 도입** | ✅ **완전 반영** | `[FROM LLM]`/`[NOT IN KB]` 태그 + KB Coverage Matrix |
| noc_pkg.sv 전용 파서 | ❌ 미반영 | 여전히 DOR/force_dim pseudocode 부재 |

**중요:** v8 리뷰의 "진짜 Hybrid 그라운딩" 권고가 **정확하게 v9에 반영**된 것은 파이프라인 개선 방향이 리뷰 피드백과 결이 맞다는 긍정 신호. 반면 `noc_pkg` 파서는 후순위로 밀린 것으로 보이며, v9.x에서 재차 제기 필요.

### 3.3 v9 내부 일관성 점검

v9 **통합 HDD vs topic 파일** 교차 확인:

| 항목 | topic 파일 | v9_N1B0_HDD.md (통합) | 일치? |
|------|-----------|----------------------|------|
| Port 106개 카테고리 | [v9_chip_no_grounding §3](../v9/v9_chip_no_grounding.md) ✅ | §3 ✅ | ✅ |
| PRTN 14-port 테이블 | [v9_chip_no_grounding §10](../v9/v9_chip_no_grounding.md) ✅ | **§11 간략화됨** | 🟡 |
| EDC 16-port 테이블 | [v9_edc §4](../v9/v9_edc.md) ✅ | **§8 간략화됨** | 🟡 |
| NoC 9개 모듈 | [v9_noc §3](../v9/v9_noc.md) ✅ | §7 ✅ | ✅ |
| Overlay 3개 FDS | [v9_overlay §3](../v9/v9_overlay.md) ✅ | §12 ✅ | ✅ |
| DFX 4-node chain | **어느 파일에도 없음** | **없음** | ❌ |

→ **통합 HDD가 topic 파일을 손실 압축하는 경향 관찰**. EDC/PRTN은 topic 파일에만 전체 테이블이 있고 통합본에서는 요약된다. 읽는 사람이 **통합 HDD만 보면 정답지 대비 부족해 보임** — 통합 프로세스의 merge 로직을 **"topic의 테이블은 보존"** 방향으로 조정 필요.

### 3.4 grounded vs no_grounding A/B 초기 관찰

| 항목 | no_grounding | grounded | 결론 |
|------|--------------|----------|------|
| PRTN 14-port table | ✅ full table | 🟡 "14 PRTN_Power ports — KB" 한 줄 | **no_grounding이 더 상세** |
| tile_t enum | ❌ 없음 | ✅ `[FROM LLM]` 8종 명시 | **grounded가 더 상세** |
| SRAM 카운트 | ❌ 없음 | ✅ `[NOT IN KB]` 솔직 고백 | **grounded가 더 투명** |
| DFX | ❌ 없음 | ✅ `[FROM LLM]` iJTAG/BIST | **grounded가 더 상세** |
| EDC 16-port | ✅ full table | ❌ "KB" 요약 | **no_grounding이 더 상세** |

**패턴:** **grounded 버전은 LLM 지식 보충 영역에서 강하고, no_grounding 버전은 KB 직접 추출 영역에서 강함**. 이는 두 Prompt가 **서로 다른 LLM 행동 편향을 유도**함을 시사:
- grounded Prompt → LLM이 **"빈칸을 채워야 한다"는 책임감**으로 domain knowledge 활성화
- no_grounding Prompt → LLM이 **KB 팩트만 엄격 제시**, 빈칸은 그대로 남김

**권고:** 두 버전을 **섹션별로 best-of merge**하는 **v9.1 파이프라인** 제안. 예: tile_t enum은 grounded, PRTN 테이블은 no_grounding에서 가져오기.

---

## 4. 품질 지표 재해석 (경영진 보고 관점)

### 4.1 RAG_Farm_Strategy_v1.5 업데이트 반영 숫자

| 지표 | v6c | v7 | v8 | **v9** | 메모 |
|------|-----|----|----|----|------|
| **Content Fidelity (가중)** | ~45% | ~55% | ~68% | **~67%** | 수평 |
| KB Hit Rate | 70%+ | 75%+ | 85%+ | **85%+** | 유지 |
| Port Coverage | 0% | 29% | 100% | **100%** | 유지 |
| **`[NOT IN KB]` 선언 가능성** | ❌ | ❌ | ❌ | **✅ (2개 섹션)** | **구조적 신규** |
| **섹션별 gap 자동 집계** | ❌ | ❌ | ❌ | **✅ (KB Coverage Matrix)** | **구조적 신규** |
| **경영진 보고용 단일 통합 HDD** | ❌ | ❌ | ❌ | **✅ ([v9_N1B0_HDD.md](../v9/v9_N1B0_HDD.md))** | **구조적 신규** |
| **Hallucination 격리** | 환각 없음 | 환각 없음 | 환각 없음 | **명시적 `[FROM LLM]` 태그** | 정성적 개선 |

### 4.2 v1.5 로드맵 예측 vs 실측 (업데이트)

| 버전 | v1.4 예측 | 실측 | 차이 | 비고 |
|------|----------|------|------|------|
| v7 | 72% | 55% | -17pp | Port Classifier만으로는 한계 |
| v8 | 78% | 68% | -10pp | max_results 도약 |
| **v9 (Hybrid)** | **82%** | **67%** | **-15pp** | **예측보다 낮음 — regression 원인** |
| v10 (Spec RAG) | 88%+ | TBD | — | 다음 마일스톤 |

**격차 재확대:** v7→v8은 격차가 좁혀졌으나 v9에서 다시 벌어짐. 원인은 **Hybrid 태그 도입의 비용 (DFX/SFR 정보 유실)**. v9.x에서 **regression 복구 + 태그 체계 유지**로 70% 돌파 가능할 것으로 재전망.

### 4.3 경영진 보고 권장 내러티브

- **v9 = "측정 체계 성립"** — 정답지 대비 숫자는 v8과 수평이지만, **"어느 정보가 KB에서 왔고 어느 정보가 LLM 추론인지"를 문서가 스스로 선언**하는 파이프라인이 처음 작동.
- **"통합 HDD 자동 생성"** 기능 확보 — v9 이전에는 리뷰어가 수작업으로 topic 파일을 읽었으나, 이제 **경영진이 볼 단일 문서**(`v9_N1B0_HDD.md`)가 자동 생성된다는 소구점.
- **Spec RAG 준비 완료 신호** — v9의 `[NOT IN KB]` 섹션 = **v10 Spec RAG가 채워야 할 정확한 빈칸**. 즉 "Spec RAG 합류 후 몇 %p 올랐다"를 **정량 측정할 수 있는 인프라**가 v9에서 마련됨.

**주의 포인트:** "왜 v9는 v8보다 숫자가 내려갔나?"라는 질문에 대해:
- "v9는 **새로운 그라운딩 태그 체계 구축 과정에서 일시적 회귀가 있었고, v9.x 패치(DFX/SFR 복구)로 수복 예정**"
- 즉, **v9의 가치는 숫자가 아니라 "Spec RAG 측정 인프라"에 있음**을 강조

---

## 5. 권고

### 5.1 즉시 유지
- ✅ **Hybrid 그라운딩 태그 체계** — v9의 핵심 성과, 되돌리지 말 것
- ✅ **grounded / no_grounding 2-way 출력** — A/B 실험 기반으로 유지
- ✅ **통합 HDD 파이프라인** — Appendix 소스 추적 테이블 포함
- ✅ KB Coverage Matrix — v1.5 보고서의 정량 근거

### 5.2 v9.x 단기 보강 (다음 v10 이전)

1. **🔥 DFX 정보 복구 (최우선)** (즉시)
   - v8 `claude_review_v8.md §1.2-(4)`의 **4-node 양방향 iJTAG chain** 복구
   - topic 파일에 **DFX 전용 파일(`v9_dfx.md`)** 추가 또는 chip 파일에 DFX 섹션 명시
   - 기대 +10pp

2. **🔥 SFR SRAM family 4종 복구 (최우선)**
   - `SFR_RF_2P_HSC_*` / `SFR_RA1_HS_*` / `SFR_RF1_HS_*` / `SFR_RF1_HD_*` 4-family 인벤토리 통합본에 포함
   - merge 로직에서 "port 카테고리 내부 서브 패턴 표시" 옵션 활성화
   - 기대 +5pp

3. **grounded/no_grounding best-of merge 실험**
   - 섹션별로 두 버전 중 더 상세한 쪽을 자동 선택
   - PRTN/EDC 테이블은 no_grounding에서, tile_t/DEST/SRCB는 grounded에서
   - 기대 +3~5pp

4. **noc_pkg.sv 전용 파서** (v8 리뷰에서 이어짐)
   - flit struct, 라우팅 테이블 추출
   - 기대 +3pp

5. **regression test 도입**
   - v8 → v9 회귀 방지 체크리스트 자동화
   - 다음 v10 이전 릴리스마다 "v8의 핵심 KB 팩트"가 유지되는지 확인

### 5.3 v10 (Spec RAG) — 다음 큰 도약 준비

- v9의 `[NOT IN KB]` 섹션을 **v10 Spec RAG의 검색 타겟**으로 직접 활용
- 특히 **N1B0 vs Baseline 차이 테이블**, **AXI 56b gasket 의미**, **flit 구조**는 Spec에서만 해결 가능
- v10 릴리스 후 **"그라운딩 매트릭스 before/after"**를 비교하면 Spec RAG 기여도 정량 증명 가능

### 5.4 v9의 교훈 — v1.5 보고서 반영 사항

- **"구조적 개선은 일시적 regression을 동반한다"**: v9는 측정 체계 구축 과정에서 v8의 일부 KB 팩트를 유실. 다음부터 **파이프라인 구조 변경 시 regression suite 필수**.
- **"숫자가 전부가 아니다"**: v9의 67%는 v8의 68%와 사실상 동일하지만, **"67%를 설명 가능하게 구성"**한 것이 진짜 가치. 경영진 보고 시 **정량 지표와 정성 지표를 분리해 제시**.
- **"Spec RAG 도입을 위한 측정 인프라가 v9에서 완성"** — 이것이 v9의 단 하나의 핵심 소구점이자, v10 투자 근거.

---

## 6. 코멘트

- v9는 **"제품 단계로의 전환점"**. v5~v8이 "정답 맞추기 경주"였다면 v9는 **"답안의 근거를 제시하는 시험지"**로 진화. Hybrid 태그 체계는 RAG 시스템의 **신뢰성 계층(trust layer)**을 처음 도입한 것.
- **회귀 이슈(DFX/SFR)는 설계 복잡화의 자연스러운 부작용**. v7→v8이 파라미터 1개 변경의 드문 성공 사례였다면, v9는 **프로덕션 RAG에서 흔한 "구조 리팩터링 후 기능 회복"** 패턴. v9.x 한두 스프린트로 복구 가능.
- **v1.5 보고서의 v9 프레이밍**: "숫자는 수평이나 측정 인프라 구축 완료 → v10 Spec RAG가 정량 평가 가능" — **정직하면서도 전략적 가치를 명확히** 전달하는 표현 권장.
- v9가 달성한 **`[NOT IN KB]` 선언 능력**은 **경영진이 처음으로 "아직 모르는 것"을 측정해볼 수 있는 지표** — 이는 RAG 시스템에서 흔치 않은 정직성으로, 조직 내부 신뢰도 상승에 기여할 것.

---

*Review complete — 2026-05-06*
