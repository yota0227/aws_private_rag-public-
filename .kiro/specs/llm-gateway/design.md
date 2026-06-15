# Design Document: LLM Gateway

## Overview

LLM Gateway는 세 개의 EC2 인스턴스를 두 VPC에 분산 배치하여 통합 AI 개발 인프라를 구성하는 시스템이다:

1. **LiteLLM Proxy** (Logging VPC, t3.medium) — OpenAI-compatible API로 GPT + Bedrock 모델 통합, Virtual Key 기반 20팀/300명 예산 관리
2. **MCP Server** (Frontend VPC, t3.small) — 17개 RAG/Neptune/HDD 도구를 MCP 프로토콜로 노출
3. **Squid Forward Proxy** (Logging VPC, t3.micro) — 도메인 화이트리스트 기반 인터넷 접근 제어

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LiteLLM 위치 | Logging VPC | NAT Gateway 통한 직접 OpenAI 접근, Bedrock은 TGW→Frontend VPC→VPC Peering 경로 |
| MCP Server 위치 | Frontend VPC | Lambda와 동일 VPC로 VPC Endpoint 경유 직접 호출, RAG 데이터 격리 |
| Squid 위치 | Logging VPC | NAT Gateway 공유, 온프레미스→VPN→TGW 경로 단순화 |
| **Nginx Reverse Proxy 위치** | **Frontend VPC** | **Private API GW는 custom domain 미지원 → Nginx가 TLS 종단 + API GW 프록시 담당. on-prem 엔지니어가 SSH 터널 없이 llm/mcp 도메인 직접 사용 가능** |
| DB 선택 | Docker PostgreSQL | LiteLLM 공식 지원, 외부 RDS 불필요한 소규모 메타데이터 |
| API Gateway 통합 | HTTP_PROXY integration | 기존 Private REST API에 경로 추가, Lambda 불필요 |
| MCP 전송 방식 | Streamable HTTP | MCP SDK 표준, SSE 호환, 방화벽 친화적 |
| Terraform 분리 | 서비스별 별도 .tf 파일 | 기존 인프라 보호, 독립 배포 가능 |

## Architecture

### High-Level Architecture

```mermaid
graph TB
    subgraph OnPrem["On-Premises (192.128.0.0/16)"]
        CodexCLI[Codex CLI]
        ClaudeCode[Claude Code]
        KiroCLI[Kiro CLI]
        VSCode[VS Code MCP Client]
    end

    subgraph AWS["AWS Seoul (ap-northeast-2)"]
        subgraph FrontendVPC["Frontend VPC (10.10.0.0/16)"]
            APIGW[Private API Gateway]
            VPCE[VPC Endpoint execute-api]
            MCP_EC2[MCP Server EC2\nt3.small:3000]
            LambdaFn[Lambda\ndocument-processor]
        end

        subgraph LoggingVPC["Logging VPC (10.200.0.0/16)"]
            LiteLLM_EC2[LiteLLM EC2\nt3.medium:4000]
            PostgreSQL[(PostgreSQL\nDocker Container)]
            Squid_EC2[Squid EC2\nt3.micro:3128]
            NAT[NAT Gateway]
            IGW[Internet Gateway]
        end

        TGW[Transit Gateway]
    end

    subgraph Virginia["AWS Virginia (us-east-1)"]
        subgraph BackendVPC["Backend VPC (10.20.0.0/16)"]
            Bedrock[Bedrock Endpoint]
        end
    end

    subgraph Internet["Internet"]
        OpenAI[api.openai.com]
        Anthropic[api.anthropic.com]
        KiroDev["*.kiro.dev"]
    end

    CodexCLI & ClaudeCode -->|VPN→TGW| APIGW
    KiroCLI -->|VPN→TGW| Squid_EC2
    VSCode -->|VPN→TGW| APIGW

    APIGW -->|/llm/*| LiteLLM_EC2
    APIGW -->|/mcp/*| MCP_EC2

    LiteLLM_EC2 --> PostgreSQL
    LiteLLM_EC2 -->|NAT→IGW| OpenAI
    LiteLLM_EC2 -->|TGW→Peering| Bedrock

    MCP_EC2 -->|VPC Endpoint| LambdaFn

    Squid_EC2 -->|NAT→IGW| Anthropic
    Squid_EC2 -->|NAT→IGW| KiroDev
    Squid_EC2 -->|NAT→IGW| OpenAI
```

### Network Routing Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Path 1: LiteLLM → OpenAI (GPT models)                                        │
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌─────┐    ┌─────────────────┐      │
│  │ LiteLLM EC2  │───→│ Logging NAT  │───→│ IGW │───→│ api.openai.com  │      │
│  │ (10.200.x.x) │    │ (10.200.x.x) │    │     │    │   (internet)    │      │
│  └──────────────┘    └──────────────┘    └─────┘    └─────────────────┘      │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Path 2: LiteLLM → Bedrock (Claude/Titan)                                     │
│                                                                              │
│  ┌──────────────┐    ┌─────┐    ┌──────────────┐    ┌───────────┐    ┌─────┐ │
│  │ LiteLLM EC2  │───→│ TGW │───→│ Frontend VPC │───→│VPC Peering│───→│ BD  │ │
│  │ (10.200.x.x) │    │     │    │ (10.10.x.x)  │    │           │    │(VA) │ │
│  └──────────────┘    └─────┘    └──────────────┘    └───────────┘    └─────┘ │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Path 3: On-Prem → LiteLLM (via API Gateway)                                  │
│                                                                              │
│  ┌──────────┐    ┌─────────┐    ┌────────────┐    ┌────────┐    ┌─────────┐  │
│  │ On-Prem  │───→│ VPN/TGW │───→│VPC Endpoint│───→│ API GW │───→│ LiteLLM │  │
│  │(192.128) │    │         │    │(10.10.x.x) │    │  /llm  │    │  :4000  │  │
│  └──────────┘    └─────────┘    └────────────┘    └────────┘    └─────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Path 4: On-Prem → MCP Server (via API Gateway)                               │
│                                                                              │
│  ┌──────────┐    ┌─────────┐    ┌────────────┐    ┌────────┐    ┌─────────┐  │
│  │ On-Prem  │───→│ VPN/TGW │───→│VPC Endpoint│───→│ API GW │───→│  MCP    │  │
│  │(192.128) │    │         │    │(10.10.x.x) │    │  /mcp  │    │  :3000  │  │
│  └──────────┘    └─────────┘    └────────────┘    └────────┘    └─────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Path 5: On-Prem → Squid → Internet (whitelisted domains only)                │
│                                                                              │
│  ┌──────────┐    ┌─────────┐    ┌──────────┐    ┌─────┐    ┌─────┐    ┌───┐  │
│  │ On-Prem  │───→│ VPN/TGW │───→│Squid:3128│───→│ NAT │───→│ IGW │───→│NET│  │
│  │(192.128) │    │         │    │(10.200.x)│    │     │    │     │    │   │  │
│  └──────────┘    └─────────┘    └──────────┘    └─────┘    └─────┘    └───┘  │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│ Path 6: MCP → Lambda (RAG tool execution)                                    │
│                                                                              │
│  ┌──────────┐    ┌────────────────┐    ┌────────────────────────┐            │ 
│  │ MCP EC2  │───→│ Lambda VPC EP  │───→│ Lambda (doc-processor) │            │
│  │(10.10.x) │    │ (10.10.x.x)    │    │ (10.10.x.x)            │            │
│  └──────────┘    └────────────────┘    └────────────────────────┘            │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Terraform File Layout

```
environments/
├── app-layer/bedrock-rag/
│   ├── llm-gateway-litellm.tf    # LiteLLM EC2, IAM, SG, Secrets, CloudWatch
│   ├── llm-gateway-mcp.tf        # MCP Server EC2, IAM, SG, Secrets, CloudWatch
│   ├── llm-gateway-apigw.tf      # /llm, /mcp API Gateway routes
│   ├── llm-gateway-dns.tf        # Route53 llm/mcp DNS records (A record, ENI IPs)
│   └── llm-gateway-nginx.tf      # Nginx Reverse Proxy EC2 (NEW)
├── network-layer/
│   ├── llm-gateway-squid.tf      # Squid EC2, IAM, SG, CloudWatch
│   └── llm-gateway-routes.tf     # Frontend VPC default route (0.0.0.0/0 → TGW)
```

## Components and Interfaces

### Component 1: LiteLLM EC2 (Logging VPC)

| Attribute | Value |
|-----------|-------|
| Instance Type | t3.medium (2 vCPU, 4GB RAM) |
| AMI | Amazon Linux 2023 (x86_64, HVM) |
| VPC/Subnet | Logging VPC private subnet (10.200.x.0/24) |
| EBS Root | 20GB gp3, encrypted |
| EBS Data | 50GB gp3, encrypted, mounted /data |
| IMDS | v2 required |
| Port | 4000 (LiteLLM), 5432 (PostgreSQL internal only) |

**Docker Compose Stack:**
```yaml
services:
  litellm:
    image: ghcr.io/berriai/litellm:v1.x.x  # version pinned
    ports: ["4000:4000"]
    environment:
      DATABASE_URL: postgresql://litellm:${POSTGRES_PASSWORD}@postgres:5432/litellm
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY}
    volumes: ["/data/litellm/config.yaml:/app/config.yaml"]
    deploy:
      resources:
        limits: { memory: 3G }
    restart: always
    depends_on: [postgres]

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: litellm
      POSTGRES_USER: litellm
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: ["/data/postgres:/var/lib/postgresql/data"]
    deploy:
      resources:
        limits: { memory: 1G }
    restart: always
    # No port binding — accessible only via Docker internal network
```

**LiteLLM config.yaml:**
```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY
  - model_name: gpt-4o-mini
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY
  - model_name: o3-mini
    litellm_params:
      model: openai/o3-mini
      api_key: os.environ/OPENAI_API_KEY
  - model_name: claude-3-5-sonnet
    litellm_params:
      model: bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0
      aws_region_name: us-east-1
  - model_name: claude-3-haiku
    litellm_params:
      model: bedrock/anthropic.claude-3-haiku-20240307-v1:0
      aws_region_name: us-east-1
  - model_name: claude-3-opus
    litellm_params:
      model: bedrock/anthropic.claude-3-opus-20240229-v1:0
      aws_region_name: us-east-1
  - model_name: titan-embed-text-v2
    litellm_params:
      model: bedrock/amazon.titan-embed-text-v2:0
      aws_region_name: us-east-1

general_settings:
  database_url: os.environ/DATABASE_URL
  master_key: os.environ/LITELLM_MASTER_KEY
  max_parallel_requests: 50

router_settings:
  num_retries: 2
  timeout: 120
  max_parallel_requests: 50
```

### Component 2: MCP Server EC2 (Frontend VPC)

| Attribute | Value |
|-----------|-------|
| Instance Type | t3.small (2 vCPU, 2GB RAM) |
| AMI | Amazon Linux 2023 (x86_64, HVM) |
| VPC/Subnet | Frontend VPC private subnet (10.10.x.0/24) |
| EBS Root | 20GB gp3, encrypted |
| IMDS | v2 required |
| Port | 3000 |
| Runtime | Node.js 20 + @modelcontextprotocol/sdk |

**MCP Tool Registry (17 tools):**

| Category | Tools |
|----------|-------|
| RAG/Archive (9) | rag_query, rag_list_documents, rag_categories, rag_upload_status, rag_extract_status, rag_delete_document, search_rtl, search_archive, get_evidence |
| Neptune (4) | trace_signal_path, find_instantiation_tree, find_clock_crossings, graph_export |
| Claims/HDD (4) | list_verified_claims, generate_hdd_section, publish_markdown, regenerate_stale_hdd |

**MCP Server Architecture:**
```
┌─────────────────────────────────────────────┐
│  MCP Server (Node.js, port 3000)            │
├─────────────────────────────────────────────┤
│  Transport: Streamable HTTP (/mcp)          │
│  Auth: API Key (from Secrets Manager)       │
├─────────────────────────────────────────────┤
│  Tool Router                                │
│    ├── RAG tools → Lambda invoke            │
│    ├── Neptune tools → Lambda invoke        │
│    └── HDD tools → Lambda invoke            │
├─────────────────────────────────────────────┤
│  Lambda Client (AWS SDK)                    │
│    → lambda-document-processor-seoul-prod   │
└─────────────────────────────────────────────┘
```

### Component 3: Squid Forward Proxy EC2 (Logging VPC)

| Attribute | Value |
|-----------|-------|
| Instance Type | t3.micro (2 vCPU, 1GB RAM) |
| AMI | Amazon Linux 2023 (x86_64, HVM) |
| VPC/Subnet | Logging VPC private subnet (10.200.x.0/24) |
| EBS Root | 20GB gp3, encrypted |
| IMDS | v2 required |
| Port | 3128 |

**Squid Configuration (squid.conf):**
```
# ACL definitions
acl onprem_network src 192.128.0.0/16
acl SSL_ports port 443
acl CONNECT method CONNECT

# Domain whitelist
acl allowed_domains dstdomain .kiro.dev
acl allowed_domains dstdomain api.openai.com
acl allowed_domains dstdomain api.anthropic.com
acl allowed_domains dstdomain .amazoncognito.com

# Access control
http_access deny !onprem_network
http_access deny CONNECT !SSL_ports
http_access allow onprem_network allowed_domains
http_access deny all

# Security headers
request_header_access X-Forwarded-For deny all
via off

# Logging
access_log /var/log/squid/access.log squid
cache_log /var/log/squid/cache.log

# Port
http_port 3128
```

### Component 4: API Gateway Routes

기존 `private-rag-api-prod` REST API에 두 경로 추가:

| Route | Integration | Target |
|-------|-------------|--------|
| `/llm/{proxy+}` ANY | HTTP_PROXY | `http://{LiteLLM_EC2_IP}:4000/{proxy}` |
| `/mcp/{proxy+}` ANY | HTTP_PROXY | `http://{MCP_EC2_IP}:3000/{proxy}` |

Cross-VPC 접근 (API GW in Frontend VPC → LiteLLM in Logging VPC)은 TGW 라우팅으로 해결. Frontend VPC에서 10.200.x.x 대역 통신 가능.

### Component 5: Route53 DNS Records

| Record | Type | Target |
|--------|------|--------|
| llm.corp.bos-semi.com | A | Nginx EC2 private IP (사내 BIND 직접 등록) |
| mcp.corp.bos-semi.com | A | Nginx EC2 private IP (사내 BIND 직접 등록) |

> **변경 이력**: 초기 설계는 Route53 PHZ ALIAS → VPC Endpoint였으나, ALIAS 레코드는 VPC 외부 forwarder에서 empty name을 반환하는 문제로 Nginx EC2 IP를 사내 BIND에 직접 등록하는 방식으로 변경.

### Component 5.5: Nginx Reverse Proxy EC2 (Frontend VPC) — NEW

Private API Gateway는 custom domain을 지원하지 않으므로, Nginx EC2가 TLS 종단 및 API Gateway 프록시를 담당한다.

| Attribute | Value |
|-----------|-------|
| Instance Type | t3.micro |
| VPC/Subnet | Frontend VPC private subnet (10.10.x.0/24) |
| EBS Root | 20GB gp3, encrypted |
| Port | 443 |
| Terraform | `environments/app-layer/bedrock-rag/llm-gateway-nginx.tf` |

**Nginx 설정 (llm-gateway.conf):**
```nginx
server {
    listen 443 ssl;
    server_name llm.corp.bos-semi.com;
    ssl_certificate     /etc/nginx/ssl/server.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;
    location / {
        proxy_pass https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/prod/llm/;
        proxy_ssl_server_name on;
        proxy_set_header Host r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com;
    }
}
server {
    listen 443 ssl;
    server_name mcp.corp.bos-semi.com;
    ssl_certificate     /etc/nginx/ssl/server.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;
    location / {
        proxy_pass https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/prod/mcp/;
        proxy_ssl_server_name on;
        proxy_set_header Host r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600;
    }
}
```

**Security Group (SG-Nginx):**
| Direction | Port | Source | Purpose |
|-----------|------|--------|---------|
| Inbound | 443 | 192.128.0.0/16 | On-prem HTTPS |
| Outbound | 443 | 10.10.0.0/16 | API GW VPC Endpoint |

**최종 네트워크 경로:**
```
On-prem → VPN → TGW → Frontend VPC → Nginx:443 → API GW → LiteLLM/MCP EC2
```

### Component 6: IAM Roles

**LiteLLM EC2 IAM Role:**
```
Trust: ec2.amazonaws.com
Policies:
  - bedrock:InvokeModel, bedrock:InvokeModelWithResponseStream (us-east-1, *)
  - secretsmanager:GetSecretValue (ap-northeast-2, llm-gateway/*)
  - logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents
  - s3:PutObject (s3-bos-ai-backups-seoul-prod/llm-gateway/postgres/*)
  - AmazonSSMManagedInstanceCore (managed policy)
```

**MCP EC2 IAM Role:**
```
Trust: ec2.amazonaws.com
Policies:
  - lambda:InvokeFunction (ap-northeast-2, lambda-document-processor-seoul-prod)
  - secretsmanager:GetSecretValue (ap-northeast-2, llm-gateway/*)
  - logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents
  - AmazonSSMManagedInstanceCore (managed policy)
```

**Squid EC2 IAM Role:**
```
Trust: ec2.amazonaws.com
Policies:
  - logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents
  - AmazonSSMManagedInstanceCore (managed policy)
```

### Component 7: Security Groups

**SG-LiteLLM:**
| Direction | Protocol | Port | Source/Dest | Purpose |
|-----------|----------|------|-------------|---------|
| Inbound | TCP | 4000 | 10.10.0.0/16 | API GW integration |
| Inbound | TCP | 4000 | 192.128.0.0/16 | On-prem direct TGW |
| Outbound | TCP | 443 | 0.0.0.0/0 | OpenAI via NAT, Bedrock via TGW |

**SG-MCP:**
| Direction | Protocol | Port | Source/Dest | Purpose |
|-----------|----------|------|-------------|---------|
| Inbound | TCP | 3000 | 10.10.0.0/16 | API GW/Lambda calls |
| Outbound | TCP | 443 | 0.0.0.0/0 | Lambda VPC Endpoint, Secrets Manager |

**SG-Squid:**
| Direction | Protocol | Port | Source/Dest | Purpose |
|-----------|----------|------|-------------|---------|
| Inbound | TCP | 3128 | 192.128.0.0/16 | Proxy traffic |
| Inbound | TCP | 22 | 192.128.0.0/16 | SSH management |
| Outbound | TCP | 443 | 0.0.0.0/0 | HTTPS via NAT |
| Outbound | UDP/TCP | 53 | 0.0.0.0/0 | DNS resolution |

### Component 8: Secrets Manager

| Secret Name | Purpose | Length |
|-------------|---------|--------|
| llm-gateway/litellm-master-key | LiteLLM admin operations | 32 chars alphanumeric |
| llm-gateway/mcp-api-key | MCP Server authentication | 32 chars alphanumeric |
| llm-gateway/postgres-password | PostgreSQL password | 24 chars alphanumeric |

### Component 9: Monitoring & Alerting

**CloudWatch Alarms:**
| Instance | Metric | Threshold | Period |
|----------|--------|-----------|--------|
| LiteLLM EC2 | CPUUtilization | > 80% | 5 min |
| LiteLLM EC2 | StatusCheckFailed | > 0 | 2 periods |
| MCP EC2 | CPUUtilization | > 80% | 5 min |
| MCP EC2 | StatusCheckFailed | > 0 | 2 periods |
| Squid EC2 | CPUUtilization | > 70% | 5 min |
| Squid EC2 | StatusCheckFailed | > 0 | 2 periods |
| Backup | S3 backup age | > 25 hours | 1 period |

**CloudWatch Log Groups (30-day retention):**
- /llm-gateway/litellm
- /llm-gateway/mcp-server
- /llm-gateway/squid

**SNS Topic:** llm-gateway-alerts

**Health Endpoints:**
- LiteLLM: `GET /health` → 200 (healthy) / 503 (PostgreSQL unreachable)
- MCP Server: `GET /health` → 200 (Lambda connectivity OK)

### Component 10: Backup & Recovery

**Daily PostgreSQL Backup (cron 03:00 KST):**
```bash
#!/bin/bash
# /data/scripts/backup-postgres.sh
BACKUP_DIR=/data/backups
DATE=$(date +%Y%m%d)
FILENAME="postgres-${DATE}.sql.gz"

# Dump and compress
docker exec postgres pg_dump -U litellm litellm | gzip > "${BACKUP_DIR}/${FILENAME}"

# Upload to S3
aws s3 cp "${BACKUP_DIR}/${FILENAME}" \
  s3://s3-bos-ai-backups-seoul-prod/llm-gateway/postgres/${FILENAME}

# Retain only last 7 local backups
ls -t ${BACKUP_DIR}/postgres-*.sql.gz | tail -n +8 | xargs rm -f
```

**Recovery Procedure:**
1. Stop LiteLLM container
2. `gunzip < /data/backups/postgres-latest.sql.gz | docker exec -i postgres psql -U litellm litellm`
3. Start LiteLLM container
4. Verify `/health` returns 200

### Component 11: Deployment & Rollback

**LiteLLM Version Update:**
1. Create pre-update AMI snapshot
2. Update `docker-compose.yml` image tag
3. `docker compose pull && docker compose up -d`
4. Verify `/health` within 120 seconds
5. On failure: Launch Template version switch → instance replace (< 15 min)

**MCP Server Update:**
- systemd service with `ExecStartPre` health check
- Rollback to previous binary if health check fails within 60 seconds

**Squid Config Update:**
- `squid -k parse` validation before apply
- Automatic rollback to `/etc/squid/squid.conf.bak` on parse failure

## Data Models

### LiteLLM Virtual Key (PostgreSQL)

LiteLLM은 자체 스키마를 관리하며, 핵심 엔티티:

```
┌──────────────────────────────┐
│ LiteLLMKey                   │
├──────────────────────────────┤
│ token (PK, varchar)          │
│ key_name (varchar)           │
│ user_id (varchar)            │
│ team_id (varchar)            │
│ max_budget (decimal)         │
│ spend (decimal)              │
│ allowed_models (json array)  │
│ created_at (timestamp)       │
│ expires_at (timestamp)       │
│ status (enum: active/expired)│
└──────────────────────────────┘
```

### MCP Tool Request/Response

```typescript
// MCP Tool Call (incoming)
interface MCPToolRequest {
  jsonrpc: "2.0";
  id: string;
  method: "tools/call";
  params: {
    name: string;  // e.g., "rag_query"
    arguments: Record<string, unknown>;
  };
}

// Lambda Invocation Payload
interface LambdaPayload {
  action: string;       // tool name mapped to Lambda action
  parameters: Record<string, unknown>;
}

// MCP Tool Response
interface MCPToolResponse {
  jsonrpc: "2.0";
  id: string;
  result: {
    content: Array<{ type: "text"; text: string }>;
    isError?: boolean;
  };
}
```

### Squid Access Log Format

```
timestamp elapsed remotehost code/status bytes method URL rfc931 peerstatus/peerhost type
```

### Backup Data Model

```
/data/backups/
├── postgres-20260101.sql.gz   # Daily pg_dump (7-day local retention)
├── postgres-20260102.sql.gz
└── ...

S3: s3-bos-ai-backups-seoul-prod/llm-gateway/postgres/
├── postgres-20260101.sql.gz   # 90-day lifecycle expiration
└── ...
```

## Error Handling

### LiteLLM Error Responses

| Condition | HTTP Status | Response Body |
|-----------|-------------|---------------|
| Invalid/expired Virtual Key | 401 | `{"error": {"message": "Invalid API key: <reason>", "type": "auth_error"}}` |
| Budget exceeded | 429 | `{"error": {"message": "Budget exceeded", "remaining_budget": 0, "type": "budget_error"}, "headers": {"Retry-After": "3600"}}` |
| Queue capacity exceeded | 429 | `{"error": {"message": "Rate limit", "type": "rate_limit"}, "headers": {"Retry-After": "<seconds>"}}` |
| Invalid model | 400 | `{"error": {"message": "Model '<name>' not found", "type": "invalid_request"}}` |
| PostgreSQL unavailable | 503 | `{"error": {"message": "Service unavailable: database connection failure", "type": "service_error"}}` |

### MCP Server Error Responses

| Condition | Error Code | Response |
|-----------|-----------|----------|
| Undefined tool | -32601 | `{"jsonrpc":"2.0","error":{"code":-32601,"message":"Tool not found","data":{"available_tools":[...]}}}` |
| Lambda invocation failure | -32603 | `{"jsonrpc":"2.0","error":{"code":-32603,"message":"Lambda error","data":{"lambda_error":"..."}}}` |
| Invalid API key | -32600 | `{"jsonrpc":"2.0","error":{"code":-32600,"message":"Authentication failed"}}` |

### Squid Error Handling

| Condition | Action |
|-----------|--------|
| Domain not in whitelist | DENY + log (domain, client IP, timestamp) |
| Source IP not in on-prem CIDR | DENY + log |
| Upstream timeout | Return 504 to client |

### Boot-time Failure Handling

| Component | Failure | Recovery |
|-----------|---------|----------|
| Secrets Manager retrieval | Retry 3× (2s, 4s, 8s exponential) | Log to /var/log/user-data.log, halt service start |
| Docker container start | systemd restart: always | Auto-restart with backoff |
| PostgreSQL container fail | Restore from latest /data/backups/*.sql.gz | pg_restore + container restart |

## Testing Strategy

### Assessment: Property-Based Testing Applicability

This feature is primarily **Infrastructure as Code** (Terraform + Docker Compose + Squid config + network routing). The vast majority of requirements describe:
- EC2 instance provisioning (declarative IaC)
- Security group rules (declarative configuration)
- IAM policies (declarative permissions)
- Network routes (infrastructure wiring)
- Docker Compose configurations (declarative)
- Monitoring alarms (declarative)

**PBT is NOT applicable** for this feature because:
1. Terraform configurations are declarative — not functions with inputs/outputs
2. Security groups and IAM policies are static configuration, not dynamic logic
3. Network routing is infrastructure wiring verified by integration tests
4. Docker Compose is declarative service definition
5. No meaningful "for all inputs X, property P(X) holds" statements exist

### Recommended Testing Approach

**1. Terraform Plan Validation (snapshot-style)**
- `terraform plan` → verify no destructive changes to existing resources
- `terraform validate` + `tflint` for syntax/convention compliance
- OPA/Rego policies for security compliance (encryption, no public IP, IMDSv2)

**2. Go Integration Tests** (`tests/integration/`)
- Verify EC2 instances are running with correct instance type, AMI, VPC placement
- Verify security group rules match specification
- Verify IAM role policies contain required permissions
- Verify Route53 records resolve correctly
- Verify API Gateway routes respond (health endpoints)
- Verify TGW route propagation (Logging VPC ↔ Frontend VPC connectivity)

**3. Go Property-Based Tests** (`tests/properties/`)
- Verify Terraform plan output contains required tags on all resources
- Verify all EBS volumes are encrypted
- Verify no public IPs assigned
- Verify IMDSv2 enforced on all instances

**4. Service Health Smoke Tests**
- LiteLLM `/health` returns 200
- MCP Server `/health` returns 200
- Squid accepts CONNECT to whitelisted domain
- Squid denies CONNECT to non-whitelisted domain

**5. End-to-End Integration Tests**
- On-prem → API GW → LiteLLM → OpenAI (GPT model call)
- On-prem → API GW → MCP Server → Lambda (rag_query tool)
- On-prem → Squid → api.openai.com (CONNECT)

**6. Backup Verification Tests**
- pg_dump creates valid backup file
- S3 upload succeeds
- pg_restore from backup restores data correctly

### Test File Mapping

| Test File | Coverage |
|-----------|----------|
| `tests/integration/llm_gateway_litellm_test.go` | Req 1-3, 11, 13, 16, 18, 23-26 |
| `tests/integration/llm_gateway_mcp_test.go` | Req 4-5, 12, 14, 16 |
| `tests/integration/llm_gateway_squid_test.go` | Req 6-7, 15, 20 |
| `tests/integration/llm_gateway_network_test.go` | Req 8, 19-20 |
| `tests/integration/llm_gateway_apigw_test.go` | Req 9-10, 17 |
| `tests/properties/llm_gateway_compliance_test.go` | Req 21-22 (tag/encryption/IMDS compliance) |
| `policies/llm_gateway.rego` | Req 21-22 (no destructive changes, security baseline) |
