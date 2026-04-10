# Backend Configuration for App Layer - Knowledge Graph (Neptune)
# S3 backend으로 상태 관리, DynamoDB로 동시 접근 방지
#
# Requirements: 16.4, 16.5, 16.15

terraform {
  backend "s3" {
    bucket         = "bos-ai-terraform-state"
    key            = "app-layer/knowledge-graph/terraform.tfstate"
    region         = "ap-northeast-2"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}
