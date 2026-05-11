# RAG v4 (v5/) vs RAG v3.1 (v4.1/) 비교 리뷰

**리뷰어:** Claude Code
**리뷰일:** 2026-04-27
**비교 대상:** RAG v4 (`v5/`) vs RAG v3.1 (`v4.1/`)

---

## RAG v4 변경사항 (prompt.md 기준)

| 변경 | 설명 |
|------|------|
| analysis_type 패스스루 | API Gateway → RTL Lambda로 analysis_type 파라미터가 전달됨 |
| Boost 가중치 | claim 3.0, hdd_section 2.0, module_parse 0.3 |
| 응답 포맷 분기 | analysis_type별로 응답 형식이 달라짐 |

---

## 1. Chip 전체 HDD — No Grounding

| 항목 | v4.1a | v5 | 판정 |
|------|-------|-----|------|
| 문서 길이 | ~525줄 (14섹션 + 부록) | ~123줄 (4섹션만) | v4.1 우위 |
| 언어 | 한국어/영어 혼용 | 영어 전용 | 변경 (프롬프트 차이?) |
| Grid 레이아웃 | TSIX/NIU/ARC/DRAM 4타입 | ETH/ROUTER/TENSIX/DRAM/PCI/ARC 6타입 | v5 우위 — 더 세분화 |
| Module Hierarchy | 일반적 이름 (`fpu_top`, `tdma_engine`, `l1_cache`) | 실제 RTL 모듈명 (`tt_sfpu_lregs`, `tt_noc_secded_chk_corr_116_10`, `tt_niu_mst_timeout`) | **v5 우위** |
| NIU 상세 | AXI Bridge, ATT, SMN 개념 설명 | `tt_noc2axi_local_reg [x3]`, `tt_niu_mst_timeout [x5]` 구체 모듈 | **v5 우위** |
| NoC 모듈 | `noc_mesh_2d`, `noc_clk_domain` (추정) | `tt_noc_secded_chk_corr_116_10`, `tt_upf_async_fifo`, `tt_noc_sync3_pulse` (실제) | **v5 우위** |
| Clock 모듈 | `pll_ai`, `pll_noc`, `clk_div` (추정) | `tt_pll`, `tt_clkdiv2`, `tt_clkbuf`, `tt_clkgater` (실제) | **v5 우위** |
| 섹션 완전성 | 14섹션 (Compute, Dispatch, NoC, NIU, Clock, Reset, EDC, SRAM, DFX 등) | 4섹션 (Overview, Grid, Ports, Hierarchy)에서 끝남 | **v4.1 우위** — v5는 미완성 |
| Dispatch 상세 | East/West 구조, 명령 분배 다이어그램 | 없음 (hierarchy에 이름만) | v4.1 우위 |
| EDC 상세 | 링 토폴로지, 시리얼 버스, 하베스트 | 없음 (hierarchy에 이름만) | v4.1 우위 |
| [TBC] 마커 | 9개 Open Items 추적 | 없음 | v4.1 체계적 |

**요약:** v5의 Module Hierarchy가 실제 RTL 모듈명을 담고 있어 **기술적 정확성은 향상**되었으나, 문서가 4섹션에서 끊겨 **완전성은 대폭 하락**. Claim boost(3.0)가 실제 모듈명을 끌어올리는 효과는 확인됨.

---

## 2. Chip 전체 HDD — Grounded

| 항목 | v4.1b | v5 | 판정 |
|------|-------|-----|------|
| 검색 결과 수 | 3 HDD + claims + module_parse (복합) | 3 HDD only (hdd_section 필터) | **v4.1 우위** |
| 검색 결과 토픽 | FPU, SFPU, SMN + EDC(module_parse) + NoC(claims) + Overlay(module_parse) | FPU, SFPU, SMN만 | **v4.1 우위** |
| 커버리지 | 46% (12/26 섹션 grounded) | ~18% (3/17 섹션 grounded) | **v4.1 우위** |
| EDC 정보 | tt_edc_pkg.sv modport 4개 + 시그널 전체 확인 | 없음 | v4.1 우위 |
| Overlay 정보 | TTTrinityConfig CDC 모듈 확인 | 없음 | v4.1 우위 |
| NoC 정보 | noc_repeaters_cardinal + noc_arbiter_tree claims | 없음 | v4.1 우위 |
| SRAM 정보 | tt_mem_wrap_32x1024_2p_nomask (1건) | 동일 (1건) | 동등 |
| KB Coverage Matrix | 있음 (26항목 추적) | 없음 | v4.1 우위 |
| Recommended Searches | 있음 (8개 우선순위별) | 없음 | v4.1 우위 |

**요약:** **명확한 퇴보.** v5 grounded가 `analysis_type=hdd_section`으로 필터하면서 claim과 module_parse 데이터를 모두 놓침. v4.1b는 필터 없이 전체 타입을 가져와서 더 넓은 커버리지 확보.

**원인 추정:** 프롬프트 9번(통합 HDD)이 `query="HDD"`로 검색 → analysis_type 패스스루가 자동으로 `hdd_section`을 필터로 적용 → claim/module_parse 누락.

---

## 3. EDC 서브시스템

| 항목 | v4.1 | v5 | 판정 |
|------|------|-----|------|
| 문서 길이 | ~524줄 (11섹션 + 2부록) | ~262줄 (11섹션 + 부록) | v4.1 우위 |
| 그라운딩 | "RTL-grounded" (도메인 지식 포함) | 엄격 KB-only + [NOT IN KB] | 방법론 차이 |
| 검색 결과 | (v3.1 RAG 데이터) | 8건 claims | — |
| Toggle-handshake 프로토콜 | 완전 (req_tgl/ack_tgl/data/data_p/async_init 시그널 테이블, 시퀀스 다이어그램) | **[NOT IN KB]** | v4.1 우위 |
| Packet Format | 완전 (fragment 구조, opcode 7종, MAX_FRGS) | **[NOT IN KB]** | v4.1 우위 |
| Node ID Structure | 완전 (12-bit 계층, 디코딩 테이블, SystemVerilog 매치 로직) | **[NOT IN KB]** | v4.1 우위 |
| Module Hierarchy | 완전 (ring_head, node, bypass_mux, cdc_sync 등 풀 트리) | 부분 (biu_apb4_wrap, noc_sec_block_reg, serial_bus_repeater, intf_connector) | v4.1 우위 |
| Ring Topology | U-shape 다이어그램 (Segment A/B, 40 hop) | **[NOT IN KB]** — 모듈명 기반 추론만 | v4.1 우위 |
| Harvest Bypass | 완전 (mux/demux 다이어그램, edc_mux_demux_sel, ARC 프로그래밍) | **[NOT IN KB]** | v4.1 우위 |
| BIU Register Map | 8개 레지스터 (EDC_CMD~EDC_INJ_CTRL), 오프셋/접근타입 완전 | APB4 포트 리스트만 (s_apb_psel 등) + 5개 인터럽트 | v4.1 우위 |
| CDC | 3개 boundary 상세 (Ring Head↔BIU, Node↔SRAM, Node↔Regs) | **[NOT IN KB]** | v4.1 우위 |
| SystemVerilog 코드 | tt_edc_if interface 전체 코드 | 없음 | v4.1 우위 |
| v5에만 있는 것 | — | BIU inner module 분리 (edc1_biu_soc_apb4_inner), noc_sec_block_reg inner, 5개 인터럽트 시그널 (fatal_err_irq, crit_err_irq, cor_err_irq, pkt_sent_irq, pkt_rcvd_irq) | **v5 우위** |

**요약:** v4.1이 압도적으로 풍부하나, **LLM 도메인 지식이 대부분**. v5는 KB 데이터만 사용하여 [NOT IN KB]가 대량 발생. 단, v5에서 새로 확인된 사실(5개 인터럽트 시그널, inner module 구조)은 v4.1에 없던 실제 RTL 정보.

**핵심 문제:** module_parse 가중치 0.3으로 인해 `tt_edc_pkg.sv` 인터페이스 정의(v4.1b에서 확인됨)가 v5 EDC 검색에서 누락. Claims만으로는 프로토콜 상세를 복원할 수 없음.

---

## 4. NoC 서브시스템

| 항목 | v4.1 | v5 | 판정 |
|------|------|-----|------|
| 문서 길이 | ~718줄 (10섹션 + 2부록) | ~234줄 (10섹션 + 부록) | v4.1 우위 |
| 그라운딩 | "RTL-grounded" (도메인 지식 포함) | 엄격 KB-only + [NOT IN KB] | 방법론 차이 |
| 검색 결과 | (v3.1 RAG 데이터) | 14건 (claims + 1 HDD) | v5 결과 수 더 많음 |
| Routing Algorithms | 3종 완전 비교 (DOR/TENDRIL/DYNAMIC, 의사코드, 데드락 회피) | **[NOT IN KB]** | v4.1 우위 |
| Flit Structure | 512-bit 비트레벨 필드 매핑 (x_dest, y_dest, endpoint_id 등 14개 필드) | **[NOT IN KB]** — SECDED 116+10만 확인 | v4.1 우위 |
| AXI Address Gasket | 56-bit 구조 (target_idx/endpoint_id/tlb_index/address), ATT flow | 부분 — SRAM 32x1024만 확인 | v4.1 우위 |
| Virtual Channel | 4 VC 구조, credit flow 다이어그램, VC별 용도/우선순위 | **[NOT IN KB]** — arbiter_tree만 확인 | v4.1 우위 |
| Security Fence | SMN group access control, 의사-RTL, 위반 핸들링 | **[NOT IN KB]** | v4.1 우위 |
| Router Hierarchy | 5-level 풀 트리 (input_port → vc_buffer → route_compute → crossbar → arbiter → output_port → sec_fence) | 부분 (repeaters, arbiter_tree, skid_buffer, SECDED, async_fifo 등 개별 모듈) | v4.1 우위 (구조), v5 우위 (실제 모듈명) |
| Endpoint Map | 4×5 grid 전체 (20 타일 × 6 endpoint, 120+ 매핑) | **[NOT IN KB]** | v4.1 우위 |
| Key Parameters | 40+ 파라미터 (FLIT_WIDTH=512, NUM_VCS=4, VC_DEPTH=4 등) | 4개만 (DATA_WIDTH=116, ECC_WIDTH=10, TABLE_DEPTH=1024, TABLE_WIDTH=32) | v4.1 우위 |
| v5에만 있는 것 | — | `tt_noc_sync3_pulse` (3-stage pulse sync), `tt_harvest_robust_sync` (multi-replication), `tt_noc_async_fifo_wr_side_reset` (FIFO reset gen) — 실제 RTL 모듈 | **v5 우위** |

**요약:** v4.1이 아키텍처 이해도에서 압도적이나 대부분 LLM 생성. v5는 14건의 claim으로 실제 모듈명은 더 많이 확보했지만, 이를 아키텍처로 조립하지 못함. 3개 신규 모듈(sync3_pulse, harvest_robust_sync, async_fifo_wr_side_reset)은 v5에서 처음 확인.

---

## 5. Overlay (RISC-V) 서브시스템

| 항목 | v4.1 | v5 | 판정 |
|------|------|-----|------|
| 문서 길이 | ~847줄 (12섹션 + 부록) | ~273줄 (12섹션 + 부록) | v4.1 우위 |
| 그라운딩 | "RTL-grounded" (도메인 지식 포함) | 엄격 KB-only + [NOT IN KB] | 방법론 차이 |
| 검색 결과 | (v3.1 RAG 데이터) | 7건 (claims + 1 HDD) | — |
| CPU Cluster | 8× RV64GC, 5-stage pipeline, Chipyard/Rocket, FPU, PTW 상세 | **[NOT IN KB]** | v4.1 우위 |
| L1 Cache | I$ 32KB/4-way, D$ 64KB/8-way, SRAM 1MB/32bank | **[NOT IN KB]** — CSR 레지스터(38in/97out)만 | v4.1 우위 |
| iDMA | 4채널, 1D/2D/scatter-gather, 디스크립터 포맷, flow 다이어그램 | **[NOT IN KB]** | v4.1 우위 |
| ROCC | tightly-coupled, cmd/resp/mem 인터페이스 | **[NOT IN KB]** | v4.1 우위 |
| LLK | trigger-based dispatch, semaphore barrier, perf counters | **[NOT IN KB]** | v4.1 우위 |
| SMN | access_ctrl, firewall, apb_bridge, 보안 모델 | **[NOT IN KB]** | v4.1 우위 |
| FDS | ring_osc, counter, apb_if, droop detection | 레지스터 블록만 (tensixneo_reg 106/41, dispatch_reg 68/41) | v4.1 우위 (구조), v5 우위 (포트 수) |
| APB Register Map | 9개 슬레이브, 주소 맵 (0x0200_0000 ~ 0x1000_F000) | **[NOT IN KB]** | v4.1 우위 |
| Verification Checklist | 20 기능 + 5 CDC + 4 DFT 항목 | [NOT VERIFIED] 5항목만 | v4.1 우위 |
| Key Parameters | 40+ 파라미터 (NUM_CLUSTER_CPUS=8, L1_SRAM_SIZE_KB=1024 등) | 4개만 (포트 카운트 기반) | v4.1 우위 |
| v5에만 있는 것 | — | FDS 레지스터 포트 카운트 (106/41, 68/41), L1 CSR 포트 카운트 (38/97), 두 FDS 모듈의 출력 수 동일(41) 관찰 | **v5 우위** |

**요약:** v4.1이 가장 풍부한 문서(847줄). v5는 FDS/L1 CSR의 정확한 포트 카운트를 새로 확인했으나, 나머지는 모두 [NOT IN KB]. Overlay는 Chipyard 생성 RTL이라 module_parse 데이터가 핵심인데, 0.3 가중치로 인해 누락.

---

## 종합 분석

### Boost 가중치 효과

| 가중치 | 의도 | 실제 효과 |
|--------|------|----------|
| claim 3.0 | Claim 데이터 우선 노출 | **효과 있음** — No Grounding 모드에서 실제 RTL 모듈명이 풍부하게 등장. 14건(NoC), 8건(EDC), 7건(Overlay) 확보 |
| hdd_section 2.0 | HDD 섹션 우선 노출 | **제한적** — HDD 자체가 3건(FPU, SFPU, SMN)뿐이고 모두 truncated. Boost해봐야 데이터가 없으면 소용없음 |
| module_parse 0.3 | 구조 데이터 후순위 | **부작용 심각** — tt_edc_pkg.sv, TTTrinityConfig 등 핵심 인터페이스 정의가 Grounded 검색에서 사라짐. v4.1b에서 46% 커버리지였던 것이 v5에서 18%로 하락한 주요 원인 |

### analysis_type 패스스루 효과

| 상황 | 효과 |
|------|------|
| topic 검색 (EDC, NoC, Overlay) | **긍정적** — topic별로 관련 claim이 정확하게 필터됨 |
| 칩 전체 Grounded 검색 | **부정적** — `analysis_type=hdd_section` 필터가 claim/module_parse를 제거하여 커버리지 급감 |

### 그라운딩 정책 변화

v4.1 토픽별 문서(EDC, NoC, Overlay)는 **"RTL-grounded"** 라벨이지만 실제로는 LLM이 도메인 지식으로 대부분 채움. v5는 **엄격 [NOT IN KB]** 정책 적용. 이것은 RAG 변경이 아닌 **프롬프트/LLM 행동 변화**이지만, 결과 품질에 가장 큰 영향을 미침.

| 정책 | 장점 | 단점 |
|------|------|------|
| v4.1 자유 생성 | 풍부한 문서, 아키텍처 이해 | hallucination 위험, 검증 불가 |
| v5 엄격 그라운딩 | 모든 내용 검증 가능, 신뢰성 높음 | KB 부족 시 [NOT IN KB] 폭발, 문서 가치 급감 |

---

## 개선 권장사항

### 즉시 적용 (Quick Win)

| # | 항목 | 기대 효과 |
|---|------|----------|
| 1 | **module_parse 가중치 0.3 → 1.5로 상향** | tt_edc_pkg.sv, TTTrinityConfig 등 인터페이스 정의 복원. Grounded 문서 커버리지 18% → 40%+ 예상 |
| 2 | **칩 전체 Grounded 검색 시 analysis_type 필터 제거** | claim + hdd_section + module_parse 전체를 가져와 v4.1b 수준 커버리지 복원 |
| 3 | **max_results 20 → 30으로 확대** (칩 전체 검색 한정) | 칩 레벨 HDD는 토픽이 넓어서 20건으로는 부족 |

### 중기 개선

| # | 항목 | 기대 효과 |
|---|------|----------|
| 4 | **No Grounding 문서 완전성 확보** — v5가 4섹션에서 끊긴 원인 조사 | Obot 응답 길이 제한? 토큰 한도? 프롬프트 문제? |
| 5 | **Hybrid 그라운딩 도입** — KB 데이터 우선, 빈 섹션은 `[FROM LLM]` 태그로 LLM 지식 보완 | v4.1의 풍부함 + v5의 투명성 동시 확보 |
| 6 | **HDD 섹션 truncation 해결** — FPU/SFPU/SMN HDD가 overview만 나오고 나머지 truncated | 임베딩 청크 크기 확대 또는 multi-chunk retrieval |

### 장기 방향

| # | 항목 |
|---|------|
| 7 | **Spec RAG 구축 후 RTL RAG와 교차 검색** — 현재 RTL claim만으로는 "What" 정보가 구조적으로 부재 |
| 8 | **토픽별 검색 전략 분기** — 칩 전체는 필터 없이 넓게, 토픽별은 topic+claim boost로 좁게 |

---

## 파일별 비교 요약표

| 문서 | v4.1 줄수 | v5 줄수 | v5 판정 | 핵심 변화 |
|------|-----------|---------|---------|----------|
| Chip No Grounding | 525 | 123 | **혼합** — 모듈명 정확성↑, 완전성↓↓ | Claim boost로 실제 RTL명 확보, but 문서 미완성 |
| Chip Grounded | 546 | 216 | **퇴보** — 커버리지 46%→18% | analysis_type 필터 + module_parse 0.3 부작용 |
| EDC | 524 | 262 | **퇴보** (단, 방법론 차이) | 5개 인터럽트 신규 발견, but 프로토콜 상세 전멸 |
| NoC | 718 | 234 | **퇴보** (단, 방법론 차이) | 3개 신규 모듈 발견, but 아키텍처 정보 전멸 |
| Overlay | 847 | 273 | **퇴보** (단, 방법론 차이) | FDS 포트 카운트 신규, but CPU/DMA/ROCC/LLK 전멸 |

**총평:** RAG v4의 핵심 변경(analysis_type 패스스루, boost 가중치)은 **의도한 방향은 맞으나 튜닝이 필요**. module_parse 0.3 감쇠가 가장 큰 부작용이고, 칩 전체 검색의 analysis_type 필터가 두 번째 문제. 토픽별 claim 검색은 잘 동작함.
