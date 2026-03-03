# Transit Gateway Module
# Creates TGW for connecting multiple VPCs and VPN

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# Transit Gateway
resource "aws_ec2_transit_gateway" "main" {
  description                     = var.description
  amazon_side_asn                 = var.amazon_side_asn
  default_route_table_association = var.default_route_table_association
  default_route_table_propagation = var.default_route_table_propagation
  dns_support                     = var.dns_support
  vpn_ecmp_support                = var.vpn_ecmp_support
  auto_accept_shared_attachments  = var.auto_accept_shared_attachments

  tags = merge(
    var.tags,
    {
      Name = var.tgw_name
    }
  )
}

# VPC Attachments
resource "aws_ec2_transit_gateway_vpc_attachment" "vpc_attachments" {
  for_each = var.vpc_attachments

  transit_gateway_id = aws_ec2_transit_gateway.main.id
  vpc_id             = each.value.vpc_id
  subnet_ids         = each.value.subnet_ids

  dns_support                                     = lookup(each.value, "dns_support", "enable")
  ipv6_support                                    = lookup(each.value, "ipv6_support", "disable")
  appliance_mode_support                          = lookup(each.value, "appliance_mode_support", "disable")
  transit_gateway_default_route_table_association = lookup(each.value, "transit_gateway_default_route_table_association", true)
  transit_gateway_default_route_table_propagation = lookup(each.value, "transit_gateway_default_route_table_propagation", true)

  tags = merge(
    var.tags,
    lookup(each.value, "tags", {}),
    {
      Name = each.key
    }
  )
}

# VPN Attachment (if VPN connection is provided)
resource "aws_ec2_transit_gateway_vpc_attachment" "vpn_attachment" {
  count = var.vpn_connection_id != null ? 1 : 0

  transit_gateway_id = aws_ec2_transit_gateway.main.id
  vpc_id             = var.vpn_vpc_id
  subnet_ids         = var.vpn_subnet_ids

  tags = merge(
    var.tags,
    {
      Name = "${var.tgw_name}-vpn-attachment"
    }
  )
}

# Route Table Associations (if custom route tables are needed)
resource "aws_ec2_transit_gateway_route_table" "custom" {
  for_each = var.custom_route_tables

  transit_gateway_id = aws_ec2_transit_gateway.main.id

  tags = merge(
    var.tags,
    {
      Name = each.key
    }
  )
}

# Static Routes
resource "aws_ec2_transit_gateway_route" "static_routes" {
  for_each = var.static_routes

  destination_cidr_block         = each.value.destination_cidr_block
  transit_gateway_attachment_id  = lookup(each.value, "attachment_id", null)
  transit_gateway_route_table_id = each.value.route_table_id
  blackhole                      = lookup(each.value, "blackhole", false)
}
