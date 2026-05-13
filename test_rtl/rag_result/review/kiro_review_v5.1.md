# Kiro Review: v5.1 정답지 비교 + v5 → v5.1 진화 분석

**리뷰어:** Kiro
**리뷰일:** 2026-04-28
**비교 대상:** `v5.1/` 5개 문서 vs `Sample/ORG/N1B0_NPU_HDD_v0.1.md` 정답지
**참고:** `claude_review_v5.1.md`, `codex_review_v5.1.md`

---

## 0. TL;DR

v5.1은 **RAG 튜닝(module_parse 0.3→1.5)의 성공**이다. grounded 커버리지 18%→59%, chip_no_grounding 14섹션 완전 복원, module_parse 데이터(tt_edc_pkg.sv) 복귀. 하지만 정답지 대비로는 **모듈명은 맞고 구조는 틀린** 상태 — `SizeX=4/SizeY=5` 좌표계, tile_t enum, PRTN/ISO_EN이 여전히 부재.

---

## 1. 세 리뷰어 동의 사항

| 항목 | 판정 |
|------|------|
| module_parse 1.5 효과 | ✅ 확실히 동작 |
| chip_no_grounding 완성도 회복 | ✅ 123줄 → 494줄, 14섹션 |
| grounded 커버리지 개선 | ✅ 18% → 59% |
| Grid 좌표계 오류 (Critical) | ❌ `GridSizeX=5, GridSizeY=4` — 정답지는 `SizeX=4, SizeY=5` |
| 비-Tensix 타일 환각 | ❌ ETH/DRAM/PCI/ARC — 정답지는 NOC2AXI/DISPATCH/ROUTER |
| 알고리즘/파라미터 부재 | ❌ DOR pseudo code, ATT 3-stage, FDS CDC 등 KB에 없음 |
| No Grounding hallucination 위험 | ⚠️ 완성도 높지만 검증 불가 내용 다수 |

---

## 2. v5.1 vs 정답지 — 섹션별 비교

| # | 섹션 | 정답지 | v5.1 Grounded | v5.1 No Grounding | 판정 |
|---|------|--------|---------------|-------------------|------|
| 1 | Overview | N1B0 vs Baseline 차이 테이블 | 17개 모듈 리스트 | 일반 AI accelerator 설명 | ⚠️ 골격만 |
| 2 | Package Constants | SizeX=4, SizeY=5, tile_t 8종 | **[NOT IN KB]** | GridSizeX=5, GridSizeY=4 ❌ | ❌ 핵심 실패 |
| 3 | Top-Level Ports | i_ai_clk[3:0], PRTN, ISO_EN[11:0] | **[NOT IN KB]** | generic SoC ports | ❌ |
| 4 | Module Hierarchy | trinity → gen_tensix/dispatch/NOC2AXI | 17개 평면 리스트 | 계층 트리 (이름 정확, 구조 추정) | ⚠️ 부분 |
| 5 | SFPU | tt_sfpu 내부 14 format | lregs + instrn_resources ✅ | 동일 | ✅ 모듈명 일치 |
| 6 | SMN | (정답지에 없음) | clkdiv 5/3, repeater 16/8 ✅ | 동일 | ✅ 추가 정보 |
| 7 | TDMA | Unpack CH0/CH1 상세 | thread_context 한 줄 | 동일 | ❌ 얕음 |
| 8 | NoC | DOR/Tendril/Dynamic + 928-bit | 3개 모듈만 | 10개 모듈 + ECC | ⚠️ 모듈 풍부, 알고리즘 부재 |
| 9 | EDC | node_id, U-shape, harvest | 2개 모듈 | modport 4개 + 5 IRQ | ⚠️ BIU 정확 |
| 10 | Overlay | (정답지 기준 없음) | FDS 106/41, 68/41, CSR 38/97 | 동일 | ✅ 보강 |
| 11 | Clock | 4도메인 + clock_routing_t | 셀 이름만 | 4도메인 (axi_clk 누락) | ❌ |
| 12 | Reset | reset tree + harvest | **[NOT IN KB]** | generic chain | ❌ |
| 13 | SRAM | 12×16×3072×128 전체 | 1개 SRAM만 | 동일 + 추정 | ❌ 얕음 |
| 14 | DFX | 4개 모듈 + IJTAG | selftest 1개 | iJTAG 설명 | ❌ 얕음 |
| 15 | Power Mgmt | PRTN, ISO_EN[11:0] | — | — | ❌ 완전 누락 |

---

## 3. 정답지 대비 점수

### 3.1 자체 지표 (항목 존재 여부)

| 문서 | 점수 |
|------|------|
| Grounded | ~30% |
| No Grounding | ~20% |
| EDC | ~25% |
| NoC | ~30% |
| Overlay | ~20% |

### 3.2 가중 지표 (정답지 핵심 항목 기준)

| 정답지 핵심 항목 | 가중치 | v5.1 Grounded |
|-----------------|--------|---------------|
| Package Constants | 20% | ❌ 0% |
| Top-Level Ports | 15% | ❌ 0% |
| Module Hierarchy (정확한 구조) | 15% | ⚠️ 5% |
| NoC Routing/ATT | 15% | ❌ 0% |
| EDC Topology/Protocol | 10% | ⚠️ 3% |
| Clock/Reset/Power | 10% | ⚠️ 2% |
| SRAM/DFX/RTL Files | 15% | ⚠️ 3% |
| **가중 합계** | 100% | **~13%** |

자체 59%와 가중 13%의 괴리 = "쉬운 항목(모듈명)은 맞추고, 어려운 항목(파라미터/알고리즘)은 전멸"

---

## 4. v5 → v5.1 개선 효과

| 지표 | v5 | v5.1 | 변화 |
|------|-----|------|------|
| Grounded 커버리지 | 18% | **59%** | +41pp |
| chip_no_grounding | 123줄 | **494줄** | 4× |
| 검색 결과 다양성 | 3건 | **20건** | 6.7× |
| 확인된 모듈 수 | 3 | **17** | 5.7× |
| 토픽별 문서 | 변화 없음 | 변화 없음 | 토픽 필터 한정 |

**핵심:** module_parse boost 효과는 **chip-level 쿼리에서만** 나타남.

---

## 5. Kiro 고유 관찰

### 5.1 Grid 오류의 근본 원인

KB에 `trinity_pkg.sv`의 `SizeX=4, SizeY=5`가 **인덱싱되어 있지 않다**. module_parse는 모듈 선언부(port list)만 파싱하고, package 내부 `localparam`/`typedef enum`은 추출하지 않는다. LLM이 "4×5"를 일반적 "행×열"로 해석하여 뒤집는 것.

**해결:** package-level parser 추가 (localparam, typedef enum, struct → claim 추출)

### 5.2 가중 커버리지 13% 재평가

Claude/Codex는 자체 지표(59%)를 인용했지만, 정답지 핵심 가중치 기준으로는 **~13%**. "쉬운 항목을 많이 맞춘 것"과 "핵심을 맞춘 것"은 다르다.

### 5.3 subsystem 문서가 v5보다 짧아진 이유

내가(Kiro) "검색 결과에 없는 내용은 절대 추가하지 마" 규칙을 더 엄격하게 따랐기 때문. 정직하지만 문서 가치가 떨어지는 트레이드오프. Hybrid 그라운딩으로 해결 가능.

### 5.4 Codex의 "v4 좌표계가 더 정확했다" 관찰에 동의

v4는 `SizeX=4, SizeY=5` 방향을 비교적 잘 잡았다. v5에서 module_parse가 약해지면서 package 정보가 사라졌고, LLM이 일반 SoC 지식으로 채우면서 Grid가 오염됐다. v5.1에서 module_parse를 복원했지만 **package 상수 자체가 module_parse에 포함되지 않으므로** Grid 오류는 해결되지 않았다.

---

## 6. 개선 권장사항

### P0 (즉시)

| # | 항목 | 효과 |
|---|------|------|
| 1 | **Package parser** — localparam/enum/struct → claim | Grid 오류 근본 해결 |
| 2 | **Hybrid 그라운딩** — `[FROM LLM]` 태그 | subsystem 두께 + 투명성 |
| 3 | **max_results 30** (chip-level) | 토픽 커버리지 확대 |

### P1 (중기)

| # | 항목 | 효과 |
|---|------|------|
| 4 | **KB chunking 확장** — pseudo code, typedef 블록 | 가중 커버리지 13% → 40%+ |
| 5 | **No Grounding `[INFERRED]` 태그** | hallucination 식별 |
| 6 | **정답지 기반 자동 채점기** | regression 방지 |

### P2 (장기)

| # | 항목 |
|---|------|
| 7 | Spec RAG + RTL RAG 듀얼 검색 |
| 8 | Sample HDD를 KB에 등록 (human-validated) |

---

## 7. 최종 판정

v5.1은 **RAG 튜닝 루프가 실제로 동작한다는 증거**다. module_parse 0.3→1.5 한 줄 변경으로 chip-level 커버리지가 3.3× 개선됐다. 하지만 정답지 재현에는 **package parser + KB chunking 확장**이라는 구조적 변경이 필요하다. 현재 RAG는 "모듈 이름"은 잘 찾지만 "모듈이 뭘 하는지"는 아직 부족하다.

---

*End of Review — Kiro Review v5.1*