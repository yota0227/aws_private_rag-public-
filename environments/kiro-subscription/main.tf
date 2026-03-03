# Kiro Subscription - S3 Bucket for User Prompt Metadata
# Stores user prompts and metadata for Kiro subscription service
# Region: us-east-1 (Virginia)
#
# Requirements: Kiro subscription metadata storage

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# Local variables
locals {
  common_tags = {
    Project     = "Kiro-Subscription"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Layer       = "kiro"
    Region      = var.aws_region
    Owner       = "Kiro-Team"
    CostCenter  = "Kiro-Infrastructure"
  }
}

# S3 Bucket for User Prompt Metadata
resource "aws_s3_bucket" "kiro_prompts" {
  bucket = var.bucket_name

  tags = merge(
    local.common_tags,
    {
      Name        = "kiro-user-prompts-${var.environment}"
      Description = "Stores user prompts and metadata for Kiro subscription"
    }
  )
}

# Enable versioning for audit trail
resource "aws_s3_bucket_versioning" "kiro_prompts" {
  bucket = aws_s3_bucket.kiro_prompts.id

  versioning_configuration {
    status     = "Enabled"
    mfa_delete = "Disabled"
  }
}

# Server-side encryption with KMS
resource "aws_s3_bucket_server_side_encryption_configuration" "kiro_prompts" {
  bucket = aws_s3_bucket.kiro_prompts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.kiro_prompts.arn
    }
    bucket_key_enabled = true
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "kiro_prompts" {
  bucket = aws_s3_bucket.kiro_prompts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable logging
resource "aws_s3_bucket_logging" "kiro_prompts" {
  bucket = aws_s3_bucket.kiro_prompts.id

  target_bucket = aws_s3_bucket.kiro_prompts_logs.id
  target_prefix = "access-logs/"
}

# S3 Bucket for Access Logs
resource "aws_s3_bucket" "kiro_prompts_logs" {
  bucket = "${var.bucket_name}-logs"

  tags = merge(
    local.common_tags,
    {
      Name        = "kiro-user-prompts-logs-${var.environment}"
      Description = "Access logs for Kiro user prompts bucket"
    }
  )
}

# Block public access for logs bucket
resource "aws_s3_bucket_public_access_block" "kiro_prompts_logs" {
  bucket = aws_s3_bucket.kiro_prompts_logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle policy for logs bucket
resource "aws_s3_bucket_lifecycle_configuration" "kiro_prompts_logs" {
  bucket = aws_s3_bucket.kiro_prompts_logs.id

  rule {
    id     = "delete-old-logs"
    status = "Enabled"

    expiration {
      days = var.log_retention_days
    }
  }
}

# KMS Key for encryption
resource "aws_kms_key" "kiro_prompts" {
  description             = "KMS key for Kiro user prompts encryption"
  deletion_window_in_days = 10
  enable_key_rotation     = true

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-prompts-key-${var.environment}"
    }
  )
}

# KMS Key Alias
resource "aws_kms_alias" "kiro_prompts" {
  name          = "alias/kiro-prompts-${var.environment}"
  target_key_id = aws_kms_key.kiro_prompts.key_id
}

# KMS Key Policy
resource "aws_kms_key_policy" "kiro_prompts" {
  key_id = aws_kms_key.kiro_prompts.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow S3 to use the key"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = "*"
      },
      {
        Sid    = "Allow CloudWatch Logs"
        Effect = "Allow"
        Principal = {
          Service = "logs.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:CreateGrant",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })
}

# S3 Bucket Policy
resource "aws_s3_bucket_policy" "kiro_prompts" {
  bucket = aws_s3_bucket.kiro_prompts.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyUnencryptedObjectUploads"
        Effect = "Deny"
        Principal = "*"
        Action = "s3:PutObject"
        Resource = "${aws_s3_bucket.kiro_prompts.arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption" = "aws:kms"
          }
        }
      },
      {
        Sid    = "DenyInsecureTransport"
        Effect = "Deny"
        Principal = "*"
        Action = "s3:*"
        Resource = [
          aws_s3_bucket.kiro_prompts.arn,
          "${aws_s3_bucket.kiro_prompts.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# CloudWatch Log Group for S3 access logs
resource "aws_cloudwatch_log_group" "kiro_prompts" {
  name              = "/aws/s3/kiro-prompts-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-prompts-logs-${var.environment}"
    }
  )
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}
