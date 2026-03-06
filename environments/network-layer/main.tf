# Network Layer Main Configuration with Transit Gateway
# Creates VPCs in Seoul, establishes TGW for VPN and VPC connectivity
#
# Architecture:
# - Logging Pipeline VPC (10.200.0.0/16) - Security logging infrastructure
# - BOS-AI Frontend VPC (10.10.0.0/16) - AI workload frontend
# - Transit Gateway - Central hub for VPN and VPC connectivity
# - VPC Peering to US Backend VPC (10.20.0.0/16)

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

# ============================================================================
# Logging Pipeline VPC (10.200.0.0/16)
# Purpose: Security logging infrastructure (EC2 log collectors, Firehose, etc.)
# ============================================================================

module "vpc_logging" {
  source = "../../modules/network/vpc"

  providers = {
    aws = aws.seoul
  }

  vpc_name             = "vpc-logging-seoul-prod"
  vpc_cidr             = "10.200.0.0/16"
  availability_zones   = ["ap-northeast-2a", "ap-northeast-2c"]
  private_subnet_cidrs = ["10.200.1.0/24", "10.200.2.0/24"]
  public_subnet_cidrs  = ["10.200.10.0/24", "10.200.20.0/24"]
  enable_dns_hostnames = true
  enable_dns_support   = true
  enable_nat_gateway   = true
  single_nat_gateway   = true

  tags = merge(
    local.seoul_tags,
    {
      Purpose = "Security Logging Pipeline"
      VPCType = "Logging"
    }
  )
}

# ============================================================================
# BOS-AI Frontend VPC (10.10.0.0/16)
# Purpose: AI workload frontend, connects to US backend via VPC peering
# ============================================================================

module "vpc_frontend" {
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

  tags = merge(
    local.seoul_tags,
    {
      Purpose = "BOS-AI Frontend"
      VPCType = "Frontend"
    }
  )
}

# ============================================================================
# US Backend VPC (10.20.0.0/16)
# Purpose: AI workload backend (Bedrock, OpenSearch, Lambda)
# ============================================================================

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

  tags = merge(
    local.us_tags,
    {
      Purpose = "BOS-AI Backend"
      VPCType = "Backend"
    }
  )
}

# ============================================================================
# Transit Gateway
# Purpose: Central hub for connecting VPN and multiple VPCs
# ============================================================================

# Transit Gateway
resource "aws_ec2_transit_gateway" "main" {
  provider = aws.seoul

  description                     = "Transit Gateway for BOS-AI VPN and VPC connectivity"
  amazon_side_asn                 = 64512
  default_route_table_association = "enable"
  default_route_table_propagation = "enable"
  dns_support                     = "enable"
  vpn_ecmp_support                = "enable"

  tags = merge(
    local.seoul_tags,
    {
      Name = "tgw-bos-ai-seoul-${var.environment}"
    }
  )
}

# TGW Attachment - Logging VPC (10.200.0.0/16)
resource "aws_ec2_transit_gateway_vpc_attachment" "logging_vpc" {
  provider = aws.seoul

  transit_gateway_id = aws_ec2_transit_gateway.main.id
  vpc_id             = module.vpc_logging.vpc_id
  subnet_ids         = module.vpc_logging.private_subnet_ids

  tags = merge(
    local.seoul_tags,
    {
      Name = "tgw-attach-logging-vpc"
      VPC  = "Logging Pipeline"
    }
  )

  depends_on = [aws_ec2_transit_gateway.main]
}

# TGW Attachment - Frontend VPC (10.10.0.0/16)
resource "aws_ec2_transit_gateway_vpc_attachment" "frontend_vpc" {
  provider = aws.seoul

  transit_gateway_id = aws_ec2_transit_gateway.main.id
  vpc_id             = module.vpc_frontend.vpc_id
  subnet_ids         = module.vpc_frontend.private_subnet_ids

  tags = merge(
    local.seoul_tags,
    {
      Name = "tgw-attach-frontend-vpc"
      VPC  = "BOS-AI Frontend"
    }
  )

  depends_on = [aws_ec2_transit_gateway.main]
}

# ============================================================================
# VPC Peering Connection (Frontend Seoul <-> Backend US)
# Purpose: Connect Seoul frontend to US backend for AI workloads
# ============================================================================

module "vpc_peering" {
  source = "../../modules/network/peering"

  providers = {
    aws.requester = aws.seoul
    aws.accepter  = aws.us_east
  }

  vpc_id      = module.vpc_frontend.vpc_id
  peer_vpc_id = module.vpc_us.vpc_id
  peer_region = "us-east-1"
  peer_cidr   = var.us_vpc_cidr

  auto_accept = true

  requester_route_table_ids = module.vpc_frontend.private_route_table_ids
  accepter_route_table_ids  = module.vpc_us.private_route_table_ids

  tags = merge(
    local.common_tags,
    {
      Name = "bos-ai-seoul-us-peering-${var.environment}"
    }
  )

  depends_on = [
    module.vpc_frontend,
    module.vpc_us
  ]
}

# ============================================================================
# Route Table Updates for TGW
# ============================================================================

# Add TGW routes to Logging VPC route tables
resource "aws_route" "logging_to_frontend_via_tgw" {
  count = length(module.vpc_logging.private_route_table_ids)

  provider = aws.seoul

  route_table_id         = module.vpc_logging.private_route_table_ids[count.index]
  destination_cidr_block = var.seoul_vpc_cidr  # 10.10.0.0/16
  transit_gateway_id     = aws_ec2_transit_gateway.main.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.logging_vpc]
}

resource "aws_route" "logging_to_onprem_via_tgw" {
  count = length(module.vpc_logging.private_route_table_ids)

  provider = aws.seoul

  route_table_id         = module.vpc_logging.private_route_table_ids[count.index]
  destination_cidr_block = "192.128.0.0/16"  # On-premises CIDR
  transit_gateway_id     = aws_ec2_transit_gateway.main.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.logging_vpc]
}

# Add TGW routes to Frontend VPC route tables
resource "aws_route" "frontend_to_logging_via_tgw" {
  count = length(module.vpc_frontend.private_route_table_ids)

  provider = aws.seoul

  route_table_id         = module.vpc_frontend.private_route_table_ids[count.index]
  destination_cidr_block = "10.200.0.0/16"  # Logging VPC CIDR
  transit_gateway_id     = aws_ec2_transit_gateway.main.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.frontend_vpc]
}

resource "aws_route" "frontend_to_onprem_via_tgw" {
  count = length(module.vpc_frontend.private_route_table_ids)

  provider = aws.seoul

  route_table_id         = module.vpc_frontend.private_route_table_ids[count.index]
  destination_cidr_block = "192.128.0.0/16"  # On-premises CIDR
  transit_gateway_id     = aws_ec2_transit_gateway.main.id

  depends_on = [aws_ec2_transit_gateway_vpc_attachment.frontend_vpc]
}

# Frontend VPC: Subnet → Route Table Association
# Terraform이 만든 RTB(TGW/Peering 경로 포함)에 서브넷을 명시적으로 연결
# Main RTB(local만 있음)를 사용하지 않도록 함
resource "aws_route_table_association" "frontend_private" {
  count = length(module.vpc_frontend.private_subnet_ids)

  provider = aws.seoul

  subnet_id      = module.vpc_frontend.private_subnet_ids[count.index]
  route_table_id = module.vpc_frontend.private_route_table_ids[count.index]
}

# ============================================================================
# Security Groups
# ============================================================================

# Security Groups for Logging VPC
module "security_groups_logging" {
  source = "../../modules/network/security-groups"

  providers = {
    aws = aws.seoul
  }

  vpc_id        = module.vpc_logging.vpc_id
  vpc_cidr      = "10.200.0.0/16"
  peer_vpc_cidr = var.seoul_vpc_cidr
  environment   = var.environment

  tags = merge(
    local.seoul_tags,
    {
      VPC = "Logging Pipeline"
    }
  )

  depends_on = [module.vpc_logging]
}

# Security Groups for Frontend VPC
module "security_groups_frontend" {
  source = "../../modules/network/security-groups"

  providers = {
    aws = aws.seoul
  }

  vpc_id        = module.vpc_frontend.vpc_id
  vpc_cidr      = var.seoul_vpc_cidr
  peer_vpc_cidr = var.us_vpc_cidr
  environment   = var.environment

  tags = merge(
    local.seoul_tags,
    {
      VPC = "BOS-AI Frontend"
    }
  )

  depends_on = [module.vpc_frontend]
}

# Security Groups for US Backend VPC
module "security_groups_us" {
  source = "../../modules/network/security-groups"

  providers = {
    aws = aws.us_east
  }

  vpc_id        = module.vpc_us.vpc_id
  vpc_cidr      = var.us_vpc_cidr
  peer_vpc_cidr = var.seoul_vpc_cidr
  environment   = var.environment

  tags = merge(
    local.us_tags,
    {
      VPC = "BOS-AI Backend"
    }
  )

  depends_on = [module.vpc_us]
}

# ============================================================================
# VPN Gateway Import (Existing)
# Note: This will be migrated to TGW VPN attachment
# Commented out for now - will be used when TGW is enabled
# ============================================================================

# # Import existing VPN Gateway for Logging VPC
# # This is temporary - will be replaced with TGW VPN attachment
# data "aws_vpn_gateway" "logging_vgw" {
#   provider = aws.seoul
# 
#   filter {
#     name   = "attachment.vpc-id"
#     values = [module.vpc_logging.vpc_id]
#   }
# }
# 
# # Import existing VPN Gateway for Frontend VPC
# # This is temporary - will be replaced with TGW VPN attachment
# data "aws_vpn_gateway" "frontend_vgw" {
#   provider = aws.seoul
# 
#   filter {
#     name   = "attachment.vpc-id"
#     values = [module.vpc_frontend.vpc_id]
#   }
# }
