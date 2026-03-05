# OpenSearch Serverless - Virginia Collection + Seoul VPC Endpoint
# Collection: us-east-1 bos-ai-vectors (module bedrock_rag manages)
# VPC Endpoint: Seoul Private RAG VPC for Lambda access
# Requirements: 3.2, NFR-1, NFR-2

data "aws_opensearchserverless_collection" "virginia" {
  name = "bos-ai-vectors"
}

resource "aws_security_group" "opensearch" {
  provider    = aws.seoul
  name        = "opensearch-vpce-bos-ai-${var.environment}"
  description = "SG for OpenSearch VPC Endpoint - Seoul"
  vpc_id      = local.frontend_vpc_id

  ingress {
    description     = "HTTPS from Lambda"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  ingress {
    description = "HTTPS from Private RAG VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.10.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name    = "opensearch-vpce-bos-ai-${var.environment}"
    Purpose = "OpenSearch VPC Endpoint SG"
  })
}

resource "aws_opensearchserverless_vpc_endpoint" "seoul" {
  provider           = aws.seoul
  name               = "vpce-opensearch-seoul-${var.environment}"
  vpc_id             = local.frontend_vpc_id
  subnet_ids         = local.frontend_private_subnet_ids
  security_group_ids = [aws_security_group.opensearch.id]
}

output "opensearch_collection_arn" {
  description = "Virginia OpenSearch collection ARN"
  value       = data.aws_opensearchserverless_collection.virginia.arn
}

output "opensearch_collection_endpoint" {
  description = "Virginia OpenSearch collection endpoint"
  value       = data.aws_opensearchserverless_collection.virginia.collection_endpoint
}

output "opensearch_seoul_vpc_endpoint_id" {
  description = "Seoul OpenSearch VPC Endpoint ID"
  value       = aws_opensearchserverless_vpc_endpoint.seoul.id
}

output "opensearch_security_group_id" {
  description = "OpenSearch VPC Endpoint SG ID"
  value       = aws_security_group.opensearch.id
}
