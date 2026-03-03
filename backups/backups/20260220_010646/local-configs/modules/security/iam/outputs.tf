# Bedrock Knowledge Base Role Outputs
output "bedrock_kb_role_arn" {
  description = "ARN of the Bedrock Knowledge Base IAM role"
  value       = aws_iam_role.bedrock_kb.arn
}

output "bedrock_kb_role_name" {
  description = "Name of the Bedrock Knowledge Base IAM role"
  value       = aws_iam_role.bedrock_kb.name
}

output "bedrock_kb_role_id" {
  description = "ID of the Bedrock Knowledge Base IAM role"
  value       = aws_iam_role.bedrock_kb.id
}

# Lambda Processor Role Outputs
output "lambda_processor_role_arn" {
  description = "ARN of the Lambda document processor IAM role"
  value       = aws_iam_role.lambda_processor.arn
}

output "lambda_processor_role_name" {
  description = "Name of the Lambda document processor IAM role"
  value       = aws_iam_role.lambda_processor.name
}

output "lambda_processor_role_id" {
  description = "ID of the Lambda document processor IAM role"
  value       = aws_iam_role.lambda_processor.id
}

# Policy ARNs for reference
output "bedrock_kb_s3_policy_arn" {
  description = "ARN of the Bedrock Knowledge Base S3 access policy"
  value       = aws_iam_policy.bedrock_kb_s3_access.arn
}

output "bedrock_kb_opensearch_policy_arn" {
  description = "ARN of the Bedrock Knowledge Base OpenSearch access policy"
  value       = aws_iam_policy.bedrock_kb_opensearch_access.arn
}

output "bedrock_kb_kms_policy_arn" {
  description = "ARN of the Bedrock Knowledge Base KMS access policy"
  value       = aws_iam_policy.bedrock_kb_kms_access.arn
}

output "bedrock_kb_model_policy_arn" {
  description = "ARN of the Bedrock Knowledge Base model invocation policy"
  value       = aws_iam_policy.bedrock_kb_model_access.arn
}

output "lambda_s3_policy_arn" {
  description = "ARN of the Lambda S3 access policy"
  value       = aws_iam_policy.lambda_s3_access.arn
}

output "lambda_cloudwatch_logs_policy_arn" {
  description = "ARN of the Lambda CloudWatch Logs policy"
  value       = aws_iam_policy.lambda_cloudwatch_logs.arn
}

output "lambda_bedrock_policy_arn" {
  description = "ARN of the Lambda Bedrock access policy"
  value       = aws_iam_policy.lambda_bedrock_access.arn
}

output "lambda_kms_policy_arn" {
  description = "ARN of the Lambda KMS access policy"
  value       = aws_iam_policy.lambda_kms_access.arn
}

output "lambda_vpc_policy_arn" {
  description = "ARN of the Lambda VPC access policy"
  value       = aws_iam_policy.lambda_vpc_access.arn
}

# VPC Flow Logs Role Outputs
output "vpc_flow_logs_role_arn" {
  description = "ARN of the VPC Flow Logs IAM role"
  value       = aws_iam_role.vpc_flow_logs.arn
}

output "vpc_flow_logs_role_name" {
  description = "Name of the VPC Flow Logs IAM role"
  value       = aws_iam_role.vpc_flow_logs.name
}

output "vpc_flow_logs_role_id" {
  description = "ID of the VPC Flow Logs IAM role"
  value       = aws_iam_role.vpc_flow_logs.id
}
