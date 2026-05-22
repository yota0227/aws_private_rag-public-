# =============================================================================
# LLM Gateway — Frontend VPC Default Route
# Purpose: Add 0.0.0.0/0 → TGW route to Frontend VPC private route tables
#
# This enables:
#   1. LiteLLM (Logging VPC) → Bedrock path via TGW → Frontend VPC → VPC Peering → Virginia
#   2. Frontend VPC internet-bound traffic via TGW → Logging VPC NAT Gateway
#
# NOTE: Uses aws_route (additive-only) to preserve all existing routes.
#       Does NOT modify any existing route table resources.
# =============================================================================

# Default route: Frontend VPC private subnets → TGW (for internet via Logging NAT)
resource "aws_route" "frontend_default_via_tgw" {
  count = length(module.vpc_frontend.private_route_table_ids)

  provider = aws.seoul

  route_table_id         = module.vpc_frontend.private_route_table_ids[count.index]
  destination_cidr_block = "0.0.0.0/0"
  transit_gateway_id     = aws_ec2_transit_gateway.main.id

  depends_on = [
    aws_ec2_transit_gateway_vpc_attachment.frontend_vpc,
    aws_ec2_transit_gateway_vpc_attachment.logging_vpc
  ]
}
