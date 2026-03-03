# SNS Topic for Alarm Notifications (if not provided)
resource "aws_sns_topic" "alarms" {
  count = var.sns_topic_arn == "" ? 1 : 0

  name = "${var.project_name}-${var.environment}-cloudwatch-alarms"

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-cloudwatch-alarms-topic"
    }
  )
}

locals {
  sns_topic_arn = var.sns_topic_arn != "" ? var.sns_topic_arn : aws_sns_topic.alarms[0].arn
}

# Lambda Error Rate Alarms
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = toset(var.lambda_function_names)

  alarm_name          = "${var.project_name}-${var.environment}-lambda-${each.value}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = var.lambda_error_threshold
  alarm_description   = "This metric monitors Lambda function errors for ${each.value}"
  alarm_actions       = [local.sns_topic_arn]

  dimensions = {
    FunctionName = each.value
  }

  tags = merge(
    var.tags,
    {
      Name     = "${var.project_name}-${var.environment}-lambda-${each.value}-errors-alarm"
      Function = each.value
    }
  )
}

# Lambda Throttle Alarms
resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  for_each = toset(var.lambda_function_names)

  alarm_name          = "${var.project_name}-${var.environment}-lambda-${each.value}-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = var.lambda_throttle_threshold
  alarm_description   = "This metric monitors Lambda function throttles for ${each.value}"
  alarm_actions       = [local.sns_topic_arn]

  dimensions = {
    FunctionName = each.value
  }

  tags = merge(
    var.tags,
    {
      Name     = "${var.project_name}-${var.environment}-lambda-${each.value}-throttles-alarm"
      Function = each.value
    }
  )
}

# Lambda Duration Alarm (approaching timeout)
resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  for_each = toset(var.lambda_function_names)

  alarm_name          = "${var.project_name}-${var.environment}-lambda-${each.value}-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = 270000 # 270 seconds (90% of 300s timeout)
  alarm_description   = "This metric monitors Lambda function duration approaching timeout for ${each.value}"
  alarm_actions       = [local.sns_topic_arn]

  dimensions = {
    FunctionName = each.value
  }

  tags = merge(
    var.tags,
    {
      Name     = "${var.project_name}-${var.environment}-lambda-${each.value}-duration-alarm"
      Function = each.value
    }
  )
}

# Bedrock API Error Alarm
resource "aws_cloudwatch_metric_alarm" "bedrock_errors" {
  count = var.bedrock_kb_id != "" ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-bedrock-api-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ModelInvocationClientError"
  namespace           = "AWS/Bedrock"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "This metric monitors Bedrock API client errors"
  alarm_actions       = [local.sns_topic_arn]

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-bedrock-errors-alarm"
    }
  )
}

# Bedrock Throttling Alarm
resource "aws_cloudwatch_metric_alarm" "bedrock_throttles" {
  count = var.bedrock_kb_id != "" ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-bedrock-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ModelInvocationThrottles"
  namespace           = "AWS/Bedrock"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "This metric monitors Bedrock API throttling"
  alarm_actions       = [local.sns_topic_arn]

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-bedrock-throttles-alarm"
    }
  )
}

# OpenSearch Capacity Utilization Alarm
resource "aws_cloudwatch_metric_alarm" "opensearch_capacity" {
  count = var.opensearch_collection_id != "" ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-opensearch-capacity"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "SearchOCU"
  namespace           = "AWS/AOSS"
  period              = 300
  statistic           = "Average"
  threshold           = var.opensearch_capacity_threshold
  alarm_description   = "This metric monitors OpenSearch Serverless capacity utilization"
  alarm_actions       = [local.sns_topic_arn]

  dimensions = {
    CollectionId = var.opensearch_collection_id
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-opensearch-capacity-alarm"
    }
  )
}
