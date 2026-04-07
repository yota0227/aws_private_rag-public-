# AWS Bedrock RAG Infrastructure - Current Deployment Status

**Generated:** 2026-02-20  
**Account ID:** 533335672315  
**User:** seungil.woo  
**Status:** ✅ PARTIALLY DEPLOYED

---

## 📊 배포 현황 요약

### ✅ 완료된 배포 (Network Layer)

#### 1. Seoul Region (ap-northeast-2)
- **VPC**: `vpc-0f759f00e5df658d1`
  - CIDR: `10.0.0.0/16`
  - 상태: Active ✅
  - 가용 영역: 3개 (2a, 2b, 2c)
  - 서브넷: 6개 (Private 3개, Public 3개)
  - NAT Gateway: 3개 (각 AZ별)

- **VPN Gateway**: `vgw-XXXXXXXXX` (기존 인프라)
  - 상태: Attached ✅
  - ASN: 64512
  - 용도: On-premises 연결

- **Security Groups**: 3개
  - Lambda SG: `sg-XXXXXXXXX`
  - OpenSearch SG: `sg-XXXXXXXXX`
  - VPC Endpoints SG: `sg-XXXXXXXXX`

#### 2. US East Region (us-east-1)
- **VPC**: `vpc-0ed37ff82027c088f`
  - CIDR: `10.1.0.0/16`
  - 상태: Active ✅
  - 가용 영역: 3개 (1a, 1b, 1c)
  - 서브넷: 6개 (Private 3개, Public 3개)
  - NAT Gateway: 3개 (각 AZ별)

- **Security Groups**: 3개
  - Lambda SG: `sg-XXXXXXXXX`
  - OpenSearch SG: `sg-XXXXXXXXX`
  - VPC Endpoints SG: `sg-XXXXXXXXX`

#### 3. VPC Peering
- **Peering Connection**: `pcx-06877f7ce046cd122`
  - 상태: Active ✅
  - 연결: Seoul VPC ↔ US VPC
  - 대역폭: 10Gbps
  - DNS 해석: Seoul → US (활성화), US → Seoul (비활성화)

#### 4. Route53 DNS Integration
- **Private Hosted Zone**: `Z08304561GR4R43JANCB3`
  - 이름: `aws.internal`
  - 상태: Active ✅
  - 연결 VPC: Seoul, US

- **Route53 Resolver Inbound Endpoint**: `rslvr-in-5b3dfa84cbeb4e66a`
  - 위치: Seoul (ap-northeast-2)
  - IPs: `10.10.1.10`, `10.10.2.10`
  - 상태: Active ✅
  - 용도: On-premises DNS 쿼리 수신

- **Security Group**: `sg-02892b260ed8b09c4`
  - Ingress: DNS (TCP/UDP 53) from 10.0.0.0/8
  - Egress: All traffic

---

### ⏳ 배포 대기 중 (App Layer)

#### 1. S3 Pipeline (US East)
- **S3 Buckets**:
  - Seoul Source: `bos-ai-documents-seoul`
  - US Target: `bos-ai-documents-us`
  - CloudTrail Logs: `bos-ai-cloudtrail-logs`
  - Status: ⏳ Not Deployed

- **Cross-Region Replication**:
  - Seoul → US
  - Status: ⏳ Not Deployed

- **Lambda Function**: `document-processor`
  - Memory: 1024MB
  - Timeout: 300s
  - VPC: US VPC
  - Status: ⏳ Not Deployed

#### 2. Bedrock RAG (US East)
- **OpenSearch Serverless**:
  - Collection: `bos-ai-vectors`
  - Index: `bedrock-knowledge-base-index`
  - Dimensions: 1536 (Titan Embed)
  - Status: ⏳ Not Deployed

- **Bedrock Knowledge Base**:
  - Name: `bos-ai-knowledge-base`
  - Data Source: S3
  - Status: ⏳ Not Deployed

- **KMS Encryption**:
  - Key: `bos-ai-kms-key`
  - Status: ⏳ Not Deployed

#### 3. Monitoring (US East)
- **CloudWatch Logs**: 5개 그룹
  - /aws/lambda/document-processor
  - /aws/bedrock/knowledgebase/bos-ai-knowledge-base
  - /aws/opensearchserverless/bos-ai-vectors
  - /aws/vpc-flow-logs/us-vpc
  - Status: ⏳ Not Deployed

- **CloudWatch Alarms**: 3개
  - Lambda Errors
  - Lambda Duration
  - Lambda Throttles
  - Status: ⏳ Not Deployed

- **CloudWatch Dashboard**: 1개
  - Status: ⏳ Not Deployed

#### 4. Cost Management
- **AWS Budgets**: Monthly budget alert
  - Status: ⏳ Not Deployed

---

## 🏗️ 배포된 리소스 상세 정보

### Network Layer Resources (35개)

#### Seoul Region (ap-northeast-2)
| 리소스 타입 | 개수 | 상태 |
|-----------|------|------|
| VPC | 1 | ✅ |
| Public Subnets | 3 | ✅ |
| Private Subnets | 3 | ✅ |
| NAT Gateways | 3 | ✅ |
| Elastic IPs | 3 | ✅ |
| Route Tables | 4 | ✅ |
| Security Groups | 3 | ✅ |
| VPN Gateway | 1 | ✅ |
| Route Propagation | 3 | ✅ |
| **Subtotal** | **24** | **✅** |

#### US Region (us-east-1)
| 리소스 타입 | 개수 | 상태 |
|-----------|------|------|
| VPC | 1 | ✅ |
| Public Subnets | 3 | ✅ |
| Private Subnets | 3 | ✅ |
| NAT Gateways | 3 | ✅ |
| Elastic IPs | 3 | ✅ |
| Route Tables | 4 | ✅ |
| Security Groups | 3 | ✅ |
| **Subtotal** | **22** | **✅** |

#### Multi-Region
| 리소스 타입 | 개수 | 상태 |
|-----------|------|------|
| VPC Peering | 1 | ✅ |
| Route53 Hosted Zone | 1 | ✅ |
| Route53 Resolver Endpoint | 1 | ✅ |
| Route53 Resolver SG | 1 | ✅ |
| **Subtotal** | **4** | **✅** |

**Network Layer Total: 50개 리소스 ✅**

---

## 📋 배포 체크리스트

### Phase 1: Global Backend ✅
- [x] S3 Terraform State Bucket
- [x] DynamoDB State Lock Table
- [x] IAM Policies for State Management

### Phase 2: Network Layer ✅
- [x] Seoul VPC (10.0.0.0/16)
- [x] US VPC (10.1.0.0/16)
- [x] VPC Peering Connection
- [x] Security Groups (Seoul & US)
- [x] VPN Gateway (Imported)
- [x] Route53 DNS Integration
- [x] Route53 Resolver Endpoint

### Phase 3: App Layer ⏳
- [ ] KMS Encryption Key
- [ ] IAM Roles & Policies
- [ ] S3 Buckets (Seoul & US)
- [ ] S3 Cross-Region Replication
- [ ] Lambda Function (document-processor)
- [ ] OpenSearch Serverless Collection
- [ ] OpenSearch Vector Index
- [ ] Bedrock Knowledge Base
- [ ] Bedrock Data Source
- [ ] CloudWatch Logs
- [ ] CloudWatch Alarms
- [ ] CloudWatch Dashboard
- [ ] CloudTrail
- [ ] AWS Budgets

---

## 🔧 다음 단계

### 1. AWS 자격증명 설정 (필수)
```powershell
# AWS CLI 자격증명 설정
aws configure

# 또는 환경 변수 설정
$env:AWS_ACCESS_KEY_ID = "YOUR_ACCESS_KEY"
$env:AWS_SECRET_ACCESS_KEY = "YOUR_SECRET_KEY"
$env:AWS_DEFAULT_REGION = "ap-northeast-2"
```

### 2. Terraform 상태 확인
```bash
cd environments/network-layer
terraform state list
terraform state show module.vpc_seoul
terraform state show module.vpc_us
```

### 3. App Layer 배포 준비
```bash
cd environments/app-layer/bedrock-rag
terraform init
terraform plan
```

### 4. On-Premises DNS 설정 (필수)
Route53 Resolver Endpoint IPs: `10.10.1.10`, `10.10.2.10`

**Windows DNS Server:**
```powershell
Add-DnsServerConditionalForwarderZone `
  -Name "aws.internal" `
  -MasterServers 10.10.1.10,10.10.2.10
```

**BIND DNS Server:**
```bash
zone "aws.internal" {
    type forward;
    forward only;
    forwarders { 10.10.1.10; 10.10.2.10; };
};
```

---

## 💰 현재 월별 비용

### Network Layer (배포됨)
| 항목 | 월별 비용 |
|------|---------|
| NAT Gateway (6개) | $194.40 |
| VPC Peering | $0 (같은 계정) |
| Route53 Resolver Endpoint | $180 |
| Route53 Hosted Zone | $0.50 |
| **Subtotal** | **$374.90** |

### App Layer (미배포)
| 항목 | 예상 월별 비용 |
|------|-------------|
| Lambda | $5-10 |
| S3 Storage | $46 |
| S3 Replication | $20 |
| OpenSearch Serverless | $700 |
| Bedrock Embedding | $10-20 |
| Bedrock Claude | $50-100 |
| CloudWatch | $8 |
| CloudTrail | $2 |
| **Subtotal** | **$841-906** |

**Total (Network Only): $374.90/month**  
**Total (Full Deployment): $1,216-1,281/month**

---

## 🔍 배포 검증 명령어

### Network Layer 검증
```bash
# VPC 확인
aws ec2 describe-vpcs --region ap-northeast-2
aws ec2 describe-vpcs --region us-east-1

# VPC Peering 확인
aws ec2 describe-vpc-peering-connections --region ap-northeast-2

# Route53 확인
aws route53 get-hosted-zone --id Z08304561GR4R43JANCB3
aws route53 list-resource-record-sets --hosted-zone-id Z08304561GR4R43JANCB3

# Route53 Resolver 확인
aws route53resolver describe-resolver-endpoints --region ap-northeast-2
```

### Terraform 상태 확인
```bash
cd environments/network-layer
terraform output
terraform state list
terraform state show module.vpc_seoul.aws_vpc.main
```

---

## 📝 주요 구성 파일

### Network Layer
- `environments/network-layer/main.tf` - VPC, Peering, Security Groups
- `environments/network-layer/providers.tf` - Multi-region providers
- `environments/network-layer/outputs.tf` - VPC/Subnet/SG IDs
- `environments/network-layer/variables.tf` - CIDR, AZ 설정

### App Layer
- `environments/app-layer/bedrock-rag/main.tf` - KMS, IAM, S3
- `environments/app-layer/bedrock-rag/lambda.tf` - Lambda 함수
- `environments/app-layer/bedrock-rag/opensearch-serverless.tf` - OpenSearch
- `environments/app-layer/bedrock-rag/bedrock-kb.tf` - Bedrock KB

### Modules
- `modules/network/vpc/` - VPC 모듈
- `modules/network/peering/` - VPC Peering 모듈
- `modules/network/security-groups/` - Security Groups 모듈
- `modules/network/route53-resolver/` - Route53 Resolver 모듈

---

## ⚠️ 알려진 문제 및 해결 방법

### 1. SSL Certificate Verification Failed
**증상:** AWS CLI 실행 시 SSL 인증서 오류
```
SSL validation failed for https://ap-northeast-2.signin.aws.amazon.com/v1/token
```

**해결:**
```powershell
# AWS CLI 자격증명 설정 필요
aws configure

# 또는 환경 변수 설정
$env:AWS_ACCESS_KEY_ID = "YOUR_KEY"
$env:AWS_SECRET_ACCESS_KEY = "YOUR_SECRET"
```

### 2. Route53 Resolver DNS 미응답
**증상:** On-premises에서 Route53 Resolver로 DNS 쿼리 실패

**해결:**
1. Security Group 확인: TCP/UDP 53 Ingress 활성화
2. VPN 연결 확인: On-premises ↔ Seoul VPC
3. Route53 Resolver 상태 확인: `rslvr-in-5b3dfa84cbeb4e66a`

### 3. VPC Peering 라우팅 미작동
**증상:** Seoul VPC에서 US VPC로 통신 불가

**해결:**
1. Route Table 확인: 10.1.0.0/16 → pcx-XXXXXXXXX
2. Security Group 확인: Ingress 규칙 확인
3. Network ACL 확인: Ingress/Egress 규칙 확인

---

## 📞 지원 및 문서

- **배포 가이드**: `docs/DEPLOYMENT_GUIDE.md`
- **운영 가이드**: `docs/OPERATIONAL_RUNBOOK.md`
- **테스트 가이드**: `docs/TESTING_GUIDE.md`
- **README**: `README.md`

---

**Last Updated:** 2026-02-20  
**Status:** ✅ Network Layer Complete, ⏳ App Layer Pending  
**Next Action:** Deploy App Layer (Bedrock RAG)

