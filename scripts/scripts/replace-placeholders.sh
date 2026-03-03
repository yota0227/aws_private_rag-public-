#!/bin/bash
# Auto-generated placeholder replacement script

set -e

# Resource IDs
PRIVATE_2A="subnet-0f027e9de8e26c18f"
PRIVATE_2C="subnet-0625d992edf151017"
PUBLIC_2A="subnet-06d3c439cedf14742"
PUBLIC_2C="subnet-0a9ba13fade9c4c66"
RTB_PRIVATE="rtb-078c8f8a00c2960f7"
RTB_PUBLIC="rtb-0446cd3e4c6a6f2ce"
NAT_GW="nat-03dc6eb89ecb8f21c"
IGW="igw-007a80a4355e38fc4"
ACCOUNT_ID="533335672315"

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
