# BOS-AI VPC 통합 네이밍 규칙

## 1. 개요

이 문서는 BOS-AI VPC 통합 마이그레이션 프로젝트의 모든 AWS 리소스에 적용되는 네이밍 규칙을 정의합니다.

## 2. 네이밍 패턴

### 2.1 기본 구조
```
{resource-type}-{service/purpose}-{project}-{region}-{environment}-{sequence}{az}
```

### 2.2 구성 요소

| 요소 | 설명 | 예시 |
|------|------|------|
| resource-type | AWS 리소스 타입 약어 | vpc, sn, sg, rtb, vpce |
| service/purpose | 서비스 또는 용도 | private, public, opensearch, lambda |
| project | 프로젝트 이름 | bos-ai |
| region | AWS 리전 약어 | seoul, virginia |
| environment | 환경 | prod, dev, staging |
| sequence | 순번 (2자리) | 01, 02 |
| az | 가용 영역 (선택사항) | a, c |

## 3. 리소스별 네이밍 규칙

### 3.1 VPC
**패턴:** `vpc-{project}-{region}-{environment}-{sequence}`

**예시:**
- `vpc-bos-ai-seoul-prod-01`
- `vpc-bos-ai-virginia-backend-prod`

### 3.2 Subnet
**패턴:** `sn-{type}-{project}-{region}-{environment}-{sequence}{az}`

**예시:**
- `sn-private-bos-ai-seoul-prod-01a`
- `sn-private-bos-ai-seoul-prod-01c`
- `sn-public-bos-ai-seoul-prod-01a`
- `sn-public-bos-ai-seoul-prod-01c`

### 3.3 Security Group
**패턴:** `sg-{service}-{project}-{region}-{environment}`

**예시:**
- `sg-opensearch-bos-ai-seoul-prod`
- `sg-lambda-bos-ai-seoul-prod`
- `sg-bedrock-kb-bos-ai-seoul-prod`
- `sg-vpc-endpoints-bos-ai-seoul-prod`
- `sg-route53-resolver-bos-ai-seoul-prod`

### 3.4 Route Table
**패턴:** `rtb-{type}-{project}-{region}-{environment}-{sequence}`

**예시:**
- `rtb-private-bos-ai-seoul-prod-01`
- `rtb-public-bos-ai-seoul-prod-01`

### 3.5 VPC Endpoint
**패턴:** `vpce-{service}-{region}-{environment}`

**예시:**
- `vpce-bedrock-runtime-seoul-prod`
- `vpce-secretsmanager-seoul-prod`
- `vpce-logs-seoul-prod`
- `vpce-s3-seoul-prod`
- `vpce-opensearch-serverless-seoul-prod`

### 3.6 NAT Gateway
**패턴:** `nat-{project}-{region}-{environment}-{sequence}{az}`

**예시:**
- `nat-bos-ai-seoul-prod-01a`

### 3.7 Internet Gateway
**패턴:** `igw-{project}-{region}-{environment}-{sequence}`

**예시:**
- `igw-bos-ai-seoul-prod-01`

### 3.8 Route53 Resolver Endpoint
**패턴:** `{type}-{project}-{region}-{environment}`

**예시:**
- `ibe-bos-ai-seoul-prod` (Inbound Endpoint)
- `obe-bos-ai-seoul-prod` (Outbound Endpoint)

### 3.9 Lambda Function
**패턴:** `lambda-{purpose}-{region}-{environment}`

**예시:**
- `lambda-document-processor-seoul-prod`

### 3.10 IAM Role
**패턴:** `role-{service}-{purpose}-{region}-{environment}`

**예시:**
- `role-lambda-document-processor-seoul-prod`
- `role-bedrock-kb-seoul-prod`
- `role-opensearch-serverless-seoul-prod`

### 3.11 OpenSearch Serverless Collection
**패턴:** `{project}-{purpose}-{environment}`

**예시:**
- `bos-ai-rag-vectors-prod`

### 3.12 Bedrock Knowledge Base
**패턴:** `{project}-kb-{region}-{environment}`

**예시:**
- `bos-ai-kb-seoul-prod`

### 3.13 VPC Peering Connection
**패턴:** `pcx-{source-region}-{target-region}`

**예시:**
- `pcx-seoul-virginia`

## 4. 태그 전략

### 4.1 필수 태그

모든 리소스는 다음 필수 태그를 가져야 합니다:

| 태그 키 | 설명 | 예시 값 |
|---------|------|---------|
| Name | 리소스 이름 (네이밍 규칙 준수) | vpc-bos-ai-seoul-prod-01 |
| Project | 프로젝트 이름 | BOS-AI |
| Environment | 환경 | Production |
| ManagedBy | 관리 도구 | Terraform |
| Layer | 아키텍처 레이어 | Network, Compute, Data |

### 4.2 선택 태그

필요에 따라 추가할 수 있는 태그:

| 태그 키 | 설명 | 예시 값 |
|---------|------|---------|
| Owner | 담당자 또는 팀 | Infrastructure Team |
| CostCenter | 비용 센터 | IT-AI-001 |
| Backup | 백업 필요 여부 | true, false |
| Compliance | 컴플라이언스 요구사항 | GDPR, SOC2 |

### 4.3 태그 예시

**VPC 태그:**
```json
{
  "Name": "vpc-bos-ai-seoul-prod-01",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Network"
}
```

**Lambda 태그:**
```json
{
  "Name": "lambda-document-processor-seoul-prod",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Compute"
}
```

**OpenSearch 태그:**
```json
{
  "Name": "bos-ai-rag-vectors-prod",
  "Project": "BOS-AI",
  "Environment": "Production",
  "ManagedBy": "Terraform",
  "Layer": "Data"
}
```

## 5. 기존 리소스 매핑

### 5.1 서울 PoC VPC 리소스

| 기존 이름 | 새 이름 | 리소스 ID |
|-----------|---------|-----------|
| vpc-itdev-int-poc-01 | vpc-bos-ai-seoul-prod-01 | vpc-066c464f9c750ee9e |
| sn-private-itdev-int-poc-01a | sn-private-bos-ai-seoul-prod-01a | subnet-0e0e0e0e0e0e0e0e0 |
| sn-private-itdev-int-poc-01c | sn-private-bos-ai-seoul-prod-01c | subnet-0f0f0f0f0f0f0f0f0 |
| sn-public-itdev-int-poc-01a | sn-public-bos-ai-seoul-prod-01a | subnet-0a0a0a0a0a0a0a0a0 |
| sn-public-itdev-int-poc-01c | sn-public-bos-ai-seoul-prod-01c | subnet-0b0b0b0b0b0b0b0b0 |
| sg-logclt-itdev-int-poc-01 | sg-logclt-bos-ai-seoul-prod | sg-xxxxxxxxxxxxxxxxx |
| sg-gra-itdev-int-poc-01 | sg-grafana-bos-ai-seoul-prod | sg-xxxxxxxxxxxxxxxxx |
| ibe-onprem-itdev-int-poc-01 | ibe-bos-ai-seoul-prod | rslvr-in-79867dcffe644a378 |
| obe-onprem-itdev-int-poc-01 | obe-bos-ai-seoul-prod | rslvr-out-528276266e13403aa |

### 5.2 신규 리소스

다음 리소스는 새로 생성되며 네이밍 규칙을 따릅니다:

- `sg-opensearch-bos-ai-seoul-prod`
- `sg-lambda-bos-ai-seoul-prod`
- `sg-bedrock-kb-bos-ai-seoul-prod`
- `sg-vpc-endpoints-bos-ai-seoul-prod`
- `vpce-bedrock-runtime-seoul-prod`
- `vpce-secretsmanager-seoul-prod`
- `vpce-logs-seoul-prod`
- `vpce-s3-seoul-prod`
- `vpce-opensearch-serverless-seoul-prod`
- `lambda-document-processor-seoul-prod`
- `bos-ai-rag-vectors-prod`
- `bos-ai-kb-seoul-prod`
- `pcx-seoul-virginia`

## 6. 네이밍 규칙 검증

### 6.1 자동 검증

Terraform 배포 시 다음 검증을 수행합니다:

1. 모든 리소스 이름이 패턴과 일치하는지 확인
2. 필수 태그가 모두 존재하는지 확인
3. 태그 값이 허용된 값인지 확인

### 6.2 수동 검증

배포 후 다음 명령으로 네이밍 규칙 준수를 확인합니다:

```bash
# VPC 리소스 확인
aws ec2 describe-vpcs --filters "Name=tag:Project,Values=BOS-AI" --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0]]' --output table

# 서브넷 확인
aws ec2 describe-subnets --filters "Name=tag:Project,Values=BOS-AI" --query 'Subnets[*].[SubnetId,Tags[?Key==`Name`].Value|[0]]' --output table

# Security Group 확인
aws ec2 describe-security-groups --filters "Name=tag:Project,Values=BOS-AI" --query 'SecurityGroups[*].[GroupId,GroupName,Tags[?Key==`Name`].Value|[0]]' --output table
```

## 7. 예외 사항

### 7.1 기존 로깅 인프라

다음 리소스는 기존 이름을 유지합니다 (마이그레이션 범위 외):

- `ec2-logclt-itdev-int-poc-01` (로그 수집기 EC2)
- `open-mon-itdev-int-poc-001` (OpenSearch Managed 도메인)
- `vpce-firehose-itdev-int-poc-01` (Firehose VPC 엔드포인트)

단, 태그는 새로운 태그 전략에 맞게 업데이트합니다.

## 8. 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|-----------|--------|
| 2025-01-XX | 1.0 | 초기 작성 | Kiro |

## 9. 참고 자료

- AWS 네이밍 모범 사례: https://docs.aws.amazon.com/general/latest/gr/aws_tagging.html
- Terraform 네이밍 규칙: https://www.terraform-best-practices.com/naming
- 내부 인프라 표준: (내부 문서 링크)
