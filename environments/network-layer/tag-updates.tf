# Tag Updates for Existing Resources
# This file contains tag updates for existing VPC resources to align with new naming conventions
# Requirements: 2.4, 3.1, NFR-4
#
# IMPORTANT: These are metadata-only changes and do not affect resource functionality

# Local variables for tag management
locals {
  # Base tags for all resources
  base_tags = {
    Project     = "BOS-AI"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  # Network layer tags
  network_tags = merge(
    local.base_tags,
    {
      Layer = "Network"
      Owner = "Infrastructure Team"
    }
  )

  # Security layer tags
  security_tags = merge(
    local.base_tags,
    {
      Layer = "Security"
      Owner = "Security Team"
    }
  )
}

# VPC Tag Update
# Updates tags for existing Seoul PoC VPC to new naming convention
resource "aws_ec2_tag" "vpc_name" {
  resource_id = "vpc-066c464f9c750ee9e"
  key         = "Name"
  value       = "vpc-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "vpc_project" {
  resource_id = "vpc-066c464f9c750ee9e"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "vpc_environment" {
  resource_id = "vpc-066c464f9c750ee9e"
  key         = "Environment"
  value       = "Production"
}

resource "aws_ec2_tag" "vpc_managed_by" {
  resource_id = "vpc-066c464f9c750ee9e"
  key         = "ManagedBy"
  value       = "Terraform"
}

resource "aws_ec2_tag" "vpc_layer" {
  resource_id = "vpc-066c464f9c750ee9e"
  key         = "Layer"
  value       = "Network"
}

resource "aws_ec2_tag" "vpc_owner" {
  resource_id = "vpc-066c464f9c750ee9e"
  key         = "Owner"
  value       = "Infrastructure Team"
}

resource "aws_ec2_tag" "vpc_description" {
  resource_id = "vpc-066c464f9c750ee9e"
  key         = "Description"
  value       = "Consolidated VPC for logging and AI workloads with VPN connectivity"
}

# Subnet Tag Updates
# Private Subnet 2a
resource "aws_ec2_tag" "subnet_private_2a_name" {
  resource_id = "subnet-0f027e9de8e26c18f"  # Replace with actual subnet ID
  key         = "Name"
  value       = "sn-private-bos-ai-seoul-prod-01a"
}

resource "aws_ec2_tag" "subnet_private_2a_project" {
  resource_id = "subnet-0f027e9de8e26c18f"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "subnet_private_2a_environment" {
  resource_id = "subnet-0f027e9de8e26c18f"
  key         = "Environment"
  value       = "Production"
}

resource "aws_ec2_tag" "subnet_private_2a_managed_by" {
  resource_id = "subnet-0f027e9de8e26c18f"
  key         = "ManagedBy"
  value       = "Terraform"
}

resource "aws_ec2_tag" "subnet_private_2a_layer" {
  resource_id = "subnet-0f027e9de8e26c18f"
  key         = "Layer"
  value       = "Network"
}

resource "aws_ec2_tag" "subnet_private_2a_description" {
  resource_id = "subnet-0f027e9de8e26c18f"
  key         = "Description"
  value       = "Private subnet for Lambda and OpenSearch in AZ 2a"
}

# Private Subnet 2c
resource "aws_ec2_tag" "subnet_private_2c_name" {
  resource_id = "subnet-0625d992edf151017"  # Replace with actual subnet ID
  key         = "Name"
  value       = "sn-private-bos-ai-seoul-prod-01c"
}

resource "aws_ec2_tag" "subnet_private_2c_project" {
  resource_id = "subnet-0625d992edf151017"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "subnet_private_2c_environment" {
  resource_id = "subnet-0625d992edf151017"
  key         = "Environment"
  value       = "Production"
}

resource "aws_ec2_tag" "subnet_private_2c_managed_by" {
  resource_id = "subnet-0625d992edf151017"
  key         = "ManagedBy"
  value       = "Terraform"
}

resource "aws_ec2_tag" "subnet_private_2c_layer" {
  resource_id = "subnet-0625d992edf151017"
  key         = "Layer"
  value       = "Network"
}

resource "aws_ec2_tag" "subnet_private_2c_description" {
  resource_id = "subnet-0625d992edf151017"
  key         = "Description"
  value       = "Private subnet for Lambda and OpenSearch in AZ 2c"
}

# Public Subnet 2a
resource "aws_ec2_tag" "subnet_public_2a_name" {
  resource_id = "subnet-06d3c439cedf14742"  # Replace with actual subnet ID
  key         = "Name"
  value       = "sn-public-bos-ai-seoul-prod-01a"
}

resource "aws_ec2_tag" "subnet_public_2a_project" {
  resource_id = "subnet-06d3c439cedf14742"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "subnet_public_2a_environment" {
  resource_id = "subnet-06d3c439cedf14742"
  key         = "Environment"
  value       = "Production"
}

resource "aws_ec2_tag" "subnet_public_2a_managed_by" {
  resource_id = "subnet-06d3c439cedf14742"
  key         = "ManagedBy"
  value       = "Terraform"
}

resource "aws_ec2_tag" "subnet_public_2a_layer" {
  resource_id = "subnet-06d3c439cedf14742"
  key         = "Layer"
  value       = "Network"
}

resource "aws_ec2_tag" "subnet_public_2a_description" {
  resource_id = "subnet-06d3c439cedf14742"
  key         = "Description"
  value       = "Public subnet for NAT Gateway and Bastion in AZ 2a"
}

# Public Subnet 2c
resource "aws_ec2_tag" "subnet_public_2c_name" {
  resource_id = "subnet-0a9ba13fade9c4c66"  # Replace with actual subnet ID
  key         = "Name"
  value       = "sn-public-bos-ai-seoul-prod-01c"
}

resource "aws_ec2_tag" "subnet_public_2c_project" {
  resource_id = "subnet-0a9ba13fade9c4c66"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "subnet_public_2c_environment" {
  resource_id = "subnet-0a9ba13fade9c4c66"
  key         = "Environment"
  value       = "Production"
}

resource "aws_ec2_tag" "subnet_public_2c_managed_by" {
  resource_id = "subnet-0a9ba13fade9c4c66"
  key         = "ManagedBy"
  value       = "Terraform"
}

resource "aws_ec2_tag" "subnet_public_2c_layer" {
  resource_id = "subnet-0a9ba13fade9c4c66"
  key         = "Layer"
  value       = "Network"
}

resource "aws_ec2_tag" "subnet_public_2c_description" {
  resource_id = "subnet-0a9ba13fade9c4c66"
  key         = "Description"
  value       = "Public subnet reserved for future use in AZ 2c"
}

# Route Table Tag Updates
# Private Route Table
resource "aws_ec2_tag" "rtb_private_name" {
  resource_id = "rtb-078c8f8a00c2960f7"  # Replace with actual route table ID
  key         = "Name"
  value       = "rtb-private-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "rtb_private_project" {
  resource_id = "rtb-078c8f8a00c2960f7"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "rtb_private_environment" {
  resource_id = "rtb-078c8f8a00c2960f7"
  key         = "Environment"
  value       = "Production"
}

resource "aws_ec2_tag" "rtb_private_managed_by" {
  resource_id = "rtb-078c8f8a00c2960f7"
  key         = "ManagedBy"
  value       = "Terraform"
}

resource "aws_ec2_tag" "rtb_private_layer" {
  resource_id = "rtb-078c8f8a00c2960f7"
  key         = "Layer"
  value       = "Network"
}

# Public Route Table
resource "aws_ec2_tag" "rtb_public_name" {
  resource_id = "rtb-0446cd3e4c6a6f2ce"  # Replace with actual route table ID
  key         = "Name"
  value       = "rtb-public-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "rtb_public_project" {
  resource_id = "rtb-0446cd3e4c6a6f2ce"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "rtb_public_environment" {
  resource_id = "rtb-0446cd3e4c6a6f2ce"
  key         = "Environment"
  value       = "Production"
}

resource "aws_ec2_tag" "rtb_public_managed_by" {
  resource_id = "rtb-0446cd3e4c6a6f2ce"
  key         = "ManagedBy"
  value       = "Terraform"
}

resource "aws_ec2_tag" "rtb_public_layer" {
  resource_id = "rtb-0446cd3e4c6a6f2ce"
  key         = "Layer"
  value       = "Network"
}

# NAT Gateway Tag Updates
resource "aws_ec2_tag" "nat_gateway_name" {
  resource_id = "nat-03dc6eb89ecb8f21c"  # Replace with actual NAT Gateway ID
  key         = "Name"
  value       = "nat-bos-ai-seoul-prod-01a"
}

resource "aws_ec2_tag" "nat_gateway_project" {
  resource_id = "nat-03dc6eb89ecb8f21c"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "nat_gateway_environment" {
  resource_id = "nat-03dc6eb89ecb8f21c"
  key         = "Environment"
  value       = "Production"
}

resource "aws_ec2_tag" "nat_gateway_managed_by" {
  resource_id = "nat-03dc6eb89ecb8f21c"
  key         = "ManagedBy"
  value       = "Terraform"
}

resource "aws_ec2_tag" "nat_gateway_layer" {
  resource_id = "nat-03dc6eb89ecb8f21c"
  key         = "Layer"
  value       = "Network"
}

# Internet Gateway Tag Updates
resource "aws_ec2_tag" "igw_name" {
  resource_id = "igw-007a80a4355e38fc4"  # Replace with actual Internet Gateway ID
  key         = "Name"
  value       = "igw-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "igw_project" {
  resource_id = "igw-007a80a4355e38fc4"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "igw_environment" {
  resource_id = "igw-007a80a4355e38fc4"
  key         = "Environment"
  value       = "Production"
}

resource "aws_ec2_tag" "igw_managed_by" {
  resource_id = "igw-007a80a4355e38fc4"
  key         = "ManagedBy"
  value       = "Terraform"
}

resource "aws_ec2_tag" "igw_layer" {
  resource_id = "igw-007a80a4355e38fc4"
  key         = "Layer"
  value       = "Network"
}

# Note: To apply these tag updates, you need to:
# 1. Replace placeholder IDs (subnet-0x0x..., rtb-xxx, nat-xxx, igw-xxx) with actual resource IDs
# 2. Run: terraform plan to preview changes
# 3. Run: terraform apply to apply tag updates
# 4. Verify: aws ec2 describe-vpcs --vpc-ids vpc-066c464f9c750ee9e --query 'Vpcs[0].Tags'
