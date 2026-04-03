# ============================================================================
# QuickSight Security Groups
# Requirements: 1.3, 4.2, 4.3, 7.2
#
# 1. sg-quicksight-endpoints: Quick API/Website VPC Endpoint용
#    - 인바운드: Seoul VPC(10.10.0.0/16) + 온프레미스(192.128.0.0/16) -> HTTPS(443)
#    - 아웃바운드: 0.0.0.0/0 허용 금지, 명시적 CIDR만
#
# 2. sg-quicksight-vpc-conn: Quick VPC Connection ENI용
#    - 아웃바운드: Seoul VPC CIDR(10.10.0.0/16) HTTPS(443)만 허용
#    - Virginia CIDR(10.20.0.0/16) 직접 지정 금지 (VPC Peering 라우팅 경유)
# ============================================================================

# ──────────────────────────────────────────────
# 1. Quick VPC Endpoint Security Group
# ──────────────────────────────────────────────
resource "aws_security_group" "quicksight_endpoints" {
  provider = aws.seoul

  name        = "quicksight-endpoints-bos-ai-seoul-prod"
  description = "Quick VPC Endpoints - HTTPS from Seoul VPC and on-premises only"
  vpc_id      = module.vpc_frontend.vpc_id

  ingress {
    description = "HTTPS from Seoul VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.seoul_vpc_cidr]
  }

  ingress {
    description = "HTTPS from on-premises"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["192.128.0.0/16"]
  }

  egress {
    description = "HTTPS response to Seoul VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.seoul_vpc_cidr]
  }

  egress {
    description = "HTTPS response to on-premises"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["192.128.0.0/16"]
  }

  tags = merge(
    local.seoul_tags,
    {
      Name    = "quicksight-endpoints-bos-ai-seoul-prod"
      Purpose = "Quick VPC Endpoints"
      Service = "quicksight"
    }
  )
}

# ──────────────────────────────────────────────
# 2. Quick VPC Connection Security Group
# Virginia CIDR 직접 지정 금지 - VPC Peering 라우팅 테이블 경유
# ──────────────────────────────────────────────
resource "aws_security_group" "quicksight_vpc_conn" {
  provider = aws.seoul

  name        = "quicksight-vpc-conn-bos-ai-seoul-prod"
  description = "Quick VPC Connection ENI - outbound via Seoul VPC routing only, no direct Virginia access"
  vpc_id      = module.vpc_frontend.vpc_id

  ingress {
    description = "Response traffic from Quick service ENI"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.seoul_vpc_cidr]
  }

  # Seoul VPC CIDR만 허용
  # Virginia(10.20.0.0/16)는 Seoul VPC 라우팅 테이블의 VPC Peering 경로로 자동 전달
  # 직접 지정 금지 (OPA 정책 deny_quicksight_sg_virginia_direct 검증 대상)
  egress {
    description = "HTTPS to Seoul VPC (VPC Peering path to Virginia via routing table)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.seoul_vpc_cidr]
  }

  tags = merge(
    local.seoul_tags,
    {
      Name    = "quicksight-vpc-conn-bos-ai-seoul-prod"
      Purpose = "Quick VPC Connection ENI"
      Service = "quicksight"
    }
  )
}

# ──────────────────────────────────────────────
# Outputs
# ──────────────────────────────────────────────
output "quicksight_endpoints_sg_id" {
  description = "Quick VPC Endpoints Security Group ID"
  value       = aws_security_group.quicksight_endpoints.id
}

output "quicksight_vpc_conn_sg_id" {
  description = "Quick VPC Connection Security Group ID"
  value       = aws_security_group.quicksight_vpc_conn.id
}
