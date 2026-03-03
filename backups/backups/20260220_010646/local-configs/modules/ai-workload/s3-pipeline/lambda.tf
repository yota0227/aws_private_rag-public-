# Lambda Document Processor Configuration
# Creates Lambda function for processing documents uploaded to S3

# Lambda Function
resource "aws_lambda_function" "document_processor" {
  function_name = var.lambda_function_name
  role          = var.lambda_execution_role_arn
  handler       = "handler.lambda_handler"
  runtime       = var.lambda_runtime

  # Placeholder for Lambda deployment package
  # In production, this should reference an S3 bucket or local file
  filename         = "${path.module}/lambda_placeholder.zip"
  source_code_hash = filebase64sha256("${path.module}/lambda_placeholder.zip")

  memory_size = var.lambda_memory_size
  timeout     = var.lambda_timeout

  # VPC Configuration for private subnet deployment
  vpc_config {
    subnet_ids         = var.lambda_vpc_config.subnet_ids
    security_group_ids = var.lambda_vpc_config.security_group_ids
  }

  # Environment variables for Lambda function
  environment {
    variables = merge(
      {
        DESTINATION_BUCKET = aws_s3_bucket.destination.id
        SOURCE_BUCKET      = aws_s3_bucket.source.id
        KMS_KEY_ARN        = var.kms_key_arn
        LOG_LEVEL          = "INFO"
      },
      var.lambda_environment_variables
    )
  }

  # Enable X-Ray tracing for distributed tracing
  tracing_config {
    mode = "Active"
  }

  # Dead Letter Queue configuration for failed invocations
  dead_letter_config {
    target_arn = aws_sqs_queue.lambda_dlq.arn
  }

  tags = merge(
    var.tags,
    {
      Name = var.lambda_function_name
    }
  )
}

# Create placeholder zip file if it doesn't exist
resource "null_resource" "lambda_placeholder" {
  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    command = <<-EOT
      if [ ! -f "${path.module}/lambda_placeholder.zip" ]; then
        echo 'def lambda_handler(event, context): return {"statusCode": 200}' > /tmp/handler.py
        cd /tmp && zip -q ${path.module}/lambda_placeholder.zip handler.py
        rm /tmp/handler.py
      fi
    EOT
  }
}

# Lambda Function URL (optional, for testing)
# Uncomment if you need direct HTTP access to Lambda
# resource "aws_lambda_function_url" "document_processor" {
#   function_name      = aws_lambda_function.document_processor.function_name
#   authorization_type = "AWS_IAM"
# }


# Dead Letter Queue (SQS) for failed Lambda invocations
resource "aws_sqs_queue" "lambda_dlq" {
  name                       = "${var.lambda_function_name}-dlq"
  message_retention_seconds  = 1209600 # 14 days
  visibility_timeout_seconds = var.lambda_timeout * 6 # 6x Lambda timeout

  # Enable encryption
  sqs_managed_sse_enabled = true

  tags = merge(
    var.tags,
    {
      Name = "${var.lambda_function_name}-dlq"
      Type = "DeadLetterQueue"
    }
  )
}

# Dead Letter Queue Policy
resource "aws_sqs_queue_policy" "lambda_dlq" {
  queue_url = aws_sqs_queue.lambda_dlq.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.lambda_dlq.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_lambda_function.document_processor.arn
          }
        }
      }
    ]
  })
}

# Update Lambda function to include DLQ configuration
# Note: This is added to the existing Lambda function resource
# The dead_letter_config block should be added to aws_lambda_function.document_processor

# Lambda Permission for S3 to invoke the function
resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.document_processor.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.destination.arn
}

# S3 Event Notification to trigger Lambda on object creation
resource "aws_s3_bucket_notification" "document_upload" {
  bucket = aws_s3_bucket.destination.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.document_processor.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = ""
    filter_suffix       = ""
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke]
}
