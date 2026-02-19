# Variables for Global Backend Infrastructure

variable "region" {
  description = "AWS region for backend resources (Seoul region for centralized state management)"
  type        = string
  default     = "ap-northeast-2"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]{1}$", var.region))
    error_message = "Region must be a valid AWS region format (e.g., ap-northeast-2)"
  }
}

variable "state_bucket_name" {
  description = "Name of S3 bucket for Terraform state storage"
  type        = string
  default     = "bos-ai-terraform-state"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "Bucket name must be valid S3 bucket name (lowercase, alphanumeric, hyphens)"
  }
}

variable "dynamodb_table_name" {
  description = "Name of DynamoDB table for state locking"
  type        = string
  default     = "terraform-state-lock"

  validation {
    condition     = can(regex("^[a-zA-Z0-9_.-]{3,255}$", var.dynamodb_table_name))
    error_message = "DynamoDB table name must be 3-255 characters (alphanumeric, underscore, dot, hyphen)"
  }
}

variable "authorized_principals" {
  description = "List of IAM principal ARNs authorized to access the state bucket"
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.authorized_principals) == 0 || alltrue([for arn in var.authorized_principals : can(regex("^arn:aws:iam::[0-9]{12}:(user|role)/", arn))])
    error_message = "All principals must be valid IAM user or role ARNs"
  }
}
