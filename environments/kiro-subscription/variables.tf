# Variables for Kiro Subscription S3 Bucket
# Configuration for user prompt metadata storage

variable "aws_region" {
  description = "AWS region for Kiro subscription resources"
  type        = string
  default     = "us-east-1"

  validation {
    condition     = var.aws_region == "us-east-1"
    error_message = "Kiro subscription is currently only available in us-east-1 (Virginia)"
  }
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod"
  }
}

variable "bucket_name" {
  description = "Name of S3 bucket for Kiro user prompts"
  type        = string
  default     = "bos-ai-kiro-logs"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]*[a-z0-9]$", var.bucket_name))
    error_message = "Bucket name must be lowercase alphanumeric with hyphens, starting and ending with alphanumeric"
  }
}

variable "log_retention_days" {
  description = "Number of days to retain access logs"
  type        = number
  default     = 90

  validation {
    condition     = var.log_retention_days > 0 && var.log_retention_days <= 3653
    error_message = "Log retention days must be between 1 and 3653"
  }
}

variable "enable_versioning" {
  description = "Enable S3 bucket versioning for audit trail"
  type        = bool
  default     = true
}

variable "enable_mfa_delete" {
  description = "Enable MFA delete protection"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}
