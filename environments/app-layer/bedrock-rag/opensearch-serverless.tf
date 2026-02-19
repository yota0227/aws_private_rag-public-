# OpenSearch Serverless Configuration for Seoul Consolidated VPC
# Creates OpenSearch Serverless collection with VPC endpoint for private access
# Requirements: 3.2, NFR-1, NFR-2

# Security Group for OpenSearch Serverless
resource "aws_security_group" "opensearch" {
  provider    = aws.seoul
  name        = "opensearch-bos-ai-seoul-prod"
  description = "Security group for OpenSearch Serverless collection"
  vpc_id      = "vpc-066c464f9c750ee9e"  # Seoul consolidated VPC

  # Inbound Rules
  # Note: Lambda and Bedrock KB security group rules will be added after those SGs are created
  
  # Allow HTTPS from on-premises networks
  ingress {
    description = "HTTPS from on-premises"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["192.128.0.0/16"]
  }

  # Allow HTTPS from Virginia VPC (via peering)
  ingress {
    description = "HTTPS from Virginia VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.20.0.0/16"]
  }

  # Outbound Rules
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "opensearch-bos-ai-seoul-prod"
    Project     = "BOS-AI"
    Environment = "Production"
    ManagedBy   = "Terraform"
    Layer       = "Security"
  }
}

# OpenSearch Serverless Encryption Policy
resource "aws_opensearchserverless_security_policy" "encryption" {
  provider    = aws.seoul
  name        = "bos-ai-vectors-encrypt"
  type        = "encryption"
  description = "Encryption policy for BOS-AI RAG vector collection"

  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource = [
          "collection/bos-ai-vectors-prod"
        ]
      }
    ]
    AWSOwnedKey = true  # Using AWS managed key for simplicity
  })
}

# OpenSearch Serverless Network Policy
# This policy restricts access to VPC endpoints only
resource "aws_opensearchserverless_security_policy" "network" {
  provider    = aws.seoul
  name        = "bos-ai-vectors-network"
  type        = "network"
  description = "Network policy for BOS-AI RAG vector collection - VPC access only"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource = [
            "collection/bos-ai-vectors-prod"
          ]
        },
        {
          ResourceType = "dashboard"
          Resource = [
            "collection/bos-ai-vectors-prod"
          ]
        }
      ]
      AllowFromPublic = false
      SourceVPCEs = [
        aws_opensearchserverless_vpc_endpoint.main.id
      ]
    }
  ])

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_vpc_endpoint.main
  ]
}

# OpenSearch Serverless Collection
resource "aws_opensearchserverless_collection" "main" {
  provider    = aws.seoul
  name        = "bos-ai-vectors-prod"
  type        = "VECTORSEARCH"
  description = "Vector search collection for BOS-AI RAG system in Seoul VPC"

  standby_replicas = "ENABLED"  # Enable standby replicas for high availability

  depends_on = [
    aws_opensearchserverless_security_policy.encryption
  ]

  tags = {
    Name               = "bos-ai-rag-vectors-prod"
    Project            = "BOS-AI"
    Environment        = "Production"
    ManagedBy          = "Terraform"
    Layer              = "Data"
    DataClassification = "Internal"
    Backup             = "true"
  }
}

# OpenSearch Serverless VPC Endpoint
resource "aws_opensearchserverless_vpc_endpoint" "main" {
  provider           = aws.seoul
  name               = "vpce-opensearch-seoul-prod"
  vpc_id             = "vpc-066c464f9c750ee9e"
  subnet_ids         = ["subnet-0f027e9de8e26c18f", "subnet-0625d992edf151017"]  # Replace with actual subnet IDs
  security_group_ids = [aws_security_group.opensearch.id]

  depends_on = [aws_opensearchserverless_collection.main]
}

# OpenSearch Serverless Data Access Policy
# Grants access to Lambda and Bedrock KB roles
resource "aws_opensearchserverless_access_policy" "data_access" {
  provider    = aws.seoul
  name        = "bos-ai-vectors-data-access"
  type        = "data"
  description = "Data access policy for BOS-AI RAG vector collection"

  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource = [
            "collection/bos-ai-rag-vectors-prod"
          ]
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems"
          ]
        },
        {
          ResourceType = "index"
          Resource = [
            "index/bos-ai-rag-vectors-prod/*"
          ]
          Permission = [
            "aoss:CreateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument",
            "aoss:UpdateIndex",
            "aoss:DeleteIndex"
          ]
        }
      ]
      Principal = [
        "arn:aws:iam::533335672315:role/role-lambda-document-processor-seoul-prod",
        "arn:aws:iam::533335672315:role/role-bedrock-kb-seoul-prod"
      ]
    }
  ])

  depends_on = [aws_opensearchserverless_collection.main]
}

# CloudWatch Log Group for OpenSearch
resource "aws_cloudwatch_log_group" "opensearch" {
  name              = "/aws/opensearch/bos-ai-rag-vectors-prod"
  retention_in_days = 30

  tags = {
    Name        = "bos-ai-rag-vectors-prod-logs"
    Project     = "BOS-AI"
    Environment = "Production"
    ManagedBy   = "Terraform"
  }
}

# Outputs moved to outputs.tf to avoid duplication

output "opensearch_vpc_endpoint_id" {
  description = "OpenSearch Serverless VPC endpoint ID"
  value       = aws_opensearchserverless_vpc_endpoint.main.id
}

output "opensearch_security_group_id" {
  description = "OpenSearch security group ID"
  value       = aws_security_group.opensearch.id
}

# Note: After creating the collection, you need to create the vector index
# Use the script: scripts/create-opensearch-index.py
# Or manually create the index with the mapping from modules/ai-workload/bedrock-rag/opensearch_index_mapping.json
