#!/bin/bash

# AWS Bedrock RAG Cost Estimation Script
# This script calculates estimated monthly costs for the AWS Bedrock RAG infrastructure

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
REGION_SEOUL="ap-northeast-2"
REGION_US="us-east-1"
PROJECT_TAG="BOS-AI-RAG"

# Usage scenarios
SCENARIO="${1:-baseline}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AWS Bedrock RAG Cost Estimation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to print section header
print_header() {
    echo -e "${GREEN}$1${NC}"
    echo "----------------------------------------"
}

# Function to print cost line
print_cost() {
    local service=$1
    local cost=$2
    local details=$3
    printf "%-30s: $%8.2f  %s\n" "$service" "$cost" "$details"
}

# Function to calculate Bedrock costs
calculate_bedrock_cost() {
    local scenario=$1
    local monthly_queries=$2
    local tokens_per_query=$3
    local embedding_tokens=$4
    
    # Pricing (as of 2024, approximate)
    # Claude v2: $0.008 per 1K input tokens, $0.024 per 1K output tokens
    # Titan Embeddings: $0.0001 per 1K tokens
    
    local input_tokens=$((monthly_queries * tokens_per_query))
    local output_tokens=$((monthly_queries * tokens_per_query / 2))  # Assume output is half of input
    
    local claude_input_cost=$(echo "scale=2; $input_tokens / 1000 * 0.008" | bc)
    local claude_output_cost=$(echo "scale=2; $output_tokens / 1000 * 0.024" | bc)
    local embedding_cost=$(echo "scale=2; $embedding_tokens / 1000 * 0.0001" | bc)
    
    local total=$(echo "scale=2; $claude_input_cost + $claude_output_cost + $embedding_cost" | bc)
    
    echo "$total"
}

# Function to calculate OpenSearch Serverless costs
calculate_opensearch_cost() {
    local search_ocu=$1
    local indexing_ocu=$2
    
    # Pricing: $0.24 per OCU-hour
    local hours_per_month=730
    local cost_per_ocu_hour=0.24
    
    local total_ocu=$((search_ocu + indexing_ocu))
    local total=$(echo "scale=2; $total_ocu * $hours_per_month * $cost_per_ocu_hour" | bc)
    
    echo "$total"
}

# Function to calculate S3 costs
calculate_s3_cost() {
    local storage_gb=$1
    local requests=$2
    
    # Pricing (Intelligent-Tiering)
    # Storage: $0.023 per GB (Frequent Access)
    # PUT requests: $0.005 per 1,000 requests
    # GET requests: $0.0004 per 1,000 requests
    # Monitoring: $0.0025 per 1,000 objects
    
    local storage_cost=$(echo "scale=2; $storage_gb * 0.023" | bc)
    local put_cost=$(echo "scale=2; $requests / 1000 * 0.005" | bc)
    local get_cost=$(echo "scale=2; $requests * 2 / 1000 * 0.0004" | bc)  # Assume 2x GET vs PUT
    local monitoring_cost=$(echo "scale=2; $requests / 1000 * 0.0025" | bc)
    
    local total=$(echo "scale=2; $storage_cost + $put_cost + $get_cost + $monitoring_cost" | bc)
    
    echo "$total"
}

# Function to calculate Lambda costs
calculate_lambda_cost() {
    local invocations=$1
    local avg_duration_ms=$2
    local memory_mb=$3
    
    # Pricing
    # Requests: $0.20 per 1M requests
    # Duration: $0.0000166667 per GB-second
    
    local request_cost=$(echo "scale=2; $invocations / 1000000 * 0.20" | bc)
    
    local gb_memory=$(echo "scale=4; $memory_mb / 1024" | bc)
    local duration_seconds=$(echo "scale=2; $avg_duration_ms / 1000" | bc)
    local gb_seconds=$(echo "scale=2; $invocations * $gb_memory * $duration_seconds" | bc)
    local duration_cost=$(echo "scale=2; $gb_seconds * 0.0000166667" | bc)
    
    local total=$(echo "scale=2; $request_cost + $duration_cost" | bc)
    
    echo "$total"
}

# Function to calculate Data Transfer costs
calculate_data_transfer_cost() {
    local cross_region_gb=$1
    
    # Pricing: $0.02 per GB for cross-region transfer
    local total=$(echo "scale=2; $cross_region_gb * 0.02" | bc)
    
    echo "$total"
}

# Function to calculate VPC costs
calculate_vpc_cost() {
    local vpc_endpoints=$1
    
    # Pricing: $0.01 per VPC endpoint per hour
    local hours_per_month=730
    local total=$(echo "scale=2; $vpc_endpoints * $hours_per_month * 0.01" | bc)
    
    echo "$total"
}

# Function to calculate CloudWatch costs
calculate_cloudwatch_cost() {
    local log_ingestion_gb=$1
    local metrics=$2
    local alarms=$3
    
    # Pricing
    # Logs ingestion: $0.50 per GB
    # Logs storage: $0.03 per GB (assume 1 month retention)
    # Custom metrics: $0.30 per metric
    # Alarms: $0.10 per alarm
    
    local ingestion_cost=$(echo "scale=2; $log_ingestion_gb * 0.50" | bc)
    local storage_cost=$(echo "scale=2; $log_ingestion_gb * 0.03" | bc)
    local metrics_cost=$(echo "scale=2; $metrics * 0.30" | bc)
    local alarms_cost=$(echo "scale=2; $alarms * 0.10" | bc)
    
    local total=$(echo "scale=2; $ingestion_cost + $storage_cost + $metrics_cost + $alarms_cost" | bc)
    
    echo "$total"
}

# Scenario configurations
case $SCENARIO in
    "baseline"|"low")
        print_header "Scenario: Baseline (Low Usage)"
        echo "Document Storage: 100GB"
        echo "Monthly Queries: 10,000"
        echo "Embedding Tokens: 1,000,000/month"
        echo ""
        
        STORAGE_GB=100
        MONTHLY_QUERIES=10000
        TOKENS_PER_QUERY=500
        EMBEDDING_TOKENS=1000000
        SEARCH_OCU=2
        INDEXING_OCU=2
        LAMBDA_INVOCATIONS=1000
        LAMBDA_DURATION_MS=5000
        LAMBDA_MEMORY_MB=1024
        CROSS_REGION_GB=10
        VPC_ENDPOINTS=4
        LOG_INGESTION_GB=5
        CUSTOM_METRICS=20
        ALARMS=10
        ;;
        
    "medium")
        print_header "Scenario: Medium (Moderate Usage)"
        echo "Document Storage: 500GB"
        echo "Monthly Queries: 50,000"
        echo "Embedding Tokens: 5,000,000/month"
        echo ""
        
        STORAGE_GB=500
        MONTHLY_QUERIES=50000
        TOKENS_PER_QUERY=500
        EMBEDDING_TOKENS=5000000
        SEARCH_OCU=4
        INDEXING_OCU=4
        LAMBDA_INVOCATIONS=5000
        LAMBDA_DURATION_MS=5000
        LAMBDA_MEMORY_MB=1024
        CROSS_REGION_GB=50
        VPC_ENDPOINTS=4
        LOG_INGESTION_GB=20
        CUSTOM_METRICS=30
        ALARMS=15
        ;;
        
    "high")
        print_header "Scenario: High (Heavy Usage)"
        echo "Document Storage: 2TB (2048GB)"
        echo "Monthly Queries: 200,000"
        echo "Embedding Tokens: 20,000,000/month"
        echo ""
        
        STORAGE_GB=2048
        MONTHLY_QUERIES=200000
        TOKENS_PER_QUERY=500
        EMBEDDING_TOKENS=20000000
        SEARCH_OCU=8
        INDEXING_OCU=8
        LAMBDA_INVOCATIONS=20000
        LAMBDA_DURATION_MS=5000
        LAMBDA_MEMORY_MB=1024
        CROSS_REGION_GB=200
        VPC_ENDPOINTS=4
        LOG_INGESTION_GB=80
        CUSTOM_METRICS=40
        ALARMS=20
        ;;
        
    *)
        echo -e "${RED}Error: Unknown scenario '$SCENARIO'${NC}"
        echo "Usage: $0 [baseline|medium|high]"
        exit 1
        ;;
esac

# Calculate costs
print_header "Cost Breakdown by Service"

BEDROCK_COST=$(calculate_bedrock_cost "$SCENARIO" $MONTHLY_QUERIES $TOKENS_PER_QUERY $EMBEDDING_TOKENS)
print_cost "AWS Bedrock" "$BEDROCK_COST" "(Claude + Titan Embeddings)"

OPENSEARCH_COST=$(calculate_opensearch_cost $SEARCH_OCU $INDEXING_OCU)
print_cost "OpenSearch Serverless" "$OPENSEARCH_COST" "($SEARCH_OCU search + $INDEXING_OCU indexing OCU)"

S3_COST=$(calculate_s3_cost $STORAGE_GB $LAMBDA_INVOCATIONS)
print_cost "S3 Storage" "$S3_COST" "(${STORAGE_GB}GB Intelligent-Tiering)"

LAMBDA_COST=$(calculate_lambda_cost $LAMBDA_INVOCATIONS $LAMBDA_DURATION_MS $LAMBDA_MEMORY_MB)
print_cost "Lambda" "$LAMBDA_COST" "($LAMBDA_INVOCATIONS invocations)"

DATA_TRANSFER_COST=$(calculate_data_transfer_cost $CROSS_REGION_GB)
print_cost "Data Transfer" "$DATA_TRANSFER_COST" "(${CROSS_REGION_GB}GB cross-region)"

VPC_COST=$(calculate_vpc_cost $VPC_ENDPOINTS)
print_cost "VPC Endpoints" "$VPC_COST" "($VPC_ENDPOINTS endpoints)"

CLOUDWATCH_COST=$(calculate_cloudwatch_cost $LOG_INGESTION_GB $CUSTOM_METRICS $ALARMS)
print_cost "CloudWatch" "$CLOUDWATCH_COST" "(Logs, Metrics, Alarms)"

# Additional services (estimated)
KMS_COST=2.00
print_cost "KMS" "$KMS_COST" "(Customer-managed keys)"

CLOUDTRAIL_COST=5.00
print_cost "CloudTrail" "$CLOUDTRAIL_COST" "(API logging)"

DYNAMODB_COST=1.00
print_cost "DynamoDB" "$DYNAMODB_COST" "(State locking)"

OTHER_COST=10.00
print_cost "Other Services" "$OTHER_COST" "(NAT, Route53, etc.)"

echo ""
print_header "Total Estimated Monthly Cost"

TOTAL_COST=$(echo "scale=2; $BEDROCK_COST + $OPENSEARCH_COST + $S3_COST + $LAMBDA_COST + $DATA_TRANSFER_COST + $VPC_COST + $CLOUDWATCH_COST + $KMS_COST + $CLOUDTRAIL_COST + $DYNAMODB_COST + $OTHER_COST" | bc)

echo -e "${YELLOW}Total: \$$TOTAL_COST/month${NC}"
echo ""

# Cost breakdown percentages
print_header "Cost Distribution"

BEDROCK_PCT=$(echo "scale=1; $BEDROCK_COST / $TOTAL_COST * 100" | bc)
OPENSEARCH_PCT=$(echo "scale=1; $OPENSEARCH_COST / $TOTAL_COST * 100" | bc)
S3_PCT=$(echo "scale=1; $S3_COST / $TOTAL_COST * 100" | bc)
LAMBDA_PCT=$(echo "scale=1; $LAMBDA_COST / $TOTAL_COST * 100" | bc)
DATA_TRANSFER_PCT=$(echo "scale=1; $DATA_TRANSFER_COST / $TOTAL_COST * 100" | bc)
OTHER_PCT=$(echo "scale=1; ($VPC_COST + $CLOUDWATCH_COST + $KMS_COST + $CLOUDTRAIL_COST + $DYNAMODB_COST + $OTHER_COST) / $TOTAL_COST * 100" | bc)

printf "%-30s: %5.1f%%\n" "Bedrock" "$BEDROCK_PCT"
printf "%-30s: %5.1f%%\n" "OpenSearch Serverless" "$OPENSEARCH_PCT"
printf "%-30s: %5.1f%%\n" "S3 Storage" "$S3_PCT"
printf "%-30s: %5.1f%%\n" "Lambda" "$LAMBDA_PCT"
printf "%-30s: %5.1f%%\n" "Data Transfer" "$DATA_TRANSFER_PCT"
printf "%-30s: %5.1f%%\n" "Other Services" "$OTHER_PCT"

echo ""
print_header "Cost Optimization Recommendations"

# Provide recommendations based on scenario
if [ "$SCENARIO" = "baseline" ] || [ "$SCENARIO" = "low" ]; then
    echo "✓ Current configuration is cost-optimized for low usage"
    echo "✓ OpenSearch OCU is at minimum (2+2)"
    echo "✓ Consider S3 lifecycle policies for older documents"
elif [ "$SCENARIO" = "medium" ]; then
    echo "• Monitor OpenSearch OCU usage - may need adjustment"
    echo "• Implement S3 lifecycle policies to move old data to Glacier"
    echo "• Review Lambda memory allocation for optimization"
    echo "• Consider Reserved Capacity for predictable workloads"
elif [ "$SCENARIO" = "high" ]; then
    echo "⚠ High usage detected - consider these optimizations:"
    echo "  1. Implement aggressive S3 lifecycle policies"
    echo "  2. Review and optimize Lambda execution time"
    echo "  3. Consider Bedrock Provisioned Throughput for cost savings"
    echo "  4. Optimize OpenSearch index settings"
    echo "  5. Implement caching layer for frequent queries"
    echo "  6. Review data transfer patterns to minimize cross-region costs"
fi

echo ""
print_header "Key Cost Drivers"

# Identify top 3 cost drivers
echo "1. OpenSearch Serverless (largest fixed cost)"
echo "   - Minimum 4 OCU (2 search + 2 indexing) = ~\$700/month"
echo "   - Consider workload patterns for OCU optimization"
echo ""
echo "2. AWS Bedrock (variable based on usage)"
echo "   - Scales with query volume and token usage"
echo "   - Optimize prompt engineering to reduce tokens"
echo ""
echo "3. Data Transfer (cross-region)"
echo "   - Minimize unnecessary data movement"
echo "   - Consider regional data processing where possible"

echo ""
print_header "Monitoring and Alerts"

echo "Set up AWS Budgets alerts at:"
echo "  • 50% of estimated cost: \$$(echo "scale=2; $TOTAL_COST * 0.5" | bc)"
echo "  • 80% of estimated cost: \$$(echo "scale=2; $TOTAL_COST * 0.8" | bc)"
echo "  • 100% of estimated cost: \$$(echo "scale=2; $TOTAL_COST" | bc)"
echo ""
echo "Monitor these metrics weekly:"
echo "  • OpenSearch OCU utilization"
echo "  • Bedrock token usage"
echo "  • Lambda execution duration"
echo "  • S3 storage growth"
echo "  • Cross-region data transfer"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Estimation Complete${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Note: These are estimates based on AWS pricing as of 2024."
echo "Actual costs may vary based on:"
echo "  • Specific usage patterns"
echo "  • Regional pricing differences"
echo "  • AWS pricing changes"
echo "  • Reserved capacity or savings plans"
echo ""
echo "For accurate cost tracking, use:"
echo "  • AWS Cost Explorer"
echo "  • AWS Budgets"
echo "  • Cost allocation tags"
echo ""
echo "Run this script with different scenarios:"
echo "  $0 baseline  # Low usage"
echo "  $0 medium    # Moderate usage"
echo "  $0 high      # Heavy usage"
echo ""
