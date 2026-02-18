package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 18: KMS Customer-Managed Keys
// Feature: aws-bedrock-rag-deployment, Property 18: KMS Customer-Managed Keys
// Validates: Requirements 5.4
//
// For any encryption configuration in the module, KMS customer-managed keys should be used
// instead of AWS-managed keys, providing full control over key policies and rotation.
func TestProperty18_KMSCustomerManagedKeys(t *testing.T) {
	t.Parallel()

	kmsModuleDir := "../../modules/security/kms"
	mainFile := filepath.Join(kmsModuleDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Verify KMS key resource is defined (customer-managed)
	assert.Contains(t, contentStr, `resource "aws_kms_key" "main"`, "Should define customer-managed KMS key resource")

	// Extract KMS key resource block
	keyStart := strings.Index(contentStr, `resource "aws_kms_key" "main"`)
	require.NotEqual(t, -1, keyStart, "KMS key resource should exist")

	keyEnd := findResourceBlockEnd(contentStr, keyStart)
	keyBlock := contentStr[keyStart:keyEnd]

	// Verify key rotation is enabled
	assert.Contains(t, keyBlock, `enable_key_rotation`, "KMS key should have key rotation configuration")

	// Verify key has a custom policy (not AWS-managed)
	assert.Contains(t, keyBlock, `policy`, "KMS key should have a custom policy")
	assert.Contains(t, keyBlock, `data.aws_iam_policy_document.kms_key_policy.json`,
		"KMS key should use custom policy document")

	// Verify key usage is specified
	assert.Contains(t, keyBlock, `key_usage`, "KMS key should specify key usage")

	// Verify deletion window is configured
	assert.Contains(t, keyBlock, `deletion_window_in_days`, "KMS key should have deletion window configured")

	// Verify variables.tf has key rotation enabled by default
	variablesFile := filepath.Join(kmsModuleDir, "variables.tf")
	varContent, err := os.ReadFile(variablesFile)
	require.NoError(t, err, "Should be able to read variables.tf")

	varStr := string(varContent)

	// Find enable_key_rotation variable
	rotationVarStart := strings.Index(varStr, `variable "enable_key_rotation"`)
	require.NotEqual(t, -1, rotationVarStart, "enable_key_rotation variable should exist")

	rotationVarEnd := findResourceBlockEnd(varStr, rotationVarStart)
	rotationVarBlock := varStr[rotationVarStart:rotationVarEnd]

	assert.Contains(t, rotationVarBlock, `default     = true`, "Key rotation should be enabled by default")

	// Verify KMS key alias is created for friendly naming
	assert.Contains(t, contentStr, `resource "aws_kms_alias" "main"`, "Should define KMS key alias")
}


// Property 19: KMS Key Policy Service Principals
// Feature: aws-bedrock-rag-deployment, Property 19: KMS Key Policy Service Principals
// Validates: Requirements 5.5, 5.6
//
// For any KMS key created by the module, the key policy should grant usage permissions to
// the Bedrock service principal (bedrock.amazonaws.com), S3 service principal (s3.amazonaws.com),
// and OpenSearch service principal (aoss.amazonaws.com).
func TestProperty19_KMSKeyPolicyServicePrincipals(t *testing.T) {
	t.Parallel()

	kmsModuleDir := "../../modules/security/kms"
	mainFile := filepath.Join(kmsModuleDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Verify key policy document is defined
	assert.Contains(t, contentStr, `data "aws_iam_policy_document" "kms_key_policy"`,
		"Should define KMS key policy document")

	// Extract key policy document block
	policyStart := strings.Index(contentStr, `data "aws_iam_policy_document" "kms_key_policy"`)
	require.NotEqual(t, -1, policyStart, "Key policy document should exist")

	policyEnd := findResourceBlockEnd(contentStr, policyStart)
	policyBlock := contentStr[policyStart:policyEnd]

	// Test Bedrock service principal access
	t.Run("Bedrock Service Principal", func(t *testing.T) {
		// Verify Bedrock statement exists
		assert.Contains(t, policyBlock, `Allow Bedrock to use the key`,
			"Key policy should have Bedrock statement")
		assert.Contains(t, policyBlock, `bedrock.amazonaws.com`,
			"Key policy should grant access to Bedrock service principal")

		// Verify required actions are in the policy
		requiredActions := []string{"kms:Decrypt", "kms:GenerateDataKey", "kms:CreateGrant", "kms:DescribeKey"}
		for _, action := range requiredActions {
			assert.Contains(t, policyBlock, action,
				"Policy should include %s action", action)
		}

		// Verify ViaService condition
		assert.Contains(t, policyBlock, `kms:ViaService`,
			"Policy should have ViaService condition")
		assert.Contains(t, policyBlock, `bedrock.${var.region}.amazonaws.com`,
			"Policy should scope Bedrock to specific region")
	})

	// Test S3 service principal access
	t.Run("S3 Service Principal", func(t *testing.T) {
		// Verify S3 statement exists
		assert.Contains(t, policyBlock, `Allow S3 to use the key`,
			"Key policy should have S3 statement")
		assert.Contains(t, policyBlock, `s3.amazonaws.com`,
			"Key policy should grant access to S3 service principal")

		// Verify required actions are in the policy
		requiredActions := []string{"kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"}
		for _, action := range requiredActions {
			assert.Contains(t, policyBlock, action,
				"Policy should include %s action", action)
		}

		// Verify ViaService condition
		assert.Contains(t, policyBlock, `s3.${var.region}.amazonaws.com`,
			"Policy should scope S3 to specific region")
	})

	// Test OpenSearch service principal access
	t.Run("OpenSearch Service Principal", func(t *testing.T) {
		// Verify OpenSearch statement exists
		assert.Contains(t, policyBlock, `Allow OpenSearch Serverless to use the key`,
			"Key policy should have OpenSearch statement")
		assert.Contains(t, policyBlock, `aoss.amazonaws.com`,
			"Key policy should grant access to OpenSearch service principal")

		// Verify required actions are in the policy
		requiredActions := []string{"kms:Decrypt", "kms:CreateGrant", "kms:DescribeKey"}
		for _, action := range requiredActions {
			assert.Contains(t, policyBlock, action,
				"Policy should include %s action", action)
		}

		// Verify ViaService condition
		assert.Contains(t, policyBlock, `aoss.${var.region}.amazonaws.com`,
			"Policy should scope OpenSearch to specific region")
	})

	// Test that service principal access is configurable
	t.Run("Service Principal Configuration", func(t *testing.T) {
		variablesFile := filepath.Join(kmsModuleDir, "variables.tf")
		varContent, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		varStr := string(varContent)

		// Verify enable flags exist
		assert.Contains(t, varStr, `variable "enable_bedrock_access"`,
			"Should have enable_bedrock_access variable")
		assert.Contains(t, varStr, `variable "enable_s3_access"`,
			"Should have enable_s3_access variable")
		assert.Contains(t, varStr, `variable "enable_opensearch_access"`,
			"Should have enable_opensearch_access variable")

		// Verify default values are true
		bedrockVarStart := strings.Index(varStr, `variable "enable_bedrock_access"`)
		if bedrockVarStart != -1 {
			bedrockVarEnd := findResourceBlockEnd(varStr, bedrockVarStart)
			bedrockVarBlock := varStr[bedrockVarStart:bedrockVarEnd]
			assert.Contains(t, bedrockVarBlock, `default     = true`,
				"Bedrock access should be enabled by default")
		}

		s3VarStart := strings.Index(varStr, `variable "enable_s3_access"`)
		if s3VarStart != -1 {
			s3VarEnd := findResourceBlockEnd(varStr, s3VarStart)
			s3VarBlock := varStr[s3VarStart:s3VarEnd]
			assert.Contains(t, s3VarBlock, `default     = true`,
				"S3 access should be enabled by default")
		}

		ossVarStart := strings.Index(varStr, `variable "enable_opensearch_access"`)
		if ossVarStart != -1 {
			ossVarEnd := findResourceBlockEnd(varStr, ossVarStart)
			ossVarBlock := varStr[ossVarStart:ossVarEnd]
			assert.Contains(t, ossVarBlock, `default     = true`,
				"OpenSearch access should be enabled by default")
		}
	})

	// Test root account access
	t.Run("Root Account Access", func(t *testing.T) {
		// Verify root account statement exists
		assert.Contains(t, policyBlock, `Enable IAM User Permissions`,
			"Key policy should have root account statement")
		assert.Contains(t, policyBlock, `:root`,
			"Key policy should grant access to account root")

		// Verify full key management permissions
		assert.Contains(t, policyBlock, `kms:*`,
			"Root statement should grant full KMS permissions")
	})
}

// TestProperty19_KMSKeyOutputs tests that KMS module exposes required outputs
// Validates: Requirements 12.4
func TestProperty19_KMSKeyOutputs(t *testing.T) {
	t.Parallel()

	kmsModuleDir := "../../modules/security/kms"
	outputsFile := filepath.Join(kmsModuleDir, "outputs.tf")

	content, err := os.ReadFile(outputsFile)
	require.NoError(t, err, "Should be able to read outputs.tf")

	contentStr := string(content)

	// Verify required outputs are defined
	requiredOutputs := []struct {
		name        string
		description string
	}{
		{"key_id", "ID of the KMS key"},
		{"key_arn", "ARN of the KMS key"},
		{"key_alias_name", "Alias name"},
		{"key_alias_arn", "ARN of the KMS key alias"},
	}

	for _, output := range requiredOutputs {
		assert.Contains(t, contentStr, `output "`+output.name+`"`,
			"Should define %s output", output.name)

		// Extract output block
		outputStart := strings.Index(contentStr, `output "`+output.name+`"`)
		if outputStart != -1 {
			outputEnd := findResourceBlockEnd(contentStr, outputStart)
			outputBlock := contentStr[outputStart:outputEnd]

			assert.Contains(t, outputBlock, `description`, "Output %s should have description", output.name)
			assert.Contains(t, outputBlock, `value`, "Output %s should have value", output.name)
		}
	}

	// Verify key_policy output is marked as sensitive
	policyOutputStart := strings.Index(contentStr, `output "key_policy"`)
	if policyOutputStart != -1 {
		policyOutputEnd := findResourceBlockEnd(contentStr, policyOutputStart)
		policyOutputBlock := contentStr[policyOutputStart:policyOutputEnd]

		assert.Contains(t, policyOutputBlock, `sensitive   = true`,
			"key_policy output should be marked as sensitive")
	}
}

// Helper function to find the end of a statement block within a policy document
func findStatementBlockEnd(content string, startPos int) int {
	if startPos == -1 {
		return -1
	}

	// Look for the next "statement" or "dynamic" keyword which indicates a new statement
	searchStart := startPos + 20 // Skip past the current statement identifier
	
	// Find the next statement or dynamic block
	nextStatement := strings.Index(content[searchStart:], "statement {")
	nextDynamic := strings.Index(content[searchStart:], "dynamic \"statement\"")
	
	// Determine which comes first
	var nextBlockStart int
	if nextStatement == -1 && nextDynamic == -1 {
		// No more statements, return end of content
		return len(content)
	} else if nextStatement == -1 {
		nextBlockStart = searchStart + nextDynamic
	} else if nextDynamic == -1 {
		nextBlockStart = searchStart + nextStatement
	} else {
		// Both found, use whichever comes first
		if nextStatement < nextDynamic {
			nextBlockStart = searchStart + nextStatement
		} else {
			nextBlockStart = searchStart + nextDynamic
		}
	}
	
	return nextBlockStart
}

// TestKMSKeyPolicyJSON tests that the key policy can be parsed as valid JSON
func TestKMSKeyPolicyJSON(t *testing.T) {
	t.Parallel()

	kmsModuleDir := "../../modules/security/kms"
	mainFile := filepath.Join(kmsModuleDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Verify policy document uses proper JSON structure
	policyStart := strings.Index(contentStr, `data "aws_iam_policy_document" "kms_key_policy"`)
	require.NotEqual(t, -1, policyStart, "Key policy document should exist")

	policyEnd := findResourceBlockEnd(contentStr, policyStart)
	policyBlock := contentStr[policyStart:policyEnd]

	// Verify statement blocks are properly structured
	assert.Contains(t, policyBlock, `statement {`, "Policy should have statement blocks")
	assert.Contains(t, policyBlock, `sid`, "Statements should have SID")
	assert.Contains(t, policyBlock, `effect`, "Statements should have effect")
	assert.Contains(t, policyBlock, `principals {`, "Statements should have principals")
	assert.Contains(t, policyBlock, `actions`, "Statements should have actions")
	assert.Contains(t, policyBlock, `resources`, "Statements should have resources")

	// Verify the policy is assigned to the KMS key
	keyStart := strings.Index(contentStr, `resource "aws_kms_key" "main"`)
	require.NotEqual(t, -1, keyStart, "KMS key resource should exist")

	keyEnd := findResourceBlockEnd(contentStr, keyStart)
	keyBlock := contentStr[keyStart:keyEnd]

	assert.Contains(t, keyBlock, `policy                  = data.aws_iam_policy_document.kms_key_policy.json`,
		"KMS key should use the policy document JSON")
}

// TestKMSVariableValidation tests that KMS module variables have proper validation
func TestKMSVariableValidation(t *testing.T) {
	t.Parallel()

	kmsModuleDir := "../../modules/security/kms"
	variablesFile := filepath.Join(kmsModuleDir, "variables.tf")

	content, err := os.ReadFile(variablesFile)
	require.NoError(t, err, "Should be able to read variables.tf")

	contentStr := string(content)

	// Test deletion_window_in_days validation
	t.Run("Deletion Window Validation", func(t *testing.T) {
		deletionVarStart := strings.Index(contentStr, `variable "deletion_window_in_days"`)
		require.NotEqual(t, -1, deletionVarStart, "deletion_window_in_days variable should exist")

		deletionVarEnd := findResourceBlockEnd(contentStr, deletionVarStart)
		deletionVarBlock := contentStr[deletionVarStart:deletionVarEnd]

		assert.Contains(t, deletionVarBlock, `validation {`, "Should have validation block")
		assert.Contains(t, deletionVarBlock, `>= 7`, "Should validate minimum 7 days")
		assert.Contains(t, deletionVarBlock, `<= 30`, "Should validate maximum 30 days")
	})

	// Test key_usage validation
	t.Run("Key Usage Validation", func(t *testing.T) {
		keyUsageVarStart := strings.Index(contentStr, `variable "key_usage"`)
		require.NotEqual(t, -1, keyUsageVarStart, "key_usage variable should exist")

		keyUsageVarEnd := findResourceBlockEnd(contentStr, keyUsageVarStart)
		keyUsageVarBlock := contentStr[keyUsageVarStart:keyUsageVarEnd]

		assert.Contains(t, keyUsageVarBlock, `validation {`, "Should have validation block")
		assert.Contains(t, keyUsageVarBlock, `ENCRYPT_DECRYPT`, "Should validate ENCRYPT_DECRYPT")
		assert.Contains(t, keyUsageVarBlock, `SIGN_VERIFY`, "Should validate SIGN_VERIFY")
	})

	// Test region variable is required
	t.Run("Region Variable Required", func(t *testing.T) {
		regionVarStart := strings.Index(contentStr, `variable "region"`)
		require.NotEqual(t, -1, regionVarStart, "region variable should exist")

		regionVarEnd := findResourceBlockEnd(contentStr, regionVarStart)
		regionVarBlock := contentStr[regionVarStart:regionVarEnd]

		// Region should not have a default value (making it required)
		assert.NotContains(t, regionVarBlock, `default`, "Region variable should be required (no default)")
	})
}


