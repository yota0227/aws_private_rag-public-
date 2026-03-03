variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "budget_name" {
  description = "Name for the AWS Budget"
  type        = string
}

variable "budget_limit_amount" {
  description = "Budget limit amount in USD"
  type        = number
  validation {
    condition     = var.budget_limit_amount > 0
    error_message = "Budget limit amount must be greater than 0"
  }
}

variable "budget_time_unit" {
  description = "Time unit for the budget (MONTHLY, QUARTERLY, ANNUALLY)"
  type        = string
  default     = "MONTHLY"
  validation {
    condition     = contains(["MONTHLY", "QUARTERLY", "ANNUALLY"], var.budget_time_unit)
    error_message = "Budget time unit must be MONTHLY, QUARTERLY, or ANNUALLY"
  }
}

variable "notification_emails" {
  description = "List of email addresses to receive budget notifications"
  type        = list(string)
  validation {
    condition     = length(var.notification_emails) > 0
    error_message = "At least one notification email must be provided"
  }
}

variable "alert_thresholds" {
  description = "List of threshold percentages for budget alerts (e.g., [80, 100])"
  type        = list(number)
  default     = [80, 100]
  validation {
    condition     = alltrue([for t in var.alert_thresholds : t > 0 && t <= 100])
    error_message = "Alert thresholds must be between 0 and 100"
  }
}

variable "cost_filters" {
  description = "Cost filters for the budget (e.g., by service, tag)"
  type        = map(list(string))
  default     = {}
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
