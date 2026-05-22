# Bugfix Requirements Document

## Introduction

AOSS(OpenSearch Serverless)에서 Qdrant(EC2)로 벡터 DB를 전환한 후에도, 코드베이스 전반에 AOSS 잔류 의존성이 남아 있어 RTL 인덱싱/검색 파이프라인이 실패한다. RTL Parser Lambda(`handler.py`)의 핵심 함수는 Qdrant로 교체되었지만, Document Processor Lambda(`index.py`)의 일부 함수들이 여전히 AOSS SigV4 서명 방식으로 직접 호출을 시도하며, Lambda에서 Qdrant EC2(10.20.1.217:6333)로의 네트워크 경로가 열려있지 않아 인덱싱과 검색 모두 실패한다.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN RTL Parser Lambda가 Qdrant EC2(10.20.1.217:6333)에 인덱싱/검색 요청을 보낼 때 THEN the system이 네트워크 타임아웃으로 실패한다 (Lambda VPC → Qdrant EC2 간 VPC Peering/Route/SG 미설정)

1.2 WHEN Document Processor Lambda(`index.py`)의 `_get_pipeline_coverage()` 함수가 호출될 때 THEN the system이 RTL_OPENSEARCH_ENDPOINT(빈 값)를 확인하고 "RTL_OPENSEARCH_ENDPOINT not configured" 에러를 반환한다

1.3 WHEN Document Processor Lambda(`index.py`)의 이름 복구 함수(Source ②)가 `RTL_OPENSEARCH_ENDPOINT`를 조건으로 검색을 시도할 때 THEN the system이 AOSS 종료로 인해 해당 분기를 건너뛰어 이름 복구 정확도가 저하된다

1.4 WHEN 기존 AOSS에 인덱싱되었던 9465건의 RTL 데이터가 Qdrant에 없을 때 THEN the system이 검색 결과 0건을 반환한다

1.5 WHEN Terraform의 AOSS VPC Endpoint, SG, IAM 리소스가 비활성화(종료) 상태인데 코드에서 여전히 참조할 때 THEN the system이 불필요한 리소스 비용을 유발하거나 배포 시 에러를 발생시킨다

### Expected Behavior (Correct)

2.1 WHEN RTL Parser Lambda가 Qdrant EC2(10.20.1.217:6333)에 인덱싱/검색 요청을 보낼 때 THEN the system SHALL Lambda VPC에서 Qdrant EC2로의 네트워크 경로(VPC Peering + Route Table + Security Group)가 정상적으로 열려 요청이 성공한다

2.2 WHEN Document Processor Lambda(`index.py`)의 `_get_pipeline_coverage()` 함수가 호출될 때 THEN the system SHALL RTL Parser Lambda를 invoke하여 Qdrant 기반으로 파이프라인 커버리지를 조회한다 (AOSS 직접 호출 대신)

2.3 WHEN Document Processor Lambda(`index.py`)의 이름 복구 함수(Source ②)가 실행될 때 THEN the system SHALL RTL Parser Lambda invoke를 통해 Qdrant에서 검색하여 이름 복구를 수행한다 (RTL_OPENSEARCH_ENDPOINT 조건 의존 제거)

2.4 WHEN Qdrant 전환이 완료된 후 THEN the system SHALL 기존 9465건의 RTL 데이터를 재인덱싱하여 Qdrant에 적재하고, 검색 결과가 정상적으로 반환된다

2.5 WHEN Terraform 인프라가 배포될 때 THEN the system SHALL AOSS 관련 불필요한 리소스(VPC Endpoint, SG rule, IAM policy, KMS grant)를 비활성화/제거하고, Qdrant EC2에 대한 네트워크 설정(SG ingress 6333, Route)을 추가한다

### Unchanged Behavior (Regression Prevention)

3.1 WHEN RTL Parser Lambda가 S3 이벤트로 새 RTL 파일을 수신할 때 THEN the system SHALL CONTINUE TO 파싱 → 임베딩 → 인덱싱 파이프라인을 정상 수행한다

3.2 WHEN Document Processor Lambda가 `search-archive` API로 RTL 검색을 위임받을 때 THEN the system SHALL CONTINUE TO RTL Parser Lambda invoke를 통해 검색 결과를 반환한다

3.3 WHEN Neptune Graph DB에 Signal Path 데이터를 적재할 때 THEN the system SHALL CONTINUE TO Neptune 인덱싱이 정상 동작한다 (Neptune은 AOSS 전환과 무관)

3.4 WHEN Bedrock KB(Virginia)가 문서 임베딩/검색을 수행할 때 THEN the system SHALL CONTINUE TO Bedrock Knowledge Base의 기존 S3→KB 파이프라인이 영향받지 않는다

3.5 WHEN MCP 서버가 `search_rtl` 도구를 호출할 때 THEN the system SHALL CONTINUE TO API Gateway → Document Processor Lambda → RTL Parser Lambda 체인이 정상 동작한다
