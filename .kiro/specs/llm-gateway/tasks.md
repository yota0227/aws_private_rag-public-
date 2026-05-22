# Implementation Plan: LLM Gateway

## Overview

LLM Gateway 인프라를 Terraform으로 프로비저닝한다. 3개 EC2 인스턴스(LiteLLM, MCP Server, Squid)를 2개 VPC에 분산 배치하고, API Gateway 경로, DNS, IAM, Security Group, Secrets Manager, 모니터링, 백업을 구성한다. 기존 인프라 보호를 위해 서비스별 별도 .tf 파일로 분리한다.

## Tasks

- [x] 1. Secrets Manager 및 공통 리소스
  - [x] 1.1 Create Secrets Manager secrets and SNS topic in `environments/app-layer/bedrock-rag/llm-gateway-litellm.tf`
    - Create three `aws_secretsmanager_secret` + `aws_secretsmanager_secret_version` with `random_password` resources
    - Secret names: `llm-gateway/litellm-master-key` (32 chars), `llm-gateway/mcp-api-key` (32 chars), `llm-gateway/postgres-password` (24 chars)
    - Create `aws_sns_topic` "llm-gateway-alerts" for alarm notifications
    - Define common `locals` block with tags (Project=BOS-AI, Environment=prod, ManagedBy=terraform, Layer=app)
    - _Requirements: 16.1, 16.2, 16.3, 23.10_

- [x] 2. LiteLLM EC2 인스턴스 (Logging VPC)
  - [x] 2.1 Create IAM role, instance profile, and policies for LiteLLM EC2 in `environments/app-layer/bedrock-rag/llm-gateway-litellm.tf`
    - Create `aws_iam_role` with ec2.amazonaws.com trust policy
    - Attach policies: Bedrock InvokeModel (us-east-1), SecretsManager GetSecretValue (ap-northeast-2, llm-gateway/*), CloudWatch Logs, S3 PutObject (s3-bos-ai-backups-seoul-prod/llm-gateway/postgres/*), AmazonSSMManagedInstanceCore
    - Create `aws_iam_instance_profile`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 24.4_

  - [x] 2.2 Create Security Group for LiteLLM EC2 in `environments/app-layer/bedrock-rag/llm-gateway-litellm.tf`
    - Inbound TCP 4000 from 10.10.0.0/16 (Frontend VPC / API GW)
    - Inbound TCP 4000 from 192.128.0.0/16 (On-prem direct TGW)
    - Outbound TCP 443 to 0.0.0.0/0 (OpenAI NAT, Bedrock TGW)
    - Associate with Logging VPC
    - _Requirements: 13.1, 13.2, 13.3, 13.5_

  - [x] 2.3 Create LiteLLM EC2 instance with Launch Template in `environments/app-layer/bedrock-rag/llm-gateway-litellm.tf`
    - Instance type: t3.medium, Amazon Linux 2023 AMI, Logging VPC private subnet
    - No public IP, IMDSv2 required (http_tokens = "required")
    - Root EBS 20GB gp3 encrypted, additional data EBS 50GB gp3 encrypted at /data
    - Launch Template with version tracking
    - User Data script: install Docker + Docker Compose, retrieve secrets from Secrets Manager (retry 3x exponential backoff), create docker-compose.yml and config.yaml, mount /data volume, start containers, install CloudWatch Agent, configure pg_dump cron at 03:00 KST, log to /var/log/user-data.log
    - Docker Compose: LiteLLM container (v1.x.x pinned, port 4000, memory 3G), PostgreSQL 16-alpine (no port binding, memory 1G, /data/postgres volume)
    - LiteLLM config.yaml with GPT models (gpt-4o, gpt-4o-mini, o3-mini) and Bedrock models (claude-3-5-sonnet, claude-3-haiku, claude-3-opus, titan-embed-text-v2)
    - Backup script at /data/scripts/backup-postgres.sh (pg_dump + gzip + S3 upload + 7-day local retention)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 2.4, 2.5, 3.3, 16.4, 16.5, 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 22.1, 22.2, 22.3, 22.4, 23.9, 24.1, 24.2, 24.3, 25.4, 26.1, 26.6_

  - [x] 2.4 Create CloudWatch Log Group and Alarms for LiteLLM in `environments/app-layer/bedrock-rag/llm-gateway-litellm.tf`
    - Log Group `/llm-gateway/litellm` with 30-day retention
    - Alarm: CPUUtilization > 80% for 5 minutes → SNS topic
    - Alarm: StatusCheckFailed > 0 for 2 consecutive periods → SNS topic
    - Alarm: S3 backup age > 25 hours (custom metric or Lambda check)
    - _Requirements: 23.1, 23.6, 24.6_

- [x] 3. MCP Server EC2 인스턴스 (Frontend VPC)
  - [x] 3.1 Create IAM role, instance profile, and policies for MCP EC2 in `environments/app-layer/bedrock-rag/llm-gateway-mcp.tf`
    - Create `aws_iam_role` with ec2.amazonaws.com trust policy
    - Attach policies: Lambda InvokeFunction (lambda-document-processor-seoul-prod), SecretsManager GetSecretValue (ap-northeast-2, llm-gateway/*), CloudWatch Logs, AmazonSSMManagedInstanceCore
    - Create `aws_iam_instance_profile`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x] 3.2 Create Security Group for MCP EC2 in `environments/app-layer/bedrock-rag/llm-gateway-mcp.tf`
    - Inbound TCP 3000 from 10.10.0.0/16 (Frontend VPC)
    - Outbound TCP 443 to 0.0.0.0/0 (Lambda VPC Endpoint, Secrets Manager)
    - Associate with Frontend VPC (vpc-0a118e1bf21d0c057)
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 3.3 Create MCP Server EC2 instance with Launch Template in `environments/app-layer/bedrock-rag/llm-gateway-mcp.tf`
    - Instance type: t3.small, Amazon Linux 2023 AMI, Frontend VPC private subnet
    - No public IP, IMDSv2 required
    - Root EBS 20GB gp3 encrypted
    - Launch Template with version tracking
    - User Data script: install Node.js 20, retrieve MCP API key from Secrets Manager (retry 3x), deploy MCP server (port 3000, Streamable HTTP, 17 tools), configure systemd service with ExecStartPre health check, install CloudWatch Agent, log to /var/log/user-data.log
    - MCP Server implements: 9 RAG/Archive tools, 4 Neptune tools, 4 Claims/HDD tools via Lambda invoke
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.10, 16.4, 16.5, 22.1, 22.2, 22.3, 22.4, 23.9, 26.4, 26.6_

  - [x] 3.4 Create CloudWatch Log Group and Alarms for MCP Server in `environments/app-layer/bedrock-rag/llm-gateway-mcp.tf`
    - Log Group `/llm-gateway/mcp-server` with 30-day retention
    - Alarm: CPUUtilization > 80% for 5 minutes → SNS topic
    - Alarm: StatusCheckFailed > 0 for 2 consecutive periods → SNS topic
    - _Requirements: 23.2, 23.7_

- [x] 4. Checkpoint - Verify app-layer Terraform configuration
  - Ensure `terraform validate` and `tflint` pass for `environments/app-layer/bedrock-rag/`
  - Ensure `terraform plan` shows no destructive changes to existing resources
  - Ask the user if questions arise.

- [x] 5. API Gateway 경로 추가
  - [x] 5.1 Create API Gateway routes in `environments/app-layer/bedrock-rag/llm-gateway-apigw.tf`
    - Reference existing `private-rag-api-prod` REST API via data source
    - Create `/llm/{proxy+}` resource with ANY method → HTTP_PROXY integration to LiteLLM_EC2 private IP:4000
    - Create `/mcp/{proxy+}` resource with ANY method → HTTP_PROXY integration to MCP_EC2 private IP:3000
    - Create `aws_api_gateway_deployment` to redeploy prod stage
    - Preserve all existing API Gateway resources (additive only)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 21.1_

- [x] 6. Route53 DNS 레코드
  - [x] 6.1 Create Route53 DNS records in `environments/app-layer/bedrock-rag/llm-gateway-dns.tf`
    - A record (Alias) for `llm.corp.bos-semi.com` → execute-api VPC Endpoint
    - A record (Alias) for `mcp.corp.bos-semi.com` → execute-api VPC Endpoint
    - Use existing PHZ (zone ID: Z04599582HCRH2UPCSS34), no new zone creation
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 7. Squid Forward Proxy EC2 (Logging VPC, network-layer)
  - [x] 7.1 Create IAM role and Security Group for Squid EC2 in `environments/network-layer/llm-gateway-squid.tf`
    - IAM role with ec2.amazonaws.com trust: CloudWatch Logs + AmazonSSMManagedInstanceCore only
    - Security Group: Inbound TCP 3128 from 192.128.0.0/16, Inbound TCP 22 from 192.128.0.0/16, Outbound TCP 443 to 0.0.0.0/0, Outbound UDP/TCP 53 to 0.0.0.0/0
    - Associate with Logging VPC
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x] 7.2 Create Squid EC2 instance with Launch Template in `environments/network-layer/llm-gateway-squid.tf`
    - Instance type: t3.micro, Amazon Linux 2023 AMI, Logging VPC private subnet
    - No public IP, IMDSv2 required
    - Root EBS 20GB gp3 encrypted
    - Launch Template with version tracking
    - User Data script: install Squid, configure squid.conf (domain whitelist: *.kiro.dev, api.openai.com, api.anthropic.com, *.amazoncognito.com; source ACL 192.128.0.0/16; CONNECT port 443 only; strip X-Forwarded-For, disable Via), validate with `squid -k parse`, install CloudWatch Agent, log to /var/log/user-data.log
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 22.1, 22.2, 22.3, 22.4, 22.6, 23.9, 26.5, 26.6_

  - [x] 7.3 Create CloudWatch Log Group and Alarms for Squid in `environments/network-layer/llm-gateway-squid.tf`
    - Log Group `/llm-gateway/squid` with 30-day retention
    - Alarm: CPUUtilization > 70% for 5 minutes → SNS topic
    - Alarm: StatusCheckFailed > 0 for 2 consecutive periods → SNS topic
    - _Requirements: 23.3, 23.8_

- [x] 8. Frontend VPC 네트워크 경로
  - [x] 8.1 Add default route to Frontend VPC in `environments/network-layer/llm-gateway-routes.tf`
    - Add route 0.0.0.0/0 → Transit Gateway to Frontend VPC private route table
    - Reference existing TGW via data source, verify attachments are active
    - Preserve all existing routes (additive only, use `aws_route` resource not inline)
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 9. Checkpoint - Verify network-layer Terraform configuration
  - Ensure `terraform validate` and `tflint` pass for `environments/network-layer/`
  - Ensure `terraform plan` shows no destructive changes to existing resources
  - Verify existing TGW route propagation covers Logging VPC → Frontend VPC path
  - Ask the user if questions arise.

- [ ] 12. Nginx Reverse Proxy EC2 (Frontend VPC) — NEW
  - [ ] 12.1 Create Nginx EC2 with IAM, SG, Launch Template in `environments/app-layer/bedrock-rag/llm-gateway-nginx.tf`
    - Instance type: t3.micro, Amazon Linux 2023, Frontend VPC private subnet (10.10.x.x)
    - No public IP, IMDSv2 required, Root EBS 20GB gp3 encrypted
    - Security Group: Inbound TCP 443 from 192.128.0.0/16, Outbound TCP 443 to 10.10.0.0/16
    - IAM role: CloudWatch Logs + AmazonSSMManagedInstanceCore
    - User Data: install Nginx, create self-signed cert (or CSR for sysadmin signing), configure llm/mcp virtual hosts with proxy_pass → API Gateway URL, enable systemd, install CloudWatch Agent
    - API GW URL: `https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/prod/llm/` and `/prod/mcp/`
    - SSE/WebSocket 지원: `proxy_http_version 1.1`, `proxy_read_timeout 3600`
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ] 12.2 Update 사내 DNS (BIND)
    - 사내 `corp.bos-semi.com.zone`에서 `llm`, `mcp` A 레코드를 Nginx EC2 private IP로 업데이트
    - Serial 증가 후 `rndc reload`
    - 검증: `dig @192.128.10.101 -p 8853 llm.corp.bos-semi.com +short` → Nginx EC2 IP
    - _Requirements: 10.1, 10.2_

  - [ ] 12.3 End-to-end 검증
    - `curl -k https://llm.corp.bos-semi.com/health` → 200
    - `curl -k https://mcp.corp.bos-semi.com/health` → 200
    - Kiro MCP 설정으로 `search_rtl` 도구 동작 확인
    - _Requirements: 19.1, 19.2, 19.3_

- [x] 10. Integration tests and validation
  - [x] 10.1 Create Terraform plan validation test in `tests/integration/llm_gateway_plan_test.go`
    - Verify terraform plan produces no destructive changes to existing resources
    - Verify all new resources have required tags (Project, Environment, ManagedBy)
    - Verify all EBS volumes are encrypted
    - Verify no public IPs assigned
    - Verify IMDSv2 enforced on all instances
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 22.1, 22.2, 22.3_

  - [x]* 10.2 Create service connectivity integration tests in `tests/integration/llm_gateway_connectivity_test.go`
    - Verify LiteLLM /health returns 200
    - Verify MCP Server /health returns 200
    - Verify API Gateway /llm and /mcp routes respond
    - Verify Route53 DNS records resolve correctly
    - Verify Squid accepts CONNECT to whitelisted domain
    - Verify Squid denies CONNECT to non-whitelisted domain
    - _Requirements: 19.1, 19.2, 19.3, 20.1, 20.2, 20.3, 23.4, 23.5_

- [x] 11. Final checkpoint - Ensure all validation passes
  - Ensure `terraform validate` passes for both environment directories
  - Ensure `tflint` passes with no errors
  - Ensure `terraform plan` is clean (additive only, no destructive changes)
  - Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation via `terraform validate` and `terraform plan`
- All Terraform files are additive — no existing .tf file modifications
- User Data scripts embed Docker Compose, config files, and backup scripts inline via heredoc in Terraform `templatefile()`
- Go integration tests use the existing test framework in `tests/` directory
- Implementation language: Terraform (HCL) for infrastructure, Bash for User Data scripts, Node.js for MCP Server application code

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "7.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.2", "3.3", "7.2", "8.1"] },
    { "id": 3, "tasks": ["2.4", "3.4", "5.1", "6.1", "7.3"] },
    { "id": 4, "tasks": ["10.1"] },
    { "id": 5, "tasks": ["10.2"] }
  ]
}
```
