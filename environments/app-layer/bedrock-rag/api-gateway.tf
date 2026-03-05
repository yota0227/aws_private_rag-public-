# ============================================================================
# Private API Gateway - REST API (Private Type)
# Purpose: 온프렘에서만 접근 가능한 RAG API 엔드포인트
#
# Endpoints:
#   POST /rag/query     - RAG 질의
#   POST /rag/documents - 문서 업로드
#   GET  /rag/health    - 헬스체크
#
# Requirements: 2.3, 2.6, 2.7, 2.8, 2.9, 2.10
# ============================================================================

# ----------------------------------------------------------------------------
# REST API (Private)
# ----------------------------------------------------------------------------

resource "aws_api_gateway_rest_api" "private_rag" {
  provider = aws.seoul

  name        = "private-rag-api-${var.environment}"
  description = "Private RAG API - accessible only from on-premises via VPC Endpoint"

  endpoint_configuration {
    types            = ["PRIVATE"]
    vpc_endpoint_ids = [local.frontend_execute_api_endpoint_id]
  }

  # Resource Policy: VPC Endpoint 또는 온프렘 CIDR에서 오는 요청 허용
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = "*"
        Action    = "execute-api:Invoke"
        Resource  = "execute-api:/*"
        Condition = {
          IpAddress = {
            "aws:SourceIp" = "192.128.0.0/16"  # 온프렘 네트워크
          }
        }
      },
      {
        Effect    = "Allow"
        Principal = "*"
        Action    = "execute-api:Invoke"
        Resource  = "execute-api:/*"
        Condition = {
          StringEquals = {
            "aws:sourceVpce" = local.frontend_execute_api_endpoint_id
          }
        }
      },
      {
        Effect    = "Deny"
        Principal = "*"
        Action    = "execute-api:Invoke"
        Resource  = "execute-api:/*"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name    = "private-rag-api-${var.environment}"
    Purpose = "Private RAG API Gateway"
  })
}

# ----------------------------------------------------------------------------
# API Resources & Methods
# ----------------------------------------------------------------------------

# /rag resource
resource "aws_api_gateway_resource" "rag" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_rest_api.private_rag.root_resource_id
  path_part   = "rag"
}

# /rag/query resource
resource "aws_api_gateway_resource" "query" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.rag.id
  path_part   = "query"
}

# /rag/documents resource
resource "aws_api_gateway_resource" "documents" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.rag.id
  path_part   = "documents"
}

# /rag/health resource
resource "aws_api_gateway_resource" "health" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.rag.id
  path_part   = "health"
}

# POST /rag/query
resource "aws_api_gateway_method" "query_post" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.query.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "query_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.query.id
  http_method             = aws_api_gateway_method.query_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# POST /rag/documents
resource "aws_api_gateway_method" "documents_post" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.documents.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "documents_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.documents.id
  http_method             = aws_api_gateway_method.documents_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# GET /rag/health
resource "aws_api_gateway_method" "health_get" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.health.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "health_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.health.id
  http_method             = aws_api_gateway_method.health_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# ----------------------------------------------------------------------------
# Deployment & Stage
# ----------------------------------------------------------------------------

resource "aws_api_gateway_deployment" "main" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.rag.id,
      aws_api_gateway_resource.query.id,
      aws_api_gateway_resource.documents.id,
      aws_api_gateway_resource.health.id,
      aws_api_gateway_method.query_post.id,
      aws_api_gateway_method.documents_post.id,
      aws_api_gateway_method.health_get.id,
      aws_api_gateway_integration.query_lambda.id,
      aws_api_gateway_integration.documents_lambda.id,
      aws_api_gateway_integration.health_lambda.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  provider = aws.seoul

  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  stage_name    = var.environment

  tags = merge(local.common_tags, {
    Name = "private-rag-api-stage-${var.environment}"
  })
}

# ----------------------------------------------------------------------------
# Lambda Permission for API Gateway
# ----------------------------------------------------------------------------

resource "aws_lambda_permission" "api_gateway" {
  provider = aws.seoul

  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.document_processor.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.private_rag.execution_arn}/*/*"
}

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

output "api_gateway_id" {
  description = "Private API Gateway ID"
  value       = aws_api_gateway_rest_api.private_rag.id
}

output "api_gateway_execution_arn" {
  description = "Private API Gateway execution ARN"
  value       = aws_api_gateway_rest_api.private_rag.execution_arn
}

output "api_gateway_stage_invoke_url" {
  description = "API Gateway stage invoke URL (via VPC Endpoint only)"
  value       = aws_api_gateway_stage.prod.invoke_url
}
