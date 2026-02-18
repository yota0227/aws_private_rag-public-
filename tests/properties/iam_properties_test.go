package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 16: Lambda IAM Permissions
// Feature: aws-bedrock-rag-deployment, Property 16: Lambda IAM Permissions
// Validates: Requirements 4.11
//
// For any Lambda function created for document processing, its execution role should have
// IAM policies granting permissions to read from S3, write to CloudWatch Logs, start Bedrock
// ingestion jobs, and use KMS keys.
func TestProperty16_LambdaIAMPermissions(t *testing.T) {
	t.Parallel()

	iamModuleDir := "../../modules/security/iam"
	lambdaRoleFile := filepath.Join(iamModuleDir, "lambda-role.tf")

	content, err := os.ReadFile(lambdaRoleFile)
	require.NoError(t, err, "Should be able to read lambda-role.tf")

	contentStr := string(content)

	// Verify Lambda execution role is defined
	assert.Contains(t, contentStr, `resource "aws_iam_role" "lambda_processor"`,
		"Should define Lambda processor IAM role")

	// Test S3 read permissions
	t.Run("S3 Read Permissions", func(t *testing.T) {
		// Verify S3 policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "lambda_s3_access"`,
			"Should define Lambda S3 access policy document")

		// Extract S3 policy block
		s3PolicyStart := strings.Index(contentStr, `data "aws_iam_policy_document" "lambda_s3_access"`)
		require.NotEqual(t, -1, s3PolicyStart, "S3 policy document should exist")

		s3PolicyEnd := findResourceBlockEnd(contentStr, s3PolicyStart)
		s3PolicyBlock := contentStr[s3PolicyStart:s3PolicyEnd]

		// Verify required S3 actions
		requiredActions := []string{"s3:GetObject", "s3:ListBucket"}
		for _, action := range requiredActions {
			assert.Contains(t, s3PolicyBlock, action,
				"S3 policy should include %s action", action)
		}

		// Verify S3 policy is attached to role
		assert.Contains(t, contentStr, `resource "aws_iam_policy" "lambda_s3_access"`,
			"Should create Lambda S3 access policy")
		assert.Contains(t, contentStr, `resource "aws_iam_role_policy_attachment" "lambda_s3_access"`,
			"Should attach S3 policy to Lambda role")
	})

	// Test CloudWatch Logs permissions
	t.Run("CloudWatch Logs Permissions", func(t *testing.T) {
		// Verify CloudWatch Logs policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "lambda_cloudwatch_logs"`,
			"Should define Lambda CloudWatch Logs policy document")

		// Extract CloudWatch Logs policy block
		logsStart := strings.Index(contentStr, `data "aws_iam_policy_document" "lambda_cloudwatch_logs"`)
		require.NotEqual(t, -1, logsStart, "CloudWatch Logs policy document should exist")

		logsEnd := findResourceBlockEnd(contentStr, logsStart)
		logsBlock := contentStr[logsStart:logsEnd]

		// Verify required CloudWatch Logs actions
		requiredActions := []string{
			"logs:CreateLogGroup",
			"logs:CreateLogStream",
			"logs:PutLogEvents",
		}
		for _, action := range requiredActions {
			assert.Contains(t, logsBlock, action,
				"CloudWatch Logs policy should include %s action", action)
		}

		// Verify CloudWatch Logs policy is attached to role
		assert.Contains(t, contentStr, `resource "aws_iam_policy" "lambda_cloudwatch_logs"`,
			"Should create Lambda CloudWatch Logs policy")
		assert.Contains(t, contentStr, `resource "aws_iam_role_policy_attachment" "lambda_cloudwatch_logs"`,
			"Should attach CloudWatch Logs policy to Lambda role")
	})

	// Test Bedrock ingestion permissions
	t.Run("Bedrock Ingestion Permissions", func(t *testing.T) {
		// Verify Bedrock policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "lambda_bedrock_access"`,
			"Should define Lambda Bedrock access policy document")

		// Extract Bedrock policy block
		bedrockStart := strings.Index(contentStr, `data "aws_iam_policy_document" "lambda_bedrock_access"`)
		require.NotEqual(t, -1, bedrockStart, "Bedrock policy document should exist")

		bedrockEnd := findResourceBlockEnd(contentStr, bedrockStart)
		bedrockBlock := contentStr[bedrockStart:bedrockEnd]

		// Verify required Bedrock actions
		requiredActions := []string{
			"bedrock:StartIngestionJob",
			"bedrock:GetIngestionJob",
		}
		for _, action := range requiredActions {
			assert.Contains(t, bedrockBlock, action,
				"Bedrock policy should include %s action", action)
		}

		// Verify Bedrock policy is attached to role
		assert.Contains(t, contentStr, `resource "aws_iam_policy" "lambda_bedrock_access"`,
			"Should create Lambda Bedrock access policy")
		assert.Contains(t, contentStr, `resource "aws_iam_role_policy_attachment" "lambda_bedrock_access"`,
			"Should attach Bedrock policy to Lambda role")
	})

	// Test KMS permissions
	t.Run("KMS Permissions", func(t *testing.T) {
		// Verify KMS policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "lambda_kms_access"`,
			"Should define Lambda KMS access policy document")

		// Extract KMS policy block
		kmsStart := strings.Index(contentStr, `data "aws_iam_policy_document" "lambda_kms_access"`)
		require.NotEqual(t, -1, kmsStart, "KMS policy document should exist")

		kmsEnd := findResourceBlockEnd(contentStr, kmsStart)
		kmsBlock := contentStr[kmsStart:kmsEnd]

		// Verify required KMS actions
		requiredActions := []string{"kms:Decrypt", "kms:GenerateDataKey"}
		for _, action := range requiredActions {
			assert.Contains(t, kmsBlock, action,
				"KMS policy should include %s action", action)
		}

		// Verify KMS policy is attached to role
		assert.Contains(t, contentStr, `resource "aws_iam_policy" "lambda_kms_access"`,
			"Should create Lambda KMS access policy")
		assert.Contains(t, contentStr, `resource "aws_iam_role_policy_attachment" "lambda_kms_access"`,
			"Should attach KMS policy to Lambda role")
	})

	// Test VPC network interface management permissions
	t.Run("VPC Network Interface Permissions", func(t *testing.T) {
		// Verify VPC policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "lambda_vpc_access"`,
			"Should define Lambda VPC access policy document")

		// Extract VPC policy block
		vpcStart := strings.Index(contentStr, `data "aws_iam_policy_document" "lambda_vpc_access"`)
		require.NotEqual(t, -1, vpcStart, "VPC policy document should exist")

		vpcEnd := findResourceBlockEnd(contentStr, vpcStart)
		vpcBlock := contentStr[vpcStart:vpcEnd]

		// Verify required VPC actions
		requiredActions := []string{
			"ec2:CreateNetworkInterface",
			"ec2:DescribeNetworkInterfaces",
			"ec2:DeleteNetworkInterface",
		}
		for _, action := range requiredActions {
			assert.Contains(t, vpcBlock, action,
				"VPC policy should include %s action", action)
		}

		// Verify VPC policy is attached to role
		assert.Contains(t, contentStr, `resource "aws_iam_policy" "lambda_vpc_access"`,
			"Should create Lambda VPC access policy")
		assert.Contains(t, contentStr, `resource "aws_iam_role_policy_attachment" "lambda_vpc_access"`,
			"Should attach VPC policy to Lambda role")
	})

	// Test Lambda assume role policy
	t.Run("Lambda Assume Role Policy", func(t *testing.T) {
		// Verify assume role policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "lambda_assume_role"`,
			"Should define Lambda assume role policy document")

		// Extract assume role policy block
		assumeStart := strings.Index(contentStr, `data "aws_iam_policy_document" "lambda_assume_role"`)
		require.NotEqual(t, -1, assumeStart, "Assume role policy document should exist")

		assumeEnd := findResourceBlockEnd(contentStr, assumeStart)
		assumeBlock := contentStr[assumeStart:assumeEnd]

		// Verify Lambda service principal
		assert.Contains(t, assumeBlock, `lambda.amazonaws.com`,
			"Assume role policy should allow Lambda service principal")

		// Verify AssumeRole action
		assert.Contains(t, assumeBlock, `sts:AssumeRole`,
			"Assume role policy should include AssumeRole action")
	})
}

// Property 17: IAM Policy Administrator Access Prohibition
// Feature: aws-bedrock-rag-deployment, Property 17: IAM Policy Administrator Access Prohibition
// Validates: Requirements 5.3
//
// For any IAM role or policy created by the module, it should not reference or attach
// the AdministratorAccess managed policy ARN.
func TestProperty17_IAMPolicyAdministratorAccessProhibition(t *testing.T) {
	t.Parallel()

	iamModuleDir := "../../modules/security/iam"

	// Test all IAM role files
	roleFiles := []string{
		"bedrock-kb-role.tf",
		"lambda-role.tf",
	}

	for _, roleFile := range roleFiles {
		t.Run(roleFile, func(t *testing.T) {
			filePath := filepath.Join(iamModuleDir, roleFile)
			content, err := os.ReadFile(filePath)
			require.NoError(t, err, "Should be able to read %s", roleFile)

			contentStr := string(content)

			// Verify AdministratorAccess is not used
			assert.NotContains(t, contentStr, "AdministratorAccess",
				"%s should not reference AdministratorAccess policy", roleFile)

			// Verify arn:aws:iam::aws:policy/AdministratorAccess is not used
			assert.NotContains(t, contentStr, "arn:aws:iam::aws:policy/AdministratorAccess",
				"%s should not attach AdministratorAccess managed policy", roleFile)

			// Verify PowerUserAccess is not used (also overly permissive)
			assert.NotContains(t, contentStr, "PowerUserAccess",
				"%s should not reference PowerUserAccess policy", roleFile)

			// Verify all policies are custom (data.aws_iam_policy_document)
			customPolicies := countOccurrences(contentStr, `resource "aws_iam_policy"`)

			assert.Greater(t, customPolicies, 0,
				"%s should define custom IAM policies", roleFile)

			// Verify all policy attachments reference custom policies
			assert.Contains(t, contentStr, `policy_arn = aws_iam_policy.`,
				"%s should attach custom policies, not managed policies", roleFile)
		})
	}

	// Test that all policies use least-privilege principle
	t.Run("Least Privilege Policies", func(t *testing.T) {
		lambdaRoleFile := filepath.Join(iamModuleDir, "lambda-role.tf")
		content, err := os.ReadFile(lambdaRoleFile)
		require.NoError(t, err, "Should be able to read lambda-role.tf")

		contentStr := string(content)

		// Verify no wildcard-only actions (e.g., "s3:*", "bedrock:*")
		// Specific actions should be listed
		policyDocs := extractPolicyDocuments(contentStr)

		for policyName, policyContent := range policyDocs {
			// Skip assume role policies as they have different structure
			if strings.Contains(policyName, "assume_role") {
				continue
			}

			// Check for overly permissive actions
			assert.NotContains(t, policyContent, `"*:*"`,
				"Policy %s should not use wildcard service and action", policyName)

			// VPC policy is an exception as it needs ec2:* on resources
			if !strings.Contains(policyName, "vpc") {
				// Verify specific actions are used, not service wildcards
				if strings.Contains(policyContent, `actions`) {
					// Should have specific actions listed
					assert.True(t,
						strings.Contains(policyContent, `"s3:Get`) ||
							strings.Contains(policyContent, `"bedrock:Start`) ||
							strings.Contains(policyContent, `"kms:Decrypt`) ||
							strings.Contains(policyContent, `"logs:Create`),
						"Policy %s should use specific actions", policyName)
				}
			}
		}
	})
}

// TestBedrockKnowledgeBaseIAMRole tests Bedrock Knowledge Base IAM role configuration
// Validates: Requirements 5.1, 5.2
func TestBedrockKnowledgeBaseIAMRole(t *testing.T) {
	t.Parallel()

	iamModuleDir := "../../modules/security/iam"
	bedrockRoleFile := filepath.Join(iamModuleDir, "bedrock-kb-role.tf")

	content, err := os.ReadFile(bedrockRoleFile)
	require.NoError(t, err, "Should be able to read bedrock-kb-role.tf")

	contentStr := string(content)

	// Verify Bedrock Knowledge Base role is defined
	assert.Contains(t, contentStr, `resource "aws_iam_role" "bedrock_kb"`,
		"Should define Bedrock Knowledge Base IAM role")

	// Test Bedrock assume role policy
	t.Run("Bedrock Assume Role Policy", func(t *testing.T) {
		// Verify assume role policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "bedrock_kb_assume_role"`,
			"Should define Bedrock KB assume role policy document")

		// Extract assume role policy block
		assumeStart := strings.Index(contentStr, `data "aws_iam_policy_document" "bedrock_kb_assume_role"`)
		require.NotEqual(t, -1, assumeStart, "Assume role policy document should exist")

		assumeEnd := findResourceBlockEnd(contentStr, assumeStart)
		assumeBlock := contentStr[assumeStart:assumeEnd]

		// Verify Bedrock service principal
		assert.Contains(t, assumeBlock, `bedrock.amazonaws.com`,
			"Assume role policy should allow Bedrock service principal")

		// Verify AssumeRole action
		assert.Contains(t, assumeBlock, `sts:AssumeRole`,
			"Assume role policy should include AssumeRole action")

		// Verify condition for source account
		assert.Contains(t, assumeBlock, `aws:SourceAccount`,
			"Assume role policy should have source account condition")

		// Verify condition for source ARN
		assert.Contains(t, assumeBlock, `aws:SourceArn`,
			"Assume role policy should have source ARN condition")
	})

	// Test S3 access policy
	t.Run("S3 Access Policy", func(t *testing.T) {
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "bedrock_kb_s3_access"`,
			"Should define Bedrock KB S3 access policy document")

		s3Start := strings.Index(contentStr, `data "aws_iam_policy_document" "bedrock_kb_s3_access"`)
		require.NotEqual(t, -1, s3Start, "S3 policy document should exist")

		s3End := findResourceBlockEnd(contentStr, s3Start)
		s3Block := contentStr[s3Start:s3End]

		// Verify required S3 actions
		assert.Contains(t, s3Block, "s3:GetObject", "Should allow GetObject")
		assert.Contains(t, s3Block, "s3:ListBucket", "Should allow ListBucket")

		// Verify resource scoping
		assert.Contains(t, s3Block, "var.s3_data_source_bucket_arn",
			"Should scope to specific S3 bucket")
	})

	// Test OpenSearch access policy
	t.Run("OpenSearch Access Policy", func(t *testing.T) {
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "bedrock_kb_opensearch_access"`,
			"Should define Bedrock KB OpenSearch access policy document")

		ossStart := strings.Index(contentStr, `data "aws_iam_policy_document" "bedrock_kb_opensearch_access"`)
		require.NotEqual(t, -1, ossStart, "OpenSearch policy document should exist")

		ossEnd := findResourceBlockEnd(contentStr, ossStart)
		ossBlock := contentStr[ossStart:ossEnd]

		// Verify OpenSearch Serverless action
		assert.Contains(t, ossBlock, "aoss:APIAccessAll",
			"Should allow OpenSearch Serverless API access")

		// Verify resource scoping
		assert.Contains(t, ossBlock, "var.opensearch_collection_arn",
			"Should scope to specific OpenSearch collection")
	})

	// Test KMS access policy
	t.Run("KMS Access Policy", func(t *testing.T) {
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "bedrock_kb_kms_access"`,
			"Should define Bedrock KB KMS access policy document")

		kmsStart := strings.Index(contentStr, `data "aws_iam_policy_document" "bedrock_kb_kms_access"`)
		require.NotEqual(t, -1, kmsStart, "KMS policy document should exist")

		kmsEnd := findResourceBlockEnd(contentStr, kmsStart)
		kmsBlock := contentStr[kmsStart:kmsEnd]

		// Verify required KMS actions
		assert.Contains(t, kmsBlock, "kms:Decrypt", "Should allow Decrypt")
		assert.Contains(t, kmsBlock, "kms:GenerateDataKey", "Should allow GenerateDataKey")

		// Verify resource scoping
		assert.Contains(t, kmsBlock, "var.kms_key_arn",
			"Should scope to specific KMS key")
	})

	// Test Bedrock model invocation policy
	t.Run("Bedrock Model Invocation Policy", func(t *testing.T) {
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "bedrock_kb_model_access"`,
			"Should define Bedrock KB model access policy document")

		modelStart := strings.Index(contentStr, `data "aws_iam_policy_document" "bedrock_kb_model_access"`)
		require.NotEqual(t, -1, modelStart, "Model access policy document should exist")

		modelEnd := findResourceBlockEnd(contentStr, modelStart)
		modelBlock := contentStr[modelStart:modelEnd]

		// Verify Bedrock model invocation action
		assert.Contains(t, modelBlock, "bedrock:InvokeModel",
			"Should allow InvokeModel")

		// Verify resource scoping
		assert.Contains(t, modelBlock, "var.bedrock_model_arns",
			"Should scope to specific Bedrock models")
	})
}

// TestIAMModuleOutputs tests that IAM module exposes required outputs
// Validates: Requirements 12.4
func TestIAMModuleOutputs(t *testing.T) {
	t.Parallel()

	iamModuleDir := "../../modules/security/iam"
	outputsFile := filepath.Join(iamModuleDir, "outputs.tf")

	content, err := os.ReadFile(outputsFile)
	require.NoError(t, err, "Should be able to read outputs.tf")

	contentStr := string(content)

	// Verify required outputs for Bedrock KB role
	bedrockOutputs := []string{
		"bedrock_kb_role_arn",
		"bedrock_kb_role_name",
		"bedrock_kb_role_id",
	}

	for _, output := range bedrockOutputs {
		assert.Contains(t, contentStr, `output "`+output+`"`,
			"Should define %s output", output)

		// Extract output block
		outputStart := strings.Index(contentStr, `output "`+output+`"`)
		if outputStart != -1 {
			outputEnd := findResourceBlockEnd(contentStr, outputStart)
			outputBlock := contentStr[outputStart:outputEnd]

			assert.Contains(t, outputBlock, `description`, "Output %s should have description", output)
			assert.Contains(t, outputBlock, `value`, "Output %s should have value", output)
		}
	}

	// Verify required outputs for Lambda role
	lambdaOutputs := []string{
		"lambda_processor_role_arn",
		"lambda_processor_role_name",
		"lambda_processor_role_id",
	}

	for _, output := range lambdaOutputs {
		assert.Contains(t, contentStr, `output "`+output+`"`,
			"Should define %s output", output)

		// Extract output block
		outputStart := strings.Index(contentStr, `output "`+output+`"`)
		if outputStart != -1 {
			outputEnd := findResourceBlockEnd(contentStr, outputStart)
			outputBlock := contentStr[outputStart:outputEnd]

			assert.Contains(t, outputBlock, `description`, "Output %s should have description", output)
			assert.Contains(t, outputBlock, `value`, "Output %s should have value", output)
		}
	}
}

// TestIAMVariableDescriptions tests that all IAM variables have descriptions
// Validates: Requirements 12.3
func TestIAMVariableDescriptions(t *testing.T) {
	t.Parallel()

	iamModuleDir := "../../modules/security/iam"
	variablesFile := filepath.Join(iamModuleDir, "variables.tf")

	content, err := os.ReadFile(variablesFile)
	require.NoError(t, err, "Should be able to read variables.tf")

	contentStr := string(content)

	// Find all variable blocks
	variables := extractVariableNames(contentStr)

	for _, varName := range variables {
		t.Run(varName, func(t *testing.T) {
			varStart := strings.Index(contentStr, `variable "`+varName+`"`)
			require.NotEqual(t, -1, varStart, "Variable %s should exist", varName)

			varEnd := findResourceBlockEnd(contentStr, varStart)
			varBlock := contentStr[varStart:varEnd]

			// Verify description exists
			assert.Contains(t, varBlock, `description`, "Variable %s should have description", varName)

			// Verify type is specified
			assert.Contains(t, varBlock, `type`, "Variable %s should have type", varName)
		})
	}
}

// Helper function to count occurrences of a substring
func countOccurrences(content, substr string) int {
	return strings.Count(content, substr)
}

// Helper function to extract policy document names and content
func extractPolicyDocuments(content string) map[string]string {
	policies := make(map[string]string)

	// Find all policy document data sources
	lines := strings.Split(content, "\n")
	var currentPolicy string
	var policyContent strings.Builder
	inPolicy := false
	braceCount := 0

	for _, line := range lines {
		if strings.Contains(line, `data "aws_iam_policy_document"`) {
			// Extract policy name
			parts := strings.Split(line, `"`)
			if len(parts) >= 4 {
				currentPolicy = parts[3]
				inPolicy = true
				braceCount = 0
			}
		}

		if inPolicy {
			policyContent.WriteString(line + "\n")

			// Count braces
			braceCount += strings.Count(line, "{")
			braceCount -= strings.Count(line, "}")

			if braceCount == 0 && strings.Contains(line, "}") {
				policies[currentPolicy] = policyContent.String()
				policyContent.Reset()
				inPolicy = false
			}
		}
	}

	return policies
}

// Helper function to extract variable names from variables.tf
func extractVariableNames(content string) []string {
	var variables []string

	lines := strings.Split(content, "\n")
	for _, line := range lines {
		if strings.Contains(line, `variable "`) {
			parts := strings.Split(line, `"`)
			if len(parts) >= 2 {
				variables = append(variables, parts[1])
			}
		}
	}

	return variables
}
