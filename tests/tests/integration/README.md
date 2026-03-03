# Integration Tests

This directory contains Terratest integration tests for the AWS Bedrock RAG infrastructure.

## Overview

Integration tests validate the actual deployment of infrastructure components and their interactions. These tests:

- Deploy real AWS resources using Terraform
- Validate resource configurations
- Test cross-service integrations
- Verify end-to-end workflows
- Clean up resources after testing

## Test Files

### vpc_peering_test.go
Tests VPC peering connectivity between Seoul and US regions:
- VPC peering connection establishment
- Bidirectional routing configuration
- VPC CIDR non-overlap validation
- No-IGW policy enforcement
- Multi-AZ subnet distribution
- Network performance

### s3_replication_test.go
Tests S3 cross-region replication:
- S3 bucket creation and configuration
- Versioning and encryption
- Replication configuration
- Actual object replication
- Public access blocking

### lambda_invocation_test.go
Tests Lambda function deployment and invocation:
- Lambda function configuration
- S3 event trigger integration
- X-Ray tracing
- Dead Letter Queue configuration
- IAM permissions
- Performance characteristics

### bedrock_kb_test.go
Tests Bedrock Knowledge Base deployment:
- Knowledge Base creation
- OpenSearch Serverless integration
- Data source configuration
- Embedding model configuration
- Document ingestion
- Query functionality

## Prerequisites

### Required Tools

1. **Go** (v1.21+)
   ```bash
   go version
   ```

2. **Terraform** (v1.5+)
   ```bash
   terraform version
   ```

3. **AWS CLI** (v2.0+)
   ```bash
   aws --version
   ```

4. **Terratest**
   ```bash
   go get github.com/gruntwork-io/terratest/modules/terraform
   go get github.com/gruntwork-io/terratest/modules/aws
   go get github.com/gruntwork-io/terratest/modules/random
   go get github.com/gruntwork-io/terratest/modules/test-structure
   ```

### AWS Configuration

1. **AWS Credentials**
   ```bash
   aws configure
   ```

2. **Required Permissions**
   - VPC, Subnet, Route Table management
   - VPC Peering management
   - S3 bucket management
   - Lambda function management
   - Bedrock Knowledge Base management
   - OpenSearch Serverless management
   - IAM role and policy management
   - KMS key management
   - CloudWatch Logs access

3. **Bedrock Model Access**
   - Enable access to Anthropic Claude v2
   - Enable access to Amazon Titan Embeddings
   - Go to AWS Console → Bedrock → Model access

## Running Tests

### Run All Integration Tests

```bash
cd tests/integration
go test -v -timeout 60m
```

### Run Specific Test

```bash
# VPC Peering test
go test -v -timeout 30m -run TestVPCPeeringConnectivity

# S3 Replication test
go test -v -timeout 30m -run TestS3CrossRegionReplication

# Lambda Invocation test
go test -v -timeout 30m -run TestLambdaS3EventTrigger

# Bedrock Knowledge Base test
go test -v -timeout 30m -run TestBedrockKnowledgeBase
```

### Run Tests in Parallel

```bash
go test -v -timeout 60m -parallel 4
```

### Run with Specific AWS Profile

```bash
AWS_PROFILE=bos-ai go test -v -timeout 60m
```

### Run with Specific Region

```bash
AWS_DEFAULT_REGION=us-east-1 go test -v -timeout 60m
```

## Test Stages

Each test follows the Terratest test structure pattern:

1. **Setup**: Deploy infrastructure using Terraform
2. **Validate**: Run validation tests
3. **Cleanup**: Destroy infrastructure (deferred)

### Skipping Stages

You can skip specific stages for debugging:

```bash
# Skip cleanup (keep resources for inspection)
SKIP_cleanup=true go test -v -timeout 30m -run TestVPCPeeringConnectivity

# Skip setup (use existing resources)
SKIP_setup=true go test -v -timeout 30m -run TestVPCPeeringConnectivity
```

## Test Output

### Successful Test Output

```
=== RUN   TestVPCPeeringConnectivity
=== RUN   TestVPCPeeringConnectivity/VPCPeeringConnectionExists
=== RUN   TestVPCPeeringConnectivity/VPCPeeringConnectionActive
=== RUN   TestVPCPeeringConnectivity/BidirectionalRoutingConfigured
--- PASS: TestVPCPeeringConnectivity (300.45s)
    --- PASS: TestVPCPeeringConnectivity/VPCPeeringConnectionExists (0.50s)
    --- PASS: TestVPCPeeringConnectivity/VPCPeeringConnectionActive (1.20s)
    --- PASS: TestVPCPeeringConnectivity/BidirectionalRoutingConfigured (2.30s)
PASS
ok      integration     300.456s
```

### Failed Test Output

```
=== RUN   TestVPCPeeringConnectivity
=== RUN   TestVPCPeeringConnectivity/VPCPeeringConnectionActive
    vpc_peering_test.go:85: 
        Error Trace:    vpc_peering_test.go:85
        Error:          Not equal: 
                        expected: "active"
                        actual  : "pending-acceptance"
        Test:           TestVPCPeeringConnectivity/VPCPeeringConnectionActive
--- FAIL: TestVPCPeeringConnectivity (150.23s)
    --- FAIL: TestVPCPeeringConnectivity/VPCPeeringConnectionActive (1.20s)
FAIL
exit status 1
FAIL    integration     150.234s
```

## Cost Considerations

**WARNING**: Integration tests deploy real AWS resources that incur costs.

### Estimated Costs per Test Run

- **VPC Peering Test**: ~$0.10 (VPC, subnets, peering)
- **S3 Replication Test**: ~$0.05 (S3 buckets, minimal storage)
- **Lambda Test**: ~$0.02 (Lambda invocations)
- **Bedrock KB Test**: ~$5-10 (OpenSearch Serverless minimum 4 OCU for ~30 minutes)

**Total per full test run**: ~$5-15

### Cost Optimization Tips

1. **Run tests selectively**: Only run tests you need
2. **Use parallel execution**: Reduces total time
3. **Clean up promptly**: Ensure cleanup stage runs
4. **Monitor costs**: Use AWS Cost Explorer
5. **Set budget alerts**: Configure AWS Budgets

## Troubleshooting

### Test Timeout

If tests timeout, increase the timeout:

```bash
go test -v -timeout 90m
```

### Resource Cleanup Failures

If cleanup fails, manually destroy resources:

```bash
cd environments/network-layer
terraform destroy

cd ../app-layer/bedrock-rag
terraform destroy
```

### AWS Rate Limiting

If you encounter rate limiting errors:

1. Add retry logic (already included in Terratest)
2. Reduce parallel test execution
3. Add delays between tests

### Bedrock Model Access Denied

If you get "AccessDeniedException" for Bedrock:

1. Go to AWS Console → Bedrock → Model access
2. Request access to required models
3. Wait for approval (usually instant)

### OpenSearch Capacity Errors

If OpenSearch Serverless fails to create:

1. Check service quotas in AWS Console
2. Ensure minimum 2 OCU for search and indexing
3. Verify region supports OpenSearch Serverless

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Integration Tests

on:
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # Run daily at 2 AM

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 90
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Go
        uses: actions/setup-go@v4
        with:
          go-version: '1.21'
      
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: '1.5.0'
      
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      
      - name: Run Integration Tests
        run: |
          cd tests/integration
          go test -v -timeout 60m
        env:
          AWS_DEFAULT_REGION: us-east-1
```

## Best Practices

1. **Always run cleanup**: Use `defer` to ensure resources are destroyed
2. **Use unique IDs**: Prevent naming conflicts with `random.UniqueId()`
3. **Test in isolation**: Each test should be independent
4. **Validate thoroughly**: Check all critical configurations
5. **Handle errors gracefully**: Use `require` for critical checks, `assert` for non-critical
6. **Log useful information**: Use `t.Logf()` for debugging
7. **Set appropriate timeouts**: Integration tests can take time
8. **Monitor costs**: Track AWS spending during test development

## Additional Resources

- [Terratest Documentation](https://terratest.gruntwork.io/)
- [AWS SDK for Go](https://aws.github.io/aws-sdk-go-v2/)
- [Terraform Testing Best Practices](https://www.terraform.io/docs/language/modules/testing-experiment.html)
- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)

## Support

For issues or questions:

1. Check test logs for detailed error messages
2. Review AWS CloudWatch Logs
3. Verify AWS service quotas
4. Consult team documentation
5. Contact infrastructure team
