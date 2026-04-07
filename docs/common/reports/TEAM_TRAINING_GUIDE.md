# BOS-AI RAG 팀원 교육 가이드

## 🎯 이 문서의 목적

이 문서는 BOS-AI RAG 시스템을 처음 접하는 팀원들이 **시스템의 목적, 구조, 배포 방법**을 빠르게 이해할 수 있도록 작성되었습니다.

---

## 📚 학습 순서

### 1단계: 시스템 이해 (30분)

**읽을 문서**: [Report/ARCHITECTURE_DETAILS.md](ARCHITECTURE_DETAILS.md)

**학습 목표**:
- [ ] BOS-AI RAG의 목적 이해
- [ ] 온프렘과 AWS 간 연결 방식 이해
- [ ] 3개 VPC의 역할 이해
- [ ] 데이터 흐름 이해

**핵심 개념**:
```
온프렘 (192.128.0.0/16)
    ↓ VPN
AWS Transit Gateway
    ├─ Logging VPC (10.200.0.0/16) - 모니터링
    ├─ Private RAG VPC (10.10.0.0/16) - 프론트엔드 (Lambda, API)
    └─ US Backend VPC (10.20.0.0/16) - 백엔드 (Bedrock, OpenSearch)
```

### 2단계: 배포 구조 이해 (30분)

**읽을 문서**: [Report/DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md)

**학습 목표**:
- [ ] 배포 3단계 이해
- [ ] 각 단계별 구성 요소 이해
- [ ] 배포 순서의 중요성 이해
- [ ] 각 단계별 검증 항목 이해

**배포 3단계**:
1. **네트워크 레이어** - VPC, TGW, VPN, DNS
2. **앱 레이어** - Lambda, API Gateway, S3, OpenSearch, Bedrock
3. **모니터링 레이어** - CloudWatch, CloudTrail, 알람

### 3단계: 실제 배포 (1-2시간)

**읽을 문서**: [Report/DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md) + [docs/DEPLOYMENT_GUIDE.md](../docs/DEPLOYMENT_GUIDE.md)

**실습 목표**:
- [ ] 네트워크 레이어 배포
- [ ] 앱 레이어 배포
- [ ] 모니터링 레이어 배포
- [ ] 배포 후 검증

**배포 명령어**:
```bash
# 1단계: 네트워크
cd environments/network-layer
terraform init
terraform apply

# 2단계: 앱
cd environments/app-layer/bedrock-rag
terraform init
terraform apply

# 3단계: 모니터링
cd environments/monitoring
terraform init
terraform apply
```

### 4단계: 테스트 및 검증 (1시간)

**읽을 문서**: [Report/20260303_VPN_CONNECTIVITY_TEST_RESULTS.md](20260303_VPN_CONNECTIVITY_TEST_RESULTS.md)

**테스트 항목**:
- [ ] VPN 연결성 테스트
- [ ] DNS 해석 테스트
- [ ] API 엔드포인트 테스트
- [ ] 문서 업로드 테스트
- [ ] RAG 질의 테스트

---

## 🏗️ 시스템 아키텍처 한눈에 보기

### 프론트엔드 (Seoul - Private RAG VPC)

```
온프렘 사용자
    ↓
API Gateway (rag.corp.bos-semi.com)
    ├─ POST /rag/documents - 문서 업로드
    ├─ POST /rag/query - RAG 질의
    └─ GET /rag/health - 헬스 체크
    ↓
Lambda (document-processor)
    ├─ 문서 처리
    ├─ 벡터 생성
    └─ 응답 생성
    ↓
S3 (Seoul) - bos-ai-documents-seoul-v3
    └─ 문서 임시 저장
```

### 백엔드 (Virginia - US Backend VPC)

```
S3 (Virginia) - bos-ai-documents-us
    ↓
Bedrock Knowledge Base
    ├─ 문서 인덱싱
    ├─ 벡터 생성 (Titan Embed)
    └─ 응답 생성 (Claude)
    ↓
OpenSearch Serverless
    └─ 벡터 저장소
```

### 데이터 흐름

```
1. 문서 업로드
   온프렘 → API Gateway → Lambda → S3 (Seoul)
                                    ↓ 크로스 리전 복제
                                    S3 (Virginia)
                                    ↓
                                    Bedrock KB
                                    ↓
                                    OpenSearch

2. RAG 질의
   온프렘 → API Gateway → Lambda → OpenSearch (검색)
                                    ↓
                                    Bedrock (응답 생성)
                                    ↓
                                    온프렘
```

---

## 🔑 핵심 개념 설명

### 1. Transit Gateway (TGW)

**역할**: 3개 VPC를 중앙에서 연결하는 라우터

**왜 필요한가?**
- VPC 간 직접 연결 대신 중앙 라우터 사용
- 온프렘 ↔ 모든 VPC 연결 가능
- 라우팅 정책 중앙화

**예시**:
```
온프렘 (192.128.0.0/16)
    ↓
TGW (중앙 라우터)
    ├─ 라우트 1: 192.128.0.0/16 → Logging VPC
    ├─ 라우트 2: 192.128.0.0/16 → Private RAG VPC
    └─ 라우트 3: 192.128.0.0/16 → US Backend VPC
```

### 2. VPC Endpoints

**역할**: AWS 서비스에 인터넷 없이 접근

**왜 필요한가?**
- 보안: 인터넷 게이트웨이 불필요
- 성능: 더 빠른 연결
- 비용: 데이터 전송 비용 절감

**예시**:
```
Lambda (Seoul VPC)
    ↓ VPC Endpoint (Private Link)
    ├─ S3 (Seoul)
    ├─ OpenSearch (Virginia)
    ├─ Bedrock (Virginia)
    └─ CloudWatch Logs (Seoul)
```

### 3. Route53 Resolver

**역할**: 온프렘 DNS 쿼리를 AWS Private Hosted Zone으로 해석

**왜 필요한가?**
- 온프렘에서 AWS 도메인 해석 가능
- 중앙화된 DNS 관리
- 자동 페일오버

**예시**:
```
온프렘 사용자
    ↓
nslookup rag.corp.bos-semi.com
    ↓
Route53 Resolver Inbound (10.10.1.34 또는 10.10.2.144)
    ↓
AWS Private Hosted Zone
    ↓
rag.corp.bos-semi.com → 10.10.1.21 (API Gateway VPC Endpoint)
```

### 4. S3 크로스 리전 복제

**역할**: Seoul S3 → Virginia S3 자동 복제

**왜 필요한가?**
- Bedrock KB는 Virginia에만 있음
- 문서는 Seoul에서 업로드됨
- 자동 복제로 데이터 동기화

**예시**:
```
온프렘 사용자
    ↓
S3 (Seoul)에 문서 업로드
    ↓ 자동 복제 (15분 이내)
    ↓
S3 (Virginia)
    ↓
Bedrock KB 자동 인덱싱
```

---

## 🚀 배포 체크리스트

### 배포 전 준비

- [ ] AWS 자격증명 설정
  ```bash
  aws configure
  # AWS Access Key ID: [입력]
  # AWS Secret Access Key: [입력]
  # Default region: ap-northeast-2
  ```

- [ ] Terraform 설치 확인
  ```bash
  terraform version
  # Terraform v1.0 이상 필요
  ```

- [ ] 변수 파일 준비
  ```bash
  cd environments/network-layer
  cp terraform.tfvars.example terraform.tfvars
  # terraform.tfvars 파일 수정
  ```

### 1단계: 네트워크 배포

```bash
cd environments/network-layer
terraform init
terraform plan
terraform apply
```

**검증**:
```bash
# VPC 생성 확인
aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,CidrBlock]'

# TGW 확인
aws ec2 describe-transit-gateways --query 'TransitGateways[*].[TransitGatewayId,State]'

# VPC Endpoints 확인
aws ec2 describe-vpc-endpoints --query 'VpcEndpoints[*].[VpcEndpointId,ServiceName,State]'
```

### 2단계: 앱 배포

```bash
cd environments/app-layer/bedrock-rag
terraform init
terraform plan
terraform apply
```

**검증**:
```bash
# Lambda 함수 확인
aws lambda list-functions --query 'Functions[*].[FunctionName,Runtime]'

# API Gateway 확인
aws apigateway get-rest-apis --query 'items[*].[id,name]'

# S3 버킷 확인
aws s3 ls
```

### 3단계: 모니터링 배포

```bash
cd environments/monitoring
terraform init
terraform plan
terraform apply
```

**검증**:
```bash
# CloudWatch 로그 그룹 확인
aws logs describe-log-groups --query 'logGroups[*].logGroupName'

# CloudTrail 확인
aws cloudtrail describe-trails --query 'trailList[*].[Name,S3BucketName]'
```

---

## 🧪 테스트 시나리오

### 테스트 1: VPN 연결성

```bash
# 온프렘에서 실행
ping 10.10.1.34  # Route53 Resolver
ping 10.10.1.21  # API Gateway VPC Endpoint
```

**예상 결과**: 응답 시간 50-100ms

### 테스트 2: DNS 해석

```bash
# 온프렘에서 실행
nslookup rag.corp.bos-semi.com
```

**예상 결과**: 10.10.1.21 또는 10.10.2.75

### 테스트 3: API 엔드포인트

```bash
# 온프렘에서 실행
curl -X GET https://rag.corp.bos-semi.com/dev/rag/health
```

**예상 결과**: 200 OK + 헬스 체크 응답

### 테스트 4: 문서 업로드

```bash
# 온프렘에서 실행
curl -X POST https://rag.corp.bos-semi.com/dev/rag/documents \
  -H "Content-Type: application/json" \
  -d '{"filename": "test.pdf", "content": "..."}'
```

**예상 결과**: 200 OK + 업로드 완료 메시지

### 테스트 5: RAG 질의

```bash
# 온프렘에서 실행
curl -X POST https://rag.corp.bos-semi.com/dev/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "문서에서 XXX에 대해 설명해줘"}'
```

**예상 결과**: 200 OK + AI 응답

---

## 📊 모니터링 대시보드

### CloudWatch 대시보드 확인

```bash
# 대시보드 목록
aws cloudwatch list-dashboards

# 특정 대시보드 조회
aws cloudwatch get-dashboard --dashboard-name bos-ai-dev-dashboard
```

### 주요 메트릭

| 메트릭 | 정상 범위 | 경고 기준 |
|--------|---------|---------|
| Lambda 에러율 | < 0.1% | > 1% |
| API 응답 시간 | 100-500ms | > 5초 |
| OpenSearch 검색 시간 | 100-200ms | > 1초 |
| Bedrock 응답 시간 | 1-3초 | > 10초 |

---

## 🔧 트러블슈팅

### 문제 1: VPN 연결 실패

**증상**: 온프렘에서 AWS 리소스 접근 불가

**해결 방법**:
```bash
# VPN 상태 확인
aws ec2 describe-vpn-connections --query 'VpnConnections[*].[VpnConnectionId,State]'

# BGP 라우트 확인
aws ec2 search-transit-gateway-routes --transit-gateway-route-table-id tgw-rtb-xxx

# 온프렘 방화벽 로그 확인
# FortiGate: diagnose vpn ipsec status
```

### 문제 2: DNS 해석 실패

**증상**: nslookup rag.corp.bos-semi.com 실패

**해결 방법**:
```bash
# Route53 Resolver 상태 확인
aws route53resolver list-resolver-endpoints

# DNS 쿼리 테스트
dig @10.10.1.34 rag.corp.bos-semi.com

# Private Hosted Zone 확인
aws route53 list-hosted-zones-by-name
```

### 문제 3: API 응답 느림

**증상**: API 응답 시간 > 5초

**해결 방법**:
```bash
# Lambda 로그 확인
aws logs tail /aws/lambda/lambda-document-processor-seoul-prod --follow

# Lambda 메트릭 확인
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=lambda-document-processor-seoul-prod \
  --start-time 2026-03-06T00:00:00Z \
  --end-time 2026-03-06T23:59:59Z \
  --period 300 \
  --statistics Average,Maximum
```

---

## 📚 추가 학습 자료

### 필수 읽을거리

1. [Report/ARCHITECTURE_DETAILS.md](ARCHITECTURE_DETAILS.md) - 아키텍처 상세
2. [Report/DEPLOYMENT_PHASES.md](DEPLOYMENT_PHASES.md) - 배포 3단계
3. [docs/OPERATIONAL_RUNBOOK.md](../docs/OPERATIONAL_RUNBOOK.md) - 운영 가이드

### 선택 읽을거리

1. [docs/DEPLOYMENT_GUIDE.md](../docs/DEPLOYMENT_GUIDE.md) - 전체 배포 가이드
2. [docs/vpn-migration-and-testing-guide.md](../docs/vpn-migration-and-testing-guide.md) - VPN 상세
3. [docs/tgw-migration-guide.md](../docs/tgw-migration-guide.md) - TGW 상세

### AWS 공식 문서

- [Transit Gateway](https://docs.aws.amazon.com/vpc/latest/tgw/)
- [VPC Endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/)
- [Route53 Resolver](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver.html)
- [Bedrock Knowledge Base](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless.html)

---

## 🎓 학습 완료 체크리스트

### 이론 학습
- [ ] 시스템 목적 이해
- [ ] 아키텍처 이해
- [ ] 배포 3단계 이해
- [ ] 데이터 흐름 이해
- [ ] 보안 정책 이해

### 실습
- [ ] 네트워크 레이어 배포
- [ ] 앱 레이어 배포
- [ ] 모니터링 레이어 배포
- [ ] VPN 연결성 테스트
- [ ] DNS 해석 테스트
- [ ] API 엔드포인트 테스트
- [ ] 문서 업로드 테스트
- [ ] RAG 질의 테스트

### 운영
- [ ] CloudWatch 대시보드 확인
- [ ] 알람 설정 확인
- [ ] 로그 조회 방법 학습
- [ ] 트러블슈팅 방법 학습

---

## 📞 질문 및 지원

**질문이 있으신가요?**

1. 먼저 [docs/OPERATIONAL_RUNBOOK.md](../docs/OPERATIONAL_RUNBOOK.md)의 트러블슈팅 섹션 확인
2. 팀 Slack 채널에 질문 (예: #bos-ai-rag)
3. 담당자에게 직접 연락

---

**작성일**: 2026-03-06  
**버전**: 1.0  
**대상**: 팀원 교육용
