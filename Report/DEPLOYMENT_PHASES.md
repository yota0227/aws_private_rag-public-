# BOS-AI RAG 배포 3단계 상세 가이드

## 📋 개요

BOS-AI RAG 시스템은 온프렘과 AWS를 연결하는 하이브리드 AI 인프라입니다. 배포는 3단계로 진행되며, 각 단계는 독립적이면서도 순차적으로 진행되어야 합니다.

**배포 순서**:
1. **네트워크 레이어** (Network Layer) - 기반 인프라
2. **앱 레이어** (App Layer) - AI 워크로드
3. **모니터링 레이어** (Monitoring Layer) - 운영 관리

---

## 🌐 1단계: 네트워크 레이어 배포

### 목적
온프렘과 AWS를 연결하는 기반 네트워크 인프라 구축

### 배포 위치
```
environments/network-layer/
```

### 구성 요소

#### 1.1 VPC 구성 (3개)
| VPC | CIDR | 용도 | 리전 |
|-----|------|------|------|
| Private RAG VPC | 10.10.0.0/16 | 프론트엔드 (Lambda, API Gateway) | ap-northeast-2 (Seoul) |
| US Backend VPC | 10.20.0.0/16 | 백엔드 (Bedrock, OpenSearch) | us-east-1 (Virginia) |
| Logging VPC | 10.200.0.0/16 | 중앙 로깅 및 모니터링 | ap-northeast-2 (Seoul) |

#### 1.2 Transit Gateway (TGW)
- **ID**: tgw-0897383168475b532
- **역할**: 3개 VPC 간 라우팅 중앙화
- **라우트 테이블**: 각 VPC별 독립적 라우팅 정책

#### 1.3 VPC 피어링
- **ID**: pcx-0a44f0b90565313f7
- **연결**: Private RAG VPC (10.10.0.0/16) ↔ US Backend VPC (10.20.0.0/16)
- **용도**: 크로스 리전 데이터 전송

#### 1.4 Route53 Resolver Inbound Endpoint
- **ID**: rslvr-in-93384eeb51fc4c4db
- **IP**: 10.10.1.34 (AZ-a), 10.10.2.144 (AZ-b)
- **용도**: 온프렘 DNS 쿼리 수신 및 AWS Private Hosted Zone 해석

#### 1.5 VPC Endpoints (Private RAG VPC)
| 서비스 | ID | 용도 |
|--------|-----|------|
| execute-api | vpce-0e5f61dd7bd52882e | API Gateway 접근 |
| S3 Gateway | vpce-08474f7814c698b6c | S3 접근 |
| CloudWatch Logs | vpce-0f017558595dedd41 | 로그 전송 |
| Secrets Manager | vpce-075ba17f3151048ba | 시크릿 관리 |
| OpenSearch AOSS | vpce-013aa002a16145cd0 | OpenSearch 접근 |
| Bedrock Runtime | vpce-0fe70be9fc4fd10ea | Bedrock 접근 |

#### 1.6 Security Groups
- **VPC Endpoints SG**: HTTPS (443) from 192.128.0.0/16 (온프렘) + 10.10.0.0/16 (Seoul VPC)
- **Route53 Resolver SG**: DNS (53) TCP/UDP from 192.128.0.0/16

### 배포 명령어
```bash
cd environments/network-layer
terraform init
terraform plan
terraform apply
```

### 검증 항목
- [ ] 3개 VPC 생성 확인
- [ ] TGW 라우팅 테이블 확인
- [ ] VPC 피어링 활성화 확인
- [ ] Route53 Resolver Inbound 엔드포인트 OPERATIONAL 상태 확인
- [ ] VPC Endpoints 생성 확인

### 산출물
- Terraform State: `environments/network-layer/terraform.tfstate`
- 리소스 ID 목록: [Report/20260303_AWS_RESOURCES_INVENTORY.md](20260303_AWS_RESOURCES_INVENTORY.md)

---

## 🤖 2단계: 앱 레이어 배포

### 목적
AI 워크로드 및 API 엔드포인트 구축

### 배포 위치
```
environments/app-layer/bedrock-rag/
```

### 구성 요소

#### 2.1 프론트엔드 (Seoul - Private RAG VPC)

**Lambda 함수**
- **이름**: lambda-document-processor-seoul-prod
- **런타임**: Python 3.12
- **메모리**: 512 MB
- **타임아웃**: 300초
- **VPC**: Private RAG VPC (10.10.1.0/24, 10.10.2.0/24)
- **역할**: 문서 처리 및 OpenSearch 인덱싱

**API Gateway**
- **ID**: r0qa9lzhgi
- **타입**: PRIVATE (VPC Endpoint 경유만)
- **엔드포인트**:
  - `POST /rag/query` - RAG 질의
  - `POST /rag/documents` - 문서 업로드
  - `GET /rag/health` - 헬스 체크
- **도메인**: rag.corp.bos-semi.com
- **정책**: 온프렘 (192.128.0.0/16) + VPC Endpoint 허용

**S3 (Seoul)**
- **버킷**: bos-ai-documents-seoul-v3
- **용도**: 온프렘에서 업로드된 문서 임시 저장
- **정책**: VPC Endpoint 경유만 접근
- **암호화**: KMS (Seoul)
- **버전 관리**: 활성화 (크로스 리전 복제 필수)

#### 2.2 백엔드 (Virginia - US Backend VPC)

**OpenSearch Serverless**
- **컬렉션 ID**: iw3pzcloa0en8d90hh7
- **이름**: bos-ai-vectors
- **리전**: us-east-1 (Virginia)
- **용도**: 벡터 저장소 (Bedrock 임베딩)
- **VPC Endpoint**: vpce-013aa002a16145cd0 (Seoul에서 접근)

**Bedrock Knowledge Base**
- **ID**: FNNOP3VBZV
- **이름**: bos-ai-kb-dev
- **모델**: Amazon Titan Embed Text v1
- **데이터 소스**: S3 (bos-ai-documents-us)
- **벡터 저장소**: OpenSearch Serverless (Virginia)

**S3 (Virginia)**
- **버킷**: bos-ai-documents-us
- **용도**: Bedrock Knowledge Base 데이터 소스
- **정책**: Bedrock KB 역할만 접근
- **암호화**: KMS (Virginia)

#### 2.3 크로스 리전 복제
- **소스**: bos-ai-documents-seoul-v3 (Seoul)
- **대상**: bos-ai-documents-us (Virginia)
- **복제 시간**: 15분 이내
- **암호화**: KMS 키 자동 재암호화

### 배포 명령어
```bash
cd environments/app-layer/bedrock-rag
terraform init
terraform plan
terraform apply
```

### 배포 순서 (중요!)
1. 네트워크 레이어 완료 후 진행
2. Lambda 함수 배포 패키지 준비
3. Terraform apply 실행

### 검증 항목
- [ ] Lambda 함수 생성 확인
- [ ] API Gateway 배포 확인
- [ ] S3 버킷 생성 및 정책 확인
- [ ] OpenSearch 컬렉션 생성 확인
- [ ] Bedrock Knowledge Base 생성 확인
- [ ] 크로스 리전 복제 활성화 확인

### 산출물
- Terraform State: `environments/app-layer/bedrock-rag/terraform.tfstate`
- Lambda 배포 패키지: `environments/app-layer/bedrock-rag/lambda-deployment-package.zip`
- 리소스 ID 목록: [Report/20260303_AWS_RESOURCES_INVENTORY.md](20260303_AWS_RESOURCES_INVENTORY.md)

---

## 📊 3단계: 모니터링 레이어 배포

### 목적
운영 및 모니터링 인프라 구축

### 배포 위치
```
environments/monitoring/
```

### 구성 요소

#### 3.1 CloudWatch
- **로그 그룹**: Lambda, Bedrock, OpenSearch 로그 수집
- **메트릭**: Lambda 성능, API 응답 시간
- **대시보드**: 실시간 모니터링

#### 3.2 CloudTrail
- **로깅**: 모든 AWS API 호출 기록
- **저장소**: S3 (bos-ai-cloudtrail-logs)
- **보존**: 90일

#### 3.3 알람
- Lambda 에러율 > 1%
- API 응답 시간 > 5초
- OpenSearch 인덱싱 실패

### 배포 명령어
```bash
cd environments/monitoring
terraform init
terraform plan
terraform apply
```

### 검증 항목
- [ ] CloudWatch 로그 그룹 생성 확인
- [ ] CloudTrail 활성화 확인
- [ ] 알람 생성 확인

---

## 🔄 데이터 흐름

```
온프렘 (192.128.0.0/16)
    ↓ VPN (IPsec)
Transit Gateway
    ↓
Private RAG VPC (Seoul)
    ├─ API Gateway (rag.corp.bos-semi.com)
    │   ↓
    ├─ Lambda (문서 처리)
    │   ├─ S3 (Seoul) - 문서 임시 저장
    │   │   ↓ 크로스 리전 복제
    │   │   S3 (Virginia)
    │   │       ↓
    │   │   Bedrock KB (Virginia)
    │   │       ↓
    │   │   OpenSearch (Virginia)
    │   │
    │   └─ OpenSearch VPC Endpoint (Seoul)
    │       ↓
    │       OpenSearch (Virginia)
    │
    └─ Route53 Resolver Inbound
        ↓
        DNS 쿼리 응답
```

---

## 📝 주요 설정 파일

### 네트워크 레이어
- `environments/network-layer/main.tf` - VPC, TGW, 피어링
- `environments/network-layer/route53-resolver.tf` - DNS 설정
- `environments/network-layer/vpc-endpoints.tf` - VPC 엔드포인트

### 앱 레이어
- `environments/app-layer/bedrock-rag/lambda.tf` - Lambda 함수
- `environments/app-layer/bedrock-rag/api-gateway.tf` - API Gateway
- `environments/app-layer/bedrock-rag/s3-upload-pipeline.tf` - S3 및 복제
- `environments/app-layer/bedrock-rag/opensearch.tf` - OpenSearch
- `environments/app-layer/bedrock-rag/bedrock-kb.tf` - Bedrock KB

---

## ✅ 배포 체크리스트

### 배포 전
- [ ] AWS 자격증명 설정
- [ ] Terraform 설치 (>= 1.0)
- [ ] 변수 파일 준비 (terraform.tfvars)

### 1단계 배포
- [ ] 네트워크 레이어 terraform apply 완료
- [ ] 모든 VPC 생성 확인
- [ ] TGW 라우팅 확인
- [ ] VPC Endpoints 생성 확인

### 2단계 배포
- [ ] Lambda 배포 패키지 준비
- [ ] 앱 레이어 terraform apply 완료
- [ ] API Gateway 배포 확인
- [ ] S3 크로스 리전 복제 활성화 확인
- [ ] Bedrock KB 생성 확인

### 3단계 배포
- [ ] 모니터링 레이어 terraform apply 완료
- [ ] CloudWatch 로그 수집 확인
- [ ] 알람 설정 확인

### 배포 후
- [ ] VPN 연결성 테스트
- [ ] DNS 해석 테스트
- [ ] API 엔드포인트 테스트
- [ ] 문서 업로드 및 처리 테스트

---

## 🔗 관련 문서

- [VPN 연결성 테스트 결과](20260303_VPN_CONNECTIVITY_TEST_RESULTS.md)
- [DNS 테스트 결과](20260303_DNS_LOOKUP_TEST_RESULTS.md)
- [AWS 리소스 인벤토리](20260303_AWS_RESOURCES_INVENTORY.md)
- [FortiGate VPN 설정 가이드](20260303_FORTIGATE_TGW_VPN_SETUP_GUIDE.md)

---

**작성일**: 2026-03-06  
**버전**: 1.0  
**상태**: 배포 완료
