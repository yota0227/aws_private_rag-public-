# BOS-AI Private RAG 운영자 온보딩 가이드

> 신규 운영자가 BOS-AI Private RAG 시스템을 독립적으로 운영할 수 있도록 안내합니다.
> 이 문서를 순서대로 따라하면 시스템 이해 → 접근 설정 → 일상 운영이 가능합니다.

---

## 1단계: 시스템 이해 (1일차)

### 필수 읽기 자료

| 순서 | 문서 | 소요 시간 | 핵심 내용 |
|------|------|----------|----------|
| 1 | [시스템 개요](../../BOS-AI-Private-RAG-System-Overview.md) | 30분 | 전체 아키텍처, 데이터 흐름, 보안 정책 |
| 2 | [네트워크 아키텍처](../3_private-rag-api/deep-dive-network-architecture.md) | 20분 | VPC, TGW, VPN, VPC Peering 구조 |
| 3 | [컴포넌트 상세](../3_private-rag-api/deep-dive-component-details.md) | 20분 | Lambda, Bedrock, OpenSearch 등 |
| 4 | [보안 정책](../3_private-rag-api/deep-dive-security-policy.md) | 15분 | Air-Gapped 환경, 접근 제어 |

### 핵심 개념 체크리스트

- [ ] RAG 시스템이 왜 서울과 버지니아 두 리전을 사용하는지 설명할 수 있다
- [ ] 온프레미스에서 AWS까지의 네트워크 경로를 설명할 수 있다 (VPN → TGW → VPC)
- [ ] 문서 업로드부터 AI 검색까지의 데이터 흐름을 설명할 수 있다
- [ ] 이 시스템이 인터넷에 노출되지 않는 이유를 설명할 수 있다

---

## 2단계: 접근 환경 설정 (1일차)

### AWS Console 접근

1. IAM 사용자 계정 발급 요청 (IT팀)
2. MFA 설정 완료
3. VPN 연결 상태에서 AWS Console 접속 확인

### AWS CLI 설정

```bash
aws configure --profile mgmt
# Region: ap-northeast-2
# Output: json

aws sts get-caller-identity --profile mgmt
```

### 주요 리소스 ID

| 리소스 | ID | 콘솔 위치 |
|--------|-----|----------|
| Knowledge Base | FNNOP3VBZV | Bedrock > Knowledge bases (us-east-1) |
| OpenSearch Collection | bos-ai-vectors | OpenSearch Serverless (us-east-1) |
| Lambda | lambda-document-processor-seoul-prod | Lambda (ap-northeast-2) |
| S3 (서울) | bos-ai-documents-seoul-v3 | S3 (ap-northeast-2) |
| S3 (버지니아) | bos-ai-documents-us | S3 (us-east-1) |
| Frontend VPC | vpc-0a118e1bf21d0c057 | VPC (ap-northeast-2) |
| Transit Gateway | tgw-0897383168475b532 | VPC > TGW (ap-northeast-2) |

---

## 3단계: 일상 운영 실습 (2일차)

### 3.1 시스템 상태 확인 (매일 아침)

```bash
# CloudWatch 알람 상태
aws cloudwatch describe-alarms --state-value ALARM \
  --region ap-northeast-2 --profile mgmt

# Lambda 최근 에러
aws logs filter-log-events \
  --log-group-name /aws/lambda/lambda-document-processor-seoul-prod \
  --filter-pattern "ERROR" \
  --start-time $(date -d '24 hours ago' +%s)000 \
  --region ap-northeast-2 --profile mgmt

# VPN 터널 상태
aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-0b2b65e9414092369 \
  --query 'VpnConnections[0].VgwTelemetry[*].[OutsideIpAddress,Status]' \
  --output table --region ap-northeast-2 --profile mgmt
```

### 3.2 문서 업로드 테스트

```bash
# 테스트 문서 업로드
echo "운영자 온보딩 테스트 문서입니다." > /tmp/onboarding-test.txt
aws s3 cp /tmp/onboarding-test.txt \
  s3://bos-ai-documents-seoul-v3/documents/soc/spec/onboarding-test.txt \
  --region ap-northeast-2 --profile mgmt

# 복제 상태 확인 (5분 후)
aws s3api head-object \
  --bucket bos-ai-documents-seoul-v3 \
  --key documents/soc/spec/onboarding-test.txt \
  --query 'ReplicationStatus' --region ap-northeast-2 --profile mgmt

# 테스트 문서 삭제
aws s3 rm s3://bos-ai-documents-seoul-v3/documents/soc/spec/onboarding-test.txt \
  --region ap-northeast-2 --profile mgmt
```

### 3.3 KB Sync 수동 트리거

```bash
# Ingestion Job 시작
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id FNNOP3VBZV \
  --data-source-id 211WMHQAOK \
  --region us-east-1 --profile mgmt

# Job 상태 확인
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id FNNOP3VBZV \
  --data-source-id 211WMHQAOK \
  --max-results 3 --region us-east-1 --profile mgmt
```

---

## 4단계: 장애 대응 실습 (3일차)

### Lambda 에러율 증가

```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/lambda-document-processor-seoul-prod \
  --filter-pattern "ERROR" --region ap-northeast-2 --profile mgmt
```

### VPN 터널 다운

- 터널 1개 DOWN → BGP 자동 페일오버, 서비스 영향 없음
- 터널 2개 DOWN → 네트워크팀 긴급 연락

### S3 복제 실패

```bash
aws s3api head-object --bucket bos-ai-documents-seoul-v3 \
  --key <파일경로> --query 'ReplicationStatus' \
  --region ap-northeast-2 --profile mgmt
# FAILED → IAM 역할 권한 확인 → IT팀 에스컬레이션
```

---

## 5단계: Terraform 기본 (선택)

### 배포 순서 (반드시 준수)

```
1. global/backend → 2. global/iam → 3. network-layer → 4. app-layer/*
```

### 기본 명령어

```bash
terraform plan          # 변경 미리보기 (안전)
terraform apply         # 변경 적용 (주의)
terraform state list    # 현재 상태 확인
```

---

## 온보딩 완료 체크리스트

- [ ] 시스템 개요 문서 읽기 완료
- [ ] AWS Console 접근 및 MFA 설정 완료
- [ ] AWS CLI 프로파일 설정 및 테스트 완료
- [ ] CloudWatch 알람 확인 방법 숙지
- [ ] 문서 업로드 및 복제 확인 실습 완료
- [ ] KB Sync 수동 트리거 실습 완료
- [ ] Lambda 에러 로그 확인 방법 숙지
- [ ] VPN 터널 상태 확인 방법 숙지
- [ ] 긴급 연락망 확인 (docs/common/emergency-contacts.md)

---

## 참고 문서

| 문서 | 용도 |
|------|------|
| [운영 런북](../3_private-rag-api/OPERATIONAL_RUNBOOK.md) | 일상 운영 상세 절차 |
| [배포 가이드](../1_bedrock-rag-deployment/DEPLOYMENT_GUIDE.md) | Terraform 배포 절차 |
| [QuickSight 가이드](../8_quicksight-private-integration/quicksight-guide.md) | QuickSight 운영 가이드 |
| [문서 디렉토리](../README.md) | 전체 문서 구조 및 스펙 매핑 |

---

*최종 업데이트: 2026-04-03*
