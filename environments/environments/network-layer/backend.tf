# Backend Configuration for Network Layer
# This configuration uses the S3 backend created in environments/global/backend
# State file is encrypted and versioned with DynamoDB locking for concurrent access prevention
#
# Requirements: 6.1, 6.2, 6.3, 6.4, 6.5

terraform {
  backend "s3" {
    bucket         = "bos-ai-terraform-state"
    key            = "network-layer/terraform.tfstate"
    region         = "ap-northeast-2"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"

    # Optional: Uncomment to use KMS encryption for state file
    # kms_key_id = "arn:aws:kms:ap-northeast-2:ACCOUNT_ID:key/KEY_ID"
  }
}
