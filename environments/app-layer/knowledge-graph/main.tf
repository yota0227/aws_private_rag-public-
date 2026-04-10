# Main Configuration for App Layer - Knowledge Graph (Neptune)
# Neptune 모듈 호출 및 공통 태그 정의
#
# Requirements: 16.4, 16.5, 16.15

locals {
  common_tags = {
    Project     = "BOS-AI"
    Environment = var.environment
    ManagedBy   = "terraform"
    Layer       = "app"
  }
}

module "neptune" {
  source = "../../../modules/ai-workload/graph-knowledge"

  project_name           = var.project_name
  environment            = var.environment
  vpc_id                 = data.terraform_remote_state.network.outputs.frontend_vpc_id
  private_subnet_ids     = data.terraform_remote_state.network.outputs.frontend_private_subnet_ids
  kms_key_arn            = var.kms_key_arn
  neptune_instance_class = var.neptune_instance_class
  rtl_parser_lambda_sg_id = var.rtl_parser_lambda_sg_id
  lambda_handler_sg_id    = var.lambda_handler_sg_id
  common_tags            = local.common_tags
}
