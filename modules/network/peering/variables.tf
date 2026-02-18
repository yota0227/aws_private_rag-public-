variable "vpc_id" {
  description = "Requester VPC ID"
  type        = string
}

variable "peer_vpc_id" {
  description = "Accepter VPC ID"
  type        = string
}

variable "peer_region" {
  description = "Accepter VPC region"
  type        = string
}

variable "auto_accept" {
  description = "Automatically accept peering (same account)"
  type        = bool
  default     = true
}

variable "requester_route_table_ids" {
  description = "Route table IDs in requester VPC"
  type        = list(string)
}

variable "accepter_route_table_ids" {
  description = "Route table IDs in accepter VPC"
  type        = list(string)
}

variable "peer_cidr" {
  description = "CIDR block of peer VPC"
  type        = string
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
