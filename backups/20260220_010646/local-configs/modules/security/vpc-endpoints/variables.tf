variable "vpc_id" {
  description = "ID of the VPC where endpoints will be created"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for interface endpoints"
  type        = list(string)
}

variable "security_group_ids" {
  description = "List of security group IDs to attach to interface endpoints"
  type        = list(string)
}

variable "region" {
  description = "AWS region for endpoint service names"
  type        = string
}

variable "enable_bedrock_runtime_endpoint" {
  description = "Enable Bedrock Runtime VPC endpoint"
  type        = bool
  default     = true
}

variable "enable_bedrock_agent_runtime_endpoint" {
  description = "Enable Bedrock Agent Runtime VPC endpoint"
  type        = bool
  default     = true
}

variable "enable_s3_endpoint" {
  description = "Enable S3 Gateway endpoint"
  type        = bool
  default     = true
}

variable "enable_opensearch_endpoint" {
  description = "Enable OpenSearch Serverless VPC endpoint"
  type        = bool
  default     = true
}

variable "route_table_ids" {
  description = "List of route table IDs for S3 Gateway endpoint"
  type        = list(string)
  default     = []
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
  description = "Common tags for all VPC endpoint resources"
  type        = map(string)
  default     = {}
}
