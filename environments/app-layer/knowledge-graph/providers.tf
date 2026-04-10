# Provider Configuration for App Layer - Knowledge Graph (Neptune)
# Neptune은 Seoul 리전(ap-northeast-2) Frontend VPC에 배포
#
# Requirements: 16.4, 16.15

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}

# Seoul Provider — Neptune 클러스터가 배포되는 기본 리전
provider "aws" {
  region = "ap-northeast-2"

  default_tags {
    tags = local.common_tags
  }
}

# US East Provider — Cross-Region 참조용
provider "aws" {
  alias  = "us_east"
  region = "us-east-1"

  default_tags {
    tags = local.common_tags
  }
}
