variable "vpc_id" {
  description = "ID of the VPC where security groups will be created"
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC for internal traffic rules"
  type        = string
  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "VPC CIDR must be a valid IPv4 CIDR block"
  }
}

variable "peer_vpc_cidr" {
  description = "CIDR block of the peered VPC for cross-region traffic rules"
  type        = string
  default     = ""
  validation {
    condition     = var.peer_vpc_cidr == "" || can(cidrhost(var.peer_vpc_cidr, 0))
    error_message = "Peer VPC CIDR must be a valid IPv4 CIDR block or empty string"
  }
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
}

variable "tags" {
  description = "Common tags to apply to all security group resources"
  type        = map(string)
  default     = {}
}
