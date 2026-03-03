# AWS Secrets Manager for Kiro API Keys and Credentials

# Secrets Manager Secret for Kiro API Key
resource "aws_secretsmanager_secret" "kiro_api_key" {
  name                    = "kiro/subscription/api-key-${var.environment}"
  description             = "Kiro subscription API key for authentication"
  recovery_window_in_days = 7

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-api-key-${var.environment}"
    }
  )
}

# Secrets Manager Secret Version (placeholder)
resource "aws_secretsmanager_secret_version" "kiro_api_key" {
  secret_id = aws_secretsmanager_secret.kiro_api_key.id
  secret_string = jsonencode({
    api_key = "PLACEHOLDER_API_KEY_REPLACE_ME"
    api_url = "https://api.kiro.example.com"
    version = "1.0"
  })
}

# Secrets Manager Secret for Database Credentials (optional)
resource "aws_secretsmanager_secret" "kiro_db_credentials" {
  name                    = "kiro/subscription/db-credentials-${var.environment}"
  description             = "Database credentials for Kiro subscription service"
  recovery_window_in_days = 7

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-db-credentials-${var.environment}"
    }
  )
}

# Secrets Manager Secret Version for Database
resource "aws_secretsmanager_secret_version" "kiro_db_credentials" {
  secret_id = aws_secretsmanager_secret.kiro_db_credentials.id
  secret_string = jsonencode({
    username = "kiro_user"
    password = "PLACEHOLDER_PASSWORD_REPLACE_ME"
    host     = "PLACEHOLDER_HOST_REPLACE_ME"
    port     = 5432
    database = "kiro_subscription"
  })
}

# Secrets Manager Secret for S3 Configuration
resource "aws_secretsmanager_secret" "kiro_s3_config" {
  name                    = "kiro/subscription/s3-config-${var.environment}"
  description             = "S3 bucket configuration for Kiro subscription"
  recovery_window_in_days = 7

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-s3-config-${var.environment}"
    }
  )
}

# Secrets Manager Secret Version for S3 Configuration
resource "aws_secretsmanager_secret_version" "kiro_s3_config" {
  secret_id = aws_secretsmanager_secret.kiro_s3_config.id
  secret_string = jsonencode({
    bucket_name = aws_s3_bucket.kiro_prompts.id
    region      = var.aws_region
    kms_key_id  = aws_kms_key.kiro_prompts.id
    prefix      = "prompts"
  })
}

# CloudWatch Log Group for Secrets Manager
resource "aws_cloudwatch_log_group" "kiro_secrets" {
  name              = "/aws/secretsmanager/kiro-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-secrets-logs-${var.environment}"
    }
  )
}
