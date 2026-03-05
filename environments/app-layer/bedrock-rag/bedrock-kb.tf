# ============================================================================
# Bedrock Knowledge Base Configuration (us-east-1 Virginia)
#
# Architecture:
#   - Bedrock KB: us-east-1 (default provider)
#   - OpenSearch Serverless: us-east-1 기존 collection (bos-ai-vectors)
#   - Embedding Model: Titan Embed Text V1 (us-east-1 지원)
#   - Seoul Lambda → VPC Peering → Virginia Bedrock KB 호출
#
# Requirements: 3.4, NFR-1, NFR-2
# ============================================================================

# ----------------------------------------------------------------------------
# Security Group for Bedrock Knowledge Base (US Backend VPC)
# ----------------------------------------------------------------------------

resource "aws_security_group" "bedrock_kb" {
  # default provider = us-east-1
  name        = "bedrock-kb-bos-ai-${var.environment}"
  description = "Security group for Bedrock Knowledge Base - US Backend VPC"
  vpc_id      = local.us_vpc_id  # US Backend VPC (10.20.0.0/16)

  # Outbound: HTTPS to AWS services (OpenSearch, Bedrock, S3)
  egress {
    description = "HTTPS to AWS services"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name    = "bedrock-kb-bos-ai-${var.environment}"
    Purpose = "Bedrock Knowledge Base - Backend"
    Layer   = "Security"
  })
}

# ----------------------------------------------------------------------------
# IAM Role for Bedrock Knowledge Base
# ----------------------------------------------------------------------------

resource "aws_iam_role" "bedrock_kb" {
  name        = "role-bedrock-kb-seoul-prod"
  description = "IAM role for Bedrock Knowledge Base"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = "533335672315"
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:bedrock:us-east-1:533335672315:knowledge-base/*"
          }
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name    = "role-bedrock-kb-seoul-prod"
    Purpose = "Bedrock KB IAM Role"
    Layer   = "Security"
  })
}

# IAM Policy for Bedrock KB - S3 Access
resource "aws_iam_role_policy" "bedrock_kb_s3" {
  name = "bedrock-kb-s3-access"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
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

# IAM Policy for Bedrock KB - OpenSearch Serverless Access (us-east-1)
resource "aws_iam_role_policy" "bedrock_kb_opensearch" {
  name = "bedrock-kb-opensearch-access"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "aoss:APIAccessAll"
        ]
        Resource = [
          data.aws_opensearchserverless_collection.virginia.arn
        ]
      }
    ]
  })
}

# IAM Policy for Bedrock KB - Bedrock Model Access (us-east-1)
resource "aws_iam_role_policy" "bedrock_kb_bedrock" {
  name = "bedrock-kb-bedrock-access"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = [
          "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1"
        ]
      }
    ]
  })
}

# ----------------------------------------------------------------------------
# Bedrock Knowledge Base는 module.bedrock_rag (main.tf)에서 관리
# Virginia의 기존 OpenSearch collection (bos-ai-vectors) 사용
# standalone IAM Role/Policy는 여기서 관리 (기존 state 호환)
# ----------------------------------------------------------------------------

# CloudWatch Log Group for Bedrock KB
resource "aws_cloudwatch_log_group" "bedrock_kb" {
  name              = "/aws/bedrock/knowledge-base/bos-ai-kb-${var.environment}"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Name    = "bos-ai-kb-${var.environment}-logs"
    Purpose = "Bedrock KB Logs"
  })
}

# Variables
variable "enable_seoul_data_source" {
  description = "Enable Seoul S3 bucket as data source"
  type        = bool
  default     = false
}

# Outputs - KB outputs come from module.bedrock_rag in outputs.tf
output "bedrock_kb_standalone_role_arn" {
  description = "Standalone Bedrock KB IAM Role ARN"
  value       = aws_iam_role.bedrock_kb.arn
}
