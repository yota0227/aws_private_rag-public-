# KMS Module Main Configuration
# Creates customer-managed KMS keys with service principal access
# Requirements: 5.4, 5.5, 5.6

# Get current AWS account ID and caller identity
data "aws_caller_identity" "current" {}

# Get current AWS region
data "aws_region" "current" {}

# KMS Key Policy Document
# Grants access to account root, service principals, and additional users
data "aws_iam_policy_document" "kms_key_policy" {
  # Statement 1: Enable IAM User Permissions
  # Allows account root to manage the key
  statement {
    sid    = "Enable IAM User Permissions"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions   = ["kms:*"]
    resources = ["*"]
  }


  # Statement 2: Allow Key Administrators
  # Grants key administration permissions to specified IAM principals
  dynamic "statement" {
    for_each = length(var.additional_key_admins) > 0 ? [1] : []

    content {
      sid    = "Allow Key Administrators"
      effect = "Allow"

      principals {
        type        = "AWS"
        identifiers = var.additional_key_admins
      }

      actions = [
        "kms:Create*",
        "kms:Describe*",
        "kms:Enable*",
        "kms:List*",
        "kms:Put*",
        "kms:Update*",
        "kms:Revoke*",
        "kms:Disable*",
        "kms:Get*",
        "kms:Delete*",
        "kms:TagResource",
        "kms:UntagResource",
        "kms:ScheduleKeyDeletion",
        "kms:CancelKeyDeletion"
      ]

      resources = ["*"]
    }
  }


  # Statement 3: Allow Key Users
  # Grants key usage permissions to specified IAM principals
  dynamic "statement" {
    for_each = length(var.additional_key_users) > 0 ? [1] : []

    content {
      sid    = "Allow Key Users"
      effect = "Allow"

      principals {
        type        = "AWS"
        identifiers = var.additional_key_users
      }

      actions = [
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:Encrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:CreateGrant"
      ]

      resources = ["*"]
    }
  }


  # Statement 4: Allow Bedrock Service to use the key
  # Requirement 5.5: Grant access to Bedrock service principal
  dynamic "statement" {
    for_each = var.enable_bedrock_access ? [1] : []

    content {
      sid    = "Allow Bedrock to use the key"
      effect = "Allow"

      principals {
        type        = "Service"
        identifiers = ["bedrock.amazonaws.com"]
      }

      actions = [
        "kms:Decrypt",
        "kms:GenerateDataKey",
        "kms:CreateGrant",
        "kms:DescribeKey"
      ]

      resources = ["*"]

      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["bedrock.${var.region}.amazonaws.com"]
      }
    }
  }


  # Statement 5: Allow S3 Service to use the key
  # Requirement 5.6: Grant access to S3 service principal
  dynamic "statement" {
    for_each = var.enable_s3_access ? [1] : []

    content {
      sid    = "Allow S3 to use the key"
      effect = "Allow"

      principals {
        type        = "Service"
        identifiers = ["s3.amazonaws.com"]
      }

      actions = [
        "kms:Decrypt",
        "kms:GenerateDataKey",
        "kms:DescribeKey"
      ]

      resources = ["*"]

      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["s3.${var.region}.amazonaws.com"]
      }
    }
  }


  # Statement 6: Allow OpenSearch Serverless to use the key
  # Requirement 5.6: Grant access to OpenSearch service principal
  dynamic "statement" {
    for_each = var.enable_opensearch_access ? [1] : []

    content {
      sid    = "Allow OpenSearch Serverless to use the key"
      effect = "Allow"

      principals {
        type        = "Service"
        identifiers = ["aoss.amazonaws.com"]
      }

      actions = [
        "kms:Decrypt",
        "kms:CreateGrant",
        "kms:DescribeKey"
      ]

      resources = ["*"]

      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["aoss.${var.region}.amazonaws.com"]
      }
    }
  }


  # Statement 7: Allow Lambda Service to use the key (optional)
  dynamic "statement" {
    for_each = var.enable_lambda_access ? [1] : []

    content {
      sid    = "Allow Lambda to use the key"
      effect = "Allow"

      principals {
        type        = "Service"
        identifiers = ["lambda.amazonaws.com"]
      }

      actions = [
        "kms:Decrypt",
        "kms:GenerateDataKey",
        "kms:DescribeKey"
      ]

      resources = ["*"]

      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["lambda.${var.region}.amazonaws.com"]
      }
    }
  }

  # Statement 8: Allow CloudWatch Logs Service to use the key (optional)
  dynamic "statement" {
    for_each = var.enable_cloudwatch_logs_access ? [1] : []

    content {
      sid    = "Allow CloudWatch Logs to use the key"
      effect = "Allow"

      principals {
        type        = "Service"
        identifiers = ["logs.${var.region}.amazonaws.com"]
      }

      actions = [
        "kms:Decrypt",
        "kms:Encrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:CreateGrant",
        "kms:DescribeKey"
      ]

      resources = ["*"]

      condition {
        test     = "ArnLike"
        variable = "kms:EncryptionContext:aws:logs:arn"
        values   = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:*"]
      }
    }
  }

  # Statement 9: Allow CloudTrail Service to use the key
  statement {
    sid    = "Allow CloudTrail to use the key"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey*",
      "kms:DescribeKey"
    ]

    resources = ["*"]

    condition {
      test     = "StringLike"
      variable = "kms:EncryptionContext:aws:cloudtrail:arn"
      values   = ["arn:aws:cloudtrail:*:${data.aws_caller_identity.current.account_id}:trail/*"]
    }
  }
}


# KMS Key Resource
# Customer-managed key with automatic rotation enabled
resource "aws_kms_key" "main" {
  description             = var.key_description
  deletion_window_in_days = var.deletion_window_in_days
  enable_key_rotation     = var.enable_key_rotation
  key_usage               = var.key_usage
  customer_master_key_spec = var.customer_master_key_spec
  policy                  = data.aws_iam_policy_document.kms_key_policy.json

  tags = merge(
    var.tags,
    {
      Name = var.key_description
    }
  )
}

# KMS Key Alias
# Provides a friendly name for the key
resource "aws_kms_alias" "main" {
  name          = "alias/bos-ai-rag-${data.aws_region.current.name}"
  target_key_id = aws_kms_key.main.key_id
}
