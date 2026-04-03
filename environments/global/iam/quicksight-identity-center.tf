# QuickSight IAM Identity Center Groups
# Requirements: 2.6, 2.7, 2.8, 2.9
#
# IAM Identity Center를 통한 QuickSight 사용자 자동 프로비저닝
# RBAC Pipeline GROUP_MAP 연계:
#   "quicksight-admin"  -> QS_Admin_Users  -> Quick ADMIN
#   "quicksight-author" -> QS_Author_Users -> Quick AUTHOR
#   "quicksight-viewer" -> QS_Viewer_Users -> Quick READER

data "aws_ssoadmin_instances" "main" {}

# ──────────────────────────────────────────────
# IAM Identity Center 그룹 3개
# ──────────────────────────────────────────────
resource "aws_identitystore_group" "qs_admin" {
  identity_store_id = tolist(data.aws_ssoadmin_instances.main.identity_store_ids)[0]
  display_name      = "QS_Admin_Users"
  description       = "QuickSight 관리자 그룹 - 계정/사용자/데이터소스 관리"
}

resource "aws_identitystore_group" "qs_author" {
  identity_store_id = tolist(data.aws_ssoadmin_instances.main.identity_store_ids)[0]
  display_name      = "QS_Author_Users"
  description       = "QuickSight 작성자 그룹 - 대시보드 생성/편집"
}

resource "aws_identitystore_group" "qs_viewer" {
  identity_store_id = tolist(data.aws_ssoadmin_instances.main.identity_store_ids)[0]
  display_name      = "QS_Viewer_Users"
  description       = "QuickSight 뷰어 그룹 - 대시보드 조회 전용"
}

# ──────────────────────────────────────────────
# Outputs - RBAC Pipeline GROUP_MAP 확장 시 참조
# ──────────────────────────────────────────────
output "qs_admin_group_id" {
  description = "QS_Admin_Users Identity Center 그룹 ID (RBAC Pipeline GROUP_MAP용)"
  value       = aws_identitystore_group.qs_admin.group_id
}

output "qs_author_group_id" {
  description = "QS_Author_Users Identity Center 그룹 ID (RBAC Pipeline GROUP_MAP용)"
  value       = aws_identitystore_group.qs_author.group_id
}

output "qs_viewer_group_id" {
  description = "QS_Viewer_Users Identity Center 그룹 ID (RBAC Pipeline GROUP_MAP용)"
  value       = aws_identitystore_group.qs_viewer.group_id
}

output "quicksight_iam_role_arns" {
  description = "QuickSight IAM 역할 ARN 맵"
  value = {
    admin  = aws_iam_role.quicksight_admin.arn
    author = aws_iam_role.quicksight_author.arn
    viewer = aws_iam_role.quicksight_viewer.arn
  }
}
