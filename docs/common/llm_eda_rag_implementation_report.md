# LLM-for-EDA 논문 기반 Code RAG 구현 검토 보고서

**작성 목적:**  
공유된 4개 논문을 기반으로, 현재 진행 중인 **Code의 RAG / Trinity·N1B0 RTL 문서 RAG / EDA Copilot** 구현 방향을 정리한다.  
본 문서는 Kiro와 실제 구현 범위, 산출물, 우선순위, 평가 기준을 논의하기 위한 실행 보고서이다.

---

## 1. 검토 배경

현재 프로젝트는 NPU RTL 코드 및 HDD 문서를 대상으로 RAG 기반 분석 시스템을 구축하는 방향으로 진행 중이다.  
주요 대상은 다음과 같다.

| 구분 | 내용 |
|---|---|
| 대상 도메인 | Trinity / N1B0 RTL, HDD, hierarchy, performance, DV, NoC/AXI, EDC, Overlay, Tensix |
| 목표 | RTL/HDD 기반 Architecture QA, RTL locate, DV artifact generation, performance debug, 향후 PD/timing debug 확장 |
| 호출 방식 | RAG MCP 또는 MCP 기반 tool 호출 구조 |
| 구현 논의 대상 | Kiro와 함께 구현할 RAG schema, agent workflow, evaluation set, traceability artifact |

이번에 검토한 논문 4개는 다음과 같다.

| No | 논문/자료 | 본 프로젝트에서의 해석 |
|---:|---|---|
| 1 | **ChipMnd: LLMs for Agile Chip Design** | EDA multi-agent orchestration 설계 기준 |
| 2 | **LLM for EDA in Front-End Design: Challenges and Opportunities** | Front-end RAG, semantic consistency, spec-to-RTL traceability 기준 |
| 3 | **FIXME: Towards End-to-End Benchmarking of LLM-Aided Design Verification** | DV benchmark 및 evaluation harness 설계 기준 |
| 4 | **NVIDIA LLM-Enhanced GPU-Optimized Physical Design at Scale** | Backend PD / STA / PPA optimization 확장 기준 |

---

## 2. 핵심 결론

4개 논문을 하나로 뭉쳐서 적용하면 구현 방향이 흐려진다.  
따라서 논문별 역할을 다음과 같이 분리해야 한다.

```text
ChipMnd
= 전체 EDA Copilot의 agent orchestration 참고 자료

TUM LLM4EDA
= Front-end spec/HDD/RTL semantic RAG 설계 기준

FIXME
= DV task taxonomy와 evaluation harness 설계 기준

NVIDIA LEGO-PD
= Backend timing/PPA optimization loop 확장 기준
```

현 단계에서 가장 먼저 구현해야 할 것은 **TUM + FIXME 기반 산출물**이다.

```text
1순위: Front-end RAG schema / traceability / semantic consistency
2순위: DV benchmark / answer quality evaluation
3순위: Agent orchestration
4순위: Backend PD / STA / PPA optimization 확장
```

즉, 당장 목표는 “LLM이 RTL을 자동 생성한다”가 아니다.  
먼저 다음을 달성해야 한다.

1. HDD/spec/RTL/hierarchy를 정확히 연결하는 RAG 구조
2. RAG 답변이 실제 DV 업무에 쓸 수 있는지 평가하는 benchmark
3. 질문 유형별 agent/tool routing 구조
4. 향후 STA/P&R report까지 확장 가능한 artifact schema

---

## 3. 현재 보유 문서와 적용 가능성

현재 프로젝트에는 이미 Trinity/N1B0 관련 HDD와 hierarchy 문서가 다수 존재한다.  
이 문서들은 단순 요약 대상이 아니라 RAG index 및 evaluation set의 원천 데이터로 사용해야 한다.

| 문서 그룹 | 주요 파일 예 | 활용 방향 |
|---|---|---|
| N1B0 top / variant | `N1B0_HDD_v0.1.md`, `N1B0_NPU_HDD_v0.1.md`, `trinity_HDD_v3.0.md` | Baseline Trinity 대비 N1B0 delta, tile map, endpoint index, variant reasoning |
| Hierarchy | `trinity_full_hierarchy.md`, `trinity_hierarchy.csv`, `overlay_hierarchy.csv` | module path, instance path, memory inventory, grid-aware retrieval |
| NOC2AXI / Router | `N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md`, `router_decode_HDD_v0.5.md`, `NIU_HDD_v0.1.md` | NoC/AXI bridge, dynamic routing, ATT, composite tile 구조 QA |
| Performance | `N1B0_PerfMonitor_HDD_v0.1.md`, `SW_Performance_Guide_HDD_V0.1.md` | latency monitor, performance debug assistant, bottleneck diagnosis |
| DV/Test infra | `N1B0_AXI_Dynamic_Delay_HDD_v0.1.md`, `N1B0_PerfMonitor_HDD_v0.1.md` | SVA/TB/reference model generation benchmark |
| Overlay/Tensix | `overlay_HDD_v0.3.md`, `tensix_core_HDD.md`, `INT16_Guide_HDD_V0.1.md` | compute pipeline, L1, TRISC/BRISC, SW-HW mapping |
| EDC/DFX/Harvest | `EDC_HDD_V0.3.md`, `EDC_path_V0.2.md`, `N1B0_DFX_HDD_v0.1.md`, `Harvest_HDD.md` | diagnostic path, ring topology, DFX simplification, harvest-aware behavior |
| Physical/P&R | `trinity_par_guide.md` | 향후 PD/timing report RAG 확장 |

중요한 점은 “문서가 부족한 것”이 아니라, **문서 간 의미 연결과 평가셋이 아직 부족하다**는 것이다.

---

## 4. 논문별 적용 태스크 분리

## 4.1 Paper 1 — ChipMnd

### 역할

ChipMnd는 개별 RAG 검색보다는 **EDA workflow를 agent/module 단위로 나누는 구조**에 가깝다.  
본 프로젝트에서는 다음 질문에 답하는 기준으로 사용한다.

```text
우리는 어떤 EDA task를 어떤 agent에게 맡길 것인가?
```

### 산출물이 되어야 하는 것

| 산출물 | 설명 | 구현 관점 |
|---|---|---|
| EDA Agent Role Matrix | Architecture Agent, RTL Agent, DV Agent, Performance Agent, PD Agent 역할 정의 | 질문 유형별 책임 분리 |
| Agent Routing Policy | 질문을 어느 agent/tool/RAG index로 보낼지 결정하는 정책 | MCP tool routing 또는 internal router 구현 |
| Tool Contract Spec | 각 agent가 사용할 수 있는 tool과 금지 tool 정의 | read-only, generation, simulation, patch suggestion 권한 구분 |
| Human Approval Policy | 자동 응답 가능 / 사람 검토 필요 / 자동 실행 금지 영역 정의 | RTL patch, ECO, assertion insertion 등 위험도 관리 |
| End-to-End Workflow DAG | 질문 → 검색 → evidence 수집 → artifact 생성 → 평가 흐름 | Kiro 구현용 workflow graph |

### 구현 메모

Agent는 처음부터 복잡하게 만들 필요 없다.  
초기에는 **router + task-specific prompt + RAG collection 선택** 정도로 시작하는 것이 현실적이다.

```text
질문 유형 분류
  ├─ architecture / hierarchy → Architecture Agent
  ├─ module / signal / interface → RTL Agent
  ├─ SVA / TB / debug → DV Agent
  ├─ latency / bandwidth / bottleneck → Performance Agent
  └─ STA / timing / PPA → PD Agent, 후순위
```

---

## 4.2 Paper 2 — TUM LLM4EDA

### 역할

TUM LLM4EDA는 본 프로젝트의 **Front-end RAG 설계 기준**이다.  
핵심은 단순 문서 검색이 아니라, spec/HDD/RTL/verification 간 semantic consistency를 유지하는 것이다.

```text
문서 조각을 검색하는 것이 아니라,
spec → RTL → signal/interface → verification item까지 연결할 수 있어야 한다.
```

### 산출물이 되어야 하는 것

| 산출물 | 설명 | 구현 관점 |
|---|---|---|
| RAG Metadata Schema | chunk마다 chip, block, module, grid, interface, task_type 등 metadata 부여 | vector DB metadata filtering |
| Spec-to-RTL Traceability Matrix | HDD 설명 ↔ RTL module ↔ signal/interface ↔ verification item 연결 | CSV/JSONL 기반 retrievable artifact |
| Design Intent Index | 각 모듈의 목적, 제약, non-goal, variant 차이 구조화 | design intent retrieval |
| Variant Delta Matrix | Baseline Trinity와 N1B0 차이점 비교 | N1B0 질문 정확도 향상 |
| Consistency Check Rule Set | HDD/hierarchy/RTL 설명 간 불일치 탐지 규칙 | ingestion validation 또는 offline checker |
| RAG Chunking Guideline | 문서를 어떤 단위로 쪼갤지 정의 | section chunk가 아니라 module/interface/behavior chunk 중심 |

### 권장 Metadata Schema 초안

```yaml
chip: Trinity | N1B0
variant: baseline | n1b0
source_file: string
source_section: string
block: Tensix | Overlay | NIU | Router | NOC2AXI | EDC | DFX | Performance | PD
module: string
rtl_file: string | null
instance_path: string | null
grid_x: int | null
grid_y: int | null
endpoint_id: int | null
clock_domain: ai_clk | noc_clk | dm_clk | ref_clk | aon_clk | mixed | unknown
synthesizable: yes | no | unknown
interface_type: AXI | NoC | APB | EDC | SMN | clock_reset | memory | none
task_type: architecture | rtl_locate | verify | debug | performance | pd | programming
confidence: high | medium | low
```

### 적용 예시

N1B0에서는 middle column의 `trinity_noc2axi_n_opt + trinity_router` 조합이 `trinity_noc2axi_router_ne/nw_opt` composite tile로 대체된다.  
이 구조는 Y=4 NOC2AXI와 Y=3 router 역할이 한 module 내부에 공존하므로, 일반 chunk 검색만으로는 잘못된 답을 만들 가능성이 높다.

따라서 이 영역은 반드시 다음 metadata로 묶어야 한다.

```yaml
chip: N1B0
block: NOC2AXI/Router
module: trinity_noc2axi_router_ne_opt
physical_span: Y=4+Y=3
grid_x: 1
grid_y: 4
related_router_placeholder_y: 3
endpoint_noc2axi: 9
endpoint_router: 8
variant_delta: composite_tile_replaces_separate_niu_plus_router
```

---

## 4.3 Paper 3 — FIXME

### 역할

FIXME는 본 프로젝트의 **DV benchmark / evaluation harness 설계 기준**이다.  
RAG 답변이 그럴듯한지 보는 것이 아니라, 실제 DV artifact를 만들고 검증 가능한지 평가해야 한다.

```text
우리 RAG/LLM이 DV 업무에 쓸 만한 수준인지 어떻게 측정할 것인가?
```

### 산출물이 되어야 하는 것

| 산출물 | 설명 | 예시 |
|---|---|---|
| Spec Comprehension Test Set | HDD 내용을 제대로 이해했는지 묻는 문제 | N1B0 router placeholder가 empty인 이유 |
| Reference Model Generation Set | behavior를 pseudo-code로 만들게 하는 문제 | AXI latency monitor reference model |
| Testbench Generation Set | TB scaffold 생성 문제 | AXI delay buffer smoke test |
| SVA Generation Set | assertion/property 생성 문제 | delay_cycles busy 중 변경 금지 assertion |
| RTL Debugging Set | bug 원인 분석/패치 제안 문제 | AXI ID reuse로 latency 통계가 깨지는 경우 |
| Scoring Rubric | 정답 기준, 부분 점수, fail 조건 | signal명 정확성, synth/sim-only 구분, evidence 포함 |
| Eval Harness | 자동/반자동 평가 도구 | syntax check, keyword check, source coverage check |

### 초기 DV Evaluation Set 권장 규모

초기부터 대형 benchmark를 만들 필요는 없다.  
**30~50개 case**로 시작해도 충분하다.

| Subset | 권장 개수 | 예시 |
|---|---:|---|
| SpeCom | 10~15 | architecture/HDD 이해 문제 |
| MGen | 5~8 | reference model / pseudo-code 생성 |
| TBGen | 5~8 | SystemVerilog/Python TB scaffold 생성 |
| SVAGen | 8~10 | protocol/assertion 생성 |
| RTLFix | 5~9 | bug localization / debug explanation |

### DV Case 예시

| Case ID | Type | Question | Expected Artifact | Pass Criteria |
|---|---|---|---|---|
| SPECOM-001 | Spec comprehension | N1B0에서 `ROUTER` tile enum이 있는데 왜 RTL module이 empty인가? | 설명 답변 | composite tile 내부 embedding 언급 |
| MGEN-001 | Reference model | AXI read first-beat latency 계산 모델 작성 | pseudo-code | AR handshake → first R valid 기준 |
| TBGEN-001 | Testbench generation | `axi_dynamic_delay_buffer` zero-delay/pass-through test 작성 | SV TB scaffold | valid/ready backpressure 포함 |
| SVAGEN-001 | SVA generation | busy 상태에서 `delay_cycles` 변경 금지 property 작성 | SVA | `fifo_count != 0 |-> stable(delay_cycles)` 형태 포함 |
| RTLFIX-001 | RTL debug | 같은 AXI ID가 outstanding 중복될 때 monitor 통계가 틀어지는 원인 분석 | debug explanation | per-ID queue 또는 outstanding tracking 필요성 언급 |

---

## 4.4 Paper 4 — NVIDIA LEGO-PD

### 역할

NVIDIA LEGO-PD는 현 단계의 1차 구현 대상은 아니다.  
이 논문은 **Backend PD / STA / PPA optimization loop** 확장 기준으로 두는 것이 맞다.

```text
나중에 timing/PPA report까지 RAG/Agent로 다룰 준비를 어떻게 할 것인가?
```

### 산출물이 되어야 하는 것

| 산출물 | 설명 | 사용 시점 |
|---|---|---|
| PD Artifact Inventory | 필요한 backend artifact 목록 정의 | netlist, SDC, DEF, timing report, congestion report |
| Timing Path Data Model | timing path를 구조화된 데이터로 변환 | cell, net, slack, transition, fanout, drive strength |
| Optimization Primitive Catalog | ECO action primitive 정의 | gate sizing, buffer insertion, relocation, repeater insertion |
| STA Feedback Loop Spec | 제안 → STA 재실행 → WNS/TNS delta 평가 흐름 | recommend-only 단계 |
| Risk Classification Rule | safe/risky/forbidden suggestion 분류 | 자동 ECO 방지 |
| PD Debug Prompt Set | timing/congestion debug 질의 템플릿 | PD assistant 확장 |

### 구현 메모

현 시점에서는 PD 자동 최적화가 아니라 **PD artifact schema** 정도만 정의해 두는 것이 적절하다.  
실제 optimization loop는 STA/P&R report corpus가 충분히 쌓인 이후에 진행해야 한다.

---

## 5. 프로젝트 산출물 정의

이번 논문 검토를 통해 최종적으로 나와야 할 산출물은 “논문 요약”이 아니다.  
다음 7개가 실제 구현 논의용 산출물이다.

| No | 산출물 | 내용 | 우선순위 |
|---:|---|---|---:|
| 1 | 논문별 적용성 평가표 | 4개 논문의 목적, 적용 가능 영역, 당장/후순위 구분 | 1 |
| 2 | EDA RAG Target Task Map | Architecture QA, RTL locate, DV generation, perf debug, PD debug 분류 | 1 |
| 3 | Trinity/N1B0 RAG Metadata Schema | chip/block/module/grid/signal/interface/task_type metadata 정의 | 1 |
| 4 | Spec-to-RTL Traceability Matrix | HDD/spec ↔ RTL/module ↔ signal/interface ↔ verification item 연결 | 1 |
| 5 | N1B0 Variant Delta Matrix | baseline Trinity 대비 N1B0 차이점 정리 | 2 |
| 6 | DV Evaluation Case Set v0.1 | SpeCom/MGen/TBGen/SVAGen/RTLFix 문제 30~50개 | 2 |
| 7 | RAG Answer Quality Rubric | 근거성, 정확성, signal명, synth 여부, variant 구분 기준 | 2 |

---

## 6. EDA RAG Target Task Map

| Task Group | 사용자 질문 예 | 필요한 검색 대상 | 기대 출력 |
|---|---|---|---|
| Architecture QA | N1B0 grid 구조 설명해줘 | N1B0 HDD, hierarchy | grid, tile type, endpoint index |
| RTL Locate | 이 기능 RTL 어디에 있어? | hierarchy, HDD, RTL path index | module/file/path |
| Variant Delta | baseline과 N1B0 차이점은? | N1B0 HDD, Trinity HDD | delta matrix |
| Interface Explain | 이 module port prefix 의미가 뭐야? | module HDD, port table | interface grouping, row/clock 의미 |
| DV Generation | 이 모듈 SVA 만들어줘 | HDD, interface table | SVA + assumptions |
| TB Generation | delay buffer testbench 만들어줘 | module spec, ports | TB scaffold |
| Performance Debug | read latency가 높을 때 어디 봐야 해? | perf monitor, SW perf guide | probe list, rerun command |
| EDC Debug | 특정 EDC node path 찾아줘 | EDC HDD, EDC path reference | ring segment, node instance path |
| PD Debug | timing path bottleneck 분석해줘 | P&R guide, timing report | ECO 후보, risk |

---

## 7. Spec-to-RTL Traceability Matrix 예시

| Spec Item | Block | Module | RTL File | Interface/Signal | Verification Impact | Source |
|---|---|---|---|---|---|---|
| N1B0 middle columns use composite NOC2AXI+Router tile | NOC2AXI/Router | `trinity_noc2axi_router_ne_opt` / `nw_opt` | `used_in_n1/rtl/trinity_noc2axi_router_*_opt.sv` | Y=4 `noc2axi_*`, Y=3 `router_*` | Y=3 router placeholder empty 여부 확인 필요 | `N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` |
| NOC2AXI latency monitor is simulation-only | Perf Monitor | `noc2axi_perf_monitor` | `used_in_n1/rtl/noc2axi_perf_monitor.sv` | AR/R/AW/B channels, `output real` | gate-level/synthesis 대상 제외 | `N1B0_PerfMonitor_HDD_v0.1.md` |
| AXI dynamic delay must not change delay while busy | AXI test infra | `axi_dynamic_delay_buffer` | `used_in_n1/rtl/axi_dynamic_delay_buffer.sv` | `delay_cycles`, `fifo_count` | SVA must check stability while non-empty | `N1B0_AXI_Dynamic_Delay_HDD_v0.1.md` |
| Router address decoding has mesh-level and local address-level split | Router/NIU | `trinity_router`, `tt_noc2axi` | router/NIU RTL | NoC header, ATT/TLB | routing and local AXI decode tests should be separated | `router_decode_HDD_v0.5.md` |
| Overlay provides CPU/NoC/L1/iDMA/ROCC/SMN/EDC integration | Overlay | `tt_overlay_wrapper` | overlay RTL | L1, NoC, APB, SMN, EDC | verification should split control/data/diagnostic paths | `overlay_HDD_v0.3.md` |

---

## 8. RAG Answer Quality Rubric 초안

| 평가 항목 | 설명 | Pass 기준 | Fail 예시 |
|---|---|---|---|
| Evidence grounding | 답변이 문서 근거에 기반하는가 | source file/section 또는 명확한 근거 포함 | 근거 없이 일반 EDA 지식으로 단정 |
| Variant correctness | Trinity baseline과 N1B0를 구분하는가 | variant 명시, N1B0 delta 반영 | baseline router tile을 N1B0에도 그대로 있다고 설명 |
| RTL specificity | module/file/signal/interface가 정확한가 | RTL file, module, port prefix 정확 | 비슷한 module명 혼동 |
| Synth/sim distinction | synthesizable 여부를 구분하는가 | `noc2axi_perf_monitor`는 sim-only로 답변 | sim-only monitor를 gate-level에 있다고 설명 |
| Task fit | 질문 의도에 맞는 artifact를 내는가 | SVA 요청 시 property와 assumption 제공 | architecture summary만 제공 |
| Risk handling | 위험 작업에서 guardrail을 적용하는가 | patch/ECO는 recommend-only로 제한 | 자동 RTL 수정 단정 |
| Completeness | 답변에 필요한 맥락을 포함하는가 | grid, endpoint, clock/interface 등 필요 정보 포함 | 부분 정보만 제공 |

---

## 9. 구현 우선순위 제안

## Phase 1 — Front-end RAG foundation

| Step | 구현 항목 | 설명 |
|---:|---|---|
| 1 | Document inventory 정리 | 현재 HDD/CSV/guide 파일을 block/task별로 분류 |
| 2 | RAG metadata schema 적용 | chunk ingestion 시 metadata 부여 |
| 3 | Variant-aware retrieval | Trinity baseline / N1B0 필터링 지원 |
| 4 | Module/interface chunking | section chunk 외 module/interface/behavior chunk 생성 |
| 5 | Source evidence output | 답변에 file/section 근거 포함 |

## Phase 2 — Traceability and task map

| Step | 구현 항목 | 설명 |
|---:|---|---|
| 1 | Spec-to-RTL trace matrix 생성 | HDD 문장과 module/file/signal 연결 |
| 2 | N1B0 variant delta matrix 생성 | baseline vs N1B0 차이 구조화 |
| 3 | EDA task map 구현 | 질문 유형별 target collection/tool 선택 |
| 4 | Consistency check rule 추가 | grid/endpoint/module mismatch 탐지 |

## Phase 3 — DV evaluation

| Step | 구현 항목 | 설명 |
|---:|---|---|
| 1 | DV case set v0.1 작성 | 30~50개 case |
| 2 | Rubric 정의 | pass/fail/partial 기준 |
| 3 | 반자동 scoring 구현 | keyword/source/syntax 기반 1차 평가 |
| 4 | SVA/TB generation prompt 안정화 | known module 대상으로 반복 평가 |

## Phase 4 — Agent orchestration

| Step | 구현 항목 | 설명 |
|---:|---|---|
| 1 | Agent role 정의 | Architecture/RTL/DV/Perf/PD |
| 2 | Routing policy 구현 | 질문 유형 분류 |
| 3 | Tool contract 적용 | read-only/generation/debug 권한 구분 |
| 4 | Human approval guardrail | RTL patch/ECO 등 위험 작업 제한 |

## Phase 5 — Backend PD 확장

| Step | 구현 항목 | 설명 |
|---:|---|---|
| 1 | PD artifact schema 정의 | timing/congestion/netlist/report |
| 2 | Timing path parser 설계 | report-to-structured-data |
| 3 | ECO primitive catalog 작성 | gate sizing/buffer insertion 등 |
| 4 | Recommend-only PD assistant | 자동 ECO 전 사람 검토 전제 |

---

## 10. Kiro와 논의할 질문 목록

아래 질문은 실제 구현 전 Kiro와 합의가 필요하다.

| No | 논의 질문 | 결정 필요 사항 |
|---:|---|---|
| 1 | RAG collection을 block별로 나눌 것인가, 하나의 collection에 metadata filter를 쓸 것인가? | collection architecture |
| 2 | Trinity baseline과 N1B0 variant를 어떻게 구분할 것인가? | variant metadata / retrieval filter |
| 3 | hierarchy CSV와 HDD markdown을 ingestion 단계에서 어떻게 연결할 것인가? | preprocessor 설계 |
| 4 | Spec-to-RTL traceability matrix를 수동 curated로 만들 것인가, LLM-assisted로 만들 것인가? | artifact generation 방식 |
| 5 | 답변에 source evidence를 어떤 형식으로 넣을 것인가? | citation/output format |
| 6 | DV evaluation case는 JSONL로 관리할 것인가, markdown table로 관리할 것인가? | benchmark format |
| 7 | SVA/TB 생성 결과를 실제 simulation까지 돌릴 것인가, 초기는 static review만 할 것인가? | evaluation depth |
| 8 | MCP tool을 agent별로 분리할 것인가, gateway 하나에서 task routing할 것인가? | MCP architecture |
| 9 | PD/timing artifact는 지금 schema만 만들 것인가, parser까지 만들 것인가? | backend scope |
| 10 | 외부 LLM 답변의 hallucination을 어떻게 점수화할 것인가? | quality gate |

---

## 11. 권장 MVP

가장 현실적인 MVP는 다음이다.

```text
MVP 이름:
  Trinity/N1B0 EDA RAG v0.1

MVP 목표:
  HDD/RTL/hierarchy 기반 Architecture QA + RTL locate + DV seed generation

MVP 포함:
  - N1B0/Trinity variant-aware retrieval
  - NOC2AXI_ROUTER_OPT composite tile 정확 답변
  - noc2axi_perf_monitor sim-only 구분
  - axi_dynamic_delay_buffer SVA/TB 생성
  - router_decode / ATT / dynamic routing 설명
  - 답변 source evidence 포함
  - 30개 내외 DV evaluation cases

MVP 제외:
  - 자동 RTL patch 적용
  - 자동 ECO 적용
  - full STA/P&R optimization
  - waveform 자동 해석, 단 초기 prompt/eval case는 준비 가능
```

---

## 12. 최종 제안

이번 논문 검토를 기반으로 프로젝트는 다음 방향으로 가는 것이 가장 타당하다.

```text
1. 논문 요약을 하지 말고, 논문별 역할을 workstream으로 분리한다.
2. 1차 구현은 TUM LLM4EDA + FIXME 중심으로 한다.
3. 먼저 RAG metadata schema와 traceability matrix를 만든다.
4. 그 다음 DV evaluation case set으로 답변 품질을 측정한다.
5. ChipMnd는 agent orchestration 구조 설계에 사용한다.
6. NVIDIA LEGO-PD는 backend artifact가 충분히 쌓인 뒤 확장한다.
```

결론적으로, 현재 단계의 핵심 산출물은 다음이다.

```text
- EDA RAG Target Task Map
- Trinity/N1B0 RAG Metadata Schema
- Spec-to-RTL Traceability Matrix
- N1B0 Variant Delta Matrix
- DV Evaluation Case Set v0.1
- RAG Answer Quality Rubric
- Agent Routing / Tool Contract Policy
```

이 산출물들이 준비되면 Kiro와 실제 구현 단위, MCP tool routing, RAG collection 구조, evaluation loop를 구체적으로 논의할 수 있다.

---

## 13. 부록 — 산출물 상태 구분

현재 존재하는 것은 Trinity/N1B0 HDD와 hierarchy 관련 문서들이다.  
아래 산출물들은 아직 존재하는 파일이 아니라, 이번 검토 결과로 **새로 만들어야 할 산출물**이다.

| 산출물 | 상태 |
|---|---|
| EDA RAG Target Task Map | 신규 작성 필요 |
| Trinity/N1B0 RAG Metadata Schema | 신규 작성 필요 |
| Spec-to-RTL Traceability Matrix | 신규 작성 필요 |
| N1B0 Variant Delta Matrix | 신규 작성 필요 |
| DV Evaluation Case Set v0.1 | 신규 작성 필요 |
| RAG Answer Quality Rubric | 신규 작성 필요 |
| Agent Routing / Tool Contract Policy | 신규 작성 필요 |
| PD Artifact Schema | 후순위 신규 작성 필요 |
