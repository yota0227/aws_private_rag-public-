# ============================================================================
# Route53 Private Hosted Zone - corp.bos-semi.com
# Purpose: 커스텀 도메인(rag.corp.bos-semi.com)으로 Private API Gateway 접근
#
# Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
# ============================================================================

# ----------------------------------------------------------------------------
# Private Hosted Zone
# ----------------------------------------------------------------------------

resource "aws_route53_zone" "corp" {
  provider = aws.seoul

  name = "corp.bos-semi.com"

  vpc {
    vpc_id     = local.frontend_vpc_id  # Private RAG VPC만 연결
    vpc_region = "ap-northeast-2"
  }

  comment = "Private Hosted Zone for RAG API - accessible only from Private RAG VPC"

  tags = merge(local.common_tags, {
    Name    = "phz-corp-bos-semi-com-${var.environment}"
    Purpose = "Private RAG API DNS"
  })
}

# ----------------------------------------------------------------------------
# DNS Record: rag.corp.bos-semi.com → execute-api VPC Endpoint
# ACM 인증서 없이 VPC Endpoint DNS를 직접 CNAME으로 연결
# Private API Gateway 호출: https://rag.corp.bos-semi.com/{stage}/rag/query
# 실제 요청 시 Host 헤더에 {api-id}.execute-api.ap-northeast-2.amazonaws.com 필요
# ----------------------------------------------------------------------------

# execute-api VPC Endpoint의 DNS 이름 조회
data "aws_vpc_endpoint" "execute_api" {
  provider = aws.seoul
  id       = local.frontend_execute_api_endpoint_id
}

resource "aws_route53_record" "rag_api" {
  provider = aws.seoul

  zone_id = aws_route53_zone.corp.zone_id
  name    = "rag.corp.bos-semi.com"
  type    = "A"

  alias {
    # VPC Endpoint의 첫 번째 DNS 이름 사용
    name                   = data.aws_vpc_endpoint.execute_api.dns_entry[0]["dns_name"]
    zone_id                = data.aws_vpc_endpoint.execute_api.dns_entry[0]["hosted_zone_id"]
    evaluate_target_health = true
  }
}

# ----------------------------------------------------------------------------
# API Gateway Custom Domain (ACM 인증서 준비 후 활성화)
# 현재는 ACM Private CA 또는 공인 인증서가 없으므로 비활성화
# 준비되면 var.acm_certificate_arn 설정 후 아래 주석 해제
# ----------------------------------------------------------------------------

# resource "aws_api_gateway_domain_name" "rag" {
#   provider = aws.seoul
#
#   domain_name              = "rag.corp.bos-semi.com"
#   regional_certificate_arn = var.acm_certificate_arn
#
#   endpoint_configuration {
#     types = ["REGIONAL"]
#   }
#
#   tags = merge(local.common_tags, {
#     Name    = "rag-corp-bos-semi-com-${var.environment}"
#     Purpose = "Private RAG API Custom Domain"
#   })
# }

# resource "aws_api_gateway_base_path_mapping" "rag" {
#   provider = aws.seoul
#
#   api_id      = aws_api_gateway_rest_api.private_rag.id
#   stage_name  = aws_api_gateway_stage.prod.stage_name
#   domain_name = aws_api_gateway_domain_name.rag.domain_name
# }

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

output "private_hosted_zone_id" {
  description = "Private Hosted Zone ID for corp.bos-semi.com"
  value       = aws_route53_zone.corp.zone_id
}

output "rag_api_domain" {
  description = "RAG API custom domain"
  value       = "rag.corp.bos-semi.com"
}

output "rag_api_invoke_url" {
  description = "RAG API invoke URL via custom domain"
  value       = "https://rag.corp.bos-semi.com/${var.environment}/rag"
}
