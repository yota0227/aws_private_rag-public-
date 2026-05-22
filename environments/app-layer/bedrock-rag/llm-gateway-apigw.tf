# ============================================================================
# LLM Gateway - API Gateway Routes (/llm, /mcp)
# Purpose: 기존 Private REST API에 LiteLLM 및 MCP Server 프록시 경로 추가
#
# Endpoints:
#   ANY /llm/{proxy+}  → HTTP_PROXY → LiteLLM EC2:4000 (Logging VPC)
#   ANY /mcp/{proxy+}  → HTTP_PROXY → MCP Server EC2:3000 (Frontend VPC)
#
# Note: Uses existing aws_api_gateway_rest_api.private_rag (private-rag-api-prod)
#       defined in api-gateway.tf. Cross-VPC connectivity (API GW in Frontend VPC
#       → LiteLLM in Logging VPC) is handled via TGW routing.
#
# Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 21.1
# ============================================================================

# ----------------------------------------------------------------------------
# /llm Resource and Integration
# ----------------------------------------------------------------------------

# /llm resource under root
resource "aws_api_gateway_resource" "llm" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_rest_api.private_rag.root_resource_id
  path_part   = "llm"
}

# /llm/{proxy+} resource
resource "aws_api_gateway_resource" "llm_proxy" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.llm.id
  path_part   = "{proxy+}"
}

# ANY method on /llm/{proxy+}
resource "aws_api_gateway_method" "llm_proxy_any" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.llm_proxy.id
  http_method   = "ANY"
  authorization = "NONE"

  request_parameters = {
    "method.request.path.proxy" = true
  }
}

# HTTP_PROXY integration to LiteLLM EC2 (Logging VPC, cross-VPC via TGW)
resource "aws_api_gateway_integration" "llm_proxy_http" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.llm_proxy.id
  http_method             = aws_api_gateway_method.llm_proxy_any.http_method
  type                    = "HTTP_PROXY"
  integration_http_method = "ANY"
  uri                     = "http://${aws_instance.litellm.private_ip}:4000/{proxy}"
  connection_type         = "INTERNET"

  request_parameters = {
    "integration.request.path.proxy" = "method.request.path.proxy"
  }
}

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
# Deployment — Redeploy prod stage after adding LLM Gateway routes
# Note: The existing prod stage (aws_api_gateway_stage.prod in api-gateway.tf)
#       will be updated to reference this deployment upon next terraform apply.
# ----------------------------------------------------------------------------

resource "aws_api_gateway_deployment" "llm_gateway" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id

  # Trigger redeployment when any LLM Gateway route changes
  triggers = {
    redeployment = sha1(join(",", [
      jsonencode(aws_api_gateway_resource.llm.id),
      jsonencode(aws_api_gateway_resource.llm_proxy.id),
      jsonencode(aws_api_gateway_method.llm_proxy_any.id),
      jsonencode(aws_api_gateway_integration.llm_proxy_http.id),
      jsonencode(aws_api_gateway_resource.mcp.id),
      jsonencode(aws_api_gateway_resource.mcp_proxy.id),
      jsonencode(aws_api_gateway_method.mcp_proxy_any.id),
      jsonencode(aws_api_gateway_integration.mcp_proxy_http.id),
    ]))
  }

  # Ensure all resources are created before deployment
  depends_on = [
    aws_api_gateway_integration.llm_proxy_http,
    aws_api_gateway_integration.mcp_proxy_http,
  ]

  lifecycle {
    create_before_destroy = true
  }
}
