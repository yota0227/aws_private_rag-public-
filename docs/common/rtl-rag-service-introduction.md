# RTL RAG 서비스 소개 및 활용 가이드

**문서 ID:** BOS-AI-GUIDE-RTL-RAG-SERVICE-INTRO-001  
**작성일:** 2026-06-04  
**대상:** RTL 설계, DV, DFT, Firmware, SoC Integration, Architecture 엔지니어  

---

## 1. 서비스 소개

RTL RAG는 사내 RTL 코드, 설계 문서, firmware 자료, register map, generated HDD, graph database를 검색하고 연결해서 엔지니어가 설계 구조를 빠르게 이해하도록 돕는 AI 기반 RTL 지식 검색 서비스입니다.

이 서비스의 목표는 AI가 RTL을 상상해서 설명하는 것이 아닙니다. 목표는 명확합니다.

> **RTL source와 graph evidence를 기반으로, 설계자가 확인해야 하는 module, port, signal, instance, clock/reset, NoC, EDC, DFX, firmware 정보를 빠르게 찾아주는 것.**

기존 문서 검색은 키워드가 맞지 않으면 놓치기 쉽고, RTL 코드는 module hierarchy와 signal connection을 사람이 따라가야 해서 시간이 오래 걸립니다. RTL RAG는 다음 정보를 함께 사용합니다.

| 정보원 | 역할 |
|---|---|
| RTL source | module, port, parameter, instance, signal declaration의 원본 |
| Parsed RTL JSON | parser가 추출한 구조화 정보 |
| Vector DB | 자연어/키워드 기반 검색 |
| Neptune Graph | module hierarchy, instance, `CONNECTS_TO` 관계 |
| Claim DB | 검증된 설계 claim과 근거 |
| Generated HDD | topic별 설계 요약 문서 |
| Schematic Map | chip/module/signal 구조를 시각적으로 이해하기 위한 map |

---

## 2. 이 서비스를 쓰면 좋은 상황

RTL RAG는 다음 업무에서 특히 효과적입니다.

| 업무 | 활용 예 |
|---|---|
| 신규 블록 온보딩 | "이 module이 전체 chip에서 어디에 붙어 있는가?" |
| RTL 리뷰 | "이 port가 실제로 어떤 instance에 연결되는가?" |
| DV plan 작성 | "검증해야 할 interface, reset, interrupt, register가 무엇인가?" |
| Debug | "이 signal이 어디서 생성되고 어디까지 전달되는가?" |
| DFT/CDC 검토 | "clock domain crossing 또는 DFX wrapper가 어디에 있는가?" |
| Firmware bring-up | "register, interrupt, command buffer, device tree 정보가 어디 있는가?" |
| HDD 작성 | "NoC, EDC, DFX, Overlay section 초안을 evidence 기반으로 생성" |
| 설계 변경 영향도 분석 | "이 module 변경 시 영향을 받는 상위/하위 module은 무엇인가?" |
| 코드 인수인계 | "정답 문서가 없을 때 현재 RTL 기준 구조 요약 생성" |

---

## 3. 중요한 사용 원칙

RTL RAG는 매우 강력하지만, 좋은 결과를 얻으려면 질문을 잘 해야 합니다.

### 3.1 pipeline_id를 고정하세요

RTL은 snapshot마다 구조가 달라질 수 있습니다. 반드시 어떤 RTL 버전을 보고 싶은지 지정하세요.

좋은 예:

```text
pipeline_id=tt_20260516 기준으로 trinity top의 NOC2AXI tile 구성을 찾아줘.
정답처럼 단정하지 말고, RTL evidence와 함께 보여줘.
```

나쁜 예:

```text
trinity 구조 알려줘.
```

### 3.2 "근거와 함께"라고 요청하세요

RTL RAG의 가장 중요한 가치는 답변 자체가 아니라 답변의 근거입니다.

좋은 예:

```text
search_rtl과 find_instantiation_tree를 사용해서
trinity_noc2axi_router_ne_opt가 어떤 하위 module을 instantiate하는지 찾아줘.
각 항목마다 file path, line, evidence type을 붙여줘.
```

### 3.3 모르면 모른다고 답하게 하세요

AI가 추측하지 않도록 질문에 다음 문장을 넣는 것이 좋습니다.

```text
근거가 없는 내용은 추정하지 말고 "현재 index에서 확인 불가"라고 표시해줘.
```

### 3.4 용도를 말하세요

같은 정보라도 DV, 설계 리뷰, firmware bring-up에서 필요한 형태가 다릅니다.

예:

```text
DV plan 작성용으로 정리해줘.
각 interface별로 check item, expected behavior, 필요한 evidence를 표로 만들어줘.
```

---

## 4. Codex CLI에서 MCP로 사용하는 방법

Codex CLI에서 BOS-AI RAG MCP 서버가 연결되어 있으면 자연어로 도구를 호출할 수 있습니다. 질문할 때 도구명을 직접 언급하면 더 안정적입니다.

사용 가능한 주요 MCP 도구:

| 도구 | 언제 쓰나 |
|---|---|
| `rag_query` | 넓은 자연어 질문, 요약 질문 |
| `search_rtl` | RTL/source/firmware/register 문서 검색 |
| `trace_signal_path` | 특정 signal의 연결 경로 추적 |
| `find_instantiation_tree` | module hierarchy 확인 |
| `find_clock_crossings` | CDC 후보 검색 |
| `graph_export` | Neptune graph를 JSON으로 export |
| `get_evidence` | claim의 source 근거 조회 |
| `list_verified_claims` | topic별 검증된 claim 목록 조회 |
| `generate_hdd_section` | HDD section 초안 생성 |

---

## 5. 추천 프롬프트 패턴

### 5.1 구조를 처음 파악할 때

```text
pipeline_id=tt_20260516 기준으로 trinity top 구조를 설명해줘.

반드시 MCP 도구를 사용해줘:
1. search_rtl로 trinity_pkg, trinity.sv, GridConfig 관련 정보를 검색
2. find_instantiation_tree로 trinity depth=2 hierarchy 확인
3. 가능하면 graph_export로 chip-level graph 확인

출력은 다음 형태로 정리해줘:
- grid 구성
- 주요 tile type과 개수
- top-level module hierarchy
- 확인된 evidence
- 현재 index에서 확인 불가한 항목
```

### 5.2 특정 module을 분석할 때

```text
pipeline_id=tt_20260516 기준으로 module=tt_noc2axi를 분석해줘.

search_rtl과 find_instantiation_tree를 사용해서:
- port list
- parameter
- submodule instance
- clock/reset domain
- AXI/NoC/EDC interface
- 관련 file path
를 표로 정리해줘.

근거 없는 기능 설명은 하지 말고, 확인된 RTL evidence만 "확정"으로 표시해줘.
```

### 5.3 signal path를 추적할 때

```text
pipeline_id=tt_20260516 기준으로 signal=npu_out_araddr 경로를 trace_signal_path로 추적해줘.

출력 형식:
- source module / source port
- intermediate instance / signal
- destination module / destination port
- CONNECTS_TO edge evidence
- 끊긴 지점 또는 미확인 지점

연결 근거가 없는 추정 경로는 제외해줘.
```

### 5.4 정답지와 비교할 때

```text
정답지 N1B0_HDD_v0.1.md와 pipeline_id=tt_20260516 검색 결과를 비교해줘.

특히 다음 항목을 확인해줘:
- top-level port count
- SFR_* port 실명
- PRTNUN_* 및 ISO_EN presence
- NOC2AXI_ROUTER_NE/NW_OPT 존재 여부
- trinity_router standalone instance 여부
- EDC ring topology
- DFX wrapper chain

각 항목을 "일치 / 불일치 / snapshot 차이 가능 / 현재 index에서 확인 불가"로 분류해줘.
```

### 5.5 DV plan으로 바꿀 때

```text
pipeline_id=tt_20260516 기준으로 EDC subsystem을 DV plan 작성용으로 정리해줘.

MCP로 search_rtl, list_verified_claims, get_evidence를 사용해줘.

출력:
- 검증 대상 interface
- register / IRQ 목록
- 정상 시나리오
- error injection 시나리오
- harvest bypass 관련 check
- 필요한 waveform signal
- evidence file path
```

### 5.6 설계 변경 영향도를 볼 때

```text
pipeline_id=tt_20260516에서 module=trinity_noc2axi_n_opt 변경 영향도를 분석해줘.

find_instantiation_tree와 graph_export를 사용해서:
- 이 module을 instantiate하는 상위 module
- 연결된 NoC/AXI/EDC interface
- 관련 clock/reset
- 영향을 받을 가능성이 있는 generated HDD section
- DV regression 추천 항목
을 정리해줘.
```

### 5.7 HDD 초안을 만들 때

```text
pipeline_id=tt_20260516 기준으로 topic=NoC에 대한 HDD section 초안을 generate_hdd_section으로 만들어줘.

조건:
- 모든 확정문에는 evidence를 붙여줘.
- [FROM LLM] 추론은 별도 섹션에 넣고 본문 확정문처럼 쓰지 마.
- Known gaps를 마지막에 정리해줘.
- DV/architecture review에서 바로 쓸 수 있게 table 중심으로 작성해줘.
```

---

## 6. 좋은 질문과 나쁜 질문

| 나쁜 질문 | 왜 안 좋은가 | 좋은 질문 |
|---|---|---|
| "NoC 설명해줘" | 범위와 RTL snapshot이 불명확함 | "`pipeline_id=tt_20260516`의 NoC fabric을 search_rtl로 찾아, routing/VC/repeater/ATT로 나눠 evidence와 정리해줘" |
| "이거 맞아?" | 비교 기준이 없음 | "정답지 `N1B0_HDD_v0.1.md`의 NOC2AXI_ROUTER 구조와 현재 RTL evidence를 비교해줘" |
| "trinity 구조 다 알려줘" | 너무 넓어 요약 환각 위험이 커짐 | "trinity top depth=2 hierarchy와 GridConfig만 먼저 확인해줘" |
| "DFX 찾아줘" | module/범위/목적이 없음 | "N1B0 DFX wrapper chain 4개가 현재 RTL index에서 확인되는지 찾아줘" |
| "HDD 만들어줘" | evidence gate가 약함 | "topic=EDC HDD section을 만들되, evidence 없는 claim은 Known gaps로 보내줘" |

---

## 7. 업무별 활용 방법

### 7.1 RTL 설계자

활용:

- 내 module이 상위 top에서 어떻게 instantiate되는지 확인
- port rename 또는 parameter 변경 영향도 확인
- 기존 HDD와 현재 RTL 차이 확인
- schematic map으로 리뷰 자료 준비

추천 질문:

```text
내가 수정한 module=OOO가 pipeline_id=tt_20260516에서 어디에 instantiate되는지 찾아줘.
상위 3 depth까지 보여주고, 연결된 clock/reset/interrupt/sfr interface를 같이 정리해줘.
```

### 7.2 DV 엔지니어

활용:

- interface checklist 생성
- register/IRQ/error status 기반 testcase 도출
- reset/clock/CDC 검증 포인트 정리
- 기존 spec과 RTL mismatch 찾기

추천 질문:

```text
module=OOO에 대해 DV checklist를 만들어줘.
port, register, interrupt, reset, clock, error path를 evidence 기반으로 분류하고
각 항목별 recommended testcase를 제안해줘.
```

### 7.3 DFT 엔지니어

활용:

- scan/MBIST/DFX wrapper 관련 module 검색
- DFT mode port 확인
- DFX wrapper chain 확인
- DFTed RTL과 functional RTL 차이 후보 파악

추천 질문:

```text
pipeline_id=tt_20260516에서 DFX wrapper chain을 찾아줘.
tt_noc_niu_router_dfx, tt_overlay_wrapper_dfx, tt_instrn_engine_wrapper_dfx, tt_t6_l1_partition_dfx가
어디에서 instantiate되는지 evidence와 함께 정리해줘.
```

### 7.4 Firmware 엔지니어

활용:

- register map, IRQ, command buffer, device tree 검색
- firmware API와 RTL register 연결 확인
- bring-up sequence 초안 생성

추천 질문:

```text
EDC 관련 firmware bring-up에 필요한 register, IRQ, status bit, device-tree 정보를 찾아줘.
RTL/source/firmware 문서 evidence를 분리해서 보여주고,
초기화 순서를 제안해줘.
```

### 7.5 SoC Integration 엔지니어

활용:

- top-level port와 external interface 확인
- AXI/APB/clock/reset 연결 검토
- IP integration checklist 작성
- snapshot 간 port diff 확인

추천 질문:

```text
pipeline_id=tt_20260516의 trinity top-level port를 category별로 정리해줘.
AXI, APB, EDC, SFR, PRTN, clock/reset으로 나누고,
정답지와 count mismatch가 있는지 확인해줘.
```

### 7.6 Architecture / Tech Lead

활용:

- 전체 구조 파악
- topic별 HDD 초안 리뷰
- 설계 변경 리스크 판단
- onboarding 자료 생성

추천 질문:

```text
N1B0 NoC/EDC/DFX/Overlay 구조를 architecture review용 1-page summary로 만들어줘.
확정 evidence와 추정/미확인 항목을 분리하고,
리뷰 회의에서 물어봐야 할 open question을 뽑아줘.
```

---

## 8. 산출물을 업무에 활용하는 방법

RTL RAG 결과는 그대로 최종 결론으로 복사하기보다, 다음 방식으로 활용하는 것을 권장합니다.

### 8.1 리뷰 전 사전 조사

RAG로 module hierarchy, port, signal path를 먼저 뽑고 회의 전에 open question을 줄입니다.

결과물:

- module summary
- signal path table
- unresolved evidence list
- 설계자에게 확인할 질문 목록

### 8.2 DV plan 초안

RAG가 뽑은 port/register/IRQ/error path를 기반으로 testcase skeleton을 만듭니다.

결과물:

- interface checklist
- register access testcase
- error injection testcase
- reset/clock sequence testcase
- coverage item 초안

### 8.3 HDD 작성

RAG가 생성한 HDD section을 초안으로 사용하고, 설계자가 source evidence를 확인해 sign-off합니다.

권장 flow:

```text
RAG section 생성
  -> evidence 없는 문장 제거
  -> 설계자 review
  -> 정답지/HDD에 반영
  -> stale HDD regeneration 대상 등록
```

### 8.4 Debug

특정 signal, register, interrupt가 어디서 끊기는지 찾을 때 trace 결과를 사용합니다.

결과물:

- source/destination path
- intermediate instance
- clock domain
- unresolved connection
- waveform probe 후보

### 8.5 설계 변경 영향도 분석

module 또는 port 변경 전에 영향을 받는 hierarchy와 generated document를 확인합니다.

결과물:

- affected module list
- affected top port/interface
- affected HDD section
- recommended regression
- owner/team follow-up

---

## 9. 결과를 읽을 때의 신뢰도 기준

답변을 볼 때 다음 기준으로 신뢰도를 판단하세요.

| 표시 | 의미 | 업무 사용 |
|---|---|---|
| source file + line 있음 | RTL 원문 근거 있음 | 높은 신뢰 |
| Neptune edge 있음 | graph로 hierarchy/connection 확인 | 높은 신뢰 |
| verified claim 있음 | Claim DB에 검증된 사실 | 높은 신뢰 |
| vector search only | 관련 문맥은 찾았지만 구조 확정은 약함 | 추가 확인 필요 |
| `[FROM LLM]` | AI 해석 또는 요약 | 확정 사실로 사용 금지 |
| `현재 index에서 확인 불가` | 검색/graph에서 근거 없음 | 설계자 확인 필요 |

중요한 sign-off 자료에는 반드시 file path, line, claim ID, graph edge 중 하나 이상의 evidence가 있어야 합니다.

---

## 10. 한계와 주의사항

RTL RAG는 설계 검토를 빠르게 해주는 도구이지, RTL sign-off를 대체하지 않습니다.

주의사항:

- 다른 `pipeline_id`의 결과를 섞으면 잘못된 결론이 나올 수 있습니다.
- Neptune graph가 미적재된 snapshot은 hierarchy와 signal path 정확도가 낮아질 수 있습니다.
- `[FROM LLM]` 문장은 확정 사실이 아닙니다.
- source line이 없는 module hierarchy는 반드시 재확인해야 합니다.
- generated HDD는 초안입니다. 설계 owner review가 필요합니다.
- security/IP 정책상 외부 서비스에 RTL 내용을 복사하지 마세요.

---

## 11. 추천 사용 흐름

처음 사용하는 사용자는 다음 순서로 접근하면 좋습니다.

```text
1. pipeline_id 확인
2. module 또는 topic 범위 지정
3. search_rtl로 관련 source 검색
4. find_instantiation_tree 또는 trace_signal_path로 구조 확인
5. get_evidence/list_verified_claims로 근거 확인
6. 필요한 경우 generate_hdd_section으로 문서 초안 생성
7. Known gaps와 open question 정리
8. 설계/DV/DFT/FW owner와 최종 확인
```

---

## 12. 바로 써볼 수 있는 첫 질문

### Chip 구조

```text
pipeline_id=tt_20260516 기준으로 trinity chip 구조를 설명해줘.
search_rtl, find_instantiation_tree, graph_export를 사용하고,
확인된 evidence와 미확인 항목을 분리해줘.
```

### Port 확인

```text
pipeline_id=tt_20260516 기준으로 trinity top-level ports를 category별로 정리해줘.
SFR, PRTN, ISO_EN, AXI, EDC_APB, clock/reset을 반드시 포함하고,
각 category의 count와 source evidence를 보여줘.
```

### Signal 추적

```text
pipeline_id=tt_20260516에서 signal=npu_out_araddr를 trace_signal_path로 추적해줘.
근거 없는 연결은 제외하고, 끊긴 지점은 unresolved로 표시해줘.
```

### HDD 생성

```text
pipeline_id=tt_20260516, topic=EDC로 HDD section 초안을 만들어줘.
generate_hdd_section을 사용하고, 모든 claim에 evidence를 붙여줘.
[FROM LLM] 내용은 별도 추정 섹션으로 분리해줘.
```

### 정답지 비교

```text
pipeline_id=tt_20260516 산출물을 N1B0_HDD_v0.1.md 정답지와 비교해줘.
일치/불일치/snapshot 차이 가능/현재 index에서 확인 불가로 분류하고,
다음 액션을 추천해줘.
```

---

## 13. 우리가 기대하는 사용 방식

이 서비스는 질문 한 번으로 정답을 받는 챗봇이 아닙니다. 엔지니어가 더 빨리, 더 넓게, 더 근거 있게 설계를 이해하도록 돕는 RTL investigation assistant입니다.

가장 좋은 사용 방식은 다음과 같습니다.

```text
검색한다
  -> 근거를 확인한다
  -> 모르는 항목을 분리한다
  -> 업무 산출물로 변환한다
  -> owner와 최종 확인한다
```

RTL RAG가 잘하는 일은 "근거 후보를 빠르게 모으는 것"입니다. 엔지니어가 잘하는 일은 "그 근거를 바탕으로 설계적 판단을 내리는 것"입니다. 두 역할을 분리할 때 가장 좋은 결과가 나옵니다.

