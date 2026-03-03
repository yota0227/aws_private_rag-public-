variable "source_bucket_name" {
  description = "Name for source S3 bucket (Seoul region)"
  type        = string
}

variable "destination_bucket_name" {
  description = "Name for destination S3 bucket (US region)"
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of KMS key for S3 encryption"
  type        = string
}

variable "enable_versioning" {
  description = "Enable S3 versioning"
  type        = bool
  default     = true
}

variable "enable_replication" {
  description = "Enable cross-region replication"
  type        = bool
  default     = true
}

variable "replication_role_arn" {
  description = "ARN of IAM role for S3 replication (optional, will be created if not provided)"
  type        = string
  default     = ""
}

variable "lifecycle_glacier_transition_days" {
  description = "Number of days before transitioning objects to Glacier"
  type        = number
  default     = 90
  validation {
    condition     = var.lifecycle_glacier_transition_days >= 30
    error_message = "Glacier transition must be at least 30 days"
  }
}

variable "lifecycle_deep_archive_transition_days" {
  description = "Number of days before transitioning objects to Glacier Deep Archive"
  type        = number
  default     = 180
  validation {
    condition     = var.lifecycle_deep_archive_transition_days >= 90
    error_message = "Deep Archive transition must be at least 90 days"
  }
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

variable "source_region" {
  description = "Source region for S3 bucket (Seoul)"
  type        = string
  default     = "ap-northeast-2"
}

variable "destination_region" {
  description = "Destination region for S3 bucket (US)"
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Common tags for all S3 resources"
  type        = map(string)
  default     = {}
}

# Lambda Configuration Variables
variable "lambda_function_name" {
  description = "Name for document processor Lambda function"
  type        = string
}

variable "lambda_runtime" {
  description = "Lambda runtime version"
  type        = string
  default     = "python3.11"
}

variable "lambda_memory_size" {
  description = "Lambda memory allocation in MB (minimum 1024 MB for document processing)"
  type        = number
  default     = 1024
  validation {
    condition     = var.lambda_memory_size >= 1024
    error_message = "Lambda memory must be at least 1024 MB for document processing"
  }
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds (minimum 300 seconds for complex document processing)"
  type        = number
  default     = 300
  validation {
    condition     = var.lambda_timeout >= 300
    error_message = "Lambda timeout must be at least 300 seconds (5 minutes)"
  }
}

variable "lambda_vpc_config" {
  description = "VPC configuration for Lambda function"
  type = object({
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
}

variable "lambda_execution_role_arn" {
  description = "ARN of IAM role for Lambda execution"
  type        = string
}

variable "lambda_environment_variables" {
  description = "Environment variables for Lambda function"
  type        = map(string)
  default     = {}
}

variable "lambda_log_retention_days" {
  description = "CloudWatch log retention period in days"
  type        = number
  default     = 7
}
