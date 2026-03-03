# Bedrock Knowledge Base Configuration for Seoul Consolidated VPC
# Creates Bedrock Knowledge Base with VPC connectivity to OpenSearch Serverless
# Requirements: 3.4, NFR-1, NFR-2

# Security Group for Bedrock Knowledge Base
resource "aws_security_group" "bedrock_kb" {
  name        = "bedrock-kb-bos-ai-seoul-prod"
  description = "Security group for Bedrock Knowledge Base"
  vpc_id      = "vpc-066c464f9c750ee9e"  # Seoul consolidated VPC

  # No inbound rules needed for Bedrock KB

  # Outbound Rules
  # Allow HTTPS to OpenSearch
  egress {
    description     = "HTTPS to OpenSearch Serverless"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.opensearch.id]
  }

  # Allow HTTPS to VPC Endpoints
  egress {
    description = "HTTPS to VPC Endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.200.0.0/16"]
  }

  # Allow all outbound for AWS service access
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "bedrock-kb-bos-ai-seoul-prod"
    Project     = "BOS-AI"
    Environment = "Production"
    ManagedBy   = "Terraform"
    Layer       = "Security"
  }
}

# IAM Role for Bedrock Knowledge Base
resource "aws_iam_role" "bedrock_kb" {
  name        = "role-bedrock-kb-seoul-prod"
  description = "IAM role for Bedrock Knowledge Base"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = "533335672315"
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:bedrock:ap-northeast-2:533335672315:knowledge-base/*"
          }
        }
      }
    ]
  })

  tags = {
    Name        = "role-bedrock-kb-seoul-prod"
    Project     = "BOS-AI"
    Environment = "Production"
    ManagedBy   = "Terraform"
    Layer       = "Security"
  }
}

# IAM Policy for Bedrock KB - S3 Access
resource "aws_iam_role_policy" "bedrock_kb_s3" {
  name = "bedrock-kb-s3-access"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::bos-ai-documents-*",
          "arn:aws:s3:::bos-ai-documents-*/*"
        ]
      }
    ]
  })
}

# IAM Policy for Bedrock KB - OpenSearch Serverless Access
resource "aws_iam_role_policy" "bedrock_kb_opensearch" {
  name = "bedrock-kb-opensearch-access"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "aoss:APIAccessAll"
        ]
        Resource = [
          "arn:aws:aoss:ap-northeast-2:533335672315:collection/*"
        ]
      }
    ]
  })
}

# IAM Policy for Bedrock KB - Bedrock Model Access
resource "aws_iam_role_policy" "bedrock_kb_bedrock" {
  name = "bedrock-kb-bedrock-access"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = [
          "arn:aws:bedrock:ap-northeast-2::foundation-model/amazon.titan-embed-text-v1"
        ]
      }
    ]
  })
}

# Bedrock Knowledge Base
resource "aws_bedrockagent_knowledge_base" "main" {
  name        = "bos-ai-kb-seoul-prod"
  description = "BOS-AI Knowledge Base for RAG system in Seoul VPC"
  role_arn    = aws_iam_role.bedrock_kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:ap-northeast-2::foundation-model/amazon.titan-embed-text-v1"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.main.arn
      vector_index_name = "bos-ai-documents"
      field_mapping {
        vector_field   = "bedrock-knowledge-base-default-vector"
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }

  tags = {
    Name        = "bos-ai-kb-seoul-prod"
    Project     = "BOS-AI"
    Environment = "Production"
    ManagedBy   = "Terraform"
    Layer       = "Data"
  }

  depends_on = [
    aws_iam_role_policy.bedrock_kb_s3,
    aws_iam_role_policy.bedrock_kb_opensearch,
    aws_iam_role_policy.bedrock_kb_bedrock,
    aws_opensearchserverless_collection.main,
    aws_opensearchserverless_access_policy.data_access
  ]
}

# Bedrock Knowledge Base Data Source - Virginia S3 Bucket
resource "aws_bedrockagent_data_source" "virginia_s3" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.main.id
  name              = "bos-ai-documents-virginia"
  description       = "S3 data source from Virginia region"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = "arn:aws:s3:::bos-ai-documents-us"
      inclusion_prefixes = [
        "documents/"
      ]
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 300
        overlap_percentage = 20
      }
    }
  }
}

# Bedrock Knowledge Base Data Source - Seoul S3 Bucket (Optional)
resource "aws_bedrockagent_data_source" "seoul_s3" {
  count = var.enable_seoul_data_source ? 1 : 0

  knowledge_base_id = aws_bedrockagent_knowledge_base.main.id
  name              = "bos-ai-documents-seoul"
  description       = "S3 data source from Seoul region"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = "arn:aws:s3:::bos-ai-documents-seoul"
      inclusion_prefixes = [
        "documents/"
      ]
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 300
        overlap_percentage = 20
      }
    }
  }
}

# CloudWatch Log Group for Bedrock KB
resource "aws_cloudwatch_log_group" "bedrock_kb" {
  name              = "/aws/bedrock/knowledge-base/bos-ai-kb-seoul-prod"
  retention_in_days = 30

  tags = {
    Name        = "bos-ai-kb-seoul-prod-logs"
    Project     = "BOS-AI"
    Environment = "Production"
    ManagedBy   = "Terraform"
  }
}

# Variables
variable "enable_seoul_data_source" {
  description = "Enable Seoul S3 bucket as data source"
  type        = bool
  default     = false
}

# Outputs
output "bedrock_kb_id" {
  description = "Bedrock Knowledge Base ID"
  value       = aws_bedrockagent_knowledge_base.main.id
}

output "bedrock_kb_arn" {
  description = "Bedrock Knowledge Base ARN"
  value       = aws_bedrockagent_knowledge_base.main.arn
}

# Outputs moved to outputs.tf to avoid duplication

# Note: After deployment:
# 1. Verify OpenSearch index exists (bos-ai-documents)
# 2. Start data source synchronization
# 3. Test knowledge base queries
# 4. Monitor CloudWatch logs for errors
