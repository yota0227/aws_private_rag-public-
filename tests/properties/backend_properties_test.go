package properties

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 25: Terraform State Backend Configuration
// Feature: aws-bedrock-rag-deployment, Property 25: Terraform State Backend Configuration
// Validates: Requirements 6.1, 6.2, 6.3, 6.4
//
// For any Terraform configuration in the module, an S3 backend should be configured with
// encryption enabled, versioning enabled on the state bucket, and a DynamoDB table for state locking.
func TestProperty25_TerraformStateBackendConfiguration(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name              string
		terraformDir      string
		expectedKey       string
		shouldHaveBackend bool
	}{
		{
			name:              "Network Layer Backend",
			terraformDir:      "../../environments/network-layer",
			expectedKey:       "network-layer/terraform.tfstate",
			shouldHaveBackend: true,
		},
		{
			name:              "App Layer Backend",
			terraformDir:      "../../environments/app-layer/bedrock-rag",
			expectedKey:       "app-layer/bedrock-rag/terraform.tfstate",
			shouldHaveBackend: true,
		},
		{
			name:              "Global Backend (No Backend)",
			terraformDir:      "../../environments/global/backend",
			expectedKey:       "",
			shouldHaveBackend: false,
		},
	}

	for _, tc := range testCases {
		tc := tc // capture range variable
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			backendFile := filepath.Join(tc.terraformDir, "backend.tf")

			if !tc.shouldHaveBackend {
				// Global backend should not have a backend.tf file
				_, err := os.Stat(backendFile)
				assert.True(t, os.IsNotExist(err), "Global backend should not have backend.tf")
				return
			}

			// Read backend.tf file
			content, err := os.ReadFile(backendFile)
			require.NoError(t, err, "Should be able to read backend.tf")

			contentStr := string(content)

			// Verify S3 backend is configured
			assert.Contains(t, contentStr, `backend "s3"`, "Backend type should be S3")

			// Verify required backend attributes
			assert.Contains(t, contentStr, `bucket`, "Backend bucket should be specified")
			assert.Contains(t, contentStr, fmt.Sprintf(`key            = "%s"`, tc.expectedKey), "Backend key should match expected path")
			assert.Contains(t, contentStr, `region         = "ap-northeast-2"`, "Backend region should be ap-northeast-2")
			assert.Contains(t, contentStr, `encrypt        = true`, "Backend encryption should be enabled")
			assert.Contains(t, contentStr, `dynamodb_table`, "DynamoDB table for locking should be specified")

			// Verify bucket and table names match expected values
			assert.Contains(t, contentStr, `bucket         = "bos-ai-terraform-state"`, "Backend bucket name should match")
			assert.Contains(t, contentStr, `dynamodb_table = "terraform-state-lock"`, "DynamoDB table name should match")
		})
	}
}

// TestProperty25_BackendInfrastructureResources tests that the backend infrastructure
// creates the required S3 bucket and DynamoDB table with proper configuration
func TestProperty25_BackendInfrastructureResources(t *testing.T) {
	t.Parallel()

	terraformDir := "../../environments/global/backend"
	mainFile := filepath.Join(terraformDir, "main.tf")

	// Read main.tf to verify resource configuration
	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Check for required resources
	assert.Contains(t, contentStr, `resource "aws_s3_bucket" "terraform_state"`, "Should define S3 bucket resource")
	assert.Contains(t, contentStr, `resource "aws_s3_bucket_versioning" "terraform_state"`, "Should define S3 versioning resource")
	assert.Contains(t, contentStr, `resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state"`, "Should define S3 encryption resource")
	assert.Contains(t, contentStr, `resource "aws_dynamodb_table" "terraform_state_lock"`, "Should define DynamoDB table resource")

	// Verify versioning is enabled
	assert.Contains(t, contentStr, `status = "Enabled"`, "Versioning should be enabled")

	// Verify encryption algorithm
	assert.Contains(t, contentStr, `sse_algorithm = "AES256"`, "Should use AES256 encryption")

	// Verify DynamoDB hash key
	assert.Contains(t, contentStr, `hash_key     = "LockID"`, "DynamoDB table should have LockID as hash key")
}

// TestProperty25_BackendAccessLogging tests that access logging is enabled for the state bucket
// Validates: Requirement 6.6
func TestProperty25_BackendAccessLogging(t *testing.T) {
	t.Parallel()

	terraformDir := "../../environments/global/backend"
	mainFile := filepath.Join(terraformDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Check for logging configuration
	assert.Contains(t, contentStr, `resource "aws_s3_bucket_logging" "terraform_state"`, "Should define S3 logging resource")
	assert.Contains(t, contentStr, `target_bucket`, "Should specify target bucket for logs")
	assert.Contains(t, contentStr, `target_prefix`, "Should specify target prefix for logs")
}

// TestProperty25_BackendBucketPolicy tests that bucket policy restricts access
// Validates: Requirement 6.5
func TestProperty25_BackendBucketPolicy(t *testing.T) {
	t.Parallel()

	terraformDir := "../../environments/global/backend"
	mainFile := filepath.Join(terraformDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Check for bucket policy
	assert.Contains(t, contentStr, `resource "aws_s3_bucket_policy" "terraform_state"`, "Should define bucket policy")
	assert.Contains(t, contentStr, `data "aws_iam_policy_document" "terraform_state_policy"`, "Should define policy document")

	// Check for secure transport enforcement
	assert.Contains(t, contentStr, `DenyInsecureTransport`, "Should deny insecure transport")
	assert.Contains(t, contentStr, `aws:SecureTransport`, "Should check SecureTransport condition")
}

// TestProperty25_BackendPublicAccessBlock tests that public access is blocked
// Validates: Requirement 6.5
func TestProperty25_BackendPublicAccessBlock(t *testing.T) {
	t.Parallel()

	terraformDir := "../../environments/global/backend"
	mainFile := filepath.Join(terraformDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Check for public access block
	assert.Contains(t, contentStr, `resource "aws_s3_bucket_public_access_block" "terraform_state"`, "Should define public access block")
	assert.Contains(t, contentStr, `block_public_acls       = true`, "Should block public ACLs")
	assert.Contains(t, contentStr, `block_public_policy     = true`, "Should block public policy")
	assert.Contains(t, contentStr, `ignore_public_acls      = true`, "Should ignore public ACLs")
	assert.Contains(t, contentStr, `restrict_public_buckets = true`, "Should restrict public buckets")
}
