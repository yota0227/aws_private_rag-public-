# 현재 IAM Role 및 정책 문서

## 문서 정보

- **작성일**: 2026-02-20
- **작성자**: Kiro AI
- **목적**: BOS-AI VPC 통합 마이그레이션 전 현재 IAM 권한 설정 기록
- **관련 스펙**: `.kiro/specs/bos-ai-vpc-consolidation/`

## 개요

이 문서는 BOS-AI VPC 통합 마이그레이션 프로젝트의 일환으로 현재 IAM Role 및 정책을 문서화합니다. 마이그레이션 전 권한 설정을 정확히 기록하여 변경 사항 추적 및 보안 검증에 활용합니다.

---

## 1. IAM Role 개요

### 1.1 현재 정의된 IAM Role 목록

| Role 이름 | 용도 | 서비스 | 상태 | 위치 |
|----------|------|--------|------|------|
| `{project_name}-lambda-processor-role-{environment}` | Lambda 문서 처리 함수 | Lambda | 정의됨 | `modules/security/iam/lambda-role.tf` |
| `{project_name}-bedrock-kb-role-{environment}` | Bedrock Knowledge Base | Bedrock | 정의됨 | `modules/security/iam/bedrock-kb-role.tf` |
| `{project_name}-{environment}-vpc-flow-logs-role` | VPC Flow Logs | VPC | 정의됨 | `modules/security/iam/vpc-flow-logs-role.tf` |
| `{project_name}-s3-replication-role-{environment}` | S3 교차 리전 복제 | S3 | 조건부 | `modules/ai-workload/s3-pipeline/s3.tf` |
| `BOS-AI-Engineer-Role` | 엔지니어 관리자 권한 | IAM User | 정의됨 | `environments/global/iam/main.tf` |

**참고**: 
- `{project_name}`: 기본값 `bos-ai-rag` (변수로 설정 가능)
- `{environment}`: `dev`, `staging`, `prod` 등 환경별 구분
- S3 Replication Role은 `enable_replication=true`이고 `replication_role_arn`이 비어있을 때만 생성됨

---

## 2. Lambda Document Processor Role

### 2.1 기본 정보

| 항목 | 값 |
|------|-----|
| **Role 이름** | `{project_name}-lambda-processor-role-{environment}` |
| **ARN** | `arn:aws:iam::{account_id}:role/{project_name}-lambda-processor-role-{environment}` |
| **설명** | IAM role for Lambda document processor with least-privilege access |
| **신뢰 관계 (Trust Policy)** | Lambda 서비스 (`lambda.amazonaws.com`) |
| **위치** | `modules/security/iam/lambda-role.tf` |


### 2.2 신뢰 관계 (Assume Role Policy)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### 2.3 연결된 정책 (Attached Policies)

#### 2.3.1 S3 Access Policy

**정책 이름**: `{project_name}-lambda-s3-policy-{environment}`

**권한**:
- `s3:GetObject` - S3 객체 읽기
- `s3:GetObjectVersion` - S3 객체 버전 읽기
- `s3:ListBucket` - S3 버킷 목록 조회

**리소스**:
- `{s3_data_source_bucket_arn}` - 데이터 소스 버킷
- `{s3_data_source_bucket_arn}/*` - 버킷 내 모든 객체

**용도**: Lambda 함수가 S3 버킷에서 문서를 읽어 처리

---

#### 2.3.2 CloudWatch Logs Policy

**정책 이름**: `{project_name}-lambda-logs-policy-{environment}`

**권한**:
- `logs:CreateLogGroup` - 로그 그룹 생성
- `logs:CreateLogStream` - 로그 스트림 생성
- `logs:PutLogEvents` - 로그 이벤트 기록

**리소스**:
- `arn:aws:logs:*:{account_id}:log-group:/aws/lambda/{project_name}-*`

**용도**: Lambda 함수 실행 로그를 CloudWatch Logs에 기록


---

#### 2.3.3 Bedrock Access Policy

**정책 이름**: `{project_name}-lambda-bedrock-policy-{environment}`

**권한**:
- `bedrock:StartIngestionJob` - Bedrock Knowledge Base 인제스트 작업 시작
- `bedrock:GetIngestionJob` - 인제스트 작업 상태 조회
- `bedrock:ListIngestionJobs` - 인제스트 작업 목록 조회

**리소스**:
- `arn:aws:bedrock:*:{account_id}:knowledge-base/*`

**용도**: Lambda 함수가 Bedrock Knowledge Base 동기화 작업을 트리거

---

#### 2.3.4 KMS Access Policy

**정책 이름**: `{project_name}-lambda-kms-policy-{environment}`

**권한**:
- `kms:Decrypt` - KMS 키를 사용한 복호화
- `kms:GenerateDataKey` - 데이터 키 생성

**리소스**:
- `{kms_key_arn}` - 프로젝트 KMS 키

**용도**: 암호화된 S3 객체 및 환경 변수 복호화

---

#### 2.3.5 VPC Access Policy

**정책 이름**: `{project_name}-lambda-vpc-policy-{environment}`

**권한**:
- `ec2:CreateNetworkInterface` - ENI 생성
- `ec2:DescribeNetworkInterfaces` - ENI 조회
- `ec2:DeleteNetworkInterface` - ENI 삭제
- `ec2:AssignPrivateIpAddresses` - 프라이빗 IP 할당
- `ec2:UnassignPrivateIpAddresses` - 프라이빗 IP 해제

**리소스**:
- `*` (모든 리소스)

**용도**: Lambda 함수가 VPC 내부에서 실행되기 위한 ENI 관리

**참고**: VPC Lambda는 ENI를 통해 VPC 리소스에 접근하므로 이 권한이 필수입니다.


---

#### 2.3.6 SQS Access Policy

**정책 이름**: `{project_name}-lambda-sqs-policy-{environment}`

**권한**:
- `sqs:SendMessage` - SQS 메시지 전송
- `sqs:GetQueueAttributes` - 큐 속성 조회
- `sqs:GetQueueUrl` - 큐 URL 조회

**리소스**:
- `arn:aws:sqs:*:{account_id}:*-dlq` (Dead Letter Queue)

**용도**: Lambda 함수 실행 실패 시 DLQ로 메시지 전송

---

### 2.4 보안 고려사항

- ✅ **최소 권한 원칙**: 각 정책이 필요한 권한만 부여
- ✅ **리소스 제한**: 가능한 경우 특정 리소스 ARN으로 제한
- ⚠️ **VPC 권한**: ENI 관리 권한은 `*` 리소스 필요 (AWS 제약)
- ✅ **신뢰 관계**: Lambda 서비스만 Role 사용 가능

---

## 3. Bedrock Knowledge Base Role

### 3.1 기본 정보

| 항목 | 값 |
|------|-----|
| **Role 이름** | `{project_name}-bedrock-kb-role-{environment}` |
| **ARN** | `arn:aws:iam::{account_id}:role/{project_name}-bedrock-kb-role-{environment}` |
| **설명** | IAM role for Bedrock Knowledge Base with least-privilege access |
| **신뢰 관계 (Trust Policy)** | Bedrock 서비스 (`bedrock.amazonaws.com`) |
| **위치** | `modules/security/iam/bedrock-kb-role.tf` |

### 3.2 신뢰 관계 (Assume Role Policy)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "bedrock.amazonaws.com"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "{account_id}"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:bedrock:*:{account_id}:knowledge-base/*"
        }
      }
    }
  ]
}
```

**보안 강화**:
- `StringEquals` 조건으로 동일 계정만 허용
- `ArnLike` 조건으로 Knowledge Base 리소스만 허용


### 3.3 연결된 정책 (Attached Policies)

#### 3.3.1 S3 Access Policy

**정책 이름**: `{project_name}-bedrock-kb-s3-policy-{environment}`

**권한**:
- `s3:GetObject` - S3 객체 읽기
- `s3:ListBucket` - S3 버킷 목록 조회

**리소스**:
- `{s3_data_source_bucket_arn}` - 데이터 소스 버킷
- `{s3_data_source_bucket_arn}/*` - 버킷 내 모든 객체

**용도**: Bedrock Knowledge Base가 S3에서 문서를 읽어 벡터화

---

#### 3.3.2 OpenSearch Serverless Access Policy

**정책 이름**: `{project_name}-bedrock-kb-opensearch-policy-{environment}`

**권한**:
- `aoss:APIAccessAll` - OpenSearch Serverless 전체 API 접근

**리소스**:
- `{opensearch_collection_arn}` - OpenSearch Serverless 컬렉션

**용도**: Bedrock Knowledge Base가 벡터 임베딩을 OpenSearch에 저장

---

#### 3.3.3 KMS Access Policy

**정책 이름**: `{project_name}-bedrock-kb-kms-policy-{environment}`

**권한**:
- `kms:Decrypt` - KMS 키를 사용한 복호화
- `kms:GenerateDataKey` - 데이터 키 생성

**리소스**:
- `{kms_key_arn}` - 프로젝트 KMS 키

**용도**: 암호화된 S3 객체 및 OpenSearch 데이터 암호화/복호화

---

#### 3.3.4 Bedrock Model Access Policy

**정책 이름**: `{project_name}-bedrock-kb-model-policy-{environment}`

**권한**:
- `bedrock:InvokeModel` - Bedrock 모델 호출

**리소스** (기본값):
- `arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v1` - Titan 임베딩 모델
- `arn:aws:bedrock:*::foundation-model/anthropic.claude-v2` - Claude v2 모델

**용도**: Bedrock Knowledge Base가 임베딩 및 생성 모델 호출


### 3.4 보안 고려사항

- ✅ **최소 권한 원칙**: 각 정책이 필요한 권한만 부여
- ✅ **리소스 제한**: 모든 정책이 특정 리소스 ARN으로 제한
- ✅ **신뢰 관계 조건**: SourceAccount 및 SourceArn 조건으로 보안 강화
- ✅ **모델 제한**: 특정 Foundation Model만 호출 가능

---

## 4. VPC Flow Logs Role

### 4.1 기본 정보

| 항목 | 값 |
|------|-----|
| **Role 이름** | `{project_name}-{environment}-vpc-flow-logs-role` |
| **ARN** | `arn:aws:iam::{account_id}:role/{project_name}-{environment}-vpc-flow-logs-role` |
| **설명** | IAM role for VPC Flow Logs to write to CloudWatch Logs |
| **신뢰 관계 (Trust Policy)** | VPC Flow Logs 서비스 (`vpc-flow-logs.amazonaws.com`) |
| **위치** | `modules/security/iam/vpc-flow-logs-role.tf` |

### 4.2 신뢰 관계 (Assume Role Policy)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "vpc-flow-logs.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### 4.3 인라인 정책 (Inline Policy)

**정책 이름**: `{project_name}-{environment}-vpc-flow-logs-policy`

**권한**:
- `logs:CreateLogGroup` - 로그 그룹 생성
- `logs:CreateLogStream` - 로그 스트림 생성
- `logs:PutLogEvents` - 로그 이벤트 기록
- `logs:DescribeLogGroups` - 로그 그룹 조회
- `logs:DescribeLogStreams` - 로그 스트림 조회

**리소스**:
- `*` (모든 CloudWatch Logs 리소스)

**용도**: VPC Flow Logs가 네트워크 트래픽 로그를 CloudWatch에 기록

### 4.4 보안 고려사항

- ✅ **신뢰 관계**: VPC Flow Logs 서비스만 Role 사용 가능
- ⚠️ **리소스 범위**: CloudWatch Logs 권한은 `*` 필요 (AWS 제약)
- ✅ **읽기 전용 조회**: DescribeLogGroups/Streams는 읽기 전용


---

## 5. S3 Replication Role (조건부)

### 5.1 기본 정보

| 항목 | 값 |
|------|-----|
| **Role 이름** | `{project_name}-s3-replication-role-{environment}` |
| **ARN** | `arn:aws:iam::{account_id}:role/{project_name}-s3-replication-role-{environment}` |
| **설명** | IAM role for S3 cross-region replication |
| **신뢰 관계 (Trust Policy)** | S3 서비스 (`s3.amazonaws.com`) |
| **위치** | `modules/ai-workload/s3-pipeline/s3.tf` |
| **생성 조건** | `enable_replication=true` AND `replication_role_arn=""` |

**참고**: 이 Role은 S3 교차 리전 복제가 활성화되고 기존 Role ARN이 제공되지 않은 경우에만 생성됩니다.

### 5.2 신뢰 관계 (Assume Role Policy)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "s3.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### 5.3 인라인 정책 (Inline Policy)

**정책 이름**: `{project_name}-s3-replication-policy-{environment}`

**권한**:

**소스 버킷 권한**:
- `s3:GetReplicationConfiguration` - 복제 설정 조회
- `s3:ListBucket` - 버킷 목록 조회

**소스 객체 권한**:
- `s3:GetObjectVersionForReplication` - 복제용 객체 버전 읽기
- `s3:GetObjectVersionAcl` - 객체 버전 ACL 읽기
- `s3:GetObjectVersionTagging` - 객체 버전 태그 읽기

**대상 버킷 권한**:
- `s3:ReplicateObject` - 객체 복제
- `s3:ReplicateDelete` - 삭제 마커 복제
- `s3:ReplicateTags` - 태그 복제

**KMS 권한**:
- `kms:Decrypt` - 소스 객체 복호화

**리소스**:
- 소스 버킷: `{source_bucket_arn}`, `{source_bucket_arn}/*`
- 대상 버킷: `{destination_bucket_arn}/*`
- KMS 키: `{kms_key_arn}`

**용도**: S3 버킷 간 교차 리전 복제 (예: 서울 → 버지니아)


### 5.4 보안 고려사항

- ✅ **최소 권한 원칙**: 복제에 필요한 권한만 부여
- ✅ **리소스 제한**: 특정 소스/대상 버킷으로 제한
- ✅ **KMS 통합**: 암호화된 객체 복제 지원
- ✅ **조건부 생성**: 필요한 경우에만 생성되어 리소스 낭비 방지

---

## 6. Engineer Role (관리자 권한)

### 6.1 기본 정보

| 항목 | 값 |
|------|-----|
| **Role 이름** | `BOS-AI-Engineer-Role` |
| **ARN** | `arn:aws:iam::533335672315:role/BOS-AI-Engineer-Role` |
| **설명** | 엔지니어용 관리자 권한 Role |
| **신뢰 관계 (Trust Policy)** | IAM User (`seungil.woo`) |
| **위치** | `environments/global/iam/main.tf` |

### 6.2 신뢰 관계 (Assume Role Policy)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::533335672315:user/seungil.woo"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

**참고**: 
- 특정 IAM User (`seungil.woo`)만 이 Role을 사용할 수 있습니다.
- 보안 Condition이 제거되어 원격 근무(WFH) 환경에서도 접속 가능합니다.

### 6.3 연결된 정책 (Attached Policies)

#### 6.3.1 AdministratorAccess (AWS 관리형 정책)

**정책 ARN**: `arn:aws:iam::aws:policy/AdministratorAccess`

**권한**: AWS 계정의 모든 리소스에 대한 전체 권한

**용도**: 인프라 관리 및 개발 작업

### 6.4 보안 고려사항

- ⚠️ **관리자 권한**: 전체 권한을 가지므로 신중하게 사용 필요
- ✅ **특정 사용자 제한**: 특정 IAM User만 사용 가능
- ⚠️ **Condition 제거**: IP 제한 등 추가 보안 조건 없음
- 🔒 **권장사항**: MFA(Multi-Factor Authentication) 활성화 권장


---

## 7. IAM 정책 요약

### 7.1 정책 유형별 분류

| 정책 유형 | 개수 | 정책 이름 |
|----------|------|----------|
| **Lambda 관련** | 6개 | S3, CloudWatch Logs, Bedrock, KMS, VPC, SQS |
| **Bedrock KB 관련** | 4개 | S3, OpenSearch, KMS, Model |
| **VPC Flow Logs** | 1개 | CloudWatch Logs |
| **S3 Replication** | 1개 | S3 Replication |
| **관리자 권한** | 1개 | AdministratorAccess |

**총 정책 수**: 13개 (관리형 정책 1개 포함)

### 7.2 서비스별 권한 매트릭스

| 서비스 | Lambda Role | Bedrock KB Role | VPC Flow Logs | S3 Replication | Engineer Role |
|--------|-------------|-----------------|---------------|----------------|---------------|
| **S3** | ✅ Read | ✅ Read | ❌ | ✅ Read/Write | ✅ Full |
| **CloudWatch Logs** | ✅ Write | ❌ | ✅ Write | ❌ | ✅ Full |
| **Bedrock** | ✅ Ingestion | ✅ Model Invoke | ❌ | ❌ | ✅ Full |
| **OpenSearch** | ❌ | ✅ Full | ❌ | ❌ | ✅ Full |
| **KMS** | ✅ Decrypt | ✅ Decrypt/Encrypt | ❌ | ✅ Decrypt | ✅ Full |
| **VPC/EC2** | ✅ ENI Mgmt | ❌ | ❌ | ❌ | ✅ Full |
| **SQS** | ✅ Send | ❌ | ❌ | ❌ | ✅ Full |

### 7.3 리소스 제한 수준

| Role | 리소스 제한 수준 | 설명 |
|------|----------------|------|
| Lambda Processor | 🟢 높음 | 대부분 특정 ARN으로 제한 (VPC 제외) |
| Bedrock KB | 🟢 매우 높음 | 모든 정책이 특정 ARN으로 제한 |
| VPC Flow Logs | 🟡 중간 | CloudWatch Logs는 `*` 필요 |
| S3 Replication | 🟢 높음 | 특정 버킷으로 제한 |
| Engineer Role | 🔴 없음 | 전체 권한 (`*`) |

---

## 8. 마이그레이션 영향 분석

### 8.1 변경 필요 사항

#### 8.1.1 Lambda Processor Role

**현재 상태**: 정의됨 (미배포)

**마이그레이션 시 변경**:
- ✅ Role 이름 유지 (변수 기반)
- ✅ 정책 내용 유지
- 🔄 **VPC 설정 추가**: 서울 통합 VPC의 서브넷 및 Security Group 연결
- 🔄 **환경 변수 업데이트**: OpenSearch Serverless 엔드포인트, S3 버킷 등

**필요 작업**:
1. Lambda 함수 배포 시 이 Role 연결
2. VPC 서브넷 및 Security Group 지정
3. 환경 변수 설정


#### 8.1.2 Bedrock KB Role

**현재 상태**: 정의됨 (미배포)

**마이그레이션 시 변경**:
- ✅ Role 이름 유지 (변수 기반)
- ✅ 정책 내용 유지
- 🔄 **OpenSearch Collection ARN 업데이트**: 서울 통합 VPC의 OpenSearch Serverless 컬렉션
- 🔄 **S3 버킷 ARN 업데이트**: 버지니아 및 서울 데이터 소스 버킷

**필요 작업**:
1. OpenSearch Serverless 컬렉션 생성 후 ARN 업데이트
2. Bedrock Knowledge Base 생성 시 이 Role 연결
3. 데이터 소스 S3 버킷 ARN 확인 및 업데이트

---

#### 8.1.3 VPC Flow Logs Role

**현재 상태**: 정의됨 (배포 여부 미확인)

**마이그레이션 시 변경**:
- ✅ Role 이름 유지 (변수 기반)
- ✅ 정책 내용 유지
- ✅ **변경 없음**: VPC Flow Logs는 기존 VPC에서 계속 사용

**필요 작업**:
1. 서울 통합 VPC에 VPC Flow Logs 활성화 확인
2. 이 Role이 연결되어 있는지 확인

---

#### 8.1.4 S3 Replication Role

**현재 상태**: 조건부 생성 (배포 여부 미확인)

**마이그레이션 시 변경**:
- ✅ Role 이름 유지 (변수 기반)
- ✅ 정책 내용 유지
- 🔄 **소스/대상 버킷 확인**: 서울 ↔ 버지니아 복제 설정 확인

**필요 작업**:
1. S3 복제가 필요한지 확인
2. 필요한 경우 소스/대상 버킷 ARN 설정
3. KMS 키 ARN 설정

---

#### 8.1.5 Engineer Role

**현재 상태**: 배포됨

**마이그레이션 시 변경**:
- ✅ **변경 없음**: 관리자 권한 Role은 마이그레이션 영향 없음

**필요 작업**:
- 없음

---

### 8.2 신규 생성 필요 Role

마이그레이션 과정에서 추가로 필요할 수 있는 Role:

#### 8.2.1 OpenSearch Serverless Service Role (선택사항)

**용도**: OpenSearch Serverless가 VPC 엔드포인트를 생성하기 위한 Role

**권한**:
- `ec2:CreateNetworkInterface`
- `ec2:DescribeNetworkInterfaces`
- `ec2:DeleteNetworkInterface`

**참고**: OpenSearch Serverless는 일반적으로 서비스 연결 Role을 자동 생성하므로 명시적 생성이 불필요할 수 있습니다.


---

## 9. 보안 검증 체크리스트

### 9.1 최소 권한 원칙 (Least Privilege)

- [x] Lambda Processor Role: 필요한 권한만 부여
- [x] Bedrock KB Role: 필요한 권한만 부여
- [x] VPC Flow Logs Role: 필요한 권한만 부여
- [x] S3 Replication Role: 필요한 권한만 부여
- [ ] Engineer Role: ⚠️ 관리자 권한 (전체 권한)

**권장사항**: Engineer Role은 개발/테스트 환경에서만 사용하고, 프로덕션 환경에서는 더 제한적인 권한 사용 권장

### 9.2 신뢰 관계 (Trust Policy) 검증

- [x] Lambda Processor: Lambda 서비스만 허용
- [x] Bedrock KB: Bedrock 서비스만 허용 + SourceAccount/SourceArn 조건
- [x] VPC Flow Logs: VPC Flow Logs 서비스만 허용
- [x] S3 Replication: S3 서비스만 허용
- [x] Engineer Role: 특정 IAM User만 허용

### 9.3 리소스 제한 검증

- [x] Lambda S3 Policy: 특정 버킷으로 제한
- [x] Lambda Bedrock Policy: Knowledge Base 리소스로 제한
- [x] Lambda CloudWatch Logs: 특정 로그 그룹 패턴으로 제한
- [ ] Lambda VPC Policy: ⚠️ `*` 리소스 (AWS 제약)
- [x] Bedrock KB S3 Policy: 특정 버킷으로 제한
- [x] Bedrock KB OpenSearch Policy: 특정 컬렉션으로 제한
- [x] Bedrock KB Model Policy: 특정 모델로 제한
- [ ] VPC Flow Logs Policy: ⚠️ `*` 리소스 (AWS 제약)

### 9.4 암호화 및 KMS

- [x] Lambda KMS Policy: 특정 KMS 키로 제한
- [x] Bedrock KB KMS Policy: 특정 KMS 키로 제한
- [x] S3 Replication KMS: 특정 KMS 키로 제한

### 9.5 교차 계정 접근 방지

- [x] Bedrock KB: SourceAccount 조건으로 동일 계정만 허용
- [x] 모든 Role: 동일 계정 내에서만 사용

---

## 10. 모니터링 및 감사

### 10.1 CloudTrail 로깅

**권장사항**:
- ✅ 모든 IAM Role의 AssumeRole 이벤트 로깅
- ✅ 정책 변경 이벤트 로깅
- ✅ 권한 사용 이벤트 로깅

### 10.2 IAM Access Analyzer

**권장사항**:
- ✅ IAM Access Analyzer 활성화
- ✅ 외부 접근 가능한 리소스 검토
- ✅ 미사용 권한 식별

### 10.3 정기 검토

**권장사항**:
- 월간: IAM Role 사용 현황 검토
- 분기: 권한 최소화 검토
- 반기: 보안 정책 업데이트


---

## 11. Terraform 변수 설정

### 11.1 필수 변수

IAM Role 생성 시 필요한 Terraform 변수:

```hcl
# modules/security/iam/variables.tf

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "bos-ai-rag"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "s3_data_source_bucket_arn" {
  description = "ARN of S3 bucket containing documents"
  type        = string
  # 예: "arn:aws:s3:::bos-ai-documents-us"
}

variable "opensearch_collection_arn" {
  description = "ARN of OpenSearch Serverless collection"
  type        = string
  # 예: "arn:aws:aoss:ap-northeast-2:533335672315:collection/xxxxx"
}

variable "kms_key_arn" {
  description = "ARN of KMS key for encryption/decryption"
  type        = string
  # 예: "arn:aws:kms:ap-northeast-2:533335672315:key/xxxxx"
}

variable "bedrock_model_arns" {
  description = "List of Bedrock model ARNs"
  type        = list(string)
  default = [
    "arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v1",
    "arn:aws:bedrock:*::foundation-model/anthropic.claude-v2"
  ]
}

variable "tags" {
  description = "Common tags for all IAM resources"
  type        = map(string)
  default = {
    Project     = "BOS-AI-RAG"
    Environment = "prod"
    ManagedBy   = "Terraform"
    Layer       = "Security"
  }
}
```

### 11.2 환경별 설정 예시

#### 개발 환경 (dev)

```hcl
# environments/app-layer/dev/terraform.tfvars

project_name = "bos-ai-rag"
environment  = "dev"

s3_data_source_bucket_arn = "arn:aws:s3:::bos-ai-documents-dev"
opensearch_collection_arn = "arn:aws:aoss:ap-northeast-2:533335672315:collection/dev-xxxxx"
kms_key_arn              = "arn:aws:kms:ap-northeast-2:533335672315:key/dev-xxxxx"

tags = {
  Project     = "BOS-AI-RAG"
  Environment = "dev"
  ManagedBy   = "Terraform"
  Layer       = "Security"
}
```

#### 프로덕션 환경 (prod)

```hcl
# environments/app-layer/prod/terraform.tfvars

project_name = "bos-ai-rag"
environment  = "prod"

s3_data_source_bucket_arn = "arn:aws:s3:::bos-ai-documents-us"
opensearch_collection_arn = "arn:aws:aoss:ap-northeast-2:533335672315:collection/prod-xxxxx"
kms_key_arn              = "arn:aws:kms:ap-northeast-2:533335672315:key/prod-xxxxx"

tags = {
  Project     = "BOS-AI-RAG"
  Environment = "prod"
  ManagedBy   = "Terraform"
  Layer       = "Security"
}
```


---

## 12. AWS CLI 명령어

### 12.1 IAM Role 확인

```bash
# 계정의 모든 IAM Role 목록 조회
aws iam list-roles --query 'Roles[?contains(RoleName, `bos-ai`)].{Name:RoleName,ARN:Arn}' --output table

# 특정 Role 상세 정보 조회
aws iam get-role --role-name bos-ai-rag-lambda-processor-role-prod

# Role의 신뢰 관계 (Assume Role Policy) 조회
aws iam get-role --role-name bos-ai-rag-lambda-processor-role-prod --query 'Role.AssumeRolePolicyDocument'
```

### 12.2 연결된 정책 확인

```bash
# Role에 연결된 관리형 정책 목록
aws iam list-attached-role-policies --role-name bos-ai-rag-lambda-processor-role-prod

# Role의 인라인 정책 목록
aws iam list-role-policies --role-name bos-ai-rag-lambda-processor-role-prod

# 특정 정책 내용 조회
aws iam get-policy --policy-arn arn:aws:iam::533335672315:policy/bos-ai-rag-lambda-s3-policy-prod
aws iam get-policy-version --policy-arn arn:aws:iam::533335672315:policy/bos-ai-rag-lambda-s3-policy-prod --version-id v1
```

### 12.3 Role 사용 현황 확인

```bash
# Role이 마지막으로 사용된 시간 확인
aws iam get-role --role-name bos-ai-rag-lambda-processor-role-prod --query 'Role.RoleLastUsed'

# CloudTrail에서 AssumeRole 이벤트 조회 (최근 1시간)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --query 'Events[?contains(CloudTrailEvent, `bos-ai-rag-lambda-processor-role-prod`)].{Time:EventTime,User:Username,Event:EventName}'
```

### 12.4 정책 시뮬레이션

```bash
# Lambda Role이 S3 GetObject 권한을 가지는지 시뮬레이션
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::533335672315:role/bos-ai-rag-lambda-processor-role-prod \
  --action-names s3:GetObject \
  --resource-arns arn:aws:s3:::bos-ai-documents-us/test.pdf

# Bedrock KB Role이 OpenSearch 접근 권한을 가지는지 시뮬레이션
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::533335672315:role/bos-ai-rag-bedrock-kb-role-prod \
  --action-names aoss:APIAccessAll \
  --resource-arns arn:aws:aoss:ap-northeast-2:533335672315:collection/xxxxx
```

---

## 13. 문제 해결 (Troubleshooting)

### 13.1 Lambda 함수가 S3에 접근할 수 없는 경우

**증상**: `AccessDenied` 오류

**확인 사항**:
1. Lambda 함수에 올바른 IAM Role이 연결되어 있는지 확인
2. S3 버킷 ARN이 정책에 정확히 명시되어 있는지 확인
3. S3 버킷 정책에서 Lambda Role을 차단하지 않는지 확인
4. KMS 키 정책에서 Lambda Role의 Decrypt 권한이 있는지 확인

**해결 방법**:
```bash
# Lambda 함수의 Role 확인
aws lambda get-function-configuration --function-name lambda-document-processor-seoul-prod --query 'Role'

# Role의 S3 정책 확인
aws iam get-policy-version --policy-arn arn:aws:iam::533335672315:policy/bos-ai-rag-lambda-s3-policy-prod --version-id v1
```


### 13.2 Bedrock Knowledge Base가 OpenSearch에 접근할 수 없는 경우

**증상**: `AccessDeniedException` 또는 `UnauthorizedException`

**확인 사항**:
1. Bedrock KB에 올바른 IAM Role이 연결되어 있는지 확인
2. OpenSearch Serverless Data Access Policy에 Role이 추가되어 있는지 확인
3. OpenSearch Serverless Network Policy에 VPC 엔드포인트가 추가되어 있는지 확인
4. IAM 정책의 OpenSearch Collection ARN이 정확한지 확인

**해결 방법**:
```bash
# Bedrock KB의 Role 확인
aws bedrock-agent get-knowledge-base --knowledge-base-id xxxxx --query 'knowledgeBase.roleArn'

# OpenSearch Serverless Data Access Policy 확인
aws opensearchserverless get-access-policy --name bos-ai-rag-data-access-policy --type data

# OpenSearch Serverless Network Policy 확인
aws opensearchserverless get-access-policy --name bos-ai-rag-network-policy --type network
```

### 13.3 VPC Lambda가 ENI를 생성할 수 없는 경우

**증상**: `ENILimitReachedException` 또는 `EC2ThrottledException`

**확인 사항**:
1. Lambda Role에 VPC 권한이 있는지 확인
2. 서브넷에 충분한 IP 주소가 있는지 확인
3. Security Group이 올바르게 설정되어 있는지 확인
4. Lambda 함수의 동시 실행 수가 너무 높지 않은지 확인

**해결 방법**:
```bash
# Lambda Role의 VPC 정책 확인
aws iam get-policy-version --policy-arn arn:aws:iam::533335672315:policy/bos-ai-rag-lambda-vpc-policy-prod --version-id v1

# 서브넷의 사용 가능한 IP 주소 확인
aws ec2 describe-subnets --subnet-ids subnet-xxxxx --query 'Subnets[0].AvailableIpAddressCount'

# Lambda ENI 확인
aws ec2 describe-network-interfaces --filters "Name=description,Values=AWS Lambda VPC ENI*" --query 'NetworkInterfaces[*].{ID:NetworkInterfaceId,Status:Status,Subnet:SubnetId}'
```

### 13.4 Engineer Role을 Assume할 수 없는 경우

**증상**: `AccessDenied` when calling AssumeRole

**확인 사항**:
1. IAM User가 신뢰 관계에 명시된 사용자인지 확인
2. IAM User에게 `sts:AssumeRole` 권한이 있는지 확인
3. MFA가 필요한 경우 MFA 토큰을 제공했는지 확인

**해결 방법**:
```bash
# 현재 IAM User 확인
aws sts get-caller-identity

# Role의 신뢰 관계 확인
aws iam get-role --role-name BOS-AI-Engineer-Role --query 'Role.AssumeRolePolicyDocument'

# Role Assume 시도
aws sts assume-role --role-arn arn:aws:iam::533335672315:role/BOS-AI-Engineer-Role --role-session-name test-session
```

---

## 14. 참고 자료

### 14.1 관련 문서

- 요구사항 문서: `.kiro/specs/bos-ai-vpc-consolidation/requirements.md`
- 설계 문서: `.kiro/specs/bos-ai-vpc-consolidation/design.md`
- 작업 목록: `.kiro/specs/bos-ai-vpc-consolidation/tasks.md`
- VPC 설정 문서: `docs/current-vpc-configuration.md`
- Security Group 문서: `docs/current-security-groups.md`

### 14.2 AWS 공식 문서

- [IAM Roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html)
- [IAM Policies](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html)
- [Lambda Execution Role](https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html)
- [Bedrock Knowledge Base IAM](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-permissions.html)
- [VPC Flow Logs IAM](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-cwl.html)

### 14.3 보안 모범 사례

- [AWS Security Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [Least Privilege Principle](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#grant-least-privilege)
- [IAM Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html)

---

## 15. 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|----------|--------|
| 2026-02-20 | 1.0 | 초기 문서 작성 | Kiro AI |

---

**문서 끝**
