# ============================================================================
# QuickSight VPC Connection 라우팅 검증
# Requirements: 4.6, 7.1, 7.3
#
# Quick VPC Connection ENI는 Seoul VPC Private 서브넷에 배치됩니다.
# Virginia(10.20.0.0/16) 트래픽은 Seoul VPC 라우팅 테이블의
# VPC Peering 경로를 통해 자동 전달됩니다.
#
# 배포 전 확인 사항:
#   Seoul VPC Private 서브넷 라우팅 테이블에
#   10.20.0.0/16 -> pcx-xxx (VPC Peering) 경로가 존재해야 합니다.
#
# 확인 명령:
#   aws ec2 describe-route-tables \
#     --filters "Name=vpc-id,Values=<frontend-vpc-id>" \
#     --query "RouteTables[*].Routes[?DestinationCidrBlock=='10.20.0.0/16']"
# ============================================================================

data "aws_route_tables" "frontend_private" {
  provider = aws.seoul

  filter {
    name   = "vpc-id"
    values = [module.vpc_frontend.vpc_id]
  }

  filter {
    name   = "tag:Layer"
    values = ["network"]
  }
}

check "quicksight_virginia_route_exists" {
  assert {
    condition     = length(data.aws_route_tables.frontend_private.ids) > 0
    error_message = "Seoul VPC Private 라우팅 테이블을 찾을 수 없습니다. Quick VPC Connection ENI 배포 전 10.20.0.0/16 -> VPC Peering 경로가 존재하는지 확인하세요."
  }
}
