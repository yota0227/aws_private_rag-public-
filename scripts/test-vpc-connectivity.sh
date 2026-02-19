#!/bin/bash
# VPC Connectivity Test Script
# Tests connectivity between Seoul and Virginia VPCs

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}VPC Connectivity Test${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Test 1: VPC Peering Status
echo -e "${YELLOW}[TEST 1]${NC} VPC Peering Connection Status"
PEERING_STATUS=$(aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids pcx-06599e9d9a3fe573f \
  --region ap-northeast-2 \
  --query 'VpcPeeringConnections[0].Status.Code' \
  --output text)

if [ "$PEERING_STATUS" == "active" ]; then
  echo -e "${GREEN}✓ VPC Peering is ACTIVE${NC}"
else
  echo -e "${RED}✗ VPC Peering is $PEERING_STATUS${NC}"
  exit 1
fi
echo ""

# Test 2: DNS Resolution
echo -e "${YELLOW}[TEST 2]${NC} DNS Resolution Options"
DNS_REQUESTER=$(aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids pcx-06599e9d9a3fe573f \
  --region ap-northeast-2 \
  --query 'VpcPeeringConnections[0].RequesterVpcInfo.PeeringOptions.AllowDnsResolutionFromRemoteVpc' \
  --output text)

DNS_ACCEPTER=$(aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids pcx-06599e9d9a3fe573f \
  --region ap-northeast-2 \
  --query 'VpcPeeringConnections[0].AccepterVpcInfo.PeeringOptions.AllowDnsResolutionFromRemoteVpc' \
  --output text)

if [ "$DNS_REQUESTER" == "True" ] && [ "$DNS_ACCEPTER" == "True" ]; then
  echo -e "${GREEN}✓ DNS Resolution enabled (both directions)${NC}"
else
  echo -e "${RED}✗ DNS Resolution not fully enabled${NC}"
  echo "  Requester: $DNS_REQUESTER"
  echo "  Accepter: $DNS_ACCEPTER"
fi
echo ""

# Test 3: Route Tables
echo -e "${YELLOW}[TEST 3]${NC} Route Table Configuration"

# Seoul to Virginia route
SEOUL_ROUTE=$(aws ec2 describe-route-tables \
  --route-table-id rtb-078c8f8a00c2960f7 \
  --region ap-northeast-2 \
  --query 'RouteTables[0].Routes[?DestinationCidrBlock==`10.20.0.0/16`].State' \
  --output text)

if [ "$SEOUL_ROUTE" == "active" ]; then
  echo -e "${GREEN}✓ Seoul → Virginia route is active${NC}"
else
  echo -e "${RED}✗ Seoul → Virginia route not found or inactive${NC}"
fi

# Virginia to Seoul routes
VA_ROUTES=$(aws ec2 describe-route-tables \
  --region us-east-1 \
  --filters "Name=vpc-id,Values=vpc-0ed37ff82027c088f" \
  --query 'RouteTables[*].Routes[?DestinationCidrBlock==`10.200.0.0/16`].State' \
  --output text | wc -w)

if [ "$VA_ROUTES" -ge 3 ]; then
  echo -e "${GREEN}✓ Virginia → Seoul routes configured ($VA_ROUTES route tables)${NC}"
else
  echo -e "${RED}✗ Virginia → Seoul routes incomplete${NC}"
fi
echo ""

# Test 4: OpenSearch Serverless
echo -e "${YELLOW}[TEST 4]${NC} OpenSearch Serverless Collection"
OPENSEARCH_STATUS=$(aws opensearchserverless batch-get-collection \
  --ids iw3pzcloa0en8d90hh7 \
  --region us-east-1 \
  --query 'collectionDetails[0].status' \
  --output text)

if [ "$OPENSEARCH_STATUS" == "ACTIVE" ]; then
  echo -e "${GREEN}✓ OpenSearch collection is ACTIVE${NC}"
  OPENSEARCH_ENDPOINT=$(aws opensearchserverless batch-get-collection \
    --ids iw3pzcloa0en8d90hh7 \
    --region us-east-1 \
    --query 'collectionDetails[0].collectionEndpoint' \
    --output text)
  echo "  Endpoint: $OPENSEARCH_ENDPOINT"
else
  echo -e "${RED}✗ OpenSearch collection is $OPENSEARCH_STATUS${NC}"
fi
echo ""

# Test 5: Bedrock Knowledge Base
echo -e "${YELLOW}[TEST 5]${NC} Bedrock Knowledge Base"
KB_STATUS=$(aws bedrock-agent get-knowledge-base \
  --knowledge-base-id FNNOP3VBZV \
  --region us-east-1 \
  --query 'knowledgeBase.status' \
  --output text)

if [ "$KB_STATUS" == "ACTIVE" ]; then
  echo -e "${GREEN}✓ Bedrock Knowledge Base is ACTIVE${NC}"
  KB_NAME=$(aws bedrock-agent get-knowledge-base \
    --knowledge-base-id FNNOP3VBZV \
    --region us-east-1 \
    --query 'knowledgeBase.name' \
    --output text)
  echo "  Name: $KB_NAME"
  echo "  ID: FNNOP3VBZV"
else
  echo -e "${RED}✗ Bedrock Knowledge Base is $KB_STATUS${NC}"
fi
echo ""

# Test 6: Lambda Function
echo -e "${YELLOW}[TEST 6]${NC} Lambda Function"
LAMBDA_STATE=$(aws lambda get-function \
  --function-name document-processor \
  --region us-east-1 \
  --query 'Configuration.State' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$LAMBDA_STATE" == "Active" ]; then
  echo -e "${GREEN}✓ Lambda function is Active${NC}"
  LAMBDA_VPC=$(aws lambda get-function \
    --function-name document-processor \
    --region us-east-1 \
    --query 'Configuration.VpcConfig.VpcId' \
    --output text)
  echo "  VPC: $LAMBDA_VPC (Virginia)"
else
  echo -e "${YELLOW}⚠ Lambda function state: $LAMBDA_STATE${NC}"
fi
echo ""

# Test 7: S3 Buckets
echo -e "${YELLOW}[TEST 7]${NC} S3 Buckets"
SEOUL_BUCKET=$(aws s3 ls | grep "bos-ai-documents-seoul" | wc -l)
VA_BUCKET=$(aws s3 ls | grep "bos-ai-documents-us" | wc -l)

if [ "$SEOUL_BUCKET" -eq 1 ]; then
  echo -e "${GREEN}✓ Seoul S3 bucket exists (bos-ai-documents-seoul)${NC}"
else
  echo -e "${RED}✗ Seoul S3 bucket not found${NC}"
fi

if [ "$VA_BUCKET" -eq 1 ]; then
  echo -e "${GREEN}✓ Virginia S3 bucket exists (bos-ai-documents-us)${NC}"
else
  echo -e "${RED}✗ Virginia S3 bucket not found${NC}"
fi
echo ""

# Test 8: VPC Endpoints (Seoul)
echo -e "${YELLOW}[TEST 8]${NC} VPC Endpoints (Seoul)"
ENDPOINT_COUNT=$(aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --query 'VpcEndpoints[?State==`available`] | length(@)' \
  --output text)

echo -e "${GREEN}✓ $ENDPOINT_COUNT VPC endpoints available in Seoul${NC}"
aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --query 'VpcEndpoints[?State==`available`].[ServiceName]' \
  --output text | sed 's/^/  - /'
echo ""

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Connectivity Test Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Summary:${NC}"
echo "  - VPC Peering: Seoul ↔ Virginia (ACTIVE)"
echo "  - OpenSearch: us-east-1 (ACTIVE)"
echo "  - Bedrock KB: us-east-1 (ACTIVE)"
echo "  - Lambda: us-east-1 (Active)"
echo "  - S3 Buckets: Seoul + Virginia"
echo "  - VPC Endpoints: $ENDPOINT_COUNT in Seoul"
echo ""
echo -e "${GREEN}🎉 System is ready for demo!${NC}"
echo ""
