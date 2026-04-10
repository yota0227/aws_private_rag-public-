# ============================================================================
# Claim DB - DynamoDB Table (Knowledge Archive, claim lifecycle managed)
# PK: claim_id (S), SK: version (N)
# 5 GSI: topic-index, status-index, topic-variant-index,
#        source-document-index, family-index
# Requirements: 4.1, 4.2, 4.5, 4.6, 4.7, 13.3, 13.4, 13.6
# ============================================================================

resource "aws_dynamodb_table" "claim_db" {
  provider     = aws.seoul
  name         = "bos-ai-claim-db-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "claim_id"
  range_key    = "version"

  # --- Primary Key Attributes ---
  attribute {
    name = "claim_id"
    type = "S"
  }
  attribute {
    name = "version"
    type = "N"
  }

  # --- GSI Key Attributes ---
  attribute {
    name = "topic"
    type = "S"
  }
  attribute {
    name = "status"
    type = "S"
  }
  attribute {
    name = "topic_variant"
    type = "S"
  }
  attribute {
    name = "source_document_id"
    type = "S"
  }
  attribute {
    name = "claim_family_id"
    type = "S"
  }
  attribute {
    name = "last_verified_at"
    type = "S"
  }
  attribute {
    name = "extraction_date"
    type = "S"
  }

  # --- GSI 1: topic-index (주제별 claim 조회, Verification Pipeline 3단계) ---
  global_secondary_index {
    name            = "topic-index"
    hash_key        = "topic"
    range_key       = "last_verified_at"
    projection_type = "ALL"
  }

  # --- GSI 2: status-index (상태별 claim 조회, Cross-Check 대상 선별) ---
  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    range_key       = "last_verified_at"
    projection_type = "ALL"
  }

  # --- GSI 3: topic-variant-index (variant 필터링, baseline/N1B0 구분) ---
  global_secondary_index {
    name            = "topic-variant-index"
    hash_key        = "topic_variant"
    range_key       = "last_verified_at"
    projection_type = "ALL"
  }

  # --- GSI 4: source-document-index (evidence 역추적) ---
  global_secondary_index {
    name            = "source-document-index"
    hash_key        = "source_document_id"
    range_key       = "extraction_date"
    projection_type = "KEYS_ONLY"
  }

  # --- GSI 5: family-index (claim 계보 추적, 버전 체인) ---
  global_secondary_index {
    name            = "family-index"
    hash_key        = "claim_family_id"
    range_key       = "version"
    projection_type = "ALL"
  }

  # --- Point-in-Time Recovery ---
  point_in_time_recovery {
    enabled = true
  }

  # --- KMS CMK 암호화 ---
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.s3_seoul.arn
  }

  tags = merge(local.common_tags, {
    Name    = "bos-ai-claim-db-${var.environment}"
    Purpose = "Claim Knowledge Archive"
  })
}

# --- Claim DB IAM Policy for Lambda Handler ---
# Requirements: 13.3
resource "aws_iam_role_policy" "lambda_claim_db" {
  name = "lambda-claim-db-access"
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
          "dynamodb:Query",
          "dynamodb:Scan",
        ]
        Resource = [
          aws_dynamodb_table.claim_db.arn,
          "${aws_dynamodb_table.claim_db.arn}/index/*",
        ]
      }
    ]
  })
}

# --- Outputs ---
output "claim_db_table_name" {
  description = "Claim DB DynamoDB table name"
  value       = aws_dynamodb_table.claim_db.name
}

output "claim_db_table_arn" {
  description = "Claim DB DynamoDB table ARN"
  value       = aws_dynamodb_table.claim_db.arn
}
