# Bedrock RAG Module Outputs

# Knowledge Base Outputs
output "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.main.id
}

output "knowledge_base_arn" {
  description = "ARN of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.main.arn
}

output "knowledge_base_name" {
  description = "Name of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.main.name
}

output "knowledge_base_created_at" {
  description = "Timestamp when the Knowledge Base was created"
  value       = aws_bedrockagent_knowledge_base.main.created_at
}

output "knowledge_base_updated_at" {
  description = "Timestamp when the Knowledge Base was last updated"
  value       = aws_bedrockagent_knowledge_base.main.updated_at
}

# Data Source Outputs
output "data_source_id" {
  description = "ID of the Bedrock Data Source"
  value       = aws_bedrockagent_data_source.s3.id
}

output "data_source_arn" {
  description = "ARN of the Bedrock Data Source"
  value       = aws_bedrockagent_data_source.s3.data_source_id
}

output "data_source_name" {
  description = "Name of the Bedrock Data Source"
  value       = aws_bedrockagent_data_source.s3.name
}

# OpenSearch Outputs
output "opensearch_collection_id" {
  description = "ID of the OpenSearch Serverless collection"
  value       = aws_opensearchserverless_collection.main.id
}

output "opensearch_collection_arn" {
  description = "ARN of the OpenSearch Serverless collection"
  value       = aws_opensearchserverless_collection.main.arn
}

output "opensearch_collection_endpoint" {
  description = "Endpoint of the OpenSearch Serverless collection"
  value       = aws_opensearchserverless_collection.main.collection_endpoint
}

output "opensearch_collection_name" {
  description = "Name of the OpenSearch Serverless collection"
  value       = aws_opensearchserverless_collection.main.name
}

output "opensearch_dashboard_endpoint" {
  description = "Dashboard endpoint of the OpenSearch Serverless collection"
  value       = aws_opensearchserverless_collection.main.dashboard_endpoint
}

# CloudWatch Log Group Outputs
output "bedrock_kb_log_group_name" {
  description = "Name of the CloudWatch log group for Bedrock Knowledge Base"
  value       = aws_cloudwatch_log_group.bedrock_kb.name
}

output "bedrock_kb_log_group_arn" {
  description = "ARN of the CloudWatch log group for Bedrock Knowledge Base"
  value       = aws_cloudwatch_log_group.bedrock_kb.arn
}

output "bedrock_api_log_group_name" {
  description = "Name of the CloudWatch log group for Bedrock API calls"
  value       = aws_cloudwatch_log_group.bedrock_api.name
}

output "bedrock_api_log_group_arn" {
  description = "ARN of the CloudWatch log group for Bedrock API calls"
  value       = aws_cloudwatch_log_group.bedrock_api.arn
}

output "bedrock_ingestion_log_group_name" {
  description = "Name of the CloudWatch log group for Bedrock ingestion"
  value       = aws_cloudwatch_log_group.bedrock_ingestion.name
}

output "bedrock_ingestion_log_group_arn" {
  description = "ARN of the CloudWatch log group for Bedrock ingestion"
  value       = aws_cloudwatch_log_group.bedrock_ingestion.arn
}

output "opensearch_log_group_name" {
  description = "Name of the CloudWatch log group for OpenSearch"
  value       = aws_cloudwatch_log_group.opensearch.name
}

output "opensearch_log_group_arn" {
  description = "ARN of the CloudWatch log group for OpenSearch"
  value       = aws_cloudwatch_log_group.opensearch.arn
}

# Configuration Outputs
output "embedding_model_arn" {
  description = "ARN of the embedding model used"
  value       = var.embedding_model_arn
}

output "vector_dimension" {
  description = "Dimension of the vector embeddings"
  value       = var.vector_dimension
}

output "opensearch_index_name" {
  description = "Name of the OpenSearch vector index"
  value       = var.opensearch_index_name
}
