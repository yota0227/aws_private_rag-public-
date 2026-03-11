# Variables for App Layer - Bedrock RAG
# Requirements: 12.3

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "bos-ai"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "us_region" {
  description = "AWS region for US resources (AI workload)"
  type        = string
  default     = "us-east-1"
}

# Bedrock Configuration
variable "knowledge_base_name" {
  description = "Name for Bedrock Knowledge Base"
  type        = string
  default     = "bos-ai-knowledge-base"
}

variable "embedding_model_arn" {
  description = "ARN of embedding model (Titan Embeddings)"
  type        = string
  default     = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1"
}

variable "foundation_model_arn" {
  description = "ARN of foundation model for generation (Claude 3.5 Haiku via US inference profile)"
  type        = string
  default     = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
}

# OpenSearch Configuration
variable "opensearch_collection_name" {
  description = "Name for OpenSearch Serverless collection"
  type        = string
  default     = "bos-ai-vectors"
}

variable "opensearch_index_name" {
  description = "Name for vector index"
  type        = string
  default     = "bedrock-knowledge-base-index"
}

variable "vector_dimension" {
  description = "Dimension of embedding vectors (Titan: 1536)"
  type        = number
  default     = 1536
}

variable "opensearch_capacity_units" {
  description = "OCU capacity for OpenSearch Serverless"
  type = object({
    search_ocu   = number
    indexing_ocu = number
  })
  default = {
    search_ocu   = 2
    indexing_ocu = 2
  }
}

# S3 Configuration
variable "source_bucket_name" {
  description = "Name for source S3 bucket (Seoul)"
  type        = string
  default     = "bos-ai-documents-seoul"
}

variable "destination_bucket_name" {
  description = "Name for destination S3 bucket (US)"
  type        = string
  default     = "bos-ai-documents-us"
}

# Lambda Configuration
variable "lambda_function_name" {
  description = "Name for document processor Lambda"
  type        = string
  default     = "document-processor"
}

variable "lambda_runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "python3.11"
}

variable "lambda_memory_size" {
  description = "Lambda memory in MB"
  type        = number
  default     = 1024
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 300
}

# Monitoring Configuration
variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 30
}

variable "sns_notification_emails" {
  description = "List of email addresses for alarm notifications"
  type        = list(string)
  default     = []
}

# Budget Configuration
variable "monthly_budget_amount" {
  description = "Monthly budget limit in USD"
  type        = number
  default     = 1000
}

variable "budget_alert_thresholds" {
  description = "Budget alert thresholds (percentages)"
  type        = list(number)
  default     = [80, 100]
}

# CloudTrail Configuration
variable "cloudtrail_bucket_name" {
  description = "Name for CloudTrail S3 bucket"
  type        = string
  default     = "bos-ai-cloudtrail-logs"
}

# ACM Certificate for Private API Gateway Custom Domain
variable "acm_certificate_arn" {
  description = "ACM certificate ARN for rag.corp.bos-semi.com (Private CA or Regional)"
  type        = string
  default     = ""  # Must be set before deployment
}

# Bedrock KB Data Source ID (for sync after upload)
variable "bedrock_kb_data_source_id" {
  description = "Bedrock Knowledge Base Data Source ID for triggering sync"
  type        = string
  default     = ""  # Set after KB data source is created
}
