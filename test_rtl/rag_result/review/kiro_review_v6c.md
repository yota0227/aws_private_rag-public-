# v6c 정답지 비교 리뷰

**리뷰어:** Kiro | **리뷰일:** 2026-04-28
**비교:** `v6c_chip_integrated.md` (365줄, 13KB) vs `N1B0_NPU_HDD_v0.1.md` (1,291줄, 57KB)

---

## 정량 비교

| 문서 | 줄 | KB | 정답지 대비 |
|------|-----|-----|------------|
| v6 (1회 검색) | 202 | 7 | 16% |
| v6a (5회, 구 parser) | 469 | 20 | 36% |
| **v6c (5회, 신 parser)** | **365** | **13** | **28%** |
| 정답지 | 1,291 | 57 | 100% |

---

## 섹션별 비교

| # | 섹션 | 정답지 | v6c | 일치도 |
|---|------|--------|-----|--------|
| 1 | Overview | N1B0 vs Baseline 차이 테이블 10행 | 타일 구성 + 특성 테이블 | ⚠️ 50% |
| 2 | **Package Constants** | 10개 상수 + tile_t + EP 20행 + Helper 6개 | **13개 상수 ✅ + tile_t ✅ + EP 20행 ✅** | **✅ 90%** |
| 3 | Top-Level Ports | 7개 서브섹션 | Clock/Reset + EDC IRQ | ⚠️ 35% |
| 4 | Module Hierarchy | 3-level generate + deep hierarchy | 2-level + EP | ⚠️ 40% |
| 5 | Compute Tile | 7개 서브섹션 (FPU/SFPU/TDMA/L1/DEST/SRCB) | SFPU + TDMA 이름만 | ❌ 15% |
| 6 | Dispatch | 내부 3-level + FDS 기능 | 이름 + EP | ❌ 15% |
| 7 | NoC | 알고리즘 + flit + gasket + repeater 테이블 | 9개 모듈 리스트 | ⚠️ 25% |
| 8 | NIU | Corner vs Composite + 내부 + parameters | 타일 테이블 + ATT | ⚠️ 30% |
| 9 | **Clock** | clock_routing_t + per-column | **8필드 ✅** + 모듈 | **✅ 70%** |
| 10 | Reset | dm_core/uncore 상세 | 기본 4개 | ⚠️ 30% |
| 11 | **EDC** | 간략 | **modport 4개 + BIU + 5 IRQ ✅** | **✅ 80%** |
| 12 | Power Mgmt | PRTN + ISO_EN | 없음 | ❌ 0% |
| 13 | SRAM | L1+VC+ATT 전체 | ATT 1개 | ❌ 10% |
| 14 | DFX | 4개 모듈 + iJTAG | 3개 모듈 | ⚠️ 40% |
| 15-17 | Physical/SW/RTL | P&R + SW + 파일 | 파일 10개 | ⚠️ 30% |

---

## 가중 점수 (v5.1 → v6c 비교)

| 핵심 항목 | 가중치 | v5.1 | v6c | 변화 |
|----------|--------|------|-----|------|
| Package Constants | 20% | 0% | **18%** | +18pp |
| Top-Level Ports | 15% | 0% | 5% | +5pp |
| Module Hierarchy | 15% | 5% | 6% | +1pp |
| NoC | 15% | 0% | 4% | +4pp |
| EDC | 10% | 3% | **8%** | +5pp |
| Clock/Reset/Power | 10% | 2% | **7%** | +5pp |
| Compute Tile | 10% | 2% | 2% | — |
| SRAM/DFX/RTL | 5% | 3% | 2% | -1pp |
| **합계** | **100%** | **~13%** | **~45%** | **+32pp** |

---

## 핵심 개선 (v5.1 → v6c)

| 항목 | v5.1 | v6c |
|------|------|-----|
| SizeX/SizeY | ❌ 뒤집힘 (5×4) | ✅ 4×5 정확 |
| 13개 localparam | 0개 | **13개 전부** |
| EP 테이블 | 없음 | **20행 전체** |
| Grid 다이어그램 | ETH/DRAM 환각 | **정답지와 동일** |

---

## 여전한 Gap

| 항목 | 해결 방법 |
|------|----------|
| dm_clk, APB, AXI, PRTN, ISO_EN | trinity.sv 포트 truncation 해결 |
| FPU G-Tile/M-Tile, TDMA 4채널, L1 크기 | Spec RAG 필수 |
| NoC 알고리즘, flit 구조 | KB chunking 확장 |
| N1B0 vs Baseline 차이 테이블 | Hybrid 그라운딩 |

---

## 결론

v6c는 **Package Constants에서 정답지 90% 일치** 달성. 가중 점수 **13% → 45% (+32pp)**. Package parser 정규식 한 줄 수정이 이 차이를 만들었다.

남은 55%: trinity.sv 포트 전체 파싱(15%) + Spec RAG/KB chunking(40%).

---

*End of Review*