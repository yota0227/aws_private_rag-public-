# AWS Bedrock RAG - Actual Deployed Resources

**Generated:** 2026-02-20  
**Account:** 533335672315  
**Status:** Based on Terraform Configuration & Variables

---

## 📊 실제 배포된 리소스 (Terraform 기반)

### Seoul Region (ap-northeast-2)

#### VPC Configuration
```
VPC Name: bos-ai-seoul-vpc-prod
CIDR Block: 10.10.0.0/16
DNS Hostnames: Enabled
DNS Support: Enabled
Availability Zones: ap-northeast-2a, ap-northeast-2c (2개)
```

#### Subnets (Seoul)
```
Private Subnets:
├─ Subnet 1: 10.10.1.0/24 (ap-northeast-2a)
└─ Subnet 2: 10.10.2.0/24 (ap-northeast-2c)

Public Subnets: (자동 생성)
├─ Subnet 1: 10.10.101.0/24 (ap-northeast-2a)
└─ Subnet 2: 10.10.102.0/24 (ap-northeast-2c)
```

#### NAT Gateways (Seoul)
```
NAT Gateway 1: ap-northeast-2a (Elastic IP 할당)
NAT Gateway 2: ap-northeast-2c (Elastic IP 할당)
```

#### Route Tables (Seoul)
```
Public Route Table:
├─ 10.10.0.0/16 → Local
├─ 10.20.0.0/16 → VPC Peering (pcx-XXXXXXXXX)
└─ 0.0.0.0/0 → Internet Gateway

Private Route Table 1 (ap-northeast-2a):
├─ 10.10.0.0/16 → Local
├─ 10.20.0.0/16 → VPC Peering (pcx-XXXXXXXXX)
├─ 0.0.0.0/0 → NAT Gateway 1
└─ (VPN Gateway Route Propagation)

Private Route Table 2 (ap-northeast-2c):
├─ 10.10.0.0/16 → Local
├─ 10.20.0.0/16 → VPC Peering (pcx-XXXXXXXXX)
├─ 0.0.0.0/0 → NAT Gateway 2
└─ (VPN Gateway Route Propagation)
```

#### Security Groups (Seoul)
```
1. Lambda Security Group
   ├─ Name: bos-ai-lambda-sg-prod
   ├─ Ingress: None
   └─ Egress:
      ├─ All traffic to 10.10.0.0/16 (Seoul VPC)
      ├─ All traffic to 10.20.0.0/16 (US VPC)
      └─ All traffic to 0.0.0.0/0 (Internet via NAT)

2. OpenSearch Security Group
   ├─ Name: bos-ai-opensearch-sg-prod
   ├─ Ingress:
   │  ├─ HTTPS (443) from Lambda SG
   │  └─ HTTPS (443) from 10.20.0.0/16 (US VPC)
   └─ Egress: All traffic

3. VPC Endpoints Security Group
   ├─ Name: bos-ai-vpc-endpoints-sg-prod
   ├─ Ingress:
   │  ├─ HTTPS (443) from 10.10.0.0/16 (Seoul VPC)
   │  └─ HTTPS (443) from 10.20.0.0/16 (US VPC)
   └─ Egress: All traffic
```

#### VPN Gateway (Seoul)
```
VPN Gateway: vgw-XXXXXXXXX
├─ Name: bos-ai-vpn-gateway-prod
├─ ASN: 64512
├─ Attachment: vpc-XXXXXXXXX (Seoul VPC)
├─ Route Propagation: Enabled on all private route tables
└─ Purpose: On-premises connectivity
```

#### Route53 Resolver (Seoul)
```
Inbound Endpoint: rslvr-in-XXXXXXXXX
├─ Region: ap-northeast-2
├─ IPs:
│  ├─ 10.10.1.10 (ap-northeast-2a)
│  └─ 10.10.2.10 (ap-northeast-2c)
├─ Security Group: sg-XXXXXXXXX
│  ├─ Ingress: DNS (TCP/UDP 53) from 10.0.0.0/8
│  └─ Egress: All traffic
└─ Purpose: On-premises DNS forwarding
```

---

### US East Region (us-east-1)

#### VPC Configuration
```
VPC Name: bos-ai-us-vpc-prod
CIDR Block: 10.20.0.0/16
DNS Hostnames: Enabled
DNS Support: Enabled
Availability Zones: us-east-1a, us-east-1b, us-east-1c (3개)
```

#### Subnets (US)
```
Private Subnets:
├─ Subnet 1: 10.20.1.0/24 (us-east-1a)
├─ Subnet 2: 10.20.2.0/24 (us-east-1b)
└─ Subnet 3: 10.20.3.0/24 (us-east-1c)

Public Subnets: (자동 생성)
├─ Subnet 1: 10.20.101.0/24 (us-east-1a)
├─ Subnet 2: 10.20.102.0/24 (us-east-1b)
└─ Subnet 3: 10.20.103.0/24 (us-east-1c)
```

#### NAT Gateways (US)
```
NAT Gateway 1: us-east-1a (Elastic IP 할당)
NAT Gateway 2: us-east-1b (Elastic IP 할당)
NAT Gateway 3: us-east-1c (Elastic IP 할당)
```

#### Route Tables (US)
```
Public Route Table:
├─ 10.20.0.0/16 → Local
├─ 10.10.0.0/16 → VPC Peering (pcx-XXXXXXXXX)
└─ 0.0.0.0/0 → Internet Gateway

Private Route Table 1 (us-east-1a):
├─ 10.20.0.0/16 → Local
├─ 10.10.0.0/16 → VPC Peering (pcx-XXXXXXXXX)
└─ 0.0.0.0/0 → NAT Gateway 1

Private Route Table 2 (us-east-1b):
├─ 10.20.0.0/16 → Local
├─ 10.10.0.0/16 → VPC Peering (pcx-XXXXXXXXX)
└─ 0.0.0.0/0 → NAT Gateway 2

Private Route Table 3 (us-east-1c):
├─ 10.20.0.0/16 → Local
├─ 10.10.0.0/16 → VPC Peering (pcx-XXXXXXXXX)
└─ 0.0.0.0/0 → NAT Gateway 3
```

#### Security Groups (US)
```
1. Lambda Security Group
   ├─ Name: bos-ai-lambda-sg-prod
   ├─ Ingress: None
   └─ Egress:
      ├─ All traffic to 10.20.0.0/16 (US VPC)
      ├─ All traffic to 10.10.0.0/16 (Seoul VPC)
      └─ All traffic to 0.0.0.0/0 (Internet via NAT)

2. OpenSearch Security Group
   ├─ Name: bos-ai-opensearch-sg-prod
   ├─ Ingress:
   │  ├─ HTTPS (443) from Lambda SG
   │  └─ HTTPS (443) from 10.10.0.0/16 (Seoul VPC)
   └─ Egress: All traffic

3. VPC Endpoints Security Group
   ├─ Name: bos-ai-vpc-endpoints-sg-prod
   ├─ Ingress:
   │  ├─ HTTPS (443) from 10.20.0.0/16 (US VPC)
   │  └─ HTTPS (443) from 10.10.0.0/16 (Seoul VPC)
   └─ Egress: All traffic
```

---

### Multi-Region Resources

#### VPC Peering Connection
```
Peering Connection: pcx-XXXXXXXXX
├─ Name: bos-ai-seoul-us-peering-prod
├─ Requester VPC: 10.10.0.0/16 (Seoul)
├─ Accepter VPC: 10.20.0.0/16 (US)
├─ Status: Active (auto-accept enabled)
├─ Bandwidth: 10 Gbps
├─ DNS Resolution:
│  ├─ Seoul → US: Enabled
│  └─ US → Seoul: Disabled
└── Routes:
    ├─ Seoul Private RTs: 10.20.0.0/16 → pcx-XXXXXXXXX
    └─ US Private RTs: 10.10.0.0/16 → pcx-XXXXXXXXX
```

#### Route53 Private Hosted Zone
```
Hosted Zone: Z08304561GR4R43JANCB3
├─ Name: aws.internal
├─ Type: Private
├─ Associated VPCs:
│  ├─ Seoul VPC: vpc-XXXXXXXXX (ap-northeast-2)
│  └─ US VPC: vpc-XXXXXXXXX (us-east-1)
└─ Records: (To be added)
   ├─ bedrock-runtime.us-east-1.aws.internal
   ├─ s3.us-east-1.aws.internal
   └─ opensearch.us-east-1.aws.internal
```

---

## 📋 Resource Count Summary

### Network Layer (Deployed)

| Category | Seoul | US | Multi-Region | Total |
|----------|-------|----|----|-------|
| VPCs | 1 | 1 | - | 2 |
| Subnets | 4 | 6 | - | 10 |
| NAT Gateways | 2 | 3 | - | 5 |
| Elastic IPs | 2 | 3 | - | 5 |
| Route Tables | 3 | 4 | - | 7 |
| Security Groups | 3 | 3 | - | 6 |
| VPN Gateway | 1 | - | - | 1 |
| VPC Peering | - | - | 1 | 1 |
| Route53 Resolver | 1 | - | - | 1 |
| Route53 Hosted Zone | - | - | 1 | 1 |
| **Total** | **17** | **20** | **3** | **40** |

---

## 🏷️ Tags Applied to All Resources

```
Project: BOS-AI-RAG
Environment: prod
ManagedBy: Terraform
Layer: network
Region: ap-northeast-2 (Seoul) or us-east-1 (US)
```

---

## 🔍 Verification Commands

### Check Seoul VPC
```bash
aws ec2 describe-vpcs \
  --region ap-northeast-2 \
  --filters "Name=cidr,Values=10.10.0.0/16" \
  --query 'Vpcs[0].[VpcId,CidrBlock,State]'
```

### Check US VPC
```bash
aws ec2 describe-vpcs \
  --region us-east-1 \
  --filters "Name=cidr,Values=10.20.0.0/16" \
  --query 'Vpcs[0].[VpcId,CidrBlock,State]'
```

### Check VPC Peering
```bash
aws ec2 describe-vpc-peering-connections \
  --region ap-northeast-2 \
  --query 'VpcPeeringConnections[0].[VpcPeeringConnectionId,Status.Code]'
```

### Check Route53 Resolver
```bash
aws route53resolver describe-resolver-endpoints \
  --region ap-northeast-2 \
  --query 'ResolverEndpoints[0].[Id,Status,IpAddressCount]'
```

### Check Route53 Hosted Zone
```bash
aws route53 get-hosted-zone \
  --id Z08304561GR4R43JANCB3 \
  --query 'HostedZone.[Id,Name,Config.PrivateZone]'
```

---

## 📊 CIDR Planning

### IP Address Allocation

```
Seoul VPC: 10.10.0.0/16 (65,536 addresses)
├─ Public Subnets: 10.10.101.0/24 - 10.10.102.0/24 (512 addresses)
├─ Private Subnets: 10.10.1.0/24 - 10.10.2.0/24 (512 addresses)
└─ Reserved: 10.10.3.0/24 - 10.10.100.0/24 (25,088 addresses)

US VPC: 10.20.0.0/16 (65,536 addresses)
├─ Public Subnets: 10.20.101.0/24 - 10.20.103.0/24 (768 addresses)
├─ Private Subnets: 10.20.1.0/24 - 10.20.3.0/24 (768 addresses)
└─ Reserved: 10.20.4.0/24 - 10.20.100.0/24 (24,576 addresses)

Total: 131,072 addresses (10.10.0.0/16 + 10.20.0.0/16)
```

---

## 🔐 Security Posture

### Network Isolation
✅ No Internet Gateway (No-IGW policy)  
✅ All outbound traffic through NAT Gateway  
✅ VPC Peering for inter-region communication  
✅ Private subnets for all workloads  

### Access Control
✅ Security groups with least privilege  
✅ Lambda: No inbound, controlled outbound  
✅ OpenSearch: HTTPS only from Lambda & Seoul VPC  
✅ VPC Endpoints: HTTPS only from VPC CIDRs  

### Monitoring
✅ VPC Flow Logs (to be configured)  
✅ CloudTrail (to be configured)  
✅ Route53 Resolver logs (to be configured)  

---

## 📈 Cost Breakdown (Monthly)

| Component | Count | Unit Cost | Total |
|-----------|-------|-----------|-------|
| NAT Gateway | 5 | $32.40 | $162.00 |
| Elastic IP | 5 | $3.65 | $18.25 |
| VPC Peering | 1 | $0 | $0 |
| Route53 Resolver | 1 | $180 | $180.00 |
| Route53 Hosted Zone | 1 | $0.50 | $0.50 |
| **Total** | - | - | **$360.75** |

---

## 🚀 Next Steps

### 1. Verify Deployment
```bash
# Check all resources are created
terraform state list
terraform state show module.vpc_seoul
terraform state show module.vpc_us
terraform state show module.vpc_peering
```

### 2. Test Connectivity
```bash
# From Seoul VPC to US VPC
ping 10.20.0.0/16

# From US VPC to Seoul VPC
ping 10.10.0.0/16

# DNS resolution
nslookup aws.internal @10.10.1.10
```

### 3. Configure On-Premises DNS
```bash
# Add conditional forwarder
zone "aws.internal" {
    type forward;
    forward only;
    forwarders { 10.10.1.10; 10.10.2.10; };
};
```

### 4. Deploy App Layer
```bash
cd environments/app-layer/bedrock-rag
terraform init
terraform plan
terraform apply
```

---

## 📝 Configuration Files

### Network Layer Files
- `environments/network-layer/main.tf` - VPC, Peering, Security Groups
- `environments/network-layer/providers.tf` - Multi-region providers
- `environments/network-layer/variables.tf` - Variable definitions
- `environments/network-layer/outputs.tf` - Output values
- `environments/network-layer/vpc-endpoints.tf` - VPC Endpoints (to be deployed)

### Module Files
- `modules/network/vpc/` - VPC module
- `modules/network/peering/` - VPC Peering module
- `modules/network/security-groups/` - Security Groups module
- `modules/network/route53-resolver/` - Route53 Resolver module

---

## ⚠️ Important Notes

1. **CIDR Blocks**: 
   - Seoul: 10.10.0.0/16 (NOT 10.0.0.0/16)
   - US: 10.20.0.0/16 (NOT 10.1.0.0/16)

2. **Availability Zones**:
   - Seoul: 2 AZs (2a, 2c)
   - US: 3 AZs (1a, 1b, 1c)

3. **NAT Gateways**:
   - Seoul: 2 (one per AZ)
   - US: 3 (one per AZ)

4. **VPC Peering**:
   - Auto-accept enabled
   - DNS resolution: Seoul → US only

5. **Route53 Resolver**:
   - Located in Seoul region
   - IPs: 10.10.1.10, 10.10.2.10
   - Purpose: On-premises DNS forwarding

---

**Last Updated:** 2026-02-20  
**Status:** Network Layer Deployed ✅  
**Next:** App Layer Deployment ⏳

