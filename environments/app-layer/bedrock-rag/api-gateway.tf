# ============================================================================
# Private API Gateway - REST API (Private Type)
# Purpose: 온프렘에서만 접근 가능한 RAG API 엔드포인트
#
# Endpoints:
#   GET  /rag/upload                  - 웹 업로드 UI
#   POST /rag/documents/initiate      - S3 multipart upload 시작
#   POST /rag/documents/upload-part   - chunk 업로드
#   POST /rag/documents/complete      - multipart upload 완료 + KB sync
#   GET  /rag/documents               - 업로드된 파일 목록
#   POST /rag/query                   - RAG 질의
#   GET  /rag/health                  - 헬스체크
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

  # Resource Policy: VPC Endpoint를 통한 요청만 허용
  # Private API는 VPC Endpoint를 통해서만 접근 가능하므로 vpce 조건으로 제어
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowVPCEndpointAccess"
        Effect    = "Allow"
        Principal = "*"
        Action    = "execute-api:Invoke"
        Resource  = "execute-api:/*"
        Condition = {
          StringEquals = {
            "aws:sourceVpce" = local.frontend_execute_api_endpoint_id
          }
        }
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

# /rag/documents/initiate resource
resource "aws_api_gateway_resource" "documents_initiate" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.documents.id
  path_part   = "initiate"
}

# /rag/documents/upload-part resource
resource "aws_api_gateway_resource" "documents_upload_part" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.documents.id
  path_part   = "upload-part"
}

# /rag/documents/complete resource
resource "aws_api_gateway_resource" "documents_complete" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.documents.id
  path_part   = "complete"
}

# /rag/upload resource (웹 UI)
resource "aws_api_gateway_resource" "upload" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.rag.id
  path_part   = "upload"
}

# /rag/health resource
resource "aws_api_gateway_resource" "health" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.rag.id
  path_part   = "health"
}

# /rag/categories resource (팀/카테고리 목록 API)
resource "aws_api_gateway_resource" "categories" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.rag.id
  path_part   = "categories"
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

# GET /rag/documents (파일 목록)
resource "aws_api_gateway_method" "documents_get" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.documents.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "documents_get_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.documents.id
  http_method             = aws_api_gateway_method.documents_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# POST /rag/documents/initiate (multipart upload 시작)
resource "aws_api_gateway_method" "documents_initiate_post" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.documents_initiate.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "documents_initiate_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.documents_initiate.id
  http_method             = aws_api_gateway_method.documents_initiate_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# POST /rag/documents/upload-part (chunk 업로드)
resource "aws_api_gateway_method" "documents_upload_part_post" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.documents_upload_part.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "documents_upload_part_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.documents_upload_part.id
  http_method             = aws_api_gateway_method.documents_upload_part_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# POST /rag/documents/complete (multipart upload 완료)
resource "aws_api_gateway_method" "documents_complete_post" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.documents_complete.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "documents_complete_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.documents_complete.id
  http_method             = aws_api_gateway_method.documents_complete_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# GET /rag/upload (웹 업로드 UI)
resource "aws_api_gateway_method" "upload_get" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.upload.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "upload_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.upload.id
  http_method             = aws_api_gateway_method.upload_get.http_method
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

# GET /rag/categories (팀/카테고리 목록)
resource "aws_api_gateway_method" "categories_get" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.categories.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "categories_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.categories.id
  http_method             = aws_api_gateway_method.categories_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# ----------------------------------------------------------------------------
# Pre-signed URL 업로드 라우트 (Multi-file Upload)
# Requirements: 7.1, 7.6, 10.1 | Design: 5.6
# ----------------------------------------------------------------------------

# /rag/documents/presign resource
resource "aws_api_gateway_resource" "documents_presign" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.documents.id
  path_part   = "presign"
}

# POST /rag/documents/presign (Pre-signed URL 생성)
resource "aws_api_gateway_method" "documents_presign_post" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.documents_presign.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "documents_presign_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.documents_presign.id
  http_method             = aws_api_gateway_method.documents_presign_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# /rag/documents/confirm resource
resource "aws_api_gateway_resource" "documents_confirm" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.documents.id
  path_part   = "confirm"
}

# POST /rag/documents/confirm (업로드 완료 확인)
resource "aws_api_gateway_method" "documents_confirm_post" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.documents_confirm.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "documents_confirm_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.documents_confirm.id
  http_method             = aws_api_gateway_method.documents_confirm_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# /rag/documents/extract resource
resource "aws_api_gateway_resource" "documents_extract" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.documents.id
  path_part   = "extract"
}

# POST /rag/documents/extract (비동기 압축 해제 시작)
resource "aws_api_gateway_method" "documents_extract_post" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.documents_extract.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "documents_extract_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.documents_extract.id
  http_method             = aws_api_gateway_method.documents_extract_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.document_processor.invoke_arn
}

# /rag/documents/extract-status resource
resource "aws_api_gateway_resource" "documents_extract_status" {
  provider = aws.seoul

  rest_api_id = aws_api_gateway_rest_api.private_rag.id
  parent_id   = aws_api_gateway_resource.documents.id
  path_part   = "extract-status"
}

# GET /rag/documents/extract-status (압축 해제 상태 조회)
resource "aws_api_gateway_method" "documents_extract_status_get" {
  provider = aws.seoul

  rest_api_id   = aws_api_gateway_rest_api.private_rag.id
  resource_id   = aws_api_gateway_resource.documents_extract_status.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "documents_extract_status_lambda" {
  provider = aws.seoul

  rest_api_id             = aws_api_gateway_rest_api.private_rag.id
  resource_id             = aws_api_gateway_resource.documents_extract_status.id
  http_method             = aws_api_gateway_method.documents_extract_status_get.http_method
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
      aws_api_gateway_resource.documents_initiate.id,
      aws_api_gateway_resource.documents_upload_part.id,
      aws_api_gateway_resource.documents_complete.id,
      aws_api_gateway_resource.upload.id,
      aws_api_gateway_resource.health.id,
      aws_api_gateway_resource.categories.id,
      aws_api_gateway_resource.documents_presign.id,
      aws_api_gateway_resource.documents_confirm.id,
      aws_api_gateway_resource.documents_extract.id,
      aws_api_gateway_resource.documents_extract_status.id,
      aws_api_gateway_method.query_post.id,
      aws_api_gateway_method.documents_get.id,
      aws_api_gateway_method.documents_initiate_post.id,
      aws_api_gateway_method.documents_upload_part_post.id,
      aws_api_gateway_method.documents_complete_post.id,
      aws_api_gateway_method.upload_get.id,
      aws_api_gateway_method.health_get.id,
      aws_api_gateway_method.categories_get.id,
      aws_api_gateway_method.documents_presign_post.id,
      aws_api_gateway_method.documents_confirm_post.id,
      aws_api_gateway_method.documents_extract_post.id,
      aws_api_gateway_method.documents_extract_status_get.id,
      aws_api_gateway_integration.query_lambda.id,
      aws_api_gateway_integration.documents_get_lambda.id,
      aws_api_gateway_integration.documents_initiate_lambda.id,
      aws_api_gateway_integration.documents_upload_part_lambda.id,
      aws_api_gateway_integration.documents_complete_lambda.id,
      aws_api_gateway_integration.upload_lambda.id,
      aws_api_gateway_integration.health_lambda.id,
      aws_api_gateway_integration.categories_lambda.id,
      aws_api_gateway_integration.documents_presign_lambda.id,
      aws_api_gateway_integration.documents_confirm_lambda.id,
      aws_api_gateway_integration.documents_extract_lambda.id,
      aws_api_gateway_integration.documents_extract_status_lambda.id,
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
