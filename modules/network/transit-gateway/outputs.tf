# Transit Gateway Module Outputs

output "transit_gateway_id" {
  description = "ID of the Transit Gateway"
  value       = aws_ec2_transit_gateway.main.id
}

output "transit_gateway_arn" {
  description = "ARN of the Transit Gateway"
  value       = aws_ec2_transit_gateway.main.arn
}

output "transit_gateway_owner_id" {
  description = "Owner ID of the Transit Gateway"
  value       = aws_ec2_transit_gateway.main.owner_id
}

output "transit_gateway_association_default_route_table_id" {
  description = "ID of the default association route table"
  value       = aws_ec2_transit_gateway.main.association_default_route_table_id
}

output "transit_gateway_propagation_default_route_table_id" {
  description = "ID of the default propagation route table"
  value       = aws_ec2_transit_gateway.main.propagation_default_route_table_id
}

output "vpc_attachment_ids" {
  description = "Map of VPC attachment IDs"
  value       = { for k, v in aws_ec2_transit_gateway_vpc_attachment.vpc_attachments : k => v.id }
}

output "custom_route_table_ids" {
  description = "Map of custom route table IDs"
  value       = { for k, v in aws_ec2_transit_gateway_route_table.custom : k => v.id }
}
