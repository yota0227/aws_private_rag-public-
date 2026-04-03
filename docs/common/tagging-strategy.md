# BOS-AI VPC 통합 태그 전략

## 1. 개요

이 문서는 BOS-AI VPC 통합 마이그레이션 프로젝트의 모든 AWS 리소스에 적용되는 태그 전략을 정의합니다. 일관된 태그 전략은 리소스 관리, 비용 추적, 보안 감사, 자동화를 용이하게 합니다.

## 2. 태그 정책

### 2.1 필수 태그

모든 AWS 리소스는 다음 5개의 필수 태그를 가져야 합니다:

| 태그 키 | 설명 | 허용 값 | 예시 |
|---------|------|---------|------|
| Name | 리소스 이름 (네이밍 규칙 준수) | 네이밍 규칙 참조 | vpc-bos-ai-seoul-prod-01 |
| Project | 프로젝트 이름 | BOS-AI | BOS-AI |
| Environment | 환경 구분 | Production, Development, Staging | Production |
| ManagedBy | 관리 도구 | Terraform, Manual, CloudFormation | Terraform |
| Layer | 아키텍처 레이어 | Network, Compute, Data, Security | Network |

### 2.2 권장 태그

다음 태그는 필수는 아니지만 운영 효율성을 위해 권장됩니다:

| 태그 키 | 설명 | 예시 |
|---------|------|------|
| Owner | 담당자 또는 팀 | Infrastructure Team |
| CostCenter | 비용 센터 코드 | IT-AI-001 |
| Backup | 백업 필요 여부 | true, false |
| Compliance | 컴플라이언스 요구사항 | Internal, GDPR, SOC2 |
| Description | 리소스 설명 | AI workload VPC for RAG system |

### 2.3 선택 태그

특정 리소스나 상황에 따라 추가할 수 있는 태그:

| 태그 키 | 설명 | 사용 시나리오 |
|---------|------|--------------|
| DataClassification | 데이터 분류 | 민감 데이터 처리 리소스 |
| MaintenanceWindow | 유지보수 시간 | 정기 유지보수가 필요한 리소스 |
| AutoShutdown | 자동 종료 설정 | 비용 절감을 위한 자동화 |
| Version | 리소스 버전 | 버전 관리가 필요한 리소스 |

## 3. 레이어별 태그 전략

### 3.1 Network Layer

**적용 리소스:** VPC, Subnet, Route Table, NAT Gateway, Internet Gateway, VPC Peering

**필수 태그:**
```json
{
  "Name": "vpc-bos-ai-seoul-prod-01",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Network"
}
```

**권장 태그:**
```json
{
  "Owner": "Infrastructure Team",
  "CostCenter": "IT-AI-001",
  "Description": "Consolidated VPC for logging and AI workloads"
}
```

### 3.2 Security Layer

**적용 리소스:** Security Group, Network ACL, IAM Role, IAM Policy

**필수 태그:**
```json
{
  "Name": "sg-opensearch-bos-ai-seoul-prod",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Security"
}
```

**권장 태그:**
```json
{
  "Owner": "Security Team",
  "Compliance": "Internal",
  "Description": "Security group for OpenSearch Serverless access"
}
```

### 3.3 Compute Layer

**적용 리소스:** Lambda, EC2, ECS, EKS

**필수 태그:**
```json
{
  "Name": "lambda-document-processor-seoul-prod",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Compute"
}
```

**권장 태그:**
```json
{
  "Owner": "AI Team",
  "CostCenter": "IT-AI-001",
  "Description": "Document processing and embedding generation"
}
```

### 3.4 Data Layer

**적용 리소스:** OpenSearch, S3, RDS, DynamoDB

**필수 태그:**
```json
{
  "Name": "bos-ai-rag-vectors-prod",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Data"
}
```

**권장 태그:**
```json
{
  "Owner": "Data Team",
  "CostCenter": "IT-AI-001",
  "Backup": "true",
  "DataClassification": "Internal",
  "Description": "Vector database for RAG embeddings"
}
```

## 4. 환경별 태그 값

### 4.1 Production 환경

```json
{
  "Environment": "Production",
  "Backup": "true",
  "MaintenanceWindow": "Sunday 02:00-04:00 KST"
}
```

### 4.2 Development 환경

```json
{
  "Environment": "Development",
  "AutoShutdown": "true",
  "Backup": "false"
}
```

### 4.3 Staging 환경

```json
{
  "Environment": "Staging",
  "Backup": "true",
  "AutoShutdown": "false"
}
```

## 5. 리소스별 태그 예시

### 5.1 VPC

```json
{
  "Name": "vpc-bos-ai-seoul-prod-01",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Network",
  "Owner": "Infrastructure Team",
  "CostCenter": "IT-AI-001",
  "Description": "Consolidated VPC for logging and AI workloads with VPN connectivity"
}
```

### 5.2 Subnet

```json
{
  "Name": "sn-private-bos-ai-seoul-prod-01a",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Network",
  "Owner": "Infrastructure Team",
  "Description": "Private subnet for Lambda and OpenSearch in AZ 2a"
}
```

### 5.3 Security Group

```json
{
  "Name": "sg-opensearch-bos-ai-seoul-prod",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Security",
  "Owner": "Security Team",
  "Compliance": "Internal",
  "Description": "Security group for OpenSearch Serverless collection access"
}
```

### 5.4 Lambda Function

```json
{
  "Name": "lambda-document-processor-seoul-prod",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Compute",
  "Owner": "AI Team",
  "CostCenter": "IT-AI-001",
  "Description": "Processes documents and generates embeddings for RAG"
}
```

### 5.5 OpenSearch Serverless Collection

```json
{
  "Name": "bos-ai-rag-vectors-prod",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Data",
  "Owner": "Data Team",
  "CostCenter": "IT-AI-001",
  "Backup": "true",
  "DataClassification": "Internal",
  "Description": "Vector database for storing document embeddings"
}
```

### 5.6 IAM Role

```json
{
  "Name": "role-lambda-document-processor-seoul-prod",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Security",
  "Owner": "Security Team",
  "Description": "IAM role for Lambda document processor with minimal permissions"
}
```

### 5.7 VPC Endpoint

```json
{
  "Name": "vpce-bedrock-runtime-seoul-prod",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Network",
  "Owner": "Infrastructure Team",
  "Description": "VPC endpoint for Bedrock Runtime API access"
}
```

## 6. 비용 추적 전략

### 6.1 비용 할당 태그

AWS Cost Explorer에서 다음 태그를 활성화하여 비용을 추적합니다:

- **Project**: 프로젝트별 비용 분석
- **Environment**: 환경별 비용 분석
- **Layer**: 레이어별 비용 분석
- **CostCenter**: 비용 센터별 청구

### 6.2 비용 최적화 태그

다음 태그를 사용하여 비용 최적화 기회를 식별합니다:

- **AutoShutdown**: 자동 종료 대상 리소스
- **Backup**: 백업 비용 추적
- **Environment=Development**: 개발 환경 리소스 최적화

## 7. 태그 적용 방법

### 7.1 Terraform을 통한 태그 적용

**로컬 변수 정의:**
```hcl
locals {
  common_tags = {
    Project     = "BOS-AI"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  network_tags = merge(
    local.common_tags,
    {
      Layer = "Network"
      Owner = "Infrastructure Team"
    }
  )

  compute_tags = merge(
    local.common_tags,
    {
      Layer      = "Compute"
      Owner      = "AI Team"
      CostCenter = "IT-AI-001"
    }
  )
}
```

**리소스에 태그 적용:**
```hcl
resource "aws_vpc" "main" {
  cidr_block = "10.200.0.0/16"

  tags = merge(
    local.network_tags,
    {
      Name        = "vpc-bos-ai-seoul-prod-01"
      Description = "Consolidated VPC for logging and AI workloads"
    }
  )
}
```

### 7.2 AWS CLI를 통한 태그 적용

```bash
# VPC 태그 추가
aws ec2 create-tags \
  --resources vpc-066c464f9c750ee9e \
  --tags \
    Key=Name,Value=vpc-bos-ai-seoul-prod-01 \
    Key=Project,Value=BOS-AI \
    Key=Environment,Value=Production \
    Key=ManagedBy,Value=Terraform \
    Key=Layer,Value=Network

# 여러 리소스에 동일 태그 적용
aws ec2 create-tags \
  --resources subnet-xxx subnet-yyy \
  --tags Key=Project,Value=BOS-AI
```

## 8. 태그 검증

### 8.1 필수 태그 검증 스크립트

```bash
#!/bin/bash
# check-required-tags.sh

REQUIRED_TAGS=("Name" "Project" "Environment" "ManagedBy" "Layer")

# VPC 태그 확인
aws ec2 describe-vpcs --filters "Name=tag:Project,Values=BOS-AI" \
  --query 'Vpcs[*].[VpcId,Tags]' --output json | \
  jq -r '.[] | @json' | while read vpc; do
    vpc_id=$(echo $vpc | jq -r '.[0]')
    tags=$(echo $vpc | jq -r '.[1]')
    
    for tag in "${REQUIRED_TAGS[@]}"; do
      if ! echo $tags | jq -e ".[] | select(.Key==\"$tag\")" > /dev/null; then
        echo "ERROR: VPC $vpc_id is missing required tag: $tag"
      fi
    done
done
```

### 8.2 Terraform 검증

```hcl
# variables.tf에 검증 추가
variable "tags" {
  description = "Resource tags"
  type        = map(string)

  validation {
    condition = alltrue([
      for required_key in ["Name", "Project", "Environment", "ManagedBy", "Layer"] :
      contains(keys(var.tags), required_key)
    ])
    error_message = "All required tags must be present: Name, Project, Environment, ManagedBy, Layer"
  }
}
```

### 8.3 AWS Config 규칙

AWS Config를 사용하여 태그 준수를 자동으로 모니터링:

```json
{
  "ConfigRuleName": "required-tags-bos-ai",
  "Description": "Checks that BOS-AI resources have required tags",
  "Source": {
    "Owner": "AWS",
    "SourceIdentifier": "REQUIRED_TAGS"
  },
  "InputParameters": {
    "tag1Key": "Project",
    "tag2Key": "Environment",
    "tag3Key": "ManagedBy",
    "tag4Key": "Layer",
    "tag5Key": "Name"
  }
}
```

## 9. 태그 거버넌스

### 9.1 태그 정책 (AWS Organizations)

```json
{
  "tags": {
    "Project": {
      "tag_key": {
        "@@assign": "Project"
      },
      "tag_value": {
        "@@assign": ["BOS-AI"]
      },
      "enforced_for": {
        "@@assign": ["ec2:*", "lambda:*", "opensearch:*"]
      }
    },
    "Environment": {
      "tag_key": {
        "@@assign": "Environment"
      },
      "tag_value": {
        "@@assign": ["Production", "Development", "Staging"]
      },
      "enforced_for": {
        "@@assign": ["*"]
      }
    }
  }
}
```

### 9.2 태그 변경 승인 프로세스

1. **제안**: 새로운 태그 또는 태그 값 제안
2. **검토**: 인프라 팀 검토
3. **승인**: 아키텍처 팀 승인
4. **문서화**: 이 문서 업데이트
5. **적용**: Terraform 코드 업데이트 및 배포

## 10. 마이그레이션 태그 전략

### 10.1 기존 리소스 태그 업데이트

**Phase 1: 태그 추가 (기존 태그 유지)**
```bash
# 기존 태그를 유지하면서 새 태그 추가
aws ec2 create-tags --resources vpc-066c464f9c750ee9e \
  --tags Key=Project,Value=BOS-AI
```

**Phase 2: 태그 정리 (불필요한 태그 제거)**
```bash
# 불필요한 태그 제거
aws ec2 delete-tags --resources vpc-066c464f9c750ee9e \
  --tags Key=OldTag
```

### 10.2 마이그레이션 추적 태그

마이그레이션 중에는 다음 임시 태그를 사용:

```json
{
  "MigrationStatus": "InProgress",
  "MigrationPhase": "Phase2-Naming",
  "MigrationDate": "2025-01-XX",
  "OriginalName": "vpc-itdev-int-poc-01"
}
```

마이그레이션 완료 후 제거합니다.

## 11. 모니터링 및 보고

### 11.1 태그 준수 대시보드

CloudWatch Dashboard에서 다음 메트릭을 추적:

- 필수 태그가 없는 리소스 수
- 프로젝트별 리소스 수
- 환경별 리소스 수
- 레이어별 리소스 수

### 11.2 월간 태그 감사

매월 다음 항목을 검토:

- [ ] 모든 리소스에 필수 태그 존재
- [ ] 태그 값이 허용된 값 범위 내
- [ ] 비용 할당 태그 정확성
- [ ] 불필요한 태그 정리

## 12. 참고 자료

- [AWS 태그 모범 사례](https://docs.aws.amazon.com/general/latest/gr/aws_tagging.html)
- [AWS 비용 할당 태그](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html)
- [Terraform 태그 관리](https://www.terraform.io/docs/language/meta-arguments/tags.html)
- 내부 네이밍 규칙: `docs/naming-conventions.md`

## 13. 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|-----------|--------|
| 2025-01-XX | 1.0 | 초기 작성 | Kiro |

## 14. 부록: 태그 체크리스트

### 14.1 신규 리소스 생성 시

- [ ] Name 태그 (네이밍 규칙 준수)
- [ ] Project 태그 (BOS-AI)
- [ ] Environment 태그 (Production/Development/Staging)
- [ ] ManagedBy 태그 (Terraform/Manual)
- [ ] Layer 태그 (Network/Compute/Data/Security)
- [ ] Owner 태그 (담당 팀)
- [ ] Description 태그 (리소스 설명)

### 14.2 기존 리소스 업데이트 시

- [ ] 기존 태그 검토
- [ ] 필수 태그 추가
- [ ] 불필요한 태그 제거
- [ ] 태그 값 표준화
- [ ] 문서 업데이트
