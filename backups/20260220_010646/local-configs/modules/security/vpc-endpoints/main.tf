# VPC Endpoints Module
# Creates VPC endpoints for AWS services to enable PrivateLink connectivity

# Bedrock Runtime VPC Endpoint (Interface)
resource "aws_vpc_endpoint" "bedrock_runtime" {
  count = var.enable_bedrock_runtime_endpoint ? 1 : 0

  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  policy = data.aws_iam_policy_document.bedrock_runtime_endpoint_policy[0].json

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-bedrock-runtime-endpoint-${var.environment}"
    }
  )
}

# Bedrock Runtime Endpoint Policy
data "aws_iam_policy_document" "bedrock_runtime_endpoint_policy" {
  count = var.enable_bedrock_runtime_endpoint ? 1 : 0

  statement {
    sid    = "AllowBedrockRuntimeAccess"
    effect = "Allow"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream"
    ]

    resources = [
      "arn:aws:bedrock:${var.region}::foundation-model/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

# Bedrock Agent Runtime VPC Endpoint (Interface)
resource "aws_vpc_endpoint" "bedrock_agent_runtime" {
  count = var.enable_bedrock_agent_runtime_endpoint ? 1 : 0

  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.bedrock-agent-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  policy = data.aws_iam_policy_document.bedrock_agent_runtime_endpoint_policy[0].json

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-bedrock-agent-runtime-endpoint-${var.environment}"
    }
  )
}

# Bedrock Agent Runtime Endpoint Policy
data "aws_iam_policy_document" "bedrock_agent_runtime_endpoint_policy" {
  count = var.enable_bedrock_agent_runtime_endpoint ? 1 : 0

  statement {
    sid    = "AllowBedrockAgentRuntimeAccess"
    effect = "Allow"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = [
      "bedrock:Retrieve",
      "bedrock:RetrieveAndGenerate",
      "bedrock:InvokeAgent"
    ]

    resources = [
      "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:knowledge-base/*",
      "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:agent/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

# S3 Gateway Endpoint
resource "aws_vpc_endpoint" "s3" {
  count = var.enable_s3_endpoint ? 1 : 0

  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.route_table_ids

  policy = data.aws_iam_policy_document.s3_endpoint_policy[0].json

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-s3-endpoint-${var.environment}"
    }
  )
}

# S3 Endpoint Policy
data "aws_iam_policy_document" "s3_endpoint_policy" {
  count = var.enable_s3_endpoint ? 1 : 0

  statement {
    sid    = "AllowS3Access"
    effect = "Allow"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
      "s3:GetObjectVersion"
    ]

    resources = [
      "arn:aws:s3:::${var.project_name}-*",
      "arn:aws:s3:::${var.project_name}-*/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

# OpenSearch Serverless VPC Endpoint (Interface)
resource "aws_vpc_endpoint" "opensearch" {
  count = var.enable_opensearch_endpoint ? 1 : 0

  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.aoss"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  policy = data.aws_iam_policy_document.opensearch_endpoint_policy[0].json

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-opensearch-endpoint-${var.environment}"
    }
  )
}

# OpenSearch Serverless Endpoint Policy
data "aws_iam_policy_document" "opensearch_endpoint_policy" {
  count = var.enable_opensearch_endpoint ? 1 : 0

  statement {
    sid    = "AllowOpenSearchServerlessAccess"
    effect = "Allow"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = [
      "aoss:APIAccessAll"
    ]

    resources = [
      "arn:aws:aoss:${var.region}:${data.aws_caller_identity.current.account_id}:collection/*"
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}
