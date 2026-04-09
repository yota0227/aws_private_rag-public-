# Remote State 참조 — Network Layer 및 Bedrock RAG Layer
# VPC ID, Subnet ID, Security Group ID 등을 동적으로 참조
#
# Requirements: 16.4, 16.15

# Network Layer 상태 참조 — VPC, Subnet, Security Group 정보
data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "bos-ai-terraform-state"
    key    = "network-layer/terraform.tfstate"
    region = "ap-northeast-2"
  }
}

# Bedrock RAG Layer 상태 참조 — KMS 키, Lambda 관련 정보
data "terraform_remote_state" "bedrock_rag" {
  backend = "s3"
  config = {
    bucket = "bos-ai-terraform-state"
    key    = "app-layer/bedrock-rag/terraform.tfstate"
    region = "ap-northeast-2"
  }
}
