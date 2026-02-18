package integration

import (
	"fmt"
	"testing"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/s3"
	"github.com/gruntwork-io/terratest/modules/random"
	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	test_structure "github.com/gruntwork-io/terratest/modules/test-structure"
)

// TestS3CrossRegionReplication tests S3 cross-region replication functionality
func TestS3CrossRegionReplication(t *testing.T) {
	t.Parallel()

	workingDir := "../../environments/app-layer/bedrock-rag"
	
	defer test_structure.RunTestStage(t, "cleanup", func() {
		terraformOptions := test_structure.LoadTerraformOptions(t, workingDir)
		
		// Clean up test objects before destroying
		sourceBucket := terraform.Output(t, terraformOptions, "source_bucket_id")
		destBucket := terraform.Output(t, terraformOptions, "destination_bucket_id")
		
		cleanupS3Objects(t, sourceBucket, "ap-northeast-2")
		cleanupS3Objects(t, destBucket, "us-east-1")
		
		terraform.Destroy(t, terraformOptions)
	})

	test_structure.RunTestStage(t, "setup", func() {
		uniqueID := random.UniqueId()
		
		terraformOptions := &terraform.Options{
			TerraformDir: workingDir,
			Vars: map[string]interface{}{
				"source_bucket_name":      fmt.Sprintf("bos-ai-test-seoul-%s", uniqueID),
				"destination_bucket_name": fmt.Sprintf("bos-ai-test-us-%s", uniqueID),
				"environment":             "test",
				"project":                 "BOS-AI-RAG-Test",
			},
			NoColor: true,
		}

		test_structure.SaveTerraformOptions(t, workingDir, terraformOptions)
		terraform.InitAndApply(t, terraformOptions)
	})

	test_structure.RunTestStage(t, "validate", func() {
		terraformOptions := test_structure.LoadTerraformOptions(t, workingDir)

		// Test 1: Verify S3 buckets exist
		t.Run("S3BucketsExist", func(t *testing.T) {
			sourceBucket := terraform.Output(t, terraformOptions, "source_bucket_id")
			destBucket := terraform.Output(t, terraformOptions, "destination_bucket_id")
			
			assert.NotEmpty(t, sourceBucket, "Source bucket ID should not be empty")
			assert.NotEmpty(t, destBucket, "Destination bucket ID should not be empty")
			
			// Verify source bucket exists
			seoulS3Client := createS3Client(t, "ap-northeast-2")
			_, err := seoulS3Client.HeadBucket(&s3.HeadBucketInput{
				Bucket: aws.String(sourceBucket),
			})
			require.NoError(t, err, "Source bucket should exist")
			
			// Verify destination bucket exists
			usS3Client := createS3Client(t, "us-east-1")
			_, err = usS3Client.HeadBucket(&s3.HeadBucketInput{
				Bucket: aws.String(destBucket),
			})
			require.NoError(t, err, "Destination bucket should exist")
		})

		// Test 2: Verify S3 versioning is enabled
		t.Run("S3VersioningEnabled", func(t *testing.T) {
			sourceBucket := terraform.Output(t, terraformOptions, "source_bucket_id")
			destBucket := terraform.Output(t, terraformOptions, "destination_bucket_id")
			
			// Check source bucket versioning
			seoulS3Client := createS3Client(t, "ap-northeast-2")
			sourceVersioning, err := seoulS3Client.GetBucketVersioning(&s3.GetBucketVersioningInput{
				Bucket: aws.String(sourceBucket),
			})
			require.NoError(t, err, "Failed to get source bucket versioning")
			assert.Equal(t, "Enabled", *sourceVersioning.Status, "Source bucket versioning should be enabled")
			
			// Check destination bucket versioning
			usS3Client := createS3Client(t, "us-east-1")
			destVersioning, err := usS3Client.GetBucketVersioning(&s3.GetBucketVersioningInput{
				Bucket: aws.String(destBucket),
			})
			require.NoError(t, err, "Failed to get destination bucket versioning")
			assert.Equal(t, "Enabled", *destVersioning.Status, "Destination bucket versioning should be enabled")
		})

		// Test 3: Verify S3 encryption is enabled
		t.Run("S3EncryptionEnabled", func(t *testing.T) {
			sourceBucket := terraform.Output(t, terraformOptions, "source_bucket_id")
			destBucket := terraform.Output(t, terraformOptions, "destination_bucket_id")
			
			// Check source bucket encryption
			seoulS3Client := createS3Client(t, "ap-northeast-2")
			sourceEncryption, err := seoulS3Client.GetBucketEncryption(&s3.GetBucketEncryptionInput{
				Bucket: aws.String(sourceBucket),
			})
			require.NoError(t, err, "Failed to get source bucket encryption")
			assert.NotNil(t, sourceEncryption.ServerSideEncryptionConfiguration, "Source bucket should have encryption configured")
			
			// Check destination bucket encryption
			usS3Client := createS3Client(t, "us-east-1")
			destEncryption, err := usS3Client.GetBucketEncryption(&s3.GetBucketEncryptionInput{
				Bucket: aws.String(destBucket),
			})
			require.NoError(t, err, "Failed to get destination bucket encryption")
			assert.NotNil(t, destEncryption.ServerSideEncryptionConfiguration, "Destination bucket should have encryption configured")
		})

		// Test 4: Verify replication configuration
		t.Run("ReplicationConfigured", func(t *testing.T) {
			sourceBucket := terraform.Output(t, terraformOptions, "source_bucket_id")
			
			seoulS3Client := createS3Client(t, "ap-northeast-2")
			replication, err := seoulS3Client.GetBucketReplication(&s3.GetBucketReplicationInput{
				Bucket: aws.String(sourceBucket),
			})
			require.NoError(t, err, "Failed to get bucket replication configuration")
			assert.NotNil(t, replication.ReplicationConfiguration, "Replication configuration should exist")
			assert.NotEmpty(t, replication.ReplicationConfiguration.Rules, "Replication rules should be configured")
		})

		// Test 5: Test actual replication
		t.Run("ObjectReplication", func(t *testing.T) {
			sourceBucket := terraform.Output(t, terraformOptions, "source_bucket_id")
			destBucket := terraform.Output(t, terraformOptions, "destination_bucket_id")
			
			// Upload test object to source bucket
			testKey := fmt.Sprintf("test-documents/test-%s.txt", random.UniqueId())
			testContent := "This is a test document for replication testing"
			
			seoulS3Client := createS3Client(t, "ap-northeast-2")
			_, err := seoulS3Client.PutObject(&s3.PutObjectInput{
				Bucket: aws.String(sourceBucket),
				Key:    aws.String(testKey),
				Body:   aws.ReadSeekCloser([]byte(testContent)),
			})
			require.NoError(t, err, "Failed to upload test object to source bucket")
			
			// Wait for replication (can take a few minutes)
			t.Log("Waiting for replication to complete (up to 5 minutes)...")
			usS3Client := createS3Client(t, "us-east-1")
			
			maxRetries := 30
			retryInterval := 10 * time.Second
			replicated := false
			
			for i := 0; i < maxRetries; i++ {
				_, err := usS3Client.HeadObject(&s3.HeadObjectInput{
					Bucket: aws.String(destBucket),
					Key:    aws.String(testKey),
				})
				
				if err == nil {
					replicated = true
					t.Logf("Object replicated successfully after %d seconds", i*10)
					break
				}
				
				if i < maxRetries-1 {
					time.Sleep(retryInterval)
				}
			}
			
			assert.True(t, replicated, "Object should be replicated to destination bucket within 5 minutes")
			
			// Verify replicated object content
			if replicated {
				getResult, err := usS3Client.GetObject(&s3.GetObjectInput{
					Bucket: aws.String(destBucket),
					Key:    aws.String(testKey),
				})
				require.NoError(t, err, "Failed to get replicated object")
				
				// Read content
				buf := make([]byte, len(testContent))
				_, err = getResult.Body.Read(buf)
				getResult.Body.Close()
				
				if err != nil && err.Error() != "EOF" {
					require.NoError(t, err, "Failed to read replicated object content")
				}
				
				assert.Equal(t, testContent, string(buf), "Replicated object content should match original")
			}
		})

		// Test 6: Verify public access is blocked
		t.Run("PublicAccessBlocked", func(t *testing.T) {
			sourceBucket := terraform.Output(t, terraformOptions, "source_bucket_id")
			destBucket := terraform.Output(t, terraformOptions, "destination_bucket_id")
			
			// Check source bucket
			seoulS3Client := createS3Client(t, "ap-northeast-2")
			sourcePublicAccess, err := seoulS3Client.GetPublicAccessBlock(&s3.GetPublicAccessBlockInput{
				Bucket: aws.String(sourceBucket),
			})
			require.NoError(t, err, "Failed to get source bucket public access block")
			assert.True(t, *sourcePublicAccess.PublicAccessBlockConfiguration.BlockPublicAcls, "Source bucket should block public ACLs")
			assert.True(t, *sourcePublicAccess.PublicAccessBlockConfiguration.BlockPublicPolicy, "Source bucket should block public policies")
			
			// Check destination bucket
			usS3Client := createS3Client(t, "us-east-1")
			destPublicAccess, err := usS3Client.GetPublicAccessBlock(&s3.GetPublicAccessBlockInput{
				Bucket: aws.String(destBucket),
			})
			require.NoError(t, err, "Failed to get destination bucket public access block")
			assert.True(t, *destPublicAccess.PublicAccessBlockConfiguration.BlockPublicAcls, "Destination bucket should block public ACLs")
			assert.True(t, *destPublicAccess.PublicAccessBlockConfiguration.BlockPublicPolicy, "Destination bucket should block public policies")
		})
	})
}

// Helper functions

func createS3Client(t *testing.T, region string) *s3.S3 {
	sess := createAWSSession(t, region)
	return s3.New(sess)
}

func cleanupS3Objects(t *testing.T, bucket string, region string) {
	s3Client := createS3Client(t, region)
	
	// List all objects
	listResult, err := s3Client.ListObjectsV2(&s3.ListObjectsV2Input{
		Bucket: aws.String(bucket),
	})
	
	if err != nil {
		t.Logf("Warning: Failed to list objects in bucket %s: %v", bucket, err)
		return
	}
	
	// Delete all objects
	for _, obj := range listResult.Contents {
		_, err := s3Client.DeleteObject(&s3.DeleteObjectInput{
			Bucket: aws.String(bucket),
			Key:    obj.Key,
		})
		
		if err != nil {
			t.Logf("Warning: Failed to delete object %s: %v", *obj.Key, err)
		}
	}
	
	// List and delete all versions (for versioned buckets)
	versionResult, err := s3Client.ListObjectVersions(&s3.ListObjectVersionsInput{
		Bucket: aws.String(bucket),
	})
	
	if err != nil {
		t.Logf("Warning: Failed to list object versions in bucket %s: %v", bucket, err)
		return
	}
	
	for _, version := range versionResult.Versions {
		_, err := s3Client.DeleteObject(&s3.DeleteObjectInput{
			Bucket:    aws.String(bucket),
			Key:       version.Key,
			VersionId: version.VersionId,
		})
		
		if err != nil {
			t.Logf("Warning: Failed to delete version %s: %v", *version.VersionId, err)
		}
	}
	
	for _, marker := range versionResult.DeleteMarkers {
		_, err := s3Client.DeleteObject(&s3.DeleteObjectInput{
			Bucket:    aws.String(bucket),
			Key:       marker.Key,
			VersionId: marker.VersionId,
		})
		
		if err != nil {
			t.Logf("Warning: Failed to delete marker %s: %v", *marker.VersionId, err)
		}
	}
}
