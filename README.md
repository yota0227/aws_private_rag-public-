# AWS Bedrock RAG Infrastructure

AWS Bedrock 기반 RAG(Retrieval-Augmented Generation) 시스템을 위한 프로덕션급 Terraform IaC 프로젝트입니다.

## 🏗️ 아키텍처 개요

### 멀티 리전 구성
- **서울 리전 (ap-northeast-2)**: 
  - Transit Bridge VPC (기존 인프라 연동)
  - VPN Gateway (온프레미스 연결)
  - S3 소스 버킷 (문서 업로드)
  - 3개 가용 영역 (고가용성)

- **미국 리전 (us-east-1)**: 
  - AI 워크로드 VPC
  - Bedrock Knowledge Base (RAG 엔진)
  - OpenSearch Serverless (벡터 DB)
  - Lambda 문서 처리 파이프라인
  - S3 대상 버킷 (복제된 문서)
  - 3개 가용 영역 (고가용성)

### 네트워크 아키텍처
- **VPC Peering**: 서울-미국 간 프라이빗 네트워크 연결 (10.0.0.0/16 ↔ 10.1.0.0/16)
- **No-IGW 정책**: 모든 VPC에서 인터넷 게이트웨이 없음 (보안 강화)
- **PrivateLink**: VPC 엔드포인트를 통한 AWS 서비스 접근
  - Bedrock Runtime
  - Bedrock Agent Runtime
  - S3 Gateway Endpoint
  - OpenSearch Serverless
- **NAT Gateway**: 각 가용 영역별 NAT Gateway (아웃바운드 트래픽)

### 데이터 흐름
```
[온프레미스] 
    ↓ VPN
[서울 VPC] → [S3 Seoul] 
    ↓ Cross-Region Replication
[S3 US] → [Lambda] → [Bedrock KB] ← [OpenSearch Serverless]
    ↓ S3 Event
[Knowledge Base Sync]
```

## 📁 프로젝트 구조

```
bos-ai-infra/
├── modules/                           # 재사용 가능한 Terraform 모듈
│   ├── network/
│   │   ├── vpc/                      # VPC, 서브넷, 라우팅 테이블
│   │   ├── peering/                  # VPC Peering 연결
│   │   ├── security-groups/          # 보안 그룹 규칙
│   │   └── network-acls/             # 네트워크 ACL
│   ├── security/
│   │   ├── kms/                      # KMS 암호화 키
│   │   ├── iam/                      # IAM 역할 및 정책
│   │   ├── vpc-endpoints/            # PrivateLink 엔드포인트
│   │   └── cloudtrail/               # 감사 로깅
│   ├── ai-workload/
│   │   ├── s3-pipeline/              # S3 버킷, Lambda, 복제
│   │   └── bedrock-rag/              # Bedrock KB, OpenSearch
│   ├── monitoring/
│   │   ├── cloudwatch-logs/          # 로그 그룹
│   │   ├── cloudwatch-alarms/        # 알람 설정
│   │   ├── cloudwatch-dashboards/    # 대시보드
│   │   └── vpc-flow-logs/            # VPC 플로우 로그
│   └── cost-management/
│       └── budgets/                  # AWS Budgets
├── environments/                      # 환경별 배포 구성
│   ├── global/
│   │   └── backend/                  # Terraform 상태 백엔드
│   ├── network-layer/                # 네트워크 인프라
│   │   ├── main.tf                   # Seoul + US VPC, Peering
│   │   ├── providers.tf              # Multi-region providers
│   │   └── outputs.tf                # VPC ID, 서브넷 등
│   └── app-layer/
│       └── bedrock-rag/              # AI 워크로드
│           ├── main.tf               # KMS, IAM, S3, Lambda, Bedrock
│           ├── data.tf               # Remote state 참조
│           └── variables.tf          # 환경 변수
├── lambda/
│   └── document-processor/           # Lambda 함수 코드
│       ├── handler.py                # 메인 핸들러
│       ├── requirements.txt          # Python 의존성
│       └── test_handler.py           # 단위 테스트
├── tests/                            # 테스트 스위트
│   ├── properties/                   # Property-based tests (47개)
│   │   ├── vpc_properties_test.go
│   │   ├── bedrock_properties_test.go
│   │   └── ...
│   ├── unit/                         # 단위 테스트
│   │   └── vpn_import_test.go
│   └── integration/                  # 통합 테스트
│       ├── bedrock_kb_test.go
│       ├── lambda_invocation_test.go
│       └── s3_replication_test.go
├── policies/                         # Policy-as-Code (OPA)
│   ├── security.rego                 # 보안 정책
│   ├── cost.rego                     # 비용 정책
│   └── compliance.rego               # 컴플라이언스 정책
├── scripts/                          # 유틸리티 스크립트
│   ├── terraform-validate.sh         # Terraform 검증
│   ├── run-policy-tests.sh           # 정책 테스트
│   ├── run-integration-tests.sh      # 통합 테스트
│   ├── cost-estimation.sh            # 비용 추정
│   ├── identify-vpn-gateway.sh       # VPN Gateway 탐지
│   └── create-opensearch-index.py    # OpenSearch 인덱스 생성
└── docs/                             # 문서
    ├── DEPLOYMENT_GUIDE.md           # 배포 가이드
    ├── OPERATIONAL_RUNBOOK.md        # 운영 가이드
    └── TESTING_GUIDE.md              # 테스트 가이드
```

## 🚀 배포 가이드

### 사전 요구사항

#### 필수 도구
- **Terraform** >= 1.5.0
- **AWS CLI** >= 2.0 (자격 증명 구성 완료)
- **Go** >= 1.21 (테스트용)
- **Python** >= 3.11 (Lambda 및 스크립트용)
- **jq** (JSON 처리용)

#### AWS 권한
배포를 위해 다음 권한이 필요합니다:
- VPC, Subnet, Route Table 생성/수정
- S3 버킷 생성 및 복제 설정
- Lambda 함수 생성 및 VPC 연결
- Bedrock Knowledge Base 생성
- OpenSearch Serverless 컬렉션 생성
- KMS 키 생성 및 정책 관리
- IAM 역할 및 정책 생성
- CloudWatch 로그, 알람, 대시보드 생성
- CloudTrail 생성

#### Python 패키지 (OpenSearch 인덱스 생성용)
```bash
pip3 install boto3 requests-aws4auth --break-system-packages
```

### 배포 순서

#### 1단계: Global Backend 배포 (최초 1회)

Terraform 상태를 저장할 S3 버킷과 DynamoDB 테이블을 생성합니다.

```bash
cd environments/global/backend
terraform init
terraform plan
terraform apply
```

**생성 리소스:**
- S3 버킷: `bos-ai-terraform-state` (버전 관리, 암호화 활성화)
- DynamoDB 테이블: `bos-ai-terraform-locks` (상태 잠금)

#### 2단계: Network Layer 배포

서울과 미국 리전에 VPC를 생성하고 Peering 연결을 설정합니다.

```bash
cd environments/network-layer
terraform init
terraform plan
terraform apply
```

**생성 리소스 (35개):**
- Seoul VPC (10.0.0.0/16)
  - 3개 Public 서브넷
  - 3개 Private 서브넷
  - 3개 NAT Gateway
  - Route Tables, Security Groups
  - VPN Gateway (기존 인프라 import)
- US VPC (10.1.0.0/16)
  - 3개 Public 서브넷
  - 3개 Private 서브넷
  - 3개 NAT Gateway
  - Route Tables, Security Groups
- VPC Peering 연결 (Seoul ↔ US)

**배포 시간:** 약 5-7분

**주의사항:**
- VPN Gateway가 이미 존재하는 경우 자동으로 import됩니다
- VPN Gateway가 없으면 새로 생성됩니다
- NAT Gateway 생성으로 인해 비용이 발생합니다 ($0.045/시간 × 6개 = ~$200/월)

#### 3단계: App Layer 배포

AI 워크로드 리소스를 미국 리전에 배포합니다.

```bash
cd environments/app-layer/bedrock-rag
terraform init
terraform plan
terraform apply
```

**생성 리소스 (95개):**
- **보안**
  - KMS 암호화 키 (모든 서비스 접근 권한)
  - IAM 역할 3개 (Bedrock KB, Lambda, VPC Flow Logs)
  - IAM 정책 8개 (최소 권한 원칙)
  - VPC 엔드포인트 4개 (Bedrock, S3, OpenSearch)
  - CloudTrail (감사 로깅)

- **스토리지 및 처리**
  - S3 버킷 2개 (Seoul 소스, US 대상)
  - Cross-Region Replication (Seoul → US)
  - Lambda 함수 (document-processor)
  - SQS Dead Letter Queue

- **AI 워크로드**
  - OpenSearch Serverless 컬렉션
  - OpenSearch 벡터 인덱스 (1536 차원)
  - Bedrock Knowledge Base
  - Bedrock Data Source (S3)

- **모니터링**
  - CloudWatch 로그 그룹 5개
  - CloudWatch 알람 3개
  - CloudWatch 대시보드
  - VPC Flow Logs

- **비용 관리**
  - AWS Budgets (월별 예산 알림)
  - SNS 토픽 (알림용)

**배포 시간:** 약 8-10분

### 배포 중 발생 가능한 이슈 및 해결 방법

#### 이슈 1: OpenSearch 인덱스 생성 실패

**증상:**
```
ValidationException: The knowledge base storage configuration provided is invalid... 
no such index [bedrock-knowledge-base-index]
```

**원인:** OpenSearch Serverless는 Terraform으로 인덱스를 직접 생성할 수 없습니다.

**해결 방법:**

1. OpenSearch 컬렉션 엔드포인트 확인:
```bash
terraform output opensearch_collection_endpoint
# 출력: https://xxx.us-east-1.aoss.amazonaws.com
```

2. 현재 사용자를 OpenSearch 데이터 액세스 정책에 추가:
```bash
# 현재 사용자 ARN 확인
aws sts get-caller-identity

# 데이터 액세스 정책 업데이트
POLICY_VERSION=$(aws opensearchserverless get-access-policy \
  --name bos-ai-vectors-data-access \
  --type data \
  --region us-east-1 | jq -r '.accessPolicyDetail.policyVersion')

aws opensearchserverless update-access-policy \
  --name bos-ai-vectors-data-access \
  --type data \
  --policy-version $POLICY_VERSION \
  --policy '[{
    "Rules": [
      {
        "ResourceType": "collection",
        "Resource": ["collection/bos-ai-vectors"],
        "Permission": ["aoss:CreateCollectionItems", "aoss:UpdateCollectionItems", "aoss:DescribeCollectionItems"]
      },
      {
        "ResourceType": "index",
        "Resource": ["index/bos-ai-vectors/*"],
        "Permission": ["aoss:CreateIndex", "aoss:DescribeIndex", "aoss:ReadDocument", "aoss:WriteDocument", "aoss:UpdateIndex", "aoss:DeleteIndex"]
      }
    ],
    "Principal": [
      "arn:aws:iam::YOUR_ACCOUNT_ID:role/bos-ai-bedrock-kb-role-dev",
      "arn:aws:iam::YOUR_ACCOUNT_ID:user/YOUR_USER"
    ]
  }]' \
  --region us-east-1
```

3. Python 스크립트로 인덱스 생성:
```bash
python3 scripts/create-opensearch-index.py \
  https://xxx.us-east-1.aoss.amazonaws.com \
  bedrock-knowledge-base-index \
  1536
```

4. Terraform apply 재실행:
```bash
terraform apply
```

#### 이슈 2: CloudWatch Log Groups 중복

**증상:**
```
ResourceAlreadyExistsException: The specified log group already exists
```

**원인:** Lambda나 Bedrock이 자동으로 로그 그룹을 생성하는 경우가 있습니다.

**해결 방법:**

1. 기존 로그 그룹 삭제:
```bash
aws logs delete-log-group \
  --log-group-name /aws/bedrock/knowledgebase/bos-ai-knowledge-base \
  --region us-east-1

aws logs delete-log-group \
  --log-group-name /aws/lambda/document-processor \
  --region us-east-1
```

2. Terraform apply 재실행:
```bash
terraform apply
```

#### 이슈 3: Lambda VPC 연결 타임아웃

**증상:**
Lambda 함수 생성이 5분 이상 소요되거나 타임아웃 발생

**원인:** 
- VPC 서브넷에 NAT Gateway가 없거나
- Security Group이 아웃바운드 트래픽을 차단하거나
- VPC 엔드포인트가 제대로 설정되지 않음

**해결 방법:**

1. NAT Gateway 확인:
```bash
aws ec2 describe-nat-gateways \
  --filter "Name=vpc-id,Values=$(terraform output -raw us_vpc_id)" \
  --region us-east-1
```

2. Security Group 아웃바운드 규칙 확인:
```bash
aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=$(terraform output -raw us_vpc_id)" \
  --region us-east-1
```

3. VPC 엔드포인트 상태 확인:
```bash
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=$(terraform output -raw us_vpc_id)" \
  --region us-east-1
```

#### 이슈 4: S3 Cross-Region Replication 실패

**증상:**
```
InvalidRequest: The replication configuration is not valid
```

**원인:** 
- 소스 또는 대상 버킷에 버전 관리가 활성화되지 않음
- KMS 키 권한 부족
- IAM 역할 권한 부족

**해결 방법:**

1. 버킷 버전 관리 확인:
```bash
aws s3api get-bucket-versioning --bucket bos-ai-documents-seoul
aws s3api get-bucket-versioning --bucket bos-ai-documents-us --region us-east-1
```

2. KMS 키 정책 확인:
```bash
aws kms get-key-policy \
  --key-id $(terraform output -raw kms_key_id) \
  --policy-name default \
  --region us-east-1
```

3. IAM 역할 확인:
```bash
aws iam get-role --role-name bos-ai-s3-replication-role-dev
```

#### 이슈 5: Bedrock 모델 접근 권한 없음

**증상:**
```
AccessDeniedException: You don't have access to the model
```

**원인:** Bedrock 모델에 대한 접근 권한이 활성화되지 않음

**해결 방법:**

1. AWS Console에서 Bedrock 모델 접근 활성화:
   - Bedrock 콘솔 → Model access
   - Amazon Titan Embed Text v1 활성화
   - Anthropic Claude 모델 활성화 (선택사항)

2. 또는 AWS CLI로 활성화:
```bash
aws bedrock put-model-invocation-logging-configuration \
  --region us-east-1
```

### 배포 검증

배포가 완료되면 다음 명령어로 리소스를 확인합니다:

```bash
# 모든 출력 확인
terraform output

# Knowledge Base ID 확인
terraform output knowledge_base_id

# OpenSearch 엔드포인트 확인
terraform output opensearch_collection_endpoint

# Lambda 함수 확인
aws lambda get-function \
  --function-name document-processor \
  --region us-east-1

# Bedrock Knowledge Base 상태 확인
aws bedrock-agent get-knowledge-base \
  --knowledge-base-id $(terraform output -raw knowledge_base_id) \
  --region us-east-1
```

## 🧪 테스트

### Terraform 검증

모든 Terraform 구성 파일의 문법과 유효성을 검증합니다:

```bash
./scripts/terraform-validate.sh
```

**검증 항목:**
- Terraform 문법 검사 (`terraform validate`)
- 포맷 검사 (`terraform fmt -check`)
- 모듈 의존성 검사

### Policy-as-Code 테스트

OPA(Open Policy Agent)를 사용한 정책 검증:

```bash
./scripts/run-policy-tests.sh
```

**검증 정책:**
- **보안 정책** (`policies/security.rego`)
  - 모든 S3 버킷 암호화 필수
  - 모든 S3 버킷 버전 관리 활성화
  - 모든 S3 버킷 퍼블릭 액세스 차단
  - KMS 키 자동 로테이션 활성화
  - CloudTrail 로그 파일 검증 활성화

- **비용 정책** (`policies/cost.rego`)
  - S3 Lifecycle 정책 설정 필수
  - S3 Intelligent-Tiering 활성화
  - Lambda 메모리 제한 (최대 3008MB)
  - Lambda 타임아웃 제한 (최대 900초)

- **컴플라이언스 정책** (`policies/compliance.rego`)
  - 모든 리소스 태그 필수 (Project, Environment, ManagedBy)
  - VPC Flow Logs 활성화
  - CloudTrail 멀티 리전 활성화

### Property-Based 테스트

Go를 사용한 속성 기반 테스트 (47개 테스트):

```bash
cd tests
go test -v ./properties/
```

**테스트 모듈:**
- `vpc_properties_test.go` - VPC CIDR, 서브넷 검증
- `vpc_peering_properties_test.go` - Peering 연결 검증
- `security_groups_properties_test.go` - 보안 그룹 규칙 검증
- `kms_properties_test.go` - KMS 키 정책 검증
- `iam_properties_test.go` - IAM 최소 권한 검증
- `s3_pipeline_properties_test.go` - S3 복제 설정 검증
- `bedrock_properties_test.go` - Bedrock KB 구성 검증
- `opensearch_properties_test.go` - OpenSearch 인덱스 검증
- `lambda_properties_test.go` - Lambda VPC 구성 검증
- `monitoring_properties_test.go` - CloudWatch 설정 검증

**실행 예시:**
```bash
# 특정 모듈만 테스트
go test -v ./properties/ -run TestVPCProperties

# 병렬 실행
go test -v -parallel 4 ./properties/

# 커버리지 확인
go test -v -cover ./properties/
```

### 단위 테스트

개별 모듈의 단위 테스트:

```bash
cd tests
go test -v ./unit/
```

### 통합 테스트 (⚠️ 비용 발생 주의!)

실제 AWS 리소스를 생성하여 테스트합니다:

```bash
./scripts/run-integration-tests.sh
```

**테스트 시나리오:**
- `bedrock_kb_test.go` - Knowledge Base 생성 및 쿼리
- `lambda_invocation_test.go` - Lambda 함수 호출 및 S3 이벤트
- `s3_replication_test.go` - Cross-Region Replication 검증
- `vpc_peering_test.go` - VPC Peering 연결 테스트

**주의사항:**
- 통합 테스트는 실제 AWS 리소스를 생성하므로 비용이 발생합니다
- 테스트 완료 후 자동으로 리소스를 정리합니다
- 테스트 실행 시간: 약 15-20분
- 예상 비용: $5-10 (테스트 1회당)

**환경 변수 설정:**
```bash
export AWS_REGION=us-east-1
export TF_VAR_project_name=bos-ai-test
export TF_VAR_environment=test
```

자세한 테스트 가이드는 [TESTING_GUIDE.md](docs/TESTING_GUIDE.md)를 참조하세요.

## 💰 비용 분석

### 월별 예상 비용

| 구성 요소 | Baseline | Medium | High | 설명 |
|---------|----------|--------|------|------|
| **컴퓨팅** |
| Lambda (US) | $5-10 | $25-50 | $100-200 | 문서 처리 (1GB 메모리, 300초) |
| **스토리지** |
| S3 Seoul | $23 | $115 | $460 | 100GB / 500GB / 2TB |
| S3 US | $23 | $115 | $460 | 복제된 데이터 |
| S3 Replication | $20 | $100 | $400 | Cross-Region 전송 비용 |
| **AI 서비스** |
| Bedrock Titan Embed | $10-20 | $50-100 | $200-400 | 임베딩 생성 (10K/50K/200K 청크) |
| Bedrock Claude | $50-100 | $250-500 | $1,000-2,000 | RAG 쿼리 (1K/5K/20K 쿼리) |
| OpenSearch Serverless | $700 | $1,400 | $2,800 | OCU 기반 (2/4/8 OCU) |
| **네트워크** |
| NAT Gateway | $194 | $194 | $194 | 6개 × $32.40/월 |
| VPC Endpoints | $44 | $44 | $44 | 4개 × $10.95/월 |
| Data Transfer | $9 | $45 | $180 | 아웃바운드 전송 |
| **모니터링** |
| CloudWatch Logs | $5 | $15 | $50 | 로그 수집 및 저장 |
| CloudWatch Alarms | $1 | $1 | $1 | 알람 3개 |
| CloudTrail | $2 | $2 | $2 | 감사 로깅 |
| **총계** | **$787-965** | **$1,760-2,305** | **$4,170-5,910** |

### 시나리오 설명

**Baseline (개발/테스트)**
- 문서: 100GB (약 10만 페이지)
- 임베딩: 10,000 청크/월
- RAG 쿼리: 1,000 쿼리/월
- OpenSearch: 2 OCU (최소 구성)
- 사용 패턴: 간헐적 사용

**Medium (소규모 프로덕션)**
- 문서: 500GB (약 50만 페이지)
- 임베딩: 50,000 청크/월
- RAG 쿼리: 5,000 쿼리/월
- OpenSearch: 4 OCU
- 사용 패턴: 일일 사용

**High (대규모 프로덕션)**
- 문서: 2TB (약 200만 페이지)
- 임베딩: 200,000 청크/월
- RAG 쿼리: 20,000 쿼리/월
- OpenSearch: 8 OCU
- 사용 패턴: 24/7 운영

### 비용 최적화 전략

#### 1. S3 비용 절감
```hcl
# Intelligent-Tiering (자동 계층 이동)
- 30일 미접근 → Infrequent Access (68% 절감)
- 90일 미접근 → Archive Access (82% 절감)
- 180일 미접근 → Deep Archive (95% 절감)

# Lifecycle 정책
- 90일 후 Glacier로 이동
- 180일 후 Deep Archive로 이동
- 이전 버전 30일 후 Glacier로 이동
```

#### 2. Lambda 비용 절감
```hcl
# 메모리 최적화
- 1024MB → 512MB (처리 시간이 2배 미만 증가 시)
- 예상 절감: 50%

# 동시 실행 제한
- Reserved Concurrency 설정으로 비용 예측 가능
```

#### 3. OpenSearch 비용 절감
```hcl
# OCU 최적화
- 개발 환경: 2 OCU (최소)
- 프로덕션: 4-8 OCU (워크로드에 따라)
- 자동 스케일링 비활성화 (예측 가능한 비용)
```

#### 4. 네트워크 비용 절감
```hcl
# VPC Endpoint 사용
- 인터넷 게이트웨이 대신 PrivateLink 사용
- 데이터 전송 비용 절감 (약 30%)

# S3 Transfer Acceleration 비활성화
- Cross-Region Replication만 사용
```

### 비용 추정 스크립트

```bash
# Baseline 시나리오
./scripts/cost-estimation.sh baseline

# Medium 시나리오
./scripts/cost-estimation.sh medium

# High 시나리오
./scripts/cost-estimation.sh high

# 커스텀 시나리오
./scripts/cost-estimation.sh custom \
  --storage-gb 1000 \
  --embeddings 100000 \
  --queries 10000 \
  --ocu 6
```

### AWS Budgets 설정

프로젝트에는 자동 예산 알림이 포함되어 있습니다:

```hcl
# 예산 임계값
- 80% 도달 시: 이메일 알림
- 100% 도달 시: 이메일 알림
- 120% 도달 시: 이메일 알림 (초과)

# 알림 수신자
variable "sns_notification_emails" {
  default = ["your-email@example.com"]
}
```

**예산 확인:**
```bash
aws budgets describe-budget \
  --account-id $(aws sts get-caller-identity --query Account --output text) \
  --budget-name bos-ai-dev-monthly-budget
```

## 📚 문서

- [배포 가이드](docs/DEPLOYMENT_GUIDE.md) - 전체 배포 절차
- [운영 가이드](docs/OPERATIONAL_RUNBOOK.md) - 일상 운영 및 문제 해결
- [테스트 가이드](docs/TESTING_GUIDE.md) - 테스트 전략 및 실행 방법

## 🔒 보안

- **암호화**: 모든 데이터는 KMS 고객 관리형 키로 암호화
- **네트워크 격리**: PrivateLink를 통한 AWS 서비스 접근
- **최소 권한**: IAM 정책은 최소 권한 원칙 적용
- **감사**: CloudTrail로 모든 API 호출 로깅

## 🏷️ 주요 기능

### 네트워크 아키텍처
- ✅ **Multi-Region Deployment**: 서울(ap-northeast-2)과 미국(us-east-1) 리전에 걸친 배포
- ✅ **VPC Peering**: 리전 간 프라이빗 네트워크 연결 (10Gbps 대역폭)
- ✅ **No Internet Gateway**: 모든 VPC에서 IGW 없이 NAT Gateway만 사용 (보안 강화)
- ✅ **PrivateLink**: VPC 엔드포인트를 통한 AWS 서비스 접근 (인터넷 미경유)
- ✅ **Multi-AZ**: 각 리전에서 3개 가용 영역 사용 (고가용성)

### 데이터 파이프라인
- ✅ **Cross-Region Replication**: S3 교차 리전 자동 복제 (Seoul → US)
- ✅ **Event-Driven Processing**: S3 이벤트 → Lambda → Bedrock 자동 파이프라인
- ✅ **Intelligent Tiering**: S3 자동 계층 이동 (비용 최적화)
- ✅ **Lifecycle Policies**: 90일 후 Glacier, 180일 후 Deep Archive 이동
- ✅ **Versioning**: 모든 S3 버킷 버전 관리 활성화

### AI/ML 기능
- ✅ **Semantic Search**: OpenSearch Serverless 벡터 DB (HNSW 알고리즘)
- ✅ **Embedding Model**: Amazon Titan Embed Text v1 (1536 차원)
- ✅ **Foundation Model**: Anthropic Claude (RAG 쿼리용)
- ✅ **Semantic Chunking**: 문서 타입별 최적화된 청킹 전략 (300 토큰, 20% 오버랩)
- ✅ **Knowledge Base Sync**: S3 업로드 시 자동 임베딩 및 인덱싱

### 보안
- ✅ **Encryption at Rest**: KMS 고객 관리형 키로 모든 데이터 암호화
- ✅ **Encryption in Transit**: TLS 1.2+ 강제 적용
- ✅ **Least Privilege IAM**: 최소 권한 원칙 적용 (8개 세분화된 정책)
- ✅ **Network Isolation**: Private 서브넷에서만 리소스 실행
- ✅ **Audit Logging**: CloudTrail로 모든 API 호출 로깅
- ✅ **VPC Flow Logs**: 네트워크 트래픽 모니터링
- ✅ **Security Groups**: Stateful 방화벽 규칙
- ✅ **Network ACLs**: Stateless 방화벽 규칙 (추가 보안 계층)

### 모니터링 및 관찰성
- ✅ **CloudWatch Logs**: 5개 로그 그룹 (Lambda, Bedrock, OpenSearch, VPC)
- ✅ **CloudWatch Alarms**: 3개 알람 (Lambda 에러, 지연, 스로틀링)
- ✅ **CloudWatch Dashboard**: 통합 대시보드 (메트릭 시각화)
- ✅ **X-Ray Tracing**: Lambda 분산 추적 활성화
- ✅ **Dead Letter Queue**: Lambda 실패 메시지 수집

### 비용 최적화
- ✅ **S3 Intelligent-Tiering**: 자동 계층 이동 (최대 95% 절감)
- ✅ **S3 Lifecycle Policies**: 오래된 데이터 자동 아카이빙
- ✅ **Lambda Right-Sizing**: 메모리 및 타임아웃 최적화
- ✅ **OpenSearch OCU Control**: 자동 스케일링 비활성화 (예측 가능한 비용)
- ✅ **AWS Budgets**: 예산 초과 시 자동 알림
- ✅ **Cost Allocation Tags**: 모든 리소스 태그 기반 비용 추적

### 운영 효율성
- ✅ **Infrastructure as Code**: 100% Terraform으로 관리
- ✅ **Modular Design**: 재사용 가능한 12개 모듈
- ✅ **Remote State**: S3 + DynamoDB 백엔드 (팀 협업)
- ✅ **State Locking**: DynamoDB를 통한 동시 실행 방지
- ✅ **Property-Based Testing**: 47개 속성 기반 테스트
- ✅ **Policy as Code**: OPA를 통한 자동 정책 검증
- ✅ **CI/CD Ready**: GitHub Actions 통합 가능

### 컴플라이언스
- ✅ **Tagging Strategy**: 모든 리소스 필수 태그 (Project, Environment, ManagedBy)
- ✅ **Multi-Region Trail**: CloudTrail 멀티 리전 활성화
- ✅ **Log File Validation**: CloudTrail 로그 무결성 검증
- ✅ **Encryption Compliance**: 모든 데이터 암호화 강제
- ✅ **Access Logging**: S3 버킷 액세스 로그 활성화

## 🤝 기여

이슈나 풀 리퀘스트를 환영합니다!

## 📄 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.

## 📞 지원

문제가 발생하면 [Issues](../../issues)에 등록해주세요.


## 🔧 운영 가이드

### 일상 운영 작업

#### 문서 업로드 및 처리

1. **서울 S3 버킷에 문서 업로드:**
```bash
aws s3 cp document.pdf s3://bos-ai-documents-seoul/documents/
```

2. **자동 처리 흐름:**
   - S3 Cross-Region Replication → US 버킷으로 복제
   - S3 Event → Lambda 함수 트리거
   - Lambda → Bedrock Knowledge Base 동기화 시작
   - Bedrock → 문서 청킹 및 임베딩 생성
   - OpenSearch → 벡터 인덱스에 저장

3. **처리 상태 확인:**
```bash
# Lambda 로그 확인
aws logs tail /aws/lambda/document-processor \
  --follow \
  --region us-east-1

# Bedrock 동기화 작업 확인
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id $(terraform output -raw knowledge_base_id) \
  --data-source-id $(terraform output -raw data_source_id) \
  --region us-east-1
```

#### Knowledge Base 쿼리

```bash
# Bedrock Agent Runtime API를 통한 쿼리
aws bedrock-agent-runtime retrieve-and-generate \
  --input '{"text":"What is the main topic of the document?"}' \
  --retrieve-and-generate-configuration '{
    "type": "KNOWLEDGE_BASE",
    "knowledgeBaseConfiguration": {
      "knowledgeBaseId": "FNNOP3VBZV",
      "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2"
    }
  }' \
  --region us-east-1
```

#### 모니터링 및 알람

```bash
# CloudWatch 대시보드 확인
aws cloudwatch get-dashboard \
  --dashboard-name bos-ai-dev-dashboard \
  --region us-east-1

# 알람 상태 확인
aws cloudwatch describe-alarms \
  --alarm-name-prefix bos-ai-dev \
  --region us-east-1

# 메트릭 조회
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=document-processor \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region us-east-1
```

### 문제 해결

#### Lambda 함수 실패

**증상:** Lambda 함수가 실패하고 Dead Letter Queue에 메시지가 쌓임

**진단:**
```bash
# DLQ 메시지 확인
aws sqs receive-message \
  --queue-url $(terraform output -raw lambda_dlq_url) \
  --region us-east-1

# Lambda 에러 로그 확인
aws logs filter-log-events \
  --log-group-name /aws/lambda/document-processor \
  --filter-pattern "ERROR" \
  --region us-east-1
```

**해결:**
1. 로그에서 에러 원인 파악
2. VPC 연결 문제인 경우: Security Group 및 NAT Gateway 확인
3. 권한 문제인 경우: IAM 역할 정책 확인
4. 타임아웃 문제인 경우: Lambda 타임아웃 증가 (최대 900초)

#### OpenSearch 쿼리 느림

**증상:** 벡터 검색 응답 시간이 느림 (>5초)

**진단:**
```bash
# OpenSearch 메트릭 확인
aws cloudwatch get-metric-statistics \
  --namespace AWS/AOSS \
  --metric-name SearchLatency \
  --dimensions Name=CollectionId,Value=$(terraform output -raw opensearch_collection_id) \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average \
  --region us-east-1
```

**해결:**
1. OCU 증가 (2 → 4 → 8)
2. 인덱스 최적화 (ef_search 파라미터 조정)
3. 쿼리 최적화 (필터 조건 추가)

#### S3 복제 지연

**증상:** 서울에서 업로드한 파일이 미국 버킷에 나타나지 않음

**진단:**
```bash
# 복제 상태 확인
aws s3api get-bucket-replication \
  --bucket bos-ai-documents-seoul

# 복제 메트릭 확인
aws cloudwatch get-metric-statistics \
  --namespace AWS/S3 \
  --metric-name ReplicationLatency \
  --dimensions Name=SourceBucket,Value=bos-ai-documents-seoul \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

**해결:**
1. 복제 역할 권한 확인
2. KMS 키 정책 확인 (양쪽 리전 모두)
3. 버킷 버전 관리 활성화 확인
4. 일반적으로 15분 이내 복제 완료 (SLA)

### 백업 및 복구

#### Terraform 상태 백업

```bash
# 상태 파일 다운로드
aws s3 cp s3://bos-ai-terraform-state/network-layer/terraform.tfstate \
  ./backups/network-layer-$(date +%Y%m%d).tfstate

aws s3 cp s3://bos-ai-terraform-state/app-layer/bedrock-rag/terraform.tfstate \
  ./backups/app-layer-$(date +%Y%m%d).tfstate

# 상태 파일 복원 (필요 시)
aws s3 cp ./backups/network-layer-20260218.tfstate \
  s3://bos-ai-terraform-state/network-layer/terraform.tfstate
```

#### OpenSearch 인덱스 백업

OpenSearch Serverless는 자동 백업을 제공하지 않으므로 수동 백업이 필요합니다:

```python
# scripts/backup-opensearch-index.py
import boto3
import json
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# OpenSearch 클라이언트 생성
session = boto3.Session()
credentials = session.get_credentials()
awsauth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    'us-east-1',
    'aoss',
    session_token=credentials.token
)

client = OpenSearch(
    hosts=['https://xxx.us-east-1.aoss.amazonaws.com'],
    http_auth=awsauth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)

# 모든 문서 백업
response = client.search(
    index='bedrock-knowledge-base-index',
    body={'query': {'match_all': {}}, 'size': 10000}
)

with open('opensearch-backup.json', 'w') as f:
    json.dump(response['hits']['hits'], f)
```

### 리소스 정리

#### 전체 인프라 삭제

```bash
# 1. App Layer 삭제
cd environments/app-layer/bedrock-rag
terraform destroy

# 2. Network Layer 삭제
cd environments/network-layer
terraform destroy

# 3. Backend 삭제 (선택사항)
cd environments/global/backend
# S3 버킷 비우기
aws s3 rm s3://bos-ai-terraform-state --recursive
terraform destroy
```

**주의사항:**
- S3 버킷에 데이터가 있으면 삭제가 실패합니다
- OpenSearch 컬렉션 삭제는 약 5-10분 소요됩니다
- VPC 삭제 전 모든 ENI가 제거되어야 합니다

#### 특정 리소스만 삭제

```bash
# Lambda 함수만 삭제
terraform destroy -target=module.s3_pipeline.aws_lambda_function.document_processor

# OpenSearch 컬렉션만 삭제
terraform destroy -target=module.bedrock_rag.aws_opensearchserverless_collection.main

# Knowledge Base만 삭제
terraform destroy -target=module.bedrock_rag.aws_bedrockagent_knowledge_base.main
```

자세한 운영 가이드는 [OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md)를 참조하세요.

## 📊 배포된 리소스 요약

### Global (Backend)
- S3 버킷: 1개 (Terraform 상태)
- DynamoDB 테이블: 1개 (상태 잠금)

### Seoul Region (ap-northeast-2)
- VPC: 1개 (10.0.0.0/16)
- 서브넷: 6개 (Public 3개, Private 3개)
- NAT Gateway: 3개
- Route Tables: 4개
- Security Groups: 3개
- VPN Gateway: 1개 (기존 인프라)
- S3 버킷: 1개 (소스)

### US East Region (us-east-1)
- VPC: 1개 (10.1.0.0/16)
- 서브넷: 6개 (Public 3개, Private 3개)
- NAT Gateway: 3개
- Route Tables: 4개
- Security Groups: 3개
- VPC 엔드포인트: 4개
- S3 버킷: 3개 (대상, CloudTrail, CloudTrail 액세스 로그)
- Lambda 함수: 1개
- SQS 큐: 1개 (DLQ)
- OpenSearch Serverless 컬렉션: 1개
- Bedrock Knowledge Base: 1개
- Bedrock Data Source: 1개
- KMS 키: 1개
- IAM 역할: 3개
- IAM 정책: 8개
- CloudWatch 로그 그룹: 5개
- CloudWatch 알람: 3개
- CloudWatch 대시보드: 1개
- CloudTrail: 1개
- AWS Budget: 1개
- SNS 토픽: 2개

### Multi-Region
- VPC Peering 연결: 1개

**총 리소스: 130개 이상**

