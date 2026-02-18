package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 20: VPC Endpoints for PrivateLink
// Feature: aws-bedrock-rag-deployment, Property 20: VPC Endpoints for PrivateLink
// Validates: Requirements 5.7
//
// For any deployment in the US region, VPC endpoints should be created for Bedrock, S3,
// and OpenSearch Serverless services to enable PrivateLink connectivity.
func TestProperty20_VPCEndpointsForPrivateLink(t *testing.T) {
	t.Parallel()

	vpcEndpointsModuleDir := "../../modules/security/vpc-endpoints"
	mainFile := filepath.Join(vpcEndpointsModuleDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Test Bedrock Runtime VPC Endpoint
	t.Run("Bedrock Runtime Endpoint", func(t *testing.T) {
		// Verify Bedrock Runtime endpoint resource is defined
		assert.Contains(t, contentStr, `resource "aws_vpc_endpoint" "bedrock_runtime"`,
			"Should define Bedrock Runtime VPC endpoint")

		// Extract Bedrock Runtime endpoint block
		bedrockStart := strings.Index(contentStr, `resource "aws_vpc_endpoint" "bedrock_runtime"`)
		require.NotEqual(t, -1, bedrockStart, "Bedrock Runtime endpoint should exist")

		bedrockEnd := findResourceBlockEnd(contentStr, bedrockStart)
		bedrockBlock := contentStr[bedrockStart:bedrockEnd]

		// Verify service name
		assert.Contains(t, bedrockBlock, `com.amazonaws.${var.region}.bedrock-runtime`,
			"Should use correct Bedrock Runtime service name")

		// Verify endpoint type is Interface
		assert.Contains(t, bedrockBlock, `vpc_endpoint_type   = "Interface"`,
			"Bedrock Runtime endpoint should be Interface type")

		// Verify private DNS is enabled
		assert.Contains(t, bedrockBlock, `private_dns_enabled = true`,
			"Bedrock Runtime endpoint should have private DNS enabled")

		// Verify subnet and security group configuration
		assert.Contains(t, bedrockBlock, `subnet_ids`,
			"Bedrock Runtime endpoint should have subnet configuration")
		assert.Contains(t, bedrockBlock, `security_group_ids`,
			"Bedrock Runtime endpoint should have security group configuration")
	})

	// Test Bedrock Agent Runtime VPC Endpoint
	t.Run("Bedrock Agent Runtime Endpoint", func(t *testing.T) {
		// Verify Bedrock Agent Runtime endpoint resource is defined
		assert.Contains(t, contentStr, `resource "aws_vpc_endpoint" "bedrock_agent_runtime"`,
			"Should define Bedrock Agent Runtime VPC endpoint")

		// Extract Bedrock Agent Runtime endpoint block
		agentStart := strings.Index(contentStr, `resource "aws_vpc_endpoint" "bedrock_agent_runtime"`)
		require.NotEqual(t, -1, agentStart, "Bedrock Agent Runtime endpoint should exist")

		agentEnd := findResourceBlockEnd(contentStr, agentStart)
		agentBlock := contentStr[agentStart:agentEnd]

		// Verify service name
		assert.Contains(t, agentBlock, `com.amazonaws.${var.region}.bedrock-agent-runtime`,
			"Should use correct Bedrock Agent Runtime service name")

		// Verify endpoint type is Interface
		assert.Contains(t, agentBlock, `vpc_endpoint_type   = "Interface"`,
			"Bedrock Agent Runtime endpoint should be Interface type")

		// Verify private DNS is enabled
		assert.Contains(t, agentBlock, `private_dns_enabled = true`,
			"Bedrock Agent Runtime endpoint should have private DNS enabled")
	})

	// Test S3 Gateway Endpoint
	t.Run("S3 Gateway Endpoint", func(t *testing.T) {
		// Verify S3 endpoint resource is defined
		assert.Contains(t, contentStr, `resource "aws_vpc_endpoint" "s3"`,
			"Should define S3 VPC endpoint")

		// Extract S3 endpoint block
		s3Start := strings.Index(contentStr, `resource "aws_vpc_endpoint" "s3"`)
		require.NotEqual(t, -1, s3Start, "S3 endpoint should exist")

		s3End := findResourceBlockEnd(contentStr, s3Start)
		s3Block := contentStr[s3Start:s3End]

		// Verify service name
		assert.Contains(t, s3Block, `com.amazonaws.${var.region}.s3`,
			"Should use correct S3 service name")

		// Verify endpoint type is Gateway
		assert.Contains(t, s3Block, `vpc_endpoint_type = "Gateway"`,
			"S3 endpoint should be Gateway type")

		// Verify route table configuration
		assert.Contains(t, s3Block, `route_table_ids`,
			"S3 endpoint should have route table configuration")
	})

	// Test OpenSearch Serverless VPC Endpoint
	t.Run("OpenSearch Serverless Endpoint", func(t *testing.T) {
		// Verify OpenSearch endpoint resource is defined
		assert.Contains(t, contentStr, `resource "aws_vpc_endpoint" "opensearch"`,
			"Should define OpenSearch Serverless VPC endpoint")

		// Extract OpenSearch endpoint block
		ossStart := strings.Index(contentStr, `resource "aws_vpc_endpoint" "opensearch"`)
		require.NotEqual(t, -1, ossStart, "OpenSearch endpoint should exist")

		ossEnd := findResourceBlockEnd(contentStr, ossStart)
		ossBlock := contentStr[ossStart:ossEnd]

		// Verify service name (aoss = Amazon OpenSearch Serverless)
		assert.Contains(t, ossBlock, `com.amazonaws.${var.region}.aoss`,
			"Should use correct OpenSearch Serverless service name")

		// Verify endpoint type is Interface
		assert.Contains(t, ossBlock, `vpc_endpoint_type   = "Interface"`,
			"OpenSearch endpoint should be Interface type")

		// Verify private DNS is enabled
		assert.Contains(t, ossBlock, `private_dns_enabled = true`,
			"OpenSearch endpoint should have private DNS enabled")
	})

	// Test that endpoints are configurable
	t.Run("Endpoint Configuration", func(t *testing.T) {
		variablesFile := filepath.Join(vpcEndpointsModuleDir, "variables.tf")
		varContent, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		varStr := string(varContent)

		// Verify enable flags exist
		assert.Contains(t, varStr, `variable "enable_bedrock_runtime_endpoint"`,
			"Should have enable_bedrock_runtime_endpoint variable")
		assert.Contains(t, varStr, `variable "enable_bedrock_agent_runtime_endpoint"`,
			"Should have enable_bedrock_agent_runtime_endpoint variable")
		assert.Contains(t, varStr, `variable "enable_s3_endpoint"`,
			"Should have enable_s3_endpoint variable")
		assert.Contains(t, varStr, `variable "enable_opensearch_endpoint"`,
			"Should have enable_opensearch_endpoint variable")

		// Verify default values are true
		endpoints := []string{
			"enable_bedrock_runtime_endpoint",
			"enable_bedrock_agent_runtime_endpoint",
			"enable_s3_endpoint",
			"enable_opensearch_endpoint",
		}

		for _, endpoint := range endpoints {
			varStart := strings.Index(varStr, `variable "`+endpoint+`"`)
			if varStart != -1 {
				varEnd := findResourceBlockEnd(varStr, varStart)
				varBlock := varStr[varStart:varEnd]
				assert.Contains(t, varBlock, `default     = true`,
					"%s should be enabled by default", endpoint)
			}
		}
	})
}

// Property 21: VPC Endpoint Policy Configuration
// Feature: aws-bedrock-rag-deployment, Property 21: VPC Endpoint Policy Configuration
// Validates: Requirements 5.8
//
// For any VPC endpoint created by the module, an endpoint policy should be configured
// to restrict access to specific resources or actions.
func TestProperty21_VPCEndpointPolicyConfiguration(t *testing.T) {
	t.Parallel()

	vpcEndpointsModuleDir := "../../modules/security/vpc-endpoints"
	mainFile := filepath.Join(vpcEndpointsModuleDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Test Bedrock Runtime Endpoint Policy
	t.Run("Bedrock Runtime Endpoint Policy", func(t *testing.T) {
		// Verify endpoint policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "bedrock_runtime_endpoint_policy"`,
			"Should define Bedrock Runtime endpoint policy document")

		// Extract policy block
		policyStart := strings.Index(contentStr, `data "aws_iam_policy_document" "bedrock_runtime_endpoint_policy"`)
		require.NotEqual(t, -1, policyStart, "Bedrock Runtime endpoint policy should exist")

		policyEnd := findResourceBlockEnd(contentStr, policyStart)
		policyBlock := contentStr[policyStart:policyEnd]

		// Verify policy has statements
		assert.Contains(t, policyBlock, `statement {`,
			"Endpoint policy should have statements")

		// Verify policy restricts actions
		assert.Contains(t, policyBlock, `actions`,
			"Endpoint policy should specify allowed actions")
		assert.Contains(t, policyBlock, `bedrock:InvokeModel`,
			"Endpoint policy should allow InvokeModel action")

		// Verify policy restricts resources
		assert.Contains(t, policyBlock, `resources`,
			"Endpoint policy should specify allowed resources")

		// Verify policy has condition for account restriction
		assert.Contains(t, policyBlock, `condition {`,
			"Endpoint policy should have conditions")
		assert.Contains(t, policyBlock, `aws:PrincipalAccount`,
			"Endpoint policy should restrict by account")

		// Verify policy is attached to endpoint
		endpointStart := strings.Index(contentStr, `resource "aws_vpc_endpoint" "bedrock_runtime"`)
		endpointEnd := findResourceBlockEnd(contentStr, endpointStart)
		endpointBlock := contentStr[endpointStart:endpointEnd]

		assert.Contains(t, endpointBlock, `policy = data.aws_iam_policy_document.bedrock_runtime_endpoint_policy`,
			"Endpoint should use the policy document")
	})

	// Test Bedrock Agent Runtime Endpoint Policy
	t.Run("Bedrock Agent Runtime Endpoint Policy", func(t *testing.T) {
		// Verify endpoint policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "bedrock_agent_runtime_endpoint_policy"`,
			"Should define Bedrock Agent Runtime endpoint policy document")

		// Extract policy block
		policyStart := strings.Index(contentStr, `data "aws_iam_policy_document" "bedrock_agent_runtime_endpoint_policy"`)
		require.NotEqual(t, -1, policyStart, "Bedrock Agent Runtime endpoint policy should exist")

		policyEnd := findResourceBlockEnd(contentStr, policyStart)
		policyBlock := contentStr[policyStart:policyEnd]

		// Verify policy restricts actions
		assert.Contains(t, policyBlock, `bedrock:Retrieve`,
			"Endpoint policy should allow Retrieve action")
		assert.Contains(t, policyBlock, `bedrock:RetrieveAndGenerate`,
			"Endpoint policy should allow RetrieveAndGenerate action")

		// Verify policy restricts resources to knowledge bases
		assert.Contains(t, policyBlock, `knowledge-base`,
			"Endpoint policy should restrict to knowledge bases")

		// Verify policy has account condition
		assert.Contains(t, policyBlock, `aws:PrincipalAccount`,
			"Endpoint policy should restrict by account")
	})

	// Test S3 Endpoint Policy
	t.Run("S3 Endpoint Policy", func(t *testing.T) {
		// Verify endpoint policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "s3_endpoint_policy"`,
			"Should define S3 endpoint policy document")

		// Extract policy block
		policyStart := strings.Index(contentStr, `data "aws_iam_policy_document" "s3_endpoint_policy"`)
		require.NotEqual(t, -1, policyStart, "S3 endpoint policy should exist")

		policyEnd := findResourceBlockEnd(contentStr, policyStart)
		policyBlock := contentStr[policyStart:policyEnd]

		// Verify policy restricts actions
		assert.Contains(t, policyBlock, `s3:GetObject`,
			"Endpoint policy should allow GetObject action")
		assert.Contains(t, policyBlock, `s3:PutObject`,
			"Endpoint policy should allow PutObject action")
		assert.Contains(t, policyBlock, `s3:ListBucket`,
			"Endpoint policy should allow ListBucket action")

		// Verify policy restricts resources to project buckets
		assert.Contains(t, policyBlock, `var.project_name`,
			"Endpoint policy should restrict to project buckets")

		// Verify policy has account condition
		assert.Contains(t, policyBlock, `aws:PrincipalAccount`,
			"Endpoint policy should restrict by account")
	})

	// Test OpenSearch Serverless Endpoint Policy
	t.Run("OpenSearch Serverless Endpoint Policy", func(t *testing.T) {
		// Verify endpoint policy document is defined
		assert.Contains(t, contentStr, `data "aws_iam_policy_document" "opensearch_endpoint_policy"`,
			"Should define OpenSearch Serverless endpoint policy document")

		// Extract policy block
		policyStart := strings.Index(contentStr, `data "aws_iam_policy_document" "opensearch_endpoint_policy"`)
		require.NotEqual(t, -1, policyStart, "OpenSearch endpoint policy should exist")

		policyEnd := findResourceBlockEnd(contentStr, policyStart)
		policyBlock := contentStr[policyStart:policyEnd]

		// Verify policy restricts actions
		assert.Contains(t, policyBlock, `aoss:APIAccessAll`,
			"Endpoint policy should allow OpenSearch Serverless API access")

		// Verify policy restricts resources to collections
		assert.Contains(t, policyBlock, `collection`,
			"Endpoint policy should restrict to collections")

		// Verify policy has account condition
		assert.Contains(t, policyBlock, `aws:PrincipalAccount`,
			"Endpoint policy should restrict by account")
	})

	// Test that all endpoint policies use least-privilege principle
	t.Run("Least Privilege Endpoint Policies", func(t *testing.T) {
		// Verify no wildcard-only policies
		assert.NotContains(t, contentStr, `"*:*"`,
			"Endpoint policies should not use wildcard service and action")

		// Verify all policies have resource restrictions
		policyDocs := []string{
			"bedrock_runtime_endpoint_policy",
			"bedrock_agent_runtime_endpoint_policy",
			"s3_endpoint_policy",
			"opensearch_endpoint_policy",
		}

		for _, policyName := range policyDocs {
			policyStart := strings.Index(contentStr, `data "aws_iam_policy_document" "`+policyName+`"`)
			if policyStart != -1 {
				policyEnd := findResourceBlockEnd(contentStr, policyStart)
				policyBlock := contentStr[policyStart:policyEnd]

				assert.Contains(t, policyBlock, `resources`,
					"Policy %s should have resource restrictions", policyName)
				assert.Contains(t, policyBlock, `condition {`,
					"Policy %s should have conditions", policyName)
			}
		}
	})
}

// TestVPCEndpointsModuleOutputs tests that VPC Endpoints module exposes required outputs
// Validates: Requirements 12.4
func TestVPCEndpointsModuleOutputs(t *testing.T) {
	t.Parallel()

	vpcEndpointsModuleDir := "../../modules/security/vpc-endpoints"
	outputsFile := filepath.Join(vpcEndpointsModuleDir, "outputs.tf")

	content, err := os.ReadFile(outputsFile)
	require.NoError(t, err, "Should be able to read outputs.tf")

	contentStr := string(content)

	// Verify required outputs for each endpoint
	requiredOutputs := []struct {
		name        string
		description string
	}{
		{"bedrock_runtime_endpoint_id", "ID of the Bedrock Runtime VPC endpoint"},
		{"bedrock_agent_runtime_endpoint_id", "ID of the Bedrock Agent Runtime VPC endpoint"},
		{"s3_endpoint_id", "ID of the S3 Gateway VPC endpoint"},
		{"opensearch_endpoint_id", "ID of the OpenSearch Serverless VPC endpoint"},
		{"all_endpoint_ids", "Map of all VPC endpoint IDs"},
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

	// Verify DNS entries outputs for interface endpoints
	dnsOutputs := []string{
		"bedrock_runtime_endpoint_dns_entries",
		"bedrock_agent_runtime_endpoint_dns_entries",
		"opensearch_endpoint_dns_entries",
	}

	for _, output := range dnsOutputs {
		assert.Contains(t, contentStr, `output "`+output+`"`,
			"Should define %s output", output)
	}
}

// TestVPCEndpointsVariableDescriptions tests that all VPC Endpoints variables have descriptions
// Validates: Requirements 12.3
func TestVPCEndpointsVariableDescriptions(t *testing.T) {
	t.Parallel()

	vpcEndpointsModuleDir := "../../modules/security/vpc-endpoints"
	variablesFile := filepath.Join(vpcEndpointsModuleDir, "variables.tf")

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
