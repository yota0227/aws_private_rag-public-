# RAG v3 Claim Filter Fix 품질 검증 — v4.1 평가 보고서

**문서 ID:** REVIEW-RAG-V4.1-QUALITY-001  
**버전:** v4.1  
**작성일:** 2026-04-24  
**이전 버전:** claude_review_v1.1 (v3 vs v2.5 비교 + Claim 필터링 부작용 진단)  
**분석 대상:** `test_rtl/rag_result/v4.1/` (RAG v3 + Claim Filter Fix)

---

## 목차

1. [분석 배경](#1-분석-배경)
2. [적용된 수정 사항](#2-적용된-수정-사항)
3. [파일 규모 비교](#3-파일-규모-비교)
4. [문서별 비교 분석](#4-문서별-비교-분석)
5. [종합 커버리지 판정](#5-종합-커버리지-판정)
6. [KB Grounding vs LLM Inference 구분](#6-kb-grounding-vs-llm-inference-구분)
7. [Claim 필터 수정 효과 검증](#7-claim-필터-수정-효과-검증)
8. [결론 및 다음 단계](#8-결론-및-다음-단계)

---

## 1. 분석 배경

### 1.1 버전 로드맵

| RAG 버전 | 저장 위치 | 주요 변경 사항 | 커버리지 목표 |
|----------|----------|----------------|--------------|
| v2.5 | `v3/` | chip_config + edc_topology + noc_protocol + overlay_deep + sram_inventory | 55% |
| v3 | `v4/` | 포트 비트폭 추출, 토픽 확장, Claim 귀속 수정 | 70% |
| **v3 + fix** | **`v4.1/`** | **Claim 필터 수정 (옵션 A+B+C 적용)** | **70%** |
| v5 (계획) | — | 검색 정밀도 개선 | 75% |
| v6 (계획) | — | 크로스-토픽 통합, 계층 연결 | 85% |

### 1.2 평가 목적

`claude_review_v1.1`에서 진단한 **Claim 필터링 부작용**(EDC -11%p, Overlay -42%p 퇴보)이 수정 후 해소되었는지 검증하고, v4.1의 실제 커버리지를 판정한다.

---

## 2. 적용된 수정 사항

### 2.1 옵션 A — 패턴 축소

```python
# Before
REGISTER_WRAPPER_PATTERNS = ["_reg_inner", "_wrap", "_reg_top"]

# After — _wrap 제거
REGISTER_WRAPPER_PATTERNS = ["_reg_inner", "_reg_top"]
```

`tt_edc1_biu_soc_apb4_wrap`(APB4-BIU 브릿지)이 더 이상 레지스터 래퍼로 오분류되지 않음.

### 2.2 옵션 B — fallback 임계값 상향

```python
# Before
if len(datapath) < 3:
    datapath.extend(register)

# After
if len(datapath) < 10:
    datapath.extend(register)
```

파서 확장으로 datapath 모듈이 증가해도 `_reg_inner` 모듈들이 fallback으로 포함될 가능성을 높임.

### 2.3 옵션 C (부분) — 기능 블록 화이트리스트

```python
FUNCTIONAL_BLOCK_PREFIXES = [
    "tt_edc1_biu_", "tt_cluster_ctrl_", "tt_fds_",
    "tt_dispatch_", "tt_overlay_reg_xbar_",
]
```

확인된 기능 블록은 이름 패턴과 무관하게 datapath로 보존.

---

## 3. 파일 규모 비교

| 문서 | v3 (v2.5) | v4 (v3) | v4.1 (v3+fix) | 증가율 (v4→v4.1) |
|------|-----------|---------|---------------|-------------------|
| Chip (no grounding) | 13.0 KB | 17.6 KB | **22.7 KB** | +29% |
| Chip (grounded) | 11.8 KB | 6.3 KB | **23.5 KB** | +273% |
| EDC | 11.6 KB | 20.5 KB | **26.6 KB** | +30% |
| NoC | 7.6 KB | 19.2 KB | **38.0 KB** | +98% |
| Overlay | 12.6 KB | 21.6 KB | **46.7 KB** | +116% |
| **합계** | **56.6 KB** | **85.2 KB** | **157.5 KB** | **+85%** |

> 전 문서에서 v4 대비 대폭 증가. 특히 Overlay(+116%)와 NoC(+98%)에서 claim 복원 + 심화 효과가 뚜렷함.

---

## 4. 문서별 비교 분석

### 4.1 칩 전체 HDD (no grounding) — v4.1 ~80-85%

| 항목 | v4 (~55%) | v4.1 (~80-85%) | 변화 |
|------|-----------|----------------|------|
| 그리드 레이아웃 | 언급 없음 | 4×5 ASCII art, 타일 타입별 배치도 | **신규** |
| Top-level 포트 | 약 10개 | 24개 포트 (AXI/EDC/JTAG/Scan/Overlay) | **대폭 확장** |
| 모듈 계층 | 7개 인스턴스 flat | 완전한 트리 (3단계 깊이, 하위 모듈 포함) | **대폭 확장** |
| 클럭 아키텍처 | 4개 도메인 기본 | PLL 구조도 + CDC synchronizer + 도메인별 소비자 | **심화** |
| 리셋 아키텍처 | 4개 리셋 신호 | 파워 파티션별 리셋 체인, 비동기 assert/동기 deassert | **심화** |
| DFX (iJTAG/Scan) | 없음 | iJTAG SIB 계층, 스캔 체인 구조 | **신규** |
| SRAM Inventory | 없음 | 7개 SRAM 인스턴스, ECC 타입, 클럭 도메인 | **신규** |
| `[TBC]` 태그 사용 | 없음 | 미확인 수치에 일관 적용 | **방법론 개선** |

> v4.1a는 HDD의 구조적 완성도가 가장 높은 문서. 검색에서 직접 확인되지 않은 값에 `[TBC]`를 달아 KB 기반 vs 추론 영역을 구분한 점이 주목할 만함.

### 4.2 칩 전체 HDD (grounded) — v4.1 ~46%

| 항목 | v4 (~40%) | v4.1 (~46%) | 변화 |
|------|-----------|-------------|------|
| 문서 길이 | 6.3 KB | 23.5 KB | **+273%** |
| HDD 섹션 토픽 | SFPU/Clock/SMN/NoC/FPU (5개) | FPU/SFPU/SMN/NoC/EDC + Overlay CDC | **토픽 확장** |
| NoC claim | 없음 | arbiter_tree, repeater 구조 | **복원** |
| EDC modport | 없음 | ingress/egress/edc_node/sram 4개 | **복원** |
| Overlay CDC | 없음 | `TTTrinityConfig_IntSyncAsyncCrossingSink_n1x1` 확인 | **복원** |
| Grounding 비율 | ~40% | ~46% (strict KB only) | **소폭 개선** |

> Grounded 버전은 KB에서 직접 확인된 데이터만 포함하므로 커버리지가 낮지만, v4에서 소실된 EDC modport와 NoC claim이 복원됨.

### 4.3 EDC 서브시스템 — v4.1 ~85-90% (v4 대비 +58%p)

| 항목 | v3 (~38%) | v4 (~27%) | v4.1 (~85-90%) | 변화 |
|------|-----------|-----------|----------------|------|
| BIU 모듈 | `tt_edc1_biu_soc_apb4_wrap` claim | **소실** | **복원** + 레지스터 맵 (8개 CSR) | **대폭 확장** |
| Serial Bus 신호 | req_tgl, ack_tgl, cor_err, err_inj_vec | NOT IN KB | 복원 + 패킷 포맷, opcode 테이블 | **대폭 확장** |
| Modport 구조 | 4개 modport 확인 | 없음 | 4개 modport + 신호 방향 상세 | **복원+심화** |
| Ring Topology | NOT IN KB | U-shape 추론 | U-shape 40 hop + Node ID 12-bit 구조 | **대폭 확장** |
| Harvest Bypass | 없음 | 없음 | MUX/DEMUX 바이패스 로직 상세 | **신규** |
| CDC Synchronizer | 없음 | 없음 | edc_clk ↔ ref_clk crossing 상세 | **신규** |
| Module Tree | 1개 leaf | 2개 top-level | 완전한 하위 계층 트리 | **대폭 확장** |

> v4에서 가장 심각한 퇴보를 보였던 EDC가 v4.1에서 가장 큰 도약. BIU claim 복원이 핵심 트리거이며, 이를 기반으로 레지스터 맵, 패킷 포맷, 링 토폴로지까지 연쇄적으로 확보됨.

### 4.4 NoC 라우팅/패킷 — v4.1 ~90-95% (v4 대비 +55%p)

| 항목 | v3 (~35%) | v4 (~35%) | v4.1 (~90-95%) | 변화 |
|------|-----------|-----------|----------------|------|
| 라우팅 알고리즘 | NOT IN KB | NOT IN KB | **3종** (DOR/Tendril/Dynamic) + pseudo-RTL | **신규** |
| Flit 구조 | NOT IN KB | NOT IN KB | **512-bit** bit-level 필드 분해 | **신규** |
| AXI Gasket | 없음 | 없음 | 56-bit 주소 분해 (row/col/reg/offset) | **신규** |
| Virtual Channel | NOT IN KB | NOT IN KB | **4 VC** + credit 기반 flow control | **신규** |
| Security Fence | 없음 | 없음 | SMN group matching, per-VC 보안 | **신규** |
| Router Hierarchy | 1개 leaf | 5개 모듈 flat | 완전한 계층 + 인스턴스 수 | **대폭 확장** |
| Endpoint Map | 없음 | 없음 | 4×5 그리드 엔드포인트 맵 | **신규** |
| 파라미터 | 없음 | 없음 | 30+ 파라미터 + 유도 상수 | **신규** |

> v3/v4에서 가장 약했던 프로토콜 세부(라우팅/flit/VC)가 v4.1에서 전면 확보. claim 복원과 module_parse 심화의 시너지 효과.

### 4.5 Overlay (RISC-V) — v4.1 ~90-95% (v4 대비 +90%p)

| 항목 | v3 (~42%) | v4 (~0%) | v4.1 (~90-95%) | 변화 |
|------|-----------|----------|----------------|------|
| Claim 데이터 | 3건 | **0건** | **다수** (cluster_ctrl, fds, dispatch 등) | **완전 복원+확장** |
| CPU 스펙 | 없음 | 없음 | 8× RV64GC 코어, L1 I$/D$, 1MB scratchpad | **신규** |
| iDMA | 없음 | 없음 | scatter-gather, 2D 전송 | **신규** |
| ROCC Interface | 없음 | 없음 | 커스텀 가속기 인터페이스 신호 상세 | **신규** |
| LLK Flow | 없음 | 없음 | 6-step 디스패치 흐름 | **신규** |
| SMN Firewall | 없음 | 없음 | 보안 필터링, trust level | **신규** |
| FDS Ring Oscillator | 없음 | 없음 | 주파수 모니터링 로직 | **신규** |
| Dispatch East/West | CPU I/F 신호 일부 | 없음 | 동작 모드, 파이프라인 구조 상세 | **대폭 확장** |
| CPU→NoC 경로 | 없음 | 없음 | 8-step 트랜잭션 흐름 | **신규** |
| APB Slave Map | 없음 | 없음 | 9개 슬레이브 + 주소 맵 | **신규** |
| RTL Files | 없음 | 없음 | 19개 소스 파일 목록 | **신규** |

> v4에서 **0%로 완전 소실**되었던 Overlay가 v4.1에서 **~90-95%로 최대 도약**. 필터 수정으로 claim이 복원되면서 Chipyard/ROCC/LLK/FDS 등 RISC-V 서브시스템 전체가 연쇄적으로 확보됨.

---

## 5. 종합 커버리지 판정

| 문서 | v3 (v2.5) | v4 (v3) | v4.1 (v3+fix) | 로드맵 목표 | 판정 |
|------|-----------|---------|---------------|------------|------|
| Chip (no grounding) | ~35% | ~55% | **~80-85%** | v5: 75% | **v5 목표 초과** |
| Chip (grounded) | ~25% | ~40% | **~46%** | — | KB grounding 한계 |
| EDC | ~38% | ~27% | **~85-90%** | v6: 85% | **v6 목표 도달** |
| NoC | ~35% | ~35% | **~90-95%** | v6: 85% | **v6 목표 초과** |
| Overlay | ~42% | ~0% | **~90-95%** | v6: 85% | **v6 목표 초과** |
| **가중 평균 (no grounding 기준)** | **~37%** | **~34%** | **~87%** | v6: 85% | **v6 달성** |

### 버전별 추이 그래프 (텍스트)

```
100% ┬─────────────────────────────────────────────
     │                              ████ ████ ████
 90% ┤                              ████ ████ ████
     │                         ████ ████ ████ ████
 80% ┤                         ████ ████ ████ ████  ← v6 목표 (85%)
     │                         ████ ████ ████ ████
 70% ┤                         ████ ████ ████ ████  ← v5 목표 (75%)
     │                         ████ ████ ████ ████  ← v4 목표 (70%)
 60% ┤                         ████ ████ ████ ████
     │                    ▓▓▓▓ ████ ████ ████ ████
 50% ┤                    ▓▓▓▓ ████ ████ ████ ████
     │               ░░░░ ▓▓▓▓ ████ ████ ████ ████
 40% ┤          ░░░░ ░░░░ ▓▓▓▓ ████ ████ ████ ████
     │     ░░░░ ░░░░ ░░░░ ▓▓▓▓ ████ ████ ████ ████
 30% ┤     ░░░░ ░░░░ ░░░░ ▓▓▓▓ ████ ████ ████ ████
     │     ░░░░ ░░░░ ░░░░ ▓▓▓▓      ▓▓▓▓
 20% ┤     ░░░░ ░░░░ ░░░░
     │
 10% ┤
     │                                   ▓▓▓▓
  0% ┼──────────────────────────────────────────────
       Chip   EDC   NoC  Overlay  Chip   EDC  NoC Overlay
       ──── v3 (v2.5) ────────   ────── v4 (v3) ────────

       Chip   EDC   NoC  Overlay
       ──── v4.1 (v3+fix) ─────

     ░░░░ v3 (v2.5)   ▓▓▓▓ v4 (v3)   ████ v4.1 (v3+fix)
```

---

## 6. KB Grounding vs LLM Inference 구분

### 6.1 중요한 주의사항

v4.1의 높은 커버리지(80-95%)에는 **LLM inference가 상당 부분 포함**되어 있다. v4.1b (grounded 버전)이 ~46%인 것은 KB에서 직접 확인 가능한 데이터의 실제 비율을 보여준다.

### 6.2 예시 — v4.1a Chip (no grounding)

| 카테고리 | 내용 | 출처 |
|----------|------|------|
| 그리드 4×5 | Col 0-4 × Row 0-3 배치도 | KB claim 기반 |
| 포트 24개 | AXI/EDC/JTAG/Scan 신호 목록 | module_parse 기반 |
| FPU 지원 포맷 "FP32, BF16, FP16, TF32" | **[TBC] 태그 부착** | **LLM inference** |
| L1 캐시 용량 "[TBC] KB per tile" | **[TBC] 태그 부착** | **LLM inference** |
| PLL 구조 (pll_ai, pll_noc, pll_dm) | 도메인 이름은 KB, 세부 구조는 추론 | **혼합** |

### 6.3 [TBC] 태그의 의미

v4.1a에서 도입된 `[TBC]` (To Be Confirmed) 태그는 "KB에서 직접 확인되지 않은 수치"를 표시한다. 이는 v3/v4에는 없던 방법론적 개선으로, HDD의 신뢰성 등급을 자체적으로 구분한다.

| 등급 | 의미 | 예시 |
|------|------|------|
| 수치 직접 기재 | KB에서 파싱/claim으로 확인됨 | `GridSizeX = 5`, `NumTensix = 12` |
| `[TBC]` | LLM이 구조적으로 추론했으나 KB에서 미확인 | `FP32, BF16 [TBC]`, `1 MAC/cycle [TBC]` |
| NOT IN KB | 검색 결과 없음 (v3/v4에서 사용) | v4.1에서는 `[TBC]`로 대체 |

---

## 7. Claim 필터 수정 효과 검증

### 7.1 필터에 걸렸던 4개 모듈 복원 확인

| 모듈 | v4 상태 | v4.1 상태 | 복원 확인 |
|------|---------|-----------|-----------|
| `tt_edc1_biu_soc_apb4_wrap` | 필터됨 (패턴: `_wrap`) | **복원** — BIU 레지스터 맵 8개 CSR | O (옵션 A) |
| `tt_cluster_ctrl_reg_inner` | 필터됨 (패턴: `_reg_inner`) | **복원** — 클러스터 제어 레지스터 | O (옵션 B+C) |
| `tt_fds_dispatch_reg_inner` | 필터됨 (패턴: `_reg_inner`) | **복원** — FDS 디스패치 레지스터 | O (옵션 B+C) |
| `tt_fds_tensixneo_reg_inner` | 필터됨 (패턴: `_reg_inner`) | **복원** — FDS Tensix/Neo 레지스터 | O (옵션 B+C) |

### 7.2 수정 옵션별 기여

| 옵션 | 적용 | 효과 |
|------|------|------|
| **A. `_wrap` 패턴 제거** | O | `tt_edc1_biu_soc_apb4_wrap` 직접 복원 → EDC BIU 섹션 전체 복구 |
| **B. 임계값 3→10** | O | `_reg_inner` 모듈들이 fallback으로 포함될 확률 대폭 증가 |
| **C. 화이트리스트 (부분)** | O | `tt_edc1_biu_`, `tt_cluster_ctrl_`, `tt_fds_` 등 확인된 기능 블록 보호 |

### 7.3 연쇄 효과

```
Claim 필터 수정
    │
    ├─► tt_edc1_biu_soc_apb4_wrap 복원
    │       │
    │       ├─► BIU 레지스터 맵 (8 CSR) 확보
    │       ├─► EDC 패킷 포맷 + opcode 확보
    │       └─► Ring topology 40-hop 구조 상세화
    │
    ├─► tt_cluster_ctrl_reg_inner 복원
    │       │
    │       ├─► 8× RV64GC CPU cluster 구조 확보
    │       └─► SMN firewall + trust level 확보
    │
    ├─► tt_fds_dispatch_reg_inner 복원
    │       │
    │       ├─► Dispatch East/West 파이프라인 확보
    │       └─► LLK 6-step flow 확보
    │
    └─► tt_fds_tensixneo_reg_inner 복원
            │
            ├─► ROCC interface 확보
            └─► FDS ring oscillator 확보
```

> 4개 모듈의 claim 복원이 **문서 전체의 깊이를 연쇄적으로 확장**시킴. 단순 복원이 아니라, 복원된 claim이 LLM의 추론 기반을 넓혀 관련 세부사항까지 풍부해진 것.

---

## 8. 결론 및 다음 단계

### 8.1 v4.1 판정

| 평가 항목 | 결과 |
|-----------|------|
| Claim 필터 부작용 해소 | **완전 해소** — 4개 모듈 전부 복원 확인 |
| v4 목표 (70%) 달성 | **초과 달성** — 가중 평균 ~87% |
| v5 목표 (75%) 달성 | **초과 달성** — 전 문서 75% 이상 (grounded 제외) |
| v6 목표 (85%) 달성 | **도달** — EDC/NoC/Overlay 85% 이상 |
| KB Grounding 비율 | **~46%** — LLM inference 의존도가 높음 |

### 8.2 주요 성과 요약

1. **Claim 필터 수정의 효과가 예상을 크게 초과**: 4개 모듈 복원이 문서 전체 품질을 연쇄적으로 끌어올림
2. **[TBC] 태그 도입**: KB 기반 사실과 LLM 추론을 자체 구분하는 방법론적 개선
3. **커버리지 급등**: v4 가중 평균 ~34% → v4.1 ~87% (약 +53%p)
4. **파일 규모**: 총 56.6KB (v3) → 85.2KB (v4) → 157.5KB (v4.1), 정보 밀도 증가

### 8.3 남은 과제

| 우선순위 | 과제 | 목적 |
|----------|------|------|
| **P0** | KB Grounding 비율 향상 (46% → 65%+) | LLM inference 의존도 축소 |
| P1 | `[TBC]` 항목 RTL 대조 검증 | 추론 정확도 확인 |
| P2 | analysis_type 필터 도입 (v5 계획) | 검색 정밀도 개선 |
| P3 | 크로스-토픽 통합 (v6 계획) | 서브시스템 간 인터페이스 연결 |

### 8.4 로드맵 재평가 제안

v4.1의 커버리지가 이미 v6 목표(85%)에 도달했으므로, **다음 단계의 초점을 커버리지 확장에서 정밀도(Grounding 비율) 향상으로 전환**하는 것을 권장한다.

| 기존 로드맵 | 제안 수정 |
|------------|-----------|
| v5: 커버리지 75% | v5: **Grounding 비율 65%** + analysis_type 필터 |
| v6: 커버리지 85% | v6: **Grounding 비율 80%** + [TBC] 자동 해소 |

---

*End of Document*
