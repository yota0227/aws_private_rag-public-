# IAM Role for Bedrock Knowledge Base
# This role allows Bedrock to access S3, OpenSearch, and KMS with least-privilege permissions

data "aws_iam_policy_document" "bedrock_kb_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:knowledge-base/*"]
    }
  }
}

resource "aws_iam_role" "bedrock_kb" {
  name               = "${var.project_name}-bedrock-kb-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.bedrock_kb_assume_role.json
  description        = "IAM role for Bedrock Knowledge Base with least-privilege access"

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-bedrock-kb-role-${var.environment}"
    }
  )
}

# Policy for S3 read access to data source bucket
data "aws_iam_policy_document" "bedrock_kb_s3_access" {
  statement {
    sid    = "S3ReadAccess"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:ListBucket"
    ]

    resources = [
      var.s3_data_source_bucket_arn,
      "${var.s3_data_source_bucket_arn}/*"
    ]
  }
}

resource "aws_iam_policy" "bedrock_kb_s3_access" {
  name        = "${var.project_name}-bedrock-kb-s3-policy-${var.environment}"
  description = "Allows Bedrock Knowledge Base to read from S3 data source bucket"
  policy      = data.aws_iam_policy_document.bedrock_kb_s3_access.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "bedrock_kb_s3_access" {
  role       = aws_iam_role.bedrock_kb.name
  policy_arn = aws_iam_policy.bedrock_kb_s3_access.arn
}

# Policy for OpenSearch Serverless access
data "aws_iam_policy_document" "bedrock_kb_opensearch_access" {
  statement {
    sid    = "OpenSearchServerlessAccess"
    effect = "Allow"

    actions = [
      "aoss:APIAccessAll"
    ]

    resources = [
      var.opensearch_collection_arn
    ]
  }
}

resource "aws_iam_policy" "bedrock_kb_opensearch_access" {
  name        = "${var.project_name}-bedrock-kb-opensearch-policy-${var.environment}"
  description = "Allows Bedrock Knowledge Base to write to OpenSearch Serverless collection"
  policy      = data.aws_iam_policy_document.bedrock_kb_opensearch_access.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "bedrock_kb_opensearch_access" {
  role       = aws_iam_role.bedrock_kb.name
  policy_arn = aws_iam_policy.bedrock_kb_opensearch_access.arn
}

# Policy for KMS key usage
data "aws_iam_policy_document" "bedrock_kb_kms_access" {
  statement {
    sid    = "KMSDecryptEncrypt"
    effect = "Allow"

    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey"
    ]

    resources = [
      var.kms_key_arn
    ]
  }
}

resource "aws_iam_policy" "bedrock_kb_kms_access" {
  name        = "${var.project_name}-bedrock-kb-kms-policy-${var.environment}"
  description = "Allows Bedrock Knowledge Base to use KMS key for encryption/decryption"
  policy      = data.aws_iam_policy_document.bedrock_kb_kms_access.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "bedrock_kb_kms_access" {
  role       = aws_iam_role.bedrock_kb.name
  policy_arn = aws_iam_policy.bedrock_kb_kms_access.arn
}

# Policy for Bedrock model invocation
data "aws_iam_policy_document" "bedrock_kb_model_access" {
  statement {
    sid    = "BedrockModelInvoke"
    effect = "Allow"

    actions = [
      "bedrock:InvokeModel"
    ]

    resources = var.bedrock_model_arns
  }
}

resource "aws_iam_policy" "bedrock_kb_model_access" {
  name        = "${var.project_name}-bedrock-kb-model-policy-${var.environment}"
  description = "Allows Bedrock Knowledge Base to invoke embedding and foundation models"
  policy      = data.aws_iam_policy_document.bedrock_kb_model_access.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "bedrock_kb_model_access" {
  role       = aws_iam_role.bedrock_kb.name
  policy_arn = aws_iam_policy.bedrock_kb_model_access.arn
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}
