# Codex Review: RAG v4.1 -> v5 산출물 비교

**작성일:** 2026-04-27  
**리뷰어:** Codex  
**비교 경로:** `C:\Users\Seung-IlWoo\aws_private_rag\test_rtl\rag_result`  
**비교 대상:** `v4.1/` 산출물 5개 vs `v5/` 산출물 5개  

---

## 0. 결론

v5는 "좋아진 버전"이라기보다 **검색 정밀도와 그라운딩 투명성을 높이는 실험 버전**에 가깝다.

개선된 축은 분명하다. v5는 `claim` 중심 검색 덕분에 실제 RTL 모듈명, 포트 수, APB4 래퍼, SECDED/CDC/arbiter 같은 구체 사실을 v4.1보다 더 많이 드러낸다. 또한 `[NOT IN KB]`를 적극적으로 표시해서, 근거 없는 내용을 채워 넣는 위험은 줄었다.

하지만 HDD 산출물로서의 전체 품질은 **v4.1 대비 후퇴**했다. 전체 문서량은 약 65% 줄었고, 테이블/코드블록/구조 설명도 크게 감소했다. 특히 v5 grounded 통합 문서는 `analysis_type=hdd_section` 필터 때문에 FPU/SFPU/SMN 3개 HDD만 가져오고, v4.1에서 잡혔던 `claim` 및 `module_parse` 기반 EDC/NoC/Overlay 정보가 빠졌다.

따라서 v4.1 -> v5의 개선 정도를 한 문장으로 요약하면:

> **신뢰성/추적성은 개선됐지만, 실제 HDD로 쓸 수 있는 커버리지와 완성도는 크게 하락했다. 종합 산출물 품질 기준으로는 v5가 v4.1보다 낮다.**

---

## 1. 참고한 파일

### v4.1 산출물

| 파일 | 역할 |
|---|---|
| `v4.1/v4.1a_chip_no_grounding.md` | 칩 전체 HDD, 자유 생성 성격 |
| `v4.1/v4.1b_chip_grounded.md` | 칩 전체 HDD, KB-only grounded 성격 |
| `v4.1/v4.1_edc.md` | EDC 서브시스템 HDD |
| `v4.1/v4.1_noc.md` | NoC 서브시스템 HDD |
| `v4.1/v4.1_overlay.md` | Overlay 서브시스템 HDD |

### v5 산출물

| 파일 | 역할 |
|---|---|
| `v5/v5_chip_no_grounding.md` | 칩 전체 HDD, no grounding |
| `v5/v5_chip_grounded.md` | 칩 전체 HDD, KB-only grounded |
| `v5/v5_edc.md` | EDC 서브시스템 HDD |
| `v5/v5_noc.md` | NoC 서브시스템 HDD |
| `v5/v5_overlay.md` | Overlay 서브시스템 HDD |
| `v5/claude_review_v5.md` | 기존 v5 비교 리뷰 |

### 참고 리뷰/프롬프트

| 파일 | 리뷰에 반영한 포인트 |
|---|---|
| `Compare_Report_01_vs_Sample_HDD.md` | 정답지 기준 17개 섹션, RAG 평가 축: 커버리지, 수치/파라미터, 아키텍처 깊이 |
| `Compare_Report_v1_vs_v2.md` | RAG 산출물 비교 방식, 부족 영역 Top 5, 개선 권장사항 구조 |
| `prompt.md` | 버전 이력 및 v5 변경사항: `analysis_type` 패스스루, boost 가중치, 응답 포맷 분기 |
| `v5/claude_review_v5.md` | v5의 개선/퇴보 포인트와 원인 추정 |

---

## 2. 정량 비교

### 2.1 파일별 크기와 구조

| 문서 | v4.1 lines | v5 lines | v5/v4.1 | 판단 |
|---|---:|---:|---:|---|
| Chip no grounding | 526 | 124 | 24% | 대폭 축소 |
| Chip grounded | 546 | 216 | 40% | 대폭 축소 |
| EDC | 524 | 262 | 50% | 절반 수준 |
| NoC | 718 | 234 | 33% | 대폭 축소 |
| Overlay | 847 | 273 | 32% | 대폭 축소 |
| **합계** | **3161** | **1109** | **35%** | **전체 약 65% 감소** |

v5가 짧아진 것 자체가 항상 나쁜 것은 아니다. 문제는 줄어든 부분이 단순한 장황함이 아니라 라우팅 알고리즘, flit 구조, EDC 프로토콜, Overlay CPU/iDMA/ROCC, verification checklist 같은 핵심 HDD 내용을 포함한다는 점이다.

### 2.2 구조/근거 표기 지표

| 지표 | v4.1 합계 | v5 합계 | 변화 |
|---|---:|---:|---|
| Headings | 289 | 108 | 63% 감소 |
| Tables | 894 | 210 | 77% 감소 |
| Code blocks | 55 | 10 | 82% 감소 |
| Backtick terms | 855 | 241 | 72% 감소 |
| `[NOT IN KB]` | 35 | 124 | 254% 증가 |

해석:

- v5는 근거 없는 내용을 덜 쓰는 대신 `[NOT IN KB]`가 폭증했다.
- 즉, v5의 출력은 "검증 가능한 사실만 남기기"에는 성공했지만, "HDD 문서로 충분히 채우기"에는 실패했다.
- v4.1은 풍부하지만 검증 불명확한 내용이 많고, v5는 정직하지만 빈칸이 많다.

---

## 3. 파일별 리뷰

## 3.1 Chip no grounding

### v5 개선점

v5 no-grounding 문서는 실제 RTL 모듈명 노출 측면에서 v4.1보다 좋아졌다.

예:

| 영역 | v4.1 경향 | v5 개선 |
|---|---|---|
| NoC | `noc_mesh_2d`, `noc_clk_domain` 같은 일반명 | `tt_noc_repeaters_cardinal`, `tt_noc_secded_chk_corr_116_10`, `tt_upf_async_fifo`, `tt_noc_sync3_pulse` |
| NIU | `axi_bridge`, `att`, `smn_sec` 같은 개념명 | `tt_noc2axi_local_reg`, `tt_niu_mst_timeout` |
| Clock | `pll_ai`, `pll_noc`, `clk_div` | `tt_pll`, `tt_clkdiv2`, `tt_clkbuf`, `tt_clkgater` |
| SFPU | `sfpu` 정도 | `tt_sfpu_lregs`, `tt_sfpu_instrn_resources_used` |

이 부분은 v5의 `claim` boost가 효과를 낸 것으로 보인다. v4.1의 no-grounding 문서는 구조는 크지만, 많은 이름이 일반화되어 있어 실제 RTL 식별자로 이어지기 어렵다.

### v5 문제점

문서가 4개 섹션에서 끝난다. v4.1에는 Compute Tile, Dispatch, NoC, NIU, Clock, Reset, EDC, SRAM, DFX, RTL reference, Open Items까지 있었지만 v5는 Overview, Package/Grid, Ports, Module Hierarchy 수준에서 종료된다.

결과적으로 v5 no-grounding은 "실제 모듈명 샘플이 포함된 짧은 hierarchy 초안"이지, 칩 전체 HDD는 아니다.

### 판정

**부분 개선, 전체 후퇴.**  
정확한 RTL 명칭 노출은 개선됐지만, 문서 완성도는 크게 낮아졌다.

---

## 3.2 Chip grounded

### v5 개선점

v5 grounded 문서는 `analysis_type=hdd_section`, `pipeline_id=tt_20260221`, `query=HDD`와 결과 수를 명시한다. 출력 정책도 "KB에 없으면 `[NOT IN KB]`"로 일관적이다. 신뢰성 표기는 v4.1보다 깔끔하다.

### v5 문제점

검색 결과가 3개 HDD section으로 제한된다.

v5 metadata:

| 항목 | 값 |
|---|---|
| Search parameters | `analysis_type=hdd_section`, `pipeline_id=tt_20260221`, `query=HDD` |
| Results returned | 3 of 3 |
| 실제 커버 토픽 | FPU, SFPU, SMN 중심 |

반면 v4.1 grounded는 FPU/SFPU/SMN HDD뿐 아니라 다음 정보까지 사용했다.

| 정보 | v4.1 근거 |
|---|---|
| EDC interface/modport | `module_parse` for `tt_edc_pkg.sv` |
| Overlay CDC module | `module_parse` for `TTTrinityConfig_IntSyncAsyncCrossingSink_n1x1` |
| NoC repeater/arbiter | structural claims |
| SRAM macro | HDD/claim 기반 |
| Coverage Matrix | 섹션별 KB 상태 추적 |
| Recommended Searches | 후속 검색 전략 포함 |

v4.1 grounded의 자체 coverage summary는 46%였고, v5 grounded는 사실상 FPU/SFPU/SMN에 국한되어 기존 리뷰 기준 약 18% 수준으로 떨어진다.

### 원인

`analysis_type` 패스스루 자체는 좋은 기능이지만, 통합 HDD 검색에서 `hdd_section`만 필터링하면 오히려 치명적이다. 칩 전체 문서는 HDD section뿐 아니라 `claim`, `module_parse`, parameter/localparam, file path, port summary가 같이 필요하다.

### 판정

**명확한 후퇴.**  
v5 grounded는 더 정직하지만 더 좁다. 통합 HDD 생성에는 부적합한 retrieval strategy다.

---

## 3.3 EDC

### v5 개선점

v5 EDC는 v4.1에 없거나 약했던 실제 RTL claim을 몇 가지 확실히 포착했다.

| v5에서 확인된 정보 | 의미 |
|---|---|
| `tt_edc1_biu_soc_apb4_wrap` | APB4 래퍼 존재와 포트 리스트 |
| `edc1_biu_soc_apb4_inner` | 내부 구현 모듈 연결 |
| `tt_edc1_noc_sec_block_reg` | NoC security block register |
| `edc1_noc_sec_block_reg_inner` | register block 내부 모듈 |
| `fatal_err_irq`, `crit_err_irq`, `cor_err_irq`, `pkt_sent_irq`, `pkt_rcvd_irq` | 5개 interrupt output |
| `tt_edc1_serial_bus_repeater` | serial bus 관련 실제 모듈 |

이 정보들은 신뢰도가 높다. v4.1의 넓은 아키텍처 설명보다 좁지만, 실제 RTL fact로는 더 단단하다.

### v5 문제점

EDC HDD로 필요한 핵심은 대부분 `[NOT IN KB]`로 빠진다.

| 항목 | v4.1 | v5 |
|---|---|---|
| Toggle handshake | 시그널/시퀀스 설명 있음 | `[NOT IN KB]` |
| Packet format | fragment/opcode/MAX_FRGS 설명 있음 | `[NOT IN KB]` |
| Node ID structure | 12-bit 계층/디코딩 설명 있음 | `[NOT IN KB]` |
| Ring topology | U-shape/segment 설명 있음 | `[NOT IN KB]` |
| Harvest bypass | mux/demux 및 control 설명 있음 | `[NOT IN KB]` |
| CDC | boundary 설명 있음 | `[NOT IN KB]` |
| Register map | 8개 레지스터 수준 설명 | APB4 포트 중심 |

v5의 검색 결과는 8건으로 모두 EDC topic에 맞지만, 대부분 claim 단위다. 프로토콜과 토폴로지를 복원하기에는 `module_parse`와 패키지/interface 정보가 부족하다.

### 판정

**신뢰성은 개선, HDD 완성도는 후퇴.**  
EDC에서 v5는 좋은 RTL fact를 건졌지만, 시스템 동작 설명을 만들 만큼의 근거를 가져오지 못했다.

---

## 3.4 NoC

### v5 개선점

v5 NoC는 14개 결과를 가져오며, 다음 실제 모듈을 잘 드러낸다.

| 모듈 | v5에서 얻은 의미 |
|---|---|
| `tt_noc_repeaters_cardinal` | cardinal-direction repeater |
| `tt_upf_async_fifo` | 서로 다른 clock frequency 간 async FIFO |
| `tt_noc_sync3_pulse` | 3-stage pulse synchronizer |
| `tt_noc_async_fifo_wr_side_reset` | async FIFO reset generation |
| `tt_skid_buffer_new_assertion_off` | repeater boundary decoupling |
| `tt_noc_secded_chk_corr_116_10` | 116-bit data + 10-bit check SECDED |
| `noc_arbiter_tree` | multi-requestor priority/tree arbitration |
| `tt_harvest_robust_sync` | harvest signal synchronization |

이것은 v4.1의 일반적 NoC 설명보다 실제 RTL에 가깝다.

### v5 문제점

NoC HDD의 핵심 내용은 대부분 빠졌다.

| 항목 | v4.1 | v5 |
|---|---|---|
| Routing algorithms | DOR/TENDRIL/DYNAMIC 비교와 의사코드 | `[NOT IN KB]` |
| Flit structure | header/body/tail 필드 설명 | 일부 ECC 정보만 |
| AXI address gasket | 56-bit address field 설명 | SRAM 32x1024 기반 추정 일부 |
| Virtual channel | VC count/depth/flow control | `[NOT IN KB]` |
| Security fence | SMN group access, rule matching | `[NOT IN KB]` |
| Endpoint map | 4x5 grid endpoint layout | `[NOT IN KB]` |
| Key parameters | 40개 이상 파라미터 | 4개 수준 |

즉 v5 NoC는 "NoC 주변 RTL building block 목록"으로는 개선됐지만, "NoC architecture HDD"로는 부족하다.

### 판정

**모듈 식별은 개선, 아키텍처 문서화는 후퇴.**

---

## 3.5 Overlay

### v5 개선점

v5 Overlay는 포트 카운트와 일부 register block 실체를 잘 잡았다.

| v5에서 확인된 정보 | 의미 |
|---|---|
| FDS TensixNeo in/out = 106 / 41 | FDS register block 규모 확인 |
| FDS Dispatch in/out = 68 / 41 | dispatch-side FDS register block 규모 확인 |
| L1 CSR in/out = 38 / 97 | L1 CSR interface 규모 확인 |
| `BDAed_trinity_noc2axi_router_nw_opt...tt_mem_wrap_32x1024_2p_nomask...` | NoC routing translation selftest 계열 HDD section |

### v5 문제점

Overlay의 본질적인 내용은 거의 전부 빠졌다.

| 항목 | v4.1 | v5 |
|---|---|---|
| CPU Cluster | 8x RISC-V, Chipyard/Rocket 등 설명 | `[NOT IN KB]` |
| L1 Cache | cache/bank/SRAM 구조 설명 | CSR 포트 수만 |
| iDMA | descriptor/transfer flow 설명 | `[NOT IN KB]` |
| ROCC | command/response/memory interface 설명 | `[NOT IN KB]` |
| LLK | trigger/semaphore/perf counter 설명 | `[NOT IN KB]` |
| SMN | access/firewall/APB bridge 설명 | `[NOT IN KB]` |
| APB register map | 주소 맵 설명 | `[NOT IN KB]` |
| Verification checklist | 기능/CDC/DFT 항목 | 대부분 `[NOT IN KB]` |

Overlay는 Chipyard generated RTL과 `module_parse` 정보가 중요해 보이는데, v5 retrieval에서는 이 축이 약해졌다.

### 판정

**일부 계측형 fact는 개선, 서브시스템 HDD로는 후퇴.**

---

## 4. v5 변경사항별 효과

## 4.1 `analysis_type` 패스스루

### 긍정 효과

토픽별 검색에서는 precision이 좋아졌다.

| 토픽 | v5 결과 |
|---|---|
| EDC | 8 of 8, 대부분 EDC claim |
| NoC | 14 of 14, 대부분 NoC claim |
| Overlay | 7 of 7, Overlay claim/HDD |

무관한 토픽이 섞이는 문제는 줄었다.

### 부정 효과

통합 HDD에서는 필터가 너무 강해졌다. `analysis_type=hdd_section`만 통과시키면 다음 정보가 빠진다.

| 빠지는 타입 | 영향 |
|---|---|
| `claim` | 실제 모듈 기능/행동 요약 누락 |
| `module_parse` | interface, modport, file path, hierarchy 누락 |
| parameter/localparam/enum 추출 결과 | package constants, grid, bit width 누락 |

통합 문서 검색은 `hdd_section` 단일 타입이 아니라 multi-pass 또는 type-unfiltered 검색이 맞다.

## 4.2 Boost 가중치

prompt 기준 v5 가중치:

| 타입 | 가중치 | 관찰 결과 |
|---|---:|---|
| `claim` | 3.0 | topic 검색에서 실제 모듈명 노출 개선 |
| `hdd_section` | 2.0 | FPU/SFPU/SMN HDD만 반복 노출, coverage 제한 |
| `module_parse` | 0.3 | EDC interface, Overlay generated module, package constants 계열이 약해짐 |

`module_parse=0.3`은 현재 산출물 기준으로 과하게 낮다. v4.1 grounded에서 `tt_edc_pkg.sv`, `TTTrinityConfig_IntSyncAsyncCrossingSink_n1x1` 같은 정보가 살아 있었던 반면, v5 grounded에서는 대부분 사라졌다.

## 4.3 엄격한 `[NOT IN KB]` 정책

이 정책은 품질 평가를 어렵게도, 쉽게도 만든다.

좋은 점:

- hallucination 위험 감소
- 근거 없는 내용을 독자가 바로 구분 가능
- 검색 실패 영역이 선명하게 드러남

나쁜 점:

- KB coverage가 낮으면 HDD가 빈칸 투성이가 됨
- 도메인 문서로 읽을 수 있는 연결 설명이 급감
- v4.1보다 "쓸모 있는 설명"이 줄어듦

정책 자체는 유지하되, 출력 모드를 둘로 나누는 편이 좋다.

| 모드 | 설명 |
|---|---|
| Strict KB | 현재 v5처럼 KB에 있는 사실만 작성 |
| Hybrid HDD | KB fact는 `Source` 표기, 추론/상식 보강은 `[INFERRED]` 또는 `[FROM LLM]`로 명시 |

---

## 5. 이전 리뷰 기준으로 본 v5의 개선 정도

이전 비교 리포트들은 정답지 기준으로 다음 항목을 계속 강조했다.

| 평가 축 | 이전 리뷰에서 중요했던 내용 | v5 결과 |
|---|---|---|
| Package Constants/Grid | SizeX/Y, NumTensix, tile enum, endpoint table | v5 grounded에서는 여전히 `[NOT IN KB]`; no-grounding은 일부 있지만 근거 불명 |
| Top-Level Ports | 비트폭, 배열 인덱스, APB x4 | v5 grounded에서 대부분 `[NOT IN KB]` |
| Module Hierarchy | 전체 인스턴스 트리 | v5 no-grounding은 모듈명 개선, grounded는 FPU/SFPU/SMN 중심 |
| Tensix 내부 | TRISC/BRISC/FPU/SFPU/TDMA/L1 | v5에서 여전히 제한적 |
| NoC | 라우팅 3종, flit, VC, endpoint | v5 NoC에서 대부분 `[NOT IN KB]` |
| EDC | ring, serial bus, harvest bypass | v5 EDC에서 대부분 `[NOT IN KB]` |
| Overlay | CPU, L1, iDMA, ROCC, LLK, APB | v5 Overlay에서 대부분 `[NOT IN KB]` |
| SRAM Inventory | 타입별 수량/크기 | v5는 일부 `32x1024`만 |
| DFX/Power | iJTAG, scan, PRTN/ISO | v5에서 거의 없음 |

따라서 v5는 이전 리뷰에서 지적된 핵심 부족 항목을 해결하지 못했다. 오히려 "정확한 claim을 몇 개 더 잘 찾는다"는 장점은 생겼지만, 정답지 구조를 채우는 능력은 낮아졌다.

---

## 6. 종합 점수

정량 점수는 산출물만 보고 부여한 상대 평가다.

| 평가 항목 | v4.1 | v5 | 변화 |
|---|---:|---:|---|
| Evidence traceability | 2.5 / 5 | 4.0 / 5 | 개선 |
| Actual RTL module exposure | 3.0 / 5 | 4.0 / 5 | 개선 |
| Section coverage | 4.0 / 5 | 1.8 / 5 | 후퇴 |
| Architecture synthesis | 4.0 / 5 | 1.7 / 5 | 후퇴 |
| Parameter/register/detail richness | 3.5 / 5 | 2.0 / 5 | 후퇴 |
| Usability as HDD draft | 3.8 / 5 | 2.0 / 5 | 후퇴 |
| Debuggability of RAG result | 2.5 / 5 | 4.2 / 5 | 개선 |

### 최종 판정

| 관점 | 판정 |
|---|---|
| RAG 검색 디버깅 관점 | v5 개선 |
| RTL fact 정확도 관점 | v5 개선 |
| Grounded output 투명성 관점 | v5 개선 |
| 통합 HDD 문서 품질 관점 | v5 후퇴 |
| 정답지 대비 커버리지 관점 | v5 후퇴 |
| 전체 사용자 산출물 관점 | v5 후퇴 |

---

## 7. 개선 권장사항

## 7.1 P0: 통합 HDD 검색에서 `analysis_type=hdd_section` 단일 필터 제거

통합 문서 생성 시에는 다음 중 하나로 바꾸는 것이 좋다.

| 전략 | 설명 |
|---|---|
| Multi-pass retrieval | `hdd_section`, `claim`, `module_parse`를 각각 검색 후 병합 |
| No type filter for broad HDD | chip-level query에서는 `analysis_type` 필터를 제거 |
| Section-specific retrieval | 섹션별로 필요한 타입을 다르게 호출 |

추천:

| 섹션 | 우선 타입 |
|---|---|
| Overview | `hdd_section`, `claim` |
| Package Constants/Grid | `module_parse`, parameter/localparam extraction |
| Top-Level Ports | `module_parse` |
| Module Hierarchy | `module_parse`, `claim` |
| NoC/EDC/Overlay detail | `claim`, `module_parse`, `hdd_section` |
| RTL File Reference | `module_parse` |

## 7.2 P0: `module_parse` 가중치 상향

현재 `module_parse=0.3`은 너무 낮다.

권장:

| 상황 | 권장 가중치 |
|---|---:|
| 통합 HDD | 1.2 ~ 1.5 |
| interface/port/package 검색 | 2.0 이상 |
| topic claim 검색 | 0.8 ~ 1.2 |

특히 `tt_edc_pkg.sv`, `TTTrinityConfig_*`, top-level port, package constant, file path는 `module_parse` 없이는 복구하기 어렵다.

## 7.3 P0: 최소 커버리지 게이트 추가

문서 생성 후 자동 검증을 넣는 것이 좋다.

| 게이트 | 실패 예 |
|---|---|
| Target section coverage >= 70% | v5 chip no-grounding 4섹션 종료 |
| `[NOT IN KB]` ratio <= 30% | v5 NoC/Overlay처럼 빈칸 과다 |
| Required sections present | Package/Grid, Ports, Hierarchy, NoC, EDC, Overlay |
| Search result type diversity | hdd_section만 3건인 v5 grounded |

게이트 실패 시 문서를 저장하지 말고 "검색 재시도 필요" 상태로 남기는 편이 낫다.

## 7.4 P1: HDD section truncation 해결

v5 grounded에서 FPU/SFPU/SMN HDD가 검색되지만 대부분 overview 수준에서 잘린다.

가능한 조치:

- chunk size 확대
- section continuation retrieval
- 같은 HDD의 adjacent chunks 가져오기
- result metadata에 `truncated=true`가 있으면 자동 follow-up 검색

## 7.5 P1: Strict/Hybrid 출력 모드 분리

현재 v5는 strict mode로는 좋지만, HDD 초안으로는 너무 비어 있다.

추천 출력 방식:

| 레이어 | 표기 |
|---|---|
| KB에서 직접 확인 | `[KB]` + source/result id |
| module name 기반 추론 | `[INFERRED_FROM_MODULE_NAME]` |
| 일반 아키텍처 보강 | `[FROM_LLM]` |
| 확인 불가 | `[NOT IN KB]` |

이렇게 하면 v4.1의 풍부함과 v5의 투명성을 같이 가져갈 수 있다.

## 7.6 P1: 토픽별 검색어 재설계

현재 v5 topic 검색은 실제 모듈명은 잘 찾지만 상위 설계 개념은 놓친다.

예:

| 토픽 | 보강 검색어 |
|---|---|
| EDC | `tt_edc_pkg`, `modport`, `req_tgl`, `ack_tgl`, `edc_mux_demux_sel`, `node_id` |
| NoC | `noc_header_address_t`, `DIM_ORDER`, `TENDRIL`, `DYNAMIC`, `VC`, `endpoint_id`, `flit_type` |
| Overlay | `TTTrinityConfig`, `Rocket`, `TileLink`, `RoCC`, `iDMA`, `APB slave`, `L1 CSR` |
| Chip | `trinity_pkg`, `SizeX`, `SizeY`, `NumTensix`, `tile_t`, `i_ai_clk`, `i_tensix_reset_n` |

---

## 8. 최종 요약

v5의 핵심 가치는 "정확한 RTL fact를 더 선명하게 보여준다"는 점이다. 특히 NoC/EDC/Overlay에서 개별 모듈명과 포트 카운트가 좋아졌고, `[NOT IN KB]` 정책 덕분에 근거 없는 설명을 쉽게 식별할 수 있다.

하지만 산출물의 목적이 HDD 작성이라면, v5는 v4.1보다 덜 완성된 결과다. 문서 총량은 v4.1의 35% 수준이고, 정답지 기준 핵심 섹션 대부분이 여전히 비어 있다. `analysis_type` 패스스루와 boost 가중치는 방향은 맞지만, 통합 HDD에서 너무 좁게 작동했다.

가장 먼저 고칠 것은 두 가지다.

1. 통합 HDD 검색에서 `analysis_type=hdd_section` 단일 필터를 제거하거나 multi-pass로 바꾼다.
2. `module_parse` 가중치를 올려 interface, package, file path, hierarchy 정보를 다시 살린다.

이 두 가지만 적용해도 v5의 강점인 정확한 claim 노출을 유지하면서, v4.1이 갖고 있던 넓은 커버리지 일부를 회복할 가능성이 높다.

