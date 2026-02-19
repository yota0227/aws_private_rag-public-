# Main Configuration for App Layer - Bedrock RAG
# This configuration deploys AI workload resources in US East region
#
# Requirements: 9.7, 12.1, 12.2, 12.5

# KMS Module for Encryption
module "kms" {
  source = "../../../modules/security/kms"

  region                       = var.us_region
  key_description              = "KMS key for BOS AI RAG infrastructure encryption"
  enable_bedrock_access        = true
  enable_s3_access             = true
  enable_opensearch_access     = true
  enable_lambda_access         = true
  enable_cloudwatch_logs_access = true

  tags = local.common_tags
}

# IAM Module for Roles and Policies
module "iam" {
  source = "../../../modules/security/iam"

  project_name = var.project_name
  environment  = var.environment
  
  # Resource ARNs for IAM policies
  s3_data_source_bucket_arn = "arn:aws:s3:::${var.source_bucket_name}"
  
  opensearch_collection_arn = module.bedrock_rag.opensearch_collection_arn
  kms_key_arn              = module.kms.key_arn
  bedrock_model_arns = [
    var.embedding_model_arn,
    var.foundation_model_arn
  ]

  tags = local.common_tags
}

# VPC Endpoints Module for PrivateLink
module "vpc_endpoints" {
  source = "../../../modules/security/vpc-endpoints"

  project_name = var.project_name
  environment  = var.environment
  region       = var.us_region
  
  vpc_id             = local.us_vpc_id
  subnet_ids         = local.us_private_subnet_ids
  security_group_ids = local.us_security_group_ids
  route_table_ids    = local.us_private_route_table_ids
  
  # Enable required VPC endpoints
  enable_bedrock_runtime_endpoint       = true
  enable_bedrock_agent_runtime_endpoint = true
  enable_s3_endpoint                    = true
  enable_opensearch_endpoint            = true

  tags = local.common_tags
}

# S3 Pipeline Module for Document Storage and Processing
module "s3_pipeline" {
  source = "../../../modules/ai-workload/s3-pipeline"

  project_name = var.project_name
  environment  = var.environment
  
  source_bucket_name      = var.source_bucket_name
  destination_bucket_name = var.destination_bucket_name
  kms_key_arn            = module.kms.key_arn
  
  # Lambda configuration
  lambda_function_name = var.lambda_function_name
  lambda_runtime       = var.lambda_runtime
  lambda_memory_size   = var.lambda_memory_size
  lambda_timeout       = var.lambda_timeout
  
  lambda_vpc_config = {
    subnet_ids         = local.us_private_subnet_ids
    security_group_ids = local.us_security_group_ids
  }
  
  lambda_execution_role_arn = module.iam.lambda_processor_role_arn
  
  # Enable cross-region replication
  enable_replication = true

  tags = local.common_tags
}

# Bedrock RAG Module for Knowledge Base and OpenSearch
module "bedrock_rag" {
  source = "../../../modules/ai-workload/bedrock-rag"

  project_name = var.project_name
  environment  = var.environment
  
  # Bedrock configuration
  knowledge_base_name   = var.knowledge_base_name
  embedding_model_arn   = var.embedding_model_arn
  foundation_model_arn  = var.foundation_model_arn
  
  # OpenSearch configuration
  opensearch_collection_name = var.opensearch_collection_name
  opensearch_index_name      = var.opensearch_index_name
  vector_dimension           = var.vector_dimension
  opensearch_capacity_units  = var.opensearch_capacity_units
  
  # S3 data source
  s3_data_source_bucket_arn = module.s3_pipeline.destination_bucket_arn
  
  # Security
  kms_key_arn        = module.kms.key_arn
  vpc_subnet_ids     = local.us_private_subnet_ids
  security_group_ids = local.us_security_group_ids
  
  # IAM
  bedrock_execution_role_arn  = module.iam.bedrock_kb_role_arn
  opensearch_access_role_arn  = module.iam.bedrock_kb_role_arn

  tags = local.common_tags
}

# CloudWatch Logs Module for Monitoring
module "cloudwatch_logs" {
  source = "../../../modules/monitoring/cloudwatch-logs"

  project_name = var.project_name
  environment  = var.environment
  
  lambda_function_names = [var.lambda_function_name]
  bedrock_kb_name       = var.knowledge_base_name
  vpc_ids               = [local.us_vpc_id]
  log_retention_days    = var.log_retention_days

  tags = local.common_tags
}

# VPC Flow Logs Module
module "vpc_flow_logs" {
  source = "../../../modules/monitoring/vpc-flow-logs"

  vpc_id                    = local.us_vpc_id
  vpc_name                  = "${var.project_name}-${var.environment}-us-vpc"
  cloudwatch_log_group_arn  = module.cloudwatch_logs.vpc_flow_log_group_arns[local.us_vpc_id]
  iam_role_arn             = module.iam.vpc_flow_logs_role_arn

  tags = local.common_tags
}

# CloudWatch Alarms Module
module "cloudwatch_alarms" {
  source = "../../../modules/monitoring/cloudwatch-alarms"

  project_name = var.project_name
  environment  = var.environment
  
  lambda_function_names     = [var.lambda_function_name]
  bedrock_kb_id            = ""  # Will be populated after first apply
  opensearch_collection_id = ""  # Will be populated after first apply
  
  # SNS topic for notifications (empty string means create new topic)
  sns_topic_arn = ""

  tags = local.common_tags
}

# CloudWatch Dashboards Module
module "cloudwatch_dashboards" {
  source = "../../../modules/monitoring/cloudwatch-dashboards"

  project_name = var.project_name
  environment  = var.environment
  region       = var.us_region
  
  lambda_function_names     = [var.lambda_function_name]
  bedrock_kb_id            = module.bedrock_rag.knowledge_base_id
  opensearch_collection_id = module.bedrock_rag.opensearch_collection_id
  vpc_ids                  = [local.us_vpc_id]

  tags = local.common_tags
}

# CloudTrail Module for Audit Logging
module "cloudtrail" {
  source = "../../../modules/security/cloudtrail"

  project_name = var.project_name
  environment  = var.environment
  
  trail_name      = "${var.project_name}-${var.environment}-trail"
  s3_bucket_name  = var.cloudtrail_bucket_name
  kms_key_id      = module.kms.key_arn
  
  enable_log_file_validation    = true
  include_global_service_events = true
  is_multi_region_trail         = true

  tags = local.common_tags
}

# Network ACLs Module for Additional Security
module "network_acls" {
  source = "../../../modules/network/network-acls"

  vpc_id              = local.us_vpc_id
  vpc_name            = "${var.project_name}-${var.environment}-us-vpc"
  private_subnet_ids  = local.us_private_subnet_ids
  vpc_cidr            = data.terraform_remote_state.network.outputs.us_vpc_cidr
  peer_vpc_cidr       = data.terraform_remote_state.network.outputs.seoul_vpc_cidr

  tags = local.common_tags
}

# AWS Budgets Module for Cost Management
module "budgets" {
  source = "../../../modules/cost-management/budgets"

  project_name = var.project_name
  environment  = var.environment
  
  budget_name         = "${var.project_name}-${var.environment}-monthly-budget"
  budget_limit_amount = var.monthly_budget_amount
  budget_time_unit    = "MONTHLY"
  
  notification_emails = length(var.sns_notification_emails) > 0 ? var.sns_notification_emails : ["placeholder@example.com"]
  alert_thresholds    = var.budget_alert_thresholds
  
  # Cost filters by project tag
  cost_filters = {
    TagKeyValue = ["Project$${var.project_name}"]
  }

  tags = local.common_tags
}
