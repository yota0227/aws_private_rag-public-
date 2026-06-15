# HDD 자동 생성 테스트 가이드 (SoC Engineer용)

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-04-17 | 초판 |
| v1.3 | 2026-04-29 | RAG v7 반영 |
| v2.0 | 2026-05-08 | v9.2 기준 정리. SoC Engineer 가독성 개선. 사용 중인 프롬프트만 상단 배치 |
| **v2.1** | **2026-05-14** | **RAG 검증 프레임워크 추가. 측정 기준 계층화 (L1~L6). 버전별 비교 기준 명확화** |
| **v2.2** | **2026-05-18** | **v9.4a 산출물 생성 완료. Neptune Graph DB 기여도 반영. 버전 이력 갱신** |

---

## 이 문서가 뭔가요?

RTL 코드를 AI가 자동으로 읽어서 **HDD(Hardware Design Document) 초안**을 만드는 시스템이 있습니다.
이 문서는 그 시스템의 **품질을 측정하는 테스트 프롬프트 모음**입니다.

**테스트 방식:**
1. 아래 프롬프트를 AI 채팅(Obot/MCP)에 붙여넣기
2. 생성된 HDD를 정답지(`Sample/ORG/N1B0_NPU_HDD_v0.1.md`)와 비교
3. "이 부분이 빠졌다" / "이건 틀렸다" 피드백

**현재 정답지 대비 달성률:** ~85% (v9.4a 기준, L1~L3 구조적 사실 범위) / ~52% (v9.4a 기준, L1~L6 전체 범위, Neptune 포함)

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
> **⚠️ 실행 주의:** 반드시 **새 세션(fresh context)**에서 실행할 것. 1~5번 생성 후 같은 세션에서 하면 context 부족으로 과도한 압축 발생.

```
v{N} 폴더의 5개 문서를 직접 읽고 통합 N1B0 HDD 문서를 만들어줘:
- v{N}/v{N}_chip_no_grounding.md
- v{N}/v{N}_chip_grounded.md
- v{N}/v{N}_edc.md
- v{N}/v{N}_noc.md
- v{N}/v{N}_overlay.md

규칙:
1. 중복 제거하되, 테이블/코드블록은 가장 상세한 버전을 유지
2. 섹션 순서는 정답지(N1B0_NPU_HDD_v0.1.md) 기준
3. 각 섹션의 출처(어떤 토픽 검색에서 왔는지)를 Appendix에 기록
4. trinity_router는 N1B0에서 인스턴스화되지 않음 (EMPTY by design). 계층에 넣지 마.

⚠️ MERGE 품질 규칙 (절대 위반 금지):
- 통합본의 줄 수는 chip_no_grounding의 80% 이상이어야 함
- topic 파일에 있는 테이블(EP Table, RISC-V Parameters, BIU Register Map 등)은 반드시 통합본에 포함
- topic 파일에 있는 ASCII 다이어그램(Endpoint Map, Module Hierarchy, Ring Topology)은 그대로 포함
- "Known Gaps" 섹션을 문서 끝에 포함하여 KB에 없는 정보를 명시
- 절대 "see that file"로 다른 파일 참조하지 말 것 — 통합본 하나로 완결되어야 함
```

---

## RAG 검증 프레임워크 (v2.1)

### 배경

- Trinity는 외부 IP RTL이며, 설계 스펙 문서가 없음
- RAG 시스템의 목표는 **RTL 역분석(reverse engineering) 자동화/가속화**
- 정답지(`N1B0_NPU_HDD_v0.1.md`)는 엔지니어가 RTL을 직접 읽고 작성한 결과물
- 측정 기준은 **입력 소스별로 분리**하여 버전 간 일관된 비교를 보장

---

### 측정 계층 정의 (L1~L6)

| 계층 | 이름 | 입력 소스 | 자동 추출 | 측정 대상 | 예시 |
|------|------|----------|-----------|-----------|------|
| **L1** | 구조 (Hierarchy) | RTL instantiation | ✅ 완전 자동 | 모듈 트리, 인스턴스 수, depth, generate block | `trinity → tt_tensix_with_l1 → u_l1part` |
| **L2** | 인터페이스 (Ports) | RTL port/wire 선언 | ✅ 완전 자동 | 포트 리스트, 비트폭, 방향, 배열 차원 | `i_edc_apb_psel[3:0]`, `output [55:0] o_axi_addr` |
| **L3** | 연결 (Connectivity) | RTL port binding | ✅ 완전 자동 | 신호 연결 관계, expression, offset | `.i_noc_endpoint_id(EndpointIndex - 1)` |
| **L4** | 파라미터 (Parameters) | RTL parameter/localparam/define | ✅ 파서 확장 필요 | 수치, 설정값, enum 매핑 | `AXI_SLV_OUTSTANDING_READS=64`, `MAX_FRGS=12` |
| **L5** | 동작 추론 (Behavior) | RTL always/assign + 패턴 매칭 | ⚠️ 부분 자동 | FSM 상태, mux 로직, 프로토콜 패턴, 카운터 | EDC ring protocol, VC arbitration FSM |
| **L6** | 설계 의도 (Intent) | 엔지니어 해석 / 외부 문서 | ❌ 수동 | "왜" 이렇게 만들었는가, 트레이드오프, SW 가이드 | "N1B0에서 trinity_router를 제거한 이유" |

---

### 계층별 측정 방법

#### L1 구조 — Module Hierarchy Coverage

```
측정 = (RAG가 정확히 기술한 인스턴스 수) / (정답지에 기술된 인스턴스 수)
```

확인 항목:
- [ ] Top module 식별 정확성
- [ ] Depth 1~3 서브모듈 완전성
- [ ] Generate block 이름 포함 여부
- [ ] 인스턴스 개수 (예: 12 Tensix, 4 Dispatch)
- [ ] "인스턴스화되지 않음" 정보 (예: trinity_router = EMPTY)

#### L2 인터페이스 — Port/Wire Accuracy

```
측정 = (정확한 포트 기술 수) / (정답지 포트 총 수)
정확 = 이름 + 방향 + 비트폭 + 배열 차원 모두 일치
```

확인 항목:
- [ ] 포트 이름 정확성
- [ ] 방향 (input/output/inout)
- [ ] 비트폭 (단일 비트 vs 벡터)
- [ ] 배열 차원 보존 (`[3:0]`, `[SizeX][SizeY-1][2]`)
- [ ] struct 필드 분해

#### L3 연결 — Connectivity Accuracy

```
측정 = (정확한 연결 기술 수) / (정답지 연결 총 수)
정확 = source + destination + expression 모두 일치
```

확인 항목:
- [ ] Port binding 정확성 (`.port(signal)`)
- [ ] Expression 연산 포함 여부 (`±1`, bit slice)
- [ ] Signal path 추적 가능성
- [ ] Clock/Reset 연결 정확성

#### L4 파라미터 — Parameter Extraction Rate

```
측정 = (추출된 파라미터 수) / (정답지에 기술된 파라미터 수)
```

확인 항목:
- [ ] Top module parameter
- [ ] Package localparam/enum
- [ ] `define` 매크로 값
- [ ] 파라미터 override (인스턴스별 #(.PARAM(value)))

#### L5 동작 추론 — Behavioral Pattern Detection

```
측정 = (정확히 식별된 동작 패턴 수) / (정답지에 기술된 동작 패턴 수)
```

확인 항목:
- [ ] FSM 상태 식별
- [ ] 프로토콜 패턴 (handshake, ring, arbitration)
- [ ] 카운터/타이머 동작
- [ ] Mux/Demux 선택 조건

#### L6 설계 의도 — (수동 평가, 자동화 대상 아님)

```
측정 = 엔지니어 리뷰로만 판단
```

확인 항목:
- [ ] 아키텍처 결정 이유
- [ ] 트레이드오프 설명
- [ ] SW/FW 프로그래밍 가이드
- [ ] 성능/면적 고려사항

---

### 버전별 점수 기록 형식

| 버전 | L1 구조 | L2 인터페이스 | L3 연결 | L4 파라미터 | L5 동작 | L6 의도 | 비고 |
|------|---------|-------------|---------|------------|---------|---------|------|
| v9.1 | 72% | 68% | 55% | 20% | 15% | 0% | EP Table 추가 |
| v9.2 | 76% | 74% | 60% | 22% | 18% | 0% | Dispatch wire, Flit 4D |
| v9.3 | 82% | 78% | 70% | 30% | 25% | 5% | Port Binding 추가 |
| v9.4 | 84% | 80% | 72% | 35% | 25% | 5% | Neptune 없이, 인덱싱+PBT 기반 |
| **v9.4a** | **88%** | **82%** | **78%** | **38%** | **28%** | **5%** | **Neptune Graph DB 추가. L1/L3 대폭 개선** |

> **주의:** v9.1~v9.3 점수는 이전 리뷰에서 역산한 추정치. v9.4부터 이 프레임워크로 정식 측정.

---

### 입력 소스별 기여 매핑

어떤 소스가 어떤 계층에 기여하는지:

| 입력 소스 | L1 | L2 | L3 | L4 | L5 | L6 |
|----------|----|----|----|----|----|----|
| RTL Hierarchy (instantiation tree) | ●● | · | · | · | · | · |
| RTL Port/Wire 선언 | · | ●● | · | · | · | · |
| RTL Port Binding | · | · | ●● | · | · | · |
| RTL Parameter/Package | · | · | · | ●● | · | · |
| RTL always/assign 블록 | · | · | · | · | ●● | · |
| Neptune Graph DB | ● | · | ●● | · | · | · |
| Spec RAG (설계 문서) | · | · | · | ● | ● | ●● |
| 엔지니어 수동 Claim | · | · | · | ● | ● | ●● |

`●●` = 주요 기여, `●` = 보조 기여, `·` = 기여 없음

---

### 치명적 오류 분류

| 등급 | 정의 | 예시 |
|------|------|------|
| **Critical** | 사실과 반대되는 기술 | "East handles columns 0-1" (실제: East=X=3) |
| **Major** | 핵심 구조 누락 | EDC per-column ring을 1개 ring으로 기술 |
| **Minor** | 세부 수치 오류 | 배열 차원 `[3:0]` 누락 |
| **Cosmetic** | 표현/포맷 문제 | 섹션 순서 불일치 |

버전별 오류 카운트:

| 버전 | Critical | Major | Minor | Cosmetic |
|------|----------|-------|-------|----------|
| v9.3 | 2 | 4 | 3 | 다수 |
| v9.4 | 1 | 2 | 2 | 다수 |
| **v9.4a** | **0** | **1** | **2** | **다수** |

---

### 엔지니어 논의 필요 사항

1. **L5 동작 추론의 범위**: RTL always 블록에서 FSM/프로토콜을 자동 추출하는 게 현실적인가? 어디까지 자동화하고 어디부터 수동 claim으로 넣을 것인가?
2. **정답지 갱신**: 현재 정답지가 "완벽한 정답"인지, 아니면 정답지 자체도 업데이트가 필요한지?
3. **측정 주기**: 매 버전마다 전체 L1~L6를 측정할 것인지, 변경된 계층만 측정할 것인지?
4. **Neptune 기여도 실측**: v9.4 vs v9.4a 비교로 Neptune이 실제로 L3 연결 정확도를 얼마나 올리는지 정량화

---

## 검증 체크리스트 (기존)

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
| v9.3 | 5/12 | Port Binding + 6건 치명적 오류 식별 | L1:82% L2:78% L3:70% |
| v9.4 | 5/14 | 재인덱싱 + 오류 수정 + PBT 검증 (Neptune 없이) | L1:84% L3:72% |
| **v9.4a** | **5/18** | **Neptune Graph DB 추가. 10건 신규 hierarchy 발견. Critical 오류 0** | **L1:88% L3:78%** |

---

## 피드백 방법

가장 도움이 되는 피드백:

```
[프롬프트 N번 결과 관련]
- 정답지 섹션 X에 있는 <내용>이 RAG 결과에 없다
- 또는: RAG 결과의 <내용>이 틀렸다. 정확한 값은 <정답>이다
- 또는: 이 부분은 RTL의 <파일명>을 보면 알 수 있다
```




