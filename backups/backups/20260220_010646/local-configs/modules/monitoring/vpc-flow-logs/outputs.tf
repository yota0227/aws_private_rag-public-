output "flow_log_id" {
  description = "ID of the VPC Flow Log"
  value       = aws_flow_log.main.id
}

output "flow_log_arn" {
  description = "ARN of the VPC Flow Log"
  value       = aws_flow_log.main.arn
}
