package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 13: S3 Bucket Security Configuration
// Feature: aws-bedrock-rag-deployment, Property 13: S3 Bucket Security Configuration
// Validates: Requirements 4.1, 4.2, 13.1
//
// For any S3 bucket created by the module, versioning should be enabled, and encryption
// at rest using KMS customer-managed keys should be configured.
func TestProperty13_S3BucketSecurityConfiguration(t *testing.T) {
	t.Parallel()

	s3ModuleDir := "../../modules/ai-workload/s3-pipeline"
	s3File := filepath.Join(s3ModuleDir, "s3.tf")

	content, err := os.ReadFile(s3File)
	require.NoError(t, err, "Should be able to read s3.tf")

	contentStr := string(content)

	// Test Source Bucket Configuration
	t.Run("Source Bucket Security", func(t *testing.T) {
		// Verify source bucket is defined
		assert.Contains(t, contentStr, `resource "aws_s3_bucket" "source"`,
			"Should define source S3 bucket")

		// Verify versioning is enabled
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_versioning" "source"`,
			"Should define source bucket versioning")

		// Extract versioning block
		versioningStart := strings.Index(contentStr, `resource "aws_s3_bucket_versioning" "source"`)
		require.NotEqual(t, -1, versioningStart, "Source bucket versioning should exist")

		versioningEnd := findResourceBlockEnd(contentStr, versioningStart)
		versioningBlock := contentStr[versioningStart:versioningEnd]

		assert.Contains(t, versioningBlock, `status = var.enable_versioning ? "Enabled" : "Suspended"`,
			"Versioning should be configurable")

		// Verify KMS encryption is configured
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_server_side_encryption_configuration" "source"`,
			"Should define source bucket encryption")

		// Extract encryption block
		encryptionStart := strings.Index(contentStr, `resource "aws_s3_bucket_server_side_encryption_configuration" "source"`)
		require.NotEqual(t, -1, encryptionStart, "Source bucket encryption should exist")

		encryptionEnd := findResourceBlockEnd(contentStr, encryptionStart)
		encryptionBlock := contentStr[encryptionStart:encryptionEnd]

		// Verify KMS encryption is used
		assert.Contains(t, encryptionBlock, `sse_algorithm     = "aws:kms"`,
			"Should use KMS encryption")
		assert.Contains(t, encryptionBlock, `kms_master_key_id = var.kms_key_arn`,
			"Should use customer-managed KMS key")
		assert.Contains(t, encryptionBlock, `bucket_key_enabled = true`,
			"Should enable bucket key for cost optimization")

		// Verify public access is blocked
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_public_access_block" "source"`,
			"Should define source bucket public access block")

		// Extract public access block
		publicAccessStart := strings.Index(contentStr, `resource "aws_s3_bucket_public_access_block" "source"`)
		require.NotEqual(t, -1, publicAccessStart, "Source bucket public access block should exist")

		publicAccessEnd := findResourceBlockEnd(contentStr, publicAccessStart)
		publicAccessBlock := contentStr[publicAccessStart:publicAccessEnd]

		assert.Contains(t, publicAccessBlock, `block_public_acls       = true`,
			"Should block public ACLs")
		assert.Contains(t, publicAccessBlock, `block_public_policy     = true`,
			"Should block public policy")
		assert.Contains(t, publicAccessBlock, `ignore_public_acls      = true`,
			"Should ignore public ACLs")
		assert.Contains(t, publicAccessBlock, `restrict_public_buckets = true`,
			"Should restrict public buckets")
	})

	// Test Destination Bucket Configuration
	t.Run("Destination Bucket Security", func(t *testing.T) {
		// Verify destination bucket is defined
		assert.Contains(t, contentStr, `resource "aws_s3_bucket" "destination"`,
			"Should define destination S3 bucket")

		// Verify versioning is enabled (required for replication)
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_versioning" "destination"`,
			"Should define destination bucket versioning")

		// Extract versioning block
		versioningStart := strings.Index(contentStr, `resource "aws_s3_bucket_versioning" "destination"`)
		require.NotEqual(t, -1, versioningStart, "Destination bucket versioning should exist")

		versioningEnd := findResourceBlockEnd(contentStr, versioningStart)
		versioningBlock := contentStr[versioningStart:versioningEnd]

		assert.Contains(t, versioningBlock, `status = "Enabled"`,
			"Destination bucket versioning should always be enabled for replication")

		// Verify KMS encryption is configured
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_server_side_encryption_configuration" "destination"`,
			"Should define destination bucket encryption")

		// Extract encryption block
		encryptionStart := strings.Index(contentStr, `resource "aws_s3_bucket_server_side_encryption_configuration" "destination"`)
		require.NotEqual(t, -1, encryptionStart, "Destination bucket encryption should exist")

		encryptionEnd := findResourceBlockEnd(contentStr, encryptionStart)
		encryptionBlock := contentStr[encryptionStart:encryptionEnd]

		// Verify KMS encryption is used
		assert.Contains(t, encryptionBlock, `sse_algorithm     = "aws:kms"`,
			"Should use KMS encryption")
		assert.Contains(t, encryptionBlock, `kms_master_key_id = var.kms_key_arn`,
			"Should use customer-managed KMS key")

		// Verify public access is blocked
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_public_access_block" "destination"`,
			"Should define destination bucket public access block")
	})

	// Test versioning variable configuration
	t.Run("Versioning Configuration", func(t *testing.T) {
		variablesFile := filepath.Join(s3ModuleDir, "variables.tf")
		varContent, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		varStr := string(varContent)

		// Verify enable_versioning variable exists
		assert.Contains(t, varStr, `variable "enable_versioning"`,
			"Should have enable_versioning variable")

		// Extract enable_versioning variable block
		versioningVarStart := strings.Index(varStr, `variable "enable_versioning"`)
		require.NotEqual(t, -1, versioningVarStart, "enable_versioning variable should exist")

		versioningVarEnd := findResourceBlockEnd(varStr, versioningVarStart)
		versioningVarBlock := varStr[versioningVarStart:versioningVarEnd]

		assert.Contains(t, versioningVarBlock, `default     = true`,
			"Versioning should be enabled by default")
	})
}

// Property 28: S3 Cross-Region Replication
// Feature: aws-bedrock-rag-deployment, Property 28: S3 Cross-Region Replication
// Validates: Requirements 8.1, 13.3, 13.4
//
// For any S3 bucket in the Seoul region configured as a document source, cross-region
// replication should be configured to replicate objects to a corresponding bucket in the US region.
func TestProperty28_S3CrossRegionReplication(t *testing.T) {
	t.Parallel()

	s3ModuleDir := "../../modules/ai-workload/s3-pipeline"
	s3File := filepath.Join(s3ModuleDir, "s3.tf")

	content, err := os.ReadFile(s3File)
	require.NoError(t, err, "Should be able to read s3.tf")

	contentStr := string(content)

	// Test Replication Configuration
	t.Run("Replication Configuration", func(t *testing.T) {
		// Verify replication configuration is defined
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_replication_configuration" "source_to_destination"`,
			"Should define S3 replication configuration")

		// Extract replication block
		replicationStart := strings.Index(contentStr, `resource "aws_s3_bucket_replication_configuration" "source_to_destination"`)
		require.NotEqual(t, -1, replicationStart, "Replication configuration should exist")

		replicationEnd := findResourceBlockEnd(contentStr, replicationStart)
		replicationBlock := contentStr[replicationStart:replicationEnd]

		// Verify replication is configurable
		assert.Contains(t, replicationBlock, `count = var.enable_replication ? 1 : 0`,
			"Replication should be configurable")

		// Verify replication depends on versioning
		assert.Contains(t, replicationBlock, `depends_on`,
			"Replication should depend on versioning")
		assert.Contains(t, replicationBlock, `aws_s3_bucket_versioning.source`,
			"Replication should depend on source bucket versioning")
		assert.Contains(t, replicationBlock, `aws_s3_bucket_versioning.destination`,
			"Replication should depend on destination bucket versioning")

		// Verify replication rule is enabled
		assert.Contains(t, replicationBlock, `status = "Enabled"`,
			"Replication rule should be enabled")

		// Verify destination configuration
		assert.Contains(t, replicationBlock, `destination {`,
			"Replication should have destination configuration")
		assert.Contains(t, replicationBlock, `bucket        = aws_s3_bucket.destination.arn`,
			"Replication should target destination bucket")

		// Verify storage class for replicated objects
		assert.Contains(t, replicationBlock, `storage_class = "INTELLIGENT_TIERING"`,
			"Replicated objects should use Intelligent-Tiering")

		// Verify encryption configuration for replicated objects
		assert.Contains(t, replicationBlock, `encryption_configuration {`,
			"Replication should have encryption configuration")
		assert.Contains(t, replicationBlock, `replica_kms_key_id = var.kms_key_arn`,
			"Replicated objects should use KMS encryption")

		// Verify replication time control (RTC)
		assert.Contains(t, replicationBlock, `replication_time {`,
			"Replication should have time control")
		assert.Contains(t, replicationBlock, `status = "Enabled"`,
			"Replication time control should be enabled")

		// Verify delete marker replication
		assert.Contains(t, replicationBlock, `delete_marker_replication {`,
			"Replication should handle delete markers")
	})

	// Test Replication IAM Role
	t.Run("Replication IAM Role", func(t *testing.T) {
		// Verify replication role is defined
		assert.Contains(t, contentStr, `resource "aws_iam_role" "replication"`,
			"Should define replication IAM role")

		// Extract role block
		roleStart := strings.Index(contentStr, `resource "aws_iam_role" "replication"`)
		require.NotEqual(t, -1, roleStart, "Replication role should exist")

		roleEnd := findResourceBlockEnd(contentStr, roleStart)
		roleBlock := contentStr[roleStart:roleEnd]

		// Verify role is conditionally created
		assert.Contains(t, roleBlock, `count = var.enable_replication && var.replication_role_arn == "" ? 1 : 0`,
			"Replication role should be conditionally created")

		// Verify S3 service can assume the role
		assert.Contains(t, roleBlock, `Service = "s3.amazonaws.com"`,
			"S3 service should be able to assume the role")

		// Verify replication policy is defined
		assert.Contains(t, contentStr, `resource "aws_iam_role_policy" "replication"`,
			"Should define replication IAM policy")

		// Extract policy block
		policyStart := strings.Index(contentStr, `resource "aws_iam_role_policy" "replication"`)
		require.NotEqual(t, -1, policyStart, "Replication policy should exist")

		policyEnd := findResourceBlockEnd(contentStr, policyStart)
		policyBlock := contentStr[policyStart:policyEnd]

		// Verify required permissions
		requiredActions := []string{
			"s3:GetReplicationConfiguration",
			"s3:ListBucket",
			"s3:GetObjectVersionForReplication",
			"s3:ReplicateObject",
			"s3:ReplicateDelete",
			"kms:Decrypt",
			"kms:Encrypt",
		}

		for _, action := range requiredActions {
			assert.Contains(t, policyBlock, action,
				"Replication policy should include %s action", action)
		}
	})

	// Test replication variable configuration
	t.Run("Replication Variable Configuration", func(t *testing.T) {
		variablesFile := filepath.Join(s3ModuleDir, "variables.tf")
		varContent, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		varStr := string(varContent)

		// Verify enable_replication variable exists
		assert.Contains(t, varStr, `variable "enable_replication"`,
			"Should have enable_replication variable")

		// Extract enable_replication variable block
		replicationVarStart := strings.Index(varStr, `variable "enable_replication"`)
		require.NotEqual(t, -1, replicationVarStart, "enable_replication variable should exist")

		replicationVarEnd := findResourceBlockEnd(varStr, replicationVarStart)
		replicationVarBlock := varStr[replicationVarStart:replicationVarEnd]

		assert.Contains(t, replicationVarBlock, `default     = true`,
			"Replication should be enabled by default")
	})
}

// Property 42: S3 Intelligent-Tiering
// Feature: aws-bedrock-rag-deployment, Property 42: S3 Intelligent-Tiering
// Validates: Requirements 11.2
//
// For any S3 bucket used for document storage, the default storage class should be set to
// Intelligent-Tiering to automatically optimize storage costs.
func TestProperty42_S3IntelligentTiering(t *testing.T) {
	t.Parallel()

	s3ModuleDir := "../../modules/ai-workload/s3-pipeline"
	s3File := filepath.Join(s3ModuleDir, "s3.tf")

	content, err := os.ReadFile(s3File)
	require.NoError(t, err, "Should be able to read s3.tf")

	contentStr := string(content)

	// Test Source Bucket Intelligent-Tiering
	t.Run("Source Bucket Intelligent-Tiering", func(t *testing.T) {
		// Verify Intelligent-Tiering configuration is defined
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_intelligent_tiering_configuration" "source"`,
			"Should define source bucket Intelligent-Tiering configuration")

		// Extract Intelligent-Tiering block
		tieringStart := strings.Index(contentStr, `resource "aws_s3_bucket_intelligent_tiering_configuration" "source"`)
		require.NotEqual(t, -1, tieringStart, "Source bucket Intelligent-Tiering should exist")

		tieringEnd := findResourceBlockEnd(contentStr, tieringStart)
		tieringBlock := contentStr[tieringStart:tieringEnd]

		// Verify Archive Access tier is configured
		assert.Contains(t, tieringBlock, `access_tier = "ARCHIVE_ACCESS"`,
			"Should configure Archive Access tier")

		// Verify Deep Archive Access tier is configured
		assert.Contains(t, tieringBlock, `access_tier = "DEEP_ARCHIVE_ACCESS"`,
			"Should configure Deep Archive Access tier")

		// Verify tiering days are configured
		assert.Contains(t, tieringBlock, `days        = 90`,
			"Should configure Archive Access after 90 days")
		assert.Contains(t, tieringBlock, `days        = 180`,
			"Should configure Deep Archive Access after 180 days")
	})

	// Test Destination Bucket Intelligent-Tiering
	t.Run("Destination Bucket Intelligent-Tiering", func(t *testing.T) {
		// Verify Intelligent-Tiering configuration is defined
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_intelligent_tiering_configuration" "destination"`,
			"Should define destination bucket Intelligent-Tiering configuration")

		// Extract Intelligent-Tiering block
		tieringStart := strings.Index(contentStr, `resource "aws_s3_bucket_intelligent_tiering_configuration" "destination"`)
		require.NotEqual(t, -1, tieringStart, "Destination bucket Intelligent-Tiering should exist")

		tieringEnd := findResourceBlockEnd(contentStr, tieringStart)
		tieringBlock := contentStr[tieringStart:tieringEnd]

		// Verify Archive Access tier is configured
		assert.Contains(t, tieringBlock, `access_tier = "ARCHIVE_ACCESS"`,
			"Should configure Archive Access tier")

		// Verify Deep Archive Access tier is configured
		assert.Contains(t, tieringBlock, `access_tier = "DEEP_ARCHIVE_ACCESS"`,
			"Should configure Deep Archive Access tier")
	})

	// Test Replication uses Intelligent-Tiering
	t.Run("Replication Storage Class", func(t *testing.T) {
		// Verify replication uses Intelligent-Tiering
		replicationStart := strings.Index(contentStr, `resource "aws_s3_bucket_replication_configuration" "source_to_destination"`)
		if replicationStart != -1 {
			replicationEnd := findResourceBlockEnd(contentStr, replicationStart)
			replicationBlock := contentStr[replicationStart:replicationEnd]

			assert.Contains(t, replicationBlock, `storage_class = "INTELLIGENT_TIERING"`,
				"Replicated objects should use Intelligent-Tiering storage class")
		}
	})
}

// Property 43: S3 Lifecycle Policies
// Feature: aws-bedrock-rag-deployment, Property 43: S3 Lifecycle Policies
// Validates: Requirements 11.4
//
// For any S3 bucket used for document storage, lifecycle policies should be configured to
// transition old objects to cheaper storage classes (e.g., Glacier) after a specified period.
func TestProperty43_S3LifecyclePolicies(t *testing.T) {
	t.Parallel()

	s3ModuleDir := "../../modules/ai-workload/s3-pipeline"
	s3File := filepath.Join(s3ModuleDir, "s3.tf")

	content, err := os.ReadFile(s3File)
	require.NoError(t, err, "Should be able to read s3.tf")

	contentStr := string(content)

	// Test Source Bucket Lifecycle Policy
	t.Run("Source Bucket Lifecycle Policy", func(t *testing.T) {
		// Verify lifecycle configuration is defined
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_lifecycle_configuration" "source"`,
			"Should define source bucket lifecycle configuration")

		// Extract lifecycle block
		lifecycleStart := strings.Index(contentStr, `resource "aws_s3_bucket_lifecycle_configuration" "source"`)
		require.NotEqual(t, -1, lifecycleStart, "Source bucket lifecycle should exist")

		lifecycleEnd := findResourceBlockEnd(contentStr, lifecycleStart)
		lifecycleBlock := contentStr[lifecycleStart:lifecycleEnd]

		// Verify lifecycle rule is enabled
		assert.Contains(t, lifecycleBlock, `status = "Enabled"`,
			"Lifecycle rule should be enabled")

		// Verify transition to Glacier
		assert.Contains(t, lifecycleBlock, `storage_class = "GLACIER"`,
			"Should transition to Glacier storage class")
		assert.Contains(t, lifecycleBlock, `days          = var.lifecycle_glacier_transition_days`,
			"Glacier transition should be configurable")

		// Verify transition to Deep Archive
		assert.Contains(t, lifecycleBlock, `storage_class = "DEEP_ARCHIVE"`,
			"Should transition to Deep Archive storage class")
		assert.Contains(t, lifecycleBlock, `days          = var.lifecycle_deep_archive_transition_days`,
			"Deep Archive transition should be configurable")

		// Verify noncurrent version transitions
		assert.Contains(t, lifecycleBlock, `noncurrent_version_transition {`,
			"Should have noncurrent version transition")
		assert.Contains(t, lifecycleBlock, `noncurrent_days = 30`,
			"Should transition noncurrent versions after 30 days")

		// Verify noncurrent version expiration
		assert.Contains(t, lifecycleBlock, `noncurrent_version_expiration {`,
			"Should have noncurrent version expiration")
		assert.Contains(t, lifecycleBlock, `noncurrent_days = 90`,
			"Should expire noncurrent versions after 90 days")
	})

	// Test Destination Bucket Lifecycle Policy
	t.Run("Destination Bucket Lifecycle Policy", func(t *testing.T) {
		// Verify lifecycle configuration is defined
		assert.Contains(t, contentStr, `resource "aws_s3_bucket_lifecycle_configuration" "destination"`,
			"Should define destination bucket lifecycle configuration")

		// Extract lifecycle block
		lifecycleStart := strings.Index(contentStr, `resource "aws_s3_bucket_lifecycle_configuration" "destination"`)
		require.NotEqual(t, -1, lifecycleStart, "Destination bucket lifecycle should exist")

		lifecycleEnd := findResourceBlockEnd(contentStr, lifecycleStart)
		lifecycleBlock := contentStr[lifecycleStart:lifecycleEnd]

		// Verify lifecycle rule is enabled
		assert.Contains(t, lifecycleBlock, `status = "Enabled"`,
			"Lifecycle rule should be enabled")

		// Verify transition to Glacier
		assert.Contains(t, lifecycleBlock, `storage_class = "GLACIER"`,
			"Should transition to Glacier storage class")

		// Verify transition to Deep Archive
		assert.Contains(t, lifecycleBlock, `storage_class = "DEEP_ARCHIVE"`,
			"Should transition to Deep Archive storage class")
	})

	// Test lifecycle variable configuration
	t.Run("Lifecycle Variable Configuration", func(t *testing.T) {
		variablesFile := filepath.Join(s3ModuleDir, "variables.tf")
		varContent, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		varStr := string(varContent)

		// Verify lifecycle variables exist
		assert.Contains(t, varStr, `variable "lifecycle_glacier_transition_days"`,
			"Should have lifecycle_glacier_transition_days variable")
		assert.Contains(t, varStr, `variable "lifecycle_deep_archive_transition_days"`,
			"Should have lifecycle_deep_archive_transition_days variable")

		// Extract Glacier transition variable block
		glacierVarStart := strings.Index(varStr, `variable "lifecycle_glacier_transition_days"`)
		require.NotEqual(t, -1, glacierVarStart, "lifecycle_glacier_transition_days variable should exist")

		glacierVarEnd := findResourceBlockEnd(varStr, glacierVarStart)
		glacierVarBlock := varStr[glacierVarStart:glacierVarEnd]

		// Verify default value
		assert.Contains(t, glacierVarBlock, `default     = 90`,
			"Glacier transition should default to 90 days")

		// Verify validation
		assert.Contains(t, glacierVarBlock, `validation {`,
			"Glacier transition should have validation")
		assert.Contains(t, glacierVarBlock, `>= 30`,
			"Glacier transition should be at least 30 days")

		// Extract Deep Archive transition variable block
		deepArchiveVarStart := strings.Index(varStr, `variable "lifecycle_deep_archive_transition_days"`)
		require.NotEqual(t, -1, deepArchiveVarStart, "lifecycle_deep_archive_transition_days variable should exist")

		deepArchiveVarEnd := findResourceBlockEnd(varStr, deepArchiveVarStart)
		deepArchiveVarBlock := varStr[deepArchiveVarStart:deepArchiveVarEnd]

		// Verify default value
		assert.Contains(t, deepArchiveVarBlock, `default     = 180`,
			"Deep Archive transition should default to 180 days")

		// Verify validation
		assert.Contains(t, deepArchiveVarBlock, `validation {`,
			"Deep Archive transition should have validation")
		assert.Contains(t, deepArchiveVarBlock, `>= 90`,
			"Deep Archive transition should be at least 90 days")
	})
}

// TestS3PipelineModuleOutputs tests that S3 Pipeline module exposes required outputs
// Validates: Requirements 12.4
func TestS3PipelineModuleOutputs(t *testing.T) {
	t.Parallel()

	s3ModuleDir := "../../modules/ai-workload/s3-pipeline"
	outputsFile := filepath.Join(s3ModuleDir, "outputs.tf")

	content, err := os.ReadFile(outputsFile)
	require.NoError(t, err, "Should be able to read outputs.tf")

	contentStr := string(content)

	// Verify required outputs for source bucket
	sourceOutputs := []string{
		"source_bucket_id",
		"source_bucket_arn",
		"source_bucket_domain_name",
	}

	for _, output := range sourceOutputs {
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

	// Verify required outputs for destination bucket
	destinationOutputs := []string{
		"destination_bucket_id",
		"destination_bucket_arn",
		"destination_bucket_domain_name",
	}

	for _, output := range destinationOutputs {
		assert.Contains(t, contentStr, `output "`+output+`"`,
			"Should define %s output", output)
	}

	// Verify replication outputs
	replicationOutputs := []string{
		"replication_role_arn",
		"replication_enabled",
	}

	for _, output := range replicationOutputs {
		assert.Contains(t, contentStr, `output "`+output+`"`,
			"Should define %s output", output)
	}
}
