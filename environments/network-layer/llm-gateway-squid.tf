# ==============================================================================
# LLM Gateway — Squid Forward Proxy (Logging VPC)
# IAM Role, Instance Profile, Security Group
#
# Requirements: 15.1, 15.2, 15.3, 15.4, 15.5
# ==============================================================================

locals {
  llm_gateway_tags = {
    Project     = "BOS-AI"
    Environment = "prod"
    ManagedBy   = "terraform"
    Layer       = "network"
    Service     = "llm-gateway"
    Component   = "squid-proxy"
  }
}

# ==============================================================================
# IAM Role for Squid EC2
# ==============================================================================

resource "aws_iam_role" "squid_proxy" {
  provider = aws.seoul

  name = "role-squid-proxy-bos-ai-seoul-prod"

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
    Name = "role-squid-proxy-bos-ai-seoul-prod"
  })
}

# CloudWatch Logs policy for Squid EC2
resource "aws_iam_role_policy" "squid_proxy_cloudwatch" {
  provider = aws.seoul

  name = "squid-proxy-cloudwatch-logs"
  role = aws_iam_role.squid_proxy.id

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
        Resource = "arn:aws:logs:ap-northeast-2:*:log-group:/llm-gateway/squid*"
      }
    ]
  })
}

# SSM Managed Instance Core policy attachment
resource "aws_iam_role_policy_attachment" "squid_proxy_ssm" {
  provider = aws.seoul

  role       = aws_iam_role.squid_proxy.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Instance Profile for Squid EC2
resource "aws_iam_instance_profile" "squid_proxy" {
  provider = aws.seoul

  name = "profile-squid-proxy-bos-ai-seoul-prod"
  role = aws_iam_role.squid_proxy.name

  tags = merge(local.llm_gateway_tags, {
    Name = "profile-squid-proxy-bos-ai-seoul-prod"
  })
}

# ==============================================================================
# Security Group for Squid EC2 (Logging VPC)
# ==============================================================================

resource "aws_security_group" "squid_proxy" {
  provider = aws.seoul

  name        = "squid-proxy-bos-ai-seoul-prod"
  description = "Security group for Squid forward proxy EC2 in Logging VPC"
  vpc_id      = module.vpc_logging.vpc_id

  tags = merge(local.llm_gateway_tags, {
    Name = "sg-squid-proxy-bos-ai-seoul-prod"
  })
}

# Inbound: TCP 3128 from on-premises (proxy traffic)
resource "aws_security_group_rule" "squid_inbound_proxy" {
  provider = aws.seoul

  type              = "ingress"
  from_port         = 3128
  to_port           = 3128
  protocol          = "tcp"
  cidr_blocks       = ["192.128.0.0/16"]
  security_group_id = aws_security_group.squid_proxy.id
  description       = "Squid proxy traffic from on-premises"
}

# Inbound: TCP 22 from on-premises (SSH management)
resource "aws_security_group_rule" "squid_inbound_ssh" {
  provider = aws.seoul

  type              = "ingress"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = ["192.128.0.0/16"]
  security_group_id = aws_security_group.squid_proxy.id
  description       = "SSH management from on-premises"
}

# Outbound: TCP 443 to 0.0.0.0/0 (HTTPS via NAT Gateway)
resource "aws_security_group_rule" "squid_outbound_https" {
  provider = aws.seoul

  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.squid_proxy.id
  description       = "HTTPS outbound via NAT Gateway"
}

# Outbound: UDP 53 to 0.0.0.0/0 (DNS resolution)
resource "aws_security_group_rule" "squid_outbound_dns_udp" {
  provider = aws.seoul

  type              = "egress"
  from_port         = 53
  to_port           = 53
  protocol          = "udp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.squid_proxy.id
  description       = "DNS resolution (UDP)"
}

# Outbound: TCP 53 to 0.0.0.0/0 (DNS resolution)
resource "aws_security_group_rule" "squid_outbound_dns_tcp" {
  provider = aws.seoul

  type              = "egress"
  from_port         = 53
  to_port           = 53
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.squid_proxy.id
  description       = "DNS resolution (TCP)"
}


# ==============================================================================
# Squid EC2 Instance with Launch Template
# Requirements: 6.1-6.6, 7.1-7.8, 22.1-22.4, 22.6, 23.9, 26.5, 26.6
# ==============================================================================

# Amazon Linux 2023 AMI data source
data "aws_ami" "amazon_linux_2023_squid" {
  provider    = aws.seoul
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
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

# Launch Template for Squid EC2
resource "aws_launch_template" "squid_proxy" {
  provider = aws.seoul

  name        = "lt-squid-proxy-bos-ai-seoul-prod"
  description = "Launch template for Squid forward proxy EC2 instance"

  image_id      = data.aws_ami.amazon_linux_2023_squid.id
  instance_type = "t3.micro"

  # IMDSv2 required
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  # No public IP
  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [aws_security_group.squid_proxy.id]
    subnet_id                   = module.vpc_logging.private_subnet_ids[0]
  }

  # Root EBS 20GB gp3 encrypted
  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  # IAM instance profile
  iam_instance_profile {
    name = aws_iam_instance_profile.squid_proxy.name
  }

  # User Data script
  user_data = base64encode(templatefile("${path.module}/templates/squid-user-data.sh.tpl", {}))

  tag_specifications {
    resource_type = "instance"
    tags = merge(local.llm_gateway_tags, {
      Name = "ec2-squid-proxy-bos-ai-seoul-prod"
    })
  }

  tag_specifications {
    resource_type = "volume"
    tags = merge(local.llm_gateway_tags, {
      Name = "ebs-squid-proxy-bos-ai-seoul-prod"
    })
  }

  tags = merge(local.llm_gateway_tags, {
    Name = "lt-squid-proxy-bos-ai-seoul-prod"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# Squid EC2 Instance
resource "aws_instance" "squid_proxy" {
  provider = aws.seoul

  launch_template {
    id      = aws_launch_template.squid_proxy.id
    version = "$Latest"
  }

  tags = merge(local.llm_gateway_tags, {
    Name = "ec2-squid-proxy-bos-ai-seoul-prod"
  })
}

# ==============================================================================
# CloudWatch Log Group and Alarms for Squid
# Requirements: 23.3, 23.8
# ==============================================================================

# CloudWatch Log Group for Squid access logs (30-day retention)
resource "aws_cloudwatch_log_group" "squid_proxy" {
  provider = aws.seoul

  name              = "/llm-gateway/squid"
  retention_in_days = 30

  tags = merge(local.llm_gateway_tags, {
    Name = "log-squid-proxy-bos-ai-seoul-prod"
  })
}

# Data source to look up SNS topic for alarms
data "aws_sns_topic" "llm_gateway_alerts" {
  provider = aws.seoul

  name = "llm-gateway-alerts"
}

# CloudWatch Alarm: Squid CPU Utilization > 70% for 5 minutes
resource "aws_cloudwatch_metric_alarm" "squid_cpu_high" {
  provider = aws.seoul

  alarm_name          = "squid-proxy-cpu-high-bos-ai-seoul-prod"
  alarm_description   = "Squid proxy CPU utilization exceeds 70% for 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 70

  dimensions = {
    InstanceId = aws_instance.squid_proxy.id
  }

  alarm_actions = [data.aws_sns_topic.llm_gateway_alerts.arn]
  ok_actions    = [data.aws_sns_topic.llm_gateway_alerts.arn]

  tags = merge(local.llm_gateway_tags, {
    Name = "alarm-squid-cpu-high-bos-ai-seoul-prod"
  })
}

# CloudWatch Alarm: Squid StatusCheckFailed > 0 for 2 consecutive periods
resource "aws_cloudwatch_metric_alarm" "squid_status_check_failed" {
  provider = aws.seoul

  alarm_name          = "squid-proxy-status-check-failed-bos-ai-seoul-prod"
  alarm_description   = "Squid proxy status check failed for 2 consecutive periods"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0

  dimensions = {
    InstanceId = aws_instance.squid_proxy.id
  }

  alarm_actions = [data.aws_sns_topic.llm_gateway_alerts.arn]
  ok_actions    = [data.aws_sns_topic.llm_gateway_alerts.arn]

  tags = merge(local.llm_gateway_tags, {
    Name = "alarm-squid-status-check-bos-ai-seoul-prod"
  })
}
