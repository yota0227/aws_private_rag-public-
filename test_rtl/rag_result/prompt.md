# Obot HDD 생성 프롬프트 모음

## 버전 정의

| RAG 버전 | 날짜 | RAG 파이프라인 상태 | 프롬프트 | 저장 위치 |
|----------|------|-------------------|---------|----------|
| RAG v1 | 4/17 | 기본 파싱(module_parse) + claim + hdd_section | 프롬프트 1번 (칩 전체) | `v1/` |
| RAG v2 | 4/20 | v1과 동일 | 프롬프트 1~6번 (토픽별 분할) | `v2/` |
| RAG v2.5 | 4/22 | chip_config + edc_topology + noc_protocol + overlay_deep + sram_inventory 추가 | 프롬프트 1번 (Grounding 없음) → v3a, 프롬프트 9번 (Grounding 있음) → v3b | `v3/` |

### 아침에 돌릴 것

| 순서 | 프롬프트 | 파일명 | 목적 |
|------|---------|--------|------|
| 1 | 1번 (칩 전체, Grounding 없음) | `v3/v3a_chip_no_grounding.md` | RAG 데이터 개선 효과 측정 (v2 → v2.5) |
| 2 | 9번 (통합, Grounding 있음) | `v3/v3b_chip_grounded.md` | 프롬프트 개선 효과 측정 (v3a → v3b) |
| 3 | 2번 (EDC) | `v3/v3_edc.md` | EDC 토폴로지 반영 확인 |
| 4 | 4번 (NoC) | `v3/v3_noc.md` | NoC 프로토콜 반영 확인 |
| 5 | 3번 (Overlay) | `v3/v3_overlay.md` | Overlay 심화 반영 확인 |

비교 기준:
- v3a vs v2 1번 결과 → RAG 데이터 개선 효과 (같은 프롬프트, 다른 RAG)
- v3b vs v3a → 프롬프트 개선 효과 (같은 RAG, 다른 프롬프트)
- v3 EDC/NoC/Overlay vs v2 → 심화 분석 반영 효과

---

## 사용법
- Obot 채팅창에 아래 프롬프트를 **하나씩** 입력
- **중요: search_rtl 도구는 한 번에 하나만 호출하도록 유도** (병렬 호출 시 JSON 파싱 에러 발생)
- 에러 발생 시: 프롬프트를 더 짧게 줄이거나, "도구를 한 번만 호출해" 추가

## ⚠️ Obot JSON 에러 대응
`failed to unmarshal input: invalid character '{' after top-level value` 에러가 나면:
- Obot이 search_rtl을 여러 번 동시 호출하려다 JSON을 깨뜨린 것
- 프롬프트에 **"search_rtl 도구를 딱 한 번만 호출해"** 를 추가
- 또는 검색 없이 **"이미 알고 있는 정보로 작성해"** 로 변경

---

## 1. 칩 전체 HDD (N1B0_NPU_HDD 대응)

비교 대상: `Sample/ORG/N1B0_NPU_HDD_v0.1.md`

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221"의 claim 데이터를 검색하고,
그 결과를 바탕으로 Trinity N1B0 칩 전체의 HDD(Hardware Design Document)를 작성해줘.
도구 호출은 반드시 1회만 해.

다음 섹션을 반드시 포함해:
1. Overview — 칩 목적, 주요 특징
2. Package Constants and Grid — 4×5 그리드, SizeX/SizeY, NumTensix=12, 타일 타입별 개수
3. Top-Level Ports — 주요 I/O 포트 테이블
4. Module Hierarchy — 탑 모듈(trinity)부터 주요 서브모듈까지 계층 트리
5. Compute Tile (Tensix) — FPU, SFPU, TDMA, L1 Cache, DEST/SRCB 레지스터
6. Dispatch Engine — East/West 디스패치, 명령 분배 구조
7. NoC Fabric — 라우팅 알고리즘(DOR/Tendril/Dynamic), flit 구조, VC 버퍼
8. NIU — AXI Bridge, ATT, SMN 보안
9. Clock Architecture — ai_clk, noc_clk, dm_clk, ref_clk 도메인별 구조
10. Reset Architecture — 리셋 체인, 파워 파티션
11. EDC — 링 토폴로지, 시리얼 버스, 하베스트 바이패스
12. SRAM Inventory — 메모리 인스턴스 목록
13. DFX — iJTAG, 스캔 체인
14. RTL File Reference — 주요 소스 파일 경로

pipeline_id는 tt_20260221이야.
```

---

## 2. EDC 서브시스템 HDD (EDC_HDD 대응)

비교 대상: `Sample/ORG/EDC_HDD.md`, `EDC_HDD_V0.2.md`, `EDC_HDD_V0.3.md`

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", topic "EDC"로 검색하고,
그 결과를 바탕으로 EDC1 서브시스템의 상세 HDD를 작성해줘.
도구 호출은 반드시 1회만 해.

다음 섹션을 반드시 포함해:
1. Overview — EDC1 버전, 핵심 특성 (toggle-handshake, 16-bit data + parity)
2. Architecture — 시스템 레벨 블록 다이어그램
3. Serial Bus Interface — req_tgl, ack_tgl, data, data_p, async_init 신호 설명
4. Packet Format — 프래그먼트 구조, MAX_FRGS
5. Node ID Structure — node_id_part, node_id_subp, node_id_inst 디코딩 테이블
6. Module Hierarchy — tt_edc1_* 모듈 계층
7. Ring Topology — U-shape (Segment A 하향 → U-turn → Segment B 상향) ASCII 다이어그램
8. Harvest Bypass — mux/demux 바이패스 메커니즘, edc_mux_demux_sel 동작
9. BIU (Bus Interface Unit) — 레지스터 접근 경로
10. CDC / Synchronization — 클럭 도메인 크로싱 처리
11. Instance Paths — Trinity 내 EDC 인스턴스 경로

pipeline_id는 tt_20260221이야.
```

---

## 3. Overlay (RISC-V) 블록 HDD (overlay_HDD 대응)

비교 대상: `Sample/ORG/overlay_HDD_v0.1.md`

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", topic "Overlay"로 검색하고,
그 결과를 바탕으로 Overlay(RISC-V 서브시스템) 블록의 상세 HDD를 작성해줘.
도구 호출은 반드시 1회만 해.

다음 섹션을 반드시 포함해:
1. Overview — Overlay 역할 (CPU 클러스터 + NoC + L1 + DMA의 글루 로직)
2. Position in Grid — 4×5 메시에서 Overlay가 위치하는 타일
3. Feature Summary — 기능 테이블
4. Block Diagram — ASCII 블록 다이어그램
5. Sub-module Hierarchy — tt_overlay_wrapper 하위 모듈 트리
6. Feature Details:
   - CPU Cluster (8× RISC-V cores, NUM_CLUSTER_CPUS)
   - L1 Cache (뱅크 수, 뱅크 폭, ECC 타입, SRAM 타입)
   - iDMA Engine
   - ROCC Accelerator
   - LLK (Low-Latency Kernel)
   - SMN (System Maintenance Network)
   - FDS (Frequency/Droop Sensor)
   - Dispatch Engine
7. Control Path — CPU-to-NoC Write/Read 경로 예시
8. Key Parameters — tt_overlay_pkg.sv에서 추출된 파라미터 테이블
9. Clock/Reset Summary — 멀티 클럭 도메인 구조
10. APB Register Interfaces — 슬레이브 목록, 주소 맵
11. Verification Checklist
12. Key RTL File Index

pipeline_id는 tt_20260221이야.
```

---

## 4. NoC 라우팅/패킷 HDD (router_decode_HDD 대응)

비교 대상: `Sample/ORG/router_decode_HDD_v0.5.md`, `Router_Address_Decoding_HDD.md`

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", topic "NoC"로 검색하고,
그 결과를 바탕으로 NoC 라우팅 및 패킷 구조의 상세 HDD를 작성해줘.
도구 호출은 반드시 1회만 해.

다음 섹션을 반드시 포함해:
1. Overview — 2D 메시 NoC, 라우팅 알고리즘 3종
2. Routing Algorithms — DIM_ORDER vs TENDRIL vs DYNAMIC 비교 테이블
3. Flit Structure — noc_header_address_t 필드 (x_dest, y_dest, endpoint_id, flit_type)
4. AXI Address Gasket — 56-bit 구조 (target_index, endpoint_id, tlb_index, address)
5. Virtual Channel — VC 버퍼 구조, 중재 방식
6. Security Fence — tt_noc_sec_fence_edc_wrapper, SMN 그룹 기반 접근 제어
7. Router Module Hierarchy — tt_noc_* 모듈 계층
8. Endpoint Map — 4×5 그리드의 endpoint_id 배치
9. Inter-column Repeaters — Y=3, Y=4 리피터 구조
10. Key Parameters — tt_noc_pkg.sv 파라미터 테이블

pipeline_id는 tt_20260221이야.
```

---

## 5. NIU HDD (NIU_HDD 대응)

비교 대상: `Sample/ORG/NIU_HDD_v0.1.md`

> NIU는 별도 토픽이 아님 — NoC 토픽 안에 포함. query="noc2axi"로 검색.

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", query "noc2axi"로 검색하고,
그 결과를 바탕으로 NIU(Network Interface Unit) AXI Bridge의 상세 HDD를 작성해줘.
도구 호출은 반드시 1회만 해.

포함할 섹션: Overview, AXI Interface, ATT(Address Translation Table),
SMN Security, Corner NIU vs Composite NIU+Router 차이,
FIFO 구조, 타임아웃 메커니즘, 주요 파라미터, 모듈 계층.

pipeline_id는 tt_20260221이야.
```

---

## 6. Dispatch HDD

비교 대상: (Sample에 별도 Dispatch HDD 없음 — N1B0_NPU_HDD 섹션 6 참조)

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", topic "Dispatch"로 검색하고,
그 결과를 바탕으로 Dispatch Engine의 상세 HDD를 작성해줘.
도구 호출은 반드시 1회만 해.

포함할 섹션: Overview, East/West 디스패치 구조, 명령 분배 메커니즘,
NoC 인터페이스, 모듈 계층, 주요 파라미터, 클럭/리셋.

pipeline_id는 tt_20260221이야.
```

---

## 7. v1 결과 vs Sample 비교 검증 (칩 전체 HDD)

비교 대상:
- v1: `rag_result/Trinity_N1B0_HDD_Complete_v1.md`
- Sample: `Sample/ORG/N1B0_NPU_HDD_v0.1.md`

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", query "HDD"로 검색해줘.
도구 호출은 반드시 1회만 해.

검색 결과를 보고, 아래 정답지 구조와 섹션별로 비교해줘.

[문서 B — 엔지니어 수동 작성 (정답지)]
N1B0_NPU_HDD_v0.1.md의 구조는 다음과 같아:
1. Overview
2. Package Constants and Grid — SizeX=4, SizeY=5, NumTensix=12, tile_t enum (8종), Endpoint Index Table (20개)
3. Top-Level Ports — 파라미터(AXI_SLV_OUTSTANDING_READS=64 등), 클럭(i_ai_clk[3:0] 컬럼별), 리셋(i_tensix_reset_n[11:0] 타일별), APB(×4 컬럼)
4. Module Hierarchy
5. Compute Tile (Tensix) — TRISC/BRISC, FPU G-Tile/M-Tile, SFPU, TDMA, L1 Cache, DEST/SRCB
6. Dispatch Engine
7. NoC Fabric — DOR/Tendril/Dynamic 라우팅, flit 구조, VC 버퍼
8. NIU — Corner NIU vs Composite NIU+Router, AXI Interface, ATT, SMN Security
9. Clock Architecture — per-column i_ai_clk[3:0], i_dm_clk[3:0]
10. Reset Architecture — per-tile i_tensix_reset_n[11:0], PRTN chain
11. EDC — 링 토폴로지, 시리얼 버스, 하베스트 바이패스
12. Power Management — PRTN, ISO_EN[11:0]
13. SRAM Inventory
14. DFX Hierarchy
15. Physical / P&R Guide
16. SW Programming Guide
17. RTL File Reference

다음 형식으로 비교 결과를 작성해줘:

## 섹션별 비교

| # | 섹션 | Sample(정답지) | RAG v1 | 판정 | 비고 |
|---|------|---------------|--------|------|------|
| 1 | Overview | ✅ | ✅/❌ | 동등/부족/우위 | 차이점 설명 |
| 2 | Package Constants | ✅ | ? | ? | ? |
| ... | ... | ... | ... | ... | ... |

## RAG v1이 부족한 부분 (Top 5)
1. ...
2. ...

## RAG v1이 더 나은 부분
1. ...
2. ...

## 개선 권장사항
- ...

pipeline_id는 tt_20260221이야.
```

---

## 8. v2 생성 프롬프트 (비교 결과 반영)

위 비교 결과를 확인한 후, 부족한 부분을 보강하여 v2를 생성할 때 사용:

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221"의 claim을 검색하고,
그 결과를 바탕으로 Trinity N1B0 칩 전체 HDD v2를 작성해줘.
도구 호출은 반드시 1회만 해.

v1 대비 다음 부분을 반드시 보강해:

1. Package Constants — trinity_pkg.sv 기반:
   - SizeX=4, SizeY=5, NumNodes=20, NumTensix=12, NumNoc2Axi=4, NumDispatch=2
   - tile_t enum 8종 (TENSIX, NOC2AXI_NE_OPT, NOC2AXI_ROUTER_NE_OPT, NOC2AXI_ROUTER_NW_OPT, NOC2AXI_NW_OPT, DISPATCH_E, DISPATCH_W, ROUTER)
   - Endpoint Index Table (EP=x*5+y, 20개 전체)
   - EnableDynamicRouting=1, DMCoresPerCluster=8

2. Top-Level Ports 정확한 폭:
   - i_ai_clk[3:0] (컬럼별 4개), i_dm_clk[3:0] (컬럼별 4개)
   - i_tensix_reset_n[11:0] (타일별 12개)
   - i_dm_core_reset_n[13:0][7:0] (14×8)
   - APB ×4 컬럼 (i_reg_psel[3:0] 등)

3. NoC 라우팅 3종 비교:
   - DIM_ORDER: XY 차원 순서
   - TENDRIL: 적응형 라우팅
   - DYNAMIC: 동적 라우팅 (EnableDynamicRouting=1)
   - flit 헤더: x_dest, y_dest, endpoint_id, flit_type, dynamic_carried_list

4. N1B0 vs Baseline Trinity 차이 테이블:
   - per-column 클럭 배열, inter-column 리피터, PRTN chain, ISO_EN[11:0]

5. Power Management:
   - PRTN 4-column daisy-chain
   - ISO_EN[11:0] 파워 아일랜드 격리

6. SRAM Inventory — 메모리 인스턴스 목록 (타입, 크기, 위치)

기존 v1의 좋은 부분(UCIe, 보안 블록 228포트, VC 버퍼 파라미터, 포트 스로틀러, CDC 동기화 상세)은 유지해.

pipeline_id는 tt_20260221이야.
```

---

## 검증 체크리스트

각 HDD 생성 후 Sample/ORG 문서와 비교할 포인트:

| 비교 항목 | 확인 내용 |
|-----------|----------|
| 구조 완전성 | Sample의 섹션이 RAG 결과에도 있는가? |
| 수치 정확성 | 4×5 그리드, 12 Tensix, 8 RISC-V cores 등 |
| 토폴로지 | EDC 링, NoC 메시, 하베스트 바이패스 |
| 파라미터 | pkg.sv에서 추출된 localparam 값 |
| 깊이 | 서브모듈 역할, 신호 레벨 설명 |
| 누락 | Sample에 있는데 RAG에 없는 내용 |
| RAG 우위 | RAG에만 있는 추가 정보 (UCIe, 보안 블록 등) |


---

## 9. v2.5 통합 HDD 확인 (심화 분석 반영 후)

> 4/22 HDD 재생성 후 결과 확인용. Round 1 Grounding 제약 포함.

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", query "HDD", max_results 20으로 검색하고,
검색된 HDD 섹션들을 하나의 통합 N1B0 HDD 문서로 정리해줘.
도구 호출은 반드시 1회만 해.

규칙:
- 영어로 작성
- 검색 결과에 없는 내용은 절대 추가하지 마. 없으면 "[NOT IN KB]"로 표기
- RTL 신호명, 모듈명은 원문 그대로 유지
- trinity_router는 N1B0에서 인스턴스화되지 않음 (EMPTY by design). 계층에 넣지 마.
- Package Constants가 있으면 SizeX, SizeY, NumTensix, tile_t enum 반드시 포함
- EDC 토폴로지가 있으면 링 구조, 시리얼 버스, 하베스트 바이패스 포함
- NoC 프로토콜이 있으면 라우팅 알고리즘 3종 비교, flit 구조 포함
- Overlay 심화가 있으면 CPU 클러스터, L1 캐시, APB 슬레이브 포함
- SRAM Inventory가 있으면 메모리 타입별 수량 테이블 포함

pipeline_id는 tt_20260221이야.
```
