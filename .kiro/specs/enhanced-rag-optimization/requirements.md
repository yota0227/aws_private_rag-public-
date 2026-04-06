# 요구사항 문서: Enhanced RAG Optimization (v0.2)

## 소개

BOS-AI Private RAG 시스템의 검색 품질과 지식 관리 체계를 근본적으로 강화하기 위한 확장 기능이다. Spec 5(rag-search-optimization)에서 구현한 Hybrid Search, 메타데이터 자동 생성/필터링, 검색 응답 구조 개선, MCP Bridge 필터 전달, 검색 품질 모니터링을 기반으로, 두 개의 아키텍처 제안서(A: RTL 파이프라인 분리 + 인프라 격리, B: 분석 워크플로형 RAG + Claim DB + Verification Pipeline)의 장점을 냉철히 분석하여 수용한 결과물이다.

v0.2 변경 사항 (아키텍트 리뷰 반영):
- Claim_DB 키 설계 강화: `variant`, `claim_family_id`, `is_latest` 필드 및 3개 GSI 추가
- Evidence 객체 확장: `source_type`, `source_path`, `line_start`, `line_end`, `chunk_hash` 필드 추가
- `verify_claims` → `list_verified_claims` 도구명 변경 (읽기 작업 명확화)
- Conflict_Score를 `validation_risk_score`와 `contradiction_score`로 분리
- `source` 허용 값에 `"system_generated"` 추가
- Claim statement vs evidence 분리 명확화
- Human Review Gate 추가 (요구사항 14)
- Operational KPI Metrics 추가 (요구사항 15)
- RTL Parser Lambda 메모리 2048MB 상향, OCI 컨테이너 마이그레이션 준비, 8000 토큰 truncation
- OpenSearch 인덱스 생성을 별도 Python 스크립트로 분리
- DynamoDB Optimistic Locking 추가
- IAM Explicit Deny로 Source of Truth 버킷 보호
- Object Lock 범위 명확화, RTL Parser Lambda 명칭 수정, Claim_DB 용어집 수정
- Claim-level variant 지원 추가

핵심 변경 영역:
1. RTL 전용 S3 버킷 분리 및 RTL 구조 파싱 Lambda (제안서 A)
2. RTL 전용 OpenSearch 인덱스 생성 (제안서 A)
3. Claim DB 구조 (DynamoDB 기반, statement + evidence + status + variant + family) (제안서 B)
4. DB 오염 방지 장치 (claim status lifecycle, evidence mandatory, contradiction check, optimistic locking) (제안서 B)
5. MCP Tool 분리 (search_archive, get_evidence, list_verified_claims 등) (제안서 B)
6. Verification Pipeline (topic 식별 → claim 검색 → 근거 추적 → 충돌 검사 → 답변 생성) (제안서 B)
7. 3계층 RAG 분리 (Source of Truth / Knowledge Archive / Serving) (제안서 B)
8. Cross-check 파이프라인 (1차 LLM claim 생성 → 2차 검증 → 3차 rule-based checker) (제안서 B)
9. Human Review Gate (critical topic 출판 전 승인 게이트) (v0.2 신규)
10. Operational KPI Metrics (CloudWatch 커스텀 메트릭 발행) (v0.2 신규)

단계적 도입: Phase 1(문서 ingestion 분리 + RTL 파이프라인) → Phase 2(Claim DB 구축) → Phase 3(MCP Tool 오픈) → Phase 4(문서 생성 + Human Review) → Phase 5(conflict detector + cross-check + KPI 모니터링)

보류 항목: Neptune Graph DB(Phase 3 이후 검증), Aurora PostgreSQL(DynamoDB 대체), Step Functions(Lambda 내부 오케스트레이션), ECS/Fargate MCP 서버(온프렘 Node.js 유지)

## 용어집

- **Lambda_Handler**: Seoul VPC에 배포된 `lambda-document-processor-seoul-prod` Lambda 함수로, 문서 업로드/삭제/질의 처리를 담당하는 핵심 컴포넌트
- **Bedrock_KB**: AWS Bedrock Knowledge Base(ID: FNNOP3VBZV)로, 문서 임베딩 저장 및 검색-생성(Retrieve and Generate)을 수행하는 서비스
- **OpenSearch_Collection**: Virginia 리전의 OpenSearch Serverless 벡터 컬렉션(ID: iw3pzcloa0en8d90hh7)으로, 임베딩 벡터를 저장하고 검색하는 벡터 데이터베이스
- **RTL_S3_Bucket**: RTL 전용 S3 버킷(`bos-ai-rtl-codes-<account_id>`)으로, RTL 소스 코드 원본을 저장하며 S3 Event Notification이 활성화된 격리 저장소
- **RTL_Parser_Lambda**: RTL 코드를 정규식 기반으로 파싱하여 module_name, parent_module, port_list, parameter_list 등 메타데이터를 추출하는 전용 Lambda 함수. 현재 정규식 기반 구현이며, 향후 PyVerilog/AST 통합을 위한 모듈화 구조를 유지한다
- **RTL_OpenSearch_Index**: RTL 메타데이터 전용 OpenSearch 인덱스(`rtl-knowledge-base-index`)로, knn_vector + keyword + text 매핑을 지원하는 벡터 검색 인덱스
- **Claim_DB**: DynamoDB 기반 Knowledge Archive (claim lifecycle managed)로, claim 단위로 지식을 저장하며 draft/verified/conflicted/deprecated 전체 생명주기를 관리한다. claim_id, topic, statement, evidence, confidence, version, status, variant, claim_family_id, is_latest, derived_from, last_verified_at 필드를 포함
- **Claim**: 단일 지식 단위로, 하나의 주제(topic)에 대한 하나의 진술(statement)과 그 근거(evidence)를 포함하는 구조화된 레코드. variant와 claim_family_id를 통해 변형 및 계보 추적을 지원한다
- **Claim_Status**: Claim의 생명주기 상태로, `draft`(초안), `verified`(검증 완료), `conflicted`(충돌 감지), `deprecated`(폐기) 중 하나
- **Evidence**: Claim의 근거가 되는 원본 문서 참조 정보로, source_document_id, source_chunk, page_number, extraction_date, source_type, source_path, line_start, line_end, chunk_hash를 포함
- **Verification_Pipeline**: 질문 수신 → topic 식별 → claim 검색 → 근거 추적 → 충돌 검사 → 버전 확인 → 답변 생성 → evidence 첨부의 8단계 검증 파이프라인
- **Cross_Check_Pipeline**: 1차 LLM claim 생성 → 2차 다른 prompt/model 검증 → 3차 rule-based checker → validation_risk_score 계산의 4단계 교차 검증 파이프라인
- **Source_of_Truth_Layer**: 원본 문서 저장 계층으로, LLM이 직접 수정할 수 없는 불변 원본 (S3 버킷의 md/pdf/rtl 파일)
- **Verified_Knowledge_Layer**: Claim DB 계층으로, 원본에서 추출/검증된 claim을 구조화하여 저장하는 중간 계층
- **Serving_Layer**: 사용자 인터페이스 계층으로, MCP Tool을 통해 Claim DB와 원본을 조합하여 답변을 생성하는 최종 계층
- **MCP_Bridge**: 온프레미스 Obot 서버(192.128.20.241)에서 실행되는 Node.js MCP SSE 브릿지 서버로, 사용자 질의를 API Gateway를 통해 Lambda_Handler로 전달
- **Seoul_S3**: 서울 리전 S3 버킷(bos-ai-documents-seoul-v3)으로, 문서 업로드의 최초 저장소
- **Virginia_S3**: 버지니아 리전 S3 버킷(bos-ai-documents-us)으로, 크로스 리전 복제를 통해 Seoul_S3의 문서를 수신하며 Bedrock_KB의 데이터 소스로 사용
- **Validation_Risk_Score**: Cross_Check_Pipeline에서 산출되는 개별 claim의 검증 실패 위험도 점수(0.0~1.0). 공식: `validation_risk_score = 1.0 - (score_1 * 0.4 + score_2 * 0.4 + score_3 * 0.2)`. 0.3 미만이면 verified, 0.3~0.7이면 수동 검토, 0.7 이상이면 conflicted로 상태 전이에 사용
- **Contradiction_Score**: 동일 topic 내 두 claim 간의 모순 정도를 0.0~1.0 범위로 수치화한 값. 0.7 이상이면 모순으로 판정하여 기존 claim의 status를 `conflicted`로 변경. 요구사항 5.5의 claim 간 비교에 사용
- **Topic**: Claim을 분류하는 주제 식별자로, 계층적 구조를 지원 (예: `ucie/phy/ltssm`, `ahb/signal/haddr`)
- **Foundation_Model**: Bedrock에서 응답 생성에 사용하는 Claude 3.5 Haiku 모델(us.anthropic.claude-3-5-haiku-20241022-v1:0)

## 요구사항

### 요구사항 1: RTL 전용 S3 버킷 분리 및 Event Notification

**사용자 스토리:** 반도체 설계 엔지니어로서, RTL 소스 코드를 일반 문서와 분리된 전용 저장소에 업로드하고 싶다. 이를 통해 RTL 코드가 전용 파싱 파이프라인을 거쳐 정확한 메타데이터와 함께 검색 가능해지기를 원한다.

#### 인수 조건

1. THE Terraform 구성 SHALL RTL 전용 S3 버킷(`bos-ai-rtl-codes-<account_id>`)을 Seoul 리전(ap-northeast-2)에 생성하며, 버전 관리(versioning)를 활성화한다.
2. THE Terraform 구성 SHALL RTL_S3_Bucket에 KMS CMK 암호화를 적용하며, 기존 BOS-AI KMS 키를 사용한다.
3. THE Terraform 구성 SHALL RTL_S3_Bucket에 S3 Event Notification을 구성하여, `rtl-sources/` 접두사에 객체가 생성될 때 RTL_Parser_Lambda를 트리거한다.
4. THE Terraform 구성 SHALL RTL_S3_Bucket에서 Virginia 리전 RTL 전용 S3 버킷으로의 Cross-Region Replication을 구성한다.
5. THE Terraform 구성 SHALL RTL_S3_Bucket에 퍼블릭 액세스 차단(Block Public Access)을 활성화하고, VPC Endpoint를 통한 접근만 허용하는 버킷 정책을 적용한다.
6. THE Terraform 구성 SHALL RTL_S3_Bucket에 필수 태그(Project: BOS-AI, Environment: prod, ManagedBy: terraform, Layer: app)를 적용한다.
7. IF RTL_S3_Bucket 생성 중 버킷명 충돌이 발생하면, THEN THE Terraform 구성 SHALL 에러 메시지에 대체 버킷명 규칙을 안내한다.

### 요구사항 2: RTL 구조 파싱 Lambda

**사용자 스토리:** 반도체 설계 엔지니어로서, RTL 코드가 업로드되면 모듈명, 포트 목록, 파라미터, 인스턴스 계층 등 구조적 메타데이터가 자동으로 추출되어, "BLK_UCIE 모듈의 입력 포트 목록"과 같은 구조적 질의에 정확한 답변을 받고 싶다.

#### 인수 조건

1. WHEN RTL 파일이 RTL_S3_Bucket의 `rtl-sources/` 접두사에 업로드되면, THE RTL_Parser_Lambda SHALL S3 Event Notification을 통해 자동으로 트리거된다.
2. THE RTL_Parser_Lambda SHALL RTL 파일 콘텐츠를 S3에서 읽어 정규식 기반 파서 함수(`parse_rtl_to_ast`)를 호출하여 다음 메타데이터를 추출한다: `module_name`(모듈명), `parent_module`(상위 모듈명, 없으면 빈 문자열), `port_list`(포트 목록 배열), `parameter_list`(파라미터 목록 배열), `instance_list`(인스턴스화된 하위 모듈 목록 배열), `file_path`(원본 S3 키).
3. THE RTL_Parser_Lambda SHALL `parse_rtl_to_ast` 함수를 모듈화된 구조로 구현하여, 향후 PyVerilog/AST 통합 시 함수 시그니처 변경 없이 내부 구현만 교체할 수 있도록 한다.
4. THE RTL_Parser_Lambda SHALL 추출된 메타데이터를 JSON 형식으로 직렬화하고, RTL_S3_Bucket의 `rtl-parsed/` 접두사에 `{원본파일명}.parsed.json` 파일로 저장한다.
5. THE RTL_Parser_Lambda SHALL 파싱된 메타데이터를 Titan Embeddings v2 모델을 사용하여 벡터 임베딩으로 변환하고, RTL_OpenSearch_Index에 인덱싱한다.
6. IF RTL 파일의 구문이 정규식 파서로 파싱할 수 없는 형식이면, THEN THE RTL_Parser_Lambda SHALL 파싱 실패를 CloudWatch에 ERROR 로그로 기록하고, 원본 파일 경로와 실패 사유를 포함한 에러 레코드를 DynamoDB 에러 테이블에 저장한다.
7. THE RTL_Parser_Lambda SHALL 원본 RTL 소스 코드 전체를 벡터 DB에 저장하지 않으며, 파싱된 메타데이터와 코드 요약(모듈 선언부, 포트 선언부)만 저장한다.
8. THE RTL_Parser_Lambda SHALL Python 3.12 런타임으로 실행되며, 메모리 2048MB(약 1.2 vCPU, CPU 집약적 파싱 대응), 타임아웃 300초로 구성한다.
9. FOR ALL 유효한 Verilog/SystemVerilog 모듈 선언에 대해, `parse_rtl_to_ast`로 파싱한 후 파싱 결과를 텍스트로 직렬화하고 다시 파싱하면 동일한 메타데이터 구조를 생성해야 한다 (라운드트립 속성).
10. THE RTL_Parser_Lambda SHALL 향후 PyVerilog + Icarus Verilog 의존성이 Lambda Layer 250MB 제한을 초과할 경우를 대비하여, OCI 컨테이너 이미지 배포(ECR) 방식으로 마이그레이션할 수 있도록 코드 구조를 유지한다.
11. THE RTL_Parser_Lambda SHALL 파싱된 요약 텍스트(parsed_summary)를 Titan Embeddings v2 입력 제한(8,192 토큰)을 고려하여 최대 8,000 토큰으로 truncation하며, 임베딩 API 호출 전 방어적 길이 검사를 수행한다.

### 요구사항 3: RTL 전용 OpenSearch 인덱스

**사용자 스토리:** 반도체 설계 엔지니어로서, RTL 모듈 구조를 벡터 검색과 키워드 검색 모두로 조회할 수 있도록, RTL 메타데이터 전용 OpenSearch 인덱스가 구성되기를 원한다.

#### 인수 조건

1. THE Terraform 구성 SHALL OpenSearch_Collection과 데이터 액세스 정책(control plane)을 프로비저닝한다. RTL_OpenSearch_Index 생성(data plane)은 Terraform `local-exec` provisioner를 사용하지 않는다.
2. THE RTL_OpenSearch_Index(`rtl-knowledge-base-index`) 생성 SHALL 별도 Python 스크립트(`scripts/create-opensearch-index.py`)를 통해 수행되며, SigV4 인증(`requests-aws4auth`)을 사용하여 OpenSearch_Collection에 접근한다.
3. THE RTL_OpenSearch_Index SHALL 다음 필드 매핑을 정의한다: `embedding`(knn_vector, dimension: 1024, Titan Embeddings v2 기준), `module_name`(keyword), `parent_module`(keyword), `port_list`(text), `parameter_list`(text), `instance_list`(text), `file_path`(keyword), `parsed_summary`(text).
4. THE RTL_OpenSearch_Index SHALL knn_vector 필드에 `engine: faiss`, `space_type: l2` 설정을 적용한다.
5. THE Terraform 구성 SHALL RTL_OpenSearch_Index에 대한 데이터 액세스 정책을 구성하여, RTL_Parser_Lambda IAM 역할과 Bedrock_KB 서비스 프린시펄에게 인덱싱 및 검색 권한을 부여한다.
6. WHILE RTL_OpenSearch_Index가 활성 상태인 동안, THE OpenSearch_Collection SHALL 기존 문서 인덱스(`bedrock-knowledge-base-default-index`)와 RTL_OpenSearch_Index를 독립적으로 유지하며, 한 인덱스의 변경이 다른 인덱스에 영향을 주지 않아야 한다.

### 요구사항 4: Claim DB 구조 (DynamoDB)

**사용자 스토리:** 반도체 설계 엔지니어로서, RAG 시스템이 단순 문서 검색을 넘어 검증된 지식 단위(claim)로 답변을 제공하여, 각 답변의 근거와 신뢰도를 명확히 확인할 수 있기를 원한다.

#### 인수 조건

1. THE Terraform 구성 SHALL Claim_DB용 DynamoDB 테이블을 Seoul 리전에 생성하며, 파티션 키를 `claim_id`(String), 정렬 키를 `version`(Number)으로 설정한다.
2. THE Terraform 구성 SHALL Claim_DB 테이블에 다음 GSI(Global Secondary Index)를 생성한다: `topic-index`(파티션 키: `topic`, 정렬 키: `last_verified_at`), `status-index`(파티션 키: `status`, 정렬 키: `last_verified_at`), `topic-variant-index`(파티션 키: `topic#variant` 복합 키, 정렬 키: `last_verified_at`, baseline/N1B0 variant 쿼리용), `source-document-index`(파티션 키: `source_document_id`, 정렬 키: `extraction_date`, evidence 역추적용), `family-index`(파티션 키: `claim_family_id`, 정렬 키: `version`, claim 계보 추적용).
3. THE Claim_DB SHALL 각 Claim 레코드에 다음 필드를 포함한다: `claim_id`(UUID 문자열), `topic`(계층적 주제 식별자 문자열), `statement`(정규화된 1문장 사실 진술 문자열, 10~500자), `evidence`(Evidence 객체 배열, 최소 1개 필수), `confidence`(0.0~1.0 범위 숫자), `version`(정수, 1부터 시작), `status`(Claim_Status 열거값), `variant`(변형 식별자 문자열, 기본값 `"default"`), `claim_family_id`(UUID 문자열, 동일 claim의 버전 그룹 식별), `is_latest`(불리언, 최신 버전 빠른 조회용), `applies_to`(적용 대상 variant 배열, 예: `["baseline", "N1B0"]`), `baseline_reference`(문자열, nullable, baseline variant claim_id 참조), `supersedes_claim_id`(문자열, nullable, claim 버전 체인용), `derived_from`(원본 claim_id 배열, 없으면 빈 배열), `created_at`(ISO 8601 문자열), `last_verified_at`(ISO 8601 문자열), `created_by`(생성 주체 식별자 문자열).
4. THE Claim_DB SHALL 각 Evidence 객체에 다음 필드를 포함한다: `source_document_id`(S3 키 또는 문서 식별자 문자열), `source_chunk`(원본 문서에서 정확히 인용한 짧은 발췌 문자열, 10~1000자), `page_number`(페이지 번호 정수, 없으면 null), `extraction_date`(ISO 8601 문자열), `source_type`(문자열: `"md"`, `"pdf"`, `"rtl"`, `"csv"` 중 하나), `source_path`(파일 내부 위치 문자열), `line_start`(정수, nullable, md/rtl 라인 수준 앵커링용), `line_end`(정수, nullable), `chunk_hash`(문자열, source_chunk의 SHA-256 해시, 중복 제거용).
5. THE Terraform 구성 SHALL Claim_DB 테이블에 KMS CMK 암호화를 적용한다.
6. THE Terraform 구성 SHALL Claim_DB 테이블에 Point-in-Time Recovery(PITR)를 활성화한다.
7. THE Terraform 구성 SHALL Claim_DB 테이블의 과금 모드를 PAY_PER_REQUEST(온디맨드)로 설정한다.

### 요구사항 5: Claim DB 오염 방지 장치

**사용자 스토리:** DevOps 엔지니어로서, Claim DB에 저장되는 지식의 품질을 보장하기 위해, 근거 없는 claim 저장 방지, 상태 관리, 버전 고정, 충돌 감지, 동시성 제어 메커니즘이 구현되기를 원한다.

#### 인수 조건

1. WHEN 새로운 Claim이 Claim_DB에 저장될 때, THE Lambda_Handler SHALL `evidence` 배열이 최소 1개의 Evidence 객체를 포함하는지 검증하며, 빈 배열이면 저장을 거부하고 HTTP 400 응답을 반환한다.
2. THE Lambda_Handler SHALL Claim 생성 시 `status`를 `draft`로 초기화하며, `draft` → `verified`, `draft` → `deprecated`, `verified` → `conflicted`, `verified` → `deprecated`, `conflicted` → `verified`, `conflicted` → `deprecated` 전이만 허용한다.
3. IF 허용되지 않은 상태 전이가 요청되면, THEN THE Lambda_Handler SHALL HTTP 409 응답과 함께 현재 상태와 요청된 상태를 포함한 에러 메시지를 반환한다.
4. WHEN 기존 Claim이 업데이트될 때, THE Lambda_Handler SHALL 새로운 version 번호를 자동 증가시키고, 이전 version의 레코드를 유지하여 버전 이력을 보존한다.
5. WHEN 새로운 Claim이 저장될 때, THE Lambda_Handler SHALL 동일 topic 내 기존 `verified` 상태 claim들과 statement를 비교하여 Contradiction_Score를 계산하며, Contradiction_Score가 0.7 이상이면 기존 claim의 status를 `conflicted`로 변경하고 새 claim의 `derived_from`에 충돌 claim_id를 기록한다.
6. THE Lambda_Handler SHALL Claim의 `confidence` 값이 0.0 이상 1.0 이하 범위인지 검증하며, 범위를 벗어나면 저장을 거부하고 HTTP 400 응답을 반환한다.
7. THE Lambda_Handler SHALL Claim의 `topic` 값이 비어있지 않고 계층적 형식(슬래시 구분, 예: `ucie/phy/ltssm`)을 따르는지 검증한다.
8. WHEN Claim의 status가 `deprecated`로 변경될 때, THE Lambda_Handler SHALL 해당 claim을 `derived_from`으로 참조하는 모든 하위 claim의 `status`를 `conflicted`로 변경하고 CloudWatch에 경고 로그를 기록한다.
9. THE Lambda_Handler SHALL 모든 Claim_DB 쓰기 작업(PutItem, UpdateItem)에 optimistic locking을 적용하여 `ConditionExpression='version = :expected_version'`을 사용한다.
10. IF Claim_DB 쓰기 작업에서 `ConditionalCheckFailedException`이 발생하면, THEN THE Lambda_Handler SHALL 최신 version을 다시 읽어 업데이트를 재적용하며, 최대 3회 재시도한다.

### 요구사항 6: 문서 Ingestion 분리 및 Topic/Variant/Version 구조화

**사용자 스토리:** DevOps 엔지니어로서, 기존 md archive 문서를 topic, variant, version, source 기준으로 분리하여 ingestion하고 싶다. 이를 통해 동일 주제의 다른 버전/변형 문서를 구분하여 검색할 수 있기를 원한다.

#### 인수 조건

1. THE Lambda_Handler SHALL 문서 업로드 시 `topic`(주제 식별자), `variant`(변형 식별자, 선택적), `doc_version`(문서 버전, 선택적) 파라미터를 수용한다.
2. WHEN 문서가 `topic` 파라미터와 함께 업로드되면, THE Lambda_Handler SHALL 메타데이터 파일에 `topic`, `variant`(기본값 `"default"`), `doc_version`(기본값 `"1.0"`) 필드를 추가한다.
3. THE Lambda_Handler SHALL 동일 topic + variant 조합에 대해 새로운 doc_version이 업로드되면, 이전 버전의 메타데이터에 `superseded_by` 필드를 추가하여 최신 버전의 S3 키를 기록한다.
4. WHEN 질의 요청에 `topic` 필터가 포함되면, THE Lambda_Handler SHALL 해당 topic과 일치하는 문서만 대상으로 검색을 수행하며, 기본적으로 최신 doc_version의 문서를 우선 반환한다.
5. THE Lambda_Handler SHALL 문서 메타데이터에 `source`(원본 출처) 필드를 포함하며, 허용 값은 `"archive_md"`, `"rtl_parsed"`, `"codebeamer"`, `"manual_upload"`, `"system_generated"`이다.
6. THE Lambda_Handler SHALL 기존 `documents/` 접두사의 md 파일에 대해 topic 자동 추출을 지원하며, 파일 경로와 파일명에서 topic을 유추한다 (예: `documents/soc/ucie/phy_spec.md` → topic: `ucie/phy`).

### 요구사항 7: Claim 생성 및 Ingestion 파이프라인

**사용자 스토리:** DevOps 엔지니어로서, archive 문서를 claim 단위로 재파싱하여 statement + evidence + status 구조로 Claim_DB에 저장하고 싶다. 이를 통해 문서 단위가 아닌 지식 단위로 검색과 검증이 가능해지기를 원한다.

#### 인수 조건

1. WHEN 관리자가 `ingest_claims` 액션을 Lambda Event 비동기 호출로 실행하면, THE Lambda_Handler SHALL 지정된 S3 접두사의 문서를 읽어 Bedrock Foundation_Model을 사용하여 claim 단위로 분해한다.
2. THE Lambda_Handler SHALL 각 문서에서 추출된 claim에 대해 다음을 생성한다: `topic`(문서 경로 및 내용에서 추출), `statement`(소스에서 도출된 정규화된 1문장 사실 진술, LLM이 명확성을 위해 재구성 가능, 10~500자), `evidence`(원본 문서 참조 + `source_chunk`는 원본 문서의 정확한 인용 발췌, 10~1000자), `confidence`(LLM이 평가한 확신도 0.0~1.0).
3. THE Lambda_Handler SHALL 추출된 각 claim을 Claim_DB에 `status: draft`, `version: 1`로 저장한다.
4. THE Lambda_Handler SHALL 1회 요청당 최대 100건의 문서를 처리하며, 미처리 문서가 남아있으면 응답에 `has_more: true`와 `continuation_token`을 포함한다.
5. IF 개별 문서의 claim 추출 중 LLM 호출이 실패하면, THEN THE Lambda_Handler SHALL 해당 문서를 건너뛰고 에러를 CloudWatch에 기록하며, 나머지 문서의 처리를 계속한다.
6. THE Lambda_Handler SHALL claim 추출 시 LLM에 전달하는 프롬프트에 다음 지시를 포함한다: `statement`는 소스에서 도출된 정규화된 1문장 사실 진술로 LLM이 명확성을 위해 재구성할 수 있으며, `evidence.source_chunk`는 원본 문서의 정확한 인용(verbatim excerpt)이어야 한다. 이를 통해 Source_of_Truth_Layer의 무결성을 보장한다.
7. THE Lambda_Handler SHALL 추출 완료 후 처리된 문서 수(`documents_processed`), 생성된 claim 수(`claims_created`), 실패한 문서 수(`documents_failed`)를 응답에 포함한다.

### 요구사항 8: MCP Tool 분리 (Phase 3 작업형 도구)

**사용자 스토리:** 반도체 설계 엔지니어로서, Obot 채팅에서 단순 질의 외에 archive 검색, 근거 조회, 검증된 claim 조회 등 목적별 전용 도구를 사용하여, 더 정확하고 구조화된 답변을 받고 싶다.

#### 인수 조건

1. THE MCP_Bridge SHALL `search_archive` 도구를 제공하며, 입력으로 `query`(필수 문자열), `topic`(선택적 문자열), `source`(선택적 문자열), `max_results`(선택적 정수, 기본값 5)를 수용하고, 기존 Bedrock_KB 검색 결과를 topic/source 필터와 함께 반환한다.
2. THE MCP_Bridge SHALL `get_evidence` 도구를 제공하며, 입력으로 `claim_id`(필수 문자열)를 수용하고, 해당 claim의 evidence 배열(source_document_id, source_chunk, page_number, extraction_date, source_type, source_path, line_start, line_end, chunk_hash)을 반환한다.
3. THE MCP_Bridge SHALL `list_verified_claims` 도구를 제공하며, 입력으로 `topic`(필수 문자열)을 수용하고, 해당 topic의 모든 `verified` 상태 claim 목록과 각 claim의 confidence, last_verified_at을 반환한다.
4. THE Lambda_Handler SHALL 각 MCP Tool 요청에 대응하는 API 엔드포인트를 제공한다: `POST /rag/search-archive`, `POST /rag/get-evidence`, `POST /rag/list-verified-claims`.
5. WHEN MCP Tool 요청이 잘못된 파라미터를 포함하면, THE Lambda_Handler SHALL HTTP 400 응답과 함께 누락/잘못된 파라미터를 명시하는 에러 메시지를 반환한다.
6. THE MCP_Bridge SHALL 각 도구의 응답에 `execution_time_ms`(실행 시간)를 포함하여 성능 모니터링을 지원한다.

### 요구사항 9: Verification Pipeline

**사용자 스토리:** 반도체 설계 엔지니어로서, 질의에 대한 답변이 검증된 claim에 기반하고, 각 답변에 근거 문서와 검증 상태가 첨부되어, 답변의 신뢰성을 즉시 판단할 수 있기를 원한다.

#### 인수 조건

1. WHEN 사용자가 질의를 전송하면, THE Lambda_Handler SHALL 다음 8단계 Verification_Pipeline을 순차적으로 실행한다: (1) 질문 수신, (2) topic 식별, (3) Claim_DB에서 관련 claim 검색, (4) 각 claim의 evidence 근거 추적, (5) claim 간 충돌 검사, (6) claim 버전 확인(최신 version만 사용), (7) Foundation_Model을 사용하여 답변 생성, (8) 사용된 claim의 evidence를 답변에 첨부.
2. THE Lambda_Handler SHALL topic 식별 단계에서 사용자 질의를 Foundation_Model에 전달하여 관련 topic 목록(최대 3개)을 추출한다.
3. THE Lambda_Handler SHALL claim 검색 단계에서 Claim_DB의 `topic-index` GSI를 사용하여 `status`가 `verified`인 claim만 조회하여 답변 생성 컨텍스트로 사용한다.
4. THE Lambda_Handler SHALL 충돌 검사 단계에서 식별된 동일 topic에 대해 별도 쿼리를 실행하여 `status`가 `conflicted`인 claim이 존재하는지 확인하고, 존재하면 답변에 "일부 정보에 충돌이 감지되었습니다" 경고 메시지를 포함한다.
5. THE Lambda_Handler SHALL 답변 생성 단계에서 조회된 verified claim의 statement와 evidence를 Foundation_Model의 컨텍스트로 전달하여 답변을 생성한다.
6. THE Lambda_Handler SHALL 답변 응답에 `verification_metadata` 객체를 포함하며, 해당 객체에는 `claims_used`(사용된 claim_id 배열), `topics_identified`(식별된 topic 배열), `has_conflicts`(충돌 존재 여부 불리언), `pipeline_execution_time_ms`(파이프라인 실행 시간)를 포함한다.
7. IF Claim_DB에 관련 claim이 존재하지 않으면, THEN THE Lambda_Handler SHALL 기존 Bedrock_KB 검색으로 폴백하여 답변을 생성하고, `verification_metadata.fallback`을 `true`로 설정한다.
8. THE Lambda_Handler SHALL Verification_Pipeline의 각 단계 실행 시간을 CloudWatch에 구조화 로그로 기록한다.
9. WHEN 질의 요청에 `variant` 파라미터가 포함되면, THE Lambda_Handler SHALL claim 검색 단계에서 `topic-variant-index` GSI를 사용하여 해당 variant의 claim만 필터링하여 조회한다.

### 요구사항 10: MCP Tool 확장 (Phase 4 문서 생성 도구)

**사용자 스토리:** 반도체 설계 엔지니어로서, 검증된 claim을 기반으로 HDD(Hardware Design Description) 섹션을 자동 생성하고, 마크다운 형식으로 출판할 수 있기를 원한다.

#### 인수 조건

1. THE MCP_Bridge SHALL `generate_hdd_section` 도구를 제공하며, 입력으로 `topic`(필수 문자열), `section_title`(필수 문자열), `include_evidence`(선택적 불리언, 기본값 true)를 수용한다.
2. WHEN `generate_hdd_section`이 호출되면, THE Lambda_Handler SHALL 해당 topic의 `verified` 상태 claim을 조회하고, Foundation_Model을 사용하여 claim들을 논리적으로 구성한 HDD 섹션 마크다운을 생성한다.
3. THE Lambda_Handler SHALL 생성된 HDD 섹션에 각 claim의 evidence 출처를 각주 형식으로 포함한다 (include_evidence가 true인 경우).
4. THE MCP_Bridge SHALL `publish_markdown` 도구를 제공하며, 입력으로 `content`(필수 문자열), `filename`(필수 문자열), `topic`(선택적 문자열)을 수용하고, 마크다운 콘텐츠를 Seoul_S3의 `published/` 접두사에 저장한다.
5. WHEN `publish_markdown`이 호출되면, THE Lambda_Handler SHALL 저장된 마크다운 파일에 대해 메타데이터 파일을 자동 생성하며, `source`를 `"system_generated"`, `document_type`을 `"markdown"`, `generation_basis`를 `"verified_claims"`로 설정한다.
6. THE Lambda_Handler SHALL 생성된 HDD 섹션에 "이 문서는 AI가 검증된 claim을 기반으로 자동 생성하였습니다" 면책 조항을 포함한다.

### 요구사항 11: Cross-Check 파이프라인 및 Conflict Detection

**사용자 스토리:** DevOps 엔지니어로서, Claim DB에 저장되는 claim의 정확성을 다중 검증 단계로 보장하고, claim 간 충돌을 자동으로 감지하여, 지식 베이스의 일관성을 유지하고 싶다.

#### 인수 조건

1. WHEN 관리자가 `cross_check_claims` 액션을 Lambda Event 비동기 호출로 실행하면, THE Lambda_Handler SHALL 지정된 topic의 `draft` 상태 claim에 대해 Cross_Check_Pipeline을 실행한다.
2. THE Lambda_Handler SHALL Cross_Check_Pipeline의 1차 단계에서 원본 claim의 statement와 evidence를 Foundation_Model에 전달하여 claim의 정확성을 평가하고, 1차 검증 점수(0.0~1.0)를 산출한다.
3. THE Lambda_Handler SHALL Cross_Check_Pipeline의 2차 단계에서 1차와 다른 프롬프트 템플릿을 사용하여 동일 claim을 재검증하고, 2차 검증 점수를 산출한다.
4. THE Lambda_Handler SHALL Cross_Check_Pipeline의 3차 단계에서 rule-based checker를 실행하여 다음을 검증한다: evidence의 source_document_id가 실제 S3에 존재하는지, statement 길이가 10자 이상 500자 이하인지, topic 형식이 유효한지.
5. THE Lambda_Handler SHALL 1차, 2차, 3차 검증 결과를 종합하여 최종 Validation_Risk_Score를 계산한다: `validation_risk_score = 1.0 - (score_1 * 0.4 + score_2 * 0.4 + score_3 * 0.2)`.
6. WHEN 최종 Validation_Risk_Score가 0.3 미만이면, THE Lambda_Handler SHALL claim의 status를 `verified`로 변경하고 `confidence`를 `1.0 - validation_risk_score`로 업데이트한다.
7. WHEN 최종 Validation_Risk_Score가 0.3 이상 0.7 미만이면, THE Lambda_Handler SHALL claim의 status를 `draft`로 유지하고 CloudWatch에 수동 검토 필요 경고 로그를 기록한다.
8. WHEN 최종 Validation_Risk_Score가 0.7 이상이면, THE Lambda_Handler SHALL claim의 status를 `conflicted`로 변경하고 CloudWatch에 ERROR 로그를 기록한다.
9. THE Lambda_Handler SHALL Cross_Check_Pipeline 실행 결과를 응답에 포함한다: `claims_verified`(검증 완료 수), `claims_conflicted`(충돌 감지 수), `claims_pending`(수동 검토 필요 수), `total_processed`(총 처리 수).
10. THE Lambda_Handler SHALL 동일 topic 내에서 `verified` 상태 claim 간의 statement 유사도를 비교하여, 유사도가 0.9 이상이면 중복 claim으로 판정하고 최신 version만 `verified`로 유지하며 이전 version을 `deprecated`로 변경한다.

### 요구사항 12: 3계층 RAG 분리 아키텍처

**사용자 스토리:** 보안 엔지니어로서, 원본 문서(Source of Truth), 검증된 지식(Knowledge Archive), 사용자 인터페이스(Serving)가 명확히 분리되어, LLM이 원본 데이터를 직접 수정할 수 없고 각 계층의 접근 권한이 독립적으로 관리되기를 원한다.

#### 인수 조건

1. THE Source_of_Truth_Layer SHALL Seoul_S3와 RTL_S3_Bucket의 원본 문서를 불변(immutable) 상태로 유지하며, Lambda_Handler를 포함한 어떤 애플리케이션 코드도 원본 문서의 내용을 수정하는 S3 PutObject 호출을 수행하지 않는다 (메타데이터 파일 생성은 허용).
2. THE Terraform 구성 SHALL RTL_S3_Bucket(신규 생성 버킷)에 Object Lock(Governance 모드)을 활성화하여 원본 문서의 우발적 삭제/덮어쓰기를 방지한다. 기존 Seoul_S3 버킷에 대해서는 Object Lock 적용 가능성을 검증한 후 별도 마이그레이션 계획을 수립한다.
3. THE Verified_Knowledge_Layer SHALL Claim_DB를 통해서만 접근 가능하며, claim의 생성/수정/삭제는 Lambda_Handler의 전용 함수를 통해서만 수행된다.
4. THE Serving_Layer SHALL MCP_Bridge를 통해 사용자 요청을 수신하고, Verified_Knowledge_Layer(Claim_DB)와 Source_of_Truth_Layer(Bedrock_KB)를 조합하여 답변을 생성한다.
5. THE Lambda_Handler SHALL 각 계층 간 데이터 흐름을 단방향으로 유지한다: Source_of_Truth → Verified_Knowledge (claim 추출), Verified_Knowledge → Serving (답변 생성). 역방향 데이터 흐름(Serving → Source_of_Truth)은 허용하지 않는다.
6. THE Terraform 구성 SHALL 각 계층별 IAM 역할을 분리하여, RTL_Parser_Lambda는 RTL_S3_Bucket 읽기 + RTL_OpenSearch_Index 쓰기만, Lambda_Handler는 Seoul_S3 읽기/쓰기 + Claim_DB 읽기/쓰기 + Bedrock_KB 호출만 허용한다.

### 요구사항 13: 보안 및 네트워크 격리

**사용자 스토리:** 보안 엔지니어로서, 새로 추가되는 모든 리소스(RTL S3 버킷, RTL Parser Lambda, Claim DB)가 기존 폐쇄망 보안 정책을 준수하고, 최소 권한 원칙에 따라 접근이 제어되기를 원한다.

#### 인수 조건

1. THE RTL_Parser_Lambda SHALL 기존 BOS-AI Frontend VPC(10.10.0.0/16) 내에서 실행되며, VPC Endpoint를 통해서만 AWS 서비스(S3, OpenSearch, DynamoDB, Bedrock)에 접근한다.
2. THE Terraform 구성 SHALL RTL_Parser_Lambda용 IAM 역할을 생성하며, 다음 권한만 부여한다: RTL_S3_Bucket에 대한 GetObject/PutObject(`rtl-sources/*`, `rtl-parsed/*` 접두사), RTL_OpenSearch_Index에 대한 인덱싱 권한, CloudWatch Logs에 대한 쓰기 권한, KMS 키에 대한 Decrypt/GenerateDataKey 권한.
3. THE Terraform 구성 SHALL Claim_DB DynamoDB 테이블에 대한 접근을 Lambda_Handler IAM 역할로만 제한하며, PutItem/GetItem/UpdateItem/Query/Scan 권한을 부여한다.
4. THE Terraform 구성 SHALL 모든 신규 리소스에 KMS CMK 암호화를 적용한다: RTL_S3_Bucket(SSE-KMS), Claim_DB(DynamoDB 암호화), RTL_OpenSearch_Index(기존 OpenSearch_Collection 암호화 상속).
5. THE Terraform 구성 SHALL 모든 신규 Lambda 함수의 환경 변수에 KMS 암호화를 적용한다.
6. THE Terraform 구성 SHALL 모든 신규 리소스에 필수 태그(Project: BOS-AI, Environment: prod, ManagedBy: terraform, Layer: app)를 적용한다.
7. THE Lambda_Handler SHALL RTL 원본 소스 코드 전체를 로그에 기록하지 않으며, 파일명과 파싱 결과 요약만 로그에 포함한다.
8. IF VPC Endpoint를 통한 서비스 접근이 실패하면, THEN THE Lambda_Handler SHALL 연결 에러를 CloudWatch에 기록하고, 대체 네트워크 경로를 시도하지 않으며 즉시 에러 응답을 반환한다.
9. THE Terraform 구성 SHALL Lambda_Handler IAM 역할에 Explicit Deny 정책을 포함하여, Source_of_Truth 버킷(Seoul_S3의 `documents/*` 접두사 및 RTL_S3_Bucket의 `rtl-sources/*` 접두사)에 대한 `s3:PutObject` 및 `s3:DeleteObject` 작업을 명시적으로 거부한다. 이를 통해 prompt injection 공격으로 인한 원본 문서 변조를 인프라 수준에서 방지한다.

### 요구사항 14: Human Review Gate

**사용자 스토리:** DevOps 엔지니어로서, critical topic의 claim이 자동 검증만으로 출판되지 않도록, 사람의 승인 단계를 거쳐 지식 베이스의 신뢰성을 보장하고 싶다.

#### 인수 조건

1. THE Claim_DB SHALL 각 Claim 레코드에 다음 승인 관련 필드를 포함한다: `approval_status`(문자열: `"pending_review"`, `"approved"`, `"rejected"` 중 하나, 기본값 `"pending_review"`), `approved_by`(승인자 식별자 문자열, nullable), `approved_at`(ISO 8601 문자열, nullable).
2. WHEN Claim의 status가 `verified`로 변경될 때, THE Lambda_Handler SHALL `approval_status`를 `"pending_review"`로 설정한다.
3. THE Lambda_Handler SHALL `approve_claim` 액션을 제공하며, 입력으로 `claim_id`(필수), `version`(필수), `approved_by`(필수) 파라미터를 수용하고, `approval_status`를 `"approved"`로, `approved_by`와 `approved_at`을 설정한다.
4. THE Lambda_Handler SHALL `reject_claim` 액션을 제공하며, 입력으로 `claim_id`(필수), `version`(필수), `rejected_by`(필수), `rejection_reason`(선택적) 파라미터를 수용하고, `approval_status`를 `"rejected"`로 설정한다.
5. WHEN `publish_markdown` 도구가 critical topic의 claim을 사용하여 문서를 생성할 때, THE Lambda_Handler SHALL `approval_status`가 `"approved"`인 claim만 사용한다.
6. THE Claim_DB SHALL 각 Claim 레코드에 `publishable` 계산 필드를 지원한다: `publishable`은 `status`가 `verified`이고 `approval_status`가 `"approved"`인 경우에만 `true`이다.
7. IF `approval_status`가 `"pending_review"` 또는 `"rejected"`인 claim이 critical topic 문서 생성에 사용되려 하면, THEN THE Lambda_Handler SHALL HTTP 403 응답과 함께 승인 필요 메시지를 반환한다.

### 요구사항 15: Operational KPI Metrics

**사용자 스토리:** DevOps 엔지니어로서, Claim DB 기반 RAG 시스템의 운영 상태를 실시간으로 모니터링하고, 주요 KPI 지표를 CloudWatch 대시보드에서 확인하여 시스템 건강도를 파악하고 싶다.

#### 인수 조건

1. THE Lambda_Handler SHALL 다음 운영 KPI 메트릭을 CloudWatch 커스텀 네임스페이스 `BOS-AI/ClaimDB`에 발행한다: `ClaimIngestionSuccessRate`(claim ingestion 성공률), `ClaimVerificationPassRate`(claim 검증 통과율), `ContradictionDetectionRate`(모순 감지율), `BedrockKBFallbackRate`(Bedrock_KB 폴백 비율), `AvgEvidenceCountPerAnswer`(답변당 평균 evidence 수), `StaleClaimRatio`(30일 이상 미검증 claim 비율), `TopicCoverageRatio`(topic 커버리지 비율).
2. WHEN `ingest_claims` 액션이 완료될 때, THE Lambda_Handler SHALL `ClaimIngestionSuccessRate` 메트릭을 `(claims_created / (claims_created + documents_failed)) * 100` 공식으로 계산하여 발행한다.
3. WHEN `cross_check_claims` 액션이 완료될 때, THE Lambda_Handler SHALL `ClaimVerificationPassRate` 메트릭을 `(claims_verified / total_processed) * 100` 공식으로 계산하여 발행하고, `ContradictionDetectionRate`를 `(claims_conflicted / total_processed) * 100` 공식으로 계산하여 발행한다.
4. WHEN Verification_Pipeline이 Bedrock_KB 폴백을 실행할 때, THE Lambda_Handler SHALL `BedrockKBFallbackRate` 메트릭을 증가시킨다.
5. WHEN Verification_Pipeline이 답변을 생성할 때, THE Lambda_Handler SHALL 사용된 claim의 evidence 수 평균을 `AvgEvidenceCountPerAnswer` 메트릭으로 발행한다.
6. THE Lambda_Handler SHALL `StaleClaimRatio` 메트릭을 계산하기 위해, `last_verified_at`이 현재 시점으로부터 30일 이상 경과한 `verified` 상태 claim의 비율을 주기적으로(질의 처리 시 또는 별도 스케줄) 산출하여 발행한다.
7. THE Lambda_Handler SHALL `TopicCoverageRatio` 메트릭을 계산하기 위해, `verified` 상태 claim이 존재하는 고유 topic 수를 전체 등록된 topic 수로 나눈 비율을 발행한다.
8. THE Terraform 구성 SHALL CloudWatch 커스텀 네임스페이스 `BOS-AI/ClaimDB`에 대한 Lambda_Handler의 `cloudwatch:PutMetricData` 권한을 IAM 정책에 포함한다.
