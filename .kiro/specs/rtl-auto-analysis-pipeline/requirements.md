# 요구사항 문서: RTL 자동 분석 파이프라인

## 소개

RTL 자동 분석 파이프라인은 Verilog/SystemVerilog RTL 코드를 S3에 업로드하면 자동으로 다단계 분석을 수행하여 HDD(Hardware Design Document) 수준의 구조화된 지식을 생성하고, OpenSearch RAG 인덱스에서 검색 가능하게 만드는 시스템이다. 현재 RTL Parser Lambda가 수행하는 단일 모듈 수준의 기본 파싱(모듈명, 포트, 파라미터, 인스턴스)을 확장하여, 엔지니어가 수동으로 수행하던 계층 분석, 클럭 도메인 분석, 데이터 흐름 추적, 토픽 분류, Claim 생성, HDD 섹션 생성까지 자동화한다.

이 Spec은 현재 업로드된 Trinity/N1B0 RTL(`rtl-sources/tt_20260221/`, 9,465개 파일, 539MB)을 대상으로 한 첫 번째 파이프라인 구축을 다룬다. 성공 후 다른 RTL 칩(예: `rtl-sources/n2_20260501/`)에 대해 동일 인프라 위에서 별도 파이프라인을 추가할 수 있는 확장 구조를 갖추며, S3 디렉토리 네이밍 규칙(`{chip_type}_{date}`)으로 파이프라인을 분기한다.

## 용어 정의

- **RTL_Parser_Lambda**: S3 이벤트로 트리거되어 RTL 소스 코드를 정규식 기반으로 파싱하고 OpenSearch에 인덱싱하는 AWS Lambda 함수 (`lambda-rtl-parser-seoul-dev`)
- **Analysis_Orchestrator**: RTL 파싱 완료 후 다단계 분석 작업을 순차적으로 조율하는 Step Functions 상태 머신
- **Hierarchy_Extractor**: RTL 모듈 간 parent→child 인스턴스화 관계를 추출하여 계층 트리를 생성하는 분석 컴포넌트
- **Clock_Domain_Analyzer**: RTL 코드에서 클럭 도메인을 추출하고 CDC(Clock Domain Crossing) 경계를 식별하는 분석 컴포넌트
- **Dataflow_Tracker**: 모듈 간 신호 연결 관계와 포트 매핑을 추적하는 분석 컴포넌트
- **Topic_Classifier**: 파일 경로와 모듈명 패턴을 기반으로 RTL 모듈을 주제별(NoC, FPU, EDC, Overlay 등)로 자동 분류하는 컴포넌트
- **Claim_Generator**: LLM(Bedrock Claude)을 사용하여 파싱 및 분석 결과로부터 구조화된 지식(claim)을 자동 생성하는 컴포넌트
- **HDD_Section_Generator**: 분석 결과를 조합하여 HDD 문서 섹션을 자동 생성하는 컴포넌트
- **RTL_S3_Bucket**: RTL 소스 코드가 업로드되는 S3 버킷 (`bos-ai-rtl-src-{account_id}`, Seoul 리전)
- **RTL_OpenSearch_Index**: RTL 파싱 및 분석 결과가 인덱싱되는 OpenSearch Serverless 인덱스 (us-east-1)
- **Claim_DB**: 자동 생성된 Claim이 저장되는 DynamoDB 테이블
- **HDD**: Hardware Design Document — 엔지니어가 RTL 코드를 분석하여 작성하는 구조화된 하드웨어 설계 문서
- **CDC**: Clock Domain Crossing — 서로 다른 클럭 도메인 간 신호가 전달되는 경계
- **Titan_Embeddings**: Amazon Titan Embed Text v2 모델로 생성되는 벡터 임베딩
- **Main_Lambda**: Seoul VPC 안에서 실행되는 메인 문서 처리 Lambda (`lambda-document-processor-seoul-prod`)
- **Pipeline_ID**: S3 디렉토리 네이밍에서 파생되는 파이프라인 식별자 (예: `tt_20260221`). `{chip_type}_{date}` 형식
- **Chip_Type**: RTL 칩 종류 식별자 (예: `tt` = Trinity/Tenstorrent). 디렉토리 이름의 첫 번째 `_` 앞 부분
- **Snapshot_Date**: RTL 스냅샷 날짜 (예: `20260221`). 디렉토리 이름의 첫 번째 `_` 뒤 부분

## 요구사항

### 요구사항 1: S3 업로드 트리거 및 분석 오케스트레이션

**사용자 스토리:** 엔지니어로서, RTL 코드를 S3에 업로드하기만 하면 전체 분석 파이프라인이 자동으로 실행되기를 원한다. 이를 통해 수동 분석 작업 없이 구조화된 지식을 얻을 수 있다.

#### 수용 기준

1. WHEN RTL 파일(.v, .sv, .svh)이 RTL_S3_Bucket의 `rtl-sources/` 경로에 업로드되면, THE RTL_Parser_Lambda SHALL 기존 모듈 수준 파싱을 수행하고 파싱 완료 이벤트를 발행한다
2. WHEN RTL_Parser_Lambda가 파싱 완료 이벤트를 발행하면, THE Analysis_Orchestrator SHALL 2단계 분석 파이프라인(베이스라인 분석 → HDD 생성)을 순차적으로 시작한다
3. WHILE Analysis_Orchestrator가 분석 파이프라인을 실행하는 동안, THE Analysis_Orchestrator SHALL 각 분석 단계의 진행 상태(pending, in_progress, completed, failed)를 DynamoDB에 기록한다
4. IF 분석 파이프라인의 특정 단계에서 오류가 발생하면, THEN THE Analysis_Orchestrator SHALL 해당 단계를 최대 2회 재시도하고, 재시도 실패 시 오류 상태를 기록하며 후속 단계를 건너뛴다
5. WHEN 단일 S3 업로드 이벤트에 여러 RTL 파일이 포함되면, THE Analysis_Orchestrator SHALL 각 파일에 대해 독립적인 분석 파이프라인 인스턴스를 생성한다
6. WHEN RTL 파일이 `rtl-sources/{chip_type}_{date}/` 경로에 업로드되면, THE RTL_Parser_Lambda SHALL 디렉토리 이름에서 Pipeline_ID를 추출하여 모든 분석 결과에 메타데이터로 포함한다
7. THE Analysis_Orchestrator SHALL Pipeline_ID별로 독립적인 분석 상태를 관리하여, 서로 다른 파이프라인의 분석이 간섭하지 않도록 한다

### 요구사항 2: 모듈 계층 관계 추출

**사용자 스토리:** 엔지니어로서, RTL 코드에서 모듈 계층 트리가 자동으로 추출되기를 원한다. 이를 통해 trinity_hierarchy.csv와 같은 계층 정보를 수동으로 작성하지 않아도 된다.

#### 수용 기준

1. WHEN RTL_Parser_Lambda가 모듈의 인스턴스 목록을 추출하면, THE Hierarchy_Extractor SHALL 동일 S3 업로드 세트 내의 모든 모듈 간 parent→child 인스턴스화 관계를 구축한다
2. THE Hierarchy_Extractor SHALL 각 계층 노드에 대해 모듈명, 인스턴스명, 계층 경로(예: `trinity.gen_dispatch_e.tt_dispatch_top_inst_east`)를 포함하는 계층 트리를 생성한다
3. WHEN 계층 트리가 생성되면, THE Hierarchy_Extractor SHALL 각 노드에 해당 모듈의 클럭 신호 목록과 리셋 신호 목록을 매핑한다
4. WHEN 계층 트리가 생성되면, THE Hierarchy_Extractor SHALL 메모리 인스턴스(SRAM, register file)를 식별하여 해당 계층 노드에 태깅한다
5. THE Hierarchy_Extractor SHALL 생성된 계층 트리를 CSV 형식과 JSON 형식 모두로 RTL_S3_Bucket의 `rtl-parsed/hierarchy/` 경로에 저장한다
6. FOR ALL 유효한 RTL 모듈 세트에 대해, 계층 트리를 생성한 후 해당 트리에서 각 parent→child 관계를 역으로 추적하면 원본 인스턴스화 관계와 동일한 결과를 산출한다 (라운드트립 속성)

### 요구사항 3: 클럭 도메인 분석

**사용자 스토리:** 엔지니어로서, RTL 코드에서 클럭 도메인과 CDC 경계가 자동으로 식별되기를 원한다. 이를 통해 타이밍 관련 설계 검증을 효율적으로 수행할 수 있다.

#### 수용 기준

1. WHEN RTL 파일이 파싱되면, THE Clock_Domain_Analyzer SHALL `always_ff @(posedge <clock>)` 및 `always @(posedge <clock>)` 패턴에서 클럭 신호명을 추출한다
2. THE Clock_Domain_Analyzer SHALL 추출된 클럭 신호를 클럭 도메인 그룹으로 분류한다 (예: `i_ai_clk` 계열, `i_noc_clk` 계열, `i_dm_clk` 계열, `i_ref_clk` 계열)
3. WHEN 하나의 모듈 내에서 2개 이상의 클럭 도메인이 감지되면, THE Clock_Domain_Analyzer SHALL 해당 모듈을 CDC 경계 모듈로 표시하고, 관련 클럭 도메인 쌍을 기록한다
4. THE Clock_Domain_Analyzer SHALL 클럭 도메인 분석 결과를 모듈별로 RTL_OpenSearch_Index에 인덱싱하여 `search_archive(source="rtl_parsed")` 쿼리로 검색 가능하게 한다
5. IF 클럭 신호명이 표준 패턴(`i_*clk*`, `clk_*`)과 일치하지 않으면, THEN THE Clock_Domain_Analyzer SHALL 해당 신호를 "unclassified_clock"으로 분류하고 경고 로그를 기록한다

### 요구사항 4: 데이터 흐름 추적

**사용자 스토리:** 엔지니어로서, 모듈 간 신호 연결 관계가 자동으로 추적되기를 원한다. 이를 통해 데이터 경로를 파악하기 위해 RTL 코드를 수동으로 추적하지 않아도 된다.

#### 수용 기준

1. WHEN 계층 트리가 구축되면, THE Dataflow_Tracker SHALL 각 모듈 인스턴스의 포트 연결(port mapping)을 추출하여 상위 모듈 신호와 하위 모듈 포트 간의 매핑을 기록한다
2. THE Dataflow_Tracker SHALL 추출된 포트 매핑을 기반으로 모듈 간 신호 연결 그래프(A→B→C 경로)를 생성한다
3. WHEN 신호 연결 그래프가 생성되면, THE Dataflow_Tracker SHALL 각 연결에 대해 신호 방향(input/output/inout)과 비트 폭 정보를 포함한다
4. THE Dataflow_Tracker SHALL 신호 연결 그래프를 RTL_OpenSearch_Index에 인덱싱하여 특정 신호명으로 연결 경로를 검색할 수 있게 한다
5. IF 포트 연결에서 비트 폭 불일치가 감지되면, THEN THE Dataflow_Tracker SHALL 해당 연결을 "width_mismatch" 경고로 태깅하고 로그에 기록한다

### 요구사항 5: 토픽 자동 분류

**사용자 스토리:** 엔지니어로서, RTL 모듈이 주제별로 자동 분류되기를 원한다. 이를 통해 특정 기능 블록(NoC, FPU, EDC 등)에 관련된 모듈을 빠르게 찾을 수 있다.

#### 수용 기준

1. THE Topic_Classifier SHALL 파일 경로 패턴(예: `*/noc/*`, `*/fpu/*`, `*/edc/*`)과 모듈명 접두사 패턴(예: `tt_noc_*`, `tt_fpu_*`, `tt_edc_*`)을 기반으로 RTL 모듈을 주제별로 분류한다
2. THE Topic_Classifier SHALL 최소 다음 토픽 카테고리를 지원한다: NoC, FPU, SFPU, TDMA, Overlay, EDC, Dispatch, L1_Cache, Clock_Reset, DFX, NIU, SMN
3. WHEN 하나의 모듈이 여러 토픽에 해당하면, THE Topic_Classifier SHALL 해당 모듈에 복수의 토픽 태그를 부여한다
4. IF 모듈이 사전 정의된 토픽 패턴과 일치하지 않으면, THEN THE Topic_Classifier SHALL 해당 모듈을 "unclassified"로 분류하고, 계층 트리에서 가장 가까운 분류된 상위 모듈의 토픽을 상속 후보로 제안한다
5. THE Topic_Classifier SHALL 토픽 분류 결과를 각 모듈의 OpenSearch 문서에 `topic` 필드로 추가하여 토픽 기반 필터링 검색을 지원한다

### 요구사항 6: LLM 기반 Claim 자동 생성

**사용자 스토리:** 엔지니어로서, RTL 분석 결과로부터 구조화된 지식(claim)이 자동 생성되기를 원한다. 이를 통해 검증 팀이 활용할 수 있는 설계 사실(fact)을 자동으로 축적할 수 있다.

#### 수용 기준

1. WHEN 베이스라인 분석(계층 추출, 클럭 분석, 데이터 흐름 추적, 토픽 분류)이 완료되면, THE Claim_Generator SHALL Bedrock Claude 모델을 호출하여 분석 결과로부터 구조화된 claim을 생성한다
2. THE Claim_Generator SHALL 각 claim에 대해 다음 필드를 포함한다: claim_id, module_name, topic, claim_type(structural, behavioral, connectivity, timing), claim_text, confidence_score, source_files
3. THE Claim_Generator SHALL 생성된 claim을 Claim_DB(DynamoDB)에 저장하고, 동시에 RTL_OpenSearch_Index에 Titan_Embeddings 벡터와 함께 인덱싱한다
4. WHILE Claim_Generator가 LLM을 호출하는 동안, THE Claim_Generator SHALL 단일 LLM 호출당 입력 토큰 수를 100,000 토큰 이하로 제한하고, 초과 시 모듈 그룹 단위로 분할하여 호출한다
5. IF LLM 호출이 실패하거나 타임아웃(60초)이 발생하면, THEN THE Claim_Generator SHALL 해당 모듈 그룹에 대해 최대 1회 재시도하고, 재시도 실패 시 해당 그룹을 건너뛰고 오류를 기록한다

### 요구사항 7: HDD 섹션 자동 생성

**사용자 스토리:** 엔지니어로서, 분석 결과가 HDD 문서 형식으로 자동 생성되기를 원한다. 이를 통해 수동으로 HDD를 작성하는 시간을 절약하고, RAG에서 HDD 수준의 상세한 답변을 얻을 수 있다.

#### 수용 기준

1. WHEN 베이스라인 분석과 Claim 생성이 완료되면, THE HDD_Section_Generator SHALL 토픽별로 그룹화된 분석 결과를 Bedrock Claude 모델에 전달하여 HDD 섹션을 생성한다
2. THE HDD_Section_Generator SHALL 각 HDD 섹션에 다음 구조를 포함한다: 개요, 모듈 계층, 블록 다이어그램(ASCII), 기능 상세, 클럭/리셋 구조, 주요 파라미터, 검증 체크리스트
3. THE HDD_Section_Generator SHALL 생성된 HDD 섹션을 Markdown 형식으로 RTL_S3_Bucket의 `rtl-parsed/hdd/` 경로에 저장한다
4. WHEN HDD 섹션이 생성되면, THE HDD_Section_Generator SHALL 해당 섹션을 RTL_OpenSearch_Index에 Titan_Embeddings 벡터와 함께 인덱싱하여 `search_archive(source="rtl_parsed")` 쿼리로 검색 가능하게 한다
5. THE HDD_Section_Generator SHALL 생성된 HDD 섹션에 소스 RTL 파일 목록, 생성 일시, 분석 파이프라인 버전을 메타데이터로 포함한다
6. FOR ALL 생성된 HDD 섹션에 대해, 해당 섹션에서 참조하는 모듈명은 계층 트리에 존재하는 모듈명의 부분집합이어야 한다 (참조 무결성)

### 요구사항 8: OpenSearch 인덱싱 및 RAG 검색 통합

**사용자 스토리:** 엔지니어로서, 자동 분석 결과를 기존 RAG 시스템에서 자연어로 검색할 수 있기를 원한다. 이를 통해 "NoC 라우터의 클럭 도메인은?" 같은 질문에 즉시 답변을 얻을 수 있다.

#### 수용 기준

1. THE RTL_Parser_Lambda SHALL 기존 `rtl-parsed` 인덱스 스키마를 확장하여 hierarchy_path, clock_domains, topic, claim_type, dataflow_connections 필드를 추가한다
2. WHEN 분석 결과가 RTL_OpenSearch_Index에 인덱싱되면, THE RTL_Parser_Lambda SHALL 각 문서에 대해 Titan_Embeddings 벡터를 생성하여 벡터 검색을 지원한다
3. WHEN Main_Lambda가 `search_archive(source="rtl_parsed")` 요청을 수신하면, THE Main_Lambda SHALL 토픽, 클럭 도메인, 계층 경로 필드를 활용한 필터링 검색을 지원한다
4. THE RTL_OpenSearch_Index SHALL 분석 유형별(hierarchy, clock_domain, dataflow, topic, claim, hdd_section) 문서 타입을 구분하는 `analysis_type` 필드를 포함한다
5. IF 동일 모듈에 대해 새로운 분석 결과가 생성되면, THEN THE RTL_Parser_Lambda SHALL 기존 인덱스 문서를 업데이트하고 이전 버전의 타임스탬프를 보존한다

### 요구사항 9: Variant Delta 분석

**사용자 스토리:** 엔지니어로서, 베이스라인 칩 대비 variant 칩의 변경점이 자동으로 추출되기를 원한다. 이를 통해 N1B0 같은 variant의 차이점을 빠르게 파악할 수 있다.

#### 수용 기준

1. WHEN 동일 S3 경로 구조에 베이스라인과 variant RTL이 모두 존재하면, THE Analysis_Orchestrator SHALL variant 분석 단계를 추가로 실행한다
2. THE Analysis_Orchestrator SHALL 베이스라인과 variant 간 다음 항목의 차이를 추출한다: 그리드 크기 변경, 모듈 추가/삭제, 파라미터 값 변경, 클럭 배열 변경, 인스턴스 추가/삭제
3. WHEN variant delta가 추출되면, THE HDD_Section_Generator SHALL 베이스라인 HDD에 delta 정보를 병합하여 variant 전용 HDD 섹션을 생성한다
4. THE Analysis_Orchestrator SHALL variant delta 결과를 RTL_OpenSearch_Index에 `analysis_type=variant_delta` 문서로 인덱싱하여 variant 간 비교 검색을 지원한다

### 요구사항 10: 파이프라인 분기 및 멀티 칩 지원

**사용자 스토리:** 인프라 운영자로서, 새로운 RTL 칩이 추가될 때 인프라 변경 없이 디렉토리 네이밍만으로 별도 파이프라인을 생성할 수 있기를 원한다. 이를 통해 여러 칩의 RTL을 동일 시스템에서 관리할 수 있다.

#### 수용 기준

1. WHEN RTL 파일이 `rtl-sources/{chip_type}_{date}/` 형식의 디렉토리에 업로드되면, THE RTL_Parser_Lambda SHALL 디렉토리 이름에서 `{chip_type}`과 `{date}`를 파싱하여 Pipeline_ID(`{chip_type}_{date}`)를 생성한다
2. THE Analysis_Orchestrator SHALL Pipeline_ID별로 독립적인 분석 파이프라인 인스턴스를 실행하여, 서로 다른 칩의 분석이 간섭하지 않도록 한다
3. THE RTL_OpenSearch_Index SHALL 모든 문서에 `pipeline_id` 필드를 포함하여, `search_archive(source="rtl_parsed", pipeline_id="tt_20260221")` 형태의 파이프라인별 필터링 검색을 지원한다
4. THE Claim_DB SHALL `pipeline_id`를 파티션 키의 일부로 포함하여 파이프라인별 Claim을 논리적으로 격리한다
5. WHEN 동일 Chip_Type의 새로운 Snapshot_Date 스냅샷이 업로드되면, THE Analysis_Orchestrator SHALL 이전 스냅샷의 분석 결과를 유지하면서 새 스냅샷에 대한 독립적인 분석을 수행한다
6. THE HDD_Section_Generator SHALL 생성된 HDD 섹션에 Pipeline_ID를 메타데이터로 포함하여, 어떤 RTL 스냅샷에서 생성된 문서인지 추적 가능하게 한다

### 요구사항 11: 인프라 및 보안 제약

**사용자 스토리:** 인프라 운영자로서, 분석 파이프라인이 기존 BOS-AI 인프라의 보안 및 네트워크 제약을 준수하기를 원한다. 이를 통해 기존 시스템과의 호환성을 유지할 수 있다.

#### 수용 기준

1. THE Analysis_Orchestrator SHALL Seoul 리전(ap-northeast-2)의 BOS-AI Frontend VPC 내에서 실행된다
2. THE RTL_Parser_Lambda SHALL Python 3.12 런타임과 boto3 표준 라이브러리만 사용한다 (requests 라이브러리는 기존 배포 패키지에 포함된 것만 허용)
3. THE Analysis_Orchestrator SHALL OpenSearch Serverless(us-east-1)에 접근할 때 VPC Peering 경로를 통해 접근한다
4. THE Claim_Generator SHALL Bedrock Claude 모델 호출 시 us-east-1 리전의 Bedrock 엔드포인트를 사용한다
5. THE RTL_Parser_Lambda SHALL 모든 S3 객체에 대해 KMS 암호화(SSE-KMS)를 적용한다
6. THE Analysis_Orchestrator SHALL 모든 AWS 리소스에 Project=BOS-AI, Environment, ManagedBy 태그를 포함한다
7. THE RTL_Parser_Lambda SHALL Lambda 실행 시간이 300초를 초과하지 않도록 분석 작업을 분할한다
8. THE Analysis_Orchestrator SHALL 새로운 RTL 칩이 추가되어도 기존 인프라 리소스(S3 버킷, OpenSearch 인덱스, Lambda 함수, DynamoDB 테이블)를 재생성하지 않고 동일 리소스를 공유한다
9. THE RTL_OpenSearch_Index SHALL Pipeline_ID 필드를 포함하여 파이프라인별 검색 필터링을 지원한다
10. THE Claim_DB SHALL Pipeline_ID를 파티션 키의 일부로 포함하여 파이프라인별 Claim을 격리한다

### 요구사항 12: 패키지 파라미터 및 칩 구성 추출

**사용자 스토리:** 엔지니어로서, RTL 패키지 파일(`*_pkg.sv`)에서 칩 구성 파라미터(그리드 크기, 타일 수, 타일 타입 enum 등)가 자동으로 추출되기를 원한다. 이를 통해 "4×5 그리드, 12 Tensix, 4 NIU" 같은 칩 레벨 사양을 수동으로 파악하지 않아도 된다.

#### 수용 기준

1. WHEN RTL 파일이 파싱되면, THE RTL_Parser_Lambda SHALL `*_pkg.sv` 파일에서 `localparam`, `parameter`, `typedef enum` 선언을 추출하여 패키지 파라미터 목록을 생성한다
2. THE RTL_Parser_Lambda SHALL 추출된 파라미터에서 칩 구성 정보(SizeX, SizeY, NumTensix, NumNoc2Axi, NumDispatch 등)를 식별하고 `analysis_type=chip_config` 문서로 OpenSearch에 인덱싱한다
3. THE RTL_Parser_Lambda SHALL `typedef enum` 선언에서 타일 타입(TENSIX, NOC2AXI_NE_OPT 등)과 해당 RTL 모듈 매핑을 추출한다
4. WHEN HDD_Section_Generator가 칩 전체 HDD를 생성할 때, THE HDD_Section_Generator SHALL 패키지 파라미터에서 추출된 그리드 크기, 타일 수, 엔드포인트 인덱스 테이블을 HDD 개요 섹션에 포함한다
5. THE Claim_Generator SHALL 패키지 파라미터 기반으로 "N1B0는 4×5 그리드에 12개 Tensix 타일을 배치한다" 같은 칩 구성 claim을 자동 생성한다

### 요구사항 13: EDC 토폴로지 및 프로토콜 분석

**사용자 스토리:** 엔지니어로서, EDC 서브시스템의 링 토폴로지, 시리얼 버스 프로토콜, 하베스트 바이패스 메커니즘이 자동으로 분석되기를 원한다. 이를 통해 EDC_HDD 수준의 상세한 토폴로지 문서를 수동으로 작성하지 않아도 된다.

#### 수용 기준

1. WHEN EDC 관련 모듈(`tt_edc1_*`)이 파싱되면, THE Analysis_Orchestrator SHALL EDC 노드 간 연결 관계를 추출하여 링 토폴로지(U-shape: Segment A 하향 → U-turn → Segment B 상향)를 재구성한다
2. THE Analysis_Orchestrator SHALL `tt_edc1_serial_bus_mux`와 `tt_edc1_serial_bus_demux` 모듈의 인스턴스화 패턴에서 하베스트 바이패스 경로를 식별한다
3. THE Analysis_Orchestrator SHALL `tt_edc1_pkg.sv`에서 시리얼 버스 인터페이스 정의(`req_tgl`, `ack_tgl`, `data`, `data_p`, `async_init`)를 추출하여 프로토콜 사양을 문서화한다
4. THE Analysis_Orchestrator SHALL EDC 노드 ID 구조(`node_id_part`, `node_id_subp`, `node_id_inst`)를 추출하여 노드 ID 디코딩 테이블을 생성한다
5. WHEN HDD_Section_Generator가 EDC HDD를 생성할 때, THE HDD_Section_Generator SHALL 링 토폴로지 ASCII 다이어그램, 하베스트 바이패스 흐름도, 노드 ID 테이블을 포함한다

### 요구사항 14: NoC 라우팅 알고리즘 및 패킷 구조 분석

**사용자 스토리:** 엔지니어로서, NoC의 라우팅 알고리즘(DOR, Tendril, Dynamic), 패킷 구조(flit format), 보안 펜스 메커니즘이 자동으로 분석되기를 원한다. 이를 통해 router_decode_HDD 수준의 상세한 NoC 문서를 수동으로 작성하지 않아도 된다.

#### 수용 기준

1. WHEN NoC 관련 모듈이 파싱되면, THE Analysis_Orchestrator SHALL `tt_noc_pkg.sv`에서 라우팅 알고리즘 enum(`DIM_ORDER`, `TENDRIL`, `DYNAMIC`)과 관련 파라미터(`EnableDynamicRouting` 등)를 추출한다
2. THE Analysis_Orchestrator SHALL `noc_header_address_t` 구조체에서 flit 헤더 필드(x_dest, y_dest, endpoint_id, flit_type, dynamic_carried_list)를 추출하여 패킷 구조를 문서화한다
3. THE Analysis_Orchestrator SHALL AXI 주소 가스켓(56-bit) 구조(`target_index`, `endpoint_id`, `tlb_index`, `address`)를 추출한다
4. THE Analysis_Orchestrator SHALL `tt_noc_sec_fence_edc_wrapper` 모듈에서 보안 펜스 메커니즘(SMN 그룹 기반 접근 제어)을 식별한다
5. WHEN HDD_Section_Generator가 NoC HDD를 생성할 때, THE HDD_Section_Generator SHALL 라우팅 알고리즘 비교 테이블, flit 구조 다이어그램, AXI 주소 매핑 테이블을 포함한다

### 요구사항 15: Overlay 내부 구조 심화 분석

**사용자 스토리:** 엔지니어로서, Overlay(RISC-V 서브시스템)의 내부 구조(CPU 클러스터, iDMA, ROCC, LLK, SMN)가 자동으로 분석되기를 원한다. 이를 통해 overlay_HDD 수준의 상세한 서브시스템 문서를 수동으로 작성하지 않아도 된다.

#### 수용 기준

1. WHEN Overlay 관련 모듈(`tt_overlay_*`)이 파싱되면, THE Analysis_Orchestrator SHALL `tt_overlay_pkg.sv`에서 CPU 클러스터 파라미터(NUM_CLUSTER_CPUS, NUM_INTERRUPTS, RESET_VECTOR_WIDTH)를 추출한다
2. THE Analysis_Orchestrator SHALL Overlay 내부의 서브모듈 역할을 식별한다: CPU 클러스터(tt_overlay_cpu_wrapper), iDMA(tt_idma_wrapper), ROCC(tt_rocc_accel), LLK 카운터(tt_overlay_tile_counters), SMN(tt_overlay_smn_wrapper), FDS(tt_fds_wrapper)
3. THE Analysis_Orchestrator SHALL L1 캐시 파라미터(뱅크 수, 뱅크 폭, ECC 타입, SRAM 타입)를 `tt_overlay_memory_wrapper` 모듈에서 추출한다
4. THE Analysis_Orchestrator SHALL Overlay의 레지스터 크로스바(`tt_overlay_reg_xbar_slave_decode`) 구조에서 APB 슬레이브 목록과 주소 맵을 추출한다
5. WHEN HDD_Section_Generator가 Overlay HDD를 생성할 때, THE HDD_Section_Generator SHALL CPU-to-NoC 데이터 경로, L1 캐시 구성 테이블, 레지스터 맵 요약을 포함한다
