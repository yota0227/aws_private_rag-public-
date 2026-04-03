# ============================================================================
# RAG Connector Lambda
# Requirements: 5.1, 5.3, 5.6, 5.7, 5.8, 5.10, 5.11
#
# Quick SPICE 새로고침 시 RAG API를 호출하여 데이터를 가져오는 Lambda
# 비용 최적화: Reserved Concurrency(10) + S3 캐싱(TTL 1h) + SPICE 스케줄
# ============================================================================

# Security Group for RAG Connector Lambda
resource "aws_security_group" "qs_lambda" {
  provider    = aws.seoul
  name        = "quicksight-rag-connector-lambda-prod"
  description = "QuickSight RAG Connector Lambda - outbound to RAG API only"
  vpc_id      = local.frontend_vpc_id

  egress {
    description = "HTTPS to Seoul VPC (RAG API Gateway VPC Endpoint)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.10.0.0/16"]
  }

  tags = merge(local.common_tags, {
    Name    = "quicksight-rag-connector-lambda-prod"
    Purpose = "QuickSight RAG Connector Lambda"
  })
}

# IAM Role for RAG Connector Lambda
resource "aws_iam_role" "qs_lambda" {
  name        = "role-lambda-qs-rag-connector-seoul-prod"
  description = "QuickSight RAG Connector Lambda 실행 역할"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(local.common_tags, {
    Name = "role-lambda-qs-rag-connector-seoul-prod"
  })
}

resource "aws_iam_role_policy" "qs_lambda_policy" {
  name = "qs-rag-connector-policy"
  role = aws_iam_role.qs_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:ap-northeast-2:${local.account_id}:log-group:/aws/lambda/lambda-quick-rag-connector-seoul-prod:*"
      },
      {
        Sid    = "VPCAccess"
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface"
        ]
        Resource = "*"
      },
      {
        Sid    = "S3CacheAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.quicksight_data.arn,
          "${aws_s3_bucket.quicksight_data.arn}/*"
        ]
      },
      {
        Sid    = "KMSAccess"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.quicksight_s3.arn
      }
    ]
  })
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "qs_lambda" {
  provider          = aws.seoul
  name              = "/aws/lambda/lambda-quick-rag-connector-seoul-prod"
  retention_in_days = 90

  tags = merge(local.common_tags, {
    Name = "lambda-quick-rag-connector-seoul-prod-logs"
  })
}

# Lambda Function
resource "aws_lambda_function" "qs_rag_connector" {
  provider = aws.seoul

  # 소스 코드는 lambda/quick-rag-connector/에서 관리
  # 초기 배포 시 placeholder zip 사용, 이후 CI/CD로 업데이트
  filename         = "${path.module}/placeholder.zip"
  function_name    = "lambda-quick-rag-connector-seoul-prod"
  role             = aws_iam_role.qs_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256

  # 비용 최적화: 동시 실행 최대 10개로 제한
  reserved_concurrent_executions = 10

  vpc_config {
    subnet_ids         = local.frontend_subnet_ids
    security_group_ids = [aws_security_group.qs_lambda.id]
  }

  environment {
    variables = {
      RAG_API_ENDPOINT   = "https://rag.corp.bos-semi.com"
      CACHE_BUCKET       = aws_s3_bucket.quicksight_data.bucket
      CACHE_TTL_SECONDS  = "3600"
      LOG_LEVEL          = "INFO"
    }
  }

  tags = merge(local.common_tags, {
    Name    = "lambda-quick-rag-connector-seoul-prod"
    Purpose = "QuickSight RAG data connector"
  })

  depends_on = [
    aws_cloudwatch_log_group.qs_lambda,
    aws_iam_role_policy.qs_lambda_policy
  ]
}

# API Gateway Usage Plan - Quick 전용 스로틀
# Requirements: 5.8
resource "aws_api_gateway_usage_plan" "quicksight" {
  provider = aws.seoul
  name     = "quicksight-rag-api-usage-plan-prod"
  description = "QuickSight RAG API 사용량 제한 - Lambda 폭발 방지"

  throttle_settings {
    rate_limit  = 10   # 초당 10 req
    burst_limit = 20
  }

  quota_settings {
    limit  = 5000   # 일일 5,000 req
    period = "DAY"
  }

  tags = merge(local.common_tags, {
    Name = "quicksight-rag-api-usage-plan-prod"
  })
}

# ──────────────────────────────────────────────
# Outputs
# ──────────────────────────────────────────────
output "qs_lambda_function_name" {
  description = "RAG Connector Lambda 함수명"
  value       = aws_lambda_function.qs_rag_connector.function_name
}

output "qs_lambda_function_arn" {
  description = "RAG Connector Lambda ARN"
  value       = aws_lambda_function.qs_rag_connector.arn
}
