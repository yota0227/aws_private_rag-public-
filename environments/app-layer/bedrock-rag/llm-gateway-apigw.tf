# ============================================================================
# LLM Gateway - API Gateway Routes (/mcp only)
# Purpose: 기존 Private REST API에 MCP Server 프록시 경로 추가
#
# Endpoints:
#   ANY /mcp/{proxy+}  → HTTP_PROXY → MCP Server EC2:3000 (Frontend VPC)
#
# NOTE: /llm route removed on 2026-05-29.
#       LiteLLM is now On-Premises (192.128.10.102), accessed directly by clients.
#       DNS llm.corp.bos-semi.com → On-Prem IP (사내 BIND 직접 등록)
#
# Requirements: 9.3, 9.4, 9.5, 9.6
# ============================================================================

# ----------------------------------------------------------------------------
# /mcp Resource and Integration
# ----------------------------------------------------------------------------

# /mcp resource under root
resource "aws_api_gateway_resource" "mcp" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_rest_api.private_rag.root_resource_id
  path_part   = "mcp"
}

# /mcp/{proxy+} resource
resource "aws_api_gateway_resource" "mcp_proxy" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.mcp.id
  path_part   = "{proxy+}"
}

# ANY method on /mcp/{proxy+}
resource "aws_api_gateway_method" "mcp_proxy_any" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.mcp_proxy.id
  http_method   = "ANY"
  authorization = "NONE"

  request_parameters = {
    "method.request.path.proxy" = true
  }
}

# HTTP_PROXY integration to MCP Server EC2 (Frontend VPC, same VPC as API GW)
resource "aws_api_gateway_integration" "mcp_proxy_http" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.mcp_proxy.id
  http_method             = aws_api_gateway_method.mcp_proxy_any.http_method
  type                    = "HTTP_PROXY"
  integration_http_method = "ANY"
  uri                     = "http://${aws_instance.mcp_server.private_ip}:3000/{proxy}"
  connection_type         = "INTERNET"

  request_parameters = {
    "integration.request.path.proxy" = "method.request.path.proxy"
  }
}

# ----------------------------------------------------------------------------
# Deployment — Redeploy prod stage after MCP route changes
# ----------------------------------------------------------------------------

resource "aws_api_gateway_deployment" "llm_gateway" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id

  triggers = {
    redeployment = sha1(join(",", [
      jsonencode(aws_api_gateway_resource.mcp.id),
      jsonencode(aws_api_gateway_resource.mcp_proxy.id),
      jsonencode(aws_api_gateway_method.mcp_proxy_any.id),
      jsonencode(aws_api_gateway_integration.mcp_proxy_http.id),
    ]))
  }

  depends_on = [
    aws_api_gateway_integration.mcp_proxy_http,
  ]

  lifecycle {
    create_before_destroy = true
  }
}
