# ============================================================================
# QuickSight 모니터링 - CloudWatch 알람 및 대시보드
# Requirements: 5.11, 7.4, 10.1, 10.2, 10.3, 10.4, 10.5
# ============================================================================

resource "aws_sns_topic" "quicksight_alerts" {
  provider = aws.seoul
  name     = "quicksight-alerts-bos-ai-seoul-prod"

  tags = merge(local.common_tags, {
    Name = "quicksight-alerts-bos-ai-seoul-prod"
  })
}

# Lambda 스로틀 알람 (5분간 5회 초과)
resource "aws_cloudwatch_metric_alarm" "qs_lambda_throttle" {
  provider            = aws.seoul
  alarm_name          = "quicksight-lambda-throttle-alarm"
  alarm_description   = "QuickSight RAG Connector Lambda 스로틀 과다 - SPICE 새로고침 빈도 조정 필요"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.qs_rag_connector.function_name
  }

  alarm_actions = [aws_sns_topic.quicksight_alerts.arn]
  ok_actions    = [aws_sns_topic.quicksight_alerts.arn]

  tags = local.common_tags
}

# Lambda 에러 알람
resource "aws_cloudwatch_metric_alarm" "qs_lambda_errors" {
  provider            = aws.seoul
  alarm_name          = "quicksight-lambda-error-alarm"
  alarm_description   = "QuickSight RAG Connector Lambda 에러율 증가"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.qs_rag_connector.function_name
  }

  alarm_actions = [aws_sns_topic.quicksight_alerts.arn]

  tags = local.common_tags
}

# CloudWatch 대시보드
resource "aws_cloudwatch_dashboard" "quicksight" {
  provider       = aws.seoul
  dashboard_name = "QuickSight-BOS-AI-Prod"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "RAG Connector Lambda - 동시 실행 / 스로틀"
          period = 300
          metrics = [
            ["AWS/Lambda", "ConcurrentExecutions", "FunctionName", aws_lambda_function.qs_rag_connector.function_name],
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.qs_rag_connector.function_name]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "QuickSight S3 버킷 - 크기 / 객체 수"
          period = 86400
          metrics = [
            ["AWS/S3", "BucketSizeBytes", "BucketName", aws_s3_bucket.quicksight_data.bucket, "StorageType", "StandardStorage"],
            ["AWS/S3", "NumberOfObjects", "BucketName", aws_s3_bucket.quicksight_data.bucket, "StorageType", "AllStorageTypes"]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "RAG Connector Lambda - 에러 / 실행 시간"
          period = 300
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.qs_rag_connector.function_name],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.qs_rag_connector.function_name]
          ]
          view = "timeSeries"
        }
      }
    ]
  })
}

# QuickSight 감사 로그 그룹 (90일 보존)
resource "aws_cloudwatch_log_group" "quicksight_audit" {
  provider          = aws.seoul
  name              = "/aws/quicksight/audit-bos-ai-seoul-prod"
  retention_in_days = 90

  tags = merge(local.common_tags, {
    Name = "quicksight-audit-logs"
  })
}

output "quicksight_alerts_sns_arn" {
  description = "QuickSight 알람 SNS 토픽 ARN"
  value       = aws_sns_topic.quicksight_alerts.arn
}
