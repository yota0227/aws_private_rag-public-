output "network_acl_id" {
  description = "ID of the network ACL"
  value       = aws_network_acl.private.id
}

output "network_acl_arn" {
  description = "ARN of the network ACL"
  value       = aws_network_acl.private.arn
}
