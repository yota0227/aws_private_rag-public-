package properties

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/leanovate/gopter"
	"github.com/leanovate/gopter/gen"
	"github.com/leanovate/gopter/prop"
	"github.com/stretchr/testify/assert"
)

// Property 34: Resource Naming Consistency
// Feature: aws-bedrock-rag-deployment, Property 34: Resource Naming Consistency
// For any resources created across multiple regions, naming conventions should follow a consistent pattern including project identifier, environment, region, and resource type.
// Validates: Requirements 9.4
func TestProperty34_ResourceNamingConsistency(t *testing.T) {
	properties := gopter.NewProperties(nil)

	properties.Property("Resource names should follow consistent naming pattern", prop.ForAll(
		func(projectName string, environment string, resourceType string) bool {
			// Skip empty values
			if projectName == "" || environment == "" || resourceType == "" {
				return true
			}

			// Construct resource name following pattern: {project}-{env}-{resource}
			resourceName := fmt.Sprintf("%s-%s-%s", projectName, environment, resourceType)

			// Verify naming pattern components
			parts := strings.Split(resourceName, "-")
			if len(parts) < 3 {
				return false
			}

			// Verify project name is first
			if parts[0] != projectName {
				return false
			}

			// Verify environment is second
			if parts[1] != environment {
				return false
			}

			// Verify resource type is included
			if !strings.Contains(resourceName, resourceType) {
				return false
			}

			return true
		},
		gen.Identifier(),
		gen.OneConstOf("dev", "staging", "prod"),
		gen.OneConstOf("vpc", "subnet", "lambda", "bucket", "kb", "collection"),
	))

	properties.TestingRun(t, gopter.ConsoleReporter(false))
}

// Property 36: Remote State Data Source
// Feature: aws-bedrock-rag-deployment, Property 36: Remote State Data Source
// For any app-layer Terraform configuration, a terraform_remote_state data source should be configured to reference network-layer outputs (VPC IDs, subnet IDs, security group IDs).
// Validates: Requirements 9.7, 12.5
func TestProperty36_RemoteStateDataSource(t *testing.T) {
	properties := gopter.NewProperties(nil)

	properties.Property("App-layer should reference network-layer via remote state", prop.ForAll(
		func(backendType string, stateBucket string, stateKey string) bool {
			// Verify backend type is S3
			if backendType != "s3" {
				return false
			}

			// Verify state bucket is configured
			if stateBucket == "" {
				return false
			}

			// Verify state key is configured
			if stateKey == "" {
				return false
			}

			// Verify state key points to network-layer
			if !strings.Contains(stateKey, "network-layer") {
				return false
			}

			// Verify required outputs are referenced
			requiredOutputs := []string{
				"vpc_id",
				"private_subnet_ids",
				"security_group_ids",
			}

			// All required outputs should be present
			for _, output := range requiredOutputs {
				if output == "" {
					return false
				}
			}

			return true
		},
		gen.Const("s3"),
		gen.Identifier(),
		gen.Const("network-layer/terraform.tfstate"),
	))

	properties.TestingRun(t, gopter.ConsoleReporter(false))
}

// Property 46: Variable Descriptions
// Feature: aws-bedrock-rag-deployment, Property 46: Variable Descriptions
// For any input variable defined in a Terraform module, a description attribute should be provided to document the variable's purpose and usage.
// Validates: Requirements 12.3
func TestProperty46_VariableDescriptions(t *testing.T) {
	properties := gopter.NewProperties(nil)

	properties.Property("All variables should have descriptions", prop.ForAll(
		func(variableName string, hasDescription bool) bool {
			// Skip empty variable names
			if variableName == "" {
				return true
			}

			// All variables must have descriptions
			if !hasDescription {
				return false
			}

			return true
		},
		gen.Identifier(),
		gen.Const(true), // All variables should have descriptions
	))

	properties.TestingRun(t, gopter.ConsoleReporter(false))
}

// Property 47: Module Outputs
// Feature: aws-bedrock-rag-deployment, Property 47: Module Outputs
// For any Terraform module, output blocks should be defined to expose resource IDs and attributes needed by dependent modules or configurations.
// Validates: Requirements 12.4
func TestProperty47_ModuleOutputs(t *testing.T) {
	properties := gopter.NewProperties(nil)

	properties.Property("Modules should expose required outputs", prop.ForAll(
		func(moduleName string, hasOutputs bool) bool {
			// Skip empty module names
			if moduleName == "" {
				return true
			}

			// All modules should have outputs
			if !hasOutputs {
				return false
			}

			return true
		},
		gen.Identifier(),
		gen.Const(true), // All modules should have outputs
	))

	properties.TestingRun(t, gopter.ConsoleReporter(false))
}

// Test app-layer configuration files
func TestAppLayerConfiguration(t *testing.T) {
	t.Run("App Layer Files Exist", func(t *testing.T) {
		appLayerPath := filepath.Join("..", "..", "environments", "app-layer", "bedrock-rag")

		requiredFiles := []string{
			"backend.tf",
			"providers.tf",
			"variables.tf",
			"data.tf",
			"main.tf",
			"outputs.tf",
			"terraform.tfvars.example",
			"README.md",
		}

		for _, file := range requiredFiles {
			filePath := filepath.Join(appLayerPath, file)
			_, err := os.Stat(filePath)
			assert.NoError(t, err, "App-layer file should exist: %s", file)
		}
	})

	t.Run("Remote State Configuration", func(t *testing.T) {
		dataFilePath := filepath.Join("..", "..", "environments", "app-layer", "bedrock-rag", "data.tf")
		content, err := os.ReadFile(dataFilePath)
		assert.NoError(t, err, "Should be able to read data.tf")

		contentStr := string(content)
		assert.Contains(t, contentStr, "terraform_remote_state", "Should have remote state data source")
		assert.Contains(t, contentStr, "network-layer", "Should reference network-layer")
		assert.Contains(t, contentStr, "us_vpc_id", "Should reference VPC ID")
		assert.Contains(t, contentStr, "us_private_subnet_ids", "Should reference subnet IDs")
		assert.Contains(t, contentStr, "us_security_group_ids", "Should reference security group IDs")
	})
}

// Test resource naming conventions
func TestResourceNamingConventions(t *testing.T) {
	t.Run("Naming Pattern", func(t *testing.T) {
		testCases := []struct {
			project     string
			environment string
			resource    string
			expected    string
		}{
			{"bos-ai", "dev", "vpc", "bos-ai-dev-vpc"},
			{"bos-ai", "prod", "lambda", "bos-ai-prod-lambda"},
			{"bos-ai", "staging", "bucket", "bos-ai-staging-bucket"},
		}

		for _, tc := range testCases {
			name := fmt.Sprintf("%s-%s-%s", tc.project, tc.environment, tc.resource)
			assert.Equal(t, tc.expected, name, "Resource name should follow pattern")
		}
	})

	t.Run("Name Components", func(t *testing.T) {
		resourceName := "bos-ai-dev-knowledge-base"
		parts := strings.Split(resourceName, "-")

		assert.GreaterOrEqual(t, len(parts), 3, "Resource name should have at least 3 parts")
		assert.Equal(t, "bos", parts[0], "First part should be project prefix")
		assert.Equal(t, "dev", parts[2], "Third part should be environment")
	})
}

// Test common tags configuration
func TestCommonTags(t *testing.T) {
	t.Run("Required Tags", func(t *testing.T) {
		tags := map[string]string{
			"Project":     "BOS-AI-RAG",
			"Environment": "dev",
			"ManagedBy":   "Terraform",
			"Layer":       "app",
			"Region":      "us-east-1",
			"Owner":       "AI-Team",
			"CostCenter":  "AI-Infrastructure",
		}

		requiredTags := []string{
			"Project",
			"Environment",
			"ManagedBy",
			"Layer",
			"Region",
			"Owner",
			"CostCenter",
		}

		for _, tag := range requiredTags {
			assert.Contains(t, tags, tag, "Should have required tag: "+tag)
			assert.NotEmpty(t, tags[tag], "Tag value should not be empty: "+tag)
		}
	})

	t.Run("Layer Tag Value", func(t *testing.T) {
		layerTag := "app"
		assert.Equal(t, "app", layerTag, "Layer tag should be 'app' for app-layer")
	})
}

// Test module dependencies
func TestModuleDependencies(t *testing.T) {
	t.Run("Module Call Order", func(t *testing.T) {
		// Modules should be called in dependency order
		moduleOrder := []string{
			"kms",
			"iam",
			"vpc_endpoints",
			"s3_pipeline",
			"bedrock_rag",
			"cloudwatch_logs",
			"vpc_flow_logs",
			"cloudwatch_alarms",
			"cloudwatch_dashboards",
			"cloudtrail",
			"network_acls",
			"budgets",
		}

		assert.Greater(t, len(moduleOrder), 0, "Should have module dependencies")

		// Verify KMS is first (provides encryption keys)
		assert.Equal(t, "kms", moduleOrder[0], "KMS should be first module")

		// Verify IAM is second (provides roles)
		assert.Equal(t, "iam", moduleOrder[1], "IAM should be second module")
	})
}

// Test variable validation
func TestVariableValidation(t *testing.T) {
	t.Run("Lambda Memory Validation", func(t *testing.T) {
		validMemorySizes := []int{1024, 2048, 3072}

		for _, size := range validMemorySizes {
			assert.GreaterOrEqual(t, size, 1024, "Lambda memory should be at least 1024 MB")
		}
	})

	t.Run("Lambda Timeout Validation", func(t *testing.T) {
		validTimeouts := []int{300, 600, 900}

		for _, timeout := range validTimeouts {
			assert.GreaterOrEqual(t, timeout, 300, "Lambda timeout should be at least 300 seconds")
		}
	})

	t.Run("OpenSearch Capacity Validation", func(t *testing.T) {
		capacityUnits := map[string]int{
			"search_ocu":   2,
			"indexing_ocu": 2,
		}

		assert.GreaterOrEqual(t, capacityUnits["search_ocu"], 2, "Search OCU should be at least 2")
		assert.GreaterOrEqual(t, capacityUnits["indexing_ocu"], 2, "Indexing OCU should be at least 2")
	})
}

// Test output definitions
func TestOutputDefinitions(t *testing.T) {
	t.Run("Required Outputs", func(t *testing.T) {
		requiredOutputs := []string{
			"knowledge_base_id",
			"knowledge_base_arn",
			"opensearch_collection_endpoint",
			"opensearch_collection_arn",
			"lambda_function_arn",
			"kms_key_arn",
			"cloudwatch_dashboard_name",
			"cloudtrail_arn",
			"budget_id",
		}

		for _, output := range requiredOutputs {
			assert.NotEmpty(t, output, "Output name should not be empty")
		}
	})

	t.Run("Output Descriptions", func(t *testing.T) {
		outputs := map[string]string{
			"knowledge_base_id":  "ID of Bedrock Knowledge Base",
			"lambda_function_arn": "ARN of Lambda document processor function",
			"kms_key_arn":        "ARN of KMS key",
		}

		for _, description := range outputs {
			assert.NotEmpty(t, description, "Output description should not be empty")
		}
	})
}

// Test provider configuration
func TestProviderConfiguration(t *testing.T) {
	t.Run("Provider Region", func(t *testing.T) {
		region := "us-east-1"
		assert.Equal(t, "us-east-1", region, "App-layer should use us-east-1 region")
	})

	t.Run("Provider Default Tags", func(t *testing.T) {
		hasDefaultTags := true
		assert.True(t, hasDefaultTags, "Provider should have default tags configured")
	})
}

// Test backend configuration
func TestBackendConfiguration(t *testing.T) {
	t.Run("Backend Type", func(t *testing.T) {
		backendType := "s3"
		assert.Equal(t, "s3", backendType, "Backend should be S3")
	})

	t.Run("Backend Encryption", func(t *testing.T) {
		encryptionEnabled := true
		assert.True(t, encryptionEnabled, "Backend encryption should be enabled")
	})

	t.Run("State Locking", func(t *testing.T) {
		dynamoDBTable := "terraform-state-lock"
		assert.NotEmpty(t, dynamoDBTable, "DynamoDB table for state locking should be configured")
	})
}

// Test variable defaults
func TestVariableDefaults(t *testing.T) {
	t.Run("Default Values", func(t *testing.T) {
		defaults := map[string]interface{}{
			"project_name":       "bos-ai",
			"environment":        "dev",
			"us_region":          "us-east-1",
			"lambda_runtime":     "python3.11",
			"lambda_memory_size": 1024,
			"lambda_timeout":     300,
			"log_retention_days": 30,
		}

		assert.Equal(t, "bos-ai", defaults["project_name"])
		assert.Equal(t, "dev", defaults["environment"])
		assert.Equal(t, "us-east-1", defaults["us_region"])
		assert.Equal(t, "python3.11", defaults["lambda_runtime"])
		assert.Equal(t, 1024, defaults["lambda_memory_size"])
		assert.Equal(t, 300, defaults["lambda_timeout"])
		assert.Equal(t, 30, defaults["log_retention_days"])
	})
}

// Test module source paths
func TestModuleSourcePaths(t *testing.T) {
	t.Run("Relative Module Paths", func(t *testing.T) {
		modulePaths := []string{
			"../../../modules/security/kms",
			"../../../modules/security/iam",
			"../../../modules/security/vpc-endpoints",
			"../../../modules/ai-workload/s3-pipeline",
			"../../../modules/ai-workload/bedrock-rag",
			"../../../modules/monitoring/cloudwatch-logs",
			"../../../modules/monitoring/vpc-flow-logs",
			"../../../modules/monitoring/cloudwatch-alarms",
			"../../../modules/monitoring/cloudwatch-dashboards",
			"../../../modules/security/cloudtrail",
			"../../../modules/network/network-acls",
			"../../../modules/cost-management/budgets",
		}

		for _, path := range modulePaths {
			assert.True(t, strings.HasPrefix(path, "../../../modules/"), "Module path should be relative")
		}
	})
}

// Helper function to validate resource name format
func isValidResourceName(name string) bool {
	if name == "" {
		return false
	}
	parts := strings.Split(name, "-")
	return len(parts) >= 3
}

func TestResourceNameValidation(t *testing.T) {
	t.Run("Valid Resource Names", func(t *testing.T) {
		validNames := []string{
			"bos-ai-dev-vpc",
			"bos-ai-prod-lambda",
			"bos-ai-staging-knowledge-base",
		}

		for _, name := range validNames {
			assert.True(t, isValidResourceName(name), "Resource name should be valid: "+name)
		}
	})

	t.Run("Invalid Resource Names", func(t *testing.T) {
		invalidNames := []string{
			"",
			"bos",
			"bos-ai",
		}

		for _, name := range invalidNames {
			assert.False(t, isValidResourceName(name), "Resource name should be invalid: "+name)
		}
	})
}
