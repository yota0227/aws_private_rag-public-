# RAG v3 vs v2.5 품질 비교 분석 — Claim 필터링 부작용 진단

**문서 ID:** REVIEW-RAG-V3-QUALITY-001  
**버전:** v1.1  
**작성일:** 2026-04-24  
**이전 버전:** claude_review_v1.0 (통합 근본 원인 분석 및 개선 로드맵)  
**분석 대상:** `test_rtl/rag_result/v3/` (RAG v2.5) vs `test_rtl/rag_result/v4/` (RAG v3)

---

## 목차

1. [분석 배경](#1-분석-배경)
2. [파일 구성](#2-파일-구성)
3. [문서별 비교 분석](#3-문서별-비교-분석)
4. [종합 커버리지 판정](#4-종합-커버리지-판정)
5. [근본 원인 — Claim 필터링 부작용](#5-근본-원인--claim-필터링-부작용)
6. [권장 수정안](#6-권장-수정안)
7. [결론](#7-결론)

---

## 1. 분석 배경

### 1.1 버전 로드맵과 목표

| RAG 버전 | 저장 위치 | 주요 변경 사항 | 커버리지 목표 |
|----------|----------|----------------|--------------|
| v2.5 | `v3/` | chip_config + edc_topology + noc_protocol + overlay_deep + sram_inventory | 55% |
| **v3** | **`v4/`** | **포트 비트폭 추출, 토픽 확장, Claim 귀속 수정(레지스터 래퍼 필터링 + 다양성 검증), max_results 20** | **70%** |
| v5 (계획) | — | 검색 정밀도 개선 (analysis_type 필터, chip_variant) | 75% |

### 1.2 비교 기준

`prompt.md`에 정의된 5개 표준 프롬프트를 동일하게 실행하여 버전 간 품질 변화를 추적한다.

- **v{N}a vs v{N-1}a** → RAG 데이터 개선 효과 (같은 프롬프트, 다른 RAG)
- **v{N}b vs v{N}a** → 프롬프트 개선 효과 (같은 RAG, 다른 프롬프트)
- **v{N} 토픽별 vs v{N-1} 토픽별** → 심화 분석 반영 효과

---

## 2. 파일 구성

### v3 (RAG v2.5, 2026-04-22)

| 파일 | 목적 | 비고 |
|------|------|------|
| `v3a_chip_no_grounding_r2.md` | 칩 전체 HDD, Grounding 없음 | R2가 최종본 |
| `v3b_chip_grounded_r2.md` | 칩 전체 HDD, Grounding 있음 | R2가 최종본 |
| `v3_edc_r2.md` | EDC 서브시스템 | R2가 최종본 |
| `v3_noc_r2.md` | NoC 라우팅/패킷 | R2가 최종본 |
| `v3_overlay_r2.md` | Overlay RISC-V 서브시스템 | R2가 최종본 |

### v4 (RAG v3, 2026-04-24)

| 파일 | 목적 |
|------|------|
| `v4a_chip_no_grounding.md` | 칩 전체 HDD, Grounding 없음 |
| `v4b_chip_grounded.md` | 칩 전체 HDD, Grounding 있음 |
| `v4_edc.md` | EDC 서브시스템 |
| `v4_noc.md` | NoC 라우팅/패킷 |
| `v4_overlay.md` | Overlay RISC-V 서브시스템 |

---

## 3. 문서별 비교 분석

### 3.1 칩 전체 HDD (no grounding) — v4 대폭 개선

| 항목 | v3a_r2 | v4a | 변화 |
|------|--------|-----|------|
| 탑 모듈 확인 | `trinity_noc2axi_router_ne_opt_FBLC` 1개만 | `trinity.sv` + 7개 인스턴스 | **대폭 개선** |
| 포트 정보 | EDC pkg modport 신호만 (req_tgl, ack_tgl) | Top-level I/O 포트 2개 Variant (ai_clk, noc_clk, dm_clk, axi_clk, 리셋 전부) | **대폭 개선** |
| 모듈 계층 | `noc2axi_router` 1개 (leaf, "no sub-modules") | edc_direct_conn, edc_loopback, tt_tensix_with_l1, dispatch_east/west, noc_arbiter_tree, noc_repeaters_cardinal | **대폭 개선** |
| 클럭 아키텍처 | 전부 NOT IN KB | 4개 도메인 (ai/noc/dm/axi) + 폭 정보 | **신규 확보** |
| 리셋 아키텍처 | 전부 NOT IN KB | 4개 리셋 신호 + per-tile 리셋 구조 | **신규 확보** |
| RTL 파일 | tt_edc_pkg.sv 5개 경로만 | trinity.sv 4개 Variant (base/N1/mem_port/legacy) | **신규 확보** |
| **추정 커버리지** | **~35%** | **~55%** | **+20%p** |

> v4의 가장 큰 성과. `trinity.sv` 파싱이 추가되면서 포트, 인스턴스, 클럭/리셋 정보가 일괄 확보됨.

### 3.2 칩 전체 HDD (grounded) — v4 토픽 다양화

| 항목 | v3b_r2 | v4b | 변화 |
|------|--------|-----|------|
| HDD 섹션 구성 | 5개 (Overlay/DFX×2/EDC/Dispatch) | 5개 (SFPU/Clock_Reset/SMN/NoC/FPU) | **토픽 다양화** |
| 실질 내용 | 모두 `noc2axi_router` 1개 모듈 설명 반복 | 각 토픽별 별도 개요 (짧지만 구분됨) | **약간 개선** |
| **추정 커버리지** | **~25%** | **~40%** | **+15%p** |

### 3.3 EDC 서브시스템 — v4 퇴보

| 항목 | v3_edc_r2 | v4_edc | 변화 |
|------|-----------|--------|------|
| BIU 모듈 | `tt_edc1_biu_soc_apb4_wrap` claim 확보 (APB4 bridge, CSR, IRQ) | NOT IN KB | **퇴보** |
| Serial Bus 신호 | req_tgl, ack_tgl, cor_err, err_inj_vec 확인 | NOT IN KB (표준 스펙 기반 추정만) | **퇴보** |
| Modport 구조 | ingress/egress/edc_node/sram 4개 modport 확인 | 없음 | **퇴보** |
| Top-level 인스턴스 | 없음 | edc_direct_conn_nodes, edc_loopback_conn_nodes 확인 | **개선** |
| Ring Topology | NOT IN KB | U-shape 추론 (direct/loopback 명명 기반) | **약간 개선** |
| **추정 커버리지** | **~38%** | **~27%** | **-11%p** |

> v3에서 유일하게 "Fully Grounded"였던 BIU 섹션이 v4에서 완전히 소실됨.

### 3.4 NoC 라우팅/패킷 — v4 부분적 개선

| 항목 | v3_noc_r2 | v4_noc | 변화 |
|------|-----------|--------|------|
| 모듈 다양성 | `noc2axi_router` 1개 (leaf) | noc_arbiter_tree + tt_noc_repeaters_cardinal + noc2axi_router + noc_routing_translation_selftest + tt_mem_wrap | **대폭 개선** |
| Claim 데이터 | 0건 | 4건 (arbiter tree 구조, repeater 기능/연결) | **신규 확보** |
| Arbitration | NOT IN KB | tree-based, configurable width/data width 확인 | **신규 확보** |
| Routing 알고리즘 | NOT IN KB | NOT IN KB | 변화 없음 |
| Flit/VC/Security | NOT IN KB | NOT IN KB | 변화 없음 |
| **추정 커버리지** | **~35%** | **~35%** | **비슷** (구성 변화) |

> NoC 토픽에서는 원래 `_reg_inner`/`_wrap` 패턴 모듈이 없었기 때문에 필터 부작용 없음. module_parse 확대로 모듈 다양성은 개선되었으나 프로토콜 세부(routing/flit/VC)는 여전히 미확보.

### 3.5 Overlay (RISC-V) — v4 심각한 퇴보

| 항목 | v3_overlay_r2 | v4_overlay | 변화 |
|------|--------------|------------|------|
| Claim 데이터 | 3건 (cluster_ctrl, fds_dispatch, fds_tensixneo) | **0건** | **심각 퇴보** |
| 실제 모듈 발견 | tt_cluster_ctrl_reg_inner, tt_fds_dispatch_reg_inner, tt_fds_tensixneo_reg_inner | 없음 | **퇴보** |
| CPU I/F 신호 | request, address, write_data, response 확인 | NOT IN KB | **퇴보** |
| FDS 정보 | 2개 레지스터 서브도메인 (dispatch/tensixneo) 확인 | NOT IN KB | **퇴보** |
| **추정 커버리지** | **~42%** | **~0%** | **-42%p** |

> v4에서 가장 심각한 퇴보. `topic="Overlay"` 검색이 0건 반환. v3에서 확보된 3개 claim 모듈이 전부 `_reg_inner` 패턴에 의해 필터링됨.

---

## 4. 종합 커버리지 판정

| 문서 | v3 (v2.5) | v4 (v3) | 목표 | 판정 |
|------|-----------|---------|------|------|
| Chip (no grounding) | ~35% | ~55% | 55% | **목표 달성** |
| Chip (grounded) | ~25% | ~40% | — | 개선 |
| EDC | ~38% | ~27% | 70% | **목표 미달 + 퇴보** |
| NoC | ~35% | ~35% | 70% | **목표 미달** |
| Overlay | ~42% | ~0% | 70% | **심각 퇴보** |

### v4의 이중적 성격

- **칩 레벨 (module_parse)**: `trinity.sv` 파싱 추가로 포트, 인스턴스, 클럭/리셋 대폭 확보 → 성공
- **토픽 레벨 (claim)**: 레지스터 래퍼 필터링이 유효 claim까지 제거 → 실패

---

## 5. 근본 원인 — Claim 필터링 부작용

### 5.1 문제의 코드

**파일:** `rtl_parser_src/claim_generator.py` (lines 34-53)

```python
REGISTER_WRAPPER_PATTERNS = ["_reg_inner", "_wrap", "_reg_top"]

def _filter_claim_targets(modules, topic):
    datapath = []
    register = []
    for m in modules:
        name = m.get("module_name", "").lower()
        if any(pat in name for pat in REGISTER_WRAPPER_PATTERNS):
            register.append(m)
        else:
            datapath.append(m)
    if len(datapath) < 3:
        datapath.extend(register)
    return datapath
```

### 5.2 필터에 걸린 모듈 목록

| v3에서 확보된 모듈 | 매칭 패턴 | 역할 | v4 결과 |
|---|---|---|---|
| `tt_cluster_ctrl_reg_inner` | `_reg_inner` | 클러스터 제어 레지스터 — Overlay 핵심 | **필터됨** |
| `tt_fds_dispatch_reg_inner` | `_reg_inner` | FDS 디스패치 레지스터 — CPU I/F 확인 | **필터됨** |
| `tt_fds_tensixneo_reg_inner` | `_reg_inner` | FDS Tensix/Neo 레지스터 — CPU I/F 확인 | **필터됨** |
| `tt_edc1_biu_soc_apb4_wrap` | `_wrap` | APB4-BIU CSR 브릿지 — EDC 유일한 fully grounded 모듈 | **필터됨** |

### 5.3 인과 관계

```
v4 파서 확장 (trinity.sv 등 대량 모듈 추가)
    │
    ▼
datapath 모듈 수 대폭 증가 (3개 이상 충분)
    │
    ▼
fallback 조건 (len(datapath) < 3) 미발동
    │
    ▼
_reg_inner / _wrap 매칭 모듈 전부 제외
    │
    ▼
해당 모듈에 대한 claim 미생성 → 인덱스 미저장 → 검색 불가
    │
    ├─▶ EDC: tt_edc1_biu_soc_apb4_wrap claim 소실 → BIU 섹션 전체 NOT IN KB
    └─▶ Overlay: 3개 모듈 claim 전부 소실 → topic="Overlay" 검색 0건
```

### 5.4 아이러니

v4의 파서 확장은 그 자체로는 올바른 개선이었다. 하지만 **더 많은 datapath 모듈이 추가된 결과, fallback 안전장치가 무력화**되면서 레지스터 래퍼 필터링의 부작용이 표면화되었다. 파서 확장과 필터링 로직이 **서로 독립적으로 설계**되어 이런 상호작용이 예측되지 않았다.

### 5.5 다양성 검증(`_validate_claim_diversity`)의 한계

```python
def _validate_claim_diversity(claims, topic):
    # 단일 모듈이 80% 이상 차지하면 False 반환 (경고만)
    ...
```

이 함수는 **경고 로그만 남기고 실제 동작을 변경하지 않는다**. 필터링으로 제거된 모듈은 claim 생성 자체가 안 되므로, 다양성 검증 단계에 도달하지도 못한다.

---

## 6. 권장 수정안

### 옵션 A — 패턴 축소 (최소 변경, 추천)

`_wrap` 패턴을 제거하거나 더 구체적으로 제한. `tt_edc1_biu_soc_apb4_wrap`은 APB4-BIU 브릿지이지 단순 레지스터 래퍼가 아님.

```python
# Before
REGISTER_WRAPPER_PATTERNS = ["_reg_inner", "_wrap", "_reg_top"]

# After — 더 구체적인 패턴으로 제한
REGISTER_WRAPPER_PATTERNS = ["_reg_top"]
# 또는 제거 대상을 명시적으로 지정
REGISTER_WRAPPER_EXCLUDES = ["_autogen_reg_inner", "_csr_reg_top"]
```

### 옵션 B — fallback 임계값 상향

```python
# Before
if len(datapath) < 3:
    datapath.extend(register)

# After — 비율 기반 fallback
if len(register) > 0:
    max_register = max(3, len(datapath) // 3)  # datapath의 1/3까지 register 포함
    datapath.extend(register[:max_register])
```

### 옵션 C — 화이트리스트 (가장 안전)

기능 블록으로 확인된 모듈은 이름 패턴과 무관하게 보존.

```python
FUNCTIONAL_BLOCK_PREFIXES = ["tt_edc1_biu", "tt_cluster_ctrl", "tt_fds_"]

def _filter_claim_targets(modules, topic):
    datapath = []
    register = []
    for m in modules:
        name = m.get("module_name", "").lower()
        is_functional = any(name.startswith(p) for p in FUNCTIONAL_BLOCK_PREFIXES)
        is_register = any(pat in name for pat in REGISTER_WRAPPER_PATTERNS)
        if is_register and not is_functional:
            register.append(m)
        else:
            datapath.append(m)
    if len(datapath) < 3:
        datapath.extend(register)
    return datapath
```

### 옵션 비교

| 옵션 | 구현 난이도 | 부작용 위험 | v3 claim 복원 | 확장성 |
|------|-----------|-----------|---------------|--------|
| A. 패턴 축소 | 낮음 | 중간 (불필요 래퍼 재유입 가능) | 부분적 | 낮음 |
| B. 임계값 상향 | 낮음 | 낮음 | 높음 | 중간 |
| C. 화이트리스트 | 중간 | 낮음 | 높음 | 높음 (명시적) |

**권장: 옵션 B + C 병합** — 비율 기반 fallback을 기본으로 하되, 확인된 기능 블록은 화이트리스트로 보호.

---

## 7. 결론

### v4 (RAG v3)의 이중적 평가

| 영역 | 평가 |
|------|------|
| RTL 파서 확장 | **성공** — `trinity.sv` 파싱으로 칩 레벨 커버리지 35% → 55% |
| 포트 비트폭 추출 | **성공** — 클럭/리셋 도메인 정보 신규 확보 |
| max_results 20 확대 | **성공** — 검색 반환 다양성 증가 |
| Claim 귀속 수정 (레지스터 래퍼 필터링) | **실패** — 유효 모듈 4개 제거, EDC/Overlay 커버리지 퇴보 |

### 70% 달성을 위한 최단 경로

1. **Claim 필터링 수정** (옵션 B+C) → v3에서 확보된 claim 복원
2. **재인덱싱** → 수정된 필터로 claim 재생성
3. **검증** → 동일 5개 프롬프트로 v4.1 산출물 생성, v3 claim 데이터 복원 확인

v4의 module_parse 개선(칩 레벨 ~55%)과 v3의 claim 다양성(EDC ~38%, Overlay ~42%)을 합치면, **추가 파서 확장 없이도 60-65% 커버리지**에 도달할 수 있다. 여기에 v5의 검색 정밀도 개선(analysis_type 필터, chip_variant)을 더하면 75% 목표 달성이 현실적이다.

---

*End of Document*
