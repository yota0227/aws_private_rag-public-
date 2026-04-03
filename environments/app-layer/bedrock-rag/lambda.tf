# Lambda Configuration for Seoul Consolidated VPC
# Creates Lambda function for document processing with VPC connectivity
# Requirements: 3.3, NFR-1, NFR-2

# Security Group for Lambda - Private RAG VPC (서울 Frontend)
# Requirements: 2.1, 2.2
resource "aws_security_group" "lambda" {
  provider = aws.seoul

  name        = "lambda-private-rag-${var.environment}"
  description = "Lambda document processor - Private RAG VPC (Seoul Frontend)"
  vpc_id      = local.frontend_vpc_id  # Private RAG VPC (10.10.0.0/16)

  # No inbound rules needed for Lambda

  # Outbound: HTTPS to Virginia VPC (via VPC Peering) - Bedrock, OpenSearch, S3
  egress {
    description = "HTTPS to Virginia Backend VPC via VPC Peering"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.20.0.0/16"]
  }

  # Outbound: HTTPS to Seoul VPC Endpoints (CloudWatch Logs, Secrets Manager, etc.)
  egress {
    description = "HTTPS to Seoul VPC Endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.10.0.0/16"]
  }

  # Outbound: HTTPS to S3 via S3 Gateway Endpoint (prefix list)
  # S3 Gateway Endpoint는 ENI가 없어 VPC CIDR로 커버되지 않음
  # 트래픽은 AWS 내부 백본을 통해 전달되며 인터넷을 거치지 않음
  egress {
    description     = "HTTPS to S3 via Gateway Endpoint"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = ["pl-78a54011"]
  }

  tags = merge(local.common_tags, {
    Name    = "lambda-private-rag-${var.environment}"
    Purpose = "Lambda document processor - Frontend"
  })
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda" {
  name        = "role-lambda-document-processor-seoul-prod"
  description = "IAM role for Lambda document processor with minimal permissions"

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

  tags = {
    Name        = "role-lambda-document-processor-seoul-prod"
    Project     = "BOS-AI"
    Environment = "Production"
    ManagedBy   = "Terraform"
    Layer       = "Security"
  }
}

# IAM Policy for Lambda - S3 Access
resource "aws_iam_role_policy" "lambda_s3" {
  name = "lambda-s3-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:CreateMultipartUpload",
          "s3:UploadPart",
          "s3:CompleteMultipartUpload",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts"
        ]
        Resource = [
          "arn:aws:s3:::bos-ai-documents-*",
          "arn:aws:s3:::bos-ai-documents-*/*"
        ]
      }
    ]
  })
}

# IAM Policy for Lambda - OpenSearch Access (Cross-Region: us-east-1)
resource "aws_iam_role_policy" "lambda_opensearch" {
  name = "lambda-opensearch-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "aoss:APIAccessAll"
        ]
        Resource = [
          "arn:aws:aoss:us-east-1:533335672315:collection/*"
        ]
      }
    ]
  })
}

# IAM Policy for Lambda - Bedrock Access (Cross-Region: us-east-1)
resource "aws_iam_role_policy" "lambda_bedrock" {
  name = "lambda-bedrock-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:Retrieve",
          "bedrock:RetrieveAndGenerate",
          "bedrock:GetInferenceProfile"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:us-east-1:533335672315:knowledge-base/*",
          "arn:aws:bedrock:*:533335672315:inference-profile/*",
          "arn:aws:bedrock:*::inference-profile/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:StartIngestionJob",
          "bedrock:GetIngestionJob",
          "bedrock:ListIngestionJobs"
        ]
        Resource = [
          "arn:aws:bedrock:us-east-1:533335672315:knowledge-base/*"
        ]
      }
    ]
  })
}

# IAM Policy for Lambda - Secrets Manager Access
resource "aws_iam_role_policy" "lambda_secrets" {
  name = "lambda-secrets-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          "arn:aws:secretsmanager:ap-northeast-2:533335672315:secret:opensearch/*"
        ]
      }
    ]
  })
}

# IAM Policy for Lambda - CloudWatch Logs
resource "aws_iam_role_policy" "lambda_logs" {
  name = "lambda-logs-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = [
          "arn:aws:logs:ap-northeast-2:533335672315:log-group:/aws/lambda/lambda-document-processor-seoul-prod:*"
        ]
      }
    ]
  })
}

# IAM Policy for Lambda - VPC Access (ENI management)
resource "aws_iam_role_policy" "lambda_vpc" {
  name = "lambda-vpc-access"
  role = aws_iam_role.lambda.id

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

# IAM Policy for Lambda - KMS Access (Seoul S3 SSE-KMS 암호화)
resource "aws_iam_role_policy" "lambda_kms" {
  name = "lambda-kms-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey",
          "kms:GenerateDataKeyWithoutPlaintext",
          "kms:ReEncryptFrom",
          "kms:ReEncryptTo"
        ]
        Resource = [
          aws_kms_key.s3_seoul.arn
        ]
      }
    ]
  })
}

# IAM Policy for Lambda - DynamoDB Access (Extraction Task 상태 추적)
# Requirements: 7.3, 7.4, 7.5 | Design: 5.5
resource "aws_iam_role_policy" "lambda_dynamodb" {
  name = "lambda-dynamodb-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.extraction_tasks.arn
        ]
      }
    ]
  })
}

# IAM Policy for Lambda - Self Invoke (비동기 압축 해제 호출)
# Requirements: 7.3 | Design: 5.5
resource "aws_iam_role_policy" "lambda_self_invoke" {
  name = "lambda-self-invoke"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.document_processor.arn
      }
    ]
  })
}

# Lambda Function - Seoul Private RAG VPC
# Requirements: 2.1, 2.2, 2.11
resource "aws_lambda_function" "document_processor" {
  provider = aws.seoul

  filename         = "lambda-deployment-package.zip"
  function_name    = "lambda-document-processor-seoul-prod"
  role             = aws_iam_role.lambda.arn
  handler          = "index.handler"
  source_code_hash = filebase64sha256("lambda-deployment-package.zip")
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 512

  # /tmp 디스크 확대: 압축 파일 해제를 위해 3072MB (3GB) 할당
  # Requirements: 3.4 | Design: 5.3
  ephemeral_storage {
    size = 3072
  }

  # VPC Configuration - Private RAG VPC (Seoul Frontend)
  vpc_config {
    subnet_ids         = local.frontend_private_subnet_ids  # 10.10.1.0/24, 10.10.2.0/24
    security_group_ids = [aws_security_group.lambda.id]
  }

  # Environment Variables
  environment {
    variables = {
      OPENSEARCH_ENDPOINT  = data.aws_opensearchserverless_collection.virginia.collection_endpoint
      OPENSEARCH_INDEX     = "bos-ai-documents"
      BEDROCK_MODEL_ID     = "amazon.titan-embed-text-v1"
      BEDROCK_REGION       = "us-east-1"
      S3_BUCKET_VIRGINIA   = "bos-ai-documents-us"
      S3_BUCKET_SEOUL      = "bos-ai-documents-seoul-v3"
      SECRET_NAME          = "opensearch/bos-ai-rag-prod"
      LAMBDA_REGION        = "ap-northeast-2"
      BACKEND_REGION       = "us-east-1"
      BEDROCK_KB_ID            = module.bedrock_rag.knowledge_base_id
      BEDROCK_KB_DATA_SOURCE_ID = var.bedrock_kb_data_source_id
      FOUNDATION_MODEL_ARN     = var.foundation_model_arn
      DYNAMODB_TABLE           = aws_dynamodb_table.extraction_tasks.name
      SEARCH_TYPE              = var.search_type
      SEARCH_RESULTS_COUNT     = tostring(var.search_results_count)
    }
  }

  tags = merge(local.common_tags, {
    Name    = "lambda-document-processor-seoul-prod"
    Purpose = "RAG Document Processor - Frontend"
    Layer   = "Compute"
  })

  depends_on = [
    aws_iam_role_policy.lambda_s3,
    aws_iam_role_policy.lambda_opensearch,
    aws_iam_role_policy.lambda_bedrock,
    aws_iam_role_policy.lambda_secrets,
    aws_iam_role_policy.lambda_logs,
    aws_iam_role_policy.lambda_vpc,
    aws_iam_role_policy.lambda_kms,
    aws_iam_role_policy.lambda_dynamodb
    # Note: lambda_self_invoke는 Lambda ARN을 참조하므로 depends_on에 포함하면 순환 의존성 발생
    # Lambda 생성 후 자동으로 self_invoke 정책이 적용됨
  ]
}

# Lambda Event Invocation 자동 재시도를 0으로 제한
# AWS 기본값: 실패 시 최대 2회 자동 재시도 → 압축 해제 중복 실행/상태 꼬임 방지
# Requirements: 7.3 | Design: 5.4
resource "aws_lambda_function_event_invoke_config" "document_processor_async" {
  provider = aws.seoul

  function_name                = aws_lambda_function.document_processor.function_name
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 300
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/lambda-document-processor-seoul-prod"
  retention_in_days = 30

  tags = {
    Name        = "lambda-document-processor-seoul-prod-logs"
    Project     = "BOS-AI"
    Environment = "Production"
    ManagedBy   = "Terraform"
  }
}

# CloudWatch Metric Filter - RAG 인용 0건 질의 감지
# Requirements: 7.3
resource "aws_cloudwatch_log_metric_filter" "no_citation_query" {
  name           = "rag-no-citation-query"
  log_group_name = aws_cloudwatch_log_group.lambda.name
  pattern        = "{ $.event = \"no_citation_query\" }"

  metric_transformation {
    name          = "RAGNoCitationCount"
    namespace     = "BOS-AI/RAG"
    value         = "1"
    default_value = "0"
  }
}

# S3 Event Notification (to be configured on Virginia S3 bucket)
# Note: This needs to be configured separately on the Virginia S3 bucket
# resource "aws_s3_bucket_notification" "bucket_notification" {
#   bucket = "bos-ai-documents-us"
#
#   lambda_function {
#     lambda_function_arn = aws_lambda_function.document_processor.arn
#     events              = ["s3:ObjectCreated:*"]
#     filter_prefix       = "documents/"
#   }
# }

# Lambda Permission for S3 to invoke
resource "aws_lambda_permission" "allow_s3" {
  provider = aws.seoul

  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.document_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = "arn:aws:s3:::bos-ai-documents-us"
}

# Outputs moved to outputs.tf to avoid duplication

output "lambda_role_arn" {
  description = "Lambda IAM role ARN"
  value       = aws_iam_role.lambda.arn
}

output "lambda_security_group_id" {
  description = "Lambda security group ID"
  value       = aws_security_group.lambda.id
}

# Note: Before deploying:
# 1. Create the Lambda deployment package (lambda-deployment-package.zip)
# 2. Replace subnet IDs with actual private subnet IDs
# 3. Configure S3 event notification on Virginia bucket
# 4. Test Lambda function with sample document
