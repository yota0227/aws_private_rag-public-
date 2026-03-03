variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "region" {
  description = "AWS region for the dashboard"
  type        = string
}

variable "lambda_function_names" {
  description = "List of Lambda function names to include in dashboard"
  type        = list(string)
  default     = []
}

variable "bedrock_kb_id" {
  description = "Bedrock Knowledge Base ID for dashboard"
  type        = string
  default     = ""
}

variable "opensearch_collection_id" {
  description = "OpenSearch Serverless collection ID for dashboard"
  type        = string
  default     = ""
}

variable "vpc_ids" {
  description = "List of VPC IDs to include in dashboard"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
