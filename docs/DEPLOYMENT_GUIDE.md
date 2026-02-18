# AWS Bedrock RAG Deployment Guide

## Overview

이 가이드는 AWS Bedrock 기반 RAG(Retrieval-Augmented Generation) 시스템을 Terraform IaC로 배포하는 절차를 설명합니다. 시스템은 서울(ap-northeast-2)과 미국 동부(us-east-1) 리전에 걸쳐 구성되며, 기존 VPN 환경과 통합됩니다.

## Prerequisites

### Required Tools

- **Terraform**: v1.5.0 이상
  ```bash
  terraform version
  ```

- **AWS CLI**: v2.0 이상
  ```bash
  aws --version
  ```

- **Go**: v1.21 이상 (테스트 실행 시)
  ```bash
  go version
  ```

### AWS Credentials

AWS 자격 증명을 구성합니다:

```bash
# AWS CLI 프로필 설정
aws configure --profile bos-ai

# 또는 환경 변수 설정
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="ap-northeast-2"
```

### Required AWS Permissions

배포를 위해 다음 권한이 필요합니다:

- VPC, Subnet, Route Table 생성 및 관리
- VPC Peering 연결 생성 및 관리
- S3 버킷 생성 및 관리
- Lambda 함수 생성 및 관리
- IAM Role 및 Policy 생성 및 관리
- KMS Key 생성 및 관리
- Bedrock Knowledge Base 생성 및 관리
- OpenSearch Serverless 컬렉션 생성 및 관리
- CloudWatch Logs 및 Alarms 생성
- CloudTrail 구성

### Bedrock Model Access

Bedrock 모델에 대한 액세스를 활성화합니다:

1. AWS Console에서 Bedrock 서비스로 이동
2. Model access 메뉴 선택
3. 다음 모델에 대한 액세스 요청:
   - Anthropic Claude v2
   - Amazon Titan Embeddings

## Deployment Architecture

배포는 3개의 레이어로 구성됩니다:

```
1. Global Layer (Backend 및 IAM)
   ↓
2. Network Layer (VPC, Peering, Security Groups)
   ↓
3. App Layer (Bedrock, OpenSearch, S3, Lambda)
```

## Deployment Order

### Step 1: Global Infrastructure Setup

전역 인프라(Terraform 백엔드 및 IAM)를 배포합니다.

```bash
cd environments/global/backend

# 변수 파일 생성
cat > terraform.tfvars <<EOF
state_bucket_name = "bos-ai-terraform-state"
lock_table_name   = "terraform-state-lock"
region            = "ap-northeast-2"
environment       = "prod"
EOF

# 초기화 및 배포
terraform init
terraform plan
terraform apply
```

**검증:**
```bash
# S3 버킷 확인
aws s3 ls | grep bos-ai-terraform-state

# DynamoDB 테이블 확인
aws dynamodb describe-table --table-name terraform-state-lock
```

### Step 2: Import Existing VPN Resources

기존 VPN Gateway를 Terraform으로 가져옵니다.

```bash
# VPN Gateway ID 확인
cd ../../../scripts
./identify-vpn-gateway.sh

# 출력 예시:
# VPN Gateway ID: vgw-1234567890abcdef0
# VPC ID: vpc-0abcdef1234567890
# State: available
```

VPN Gateway ID를 기록하고 다음 단계에서 사용합니다.

### Step 3: Network Layer Deployment

네트워크 레이어를 배포합니다.

```bash
cd ../environments/network-layer

# 변수 파일 생성
cat > terraform.tfvars <<EOF
# VPC Configuration
seoul_vpc_cidr = "10.10.0.0/16"
us_vpc_cidr    = "10.20.0.0/16"

seoul_private_subnet_cidrs = ["10.10.1.0/24", "10.10.2.0/24"]
us_private_subnet_cidrs    = ["10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"]

seoul_availability_zones = ["ap-northeast-2a", "ap-northeast-2c"]
us_availability_zones    = ["us-east-1a", "us-east-1b", "us-east-1c"]

# VPN Gateway (기존 리소스)
existing_vpn_gateway_id = "vgw-1234567890abcdef0"  # Step 2에서 확인한 ID

# Environment
environment = "prod"
project     = "BOS-AI-RAG"

# Tags
tags = {
  Project     = "BOS-AI-RAG"
  Environment = "prod"
  ManagedBy   = "Terraform"
  CostCenter  = "AI-Infrastructure"
  Owner       = "AI-Team"
}
EOF

# 백엔드 초기화
terraform init

# 계획 검토
terraform plan

# 배포 실행
terraform apply
```

**검증:**
```bash
# VPC 확인
terraform output seoul_vpc_id
terraform output us_vpc_id

# VPC Peering 확인
terraform output peering_connection_id
aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids $(terraform output -raw peering_connection_id)

# Route Table 확인
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=$(terraform output -raw seoul_vpc_id)"
```

### Step 4: App Layer Deployment

애플리케이션 레이어를 배포합니다.

```bash
cd ../app-layer/bedrock-rag

# 변수 파일 생성
cat > terraform.tfvars <<EOF
# Knowledge Base Configuration
knowledge_base_name = "bos-ai-rag-kb"
embedding_model_arn = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1"
foundation_model_arn = "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2"

# OpenSearch Configuration
opensearch_collection_name = "bos-ai-vectors"
opensearch_index_name      = "bedrock-knowledge-base-index"
vector_dimension           = 1536

opensearch_capacity_units = {
  search_ocu   = 2
  indexing_ocu = 2
}

# S3 Configuration
source_bucket_name      = "bos-ai-documents-seoul"
destination_bucket_name = "bos-ai-documents-us"

# Lambda Configuration
lambda_function_name = "bos-ai-document-processor"
lambda_runtime       = "python3.11"
lambda_memory_size   = 1024
lambda_timeout       = 300

# Environment
environment = "prod"
project     = "BOS-AI-RAG"

# Tags
tags = {
  Project     = "BOS-AI-RAG"
  Environment = "prod"
  ManagedBy   = "Terraform"
  CostCenter  = "AI-Infrastructure"
  Layer       = "app"
  Owner       = "AI-Team"
}
EOF

# 백엔드 초기화
terraform init

# 계획 검토
terraform plan

# 배포 실행
terraform apply
```

**검증:**
```bash
# Bedrock Knowledge Base 확인
aws bedrock-agent list-knowledge-bases --region us-east-1

# OpenSearch Serverless 컬렉션 확인
aws opensearchserverless list-collections --region us-east-1

# S3 버킷 확인
aws s3 ls | grep bos-ai-documents

# Lambda 함수 확인
aws lambda get-function --function-name bos-ai-document-processor --region us-east-1
```

## Variable Configuration

### Network Layer Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `seoul_vpc_cidr` | Seoul VPC CIDR 블록 | `10.10.0.0/16` | Yes |
| `us_vpc_cidr` | US VPC CIDR 블록 | `10.20.0.0/16` | Yes |
| `seoul_private_subnet_cidrs` | Seoul 프라이빗 서브넷 CIDR 목록 | `["10.10.1.0/24", "10.10.2.0/24"]` | Yes |
| `us_private_subnet_cidrs` | US 프라이빗 서브넷 CIDR 목록 | `["10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"]` | Yes |
| `seoul_availability_zones` | Seoul AZ 목록 | `["ap-northeast-2a", "ap-northeast-2c"]` | Yes |
| `us_availability_zones` | US AZ 목록 | `["us-east-1a", "us-east-1b", "us-east-1c"]` | Yes |
| `existing_vpn_gateway_id` | 기존 VPN Gateway ID | `vgw-1234567890abcdef0` | Yes |
| `environment` | 환경 이름 | `prod`, `dev`, `staging` | Yes |
| `project` | 프로젝트 이름 | `BOS-AI-RAG` | Yes |

### App Layer Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `knowledge_base_name` | Knowledge Base 이름 | `bos-ai-rag-kb` | Yes |
| `embedding_model_arn` | 임베딩 모델 ARN | `arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1` | Yes |
| `foundation_model_arn` | 생성 모델 ARN | `arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2` | Yes |
| `opensearch_collection_name` | OpenSearch 컬렉션 이름 | `bos-ai-vectors` | Yes |
| `opensearch_capacity_units` | OpenSearch OCU 설정 | `{search_ocu = 2, indexing_ocu = 2}` | Yes |
| `source_bucket_name` | Seoul S3 버킷 이름 | `bos-ai-documents-seoul` | Yes |
| `destination_bucket_name` | US S3 버킷 이름 | `bos-ai-documents-us` | Yes |
| `lambda_function_name` | Lambda 함수 이름 | `bos-ai-document-processor` | Yes |
| `lambda_memory_size` | Lambda 메모리 (MB) | `1024` (최소값) | Yes |
| `lambda_timeout` | Lambda 타임아웃 (초) | `300` (최소값) | Yes |

## Import Procedures for Existing Resources

### VPN Gateway Import

1. **VPN Gateway ID 확인:**
   ```bash
   aws ec2 describe-vpn-gateways --region ap-northeast-2 \
     --filters "Name=state,Values=available"
   ```

2. **Import 블록 추가:**
   
   `environments/network-layer/main.tf`에 다음 추가:
   ```hcl
   import {
     to = aws_vpn_gateway.existing
     id = "vgw-1234567890abcdef0"
   }
   
   resource "aws_vpn_gateway" "existing" {
     vpc_id = module.vpc_seoul.vpc_id
     
     tags = merge(
       local.common_tags,
       {
         Name     = "existing-vpn-gateway"
         Imported = "true"
       }
     )
   }
   ```

3. **Import 실행:**
   ```bash
   terraform plan  # Import 계획 확인
   terraform apply # Import 실행
   ```

4. **검증:**
   ```bash
   terraform state show aws_vpn_gateway.existing
   ```

### Customer Gateway Import (선택사항)

기존 Customer Gateway가 있는 경우:

```bash
# Customer Gateway ID 확인
aws ec2 describe-customer-gateways --region ap-northeast-2

# Import 블록 추가
import {
  to = aws_customer_gateway.existing
  id = "cgw-1234567890abcdef0"
}

resource "aws_customer_gateway" "existing" {
  bgp_asn    = 65000
  ip_address = "203.0.113.1"
  type       = "ipsec.1"
  
  tags = merge(
    local.common_tags,
    {
      Name     = "existing-customer-gateway"
      Imported = "true"
    }
  )
}
```

### VPN Connection Import (선택사항)

기존 VPN Connection이 있는 경우:

```bash
# VPN Connection ID 확인
aws ec2 describe-vpn-connections --region ap-northeast-2

# Import 블록 추가
import {
  to = aws_vpn_connection.existing
  id = "vpn-1234567890abcdef0"
}

resource "aws_vpn_connection" "existing" {
  vpn_gateway_id      = aws_vpn_gateway.existing.id
  customer_gateway_id = aws_customer_gateway.existing.id
  type                = "ipsec.1"
  static_routes_only  = true
  
  tags = merge(
    local.common_tags,
    {
      Name     = "existing-vpn-connection"
      Imported = "true"
    }
  )
}
```

## Troubleshooting

### Common Issues

#### 1. VPC CIDR Overlap Error

**증상:**
```
Error: VPC CIDRs overlap
```

**해결:**
- Seoul과 US VPC의 CIDR 블록이 겹치지 않는지 확인
- 예: Seoul `10.10.0.0/16`, US `10.20.0.0/16`

#### 2. VPC Peering Connection Failed

**증상:**
```
Error: VPC peering connection failed to establish
```

**해결:**
```bash
# Peering 상태 확인
aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids <peering-id>

# 수동으로 수락 (cross-region의 경우)
aws ec2 accept-vpc-peering-connection \
  --vpc-peering-connection-id <peering-id> \
  --region us-east-1
```

#### 3. Bedrock Model Access Denied

**증상:**
```
Error: AccessDeniedException: You don't have access to the model
```

**해결:**
1. AWS Console → Bedrock → Model access
2. 필요한 모델에 대한 액세스 요청
3. 승인 대기 (일반적으로 즉시 승인됨)

#### 4. OpenSearch Capacity Limit

**증상:**
```
Error: Capacity units must be at least 2 for search and indexing
```

**해결:**
- `opensearch_capacity_units` 변수 확인
- 최소값: `search_ocu = 2`, `indexing_ocu = 2`

#### 5. Lambda VPC Configuration Error

**증상:**
```
Error: Lambda function failed to create network interfaces
```

**해결:**
- Lambda execution role에 VPC 권한 확인:
  ```json
  {
    "Effect": "Allow",
    "Action": [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface"
    ],
    "Resource": "*"
  }
  ```

#### 6. S3 Replication Not Working

**증상:**
- 문서가 Seoul 버킷에 업로드되었지만 US 버킷에 복제되지 않음

**해결:**
```bash
# Replication 상태 확인
aws s3api get-bucket-replication --bucket bos-ai-documents-seoul

# 객체 복제 상태 확인
aws s3api head-object \
  --bucket bos-ai-documents-seoul \
  --key <object-key> \
  --query 'ReplicationStatus'
```

#### 7. Terraform State Lock

**증상:**
```
Error: Error acquiring the state lock
```

**해결:**
```bash
# Lock 정보 확인
aws dynamodb get-item \
  --table-name terraform-state-lock \
  --key '{"LockID":{"S":"<state-path>"}}'

# 강제 unlock (주의: 다른 작업이 진행 중이 아닌지 확인)
terraform force-unlock <lock-id>
```

## Validation Checklist

배포 후 다음 항목을 확인하세요:

### Network Layer
- [ ] Seoul VPC 생성 확인
- [ ] US VPC 생성 확인
- [ ] VPC Peering 연결 활성화 확인
- [ ] Route Table에 Peering 라우트 추가 확인
- [ ] Security Groups 생성 확인
- [ ] VPN Gateway import 확인

### App Layer
- [ ] S3 버킷 생성 및 암호화 확인
- [ ] S3 Cross-Region Replication 구성 확인
- [ ] Lambda 함수 배포 확인
- [ ] Lambda VPC 구성 확인
- [ ] OpenSearch Serverless 컬렉션 생성 확인
- [ ] Bedrock Knowledge Base 생성 확인
- [ ] KMS Key 생성 및 정책 확인
- [ ] IAM Roles 및 Policies 확인
- [ ] CloudWatch Log Groups 생성 확인
- [ ] CloudWatch Alarms 구성 확인

### End-to-End Testing
- [ ] 문서를 Seoul S3 버킷에 업로드
- [ ] US S3 버킷에 복제 확인
- [ ] Lambda 함수 실행 로그 확인
- [ ] Bedrock Knowledge Base에 문서 인덱싱 확인
- [ ] Knowledge Base 쿼리 테스트

## Next Steps

배포가 완료되면:

1. **운영 가이드 검토**: `docs/OPERATIONAL_RUNBOOK.md` 참조
2. **비용 모니터링**: `scripts/cost-estimation.sh` 실행
3. **테스트 실행**: `tests/` 디렉토리의 테스트 실행
4. **모니터링 설정**: CloudWatch 대시보드 및 알람 확인

## Support

문제가 발생하면:

1. CloudWatch Logs 확인
2. Terraform 상태 파일 검토
3. AWS Support 또는 내부 팀에 문의

## References

- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [OpenSearch Serverless Documentation](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless.html)
