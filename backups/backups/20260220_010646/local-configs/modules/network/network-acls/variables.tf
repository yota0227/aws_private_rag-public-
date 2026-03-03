variable "vpc_id" {
  description = "VPC ID to create network ACLs for"
  type        = string
}

variable "vpc_name" {
  description = "VPC name for resource naming"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs to associate with network ACL"
  type        = list(string)
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC"
  type        = string
}

variable "peer_vpc_cidr" {
  description = "CIDR block of peered VPC (if any)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
