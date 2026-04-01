#!/bin/bash
# 네이밍 변경 검증 스크립트
# Logging Pipeline VPC (vpc-066c464f9c750ee9e, 10.200.0.0/16) 태그 검증

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================="
echo "네이밍 변경 검증"
echo "========================================="
echo ""

# VPC 태그 확인 (기대값: vpc-bos-logging-seoul-prod-01)
echo -e "${YELLOW}[1] VPC 태그 확인${NC}"
ACTUAL_NAME=$(aws ec2 describe-vpcs --vpc-ids vpc-066c464f9c750ee9e --region ap-northeast-2 \
  --query 'Vpcs[0].Tags[?Key==`Name`].Value' --output text)
echo "현재 이름: $ACTUAL_NAME"
if [ "$ACTUAL_NAME" == "vpc-bos-logging-seoul-prod-01" ]; then
  echo -e "${GREEN}✓ 이름 정상${NC}"
else
  echo -e "${RED}✗ 이름 불일치 (기대: vpc-bos-logging-seoul-prod-01)${NC}"
fi
echo ""

# 서브넷 태그 확인
echo -e "${YELLOW}[2] 서브넷 태그 확인${NC}"
aws ec2 describe-subnets --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --query 'Subnets[*].[SubnetId,Tags[?Key==`Name`].Value|[0]]' --output table
echo ""

# Security Group 태그 확인
echo -e "${YELLOW}[3] Security Group 태그 확인${NC}"
aws ec2 describe-security-groups --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --query 'SecurityGroups[*].[GroupId,Tags[?Key==`Name`].Value|[0],Tags[?Key==`Project`].Value|[0]]' \
  --output table
echo ""

# Route53 Resolver 엔드포인트 확인
echo -e "${YELLOW}[4] Route53 Resolver 엔드포인트 확인${NC}"
aws route53resolver list-resolver-endpoints --region ap-northeast-2 \
  --query 'ResolverEndpoints[*].[Id,Name]' --output table
echo ""

# Route Table 태그 확인
echo -e "${YELLOW}[5] Route Table 태그 확인${NC}"
aws ec2 describe-route-tables --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --query 'RouteTables[*].[RouteTableId,Tags[?Key==`Name`].Value|[0]]' --output table
echo ""

# NAT Gateway 태그 확인
echo -e "${YELLOW}[6] NAT Gateway 태그 확인${NC}"
aws ec2 describe-nat-gateways --region ap-northeast-2 \
  --filter "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --query 'NatGateways[*].[NatGatewayId,Tags[?Key==`Name`].Value|[0]]' --output table
echo ""

# Internet Gateway 태그 확인
echo -e "${YELLOW}[7] Internet Gateway 태그 확인${NC}"
aws ec2 describe-internet-gateways --region ap-northeast-2 \
  --filters "Name=attachment.vpc-id,Values=vpc-066c464f9c750ee9e" \
  --query 'InternetGateways[*].[InternetGatewayId,Tags[?Key==`Name`].Value|[0]]' --output table
echo ""

echo -e "${GREEN}✓ 네이밍 변경 검증 완료!${NC}"
