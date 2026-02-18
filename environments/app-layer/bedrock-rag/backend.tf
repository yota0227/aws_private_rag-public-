# Backend Configuration for App Layer - Bedrock RAG
# This configuration uses the S3 backend created in environments/global/backend
#
# Requirements: 6.1, 6.2, 6.3, 6.4

terraform {
  backend "s3" {
    bucket         = "bos-ai-terraform-state"
    key            = "app-layer/bedrock-rag/terraform.tfstate"
    region         = "ap-northeast-2"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
    
    # Optional: Uncomment to use KMS encryption
    # kms_key_id = "arn:aws:kms:ap-northeast-2:ACCOUNT_ID:key/KEY_ID"
  }
}
