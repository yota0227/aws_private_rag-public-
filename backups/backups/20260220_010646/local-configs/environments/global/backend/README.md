# Terraform Backend Infrastructure

이 디렉토리는 Terraform 상태 파일을 저장하고 관리하기 위한 글로벌 백엔드 인프라를 생성합니다.

## 개요

Terraform 백엔드는 다음 리소스로 구성됩니다:

- **S3 Bucket**: Terraform 상태 파일 저장
  - 버전 관리 활성화 (롤백 가능)
  - 서버 측 암호화 (AES256)
  - 퍼블릭 액세스 차단
  - 액세스 로깅 활성화
  
- **DynamoDB Table**: 상태 파일 잠금
  - 동시 수정 방지
  - Pay-per-request 요금제

## 배포 순서

⚠️ **중요**: 이 백엔드 인프라는 다른 모든 Terraform 구성보다 **먼저** 배포되어야 합니다.

### 1단계: 초기 배포 (로컬 상태 사용)

백엔드 인프라를 처음 생성할 때는 로컬 상태를 사용합니다:

```bash
cd environments/global/backend

# 초기화
terraform init

# 배포 계획 확인
terraform plan

# 배포 실행
terraform apply
```

### 2단계: 출력 값 확인

배포 후 생성된 리소스 정보를 확인합니다:

```bash
terraform output
```

출력 예시:
```
state_bucket_id = "bos-ai-terraform-state"
state_bucket_region = "ap-northeast-2"
dynamodb_table_name = "terraform-state-lock"
```

### 3단계: 네트워크 레이어 및 앱 레이어 배포

백엔드가 생성되면 다른 레이어들이 이 백엔드를 사용할 수 있습니다:

```bash
# 네트워크 레이어 배포
cd ../../network-layer
terraform init  # backend.tf에 정의된 S3 백엔드 사용
terraform apply

# 앱 레이어 배포
cd ../app-layer/bedrock-rag
terraform init  # backend.tf에 정의된 S3 백엔드 사용
terraform apply
```

## 변수 설정

### 필수 변수

기본값을 사용하지 않으려면 `terraform.tfvars` 파일을 생성하세요:

```hcl
# terraform.tfvars
region              = "ap-northeast-2"
state_bucket_name   = "bos-ai-terraform-state"
dynamodb_table_name = "terraform-state-lock"

# IAM 사용자/역할 ARN 목록 (상태 파일 접근 권한)
authorized_principals = [
  "arn:aws:iam::123456789012:user/terraform-admin",
  "arn:aws:iam::123456789012:role/TerraformExecutionRole"
]
```

### 변수 설명

- `region`: 백엔드 리소스를 생성할 AWS 리전 (기본값: ap-northeast-2)
- `state_bucket_name`: S3 버킷 이름 (기본값: bos-ai-terraform-state)
- `dynamodb_table_name`: DynamoDB 테이블 이름 (기본값: terraform-state-lock)
- `authorized_principals`: 상태 버킷에 접근할 수 있는 IAM 주체 ARN 목록

## 보안 기능

### S3 버킷 보안

1. **버전 관리**: 상태 파일의 모든 변경 사항 추적 및 롤백 가능
2. **암호화**: AES256 서버 측 암호화로 저장 시 암호화
3. **퍼블릭 액세스 차단**: 모든 퍼블릭 액세스 차단
4. **액세스 로깅**: 모든 버킷 접근 기록
5. **버킷 정책**: 
   - HTTPS 전송 강제 (HTTP 요청 거부)
   - 승인된 IAM 주체만 접근 허용

### DynamoDB 테이블

- **상태 잠금**: 동시 Terraform 실행 방지
- **Pay-per-request**: 사용량 기반 요금으로 비용 최적화

## 상태 파일 구조

백엔드가 생성되면 다음과 같은 구조로 상태 파일이 저장됩니다:

```
s3://bos-ai-terraform-state/
├── network-layer/
│   └── terraform.tfstate
└── app-layer/
    └── bedrock-rag/
        └── terraform.tfstate
```

## 문제 해결

### 버킷 이름 충돌

S3 버킷 이름은 전역적으로 고유해야 합니다. 버킷 이름 충돌 오류가 발생하면:

```hcl
# terraform.tfvars
state_bucket_name = "bos-ai-terraform-state-<고유한-접미사>"
```

### 상태 잠금 오류

다른 Terraform 프로세스가 실행 중이거나 비정상 종료된 경우:

```bash
# 잠금 ID 확인
terraform force-unlock <LOCK_ID>
```

⚠️ **주의**: 다른 프로세스가 실제로 실행 중이지 않은지 확인 후 사용하세요.

## 비용 예상

### 월별 예상 비용 (최소 사용량 기준)

- **S3 스토리지**: $0.10 - $0.50 (상태 파일 크기에 따라)
- **S3 요청**: $0.01 - $0.05 (Terraform 실행 빈도에 따라)
- **DynamoDB**: $0.01 - $0.10 (상태 잠금 요청 수에 따라)

**총 예상 비용**: $0.12 - $0.65/월

## 유지보수

### 상태 파일 백업

S3 버전 관리가 활성화되어 있어 자동으로 백업됩니다. 특정 버전으로 복원하려면:

```bash
# 버전 목록 확인
aws s3api list-object-versions \
  --bucket bos-ai-terraform-state \
  --prefix network-layer/terraform.tfstate

# 특정 버전 복원
aws s3api get-object \
  --bucket bos-ai-terraform-state \
  --key network-layer/terraform.tfstate \
  --version-id <VERSION_ID> \
  terraform.tfstate.backup
```

### 로그 확인

액세스 로그는 별도의 로그 버킷에 저장됩니다:

```bash
aws s3 ls s3://bos-ai-terraform-state-logs/state-access-logs/
```

## 참고 자료

- [Terraform S3 Backend Documentation](https://developer.hashicorp.com/terraform/language/settings/backends/s3)
- [AWS S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)
- [DynamoDB State Locking](https://developer.hashicorp.com/terraform/language/settings/backends/s3#dynamodb-state-locking)
