# BOS-AI VPC Consolidation - Resource IDs

**Generated**: 2026-02-20 01:43:55  
**VPC**: vpc-066c464f9c750ee9e  
**Region**: ap-northeast-2  
**Account**: 533335672315

## Subnet IDs

| Name | Subnet ID | CIDR | AZ |
|------|-----------|------|-----|
| Private 2a | subnet-0f027e9de8e26c18f | 10.200.1.0/24 | ap-northeast-2a |
| Private 2c | subnet-0625d992edf151017 | 10.200.2.0/24 | ap-northeast-2c |
| Public 2a | subnet-06d3c439cedf14742 | 10.200.10.0/24 | ap-northeast-2a |
| Public 2c | subnet-0a9ba13fade9c4c66 | 10.200.20.0/24 | ap-northeast-2c |

## Route Table IDs

| Name | Route Table ID |
|------|----------------|
| Private | rtb-078c8f8a00c2960f7 |
| Public | rtb-0446cd3e4c6a6f2ce |

## Gateway IDs

| Name | Gateway ID |
|------|------------|
| NAT Gateway | nat-03dc6eb89ecb8f21c |
| Internet Gateway | igw-007a80a4355e38fc4 |

## Next Steps

1. Run replacement script:
   ```bash
   ./scripts/replace-placeholders.sh
   ```

2. Review changes:
   ```bash
   git diff environments/
   ```

3. Deploy Phase 2-6:
   - Follow: docs/phase2-6-deployment-guide.md
   - Start with Phase 2 (tag updates)
   - Proceed sequentially through Phase 6

## Terraform Files to Update

- `environments/network-layer/tag-updates.tf`
- `environments/network-layer/vpc-endpoints.tf`
- `environments/app-layer/opensearch-serverless.tf`
- `environments/app-layer/lambda.tf`
- `environments/app-layer/bedrock-kb.tf`

