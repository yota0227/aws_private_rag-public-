# Kiro Review: RAG v9.2 정답지 비교 분석

**작성일:** 2026-05-08
**리뷰어:** Kiro (Claude Opus 4.6)
**비교 대상:** `test_rtl/rag_result/v9.2/` 6개 산출물 vs `test_rtl/Sample/ORG/N1B0_NPU_HDD_v0.1.md` 정답지
**참고:** `codex_review_v9.2.md`, `claude_review_v9.2.md`

---

## 0. 결론 요약

| 지표 | v9.1 | v9.2 | 변화 |
|------|------|------|------|
| **통합 HDD 단독 점수** | ~57% (Codex) / ~74% (Claude) | ~68% (Codex) / ~74% (Claude) | Codex +11pp / Claude 보합 |
| **산출물 전체 best-of** | ~74% (Codex) / ~74% (Claude) | ~76-78% (Codex) / ~74% (Claude) | Codex +2-4pp / Claude 보합 |
| **통합 HDD 크기** | 331줄 / 117 table rows | 407줄 / 172 table rows | +76줄 / +55 rows |
| **환각** | 없음 | 없음 | 유지 |

**한 줄 결론:** v9.2는 "구조물 이름 회수"에 성공한 버전. EP Index Table 20행, Dispatch feedthrough 6종, Flit 4D array, Clock routing 4x5 mesh가 최종 통합 HDD에 들어왔다. 그러나 SFR/PRTN 실명 노출 회귀와 DFX 4-node wrapper chain 미반영으로 총점은 보합~소폭 상승.

---

## 1. 두 리뷰어 점수 비교

| 섹션 | Codex 점수 | Claude 점수 | 차이 원인 |
|------|-----------|------------|----------|
| Overview | 65% | 72% | Claude가 DM/cluster 세분화를 더 인정 |
| Package/EP | 78% | 95% | Claude가 EP 20행 "정답지 100% 일치"를 높이 평가 |
| Top-Level Ports | 74% | 80% | Claude가 SFR/PRTN 회귀를 -15pp로 크게 감점 |
| Module Hierarchy | 58% | 70% | Claude가 Instrn Engine 삭제를 -10pp로 감점 |
| Compute Tile | 55% | 42% | Claude가 더 보수적 (TRISC/BRISC 부재 강조) |
| Dispatch | 62% | 40% | Codex가 wire topology 회수를 더 높이 평가 |
| NoC | 52% | 60% | Claude가 flit 4D + gasket을 더 인정 |
| Clock/Reset | 68% | 85% | Claude가 4x5 mesh를 정답지 근접으로 평가 |
| EDC | 64% | 92% | Claude가 L1 EDC daisy-chain 신설을 높이 평가 |
| Power/PRTN | 60% | 75% | Claude가 기존 유지분을 더 인정 |
| DFX | 43% | 30% | 양쪽 모두 낮음 (4-node wrapper 미반영) |

**점수 차이 해석:**
- Codex는 "정답지의 generate/wiring 예외 설명"을 기준으로 보수적 평가
- Claude는 "신규 구조 정보 노출"의 가치를 더 높이 평가하되, 회귀에 대해 명확히 감점
- 두 리뷰어 모두 **DFX가 가장 약한 섹션**이라는 데 동의

---

## 2. v9.2 핵심 성과 (양 리뷰어 합의)

### 2.1 EP Index Table 20행 — 정답지 100% 일치

- Codex: "v9.2의 가장 큰 개선"
- Claude: "정답지 Section 2.3과 100% 일치"
- v9.1 리뷰 권고 "EP 인덱스 계산 로직" **완전 반영**

### 2.2 Dispatch Feedthrough Wiring 6종 — 역대 최대 폭 개선

| Wire | Type | Dimensions |
|------|------|-----------|
| de_to_t6_coloumn | de_to_t6_t | [SizeX][SizeY-1] = 4x4 |
| de_to_t6_east/west | de_to_t6_t | [SizeX] = 4 |
| t6_to_de | t6_to_de_t | [SizeX][SizeY-2] = 4x3 |
| t6_to_de_accross_east/west | t6_to_de_t | [SizeX][SizeX] = 4x4 |

- Codex: "정답지 fidelity를 실질적으로 끌어올림"
- Claude: "Dispatch +20pp, 버전간 역대 최대 폭 개선"

### 2.3 Flit 4D Array + AXI 56b Gasket + noc_header_address_t

- flit_in/out_req/resp: [4][5][2][2] 4D 명시
- AXI 56b: target_index / endpoint_id / tlb_index / address
- noc_header: x_dest, y_dest, endpoint_id, flit_type, dynamic_carried_list

### 2.4 Clock Routing 4x5 Mesh

- clock_routing_in/out: trinity_clock_routing_t[SizeX-1:0][SizeY-1:0] = 4x5
- 8-field struct (ai_clk, noc_clk, dm_clk, + 5 resets/power_good)

### 2.5 L1 EDC Daisy-Chain 4 Generate Blocks (신규)

- gen_l1_dcache_tag_edc, gen_l1_dcache_data_edc
- gen_l1_icache_tag_edc, gen_l1_icache_data_edc

---

## 3. v9.2 회귀 포인트 (양 리뷰어 합의)

| 회귀 항목 | v9.1 상태 | v9.2 상태 | 영향 |
|-----------|----------|----------|------|
| SFR 17 신호명 실명 | 전체 나열 | 와일드카드 (SFR_RF_2P_HSC_*) | Port 섹션 -15pp (Claude) |
| PRTN 14 신호명 실명 | 전체 나열 | 와일드카드 (PRTNUN_FC2UN_*) | Power 섹션 -10pp (Claude) |
| Instruction Engine 6-sub | Section 5.4 테이블 | 삭제 (DFX에 4항목만) | Hierarchy -10pp (Claude) |
| KB Coverage 정량 매트릭스 | 118/132 = 89% | 정성 등급만 | 경영진 보고 지표 손실 |
| DFX 4-node wrapper chain | 미반영 | 여전히 미반영 | 2-sprint 연속 미해결 |

**회귀 원인 (Claude 분석):** "자동화 파이프라인의 과도한 압축" — dedup/summarization이 긴 신호명 리스트를 와일드카드로 대체.

---

## 4. 종합 점수 (Kiro 판정)

두 리뷰어의 평가를 종합하면:

| 기준 | Codex | Claude | Kiro 종합 |
|------|-------|--------|-----------|
| 통합 HDD 단독 | 68-70% | 74% | **71%** |
| 산출물 전체 best-of | 76-78% | 74% | **76%** |

**Kiro 판정 근거:**
- Codex의 보수적 기준(generate/wiring 예외 설명 부재)은 타당하나, 통합 HDD의 table density 증가(117->172 rows)를 과소평가
- Claude의 "구조 정보 노출 가치" 인정은 타당하나, 실명 회귀의 실사용 영향을 과소평가
- 절충: **통합 HDD 71%, 전체 산출물 76%**

---

## 5. v9.1 -> v9.2 진화 요약

| 축 | v9.1 | v9.2 |
|----|------|------|
| SFR/PRTN 실명 노출 | 전체 | 와일드카드 회귀 |
| Instrn Engine 6-sub | 있음 | 통합본에서 삭제 |
| KB Coverage 89% 정량 | 있음 | 정성 등급 회귀 |
| EP Index Table | 없음 | 20행 완전 (정답지 100%) |
| Dispatch wiring | 없음 | 6종 wire + 차원 완전 |
| Flit 4D array | 없음 | [4][5][2][2] 명시 |
| AXI 56b gasket | 없음 | 4필드 구조 |
| Clock 4x5 mesh | 없음 | clock_routing_t[4][5] |
| L1 EDC daisy-chain | 없음 | 4 generate blocks |
| Source Tracking | 없음 | Appendix 신설 |

**성격 변화:** v9.1 = "DV 엔지니어 실사용" / v9.2 = "칩 아키텍트 설계 이해"

---

## 6. 남은 핵심 Gap (양 리뷰어 합의, 우선순위순)

| # | Gap | 정답지 위치 | 해결 경로 | 예상 효과 |
|---|-----|-----------|----------|----------|
| 1 | DFX 4-node wrapper chain | Section 14 | *_dfx.sv 전용 파서 | +5-7pp |
| 2 | SFR/PRTN 실명 복구 | Section 3 | dedup 예외 룰 + CI | +3-5pp |
| 3 | Instrn Engine 6-sub 복구 | Section 4/5 | merge 룰 수정 | +3-5pp |
| 4 | GridConfig 4x5 ASCII map | Section 2.3 | 자동 생성 | +2-3pp |
| 5 | NOC2AXI_ROUTER dual-row | Section 4/8 | router_opt 전용 파서 | +3-4pp |
| 6 | NoC repeater instance/count | Section 7 | repeater parser 심화 | +2-3pp |
| 7 | Top module parameters | Section 3 | parameter 파서 확장 | +2-3pp |
| 8 | EDC flat arrays | Section 11 | top-level EDC query | +1-2pp |
| 9 | AXI gasket bit range | Section 7 | Spec RAG (v10) | +1-2pp |
| 10 | KB Coverage 정량 복구 | — | 파이프라인 수정 | 경영진 보고 |

**#1~#3 해결 시 예상:** 통합 HDD 71% -> 80%+, 전체 산출물 76% -> 82%+

---

## 7. 권장 다음 단계

### v9.3 (RTL-extractable 마무리)

1. **DFX 4-node wrapper chain** — 2-sprint 연속 미반영, 격리 스프린트 필수
2. **실명 노출 회귀 치유** — dedup에 "신호명 리스트 압축 금지" 룰 + CI
3. **Instrn Engine 6-sub 복구** — merge 파이프라인 수정
4. **통합 HDD merge 개선** — topic ASCII/gasket이 통합본에 전파되도록

### v10 (Spec RAG)

- 남은 gap의 60%가 Spec-only -> v10 투자 ROI 상한 14pp
- 핵심 타깃: N1B0 vs Baseline 차이 테이블, AXI bit range, flit payload 상세, SRAM 구조

---

## 8. 버전 흐름 정리

| 버전 | 핵심 변화 | 점수 (통합본) | 성격 |
|------|----------|-------------|------|
| v8 | max_results 50, port 전체 노출 | 68% | visibility 극대화 |
| v9 | Hybrid 태그 + 6-file split | 67% | 측정 인프라 도입 (회귀 발생) |
| v9.1 | dedup + 실명 노출 + KB 89% | 74% | 회귀 치유 + 정량화 |
| **v9.2** | **EP/dispatch/flit/clock 구조 회수** | **71%** | **구조 이해 도약 (실명 일부 회귀)** |
| v9.3 (예상) | DFX + 실명 복구 + merge 개선 | 80%+ | RTL-extractable 마무리 |
| v10 (예상) | Spec RAG 도입 | 85%+ | Spec-only gap 해소 |

---

*End of Review — Kiro Review v9.2 (2026-05-08)*
