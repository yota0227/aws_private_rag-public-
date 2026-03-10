# ============================================================================
# DynamoDB Table - Extraction Task Status Tracking
# Purpose: 압축 파일 비동기 해제 작업의 상태를 추적하는 DynamoDB 테이블
#
# Requirements: 7.2
# Design: 5.1
# ============================================================================

resource "aws_dynamodb_table" "extraction_tasks" {
  provider = aws.seoul

  name         = "rag-extraction-tasks-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "task_id"

  attribute {
    name = "task_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # 고객 관리형 KMS 키(CMK)로 서버 측 암호화 (보안 Guardrail)
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.s3_seoul.arn
  }

  tags = merge(local.common_tags, {
    Name    = "rag-extraction-tasks-${var.environment}"
    Purpose = "Extraction Task Status Tracking"
  })
}

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

output "extraction_tasks_table_name" {
  description = "DynamoDB extraction tasks table name"
  value       = aws_dynamodb_table.extraction_tasks.name
}

output "extraction_tasks_table_arn" {
  description = "DynamoDB extraction tasks table ARN"
  value       = aws_dynamodb_table.extraction_tasks.arn
}
