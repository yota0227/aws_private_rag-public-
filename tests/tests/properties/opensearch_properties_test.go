package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 9: OpenSearch Serverless Vector Configuration
// Feature: aws-bedrock-rag-deployment, Property 9: OpenSearch Serverless Vector Configuration
// Validates: Requirements 3.1, 3.3
//
// For any OpenSearch Serverless collection created by the module, it should be configured with
// vector search capabilities and have a vector index with dimension size matching the embedding
// model's output dimension.
func TestProperty9_OpenSearchServerlessVectorConfiguration(t *testing.T) {
	t.Parallel()

	bedrockRagDir := "../../modules/ai-workload/bedrock-rag"
	opensearchFile := filepath.Join(bedrockRagDir, "opensearch.tf")

	content, err := os.ReadFile(opensearchFile)
	require.NoError(t, err, "Should be able to read opensearch.tf")

	contentStr := string(content)

	// Test OpenSearch Serverless Collection Configuration
	t.Run("OpenSearch Serverless Collection Configuration", func(t *testing.T) {
		// Verify collection is defined
		assert.Contains(t, contentStr, `resource "aws_opensearchserverless_collection" "main"`,
			"Should define OpenSearch Serverless collection")

		// Extract collection block
		collectionStart := strings.Index(contentStr, `resource "aws_opensearchserverless_collection" "main"`)
		require.NotEqual(t, -1, collectionStart, "OpenSearch collection should exist")

		collectionEnd := findResourceBlockEnd(contentStr, collectionStart)
		collectionBlock := contentStr[collectionStart:collectionEnd]

		// Verify collection type is VECTORSEARCH
		assert.Contains(t, collectionBlock, `type        = "VECTORSEARCH"`,
			"Collection type should be VECTORSEARCH")

		// Verify collection name is configurable
		assert.Contains(t, collectionBlock, `name        = var.opensearch_collection_name`,
			"Collection name should be configurable")

		// Verify collection has description
		assert.Contains(t, collectionBlock, `description`,
			"Collection should have description")
	})

	// Test Vector Index Configuration
	t.Run("Vector Index Configuration", func(t *testing.T) {
		// Verify vector index creation is defined
		indexCreationExists := strings.Contains(contentStr, `resource "null_resource" "create_vector_index"`) ||
			strings.Contains(contentStr, `resource "local_file" "index_mapping"`)

		assert.True(t, indexCreationExists,
			"Should have vector index creation mechanism")

		// Verify index mapping includes vector field
		assert.Contains(t, contentStr, `bedrock-knowledge-base-default-vector`,
			"Index should have vector field for Bedrock")

		// Verify vector dimension is configurable
		hasDimensionConfig := strings.Contains(contentStr, `dimension = var.vector_dimension`) ||
			strings.Contains(contentStr, `dimension = ${var.vector_dimension}`)

		assert.True(t, hasDimensionConfig,
			"Vector dimension should be configurable")

		// Verify HNSW algorithm is configured
		assert.Contains(t, contentStr, `hnsw`,
			"Should use HNSW algorithm for vector search")

		// Verify FAISS engine is configured
		assert.Contains(t, contentStr, `faiss`,
			"Should use FAISS engine for vector search")

		// Verify text chunk field is configured
		assert.Contains(t, contentStr, `AMAZON_BEDROCK_TEXT_CHUNK`,
			"Index should have text chunk field")

		// Verify metadata field is configured
		assert.Contains(t, contentStr, `AMAZON_BEDROCK_METADATA`,
			"Index should have metadata field")
	})

	// Test Vector Dimension Variable
	t.Run("Vector Dimension Variable", func(t *testing.T) {
		variablesFile := filepath.Join(bedrockRagDir, "variables.tf")
		varContent, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		varStr := string(varContent)

		// Verify vector_dimension variable exists
		assert.Contains(t, varStr, `variable "vector_dimension"`,
			"Should have vector_dimension variable")

		// Extract vector_dimension variable block
		vectorDimStart := strings.Index(varStr, `variable "vector_dimension"`)
		require.NotEqual(t, -1, vectorDimStart, "vector_dimension variable should exist")

		vectorDimEnd := findResourceBlockEnd(varStr, vectorDimStart)
		vectorDimBlock := varStr[vectorDimStart:vectorDimEnd]

		// Verify default dimension is 1536 (Titan Embeddings)
		assert.Contains(t, vectorDimBlock, `default     = 1536`,
			"Vector dimension should default to 1536 for Titan Embeddings")

		// Verify validation exists
		assert.Contains(t, vectorDimBlock, `validation {`,
			"Vector dimension should have validation")
	})
}

// Property 10: OpenSearch Capacity Constraints
// Feature: aws-bedrock-rag-deployment, Property 10: OpenSearch Capacity Constraints
// Validates: Requirements 3.2, 11.1
//
// For any OpenSearch Serverless collection created by the module, the configured capacity units
// (OCU) should be within valid ranges (minimum 2 OCU for search and indexing).
func TestProperty10_OpenSearchCapacityConstraints(t *testing.T) {
	t.Parallel()

	bedrockRagDir := "../../modules/ai-workload/bedrock-rag"
	variablesFile := filepath.Join(bedrockRagDir, "variables.tf")

	content, err := os.ReadFile(variablesFile)
	require.NoError(t, err, "Should be able to read variables.tf")

	contentStr := string(content)

	// Test OpenSearch Capacity Units Variable
	t.Run("OpenSearch Capacity Units Variable", func(t *testing.T) {
		// Verify opensearch_capacity_units variable exists
		assert.Contains(t, contentStr, `variable "opensearch_capacity_units"`,
			"Should have opensearch_capacity_units variable")

		// Extract variable block
		capacityVarStart := strings.Index(contentStr, `variable "opensearch_capacity_units"`)
		require.NotEqual(t, -1, capacityVarStart, "opensearch_capacity_units variable should exist")

		capacityVarEnd := findResourceBlockEnd(contentStr, capacityVarStart)
		capacityVarBlock := contentStr[capacityVarStart:capacityVarEnd]

		// Verify type is object with search_ocu and indexing_ocu
		assert.Contains(t, capacityVarBlock, `type = object({`,
			"opensearch_capacity_units should be an object type")
		assert.Contains(t, capacityVarBlock, `search_ocu`,
			"Should have search_ocu field")
		assert.Contains(t, capacityVarBlock, `indexing_ocu`,
			"Should have indexing_ocu field")

		// Verify default values are at least 2 OCU
		assert.Contains(t, capacityVarBlock, `search_ocu   = 2`,
			"Default search OCU should be 2")
		assert.Contains(t, capacityVarBlock, `indexing_ocu = 2`,
			"Default indexing OCU should be 2")
	})

	// Test Minimum OCU Validation
	t.Run("Minimum OCU Validation", func(t *testing.T) {
		// Extract variable block
		capacityVarStart := strings.Index(contentStr, `variable "opensearch_capacity_units"`)
		require.NotEqual(t, -1, capacityVarStart, "opensearch_capacity_units variable should exist")

		capacityVarEnd := findResourceBlockEnd(contentStr, capacityVarStart)
		capacityVarBlock := contentStr[capacityVarStart:capacityVarEnd]

		// Verify validation for minimum 2 OCU
		assert.Contains(t, capacityVarBlock, `validation {`,
			"Should have validation rules")

		// Check for minimum OCU constraint
		hasMinValidation := strings.Contains(capacityVarBlock, `>= 2`) &&
			strings.Contains(capacityVarBlock, `search_ocu`) &&
			strings.Contains(capacityVarBlock, `indexing_ocu`)

		assert.True(t, hasMinValidation,
			"Should validate minimum 2 OCU for search and indexing")

		// Verify error message mentions minimum requirement
		assert.Contains(t, capacityVarBlock, `minimum 2 OCU`,
			"Error message should mention minimum 2 OCU requirement")
	})

	// Test Maximum OCU Validation
	t.Run("Maximum OCU Validation", func(t *testing.T) {
		// Extract variable block
		capacityVarStart := strings.Index(contentStr, `variable "opensearch_capacity_units"`)
		require.NotEqual(t, -1, capacityVarStart, "opensearch_capacity_units variable should exist")

		capacityVarEnd := findResourceBlockEnd(contentStr, capacityVarStart)
		capacityVarBlock := contentStr[capacityVarStart:capacityVarEnd]

		// Check for maximum OCU constraint
		hasMaxValidation := strings.Contains(capacityVarBlock, `<= 40`) &&
			strings.Contains(capacityVarBlock, `search_ocu`) &&
			strings.Contains(capacityVarBlock, `indexing_ocu`)

		assert.True(t, hasMaxValidation,
			"Should validate maximum 40 OCU for search and indexing")

		// Verify error message mentions maximum limit
		assert.Contains(t, capacityVarBlock, `maximum is 40 OCU`,
			"Error message should mention maximum 40 OCU limit")
	})
}

// Property 11: OpenSearch Data Access Policies
// Feature: aws-bedrock-rag-deployment, Property 11: OpenSearch Data Access Policies
// Validates: Requirements 3.4
//
// For any OpenSearch Serverless collection created by the module, data access policies should be
// configured to grant access to the Bedrock Knowledge Base role.
func TestProperty11_OpenSearchDataAccessPolicies(t *testing.T) {
	t.Parallel()

	bedrockRagDir := "../../modules/ai-workload/bedrock-rag"
	opensearchFile := filepath.Join(bedrockRagDir, "opensearch.tf")

	content, err := os.ReadFile(opensearchFile)
	require.NoError(t, err, "Should be able to read opensearch.tf")

	contentStr := string(content)

	// Test Data Access Policy Configuration
	t.Run("Data Access Policy Configuration", func(t *testing.T) {
		// Verify data access policy is defined
		assert.Contains(t, contentStr, `resource "aws_opensearchserverless_access_policy" "data_access"`,
			"Should define data access policy")

		// Extract policy block
		policyStart := strings.Index(contentStr, `resource "aws_opensearchserverless_access_policy" "data_access"`)
		require.NotEqual(t, -1, policyStart, "Data access policy should exist")

		policyEnd := findResourceBlockEnd(contentStr, policyStart)
		policyBlock := contentStr[policyStart:policyEnd]

		// Verify policy type is data
		assert.Contains(t, policyBlock, `type        = "data"`,
			"Policy type should be data")

		// Verify policy grants access to Bedrock execution role
		assert.Contains(t, policyBlock, `var.bedrock_execution_role_arn`,
			"Policy should grant access to Bedrock execution role")

		// Verify policy grants access to OpenSearch access role
		assert.Contains(t, policyBlock, `var.opensearch_access_role_arn`,
			"Policy should grant access to OpenSearch access role")

		// Verify required permissions for collection
		requiredCollectionPermissions := []string{
			"aoss:CreateCollectionItems",
			"aoss:UpdateCollectionItems",
			"aoss:DescribeCollectionItems",
		}

		for _, permission := range requiredCollectionPermissions {
			assert.Contains(t, policyBlock, permission,
				"Policy should include %s permission", permission)
		}

		// Verify required permissions for index
		requiredIndexPermissions := []string{
			"aoss:CreateIndex",
			"aoss:DescribeIndex",
			"aoss:ReadDocument",
			"aoss:WriteDocument",
			"aoss:UpdateIndex",
		}

		for _, permission := range requiredIndexPermissions {
			assert.Contains(t, policyBlock, permission,
				"Policy should include %s permission", permission)
		}
	})

	// Test Policy Dependencies
	t.Run("Policy Dependencies", func(t *testing.T) {
		// Extract policy block
		policyStart := strings.Index(contentStr, `resource "aws_opensearchserverless_access_policy" "data_access"`)
		require.NotEqual(t, -1, policyStart, "Data access policy should exist")

		policyEnd := findResourceBlockEnd(contentStr, policyStart)
		policyBlock := contentStr[policyStart:policyEnd]

		// Verify policy depends on collection
		assert.Contains(t, policyBlock, `depends_on`,
			"Policy should have dependencies")
		assert.Contains(t, policyBlock, `aws_opensearchserverless_collection.main`,
			"Policy should depend on collection creation")
	})
}

// Property 12: OpenSearch Encryption and Network Isolation
// Feature: aws-bedrock-rag-deployment, Property 12: OpenSearch Encryption and Network Isolation
// Validates: Requirements 3.5, 3.6
//
// For any OpenSearch Serverless collection created by the module, encryption at rest using KMS
// should be enabled, and network access policies should restrict connections to VPC endpoints only.
func TestProperty12_OpenSearchEncryptionAndNetworkIsolation(t *testing.T) {
	t.Parallel()

	bedrockRagDir := "../../modules/ai-workload/bedrock-rag"
	opensearchFile := filepath.Join(bedrockRagDir, "opensearch.tf")

	content, err := os.ReadFile(opensearchFile)
	require.NoError(t, err, "Should be able to read opensearch.tf")

	contentStr := string(content)

	// Test Encryption Policy Configuration
	t.Run("Encryption Policy Configuration", func(t *testing.T) {
		// Verify encryption policy is defined
		assert.Contains(t, contentStr, `resource "aws_opensearchserverless_security_policy" "encryption"`,
			"Should define encryption security policy")

		// Extract encryption policy block
		encryptionStart := strings.Index(contentStr, `resource "aws_opensearchserverless_security_policy" "encryption"`)
		require.NotEqual(t, -1, encryptionStart, "Encryption policy should exist")

		encryptionEnd := findResourceBlockEnd(contentStr, encryptionStart)
		encryptionBlock := contentStr[encryptionStart:encryptionEnd]

		// Verify policy type is encryption
		assert.Contains(t, encryptionBlock, `type        = "encryption"`,
			"Policy type should be encryption")

		// Verify KMS key is used (not AWS owned key)
		assert.Contains(t, encryptionBlock, `AWSOwnedKey = false`,
			"Should not use AWS owned key")
		assert.Contains(t, encryptionBlock, `KmsARN      = var.kms_key_arn`,
			"Should use customer-managed KMS key")

		// Verify policy applies to collection
		assert.Contains(t, encryptionBlock, `ResourceType = "collection"`,
			"Encryption policy should apply to collection")
	})

	// Test Network Policy Configuration
	t.Run("Network Policy Configuration", func(t *testing.T) {
		// Verify network policy is defined
		assert.Contains(t, contentStr, `resource "aws_opensearchserverless_security_policy" "network"`,
			"Should define network security policy")

		// Extract network policy block
		networkStart := strings.Index(contentStr, `resource "aws_opensearchserverless_security_policy" "network"`)
		require.NotEqual(t, -1, networkStart, "Network policy should exist")

		networkEnd := findResourceBlockEnd(contentStr, networkStart)
		networkBlock := contentStr[networkStart:networkEnd]

		// Verify policy type is network
		assert.Contains(t, networkBlock, `type        = "network"`,
			"Policy type should be network")

		// Verify public access is disabled
		assert.Contains(t, networkBlock, `AllowFromPublic = false`,
			"Public access should be disabled")

		// Verify policy applies to collection
		assert.Contains(t, networkBlock, `ResourceType = "collection"`,
			"Network policy should apply to collection")
	})

	// Test Collection Dependencies on Security Policies
	t.Run("Collection Dependencies on Security Policies", func(t *testing.T) {
		// Extract collection block
		collectionStart := strings.Index(contentStr, `resource "aws_opensearchserverless_collection" "main"`)
		require.NotEqual(t, -1, collectionStart, "OpenSearch collection should exist")

		collectionEnd := findResourceBlockEnd(contentStr, collectionStart)
		collectionBlock := contentStr[collectionStart:collectionEnd]

		// Verify collection depends on security policies
		assert.Contains(t, collectionBlock, `depends_on`,
			"Collection should have dependencies")
		assert.Contains(t, collectionBlock, `aws_opensearchserverless_security_policy.encryption`,
			"Collection should depend on encryption policy")
		assert.Contains(t, collectionBlock, `aws_opensearchserverless_security_policy.network`,
			"Collection should depend on network policy")
	})

	// Test CloudWatch Logging
	t.Run("CloudWatch Logging", func(t *testing.T) {
		// Verify CloudWatch log group is defined
		assert.Contains(t, contentStr, `resource "aws_cloudwatch_log_group" "opensearch"`,
			"Should define CloudWatch log group for OpenSearch")

		// Extract log group block
		logGroupStart := strings.Index(contentStr, `resource "aws_cloudwatch_log_group" "opensearch"`)
		require.NotEqual(t, -1, logGroupStart, "CloudWatch log group should exist")

		logGroupEnd := findResourceBlockEnd(contentStr, logGroupStart)
		logGroupBlock := contentStr[logGroupStart:logGroupEnd]

		// Verify log group uses KMS encryption
		assert.Contains(t, logGroupBlock, `kms_key_id        = var.kms_key_arn`,
			"Log group should use KMS encryption")

		// Verify retention is configured
		assert.Contains(t, logGroupBlock, `retention_in_days`,
			"Log group should have retention configured")
	})
}

// TestOpenSearchModuleVariables tests that OpenSearch module has required variables
// Validates: Requirements 12.3
func TestOpenSearchModuleVariables(t *testing.T) {
	t.Parallel()

	bedrockRagDir := "../../modules/ai-workload/bedrock-rag"
	variablesFile := filepath.Join(bedrockRagDir, "variables.tf")

	content, err := os.ReadFile(variablesFile)
	require.NoError(t, err, "Should be able to read variables.tf")

	contentStr := string(content)

	// Verify required variables exist
	requiredVariables := []string{
		"opensearch_collection_name",
		"opensearch_index_name",
		"vector_dimension",
		"opensearch_capacity_units",
		"kms_key_arn",
		"bedrock_execution_role_arn",
		"opensearch_access_role_arn",
	}

	for _, varName := range requiredVariables {
		assert.Contains(t, contentStr, `variable "`+varName+`"`,
			"Should define %s variable", varName)

		// Extract variable block
		varStart := strings.Index(contentStr, `variable "`+varName+`"`)
		if varStart != -1 {
			varEnd := findResourceBlockEnd(contentStr, varStart)
			varBlock := contentStr[varStart:varEnd]

			assert.Contains(t, varBlock, `description`,
				"Variable %s should have description", varName)
		}
	}
}

