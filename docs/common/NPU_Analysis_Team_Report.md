# NPU 분석팀 작업 현황 리포트

**작성일:** 2026-06-01
**대상:** Kiro 논의용 / NPU RAG 개선 입력 자료
**소스:** `test_rtl/Sample/CLAUDE_DBS/` (Claude Desktop/Code 기반 작업 아카이브)
**용도:** 본 리포트는 보완 후 **NPU RAG 시스템 개선(v9.5 Knowledge Import)**의 근거 자료로 사용된다.

> **측정 기준 주의:** 본 문서의 정확도 수치는 두 가지 체계가 혼재하므로 아래 정의를 따른다.
> - **L1~L6 프레임워크** (`test_rtl/rag_result/prompt.md` 기준): L1 구조 / L2 인터페이스 / L3 연결 / L4 파라미터 / L5 동작 / L6 의도. v9.4부터 정식 측정.
> - **Content Fidelity (가중)**: 정답지 대비 fact 일치도 가중 평균. v9.1 ~74%, v9.4 계열은 L1~L6 가중 시 ~65% 수준(L4~L6 저조).
> - 두 수치가 다른 이유: L1(구조)은 88%로 높지만 L4~L6(파라미터/동작/의도)이 5~38%로 낮아, 가중 평균(Content Fidelity)은 단일 L1 수치보다 낮게 나온다.

---

## 1. 요약

NPU 분석팀(Alpha 4인)이 2026-03 ~ 2026-04에 걸쳐 Claude Desktop/Code를 직접 사용하여 **RTL-verified HDD** 작업을 수행. **51개 토픽 memory 파일(ID 기준 M1~M52, 일부 결번·중복 ID 포함)** + 10개 N1B0 adapted archive + reference docs를 축적하였으며, 이는 현재 RAG 시스템(v9.4_0516 기준 L1 구조 ~88%이나 L4 파라미터 ~38%·L5 동작 ~28%로 **가중 Content Fidelity ~65%**)보다 **높은 정확도(95%+)**의 검증된 지식을 보유. v9.3 정식 평가에서 RAG 산출물은 **48/100**이었다.

---

## 2. 산출물 규모

| 카테고리 | 파일 수 | 핵심 내용 |
|---------|--------|----------|
| 토픽 메모리 (ID M1-M52) | 51 파일 | RTL 분석 결과, 파라미터 검증, 계산 도출 (ID는 M52까지 부여되나 M30·M50 등 결번 및 M48 중복으로 실제 파일은 51개) |
| N1B0 Adapted (A1-A10) | 10 | N1B0 변종 전용 지식 (baseline 대비 차이) |
| Feedback Rules (FB1-FB4) | 4 (파일 5개, FB3 중복) | 검증 방법론, 버전 관리 규칙 |
| Reference HDDs | 15+ | EDC V0.9, Router V0.5, NIU V0.1, Overlay V0.3 등 |
| 총 지식 단위 (추정) | **400-600 claims** | atomic fact 기준 |

> 디렉토리 실측: `test_rtl/Sample/CLAUDE_DBS/` 총 87개 파일 (memory 51 + N1B0_A 10 + FB 5 + reference/memlist 등 21).

---

## 3. 주요 성과

### 3.1 RTL-Verified 교정 (HDD v1.00)

| 교정 항목 | 이전(오류) | 이후(RTL 검증) | 오류 배율 | RTL 증거 |
|----------|-----------|---------------|----------|----------|
| SRCA rows | 256 | **48** | 5.3× 과대 | tt_tensix_pkg.sv:35 (SRCS_NUM_ROWS_16B=48) |
| SRCB rows/bank | 128 | **64** | 2× 과대 | RTL diagram verified |
| INT16 MACs/G-Tile | 64 | **256** | 4× 과소 | 8×2×2×8=256 |
| DEST entries/bank | 8,192 INT32 | **1,024 INT32** | 8× 과대 | tt_gtile_dest.sv:61-62 (BANK_ROWS_16B=512, NUM_COLS=4) |
| DEST capacity/G-Tile | 8 KB | **16 KB** | 2× 과소 | 4,096×4 bytes (m40 #6) |

> **주의 — 두 개의 DEST 교정은 서로 다른 레벨이다.**
> - `m31_dest_capacity_verified.md`: **bank당 INT32 엔트리** 교정 (8,192 → 1,024). "16 slices" 오기 → 실제 NUM_COLS=4.
> - `m40_n1b0_hdd_v1_00_corrections.md` #6: **G-Tile당 바이트 용량** 교정 (8 KB → 16 KB). 4,096 INT32 × 4 bytes.
> 두 수치가 모순이 아니라 측정 단위(엔트리 vs 바이트, bank vs G-Tile)가 다름.

**총 9개 오류 발견, 7건 교정 완료** (`HDD_v1.00_ERROR_REPORT.md` 9건 분석, `HDD_v1.00_CORRECTIONS_APPLIED.md` 7건 적용). 남은 2건은 비치명적(moderate)으로 미교정. 모든 교정에 RTL file:line 증거 첨부.

### 3.2 핵심 검증 결과

- **INT8 8,192 MACs/cluster** 완전 도출 (NUM_PAIR=8, HALF_FP_BW=1, two-phase latch)
- **Register file 용량 equation** 6-level decomposition (G-Tile → Tensix → Cluster → SoC = 7.7MB)
- **SDC 20260221↔20260404** 139,783 constraint 100% 동일 확인
- **EDC ring** per-column 독립 4 rings, V0.9까지 완전 문서화
- **NOC2AXI Router** 4 variants (R/C 구조, VC 수 차이, FIFO 비대칭) 분석

### 3.3 확립된 방법론 (FB4)

> "모든 HDD 스펙 주장은 RTL 파라미터 대조 없이 accept하지 마라"

1. Claim 카테고리 식별 (register size, throughput, hierarchy, physical)
2. RTL ground truth 위치 확인 (tt_tensix_pkg.sv:35 등)
3. 계산 cross-verify (first principles에서 도출)
4. Discrepancy 문서화 (before/after, 오류 배율, 심각도)
5. 교정 + 인용 (RTL file:line 필수)

---

## 4. 토픽 커버리지 맵

| 토픽 | Memory ID | 완성도 | 비고 |
|------|----------|--------|------|
| EDC (링, 토폴로지, CDC) | M1-M4, M19-M20 | ✅ 완전 | V0.9, per-column 4 rings |
| Register File (DEST/SRCA/SRCB/SRCS) | M31, M39-M49 | ✅ 완전 | 7.7MB SoC 총계, dual-bank |
| FPU/MAC Throughput | M23, M48-M49 | ✅ 완전 | 8192 INT8, 2048 INT16 |
| NoC/NIU/Router | M6, M8, M13-M14, M33, M51 | ✅ 완전 | 5 variants, flit 928-bit |
| Overlay/CPU | M9, N1B0_A9 | ✅ 완전 | 9-level hierarchy |
| N1B0 Grid/Hierarchy | M11-M13 | ✅ 완전 | 4×5, 420+ SRAMs |
| TurboQuant | M25-M29 | ✅ 설계완료 | FWHT 권장, Phase 1 준비 |
| SDC Timing | M35-M38 | ✅ 완전 | 2 version 비교 검증 |
| DFX/P&R | M14-M17, M24 | ✅ 완전 | 4 wrapper, latch DFT |
| Data Control Path | M52 | ⚠️ 60% | DM↔TRISC IPC 미완 |
| Firmware/SW Guide | M18 | ⚠️ 인벤토리만 | 프로그래밍 가이드 미작성 |

---

## 5. RAG 시스템 대비 Gap

| 측면 | NPU 팀 (수동) | RAG v9.4_0516 | Gap |
|------|-------------|---------------|-----|
| 정식 평가 점수 (v9.3 기준) | 95+/100 | **48/100** | -47 |
| Content Fidelity (가중) | **95%+** | ~65% | -30pp |
| L1 구조 | ✅ | 88% | 깊이 외 양호 |
| L4 파라미터 | ✅ 모든 claim RTL-verified | **38%** | -57pp (최대 gap) |
| L5 동작 / L6 의도 | ✅ derivation chain 포함 | 28% / 5% | RTL 단독 한계 |
| RTL line-level 추적 | ✅ 모든 claim에 file:line | ❌ 모듈 수준까지만 | 깊이 |
| Derivation chain | ✅ 계산 과정 전체 기록 | ❌ 결과값만 (있으면) | 투명성 |
| Module hierarchy depth | **5-6 레벨** | 1-2 레벨 | 깊이 |
| Cross-verification | ✅ 체계적 (FB4) | ❌ dispatch 좌표만 | 범위 |
| 검색 가능성 | ❌ 로컬 파일만 | ✅ API로 접근 | 접근성 |
| 다중 사용자 공유 | ❌ 팀 4명만 | ✅ Beta 8명+ 접근 | 확장성 |

**핵심 Gap:** NPU 팀은 정확도 높지만 접근성 없음. RAG는 접근성 높지만 정확도 부족(특히 **L4 파라미터 38%·L5 동작 28%**가 병목). **둘을 합치면 양쪽 장점을 취할 수 있음** — NPU 팀의 RTL-verified 파라미터/derivation을 RAG에 import하면 가장 낮은 L4~L6 점수를 직접 끌어올린다.

---

## 6. v9.5 Knowledge Import 제안

### 6.1 방향

CLAUDE_DBS의 51개 memory + 10개 N1B0 archive의 verified knowledge를 RAG Claim DB에 bulk import하고, 동시에 v9.5 spec의 retrieval 개선(Re-Ranker, Graph RAG routing, semantic boundary chunking)을 적용하여:
- 현재 가중 ~65% → **85%+ Content Fidelity** 달성 (특히 L4 파라미터·L5 동작 집중 개선)
- Beta 8명이 NPU 팀의 verified knowledge에 검색으로 접근 가능
- 파서 개선 효과를 정량 측정할 evaluation ground truth 확보

> 본 import는 v9.5 spec(`rag-v9.5-knowledge-import`)의 Requirement 1(Bulk Import Pipeline)에 대응한다. 단순 적재가 아니라 retrieval 파이프라인 개선(Re-Ranker 등)과 병행해야 목표 점수에 도달한다.

### 6.2 Import 대상 우선순위

| 우선순위 | 대상 (MEMORY.md ID 기준) | 예상 Claims | 기대 효과 |
|---------|------|-----------|----------|
| P0 | M11-M14 (Grid, N1B0 Hierarchy, Router_OPT, DFX) | ~60 | L1 구조/Module Hierarchy +16pp 복구 |
| P0 | M1-M4, M19-M20 (EDC ring/CDC) | ~40 | EDC section +22pp 복구 |
| P1 | M39-M49 (Register file, FPU latch) | ~80 | L4 파라미터(Compute Tile) 대폭 향상 |
| P1 | M6, M8, M33 (Router, NIU, NOC2AXI variants) | ~50 | NoC/NIU 파라미터 완비 |
| P2 | M7, M21-M23 (Tensix core, SFPU, INT8 throughput) | ~60 | L5 동작(데이터패스) 복구 |
| P2 | 나머지 (TurboQuant, SDC, Firmware 등) | ~110 | 전 토픽 커버리지 |
| | **합계 (추정)** | **~400** | P0+P1만 = ~230 |

### 6.3 기대 효과 (점수 시뮬레이션)

```
현재 v9.4_0516:             ~65%
+ P0 import (EDC+Hierarchy): +12pp → 77%
+ P1 import (RegFile+NoC):   +8pp  → 85%
+ Re-Ranker 추가:            +5pp  → 90%
─────────────────────────────────────
v9.5 예상:                   ~88%  (RTL-only RAG 사상 최고)
```

> **⚠️ 위 수치는 검증되지 않은 추정(projection)이다.** 다음 가정에 기반한다:
> - **+12pp/+8pp 가정**: P0/P1 import claim이 정답지 fact와 1:1 매핑되어 L4 파라미터(현재 38%)를 직접 채운다고 가정. 실제 효과는 import claim의 질문 커버리지에 의존하며, 측정 전까지 미확정.
> - **Re-Ranker +5pp 가정**: v8 Hybrid에서 max_results sweep이 +13pp 기여한 전례에 근거한 보수적 추정. precision 향상 폭은 모델(Cohere Rerank-v3 등)·query 분포에 따라 달라진다.
> - **합산 가정의 한계**: pp 단순 합산은 효과 중복(같은 gap을 두 개선이 동시에 메움)을 무시한다. 실측 시 합보다 낮을 가능성이 높다.
> - 65%→88%(+23pp)는 단일 릴리즈로는 공격적 목표다. 보수 시나리오는 **77~80%**로 본다.
> - **검증 방법**: 6.1의 evaluation dataset 구축 후 import 전/후 동일 프롬프트로 A/B 측정하여 실측값으로 대체할 것.

### 6.4 Requirements 문서 위치

상세 요구사항: `.kiro/specs/rag-v9.5-knowledge-import/requirements.md` (15개 요구사항, 5개 카테고리)

---

## 7. 논의 필요 사항

1. **Import 범위 결정** — 51개 전체 vs P0/P1만 우선 (복잡도 vs 효과 trade-off). 전체 import 시 예상 ~400 claims, P0+P1만이면 ~230 claims.
2. **Import 충돌 처리 (P0 결정 필요)** — 같은 토픽이 이미 RAG Claim DB에 파서 생성 claim으로 존재할 때, NPU verified claim이 **override** 하는가, **병기**하는가, 아니면 **confidence_score 우선순위**로 검색 시점에 정렬하는가? NPU claim은 RTL-verified이므로 confidence=1.0을 부여하고 파서 claim(0.5~0.7)보다 우선 노출하는 방안이 유력하나, 동일 fact 중복 노출을 막을 dedup 정책 필요.
3. **CLAUDE_DBS 업데이트 주기** — 팀이 새 memory를 추가하면 자동 sync? 수동 batch? (FB3 규칙에 따라 팀은 MEMORY.md 인덱스를 갱신하므로, 인덱스 diff 기반 증분 import가 가능)
4. **NPU 팀의 RAG 사용 피드백** — import 후 팀이 직접 RAG를 써보고 "내가 아는 것과 다른가" 검증
5. **Evaluation dataset 구축 담당** — ground truth Q&A 쌍 100+ 생성을 누가 하는가 (Claude 자동 vs 팀 수동 검증). FB4 방법론(claim category → RTL ground truth → cross-verify)을 Q&A 생성 가이드로 재사용 가능.
6. **YAML frontmatter 표준화** — 일부 memory만 frontmatter(name/description/type)를 가짐(m31, m40 보유). import 파서가 frontmatter 없는 파일도 처리하도록 fallback 필요 (v9.5 Req 1 대응).

---

## 8. NPU RAG 개선 연계 (Action Items)

본 리포트는 v9.5 Knowledge Import의 입력 자료다. 보완 완료 후 다음 순서로 진행한다:

1. **(선행) Neptune/Claim DB 적재 안정화** — tt_20260516 재인덱싱으로 파서 claim·그래프가 채워진 상태에서 import해야 충돌 정책(논의 2)을 정확히 적용 가능.
2. **Evaluation dataset 우선 구축** — import "전" baseline을 L1~L6로 정식 측정해야 효과를 정량화할 수 있다 (현재 65%는 추정치).
3. **P0 import 파일럿** — M1-M4(EDC) + M11-M14(Hierarchy/Router/DFX) 약 100 claims만 먼저 적재 → A/B 측정 → 6.3 추정 검증.
4. **결과 기반 P1/P2 확대 판단** — 파일럿 실측이 추정의 50% 이상 효과면 전체 진행, 미만이면 import 방식(claim 분해 단위) 재설계.

> 핵심 원칙: **추정(6.3)을 실측으로 대체하기 전까지 v9.5 목표 점수를 확정하지 않는다.** 파일럿 → 측정 → 확대의 증분 접근.

---

*End of Report*
