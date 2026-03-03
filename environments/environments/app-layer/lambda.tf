# Lambda Configuration for Seoul Consolidated VPC
# Creates Lambda function for document processing with VPC connectivity
# Requirements: 3.3, NFR-1, NFR-2

# Security Group for Lambda
resource "aws_security_group" "lambda" {
  name        = "lambda-bos-ai-seoul-prod"
  description = "Security group for Lambda document processor"
  vpc_id      = "vpc-066c464f9c750ee9e"  # Seoul consolidated VPC

  # No inbound rules needed for Lambda (Lambda doesn't accept inbound connections)

  # Outbound Rules
  # Allow HTTPS to OpenSearch
  egress {
    description     = "HTTPS to OpenSearch Serverless"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.opensearch.id]
  }

  # Allow HTTPS to VPC Endpoints
  egress {
    description = "HTTPS to VPC Endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.200.0.0/16"]
  }

  # Allow HTTPS to Virginia VPC (via peering)
  egress {
    description = "HTTPS to Virginia VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.20.0.0/16"]
  }

  # Allow all outbound for AWS service access
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "lambda-bos-ai-seoul-prod"
    Project     = "BOS-AI"
    Environment = "Production"
    ManagedBy   = "Terraform"
    Layer       = "Security"
  }
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
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::bos-ai-documents-*",
          "arn:aws:s3:::bos-ai-documents-*/*"
        ]
      }
    ]
  })
}

# IAM Policy for Lambda - OpenSearch Access
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
          "arn:aws:aoss:ap-northeast-2:533335672315:collection/*"
        ]
      }
    ]
  })
}

# IAM Policy for Lambda - Bedrock Access
resource "aws_iam_role_policy" "lambda_bedrock" {
  name = "lambda-bedrock-access"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = [
          "arn:aws:bedrock:ap-northeast-2::foundation-model/*"
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

# Lambda Function
resource "aws_lambda_function" "document_processor" {
  filename         = "lambda-deployment-package.zip"  # Placeholder - needs actual deployment package
  function_name    = "lambda-document-processor-seoul-prod"
  role             = aws_iam_role.lambda.arn
  handler          = "index.handler"
  source_code_hash = filebase64sha256("lambda-deployment-package.zip")
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 512

  # VPC Configuration
  vpc_config {
    subnet_ids         = ["subnet-0f027e9de8e26c18f", "subnet-0625d992edf151017"]  # Replace with actual subnet IDs
    security_group_ids = [aws_security_group.lambda.id]
  }

  # Environment Variables
  environment {
    variables = {
      OPENSEARCH_ENDPOINT = aws_opensearchserverless_collection.main.collection_endpoint
      OPENSEARCH_INDEX    = "bos-ai-documents"
      BEDROCK_MODEL_ID    = "amazon.titan-embed-text-v1"
      S3_BUCKET_VIRGINIA  = "bos-ai-documents-us"
      SECRET_NAME         = "opensearch/bos-ai-rag-prod"
      AWS_REGION          = "ap-northeast-2"
    }
  }

  tags = {
    Name        = "lambda-document-processor-seoul-prod"
    Project     = "BOS-AI"
    Environment = "Production"
    ManagedBy   = "Terraform"
    Layer       = "Compute"
  }

  depends_on = [
    aws_iam_role_policy.lambda_s3,
    aws_iam_role_policy.lambda_opensearch,
    aws_iam_role_policy.lambda_bedrock,
    aws_iam_role_policy.lambda_secrets,
    aws_iam_role_policy.lambda_logs,
    aws_iam_role_policy.lambda_vpc
  ]
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
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.document_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = "arn:aws:s3:::bos-ai-documents-us"
}

# Outputs
output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.document_processor.arn
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.document_processor.function_name
}

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
