# IAM Role for Lambda Document Processor
# This role allows Lambda to access S3, CloudWatch Logs, Bedrock, KMS, and VPC resources

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda_processor" {
  name               = "${var.project_name}-lambda-processor-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  description        = "IAM role for Lambda document processor with least-privilege access"

  tags = merge(
    var.tags,
    {
      Name = "${var.project_name}-lambda-processor-role-${var.environment}"
    }
  )
}

# Policy for S3 read access
data "aws_iam_policy_document" "lambda_s3_access" {
  statement {
    sid    = "S3ReadAccess"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucket"
    ]

    resources = [
      var.s3_data_source_bucket_arn,
      "${var.s3_data_source_bucket_arn}/*"
    ]
  }
}

resource "aws_iam_policy" "lambda_s3_access" {
  name        = "${var.project_name}-lambda-s3-policy-${var.environment}"
  description = "Allows Lambda to read from S3 document bucket"
  policy      = data.aws_iam_policy_document.lambda_s3_access.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_s3_access" {
  role       = aws_iam_role.lambda_processor.name
  policy_arn = aws_iam_policy.lambda_s3_access.arn
}

# Policy for CloudWatch Logs
data "aws_iam_policy_document" "lambda_cloudwatch_logs" {
  statement {
    sid    = "CloudWatchLogsAccess"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = [
      "arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-*"
    ]
  }
}

resource "aws_iam_policy" "lambda_cloudwatch_logs" {
  name        = "${var.project_name}-lambda-logs-policy-${var.environment}"
  description = "Allows Lambda to write logs to CloudWatch"
  policy      = data.aws_iam_policy_document.lambda_cloudwatch_logs.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_cloudwatch_logs" {
  role       = aws_iam_role.lambda_processor.name
  policy_arn = aws_iam_policy.lambda_cloudwatch_logs.arn
}

# Policy for Bedrock ingestion jobs
data "aws_iam_policy_document" "lambda_bedrock_access" {
  statement {
    sid    = "BedrockIngestionAccess"
    effect = "Allow"

    actions = [
      "bedrock:StartIngestionJob",
      "bedrock:GetIngestionJob",
      "bedrock:ListIngestionJobs"
    ]

    resources = [
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:knowledge-base/*"
    ]
  }
}

resource "aws_iam_policy" "lambda_bedrock_access" {
  name        = "${var.project_name}-lambda-bedrock-policy-${var.environment}"
  description = "Allows Lambda to start Bedrock Knowledge Base ingestion jobs"
  policy      = data.aws_iam_policy_document.lambda_bedrock_access.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_bedrock_access" {
  role       = aws_iam_role.lambda_processor.name
  policy_arn = aws_iam_policy.lambda_bedrock_access.arn
}

# Policy for KMS key usage
data "aws_iam_policy_document" "lambda_kms_access" {
  statement {
    sid    = "KMSDecrypt"
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

resource "aws_iam_policy" "lambda_kms_access" {
  name        = "${var.project_name}-lambda-kms-policy-${var.environment}"
  description = "Allows Lambda to use KMS key for decryption"
  policy      = data.aws_iam_policy_document.lambda_kms_access.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_kms_access" {
  role       = aws_iam_role.lambda_processor.name
  policy_arn = aws_iam_policy.lambda_kms_access.arn
}

# Policy for VPC network interface management (required for VPC Lambda)
data "aws_iam_policy_document" "lambda_vpc_access" {
  statement {
    sid    = "VPCNetworkInterfaceManagement"
    effect = "Allow"

    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
      "ec2:AssignPrivateIpAddresses",
      "ec2:UnassignPrivateIpAddresses"
    ]

    resources = ["*"]
  }
}

resource "aws_iam_policy" "lambda_vpc_access" {
  name        = "${var.project_name}-lambda-vpc-policy-${var.environment}"
  description = "Allows Lambda to manage VPC network interfaces"
  policy      = data.aws_iam_policy_document.lambda_vpc_access.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  role       = aws_iam_role.lambda_processor.name
  policy_arn = aws_iam_policy.lambda_vpc_access.arn
}

# Policy for SQS Dead Letter Queue access
data "aws_iam_policy_document" "lambda_sqs_access" {
  statement {
    sid    = "SQSDLQAccess"
    effect = "Allow"

    actions = [
      "sqs:SendMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl"
    ]

    resources = [
      "arn:aws:sqs:*:${data.aws_caller_identity.current.account_id}:*-dlq"
    ]
  }
}

resource "aws_iam_policy" "lambda_sqs_access" {
  name        = "${var.project_name}-lambda-sqs-policy-${var.environment}"
  description = "Allows Lambda to send messages to SQS Dead Letter Queue"
  policy      = data.aws_iam_policy_document.lambda_sqs_access.json

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_sqs_access" {
  role       = aws_iam_role.lambda_processor.name
  policy_arn = aws_iam_policy.lambda_sqs_access.arn
}
