# RTL RAG 파이프라인 아키텍처 — AI Engineer 편

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-05-04 | 초판. 원본(rtl-rag-pipeline-architecture.md)에서 AI Engineer 관점으로 분리 |

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
│  Layer 1: 구조 (Structure)                       │  ← RTL에서 직접 추출 가능
│  모듈명, 포트, 파라미터, 인스턴스 계층            │
├─────────────────────────────────────────────────┤
│  Layer 2: 타입/설정 (Type/Config)                │  ← 패키지 파일에서 추출 가능
│  localparam, enum, struct, 그리드 크기            │
├─────────────────────────────────────────────────┤
│  Layer 3: 인터페이스 분류 (Interface)             │  ← 패턴 매칭으로 분류 가능
│  포트의 기능별 그룹핑 (Power, AXI, Clock 등)      │
├─────────────────────────────────────────────────┤
│  Layer 4: 동작 (Behavior)                        │  ← always/assign 분석 필요
│  FSM, 데이터패스, 클럭 도메인 크로싱              │     (현재 미지원)
├─────────────────────────────────────────────────┤
│  Layer 5: 연결 (Connectivity)                    │  ← generate 블록 분석 필요
│  배선 토폴로지, ring/mesh, feedthrough            │     (현재 미지원)
├─────────────────────────────────────────────────┤
│  Layer 6: 설계 의도 (Intent)                     │  ← RTL에 없음. Spec 문서 필요
│  "왜 이렇게 설계했는가", 비교 테이블, 제약 조건    │
└─────────────────────────────────────────────────┘
```

**현재 파이프라인은 Layer 1~3을 커버한다.** Layer 4~5가 다음 개선 대상이고, Layer 6은 Spec RAG가 필요하다.

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
│      → localparam, enum, struct 추출                  │
│      → claim 레코드 생성 (~30건)                      │
│                                                       │
│  2b. Port Classifier (포트 10개+ 모듈)                │
│      → 9개 기능 카테고리로 포트 분류                   │
│      → 카테고리별 claim 레코드 생성 (~11건)            │
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

### 5.1 파서가 못 잡는 RTL 구조

| RTL 구조 | 예시 | 담고 있는 정보 | 개선 방향 |
|----------|------|---------------|----------|
| `always_ff` 블록 | `always_ff @(posedge clk)` | FSM 상태 전이, 레지스터 업데이트 | **Behavior 파서** — FSM 추출, 클럭 도메인 식별 |
| `always_comb` 블록 | `always_comb begin ... end` | 조합 로직, mux 선택 | **Behavior 파서** — 데이터패스 추출 |
| `assign` 문 | `assign o_data = sel ? a : b;` | 신호 구동 관계 | **Connectivity 파서** — 신호 그래프 구축 |
| `generate for` | `for (genvar i=0; i<SizeX; i++)` | 타일 배열, 반복 구조 | **Generate 파서** — 토폴로지 추출 |
| `generate if` | `if (FEATURE_EN) begin ... end` | 조건부 하드웨어 | **Generate 파서** — 설정별 구조 차이 |

### 5.2 파서 분리 로드맵

현재 파서들은 역할이 섞여 있다. 기여도 측정이 어렵고 확장성에 제약이 있다. 다음 단계에서 역할별 분리를 고려 중:

```
현재                              목표
─────                            ─────
기본 모듈 파서 (전부 다 함)        Structure 파서 (hierarchy, 인스턴스 트리)
                                  Interface 파서 (Port Classifier 확장)
Package Parser                    Type 파서 (localparam, enum, struct, function)
                                  Behavior 파서 (always/assign → FSM, 데이터패스)  ← 신규
                                  Connectivity 파서 (generate → 토폴로지, 배선)    ← 신규
```

**목적:** 각 파서의 기여도를 독립 측정 → 다음 투자 포인트 식별

### 5.3 검색 측 개선 방향

| 영역 | 현재 | 개선 방향 |
|------|------|----------|
| 임베딩 | Titan v2 단일 모델 | 코드 특화 임베딩 모델 비교 실험 |
| 청킹 | 모듈 단위 (1 모듈 = 1 레코드) | 대형 모듈 분할 전략 (포트/인스턴스/로직 별도) |
| 하이브리드 검색 | 벡터 + 키워드 고정 비율 | 질의 유형별 동적 비율 조정 |
| 그래프 검색 | 미구현 (Neptune 준비 중) | 관계 기반 탐색 (인스턴스 트리, 신호 경로) |

### 5.4 Hybrid Grounding (다음 버전)

현재 RAG의 딜레마:
- **Grounded 모드:** KB에 있는 것만 기술 → 거짓말 없음, 빈 섹션 많음
- **No Grounding:** 자유 서술 → 문서는 꽉 차지만 환각 발생

**Hybrid 모드 = 제3의 길:**

```markdown
## NoC Routing Algorithm

[GROUNDED from KB]
지원 알고리즘 3종: DOR, Tendril, Dynamic (tt_noc_pkg.sv)

[INFERRED by LLM]
DOR는 일반적으로 X-first 순서로 동작하며, 데드락 방지를 위해
VC 2개 이상을 사용합니다. ※ Spec 확인 필요.
```

검증 엔지니어는 `[GROUNDED]`는 신뢰하고 `[INFERRED]`만 검토하면 됨.

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
