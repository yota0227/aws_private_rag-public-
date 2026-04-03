# ============================================================================
# RBAC Pipeline GROUP_MAP 확장 - TODO
# Requirements: 2.6, 2.7, 2.8, 2.9
#
# enterprise-rbac-pipeline 스펙 구현 시 아래 항목을 추가해야 합니다:
#
# 1. Provisioner Lambda GROUP_MAP에 QuickSight 서비스 항목 추가:
#    "quicksight-admin":  "<qs_admin_group_id>",
#    "quicksight-author": "<qs_author_group_id>",
#    "quicksight-viewer": "<qs_viewer_group_id>",
#
# 2. 그룹 ID 확인:
#    terraform output -state=<global-iam-state> qs_admin_group_id
# ============================================================================
