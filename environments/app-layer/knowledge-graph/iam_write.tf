# Neptune Write IAM Policy — RTL Parser Lambda (관계 적재용)
# Neptune 배포 후 Lambda Role에 정책 추가
# Requirements: 16.4
#
# NOTE: Neptune cluster ARN은 배포 후 확인하여 수동 또는 후속 apply로 적용
# 현재는 placeholder — terraform apply 시 Neptune endpoint 확인 후 활성화

# RTL Parser Lambda role name 추출 (ARN에서)
locals {
  rtl_parser_role_name = element(
    split("/", data.terraform_remote_state.bedrock_rag.outputs.rtl_parser_lambda_role_arn),
    length(split("/", data.terraform_remote_state.bedrock_rag.outputs.rtl_parser_lambda_role_arn)) - 1
  )

  lambda_handler_role_name = element(
    split("/", data.terraform_remote_state.bedrock_rag.outputs.lambda_role_arn),
    length(split("/", data.terraform_remote_state.bedrock_rag.outputs.lambda_role_arn)) - 1
  )
}

# RTL Parser — Write + Read
resource "aws_iam_role_policy" "neptune_write_policy" {
  name   = "neptune-write-query"
  role   = local.rtl_parser_role_name
  policy = data.aws_iam_policy_document.neptune_write.json
}

data "aws_iam_policy_document" "neptune_write" {
  statement {
    effect  = "Allow"
    actions = ["neptune-db:WriteDataViaQuery", "neptune-db:ReadDataViaQuery"]
    resources = [
      "arn:aws:neptune-db:us-east-1:533335672315:${module.neptune.neptune_cluster_id}/*"
    ]
  }
}

# Lambda Handler (document-processor) — Read Only
resource "aws_iam_role_policy" "neptune_readonly_policy" {
  name   = "neptune-readonly-query"
  role   = local.lambda_handler_role_name
  policy = data.aws_iam_policy_document.neptune_readonly.json
}

data "aws_iam_policy_document" "neptune_readonly" {
  statement {
    effect  = "Allow"
    actions = ["neptune-db:ReadDataViaQuery"]
    resources = [
      "arn:aws:neptune-db:us-east-1:533335672315:${module.neptune.neptune_cluster_id}/*"
    ]
  }
}
