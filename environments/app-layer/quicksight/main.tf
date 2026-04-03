# ============================================================================
# QuickSight App Layer - 계정 참조 및 VPC Connection
# Requirements: 2.1, 2.2, 2.5, 4.1, 4.8
#
# Note: QuickSight 계정은 이미 활성화됨 (Edition: ENTERPRISE)
#       data source로 참조만 하고 Terraform으로 생성하지 않음
#       AuthenticationType 변경(IDENTITY_POOL -> IAM_IDENTITY_CENTER)은
#       별도 마이그레이션 계획 후 콘솔에서 수동 진행
# ============================================================================

# Note: QuickSight 계정은 이미 활성화됨 (Edition: ENTERPRISE, bossemi)
# aws_quicksight_account_subscription data source 미지원 - account_id로 직접 참조

# ──────────────────────────────────────────────
# QuickSight 서비스 IAM 역할
# S3, OpenSearch 접근용 (VPC Connection 생성에도 필요)
# ──────────────────────────────────────────────
resource "aws_iam_role" "quicksight_service" {
  name        = "role-quicksight-service-bos-ai-seoul-prod"
  description = "QuickSight 서비스 역할 - S3/OpenSearch 데이터 소스 접근"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "quicksight.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(local.common_tags, {
    Name = "role-quicksight-service-bos-ai-seoul-prod"
  })
}

resource "aws_iam_role_policy" "quicksight_service_policy" {
  name = "quicksight-service-policy"
  role = aws_iam_role.quicksight_service.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "QuickSightDataS3Access"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.quicksight_data.arn,
          "${aws_s3_bucket.quicksight_data.arn}/*"
        ]
      },
      {
        Sid    = "QuickSightRAGS3ReadOnly"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::bos-ai-documents-seoul-v2",
          "arn:aws:s3:::bos-ai-documents-seoul-v2/*"
        ]
      },
      {
        Sid      = "QuickSightOpenSearchReadOnly"
        Effect   = "Allow"
        Action   = ["aoss:APIAccessAll"]
        Resource = "arn:aws:aoss:us-east-1:${local.account_id}:collection/*"
      },
      {
        Sid    = "QuickSightVPCConnectionAccess"
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups"
        ]
        Resource = "*"
      }
    ]
  })
}

# ──────────────────────────────────────────────
# QuickSight VPC Connection
# Seoul VPC Private 서브넷에 ENI 배치
# Virginia 직접 접근 차단 - VPC Peering 라우팅 경유
# ──────────────────────────────────────────────
resource "aws_quicksight_vpc_connection" "main" {
  provider          = aws.seoul
  vpc_connection_id = "bos-ai-quicksight-vpc-conn-prod"
  name              = "bos-ai-quicksight-vpc-conn-prod"
  role_arn          = aws_iam_role.quicksight_service.arn
  security_group_ids = [local.qs_vpc_conn_sg_id]
  subnet_ids        = local.frontend_subnet_ids

  lifecycle {
    postcondition {
      condition     = length(self.subnet_ids) > 0
      error_message = "QuickSight VPC Connection 생성 실패: Seoul VPC Private 서브넷이 없습니다. 서브넷 CIDR 확장 또는 대체 서브넷 사용을 검토하세요."
    }
  }

  tags = merge(local.common_tags, {
    Name = "bos-ai-quicksight-vpc-conn-prod"
  })
}

# ──────────────────────────────────────────────
# Outputs
# ──────────────────────────────────────────────
output "quicksight_vpc_connection_id" {
  description = "QuickSight VPC Connection ID"
  value       = aws_quicksight_vpc_connection.main.vpc_connection_id
}

output "quicksight_service_role_arn" {
  description = "QuickSight 서비스 역할 ARN"
  value       = aws_iam_role.quicksight_service.arn
}
