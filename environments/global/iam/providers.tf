terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# IAM Identity Center는 us-east-1(global) 리전에서 관리
provider "aws" {
  region = "us-east-1"
}
