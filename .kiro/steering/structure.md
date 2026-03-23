# Project Structure

```
.
├── environments/                    # Terraform root configurations (deploy from here)
│   ├── network-layer/              # VPCs, Transit Gateway, VPN, Peering, Route53, Security Groups
│   ├── app-layer/                  # Application-level resources
│   │   └── bedrock-rag/           # Bedrock KB, OpenSearch, Lambda, API Gateway, S3, DynamoDB
│   ├── global/                     # Shared global resources
│   │   ├── backend/               # S3 + DynamoDB Terraform backend bootstrap
│   │   └── iam/                   # Global IAM configuration
│   └── kiro-subscription/         # Kiro subscription management (EventBridge, Lambda, Secrets)
│
├── modules/                        # Reusable Terraform modules
│   ├── network/                   # VPC, Transit Gateway, Peering, Route53 Resolver, Security Groups, NACLs
│   ├── ai-workload/               # Bedrock RAG, S3 pipeline (Lambda + S3)
│   ├── security/                  # CloudTrail, IAM roles, KMS, VPC Endpoints
│   ├── monitoring/                # CloudWatch (alarms, dashboards, logs), VPC Flow Logs
│   └── cost-management/           # AWS Budgets
│
├── lambda/                         # Lambda function source code
│   └── document-processor/        # Python 3.12 — S3 event → document chunking → Bedrock ingestion
│
├── mcp-bridge/                     # Node.js MCP SSE bridge (Obot ↔ RAG API Gateway)
│
├── policies/                       # OPA/Rego policy files
│   ├── security.rego              # S3, IAM, KMS, VPC, Lambda, encryption rules
│   ├── cost.rego                  # Cost-related policies
│   └── compliance.rego            # Compliance checks
│
├── scripts/                        # Shell/PowerShell utility scripts
│   ├── terraform-validate.sh      # Cross-environment Terraform validation
│   ├── run-policy-tests.sh        # OPA policy test runner
│   ├── run-integration-tests.sh   # Integration test runner
│   └── ...                        # VPN checks, backup, deployment prep
│
├── tests/                          # Go test suite
│   ├── unit/                      # Unit tests
│   ├── integration/               # Integration tests (AWS resource verification)
│   ├── properties/                # Property-based tests (gopter)
│   └── go.mod                     # Go module definition
│
├── docs/                           # Operational documentation
│   ├── DEPLOYMENT_GUIDE.md        # Full deployment guide
│   ├── OPERATIONAL_RUNBOOK.md     # Ops runbook and troubleshooting
│   ├── naming-conventions.md      # AWS resource naming rules
│   ├── tagging-strategy.md        # Required/recommended tags
│   └── ...                        # Network, security, DNS, VPN guides
│
├── Report/                         # Deployment reports, test results, training materials
├── backups/                        # Terraform state and config backups
├── .tflint.hcl                     # TFLint configuration (project root)
└── .gitignore                      # Excludes .terraform, tfstate, tfvars, secrets, logs
```

## Deployment Layers

Infrastructure is deployed in order:
1. `environments/global/backend/` — Terraform backend (S3 + DynamoDB)
2. `environments/network-layer/` — VPCs, Transit Gateway, VPN, Peering, DNS
3. `environments/app-layer/bedrock-rag/` — AI workload (Lambda, Bedrock, OpenSearch, API GW)

## Naming Conventions

AWS resources follow: `{resource-type}-{service/purpose}-{project}-{region}-{environment}-{sequence}{az}`
- Example: `vpc-bos-ai-seoul-prod-01`, `sg-opensearch-bos-ai-seoul-prod`, `lambda-document-processor-seoul-prod`
- Terraform resources use snake_case
- Required tags on all resources: Name, Project, Environment, ManagedBy, Layer

## Network Layout

| VPC | CIDR | Region | Purpose |
|-----|------|--------|---------|
| Logging Pipeline | 10.200.0.0/16 | Seoul | Security logging, monitoring |
| BOS-AI Frontend | 10.10.0.0/16 | Seoul | Lambda, API GW, VPC Endpoints |
| BOS-AI Backend | 10.20.0.0/16 | Virginia | Bedrock, OpenSearch, S3 |
| On-premises | 192.128.0.0/16 | — | Corporate network |
