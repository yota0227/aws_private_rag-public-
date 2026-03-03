# Bedrock RAG Module Variables

variable "knowledge_base_name" {
  description = "Name for Bedrock Knowledge Base"
  type        = string
}

variable "embedding_model_arn" {
  description = "ARN of embedding model (e.g., Titan Embeddings)"
  type        = string
  default     = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1"
}

variable "foundation_model_arn" {
  description = "ARN of foundation model for generation"
  type        = string
  default     = "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2"
}

variable "opensearch_collection_name" {
  description = "Name for OpenSearch Serverless collection"
  type        = string
}

variable "opensearch_index_name" {
  description = "Name for vector index"
  type        = string
  default     = "bedrock-knowledge-base-index"
}

variable "vector_dimension" {
  description = "Dimension of embedding vectors (1536 for Titan Embeddings)"
  type        = number
  default     = 1536
  validation {
    condition     = var.vector_dimension > 0 && var.vector_dimension <= 2048
    error_message = "Vector dimension must be between 1 and 2048"
  }
}

variable "opensearch_capacity_units" {
  description = "OCU capacity for OpenSearch Serverless (minimum 2 OCU per dimension)"
  type = object({
    search_ocu   = number
    indexing_ocu = number
  })
  default = {
    search_ocu   = 2
    indexing_ocu = 2
  }
  validation {
    condition     = var.opensearch_capacity_units.search_ocu >= 2 && var.opensearch_capacity_units.indexing_ocu >= 2
    error_message = "OpenSearch Serverless requires minimum 2 OCU for search and indexing"
  }
  validation {
    condition     = var.opensearch_capacity_units.search_ocu <= 40 && var.opensearch_capacity_units.indexing_ocu <= 40
    error_message = "OpenSearch Serverless maximum is 40 OCU per dimension"
  }
}

variable "s3_data_source_bucket_arn" {
  description = "ARN of S3 bucket containing documents"
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of KMS key for encryption"
  type        = string
}

variable "vpc_subnet_ids" {
  description = "Subnet IDs for VPC configuration"
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security group IDs for OpenSearch and Bedrock"
  type        = list(string)
}

variable "bedrock_execution_role_arn" {
  description = "ARN of IAM role for Bedrock Knowledge Base execution"
  type        = string
}

variable "opensearch_access_role_arn" {
  description = "ARN of IAM role for OpenSearch data access"
  type        = string
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "bos-ai-rag"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
