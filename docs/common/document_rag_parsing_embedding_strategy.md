# Document RAG — 파싱 + 임베딩 전략 (근거 기반 / 인프라 정합본)

**대상 1차 문서:** `DW_apb_gpio_databook_2.16a.pdf` (Synopsys IP Databook, 39p)
**참고:** `dw_apb_gpio_rag_embedding_strategy.md` (ChatGPT 초안)
**작성 기준:** 실제 PDF 구조 검증 + 현재 `aws_private_rag` 인프라(RTL RAG) 재사용
**핵심 원칙:** 새 스택을 만들지 않는다. RTL RAG 파이프라인에 "문서 파서"를 끼운다. 규모에 맞게 단순하게.

---

## 0. 이 문서가 ChatGPT 초안과 다른 점 (요약)

ChatGPT 초안의 객체 분해(parameter/signal/register/bitfield/section/figure) **방향성은 옳다**. 다만 실제 PDF와 우리 인프라를 검증한 결과 다음을 보정한다.

| 항목 | ChatGPT 초안 | 본 전략 (검증 후) |
|---|---|---|
| PDF table 추출 리스크 | "깨질 수 있음, table parser+validation 필요" (高 리스크) | **라벨 기반 결정론적 파서로 충분**. 모든 객체가 `Name:`/`Offset:`/`Enabled:` 등 규칙적 라벨 블록 |
| 조건식 정규화 | "자연어→boolean 변환 필요" (리스크) | **이미 `==`/`\|\|` 기계가독 식**. 정규화 거의 불필요 (예: `Exists: GPIO_PORTA_INTR==1`) |
| relation_store | 별도 graph-lite store 신설 | **기존 Neptune 그래프 재사용** (RTL이 이미 사용 중) |
| reranker / query classifier | cross-encoder + LLM reranker + 분류기 | **1차 범위에서 제외**. KB 벡터 + 메타데이터 필터 + 심볼 exact로 충분. 품질 부족시 추가 |
| 인덱스 아키텍처 | 4개 store 신설(vector×2/keyword/metadata/relation) | **기존 3-tier 재사용**: Bedrock KB(벡터) + DynamoDB(객체/메타) + Neptune(관계) |
| 5단계 source priority | databook + coreConsultant 5종 우선순위 | **2-tier로 단순화**: generated artifact(있으면) > databook. 나머지는 후순위 |

> 한 줄 요약: **"IP reference object RAG"라는 ChatGPT의 결론은 채택하되, 저장/검색은 우리가 이미 운영 중인 RTL RAG 인프라를 그대로 재사용한다.**

---

## 1. 실제 문서 구조 (검증된 근거)

`pdftotext -layout`로 추출해 확인한 실제 레이아웃. 파서 설계의 근거다.

### 1.1 Parameter (Ch4)
```
APB Data Bus Width      Specifies the width of APB Data Bus to which this component is attached.
                        Values: 8, 16, 32
                        Default Value: 32
                        Enabled: Always
                        Parameter Name: APB_DATA_WIDTH
```
- 고정 라벨: `Values:` / `Default Value:` / `Enabled:` / `Parameter Name:`
- 좌측 = 사람용 Label, 본문 = Description, `Parameter Name:` = 정규 심볼
- **Enabled 조건이 이미 식**: `Enabled: GPIO_PA_SYNC_INTERRUPTS==1 || GPIO_PA_SYNC_EXT_DATA==1`

### 1.2 Register (Ch6)
```
6.1.1 GPIO_SWPORTA_DR
          Name: Port A data register
          Description: Port A data register
          Size: 32 bits
          Offset: 0x0
          Exists: Always

Table 6-5 Fields for Register: GPIO_SWPORTA_DR
Bits  Name                   Memory Access   Description
31:y  RSVD_GPIO_SWPORTA_DR   R               ...
```
- 레지스터 헤더: `N.N.N <NAME>` + `Name:`/`Description:`/`Size:`/`Offset:`/`Exists:`
- 비트필드: `Table 6-N Fields for Register: <NAME>` 직후 `Bits / Name / Memory Access / Description` 컬럼
- ⚠️ 주의: 이 테이블에는 **Reset 컬럼이 항상 있는 건 아님**(Bits/Name/Access/Description만 있는 경우 존재). Reset은 별도 표기 → 파서는 Reset을 optional로.

### 1.3 Signal (Ch5)
- 신호 속성 라벨: `Exists:` / `Synchronous To:` / `Registered:` / `Power Domain:` / `Active State:`
- `Exists:` 역시 기계가독: `Exists: GPIO_PORTA_INTR==1`
- 신호는 `APB Interface / Miscellaneous / Port A~D / Parity Interrupts` 그룹으로 분류됨 → 그룹을 메타데이터로 보존

### 1.4 설명형 / 그림
- Ch1·2·3·7·9: 자연어 설명 (semantic chunk 대상)
- Figure(block/timing/verification diagram): 텍스트 추출 불완전 가능 → caption + 주변 문단으로 1차 처리, vision 요약은 2차(옵션)

---

## 2. 타깃 아키텍처 — 기존 RTL RAG 재사용 맵

```
                                ┌────────────────────────────────────────┐
온프렘 PDF 업로드 ──VPN/TGW──▶  │ Seoul S3 (bos-ai-documents-seoul-v3)     │
                                │   raw/<ip>/<doc_version>/databook.pdf    │
                                └───────────────┬──────────────────────────┘
                                                │ S3 event
                                                ▼
                          ┌─────────────────────────────────────────────┐
                          │ Document Parser Lambda (신규, RTL 파서와 동형) │
                          │  Py3.12 / pdftotext or pdfplumber layer       │
                          │  doc-type 라우팅 → extractor profile 적용     │
                          └───┬───────────────┬──────────────────┬────────┘
            canonical .md     │   structured  │     relations    │  symbols
            (section/object)  │   objects     │                  │
                              ▼               ▼                  ▼
              raw/ →  published/<...>.md   DynamoDB           Neptune        (exact symbol:
              → CRR → Virginia S3          (claim-db 패턴      (기존 그래프    DynamoDB GSI 또는
              → Bedrock KB (Titan v2)       재사용, doc 객체)   재사용)        KB 메타 필터)
                    │
                    ▼
              OpenSearch Serverless (bos-ai-vectors)
                    │
                    ▼
              MCP 툴 (search_doc / doc_query / get_register ...) ── 엔지니어
```

**재사용하는 기존 자산**
- S3 업로드 파이프라인 + CRR (그대로)
- Bedrock KB + OpenSearch Serverless + Titan Embed **v2** (`amazon.titan-embed-text-v2:0`)
- DynamoDB claim-db 스키마 패턴 (객체 = claim과 동형: id/type/canonical_text/metadata/evidence)
- Neptune 그래프 (parameter→register/signal exists 관계)
- Step Functions 오케스트레이션 패턴 (stage 분리 + skip-on-failure)
- MCP bridge 툴 노출 메커니즘

**신규로 만드는 것 (최소)**
1. Document Parser Lambda (라벨 기반 결정론적 파서 + doc-type 라우팅)
2. `published/` 아래 문서 RAG용 corpus prefix 분리 (RTL과 분리)
3. MCP 툴 3~4개 (doc_query / search_doc_symbol / get_register / get_parameter)

---

## 3. 파싱 전략

### 3.1 결정론적 라벨 파서 (LLM 비의존)
객체 추출의 90%는 정규식/라벨 스캔으로 처리한다. LLM 추출은 **canonical_text 문장 생성**과 **figure 요약**에만 보조적으로 사용(비용·환각 최소화).

```
1) pdftotext -layout 로 텍스트화 + 페이지 경계 매핑
2) TOC 파싱으로 chapter/section 경계 + 페이지 범위 확정
3) chapter별 extractor 적용:
   - Ch4  → ParameterExtractor   (Label/Values/Default/Enabled/Parameter Name 블록)
   - Ch5  → SignalExtractor       (그룹 + Exists/Sync/Registered/PowerDomain/ActiveState)
   - Ch6  → RegisterExtractor     (헤더 5필드 + "Table 6-N Fields" 비트필드 테이블)
   - Ch1/2/3/7/9 → SectionChunker (semantic chunk)
   - Figure → FigureExtractor     (caption + 주변 문단, vision 요약은 옵션)
4) 조건식: 이미 ==/||/!= 형태 → 그대로 보존 (parse 실패시 원문 string 보관, 절대 버리지 않음)
5) 심볼 정규화: GPIO_SWPORTA_DR / gpio_swporta_dr / SWPORTA_DR 동의어 셋 생성
```

### 3.2 객체 분류 (object_type)
ChatGPT 초안 taxonomy 채택. 단, 저장은 claim-db 패턴으로 통일.
```
section(overview/functional/safety/programming/verification/integration)
parameter | internal_parameter | signal | register | bitfield
figure_summary | glossary_term
```

### 3.3 공통 객체 스키마 (claim-db 호환)
모든 객체를 동일 레코드 형태로 저장 → 기존 DynamoDB/MCP 패턴 재사용.
```json
{
  "id": "doc#dw_apb_gpio#2.16a#register#GPIO_SWPORTA_DR",
  "doc_type": "synopsys_ip_databook",
  "object_type": "register",
  "ip": "DW_apb_gpio",
  "doc_version": "2.16a",
  "name": "GPIO_SWPORTA_DR",
  "canonical_text": "Register GPIO_SWPORTA_DR (Port A data register), offset 0x0, size 32 bits, exists Always.",
  "metadata": {
    "offset": "0x0", "size_bits": 32, "exists_expr": "Always",
    "chapter": "6", "section": "6.1.1", "page": 102
  },
  "relations": [
    {"type": "has_bitfield", "target": "RSVD_GPIO_SWPORTA_DR"},
    {"type": "controlled_by", "target": "GPIO_SWPORTA_RESET"}
  ],
  "evidence": {"source_file": "DW_apb_gpio_databook_2.16a.pdf", "page": 102}
}
```
- `canonical_text`가 임베딩 대상(객체 1개 = 벡터 1개)
- `metadata.*`가 필터 키 (offset/exists_expr/object_type/ip/doc_version)
- `relations`가 Neptune 적재 소스 (RTL과 동일 그래프, 노드 라벨만 다름)

---

## 4. 임베딩 / Chunking 전략 (Bedrock KB 정합)

Bedrock KB는 S3의 텍스트 + `.metadata.json` 사이드카를 함께 인덱싱한다. 두 종류를 `published/`에 올린다.

### 4.1 설명형 section → semantic chunk
- 단위: subsection(`N.N`) 기준. 700~1200 토큰, overlap 100~150 (초안 수치 채택)
- 파일: `published/doc/dw_apb_gpio/2.16a/section/2.3_interrupts.md` + 동명 `.metadata.json`
- KB chunking: section을 이미 잘라 올리므로 **NONE(사전 청크) 또는 FIXED 큰 값** 사용 → 자연 경계 보존

### 4.2 구조화 객체 → object 1개 = chunk 1개
- 각 객체의 `canonical_text`를 짧은 .md 1개로 publish + metadata 사이드카
- 객체는 의미 단위가 작고 검색 타깃이 명확 → **무조건 1객체 1청크** (KB 자동 청킹에 맡기지 않음)

### 4.3 임베딩 모델
- 기존 운영 모델 **Titan Embed Text v2** 그대로 (RTL과 동일 collection/차원 정합)
- 별도 모델 도입 안 함 (운영 단순성)

### 4.4 심볼 검색 보강 (dense 단독 회피)
초안의 핵심 지적("symbol-heavy 문서는 dense만으로 부족")은 타당. 단 **새 BM25 인덱스 신설 대신**:
1. 1차: DynamoDB GSI에 `name` / 동의어 셋으로 exact lookup (offset/심볼/레지스터명)
2. 2차: KB 벡터 + `object_type`·`ip`·`doc_version` 메타데이터 필터
3. exact hit가 있으면 그 객체를 컨텍스트 최상단에 고정

→ 대부분의 심볼/offset/bitfield 질의는 GSI exact로 결정적으로 해결, 개념 질의는 벡터로.

---

## 5. Retrieval & 답변 정책 (단순화)

```
1. 질의에 심볼 패턴(GPIO_*, gpio_*, 0x..., offset/bit/reset) 포함?
     예 → DynamoDB GSI exact lookup 우선 → 객체 + parent/relation 동봉
     아니오 → KB 벡터 검색 (+ 메타 필터)
2. 컨텍스트 조립: 직접 객체 → parent register/section → 관련 parameter/signal(relation)
3. 답변 규칙:
   - parameter/exists 조건은 반드시 함께 표기
   - offset/access/reset은 metadata에서 직접 인용(생성 금지)
   - generated artifact(ComponentRegisters.xml 등)가 있으면 그것을 우선,
     없으면 "databook 일반값이며 실제 config와 다를 수 있음" 명시
```
- cross-encoder/LLM reranker는 **도입하지 않음**(1차). 품질 측정 후 필요시 추가.

---

## 6. 확장성 설계 — doc-type registry (핵심 요구사항)

다른 문서 유형이 추가돼도 파이프라인 골격은 불변. **무엇이 바뀌고 무엇이 고정인지**를 분리한다.

### 6.1 고정(공통) 레이어
- S3 업로드/CRR, Bedrock KB, DynamoDB 객체 스키마, Neptune 관계, MCP 툴 골격
- 공통 객체 레코드 형태(§3.3) — 모든 doc_type이 동일 형태로 저장

### 6.2 가변(플러그인) 레이어 = Extractor Profile
doc_type마다 "프로파일" 하나만 추가하면 된다.
```yaml
# profiles/synopsys_ip_databook.yaml  (선언적)
doc_type: synopsys_ip_databook
detect:                       # 자동 식별 규칙
  - text_contains: "Synopsys IP"
  - text_contains: "Databook"
toc:
  pattern: "^Chapter\\s+(\\d+)\\s+(.+?)\\.{3,}\\s*(\\d+)$"
extractors:
  - chapter: 4
    type: label_block
    object_type: parameter
    labels: [Values, "Default Value", Enabled, "Parameter Name"]
  - chapter: 6
    type: register_with_fields
    header_labels: [Name, Description, Size, Offset, Exists]
    field_table: "Table \\d+-\\d+ Fields for Register:"
  - chapters: [1,2,3,7,9]
    type: section_chunk
    tokens: [700, 1200]
```
- 새 문서 유형(예: ARM TRM, 사내 design spec, app note) = **새 YAML 프로파일 + (필요시) extractor 타입 1개** 추가
- extractor 타입 라이브러리는 재사용: `label_block`, `register_with_fields`, `signal_table`, `section_chunk`, `figure`, `kv_table` …
- `detect` 규칙으로 업로드 문서의 doc_type 자동 판별 → 잘못 판별돼도 수동 override 가능(복잡도 최소화: 자동 실패시 수동 OK)

### 6.3 확장 시 변경 범위
| 추가 항목 | 변경 위치 |
|---|---|
| 같은 유형 다른 IP/버전 | 변경 없음 (메타데이터만 다름) |
| 새 문서 유형, 기존 extractor 조합 | YAML 프로파일 1개 |
| 새 문서 유형, 새 구조 | YAML + extractor 타입 1개 (Python) |
| 새 검색 패턴 | MCP 툴 1개 |

→ 파이프라인/저장/임베딩은 손대지 않는다. 이것이 확장성의 핵심.

---

## 7. 구현 단계 (phased, 기존 패턴 차용)

**Phase 1 — 단일 문서 MVP (수동 트리거 OK)**
1. `pdftotext -layout` 추출 + TOC/페이지 매핑
2. Parameter / Register / Bitfield extractor (가장 정형적, 검색가치 높음)
3. 객체 → DynamoDB + canonical .md → S3 → KB 인덱싱
4. MCP 툴: `get_register(offset|name)`, `get_parameter(name)`, `doc_query(자연어)`
5. QA 셋(§8)로 검증

**Phase 2 — section/signal/figure 확장**
6. SectionChunker + SignalExtractor
7. Neptune 관계 적재(parameter↔register/signal exists)
8. figure caption+주변문단 (vision 요약은 옵션)

**Phase 3 — 확장성 일반화**
9. extractor를 YAML 프로파일로 외부화(§6)
10. doc_type 자동 detect + 2번째 문서 유형 투입으로 검증
11. Step Functions에 doc 파이프라인 stage 편입(RTL과 동형)

> 복잡도 가드: Phase 1은 Lambda 한 개 + 수동 invoke로 시작. Step Functions 편입·자동 트리거는 문서 수가 늘 때 도입.

---

## 8. QA 테스트 셋 (수용 기준)

| No | 질의 | 기대 retrieval | 검증 포인트 |
|---:|---|---|---|
| 1 | `APB_DATA_WIDTH default?` | parameter 객체 | metadata.default=32 직접 인용 |
| 2 | `GPIO_SWPORTA_DR offset?` | register 객체 | GSI exact, offset 0x0 |
| 3 | `offset 0x4 register?` | register 객체 | offset 역방향 lookup |
| 4 | `BIT_SEL은 어느 register?` | bitfield + parent | relation has_bitfield |
| 5 | `GPIO_PA_SYNC_DEPTH 언제 enable?` | parameter + 조건 | `==1 \|\| ==1` 식 표기 |
| 6 | `interrupt debounce 동작 설명` | functional/safety section | 벡터 검색 |
| 7 | `Port A interrupt 관련 param/reg/signal` | relation 묶음 | Neptune 관계 |
| 8 | `block diagram의 APB→GPIO path` | figure + overview | figure 처리 동작 |
| 9 | `generated config가 databook과 다를 수 있나?` | source priority 정책 | 정책 문구 출력 |
| 10| (오탈자 심볼) `GPIO_SWPORT_DR` | 근접 객체 + "정확 매칭 없음" | dense fallback |

---

## 9. 리스크 & 대응 (검증 반영)

| Risk | 평가 | 대응 |
|---|---|---|
| PDF table 깨짐 | **낮음** (라벨 정형) | `-layout` + 라벨 파서. 실패 객체는 raw 문단 보관(누락 금지) |
| 조건식 파싱 | **낮음** (이미 식) | 그대로 보존, parse 실패시 string fallback |
| figure label 누락 | 중 | caption+문단 1차, vision 요약 2차(옵션) |
| Reset 컬럼 부재 | 중 | bitfield reset은 optional 필드 |
| dense 단독 오답 | 중 | GSI exact 우선 라우팅 |
| config drift | 중 | generated artifact 우선 정책, doc_version 메타 필수 |
| 과도 설계 | — | reranker/별도 store/자동분류 1차 제외 |

---

## 10. 결론

1. ChatGPT의 **"IP reference object RAG"** 분해 결론은 옳다 → 채택.
2. 단, 저장·임베딩·검색은 **현 RTL RAG 인프라를 그대로 재사용**한다 (KB+DynamoDB+Neptune+MCP). 새 store 신설 없음.
3. 실제 문서가 정형적이라 **결정론적 라벨 파서로 충분**, LLM은 보조.
4. 조건식은 이미 기계가독 → 정규화 부담 최소.
5. 확장성은 **doc-type registry(YAML 프로파일 + extractor 타입 라이브러리)**로 확보. 공통 레이어는 불변.
6. Phase 1은 Lambda 한 개 + 수동 트리거로 작게 시작, 문서가 늘면 자동화.

> 다음 액션 후보: (a) Phase 1 Parameter/Register extractor 프로토타입 코드 작성, (b) `.kiro/specs/`에 본 전략을 정식 spec(requirements/design/tasks)으로 승격.
