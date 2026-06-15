# Requirements Document

**Feature:** RAG v9.5 Knowledge Import & Retrieval Enhancement

## Introduction

RAG v9.5는 NPU 분석팀(Alpha 4인)이 Claude Desktop/Code를 사용하여 **수동으로 축적한 RTL-verified 지식**(CLAUDE_DBS, 토픽 memory 51개 파일 + N1B0 adapted 10개 + reference docs)을 RAG 시스템에 역수입하고, 동시에 Crash Course 시리즈(Part 1-9)에서 식별된 구조적 개선점(Re-Ranker, Graph RAG 경로 분기, RTL 구문 경계 Chunking, 자동 평가 프레임워크)을 적용하는 릴리즈이다.

> **근거 문서:** 본 requirements는 `docs/common/NPU_Analysis_Team_Report.md`(보완본, 2026-06-01)를 1차 입력 근거로 한다. 수치·범위는 해당 리포트와 정합을 유지한다.

### 배경

NPU 분석팀은 2026-03 ~ 2026-04에 걸쳐 다음을 달성했다:
- N1B0_NPU_HDD_v1.00에서 **9개 오류 발견, 7건 RTL-verified 교정** (SRCA 256→48 rows 5.3× 과대, SRCB 128→64 rows/bank 자기모순, INT16 MAC 64→256/G-Tile 4× 과소, DEST bank당 8,192→1,024 INT32 등)
- **Register file 용량 equation 도출** (Col × Row/Bank × Banks × Bit-Width ÷ 8 공식, 6-level hierarchy decomposition)
- **INT8 8192 MACs/cluster 검증** (NUM_PAIR=8, HALF_FP_BW=1, two-phase latch mechanism)
- **SDC 20260221↔20260404 constraint 비교** (139,783 패턴 100% 동일 확인)
- **EDC ring per-column 토폴로지** V0.9까지 완전 정리 (4 independent rings, harvest bypass mux/demux, composite tile 2-node)
- **51개 토픽별 knowledge memory 파일**(ID는 M1~M52, 결번·중복 ID 포함) + systematic RTL-driven verification methodology (FB4)

이 지식은 현재 팀원 PC의 `test_rtl/Sample/CLAUDE_DBS/` 디렉토리에만 존재하며, RAG 시스템의 Claim DB/Neptune에 반영되어 있지 않다. 결과적으로:
1. RAG가 생성하는 HDD와 NPU 팀이 검증한 HDD 사이에 **정확도 gap**이 존재 (v9.3 정식 평가: 48/100, NPU 팀 수동 작업: 95+/100)
2. NPU 팀의 RTL-verified knowledge가 **검색 불가** — 다른 사용자(Beta 8명)가 같은 질문을 해도 이 지식에 접근 못 함
3. **evaluation ground truth가 없음** — RAG 개선 시 효과 측정 불가

> **측정 기준 (NPU 리포트와 정합):** 정확도는 두 체계로 측정한다.
> - **L1~L6 프레임워크**(`test_rtl/rag_result/prompt.md`): L1 구조 / L2 인터페이스 / L3 연결 / L4 파라미터 / L5 동작 / L6 의도. v9.4a 실측 L1=88%, L4=38%, L5=28%, L6=5%.
> - **Content Fidelity(가중)**: L1~L6 가중 평균. v9.4 계열 ~65%. 최대 병목은 **L4 파라미터(38%)·L5 동작(28%)** — import가 직접 겨냥하는 영역이다.

### 목표

1. CLAUDE_DBS 52개 + N1B0_A* 10개의 RTL-verified knowledge를 Claim DB에 적재하여 **RAG 검색 가능하게** 만든다
2. Cross-encoder **Re-Ranker를 retrieval pipeline에 추가**하여 precision 향상
3. **Query type별 retrieval 경로 분기** — connectivity 질문은 Neptune Graph, parameter 질문은 Claim DB direct, general은 Bedrock KB
4. **RTL 구문 경계 기반 Chunking**으로 struct/module이 chunk 경계에서 잘리는 문제 해결
5. CLAUDE_DBS verified data를 ground truth로 사용하는 **자동 평가 프레임워크** 구축

## Glossary

- **CLAUDE_DBS**: NPU 분석팀이 Claude Desktop/Code로 축적한 RTL-verified knowledge archive (`test_rtl/Sample/CLAUDE_DBS/` 내 토픽 memory 51개 파일 + 10개 N1B0 adapted + reference docs; 디렉토리 총 87개 파일)
- **RTL-Verified Claim**: RTL 소스 파일의 특정 라인 번호에 대한 cross-reference가 포함된, 수동 검증 완료된 지식 단위
- **Re-Ranker**: Retrieval 결과를 query-document 쌍 단위로 재채점하는 Cross-encoder 모델 (Cohere Rerank-v3 또는 Bedrock 호환 모델)
- **Graph RAG Routing**: Query의 의도(connectivity/parameter/general)에 따라 retrieval backend를 분기하는 라우팅 로직
- **Semantic Boundary Chunking**: RTL 구문 경계(module/endmodule, struct/endstruct, generate/endgenerate)를 인식하여 chunk를 분할하는 전략
- **Evaluation Dataset**: CLAUDE_DBS의 verified knowledge를 question-answer 쌍으로 변환한 자동 평가용 데이터셋
- **Content Fidelity Score**: 생성된 HDD 섹션이 ground truth 대비 정확한 fact를 포함하는 비율 (L1~L6 가중 평균; v9.4 계열 ~65%, 목표 85%+)
- **Confidence_Score**: Claim DB 레코드의 신뢰도 점수 (0.0~1.0, RTL-verified = 1.0)
- **Memory_File**: CLAUDE_DBS의 개별 토픽 파일 (예: `m7_tensix_core_hdd.md`, `m14_n1b0_dfx_hdd.md`)
- **Derivation_Chain**: 결론에 이르기까지의 계산 과정 (예: "8×2×2×8×2 = 8192 INT8 MACs/cluster")
- **LiteLLM_Gateway**: 모든 LLM 호출을 중앙 통제하는 게이트웨이 (Re-Ranker API 호출 경유 포함)

---

## Requirements

### Category 1: Knowledge Import (CLAUDE_DBS → Claim DB)

---

### Requirement 1: CLAUDE_DBS Bulk Import Pipeline

**User Story:** As a RAG system operator, I want to bulk-import the 51 CLAUDE_DBS memory files and 10 N1B0 adapted archives into the Claim DB, so that RTL-verified knowledge becomes searchable by all RAG users.

#### Acceptance Criteria

1. WHEN the operator runs the import script with `--source-dir test_rtl/Sample/CLAUDE_DBS/ --pipeline-id tt_20260221`, THE Import_Pipeline SHALL parse each memory file's YAML frontmatter (name, description, type) and markdown body to extract individual knowledge claims
2. WHEN a memory file contains RTL file references with line numbers (e.g., "tt_tensix_pkg.sv:35"), THE Import_Pipeline SHALL create a claim with `evidence_type: rtl_line_reference` and populate `evidence.file_path` and `evidence.line_number` fields
3. WHEN a memory file contains numerical derivations (e.g., "8×2×2×8×2 = 8192"), THE Import_Pipeline SHALL create a claim with `claim_type: derivation` and store the full calculation chain in `claim_text`
4. THE Import_Pipeline SHALL set `confidence_score: 1.0` and `source: rtl_verified_manual` for all imported claims from CLAUDE_DBS
5. THE Import_Pipeline SHALL assign `topic` based on the memory file's keywords field in MEMORY.md index (e.g., keywords containing "edc" → topic "EDC", keywords containing "register_file" → topic "RegisterFile")
6. THE Import_Pipeline SHALL be idempotent: running twice with the same source directory SHALL NOT create duplicate claims (use composite key: source_file + claim_hash)
7. IF a memory file has NO YAML frontmatter (only m31, m40 등 일부 파일만 보유), THEN THE Import_Pipeline SHALL fall back to deriving `name` from the filename and `topic` from the MEMORY.md keywords index, and SHALL NOT skip the file
8. WHEN import completes, THE Import_Pipeline SHALL emit a summary: total_files_processed, total_claims_created, total_claims_skipped (duplicates), total_evidence_records, files_without_frontmatter, execution_time_seconds

---

### Requirement 2: Structured Knowledge Extraction from Memory Files

**User Story:** As a RAG system developer, I want the import pipeline to extract structured claims from free-form markdown memory files, so that individual facts are independently searchable.

#### Acceptance Criteria

1. WHEN a memory file contains a markdown table (e.g., register file dimensions table in M45), THE Import_Pipeline SHALL extract each table row as a separate claim with `claim_type: specification` and preserve column headers as context
2. WHEN a memory file contains a "Key findings" or "Critical" section, THE Import_Pipeline SHALL extract each bullet point as a separate claim with `claim_type: finding` and `priority: high`
3. WHEN a memory file contains correction records (e.g., M40 "Before: SRCA 256 rows, After: 48 rows"), THE Import_Pipeline SHALL create claims for the **corrected** values only, with `supersedes_claim_id` pointing to any existing incorrect claims in the DB
4. WHEN a memory file contains verification status markers (✅, ❌, ⚠️), THE Import_Pipeline SHALL map these to claim status: ✅ → `verified`, ❌ → `deprecated`, ⚠️ → `draft`
5. THE Import_Pipeline SHALL split each memory file into atomic claims such that each claim contains exactly ONE verifiable fact (not compound statements). Average target: 5-15 claims per memory file depending on content density
6. WHEN a memory file references another memory file (e.g., "see M13" or "from M45"), THE Import_Pipeline SHALL create a `derived_from` relationship between the respective claims
7. IF a referenced memory file has not yet been processed at the time of the reference, THEN THE Import_Pipeline SHALL still extract claims from the current file immediately and SHALL establish the `derived_from` relationship later when the referenced file becomes available (deferred linking, not blocking)

---

### Requirement 3: Feedback Rule Import (FB1-FB4 → System Prompt)

**User Story:** As a RAG system operator, I want the feedback rules (FB1-FB4) from CLAUDE_DBS to be encoded as system-level validation rules in the HDD generator, so that RTL-verified methodology is automatically applied.

#### Acceptance Criteria

1. WHEN the HDD_Generator produces any section containing hardware specifications, THE HDD_Generator prompt SHALL include FB4 rule: "모든 HDD 스펙 주장 (register file 크기, MAC throughput, hierarchy, physical parameter)은 RTL 파라미터 대조 없이 accept하지 마라. Claim의 evidence에 RTL file:line이 없으면 [TBC]로 표시하라"
2. WHEN the HDD_Generator references a claim with `source: rtl_verified_manual`, THE HDD_Generator SHALL display it WITHOUT [TBC] tag (이미 검증 완료)
3. WHEN the HDD_Generator produces EDC-related content, THE HDD_Generator prompt SHALL include FB3 rule: "EDC_HDD 최신 버전(V0.9)만 참조하라. 다른 버전과 혼합하지 마라"
4. WHEN a claim has `source: rtl_verified_manual` and another claim with `source: parser_generated` contradicts it, THE HDD_Generator SHALL automatically prefer the `rtl_verified_manual` claim and mark the parser claim `status: conflicted` WITHOUT requiring manual review
5. THE system SHALL log when FB rules trigger: event_type=fb_rule_applied, rule_id=FB1|FB2|FB3|FB4, claim_id, outcome

---

### Requirement 4: N1B0 Adapted Archive Priority

**User Story:** As a semiconductor design engineer, I want N1B0-specific knowledge (N1B0_A1-A10) to take priority over baseline Trinity knowledge when the query context is N1B0, so that answers reflect the correct variant.

#### Acceptance Criteria

1. WHEN a query contains "N1B0" or the pipeline_id is `tt_20260221` (N1B0 baseline), THE Retrieval_Engine SHALL boost N1B0_A* derived claims by factor 2.0 relative to baseline M* claims
2. WHEN both a baseline claim (from M* file) and an N1B0 adapted claim (from N1B0_A* file) match, THE Retrieval_Engine SHALL return the N1B0 claim first and annotate the baseline claim as `variant_note: "baseline Trinity, N1B0에서 변경될 수 있음"`
3. THE Import_Pipeline SHALL tag N1B0_A* derived claims with `variant: N1B0` and M* derived claims with `variant: baseline`. THE Import_Pipeline SHALL strictly enforce that M* files can ONLY be tagged `variant: baseline` (never `variant: N1B0`), even on processing error — on ambiguity it SHALL default to `baseline` and log a warning
4. WHEN a user asks about features that differ between baseline and N1B0 (e.g., L1 size, per-column clock, PRTN chain), THE Retrieval_Engine SHALL return BOTH variants with explicit comparison annotation

---

### Requirement 16: Import 충돌 해소 및 Confidence 우선순위 정책

**User Story:** As a RAG system operator, I want NPU verified claims to take priority over parser-generated claims when they describe the same fact, so that users always see the RTL-verified value and never stale or lower-confidence parser output.

> **근거:** NPU 리포트 §7 논의사항 2. NPU verified claim(`source: rtl_verified_manual`, `confidence_score: 1.0`)이 기존 파서 claim(`source: parser_generated`, `confidence_score: 0.5~0.7`)과 같은 fact를 기술할 때의 충돌·중복을 해소한다.

#### Acceptance Criteria

1. THE Import_Pipeline SHALL compute a `fact_key` for each claim as a hash of (`module_name` + `topic` + 정규화된 claim 주어/대상), **EXCLUDING the asserted value**, so that "SRCA = 256 rows"와 "SRCA = 48 rows"가 동일 `fact_key`로 묶인다 (값이 달라도 같은 fact로 인식)
2. WHEN an imported NPU claim shares a `fact_key` with an existing parser claim AND the asserted values are IDENTICAL, THE Import_Pipeline SHALL treat it as a duplicate fact: keep the NPU claim, and mark the parser claim `status: superseded` with `superseded_by` pointing to the NPU claim. 이 dedup 판정은 NPU claim을 **능동적으로 import하는 시점에만** 수행한다 (이미 적재된 claim 간 재-dedup은 하지 않음)
3. WHEN an imported NPU claim shares a `fact_key` with an existing parser claim AND the asserted values DIFFER (correction case, e.g., M40 SRCA 256→48), THE Import_Pipeline SHALL set the NPU claim's `supersedes_claim_id` to the parser claim and mark the parser claim `status: superseded` (정합: Req 2.3, Req 15.4)
4. WHILE serving a query, THE Retrieval_Engine SHALL exclude `status: superseded` claims from default results (감사·correction_history 목적으로 DB에는 보존; Req 15.4와 정합)
5. WHEN two or more non-superseded candidates have equal retrieval relevance, THE Retrieval_Engine SHALL order them deterministically by `confidence_score` descending (1.0 > 0.7 > 0.5). 이 정렬은 Req 5 Re-Ranker 점수가 동률일 때만 적용된다 (Re-Ranker 우선)
6. WHEN two claims share a `fact_key`, both have `confidence_score: 1.0`, but assert DIFFERENT values (예: 서로 다른 NPU memory 간 모순), THE Import_Pipeline SHALL mark BOTH `status: conflicted`, SHALL NOT auto-supersede either, and SHALL emit an operator-review log
7. WHEN de-duplication collapses claims at retrieval-exposure time, THE Retrieval_Engine SHALL surface only the highest-priority claim per `fact_key` and SHALL annotate it with `deduped_count` (suppressed 동일-fact 수)
8. THE system SHALL emit structured logs to CloudWatch namespace `BOS-AI/RAG-v9.5`: event_type=import_conflict_resolved (fields: fact_key, npu_claim_id, parser_claim_id, resolution=dedup|supersede|conflict) 및 event_type=retrieval_dedup (fields: fact_key, exposed_claim_id, deduped_count)

---

### Category 2: Retrieval Enhancement

---

### Requirement 5: Cross-Encoder Re-Ranker Integration

**User Story:** As a RAG system operator, I want a cross-encoder re-ranker between retrieval and LLM generation, so that the most relevant claims are selected from a larger initial candidate set.

#### Acceptance Criteria

1. WHEN the Retrieval_Engine fetches initial candidates from Bedrock KB / OpenSearch, THE Retrieval_Engine SHALL fetch top-20 candidates (increased from current top-5)
2. WHEN top-20 candidates are fetched, THE Re-Ranker SHALL score each candidate against the original query using a cross-encoder model (Cohere Rerank-v3 via LiteLLM Gateway or Bedrock-compatible rerank endpoint)
3. AFTER re-ranking, THE Retrieval_Engine SHALL select top-5 candidates by re-ranker score and pass ONLY these to the LLM context
4. THE Re-Ranker SHALL complete scoring within 500ms for 20 candidates (p95 latency target)
5. WHEN the Re-Ranker endpoint is unavailable (timeout or error), THE Retrieval_Engine SHALL fall back to the original top-5 from initial retrieval (graceful degradation) and log a warning
6. THE system SHALL log re-ranker metrics: input_count, output_count, score_distribution (min/max/mean), latency_ms, fallback_triggered (boolean)
7. THE Re-Ranker SHALL be configurable via environment variable `RERANKER_ENABLED` (default: true) for A/B testing

---

### Requirement 6: Query-Type Retrieval Routing

**User Story:** As a RAG system developer, I want queries to be routed to different retrieval backends based on their intent, so that connectivity questions use the graph DB and parameter questions use direct Claim DB lookup.

#### Acceptance Criteria

1. WHEN a query is received, THE Query_Router SHALL classify it into one of 4 types:
   - `connectivity_query`: "어떻게 연결되어 있는가", "signal path", "port binding", "connects to", "ring topology", "flit routing"
   - `parameter_query`: "값이 얼마인가", "bit width", "depth", "count", "how many", "파라미터", "REP_DEPTH"
   - `hierarchy_query`: "내부 구조", "hierarchy", "instantiation", "sub-module", "안에 뭐가 있는가"
   - `general_query`: 위 3개에 해당하지 않는 모든 질문
2. WHEN query_type is `connectivity_query`, THE Retrieval_Engine SHALL:
   - Primary: Neptune Graph traversal (CONNECTS_TO edges, 2-3 hop)
   - Secondary: Claim DB (topic=PortBinding OR topic=WireTopology)
   - Tertiary: Bedrock KB hybrid search
3. WHEN query_type is `parameter_query`, THE Retrieval_Engine SHALL:
   - Primary: Claim DB direct lookup (topic=TopLevelParameter OR topic=PackageConstant)
   - Secondary: Bedrock KB hybrid search
4. WHEN query_type is `hierarchy_query`, THE Retrieval_Engine SHALL:
   - Primary: Neptune Graph traversal (INSTANTIATES edges, recursive up to 5 levels)
   - Secondary: Claim DB (topic=ModuleHierarchy)
5. WHEN query_type is `general_query`, THE Retrieval_Engine SHALL use current behavior: Bedrock KB hybrid search → Claim DB verification
6. THE Query_Router classification SHALL complete within 100ms (single LLM call with few-shot examples, or rule-based regex matching)
7. THE system SHALL log routing decisions: query_type, primary_backend, primary_result_count, fallback_used (boolean)

---

### Requirement 7: BM25 Signal Name Boost

**User Story:** As a semiconductor design engineer, I want exact module/signal name matches to rank higher than semantic similarity, so that `tt_noc_repeaters_cardinal` and `tt_noc_repeaters` are not confused.

#### Acceptance Criteria

1. WHEN the Retrieval_Engine performs hybrid search, THE BM25 component SHALL apply a **3.0x boost** to matches in `module_name` and `signal_name` fields (increased from default 1.0)
2. WHEN the query contains an exact RTL identifier (matching pattern `[a-z][a-z0-9_]*` with at least one underscore), THE Retrieval_Engine SHALL add an exact-match filter as a MUST clause in addition to semantic search
3. THE boost factor SHALL be configurable via environment variable `BM25_SIGNAL_BOOST` (default: 3.0)
4. WHEN two claims match a query with similar semantic scores but different BM25 exact-match status, THE claim with exact module_name match SHALL rank first regardless of semantic score difference up to 0.15

---

### Category 3: Chunking & Indexing Improvement

---

### Requirement 8: RTL Semantic Boundary Chunking

**User Story:** As a RAG system developer, I want RTL content to be chunked at syntax boundaries (module/struct/generate block), so that complete definitions are never split across chunks.

#### Acceptance Criteria

1. WHEN the RTL_Parser chunks a file for OpenSearch indexing, THE Chunker SHALL recognize the following boundaries and NEVER split within them:
   - `module` ... `endmodule`
   - `typedef struct packed {` ... `}`
   - `typedef enum` ... `}`
   - `generate` ... `endgenerate`
   - `function` ... `endfunction`
   - `task` ... `endtask`
2. WHEN a single construct (e.g., a large module) exceeds `max_chunk_size` (8000 tokens), THE Chunker SHALL split at the NEXT recognized sub-boundary within that construct (e.g., between `always` blocks within a module), NOT at an arbitrary character position
3. WHEN no sub-boundary exists within an oversized construct, THE Chunker SHALL keep the construct as a single oversized chunk and log a warning: `event=oversized_chunk, file=<path>, construct=<type>, size=<tokens>`
4. THE Chunker SHALL preserve a **200-token overlap** between adjacent chunks that share the same parent construct (e.g., two `always` blocks from the same module)
5. WHEN a struct definition like `trinity_clock_routing_t` is chunked, THE Chunker SHALL guarantee that ALL fields of the struct appear in a SINGLE chunk (never split mid-struct). 이 struct 보호는 nesting과 무관하게 적용된다 — module 내부에 중첩된 struct도 module-level chunking보다 struct 무결성이 우선한다
6. IF a single struct definition exceeds `max_chunk_size` (8000 tokens), THEN THE Chunker SHALL keep it as a single oversized chunk and SHALL NOT split fields (struct 필드 분리 금지가 oversized 규칙보다 우선; criterion 3의 oversized 경고 로그는 동일하게 발생)
7. THE Chunker SHALL tag each chunk with metadata: `parent_construct_type`, `parent_construct_name`, `boundary_type` (natural_end | sub_boundary | oversized)

---

### Requirement 9: Claim DB Topic Enrichment from CLAUDE_DBS Keywords

**User Story:** As a RAG system operator, I want Claim DB topics to be enriched with the CLAUDE_DBS keyword taxonomy, so that retrieval precision improves for domain-specific queries.

#### Acceptance Criteria

1. WHEN importing CLAUDE_DBS claims, THE Import_Pipeline SHALL create topic entries based on the MEMORY.md keywords column, mapping to a normalized topic taxonomy:
   - `edc, node_id, ring, harvest` → topics: EDC, EDC_Harvest, EDC_Topology
   - `register_file, dest, srca, srcb, latch` → topics: RegisterFile, LatchArchitecture
   - `fpu, sfpu, mac, multiplier` → topics: FPU, SFPU, MACThroughput
   - `noc2axi, router, niu, bridge` → topics: NIU, Router, NOC2AXI
   - `overlay, hierarchy, clock_domain, sram` → topics: Overlay, ClockArchitecture, SRAM
   - `sdc, timing, constraint` → topics: SDC, TimingAnalysis
   - `turboquant, quantization, compression` → topics: TurboQuant, Compression
   - `dft, scan, bist, ijtag` → topics: DFX, DFT
   - `firmware, test, dv` → topics: Firmware, Verification
2. WHEN a claim has multiple applicable topics, THE Import_Pipeline SHALL assign ALL matching topics (multi-topic per claim allowed)
3. THE normalized topic taxonomy SHALL be stored in a configuration file (`topic_taxonomy.yaml`) for maintainability
4. WHEN a new keyword appears in CLAUDE_DBS that doesn't map to existing taxonomy, THE Import_Pipeline SHALL assign topic "Uncategorized" and log a warning for operator review. IF the warning log write fails, THEN THE Import_Pipeline SHALL continue the import (logging failure SHALL NOT halt import) and SHALL record the failure count in the final summary

---

### Category 4: Evaluation Framework

---

### Requirement 10: Ground Truth Dataset Generation from CLAUDE_DBS

**User Story:** As a RAG system operator, I want an automated evaluation dataset derived from CLAUDE_DBS verified knowledge, so that RAG improvements can be quantitatively measured.

#### Acceptance Criteria

1. THE Evaluation_Generator SHALL produce a dataset of question-answer pairs from CLAUDE_DBS memory files, with minimum 100 pairs covering all major topics (EDC, FPU, NoC, NIU, Overlay, RegisterFile, Clock, Reset, Harvest, DFX)
2. FOR EACH memory file, THE Evaluation_Generator SHALL create 2-5 question-answer pairs based on:
   - Table rows → "What is the value of [parameter]?" / "[value]"
   - Key findings → "Is [statement] true for N1B0?" / "Yes/No + evidence"
   - Derivation chains → "How many INT8 MACs per cluster?" / "8192 (8×2×2×8×2)"
   - Corrections → "What is the correct SRCA row count?" / "48 (not 256)"
3. EACH question-answer pair SHALL include:
   - `question`: natural language query a design engineer would ask
   - `expected_answer`: ground truth from CLAUDE_DBS (verified)
   - `source_memory_id`: M1-M52 or N1B0_A1-A10
   - `topic`: from normalized taxonomy
   - `difficulty`: easy (single fact lookup) | medium (multi-fact synthesis) | hard (derivation required)
   - `expected_claims`: list of claim_ids that SHOULD be retrieved
4. THE dataset SHALL be stored at `test_rtl/evaluation/ground_truth_v9.5.json`
5. THE dataset SHALL include at least 10 "adversarial" pairs where similar-but-wrong answers exist (e.g., baseline vs N1B0 values, pre-correction vs post-correction values)

---

### Requirement 11: Automated Regression Test Runner

**User Story:** As a RAG system operator, I want an automated test runner that evaluates RAG responses against the ground truth dataset, so that every pipeline change can be measured for regression.

#### Acceptance Criteria

1. WHEN the operator runs `py evaluation/run_eval.py --dataset ground_truth_v9.5.json`, THE Evaluator SHALL:
   - Submit each question to the RAG API
   - Compare the response against expected_answer
   - Score each response on 3 dimensions: Retrieval_Recall@5, Answer_Correctness, Faithfulness
2. **Retrieval_Recall@5**: THE Evaluator SHALL check if ANY of the `expected_claims` appear in the top-5 retrieved context. Score = (matched claims / expected claims)
3. **Answer_Correctness**: THE Evaluator SHALL use LLM-as-judge to compare RAG answer vs expected_answer on factual equivalence (0.0 = completely wrong, 0.5 = partially correct, 1.0 = fully correct)
4. **Faithfulness**: THE Evaluator SHALL check if the RAG answer contains any statement NOT supported by the retrieved context (hallucination detection). Score = 1.0 - (unsupported_statements / total_statements)
5. THE Evaluator SHALL produce a summary report:
   - Overall: mean Retrieval_Recall@5, mean Answer_Correctness, mean Faithfulness
   - Per-topic breakdown
   - Per-difficulty breakdown
   - Regression detection: comparison vs previous run (if `--baseline <previous_report.json>` provided)
6. WHEN mean Answer_Correctness drops by more than 5% vs baseline, THE Evaluator SHALL exit with code 1 (CI fail signal)
7. THE Evaluator SHALL complete within 30 minutes for the full 100+ pair dataset (parallel execution allowed)

---

### Requirement 12: Per-Component Performance Attribution

**User Story:** As a RAG system developer, I want to know which RAG component (retrieval, re-ranking, generation) is the bottleneck for each failed test case, so that improvement effort is targeted correctly.

#### Acceptance Criteria

1. FOR EACH failed test case (Answer_Correctness < 0.8), THE Evaluator SHALL classify the failure root cause:
   - `retrieval_miss`: expected claims NOT in top-20 initial candidates → chunking/indexing problem
   - `reranker_miss`: expected claims in top-20 but NOT in top-5 after re-ranking → re-ranker model problem
   - `generation_miss`: expected claims in top-5 context but answer is wrong → LLM generation problem
   - `knowledge_gap`: expected claims DO NOT EXIST in Claim DB → knowledge import incomplete
2. THE Evaluator SHALL aggregate root causes: "retrieval_miss: 15%, reranker_miss: 8%, generation_miss: 12%, knowledge_gap: 5%"
3. THE Evaluator SHALL flag the top-3 topics with lowest Answer_Correctness for prioritized improvement
4. WHEN `knowledge_gap` is the root cause, THE Evaluator SHALL list the specific missing claims and their source memory files for import prioritization

---

### Requirement 17: 증분 파일럿 롤아웃 및 효과 게이트

**User Story:** As a RAG system operator, I want to validate import impact on a small pilot before full rollout, so that the projected score gains (NPU report §6.3) are replaced with measured values and we avoid wasting effort on an ineffective import strategy.

> **근거:** NPU 리포트 §6.3(추정 가정 한계) + §8(Action Items). 핵심 원칙: "추정을 실측으로 대체하기 전까지 목표 점수를 확정하지 않는다."

#### Acceptance Criteria

1. THE import rollout SHALL proceed in measured stages: (a) baseline 측정 → (b) P0 파일럿 import → (c) A/B 측정 → (d) P1/P2 확대 결정. 각 단계는 이전 단계의 측정 결과 없이 진행하지 않는다
2. BEFORE any CLAUDE_DBS import, THE operator SHALL run the evaluation framework (Req 11) against the current RAG state to record an L1~L6 baseline (import "전" 점수). 이 baseline이 없으면 import 효과를 정량화할 수 없다
3. THE P0 pilot SHALL import ONLY the P0 priority set (NPU 리포트 §6.2: M1-M4·M19-M20 EDC + M11-M14 Hierarchy/Router/DFX, 약 100 claims) before importing P1/P2
4. AFTER the P0 pilot import, THE operator SHALL re-run the evaluation framework with the SAME prompts/dataset and compute the measured delta (Δ Content Fidelity, Δ per-topic Answer_Correctness) vs the baseline from criterion 2
5. IF the measured P0 delta is ≥ 50% of the §6.3 projected gain for the imported topics, THEN the rollout SHALL proceed to P1/P2 full import
6. IF the measured P0 delta is < 50% of projection, THEN the rollout SHALL HALT P1/P2 and the import strategy (claim 분해 단위, fact_key 정의, topic mapping) SHALL be revised before retry
7. THE system SHALL NOT publish a confirmed v9.5 target score until pilot measurement replaces the §6.3 projection; projected numbers SHALL be labeled "추정(projection)" in all reports until then

---

### Category 5: HDD Generation Improvement

---

### Requirement 13: Derivation Chain Display in HDD

**User Story:** As a semiconductor design engineer, I want HDD documents to show calculation derivations (not just final values), so that I can verify the numbers myself.

#### Acceptance Criteria

1. WHEN the HDD_Generator produces a section containing numerical specifications derived from calculations (e.g., MAC throughput, memory capacity, total SRAM count), THE HDD_Generator SHALL include the derivation chain in a collapsible annotation or footnote
2. THE derivation format SHALL follow: `[값] = [계산식] (source: [RTL file:line])`
   - Example: `8192 INT8 MACs/cluster = 4 Tensix × 2 G-Tiles × 8 cols × 4 rows × 2 lanes × 8 INT8 × 2 phases (source: tt_tensix_pkg.sv:35, HALF_FP_BW=1)`
3. WHEN a claim with `claim_type: derivation` is used in HDD generation, THE HDD_Generator SHALL display the full derivation_chain from claim_text, NOT just the final numeric result
4. WHEN the derivation involves multiple RTL parameters, THE HDD_Generator SHALL list all parameter sources in order of the calculation
5. THE `show_derivations` parameter (default: true) SHALL control the derivation DISPLAY FORMAT (collapsible/footnote vs inline), but THE HDD_Generator SHALL ALWAYS include the derivation chain for numerical specifications derived from calculations regardless of the `show_derivations` setting (numerical fact는 항상 derivation 동반; 플래그는 표시 방식만 제어)

---

### Requirement 14: Coverage Audit Integration

**User Story:** As a RAG system operator, I want the HDD generator to report coverage gaps (what percentage of a topic is covered vs what the verified knowledge base has), so that incomplete sections are flagged automatically.

#### Acceptance Criteria

1. WHEN the HDD_Generator produces a topic section (e.g., EDC, FPU, NoC), THE HDD_Generator SHALL calculate `coverage_ratio = claims_used / total_claims_available_for_topic`
2. WHEN coverage_ratio < 0.6 for any section, THE HDD_Generator SHALL append a coverage warning: `⚠️ Coverage: {ratio}% — {missing_count} verified claims not referenced. Topics: {list of subtopics with 0 claims used}`
3. THE HDD_Generator SHALL produce a coverage matrix (topic × subtopic) as an appendix showing which CLAUDE_DBS knowledge was used vs available
4. WHEN a specific user question maps to a topic with coverage_ratio < 0.3, THE system SHALL respond with: "이 주제에 대해 검증된 지식의 {ratio}%만 참조했습니다. 더 상세한 정보가 필요하면 [관련 subtopic 리스트]를 명시해주세요."

---

### Requirement 15: Version-Aware Response

**User Story:** As a semiconductor design engineer, I want RAG responses to indicate which HDD version the information comes from and whether corrections have been applied, so that I don't get outdated information.

#### Acceptance Criteria

1. WHEN a claim was imported from CLAUDE_DBS with a correction record (e.g., M40), THE response SHALL include: `[Corrected in v1.00] 이전값: {before}, RTL 검증값: {after}`
2. WHEN multiple HDD versions exist for the same information (e.g., EDC_HDD V0.1 through V0.9), THE Retrieval_Engine SHALL ONLY return claims from the latest version unless the user explicitly asks for version history. WHEN a topic exists ONLY in an older version (없음 in current version), THE Retrieval_Engine SHALL return no results for that topic rather than mixing in older-version data (no silent version mixing)
3. WHEN the user asks about a topic where known corrections exist, THE system SHALL proactively mention: "참고: 이 수치는 HDD v1.00에서 RTL 대조 후 교정된 값입니다. (M40 참조)"
4. THE system SHALL maintain a `correction_history` field on claims that have been superseded, containing: original_value, corrected_value, correction_date, rtl_evidence

---

## Non-Functional Requirements

### NFR-1: Import Performance
- Full CLAUDE_DBS import (51 memory + 10 N1B0 + reference files) SHALL complete within 10 minutes
- Each memory file → claims extraction SHALL complete within 5 seconds

### NFR-2: Retrieval Latency
- Re-Ranker added latency SHALL be < 500ms (p95)
- Query routing classification SHALL be < 100ms
- Total query-to-response latency SHALL remain < 8 seconds (current baseline ~5s + re-ranker overhead)

### NFR-3: Evaluation Stability
- Evaluation scores SHALL be reproducible: same dataset + same RAG state → score variation < 2%
- Ground truth dataset SHALL be version-controlled and immutable once released

### NFR-4: Backward Compatibility
- All existing API endpoints SHALL continue to function without changes
- Claims imported from CLAUDE_DBS SHALL coexist with parser-generated claims; conflicts are resolved per Requirement 16 (no silent overwrite, no duplicate exposure)
- Users who don't specify N1B0 context SHALL receive baseline Trinity answers (no regression)

### NFR-5: Observability
- All new components (Import Pipeline, Re-Ranker, Query Router, Evaluator) SHALL emit structured logs to CloudWatch
- CloudWatch namespace: `BOS-AI/RAG-v9.5`
- Metrics: ImportClaimCount, RerankerLatency, QueryRouterAccuracy, EvalScoreAvg

---

## Dependencies

| Dependency | Required By | Status |
|-----------|-------------|--------|
| v9.4 Neptune Ingestion Pipeline | Req 6 (Graph traversal routing) | Deployed (rtl-parser Lambda 실시간 적재, neptunedata 클라이언트 + UNWIND 배치, tt_20260516 재인덱싱 완료) |
| LiteLLM Gateway | Req 5 (Re-Ranker API routing) | Deployed (On-Prem 192.128.10.102) |
| Claim DB (DynamoDB bos-ai-claim-db-dev) | Req 1-4, 9, 16 | Available |
| CLAUDE_DBS files access | Req 1-2, 10 | Available (test_rtl/Sample/CLAUDE_DBS/, 87 files) |
| Neptune Graph DB | Req 6 (connectivity queries) | Available (read + write 파이프라인 모두 배포; db.t4g.medium, 대량 적재 시 동시성 제한 필요) |
| Evaluation baseline (L1~L6) | Req 17 (pilot gate) | Not yet measured (import 前 선행 필요) |

---

## Out of Scope

- ColBERT/ColPali multi-vector retrieval (v10 범위)
- SoC RTL 호환성 (v9.4 Req 14-15에서 별도 처리)
- Multimodal RAG (이미지/다이어그램 처리 — v10+ Spec RAG 범위)
- CLAUDE_DBS 이외의 외부 knowledge source import
- Interactive Schematic UI 개선 (별도 스펙)

---

## Success Criteria

| Metric | Current (baseline) | Target (v9.5, 추정) | Measurement |
|--------|---------------|---------------|-------------|
| 정식 평가 점수 | 48/100 (v9.3 review) | **85/100** (projection, Req 17 게이트 통과 후 확정) | Automated eval on ground truth dataset |
| Content Fidelity (L1~L6 가중) | ~65% (v9.4 계열) | **85%** (projection) | Automated eval |
| L4 파라미터 (최대 병목) | 38% (v9.4a) | **70%+** | L1~L6 프레임워크 측정 |
| L5 동작 | 28% (v9.4a) | **50%+** | L1~L6 프레임워크 측정 |
| Retrieval Recall@5 | unmeasured | **0.80+** | Automated eval |
| Answer Correctness | unmeasured | **0.82+** | LLM-as-judge on eval dataset |
| Faithfulness | unmeasured (많은 [FROM LLM]) | **0.90+** | Hallucination detection |
| Query-to-Response Latency | ~5s | **< 8s** (re-ranker 포함) | CloudWatch p95 |
| Knowledge Coverage (vs CLAUDE_DBS) | 0% (미연동) | **90%+ claims imported** | Import summary |

> **⚠️ 목표 점수는 NPU 리포트 §6.3의 추정(projection)이다.** Requirement 17의 P0 파일럿 실측이 baseline을 확보하고 추정을 대체하기 전까지 **확정 목표로 사용하지 않는다.** 보수 시나리오는 77~80%.

---

# Addendum A: Filelist 기반 임베딩 스코프 & OpenSearch 종속성 제거

> **Added:** 2026-06-12
> **근거:** (1) SoC 엔지니어로부터 N1 빌드 컴파일 매니페스트(`.f` filelist) 수령 — `+incdir+`(~50), `+define+`(~30, TARGET_*), 실제 소스 경로(수백~천여개). 전부 `/data/secure_data_from_tt/20260516/used_in_n1/` 아래. (2) S3 트리 실측: 버킷 `bos-ai-rtl-src-533335672315`, prefix `rtl-sources/tt_20260516/` 아래 `tt_rtl/`(전체)와 `used_in_n1/tt_rtl/`(N1 부분집합)가 **물리적으로 분리 적재**되어 있고 filelist 경로가 S3 키에 1:1 보존됨(`tt_router.sv` 63,830 bytes 실존 확인). (3) OpenSearch 종속성 맵 재조사: `rtl_parser_src/handler.py`는 Qdrant 적재 완료(단 `_index_to_opensearch()` 함수명이 실제로는 Qdrant에 쓰는 오칭), `rtl_parser_src/analysis_handler.py`(Step Functions 분석 스테이지)는 **여전히 OpenSearch에 read/write 중**, `lambda.tf` document-processor에 `OPENSEARCH_*` 환경변수·`aoss:APIAccessAll` IAM 잔존. Bedrock KB(`bos-ai-vectors`)는 유지 대상.
>
> **방침 결정:** 임베딩 boost는 "전부 임베딩 + `used_in_n1` 검색 boost"(B안 — 무식하지만 확실). npu_rag는 확실해야 하는 시스템이므로 N1 필수 파일을 누락 없이 색인하되 검색 시 우선순위만 높인다.

## Glossary 추가

- **used_in_n1 Subset**: N1 빌드에 실제 사용된 RTL 부분집합. S3 키에 `/used_in_n1/`을 포함하는 객체로 식별된다 (전체 트리 `tt_rtl/`와 물리 분리).
- **Filelist (`.f`)**: N1 빌드 컴파일 매니페스트. `+incdir+`(include 경로), `+define+`(컴파일 매크로, 예: `TARGET_*`), 소스 파일 경로 목록을 포함한다.
- **Pipeline Config Claim**: filelist의 `+define+` 매크로처럼 파이프라인(빌드) 단위로 적용되는 설정을 claim으로 저장한 것. `claim_type: pipeline_config`.
- **Qdrant 단일화 (RTL)**: RTL/SoC 벡터 검색의 backend를 Qdrant(10.20.1.217:6333, Virginia)로 일원화하고 RTL 경로의 OpenSearch Serverless(AOSS) 종속성을 제거하는 것. **Bedrock KB(`bos-ai-vectors`)의 AOSS는 본 범위에서 제외(유지).**

---

### Requirement 18: Filelist 기반 임베딩 스코프 및 used_in_n1 검색 Boost

**User Story:** As a semiconductor design engineer, I want RTL files that are actually used in the N1 build (`used_in_n1` subset) to rank higher in search results, so that answers prioritize the verified N1 design over the full superset tree, without losing the ability to search the full tree.

> **설계 결정 (B안):** 전체 트리(`tt_rtl/`)와 N1 부분집합(`used_in_n1/tt_rtl/`)을 **모두 임베딩**한다 (커버리지 누락 방지). 차별화는 **검색 시점 boost**로만 수행한다. 판정은 basename 매칭이 아니라 **S3 키의 `/used_in_n1/` 포함 여부**로 결정한다 (S3 트리 실측으로 1:1 경로 보존 확인됨).

#### Acceptance Criteria

1. WHEN the RTL_Parser indexes any object whose S3 key path contains the segment `/used_in_n1/`, THE RTL_Parser SHALL set metadata field `used_in_n1: true` on the indexed record (Qdrant payload + DynamoDB claim). WHEN the S3 key does NOT contain `/used_in_n1/`, THE RTL_Parser SHALL set `used_in_n1: false`.
2. THE `used_in_n1` 판정 SHALL rely ONLY on the presence of the `/used_in_n1/` path segment in the S3 key, and SHALL NOT use basename matching against the filelist (실측상 경로가 S3 키에 1:1 보존되므로 basename 대조 불필요).
3. WHEN the Retrieval_Engine ranks candidates AND a candidate has `used_in_n1: true`, THE Retrieval_Engine SHALL apply a **2.0x boost** to that candidate's relevance score, configurable via environment variable `USED_IN_N1_BOOST` (default: 2.0).
4. WHEN two candidates have otherwise-equal relevance but differ in `used_in_n1` status, THE Retrieval_Engine SHALL rank the `used_in_n1: true` candidate first.
5. THE `used_in_n1` boost SHALL compose with existing boosts (Req 4 N1B0 variant boost, Req 7 BM25 signal boost, Req 5 Re-Ranker) without replacing them; ordering precedence follows Req 16.5 (Re-Ranker score first, then confidence, then boosts) — `used_in_n1` boost는 retrieval 점수 단계에 곱연산으로 적용된다.
6. WHEN the import tooling ingests a filelist (`.f`), THE Import_Pipeline SHALL parse each `+define+` macro (e.g., `+define+TARGET_N1`) and store it as a claim with `claim_type: pipeline_config`, `pipeline_id` 연관, and `topic: BuildConfig`, so that build-time macros become searchable as verified configuration facts.
7. THE Import_Pipeline SHALL parse `+incdir+` entries from the filelist for reference/audit but SHALL NOT create individual claims per include directory (incdir는 경로 메타데이터로만 기록, claim 폭증 방지).
8. WHEN re-indexing is performed (Req 19.5 Full reindex), THE RTL_Parser SHALL populate `used_in_n1` on ALL records (both full-tree and subset), so that existing records indexed before this requirement also receive the field (no stale records without `used_in_n1`).
9. THE system SHALL emit a structured log on indexing: event_type=used_in_n1_tagged (fields: s3_key, used_in_n1, pipeline_id) at debug level, and an import summary field `used_in_n1_count` / `full_tree_count`.

---

### Requirement 19: OpenSearch 종속성 완전 제거 및 Qdrant 단일화 + Full 재인덱싱

**User Story:** As a RAG system operator, I want the RTL/SoC retrieval path to depend ONLY on Qdrant (no residual OpenSearch/AOSS coupling), so that the vector store migration is complete and data is not split or stale across two backends.

> **범위 경계 (중요):** 본 요구사항은 **RTL/SoC 파이프라인의 AOSS 종속성**만 제거한다. **Bedrock KB(`bos-ai-vectors`)의 OpenSearch Serverless는 유지 대상이며 본 요구사항의 제거 범위에 포함되지 않는다.** 제거 대상과 유지 대상을 혼동하지 않는다.

#### Acceptance Criteria

1. THE RTL_Parser (`rtl_parser_src/handler.py`) SHALL NOT contain functions named with `opensearch` that actually write to Qdrant (현재 `_index_to_opensearch()` 오칭). THE function SHALL be renamed to reflect its actual target (예: `_index_to_qdrant`) and all call sites updated, WITHOUT changing the indexing behavior (순수 리네이밍 + 호출부 정합; 기능 변경 금지).
2. THE analysis pipeline (`rtl_parser_src/analysis_handler.py`, Step Functions 스테이지: hierarchy / clock_domain / dataflow / topic / claim / hdd_section / variant_delta / backfill) SHALL be migrated to read from and write to Qdrant instead of OpenSearch. THE migration SHALL preserve the existing `pipeline_id` + `analysis_type` query semantics (현재 `_opensearch_scroll_query(pipeline_id, analysis_type)`와 동등한 Qdrant filter 조회로 대체).
3. WHEN the analysis pipeline queries documents by `pipeline_id` and `analysis_type`, THE Qdrant-backed query SHALL return the same logical result set as the previous OpenSearch `search_after` pagination (페이지네이션은 Qdrant scroll/offset으로 대체; 결과 누락 금지).
4. THE document-processor Lambda (`lambda.tf`) AOSS coupling SHALL be removed where it pertains to the RTL/SoC retrieval path: env vars `OPENSEARCH_ENDPOINT`/`OPENSEARCH_INDEX` (RTL 관련), IAM `aoss:APIAccessAll` (RTL 관련), and `opensearch/*` secret references that are NOT required by Bedrock KB. IF any AOSS reference is shared with the Bedrock KB path, THEN it SHALL be retained and explicitly annotated as "Bedrock KB 전용, RTL 무관".
5. THE migration SHALL be followed by a **Full re-indexing** of the target pipeline(s) (`tt_20260516` 우선, 이후 `tt_20260221`) so that all RTL records live in Qdrant with the v9.5 schema (including `used_in_n1` from Req 18). Partial/incremental reindex SHALL NOT be accepted as completion (전체 재인덱싱 필수).
6. THE Full re-indexing SHALL apply Lambda cost controls: reserved concurrency 10~20, memory 512MB, timeout 300s, and batch size tuned to avoid Qdrant broken-pipe (현행 `QDRANT_BATCH_SIZE=15` 준수). THE operator SHALL be able to throttle/resume reindex without data loss (idempotent upsert).
7. WHEN re-indexing completes, THE operator SHALL verify ZERO RTL records remain reachable only via OpenSearch (즉 RTL 검색이 Qdrant만으로 완전 동작) and SHALL confirm via MCP `search_rtl` that representative queries (module/port/signal/used_in_n1) return results sourced from Qdrant.
8. AFTER successful migration and reindex verification, THE OpenSearch RTL artifacts (terraform `aws_opensearchserverless_access_policy.rtl_index`, RTL index `rtl-knowledge-base-index`, RTL-specific SG/VPCE if unused by Bedrock KB) SHALL be decommissioned in terraform. THE decommission SHALL be a SEPARATE, explicitly-gated step performed ONLY after criterion 7 passes (검증 전 인프라 삭제 금지 — 롤백 가능성 보존).
9. THE system SHALL maintain backward-compatible search behavior during migration: WHILE the analysis pipeline is being migrated, RTL search via `handler.py` (already Qdrant) SHALL continue to function without regression. THE migration of analysis stages SHALL NOT break the live RTL parser path.
10. THE migration SHALL emit structured logs to CloudWatch namespace `BOS-AI/RAG-v9.5`: event_type=aoss_migration (fields: stage, records_migrated, source=opensearch, target=qdrant) and event_type=reindex_progress (fields: pipeline_id, files_done, files_total, used_in_n1_count).

#### 제거 대상 vs 유지 대상 (정리)

| 항목 | 위치 | 조치 |
|------|------|------|
| `_index_to_opensearch()` 오칭 | `handler.py` | 리네이밍 → `_index_to_qdrant` (기능 동일) |
| Step Functions 분석 스테이지 OpenSearch read/write | `analysis_handler.py` | Qdrant로 마이그레이션 |
| `RTL_OPENSEARCH_ENDPOINT` / `RTL_OPENSEARCH_INDEX` | `analysis_handler.py` env | 제거 (Qdrant 설정으로 대체) |
| `OPENSEARCH_ENDPOINT` / `OPENSEARCH_INDEX="bos-ai-documents"` (RTL 관련) | `lambda.tf` document-processor | 제거 (RTL 무관 확인 후) |
| `aoss:APIAccessAll` IAM (RTL 관련) | `lambda.tf` | 제거 |
| `aws_opensearchserverless_access_policy.rtl_index` | `opensearch.tf` | 검증 후 decommission (criterion 8) |
| RTL 인덱스 `rtl-knowledge-base-index` | AOSS collection | 검증 후 decommission |
| **Bedrock KB collection `bos-ai-vectors`** | `bedrock-kb.tf`, module | **유지 (제거 금지)** |
| **Bedrock KB AOSS access policy / VPCE** | `opensearch.tf` | **유지 (Bedrock KB 의존 시)** |

---

## Addendum A — Out of Scope 보강

- Bedrock KB(`bos-ai-vectors`)의 OpenSearch Serverless 제거 (유지 대상)
- filelist의 `+incdir+`를 claim으로 개별 적재 (경로 메타데이터로만 기록 — Req 18.7)
- N1 외 다른 빌드 변형(N2 등)의 used_in_n1 태깅 (현 범위는 N1만)

## Addendum A — Success Criteria 보강

| Metric | 현재 | 목표 | 측정 |
|--------|------|------|------|
| used_in_n1 태깅 커버리지 | 0% (미적용) | 100% (재인덱싱 후 전 레코드 used_in_n1 필드 보유) | Qdrant payload 샘플 + import summary |
| RTL OpenSearch 잔존 참조 | 다수 (analysis_handler.py, lambda.tf) | 0 (RTL 경로) | grep + MCP search_rtl 동작 확인 |
| Full 재인덱싱 (tt_20260516) | 부분/혼재 | 전체 Qdrant 단일 적재 | reindex_progress 로그 files_done==files_total |
