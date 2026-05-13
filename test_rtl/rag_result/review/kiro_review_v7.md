# Kiro Review: v7 정답지 비교 + v6c → v7 진화 분석

**리뷰어:** Kiro | **리뷰일:** 2026-04-28
**비교:** `v7/` 6개 문서 vs `Sample/ORG/N1B0_NPU_HDD_v0.1.md`
**참고:** `claude_review_v7.md`, `codex_review_v7.md`

---

## 0. TL;DR

v7은 **기존 섹션을 두껍게** 만든 정밀 보강. Top-Level Ports 35%→70%, Reset 30%→65%. 가중 점수 **45%→55% (+10pp)**.

---

## 1. 세 리뷰어 점수

| 리뷰어 | v6c | v7 |
|--------|-----|-----|
| Kiro | 45% | **55%** |
| Claude | 45% | **55%** |
| Codex | 56.6% | **63.3%** |

합의: **55~63%.** 보수적 55%.

---

## 2. 핵심 변화

| 항목 | v6c | v7 | 원인 |
|------|-----|-----|------|
| Top-Level Ports | 35% | **70%** | MCP 800자 + Port Classifier |
| Reset | 30% | **65%** | dm_core/uncore 노출 |
| TDMA | 1개 | **3개** sub-module | hdd_content 800자 |
| SRAM | ATT 1종 | **+RF_2P_HSC_LVT** | hdd_content 800자 |
| DFX iJTAG | 나열 | **chain 방향성** | claim connectivity |

---

## 3. Kiro 고유 관찰

1. **개선 성격 변화** — v6c(범주 신설 +32pp) → v7(밀도 증가 +10pp). 수확체감 시작
2. **남은 gap 이분화** — RTL 추출 가능(15%): PRTN/AXI/feedthrough → v8 | RTL 불가(30%): 알고리즘/Spec → v9
3. **MCP 800자의 숨은 효과** — hdd_content 확대가 TDMA sub-module + SRAM 매크로 발견의 직접 원인
4. **array dimension 누락** — Codex 지적 동의. `[NumApbNodes]` 배열 차원 파싱 개선 필요
5. **로드맵 재조정** — v7=72% 예측 → 55% 실측. v8=65~70%, v9=75~80%로 현실 정렬

---

## 4. v8 방향

| 작업 | 효과 |
|------|------|
| trinity.sv generate/wiring pass | PRTN/AXI/feedthrough (+15pp) |
| 다차원 배열 포트 파싱 | APB/EDC array dimension |
| Hybrid 그라운딩 | NoC 알고리즘 등 LLM 추론 |
| **v8 예상: 55% → 65~70%** | |

---

## 5. 결론

v7은 **v1(12%)→v6c(45%)→v7(55%) 궤적의 안정적 연장**. 환각 없이 fact를 정밀 충전. 남은 gap 성격이 명확해졌고 v8(trinity.sv pass)→v9(Spec RAG)가 예정대로 필요.

```
v1(12%) → v5.1(13%) → v6c(45%) → v7(55%) → v8(65~70%) → v9(75~80%)
```

---

*End of Review*