# ============================================================================
# RTL 전용 S3 버킷 - RTL 소스 코드 격리 저장소
# Purpose: RTL 소스 코드를 일반 문서와 분리하여 전용 파싱 파이프라인 트리거
#
# Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 12.2
# ============================================================================

# ----------------------------------------------------------------------------
# RTL S3 버킷 (Seoul, ap-northeast-2)
# Object Lock 활성화 (버킷 생성 시 설정 필수)
# ----------------------------------------------------------------------------

resource "aws_s3_bucket" "rtl_codes" {
  provider = aws.seoul

  bucket              = "bos-ai-rtl-src-${data.aws_caller_identity.current.account_id}"
  object_lock_enabled = true

  tags = merge(local.common_tags, {
    Name    = "bos-ai-rtl-codes"
    Purpose = "RTL Source Code Storage"
    Layer   = "app"
  })
}

# Object Lock 구성: Governance 모드, 365일 retention
resource "aws_s3_bucket_object_lock_configuration" "rtl_codes" {
  provider = aws.seoul

  bucket = aws_s3_bucket.rtl_codes.id

  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = 365
    }
  }
}

# 버전 관리 활성화 (Object Lock 및 CRR 필수 조건)
resource "aws_s3_bucket_versioning" "rtl_codes" {
  provider = aws.seoul

  bucket = aws_s3_bucket.rtl_codes.id

  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-KMS 암호화 (기존 BOS-AI KMS 키 사용)
resource "aws_s3_bucket_server_side_encryption_configuration" "rtl_codes" {
  provider = aws.seoul

  bucket = aws_s3_bucket.rtl_codes.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3_seoul.arn
    }
    bucket_key_enabled = true
  }
}

# Block Public Access (4개 설정 모두 true)
resource "aws_s3_bucket_public_access_block" "rtl_codes" {
  provider = aws.seoul

  bucket = aws_s3_bucket.rtl_codes.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# VPC Endpoint 전용 버킷 정책
# NOTE: DenyNonVPCEndpointAccess 조건은 frontend_s3_gateway_endpoint_id 출력이
#       network-layer에서 제공될 때 활성화. 현재는 RTL Parser Lambda와 복제 역할만 허용.
resource "aws_s3_bucket_policy" "rtl_codes" {
  provider = aws.seoul

  bucket = aws_s3_bucket.rtl_codes.id

  depends_on = [
    aws_s3_bucket_versioning.rtl_codes,
    aws_s3_bucket_server_side_encryption_configuration.rtl_codes,
    aws_s3_bucket_public_access_block.rtl_codes,
  ]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowRTLParserLambda"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.rtl_parser_lambda.arn
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:GetObjectVersion"
        ]
        Resource = [
          "${aws_s3_bucket.rtl_codes.arn}/*"
        ]
      },
      {
        Sid    = "AllowReplicationRole"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.rtl_s3_replication.arn
        }
        Action = [
          "s3:GetReplicationConfiguration",
          "s3:ListBucket",
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl",
          "s3:GetObjectVersionTagging"
        ]
        Resource = [
          aws_s3_bucket.rtl_codes.arn,
          "${aws_s3_bucket.rtl_codes.arn}/*"
        ]
      }
    ]
  })
}

# ----------------------------------------------------------------------------
# S3 Event Notification: rtl-sources/ → RTL_Parser_Lambda
# ----------------------------------------------------------------------------

resource "aws_s3_bucket_notification" "rtl_codes" {
  provider = aws.seoul

  bucket = aws_s3_bucket.rtl_codes.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.rtl_parser.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "rtl-sources/"
  }

  depends_on = [aws_lambda_permission.rtl_parser_allow_s3]
}

resource "aws_lambda_permission" "rtl_parser_allow_s3" {
  provider = aws.seoul

  statement_id  = "AllowRTLParserFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rtl_parser.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.rtl_codes.arn
}

# ----------------------------------------------------------------------------
# Cross-Region Replication: Seoul RTL → Virginia RTL 전용 버킷
# ----------------------------------------------------------------------------

# IAM Role for RTL S3 Replication
resource "aws_iam_role" "rtl_s3_replication" {
  name = "role-rtl-s3-replication-seoul-to-virginia-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name    = "role-rtl-s3-replication-seoul-to-virginia-${var.environment}"
    Purpose = "RTL S3 Cross-Region Replication"
  })
}

resource "aws_iam_role_policy" "rtl_s3_replication" {
  name = "rtl-s3-replication-policy"
  role = aws_iam_role.rtl_s3_replication.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetReplicationConfiguration",
          "s3:ListBucket"
        ]
        Resource = [aws_s3_bucket.rtl_codes.arn]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl",
          "s3:GetObjectVersionTagging"
        ]
        Resource = ["${aws_s3_bucket.rtl_codes.arn}/*"]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ReplicateObject",
          "s3:ReplicateDelete",
          "s3:ReplicateTags"
        ]
        Resource = ["arn:aws:s3:::bos-ai-rtl-src-us-${data.aws_caller_identity.current.account_id}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = [aws_kms_key.s3_seoul.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Encrypt"]
        Resource = [module.kms.key_arn]
      }
    ]
  })
}

# Replication Configuration: Seoul RTL → Virginia RTL
# NOTE: Virginia 대상 버킷(bos-ai-rtl-src-us-{account_id}) 생성 후 활성화
resource "aws_s3_bucket_replication_configuration" "rtl_seoul_to_virginia" {
  provider = aws.seoul
  count    = 0  # Virginia 대상 버킷 생성 후 1로 변경

  depends_on = [aws_s3_bucket_versioning.rtl_codes]

  role   = aws_iam_role.rtl_s3_replication.arn
  bucket = aws_s3_bucket.rtl_codes.id

  rule {
    id     = "replicate-rtl-to-virginia"
    status = "Enabled"

    filter {
      prefix = "rtl-sources/"
    }

    destination {
      bucket        = "arn:aws:s3:::bos-ai-rtl-src-us-${data.aws_caller_identity.current.account_id}"
      storage_class = "STANDARD"

      encryption_configuration {
        replica_kms_key_id = module.kms.key_arn
      }
    }

    source_selection_criteria {
      sse_kms_encrypted_objects {
        status = "Enabled"
      }
    }

    delete_marker_replication {
      status = "Enabled"
    }
  }
}

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

output "rtl_codes_bucket_name" {
  description = "RTL S3 bucket name"
  value       = aws_s3_bucket.rtl_codes.bucket
}

output "rtl_codes_bucket_arn" {
  description = "RTL S3 bucket ARN"
  value       = aws_s3_bucket.rtl_codes.arn
}
