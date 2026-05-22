# LLM Gateway - MCP Server Resources (Frontend VPC)
# IAM Role, Instance Profile, and Policies for MCP EC2
#
# Requirements: 12.1, 12.2, 12.3, 12.4, 12.5

# =============================================================================
# IAM Role - MCP Server EC2 (Requirement 12.5)
# =============================================================================

resource "aws_iam_role" "mcp_server" {
  name = "role-mcp-server-bos-ai-seoul-prod"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.llm_gateway_tags, {
    Name = "role-mcp-server-bos-ai-seoul-prod"
  })
}

# =============================================================================
# IAM Policy - Lambda InvokeFunction (Requirement 12.1)
# =============================================================================

resource "aws_iam_role_policy" "mcp_lambda_invoke" {
  name = "mcp-lambda-invoke"
  role = aws_iam_role.mcp_server.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = "arn:aws:lambda:ap-northeast-2:${data.aws_caller_identity.current.account_id}:function:lambda-document-processor-seoul-prod"
      }
    ]
  })
}

# =============================================================================
# IAM Policy - Secrets Manager (Requirement 12.2)
# =============================================================================

resource "aws_iam_role_policy" "mcp_secrets_manager" {
  name = "mcp-secrets-manager"
  role = aws_iam_role.mcp_server.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "arn:aws:secretsmanager:ap-northeast-2:${data.aws_caller_identity.current.account_id}:secret:llm-gateway/*"
      }
    ]
  })
}

# =============================================================================
# IAM Policy - CloudWatch Logs (Requirement 12.3)
# =============================================================================

resource "aws_iam_role_policy" "mcp_cloudwatch_logs" {
  name = "mcp-cloudwatch-logs"
  role = aws_iam_role.mcp_server.id

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
        Resource = "*"
      }
    ]
  })
}

# =============================================================================
# IAM Policy Attachment - SSM Managed Instance Core (Requirement 12.4)
# =============================================================================

resource "aws_iam_role_policy_attachment" "mcp_ssm_core" {
  role       = aws_iam_role.mcp_server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# =============================================================================
# IAM Instance Profile (Requirement 12.5)
# =============================================================================

resource "aws_iam_instance_profile" "mcp_server" {
  name = "profile-mcp-server-bos-ai-seoul-prod"
  role = aws_iam_role.mcp_server.name

  tags = merge(local.llm_gateway_tags, {
    Name = "profile-mcp-server-bos-ai-seoul-prod"
  })
}

# =============================================================================
# Data Source - Frontend VPC (Requirements 14.3, 4.1)
# =============================================================================

data "aws_vpc" "frontend" {
  provider = aws.seoul
  id       = "vpc-0a118e1bf21d0c057"
}

data "aws_subnets" "frontend_private" {
  provider = aws.seoul

  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.frontend.id]
  }

  filter {
    name   = "map-public-ip-on-launch"
    values = ["false"]
  }
}

# =============================================================================
# Data Source - Amazon Linux 2023 AMI (Requirement 4.3)
# =============================================================================

data "aws_ami" "al2023_mcp" {
  provider    = aws.seoul
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# =============================================================================
# Security Group - MCP Server EC2 (Requirements 14.1, 14.2, 14.3)
# =============================================================================

resource "aws_security_group" "mcp_server" {
  provider    = aws.seoul
  name        = "mcp-server-bos-ai-seoul-prod"
  description = "Security group for MCP Server EC2 - LLM Gateway"
  vpc_id      = data.aws_vpc.frontend.id

  tags = merge(local.llm_gateway_tags, {
    Name = "sg-mcp-server-bos-ai-seoul-prod"
  })
}

# Inbound: TCP 3000 from Frontend VPC — Req 14.1
resource "aws_security_group_rule" "mcp_inbound_frontend_vpc" {
  provider          = aws.seoul
  type              = "ingress"
  from_port         = 3000
  to_port           = 3000
  protocol          = "tcp"
  cidr_blocks       = ["10.10.0.0/16"]
  security_group_id = aws_security_group.mcp_server.id
  description       = "MCP Server from Frontend VPC (API Gateway/Lambda)"
}

# Outbound: TCP 443 to 0.0.0.0/0 (Lambda VPC Endpoint, Secrets Manager) — Req 14.2
resource "aws_security_group_rule" "mcp_outbound_https" {
  provider          = aws.seoul
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.mcp_server.id
  description       = "HTTPS outbound for Lambda VPC Endpoint and Secrets Manager"
}

# =============================================================================
# Launch Template - MCP Server EC2 (Requirements 4.1-4.6, 26.6)
# =============================================================================

resource "aws_launch_template" "mcp_server" {
  provider      = aws.seoul
  name_prefix   = "lt-mcp-server-bos-ai-seoul-prod-"
  image_id      = data.aws_ami.al2023_mcp.id
  instance_type = "t3.small"

  iam_instance_profile {
    name = aws_iam_instance_profile.mcp_server.name
  }

  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [aws_security_group.mcp_server.id]
    subnet_id                   = data.aws_subnets.frontend_private.ids[0]
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  user_data = base64encode(templatefile("${path.module}/templates/mcp-server-user-data.sh.tpl", {
    aws_region   = "ap-northeast-2"
    package_json = file("${path.module}/templates/mcp-server/package.json")
    server_js    = file("${path.module}/templates/mcp-server/server.js")
  }))

  tag_specifications {
    resource_type = "instance"
    tags = merge(local.llm_gateway_tags, {
      Name = "ec2-mcp-server-bos-ai-seoul-prod"
    })
  }

  tag_specifications {
    resource_type = "volume"
    tags = merge(local.llm_gateway_tags, {
      Name = "ebs-mcp-server-bos-ai-seoul-prod"
    })
  }

  tags = merge(local.llm_gateway_tags, {
    Name = "lt-mcp-server-bos-ai-seoul-prod"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# EC2 Instance - MCP Server (Requirements 4.1-4.6, 5.1-5.7, 22.1-22.4)
# =============================================================================

resource "aws_instance" "mcp_server" {
  provider = aws.seoul

  launch_template {
    id      = aws_launch_template.mcp_server.id
    version = aws_launch_template.mcp_server.latest_version
  }

  tags = merge(local.llm_gateway_tags, {
    Name = "ec2-mcp-server-bos-ai-seoul-prod"
  })
}

# =============================================================================
# CloudWatch Log Group - MCP Server (Requirement 23.7)
# =============================================================================

resource "aws_cloudwatch_log_group" "mcp_server" {
  provider          = aws.seoul
  name              = "/llm-gateway/mcp-server"
  retention_in_days = 30

  tags = merge(local.llm_gateway_tags, {
    Name = "log-mcp-server-bos-ai-seoul-prod"
  })
}

# =============================================================================
# CloudWatch Alarm - MCP Server CPU Utilization (Requirement 23.2)
# =============================================================================

resource "aws_cloudwatch_metric_alarm" "mcp_cpu_high" {
  provider            = aws.seoul
  alarm_name          = "alarm-mcp-server-cpu-high-bos-ai-seoul-prod"
  alarm_description   = "MCP Server EC2 CPU utilization exceeds 80% for 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    InstanceId = aws_instance.mcp_server.id
  }

  alarm_actions = [aws_sns_topic.llm_gateway_alerts.arn]
  ok_actions    = [aws_sns_topic.llm_gateway_alerts.arn]

  tags = merge(local.llm_gateway_tags, {
    Name = "alarm-mcp-server-cpu-high-bos-ai-seoul-prod"
  })
}

# =============================================================================
# CloudWatch Alarm - MCP Server Status Check Failed (Requirement 23.2)
# =============================================================================

resource "aws_cloudwatch_metric_alarm" "mcp_status_check_failed" {
  provider            = aws.seoul
  alarm_name          = "alarm-mcp-server-status-check-bos-ai-seoul-prod"
  alarm_description   = "MCP Server EC2 status check failed for 2 consecutive periods"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0

  dimensions = {
    InstanceId = aws_instance.mcp_server.id
  }

  alarm_actions = [aws_sns_topic.llm_gateway_alerts.arn]
  ok_actions    = [aws_sns_topic.llm_gateway_alerts.arn]

  tags = merge(local.llm_gateway_tags, {
    Name = "alarm-mcp-server-status-check-bos-ai-seoul-prod"
  })
}
