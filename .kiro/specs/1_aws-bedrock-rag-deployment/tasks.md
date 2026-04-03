# Implementation Plan: AWS Bedrock RAG Deployment

## Overview

이 구현 계획은 AWS Bedrock 기반 RAG 시스템을 Terraform IaC로 배포하기 위한 단계별 작업을 정의합니다. 작업은 레이어별로 구성되며, 네트워크 레이어를 먼저 배포한 후 애플리케이션 레이어를 배포하는 순서로 진행됩니다.

## Tasks

- [x] 1. Set up global infrastructure and Terraform backend
  - Create S3 bucket for Terraform state storage with versioning and encryption
  - Create DynamoDB table for state locking
  - Configure backend configuration files for network-layer and app-layer
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 1.1 Write property test for Terraform backend configuration
  - **Property 25: Terraform State Backend Configuration**
  - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

- [x] 2. Create network module - VPC component
  - [x] 2.1 Implement VPC module with variables, outputs, and main configuration
    - Create modules/network/vpc/variables.tf with CIDR, name, AZ, and subnet variables
    - Create modules/network/vpc/main.tf with VPC, subnet, and route table resources
    - Create modules/network/vpc/outputs.tf exposing VPC ID, CIDR, subnet IDs, and route table IDs
    - Add variable validation for CIDR blocks and minimum 2 AZs
    - _Requirements: 1.1, 1.6, 1.9_

  - [x] 2.2 Write property tests for VPC module
    - **Property 1: VPC CIDR Non-Overlap**
    - **Property 4: Multi-AZ Subnet Distribution**
    - **Property 5: No Internet Gateway Policy**
    - **Validates: Requirements 1.1, 1.6, 1.9**

- [x] 3. Create network module - VPC Peering component
  - [x] 3.1 Implement VPC Peering module
    - Create modules/network/peering/variables.tf with VPC IDs, region, and route table variables
    - Create modules/network/peering/main.tf with peering connection and route resources
    - Create modules/network/peering/outputs.tf exposing peering connection ID and status
    - Add time_sleep resource to wait for peering activation before adding routes
    - _Requirements: 1.2, 1.3, 1.4, 1.5_

  - [x] 3.2 Write property tests for VPC Peering module
    - **Property 2: VPC Peering Establishment**
    - **Property 3: VPC Peering Auto-Acceptance**
    - **Validates: Requirements 1.2, 1.3, 1.4, 1.5**

- [x] 4. Create network module - Security Groups component
  - [x] 4.1 Implement Security Groups module
    - Create modules/network/security-groups/variables.tf with VPC ID and CIDR variables
    - Create modules/network/security-groups/main.tf with security group resources
    - Define security groups for Lambda, OpenSearch, and VPC Endpoints
    - Implement default-deny inbound rules with explicit allow rules for trusted sources
    - Create modules/network/security-groups/outputs.tf exposing security group IDs
    - _Requirements: 1.7, 5.10_

  - [x] 4.2 Write property test for Security Groups
    - **Property 23: Security Group Default Deny**
    - **Validates: Requirements 5.10**

- [x] 5. Deploy network-layer environment
  - [x] 5.1 Create network-layer Terraform configuration
    - Create environments/network-layer/providers.tf with Seoul and US provider aliases
    - Create environments/network-layer/variables.tf with environment-specific variables
    - Create environments/network-layer/main.tf calling VPC and peering modules for both regions
    - Create environments/network-layer/outputs.tf exposing VPC IDs, subnet IDs, and security group IDs
    - Create environments/network-layer/backend.tf with S3 backend configuration
    - Add common tags with Project, Environment, ManagedBy, Layer, and Region
    - _Requirements: 1.1, 1.2, 9.1, 9.2, 11.5, 12.1, 12.2_

  - [x] 5.2 Write property tests for network-layer deployment
    - **Property 32: Multi-Region Provider Configuration**
    - **Property 33: Regional Resource Distribution**
    - **Property 44: Cost Allocation Tags**
    - **Validates: Requirements 9.1, 9.2, 11.5**

- [x] 6. Import existing VPN resources
  - [x] 6.1 Add import blocks for existing VPN Gateway
    - Identify existing VPN Gateway ID using AWS CLI
    - Add import block in environments/network-layer/main.tf
    - Create aws_vpn_gateway resource configuration matching existing resource
    - Add VPN Gateway attachment to Seoul VPC
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 6.2 Write unit test for VPN import configuration
    - Test that import block syntax is correct
    - Test that VPN Gateway is attached to Seoul VPC
    - **Validates: Requirements 7.1, 7.2**

- [x] 7. Checkpoint - Verify network layer deployment
  - Run terraform init, plan, and apply for network-layer
  - Verify VPC peering connection is active
  - Verify route tables have correct peering routes
  - Verify VPN Gateway is imported and attached
  - Ensure all tests pass, ask the user if questions arise

- [x] 8. Create security module - KMS component
  - [x] 8.1 Implement KMS module
    - Create modules/security/kms/variables.tf with key description and service principals
    - Create modules/security/kms/main.tf with KMS key and key policy
    - Add key policy statements for Bedrock, S3, and OpenSearch service principals
    - Enable automatic key rotation
    - Create modules/security/kms/outputs.tf exposing key ID and ARN
    - _Requirements: 5.4, 5.5, 5.6_

  - [x] 8.2 Write property tests for KMS module
    - **Property 18: KMS Customer-Managed Keys**
    - **Property 19: KMS Key Policy Service Principals**
    - **Validates: Requirements 5.4, 5.5, 5.6**

- [x] 9. Create security module - IAM component
  - [x] 9.1 Implement IAM module for Bedrock Knowledge Base role
    - Create modules/security/iam/variables.tf with resource ARNs
    - Create modules/security/iam/bedrock-kb-role.tf with IAM role and policies
    - Grant permissions for S3 read, OpenSearch write, KMS decrypt, and Bedrock invoke
    - Ensure no AdministratorAccess policy is used
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 9.2 Implement IAM module for Lambda execution role
    - Create modules/security/iam/lambda-role.tf with IAM role and policies
    - Grant permissions for S3 read, CloudWatch Logs write, Bedrock ingestion, KMS use, and VPC network interface management
    - Ensure least-privilege policy design
    - _Requirements: 4.11, 5.1, 5.2, 5.3_

  - [x] 9.3 Create IAM module outputs
    - Create modules/security/iam/outputs.tf exposing role ARNs
    - _Requirements: 12.4_

  - [x] 9.4 Write property tests for IAM module
    - **Property 16: Lambda IAM Permissions**
    - **Property 17: IAM Policy Administrator Access Prohibition**
    - **Validates: Requirements 4.11, 5.3**

- [x] 10. Create security module - VPC Endpoints component
  - [x] 10.1 Implement VPC Endpoints module
    - Create modules/security/vpc-endpoints/variables.tf with VPC ID and subnet IDs
    - Create modules/security/vpc-endpoints/main.tf with endpoint resources
    - Create VPC endpoints for Bedrock, S3 (Gateway), and OpenSearch Serverless
    - Configure endpoint policies to restrict access
    - Associate endpoints with security groups
    - Create modules/security/vpc-endpoints/outputs.tf exposing endpoint IDs
    - _Requirements: 5.7, 5.8_

  - [x] 10.2 Write property tests for VPC Endpoints
    - **Property 20: VPC Endpoints for PrivateLink**
    - **Property 21: VPC Endpoint Policy Configuration**
    - **Validates: Requirements 5.7, 5.8**

- [x] 11. Create AI workload module - S3 Pipeline component
  - [x] 11.1 Implement S3 buckets with replication
    - Create modules/ai-workload/s3-pipeline/variables.tf with bucket names and KMS key ARN
    - Create modules/ai-workload/s3-pipeline/s3.tf with source and destination buckets
    - Enable versioning and KMS encryption on both buckets
    - Configure S3 Intelligent-Tiering storage class
    - Add lifecycle policies to transition old objects to Glacier
    - Configure cross-region replication from Seoul to US bucket
    - _Requirements: 4.1, 4.2, 8.1, 11.2, 11.4, 13.1_

  - [x] 11.2 Write property tests for S3 configuration
    - **Property 13: S3 Bucket Security Configuration**
    - **Property 28: S3 Cross-Region Replication**
    - **Property 42: S3 Intelligent-Tiering**
    - **Property 43: S3 Lifecycle Policies**
    - **Validates: Requirements 4.1, 4.2, 8.1, 11.2, 11.4**

  - [x] 11.3 Implement Lambda document processor
    - Create modules/ai-workload/s3-pipeline/lambda.tf with Lambda function resource
    - Configure Lambda with Python 3.11 runtime, 1024MB memory, and 300s timeout
    - Add validation for minimum memory and timeout requirements
    - Configure Lambda VPC settings with subnet and security group IDs
    - Enable X-Ray tracing
    - Create CloudWatch log group for Lambda
    - _Requirements: 4.4, 4.5, 4.6, 10.5_

  - [x] 11.4 Write property tests for Lambda configuration
    - **Property 15: Lambda Resource Constraints**
    - **Property 40: Lambda X-Ray Tracing**
    - **Validates: Requirements 4.5, 4.6, 10.5**

  - [x] 11.5 Configure S3 event notifications and Lambda triggers
    - Add S3 event notification configuration to trigger Lambda on object creation
    - Configure Lambda permission to allow S3 invocation
    - Add Dead Letter Queue (SQS) for failed Lambda invocations
    - Create modules/ai-workload/s3-pipeline/outputs.tf exposing bucket IDs and Lambda ARN
    - _Requirements: 4.3, 8.2, 8.7_

  - [x] 11.6 Write property tests for event-driven pipeline
    - **Property 14: S3 Event-Driven Lambda Invocation**
    - **Property 29: Cross-Region Event Pipeline**
    - **Property 31: Lambda Dead Letter Queue**
    - **Validates: Requirements 4.3, 8.2, 8.7**

- [x] 12. Create Lambda function code for document processing
  - [x] 12.1 Write Lambda handler for document chunking
    - Create lambda/document-processor/handler.py with S3 event handling
    - Implement semantic chunking logic for RTL documents
    - Implement hierarchical chunking logic for specification documents
    - Implement document-type detection based on S3 metadata
    - Add error handling and logging
    - _Requirements: 4.7, 4.8, 4.9_

  - [x] 12.2 Write Lambda function to initiate Bedrock ingestion
    - Add Bedrock client initialization in handler.py
    - Implement start_ingestion_job call to Bedrock Knowledge Base
    - Add retry logic with exponential backoff for throttling
    - Add CloudWatch metrics for tracking ingestion jobs
    - _Requirements: 8.3, 8.5, 8.6_

  - [x] 12.3 Write unit tests for Lambda function
    - Test S3 event parsing
    - Test document type detection
    - Test chunking strategies for different document types
    - Test Bedrock ingestion job initiation
    - Test error handling and retry logic
    - _Requirements: 4.7, 4.8, 4.9, 8.3, 8.5_

- [x] 13. Create AI workload module - OpenSearch Serverless component
  - [x] 13.1 Implement OpenSearch Serverless collection
  - [x] 13.2 Configure OpenSearch access policies
  - [x] 13.3 Create OpenSearch vector index
  - [x] 13.4 Write property tests for OpenSearch configuration

- [x] 14. Create AI workload module - Bedrock Knowledge Base component
  - [x] 14.1 Implement Bedrock Knowledge Base
  - [x] 14.2 Configure Bedrock CloudWatch logging
  - [x] 14.3 Create Bedrock module outputs
  - [x] 14.4 Write property tests for Bedrock configuration

- [x] 15. Create monitoring and observability resources
  - [x] 15.1 Implement CloudWatch log groups
  - [x] 15.2 Configure VPC Flow Logs
  - [x] 15.3 Create CloudWatch alarms
  - [x] 15.4 Create CloudWatch dashboards
  - [x] 15.5 Write property tests for monitoring configuration

- [x] 16. Create security and compliance resources
  - [x] 16.1 Configure CloudTrail
  - [x] 16.2 Implement Network ACLs
  - [x] 16.3 Write property tests for security configuration

- [x] 17. Create cost management resources
  - [x] 17.1 Configure AWS Budgets
  - [x] 17.2 Write property test for cost management

- [x] 18. Deploy app-layer environment
  - [x] 18.1 Create app-layer Terraform configuration
  - [x] 18.2 Write property tests for app-layer deployment

- [x] 19. Create Route53 DNS configuration (optional)
  - [x] 19.1 Implement Route53 hosted zone and records
    - Create Route53 hosted zone for internal DNS
    - Create DNS records for VPC endpoints
    - Configure DNS resolution across regions
    - _Requirements: 9.5_

  - [ ] 19.2 Write property test for Route53 configuration
    - **Property 35: Route53 DNS Configuration**
    - **Validates: Requirements 9.5**

- [x] 20. Checkpoint - Verify app-layer deployment

- [x] 21. Create deployment documentation
  - [x] 21.1 Write deployment guide
  - [x] 21.2 Write operational runbook
  - [x] 21.3 Create cost estimation script

- [x] 22. Create testing and validation scripts
  - [x] 22.1 Write Terraform validation script
  - [x] 22.2 Write policy-as-code tests
  - [x] 22.3 Write Terratest integration tests

- [x] 23. Final checkpoint - End-to-end validation
  - Run all unit tests and property tests
  - Run policy-as-code validation
  - Run Terratest integration tests
  - Perform manual deployment validation
  - Upload test document and verify processing pipeline
  - Query Knowledge Base and verify RAG responses
  - Verify cost estimation matches expectations
  - Ensure all tests pass, ask the user if questions arise

## Notes

- Tasks marked with `*` are optional property-based tests and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key milestones
- Property tests validate universal correctness properties across all configurations
- Unit tests validate specific examples, edge cases, and error conditions
- Deploy network-layer before app-layer due to dependency on VPC and networking resources
- Use terraform_remote_state to share outputs between layers
- All resources should be tagged with cost allocation tags for billing analysis
- Lambda functions require VPC configuration for private subnet deployment
- OpenSearch Serverless requires minimum 2 OCU per dimension (search and indexing)
- Cross-region replication requires separate IAM role with replication permissions
- VPC peering requires route table updates in both regions
- Import existing VPN resources before deploying network-layer to avoid conflicts
