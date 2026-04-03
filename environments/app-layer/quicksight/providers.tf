terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  alias  = "seoul"
  region = "ap-northeast-2"

  default_tags {
    tags = {
      Project     = "BOS-AI"
      Environment = "prod"
      ManagedBy   = "Terraform"
      Layer       = "app"
      Service     = "quicksight"
    }
  }
}
