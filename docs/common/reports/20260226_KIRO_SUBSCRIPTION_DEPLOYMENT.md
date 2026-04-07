# Kiro Subscription S3 Bucket 배포 가이드

작성일: 2026-02-26

## 개요

Kiro 구독 서비스를 위한 사용자 프롬프트 메타데이터 저장소를 AWS S3에 배포합니다.

## 배포 구조

```
environments/kiro-subscription/
├── main.tf                    # 메인 리소스 정의
├── variables.tf               # 변수 정의
├── outputs.tf                 # 출력값 정의
├── backend.tf                 # Terraform 백엔드 설정
├── terraform.tfvars.example   # 변수 예제
└── README.md                  # 상세 문서
```

## 배포 리소스

### 1. S3 Bucket (메인)
- **이름**: `kiro-user-prompts-metadata-prod`
- **리전**: us-east-1 (Virginia)
- **용도**: 사용자 프롬프트 및 메타데이터 저장
- **암호화**: KMS (aws:kms)
- **버전 관리**: 활성화
- **공개 접근**: 차단

### 2. S3 Bucket (로그)
- **이름**: `kiro-user-prompts-metadata-logs`
- **리전**: us-east-1 (Virginia)
- **용도**: 메인 bucket의 접근 로그 저장
- **보관 기간**: 90일 (자동 삭제)

### 3. KMS Key
- **이름**: `kiro-prompts-key-prod`
- **용도**: S3 bucket 암호화
- **자동 회전**: 활성화
- **삭제 대기 기간**: 10일

### 4. CloudWatch Log Group
- **이름**: `/aws/s3/kiro-prompts-prod`
- **보관 기간**: 90일

## 배포 단계

### Step 1: 변수 파일 준비

```bash
cd environments/kiro-subscription
cp terraform.tfvars.example terraform.tfvars
```

### Step 2: 변수 파일 수정 (필요시)

```bash
# terraform.tfvars 편집
cat terraform.tfvars
```

**기본값**:
```hcl
aws_region = "us-east-1"
environment = "prod"
bucket_name = "kiro-user-prompts-metadata-prod"
log_retention_days = 90
enable_versioning = true
enable_mfa_delete = false
```

### Step 3: Terraform 초기화

```bash
terraform init
```

**출력 예**:
```
Initializing the backend...
Successfully configured the backend "s3"!

Initializing provider plugins...
- Reusing previous version of hashicorp/aws from the dependency lock file
- Using previously-installed hashicorp/aws v5.x.x

Terraform has been successfully initialized!
```

### Step 4: 배포 계획 확인

```bash
terraform plan
```

**확인 사항**:
- S3 bucket 생성
- KMS key 생성
- 로그 bucket 생성
- CloudWatch log group 생성
- 정책 및 설정 적용

### Step 5: 배포 실행

```bash
terraform apply
```

**확인 메시지**:
```
Do you want to perform these actions?
  Terraform will perform the following actions:
  + aws_s3_bucket.kiro_prompts
  + aws_s3_bucket.kiro_prompts_logs
  + aws_kms_key.kiro_prompts
  + aws_kms_alias.kiro_prompts
  + aws_cloudwatch_log_group.kiro_prompts
  ...

Enter a value: yes
```

### Step 6: 출력값 확인

```bash
terraform output
```

**출력 예**:
```
bucket_arn = "arn:aws:s3:::kiro-user-prompts-metadata-prod"
bucket_name = "kiro-user-prompts-metadata-prod"
bucket_region = "us-east-1"
kms_key_arn = "arn:aws:kms:us-east-1:533335672315:key/..."
kms_key_id = "..."
logs_bucket_arn = "arn:aws:s3:::kiro-user-prompts-metadata-logs"
logs_bucket_name = "kiro-user-prompts-metadata-logs"
```

## 배포 후 검증

### 1. S3 Bucket 확인

```bash
# Bucket 존재 확인
aws s3 ls s3://kiro-user-prompts-metadata-prod --region us-east-1

# Bucket 정책 확인
aws s3api get-bucket-policy --bucket kiro-user-prompts-metadata-prod --region us-east-1

# 암호화 설정 확인
aws s3api get-bucket-encryption --bucket kiro-user-prompts-metadata-prod --region us-east-1

# 버전 관리 확인
aws s3api get-bucket-versioning --bucket kiro-user-prompts-metadata-prod --region us-east-1
```

### 2. KMS Key 확인

```bash
# KMS Key 정보 확인
aws kms describe-key --key-id alias/kiro-prompts-prod --region us-east-1

# KMS Key 정책 확인
aws kms get-key-policy --key-id alias/kiro-prompts-prod --policy-name default --region us-east-1
```

### 3. 로깅 확인

```bash
# CloudWatch Log Group 확인
aws logs describe-log-groups --log-group-name-prefix /aws/s3/kiro-prompts --region us-east-1

# S3 로깅 설정 확인
aws s3api get-bucket-logging --bucket kiro-user-prompts-metadata-prod --region us-east-1
```

### 4. 테스트 업로드

```bash
# 테스트 파일 생성
cat > test-prompt.json << 'EOF'
{
  "prompt_id": "test-001",
  "user_id": "test-user",
  "timestamp": "2026-02-26T10:30:00Z",
  "prompt_text": "This is a test prompt",
  "metadata": {
    "session_id": "test-session",
    "model": "claude-3-sonnet"
  }
}
EOF

# S3에 업로드
aws s3 cp test-prompt.json s3://kiro-user-prompts-metadata-prod/prompts/2026/02/26/test-prompt.json \
  --region us-east-1 \
  --sse aws:kms \
  --sse-kms-key-id alias/kiro-prompts-prod

# 업로드 확인
aws s3 ls s3://kiro-user-prompts-metadata-prod/prompts/2026/02/26/ --region us-east-1

# 파일 다운로드 및 확인
aws s3 cp s3://kiro-user-prompts-metadata-prod/prompts/2026/02/26/test-prompt.json - --region us-east-1 | jq .
```

## 사용 예제

### Python에서 프롬프트 저장

```python
import boto3
import json
from datetime import datetime
from uuid import uuid4

# S3 클라이언트 생성
s3_client = boto3.client('s3', region_name='us-east-1')

# 프롬프트 메타데이터
prompt_data = {
    "prompt_id": str(uuid4()),
    "user_id": "user-123",
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "prompt_text": "How do I optimize my Terraform code?",
    "metadata": {
        "session_id": "session-456",
        "model": "claude-3-sonnet",
        "temperature": 0.7,
        "max_tokens": 2048,
        "tags": ["terraform", "optimization"],
        "source": "kiro-ide"
    },
    "response": {
        "response_id": str(uuid4()),
        "tokens_used": 1234,
        "execution_time_ms": 2500
    }
}

# S3에 저장
bucket_name = "kiro-user-prompts-metadata-prod"
key = f"prompts/{datetime.utcnow().strftime('%Y/%m/%d')}/user-123/prompt-{prompt_data['prompt_id']}.json"

s3_client.put_object(
    Bucket=bucket_name,
    Key=key,
    Body=json.dumps(prompt_data),
    ContentType='application/json',
    ServerSideEncryption='aws:kms',
    SSEKMSKeyId='alias/kiro-prompts-prod'
)

print(f"Prompt saved to s3://{bucket_name}/{key}")
```

### AWS CLI에서 프롬프트 조회

```bash
# 특정 사용자의 프롬프트 목록
aws s3 ls s3://kiro-user-prompts-metadata-prod/prompts/2026/02/26/user-123/ \
  --region us-east-1

# 특정 프롬프트 조회
aws s3 cp s3://kiro-user-prompts-metadata-prod/prompts/2026/02/26/user-123/prompt-xxx.json - \
  --region us-east-1 | jq .

# 모든 프롬프트 다운로드
aws s3 sync s3://kiro-user-prompts-metadata-prod/prompts/ ./local-prompts/ \
  --region us-east-1
```

## 비용 추정

### 월별 비용 (예상)

| 항목 | 비용 |
|------|------|
| S3 Storage (1GB) | $0.023 |
| KMS Key | $1.00 |
| KMS Requests (10,000) | $0.30 |
| CloudWatch Logs (100MB) | $0.05 |
| **합계** | **~$1.38** |

### 비용 최적화

1. **로그 보관 기간 단축**: 90일 → 30일 (약 60% 절감)
2. **S3 Intelligent-Tiering**: 자동 계층화로 저장 비용 절감
3. **Lifecycle Policy**: 오래된 데이터 자동 삭제

## 문제 해결

### 문제 1: Bucket 이름 충돌

**증상**: `BucketAlreadyExists` 오류

**해결**:
```bash
# 고유한 이름으로 변경
terraform apply -var="bucket_name=kiro-prompts-unique-$(date +%s)"
```

### 문제 2: KMS 권한 오류

**증상**: `AccessDenied` 오류

**해결**:
```bash
# IAM 사용자/역할에 KMS 권한 추가
aws iam attach-user-policy \
  --user-name your-user \
  --policy-arn arn:aws:iam::aws:policy/AWSKeyManagementServicePowerUser
```

### 문제 3: S3 업로드 실패

**증상**: `SignatureDoesNotMatch` 오류

**해결**:
```bash
# AWS 자격증명 확인
aws sts get-caller-identity

# 버킷 정책 확인
aws s3api get-bucket-policy --bucket kiro-user-prompts-metadata-prod
```

## 정리 (Cleanup)

모든 리소스 삭제:

```bash
cd environments/kiro-subscription
terraform destroy
```

**확인 메시지**:
```
Do you really want to destroy all resources?
  Terraform will destroy all your managed infrastructure.

Enter a value: yes
```

## 다음 단계

1. ✅ S3 Bucket 배포 완료
2. ⏳ IAM 정책 설정 (애플리케이션 접근)
3. ⏳ CloudWatch 알람 설정
4. ⏳ 데이터 파이프라인 구성
5. ⏳ 모니터링 및 로깅 설정

## 참고 자료

- [Terraform AWS S3 Bucket](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket)
- [AWS S3 Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/BestPractices.html)
- [AWS KMS Best Practices](https://docs.aws.amazon.com/kms/latest/developerguide/best-practices.html)
