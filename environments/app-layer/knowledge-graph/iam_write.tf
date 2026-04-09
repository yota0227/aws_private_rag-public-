# Neptune Write IAM Role — RTL Parser Lambda (관계 적재용)
# RTL Parser Lambda가 파싱 결과를 Neptune에 노드/엣지로 적재
# 기존 RTL Parser Lambda IAM Role에 Write 정책 추가
#
# Requirements: 16.4

resource "aws_iam_role_policy" "neptune_write_policy" {
  name   = "neptune-write-query"
  role   = var.rtl_parser_lambda_role_name
  policy = data.aws_iam_policy_document.neptune_write.json
}

data "aws_iam_policy_document" "neptune_write" {
  statement {
    effect  = "Allow"
    actions = ["neptune-db:WriteDataViaQuery"]
    resources = [
      "arn:aws:neptune-db:ap-northeast-2:*:${module.neptune.neptune_cluster_id}/*"
    ]
  }
}
