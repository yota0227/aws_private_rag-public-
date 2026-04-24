# SoC 개발 RAG Farm 전략

**작성일:** 2026-04-24
**작성:** Claude Code (리뷰/분석 역할)
**상태:** Draft v0.1 — 아이템 발굴 및 방향성 정리

---

## 1. 배경

### 1.1 현재 상황

BOS-AI 팀은 RTL 소스 코드를 대상으로 Private RAG 시스템을 구축하여 HDD(Hardware Design Document) 자동 생성을 시도했다. 5일간의 집중 개선을 통해 정답지 대비 50% 품질에 도달했으나, 근본적인 한계에 직면했다.

**핵심 발견:**
- RTL 코드는 **"어떻게(How)"** 만 알려주고, **"무엇을(What)"** 은 알려주지 않는다
- 엔지니어 수작업 HDD의 80% 이상은 RTL이 아닌 Spec 문서(패키지 정의, 설계 의도)에서 유래한다
- DV(Design Verification) 팀의 실제 요구사항은 RTL 분석이 아니라 **Spec 기반 검증 산출물 생성**이다
- FMEDA, Design Document, FW 코드 등 다양한 팀의 산출물 자동화 수요가 존재한다

### 1.2 전략 전환: RTL RAG → RAG Farm

단일 RAG가 아닌, **목적별 RAG 인스턴스의 집합체(RAG Farm)** 로 확장하여 SoC 개발 전 Phase에 걸친 업무 자동화를 지원한다.

```
┌──────────────────── RAG Farm ──────────────────────────────┐
│                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────────┐ │
│  │ RTL RAG │  │Spec RAG │  │ Safety  │  │ Compliance   │ │
│  │ (구축됨)│  │ (1순위) │  │ RAG     │  │ RAG          │ │
│  └─────────┘  └─────────┘  └─────────┘  └──────────────┘ │
│                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────────┐ │
│  │ DV RAG  │  │Debug RAG│  │Waiver   │  │ Knowledge    │ │
│  │         │  │         │  │RAG      │  │ RAG          │ │
│  └─────────┘  └─────────┘  └─────────┘  └──────────────┘ │
│                                                             │
│  공유 인프라: OpenSearch AOSS, Bedrock, Lambda, MCP Bridge  │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 인프라 재사용

기존 RTL RAG 파이프라인에서 구축한 인프라를 그대로 활용한다.

| 인프라 컴포넌트 | 상태 | 재사용 범위 |
|----------------|------|-----------|
| OpenSearch Serverless (AOSS) | 운영 중 | 인덱스 추가로 전 RAG 공유 |
| Bedrock (Titan Embeddings + Claude) | 운영 중 | 전 RAG 공유 |
| Lambda (Seoul) | 운영 중 | 파서 모듈만 교체/추가 |
| Step Functions | 운영 중 | 파이프라인 단계만 확장 |
| MCP Bridge + Obot | 운영 중 | 도구(tool) 추가로 확장 |
| S3 (RTL 소스 저장) | 운영 중 | 버킷/prefix 추가 |
| DynamoDB (상태 관리) | 운영 중 | 테이블 공유 |

신규 RAG 추가 시 **Lambda 파서 코드 + OpenSearch 인덱스 + MCP 도구 정의**만 추가하면 된다.

---

## 2. 활용 아이템 요약

| # | 아이템 | SoC Phase | 주 사용 팀 | 입력 데이터 | 출력 |
|---|--------|-----------|-----------|------------|------|
| 기반 | Spec RAG 구축 | 전 Phase | 전체 | HDD, AddressMap, I/F Spec | 검색/조회 |
| ① | FMEDA 자동 분석 | Signoff | Safety | Netlist, FM Library, SM DB | FMEDA 초안 |
| ② | 검증 TB 자동 생성 | Verification | DV | Spec + TB구조 + VIP | UVM TB 코드 |
| ④ | ISO/ASPICE Design Doc | Certification | 설계/품질 | RTL + Spec + 규격 | Architecture/Detail Design |
| ⑤ | FW/Driver 코드 생성 | Implementation | FW | AddressMap + HDD | HAL/Driver 코드 |
| ⑥ | Post-Silicon Debug KB | Post-Silicon | Debug | Debug 로그, Errata, ECO | 유사 이슈 검색, Errata 문서 |
| ⑦ | Waiver 자동화 | Signoff | 설계/DV | Lint/CDC/Cov + 과거 waiver | Waiver 근거 자동 생성 |
| ⑧ | IP Integration Guide | Design | 설계 | IP Spec + 과거 이력 | 통합 체크리스트 |
| ⑨ | EDA Recipe 관리 | Implementation | BE | SDC/스크립트/리포트 | 과거 레시피 검색 |
| ⑩ | 온보딩 / 기술 Q&A | 전 Phase | 전체 | RAG Farm 전체 | 대화형 기술 지원 |

---

## 3. 아이템별 상세

### 기반: Spec RAG 구축

**목적**
SoC Spec 문서(HDD, AddressMap, Interface Spec)를 임베딩하여, 설계 의도("What")를 검색 가능한 지식으로 만든다. 전체 활용 아이템 10개 중 7개가 Spec RAG에 의존하므로 이것이 전제조건이다.

**기대 효과**
- Spec 기반 활용 아이템(②④⑤⑦ 등)의 기반 확보
- RTL RAG와 교차 검색으로 RTL↔Spec 정합성 검증 가능
- Obot/MCP Bridge를 통한 Spec 내용 즉시 검색

**고려 사항**
- HDD 형식 파악 필요: Word → python-docx 변환, Confluence → REST API, Markdown → 즉시 가능
- AddressMap 형식 파악 필요: Excel(openpyxl), IP-XACT(XML 파서), SystemRDL(PeakRDL)
- 임베딩 단위(Chunk) 전략이 검색 품질을 결정함: HDD는 섹션 단위, AddressMap은 레지스터 단위
- 문서 버전 관리: pipeline_id 격리 방식 그대로 적용 가능

---

### ① FMEDA 자동 분석

**목적**
Netlist의 각 element(게이트/FF/메모리)에 대해 Failure Mode 분류, Effect 판정, Safety Mechanism 매핑, Diagnostic Coverage 계산을 자동화한다. 현재 수만~수십만 행 Excel을 엔지니어 수 명이 수 주간 수작업으로 작성하는 프로세스를 개선한다.

**기대 효과**
- FMEDA 초안 작성 시간 대폭 단축 (수 주 → 수 일)
- 이전칩 FMEDA 결과 기반 유사 element 판정 자동 검색
- Safety Mechanism 매핑 후보 자동 제안
- Diagnostic Coverage 수치 자동 계산

**고려 사항**
- Effect 판정(Safe vs Dangerous)은 LLM 단독 불가 — "제안 + 엔지니어 승인" 워크플로우 필수
- ISO 26262 심사관의 AI 활용 수용 여부 — AI는 초안 생성, 엔지니어 서명이 최종
- Netlist 파서 신규 개발 필요 (Verilog netlist → JSON 구조화)
- Failure Mode Library와 Safety Mechanism DB의 구조화 상태에 따라 난이도 변동

---

### ② 검증 Testbench 자동 생성

**목적**
DV팀의 핵심 요구사항. Spec(HDD, AddressMap, I/F Spec) 기반으로 UVM Testbench 코드를 단계적으로 자동 생성한다. Testplan 작성/리뷰, Checker/Sequence 코드 생성, 코너 케이스 및 복합 시나리오 도출을 포함한다.

**기대 효과**
- TB 초기 셋업 시간 50%+ 단축 (보일러플레이트 자동 생성)
- Spec 기반 Testplan 자동 생성으로 feature 누락 방지
- AddressMap → 레지스터 R/W 테스트 완전 자동화
- I/F Spec → SVA assertion 자동 생성
- BOS TB 프레임워크 + SNPS VIP 패턴 학습으로 팀 고유 코드 스타일 반영

**고려 사항**
- 단계적 접근 필요: 스켈레톤(L1) → Checker(L2) → Sequence(L3) → 통합(L4)
- Scoreboard 내부 로직은 도메인 전문성 필요 — L4는 자동화율 낮음
- BOS TB 구조 문서와 VIP API 레퍼런스의 임베딩이 코드 품질을 좌우
- 생성된 코드의 컴파일/시뮬레이션 검증 프로세스 필요
- DV팀과 데이터 형식 합의 필요: Testplan(Excel 템플릿), Coverage 결과 형식

---

### ④ ISO 26262 / ASPICE Design Document 자동 작성

**목적**
RTL 코드 또는 SW 소스 코드에서 ISO 26262 Part 5/6 및 ASPICE 요구사항에 부합하는 Architecture Design / Detailed Design 문서를 자동 생성한다. 인증 직전 병목(코드는 바뀌는데 문서가 안 따라감)을 해소한다.

**기대 효과**
- 인증 준비 기간 대폭 단축
- 코드 변경 시 Design 문서 자동 갱신 (diff 감지 → 영향 섹션 플래그)
- Traceability 매트릭스(요구사항 ↔ Design ↔ 코드 ↔ Test) 자동 생성
- **기존 RTL RAG(8,107건 module_parse + 80개 hierarchy)를 직접 활용**

**고려 사항**
- 과거 인증 통과 문서를 RAG에 넣어야 톤/포맷/심사관 기대 수준 학습 가능
- Safety rationale(안전 근거)은 엔지니어 작성 필수 — AI는 구조/템플릿만 채움
- 규격 요구사항(ISO 26262 Table, ASPICE Work Product) 구조화 임베딩 필요
- SW 코드 분석은 별도 AST 파서 필요 (Python AST, C/C++ clang 등)
- 가장 ROI가 높고 경영진 설득이 쉬운 아이템

---

### ⑤ AddressMap → FW/Driver 코드 자동 생성

**목적**
AddressMap(레지스터 맵)과 HDD를 기반으로 FW/Driver 레벨의 HAL(Hardware Abstraction Layer) 코드를 자동 생성한다. 단순 코드 생성(#define, struct)을 넘어, HDD의 초기화 시퀀스/사용 패턴까지 반영한 실용적 코드를 생성한다.

**기대 효과**
- 레지스터 접근 코드 수작업 제거 (블록당 수백 개 레지스터)
- 레지스터 변경 시 FW 코드 자동 동기화
- HDD 기반 초기화 시퀀스 코드 자동 생성 (단순 codegen 대비 차별점)
- 코딩 스타일/네이밍 컨벤션 일관성 보장

**고려 사항**
- 단순 코드 생성(#define, struct)은 기존 도구(ralgen 등)로도 가능 — RAG의 가치는 HDD 기반 "사용 패턴" 생성
- FW팀의 코딩 컨벤션/프레임워크에 맞춰야 함 — 과거 FW 코드 패턴 임베딩 필요
- AddressMap이 Excel인 경우 컬럼 매핑 규칙 정의 필요
- Spec RAG(AddressMap + HDD)에 직접 의존

---

### ⑥ Post-Silicon Debug Knowledge Base

**목적**
실리콘 bring-up 및 디버그 과정에서 발생한 이슈를 이전 세대 칩의 Debug 로그, Errata, ECO 이력과 교차 검색하여 근본 원인 분석(RCA) 시간을 단축한다. 확인된 버그에 대한 Errata 문서와 SW workaround를 자동 생성한다.

**기대 효과**
- 디버그 시간 단축 (유사 이슈 즉시 검색 — "이전 칩에서도 이런 적 있었나?")
- 세대 간 동일 실수 반복 방지
- Errata 문서 자동 생성 (RTL RAG + Spec RAG 연동)
- 영향받는 고객 use case 자동 식별

**고려 사항**
- Debug 로그의 형식이 팀/프로젝트마다 다를 수 있음 — 최소한의 구조화 필요
- Errata/ECO 데이터가 Jira, Confluence 등 여러 시스템에 분산되어 있을 가능성
- 과거 데이터 수집이 일회성 대규모 작업 — 이후 신규 데이터는 자동 적재 가능
- **Post-silicon 디버그가 프로젝트 일정의 30-40%를 차지하므로 ROI가 매우 높음**

---

### ⑦ Waiver 자동화 (Lint / CDC / Coverage)

**목적**
Lint, CDC, Coverage 도구 실행 결과에서 발생하는 수천 건의 경고/violation에 대해, 과거 waiver 이력 + RTL 구조 + Spec 설계 의도를 종합하여 waiver 근거를 자동 생성한다.

**기대 효과**
- Waiver 작성 시간 대폭 단축 (건당 수십 분 → 자동 생성 + 검토)
- 이전 프로젝트 동일 패턴 waiver 자동 재활용
- Waiver 근거의 일관성/품질 향상 (Spec 참조 자동 첨부)
- 불필요한 waiver 식별 (실제 수정이 필요한 항목 분리)

**고려 사항**
- Lint/CDC 도구별 출력 형식이 다름 — 파서 어댑터 필요 (Synopsys SpyGlass, Cadence JasperGold 등)
- 과거 waiver DB의 구조화 상태에 따라 초기 임베딩 난이도 변동
- Waiver 승인 워크플로우 — AI 생성 → 리드 엔지니어 승인 → 서명
- RTL RAG(구조 분석) + Spec RAG(설계 의도) 교차 활용의 대표적 사례

---

### ⑧ IP Integration Guide 자동 생성

**목적**
외부 또는 내부 IP를 SoC에 통합할 때, IP Spec과 과거 통합 이력을 검색하여 Integration Checklist와 설정 가이드를 자동 생성한다.

**기대 효과**
- IP 통합 초기 셋업 시간 단축
- 과거 프로젝트 동일 IP 통합 경험 즉시 검색
- 클럭/리셋/인터럽트/전력 도메인 매핑 자동 제안
- 통합 시 주의사항 자동 경고 (과거 이슈 기반)

**고려 사항**
- IP Datasheet 형식이 벤더마다 다름 — PDF 파싱 품질이 관건
- 과거 Integration 이력이 체계적으로 관리되어 있어야 함
- SoC 아키텍처 정보(클럭 트리, 파워 도메인)가 Spec RAG에 있어야 정확한 매핑 가능
- 우선순위는 낮지만 IP 재사용이 많은 팀에서 가치 있음

---

### ⑨ EDA Tool Recipe 관리

**목적**
합성/P&R/STA 등 EDA 실행에 사용된 SDC 제약 조건, 스크립트, 실행 결과를 임베딩하여 과거 레시피를 검색 가능하게 한다.

**기대 효과**
- "이전에 이런 타이밍 경로 어떻게 닫았지?" 즉시 검색
- SDC 제약 조건 패턴 재사용
- QoR(Quality of Results) 비교 데이터 축적

**고려 사항**
- EDA 도구별 입출력 형식이 매우 다양
- 스크립트/SDC는 텍스트 기반이라 임베딩은 용이하나, 실행 결과(리포트)는 파싱 필요
- BE(Back-End) 팀의 워크플로우 이해가 선행되어야 함
- 우선순위 낮음 — Phase 4에서 검토

---

### ⑩ 온보딩 / 사내 기술 Q&A

**목적**
RAG Farm 전체를 프론트엔드(Obot/MCP Bridge)로 통합하여 대화형 기술 Q&A 시스템을 제공한다. 신규 입사자 온보딩, 타 팀 기술 질의, 레거시 지식 검색에 활용한다.

**기대 효과**
- 신규 입사자 온보딩 시간 단축 (선임 엔지니어 시간 절약)
- "이전 칩에서 이거 어떻게 했지?" 즉시 답변
- Confluence/Jira 검색의 한계 극복 (의미 기반 검색)
- 세대 간 기술 지식 전달 체계 확립

**고려 사항**
- 별도 개발 아이템이 아님 — RAG Farm이 성장하면 자연스럽게 완성
- 검색 품질은 각 RAG의 임베딩 품질에 의존
- 접근 권한 관리: 팀/프로젝트별 데이터 접근 제어 필요
- MCP Bridge에 도구(tool)를 계속 추가하는 구조로 확장

---

## 4. 실행 로드맵 (안)

> **참고:** 아래 로드맵과 Phase 구분은 초안이며, 팀별 데이터 현황 파악 및 우선순위 논의 후 확정 예정이다.

### Phase 구분

| Phase | 내용 | 전제 조건 |
|-------|------|----------|
| Phase 0 | RTL RAG 운영 (현재) | 구축 완료 |
| Phase 1 | Spec RAG 구축 — 전체의 기반 | DV/설계팀 데이터 형식 합의, HDD/AddressMap 확보 |
| Phase 2 | Spec 기반 산출물 자동화 (④②⑤) | Spec RAG 완성, 각 팀 요구사항 상세화 |
| Phase 3 | Safety/Signoff 자동화 (①⑦⑥) | Phase 2 운영 안정화, Safety/Debug 팀 데이터 확보 |
| Phase 4 | 확장 및 Q&A 통합 (⑧⑨⑩) | RAG Farm 운영 경험 축적 |

### 로드맵 흐름

```
Phase 0 (현재):  RTL RAG 운영 중
                      │
Phase 1:         Spec RAG 구축 ─── 전체의 기반
                      │
              ┌───────┼─────────────┐
              ▼       ▼             ▼
Phase 2:   ④Design  ②TB 생성    ⑤FW/Driver
           Doc       (DV팀)      (FW팀)
                      │
              ┌───────┼───────┐
              ▼       ▼       ▼
Phase 3:   ①FMEDA  ⑦Waiver  ⑥Debug KB
           (Safety) (전체)    (Post-Si)
                      │
Phase 4:   ⑧IP통합  ⑨EDA    ⑩Q&A (자동 완성)
```

---

## 5. 비고

- 본 문서는 아이템 발굴 및 방향성 정리 단계이다.
- 로드맵의 Phase 구분과 우선순위는 팀별 데이터 현황 파악 후 확정한다.
- Spec RAG가 다수 아이템의 전제조건이라는 점은 확인되었으나, 실행 시점은 별도 논의 대상이다.
