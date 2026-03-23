# 요구사항 문서: RAG 검색 성능 최적화

## 소개

BOS-AI Private RAG 시스템의 검색 품질을 단계적으로 개선하기 위한 최적화 기능이다. 현재 시스템은 Bedrock Knowledge Base의 기본 시맨틱 검색만 사용하고 있어, RTL 변수명(HADDR, BLK_UCIE 등) 같은 기술 키워드 매칭이 부정확하고, 문서 메타데이터 기반 필터링이 불가능하며, 검색 결과의 관련성 평가가 어렵다. 본 기능은 Hybrid Search 활성화, 메타데이터 자동 부착, 검색 결과 품질 모니터링을 Phase 1으로 구현하고, 향후 Custom Chunking(Phase 2)과 HyDE/Query Transformation(Phase 3)으로 확장한다.

## 용어집

- **Lambda_Handler**: Seoul VPC에 배포된 `lambda-document-processor-seoul-prod` Lambda 함수로, 문서 업로드/삭제/질의 처리를 담당하는 핵심 컴포넌트
- **Bedrock_KB**: AWS Bedrock Knowledge Base(ID: FNNOP3VBZV)로, 문서 임베딩 저장 및 검색-생성(Retrieve and Generate)을 수행하는 서비스
- **OpenSearch_Collection**: Virginia 리전의 OpenSearch Serverless 벡터 컬렉션(ID: iw3pzcloa0en8d90hh7)으로, 임베딩 벡터를 저장하고 검색하는 벡터 데이터베이스
- **Hybrid_Search**: 시맨틱 검색(벡터 유사도)과 키워드 검색(텍스트 매칭)을 결합한 검색 방식으로, Bedrock KB의 `searchType: HYBRID` 파라미터로 활성화
- **Metadata_File**: S3에 문서와 함께 저장되는 `.metadata.json` 파일로, Bedrock KB가 문서 필터링에 사용하는 속성(팀, 카테고리, 문서 유형 등)을 포함
- **MCP_Bridge**: 온프레미스 Obot 서버(192.128.20.241)에서 실행되는 Node.js MCP SSE 브릿지 서버로, 사용자 질의를 API Gateway를 통해 Lambda_Handler로 전달
- **Seoul_S3**: 서울 리전 S3 버킷(bos-ai-documents-seoul-v3)으로, 문서 업로드의 최초 저장소
- **Virginia_S3**: 버지니아 리전 S3 버킷(bos-ai-documents-us)으로, 크로스 리전 복제를 통해 Seoul_S3의 문서를 수신하며 Bedrock_KB의 데이터 소스로 사용
- **Foundation_Model**: Bedrock에서 응답 생성에 사용하는 Claude 3.5 Haiku 모델(us.anthropic.claude-3-5-haiku-20241022-v1:0)
- **Retrieval_Config**: `retrieve_and_generate` API 호출 시 전달하는 검색 설정 객체로, 검색 유형, 필터, 결과 수 등을 제어

## 요구사항

### 요구사항 1: Hybrid Search 활성화

**사용자 스토리:** 반도체 설계 엔지니어로서, RTL 변수명이나 블록명 같은 정확한 기술 키워드로 검색할 때도 관련 문서를 찾을 수 있도록, 시맨틱 검색과 키워드 검색이 결합된 Hybrid Search를 사용하고 싶다.

#### 인수 조건

1. WHEN 사용자가 질의를 전송하면, THE Lambda_Handler SHALL `retrieve_and_generate` API 호출 시 `retrieveAndGenerateConfiguration.knowledgeBaseConfiguration.retrievalConfiguration.vectorSearchConfiguration.searchType`을 환경 변수 `SEARCH_TYPE`에서 읽어 설정하며, 해당 환경 변수가 없을 경우 기본값 `HYBRID`를 사용한다.
2. WHEN 사용자가 질의를 전송하면, THE Lambda_Handler SHALL `retrievalConfiguration.vectorSearchConfiguration.numberOfResults`를 환경 변수 `SEARCH_RESULTS_COUNT`에서 읽어 정수로 변환하여 설정하며, 해당 환경 변수가 없을 경우 기본값 5를 사용한다.
3. THE Lambda_Handler SHALL `retrieve_and_generate` 응답에서 `citations` 내 각 `retrievedReferences`의 관련도 점수를 추출하여 응답 JSON의 `citations[].references[].score` 필드에 포함한다.
4. IF `retrieve_and_generate` API 호출이 `ValidationException`을 반환하면, THEN THE Lambda_Handler SHALL 에러 메시지와 함께 HTTP 400 응답을 반환하고 CloudWatch에 에러 로그를 기록한다.
5. IF `retrieve_and_generate` API 호출이 `ThrottlingException`을 반환하면, THEN THE Lambda_Handler SHALL 에러 메시지와 함께 HTTP 429 응답을 반환하고 CloudWatch에 경고 로그를 기록한다.

### 요구사항 2: Hybrid Search Terraform 구성

**사용자 스토리:** DevOps 엔지니어로서, Hybrid Search 관련 설정을 Terraform 변수로 관리하여 환경별로 검색 파라미터를 일관되게 배포하고 싶다.

#### 인수 조건

1. THE Terraform 구성 SHALL `variables.tf`에 `search_type` 변수를 `string` 타입으로 정의하고 기본값을 `"HYBRID"`로 설정하며, 변수 설명에 허용 값(`HYBRID`, `SEMANTIC`)을 명시한다.
2. THE Terraform 구성 SHALL `variables.tf`에 `search_results_count` 변수를 `number` 타입으로 정의하고 기본값을 `5`로 설정한다.
3. THE Terraform 구성 SHALL Lambda 함수의 환경 변수에 `SEARCH_TYPE`과 `SEARCH_RESULTS_COUNT`를 추가하여 `search_type` 변수와 `search_results_count` 변수의 값을 전달한다.
4. THE Terraform 구성 SHALL `search_type` 변수에 `validation` 블록을 추가하여 값이 `HYBRID` 또는 `SEMANTIC`인 경우에만 허용한다.

### 요구사항 3: 문서 업로드 시 메타데이터 자동 생성

**사용자 스토리:** 반도체 설계 엔지니어로서, 문서를 업로드할 때 팀명과 카테고리 정보가 자동으로 메타데이터에 기록되어, 나중에 특정 팀이나 카테고리로 검색 결과를 필터링할 수 있도록 하고 싶다.

#### 인수 조건

1. WHEN 단일 파일 업로드가 `confirm_upload`를 통해 완료되면, THE Lambda_Handler SHALL 해당 S3 객체와 동일 경로에 `{원본파일명}.metadata.json` 파일을 Seoul_S3에 생성한다.
2. THE Lambda_Handler SHALL Metadata_File에 다음 필드를 포함한다: `metadataAttributes` 객체 내에 `team`(문자열), `category`(문자열), `document_type`(문자열), `upload_date`(ISO 8601 형식 문자열).
3. WHEN 업로드 요청에 `team` 또는 `category` 값이 포함되지 않으면, THE Lambda_Handler SHALL 해당 필드를 빈 문자열(`""`)로 설정하여 Metadata_File을 생성한다.
4. WHEN 압축 파일 해제(`process_extraction`)를 통해 개별 파일이 Seoul_S3에 업로드되면, THE Lambda_Handler SHALL 각 개별 파일에 대해 Metadata_File을 생성하며, `team`과 `category`는 압축 해제 요청 시 전달된 값을 사용한다.
5. THE Lambda_Handler SHALL Metadata_File의 `document_type` 값을 파일 확장자 기반으로 결정한다: `.pdf`는 `"pdf"`, `.txt`는 `"text"`, `.md`는 `"markdown"`, 그 외는 `"other"`.
6. THE Lambda_Handler SHALL Metadata_File을 `Content-Type: application/json`과 `UTF-8` 인코딩으로 S3에 저장한다.
7. WHEN Metadata_File 생성이 완료되면, THE Lambda_Handler SHALL 메타데이터 생성 후 즉시 KB Sync를 fire-and-forget으로 트리거하며, CRR 복제가 완료되지 않은 경우 다음 KB Sync 시 자연 반영된다 (Eventual Consistency 모델).

### 요구사항 4: 메타데이터 기반 검색 필터링

**사용자 스토리:** 반도체 설계 엔지니어로서, 특정 팀의 문서나 특정 카테고리의 문서만 대상으로 검색하여, 더 정확한 답변을 얻고 싶다.

#### 인수 조건

1. WHEN 질의 요청에 `filter` 객체가 포함되면, THE Lambda_Handler SHALL `retrieveAndGenerateConfiguration.knowledgeBaseConfiguration.retrievalConfiguration.vectorSearchConfiguration.filter`에 해당 필터 조건을 Bedrock_KB 필터 구문으로 변환하여 전달한다.
2. THE Lambda_Handler SHALL `filter` 객체 내 `team` 필드가 존재하면 `{"equals": {"key": "team", "value": "<team값>"}}` 형식의 Bedrock_KB 필터를 생성한다.
3. THE Lambda_Handler SHALL `filter` 객체 내 `category` 필드가 존재하면 `{"equals": {"key": "category", "value": "<category값>"}}` 형식의 Bedrock_KB 필터를 생성한다.
4. WHEN `filter` 객체에 `team`과 `category`가 모두 존재하면, THE Lambda_Handler SHALL 두 조건을 `{"andAll": [...]}` 연산자로 결합하여 전달한다.
5. WHEN 질의 요청에 `filter` 객체가 포함되지 않으면, THE Lambda_Handler SHALL 필터 없이 전체 문서를 대상으로 검색을 수행한다.

### 요구사항 5: 검색 응답 구조 개선

**사용자 스토리:** 반도체 설계 엔지니어로서, 검색 결과에 출처 문서의 상세 정보(파일명, 관련도 점수)가 포함되어, 답변의 신뢰성을 판단할 수 있도록 하고 싶다.

#### 인수 조건

1. THE Lambda_Handler SHALL 질의 응답 JSON에 `answer`(문자열), `citations`(배열), `metadata`(객체) 필드를 포함한다.
2. THE Lambda_Handler SHALL `citations` 배열의 각 항목에 `text`(인용 텍스트), `references`(배열) 필드를 포함하며, 각 `references` 항목에는 `uri`(S3 URI), `score`(관련도 점수, 숫자 또는 null) 필드를 포함한다.
3. THE Lambda_Handler SHALL `metadata` 객체에 `search_type`(사용된 검색 유형), `results_count`(설정된 검색 결과 수), `query_length`(질의 문자 수) 필드를 포함한다.
4. THE Lambda_Handler SHALL 기존 응답 형식과의 하위 호환성을 유지하여, `answer`와 `citations` 필드의 기본 구조를 변경하지 않는다.

### 요구사항 6: MCP Bridge 필터 파라미터 전달

**사용자 스토리:** 반도체 설계 엔지니어로서, Obot 채팅에서 팀명이나 카테고리를 지정하여 검색 범위를 좁힐 수 있도록, MCP Bridge가 필터 파라미터를 지원하길 원한다.

#### 인수 조건

1. THE MCP_Bridge SHALL `rag_query` 도구의 입력 스키마에 `team`(선택적 문자열)과 `category`(선택적 문자열) 파라미터를 추가한다.
2. WHEN `team` 또는 `category` 파라미터가 제공되면, THE MCP_Bridge SHALL API Gateway 호출 시 요청 본문의 `filter` 객체에 해당 값을 포함하여 전달한다.
3. WHEN `team`과 `category` 파라미터가 모두 제공되지 않으면, THE MCP_Bridge SHALL 요청 본문에 `filter` 객체를 포함하지 않는다.

### 요구사항 7: 검색 품질 로깅 및 모니터링

**사용자 스토리:** DevOps 엔지니어로서, Hybrid Search 활성화 전후의 검색 품질 변화를 측정하고, 검색 성능 이슈를 조기에 감지할 수 있도록 모니터링 체계를 갖추고 싶다.

#### 인수 조건

1. WHEN 질의가 처리되면, THE Lambda_Handler SHALL CloudWatch에 구조화된 로그를 기록하며, 로그에는 `query_length`(질의 문자 수), `search_type`(검색 유형), `citation_count`(인용 수), `response_time_ms`(응답 시간 밀리초), `has_filter`(필터 사용 여부) 필드를 포함한다.
2. WHEN 질의 결과에 인용(`citations`)이 0건이면, THE Lambda_Handler SHALL CloudWatch에 `no_citation_query` 메트릭 이름으로 경고 로그를 기록한다.
3. THE Terraform 구성 SHALL CloudWatch 로그 그룹의 메트릭 필터를 생성하여, `no_citation_query` 로그 패턴을 감지하고 `RAGNoCitationCount` 커스텀 메트릭으로 발행한다.
4. IF 질의 처리 중 `retrieve_and_generate` API 호출의 응답 시간이 30초를 초과하면, THEN THE Lambda_Handler SHALL CloudWatch에 `slow_query` 메트릭 이름으로 경고 로그를 기록한다.

### 요구사항 8: 기존 문서 메타데이터 일괄 생성

**사용자 스토리:** DevOps 엔지니어로서, Hybrid Search 활성화 전에 기존에 업로드된 문서들에 대해서도 메타데이터 파일을 일괄 생성하여, 모든 문서가 메타데이터 기반 필터링의 대상이 되도록 하고 싶다.

#### 인수 조건

1. WHEN 관리자가 `aws lambda invoke --invocation-type Event`로 `backfill_metadata` 액션을 호출하면, THE Lambda_Handler SHALL Seoul_S3의 `documents/` 접두사 아래 모든 객체를 조회하여, `.metadata.json` 파일이 없는 문서를 식별한다.
2. THE Lambda_Handler SHALL 식별된 각 문서에 대해 S3 키 경로에서 `team`과 `category`를 파싱하여(`documents/{team}/{category}/{filename}` 형식) Metadata_File을 생성하며, 경로에서 파싱할 수 없는 경우 빈 문자열(`""`)을 사용한다. `document_type`은 파일 확장자 기반으로 설정한다.
3. THE Lambda_Handler SHALL 일괄 생성 완료 후 처리된 문서 수(`processed_count`)와 건너뛴 문서 수(`skipped_count`)를 응답에 포함한다.
4. IF 개별 문서의 Metadata_File 생성 중 오류가 발생하면, THEN THE Lambda_Handler SHALL 해당 문서를 건너뛰고 오류를 로그에 기록하며, 나머지 문서의 처리를 계속한다.
5. THE Lambda_Handler SHALL 일괄 생성 완료 후 Bedrock_KB 동기화(`trigger_kb_sync`)를 1회 실행한다.
6. THE Lambda_Handler SHALL 1회 요청당 최대 500건의 문서를 처리하며, 미처리 문서가 남아있으면 응답에 `has_more: true`와 `continuation_token`(마지막 처리된 S3 키)을 포함하여 클라이언트가 후속 요청으로 나머지를 처리할 수 있도록 한다.
7. WHEN 요청에 `continuation_token`이 포함되면, THE Lambda_Handler SHALL 해당 토큰을 S3 `list_objects_v2`의 `StartAfter` 파라미터로 사용하여 이전 요청에서 중단된 지점부터 처리를 재개한다.
8. THE Lambda_Handler SHALL 처리 시작 시 경과 시간을 추적하고, Lambda 잔여 실행 시간(`context.get_remaining_time_in_millis()`)이 30초 미만이 되면 현재 처리를 중단하고 `has_more: true`와 `continuation_token`을 포함한 응답을 반환한다.
