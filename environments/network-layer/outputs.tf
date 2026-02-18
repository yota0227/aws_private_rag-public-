# Network Layer Outputs
# Exposes VPC IDs, subnet IDs, and security group IDs for app-layer consumption
#
# Requirements: 12.4, 9.7

# Seoul VPC Outputs
output "seoul_vpc_id" {
  description = "ID of the Seoul VPC"
  value       = module.vpc_seoul.vpc_id
}

output "seoul_vpc_cidr" {
  description = "CIDR block of the Seoul VPC"
  value       = module.vpc_seoul.vpc_cidr
}

output "seoul_private_subnet_ids" {
  description = "List of private subnet IDs in Seoul VPC"
  value       = module.vpc_seoul.private_subnet_ids
}

output "seoul_private_route_table_ids" {
  description = "List of private route table IDs in Seoul VPC"
  value       = module.vpc_seoul.private_route_table_ids
}

# US VPC Outputs
output "us_vpc_id" {
  description = "ID of the US VPC"
  value       = module.vpc_us.vpc_id
}

output "us_vpc_cidr" {
  description = "CIDR block of the US VPC"
  value       = module.vpc_us.vpc_cidr
}

output "us_private_subnet_ids" {
  description = "List of private subnet IDs in US VPC"
  value       = module.vpc_us.private_subnet_ids
}

output "us_private_route_table_ids" {
  description = "List of private route table IDs in US VPC"
  value       = module.vpc_us.private_route_table_ids
}

# VPC Peering Outputs
output "vpc_peering_connection_id" {
  description = "ID of the VPC peering connection between Seoul and US"
  value       = module.vpc_peering.peering_connection_id
}

output "vpc_peering_status" {
  description = "Status of the VPC peering connection"
  value       = module.vpc_peering.peering_status
}

# Seoul Security Group Outputs
output "seoul_lambda_security_group_id" {
  description = "ID of the Lambda security group in Seoul VPC"
  value       = module.security_groups_seoul.lambda_security_group_id
}

output "seoul_opensearch_security_group_id" {
  description = "ID of the OpenSearch security group in Seoul VPC"
  value       = module.security_groups_seoul.opensearch_security_group_id
}

output "seoul_vpc_endpoints_security_group_id" {
  description = "ID of the VPC Endpoints security group in Seoul VPC"
  value       = module.security_groups_seoul.vpc_endpoints_security_group_id
}

output "seoul_all_security_group_ids" {
  description = "Map of all security group IDs in Seoul VPC"
  value       = module.security_groups_seoul.all_security_group_ids
}

# US Security Group Outputs
output "us_lambda_security_group_id" {
  description = "ID of the Lambda security group in US VPC"
  value       = module.security_groups_us.lambda_security_group_id
}

output "us_opensearch_security_group_id" {
  description = "ID of the OpenSearch security group in US VPC"
  value       = module.security_groups_us.opensearch_security_group_id
}

output "us_vpc_endpoints_security_group_id" {
  description = "ID of the VPC Endpoints security group in US VPC"
  value       = module.security_groups_us.vpc_endpoints_security_group_id
}

output "us_all_security_group_ids" {
  description = "Map of all security group IDs in US VPC"
  value       = module.security_groups_us.all_security_group_ids
}

# Convenience outputs for app-layer consumption
output "bedrock_security_group_ids" {
  description = "Security group IDs for Bedrock workload (Lambda, OpenSearch, VPC Endpoints)"
  value = {
    lambda        = module.security_groups_us.lambda_security_group_id
    opensearch    = module.security_groups_us.opensearch_security_group_id
    vpc_endpoints = module.security_groups_us.vpc_endpoints_security_group_id
  }
}

# VPN Gateway Outputs
output "vpn_gateway_id" {
  description = "ID of the VPN Gateway attached to Seoul VPC"
  value       = aws_vpn_gateway.existing.id
}

output "vpn_gateway_state" {
  description = "State of the VPN Gateway (should be 'available')"
  value       = aws_vpn_gateway.existing.state
}

output "vpn_gateway_amazon_side_asn" {
  description = "Amazon side ASN for BGP"
  value       = aws_vpn_gateway.existing.amazon_side_asn
}

output "vpn_gateway_attachment_state" {
  description = "State of the VPN Gateway attachment to Seoul VPC"
  value       = aws_vpn_gateway_attachment.seoul.vpc_attachment_state
}
