#!/bin/bash
# Deployment script for Terraform backend infrastructure
# This script deploys the S3 bucket and DynamoDB table for Terraform state management

set -e

echo "=========================================="
echo "Terraform Backend Infrastructure Deployment"
echo "=========================================="
echo ""

# Check if terraform is installed
if ! command -v terraform &> /dev/null; then
    echo "Error: Terraform is not installed"
    echo "Please install Terraform from https://www.terraform.io/downloads"
    exit 1
fi

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed"
    echo "Please install AWS CLI from https://aws.amazon.com/cli/"
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

# Check if terraform.tfvars exists
if [ ! -f "terraform.tfvars" ]; then
    echo "Warning: terraform.tfvars not found"
    echo "Creating terraform.tfvars from example..."
    cp terraform.tfvars.example terraform.tfvars
    
    # Update account ID in terraform.tfvars
    sed -i.bak "s/123456789012/$ACCOUNT_ID/g" terraform.tfvars
    rm terraform.tfvars.bak
    
    echo ""
    echo "Please review and update terraform.tfvars with your configuration"
    echo "Press Enter to continue or Ctrl+C to exit..."
    read
fi

# Initialize Terraform
echo "Initializing Terraform..."
terraform init

# Format Terraform files
echo "Formatting Terraform files..."
terraform fmt

# Validate configuration
echo "Validating Terraform configuration..."
terraform validate

# Show plan
echo ""
echo "=========================================="
echo "Terraform Plan"
echo "=========================================="
terraform plan

# Confirm deployment
echo ""
echo "Do you want to apply this configuration? (yes/no)"
read -r response

if [ "$response" != "yes" ]; then
    echo "Deployment cancelled"
    exit 0
fi

# Apply configuration
echo ""
echo "=========================================="
echo "Applying Terraform Configuration"
echo "=========================================="
terraform apply -auto-approve

# Show outputs
echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
terraform output

echo ""
echo "Backend infrastructure has been successfully deployed."
echo "You can now use this backend in your network-layer and app-layer configurations."
echo ""
echo "Next steps:"
echo "1. Deploy network-layer: cd ../../network-layer && terraform init && terraform apply"
echo "2. Deploy app-layer: cd ../../app-layer/bedrock-rag && terraform init && terraform apply"
