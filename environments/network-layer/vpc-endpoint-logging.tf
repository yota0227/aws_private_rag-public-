# ============================================================================
# VPC Endpoints - Logging Pipeline VPC (10.200.0.0/16)
# Purpose: Logging VPC에서 AWS 서비스 Private 연결
#
# Endpoints:
#   - kinesis-firehose (Interface) - 로그 스트리밍
#   - logs (Interface)             - CloudWatch Logs
#   - s3 (Gateway)                 - S3 로그 저장
#
# NOTE: Bedrock/Secrets Manager endpoint는 이 VPC에 불필요.
#       Bedrock은 버지니아 Backend VPC(10.20.0.0/16)에서만 사용.
#
# Requirements: 2.3, 3.6, NFR-1
# ============================================================================

# ----------------------------------------------------------------------------
# Security Group (Interface Endpoint용)
# ----------------------------------------------------------------------------

resource "aws_security_group" "vpc_endpoints_logging" {
  provider = aws.seoul

  name        = "vpc-endpoints-logging-seoul-${var.environment}"
  description = "VPC Endpoints for Logging Pipeline VPC - HTTPS from VPC and on-premises"
  vpc_id      = module.vpc_logging.vpc_id

  ingress {
    description = "HTTPS from Logging VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.200.0.0/16"]
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
      Name    = "vpc-endpoints-logging-seoul-${var.environment}"
      Purpose = "VPC Endpoints for Logging Pipeline VPC"
      Layer   = "Security"
    }
  )
}

# ----------------------------------------------------------------------------
# Kinesis Firehose VPC Endpoint (Interface)
# Purpose: 로그 데이터 스트리밍
# ----------------------------------------------------------------------------

resource "aws_vpc_endpoint" "logging_kinesis_firehose" {
  provider = aws.seoul

  vpc_id              = module.vpc_logging.vpc_id
  service_name        = "com.amazonaws.ap-northeast-2.kinesis-firehose"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true

  subnet_ids         = module.vpc_logging.private_subnet_ids
  security_group_ids = [aws_security_group.vpc_endpoints_logging.id]

  tags = merge(
    local.seoul_tags,
    {
      Name    = "vpce-kinesis-firehose-logging-${var.environment}"
      Purpose = "Kinesis Firehose for log streaming"
    }
  )
}

# ----------------------------------------------------------------------------
# CloudWatch Logs VPC Endpoint (Interface)
# Purpose: 로그 그룹/스트림 전송
# ----------------------------------------------------------------------------

resource "aws_vpc_endpoint" "logging_logs" {
  provider = aws.seoul

  vpc_id              = module.vpc_logging.vpc_id
  service_name        = "com.amazonaws.ap-northeast-2.logs"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true

  subnet_ids         = module.vpc_logging.private_subnet_ids
  security_group_ids = [aws_security_group.vpc_endpoints_logging.id]

  tags = merge(
    local.seoul_tags,
    {
      Name    = "vpce-logs-logging-${var.environment}"
      Purpose = "CloudWatch Logs for logging pipeline"
    }
  )
}

# ----------------------------------------------------------------------------
# S3 Gateway VPC Endpoint
# Purpose: 로그 데이터 S3 저장
# ----------------------------------------------------------------------------

resource "aws_vpc_endpoint" "logging_s3_gateway" {
  provider = aws.seoul

  vpc_id            = module.vpc_logging.vpc_id
  service_name      = "com.amazonaws.ap-northeast-2.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc_logging.private_route_table_ids

  tags = merge(
    local.seoul_tags,
    {
      Name    = "vpce-s3-gateway-logging-${var.environment}"
      Purpose = "S3 access for log storage"
    }
  )
}

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

output "logging_vpc_endpoints_sg_id" {
  description = "Security Group ID for VPC Endpoints in Logging VPC"
  value       = aws_security_group.vpc_endpoints_logging.id
}

output "logging_kinesis_firehose_endpoint_id" {
  description = "Kinesis Firehose VPC Endpoint ID in Logging VPC"
  value       = aws_vpc_endpoint.logging_kinesis_firehose.id
}

output "logging_logs_endpoint_id" {
  description = "CloudWatch Logs VPC Endpoint ID in Logging VPC"
  value       = aws_vpc_endpoint.logging_logs.id
}

output "logging_s3_gateway_endpoint_id" {
  description = "S3 Gateway VPC Endpoint ID in Logging VPC"
  value       = aws_vpc_endpoint.logging_s3_gateway.id
}
