# ============================================================================
# Step Functions - RTL 분석 파이프라인 오케스트레이터
# Purpose: 6단계 분석 파이프라인(Hierarchy → Clock → Dataflow → Topic → Claim → HDD)을
#          Step Functions Standard Workflow로 조율
#
# Requirements: 1.2, 1.3, 1.4, 1.7, 11.1, 11.6
# ============================================================================

# ----------------------------------------------------------------------------
# IAM Role for Step Functions
# ----------------------------------------------------------------------------

resource "aws_iam_role" "sfn_analysis" {
  provider = aws.seoul

  name        = "role-sfn-analysis-orchestrator-${var.environment}"
  description = "IAM role for RTL Analysis Orchestrator Step Functions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name    = "role-sfn-analysis-orchestrator-${var.environment}"
    Purpose = "Step Functions Analysis Orchestrator IAM Role"
  })
}

# IAM Policy: Lambda Invoke - RTL Parser Lambda 호출 권한
resource "aws_iam_role_policy" "sfn_lambda_invoke" {
  name = "sfn-lambda-invoke-access"
  role = aws_iam_role.sfn_analysis.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = [aws_lambda_function.rtl_parser.arn]
      }
    ]
  })
}

# IAM Policy: DynamoDB - rag-extraction-tasks 테이블 상태 기록 권한
resource "aws_iam_role_policy" "sfn_dynamodb" {
  name = "sfn-dynamodb-access"
  role = aws_iam_role.sfn_analysis.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [aws_dynamodb_table.extraction_tasks.arn]
      }
    ]
  })
}

# IAM Policy: CloudWatch Logs - Step Functions 실행 로그 권한
resource "aws_iam_role_policy" "sfn_logs" {
  name = "sfn-logs-access"
  role = aws_iam_role.sfn_analysis.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:CreateLogStream",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutLogEvents",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = ["*"]
      }
    ]
  })
}

# ----------------------------------------------------------------------------
# Step Functions State Machine - Analysis Orchestrator
# Standard Workflow: 9,465개 파일 처리 시 5분 이상 소요 가능
# 6단계: HierarchyExtraction → ClockDomainAnalysis → DataflowTracking
#        → TopicClassification → ClaimGeneration → HDDGeneration
# ----------------------------------------------------------------------------

resource "aws_sfn_state_machine" "analysis_orchestrator" {
  provider = aws.seoul

  name     = "analysis-orchestrator-${var.environment}"
  role_arn = aws_iam_role.sfn_analysis.arn
  type     = "STANDARD"

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn_analysis.arn}:*"
    include_execution_data = true
    level                  = "ERROR"
  }

  definition = jsonencode({
    Comment = "RTL Analysis Pipeline Orchestrator - 6-stage analysis with retry and skip-on-failure"
    StartAt = "HierarchyExtraction"
    States = {
      # ------------------------------------------------------------------
      # Stage 1: Hierarchy Extraction
      # ------------------------------------------------------------------
      HierarchyExtraction = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.rtl_parser.arn
          Payload = {
            "stage"           = "hierarchy_extraction"
            "pipeline_id.$"   = "$.pipeline_id"
            "chip_type.$"     = "$.chip_type"
            "snapshot_date.$" = "$.snapshot_date"
            "s3_prefix.$"     = "$.s3_prefix"
          }
        }
        ResultPath = "$.hierarchy_result"
        Retry = [
          {
            ErrorEquals     = ["States.ALL"]
            MaxAttempts     = 2
            BackoffRate     = 2
            IntervalSeconds = 10
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "ClockDomainAnalysis"
            ResultPath  = "$.hierarchy_error"
          }
        ]
        Next = "ClockDomainAnalysis"
      }

      # ------------------------------------------------------------------
      # Stage 2: Clock Domain Analysis
      # ------------------------------------------------------------------
      ClockDomainAnalysis = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.rtl_parser.arn
          Payload = {
            "stage"           = "clock_domain_analysis"
            "pipeline_id.$"   = "$.pipeline_id"
            "chip_type.$"     = "$.chip_type"
            "snapshot_date.$" = "$.snapshot_date"
            "s3_prefix.$"     = "$.s3_prefix"
          }
        }
        ResultPath = "$.clock_domain_result"
        Retry = [
          {
            ErrorEquals     = ["States.ALL"]
            MaxAttempts     = 2
            BackoffRate     = 2
            IntervalSeconds = 10
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "DataflowTracking"
            ResultPath  = "$.clock_domain_error"
          }
        ]
        Next = "DataflowTracking"
      }

      # ------------------------------------------------------------------
      # Stage 3: Dataflow Tracking
      # ------------------------------------------------------------------
      DataflowTracking = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.rtl_parser.arn
          Payload = {
            "stage"           = "dataflow_tracking"
            "pipeline_id.$"   = "$.pipeline_id"
            "chip_type.$"     = "$.chip_type"
            "snapshot_date.$" = "$.snapshot_date"
            "s3_prefix.$"     = "$.s3_prefix"
          }
        }
        ResultPath = "$.dataflow_result"
        Retry = [
          {
            ErrorEquals     = ["States.ALL"]
            MaxAttempts     = 2
            BackoffRate     = 2
            IntervalSeconds = 10
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "TopicClassification"
            ResultPath  = "$.dataflow_error"
          }
        ]
        Next = "TopicClassification"
      }

      # ------------------------------------------------------------------
      # Stage 4: Topic Classification
      # ------------------------------------------------------------------
      TopicClassification = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.rtl_parser.arn
          Payload = {
            "stage"           = "topic_classification"
            "pipeline_id.$"   = "$.pipeline_id"
            "chip_type.$"     = "$.chip_type"
            "snapshot_date.$" = "$.snapshot_date"
            "s3_prefix.$"     = "$.s3_prefix"
          }
        }
        ResultPath = "$.topic_result"
        Retry = [
          {
            ErrorEquals     = ["States.ALL"]
            MaxAttempts     = 2
            BackoffRate     = 2
            IntervalSeconds = 10
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "ClaimGeneration"
            ResultPath  = "$.topic_error"
          }
        ]
        Next = "ClaimGeneration"
      }

      # ------------------------------------------------------------------
      # Stage 5: Claim Generation
      # ------------------------------------------------------------------
      ClaimGeneration = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.rtl_parser.arn
          Payload = {
            "stage"           = "claim_generation"
            "pipeline_id.$"   = "$.pipeline_id"
            "chip_type.$"     = "$.chip_type"
            "snapshot_date.$" = "$.snapshot_date"
            "s3_prefix.$"     = "$.s3_prefix"
          }
        }
        ResultPath = "$.claim_result"
        Retry = [
          {
            ErrorEquals     = ["States.ALL"]
            MaxAttempts     = 2
            BackoffRate     = 2
            IntervalSeconds = 10
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "HDDGeneration"
            ResultPath  = "$.claim_error"
          }
        ]
        Next = "HDDGeneration"
      }

      # ------------------------------------------------------------------
      # Stage 6: HDD Generation
      # ------------------------------------------------------------------
      HDDGeneration = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.rtl_parser.arn
          Payload = {
            "stage"           = "hdd_generation"
            "pipeline_id.$"   = "$.pipeline_id"
            "chip_type.$"     = "$.chip_type"
            "snapshot_date.$" = "$.snapshot_date"
            "s3_prefix.$"     = "$.s3_prefix"
          }
        }
        ResultPath = "$.hdd_result"
        Retry = [
          {
            ErrorEquals     = ["States.ALL"]
            MaxAttempts     = 2
            BackoffRate     = 2
            IntervalSeconds = 10
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "PipelineComplete"
            ResultPath  = "$.hdd_error"
          }
        ]
        Next = "PipelineComplete"
      }

      # ------------------------------------------------------------------
      # Terminal State
      # ------------------------------------------------------------------
      PipelineComplete = {
        Type = "Succeed"
      }
    }
  })

  tags = merge(local.common_tags, {
    Name    = "analysis-orchestrator-${var.environment}"
    Purpose = "RTL Analysis Pipeline Orchestrator"
  })

  depends_on = [
    aws_iam_role_policy.sfn_lambda_invoke,
    aws_iam_role_policy.sfn_dynamodb,
    aws_iam_role_policy.sfn_logs,
    aws_cloudwatch_log_group.sfn_analysis,
  ]
}

# ----------------------------------------------------------------------------
# CloudWatch Log Group for Step Functions
# ----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "sfn_analysis" {
  provider = aws.seoul

  name              = "/aws/states/analysis-orchestrator-${var.environment}"
  retention_in_days = 30

  tags = merge(local.common_tags, {
    Name    = "analysis-orchestrator-${var.environment}-logs"
    Purpose = "Step Functions Analysis Orchestrator Logs"
  })
}

# ----------------------------------------------------------------------------
# CloudWatch Metric Alarm - Analysis Error Rate
# ExecutionsFailed 메트릭이 10% 초과 시 알람
# ----------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "analysis_error_rate" {
  provider = aws.seoul

  alarm_name          = "sfn-analysis-error-rate-${var.environment}"
  alarm_description   = "RTL Analysis Pipeline - ExecutionsFailed exceeds 10% threshold"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 10

  metric_query {
    id          = "error_rate"
    expression  = "(failed / total) * 100"
    label       = "Error Rate (%)"
    return_data = true
  }

  metric_query {
    id = "failed"

    metric {
      metric_name = "ExecutionsFailed"
      namespace   = "AWS/States"
      period      = 300
      stat        = "Sum"

      dimensions = {
        StateMachineArn = aws_sfn_state_machine.analysis_orchestrator.arn
      }
    }
  }

  metric_query {
    id = "total"

    metric {
      metric_name = "ExecutionsStarted"
      namespace   = "AWS/States"
      period      = 300
      stat        = "Sum"

      dimensions = {
        StateMachineArn = aws_sfn_state_machine.analysis_orchestrator.arn
      }
    }
  }

  tags = merge(local.common_tags, {
    Name    = "sfn-analysis-error-rate-${var.environment}"
    Purpose = "Analysis Pipeline Error Rate Alarm"
  })
}

# ----------------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------------

output "sfn_analysis_orchestrator_arn" {
  description = "Step Functions Analysis Orchestrator state machine ARN"
  value       = aws_sfn_state_machine.analysis_orchestrator.arn
}

output "sfn_analysis_role_arn" {
  description = "Step Functions Analysis Orchestrator IAM role ARN"
  value       = aws_iam_role.sfn_analysis.arn
}
