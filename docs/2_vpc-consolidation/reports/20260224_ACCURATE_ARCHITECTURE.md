# BOS-AI RAG 정확한 아키텍처 문서

**Date:** 2026-02-24  
**Account:** 533335672315  
**Status:** ✅ Terraform 코드 기반 정확한 현황

---

## 🎯 프로젝트 목적

**2-Region 아키텍처:**
- **Seoul (ap-northeast-2)**: Frontend - VPN 접근, VPC Peering을 통한 Backend 연결
- **US East (us-east-1)**: Backend - Bedrock, OpenSearch, Lambda 등 AI 워크로드

**핵심 원칙:**
- Seoul VPC (10.10.0.0/16): Private VPC, IGW 없음, VPN으로만 접근
- US VPC (10.20.0.0/16): Private VPC, VPC Endpoints로 AWS 서비스 접근
- VPC Peering: Seoul ↔ US 양방향 통신

---

## 🏗️ 실제 배포된 인프라

### Seoul Region (ap-northeast-2)

#### VPC 구성
```
VPC ID: vpc-0f759f00e5df658d1
├─ Name: bos-ai-seoul-vpc-prod
├─ CIDR: 10.10.0.0/16
├─ Purpose: Frontend / Transit Bridge
├─ Internet Access: ❌ None (Private only)
└─ DNS: Enabled (Hostnames + Support)
```

#### Subnets
```
Private Subnets (2개):
├─ 10.10.1.0/24 (ap-northeast-2a)
└─ 10.10.2.0/24 (ap-northeast-2c)

Public Subnets: ❌ None
```

#### Route Tables
```
Private RT 1 (ap-northeast-2a):
├─ 10.10.0.0/16 → Local
├─ 10.20.0.0/16 → VPC Peering
└─ VPN Gateway Route Propagation: Enabled

Private RT 2 (ap-northeast-2c):
├─ 10.10.0.0/16 → Local
├─ 10.20.0.0/16 → VPC Peering
└─ VPN Gateway Route Propagation: Enabled
```

#### Security Groups (3개)
```
1. Lambda SG (prod-lambda-sg)
   ├─ Ingress: None
   └─ Egress: HTTPS 443 to 10.10.0.0/16

2. OpenSearch SG (prod-opensearch-sg)
   ├─ Ingress: HTTPS 443 from Lambda SG
   ├─ Ingress: HTTPS 443 from 10.10.0.0/16
   ├─ Ingress: HTTPS 443 from 10.20.0.0/16 (Peer VPC)
   └─ Egress: All

3. VPC Endpoints SG (prod-vpc-endpoints-sg)
   ├─ Ingress: HTTPS 443 from 10.10.0.0/16
   ├─ Ingress: HTTPS 443 from 10.20.0.0/16 (Peer VPC)
   └─ Egress: All
```

#### VPN Gateway
```
Resource: aws_vpn_gateway.existing
├─ Name: bos-ai-vpn-gateway-prod
├─ VPC: vpc-0f759f00e5df658d1
├─ ASN: 64512
├─ Status: Imported (기존 리소스)
├─ Route Propagation: Enabled (모든 Private RT)
└─ Purpose: On-Premises 연결
```

---

### US Region (us-east-1)

#### VPC 구성
```
VPC: bos-ai-us-vpc-prod
├─ CIDR: 10.20.0.0/16
├─ Purpose: Backend / AI Workload
├─ Internet Access: VPC Endpoints (PrivateLink)
└─ DNS: Enabled (Hostnames + Support)
```

#### Subnets
```
Private Subnets (3개):
├─ 10.20.1.0/24 (us-east-1a)
├─ 10.20.2.0/24 (us-east-1b)
└─ 10.20.3.0/24 (us-east-1c)

Public Subnets: ❌ None
```

#### Route Tables
```
Private RT 1 (us-east-1a):
├─ 10.20.0.0/16 → Local
└─ 10.10.0.0/16 → VPC Peering

Private RT 2 (us-east-1b):
├─ 10.20.0.0/16 → Local
└─ 10.10.0.0/16 → VPC Peering

Private RT 3 (us-east-1c):
├─ 10.20.0.0/16 → Local
└─ 10.10.0.0/16 → VPC Peering
```

#### Security Groups (3개)
```
1. Lambda SG (prod-lambda-sg)
   ├─ Ingress: None
   └─ Egress: HTTPS 443 to 10.20.0.0/16

2. OpenSearch SG (prod-opensearch-sg)
   ├─ Ingress: HTTPS 443 from Lambda SG
   ├─ Ingress: HTTPS 443 from 10.20.0.0/16
   ├─ Ingress: HTTPS 443 from 10.10.0.0/16 (Peer VPC)
   └─ Egress: All

3. VPC Endpoints SG (prod-vpc-endpoints-sg)
   ├─ Ingress: HTTPS 443 from 10.20.0.0/16
   ├─ Ingress: HTTPS 443 from 10.10.0.0/16 (Peer VPC)
   └─ Egress: All
```

#### VPC Endpoints (계획됨)
```
Interface Endpoints:
├─ Bedrock Runtime
├─ Bedrock Agent Runtime
├─ Secrets Manager
├─ CloudWatch Logs
└─ OpenSearch Serverless

Gateway Endpoints:
└─ S3
```

---

### Multi-Region Resources

#### VPC Peering
```
module "vpc_peering"
├─ Name: bos-ai-seoul-us-peering-prod
├─ Requester: Seoul VPC (10.10.0.0/16)
├─ Accepter: US VPC (10.20.0.0/16)
├─ Auto Accept: true
├─ Routes:
│  ├─ Seoul → US: 10.20.0.0/16 via Peering
│  └─ US → Seoul: 10.10.0.0/16 via Peering
└─ Status: Active
```

---

## 🔗 네트워크 연결 흐름

### 1. On-Premises → Seoul VPC
```
On-Premises Network
    ↓ (VPN Tunnel)
Seoul VPC (10.10.0.0/16)
├─ VPN Gateway (ASN: 64512)
├─ Route Propagation: Enabled
└─ Private Subnets: 10.10.1.0/24, 10.10.2.0/24
```

### 2. Seoul VPC → US VPC
```
Seoul VPC (10.10.0.0/16)
    ↓ (VPC Peering)
US VPC (10.20.0.0/16)
├─ Route: 10.10.0.0/16 → Peering Connection
└─ Security Groups: Allow 10.10.0.0/16
```

### 3. US VPC → AWS Services
```
US VPC (10.20.0.0/16)
    ↓ (VPC Endpoints - PrivateLink)
AWS Services
├─ Bedrock Runtime
├─ Bedrock Agent Runtime
├─ S3
├─ OpenSearch Serverless
├─ Secrets Manager
└─ CloudWatch Logs
```

### 4. 전체 흐름
```
On-Premises
    ↓ VPN
Seoul VPC (10.10.0.0/16)
    ↓ VPC Peering
US VPC (10.20.0.0/16)
    ↓ VPC Endpoints
AWS Services (Bedrock, S3, OpenSearch)
```

---

## 📊 실제 리소스 개수

### Network Layer (배포 완료)

| Category | Seoul | US | Multi | Total |
|----------|-------|----|----|-------|
| VPCs | 1 | 1 | - | 2 |
| Subnets | 2 | 3 | - | 5 |
| Route Tables | 2 | 3 | - | 5 |
| Security Groups | 3 | 3 | - | 6 |
| VPN Gateway | 1 | - | - | 1 |
| VPC Peering | - | - | 1 | 1 |
| **Subtotal** | **9** | **10** | **1** | **20** |

### App Layer (배포 예정)

| Category | Count | Region |
|----------|-------|--------|
| KMS Keys | 1 | US |
| IAM Roles | 3 | Global |
| S3 Buckets | 4 | Seoul + US |
| Lambda Functions | 1 | US |
| OpenSearch Serverless | 1 | US |
| Bedrock Knowledge Base | 1 | US |
| VPC Endpoints | 6 | US |
| CloudWatch Logs | 5 | US |
| CloudWatch Alarms | 3 | US |
| CloudTrail | 1 | Multi-Region |
| AWS Budgets | 1 | Global |
| **Subtotal** | **27** | - |

**Total: 47개 리소스 (20 배포됨 + 27 예정)**

---

## 💰 월별 비용

### Network Layer (현재)
```
VPC Peering: $0 (같은 계정)
VPN Gateway: $0 (기존 리소스)
Total: $0/month
```

### App Layer (예정)
```
VPC Endpoints (Interface): $28.80 (4개 × $7.20)
VPC Endpoints (Gateway): $0 (S3)
OpenSearch Serverless: $700 (2 OCU × $350)
Lambda: $5-10
S3 Storage: $46
S3 Replication: $20
Bedrock Embedding: $10-20
Bedrock Claude: $50-100
CloudWatch: $8
CloudTrail: $2
Total: $870-935/month
```

**전체 예상 비용: $870-935/month**

---

## 🔐 보안 아키텍처

### Layer 1: Network Isolation
```
Seoul VPC:
├─ IGW: ❌ None
├─ NAT Gateway: ❌ None
├─ Internet Access: ❌ None
└─ Access: VPN only

US VPC:
├─ IGW: ❌ None
├─ NAT Gateway: ❌ None
├─ Internet Access: VPC Endpoints only
└─ Access: VPC Peering from Seoul
```

### Layer 2: VPC Endpoints (PrivateLink)
```
모든 AWS 서비스 접근:
├─ Bedrock Runtime: PrivateLink
├─ Bedrock Agent Runtime: PrivateLink
├─ S3: Gateway Endpoint
├─ OpenSearch: PrivateLink
├─ Secrets Manager: PrivateLink
└─ CloudWatch Logs: PrivateLink

특징:
├─ 인터넷 노출: ❌ None
├─ 트래픽: AWS 백본 네트워크만
└─ 비용: Interface Endpoint만 과금
```

### Layer 3: Security Groups
```
최소 권한 원칙:
├─ Lambda: Outbound only (HTTPS 443)
├─ OpenSearch: Lambda + VPC CIDR만 허용
└─ VPC Endpoints: VPC CIDR만 허용

Peer VPC 지원:
├─ Seoul → US: 10.20.0.0/16 허용
└─ US → Seoul: 10.10.0.0/16 허용
```

### Layer 4: Encryption
```
At Rest:
├─ KMS: 모든 서비스 암호화
├─ S3: KMS 암호화
├─ OpenSearch: KMS 암호화
└─ CloudWatch Logs: KMS 암호화

In Transit:
├─ VPC Peering: AWS 백본 (암호화)
├─ VPC Endpoints: TLS 1.2+
└─ VPN: IPSec
```

### Layer 5: IAM (Least Privilege)
```
Roles:
├─ Bedrock KB Role: S3 read, OpenSearch write, KMS decrypt
├─ Lambda Role: S3 read/write, Bedrock invoke, OpenSearch write
└─ VPC Flow Logs Role: CloudWatch logs write

Policies:
├─ Resource-based: S3, KMS, OpenSearch
└─ Identity-based: Lambda, Bedrock
```

### Layer 6: Audit & Compliance
```
Logging:
├─ CloudTrail: 모든 API 호출
├─ VPC Flow Logs: 네트워크 트래픽
├─ CloudWatch Logs: 애플리케이션 로그
└─ Retention: 30일

Monitoring:
├─ CloudWatch Alarms: Lambda, Bedrock, OpenSearch
├─ CloudWatch Dashboard: 통합 모니터링
└─ AWS Budgets: 비용 알림
```

---

## 🚀 배포 순서

### Phase 1: Network Layer ✅ (완료)
```bash
cd environments/network-layer
terraform init
terraform plan
terraform apply
```

**배포된 리소스:**
- Seoul VPC + Subnets + Route Tables
- US VPC + Subnets + Route Tables
- VPC Peering
- Security Groups (Seoul + US)
- VPN Gateway (Imported)

### Phase 2: App Layer ⏳ (대기 중)
```bash
cd environments/app-layer/bedrock-rag
terraform init
terraform plan
terraform apply
```

**배포 예정 리소스:**
- KMS Keys
- IAM Roles & Policies
- S3 Buckets + Replication
- Lambda Functions
- OpenSearch Serverless
- Bedrock Knowledge Base
- VPC Endpoints
- CloudWatch Monitoring
- CloudTrail
- AWS Budgets

---

## 📝 Terraform 모듈 구조

```
environments/
├── network-layer/
│   ├── main.tf (VPC, Peering, SG, VPN)
│   ├── variables.tf (CIDR, AZ 설정)
│   └── outputs.tf (VPC ID, Subnet ID 등)
│
└── app-layer/
    └── bedrock-rag/
        ├── main.tf (KMS, IAM, S3, Lambda, Bedrock)
        ├── variables.tf (설정값)
        ├── outputs.tf (리소스 ID)
        └── data.tf (Network Layer 참조)

modules/
├── network/
│   ├── vpc/ (VPC, Subnet, RT)
│   ├── peering/ (VPC Peering)
│   └── security-groups/ (SG)
│
├── security/
│   ├── kms/ (암호화 키)
│   ├── iam/ (역할 & 정책)
│   ├── vpc-endpoints/ (PrivateLink)
│   └── cloudtrail/ (감사 로그)
│
├── ai-workload/
│   ├── s3-pipeline/ (S3 + Lambda)
│   └── bedrock-rag/ (Bedrock + OpenSearch)
│
├── monitoring/
│   ├── cloudwatch-logs/
│   ├── cloudwatch-alarms/
│   ├── cloudwatch-dashboards/
│   └── vpc-flow-logs/
│
└── cost-management/
    └── budgets/
```

---

## ⚠️ 중요 사항

### 1. Seoul VPC는 Private Only
- IGW 없음
- NAT Gateway 없음
- 인터넷 접근 불가
- VPN으로만 접근 가능

### 2. US VPC는 VPC Endpoints만 사용
- IGW 없음
- NAT Gateway 없음
- VPC Endpoints로 AWS 서비스 접근
- VPC Peering으로 Seoul VPC와 통신

### 3. 기존 VPC (10.200.0.0/16)와 분리
- vpc-066c464f9c750ee9e: 기존 서비스용
- vpc-0f759f00e5df658d1: BOS-AI 신규 (10.10.0.0/16)
- 두 VPC는 독립적으로 운영

### 4. VPN 접근
- Seoul VPC (10.10.0.0/16): VPN으로만 접근
- 기존 VPC (10.200.0.0/16): VPN으로 접근 (기존 설정)

---

## ✅ 다음 단계

### 즉시
1. ✅ 정확한 아키텍처 문서 작성 완료
2. ⏳ App Layer 배포 준비
3. ⏳ VPC Endpoints 설정 확인

### 단기
1. ⏳ App Layer 배포 (Bedrock, OpenSearch, Lambda)
2. ⏳ 통합 테스트
3. ⏳ 성능 최적화

### 중기
1. ⏳ 부하 테스트
2. ⏳ 비용 최적화
3. ⏳ 보안 감사

---

**Last Updated:** 2026-02-24  
**Status:** ✅ 정확한 아키텍처 문서 작성 완료  
**Next Action:** App Layer 배포

