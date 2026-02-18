package main

# Cost Optimization Policy Tests for AWS Bedrock RAG Infrastructure
# These policies enforce cost optimization best practices

# METADATA
# title: Cost Optimization Policies
# description: Validates cost-related configurations for AWS resources
# custom:
#   matchers:
#     - resource

#######################
# S3 Cost Optimization
#######################

# Warn on S3 buckets without Intelligent-Tiering or lifecycle policies
warn[msg] {
    resource := input.resource.aws_s3_bucket[name]
    not input.resource.aws_s3_bucket_lifecycle_configuration
    not input.resource.aws_s3_bucket_intelligent_tiering_configuration
    msg := sprintf("S3 bucket '%s' should use Intelligent-Tiering or lifecycle policies for cost optimization (Requirement 11.2, 11.4)", [name])
}

# Warn on aggressive lifecycle transitions
warn[msg] {
    resource := input.resource.aws_s3_bucket_lifecycle_configuration[name]
    rule := resource.rule[_]
    rule.transition[_].days < 30
    msg := sprintf("S3 lifecycle rule in '%s' transitions objects < 30 days - may increase costs due to minimum storage duration", [name])
}

# Warn on missing lifecycle expiration
warn[msg] {
    resource := input.resource.aws_s3_bucket_lifecycle_configuration[name]
    rule := resource.rule[_]
    not rule.expiration
    msg := sprintf("S3 lifecycle rule in '%s' should include expiration to delete old objects", [name])
}

#######################
# Lambda Cost Optimization
#######################

# Warn on Lambda with excessive memory allocation
warn[msg] {
    resource := input.resource.aws_lambda_function[name]
    resource.memory_size > 3008
    msg := sprintf("Lambda function '%s' has memory > 3GB - verify if this is necessary for cost optimization", [name])
}

# Warn on Lambda without reserved concurrency (for predictable workloads)
warn[msg] {
    resource := input.resource.aws_lambda_function[name]
    not resource.reserved_concurrent_executions
    msg := sprintf("Lambda function '%s' - consider reserved concurrency for predictable workloads to control costs", [name])
}

# Warn on Lambda with excessive timeout
warn[msg] {
    resource := input.resource.aws_lambda_function[name]
    resource.timeout > 600
    msg := sprintf("Lambda function '%s' has timeout > 10 minutes - consider optimizing or using alternative services", [name])
}

#######################
# OpenSearch Cost Optimization
#######################

# Warn on OpenSearch with high OCU allocation
warn[msg] {
    # Note: OCU is configured via API, not Terraform resource directly
    # This is a reminder to monitor OCU usage
    resource := input.resource.aws_opensearchserverless_collection[name]
    msg := sprintf("OpenSearch Serverless collection '%s' - monitor OCU usage and adjust capacity based on workload (Requirement 11.1)", [name])
}

#######################
# Data Transfer Cost Optimization
#######################

# Warn on potential high data transfer costs
warn[msg] {
    resource := input.resource.aws_s3_bucket_replication_configuration[name]
    msg := sprintf("S3 replication '%s' incurs cross-region data transfer costs - monitor usage (Requirement 11.8)", [name])
}

# Warn on missing VPC endpoints (increases data transfer costs)
warn[msg] {
    input.resource.aws_vpc[_]
    not input.resource.aws_vpc_endpoint
    msg := "VPC endpoints reduce data transfer costs by keeping traffic within AWS network"
}

#######################
# CloudWatch Cost Optimization
#######################

# Warn on excessive log retention
warn[msg] {
    resource := input.resource.aws_cloudwatch_log_group[name]
    resource.retention_in_days > 90
    msg := sprintf("CloudWatch log group '%s' has retention > 90 days - consider shorter retention for cost savings", [name])
}

# Warn on missing log retention (infinite retention)
warn[msg] {
    resource := input.resource.aws_cloudwatch_log_group[name]
    not resource.retention_in_days
    msg := sprintf("CloudWatch log group '%s' has no retention policy - logs will be kept indefinitely, increasing costs", [name])
}

# Warn on excessive custom metrics
warn[msg] {
    metrics := [m | m := input.resource.aws_cloudwatch_metric_alarm[_]]
    count(metrics) > 50
    msg := sprintf("High number of CloudWatch alarms (%d) - each alarm costs $0.10/month", [count(metrics)])
}

#######################
# KMS Cost Optimization
#######################

# Warn on excessive KMS keys
warn[msg] {
    keys := [k | k := input.resource.aws_kms_key[_]]
    count(keys) > 5
    msg := sprintf("High number of KMS keys (%d) - each key costs $1/month, consider consolidating", [count(keys)])
}

#######################
# VPC Cost Optimization
#######################

# Warn on excessive VPC endpoints
warn[msg] {
    endpoints := [e | e := input.resource.aws_vpc_endpoint[_]; e.vpc_endpoint_type == "Interface"]
    count(endpoints) > 10
    msg := sprintf("High number of Interface VPC endpoints (%d) - each costs ~$7/month", [count(endpoints)])
}

# Warn on NAT Gateway usage (expensive)
warn[msg] {
    resource := input.resource.aws_nat_gateway[name]
    msg := sprintf("NAT Gateway '%s' costs ~$32/month plus data transfer - consider alternatives if possible", [name])
}

#######################
# Resource Tagging for Cost Allocation
#######################

# Deny resources without cost allocation tags
deny[msg] {
    resource_types := ["aws_vpc", "aws_s3_bucket", "aws_lambda_function", "aws_kms_key", "aws_opensearchserverless_collection"]
    resource_type := resource_types[_]
    resource := input.resource[resource_type][name]
    not resource.tags.CostCenter
    msg := sprintf("%s '%s' must have 'CostCenter' tag for cost allocation (Requirement 11.5)", [resource_type, name])
}

deny[msg] {
    resource_types := ["aws_vpc", "aws_s3_bucket", "aws_lambda_function", "aws_kms_key", "aws_opensearchserverless_collection"]
    resource_type := resource_types[_]
    resource := input.resource[resource_type][name]
    not resource.tags.Environment
    msg := sprintf("%s '%s' must have 'Environment' tag for cost allocation (Requirement 11.5)", [resource_type, name])
}

#######################
# Bedrock Cost Optimization
#######################

# Warn on Bedrock usage without monitoring
warn[msg] {
    resource := input.resource.aws_bedrockagent_knowledge_base[name]
    not input.resource.aws_cloudwatch_metric_alarm
    msg := sprintf("Bedrock Knowledge Base '%s' - set up CloudWatch alarms to monitor token usage and costs", [name])
}

# Warn on potential high token usage
warn[msg] {
    resource := input.resource.aws_bedrockagent_knowledge_base[name]
    msg := sprintf("Bedrock Knowledge Base '%s' - optimize prompt engineering to reduce token usage and costs (Requirement 11.7)", [name])
}

#######################
# Budget Configuration
#######################

# Deny missing budget alerts
deny[msg] {
    not input.resource.aws_budgets_budget
    msg := "AWS Budgets must be configured with alerts for cost monitoring (Requirement 11.6)"
}

# Warn on budget without SNS notification
warn[msg] {
    resource := input.resource.aws_budgets_budget[name]
    not resource.notification
    msg := sprintf("Budget '%s' should have SNS notifications configured for alerts", [name])
}

# Validate budget thresholds
warn[msg] {
    resource := input.resource.aws_budgets_budget[name]
    notification := resource.notification[_]
    notification.threshold > 100
    msg := sprintf("Budget '%s' has notification threshold > 100%% - consider adding alerts at 50%% and 80%%", [name])
}

#######################
# Right-Sizing Recommendations
#######################

# Warn on potentially over-provisioned Lambda
warn[msg] {
    resource := input.resource.aws_lambda_function[name]
    resource.memory_size >= 2048
    resource.timeout <= 60
    msg := sprintf("Lambda function '%s' has high memory but low timeout - may be over-provisioned", [name])
}

# Warn on Lambda with low memory for document processing
warn[msg] {
    resource := input.resource.aws_lambda_function[name]
    contains(name, "document")
    resource.memory_size < 1024
    msg := sprintf("Lambda function '%s' may be under-provisioned for document processing - could cause timeouts and retries", [name])
}

#######################
# Storage Class Optimization
#######################

# Warn on S3 Standard storage without lifecycle policies
warn[msg] {
    resource := input.resource.aws_s3_bucket[name]
    not input.resource.aws_s3_bucket_lifecycle_configuration
    msg := sprintf("S3 bucket '%s' - implement lifecycle policies to transition to cheaper storage classes (Standard → IA → Glacier)", [name])
}

#######################
# Monitoring Cost Optimization
#######################

# Warn on excessive dashboard widgets
warn[msg] {
    resource := input.resource.aws_cloudwatch_dashboard[name]
    # CloudWatch dashboards are free for first 3, then $3/month each
    msg := sprintf("CloudWatch dashboard '%s' - first 3 dashboards are free, additional dashboards cost $3/month", [name])
}

#######################
# Cross-Region Cost Considerations
#######################

# Warn on cross-region data transfer
warn[msg] {
    resource := input.resource.aws_vpc_peering_connection[name]
    resource.peer_region
    msg := sprintf("VPC peering connection '%s' is cross-region - data transfer costs $0.02/GB", [name])
}

# Warn on cross-region replication costs
warn[msg] {
    resource := input.resource.aws_s3_bucket_replication_configuration[name]
    msg := sprintf("S3 replication '%s' - cross-region replication costs include storage + data transfer + replication PUT requests", [name])
}

#######################
# Reserved Capacity Recommendations
#######################

# Warn on potential savings with reserved capacity
warn[msg] {
    lambdas := [l | l := input.resource.aws_lambda_function[_]]
    count(lambdas) > 5
    msg := "Consider Lambda Reserved Concurrency or Savings Plans for predictable workloads"
}

#######################
# Cost Estimation
#######################

# Provide cost estimation guidance
warn[msg] {
    msg := "Run scripts/cost-estimation.sh to estimate monthly costs for different usage scenarios (Requirement 11.7)"
}
