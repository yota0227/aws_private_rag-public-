# SNS Topic for Budget Notifications
resource "aws_sns_topic" "budget_alerts" {
  name = "${var.project_name}-${var.environment}-budget-alerts"

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-budget-alerts-topic"
    }
  )
}

# SNS Topic Subscriptions for Email Notifications
resource "aws_sns_topic_subscription" "budget_email" {
  for_each = toset(var.notification_emails)

  topic_arn = aws_sns_topic.budget_alerts.arn
  protocol  = "email"
  endpoint  = each.value
}

# AWS Budget
resource "aws_budgets_budget" "main" {
  name              = var.budget_name
  budget_type       = "COST"
  limit_amount      = var.budget_limit_amount
  limit_unit        = "USD"
  time_unit         = var.budget_time_unit
  time_period_start = formatdate("YYYY-MM-01_00:00", timestamp())

  # Cost filters (optional)
  dynamic "cost_filter" {
    for_each = var.cost_filters
    content {
      name   = cost_filter.key
      values = cost_filter.value
    }
  }

  # Notifications for each threshold
  dynamic "notification" {
    for_each = var.alert_thresholds
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_sns_topic_arns  = [aws_sns_topic.budget_alerts.arn]
    }
  }

  # Additional notification for forecasted costs
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_sns_topic_arns = [aws_sns_topic.budget_alerts.arn]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-${var.environment}-budget"
    }
  )
}
