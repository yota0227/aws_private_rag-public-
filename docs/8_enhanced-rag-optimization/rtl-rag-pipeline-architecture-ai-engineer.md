# RTL RAG 파이프라인 아키텍처 — AI Engineer 편

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-05-04 | 초판. 원본(rtl-rag-pipeline-architecture.md)에서 AI Engineer 관점으로 분리 |
| v2.0 | 2026-05-08 | v9.2 기준 업데이트. 8종 파서 반영, Layer 4~5 부분 커버, 동적 Boost/청킹/Hybrid Grounding 구현 완료 |

**대상:** AI/RAG Engineer (파이프라인 구현·개선 담당)
**목적:** RTL 코드를 어떻게 바라보고, 어떤 전략으로 전처리하여 KB를 구축하는지 이해한다. 이를 바탕으로 파서와 검색 파이프라인을 개선한다.

---

## 1. 문제 정의 — RTL 코드는 왜 어려운가

### 1.1 우리가 풀려는 문제

반도체 설계에서 **HDD(Hardware Design Document)**는 칩의 구조와 동작을 기술하는 핵심 산출물이다. 블록 하나의 HDD 작성에 2~4주가 걸리고, 칩 전체로는 수십 인·월이 소요된다.

**목표:** RTL 소스 코드를 자동 분석하여 HDD 초안을 생성한다.

### 1.2 RTL 코드의 특성 — 일반 소프트웨어와 다른 점

RTL(Register Transfer Level)은 하드웨어를 기술하는 코드다. 일반 소프트웨어 코드와 근본적으로 다른 특성이 있어서, 범용 코드 분석 도구로는 처리할 수 없다.

| 특성 | 소프트웨어 코드 | RTL 코드 |
|------|---------------|---------|
| **실행 모델** | 순차 실행 (위→아래) | 병렬 실행 (모든 `always` 블록이 동시에 동작) |
| **구조 단위** | 함수, 클래스 | 모듈 (module), 인스턴스 (instantiation) |
| **인터페이스** | 함수 시그니처 (인자 + 리턴) | 포트 목록 (input/output/inout × 비트폭 × 수백 개) |
| **타입 시스템** | 고수준 (int, string, object) | 비트 레벨 (`logic [31:0]`, `wire`, `reg`) |
| **설정 상수** | 환경변수, config 파일 | `localparam`, `parameter`, `typedef enum/struct` (패키지 파일) |
| **계층 구조** | import/include | 모듈 인스턴스화 (트리 구조, 수천 노드) |
| **조건부 구조** | `#ifdef` | `generate for/if` (하드웨어 구조를 조건부로 생성) |
| **파일 규모** | 수백~수천 줄 | top-level 모듈 하나가 수천 줄, 전체 9,000+ 파일 |

### 1.3 HDD가 요구하는 정보의 층위

HDD 한 문서에는 여러 층위의 정보가 필요하다. 각 층위마다 **RTL 코드에서 추출 가능한 정도**가 다르다.

```
┌─────────────────────────────────────────────────┐
│  Layer 1: 구조 (Structure)                       │  ← ✅ RTL에서 직접 추출
│  모듈명, 포트, 파라미터, 인스턴스 계층            │
├─────────────────────────────────────────────────┤
│  Layer 2: 타입/설정 (Type/Config)                │  ← ✅ 패키지 파일에서 추출
│  localparam, enum, struct, function, EP Table    │
├─────────────────────────────────────────────────┤
│  Layer 3: 인터페이스 분류 (Interface)             │  ← ✅ 패턴 매칭으로 분류
│  포트의 기능별 그룹핑 (Power, AXI, Clock 등)      │
├─────────────────────────────────────────────────┤
│  Layer 4: 동작 (Behavior)                        │  ← ⚠️ 부분 지원 (v9)
│  클럭 도메인 추출, CDC 경고                       │     FSM/데이터패스는 미지원
├─────────────────────────────────────────────────┤
│  Layer 5: 연결 (Connectivity)                    │  ← ⚠️ 부분 지원 (v9~v9.2)
│  generate 토폴로지, wire 배열, 인스턴스 위치      │     assign 구동 관계는 미지원
├─────────────────────────────────────────────────┤
│  Layer 6: 설계 의도 (Intent)                     │  ← ❌ RTL에 없음. Spec 문서 필요
│  "왜 이렇게 설계했는가", 비교 테이블, 제약 조건    │
└─────────────────────────────────────────────────┘
```

**v9.2 파이프라인은 Layer 1~3을 완전 커버하고, Layer 4~5를 부분 커버한다.** Layer 6은 Spec RAG가 필요하다.

---

## 2. 파이프라인 전체 흐름

### 2.1 데이터 흐름

```
RTL 소스 (.sv / .v / .svh)
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  Stage 1: 구조 추출 (Structural Parsing)              │
│                                                       │
│  모든 RTL 파일 → 정규식 기반 파싱                      │
│  추출: 모듈명, 포트(방향+비트폭+이름),                 │
│        파라미터, 인스턴스(인스턴스명:모듈타입)           │
│                                                       │
│  결과: module_parse 레코드 (~10,000건)                 │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│  Stage 2: 의미 강화 (Semantic Enrichment)             │
│                                                       │
│  2a. Package Parser (*_pkg.sv 전용)                   │
│      → localparam, enum, struct, function/task 추출   │
│      → EP Index Table 계산 (v9.2)                     │
│      → 중첩 struct + 필드별 비트폭 (v9)               │
│      → claim 레코드 생성 (~80건)                      │
│                                                       │
│  2b. Port Classifier (포트 10개+ 모듈)                │
│      → 9개 기능 카테고리로 포트 분류                   │
│      → 카테고리별 claim 레코드 생성 (~11건)            │
│                                                       │
│  2c. Generate Block Parser (v9 신규)                  │
│      → generate for/if 블록 토폴로지 인식             │
│      → 인스턴스-위치 매핑, NoC repeater (v9.2)        │
│      → claim 레코드 생성 (~20건)                      │
│                                                       │
│  2d. Always Block Parser (v9 신규)                    │
│      → always_ff 클럭 도메인 추출, CDC 경고           │
│      → claim 레코드 생성 (~15건)                      │
│                                                       │
│  2e. Wire Declaration Parser (v9.2 신규)              │
│      → struct/logic wire 선언 + 배열 차원 + 목적 유추 │
│      → claim 레코드 생성 (~10건)                      │
│                                                       │
│  2f. Bitwidth Evaluator (v9 신규)                     │
│      → 파라미터 표현식을 정수로 평가 (SizeX-1 → 3)    │
│      → ast.NodeVisitor 기반 안전한 파서               │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│  Stage 3: 벡터화 + 인덱싱                             │
│                                                       │
│  Titan Embeddings v2 (1024차원)                       │
│      → 각 레코드를 벡터로 변환                         │
│                                                       │
│  OpenSearch Serverless 인덱싱                         │
│      → 벡터 검색 + 키워드 검색 하이브리드              │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│  Stage 4: 검색 + 생성 (Retrieval + Generation)        │
│                                                       │
│  사용자 질의 → 벡터 유사도 + 키워드 매칭               │
│      → 상위 50건 검색 (boost 가중치 적용)              │
│      → Claude에게 컨텍스트로 전달                      │
│      → HDD 섹션 초안 생성                              │
└──────────────────────────────────────────────────────┘
```

### 2.2 핵심 설계 원칙

**"Claim" 아키텍처:** 파서가 추출한 사실을 자연어 문장(claim)으로 변환하여 저장한다.

```
# 원본 RTL
localparam int SizeX = 4;

# claim으로 변환
"Package 'trinity_pkg' defines localparam SizeX = 4"
```

왜 이렇게 하는가:
- **임베딩 품질 향상** — 코드 조각보다 자연어 문장이 벡터 공간에서 더 잘 클러스터링됨
- **검색 정확도** — "그리드 크기가 몇이야?"라는 질문과 claim이 의미적으로 가까움
- **LLM 컨텍스트 효율** — 구조화된 사실이 raw 코드보다 토큰 대비 정보 밀도가 높음

**"공급(Supply) vs 소비(Consumption)" 프레임워크:**

```
공급 측 (Supply)              소비 측 (Consumption)
─────────────────            ─────────────────────
파서가 KB에 넣는 것           검색이 KB에서 꺼내는 것

• 파서 종류/개수              • max_results (cutoff)
• claim 품질/밀도             • boost 가중치
• 분석 범주 (analysis_type)   • 필터 (topic, pipeline_id)
• 임베딩 전략                 • 벡터 vs 키워드 비율
```

이 두 축은 독립적이다. 공급을 아무리 늘려도 소비 측 cutoff가 좁으면 KB에 있는 정보가 검색에 안 잡힌다. 반대로 소비를 넓혀도 공급이 빈약하면 노이즈만 늘어난다.

---

## 3. 파서 컴포넌트 상세

### 3.1 기본 모듈 파서 (Stage 1)

**파일:** `handler.py` → `parse_rtl_to_ast`
**대상:** 모든 `.sv`, `.v`, `.svh` 파일
**방식:** 정규식 기반

| 추출 항목 | 정규식이 잡는 것 | 예시 |
|-----------|----------------|------|
| 모듈 선언 | `module <이름>` | `module trinity` |
| 포트 | `input/output/inout [비트폭] <이름>` | `input [SizeX-1:0] i_ai_clk` |
| 파라미터 | `parameter/localparam <이름> = <값>` | `DATA_WIDTH=32` |
| 인스턴스 | `<모듈타입> <인스턴스명> (` | `tt_dispatch_top u_dispatch (` |

**결과물:** `analysis_type=module_parse` 레코드. 모듈 하나당 하나의 레코드.

**한계 — 정규식이 잡지 못하는 것:**

| RTL 구조 | 왜 못 잡는가 | 담고 있는 정보 |
|----------|-------------|---------------|
| `always_ff` / `always_comb` | 블록 내부 로직은 문맥 의존적 | 클럭 도메인, FSM, 데이터패스 |
| `assign` 문 | 단순 대입이지만 신호 구동 관계를 형성 | 모듈 간 연결, mux 선택 |
| `generate for/if` | 반복/조건부 구조 생성, 정규식으로 범위 파악 불가 | 배선 토폴로지, 타일 배열 |

### 3.2 Package Parser (Stage 2a)

**파일:** `package_extractor.py`
**대상:** `*_pkg.sv` 파일만
**방식:** 정규식 기반

**왜 별도 파서가 필요한가:**

패키지 파일은 칩의 "설정 파일"이다. 그리드 크기, 타일 종류, 클럭 라우팅 구조체 등 **칩 전체에 영향을 미치는 상수와 타입**이 정의되어 있다. 기본 모듈 파서는 이걸 `parameter` 수준으로만 잡기 때문에, `localparam`, `typedef enum`, `typedef struct`를 전용으로 추출하는 파서가 필요하다.

| 추출 대상 | 왜 중요한가 | claim 예시 |
|-----------|-----------|-----------|
| `localparam` | 그리드 크기(SizeX=4, SizeY=5), 엔드포인트 수 등 칩 구성 결정 | `Package 'trinity_pkg' defines localparam SizeX = 4` |
| `typedef enum` | 타일 종류(TENSIX, ROUTER, DRAM 등) 정의 | `...defines typedef enum 'tile_t' with 8 members` |
| `typedef struct` | 클럭 라우팅, 리셋 구조 등 복합 타입 | `...defines typedef struct 'trinity_clock_routing_t'` |

**현재 한계:**
- `function` / `task` 미추출 — 인덱스 계산 함수(`getTensixIndex` 등)가 빠짐
- 중첩 struct 미지원
- 표현식 평가 안 함 — `SizeX * SizeY`를 `20`으로 계산하지 않고 문자열 그대로 저장

### 3.3 Port Classifier (Stage 2b)

**파일:** `port_classifier.py`
**대상:** 포트 10개 이상인 모듈
**방식:** 포트 이름 패턴 매칭 → 기능 카테고리 분류

**왜 필요한가:**

Top-level 모듈(예: `trinity.sv`)은 포트가 106개다. 이걸 flat list로 임베딩하면:
1. 벡터 공간에서 의미가 희석됨 (106개가 하나의 벡터에 뭉개짐)
2. LLM 컨텍스트에서 "Lost in the Middle" — 중간에 있는 포트를 무시함
3. "Power 관련 포트가 뭐야?"라는 질문에 정확히 답할 수 없음

**해결:** 포트를 기능별로 그룹핑하여 **카테고리당 하나의 claim**을 생성한다.

| 카테고리 | 매칭 패턴 (정규식) | 의미 |
|----------|-------------------|------|
| PRTN_Power | `PRTNUN_`, `ISO_EN`, `power_good` | 전원 파티션, 아이솔레이션 |
| EDC_APB | `edc_apb_`, `edc_.*irq` | EDC 서브시스템 인터페이스 |
| AXI_Interface | `npu_out_`, `npu_in_`, `axi_` | 외부 버스 인터페이스 |
| APB_Register | `i_reg_`, `o_reg_` | 레지스터 접근 |
| DM_Clock_Reset | `i_dm_clk`, `i_dm_*_reset` | DM 도메인 클럭/리셋 |
| AI_Clock_Reset | `i_ai_clk`, `i_ai_reset` | AI 도메인 클럭/리셋 |
| NoC_Clock_Reset | `i_noc_clk`, `i_noc_reset` | NoC 도메인 클럭/리셋 |
| Tensix_Reset | `i_tensix_reset` | Tensix 코어 리셋 |
| SFR_Memory_Config | `SFR_`, `sfr_` | SRAM 설정 레지스터 |

**결과:** 106개 포트 → 9개 카테고리 claim + 1개 Other claim = 10개 레코드. 각각이 독립적으로 검색 가능.

---

## 4. 검색 설계

### 4.1 인덱스 구조

KB에는 3가지 타입의 레코드가 공존한다:

| analysis_type | 생성 주체 | 건수 | 성격 |
|---------------|----------|------|------|
| `module_parse` | 기본 파서 | ~10,000 | 원본 구조 데이터 (넓고 얕음) |
| `claim` | Package Parser + Port Classifier + LLM | ~140 | 구조화된 사실 (좁고 깊음) |
| `hdd_section` | LLM 생성 | ~12 | 문맥이 풍부한 서술 |

### 4.2 검색 가중치 전략

검색 시 `claim`에 가장 높은 boost(3.0)를 준다. 이유:

- `module_parse`는 양이 많지만 정보 밀도가 낮음 (포트 목록 나열)
- `claim`은 양이 적지만 **질문에 직접 답하는 형태**로 구조화되어 있음
- `hdd_section`은 문맥이 풍부하지만 LLM이 생성한 것이라 순환 참조 위험

### 4.3 max_results의 의미

검색 결과 상위 N건만 LLM에게 전달된다. 이 N이 곧 **KB의 유효 범위**다.

- `max_results=20` (v6까지): 파서가 아무리 많은 claim을 만들어도 상위 20건만 보임
- `max_results=50` (v7~): 같은 KB에서 더 많은 claim이 노출됨

이것이 "공급 vs 소비" 프레임워크의 핵심이다. v6에서 Port Classifier가 106개 포트를 전부 분류해놨지만, 검색 cutoff 20건에 가려져 31개만 보였다. max_results=50으로 바꾸자 나머지 75개가 한 번에 노출됐다.

---

## 5. 현재 한계와 개선 방향

### 5.1 파서가 못 잡는 RTL 구조 (v9.2 기준 — 남은 갭)

| RTL 구조 | 예시 | 담고 있는 정보 | 상태 |
|----------|------|---------------|------|
| `always_ff` 블록 | `always_ff @(posedge clk)` | 클럭 도메인 | ✅ 해결 (Always Block Parser) |
| `always_comb` 블록 | `always_comb begin ... end` | FSM, mux 선택 | ❌ 미지원 |
| `assign` 문 | `assign o_data = sel ? a : b;` | 신호 구동 관계 | ❌ 미지원 |
| `generate for` | `for (genvar i=0; i<SizeX; i++)` | 토폴로지, 인스턴스 위치 | ✅ 해결 (Generate Block Parser) |
| `generate if` | `if (FEATURE_EN) begin ... end` | 조건부 bypass | ✅ 해결 (Generate Block Parser) |
| `function` / `task` | `function automatic int ...` | 인덱스 계산 | ✅ 해결 (Package Function Extractor) |
| wire 선언 | `struct_t sig [SizeX][SizeY]` | 배선 구조 | ✅ 해결 (Wire Declaration Parser) |
| `interface` / `modport` | `interface axi_if` | 구조화된 포트 번들 | ❌ 미지원 |

### 5.2 파서 아키텍처 (v9.2 현재)

v9.2에서 파서 분리가 완료되었다. 각 파서는 독립적으로 feature flag로 제어 가능하다.

```
v9.2 파서 아키텍처 (8종)
─────────────────────────
① 기본 모듈 파서          → module_parse 레코드 (구조)
② Package Parser          → claim (localparam, enum, struct, function, EP Table)
③ Port Classifier         → claim (포트 기능 분류)
④ Generate Block Parser   → claim (토폴로지, 인스턴스 위치, repeater)
⑤ Always Block Parser     → claim (클럭 도메인, CDC 경고)
⑥ Bitwidth Evaluator      → 내부 유틸 (표현식 → 정수 평가)
⑦ Wire Declaration Parser → claim (wire 배열, struct 참조, 목적 유추)
⑧ 대형 모듈 청킹          → module_parse_chunk (50+ 포트 모듈 분할)
```

**Feature Flag 제어:** 환경 변수 `PARSER_*_ENABLED` (기본값 모두 `true`)로 A/B 테스트 가능.

**파서별 기여도 측정:** CloudWatch `BOS-AI/RTLParser` 네임스페이스에 `ParserClaimCount`, `ParserExecutionTime`, `ParserHitRatio` 메트릭 발행.

### 5.3 검색 측 (v9.2 구현 완료)

| 영역 | v1.0 상태 | v9.2 상태 |
|------|----------|----------|
| 임베딩 | Titan v2 단일 모델 | Titan v2 (변경 없음) |
| 청킹 | 모듈 단위 (1 모듈 = 1 레코드) | ✅ 대형 모듈 분할 (50+ 포트 → 3 Sub_Record) |
| 하이브리드 검색 | 벡터 + 키워드 고정 비율 | ✅ 질의 유형별 동적 Boost (5가지 유형) |
| 그래프 검색 | 미구현 | ✅ Neptune Graph DB (인스턴스 트리, 신호 경로, CDC) |
| Grounding | No Grounding only | ✅ Hybrid Grounding (strict/hybrid/free 3모드) |

### 5.4 동적 Boost 상세 (v9.2)

| 질의 유형 | claim boost | module_parse boost | 매칭 키워드 |
|-----------|------------|-------------------|------------|
| port_query | 4.0 | 0.5 | port, pin, signal, interface |
| hierarchy_query | 1.5 | 3.0 | instance, hierarchy, tree, sub-module |
| config_query | 4.0 | 1.0 | parameter, config, constant, setting |
| connectivity_query | 4.0 | 1.0 | connect, wire, route, topology |
| general_query | 3.0 | 1.0 | (default fallback) |

---

## 6. 시스템 아키텍처 (참고)

```
On-Premises                          AWS Seoul                    AWS Virginia
─────────────                        ─────────                    ────────────
엔지니어                              API Gateway (Private)        OpenSearch Serverless
  ↓                                     ↓                           (벡터 인덱스)
Obot → MCP Bridge (server02:3100)    Main Lambda
         ↓ HTTPS                        ↓                         Bedrock
       VPN → TGW → VPC Endpoint     RTL Parser Lambda              Titan Embed v2
                                     ┌─────────────┐               Claude 3 Haiku
                                     │ 기본 파서     │
                                     │ Package 파서  │
                                     │ Port 분류기   │
                                     │ 임베딩        │
                                     │ 인덱싱        │
                                     └─────────────┘
```

**인프라 상세는 별도 문서 참조:** 네트워크, VPC, IAM 등은 인프라 문서에서 다룬다. 이 문서는 파이프라인 로직에 집중한다.

---

## 7. 피드백 요청 (AI Engineer 관점)

1. **파서 분리 우선순위:** Behavior 파서와 Connectivity 파서 중 어느 쪽이 품질 기여도가 클까?
2. **임베딩 전략:** 코드 조각 vs claim(자연어) 중 어느 쪽을 더 늘려야 하는가?
3. **청킹 전략:** 대형 모듈(포트 100+)의 최적 분할 단위는?
4. **그래프 DB 활용:** Neptune 도입 시 가장 먼저 구현할 쿼리 패턴은?
5. **품질 측정:** Content Fidelity 외에 추가할 자동화 지표는?

---

*피드백: Confluence 댓글 또는 Slack #bos-ai-rag*
