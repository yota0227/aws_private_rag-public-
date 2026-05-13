# Requirements Document

## Introduction

RAG v9.4는 BOS-AI Private RAG 시스템의 RTL 파이프라인 최종 대규모 개선 버전이다. v9.3 리뷰에서 식별된 치명적 오류 6건과 구조적 한계를 해결하며, 4개 카테고리의 작업을 포함한다: (1) 즉시 수정 — 프롬프트/데이터 수정으로 factual error 제거, (2) 파서 확장 — RTL Parser의 expression evaluation, generate block, parameter 추출 등 코드 수정, (3) Neptune Ingestion Pipeline — DynamoDB 파싱 데이터를 Neptune Graph DB에 적재하는 쓰기 파이프라인 구현, (4) SoC RTL 호환성 검증 — 파서의 범용성 확인 및 개선.

## Glossary

- **RTL_Parser**: `rtl_parser_src/` 디렉토리에 위치한 Python 기반 RTL 코드 파싱 모듈 집합
- **Port_Binding_Parser**: RTL 인스턴스화 구문에서 `.port(signal)` 바인딩을 추출하는 파서 모듈 (`port_binding_parser.py`)
- **Wire_Declaration_Parser**: wire/logic 선언에서 struct 타입과 배열 차원을 추출하는 파서 모듈 (`wire_declaration_parser.py`)
- **Generate_Block_Parser**: RTL generate for/if 블록의 이름과 구조를 추출하는 파서 모듈 (`generate_block_parser.py`)
- **Package_Extractor**: SystemVerilog package에서 struct, enum, parameter를 추출하는 파서 모듈 (`package_extractor.py`)
- **Neptune_Graph_DB**: AWS Neptune 서비스로 운영되는 그래프 데이터베이스, openCypher 쿼리 언어 사용
- **Ingestion_Pipeline**: DynamoDB의 파싱 결과를 Neptune Graph DB에 노드/엣지로 적재하는 데이터 파이프라인
- **Claim**: RTL 파싱 결과로 생성되는 구조화된 지식 단위 (DynamoDB `bos-ai-claim-db-prod` 테이블에 저장)
- **Module_Parse**: RTL 파서가 생성하는 모듈 구조 분석 결과 (DynamoDB에 저장)
- **DynamoDB_Table**: `bos-ai-claim-db-prod` — Claim 및 파싱 결과 저장소
- **Graph_Export_API**: Neptune 그래프의 부분집합을 JSON으로 내보내는 기존 API (`/rag/graph-export`)
- **Interactive_Schematic**: `interactive_schematic.html` — 브라우저 기반 회로도 시각화 도구
- **Pipeline_ID**: RTL 파싱 실행 단위를 식별하는 고유 ID (예: `tt_20260221`)
- **SoC_RTL**: NPU(trinity) 외의 전체 SoC 레벨 RTL 코드 (AXI interconnect, CPU subsystem, peripherals 포함)
- **Expression_Evaluator**: Port Binding에서 산술 연산 (`±1`, `*2` 등)을 파싱하고 표현하는 컴포넌트

---

## Requirements

### Requirement 1: EDC Per-Column Ring Claim 추가

**User Story:** As a semiconductor design engineer, I want the EDC section to correctly describe 4 independent per-column rings, so that the HDD document reflects the actual hardware topology.

#### Acceptance Criteria

1. WHEN the Ingestion_Pipeline processes EDC topology data, THE Claim system SHALL contain a claim stating "Each column (X=0..3) has its own independent EDC ring" with claim_type "structural" and topic "EDC"
2. WHEN the HDD generator produces the EDC section and the per-column ring claim is available, THE HDD_Generator SHALL reference the per-column ring claim instead of depicting a single chip-wide ring
3. THE Claim system SHALL store the EDC per-column ring claim with confidence_score 1.0 and source "manual_claim"

### Requirement 2: Dispatch E/W 좌표 Self-Consistency Check

**User Story:** As a RAG system operator, I want the LLM prompt to include a self-consistency check between EP Table coordinates and textual descriptions, so that [FROM LLM] inferences do not contradict parsed RTL data.

#### Acceptance Criteria

1. WHEN the HDD_Generator produces a section containing [FROM LLM] inferences about dispatch coordinates, THE HDD_Generator SHALL validate that East/West assignments are consistent with the EP Table coordinates (East=X=3, West=X=0)
2. IF a [FROM LLM] inference contradicts the EP Table data, THEN THE HDD_Generator SHALL discard only the coordinate-related parts of the inference, process remaining non-coordinate inferences normally, and emit a warning log entry with the conflicting values. IF the remaining text after coordinate removal is not contextually complete (i.e., forms an incomplete or meaningless sentence), THEN THE HDD_Generator SHALL regenerate the entire paragraph rather than outputting a fragmented result
3. THE HDD_Generator prompt SHALL include the instruction: "EP Table의 좌표를 참조하여 [FROM LLM] 추론을 검증하라. East dispatch는 X=3, West dispatch는 X=0이다."

### Requirement 3: EDC Port 배열 차원 반영

**User Story:** As a semiconductor design engineer, I want EDC port declarations to include the [3:0] array dimension, so that per-column independence is visible in the port table.

#### Acceptance Criteria

1. WHEN the RTL_Parser extracts EDC top-level ports, THE RTL_Parser SHALL preserve the `[3:0]` array dimension for ports such as `i_edc_apb_psel[3:0]` and `o_edc_fatal_err_irq[3:0]`. IF dimension preservation fails, THE RTL_Parser SHALL continue extracting ports without dimensions rather than failing the entire extraction
2. WHEN the HDD_Generator produces the EDC port table, THE HDD_Generator SHALL display the array dimension notation (e.g., `[3:0]`) alongside each per-column port
3. THE Claim system SHALL store EDC port claims with the full dimension string including `[3:0]` in the claim_text field

### Requirement 4: DFX 4-Wrapper Chain 모듈명 Claim 추가

**User Story:** As a semiconductor design engineer, I want the DFX section to list the correct 4 DFX wrapper modules, so that the HDD accurately describes the DFX chain.

#### Acceptance Criteria

1. THE Claim system SHALL contain manual claims for each of the 4 DFX wrapper modules: `tt_noc_niu_router_dfx`, `tt_overlay_wrapper_dfx`, `tt_instrn_engine_wrapper_dfx`, `tt_t6_l1_partition_dfx`
2. WHEN the HDD_Generator produces the DFX section, THE HDD_Generator SHALL reference the 4-wrapper chain claims and list all 4 modules with their clock in→out counts
3. THE Claim system SHALL store each DFX wrapper claim with claim_type "structural", topic "DFX", and source "manual_claim"

### Requirement 5: Port Binding Expression Evaluation

**User Story:** As a RAG system developer, I want the Port_Binding_Parser to evaluate arithmetic expressions in port bindings, so that offset operations like `±1` are captured in connectivity claims.

#### Acceptance Criteria

1. WHEN the Port_Binding_Parser encounters a port binding with an arithmetic expression (e.g., `.i_local_nodeid_y(i_local_nodeid_y - 1)`), THE Port_Binding_Parser SHALL extract and preserve the full expression including the arithmetic operator and operand
2. WHEN the Port_Binding_Parser encounters expressions with `+`, `-`, `*`, `/` operators and integer literal operands, THE Port_Binding_Parser SHALL record the expression as-is in the signal_expr field
3. THE Port_Binding_Parser SHALL generate a claim_text that includes the arithmetic expression (e.g., "binds port 'i_local_nodeid_y' to signal 'i_local_nodeid_y - 1'")
4. WHEN the Port_Binding_Parser encounters nested expressions (e.g., `(SizeX - 1) * 2`), THE Port_Binding_Parser SHALL preserve the full parenthesized expression without simplification
5. FOR ALL valid port binding expressions containing arithmetic operators, parsing then formatting the expression back to text SHALL produce an equivalent string (round-trip property)

### Requirement 6: Generate Block Name 추출

**User Story:** As a semiconductor design engineer, I want the RTL parser to extract generate block names, so that the module hierarchy includes generate context (e.g., `gen_noc2axi_ne_opt`, `gen_tensix_neo`).

#### Acceptance Criteria

1. WHEN the Generate_Block_Parser encounters a `generate for` or `generate if` block with a label (e.g., `gen_noc2axi_ne_opt: begin`), THE Generate_Block_Parser SHALL extract the block label name
2. WHEN the Generate_Block_Parser encounters a labeled generate block containing module instantiations, THE Generate_Block_Parser SHALL associate each instantiation with its enclosing generate block name
3. THE Generate_Block_Parser SHALL produce claims with claim_type "structural" and topic "Hierarchy" that include the generate block name in the claim_text
4. WHEN the Generate_Block_Parser encounters nested generate blocks, THE Generate_Block_Parser SHALL preserve the full hierarchy path (e.g., `gen_outer/gen_inner`)
5. FOR ALL RTL files containing labeled generate blocks, THE Generate_Block_Parser SHALL extract the block name without altering the original label string (round-trip property)

### Requirement 7: Top Module Parameter 추출

**User Story:** As a semiconductor design engineer, I want the RTL parser to extract top module parameters (e.g., `AXI_SLV_OUTSTANDING_READS=64`), so that key design parameters appear in the HDD.

#### Acceptance Criteria

1. WHEN the Package_Extractor processes a top-level module declaration containing `parameter` statements, THE Package_Extractor SHALL extract each parameter name and its default value
2. WHEN the Package_Extractor encounters parameters with numeric default values (e.g., `parameter AXI_SLV_OUTSTANDING_READS = 64`), THE Package_Extractor SHALL store the parameter name and numeric value as a claim with topic "TopLevelParameter" only after the parameter extraction is complete (not upon initial detection of the numeric value)
3. WHEN the Package_Extractor encounters parameters with expression default values (e.g., `parameter DEPTH = WIDTH * 2`), THE Package_Extractor SHALL store the parameter name and the expression string as-is
4. THE Package_Extractor SHALL extract at minimum the following parameters when present: `AXI_SLV_OUTSTANDING_READS`, `AXI_SLV_OUTSTANDING_WRITES`, `AXI_SLV_RD_RDATA_FIFO_DEPTH`

### Requirement 8: Wire Dimension 3차원 보존

**User Story:** As a semiconductor design engineer, I want the Wire_Declaration_Parser to preserve all array dimensions including 3-dimensional arrays, so that wires like `de_to_t6_coloumn[SizeX][SizeY-1][2]` are correctly represented.

#### Acceptance Criteria

1. WHEN the Wire_Declaration_Parser encounters a wire declaration with 3 or more dimensions (e.g., `[SizeX][SizeY-1][2]`), THE Wire_Declaration_Parser SHALL preserve all dimensions in the correct order
2. WHEN the Wire_Declaration_Parser processes `de_to_t6_coloumn[SizeX][SizeY-1][2]`, THE Wire_Declaration_Parser SHALL produce a claim containing all 3 dimensions: `SizeX`, `SizeY-1`, and `2`
3. THE Wire_Declaration_Parser SHALL not drop trailing dimensions regardless of the total dimension count
4. FOR ALL wire declarations with N dimensions (N >= 1), THE Wire_Declaration_Parser SHALL extract exactly N dimension expressions in their original order (round-trip property)

### Requirement 9: Struct Field Packed Dimension 추출

**User Story:** As a semiconductor design engineer, I want the Package_Extractor to extract packed dimensions from struct fields, so that structs like `trinity_clock_routing_t` report the correct field count (9 fields).

#### Acceptance Criteria

1. WHEN the Package_Extractor processes a struct definition containing fields with packed dimensions (e.g., `logic [SizeX-1:0] field_name`), THE Package_Extractor SHALL extract both the field name and its packed dimension
2. WHEN the Package_Extractor processes a struct definition (e.g., `trinity_clock_routing_t`), THE Package_Extractor SHALL report the exact number of fields declared in the RTL source with their respective packed dimensions. IF the extracted field count does not match the source declaration, THE Package_Extractor SHALL fail extraction and report the mismatch
3. THE Package_Extractor SHALL distinguish between packed dimensions (bit-width, e.g., `[7:0]`) and unpacked dimensions (array, e.g., `[3:0]`) in struct field extraction
4. FOR ALL struct definitions, THE Package_Extractor SHALL extract the same number of fields as declared in the RTL source

### Requirement 10: Neptune Ingestion Pipeline — 노드 적재

**User Story:** As a RAG system developer, I want a pipeline that reads DynamoDB parsing results and creates Neptune graph nodes, so that the graph database contains actual RTL structural data.

#### Acceptance Criteria

1. WHEN the Ingestion_Pipeline executes, THE Ingestion_Pipeline SHALL read module_parse records from DynamoDB_Table and create Module nodes in Neptune_Graph_DB with properties: `name`, `file_path`, `pipeline_id`, `module_type`
2. WHEN the Ingestion_Pipeline processes port data from module_parse records, THE Ingestion_Pipeline SHALL create Port nodes with properties: `name`, `direction` (input/output/inout), `bit_width`, `parent_module`
3. WHEN the Ingestion_Pipeline processes wire declarations from claims with topic "WireTopology", THE Ingestion_Pipeline SHALL create Signal nodes with properties: `name`, `dimensions`, `struct_type`, `purpose`
4. WHEN the Ingestion_Pipeline processes clock domain data, THE Ingestion_Pipeline SHALL create ClockDomain nodes with properties: `name`, `frequency` (if available), `source_module`
5. THE Ingestion_Pipeline SHALL use idempotent upsert operations so that re-running the pipeline does not create duplicate nodes

### Requirement 11: Neptune Ingestion Pipeline — 엣지 적재

**User Story:** As a RAG system developer, I want the ingestion pipeline to create relationship edges between Neptune nodes, so that the graph represents RTL connectivity.

#### Acceptance Criteria

1. WHEN the Ingestion_Pipeline processes module instantiation data, THE Ingestion_Pipeline SHALL create INSTANTIATES edges from parent Module nodes to child Module nodes
2. WHEN the Ingestion_Pipeline processes port binding claims with topic "PortBinding", THE Ingestion_Pipeline SHALL create CONNECTS_TO edges between Port nodes with the signal expression as an edge property
3. WHEN the Ingestion_Pipeline identifies signal driver relationships, THE Ingestion_Pipeline SHALL create DRIVES edges from output Port nodes to Signal nodes
4. WHEN the Ingestion_Pipeline processes clock domain assignments, THE Ingestion_Pipeline SHALL create BELONGS_TO edges from Signal nodes to ClockDomain nodes
5. THE Ingestion_Pipeline SHALL use idempotent upsert operations so that re-running the pipeline does not create duplicate edges

### Requirement 12: Neptune Ingestion Pipeline — 실행 인프라

**User Story:** As a RAG system developer, I want the ingestion pipeline to run as a Lambda function or standalone script, so that it can be triggered after RTL parsing completes.

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL be implemented as a Python script executable via `py neptune_ingestion.py --pipeline-id <id>` from the `lambda_src/` directory
2. WHEN the Ingestion_Pipeline is invoked with a `pipeline_id` parameter, THE Ingestion_Pipeline SHALL process only records matching that pipeline_id from DynamoDB
3. THE Ingestion_Pipeline SHALL authenticate to Neptune_Graph_DB using IAM SigV4 authentication consistent with the existing Neptune read APIs
4. IF the Neptune_Graph_DB endpoint is not configured, THEN THE Ingestion_Pipeline SHALL check configuration first, log an error, and exit immediately with a non-zero exit code without attempting to reach the endpoint. IF the endpoint is configured but unreachable, THEN THE Ingestion_Pipeline SHALL log an error and exit with the same non-zero exit code
5. WHEN the Ingestion_Pipeline completes successfully, THE Ingestion_Pipeline SHALL log a summary including: total nodes created, total edges created, execution time, and any skipped records

### Requirement 13: Neptune Ingestion 검증

**User Story:** As a RAG system developer, I want to verify that the Graph_Export_API returns real data after ingestion, so that the interactive schematic can display actual RTL topology.

#### Acceptance Criteria

1. WHEN the Ingestion_Pipeline completes for a given pipeline_id, THE Graph_Export_API SHALL return node and edge arrays whose counts match the modules discovered during parsing. IF the parsing produced zero modules, an empty array is a valid response. IF the parsing produced N>0 modules but the ingestion result contains zero nodes, THE Ingestion_Pipeline SHALL report this as an error indicating a parsing-to-ingestion mismatch
2. WHEN the Graph_Export_API is called with scope "chip" after ingestion, THE Graph_Export_API SHALL return Module nodes with INSTANTIATES edges reflecting the actual RTL hierarchy
3. WHEN the Graph_Export_API is called with scope "module" after ingestion, THE Graph_Export_API SHALL return Port and Signal nodes with CONNECTS_TO and DRIVES edges
4. THE Interactive_Schematic SHALL load and render the graph data returned by Graph_Export_API without JavaScript errors
5. WHEN the Interactive_Schematic requests graph data for an ingested module, THE Interactive_Schematic SHALL display nodes and edges matching the Neptune_Graph_DB content

### Requirement 14: SoC RTL 호환성 — 파서 범용성 검증

**User Story:** As a RAG system developer, I want to verify that the RTL parser pipeline works with SoC-level RTL (beyond NPU/trinity), so that the system can be extended to full chip analysis.

#### Acceptance Criteria

1. WHEN the RTL_Parser processes SoC RTL files containing AXI interconnect modules, THE RTL_Parser SHALL extract module declarations, port lists, and instantiation hierarchies without errors
2. WHEN the RTL_Parser encounters SystemVerilog constructs common in SoC RTL (e.g., `interface`, `modport`, `virtual interface`), THE RTL_Parser SHALL either parse them correctly or skip them gracefully with a warning log
3. IF the RTL_Parser encounters an unsupported construct, THEN THE RTL_Parser SHALL log the construct type and file location and continue processing remaining files without termination. IF the ratio of skipped constructs exceeds 30% of total constructs encountered in a file, THE RTL_Parser SHALL escalate the warning level and include the skip ratio in the pipeline summary
4. THE RTL_Parser SHALL support multiple pipeline_id values to distinguish NPU RTL results from SoC RTL results in DynamoDB
5. THE RTL_Parser SHALL maintain a common parsing strategy for Verilog/SystemVerilog syntax structures, while allowing RTL-type-specific chunking strategies (e.g., NPU vs SoC) to be configured independently per pipeline_id

### Requirement 15: SoC RTL 호환성 — 모듈 필터링

**User Story:** As a RAG system developer, I want the parser to support module filtering, so that SoC-level parsing can focus on specific subsystems without processing the entire RTL tree.

#### Acceptance Criteria

1. WHEN the RTL_Parser is invoked with a `module_filter` parameter (e.g., `--module-filter "tt_*"`), THE RTL_Parser SHALL process only files whose module names match the glob pattern. IF the filter pattern matches zero modules, THE RTL_Parser SHALL treat this as a valid outcome and continue without error
2. WHEN the RTL_Parser is invoked without a `module_filter` parameter, THE RTL_Parser SHALL process all RTL files in the target directory (backward-compatible behavior). IF the target directory contains no RTL files, THE RTL_Parser SHALL process nothing and succeed silently
3. WHEN the RTL_Parser applies a module filter, THE RTL_Parser SHALL log the filter pattern and the count of matched vs. skipped modules
4. THE RTL_Parser SHALL support comma-separated multiple filter patterns (e.g., `"tt_*,axi_*,cpu_*"`)
