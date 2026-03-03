# Bedrock Runtime Endpoint Outputs
output "bedrock_runtime_endpoint_id" {
  description = "ID of the Bedrock Runtime VPC endpoint"
  value       = var.enable_bedrock_runtime_endpoint ? aws_vpc_endpoint.bedrock_runtime[0].id : null
}

output "bedrock_runtime_endpoint_dns_entries" {
  description = "DNS entries for the Bedrock Runtime VPC endpoint"
  value       = var.enable_bedrock_runtime_endpoint ? aws_vpc_endpoint.bedrock_runtime[0].dns_entry : []
}

output "bedrock_runtime_endpoint_network_interface_ids" {
  description = "Network interface IDs for the Bedrock Runtime VPC endpoint"
  value       = var.enable_bedrock_runtime_endpoint ? aws_vpc_endpoint.bedrock_runtime[0].network_interface_ids : []
}

# Bedrock Agent Runtime Endpoint Outputs
output "bedrock_agent_runtime_endpoint_id" {
  description = "ID of the Bedrock Agent Runtime VPC endpoint"
  value       = var.enable_bedrock_agent_runtime_endpoint ? aws_vpc_endpoint.bedrock_agent_runtime[0].id : null
}

output "bedrock_agent_runtime_endpoint_dns_entries" {
  description = "DNS entries for the Bedrock Agent Runtime VPC endpoint"
  value       = var.enable_bedrock_agent_runtime_endpoint ? aws_vpc_endpoint.bedrock_agent_runtime[0].dns_entry : []
}

output "bedrock_agent_runtime_endpoint_network_interface_ids" {
  description = "Network interface IDs for the Bedrock Agent Runtime VPC endpoint"
  value       = var.enable_bedrock_agent_runtime_endpoint ? aws_vpc_endpoint.bedrock_agent_runtime[0].network_interface_ids : []
}

# S3 Endpoint Outputs
output "s3_endpoint_id" {
  description = "ID of the S3 Gateway VPC endpoint"
  value       = var.enable_s3_endpoint ? aws_vpc_endpoint.s3[0].id : null
}

output "s3_endpoint_prefix_list_id" {
  description = "Prefix list ID for the S3 Gateway endpoint"
  value       = var.enable_s3_endpoint ? aws_vpc_endpoint.s3[0].prefix_list_id : null
}

# OpenSearch Serverless Endpoint Outputs
output "opensearch_endpoint_id" {
  description = "ID of the OpenSearch Serverless VPC endpoint"
  value       = var.enable_opensearch_endpoint ? aws_vpc_endpoint.opensearch[0].id : null
}

output "opensearch_endpoint_dns_entries" {
  description = "DNS entries for the OpenSearch Serverless VPC endpoint"
  value       = var.enable_opensearch_endpoint ? aws_vpc_endpoint.opensearch[0].dns_entry : []
}

output "opensearch_endpoint_network_interface_ids" {
  description = "Network interface IDs for the OpenSearch Serverless VPC endpoint"
  value       = var.enable_opensearch_endpoint ? aws_vpc_endpoint.opensearch[0].network_interface_ids : []
}

# All Endpoint IDs
output "all_endpoint_ids" {
  description = "Map of all VPC endpoint IDs"
  value = {
    bedrock_runtime       = var.enable_bedrock_runtime_endpoint ? aws_vpc_endpoint.bedrock_runtime[0].id : null
    bedrock_agent_runtime = var.enable_bedrock_agent_runtime_endpoint ? aws_vpc_endpoint.bedrock_agent_runtime[0].id : null
    s3                    = var.enable_s3_endpoint ? aws_vpc_endpoint.s3[0].id : null
    opensearch            = var.enable_opensearch_endpoint ? aws_vpc_endpoint.opensearch[0].id : null
  }
}
