output "lambda_log_group_names" {
  description = "Names of Lambda CloudWatch log groups"
  value       = { for k, v in aws_cloudwatch_log_group.lambda : k => v.name }
}

output "lambda_log_group_arns" {
  description = "ARNs of Lambda CloudWatch log groups"
  value       = { for k, v in aws_cloudwatch_log_group.lambda : k => v.arn }
}

output "bedrock_log_group_name" {
  description = "Name of Bedrock CloudWatch log group"
  value       = var.bedrock_kb_name != "" ? aws_cloudwatch_log_group.bedrock[0].name : null
}

output "bedrock_log_group_arn" {
  description = "ARN of Bedrock CloudWatch log group"
  value       = var.bedrock_kb_name != "" ? aws_cloudwatch_log_group.bedrock[0].arn : null
}

output "vpc_flow_log_group_names" {
  description = "Names of VPC Flow Log CloudWatch log groups"
  value       = { for k, v in aws_cloudwatch_log_group.vpc_flow_logs : k => v.name }
}

output "vpc_flow_log_group_arns" {
  description = "ARNs of VPC Flow Log CloudWatch log groups"
  value       = { for k, v in aws_cloudwatch_log_group.vpc_flow_logs : k => v.arn }
}
