terraform {
  backend "s3" {
    bucket         = "bos-ai-terraform-state"
    key            = "app-layer/quicksight/terraform.tfstate"
    region         = "ap-northeast-2"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}
