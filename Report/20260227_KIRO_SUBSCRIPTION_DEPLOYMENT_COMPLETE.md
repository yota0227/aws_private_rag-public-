# Kiro 구독 배포 완료 보고서

작성일: 2026-02-27

## 프로젝트 개요

Kiro IDE의 구독 서비스를 AWS 인프라에 배포하는 프로젝트가 완료되었습니다. 사용자 프롬프트 메타데이터 저장, 이벤트 처리, 모니터링 등 전체 파이프라인이 구성되었습니다.

## 배포 완료 항목

### Phase 1: 기본 인프라 (✅ 완료)

#### S3 Bucket
- **메인 버킷**: `bos-ai-kiro-logs`
- **로그 버킷**: `bos-ai-kiro-logs-logs`
- **리전**: us-east-1 (Virginia)
- **암호화**: KMS (aws:kms)
- **버전 관리**: 활성화
- **공개 접근**: 차단

#### KMS Key
- **이름**: `kiro-prompts-key-prod`
- **자동 회전**: 활성화
- **삭제 대기**: 10일

#### CloudWatch Log Group
- **이름**: `/aws/s3/kiro-prompts-prod`
- **보관 기간**: 90일

### Phase 2: IAM 및 보안 (✅ 완료)

#### IAM Roles (3개)
1. **App Role** (`kiro-app-role`)
   - S3 읽기/쓰기 권한
   - KMS 암호화/복호화 권한
   - CloudWatch Logs 쓰기 권한

2. **Lambda Role** (`kiro-lambda-role`)
   - S3 접근 권한
   - KMS 권한
   - CloudWatch Logs 쓰기 권한
   - Secrets Manager 읽기 권한

3. **EventBridge Role** (`kiro-eventbridge-role`)
   - Lambda 호출 권한
   - CloudWatch Logs 쓰기 권한
   - SNS 발행 권한

#### Secrets Manager (3개)
1. **API Key** (`kiro-api-key`)
   - 외부 API 인증용

2. **Database Credentials** (`kiro-db-credentials`)
   - 데이터베이스 접근용

3. **S3 Configuration** (`kiro-s3-config`)
   - S3 버킷 설정 정보

### Phase 3: 이벤트 처리 (✅ 완료)

#### EventBridge
- **Event Bus**: `kiro-events`
- **Rules** (3개):
  1. **Prompt Received**: 프롬프트 수신 이벤트 처리
  2. **Prompt Error**: 오류 이벤트 처리
  3. **All Events**: 모든 이벤트 로깅

#### Lambda Functions (2개)
1. **Prompt Processor** (`kiro-prompt-processor`)
   - 사용자 프롬프트 처리
   - S3에 저장
   - 메타데이터 추출

2. **Metadata Analyzer** (`kiro-metadata-analyzer`)
   - 메타데이터 분석
   - 통계 생성
   - 인사이트 도출

### Phase 4: 모니터링 및 알림 (✅ 완료)

#### SNS Topic
- **이름**: `kiro-errors`
- **용도**: 오류 알림

#### CloudWatch Alarms (2개)
1. **Lambda Errors**: Lambda 함수 오류 감지
2. **Lambda Duration**: Lambda 실행 시간 모니터링

## 배포된 리소스 요약

| 리소스 유형 | 이름 | 상태 | 리전 |
|-----------|------|------|------|
| S3 Bucket | bos-ai-kiro-logs | Active | us-east-1 |
| S3 Bucket | bos-ai-kiro-logs-logs | Active | us-east-1 |
| KMS Key | kiro-prompts-key-prod | Active | us-east-1 |
| CloudWatch Log Group | /aws/s3/kiro-prompts-prod | Active | us-east-1 |
| IAM Role | kiro-app-role | Active | Global |
| IAM Role | kiro-lambda-role | Active | Global |
| IAM Role | kiro-eventbridge-role | Active | Global |
| Secrets Manager | kiro-api-key | Active | us-east-1 |
| Secrets Manager | kiro-db-credentials | Active | us-east-1 |
| Secrets Manager | kiro-s3-config | Active | us-east-1 |
| EventBridge Bus | kiro-events | Active | us-east-1 |
| EventBridge Rule | kiro-prompt-received | Active | us-east-1 |
| EventBridge Rule | kiro-prompt-error | Active | us-east-1 |
| EventBridge Rule | kiro-all-events | Active | us-east-1 |
| Lambda Function | kiro-prompt-processor | Active | us-east-1 |
| Lambda Function | kiro-metadata-analyzer | Active | us-east-1 |
| SNS Topic | kiro-errors | Active | us-east-1 |
| CloudWatch Alarm | kiro-lambda-errors | Active | us-east-1 |
| CloudWatch Alarm | kiro-lambda-duration | Active | us-east-1 |

**총 리소스 수**: 19개

## 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────┐
│                    Kiro IDE (Client)                         │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Subscription Management UI                           │  │
│  │  ├─ User Invitation Panel                             │  │
│  │  ├─ Team Management                                   │  │
│  │  ├─ Usage Monitoring                                  │  │
│  │  └─ Billing Information                               │  │
│  └───────────────────────────────────────────────────────┘  │
│           │                                                   │
│           └─ Kiro Backend API                                │
│              ├─ Authentication                               │
│              ├─ User Management                              │
│              └─ Subscription Management                      │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    AWS Infrastructure                        │
│                   (us-east-1 / Virginia)                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Data Storage Layer                                  │   │
│  │  ├─ S3: bos-ai-kiro-logs (Prompts & Metadata)       │   │
│  │  ├─ S3: bos-ai-kiro-logs-logs (Access Logs)         │   │
│  │  └─ KMS: kiro-prompts-key-prod (Encryption)         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Secrets & Configuration Layer                       │   │
│  │  ├─ Secrets Manager: API Keys                        │   │
│  │  ├─ Secrets Manager: DB Credentials                 │   │
│  │  └─ Secrets Manager: S3 Config                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Event Processing Layer                              │   │
│  │  ├─ EventBridge Bus: kiro-events                     │   │
│  │  ├─ Rule: Prompt Received → Lambda                   │   │
│  │  ├─ Rule: Prompt Error → SNS                         │   │
│  │  └─ Rule: All Events → CloudWatch Logs              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Compute Layer                                       │   │
│  │  ├─ Lambda: Prompt Processor                         │   │
│  │  └─ Lambda: Metadata Analyzer                        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Monitoring & Alerting Layer                         │   │
│  │  ├─ CloudWatch Logs: /aws/s3/kiro-prompts-prod      │   │
│  │  ├─ CloudWatch Alarms: Lambda Errors                │   │
│  │  ├─ CloudWatch Alarms: Lambda Duration              │   │
│  │  └─ SNS Topic: kiro-errors                           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Security & Access Control Layer                     │   │
│  │  ├─ IAM Role: kiro-app-role                          │   │
│  │  ├─ IAM Role: kiro-lambda-role                       │   │
│  │  └─ IAM Role: kiro-eventbridge-role                  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## 데이터 흐름

### 사용자 프롬프트 처리 흐름

```
1. User Submits Prompt
   │
   ├─ Kiro IDE
   │  └─ Validate & Prepare
   │
   ▼
2. Send to Backend API
   │
   ├─ Kiro Backend
   │  ├─ Authenticate User
   │  ├─ Check Subscription
   │  └─ Publish Event
   │
   ▼
3. EventBridge Receives Event
   │
   ├─ Event Bus: kiro-events
   │  ├─ Rule: Prompt Received
   │  │  └─ Trigger: Lambda Prompt Processor
   │  ├─ Rule: All Events
   │  │  └─ Trigger: CloudWatch Logs
   │  └─ Rule: Prompt Error (if error)
   │     └─ Trigger: SNS Topic
   │
   ▼
4. Lambda Processing
   │
   ├─ Prompt Processor
   │  ├─ Extract Metadata
   │  ├─ Encrypt Data
   │  └─ Store in S3
   │
   ├─ Metadata Analyzer
   │  ├─ Analyze Patterns
   │  ├─ Generate Statistics
   │  └─ Update Metrics
   │
   ▼
5. Data Storage
   │
   ├─ S3: bos-ai-kiro-logs
   │  └─ prompts/2026/02/27/user-123/prompt-xxx.json
   │
   ├─ CloudWatch Logs
   │  └─ /aws/s3/kiro-prompts-prod
   │
   ▼
6. Monitoring & Alerts
   │
   ├─ CloudWatch Metrics
   │  ├─ Prompt Count
   │  ├─ Processing Time
   │  └─ Error Rate
   │
   ├─ CloudWatch Alarms
   │  ├─ Lambda Errors
   │  └─ Lambda Duration
   │
   ▼
7. Notifications (if needed)
   │
   └─ SNS Topic: kiro-errors
      └─ Send Alert Email
```

## 사용자 초대 프로세스

### 초대 흐름

```
1. Owner Opens Subscription Panel
   │
   ├─ Kiro IDE
   │  └─ Subscription Management UI
   │
   ▼
2. Click "Invite Users"
   │
   ├─ Input Email & Role
   │  ├─ Email: user@example.com
   │  ├─ Role: Editor
   │  └─ Message: (optional)
   │
   ▼
3. Confirm & Send
   │
   ├─ Kiro Backend
   │  ├─ Validate Email
   │  ├─ Check Quota
   │  ├─ Generate Token
   │  └─ Store Invitation
   │
   ▼
4. Send Invitation Email
   │
   ├─ Email Service (SES)
   │  └─ Send to: user@example.com
   │
   ▼
5. User Receives Email
   │
   ├─ Email Content
   │  ├─ Invitation Details
   │  ├─ Accept Link
   │  └─ Expiration: 7 days
   │
   ▼
6. User Accepts Invitation
   │
   ├─ Click Email Link
   │  └─ Redirect to Kiro IDE
   │
   ├─ Or Accept in Kiro IDE
   │  └─ Subscription Panel
   │
   ▼
7. Invitation Accepted
   │
   ├─ Kiro Backend
   │  ├─ Validate Token
   │  ├─ Add User to Team
   │  ├─ Set Role
   │  └─ Log Event
   │
   ▼
8. User Added to Subscription
   │
   ├─ User Can Now
   │  ├─ Access Shared Projects
   │  ├─ View Team Resources
   │  └─ Collaborate
   │
   ▼
9. Notifications
   │
   ├─ Owner Notified
   │  └─ "User accepted invitation"
   │
   ├─ New User Notified
   │  └─ "Welcome to subscription"
   │
   └─ Event Logged
      └─ Audit Trail
```

## 배포 파일 구조

```
environments/kiro-subscription/
├── main.tf                    # S3, KMS, CloudWatch 리소스
├── iam.tf                     # IAM Roles & Policies
├── secrets.tf                 # Secrets Manager
├── eventbridge.tf             # EventBridge Bus & Rules
├── lambda.tf                  # Lambda Functions
├── variables.tf               # 변수 정의
├── outputs.tf                 # 출력값
├── backend.tf                 # Terraform 백엔드
├── terraform.tfvars           # 변수 값
├── terraform.tfvars.example   # 변수 예제
└── README.md                  # 상세 문서
```

## 배포 명령어

### 초기 배포

```bash
cd environments/kiro-subscription

# 1. 변수 파일 준비
cp terraform.tfvars.example terraform.tfvars

# 2. Terraform 초기화
terraform init

# 3. 배포 계획 확인
terraform plan

# 4. 배포 실행
terraform apply
```

### 배포 후 검증

```bash
# 1. 출력값 확인
terraform output

# 2. S3 버킷 확인
aws s3 ls s3://bos-ai-kiro-logs --region us-east-1

# 3. Lambda 함수 확인
aws lambda list-functions --region us-east-1 --query 'Functions[?contains(FunctionName, `kiro`)]'

# 4. EventBridge 규칙 확인
aws events list-rules --event-bus-name kiro-events --region us-east-1
```

### 리소스 정리

```bash
# 모든 리소스 삭제
terraform destroy
```

## 비용 추정

### 월별 예상 비용

| 서비스 | 항목 | 비용 |
|--------|------|------|
| S3 | 스토리지 (1GB) | $0.023 |
| S3 | 요청 (10,000) | $0.04 |
| KMS | 키 관리 | $1.00 |
| KMS | 요청 (10,000) | $0.30 |
| Lambda | 호출 (1,000,000) | $0.20 |
| Lambda | 실행 시간 (100,000 GB-s) | $1.67 |
| EventBridge | 이벤트 (1,000,000) | $0.35 |
| CloudWatch | 로그 저장 (100MB) | $0.05 |
| SNS | 발행 (1,000) | $0.50 |
| **합계** | | **~$4.14** |

### 비용 최적화 팁

1. **S3 Intelligent-Tiering**: 자동 계층화로 저장 비용 절감
2. **Lambda 최적화**: 실행 시간 단축으로 비용 감소
3. **로그 보관 기간 단축**: 90일 → 30일 (약 60% 절감)
4. **EventBridge 필터링**: 불필요한 이벤트 필터링

## 모니터링 및 관리

### CloudWatch 대시보드

```bash
# 대시보드 생성
aws cloudwatch put-dashboard \
  --dashboard-name kiro-subscription \
  --dashboard-body file://dashboard.json
```

### 알람 설정

```bash
# Lambda 오류 알람
aws cloudwatch put-metric-alarm \
  --alarm-name kiro-lambda-errors \
  --alarm-description "Alert on Lambda errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold

# Lambda 실행 시간 알람
aws cloudwatch put-metric-alarm \
  --alarm-name kiro-lambda-duration \
  --alarm-description "Alert on high Lambda duration" \
  --metric-name Duration \
  --namespace AWS/Lambda \
  --statistic Average \
  --period 300 \
  --threshold 5000 \
  --comparison-operator GreaterThanThreshold
```

## 보안 체크리스트

- ✅ S3 버킷 공개 접근 차단
- ✅ KMS 암호화 활성화
- ✅ 버전 관리 활성화
- ✅ 접근 로깅 활성화
- ✅ IAM 역할 최소 권한 원칙 적용
- ✅ Secrets Manager 사용
- ✅ 감사 로그 활성화
- ✅ CloudWatch 모니터링 설정

## 다음 단계

### 즉시 실행 (1-2주)
1. ✅ 인프라 배포 완료
2. ✅ 사용자 초대 방식 결정
3. ⏳ 팀 멤버 초대 및 구독 활성화
4. ⏳ 초기 사용자 테스트

### 단기 (1개월)
1. ⏳ 사용 현황 모니터링
2. ⏳ 성능 최적화
3. ⏳ 비용 최적화
4. ⏳ 보안 감사

### 중기 (3개월)
1. ⏳ 고급 분석 기능 추가
2. ⏳ 자동화 워크플로우 구성
3. ⏳ 통합 기능 확장
4. ⏳ 규정 준수 검증

## 참고 자료

### 문서
- `20260226_KIRO_SUBSCRIPTION_DEPLOYMENT.md` - S3 배포 가이드
- `20260227_KIRO_SUBSCRIPTION_USER_INVITATION_GUIDE.md` - 사용자 초대 가이드
- `environments/kiro-subscription/README.md` - Terraform 상세 문서

### AWS 공식 문서
- [AWS S3](https://docs.aws.amazon.com/s3/)
- [AWS KMS](https://docs.aws.amazon.com/kms/)
- [AWS Lambda](https://docs.aws.amazon.com/lambda/)
- [AWS EventBridge](https://docs.aws.amazon.com/eventbridge/)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)

### Terraform 문서
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform Best Practices](https://www.terraform.io/docs/cloud/guides/recommended-practices.html)

## 문제 해결

### 배포 실패

**증상**: `terraform apply` 실패

**해결**:
1. AWS 자격증명 확인: `aws sts get-caller-identity`
2. 권한 확인: IAM 정책 검토
3. 리전 확인: `us-east-1` 설정 확인
4. 로그 확인: `terraform apply -var="log_level=DEBUG"`

### 리소스 접근 오류

**증상**: S3 또는 Lambda 접근 실패

**해결**:
1. IAM 역할 확인
2. KMS 키 정책 확인
3. 보안 그룹 확인
4. 네트워크 연결 확인

### 비용 초과

**증상**: 예상보다 높은 비용

**해결**:
1. CloudWatch 메트릭 확인
2. Lambda 실행 시간 최적화
3. S3 요청 수 감소
4. 로그 보관 기간 단축

## 연락처

- **기술 지원**: [support@kiro.dev](mailto:support@kiro.dev)
- **청구 문의**: [billing@kiro.dev](mailto:billing@kiro.dev)
- **보안 문제**: [security@kiro.dev](mailto:security@kiro.dev)

---

**배포 완료일**: 2026-02-27
**배포 상태**: ✅ 완료
**다음 검토**: 2026-03-06

