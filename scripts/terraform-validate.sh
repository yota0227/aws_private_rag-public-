#!/bin/bash

# Terraform Validation Script
# This script runs terraform fmt, validate, and tflint on all Terraform configurations

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# Directories to validate
TERRAFORM_DIRS=(
    "environments/global/backend"
    "environments/network-layer"
    "environments/app-layer/bedrock-rag"
    "modules/network/vpc"
    "modules/network/peering"
    "modules/network/security-groups"
    "modules/ai-workload/bedrock-rag"
    "modules/ai-workload/s3-pipeline"
    "modules/security/iam"
    "modules/security/kms"
    "modules/security/vpc-endpoints"
    "modules/monitoring/cloudwatch-alarms"
    "modules/monitoring/cloudwatch-dashboards"
    "modules/security/cloudtrail"
    "modules/cost-management/budgets"
)

# Function to print section header
print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
    ((PASSED_CHECKS++))
}

# Function to print error
print_error() {
    echo -e "${RED}✗ $1${NC}"
    ((FAILED_CHECKS++))
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Function to print info
print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if terraform is installed
check_terraform() {
    print_header "Checking Prerequisites"
    
    if command -v terraform &> /dev/null; then
        TERRAFORM_VERSION=$(terraform version -json | grep -o '"terraform_version":"[^"]*' | cut -d'"' -f4)
        print_success "Terraform installed: v$TERRAFORM_VERSION"
        ((TOTAL_CHECKS++))
    else
        print_error "Terraform not found. Please install Terraform."
        ((TOTAL_CHECKS++))
        exit 1
    fi
}

# Check if tflint is installed
check_tflint() {
    if command -v tflint &> /dev/null; then
        TFLINT_VERSION=$(tflint --version | head -n1 | awk '{print $3}')
        print_success "tflint installed: $TFLINT_VERSION"
        ((TOTAL_CHECKS++))
    else
        print_warning "tflint not found. Skipping tflint checks."
        print_info "Install tflint: https://github.com/terraform-linters/tflint"
        ((TOTAL_CHECKS++))
        return 1
    fi
    return 0
}

# Run terraform fmt check
run_terraform_fmt() {
    local dir=$1
    print_info "Checking format: $dir"
    
    ((TOTAL_CHECKS++))
    
    if terraform fmt -check -recursive "$dir" > /dev/null 2>&1; then
        print_success "Format check passed: $dir"
        return 0
    else
        print_error "Format check failed: $dir"
        echo "  Run 'terraform fmt -recursive $dir' to fix"
        return 1
    fi
}

# Run terraform validate
run_terraform_validate() {
    local dir=$1
    print_info "Validating: $dir"
    
    ((TOTAL_CHECKS++))
    
    # Change to directory
    cd "$dir" || return 1
    
    # Initialize without backend (for validation only)
    if terraform init -backend=false > /dev/null 2>&1; then
        if terraform validate > /dev/null 2>&1; then
            print_success "Validation passed: $dir"
            cd - > /dev/null
            return 0
        else
            print_error "Validation failed: $dir"
            terraform validate
            cd - > /dev/null
            return 1
        fi
    else
        print_error "Terraform init failed: $dir"
        cd - > /dev/null
        return 1
    fi
}

# Run tflint
run_tflint() {
    local dir=$1
    print_info "Running tflint: $dir"
    
    ((TOTAL_CHECKS++))
    
    cd "$dir" || return 1
    
    # Initialize tflint if .tflint.hcl exists
    if [ -f ".tflint.hcl" ]; then
        tflint --init > /dev/null 2>&1
    fi
    
    if tflint > /dev/null 2>&1; then
        print_success "tflint passed: $dir"
        cd - > /dev/null
        return 0
    else
        print_error "tflint failed: $dir"
        tflint
        cd - > /dev/null
        return 1
    fi
}

# Check for common issues
check_common_issues() {
    local dir=$1
    print_info "Checking common issues: $dir"
    
    local issues_found=0
    
    # Check for hardcoded credentials
    if grep -r "aws_access_key_id\|aws_secret_access_key" "$dir"/*.tf 2>/dev/null | grep -v "^#" > /dev/null; then
        print_error "Hardcoded credentials found in $dir"
        ((issues_found++))
    fi
    
    # Check for hardcoded IPs (except for CIDR blocks)
    if grep -rE "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}[^/]" "$dir"/*.tf 2>/dev/null | grep -v "cidr\|CIDR" | grep -v "^#" > /dev/null; then
        print_warning "Potential hardcoded IPs found in $dir (review manually)"
    fi
    
    # Check for missing descriptions in variables
    if [ -f "$dir/variables.tf" ]; then
        if grep -A 2 "^variable" "$dir/variables.tf" | grep -v "description" > /dev/null; then
            print_warning "Some variables missing descriptions in $dir/variables.tf"
        fi
    fi
    
    # Check for missing tags
    if grep -r "resource \"aws_" "$dir"/*.tf 2>/dev/null | grep -v "tags\s*=" > /dev/null; then
        print_warning "Some resources may be missing tags in $dir"
    fi
    
    ((TOTAL_CHECKS++))
    
    if [ $issues_found -eq 0 ]; then
        print_success "Common issues check passed: $dir"
        return 0
    else
        return 1
    fi
}

# Main validation function
validate_directory() {
    local dir=$1
    
    if [ ! -d "$dir" ]; then
        print_warning "Directory not found: $dir (skipping)"
        return 0
    fi
    
    print_header "Validating: $dir"
    
    local dir_failed=0
    
    # Run terraform fmt check
    run_terraform_fmt "$dir" || ((dir_failed++))
    
    # Run terraform validate
    run_terraform_validate "$dir" || ((dir_failed++))
    
    # Run tflint if available
    if check_tflint > /dev/null 2>&1; then
        run_tflint "$dir" || ((dir_failed++))
    fi
    
    # Check common issues
    check_common_issues "$dir" || ((dir_failed++))
    
    if [ $dir_failed -eq 0 ]; then
        print_success "All checks passed for: $dir"
    else
        print_error "$dir_failed check(s) failed for: $dir"
    fi
    
    return $dir_failed
}

# Main script
main() {
    print_header "Terraform Validation Script"
    echo "This script validates all Terraform configurations"
    echo ""
    
    # Check prerequisites
    check_terraform
    TFLINT_AVAILABLE=0
    check_tflint && TFLINT_AVAILABLE=1
    
    # Validate each directory
    for dir in "${TERRAFORM_DIRS[@]}"; do
        validate_directory "$dir"
    done
    
    # Print summary
    print_header "Validation Summary"
    echo "Total checks: $TOTAL_CHECKS"
    echo -e "${GREEN}Passed: $PASSED_CHECKS${NC}"
    echo -e "${RED}Failed: $FAILED_CHECKS${NC}"
    echo ""
    
    if [ $FAILED_CHECKS -eq 0 ]; then
        print_success "All validations passed!"
        echo ""
        echo "Next steps:"
        echo "  1. Review any warnings above"
        echo "  2. Run 'terraform plan' in each environment"
        echo "  3. Run property-based tests: cd tests && go test ./properties/..."
        exit 0
    else
        print_error "Some validations failed. Please fix the issues above."
        echo ""
        echo "Common fixes:"
        echo "  • Run 'terraform fmt -recursive .' to fix formatting"
        echo "  • Check variable definitions and types"
        echo "  • Ensure all required providers are configured"
        echo "  • Review tflint output for specific issues"
        exit 1
    fi
}

# Run main function
main
