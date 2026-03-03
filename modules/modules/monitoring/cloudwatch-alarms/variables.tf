variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "lambda_function_names" {
  description = "List of Lambda function names to create alarms for"
  type        = list(string)
  default     = []
}

variable "bedrock_kb_id" {
  description = "Bedrock Knowledge Base ID for alarms"
  type        = string
  default     = ""
}

variable "opensearch_collection_id" {
  description = "OpenSearch Serverless collection ID for alarms"
  type        = string
  default     = ""
}

variable "sns_topic_arn" {
  description = "ARN of SNS topic for alarm notifications"
  type        = string
}

variable "lambda_error_threshold" {
  description = "Threshold for Lambda error rate alarm (percentage)"
  type        = number
  default     = 5
}

variable "lambda_throttle_threshold" {
  description = "Threshold for Lambda throttle alarm (count)"
  type        = number
  default     = 10
}

variable "opensearch_capacity_threshold" {
  description = "Threshold for OpenSearch capacity utilization (percentage)"
  type        = number
  default     = 80
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
