# App Layer - Bedrock RAG Deployment

This directory contains the Terraform configuration for deploying the AI workload resources in the US East region, including Bedrock Knowledge Base, OpenSearch Serverless, S3 pipeline, Lambda functions, and monitoring infrastructure.

## Prerequisites

1. **Network Layer Deployed**: The network-layer must be deployed first, as this app-layer depends on VPC, subnet, and security group outputs from the network layer.

2. **AWS Credentials**: Configure AWS credentials with appropriate permissions for deploying Bedrock, OpenSearch, S3, Lambda, IAM, KMS, CloudWatch, CloudTrail, and Budgets resources.

3. **Terraform Backend**: The S3 backend and DynamoDB table must be created (see `environments/global/backend/`).

## Architecture

This app-layer deploys the following components:

- **KMS**: Customer-managed encryption keys for all services
- **IAM**: Roles and policies for Bedrock, Lambda, and VPC Flow Logs
- **VPC Endpoints**: PrivateLink endpoints for Bedrock, S3, and OpenSearch
- **S3 Pipeline**: Document storage buckets with cross-region replication
- **Lambda**: Document processor for chunking and ingestion
- **Bedrock Knowledge Base**: RAG system with Claude and Titan models
- **OpenSearch Serverless**: Vector database for embeddings
- **CloudWatch**: Logs, alarms, and dashboards for monitoring
- **VPC Flow Logs**: Network traffic analysis
- **CloudTrail**: API audit logging
- **Network ACLs**: Additional network security layer
- **AWS Budgets**: Cost monitoring and alerts

## Deployment Steps

### 1. Configure Variables

Copy the example variables file and customize it:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your specific values:
- Update `sns_notification_emails` with your email addresses
- Adjust `monthly_budget_amount` based on your budget
- Customize bucket names to ensure global uniqueness
- Review OpenSearch capacity units based on workload

### 2. Initialize Terraform

```bash
terraform init
```

This will:
- Initialize the S3 backend
- Download required provider plugins
- Configure the remote state data source for network layer

### 3. Review the Plan

```bash
terraform plan
```

Review the planned changes carefully. Verify:
- Network layer outputs are correctly referenced
- All resource names follow naming conventions
- Tags are properly applied
- Security configurations are correct

### 4. Apply the Configuration

```bash
terraform apply
```

Type `yes` when prompted to confirm the deployment.

**Note**: The initial deployment may take 15-20 minutes due to:
- OpenSearch Serverless collection creation (~10 minutes)
- Bedrock Knowledge Base setup
- VPC endpoint provisioning
- CloudTrail trail activation

### 5. Verify Deployment

After successful deployment, verify the resources:

```bash
# Check Bedrock Knowledge Base
aws bedrock-agent list-knowledge-bases --region us-east-1

# Check OpenSearch collection
aws opensearchserverless list-collections --region us-east-1

# Check Lambda function
aws lambda get-function --function-name document-processor --region us-east-1

# Check CloudWatch dashboard
aws cloudwatch list-dashboards --region us-east-1

# Check CloudTrail
aws cloudtrail describe-trails --region us-east-1

# Check Budget
aws budgets describe-budgets --account-id $(aws sts get-caller-identity --query Account --output text)
```

## Usage

### Upload Documents

Upload documents to the Seoul S3 bucket for processing:

```bash
aws s3 cp document.pdf s3://bos-ai-documents-seoul/documents/
```

The document will be:
1. Replicated to the US bucket via cross-region replication
2. Processed by the Lambda function for chunking
3. Ingested into the Bedrock Knowledge Base
4. Vectorized and stored in OpenSearch

### Query the Knowledge Base

Query the Bedrock Knowledge Base:

```bash
aws bedrock-agent-runtime retrieve-and-generate \
  --knowledge-base-id <kb-id> \
  --input '{"text": "What is the architecture?"}' \
  --region us-east-1
```

### Monitor the System

- **CloudWatch Dashboard**: View metrics in the AWS Console under CloudWatch > Dashboards
- **CloudWatch Logs**: Check logs for Lambda, Bedrock, and VPC Flow Logs
- **CloudWatch Alarms**: Monitor alarm status and receive SNS notifications
- **CloudTrail**: Review API calls in CloudTrail console
- **AWS Budgets**: Track costs in AWS Budgets console

## Outputs

After deployment, Terraform outputs the following values:

- `knowledge_base_id`: Bedrock Knowledge Base ID
- `opensearch_collection_endpoint`: OpenSearch endpoint
- `lambda_function_arn`: Lambda function ARN
- `cloudwatch_dashboard_name`: Dashboard name
- `cloudtrail_arn`: CloudTrail ARN
- `budget_id`: Budget ID

View outputs:

```bash
terraform output
```

## Cost Estimation

Estimated monthly costs for this deployment:

- **Bedrock**: $50-500 (depends on usage)
- **OpenSearch Serverless**: $700-800 (minimum 4 OCU)
- **S3**: $5-20 (storage and replication)
- **Lambda**: $5-40 (depends on invocations)
- **Data Transfer**: $10-100 (cross-region)
- **CloudWatch**: $10-30 (logs and metrics)
- **CloudTrail**: $5-15 (API logging)
- **Other**: $10-20 (VPC endpoints, KMS, etc.)

**Total**: ~$800-1,500/month for baseline workload

## Troubleshooting

### OpenSearch Collection Creation Fails

If OpenSearch collection creation fails:
1. Check IAM permissions for OpenSearch Serverless
2. Verify VPC endpoint configuration
3. Check capacity unit limits in your account

### Lambda Function Fails

If Lambda function fails to process documents:
1. Check CloudWatch Logs: `/aws/lambda/document-processor`
2. Verify IAM role permissions
3. Check VPC configuration and security groups
4. Verify S3 event notification configuration

### Bedrock Knowledge Base Ingestion Fails

If ingestion jobs fail:
1. Check Bedrock CloudWatch logs
2. Verify IAM role has access to S3 and OpenSearch
3. Check KMS key policy allows Bedrock access
4. Verify OpenSearch collection is active

### CloudTrail Not Logging

If CloudTrail is not logging events:
1. Verify S3 bucket policy allows CloudTrail writes
2. Check trail is enabled and logging
3. Verify KMS key policy (if using encryption)

## Cleanup

To destroy all resources:

```bash
terraform destroy
```

**Warning**: This will delete:
- All S3 buckets and their contents
- OpenSearch collection and all vectors
- Bedrock Knowledge Base
- All CloudWatch logs
- CloudTrail logs
- All other resources

Make sure to backup any important data before destroying.

## Dependencies

This app-layer depends on the network-layer outputs:
- `us_vpc_id`: VPC ID for US region
- `us_private_subnet_ids`: Private subnet IDs
- `us_security_group_ids`: Security group IDs
- `us_vpc_cidr`: VPC CIDR block
- `seoul_vpc_cidr`: Seoul VPC CIDR (for Network ACLs)

## Module Structure

```
app-layer/bedrock-rag/
├── backend.tf              # S3 backend configuration
├── providers.tf            # AWS provider configuration
├── variables.tf            # Input variables
├── data.tf                 # Remote state and data sources
├── main.tf                 # Main resource configuration
├── outputs.tf              # Output values
├── terraform.tfvars.example # Example variables
└── README.md               # This file
```

## Related Documentation

- [Network Layer README](../../network-layer/README.md)
- [Design Document](../../../.kiro/specs/aws-bedrock-rag-deployment/design.md)
- [Requirements Document](../../../.kiro/specs/aws-bedrock-rag-deployment/requirements.md)
- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [OpenSearch Serverless Documentation](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless.html)
