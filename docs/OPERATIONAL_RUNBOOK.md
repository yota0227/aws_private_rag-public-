# AWS Bedrock RAG Operational Runbook

## Overview

이 운영 가이드는 AWS Bedrock RAG 시스템의 일상적인 운영, 모니터링, 문제 해결 절차를 제공합니다.

## Table of Contents

1. [Document Management](#document-management)
2. [Knowledge Base Operations](#knowledge-base-operations)
3. [System Monitoring](#system-monitoring)
4. [Troubleshooting](#troubleshooting)
5. [Disaster Recovery](#disaster-recovery)
6. [Maintenance Procedures](#maintenance-procedures)

## Document Management

### Uploading Documents

#### Seoul S3 Bucket에 문서 업로드

**실제 버킷 이름:** `bos-ai-documents-seoul`

**AWS CLI 사용:**

```bash
# 단일 파일 업로드
aws s3 cp document.pdf s3://bos-ai-documents-seoul/documents/ \
  --metadata document-type=spec,chunking-strategy=hierarchical

# 디렉토리 업로드
aws s3 sync ./documents/ s3://bos-ai-documents-seoul/documents/ \
  --metadata document-type=text,chunking-strategy=semantic

# RTL 파일 업로드 (특수 메타데이터)
aws s3 cp design.v s3://bos-ai-documents-seoul/rtl/ \
  --metadata document-type=rtl,chunking-strategy=semantic,preserve-structure=true
```

**Python SDK 사용:**

```python
import boto3

s3_client = boto3.client('s3', region_name='ap-northeast-2')

# 문서 업로드
s3_client.upload_file(
    'document.pdf',
    'bos-ai-documents-seoul',
    'documents/document.pdf',
    ExtraArgs={
        'Metadata': {
            'document-type': 'spec',
            'chunking-strategy': 'hierarchical',
            'version': '1.0',
            'classification': 'internal'
        }
    }
)
```

#### Document Type 메타데이터

문서 타입에 따라 적절한 메타데이터를 설정하세요:

| Document Type | Metadata | Chunking Strategy |
|---------------|----------|-------------------|
| RTL Code | `document-type=rtl` | `semantic` (코드 구조 보존) |
| Specifications | `document-type=spec` | `hierarchical` (섹션 기반) |
| Diagrams | `document-type=diagram` | `fixed` (고정 크기) |
| Text Documents | `document-type=text` | `semantic` (문장 경계) |

### Monitoring Document Processing

#### Lambda 실행 로그 확인

**실제 Lambda 함수 이름:** `document-processor`

```bash
# 최근 로그 확인
aws logs tail /aws/lambda/document-processor \
  --region us-east-1 \
  --follow

# 특정 시간대 로그 조회
aws logs filter-log-events \
  --log-group-name /aws/lambda/document-processor \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --region us-east-1
```

#### S3 Replication 상태 확인

```bash
# 복제 상태 확인
aws s3api head-object \
  --bucket bos-ai-documents-seoul \
  --key documents/document.pdf \
  --query 'ReplicationStatus'

# 가능한 상태:
# - PENDING: 복제 대기 중
# - COMPLETED: 복제 완료
# - FAILED: 복제 실패
# - REPLICA: 복제본 (대상 버킷)
```

#### Bedrock Ingestion Job 상태 확인

**실제 Knowledge Base ID:** `FNNOP3VBZV`

```bash
# Knowledge Base ID 사용
KB_ID="FNNOP3VBZV"

# 또는 동적으로 확인
KB_ID=$(aws bedrock-agent list-knowledge-bases \
  --region us-east-1 \
  --query 'knowledgeBaseSummaries[0].knowledgeBaseId' \
  --output text)

# Ingestion Job 목록 조회
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id $KB_ID \
  --region us-east-1

# 특정 Job 상태 확인
aws bedrock-agent get-ingestion-job \
  --knowledge-base-id $KB_ID \
  --data-source-id <data-source-id> \
  --ingestion-job-id <job-id> \
  --region us-east-1
```

### Document Deletion

```bash
# Seoul 버킷에서 삭제 (자동으로 US 버킷에서도 삭제됨)
aws s3 rm s3://bos-ai-documents-seoul/documents/document.pdf

# 버전 삭제 (versioning 활성화된 경우)
aws s3api delete-object \
  --bucket bos-ai-documents-seoul \
  --key documents/document.pdf \
  --version-id <version-id>
```

**주의:** 문서를 삭제해도 Knowledge Base의 벡터는 자동으로 삭제되지 않습니다. 필요시 수동으로 재인덱싱하세요.

## Knowledge Base Operations

### Querying the Knowledge Base

**실제 Knowledge Base ID:** `FNNOP3VBZV`

#### AWS CLI 사용

```bash
# Knowledge Base ID 설정
KB_ID="FNNOP3VBZV"

# Retrieve API (검색만)
aws bedrock-agent-runtime retrieve \
  --knowledge-base-id $KB_ID \
  --retrieval-query text="반도체 설계 프로세스" \
  --region us-east-1

# RetrieveAndGenerate API (검색 + 생성)
aws bedrock-agent-runtime retrieve-and-generate \
  --input text="반도체 설계 프로세스를 설명해주세요" \
  --retrieve-and-generate-configuration '{
    "type": "KNOWLEDGE_BASE",
    "knowledgeBaseConfiguration": {
      "knowledgeBaseId": "'$KB_ID'",
      "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2"
    }
  }' \
  --region us-east-1
```

#### Python SDK 사용

```python
import boto3
import json

bedrock_agent_runtime = boto3.client(
    'bedrock-agent-runtime',
    region_name='us-east-1'
)

# 실제 Knowledge Base ID
KB_ID = 'FNNOP3VBZV'

# 검색 및 생성
response = bedrock_agent_runtime.retrieve_and_generate(
    input={
        'text': '반도체 설계 프로세스를 설명해주세요'
    },
    retrieveAndGenerateConfiguration={
        'type': 'KNOWLEDGE_BASE',
        'knowledgeBaseConfiguration': {
            'knowledgeBaseId': KB_ID,
            'modelArn': 'arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2',
            'retrievalConfiguration': {
                'vectorSearchConfiguration': {
                    'numberOfResults': 5
                }
            }
        }
    }
)

print(json.dumps(response, indent=2, ensure_ascii=False))
```

### Manual Re-indexing

Knowledge Base를 수동으로 재인덱싱해야 하는 경우:

```bash
# Knowledge Base ID 설정
KB_ID="FNNOP3VBZV"

# Data Source ID 확인
DATA_SOURCE_ID=$(aws bedrock-agent list-data-sources \
  --knowledge-base-id $KB_ID \
  --region us-east-1 \
  --query 'dataSourceSummaries[0].dataSourceId' \
  --output text)

# Ingestion Job 시작
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id $KB_ID \
  --data-source-id $DATA_SOURCE_ID \
  --region us-east-1

# Job 상태 모니터링
aws bedrock-agent get-ingestion-job \
  --knowledge-base-id $KB_ID \
  --data-source-id $DATA_SOURCE_ID \
  --ingestion-job-id <job-id> \
  --region us-east-1 \
  --query 'ingestionJob.status'
```

### OpenSearch Index Management

**실제 OpenSearch 컬렉션 엔드포인트:** `https://iw3pzcloa0en8d90hh7.us-east-1.aoss.amazonaws.com`
**실제 인덱스 이름:** `bedrock-knowledge-base-index`

#### Index 상태 확인

```bash
# OpenSearch 컬렉션 엔드포인트 확인
COLLECTION_ENDPOINT="https://iw3pzcloa0en8d90hh7.us-east-1.aoss.amazonaws.com"

# 또는 동적으로 확인
COLLECTION_ENDPOINT=$(aws opensearchserverless list-collections \
  --region us-east-1 \
  --query 'collectionSummaries[?name==`bos-ai-vectors`].collectionEndpoint' \
  --output text)

# Index 통계 확인 (Python 스크립트 사용)
# AWS Console → OpenSearch Serverless → Collections → bos-ai-vectors → Indexes
```

#### Index 재생성 (필요시)

OpenSearch Serverless는 자동으로 인덱스를 관리하지만, 필요시 수동으로 재생성할 수 있습니다:

```bash
# 기존 인덱스 삭제 (주의!)
# AWS Console에서 수행하거나 Python 스크립트 사용

# 새 인덱스 생성
cd scripts
python3 create-opensearch-index.py \
  https://iw3pzcloa0en8d90hh7.us-east-1.aoss.amazonaws.com \
  bedrock-knowledge-base-index \
  1536
```

**주의:** 인덱스를 삭제하면 모든 벡터 데이터가 손실됩니다. 재인덱싱이 필요합니다.

## System Monitoring

### CloudWatch Dashboards

#### 대시보드 접근

1. AWS Console → CloudWatch → Dashboards
2. `BOS-AI-RAG-Dashboard` 선택

#### 주요 메트릭

**Bedrock Metrics:**
- API 호출 수
- 응답 시간 (Latency)
- 오류율
- 토큰 사용량

**Lambda Metrics:**
- 실행 횟수
- 오류 수
- 실행 시간
- 동시 실행 수

**OpenSearch Metrics:**
- 검색 지연 시간
- 인덱싱 속도
- OCU 사용률
- 스토리지 사용량

**S3 Metrics:**
- 객체 수
- 스토리지 크기
- 복제 지연 시간

### CloudWatch Alarms

#### 알람 상태 확인

```bash
# 모든 알람 상태 확인
aws cloudwatch describe-alarms \
  --alarm-name-prefix "BOS-AI-RAG" \
  --region us-east-1

# ALARM 상태인 알람만 확인
aws cloudwatch describe-alarms \
  --state-value ALARM \
  --region us-east-1
```

#### 주요 알람

| Alarm Name | Threshold | Action |
|------------|-----------|--------|
| `BOS-AI-RAG-Bedrock-Errors` | 오류율 > 5% | SNS 알림 |
| `BOS-AI-RAG-Lambda-Failures` | 실패 > 10회/5분 | SNS 알림 |
| `BOS-AI-RAG-OpenSearch-Capacity` | OCU 사용률 > 80% | SNS 알림, 용량 증설 검토 |
| `BOS-AI-RAG-S3-Replication-Lag` | 복제 지연 > 15분 | SNS 알림 |

### VPC Flow Logs

#### Flow Logs 조회

```bash
# Flow Logs 그룹 확인
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/vpc/flow-logs" \
  --region us-east-1

# 최근 Flow Logs 조회
aws logs tail /aws/vpc/flow-logs/bos-ai-rag \
  --region us-east-1 \
  --follow
```

#### 네트워크 트래픽 분석

```bash
# 특정 IP로의 트래픽 필터링
aws logs filter-log-events \
  --log-group-name /aws/vpc/flow-logs/bos-ai-rag \
  --filter-pattern "[version, account, eni, source, destination=10.20.*, ...]" \
  --region us-east-1
```

### Cost Monitoring

#### 현재 비용 확인

```bash
# 이번 달 비용 확인
aws ce get-cost-and-usage \
  --time-period Start=$(date -d "$(date +%Y-%m-01)" +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --filter file://cost-filter.json

# cost-filter.json:
{
  "Tags": {
    "Key": "Project",
    "Values": ["BOS-AI-RAG"]
  }
}
```

#### 서비스별 비용 분석

```bash
# 서비스별 비용 확인
aws ce get-cost-and-usage \
  --time-period Start=$(date -d "7 days ago" +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity DAILY \
  --metrics BlendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --filter file://cost-filter.json
```

## Troubleshooting

### Lambda Function Issues

#### Lambda 실행 실패

**실제 Lambda 함수 이름:** `document-processor`

**증상:** Lambda 함수가 실패하고 오류 로그가 표시됨

**진단:**

```bash
# 최근 오류 로그 확인
aws logs filter-log-events \
  --log-group-name /aws/lambda/document-processor \
  --filter-pattern "ERROR" \
  --region us-east-1

# Lambda 함수 구성 확인
aws lambda get-function-configuration \
  --function-name document-processor \
  --region us-east-1
```

**일반적인 원인 및 해결:**

1. **메모리 부족:**
   ```bash
   # 메모리 증가
   aws lambda update-function-configuration \
     --function-name document-processor \
     --memory-size 2048 \
     --region us-east-1
   ```

2. **타임아웃:**
   ```bash
   # 타임아웃 증가
   aws lambda update-function-configuration \
     --function-name document-processor \
     --timeout 600 \
     --region us-east-1
   ```

3. **IAM 권한 부족:**
   - Lambda execution role의 정책 확인
   - 필요한 권한 추가 (S3, SQS, Bedrock, VPC 등)

#### Lambda VPC 연결 문제

**증상:** Lambda가 VPC 리소스에 접근할 수 없음

**진단:**

```bash
# Lambda VPC 구성 확인
aws lambda get-function-configuration \
  --function-name document-processor \
  --query 'VpcConfig' \
  --region us-east-1

# Security Group 규칙 확인
aws ec2 describe-security-groups \
  --group-ids <sg-id> \
  --region us-east-1
```

**해결:**
- Security Group의 아웃바운드 규칙 확인 (모든 트래픽 허용 필요)
- VPC Endpoint 연결 확인 (S3, Bedrock, SQS 등)
- NAT Gateway 구성 확인 (외부 API 호출 시 필요)
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

### Bedrock Knowledge Base Issues

#### 쿼리 응답 없음

**증상:** Knowledge Base 쿼리가 빈 응답을 반환

**진단:**

```bash
# Knowledge Base ID 설정
KB_ID="FNNOP3VBZV"

# Knowledge Base 상태 확인
aws bedrock-agent get-knowledge-base \
  --knowledge-base-id $KB_ID \
  --region us-east-1

# Data Source 상태 확인
aws bedrock-agent list-data-sources \
  --knowledge-base-id $KB_ID \
  --region us-east-1

# 최근 Ingestion Job 확인
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id $KB_ID \
  --region us-east-1 \
  --max-results 5
```

**해결:**
1. Data Source가 올바르게 구성되었는지 확인
2. S3 버킷 (bos-ai-documents-us)에 문서가 있는지 확인
3. Ingestion Job이 성공적으로 완료되었는지 확인
4. OpenSearch 인덱스가 생성되었는지 확인
5. 필요시 수동 재인덱싱 실행

#### Bedrock API 오류

**증상:** `ThrottlingException` 또는 `ServiceQuotaExceededException`

**진단:**

```bash
# CloudWatch 메트릭 확인
aws cloudwatch get-metric-statistics \
  --namespace AWS/Bedrock \
  --metric-name Invocations \
  --dimensions Name=ModelId,Value=anthropic.claude-v2 \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region us-east-1
```

**해결:**
1. **Throttling:** Lambda에 재시도 로직 추가 또는 호출 빈도 감소
2. **Quota 초과:** AWS Support에 할당량 증가 요청

### OpenSearch Serverless Issues

#### 검색 성능 저하

**증상:** 검색 쿼리 응답 시간이 느림

**진단:**

```bash
# OpenSearch 메트릭 확인
aws cloudwatch get-metric-statistics \
  --namespace AWS/AOSS \
  --metric-name SearchLatency \
  --dimensions Name=CollectionName,Value=bos-ai-vectors \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average \
  --region us-east-1
```

**해결:**
1. OCU 용량 증가
2. 인덱스 최적화
3. 쿼리 패턴 검토

#### OCU 용량 부족

**증상:** `InsufficientCapacityException`

**해결:**

Terraform 변수 파일 수정:
```hcl
opensearch_capacity_units = {
  search_ocu   = 4  # 2에서 4로 증가
  indexing_ocu = 4  # 2에서 4로 증가
}
```

```bash
cd environments/app-layer/bedrock-rag
terraform apply
```

### S3 Replication Issues

#### 복제 지연

**증상:** 문서가 Seoul 버킷에 업로드되었지만 US 버킷에 나타나지 않음

**진단:**

```bash
# Replication 구성 확인
aws s3api get-bucket-replication \
  --bucket bos-ai-documents-seoul

# 객체 복제 상태 확인
aws s3api head-object \
  --bucket bos-ai-documents-seoul \
  --key documents/document.pdf \
  --query 'ReplicationStatus'
```

**해결:**
1. Replication role의 권한 확인
2. 대상 버킷의 정책 확인
3. KMS 키 권한 확인 (암호화된 경우)

#### 복제 실패

**증상:** Replication Status가 `FAILED`

**해결:**

```bash
# 실패한 객체 재업로드
aws s3 cp s3://bos-ai-documents-seoul/documents/document.pdf \
  s3://bos-ai-documents-seoul/documents/document.pdf \
  --metadata-directive REPLACE

# 또는 수동 복사
aws s3 cp s3://bos-ai-documents-seoul/documents/document.pdf \
  s3://bos-ai-documents-us/documents/document.pdf
```

### VPC Peering Issues

#### Peering 연결 실패

**증상:** VPC 간 통신이 되지 않음

**진단:**

```bash
# Peering 상태 확인
aws ec2 describe-vpc-peering-connections \
  --filters "Name=status-code,Values=active" \
  --region ap-northeast-2

# Route Table 확인
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=<vpc-id>" \
  --region ap-northeast-2
```

**해결:**
1. Peering 연결이 `active` 상태인지 확인
2. Route Table에 Peering 라우트가 있는지 확인
3. Security Group 규칙 확인
4. Network ACL 규칙 확인

## Disaster Recovery

### RTO/RPO Targets

- **RTO (Recovery Time Objective):** 4시간
- **RPO (Recovery Point Objective):** 1시간

### Backup Procedures

#### S3 Versioning

S3 versioning이 활성화되어 있어 실수로 삭제된 객체를 복구할 수 있습니다:

```bash
# 삭제된 객체 복구
aws s3api list-object-versions \
  --bucket bos-ai-documents-seoul \
  --prefix documents/document.pdf

# 특정 버전 복구
aws s3api copy-object \
  --copy-source bos-ai-documents-seoul/documents/document.pdf?versionId=<version-id> \
  --bucket bos-ai-documents-seoul \
  --key documents/document.pdf
```

#### OpenSearch Snapshots

OpenSearch Serverless는 자동으로 스냅샷을 생성합니다. 수동 복구가 필요한 경우 AWS Support에 문의하세요.

#### Terraform State Backup

Terraform 상태 파일은 S3에 versioning과 함께 저장됩니다:

```bash
# 상태 파일 버전 확인
aws s3api list-object-versions \
  --bucket bos-ai-terraform-state \
  --prefix network-layer/terraform.tfstate

# 이전 버전으로 복구
aws s3api copy-object \
  --copy-source bos-ai-terraform-state/network-layer/terraform.tfstate?versionId=<version-id> \
  --bucket bos-ai-terraform-state \
  --key network-layer/terraform.tfstate
```

### Recovery Procedures

#### Complete System Recovery

1. **Network Layer 복구:**
   ```bash
   cd environments/network-layer
   terraform init
   terraform apply
   ```

2. **App Layer 복구:**
   ```bash
   cd environments/app-layer/bedrock-rag
   terraform init
   terraform apply
   ```

3. **Data 복구:**
   - S3 versioning을 사용하여 문서 복구
   - Knowledge Base 재인덱싱

4. **검증:**
   - 모든 리소스가 정상 작동하는지 확인
   - 테스트 쿼리 실행

#### Partial Recovery

**Lambda 함수만 복구:**
```bash
cd environments/app-layer/bedrock-rag
terraform apply -target=module.s3_pipeline.aws_lambda_function.processor
```

**Knowledge Base만 복구:**
```bash
terraform apply -target=module.bedrock_rag.aws_bedrockagent_knowledge_base.main
```

## Maintenance Procedures

### Regular Maintenance Tasks

#### Daily
- [ ] CloudWatch 알람 확인
- [ ] Lambda 오류 로그 검토
- [ ] S3 복제 상태 확인

#### Weekly
- [ ] 비용 리포트 검토
- [ ] OpenSearch OCU 사용률 검토
- [ ] 문서 처리 통계 검토
- [ ] 보안 그룹 규칙 검토

#### Monthly
- [ ] Terraform 상태 파일 백업 확인
- [ ] IAM 권한 검토
- [ ] CloudWatch Logs 보존 기간 검토
- [ ] 비용 최적화 기회 검토
- [ ] 보안 패치 및 업데이트 적용

#### Quarterly
- [ ] 재해 복구 테스트 수행
- [ ] 용량 계획 검토
- [ ] 아키텍처 검토
- [ ] 문서 업데이트

### Scaling Procedures

#### Lambda 스케일링

Lambda는 자동으로 스케일링되지만, 동시 실행 제한을 조정할 수 있습니다:

**실제 Lambda 함수 이름:** `document-processor`

```bash
aws lambda put-function-concurrency \
  --function-name document-processor \
  --reserved-concurrent-executions 100 \
  --region us-east-1
```

#### OpenSearch 스케일링

OCU 용량 조정:

```hcl
# terraform.tfvars
opensearch_capacity_units = {
  search_ocu   = 4  # 증가
  indexing_ocu = 4  # 증가
}
```

```bash
terraform apply
```

#### S3 스케일링

S3는 자동으로 스케일링됩니다. 추가 작업 불필요.

### Update Procedures

#### Lambda 코드 업데이트

**실제 Lambda 함수 이름:** `document-processor`

```bash
# 코드 수정 후
cd lambda/document-processor
zip -r function.zip handler.py requirements.txt

# Lambda 업데이트
aws lambda update-function-code \
  --function-name document-processor \
  --zip-file fileb://function.zip \
  --region us-east-1

# 또는 Terraform으로 업데이트
cd ../../environments/app-layer/bedrock-rag
terraform apply -target=module.s3_pipeline.aws_lambda_function.processor
```

#### Terraform 구성 업데이트

```bash
# 변경 사항 검토
terraform plan

# 적용
terraform apply

# 특정 리소스만 업데이트
terraform apply -target=<resource>
```

## Security Operations

### Access Review

#### IAM 권한 검토

```bash
# Role에 연결된 정책 확인
aws iam list-attached-role-policies \
  --role-name BOS-AI-Lambda-Execution-Role

# 정책 내용 확인
aws iam get-policy-version \
  --policy-arn <policy-arn> \
  --version-id v1
```

#### CloudTrail 로그 검토

```bash
# 최근 API 호출 확인
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceType,AttributeValue=AWS::Bedrock::KnowledgeBase \
  --max-results 50 \
  --region us-east-1
```

### Security Incident Response

1. **의심스러운 활동 감지 시:**
   - CloudTrail 로그 확인
   - 영향받은 리소스 식별
   - 필요시 IAM 자격 증명 회전

2. **데이터 유출 의심 시:**
   - S3 액세스 로그 검토
   - VPC Flow Logs 분석
   - 보안 팀에 에스컬레이션

3. **무단 접근 시도:**
   - Security Group 규칙 강화
   - IAM 정책 검토
   - MFA 활성화 확인

## Contact Information

### Support Escalation

- **Level 1 (운영팀):** 일상적인 운영 및 모니터링
- **Level 2 (인프라팀):** 인프라 문제 및 성능 이슈
- **Level 3 (AWS Support):** AWS 서비스 관련 문제

### Emergency Contacts

- **On-Call Engineer:** [연락처]
- **Team Lead:** [연락처]
- **AWS Support:** AWS Console → Support Center

## Appendix

### Useful Commands Cheat Sheet

```bash
# Knowledge Base ID (실제 값)
KB_ID="FNNOP3VBZV"

# OpenSearch 컬렉션 엔드포인트 (실제 값)
COLLECTION_ENDPOINT="https://iw3pzcloa0en8d90hh7.us-east-1.aoss.amazonaws.com"

# Lambda 로그 실시간 확인
aws logs tail /aws/lambda/document-processor --follow --region us-east-1

# S3 복제 상태 확인
aws s3api head-object --bucket bos-ai-documents-seoul --key <key> --query 'ReplicationStatus'

# OpenSearch 컬렉션 상태
aws opensearchserverless list-collections --region us-east-1

# VPC Peering 상태
aws ec2 describe-vpc-peering-connections --region ap-northeast-2

# 비용 확인
aws ce get-cost-and-usage --time-period Start=$(date -d "$(date +%Y-%m-01)" +%Y-%m-%d),End=$(date +%Y-%m-%d) --granularity MONTHLY --metrics BlendedCost

# OpenSearch 인덱스 생성
cd scripts
python3 create-opensearch-index.py $COLLECTION_ENDPOINT bedrock-knowledge-base-index 1536
```

### Monitoring URLs

**실제 배포된 리소스:**
- Knowledge Base ID: `FNNOP3VBZV`
- OpenSearch Collection: `bos-ai-vectors`
- Lambda Function: `document-processor`
- S3 Buckets: `bos-ai-documents-seoul`, `bos-ai-documents-us`

**AWS Console URLs:**
- **CloudWatch Dashboard:** https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:
- **Bedrock Console:** https://console.aws.amazon.com/bedrock/home?region=us-east-1#/knowledge-bases/FNNOP3VBZV
- **OpenSearch Console:** https://console.aws.amazon.com/aos/home?region=us-east-1#opensearch/collections/bos-ai-vectors
- **Lambda Console:** https://console.aws.amazon.com/lambda/home?region=us-east-1#/functions/document-processor
- **S3 Console (Seoul):** https://s3.console.aws.amazon.com/s3/buckets/bos-ai-documents-seoul?region=ap-northeast-2
- **S3 Console (US):** https://s3.console.aws.amazon.com/s3/buckets/bos-ai-documents-us?region=us-east-1

### References

- [AWS Bedrock User Guide](https://docs.aws.amazon.com/bedrock/)
- [OpenSearch Serverless Developer Guide](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless.html)
- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/)
- [Terraform AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
