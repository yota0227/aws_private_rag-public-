# 구현 계획: Private RAG API

## 개요

온프레미스 환경에서만 접근 가능한 완전 Private RAG API를 구축하기 위한 단계별 구현 계획이다. 배포 순서는 design.md의 단계별 배포 계획을 따르며, 각 단계 완료 후 Terraform 멱등성 검증과 기능 검증을 수행한다. 기존 `environments/`, `modules/` 디렉토리 구조를 유지하며, 코드는 항상 To-Be 상태로 배포 가능해야 한다.

## Tasks

- [x] 1. Route53 Resolver Endpoint를 Private RAG VPC로 이전 (1단계)
  - [x] 1.1 Route53 Resolver용 Security Group 생성
    - `environments/network-layer/route53-resolver.tf` 파일 신규 생성
    - Resolver Inbound SG: TCP/UDP 53 from 192.128.0.0/16 (온프렘)만 허용
    - Resolver Outbound SG: TCP/UDP 53 to 0.0.0.0/0 허용
    - _요구사항: 1.3, 1.4_

  - [x] 1.2 Route53 Resolver Inbound/Outbound Endpoint 생성
    - 동일 `environments/network-layer/route53-resolver.tf`에 추가
    - Inbound: Private RAG VPC 10.10.1.0/24, 10.10.2.0/24 서브넷에 IP 할당
    - Outbound: Private RAG VPC 10.10.1.0/24, 10.10.2.0/24 서브넷에 IP 할당
    - 기존 Logging VPC Resolver는 아직 삭제하지 않음 (병행 운영)
    - _요구사항: 1.1, 1.2, 1.7_

  - [ ]* 1.3 Property 1 테스트 작성: Resolver Inbound SG는 온프렘 DNS만 허용
    - `tests/properties/security_group_test.go` 파일 생성
    - **Property 1: Resolver Inbound Security Group은 온프렘 DNS만 허용**
    - rapid 라이브러리로 랜덤 CIDR/포트 생성 → 192.128.0.0/16 port 53만 허용 검증
    - **검증 대상: 요구사항 1.3**

  - [x] 1.4 `terraform plan` 멱등성 검증 및 DNS 해석 테스트
    - `terraform plan`으로 변경사항 없음(no changes) 확인
    - 온프렘에서 새 Resolver Inbound IP로 nslookup 테스트 절차 문서화
    - _요구사항: 6.1_

- [x] 2. Private RAG VPC용 VPC Endpoint 생성 (2단계)
  - [x] 2.1 VPC Endpoint 공통 Security Group 생성
    - `environments/network-layer/vpc-endpoints-frontend.tf` 파일 신규 생성
    - HTTPS(443) from 10.10.0.0/16 (Private RAG VPC) + 192.128.0.0/16 (온프렘)만 허용
    - _요구사항: 2.5, 7.5_

  - [x] 2.2 VPC Interface Endpoint 생성 (execute-api, CloudWatch Logs, Secrets Manager)
    - 동일 `environments/network-layer/vpc-endpoints-frontend.tf`에 추가
    - execute-api: Private DNS 비활성화 (Private Hosted Zone 충돌 방지)
    - CloudWatch Logs: Private DNS 활성화
    - Secrets Manager: Private DNS 활성화
    - 모든 Interface Endpoint는 10.10.1.0/24, 10.10.2.0/24 서브넷에 배치
    - _요구사항: 7.1, 7.2, 7.3, 7.4, 5.5_

  - [x] 2.3 S3 Gateway VPC Endpoint 생성
    - 동일 `environments/network-layer/vpc-endpoints-frontend.tf`에 추가
    - Private RAG VPC 라우팅 테이블에 S3 prefix list 경로 추가
    - _요구사항: 9.4_

  - [ ]* 2.4 Property 2 테스트 작성: VPC Endpoint SG는 허용된 CIDR만 허용
    - `tests/properties/security_group_test.go`에 추가
    - **Property 2: VPC Endpoint Security Group은 허용된 CIDR만 허용**
    - rapid 라이브러리로 랜덤 CIDR/포트 생성 → 10.10.0.0/16, 192.128.0.0/16 port 443만 허용 검증
    - **검증 대상: 요구사항 2.5, 7.5**

  - [ ]* 2.5 Property 9 테스트 작성: VPC Endpoint Private DNS 설정 일관성
    - `tests/properties/vpc_endpoint_test.go` 파일 생성
    - **Property 9: VPC Endpoint Private DNS 설정 일관성**
    - execute-api만 Private DNS 비활성화, 나머지는 활성화 검증
    - **검증 대상: 요구사항 5.5, 7.4**

  - [x] 2.6 `terraform plan` 멱등성 검증 및 VPC Endpoint 연결 테스트
    - `terraform plan`으로 변경사항 없음(no changes) 확인
    - VPC Endpoint ENI의 Private IP 확인 절차 문서화
    - _요구사항: 6.2_

- [x] 3. 체크포인트 - 네트워크 레이어 검증
  - 모든 테스트 통과 확인, 사용자에게 질문이 있으면 확인 요청
  - `terraform plan` 결과 no changes 확인
  - 기존 인프라(Logging VPC, US Backend VPC)에 영향 없음 확인

- [x] 4. Lambda 이전 (document-processor: 버지니아 → 서울 Private RAG VPC) (3단계)
  - [x] 4.1 Lambda Security Group 생성
    - `environments/app-layer/bedrock-rag/lambda.tf` 수정
    - Outbound: HTTPS(443) to 10.20.0.0/16 (버지니아 VPC Peering) + 10.10.0.0/16 (서울 VPC Endpoint)
    - _요구사항: 2.2_

  - [x] 4.2 Lambda VPC 설정을 서울 Private RAG VPC로 변경
    - `environments/app-layer/bedrock-rag/lambda.tf` 수정
    - VPC: Private RAG VPC (vpc-0a118e1bf21d0c057)
    - 서브넷: 10.10.1.0/24, 10.10.2.0/24
    - 환경 변수: 버지니아 VPC Endpoint DNS 직접 참조하도록 변경
    - IAM Role: 서울 리전 기반으로 수정, Cross-Region 접근 권한 추가
    - _요구사항: 2.1, 2.2, 2.11_

  - [x] 4.3 providers.tf에 서울 리전 provider 추가
    - `environments/app-layer/bedrock-rag/providers.tf` 수정
    - 서울 리전(ap-northeast-2) provider alias 추가
    - _요구사항: 2.1_

  - [ ]* 4.4 Lambda 배치 유닛 테스트 작성
    - `tests/unit/resolver_test.go` 또는 `tests/unit/lambda_test.go` 파일 생성
    - Lambda가 서울 VPC에 배포되고 버지니아 VPC에는 없는지 확인
    - Lambda SG의 Outbound 규칙이 올바른지 확인
    - **검증 대상: 요구사항 2.1, 2.2**

  - [x] 4.5 `terraform plan` 멱등성 검증
    - `terraform plan`으로 변경사항 없음(no changes) 확인
    - _요구사항: 6.5_

- [x] 5. Private API Gateway 생성 (4단계)
  - [x] 5.1 Private API Gateway (REST API, Private 타입) 생성
    - `environments/app-layer/bedrock-rag/api-gateway.tf` 파일 신규 생성
    - REST API Private 타입으로 생성
    - Resource Policy: VPC Endpoint (execute-api)에서 오는 요청만 허용
    - 엔드포인트 설정: /rag/query (POST), /rag/documents (POST), /rag/health (GET)
    - 각 엔드포인트를 서울 Lambda(document-processor)로 프록시
    - _요구사항: 2.3, 2.6, 2.7, 2.8, 2.9, 2.10_

  - [ ]* 5.2 Property 3 테스트 작성: Private API Gateway는 VPC Endpoint 외부 요청 거부
    - `tests/properties/vpc_endpoint_test.go`에 추가
    - **Property 3: Private API Gateway는 VPC Endpoint 외부 요청을 거부**
    - Resource Policy의 Deny/Allow 조건 검증
    - **검증 대상: 요구사항 2.10**

  - [ ]* 5.3 API Gateway 유닛 테스트 작성
    - `tests/unit/api_gateway_test.go` 파일 생성
    - API Gateway Resource Policy가 VPC Endpoint만 허용하는지 확인
    - 엔드포인트 경로와 메서드가 올바른지 확인
    - **검증 대상: 요구사항 2.6, 2.7, 2.8, 2.9**

  - [x] 5.4 `terraform plan` 멱등성 검증
    - `terraform plan`으로 변경사항 없음(no changes) 확인
    - _요구사항: 6.3_

- [x] 6. Private Hosted Zone 설정 (5단계)
  - [x] 6.1 Private Hosted Zone 및 DNS 레코드 생성
    - `environments/app-layer/bedrock-rag/route53.tf` 파일 신규 생성
    - Private Hosted Zone: corp.bos-semi.com, Private RAG VPC에만 연결
    - A 레코드 (Alias): rag.corp.bos-semi.com → VPC Endpoint (execute-api) DNS
    - API Gateway 커스텀 도메인: rag.corp.bos-semi.com 설정
    - _요구사항: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 6.2 Property 4 테스트 작성: Private Hosted Zone DNS 격리
    - `tests/properties/dns_isolation_test.go` 파일 생성
    - **Property 4: Private Hosted Zone DNS 격리**
    - PHZ가 Private RAG VPC에만 연결되어 있는지 검증
    - **검증 대상: 요구사항 3.3**

  - [ ]* 6.3 Property 5 테스트 작성: 조건부 포워딩 정확성
    - `tests/properties/dns_isolation_test.go`에 추가
    - **Property 5: 조건부 포워딩 정확성**
    - *.corp.bos-semi.com만 Route53 Resolver로 전달되는지 검증
    - **검증 대상: 요구사항 4.1, 4.2**

  - [ ]* 6.4 Private Hosted Zone 유닛 테스트 작성
    - `tests/unit/private_hosted_zone_test.go` 파일 생성
    - PHZ가 올바른 VPC에만 연결되어 있는지 확인
    - Alias 레코드가 VPC Endpoint DNS를 가리키는지 확인
    - **검증 대상: 요구사항 3.1, 3.2**

  - [x] 6.5 `terraform plan` 멱등성 검증
    - `terraform plan`으로 변경사항 없음(no changes) 확인
    - DNS 해석 테스트 절차 문서화 (nslookup rag.corp.bos-semi.com)
    - _요구사항: 6.3_

- [x] 7. 체크포인트 - 앱 레이어 검증
  - 모든 테스트 통과 확인, 사용자에게 질문이 있으면 확인 요청
  - `terraform plan` 결과 no changes 확인 (network-layer + app-layer 모두)
  - Lambda → Bedrock/OpenSearch 호출 경로 확인

- [x] 8. 데이터 업로드 파이프라인 구축 (6단계)
  - [x] 8.1 서울 리전 S3 버킷 생성 및 암호화 설정
    - `environments/app-layer/bedrock-rag/s3-pipeline.tf` 파일 신규 생성 또는 `modules/ai-workload/s3-pipeline/` 모듈 활용
    - 버킷명: bos-ai-documents-seoul-v2 (ap-northeast-2)
    - SSE-KMS (CMK) 암호화 활성화
    - 버전 관리 활성화 (Replication 필수 조건)
    - Bucket Policy: Private RAG VPC의 S3 VPC Endpoint에서만 접근 허용
    - _요구사항: 9.1, 9.2, 9.3_

  - [x] 8.2 S3 Cross-Region Replication 설정
    - 동일 파일에 추가
    - Source: bos-ai-documents-seoul-v2 (ap-northeast-2)
    - Destination: bos-ai-documents-us (us-east-1)
    - Replication Time Control: 15분
    - KMS 암호화 객체 복제 활성화
    - Delete Marker 복제 활성화
    - IAM Role 생성 (Replication 전용)
    - _요구사항: 9.5, 9.6_

  - [ ]* 8.3 S3 파이프라인 유닛 테스트 작성
    - `tests/unit/s3_pipeline_test.go` 파일 생성
    - S3 버킷 암호화 설정 확인
    - Bucket Policy가 VPC Endpoint만 허용하는지 확인
    - Cross-Region Replication 설정 확인
    - **검증 대상: 요구사항 9.1, 9.2, 9.3, 9.5, 9.6**

  - [x] 8.4 `terraform plan` 멱등성 검증
    - `terraform plan`으로 변경사항 없음(no changes) 확인
    - _요구사항: 9.7_

- [x] 9. 사내 DNS 조건부 포워딩 가이드 작성 (7단계)
  - [x] 9.1 조건부 포워딩 설정 가이드 문서 작성
    - `docs/dns-conditional-forwarding-guide.md` 파일 생성
    - 사내 DNS 서버에 *.corp.bos-semi.com → Route53 Resolver Inbound IP 설정 절차
    - Route53 Resolver Inbound IP 주소 출력 (Terraform output)
    - 검증 절차: nslookup rag.corp.bos-semi.com, 기존 SaaS 서비스 DNS 해석 확인
    - 롤백 절차: 조건부 포워딩 규칙 비활성화 방법
    - _요구사항: 4.1, 4.2, 4.3, 4.4, 4.5, 6.4_

- [x] 10. 네트워크 보안 격리 검증 (라우팅 및 보안)
  - [ ]* 10.1 Property 6 테스트 작성: Private RAG VPC 라우팅 정확성
    - `tests/properties/routing_test.go` 파일 생성
    - **Property 6: Private RAG VPC 라우팅 정확성**
    - rapid 라이브러리로 랜덤 목적지 IP 생성 → 올바른 next-hop (TGW, VPC Peering) 검증
    - 0.0.0.0/0 기본 경로가 없는지 검증
    - **검증 대상: 요구사항 5.2**

  - [ ]* 10.2 Property 7 테스트 작성: Private RAG VPC 인터넷 격리
    - `tests/properties/routing_test.go`에 추가
    - **Property 7: Private RAG VPC 인터넷 격리**
    - IGW 미연결, 0.0.0.0/0 → IGW/NAT 경로 없음 검증
    - **검증 대상: 요구사항 5.4**

  - [ ]* 10.3 Property 8 테스트 작성: 비인가 CIDR 차단
    - `tests/properties/security_group_test.go`에 추가
    - **Property 8: 비인가 CIDR 차단**
    - rapid 라이브러리로 허용 목록 외 랜덤 CIDR 생성 → 차단 검증
    - **검증 대상: 요구사항 5.6**

- [x] 11. 기존 Logging VPC Resolver 삭제 (8단계)
  - [x] 11.1 Logging VPC의 기존 Route53 Resolver Endpoint 삭제
    - `environments/network-layer/route53-resolver.tf` 수정
    - 기존 Logging VPC Resolver Inbound (rslvr-in-79867dcffe644a378) 삭제
    - 기존 Logging VPC Resolver Outbound (rslvr-out-528276266e13403aa) 삭제
    - 관련 Security Group 정리
    - 삭제 전 Private RAG VPC Resolver가 정상 동작하는지 반드시 확인
    - _요구사항: 1.5, 1.6_

  - [x] 11.2 `terraform plan` 멱등성 검증
    - `terraform plan`으로 삭제 대상만 표시되는지 확인
    - apply 후 no changes 확인
    - _요구사항: 6.5_

- [x] 12. 체크포인트 - 전체 인프라 검증
  - 모든 테스트 통과 확인, 사용자에게 질문이 있으면 확인 요청
  - `terraform plan` 결과 no changes 확인 (모든 레이어)
  - 전체 E2E 흐름 검증 절차 확인

- [x] 13. As-Is / To-Be 아키텍처 문서화 (9단계)
  - [x] 13.1 아키텍처 비교 문서 작성
    - `docs/architecture-as-is-to-be.md` 파일 생성
    - As-Is 네트워크 토폴로지: Route53 Resolver(Logging VPC), VPC Endpoint(Logging VPC), DNS 해석 경로
    - To-Be 네트워크 토폴로지: Route53 Resolver(Private RAG VPC), Private API Gateway, Private Hosted Zone, 조건부 포워딩 경로
    - 변경 대상 리소스 목록: 리소스 ID, 변경 유형(생성/이전/삭제), 영향 범위
    - 온프렘 → RAG API 전체 트래픽 흐름 (단계별)
    - 온프렘 → RAG API DNS 해석 흐름 (단계별)
    - _요구사항: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 14. 최종 체크포인트 - 전체 완료 검증
  - 모든 테스트 통과 확인, 사용자에게 질문이 있으면 확인 요청
  - 모든 Terraform 레이어에서 `terraform plan` no changes 확인
  - 아키텍처 문서 완성 확인

## 참고사항

- `*` 표시된 태스크는 선택사항이며 빠른 MVP를 위해 건너뛸 수 있음
- 각 태스크는 추적 가능성을 위해 특정 요구사항을 참조함
- 체크포인트는 점진적 검증을 보장함
- Property 테스트는 보편적 정확성 속성을 검증하며, 유닛 테스트는 특정 예제와 에지 케이스를 검증함
- Terraform 멱등성 검증은 TGW 구조 변경 이후 특히 중요하므로 각 단계마다 반드시 수행
- 기존 인프라가 깨지지 않도록 항상 To-Be 배포 가능 상태를 유지
