# Network Layer Main Configuration
# Creates VPCs in Seoul and US regions, establishes VPC peering, and configures security groups
#
# Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.7, 1.9, 9.2, 11.5, 12.1

# Local variables for common tags
locals {
  common_tags = merge(
    {
      Project     = "BOS-AI-RAG"
      Environment = var.environment
      ManagedBy   = "Terraform"
      Layer       = "network"
    },
    var.additional_tags
  )

  seoul_tags = merge(
    local.common_tags,
    {
      Region = "ap-northeast-2"
    }
  )

  us_tags = merge(
    local.common_tags,
    {
      Region = "us-east-1"
    }
  )
}

# Seoul VPC
# Purpose: Transit Bridge for on-premises to US region access
# No Internet Gateway (No-IGW policy)
module "vpc_seoul" {
  source = "../../modules/network/vpc"

  providers = {
    aws = aws.seoul
  }

  vpc_name             = "bos-ai-seoul-vpc-${var.environment}"
  vpc_cidr             = var.seoul_vpc_cidr
  availability_zones   = var.seoul_availability_zones
  private_subnet_cidrs = var.seoul_private_subnet_cidrs
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = local.seoul_tags
}

# US VPC
# Purpose: AI workload hosting (Bedrock, OpenSearch, Lambda)
# No Internet Gateway (No-IGW policy)
module "vpc_us" {
  source = "../../modules/network/vpc"

  providers = {
    aws = aws.us_east
  }

  vpc_name             = "bos-ai-us-vpc-${var.environment}"
  vpc_cidr             = var.us_vpc_cidr
  availability_zones   = var.us_availability_zones
  private_subnet_cidrs = var.us_private_subnet_cidrs
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = local.us_tags
}

# VPC Peering Connection
# Establishes bidirectional connectivity between Seoul and US VPCs
# Seoul VPC acts as Transit Bridge for on-premises traffic to US region
module "vpc_peering" {
  source = "../../modules/network/peering"

  providers = {
    aws = aws.seoul
  }

  vpc_id      = module.vpc_seoul.vpc_id
  peer_vpc_id = module.vpc_us.vpc_id
  peer_region = "us-east-1"
  peer_cidr   = var.us_vpc_cidr

  auto_accept = true

  requester_route_table_ids = module.vpc_seoul.private_route_table_ids
  accepter_route_table_ids  = module.vpc_us.private_route_table_ids

  tags = merge(
    local.common_tags,
    {
      Name = "bos-ai-seoul-us-peering-${var.environment}"
    }
  )

  depends_on = [
    module.vpc_seoul,
    module.vpc_us
  ]
}

# Security Groups for Seoul VPC
# Minimal security groups for Seoul region (primarily for VPN and transit)
module "security_groups_seoul" {
  source = "../../modules/network/security-groups"

  providers = {
    aws = aws.seoul
  }

  vpc_id        = module.vpc_seoul.vpc_id
  vpc_cidr      = var.seoul_vpc_cidr
  peer_vpc_cidr = var.us_vpc_cidr
  environment   = var.environment

  tags = local.seoul_tags

  depends_on = [module.vpc_seoul]
}

# Security Groups for US VPC
# Security groups for Lambda, OpenSearch, and VPC Endpoints
module "security_groups_us" {
  source = "../../modules/network/security-groups"

  providers = {
    aws = aws.us_east
  }

  vpc_id        = module.vpc_us.vpc_id
  vpc_cidr      = var.us_vpc_cidr
  peer_vpc_cidr = var.seoul_vpc_cidr
  environment   = var.environment

  tags = local.us_tags

  depends_on = [module.vpc_us]
}

# Import existing VPN Gateway
# Requirements: 7.1, 7.2, 7.3
#
# To import an existing VPN Gateway, follow these steps:
# 1. Identify the VPN Gateway ID using AWS CLI:
#    aws ec2 describe-vpn-gateways --region ap-northeast-2
# 2. Replace the placeholder ID below with the actual VPN Gateway ID
# 3. Run: terraform plan -generate-config-out=generated.tf
# 4. Review generated.tf and merge into this configuration
# 5. Run: terraform apply to complete the import
#
# Note: Uncomment the import block below and replace the ID when ready to import

# import {
#   to = aws_vpn_gateway.existing
#   id = "vgw-XXXXXXXXXXXXXXXXX"  # Replace with actual VPN Gateway ID
# }

# VPN Gateway Resource Configuration
# This resource will be managed by Terraform after import
resource "aws_vpn_gateway" "existing" {
  # VPC attachment - connects VPN Gateway to Seoul VPC
  vpc_id = module.vpc_seoul.vpc_id

  # Amazon side ASN for BGP
  amazon_side_asn = 64512

  tags = merge(
    local.seoul_tags,
    {
      Name     = "bos-ai-vpn-gateway-${var.environment}"
      Imported = "true"
      Purpose  = "On-premises connectivity"
    }
  )

  # Ensure VPC is created before attaching VPN Gateway
  depends_on = [module.vpc_seoul]
}

# VPN Gateway Attachment (explicit attachment for clarity)
# Note: The vpc_id in aws_vpn_gateway already creates the attachment,
# but this resource makes the attachment explicit and manageable
resource "aws_vpn_gateway_attachment" "seoul" {
  vpc_id         = module.vpc_seoul.vpc_id
  vpn_gateway_id = aws_vpn_gateway.existing.id

  depends_on = [
    module.vpc_seoul,
    aws_vpn_gateway.existing
  ]
}

# Route propagation for VPN Gateway
# Enables automatic route propagation from VPN Gateway to route tables
resource "aws_vpn_gateway_route_propagation" "seoul_private" {
  count = length(module.vpc_seoul.private_route_table_ids)

  vpn_gateway_id = aws_vpn_gateway.existing.id
  route_table_id = module.vpc_seoul.private_route_table_ids[count.index]

  depends_on = [
    aws_vpn_gateway_attachment.seoul
  ]
}
