# Data Sources for App Layer - QuickSight
# network-layer outputs 참조

data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "bos-ai-terraform-state"
    key    = "network-layer/terraform.tfstate"
    region = "ap-northeast-2"
  }
}

data "aws_caller_identity" "current" {
  provider = aws.seoul
}

locals {
  account_id = data.aws_caller_identity.current.account_id

  frontend_vpc_id     = data.terraform_remote_state.network.outputs.frontend_vpc_id
  frontend_subnet_ids = data.terraform_remote_state.network.outputs.frontend_private_subnet_ids
  qs_vpc_conn_sg_id   = data.terraform_remote_state.network.outputs.quicksight_vpc_conn_sg_id
  qs_api_endpoint_id  = data.terraform_remote_state.network.outputs.quicksight_api_endpoint_id

  common_tags = {
    Project     = "BOS-AI"
    Environment = "prod"
    ManagedBy   = "Terraform"
    Layer       = "app"
    Service     = "quicksight"
  }
}
