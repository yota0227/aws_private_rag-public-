# Provider Configuration for App Layer - Knowledge Graph (Neptune)
# Neptune은 Virginia 리전(us-east-1) Backend VPC에 배포
# Lambda(Seoul)는 VPC Peering 경유로 Neptune에 접근
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

# Virginia Provider — Neptune 클러스터가 배포되는 기본 리전
provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = local.common_tags
  }
}

# Seoul Provider — Lambda SG egress 규칙 추가용
provider "aws" {
  alias  = "seoul"
  region = "ap-northeast-2"

  default_tags {
    tags = local.common_tags
  }
}
