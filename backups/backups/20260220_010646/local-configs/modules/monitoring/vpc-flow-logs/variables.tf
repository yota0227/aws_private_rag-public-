variable "vpc_id" {
  description = "VPC ID to enable flow logs for"
  type        = string
}

variable "vpc_name" {
  description = "VPC name for resource naming"
  type        = string
}

variable "log_destination_type" {
  description = "Type of log destination (cloud-watch-logs or s3)"
  type        = string
  default     = "cloud-watch-logs"
  validation {
    condition     = contains(["cloud-watch-logs", "s3"], var.log_destination_type)
    error_message = "Log destination type must be either 'cloud-watch-logs' or 's3'"
  }
}

variable "cloudwatch_log_group_arn" {
  description = "ARN of CloudWatch log group for flow logs"
  type        = string
}

variable "iam_role_arn" {
  description = "ARN of IAM role for VPC Flow Logs to write to CloudWatch"
  type        = string
}

variable "traffic_type" {
  description = "Type of traffic to log (ACCEPT, REJECT, or ALL)"
  type        = string
  default     = "ALL"
  validation {
    condition     = contains(["ACCEPT", "REJECT", "ALL"], var.traffic_type)
    error_message = "Traffic type must be ACCEPT, REJECT, or ALL"
  }
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
