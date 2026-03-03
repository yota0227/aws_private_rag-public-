package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 14: S3 Event-Driven Lambda Invocation
// Feature: aws-bedrock-rag-deployment, Property 14: S3 Event-Driven Lambda Invocation
// Validates: Requirements 4.3, 4.10
//
// For any S3 bucket configured as a document source, S3 event notifications should be
// configured to invoke the document processor Lambda function on object creation events.
func TestProperty14_S3EventDrivenLambdaInvocation(t *testing.T) {
	t.Parallel()

	s3PipelineDir := "../../modules/ai-workload/s3-pipeline"
	lambdaFile := filepath.Join(s3PipelineDir, "lambda.tf")

	content, err := os.ReadFile(lambdaFile)
	require.NoError(t, err, "Should be able to read lambda.tf")

	contentStr := string(content)

	// Test S3 Event Notification Configuration
	t.Run("S3 Event Notification Configuration", func(t *testing.T) {
		// Verify S3 bucket notification is defined
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_notification" "document_upload"`,
			"Should define S3 bucket notification")

		// Extract notification block
		notificationStart := strings.Index(contentStr, `resource "aws_s3_bucket_notification" "document_upload"`)
		require.NotEqual(t, -1, notificationStart, "S3 bucket notification should exist")

		notificationEnd := findResourceBlockEnd(contentStr, notificationStart)
		notificationBlock := contentStr[notificationStart:notificationEnd]

		// Verify notification is configured for destination bucket
		assert.Contains(t, notificationBlock, `bucket = aws_s3_bucket.destination.id`,
			"Notification should be configured for destination bucket")

		// Verify lambda_function block exists
		assert.Contains(t, notificationBlock, `lambda_function {`,
			"Notification should have lambda_function configuration")

		// Extract lambda_function block
		lambdaFuncStart := strings.Index(notificationBlock, `lambda_function {`)
		require.NotEqual(t, -1, lambdaFuncStart, "lambda_function block should exist")

		lambdaFuncEnd := findNestedBlockEnd(notificationBlock, lambdaFuncStart)
		lambdaFuncBlock := notificationBlock[lambdaFuncStart:lambdaFuncEnd]

		// Verify Lambda function ARN is configured
		assert.Contains(t, lambdaFuncBlock, `lambda_function_arn = aws_lambda_function.document_processor.arn`,
			"Notification should reference Lambda function ARN")

		// Verify events include object creation
		assert.Contains(t, lambdaFuncBlock, `events              = ["s3:ObjectCreated:*"]`,
			"Notification should trigger on object creation events")

		// Verify notification depends on Lambda permission
		assert.Contains(t, notificationBlock, `depends_on = [aws_lambda_permission.allow_s3_invoke]`,
			"Notification should depend on Lambda permission")
	})

	// Test Lambda Permission for S3 Invocation
	t.Run("Lambda Permission for S3 Invocation", func(t *testing.T) {
		// Verify Lambda permission is defined
		assert.Contains(t, contentStr, `resource "aws_lambda_permission" "allow_s3_invoke"`,
			"Should define Lambda permission for S3")

		// Extract permission block
		permissionStart := strings.Index(contentStr, `resource "aws_lambda_permission" "allow_s3_invoke"`)
		require.NotEqual(t, -1, permissionStart, "Lambda permission should exist")

		permissionEnd := findResourceBlockEnd(contentStr, permissionStart)
		permissionBlock := contentStr[permissionStart:permissionEnd]

		// Verify permission allows Lambda invocation
		assert.Contains(t, permissionBlock, `action        = "lambda:InvokeFunction"`,
			"Permission should allow Lambda invocation")

		// Verify permission is for the document processor function
		assert.Contains(t, permissionBlock, `function_name = aws_lambda_function.document_processor.function_name`,
			"Permission should be for document processor function")

		// Verify principal is S3 service
		assert.Contains(t, permissionBlock, `principal     = "s3.amazonaws.com"`,
			"Permission principal should be S3 service")

		// Verify source ARN is the destination bucket
		assert.Contains(t, permissionBlock, `source_arn    = aws_s3_bucket.destination.arn`,
			"Permission source should be destination bucket")
	})

	// Test Event Filter Configuration
	t.Run("Event Filter Configuration", func(t *testing.T) {
		// Extract notification block
		notificationStart := strings.Index(contentStr, `resource "aws_s3_bucket_notification" "document_upload"`)
		require.NotEqual(t, -1, notificationStart, "S3 bucket notification should exist")

		notificationEnd := findResourceBlockEnd(contentStr, notificationStart)
		notificationBlock := contentStr[notificationStart:notificationEnd]

		// Extract lambda_function block
		lambdaFuncStart := strings.Index(notificationBlock, `lambda_function {`)
		require.NotEqual(t, -1, lambdaFuncStart, "lambda_function block should exist")

		lambdaFuncEnd := findNestedBlockEnd(notificationBlock, lambdaFuncStart)
		lambdaFuncBlock := notificationBlock[lambdaFuncStart:lambdaFuncEnd]

		// Verify filter_prefix is defined (even if empty)
		assert.Contains(t, lambdaFuncBlock, `filter_prefix`,
			"Notification should have filter_prefix defined")

		// Verify filter_suffix is defined (even if empty)
		assert.Contains(t, lambdaFuncBlock, `filter_suffix`,
			"Notification should have filter_suffix defined")
	})
}

// Property 29: Cross-Region Event Pipeline
// Feature: aws-bedrock-rag-deployment, Property 29: Cross-Region Event Pipeline
// Validates: Requirements 8.2
//
// For any S3 bucket in the Seoul region, event notifications should be configured to trigger
// the synchronization pipeline when documents are uploaded.
func TestProperty29_CrossRegionEventPipeline(t *testing.T) {
	t.Parallel()

	s3PipelineDir := "../../modules/ai-workload/s3-pipeline"
	lambdaFile := filepath.Join(s3PipelineDir, "lambda.tf")
	s3File := filepath.Join(s3PipelineDir, "s3.tf")

	// Test Cross-Region Replication triggers event pipeline
	t.Run("Cross-Region Replication to Event Pipeline", func(t *testing.T) {
		// Read S3 configuration
		s3Content, err := os.ReadFile(s3File)
		require.NoError(t, err, "Should be able to read s3.tf")

		s3ContentStr := string(s3Content)

		// Verify replication is configured
		assert.Contains(t, s3ContentStr, `resource "aws_s3_bucket_replication_configuration" "source_to_destination"`,
			"Should have cross-region replication configured")

		// Read Lambda configuration
		lambdaContent, err := os.ReadFile(lambdaFile)
		require.NoError(t, err, "Should be able to read lambda.tf")

		lambdaContentStr := string(lambdaContent)

		// Verify event notification is configured on destination bucket
		assert.Contains(t, lambdaContentStr, `resource "aws_s3_bucket_notification" "document_upload"`,
			"Should have event notification on destination bucket")

		// Extract notification block
		notificationStart := strings.Index(lambdaContentStr, `resource "aws_s3_bucket_notification" "document_upload"`)
		require.NotEqual(t, -1, notificationStart, "S3 bucket notification should exist")

		notificationEnd := findResourceBlockEnd(lambdaContentStr, notificationStart)
		notificationBlock := lambdaContentStr[notificationStart:notificationEnd]

		// Verify notification is on destination bucket (which receives replicated objects)
		assert.Contains(t, notificationBlock, `bucket = aws_s3_bucket.destination.id`,
			"Event notification should be on destination bucket that receives replicated objects")
	})

	// Test Event Pipeline Flow
	t.Run("Event Pipeline Flow", func(t *testing.T) {
		// Read Lambda configuration
		lambdaContent, err := os.ReadFile(lambdaFile)
		require.NoError(t, err, "Should be able to read lambda.tf")

		lambdaContentStr := string(lambdaContent)

		// Verify Lambda function exists to process events
		assert.Contains(t, lambdaContentStr, `resource "aws_lambda_function" "document_processor"`,
			"Should have Lambda function to process S3 events")

		// Verify S3 can invoke Lambda
		assert.Contains(t, lambdaContentStr, `resource "aws_lambda_permission" "allow_s3_invoke"`,
			"Should have permission for S3 to invoke Lambda")

		// Verify event notification triggers Lambda
		assert.Contains(t, lambdaContentStr, `resource "aws_s3_bucket_notification" "document_upload"`,
			"Should have event notification to trigger Lambda")

		// Extract Lambda function block
		lambdaStart := strings.Index(lambdaContentStr, `resource "aws_lambda_function" "document_processor"`)
		require.NotEqual(t, -1, lambdaStart, "Lambda function should exist")

		lambdaEnd := findResourceBlockEnd(lambdaContentStr, lambdaStart)
		lambdaBlock := lambdaContentStr[lambdaStart:lambdaEnd]

		// Verify Lambda has environment variables for bucket information
		assert.Contains(t, lambdaBlock, `environment {`,
			"Lambda should have environment variables")
		assert.Contains(t, lambdaBlock, `DESTINATION_BUCKET`,
			"Lambda should have destination bucket in environment")
		assert.Contains(t, lambdaBlock, `SOURCE_BUCKET`,
			"Lambda should have source bucket in environment")
	})
}

// Property 31: Lambda Dead Letter Queue
// Feature: aws-bedrock-rag-deployment, Property 31: Lambda Dead Letter Queue
// Validates: Requirements 8.7
//
// For any Lambda function handling S3 events, a Dead Letter Queue (DLQ) should be configured
// to capture failed invocation events for retry and debugging.
func TestProperty31_LambdaDeadLetterQueue(t *testing.T) {
	t.Parallel()

	s3PipelineDir := "../../modules/ai-workload/s3-pipeline"
	lambdaFile := filepath.Join(s3PipelineDir, "lambda.tf")

	content, err := os.ReadFile(lambdaFile)
	require.NoError(t, err, "Should be able to read lambda.tf")

	contentStr := string(content)

	// Test Dead Letter Queue Configuration
	t.Run("Dead Letter Queue Configuration", func(t *testing.T) {
		// Verify SQS queue for DLQ is defined
		assert.Contains(t, contentStr, `resource "aws_sqs_queue" "lambda_dlq"`,
			"Should define SQS queue for Dead Letter Queue")

		// Extract DLQ block
		dlqStart := strings.Index(contentStr, `resource "aws_sqs_queue" "lambda_dlq"`)
		require.NotEqual(t, -1, dlqStart, "DLQ should exist")

		dlqEnd := findResourceBlockEnd(contentStr, dlqStart)
		dlqBlock := contentStr[dlqStart:dlqEnd]

		// Verify DLQ name follows naming convention
		assert.Contains(t, dlqBlock, `name                       = "${var.lambda_function_name}-dlq"`,
			"DLQ name should follow naming convention")

		// Verify message retention is configured
		assert.Contains(t, dlqBlock, `message_retention_seconds`,
			"DLQ should have message retention configured")

		// Verify visibility timeout is appropriate (should be 6x Lambda timeout)
		assert.Contains(t, dlqBlock, `visibility_timeout_seconds = var.lambda_timeout * 6`,
			"DLQ visibility timeout should be 6x Lambda timeout")

		// Verify encryption is enabled
		assert.Contains(t, dlqBlock, `sqs_managed_sse_enabled = true`,
			"DLQ should have encryption enabled")
	})

	// Test DLQ Policy Configuration
	t.Run("DLQ Policy Configuration", func(t *testing.T) {
		// Verify DLQ policy is defined
		assert.Contains(t, contentStr, `resource "aws_sqs_queue_policy" "lambda_dlq"`,
			"Should define DLQ policy")

		// Extract DLQ policy block
		policyStart := strings.Index(contentStr, `resource "aws_sqs_queue_policy" "lambda_dlq"`)
		require.NotEqual(t, -1, policyStart, "DLQ policy should exist")

		policyEnd := findResourceBlockEnd(contentStr, policyStart)
		policyBlock := contentStr[policyStart:policyEnd]

		// Verify policy allows Lambda service to send messages
		assert.Contains(t, policyBlock, `Service = "lambda.amazonaws.com"`,
			"DLQ policy should allow Lambda service")

		// Verify policy allows SendMessage action
		assert.Contains(t, policyBlock, `Action   = "sqs:SendMessage"`,
			"DLQ policy should allow SendMessage action")

		// Verify policy is scoped to the Lambda function
		assert.Contains(t, policyBlock, `aws:SourceArn`,
			"DLQ policy should be scoped to Lambda function ARN")
	})

	// Test Lambda Function DLQ Configuration
	t.Run("Lambda Function DLQ Configuration", func(t *testing.T) {
		// Verify Lambda function has DLQ configured
		lambdaStart := strings.Index(contentStr, `resource "aws_lambda_function" "document_processor"`)
		require.NotEqual(t, -1, lambdaStart, "Lambda function should exist")

		lambdaEnd := findResourceBlockEnd(contentStr, lambdaStart)
		lambdaBlock := contentStr[lambdaStart:lambdaEnd]

		// Verify dead_letter_config block exists
		assert.Contains(t, lambdaBlock, `dead_letter_config {`,
			"Lambda should have dead_letter_config block")

		// Extract dead_letter_config block
		dlcStart := strings.Index(lambdaBlock, `dead_letter_config {`)
		require.NotEqual(t, -1, dlcStart, "dead_letter_config block should exist")

		dlcEnd := findNestedBlockEnd(lambdaBlock, dlcStart)
		dlcBlock := lambdaBlock[dlcStart:dlcEnd]

		// Verify target_arn points to DLQ
		assert.Contains(t, dlcBlock, `target_arn = aws_sqs_queue.lambda_dlq.arn`,
			"Lambda DLQ should reference SQS queue ARN")
	})

	// Test DLQ Outputs
	t.Run("DLQ Outputs", func(t *testing.T) {
		outputsFile := filepath.Join(s3PipelineDir, "outputs.tf")
		outputContent, err := os.ReadFile(outputsFile)
		require.NoError(t, err, "Should be able to read outputs.tf")

		outputStr := string(outputContent)

		// Verify DLQ outputs are defined
		dlqOutputs := []string{
			"lambda_dlq_arn",
			"lambda_dlq_url",
			"lambda_dlq_name",
		}

		for _, output := range dlqOutputs {
			assert.Contains(t, outputStr, `output "`+output+`"`,
				"Should define %s output", output)

			// Extract output block
			outputStart := strings.Index(outputStr, `output "`+output+`"`)
			if outputStart != -1 {
				outputEnd := findResourceBlockEnd(outputStr, outputStart)
				outputBlock := outputStr[outputStart:outputEnd]

				assert.Contains(t, outputBlock, `description`,
					"Output %s should have description", output)
				assert.Contains(t, outputBlock, `value`,
					"Output %s should have value", output)
			}
		}
	})
}

// TestEventPipelineModuleOutputs tests that event pipeline outputs are properly defined
// Validates: Requirements 12.4
func TestEventPipelineModuleOutputs(t *testing.T) {
	t.Parallel()

	s3PipelineDir := "../../modules/ai-workload/s3-pipeline"
	outputsFile := filepath.Join(s3PipelineDir, "outputs.tf")

	content, err := os.ReadFile(outputsFile)
	require.NoError(t, err, "Should be able to read outputs.tf")

	contentStr := string(content)

	// Verify S3 event notification output
	assert.Contains(t, contentStr, `output "s3_event_notification_id"`,
		"Should define s3_event_notification_id output")

	// Extract output block
	outputStart := strings.Index(contentStr, `output "s3_event_notification_id"`)
	if outputStart != -1 {
		outputEnd := findResourceBlockEnd(contentStr, outputStart)
		outputBlock := contentStr[outputStart:outputEnd]

		assert.Contains(t, outputBlock, `description`,
			"Output s3_event_notification_id should have description")
		assert.Contains(t, outputBlock, `value`,
			"Output s3_event_notification_id should have value")
		assert.Contains(t, outputBlock, `aws_s3_bucket_notification.document_upload.id`,
			"Output should reference S3 bucket notification ID")
	}
}

