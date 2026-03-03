package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 15: Lambda Resource Constraints
// Feature: aws-bedrock-rag-deployment, Property 15: Lambda Resource Constraints
// Validates: Requirements 4.5, 4.6
//
// For any Lambda function created for document processing, the memory allocation should be
// at least 1024 MB and the timeout should be at least 300 seconds (5 minutes).
func TestProperty15_LambdaResourceConstraints(t *testing.T) {
	t.Parallel()

	s3PipelineDir := "../../modules/ai-workload/s3-pipeline"
	lambdaFile := filepath.Join(s3PipelineDir, "lambda.tf")
	variablesFile := filepath.Join(s3PipelineDir, "variables.tf")

	// Test Lambda function resource configuration
	t.Run("Lambda Function Resource Configuration", func(t *testing.T) {
		content, err := os.ReadFile(lambdaFile)
		require.NoError(t, err, "Should be able to read lambda.tf")

		contentStr := string(content)

		// Verify Lambda function is defined
		assert.Contains(t, contentStr, `resource "aws_lambda_function" "document_processor"`,
			"Should define Lambda document processor function")

		// Extract Lambda function block
		lambdaStart := strings.Index(contentStr, `resource "aws_lambda_function" "document_processor"`)
		require.NotEqual(t, -1, lambdaStart, "Lambda function should exist")

		lambdaEnd := findResourceBlockEnd(contentStr, lambdaStart)
		lambdaBlock := contentStr[lambdaStart:lambdaEnd]

		// Verify memory_size is configured
		assert.Contains(t, lambdaBlock, `memory_size = var.lambda_memory_size`,
			"Lambda should use configurable memory size")

		// Verify timeout is configured
		assert.Contains(t, lambdaBlock, `timeout     = var.lambda_timeout`,
			"Lambda should use configurable timeout")

		// Verify runtime is configured
		assert.Contains(t, lambdaBlock, `runtime       = var.lambda_runtime`,
			"Lambda should use configurable runtime")

		// Verify handler is configured
		assert.Contains(t, lambdaBlock, `handler       = "handler.lambda_handler"`,
			"Lambda should have handler configured")

		// Verify execution role is configured
		assert.Contains(t, lambdaBlock, `role          = var.lambda_execution_role_arn`,
			"Lambda should use IAM execution role")
	})

	// Test Lambda memory size variable validation
	t.Run("Lambda Memory Size Variable Validation", func(t *testing.T) {
		content, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		contentStr := string(content)

		// Verify lambda_memory_size variable exists
		assert.Contains(t, contentStr, `variable "lambda_memory_size"`,
			"Should have lambda_memory_size variable")

		// Extract lambda_memory_size variable block
		memoryVarStart := strings.Index(contentStr, `variable "lambda_memory_size"`)
		require.NotEqual(t, -1, memoryVarStart, "lambda_memory_size variable should exist")

		memoryVarEnd := findResourceBlockEnd(contentStr, memoryVarStart)
		memoryVarBlock := contentStr[memoryVarStart:memoryVarEnd]

		// Verify default value is at least 1024 MB
		assert.Contains(t, memoryVarBlock, `default     = 1024`,
			"Lambda memory should default to 1024 MB")

		// Verify validation rule exists
		assert.Contains(t, memoryVarBlock, `validation {`,
			"Lambda memory should have validation")

		// Verify minimum memory constraint
		assert.Contains(t, memoryVarBlock, `>= 1024`,
			"Lambda memory must be at least 1024 MB")

		// Verify error message
		assert.Contains(t, memoryVarBlock, `error_message`,
			"Lambda memory validation should have error message")
		assert.Contains(t, memoryVarBlock, `at least 1024 MB`,
			"Error message should mention minimum 1024 MB requirement")
	})

	// Test Lambda timeout variable validation
	t.Run("Lambda Timeout Variable Validation", func(t *testing.T) {
		content, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		contentStr := string(content)

		// Verify lambda_timeout variable exists
		assert.Contains(t, contentStr, `variable "lambda_timeout"`,
			"Should have lambda_timeout variable")

		// Extract lambda_timeout variable block
		timeoutVarStart := strings.Index(contentStr, `variable "lambda_timeout"`)
		require.NotEqual(t, -1, timeoutVarStart, "lambda_timeout variable should exist")

		timeoutVarEnd := findResourceBlockEnd(contentStr, timeoutVarStart)
		timeoutVarBlock := contentStr[timeoutVarStart:timeoutVarEnd]

		// Verify default value is at least 300 seconds
		assert.Contains(t, timeoutVarBlock, `default     = 300`,
			"Lambda timeout should default to 300 seconds")

		// Verify validation rule exists
		assert.Contains(t, timeoutVarBlock, `validation {`,
			"Lambda timeout should have validation")

		// Verify minimum timeout constraint
		assert.Contains(t, timeoutVarBlock, `>= 300`,
			"Lambda timeout must be at least 300 seconds")

		// Verify error message
		assert.Contains(t, timeoutVarBlock, `error_message`,
			"Lambda timeout validation should have error message")
		assert.Contains(t, timeoutVarBlock, `at least 300 seconds`,
			"Error message should mention minimum 300 seconds requirement")
		assert.Contains(t, timeoutVarBlock, `5 minutes`,
			"Error message should mention 5 minutes for clarity")
	})

	// Test Lambda runtime variable
	t.Run("Lambda Runtime Variable", func(t *testing.T) {
		content, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		contentStr := string(content)

		// Verify lambda_runtime variable exists
		assert.Contains(t, contentStr, `variable "lambda_runtime"`,
			"Should have lambda_runtime variable")

		// Extract lambda_runtime variable block
		runtimeVarStart := strings.Index(contentStr, `variable "lambda_runtime"`)
		require.NotEqual(t, -1, runtimeVarStart, "lambda_runtime variable should exist")

		runtimeVarEnd := findResourceBlockEnd(contentStr, runtimeVarStart)
		runtimeVarBlock := contentStr[runtimeVarStart:runtimeVarEnd]

		// Verify default runtime is Python 3.11+
		assert.Contains(t, runtimeVarBlock, `default     = "python3.11"`,
			"Lambda runtime should default to Python 3.11")
	})
}

// Property 40: Lambda X-Ray Tracing
// Feature: aws-bedrock-rag-deployment, Property 40: Lambda X-Ray Tracing
// Validates: Requirements 10.5
//
// For any Lambda function created by the module, X-Ray tracing should be enabled to provide
// distributed tracing capabilities.
func TestProperty40_LambdaXRayTracing(t *testing.T) {
	t.Parallel()

	s3PipelineDir := "../../modules/ai-workload/s3-pipeline"
	lambdaFile := filepath.Join(s3PipelineDir, "lambda.tf")

	content, err := os.ReadFile(lambdaFile)
	require.NoError(t, err, "Should be able to read lambda.tf")

	contentStr := string(content)

	// Test X-Ray tracing configuration
	t.Run("X-Ray Tracing Configuration", func(t *testing.T) {
		// Verify Lambda function is defined
		assert.Contains(t, contentStr, `resource "aws_lambda_function" "document_processor"`,
			"Should define Lambda document processor function")

		// Extract Lambda function block
		lambdaStart := strings.Index(contentStr, `resource "aws_lambda_function" "document_processor"`)
		require.NotEqual(t, -1, lambdaStart, "Lambda function should exist")

		lambdaEnd := findResourceBlockEnd(contentStr, lambdaStart)
		lambdaBlock := contentStr[lambdaStart:lambdaEnd]

		// Verify tracing_config block exists
		assert.Contains(t, lambdaBlock, `tracing_config {`,
			"Lambda should have tracing_config block")

		// Extract tracing_config block
		tracingStart := strings.Index(lambdaBlock, `tracing_config {`)
		require.NotEqual(t, -1, tracingStart, "tracing_config block should exist")

		tracingEnd := findNestedBlockEnd(lambdaBlock, tracingStart)
		tracingBlock := lambdaBlock[tracingStart:tracingEnd]

		// Verify X-Ray tracing is set to Active
		assert.Contains(t, tracingBlock, `mode = "Active"`,
			"X-Ray tracing mode should be Active")
	})
}

// TestLambdaVPCConfiguration tests Lambda VPC configuration
// Validates: Requirements 4.4
func TestLambdaVPCConfiguration(t *testing.T) {
	t.Parallel()

	s3PipelineDir := "../../modules/ai-workload/s3-pipeline"
	lambdaFile := filepath.Join(s3PipelineDir, "lambda.tf")
	variablesFile := filepath.Join(s3PipelineDir, "variables.tf")

	// Test Lambda VPC configuration
	t.Run("Lambda VPC Configuration", func(t *testing.T) {
		content, err := os.ReadFile(lambdaFile)
		require.NoError(t, err, "Should be able to read lambda.tf")

		contentStr := string(content)

		// Extract Lambda function block
		lambdaStart := strings.Index(contentStr, `resource "aws_lambda_function" "document_processor"`)
		require.NotEqual(t, -1, lambdaStart, "Lambda function should exist")

		lambdaEnd := findResourceBlockEnd(contentStr, lambdaStart)
		lambdaBlock := contentStr[lambdaStart:lambdaEnd]

		// Verify vpc_config block exists
		assert.Contains(t, lambdaBlock, `vpc_config {`,
			"Lambda should have vpc_config block")

		// Extract vpc_config block
		vpcStart := strings.Index(lambdaBlock, `vpc_config {`)
		require.NotEqual(t, -1, vpcStart, "vpc_config block should exist")

		vpcEnd := findNestedBlockEnd(lambdaBlock, vpcStart)
		vpcBlock := lambdaBlock[vpcStart:vpcEnd]

		// Verify subnet_ids is configured
		assert.Contains(t, vpcBlock, `subnet_ids         = var.lambda_vpc_config.subnet_ids`,
			"Lambda should use VPC subnet IDs")

		// Verify security_group_ids is configured
		assert.Contains(t, vpcBlock, `security_group_ids = var.lambda_vpc_config.security_group_ids`,
			"Lambda should use VPC security group IDs")
	})

	// Test Lambda VPC variable configuration
	t.Run("Lambda VPC Variable Configuration", func(t *testing.T) {
		content, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		contentStr := string(content)

		// Verify lambda_vpc_config variable exists
		assert.Contains(t, contentStr, `variable "lambda_vpc_config"`,
			"Should have lambda_vpc_config variable")

		// Extract lambda_vpc_config variable block
		vpcVarStart := strings.Index(contentStr, `variable "lambda_vpc_config"`)
		require.NotEqual(t, -1, vpcVarStart, "lambda_vpc_config variable should exist")

		vpcVarEnd := findResourceBlockEnd(contentStr, vpcVarStart)
		vpcVarBlock := contentStr[vpcVarStart:vpcVarEnd]

		// Verify type is object with required fields
		assert.Contains(t, vpcVarBlock, `type = object({`,
			"lambda_vpc_config should be an object type")
		assert.Contains(t, vpcVarBlock, `subnet_ids         = list(string)`,
			"lambda_vpc_config should have subnet_ids field")
		assert.Contains(t, vpcVarBlock, `security_group_ids = list(string)`,
			"lambda_vpc_config should have security_group_ids field")
	})
}

// TestLambdaCloudWatchLogging tests Lambda CloudWatch logging configuration
// Validates: Requirements 10.1
func TestLambdaCloudWatchLogging(t *testing.T) {
	t.Parallel()

	s3PipelineDir := "../../modules/ai-workload/s3-pipeline"
	lambdaFile := filepath.Join(s3PipelineDir, "lambda.tf")
	variablesFile := filepath.Join(s3PipelineDir, "variables.tf")

	// Test CloudWatch log group configuration
	t.Run("CloudWatch Log Group Configuration", func(t *testing.T) {
		content, err := os.ReadFile(lambdaFile)
		require.NoError(t, err, "Should be able to read lambda.tf")

		contentStr := string(content)

		// Verify CloudWatch log group is defined
		assert.Contains(t, contentStr, `resource "aws_cloudwatch_log_group" "lambda"`,
			"Should define CloudWatch log group for Lambda")

		// Extract log group block
		logGroupStart := strings.Index(contentStr, `resource "aws_cloudwatch_log_group" "lambda"`)
		require.NotEqual(t, -1, logGroupStart, "CloudWatch log group should exist")

		logGroupEnd := findResourceBlockEnd(contentStr, logGroupStart)
		logGroupBlock := contentStr[logGroupStart:logGroupEnd]

		// Verify log group name follows AWS Lambda convention
		assert.Contains(t, logGroupBlock, `name              = "/aws/lambda/${var.lambda_function_name}"`,
			"Log group name should follow AWS Lambda convention")

		// Verify retention is configured
		assert.Contains(t, logGroupBlock, `retention_in_days = var.lambda_log_retention_days`,
			"Log retention should be configurable")

		// Verify KMS encryption is configured
		assert.Contains(t, logGroupBlock, `kms_key_id        = var.kms_key_arn`,
			"Log group should use KMS encryption")

		// Verify Lambda depends on log group
		lambdaStart := strings.Index(contentStr, `resource "aws_lambda_function" "document_processor"`)
		require.NotEqual(t, -1, lambdaStart, "Lambda function should exist")

		lambdaEnd := findResourceBlockEnd(contentStr, lambdaStart)
		lambdaBlock := contentStr[lambdaStart:lambdaEnd]

		assert.Contains(t, lambdaBlock, `depends_on = [aws_cloudwatch_log_group.lambda]`,
			"Lambda should depend on log group creation")
	})

	// Test log retention variable
	t.Run("Log Retention Variable", func(t *testing.T) {
		content, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		contentStr := string(content)

		// Verify lambda_log_retention_days variable exists
		assert.Contains(t, contentStr, `variable "lambda_log_retention_days"`,
			"Should have lambda_log_retention_days variable")

		// Extract variable block
		retentionVarStart := strings.Index(contentStr, `variable "lambda_log_retention_days"`)
		require.NotEqual(t, -1, retentionVarStart, "lambda_log_retention_days variable should exist")

		retentionVarEnd := findResourceBlockEnd(contentStr, retentionVarStart)
		retentionVarBlock := contentStr[retentionVarStart:retentionVarEnd]

		// Verify default value
		assert.Contains(t, retentionVarBlock, `default     = 7`,
			"Log retention should have a default value")
	})
}

// TestLambdaEnvironmentVariables tests Lambda environment variable configuration
// Validates: Requirements 4.4
func TestLambdaEnvironmentVariables(t *testing.T) {
	t.Parallel()

	s3PipelineDir := "../../modules/ai-workload/s3-pipeline"
	lambdaFile := filepath.Join(s3PipelineDir, "lambda.tf")
	variablesFile := filepath.Join(s3PipelineDir, "variables.tf")

	// Test Lambda environment variables
	t.Run("Lambda Environment Variables", func(t *testing.T) {
		content, err := os.ReadFile(lambdaFile)
		require.NoError(t, err, "Should be able to read lambda.tf")

		contentStr := string(content)

		// Extract Lambda function block
		lambdaStart := strings.Index(contentStr, `resource "aws_lambda_function" "document_processor"`)
		require.NotEqual(t, -1, lambdaStart, "Lambda function should exist")

		lambdaEnd := findResourceBlockEnd(contentStr, lambdaStart)
		lambdaBlock := contentStr[lambdaStart:lambdaEnd]

		// Verify environment block exists
		assert.Contains(t, lambdaBlock, `environment {`,
			"Lambda should have environment block")

		// Extract environment block
		envStart := strings.Index(lambdaBlock, `environment {`)
		require.NotEqual(t, -1, envStart, "environment block should exist")

		envEnd := findNestedBlockEnd(lambdaBlock, envStart)
		envBlock := lambdaBlock[envStart:envEnd]

		// Verify required environment variables
		requiredEnvVars := []string{
			"DESTINATION_BUCKET",
			"SOURCE_BUCKET",
			"KMS_KEY_ARN",
			"LOG_LEVEL",
		}

		for _, envVar := range requiredEnvVars {
			assert.Contains(t, envBlock, envVar,
				"Lambda should have %s environment variable", envVar)
		}

		// Verify merge with custom environment variables
		assert.Contains(t, envBlock, `merge(`,
			"Lambda should merge default and custom environment variables")
		assert.Contains(t, envBlock, `var.lambda_environment_variables`,
			"Lambda should accept custom environment variables")
	})

	// Test environment variables variable
	t.Run("Environment Variables Variable", func(t *testing.T) {
		content, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		contentStr := string(content)

		// Verify lambda_environment_variables variable exists
		assert.Contains(t, contentStr, `variable "lambda_environment_variables"`,
			"Should have lambda_environment_variables variable")

		// Extract variable block
		envVarStart := strings.Index(contentStr, `variable "lambda_environment_variables"`)
		require.NotEqual(t, -1, envVarStart, "lambda_environment_variables variable should exist")

		envVarEnd := findResourceBlockEnd(contentStr, envVarStart)
		envVarBlock := contentStr[envVarStart:envVarEnd]

		// Verify type is map(string)
		assert.Contains(t, envVarBlock, `type        = map(string)`,
			"lambda_environment_variables should be map(string)")

		// Verify default is empty map
		assert.Contains(t, envVarBlock, `default     = {}`,
			"lambda_environment_variables should default to empty map")
	})
}

// TestLambdaModuleOutputs tests that Lambda outputs are properly defined
// Validates: Requirements 12.4
func TestLambdaModuleOutputs(t *testing.T) {
	t.Parallel()

	s3PipelineDir := "../../modules/ai-workload/s3-pipeline"
	outputsFile := filepath.Join(s3PipelineDir, "outputs.tf")

	content, err := os.ReadFile(outputsFile)
	require.NoError(t, err, "Should be able to read outputs.tf")

	contentStr := string(content)

	// Verify required Lambda outputs
	lambdaOutputs := []string{
		"lambda_function_arn",
		"lambda_function_name",
		"lambda_function_invoke_arn",
		"lambda_log_group_name",
		"lambda_log_group_arn",
	}

	for _, output := range lambdaOutputs {
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
}

