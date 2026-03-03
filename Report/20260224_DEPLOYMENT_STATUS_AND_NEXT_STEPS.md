# 배포 상태 및 다음 단계

작성일: 2026-02-24

## 현재 배포 상태

### ✅ Network Layer (완료)
- **배포 상태**: 완료
- **리소스 수**: 20개
- **리전**: Seoul (ap-northeast-2), US East (us-east-1)

#### Seoul VPC (10.10.0.0/16)
- VPC ID: `vpc-0f759f00e5df658d1`
- Private Subnets: 2개 (AZ-a, AZ-c)
- VPN Gateway: 연결됨
- Security Groups: Lambda, OpenSearch, VPC Endpoints
- **역할**: Frontend - VPN 접근 포인트

#### US VPC (10.20.0.0/16)
- VPC ID: `bos-ai-us-vpc-prod`
- Private Subnets: 2개 (AZ-a, AZ-b)
- Security Groups: Lambda, OpenSearch, VPC Endpoints
- **역할**: Backend - AI 워크로드 호스팅

#### VPC Peering
- Seoul ↔ US 양방향 연결
- Route Tables 업데이트 완료

### ❌ App Layer (배포 안 됨)
- **배포 상태**: 미배포
- **문제점**: 
  1. Terraform 초기화 안 됨 (`.terraform` 디렉토리 없음)
  2. 잘못된 VPC ID 하드코딩 (기존 서비스 VPC 참조)
  3. 잘못된 Subnet ID 하드코딩
  4. 리전 혼동 (Seoul vs US)

## 발견된 문제점

### 1. 잘못된 VPC ID 하드코딩

모든 App Layer 리소스가 **기존 서비스 VPC**를 참조:
- 하드코딩된 VPC ID: `vpc-066c464f9c750ee9e` (10.200.0.0/16)
- 올바른 VPC ID: `bos-ai-us-vpc-prod` (10.20.0.0/16)

**영향받는 파일**:
- `lambda.tf`: Security Group, Lambda VPC Config
- `opensearch-serverless.tf`: Security Group, VPC Endpoint
- `bedrock-kb.tf`: Security Group

### 2. 잘못된 Subnet ID 하드코딩

하드코딩된 Subnet IDs:
- `subnet-0f027e9de8e26c18f`
- `subnet-0625d992edf151017`

이 Subnet들이 어느 VPC에 속하는지 불명확하며, Terraform Remote State를 사용해야 합니다.

### 3. 리전 혼동

- **현재 코드**: 일부 리소스가 Seoul 리전 (`provider = aws.seoul`) 사용
- **올바른 설정**: 모든 App Layer 리소스는 US East 리전 사용

### 4. CIDR 블록 오류

Security Group 규칙에서 잘못된 CIDR 블록 사용:
- `10.200.0.0/16` (기존 서비스 VPC) → `10.20.0.0/16` (US VPC) 또는 `10.10.0.0/16` (Seoul VPC)

## 수정 계획

### Phase 1: 코드 수정

#### 1.1 data.tf 수정
```hcl
locals {
  # 추가 필요
  us_vpc_cidr    = data.terraform_remote_state.network.outputs.us_vpc_cidr
  seoul_vpc_cidr = data.terraform_remote_state.network.outputs.seoul_vpc_cidr
}
```

#### 1.2 lambda.tf 수정
- VPC ID: `"vpc-066c464f9c750ee9e"` → `local.us_vpc_id`
- Subnet IDs: 하드코딩 → `local.us_private_subnet_ids`
- CIDR 블록: `"10.200.0.0/16"` → `local.us_vpc_cidr`
- Provider: 모든 리소스에 `provider = aws` (기본 US 리전)

#### 1.3 opensearch-serverless.tf 수정
- VPC ID: `"vpc-066c464f9c750ee9e"` → `local.us_vpc_id`
- Subnet IDs: 하드코딩 → `local.us_private_subnet_ids`
- Provider: `aws.seoul` → `aws` (기본 US 리전)
- Ingress 규칙: Seoul VPC CIDR 허용

#### 1.4 bedrock-kb.tf 수정
- VPC ID: `"vpc-066c464f9c750ee9e"` → `local.us_vpc_id`
- CIDR 블록: `"10.200.0.0/16"` → `local.us_vpc_cidr`
- Provider: 모든 리소스에 `provider = aws` (기본 US 리전)

### Phase 2: Terraform 초기화 및 검증

```bash
cd environments/app-layer/bedrock-rag
terraform init
terraform validate
terraform plan
```

### Phase 3: 배포

```bash
terraform apply
```

### Phase 4: 검증

1. **리소스 확인**
   - Lambda 함수가 US VPC에 배포되었는지
   - OpenSearch Serverless가 US VPC에 배포되었는지
   - Bedrock Knowledge Base가 US 리전에 배포되었는지

2. **네트워크 연결 확인**
   - Seoul VPC → US VPC (VPC Peering)
   - Lambda → OpenSearch (Security Group)
   - Bedrock KB → OpenSearch (Security Group)

3. **로그 확인**
   - CloudWatch Logs에 로그 기록되는지
   - 오류 없이 정상 작동하는지

## 배포 예정 리소스 (US East Region)

### Compute (3개)
1. Lambda Function: `lambda-document-processor-us-prod`
2. Lambda IAM Role: `role-lambda-document-processor-us-prod`
3. Lambda Security Group: `lambda-bos-ai-us-prod`

### Data (6개)
4. OpenSearch Serverless Collection: `bos-ai-vectors-prod`
5. OpenSearch VPC Endpoint: `vpce-opensearch-us-prod`
6. OpenSearch Security Group: `opensearch-bos-ai-us-prod`
7. Bedrock Knowledge Base: `bos-ai-kb-us-prod`
8. Bedrock IAM Role: `role-bedrock-kb-us-prod`
9. Bedrock Security Group: `bedrock-kb-bos-ai-us-prod`

### Storage (2개)
10. S3 Bucket (Source): `bos-ai-documents-us`
11. S3 Bucket (Destination): `bos-ai-documents-processed-us`

### Security (5개)
12. KMS Key: BOS-AI 암호화 키
13. IAM Policy: Lambda S3 Access
14. IAM Policy: Lambda OpenSearch Access
15. IAM Policy: Bedrock KB S3 Access
16. IAM Policy: Bedrock KB OpenSearch Access

### Monitoring (7개)
17. CloudWatch Log Group: Lambda
18. CloudWatch Log Group: OpenSearch
19. CloudWatch Log Group: Bedrock KB
20. CloudWatch Alarm: Lambda Errors
21. CloudWatch Alarm: OpenSearch Capacity
22. CloudWatch Dashboard: System Overview
23. VPC Flow Logs: US VPC

### Audit (2개)
24. CloudTrail: API Audit Logs
25. CloudTrail S3 Bucket: `bos-ai-cloudtrail-logs`

### Cost Management (1개)
26. AWS Budget: Monthly Budget Alert

### VPC Endpoints (4개)
27. VPC Endpoint: Bedrock Runtime
28. VPC Endpoint: Bedrock Agent Runtime
29. VPC Endpoint: S3
30. VPC Endpoint: OpenSearch

**총 예상 리소스**: 약 30개

## 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                        On-Premises                               │
│                      (192.128.0.0/16)                            │
└────────────────────────────┬────────────────────────────────────┘
                             │ VPN
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Seoul VPC (10.10.0.0/16)                       │
│                   vpc-0f759f00e5df658d1                          │
│                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │ Private Subnet  │  │ Private Subnet  │                       │
│  │   AZ-a          │  │   AZ-c          │                       │
│  └─────────────────┘  └─────────────────┘                       │
│                                                                   │
│  - VPN Gateway                                                   │
│  - Security Groups                                               │
│  - Route Tables                                                  │
│                                                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ VPC Peering
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    US VPC (10.20.0.0/16)                         │
│                   bos-ai-us-vpc-prod                             │
│                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │ Private Subnet  │  │ Private Subnet  │                       │
│  │   AZ-a          │  │   AZ-b          │                       │
│  │                 │  │                 │                       │
│  │  ┌──────────┐   │  │  ┌──────────┐   │                       │
│  │  │ Lambda   │   │  │  │ Lambda   │   │                       │
│  │  └────┬─────┘   │  │  └────┬─────┘   │                       │
│  │       │         │  │       │         │                       │
│  │       ▼         │  │       ▼         │                       │
│  │  ┌──────────┐   │  │  ┌──────────┐   │                       │
│  │  │OpenSearch│◄──┼──┼──┤OpenSearch│   │                       │
│  │  │Serverless│   │  │  │Serverless│   │                       │
│  │  └────┬─────┘   │  │  └────┬─────┘   │                       │
│  │       │         │  │       │         │                       │
│  │       ▼         │  │       ▼         │                       │
│  │  ┌──────────┐   │  │  ┌──────────┐   │                       │
│  │  │ Bedrock  │   │  │  │ Bedrock  │   │                       │
│  │  │    KB    │   │  │  │    KB    │   │                       │
│  │  └──────────┘   │  │  └──────────┘   │                       │
│  └─────────────────┘  └─────────────────┘                       │
│                                                                   │
│  - Security Groups                                               │
│  - VPC Endpoints (Bedrock, S3, OpenSearch)                       │
│  - Route Tables                                                  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## 다음 단계

### 즉시 수행
1. ✅ 문제점 파악 완료
2. ✅ 수정 계획 수립 완료
3. ⏳ **코드 수정 시작** ← 현재 단계
   - data.tf
   - lambda.tf
   - opensearch-serverless.tf
   - bedrock-kb.tf

### 코드 수정 후
4. ⏳ Terraform 초기화 및 검증
5. ⏳ Terraform 배포
6. ⏳ 배포 후 검증

### 배포 후
7. ⏳ 네트워크 연결 테스트
8. ⏳ Lambda 함수 테스트
9. ⏳ Bedrock Knowledge Base 테스트
10. ⏳ 문서 업데이트

## 주의사항

### 절대 금지
- ❌ 기존 서비스 VPC (`vpc-066c464f9c750ee9e`, 10.200.0.0/16) 건드리지 말 것
- ❌ 하드코딩된 VPC ID, Subnet ID 사용하지 말 것
- ❌ Seoul 리전에 App Layer 리소스 배포하지 말 것

### 반드시 준수
- ✅ 모든 App Layer 리소스는 US East 리전에 배포
- ✅ Terraform Remote State를 통한 VPC ID, Subnet ID 참조
- ✅ VPC Peering을 통한 Seoul ↔ US 통신
- ✅ VPN을 통한 On-Premises → Seoul 접근

## 참고 문서

- `20260224_ACCURATE_ARCHITECTURE.md`: 정확한 아키텍처 문서
- `20260224_APP_LAYER_DEPLOYMENT_ANALYSIS.md`: App Layer 배포 분석
- `20260224_APP_LAYER_FIX_PLAN.md`: 상세 수정 계획
- `20260224_CLEANUP_SUMMARY.md`: 문서 정리 요약
