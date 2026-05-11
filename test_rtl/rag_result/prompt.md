# HDD 자동 생성 테스트 가이드 (SoC Engineer용)

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-04-17 | 초판 |
| v1.3 | 2026-04-29 | RAG v7 반영 |
| **v2.0** | **2026-05-08** | **v9.2 기준 정리. SoC Engineer 가독성 개선. 사용 중인 프롬프트만 상단 배치** |

---

## 이 문서가 뭔가요?

RTL 코드를 AI가 자동으로 읽어서 **HDD(Hardware Design Document) 초안**을 만드는 시스템이 있습니다.
이 문서는 그 시스템의 **품질을 측정하는 테스트 프롬프트 모음**입니다.

**테스트 방식:**
1. 아래 프롬프트를 AI 채팅(Obot/MCP)에 붙여넣기
2. 생성된 HDD를 정답지(`Sample/ORG/N1B0_NPU_HDD_v0.1.md`)와 비교
3. "이 부분이 빠졌다" / "이건 틀렸다" 피드백

**현재 정답지 대비 달성률:** ~76% (v9.2 기준, 산출물 전체)

---

## 산출물 구조

매 버전 업데이트 시 아래 6개 파일을 동일하게 생성하여 품질 변화를 추적합니다.

| 순서 | 무엇을 검색하나 | 생성 파일 | 목적 |
|------|---------------|----------|------|
| 1 | 칩 전체 (**KB 데이터만**) | `v{N}/v{N}_chip_no_grounding.md` | 순수 RAG 검색 결과만으로 작성. 빈 곳은 비워둠 |
| 2 | 칩 전체 (**KB + LLM 보완**) | `v{N}/v{N}_chip_grounded.md` | KB에 없는 부분은 AI가 추론하여 보완 (태그 표시) |
| 3 | EDC 토픽 | `v{N}/v{N}_edc.md` | EDC 토폴로지 확인 |
| 4 | NoC 토픽 | `v{N}/v{N}_noc.md` | NoC 프로토콜 확인 |
| 5 | Overlay 토픽 | `v{N}/v{N}_overlay.md` | Overlay 심화 확인 |
| **6** | **1~5번 머지** | **`v{N}/v{N}_N1B0_HDD.md`** | **정답지와 1:1 비교용 통합 HDD** |

> 중간 산출물(1~5번)은 삭제하지 않습니다. 추적성과 재현성을 위해 보존.

### 비교 방법

- `v{N}_chip_no_grounding` vs `v{N-1}_chip_no_grounding` → **RAG 데이터 자체가 좋아졌나?** (파서 개선 효과)
- `v{N}_chip_grounded` vs `v{N}_chip_no_grounding` → **AI 보완이 얼마나 도움 되나?** (LLM 추론 가치)
- **`v{N}_N1B0_HDD` vs 정답지** → 최종 품질 평가

---

## 현재 사용 중인 프롬프트 (v9.2)

### 사용 전 주의사항

- MCP 도구가 연결된 AI 채팅 환경에서 사용
- **search_rtl 도구는 한 번에 하나만 호출** (병렬 호출 시 JSON 에러 발생)
- 에러 나면: "search_rtl 도구를 딱 한 번만 호출해" 추가

---

### 프롬프트 1: 칩 전체 HDD (KB 데이터만 — 순수 검색 결과)

> 파일명: `v{N}/v{N}_chip_no_grounding.md`
> 비교 대상: `Sample/ORG/N1B0_NPU_HDD_v0.1.md`
> **특징:** KB에서 검색된 내용만 사용. AI가 추론/보완하지 않음. 빈 섹션이 있을 수 있음.

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221"의 claim 데이터를 검색하고,
그 결과를 바탕으로 Trinity N1B0 칩 전체의 HDD(Hardware Design Document)를 작성해줘.
도구 호출은 반드시 1회만 해.

다음 섹션을 반드시 포함해:
1. Overview — 칩 목적, 주요 특징
2. Package Constants and Grid — 4x5 그리드, SizeX/SizeY, NumTensix=12, 타일 타입별 개수
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

### 프롬프트 2: 칩 전체 HDD (KB + LLM 보완 — 빈 곳을 AI가 채움)

> 파일명: `v{N}/v{N}_chip_grounded.md`
> **특징:** KB에 있는 건 그대로 쓰고, 없는 부분은 AI가 도메인 지식으로 보완.
> - 태그 없음 = KB에서 확인된 사실 (신뢰 가능)
> - `[FROM LLM]` = AI 추론으로 보완 (검증 필요)
> - `[NOT IN KB]` = 정보 없음 (Spec 문서 참조 필요)

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", query "HDD", max_results 30으로 검색하고,
검색된 결과를 바탕으로 통합 N1B0 HDD 문서를 정리해줘.
도구 호출은 반드시 1회만 해.

Hybrid 그라운딩 규칙:
- KB에서 확인된 내용은 태그 없이 작성 (모듈명, 포트, claim 등)
- KB에 없지만 아키텍처 이해에 필수적인 내용은 [FROM LLM] 태그를 붙여서 보완
- 구체적 수치(비트폭, 엔트리 수 등)가 KB에 없으면 [TBC]로 표기
- RTL 신호명, 모듈명은 원문 그대로 유지
- trinity_router는 N1B0에서 인스턴스화되지 않음 (EMPTY by design). 계층에 넣지 마.
- 문서 끝에 KB Coverage Matrix를 포함해서 어떤 섹션이 KB/LLM/미확인인지 추적

pipeline_id는 tt_20260221이야.
```

---

### 프롬프트 3: EDC 서브시스템

> 파일명: `v{N}/v{N}_edc.md`
> 비교 대상: `Sample/ORG/EDC_HDD.md`

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

### 프롬프트 4: NoC 라우팅/패킷

> 파일명: `v{N}/v{N}_noc.md`
> 비교 대상: `Sample/ORG/router_decode_HDD_v0.5.md`

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
8. Endpoint Map — 4x5 그리드의 endpoint_id 배치
9. Inter-column Repeaters — Y=3, Y=4 리피터 구조
10. Key Parameters — tt_noc_pkg.sv 파라미터 테이블

pipeline_id는 tt_20260221이야.
```

---

### 프롬프트 5: Overlay (RISC-V)

> 파일명: `v{N}/v{N}_overlay.md`
> 비교 대상: `Sample/ORG/overlay_HDD_v0.1.md`

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", topic "Overlay"로 검색하고,
그 결과를 바탕으로 Overlay(RISC-V 서브시스템) 블록의 상세 HDD를 작성해줘.
도구 호출은 반드시 1회만 해.

다음 섹션을 반드시 포함해:
1. Overview — Overlay 역할 (CPU 클러스터 + NoC + L1 + DMA의 글루 로직)
2. Position in Grid — 4x5 메시에서 Overlay가 위치하는 타일
3. Feature Summary — 기능 테이블
4. Block Diagram — ASCII 블록 다이어그램
5. Sub-module Hierarchy — tt_overlay_wrapper 하위 모듈 트리
6. Feature Details (CPU Cluster, L1 Cache, iDMA, FDS, Dispatch)
7. Clock/Reset Summary — 멀티 클럭 도메인 구조
8. APB Register Interfaces — 슬레이브 목록
9. Key RTL File Index

pipeline_id는 tt_20260221이야.
```

---

### 프롬프트 6: 통합 HDD 생성 (1~5번 머지)

> 파일명: `v{N}/v{N}_N1B0_HDD.md`
> 1~5번 산출물을 하나로 합치는 단계

```
위에서 생성한 5개 문서(chip_no_grounding, chip_grounded, edc, noc, overlay)를
하나의 통합 N1B0 HDD 문서로 머지해줘.

규칙:
- 중복 제거
- 섹션 순서는 정답지(N1B0_NPU_HDD_v0.1.md) 기준
- 각 섹션의 출처(어떤 토픽 검색에서 왔는지)를 Appendix에 기록
- trinity_router는 N1B0에서 인스턴스화되지 않음 (EMPTY by design). 계층에 넣지 마.
```

---

## 검증 체크리스트

생성된 HDD를 정답지와 비교할 때 확인할 포인트:

| 비교 항목 | 확인 내용 |
|-----------|----------|
| 구조 완전성 | 정답지의 섹션이 RAG 결과에도 있는가? |
| 수치 정확성 | 4x5 그리드, 12 Tensix, 8 RISC-V cores 등 |
| 토폴로지 | EDC 링, NoC 메시, 하베스트 바이패스 |
| 파라미터 | pkg.sv에서 추출된 localparam 값 |
| 깊이 | 서브모듈 역할, 신호 레벨 설명 |
| 누락 | 정답지에 있는데 RAG에 없는 내용 |
| RAG 우위 | RAG에만 있는 추가 정보 |

---

## RAG 파이프라인 버전 이력

| RAG 버전 | 날짜 | 주요 변경 | Content Fidelity |
|----------|------|----------|-----------------|
| v1 | 4/17 | 기본 파싱 + claim | ~40% |
| v5 | 4/28 | Package parser (localparam/enum/struct) | ~55% |
| v7 | 4/29 | max_results 50, 포트 전체 노출 | ~55% |
| v8 | 5/01 | Port classifier, boost 가중치 | ~68% |
| v9 | 5/04 | Hybrid 태그 + 6-file split | ~67% |
| v9.1 | 5/06 | dedup + 실명 노출 + KB Coverage 89% | ~74% |
| **v9.2** | **5/08** | **EP Table + Dispatch wire + Flit 4D + Clock mesh** | **~76%** |

---

## 피드백 방법

가장 도움이 되는 피드백:

```
[프롬프트 N번 결과 관련]
- 정답지 섹션 X에 있는 <내용>이 RAG 결과에 없다
- 또는: RAG 결과의 <내용>이 틀렸다. 정확한 값은 <정답>이다
- 또는: 이 부분은 RTL의 <파일명>을 보면 알 수 있다
```

피드백 채널: Confluence 댓글 또는 Slack #bos-ai-rag

---
---

## Backup: 이전 버전 프롬프트 (참고용)

> 아래는 v1~v8 시절에 사용했던 프롬프트입니다. 현재는 위의 6개 프롬프트만 사용합니다.

### [Backup] NIU HDD 프롬프트

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", query "noc2axi"로 검색하고,
그 결과를 바탕으로 NIU(Network Interface Unit) AXI Bridge의 상세 HDD를 작성해줘.
도구 호출은 반드시 1회만 해.

포함할 섹션: Overview, AXI Interface, ATT(Address Translation Table),
SMN Security, Corner NIU vs Composite NIU+Router 차이,
FIFO 구조, 타임아웃 메커니즘, 주요 파라미터, 모듈 계층.

pipeline_id는 tt_20260221이야.
```

### [Backup] Dispatch HDD 프롬프트

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", topic "Dispatch"로 검색하고,
그 결과를 바탕으로 Dispatch Engine의 상세 HDD를 작성해줘.
도구 호출은 반드시 1회만 해.

포함할 섹션: Overview, East/West 디스패치 구조, 명령 분배 메커니즘,
NoC 인터페이스, 모듈 계층, 주요 파라미터, 클럭/리셋.

pipeline_id는 tt_20260221이야.
```

### [Backup] v1 vs 정답지 비교 프롬프트

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221", query "HDD"로 검색해줘.
도구 호출은 반드시 1회만 해.

검색 결과를 보고, 정답지(N1B0_NPU_HDD_v0.1.md) 구조와 섹션별로 비교해줘.

## 섹션별 비교
| # | 섹션 | Sample(정답지) | RAG | 판정 | 비고 |
|---|------|---------------|-----|------|------|

## 부족한 부분 (Top 5)
## 더 나은 부분
## 개선 권장사항

pipeline_id는 tt_20260221이야.
```

### [Backup] v2 생성 프롬프트 (비교 결과 반영)

```
search_rtl 도구를 딱 한 번만 호출해서 pipeline_id "tt_20260221"의 claim을 검색하고,
그 결과를 바탕으로 Trinity N1B0 칩 전체 HDD v2를 작성해줘.
도구 호출은 반드시 1회만 해.

v1 대비 보강 포인트:
1. Package Constants — EP Table 20개 전체, tile_t 8종
2. Top-Level Ports — 정확한 비트폭 (i_ai_clk[3:0], i_tensix_reset_n[11:0] 등)
3. NoC 라우팅 3종 비교 + flit 헤더 필드
4. N1B0 vs Baseline 차이 테이블
5. Power Management — PRTN 4-column daisy-chain, ISO_EN[11:0]
6. SRAM Inventory

pipeline_id는 tt_20260221이야.
```

### [Backup] Grounding 태그 규칙

| 태그 | 의미 | 사용 조건 |
|------|------|----------|
| (태그 없음) | KB에서 직접 확인된 사실 | 검색 결과에 모듈명, 포트, claim이 있을 때 |
| `[FROM LLM]` | LLM 도메인 지식으로 보완 | KB에 없지만 아키텍처 이해에 필수적인 내용 |
| `[NOT IN KB]` | KB에 없고 LLM으로도 보완 불가 | 구체적 수치, 파라미터 등 추측 불가한 항목 |
| `[TBC]` | 확인 필요 | KB/LLM 모두 불확실한 수치 |
