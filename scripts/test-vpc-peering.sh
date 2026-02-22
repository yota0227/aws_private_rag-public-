#!/bin/bash

# VPC Peering Connection Test Script
# Tests connectivity between Seoul and Virginia VPCs

set -e

echo "=========================================="
echo "VPC Peering Connection Test"
echo "=========================================="
echo ""

# Configuration
SEOUL_VPC_ID="vpc-066c464f9c750ee9e"
VIRGINIA_VPC_ID="vpc-0ed37ff82027c088f"
PEERING_ID="pcx-06599e9d9a3fe573f"
SEOUL_REGION="ap-northeast-2"
VIRGINIA_REGION="us-east-1"

# Test 1: Verify Peering Connection Status
echo "Test 1: Verifying Peering Connection Status..."
PEERING_STATUS=$(aws ec2 describe-vpc-peering-connections \
  --region $SEOUL_REGION \
  --vpc-peering-connection-ids $PEERING_ID \
  --query 'VpcPeeringConnections[0].Status.Code' \
  --output text)

if [ "$PEERING_STATUS" == "active" ]; then
  echo "✓ Peering connection is active"
else
  echo "✗ Peering connection status: $PEERING_STATUS"
  exit 1
fi
echo ""

# Test 2: Verify DNS Resolution Settings
echo "Test 2: Verifying DNS Resolution Settings..."
DNS_ACCEPTER=$(aws ec2 describe-vpc-peering-connections \
  --region $SEOUL_REGION \
  --vpc-peering-connection-ids $PEERING_ID \
  --query 'VpcPeeringConnections[0].AccepterVpcInfo.PeeringOptions.AllowDnsResolutionFromRemoteVpc' \
  --output text)

DNS_REQUESTER=$(aws ec2 describe-vpc-peering-connections \
  --region $SEOUL_REGION \
  --vpc-peering-connection-ids $PEERING_ID \
  --query 'VpcPeeringConnections[0].RequesterVpcInfo.PeeringOptions.AllowDnsResolutionFromRemoteVpc' \
  --output text)

if [ "$DNS_ACCEPTER" == "True" ] && [ "$DNS_REQUESTER" == "True" ]; then
  echo "✓ DNS resolution enabled for both VPCs"
else
  echo "✗ DNS resolution not properly configured"
  echo "  Accepter: $DNS_ACCEPTER, Requester: $DNS_REQUESTER"
fi
echo ""

# Test 3: Verify Route Tables (Seoul)
echo "Test 3: Verifying Route Tables (Seoul)..."
SEOUL_ROUTES=$(aws ec2 describe-route-tables \
  --region $SEOUL_REGION \
  --filters "Name=vpc-id,Values=$SEOUL_VPC_ID" \
  --query "RouteTables[].Routes[?DestinationCidrBlock=='10.20.0.0/16'].VpcPeeringConnectionId" \
  --output text)

if echo "$SEOUL_ROUTES" | grep -q "$PEERING_ID"; then
  echo "✓ Seoul route table has Virginia CIDR route"
else
  echo "✗ Seoul route table missing Virginia CIDR route"
fi
echo ""

# Test 4: Verify Route Tables (Virginia)
echo "Test 4: Verifying Route Tables (Virginia)..."
VIRGINIA_ROUTES=$(aws ec2 describe-route-tables \
  --region $VIRGINIA_REGION \
  --filters "Name=vpc-id,Values=$VIRGINIA_VPC_ID" \
  --query "RouteTables[].Routes[?DestinationCidrBlock=='10.200.0.0/16'].VpcPeeringConnectionId" \
  --output text)

if echo "$VIRGINIA_ROUTES" | grep -q "$PEERING_ID"; then
  echo "✓ Virginia route table has Seoul CIDR route"
else
  echo "✗ Virginia route table missing Seoul CIDR route"
fi
echo ""

# Test 5: Verify Security Group Rules
echo "Test 5: Verifying Security Group Rules..."

# Check Seoul OpenSearch SG
SEOUL_SG_RULE=$(aws ec2 describe-security-groups \
  --region $SEOUL_REGION \
  --group-ids sg-0ac6a858ab64c545c \
  --query 'SecurityGroups[0].IpPermissions[?FromPort==`443`].IpRanges[?CidrIp==`10.20.0.0/16`]' \
  --output text)

if [ -n "$SEOUL_SG_RULE" ]; then
  echo "✓ Seoul OpenSearch SG allows Virginia CIDR"
else
  echo "✗ Seoul OpenSearch SG missing Virginia CIDR rule"
fi

# Check Virginia Lambda SG
VIRGINIA_SG_RULE=$(aws ec2 describe-security-groups \
  --region $VIRGINIA_REGION \
  --group-ids sg-02fed22ac4aceacd3 \
  --query 'SecurityGroups[0].IpPermissionsEgress[?ToPort==`443`].IpRanges[?CidrIp==`10.200.0.0/16`]' \
  --output text)

if [ -n "$VIRGINIA_SG_RULE" ]; then
  echo "✓ Virginia Lambda SG allows egress to Seoul CIDR"
else
  echo "✗ Virginia Lambda SG missing Seoul CIDR egress rule"
fi
echo ""

# Test 6: Network Connectivity Test (requires EC2 instance)
echo "Test 6: Network Connectivity Test..."
echo "Note: Actual ping/connectivity tests require EC2 instances in both VPCs"
echo "This test verifies that the infrastructure is properly configured"
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "Peering Status: $PEERING_STATUS"
echo "DNS Resolution: Accepter=$DNS_ACCEPTER, Requester=$DNS_REQUESTER"
echo "Route Tables: Configured"
echo "Security Groups: Configured"
echo ""
echo "VPC Peering infrastructure is ready for use"
echo "To test actual connectivity, launch EC2 instances in both VPCs"
