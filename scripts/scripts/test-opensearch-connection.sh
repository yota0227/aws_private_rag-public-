#!/bin/bash
# OpenSearch Serverless 연결 테스트 스크립트

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================="
echo "OpenSearch Serverless 연결 테스트"
echo "========================================="
echo ""

# OpenSearch 컬렉션 정보 확인
echo -e "${YELLOW}[TEST 1] OpenSearch 컬렉션 상태${NC}"
COLLECTION_INFO=$(aws opensearchserverless batch-get-collection \
  --ids iw3pzcloa0en8d90hh7 \
  --region us-east-1 \
  --query 'collectionDetails[0]' \
  --output json)

echo "$COLLECTION_INFO" | jq -r '"Collection ID: " + .id'
echo "$COLLECTION_INFO" | jq -r '"Name: " + .name'
echo "$COLLECTION_INFO" | jq -r '"Status: " + .status'
echo "$COLLECTION_INFO" | jq -r '"Endpoint: " + .collectionEndpoint'
echo "$COLLECTION_INFO" | jq -r '"Dashboard Endpoint: " + .dashboardEndpoint'
echo ""

# 액세스 정책 확인
echo -e "${YELLOW}[TEST 2] Data Access Policy 확인${NC}"
aws opensearchserverless list-access-policies \
  --type data \
  --region us-east-1 \
  --query 'accessPolicySummaries[?contains(name, `bos-ai`)].[name,type]' \
  --output table
echo ""

# 네트워크 정책 확인
echo -e "${YELLOW}[TEST 3] Network Policy 확인${NC}"
aws opensearchserverless list-security-policies \
  --type network \
  --region us-east-1 \
  --query 'securityPolicySummaries[?contains(name, `bos-ai`)].[name,type]' \
  --output table
echo ""

# 암호화 정책 확인
echo -e "${YELLOW}[TEST 4] Encryption Policy 확인${NC}"
aws opensearchserverless list-security-policies \
  --type encryption \
  --region us-east-1 \
  --query 'securityPolicySummaries[?contains(name, `bos-ai`)].[name,type]' \
  --output table
echo ""

# VPC 엔드포인트 확인 (OpenSearch Serverless용)
echo -e "${YELLOW}[TEST 5] OpenSearch VPC 엔드포인트 확인${NC}"
OPENSEARCH_VPCE=$(aws opensearchserverless list-vpc-endpoints \
  --region us-east-1 \
  --query 'vpcEndpointSummaries[?contains(name, `bos-ai`) || contains(name, `opensearch`)]' \
  --output json)

if [ "$OPENSEARCH_VPCE" != "[]" ]; then
  echo "$OPENSEARCH_VPCE" | jq -r '.[] | "VPC Endpoint ID: " + .id'
  echo "$OPENSEARCH_VPCE" | jq -r '.[] | "Name: " + .name'
  echo "$OPENSEARCH_VPCE" | jq -r '.[] | "Status: " + .status'
else
  echo "OpenSearch VPC 엔드포인트가 없습니다 (Public 접근 또는 다른 설정)"
fi
echo ""

# 인덱스 확인 (권한이 있는 경우)
echo -e "${YELLOW}[TEST 6] OpenSearch 인덱스 확인${NC}"
ENDPOINT=$(echo "$COLLECTION_INFO" | jq -r '.collectionEndpoint')

echo "Endpoint: $ENDPOINT"
echo "참고: 인덱스 조회는 적절한 IAM 권한이 필요합니다."
echo ""

# Security Group 확인 (서울)
echo -e "${YELLOW}[TEST 7] Seoul OpenSearch Security Group 확인${NC}"
aws ec2 describe-security-groups \
  --region ap-northeast-2 \
  --filters "Name=group-name,Values=opensearch-bos-ai-seoul-prod" \
  --query 'SecurityGroups[0].[GroupId,GroupName,VpcId]' \
  --output table
echo ""

# Security Group 규칙 확인
echo -e "${YELLOW}[TEST 8] Security Group Inbound 규칙${NC}"
aws ec2 describe-security-groups \
  --region ap-northeast-2 \
  --filters "Name=group-name,Values=opensearch-bos-ai-seoul-prod" \
  --query 'SecurityGroups[0].IpPermissions[*].[FromPort,ToPort,IpProtocol,IpRanges[0].CidrIp]' \
  --output table
echo ""

echo -e "${GREEN}✓ OpenSearch 연결 테스트 완료!${NC}"
echo ""
echo "참고:"
echo "- OpenSearch Serverless는 버지니아 리전에 배포되어 있습니다"
echo "- VPC 내부에서만 접근 가능합니다"
echo "- 실제 데이터 쿼리는 적절한 IAM 권한이 필요합니다"
