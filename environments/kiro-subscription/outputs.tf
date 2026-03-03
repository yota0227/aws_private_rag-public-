# Outputs for Kiro Subscription S3 Bucket

output "bucket_name" {
  description = "Name of the Kiro user prompts S3 bucket"
  value       = aws_s3_bucket.kiro_prompts.id
}

output "bucket_arn" {
  description = "ARN of the Kiro user prompts S3 bucket"
  value       = aws_s3_bucket.kiro_prompts.arn
}

output "bucket_region" {
  description = "Region of the Kiro user prompts S3 bucket"
  value       = aws_s3_bucket.kiro_prompts.region
}

output "logs_bucket_name" {
  description = "Name of the access logs S3 bucket"
  value       = aws_s3_bucket.kiro_prompts_logs.id
}

output "logs_bucket_arn" {
  description = "ARN of the access logs S3 bucket"
  value       = aws_s3_bucket.kiro_prompts_logs.arn
}

output "kms_key_id" {
  description = "ID of the KMS key for encryption"
  value       = aws_kms_key.kiro_prompts.id
}

output "kms_key_arn" {
  description = "ARN of the KMS key for encryption"
  value       = aws_kms_key.kiro_prompts.arn
}

output "kms_key_alias" {
  description = "Alias of the KMS key"
  value       = aws_kms_alias.kiro_prompts.name
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group for S3 access logs"
  value       = aws_cloudwatch_log_group.kiro_prompts.name
}

output "bucket_versioning_enabled" {
  description = "Whether versioning is enabled on the bucket"
  value       = aws_s3_bucket_versioning.kiro_prompts.versioning_configuration[0].status == "Enabled"
}

# IAM Outputs
output "kiro_app_role_arn" {
  description = "ARN of the Kiro application IAM role"
  value       = aws_iam_role.kiro_app.arn
}

output "kiro_lambda_role_arn" {
  description = "ARN of the Kiro Lambda IAM role"
  value       = aws_iam_role.kiro_lambda.arn
}

# Secrets Manager Outputs
output "kiro_api_key_secret_arn" {
  description = "ARN of the Kiro API key secret"
  value       = aws_secretsmanager_secret.kiro_api_key.arn
}

output "kiro_db_credentials_secret_arn" {
  description = "ARN of the Kiro database credentials secret"
  value       = aws_secretsmanager_secret.kiro_db_credentials.arn
}

output "kiro_s3_config_secret_arn" {
  description = "ARN of the Kiro S3 configuration secret"
  value       = aws_secretsmanager_secret.kiro_s3_config.arn
}

# EventBridge Outputs
output "kiro_event_bus_arn" {
  description = "ARN of the Kiro EventBridge event bus"
  value       = aws_cloudwatch_event_bus.kiro_prompts.arn
}

output "kiro_event_bus_name" {
  description = "Name of the Kiro EventBridge event bus"
  value       = aws_cloudwatch_event_bus.kiro_prompts.name
}

# Lambda Outputs
output "kiro_prompt_processor_arn" {
  description = "ARN of the Kiro prompt processor Lambda function"
  value       = aws_lambda_function.kiro_prompt_processor.arn
}

output "kiro_prompt_processor_name" {
  description = "Name of the Kiro prompt processor Lambda function"
  value       = aws_lambda_function.kiro_prompt_processor.function_name
}

output "kiro_metadata_analyzer_arn" {
  description = "ARN of the Kiro metadata analyzer Lambda function"
  value       = aws_lambda_function.kiro_metadata_analyzer.arn
}

output "kiro_metadata_analyzer_name" {
  description = "Name of the Kiro metadata analyzer Lambda function"
  value       = aws_lambda_function.kiro_metadata_analyzer.function_name
}

# SNS Outputs
output "kiro_errors_topic_arn" {
  description = "ARN of the Kiro errors SNS topic"
  value       = aws_sns_topic.kiro_errors.arn
}

output "kiro_errors_topic_name" {
  description = "Name of the Kiro errors SNS topic"
  value       = aws_sns_topic.kiro_errors.name
}
