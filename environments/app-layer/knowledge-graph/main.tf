# Main Configuration for App Layer - Knowledge Graph (Neptune)
# Neptune을 Virginia Backend VPC에 배포
# Seoul Lambda → VPC Peering → Virginia Neptune (port 8182)
#
# Requirements: 16.4, 16.5, 16.15

locals {
  common_tags = {
    Project     = "BOS-AI"
    Environment = var.environment
    ManagedBy   = "terraform"
    Layer       = "app"
  }

  # Seoul Frontend VPC CIDR — Neptune ingress 허용 대상
  seoul_frontend_vpc_cidr = "10.10.0.0/16"
}

module "neptune" {
  source = "../../../modules/ai-workload/graph-knowledge"

  project_name           = var.project_name
  environment            = var.environment
  vpc_id                 = data.terraform_remote_state.bedrock_rag.outputs.us_vpc_id
  private_subnet_ids     = data.terraform_remote_state.bedrock_rag.outputs.us_private_subnet_ids
  kms_key_arn            = data.terraform_remote_state.bedrock_rag.outputs.kms_key_arn
  neptune_instance_class = var.neptune_instance_class
  seoul_vpc_cidr         = local.seoul_frontend_vpc_cidr
  common_tags            = local.common_tags
}

# Seoul Lambda SG에 egress 8182 추가 (Neptune 접근용)
# RTL Parser Lambda SG
resource "aws_security_group_rule" "rtl_parser_egress_neptune" {
  provider          = aws.seoul
  type              = "egress"
  from_port         = 8182
  to_port           = 8182
  protocol          = "tcp"
  description       = "RTL Parser Lambda to Neptune (Virginia) via VPC Peering"
  security_group_id = data.terraform_remote_state.bedrock_rag.outputs.lambda_security_group_id
  cidr_blocks       = ["10.20.0.0/16"]
}
