# 요구사항 문서

## 개요

CodeBeamer ASPICE RAG 통합은 CodeBeamer에서 export한 문서(JSON, PDF)를 기존 업로드 엔드포인트 또는 벌크 업로드 방식을 통해 BOS-AI Private RAG 시스템에 등록하고, 업로드 시점에 ASPICE 프로세스 카테고리(MAN.3, SUP.1, SWE.1 등)를 메타데이터로 지정하여 검색 결과에 반환하는 기능입니다.

기존 문서 파이프라인(Seoul S3 → Cross-Region Replication → Virginia S3 → Bedrock KB → OpenSearch)을 확장하여, 업로드 시 ASPICE 카테고리 정보를 메타데이터로 매핑합니다. ASPICE 카테고리 매핑 정보는 시스템 설정(정적 매핑 테이블)으로 관리되며, 사용자가 업로드 시 ASPICE 카테고리를 지정하거나 CodeBeamer 문서의 메타데이터에서 추출합니다. 엔지니어는 자연어 질의 시 "SWE.1 요구사항 분석 관련 문서 보여줘"와 같이 ASPICE 프로세스 기준으로 검색할 수 있게 됩니다.

## 용어 정의

- **CodeBeamer**: 반도체 설계 프로젝트의 요구사항, 설계 스펙을 관리하는 ALM(Application Lifecycle Management) 도구
- **ASPICE**: Automotive SPICE — 자동차/반도체 소프트웨어 개발 프로세스 표준 (ISO/IEC 33002 기반)
- **ASPICE_Category**: ASPICE 프로세스 식별자 (예: MAN.3, SUP.1, SWE.1 등)
- **ASPICE_Category_Mapping**: ASPICE 프로세스 식별자와 프로세스 이름을 매핑하는 정적 설정 테이블 (시스템 설정으로 관리)
- **Upload_API**: 기존 RAG 업로드 엔드포인트 — API Gateway를 통해 Seoul S3에 문서를 업로드하는 REST API
- **Metadata_Enricher**: 업로드된 문서에 ASPICE 카테고리 메타데이터를 부착하는 처리 컴포넌트
- **RAG_Pipeline**: 기존 BOS-AI 문서 처리 파이프라인 (Seoul S3 → Cross-Region Replication → Virginia S3 → Bedrock KB → OpenSearch)
- **Document_Processor**: 기존 Lambda 함수 — S3 이벤트를 받아 head_object로 메타데이터를 읽고 문서를 청킹하여 Bedrock KB에 수집 요청
- **OpenSearch**: 벡터 검색 엔진 — 문서 임베딩과 메타데이터를 저장 (Virginia us-east-1)
- **Bedrock_KB**: AWS Bedrock Knowledge Base — 문서 임베딩 생성 및 검색 오케스트레이션 (Virginia us-east-1), .metadata.json 사이드카 파일 방식으로 메타데이터 필터링 지원
- **RAG_API**: 기존 API Gateway 엔드포인트 — 자연어 질의를 받아 검색 결과를 반환
- **Seoul_S3_Bucket**: 서울 리전 S3 버킷 (bos-ai-documents-seoul-v3) — 문서 업로드 대상, 크로스리전 복제 소스
- **Virginia_S3_Bucket**: 버지니아 리전 S3 버킷 — 크로스리전 복제 대상, Bedrock KB 데이터 소스
- **Bulk_Upload**: API Gateway/Lambda 용량 제한(API GW 10MB, Lambda 6MB)을 초과하는 대용량 문서를 위한 별도 업로드 방식
- **ASPICE_Metadata_Schema**: 문서에 부착되는 메타데이터 구조 (process_id, process_name, team, document_type, source_system, upload_timestamp 등)
- **Sync_Scheduler**: 정기적으로 CodeBeamer 문서 동기화를 트리거하는 EventBridge 스케줄러
- **CB_Collector**: CodeBeamer 문서 수집 Lambda 함수 — CodeBeamer API를 통해 문서를 가져오고 메타데이터를 추출

---

## 요구사항

### 요구사항 1: 업로드 시 ASPICE 메타데이터 정의

**사용자 스토리:** 반도체 엔지니어로서, 문서 업로드 시 ASPICE 메타데이터(팀, 카테고리, process_id)를 지정하고 싶습니다. 이를 통해 업로드 시점부터 각 문서가 ASPICE 프로세스 기반 검색을 위해 적절히 분류되기를 원합니다.

#### 수용 기준

1. 문서가 Upload_API를 통해 업로드될 때, Upload_API는 요청에서 다음 ASPICE 메타데이터 필드를 수용해야 한다: `team`, `category`, `process_id`, `process_name`, `document_type`.
2. Upload_API는 업로드를 수용하기 전에 `process_id` 필드가 ASPICE_Category_Mapping의 알려진 ASPICE_Category 식별자와 일치하는지 검증해야 한다.
3. `process_id`는 제공되었으나 `process_name`이 생략된 경우, Upload_API는 ASPICE_Category_Mapping에서 `process_name`을 자동으로 해석해야 한다.
4. 필수 메타데이터 필드(`team`, `process_id`)가 업로드 요청에서 누락된 경우, Upload_API는 누락된 필드를 나열하는 설명 메시지와 함께 HTTP 400 오류를 반환해야 한다.
5. 업로드가 수용될 때, Upload_API는 Seoul_S3_Bucket의 업로드된 문서에 ASPICE 메타데이터를 S3 객체 메타데이터로 저장해야 한다.
6. ASPICE_Category_Mapping은 ASPICE_Category 식별자를 전체 프로세스 이름 및 프로세스 그룹에 매핑하는 정적 설정 테이블(DynamoDB 또는 JSON 설정)로 유지되어야 한다.

---

### 요구사항 2: CodeBeamer 문서 수집 및 업로드

**사용자 스토리:** DevOps 엔지니어로서, CodeBeamer에서 JSON 또는 PDF 형식으로 문서를 export하고 RAG 시스템에 업로드하고 싶습니다. 이를 통해 최신 스펙 문서가 항상 검색 가능하기를 원합니다.

#### 수용 기준

1. Upload_API는 CodeBeamer에서 export한 JSON 형식의 문서를 주요 지원 형식으로 수용해야 한다.
2. Upload_API는 CodeBeamer에서 export한 PDF 형식의 문서를 보조 지원 형식으로 수용해야 한다.
3. JSON 형식의 CodeBeamer export가 업로드될 때, Document_Processor는 JSON 구조를 파싱하여 문서 콘텐츠, 항목 메타데이터 및 관계를 추출해야 한다.
4. PDF 형식의 CodeBeamer export가 업로드될 때, Document_Processor는 임베딩 생성을 위해 PDF에서 텍스트 콘텐츠를 추출해야 한다.
5. CodeBeamer API가 자동화된 export에 사용되는 경우, CB_Collector는 AWS Secrets Manager에 독점적으로 저장된 자격증명을 사용하여 CodeBeamer REST API를 통해 문서를 검색해야 한다.
6. CodeBeamer API가 HTTP 401 또는 403 오류를 반환하는 경우, CB_Collector는 인증 실패를 로깅하고 부분 쓰기 없이 동기화 작업을 중지해야 한다.
7. CodeBeamer API가 HTTP 404 오류를 반환하는 경우, CB_Collector는 누락된 문서 URL을 로깅하고 나머지 문서 처리를 계속해야 한다.
8. CodeBeamer API가 HTTP 429 오류를 반환하는 경우, CB_Collector는 30초 지연 후 요청을 재시도하고, 최대 3회 재시도 후 실패를 로깅하고 문서를 건너뛰어야 한다.

---

### 요구사항 3: ASPICE 메타데이터 부착 및 매핑

**사용자 스토리:** 반도체 엔지니어로서, 각 문서가 ASPICE 카테고리 메타데이터를 포함하기를 원합니다. 이를 통해 검색 중에 프로세스 영역별로 문서를 필터링하고 식별할 수 있기를 원합니다.

#### 수용 기준

1. ASPICE 메타데이터와 함께 문서가 업로드될 때, Metadata_Enricher는 문서에 다음 ASPICE_Metadata_Schema 필드를 부착해야 한다: `process_id` (예: "SWE.1"), `process_name` (예: "Software Requirements Analysis"), `team`, `document_type` (예: "Specification"), `source_system` (예: "CodeBeamer"), `upload_timestamp` (ISO 8601 UTC).
2. Metadata_Enricher는 ASPICE_Category_Mapping 정적 설정 테이블을 사용하여 ASPICE_Category 식별자를 전체 프로세스 이름으로 해석해야 한다.
3. ASPICE_Category 식별자가 ASPICE_Category_Mapping에 존재하지 않는 경우, Metadata_Enricher는 `process_name`을 "Unknown"으로 설정하고 인식되지 않은 식별자로 경고를 로깅해야 한다.
4. CodeBeamer JSON export가 메타데이터 필드에 ASPICE 카테고리 정보를 포함하는 경우, 업로더가 지정하지 않을 때 Metadata_Enricher는 문서 메타데이터에서 ASPICE_Category를 추출해야 한다(폴백).
5. Metadata_Enricher는 S3의 각 문서 옆에 `.metadata.json` 사이드카 파일을 생성해야 하며, 이는 Bedrock_KB 메타데이터 필터링 형식과 호환되어야 한다.

---

### 요구사항 4: S3 저장 및 크로스리전 복제 연동

**사용자 스토리:** DevOps 엔지니어로서, ASPICE 메타데이터가 포함된 업로드된 문서가 Seoul S3에 저장되고 자동으로 Virginia로 복제되기를 원합니다. 이를 통해 기존 RAG 파이프라인이 수정 없이 이를 처리하기를 원합니다.

#### 수용 기준

1. 메타데이터가 풍부해진 문서가 준비되면, Metadata_Enricher는 Seoul_S3_Bucket (bos-ai-documents-seoul-v3)의 지정된 S3 접두사(`codebeamer/aspice/{process_id}/`)에 문서를 업로드해야 한다.
2. Metadata_Enricher는 키 접두사 `x-amz-meta-aspice-*` (예: `x-amz-meta-aspice-process-id`, `x-amz-meta-aspice-process-name`, `x-amz-meta-aspice-team`)를 사용하여 ASPICE 메타데이터를 S3 객체 메타데이터로 저장해야 한다.
3. 문서가 Seoul_S3_Bucket에 업로드될 때, 기존 크로스리전 복제는 문서와 메타데이터를 자동으로 Virginia_S3_Bucket으로 복제해야 한다.
4. 복제된 문서가 Virginia_S3_Bucket에 도착할 때, 기존 Document_Processor는 기존 S3 이벤트 알림을 통해 트리거되어야 하며 head_object를 통해 ASPICE 메타데이터를 읽어야 한다.
5. Metadata_Enricher는 각 문서 옆에 `.metadata.json` 사이드카 파일을 업로드해야 하며, 이는 Bedrock_KB 메타데이터 필터링 형식의 ASPICE 메타데이터 필드를 포함해야 한다.
6. Metadata_Enricher는 CodeBeamer 문서 ID를 기반으로 결정론적 S3 객체 키를 사용하여 재업로드 시 중복 업로드를 방지해야 한다.
7. S3 업로드가 실패하는 경우, Metadata_Enricher는 문서 ID 및 S3 키와 함께 실패를 로깅하고 문서를 실패로 표시하기 전에 한 번 재시도해야 한다.

---

### 요구사항 5: 대용량 벌크 업로드 절차

**사용자 스토리:** DevOps 엔지니어로서, API Gateway/Lambda 페이로드 제한을 초과하는 대용량 문서를 위한 벌크 업로드 절차를 원합니다. 이를 통해 대용량 CodeBeamer export를 RAG 시스템에 수집할 수 있기를 원합니다.

#### 수용 기준

1. Bulk_Upload 절차는 API Gateway 페이로드 제한(10MB)과 Lambda 페이로드 제한(6MB)을 초과하는 문서 업로드를 지원해야 한다.
2. Bulk_Upload 절차는 Upload_API를 통한 S3 presigned URL 생성을 제공해야 하며, Seoul_S3_Bucket에 ASPICE 메타데이터가 S3 객체 메타데이터로 첨부된 직접 업로드를 허용해야 한다.
3. Presigned URL이 요청될 때, Upload_API는 presigned URL을 생성하기 전에 ASPICE 메타데이터 필드(`team`, `process_id`)를 검증해야 한다.
4. Bulk_Upload 절차는 VPN 연결을 통한 AWS CLI를 통한 직접 S3 업로드를 지원해야 하며, 지정된 S3 접두사(`codebeamer/aspice/{process_id}/`)와 ASPICE 메타데이터 헤더를 사용해야 한다.
5. Bulk_Upload 절차는 운영 실행 가이드에서 presigned URL 업로드 및 AWS CLI 직접 업로드 방법 모두에 대한 단계별 프로세스를 문서화해야 한다.
6. Bulk_Upload 절차를 통해 문서가 업로드될 때, 문서는 Upload_API를 통해 업로드된 문서와 동일한 S3 접두사 규칙 및 메타데이터 스키마를 따라야 한다.
7. Presigned URL 업로드가 URL 만료 기간 내에 완료되지 않는 경우, Upload_API는 새로운 presigned URL을 생성하도록 요구해야 한다.

---

### 요구사항 6: OpenSearch 메타데이터 인덱싱

**사용자 스토리:** 반도체 엔지니어로서, ASPICE 메타데이터가 OpenSearch에 인덱싱되기를 원합니다. 이를 통해 ASPICE 프로세스 카테고리별로 문서를 검색하고 필터링할 수 있기를 원합니다.

#### 수용 기준

1. 문서가 Bedrock_KB에 수집될 때, Document_Processor는 ASPICE 메타데이터 필드를 벡터 임베딩과 함께 OpenSearch의 문서 수준 메타데이터 필드로 전달해야 한다.
2. OpenSearch 인덱스는 ASPICE 문서에 대해 다음 메타데이터 필드를 포함해야 한다: `aspice_process_id` (keyword), `aspice_process_name` (keyword), `aspice_team` (keyword), `aspice_document_type` (keyword), `source_system` (keyword), `upload_timestamp` (date).
3. ASPICE 문서가 OpenSearch에 존재하는 동안, OpenSearch 인덱스는 `aspice_process_id` 필드를 카테고리 기반 필터링을 지원하는 필터링 가능한 keyword 필드로 유지해야 한다.
4. Document_Processor는 ASPICE 메타데이터가 없는 문서를 처리할 때 기존 비-ASPICE 문서 동작을 보존해야 한다.

---

### 요구사항 7: 검색 결과에 ASPICE 메타데이터 반환

**사용자 스토리:** 반도체 엔지니어로서, 검색 결과에 ASPICE 카테고리 정보가 포함되기를 원합니다. 이를 통해 문서를 열지 않고도 결과가 어느 프로세스 영역에 속하는지 즉시 식별할 수 있기를 원합니다.

#### 수용 기준

1. 검색 쿼리가 RAG_API에 제출될 때, RAG_API는 ASPICE 메타데이터가 있는 각 결과에 대해 검색 결과 페이로드에 ASPICE 메타데이터 필드(`process_id`, `process_name`, `team`, `document_type`, `source_system`)를 반환해야 한다.
2. 검색 쿼리에 ASPICE 카테고리 필터가 포함될 때(예: `filter: {aspice_process_id: "SWE.1"}`), RAG_API는 지정된 `aspice_process_id`와 일치하는 문서만 반환해야 한다.
3. 검색 결과에 ASPICE 메타데이터가 없는 경우, RAG_API는 해당 결과의 페이로드에서 ASPICE 메타데이터 필드를 생략해야 하며 null 값을 반환하지 않아야 한다.
4. RAG_API는 기준 응답 지연 시간과 비교하여 p95 응답 지연 시간을 100ms 이상 증가시키지 않으면서 ASPICE 메타데이터를 반환해야 한다.

---

### 요구사항 8: 정기 동기화 스케줄링

**사용자 스토리:** DevOps 엔지니어로서, CodeBeamer 문서가 일정에 따라 자동으로 재동기화되기를 원합니다. 이를 통해 RAG 시스템이 항상 최신 문서 버전을 반영하기를 원합니다.

#### 수용 기준

1. Sync_Scheduler는 기본 간격 24시간으로 구성 가능한 일정에 따라 CB_Collector를 트리거해야 한다.
2. 동기화 작업이 시작될 때, CB_Collector는 문서 체크섬을 이전에 저장된 체크섬과 비교해야 하며 콘텐츠가 변경된 문서만 재업로드해야 한다.
3. 동기화 작업이 이미 실행 중인 경우, Sync_Scheduler는 새로운 트리거를 건너뛰고 동시 동기화 충돌을 방지하기 위해 경고를 로깅해야 한다.
4. CB_Collector는 동기화 작업 상태(시작 시간, 종료 시간, 처리된 문서, 실패한 문서)를 DynamoDB 테이블에 저장하여 운영 가시성을 제공해야 한다.
5. 동기화 작업이 완료될 때, CB_Collector는 발견된 총 문서, 업데이트된 문서, 건너뛴 문서(변경 없음) 및 실패한 문서를 포함하는 요약을 로깅해야 한다.

---

### 요구사항 9: 보안 및 네트워크 격리

**사용자 스토리:** 보안 엔지니어로서, 모든 CodeBeamer API 호출 및 문서 업로드가 프라이빗 네트워크 내에 유지되기를 원합니다. 이를 통해 문서 콘텐츠가 공개 인터넷을 통과하지 않기를 원합니다.

#### 수용 기준

1. CB_Collector는 기존 BOS-AI Frontend VPC (10.10.0.0/16) 내에서 실행되어야 하며 Transit Gateway를 통한 온프레미스 VPN 연결을 통해서만 CodeBeamer 엔드포인트에 접근해야 한다.
2. CB_Collector는 기존 VPC Endpoints를 통해서만 AWS 서비스(S3, Secrets Manager, DynamoDB)에 접근해야 하며 인터넷 게이트웨이 또는 NAT 게이트웨이 접근을 요구하지 않아야 한다.
3. CB_Collector IAM 역할은 최소 권한 원칙을 따라야 하며 다음에 필요한 권한만 부여해야 한다: 지정된 접두사에 대한 S3 PutObject, 지정된 시크릿에 대한 Secrets Manager GetSecretValue, 동기화 상태 테이블에 대한 DynamoDB PutItem/GetItem.
4. 온프레미스 네트워크에 대한 VPN 연결을 사용할 수 없는 경우, CB_Collector는 연결 오류를 로깅하고 대체 네트워크 경로를 통한 자격증명 노출을 방지하기 위해 재시도 없이 동기화 작업을 중지해야 한다.
5. Bulk_Upload presigned URL은 특정 S3 접두사로 범위가 지정되어야 하며 생성 후 1시간 이내에 만료되어야 한다.
