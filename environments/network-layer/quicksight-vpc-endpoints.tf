# ============================================================================
# QuickSight VPC Endpoints (PrivateLink)
# Requirements: 1.1, 1.2, 1.4, 1.5, 1.6
#
# - Quick API Endpoint:     com.amazonaws.ap-northeast-2.quicksight
# - Quick Website Endpoint: com.amazonaws.ap-northeast-2.quicksight-website
#
# 두 Endpoint 모두:
#   - Interface 타입, Private DNS ON
#   - Seoul VPC Private 서브넷 배치
#   - sg-quicksight-endpoints SG 연결
# ============================================================================

resource "aws_vpc_endpoint" "quicksight_api" {
  provider = aws.seoul

  vpc_id              = module.vpc_frontend.vpc_id
  service_name        = "com.amazonaws.ap-northeast-2.quicksight"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true

  subnet_ids         = module.vpc_frontend.private_subnet_ids
  security_group_ids = [aws_security_group.quicksight_endpoints.id]

  lifecycle {
    precondition {
      condition     = length(module.vpc_frontend.private_subnet_ids) > 0
      error_message = "Quick API VPC Endpoint 생성 실패: Seoul VPC Private 서브넷이 없습니다. network-layer가 먼저 배포되어야 합니다."
    }
  }

  tags = merge(
    local.seoul_tags,
    {
      Name    = "vpce-quicksight-api-bos-ai-seoul-prod"
      Purpose = "Quick API Private access"
      Service = "quicksight"
    }
  )
}

resource "aws_vpc_endpoint" "quicksight_website" {
  provider = aws.seoul

  vpc_id              = module.vpc_frontend.vpc_id
  service_name        = "com.amazonaws.ap-northeast-2.quicksight-website"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true

  subnet_ids         = module.vpc_frontend.private_subnet_ids
  security_group_ids = [aws_security_group.quicksight_endpoints.id]

  lifecycle {
    precondition {
      condition     = length(module.vpc_frontend.private_subnet_ids) > 0
      error_message = "Quick Website VPC Endpoint 생성 실패: Seoul VPC Private 서브넷이 없습니다. network-layer가 먼저 배포되어야 합니다."
    }
  }

  tags = merge(
    local.seoul_tags,
    {
      Name    = "vpce-quicksight-website-bos-ai-seoul-prod"
      Purpose = "Quick Website Private access"
      Service = "quicksight"
    }
  )
}

# ──────────────────────────────────────────────
# Outputs - app-layer/quicksight에서 참조
# ──────────────────────────────────────────────
output "quicksight_api_endpoint_id" {
  description = "Quick API VPC Endpoint ID"
  value       = aws_vpc_endpoint.quicksight_api.id
}

output "quicksight_api_endpoint_dns" {
  description = "Quick API VPC Endpoint DNS entries (Route53 레코드용)"
  value       = aws_vpc_endpoint.quicksight_api.dns_entry
}

output "quicksight_website_endpoint_id" {
  description = "Quick Website VPC Endpoint ID"
  value       = aws_vpc_endpoint.quicksight_website.id
}
