# Network Layer Outputs with Transit Gateway
# Exposes VPC IDs, subnet IDs, security group IDs, and TGW information

# ============================================================================
# Logging VPC Outputs
# ============================================================================

output "logging_vpc_id" {
  description = "ID of the Logging Pipeline VPC"
  value       = module.vpc_logging.vpc_id
}

output "logging_vpc_cidr" {
  description = "CIDR block of the Logging Pipeline VPC"
  value       = module.vpc_logging.vpc_cidr
}

output "logging_private_subnet_ids" {
  description = "List of private subnet IDs in Logging VPC"
  value       = module.vpc_logging.private_subnet_ids
}

output "logging_public_subnet_ids" {
  description = "List of public subnet IDs in Logging VPC"
  value       = module.vpc_logging.public_subnet_ids
}

output "logging_private_route_table_ids" {
  description = "List of private route table IDs in Logging VPC"
  value       = module.vpc_logging.private_route_table_ids
}

# ============================================================================
# Frontend VPC Outputs
# ============================================================================

output "frontend_vpc_id" {
  description = "ID of the BOS-AI Frontend VPC"
  value       = module.vpc_frontend.vpc_id
}

output "frontend_vpc_cidr" {
  description = "CIDR block of the Frontend VPC"
  value       = module.vpc_frontend.vpc_cidr
}

output "frontend_private_subnet_ids" {
  description = "List of private subnet IDs in Frontend VPC"
  value       = module.vpc_frontend.private_subnet_ids
}

output "frontend_private_route_table_ids" {
  description = "List of private route table IDs in Frontend VPC"
  value       = module.vpc_frontend.private_route_table_ids
}

# ============================================================================
# US Backend VPC Outputs
# ============================================================================

output "us_vpc_id" {
  description = "ID of the US Backend VPC"
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

# ============================================================================
# Transit Gateway Outputs
# Note: Commented out until TGW module is uncommented
# ============================================================================

# output "transit_gateway_id" {
#   description = "ID of the Transit Gateway"
#   value       = module.transit_gateway.transit_gateway_id
# }
# 
# output "transit_gateway_arn" {
#   description = "ARN of the Transit Gateway"
#   value       = module.transit_gateway.transit_gateway_arn
# }
# 
# output "transit_gateway_default_route_table_id" {
#   description = "ID of the default TGW route table"
#   value       = module.transit_gateway.transit_gateway_association_default_route_table_id
# }
# 
# output "tgw_vpc_attachment_ids" {
#   description = "Map of TGW VPC attachment IDs"
#   value       = module.transit_gateway.vpc_attachment_ids
# }

# ============================================================================
# VPC Peering Outputs
# ============================================================================

output "vpc_peering_connection_id" {
  description = "ID of the VPC peering connection between Seoul Frontend and US Backend"
  value       = module.vpc_peering.peering_connection_id
}

output "vpc_peering_status" {
  description = "Status of the VPC peering connection"
  value       = module.vpc_peering.peering_status
}

# ============================================================================
# Security Group Outputs - Logging VPC
# ============================================================================

output "logging_security_group_ids" {
  description = "Map of all security group IDs in Logging VPC"
  value       = module.security_groups_logging.all_security_group_ids
}

# ============================================================================
# Security Group Outputs - Frontend VPC
# ============================================================================

output "frontend_security_group_ids" {
  description = "Map of all security group IDs in Frontend VPC"
  value       = module.security_groups_frontend.all_security_group_ids
}

# ============================================================================
# Security Group Outputs - US Backend VPC
# ============================================================================

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

# ============================================================================
# Convenience Outputs
# ============================================================================

output "bedrock_security_group_ids" {
  description = "Security group IDs for Bedrock workload (Lambda, OpenSearch, VPC Endpoints)"
  value = {
    lambda        = module.security_groups_us.lambda_security_group_id
    opensearch    = module.security_groups_us.opensearch_security_group_id
    vpc_endpoints = module.security_groups_us.vpc_endpoints_security_group_id
  }
}

output "all_vpc_ids" {
  description = "Map of all VPC IDs"
  value = {
    logging  = module.vpc_logging.vpc_id
    frontend = module.vpc_frontend.vpc_id
    backend  = module.vpc_us.vpc_id
  }
}

output "all_vpc_cidrs" {
  description = "Map of all VPC CIDRs"
  value = {
    logging  = module.vpc_logging.vpc_cidr
    frontend = module.vpc_frontend.vpc_cidr
    backend  = module.vpc_us.vpc_cidr
  }
}
