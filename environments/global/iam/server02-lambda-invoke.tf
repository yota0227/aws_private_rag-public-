# ============================================================================
# server02 MCP bridge용 IAM 사용자 — Lambda direct invoke 전용
#
# Purpose: server02(온프레미스 개발 서버)의 MCP bridge(server.js)가
#          lambda-rtl-parser-seoul-dev를 직접 invoke할 수 있도록 최소 권한 부여.
#          EC2 인스턴스 프로파일이 없는 온프레미스 환경에서 임시 방편으로 사용.
#
# Access Key는 server02의 ~/.aws/credentials에 등록한다.
# 운영(EC2 인스턴스 프로파일) 방식과 동일한 결과를 낸다.
# ============================================================================

resource "aws_iam_user" "server02_mcp_dev" {
  provider = aws
  name     = "server02-mcp-dev"
  path     = "/bos-ai/"

  tags = {
    Project     = "BOS-AI"
    Environment = "dev"
    ManagedBy   = "Terraform"
    Purpose     = "server02 MCP bridge Lambda invoke"
  }
}

# 최소 권한 정책: lambda-rtl-parser-seoul-dev invoke만 허용
resource "aws_iam_user_policy" "server02_mcp_dev_lambda" {
  provider = aws
  name     = "server02-mcp-dev-lambda-invoke"
  user     = aws_iam_user.server02_mcp_dev.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RTLParserLambdaInvoke"
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          "arn:aws:lambda:ap-northeast-2:533335672315:function:lambda-rtl-parser-seoul-dev"
        ]
      }
    ]
  })
}

# Access Key 생성 (server02 ~/.aws/credentials에 등록할 값)
resource "aws_iam_access_key" "server02_mcp_dev" {
  provider = aws
  user     = aws_iam_user.server02_mcp_dev.name
}

# ============================================================================
# Outputs — terraform apply 후 이 값을 server02에 등록
# terraform output server02_access_key_id
# terraform output server02_secret_access_key (sensitive)
# ============================================================================

output "server02_access_key_id" {
  description = "server02 ~/.aws/credentials에 등록할 AWS Access Key ID"
  value       = aws_iam_access_key.server02_mcp_dev.id
}

output "server02_secret_access_key" {
  description = "server02 ~/.aws/credentials에 등록할 AWS Secret Access Key"
  value       = aws_iam_access_key.server02_mcp_dev.secret
  sensitive   = true
}
