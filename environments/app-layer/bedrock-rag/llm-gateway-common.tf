# LLM Gateway - Common Resources (Shared by MCP Server, Nginx)
#
# NOTE: LiteLLM has been moved to On-Premises (192.128.10.102).
#       AWS LiteLLM EC2 (10.200.1.113) terminated on 2026-05-29.
#       This file retains only shared resources used by MCP/Nginx.

# =============================================================================
# Locals - Common tags for LLM Gateway resources
# =============================================================================

locals {
  llm_gateway_tags = {
    Project     = "BOS-AI"
    Environment = "prod"
    ManagedBy   = "terraform"
    Layer       = "app"
  }
}

# =============================================================================
# Secrets Manager - MCP API Key (retained for future use)
# =============================================================================

resource "random_password" "mcp_api_key" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "mcp_api_key" {
  name        = "llm-gateway/mcp-api-key"
  description = "MCP Server authentication API key (currently disabled — network isolation mode)"

  tags = merge(local.llm_gateway_tags, {
    Name = "llm-gateway/mcp-api-key"
  })
}

resource "aws_secretsmanager_secret_version" "mcp_api_key" {
  secret_id     = aws_secretsmanager_secret.mcp_api_key.id
  secret_string = random_password.mcp_api_key.result
}

# =============================================================================
# SNS Topic - Alarm Notifications (used by MCP + Nginx alarms)
# =============================================================================

resource "aws_sns_topic" "llm_gateway_alerts" {
  provider = aws.seoul
  name     = "llm-gateway-alerts"

  tags = merge(local.llm_gateway_tags, {
    Name = "llm-gateway-alerts"
  })
}
