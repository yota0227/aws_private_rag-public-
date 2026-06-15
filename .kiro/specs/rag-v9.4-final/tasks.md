# Implementation Plan: RAG v9.4 Final

## Overview

RAG v9.4는 BOS-AI Private RAG 시스템의 RTL 파이프라인 최종 대규모 개선이다. 4개 카테고리로 구현한다:
1. 즉시 수정 — Manual Claim 삽입 + HDD Self-Consistency Check
2. 파서 확장 — Expression Preserver, Generate Block Label, Parameter 추출, Wire Dimension, Struct Field
3. Neptune Ingestion Pipeline — DynamoDB → Neptune 노드/엣지 적재 + Graph Evidence Provider
4. 검증 — Graph Export API 검증 + Interactive Schematic 연동

SoC RTL 호환성 (Requirements 14-15)은 v9.5로 이동되어 본 구현에서 제외한다.

## Tasks

- [x] 1. Manual Claim 삽입 및 HDD Self-Consistency Check
  - [x] 1.1 EDC per-column ring claim 및 DFX 4-wrapper chain claims를 DynamoDB에 삽입하는 스크립트 작성
    - `lambda_src/` 디렉토리에 `inject_manual_claims.py` 스크립트 생성
    - EDC per-column ring claim: claim_id=manual_edc_ring_001, claim_type=structural, topic=EDC, confidence_score=1.0, source=manual_claim
    - DFX 4-wrapper claims: tt_noc_niu_router_dfx, tt_overlay_wrapper_dfx, tt_instrn_engine_wrapper_dfx, tt_t6_l1_partition_dfx (각각 claim_type=structural, topic=DFX, source=manual_claim)
    - EDC port [3:0] 배열 차원 claim 포함
    - _Requirements: 1.1, 1.3, 3.3, 4.1, 4.3_

  - [x] 1.2 HDD Generator Self-Consistency Check 구현
    - `rtl_parser_src/hdd_generator.py`에 `_validate_dispatch_coordinates(inference_text, ep_table) -> str` 함수 추가
    - EP Table 좌표와 [FROM LLM] 추론의 일관성 검증 로직 구현
    - 모순 발견 시: 좌표 부분 제거 → 문장 불완전 시 전체 단락 재생성
    - Warning log 발행: event=dispatch_coord_conflict, conflicting_values={...}
    - 프롬프트에 "EP Table의 좌표를 참조하여 [FROM LLM] 추론을 검증하라. East dispatch는 X=3, West dispatch는 X=0이다." 추가
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 1.3 좌표계 일반화 Self-Consistency 구현
    - `_validate_dispatch_coordinates()`를 `_validate_coordinates()`로 일반화
    - Overlay Y축 검증 추가: Y=4 (NOC2AXI row), Y=0..3 (Tensix rows)
    - Composite tile row_span 검증 (Y=4+Y=3 걸침)
    - [FROM LLM] 추론에서 X/Y 좌표가 EP Table과 모순되면 동일 discard/regenerate 로직 적용
    - _Requirements: 2.1, 2.2_

  - [x] 1.4 DFX 자동 추출 경로 구현
    - `rtl_parser_src/handler.py`에 DFX 모듈 자동 감지 로직 추가
    - module_filter='*_dfx' 패턴으로 DFX wrapper 모듈 자동 감지
    - 추출 대상: module name, file path, clock in/out port count, IJTAG ifdef presence
    - Claim 생성: topic="DFX", claim_type="structural", source="auto_extracted"
    - Manual claim과 auto claim 충돌 시 manual 우선 (confidence_score 비교)
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 2. Checkpoint — Category 1 검증
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. 파서 확장 — Port Binding ExpressionPreserver
  - [x] 3.1 Port Binding ExpressionPreserver 구현
    - `rtl_parser_src/port_binding_parser.py` 수정
    - signal_expr 필드에 산술 연산 포함 표현식 그대로 보존 확인
    - expression_type 필드 추가: simple, arithmetic, concatenation
    - 분류 로직: 빈 문자열→simple, {로 시작→concatenation, +/-/*/÷ 포함→arithmetic, 그 외→simple
    - Claim text 생성 시 expression 전체 포함 보장 (e.g., "binds port 'i_local_nodeid_y' to signal 'i_local_nodeid_y - 1'")
    - 중첩 괄호 표현식 (e.g., `(SizeX - 1) * 2`) 보존 without simplification
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x]* 3.2 Port Binding Expression round-trip property test 작성
    - **Property 4: Port binding expression round-trip**
    - hypothesis 라이브러리 사용, 최소 100 iterations
    - Generator: +, -, *, / 연산자 + 정수 리터럴 + 괄호 + 식별자 조합의 랜덤 표현식
    - Assertion: parse(format(expr)) == expr (whitespace-normalized)
    - **Validates: Requirements 5.1, 5.2, 5.4, 5.5**

- [x] 4. 파서 확장 — Generate Block Label Extraction
  - [x] 4.1 Generate Block Label 추출 구현
    - `rtl_parser_src/generate_block_parser.py`에 `_extract_generate_block_labels(clean_content) -> list` 함수 추가
    - 모든 labeled generate block 추출 (for/if 모두)
    - 반환: label, parent_label, hierarchy_path, block_type (for/if), instances 리스트
    - 인스턴스와 enclosing generate block 연관 기록
    - 중첩 generate block 계층 경로 구성 (e.g., gen_outer/gen_inner)
    - Claim 생성: claim_type="structural", topic="Hierarchy"
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x]* 4.2 Generate Block Label 추출 unit test 작성
    - gen_noc2axi_ne_opt 추출 및 instance 연관 검증
    - 중첩 generate block 계층 경로 검증
    - generate if 블록 label 추출 검증
    - _Requirements: 6.1, 6.2, 6.4_

- [x] 5. 파서 확장 — Top Module Parameter 및 Instantiation Override
  - [x] 5.1 Top Module Parameter 추출 구현
    - `rtl_parser_src/package_extractor.py`에 `extract_module_parameters(rtl_content, module_name, file_path, pipeline_id) -> list` 함수 추가
    - 패턴 1: module module_name #( parameter TYPE NAME = VALUE, ... ) (ports);
    - 패턴 2: module 내부 parameter TYPE NAME = VALUE;
    - topic: TopLevelParameter
    - 최소 추출 대상: AXI_SLV_OUTSTANDING_READS, AXI_SLV_OUTSTANDING_WRITES, AXI_SLV_RD_RDATA_FIFO_DEPTH
    - Expression default values (e.g., `DEPTH = WIDTH * 2`) 문자열 그대로 저장
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [x] 5.2 Instantiation Parameter Override 추출 구현
    - `rtl_parser_src/port_binding_parser.py`에 `_extract_instance_param_overrides(instance_text) -> list[dict]` 함수 추가
    - 패턴: `module_name #( .PARAM_NAME(value), ... ) instance_name (...)`
    - 반환: [{param_name, override_value, instance_name, module_name}]
    - topic: "InstanceParameter", claim_text: "Instance 'u_repeater' overrides NUM_REPEATERS=4"
    - _Requirements: 7.2 (extended)_

  - [x] 5.3 handler.py에서 extract_module_parameters 호출 연동
    - `rtl_parser_src/handler.py`의 `_process_rtl_file()`에서 package file이 아닌 일반 모듈 파일에서도 `extract_module_parameters()` 호출
    - _Requirements: 7.1, 7.4_

  - [x]* 5.4 Top Module Parameter 추출 unit test 작성
    - AXI_SLV_OUTSTANDING_READS=64 추출 검증
    - Expression default value 보존 검증
    - #(.NUM_REPEATERS(4)) instantiation override 추출 검증
    - _Requirements: 7.2, 7.3, 7.4_

- [x] 6. 파서 확장 — Wire Dimension 3차원 보존
  - [x] 6.1 Wire Dimension 3차원 보존 구현
    - `rtl_parser_src/wire_declaration_parser.py`의 Pattern C 정규식 수정
    - packed dimension 그룹과 array dimension 그룹 명확히 분리
    - Group 1: type name (_t 접미사), Group 2: packed dimensions, Group 3: signal name, Group 4: array dimensions
    - 검증: de_to_t6_coloumn[SizeX][SizeY-1][2] → dims = [SizeX, SizeY-1, 2] (3개 모두 보존)
    - _Requirements: 8.1, 8.2, 8.3_

  - [x]* 6.2 Wire dimension count preservation property test 작성
    - **Property 1: Wire dimension count preservation**
    - hypothesis 라이브러리 사용, 최소 100 iterations
    - Generator: 1-5개 차원의 랜덤 wire 선언 (각 차원은 identifier 또는 expression)
    - Assertion: len(extracted_dims) == N and order matches
    - **Validates: Requirements 8.1, 8.3, 8.4**

- [x] 7. 파서 확장 — Struct Field Packed Dimension
  - [x] 7.1 Struct Field Packed Dimension 추출 구현
    - `rtl_parser_src/package_extractor.py`의 `_parse_struct_fields()` 수정
    - Packed dimension ([7:0] field_name) vs Unpacked dimension (field_name [3:0]) 구분
    - 반환 dict에 packed_dim, unpacked_dim 키 추가
    - 필드 수 검증: 추출된 필드 수가 소스와 불일치 시 에러 보고 (extraction fail + mismatch report)
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x]* 7.2 Struct field count invariant property test 작성
    - **Property 2: Struct field count invariant**
    - hypothesis 라이브러리 사용, 최소 100 iterations
    - Generator: 1-15개 필드의 랜덤 struct 정의 (packed/unpacked/custom type 혼합)
    - Assertion: len(extracted_fields) == N and packed/unpacked correctly classified
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4**

- [x] 8. Checkpoint — Category 2 파서 확장 검증
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Neptune Ingestion Pipeline — 노드 적재
  - [x] 9.1 neptune_ingestion.py 스크립트 기본 구조 및 CLI 인터페이스 작성
    - `lambda_src/neptune_ingestion.py` 생성
    - CLI: `py neptune_ingestion.py --pipeline-id <id> [--neptune-endpoint] [--batch-size 50] [--dry-run] [--verbose]`
    - IAM SigV4 인증 (botocore.auth.SigV4Auth + AWSRequest)
    - Neptune endpoint 미설정 시: config 확인 → 에러 로그 → exit code 1 (네트워크 시도 없음)
    - Neptune endpoint 설정되었으나 unreachable 시: 에러 로그 → exit code 1
    - _Requirements: 12.1, 12.3, 12.4_

  - [x] 9.2 DynamoDB 스캔 및 데이터 변환 로직 구현
    - pipeline_id로 DynamoDB bos-ai-claim-db-prod 테이블 스캔
    - module_parse records → ModuleDef 노드 변환 (name, file_path, pipeline_id, module_type)
    - Instance 노드 변환 (instance_name, hier_path, generate_scope, x, y, parent_instance)
    - port data → PortDef/PortInstance 노드 변환 (name, direction, bit_width, parent_module)
    - wire claims (topic=WireTopology) → Signal 노드 변환 (name, dimensions, struct_type, purpose)
    - clock domain claims → ClockDomain 노드 변환 (name, frequency, source_module)
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 9.3 Neptune MERGE upsert로 노드 적재 구현
    - Idempotent upsert: MERGE openCypher with composite key (pipeline_id + name/hier_path)
    - Batch upsert (default batch_size=50)
    - ModuleDef, Instance, PortDef, PortInstance, Signal, ClockDomain 노드 생성
    - 재실행 시 중복 노드 방지
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 10. Neptune Ingestion Pipeline — 엣지 적재
  - [x] 10.1 Neptune 엣지 적재 구현
    - DEFINES (ModuleDef → PortDef)
    - INSTANCE_OF (Instance → ModuleDef): instance_name, generate_scope
    - INSTANTIATES (Instance → Instance): hier_path
    - HAS_PORT (Instance → PortInstance)
    - BINDS_TO (PortInstance → Signal): signal_expr, expression_type
    - DRIVES (PortInstance → Signal): driver_type (output/inout)
    - READS (Signal → PortInstance): reader_type (input/inout)
    - BELONGS_TO (Signal → ClockDomain)
    - Idempotent MERGE upsert로 중복 엣지 방지
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 10.2 Completion summary 로그 및 에러 핸들링 구현
    - 완료 시 summary log: total_nodes_created, total_edges_created, execution_time_seconds, skipped_records
    - Parsing-to-ingestion mismatch detection: N>0 모듈 발견 but 0 노드 → 에러 보고
    - Skip ratio > 30% 시 경고 레벨 상향
    - DynamoDB scan timeout → exponential backoff retry (max 3)
    - _Requirements: 12.5, 13.1_

  - [x]* 10.3 Neptune ingestion idempotence property test 작성
    - **Property 3: Neptune ingestion idempotence**
    - hypothesis 라이브러리 사용, 최소 100 iterations
    - Generator: 랜덤 module_parse + claim records (mocked Neptune client)
    - Assertion: run_twice_count == run_once_count for both nodes and edges
    - **Validates: Requirements 10.5, 11.5**

- [ ] 11. Graph Evidence Provider 구현
  - [x] 11.1 graph_evidence_provider.py 모듈 생성
    - `rtl_parser_src/graph_evidence_provider.py` 신규 생성
    - `GraphEvidenceProvider` 클래스 구현
    - `get_section_evidence(topic, module_name) -> dict`: Neptune에서 HDD 섹션별 evidence 조회
    - `get_connectivity_path(from_port, to_port) -> list`: trace_signal_path API 호출
    - `get_hierarchy_tree(module_name, depth=3) -> dict`: find-instantiation-tree API 호출
    - `get_instance_params(instance_hier_path) -> dict`: instance parameter override 값 조회
    - Fallback: Neptune 미접속 시 graceful degradation (claim-only 모드)
    - _Requirements: 13.2, 13.3_

  - [x] 11.2 HDD Generator에 Graph Evidence Provider 연동
    - `rtl_parser_src/hdd_generator.py`의 `_build_hdd_prompt()`에서 topic별 graph evidence 조회
    - Evidence table 형식으로 프롬프트에 주입 ([GRAPH EVIDENCE — Section] 형식)
    - Neptune 미접속 시 기존 claim-only 모드로 동작
    - _Requirements: 13.2, 13.3_

  - [x]* 11.3 Graph Evidence Provider unit test 작성
    - Neptune 접속 가능 시 evidence 조회 검증
    - Neptune 미접속 시 graceful degradation 검증
    - Evidence table 형식 출력 검증
    - _Requirements: 13.2, 13.3_

- [x] 12. Checkpoint — Neptune Ingestion 및 Graph Evidence 검증
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Neptune Ingestion 검증 및 Interactive Schematic 연동
  - [x] 13.1 Graph Export API 검증 로직 구현
    - Ingestion 완료 후 Graph Export API 호출하여 node/edge count 검증
    - scope "chip": Module nodes + INSTANTIATES edges 반환 확인
    - scope "module": Port + Signal nodes + CONNECTS_TO/DRIVES edges 반환 확인
    - Parsing N>0 modules but ingestion 0 nodes → 에러 보고
    - _Requirements: 13.1, 13.2, 13.3_

  - [x]* 13.2 Integration test — Neptune ingestion end-to-end
    - DynamoDB → neptune_ingestion.py → Graph Export API 검증
    - Graph evidence provider → HDD evidence injection 검증
    - Interactive Schematic graph data 로딩 검증 (JS error 없음)
    - _Requirements: 13.1, 13.4, 13.5_

- [x] 14. Final Checkpoint — 전체 통합 검증
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (4 properties from design)
- Unit tests validate specific examples and edge cases
- Requirements 14-15 (SoC RTL 호환성)은 v9.5로 이동되어 본 구현에서 제외
- Python 테스트는 `py -m pytest` (rtl_parser_src/ 디렉토리에서 실행)
- hypothesis 라이브러리를 PBT에 사용 (최소 100 iterations)
- Neptune 관련 integration test는 Neptune endpoint 접근 가능 시에만 실행

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "4.1", "6.1", "9.1"] },
    { "id": 1, "tasks": ["1.2", "3.2", "4.2", "5.1", "6.2", "7.1", "9.2"] },
    { "id": 2, "tasks": ["1.3", "5.2", "5.3", "5.4", "7.2", "9.3"] },
    { "id": 3, "tasks": ["1.4", "10.1"] },
    { "id": 4, "tasks": ["10.2", "10.3", "11.1"] },
    { "id": 5, "tasks": ["11.2", "11.3"] },
    { "id": 6, "tasks": ["13.1"] },
    { "id": 7, "tasks": ["13.2"] }
  ]
}
```
