# Neptune 전용 Security Group — Virginia Backend VPC
# Seoul Lambda(10.10.0.0/16)가 VPC Peering 경유로 Neptune 8182 접근
#
# Requirements: 16.3, 16.15

resource "aws_security_group" "neptune" {
  name        = "neptune-${var.project_name}-${var.environment}"
  description = "Neptune Graph DB SG - Allow TCP 8182 from Seoul VPC via Peering"
  vpc_id      = var.vpc_id

  tags = merge(local.tags, {
    Name    = "neptune-${var.project_name}-${var.environment}"
    Purpose = "Neptune Graph DB Access Control"
  })
}

# 인바운드: Seoul Frontend VPC CIDR → Neptune 8182 (VPC Peering 경유)
resource "aws_security_group_rule" "neptune_ingress_seoul_lambda" {
  type              = "ingress"
  from_port         = 8182
  to_port           = 8182
  protocol          = "tcp"
  description       = "Seoul Lambda to Neptune via VPC Peering (RTL Parser Write + Handler Read)"
  security_group_id = aws_security_group.neptune.id
  cidr_blocks       = [var.seoul_vpc_cidr]
}

# 아웃바운드: 모든 트래픽 허용
resource "aws_security_group_rule" "neptune_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  description       = "Allow all outbound traffic"
  security_group_id = aws_security_group.neptune.id
  cidr_blocks       = ["0.0.0.0/0"]
}
