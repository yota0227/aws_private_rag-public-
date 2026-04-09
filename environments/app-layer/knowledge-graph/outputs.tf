# Outputs for App Layer - Knowledge Graph (Neptune)
# Requirements: 16.4, 16.5, 16.15

output "neptune_cluster_endpoint" {
  description = "Neptune 클러스터 Writer 엔드포인트"
  value       = module.neptune.neptune_cluster_endpoint
}

output "neptune_cluster_reader_endpoint" {
  description = "Neptune 클러스터 Reader 엔드포인트"
  value       = module.neptune.neptune_cluster_reader_endpoint
}

output "neptune_readonly_role_arn" {
  description = "Neptune Read-Only IAM Role ARN (Lambda Handler용)"
  value       = aws_iam_role.neptune_readonly.arn
}

output "neptune_security_group_id" {
  description = "Neptune 전용 Security Group ID"
  value       = module.neptune.neptune_security_group_id
}
