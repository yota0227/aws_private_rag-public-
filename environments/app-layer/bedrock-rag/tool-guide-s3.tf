# ============================================================================
# Tool Guide 전용 S3 버킷 - EDA 툴 가이드 문서 격리 저장소
# Purpose: EDA 툴 가이드(PDF/MD)를 RTL corpus와 분리하여
#          Tool Guide 전용 파싱 파이프라인을 트리거
#
# Design ref: .kiro/specs/eda-tool-guide-rag/design.md (C1, 가정 3)
# Requirements: R1.1, R1.2, R1.3, R1.4, R1.5, R1.6, R5.1
# ============================================================================

# ----------------------------------------------------------------------------
# Tool Guide S3 소스 버킷 (Seoul, ap-northeast-2)
# 네이밍: account_id 접미사로 전역 고유성 보장 (RTL 버킷과 동일 패턴)
# ----------------------------------------------------------------------------

resource "aws_s3_bucket" "tool_guide_docs_seoul" {
  provider = aws.seoul

  bucket = "bos-ai-toolguide-docs-seoul-${data.aws_caller_identity.current.account_id}"

  tags = merge(local.common_tags, {
    Name     = "bos-ai-toolguide-docs-seoul"
    Purpose  = "EDA Tool Guide Document Storage"
    Layer    = "app"
    Pipeline = "tool-guide"
  })
}

# 버전 관리 활성화 (CRR 필수 조건 + 재업로드 멱등성 보장)
resource "aws_s3_bucket_versioning" "tool_guide_docs_seoul" {
  provider = aws.seoul

  bucket = aws_s3_bucket.tool_guide_docs_seoul.id

  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-KMS 암호화 (기존 BOS-AI KMS 키 재사용, R1.5)
resource "aws_s3_bucket_server_side_encryption_configuration" "tool_guide_docs_seoul" {
  provider = aws.seoul

  bucket = aws_s3_bucket.tool_guide_docs_seoul.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3_seoul.arn
    }
    bucket_key_enabled = true
  }
}

# Block Public Access (4개 설정 모두 true)
resource "aws_s3_bucket_public_access_block" "tool_guide_docs_seoul" {
  provider = aws.seoul

  bucket = aws_s3_bucket.tool_guide_docs_seoul.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 버킷 정책: Tool Guide Parser Lambda + 복제 역할만 허용
resource "aws_s3_bucket_policy" "tool_guide_docs_seoul" {
  provider = aws.seoul

  bucket = aws_s3_bucket.tool_guide_docs_seoul.id

  depends_on = [
    aws_s3_bucket_versioning.tool_guide_docs_seoul,
    aws_s3_bucket_server_side_encryption_configuration.tool_guide_docs_seoul,
    aws_s3_bucket_public_access_block.tool_guide_docs_seoul,
  ]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowToolGuideParserLambda"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.tool_guide_parser_lambda.arn
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:GetObjectVersion"
        ]
        Resource = ["${aws_s3_bucket.tool_guide_docs_seoul.arn}/*"]
      },
      {
        Sid    = "AllowReplicationRole"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.tool_guide_s3_replication.arn
        }
        Action = [
          "s3:GetReplicationConfiguration",
          "s3:ListBucket",
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl",
          "s3:GetObjectVersionTagging"
        ]
        Resource = [
          aws_s3_bucket.tool_guide_docs_seoul.arn,
          "${aws_s3_bucket.tool_guide_docs_seoul.arn}/*"
        ]
      }
    ]
  })
}

# ----------------------------------------------------------------------------
# S3 Event Notification: 전용 버킷 전체 → Tool_Guide_Parser_Lambda
# (prefix 라우팅 없음 — 버킷 자체가 분리, 설계 이벤트 라우팅 원칙)
# ----------------------------------------------------------------------------

resource "aws_s3_bucket_notification" "tool_guide_docs_seoul" {
  provider = aws.seoul

  bucket = aws_s3_bucket.tool_guide_docs_seoul.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.tool_guide_parser.arn
    events              = ["s3:ObjectCreated:*"]
    # prefix 필터 없음: 버킷 전체가 Tool Guide 전용
  }

  depends_on = [aws_lambda_permission.tool_guide_parser_allow_s3]
}

resource "aws_lambda_permission" "tool_guide_parser_allow_s3" {
  provider = aws.seoul

  statement_id  = "AllowToolGuideParserFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.tool_guide_parser.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.tool_guide_docs_seoul.arn
}

# ----------------------------------------------------------------------------
# Cross-Region Replication: Seoul → Virginia 전용 버킷
# ----------------------------------------------------------------------------

resource "aws_iam_role" "tool_guide_s3_replication" {
  name = "role-toolguide-s3-replication-seoul-to-virginia-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(local.common_tags, {
    Name    = "role-toolguide-s3-replication-seoul-to-virginia-${var.environment}"
    Purpose = "Tool Guide S3 Cross-Region Replication"
  })
}

resource "aws_iam_role_policy" "tool_guide_s3_replication" {
  name = "toolguide-s3-replication-policy"
  role = aws_iam_role.tool_guide_s3_replication.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetReplicationConfiguration", "s3:ListBucket"]
        Resource = [aws_s3_bucket.tool_guide_docs_seoul.arn]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl",
          "s3:GetObjectVersionTagging"
        ]
        Resource = ["${aws_s3_bucket.tool_guide_docs_seoul.arn}/*"]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ReplicateObject",
          "s3:ReplicateDelete",
          "s3:ReplicateTags"
        ]
        Resource = ["arn:aws:s3:::bos-ai-toolguide-docs-virginia-${data.aws_caller_identity.current.account_id}/*"]
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

# CRR 구성: count=0 (Virginia 대상 버킷 생성 후 1로 변경)
resource "aws_s3_bucket_replication_configuration" "tool_guide_seoul_to_virginia" {
  provider = aws.seoul
  count    = 0

  depends_on = [aws_s3_bucket_versioning.tool_guide_docs_seoul]

  role   = aws_iam_role.tool_guide_s3_replication.arn
  bucket = aws_s3_bucket.tool_guide_docs_seoul.id

  rule {
    id     = "replicate-toolguide-to-virginia"
    status = "Enabled"

    destination {
      bucket        = "arn:aws:s3:::bos-ai-toolguide-docs-virginia-${data.aws_caller_identity.current.account_id}"
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

output "tool_guide_docs_seoul_bucket_name" {
  description = "Tool Guide S3 소스 버킷명. 업로드 경로: s3://<bucket>/<tool_name>/<doc_version>/<filename>"
  value       = aws_s3_bucket.tool_guide_docs_seoul.bucket
}

output "tool_guide_docs_seoul_bucket_arn" {
  description = "Tool Guide S3 소스 버킷 ARN"
  value       = aws_s3_bucket.tool_guide_docs_seoul.arn
}
