# BOS-AI VPC 통합 마이그레이션 요구사항

## 1. 개요

### 1.1 목적
서울 리전에 격리되어 있는 BOS-AI-RAG VPC(vpc-0f759f00e5df658d1)의 리소스를 기존 PoC VPC(vpc-066c464f9c750ee9e)로 통합하여, 온프레미스와 VPN으로 연결된 단일 통합 VPC 환경을 구축합니다.

### 1.2 배경
- 현재 BOS-AI-RAG VPC는 VPN 연결이 없어 온프레미스에서 접근 불가
- 기존 로깅 인프라(PoC VPC)는 VPN을 통해 온프레미스와 안전하게 연결됨
- AI 워크로드와 로깅 인프라를 통합하여 관리 복잡도 감소 필요
- 버지니아 VPC는 백엔드 레이어로 유지하며 직접 온프레미스 접근 불필요

### 1.3 범위
**포함:**
- BOS-AI-RAG 리소스(OpenSearch Serverless, Lambda, Bedrock KB)를 서울 통합 VPC로 마이그레이션
- 서울 통합 VPC 네이밍 표준화
- 서울-버지니아 VPC 피어링 구성
- Route53 Resolver 엔드포인트 검토 및 구성
- 기존 BOS-AI-RAG VPC 제거

**제외:**
- 기존 로깅 인프라 변경 (EC2 수집기, Grafana, OpenSearch Managed)
- 온프레미스 VPN 설정 변경
- 버지니아 VPC 내부 리소스 변경

## 2. 사용자 스토리

### 2.1 US-1: 온프레미스 사용자의 AI 서비스 접근
**As a** 온프레미스 네트워크 사용자  
**I want to** VPN을 통해 서울 VPC의 AI 서비스(Bedrock, OpenSearch)에 접근  
**So that** 공용 인터넷을 거치지 않고 안전하게 RAG 기능을 사용할 수 있다

**인수 기준:**
- 온프레미스(192.128.x.x)에서 서울 VPC의 OpenSearch Serverless 엔드포인트 접근 가능
- 온프레미스에서 서울 VPC의 Lambda 함수 호출 가능
- VPN 터널을 통한 암호화된 통신 유지
- 기존 VPN Gateway(vgw-0d54d0b0af6515dec) 활용

### 2.2 US-2: AI 워크로드의 백엔드 데이터 접근
**As an** AI 워크로드 (Lambda, Bedrock)  
**I want to** VPC 피어링을 통해 버지니아 VPC의 S3 데이터에 접근  
**So that** 문서 처리 및 벡터 임베딩 작업을 수행할 수 있다

**인수 기준:**
- 서울 VPC(10.200.0.0/16)와 버지니아 VPC(10.20.0.0/16) 간 VPC 피어링 활성화
- 라우팅 테이블에 피어링 경로 추가
- Security Group에서 교차 VPC 트래픽 허용
- Lambda에서 버지니아 S3 버킷 읽기/쓰기 가능

### 2.3 US-3: 프라이빗 환경에서의 AWS 서비스 호출
**As a** 프라이빗 서브넷의 Lambda 함수  
**I want to** VPC 엔드포인트를 통해 AWS 서비스(Bedrock, S3, Secrets Manager)를 호출  
**So that** 인터넷 게이트웨이 없이도 AWS 서비스를 안전하게 사용할 수 있다

**인수 기준:**
- Bedrock Runtime VPC 엔드포인트 구성
- S3 Gateway 엔드포인트 구성
- Secrets Manager Interface 엔드포인트 구성
- Route53 Resolver를 통한 AWS 서비스 도메인 해석

### 2.4 US-4: 통합 VPC 리소스 네이밍 표준화
**As an** 인프라 관리자  
**I want to** 모든 VPC 리소스가 일관된 네이밍 규칙을 따르도록  
**So that** 리소스 식별 및 관리가 용이하다

**인수 기준:**
- VPC 이름: `vpc-bos-ai-seoul-prod-01`
- 서브넷 이름: `sn-{type}-bos-ai-seoul-prod-01{az}` 형식
- Security Group 이름: `sg-{service}-bos-ai-seoul-prod` 형식
- 모든 리소스에 표준 태그 적용 (Project, Environment, ManagedBy, Layer)

### 2.5 US-5: 기존 로깅 인프라 무중단 운영
**As a** 로깅 시스템 운영자  
**I want to** 마이그레이션 중에도 기존 로깅 파이프라인이 정상 동작  
**So that** 온프레미스 로그 수집에 중단이 없다

**인수 기준:**
- EC2 로그 수집기(ec2-logclt-itdev-int-poc-01) 정상 동작 유지
- Firehose VPC 엔드포인트 정상 동작 유지
- OpenSearch Managed 도메인(open-mon-itdev-int-poc-001) 정상 동작 유지
- Grafana 대시보드 접근 가능 유지

## 3. 기능 요구사항

### 3.1 FR-1: VPC 네이밍 변경
서울 PoC VPC의 모든 리소스를 새로운 네이밍 규칙에 맞게 변경해야 합니다.

**상세:**
- VPC 태그 업데이트
- 서브넷 태그 업데이트
- Security Group 이름 및 태그 업데이트
- Route Table 태그 업데이트
- NAT Gateway, Internet Gateway 태그 업데이트

### 3.2 FR-2: OpenSearch Serverless 마이그레이션
기존 BOS-AI-RAG VPC의 OpenSearch Serverless 컬렉션을 서울 통합 VPC로 재배포해야 합니다.

**상세:**
- 새로운 VPC 엔드포인트 생성
- Security Group 구성 (온프레미스 및 Lambda 접근 허용)
- 데이터 소스 재설정
- 인덱스 매핑 유지

### 3.3 FR-3: Lambda 함수 VPC 설정 변경
문서 처리 Lambda 함수를 서울 통합 VPC의 프라이빗 서브넷에 배포해야 합니다.

**상세:**
- VPC 설정 변경 (서브넷, Security Group)
- ENI 생성 및 IP 할당
- VPC 엔드포인트를 통한 AWS 서비스 접근 설정
- IAM Role 권한 검증

### 3.4 FR-4: Bedrock Knowledge Base VPC 연동
Bedrock Knowledge Base가 서울 통합 VPC의 OpenSearch Serverless에 접근하도록 설정해야 합니다.

**상세:**
- Knowledge Base VPC 설정 업데이트
- Security Group 규칙 추가
- 데이터 소스 연결 재설정
- 동기화 작업 테스트

### 3.5 FR-5: VPC 피어링 구성
서울 통합 VPC와 버지니아 백엔드 VPC 간 피어링을 구성해야 합니다.

**상세:**
- VPC Peering Connection 생성
- 양방향 라우팅 테이블 업데이트
- Security Group 교차 참조 설정
- DNS 해석 옵션 활성화

### 3.6 FR-6: VPC 엔드포인트 구성
프라이빗 서브넷에서 AWS 서비스 접근을 위한 VPC 엔드포인트를 구성해야 합니다.

**상세:**
- Bedrock Runtime Interface 엔드포인트
- S3 Gateway 엔드포인트
- Secrets Manager Interface 엔드포인트
- CloudWatch Logs Interface 엔드포인트

### 3.7 FR-7: Route53 Resolver 설정
프라이빗 환경에서 AWS 서비스 도메인 해석을 위한 Route53 Resolver를 구성해야 합니다.

**상세:**
- 기존 Inbound/Outbound 엔드포인트 활용
- AWS 서비스 도메인에 대한 포워딩 규칙 추가
- 온프레미스 DNS와의 통합 유지

### 3.8 FR-8: 기존 BOS-AI-RAG VPC 제거
마이그레이션 완료 후 격리된 BOS-AI-RAG VPC를 안전하게 제거해야 합니다.

**상세:**
- 모든 리소스 마이그레이션 검증
- VPC 피어링 연결 삭제
- VPN Gateway 분리
- VPC 삭제

## 4. 비기능 요구사항

### 4.1 NFR-1: 보안
- 모든 통신은 프라이빗 네트워크를 통해 이루어져야 함
- Security Group은 최소 권한 원칙을 따라야 함
- IAM Role은 서비스별로 분리되어야 함
- 암호화된 VPN 터널을 통한 온프레미스 연결 유지

### 4.2 NFR-2: 가용성
- 마이그레이션 중 기존 로깅 인프라 무중단 운영
- Multi-AZ 배포 유지 (ap-northeast-2a, ap-northeast-2c)
- VPC 엔드포인트 이중화 구성

### 4.3 NFR-3: 성능
- VPC 피어링을 통한 저지연 통신 (<10ms)
- VPC 엔드포인트를 통한 AWS 서비스 호출 최적화
- NAT Gateway 대역폭 충분성 확보

### 4.4 NFR-4: 관리성
- 모든 인프라는 Terraform으로 관리
- 일관된 네이밍 규칙 적용
- 표준 태그 전략 준수
- 변경 이력 추적 가능

### 4.5 NFR-5: 비용 최적화
- 불필요한 VPC 제거로 비용 절감
- VPC 엔드포인트 통합으로 데이터 전송 비용 절감
- NAT Gateway 사용 최소화

## 5. 제약사항

### 5.1 기술적 제약사항
- 기존 VPN Gateway 설정 변경 불가
- 온프레미스 방화벽 정책 변경 최소화
- 기존 로깅 파이프라인 중단 불가
- Terraform 상태 파일 충돌 방지 필요

### 5.2 운영적 제약사항
- 마이그레이션은 업무 시간 외 수행
- 롤백 계획 필수
- 단계별 검증 필수
- 변경 승인 프로세스 준수

## 6. 의존성

### 6.1 외부 의존성
- 온프레미스 네트워크 팀 협조 (방화벽 규칙 검토)
- AWS Support (VPC 피어링 제한 확인)
- 보안팀 승인 (Security Group 변경)

### 6.2 내부 의존성
- 기존 Terraform 모듈 (modules/network/, modules/security/)
- IAM Role 정의 (modules/security/iam/)
- VPC 엔드포인트 모듈 (modules/security/vpc-endpoints/)

## 7. 성공 기준

### 7.1 기능적 성공 기준
- [ ] 온프레미스에서 서울 VPC의 OpenSearch Serverless 접근 가능
- [ ] Lambda 함수가 버지니아 S3 버킷 접근 가능
- [ ] Bedrock Knowledge Base가 정상 동작
- [ ] 기존 로깅 파이프라인 정상 동작
- [ ] 모든 리소스가 새로운 네이밍 규칙 준수

### 7.2 비기능적 성공 기준
- [ ] 마이그레이션 중 로깅 인프라 다운타임 0분
- [ ] VPC 피어링 지연시간 <10ms
- [ ] 모든 인프라가 Terraform으로 관리됨
- [ ] 보안 스캔 통과 (tfsec, checkov)
- [ ] 비용 증가 <10%

## 8. 위험 및 완화 전략

### 8.1 위험: VPC 피어링 라우팅 충돌
**완화:** 사전에 CIDR 블록 검증, 라우팅 테이블 시뮬레이션

### 8.2 위험: Lambda ENI 생성 실패
**완화:** 충분한 IP 주소 확보, 서브넷 용량 사전 확인

### 8.3 위험: OpenSearch 데이터 손실
**완화:** 마이그레이션 전 스냅샷 생성, 롤백 계획 수립

### 8.4 위험: VPN 연결 중단
**완화:** VPN Gateway 설정 변경 없음, 기존 라우팅 유지

## 9. 마일스톤

### Phase 1: 준비 (1주)
- 현재 상태 문서화
- 네이밍 규칙 확정
- Terraform 코드 리뷰

### Phase 2: VPC 네이밍 변경 (1주)
- 태그 업데이트
- 문서 업데이트
- 검증

### Phase 3: 리소스 마이그레이션 (2주)
- OpenSearch Serverless 재배포
- Lambda VPC 설정 변경
- Bedrock KB 재설정

### Phase 4: VPC 피어링 구성 (1주)
- 피어링 연결 생성
- 라우팅 설정
- 테스트

### Phase 5: 정리 및 검증 (1주)
- 기존 VPC 제거
- 통합 테스트
- 문서화

## 10. 부록

### 10.1 현재 리소스 목록
**서울 PoC VPC (vpc-066c464f9c750ee9e):**
- CIDR: 10.200.0.0/16
- 서브넷: 4개 (Private 2, Public 2)
- VPN Gateway: vgw-0d54d0b0af6515dec
- EC2: 6개 (로그 수집기, Grafana, EKS 노드)
- OpenSearch Managed: open-mon-itdev-int-poc-001
- NAT Gateway: 1개
- Route53 Resolver: Inbound/Outbound

**서울 BOS-AI-RAG VPC (vpc-0f759f00e5df658d1):**
- CIDR: 10.10.0.0/16
- 서브넷: 2개 (Private only)
- VPN Gateway: vgw-0461cd4d6a4463f67 (사용 안 함)
- OpenSearch Serverless: 미배포 (계획만 존재)
- Lambda: 미배포 (계획만 존재)

### 10.2 네이밍 규칙
```
VPC: vpc-{project}-{region}-{env}-{seq}
Subnet: sn-{type}-{project}-{region}-{env}-{seq}{az}
Security Group: sg-{service}-{project}-{region}-{env}
Route Table: rtb-{type}-{project}-{region}-{env}-{seq}
```

예시:
- `vpc-bos-ai-seoul-prod-01`
- `sn-private-bos-ai-seoul-prod-01a`
- `sg-opensearch-bos-ai-seoul-prod`
