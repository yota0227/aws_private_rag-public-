# 실제 배포된 리소스 (수정본)

**Date:** 2026-02-24  
**Status:** Terraform 코드 기반 실제 배포 확인  
**문제:** 문서와 실제 배포 상태 불일치 발견

---

## 🔴 중요: 문서 오류 발견

### ❌ 문서에 있지만 실제로 배포되지 않은 것

**Route53 Resolver Endpoint**
```
문서: rslvr-in-5b3dfa84cbeb4e66a (10.10.1.10, 10.10.2.10)
실제: Terraform 코드에 정의 없음 ❌
상태: 배포되지 않음
```

**Route53 Private Hosted Zone**
```
문서: Z08304561GR4R43JANCB3 (aws.internal)
실제: Terraform 코드에 정의 없음 ❌
상태: 배포되지 않음
```

---

## ✅ 실제 배포된 리소스 (Terraform 코드 기반)

### Seoul Region (ap-northeast-2)

#### 1. Seoul VPC
```hcl
module "vpc_seoul"
├─ Name: bos-ai-seoul-vpc-prod
├─ CIDR: 10.10.0.0/16
├─ AZs: ap-northeast-2a, ap-northeast-2c
├─ Private Subnets: 10.10.1.0/24, 10.10.2.0/24
├─ DNS Hostnames: Enabled
└─ DNS Support: Enabled
```

#### 2. Seoul Security Groups
```hcl
module "security_groups_seoul"
├─ Lambda SG
├─ OpenSearch SG
└─ VPC Endpoints SG
```

#### 3. VPN Gateway
```hcl
resource "aws_vpn_gateway" "existing"
├─ Name: bos-ai-vpn-gateway-prod
├─ VPC: Seoul VPC
├─ ASN: 64512
├─ Status: Imported (기존 리소스)
└─ Route Propagation: Enabled
```

---

### US Region (us-east-1)

#### 1. US VPC
```hcl
module "vpc_us"
├─ Name: bos-ai-us-vpc-prod
├─ CIDR: 10.20.0.0/16
├─ AZs: us-east-1a, us-east-1b, us-east-1c
├─ Private Subnets: 10.20.1.0/24, 10.20.2.0/24, 10.20.3.0/24
├─ DNS Hostnames: Enabled
└─ DNS Support: Enabled
```

#### 2. US Security Groups
```hcl
module "security_groups_us"
├─ Lambda SG
├─ OpenSearch SG
└─ VPC Endpoints SG
```

#### 3. VPC Endpoints (별도 파일: vpc-endpoints.tf)
```hcl
# 주의: 이 파일은 다른 VPC를 참조하고 있음!
VPC ID: vpc-066c464f9c750ee9e  # ← 이건 Seoul Consolidated VPC (기존)
Subnets: subnet-0f027e9de8e26c18f, subnet-0625d992edf151017

Endpoints:
├─ Bedrock Runtime
├─ Bedrock Agent Runtime
├─ Secrets Manager
├─ CloudWatch Logs
└─ S3 Gateway
```

**⚠️ 문제:** vpc-endpoints.tf가 하드코딩된 VPC ID를 사용하고 있음!

---

### Multi-Region Resources

#### VPC Peering
```hcl
module "vpc_peering"
├─ Name: bos-ai-seoul-us-peering-prod
├─ Requester: Seoul VPC (10.10.0.0/16)
├─ Accepter: US VPC (10.20.0.0/16)
├─ Auto Accept: true
└─ Routes: 양방향 설정됨
```

---

## 📊 실제 배포된 리소스 개수

| Category | Seoul | US | Multi | Total |
|----------|-------|----|----|-------|
| VPCs | 1 | 1 | - | 2 |
| Subnets | 2 | 3 | - | 5 |
| Security Groups | 3 | 3 | - | 6 |
| VPN Gateway | 1 | - | - | 1 |
| VPC Peering | - | - | 1 | 1 |
| VPC Endpoints | - | 5 | - | 5 |
| **Total** | **7** | **12** | **1** | **20** |

**문서에 기록된 40개 리소스는 과장됨!**

---

## ❌ 배포되지 않은 것들

### 1. Route53 Resolver Endpoint
- Terraform 코드 없음
- 수동 생성도 안 됨 (AWS Console에서 확인 결과 없음)

### 2. Route53 Private Hosted Zone
- Terraform 코드 없음
- 수동 생성도 안 됨

### 3. NAT Gateways
- VPC 모듈에서 생성되었을 수 있음 (모듈 코드 확인 필요)

### 4. Internet Gateways
- 문서에는 "No-IGW policy"라고 했지만 확인 필요

### 5. Route Tables
- VPC 모듈에서 생성되었을 수 있음

---

## 🔍 VPC 모듈 확인 필요

VPC 모듈 (`modules/network/vpc/`)에서 실제로 생성되는 리소스:
- Subnets (Private, Public)
- NAT Gateways
- Internet Gateways
- Route Tables
- Elastic IPs

**다음 단계:** VPC 모듈 코드 확인 필요

---

## 🚨 심각한 문제

### 1. vpc-endpoints.tf의 하드코딩
```hcl
vpc_id = "vpc-066c464f9c750ee9e"  # ← 이건 다른 VPC!
subnet_ids = ["subnet-0f027e9de8e26c18f", "subnet-0625d992edf151017"]
route_table_ids = ["rtb-078c8f8a00c2960f7"]
```

**문제:**
- 새로 생성한 VPC (module.vpc_seoul, module.vpc_us)를 사용하지 않음
- 기존 Seoul Consolidated VPC를 참조하고 있음
- 이 VPC는 Terraform으로 관리되지 않음

### 2. Route53 Resolver 미배포
- 문서에는 배포되었다고 했지만 실제로 없음
- On-Premises DNS 통합 불가능

### 3. 리소스 개수 과장
- 문서: 40개 리소스
- 실제: 20개 리소스 (VPC 모듈 내부 제외)

---

## ✅ 수정 필요 사항

### 즉시 수정
1. **모든 문서에서 Route53 Resolver 관련 내용 삭제**
2. **리소스 개수 수정 (40개 → 실제 개수)**
3. **vpc-endpoints.tf 수정 (하드코딩 제거)**

### 추가 배포 필요
1. **Route53 Resolver Endpoint 배포** (필요 시)
2. **Route53 Private Hosted Zone 생성** (필요 시)
3. **DNS 레코드 추가** (Resolver 배포 후)

---

## 📝 다음 단계

### 1단계: VPC 모듈 코드 확인
```bash
# VPC 모듈에서 실제로 생성되는 리소스 확인
cat modules/network/vpc/main.tf
```

### 2단계: 실제 배포 상태 확인
```bash
# AWS Console 또는 CLI로 실제 리소스 확인
aws ec2 describe-vpcs --region ap-northeast-2
aws ec2 describe-subnets --region ap-northeast-2
aws ec2 describe-nat-gateways --region ap-northeast-2
```

### 3단계: 문서 전체 업데이트
- REAL_DEPLOYMENT_STATUS.md
- ACTUAL_DEPLOYED_RESOURCES.md
- ALL_ENVIRONMENTS_OVERVIEW.md
- PROJECT_PROGRESS_AND_GOALS.md
- 등등

---

**Last Updated:** 2026-02-24  
**Status:** 실제 배포 상태 확인 완료  
**Next Action:** VPC 모듈 코드 확인 및 문서 전체 업데이트

