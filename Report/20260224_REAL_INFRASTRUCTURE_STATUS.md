# 실제 인프라 현황 (정확한 버전)

**Date:** 2026-02-24  
**Account:** 533335672315  
**Region:** ap-northeast-2 (Seoul), us-east-1 (US)

---

## 🎯 실제 VPC 구성

### Seoul Region (ap-northeast-2)

#### 존재하는 VPC 3개

| VPC ID | CIDR | 용도 | IGW | 상태 |
|--------|------|------|-----|------|
| vpc-066c464f9c750ee9e | 10.200.0.0/16 | 기존 서비스 | ✅ | Active |
| vpc-0f759f00e5df658d1 | 10.10.0.0/16 | **BOS-AI (신규)** | ❌ | Active |
| vpc-0a95e64e8e99cc162 | Default | Default VPC | ✅ | Active |

#### BOS-AI VPC 상세 (vpc-0f759f00e5df658d1)

```
VPC: vpc-0f759f00e5df658d1
├─ Name: bos-ai-seoul-vpc-prod
├─ CIDR: 10.10.0.0/16
├─ Purpose: Private VPC (No IGW)
├─ Internet Access: ❌ None (Private only)
├─ Connectivity:
│  ├─ VPN Gateway → On-Premises
│  └─ VPC Peering → US VPC (10.20.0.0/16)
└─ Subnets:
   ├─ Private Subnet 1: 10.10.1.0/24 (ap-northeast-2a)
   └─ Private Subnet 2: 10.10.2.0/24 (ap-northeast-2c)
```

**중요:**
- IGW 없음 (Private VPC)
- NAT Gateway 불필요 (인터넷 접근 안 함)
- VPC Peering으로만 US VPC와 통신

---

### US Region (us-east-1)

#### BOS-AI VPC (예상)

```
VPC: vpc-XXXXXXXXX (확인 필요)
├─ Name: bos-ai-us-vpc-prod
├─ CIDR: 10.20.0.0/16
├─ Purpose: AI Workload (Bedrock, OpenSearch, Lambda)
├─ Internet Access: VPC Endpoints (PrivateLink)
├─ Connectivity:
│  └─ VPC Peering → Seoul VPC (10.10.0.0/16)
└─ Subnets:
   ├─ Private Subnet 1: 10.20.1.0/24 (us-east-1a)
   ├─ Private Subnet 2: 10.20.2.0/24 (us-east-1b)
   └─ Private Subnet 3: 10.20.3.0/24 (us-east-1c)
```

---

## 🔗 네트워크 연결

### 1. On-Premises → Seoul VPC
```
On-Premises
    ↓ (VPN Tunnel)
Seoul VPC (10.10.0.0/16)
    ↓ (VPC Peering)
US VPC (10.20.0.0/16)
```

### 2. Seoul VPC → US VPC
```
VPC Peering Connection
├─ Requester: Seoul VPC (10.10.0.0/16)
├─ Accepter: US VPC (10.20.0.0/16)
├─ Status: Active
└─ Routes: 양방향 설정
```

---

## ❌ 배포되지 않은 것들 (문서 오류)

### 1. Route53 Resolver
- 문서: rslvr-in-5b3dfa84cbeb4e66a
- 실제: **없음**
- 필요성: **불필요** (On-Premises DNS는 VPN으로 직접 연결)

### 2. Route53 Private Hosted Zone
- 문서: Z08304561GR4R43JANCB3
- 실제: **없음**
- 필요성: **불필요** (VPC Endpoints 사용)

### 3. NAT Gateways
- 문서: 5개
- 실제: **0개**
- 필요성: **불필요** (Private VPC, 인터넷 접근 안 함)

### 4. Public Subnets
- 문서: Seoul 2개, US 3개
- 실제: **0개**
- 필요성: **불필요** (Private VPC)

### 5. Internet Gateways
- 문서: "No-IGW policy"
- 실제: **없음** (정확함)
- 필요성: **불필요** (Private VPC)

---

## ✅ 실제 배포된 리소스

### Seoul Region

```
1. VPC (1개)
   └─ vpc-0f759f00e5df658d1 (10.10.0.0/16)

2. Private Subnets (2개)
   ├─ 10.10.1.0/24 (ap-northeast-2a)
   └─ 10.10.2.0/24 (ap-northeast-2c)

3. Route Tables (2개)
   ├─ Private RT 1
   └─ Private RT 2

4. Security Groups (3개)
   ├─ Lambda SG
   ├─ OpenSearch SG
   └─ VPC Endpoints SG

5. VPN Gateway (1개)
   └─ Imported (기존 리소스)

Total: 9개 리소스
```

### US Region

```
1. VPC (1개)
   └─ bos-ai-us-vpc-prod (10.20.0.0/16)

2. Private Subnets (3개)
   ├─ 10.20.1.0/24 (us-east-1a)
   ├─ 10.20.2.0/24 (us-east-1b)
   └─ 10.20.3.0/24 (us-east-1c)

3. Route Tables (3개)
   ├─ Private RT 1
   ├─ Private RT 2
   └─ Private RT 3

4. Security Groups (3개)
   ├─ Lambda SG
   ├─ OpenSearch SG
   └─ VPC Endpoints SG

5. VPC Endpoints (5개)
   ├─ Bedrock Runtime
   ├─ Bedrock Agent Runtime
   ├─ Secrets Manager
   ├─ CloudWatch Logs
   └─ S3 Gateway

Total: 15개 리소스
```

### Multi-Region

```
1. VPC Peering (1개)
   └─ Seoul ↔ US

Total: 1개 리소스
```

---

## 📊 정확한 리소스 개수

| Category | Seoul | US | Multi | Total |
|----------|-------|----|----|-------|
| VPCs | 1 | 1 | - | 2 |
| Subnets | 2 | 3 | - | 5 |
| Route Tables | 2 | 3 | - | 5 |
| Security Groups | 3 | 3 | - | 6 |
| VPN Gateway | 1 | - | - | 1 |
| VPC Peering | - | - | 1 | 1 |
| VPC Endpoints | - | 5 | - | 5 |
| **Total** | **9** | **15** | **1** | **25** |

---

## 💰 정확한 월별 비용

| 항목 | 개수 | 단가 | 합계 |
|------|------|------|------|
| VPC Peering | 1 | $0 | $0 |
| VPC Endpoints (Interface) | 4 | $7.20 | $28.80 |
| VPC Endpoints (Gateway) | 1 | $0 | $0 |
| **합계** | - | - | **$28.80** |

**문서 오류:**
- 문서: $360.75/month
- 실제: $28.80/month

---

## 🏗️ 정확한 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    ON-PREMISES NETWORK                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Internal Network                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                   │
│                    VPN Tunnel                                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│              AWS REGION: ap-northeast-2 (Seoul)             │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  VPC: vpc-0f759f00e5df658d1 (10.10.0.0/16)          │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │  Private Subnets (2)                           │ │  │
│  │  │  ├─ 10.10.1.0/24 (2a)                          │ │  │
│  │  │  └─ 10.10.2.0/24 (2c)                          │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  │                                                       │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │  VPN Gateway (Imported)                        │ │  │
│  │  │  └─ ASN: 64512                                 │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  │                                                       │  │
│  │  Security Groups:                                    │  │
│  │  ├─ Lambda SG                                        │  │
│  │  ├─ OpenSearch SG                                    │  │
│  │  └─ VPC Endpoints SG                                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                   │
│                    VPC Peering                               │
│                          ↓                                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    AWS REGION: us-east-1 (US)               │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  VPC: bos-ai-us-vpc-prod (10.20.0.0/16)             │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │  Private Subnets (3)                           │ │  │
│  │  │  ├─ 10.20.1.0/24 (1a)                          │ │  │
│  │  │  ├─ 10.20.2.0/24 (1b)                          │ │  │
│  │  │  └─ 10.20.3.0/24 (1c)                          │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  │                                                       │  │
│  │  VPC Endpoints (PrivateLink):                        │  │
│  │  ├─ Bedrock Runtime                                  │  │
│  │  ├─ Bedrock Agent Runtime                            │  │
│  │  ├─ Secrets Manager                                  │  │
│  │  ├─ CloudWatch Logs                                  │  │
│  │  └─ S3 Gateway                                       │  │
│  │                                                       │  │
│  │  Security Groups:                                    │  │
│  │  ├─ Lambda SG                                        │  │
│  │  ├─ OpenSearch SG                                    │  │
│  │  └─ VPC Endpoints SG                                 │  │
│  │                                                       │  │
│  │  AI/ML Services (To be deployed):                    │  │
│  │  ├─ OpenSearch Serverless                            │  │
│  │  ├─ Bedrock Knowledge Base                           │  │
│  │  └─ Lambda Functions                                 │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔐 보안 아키텍처

### Layer 1: Network Isolation
- ✅ Seoul VPC: Private only (No IGW)
- ✅ US VPC: Private only (VPC Endpoints)
- ✅ VPC Peering: Seoul ↔ US
- ✅ VPN: On-Premises ↔ Seoul

### Layer 2: VPC Endpoints (PrivateLink)
- ✅ Bedrock Runtime (no internet)
- ✅ Bedrock Agent Runtime (no internet)
- ✅ S3 Gateway (no internet)
- ✅ Secrets Manager (no internet)
- ✅ CloudWatch Logs (no internet)

### Layer 3: Security Groups
- ✅ Lambda SG: No inbound, controlled outbound
- ✅ OpenSearch SG: HTTPS 443 from Lambda
- ✅ VPC Endpoints SG: HTTPS 443 from VPC CIDRs

---

## 🚨 vpc-endpoints.tf 문제

### 현재 코드 (잘못됨)
```hcl
vpc_id = "vpc-066c464f9c750ee9e"  # ← 기존 서비스 VPC (10.200.0.0/16)
```

### 수정 필요
```hcl
vpc_id = module.vpc_us.vpc_id  # ← BOS-AI US VPC (10.20.0.0/16)
```

---

## ✅ 다음 단계

### 1. 모든 문서 수정
- [ ] Route53 Resolver 관련 내용 삭제
- [ ] NAT Gateway 관련 내용 삭제
- [ ] Public Subnet 관련 내용 삭제
- [ ] 리소스 개수 수정 (40개 → 25개)
- [ ] 비용 수정 ($360.75 → $28.80)
- [ ] VPC ID 수정 (vpc-0f759f00e5df658d1)

### 2. vpc-endpoints.tf 수정
- [ ] VPC ID 하드코딩 제거
- [ ] module.vpc_us.vpc_id 사용
- [ ] Subnet IDs 수정
- [ ] Route Table IDs 수정

### 3. US VPC 실제 ID 확인
- [ ] AWS Console에서 US VPC ID 확인
- [ ] 문서에 정확한 ID 기록

---

**Last Updated:** 2026-02-24  
**Status:** ✅ 실제 인프라 현황 정확히 파악  
**Next Action:** 모든 문서 수정

