# Network ACL for Private Subnets
resource "aws_network_acl" "private" {
  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  tags = merge(
    var.tags,
    {
      Name = "${var.vpc_name}-private-nacl"
      Type = "Private"
    }
  )
}

# Inbound Rules

# Allow inbound traffic from VPC CIDR
resource "aws_network_acl_rule" "private_inbound_vpc" {
  network_acl_id = aws_network_acl.private.id
  rule_number    = 100
  egress         = false
  protocol       = "-1"
  rule_action    = "allow"
  cidr_block     = var.vpc_cidr
}

# Allow inbound traffic from peered VPC (if configured)
resource "aws_network_acl_rule" "private_inbound_peer" {
  count = var.peer_vpc_cidr != "" ? 1 : 0

  network_acl_id = aws_network_acl.private.id
  rule_number    = 110
  egress         = false
  protocol       = "-1"
  rule_action    = "allow"
  cidr_block     = var.peer_vpc_cidr
}

# Allow inbound HTTPS from anywhere (for VPC endpoints)
resource "aws_network_acl_rule" "private_inbound_https" {
  network_acl_id = aws_network_acl.private.id
  rule_number    = 120
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 443
  to_port        = 443
}

# Allow inbound ephemeral ports (for return traffic)
resource "aws_network_acl_rule" "private_inbound_ephemeral" {
  network_acl_id = aws_network_acl.private.id
  rule_number    = 130
  egress         = false
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

# Deny all other inbound traffic (explicit deny)
resource "aws_network_acl_rule" "private_inbound_deny_all" {
  network_acl_id = aws_network_acl.private.id
  rule_number    = 32766
  egress         = false
  protocol       = "-1"
  rule_action    = "deny"
  cidr_block     = "0.0.0.0/0"
}

# Outbound Rules

# Allow outbound traffic to VPC CIDR
resource "aws_network_acl_rule" "private_outbound_vpc" {
  network_acl_id = aws_network_acl.private.id
  rule_number    = 100
  egress         = true
  protocol       = "-1"
  rule_action    = "allow"
  cidr_block     = var.vpc_cidr
}

# Allow outbound traffic to peered VPC (if configured)
resource "aws_network_acl_rule" "private_outbound_peer" {
  count = var.peer_vpc_cidr != "" ? 1 : 0

  network_acl_id = aws_network_acl.private.id
  rule_number    = 110
  egress         = true
  protocol       = "-1"
  rule_action    = "allow"
  cidr_block     = var.peer_vpc_cidr
}

# Allow outbound HTTPS to anywhere (for AWS services via VPC endpoints)
resource "aws_network_acl_rule" "private_outbound_https" {
  network_acl_id = aws_network_acl.private.id
  rule_number    = 120
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 443
  to_port        = 443
}

# Allow outbound ephemeral ports (for return traffic)
resource "aws_network_acl_rule" "private_outbound_ephemeral" {
  network_acl_id = aws_network_acl.private.id
  rule_number    = 130
  egress         = true
  protocol       = "tcp"
  rule_action    = "allow"
  cidr_block     = "0.0.0.0/0"
  from_port      = 1024
  to_port        = 65535
}

# Deny all other outbound traffic (explicit deny)
resource "aws_network_acl_rule" "private_outbound_deny_all" {
  network_acl_id = aws_network_acl.private.id
  rule_number    = 32766
  egress         = true
  protocol       = "-1"
  rule_action    = "deny"
  cidr_block     = "0.0.0.0/0"
}
