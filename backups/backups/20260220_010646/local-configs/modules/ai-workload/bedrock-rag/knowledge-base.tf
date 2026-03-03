# Bedrock Knowledge Base Configuration
# Creates Bedrock Knowledge Base with S3 data source and OpenSearch vector store

# Bedrock Knowledge Base
resource "aws_bedrockagent_knowledge_base" "main" {
  name        = var.knowledge_base_name
  description = "Knowledge Base for ${var.project_name} RAG system"
  role_arn    = var.bedrock_execution_role_arn

  knowledge_base_configuration {
    type = "VECTOR"
    
    vector_knowledge_base_configuration {
      embedding_model_arn = var.embedding_model_arn
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.main.arn
      vector_index_name = var.opensearch_index_name
      
      field_mapping {
        vector_field   = "bedrock-knowledge-base-default-vector"
        text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
        metadata_field = "AMAZON_BEDROCK_METADATA"
      }
    }
  }

  depends_on = [
    aws_opensearchserverless_collection.main,
    aws_opensearchserverless_access_policy.data_access,
    time_sleep.wait_for_collection
  ]

  tags = merge(
    var.tags,
    {
      Name = var.knowledge_base_name
    }
  )
}

# Bedrock Data Source (S3)
resource "aws_bedrockagent_data_source" "s3" {
  name              = "${var.knowledge_base_name}-s3-source"
  description       = "S3 data source for ${var.knowledge_base_name}"
  knowledge_base_id = aws_bedrockagent_knowledge_base.main.id

  data_source_configuration {
    type = "S3"
    
    s3_configuration {
      bucket_arn = var.s3_data_source_bucket_arn
      
      # Optional: Include/exclude patterns
      # inclusion_prefixes = ["documents/"]
    }
  }

  # Optional: Configure chunking strategy
  # Bedrock can handle chunking automatically, but we can customize it
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

# Wait for data source to be ready
resource "time_sleep" "wait_for_data_source" {
  depends_on = [aws_bedrockagent_data_source.s3]
  
  create_duration = "30s"
}

# CloudWatch Log Group for Bedrock API Calls
resource "aws_cloudwatch_log_group" "bedrock_api" {
  name              = "/aws/bedrock/api/${var.knowledge_base_name}"
  retention_in_days = 7
  kms_key_id        = var.kms_key_arn

  tags = merge(
    var.tags,
    {
      Name = "${var.knowledge_base_name}-api-logs"
    }
  )
}

# CloudWatch Log Group for Bedrock Data Source Ingestion
resource "aws_cloudwatch_log_group" "bedrock_ingestion" {
  name              = "/aws/bedrock/datasource/${var.knowledge_base_name}"
  retention_in_days = 7
  kms_key_id        = var.kms_key_arn

  tags = merge(
    var.tags,
    {
      Name = "${var.knowledge_base_name}-ingestion-logs"
    }
  )
}
