#!/bin/bash

# Import script for Logging VPC resources
# Run from environments/network-layer directory

set -e

echo "Importing Logging VPC resources..."

# IGW
echo "Importing Internet Gateway..."
terraform import 'module.vpc_logging.aws_internet_gateway.main[0]' igw-007a80a4355e38fc4

# NAT Gateway
echo "Importing NAT Gateway..."
terraform import 'module.vpc_logging.aws_nat_gateway.main[0]' nat-03dc6eb89ecb8f21c

# EIP for NAT Gateway
echo "Getting EIP allocation ID..."
EIP_ALLOC_ID=$(aws ec2 describe-nat-gateways --region ap-northeast-2 --nat-gateway-ids nat-03dc6eb89ecb8f21c --query 'NatGateways[0].NatGatewayAddresses[0].AllocationId' --output text)
echo "Importing EIP: $EIP_ALLOC_ID"
terraform import "module.vpc_logging.aws_eip.nat[0]" $EIP_ALLOC_ID

# Route Tables
echo "Getting Route Table IDs..."
RTB_IDS=$(aws ec2 describe-route-tables --region ap-northeast-2 --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" --query 'RouteTables[*].RouteTableId' --output text)

# Find private and public route tables
for rtb in $RTB_IDS; do
  ROUTES=$(aws ec2 describe-route-tables --region ap-northeast-2 --route-table-ids $rtb --query 'RouteTables[0].Routes[?GatewayId!=`local`].GatewayId' --output text)
  
  if echo "$ROUTES" | grep -q "igw-"; then
    echo "Public Route Table: $rtb"
    PUBLIC_RTB=$rtb
  elif echo "$ROUTES" | grep -q "nat-"; then
    echo "Private Route Table (with NAT): $rtb"
    if [ -z "$PRIVATE_RTB_0" ]; then
      PRIVATE_RTB_0=$rtb
    else
      PRIVATE_RTB_1=$rtb
    fi
  fi
done

# Import Route Tables
echo "Importing Private Route Table 0..."
terraform import "module.vpc_logging.aws_route_table.private[0]" $PRIVATE_RTB_0

echo "Importing Private Route Table 1..."
terraform import "module.vpc_logging.aws_route_table.private[1]" $PRIVATE_RTB_1

echo "Importing Public Route Table..."
terraform import "module.vpc_logging.aws_route_table.public[0]" $PUBLIC_RTB

# Route Table Associations
echo "Getting Route Table Associations..."
ASSOC_0=$(aws ec2 describe-route-tables --region ap-northeast-2 --route-table-ids $PRIVATE_RTB_0 --query 'RouteTables[0].Associations[?SubnetId!=null].RouteTableAssociationId' --output text)
ASSOC_1=$(aws ec2 describe-route-tables --region ap-northeast-2 --route-table-ids $PRIVATE_RTB_1 --query 'RouteTables[0].Associations[?SubnetId!=null].RouteTableAssociationId' --output text)
ASSOC_PUB_0=$(aws ec2 describe-route-tables --region ap-northeast-2 --route-table-ids $PUBLIC_RTB --query 'RouteTables[0].Associations[?SubnetId==`subnet-06d3c439cedf14742`].RouteTableAssociationId' --output text)
ASSOC_PUB_1=$(aws ec2 describe-route-tables --region ap-northeast-2 --route-table-ids $PUBLIC_RTB --query 'RouteTables[0].Associations[?SubnetId==`subnet-0a9ba13fade9c4c66`].RouteTableAssociationId' --output text)

echo "Importing Route Table Associations..."
terraform import "module.vpc_logging.aws_route_table_association.private[0]" $ASSOC_0
terraform import "module.vpc_logging.aws_route_table_association.private[1]" $ASSOC_1
terraform import "module.vpc_logging.aws_route_table_association.public[0]" $ASSOC_PUB_0
terraform import "module.vpc_logging.aws_route_table_association.public[1]" $ASSOC_PUB_1

echo "Import complete!"
echo "Run 'terraform plan' to verify"
