# IAM Roles and Policies for Kiro Subscription

# IAM Role for Kiro Application
resource "aws_iam_role" "kiro_app" {
  name        = "kiro-subscription-app-role-${var.environment}"
  description = "IAM role for Kiro subscription application"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = [
            "lambda.amazonaws.com",
            "ec2.amazonaws.com"
          ]
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-subscription-app-role-${var.environment}"
    }
  )
}

# IAM Policy for S3 Access
resource "aws_iam_role_policy" "kiro_s3_access" {
  name = "kiro-s3-access-policy"
  role = aws_iam_role.kiro_app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.kiro_prompts.arn,
          "${aws_s3_bucket.kiro_prompts.arn}/*"
        ]
      }
    ]
  })
}

# IAM Policy for KMS Access
resource "aws_iam_role_policy" "kiro_kms_access" {
  name = "kiro-kms-access-policy"
  role = aws_iam_role.kiro_app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.kiro_prompts.arn
      }
    ]
  })
}

# IAM Policy for Secrets Manager Access
resource "aws_iam_role_policy" "kiro_secrets_access" {
  name = "kiro-secrets-access-policy"
  role = aws_iam_role.kiro_app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = aws_secretsmanager_secret.kiro_api_key.arn
      }
    ]
  })
}

# IAM Policy for CloudWatch Logs
resource "aws_iam_role_policy" "kiro_logs_access" {
  name = "kiro-logs-access-policy"
  role = aws_iam_role.kiro_app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/kiro/*"
      }
    ]
  })
}

# IAM Policy for EventBridge
resource "aws_iam_role_policy" "kiro_eventbridge_access" {
  name = "kiro-eventbridge-access-policy"
  role = aws_iam_role.kiro_app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "events:PutEvents"
        ]
        Resource = aws_cloudwatch_event_bus.kiro_prompts.arn
      }
    ]
  })
}

# IAM Role for Lambda Execution
resource "aws_iam_role" "kiro_lambda" {
  name        = "kiro-subscription-lambda-role-${var.environment}"
  description = "IAM role for Kiro subscription Lambda functions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(
    local.common_tags,
    {
      Name = "kiro-subscription-lambda-role-${var.environment}"
    }
  )
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "kiro_lambda_basic" {
  role       = aws_iam_role.kiro_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# IAM Policy for Lambda S3 Access
resource "aws_iam_role_policy" "kiro_lambda_s3" {
  name = "kiro-lambda-s3-policy"
  role = aws_iam_role.kiro_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.kiro_prompts.arn}/*"
      }
    ]
  })
}

# IAM Policy for Lambda KMS Access
resource "aws_iam_role_policy" "kiro_lambda_kms" {
  name = "kiro-lambda-kms-policy"
  role = aws_iam_role.kiro_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.kiro_prompts.arn
      }
    ]
  })
}

# IAM Role for EventBridge
resource "aws_iam_role" "kiro_eventbridge" {
  name        = "kiro-subscription-eventbridge-role-${var.environment}"
  description = "IAM role for Kiro subscription EventBridge"

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
      Name = "kiro-subscription-eventbridge-role-${var.environment}"
    }
  )
}

# IAM Policy for EventBridge to invoke Lambda
resource "aws_iam_role_policy" "kiro_eventbridge_lambda" {
  name = "kiro-eventbridge-lambda-policy"
  role = aws_iam_role.kiro_eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = aws_lambda_function.kiro_prompt_processor.arn
      }
    ]
  })
}
