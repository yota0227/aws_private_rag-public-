# Deep Dive: 보안 정책 상세

> 상위 문서: [BOS-AI Private RAG System Overview](../BOS-AI-Private-RAG-System-Overview.md)

---

## 1. 보안 설계 원칙

BOS-AI Private RAG 시스템은 다음 원칙에 따라 설계되었습니다:

| 원칙 | 설명 |
|------|------|
| Air-Gapped | 인터넷에서 시스템의 존재 자체를 알 수 없음 |
| Zero Trust | 모든 접근은 명시적으로 허용된 경우만 가능 |
| 최소 권한 | 각 컴포넌트는 필요한 최소한의 권한만 보유 |
| 암호화 기본 | 전송 중, 저장 중 모든 데이터 암호화 |

---

## 2. 네트워크 격리

### 2.1 Private RAG VPC 격리

Private RAG VPC(10.10.0.0/16)는 인터넷과 완전히 격리되어 있습니다:

```
인터넷 ──X──→ Private RAG VPC (접근 불가)
                │
                ├─ Internet Gateway: 없음
                ├─ NAT Gateway: 없음
                ├─ 0.0.0.0/0 라우팅: 없음
                │
                └─ 허용된 경로만 존재:
                   ├─ 192.128.0.0/16 → TGW (온프레미스)
                   └─ 10.20.0.0/16 → VPC Peering (버지니아)
```

### 2.2 Security Group 규칙

#### VPC Endpoints Security Group

| 방향 | 프로토콜 | 포트 | 소스/대상 | 설명 |
|------|---------|------|----------|------|
| Inbound | TCP | 443 | 192.128.0.0/16 | 온프레미스에서 접근 |
| Inbound | TCP | 443 | 10.10.0.0/16 | VPC 내부 접근 |

#### Route53 Resolver Security Group

| 방향 | 프로토콜 | 포트 | 소스/대상 | 설명 |
|------|---------|------|----------|------|
| Inbound | TCP/UDP | 53 | 192.128.0.0/16 | 온프레미스 DNS 쿼리 |

#### Lambda Security Group

| 방향 | 프로토콜 | 포트 | 소스/대상 | 설명 |
|------|---------|------|----------|------|
| Outbound | TCP | 443 | VPC Endpoints SG | AWS 서비스 접근 |
| Outbound | TCP | 443 | 10.20.0.0/16 | 버지니아 Backend 접근 |

> Lambda는 Inbound 규칙이 없습니다. Lambda는 외부에서 직접 호출되지 않고, API Gateway가 내부적으로 호출합니다.

---

## 3. API Gateway 보안

### 3.1 Resource Policy

API Gateway는 Resource Policy를 통해 접근을 제한합니다:

```json
{
  "Effect": "Allow",
  "Principal": "*",
  "Action": "execute-api:Invoke",
  "Resource": "execute-api:/*",
  "Condition": {
    "StringEquals": {
      "aws:sourceVpce": "vpce-0e5f61dd7bd52882e"
    }
  }
}
```

이 정책은:
- VPC Endpoint(vpce-0e5f61dd7bd52882e)를 통한 요청만 허용
- 인터넷에서의 직접 접근은 불가능
- VPC Endpoint의 Security Group이 온프레미스 IP만 허용하므로 이중 보안

### 3.2 execute-api VPC Endpoint Private DNS 비활성화

VPC Endpoint의 Private DNS를 비활성화한 이유:

```
[문제]
execute-api VPC Endpoint의 Private DNS가 활성화되면:
  *.execute-api.ap-northeast-2.amazonaws.com → VPC Endpoint IP
  
이 경우 Private Hosted Zone의 커스텀 도메인과 충돌 발생

[해결]
Private DNS 비활성화 → Private Hosted Zone에서 Alias 레코드로 라우팅
  rag.corp.bos-semi.com → VPC Endpoint DNS → VPC Endpoint IP
```

---

## 4. IAM 정책 (최소 권한)

### 4.1 Lambda Execution Role

Lambda 함수는 다음 권한만 보유합니다:

| 정책 | 권한 | 리소스 |
|------|------|--------|
| S3 Access | GetObject, ListBucket | 데이터 소스 버킷만 |
| CloudWatch Logs | CreateLogGroup, PutLogEvents | Lambda 로그 그룹만 |
| Bedrock Access | StartIngestionJob, GetIngestionJob | Knowledge Base만 |
| KMS Access | Decrypt, GenerateDataKey | 프로젝트 KMS 키만 |
| VPC Access | CreateNetworkInterface, DeleteNetworkInterface | ENI 관리 |

### 4.2 Bedrock KB Role

| 정책 | 권한 | 리소스 |
|------|------|--------|
| S3 Read | GetObject, ListBucket | 데이터 소스 버킷만 |
| OpenSearch | aoss:APIAccessAll | 벡터 컬렉션만 |
| Bedrock | bedrock:InvokeModel | 임베딩 모델만 |

### 4.3 S3 Replication Role

| 정책 | 권한 | 리소스 |
|------|------|--------|
| Source S3 | GetObject, GetReplicationConfiguration | 서울 버킷만 |
| Destination S3 | ReplicateObject, ReplicateDelete | 버지니아 버킷만 |
| KMS | Decrypt (서울), Encrypt (버지니아) | 각 리전 KMS 키 |

---

## 5. 데이터 암호화

### 5.1 전송 중 암호화

| 구간 | 암호화 방식 |
|------|-----------|
| 온프레미스 ↔ AWS | IPsec VPN (AES-256) |
| 브라우저 ↔ API Gateway | TLS 1.2 |
| Lambda ↔ AWS 서비스 | TLS 1.2 (VPC Endpoint) |
| VPC Peering (서울 ↔ 버지니아) | AWS 내부 암호화 |

### 5.2 저장 중 암호화

| 서비스 | 암호화 방식 | KMS 키 |
|--------|-----------|--------|
| S3 (서울) | SSE-KMS | 서울 리전 KMS 키 |
| S3 (버지니아) | SSE-KMS | 버지니아 리전 KMS 키 |
| OpenSearch Serverless | AWS 관리형 암호화 | AWS 관리 |
| Lambda 환경 변수 | KMS | 프로젝트 KMS 키 |

### 5.3 Cross-Region 암호화

S3 Cross-Region Replication 시:
1. 서울 KMS 키로 복호화
2. 버지니아 KMS 키로 재암호화
3. 암호화된 상태로 전송

---

## 6. S3 Bucket Policy

S3 버킷은 VPC Endpoint를 통한 접근만 허용합니다:

```json
{
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": [
    "arn:aws:s3:::bos-ai-documents-seoul-v3",
    "arn:aws:s3:::bos-ai-documents-seoul-v3/*"
  ],
  "Condition": {
    "StringNotEquals": {
      "aws:sourceVpce": "vpce-08474f7814c698b6c"
    }
  }
}
```

예외:
- Terraform IAM 사용자 (인프라 관리)
- S3 Replication Role (Cross-Region 복제)

---

## 7. DNS 보안

### 7.1 조건부 포워딩

| 항목 | 설정 |
|------|------|
| 포워딩 도메인 | *.corp.bos-semi.com만 |
| 포워딩 대상 | Route53 Resolver Inbound IP |
| 기타 도메인 | 기존 DNS 경로 유지 |
| 롤백 시간 | 1분 이내 |

### 7.2 Private Hosted Zone 격리

Private Hosted Zone은 연결된 VPC 내부에서만 해석됩니다:
- Private RAG VPC에서만 rag.corp.bos-semi.com 해석 가능
- Logging VPC나 다른 VPC에서는 해석 불가
- 인터넷에서는 존재 자체를 알 수 없음

---

## 8. 감사 및 로깅

### 8.1 CloudTrail

모든 AWS API 호출이 기록됩니다:
- S3 접근 로그
- Lambda 호출 로그
- IAM 인증 로그
- 보존 기간: 90일

### 8.2 VPC Flow Logs

네트워크 트래픽 로그:
- 허용/거부된 트래픽 기록
- 소스/대상 IP, 포트 기록
- 보안 분석에 활용

### 8.3 API Gateway 로그

API 호출 로그:
- 요청/응답 로그
- 에러 로그
- 접근 로그 (소스 IP, 요청 경로)

---

## 9. 보안 체크리스트

| 항목 | 상태 | 설명 |
|------|------|------|
| Internet Gateway 없음 | ✅ | Private RAG VPC |
| NAT Gateway 없음 | ✅ | Private RAG VPC |
| VPC Endpoint 전용 접근 | ✅ | 모든 AWS 서비스 |
| Security Group 최소 규칙 | ✅ | 온프레미스 IP만 허용 |
| IAM 최소 권한 | ✅ | 각 역할별 필요 권한만 |
| KMS 암호화 | ✅ | S3, Lambda 환경 변수 |
| TLS 1.2 | ✅ | 모든 API 통신 |
| CloudTrail 활성화 | ✅ | 모든 API 호출 기록 |
| 조건부 DNS 포워딩 | ✅ | SaaS 서비스 영향 없음 |
| Private API Gateway | ✅ | VPC Endpoint 전용 |

---

## 참고 문서

- [현재 IAM 정책](current-iam-roles-policies.md)
- [현재 Security Group](current-security-groups.md)
- [DNS 조건부 포워딩 가이드](dns-conditional-forwarding-guide.md)
- [롤백 계획](rollback-plan.md)
- [태깅 전략](tagging-strategy.md)

---

> **작성일**: 2026-03-10  
> **상위 문서**: [BOS-AI Private RAG System Overview](../BOS-AI-Private-RAG-System-Overview.md)
