# 요구사항 문서

## 소개

온프레미스 환경에서만 접근 가능한 완전 Private RAG API를 구축한다. 핵심 아키텍처 원칙은 **Frontend/Backend 분리**이다:

- **서울 Private RAG VPC (10.10.0.0/16) = Frontend**: 유저 접점. API Gateway, Lambda가 위치하며, 온프렘 사용자가 VPN을 통해 접근하는 유일한 진입점이다.
- **버지니아 Backend VPC (10.20.0.0/16) = Backend**: Bedrock, OpenSearch Serverless, S3가 위치하며, 유저의 직접 접근 없이 Frontend Lambda에서 VPC Peering을 통해서만 호출된다.

현재 서울 리전에 Logging VPC(10.200.0.0/16)와 Private RAG VPC(10.10.0.0/16)가 존재하며, 온프렘(192.128.0.0/16)에서 VPN → Transit Gateway를 통해 두 VPC에 연결이 완료된 상태이다. RAG Lambda(document-processor)는 현재 버지니아 VPC에 있으나, Frontend/Backend 분리 원칙에 따라 서울 Private RAG VPC로 이전해야 한다.

이 프로젝트는 Lambda 이전, Private API Gateway, Route53 Private Hosted Zone, Route53 Resolver 이전, 사내 DNS 조건부 포워딩을 통해 온프렘에서만 RAG API에 접근할 수 있는 Air-Gapped 환경을 구현한다. 이전에 사내 DNS에 Route53 Endpoint를 무조건 등록하여 SaaS 서비스 파일 업로드 오류가 발생한 경험이 있으므로, 조건부 포워딩을 반드시 적용하여 기존 서비스에 영향이 없도록 한다.

## 용어 정의

- **Private_RAG_VPC**: 서울 리전의 Private RAG 전용 VPC (vpc-0a118e1bf21d0c057, CIDR: 10.10.0.0/16). IGW 없음, Private 서브넷만 존재
- **Logging_VPC**: 서울 리전의 로깅 인프라 VPC (vpc-066c464f9c750ee9e, CIDR: 10.200.0.0/16). IGW 있음, Route53 Resolver 현재 위치
- **US_Backend_VPC**: 버지니아 리전의 백엔드 VPC (vpc-0ed37ff82027c088f, CIDR: 10.20.0.0/16). Lambda document-processor, VPC Endpoint 위치
- **Transit_Gateway**: 온프렘과 AWS VPC를 연결하는 Transit Gateway (tgw-0897383168475b532)
- **Private_API_Gateway**: VPC Endpoint를 통해서만 접근 가능한 Amazon API Gateway (REST API, Private 타입)
- **Route53_Resolver_Inbound**: 온프렘 DNS 서버에서 AWS 내부 도메인을 해석하기 위한 Route53 Resolver Inbound Endpoint
- **Route53_Resolver_Outbound**: AWS에서 온프렘 도메인을 해석하기 위한 Route53 Resolver Outbound Endpoint
- **Private_Hosted_Zone**: VPC에 연결된 Route53 Private Hosted Zone. 연결된 VPC 내부에서만 DNS 해석 가능
- **Conditional_Forwarding**: 사내 DNS 서버에서 특정 도메인(*.corp.bos-semi.com)에 대한 DNS 쿼리만 Route53 Resolver로 전달하는 설정
- **VPC_Endpoint_Execute_API**: Private API Gateway 호출을 위한 execute-api 서비스용 VPC Interface Endpoint
- **Document_Processor_Lambda**: RAG 문서 처리 Lambda 함수. 현재 버지니아 VPC에 배포되어 있으나, Frontend/Backend 분리 원칙에 따라 서울 Private_RAG_VPC로 이전 예정
- **Frontend_Layer**: 서울 Private_RAG_VPC에 위치하는 유저 접점 계층. API Gateway, Lambda가 포함되며, 온프렘에서 VPN을 통해 접근하는 유일한 진입점
- **Backend_Layer**: 버지니아 US_Backend_VPC에 위치하는 AI 서비스 계층. Bedrock, OpenSearch Serverless, S3가 포함되며, Frontend Lambda에서 VPC Peering을 통해서만 호출됨. 유저 직접 접근 불가
- **OnPrem_Network**: 온프레미스 네트워크 (CIDR: 192.128.0.0/16). VPN을 통해 Transit Gateway에 연결됨
- **Corp_Domain**: 사내 서브도메인 (corp.bos-semi.com). RAG API 도메인의 상위 도메인

## 요구사항

### 요구사항 1: Route53 Resolver Endpoint를 Private RAG VPC로 이전

**사용자 스토리:** 인프라 관리자로서, Route53 Resolver Endpoint를 Private_RAG_VPC로 이전하여, RAG 전용 VPC에서 DNS 해석이 가능하도록 하고 싶다.

#### 인수 조건

1. THE Route53_Resolver_Inbound SHALL 10.10.1.0/24 서브넷과 10.10.2.0/24 서브넷에 각각 하나의 IP 주소를 가지도록 Private_RAG_VPC에 생성된다
2. THE Route53_Resolver_Outbound SHALL 10.10.1.0/24 서브넷과 10.10.2.0/24 서브넷에 각각 하나의 IP 주소를 가지도록 Private_RAG_VPC에 생성된다
3. THE Route53_Resolver_Inbound SHALL DNS 쿼리(TCP/UDP 53 포트)를 OnPrem_Network CIDR(192.128.0.0/16)에서만 허용하는 Security Group을 사용한다
4. THE Route53_Resolver_Outbound SHALL DNS 쿼리(TCP/UDP 53 포트)를 모든 대상으로 허용하는 Security Group을 사용한다
5. WHEN Route53_Resolver_Inbound가 Private_RAG_VPC에 정상 생성되면, THE Logging_VPC의 기존 Route53_Resolver_Inbound(rslvr-in-79867dcffe644a378) SHALL 삭제된다
6. WHEN Route53_Resolver_Outbound가 Private_RAG_VPC에 정상 생성되면, THE Logging_VPC의 기존 Route53_Resolver_Outbound(rslvr-out-528276266e13403aa) SHALL 삭제된다
7. IF Route53_Resolver_Inbound 생성에 실패하면, THEN THE 시스템 SHALL 기존 Logging_VPC의 Resolver Endpoint를 유지하고 롤백 절차를 실행한다

### 요구사항 2: Private API Gateway 생성 및 Lambda 이전

**사용자 스토리:** 개발자로서, 온프렘에서만 접근 가능한 Private API Gateway를 통해 RAG API를 호출하여, 외부 인터넷에서 RAG 시스템에 접근할 수 없도록 하고 싶다.

#### 인수 조건

1. THE Document_Processor_Lambda SHALL 버지니아 US_Backend_VPC에서 서울 Private_RAG_VPC(10.10.0.0/16)로 이전 배포된다
2. THE Document_Processor_Lambda SHALL Private_RAG_VPC의 10.10.1.0/24 서브넷과 10.10.2.0/24 서브넷에 배치되어 VPC Peering을 통해 US_Backend_VPC의 Bedrock, OpenSearch Serverless, S3 VPC Endpoint에 접근한다
3. THE Private_API_Gateway SHALL Private_RAG_VPC 내에 execute-api 서비스용 VPC_Endpoint_Execute_API를 통해서만 접근 가능한 REST API(Private 타입)로 생성된다
4. THE VPC_Endpoint_Execute_API SHALL Private_RAG_VPC의 10.10.1.0/24 서브넷과 10.10.2.0/24 서브넷에 생성된다
5. THE VPC_Endpoint_Execute_API SHALL HTTPS(443 포트) 트래픽을 OnPrem_Network CIDR(192.128.0.0/16)과 Private_RAG_VPC CIDR(10.10.0.0/16)에서만 허용하는 Security Group을 사용한다
6. THE Private_API_Gateway SHALL Resource Policy를 통해 VPC_Endpoint_Execute_API에서 오는 요청만 허용한다
7. THE Private_API_Gateway SHALL /rag/query 엔드포인트에 대한 POST 요청을 서울 Private_RAG_VPC의 Document_Processor_Lambda로 프록시한다
8. THE Private_API_Gateway SHALL /rag/documents 엔드포인트에 대한 POST 요청을 Document_Processor_Lambda의 문서 업로드 기능으로 프록시한다
9. THE Private_API_Gateway SHALL /rag/health 엔드포인트에 대한 GET 요청에 API 상태 정보를 반환한다
10. IF OnPrem_Network 외부에서 Private_API_Gateway에 접근을 시도하면, THEN THE Private_API_Gateway SHALL 해당 요청을 거부하고 403 Forbidden 응답을 반환한다
11. THE Document_Processor_Lambda SHALL 서울 리전(ap-northeast-2)에서 VPC Peering을 통해 버지니아 리전(us-east-1)의 Bedrock Runtime, Bedrock Agent Runtime, OpenSearch Serverless, S3에 접근한다

### 요구사항 3: Route53 Private Hosted Zone 설정

**사용자 스토리:** 개발자로서, rag.corp.bos-semi.com 도메인으로 RAG API에 접근하여, IP 주소 대신 의미 있는 도메인 이름을 사용하고 싶다.

#### 인수 조건

1. THE Private_Hosted_Zone SHALL corp.bos-semi.com 도메인으로 생성되고 Private_RAG_VPC에 연결된다
2. THE Private_Hosted_Zone SHALL rag.corp.bos-semi.com A 레코드(Alias)를 VPC_Endpoint_Execute_API의 DNS 이름으로 설정한다
3. WHILE Private_Hosted_Zone이 Private_RAG_VPC에만 연결된 상태에서, THE Private_Hosted_Zone의 DNS 레코드 SHALL Logging_VPC 또는 다른 VPC에서 해석되지 않는다
4. THE Private_Hosted_Zone SHALL Private_API_Gateway의 커스텀 도메인 이름으로 rag.corp.bos-semi.com을 설정한다
5. IF Private_Hosted_Zone의 DNS 레코드가 잘못 설정되면, THEN THE 시스템 SHALL DNS 해석 실패 시 명확한 오류 메시지를 CloudWatch Logs에 기록한다

### 요구사항 4: 사내 DNS 조건부 포워딩 설정

**사용자 스토리:** 인프라 관리자로서, 사내 DNS 서버에 조건부 포워딩을 설정하여, *.corp.bos-semi.com 도메인 쿼리만 Route53 Resolver로 전달하고 다른 도메인 해석에 영향을 주지 않도록 하고 싶다.

#### 인수 조건

1. THE Conditional_Forwarding SHALL *.corp.bos-semi.com 도메인에 대한 DNS 쿼리만 Route53_Resolver_Inbound의 IP 주소로 전달하도록 사내 DNS 서버에 설정된다
2. THE Conditional_Forwarding SHALL corp.bos-semi.com 이외의 도메인에 대한 DNS 쿼리를 기존 DNS 해석 경로로 유지한다
3. WHEN OnPrem_Network의 클라이언트가 rag.corp.bos-semi.com을 조회하면, THE 사내 DNS 서버 SHALL 해당 쿼리를 Route53_Resolver_Inbound로 전달하고 VPC_Endpoint_Execute_API의 Private IP 주소를 반환한다
4. WHEN OnPrem_Network의 클라이언트가 기존 SaaS 서비스 도메인을 조회하면, THE 사내 DNS 서버 SHALL 기존 DNS 해석 경로를 사용하여 정상적으로 해석한다
5. IF Conditional_Forwarding 설정 후 SaaS 서비스의 DNS 해석이 실패하면, THEN THE 사내 DNS 서버 SHALL Conditional_Forwarding 규칙을 즉시 비활성화하고 기존 DNS 설정으로 롤백한다

### 요구사항 5: 네트워크 라우팅 및 보안 격리

**사용자 스토리:** 보안 관리자로서, RAG API가 온프렘에서만 접근 가능하고 외부에서 존재 자체를 알 수 없도록 완전히 격리하고 싶다.

#### 인수 조건

1. THE Private_RAG_VPC SHALL Internet Gateway 없이 유지되어 인터넷에서 직접 접근이 불가능하다
2. THE Private_RAG_VPC의 라우팅 테이블 SHALL OnPrem_Network(192.128.0.0/16) 트래픽을 Transit_Gateway로, US_Backend_VPC(10.20.0.0/16) 트래픽을 VPC Peering으로 라우팅한다
3. THE Transit_Gateway 라우팅 테이블 SHALL Private_RAG_VPC(10.10.0.0/16) 대상 트래픽을 Private_RAG_VPC Attachment로 라우팅한다
4. WHILE Private_RAG_VPC에 IGW가 없는 상태에서, THE Private_RAG_VPC 내부의 모든 리소스 SHALL 인터넷으로부터 도달 불가능하다
5. THE VPC_Endpoint_Execute_API SHALL Private DNS를 비활성화하여 Private_Hosted_Zone의 커스텀 도메인 해석과 충돌하지 않도록 한다
6. IF 인가되지 않은 CIDR 범위에서 Private_RAG_VPC의 리소스에 접근을 시도하면, THEN THE Security Group과 Network ACL SHALL 해당 트래픽을 차단한다

### 요구사항 6: 단계별 검증 및 롤백 계획

**사용자 스토리:** 인프라 관리자로서, 각 구성 단계마다 검증을 수행하고 문제 발생 시 롤백할 수 있어, 기존 서비스에 영향 없이 안전하게 배포하고 싶다.

#### 인수 조건

1. WHEN Route53_Resolver_Inbound가 Private_RAG_VPC에 생성되면, THE 검증 프로세스 SHALL OnPrem_Network에서 새 Resolver IP로 DNS 쿼리(nslookup)를 실행하여 응답을 확인한다
2. WHEN VPC_Endpoint_Execute_API가 생성되면, THE 검증 프로세스 SHALL OnPrem_Network에서 VPC Endpoint의 Private IP로 HTTPS 연결을 시도하여 응답을 확인한다
3. WHEN Private_API_Gateway가 배포되면, THE 검증 프로세스 SHALL OnPrem_Network에서 rag.corp.bos-semi.com/rag/health 엔드포인트를 호출하여 정상 응답을 확인한다
4. WHEN Conditional_Forwarding이 설정되면, THE 검증 프로세스 SHALL 기존 SaaS 서비스 도메인 5개 이상에 대해 DNS 해석이 정상 작동하는지 확인한다
5. THE 검증 프로세스 SHALL 각 단계의 검증 결과를 문서화하고, 실패 시 해당 단계의 변경사항을 롤백하는 절차를 포함한다
6. IF 검증 단계에서 기존 서비스에 영향이 감지되면, THEN THE 롤백 프로세스 SHALL 해당 단계의 모든 변경사항을 5분 이내에 원복한다

### 요구사항 7: Private RAG VPC용 VPC Endpoint 구성

**사용자 스토리:** 인프라 관리자로서, Private_RAG_VPC에서 AWS 서비스에 접근하기 위한 VPC Endpoint를 구성하여, 인터넷 없이도 필요한 AWS 서비스를 사용할 수 있도록 하고 싶다.

#### 인수 조건

1. THE Private_RAG_VPC SHALL execute-api 서비스용 VPC Interface Endpoint를 10.10.1.0/24 서브넷과 10.10.2.0/24 서브넷에 생성한다
2. THE Private_RAG_VPC SHALL CloudWatch Logs 서비스용 VPC Interface Endpoint를 생성하여 API Gateway 및 Lambda 로그를 전송할 수 있도록 한다
3. THE Private_RAG_VPC SHALL Secrets Manager 서비스용 VPC Interface Endpoint를 생성하여 API 키 및 인증 정보를 안전하게 조회할 수 있도록 한다
4. WHILE Private_RAG_VPC에 IGW가 없는 상태에서, THE 모든 VPC Endpoint SHALL Private DNS를 활성화하여 AWS 서비스 도메인이 VPC 내부 IP로 해석되도록 한다
5. THE 모든 VPC Interface Endpoint의 Security Group SHALL HTTPS(443 포트) 트래픽을 Private_RAG_VPC CIDR(10.10.0.0/16)과 OnPrem_Network CIDR(192.128.0.0/16)에서만 허용한다
6. IF VPC Endpoint를 통한 AWS 서비스 호출이 실패하면, THEN THE CloudWatch Alarm SHALL 5분 이내에 관리자에게 알림을 전송한다

### 요구사항 8: As-Is / To-Be 아키텍처 비교 및 문서화

**사용자 스토리:** 인프라 관리자로서, 현재 상태와 목표 상태를 명확히 비교하여, 변경 범위와 영향을 정확히 파악하고 싶다.

#### 인수 조건

1. THE 아키텍처 문서 SHALL 현재 상태(As-Is)의 네트워크 토폴로지를 Route53 Resolver 위치(Logging_VPC), VPC Endpoint 위치(Logging_VPC), DNS 해석 경로를 포함하여 기술한다
2. THE 아키텍처 문서 SHALL 목표 상태(To-Be)의 네트워크 토폴로지를 Route53 Resolver 위치(Private_RAG_VPC), Private API Gateway, Private Hosted Zone, 조건부 포워딩 경로를 포함하여 기술한다
3. THE 아키텍처 문서 SHALL 변경 대상 리소스 목록을 리소스 ID, 변경 유형(생성/이전/삭제), 영향 범위와 함께 기술한다
4. THE 아키텍처 문서 SHALL 온프렘에서 RAG API까지의 전체 트래픽 흐름을 단계별로 기술한다: OnPrem_Network → VPN → Transit_Gateway → Private_RAG_VPC → VPC_Endpoint_Execute_API → Private_API_Gateway → Document_Processor_Lambda(서울) → VPC Peering → US_Backend_VPC VPC Endpoint → Bedrock/OpenSearch/S3
5. THE 아키텍처 문서 SHALL 온프렘에서 RAG API까지의 DNS 해석 흐름을 단계별로 기술한다: 사내 DNS → Conditional_Forwarding → Route53_Resolver_Inbound → Private_Hosted_Zone → VPC_Endpoint_Execute_API IP 반환

### 요구사항 9: 데이터 업로드 파이프라인 (서울 S3 + Cross-Region Replication)

**사용자 스토리:** 데이터 관리자로서, 온프렘에서 RAG 임베딩용 문서를 Air-Gapped 환경에서 안전하게 업로드하고, 버지니아 Bedrock Knowledge Base에 자동으로 반영되도록 하고 싶다.

#### 인수 조건

1. THE 서울 리전(ap-northeast-2) SHALL RAG 문서 업로드 전용 S3 버킷을 생성한다 (기존 bos-ai-documents-seoul은 실제 버지니아에 위치하므로 서울 리전에 신규 생성)
2. THE 서울 S3 버킷 SHALL SSE-KMS(CMK) 암호화와 버전 관리를 활성화한다
3. THE 서울 S3 버킷 SHALL Bucket Policy를 통해 Private_RAG_VPC의 S3 VPC Endpoint에서만 접근을 허용한다
4. THE Private_RAG_VPC SHALL S3 Gateway VPC Endpoint를 생성하여 온프렘에서 VPN → TGW → VPC Endpoint 경로로 S3에 접근할 수 있도록 한다
5. THE 서울 S3 버킷 SHALL S3 Cross-Region Replication을 설정하여 업로드된 문서를 버지니아 S3 버킷(bos-ai-documents-us)에 15분 이내에 자동 복제한다
6. THE S3 Cross-Region Replication SHALL KMS 암호화 객체 복제와 Delete Marker 복제를 활성화한다
7. WHEN 온프렘에서 aws s3 cp 또는 aws s3 sync 명령으로 문서를 업로드하면, THE 문서 SHALL 서울 S3 → 버지니아 S3 → Bedrock Knowledge Base 순서로 자동 반영된다
8. IF S3 Cross-Region Replication이 실패하면, THEN THE CloudWatch Alarm SHALL 관리자에게 알림을 전송한다
