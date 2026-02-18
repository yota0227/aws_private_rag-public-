# KMS Module Variables
# Requirements: 5.4, 5.5, 5.6

variable "key_description" {
  description = "Description for the KMS key"
  type        = string
  default     = "KMS key for BOS AI RAG infrastructure encryption"
}

variable "deletion_window_in_days" {
  description = "Duration in days after which the key is deleted after destruction"
  type        = number
  default     = 30

  validation {
    condition     = var.deletion_window_in_days >= 7 && var.deletion_window_in_days <= 30
    error_message = "Deletion window must be between 7 and 30 days"
  }
}

variable "enable_key_rotation" {
  description = "Enable automatic key rotation"
  type        = bool
  default     = true
}

variable "key_usage" {
  description = "Intended use of the key (ENCRYPT_DECRYPT or SIGN_VERIFY)"
  type        = string
  default     = "ENCRYPT_DECRYPT"

  validation {
    condition     = contains(["ENCRYPT_DECRYPT", "SIGN_VERIFY"], var.key_usage)
    error_message = "Key usage must be either ENCRYPT_DECRYPT or SIGN_VERIFY"
  }
}

variable "customer_master_key_spec" {
  description = "Specification of the key material"
  type        = string
  default     = "SYMMETRIC_DEFAULT"

  validation {
    condition = contains([
      "SYMMETRIC_DEFAULT",
      "RSA_2048",
      "RSA_3072",
      "RSA_4096",
      "ECC_NIST_P256",
      "ECC_NIST_P384",
      "ECC_NIST_P521",
      "ECC_SECG_P256K1"
    ], var.customer_master_key_spec)
    error_message = "Invalid customer master key spec"
  }
}

variable "enable_bedrock_access" {
  description = "Grant Bedrock service principal access to the key"
  type        = bool
  default     = true
}

variable "enable_s3_access" {
  description = "Grant S3 service principal access to the key"
  type        = bool
  default     = true
}

variable "enable_opensearch_access" {
  description = "Grant OpenSearch Serverless service principal access to the key"
  type        = bool
  default     = true
}

variable "enable_lambda_access" {
  description = "Grant Lambda service principal access to the key"
  type        = bool
  default     = false
}

variable "enable_cloudwatch_logs_access" {
  description = "Grant CloudWatch Logs service principal access to the key"
  type        = bool
  default     = false
}

variable "additional_key_admins" {
  description = "List of IAM ARNs that can administer the key"
  type        = list(string)
  default     = []
}

variable "additional_key_users" {
  description = "List of IAM ARNs that can use the key"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to the KMS key"
  type        = map(string)
  default     = {}
}

variable "region" {
  description = "AWS region for the KMS key (used in key policy conditions)"
  type        = string
}
