package main

# Compliance Policy Tests for AWS Bedrock RAG Infrastructure
# These policies enforce compliance requirements and best practices

# METADATA
# title: Compliance Policies
# description: Validates compliance configurations for AWS resources
# custom:
#   matchers:
#     - resource

#######################
# Data Retention
#######################

# Deny S3 buckets without lifecycle policies for cost optimization
warn[msg] {
    resource := input.resource.aws_s3_bucket[name]
    not input.resource.aws_s3_bucket_lifecycle_configuration
    msg := sprintf("S3 bucket '%s' should have lifecycle policies configured for cost optimization (Requirement 11.4)", [name])
}

# Deny CloudWatch log groups without retention policy
deny[msg] {
    resource := input.resource.aws_cloudwatch_log_group[name]
    not resource.retention_in_days
    msg := sprintf("CloudWatch log group '%s' must have retention policy configured", [name])
}

# Warn on excessive log retention
warn[msg] {
    resource := input.resource.aws_cloudwatch_log_group[name]
    resource.retention_in_days > 365
    msg := sprintf("CloudWatch log group '%s' has retention > 365 days - consider cost implications", [name])
}

#######################
# Backup and Recovery
#######################

# Deny S3 buckets without versioning for backup
deny[msg] {
    resource := input.resource.aws_s3_bucket[name]
    contains(name, "terraform-state")
    not resource.versioning[_].enabled
    msg := sprintf("Terraform state bucket '%s' must have versioning enabled for backup (Requirement 6.2)", [name])
}

# Warn on missing backup configuration
warn[msg] {
    resource := input.resource.aws_opensearchserverless_collection[name]
    msg := sprintf("OpenSearch Serverless collection '%s' - ensure AWS automatic backups are enabled (Requirement 13.2)", [name])
}

#######################
# Monitoring and Logging
#######################

# Deny VPCs without Flow Logs
deny[msg] {
    vpc := input.resource.aws_vpc[name]
    not input.resource.aws_flow_log
    msg := sprintf("VPC '%s' must have Flow Logs enabled (Requirement 10.4)", [name])
}

# Deny Lambda functions without CloudWatch log groups
deny[msg] {
    lambda := input.resource.aws_lambda_function[name]
    log_group_name := sprintf("/aws/lambda/%s", [name])
    not input.resource.aws_cloudwatch_log_group[log_group_name]
    msg := sprintf("Lambda function '%s' must have CloudWatch log group configured (Requirement 10.1)", [name])
}

# Warn on missing CloudWatch alarms
warn[msg] {
    input.resource.aws_lambda_function[_]
    not input.resource.aws_cloudwatch_metric_alarm
    msg := "CloudWatch alarms should be configured for critical metrics (Requirement 10.3)"
}

# Warn on missing X-Ray tracing for Lambda
warn[msg] {
    resource := input.resource.aws_lambda_function[name]
    not resource.tracing_config
    msg := sprintf("Lambda function '%s' should have X-Ray tracing enabled (Requirement 10.5)", [name])
}

deny[msg] {
    resource := input.resource.aws_lambda_function[name]
    resource.tracing_config[_].mode != "Active"
    resource.tracing_config[_].mode != "PassThrough"
    msg := sprintf("Lambda function '%s' has invalid X-Ray tracing mode", [name])
}

#######################
# High Availability
#######################

# Deny VPCs with insufficient availability zones
deny[msg] {
    resource := input.resource.aws_subnet[_]
    subnets := [s | s := input.resource.aws_subnet[_]]
    azs := {s.availability_zone | s := subnets[_]}
    count(azs) < 2
    msg := "VPC must have subnets in at least 2 availability zones for high availability (Requirement 1.6)"
}

# Warn on single-AZ deployments
warn[msg] {
    resource := input.resource.aws_lambda_function[name]
    resource.vpc_config[_]
    count(resource.vpc_config[_].subnet_ids) < 2
    msg := sprintf("Lambda function '%s' should be deployed across multiple subnets for high availability", [name])
}

#######################
# Resource Naming
#######################

# Warn on inconsistent naming conventions
warn[msg] {
    resource := input.resource.aws_vpc[name]
    not contains(name, "vpc")
    msg := sprintf("VPC resource '%s' should follow naming convention including 'vpc'", [name])
}

warn[msg] {
    resource := input.resource.aws_s3_bucket[name]
    not regex.match("^[a-z0-9][a-z0-9-]*[a-z0-9]$", name)
    msg := sprintf("S3 bucket '%s' should follow DNS-compliant naming convention", [name])
}

#######################
# State Management
#######################

# Deny missing DynamoDB table for state locking
deny[msg] {
    backend := input.terraform[_].backend[_].s3[_]
    not backend.dynamodb_table
    msg := "Terraform S3 backend must have DynamoDB table for state locking (Requirement 6.3)"
}

# Deny unencrypted Terraform state
deny[msg] {
    backend := input.terraform[_].backend[_].s3[_]
    not backend.encrypt == true
    msg := "Terraform S3 backend must have encryption enabled (Requirement 6.4)"
}

#######################
# Provider Configuration
#######################

# Deny missing provider version constraints
deny[msg] {
    not input.terraform[_].required_providers
    msg := "Terraform configuration must specify required provider versions"
}

# Warn on outdated Terraform version
warn[msg] {
    required_version := input.terraform[_].required_version
    not contains(required_version, "1.5")
    not contains(required_version, "1.6")
    not contains(required_version, "1.7")
    not contains(required_version, "1.8")
    msg := "Consider using Terraform 1.5+ for latest features and security updates"
}

#######################
# Multi-Region Configuration
#######################

# Deny missing provider aliases for multi-region
warn[msg] {
    providers := [p | p := input.provider.aws[_]]
    count(providers) < 2
    msg := "Multi-region deployment should have provider aliases for Seoul and US regions (Requirement 9.1)"
}

# Validate region configuration
deny[msg] {
    provider := input.provider.aws[name]
    provider.region
    not provider.region == "ap-northeast-2"
    not provider.region == "us-east-1"
    msg := sprintf("Provider '%s' uses unsupported region - only ap-northeast-2 and us-east-1 are allowed", [name])
}

#######################
# VPC Peering
#######################

# Deny VPC peering without auto-accept for same account
warn[msg] {
    resource := input.resource.aws_vpc_peering_connection[name]
    not resource.auto_accept == true
    not resource.peer_region
    msg := sprintf("VPC peering connection '%s' should have auto_accept enabled for same-account peering (Requirement 1.3)", [name])
}

# Warn on missing peering routes
warn[msg] {
    input.resource.aws_vpc_peering_connection[_]
    routes := [r | r := input.resource.aws_route[_]; r.vpc_peering_connection_id]
    count(routes) < 2
    msg := "VPC peering should have bidirectional routes configured (Requirement 1.4)"
}

#######################
# OpenSearch Configuration
#######################

# Deny OpenSearch with insufficient capacity
deny[msg] {
    resource := input.resource.aws_opensearchserverless_collection[name]
    # Note: Capacity is configured separately in AWS, but we can check for proper configuration
    msg := sprintf("OpenSearch Serverless collection '%s' - ensure minimum 2 OCU for search and indexing (Requirement 3.2)", [name])
}

#######################
# Lambda Configuration
#######################

# Deny Lambda with insufficient timeout for document processing
deny[msg] {
    resource := input.resource.aws_lambda_function[name]
    contains(name, "document-processor")
    resource.timeout < 300
    msg := sprintf("Lambda function '%s' must have timeout >= 300 seconds for document processing (Requirement 4.5)", [name])
}

# Deny Lambda without Dead Letter Queue for critical functions
warn[msg] {
    resource := input.resource.aws_lambda_function[name]
    contains(name, "processor")
    not resource.dead_letter_config
    msg := sprintf("Lambda function '%s' should have Dead Letter Queue configured (Requirement 8.7)", [name])
}

#######################
# Cost Management
#######################

# Warn on missing AWS Budgets configuration
warn[msg] {
    not input.resource.aws_budgets_budget
    msg := "AWS Budgets should be configured for cost monitoring (Requirement 11.6)"
}

# Warn on S3 storage class
warn[msg] {
    resource := input.resource.aws_s3_bucket[name]
    not input.resource.aws_s3_bucket_lifecycle_configuration
    msg := sprintf("S3 bucket '%s' should use Intelligent-Tiering or lifecycle policies for cost optimization (Requirement 11.2)", [name])
}

#######################
# Documentation
#######################

# Warn on missing variable descriptions
warn[msg] {
    variable := input.variable[name]
    not variable.description
    msg := sprintf("Variable '%s' should have a description (Requirement 12.3)", [name])
}

# Warn on missing output descriptions
warn[msg] {
    output := input.output[name]
    not output.description
    msg := sprintf("Output '%s' should have a description (Requirement 12.4)", [name])
}

#######################
# Import Configuration
#######################

# Validate import blocks for existing resources
warn[msg] {
    import_block := input.import[_]
    not import_block.to
    msg := "Import block must specify 'to' attribute for target resource"
}

warn[msg] {
    import_block := input.import[_]
    not import_block.id
    msg := "Import block must specify 'id' attribute for existing resource"
}
