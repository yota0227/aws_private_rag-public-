# CloudWatch Log Groups for Lambda Functions
resource "aws_cloudwatch_log_group" "lambda" {
  for_each = toset(var.lambda_function_names)

  name              = "/aws/lambda/${each.value}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name      = "${var.project_name}-${var.environment}-lambda-${each.value}-logs"
      Component = "Lambda"
      Function  = each.value
    }
  )
}

# CloudWatch Log Group for Bedrock Knowledge Base
resource "aws_cloudwatch_log_group" "bedrock" {
  count = var.bedrock_kb_name != "" ? 1 : 0

  name              = "/aws/bedrock/knowledgebase/${var.bedrock_kb_name}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name      = "${var.project_name}-${var.environment}-bedrock-kb-logs"
      Component = "Bedrock"
      Service   = "KnowledgeBase"
    }
  )
}

# CloudWatch Log Groups for VPC Flow Logs
resource "aws_cloudwatch_log_group" "vpc_flow_logs" {
  for_each = toset(var.vpc_ids)

  name              = "/aws/vpc/flowlogs/${each.value}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.tags,
    {
      Name      = "${var.project_name}-${var.environment}-vpc-flowlogs-${each.value}"
      Component = "VPC"
      VpcId     = each.value
    }
  )
}
