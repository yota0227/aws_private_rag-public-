# VPC Endpoints Configuration for Seoul Consolidated VPC
# Creates VPC endpoints for AWS services to enable private connectivity
# Requirements: 2.3, 3.6, NFR-1

# Security Group for VPC Endpoints
resource "aws_security_group" "vpc_endpoints" {
  name        = "vpc-endpoints-bos-ai-seoul-prod"
  description = "Security group for VPC endpoints - allows HTTPS from VPC and on-premises"
  vpc_id      = "vpc-066c464f9c750ee9e"  # Seoul consolidated VPC

  # Inbound Rules
  # Allow HTTPS from VPC CIDR
  ingress {
    description = "HTTPS from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.200.0.0/16"]
  }

  # Allow HTTPS from on-premises networks
  ingress {
    description = "HTTPS from on-premises agent network"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["192.128.1.0/24"]
  }

  ingress {
    description = "HTTPS from on-premises FTP network"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["192.128.10.0/24"]
  }

  ingress {
    description = "HTTPS from on-premises OpenSearch network"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["192.128.20.0/24"]
  }

  # Outbound Rules
  # Allow all outbound traffic
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    local.security_tags,
    {
      Name        = "sg-vpc-endpoints-bos-ai-seoul-prod"
      Description = "Security group for VPC endpoints"
    }
  )
}

# VPC Endpoints Module
module "vpc_endpoints" {
  source = "../../modules/security/vpc-endpoints"

  vpc_id             = "vpc-066c464f9c750ee9e"
  subnet_ids         = ["subnet-0f027e9de8e26c18f", "subnet-0625d992edf151017"]  # Replace with actual subnet IDs
  security_group_ids = [aws_security_group.vpc_endpoints.id]
  region             = "ap-northeast-2"

  # Enable required endpoints
  enable_bedrock_runtime_endpoint       = true
  enable_bedrock_agent_runtime_endpoint = true
  enable_secretsmanager_endpoint        = true
  enable_logs_endpoint                  = true
  enable_s3_endpoint                    = true
  enable_opensearch_endpoint            = false  # OpenSearch Serverless has its own VPC endpoint

  # Route table IDs for S3 Gateway endpoint
  route_table_ids = ["rtb-078c8f8a00c2960f7"]  # Replace with actual route table ID

  project_name = "bos-ai"
  environment  = var.environment

  tags = merge(
    local.network_tags,
    {
      Purpose = "Private connectivity to AWS services"
    }
  )

  depends_on = [aws_security_group.vpc_endpoints]
}

# Outputs
output "vpc_endpoints_security_group_id" {
  description = "Security group ID for VPC endpoints"
  value       = aws_security_group.vpc_endpoints.id
}

output "bedrock_runtime_endpoint_id" {
  description = "Bedrock Runtime VPC endpoint ID"
  value       = module.vpc_endpoints.bedrock_runtime_endpoint_id
}

output "secretsmanager_endpoint_id" {
  description = "Secrets Manager VPC endpoint ID"
  value       = module.vpc_endpoints.secretsmanager_endpoint_id
}

output "logs_endpoint_id" {
  description = "CloudWatch Logs VPC endpoint ID"
  value       = module.vpc_endpoints.logs_endpoint_id
}

output "s3_endpoint_id" {
  description = "S3 Gateway VPC endpoint ID"
  value       = module.vpc_endpoints.s3_endpoint_id
}

# Note: Before applying, replace placeholder IDs:
# - subnet-0f027e9de8e26c18f, subnet-0625d992edf151017: Actual private subnet IDs
# - rtb-078c8f8a00c2960f7: Actual private route table ID
