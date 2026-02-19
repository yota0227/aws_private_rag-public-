# BOS-AI VPC 통합 배포 실행 가이드

## 개요

이 가이드는 Phase 2-6의 실제 AWS 배포 절차를 설명합니다. AI가 생성한 Terraform 코드를 실제 AWS 환경에 배포하는 방법을 단계별로 안내합니다.

**중요**: AI는 실제 AWS 리소스를 배포할 수 없습니다. 이 가이드를 따라 수동으로 배포해야 합니다.

## 사전 준비

### 1. 필수 도구 확인

```bash
# AWS CLI 설치 확인
aws --version

# Terraform 설치 확인
terraform --version

# jq 설치 확인 (JSON 파싱용)
jq --version
```

### 2. AWS 자격 증명 확인

```bash
# 현재 AWS 계정 확인
aws sts get-caller-identity

# 출력 예시:
# {
#     "UserId": "AIDAXXXXXXXXXXXXXXXXX",
#     "Account": "533335672315",
#     "Arn": "arn:aws:iam::533335672315:user/your-username"
# }
```

### 3. 작업 디렉토리 확인

```bash
# 프로젝트 루트로 이동
cd ~/bos-ai-infra

# Git 상태 확인
git status
```

## 배포 절차

### Step 1: 리소스 ID 수집

배포 준비 스크립트를 실행하여 실제 AWS 리소스 ID를 수집합니다.

```bash
# 스크립트 실행
./scripts/prepare-deployment.sh
```

**예상 출력:**
```
========================================
BOS-AI VPC Consolidation
Deployment Preparation Script
========================================

[INFO] AWS Account ID: 533335672315
[INFO] Target VPC: vpc-066c464f9c750ee9e
[INFO] Region: ap-northeast-2

[STEP 1] Collecting Subnet IDs...
  - subnet-xxxxx | 10.200.1.0/24 | ap-northeast-2a | sn-private-seoul-poc-01a
  - subnet-xxxxx | 10.200.2.0/24 | ap-northeast-2c | sn-private-seoul-poc-01c
  ...

[SUCCESS] All resource IDs validated successfully
[SUCCESS] Replacement script created: scripts/replace-placeholders.sh
[SUCCESS] Deployment summary created: docs/deployment-resource-ids.md

✅ Deployment Preparation Complete!
```

**생성된 파일:**
- `scripts/replace-placeholders.sh` - 플레이스홀더 교체 스크립트
- `docs/deployment-resource-ids.md` - 수집된 리소스 ID 요약

### Step 2: 플레이스홀더 교체

수집된 리소스 ID로 Terraform 파일의 플레이스홀더를 교체합니다.

```bash
# 교체 스크립트 실행
./scripts/replace-placeholders.sh
```

**예상 출력:**
```
Replacing placeholders in Terraform files...
✅ Placeholder replacement complete!
Backup files created with .bak extension
```

**백업 파일:**
- `*.tf.bak` - 원본 파일 백업 (롤백용)

### Step 3: 변경 사항 검토

교체된 내용을 확인합니다.

```bash
# Git diff로 변경 사항 확인
git diff environments/network-layer/tag-updates.tf
git diff environments/network-layer/vpc-endpoints.tf
git diff environments/app-layer/opensearch-serverless.tf
git diff environments/app-layer/lambda.tf
git diff environments/app-layer/bedrock-kb.tf

# 또는 모든 변경 사항 확인
git diff environments/
```

**확인 사항:**
- ✅ 모든 플레이스홀더가 실제 리소스 ID로 교체되었는지
- ✅ 서브넷 ID가 올바른 AZ와 매칭되는지
- ✅ 계정 ID가 정확한지

### Step 4: Phase 2 배포 (태그 업데이트)

**안전성**: 메타데이터만 변경, 리소스 영향 없음

```bash
# Network Layer 디렉토리로 이동
cd environments/network-layer

# Terraform 초기화
terraform init

# 변경 사항 미리보기
terraform plan

# 태그 업데이트 적용
terraform apply

# 확인 프롬프트에서 'yes' 입력
```

**검증:**
```bash
# VPC 태그 확인
aws ec2 describe-vpcs \
  --vpc-ids vpc-066c464f9c750ee9e \
  --region ap-northeast-2 \
  --query 'Vpcs[0].Tags'

# 서브넷 태그 확인
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --region ap-northeast-2 \
  --query 'Subnets[*].[SubnetId,Tags[?Key==`Name`].Value|[0]]'
```

**예상 결과:**
- VPC Name 태그: `vpc-bos-ai-seoul-prod-01`
- 서브넷 Name 태그: `sn-private-bos-ai-seoul-prod-01a` 등

### Step 5: Phase 3 배포 (VPC 엔드포인트)

**안전성**: 신규 리소스만 생성, 기존 인프라 영향 없음

```bash
# Network Layer 디렉토리에서 계속
cd environments/network-layer

# Security Group 생성
terraform apply -target=aws_security_group.vpc_endpoints

# VPC 엔드포인트 생성
terraform apply -target=module.vpc_endpoints
```

**검증:**
```bash
# VPC 엔드포인트 확인
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --region ap-northeast-2 \
  --query 'VpcEndpoints[*].[VpcEndpointId,ServiceName,State]'

# Private DNS 확인 (VPC 내부 EC2에서)
nslookup bedrock-runtime.ap-northeast-2.amazonaws.com
nslookup secretsmanager.ap-northeast-2.amazonaws.com
```

**예상 결과:**
- 5개 VPC 엔드포인트 생성 (Bedrock, Secrets Manager, Logs, S3)
- 상태: `available`
- Private DNS 활성화됨

### Step 6: Phase 4 배포 (OpenSearch Serverless)

**안전성**: 신규 리소스만 생성

```bash
# App Layer 디렉토리로 이동
cd ../app-layer

# Terraform 초기화
terraform init

# Security Group 생성
terraform apply -target=aws_security_group.opensearch

# OpenSearch 컬렉션 생성
terraform apply -target=aws_opensearchserverless_collection.main

# VPC 엔드포인트 생성
terraform apply -target=aws_opensearchserverless_vpc_endpoint.main

# 액세스 정책 적용
terraform apply -target=aws_opensearchserverless_access_policy.data_access
terraform apply -target=aws_opensearchserverless_security_policy.network
terraform apply -target=aws_opensearchserverless_security_policy.encryption
```

**검증:**
```bash
# 컬렉션 상태 확인
aws opensearchserverless list-collections \
  --region ap-northeast-2

# VPC 엔드포인트 확인
aws opensearchserverless list-vpc-endpoints \
  --region ap-northeast-2

# 연결 테스트 (VPC 내부 EC2에서)
curl -X GET "https://[collection-endpoint]/bos-ai-documents/_search" \
  --aws-sigv4 "aws:amz:ap-northeast-2:aoss" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY"
```

**예상 결과:**
- 컬렉션 상태: `ACTIVE`
- VPC 엔드포인트 상태: `ACTIVE`
- 연결 테스트 성공

### Step 7: Lambda 배포 패키지 준비

Lambda 함수 배포 전에 배포 패키지를 준비합니다.

```bash
# Lambda 디렉토리로 이동
cd ../../lambda/document-processor

# 의존성 설치
pip install -r requirements.txt -t package/

# 배포 패키지 생성
cd package
zip -r ../lambda-deployment-package.zip .
cd ..
zip -g lambda-deployment-package.zip index.py

# App Layer로 이동
mv lambda-deployment-package.zip ../../environments/app-layer/
cd ../../environments/app-layer
```

### Step 8: Phase 5 배포 (Lambda)

**안전성**: 신규 리소스만 생성

```bash
# App Layer 디렉토리에서 계속
cd environments/app-layer

# Security Group 생성
terraform apply -target=aws_security_group.lambda

# IAM Role 생성
terraform apply -target=aws_iam_role.lambda
terraform apply -target=aws_iam_role_policy_attachment.lambda_s3
terraform apply -target=aws_iam_role_policy_attachment.lambda_opensearch
terraform apply -target=aws_iam_role_policy_attachment.lambda_bedrock
terraform apply -target=aws_iam_role_policy_attachment.lambda_secrets
terraform apply -target=aws_iam_role_policy_attachment.lambda_logs
terraform apply -target=aws_iam_role_policy_attachment.lambda_vpc

# Lambda 함수 생성
terraform apply -target=aws_lambda_function.document_processor
```

**검증:**
```bash
# Lambda 함수 확인
aws lambda get-function \
  --function-name lambda-document-processor-seoul-prod \
  --region ap-northeast-2

# 테스트 실행
aws lambda invoke \
  --function-name lambda-document-processor-seoul-prod \
  --region ap-northeast-2 \
  --payload '{"test": true}' \
  response.json

# 로그 확인
aws logs tail /aws/lambda/lambda-document-processor-seoul-prod \
  --region ap-northeast-2 \
  --follow
```

**예상 결과:**
- 함수 상태: `Active`
- VPC 설정: ENI 생성됨
- 테스트 실행 성공

### Step 9: Phase 6 배포 (Bedrock Knowledge Base)

**안전성**: 신규 리소스만 생성

```bash
# App Layer 디렉토리에서 계속
cd environments/app-layer

# Security Group 생성
terraform apply -target=aws_security_group.bedrock_kb

# IAM Role 생성
terraform apply -target=aws_iam_role.bedrock_kb
terraform apply -target=aws_iam_role_policy_attachment.bedrock_kb_s3
terraform apply -target=aws_iam_role_policy_attachment.bedrock_kb_opensearch
terraform apply -target=aws_iam_role_policy_attachment.bedrock_kb_bedrock

# Knowledge Base 생성
terraform apply -target=aws_bedrockagent_knowledge_base.main

# 데이터 소스 연결
terraform apply -target=aws_bedrockagent_data_source.virginia_s3
```

**검증:**
```bash
# Knowledge Base 확인
aws bedrock-agent list-knowledge-bases \
  --region ap-northeast-2

# 데이터 소스 확인
aws bedrock-agent list-data-sources \
  --knowledge-base-id [kb-id] \
  --region ap-northeast-2

# 동기화 시작
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id [kb-id] \
  --data-source-id [ds-id] \
  --region ap-northeast-2

# 쿼리 테스트
aws bedrock-agent-runtime retrieve \
  --knowledge-base-id [kb-id] \
  --retrieval-query '{"text": "test query"}' \
  --region ap-northeast-2
```

**예상 결과:**
- Knowledge Base 상태: `ACTIVE`
- 데이터 소스 연결됨
- 동기화 성공
- 쿼리 테스트 성공

### Step 10: 전체 검증

모든 Phase가 완료되면 전체 시스템을 검증합니다.

```bash
# 프로젝트 루트로 이동
cd ~/bos-ai-infra

# 전체 리소스 확인
terraform show

# 상태 파일 백업
cp terraform.tfstate backups/terraform.tfstate.phase2-6.$(date +%Y%m%d_%H%M%S)
```

**검증 체크리스트:**

Phase 2:
- [ ] VPC 태그가 `vpc-bos-ai-seoul-prod-01`로 변경됨
- [ ] 모든 서브넷 태그가 새 네이밍 규칙을 따름
- [ ] 필수 태그 5개가 모든 리소스에 존재

Phase 3:
- [ ] VPC 엔드포인트 5개 생성됨
- [ ] Private DNS 활성화됨
- [ ] nslookup으로 AWS 서비스 도메인 해석 확인

Phase 4:
- [ ] OpenSearch 컬렉션 상태: ACTIVE
- [ ] VPC 엔드포인트 생성됨
- [ ] VPC 내부에서 연결 테스트 성공

Phase 5:
- [ ] Lambda 함수 상태: Active
- [ ] VPC 설정 확인 (ENI 생성됨)
- [ ] 테스트 실행 성공
- [ ] CloudWatch Logs 확인

Phase 6:
- [ ] Knowledge Base 생성됨
- [ ] 데이터 소스 연결됨
- [ ] 동기화 작업 성공
- [ ] 쿼리 테스트 성공

## 롤백 절차

문제 발생 시 각 Phase를 역순으로 롤백할 수 있습니다.

### Phase 6 롤백
```bash
cd environments/app-layer
terraform destroy -target=aws_bedrockagent_data_source.virginia_s3
terraform destroy -target=aws_bedrockagent_knowledge_base.main
terraform destroy -target=aws_iam_role.bedrock_kb
terraform destroy -target=aws_security_group.bedrock_kb
```

### Phase 5 롤백
```bash
terraform destroy -target=aws_lambda_function.document_processor
terraform destroy -target=aws_iam_role.lambda
terraform destroy -target=aws_security_group.lambda
```

### Phase 4 롤백
```bash
terraform destroy -target=aws_opensearchserverless_access_policy.data_access
terraform destroy -target=aws_opensearchserverless_security_policy.network
terraform destroy -target=aws_opensearchserverless_security_policy.encryption
terraform destroy -target=aws_opensearchserverless_vpc_endpoint.main
terraform destroy -target=aws_opensearchserverless_collection.main
terraform destroy -target=aws_security_group.opensearch
```

### Phase 3 롤백
```bash
cd environments/network-layer
terraform destroy -target=module.vpc_endpoints
terraform destroy -target=aws_security_group.vpc_endpoints
```

### Phase 2 롤백
```bash
# 백업 파일에서 원본 복원
cp tag-updates.tf.bak tag-updates.tf
terraform apply
```

## 문제 해결

### 1. 리소스 ID를 찾을 수 없음

**증상:**
```
[ERROR] Private Subnet 2a not found
```

**해결:**
```bash
# 수동으로 서브넷 확인
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --region ap-northeast-2

# CIDR 블록으로 필터링
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" "Name=cidr-block,Values=10.200.1.0/24" \
  --region ap-northeast-2 \
  --query 'Subnets[0].SubnetId'
```

### 2. Terraform 초기화 실패

**증상:**
```
Error: Failed to get existing workspaces
```

**해결:**
```bash
# Backend 재초기화
terraform init -reconfigure

# 또는 강제 초기화
terraform init -upgrade
```

### 3. Lambda 배포 패키지 오류

**증상:**
```
Error: error creating Lambda Function: InvalidParameterValueException
```

**해결:**
```bash
# 배포 패키지 재생성
cd lambda/document-processor
rm -rf package/ lambda-deployment-package.zip
pip install -r requirements.txt -t package/
cd package && zip -r ../lambda-deployment-package.zip .
cd .. && zip -g lambda-deployment-package.zip index.py
```

### 4. OpenSearch 연결 실패

**증상:**
```
curl: (6) Could not resolve host
```

**해결:**
```bash
# VPC 엔드포인트 확인
aws opensearchserverless list-vpc-endpoints --region ap-northeast-2

# Security Group 규칙 확인
aws ec2 describe-security-groups \
  --group-ids [sg-id] \
  --region ap-northeast-2

# Network Policy 확인
aws opensearchserverless get-security-policy \
  --name bos-ai-rag-vectors-prod-network \
  --type network \
  --region ap-northeast-2
```

## 다음 단계

Phase 2-6 배포 완료 후:

1. **Phase 7**: VPC 피어링 구성 (서울 ↔ 버지니아)
2. **Phase 8**: 통합 테스트
3. **Phase 9**: 기존 VPC 제거
4. **Phase 10**: 모니터링 및 문서화

각 Phase는 사용자 승인 후 진행됩니다.

## 참고 문서

- [Phase 2-6 배포 가이드](./phase2-6-deployment-guide.md)
- [Phase 2-6 완료 요약](./phase2-6-completion-summary.md)
- [네이밍 규칙](./naming-conventions.md)
- [태그 전략](./tagging-strategy.md)

## 지원

문제 발생 시:
1. 이 가이드의 문제 해결 섹션 참조
2. Terraform 로그 확인: `TF_LOG=DEBUG terraform apply`
3. AWS CloudTrail에서 API 호출 확인
4. 팀 리더에게 에스컬레이션

---

**작성일**: 2025-01-XX  
**버전**: 1.0  
**작성자**: BOS-AI Infrastructure Team
