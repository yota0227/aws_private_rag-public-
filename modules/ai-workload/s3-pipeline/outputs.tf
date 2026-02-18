# Source Bucket Outputs
output "source_bucket_id" {
  description = "ID of the source S3 bucket"
  value       = aws_s3_bucket.source.id
}

output "source_bucket_arn" {
  description = "ARN of the source S3 bucket"
  value       = aws_s3_bucket.source.arn
}

output "source_bucket_domain_name" {
  description = "Domain name of the source S3 bucket"
  value       = aws_s3_bucket.source.bucket_domain_name
}

output "source_bucket_regional_domain_name" {
  description = "Regional domain name of the source S3 bucket"
  value       = aws_s3_bucket.source.bucket_regional_domain_name
}

# Destination Bucket Outputs
output "destination_bucket_id" {
  description = "ID of the destination S3 bucket"
  value       = aws_s3_bucket.destination.id
}

output "destination_bucket_arn" {
  description = "ARN of the destination S3 bucket"
  value       = aws_s3_bucket.destination.arn
}

output "destination_bucket_domain_name" {
  description = "Domain name of the destination S3 bucket"
  value       = aws_s3_bucket.destination.bucket_domain_name
}

output "destination_bucket_regional_domain_name" {
  description = "Regional domain name of the destination S3 bucket"
  value       = aws_s3_bucket.destination.bucket_regional_domain_name
}

# Replication Outputs
output "replication_role_arn" {
  description = "ARN of the S3 replication IAM role"
  value       = var.enable_replication && var.replication_role_arn == "" ? aws_iam_role.replication[0].arn : var.replication_role_arn
}

output "replication_enabled" {
  description = "Whether cross-region replication is enabled"
  value       = var.enable_replication
}

output "replication_configuration_id" {
  description = "ID of the replication configuration"
  value       = var.enable_replication ? aws_s3_bucket_replication_configuration.source_to_destination[0].id : null
}

# Lambda Outputs
output "lambda_function_arn" {
  description = "ARN of the Lambda document processor function"
  value       = aws_lambda_function.document_processor.arn
}

output "lambda_function_name" {
  description = "Name of the Lambda document processor function"
  value       = aws_lambda_function.document_processor.function_name
}

output "lambda_function_qualified_arn" {
  description = "Qualified ARN of the Lambda function (includes version)"
  value       = aws_lambda_function.document_processor.qualified_arn
}

output "lambda_function_invoke_arn" {
  description = "Invoke ARN of the Lambda function (for API Gateway, etc.)"
  value       = aws_lambda_function.document_processor.invoke_arn
}

# Dead Letter Queue Outputs
output "lambda_dlq_arn" {
  description = "ARN of the Lambda Dead Letter Queue"
  value       = aws_sqs_queue.lambda_dlq.arn
}

output "lambda_dlq_url" {
  description = "URL of the Lambda Dead Letter Queue"
  value       = aws_sqs_queue.lambda_dlq.url
}

output "lambda_dlq_name" {
  description = "Name of the Lambda Dead Letter Queue"
  value       = aws_sqs_queue.lambda_dlq.name
}

# S3 Event Notification Output
output "s3_event_notification_id" {
  description = "ID of the S3 event notification configuration"
  value       = aws_s3_bucket_notification.document_upload.id
}
