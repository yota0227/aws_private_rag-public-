# Neptune Read-Only IAM Role — Lambda Handler (MCP/LLM 질의용)
# LLM은 Read-Only(neptune-db:ReadDataViaQuery)만 허용하여
# 원본 RTL 코드 대신 노드/엣지 그래프에만 접근
#
# Requirements: 16.5

resource "aws_iam_role" "neptune_readonly" {
  name               = "${var.project_name}-neptune-readonly-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  tags = local.common_tags
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "neptune_readonly_policy" {
  name   = "neptune-readonly-query"
  role   = aws_iam_role.neptune_readonly.id
  policy = data.aws_iam_policy_document.neptune_readonly.json
}

data "aws_iam_policy_document" "neptune_readonly" {
  statement {
    effect  = "Allow"
    actions = ["neptune-db:ReadDataViaQuery"]
    resources = [
      "arn:aws:neptune-db:ap-northeast-2:*:${module.neptune.neptune_cluster_id}/*"
    ]
  }
}
