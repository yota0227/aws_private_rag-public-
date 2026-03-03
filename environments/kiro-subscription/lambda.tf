# Lambda Function for Kiro Prompt Processing

# Archive file for Lambda placeholder
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/lambda_placeholder.zip"

  source {
    content  = "def handler(event, context):\n    return {'statusCode': 200, 'body': 'Placeholder Lambda'}\n"
    filename = "index.py"
  }
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "kiro_lambda" {
  name              = "/aws/lambda/kiro-prompt-processor-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-lambda-logs-${var.environment}"
    }
  )
}

# Lambda Function for Prompt Processing
resource "aws_lambda_function" "kiro_prompt_processor" {
  filename         = data.archive_file.lambda_placeholder.output_path
  function_name    = "kiro-prompt-processor-${var.environment}"
  role             = aws_iam_role.kiro_lambda.arn
  handler          = "index.handler"
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 512
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  environment {
    variables = {
      S3_BUCKET_NAME    = aws_s3_bucket.kiro_prompts.id
      KMS_KEY_ID        = aws_kms_key.kiro_prompts.id
      ENVIRONMENT       = var.environment
      LOG_LEVEL         = "INFO"
      SECRETS_REGION    = var.aws_region
      API_KEY_SECRET    = aws_secretsmanager_secret.kiro_api_key.name
      S3_CONFIG_SECRET  = aws_secretsmanager_secret.kiro_s3_config.name
    }
  }

  depends_on = [
    aws_iam_role_policy.kiro_lambda_s3,
    aws_iam_role_policy.kiro_lambda_kms,
    aws_cloudwatch_log_group.kiro_lambda
  ]

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-prompt-processor-${var.environment}"
    }
  )
}

# Lambda Permission for EventBridge
resource "aws_lambda_permission" "kiro_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.kiro_prompt_processor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.kiro_prompt_received.arn
}

# Lambda Function for Metadata Analysis (optional)
resource "aws_lambda_function" "kiro_metadata_analyzer" {
  filename         = data.archive_file.lambda_placeholder.output_path
  function_name    = "kiro-metadata-analyzer-${var.environment}"
  role             = aws_iam_role.kiro_lambda.arn
  handler          = "index.handler"
  runtime          = "python3.11"
  timeout          = 300
  memory_size      = 1024
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  environment {
    variables = {
      S3_BUCKET_NAME   = aws_s3_bucket.kiro_prompts.id
      KMS_KEY_ID       = aws_kms_key.kiro_prompts.id
      ENVIRONMENT      = var.environment
      LOG_LEVEL        = "INFO"
      ANALYSIS_PREFIX  = "analysis"
    }
  }

  depends_on = [
    aws_iam_role_policy.kiro_lambda_s3,
    aws_iam_role_policy.kiro_lambda_kms
  ]

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-metadata-analyzer-${var.environment}"
    }
  )
}

# CloudWatch Alarm for Lambda Errors
resource "aws_cloudwatch_metric_alarm" "kiro_lambda_errors" {
  alarm_name          = "kiro-lambda-errors-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Alert when Lambda errors exceed threshold"
  alarm_actions       = [aws_sns_topic.kiro_errors.arn]

  dimensions = {
    FunctionName = aws_lambda_function.kiro_prompt_processor.function_name
  }

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-lambda-errors-${var.environment}"
    }
  )
}

# CloudWatch Alarm for Lambda Duration
resource "aws_cloudwatch_metric_alarm" "kiro_lambda_duration" {
  alarm_name          = "kiro-lambda-duration-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = 30000  # 30 seconds
  alarm_description   = "Alert when Lambda duration is high"
  alarm_actions       = [aws_sns_topic.kiro_errors.arn]

  dimensions = {
    FunctionName = aws_lambda_function.kiro_prompt_processor.function_name
  }

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-lambda-duration-${var.environment}"
    }
  )
}
