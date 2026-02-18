# Provider Configuration for App Layer - Bedrock RAG
# This configuration uses the US East region for AI workload resources
#
# Requirements: 9.1, 9.2, 9.3

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 4.0.0"
    }
  }
}

# US East Provider for AI Workload
provider "aws" {
  region = var.us_region

  default_tags {
    tags = local.common_tags
  }
}
