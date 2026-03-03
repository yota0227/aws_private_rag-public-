# KMS Module Outputs
# Requirements: 12.4

output "key_id" {
  description = "ID of the KMS key"
  value       = aws_kms_key.main.key_id
}

output "key_arn" {
  description = "ARN of the KMS key"
  value       = aws_kms_key.main.arn
}

output "key_alias_name" {
  description = "Alias name of the KMS key"
  value       = aws_kms_alias.main.name
}

output "key_alias_arn" {
  description = "ARN of the KMS key alias"
  value       = aws_kms_alias.main.arn
}

output "key_policy" {
  description = "Policy document for the KMS key"
  value       = data.aws_iam_policy_document.kms_key_policy.json
  sensitive   = true
}
