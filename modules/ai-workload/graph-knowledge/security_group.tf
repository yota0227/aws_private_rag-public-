# Neptune 전용 Security Group
# CRITICAL: SG-to-SG 규칙만 허용 — CIDR 기반 인바운드 금지
# Requirements: 16.3, 16.15

# Neptune Security Group — 8182 포트를 특정 Lambda SG에서만 허용
resource "aws_security_group" "neptune" {
  name        = "sg-neptune-${var.project_name}-${var.environment}"
  description = "Neptune Graph DB SG - Allow TCP 8182 from RTL Parser Lambda and Lambda Handler only"
  vpc_id      = var.vpc_id

  tags = merge(local.tags, {
    Name    = "sg-neptune-${var.project_name}-${var.environment}"
    Purpose = "Neptune Graph DB Access Control"
  })
}

# 인바운드: RTL Parser Lambda SG → Neptune 8182 (Write 용도)
resource "aws_security_group_rule" "neptune_ingress_rtl_parser" {
  type                     = "ingress"
  from_port                = 8182
  to_port                  = 8182
  protocol                 = "tcp"
  description              = "RTL Parser Lambda to Neptune Gremlin/openCypher (Write)"
  security_group_id        = aws_security_group.neptune.id
  source_security_group_id = var.rtl_parser_lambda_sg_id
}

# 인바운드: Lambda Handler SG → Neptune 8182 (Read-Only 용도)
resource "aws_security_group_rule" "neptune_ingress_lambda_handler" {
  type                     = "ingress"
  from_port                = 8182
  to_port                  = 8182
  protocol                 = "tcp"
  description              = "Lambda Handler to Neptune Read-Only query access"
  security_group_id        = aws_security_group.neptune.id
  source_security_group_id = var.lambda_handler_sg_id
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
