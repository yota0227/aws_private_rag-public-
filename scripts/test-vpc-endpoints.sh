#!/bin/bash
# VPC 엔드포인트 연결 테스트 스크립트

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================="
echo "VPC 엔드포인트 연결 테스트"
echo "========================================="
echo ""

# Bedrock Runtime 엔드포인트 테스트
echo -e "${YELLOW}[TEST 1] Bedrock Runtime 엔드포인트${NC}"
BEDROCK_ENDPOINT=$(aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=service-name,Values=com.amazonaws.ap-northeast-2.bedrock-runtime" \
  --query 'VpcEndpoints[0].[VpcEndpointId,State,DnsEntries[0].DnsName]' \
  --output text)

echo "Endpoint ID: $(echo $BEDROCK_ENDPOINT | awk '{print $1}')"
echo "State: $(echo $BEDROCK_ENDPOINT | awk '{print $2}')"
echo "DNS: $(echo $BEDROCK_ENDPOINT | awk '{print $3}')"

# DNS 조회 테스트
DNS_NAME=$(echo $BEDROCK_ENDPOINT | awk '{print $3}')
if [ ! -z "$DNS_NAME" ]; then
  echo "DNS Lookup:"
  nslookup $DNS_NAME || echo "  (DNS lookup may not work from outside VPC)"
fi
echo ""

# Bedrock Agent Runtime 엔드포인트 테스트
echo -e "${YELLOW}[TEST 2] Bedrock Agent Runtime 엔드포인트${NC}"
BEDROCK_AGENT_ENDPOINT=$(aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=service-name,Values=com.amazonaws.ap-northeast-2.bedrock-agent-runtime" \
  --query 'VpcEndpoints[0].[VpcEndpointId,State,DnsEntries[0].DnsName]' \
  --output text)

echo "Endpoint ID: $(echo $BEDROCK_AGENT_ENDPOINT | awk '{print $1}')"
echo "State: $(echo $BEDROCK_AGENT_ENDPOINT | awk '{print $2}')"
echo "DNS: $(echo $BEDROCK_AGENT_ENDPOINT | awk '{print $3}')"
echo ""

# Secrets Manager 엔드포인트 테스트
echo -e "${YELLOW}[TEST 3] Secrets Manager 엔드포인트${NC}"
SECRETS_ENDPOINT=$(aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=service-name,Values=com.amazonaws.ap-northeast-2.secretsmanager" \
  --query 'VpcEndpoints[0].[VpcEndpointId,State,DnsEntries[0].DnsName]' \
  --output text)

echo "Endpoint ID: $(echo $SECRETS_ENDPOINT | awk '{print $1}')"
echo "State: $(echo $SECRETS_ENDPOINT | awk '{print $2}')"
echo "DNS: $(echo $SECRETS_ENDPOINT | awk '{print $3}')"
echo ""

# CloudWatch Logs 엔드포인트 테스트
echo -e "${YELLOW}[TEST 4] CloudWatch Logs 엔드포인트${NC}"
LOGS_ENDPOINT=$(aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=service-name,Values=com.amazonaws.ap-northeast-2.logs" \
  --query 'VpcEndpoints[0].[VpcEndpointId,State,DnsEntries[0].DnsName]' \
  --output text)

echo "Endpoint ID: $(echo $LOGS_ENDPOINT | awk '{print $1}')"
echo "State: $(echo $LOGS_ENDPOINT | awk '{print $2}')"
echo "DNS: $(echo $LOGS_ENDPOINT | awk '{print $3}')"
echo ""

# S3 Gateway 엔드포인트 테스트
echo -e "${YELLOW}[TEST 5] S3 Gateway 엔드포인트${NC}"
S3_ENDPOINT=$(aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=service-name,Values=com.amazonaws.ap-northeast-2.s3" \
  --query 'VpcEndpoints[0].[VpcEndpointId,State,ServiceName]' \
  --output text)

echo "Endpoint ID: $(echo $S3_ENDPOINT | awk '{print $1}')"
echo "State: $(echo $S3_ENDPOINT | awk '{print $2}')"
echo "Service: $(echo $S3_ENDPOINT | awk '{print $3}')"

# Route Table 연결 확인
ROUTE_TABLES=$(aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --vpc-endpoint-ids $(echo $S3_ENDPOINT | awk '{print $1}') \
  --query 'VpcEndpoints[0].RouteTableIds' \
  --output text)

echo "Connected Route Tables: $ROUTE_TABLES"
echo ""

# Kinesis Firehose 엔드포인트 테스트
echo -e "${YELLOW}[TEST 6] Kinesis Firehose 엔드포인트${NC}"
FIREHOSE_ENDPOINT=$(aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=service-name,Values=com.amazonaws.ap-northeast-2.kinesis-firehose" \
  --query 'VpcEndpoints[0].[VpcEndpointId,State,DnsEntries[0].DnsName]' \
  --output text)

echo "Endpoint ID: $(echo $FIREHOSE_ENDPOINT | awk '{print $1}')"
echo "State: $(echo $FIREHOSE_ENDPOINT | awk '{print $2}')"
echo "DNS: $(echo $FIREHOSE_ENDPOINT | awk '{print $3}')"
echo ""

# Logging VPC (10.200.0.0/16) - Private DNS 활성화 확인
LOGGING_VPC_ID="vpc-066c464f9c750ee9e"
FRONTEND_VPC_ID="vpc-0a118e1bf21d0c057"

echo -e "${YELLOW}[TEST 7] Logging VPC (10.200.0.0/16) - Private DNS 활성화 확인${NC}"
aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=${LOGGING_VPC_ID}" \
  --query 'VpcEndpoints[?VpcEndpointType==`Interface`].[ServiceName,PrivateDnsEnabled]' \
  --output table
echo ""

echo -e "${YELLOW}[TEST 7b] Frontend VPC (10.10.0.0/16) - Private DNS 활성화 확인${NC}"
aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=${FRONTEND_VPC_ID}" \
  --query 'VpcEndpoints[?VpcEndpointType==`Interface`].[ServiceName,PrivateDnsEnabled]' \
  --output table
echo ""

# Security Group 확인
echo -e "${YELLOW}[TEST 8] Logging VPC - VPC 엔드포인트 Security Group 확인${NC}"
aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=${LOGGING_VPC_ID}" \
  --query 'VpcEndpoints[?VpcEndpointType==`Interface`].[VpcEndpointId,Groups[0].GroupId,Groups[0].GroupName]' \
  --output table
echo ""

echo -e "${YELLOW}[TEST 8b] Frontend VPC - VPC 엔드포인트 Security Group 확인${NC}"
aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=${FRONTEND_VPC_ID}" \
  --query 'VpcEndpoints[?VpcEndpointType==`Interface`].[VpcEndpointId,Groups[0].GroupId,Groups[0].GroupName]' \
  --output table
echo ""

echo -e "${GREEN}✓ VPC 엔드포인트 연결 테스트 완료!${NC}"
echo ""
echo "참고: VPC 내부에서만 엔드포인트에 접근 가능합니다."
echo "실제 연결 테스트는 VPC 내부 EC2 인스턴스에서 수행해야 합니다."
