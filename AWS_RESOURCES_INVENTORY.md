# AWS Resources Inventory - BOS-AI RAG Infrastructure

**Generated:** 2026-02-20  
**Account:** 533335672315  
**Last Sync:** From Terraform Configuration

---

## 📊 리소스 인벤토리

### 1. Seoul Region (ap-northeast-2)

#### VPC & Networking
```
VPC: vpc-0f759f00e5df658d1
├── Name: bos-ai-seoul-vpc-dev
├── CIDR: 10.0.0.0/16
├── DNS Hostnames: Enabled
├── DNS Support: Enabled
├── State: Active ✅
│
├── Public Subnets (3)
│   ├── Subnet 1: 10.0.1.0/24 (ap-northeast-2a)
│   ├── Subnet 2: 10.0.2.0/24 (ap-northeast-2b)
│   └── Subnet 3: 10.0.3.0/24 (ap-northeast-2c)
│
├── Private Subnets (3)
│   ├── Subnet 1: 10.0.11.0/24 (ap-northeast-2a)
│   ├── Subnet 2: 10.0.12.0/24 (ap-northeast-2b)
│   └── Subnet 3: 10.0.13.0/24 (ap-northeast-2c)
│
├── NAT Gateways (3)
│   ├── NAT GW 1: eipalloc-XXXXXXXXX (ap-northeast-2a)
│   ├── NAT GW 2: eipalloc-XXXXXXXXX (ap-northeast-2b)
│   └── NAT GW 3: eipalloc-XXXXXXXXX (ap-northeast-2c)
│
├── Route Tables (4)
│   ├── Public RT: rtb-XXXXXXXXX
│   │   └── Routes:
│   │       ├── 10.0.0.0/16 → Local
│   │       ├── 10.1.0.0/16 → pcx-06877f7ce046cd122 (VPC Peering)
│   │       └── 0.0.0.0/0 → igw-XXXXXXXXX (Internet Gateway)
│   │
│   ├── Private RT 1: rtb-XXXXXXXXX (ap-northeast-2a)
│   │   └── Routes:
│   │       ├── 10.0.0.0/16 → Local
│   │       ├── 10.1.0.0/16 → pcx-06877f7ce046cd122 (VPC Peering)
│   │       ├── 0.0.0.0/0 → NAT GW 1
│   │       └── 0.0.0.0/0 → vgw-XXXXXXXXX (VPN Gateway - propagated)
│   │
│   ├── Private RT 2: rtb-XXXXXXXXX (ap-northeast-2b)
│   │   └── Routes: (Similar to RT 1)
│   │
│   └── Private RT 3: rtb-XXXXXXXXX (ap-northeast-2c)
│       └── Routes: (Similar to RT 1)
│
└── VPN Gateway: vgw-XXXXXXXXX
    ├── Name: bos-ai-vpn-gateway-dev
    ├── ASN: 64512
    ├── State: Available ✅
    ├── Attachment: vpc-0f759f00e5df658d1 (Attached)
    └── Route Propagation: Enabled on all private RTs
```

#### Security Groups (Seoul)
```
Security Group 1: Lambda SG
├── ID: sg-XXXXXXXXX
├── Name: bos-ai-lambda-sg-dev
├── VPC: vpc-0f759f00e5df658d1
├── Ingress Rules:
│   └── None (Lambda doesn't receive inbound traffic)
└── Egress Rules:
    ├── All traffic to 10.0.0.0/16 (Seoul VPC)
    ├── All traffic to 10.1.0.0/16 (US VPC via Peering)
    └── All traffic to 0.0.0.0/0 (Internet via NAT)

Security Group 2: OpenSearch SG
├── ID: sg-XXXXXXXXX
├── Name: bos-ai-opensearch-sg-dev
├── VPC: vpc-0f759f00e5df658d1
├── Ingress Rules:
│   ├── HTTPS (443) from Lambda SG
│   └── HTTPS (443) from 10.1.0.0/16 (US VPC)
└── Egress Rules:
    └── All traffic

Security Group 3: VPC Endpoints SG
├── ID: sg-XXXXXXXXX
├── Name: bos-ai-vpc-endpoints-sg-dev
├── VPC: vpc-0f759f00e5df658d1
├── Ingress Rules:
│   ├── HTTPS (443) from 10.0.0.0/16 (Seoul VPC)
│   └── HTTPS (443) from 10.1.0.0/16 (US VPC)
└── Egress Rules:
    └── All traffic
```

---

### 2. US East Region (us-east-1)

#### VPC & Networking
```
VPC: vpc-0ed37ff82027c088f
├── Name: bos-ai-us-vpc-dev
├── CIDR: 10.1.0.0/16
├── DNS Hostnames: Enabled
├── DNS Support: Enabled
├── State: Active ✅
│
├── Public Subnets (3)
│   ├── Subnet 1: 10.1.1.0/24 (us-east-1a)
│   ├── Subnet 2: 10.1.2.0/24 (us-east-1b)
│   └── Subnet 3: 10.1.3.0/24 (us-east-1c)
│
├── Private Subnets (3)
│   ├── Subnet 1: 10.1.11.0/24 (us-east-1a)
│   ├── Subnet 2: 10.1.12.0/24 (us-east-1b)
│   └── Subnet 3: 10.1.13.0/24 (us-east-1c)
│
├── NAT Gateways (3)
│   ├── NAT GW 1: eipalloc-XXXXXXXXX (us-east-1a)
│   ├── NAT GW 2: eipalloc-XXXXXXXXX (us-east-1b)
│   └── NAT GW 3: eipalloc-XXXXXXXXX (us-east-1c)
│
├── Route Tables (4)
│   ├── Public RT: rtb-XXXXXXXXX
│   │   └── Routes:
│   │       ├── 10.1.0.0/16 → Local
│   │       ├── 10.0.0.0/16 → pcx-06877f7ce046cd122 (VPC Peering)
│   │       └── 0.0.0.0/0 → igw-XXXXXXXXX (Internet Gateway)
│   │
│   ├── Private RT 1: rtb-XXXXXXXXX (us-east-1a)
│   │   └── Routes:
│   │       ├── 10.1.0.0/16 → Local
│   │       ├── 10.0.0.0/16 → pcx-06877f7ce046cd122 (VPC Peering)
│   │       └── 0.0.0.0/0 → NAT GW 1
│   │
│   ├── Private RT 2: rtb-XXXXXXXXX (us-east-1b)
│   │   └── Routes: (Similar to RT 1)
│   │
│   └── Private RT 3: rtb-XXXXXXXXX (us-east-1c)
│       └── Routes: (Similar to RT 1)
│
└── VPC Endpoints (4) - To be deployed
    ├── Bedrock Runtime
    ├── Bedrock Agent Runtime
    ├── S3 Gateway Endpoint
    └── OpenSearch Serverless
```

#### Security Groups (US)
```
Security Group 1: Lambda SG
├── ID: sg-XXXXXXXXX
├── Name: bos-ai-lambda-sg-dev
├── VPC: vpc-0ed37ff82027c088f
├── Ingress Rules:
│   └── None
└── Egress Rules:
    ├── All traffic to 10.1.0.0/16 (US VPC)
    ├── All traffic to 10.0.0.0/16 (Seoul VPC via Peering)
    └── All traffic to 0.0.0.0/0 (Internet via NAT)

Security Group 2: OpenSearch SG
├── ID: sg-XXXXXXXXX
├── Name: bos-ai-opensearch-sg-dev
├── VPC: vpc-0ed37ff82027c088f
├── Ingress Rules:
│   ├── HTTPS (443) from Lambda SG
│   └── HTTPS (443) from 10.0.0.0/16 (Seoul VPC)
└── Egress Rules:
    └── All traffic

Security Group 3: VPC Endpoints SG
├── ID: sg-XXXXXXXXX
├── Name: bos-ai-vpc-endpoints-sg-dev
├── VPC: vpc-0ed37ff82027c088f
├── Ingress Rules:
│   ├── HTTPS (443) from 10.1.0.0/16 (US VPC)
│   └── HTTPS (443) from 10.0.0.0/16 (Seoul VPC)
└── Egress Rules:
    └── All traffic
```

---

### 3. Multi-Region Resources

#### VPC Peering
```
Peering Connection: pcx-06877f7ce046cd122
├── Name: bos-ai-seoul-us-peering-dev
├── Requester VPC: vpc-0f759f00e5df658d1 (Seoul)
├── Accepter VPC: vpc-0ed37ff82027c088f (US)
├── Status: Active ✅
├── Bandwidth: 10 Gbps
├── DNS Resolution:
│   ├── Seoul → US: Enabled ✅
│   └── US → Seoul: Disabled
└── Routes:
    ├── Seoul Private RTs: 10.1.0.0/16 → pcx-06877f7ce046cd122
    └── US Private RTs: 10.0.0.0/16 → pcx-06877f7ce046cd122
```

#### Route53 DNS
```
Private Hosted Zone: Z08304561GR4R43JANCB3
├── Name: aws.internal
├── Type: Private
├── Status: Active ✅
├── Associated VPCs:
│   ├── Seoul VPC: vpc-0f759f00e5df658d1 (ap-northeast-2) ✅
│   └── US VPC: vpc-0ed37ff82027c088f (us-east-1) ✅
└── Records: (To be added)
    ├── bedrock-runtime.us-east-1.aws.internal
    ├── s3.us-east-1.aws.internal
    └── opensearch.us-east-1.aws.internal

Route53 Resolver Inbound Endpoint: rslvr-in-5b3dfa84cbeb4e66a
├── Region: ap-northeast-2 (Seoul)
├── Status: Active ✅
├── IPs:
│   ├── 10.10.1.10 (ap-northeast-2a)
│   └── 10.10.2.10 (ap-northeast-2b)
├── Security Group: sg-02892b260ed8b09c4
│   ├── Ingress: DNS (TCP/UDP 53) from 10.0.0.0/8
│   └── Egress: All traffic
└── Purpose: On-premises DNS forwarding
```

---

## 🔐 Security & IAM (To be deployed)

### KMS Encryption
```
KMS Key: (To be created)
├── Name: bos-ai-kms-key-dev
├── Region: us-east-1
├── Key Policy:
│   ├── Root account access
│   ├── Bedrock KB role access
│   ├── Lambda role access
│   ├── OpenSearch role access
│   └── S3 replication role access
└── Rotation: Enabled (annual)
```

### IAM Roles & Policies
```
Role 1: Bedrock KB Role (To be created)
├── Name: bos-ai-bedrock-kb-role-dev
├── Trust Policy: Bedrock service
├── Policies:
│   ├── S3 read access (data source)
│   ├── OpenSearch write access (vector DB)
│   ├── KMS decrypt access
│   └── CloudWatch logs write

Role 2: Lambda Role (To be created)
├── Name: bos-ai-lambda-role-dev
├── Trust Policy: Lambda service
├── Policies:
│   ├── S3 read/write access
│   ├── Bedrock invoke access
│   ├── OpenSearch write access
│   ├── KMS decrypt access
│   ├── CloudWatch logs write
│   ├── VPC access (ENI management)
│   └── SQS DLQ access

Role 3: VPC Flow Logs Role (To be created)
├── Name: bos-ai-vpc-flow-logs-role-dev
├── Trust Policy: VPC Flow Logs service
└── Policies:
    └── CloudWatch logs write
```

---

## 💾 Storage (To be deployed)

### S3 Buckets
```
Bucket 1: bos-ai-documents-seoul
├── Region: ap-northeast-2
├── Versioning: Enabled
├── Encryption: KMS (bos-ai-kms-key)
├── Public Access: Blocked
├── Lifecycle:
│   ├── 90 days → Glacier
│   └── 180 days → Deep Archive
└── Replication: To bos-ai-documents-us

Bucket 2: bos-ai-documents-us
├── Region: us-east-1
├── Versioning: Enabled
├── Encryption: KMS (bos-ai-kms-key)
├── Public Access: Blocked
├── Lifecycle:
│   ├── 90 days → Glacier
│   └── 180 days → Deep Archive
└── Purpose: Replication target

Bucket 3: bos-ai-cloudtrail-logs
├── Region: us-east-1
├── Versioning: Enabled
├── Encryption: KMS (bos-ai-kms-key)
├── Public Access: Blocked
└── Purpose: CloudTrail logs

Bucket 4: bos-ai-cloudtrail-logs-access
├── Region: us-east-1
├── Purpose: S3 access logs for CloudTrail bucket
```

---

## 🤖 AI/ML Services (To be deployed)

### OpenSearch Serverless
```
Collection: bos-ai-vectors
├── Region: us-east-1
├── Type: Serverless
├── Capacity: 2 OCU (minimum)
├── Encryption: KMS (bos-ai-kms-key)
├── Network: VPC (10.1.0.0/16)
├── Security Group: sg-XXXXXXXXX (OpenSearch SG)
│
└── Index: bedrock-knowledge-base-index
    ├── Type: Vector
    ├── Dimensions: 1536 (Titan Embed)
    ├── Engine: HNSW
    ├── Mapping:
    │   ├── vector (1536-dim float)
    │   ├── text (keyword)
    │   ├── metadata (object)
    │   └── source (keyword)
    └── Settings:
        ├── ef_construction: 256
        └── ef_search: 512
```

### Bedrock Knowledge Base
```
Knowledge Base: bos-ai-knowledge-base
├── Region: us-east-1
├── Status: To be created
├── Data Source: S3 (bos-ai-documents-us)
├── Vector DB: OpenSearch Serverless
├── Embedding Model: Amazon Titan Embed Text v1
├── Chunking Strategy:
│   ├── Type: Semantic
│   ├── Max tokens: 300
│   └── Overlap: 20%
├── Metadata Filtering: Enabled
└── Sync: Automatic on S3 upload
```

---

## ⚙️ Compute (To be deployed)

### Lambda Function
```
Function: document-processor
├── Region: us-east-1
├── Runtime: Python 3.11
├── Memory: 1024 MB
├── Timeout: 300 seconds
├── Ephemeral Storage: 512 MB
├── VPC:
│   ├── Subnets: 3 (private, all AZs)
│   └── Security Group: sg-XXXXXXXXX (Lambda SG)
├── Environment Variables:
│   ├── BEDROCK_KB_ID: (from Bedrock KB)
│   ├── OPENSEARCH_ENDPOINT: (from OpenSearch)
│   └── KMS_KEY_ID: (from KMS)
├── Execution Role: bos-ai-lambda-role-dev
├── Layers: (Optional)
│   └── boto3, opensearch-py, etc.
├── Trigger: S3 (bos-ai-documents-us)
│   └── Events: s3:ObjectCreated:*
├── Dead Letter Queue: SQS (bos-ai-lambda-dlq)
└── X-Ray Tracing: Enabled
```

### SQS Dead Letter Queue
```
Queue: bos-ai-lambda-dlq
├── Region: us-east-1
├── Type: Standard
├── Message Retention: 14 days
├── Visibility Timeout: 300 seconds
├── Encryption: KMS (bos-ai-kms-key)
└── Purpose: Lambda failure handling
```

---

## 📊 Monitoring (To be deployed)

### CloudWatch Logs
```
Log Group 1: /aws/lambda/document-processor
├── Retention: 30 days
├── Encryption: KMS (bos-ai-kms-key)
└── Purpose: Lambda execution logs

Log Group 2: /aws/bedrock/knowledgebase/bos-ai-knowledge-base
├── Retention: 30 days
├── Encryption: KMS (bos-ai-kms-key)
└── Purpose: Bedrock KB sync logs

Log Group 3: /aws/opensearchserverless/bos-ai-vectors
├── Retention: 30 days
├── Encryption: KMS (bos-ai-kms-key)
└── Purpose: OpenSearch application logs

Log Group 4: /aws/vpc-flow-logs/seoul-vpc
├── Retention: 30 days
├── Encryption: KMS (bos-ai-kms-key)
└── Purpose: Seoul VPC traffic logs

Log Group 5: /aws/vpc-flow-logs/us-vpc
├── Retention: 30 days
├── Encryption: KMS (bos-ai-kms-key)
└── Purpose: US VPC traffic logs
```

### CloudWatch Alarms
```
Alarm 1: Lambda Errors
├── Metric: AWS/Lambda Errors
├── Function: document-processor
├── Threshold: > 5 errors in 5 minutes
├── Action: SNS notification
└── Severity: High

Alarm 2: Lambda Duration
├── Metric: AWS/Lambda Duration
├── Function: document-processor
├── Threshold: > 250 seconds (avg)
├── Action: SNS notification
└── Severity: Medium

Alarm 3: Lambda Throttles
├── Metric: AWS/Lambda Throttles
├── Function: document-processor
├── Threshold: > 0 throttles
├── Action: SNS notification
└── Severity: High
```

### CloudWatch Dashboard
```
Dashboard: bos-ai-dev-dashboard
├── Widgets:
│   ├── Lambda Invocations (graph)
│   ├── Lambda Errors (graph)
│   ├── Lambda Duration (graph)
│   ├── Lambda Throttles (number)
│   ├── OpenSearch Latency (graph)
│   ├── OpenSearch Indexing Rate (graph)
│   ├── S3 Replication Status (number)
│   ├── Bedrock KB Sync Status (number)
│   ├── VPC Flow Logs (graph)
│   └── Cost Trend (graph)
└── Refresh: 1 minute
```

---

## 🔍 Audit & Compliance (To be deployed)

### CloudTrail
```
Trail: bos-ai-cloudtrail
├── Region: Multi-region
├── S3 Bucket: bos-ai-cloudtrail-logs
├── Log File Validation: Enabled
├── KMS Encryption: bos-ai-kms-key
├── CloudWatch Logs: /aws/cloudtrail/bos-ai
├── Events:
│   ├── Management events: All
│   ├── Data events: S3, Lambda
│   └── Insights: Enabled
└── Retention: Indefinite (S3 Lifecycle)
```

### AWS Budgets
```
Budget: bos-ai-dev-monthly-budget
├── Type: Monthly
├── Limit: $1,500 (adjustable)
├── Alerts:
│   ├── 80% threshold: Email
│   ├── 100% threshold: Email
│   └── 120% threshold: Email
└── Recipients: [your-email@example.com]
```

---

## 📈 Resource Summary

### Deployed Resources (Network Layer)
| Category | Count | Status |
|----------|-------|--------|
| VPCs | 2 | ✅ |
| Subnets | 12 | ✅ |
| NAT Gateways | 6 | ✅ |
| Elastic IPs | 6 | ✅ |
| Route Tables | 8 | ✅ |
| Security Groups | 6 | ✅ |
| VPC Peering | 1 | ✅ |
| Route53 Hosted Zone | 1 | ✅ |
| Route53 Resolver | 1 | ✅ |
| VPN Gateway | 1 | ✅ |
| **Total** | **44** | **✅** |

### Pending Resources (App Layer)
| Category | Count | Status |
|----------|-------|--------|
| KMS Keys | 1 | ⏳ |
| IAM Roles | 3 | ⏳ |
| IAM Policies | 8 | ⏳ |
| S3 Buckets | 4 | ⏳ |
| Lambda Functions | 1 | ⏳ |
| SQS Queues | 1 | ⏳ |
| OpenSearch Collections | 1 | ⏳ |
| Bedrock KB | 1 | ⏳ |
| CloudWatch Logs | 5 | ⏳ |
| CloudWatch Alarms | 3 | ⏳ |
| CloudWatch Dashboard | 1 | ⏳ |
| CloudTrail | 1 | ⏳ |
| AWS Budgets | 1 | ⏳ |
| **Total** | **31** | **⏳** |

**Grand Total: 75 resources (44 deployed, 31 pending)**

---

## 🔗 Resource Dependencies

```
Global Backend
├── S3 Terraform State
└── DynamoDB State Lock

Network Layer
├── Seoul VPC
│   ├── Public Subnets (3)
│   ├── Private Subnets (3)
│   ├── NAT Gateways (3)
│   ├── Route Tables (4)
│   ├── Security Groups (3)
│   ├── VPN Gateway
│   └── Route53 Resolver Endpoint
│
├── US VPC
│   ├── Public Subnets (3)
│   ├── Private Subnets (3)
│   ├── NAT Gateways (3)
│   ├── Route Tables (4)
│   ├── Security Groups (3)
│   └── VPC Endpoints (4)
│
└── VPC Peering
    └── Route53 Private Hosted Zone

App Layer (Depends on Network Layer)
├── KMS Key
├── IAM Roles & Policies
├── S3 Buckets
│   └── Cross-Region Replication
├── Lambda Function
│   ├── VPC Configuration
│   ├── Security Group
│   └── IAM Role
├── OpenSearch Serverless
│   ├── VPC Configuration
│   ├── Security Group
│   └── KMS Encryption
├── Bedrock Knowledge Base
│   ├── S3 Data Source
│   ├── OpenSearch Vector DB
│   └── IAM Role
├── CloudWatch Logs
├── CloudWatch Alarms
├── CloudWatch Dashboard
├── CloudTrail
└── AWS Budgets
```

---

**Last Updated:** 2026-02-20  
**Status:** Network Layer Complete ✅, App Layer Pending ⏳

