# =============================================================================
# LLM Gateway - Nginx Reverse Proxy EC2 (Frontend VPC)
#
# Private API Gateway는 custom domain을 지원하지 않으므로
# Nginx가 TLS 종단 + API Gateway 프록시를 담당한다.
#
# 접근 경로:
#   On-prem → VPN → TGW → Frontend VPC → Nginx:443
#     → API GW r0qa9lzhgi → LiteLLM EC2 / MCP EC2
#
# 사내 DNS (corp.bos-semi.com.zone):
#   llm  IN  A  <nginx-private-ip>   (terraform output: nginx_proxy_private_ip)
#   mcp  IN  A  <nginx-private-ip>
#
# Requirements: 10.1, 10.2, 10.3
# =============================================================================

# =============================================================================
# Data sources
# =============================================================================

data "aws_subnets" "frontend_private_nginx" {
  filter {
    name   = "vpc-id"
    values = ["vpc-0a118e1bf21d0c057"]
  }
  filter {
    name   = "map-public-ip-on-launch"
    values = ["false"]
  }
}

data "aws_ami" "al2023_nginx" {
  provider    = aws.seoul
  most_recent = true
  owners      = ["self"]

  filter {
    name   = "name"
    values = ["nginx-proxy-al2023-bos-ai"]
  }
}

# =============================================================================
# IAM Role
# =============================================================================

data "aws_iam_policy_document" "nginx_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "nginx" {
  name               = "role-nginx-proxy-bos-ai-seoul-prod"
  assume_role_policy = data.aws_iam_policy_document.nginx_assume_role.json

  tags = merge(local.llm_gateway_tags, {
    Name = "role-nginx-proxy-bos-ai-seoul-prod"
  })
}

resource "aws_iam_instance_profile" "nginx" {
  name = "profile-nginx-proxy-bos-ai-seoul-prod"
  role = aws_iam_role.nginx.name

  tags = merge(local.llm_gateway_tags, {
    Name = "profile-nginx-proxy-bos-ai-seoul-prod"
  })
}

data "aws_iam_policy_document" "nginx_cloudwatch" {
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

resource "aws_iam_role_policy" "nginx_cloudwatch" {
  name   = "nginx-cloudwatch-logs"
  role   = aws_iam_role.nginx.id
  policy = data.aws_iam_policy_document.nginx_cloudwatch.json
}

resource "aws_iam_role_policy_attachment" "nginx_ssm" {
  role       = aws_iam_role.nginx.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# =============================================================================
# Security Group
# =============================================================================

resource "aws_security_group" "nginx" {
  provider    = aws.seoul
  name        = "nginx-proxy-bos-ai-seoul-prod"
  description = "Security group for Nginx Reverse Proxy - LLM Gateway"
  vpc_id      = "vpc-0a118e1bf21d0c057"

  tags = merge(local.llm_gateway_tags, {
    Name = "sg-nginx-proxy-bos-ai-seoul-prod"
  })
}

# Inbound HTTPS from on-prem via VPN/TGW
resource "aws_security_group_rule" "nginx_inbound_https" {
  provider          = aws.seoul
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["192.128.0.0/16"]
  security_group_id = aws_security_group.nginx.id
  description       = "HTTPS from on-prem via VPN/TGW"
}

# Outbound HTTPS to API Gateway VPC Endpoint
resource "aws_security_group_rule" "nginx_outbound_apigw" {
  provider          = aws.seoul
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["10.10.0.0/16"]
  security_group_id = aws_security_group.nginx.id
  description       = "HTTPS to API Gateway VPC Endpoint (10.10.1.21/10.10.2.75)"
}

# =============================================================================
# Launch Template + EC2
# =============================================================================

resource "aws_launch_template" "nginx" {
  provider    = aws.seoul
  name        = "lt-nginx-proxy-bos-ai-seoul-prod"
  description = "Nginx Reverse Proxy for LLM Gateway"

  image_id      = data.aws_ami.al2023_nginx.id
  instance_type = "t3.micro"

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  iam_instance_profile {
    name = aws_iam_instance_profile.nginx.name
  }

  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [aws_security_group.nginx.id]
    subnet_id                   = "subnet-0ec356f8f9af0ffca"
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 30
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  user_data = base64encode(templatefile(
    "${path.module}/templates/nginx-user-data.sh.tpl",
    {
      apigw_host = "r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com"
    }
  ))

  tag_specifications {
    resource_type = "instance"
    tags = merge(local.llm_gateway_tags, {
      Name = "ec2-nginx-proxy-bos-ai-seoul-prod"
    })
  }

  tags = merge(local.llm_gateway_tags, {
    Name = "lt-nginx-proxy-bos-ai-seoul-prod"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_instance" "nginx" {
  provider = aws.seoul

  launch_template {
    id      = aws_launch_template.nginx.id
    version = aws_launch_template.nginx.latest_version
  }

  tags = merge(local.llm_gateway_tags, {
    Name = "ec2-nginx-proxy-bos-ai-seoul-prod"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# CloudWatch
# =============================================================================

resource "aws_cloudwatch_log_group" "nginx" {
  provider          = aws.seoul
  name              = "/llm-gateway/nginx"
  retention_in_days = 30

  tags = merge(local.llm_gateway_tags, {
    Name = "log-nginx-proxy-bos-ai-seoul-prod"
  })
}

resource "aws_cloudwatch_metric_alarm" "nginx_cpu_high" {
  provider            = aws.seoul
  alarm_name          = "nginx-cpu-utilization-high"
  alarm_description   = "Nginx Proxy CPU > 80% for 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    InstanceId = aws_instance.nginx.id
  }

  alarm_actions = [aws_sns_topic.llm_gateway_alerts.arn]
  ok_actions    = [aws_sns_topic.llm_gateway_alerts.arn]

  tags = merge(local.llm_gateway_tags, {
    Name = "alarm-nginx-cpu-bos-ai-seoul-prod"
  })
}

# =============================================================================
# Outputs
# =============================================================================

output "nginx_proxy_private_ip" {
  description = "Nginx Proxy EC2 private IP — 사내 BIND에서 llm/mcp A 레코드로 등록 필요"
  value       = aws_instance.nginx.private_ip
}
