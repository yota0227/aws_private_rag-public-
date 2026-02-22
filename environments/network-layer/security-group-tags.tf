# Security Group 태그 업데이트
# BOS-AI VPC 통합 마이그레이션 - Phase 2

# 기존 Security Group 태그 업데이트
resource "aws_ec2_tag" "sg_logclt" {
  resource_id = "sg-099b53b7cef326c6f"
  key         = "Name"
  value       = "sec-logclt-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "sg_logclt_project" {
  resource_id = "sg-099b53b7cef326c6f"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_logclt_environment" {
  resource_id = "sg-099b53b7cef326c6f"
  key         = "Environment"
  value       = "prod"
}

resource "aws_ec2_tag" "sg_obe" {
  resource_id = "sg-0f0beea8e79df8d83"
  key         = "Name"
  value       = "sec-obe-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "sg_obe_project" {
  resource_id = "sg-0f0beea8e79df8d83"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_obe_environment" {
  resource_id = "sg-0f0beea8e79df8d83"
  key         = "Environment"
  value       = "prod"
}

resource "aws_ec2_tag" "sg_gra" {
  resource_id = "sg-01270ffd96809e5d1"
  key         = "Name"
  value       = "sec-gra-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "sg_gra_project" {
  resource_id = "sg-01270ffd96809e5d1"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_gra_environment" {
  resource_id = "sg-01270ffd96809e5d1"
  key         = "Environment"
  value       = "prod"
}

resource "aws_ec2_tag" "sg_ec2_public_ssh" {
  resource_id = "sg-09aad67a4198f3612"
  key         = "Name"
  value       = "sec-ec2-public-ssh-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "sg_ec2_public_ssh_project" {
  resource_id = "sg-09aad67a4198f3612"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_ec2_public_ssh_environment" {
  resource_id = "sg-09aad67a4198f3612"
  key         = "Environment"
  value       = "prod"
}

resource "aws_ec2_tag" "sg_vpce_firehose_old" {
  resource_id = "sg-033f49c3a260c897d"
  key         = "Name"
  value       = "sec-vpce-firehose-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "sg_vpce_firehose_old_project" {
  resource_id = "sg-033f49c3a260c897d"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_vpce_firehose_old_environment" {
  resource_id = "sg-033f49c3a260c897d"
  key         = "Environment"
  value       = "prod"
}

resource "aws_ec2_tag" "sg_ec2test" {
  resource_id = "sg-02433019091ff27f6"
  key         = "Name"
  value       = "sec-ec2test-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "sg_ec2test_project" {
  resource_id = "sg-02433019091ff27f6"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_ec2test_environment" {
  resource_id = "sg-02433019091ff27f6"
  key         = "Environment"
  value       = "prod"
}

resource "aws_ec2_tag" "sg_os_open_mon" {
  resource_id = "sg-0cba7103943a2ee68"
  key         = "Name"
  value       = "sec-os-open-mon-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "sg_os_open_mon_project" {
  resource_id = "sg-0cba7103943a2ee68"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_os_open_mon_environment" {
  resource_id = "sg-0cba7103943a2ee68"
  key         = "Environment"
  value       = "prod"
}

resource "aws_ec2_tag" "sg_app" {
  resource_id = "sg-0e9293aa650e98d1d"
  key         = "Name"
  value       = "sec-app-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "sg_app_project" {
  resource_id = "sg-0e9293aa650e98d1d"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_app_environment" {
  resource_id = "sg-0e9293aa650e98d1d"
  key         = "Environment"
  value       = "prod"
}

resource "aws_ec2_tag" "sg_alb" {
  resource_id = "sg-0a2bc263f0ef7fc8c"
  key         = "Name"
  value       = "sec-alb-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "sg_alb_project" {
  resource_id = "sg-0a2bc263f0ef7fc8c"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_alb_environment" {
  resource_id = "sg-0a2bc263f0ef7fc8c"
  key         = "Environment"
  value       = "prod"
}

resource "aws_ec2_tag" "sg_ibe" {
  resource_id = "sg-08778afa477a9ded9"
  key         = "Name"
  value       = "sec-ibe-bos-ai-seoul-prod-01"
}

resource "aws_ec2_tag" "sg_ibe_project" {
  resource_id = "sg-08778afa477a9ded9"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_ibe_environment" {
  resource_id = "sg-08778afa477a9ded9"
  key         = "Environment"
  value       = "prod"
}

resource "aws_ec2_tag" "sg_vpce_firehose_new" {
  resource_id = "sg-09e746f44d5602a85"
  key         = "Name"
  value       = "sec-vpce-firehose-bos-ai-seoul-prod-02"
}

resource "aws_ec2_tag" "sg_vpce_firehose_new_project" {
  resource_id = "sg-09e746f44d5602a85"
  key         = "Project"
  value       = "BOS-AI"
}

resource "aws_ec2_tag" "sg_vpce_firehose_new_environment" {
  resource_id = "sg-09e746f44d5602a85"
  key         = "Environment"
  value       = "prod"
}

# 새로 생성된 Security Group은 이미 올바른 태그를 가지고 있음
# - opensearch-bos-ai-seoul-prod (sg-0ac6a858ab64c545c)
# - vpc-endpoints-bos-ai-seoul-prod (sg-07de2e5d4150a05d8)
