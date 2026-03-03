# KMS Module

This module creates AWS KMS customer-managed keys with service principal access for the BOS AI RAG infrastructure.

## Features

- Customer-managed KMS keys for encryption at rest
- Automatic key rotation enabled by default
- Service principal access for Bedrock, S3, and OpenSearch Serverless
- Configurable key administrators and users
- Key alias for friendly naming

## Requirements

- Terraform >= 1.5
- AWS Provider >= 5.0

## Usage

```hcl
module "kms" {
  source = "../../modules/security/kms"

  key_description = "KMS key for BOS AI RAG infrastructure"
  region          = "us-east-1"

  enable_bedrock_access    = true
  enable_s3_access         = true
  enable_opensearch_access = true

  additional_key_admins = [
    "arn:aws:iam::123456789012:role/admin-role"
  ]

  additional_key_users = [
    "arn:aws:iam::123456789012:role/bedrock-kb-role",
    "arn:aws:iam::123456789012:role/lambda-execution-role"
  ]

  tags = {
    Project     = "BOS-AI-RAG"
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|----------|
| key_description | Description for the KMS key | string | "KMS key for BOS AI RAG infrastructure encryption" | no |
| deletion_window_in_days | Duration in days after which the key is deleted | number | 30 | no |
| enable_key_rotation | Enable automatic key rotation | bool | true | no |
| enable_bedrock_access | Grant Bedrock service principal access | bool | true | no |
| enable_s3_access | Grant S3 service principal access | bool | true | no |
| enable_opensearch_access | Grant OpenSearch service principal access | bool | true | no |
| additional_key_admins | List of IAM ARNs that can administer the key | list(string) | [] | no |
| additional_key_users | List of IAM ARNs that can use the key | list(string) | [] | no |
| region | AWS region for the KMS key | string | - | yes |
| tags | Tags to apply to the KMS key | map(string) | {} | no |

## Outputs

| Name | Description |
|------|-------------|
| key_id | ID of the KMS key |
| key_arn | ARN of the KMS key |
| key_alias_name | Alias name of the KMS key |
| key_alias_arn | ARN of the KMS key alias |
| key_policy | Policy document for the KMS key (sensitive) |

## Key Policy

The module creates a comprehensive key policy that includes:

1. **Root Account Access**: Allows the AWS account root to manage the key
2. **Key Administrators**: Grants full key management permissions to specified IAM principals
3. **Key Users**: Grants encryption/decryption permissions to specified IAM principals
4. **Bedrock Service**: Allows Bedrock to decrypt and generate data keys
5. **S3 Service**: Allows S3 to decrypt and generate data keys for bucket encryption
6. **OpenSearch Service**: Allows OpenSearch Serverless to decrypt and create grants
7. **Lambda Service** (optional): Allows Lambda to decrypt and generate data keys

All service principal access is scoped to the specific region using `kms:ViaService` conditions.

## Security Considerations

- Key rotation is enabled by default and should remain enabled for production use
- Service principal access is restricted to the specified region
- Additional key users should follow the principle of least privilege
- The key policy is marked as sensitive in outputs to prevent accidental exposure

## Requirements Validation

This module validates:
- **Requirement 5.4**: KMS customer-managed keys are used
- **Requirement 5.5**: Bedrock service principal has key access
- **Requirement 5.6**: S3 and OpenSearch service principals have key access
