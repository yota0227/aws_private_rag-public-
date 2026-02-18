package main

# Security Policy Tests for AWS Bedrock RAG Infrastructure
# These policies enforce security best practices and compliance requirements

# METADATA
# title: Security Policies
# description: Validates security configurations for AWS resources
# custom:
#   matchers:
#     - resource

#######################
# S3 Bucket Security
#######################

# Deny S3 buckets without versioning
deny[msg] {
    resource := input.resource.aws_s3_bucket[name]
    not resource.versioning[_].enabled
    msg := sprintf("S3 bucket '%s' must have versioning enabled (Requirement 4.1, 13.1)", [name])
}

# Deny S3 buckets without encryption
deny[msg] {
    resource := input.resource.aws_s3_bucket[name]
    not resource.server_side_encryption_configuration
    msg := sprintf("S3 bucket '%s' must have server-side encryption enabled (Requirement 4.2)", [name])
}

# Deny S3 buckets with public access
deny[msg] {
    resource := input.resource.aws_s3_bucket_public_access_block[name]
    not resource.block_public_acls == true
    msg := sprintf("S3 bucket '%s' must block public ACLs", [name])
}

deny[msg] {
    resource := input.resource.aws_s3_bucket_public_access_block[name]
    not resource.block_public_policy == true
    msg := sprintf("S3 bucket '%s' must block public policies", [name])
}

deny[msg] {
    resource := input.resource.aws_s3_bucket_public_access_block[name]
    not resource.ignore_public_acls == true
    msg := sprintf("S3 bucket '%s' must ignore public ACLs", [name])
}

deny[msg] {
    resource := input.resource.aws_s3_bucket_public_access_block[name]
    not resource.restrict_public_buckets == true
    msg := sprintf("S3 bucket '%s' must restrict public buckets", [name])
}

#######################
# IAM Security
#######################

# Deny IAM policies with AdministratorAccess
deny[msg] {
    resource := input.resource.aws_iam_role_policy_attachment[name]
    contains(resource.policy_arn, "AdministratorAccess")
    msg := sprintf("IAM role policy attachment '%s' must not use AdministratorAccess (Requirement 5.3)", [name])
}

deny[msg] {
    resource := input.resource.aws_iam_policy[name]
    policy := json.unmarshal(resource.policy)
    statement := policy.Statement[_]
    statement.Effect == "Allow"
    statement.Action[_] == "*"
    statement.Resource == "*"
    msg := sprintf("IAM policy '%s' must not grant wildcard permissions on all resources (Requirement 5.2)", [name])
}

# Warn on overly permissive IAM policies
warn[msg] {
    resource := input.resource.aws_iam_policy[name]
    policy := json.unmarshal(resource.policy)
    statement := policy.Statement[_]
    statement.Effect == "Allow"
    count(statement.Action) > 20
    msg := sprintf("IAM policy '%s' has more than 20 actions - consider splitting into multiple policies", [name])
}

#######################
# KMS Security
#######################

# Deny KMS keys without rotation enabled
deny[msg] {
    resource := input.resource.aws_kms_key[name]
    not resource.enable_key_rotation == true
    msg := sprintf("KMS key '%s' must have automatic key rotation enabled (Requirement 5.4)", [name])
}

# Deny KMS keys without proper key policy
deny[msg] {
    resource := input.resource.aws_kms_key[name]
    not resource.policy
    msg := sprintf("KMS key '%s' must have a key policy defined (Requirement 5.5)", [name])
}

#######################
# VPC Security
#######################

# Deny VPCs with Internet Gateway (No-IGW policy)
deny[msg] {
    resource := input.resource.aws_internet_gateway[name]
    msg := sprintf("Internet Gateway '%s' is not allowed - No-IGW policy enforced (Requirement 1.9)", [name])
}

# Deny security groups with overly permissive ingress rules
deny[msg] {
    resource := input.resource.aws_security_group[name]
    rule := resource.ingress[_]
    rule.cidr_blocks[_] == "0.0.0.0/0"
    rule.from_port != 443
    msg := sprintf("Security group '%s' has overly permissive ingress rule from 0.0.0.0/0 on port %d (Requirement 5.10)", [name, rule.from_port])
}

# Warn on security groups allowing all outbound traffic
warn[msg] {
    resource := input.resource.aws_security_group[name]
    rule := resource.egress[_]
    rule.cidr_blocks[_] == "0.0.0.0/0"
    rule.from_port == 0
    rule.to_port == 0
    msg := sprintf("Security group '%s' allows all outbound traffic - consider restricting", [name])
}

#######################
# Lambda Security
#######################

# Deny Lambda functions without VPC configuration (for private workloads)
warn[msg] {
    resource := input.resource.aws_lambda_function[name]
    contains(name, "processor")
    not resource.vpc_config
    msg := sprintf("Lambda function '%s' should be deployed in VPC for private workload access", [name])
}

# Deny Lambda functions with excessive timeout
warn[msg] {
    resource := input.resource.aws_lambda_function[name]
    resource.timeout > 900
    msg := sprintf("Lambda function '%s' has timeout > 15 minutes - consider using Step Functions", [name])
}

# Deny Lambda functions with insufficient memory for document processing
deny[msg] {
    resource := input.resource.aws_lambda_function[name]
    contains(name, "document-processor")
    resource.memory_size < 1024
    msg := sprintf("Lambda function '%s' must have at least 1024 MB memory for document processing (Requirement 4.6)", [name])
}

#######################
# CloudTrail Security
#######################

# Deny missing CloudTrail configuration
deny[msg] {
    not input.resource.aws_cloudtrail
    msg := "CloudTrail must be configured for API logging (Requirement 5.9)"
}

# Deny CloudTrail without log file validation
deny[msg] {
    resource := input.resource.aws_cloudtrail[name]
    not resource.enable_log_file_validation == true
    msg := sprintf("CloudTrail '%s' must have log file validation enabled", [name])
}

#######################
# Encryption Requirements
#######################

# Deny resources without encryption at rest
deny[msg] {
    resource := input.resource.aws_opensearchserverless_collection[name]
    not resource.encryption
    msg := sprintf("OpenSearch Serverless collection '%s' must have encryption enabled (Requirement 3.5)", [name])
}

# Deny EBS volumes without encryption
deny[msg] {
    resource := input.resource.aws_ebs_volume[name]
    not resource.encrypted == true
    msg := sprintf("EBS volume '%s' must be encrypted", [name])
}

#######################
# Network ACL Security
#######################

# Warn if Network ACLs are not configured
warn[msg] {
    input.resource.aws_vpc[_]
    not input.resource.aws_network_acl
    msg := "Network ACLs should be configured as an additional security layer (Requirement 5.11)"
}

#######################
# VPC Endpoint Security
#######################

# Deny missing VPC endpoints for AWS services
deny[msg] {
    input.resource.aws_vpc[_]
    not input.resource.aws_vpc_endpoint
    msg := "VPC endpoints must be configured for PrivateLink connectivity (Requirement 5.7)"
}

# Deny VPC endpoints without endpoint policies
warn[msg] {
    resource := input.resource.aws_vpc_endpoint[name]
    resource.vpc_endpoint_type == "Interface"
    not resource.policy
    msg := sprintf("VPC endpoint '%s' should have an endpoint policy configured (Requirement 5.8)", [name])
}

#######################
# Resource Tagging
#######################

# Deny resources without required tags
required_tags := ["Project", "Environment", "ManagedBy"]

deny[msg] {
    resource_types := ["aws_vpc", "aws_s3_bucket", "aws_lambda_function", "aws_kms_key"]
    resource_type := resource_types[_]
    resource := input.resource[resource_type][name]
    tag := required_tags[_]
    not resource.tags[tag]
    msg := sprintf("%s '%s' must have tag '%s' (Requirement 11.5)", [resource_type, name, tag])
}

#######################
# Bedrock Security
#######################

# Warn on Bedrock Knowledge Base without CloudWatch logging
warn[msg] {
    resource := input.resource.aws_bedrockagent_knowledge_base[name]
    not input.resource.aws_cloudwatch_log_group
    msg := sprintf("Bedrock Knowledge Base '%s' should have CloudWatch logging configured (Requirement 2.6)", [name])
}

#######################
# Cross-Region Replication
#######################

# Warn on S3 buckets without replication for critical data
warn[msg] {
    resource := input.resource.aws_s3_bucket[name]
    contains(name, "documents")
    not input.resource.aws_s3_bucket_replication_configuration
    msg := sprintf("S3 bucket '%s' should have cross-region replication configured for disaster recovery (Requirement 13.4)", [name])
}
