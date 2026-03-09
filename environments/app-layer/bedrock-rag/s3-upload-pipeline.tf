# ============================================================================
# S3 Data Upload Pipeline - Seoul → Virginia Cross-Region Replication
# Purpose: 온프렘에서 Air-Gapped 환경으로 RAG 문서 업로드
#
# Flow: 온프렘 → VPN → TGW → S3 Gateway Endpoint → Seoul S3
#       → Cross-Region Replication → Virginia S3 → Bedrock KB
#
# Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8
# ============================================================================

# ----------------------------------------------------------------------------
# Seoul S3 Bucket (ap-northeast-2) - 문서 업로드 전용
# ----------------------------------------------------------------------------

resource "aws_s3_bucket" "documents_seoul" {
  provider = aws.seoul

  bucket = "bos-ai-documents-seoul-v3"

  tags = merge(local.common_tags, {
    Name    = "bos-ai-documents-seoul-v3"
    Purpose = "RAG document upload - Seoul region"
    Region  = "ap-northeast-2"
  })
}

# 버전 관리 (Replication 필수 조건)
resource "aws_s3_bucket_versioning" "documents_seoul" {
  provider = aws.seoul

  bucket = aws_s3_bucket.documents_seoul.id
  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-KMS 암호화
resource "aws_s3_bucket_server_side_encryption_configuration" "documents_seoul" {
  provider = aws.seoul

  bucket = aws_s3_bucket.documents_seoul.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3_seoul.arn
    }
    bucket_key_enabled = true
  }
}

# Public Access Block
resource "aws_s3_bucket_public_access_block" "documents_seoul" {
  provider = aws.seoul

  bucket = aws_s3_bucket.documents_seoul.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Bucket Policy: S3 VPC Endpoint에서만 접근 허용 (Terraform IAM 사용자 예외)
resource "aws_s3_bucket_policy" "documents_seoul" {
  provider = aws.seoul

  bucket = aws_s3_bucket.documents_seoul.id

  # versioning, encryption 설정 완료 후 policy 적용
  depends_on = [
    aws_s3_bucket_versioning.documents_seoul,
    aws_s3_bucket_server_side_encryption_configuration.documents_seoul,
    aws_s3_bucket_public_access_block.documents_seoul
  ]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowTerraformManagement"
        Effect    = "Allow"
        Principal = {
          AWS = "arn:aws:iam::533335672315:user/seungil.woo"
        }
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.documents_seoul.arn,
          "${aws_s3_bucket.documents_seoul.arn}/*"
        ]
      },
      {
        Sid       = "AllowLambdaAccess"
        Effect    = "Allow"
        Principal = {
          AWS = aws_iam_role.lambda.arn
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:CreateMultipartUpload",
          "s3:UploadPart",
          "s3:CompleteMultipartUpload",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts"
        ]
        Resource = [
          aws_s3_bucket.documents_seoul.arn,
          "${aws_s3_bucket.documents_seoul.arn}/*"
        ]
      },
      {
        Sid       = "AllowReplicationRole"
        Effect    = "Allow"
        Principal = {
          AWS = aws_iam_role.s3_replication.arn
        }
        Action = [
          "s3:GetReplicationConfiguration",
          "s3:ListBucket",
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl",
          "s3:GetObjectVersionTagging"
        ]
        Resource = [
          aws_s3_bucket.documents_seoul.arn,
          "${aws_s3_bucket.documents_seoul.arn}/*"
        ]
      },
      {
        Sid       = "DenyNonVPCEndpointAccess"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.documents_seoul.arn,
          "${aws_s3_bucket.documents_seoul.arn}/*"
        ]
        Condition = {
          StringNotEquals = {
            "aws:sourceVpce" = data.terraform_remote_state.network.outputs.frontend_s3_gateway_endpoint_id
          }
          ArnNotEquals = {
            "aws:PrincipalArn" = [
              "arn:aws:iam::533335672315:user/seungil.woo",
              aws_iam_role.s3_replication.arn,
              aws_iam_role.lambda.arn
            ]
          }
        }
      }
    ]
  })
}

# KMS Key for Seoul S3 Bucket
resource "aws_kms_key" "s3_seoul" {
  provider = aws.seoul

  description             = "KMS key for Seoul S3 bucket encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Name    = "kms-s3-documents-seoul-${var.environment}"
    Purpose = "S3 encryption - Seoul documents"
  })
}

resource "aws_kms_alias" "s3_seoul" {
  provider = aws.seoul

  name          = "alias/bos-ai-s3-documents-seoul"
  target_key_id = aws_kms_key.s3_seoul.key_id
}

# ----------------------------------------------------------------------------
# Cross-Region Replication: Seoul → Virginia
# ----------------------------------------------------------------------------

# IAM Role for Replication
resource "aws_iam_role" "s3_replication" {
  name = "role-s3-replication-seoul-to-virginia-${var.environment}"

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
    Name    = "role-s3-replication-seoul-to-virginia-${var.environment}"
    Purpose = "S3 Cross-Region Replication"
  })
}

resource "aws_iam_role_policy" "s3_replication" {
  name = "s3-replication-policy"
  role = aws_iam_role.s3_replication.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetReplicationConfiguration",
          "s3:ListBucket"
        ]
        Resource = [aws_s3_bucket.documents_seoul.arn]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl",
          "s3:GetObjectVersionTagging"
        ]
        Resource = ["${aws_s3_bucket.documents_seoul.arn}/*"]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ReplicateObject",
          "s3:ReplicateDelete",
          "s3:ReplicateTags"
        ]
        Resource = ["arn:aws:s3:::${var.destination_bucket_name}/*"]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = [aws_kms_key.s3_seoul.arn]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt"
        ]
        Resource = [module.kms.key_arn]
      }
    ]
  })
}

# Replication Configuration
resource "aws_s3_bucket_replication_configuration" "seoul_to_virginia" {
  provider = aws.seoul

  depends_on = [aws_s3_bucket_versioning.documents_seoul]

  role   = aws_iam_role.s3_replication.arn
  bucket = aws_s3_bucket.documents_seoul.id

  rule {
    id     = "replicate-to-virginia"
    status = "Enabled"

    filter {
      prefix = ""  # 모든 객체 복제
    }

    destination {
      bucket        = "arn:aws:s3:::${var.destination_bucket_name}"
      storage_class = "STANDARD"

      encryption_configuration {
        replica_kms_key_id = module.kms.key_arn
      }

      metrics {
        status = "Enabled"
        event_threshold {
          minutes = 15
        }
      }

      replication_time {
        status = "Enabled"
        time {
          minutes = 15
        }
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

output "documents_seoul_bucket_name" {
  description = "Seoul S3 bucket name for document upload"
  value       = aws_s3_bucket.documents_seoul.bucket
}

output "documents_seoul_bucket_arn" {
  description = "Seoul S3 bucket ARN"
  value       = aws_s3_bucket.documents_seoul.arn
}

output "s3_replication_role_arn" {
  description = "S3 Replication IAM Role ARN"
  value       = aws_iam_role.s3_replication.arn
}
