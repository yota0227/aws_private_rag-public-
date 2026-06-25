# ============================================================================
# Tool Guide Parser Lambda — EDA 툴 가이드 문서 파싱 전용 Lambda
#
# Purpose : S3 bos-ai-toolguide-docs-seoul 버킷 ObjectCreated 이벤트를
#           수신하여 PDF/MD 문서를 결정론적으로 파싱, Qdrant tool-guide-knowledge-base
#           컬렉션 + DynamoDB claim-db + S3 published 경로에 적재.
#
# Design ref : .kiro/specs/eda-tool-guide-rag/design.md (C1, C2, C3, C4)
# Requirements: R1, R2, R3, R5.1, R5.2, R5.3
#
# Created: 2026-06-18
# ============================================================================

# ----------------------------------------------------------------------------
# Security Group — Tool Guide Parser Lambda
# RTL Parser Lambda SG와 동일한 egress 패턴(Qdrant:6333, HTTPS:443)
# ----------------------------------------------------------------------------

resource "aws_security_group" "tool_guide_parser_lambda" {
  provider = aws.seoul

  name        = "tool-guide-parser-lambda-sg-${var.environment}"
  description = "Tool Guide Parser Lambda - BOS-AI Frontend VPC (Seoul)"
  vpc_id      = local.frontend_vpc_id

  egress {
    description = "HTTPS to Seoul VPC Endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.10.0.0/16"]
  }

  egress {
    description = "HTTPS to Virginia Backend VPC via VPC Peering (Bedrock)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.20.0.0/16"]
  }

  egress {
    description     = "HTTPS to S3 via Gateway Endpoint"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = ["pl-78a54011"]
  }

  egress {
    description     = "HTTPS to DynamoDB via Gateway Endpoint"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = ["pl-48a54021"]
  }

  egress {
    description = "Qdrant REST API to Virginia Backend VPC via VPC Peering"
    from_port   = 6333
    to_port     = 6333
    protocol    = "tcp"
    cidr_blocks = ["10.20.0.0/16"]
  }

  tags = merge(local.common_tags, {
    Name     = "sg-tool-guide-parser-lambda-${var.environment}"
    Purpose  = "Tool Guide Parser Lambda Security Group"
    Pipeline = "tool-guide"
  })
}

# ----------------------------------------------------------------------------
# IAM Role — Tool Guide Parser Lambda
# ----------------------------------------------------------------------------

resource "aws_iam_role" "tool_guide_parser_lambda" {
  name        = "role-tool-guide-parser-lambda-${var.environment}"
  description = "IAM role for Tool Guide Parser Lambda - minimal permissions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(local.common_tags, {
    Name     = "role-tool-guide-parser-lambda-${var.environment}"
    Purpose  = "Tool Guide Parser Lambda IAM Role"
    Pipeline = "tool-guide"
  })
}

# S3: Tool Guide 전용 버킷에서 읽기 + published/ 쓰기
resource "aws_iam_role_policy" "tool_guide_parser_s3" {
  name = "tool-guide-parser-s3-access"
  role = aws_iam_role.tool_guide_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion"]
        Resource = ["${aws_s3_bucket.tool_guide_docs_seoul.arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.tool_guide_docs_seoul.arn}/published/*"]
      }
    ]
  })
}

# CloudWatch Logs
resource "aws_iam_role_policy" "tool_guide_parser_logs" {
  name = "tool-guide-parser-logs-access"
  role = aws_iam_role.tool_guide_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = [
        "arn:aws:logs:ap-northeast-2:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/lambda-tool-guide-parser-seoul-${var.environment}:*"
      ]
    }]
  })
}

# KMS: S3 SSE-KMS 복호화/암호화
resource "aws_iam_role_policy" "tool_guide_parser_kms" {
  name = "tool-guide-parser-kms-access"
  role = aws_iam_role.tool_guide_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
      Resource = [aws_kms_key.s3_seoul.arn]
    }]
  })
}

# Bedrock: Titan Embed v2 임베딩 + Claude Vision(Converse) 호출 (R1.5/R7)
resource "aws_iam_role_policy" "tool_guide_parser_bedrock" {
  name = "tool-guide-parser-bedrock-access"
  role = aws_iam_role.tool_guide_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ]
      Resource = [
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
        "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*"
      ]
    }]
  })
}

# DynamoDB: 기존 claim-db 테이블에 pipeline_id=tool-guide 파티션으로 upsert (R1.5)
resource "aws_iam_role_policy" "tool_guide_parser_dynamodb" {
  name = "tool-guide-parser-dynamodb-access"
  role = aws_iam_role.tool_guide_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
      Resource = [aws_dynamodb_table.claim_db.arn]
    }]
  })
}

# VPC: ENI 관리
resource "aws_iam_role_policy" "tool_guide_parser_vpc" {
  name = "tool-guide-parser-vpc-access"
  role = aws_iam_role.tool_guide_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DeleteNetworkInterface",
        "ec2:AssignPrivateIpAddresses",
        "ec2:UnassignPrivateIpAddresses"
      ]
      Resource = "*"
    }]
  })
}

# Secrets Manager: Qdrant API Key 조회
resource "aws_iam_role_policy" "tool_guide_parser_qdrant_secret" {
  name = "tool-guide-parser-qdrant-secret-access"
  role = aws_iam_role.tool_guide_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = ["arn:aws:secretsmanager:ap-northeast-2:${data.aws_caller_identity.current.account_id}:secret:qdrant/api-key-*"]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = ["arn:aws:kms:ap-northeast-2:${data.aws_caller_identity.current.account_id}:key/*"]
        Condition = {
          StringEquals = {
            "kms:ViaService" = "secretsmanager.ap-northeast-2.amazonaws.com"
          }
        }
      }
    ]
  })
}

# ----------------------------------------------------------------------------
# KMS Key: Lambda 환경 변수 암호화
# ----------------------------------------------------------------------------

resource "aws_kms_key" "tool_guide_parser_lambda_env" {
  provider = aws.seoul

  description             = "KMS key for Tool Guide Parser Lambda environment variable encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Name     = "kms-tool-guide-parser-lambda-env-${var.environment}"
    Purpose  = "Tool Guide Parser Lambda env var encryption"
    Pipeline = "tool-guide"
  })
}

resource "aws_kms_alias" "tool_guide_parser_lambda_env" {
  provider = aws.seoul

  name          = "alias/bos-ai-tool-guide-parser-lambda-env-${var.environment}"
  target_key_id = aws_kms_key.tool_guide_parser_lambda_env.key_id
}

resource "aws_iam_role_policy" "tool_guide_parser_env_kms" {
  name = "tool-guide-parser-env-kms-access"
  role = aws_iam_role.tool_guide_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
      Resource = [aws_kms_key.tool_guide_parser_lambda_env.arn]
    }]
  })
}

# ----------------------------------------------------------------------------
# CloudWatch Log Group
# ----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "tool_guide_parser_lambda" {
  provider = aws.seoul

  name              = "/aws/lambda/lambda-tool-guide-parser-seoul-${var.environment}"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Name     = "lambda-tool-guide-parser-seoul-${var.environment}-logs"
    Purpose  = "Tool Guide Parser Lambda CloudWatch Logs"
    Pipeline = "tool-guide"
  })
}

# ----------------------------------------------------------------------------
# Tool Guide Parser Lambda Function
# Python 3.12, Frontend VPC, 전용 S3 버킷 트리거
#
# NOTE: 배포 전 반드시 zip 패키지를 먼저 빌드해야 한다:
#   cd c:\Users\Seung-IlWoo\aws_private_rag\tool_guide_parser_src
#   Compress-Archive -Path * -DestinationPath ..\environments\app-layer\bedrock-rag\tool-guide-parser-deployment-package.zip -Force
# ----------------------------------------------------------------------------

resource "aws_lambda_function" "tool_guide_parser" {
  provider = aws.seoul

  filename         = "tool-guide-parser-deployment-package.zip"
  function_name    = "lambda-tool-guide-parser-seoul-${var.environment}"
  role             = aws_iam_role.tool_guide_parser_lambda.arn
  handler          = "handler.lambda_handler"
  source_code_hash = filebase64sha256("tool-guide-parser-deployment-package.zip")
  runtime          = "python3.12"
  memory_size      = 3008
  timeout          = 900

  ephemeral_storage {
    size = 1024
  }

  reserved_concurrent_executions = 5

  vpc_config {
    subnet_ids         = local.frontend_private_subnet_ids
    security_group_ids = [aws_security_group.tool_guide_parser_lambda.id]
  }

  kms_key_arn = aws_kms_key.tool_guide_parser_lambda_env.arn

  environment {
    variables = {
      TOOL_GUIDE_S3_BUCKET      = aws_s3_bucket.tool_guide_docs_seoul.bucket
      BEDROCK_REGION            = "us-east-1"
      TITAN_EMBED_MODEL_ID      = "amazon.titan-embed-text-v2:0"
      CLAIM_DB_TABLE            = aws_dynamodb_table.claim_db.name
      QDRANT_ENDPOINT           = "http://10.20.1.217:6333"
      QDRANT_COLLECTION         = "tool-guide-knowledge-base"
      QDRANT_API_KEY_SECRET_ARN = "arn:aws:secretsmanager:ap-northeast-2:${data.aws_caller_identity.current.account_id}:secret:qdrant/api-key-t9KnjZ"
      PIPELINE_ID               = "tool-guide"
      PARSE_MODE                = "reference"
      # R7 Vision 다이어그램 파싱 — 텍스트 희소 페이지(<100자)를 Claude Vision으로
      # 설명 생성. 비용 발생하므로 의도적으로 켤 때만 true(R7.5). 모델은 검증된
      # cross-region 추론 프로파일(us. prefix) 사용.
      ENABLE_VISION_PARSING = "true"
      VISION_MODEL_ID       = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    }
  }

  tags = merge(local.common_tags, {
    Name     = "lambda-tool-guide-parser-seoul-${var.environment}"
    Purpose  = "EDA Tool Guide Document Parser"
    Layer    = "Compute"
    Pipeline = "tool-guide"
  })

  depends_on = [
    aws_iam_role_policy.tool_guide_parser_s3,
    aws_iam_role_policy.tool_guide_parser_logs,
    aws_iam_role_policy.tool_guide_parser_kms,
    aws_iam_role_policy.tool_guide_parser_bedrock,
    aws_iam_role_policy.tool_guide_parser_dynamodb,
    aws_iam_role_policy.tool_guide_parser_vpc,
    aws_cloudwatch_log_group.tool_guide_parser_lambda,
  ]
}

# ----------------------------------------------------------------------------
# DLQ: 파싱 실패 이벤트 캡처 (비용 폭발 방지)
# ----------------------------------------------------------------------------

resource "aws_sqs_queue" "tool_guide_parser_dlq" {
  provider = aws.seoul
  name     = "sqs-tool-guide-parser-dlq-${var.environment}"

  message_retention_seconds = 1209600 # 14일

  tags = merge(local.common_tags, {
    Name     = "sqs-tool-guide-parser-dlq-${var.environment}"
    Purpose  = "Tool Guide Parser Lambda failed event capture"
    Pipeline = "tool-guide"
  })
}

resource "aws_lambda_function_event_invoke_config" "tool_guide_parser" {
  provider      = aws.seoul
  function_name = aws_lambda_function.tool_guide_parser.function_name

  maximum_retry_attempts = 0

  destination_config {
    on_failure {
      destination = aws_sqs_queue.tool_guide_parser_dlq.arn
    }
  }

  depends_on = [aws_iam_role_policy.tool_guide_parser_dlq]
}

resource "aws_iam_role_policy" "tool_guide_parser_dlq" {
  name = "tool-guide-parser-dlq-send"
  role = aws_iam_role.tool_guide_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = [aws_sqs_queue.tool_guide_parser_dlq.arn]
    }]
  })
}

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

output "tool_guide_parser_lambda_arn" {
  description = "Tool Guide Parser Lambda function ARN"
  value       = aws_lambda_function.tool_guide_parser.arn
}

output "tool_guide_parser_lambda_role_arn" {
  description = "Tool Guide Parser Lambda IAM role ARN"
  value       = aws_iam_role.tool_guide_parser_lambda.arn
}

output "tool_guide_parser_dlq_url" {
  description = "Tool Guide Parser DLQ URL (파싱 실패 이벤트 확인용)"
  value       = aws_sqs_queue.tool_guide_parser_dlq.url
}
