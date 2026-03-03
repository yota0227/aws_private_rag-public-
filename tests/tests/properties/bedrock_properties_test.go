package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 6: Bedrock Knowledge Base Configuration
// Feature: aws-bedrock-rag-deployment, Property 6: Bedrock Knowledge Base Configuration
// Validates: Requirements 2.2, 2.3, 2.4
//
// For any Bedrock Knowledge Base created by the module, it should have a configured foundation
// model ARN, embedding model ARN, and data source connection to an S3 bucket.
func TestProperty6_BedrockKnowledgeBaseConfiguration(t *testing.T) {
	t.Parallel()

	bedrockRagDir := "../../modules/ai-workload/bedrock-rag"
	knowledgeBaseFile := filepath.Join(bedrockRagDir, "knowledge-base.tf")

	content, err := os.ReadFile(knowledgeBaseFile)
	require.NoError(t, err, "Should be able to read knowledge-base.tf")

	contentStr := string(content)

	// Test Knowledge Base Resource Configuration
	t.Run("Knowledge Base Resource Configuration", func(t *testing.T) {
		// Verify Knowledge Base is defined
		assert.Contains(t, contentStr, `resource "aws_bedrockagent_knowledge_base" "main"`,
			"Should define Bedrock Knowledge Base")

		// Extract Knowledge Base block
		kbStart := strings.Index(contentStr, `resource "aws_bedrockagent_knowledge_base" "main"`)
		require.NotEqual(t, -1, kbStart, "Knowledge Base should exist")

		kbEnd := findResourceBlockEnd(contentStr, kbStart)
		kbBlock := contentStr[kbStart:kbEnd]

		// Verify name is configurable
		assert.Contains(t, kbBlock, `name        = var.knowledge_base_name`,
			"Knowledge Base name should be configurable")

		// Verify role ARN is configured
		assert.Contains(t, kbBlock, `role_arn    = var.bedrock_execution_role_arn`,
			"Knowledge Base should have execution role")

		// Verify knowledge_base_configuration block exists
		assert.Contains(t, kbBlock, `knowledge_base_configuration {`,
			"Knowledge Base should have configuration block")

		// Verify type is VECTOR
		assert.Contains(t, kbBlock, `type = "VECTOR"`,
			"Knowledge Base type should be VECTOR")
	})

	// Test Embedding Model Configuration
	t.Run("Embedding Model Configuration", func(t *testing.T) {
		// Extract Knowledge Base block
		kbStart := strings.Index(contentStr, `resource "aws_bedrockagent_knowledge_base" "main"`)
		require.NotEqual(t, -1, kbStart, "Knowledge Base should exist")

		kbEnd := findResourceBlockEnd(contentStr, kbStart)
		kbBlock := contentStr[kbStart:kbEnd]

		// Verify vector_knowledge_base_configuration exists
		assert.Contains(t, kbBlock, `vector_knowledge_base_configuration {`,
			"Knowledge Base should have vector configuration")

		// Verify embedding model ARN is configured
		assert.Contains(t, kbBlock, `embedding_model_arn = var.embedding_model_arn`,
			"Knowledge Base should have embedding model ARN")
	})

	// Test S3 Data Source Configuration
	t.Run("S3 Data Source Configuration", func(t *testing.T) {
		// Verify Data Source is defined
		assert.Contains(t, contentStr, `resource "aws_bedrockagent_data_source" "s3"`,
			"Should define Bedrock Data Source")

		// Extract Data Source block
		dsStart := strings.Index(contentStr, `resource "aws_bedrockagent_data_source" "s3"`)
		require.NotEqual(t, -1, dsStart, "Data Source should exist")

		dsEnd := findResourceBlockEnd(contentStr, dsStart)
		dsBlock := contentStr[dsStart:dsEnd]

		// Verify data source is linked to Knowledge Base
		assert.Contains(t, dsBlock, `knowledge_base_id = aws_bedrockagent_knowledge_base.main.id`,
			"Data Source should be linked to Knowledge Base")

		// Verify data_source_configuration block exists
		assert.Contains(t, dsBlock, `data_source_configuration {`,
			"Data Source should have configuration block")

		// Verify type is S3
		assert.Contains(t, dsBlock, `type = "S3"`,
			"Data Source type should be S3")

		// Verify S3 configuration exists
		assert.Contains(t, dsBlock, `s3_configuration {`,
			"Data Source should have S3 configuration")

		// Verify bucket ARN is configured
		assert.Contains(t, dsBlock, `bucket_arn = var.s3_data_source_bucket_arn`,
			"Data Source should reference S3 bucket ARN")
	})

	// Test Embedding Model Variable
	t.Run("Embedding Model Variable", func(t *testing.T) {
		variablesFile := filepath.Join(bedrockRagDir, "variables.tf")
		varContent, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		varStr := string(varContent)

		// Verify embedding_model_arn variable exists
		assert.Contains(t, varStr, `variable "embedding_model_arn"`,
			"Should have embedding_model_arn variable")

		// Extract variable block
		embeddingVarStart := strings.Index(varStr, `variable "embedding_model_arn"`)
		require.NotEqual(t, -1, embeddingVarStart, "embedding_model_arn variable should exist")

		embeddingVarEnd := findResourceBlockEnd(varStr, embeddingVarStart)
		embeddingVarBlock := varStr[embeddingVarStart:embeddingVarEnd]

		// Verify default value is Titan Embeddings
		assert.Contains(t, embeddingVarBlock, `amazon.titan-embed-text-v1`,
			"Default embedding model should be Titan Embeddings")
	})

	// Test Foundation Model Variable
	t.Run("Foundation Model Variable", func(t *testing.T) {
		variablesFile := filepath.Join(bedrockRagDir, "variables.tf")
		varContent, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		varStr := string(varContent)

		// Verify foundation_model_arn variable exists
		assert.Contains(t, varStr, `variable "foundation_model_arn"`,
			"Should have foundation_model_arn variable")

		// Extract variable block
		foundationVarStart := strings.Index(varStr, `variable "foundation_model_arn"`)
		require.NotEqual(t, -1, foundationVarStart, "foundation_model_arn variable should exist")

		foundationVarEnd := findResourceBlockEnd(varStr, foundationVarStart)
		foundationVarBlock := varStr[foundationVarStart:foundationVarEnd]

		// Verify default value is Claude
		assert.Contains(t, foundationVarBlock, `anthropic.claude`,
			"Default foundation model should be Claude")
	})
}

// Property 7: Knowledge Base Vector Store Integration
// Feature: aws-bedrock-rag-deployment, Property 7: Knowledge Base Vector Store Integration
// Validates: Requirements 2.5
//
// For any Bedrock Knowledge Base created by the module, its storage configuration should
// reference an OpenSearch Serverless collection as the vector store.
func TestProperty7_KnowledgeBaseVectorStoreIntegration(t *testing.T) {
	t.Parallel()

	bedrockRagDir := "../../modules/ai-workload/bedrock-rag"
	knowledgeBaseFile := filepath.Join(bedrockRagDir, "knowledge-base.tf")

	content, err := os.ReadFile(knowledgeBaseFile)
	require.NoError(t, err, "Should be able to read knowledge-base.tf")

	contentStr := string(content)

	// Test Storage Configuration
	t.Run("Storage Configuration", func(t *testing.T) {
		// Extract Knowledge Base block
		kbStart := strings.Index(contentStr, `resource "aws_bedrockagent_knowledge_base" "main"`)
		require.NotEqual(t, -1, kbStart, "Knowledge Base should exist")

		kbEnd := findResourceBlockEnd(contentStr, kbStart)
		kbBlock := contentStr[kbStart:kbEnd]

		// Verify storage_configuration block exists
		assert.Contains(t, kbBlock, `storage_configuration {`,
			"Knowledge Base should have storage configuration")

		// Verify type is OPENSEARCH_SERVERLESS
		assert.Contains(t, kbBlock, `type = "OPENSEARCH_SERVERLESS"`,
			"Storage type should be OpenSearch Serverless")

		// Verify opensearch_serverless_configuration exists
		assert.Contains(t, kbBlock, `opensearch_serverless_configuration {`,
			"Knowledge Base should have OpenSearch Serverless configuration")
	})

	// Test OpenSearch Integration
	t.Run("OpenSearch Integration", func(t *testing.T) {
		// Extract Knowledge Base block
		kbStart := strings.Index(contentStr, `resource "aws_bedrockagent_knowledge_base" "main"`)
		require.NotEqual(t, -1, kbStart, "Knowledge Base should exist")

		kbEnd := findResourceBlockEnd(contentStr, kbStart)
		kbBlock := contentStr[kbStart:kbEnd]

		// Verify collection ARN is referenced
		assert.Contains(t, kbBlock, `collection_arn    = aws_opensearchserverless_collection.main.arn`,
			"Knowledge Base should reference OpenSearch collection ARN")

		// Verify vector index name is configured
		assert.Contains(t, kbBlock, `vector_index_name = var.opensearch_index_name`,
			"Knowledge Base should reference vector index name")

		// Verify field mapping exists
		assert.Contains(t, kbBlock, `field_mapping {`,
			"Knowledge Base should have field mapping")

		// Verify vector field is mapped
		assert.Contains(t, kbBlock, `vector_field   = "bedrock-knowledge-base-default-vector"`,
			"Knowledge Base should map vector field")

		// Verify text field is mapped
		assert.Contains(t, kbBlock, `text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"`,
			"Knowledge Base should map text field")

		// Verify metadata field is mapped
		assert.Contains(t, kbBlock, `metadata_field = "AMAZON_BEDROCK_METADATA"`,
			"Knowledge Base should map metadata field")
	})

	// Test Dependencies
	t.Run("Dependencies", func(t *testing.T) {
		// Extract Knowledge Base block
		kbStart := strings.Index(contentStr, `resource "aws_bedrockagent_knowledge_base" "main"`)
		require.NotEqual(t, -1, kbStart, "Knowledge Base should exist")

		kbEnd := findResourceBlockEnd(contentStr, kbStart)
		kbBlock := contentStr[kbStart:kbEnd]

		// Verify Knowledge Base depends on OpenSearch collection
		assert.Contains(t, kbBlock, `depends_on`,
			"Knowledge Base should have dependencies")
		assert.Contains(t, kbBlock, `aws_opensearchserverless_collection.main`,
			"Knowledge Base should depend on OpenSearch collection")
		assert.Contains(t, kbBlock, `aws_opensearchserverless_access_policy.data_access`,
			"Knowledge Base should depend on access policy")
	})
}

// Property 8: Bedrock CloudWatch Logging
// Feature: aws-bedrock-rag-deployment, Property 8: Bedrock CloudWatch Logging
// Validates: Requirements 2.6
//
// For any Bedrock Knowledge Base created by the module, CloudWatch log groups should be
// configured to capture API calls and operations.
func TestProperty8_BedrockCloudWatchLogging(t *testing.T) {
	t.Parallel()

	bedrockRagDir := "../../modules/ai-workload/bedrock-rag"
	knowledgeBaseFile := filepath.Join(bedrockRagDir, "knowledge-base.tf")

	content, err := os.ReadFile(knowledgeBaseFile)
	require.NoError(t, err, "Should be able to read knowledge-base.tf")

	contentStr := string(content)

	// Test Knowledge Base Log Group
	t.Run("Knowledge Base Log Group", func(t *testing.T) {
		// Verify log group is defined
		assert.Contains(t, contentStr, `resource "aws_cloudwatch_log_group" "bedrock_kb"`,
			"Should define CloudWatch log group for Knowledge Base")

		// Extract log group block
		logGroupStart := strings.Index(contentStr, `resource "aws_cloudwatch_log_group" "bedrock_kb"`)
		require.NotEqual(t, -1, logGroupStart, "Knowledge Base log group should exist")

		logGroupEnd := findResourceBlockEnd(contentStr, logGroupStart)
		logGroupBlock := contentStr[logGroupStart:logGroupEnd]

		// Verify log group name follows convention
		assert.Contains(t, logGroupBlock, `/aws/bedrock/knowledgebase/`,
			"Log group name should follow AWS Bedrock convention")

		// Verify retention is configured
		assert.Contains(t, logGroupBlock, `retention_in_days`,
			"Log group should have retention configured")

		// Verify KMS encryption is configured
		assert.Contains(t, logGroupBlock, `kms_key_id        = var.kms_key_arn`,
			"Log group should use KMS encryption")
	})

	// Test API Log Group
	t.Run("API Log Group", func(t *testing.T) {
		// Verify API log group is defined
		assert.Contains(t, contentStr, `resource "aws_cloudwatch_log_group" "bedrock_api"`,
			"Should define CloudWatch log group for Bedrock API")

		// Extract log group block
		logGroupStart := strings.Index(contentStr, `resource "aws_cloudwatch_log_group" "bedrock_api"`)
		require.NotEqual(t, -1, logGroupStart, "API log group should exist")

		logGroupEnd := findResourceBlockEnd(contentStr, logGroupStart)
		logGroupBlock := contentStr[logGroupStart:logGroupEnd]

		// Verify log group name follows convention
		assert.Contains(t, logGroupBlock, `/aws/bedrock/api/`,
			"API log group name should follow AWS Bedrock convention")

		// Verify KMS encryption is configured
		assert.Contains(t, logGroupBlock, `kms_key_id        = var.kms_key_arn`,
			"API log group should use KMS encryption")
	})

	// Test Ingestion Log Group
	t.Run("Ingestion Log Group", func(t *testing.T) {
		// Verify ingestion log group is defined
		assert.Contains(t, contentStr, `resource "aws_cloudwatch_log_group" "bedrock_ingestion"`,
			"Should define CloudWatch log group for Bedrock ingestion")

		// Extract log group block
		logGroupStart := strings.Index(contentStr, `resource "aws_cloudwatch_log_group" "bedrock_ingestion"`)
		require.NotEqual(t, -1, logGroupStart, "Ingestion log group should exist")

		logGroupEnd := findResourceBlockEnd(contentStr, logGroupStart)
		logGroupBlock := contentStr[logGroupStart:logGroupEnd]

		// Verify log group name follows convention
		assert.Contains(t, logGroupBlock, `/aws/bedrock/datasource/`,
			"Ingestion log group name should follow AWS Bedrock convention")

		// Verify KMS encryption is configured
		assert.Contains(t, logGroupBlock, `kms_key_id        = var.kms_key_arn`,
			"Ingestion log group should use KMS encryption")
	})
}

// TestBedrockModuleOutputs tests that Bedrock module exposes required outputs
// Validates: Requirements 12.4
func TestBedrockModuleOutputs(t *testing.T) {
	t.Parallel()

	bedrockRagDir := "../../modules/ai-workload/bedrock-rag"
	outputsFile := filepath.Join(bedrockRagDir, "outputs.tf")

	content, err := os.ReadFile(outputsFile)
	require.NoError(t, err, "Should be able to read outputs.tf")

	contentStr := string(content)

	// Verify required Knowledge Base outputs
	kbOutputs := []string{
		"knowledge_base_id",
		"knowledge_base_arn",
		"knowledge_base_name",
	}

	for _, output := range kbOutputs {
		assert.Contains(t, contentStr, `output "`+output+`"`,
			"Should define %s output", output)

		// Extract output block
		outputStart := strings.Index(contentStr, `output "`+output+`"`)
		if outputStart != -1 {
			outputEnd := findResourceBlockEnd(contentStr, outputStart)
			outputBlock := contentStr[outputStart:outputEnd]

			assert.Contains(t, outputBlock, `description`,
				"Output %s should have description", output)
			assert.Contains(t, outputBlock, `value`,
				"Output %s should have value", output)
		}
	}

	// Verify required Data Source outputs
	dsOutputs := []string{
		"data_source_id",
		"data_source_arn",
	}

	for _, output := range dsOutputs {
		assert.Contains(t, contentStr, `output "`+output+`"`,
			"Should define %s output", output)
	}

	// Verify required OpenSearch outputs
	osOutputs := []string{
		"opensearch_collection_endpoint",
		"opensearch_collection_arn",
	}

	for _, output := range osOutputs {
		assert.Contains(t, contentStr, `output "`+output+`"`,
			"Should define %s output", output)
	}

	// Verify required CloudWatch log group outputs
	logOutputs := []string{
		"bedrock_kb_log_group_name",
		"bedrock_api_log_group_name",
		"bedrock_ingestion_log_group_name",
	}

	for _, output := range logOutputs {
		assert.Contains(t, contentStr, `output "`+output+`"`,
			"Should define %s output", output)
	}
}

