locals {
  # Lambda metrics widgets
  lambda_widgets = [
    for idx, func_name in var.lambda_function_names : {
      type = "metric"
      properties = {
        metrics = [
          ["AWS/Lambda", "Invocations", { stat = "Sum", label = "Invocations" }],
          [".", "Errors", { stat = "Sum", label = "Errors" }],
          [".", "Throttles", { stat = "Sum", label = "Throttles" }],
          [".", "Duration", { stat = "Average", label = "Avg Duration" }]
        ]
        view    = "timeSeries"
        stacked = false
        region  = var.region
        title   = "Lambda: ${func_name}"
        period  = 300
        dimensions = {
          FunctionName = func_name
        }
      }
      x      = (idx % 2) * 12
      y      = floor(idx / 2) * 6
      width  = 12
      height = 6
    }
  ]

  # Bedrock metrics widget
  bedrock_widget = var.bedrock_kb_id != "" ? [{
    type = "metric"
    properties = {
      metrics = [
        ["AWS/Bedrock", "ModelInvocationLatency", { stat = "Average", label = "Avg Latency" }],
        [".", "ModelInvocationClientError", { stat = "Sum", label = "Client Errors" }],
        [".", "ModelInvocationServerError", { stat = "Sum", label = "Server Errors" }],
        [".", "ModelInvocationThrottles", { stat = "Sum", label = "Throttles" }]
      ]
      view    = "timeSeries"
      stacked = false
      region  = var.region
      title   = "Bedrock Knowledge Base Metrics"
      period  = 300
    }
    x      = 0
    y      = length(var.lambda_function_names) > 0 ? ceil(length(var.lambda_function_names) / 2) * 6 : 0
    width  = 12
    height = 6
  }] : []

  # OpenSearch metrics widget
  opensearch_widget = var.opensearch_collection_id != "" ? [{
    type = "metric"
    properties = {
      metrics = [
        ["AWS/AOSS", "SearchOCU", { stat = "Average", label = "Search OCU" }],
        [".", "IndexingOCU", { stat = "Average", label = "Indexing OCU" }],
        [".", "SearchLatency", { stat = "Average", label = "Search Latency" }],
        [".", "IndexingRate", { stat = "Sum", label = "Indexing Rate" }]
      ]
      view    = "timeSeries"
      stacked = false
      region  = var.region
      title   = "OpenSearch Serverless Metrics"
      period  = 300
      dimensions = {
        CollectionId = var.opensearch_collection_id
      }
    }
    x      = 12
    y      = length(var.lambda_function_names) > 0 ? ceil(length(var.lambda_function_names) / 2) * 6 : 0
    width  = 12
    height = 6
  }] : []

  # VPC Flow Logs widget
  vpc_widget = length(var.vpc_ids) > 0 ? [{
    type = "log"
    properties = {
      query   = <<-EOT
        SOURCE '/aws/vpc/flowlogs/${var.vpc_ids[0]}'
        | fields @timestamp, srcaddr, dstaddr, srcport, dstport, protocol, bytes, action
        | filter action = "REJECT"
        | stats count() by srcaddr
        | sort count desc
        | limit 20
      EOT
      region  = var.region
      title   = "Top Rejected IPs (VPC Flow Logs)"
      stacked = false
    }
    x      = 0
    y      = (length(var.lambda_function_names) > 0 ? ceil(length(var.lambda_function_names) / 2) * 6 : 0) + (var.bedrock_kb_id != "" || var.opensearch_collection_id != "" ? 6 : 0)
    width  = 24
    height = 6
  }] : []

  # Combine all widgets
  all_widgets = concat(
    local.lambda_widgets,
    local.bedrock_widget,
    local.opensearch_widget,
    local.vpc_widget
  )
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-${var.environment}-dashboard"

  dashboard_body = jsonencode({
    widgets = local.all_widgets
  })
}
