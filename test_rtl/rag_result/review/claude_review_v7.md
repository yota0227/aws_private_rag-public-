# v7 Review — 정답지 비교 + v6c → v7 진화 분석

**Review Date:** 2026-05-01
**Reviewer:** Claude (Opus 4.7)
**Scope:** `test_rtl/rag_result/v7/` 6개 문서 vs `test_rtl/Sample/ORG/` 정답지
**Progression:** v5.1 (RAG tuning) → v6c (Package Parser v2) → **v7 (Port Classifier + MCP 800char + HDD sub-module KB)**
**Cross-Reference:** `claude_review_v6.md`, `kiro_review_v6c.md`

---

## 0. TL;DR

| Dim | v6c | v7 | Δ | 비고 |
|-----|-----|----|----|------|
| **Top-Level Ports (섹션 3)** | 35% (8행) | **~70%** (3.1~3.4, DM/APB/EDC APB 풀포트) | **+35pp** | v7의 핵심 성과 |
| **Reset Architecture (섹션 10)** | 30% (4행) | **~65%** (DM core/uncore 추가) | +35pp | — |
| **TDMA 내부** | 이름만 (1 sub-module) | **3 sub-modules** 식별 | +질적 | — |
| **SRAM Inventory** | ATT 1종 | **RF_2P_HSC_LVT 32×136 추가** (EDC/NoC/DFX) | +질적 | — |
| **DFX iJTAG 체인** | 모듈 나열 | **토폴로지 방향성** (noc_niu_router_dfx → partition_dfx → dfd) | +질적 | — |
| **Package Constants** | 90% | 90% | — | 유지 |
| **Grid / tile_t / EP** | 100% | 100% | — | 유지 |
| **정답지 대비 (가중 추정)** | ~45% | **~55%** | **+10pp** | 점진적 도약 |
| **환각** | 없음 | 없음 | — | 유지 |

**한 줄 결론:** v7은 **"구조는 있으나 얇았던 영역(Ports/Reset/TDMA/SRAM/DFX)을 채워넣는 정밀 작업"**이다. v6c의 Package Parser가 "빈 섹션을 통째로 채웠다면", v7의 Port Classifier + MCP 800char 확장은 **"이미 있던 섹션을 두세 배 두껍게"** 만들었다. v6→v7 로드맵 예측(65%)에는 여전히 10pp 못 미치지만, **개선 궤적은 견고하게 유지** 중이며 남은 gap은 알고리즘/Spec 영역으로 **v8~v9에서 해결할 성격**.

---

## 1. v7 vs 정답지 상세 비교

### 1.1 Chip-level: `v7_N1B0_HDD.md` (404줄) vs `N1B0_NPU_HDD_v0.1.md` (1291줄)

| 섹션 | 정답지 | v6c 일치도 | **v7 일치도** | Δ | 근거 |
|------|--------|-----------|----------------|---|------|
| 1. Overview | 4×5 mesh + N1B0 차이 테이블 | 60% | 60% | — | 타일 구성은 동일 |
| 2. Package Constants | 10 localparam + tile_t + EP | 90% | **90%** | — | 유지 |
| **3. Top-Level Ports** | 7 서브섹션 (clock/reset/AXI/APB/EDC APB/PRTN/ISO) | **35%** | **~70%** | **+35pp** | **3.1~3.4 세분화, DM/APB/EDC APB 풀 시그널 복구** |
| 4. Module Hierarchy | 3-level generate | 40% | 50% | +10pp | TDMA/EDC/NoC 내부 모듈 추가 |
| 5. Compute Tile | FPU/SFPU/TDMA/L1/DEST/SRCB 7 서브 | 15% | **25%** | +10pp | TDMA 3 sub-module, L1 언급 복구 |
| 6. Dispatch | 3-level + FDS | 15% | 15% | — | 변화 없음 |
| 7. NoC | DOR + flit + gasket + 928-bit | 25% | 30% | +5pp | RF_2P SRAM 추가 |
| 8. NIU | Corner vs Composite + parameters | 30% | 30% | — | 변화 없음 |
| 9. Clock | clock_routing_t + per-column | 70% | **80%** | +10pp | i_dm_clk per-column 추가 |
| **10. Reset** | dm_core/uncore 상세 | **30%** | **~65%** | **+35pp** | **i_dm_core_reset_n[14][8], i_dm_uncore_reset_n[14] 복구** |
| 11. EDC | modport + BIU + 5 IRQ | 80% | **85%** | +5pp | RF_2P SRAM ×2 추가 |
| 12. Power Mgmt | PRTN + ISO_EN | 0% | 0% | — | **여전히 누락** |
| 13. SRAM | L1+VC+ATT 전체 | 10% | **30%** | +20pp | RF_2P_HSC_LVT 32×136 발견 |
| 14. DFX | 4개 모듈 + iJTAG | 40% | **55%** | +15pp | iJTAG 체인 방향성 (noc_niu → partition → dfd) |

**가중 점수 추정:** v6c ~45% → **v7 ~55%** (+10pp)

### 1.2 v7 핵심 개선 상세

#### (1) Port Classifier + MCP 800char 확장 — 섹션 3/10 도약의 주역

정답지의 `i_edc_apb_psel, i_edc_apb_penable, i_edc_apb_pwrite, i_edc_apb_pprot[2:0], i_edc_apb_paddr[5:0], i_edc_apb_pwdata[31:0], i_edc_apb_pstrb[3:0]` 풀 시그널을 v7이 복구했다. v5.1/v6c에서는 `i_edc_apb_*` 한 줄로 뭉뚱그려졌던 영역.

Port Classifier의 claim 형식(`AI_Clock_Reset(2)`, `DM_Clock_Reset(3)`)은 v5.1에는 전혀 없던 **새 KB 범주**. 이는 향후 "이 칩의 reset tree를 요약해줘" 같은 자연어 질의에 **구조화된 답변**을 가능하게 하는 기반.

#### (2) TDMA 1 → 3 sub-module 확장

v6c: `tt_tdma_thread_context` 한 줄만 식별.
v7:
- `tt_tdma_xy_address_controller` (v7 신규)
- `tt_tdma_thread_context`
- `tt_tdma_rts_rtr_pipe_stage` (v7 신규)

정답지의 TDMA 상세(Unpack CH0/CH1, address generation)에는 여전히 못 미치지만, **"존재하는 모듈을 빠짐없이 인덱싱"**이라는 면에서 KB chunking 확장 성공.

#### (3) RF_2P_HSC_LVT_32X136M1FB1WM0DR0 — SRAM 발견

EDC/NoC/DFX 3개 서브시스템에 걸쳐 등장하는 SRAM 매크로를 v7이 최초 포착. v6c까지는 `tt_mem_wrap_32x1024_2p_nomask`(ATT용) 하나만 있었으나, v7은 **HSC LVT 특성, 32×136 geometry, dual-port** 까지 기재.

#### (4) DFX iJTAG 체인의 방향성

v6c: 모듈 나열만
```
tt_disp_eng_l1_partition_dfx (iJTAG chain)
```

v7: 상/하류 연결 확인
```
tt_disp_eng_l1_partition_dfx
  ← receives from noc_niu_router_dfx
  → sends to dfd
```

이는 "체인 순서"라는 구조 정보를 claim으로 추출했다는 뜻. KB chunking이 단순 선언부 → **연결 관계**까지 확장된 신호.

### 1.3 여전히 남은 15 gap

| 카테고리 | 정답지에만 존재 | v7에서 누락 이유 | 해결 경로 |
|----------|----------------|------------------|----------|
| **Power Management** | PRTN_CLK, ISO_EN, per-partition isolation | trinity.sv 포트 일부 미추출 | v7.x에서 포트 파서 재점검 |
| **Compute Tile 내부** | FPU G-Tile/M-Tile, Unpack CH0/CH1 | RTL에 있어도 깊은 hierarchy | **v7 KB chunking 2차**: generate/block 내부 파싱 |
| **NoC 알고리즘** | DOR pseudo code, tendril, force_dim | KB에 텍스트로 없음 | **v8 Hybrid 그라운딩 or v9 Spec RAG** |
| **Flit 구조** | 2048b payload + 3b type + 32b parity | 정답지는 Spec 성격 | **v9 Spec RAG** |
| **AXI gasket 56b** | [55:52]rsvd/[51:46]Y/[45:40]X/[39:0]local | Spec 성격 | **v9 Spec RAG** |
| **EDC U-shape ring** | 토폴로지 그림 | 시각 정보 | KB 다이어그램 인덱싱 또는 Hybrid |
| **N1B0 vs Baseline 차이** | 10행 비교 테이블 | 히스토리 정보 | **v8 Hybrid** (LLM 추론 허용) |

**남은 gap의 성격이 명확히 바뀌었다**: v6c까지는 "RTL에서 추출 가능한데 놓친 것"이 많았지만, v7 이후 남은 gap 대부분은 **"RTL 단독으로 추출 불가"** 영역이다. 이는 로드맵의 v9(Spec RAG 합류)가 예정대로 필요함을 실증.

---

## 2. v6c → v7 진화 분석

### 2.1 개선 레이어의 스펙트럼

| | v5→v5.1 | v5.1→v6c | **v6c→v7** |
|---|---------|----------|------------|
| 변경 본질 | 검색 랭킹 재조정 | **KB 데이터 범주 신설** (Package Constants) | **KB 데이터 밀도 증가** (기존 범주 내 확장) |
| 대표 변경 | boost 0.3 → 1.5 | Package Parser v2 | Port Classifier + MCP 800char + HDD sub-module 인덱싱 |
| 효과 성격 | 1회성 (이미 있는 것 재발견) | 단계적 (빈 영역 신규 점유) | **선형적 (기존 영역을 2~3배 두껍게)** |
| 정답지 일치도 | 13% → 18% (+5pp, 엄격 기준 ~13%) | → 45% (+32pp) | **→ 55% (+10pp)** |

**통찰:** v7은 v6c만큼의 극적 도약은 아니지만, **"한 번 뚫린 데이터 범주를 정밀 충전"**하는 단계. 이는 v7→v8(Hybrid 그라운딩), v8→v9(Spec RAG 합류) 각 단계가 **또 다른 도약**을 가져올 수 있다는 의미. 즉 앞으로의 개선 폭은 **어느 레이어를 건드리느냐**에 따라 달라진다.

### 2.2 v6c→v7에서 해결된 "미해결 권고"

이전 `claude_review_v6.md` 권고와 v7 반영 여부:

| v6c 권고 | v7 반영 | 비고 |
|----------|---------|------|
| trinity.sv full port parse | ✅ **부분 반영** | DM/APB/EDC APB는 복구, PRTN/ISO는 여전히 누락 |
| 응축 로직 완화 | ✅ 반영 | `v7_N1B0_HDD.md` 404줄로 확대, 정보 밀도 상승 |
| KB chunking 확장 | 🟡 진행 중 | TDMA sub-module/iJTAG 체인은 성공, 알고리즘 블록은 미도달 |
| Spec RAG 합류 | ⏭️ v9 예정 | 일정 유지 |

### 2.3 v7 내부 일관성 점검

v7 파이프라인의 5개 topic 파일과 통합 문서의 **교차 일관성**:

| 항목 | topic 파일 | N1B0_HDD.md | 일치? |
|------|-----------|-------------|------|
| Package 13 localparams | `v7_chip_no_grounding` ✅ | §2.1 ✅ | ✅ |
| Top Ports 800char | `v7_chip_no_grounding` ✅ | §3.1~3.4 ✅ | ✅ |
| TDMA 3 sub-modules | `v7_overlay` ✅ | §5.2 ✅ | ✅ |
| RF_2P SRAM | `v7_edc`(×2) + `v7_noc`(×2+) + `v7_chip_grounded`(×3+) | §12 consolidated ✅ | ✅ |
| DFX iJTAG chain | `v7_chip_grounded` ✅ | §13.1 ✅ | ✅ |

→ topic 파일과 통합 문서 간 모순 없음. **merge 파이프라인이 v6c 대비 개선됨** (v6c에서는 `tt_t6_l1_partition` 같은 항목이 응축 과정에 유실됐던 이슈).

---

## 3. 품질 지표 재해석 (경영진 보고 관점)

RAG_Farm_Strategy_v1.4 문서에 반영할 **v7 숫자의 해석**:

| 지표 | v5.1 | v6c | v7 | 사용처 |
|------|------|-----|----|---------|
| **Content Fidelity (가중)** | ~13% | ~45% | **~55%** | **메인 지표** |
| KB Hit Rate | 59% | 70%+ | **75%+** | 보조 지표 |
| Package Constants 영역 | 0% | 90% | 90% | 최고 성취 사례 |
| **Port Coverage** (v7 신규) | 0% | 35% | **70%** | **새로운 최고 성취 사례** |
| Hallucination | 중간 | 없음 | 없음 | 품질 안정성 |

**v1.4 로드맵 예측 대비:**

| 버전 | 예측 | 실측 | 차이 |
|------|------|------|------|
| v6 (Pkg parser) | 65% | 45% | -20pp |
| **v7 (KB chunking)** | 72% | **55%** | **-17pp** |
| v8 (Hybrid) | 78% | TBD | — |
| v9 (Spec RAG) | 85%+ | TBD | — |

**궤적은 유지되나 기울기가 예측보다 완만**. 이는 정상: 초기 Package Parser처럼 "빈 영역을 통째로 채우는" 기회는 흔치 않고, 점점 **"남은 영역의 난이도가 상승"**하는 수확체감 패턴. v1.4 업데이트 시 기대값을 **상향 조정이 아닌 현실 정렬** 권장:

- v7 목표 72% → **실측 55%** 반영
- v8 목표 78% → **65~70% 밴드**로 조정
- v9 목표 85%+ → **75~80%대 진입**으로 조정

---

## 4. Kiro 리뷰 대비 본 리뷰의 차별점 (v7은 Kiro 리뷰 미존재)

v7 리뷰는 Kiro 측 비교 리뷰가 아직 나오지 않은 상태이므로, **본 리뷰가 단독**. 추후 Kiro 리뷰 등장 시 다음 포인트 교차 검증 필요:

- v7 Port Coverage ~70% 추정의 정량 검증
- TDMA 3 sub-module이 정답지의 TDMA 섹션과 얼마나 일치하는지
- DFX iJTAG 체인 방향성이 정답지 토폴로지와 일치하는지

---

## 5. 권고

### 5.1 즉시 유지
- ✅ **Port Classifier** — AI_Clock_Reset/Tensix_Reset/DM_Clock_Reset 카테고리화는 downstream 자연어 질의 대응력 크게 향상
- ✅ **MCP 800char 확장** — 포트 시그널 풀 리스트 복원에 결정적
- ✅ **HDD sub-module KB 인덱싱** — TDMA 3 sub-module 식별은 이 방식의 첫 성공 사례
- ✅ v6c Package Parser, v5.1 boost 가중치 모두 유지

### 5.2 v7.x 단기 보강 (다음 v8 이전)

1. **PRTN_CLK / ISO_EN 포트 복구** (Power Management 섹션 0% → 30%)
   - 현재 Port Classifier가 놓친 영역. trinity.sv의 partition/isolation 관련 포트 파싱 규칙 추가 필요.
   - 리턴 예상: 가중 점수 +3~5pp

2. **TDMA 3 sub-module의 기능 상세 claim 추가**
   - 현재는 이름만 식별. `tt_tdma_xy_address_controller`의 "XY 주소 생성 방식" 등 기능 설명 claim을 1~2줄씩 추출하면 Compute Tile 섹션 25% → 40% 가능
   - 정답지의 "Unpack CH0/CH1" 수준에는 못 가지만, 격차 절반은 메꿔짐

3. **응축 로직 규칙 문서화**
   - v6c→v7에서 응축 완화된 것은 확인됐으나 규칙이 암묵적. "SRAM 매크로는 서브시스템별로 중복 언급 허용" 같은 규칙을 명시해야 v8 병합에서도 안정성 확보

### 5.3 v8 (Hybrid 그라운딩) — 가장 효과 클 것

v7에서 해결되지 않은 gap 대부분이 **"KB에는 없지만 LLM 상식으로 답할 수 있는 영역"** (예: DOR 알고리즘은 표준 NoC 개념, AXI gasket은 AXI 표준). 이를 `[GROUNDED]` / `[INFERRED]` 태그로 구분 출력하면:

- Content Fidelity 55% → 70% 근접 가능
- 경영진 보고 시 "v5.1에서 환각으로 쓸데없이 채우던 것을 v8에서 **표시된 추론**으로 전환 — 동일 정보가 신뢰 가능하게 복원"이라는 강한 내러티브

### 5.4 v9 (Spec RAG) — 천장 돌파

- 정답지의 **N1B0 vs Baseline 차이 테이블** 같은 정보는 오직 Spec 문서에만 존재
- v7까지는 "RTL 단독 천장" 탐색, v9부터는 **"Spec 합류로 천장 돌파"**
- 충원 인력 우선 투입 영역

---

## 6. 코멘트

- v7은 **"빛나는 한 방"**이 아니라 **"여러 레이어의 정밀 보강"**이다. Port Classifier, MCP 800char, HDD sub-module 인덱싱은 각각 5~15pp 기여를 합산한 결과 +10pp.
- v7의 진짜 가치는 **"남은 gap의 성격이 명확해진 것"**. 이제 Content Fidelity를 55%에서 더 끌어올리려면 **어떤 레이어를 건드려야 하는지** 명백해졌다 (→ v8 Hybrid + v9 Spec RAG).
- v7 파이프라인의 **topic 파일 ↔ 통합 문서 일관성**은 v6c 대비 개선. 이는 자동화 성숙도가 올라가고 있다는 방증. 경영진 보고 시 **"환각 없음 + 내부 일관성 검증 통과"**는 품질 안정성 증거로 활용 가능.
- 로드맵 숫자(65%/72%)를 실측(45%/55%)에 맞춰 조정해도 **궤적 자체는 유효**. v1.4 작성 시 **"목표 재조정"이 아닌 "초기 기대가 낙관적이었음을 인정하고 현실값으로 정렬"**이라는 톤 권장 — 이는 신뢰도 지표가 된다.

---

*Review complete — 2026-05-01*
