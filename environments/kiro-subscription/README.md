# Kiro Subscription - User Prompt Metadata Storage

## Overview

This Terraform configuration creates a secure S3 bucket for storing user prompt metadata in the Kiro subscription service. The bucket is configured with encryption, versioning, logging, and access controls.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Kiro Subscription                     │
│                   (us-east-1 / Virginia)                 │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │  S3 Bucket: kiro-user-prompts-metadata           │   │
│  │  ├─ User Prompts (JSON)                          │   │
│  │  ├─ Metadata (timestamps, user IDs, etc.)        │   │
│  │  ├─ Versioning: Enabled                          │   │
│  │  ├─ Encryption: KMS (aws:kms)                    │   │
│  │  └─ Access Logs: Enabled                         │   │
│  └──────────────────────────────────────────────────┘   │
│           │                                              │
│           ├─ KMS Key (kiro-prompts-key)                 │
│           │  └─ Encryption for all objects              │
│           │                                              │
│           └─ Access Logs Bucket                         │
│              └─ S3 access logs (90 days retention)      │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## Features

### Security
- **Encryption**: Server-side encryption with KMS
- **Access Control**: Block all public access
- **Transport Security**: Enforce HTTPS (SSL/TLS)
- **Audit Trail**: Versioning enabled for all objects

### Compliance
- **Logging**: S3 access logs stored in separate bucket
- **Retention**: Configurable log retention (default: 90 days)
- **Audit**: CloudWatch log group for monitoring
- **Encryption**: KMS key with automatic rotation

### Data Protection
- **Versioning**: All object versions preserved
- **MFA Delete**: Optional MFA delete protection
- **Lifecycle**: Automatic cleanup of old logs

## Deployment

### Prerequisites
1. AWS Account with appropriate permissions
2. Terraform >= 1.5.0
3. AWS CLI configured
4. S3 backend bucket (`bos-ai-terraform-state`) already created

### Steps

1. **Copy variables file**:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   ```

2. **Update variables** (if needed):
   ```bash
   # Edit terraform.tfvars with your values
   ```

3. **Initialize Terraform**:
   ```bash
   terraform init
   ```

4. **Review plan**:
   ```bash
   terraform plan
   ```

5. **Apply configuration**:
   ```bash
   terraform apply
   ```

## S3 Bucket Structure

```
s3://kiro-user-prompts-metadata-prod/
├── prompts/
│   ├── 2026/02/26/
│   │   ├── user-123/
│   │   │   ├── prompt-001.json
│   │   │   ├── prompt-002.json
│   │   │   └── ...
│   │   ├── user-456/
│   │   │   └── ...
│   │   └── ...
│   └── ...
├── metadata/
│   ├── user-profiles.json
│   ├── usage-statistics.json
│   └── ...
└── logs/
    └── access-logs/
        ├── 2026-02-26-10-00-00-...
        └── ...
```

## Metadata Schema

### User Prompt Object
```json
{
  "prompt_id": "uuid",
  "user_id": "user-123",
  "timestamp": "2026-02-26T10:30:00Z",
  "prompt_text": "...",
  "metadata": {
    "session_id": "session-456",
    "model": "claude-3-sonnet",
    "temperature": 0.7,
    "max_tokens": 2048,
    "tags": ["feature-request", "bug-report"],
    "source": "kiro-ide"
  },
  "response": {
    "response_id": "uuid",
    "tokens_used": 1234,
    "execution_time_ms": 2500
  }
}
```

## Access Control

### IAM Policy Example

For applications that need to write prompts:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::kiro-user-prompts-metadata-prod/prompts/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:GenerateDataKey"
      ],
      "Resource": "arn:aws:kms:us-east-1:ACCOUNT_ID:key/KEY_ID"
    }
  ]
}
```

## Monitoring

### CloudWatch Metrics
- S3 bucket size
- Number of objects
- Request count
- Error rate

### CloudWatch Logs
- S3 access logs
- KMS key usage
- Bucket policy violations

### Alarms (Optional)
```bash
# Create alarm for high error rate
aws cloudwatch put-metric-alarm \
  --alarm-name kiro-prompts-high-error-rate \
  --alarm-description "Alert when S3 error rate is high" \
  --metric-name 4xxErrors \
  --namespace AWS/S3 \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

## Cost Estimation

### Monthly Costs (Approximate)
- **S3 Storage**: $0.023 per GB
- **KMS**: $1.00 per key + $0.03 per 10,000 requests
- **CloudWatch Logs**: $0.50 per GB ingested
- **Data Transfer**: $0.02 per GB (out)

### Example (1GB/month)
- S3 Storage: $0.023
- KMS: ~$1.05
- CloudWatch Logs: ~$0.05
- **Total**: ~$1.13/month

## Troubleshooting

### Bucket Already Exists
```bash
# If bucket name is already taken, use a unique name
terraform apply -var="bucket_name=kiro-prompts-unique-name"
```

### KMS Key Access Denied
```bash
# Ensure IAM user/role has KMS permissions
aws kms describe-key --key-id alias/kiro-prompts-prod
```

### S3 Access Denied
```bash
# Check bucket policy
aws s3api get-bucket-policy --bucket kiro-user-prompts-metadata-prod
```

## Cleanup

To destroy all resources:
```bash
terraform destroy
```

## References

- [AWS S3 Documentation](https://docs.aws.amazon.com/s3/)
- [AWS KMS Documentation](https://docs.aws.amazon.com/kms/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)

## Support

For issues or questions, contact the Kiro team.
