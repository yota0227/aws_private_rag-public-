# LLM Gateway - LiteLLM Resources
# Secrets Manager, SNS Topic, and common locals for LLM Gateway
#
# Requirements: 16.1, 16.2, 16.3, 23.10

# =============================================================================
# Locals - Common tags for LLM Gateway resources
# =============================================================================

locals {
  llm_gateway_tags = {
    Project     = "BOS-AI"
    Environment = "prod"
    ManagedBy   = "terraform"
    Layer       = "app"
  }
}

# =============================================================================
# Secrets Manager - LiteLLM Master Key (Requirement 16.1)
# =============================================================================

resource "random_password" "litellm_master_key" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "litellm_master_key" {
  name        = "llm-gateway/litellm-master-key"
  description = "LiteLLM admin master key for Virtual Key management"

  tags = merge(local.llm_gateway_tags, {
    Name = "llm-gateway/litellm-master-key"
  })
}

resource "aws_secretsmanager_secret_version" "litellm_master_key" {
  secret_id     = aws_secretsmanager_secret.litellm_master_key.id
  secret_string = random_password.litellm_master_key.result
}

# =============================================================================
# Secrets Manager - MCP API Key (Requirement 16.2)
# =============================================================================

resource "random_password" "mcp_api_key" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "mcp_api_key" {
  name        = "llm-gateway/mcp-api-key"
  description = "MCP Server authentication API key"

  tags = merge(local.llm_gateway_tags, {
    Name = "llm-gateway/mcp-api-key"
  })
}

resource "aws_secretsmanager_secret_version" "mcp_api_key" {
  secret_id     = aws_secretsmanager_secret.mcp_api_key.id
  secret_string = random_password.mcp_api_key.result
}

# =============================================================================
# Secrets Manager - PostgreSQL Password (Requirement 16.3)
# =============================================================================

resource "random_password" "postgres_password" {
  length  = 24
  special = false
}

resource "aws_secretsmanager_secret" "postgres_password" {
  name        = "llm-gateway/postgres-password"
  description = "PostgreSQL password for LiteLLM database"

  tags = merge(local.llm_gateway_tags, {
    Name = "llm-gateway/postgres-password"
  })
}

resource "aws_secretsmanager_secret_version" "postgres_password" {
  secret_id     = aws_secretsmanager_secret.postgres_password.id
  secret_string = random_password.postgres_password.result
}

# =============================================================================
# SNS Topic - Alarm Notifications (Requirement 23.10)
# =============================================================================

resource "aws_sns_topic" "llm_gateway_alerts" {
  provider = aws.seoul
  name     = "llm-gateway-alerts"

  tags = merge(local.llm_gateway_tags, {
    Name = "llm-gateway-alerts"
  })
}

# =============================================================================
# IAM Role & Instance Profile - LiteLLM EC2 (Requirements 11.1-11.5, 24.4)
# =============================================================================

data "aws_iam_policy_document" "litellm_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "litellm" {
  name               = "role-litellm-bos-ai-seoul-prod"
  assume_role_policy = data.aws_iam_policy_document.litellm_assume_role.json

  tags = merge(local.llm_gateway_tags, {
    Name = "role-litellm-bos-ai-seoul-prod"
  })
}

resource "aws_iam_instance_profile" "litellm" {
  name = "profile-litellm-bos-ai-seoul-prod"
  role = aws_iam_role.litellm.name

  tags = merge(local.llm_gateway_tags, {
    Name = "profile-litellm-bos-ai-seoul-prod"
  })
}

# Bedrock InvokeModel (us-east-1) — Requirement 11.1
data "aws_iam_policy_document" "litellm_bedrock" {
  statement {
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = ["arn:aws:bedrock:us-east-1::foundation-model/*"]
  }
}

resource "aws_iam_role_policy" "litellm_bedrock" {
  name   = "litellm-bedrock-invoke"
  role   = aws_iam_role.litellm.id
  policy = data.aws_iam_policy_document.litellm_bedrock.json
}

# Secrets Manager GetSecretValue (ap-northeast-2, llm-gateway/*) — Requirement 11.2
data "aws_iam_policy_document" "litellm_secrets" {
  statement {
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      "arn:aws:secretsmanager:ap-northeast-2:*:secret:llm-gateway/*",
    ]
  }
}

resource "aws_iam_role_policy" "litellm_secrets" {
  name   = "litellm-secrets-read"
  role   = aws_iam_role.litellm.id
  policy = data.aws_iam_policy_document.litellm_secrets.json
}

# CloudWatch Logs — Requirement 11.3
data "aws_iam_policy_document" "litellm_cloudwatch_logs" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:ap-northeast-2:*:log-group:/llm-gateway/*"]
  }
}

resource "aws_iam_role_policy" "litellm_cloudwatch_logs" {
  name   = "litellm-cloudwatch-logs"
  role   = aws_iam_role.litellm.id
  policy = data.aws_iam_policy_document.litellm_cloudwatch_logs.json
}

# S3 PutObject for PostgreSQL backups — Requirement 24.4
data "aws_iam_policy_document" "litellm_s3_backup" {
  statement {
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "arn:aws:s3:::s3-bos-ai-backups-seoul-prod/llm-gateway/postgres/*",
    ]
  }
}

resource "aws_iam_role_policy" "litellm_s3_backup" {
  name   = "litellm-s3-backup"
  role   = aws_iam_role.litellm.id
  policy = data.aws_iam_policy_document.litellm_s3_backup.json
}

# AmazonSSMManagedInstanceCore — Requirement 11.4
resource "aws_iam_role_policy_attachment" "litellm_ssm" {
  role       = aws_iam_role.litellm.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# =============================================================================
# Data Source - Logging VPC (managed in network-layer)
# =============================================================================

data "aws_vpc" "logging" {
  provider = aws.seoul

  filter {
    name   = "cidr-block"
    values = ["10.200.0.0/16"]
  }
}

# =============================================================================
# Security Group - LiteLLM EC2 (Requirements 13.1, 13.2, 13.3, 13.5)
# =============================================================================

resource "aws_security_group" "litellm" {
  provider    = aws.seoul
  name        = "litellm-bos-ai-seoul-prod"
  description = "Security group for LiteLLM EC2 - LLM Gateway proxy"
  vpc_id      = data.aws_vpc.logging.id

  tags = merge(local.llm_gateway_tags, {
    Name = "sg-litellm-bos-ai-seoul-prod"
  })
}

# Inbound: TCP 4000 from Frontend VPC (API Gateway integration) — Req 13.1
resource "aws_security_group_rule" "litellm_inbound_frontend_vpc" {
  provider          = aws.seoul
  type              = "ingress"
  from_port         = 4000
  to_port           = 4000
  protocol          = "tcp"
  cidr_blocks       = ["10.10.0.0/16"]
  security_group_id = aws_security_group.litellm.id
  description       = "LiteLLM API from Frontend VPC (API Gateway integration)"
}

# Inbound: TCP 4000 from On-prem (direct TGW access) — Req 13.2
resource "aws_security_group_rule" "litellm_inbound_onprem" {
  provider          = aws.seoul
  type              = "ingress"
  from_port         = 4000
  to_port           = 4000
  protocol          = "tcp"
  cidr_blocks       = ["192.128.0.0/16"]
  security_group_id = aws_security_group.litellm.id
  description       = "LiteLLM API from on-premises via TGW"
}

# Outbound: TCP 443 to 0.0.0.0/0 (OpenAI via NAT, Bedrock via TGW) — Req 13.3
resource "aws_security_group_rule" "litellm_outbound_https" {
  provider          = aws.seoul
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.litellm.id
  description       = "HTTPS outbound for OpenAI via NAT and Bedrock via TGW"
}

# =============================================================================
# Data Source - Amazon Linux 2023 AMI for Seoul (Requirement 1.3)
# =============================================================================

data "aws_ami" "al2023_seoul" {
  provider    = aws.seoul
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# =============================================================================
# Data Source - Logging VPC Private Subnets (Requirement 1.1)
# =============================================================================

data "aws_subnets" "logging_private" {
  provider = aws.seoul

  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.logging.id]
  }

  filter {
    name   = "map-public-ip-on-launch"
    values = ["false"]
  }
}

# =============================================================================
# Launch Template - LiteLLM EC2 (Requirements 1.1-1.7, 22.1-22.4, 26.3, 26.6)
# =============================================================================

resource "aws_launch_template" "litellm" {
  provider    = aws.seoul
  name        = "lt-litellm-bos-ai-seoul-prod"
  description = "Launch Template for LiteLLM EC2 instance"

  image_id      = data.aws_ami.al2023_seoul.id
  instance_type = "t3.medium"

  # IMDSv2 required (Requirement 1.6, 22.1)
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  # IAM Instance Profile (Requirement 11.4)
  iam_instance_profile {
    name = aws_iam_instance_profile.litellm.name
  }

  # Network configuration: no public IP, SG, Logging VPC private subnet
  # (Requirements 1.2, 13.5, 22.3)
  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [aws_security_group.litellm.id]
    subnet_id                   = data.aws_subnets.logging_private.ids[0]
  }

  # Root EBS volume 30GB gp3 encrypted (Requirement 1.4, 22.2)
  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size           = 30
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  # Data EBS volume 50GB gp3 encrypted (Requirement 1.5)
  block_device_mappings {
    device_name = "/dev/sdf"

    ebs {
      volume_size           = 50
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = false
    }
  }

  # User Data script (Requirement 1.7)
  user_data = base64encode(templatefile(
    "${path.module}/templates/litellm-user-data.sh.tpl",
    {
      region                 = "ap-northeast-2"
      litellm_master_key_arn = aws_secretsmanager_secret.litellm_master_key.name
      postgres_password_arn  = aws_secretsmanager_secret.postgres_password.name
    }
  ))

  tag_specifications {
    resource_type = "instance"
    tags = merge(local.llm_gateway_tags, {
      Name = "ec2-litellm-bos-ai-seoul-prod"
    })
  }

  tag_specifications {
    resource_type = "volume"
    tags = merge(local.llm_gateway_tags, {
      Name = "ebs-litellm-bos-ai-seoul-prod"
    })
  }

  tags = merge(local.llm_gateway_tags, {
    Name = "lt-litellm-bos-ai-seoul-prod"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# EC2 Instance - LiteLLM (Requirements 1.1-1.7, 26.3, 26.6)
# =============================================================================

resource "aws_instance" "litellm" {
  provider = aws.seoul

  launch_template {
    id      = aws_launch_template.litellm.id
    version = aws_launch_template.litellm.latest_version
  }

  tags = merge(local.llm_gateway_tags, {
    Name = "ec2-litellm-bos-ai-seoul-prod"
  })

  lifecycle {
    # Allow instance replacement via Launch Template version update
    create_before_destroy = true
  }
}

# =============================================================================
# CloudWatch Log Group - LiteLLM (Requirement 23.6)
# =============================================================================

resource "aws_cloudwatch_log_group" "litellm" {
  provider          = aws.seoul
  name              = "/llm-gateway/litellm"
  retention_in_days = 30

  tags = merge(local.llm_gateway_tags, {
    Name = "log-litellm-bos-ai-seoul-prod"
  })
}

# =============================================================================
# CloudWatch Alarms - LiteLLM EC2 (Requirement 23.1)
# =============================================================================

# CPU Utilization > 80% for 5 minutes
resource "aws_cloudwatch_metric_alarm" "litellm_cpu_high" {
  provider            = aws.seoul
  alarm_name          = "litellm-cpu-utilization-high"
  alarm_description   = "LiteLLM EC2 CPU utilization exceeds 80% for 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    InstanceId = aws_instance.litellm.id
  }

  alarm_actions = [aws_sns_topic.llm_gateway_alerts.arn]
  ok_actions    = [aws_sns_topic.llm_gateway_alerts.arn]

  tags = merge(local.llm_gateway_tags, {
    Name = "alarm-litellm-cpu-bos-ai-seoul-prod"
  })
}

# StatusCheckFailed > 0 for 2 consecutive periods
resource "aws_cloudwatch_metric_alarm" "litellm_status_check_failed" {
  provider            = aws.seoul
  alarm_name          = "litellm-status-check-failed"
  alarm_description   = "LiteLLM EC2 status check failed for 2 consecutive periods"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0

  dimensions = {
    InstanceId = aws_instance.litellm.id
  }

  alarm_actions = [aws_sns_topic.llm_gateway_alerts.arn]
  ok_actions    = [aws_sns_topic.llm_gateway_alerts.arn]

  tags = merge(local.llm_gateway_tags, {
    Name = "alarm-litellm-status-bos-ai-seoul-prod"
  })
}

# =============================================================================
# CloudWatch Alarm - S3 Backup Age (Requirement 24.6)
# =============================================================================
# TODO: S3 backup age alarm requires a custom CloudWatch metric published by
# the CW Agent or a scheduled Lambda that checks the latest S3 object timestamp.
# This is not practical to implement with standard EC2 metrics alone.
# Implement as a custom metric (e.g., via CW Agent collectd plugin or a cron
# script that publishes "BackupAgeHours" metric) in a future iteration.
#
# Example alarm definition (to be enabled once custom metric is published):
#
# resource "aws_cloudwatch_metric_alarm" "litellm_backup_age" {
#   alarm_name          = "litellm-backup-age-exceeded"
#   alarm_description   = "No PostgreSQL backup detected in S3 within 25 hours"
#   comparison_operator = "GreaterThanThreshold"
#   evaluation_periods  = 1
#   metric_name         = "BackupAgeHours"
#   namespace           = "LLMGateway/Backups"
#   period              = 3600
#   statistic           = "Maximum"
#   threshold           = 25
#
#   dimensions = {
#     Service = "litellm-postgres"
#   }
#
#   alarm_actions = [aws_sns_topic.llm_gateway_alerts.arn]
#
#   tags = merge(local.llm_gateway_tags, {
#     Name = "alarm-litellm-backup-age-bos-ai-seoul-prod"
#   })
# }
