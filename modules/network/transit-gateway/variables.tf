# Transit Gateway Module Variables

variable "tgw_name" {
  description = "Name of the Transit Gateway"
  type        = string
}

variable "description" {
  description = "Description of the Transit Gateway"
  type        = string
  default     = "Transit Gateway for VPC and VPN connectivity"
}

variable "amazon_side_asn" {
  description = "Private Autonomous System Number (ASN) for the Amazon side of a BGP session"
  type        = number
  default     = 64512
}

variable "default_route_table_association" {
  description = "Whether resource attachments are automatically associated with the default association route table"
  type        = string
  default     = "enable"
}

variable "default_route_table_propagation" {
  description = "Whether resource attachments automatically propagate routes to the default propagation route table"
  type        = string
  default     = "enable"
}

variable "dns_support" {
  description = "Whether DNS support is enabled"
  type        = string
  default     = "enable"
}

variable "vpn_ecmp_support" {
  description = "Whether VPN Equal Cost Multipath Protocol support is enabled"
  type        = string
  default     = "enable"
}

variable "auto_accept_shared_attachments" {
  description = "Whether resource attachment requests are automatically accepted"
  type        = string
  default     = "disable"
}

variable "vpc_attachments" {
  description = "Map of VPC attachments to create"
  type = map(object({
    vpc_id                                          = string
    subnet_ids                                      = list(string)
    dns_support                                     = optional(string, "enable")
    ipv6_support                                    = optional(string, "disable")
    appliance_mode_support                          = optional(string, "disable")
    transit_gateway_default_route_table_association = optional(bool, true)
    transit_gateway_default_route_table_propagation = optional(bool, true)
    tags                                            = optional(map(string), {})
  }))
  default = {}
}

variable "vpn_connection_id" {
  description = "VPN Connection ID to attach to TGW (optional)"
  type        = string
  default     = null
}

variable "vpn_vpc_id" {
  description = "VPC ID for VPN attachment (required if vpn_connection_id is set)"
  type        = string
  default     = null
}

variable "vpn_subnet_ids" {
  description = "Subnet IDs for VPN attachment (required if vpn_connection_id is set)"
  type        = list(string)
  default     = []
}

variable "custom_route_tables" {
  description = "Map of custom route tables to create"
  type        = map(object({}))
  default     = {}
}

variable "static_routes" {
  description = "Map of static routes to create"
  type = map(object({
    destination_cidr_block = string
    attachment_id          = optional(string)
    route_table_id         = string
    blackhole              = optional(bool, false)
  }))
  default = {}
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
