# v10 RTL Semantic Graph — 요구사항 초안 (Draft)

> **상태:** 초안 — v9.3 완료 후 피드백 반영하여 확정 예정
> **목표:** RTL RAG를 "텍스트 chunk 검색"에서 "elaborated semantic graph 기반 검색"으로 전환하여, 어떤 RTL이든 동일한 품질로 인덱싱/검색 가능하게 한다.
> **품질 목표:** Content Fidelity 85% → 92%+ (RTL 단독), 새로운 RTL 투입 시에도 80%+ 유지

## 배경

v9.2까지의 정규식 파서는 Trinity-specific 패턴(de_to_t6, EP=X*5+Y 등)에 의존한다.
다른 RTL을 넣으면 와이어 이름, EP 공식, generate 구조가 달라 파서가 깨진다.
근본 해결: RTL을 컴파일러 수준으로 elaboration하여 typed semantic graph를 생성하고,
그 그래프에서 검색한 evidence path를 LLM에게 주는 구조로 전환한다.

## 핵심 아이디어 (2명의 피드백 종합)

### 1번 관점: RTL Semantic IR + Graph-aware Retrieval
- Neptune edge 타입을 15종 이상으로 확장
- 모든 node/edge에 source provenance (file, line, hier_path, generate_scope) 부착
- Multi-vector 임베딩: symbol / structural / claim / exact lexical
- Graph-first retrieval: intent가 topology/connectivity면 vector보다 graph query 우선
- Self-supervised RTL2Vec: RTL 자체에서 positive/negative pair 자동 생성

### 2번 관점: Slang AST-first RAG
- Slang 컴파일러(Microsoft 오픈소스)로 SystemVerilog-2017 full AST 생성
- typedef 해소, generate expansion, parameter elaboration 자동 수행
- AST 노드 단위 chunking + symbol table 자동 생성
- BM25 + 벡터 + 그래프 하이브리드 검색 + RRF 랭킹
- Cross-encoder reranker (Cohere Rerank-v3 또는 BGE-reranker)

## Phase 구성 (잠정)

### Phase 10.0: Slang AST 파일럿
- ECR 컨테이너에 Slang C++ 바이너리 통합
- Trinity filelist/include path 셋업
- Slang JSON AST 출력 → Python 파서로 노드 추출
- 기존 정규식 파서와 결과 비교 (A/B 테스트)

### Phase 10.1: Neptune Semantic Graph Schema 확장
- Edge 타입 확장:
  - BINDS_PORT (v9.3에서 시작)
  - ASSIGNED_FROM (assign 문)
  - ALIASES (wire alias)
  - BIT_SLICE_OF (bus slice)
  - PART_OF_BUS (bus family)
  - CLOCKED_BY, RESET_BY (always_ff sensitivity)
  - PARAM_SPECIALIZED_AS (parameter override)
  - GENERATED_FROM (generate expansion)
  - TYPE_OF, FIELD_OF (struct/typedef)
  - CROSSES_CLOCK_DOMAIN (CDC)
- Node/Edge 공통 속성:
  - source_file, line_range, hier_path, generate_scope
  - condition, bit_range, resolved_width, confidence

### Phase 10.2: Graph-first Retrieval
- Intent classifier: topology/connectivity/hierarchy/clock/port → graph query 우선
- Graph query → evidence path 추출 → LLM context
- Vector search는 설명 보강용으로 격하
- Reciprocal Rank Fusion (BM25 + vector + graph)

### Phase 10.3: Self-supervised RTL2Vec
- Positive pair 자동 생성:
  - .port(signal) ↔ signal declaration
  - instance port ↔ parent net
  - assign lhs ↔ rhs
  - module instance ↔ module definition
  - typedef usage ↔ typedef definition
  - same bus family: req/resp, valid/ready, addr/data
- Hard negative 자동 생성:
  - 같은 이름 다른 hierarchy scope
  - 같은 port명 다른 instance
  - 같은 AXI 계열 in/out 방향 반대
- Fine-tune: Voyage-code-3 또는 jina-embeddings-v3 기반
- Eval set: RTL에서 자동 생성한 Q/A로 recall@k, path accuracy 측정

### Phase 10.4: Cross-encoder Reranker
- 1차: 50개 cheap 후보 (BM25 + vector + graph)
- 2차: Reranker로 top 10 재정렬
- Bedrock 환경에서 사용 가능한 reranker 선택 (Cohere on Bedrock 또는 self-hosted)

## 선행 조건 (v9.3에서 확보)

- [x] Neptune Graph DB 운영 중 (Phase 6)
- [ ] Port Binding Parser → BINDS_PORT/CONNECTS_TO edge (v9.3 Task 29)
- [ ] Graph Export API → evidence bundle export 기반 (v9.3 Task 30)
- [ ] ECR 컨테이너 Dockerfile 준비 (Phase 1에서 뼈대 작성)
- [ ] Feature flag 기반 파서 A/B 테스트 인프라 (Phase 7)

## 트레이드오프 & 리스크

| 항목 | 리스크 | 완화 방안 |
|------|--------|----------|
| Slang C++ 빌드 | 프로젝트마다 filelist/include 다름 | Trinity 먼저 파일럿, 범용 filelist 생성기 개발 |
| 인덱싱 시간 증가 | AST elaboration 10~50배 느림 | 증분 인덱싱 (변경 파일만), 캐시 |
| Titan 임베딩 한계 | 코드 특화 모델 아님 | Voyage-code-3 또는 jina-embeddings-v3 평가 |
| Neptune 비용 | edge 15종 × 대규모 RTL | db.t4g.medium 유지, 필요시 r6g.large |
| Lambda 타임아웃 | Slang elaboration 시간 | Step Functions 또는 ECS Fargate 전환 검토 |

## 성공 지표

| 지표 | v9.3 기준 | v10 목표 |
|------|----------|---------|
| Content Fidelity (Trinity) | 85~88% | 92%+ |
| Content Fidelity (새 RTL) | 측정 안 됨 | 80%+ |
| 신호 추적 정확도 | graph path 기반 | 95%+ (elaborated) |
| 인덱싱 시간 (Trinity) | ~30초 | ~3분 (AST) |
| 검색 latency (P95) | ~5초 | ~8초 (graph+vector+rerank) |

## 참조 문서

- 1번 친구 피드백: RTL Semantic IR + Graph-aware Retrieval + RTL2Vec
- 2번 친구 피드백: Slang AST-first RAG + BM25/RRF + Cross-encoder
- v9.3 design.md Phase 9 섹션
- `docs/8_enhanced-rag-optimization/rtl-rag-pipeline-architecture-ai-engineer.md`

## TODO (v9.3 완료 후)

- [ ] Slang 빌드 환경 PoC (Docker + Trinity filelist)
- [ ] Neptune edge schema v2 확정 (15종 edge + 공통 속성)
- [ ] Graph-first retrieval 프로토타입 (Neptune query → LLM context)
- [ ] 코드 특화 임베딩 모델 벤치마크 (Titan vs Voyage-code-3 vs jina)
- [ ] RTL2Vec training pair 자동 생성기 설계
- [ ] v9.3 피드백 반영하여 이 문서 확정
