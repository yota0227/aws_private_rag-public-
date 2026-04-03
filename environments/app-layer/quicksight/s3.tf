# ============================================================================
# QuickSight 전용 S3 버킷
# Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
#
# - KMS CMK 암호화
# - 퍼블릭 액세스 전체 차단
# - VPC Endpoint 조건부 버킷 정책
# - 수명 주기: 90일 -> Intelligent-Tiering, 365일 -> Glacier
# ============================================================================

resource "aws_kms_key" "quicksight_s3" {
  provider                = aws.seoul
  description             = "KMS key for QuickSight S3 bucket encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Name = "kms-quicksight-s3-bos-ai-seoul-prod"
  })
}

resource "aws_kms_alias" "quicksight_s3" {
  provider      = aws.seoul
  name          = "alias/quicksight-s3-bos-ai-seoul-prod"
  target_key_id = aws_kms_key.quicksight_s3.key_id
}

resource "aws_s3_bucket" "quicksight_data" {
  provider = aws.seoul
  bucket   = "s3-quicksight-data-bos-ai-seoul-prod"

  tags = merge(local.common_tags, {
    Name = "s3-quicksight-data-bos-ai-seoul-prod"
  })
}

resource "aws_s3_bucket_versioning" "quicksight_data" {
  provider = aws.seoul
  bucket   = aws_s3_bucket.quicksight_data.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "quicksight_data" {
  provider = aws.seoul
  bucket   = aws_s3_bucket.quicksight_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.quicksight_s3.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "quicksight_data" {
  provider = aws.seoul
  bucket   = aws_s3_bucket.quicksight_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# VPC Endpoint를 통한 접근만 허용
resource "aws_s3_bucket_policy" "quicksight_data" {
  provider = aws.seoul
  bucket   = aws_s3_bucket.quicksight_data.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonVPCEndpointAccess"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.quicksight_data.arn,
          "${aws_s3_bucket.quicksight_data.arn}/*"
        ]
        Condition = {
          StringNotEquals = {
            "aws:sourceVpce" = [local.qs_api_endpoint_id]
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.quicksight_data]
}

resource "aws_s3_bucket_lifecycle_configuration" "quicksight_data" {
  provider = aws.seoul
  bucket   = aws_s3_bucket.quicksight_data.id

  rule {
    id     = "quicksight-data-lifecycle"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "INTELLIGENT_TIERING"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

resource "aws_s3_bucket_logging" "quicksight_data" {
  provider = aws.seoul
  bucket   = aws_s3_bucket.quicksight_data.id

  target_bucket = "bos-ai-access-logs-seoul-prod"
  target_prefix = "quicksight-data/"
}

output "quicksight_data_bucket_name" {
  description = "QuickSight 전용 S3 버킷명"
  value       = aws_s3_bucket.quicksight_data.bucket
}

output "quicksight_data_bucket_arn" {
  description = "QuickSight 전용 S3 버킷 ARN"
  value       = aws_s3_bucket.quicksight_data.arn
}
