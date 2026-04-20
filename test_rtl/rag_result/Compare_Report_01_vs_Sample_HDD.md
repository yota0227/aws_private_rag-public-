# 비교 보고서 #1: RAG v2 vs 엔지니어 수동 작성 정답지 (N1B0_NPU_HDD_v0.1)

**작성일:** 2026-04-20  
**비교 대상:**
- **문서 A (RAG v2):** 워크스페이스 6개 파일 (`01`~`06_*_v2.md`)
- **문서 B (정답지):** N1B0_NPU_HDD_v0.1.md (엔지니어 수동 작성, 17섹션)

---

## 섹션별 비교

| # | 섹션 | Sample(정답지) | RAG v2 | 판정 | 비고 |
|---|------|---------------|--------|------|------|
| 1 | Overview | ✅ | ✅ `01`에 포함 | 동등 | RAG도 타일 기반 아키텍처, 멀티클럭, 주요 서브시스템 기술. 정답지의 NPU 관점 상위 설명은 부족 |
| 2 | Package Constants & Grid | ✅ SizeX=4, SizeY=5, NumTensix=12, tile_t enum(8종), Endpoint Index Table(20개) | ❌ 없음 | 부족 | RAG에서 그리드 크기, 타일 열거형, 엔드포인트 테이블 정보 전혀 없음. RTL 파라미터 파싱 미지원 |
| 3 | Top-Level Ports | ✅ AXI_SLV_OUTSTANDING_READS=64, i_ai_clk[3:0] 컬럼별, i_tensix_reset_n[11:0] 타일별, APB×4 | ⚠️ 부분적 | 부족 | `01`에서 포트 이름은 나열했으나 비트 폭, 배열 인덱스, 파라미터 값 없음 |
| 4 | Module Hierarchy | ✅ 전체 인스턴스 트리 | ⚠️ 부분적 | 부족 | `01`에 인스턴스 나열은 있으나 전체 계층 트리가 불완전 |
| 5 | Compute Tile (Tensix) | ✅ TRISC/BRISC, FPU G-Tile/M-Tile, SFPU, TDMA, L1 Cache, DEST/SRCB | ❌ 거의 없음 | 부족 | `01`에서 `tt_tensix_with_l1` 한 줄 언급뿐. 내부 구조 전혀 없음 |
| 6 | Dispatch Engine | ✅ 상세 디스패치 구조 | ⚠️ 부분적 | 부족 | `05`에서 구조 기술했으나 Claim 없이 hdd_section만으로 작성. 구체적 신호/파라미터 누락 |
| 7 | NoC Fabric | ✅ DOR/Tendril/Dynamic 라우팅, flit 구조, VC 버퍼 | ⚠️ 부분적 | 부족 | `04`에서 XY 라우팅, 리피터, RR Arbiter 기술. Tendril/Dynamic, flit 상세 필드, VC 깊이 누락 |
| 8 | NIU | ✅ Corner NIU vs Composite NIU+Router, AXI Interface, ATT, SMN Security | ⚠️ 부분적 | 부족 | `06`에서 noc2axi 모듈 기술했으나 Corner vs Composite 구분, ATT, SMN Security 없음 |
| 9 | Clock Architecture | ✅ per-column i_ai_clk[3:0], i_dm_clk[3:0] | ⚠️ 부분적 | 부족 | `01`에서 클럭 신호 나열은 했으나 per-column 배열 구조 [3:0] 미기술 |
| 10 | Reset Architecture | ✅ per-tile i_tensix_reset_n[11:0], PRTN chain | ⚠️ 부분적 | 부족 | `01`에서 리셋 신호 나열은 했으나 per-tile [11:0] 배열, PRTN 체인 없음 |
| 11 | EDC | ✅ 링 토폴로지, 시리얼 버스, 하베스트 바이패스 | ⚠️ 부분적 | 부족 | `02`/`03`에서 Security Block, BIU 상세. 링 토폴로지, 시리얼 버스, 하베스트 바이패스 없음 |
| 12 | Power Management | ✅ PRTN, ISO_EN[11:0] | ❌ 없음 | 부족 | RAG 문서에 전력 관리 섹션 전무 |
| 13 | SRAM Inventory | ✅ 전체 SRAM 목록 | ❌ 없음 | 부족 | SRAM 인벤토리 정보 전혀 없음 |
| 14 | DFX Hierarchy | ✅ DFX 계층 구조 상세 | ❌ 거의 없음 | 부족 | `01`에서 DFX 토픽 존재 확인만. 별도 HDD 미작성 |
| 15 | Physical / P&R Guide | ✅ 배치 배선 가이드 | ❌ 없음 | 부족 | 물리 설계 관련 내용 전혀 없음 (RTL 파싱 범위 밖) |
| 16 | SW Programming Guide | ✅ 소프트웨어 프로그래밍 가이드 | ❌ 없음 | 부족 | 소프트웨어 관점 가이드 전혀 없음 (RTL 파싱 범위 밖) |
| 17 | RTL File Reference | ✅ 파일 경로 목록 | ⚠️ 부분적 | 부족 | `01`에서 4개 변형 경로, `03`에서 1개 모듈 경로. 전체 RTL 참조 없음 |

---

## RAG v2가 부족한 부분 (Top 5)

| 순위 | 섹션 | 핵심 누락 | 원인 분석 |
|------|------|----------|----------|
| **1** | Package Constants & Grid | SizeX/Y, NumTensix, tile_t enum, Endpoint Table 전체 누락 | RTL parameter/enum/localparam 파싱 데이터가 Claim으로 추출되지 않음 |
| **2** | Compute Tile (Tensix) | TRISC/BRISC, FPU G-Tile/M-Tile, SFPU, TDMA, DEST/SRCB 전체 누락 | `tt_tensix_with_l1` 내부 Claim이 검색 상위에 노출되지 않음 |
| **3** | Power Management | PRTN, ISO_EN[11:0] 전체 누락 | 전력 관리 관련 토픽/Claim이 RAG에 미존재 또는 미분류 |
| **4** | SRAM Inventory | 전체 SRAM 목록 누락 | SRAM 관련 analysis_type이 파이프라인에 미포함 |
| **5** | EDC 토폴로지 | 링 토폴로지, 시리얼 버스, 하베스트 바이패스 누락 | EDC Claim이 Security Block/BIU에 편중. 상위 아키텍처 Claim 부재 |

---

## RAG v2가 더 나은 부분

| # | 항목 | 설명 |
|---|------|------|
| 1 | **EDC Security Block 상세도** | 228개 출력 포트를 114 Config + 114 Status로 분리 분석, 2계층(Outer/Inner) 래핑 구조 |
| 2 | **BIU APB4 Bridge 상세** | Claim 기반 behavioral 분석 — R/W 핸들링, 인터럽트 생성 기능 분해 |
| 3 | **NoC Repeater 계층** | `tt_noc_repeaters_cardinal` → `tt_noc_repeater` 2계층 + `tt_noc_rr_arb` RR 중재기 |
| 4 | **RTL 설계 변형(Variants)** | 4가지 변형(기본, mem_port, N1, legacy) + 파일 경로 + 변형 간 차이 |

---

## 개선 권장사항

### 🔴 즉시 개선 (Critical Gaps)

- **P0:** RTL 파싱에 `parameter`, `localparam`, `enum` 추출 기능 추가 → Package Constants 자동 추출
- **P0:** `topic: "Tensix"` 또는 `query: "tt_tensix_with_l1"` 별도 검색으로 Tensix 내부 Claim 확보
- **P1:** PRTN/ISO_EN 관련 RTL 신호를 파싱하여 Power Management 토픽 신설

### 🟡 중기 개선

- **P1:** EDC 링 토폴로지, 시리얼 버스, 하베스트 바이패스 Claim 분석 범위 확대
- **P1:** NIU Corner vs Composite 분류를 위한 인스턴스 위치 기반 분석 추가
- **P2:** 포트 비트폭/배열 인덱스를 `module_parse` 결과에 포함

### 🟢 장기 개선

- **P2:** SRAM Inventory — 메모리 컴파일러/synthesis 리포트에서 자동 추출
- **P3:** Physical/P&R Guide, SW Programming Guide — RTL 범위 밖, 별도 RAG 업로드 필요

---

## 종합 점수

| 항목 | 정답지 (17섹션) | RAG v2 (6문서) | 커버리지 |
|------|----------------|---------------|---------|
| 섹션 존재 여부 | 17/17 | 10/17 | **59%** |
| 구체적 수치/파라미터 | 높음 | 낮음 | **~25%** |
| 서브모듈 상세도 | 중간 | 일부 높음 (EDC, NoC) | **~40%** |
| 아키텍처 관점 | 높음 (시스템 레벨) | 낮음 (블록 레벨 편중) | **~30%** |
