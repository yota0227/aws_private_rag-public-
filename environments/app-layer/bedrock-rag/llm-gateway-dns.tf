# =============================================================================
# LLM Gateway - Route53 DNS Records
#
# VPC Endpoint ENI IP를 직접 A 레코드로 등록.
# ALIAS는 VPC 외부(온프레미스 forwarder)에서 empty name을 반환하므로 사용 불가.
# ENI IP: 10.10.1.21 (subnet-0ec356f8f9af0ffca), 10.10.2.75 (subnet-014a5abf9c1a76b07)
#
# Requirements: 10.1, 10.2, 10.3
# =============================================================================

# -----------------------------------------------------------------------------
# DNS Record: llm.corp.bos-semi.com → execute-api VPC Endpoint ENI IPs
# Requirement 10.1
# -----------------------------------------------------------------------------

resource "aws_route53_record" "llm_gateway_llm" {
  provider = aws.seoul

  zone_id = aws_route53_zone.corp.zone_id
  name    = "llm.corp.bos-semi.com"
  type    = "A"
  ttl     = 60

  records = [
    "10.10.1.21",
    "10.10.2.75",
  ]
}

# -----------------------------------------------------------------------------
# DNS Record: mcp.corp.bos-semi.com → execute-api VPC Endpoint ENI IPs
# Requirement 10.2
# -----------------------------------------------------------------------------

resource "aws_route53_record" "llm_gateway_mcp" {
  provider = aws.seoul

  zone_id = aws_route53_zone.corp.zone_id
  name    = "mcp.corp.bos-semi.com"
  type    = "A"
  ttl     = 60

  records = [
    "10.10.1.21",
    "10.10.2.75",
  ]
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "llm_gateway_llm_domain" {
  description = "LLM Gateway LiteLLM custom domain"
  value       = "llm.corp.bos-semi.com"
}

output "llm_gateway_mcp_domain" {
  description = "LLM Gateway MCP Server custom domain"
  value       = "mcp.corp.bos-semi.com"
}

output "llm_gateway_llm_invoke_url" {
  description = "LLM Gateway LiteLLM invoke URL via custom domain"
  value       = "https://llm.corp.bos-semi.com/prod/llm"
}

output "llm_gateway_mcp_invoke_url" {
  description = "LLM Gateway MCP Server invoke URL via custom domain"
  value       = "https://mcp.corp.bos-semi.com/prod/mcp"
}
