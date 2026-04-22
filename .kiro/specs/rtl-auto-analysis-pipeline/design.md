# 설계 문서: RTL 자동 분석 파이프라인

## 개요

RTL 자동 분석 파이프라인은 기존 RTL Parser Lambda의 단일 모듈 파싱 기능을 확장하여, 다단계 분석(계층 추출, 클럭 도메인 분석, 데이터 흐름 추적, 토픽 분류, Claim 생성, HDD 섹션 생성, SRAM Inventory 추출)을 자동으로 수행하는 시스템이다.

핵심 설계 원칙:
- 인프라 불변: S3 버킷, OpenSearch 인덱스, Lambda, DynamoDB 등 기존 리소스를 재사용. 새 칩 추가 시 인프라 변경 없음
- Pipeline_ID 기반 격리: S3 디렉토리 `rtl-sources/{chip_type}_{date}/`에서 Pipeline_ID를 추출하여 모든 분석 결과를 논리적으로 격리
- 기존 네트워크 제약 준수: RTL Parser Lambda(VPC 밖) AOSS/Bedrock 직접 접근, Main Lambda(VPC 안) Lambda invoke로 우회

첫 번째 대상: Trinity/N1B0 RTL (`rtl-sources/tt_20260221/`, 9,465개 파일, 539MB)

## 아키텍처

### 시스템 아키텍처 다이어그램

```
Seoul (ap-northeast-2)
======================

  RTL S3 Bucket                    RTL Parser Lambda (VPC 밖)
  bos-ai-rtl-src-{acct}           lambda-rtl-parser-seoul-dev
  +------------------+            +---------------------------+
  | rtl-sources/     |--S3 Event->| 모듈 파싱 (정규식)        |
  |   tt_20260221/   |            | Pipeline_ID 추출          |
  | rtl-parsed/      |            | OpenSearch 인덱싱         |
  |   hierarchy/     |            | Titan Embeddings 생성     |
  |   hdd/           |            | 파싱 완료 이벤트 발행     |
  +------------------+            +-------------+-------------+
         ^                                      |
         |                                      | DynamoDB 이벤트
         |                                      v
         |                        +---------------------------+
         |                        | Analysis Orchestrator     |
         |                        | (Step Functions)          |
         |                        | - Stage 1: Baseline       |
         |                        | - Stage 2: HDD Generation |
         |                        | - 재시도/에러 처리        |
         |                        +-------------+-------------+
         |                                      |
         |                    +-----------------+-----------------+
         |                    |                                   |
         |          Stage 1: Baseline              Stage 2: Knowledge Gen
         |          +-----------------+            +-------------------+
         |          | Hierarchy Ext.  |            | Claim Generator   |
         +<---------| Clock Domain    |            | (Bedrock Claude)  |
         |          | Dataflow Track  |            | HDD Section Gen   |
         |          | Topic Classify  |            | (Bedrock Claude)  |
         |          | SRAM Inventory  |            | +심화분석 4종 조회 |
         |          +-----------------+            +-------------------+
         |                    |                           |
         v                    v                           v
  +------------------+  +----------+              +----------+
  | DynamoDB         |  | OpenSearch|              | OpenSearch|
  | - 분석 상태 추적 |  | AOSS     |              | AOSS     |
  | - Claim DB       |  | us-east-1|              | us-east-1|
  +------------------+  +----------+              +----------+

Virginia (us-east-1)
====================
  OpenSearch Serverless              Bedrock Runtime
  iw3pzcloa0en8d90hh7               Claude 3 Haiku
  +------------------+              +------------------+
  | rtl-parsed index |              | Claim 생성       |
  | 벡터 검색 (1024d)|              | HDD 섹션 생성    |
  | analysis_type별  |              | Titan Embed v2   |
  | pipeline_id 격리 |              +------------------+
  +------------------+
```

### 분석 파이프라인 단계별 흐름

```mermaid
graph TD
    A["S3 업로드: rtl-sources/{chip}_{date}/"] --> B[RTL Parser Lambda]
    B --> B1[모듈 파싱 + Pipeline_ID 추출]
    B1 --> B2[OpenSearch 인덱싱 + S3 parsed JSON 저장]
    B2 --> C[파싱 완료 이벤트 DynamoDB 기록]
    C --> D[Analysis Orchestrator Step Functions]
    D --> E[Stage 1: Baseline Analysis]
    E --> E1[1.1 Hierarchy Extractor]
    E1 --> E2[1.2 Clock Domain Analyzer]
    E2 --> E3[1.3 Dataflow Tracker]
    E3 --> E4[1.4 Topic Classifier]
    E4 --> E5[1.5 SRAM Inventory Extractor]
    E5 --> F[Stage 2: Knowledge Generation]
    F --> F1[2.1 Claim Generator LLM]
    F1 --> F2[2.2 HDD Section Generator LLM]
    F2 --> G[완료: OpenSearch + S3 + DynamoDB 업데이트]
```

### Step Functions 상태 머신 설계

```mermaid
stateDiagram-v2
    [*] --> ValidateInput
    ValidateInput --> QueryParsedModules: 유효
    ValidateInput --> Failed: 무효
    QueryParsedModules --> HierarchyExtraction
    HierarchyExtraction --> ClockDomainAnalysis: 성공
    HierarchyExtraction --> RetryHierarchy: 실패
    RetryHierarchy --> HierarchyExtraction: 재시도 1회
    RetryHierarchy --> SkipToClockDomain: 재시도 초과
    SkipToClockDomain --> ClockDomainAnalysis
    ClockDomainAnalysis --> DataflowTracking: 성공
    ClockDomainAnalysis --> RetryClockDomain: 실패
    RetryClockDomain --> ClockDomainAnalysis: 재시도 1회
    RetryClockDomain --> SkipToDataflow: 재시도 초과
    SkipToDataflow --> DataflowTracking
    DataflowTracking --> TopicClassification: 성공
    DataflowTracking --> RetryDataflow: 실패
    RetryDataflow --> DataflowTracking: 재시도 1회
    RetryDataflow --> SkipToTopic: 재시도 초과
    SkipToTopic --> TopicClassification
    TopicClassification --> ClaimGeneration: 성공
    TopicClassification --> RetryTopic: 실패
    RetryTopic --> TopicClassification: 재시도 1회
    RetryTopic --> SkipToClaim: 재시도 초과
    SkipToClaim --> ClaimGeneration
    ClaimGeneration --> HDDGeneration: 성공
    ClaimGeneration --> RetryClaimGen: 실패
    RetryClaimGen --> ClaimGeneration: 재시도 1회
    RetryClaimGen --> SkipToHDD: 재시도 초과
    SkipToHDD --> HDDGeneration
    HDDGeneration --> UpdateStatus: 성공
    HDDGeneration --> RetryHDDGen: 실패
    RetryHDDGen --> HDDGeneration: 재시도 1회
    RetryHDDGen --> UpdateStatus: 재시도 초과
    UpdateStatus --> [*]
    Failed --> [*]
```

설계 결정 사항:
- 각 분석 단계는 최대 2회 재시도 (원본 1회 + 재시도 1회). 재시도 실패 시 해당 단계를 건너뛰고 후속 단계 진행
- Step Functions Express Workflow 사용 (5분 이내 완료 예상, 비용 효율적)
- 단, 전체 파이프라인이 9,465개 파일을 처리하므로 Standard Workflow 사용 (최대 1년 실행 가능)
- Pipeline_ID를 Step Functions 실행 이름에 포함하여 추적성 확보

## 컴포넌트 및 인터페이스

### 1. RTL Parser Lambda (기존 확장)

현재 `lambda-rtl-parser-seoul-dev`를 확장한다. 기존 기능(모듈 파싱, OpenSearch 인덱싱)에 Pipeline_ID 추출과 파싱 완료 이벤트 발행을 추가한다.

확장 사항:
- S3 키에서 Pipeline_ID 추출: `rtl-sources/{chip_type}_{date}/...` 에서 `{chip_type}_{date}` 파싱
- 파싱 결과에 `pipeline_id`, `chip_type`, `snapshot_date` 메타데이터 추가
- 파싱 완료 시 DynamoDB `rag-extraction-tasks` 테이블에 완료 이벤트 기록
- OpenSearch 문서에 `pipeline_id`, `analysis_type=module_parse` 필드 추가

인터페이스:
```python
# 입력: S3 Event Notification
{
    "Records": [{
        "s3": {
            "bucket": {"name": "bos-ai-rtl-src-{acct}"},
            "object": {"key": "rtl-sources/tt_20260221/path/to/module.sv"}
        }
    }]
}

# 출력: DynamoDB 파싱 완료 이벤트
{
    "task_id": "parse_{pipeline_id}_{file_hash}",
    "pipeline_id": "tt_20260221",
    "chip_type": "tt",
    "snapshot_date": "20260221",
    "status": "parsed",
    "module_name": "tt_dispatch_top",
    "file_path": "rtl-sources/tt_20260221/dispatch/tt_dispatch_top.sv",
    "timestamp": "2026-02-21T10:00:00Z"
}
```

### 2. Analysis Orchestrator (Step Functions)

Pipeline_ID 단위로 전체 분석 파이프라인을 조율하는 Step Functions 상태 머신이다.

트리거 메커니즘:
- 수동 트리거 (1차 구현): 엔지니어가 Pipeline_ID를 지정하여 Step Functions 실행을 시작
- 자동 트리거 (향후): EventBridge 규칙으로 DynamoDB Streams 파싱 완료 이벤트 감지

입력 인터페이스:
```json
{
    "pipeline_id": "tt_20260221",
    "chip_type": "tt",
    "snapshot_date": "20260221",
    "s3_prefix": "rtl-sources/tt_20260221/",
    "trigger_type": "manual",
    "options": {
        "skip_stages": [],
        "variant_baseline_id": null
    }
}
```

상태 관리 (DynamoDB `rag-extraction-tasks` 테이블):
```json
{
    "task_id": "analysis_{pipeline_id}_{stage}",
    "pipeline_id": "tt_20260221",
    "stage": "hierarchy_extraction",
    "status": "in_progress",
    "started_at": "2026-02-21T10:05:00Z",
    "updated_at": "2026-02-21T10:10:00Z",
    "retry_count": 0,
    "error_message": null,
    "modules_processed": 1500,
    "modules_total": 9465
}
```

### 3. Hierarchy Extractor

RTL Parser Lambda가 추출한 개별 모듈의 인스턴스 목록을 조합하여 전체 계층 트리를 구축한다.

알고리즘:
1. OpenSearch에서 해당 Pipeline_ID의 모든 파싱 결과를 조회 (module_name, instance_list)
2. 각 모듈의 instance_list에서 `instance_name: module_type` 쌍을 추출
3. module_type을 키로 하여 parent-child 관계 그래프를 구축
4. 루트 모듈(다른 모듈에 의해 인스턴스화되지 않는 모듈)을 식별
5. DFS로 계층 경로를 생성 (예: `trinity.gen_dispatch_e.tt_dispatch_top_inst_east`)
6. 각 노드에 클럭 신호, 리셋 신호, 메모리 인스턴스 정보를 매핑

출력 형식:
```json
{
    "pipeline_id": "tt_20260221",
    "root_module": "trinity",
    "total_modules": 1247,
    "hierarchy": [
        {
            "module_name": "trinity",
            "instance_name": "top",
            "hierarchy_path": "trinity",
            "clock_signals": ["i_ai_clk", "i_noc_clk"],
            "reset_signals": ["i_rst_n"],
            "memory_instances": [],
            "children": [
                {
                    "module_name": "tt_dispatch_top",
                    "instance_name": "gen_dispatch_e",
                    "hierarchy_path": "trinity.gen_dispatch_e",
                    "clock_signals": ["i_ai_clk"],
                    "reset_signals": ["i_rst_n"],
                    "memory_instances": ["u_sram_256x64"],
                    "children": []
                }
            ]
        }
    ]
}
```

S3 저장 경로:
- JSON: `rtl-parsed/hierarchy/{pipeline_id}/hierarchy_tree.json`
- CSV: `rtl-parsed/hierarchy/{pipeline_id}/hierarchy_tree.csv` (Hierarchy, Module, Clock, Reset, Memory_Instances 컬럼)

### 4. Clock Domain Analyzer

RTL 소스 코드에서 클럭 도메인을 추출하고 CDC 경계를 식별한다.

분석 로직:
1. S3에서 RTL 소스 파일을 읽어 `always_ff @(posedge <clock>)` 및 `always @(posedge <clock>)` 패턴 매칭
2. 추출된 클럭 신호를 도메인 그룹으로 분류:
   - `i_ai_clk` 계열: `ai_clock_domain`
   - `i_noc_clk` 계열: `noc_clock_domain`
   - `i_dm_clk` 계열: `dm_clock_domain`
   - `i_ref_clk` 계열: `ref_clock_domain`
   - 기타: `unclassified_clock`
3. 모듈 내 2개 이상 클럭 도메인 감지 시 CDC 경계 모듈로 표시
4. 결과를 OpenSearch에 `analysis_type=clock_domain` 문서로 인덱싱

출력 형식:
```json
{
    "pipeline_id": "tt_20260221",
    "module_name": "tt_noc_router",
    "analysis_type": "clock_domain",
    "clock_domains": [
        {"domain": "noc_clock_domain", "signals": ["i_noc_clk"]},
        {"domain": "ai_clock_domain", "signals": ["i_ai_clk"]}
    ],
    "is_cdc_boundary": true,
    "cdc_pairs": [["noc_clock_domain", "ai_clock_domain"]]
}
```

### 5. Dataflow Tracker

모듈 간 신호 연결 관계를 추적하여 데이터 흐름 그래프를 생성한다.

분석 로직:
1. 계층 트리의 각 parent 모듈에서 child 인스턴스의 포트 매핑을 추출
2. 정규식으로 `.port_name(signal_name)` 패턴을 파싱
3. 상위 모듈 신호와 하위 모듈 포트 간 매핑을 기록
4. 비트 폭 정보 추출 (`[MSB:LSB]` 패턴)
5. 비트 폭 불일치 감지 시 `width_mismatch` 경고 태깅

출력 형식:
```json
{
    "pipeline_id": "tt_20260221",
    "module_name": "tt_dispatch_top",
    "analysis_type": "dataflow",
    "connections": [
        {
            "parent_signal": "dispatch_data_out",
            "child_module": "tt_dispatch_engine",
            "child_port": "i_data",
            "direction": "input",
            "bit_width": 64,
            "width_mismatch": false
        }
    ]
}
```

### 6. Topic Classifier

파일 경로와 모듈명 패턴을 기반으로 RTL 모듈을 주제별로 분류한다.

분류 규칙 (우선순위 순):
```python
TOPIC_RULES = {
    "NoC":         {"path": ["*/noc/*"], "prefix": ["tt_noc_", "noc_"]},
    "FPU":         {"path": ["*/fpu/*"], "prefix": ["tt_fpu_", "fpu_"]},
    "SFPU":        {"path": ["*/sfpu/*"], "prefix": ["tt_sfpu_", "sfpu_"]},
    "TDMA":        {"path": ["*/tdma/*"], "prefix": ["tt_tdma_", "tdma_"]},
    "Overlay":     {"path": ["*/overlay/*"], "prefix": ["tt_overlay_", "overlay_"]},
    "EDC":         {"path": ["*/edc/*"], "prefix": ["tt_edc_", "edc_"]},
    "Dispatch":    {"path": ["*/dispatch/*"], "prefix": ["tt_dispatch_", "dispatch_"]},
    "L1_Cache":    {"path": ["*/l1/*", "*/cache/*"], "prefix": ["tt_l1_", "l1_"]},
    "Clock_Reset": {"path": ["*/clk/*", "*/reset/*"], "prefix": ["tt_clk_", "clk_", "rst_"]},
    "DFX":         {"path": ["*/dfx/*"], "prefix": ["tt_dfx_", "dfx_"]},
    "NIU":         {"path": ["*/niu/*"], "prefix": ["tt_niu_", "niu_"]},
    "SMN":         {"path": ["*/smn/*"], "prefix": ["tt_smn_", "smn_"]},
}
```

분류 로직:
1. 파일 경로 패턴 매칭 (우선)
2. 모듈명 접두사 패턴 매칭
3. 복수 토픽 매칭 시 모두 태깅
4. 미분류 시 `unclassified` + 계층 트리에서 가장 가까운 분류된 상위 모듈의 토픽을 상속 후보로 제안

### 7. Claim Generator

Bedrock Claude를 호출하여 분석 결과로부터 구조화된 claim을 생성한다.

LLM 호출 전략:
- 모델: `anthropic.claude-3-haiku-20240307-v1:0` (us-east-1)
- 토픽별 모듈 그룹 단위로 호출 (예: NoC 관련 모듈 50개를 하나의 프롬프트로)
- 단일 호출당 입력 토큰 100,000 이하 제한
- 초과 시 모듈 그룹을 분할하여 복수 호출
- 타임아웃: 60초, 재시도: 최대 1회

Claim 출력 형식:
```json
{
    "claim_id": "clm_{pipeline_id}_{topic}_{seq}",
    "pipeline_id": "tt_20260221",
    "module_name": "tt_noc_router",
    "topic": "NoC",
    "claim_type": "connectivity",
    "claim_text": "tt_noc_router는 4개의 방향(N/S/E/W) 포트를 통해 메시 토폴로지를 구성하며, 각 방향별 64비트 데이터 경로를 제공한다",
    "confidence_score": 0.95,
    "source_files": ["rtl-sources/tt_20260221/noc/tt_noc_router.sv"],
    "version": 1,
    "status": "auto_generated",
    "created_at": "2026-02-21T10:30:00Z"
}
```

### 8. HDD Section Generator

분석 결과를 조합하여 HDD 문서 섹션을 자동 생성한다. 엔지니어가 작성한 HDD 문서(N1B0_NPU_HDD_v0.1.md, EDC_HDD.md, overlay_HDD_v0.1.md)의 구조와 깊이를 참고한다.

심화 분석 결과 조회 로직:

`handle_hdd_generation()` 핸들러는 기존 분석 결과(hierarchy, clock_domain, dataflow, topic, claim)에 더해, OpenSearch에서 다음 4종의 심화 분석 결과를 추가로 조회하여 토픽별 HDD 생성 시 LLM 프롬프트에 포함한다:

```python
# handle_hdd_generation() 내 심화 분석 결과 조회
chip_config_docs = _opensearch_scroll_query(pipeline_id, "chip_config")
edc_topology_docs = _opensearch_scroll_query(pipeline_id, "edc_topology")
noc_protocol_docs = _opensearch_scroll_query(pipeline_id, "noc_protocol")
overlay_deep_docs = _opensearch_scroll_query(pipeline_id, "overlay_deep")
sram_inventory_docs = _opensearch_scroll_query(pipeline_id, "sram_inventory")
```

토픽별 심화 분석 데이터 매핑:

| HDD 유형 | 토픽 | 추가 조회 analysis_type | 프롬프트에 포함되는 데이터 |
|----------|------|------------------------|--------------------------|
| 칩 전체 HDD | all/chip/top | chip_config, sram_inventory | Package Constants (SizeX/SizeY, NumTensix, tile_t enum, Endpoint Index Table), SRAM Inventory (메모리 타입별 수량, 총 용량, 서브시스템별 분포) |
| EDC HDD | EDC | edc_topology | 링 토폴로지 다이어그램, 시리얼 버스 인터페이스 사양, 하베스트 바이패스 흐름도, 노드 ID 테이블 |
| NoC HDD | NoC | noc_protocol | 라우팅 알고리즘 3종 비교 테이블, flit 헤더 구조, AXI 주소 가스켓 매핑, 보안 펜스 메커니즘 |
| Overlay HDD | Overlay | overlay_deep | CPU 클러스터 파라미터, L1 캐시 구성 테이블, APB 슬레이브 레지스터 맵 |

`_build_hdd_prompt()` 함수 확장:

```python
def _build_hdd_prompt(
    pipeline_id: str,
    topic: str,
    hdd_type: str,
    hierarchy: dict[str, Any],
    clock_domains: list[dict[str, Any]],
    dataflow: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    deep_analysis: dict[str, Any] | None = None,  # 신규 파라미터
) -> str:
    # ... 기존 프롬프트 구성 ...
    # deep_analysis가 있으면 토픽에 맞는 심화 데이터를 프롬프트에 추가
    if deep_analysis:
        if hdd_type == "chip" and "chip_config" in deep_analysis:
            prompt += f"\nPackage Constants:\n{json.dumps(deep_analysis['chip_config'])[:2000]}"
        if hdd_type == "chip" and "sram_inventory" in deep_analysis:
            prompt += f"\nSRAM Inventory:\n{json.dumps(deep_analysis['sram_inventory'])[:2000]}"
        if topic.lower() == "edc" and "edc_topology" in deep_analysis:
            prompt += f"\nEDC Topology:\n{json.dumps(deep_analysis['edc_topology'])[:2000]}"
        if topic.lower() == "noc" and "noc_protocol" in deep_analysis:
            prompt += f"\nNoC Protocol:\n{json.dumps(deep_analysis['noc_protocol'])[:2000]}"
        if topic.lower() == "overlay" and "overlay_deep" in deep_analysis:
            prompt += f"\nOverlay Deep:\n{json.dumps(deep_analysis['overlay_deep'])[:2000]}"
```

HDD 섹션 유형별 생성 전략:

칩 전체 HDD (N1B0_NPU_HDD 스타일):
- 섹션: Overview, Package Constants, Top-Level Ports, Module Hierarchy, Compute Tile, Dispatch Engine, NoC Fabric, NIU, Clock Architecture, Reset Architecture, EDC, Power Management, SRAM Inventory, DFX, P and R Guide, SW Programming Guide, RTL File Reference
- 입력: 전체 계층 트리 + 토픽별 요약 + 클럭 도메인 전체 맵

서브시스템 HDD (EDC_HDD 스타일):
- 섹션: Overview, Architecture, Serial Bus Interface, Packet Format, Node ID Structure, Module Hierarchy, Module Reference, Ring Topology, Harvest Bypass, BIU, Node Configuration, Event Types, CDC, Firmware Interface, Inter-Cluster Connectivity, Instance Paths
- 입력: 해당 토픽의 모듈 그룹 + 계층 + 클럭 + 데이터 흐름 + claim

블록 HDD (overlay_HDD 스타일):
- 섹션: Overview, Position in Grid, Feature Summary, Block Diagram, Sub-module Hierarchy, Feature Details, Control Path, Key Parameters, Clock/Reset Summary, APB Register Interfaces, Worked Example, Verification Checklist, Key RTL File Index
- 입력: 단일 블록 모듈 + 하위 계층 + 포트 매핑

S3 저장 경로:
- `rtl-parsed/hdd/{pipeline_id}/{topic}_HDD.md`
- `rtl-parsed/hdd/{pipeline_id}/{chip_type}_NPU_HDD.md` (칩 전체)

### 9. Package Parameter Extractor (RTL Parser Lambda 확장)

RTL Parser Lambda에 `*_pkg.sv` 파일 전용 파싱 로직을 추가하여 패키지 파라미터 및 칩 구성 정보를 추출한다.

선별적 파일 읽기 전략:

chip_config 분석 시 전체 RTL 파일(9,465개)을 순회하지 않고, `*_pkg.sv` 파일만 선별적으로 읽는다:

```python
def handle_chip_config(event):
    # S3 ListObjects에서 *_pkg.sv 파일만 필터링
    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=RTL_S3_BUCKET, Prefix=s3_prefix)
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith("_pkg.sv"):  # pkg.sv 파일만 선별
                continue
            # 파싱 로직 실행
```

타임아웃 분할 실행 전략:

단일 Lambda 실행에서 300초 타임아웃을 초과할 위험이 있는 경우, 토픽별로 분할하여 개별 Lambda 호출로 실행한다:

```python
# 토픽별 pkg 파일 그룹화
PKG_TOPIC_PREFIXES = {
    "noc": ["tt_noc_pkg", "noc_"],
    "edc": ["tt_edc_pkg", "tt_edc1_pkg", "edc_"],
    "overlay": ["tt_overlay_pkg", "overlay_"],
    "dispatch": ["tt_dispatch_pkg", "dispatch_"],
    "general": [],  # 나머지 모든 pkg 파일
}

# 타임아웃 임박 시 (남은 시간 < 30초) 미처리 토픽을 별도 Lambda로 분할 실행
if context.get_remaining_time_in_millis() < 30000:
    for remaining_topic in unprocessed_topics:
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps({
                "pipeline_id": pipeline_id,
                "stage": "chip_config",
                "topic_filter": remaining_topic,
            }),
        )
```

S3 ListObjects 호출 최소화:
- 사전 구축된 파일 목록(module_parse 문서의 file_path 필드)에서 `*_pkg.sv` 패턴을 필터링하여 S3 ListObjects 호출을 최소화
- OpenSearch에서 `pipeline_id`로 module_parse 문서를 조회한 후, file_path에서 `_pkg.sv`로 끝나는 파일만 추출

분석 로직:
1. 파일명이 `*_pkg.sv` 패턴과 일치하는 경우 전용 파싱 경로 진입
2. `localparam` 선언 추출: `localparam\s+(\w+)\s*=\s*(.+?);` 패턴
3. `parameter` 선언 추출: `parameter\s+(\w+)\s*=\s*(.+?);` 패턴
4. `typedef enum` 선언 추출: `typedef\s+enum\s*(?:logic\s*\[.*?\])?\s*\{([^}]+)\}\s*(\w+);` 패턴
5. 칩 구성 파라미터 식별: SizeX, SizeY, NumTensix, NumNoc2Axi, NumDispatch 등 키워드 매칭
6. 타일 타입 enum에서 타일 타입 → RTL 모듈 매핑 추출

출력 형식:
```json
{
    "pipeline_id": "tt_20260221",
    "analysis_type": "chip_config",
    "package_file": "tt_noc_pkg.sv",
    "parameters": {
        "SizeX": {"value": "4", "type": "localparam"},
        "SizeY": {"value": "5", "type": "localparam"},
        "NumTensix": {"value": "12", "type": "localparam"}
    },
    "enums": {
        "tile_type_t": {
            "values": ["TENSIX", "NOC2AXI_NE_OPT", "DISPATCH"],
            "module_mapping": {"TENSIX": "tt_tensix_tile", "NOC2AXI_NE_OPT": "tt_noc2axi"}
        }
    }
}
```

### 10. EDC Topology Analyzer

EDC 서브시스템의 링 토폴로지, 시리얼 버스 프로토콜, 하베스트 바이패스 메커니즘을 분석한다. `analysis_handler.py`에 `handle_edc_topology(event)` 핸들러로 구현한다.

분석 로직:
1. `tt_edc1_*` 모듈의 인스턴스화 패턴에서 노드 간 연결 관계 추출
2. 연결 관계로부터 링 토폴로지 재구성 (U-shape: Segment A 하향 → U-turn → Segment B 상향)
3. `tt_edc1_serial_bus_mux` / `tt_edc1_serial_bus_demux` 인스턴스화 패턴에서 하베스트 바이패스 경로 식별
4. `tt_edc1_pkg.sv`에서 시리얼 버스 인터페이스 정의 추출 (`req_tgl`, `ack_tgl`, `data`, `data_p`, `async_init`)
5. `node_id_part`, `node_id_subp`, `node_id_inst` 필드에서 노드 ID 디코딩 테이블 생성

출력 형식:
```json
{
    "pipeline_id": "tt_20260221",
    "analysis_type": "edc_topology",
    "ring_topology": {
        "segment_a": ["edc_node_0", "edc_node_1", "edc_node_2"],
        "u_turn": "edc_node_2",
        "segment_b": ["edc_node_3", "edc_node_4", "edc_node_5"]
    },
    "harvest_bypass_paths": [
        {"from": "edc_node_1", "to": "edc_node_3", "type": "mux_bypass"}
    ],
    "serial_bus_interface": {
        "signals": ["req_tgl", "ack_tgl", "data", "data_p", "async_init"]
    },
    "node_id_table": [
        {"node": "edc_node_0", "part": 0, "subp": 0, "inst": 0}
    ]
}
```

### 11. NoC Protocol Analyzer

NoC의 라우팅 알고리즘, 패킷 구조(flit format), 보안 펜스 메커니즘을 분석한다. `analysis_handler.py`에 `handle_noc_protocol(event)` 핸들러로 구현한다.

분석 로직:
1. `tt_noc_pkg.sv`에서 라우팅 알고리즘 enum 추출 (`DIM_ORDER`, `TENDRIL`, `DYNAMIC`)
2. `noc_header_address_t` 구조체에서 flit 헤더 필드 추출 (x_dest, y_dest, endpoint_id, flit_type, dynamic_carried_list)
3. AXI 주소 가스켓(56-bit) 구조 추출 (`target_index`, `endpoint_id`, `tlb_index`, `address`)
4. `tt_noc_sec_fence_edc_wrapper` 모듈에서 보안 펜스 메커니즘 식별 (SMN 그룹 기반 접근 제어)

출력 형식:
```json
{
    "pipeline_id": "tt_20260221",
    "analysis_type": "noc_protocol",
    "routing_algorithms": [
        {"name": "DIM_ORDER", "enum_value": 0, "parameters": {}},
        {"name": "TENDRIL", "enum_value": 1, "parameters": {}},
        {"name": "DYNAMIC", "enum_value": 2, "parameters": {"EnableDynamicRouting": "1"}}
    ],
    "flit_structure": {
        "header_fields": ["x_dest", "y_dest", "endpoint_id", "flit_type", "dynamic_carried_list"],
        "total_bits": 64
    },
    "axi_address_gasket": {
        "total_bits": 56,
        "fields": ["target_index", "endpoint_id", "tlb_index", "address"]
    },
    "security_fence": {
        "module": "tt_noc_sec_fence_edc_wrapper",
        "mechanism": "smn_group_access_control"
    }
}
```

### 12. Overlay Deep Analyzer

Overlay(RISC-V 서브시스템)의 내부 구조를 심화 분석한다. `analysis_handler.py`에 `handle_overlay_deep_analysis(event)` 핸들러로 구현한다.

분석 로직:
1. `tt_overlay_pkg.sv`에서 CPU 클러스터 파라미터 추출 (NUM_CLUSTER_CPUS, NUM_INTERRUPTS, RESET_VECTOR_WIDTH)
2. Overlay 서브모듈 역할 식별: CPU 클러스터(`tt_overlay_cpu_wrapper`), iDMA(`tt_idma_wrapper`), ROCC(`tt_rocc_accel`), LLK 카운터(`tt_overlay_tile_counters`), SMN(`tt_overlay_smn_wrapper`), FDS(`tt_fds_wrapper`)
3. `tt_overlay_memory_wrapper` 모듈에서 L1 캐시 파라미터 추출 (뱅크 수, 뱅크 폭, ECC 타입, SRAM 타입)
4. `tt_overlay_reg_xbar_slave_decode` 구조에서 APB 슬레이브 목록과 주소 맵 추출

출력 형식:
```json
{
    "pipeline_id": "tt_20260221",
    "analysis_type": "overlay_deep",
    "cpu_cluster": {
        "NUM_CLUSTER_CPUS": 4,
        "NUM_INTERRUPTS": 32,
        "RESET_VECTOR_WIDTH": 32
    },
    "submodule_roles": {
        "tt_overlay_cpu_wrapper": "cpu_cluster",
        "tt_idma_wrapper": "idma",
        "tt_rocc_accel": "rocc_accelerator",
        "tt_overlay_tile_counters": "llk_counter",
        "tt_overlay_smn_wrapper": "smn",
        "tt_fds_wrapper": "fds"
    },
    "l1_cache": {
        "num_banks": 8,
        "bank_width": 64,
        "ecc_type": "SECDED",
        "sram_type": "SP_SRAM"
    },
    "apb_slaves": [
        {"name": "slave_0", "base_address": "0x0000", "size": "0x1000"},
        {"name": "slave_1", "base_address": "0x1000", "size": "0x1000"}
    ]
}
```

## 데이터 모델

### 13. SRAM Inventory Extractor (신규 컴포넌트)

계층 트리에서 메모리 인스턴스(SRAM, register file, ROM)를 식별하여 인벤토리를 생성한다. `analysis_handler.py`에 `handle_sram_inventory(event)` 핸들러로 구현한다.

### 14. MCP Bridge search_rtl 파라미터 패스스루 (v3 R2 이슈 #1, #5)

온프레미스 MCP Bridge `server.js`의 search_rtl 도구가 모든 검색 파라미터를 Lambda API에 정확히 전달하도록 수정한다.

현재 문제:
- Lambda `_search_rtl()`은 `max_results`를 event에서 읽어 기본값 20으로 처리
- 온프레미스 MCP Bridge `server.js`의 search_rtl 도구가 `max_results: 5`를 하드코딩하여 Lambda에 전달
- `analysis_type`, `pipeline_id`, `topic` 파라미터도 Lambda에 전달되지 않음

수정 방안:
```javascript
// 온프레미스 server.js의 search_rtl 도구 수정
mcp.tool(
    "search_rtl",
    "RTL OpenSearch 인덱스를 검색합니다.",
    {
        query: z.string().describe("검색 질의"),
        max_results: z.number().optional().default(20).describe("최대 결과 수 (기본값 20)"),
        analysis_type: z.string().optional().describe("분석 유형 필터 (module_parse, hierarchy, claim, hdd_section 등)"),
        pipeline_id: z.string().optional().describe("파이프라인 ID 필터 (예: tt_20260221)"),
        topic: z.string().optional().describe("토픽 필터 (예: NoC, EDC, Overlay)")
    },
    async (args, extra) => {
        const body = { action: "search", query: args.query, max_results: args.max_results };
        if (args.analysis_type) body.analysis_type = args.analysis_type;
        if (args.pipeline_id) body.pipeline_id = args.pipeline_id;
        if (args.topic) body.topic = args.topic;
        // Lambda invoke ...
    }
);
```

### 15. Claim 귀속 정확성 개선 (v3 R2 이슈 #2)

Claim 생성 시 토픽별 대표 모듈이 다양하게 포함되도록 `claim_generator.py`와 `analysis_handler.py`를 수정한다.

현재 문제:
- HDD 86건이 전부 `trinity_noc2axi_router_ne_opt_FBLC` 단일 모듈에 편중
- 5개 토픽(EDC/NoC/Overlay/DFX/Dispatch) 전부 같은 모듈
- claim이 `_reg_inner`/`_wrap` 패턴의 레지스터 모듈에서만 생성됨

수정 방안:

1. **레지스터 래퍼 필터링**: claim 생성 대상에서 `_reg_inner`, `_wrap` 패턴 모듈을 제외하고 데이터패스 모듈을 우선 포함
2. **토픽-모듈 교차 검증**: `classify_topic()` 결과와 hierarchy 위치를 교차 검증하여 토픽 불일치 모듈 제외
3. **다양성 검증**: 토픽별 claim의 module_name 분포를 검사하여 단일 모듈 80% 이상 편중 시 경고 + 추가 생성

```python
# claim_generator.py 수정
REGISTER_WRAPPER_PATTERNS = ["_reg_inner", "_wrap", "_reg_top"]

def _filter_claim_targets(modules: list[dict], topic: str) -> list[dict]:
    """Claim 대상 모듈 필터링: 레지스터 래퍼 제외, 토픽 일치 모듈 우선."""
    datapath_modules = []
    register_modules = []
    for m in modules:
        name = m.get("module_name", "")
        is_register = any(pat in name for pat in REGISTER_WRAPPER_PATTERNS)
        if is_register:
            register_modules.append(m)
        else:
            datapath_modules.append(m)
    # 데이터패스 모듈이 3개 미만이면 레지스터 모듈도 포함
    if len(datapath_modules) < 3:
        datapath_modules.extend(register_modules)
    return datapath_modules

def _validate_claim_diversity(claims: list[dict], topic: str) -> bool:
    """Claim 다양성 검증: 단일 모듈 80% 이상 편중 시 False."""
    if not claims:
        return True
    module_counts: dict[str, int] = {}
    for c in claims:
        mn = c.get("module_name", "")
        module_counts[mn] = module_counts.get(mn, 0) + 1
    max_count = max(module_counts.values())
    return max_count / len(claims) < 0.8
```

`analysis_handler.py`의 `handle_hdd_generation()` 수정:
```python
# HDD 생성 시 claim의 module_name이 해당 토픽의 실제 모듈 계층에 속하는지 검증
def _filter_claims_by_topic_hierarchy(claims, topic, hierarchy_modules):
    """토픽 계층에 속하지 않는 claim 제외."""
    topic_module_set = {m["module_name"] for m in hierarchy_modules if topic.lower() in [t.lower() for t in m.get("topics", [])]}
    return [c for c in claims if c.get("module_name", "") in topic_module_set]
```

### 16. 토픽 분류 확장 — Power, Memory 토픽 추가 (v3 R2 이슈 #3)

`topic_classifier.py`의 `TOPIC_RULES`에 Power, Memory 토픽을 추가하고, NIU 토픽에 `tt_noc2axi_*` 접두사를 추가한다.

현재 문제:
- NIU 토픽 0건 (NoC에 포함됨) — `tt_noc2axi_*` 모듈이 NIU가 아닌 NoC로 분류
- Power 토픽 없음 — PRTN 데이지 체인, ISO_EN 관련 모듈 미분류
- Memory 토픽 없음 — SFR 관련 모듈 미분류

수정 방안:
```python
TOPIC_RULES: dict[str, dict[str, list[str]]] = {
    # ... 기존 토픽 유지 ...
    "NIU":         {"path": [r"[/\\]niu[/\\]"],
                    "prefix": ["tt_niu_", "niu_", "tt_noc2axi_"]},  # tt_noc2axi_ 추가
    "Power":       {"path": [r"[/\\]power[/\\]", r"[/\\]prtn[/\\]"],
                    "prefix": ["tt_prtn_", "prtn_", "iso_en_"]},
    "Memory":      {"path": [r"[/\\]memory[/\\]", r"[/\\]sram[/\\]"],
                    "prefix": ["sfr_", "tt_mem_", "mem_"]},
}
```

주의: `tt_noc2axi_*` 접두사를 NIU에 추가하면 기존 NoC 분류와 중복 매칭될 수 있다. 복수 토픽 매칭은 기존 설계대로 허용하되, NIU가 우선 토픽으로 표시되도록 한다.

### 17. 포트 비트폭 추출 (v3 R2 이슈 #4)

`handler.py`의 `parse_rtl_to_ast()` 함수에서 포트 선언의 비트폭 정보를 추출하도록 정규식을 확장한다.

현재 문제:
- `input [SizeX-1:0] i_ai_clk` → 현재 `input i_ai_clk`으로만 추출 (비트폭 누락)
- 정규식 `\b(input|output|inout)\s+(?:wire|reg|logic)?\s*(?:\[[\w\s:\-]+\])?\s*(\w+)`에서 비트폭 캡처 그룹이 없음

수정 방안:
```python
# handler.py parse_rtl_to_ast() 내 포트 패턴 수정
port_pattern = re.compile(
    r"\b(input|output|inout)\s+(?:wire|reg|logic)?\s*"
    r"((?:\[[^\]]+\]\s*)*)"   # 비트폭 캡처 (다차원 지원: [A:B][C:D])
    r"(\w+)",
    re.MULTILINE
)
for m in port_pattern.finditer(content):
    direction = m.group(1)
    bit_width = m.group(2).strip()  # "[SizeX-1:0]" 또는 "[3:0][7:0]" 또는 ""
    name = m.group(3)
    if bit_width:
        ports.append(f"{direction} {bit_width} {name}")
    else:
        ports.append(f"{direction} {name}")
```

출력 예시:
- `input [SizeX-1:0] i_ai_clk` (비트폭 있음)
- `input i_rst_n` (비트폭 없음, 1비트)
- `output [3:0][7:0] data` (다차원 배열)

분석 로직:
1. OpenSearch에서 해당 Pipeline_ID의 hierarchy 문서를 조회
2. 각 계층 노드의 `memory_instances` 필드 및 `instance_list`에서 메모리 패턴 매칭
3. 매칭 패턴: 모듈명/인스턴스명에 `sram`, `ram`, `rf_`, `reg_file`, `rom`, `memory`, `mem_` 키워드 포함
4. 식별된 메모리 인스턴스에 대해 파라미터(depth, width, ECC 유무) 추출 시도
5. 파라미터 추출 불가 시 `"unknown"` 기본값 설정
6. 결과를 OpenSearch에 `analysis_type=sram_inventory` 문서로 인덱싱

메모리 패턴 매칭 규칙:
```python
MEMORY_PATTERNS = [
    "sram", "ram", "rf_", "reg_file", "rom", "memory", "mem_",
]

def is_memory_instance(instance_name: str, module_name: str) -> bool:
    """인스턴스명 또는 모듈명에 메모리 키워드가 포함되면 True."""
    combined = f"{instance_name}_{module_name}".lower()
    return any(pat in combined for pat in MEMORY_PATTERNS)
```

출력 형식:
```json
{
    "pipeline_id": "tt_20260221",
    "analysis_type": "sram_inventory",
    "memory_instances": [
        {
            "instance_name": "u_sram_256x64",
            "memory_type": "SRAM",
            "parent_module": "tt_dispatch_top",
            "hierarchy_path": "trinity.gen_dispatch_e.tt_dispatch_top_inst_east.u_sram_256x64",
            "parameters": {
                "depth": "256",
                "width": "64",
                "ecc": "unknown"
            }
        },
        {
            "instance_name": "u_rf_32x128",
            "memory_type": "RF",
            "parent_module": "tt_overlay_memory_wrapper",
            "hierarchy_path": "trinity.overlay_inst.tt_overlay_memory_wrapper.u_rf_32x128",
            "parameters": {
                "depth": "32",
                "width": "128",
                "ecc": "SECDED"
            }
        }
    ],
    "summary": {
        "total_count": 2228,
        "by_type": {"SRAM": 1800, "RF": 350, "ROM": 78},
        "by_subsystem": {"Tensix": 1200, "Overlay": 400, "NoC": 300, "EDC": 200, "Other": 128}
    }
}
```

S3 저장 경로:
- `rtl-parsed/sram_inventory/{pipeline_id}/sram_inventory.json`

### OpenSearch 인덱스 스키마 확장

기존 `rtl-knowledge-base-index` 인덱스에 다음 필드를 추가한다. 기존 8,168건의 문서와 호환성을 유지하면서 새 필드를 추가하는 방식이다.

```json
{
    "mappings": {
        "properties": {
            "embedding":          {"type": "knn_vector", "dimension": 1024},
            "module_name":        {"type": "keyword"},
            "parent_module":      {"type": "keyword"},
            "port_list":          {"type": "text"},
            "parameter_list":     {"type": "text"},
            "instance_list":      {"type": "text"},
            "file_path":          {"type": "keyword"},
            "parsed_summary":     {"type": "text"},

            "pipeline_id":        {"type": "keyword"},
            "chip_type":          {"type": "keyword"},
            "snapshot_date":      {"type": "keyword"},
            "analysis_type":      {"type": "keyword"},

            "hierarchy_path":     {"type": "keyword"},
            "hierarchy_depth":    {"type": "integer"},
            "children_modules":   {"type": "keyword"},
            "clock_signals":      {"type": "keyword"},
            "reset_signals":      {"type": "keyword"},
            "memory_instances":   {"type": "keyword"},

            "clock_domains":      {"type": "nested", "properties": {
                "domain":         {"type": "keyword"},
                "signals":        {"type": "keyword"}
            }},
            "is_cdc_boundary":    {"type": "boolean"},
            "cdc_pairs":          {"type": "keyword"},

            "dataflow_connections": {"type": "nested", "properties": {
                "parent_signal":  {"type": "keyword"},
                "child_module":   {"type": "keyword"},
                "child_port":     {"type": "keyword"},
                "direction":      {"type": "keyword"},
                "bit_width":      {"type": "integer"},
                "width_mismatch": {"type": "boolean"}
            }},

            "topic":              {"type": "keyword"},
            "topics":             {"type": "keyword"},

            "claim_id":           {"type": "keyword"},
            "claim_type":         {"type": "keyword"},
            "claim_text":         {"type": "text"},
            "confidence_score":   {"type": "float"},
            "source_files":       {"type": "keyword"},

            "hdd_section_title":  {"type": "keyword"},
            "hdd_section_type":   {"type": "keyword"},
            "hdd_content":        {"type": "text"},
            "hdd_metadata":       {"type": "object", "properties": {
                "generation_date":    {"type": "date"},
                "pipeline_version":   {"type": "keyword"},
                "source_rtl_files":   {"type": "keyword"}
            }},

            "created_at":         {"type": "date"},
            "updated_at":         {"type": "date"},
            "previous_version_at": {"type": "date"},

            "sram_inventory":     {"type": "nested", "properties": {
                "instance_name":  {"type": "keyword"},
                "memory_type":    {"type": "keyword"},
                "parent_module":  {"type": "keyword"},
                "hierarchy_path": {"type": "keyword"},
                "depth":          {"type": "keyword"},
                "width":          {"type": "keyword"},
                "ecc":            {"type": "keyword"}
            }},
            "sram_summary":       {"type": "object", "properties": {
                "total_count":    {"type": "integer"},
                "by_type":        {"type": "object"},
                "by_subsystem":   {"type": "object"}
            }}
        }
    }
}
```

`analysis_type` 필드 값:
- `module_parse`: 기존 RTL Parser Lambda 파싱 결과
- `hierarchy`: 계층 트리 노드
- `clock_domain`: 클럭 도메인 분석 결과
- `dataflow`: 데이터 흐름 연결 정보
- `topic`: 토픽 분류 결과
- `claim`: LLM 생성 claim
- `hdd_section`: HDD 문서 섹션
- `variant_delta`: variant 차이 분석 결과
- `chip_config`: 패키지 파라미터 및 칩 구성 정보
- `edc_topology`: EDC 링 토폴로지 및 프로토콜 분석 결과
- `noc_protocol`: NoC 라우팅 알고리즘 및 패킷 구조 분석 결과
- `overlay_deep`: Overlay 내부 구조 심화 분석 결과
- `sram_inventory`: SRAM/RF/ROM 메모리 인스턴스 인벤토리

### DynamoDB 테이블 스키마

기존 `rag-extraction-tasks` 테이블을 분석 상태 추적에 재사용한다. 기존 `task_id` (S) 파티션 키 구조를 유지하면서 분석 파이프라인 상태를 추적한다.

분석 상태 추적 아이템:
```json
{
    "task_id": "analysis_tt_20260221_hierarchy_extraction",
    "pipeline_id": "tt_20260221",
    "stage": "hierarchy_extraction",
    "status": "completed",
    "started_at": "2026-02-21T10:05:00Z",
    "completed_at": "2026-02-21T10:15:00Z",
    "retry_count": 0,
    "modules_processed": 9465,
    "modules_total": 9465,
    "error_message": null,
    "ttl": 1740000000
}
```

기존 `bos-ai-claim-db` 테이블에 Pipeline_ID 기반 격리를 추가한다. 기존 스키마(claim_id PK, version SK)를 유지하면서 `pipeline_id` 속성을 추가한다.

Claim DB 아이템 (확장):
```json
{
    "claim_id": "clm_tt_20260221_noc_001",
    "version": 1,
    "pipeline_id": "tt_20260221",
    "topic": "NoC",
    "topic_variant": "NoC_tt_20260221",
    "status": "auto_generated",
    "claim_type": "connectivity",
    "claim_text": "tt_noc_router는 4개의 방향 포트를 통해 메시 토폴로지를 구성한다",
    "confidence_score": 0.95,
    "source_document_id": "rtl-sources/tt_20260221/noc/tt_noc_router.sv",
    "source_files": ["rtl-sources/tt_20260221/noc/tt_noc_router.sv"],
    "extraction_date": "2026-02-21",
    "last_verified_at": "2026-02-21T10:30:00Z",
    "claim_family_id": "fam_noc_router_connectivity"
}
```

설계 결정: `topic_variant` GSI를 활용하여 `topic_variant = "NoC_tt_20260221"` 형태로 Pipeline_ID별 Claim을 격리 조회한다. 기존 GSI 구조를 변경하지 않고 `topic_variant` 값에 Pipeline_ID를 인코딩하는 방식이다.

### Pipeline_ID 기반 데이터 격리 설계

모든 데이터 저장소에서 Pipeline_ID를 기준으로 논리적 격리를 수행한다:

| 저장소 | 격리 방식 | 예시 |
|--------|-----------|------|
| S3 | 디렉토리 프리픽스 | `rtl-parsed/hierarchy/tt_20260221/` |
| OpenSearch | `pipeline_id` 필드 필터 | `{"term": {"pipeline_id": "tt_20260221"}}` |
| DynamoDB (분석 상태) | `task_id` 프리픽스 | `analysis_tt_20260221_*` |
| DynamoDB (Claim DB) | `topic_variant` GSI | `NoC_tt_20260221` |
| Step Functions | 실행 이름 | `analysis-tt_20260221-20260221T100000` |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Pipeline_ID 파싱 정확성

*For any* 유효한 S3 키 `rtl-sources/{chip_type}_{date}/...` 형식에 대해, Pipeline_ID 추출 함수는 정확한 `chip_type`과 `date`를 반환하고, `{chip_type}_{date}` 형식의 Pipeline_ID를 생성해야 한다.

**Validates: Requirements 1.6, 10.1**

### Property 2: 계층 트리 라운드트립

*For any* 유효한 RTL 모듈 세트와 그 인스턴스 목록에 대해, 계층 트리를 구축한 후 해당 트리에서 각 parent-child 관계를 역으로 추출하면 원본 인스턴스화 관계와 동일한 결과를 산출해야 한다.

**Validates: Requirements 2.1, 2.6**

### Property 3: 계층 노드 완전성

*For any* 생성된 계층 트리의 모든 노드에 대해, 해당 노드는 module_name, instance_name, hierarchy_path, clock_signals, reset_signals 필드를 포함해야 한다.

**Validates: Requirements 2.2, 2.3**

### Property 4: 계층 직렬화 라운드트립

*For any* 유효한 계층 트리에 대해, JSON으로 직렬화한 후 역직렬화하면 원본 트리와 동일한 구조를 산출해야 하며, CSV로 직렬화한 결과는 JSON과 동일한 모듈 집합을 포함해야 한다.

**Validates: Requirements 2.5**

### Property 5: 클럭 추출 및 도메인 분류

*For any* RTL 소스 코드에서 `always_ff @(posedge clock)` 또는 `always @(posedge clock)` 패턴이 포함된 경우, Clock_Domain_Analyzer는 해당 클럭 신호를 추출하고, 표준 패턴과 일치하면 올바른 도메인 그룹으로 분류하며, 일치하지 않으면 `unclassified_clock`으로 분류해야 한다.

**Validates: Requirements 3.1, 3.2, 3.5**

### Property 6: CDC 경계 감지

*For any* 모듈에 대해, 해당 모듈 내에서 2개 이상의 서로 다른 클럭 도메인이 감지되면 `is_cdc_boundary`가 true로 설정되어야 하고, 1개 이하이면 false로 설정되어야 한다.

**Validates: Requirements 3.3**

### Property 7: 데이터 흐름 연결 추출 완전성

*For any* RTL 모듈의 인스턴스 포트 매핑 `.port_name(signal_name)` 패턴에 대해, Dataflow_Tracker는 해당 연결을 추출하고, 각 연결에 parent_signal, child_module, child_port, direction, bit_width 필드를 포함해야 한다.

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 8: 비트 폭 불일치 감지

*For any* 포트 연결에서 상위 모듈 신호의 비트 폭과 하위 모듈 포트의 비트 폭이 다른 경우, `width_mismatch` 플래그가 true로 설정되어야 하고, 동일한 경우 false로 설정되어야 한다.

**Validates: Requirements 4.5**

### Property 9: 토픽 분류 정확성

*For any* RTL 모듈에 대해, 파일 경로 또는 모듈명이 사전 정의된 토픽 패턴과 일치하면 해당 토픽이 할당되어야 하고, 복수 패턴과 일치하면 모든 매칭 토픽이 할당되어야 하며, 어떤 패턴과도 일치하지 않으면 `unclassified`로 분류되어야 한다.

**Validates: Requirements 5.1, 5.3, 5.4**

### Property 10: Claim 스키마 유효성

*For any* 생성된 claim에 대해, claim_id, module_name, topic, claim_type, claim_text, confidence_score, source_files 필드가 모두 존재해야 하며, confidence_score는 0.0 이상 1.0 이하여야 하고, claim_type은 structural, behavioral, connectivity, timing 중 하나여야 한다.

**Validates: Requirements 6.2**

### Property 11: LLM 입력 토큰 분할

*For any* 모듈 그룹에 대해, Claim_Generator의 토큰 분할 함수는 각 분할 청크의 토큰 수가 100,000 이하가 되도록 분할해야 하며, 모든 모듈이 정확히 하나의 청크에 포함되어야 한다.

**Validates: Requirements 6.4**

### Property 12: HDD 섹션 완전성

*For any* 생성된 HDD 섹션에 대해, 해당 섹션은 필수 구조(개요, 모듈 계층, 기능 상세, 클럭/리셋 구조, 주요 파라미터, 검증 체크리스트)를 포함해야 하며, 메타데이터(source_rtl_files, generation_date, pipeline_version, pipeline_id)가 존재해야 한다.

**Validates: Requirements 7.2, 7.5, 10.6**

### Property 13: HDD 참조 무결성

*For any* 생성된 HDD 섹션에 대해, 해당 섹션에서 참조하는 모듈명은 계층 트리에 존재하는 모듈명의 부분집합이어야 한다.

**Validates: Requirements 7.6**

### Property 14: 검색 쿼리 구성 정확성

*For any* 검색 파라미터 조합(topic, clock_domain, hierarchy_path, pipeline_id)에 대해, 쿼리 빌더는 해당 필터 조건을 모두 포함하는 유효한 OpenSearch 쿼리를 생성해야 하며, 빈 파라미터는 쿼리에서 제외되어야 한다.

**Validates: Requirements 8.3**

### Property 15: Variant Delta 추출 정확성

*For any* 베이스라인과 variant 모듈 세트 쌍에 대해, delta 추출 함수는 모듈 추가/삭제, 파라미터 값 변경, 인스턴스 추가/삭제를 정확히 식별해야 하며, 변경되지 않은 항목은 delta에 포함되지 않아야 한다.

**Validates: Requirements 9.2**

### Property 16: Pipeline_ID 격리

*For any* 두 개의 서로 다른 Pipeline_ID에 대해, 하나의 Pipeline_ID로 필터링한 쿼리 결과에는 다른 Pipeline_ID의 문서가 포함되지 않아야 한다.

**Validates: Requirements 1.7, 10.2, 10.5**

### Property 17: Terraform 리소스 태깅

*For any* Terraform으로 생성되는 AWS 리소스에 대해, Project, Environment, ManagedBy 태그가 포함되어야 한다.

**Validates: Requirements 11.6**

### Property 18: 패키지 파라미터 추출 라운드트립

*For any* 유효한 SystemVerilog 패키지 파일(`*_pkg.sv`)에서 `localparam`, `parameter`, `typedef enum` 선언이 포함된 경우, 추출 함수는 모든 선언을 정확히 추출해야 하며, 추출된 파라미터 이름과 값을 원본 소스 코드에서 역으로 검색하면 일치하는 선언을 찾을 수 있어야 한다.

**Validates: Requirements 12.1, 12.3, 13.3, 14.1, 15.1, 15.3**

### Property 19: 구조체 필드 추출 완전성

*For any* 유효한 SystemVerilog 구조체(`typedef struct`) 정의에 대해, 필드 추출 함수는 모든 필드명과 비트 폭을 추출해야 하며, 추출된 필드 수는 원본 구조체의 필드 수와 동일해야 한다.

**Validates: Requirements 14.2, 14.3**

### Property 20: EDC 토폴로지 분석 정확성

*For any* 유효한 EDC 노드 인스턴스화 관계 세트에 대해, 링 토폴로지 재구성 함수는 모든 노드를 포함하는 연결 경로를 생성해야 하며, 재구성된 토폴로지에서 각 노드 간 연결을 역으로 추적하면 원본 인스턴스화 관계와 동일한 결과를 산출해야 한다. 또한 노드 ID 디코딩 테이블의 각 엔트리는 고유한 (part, subp, inst) 조합을 가져야 한다.

**Validates: Requirements 13.1, 13.2, 13.4**

### Property 21: Overlay 구조 분석 완전성

*For any* 유효한 Overlay 모듈 세트에 대해, 서브모듈 역할 식별 함수는 알려진 서브모듈 패턴(`tt_overlay_cpu_wrapper`, `tt_idma_wrapper`, `tt_rocc_accel`, `tt_overlay_tile_counters`, `tt_overlay_smn_wrapper`, `tt_fds_wrapper`)과 일치하는 모든 모듈에 올바른 역할을 할당해야 하며, APB 슬레이브 목록 추출 함수는 크로스바 디코드 모듈에서 모든 슬레이브 엔트리를 추출해야 한다.

**Validates: Requirements 15.2, 15.4**

### Property 22: 패키지 파일 선별 필터링

*For any* S3 파일 키 목록에 대해, chip_config 분석의 파일 필터 함수는 `*_pkg.sv` 패턴과 일치하는 파일만 선택해야 하며, 패턴과 일치하지 않는 파일은 선택하지 않아야 한다.

**Validates: Requirements 12.6, 12.8**

### Property 23: 메모리 인스턴스 식별 및 스키마 완전성

*For any* 계층 트리의 인스턴스 목록에 대해, SRAM Inventory Extractor의 메모리 패턴 매칭 함수는 `sram`, `ram`, `rf_`, `reg_file`, `rom`, `memory`, `mem_` 키워드를 포함하는 인스턴스만 메모리로 식별해야 하며, 식별된 각 메모리 인스턴스는 instance_name, memory_type, parent_module, hierarchy_path, parameters(depth, width, ecc) 필드를 모두 포함해야 한다.

**Validates: Requirements 16.1, 16.2, 16.5**

### Property 24: 메모리 파라미터 기본값 처리

*For any* 메모리 인스턴스에 대해, depth 또는 width 파라미터를 RTL에서 추출할 수 없는 경우 해당 필드는 `"unknown"` 값으로 설정되어야 하며, 필드 자체가 누락되어서는 안 된다.

**Validates: Requirements 16.6**

### Property 25: MCP Bridge 파라미터 패스스루

*For any* MCP Bridge search_rtl 도구 호출에 대해, 사용자가 제공한 max_results, analysis_type, pipeline_id, topic 파라미터는 Lambda API 요청 본문에 그대로 전달되어야 하며, 제공되지 않은 선택적 파라미터는 요청에서 생략되어야 한다.

**Validates: Requirements 17.1, 17.2, 17.3, 17.5**

### Property 26: Claim 귀속 다양성

*For any* 토픽별 claim 생성 결과에 대해, 해당 토픽의 claim이 3개 이상의 서로 다른 모듈에서 생성되어야 하며, 단일 모듈에 전체 claim의 80% 이상이 편중되어서는 안 된다.

**Validates: Requirements 18.1, 18.3, 18.4**

### Property 27: 토픽 분류 확장 완전성

*For any* RTL 모듈에 대해, Topic_Classifier는 최소 14개 토픽 카테고리(NoC, FPU, SFPU, TDMA, Overlay, EDC, Dispatch, L1_Cache, Clock_Reset, DFX, NIU, SMN, Power, Memory)를 지원해야 하며, `tt_noc2axi_*` 패턴의 모듈은 NIU 토픽으로 분류되어야 한다.

**Validates: Requirements 19.1, 19.4, 19.5**

### Property 28: 포트 비트폭 추출 정확성

*For any* RTL 포트 선언에서 `[MSB:LSB]` 형식의 비트폭이 포함된 경우, RTL_Parser_Lambda는 해당 비트폭 정보를 추출하여 `direction [bit_width] port_name` 형식으로 port_list에 포함해야 하며, 비트폭이 없는 포트는 비트폭 정보 없이 `direction port_name` 형식으로 저장되어야 한다.

**Validates: Requirements 20.1, 20.3, 20.4**

## 에러 처리

### 에러 처리 전략

| 컴포넌트 | 에러 유형 | 처리 방식 | 재시도 |
|----------|-----------|-----------|--------|
| RTL Parser Lambda | S3 GetObject 실패 | DynamoDB 에러 테이블에 기록, CloudWatch 경고 | Lambda 자체 재시도 (최대 2회) |
| RTL Parser Lambda | OpenSearch 인덱싱 실패 | 에러 로그 기록, 파싱 결과는 S3에 저장 | 1회 재시도 |
| RTL Parser Lambda | Titan Embeddings 호출 실패 | 임베딩 없이 인덱싱 진행 (텍스트 검색만 가능) | 1회 재시도 |
| RTL Parser Lambda | Pipeline_ID 파싱 실패 | `unknown_unknown` 기본값 사용, 경고 로그 | 재시도 없음 |
| Analysis Orchestrator | 분석 단계 실패 | Step Functions 재시도 (최대 2회), 실패 시 건너뛰기 | 2회 |
| Analysis Orchestrator | Step Functions 실행 타임아웃 | DynamoDB에 timeout 상태 기록, CloudWatch 알람 | 재시도 없음 |
| Hierarchy Extractor | OpenSearch 쿼리 실패 | 재시도 후 실패 시 빈 계층 트리 반환 | 2회 |
| Hierarchy Extractor | 순환 참조 감지 | 순환 경로를 로그에 기록하고 해당 브랜치 절단 | 재시도 없음 |
| Clock Domain Analyzer | S3 파일 읽기 실패 | 해당 모듈 건너뛰기, 에러 카운트 증가 | 1회 재시도 |
| Dataflow Tracker | 포트 매핑 파싱 실패 | 해당 연결 건너뛰기, 경고 로그 | 재시도 없음 |
| Claim Generator | Bedrock Claude 호출 실패 | 해당 모듈 그룹 건너뛰기, 에러 기록 | 1회 재시도 |
| Claim Generator | LLM 응답 파싱 실패 | 원본 응답을 S3에 저장, 에러 기록 | 재시도 없음 |
| Claim Generator | 토큰 제한 초과 | 모듈 그룹을 더 작은 단위로 분할하여 재호출 | 자동 분할 |
| HDD Section Generator | Bedrock Claude 호출 실패 | 해당 토픽 HDD 건너뛰기, 에러 기록 | 1회 재시도 |
| HDD Section Generator | S3 저장 실패 | 재시도 후 실패 시 에러 기록 | 2회 재시도 |
| Package Parameter Extractor | 정규식 파싱 실패 | 해당 선언 건너뛰기, 경고 로그 | 재시도 없음 |
| EDC Topology Analyzer | 토폴로지 재구성 실패 | 부분 토폴로지 반환, 에러 기록 | 1회 재시도 |
| EDC Topology Analyzer | 노드 ID 디코딩 실패 | 해당 노드 건너뛰기, 경고 로그 | 재시도 없음 |
| NoC Protocol Analyzer | 구조체 파싱 실패 | 해당 구조체 건너뛰기, 경고 로그 | 재시도 없음 |
| NoC Protocol Analyzer | 보안 펜스 식별 실패 | 빈 결과 반환, 경고 로그 | 재시도 없음 |
| Overlay Deep Analyzer | 서브모듈 역할 식별 실패 | 미식별 모듈을 "unknown" 역할로 태깅 | 재시도 없음 |
| Overlay Deep Analyzer | APB 슬레이브 추출 실패 | 빈 슬레이브 목록 반환, 경고 로그 | 재시도 없음 |
| SRAM Inventory Extractor | 메모리 패턴 매칭 실패 | 해당 인스턴스 건너뛰기, 경고 로그 | 재시도 없음 |
| SRAM Inventory Extractor | 파라미터 추출 실패 | depth/width를 "unknown"으로 설정, 경고 로그 | 재시도 없음 |
| Package Parameter Extractor | 300초 타임아웃 임박 | 미처리 토픽을 별도 Lambda로 분할 실행 | 자동 분할 |
| HDD Section Generator | 심화 분석 결과 조회 실패 | 심화 데이터 없이 기본 HDD 생성 진행 | 1회 재시도 |
| MCP Bridge | search_rtl Lambda invoke 실패 | MCP isError 응답 반환 | 재시도 없음 |
| MCP Bridge | search_rtl Lambda invoke 타임아웃(30초) | MCP isError 응답 반환 | 재시도 없음 |
| Claim Generator | 단일 모듈 편중 감지 (80% 이상) | 경고 로그 + 다른 모듈에서 추가 claim 생성 시도 | 1회 재시도 |
| Claim Generator | 토픽-모듈 교차 검증 불일치 | 불일치 claim 제외, 경고 로그 | 재시도 없음 |
| RTL Parser Lambda | 포트 비트폭 정규식 파싱 실패 | 비트폭 없이 포트명만 추출, 경고 로그 | 재시도 없음 |

### 에러 전파 정책

- 개별 파일 파싱 실패는 전체 파이프라인을 중단하지 않음
- 개별 분석 단계 실패는 후속 단계 실행을 차단하지 않음 (건너뛰기)
- LLM 호출 실패는 해당 모듈 그룹만 건너뛰고 나머지 그룹은 계속 처리
- 모든 에러는 DynamoDB `rag-extraction-tasks` 테이블과 CloudWatch Logs에 기록
- 에러율이 전체 모듈의 10% 초과 시 CloudWatch 알람 발생

### Lambda 실행 시간 관리

RTL Parser Lambda의 300초 타임아웃 제약을 준수하기 위한 작업 분할 전략:
- 개별 파일 파싱: 파일당 평균 0.03초, 충분한 여유
- Hierarchy Extractor: OpenSearch 스크롤 쿼리로 배치 처리 (1,000건씩)
- Clock Domain Analyzer: S3 파일을 배치로 읽기 (100개씩)
- Claim Generator: 토픽별 모듈 그룹 단위로 LLM 호출 (그룹당 60초 타임아웃)
- 각 분석 단계는 별도 Lambda 호출로 분리하여 300초 제한을 개별 적용
- chip_config 분석: `*_pkg.sv` 파일만 선별적으로 읽어 처리 시간 단축. 타임아웃 임박 시 토픽별(noc_pkg, edc_pkg, overlay_pkg 등) 분할 실행
- SRAM Inventory: 계층 트리 기반 패턴 매칭으로 S3 파일 읽기 불필요, 빠른 처리

## 테스팅 전략

### 이중 테스팅 접근법

이 프로젝트는 단위 테스트와 속성 기반 테스트(Property-Based Testing)를 병행한다.

- 단위 테스트: 구체적인 예시, 엣지 케이스, 에러 조건 검증
- 속성 기반 테스트: 모든 유효한 입력에 대해 보편적 속성 검증
- 통합 테스트: AWS 인프라 연동 검증

### 속성 기반 테스트 (Property-Based Testing)

라이브러리: Go `gopter` (기존 `tests/properties/` 디렉토리의 패턴을 따름)

각 속성 테스트는 최소 100회 반복 실행하며, 설계 문서의 Property를 참조하는 태그를 포함한다.

태그 형식: `Feature: rtl-auto-analysis-pipeline, Property {number}: {property_text}`

테스트 대상 속성 (순수 로직 함수):

| Property | 테스트 대상 함수 | 생성기 | 검증 조건 |
|----------|-----------------|--------|-----------|
| 1 | `extract_pipeline_id(s3_key)` | 랜덤 chip_type + date 조합의 S3 키 | 추출된 chip_type, date가 원본과 일치 |
| 2 | `build_hierarchy(modules)` | 랜덤 모듈 세트 + 인스턴스 관계 | 트리에서 역추출한 관계 = 원본 관계 |
| 3 | `build_hierarchy(modules)` | 랜덤 모듈 세트 | 모든 노드에 필수 필드 존재 |
| 4 | `serialize_hierarchy(tree)` | 랜덤 계층 트리 | JSON 라운드트립 동일성, CSV/JSON 모듈 집합 동일 |
| 5 | `extract_clock_domains(rtl)` | 랜덤 always 블록 포함 RTL | 클럭 추출 정확성 + 도메인 분류 정확성 |
| 6 | `detect_cdc_boundary(domains)` | 랜덤 클럭 도메인 목록 | domains >= 2이면 true, 아니면 false |
| 7 | `extract_port_mappings(rtl)` | 랜덤 포트 매핑 포함 RTL | 모든 연결 추출 + 필수 필드 존재 |
| 8 | `detect_width_mismatch(conn)` | 랜덤 비트 폭 쌍 | 불일치 시 true, 일치 시 false |
| 9 | `classify_topic(path, name)` | 랜덤 파일 경로 + 모듈명 | 패턴 매칭 시 올바른 토픽, 미매칭 시 unclassified |
| 10 | `validate_claim(claim)` | 랜덤 claim 객체 | 필수 필드 존재 + 값 범위 검증 |
| 11 | `split_module_groups(groups)` | 랜덤 크기의 모듈 그룹 | 모든 청크 100K 토큰 이하 + 모든 모듈 포함 |
| 14 | `build_search_query(params)` | 랜덤 검색 파라미터 | 유효한 OpenSearch 쿼리 + 빈 파라미터 제외 |
| 15 | `extract_variant_delta(base, var)` | 랜덤 베이스라인/variant 쌍 | 변경 항목 정확 식별 + 미변경 항목 미포함 |
| 17 | Terraform 리소스 파일 | 모든 .tf 파일의 리소스 블록 | Project, Environment, ManagedBy 태그 존재 |
| 18 | `extract_package_params(rtl)` | 랜덤 localparam/parameter/typedef enum 포함 SV 코드 | 모든 선언 추출 + 원본 역검색 일치 |
| 19 | `extract_struct_fields(rtl)` | 랜덤 typedef struct 정의 포함 SV 코드 | 모든 필드명/비트폭 추출 + 필드 수 동일 |
| 20 | `build_edc_topology(nodes)` | 랜덤 EDC 노드 인스턴스화 관계 | 토폴로지 라운드트립 + 노드 ID 고유성 |
| 21 | `identify_overlay_roles(modules)` | 랜덤 Overlay 모듈 세트 | 알려진 패턴 역할 할당 + APB 슬레이브 추출 |
| 22 | `filter_pkg_files(file_keys)` | 랜덤 S3 파일 키 목록 (*_pkg.sv 포함/미포함) | *_pkg.sv 파일만 선택 + 비매칭 파일 미선택 |
| 23 | `extract_sram_inventory(hierarchy)` | 랜덤 계층 트리 (메모리 인스턴스 포함/미포함) | 메모리 패턴 매칭 정확성 + 필수 필드 존재 |
| 24 | `extract_memory_params(instance)` | 랜덤 메모리 인스턴스 (파라미터 유/무) | 추출 불가 시 "unknown" 기본값 설정 |
| 25 | MCP Bridge search_rtl 파라미터 전달 | 랜덤 파라미터 조합 (max_results, analysis_type, pipeline_id, topic) | 모든 파라미터가 Lambda 요청에 포함 + 미제공 파라미터 생략 |
| 26 | `_validate_claim_diversity(claims)` | 랜덤 claim 세트 (다양한 module_name 분포) | 3개 이상 모듈 + 단일 모듈 80% 미만 |
| 27 | `classify_topic(path, name)` 확장 | 랜덤 파일 경로 + 모듈명 (Power/Memory/NIU 패턴 포함) | 14개 토픽 지원 + tt_noc2axi_* → NIU |
| 28 | `parse_rtl_to_ast(rtl)` 포트 비트폭 | 랜덤 포트 선언 (비트폭 유/무, 다차원) | 비트폭 추출 정확성 + 비트폭 없으면 생략 |

### 단위 테스트

단위 테스트는 구체적인 예시와 엣지 케이스에 집중한다:

- Pipeline_ID 파싱: 유효/무효 S3 키 예시 (빈 문자열, 언더스코어 없음, 다중 언더스코어)
- 계층 트리: 순환 참조 감지, 루트 모듈 없는 경우, 단일 모듈 트리
- 클럭 도메인: 클럭 없는 모듈, 비표준 클럭명, 주석 내 클럭 패턴 무시
- 토픽 분류: 경계 케이스 (경로와 모듈명이 다른 토픽에 매칭)
- Claim 스키마: 필수 필드 누락, 잘못된 claim_type, confidence_score 범위 초과
- HDD 참조 무결성: 존재하지 않는 모듈 참조, 빈 계층 트리
- 메모리 인스턴스 식별: SRAM, register file, ROM 패턴 매칭
- 패키지 파라미터 추출: localparam/parameter/typedef enum 파싱, 빈 패키지 파일, 주석 내 선언 무시
- EDC 토폴로지: 단일 노드 링, 바이패스 없는 경우, 불완전한 연결 관계
- NoC 프로토콜: 빈 구조체, 중첩 구조체, 보안 펜스 모듈 없는 경우
- Overlay 구조: 알려지지 않은 서브모듈, 빈 크로스바, L1 캐시 파라미터 누락
- SRAM Inventory: 메모리 패턴 매칭 (sram, ram, rf_, reg_file, rom, memory, mem_), 파라미터 추출 불가 시 "unknown" 기본값, 빈 계층 트리
- 패키지 파일 필터: *_pkg.sv 매칭, 비매칭 파일 제외, 빈 파일 목록
- HDD 심화 분석 조회: chip_config/edc_topology/noc_protocol/overlay_deep 데이터가 프롬프트에 포함되는지 확인, 심화 데이터 없을 때 기본 HDD 생성

### 통합 테스트

통합 테스트는 AWS 인프라 연동을 검증한다:

- S3 업로드 -> Lambda 트리거 -> OpenSearch 인덱싱 E2E
- Step Functions 실행 -> DynamoDB 상태 업데이트
- Bedrock Claude 호출 -> Claim 생성 -> DynamoDB/OpenSearch 저장
- OpenSearch 필터링 검색 (pipeline_id, topic, analysis_type)
- Cross-region 접근: Seoul Lambda -> Virginia OpenSearch/Bedrock

### Terraform 인프라 테스트

기존 `tests/properties/` 디렉토리의 패턴을 따라 Terraform 리소스 속성을 검증한다:

- Step Functions 상태 머신 정의 검증 (재시도 설정, 타임아웃)
- Lambda 함수 설정 검증 (런타임, 메모리, 타임아웃, VPC 설정)
- DynamoDB 테이블 스키마 검증 (파티션 키, GSI)
- IAM 정책 최소 권한 검증
- 보안 그룹 규칙 검증
- KMS 암호화 설정 검증
- 리소스 태깅 검증 (Property 17)

### Terraform 리소스 목록 (신규 추가)

| 리소스 | 타입 | 설명 |
|--------|------|------|
| `aws_sfn_state_machine.analysis_orchestrator` | Step Functions | 분석 파이프라인 오케스트레이터 |
| `aws_iam_role.sfn_analysis` | IAM Role | Step Functions 실행 역할 |
| `aws_iam_role_policy.sfn_lambda_invoke` | IAM Policy | Step Functions Lambda invoke 권한 |
| `aws_iam_role_policy.sfn_dynamodb` | IAM Policy | Step Functions DynamoDB 상태 기록 권한 |
| `aws_iam_role_policy.rtl_parser_bedrock_claude` | IAM Policy | RTL Parser Lambda Bedrock Claude 호출 권한 |
| `aws_iam_role_policy.rtl_parser_sfn` | IAM Policy | RTL Parser Lambda Step Functions 시작 권한 |
| `aws_cloudwatch_log_group.sfn_analysis` | CloudWatch | Step Functions 실행 로그 |
| `aws_cloudwatch_metric_alarm.analysis_error_rate` | CloudWatch Alarm | 분석 에러율 10% 초과 알람 |

기존 리소스 수정:
- `aws_lambda_function.rtl_parser`: 환경 변수 추가 (STEP_FUNCTIONS_ARN, ANALYSIS_TYPE 등)
- `aws_iam_role_policy.rtl_parser_dynamodb`: PutItem + UpdateItem + Query 권한 추가
- `aws_iam_role_policy.rtl_parser_bedrock`: Claude 모델 InvokeModel 권한 추가
- OpenSearch 인덱스 매핑: 새 필드 추가 (pipeline_id, analysis_type, hierarchy_path 등)
