# ============================================================================
# VPC Endpoints - Private RAG VPC (10.10.0.0/16) Frontend
# Purpose: AWS 서비스 Private 연결 (IGW 없는 환경)
#
# Endpoints:
#   - execute-api (Interface, Private DNS OFF) - Private API Gateway 접근
#   - logs (Interface, Private DNS ON) - CloudWatch Logs
#   - secretsmanager (Interface, Private DNS ON) - Secrets Manager
#   - s3 (Gateway) - S3 접근 (데이터 업로드 파이프라인)
#
# Requirements: 2.4, 2.5, 5.5, 7.1, 7.2, 7.3, 7.4, 7.5, 9.4
# ============================================================================

# ----------------------------------------------------------------------------
# 공통 Security Group (Interface Endpoint용)
# ----------------------------------------------------------------------------

resource "aws_security_group" "vpc_endpoints_frontend" {
  provider = aws.seoul

  name        = "vpc-endpoints-private-rag-${var.environment}"
  description = "VPC Endpoints for Private RAG VPC - HTTPS from VPC and on-premises"
  vpc_id      = module.vpc_frontend.vpc_id

  ingress {
    description = "HTTPS from Private RAG VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.seoul_vpc_cidr]  # 10.10.0.0/16
  }

  ingress {
    description = "HTTPS from on-premises"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["192.128.0.0/16"]
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
      Name    = "vpc-endpoints-private-rag-${var.environment}"
      Purpose = "VPC Endpoints for Private RAG"
    }
  )
}

# ----------------------------------------------------------------------------
# execute-api VPC Endpoint (Interface)
# Private DNS ON: API Gateway API ID 기반 도메인 resolve 지원
# 온프렘에서 {api-id}.execute-api.ap-northeast-2.amazonaws.com 으로 직접 접근
# ----------------------------------------------------------------------------

resource "aws_vpc_endpoint" "execute_api" {
  provider = aws.seoul

  vpc_id              = module.vpc_frontend.vpc_id
  service_name        = "com.amazonaws.ap-northeast-2.execute-api"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true  # API ID 기반 도메인 resolve 필요 (온프렘 브라우저 접근)

  subnet_ids         = module.vpc_frontend.private_subnet_ids
  security_group_ids = [aws_security_group.vpc_endpoints_frontend.id]

  tags = merge(
    local.seoul_tags,
    {
      Name    = "vpce-execute-api-private-rag-${var.environment}"
      Purpose = "Private API Gateway access"
    }
  )
}

# ----------------------------------------------------------------------------
# CloudWatch Logs VPC Endpoint (Interface)
# Private DNS ON: Lambda/API Gateway 로그 전송
# ----------------------------------------------------------------------------

resource "aws_vpc_endpoint" "logs" {
  provider = aws.seoul

  vpc_id              = module.vpc_frontend.vpc_id
  service_name        = "com.amazonaws.ap-northeast-2.logs"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true

  subnet_ids         = module.vpc_frontend.private_subnet_ids
  security_group_ids = [aws_security_group.vpc_endpoints_frontend.id]

  tags = merge(
    local.seoul_tags,
    {
      Name    = "vpce-logs-private-rag-${var.environment}"
      Purpose = "CloudWatch Logs for Lambda and API Gateway"
    }
  )
}

# ----------------------------------------------------------------------------
# Secrets Manager VPC Endpoint (Interface)
# Private DNS ON: API 키 및 인증 정보 조회
# ----------------------------------------------------------------------------

resource "aws_vpc_endpoint" "secretsmanager" {
  provider = aws.seoul

  vpc_id              = module.vpc_frontend.vpc_id
  service_name        = "com.amazonaws.ap-northeast-2.secretsmanager"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true

  subnet_ids         = module.vpc_frontend.private_subnet_ids
  security_group_ids = [aws_security_group.vpc_endpoints_frontend.id]

  tags = merge(
    local.seoul_tags,
    {
      Name    = "vpce-secretsmanager-private-rag-${var.environment}"
      Purpose = "Secrets Manager for API keys"
    }
  )
}

# ----------------------------------------------------------------------------
# S3 Gateway VPC Endpoint
# 온프렘에서 VPN → TGW → VPC Endpoint 경로로 S3 접근 (데이터 업로드)
# ----------------------------------------------------------------------------

resource "aws_vpc_endpoint" "s3_gateway" {
  provider = aws.seoul

  vpc_id            = module.vpc_frontend.vpc_id
  service_name      = "com.amazonaws.ap-northeast-2.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc_frontend.private_route_table_ids

  tags = merge(
    local.seoul_tags,
    {
      Name    = "vpce-s3-gateway-private-rag-${var.environment}"
      Purpose = "S3 access for data upload pipeline"
    }
  )
}

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

output "frontend_execute_api_endpoint_id" {
  description = "execute-api VPC Endpoint ID in Private RAG VPC"
  value       = aws_vpc_endpoint.execute_api.id
}

output "frontend_execute_api_dns_entry" {
  description = "execute-api VPC Endpoint DNS entries"
  value       = aws_vpc_endpoint.execute_api.dns_entry
}

output "frontend_logs_endpoint_id" {
  description = "CloudWatch Logs VPC Endpoint ID in Private RAG VPC"
  value       = aws_vpc_endpoint.logs.id
}

output "frontend_secretsmanager_endpoint_id" {
  description = "Secrets Manager VPC Endpoint ID in Private RAG VPC"
  value       = aws_vpc_endpoint.secretsmanager.id
}

output "frontend_s3_gateway_endpoint_id" {
  description = "S3 Gateway VPC Endpoint ID in Private RAG VPC"
  value       = aws_vpc_endpoint.s3_gateway.id
}

output "frontend_vpc_endpoints_sg_id" {
  description = "Security Group ID for VPC Endpoints in Private RAG VPC"
  value       = aws_security_group.vpc_endpoints_frontend.id
}
