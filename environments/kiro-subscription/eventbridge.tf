# EventBridge Configuration for Kiro Subscription Prompt Collection

# Custom Event Bus for Kiro Prompts
resource "aws_cloudwatch_event_bus" "kiro_prompts" {
  name = "kiro-prompts-${var.environment}"

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-prompts-bus-${var.environment}"
    }
  )
}

# EventBridge Rule for Prompt Events
resource "aws_cloudwatch_event_rule" "kiro_prompt_received" {
  name           = "kiro-prompt-received-${var.environment}"
  description    = "Trigger when user prompt is received"
  event_bus_name = aws_cloudwatch_event_bus.kiro_prompts.name

  event_pattern = jsonencode({
    source      = ["kiro.subscription"]
    detail-type = ["Prompt Received"]
    detail = {
      status = ["success"]
    }
  })

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-prompt-received-${var.environment}"
    }
  )
}

# EventBridge Target - Lambda Function
resource "aws_cloudwatch_event_target" "kiro_lambda" {
  rule           = aws_cloudwatch_event_rule.kiro_prompt_received.name
  target_id      = "KiroPromptProcessor"
  arn            = aws_lambda_function.kiro_prompt_processor.arn
  event_bus_name = aws_cloudwatch_event_bus.kiro_prompts.name
  role_arn       = aws_iam_role.kiro_eventbridge.arn

  input_transformer {
    input_paths = {
      prompt_id = "$.detail.prompt_id"
      user_id   = "$.detail.user_id"
      timestamp = "$.detail.timestamp"
    }
    input_template = jsonencode({
      prompt_id = "<prompt_id>"
      user_id   = "<user_id>"
      timestamp = "<timestamp>"
    })
  }
}

# EventBridge Rule for Error Handling
resource "aws_cloudwatch_event_rule" "kiro_prompt_error" {
  name           = "kiro-prompt-error-${var.environment}"
  description    = "Trigger when prompt processing fails"
  event_bus_name = aws_cloudwatch_event_bus.kiro_prompts.name

  event_pattern = jsonencode({
    source      = ["kiro.subscription"]
    detail-type = ["Prompt Error"]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-prompt-error-${var.environment}"
    }
  )
}

# EventBridge Target for Error - SNS
resource "aws_cloudwatch_event_target" "kiro_error_sns" {
  rule           = aws_cloudwatch_event_rule.kiro_prompt_error.name
  target_id      = "KiroErrorNotification"
  arn            = aws_sns_topic.kiro_errors.arn
  event_bus_name = aws_cloudwatch_event_bus.kiro_prompts.name
}

# SNS Topic for Error Notifications
resource "aws_sns_topic" "kiro_errors" {
  name = "kiro-subscription-errors-${var.environment}"

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-errors-${var.environment}"
    }
  )
}

# SNS Topic Policy
resource "aws_sns_topic_policy" "kiro_errors" {
  arn = aws_sns_topic.kiro_errors.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.kiro_errors.arn
      }
    ]
  })
}

# CloudWatch Log Group for EventBridge
resource "aws_cloudwatch_log_group" "kiro_eventbridge" {
  name              = "/aws/events/kiro-${var.environment}"
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-eventbridge-logs-${var.environment}"
    }
  )
}

# EventBridge Rule for Logging
resource "aws_cloudwatch_event_rule" "kiro_all_events" {
  name           = "kiro-all-events-${var.environment}"
  description    = "Log all Kiro events"
  event_bus_name = aws_cloudwatch_event_bus.kiro_prompts.name

  event_pattern = jsonencode({
    source = ["kiro.subscription"]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-all-events-${var.environment}"
    }
  )
}

# EventBridge Target for Logging
resource "aws_cloudwatch_event_target" "kiro_logs" {
  rule           = aws_cloudwatch_event_rule.kiro_all_events.name
  target_id      = "KiroEventLogging"
  arn            = aws_cloudwatch_log_group.kiro_eventbridge.arn
  event_bus_name = aws_cloudwatch_event_bus.kiro_prompts.name
}

# IAM Role for EventBridge Logging
resource "aws_iam_role" "kiro_eventbridge_logs" {
  name        = "kiro-eventbridge-logs-role-${var.environment}"
  description = "IAM role for EventBridge to write logs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-eventbridge-logs-role-${var.environment}"
    }
  )
}

# IAM Policy for EventBridge Logging
resource "aws_iam_role_policy" "kiro_eventbridge_logs" {
  name = "kiro-eventbridge-logs-policy"
  role = aws_iam_role.kiro_eventbridge_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.kiro_eventbridge.arn}:*"
      }
    ]
  })
}
