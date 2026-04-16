# ============================================================================
# RTL Parser Lambda - RTL 구조 파싱 전용 Lambda 함수
# Purpose: RTL 소스 코드를 정규식 기반으로 파싱하여 메타데이터 추출 및 OpenSearch 인덱싱
#
# Requirements: 2.1, 2.8, 2.10, 13.1, 13.2, 13.4, 13.5, 13.6
# ============================================================================

# ----------------------------------------------------------------------------
# Security Group for RTL Parser Lambda
# ----------------------------------------------------------------------------

resource "aws_security_group" "rtl_parser_lambda" {
  provider = aws.seoul

  name        = "rtl-parser-lambda-sg-${var.environment}"
  description = "RTL Parser Lambda - BOS-AI Frontend VPC (Seoul)"
  vpc_id      = local.frontend_vpc_id

  # Outbound: HTTPS to Seoul VPC Endpoints (S3, DynamoDB, CloudWatch)
  egress {
    description = "HTTPS to Seoul VPC Endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.10.0.0/16"]
  }

  # Outbound: HTTPS to Virginia Backend VPC (OpenSearch, Bedrock via VPC Peering)
  egress {
    description = "HTTPS to Virginia Backend VPC via VPC Peering"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.20.0.0/16"]
  }

  # Outbound: HTTPS to S3 via S3 Gateway Endpoint
  egress {
    description     = "HTTPS to S3 via Gateway Endpoint"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = ["pl-78a54011"]
  }

  tags = merge(local.common_tags, {
    Name    = "sg-rtl-parser-lambda-${var.environment}"
    Purpose = "RTL Parser Lambda Security Group"
  })
}

# ----------------------------------------------------------------------------
# IAM Role for RTL Parser Lambda (최소 권한)
# ----------------------------------------------------------------------------

resource "aws_iam_role" "rtl_parser_lambda" {
  name        = "role-rtl-parser-lambda-seoul-${var.environment}"
  description = "IAM role for RTL Parser Lambda - minimal permissions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name    = "role-rtl-parser-lambda-seoul-${var.environment}"
    Purpose = "RTL Parser Lambda IAM Role"
  })
}

# IAM Policy: S3 - RTL_S3_Bucket GetObject(rtl-sources/*) + PutObject(rtl-parsed/*)
resource "aws_iam_role_policy" "rtl_parser_s3" {
  name = "rtl-parser-s3-access"
  role = aws_iam_role.rtl_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:GetObjectVersion"]
        Resource = [
          "${aws_s3_bucket.rtl_codes.arn}/rtl-sources/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.rtl_codes.arn}/rtl-parsed/*"]
      }
    ]
  })
}

# IAM Policy: OpenSearch - RTL_OpenSearch_Index 인덱싱
resource "aws_iam_role_policy" "rtl_parser_opensearch" {
  name = "rtl-parser-opensearch-access"
  role = aws_iam_role.rtl_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["aoss:APIAccessAll"]
        Resource = ["arn:aws:aoss:us-east-1:${data.aws_caller_identity.current.account_id}:collection/*"]
      }
    ]
  })
}

# IAM Policy: CloudWatch Logs
resource "aws_iam_role_policy" "rtl_parser_logs" {
  name = "rtl-parser-logs-access"
  role = aws_iam_role.rtl_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "arn:aws:logs:ap-northeast-2:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/lambda-rtl-parser-seoul-${var.environment}:*"
        ]
      }
    ]
  })
}

# IAM Policy: KMS - Decrypt/GenerateDataKey (S3 SSE-KMS)
resource "aws_iam_role_policy" "rtl_parser_kms" {
  name = "rtl-parser-kms-access"
  role = aws_iam_role.rtl_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = [aws_kms_key.s3_seoul.arn]
      }
    ]
  })
}

# IAM Policy: Bedrock - Titan Embeddings v2 + Claude 3 Haiku InvokeModel
resource "aws_iam_role_policy" "rtl_parser_bedrock" {
  name = "rtl-parser-bedrock-access"
  role = aws_iam_role.rtl_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0",
          "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
        ]
      }
    ]
  })
}

# IAM Policy: DynamoDB - 에러 테이블 PutItem + UpdateItem + Query (분석 파이프라인 상태 추적)
resource "aws_iam_role_policy" "rtl_parser_dynamodb" {
  name = "rtl-parser-dynamodb-access"
  role = aws_iam_role.rtl_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [aws_dynamodb_table.extraction_tasks.arn]
      }
    ]
  })
}

# IAM Policy: VPC Access (ENI management)
resource "aws_iam_role_policy" "rtl_parser_vpc" {
  name = "rtl-parser-vpc-access"
  role = aws_iam_role.rtl_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
          "ec2:AssignPrivateIpAddresses",
          "ec2:UnassignPrivateIpAddresses"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM Policy: Neptune - WriteDataViaQuery (Phase 6 대비)
resource "aws_iam_role_policy" "rtl_parser_neptune" {
  name = "rtl-parser-neptune-access"
  role = aws_iam_role.rtl_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["neptune-db:WriteDataViaQuery"]
        Resource = ["arn:aws:neptune-db:ap-northeast-2:${data.aws_caller_identity.current.account_id}:*/*"]
      }
    ]
  })
}

# IAM Policy: Step Functions - StartExecution 권한 (분석 파이프라인 트리거)
resource "aws_iam_role_policy" "rtl_parser_sfn" {
  name = "rtl-parser-sfn-access"
  role = aws_iam_role.rtl_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = [aws_sfn_state_machine.analysis_orchestrator.arn]
      }
    ]
  })
}

# ----------------------------------------------------------------------------
# KMS Key for RTL Parser Lambda Environment Variables
# ----------------------------------------------------------------------------

resource "aws_kms_key" "rtl_parser_lambda_env" {
  provider = aws.seoul

  description             = "KMS key for RTL Parser Lambda environment variable encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Name    = "kms-rtl-parser-lambda-env-${var.environment}"
    Purpose = "RTL Parser Lambda env var encryption"
  })
}

resource "aws_kms_alias" "rtl_parser_lambda_env" {
  provider = aws.seoul

  name          = "alias/bos-ai-rtl-parser-lambda-env-${var.environment}"
  target_key_id = aws_kms_key.rtl_parser_lambda_env.key_id
}

# KMS key policy allowing Lambda role to decrypt env vars
resource "aws_iam_role_policy" "rtl_parser_env_kms" {
  name = "rtl-parser-env-kms-access"
  role = aws_iam_role.rtl_parser_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = [aws_kms_key.rtl_parser_lambda_env.arn]
      }
    ]
  })
}

# ----------------------------------------------------------------------------
# CloudWatch Log Group for RTL Parser Lambda
# ----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "rtl_parser_lambda" {
  provider = aws.seoul

  name              = "/aws/lambda/lambda-rtl-parser-seoul-${var.environment}"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Name    = "lambda-rtl-parser-seoul-${var.environment}-logs"
    Purpose = "RTL Parser Lambda CloudWatch Logs"
  })
}

# ----------------------------------------------------------------------------
# RTL Parser Lambda Function
# Python 3.12, 2048MB, 300s timeout, Frontend VPC
# ----------------------------------------------------------------------------

resource "aws_lambda_function" "rtl_parser" {
  provider = aws.seoul

  # NOTE: rtl-parser-deployment-package.zip은 배포 전 빌드 파이프라인에서 생성
  # rtl_parser_src/handler.py + requirements.txt를 패키징하여 생성
  filename         = "rtl-parser-deployment-package.zip"
  function_name    = "lambda-rtl-parser-seoul-${var.environment}"
  role             = aws_iam_role.rtl_parser_lambda.arn
  handler          = "handler.handler"
  source_code_hash = filebase64sha256("rtl-parser-deployment-package.zip")
  runtime          = "python3.12"
  memory_size      = 2048
  timeout          = 300

  # VPC Configuration - BOS-AI Frontend VPC (Seoul, 10.10.0.0/16)
  vpc_config {
    subnet_ids         = local.frontend_private_subnet_ids
    security_group_ids = [aws_security_group.rtl_parser_lambda.id]
  }

  # 환경 변수 KMS 암호화
  kms_key_arn = aws_kms_key.rtl_parser_lambda_env.arn

  environment {
    variables = {
      RTL_S3_BUCKET        = aws_s3_bucket.rtl_codes.bucket
      OPENSEARCH_ENDPOINT  = data.aws_opensearchserverless_collection.virginia.collection_endpoint
      RTL_OPENSEARCH_INDEX = "rtl-knowledge-base-index"
      BEDROCK_REGION       = "us-east-1"
      TITAN_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
      DYNAMODB_ERROR_TABLE = aws_dynamodb_table.extraction_tasks.name
      LAMBDA_REGION        = "ap-northeast-2"
      STEP_FUNCTIONS_ARN   = "arn:aws:states:ap-northeast-2:${data.aws_caller_identity.current.account_id}:stateMachine:analysis-orchestrator-${var.environment}"
      CLAUDE_MODEL_ID      = "anthropic.claude-3-haiku-20240307-v1:0"
      CLAIM_DB_TABLE       = aws_dynamodb_table.claim_db.name
    }
  }

  tags = merge(local.common_tags, {
    Name    = "lambda-rtl-parser-seoul-${var.environment}"
    Purpose = "RTL Source Code Parser"
    Layer   = "Compute"
  })

  depends_on = [
    aws_iam_role_policy.rtl_parser_s3,
    aws_iam_role_policy.rtl_parser_opensearch,
    aws_iam_role_policy.rtl_parser_logs,
    aws_iam_role_policy.rtl_parser_kms,
    aws_iam_role_policy.rtl_parser_bedrock,
    aws_iam_role_policy.rtl_parser_dynamodb,
    aws_iam_role_policy.rtl_parser_vpc,
    aws_cloudwatch_log_group.rtl_parser_lambda,
  ]
}

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

output "rtl_parser_lambda_arn" {
  description = "RTL Parser Lambda function ARN"
  value       = aws_lambda_function.rtl_parser.arn
}

output "rtl_parser_lambda_role_arn" {
  description = "RTL Parser Lambda IAM role ARN"
  value       = aws_iam_role.rtl_parser_lambda.arn
}
