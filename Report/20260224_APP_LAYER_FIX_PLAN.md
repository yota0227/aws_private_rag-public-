# App Layer 수정 계획 (상세)

작성일: 2026-02-24

## 수정 대상 파일

1. `environments/app-layer/bedrock-rag/lambda.tf`
2. `environments/app-layer/bedrock-rag/opensearch-serverless.tf`
3. `environments/app-layer/bedrock-rag/bedrock-kb.tf`
4. `environments/app-layer/bedrock-rag/providers.tf` (리전 확인)

## 수정 내용

### 1. lambda.tf

#### 수정 1: Security Group VPC ID
```hcl
# 변경 전
resource "aws_security_group" "lambda" {
  vpc_id = "vpc-066c464f9c750ee9e"  # ❌ 기존 서비스 VPC

# 변경 후
resource "aws_security_group" "lambda" {
  vpc_id = local.us_vpc_id  # ✅ US VPC (data.tf에서 정의됨)
```

#### 수정 2: Security Group Egress Rules
```hcl
# 변경 전
egress {
  description = "HTTPS to VPC Endpoints"
  cidr_blocks = ["10.200.0.0/16"]  # ❌ 기존 서비스 VPC
}

# 변경 후
egress {
  description = "HTTPS to VPC Endpoints"
  cidr_blocks = [local.us_vpc_cidr]  # ✅ US VPC CIDR (data.tf에서 정의 필요)
}
```

```hcl
# 변경 전
egress {
  description = "HTTPS to Virginia VPC"
  cidr_blocks = ["10.20.0.0/16"]  # 이미 올바름
}

# 변경 후 (Seoul VPC로 수정)
egress {
  description = "HTTPS to Seoul VPC"
  cidr_blocks = [data.terraform_remote_state.network.outputs.seoul_vpc_cidr]
}
```

#### 수정 3: Lambda VPC Config
```hcl
# 변경 전
vpc_config {
  subnet_ids         = ["subnet-0f027e9de8e26c18f", "subnet-0625d992edf151017"]  # ❌ 하드코딩
  security_group_ids = [aws_security_group.lambda.id]
}

# 변경 후
vpc_config {
  subnet_ids         = local.us_private_subnet_ids  # ✅ data.tf에서 정의됨
  security_group_ids = [aws_security_group.lambda.id]
}
```

#### 수정 4: Provider 추가
```hcl
# 파일 상단에 추가
provider "aws" {
  alias  = "us"
  region = "us-east-1"
}

# 모든 리소스에 provider 추가
resource "aws_security_group" "lambda" {
  provider = aws.us
  # ...
}

resource "aws_iam_role" "lambda" {
  provider = aws.us
  # ...
}

resource "aws_lambda_function" "document_processor" {
  provider = aws.us
  # ...
}
```

### 2. opensearch-serverless.tf

#### 수정 1: Security Group VPC ID
```hcl
# 변경 전
resource "aws_security_group" "opensearch" {
  provider = aws.seoul  # ❌ 잘못된 리전
  vpc_id   = "vpc-066c464f9c750ee9e"  # ❌ 기존 서비스 VPC

# 변경 후
resource "aws_security_group" "opensearch" {
  provider = aws.us  # ✅ US 리전
  vpc_id   = local.us_vpc_id  # ✅ US VPC
```

#### 수정 2: Security Group Ingress Rules
```hcl
# 변경 전
ingress {
  description = "HTTPS from on-premises"
  cidr_blocks = ["192.128.0.0/16"]
}

ingress {
  description = "HTTPS from Virginia VPC"
  cidr_blocks = ["10.20.0.0/16"]  # ❌ 자기 자신
}

# 변경 후
ingress {
  description = "HTTPS from Seoul VPC (via VPC Peering)"
  cidr_blocks = [data.terraform_remote_state.network.outputs.seoul_vpc_cidr]
}

ingress {
  description = "HTTPS from Lambda"
  security_groups = [aws_security_group.lambda.id]
}
```

#### 수정 3: VPC Endpoint
```hcl
# 변경 전
resource "aws_opensearchserverless_vpc_endpoint" "main" {
  provider           = aws.seoul  # ❌ 잘못된 리전
  vpc_id             = "vpc-066c464f9c750ee9e"  # ❌ 기존 서비스 VPC
  subnet_ids         = ["subnet-0f027e9de8e26c18f", "subnet-0625d992edf151017"]  # ❌ 하드코딩

# 변경 후
resource "aws_opensearchserverless_vpc_endpoint" "main" {
  provider           = aws.us  # ✅ US 리전
  vpc_id             = local.us_vpc_id  # ✅ US VPC
  subnet_ids         = local.us_private_subnet_ids  # ✅ data.tf에서 정의됨
```

#### 수정 4: Provider 변경
```hcl
# 모든 리소스의 provider를 aws.seoul → aws.us로 변경
resource "aws_opensearchserverless_security_policy" "encryption" {
  provider = aws.us  # 변경
  # ...
}

resource "aws_opensearchserverless_security_policy" "network" {
  provider = aws.us  # 변경
  # ...
}

resource "aws_opensearchserverless_collection" "main" {
  provider = aws.us  # 변경
  # ...
}
```

### 3. bedrock-kb.tf

#### 수정 1: Security Group VPC ID
```hcl
# 변경 전
resource "aws_security_group" "bedrock_kb" {
  vpc_id = "vpc-066c464f9c750ee9e"  # ❌ 기존 서비스 VPC

# 변경 후
resource "aws_security_group" "bedrock_kb" {
  provider = aws.us  # ✅ provider 추가
  vpc_id   = local.us_vpc_id  # ✅ US VPC
```

#### 수정 2: Security Group Egress Rules
```hcl
# 변경 전
egress {
  description = "HTTPS to VPC Endpoints"
  cidr_blocks = ["10.200.0.0/16"]  # ❌ 기존 서비스 VPC
}

# 변경 후
egress {
  description = "HTTPS to VPC Endpoints"
  cidr_blocks = [local.us_vpc_cidr]  # ✅ US VPC CIDR
}
```

#### 수정 3: Provider 추가
```hcl
# 모든 리소스에 provider 추가
resource "aws_security_group" "bedrock_kb" {
  provider = aws.us
  # ...
}

resource "aws_iam_role" "bedrock_kb" {
  provider = aws.us
  # ...
}

resource "aws_bedrockagent_knowledge_base" "main" {
  provider = aws.us
  # ...
}
```

### 4. data.tf

#### 추가 필요: us_vpc_cidr
```hcl
# 추가
locals {
  # Network Layer Outputs
  us_vpc_id                   = data.terraform_remote_state.network.outputs.us_vpc_id
  us_vpc_cidr                 = data.terraform_remote_state.network.outputs.us_vpc_cidr  # ✅ 추가
  us_private_subnet_ids       = data.terraform_remote_state.network.outputs.us_private_subnet_ids
  us_private_route_table_ids  = data.terraform_remote_state.network.outputs.us_private_route_table_ids
  us_security_group_ids       = [
    data.terraform_remote_state.network.outputs.us_lambda_security_group_id,
    data.terraform_remote_state.network.outputs.us_opensearch_security_group_id,
    data.terraform_remote_state.network.outputs.us_vpc_endpoints_security_group_id
  ]
  
  # Seoul VPC CIDR (for cross-VPC communication)
  seoul_vpc_cidr = data.terraform_remote_state.network.outputs.seoul_vpc_cidr  # ✅ 추가
  
  # Common Tags
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Layer       = "app"
    Region      = var.us_region
    Owner       = "AI-Team"
    CostCenter  = "AI-Infrastructure"
  }
}
```

### 5. providers.tf

#### 확인 필요: US 리전 설정
```hcl
# 확인 필요
provider "aws" {
  region = "us-east-1"  # ✅ US East 리전이어야 함
  
  default_tags {
    tags = {
      Project     = "BOS-AI"
      Environment = "Production"
      ManagedBy   = "Terraform"
    }
  }
}

# Seoul provider는 필요 없음 (모든 리소스가 US에 배포됨)
```

## 수정 순서

1. **data.tf 수정** (us_vpc_cidr, seoul_vpc_cidr 추가)
2. **providers.tf 확인** (US East 리전 설정 확인)
3. **lambda.tf 수정** (VPC ID, Subnet IDs, CIDR 블록, provider)
4. **opensearch-serverless.tf 수정** (VPC ID, Subnet IDs, CIDR 블록, provider)
5. **bedrock-kb.tf 수정** (VPC ID, CIDR 블록, provider)
6. **terraform init** (초기화)
7. **terraform validate** (검증)
8. **terraform plan** (계획 확인)
9. **terraform apply** (배포)

## 검증 체크리스트

### 배포 전
- [ ] 모든 VPC ID가 `local.us_vpc_id` 사용
- [ ] 모든 Subnet ID가 `local.us_private_subnet_ids` 사용
- [ ] 모든 CIDR 블록이 올바른 VPC CIDR 사용
- [ ] 모든 리소스에 `provider = aws.us` 설정
- [ ] `data.tf`에 `us_vpc_cidr`, `seoul_vpc_cidr` 추가
- [ ] `providers.tf`에서 US East 리전 설정 확인

### 배포 후
- [ ] Lambda 함수가 US VPC에 배포됨
- [ ] OpenSearch Serverless가 US VPC에 배포됨
- [ ] Bedrock Knowledge Base가 US 리전에 배포됨
- [ ] Security Group이 올바른 VPC에 생성됨
- [ ] VPC Peering을 통한 Seoul ↔ US 통신 가능
- [ ] CloudWatch Logs에 로그 기록됨

## 주의사항

1. **기존 서비스 VPC 절대 건드리지 말 것**
   - `vpc-066c464f9c750ee9e` (10.200.0.0/16)는 별도 운영 중

2. **모든 App Layer 리소스는 US VPC에 배포**
   - US VPC: `bos-ai-us-vpc-prod` (10.20.0.0/16)
   - Seoul VPC는 Frontend 역할만 (VPN 접근 포인트)

3. **VPC Peering을 통한 통신**
   - Seoul VPC → US VPC: VPC Peering
   - On-Premises → Seoul VPC: VPN
   - On-Premises → US VPC: VPN → Seoul VPC → VPC Peering → US VPC

4. **리전 설정 확인**
   - 모든 App Layer 리소스: `us-east-1`
   - Network Layer: Seoul (`ap-northeast-2`), US (`us-east-1`)
