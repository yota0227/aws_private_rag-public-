# Kiro Review: v6c 정답지 비교 + v5.1 → v6c 진화 분석

**리뷰어:** Kiro | **리뷰일:** 2026-04-28
**비교:** `v6c/` 6개 문서 vs `Sample/ORG/N1B0_NPU_HDD_v0.1.md`
**참고:** `claude_review_v6.md`, `codex_review_v6.md`

---

## 0. TL;DR

v6c는 **Package Parser의 승리**. 13개 상수 + tile_t 8종 + EP 20행이 KB에서 직접 나오면서, v5.1의 치명적 환각이 **완전 소멸**. 가중 점수 13%→45%(+32pp). 줄 수는 줄었지만 정보 밀도와 정확도는 상승.

---

## 1. 세 리뷰어 동의

| 항목 | 판정 |
|------|------|
| Package Constants 90%+ | ✅ 전원 동의 |
| Grid 환각 소멸 | ✅ 전원 동의 |
| 가중 점수 45~57% | ✅ (Kiro/Claude 45%, Codex 57%) |
| PRTN/ISO_EN 0% | ✅ 전원 동의 |
| trinity.sv 포트 truncation 미해결 | ✅ 전원 동의 |
| 개선 성격: 데이터 구조 확장 | ✅ 전원 동의 |

---

## 2. v5.1 → v6c 핵심 변화

| 항목 | v5.1 | v6c |
|------|------|-----|
| SizeX/SizeY | ❌ 뒤집힘 | ✅ 4×5 |
| 13개 localparam | 0개 | **13개 전부** |
| EP 테이블 | ❌ | ✅ **20행** |
| Grid 환각 | ETH/DRAM/PCI/ARC | **소멸** |
| 문서 구조 | 5개 파일 | **5개 + 통합 HDD** |

---

## 3. Kiro 고유 관찰

1. **환각 소멸 > 수치 개선** — 경영진 보고에서 45% 도달보다 "틀린 문서를 안 만든다"가 더 중요
2. **개선 성격이 다르다** — v5.1(튜닝) vs v6c(데이터 확장). 로드맵 v6 예측 적중
3. **줄 수 감소 ≠ 품질 저하** — 494줄(환각 포함) → 270줄(사실만) = 밀도 상승
4. **Codex의 Dispatch E/W 좌표 불일치 발견** — 정답지 자체 버그 가능성. canonical 확정 필요

---

## 4. 여전한 Gap과 v7 방향

| Gap | 가중치 | v7 해결 |
|-----|--------|---------|
| trinity.sv 포트 전체 | ~15% | full port parse |
| NoC 알고리즘/flit | ~10% | KB chunking |
| Deep hierarchy | ~8% | hierarchy deep parse |
| Dispatch feedthrough | ~5% | targeted search |
| SRAM inventory | ~3% | SRAM 분석 |
| FPU/SFPU/TDMA 내부 | ~10% | Spec RAG (v9) |
| P&R/SW guide | ~4% | Spec RAG |

**v7 예상: 45% → 55%**

---

## 5. 결론

v6c는 **v1(12%)→v6c(45%) 여정의 전환점**. 환각 소멸 + 정답지 좌표계 일치 + 개선 방법론 검증. 남은 55%는 trinity.sv full parse(v7) + KB chunking(v7) + Spec RAG(v9)로 해결 가능. 로드맵이 예측대로 작동 중.

---

*End of Review*