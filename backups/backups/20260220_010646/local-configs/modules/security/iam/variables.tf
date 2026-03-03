variable "s3_data_source_bucket_arn" {
  description = "ARN of S3 bucket containing documents for Bedrock Knowledge Base"
  type        = string
}

variable "opensearch_collection_arn" {
  description = "ARN of OpenSearch Serverless collection"
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of KMS key for encryption/decryption"
  type        = string
}

variable "bedrock_model_arns" {
  description = "List of Bedrock model ARNs that the Knowledge Base can invoke"
  type        = list(string)
  default = [
    "arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v1",
    "arn:aws:bedrock:*::foundation-model/anthropic.claude-v2"
  ]
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
  description = "Common tags for all IAM resources"
  type        = map(string)
  default     = {}
}
