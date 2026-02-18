output "peering_connection_id" {
  description = "ID of VPC peering connection"
  value       = aws_vpc_peering_connection.main.id
}

output "peering_status" {
  description = "Status of peering connection"
  value       = aws_vpc_peering_connection.main.accept_status
}
