//go:build integration

package integration_test

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Terraform plan JSON structures

type TerraformPlan struct {
	ResourceChanges []ResourceChange `json:"resource_changes"`
}

type ResourceChange struct {
	Address      string `json:"address"`
	Type         string `json:"type"`
	Name         string `json:"name"`
	Change       Change `json:"change"`
	Mode         string `json:"mode"`
	ProviderName string `json:"provider_name"`
}

type Change struct {
	Actions []string               `json:"actions"`
	After   map[string]interface{} `json:"after"`
	Before  map[string]interface{} `json:"before"`
}

// loadPlan reads and parses the Terraform plan JSON file.
func loadPlan(t *testing.T) TerraformPlan {
	t.Helper()

	planPath := os.Getenv("LLM_GATEWAY_PLAN_JSON")
	if planPath == "" {
		planPath = "../../plan.json"
	}

	data, err := os.ReadFile(planPath)
	require.NoError(t, err, "Failed to read plan JSON from %s", planPath)

	var plan TerraformPlan
	err = json.Unmarshal(data, &plan)
	require.NoError(t, err, "Failed to parse plan JSON")

	return plan
}

// isLLMGatewayResource returns true if the resource address belongs to the LLM Gateway project.
func isLLMGatewayResource(address string) bool {
	prefixes := []string{"llm_gateway", "litellm", "mcp", "squid"}
	lower := strings.ToLower(address)
	for _, prefix := range prefixes {
		if strings.Contains(lower, prefix) {
			return true
		}
	}
	return false
}

// TestNoDestructiveChanges verifies that no existing (non-LLM Gateway) resources
// have destructive actions (delete or replace) in the plan.
// Validates: Requirements 21.1-21.6
func TestNoDestructiveChanges(t *testing.T) {
	plan := loadPlan(t)

	destructiveActions := []string{"delete", "replace"}

	for _, rc := range plan.ResourceChanges {
		if isLLMGatewayResource(rc.Address) {
			continue
		}

		for _, action := range rc.Change.Actions {
			for _, destructive := range destructiveActions {
				if strings.Contains(strings.ToLower(action), destructive) {
					assert.Failf(t, "Destructive change detected",
						"Resource %s has destructive action %q — existing resources must not be modified",
						rc.Address, action)
				}
			}
		}
	}
}

// TestRequiredTags verifies that all new resources in the plan have the required tags:
// Project=BOS-AI, Environment=prod, ManagedBy=terraform.
// Validates: Requirements 21.1-21.6, 22.1-22.3
func TestRequiredTags(t *testing.T) {
	plan := loadPlan(t)

	requiredTags := map[string]string{
		"Project":     "BOS-AI",
		"Environment": "prod",
		"ManagedBy":   "terraform",
	}

	for _, rc := range plan.ResourceChanges {
		// Only check resources being created or updated
		hasCreate := false
		for _, action := range rc.Change.Actions {
			if action == "create" || action == "update" {
				hasCreate = true
				break
			}
		}
		if !hasCreate {
			continue
		}

		// Only check resources that support tags
		if rc.Change.After == nil {
			continue
		}

		tagsRaw, hasTags := rc.Change.After["tags"]
		if !hasTags {
			continue
		}

		tags, ok := tagsRaw.(map[string]interface{})
		if !ok {
			continue
		}

		for key, expectedValue := range requiredTags {
			actualValue, exists := tags[key]
			assert.Truef(t, exists,
				"Resource %s is missing required tag %q", rc.Address, key)
			if exists {
				assert.Equalf(t, expectedValue, actualValue,
					"Resource %s tag %q has wrong value", rc.Address, key)
			}
		}
	}
}

// TestEBSEncryption verifies that all EBS volumes in the plan have encryption enabled.
// Validates: Requirements 22.2
func TestEBSEncryption(t *testing.T) {
	plan := loadPlan(t)

	for _, rc := range plan.ResourceChanges {
		if rc.Change.After == nil {
			continue
		}

		// Check aws_ebs_volume resources
		if rc.Type == "aws_ebs_volume" {
			encrypted, exists := rc.Change.After["encrypted"]
			assert.Truef(t, exists && encrypted == true,
				"EBS volume %s must have encrypted=true", rc.Address)
		}

		// Check root_block_device and ebs_block_device in aws_instance
		if rc.Type == "aws_instance" {
			checkBlockDeviceEncryption(t, rc.Address, rc.Change.After, "root_block_device")
			checkBlockDeviceEncryption(t, rc.Address, rc.Change.After, "ebs_block_device")
		}
	}
}

// checkBlockDeviceEncryption checks that block devices within an instance have encryption enabled.
func checkBlockDeviceEncryption(t *testing.T, address string, after map[string]interface{}, blockType string) {
	t.Helper()

	blockRaw, exists := after[blockType]
	if !exists {
		return
	}

	blocks, ok := blockRaw.([]interface{})
	if !ok {
		return
	}

	for i, blockRaw := range blocks {
		block, ok := blockRaw.(map[string]interface{})
		if !ok {
			continue
		}
		encrypted, exists := block["encrypted"]
		assert.Truef(t, exists && encrypted == true,
			"Instance %s %s[%d] must have encrypted=true", address, blockType, i)
	}
}

// TestNoPublicIP verifies that no EC2 instances in the plan have public IPs assigned.
// Validates: Requirements 22.3
func TestNoPublicIP(t *testing.T) {
	plan := loadPlan(t)

	for _, rc := range plan.ResourceChanges {
		if rc.Type != "aws_instance" {
			continue
		}
		if rc.Change.After == nil {
			continue
		}

		publicIP, exists := rc.Change.After["associate_public_ip_address"]
		if exists {
			assert.Equalf(t, false, publicIP,
				"Instance %s must have associate_public_ip_address=false", rc.Address)
		}
	}
}

// TestIMDSv2 verifies that all EC2 instances enforce IMDSv2 (http_tokens="required").
// Validates: Requirements 22.1
func TestIMDSv2(t *testing.T) {
	plan := loadPlan(t)

	for _, rc := range plan.ResourceChanges {
		if rc.Type != "aws_instance" {
			continue
		}
		if rc.Change.After == nil {
			continue
		}

		metadataRaw, exists := rc.Change.After["metadata_options"]
		if !exists {
			assert.Failf(t, "Missing metadata_options",
				"Instance %s must have metadata_options with http_tokens=required", rc.Address)
			continue
		}

		// metadata_options can be a list or a map depending on plan format
		switch metadata := metadataRaw.(type) {
		case []interface{}:
			for _, item := range metadata {
				opts, ok := item.(map[string]interface{})
				if !ok {
					continue
				}
				httpTokens, exists := opts["http_tokens"]
				assert.Truef(t, exists && httpTokens == "required",
					"Instance %s must have http_tokens=required (IMDSv2)", rc.Address)
			}
		case map[string]interface{}:
			httpTokens, exists := metadata["http_tokens"]
			assert.Truef(t, exists && httpTokens == "required",
				"Instance %s must have http_tokens=required (IMDSv2)", rc.Address)
		default:
			assert.Failf(t, "Unexpected metadata_options format",
				"Instance %s has unexpected metadata_options type", rc.Address)
		}
	}
}
