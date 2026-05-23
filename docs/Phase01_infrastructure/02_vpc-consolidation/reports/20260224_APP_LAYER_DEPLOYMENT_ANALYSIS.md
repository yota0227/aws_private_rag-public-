# App Layer 배포 분석 및 수정 계획

작성일: 2026-02-24

## 1. 배포 상태 확인

### Network Layer (배포 완료)
- **상태**: ✅ 배포 완료 (20개 리소스)
- **리전**: Seoul (ap-northeast-2), US East (us-east-1)
- **주요 리소스**:
  - Seoul VPC: `vpc-0f759f00e5df658d1` (10.10.0.0/16)
  - US VPC: `bos-ai-us-vpc-prod` (10.20.0.0/16)
  - VPC Peering: Seoul ↔ US 양방향
  - VPN Gateway: Seoul VPC에 연결
  - Security Groups, Route Tables, Subnets

### App Layer (배포 안 됨)
- **상태**: ❌ 배포 안 됨
- **확인 사항**:
  - `.terraform` 디렉토리 없음 → terraform init 실행 안 됨
  - `tfplan` 파일만 존재 (바이너리)
  - 실제 AWS 리소스 배포 안 됨

## 2. 심각한 문제점 발견

### 문제 1: 잘못된 VPC ID 하드코딩

App Layer의 모든 리소스 정의 파일이 **기존 서비스 VPC**를 참조하고 있습니다:

#### `lambda.tf`
```hcl
resource "aws_security_group" "lambda" {
  vpc_id = "vpc-066c464f9c750ee9e"  # ❌ 기존 서비스 VPC (10.200.0.0/16)
  # 올바른 값: vpc-0f759f00e5df658d1 (BOS-AI VPC 10.10.0.0/16)
}

resource "aws_lambda_function" "document_processor" {
  vpc_config {
    subnet_ids = ["subnet-0f027e9de8e26c18f", "subnet-0625d992edf151017"]  # ❌ 하드코딩
    # 올바른 값: data.terraform_remote_state.network.outputs.seoul_private_subnet_ids
  }
}
```

#### `opensearch-serverless.tf`
```hcl
resource "aws_security_group" "opensearch" {
  vpc_id = "vpc-066c464f9c750ee9e"  # ❌ 기존 서비스 VPC
}

resource "aws_opensearchserverless_vpc_endpoint" "main" {
  vpc_id     = "vpc-066c464f9c750ee9e"  # ❌ 기존 서비스 VPC
  subnet_ids = ["subnet-0f027e9de8e26c18f", "subnet-0625d992edf151017"]  # ❌ 하드코딩
}
```

#### `bedrock-kb.tf`
```hcl
resource "aws_security_group" "bedrock_kb" {
  vpc_id = "vpc-066c464f9c750ee9e"  # ❌ 기존 서비스 VPC
}
```

### 문제 2: 리전 혼동

- **현재 코드**: 모든 리소스가 Seoul 리전에 배포되도록 설정
- **원래 계획**: 
  - Seoul (ap-northeast-2): Frontend - VPN 접근
  - US East (us-east-1): Backend - Bedrock, OpenSearch, Lambda

**App Layer 리소스는 US East 리전에 배포되어야 합니다!**

### 문제 3: main.tf와 실제 리소스 파일 불일치

- `main.tf`: 모듈 기반 구조로 작성됨
- `lambda.tf`, `opensearch-serverless.tf`, `bedrock-kb.tf`: 직접 리소스 정의
- **결과**: 모듈을 호출하지만 실제로는 직접 정의된 리소스가 배포됨

## 3. 아키텍처 목적 재확인

### Seoul VPC (10.10.0.0/16) - Frontend
- **역할**: VPN 접근 포인트
- **리소스**: VPN Gateway, Private Subnets
- **접근**: VPN을 통해서만 접근
- **연결**: VPC Peering을 통해 US VPC와 연결

### US VPC (10.20.0.0/16) - Backend
- **역할**: AI 워크로드 호스팅
- **리소스**: 
  - Lambda (문서 처리)
  - OpenSearch Serverless (벡터 검색)
  - Bedrock Knowledge Base (RAG)
  - S3 (문서 저장)
- **접근**: Seoul VPC에서 VPC Peering을 통해 접근

## 4. 수정 계획

### 4.1 VPC ID 수정

모든 하드코딩된 VPC ID를 Terraform Remote State 참조로 변경:

```hcl
# 변경 전
vpc_id = "vpc-066c464f9c750ee9e"

# 변경 후 (US VPC 사용)
vpc_id = data.terraform_remote_state.network.outputs.us_vpc_id
```

### 4.2 Subnet ID 수정

모든 하드코딩된 Subnet ID를 Terraform Remote State 참조로 변경:

```hcl
# 변경 전
subnet_ids = ["subnet-0f027e9de8e26c18f", "subnet-0625d992edf151017"]

# 변경 후
subnet_ids = data.terraform_remote_state.network.outputs.us_private_subnet_ids
```

### 4.3 리전 설정 확인

- `providers.tf`에서 US East 리전 설정 확인
- 모든 리소스가 US East 리전에 배포되도록 설정

### 4.4 Security Group 규칙 수정

CIDR 블록을 올바른 VPC CIDR로 변경:

```hcl
# 변경 전
cidr_blocks = ["10.200.0.0/16"]  # 기존 서비스 VPC

# 변경 후
cidr_blocks = ["10.10.0.0/16"]   # Seoul VPC (Frontend)
```

## 5. 배포 순서

1. **VPC ID 및 Subnet ID 수정**
   - `lambda.tf`
   - `opensearch-serverless.tf`
   - `bedrock-kb.tf`

2. **Security Group 규칙 수정**
   - CIDR 블록 업데이트
   - Seoul VPC (10.10.0.0/16)와 US VPC (10.20.0.0/16) 간 통신 허용

3. **Terraform 초기화 및 검증**
   ```bash
   cd environments/app-layer/bedrock-rag
   terraform init
   terraform validate
   terraform plan
   ```

4. **배포**
   ```bash
   terraform apply
   ```

## 6. 배포 예정 리소스 목록

### US East Region (Backend)

#### Compute
- Lambda Function: `lambda-document-processor-us-prod`
- Lambda IAM Role: `role-lambda-document-processor-us-prod`
- Lambda Security Group: `lambda-bos-ai-us-prod`

#### Data
- OpenSearch Serverless Collection: `bos-ai-vectors-prod`
- OpenSearch VPC Endpoint: `vpce-opensearch-us-prod`
- OpenSearch Security Group: `opensearch-bos-ai-us-prod`
- Bedrock Knowledge Base: `bos-ai-kb-us-prod`
- Bedrock IAM Role: `role-bedrock-kb-us-prod`
- Bedrock Security Group: `bedrock-kb-bos-ai-us-prod`

#### Storage
- S3 Bucket (Source): `bos-ai-documents-us`
- S3 Bucket (Destination): `bos-ai-documents-processed-us`

#### Security
- KMS Key: BOS-AI 암호화 키
- IAM Policies: Lambda, Bedrock, OpenSearch 접근 정책
- VPC Endpoints: Bedrock, S3, OpenSearch

#### Monitoring
- CloudWatch Log Groups: Lambda, OpenSearch, Bedrock
- CloudWatch Alarms: Lambda 오류, OpenSearch 용량
- CloudWatch Dashboard: 전체 시스템 모니터링
- VPC Flow Logs: US VPC 네트워크 트래픽

#### Audit
- CloudTrail: API 호출 감사 로그

#### Cost Management
- AWS Budgets: 월별 예산 알림

**총 예상 리소스**: 약 30개

## 7. 다음 단계

1. ✅ 문제점 파악 완료
2. ⏳ VPC ID 및 Subnet ID 수정 필요
3. ⏳ Security Group 규칙 수정 필요
4. ⏳ Terraform 초기화 및 배포 필요
5. ⏳ 배포 후 검증 필요

## 8. 주의사항

- **절대 기존 서비스 VPC (`vpc-066c464f9c750ee9e`)를 건드리지 말 것**
- **모든 BOS-AI 리소스는 새로운 VPC에만 배포**
  - Seoul: `vpc-0f759f00e5df658d1` (10.10.0.0/16)
  - US: `bos-ai-us-vpc-prod` (10.20.0.0/16)
- **VPN 접근만 허용** (Seoul VPC는 IGW 없음)
- **VPC Peering을 통한 Seoul ↔ US 통신**
