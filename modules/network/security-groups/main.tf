# Security Group for Lambda Functions
# Lambda initiates outbound connections only - no inbound traffic
resource "aws_security_group" "lambda" {
  name        = "${var.environment}-lambda-sg"
  description = "Controls outbound access for Lambda document processors"
  vpc_id      = var.vpc_id

  # Default deny inbound - Lambda doesn't accept incoming connections
  # No ingress rules defined

  # Outbound to Bedrock VPC Endpoint
  egress {
    description = "HTTPS to Bedrock VPC Endpoint"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  # Outbound to S3 VPC Endpoint
  egress {
    description = "HTTPS to S3 VPC Endpoint"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  # Outbound to OpenSearch VPC Endpoint
  egress {
    description = "HTTPS to OpenSearch VPC Endpoint"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.environment}-lambda-sg"
      Type = "Lambda"
    }
  )
}

# Security Group for OpenSearch Serverless
# Accepts connections from Lambda and Bedrock service
resource "aws_security_group" "opensearch" {
  name        = "${var.environment}-opensearch-sg"
  description = "Controls access to OpenSearch Serverless collection"
  vpc_id      = var.vpc_id

  # Inbound from Lambda Security Group
  ingress {
    description     = "HTTPS from Bedrock Lambda"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  # Inbound from VPC CIDR for Bedrock Service
  ingress {
    description = "HTTPS from Bedrock Service"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  # Inbound from peer VPC CIDR if peering is configured
  dynamic "ingress" {
    for_each = var.peer_vpc_cidr != "" ? [1] : []
    content {
      description = "HTTPS from peered VPC"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = [var.peer_vpc_cidr]
    }
  }

  # Outbound - allow all for AWS service communication
  egress {
    description = "Allow all outbound for AWS service communication"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.environment}-opensearch-sg"
      Type = "OpenSearch"
    }
  )
}

# Security Group for VPC Endpoints
# Accepts connections from VPC and peered VPC
resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.environment}-vpc-endpoints-sg"
  description = "Controls access to VPC Endpoints for AWS services"
  vpc_id      = var.vpc_id

  # Inbound from VPC CIDR
  ingress {
    description = "HTTPS from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  # Inbound from peer VPC CIDR if peering is configured
  dynamic "ingress" {
    for_each = var.peer_vpc_cidr != "" ? [1] : []
    content {
      description = "HTTPS from peered VPC"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = [var.peer_vpc_cidr]
    }
  }

  # Outbound - allow all for AWS service communication
  egress {
    description = "Allow all outbound for AWS service communication"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.environment}-vpc-endpoints-sg"
      Type = "VPCEndpoints"
    }
  )
}
