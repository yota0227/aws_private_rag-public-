output "sns_topic_arn" {
  description = "ARN of SNS topic for alarm notifications"
  value       = local.sns_topic_arn
}

output "lambda_error_alarm_arns" {
  description = "ARNs of Lambda error alarms"
  value       = { for k, v in aws_cloudwatch_metric_alarm.lambda_errors : k => v.arn }
}

output "lambda_throttle_alarm_arns" {
  description = "ARNs of Lambda throttle alarms"
  value       = { for k, v in aws_cloudwatch_metric_alarm.lambda_throttles : k => v.arn }
}

output "lambda_duration_alarm_arns" {
  description = "ARNs of Lambda duration alarms"
  value       = { for k, v in aws_cloudwatch_metric_alarm.lambda_duration : k => v.arn }
}

output "bedrock_error_alarm_arn" {
  description = "ARN of Bedrock error alarm"
  value       = var.bedrock_kb_id != "" ? aws_cloudwatch_metric_alarm.bedrock_errors[0].arn : null
}

output "bedrock_throttle_alarm_arn" {
  description = "ARN of Bedrock throttle alarm"
  value       = var.bedrock_kb_id != "" ? aws_cloudwatch_metric_alarm.bedrock_throttles[0].arn : null
}

output "opensearch_capacity_alarm_arn" {
  description = "ARN of OpenSearch capacity alarm"
  value       = var.opensearch_collection_id != "" ? aws_cloudwatch_metric_alarm.opensearch_capacity[0].arn : null
}
