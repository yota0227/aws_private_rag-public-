# Variables for Network Layer
# Environment-specific configuration for VPC, peering, and security groups
#
# Requirements: 1.1, 1.2, 12.1, 12.2

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod"
  }
}

# Seoul VPC Configuration
variable "seoul_vpc_cidr" {
  description = "CIDR block for Seoul VPC"
  type        = string
  default     = "10.10.0.0/16"

  validation {
    condition     = can(cidrhost(var.seoul_vpc_cidr, 0))
    error_message = "Seoul VPC CIDR must be a valid IPv4 CIDR block"
  }
}

variable "seoul_availability_zones" {
  description = "Availability zones for Seoul region"
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]

  validation {
    condition     = length(var.seoul_availability_zones) >= 2
    error_message = "At least 2 availability zones are required"
  }
}

variable "seoul_private_subnet_cidrs" {
  description = "CIDR blocks for Seoul private subnets"
  type        = list(string)
  default     = ["10.10.1.0/24", "10.10.2.0/24"]

  validation {
    condition     = length(var.seoul_private_subnet_cidrs) >= 2
    error_message = "At least 2 private subnets are required"
  }
}

# US VPC Configuration
variable "us_vpc_cidr" {
  description = "CIDR block for US VPC"
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrhost(var.us_vpc_cidr, 0))
    error_message = "US VPC CIDR must be a valid IPv4 CIDR block"
  }
}

variable "us_availability_zones" {
  description = "Availability zones for US East region"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]

  validation {
    condition     = length(var.us_availability_zones) >= 2
    error_message = "At least 2 availability zones are required"
  }
}

variable "us_private_subnet_cidrs" {
  description = "CIDR blocks for US private subnets"
  type        = list(string)
  default     = ["10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"]

  validation {
    condition     = length(var.us_private_subnet_cidrs) >= 2
    error_message = "At least 2 private subnets are required"
  }
}

# Common Tags
variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
