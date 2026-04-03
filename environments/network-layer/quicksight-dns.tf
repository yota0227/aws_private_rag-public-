# ============================================================================
# QuickSight Route53 Private DNS
# Requirements: 8.1, 8.2, 8.3, 8.4
#
# 기존 Private Hosted Zone(corp.bos-semi.com)에 Quick 레코드 추가
# quick.rag.corp.bos-semi.com -> Quick API VPC Endpoint DNS
#
# 온프레미스 접근 경로:
#   온프렘 DNS -> Route53 Resolver Inbound -> Private Hosted Zone
#   -> Quick API VPC Endpoint Private IP 반환
# ============================================================================

data "aws_route53_zone" "private" {
  provider     = aws.seoul
  name         = "corp.bos-semi.com"
  private_zone = true

  lifecycle {
    postcondition {
      condition     = self.zone_id != ""
      error_message = "Private Hosted Zone(corp.bos-semi.com) 조회 실패: Hosted Zone ID와 VPC 연결 상태를 확인하세요. (기존 Zone ID: Z04599582HCRH2UPCSS34)"
    }
  }
}

# quick.rag.corp.bos-semi.com -> Quick API VPC Endpoint DNS
resource "aws_route53_record" "quicksight" {
  provider = aws.seoul

  zone_id = data.aws_route53_zone.private.zone_id
  name    = "quick.rag.corp.bos-semi.com"
  type    = "CNAME"
  ttl     = 300
  records = [aws_vpc_endpoint.quicksight_api.dns_entry[0]["dns_name"]]
}

# ──────────────────────────────────────────────
# Output
# ──────────────────────────────────────────────
output "quicksight_dns_record_fqdn" {
  description = "Quick Private DNS FQDN (온프레미스 접속 URL용)"
  value       = aws_route53_record.quicksight.fqdn
}
