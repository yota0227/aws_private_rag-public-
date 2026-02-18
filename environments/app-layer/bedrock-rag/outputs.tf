# Outputs for App Layer - Bedrock RAG
# Requirements: 12.4

# Bedrock Outputs
output "knowledge_base_id" {
  description = "ID of Bedrock Knowledge Base"
  value       = module.bedrock_rag.knowledge_base_id
}

output "knowledge_base_arn" {
  description = "ARN of Bedrock Knowledge Base"
  value       = module.bedrock_rag.knowledge_base_arn
}

# OpenSearch Outputs
output "opensearch_collection_endpoint" {
  description = "Endpoint of OpenSearch Serverless collection"
  value       = module.bedrock_rag.opensearch_collection_endpoint
}

output "opensearch_collection_arn" {
  description = "ARN of OpenSearch Serverless collection"
  value       = module.bedrock_rag.opensearch_collection_arn
}

output "opensearch_collection_id" {
  description = "ID of OpenSearch Serverless collection"
  value       = module.bedrock_rag.opensearch_collection_id
}

# S3 Outputs
output "source_bucket_id" {
  description = "ID of source S3 bucket (Seoul)"
  value       = module.s3_pipeline.source_bucket_id
}

output "destination_bucket_id" {
  description = "ID of destination S3 bucket (US)"
  value       = module.s3_pipeline.destination_bucket_id
}

output "destination_bucket_arn" {
  description = "ARN of destination S3 bucket (US)"
  value       = module.s3_pipeline.destination_bucket_arn
}

# Lambda Outputs
output "lambda_function_arn" {
  description = "ARN of Lambda document processor function"
  value       = module.s3_pipeline.lambda_function_arn
}

output "lambda_function_name" {
  description = "Name of Lambda document processor function"
  value       = module.s3_pipeline.lambda_function_name
}

# KMS Outputs
output "kms_key_id" {
  description = "ID of KMS key"
  value       = module.kms.key_id
}

output "kms_key_arn" {
  description = "ARN of KMS key"
  value       = module.kms.key_arn
}

# IAM Outputs
output "bedrock_kb_role_arn" {
  description = "ARN of Bedrock Knowledge Base IAM role"
  value       = module.iam.bedrock_kb_role_arn
}

output "lambda_processor_role_arn" {
  description = "ARN of Lambda processor IAM role"
  value       = module.iam.lambda_processor_role_arn
}

# VPC Endpoints Outputs
output "vpc_endpoint_ids" {
  description = "IDs of VPC endpoints"
  value       = module.vpc_endpoints.all_endpoint_ids
}

# Monitoring Outputs
output "cloudwatch_dashboard_name" {
  description = "Name of CloudWatch dashboard"
  value       = module.cloudwatch_dashboards.dashboard_name
}

output "cloudwatch_alarms_sns_topic_arn" {
  description = "ARN of SNS topic for CloudWatch alarms"
  value       = module.cloudwatch_alarms.sns_topic_arn
}

# CloudTrail Outputs
output "cloudtrail_id" {
  description = "ID of CloudTrail trail"
  value       = module.cloudtrail.trail_id
}

output "cloudtrail_arn" {
  description = "ARN of CloudTrail trail"
  value       = module.cloudtrail.trail_arn
}

# Budget Outputs
output "budget_id" {
  description = "ID of AWS Budget"
  value       = module.budgets.budget_id
}

output "budget_sns_topic_arn" {
  description = "ARN of SNS topic for budget alerts"
  value       = module.budgets.sns_topic_arn
}

# Network Outputs (from remote state)
output "us_vpc_id" {
  description = "ID of US VPC (from network layer)"
  value       = local.us_vpc_id
}

output "us_private_subnet_ids" {
  description = "IDs of US private subnets (from network layer)"
  value       = local.us_private_subnet_ids
}
