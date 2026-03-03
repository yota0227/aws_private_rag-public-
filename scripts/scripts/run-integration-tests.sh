#!/bin/bash

# Integration Tests Runner Script
# This script runs Terratest integration tests for AWS Bedrock RAG infrastructure

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
TIMEOUT="60m"
PARALLEL="2"
SKIP_CLEANUP="false"
TEST_PATTERN=""
VERBOSE="true"

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

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    local all_ok=true
    
    # Check Go
    if command -v go &> /dev/null; then
        GO_VERSION=$(go version | awk '{print $3}')
        print_success "Go installed: $GO_VERSION"
    else
        print_error "Go not found. Please install Go 1.21+"
        all_ok=false
    fi
    
    # Check Terraform
    if command -v terraform &> /dev/null; then
        TERRAFORM_VERSION=$(terraform version -json | grep -o '"terraform_version":"[^"]*' | cut -d'"' -f4)
        print_success "Terraform installed: v$TERRAFORM_VERSION"
    else
        print_error "Terraform not found. Please install Terraform 1.5+"
        all_ok=false
    fi
    
    # Check AWS CLI
    if command -v aws &> /dev/null; then
        AWS_VERSION=$(aws --version | awk '{print $1}')
        print_success "AWS CLI installed: $AWS_VERSION"
    else
        print_error "AWS CLI not found. Please install AWS CLI v2+"
        all_ok=false
    fi
    
    # Check AWS credentials
    if aws sts get-caller-identity &> /dev/null; then
        AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
        AWS_USER=$(aws sts get-caller-identity --query Arn --output text | cut -d'/' -f2)
        print_success "AWS credentials configured: $AWS_USER (Account: $AWS_ACCOUNT)"
    else
        print_error "AWS credentials not configured. Run 'aws configure'"
        all_ok=false
    fi
    
    if [ "$all_ok" = false ]; then
        exit 1
    fi
}

# Check Bedrock model access
check_bedrock_access() {
    print_header "Checking Bedrock Model Access"
    
    print_info "Checking Bedrock model access in us-east-1..."
    
    # Note: This requires bedrock:ListFoundationModels permission
    if aws bedrock list-foundation-models --region us-east-1 &> /dev/null; then
        print_success "Bedrock API accessible"
        print_warning "Ensure you have enabled access to Claude v2 and Titan Embeddings"
        print_info "Check: AWS Console → Bedrock → Model access"
    else
        print_warning "Unable to verify Bedrock access (may require additional permissions)"
        print_info "Ensure Bedrock models are enabled before running tests"
    fi
}

# Install Go dependencies
install_dependencies() {
    print_header "Installing Go Dependencies"
    
    cd tests/integration
    
    if [ ! -f "go.mod" ]; then
        print_info "Initializing Go module..."
        go mod init integration
    fi
    
    print_info "Downloading dependencies..."
    go get github.com/gruntwork-io/terratest/modules/terraform
    go get github.com/gruntwork-io/terratest/modules/aws
    go get github.com/gruntwork-io/terratest/modules/random
    go get github.com/gruntwork-io/terratest/modules/test-structure
    go get github.com/stretchr/testify/assert
    go get github.com/stretchr/testify/require
    go get github.com/aws/aws-sdk-go/aws
    go get github.com/aws/aws-sdk-go/service/ec2
    go get github.com/aws/aws-sdk-go/service/s3
    go get github.com/aws/aws-sdk-go/service/lambda
    go get github.com/aws/aws-sdk-go/service/bedrockagent
    
    go mod tidy
    
    print_success "Dependencies installed"
    
    cd ../..
}

# Run tests
run_tests() {
    print_header "Running Integration Tests"
    
    cd tests/integration
    
    # Build test command
    local test_cmd="go test"
    
    if [ "$VERBOSE" = "true" ]; then
        test_cmd="$test_cmd -v"
    fi
    
    test_cmd="$test_cmd -timeout $TIMEOUT"
    test_cmd="$test_cmd -parallel $PARALLEL"
    
    if [ -n "$TEST_PATTERN" ]; then
        test_cmd="$test_cmd -run $TEST_PATTERN"
    fi
    
    # Set environment variables
    if [ "$SKIP_CLEANUP" = "true" ]; then
        export SKIP_cleanup=true
        print_warning "Cleanup stage will be skipped - resources will not be destroyed"
    fi
    
    print_info "Running: $test_cmd"
    echo ""
    
    # Run tests
    if eval "$test_cmd"; then
        print_success "All tests passed!"
        cd ../..
        return 0
    else
        print_error "Some tests failed"
        cd ../..
        return 1
    fi
}

# Estimate costs
estimate_costs() {
    print_header "Cost Estimation"
    
    echo "Integration tests deploy real AWS resources that incur costs:"
    echo ""
    echo "Estimated costs per test run:"
    echo "  • VPC Peering Test:        ~\$0.10"
    echo "  • S3 Replication Test:     ~\$0.05"
    echo "  • Lambda Invocation Test:  ~\$0.02"
    echo "  • Bedrock KB Test:         ~\$5-10 (OpenSearch Serverless)"
    echo ""
    echo "Total estimated cost:        ~\$5-15 per full test run"
    echo ""
    print_warning "Ensure cleanup runs to minimize costs!"
    echo ""
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Run Terratest integration tests for AWS Bedrock RAG infrastructure.

Options:
  -h, --help              Show this help message
  -t, --timeout DURATION  Test timeout (default: 60m)
  -p, --parallel N        Number of parallel tests (default: 2)
  -r, --run PATTERN       Run only tests matching pattern
  -s, --skip-cleanup      Skip cleanup stage (keep resources)
  -q, --quiet             Quiet mode (less verbose output)
  --install-deps          Install Go dependencies only
  --check-only            Check prerequisites only

Examples:
  $0                                    # Run all tests
  $0 -r TestVPCPeering                  # Run VPC peering tests only
  $0 -t 90m -p 4                        # 90 minute timeout, 4 parallel tests
  $0 -s -r TestS3Replication            # Run S3 test, skip cleanup
  $0 --install-deps                     # Install dependencies only

Test Patterns:
  TestVPCPeeringConnectivity            # VPC peering tests
  TestS3CrossRegionReplication          # S3 replication tests
  TestLambdaS3EventTrigger              # Lambda invocation tests
  TestBedrockKnowledgeBase              # Bedrock KB tests

Environment Variables:
  AWS_PROFILE                           # AWS profile to use
  AWS_DEFAULT_REGION                    # AWS region (default: us-east-1)
  SKIP_cleanup                          # Skip cleanup stage
  SKIP_setup                            # Skip setup stage (use existing resources)

Cost Warning:
  Integration tests deploy real AWS resources that incur costs.
  Estimated cost: \$5-15 per full test run.
  Always ensure cleanup runs to minimize costs.

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            -p|--parallel)
                PARALLEL="$2"
                shift 2
                ;;
            -r|--run)
                TEST_PATTERN="$2"
                shift 2
                ;;
            -s|--skip-cleanup)
                SKIP_CLEANUP="true"
                shift
                ;;
            -q|--quiet)
                VERBOSE="false"
                shift
                ;;
            --install-deps)
                check_prerequisites
                install_dependencies
                exit 0
                ;;
            --check-only)
                check_prerequisites
                check_bedrock_access
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# Main function
main() {
    print_header "AWS Bedrock RAG Integration Tests"
    
    # Check prerequisites
    check_prerequisites
    check_bedrock_access
    
    # Show cost estimation
    estimate_costs
    
    # Ask for confirmation
    if [ "$SKIP_CLEANUP" = "false" ]; then
        read -p "Continue with tests? Resources will be created and destroyed. (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Tests cancelled"
            exit 0
        fi
    else
        print_warning "Cleanup is disabled - resources will NOT be destroyed"
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Tests cancelled"
            exit 0
        fi
    fi
    
    # Install dependencies
    install_dependencies
    
    # Run tests
    if run_tests; then
        print_header "Test Summary"
        print_success "All integration tests passed!"
        echo ""
        echo "Next steps:"
        echo "  1. Review test output above"
        echo "  2. Check AWS Console for resource cleanup"
        echo "  3. Review AWS costs in Cost Explorer"
        exit 0
    else
        print_header "Test Summary"
        print_error "Some integration tests failed"
        echo ""
        echo "Troubleshooting:"
        echo "  1. Check test output for error details"
        echo "  2. Review CloudWatch Logs"
        echo "  3. Verify AWS service quotas"
        echo "  4. Check Bedrock model access"
        echo "  5. Ensure sufficient IAM permissions"
        echo ""
        echo "Manual cleanup (if needed):"
        echo "  cd environments/network-layer && terraform destroy"
        echo "  cd environments/app-layer/bedrock-rag && terraform destroy"
        exit 1
    fi
}

# Parse arguments and run
parse_args "$@"
main
