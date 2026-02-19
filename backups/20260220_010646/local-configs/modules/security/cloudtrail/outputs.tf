output "trail_id" {
  description = "ID of the CloudTrail trail"
  value       = aws_cloudtrail.main.id
}

output "trail_arn" {
  description = "ARN of the CloudTrail trail"
  value       = aws_cloudtrail.main.arn
}

output "trail_home_region" {
  description = "Home region of the CloudTrail trail"
  value       = aws_cloudtrail.main.home_region
}

output "s3_bucket_id" {
  description = "ID of the S3 bucket for CloudTrail logs"
  value       = aws_s3_bucket.cloudtrail.id
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket for CloudTrail logs"
  value       = aws_s3_bucket.cloudtrail.arn
}

output "access_logs_bucket_id" {
  description = "ID of the S3 bucket for CloudTrail access logs"
  value       = aws_s3_bucket.cloudtrail_access_logs.id
}
