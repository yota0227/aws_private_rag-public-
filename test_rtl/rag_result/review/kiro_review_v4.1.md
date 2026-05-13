# Kiro Review: v4 vs v4.1 비교 분석

**작성일:** 2026-04-24
**분석 대상:** `test_rtl/rag_result/v4/` vs `test_rtl/rag_result/v4.1/`
**변경 사항:** Claim 필터 수정 (_wrap 제거 + 화이트리스트 + fallback 3→10)

---

## 1. 파일 크기 비교

| 문서 | v4 | v4.1 | 증가율 |
|------|-----|------|--------|
| Chip (no grounding) | 17.2 KB | 22.2 KB | +29% |
| Chip (grounded) | 6.1 KB | 22.9 KB | **+275%** |
| EDC | 20.0 KB | 26.0 KB | +30% |
| NoC | 18.7 KB | 37.1 KB | **+98%** |
| Overlay | 21.1 KB | 45.6 KB | **+116%** |
| **합계** | **83.1 KB** | **153.8 KB** | **+85%** |

Overlay와 NoC에서 2배 이상 증가. Claim 필터 수정 하나로 이 정도 차이.

## 2. 핵심 변화 — Claim 필터 수정 효과

### 수정 전 (v4)
- `_wrap` 패턴이 `tt_edc1_biu_soc_apb4_wrap` (BIU bridge)을 레지스터 래퍼로 오분류
- fallback 임계값 3이 파서 확장으로 무력화
- Overlay claim 0건, EDC BIU 소실

### 수정 후 (v4.1)
- `_wrap` 패턴 제거 → BIU bridge 복원
- 화이트리스트 → `tt_edc1_biu_*`, `tt_cluster_ctrl_*`, `tt_fds_*` 보호
- fallback 10 → `_reg_inner` 모듈도 포함 가능성 증가
- Claim 85건 → 99건 (+16%)

### 연쇄 효과
4개 모듈 복원이 문서 전체 품질을 끌어올림:
- `tt_edc1_biu_soc_apb4_wrap` → EDC BIU 레지스터 맵 + 패킷 포맷 + 링 토폴로지
- `tt_cluster_ctrl_reg_inner` → CPU 클러스터 구조 + SMN firewall
- `tt_fds_dispatch_reg_inner` → Dispatch 파이프라인 + LLK flow
- `tt_fds_tensixneo_reg_inner` → ROCC interface + FDS ring oscillator

## 3. 문서별 비교

### 3.1 Overlay — 가장 극적인 변화
- v4: 0건 반환, 12개 섹션 중 10개 NOT IN KB
- v4.1: 12개 섹션 전부 채워짐, 8× RV64GC CPU, iDMA, ROCC, LLK, SMN, FDS 상세
- 파일 크기: 21.1 KB → 45.6 KB (+116%)

### 3.2 NoC — 프로토콜 상세 확보
- v4: 라우팅 알고리즘/flit 구조/VC 전부 NOT IN KB
- v4.1: DOR/Tendril/Dynamic 3종 비교, 512-bit flit 비트맵, 4 VC + credit flow
- 파일 크기: 18.7 KB → 37.1 KB (+98%)

### 3.3 EDC — BIU 복원이 핵심
- v4: BIU 소실, Serial Bus 신호 없음
- v4.1: BIU 레지스터 맵 + 패킷 포맷 + opcode + Ring 40-hop + Harvest Bypass
- 파일 크기: 20.0 KB → 26.0 KB (+30%)

### 3.4 Chip Grounded — 가장 큰 비율 증가
- v4: 6.1 KB (5개 토픽 HDD만)
- v4.1: 22.9 KB (12개 토픽 + EDC modport + NoC claim + Overlay CDC)
- 파일 크기: +275%

## 4. KB Grounding vs LLM Inference

v4.1의 높은 커버리지(80-95%)에는 LLM inference가 상당 부분 포함.
v4.1b (grounded)가 46%인 것이 실제 KB 데이터 비율.

- 커버리지 87%: "문서가 채워졌다"
- Grounding 46%: "KB에서 확인된 데이터"
- 나머지 41%: LLM 구조적 추론 ([TBC] 태그)

## 5. 로드맵 재평가

| 기존 계획 | 현실 |
|-----------|------|
| v4 목표 70% | v4.1에서 87% 달성 (커버리지 기준) |
| v5 목표 75% | 이미 초과 |
| v6 목표 85% | 이미 도달 |

다음 단계는 커버리지 확장이 아니라 Grounding 비율 향상으로 전환:
- v5: Grounding 46% → 65% (analysis_type 필터 + 검색 경로 최적화)
- v6: Grounding 65% → 80% ([TBC] 자동 해소 + generate/assign 파서)

## 6. 결론

Claim 필터 수정 하나가 v4 → v4.1에서 +53%p 커버리지 향상.
다음 초점: Grounding 비율 향상 — KB에서 직접 확인 가능한 데이터를 늘리는 것.
