# Trinity N1B0 HDD 비교 보고서: Complete v1 vs RAG v2

**비교 대상:**
- **문서 A (v1):** `Trinity_N1B0_HDD_Complete_v1.md` — RTL 파싱 + 자동 HDD 생성 + P&R 데이터 통합본 (Draft v1.3)
- **문서 B (v2):** RAG v2 6개 분할 문서 (`01`~`06_*_v2.md`)
- **비교일:** 2026-04-20

---

## 1. 섹션별 비교

| # | 섹션 | Complete v1 | RAG v2 (6문서) | 판정 | 비고 |
|---|------|-------------|---------------|------|------|
| 1 | **Overview** | ✅ 칩 전체 개요, 설계 목표 5가지 (FP32/FP16/BF16, 저지연 NoC, UCIe, 보안, DFX) | ✅ `01`에 유사 수준, 타일 기반 아키텍처, 멀티클럭 | **동등** | v1이 설계 목표 목록화에서 약간 더 구조적. v2는 설계 변형(4가지 RTL variant) 정보 추가 |
| 2 | **칩 레벨 사양** | ✅ 포트 3,519,581 / 넷 6,867,254 / 셀 3,994,907 / 매크로 2,228 / 참조 모듈 55 / 2.0GHz / 활용률 52.73% | ❌ 없음 | **v1 우위** | v2에 구체적 수치 전혀 없음 |
| 3 | **탑 레벨 블록 다이어그램** | ✅ ASCII 아트로 전체 아키텍처 시각화 (UCIe, Dispatch, Tensix, NoC, Overlay, EDC, Clock) | ⚠️ `01`에 개념적 Data Flow만 | **v1 우위** | v1은 전체 통합 다이어그램. v2는 블록별 분산 |
| 4 | **서브모듈 계층 구조** | ✅ 전체 인스턴스 트리 재귀적 기술 — Tensix 내부, NoC(NIU/VC/리피터/DFX), Dispatch, Overlay, TDMA, Clock | ⚠️ `01`에 1단계만, `02`~`06`에 분산 | **v1 우위** | v1은 단일 트리로 전체 계층 표현 |
| 5.1 | **Tensix Core + L1** | ✅ `tt_instrn_engine` 내부, 포트 상세, EDC 커넥터 5종, 하베스팅 | ❌ `01`에 한 줄 언급 | **v1 대폭 우위** | v2에 TRISC/BRISC, 내부 EDC 커넥터, 하베스팅 없음 |
| 5.2 | **FPU** | ✅ `tt_fpu_v2`, 다중 정밀도, 파이프라인, DFX | ⚠️ `06`에서 NIU 내부로 오인 | **v1 우위** | v2는 FPU 위치를 잘못 배치 |
| 5.3 | **SFPU** | ✅ `tt_sfpu_wrapper` → `tt_sfpu_lregs`, 비선형 활성화 가속 | ❌ 없음 | **v1 우위** | v2에 SFPU 전혀 없음 |
| 5.4 | **NoC 심화** | ✅ 5포트 VC 파라미터 13개, flit 필드 15개, NIU 4종, TDMA, 스로틀러, 멀티캐스트 | ⚠️ `04`에 XY 라우팅, 리피터, RR Arbiter. `06`에 FBLC 개요 | **v1 대폭 우위** | v1은 VC/flit/TDMA/스로틀러까지 포괄 |
| 5.5 | **EDC 심화** | ✅ Ingress/Egress/SRAM/Error 경로, `tt_edc_pkg`/`tt_edc1_pkg` modport, 토글 핸드셰이크, ECC | ⚠️ `02`/`03`에 Security Block/BIU 상세 | **v1 우위** | v1은 데이터 경로+에러 처리. v2는 보안/BIU 편중 |
| 5.6 | **Dispatch** | ✅ East/West 듀얼, 27포트, SDUMP(8포트)/FB(15포트) | ⚠️ `05`에 구조적 설명, 포트 상세 없음 | **v1 우위** | v1은 포트 수, 서브 인터페이스 상세 |
| 5.7 | **Overlay (RISC-V)** | ✅ Chipyard, TileLink(512-bit), `tt_rocc_l1_arb`, 레지스터 파일 2종 | ⚠️ `06`에서 토픽 언급만 | **v1 우위** | v2에 Overlay 전용 HDD 미작성 |
| 5.8 | **UCIe** | ✅ Clock/Reset Controller, Bus Cleaner, Watchdog Timer | ❌ 없음 | **v1 우위** | v2에 UCIe 전혀 없음 |
| 6 | **클럭 & 리셋** | ✅ 5도메인, 리셋 6종, 파워 굿 동기화, CLK 게이팅 18개, CDC 5종, 패스스루 체인 | ⚠️ `01`에 클럭/리셋 테이블, CDC/패스스루 없음 | **v1 우위** | v1은 CDC 모듈 5종+패스스루 체인 |
| 7 | **DFX** | ✅ JTAG+DFX 3종+FB 14포트+CSR+테스트 모드 3종 | ❌ DFX 토픽 확인만 | **v1 대폭 우위** | v2에 DFX HDD 미작성 |
| 8 | **보안** | ✅ Security Block 228포트, 입력 레지스터 5종 | ✅ `02`/`03`에 228=114+114 분석, 2계층 래핑 | **v2 약간 우위** | v2가 포트 의미 해석에서 우위 |
| 9 | **인터페이스 요약** | ✅ 8카테고리, 프로토콜 매핑 다이어그램 | ⚠️ `01`에 간략 Data Flow만 | **v1 우위** | v1은 전체 프로토콜 스택 시각화 |
| 10 | **설계 제약** | ✅ CDC, 하베스팅, 에러 처리, 전력 관리, NoC 혼잡 | ❌ 없음 | **v1 우위** | v2에 해당 섹션 없음 |
| 11 | **개정 이력** | ✅ v1.0~v1.3 | ❌ 없음 | **v1 우위** | — |
| A | **Appendix A: 포트 리스트** | ✅ Top 17포트, Router 11포트, NoC2AXI 12포트, Dispatch 27포트, FB 14포트 | ❌ 없음 | **v1 대폭 우위** | — |
| B | **Appendix B: 레지스터 맵** | ✅ APB 타이밍, CSR, Tensix IF, EDC 보안 레지스터, Overlay 레지스터 | ⚠️ `02`에 APB4 신호 추정, 레지스터 맵 없음 | **v1 대폭 우위** | — |
| C | **Appendix C: 타이밍 제약** | ✅ 2.0GHz, P&R 4단계, DFT 이슈 3건, SDC, UCIe sbclk 800MHz | ❌ 없음 | **v1 대폭 우위** | — |
| D | **Appendix D: 물리 설계** | ✅ 면적/활용률, 라이브러리, P&R 플로우, 검증 체크리스트 | ❌ 없음 | **v1 대폭 우위** | — |

---

## 2. RAG v2가 부족한 부분 (Top 5)

| 순위 | 영역 | v1 내용 | v2 상태 | 갭 심각도 |
|------|------|---------|---------|----------|
| **1** | **Tensix Core 내부 구조** | `tt_instrn_engine`, FPU/SFPU/JTAG/CSR 서브모듈, EDC 내부 커넥터 5종, 하베스팅, 포트 상세 | 한 줄 언급뿐 | 🔴 Critical |
| **2** | **NoC 상세 사양** | 5포트 VC 파라미터 13개, flit 필드 15개, NIU 4종 모듈 포트, TDMA, 스로틀러, 멀티캐스트 | 구조적 개요만 | 🔴 Critical |
| **3** | **Appendix (A~D)** | 포트 리스트, 레지스터 맵+APB 타이밍, 타이밍 제약+SDC+DFT 이슈, 물리 설계+P&R 플로우 | 전혀 없음 | 🔴 Critical |
| **4** | **칩 레벨 수치 사양** | 포트 350만, 셀 400만, 매크로 2,228, 2.0GHz, 활용률 52.73% | 없음 | 🟡 Major |
| **5** | **DFX / Overlay / UCIe** | JTAG+DFX 3종+FB+CSR, Chipyard+TileLink+RoCC, UCIe 3블록 | 거의 없음 | 🟡 Major |

---

## 3. RAG v2가 더 나은 부분

| # | 항목 | v2 내용 | v1 대비 차이 |
|---|------|---------|-------------|
| **1** | **EDC Security Block 포트 분석** | 228 = 114 Config + ~114 Status 분리 추정, Outer/Inner 2계층 래핑 구조 상세 | v1은 "228개 출력 포트"만 기술. v2가 포트 의미 해석에서 우위 |
| **2** | **BIU APB4 Bridge Behavioral 분석** | Claim 기반 behavioral 분석 — R/W 핸들링, 인터럽트 생성 기능 분해 | v1은 BIU를 별도로 기술하지 않음 |
| **3** | **RTL 설계 변형 정보** | 4가지 변형 + 파일 경로 + 변형 간 차이(i_dm_clk 유무) | v1은 변형 언급 없음 |
| **4** | **EDC Direct/Loopback 모드 상세** | Direct(운영) vs Loopback(테스트) 역할 분리, DFX/BIST 시나리오 | v1은 인스턴스 나열만 |

---

## 4. 종합 점수

| 평가 항목 | Complete v1 | RAG v2 (6문서) |
|-----------|------------|---------------|
| **섹션 커버리지** (18+4 부록) | 22/22 (100%) | 8/22 (36%) |
| **구체적 수치/파라미터** | 높음 | 낮음 |
| **서브모듈 상세도** | 높음 (3단계+) | 중간 (2단계, 분산) |
| **시스템 레벨 통합 뷰** | 높음 (단일 문서) | 낮음 (6문서 분산) |
| **물리/타이밍 설계** | 있음 (Appendix C, D) | 없음 |
| **Claim 기반 분석 깊이** | 낮음 (파싱 나열 중심) | 높음 (의미 해석) |

---

## 5. 개선 권장사항

### 🔴 P0: v2 → v3 즉시 반영

| 액션 | 방법 | 예상 효과 |
|------|------|----------|
| **Tensix 내부 HDD 추가** | `topic: "Tensix"` 또는 `query: "tt_tensix_with_l1"` 검색 → `07_Tensix_Core_HDD_v3.md` | 커버리지 +15% |
| **통합 문서 생성** | v2 6개 + 신규를 `Trinity_N1B0_HDD_Complete_v3.md`로 병합 | 통합 뷰 확보 |
| **v1 부록 병합** | v1 Appendix A~D를 v3에 통합 | 포트/레지스터/타이밍/물리 즉시 보완 |

### 🟡 P1: RAG 파이프라인 개선

| 액션 | 방법 |
|------|------|
| **수치 파라미터 Claim 추출** | RTL 파싱에 `parameter`/`localparam` 추출 추가 |
| **flit 구조체 Claim 추출** | `struct`/`enum`/`typedef` 파싱 추가 |
| **계층 통합 뷰 자동 생성** | `hierarchy` 결과를 전체 트리로 조합 |

### 🟢 P2: 장기 품질 향상

| 액션 | 방법 |
|------|------|
| **DFX/Overlay/UCIe 전용 HDD** | 해당 토픽 검색 후 별도 문서 작성 |
| **P&R/타이밍 데이터 RAG 업로드** | 백엔드 리포트 RAG 등록 |

---

> **핵심 결론:** Complete v1은 RTL 파싱 + P&R 데이터를 단일 문서로 통합하여 압도적 커버리지. RAG v2는 Claim 기반 의미 분석(EDC Security Block)에서 강점. v3에서는 v1 구조+부록에 v2 Claim 분석을 병합하는 전략이 최적.
