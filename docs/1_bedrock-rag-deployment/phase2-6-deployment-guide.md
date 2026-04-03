# BOS-AI VPC 통합 Phase 2-6 배포 가이드

## 개요

이 문서는 BOS-AI VPC 통합 마이그레이션의 Phase 2-6 배포를 위한 단계별 가이드입니다.

## 생성된 리소스 요약

### Phase 2: 네이밍 규칙 및 준비
- ✅ `docs/naming-conventions.md` - 네이밍 규칙 문서
- ✅ `docs/tagging-strategy.md` - 태그 전략 문서
- ✅ `environments/network-layer/terraform.tfvars` - Terraform 변수 파일
- ✅ `environments/network-layer/tag-updates.tf` - 태그 업데이트 코드

### Phase 3: VPC 엔드포인트
- ✅ `environments/network-layer/vpc-endpoints.tf` - VPC 엔드포인트 구성
- ✅ `modules/security/vpc-endpoints/` - 확장된 VPC 엔드포인트 모듈
  - Bedrock Runtime 엔드포인트
  - Secrets Manager 엔드포인트
  - CloudWatch Logs 엔드포인트
  - S3 Gateway 엔드포인트

### Phase 4: OpenSearch Serverless
- ✅ `environments/app-layer/opensearch-serverless.tf` - OpenSearch 구성
  - Security Group
  - Encryption Policy
  - Network Policy
  - Collection
  - VPC Endpoint
  - Data Access Policy

### Phase 5: Lambda
- ✅ `environments/app-layer/lambda.tf` - Lambda 구성
  - Security Group
  - IAM Role with minimal permissions
  - Lambda Function
  - CloudWatch Log Group

### Phase 6: Bedrock Knowledge Base
- ✅ `environments/app-layer/bedrock-kb.tf` - Bedrock KB 구성
  - Security Group
  - IAM Role
  - Knowledge Base
  - Data Sources (Virginia S3)

## 배포 전 준비사항

### 1. 실제 리소스 ID 확인

다음 명령으로 기존 리소스 ID를 확인하고 Terraform 파일의 플레이스홀더를 교체하세요:

```bash
# VPC ID 확인 (이미 알려진 값)
VPC_ID="vpc-066c464f9c750ee9e"

# 서브넷 ID 확인
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[*].[SubnetId,Tags[?Key==`Name`].Value|[0],AvailabilityZone]' \
  --output table

# Route Table ID 확인
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'RouteTables[*].[RouteTableId,Tags[?Key==`Name`].Value|[0]]' \
  --output table

# NAT Gateway ID 확인
aws ec2 describe-nat-gateways \
  --filter "Name=vpc-id,Values=$VPC_ID" \
  --query 'NatGateways[*].[NatGatewayId,Tags[?Key==`Name`].Value|[0]]' \
  --output table

# Internet Gateway ID 확인
aws ec2 describe-internet-gateways \
  --filters "Name=attachment.vpc-id,Values=$VPC_ID" \
  --query 'InternetGateways[*].[InternetGatewayId,Tags[?Key==`Name`].Value|[0]]' \
  --output table
```

### 2. 플레이스홀더 교체

다음 파일에서 플레이스홀더를 실제 값으로 교체:

**environments/network-layer/tag-updates.tf:**
- `subnet-0e0e0e0e0e0e0e0e0` → 실제 private subnet 2a ID
- `subnet-0f0f0f0f0f0f0f0f0` → 실제 private subnet 2c ID
- `subnet-0a0a0a0a0a0a0a0a0` → 실제 public subnet 2a ID
- `subnet-0b0b0b0b0b0b0b0b0` → 실제 public subnet 2c ID
- `rtb-private-id` → 실제 private route table ID
- `rtb-public-id` → 실제 public route table ID
- `nat-gateway-id` → 실제 NAT Gateway ID
- `igw-id` → 실제 Internet Gateway ID

**environments/network-layer/vpc-endpoints.tf:**
- `subnet-private-2a-id` → 실제 private subnet 2a ID
- `subnet-private-2c-id` → 실제 private subnet 2c ID
- `rtb-private-id` → 실제 private route table ID

**environments/app-layer/opensearch-serverless.tf:**
- `sg-lambda-id` → Lambda SG ID (배포 후)
- `sg-bedrock-kb-id` → Bedrock KB SG ID (배포 후)
- `vpce-opensearch-serverless-id` → OpenSearch VPC Endpoint ID (배포 후)
- `subnet-private-2a-id` → 실제 private subnet 2a ID
- `subnet-private-2c-id` → 실제 private subnet 2c ID

**environments/app-layer/lambda.tf:**
- `subnet-private-2a-id` → 실제 private subnet 2a ID
- `subnet-private-2c-id` → 실제 private subnet 2c ID

### 3. Lambda 배포 패키지 준비

```bash
cd lambda/document-processor
pip install -r requirements.txt -t package/
cd package
zip -r ../lambda-deployment-package.zip .
cd ..
zip -g lambda-deployment-package.zip index.py
mv lambda-deployment-package.zip ../../environments/app-layer/
```

## 배포 순서

### Phase 2: 태그 업데이트 (안전 - 메타데이터만)

```bash
cd environments/network-layer

# 1. Terraform 초기화
terraform init

# 2. 태그 업데이트 계획 확인
terraform plan -target=aws_ec2_tag.vpc_name \
               -target=aws_ec2_tag.vpc_project \
               -target=aws_ec2_tag.vpc_environment

# 3. 태그 업데이트 적용
terraform apply -target=aws_ec2_tag.vpc_name \
                -target=aws_ec2_tag.vpc_project \
                -target=aws_ec2_tag.vpc_environment

# 4. 모든 태그 업데이트 적용
terraform apply

# 5. 검증
aws ec2 describe-vpcs --vpc-ids vpc-066c464f9c750ee9e \
  --query 'Vpcs[0].Tags' --output table
```

### Phase 3: VPC 엔드포인트 배포

```bash
cd environments/network-layer

# 1. VPC 엔드포인트 계획 확인
terraform plan -target=aws_security_group.vpc_endpoints \
               -target=module.vpc_endpoints

# 2. VPC 엔드포인트 배포
terraform apply -target=aws_security_group.vpc_endpoints \
                -target=module.vpc_endpoints

# 3. 검증
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --query 'VpcEndpoints[*].[VpcEndpointId,ServiceName,State]' \
  --output table

# 4. 연결 테스트 (프라이빗 서브넷의 EC2에서)
nslookup bedrock-runtime.ap-northeast-2.amazonaws.com
nslookup secretsmanager.ap-northeast-2.amazonaws.com
```

### Phase 4: OpenSearch Serverless 배포

```bash
cd environments/app-layer

# 1. Terraform 초기화
terraform init

# 2. OpenSearch 계획 확인
terraform plan -target=aws_security_group.opensearch \
               -target=aws_opensearchserverless_security_policy.encryption \
               -target=aws_opensearchserverless_security_policy.network \
               -target=aws_opensearchserverless_collection.main

# 3. OpenSearch 배포
terraform apply -target=aws_security_group.opensearch \
                -target=aws_opensearchserverless_security_policy.encryption \
                -target=aws_opensearchserverless_security_policy.network \
                -target=aws_opensearchserverless_collection.main

# 4. VPC 엔드포인트 배포
terraform apply -target=aws_opensearchserverless_vpc_endpoint.main

# 5. 데이터 액세스 정책 배포
terraform apply -target=aws_opensearchserverless_access_policy.data_access

# 6. 검증
aws opensearchserverless list-collections \
  --query 'collectionSummaries[?name==`bos-ai-rag-vectors-prod`]' \
  --output table

# 7. 인덱스 생성
python3 ../scripts/create-opensearch-index.py \
  --collection-endpoint $(terraform output -raw opensearch_collection_endpoint) \
  --index-name bos-ai-documents
```

### Phase 5: Lambda 배포

```bash
cd environments/app-layer

# 1. Lambda 계획 확인
terraform plan -target=aws_security_group.lambda \
               -target=aws_iam_role.lambda \
               -target=aws_lambda_function.document_processor

# 2. Lambda 배포
terraform apply -target=aws_security_group.lambda \
                -target=aws_iam_role.lambda \
                -target=aws_lambda_function.document_processor

# 3. 검증
aws lambda get-function \
  --function-name lambda-document-processor-seoul-prod \
  --query 'Configuration.[FunctionName,State,VpcConfig]' \
  --output table

# 4. 테스트 실행
aws lambda invoke \
  --function-name lambda-document-processor-seoul-prod \
  --payload '{"test": true}' \
  response.json

cat response.json
```

### Phase 6: Bedrock Knowledge Base 배포

```bash
cd environments/app-layer

# 1. Bedrock KB 계획 확인
terraform plan -target=aws_security_group.bedrock_kb \
               -target=aws_iam_role.bedrock_kb \
               -target=aws_bedrockagent_knowledge_base.main

# 2. Bedrock KB 배포
terraform apply -target=aws_security_group.bedrock_kb \
                -target=aws_iam_role.bedrock_kb \
                -target=aws_bedrockagent_knowledge_base.main

# 3. 데이터 소스 배포
terraform apply -target=aws_bedrockagent_data_source.virginia_s3

# 4. 검증
aws bedrock-agent list-knowledge-bases \
  --query 'knowledgeBaseSummaries[?name==`bos-ai-kb-seoul-prod`]' \
  --output table

# 5. 동기화 시작
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id $(terraform output -raw bedrock_kb_id) \
  --data-source-id $(terraform output -raw virginia_data_source_id)

# 6. 동기화 상태 확인
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id $(terraform output -raw bedrock_kb_id) \
  --data-source-id $(terraform output -raw virginia_data_source_id) \
  --output table
```

## 배포 후 검증

### 1. 네트워크 연결성 테스트

```bash
# VPC 내부 EC2에서 실행
# OpenSearch 연결 테스트
curl -X GET "https://$(terraform output -raw opensearch_collection_endpoint)/_cluster/health" \
  --aws-sigv4 "aws:amz:ap-northeast-2:aoss"

# Bedrock 연결 테스트
aws bedrock-runtime invoke-model \
  --model-id amazon.titan-embed-text-v1 \
  --body '{"inputText":"test"}' \
  --region ap-northeast-2 \
  output.json
```

### 2. 전체 파이프라인 테스트

```bash
# 1. 테스트 문서 업로드 (Virginia S3)
aws s3 cp test-document.pdf s3://bos-ai-documents-us/documents/

# 2. Lambda 실행 확인
aws logs tail /aws/lambda/lambda-document-processor-seoul-prod --follow

# 3. OpenSearch 인덱싱 확인
curl -X GET "https://$(terraform output -raw opensearch_collection_endpoint)/bos-ai-documents/_search" \
  --aws-sigv4 "aws:amz:ap-northeast-2:aoss"

# 4. Knowledge Base 쿼리 테스트
aws bedrock-agent-runtime retrieve \
  --knowledge-base-id $(terraform output -raw bedrock_kb_id) \
  --retrieval-query '{"text":"test query"}' \
  --region ap-northeast-2
```

### 3. 기존 로깅 인프라 검증

```bash
# EC2 로그 수집기 상태 확인
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=ec2-logclt-itdev-int-poc-01" \
  --query 'Reservations[0].Instances[0].State' \
  --output table

# Firehose 전송 확인
aws firehose describe-delivery-stream \
  --delivery-stream-name your-firehose-stream \
  --query 'DeliveryStreamDescription.DeliveryStreamStatus'

# OpenSearch Managed 상태 확인
aws opensearch describe-domain \
  --domain-name open-mon-itdev-int-poc-001 \
  --query 'DomainStatus.[DomainName,Processing,Endpoint]' \
  --output table
```

## 롤백 절차

### Phase 6 롤백 (Bedrock KB)
```bash
cd environments/app-layer
terraform destroy -target=aws_bedrockagent_data_source.virginia_s3
terraform destroy -target=aws_bedrockagent_knowledge_base.main
terraform destroy -target=aws_iam_role.bedrock_kb
terraform destroy -target=aws_security_group.bedrock_kb
```

### Phase 5 롤백 (Lambda)
```bash
cd environments/app-layer
terraform destroy -target=aws_lambda_function.document_processor
terraform destroy -target=aws_iam_role.lambda
terraform destroy -target=aws_security_group.lambda
```

### Phase 4 롤백 (OpenSearch)
```bash
cd environments/app-layer
terraform destroy -target=aws_opensearchserverless_access_policy.data_access
terraform destroy -target=aws_opensearchserverless_vpc_endpoint.main
terraform destroy -target=aws_opensearchserverless_collection.main
terraform destroy -target=aws_opensearchserverless_security_policy.network
terraform destroy -target=aws_opensearchserverless_security_policy.encryption
terraform destroy -target=aws_security_group.opensearch
```

### Phase 3 롤백 (VPC Endpoints)
```bash
cd environments/network-layer
terraform destroy -target=module.vpc_endpoints
terraform destroy -target=aws_security_group.vpc_endpoints
```

### Phase 2 롤백 (태그)
```bash
cd environments/network-layer
# 태그는 메타데이터이므로 롤백 불필요
# 필요시 이전 태그 값으로 수동 변경
```

## 트러블슈팅

### 문제: VPC 엔드포인트 연결 실패
**해결:**
```bash
# Security Group 규칙 확인
aws ec2 describe-security-groups \
  --group-ids sg-vpc-endpoints-id \
  --query 'SecurityGroups[0].IpPermissions'

# Private DNS 활성화 확인
aws ec2 describe-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxx \
  --query 'VpcEndpoints[0].PrivateDnsEnabled'
```

### 문제: Lambda VPC 연결 실패
**해결:**
```bash
# ENI 생성 확인
aws ec2 describe-network-interfaces \
  --filters "Name=description,Values=AWS Lambda VPC ENI*" \
  --query 'NetworkInterfaces[*].[NetworkInterfaceId,Status,PrivateIpAddress]'

# Lambda 실행 로그 확인
aws logs tail /aws/lambda/lambda-document-processor-seoul-prod --follow
```

### 문제: OpenSearch 인덱스 생성 실패
**해결:**
```bash
# 수동으로 인덱스 생성
python3 scripts/create-opensearch-index.py \
  --collection-endpoint your-endpoint \
  --index-name bos-ai-documents \
  --verbose
```

## 모니터링

### CloudWatch 대시보드 생성
```bash
# 대시보드 생성 스크립트 실행
cd scripts
./create-monitoring-dashboard.sh
```

### 알람 설정
```bash
# 알람 생성
cd environments/monitoring
terraform init
terraform apply
```

## 다음 단계

Phase 2-6 배포 완료 후:

1. **Phase 7**: VPC 피어링 구성 (서울 ↔ 버지니아)
2. **Phase 8**: 통합 테스트
3. **Phase 9**: 기존 BOS-AI-RAG VPC 제거
4. **Phase 10**: 모니터링 및 문서화

## 참고 자료

- [네이밍 규칙](./naming-conventions.md)
- [태그 전략](./tagging-strategy.md)
- [운영 가이드](./OPERATIONAL_RUNBOOK.md)
- [테스트 가이드](./TESTING_GUIDE.md)

## 지원

문제 발생 시:
1. CloudWatch Logs 확인
2. Terraform state 확인: `terraform show`
3. AWS 리소스 상태 확인
4. 이 가이드의 트러블슈팅 섹션 참조
