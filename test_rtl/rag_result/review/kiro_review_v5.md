# RAG v4 (v5/) vs RAG v3.1 (v4.1/) — Kiro 비교 리뷰

**리뷰어:** Kiro
**리뷰일:** 2026-04-27
**비교 대상:** v5/ (RAG v4, Kiro 생성) vs v4.1/ (RAG v3.1, Obot Claude 생성)
**참고:** claude_review_v5.md

---

## 0. 컨텍스트

v5 문서는 **Kiro**가 생성했고, v4.1 문서는 **Obot에 등록된 Claude**가 생성했다.
RAG 파이프라인 버전도 다르고(v4 vs v3.1), LLM도 다르고(Kiro vs Obot Claude), 프롬프트 실행 환경도 다르다.
따라서 이 리뷰는 **RAG 변경 효과 + LLM 행동 차이 + 프롬프트 해석 차이**가 혼재된 결과를 분석한다.

### RAG v4 변경사항 (prompt.md 기준)

| 변경 | 설명 |
|------|------|
| analysis_type 패스스루 | API GW → RTL Lambda로 analysis_type이 직접 전달됨 |
| Boost 가중치 | claim 3.0 / hdd_section 2.0 / module_parse 0.3 |
| 응답 포맷 분기 | analysis_type별 응답 형식 분기 |

---

## 1. 파일별 줄 수 비교

| 문서 | v4.1 줄수 | v5 줄수 | 변화율 | 비고 |
|------|-----------|---------|--------|------|
| Chip No Grounding | 525 | 123 | **-77%** | v5 미완성 (도구 환경 문제) |
| Chip Grounded | 545 | 216 | **-60%** | [NOT IN KB] 대량 발생 |
| EDC | 523 | 262 | **-50%** | 프로토콜 상세 전멸 |
| NoC | 717 | 234 | **-67%** | 아키텍처 정보 전멸 |
| Overlay | 846 | 273 | **-68%** | CPU/DMA/ROCC/LLK 전멸 |
| **합계** | **3,156** | **1,108** | **-65%** | |

---

## 2. Chip 전체 HDD — No Grounding

### 2.1 v5가 나은 점

| 항목 | v4.1a | v5 | 판정 |
|------|-------|-----|------|
| 그리드 타일 타입 | 4종 (TSIX/NIU/ARC/DRAM) | **6종** (ETH/ROUTER/TENSIX/DRAM/PCI/ARC) | **v5 우위** |
| Module Hierarchy 모듈명 | 추정명 (`fpu_top`, `tdma_engine`) | **실제 RTL명** (`tt_sfpu_lregs`, `tt_noc_secded_chk_corr_116_10`) | **v5 우위** |
| NIU 모듈 | 개념 설명만 | `tt_noc2axi_local_reg [×3]`, `tt_niu_mst_timeout [×5]` 구체 인스턴스 | **v5 우위** |
| Clock 모듈 | `pll_ai`, `clk_div` (추정) | `tt_clkdiv2`, `tt_clkbuf`, `tt_clkgater` (실제) | **v5 우위** |
| NoC ECC | 언급만 | `tt_noc_secded_chk_corr_116_10` — 116-bit data + 10-bit check | **v5 우위** |

### 2.2 v4.1이 나은 점

| 항목 | v4.1a | v5 | 판정 |
|------|-------|-----|------|
| 섹션 완전성 | **14섹션** 완전 | 4섹션에서 끊김 | **v4.1 압도** |
| Dispatch 상세 | East/West 구조 + 다이어그램 | hierarchy에 이름만 | v4.1 우위 |
| EDC 상세 | 링 토폴로지 + 시리얼 버스 + 하베스트 | hierarchy에 이름만 | v4.1 우위 |
| [TBC] 추적 | 9개 Open Items 체계적 관리 | 없음 | v4.1 우위 |

### 2.3 v5 미완성 원인

v5 chip_no_grounding은 **fsWrite + fsAppend 중복 → preToolUse hook 반복 → 4섹션에서 중단**. RAG 품질 문제가 아닌 **도구 실행 환경 문제**. 동일 프롬프트를 hook 없이 재실행하면 14섹션 완전 생성 가능할 것으로 예상.

---

## 3. Chip 전체 HDD — Grounded

| 항목 | v4.1b | v5 | 판정 |
|------|-------|-----|------|
| 검색 결과 타입 | HDD + claims + module_parse (복합) | **hdd_section만** 3건 | **v4.1 우위** |
| 커버리지 | 46% (12/26 grounded) | ~18% (3/17 grounded) | **v4.1 우위** |
| EDC 정보 | `tt_edc_pkg.sv` modport 4개 + 시그널 | 없음 | v4.1 우위 |
| Overlay 정보 | `TTTrinityConfig` CDC 모듈 | 없음 | v4.1 우위 |
| NoC 정보 | repeaters + arbiter claims | 없음 | v4.1 우위 |
| KB Coverage Matrix | 26항목 추적 + 8개 Recommended Searches | 없음 | v4.1 우위 |

**핵심 원인:** 프롬프트 9번 `query="HDD"` → analysis_type 패스스루가 `hdd_section`만 필터 → claim/module_parse 전부 누락.

---

## 4. EDC 서브시스템

| 항목 | v4.1 | v5 | 판정 |
|------|------|-----|------|
| Toggle-handshake 프로토콜 | 완전 (시그널 테이블 + 시퀀스) | **[NOT IN KB]** | v4.1 우위 |
| Packet Format | fragment 구조, opcode 7종, MAX_FRGS | **[NOT IN KB]** | v4.1 우위 |
| Node ID Structure | 12-bit 계층, 디코딩 테이블 | **[NOT IN KB]** | v4.1 우위 |
| Ring Topology | U-shape 다이어그램 (40 hop) | **[NOT IN KB]** | v4.1 우위 |
| Harvest Bypass | mux/demux, edc_mux_demux_sel | **[NOT IN KB]** | v4.1 우위 |
| BIU Register Map | 8개 레지스터 (오프셋/접근타입) | APB4 포트 리스트만 | v4.1 우위 |
| **v5 신규 발견** | — | 5개 인터럽트 (`fatal_err_irq`, `crit_err_irq`, `cor_err_irq`, `pkt_sent_irq`, `pkt_rcvd_irq`), inner 모듈 분리 | **v5 우위** |

---

## 5. NoC 서브시스템

| 항목 | v4.1 | v5 | 판정 |
|------|------|-----|------|
| Routing Algorithms | 3종 완전 비교 + 의사코드 | **[NOT IN KB]** | v4.1 우위 |
| Flit Structure | 512-bit, 14개 필드 매핑 | SECDED 116+10만 | v4.1 우위 |
| AXI Address Gasket | 56-bit 구조 완전 | SRAM 32×1024만 | v4.1 우위 |
| Virtual Channel | 4 VC, credit flow 다이어그램 | arbiter_tree만 | v4.1 우위 |
| Security Fence | SMN group access control | **[NOT IN KB]** | v4.1 우위 |
| Endpoint Map | 4×5 grid 전체 (120+ 매핑) | **[NOT IN KB]** | v4.1 우위 |
| Key Parameters | 40+ 파라미터 | 4개만 | v4.1 우위 |
| **v5 신규 발견** | — | `tt_noc_sync3_pulse`, `tt_harvest_robust_sync`, `tt_noc_async_fifo_wr_side_reset` | **v5 우위** |

---

## 6. Overlay (RISC-V) 서브시스템

| 항목 | v4.1 | v5 | 판정 |
|------|------|-----|------|
| CPU Cluster | 8× RV64GC, 5-stage pipeline | **[NOT IN KB]** | v4.1 우위 |
| L1 Cache | I$ 32KB/4-way, D$ 64KB/8-way | CSR reg (38in/97out)만 | v4.1 우위 |
| iDMA | 4채널, scatter-gather | **[NOT IN KB]** | v4.1 우위 |
| ROCC / LLK / SMN | 각각 상세 | **[NOT IN KB]** | v4.1 우위 |
| APB Register Map | 9개 슬레이브, 주소 맵 | **[NOT IN KB]** | v4.1 우위 |
| Verification Checklist | 20+5+4 항목 | 5항목만 | v4.1 우위 |
| **v5 신규 발견** | — | FDS 포트 카운트 (tensixneo 106/41, dispatch 68/41), L1 CSR (38/97), 두 FDS 출력 수 동일(41) | **v5 우위** |

---

## 7. Claude 리뷰와의 비교 (메타 리뷰)

### 7.1 동의하는 점

| Claude 판정 | Kiro 판정 | 항목 |
|-------------|-----------|------|
| v5 모듈명 정확성 향상 | ✅ 동의 | Claim boost(3.0) 효과 확인 |
| v5 chip_no_grounding 미완성 | ✅ 동의 | 원인은 RAG가 아닌 도구 환경 |
| v5 grounded 커버리지 급감 | ✅ 동의 | analysis_type 필터 + module_parse 0.3 |
| module_parse 0.3이 핵심 부작용 | ✅ 동의 | tt_edc_pkg.sv, TTTrinityConfig 누락 주범 |
| v5 EDC 5개 인터럽트 신규 | ✅ 동의 | 실제 RTL 정보 |
| v5 NoC 3개 신규 모듈 | ✅ 동의 | sync3_pulse, harvest_robust_sync, async_fifo_wr_side_reset |

### 7.2 Kiro 추가 관찰 (Claude 리뷰에 없는 것)

| # | 관찰 |
|---|------|
| 1 | **v5 chip_no_grounding 미완성은 RAG 문제가 아님** — fsWrite/fsAppend 중복 + hook 반복이 원인. 동일 RAG로 재실행하면 14섹션 가능 |
| 2 | **v5 그라운딩 정책이 더 정직함** — v4.1은 "RTL-grounded"라면서 LLM 지식으로 채움. v5는 [NOT IN KB]로 명시. 엔지니어 입장에서 v5가 더 신뢰할 수 있음 |
| 3 | **v4.1의 풍부함은 hallucination 리스크** — "40 hop U-shape", "512-bit flit 14개 필드", "8× RV64GC 5-stage pipeline" 등은 KB 미확인. 정확할 수도 있지만 검증 불가 |
| 4 | **v5 FDS 포트 카운트 관찰이 가치 있음** — 두 FDS 모듈 출력 수 동일(41)은 공통 인터페이스 존재를 시사. 데이터 기반 인사이트 |
| 5 | **Kiro의 preToolUse hook이 생산성 저하** — 매 fsWrite/fsAppend마다 hook 검토 필요. Markdown 문서에는 불필요한 오버헤드 |

---

## 8. Boost 가중치 효과 분석

| 가중치 | 의도 | 실제 효과 | 평가 |
|--------|------|----------|------|
| claim 3.0 | Claim 우선 노출 | **효과 있음** — 실제 RTL 모듈명 풍부 (NoC 14건, EDC 8건, Overlay 7건) | ✅ 유지 |
| hdd_section 2.0 | HDD 우선 노출 | **제한적** — HDD 자체가 3건뿐, 모두 truncated | ⚠️ 데이터 부족이 본질 |
| module_parse 0.3 | 구조 데이터 후순위 | **부작용 심각** — 핵심 인터페이스 정의 누락 | ❌ 상향 필요 |

---

## 9. 개선 권장사항

### 즉시 적용 (Quick Win)

| # | 항목 | 기대 효과 |
|---|------|----------|
| 1 | **module_parse 가중치 0.3 → 1.5** | tt_edc_pkg.sv, TTTrinityConfig 복원. Grounded 커버리지 18% → 40%+ |
| 2 | **칩 전체 Grounded 검색 시 analysis_type 필터 제거** | claim + hdd + module_parse 전체 확보 |
| 3 | **max_results 20 → 30** (칩 전체 한정) | 칩 레벨은 토픽이 넓어서 20건 부족 |

### 중기 개선

| # | 항목 | 기대 효과 |
|---|------|----------|
| 4 | **Hybrid 그라운딩** — KB 우선, 빈 섹션은 `[FROM LLM]` 태그로 보완 | v4.1의 풍부함 + v5의 투명성 동시 확보 |
| 5 | **HDD 섹션 truncation 해결** — 임베딩 청크 크기 확대 또는 multi-chunk retrieval | FPU/SFPU/SMN HDD overview만 나오는 문제 해결 |
| 6 | **Markdown 파일에 대한 preToolUse hook 면제** | 생산성 향상 |

### 장기 방향

| # | 항목 |
|---|------|
| 7 | **Spec RAG 구축 후 RTL RAG와 교차 검색** — RTL claim만으로는 "What" 정보 구조적 부재 |
| 8 | **토픽별 검색 전략 분기** — 칩 전체는 필터 없이 넓게, 토픽별은 topic+claim boost로 좁게 |

---

## 10. 종합 판정

| 문서 | v5 판정 | 핵심 변화 |
|------|---------|----------|
| Chip No Grounding | **혼합** — 모듈명 정확성↑, 완전성↓↓ (도구 문제) | Claim boost로 실제 RTL명 확보 |
| Chip Grounded | **퇴보** — 커버리지 46%→18% | analysis_type 필터 + module_parse 0.3 |
| EDC | **퇴보** (방법론 차이) | 5개 인터럽트 신규, but 프로토콜 전멸 |
| NoC | **퇴보** (방법론 차이) | 3개 신규 모듈, but 아키텍처 전멸 |
| Overlay | **퇴보** (방법론 차이) | FDS 포트 카운트 신규, but CPU/DMA 전멸 |

**총평:** RAG v4의 claim boost는 **의도대로 동작**하여 실제 RTL 모듈명 확보에 성공했다. 그러나 module_parse 0.3 감쇠와 analysis_type 필터가 Grounded 문서의 커버리지를 크게 떨어뜨렸다. v5의 엄격한 [NOT IN KB] 정책은 **신뢰성 면에서 v4.1보다 우수**하지만, KB 데이터가 부족한 현 상태에서는 문서 가치가 급감한다. **Hybrid 그라운딩 + module_parse 가중치 상향**이 다음 버전의 핵심 과제다.

---

*End of Review*