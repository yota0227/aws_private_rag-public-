#!/bin/bash

# Policy-as-Code Testing Script
# This script runs OPA/Conftest policy tests on Terraform configurations

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories to test
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
)

# Policy directories
POLICY_DIR="policies"

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
WARNINGS=0

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
}

# Function to print error
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Function to print info
print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if conftest is installed
check_conftest() {
    print_header "Checking Prerequisites"
    
    if command -v conftest &> /dev/null; then
        CONFTEST_VERSION=$(conftest --version | head -n1)
        print_success "Conftest installed: $CONFTEST_VERSION"
        return 0
    else
        print_error "Conftest not found"
        echo ""
        echo "Install Conftest:"
        echo "  macOS:   brew install conftest"
        echo "  Linux:   wget https://github.com/open-policy-agent/conftest/releases/download/v0.48.0/conftest_0.48.0_Linux_x86_64.tar.gz"
        echo "           tar xzf conftest_0.48.0_Linux_x86_64.tar.gz"
        echo "           sudo mv conftest /usr/local/bin/"
        echo "  Windows: choco install conftest"
        echo ""
        echo "Or visit: https://www.conftest.dev/install/"
        exit 1
    fi
}

# Check if policy files exist
check_policies() {
    if [ ! -d "$POLICY_DIR" ]; then
        print_error "Policy directory not found: $POLICY_DIR"
        exit 1
    fi
    
    if [ ! -f "$POLICY_DIR/security.rego" ]; then
        print_error "Security policy not found: $POLICY_DIR/security.rego"
        exit 1
    fi
    
    if [ ! -f "$POLICY_DIR/compliance.rego" ]; then
        print_error "Compliance policy not found: $POLICY_DIR/compliance.rego"
        exit 1
    fi
    
    if [ ! -f "$POLICY_DIR/cost.rego" ]; then
        print_error "Cost policy not found: $POLICY_DIR/cost.rego"
        exit 1
    fi
    
    print_success "All policy files found"
}

# Test policies syntax
test_policy_syntax() {
    print_header "Testing Policy Syntax"
    
    for policy in "$POLICY_DIR"/*.rego; do
        print_info "Checking syntax: $(basename $policy)"
        if conftest verify -p "$policy" > /dev/null 2>&1; then
            print_success "Syntax valid: $(basename $policy)"
            ((PASSED_TESTS++))
        else
            print_error "Syntax error: $(basename $policy)"
            conftest verify -p "$policy"
            ((FAILED_TESTS++))
        fi
        ((TOTAL_TESTS++))
    done
}

# Run policy tests on a directory
test_directory() {
    local dir=$1
    
    if [ ! -d "$dir" ]; then
        print_warning "Directory not found: $dir (skipping)"
        return 0
    fi
    
    print_header "Testing: $dir"
    
    # Check if directory has .tf files
    if ! ls "$dir"/*.tf > /dev/null 2>&1; then
        print_warning "No .tf files found in $dir (skipping)"
        return 0
    fi
    
    ((TOTAL_TESTS++))
    
    # Run conftest test
    local output
    local exit_code
    
    output=$(conftest test "$dir"/*.tf -p "$POLICY_DIR" --all-namespaces 2>&1) || exit_code=$?
    
    if [ -z "$exit_code" ] || [ "$exit_code" -eq 0 ]; then
        print_success "All policies passed: $dir"
        ((PASSED_TESTS++))
        
        # Check for warnings
        if echo "$output" | grep -q "WARN"; then
            local warning_count=$(echo "$output" | grep -c "WARN" || true)
            print_warning "$warning_count warning(s) found"
            ((WARNINGS+=warning_count))
            echo "$output" | grep "WARN"
        fi
    else
        print_error "Policy violations found: $dir"
        ((FAILED_TESTS++))
        echo ""
        echo "$output"
        echo ""
    fi
}

# Run tests on specific policy
test_specific_policy() {
    local dir=$1
    local policy=$2
    
    if [ ! -d "$dir" ]; then
        return 0
    fi
    
    if ! ls "$dir"/*.tf > /dev/null 2>&1; then
        return 0
    fi
    
    print_info "Testing $policy policy on $dir"
    
    conftest test "$dir"/*.tf -p "$POLICY_DIR/$policy.rego" --all-namespaces || true
}

# Generate policy report
generate_report() {
    local report_file="policy-test-report.txt"
    
    print_header "Generating Policy Report"
    
    {
        echo "Policy Test Report"
        echo "Generated: $(date)"
        echo "========================================"
        echo ""
        echo "Summary:"
        echo "  Total Tests: $TOTAL_TESTS"
        echo "  Passed: $PASSED_TESTS"
        echo "  Failed: $FAILED_TESTS"
        echo "  Warnings: $WARNINGS"
        echo ""
        echo "Tested Directories:"
        for dir in "${TERRAFORM_DIRS[@]}"; do
            echo "  - $dir"
        done
        echo ""
        echo "Policies Applied:"
        echo "  - Security Policy (security.rego)"
        echo "  - Compliance Policy (compliance.rego)"
        echo "  - Cost Optimization Policy (cost.rego)"
        echo ""
    } > "$report_file"
    
    print_success "Report generated: $report_file"
}

# Main function
main() {
    print_header "Policy-as-Code Testing"
    echo "Testing Terraform configurations against OPA policies"
    echo ""
    
    # Check prerequisites
    check_conftest
    check_policies
    
    # Test policy syntax
    test_policy_syntax
    
    # Test each directory
    for dir in "${TERRAFORM_DIRS[@]}"; do
        test_directory "$dir"
    done
    
    # Generate report
    generate_report
    
    # Print summary
    print_header "Test Summary"
    echo "Total Tests: $TOTAL_TESTS"
    echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
    echo -e "${RED}Failed: $FAILED_TESTS${NC}"
    echo -e "${YELLOW}Warnings: $WARNINGS${NC}"
    echo ""
    
    if [ $FAILED_TESTS -eq 0 ]; then
        print_success "All policy tests passed!"
        echo ""
        echo "Next steps:"
        echo "  1. Review warnings above"
        echo "  2. Run Terraform validation: ./scripts/terraform-validate.sh"
        echo "  3. Run property-based tests: cd tests && go test ./properties/..."
        echo "  4. Deploy infrastructure: terraform apply"
        exit 0
    else
        print_error "Some policy tests failed"
        echo ""
        echo "Common fixes:"
        echo "  • Add required tags (Project, Environment, ManagedBy, CostCenter)"
        echo "  • Enable S3 versioning and encryption"
        echo "  • Configure CloudWatch logging and alarms"
        echo "  • Remove AdministratorAccess policies"
        echo "  • Enable KMS key rotation"
        echo "  • Configure VPC endpoints"
        echo ""
        echo "For detailed policy requirements, see:"
        echo "  • policies/security.rego"
        echo "  • policies/compliance.rego"
        echo "  • policies/cost.rego"
        exit 1
    fi
}

# Parse command line arguments
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --help, -h          Show this help message"
    echo "  --security          Test only security policies"
    echo "  --compliance        Test only compliance policies"
    echo "  --cost              Test only cost policies"
    echo "  --dir <directory>   Test specific directory"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run all tests"
    echo "  $0 --security                         # Test security policies only"
    echo "  $0 --dir environments/network-layer   # Test specific directory"
    exit 0
fi

if [ "$1" == "--security" ]; then
    print_header "Testing Security Policies Only"
    check_conftest
    check_policies
    for dir in "${TERRAFORM_DIRS[@]}"; do
        test_specific_policy "$dir" "security"
    done
    exit 0
fi

if [ "$1" == "--compliance" ]; then
    print_header "Testing Compliance Policies Only"
    check_conftest
    check_policies
    for dir in "${TERRAFORM_DIRS[@]}"; do
        test_specific_policy "$dir" "compliance"
    done
    exit 0
fi

if [ "$1" == "--cost" ]; then
    print_header "Testing Cost Policies Only"
    check_conftest
    check_policies
    for dir in "${TERRAFORM_DIRS[@]}"; do
        test_specific_policy "$dir" "cost"
    done
    exit 0
fi

if [ "$1" == "--dir" ] && [ -n "$2" ]; then
    print_header "Testing Directory: $2"
    check_conftest
    check_policies
    test_directory "$2"
    exit 0
fi

# Run main function
main
