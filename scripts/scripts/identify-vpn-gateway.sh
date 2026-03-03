#!/bin/bash
# Script to identify existing VPN Gateway for import
# Requirements: 7.1

set -e

REGION="ap-northeast-2"

echo "=========================================="
echo "VPN Gateway Identification Script"
echo "=========================================="
echo ""

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed"
    echo "Please install AWS CLI: https://aws.amazon.com/cli/"
    exit 1
fi

# Check AWS credentials
echo "Checking AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "Error: AWS credentials are not configured"
    echo "Please configure AWS credentials using 'aws configure'"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account ID: $ACCOUNT_ID"
echo ""

# List VPN Gateways in Seoul region
echo "Searching for VPN Gateways in $REGION..."
echo ""

VPN_GATEWAYS=$(aws ec2 describe-vpn-gateways \
    --region $REGION \
    --query 'VpnGateways[?State==`available`].[VpnGatewayId,Type,State,AmazonSideAsn,Tags[?Key==`Name`].Value|[0]]' \
    --output table)

if [ -z "$VPN_GATEWAYS" ] || [ "$VPN_GATEWAYS" == "None" ]; then
    echo "No available VPN Gateways found in $REGION"
    echo ""
    echo "If you need to create a VPN Gateway for testing:"
    echo "  aws ec2 create-vpn-gateway --type ipsec.1 --amazon-side-asn 64512 --region $REGION"
    exit 0
fi

echo "$VPN_GATEWAYS"
echo ""

# Get detailed information for each VPN Gateway
VPN_IDS=$(aws ec2 describe-vpn-gateways \
    --region $REGION \
    --query 'VpnGateways[?State==`available`].VpnGatewayId' \
    --output text)

for VPN_ID in $VPN_IDS; do
    echo "=========================================="
    echo "VPN Gateway: $VPN_ID"
    echo "=========================================="
    
    # Get VPN Gateway details
    aws ec2 describe-vpn-gateways \
        --region $REGION \
        --vpn-gateway-ids $VPN_ID \
        --query 'VpnGateways[0]' \
        --output json
    
    echo ""
    
    # Check VPC attachments
    ATTACHMENTS=$(aws ec2 describe-vpn-gateways \
        --region $REGION \
        --vpn-gateway-ids $VPN_ID \
        --query 'VpnGateways[0].VpcAttachments[?State==`attached`].[VpcId,State]' \
        --output table)
    
    if [ ! -z "$ATTACHMENTS" ] && [ "$ATTACHMENTS" != "None" ]; then
        echo "Current VPC Attachments:"
        echo "$ATTACHMENTS"
    else
        echo "No VPC attachments (available for import)"
    fi
    
    echo ""
done

echo "=========================================="
echo "Import Instructions"
echo "=========================================="
echo ""
echo "To import a VPN Gateway into Terraform:"
echo ""
echo "1. Choose a VPN Gateway ID from the list above"
echo ""
echo "2. Edit environments/network-layer/main.tf:"
echo "   - Uncomment the import block"
echo "   - Replace 'vgw-XXXXXXXXXXXXXXXXX' with the actual VPN Gateway ID"
echo ""
echo "3. Run Terraform plan to preview the import:"
echo "   cd environments/network-layer"
echo "   terraform plan"
echo ""
echo "4. If the VPN Gateway is already attached to a VPC, you may need to:"
echo "   - Detach it first: aws ec2 detach-vpn-gateway --vpn-gateway-id <ID> --vpc-id <VPC-ID> --region $REGION"
echo "   - Or modify the Terraform configuration to match the existing attachment"
echo ""
echo "5. Apply the configuration:"
echo "   terraform apply"
echo ""
echo "6. Verify the import:"
echo "   terraform state show aws_vpn_gateway.existing"
echo ""
