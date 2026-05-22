# Qdrant Vector DB — EC2 Single Instance (Virginia Backend VPC)
# Replaces AOSS for RTL knowledge base vector search
# Seoul Lambda → VPC Peering → Qdrant EC2 (port 6333 REST, 6334 gRPC)
#
# Future: Multi-AZ cluster expansion (3-node Qdrant cluster)

# Latest Amazon Linux 2023 AMI
data "aws_ami" "al2023" {
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

# Security Group for Qdrant EC2
resource "aws_security_group" "qdrant" {
  name        = "qdrant-bos-ai-${var.environment}"
  description = "Qdrant Vector DB - allow access from Seoul VPC via VPC Peering"
  vpc_id      = local.us_vpc_id

  # Qdrant REST API (6333) from Seoul VPC
  ingress {
    description = "Qdrant REST from Seoul VPC (VPC Peering)"
    from_port   = 6333
    to_port     = 6333
    protocol    = "tcp"
    cidr_blocks = ["10.10.0.0/16"]
  }

  # Qdrant gRPC (6334) from Seoul VPC
  ingress {
    description = "Qdrant gRPC from Seoul VPC (VPC Peering)"
    from_port   = 6334
    to_port     = 6334
    protocol    = "tcp"
    cidr_blocks = ["10.10.0.0/16"]
  }

  # Qdrant REST/gRPC from Virginia VPC (local access)
  ingress {
    description = "Qdrant from Virginia VPC (local)"
    from_port   = 6333
    to_port     = 6334
    protocol    = "tcp"
    cidr_blocks = ["10.20.0.0/16"]
  }

  # HTTPS outbound (for SSM agent)
  egress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = []
    cidr_blocks     = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name    = "sg-qdrant-bos-ai-${var.environment}"
    Purpose = "Qdrant Vector DB"
  })
}

# IAM Role for Qdrant EC2 (SSM access + S3 for binary download)
resource "aws_iam_role" "qdrant" {
  name = "role-qdrant-ec2-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })

  tags = merge(local.common_tags, {
    Name = "role-qdrant-ec2-${var.environment}"
  })
}

resource "aws_iam_role_policy_attachment" "qdrant_ssm" {
  role       = aws_iam_role.qdrant.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# S3 read access for Qdrant binary download
resource "aws_iam_role_policy" "qdrant_s3" {
  name = "qdrant-s3-read"
  role = aws_iam_role.qdrant.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = ["arn:aws:s3:::bos-ai-rtl-src-533335672315/tools/*"]
    }]
  })
}

resource "aws_iam_instance_profile" "qdrant" {
  name = "profile-qdrant-ec2-${var.environment}"
  role = aws_iam_role.qdrant.name
}

# Qdrant EC2 Instance
resource "aws_instance" "qdrant" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = "r6i.large"
  subnet_id              = local.us_private_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.qdrant.id]
  iam_instance_profile   = aws_iam_instance_profile.qdrant.name

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 100
    iops                  = 3000
    throughput            = 125
    encrypted             = true
    kms_key_id            = module.kms.key_arn
    delete_on_termination = true
  }

  # User data: Qdrant binary is pre-uploaded to S3 (no internet needed)
  # Upload first: aws s3 cp qdrant-x86_64-unknown-linux-musl.tar.gz s3://bos-ai-rtl-src-533335672315/tools/
  user_data = base64encode(file("${path.module}/qdrant-userdata.sh"))

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"  # IMDSv2 only
  }

  tags = merge(local.common_tags, {
    Name    = "ec2-qdrant-bos-ai-${var.environment}"
    Purpose = "Qdrant Vector DB for RTL Knowledge Base"
  })

  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

# Outputs
output "qdrant_instance_id" {
  description = "Qdrant EC2 instance ID"
  value       = aws_instance.qdrant.id
}

output "qdrant_private_ip" {
  description = "Qdrant EC2 private IP"
  value       = aws_instance.qdrant.private_ip
}

output "qdrant_endpoint" {
  description = "Qdrant REST API endpoint (use from Seoul Lambda via VPC Peering)"
  value       = "http://${aws_instance.qdrant.private_ip}:6333"
}
