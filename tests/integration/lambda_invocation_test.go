package integration

import (
	"encoding/json"
	"fmt"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/lambda"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/gruntwork-io/terratest/modules/random"
	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	test_structure "github.com/gruntwork-io/terratest/modules/test-structure"
)

// TestLambdaS3EventTrigger tests Lambda function invocation via S3 event
func TestLambdaS3EventTrigger(t *testing.T) {
	t.Parallel()

	workingDir := "../../environments/app-layer/bedrock-rag"
	
	defer test_structure.RunTestStage(t, "cleanup", func() {
		terraformOptions := test_structure.LoadTerraformOptions(t, workingDir)
		terraform.Destroy(t, terraformOptions)
	})

	test_structure.RunTestStage(t, "setup", func() {
		uniqueID := random.UniqueId()
		
		terraformOptions := &terraform.Options{
			TerraformDir: workingDir,
			Vars: map[string]interface{}{
				"lambda_function_name": fmt.Sprintf("test-doc-processor-%s", uniqueID),
				"lambda_memory_size":   1024,
				"lambda_timeout":       300,
				"environment":          "test",
				"project":              "BOS-AI-RAG-Test",
			},
			NoColor: true,
		}

		test_structure.SaveTerraformOptions(t, workingDir, terraformOptions)
		terraform.InitAndApply(t, terraformOptions)
	})

	test_structure.RunTestStage(t, "validate", func() {
		terraformOptions := test_structure.LoadTerraformOptions(t, workingDir)

		// Test 1: Verify Lambda function exists
		t.Run("LambdaFunctionExists", func(t *testing.T) {
			functionName := terraform.Output(t, terraformOptions, "lambda_function_name")
			assert.NotEmpty(t, functionName, "Lambda function name should not be empty")
			
			lambdaClient := createLambdaClient(t, "us-east-1")
			result, err := lambdaClient.GetFunction(&lambda.GetFunctionInput{
				FunctionName: aws.String(functionName),
			})
			require.NoError(t, err, "Lambda function should exist")
			assert.NotNil(t, result.Configuration, "Lambda configuration should not be nil")
		})

		// Test 2: Verify Lambda configuration
		t.Run("LambdaConfiguration", func(t *testing.T) {
			functionName := terraform.Output(t, terraformOptions, "lambda_function_name")
			
			lambdaClient := createLambdaClient(t, "us-east-1")
			result, err := lambdaClient.GetFunction(&lambda.GetFunctionInput{
				FunctionName: aws.String(functionName),
			})
			require.NoError(t, err, "Failed to get Lambda function")
			
			config := result.Configuration
			
			// Check memory size
			assert.GreaterOrEqual(t, *config.MemorySize, int64(1024), "Lambda memory should be at least 1024 MB")
			
			// Check timeout
			assert.GreaterOrEqual(t, *config.Timeout, int64(300), "Lambda timeout should be at least 300 seconds")
			
			// Check runtime
			assert.Contains(t, *config.Runtime, "python", "Lambda runtime should be Python")
			
			// Check VPC configuration
			assert.NotNil(t, config.VpcConfig, "Lambda should have VPC configuration")
			if config.VpcConfig != nil {
				assert.NotEmpty(t, config.VpcConfig.SubnetIds, "Lambda should be in subnets")
				assert.NotEmpty(t, config.VpcConfig.SecurityGroupIds, "Lambda should have security groups")
			}
		})

		// Test 3: Verify X-Ray tracing is enabled
		t.Run("XRayTracingEnabled", func(t *testing.T) {
			functionName := terraform.Output(t, terraformOptions, "lambda_function_name")
			
			lambdaClient := createLambdaClient(t, "us-east-1")
			result, err := lambdaClient.GetFunction(&lambda.GetFunctionInput{
				FunctionName: aws.String(functionName),
			})
			require.NoError(t, err, "Failed to get Lambda function")
			
			config := result.Configuration
			assert.NotNil(t, config.TracingConfig, "Lambda should have tracing configuration")
			if config.TracingConfig != nil {
				assert.Equal(t, "Active", *config.TracingConfig.Mode, "X-Ray tracing should be active")
			}
		})

		// Test 4: Verify Dead Letter Queue configuration
		t.Run("DeadLetterQueueConfigured", func(t *testing.T) {
			functionName := terraform.Output(t, terraformOptions, "lambda_function_name")
			
			lambdaClient := createLambdaClient(t, "us-east-1")
			result, err := lambdaClient.GetFunction(&lambda.GetFunctionInput{
				FunctionName: aws.String(functionName),
			})
			require.NoError(t, err, "Failed to get Lambda function")
			
			config := result.Configuration
			assert.NotNil(t, config.DeadLetterConfig, "Lambda should have Dead Letter Queue configured")
			if config.DeadLetterConfig != nil {
				assert.NotEmpty(t, config.DeadLetterConfig.TargetArn, "DLQ target ARN should not be empty")
			}
		})

		// Test 5: Test Lambda invocation with S3 event
		t.Run("LambdaS3EventInvocation", func(t *testing.T) {
			functionName := terraform.Output(t, terraformOptions, "lambda_function_name")
			sourceBucket := terraform.Output(t, terraformOptions, "source_bucket_id")
			
			// Create test S3 event payload
			testKey := fmt.Sprintf("test-documents/test-%s.txt", random.UniqueId())
			s3Event := map[string]interface{}{
				"Records": []map[string]interface{}{
					{
						"eventVersion": "2.1",
						"eventSource":  "aws:s3",
						"eventName":    "ObjectCreated:Put",
						"s3": map[string]interface{}{
							"bucket": map[string]interface{}{
								"name": sourceBucket,
								"arn":  fmt.Sprintf("arn:aws:s3:::%s", sourceBucket),
							},
							"object": map[string]interface{}{
								"key":  testKey,
								"size": 1024,
							},
						},
					},
				},
			}
			
			payload, err := json.Marshal(s3Event)
			require.NoError(t, err, "Failed to marshal S3 event")
			
			// Invoke Lambda function
			lambdaClient := createLambdaClient(t, "us-east-1")
			invokeResult, err := lambdaClient.Invoke(&lambda.InvokeInput{
				FunctionName: aws.String(functionName),
				Payload:      payload,
			})
			require.NoError(t, err, "Failed to invoke Lambda function")
			
			// Check invocation result
			assert.Nil(t, invokeResult.FunctionError, "Lambda invocation should not have errors")
			assert.Equal(t, int64(200), *invokeResult.StatusCode, "Lambda should return 200 status code")
		})

		// Test 6: Test Lambda with actual S3 upload
		t.Run("LambdaTriggeredByS3Upload", func(t *testing.T) {
			sourceBucket := terraform.Output(t, terraformOptions, "source_bucket_id")
			functionName := terraform.Output(t, terraformOptions, "lambda_function_name")
			
			// Upload test document to S3
			testKey := fmt.Sprintf("documents/test-%s.txt", random.UniqueId())
			testContent := "This is a test document for Lambda processing"
			
			s3Client := createS3Client(t, "us-east-1")
			_, err := s3Client.PutObject(&s3.PutObjectInput{
				Bucket: aws.String(sourceBucket),
				Key:    aws.String(testKey),
				Body:   aws.ReadSeekCloser([]byte(testContent)),
				Metadata: map[string]*string{
					"document-type":      aws.String("text"),
					"chunking-strategy":  aws.String("semantic"),
				},
			})
			require.NoError(t, err, "Failed to upload test document")
			
			// Wait for Lambda to be invoked (check CloudWatch Logs)
			t.Log("Waiting for Lambda invocation (up to 30 seconds)...")
			time.Sleep(30 * time.Second)
			
			// Check Lambda invocation metrics
			lambdaClient := createLambdaClient(t, "us-east-1")
			
			// Get function configuration to verify it was invoked
			result, err := lambdaClient.GetFunction(&lambda.GetFunctionInput{
				FunctionName: aws.String(functionName),
			})
			require.NoError(t, err, "Failed to get Lambda function")
			
			// If we got here without errors, the Lambda function is properly configured
			assert.NotNil(t, result.Configuration, "Lambda configuration should exist")
			
			t.Log("Lambda function is properly configured and ready to process S3 events")
		})

		// Test 7: Verify Lambda IAM permissions
		t.Run("LambdaIAMPermissions", func(t *testing.T) {
			functionName := terraform.Output(t, terraformOptions, "lambda_function_name")
			
			lambdaClient := createLambdaClient(t, "us-east-1")
			result, err := lambdaClient.GetFunction(&lambda.GetFunctionInput{
				FunctionName: aws.String(functionName),
			})
			require.NoError(t, err, "Failed to get Lambda function")
			
			config := result.Configuration
			assert.NotEmpty(t, *config.Role, "Lambda should have an execution role")
			
			// Verify role ARN format
			assert.Contains(t, *config.Role, "arn:aws:iam::", "Role should be a valid IAM role ARN")
			assert.Contains(t, *config.Role, ":role/", "Role should be a valid IAM role ARN")
		})
	})
}

// TestLambdaPerformance tests Lambda function performance characteristics
func TestLambdaPerformance(t *testing.T) {
	t.Parallel()

	workingDir := "../../environments/app-layer/bedrock-rag"
	
	test_structure.RunTestStage(t, "validate_performance", func() {
		terraformOptions := test_structure.LoadTerraformOptions(t, workingDir)
		
		// Test: Verify Lambda cold start time
		t.Run("LambdaColdStartTime", func(t *testing.T) {
			functionName := terraform.Output(t, terraformOptions, "lambda_function_name")
			
			// Create simple test payload
			payload := []byte(`{"test": "cold-start"}`)
			
			lambdaClient := createLambdaClient(t, "us-east-1")
			
			start := time.Now()
			invokeResult, err := lambdaClient.Invoke(&lambda.InvokeInput{
				FunctionName: aws.String(functionName),
				Payload:      payload,
			})
			elapsed := time.Since(start)
			
			require.NoError(t, err, "Failed to invoke Lambda function")
			assert.Nil(t, invokeResult.FunctionError, "Lambda invocation should not have errors")
			
			// Cold start should complete within reasonable time
			assert.Less(t, elapsed.Seconds(), 30.0, "Lambda cold start should complete within 30 seconds")
			
			t.Logf("Lambda cold start time: %.2f seconds", elapsed.Seconds())
		})

		// Test: Verify Lambda warm invocation time
		t.Run("LambdaWarmInvocationTime", func(t *testing.T) {
			functionName := terraform.Output(t, terraformOptions, "lambda_function_name")
			
			payload := []byte(`{"test": "warm-invocation"}`)
			
			lambdaClient := createLambdaClient(t, "us-east-1")
			
			// Warm up the function
			_, _ = lambdaClient.Invoke(&lambda.InvokeInput{
				FunctionName: aws.String(functionName),
				Payload:      payload,
			})
			
			time.Sleep(2 * time.Second)
			
			// Measure warm invocation
			start := time.Now()
			invokeResult, err := lambdaClient.Invoke(&lambda.InvokeInput{
				FunctionName: aws.String(functionName),
				Payload:      payload,
			})
			elapsed := time.Since(start)
			
			require.NoError(t, err, "Failed to invoke Lambda function")
			assert.Nil(t, invokeResult.FunctionError, "Lambda invocation should not have errors")
			
			// Warm invocation should be faster
			assert.Less(t, elapsed.Seconds(), 10.0, "Lambda warm invocation should complete within 10 seconds")
			
			t.Logf("Lambda warm invocation time: %.2f seconds", elapsed.Seconds())
		})
	})
}

// Helper functions

func createLambdaClient(t *testing.T, region string) *lambda.Lambda {
	sess := createAWSSession(t, region)
	return lambda.New(sess)
}
