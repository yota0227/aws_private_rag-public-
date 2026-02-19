#!/bin/bash
# BOS-AI VPC Consolidation - Deployment Preparation Script
# This script collects actual AWS resource IDs and prepares Terraform files for deployment

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}BOS-AI VPC Consolidation${NC}"
echo -e "${BLUE}Deployment Preparation Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Configuration
VPC_ID="vpc-066c464f9c750ee9e"
REGION="ap-northeast-2"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo -e "${GREEN}[INFO]${NC} AWS Account ID: ${ACCOUNT_ID}"
echo -e "${GREEN}[INFO]${NC} Target VPC: ${VPC_ID}"
echo -e "${GREEN}[INFO]${NC} Region: ${REGION}"
echo ""

# Step 1: Collect Subnet IDs
echo -e "${YELLOW}[STEP 1]${NC} Collecting Subnet IDs..."
SUBNETS=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
  --region ${REGION} \
  --query 'Subnets[*].[SubnetId,CidrBlock,AvailabilityZone,Tags[?Key==`Name`].Value|[0]]' \
  --output text)

echo "$SUBNETS" | while read subnet_id cidr az name; do
  echo "  - ${subnet_id} | ${cidr} | ${az} | ${name:-unnamed}"
done
echo ""

# Extract specific subnet IDs
PRIVATE_2A=$(echo "$SUBNETS" | grep "10.200.1.0/24" | awk '{print $1}')
PRIVATE_2C=$(echo "$SUBNETS" | grep "10.200.2.0/24" | awk '{print $1}')
PUBLIC_2A=$(echo "$SUBNETS" | grep "10.200.10.0/24" | awk '{print $1}')
PUBLIC_2C=$(echo "$SUBNETS" | grep "10.200.20.0/24" | awk '{print $1}')

echo -e "${GREEN}[INFO]${NC} Private Subnet 2a: ${PRIVATE_2A}"
echo -e "${GREEN}[INFO]${NC} Private Subnet 2c: ${PRIVATE_2C}"
echo -e "${GREEN}[INFO]${NC} Public Subnet 2a: ${PUBLIC_2A}"
echo -e "${GREEN}[INFO]${NC} Public Subnet 2c: ${PUBLIC_2C}"
echo ""

# Step 2: Collect Route Table IDs
echo -e "${YELLOW}[STEP 2]${NC} Collecting Route Table IDs..."
ROUTE_TABLES=$(aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
  --region ${REGION} \
  --query 'RouteTables[*].[RouteTableId,Tags[?Key==`Name`].Value|[0]]' \
  --output text)

echo "$ROUTE_TABLES" | while read rtb_id name; do
  echo "  - ${rtb_id} | ${name:-unnamed}"
done
echo ""

# Identify private and public route tables
RTB_PRIVATE=$(aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=${VPC_ID}" "Name=association.subnet-id,Values=${PRIVATE_2A}" \
  --region ${REGION} \
  --query 'RouteTables[0].RouteTableId' \
  --output text)

RTB_PUBLIC=$(aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=${VPC_ID}" "Name=association.subnet-id,Values=${PUBLIC_2A}" \
  --region ${REGION} \
  --query 'RouteTables[0].RouteTableId' \
  --output text)

echo -e "${GREEN}[INFO]${NC} Private Route Table: ${RTB_PRIVATE}"
echo -e "${GREEN}[INFO]${NC} Public Route Table: ${RTB_PUBLIC}"
echo ""

# Step 3: Collect NAT Gateway ID
echo -e "${YELLOW}[STEP 3]${NC} Collecting NAT Gateway ID..."
NAT_GW=$(aws ec2 describe-nat-gateways \
  --filter "Name=vpc-id,Values=${VPC_ID}" "Name=state,Values=available" \
  --region ${REGION} \
  --query 'NatGateways[0].NatGatewayId' \
  --output text)

echo -e "${GREEN}[INFO]${NC} NAT Gateway: ${NAT_GW}"
echo ""

# Step 4: Collect Internet Gateway ID
echo -e "${YELLOW}[STEP 4]${NC} Collecting Internet Gateway ID..."
IGW=$(aws ec2 describe-internet-gateways \
  --filters "Name=attachment.vpc-id,Values=${VPC_ID}" \
  --region ${REGION} \
  --query 'InternetGateways[0].InternetGatewayId' \
  --output text)

echo -e "${GREEN}[INFO]${NC} Internet Gateway: ${IGW}"
echo ""

# Step 5: Create replacement script
echo -e "${YELLOW}[STEP 5]${NC} Creating replacement script..."

cat > scripts/replace-placeholders.sh << 'EOF'
#!/bin/bash
# Auto-generated placeholder replacement script

set -e

# Resource IDs
PRIVATE_2A="__PRIVATE_2A__"
PRIVATE_2C="__PRIVATE_2C__"
PUBLIC_2A="__PUBLIC_2A__"
PUBLIC_2C="__PUBLIC_2C__"
RTB_PRIVATE="__RTB_PRIVATE__"
RTB_PUBLIC="__RTB_PUBLIC__"
NAT_GW="__NAT_GW__"
IGW="__IGW__"
ACCOUNT_ID="__ACCOUNT_ID__"

echo "Replacing placeholders in Terraform files..."

# Replace in tag-updates.tf
sed -i.bak \
  -e "s/subnet-0e0e0e0e0e0e0e0e0/${PRIVATE_2A}/g" \
  -e "s/subnet-0f0f0f0f0f0f0f0f0/${PRIVATE_2C}/g" \
  -e "s/subnet-0a0a0a0a0a0a0a0a0/${PUBLIC_2A}/g" \
  -e "s/subnet-0b0b0b0b0b0b0b0b0/${PUBLIC_2C}/g" \
  -e "s/rtb-private-id/${RTB_PRIVATE}/g" \
  -e "s/rtb-public-id/${RTB_PUBLIC}/g" \
  -e "s/nat-gateway-id/${NAT_GW}/g" \
  -e "s/igw-id/${IGW}/g" \
  environments/network-layer/tag-updates.tf

# Replace in vpc-endpoints.tf
sed -i.bak \
  -e "s/subnet-private-2a-id/${PRIVATE_2A}/g" \
  -e "s/subnet-private-2c-id/${PRIVATE_2C}/g" \
  -e "s/rtb-private-id/${RTB_PRIVATE}/g" \
  environments/network-layer/vpc-endpoints.tf

# Replace in opensearch-serverless.tf
sed -i.bak \
  -e "s/subnet-private-2a-id/${PRIVATE_2A}/g" \
  -e "s/subnet-private-2c-id/${PRIVATE_2C}/g" \
  -e "s/533335672315/${ACCOUNT_ID}/g" \
  environments/app-layer/opensearch-serverless.tf

# Replace in lambda.tf
sed -i.bak \
  -e "s/subnet-private-2a-id/${PRIVATE_2A}/g" \
  -e "s/subnet-private-2c-id/${PRIVATE_2C}/g" \
  -e "s/533335672315/${ACCOUNT_ID}/g" \
  environments/app-layer/lambda.tf

# Replace in bedrock-kb.tf
sed -i.bak \
  -e "s/533335672315/${ACCOUNT_ID}/g" \
  environments/app-layer/bedrock-kb.tf

echo "✅ Placeholder replacement complete!"
echo "Backup files created with .bak extension"
EOF

# Substitute actual values
sed -i.bak \
  -e "s/__PRIVATE_2A__/${PRIVATE_2A}/g" \
  -e "s/__PRIVATE_2C__/${PRIVATE_2C}/g" \
  -e "s/__PUBLIC_2A__/${PUBLIC_2A}/g" \
  -e "s/__PUBLIC_2C__/${PUBLIC_2C}/g" \
  -e "s/__RTB_PRIVATE__/${RTB_PRIVATE}/g" \
  -e "s/__RTB_PUBLIC__/${RTB_PUBLIC}/g" \
  -e "s/__NAT_GW__/${NAT_GW}/g" \
  -e "s/__IGW__/${IGW}/g" \
  -e "s/__ACCOUNT_ID__/${ACCOUNT_ID}/g" \
  scripts/replace-placeholders.sh

chmod +x scripts/replace-placeholders.sh

echo -e "${GREEN}[SUCCESS]${NC} Replacement script created: scripts/replace-placeholders.sh"
echo ""

# Step 6: Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Preparation Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Review collected resource IDs above"
echo "2. Run: ./scripts/replace-placeholders.sh"
echo "3. Follow deployment guide: docs/phase2-6-deployment-guide.md"
echo ""
echo -e "${YELLOW}Deployment Order:${NC}"
echo "  Phase 2: cd environments/network-layer && terraform apply"
echo "  Phase 3: terraform apply -target=module.vpc_endpoints"
echo "  Phase 4: cd environments/app-layer && terraform apply -target=aws_opensearchserverless_collection.main"
echo "  Phase 5: terraform apply -target=aws_lambda_function.document_processor"
echo "  Phase 6: terraform apply -target=aws_bedrockagent_knowledge_base.main"
echo ""

# Step 7: Validate collected IDs
echo -e "${YELLOW}[STEP 6]${NC} Validating collected resource IDs..."

VALIDATION_FAILED=0

if [ -z "$PRIVATE_2A" ] || [ "$PRIVATE_2A" == "None" ]; then
  echo -e "${RED}[ERROR]${NC} Private Subnet 2a not found"
  VALIDATION_FAILED=1
fi

if [ -z "$PRIVATE_2C" ] || [ "$PRIVATE_2C" == "None" ]; then
  echo -e "${RED}[ERROR]${NC} Private Subnet 2c not found"
  VALIDATION_FAILED=1
fi

if [ -z "$PUBLIC_2A" ] || [ "$PUBLIC_2A" == "None" ]; then
  echo -e "${RED}[ERROR]${NC} Public Subnet 2a not found"
  VALIDATION_FAILED=1
fi

if [ -z "$PUBLIC_2C" ] || [ "$PUBLIC_2C" == "None" ]; then
  echo -e "${RED}[ERROR]${NC} Public Subnet 2c not found"
  VALIDATION_FAILED=1
fi

if [ -z "$RTB_PRIVATE" ] || [ "$RTB_PRIVATE" == "None" ]; then
  echo -e "${RED}[ERROR]${NC} Private Route Table not found"
  VALIDATION_FAILED=1
fi

if [ -z "$RTB_PUBLIC" ] || [ "$RTB_PUBLIC" == "None" ]; then
  echo -e "${RED}[ERROR]${NC} Public Route Table not found"
  VALIDATION_FAILED=1
fi

if [ -z "$NAT_GW" ] || [ "$NAT_GW" == "None" ]; then
  echo -e "${RED}[ERROR]${NC} NAT Gateway not found"
  VALIDATION_FAILED=1
fi

if [ -z "$IGW" ] || [ "$IGW" == "None" ]; then
  echo -e "${RED}[ERROR]${NC} Internet Gateway not found"
  VALIDATION_FAILED=1
fi

if [ $VALIDATION_FAILED -eq 1 ]; then
  echo -e "${RED}[FAILED]${NC} Resource validation failed. Please check your VPC configuration."
  exit 1
fi

echo -e "${GREEN}[SUCCESS]${NC} All resource IDs validated successfully"
echo ""

# Step 8: Create deployment summary
echo -e "${YELLOW}[STEP 7]${NC} Creating deployment summary..."

cat > docs/deployment-resource-ids.md << EOF
# BOS-AI VPC Consolidation - Resource IDs

**Generated**: $(date '+%Y-%m-%d %H:%M:%S')  
**VPC**: ${VPC_ID}  
**Region**: ${REGION}  
**Account**: ${ACCOUNT_ID}

## Subnet IDs

| Name | Subnet ID | CIDR | AZ |
|------|-----------|------|-----|
| Private 2a | ${PRIVATE_2A} | 10.200.1.0/24 | ap-northeast-2a |
| Private 2c | ${PRIVATE_2C} | 10.200.2.0/24 | ap-northeast-2c |
| Public 2a | ${PUBLIC_2A} | 10.200.10.0/24 | ap-northeast-2a |
| Public 2c | ${PUBLIC_2C} | 10.200.20.0/24 | ap-northeast-2c |

## Route Table IDs

| Name | Route Table ID |
|------|----------------|
| Private | ${RTB_PRIVATE} |
| Public | ${RTB_PUBLIC} |

## Gateway IDs

| Name | Gateway ID |
|------|------------|
| NAT Gateway | ${NAT_GW} |
| Internet Gateway | ${IGW} |

## Next Steps

1. Run replacement script:
   \`\`\`bash
   ./scripts/replace-placeholders.sh
   \`\`\`

2. Review changes:
   \`\`\`bash
   git diff environments/
   \`\`\`

3. Deploy Phase 2-6:
   - Follow: docs/phase2-6-deployment-guide.md
   - Start with Phase 2 (tag updates)
   - Proceed sequentially through Phase 6

## Terraform Files to Update

- \`environments/network-layer/tag-updates.tf\`
- \`environments/network-layer/vpc-endpoints.tf\`
- \`environments/app-layer/opensearch-serverless.tf\`
- \`environments/app-layer/lambda.tf\`
- \`environments/app-layer/bedrock-kb.tf\`

EOF

echo -e "${GREEN}[SUCCESS]${NC} Deployment summary created: docs/deployment-resource-ids.md"
echo ""

# Final summary
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ Deployment Preparation Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}📋 Summary:${NC}"
echo "  - Resource IDs collected and validated"
echo "  - Replacement script generated"
echo "  - Deployment summary created"
echo ""
echo -e "${YELLOW}📝 Generated Files:${NC}"
echo "  - scripts/replace-placeholders.sh"
echo "  - docs/deployment-resource-ids.md"
echo ""
echo -e "${YELLOW}🚀 Ready to Deploy:${NC}"
echo "  1. ./scripts/replace-placeholders.sh"
echo "  2. Review: git diff environments/"
echo "  3. Deploy: Follow docs/phase2-6-deployment-guide.md"
echo ""
