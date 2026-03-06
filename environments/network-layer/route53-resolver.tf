# ============================================================================
# Route53 Resolver Endpoints - Private RAG VPC (10.10.0.0/16)
# Purpose: DNS resolution for on-premises → AWS Private Hosted Zone
# Migration: Logging VPC (10.200.x.x) → Private RAG VPC (10.10.x.x)
#
# Requirements: 1.1, 1.2, 1.3, 1.4, 1.7
# ============================================================================

# ----------------------------------------------------------------------------
# Security Groups
# ----------------------------------------------------------------------------

# Resolver Inbound SG: 온프렘에서 DNS 쿼리 수신
resource "aws_security_group" "resolver_inbound" {
  provider = aws.seoul

  name        = "resolver-inbound-private-rag-${var.environment}"
  description = "Route53 Resolver Inbound - Allow DNS from on-premises only"
  vpc_id      = module.vpc_frontend.vpc_id

  # TCP 53 from on-premises
  ingress {
    description = "DNS TCP from on-premises"
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = ["192.128.0.0/16"]
  }

  # UDP 53 from on-premises
  ingress {
    description = "DNS UDP from on-premises"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["192.128.0.0/16"]
  }

  # TCP 53 from VPC internal (TGW ENI uses VPC CIDR as source)
  ingress {
    description = "DNS TCP from VPC internal (TGW transit)"
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = ["10.10.0.0/16"]
  }

  # UDP 53 from VPC internal (TGW ENI uses VPC CIDR as source)
  ingress {
    description = "DNS UDP from VPC internal (TGW transit)"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["10.10.0.0/16"]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.seoul_tags,
    {
      Name    = "resolver-inbound-private-rag-${var.environment}"
      Purpose = "Route53 Resolver Inbound DNS"
    }
  )
}

# Resolver Outbound SG: AWS에서 온프렘 DNS로 포워딩
resource "aws_security_group" "resolver_outbound" {
  provider = aws.seoul

  name        = "resolver-outbound-private-rag-${var.environment}"
  description = "Route53 Resolver Outbound - Allow DNS forwarding to on-premises"
  vpc_id      = module.vpc_frontend.vpc_id

  egress {
    description = "DNS TCP to all"
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "DNS UDP to all"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.seoul_tags,
    {
      Name    = "resolver-outbound-private-rag-${var.environment}"
      Purpose = "Route53 Resolver Outbound DNS"
    }
  )
}

# ----------------------------------------------------------------------------
# Route53 Resolver Inbound Endpoint
# 온프렘 DNS → AWS Private Hosted Zone 해석
# ----------------------------------------------------------------------------

resource "aws_route53_resolver_endpoint" "inbound" {
  provider = aws.seoul

  name      = "resolver-inbound-private-rag-${var.environment}"
  direction = "INBOUND"

  security_group_ids = [aws_security_group.resolver_inbound.id]

  ip_address {
    subnet_id = module.vpc_frontend.private_subnet_ids[0]  # 10.10.1.0/24
  }

  ip_address {
    subnet_id = module.vpc_frontend.private_subnet_ids[1]  # 10.10.2.0/24
  }

  tags = merge(
    local.seoul_tags,
    {
      Name    = "resolver-inbound-private-rag-${var.environment}"
      Purpose = "On-premises DNS to AWS Private Hosted Zone"
    }
  )
}

# ----------------------------------------------------------------------------
# Route53 Resolver Outbound Endpoint
# AWS → 온프렘 DNS 포워딩 (향후 확장용)
# ----------------------------------------------------------------------------

resource "aws_route53_resolver_endpoint" "outbound" {
  provider = aws.seoul

  name      = "resolver-outbound-private-rag-${var.environment}"
  direction = "OUTBOUND"

  security_group_ids = [aws_security_group.resolver_outbound.id]

  ip_address {
    subnet_id = module.vpc_frontend.private_subnet_ids[0]  # 10.10.1.0/24
  }

  ip_address {
    subnet_id = module.vpc_frontend.private_subnet_ids[1]  # 10.10.2.0/24
  }

  tags = merge(
    local.seoul_tags,
    {
      Name    = "resolver-outbound-private-rag-${var.environment}"
      Purpose = "AWS to on-premises DNS forwarding"
    }
  )
}

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

output "resolver_inbound_endpoint_id" {
  description = "Route53 Resolver Inbound Endpoint ID"
  value       = aws_route53_resolver_endpoint.inbound.id
}

output "resolver_inbound_ip_addresses" {
  description = "Route53 Resolver Inbound IP addresses"
  value       = aws_route53_resolver_endpoint.inbound.ip_address
}

output "resolver_outbound_endpoint_id" {
  description = "Route53 Resolver Outbound Endpoint ID"
  value       = aws_route53_resolver_endpoint.outbound.id
}

# ============================================================================
# 기존 Logging VPC Resolver 삭제 대상 (수동 삭제 필요)
# ============================================================================
#
# 아래 리소스는 콘솔에서 수동 생성되었으므로 Terraform으로 관리되지 않음.
# Private RAG VPC Resolver가 정상 동작 확인 후 AWS 콘솔에서 수동 삭제할 것.
#
# 삭제 대상:
#   - Route53 Resolver Inbound: rslvr-in-79867dcffe644a378
#     IP: 10.200.1.178, 10.200.2.123 (Logging VPC)
#   - Route53 Resolver Outbound: rslvr-out-528276266e13403aa
#     (Logging VPC)
#
# 삭제 전 확인사항:
#   1. Private RAG VPC Resolver Inbound가 정상 동작하는지 확인
#   2. 사내 DNS 조건부 포워딩이 새 Resolver IP를 가리키는지 확인
#   3. 온프렘에서 nslookup rag.corp.bos-semi.com 정상 응답 확인
#
# 삭제 절차:
#   1. AWS Console → Route53 → Resolver → Inbound endpoints
#   2. rslvr-in-79867dcffe644a378 선택 → Delete
#   3. AWS Console → Route53 → Resolver → Outbound endpoints
#   4. rslvr-out-528276266e13403aa 선택 → Delete
#   5. 관련 Security Group 삭제
# ============================================================================
