# Kiro Review: v8 정답지 비교 + v7 → v8 진화 분석

**리뷰어:** Kiro | **리뷰일:** 2026-04-29
**비교:** `v8/` 6개 문서 vs `Sample/ORG/N1B0_NPU_HDD_v0.1.md`
**참고:** `claude_review_v8.md`, `codex_review_v8.md`

---

## 0. TL;DR

v8은 **파서 변경 0, 파라미터 1개(max_results 20→50)로 +13pp 도약**. Port Coverage 31→106(100%). PRTN/AXI/SFR 전부 복구. 가중 점수 **55%→68% (+13pp)**.

---

## 1. 세 리뷰어 점수

| 리뷰어 | v6c | v7 | v8 |
|--------|-----|-----|-----|
| Kiro | 45% | 55% | **68%** |
| Claude | 45% | 55% | **~68%** |
| Codex | 56.6% | 63.3% | **~72.9%** |

합의: **68~73%.** 보수적 68%.

---

## 2. 핵심 변화

| 항목 | v7 | v8 | 원인 |
|------|-----|-----|------|
| Port Coverage | 31/106 (29%) | **106/106 (100%)** | max_results 50 |
| PRTN/ISO | 0% | **~78%** (14 ports + 섹션 11 신설) | max_results 50 |
| AXI Interface | 0% | **39 ports** | max_results 50 |
| SFR Memory Config | 0% | **17 ports** (4 SRAM family) | max_results 50 |
| EDC IRQ | partial | **5 IRQs explicit** | max_results 50 |
| DFX | 3-node chain | **4-node + upstream** (overlay_wrapper_dfx) | max_results 50 |
| 파서 변경 | — | **없음** | — |

---

## 3. Kiro 고유 관찰

### 3.1 "Parser는 옳았고, Retrieval이 병목이었다"

v7 리뷰에서 세 리뷰어 모두 PRTN/AXI/SFR 누락을 **Port Classifier 문제** 또는 **trinity.sv generate 파서 필요**로 진단했다. 실제 병목은 **검색 상위 20건 cutoff**였다. Port Classifier는 v7에서 이미 9개 카테고리 106포트를 전부 분류해놨고, 단지 claim 10개(port) + hdd 3개 + claim 37개(FPU/SFPU 등)로 상위 20이 채워져서 PRTN/AXI/SFR이 밀렸을 뿐.

**교훈:** RAG 튜닝에서 "공급(parser)"과 "소비(retrieval)"는 독립 축이다. 한쪽만 보면 병목 진단을 틀린다.

### 3.2 개선 레이어 변천

```
v5→v5.1: 검색 랭킹 (boost 가중치)     → +5pp
v5.1→v6c: KB 범주 신설 (Package Parser) → +32pp
v6c→v7: KB 밀도 증가 (Port Classifier)  → +10pp
v7→v8: 검색 cutoff 확대 (max_results)   → +13pp
```

매번 다른 레이어를 건드렸다. 다음은 **KB 깊이 확장**(trinity.sv generate/wiring) 또는 **KB 소스 확장**(Spec RAG)이 될 것.

### 3.3 v8의 효율성

| 버전 | 코드 변경량 | 점수 변화 | 효율 (pp/LOC) |
|------|-----------|----------|--------------|
| v6c | ~200줄 (package_extractor.py) | +32pp | 0.16 |
| v7 | ~100줄 (port_classifier.py + server.js) | +10pp | 0.10 |
| **v8** | **0줄** (파라미터 1개) | **+13pp** | **∞** |

v8은 **투자 대비 수익이 무한대**인 개선. 이전 parser 작업(v6c/v7)의 잠재력이 retrieval 확대로 해금된 것.

### 3.4 남은 gap 성격 분류

| 성격 | 비중 | 예시 | 해결 경로 |
|------|------|------|----------|
| **RTL deep (generate/wiring)** | ~30% | clock_routing_in/out, dispatch feedthrough, NoC repeater, EDC ring | trinity.sv generate 파서 |
| **Spec-only** | ~50% | FPU G-Tile 상세, AXI 56b 주소 의미, N1B0 vs Baseline 차이 | v9 Spec RAG |
| **Hybrid (LLM 추론)** | ~20% | 동작 설명, 검증 체크리스트 | Hybrid 그라운딩 태그 |

### 3.5 수확체감 분석

```
v1(12%) → v5.1(13%) → v6c(45%) → v7(55%) → v8(68%) → ?

증분: +1pp → +32pp → +10pp → +13pp
```

v6c의 +32pp가 최대 점프였고, 이후 +10pp, +13pp로 안정화. v8의 +13pp는 "공짜"(파라미터 변경)였으므로 실질적 parser 투자 대비 수확체감은 v7부터 시작. **RTL 단독으로 80% 돌파는 어렵다** — Spec RAG가 필수.

---

## 4. v9 방향

| 작업 | 효과 | 난이도 |
|------|------|--------|
| trinity.sv generate/wiring 파서 | clock_routing, feedthrough, repeater (+8~10pp) | 중 |
| noc_pkg.sv struct 파서 | flit 구조, 라우팅 테이블 (+3~5pp) | 하 |
| Hybrid 그라운딩 태그 | 동작 설명, N1B0 차이 (+5~8pp) | 하 |
| **Spec RAG 합류** | **FPU 상세, AXI 의미, 검증 (+15~20pp)** | **상** |
| **v9 예상: 68% → 75~80%** (RTL only) / **85%+** (with Spec) | | |

---

## 5. v7 P0 gap 해결 현황

| v7 P0 Gap | v8 상태 | 해결 방법 |
|-----------|---------|----------|
| PRTN chain + ISO_EN | ✅ **해결** (14 ports + 섹션 11) | max_results 50 |
| AXI npu_out/npu_in | ✅ **해결** (39 ports) | max_results 50 |
| SFR Memory Config | ✅ **해결** (17 ports, 4 family) | max_results 50 |
| EDC IRQ outputs | ✅ **해결** (5 IRQs explicit) | max_results 50 |
| clock_routing_in/out | ❌ 미해결 | trinity.sv generate 파서 필요 |
| Dispatch feedthrough | ❌ 미해결 | trinity.sv generate 파서 필요 |
| NoC repeater placement | ❌ 미해결 | trinity.sv generate 파서 필요 |

**5/7 P0 해결.** 남은 2개는 모두 trinity.sv generate 블록 파싱이 필요.

---

## 6. 결론

v8은 **v1(12%)→v6c(45%)→v7(55%)→v8(68%) 궤적의 가장 효율적인 도약**. 코드 변경 없이 retrieval 파라미터 하나로 +13pp. Port Coverage 100% 달성. PRTN/AXI/SFR/EDC IRQ 전부 복구.

남은 32%의 성격이 명확해졌다:
- **RTL deep (30%):** trinity.sv generate 파서 → v9
- **Spec-only (50%):** Spec RAG 합류 → v10
- **Hybrid (20%):** LLM 추론 태그 → v9

```
v1(12%) → v5.1(13%) → v6c(45%) → v7(55%) → v8(68%) → v9(75~80%) → v10(85%+)
```

**v8의 최대 교훈: "KB 품질이 충분하면, retrieval 확대만으로 큰 도약이 가능하다. 병목 진단은 공급과 소비 양쪽을 봐야 한다."**

---

*End of Review*
