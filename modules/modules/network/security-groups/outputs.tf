output "lambda_security_group_id" {
  description = "ID of the Lambda security group"
  value       = aws_security_group.lambda.id
}

output "lambda_security_group_arn" {
  description = "ARN of the Lambda security group"
  value       = aws_security_group.lambda.arn
}

output "opensearch_security_group_id" {
  description = "ID of the OpenSearch security group"
  value       = aws_security_group.opensearch.id
}

output "opensearch_security_group_arn" {
  description = "ARN of the OpenSearch security group"
  value       = aws_security_group.opensearch.arn
}

output "vpc_endpoints_security_group_id" {
  description = "ID of the VPC Endpoints security group"
  value       = aws_security_group.vpc_endpoints.id
}

output "vpc_endpoints_security_group_arn" {
  description = "ARN of the VPC Endpoints security group"
  value       = aws_security_group.vpc_endpoints.arn
}

output "all_security_group_ids" {
  description = "Map of all security group IDs for easy reference"
  value = {
    lambda        = aws_security_group.lambda.id
    opensearch    = aws_security_group.opensearch.id
    vpc_endpoints = aws_security_group.vpc_endpoints.id
  }
}
