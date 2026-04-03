# QuickSight IAM Roles
# Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
#
# 공통 접근 조건:
#   - aws:SourceIp: 온프레미스(192.128.0.0/16) + Seoul VPC(10.10.0.0/16)
# Note: aws:sourceVpce 조건은 network-layer VPC Endpoint 배포 후 추가

locals {
  quicksight_tags = {
    Project     = "BOS-AI"
    Environment = "prod"
    ManagedBy   = "Terraform"
    Layer       = "global"
    Service     = "quicksight"
  }

  allowed_ip_ranges = [
    "192.128.0.0/16",
    "10.10.0.0/16"
  ]
}

# ──────────────────────────────────────────────
# 1. QuickSight Admin 역할
# ──────────────────────────────────────────────
resource "aws_iam_role" "quicksight_admin" {
  name        = "role-quicksight-admin-bos-ai-seoul-prod"
  description = "QuickSight Admin - 계정/사용자/데이터소스 관리"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "quicksight.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.quicksight_tags, {
    Name = "role-quicksight-admin-bos-ai-seoul-prod"
    Role = "admin"
  })
}

resource "aws_iam_role_policy" "quicksight_admin_policy" {
  name = "quicksight-admin-policy"
  role = aws_iam_role.quicksight_admin.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "QuickSightAdminAccess"
        Effect   = "Allow"
        Action   = ["quicksight:*"]
        Resource = "*"
        Condition = {
          IpAddress = {
            "aws:SourceIp" = local.allowed_ip_ranges
          }
        }
      }
    ]
  })
}

# ──────────────────────────────────────────────
# 2. QuickSight Author 역할
# ──────────────────────────────────────────────
resource "aws_iam_role" "quicksight_author" {
  name        = "role-quicksight-author-bos-ai-seoul-prod"
  description = "QuickSight Author - 대시보드 생성/편집, 데이터셋 조회"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "quicksight.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.quicksight_tags, {
    Name = "role-quicksight-author-bos-ai-seoul-prod"
    Role = "author"
  })
}

resource "aws_iam_role_policy" "quicksight_author_policy" {
  name = "quicksight-author-policy"
  role = aws_iam_role.quicksight_author.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "QuickSightAuthorAccess"
        Effect = "Allow"
        Action = [
          "quicksight:DescribeDashboard",
          "quicksight:ListDashboards",
          "quicksight:GetDashboardEmbedUrl",
          "quicksight:CreateDashboard",
          "quicksight:UpdateDashboard",
          "quicksight:DeleteDashboard",
          "quicksight:DescribeDataSet",
          "quicksight:ListDataSets",
          "quicksight:CreateDataSet",
          "quicksight:UpdateDataSet",
          "quicksight:DescribeAnalysis",
          "quicksight:ListAnalyses",
          "quicksight:CreateAnalysis",
          "quicksight:UpdateAnalysis",
          "quicksight:DescribeTemplate",
          "quicksight:ListTemplates",
          "quicksight:CreateIngestion",
          "quicksight:DescribeIngestion",
          "quicksight:ListIngestions"
        ]
        Resource = "*"
        Condition = {
          IpAddress = {
            "aws:SourceIp" = local.allowed_ip_ranges
          }
        }
      }
    ]
  })
}

# ──────────────────────────────────────────────
# 3. QuickSight Viewer 역할
# ──────────────────────────────────────────────
resource "aws_iam_role" "quicksight_viewer" {
  name        = "role-quicksight-viewer-bos-ai-seoul-prod"
  description = "QuickSight Viewer - 대시보드 조회 전용"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "quicksight.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(local.quicksight_tags, {
    Name = "role-quicksight-viewer-bos-ai-seoul-prod"
    Role = "viewer"
  })
}

resource "aws_iam_role_policy" "quicksight_viewer_policy" {
  name = "quicksight-viewer-policy"
  role = aws_iam_role.quicksight_viewer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "QuickSightViewerAccess"
        Effect = "Allow"
        Action = [
          "quicksight:DescribeDashboard",
          "quicksight:ListDashboards",
          "quicksight:GetDashboardEmbedUrl",
          "quicksight:GetSessionEmbedUrl"
        ]
        Resource = "*"
        Condition = {
          IpAddress = {
            "aws:SourceIp" = local.allowed_ip_ranges
          }
        }
      }
    ]
  })
}
