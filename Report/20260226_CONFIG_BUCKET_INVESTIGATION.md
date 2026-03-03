# config-bucket-533335672315 조사 결과

작성일: 2026-02-26

## 조사 결과

### 1. 코드베이스에서의 사용 현황

**검색 결과**: `config-bucket-533335672315`는 현재 코드베이스에서 **사용되지 않음**

- Terraform 파일에서 검색: ❌ 없음
- 문서에서 검색: ❌ 없음
- 스크립트에서 검색: ❌ 없음

### 1.1 실제 Bucket 내용 확인

**Bucket 경로**: `s3://config-bucket-533335672315`

**내용**: AWS Config 설정 변경 이력 (ConfigHistory)

```
AWSLogs/533335672315/Config/
├── ConfigWritabilityCheckFile (0 bytes)
└── us-east-1/2026/2/25-26/ConfigHistory/
    ├── AppConfig::DeploymentStrategy
    ├── Athena::WorkGroup
    ├── Bedrock::KnowledgeBase
    ├── Bedrock::DataSource
    ├── CloudTrail::Trail
    ├── CloudWatch::Alarm
    ├── EC2::VPC
    ├── EC2::Subnet
    ├── EC2::SecurityGroup
    ├── EC2::RouteTable
    ├── EC2::VPCPeeringConnection
    ├── EC2::VPCEndpoint
    ├── KMS::Key
    ├── Lambda::Function
    ├── OpenSearchServerless::Collection
    ├── Route53::HostedZone
    ├── Route53Resolver::ResolverRule
    ├── S3::Bucket
    ├── SNS::Topic
    ├── SQS::Queue
    └── ... (기타 AWS 리소스)
```

**파일 크기**: 대부분 400-2000 bytes (압축된 JSON.gz 형식)

**최신 업데이트**: 2026-02-26 (어제)

### 2. 실제 사용 중인 S3 Bucket

#### Terraform State Backend
```
Bucket Name: bos-ai-terraform-state
Account ID: 533335672315
Region: ap-northeast-2
```

**사용 위치**:
- `environments/network-layer/backend.tf`
- `environments/app-layer/bedrock-rag/backend.tf`
- `environments/global/backend/variables.tf`

**용도**: Terraform State 저장소

#### CloudTrail Logs
```
Bucket Name: bos-ai-cloudtrail-logs (변수)
Account ID: 533335672315
```

**사용 위치**:
- `modules/security/cloudtrail/main.tf`

**용도**: CloudTrail 감사 로그 저장

#### Document Storage
```
Bucket Names:
- bos-ai-documents-seoul (Seoul region)
- bos-ai-documents-us (US region)
Account ID: 533335672315
```

**사용 위치**:
- `environments/app-layer/bedrock-rag/variables.tf`

**용도**: Bedrock Knowledge Base 문서 저장

### 3. config-bucket-533335672315의 정체

#### ✅ 확인됨: AWS Config 저장소

**용도**: AWS Config 설정 변경 이력 저장

**내용**:
- ConfigHistory: 모든 AWS 리소스의 설정 변경 이력
- 리전: us-east-1 (US 리전의 리소스 변경 이력)
- 기간: 2026-02-25 ~ 2026-02-26 (최근 2일)

**추적 중인 리소스**:
- EC2 (VPC, Subnet, SecurityGroup, RouteTable, VPCPeeringConnection, VPCEndpoint)
- Bedrock (KnowledgeBase, DataSource)
- OpenSearch Serverless (Collection)
- Lambda (Function)
- KMS (Key)
- Route53 (HostedZone, ResolverRule)
- CloudTrail (Trail)
- CloudWatch (Alarm)
- S3 (Bucket)
- SNS, SQS, IAM 등

**상태**: ✅ 정상 작동 중 (최신 업데이트: 2026-02-26)

### 4. 현재 프로젝트의 S3 Bucket 정리

#### 배포된 Bucket
1. **bos-ai-terraform-state**
   - 용도: Terraform State 저장
   - 리전: ap-northeast-2
   - 상태: ✅ 배포됨

2. **bos-ai-cloudtrail-logs** (예정)
   - 용도: CloudTrail 감사 로그
   - 리전: ap-northeast-2
   - 상태: ⏳ 배포 예정

3. **bos-ai-documents-seoul** (예정)
   - 용도: 문서 저장 (Seoul)
   - 리전: ap-northeast-2
   - 상태: ⏳ 배포 예정

4. **bos-ai-documents-us** (예정)
   - 용도: 문서 저장 (US)
   - 리전: us-east-1
   - 상태: ⏳ 배포 예정

### 5. 권장사항

#### 현황
- ✅ AWS Config가 정상 작동 중
- ✅ 모든 AWS 리소스의 설정 변경 이력이 기록되고 있음
- ✅ 감사(Audit) 및 규정 준수(Compliance) 추적 가능

#### 유지 필요
- AWS Config는 보안 및 규정 준수를 위해 필수
- 설정 변경 이력 추적은 문제 발생 시 원인 파악에 도움
- 비용: 월 약 $2-5 (저장 용량에 따라 변동)

#### 추가 고려사항
1. **CloudTrail과의 차이**:
   - CloudTrail: API 호출 기록 (누가, 언제, 무엇을 했는가)
   - AWS Config: 리소스 설정 상태 변경 (설정이 어떻게 변했는가)

2. **모니터링**:
   - AWS Config Rules를 통해 규정 준수 자동 확인 가능
   - 비준수 리소스 자동 감지 및 알림

3. **비용 최적화**:
   - 필요한 리소스 타입만 추적하도록 설정 가능
   - 보관 기간 설정으로 저장 비용 조절 가능

## 현재 프로젝트의 S3 Bucket 구조

```
AWS Account: 533335672315

├── bos-ai-terraform-state
│   ├── 용도: Terraform State 저장
│   ├── 리전: ap-northeast-2
│   ├── 경로:
│   │   ├── network-layer/terraform.tfstate
│   │   └── app-layer/bedrock-rag/terraform.tfstate
│   └── 상태: ✅ 배포됨
│
├── bos-ai-cloudtrail-logs
│   ├── 용도: CloudTrail 감사 로그
│   ├── 리전: ap-northeast-2
│   └── 상태: ⏳ 배포 예정
│
├── bos-ai-documents-seoul
│   ├── 용도: 문서 저장 (Seoul)
│   ├── 리전: ap-northeast-2
│   └── 상태: ⏳ 배포 예정
│
├── bos-ai-documents-us
│   ├── 용도: 문서 저장 (US)
│   ├── 리전: us-east-1
│   └── 상태: ⏳ 배포 예정
│
└── config-bucket-533335672315 (?)
    ├── 용도: 불명확
    ├── 리전: 불명확
    └── 상태: ❓ 미사용 또는 레거시
```

## 다음 단계

1. ✅ 코드베이스 검색 완료
2. ✅ AWS Console에서 bucket 확인 완료
3. ✅ Bucket 내용 분석 완료
4. ⏳ AWS Config 설정 확인 (선택사항)
5. ⏳ AWS Config Rules 설정 (선택사항)

## 참고

- Terraform State Backend: `environments/network-layer/backend.tf`
- CloudTrail 설정: `modules/security/cloudtrail/main.tf`
- 문서 저장소: `environments/app-layer/bedrock-rag/variables.tf`
