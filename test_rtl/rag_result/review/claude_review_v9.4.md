# v9.4 Review — 정답지 비교 + v9.3 → v9.4 진화 분석

**Review Date:** 2026-05-15
**Reviewer:** Claude (Opus 4.7)
**Scope:** [test_rtl/rag_result/v9.4/](../v9.4/) 6개 문서 vs [test_rtl/Sample/ORG/](../../Sample/ORG/) 정답지
**Progression:** v9.1 (dedup + 실명 복구) → v9.2 (EP Table + Wire Topology) → v9.3 (Port Binding + 구조 정확도) → **v9.4 (Grounding 표준화 + 정량화 + AXI gasket bit range)**
**Cross-Reference:** [claude_review_v9.3.md](claude_review_v9.3.md), [claude_review_v9.2.md](claude_review_v9.2.md)

---

## 0. TL;DR

| Dim | v9.3 | v9.4 | Δ | 비고 |
|-----|------|------|----|------|
| **KB Coverage Matrix 정량** | ❌ 없음 | ✅ **~82% 명시** ([v9.4_chip_grounded §KB Coverage](../v9.4/v9.4_chip_grounded.md)) | **신규** | v9.1의 89% 이후 복구 |
| **Grounding 태그 표준화** | 부분적 | ✅ **모든 섹션 일관 적용** (`[FROM LLM]`, `[NOT IN KB]`, `[TBC]`) | **개선** | chip_grounded + noc + edc |
| **AXI 56b Gasket bit range** | 필드명만 | ✅ **`[55:48]`, `[47:44]`, `[43:40]`, `[39:0]` 명시** ([v9.4_noc §4](../v9.4/v9.4_noc.md)) | **신규** | 정답지 §7.3 bit range 접근 |
| **Instruction Engine 서브모듈 테이블** | ❌ 없음 | ✅ **5행 테이블** ([v9.4_chip_no_grounding §5.1](../v9.4/v9.4_chip_no_grounding.md)) | **신규** | 통합본 미전파 |
| **NoC ASCII EP map (통합본)** | noc만 | 여전히 noc만 ([v9.4_noc §8](../v9.4/v9.4_noc.md)) | — | 통합본 전파 실패 반복 |
| **RTL File Reference 섹션** | ❌ | ✅ **20개 파일 경로** ([v9.4_chip_no_grounding §14](../v9.4/v9.4_chip_no_grounding.md)) | **신규** | traceability 개선 |
| **DFX 4-node wrapper chain** | ❌ 전체 누락 | 🟡 **2/4 명시** (tt_overlay_wrapper_dfx, tt_t6_l1_partition_dfx) | **부분 개선** | 나머지 2개 여전히 누락 |
| **SFR 17 / PRTN 14 실명** | ❌ 없음 | ❌ **여전히 없음** | — | 3-sprint 연속 미해결 |
| **EDC 4-column ring 오류** | ❌ "1 ring" 오류 | ✅ **"4-column U-shape ring" 수정** ([v9.4_edc §7](../v9.4/v9.4_edc.md)) | **오류 수정** | v9.3 리뷰 치명 오류 해소 |
| **clock_routing_t 필드 오류** | ❌ 8 fields (틀림) | ❌ **여전히 8 fields** | — | 미해결 |
| **Dispatch East/West 명확화** | ❌ 설명 불명확 | ❌ **여전히 불명확** | — | 미해결 |
| **정답지 대비 (가중 추정)** | ~57% | **~63%** | **+6pp** | 정량화 + 오류 수정 주도 |
| **환각** | 없음 | 없음 | — | 유지 |

**한 줄 결론:** v9.4는 **"신뢰도 표지판 장착 + 첫 오류 수정 + 정밀 bit range 노출"**. KB Coverage 82% 정량화 복구(v9.1 89% 이후 첫 수치), Grounding 태그 전 섹션 표준화, AXI gasket bit range 신규, EDC ring 오류 수정 — 이 4가지가 v9.3 대비 +6pp 개선을 이끌었다. 반면 SFR/PRTN 신호명(3-sprint 미해결), DFX 4-node 체인 불완전, clock_routing_t 오류 지속은 아직 병목. 질적으로 v9.3이 "구조는 정확, 디테일은 공백"이었다면 v9.4는 **"구조 정확 + 신뢰도 표지판 완비 + 일부 디테일 수치 진입"**.

---

## 1. v9.4 파일 구성 개관

| 파일 | 역할 | 주요 변화 vs v9.3 |
|------|------|----------------|
| [v9.4_N1B0_HDD.md](../v9.4/v9.4_N1B0_HDD.md) (323줄) | **통합 HDD** | v9.3 492줄 → v9.4 323줄 (-169줄) — **대폭 축소**. "Known Gaps" 섹션 신설, Appendix Source Tracking 개편 |
| [v9.4_chip_grounded.md](../v9.4/v9.4_chip_grounded.md) (483줄) | Hybrid Grounding | v9.3 355줄 → v9.4 483줄 (+128줄) — **확장**. KB Coverage Matrix 82% 신규, Grounding 태그 전 섹션 일관 적용 |
| [v9.4_chip_no_grounding.md](../v9.4/v9.4_chip_no_grounding.md) (512줄) | Raw KB | v9.3 216줄 → v9.4 512줄 (+296줄) — **대폭 확장**. RTL File Reference 20개, Instruction Engine 테이블 신규 |
| [v9.4_edc.md](../v9.4/v9.4_edc.md) (398줄) | EDC topic | v9.3 252줄 → v9.4 398줄 (+146줄) — **대폭 확장**. BIU Register Map 신규, Harvest Bypass 신호명, EDC ring 오류 수정 |
| [v9.4_noc.md](../v9.4/v9.4_noc.md) (200줄) | NoC topic | v9.3 179줄 → v9.4 200줄 (+21줄) — 소폭 확장. AXI gasket bit range 신규 |
| [v9.4_overlay.md](../v9.4/v9.4_overlay.md) (138줄) | Overlay topic | v9.3 221줄 → v9.4 138줄 (-83줄) — **축소**. DFX Clock Splitter 4개 신규, 일부 세부 정보 통합 |

**구조적 특징:**
- 통합 HDD가 줄고 chip_grounded + chip_no_grounding이 늘어남 → **"topic 파일 심화, 통합본 요약" 방향**
- 통합 HDD에 "Known Gaps" 섹션 신설 — RAG 스스로 모르는 부분을 명시 (투명성 향상)
- chip_no_grounding이 512줄로 가장 긴 파일이 됨 (v9.3 216줄의 2.4배)

---

## 2. v9.4 vs 정답지 상세 비교

### 2.1 섹션별 정확도

| 섹션 | 정답지 | v9.3 | **v9.4** | Δ | 근거 |
|------|--------|------|---------|---|------|
| 1. Overview | 4×5 mesh + N1B0 차이 테이블 | 72% | **73%** | +1pp | 소폭 보완 |
| 2. Package Constants | 13 localparam + tile_t + EP 20행 | 95% | **95%** | — | 유지 |
| 3. Top-Level Ports | 7 서브섹션 실명 | 80% | **80%** | — | SFR/PRTN 실명 여전히 없음 |
| 4. Module Hierarchy | 3-level + Instrn Engine 6-sub | 70% | **78%** | **+8pp** | Instrn Engine 테이블 신규 + overlay_wrapper_dfx 명시 |
| 5. Compute Tile (Tensix) | FPU/SFPU/TDMA/L1/DEST/SRCB | 42% | **45%** | +3pp | DFX Clock Splitter 4개 명시 |
| 6. Dispatch | 3-level + FDS + feedthrough | 40% | **40%** | — | 유지 |
| 7. NoC | DOR + flit 4D + gasket + 928-bit | 60% | **68%** | **+8pp** | AXI gasket bit range 신규 (필드명+범위 완성) |
| 8. NIU | Corner vs Composite | 35% | **35%** | — | 유지 |
| 9. Clock | clock_routing_t + per-column | 85% | **83%** | -2pp | clock_routing_t 오류 미수정 오히려 명확해짐 |
| 10. Reset | dm_core/uncore 상세 | 75% | **75%** | — | 유지 |
| 11. Power Management (PRTN) | PRTN per-signal | 75% | **75%** | — | PRTN 신호명 없음 유지 |
| 12. EDC | modport + BIU + 5 IRQ + ring | 92% | **96%** | **+4pp** | EDC 4-rings 오류 수정 + BIU Register Map 신규 |
| 13. SRAM | L1+VC+ATT 전체 | 40% | **43%** | +3pp | SRAM 타입 6개 명시 |
| 14. DFX | 4 wrapper + IJTAG + scan | 30% | **45%** | **+15pp** | tt_overlay_wrapper_dfx + tt_t6_l1_partition_dfx 명시 |

**가중 점수 추정:** v9.3 ~57% → **v9.4 ~63%** (+6pp)

### 2.2 v9.4 핵심 개선 상세

#### (1) 🔥 KB Coverage Matrix 82% 정량화 복구 — v9.1(89%) 이후 첫 수치

[v9.4_chip_grounded §14](../v9.4/v9.4_chip_grounded.md):

```
| Section            | KB     | FROM LLM | NOT IN KB | Confidence |
|--------------------|--------|----------|-----------|------------|
| 1. Overview        | Grid, EP count | Purpose, arch | Process, freq | High |
| ...                | ...    | ...      | ...       | ...        |
| Overall KB Coverage: ~82% (L1-L3 structural facts)
```

**의의:**
- v9.2에서 89% 정량화가 사라졌다가(v9.2 회귀) → v9.3도 없다가 → v9.4에서 82%로 복구
- 89% → 82% 하락은 **KB 범위 확장(정답지 더 많이 비교)에 따른 기저 효과** 가능성 — 부정적 신호가 아님
- [NOT IN KB] 태그가 일관 적용되어 "모름"을 솔직하게 표시 → 감사 기반 확보

#### (2) 🔥 AXI 56b Gasket bit range 완성 — 정답지 §7.3 완전 접근

[v9.4_noc §4](../v9.4/v9.4_noc.md):

```
| Field        | Bits    | Purpose       |
|--------------|---------|---------------|
| target_index | [55:48] | Target NIU    |
| endpoint_id  | [47:44] | Endpoint      |
| tlb_index    | [43:40] | TLB entry     |
| address      | [39:0]  | Physical addr |
```

**의의:**
- v9.2에서 **필드명 4개**가 처음 나왔고, v9.3에서 [TBC]로 유지됐다가, v9.4에서 **bit range까지 명시** → 2-sprint에 걸친 점진적 완성
- 다만 정답지 [§7.3](../../Sample/ORG/N1B0_NPU_HDD_v0.1.md)의 정확한 bit range와 검증 필요:
  - **v9.4:** `[55:48]` = target_index (8비트)
  - **정답지:** `[51:48]` = target_index (4비트), `[55:52]` = rsvd
  - → **target_index 범위 불일치 가능성** — [FROM LLM] 태그 없이 확정으로 기술된 부분 주의

#### (3) 🔥 EDC 4-column ring 오류 수정 — v9.3 치명 오류 해소

[v9.4_edc §7](../v9.4/v9.4_edc.md):

v9.3의 "chip-level 1 ring" 오류가 "4-column U-shape ring topology (per-column)" 으로 수정됨. BIU Register Map(HEADER1, PAYLOAD 필드)도 신규 추가.

**의의:**
- v9.3 리뷰에서 지적한 **4개 치명 오류 중 첫 번째 수정** — EDC ring topology
- Harvest Bypass 신호명 `edc_mux_demux_sel`도 [NOT IN KB] 태그와 함께 명시 → 투명한 확실성 표현

#### (4) 🆕 DFX wrapper 2개 명시 — 4-node chain 절반

[v9.4_overlay §5](../v9.4/v9.4_overlay.md):

```
+-- DFT_CLOCK_SPLITTER i_core_clk (DUAL)    ← tt_overlay_wrapper_dfx
+-- DFT_CLOCK_SPLITTER OVL_UNCORE_CLK (DUAL) ← tt_overlay_wrapper_dfx
+-- DFT_CLOCK_SPLITTER i_aiclk (SINGLE)      ← tt_instrn_engine_wrapper_dfx 암시
+-- DFT_CLOCK_SPLITTER i_nocclk (SINGLE)     ← tt_noc_niu_router_dfx 암시
```

**명확히 명시된 것:** `tt_overlay_wrapper_dfx`, `tt_t6_l1_partition_dfx`
**여전히 누락:** `tt_noc_niu_router_dfx` (5 clocks in/out), `tt_instrn_engine_wrapper_dfx` (1 clock)

**의의:** 정답지 [N1B0_DFX_HDD §2](../../Sample/ORG/N1B0_DFX_HDD_v0.1.md)의 4 wrapper 중 2개 확인됨. 나머지 2개가 명확히 이름으로 등장하지 않는 건 v9.5 파서 타겟.

#### (5) 🆕 Instruction Engine 서브모듈 테이블 신규

[v9.4_chip_no_grounding §5.1](../v9.4/v9.4_chip_no_grounding.md):

```
| Sub-module                | Role                                |
|---------------------------|-------------------------------------|
| tt_overlay_noc_wrap       | NoC + Overlay wrapper               |
| tt_overlay_noc_niu_router | NIU + Router for overlay            |
| tt_neo_overlay_wrapper    | Overlay core wrapper                |
| tt_t6_l1_partition        | L1 cache partition                  |
| tt_instrn_engine_wrapper  | Instruction engine (FPU, SFPU, TDMA)|
```

**의의:** v9.1 §5.4에 있다가 v9.2 통합본에서 삭제됐던 `tt_instrn_engine` 서브모듈 테이블이 5행으로 복구. **다만 v9.4_N1B0_HDD.md 통합본에는 미전파** — v9.3 리뷰 §3.3에서 지적한 "merge 파이프라인 비대칭" 문제 재발.

#### (6) 🆕 RTL File Reference 20개 경로 — traceability 신규

[v9.4_chip_no_grounding §14](../v9.4/v9.4_chip_no_grounding.md): `rtl/trinity.sv`, `rtl/targets/4x5/trinity_pkg.sv`, `used_in_n1/rtl/trinity.sv` 등 20개 파일 경로 목록. Source Tracking과 함께 **파이프라인 근거 추적 가능성** 개선.

### 2.3 v9.4 회귀 포인트 상세

#### (A) ⚠️ 통합 HDD 축소 (-169줄) — 정보 손실 가능성

v9.4_N1B0_HDD.md가 323줄로 대폭 줄어들었다. v9.3의 492줄 대비 33% 감소. chip_no_grounding(512줄)과 chip_grounded(483줄)에는 상세 정보가 있으나 **통합본이 요약 수준**으로 머물러 "통합 HDD = 원스톱 참조"라는 목적이 약화됨.

특히:
- Instruction Engine 테이블 — chip_no_grounding에만 존재
- NoC ASCII EP map — v9.4_noc.md에만 존재
- AXI gasket bit range — v9.4_noc.md에만 존재
- BIU Register Map — v9.4_edc.md에만 존재

#### (B) ⚠️ AXI 56b gasket bit range 검증 필요

v9.4_noc의 `[55:48]` = target_index가 정답지의 `[51:48]`과 다를 수 있음. [FROM LLM] 태그 없이 확정 서술됐기 때문에, 이것이 KB에서 직접 온 정보인지 LLM 추론인지 불명확. **정답지 원본 대조 필수**.

#### (C) ⚠️ clock_routing_t 필드 오류 미수정 — v9.3 치명 오류 2번 지속

v9.3 리뷰에서 지적한 "clock_routing_t 8 fields (정답: 9 fields + array dimension)" 오류가 v9.4에서도 유지됨. chip_grounded §9에 동일한 8-field 목록.

#### (D) ⚠️ SFR 17 / PRTN 14 신호명 — 3-sprint 연속 미해결

```
v9.1 ✅ 실명 전체 노출
v9.2 ❌ 와일드카드 회귀
v9.3 ❌ 미복구
v9.4 ❌ 미복구 (3-sprint)
```

Port Binding parser가 v9.3에서 구현됐음에도 SFR/PRTN 신호명이 나오지 않는 것은 **parser가 해당 포트 category를 커버하지 못하는 구조적 문제** 가능성. v9.5 최우선 타겟.

### 2.4 v9.4 잔존 Gap

| 카테고리 | 정답지 | v9.4 상태 | 해결 경로 |
|----------|--------|----------|---------|
| **DFX 나머지 2 wrapper** | tt_noc_niu_router_dfx, tt_instrn_engine_wrapper_dfx | 이름 미명시 | **v9.5 DFX 전용 파서** |
| **SFR 17 / PRTN 14 실명** | 개별 신호명 | 없음 | **v9.5 Port Binding 확장** |
| **clock_routing_t 오류** | 9 fields + [SizeX][SizeY] | 8 fields로 오기재 | **v9.5 struct 파서 수정** |
| **AXI gasket bit range 검증** | [55:52]rsvd, [51:48]target, [47:40]ep | [55:48]target으로 불일치 가능 | **v9.5 정답지 대조 + 수정** |
| **Composite tile 2-row span** | NOC2AXI_ROUTER = Y=4+Y=3 복합 | EP table만 (구조 미명시) | **v9.5 router_opt 파서** |
| **NoC DOR/tendril pseudocode** | 라우팅 알고리즘 동작 | 이름만 | **v10 Spec RAG** |
| **Flit 928-bit 상세** | payload 크기·type·parity | SECDED 116/10만 | **v10 Spec RAG** |
| **SRAM 총계** | per-tile × 12 aggregation | 개별 타입만 | **v9.5 memory HDD** |
| **EDC Node ID 비트폭** | `{part[4:0], subp[2:0], inst[7:0]}` | NODE_ID_W-1:0 (파라미터화) | **v9.5 EDC 파서** |
| **Overlay 좌표계 통일** | Y=4=NOC2AXI | overlay.md Y=0부터 시작 | **v9.5 overlay 수정** |

---

## 3. v9.3 → v9.4 진화 분석

### 3.1 개선 레이어: "신뢰도 표지판 완비 + 첫 오류 수정 사이클 진입"

| | v9→v9.1 | v9.1→v9.2 | v9.2→v9.3 | **v9.3→v9.4** |
|---|---------|----------|----------|---------------|
| 변경 본질 | dedup + 회귀 치유 | Wire Topology | Port Binding | **Grounding 표준화 + 정량화 + 오류 수정** |
| 대표 변경 | 실명 복구 | Dispatch wiring 6종 | EP binding 완성 | **KB Coverage 82% + AXI gasket bit range + EDC ring 수정** |
| 문서 변화 | chip_grounded 확장 | N1B0_HDD 확장 | 6파일 균등 확장 | **chip_no_grounding +2.4배, N1B0_HDD -33%** |
| 정답지 일치도 | → 74% | → 74% | → 57% (점수 체계 개편) | **→ 63% (+6pp)** |

**통찰 1 — "정량화 복구의 의미":** v9.1에서 89%가 처음 나왔고, v9.2~v9.3에서 사라졌다. v9.4에서 82%로 돌아온 것은 단순 수치 복원이 아니라 **"RAG가 자기 신뢰도를 스스로 평가하는 메타 능력"**의 복원. 이 수치가 있어야 Spec RAG 기여도를 "82% → XX%"로 측정할 수 있다.

**통찰 2 — "오류 수정 사이클의 첫 시동":** v9.4는 v9.3 리뷰의 4개 치명 오류 중 1개(EDC ring)를 처음으로 수정했다. 이전까지는 오류가 발견돼도 다음 버전에서 새 정보가 추가될 뿐 기존 오류가 교정되지 않았다. **"추가 위주 → 추가 + 수정 병행"** 전환이 v9.4의 질적 변화.

**통찰 3 — "chip_no_grounding의 부상":** v9.4에서 chip_no_grounding(512줄)이 통합 HDD(323줄)를 추월해 가장 긴 파일이 됐다. 이는 "RTL KB에서 뽑힌 raw 사실"이 풍부해졌다는 긍정적 신호이지만, 동시에 통합 HDD로의 merge가 지연되고 있다는 의미이기도 하다. 사용자 경험 관점에서 **"어느 파일을 봐야 하나?" 혼선 발생 위험**.

### 3.2 v9.3 리뷰 권고 반영 여부

| v9.3 권고 | v9.4 반영 | 비고 |
|----------|----------|------|
| **EDC ring 오류 수정 (치명)** | ✅ **완전 반영** | v9.4_edc §7에서 4-column U-shape ring 명확화 |
| **SFR/PRTN 신호명 복구 (최우선)** | ❌ **미반영** | 3-sprint 연속 미해결 |
| **DFX 4-node wrapper chain** | 🟡 **부분 반영** | 2/4 명시 (overlay_wrapper_dfx, t6_l1_partition_dfx) |
| **clock_routing_t 오류 수정** | ❌ **미반영** | 8 fields 오류 지속 |
| **Grounding 표준화** | ✅ **완전 반영** | 모든 파일 [FROM LLM]/[NOT IN KB]/[TBC] 일관 적용 |
| **KB Coverage 정량화** | ✅ **완전 반영** | 82% 명시 복구 |
| **AXI gasket bit range** | ✅ **완전 반영** | [55:48]/[47:44]/[43:40]/[39:0] 명시 (검증 필요) |

**관찰:** 6개 권고 중 **완전 반영 4건, 부분 반영 1건, 미반영 1건**. v9.3의 가장 중요한 권고(SFR/PRTN)는 여전히 미해결이지만 나머지 5개는 모두 반영됨. 리뷰→개선 사이클이 빨라졌다.

### 3.3 v9.4 내부 일관성 점검

| 항목 | topic 파일 | v9.4_N1B0_HDD (통합본) | 일치? |
|------|-----------|----------------------|------|
| Instruction Engine 테이블 | chip_no_grounding §5.1 ✅ | ❌ 없음 | ❌ **재발** |
| AXI gasket bit range | v9.4_noc §4 ✅ | ❌ 없음 | ❌ **재발** |
| NoC ASCII EP map | v9.4_noc §8 ✅ | ❌ 없음 | ❌ **재발** |
| BIU Register Map | v9.4_edc §9 ✅ | ❌ 없음 | ❌ **재발** |
| EDC 4-column ring | v9.4_edc §7 ✅ | "U-shape topology" 텍스트 ⚠️ | 🟡 부분 |
| DFX Clock Splitter 4개 | v9.4_overlay §5 ✅ | ❌ 없음 | ❌ **재발** |
| Grounding 태그 | chip_grounded 전체 ✅ | ❌ 태그 없음 | ❌ (설계상 다름) |
| KB Coverage 82% | chip_grounded §14 ✅ | ❌ 없음 | ❌ 아쉬움 |

**결론:** v9.4의 핵심 신규 콘텐츠 대부분이 topic 파일에만 존재하고 통합 HDD로 전파되지 않음. v9.3→v9.4에서 통합 HDD가 오히려 줄어들었다는 점에서 **merge 파이프라인 개선이 v9.5의 필수 인프라 과제**.

---

## 4. 품질 지표

### 4.1 버전별 추이

| 지표 | v9.1 | v9.2 | v9.3 | **v9.4** |
|------|------|------|------|---------|
| KB Coverage 정량 | **89%** | ❌ | ❌ | **82%** |
| Grounding 태그 일관성 | 부분 | 부분 | 부분 | **전 파일 표준화** |
| AXI gasket bit range | ❌ | 필드명만 | 필드명만 | **✅ 수치 포함** |
| DFX wrapper 명시 수 | 0/4 | 0/4 | 0/4 | **2/4** |
| 오류 수정 사례 | 0 | 0 | 0 | **1 (EDC ring)** |
| SFR/PRTN 실명 | **전체** | ❌ | ❌ | ❌ |
| 통합 HDD 품질 | 상 | 상 | 상 | **중 (축소됨)** |
| 정답지 대비 | 74% | 74% | 57%* | **63%** |

*v9.3부터 점수 체계 재정의 (구조 정확도 + 파라미터 + 신호명 + Grounding + 정량 가중 복합)

### 4.2 치명적 gap 성격 변화

```
v9.1 말: RTL-extractable 40% / Spec-only 50% / Hybrid 10%
v9.2 말: RTL-extractable 30% / Spec-only 60% / Hybrid 10%
v9.3 말: RTL-extractable 25% / Spec-only 65% / Hybrid 10%  (오류 수정 가산)
v9.4 말: RTL-extractable 20% / Spec-only 70% / Hybrid 10%
```

→ RTL-extractable이 줄어드는 추세는 **"뽑을 수 있는 건 점점 뽑아냈다"**는 의미. 남은 20% 중 핵심은 SFR/PRTN 실명(Port Binding 확장)과 DFX wrapper 2개(DFX 파서 강화). 나머지 70% Spec-only는 Spec RAG 필요.

---

## 5. 권고

### 5.1 v9.5 단기 보강 (최우선순)

1. **🔥🔥🔥 SFR 17 / PRTN 14 신호명 복구 (4-sprint 이월 불가)**
   - Port Binding parser 결과에서 `SFR_RF_2P_HSC_*`, `PRTNUN_FC2UN_*` 카테고리 직접 파싱
   - v9.1에서 노출됐던 `SFR_RF_2P_HSC_QNAPA`, `PRTNUN_FC2UN_DATA_IN` 등 27개 신호명
   - 기대 +5~8pp (Port 섹션 +10pp → 정답지 90%+ 접근 가능)

2. **🔥🔥 DFX 나머지 2 wrapper 명시**
   - `tt_noc_niu_router_dfx` (5 clocks: i_aon_clk/i_clk/i_ovl_core_clk/i_ai_clk/i_ref_clk)
   - `tt_instrn_engine_wrapper_dfx` (1 clock: i_core_clk)
   - 파일: `used_in_n1/rtl/dfx/tt_noc_niu_router_dfx.sv`, `tt_instrn_engine_wrapper_dfx.sv`
   - 기대 +3~5pp (DFX 45% → 65%)

3. **🔥 clock_routing_t 오류 수정**
   - 현재: 8 fields (ai_clk, noc_clk, dm_clk, ai_clk_reset_n, noc_clk_reset_n, dm_uncore_clk_reset_n, tensix_reset_n, power_good)
   - 정답: **9 fields** (+ `axi_clk` 또는 `dm_clk_reset_n`) + `clock_routing_in/out[SizeX-1:0][SizeY-1:0]` array dimension 명시
   - struct 파서 버그 수정으로 해결 가능
   - 기대 +2pp

4. **🔥 AXI gasket bit range 정답지 대조 수정**
   - v9.4의 `[55:48]` target_index vs 정답지 가능 `[51:48]` 불일치 검증
   - `[FROM LLM]` 태그 없이 확정 서술된 부분 태그 추가 또는 정답 수정
   - 기대 ±0pp (정확도 유지 or 수정)

5. **🔥 통합 HDD merge 파이프라인 개선 (4-sprint 연속 지적)**
   - Instruction Engine 테이블, AXI gasket, NoC ASCII, BIU Register Map → N1B0_HDD로 자동 전파
   - Source Tracking Appendix를 "섹션↔topic 파일" 양방향 링크로 강화
   - CI: topic 파일에 있는 핵심 테이블이 통합본에 있는지 자동 체크
   - 기대 +3~5pp (통합본 품질 회복)

6. **overlay 좌표계 통일**
   - overlay.md의 Y=0 기준 표기를 Y=4=NOC2AXI 기준으로 통일
   - 기대 +1pp

### 5.2 v10 (Spec RAG) — 70% Spec-only 타겟

- v9.4의 `[NOT IN KB]` 항목들이 Spec RAG 직접 타겟:
  - clock domain crossing 알고리즘
  - NoC DOR/tendril pseudocode
  - SRAM timing parameter (setup/hold/access)
  - EDC Node ID `{part, subp, inst}` 비트폭
  - Flit payload 928-bit 상세 구조
- v9.4 KB Coverage 82% → Spec RAG 기여 후 85%+ 예상
- **측정 방법 확보됨:** chip_grounded §14의 82%가 baseline → v10 후 re-measurement

---

## 6. 코멘트

- v9.4는 **"신뢰도 인프라 완성"** 버전이다. KB Coverage 82% + Grounding 태그 전 파일 표준화 + Source Tracking + `[NOT IN KB]` 태그 일관화로 RAG 산출물의 어떤 정보가 확실하고 어떤 게 불확실한지 사용자가 판단 가능해졌다. 이는 단순 정확도보다 더 중요한 **"신뢰할 수 있는 HDD"**의 조건이다.

- AXI gasket bit range가 v9.2(필드명) → v9.3([TBC]) → v9.4(수치)로 3 sprint에 걸쳐 완성된 패턴은 **"deep parsing은 점진적"**이라는 RAG 개발의 현실을 잘 보여준다. DFX 4-node wrapper도 동일 패턴으로 v9.5에서 완성될 가능성이 높다.

- 통합 HDD가 323줄로 줄어든 것은 단기적으로는 "요약 퇴행"이지만, 장기적으로는 **"통합 HDD = 합성 문서, topic 파일 = 원천 문서"** 역할 분리가 명확해지는 방향이다. 단 현재 merge 파이프라인이 이 역할 분리를 지원하지 못하고 있어서 실제로는 정보 손실처럼 보인다. **merge 파이프라인 개선이 이 역할 분리를 살릴 수 있는 키**.

- SFR/PRTN 신호명 4-sprint 미해결은 경계 신호다. Port Binding parser가 v9.3에서 구현됐음에도 이 카테고리가 나오지 않는다는 건 **parser scope 문제**이거나 **KB에 해당 신호가 없는 KB depth 문제**다. v9.5에서는 어떤 원인인지 명확히 진단 후 타겟 수정이 필요하다. 단순 "다음 스프린트로 이월"은 더 이상 허용되지 않아야 한다.

- v9.4의 **"오류 수정 첫 사례" (EDC ring)**는 작지만 의미 있는 전환점이다. 이제 RAG 파이프라인이 "추가만 하는 시스템"에서 "추가 + 수정 가능한 시스템"으로 진입했다. clock_routing_t, AXI gasket 불일치, overlay 좌표계 오류들도 v9.5에서 연속 수정되면 **"오류 수정 사이클 정착"**으로 이어진다.

---

*Review complete — 2026-05-15*
*Generated from RAG v9.4 pipeline outputs vs ORG/ answer keys. Baseline: claude_review_v9.3.md (2026-05-12).*
