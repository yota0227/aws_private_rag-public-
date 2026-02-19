# Provider Configuration for Network Layer
# Configures multi-region providers for Seoul and US East regions
#
# Requirements: 9.1

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}

# Seoul Region Provider (ap-northeast-2)
# Used for Seoul VPC and VPN integration
provider "aws" {
  alias  = "seoul"
  region = "ap-northeast-2"

  default_tags {
    tags = {
      Project   = "BOS-AI-RAG"
      ManagedBy = "Terraform"
      Layer     = "network"
      Region    = "ap-northeast-2"
    }
  }
}

# US East Region Provider (us-east-1)
# Used for US VPC and AI workload infrastructure
provider "aws" {
  alias  = "us_east"
  region = "us-east-1"

  default_tags {
    tags = {
      Project   = "BOS-AI-RAG"
      ManagedBy = "Terraform"
      Layer     = "network"
      Region    = "us-east-1"
    }
  }
}
