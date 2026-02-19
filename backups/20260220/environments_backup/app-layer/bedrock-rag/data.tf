# Data Sources for App Layer - Bedrock RAG
# This file retrieves network-layer outputs via terraform_remote_state
#
# Requirements: 9.7, 12.5

# Remote State Data Source for Network Layer
data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "bos-ai-terraform-state"
    key    = "network-layer/terraform.tfstate"
    region = "ap-northeast-2"
  }
}

# Local values derived from network layer
locals {
  # Network Layer Outputs
  us_vpc_id                   = data.terraform_remote_state.network.outputs.us_vpc_id
  us_private_subnet_ids       = data.terraform_remote_state.network.outputs.us_private_subnet_ids
  us_private_route_table_ids  = data.terraform_remote_state.network.outputs.us_private_route_table_ids
  us_security_group_ids       = [
    data.terraform_remote_state.network.outputs.us_lambda_security_group_id,
    data.terraform_remote_state.network.outputs.us_opensearch_security_group_id,
    data.terraform_remote_state.network.outputs.us_vpc_endpoints_security_group_id
  ]
  
  # Common Tags
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
    Layer       = "app"
    Region      = var.us_region
    Owner       = "AI-Team"
    CostCenter  = "AI-Infrastructure"
  }
}
