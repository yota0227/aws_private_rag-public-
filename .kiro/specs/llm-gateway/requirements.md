# Requirements Document

## Introduction

기존 두 개의 개별 스펙(litellm-mcp-server, kiro-cli-proxy-routing)을 통합한 LLM Gateway 스펙이다. 세 개의 EC2 인스턴스를 두 VPC에 분산 배치하여 통합 AI 개발 인프라를 구성한다:

1. **LiteLLM Proxy (Logging VPC)** — OpenAI-compatible API로 GPT + Bedrock 모델 접근, Virtual Key 기반 20팀/300명 예산 관리
2. **MCP Server (Frontend VPC)** — 17개 RAG/Neptune/HDD 도구를 MCP 프로토콜로 노출, Lambda 연동
3. **Squid Forward Proxy (Logging VPC)** — 도메인 화이트리스트 기반 인터넷 접근 제어 (Kiro CLI, Claude Code, OpenAI API)

네트워크 구성:
- Frontend VPC(10.10.0.0/16) 기본 라우트 0.0.0.0/0 → TGW → Logging VPC NAT (LiteLLM OpenAI 아웃바운드)
- LiteLLM → Bedrock: TGW → Frontend VPC → VPC Peering → Virginia
- API Gateway /llm, /mcp 경로를 통한 온프레미스 접근
- Squid: 온프레미스 → VPN → TGW → Logging VPC → NAT → IGW → 인터넷

## Glossary

- **LiteLLM_Server**: Logging VPC EC2(t3.medium)에서 Docker 컨테이너로 실행되는 LiteLLM 프록시 서비스 (port 4000), OpenAI GPT 및 Bedrock 모델을 OpenAI-compatible API로 노출
- **MCP_Server**: Frontend VPC EC2(t3.small)에서 실행되는 MCP(Model Context Protocol) 서버 (port 3000), Streamable HTTP 전송 방식으로 RAG/Neptune 도구 제공
- **Squid_Proxy**: Logging VPC EC2(t3.micro)에서 실행되는 포워드 프록시 (port 3128), 도메인 화이트리스트 기반 인터넷 접근 제어
- **LiteLLM_EC2**: Logging VPC private subnet에 배포되는 t3.medium EC2 인스턴스, LiteLLM_Server와 PostgreSQL을 호스팅
- **MCP_EC2**: Frontend VPC private subnet에 배포되는 t3.small EC2 인스턴스, MCP_Server를 호스팅
- **Squid_EC2**: Logging VPC private subnet에 배포되는 t3.micro EC2 인스턴스, Squid_Proxy를 호스팅
- **Virtual_Key**: LiteLLM의 /key/generate API로 발급하는 사용자별 API 키, 예산 제한 및 모델 접근 제어 포함
- **PostgreSQL_DB**: LiteLLM Virtual Key 및 예산 추적용 Docker 컨테이너 PostgreSQL 데이터베이스
- **Private_API_Gateway**: 기존 private-rag-api-prod REST API Gateway (Seoul, VPC Endpoint 경유 접근)
- **VPC_Peering**: Seoul Frontend VPC(10.10.0.0/16)와 Virginia Backend VPC(10.20.0.0/16) 간 피어링 연결
- **Transit_Gateway**: Seoul 리전 TGW (tgw-bos-ai-seoul-prod), Frontend VPC와 Logging VPC 모두 연결됨
- **Logging_VPC**: Seoul 보안 로깅/모니터링 VPC (10.200.0.0/16), NAT Gateway와 IGW 보유
- **Frontend_VPC**: Seoul AI 워크로드 VPC (10.10.0.0/16), Lambda/API GW/VPC Endpoints 보유
- **Route53_PHZ**: corp.bos-semi.com Private Hosted Zone (Z04599582HCRH2UPCSS34)
- **Secrets_Manager**: AWS Secrets Manager에 저장되는 API 키 및 인증 정보
- **Domain_Whitelist**: Squid ACL에서 허용하는 도메인 목록 (방화벽 수준 정책 관리 대상)
- **NAT_Gateway**: Logging VPC에 기존 배포된 NAT Gateway, 인터넷 아웃바운드 제공

## Requirements

### Requirement 1: LiteLLM EC2 인스턴스 프로비저닝 (Logging VPC)

**User Story:** As a DevOps engineer, I want a dedicated EC2 instance in Logging VPC for LiteLLM proxy, so that OpenAI API 접근이 NAT Gateway를 통해 직접 가능하고 GPT + Bedrock 모델을 통합 제공할 수 있다.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL provision LiteLLM_EC2 as a t3.medium instance in Logging VPC private subnet (10.200.0.0/16)
2. THE LiteLLM_EC2 SHALL have no public IP address assigned
3. THE LiteLLM_EC2 SHALL use Amazon Linux 2023 AMI (x86_64, HVM)
4. THE LiteLLM_EC2 SHALL have a root EBS volume of 20GB (gp3, encrypted with AWS managed key)
5. THE LiteLLM_EC2 SHALL have an additional EBS data volume of 50GB (gp3, encrypted) mounted at /data for PostgreSQL 데이터 및 Docker 볼륨
6. THE LiteLLM_EC2 SHALL enforce IMDSv2 (http_tokens = required)
7. THE LiteLLM_EC2 SHALL execute User_Data script on first boot to install Docker, Docker Compose, PostgreSQL container, and LiteLLM container

### Requirement 2: LiteLLM 프록시 서비스 구성

**User Story:** As a developer, I want LiteLLM to provide a unified OpenAI-compatible API for both GPT and Bedrock models, so that Codex CLI, Claude Code, and other AI tools can use a single endpoint with standardized API format.

#### Acceptance Criteria

1. THE LiteLLM_Server SHALL listen on port 4000 inside LiteLLM_EC2
2. THE LiteLLM_Server SHALL proxy requests to OpenAI GPT models (gpt-4o, gpt-4o-mini, o3-mini) via Logging VPC NAT Gateway 인터넷 경로
3. THE LiteLLM_Server SHALL proxy requests to AWS Bedrock models (Claude 3.5 Sonnet, Claude 3 Haiku, Claude 3 Opus, Titan Embed Text v2) via TGW → Frontend VPC → VPC Peering → Virginia Bedrock endpoint
4. THE LiteLLM_Server SHALL use Virtual_Key system for authentication instead of single master key
5. THE LiteLLM_Server SHALL use IAM_Role credentials to authenticate with AWS Bedrock (no static AWS keys)
6. WHEN LiteLLM_Server receives a request with an invalid or expired Virtual_Key, THE LiteLLM_Server SHALL return HTTP 401 with an error message identifying the authentication failure reason
7. WHEN LiteLLM_Server receives a request for an unconfigured model, THE LiteLLM_Server SHALL return HTTP 400 with an error message identifying the invalid model name

### Requirement 3: LiteLLM Virtual Key 및 예산 관리

**User Story:** As a platform administrator, I want per-user API keys with budget limits, so that 20 teams and 300 users can be managed with cost control and usage tracking.

#### Acceptance Criteria

1. THE LiteLLM_Server SHALL provide /key/generate API endpoint to create new Virtual Keys with user_id, team_id, max_budget, and allowed_models parameters
2. THE LiteLLM_Server SHALL store Virtual Key metadata (user, team, budget, usage) in PostgreSQL_DB
3. THE PostgreSQL_DB SHALL run as a Docker container on LiteLLM_EC2 with data persisted to /data/postgres volume
4. THE LiteLLM_Server SHALL enforce per-user budget limits and reject requests when budget is exceeded with HTTP 429 and remaining budget information
5. THE LiteLLM_Server SHALL track token usage per Virtual Key and expose usage statistics via /key/info endpoint
6. THE LiteLLM_Server SHALL support team-level budget aggregation for 20 teams
7. IF PostgreSQL_DB becomes unavailable, THEN THE LiteLLM_Server SHALL return HTTP 503 with a service unavailable message and log the database connection failure

### Requirement 4: MCP Server EC2 인스턴스 프로비저닝 (Frontend VPC)

**User Story:** As a DevOps engineer, I want the MCP Server in Frontend VPC, so that RAG 데이터가 격리된 상태로 유지되고 Lambda와 같은 VPC 내에서 직접 호출할 수 있다.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL provision MCP_EC2 as a t3.small instance in Frontend VPC private subnet (10.10.0.0/16)
2. THE MCP_EC2 SHALL have no public IP address assigned
3. THE MCP_EC2 SHALL use Amazon Linux 2023 AMI (x86_64, HVM)
4. THE MCP_EC2 SHALL have a root EBS volume of 20GB (gp3, encrypted with AWS managed key)
5. THE MCP_EC2 SHALL enforce IMDSv2 (http_tokens = required)
6. THE MCP_EC2 SHALL execute User_Data script on first boot to install runtime dependencies and start MCP_Server

### Requirement 5: MCP Server 서비스 구성

**User Story:** As a developer, I want an MCP-compatible server exposing RAG and Neptune tools, so that AI agents (Kiro, Claude Code, VS Code, Codex CLI) can invoke tools via standard MCP protocol with Streamable HTTP transport.

#### Acceptance Criteria

1. THE MCP_Server SHALL listen on port 3000 inside MCP_EC2
2. THE MCP_Server SHALL implement MCP protocol with Streamable HTTP transport using Python mcp SDK or Node.js @modelcontextprotocol/sdk
3. THE MCP_Server SHALL implement the following 9 RAG/Archive tools: rag_query, rag_list_documents, rag_categories, rag_upload_status, rag_extract_status, rag_delete_document, search_rtl, search_archive, get_evidence
4. THE MCP_Server SHALL implement the following 4 Neptune tools: trace_signal_path, find_instantiation_tree, find_clock_crossings, graph_export
5. THE MCP_Server SHALL implement the following 4 Claims/HDD tools: list_verified_claims, generate_hdd_section, publish_markdown, regenerate_stale_hdd
6. THE MCP_Server SHALL invoke the existing Lambda function (lambda-document-processor-seoul-prod) to execute RAG tools
7. THE MCP_Server SHALL authenticate incoming requests using an API key stored in Secrets_Manager
8. WHEN MCP_Server receives a request for an undefined tool, THE MCP_Server SHALL return an MCP protocol error response listing available tools
9. WHEN the underlying Lambda invocation fails, THE MCP_Server SHALL return an MCP protocol error with the Lambda error details
10. THE MCP_Server SHALL support concurrent connections from multiple MCP clients (Kiro, Claude Code, VS Code, Codex CLI)

### Requirement 6: Squid Forward Proxy EC2 프로비저닝 (Logging VPC)

**User Story:** As a security engineer, I want a dedicated forward proxy in Logging VPC, so that on-premises tools can access approved internet endpoints through a controlled, auditable path.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL provision Squid_EC2 as a t3.micro instance in Logging VPC private subnet (10.200.0.0/16)
2. THE Squid_EC2 SHALL have no public IP address assigned
3. THE Squid_EC2 SHALL use Amazon Linux 2023 AMI (x86_64, HVM)
4. THE Squid_EC2 SHALL have a root EBS volume of 20GB (gp3, encrypted with AWS managed key)
5. THE Squid_EC2 SHALL enforce IMDSv2 (http_tokens = required)
6. THE Squid_EC2 SHALL execute User_Data script on first boot to install and configure Squid proxy

### Requirement 7: Squid 프록시 도메인 화이트리스트 정책

**User Story:** As a security engineer, I want domain-based whitelist access control on Squid, so that only approved services (Kiro, OpenAI, Anthropic) can be accessed from on-premises through the proxy, maintaining firewall-level policy enforcement.

#### Acceptance Criteria

1. THE Squid_Proxy SHALL listen on port 3128 inside Squid_EC2
2. THE Squid_Proxy SHALL allow CONNECT method only to port 443 (HTTPS)
3. THE Squid_Proxy SHALL allow traffic only from on-premises CIDR (192.128.0.0/16)
4. THE Squid_Proxy SHALL maintain Domain_Whitelist containing: Kiro 도메인 (*.kiro.dev 관련), OpenAI API (api.openai.com), Anthropic API (api.anthropic.com), AWS Cognito (*.amazoncognito.com)
5. WHEN Squid_Proxy receives a request for a domain not in Domain_Whitelist, THE Squid_Proxy SHALL deny the request and log the denied domain with client IP and timestamp
6. WHEN Squid_Proxy receives a request from an IP not in on-premises CIDR, THE Squid_Proxy SHALL deny the request
7. THE Squid_Proxy SHALL log all allowed and denied requests to /var/log/squid/access.log for audit trail
8. THE Squid_Proxy SHALL route outbound traffic via Logging VPC NAT_Gateway → IGW to reach internet endpoints

### Requirement 8: Frontend VPC 기본 라우트 추가

**User Story:** As a network engineer, I want a default route in Frontend VPC pointing to TGW, so that LiteLLM in Logging VPC can access Bedrock via Frontend VPC → VPC Peering → Virginia path.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL add a route 0.0.0.0/0 → Transit_Gateway to Frontend VPC private route table
2. THE Terraform_Configuration SHALL preserve all existing routes in Frontend VPC private route table without modification
3. WHILE the default route is active, THE Frontend_VPC private subnet resources SHALL route internet-bound traffic via TGW → Logging VPC NAT_Gateway
4. THE Terraform_Configuration SHALL verify TGW attachments for both Frontend VPC and Logging VPC are active before adding the route

### Requirement 9: API Gateway 경로 추가

**User Story:** As a DevOps engineer, I want /llm and /mcp routes on the existing Private API Gateway, so that on-premises clients can access LiteLLM and MCP Server through the established VPC Endpoint path.

#### Acceptance Criteria

1. THE Private_API_Gateway SHALL have a /llm/{proxy+} resource with ANY method configured as HTTP_PROXY integration to LiteLLM_EC2 port 4000 (via VPC Link or cross-VPC HTTP_PROXY)
2. THE Private_API_Gateway SHALL have a /mcp/{proxy+} resource with ANY method configured as HTTP_PROXY integration to MCP_EC2 port 3000
3. THE Terraform_Configuration SHALL preserve all existing API Gateway resources and integrations without modification
4. WHEN a request arrives at /llm/{proxy+}, THE Private_API_Gateway SHALL forward the request to LiteLLM_EC2 private IP port 4000 with path preserved
5. WHEN a request arrives at /mcp/{proxy+}, THE Private_API_Gateway SHALL forward the request to MCP_EC2 private IP port 3000 with path preserved
6. THE Private_API_Gateway SHALL redeploy the prod stage after adding the new routes

### Requirement 10: Route53 DNS 레코드

**User Story:** As a developer, I want friendly DNS names for LiteLLM and MCP Server, so that clients can use memorable hostnames instead of raw API Gateway URLs.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL create an A record (Alias) for llm.corp.bos-semi.com in Route53_PHZ pointing to the execute-api VPC Endpoint
2. THE Terraform_Configuration SHALL create an A record (Alias) for mcp.corp.bos-semi.com in Route53_PHZ pointing to the execute-api VPC Endpoint
3. THE Terraform_Configuration SHALL use the existing Route53_PHZ (zone ID: Z04599582HCRH2UPCSS34) without creating a new zone

### Requirement 11: IAM 역할 및 정책 (LiteLLM EC2)

**User Story:** As a security engineer, I want LiteLLM EC2 to have least-privilege IAM permissions covering Bedrock access and key management, so that it can operate with minimal AWS privileges.

#### Acceptance Criteria

1. THE IAM_Role for LiteLLM_EC2 SHALL allow invocation of Bedrock models (bedrock:InvokeModel, bedrock:InvokeModelWithResponseStream) in us-east-1
2. THE IAM_Role for LiteLLM_EC2 SHALL allow reading secrets from Secrets_Manager (secretsmanager:GetSecretValue) for LiteLLM-related secrets in ap-northeast-2
3. THE IAM_Role for LiteLLM_EC2 SHALL allow writing logs to CloudWatch Logs (logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents)
4. THE IAM_Role for LiteLLM_EC2 SHALL include AmazonSSMManagedInstanceCore policy for remote management via Systems Manager
5. THE IAM_Role for LiteLLM_EC2 SHALL follow the ec2.amazonaws.com trust policy pattern

### Requirement 12: IAM 역할 및 정책 (MCP Server EC2)

**User Story:** As a security engineer, I want MCP Server EC2 to have least-privilege IAM permissions for Lambda invocation and secrets access only.

#### Acceptance Criteria

1. THE IAM_Role for MCP_EC2 SHALL allow invocation of Lambda function lambda-document-processor-seoul-prod (lambda:InvokeFunction) in ap-northeast-2
2. THE IAM_Role for MCP_EC2 SHALL allow reading secrets from Secrets_Manager (secretsmanager:GetSecretValue) for MCP-related secrets in ap-northeast-2
3. THE IAM_Role for MCP_EC2 SHALL allow writing logs to CloudWatch Logs (logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents)
4. THE IAM_Role for MCP_EC2 SHALL include AmazonSSMManagedInstanceCore policy for remote management via Systems Manager
5. THE IAM_Role for MCP_EC2 SHALL follow the ec2.amazonaws.com trust policy pattern

### Requirement 13: Security Group 구성 (LiteLLM EC2)

**User Story:** As a security engineer, I want network access to LiteLLM EC2 restricted to only necessary traffic paths.

#### Acceptance Criteria

1. THE Security_Group for LiteLLM_EC2 SHALL allow inbound TCP port 4000 from Frontend VPC CIDR (10.10.0.0/16) for API Gateway integration
2. THE Security_Group for LiteLLM_EC2 SHALL allow inbound TCP port 4000 from on-premises CIDR (192.128.0.0/16) for direct TGW access
3. THE Security_Group for LiteLLM_EC2 SHALL allow outbound TCP port 443 to 0.0.0.0/0 for OpenAI API via NAT Gateway and Bedrock via TGW
4. THE Docker network configuration on LiteLLM_EC2 SHALL isolate PostgreSQL container to host-only network (no external port binding), ensuring port 5432 is accessible only from the LiteLLM container via Docker internal network
5. THE Security_Group for LiteLLM_EC2 SHALL be associated with Logging VPC

### Requirement 14: Security Group 구성 (MCP Server EC2)

**User Story:** As a security engineer, I want network access to MCP Server EC2 restricted to Frontend VPC traffic only.

#### Acceptance Criteria

1. THE Security_Group for MCP_EC2 SHALL allow inbound TCP port 3000 from Frontend VPC CIDR (10.10.0.0/16)
2. THE Security_Group for MCP_EC2 SHALL allow outbound TCP port 443 to 0.0.0.0/0 for Lambda invocation via VPC Endpoint and Secrets Manager
3. THE Security_Group for MCP_EC2 SHALL be associated with Frontend VPC (vpc-0a118e1bf21d0c057)

### Requirement 15: Security Group 구성 (Squid Proxy EC2)

**User Story:** As a security engineer, I want Squid Proxy EC2 restricted to proxy traffic from on-premises and HTTPS outbound only.

#### Acceptance Criteria

1. THE Security_Group for Squid_EC2 SHALL allow inbound TCP port 3128 from on-premises CIDR (192.128.0.0/16)
2. THE Security_Group for Squid_EC2 SHALL allow inbound TCP port 22 from on-premises CIDR (192.128.0.0/16) for SSH management
3. THE Security_Group for Squid_EC2 SHALL allow outbound TCP port 443 to 0.0.0.0/0 for HTTPS via NAT Gateway
4. THE Security_Group for Squid_EC2 SHALL allow outbound UDP port 53 and TCP port 53 to 0.0.0.0/0 for DNS resolution
5. THE Security_Group for Squid_EC2 SHALL be associated with Logging VPC

### Requirement 16: Secrets Manager 구성

**User Story:** As a security engineer, I want all service credentials stored in Secrets Manager with secure random values, so that authentication is centralized and keys are rotatable.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL create a Secrets_Manager secret named "llm-gateway/litellm-master-key" in ap-northeast-2 with a random 32-character alphanumeric value for LiteLLM admin operations
2. THE Terraform_Configuration SHALL create a Secrets_Manager secret named "llm-gateway/mcp-api-key" in ap-northeast-2 with a random 32-character alphanumeric value for MCP Server authentication
3. THE Terraform_Configuration SHALL create a Secrets_Manager secret named "llm-gateway/postgres-password" in ap-northeast-2 with a random 24-character alphanumeric value for PostgreSQL
4. THE User_Data scripts SHALL retrieve secrets from Secrets_Manager at boot time and inject them into Docker Compose environment
5. IF Secrets_Manager retrieval fails during boot, THEN THE User_Data script SHALL retry 3 times with exponential backoff (2s, 4s, 8s) and log the failure to /var/log/user-data.log

### Requirement 17: CLI 도구 연동 구성

**User Story:** As a developer, I want clear integration paths for Codex CLI, Claude Code, Kiro CLI, and VS Code, so that each tool can access the appropriate gateway service.

#### Acceptance Criteria

1. THE LiteLLM_Server SHALL expose an OpenAI-compatible endpoint that Codex CLI can use by setting OPENAI_API_KEY (Virtual_Key) and OPENAI_BASE_URL (https://llm.corp.bos-semi.com/prod/llm)
2. THE LiteLLM_Server SHALL expose an Anthropic-compatible endpoint that Claude Code can use via Virtual_Key authentication
3. THE Squid_Proxy SHALL support Kiro CLI proxy configuration (HTTPS_PROXY=http://{squid_ip}:3128) for external auth to *.kiro.dev
4. THE Squid_Proxy SHALL support Claude Code proxy configuration for Anthropic API access (api.anthropic.com)
5. THE MCP_Server SHALL support VS Code MCP client connections via mcp.json configuration pointing to https://mcp.corp.bos-semi.com/prod/mcp

### Requirement 18: Docker Compose 및 User Data 구성 (LiteLLM EC2)

**User Story:** As a DevOps engineer, I want LiteLLM EC2 fully self-contained with Docker Compose, so that LiteLLM + PostgreSQL are reproducible without external dependencies.

#### Acceptance Criteria

1. THE User_Data script for LiteLLM_EC2 SHALL install Docker and Docker Compose plugin on Amazon Linux 2023
2. THE User_Data script SHALL create docker-compose.yml at /data/docker-compose.yml defining litellm and postgres containers
3. THE User_Data script SHALL create LiteLLM config.yaml at /data/litellm/config.yaml with all model definitions (OpenAI GPT + Bedrock)
4. THE User_Data script SHALL configure PostgreSQL container with persistent volume at /data/postgres
5. THE User_Data script SHALL start all containers via docker compose up -d with restart: always policy
6. THE User_Data script SHALL log all operations to /var/log/user-data.log with timestamps

### Requirement 19: 네트워크 경로 — LiteLLM Bedrock 접근

**User Story:** As a network engineer, I want LiteLLM in Logging VPC to reach Virginia Bedrock, so that Bedrock 모델 호출이 TGW → Frontend VPC → VPC Peering 경로로 가능하다.

#### Acceptance Criteria

1. THE LiteLLM_EC2 SHALL access Bedrock endpoint in us-east-1 via path: Logging VPC → TGW → Frontend VPC → VPC Peering → Virginia Backend VPC → Bedrock VPC Endpoint
2. THE Logging VPC route table SHALL have a route for 10.10.0.0/16 (Frontend VPC) via Transit_Gateway
3. THE Frontend VPC route table SHALL have a route for 10.20.0.0/16 (Virginia VPC) via VPC_Peering
4. THE Terraform_Configuration SHALL verify existing TGW route propagation covers Logging VPC → Frontend VPC path

### Requirement 20: 네트워크 경로 — Squid 인터넷 접근

**User Story:** As a network engineer, I want Squid proxy traffic to reach internet via existing NAT Gateway, so that whitelisted domains are accessible from on-premises through the proxy chain.

#### Acceptance Criteria

1. THE Squid_EC2 SHALL route outbound HTTPS traffic via Logging VPC NAT_Gateway → IGW → Internet
2. THE Logging VPC private subnet route table SHALL have a route 0.0.0.0/0 → NAT_Gateway for Squid outbound
3. WHEN on-premises client sends CONNECT request to Squid_Proxy, THE traffic path SHALL be: On-prem → VPN → TGW → Logging VPC → Squid → NAT_Gateway → IGW → Internet
4. THE return traffic SHALL follow the reverse path back to the on-premises client

### Requirement 21: 기존 인프라 보호

**User Story:** As a DevOps engineer, I want the deployment to be additive-only, so that existing resources remain unaffected.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL add new resources without modifying any existing resource blocks in api-gateway.tf
2. THE Terraform_Configuration SHALL preserve all existing VPC Endpoints, Lambda functions, and TGW attachments
3. THE Terraform_Configuration SHALL place LiteLLM resources in a separate Terraform file (llm-gateway-litellm.tf) within environments/app-layer/bedrock-rag/
4. THE Terraform_Configuration SHALL place MCP Server resources in a separate Terraform file (llm-gateway-mcp.tf) within environments/app-layer/bedrock-rag/
5. THE Terraform_Configuration SHALL place Squid Proxy resources in a separate Terraform file (llm-gateway-squid.tf) within environments/network-layer/
6. IF terraform plan shows any destructive changes to existing resources, THEN THE deployment SHALL be halted for manual review

### Requirement 22: 보안 강화 공통 요구사항

**User Story:** As a security engineer, I want all EC2 instances to follow security best practices, so that the attack surface is minimized across the entire LLM Gateway.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL enforce IMDSv2 on all three EC2 instances (LiteLLM_EC2, MCP_EC2, Squid_EC2)
2. THE Terraform_Configuration SHALL encrypt all EBS volumes with AWS managed keys
3. THE Terraform_Configuration SHALL assign no public IP to any of the three EC2 instances
4. THE Terraform_Configuration SHALL enable Systems Manager (SSM) access on all instances for management without SSH exposure
5. WHILE RAG data is processed, THE MCP_Server SHALL keep all data within Frontend VPC (no RAG data transmitted to Logging VPC)
6. THE Squid_Proxy SHALL delete X-Forwarded-For headers and disable Via header to prevent information leakage

### Requirement 23: 모니터링 및 운영 가시성

**User Story:** As a DevOps engineer, I want comprehensive monitoring with CloudWatch alarms and health checks, so that service degradation is detected early and operational visibility is maintained.

#### Acceptance Criteria

1. THE Terraform_Configuration SHALL create CloudWatch Alarms for LiteLLM_EC2: CPUUtilization > 80% for 5 minutes, StatusCheckFailed for 2 consecutive periods
2. THE Terraform_Configuration SHALL create CloudWatch Alarms for MCP_EC2: CPUUtilization > 80% for 5 minutes, StatusCheckFailed for 2 consecutive periods
3. THE Terraform_Configuration SHALL create CloudWatch Alarms for Squid_EC2: CPUUtilization > 70% for 5 minutes, StatusCheckFailed for 2 consecutive periods
4. THE LiteLLM_Server SHALL expose /health endpoint on port 4000 returning HTTP 200 when service is healthy and HTTP 503 when PostgreSQL_DB is unreachable
5. THE MCP_Server SHALL expose /health endpoint on port 3000 returning HTTP 200 when Lambda connectivity is verified
6. THE Terraform_Configuration SHALL create a CloudWatch Log Group /llm-gateway/litellm with 30-day retention for LiteLLM container logs
7. THE Terraform_Configuration SHALL create a CloudWatch Log Group /llm-gateway/mcp-server with 30-day retention for MCP Server logs
8. THE Terraform_Configuration SHALL create a CloudWatch Log Group /llm-gateway/squid with 30-day retention for Squid access logs
9. THE User_Data scripts SHALL install and configure CloudWatch Agent on all three EC2 instances to ship logs and custom metrics (disk usage, memory)
10. THE Terraform_Configuration SHALL create an SNS Topic (llm-gateway-alerts) for alarm notifications

### Requirement 24: PostgreSQL 백업 및 복구 전략

**User Story:** As a DevOps engineer, I want automated PostgreSQL backups and documented recovery procedures, so that Virtual Key data and usage history are protected against data loss.

#### Acceptance Criteria

1. THE LiteLLM_EC2 SHALL execute a daily pg_dump cron job at 03:00 KST, compressing output to /data/backups/postgres-{YYYYMMDD}.sql.gz
2. THE LiteLLM_EC2 SHALL retain the last 7 daily backup files locally and delete older backups automatically
3. THE LiteLLM_EC2 SHALL upload daily backups to S3 bucket (s3-bos-ai-backups-seoul-prod/llm-gateway/postgres/) with 90-day lifecycle expiration
4. THE IAM_Role for LiteLLM_EC2 SHALL additionally allow s3:PutObject to the backup S3 path
5. IF PostgreSQL container fails to start, THEN THE recovery procedure SHALL restore from the latest local backup via pg_restore and restart the container
6. THE Terraform_Configuration SHALL create a CloudWatch Alarm when backup cron fails (no new backup file detected in S3 within 25 hours)

### Requirement 25: 용량 계획 및 스케일링 대응

**User Story:** As a platform administrator, I want capacity planning aligned with 300 concurrent users across 20 teams, so that the system remains responsive under expected peak load.

#### Acceptance Criteria

1. THE LiteLLM_EC2 t3.medium (2 vCPU, 4GB RAM) SHALL support up to 50 concurrent API requests with < 500ms proxy overhead (excluding upstream model latency)
2. THE MCP_Server t3.small (2 vCPU, 2GB RAM) SHALL support up to 30 concurrent MCP tool invocations
3. IF CloudWatch CPUUtilization alarm triggers for LiteLLM_EC2, THEN THE operations team SHALL evaluate vertical scaling to t3.large (documented in operational runbook)
4. THE Docker Compose configuration SHALL set resource limits: LiteLLM container max 3GB memory, PostgreSQL container max 1GB memory
5. THE LiteLLM_Server SHALL configure connection pooling with max 50 concurrent upstream connections to OpenAI and 20 to Bedrock
6. WHEN request queue exceeds capacity, THE LiteLLM_Server SHALL return HTTP 429 with Retry-After header indicating recommended wait time

### Requirement 26: 배포 및 업데이트 절차

**User Story:** As a DevOps engineer, I want documented deployment and rollback procedures, so that LiteLLM, MCP Server, and Squid can be safely updated without service disruption.

#### Acceptance Criteria

1. THE LiteLLM_EC2 SHALL support container image version pinning in docker-compose.yml (e.g., ghcr.io/berriai/litellm:v1.x.x)
2. THE deployment procedure SHALL create a pre-update AMI snapshot of LiteLLM_EC2 before any version upgrade
3. THE rollback procedure SHALL restore LiteLLM_EC2 from the pre-update AMI snapshot within 15 minutes using Launch Template version switch
4. THE MCP_Server deployment SHALL use a systemd service with ExecStartPre health check, rolling back to previous binary if health check fails within 60 seconds
5. THE Squid_Proxy configuration changes SHALL be validated via squid -k parse before applying, with automatic rollback to /etc/squid/squid.conf.bak on parse failure
6. THE Terraform_Configuration SHALL use Launch Template with version tracking for all three EC2 instances, enabling instance replacement via terraform apply without manual intervention
7. WHEN a container version update is deployed to LiteLLM_EC2, THE procedure SHALL verify /health endpoint returns 200 within 120 seconds, otherwise trigger automatic rollback
