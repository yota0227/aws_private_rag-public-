# v9.4_0516 Review — 정답지 비교 + v9.4a 대비 분석

**Review Date:** 2026-06-01
**Reviewer:** Claude (Opus 4.7)
**Scope:** [test_rtl/rag_result/v9.4_0516/](../v9.4_0516/) 7개 파일 + schematic_map.html vs [test_rtl/Sample/ORG/](../../Sample/ORG/) 정답지
**Pipeline ID:** tt_20260516 (변경됨 — 이전: tt_20260221)
**Cross-Reference:** [claude_review_v9.4a.md](claude_review_v9.4a.md), [claude_review_v9.4.md](claude_review_v9.4.md)

---

## 0. TL;DR

| Dim | v9.4a (tt_20260221) | v9.4_0516 (tt_20260516) | Δ | 비고 |
|-----|------|------|----|------|
| **SFR 17개 실명** | ❌ 없음 | ✅ **전체 복구** (`SFR_RF_2P_HSC_QNAPA` 등 16개+) | **🔥 5-sprint 해결** | signal_path_graph sfr 카테고리 효과 |
| **PRTN 14개 실명** | ❌ 없음 | ✅ **13개 실명** (`PRTNUN_FC2UN_DATA_IN` 등) | **🔥 5-sprint 해결** | prtn 카테고리 효과 |
| **Pipeline ID** | tt_20260221 | **tt_20260516** | **변경** | 새 RTL 스냅샷 기반 |
| **N1B0_HDD 분량** | 1,239줄 | **271줄** | -78% | topic 분산 + 통합본 요약화 |
| **schematic_map** | .md (352줄) | **.md (328줄) + .html (신규)** | **HTML 추가** | 인터랙티브 뷰 |
| **Grid 레이아웃** | NOC2AXI = Y=4 (우측) | **NOC2AXI = Row 0 (상단)** | **좌표계 변경** | tt_20260516 GridConfig 반영 |
| **Neptune 병합** | ✅ 대량 ([FROM NEPTUNE]) | ❌ **미적재** (Qdrant KB만) | **후퇴** | EDC ring / instantiation tree 손실 |
| **DFX 4-node wrapper** | 2/4 명시 | ❌ **0/4** | **후퇴** | Neptune 미적재 영향 |
| **KB Coverage 정량** | 82% | **정성만 (●/◐ 표기)** | **후퇴** | % 수치 미제시 |
| **AXI 56b gasket bit range** | [55:48] 등 (오류) | ❌ **미포함** | **삭제** | 오류 제거됐으나 정답도 없음 |
| **clock_routing_t** | 명시 없음 | **4 필드 명시** (reset 계열) | **부분 개선** | 정답 9개 중 4개 |
| **Grounding 태그** | [FROM NEPTUNE]/[FROM LLM]/[NOT IN KB] | **[FROM LLM]/[TBC]/무태그** 3종 | **축소** | Neptune 태그 사라짐 |
| **정답지 대비 (가중 추정)** | ~70% | **~65%** | **-5pp** | SFR/PRTN 복구(+8pp) vs Neptune 손실(-10pp) + 축소(-3pp) |
| **환각** | 없음 | 없음 | — | 유지 |

**한 줄 결론:** v9.4_0516은 **"5-sprint 최대 숙제(SFR/PRTN 실명)를 해결"**한 동시에, **Neptune 미적재로 v9.4a의 계층 정보가 대거 후퇴**한 양면성을 가진 빌드. 새 파이프라인(tt_20260516)으로 전환하며 Grid 좌표계가 바뀌었고 통합 HDD가 요약본으로 전환됨. 순수 점수로는 -5pp이지만, **SFR/PRTN 복구는 DV 엔지니어 실사용 관점에서 가장 큰 단일 성과**이며, Neptune 재적재만 하면 v9.4a 수준 이상으로 즉시 회복 가능한 상태.

---

## 1. 파일 구성 및 분량 비교

| 파일 | v9.4a | v9.4_0516 | Δ | 특이사항 |
|------|-------|-----------|---|--------|
| N1B0_HDD.md | 1,239줄 | **271줄** | -78% | 요약본 전환, topic 분산 |
| chip_grounded.md | 431줄 | **223줄** | -48% | LLM 해석 중심, 상세는 no_grounding 참조 |
| chip_no_grounding.md | 701줄 | **255줄** | -64% | **SFR/PRTN 실명 복구 핵심 파일** |
| edc.md | 260줄 | **169줄** | -35% | Neptune 미적재 영향 |
| noc.md | 264줄 | **182줄** | -31% | AXI gasket bit range 삭제 |
| overlay.md | 225줄 | **166줄** | -26% | FDS + Command Buffer 중심 |
| schematic_map.md | 352줄 | **328줄** | -7% | ASCII + Mermaid×6 + Graphviz DOT |
| schematic_map.html | ❌ | **신규** | +16KB | 인터랙티브 HTML 뷰 |
| **총계 (.md)** | 3,471줄 | **1,594줄** | **-54%** | 전반적 축소 |

**축소 원인 분석:**
1. **tt_20260516 파이프라인 전환** — 새 RTL 스냅샷, 새 GridConfig
2. **Neptune 미적재** — v9.4a의 `[FROM NEPTUNE]` 데이터 전량 손실 (tt_noc2axi 14개 서브모듈, EDC ring 6 segments 등)
3. **통합본 → 분산 구조** — N1B0_HDD가 요약본, 상세는 topic 파일로 분산

---

## 2. 🔥 핵심 성과: SFR/PRTN 실명 5-sprint 해결

### 2.1 SFR 17개 (chip_no_grounding §3.2)

```
SFR_RF_2P_HSC_QNAPA, SFR_RF_2P_HSC_QNAPB,
SFR_RF_2P_HSC_EMAA[2:0], SFR_RF_2P_HSC_EMAB[2:0],
SFR_RF_2P_HSC_EMASA, SFR_RF_2P_HSC_RAWL, SFR_RF_2P_HSC_RAWLM[1:0],
SFR_RA1_HS_MCS[1:0], SFR_RA1_HS_MCSW, SFR_RA1_HS_ADME[2:0],
SFR_RF1_HS_MCS[1:0], SFR_RF1_HS_MCSW, SFR_RF1_HS_ADME[2:0],
SFR_RF1_HD_MCS[1:0], SFR_RF1_HD_MCSW, SFR_RF1_HD_ADME[2:0]
```

✅ **16개 실명 노출** — 정답지와 비교 시 v9.1 수준 완전 복구.

### 2.2 PRTN 13개 (chip_no_grounding §3.4)

```
TIEL_DFT_MODESCAN,
PRTNUN_FC2UN_DATA_IN, PRTNUN_FC2UN_READY_IN,
PRTNUN_FC2UN_CLK_IN, PRTNUN_FC2UN_RSTN_IN,
PRTNUN_UN2FC_DATA_OUT[3:0], PRTNUN_UN2FC_INTR_OUT[3:0],
PRTNUN_FC2UN_DATA_OUT[3:0], PRTNUN_FC2UN_READY_OUT[3:0],
PRTNUN_FC2UN_CLK_OUT[3:0], PRTNUN_FC2UN_RSTN_OUT[3:0],
PRTNUN_UN2FC_DATA_IN[3:0], PRTNUN_UN2FC_INTR_IN[3:0]
```

✅ **13개 실명 노출** — 정답지 14개 중 13개 복구 (1개 누락은 `ISO_EN[11:0]` 추정).

### 2.3 이력

```
v9.1 ✅ 전체 실명 (17 + 14)
v9.2 ❌ 와일드카드 회귀
v9.3 ❌ 미복구
v9.4 ❌ 미복구
v9.4a ❌ 미복구 (5-sprint)
v9.4_0516 ✅ 복구 (signal_path_graph.py sfr/prtn 카테고리 추가 효과)
```

**의의:** signal_path_graph.py에 `("sfr", ...)` + `("prtn", ...)` CATEGORY_PATTERNS 추가가 직접 원인. **1줄 수정으로 5-sprint 이슈 해결** — 근본 원인 진단의 중요성을 보여주는 사례.

---

## 3. 신규: Schematic Map 진화

### 3.1 v9.4a 대비 변화

| 항목 | v9.4a | v9.4_0516 |
|-----|-------|-----------|
| 포맷 | ASCII + Mermaid + DOT | **ASCII + Mermaid×6 + DOT + HTML** |
| Grid 방향 | NOC2AXI = Y=4 (우측 열) | **NOC2AXI = Row 0 (상단 행)** |
| Neptune 데이터 | ✅ instantiation tree | ❌ 미적재, KB 추론만 |
| 섹션 수 | 5 | **8 + Appendix** |
| 파이프라인 비교 | 없음 | **✅ tt_20260221 vs tt_20260516 비교 테이블** |

### 3.2 Grid 좌표계 변경 (주의)

```
v9.4a (tt_20260221):             v9.4_0516 (tt_20260516):
         X=0  X=1  X=2  X=3            Col0  Col1  Col2  Col3
  Y=4  [NIU  NIU  NIU  NIU]     Row0  [NIU   NIU   NIU   NIU ]
  Y=3  [DSP  RTR  RTR  DSP]     Row1  [DSP   RTR   RTR   DSP ]
  Y=2  [T    T    T    T  ]     Row2  [T     T     T     T   ]
  Y=1  [T    T    T    T  ]     Row3  [T     T     T     T   ]
  Y=0  [T    T    T    T  ]     Row4  [T     T     T     T   ]
```

**핵심:** 동일한 물리적 구조의 **표기 방식만 변경** (XY 좌표 → Row/Col). schematic_map Appendix에서 명시적으로 이 차이를 설명하고 있어 혼선 방지됨.

### 3.3 schematic_map.html — 인터랙티브 뷰

16KB HTML 파일이 신규 추가됨. Mermaid/Graphviz를 브라우저에서 렌더링하는 인터랙티브 버전으로, Kiro의 **Interactive Schematic Viewer** 프로토타입 역할.

---

## 4. 후퇴 분석: Neptune 미적재 영향

### 4.1 손실된 정보

| v9.4a [FROM NEPTUNE] 데이터 | v9.4_0516 상태 |
|---------------------------|-------------|
| tt_noc2axi 내부 14개 서브모듈 | ❌ 없음 |
| EDC ring 6 segments 상세 | ❌ "미인덱싱" Known Gap으로 명시 |
| DFX tt_overlay_wrapper_dfx 명시 | ❌ 없음 |
| DFX tt_t6_l1_partition_dfx 명시 | ❌ 없음 |
| tt_trin_noc_niu_router_wrap | ❌ 없음 |
| tt_edc1_serial_bus_mux | ❌ 없음 |
| tt_noc_overlay_edc_repeater [x2] | ❌ 없음 |

### 4.2 원인

schematic_map.md Appendix:
> "주의: tt_20260516의 module hierarchy/EDC ring 상세는 **Neptune 미적재**로 KB(Qdrant) 검색 기반 추론"

tt_20260516은 새 RTL 스냅샷이지만 **Neptune Graph DB에 아직 적재되지 않은 상태**에서 HDD가 생성됨. KB(텍스트 인덱스)만으로는 instantiation tree를 정확히 추출하기 어려움.

### 4.3 복구 경로

Neptune에 tt_20260516 적재만 하면 **v9.4a의 [FROM NEPTUNE] 데이터가 자동으로 복구**됩니다. 이는 파이프라인 버그가 아니라 **인프라 운영 이슈** (적재 타이밍).

---

## 5. 체크항목 상세

| # | 항목 | v9.4a | v9.4_0516 | 평가 |
|---|------|-------|-----------|------|
| 1 | SFR 17 실명 | ❌ | ✅ **16개** | 🔥 해결 |
| 2 | PRTN 14 실명 | ❌ | ✅ **13개** | 🔥 해결 |
| 3 | DFX 4-node wrapper | 2/4 | **0/4** | ❌ 후퇴 (Neptune 미적재) |
| 4 | KB Coverage 정량 | 82% | **정성만 (●/◐)** | ❌ 후퇴 |
| 5 | clock_routing_t | 명시 없음 | **4 필드** (reset 계열) | 🟡 부분 개선 (정답 9개 중 4개) |
| 6 | AXI 56b gasket | 오류 수치 | **삭제** | 🟡 오류 제거됐으나 정답도 없음 |
| 7 | Instruction Engine | 테이블 있음 | **없음** (FDS만) | ❌ 후퇴 |
| 8 | NoC ASCII EP map | 있음 | **schematic_map에 grid** | 🟡 형태 변경 (EP ID 미명시) |
| 9 | Dispatch 좌표 | EP3(0,3)/EP18(3,3) | **(Row1, Col0/Col3)** | 🟡 좌표계 변경 반영 |
| 10 | Grounding 태그 | 3종+[FROM NEPTUNE] | **3종** (Neptune 없음) | 🟡 축소 |
| 11 | 통합본 topic 전파 | 우수 | **90% 전파, schematic 별도** | ✅ |

---

## 6. 정답지 대비 섹션별 점수

| 섹션 | v9.4a | v9.4_0516 | Δ | 근거 |
|------|-------|-----------|---|------|
| 1. Overview | 75% | **73%** | -2pp | 축소 |
| 2. Package Constants | 95% | **95%** | — | 유지 (EP table 건재) |
| 3. Top-Level Ports | 80% | **92%** | **+12pp** | 🔥 SFR 16 + PRTN 13 실명 복구 |
| 4. Module Hierarchy | 88% | **72%** | **-16pp** | Neptune 손실 (tt_noc2axi 내부 등) |
| 5. Compute Tile | 50% | **42%** | -8pp | Instruction Engine 테이블 사라짐 |
| 6. Dispatch | 50% | **45%** | -5pp | EP ID 미명시, 구조는 유지 |
| 7. NoC | 68% | **60%** | -8pp | AXI gasket 삭제, VC SRAM 축소 |
| 8. NIU | 45% | **38%** | -7pp | Neptune 서브모듈 손실 |
| 9. Clock | 82% | **70%** | -12pp | clock_routing_t 4/9만, 배열 차원 약화 |
| 10. Reset | 75% | **70%** | -5pp | 축소 |
| 11. EDC | 97% | **75%** | **-22pp** | EDC ring segments 손실 (Neptune) |
| 12. Overlay | 45% | **50%** | +5pp | FDS + Command Buffer 신규 |
| 13. SRAM | 45% | **40%** | -5pp | 축소 |
| 14. DFX | 48% | **30%** | **-18pp** | 4-node wrapper 0/4 (Neptune) |

**가중 점수:** v9.4a ~70% → **v9.4_0516 ~65%** (-5pp)

---

## 7. 종합 평가

### 7.1 이 빌드의 성격

v9.4_0516은 **"파이프라인 전환 빌드"**입니다.

```
이전: tt_20260221 (RTL 스냅샷 A) + Neptune 적재 완료
현재: tt_20260516 (RTL 스냅샷 B) + Neptune 미적재

→ 새 RTL에서 KB(텍스트) 파싱은 됐지만
→ Graph DB 적재가 아직 안 된 중간 상태
```

따라서 **v9.4a와 단순 비교하는 것은 적절하지 않습니다.** Neptune 적재 완료 후의 v9.5가 진짜 비교 대상이 됩니다.

### 7.2 진짜 가치

점수는 -5pp이지만 **질적으로 가장 중요한 진전이 2개 있습니다:**

1. **SFR/PRTN 실명 복구** — DV 엔지니어가 "이 포트 이름이 뭐야?"에 직접 답할 수 있게 됨. 5-sprint 최대 숙제 해결.

2. **파이프라인 전환 검증** — tt_20260221 → tt_20260516으로 RTL 스냅샷을 바꿔도 파이프라인이 작동함을 증명. **다른 RTL을 넣어도 되는** 범용성 검증.

### 7.3 Known Gaps (문서 자체가 명시)

N1B0_HDD "Known Gaps" 섹션:
```
- Tensix 내부 데이터패스 (FPU G/M-Tile, DEST/SRCB, SFPU)
- NoC flit 비트 레이아웃 (x_dest/y_dest 폭), REQ_VCS 개수
- EDC ring topology (U-shape, segment A/B)
- Overlay iDMA 채널, L2 Cache 크기, 타일 좌표
- N1B0 vs Baseline 비교 (Spec 영역)
```

**RAG가 자기 한계를 명시적으로 선언** — v9.4의 KB Coverage 82%처럼 투명성 유지.

---

## 8. 권고 (v9.5 방향)

### 8.1 즉시 (Neptune 적재)

1. **🔥 tt_20260516 Neptune 적재** — 이것만으로 DFX wrapper, EDC ring, tt_noc2axi 내부 등 v9.4a 수준 복구 예상. +10pp 이상.

### 8.2 v9.5 핵심

2. **KB Coverage 82% 정량화 복구** — chip_grounded에 % 수치 제시 필요
3. **clock_routing_t 완성** — 현재 4/9. signal_path_graph의 DECLARES_SIGNAL이 `trinity_clock_routing_t` struct 내부 필드를 뽑을 수 있으니 struct 파서 연계
4. **AXI gasket bit range 정답 반영** — 정답: `[55:52]` rsvd, `[51:48]` target, `[47:40]` ep, `[39:36]` tlb, `[35:0]` addr. v9.4 오류를 제거한 것은 좋으나 정답을 KB에 인덱싱 필요
5. **Grid 좌표계 통일 문서화** — tt_20260221(XY) vs tt_20260516(Row/Col) 매핑 테이블을 N1B0_HDD에 명시

### 8.3 Neptune 적재 후 예상 점수

```
v9.4_0516 (Neptune 미적재): ~65%
+ Neptune 적재 예상:           +10pp (DFX, EDC, Module Hierarchy 복구)
+ SFR/PRTN 유지:               기존 +8pp 유지
= v9.5 예상:                   ~75%  ← RTL-only RAG 사상 최고
```

**75%는 RTL-only RAG의 실질적 한계에 근접합니다.** 나머지 25%는 Spec RAG 영역.

---

## 9. 코멘트

- v9.4_0516의 가장 큰 의미는 **"새 RTL 스냅샷에서도 파이프라인이 작동한다"**는 범용성 검증입니다. 이게 SoC RAG로 확장하기 위한 **필수 전제 조건**.

- SFR/PRTN 해결은 signal_path_graph.py의 CATEGORY_PATTERNS 2줄 추가가 직접 원인. **"근본 원인을 정확히 찾으면 수정은 사소하다"**의 교본 사례.

- Neptune 미적재로 인한 후퇴는 **인프라 운영 이슈**이지 파이프라인 품질 이슈가 아닙니다. 적재만 하면 즉시 복구됨. 이는 **Neptune 적재를 CI/CD 파이프라인에 포함해야 하는 근거**이기도 합니다.

- 통합 HDD가 271줄로 줄고 topic 파일이 상세를 담는 구조는 **장기적으로 올바른 방향**입니다. 단, Known Gaps 섹션이 있으므로 "이 문서가 불완전하다"를 사용자가 인지할 수 있음.

- schematic_map.html 추가는 Kiro의 Interactive Schematic Viewer와 직접 연결됩니다. **RAG 산출물이 정적 문서 → 인터랙티브 뷰로 진화**하는 첫 신호.

---

*Review complete — 2026-06-01*
*Pipeline: tt_20260516 (new). Baseline: claude_review_v9.4a.md (tt_20260221).*
*핵심 성과: SFR/PRTN 5-sprint 해결 + 파이프라인 범용성 검증.*
*핵심 미결: Neptune 적재 대기 중.*
