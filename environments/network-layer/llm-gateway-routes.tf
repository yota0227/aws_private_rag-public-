# =============================================================================
# LLM Gateway — Frontend VPC Default Route & TGW Static Routes
# Purpose: Add 0.0.0.0/0 → TGW route to Frontend VPC private route tables
#          Add TGW static route for on-prem NAT subnet (192.128.2.0/24)
#
# This enables:
#   1. LiteLLM (Logging VPC) → Bedrock path via TGW → Frontend VPC → VPC Peering → Virginia
#   2. Frontend VPC internet-bound traffic via TGW → Logging VPC NAT Gateway
#   3. Return traffic to on-prem internal firewall NAT subnet (192.128.2.0/24)
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

# =============================================================================
# TGW Static Route — On-prem Internal Firewall NAT Subnet
# Purpose: Return path for traffic from closed network (192.128.1.0/24)
#          that gets SNAT'd to 192.128.2.0/24 by the internal FortiGate firewall
#
# Background:
#   Closed network (192.128.1.208) → Internal FW (SNAT → 192.128.2.254)
#   → L3 Switch → External FW → VPN → AWS TGW → Frontend VPC (10.10.1.62)
#   Return: AWS → TGW needs 192.128.2.0/24 → VPN route to send response back
#
# Note: 192.128.2.0/24 is NOT advertised via BGP from on-prem, so a static
#       route is required. The VPN attachment ID is for the existing Site-to-Site
#       VPN connection (vpn-0b2b65e9414092369).
# =============================================================================

# Data source to reference the existing VPN attachment on TGW
data "aws_ec2_transit_gateway_vpn_attachment" "onprem_vpn" {
  provider = aws.seoul

  transit_gateway_id = aws_ec2_transit_gateway.main.id
  vpn_connection_id  = "vpn-0b2b65e9414092369"
}

# Static route: 192.128.2.0/24 → VPN (on-prem internal firewall NAT subnet)
resource "aws_ec2_transit_gateway_route" "onprem_nat_subnet" {
  provider = aws.seoul

  destination_cidr_block         = "192.128.2.0/24"
  transit_gateway_attachment_id  = data.aws_ec2_transit_gateway_vpn_attachment.onprem_vpn.id
  transit_gateway_route_table_id = aws_ec2_transit_gateway.main.association_default_route_table_id
}
