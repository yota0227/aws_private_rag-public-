# Kiro Review: RAG v9.4 정답지 비교 분석

**작성일:** 2026-05-15
**리뷰어:** Kiro
**비교 대상:** `v9.4/v9.4_N1B0_HDD.md` (통합본) + 폴더 전체 vs `Sample/ORG/N1B0_HDD_v0.1.md` (정답지)
**참고:** codex_review_v9.4.md, claude_review_v9.4.md

---

## 0. 요약

v9.4는 **검색 원천(KB-only)은 크게 좋아졌으나, 최종 통합 HDD가 과도하게 압축되어 정답지 대비 후퇴**한 버전이다.

| 기준 | 점수 | 비고 |
|------|------|------|
| 통합 HDD vs 정답지 (N1B0_HDD_v0.1.md) | **60~64%** | v9.3 대비 하락 |
| 폴더 전체 best-of | **74~77%** | v9.3과 유사 |
| KB-only strict | **70~73%** | v9.3 대비 대폭 개선 |
| EDC topic 단독 | **84~87%** | 최고 품질 |

**핵심 문제:** `chip_no_grounding`(512줄)이 통합 HDD(323줄)보다 길다. 좋은 검색 결과가 merge 과정에서 버려졌다.

---

## 1. 정답지 대비 섹션별 비교

### 정답지 핵심 구조 (N1B0_HDD_v0.1.md, 514줄)

| # | 섹션 | 핵심 내용 |
|---|------|----------|
| 1 | Overview | HPDF composite tile 교체, per-column clock, PRTN/ISO_EN 추가 |
| 2 | Package | GridConfig ASCII, tile_t 8종, helper functions, EndpointIndex formula |
| 3 | Top-Level Ports | Parameters(AXI_SLV_*), Clock/Reset arrays, APB, EDC APB+IRQ, AXI, SFR, PRTN 14개 |
| 4 | Module Hierarchy | gen_x/gen_y generate tree, dual-row span 설명, repeater 4개 인스턴스 |
| 5 | NoC Fabric | Y-axis generate, X-axis manual, 4/6-stage repeater 실명 |
| 6 | Clock and Reset | trinity_clock_routing_t struct(9 fields), entry point, router exception |
| 7 | EDC Ring | flat array[20], per-column chain, router exception |
| 8 | Dispatch Feedthrough | de_to_t6_coloumn[SizeX][SizeY-1][2], feedthrough 실명 |
| 9 | PRTN Daisy Chain | per-column Y=2->1->0, 실명 포트 |
| 10 | Memory Config (SFR) | SFR_RF_2P_HSC_* 실명 8종 |
| 11 | RTL File Map | 12개 모듈-파일 매핑 |
| 12 | Hierarchy Verification | Package<->RTL 일관성 체크 12항목 |
| 13 | Differences vs Baseline | 11개 항목 비교 테이블 |

---

### v9.4 통합 HDD 섹션별 판정

| 정답지 섹션 | v9.4 상태 | 점수 | 핵심 누락 |
|------------|----------|------|----------|
| 1. Overview | 4x5, 20 EP, trinity_router EMPTY 명시 | 70% | HPDF 교체 의미, per-column clock 변경 이유 |
| 2. Package | EP Table 20개 정확 | 75% | GridConfig ASCII, helper functions, EndpointIndex formula, tile_t enum 값 |
| 3. Top-Level Ports | 그룹 수준만 | **45%** | **Parameters(AXI_SLV_*=64/32/512), PRTN 14포트 실명, ISO_EN[11:0], SFR 실명, EDC IRQ 5종** |
| 4. Module Hierarchy | depth 3 커버 | 65% | gen_x/gen_y generate 이름, dual-row span 상세, repeater 4 인스턴스 |
| 5. NoC Fabric | 라우팅 3종, repeater 존재 | 55% | **4개 repeater 실명+stage수(4/6), X-axis manual assign, Y-axis generate** |
| 6. Clock and Reset | 6 domain 나열 | **40%** | **trinity_clock_routing_t struct, clock_routing_in/out[SizeX][SizeY], entry point, router exception** |
| 7. EDC Ring | U-shape ring, node ID | 65% | **flat array[20], router exception (Y=4 no EDC)** |
| 8. Dispatch Feedthrough | FDS bus만 | **30%** | **de_to_t6_coloumn[SizeX][SizeY-1][2], feedthrough 실명 전체** |
| 9. PRTN | "2 PRTN_Power ports" 한 줄 | **25%** | **per-column chain topology, 14개 포트 실명, ISO_EN bit mapping** |
| 10. SFR | "SFR_Memory_Config(13)" 숫자만 | **30%** | **SFR_RF_2P_HSC_* 8종 실명** |
| 11. RTL File Map | 18개 파일 경로 (chip_no_grounding) | 80% | 통합본에는 미포함 |
| 12. Hierarchy Verification | 없음 | **0%** | 전체 누락 |
| 13. Baseline Differences | 3행 테이블 | 50% | 11개 중 3개만 |

**가중 평균: ~60%** (통합 HDD 단독 기준)

---

## 2. v9.3 -> v9.4 변화 분석

### 개선된 점

| 항목 | v9.3 | v9.4 | 효과 |
|------|------|------|------|
| KB-only 산출물 | 215줄/29행 | **512줄/264행** | 원천 데이터 2.4배 |
| EDC ring 오류 | "1 ring" (치명 오류) | **4-column U-shape 수정** | 치명 오류 1건 해소 |
| KB Coverage 정량화 | 없음 | **82% 명시** | 측정 기반 확보 |
| Grounding 태그 | 부분적 | **전 파일 표준화** | 신뢰도 판단 가능 |
| DFX wrapper | 0/4 | **2/4 명시** | 부분 개선 |
| RISC-V 파라미터 | 일부 | **50+개 상세** | L4 파라미터 개선 |
| RTL File Reference | 없음 | **20개 경로** | traceability |

### 회귀/미해결

| 항목 | 상태 | 심각도 |
|------|------|--------|
| 통합 HDD 크기 | 493줄->323줄 (-34%) | **High** -- 정보 손실 |
| PRTN/ISO_EN 실명 | 4-sprint 미해결 | **Critical** -- 정답지 핵심 |
| clock_routing_t struct | 미노출 | **High** -- 정답지 S6 핵심 |
| Dispatch feedthrough | 거의 누락 | **High** -- 정답지 S8 핵심 |
| NoC repeater 4개 실명 | generic만 | **Medium** |
| Hierarchy Verification | 없음 | **Medium** |
| topic->통합본 merge 손실 | 재발 | **High** -- 구조적 문제 |

---

## 3. L1~L6 계층별 점수 (v9.4)

| 계층 | v9.3 | v9.4 | 변화 | 근거 |
|------|------|------|------|------|
| L1 구조 | 82% | **80%** | -2pp | 통합본 축소로 hierarchy 정보 감소 |
| L2 인터페이스 | 78% | **75%** | -3pp | PRTN/SFR 실명 여전히 없음, 통합본 port 축소 |
| L3 연결 | 70% | **65%** | -5pp | Port Binding evidence가 통합본에서 사라짐 |
| L4 파라미터 | 30% | **38%** | +8pp | RISC-V params 50+개, FBLC params |
| L5 동작 | 25% | **25%** | 0 | 변화 없음 |
| L6 의도 | 5% | **5%** | 0 | 변화 없음 |

**해석:** L4(파라미터)는 개선됐지만, L1~L3(구조/인터페이스/연결)은 통합본 기준으로 오히려 하락. 이는 검색 결과가 나빠진 게 아니라 **merge 과정의 문제**.

---

## 4. 치명적 오류 카운트

| 등급 | v9.3 | v9.4 | 변화 |
|------|------|------|------|
| Critical | 2 | **1** | -1 (EDC ring 수정) |
| Major | 4 | **3** | -1 (KB Coverage 복구) |
| Minor | 3 | **4** | +1 (AXI gasket bit range 불일치 가능) |
| Cosmetic | 다수 | 다수 | -- |

### 잔존 Critical 오류

1. **clock_routing_t 미노출** -- 정답지 S6의 핵심 struct가 전혀 없음. 9 fields + [SizeX][SizeY] array dimension이 빠져있어 clock 아키텍처 이해 불가.

### 잔존 Major 오류

1. **PRTN/ISO_EN 전체 누락** -- 정답지 S3/S9의 14개 포트 + bit mapping
2. **Dispatch feedthrough 누락** -- 정답지 S8의 multi-dim array 구조
3. **NoC repeater 4개 실명+stage수 누락** -- 정답지 S5.3

---

## 5. Codex/Claude 리뷰와의 비교

| 관점 | Codex | Claude | Kiro |
|------|-------|--------|------|
| 통합본 점수 | 64~67% | 63% | **60~64%** |
| 폴더 best-of | 74~77% | -- | **74~77%** |
| 핵심 문제 | merge 압축 | merge 파이프라인 | **merge + PRTN/clock** |
| 최고 산출물 | chip_no_grounding + edc | chip_no_grounding | **동의** |
| v9.5 최우선 | 통합본 merge 개선 | SFR/PRTN 복구 | **둘 다 필수** |

**3개 리뷰어 공통 지적:**
1. 통합 HDD가 topic 파일보다 빈약 -- merge 파이프라인 문제
2. PRTN/SFR 실명 4-sprint 미해결
3. clock_routing_t struct 미노출

---

## 6. v9.4a/v9.5 권고

### v9.4a (Neptune 추가) 기대 효과

| 도구 | 기대 개선 | 대상 계층 |
|------|----------|----------|
| `find_instantiation_tree` | gen_x/gen_y hierarchy 복구 | L1 +5~8pp |
| `trace_signal_path` | clock_routing, dispatch feedthrough 경로 | L3 +5~10pp |
| 하이라키 인덱싱 | module depth/parent 정보 | L1 +3~5pp |

**예상:** v9.4a 통합본 기준 70~75% 가능 (현재 60% -> +10~15pp)

### v9.5 필수 과제

1. **통합 HDD merge 개선** -- topic 파일의 핵심 테이블을 통합본에 자동 전파
2. **PRTN/ISO_EN 14포트 실명** -- Port Binding parser scope 확장
3. **clock_routing_t struct** -- struct 파서로 9 fields + array dimension 추출
4. **Dispatch feedthrough** -- multi-dim array 파서
5. **NoC repeater 4개 실명** -- instance name exact retrieval
6. **DFX 나머지 2 wrapper** -- tt_noc_niu_router_dfx, tt_instrn_engine_wrapper_dfx

---

## 7. 결론

v9.4는 **"검색 엔진은 좋아졌는데 최종 보고서가 나빠진"** 역설적 버전이다.

- `chip_no_grounding`(512줄)과 `edc`(398줄)는 v9.3보다 확실히 좋다
- 하지만 통합 HDD(323줄)는 정답지(514줄)의 62% 분량에 불과하고, 핵심 정보가 누락됨
- **v9.4a에서 Neptune을 추가하면 L1/L3가 크게 개선될 것으로 예상**
- **v9.5에서는 merge 파이프라인 + PRTN/clock 파서가 필수**

---

*End of Review -- Kiro Review v9.4 (2026-05-15)*
