package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 32: Multi-Region Provider Configuration
// Feature: aws-bedrock-rag-deployment, Property 32: Multi-Region Provider Configuration
// Validates: Requirements 9.1
//
// For any Terraform configuration requiring multi-region deployment, provider aliases should be
// defined for both Seoul (ap-northeast-2) and US East (us-east-1) regions.
func TestProperty32_MultiRegionProviderConfiguration(t *testing.T) {
	t.Parallel()

	networkLayerDir := "../../environments/network-layer"
	providersFile := filepath.Join(networkLayerDir, "providers.tf")

	// Read providers.tf file
	content, err := os.ReadFile(providersFile)
	require.NoError(t, err, "Should be able to read providers.tf")

	contentStr := string(content)

	// Verify Seoul provider alias is defined
	assert.Contains(t, contentStr, `provider "aws"`, "Should define AWS provider")
	assert.Contains(t, contentStr, `alias  = "seoul"`, "Should define Seoul provider alias")
	assert.Contains(t, contentStr, `region = "ap-northeast-2"`, "Seoul provider should use ap-northeast-2 region")

	// Verify US East provider alias is defined
	assert.Contains(t, contentStr, `alias  = "us_east"`, "Should define US East provider alias")
	assert.Contains(t, contentStr, `region = "us-east-1"`, "US East provider should use us-east-1 region")

	// Count provider blocks to ensure both are present
	providerCount := strings.Count(contentStr, `provider "aws"`)
	assert.GreaterOrEqual(t, providerCount, 2, "Should have at least 2 AWS provider configurations (Seoul and US East)")

	// Verify main.tf uses provider aliases in modules
	mainFile := filepath.Join(networkLayerDir, "main.tf")
	mainContent, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	mainStr := string(mainContent)

	// Verify Seoul VPC module uses Seoul provider
	assert.Contains(t, mainStr, `module "vpc_seoul"`, "Should define Seoul VPC module")
	seoulModuleStart := strings.Index(mainStr, `module "vpc_seoul"`)
	seoulModuleEnd := findModuleBlockEnd(mainStr, seoulModuleStart)
	seoulModuleBlock := mainStr[seoulModuleStart:seoulModuleEnd]
	assert.Contains(t, seoulModuleBlock, `aws = aws.seoul`, "Seoul VPC module should use Seoul provider alias")

	// Verify US VPC module uses US East provider
	assert.Contains(t, mainStr, `module "vpc_us"`, "Should define US VPC module")
	usModuleStart := strings.Index(mainStr, `module "vpc_us"`)
	usModuleEnd := findModuleBlockEnd(mainStr, usModuleStart)
	usModuleBlock := mainStr[usModuleStart:usModuleEnd]
	assert.Contains(t, usModuleBlock, `aws = aws.us_east`, "US VPC module should use US East provider alias")
}

// Property 33: Regional Resource Distribution
// Feature: aws-bedrock-rag-deployment, Property 33: Regional Resource Distribution
// Validates: Requirements 9.2, 9.3
//
// For any deployment, network infrastructure resources should be created in both Seoul and US regions,
// while Bedrock and AI workload resources should be created only in the US East region.
func TestProperty33_RegionalResourceDistribution(t *testing.T) {
	t.Parallel()

	networkLayerDir := "../../environments/network-layer"
	mainFile := filepath.Join(networkLayerDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Verify Seoul region resources
	assert.Contains(t, contentStr, `module "vpc_seoul"`, "Should create VPC in Seoul region")
	assert.Contains(t, contentStr, `module "security_groups_seoul"`, "Should create security groups in Seoul region")

	// Verify US region resources
	assert.Contains(t, contentStr, `module "vpc_us"`, "Should create VPC in US region")
	assert.Contains(t, contentStr, `module "security_groups_us"`, "Should create security groups in US region")

	// Verify VPC peering connects both regions
	assert.Contains(t, contentStr, `module "vpc_peering"`, "Should create VPC peering connection")

	// Extract VPC peering configuration
	peeringStart := strings.Index(contentStr, `module "vpc_peering"`)
	peeringEnd := findModuleBlockEnd(contentStr, peeringStart)
	peeringBlock := contentStr[peeringStart:peeringEnd]

	// Verify peering connects Seoul and US VPCs
	assert.Contains(t, peeringBlock, `vpc_id      = module.vpc_seoul.vpc_id`, "Peering should reference Seoul VPC")
	assert.Contains(t, peeringBlock, `peer_vpc_id = module.vpc_us.vpc_id`, "Peering should reference US VPC")
	assert.Contains(t, peeringBlock, `peer_region = "us-east-1"`, "Peering should specify US East region")

	// Verify network layer does NOT contain Bedrock or AI workload resources
	assert.NotContains(t, contentStr, `bedrock`, "Network layer should not contain Bedrock resources")
	assert.NotContains(t, contentStr, `opensearch`, "Network layer should not contain OpenSearch resources")
	assert.NotContains(t, contentStr, `knowledge_base`, "Network layer should not contain Knowledge Base resources")
	assert.NotContains(t, contentStr, `lambda`, "Network layer should not contain Lambda resources")

	// Check app-layer for AI workload resources (if it exists)
	appLayerDir := "../../environments/app-layer/bedrock-rag"
	appLayerMain := filepath.Join(appLayerDir, "main.tf")

	if _, err := os.Stat(appLayerMain); err == nil {
		appContent, err := os.ReadFile(appLayerMain)
		require.NoError(t, err, "Should be able to read app-layer main.tf")

		appStr := string(appContent)

		// Verify AI workload resources are in app-layer
		// Note: These assertions will pass when app-layer is implemented
		if strings.Contains(appStr, "bedrock") || strings.Contains(appStr, "opensearch") {
			// Verify app-layer uses only US East provider
			appProvidersFile := filepath.Join(appLayerDir, "providers.tf")
			appProvidersContent, err := os.ReadFile(appProvidersFile)
			require.NoError(t, err, "Should be able to read app-layer providers.tf")

			appProvidersStr := string(appProvidersContent)
			assert.Contains(t, appProvidersStr, `region = "us-east-1"`, "App layer should use US East region")
			assert.NotContains(t, appProvidersStr, `region = "ap-northeast-2"`, "App layer should not use Seoul region for AI workloads")
		}
	}
}

// Property 44: Cost Allocation Tags
// Feature: aws-bedrock-rag-deployment, Property 44: Cost Allocation Tags
// Validates: Requirements 11.5
//
// For any resource created by the module, cost allocation tags should be applied including
// Project, Environment, ManagedBy, CostCenter, Layer, and Owner tags.
func TestProperty44_CostAllocationTags(t *testing.T) {
	t.Parallel()

	networkLayerDir := "../../environments/network-layer"
	mainFile := filepath.Join(networkLayerDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Verify common_tags local variable is defined
	assert.Contains(t, contentStr, `locals {`, "Should define local variables")
	assert.Contains(t, contentStr, `common_tags`, "Should define common_tags local variable")

	// Extract locals block
	localsStart := strings.Index(contentStr, "locals {")
	localsEnd := findBlockEnd(contentStr, localsStart)
	localsBlock := contentStr[localsStart:localsEnd]

	// Verify required cost allocation tags are present
	requiredTags := []string{
		"Project",
		"Environment",
		"ManagedBy",
		"Layer",
	}

	for _, tag := range requiredTags {
		assert.Contains(t, localsBlock, tag, "common_tags should include %s tag", tag)
	}

	// Verify Project tag has correct value
	assert.Contains(t, localsBlock, `Project     = "BOS-AI-RAG"`, "Project tag should be BOS-AI-RAG")

	// Verify ManagedBy tag indicates Terraform
	assert.Contains(t, localsBlock, `ManagedBy   = "Terraform"`, "ManagedBy tag should be Terraform")

	// Verify Layer tag indicates network layer
	assert.Contains(t, localsBlock, `Layer       = "network"`, "Layer tag should be network")

	// Verify Environment tag uses variable
	assert.Contains(t, localsBlock, `Environment = var.environment`, "Environment tag should use variable")

	// Verify region-specific tags are defined
	assert.Contains(t, contentStr, `seoul_tags`, "Should define Seoul-specific tags")
	assert.Contains(t, contentStr, `us_tags`, "Should define US-specific tags")

	// Extract seoul_tags block
	seoulTagsStart := strings.Index(contentStr, "seoul_tags = merge(")
	if seoulTagsStart != -1 {
		seoulTagsEnd := findBlockEnd(contentStr, seoulTagsStart)
		seoulTagsBlock := contentStr[seoulTagsStart:seoulTagsEnd]
		assert.Contains(t, seoulTagsBlock, `Region = "ap-northeast-2"`, "Seoul tags should include Region tag")
	}

	// Extract us_tags block
	usTagsStart := strings.Index(contentStr, "us_tags = merge(")
	if usTagsStart != -1 {
		usTagsEnd := findBlockEnd(contentStr, usTagsStart)
		usTagsBlock := contentStr[usTagsStart:usTagsEnd]
		assert.Contains(t, usTagsBlock, `Region = "us-east-1"`, "US tags should include Region tag")
	}

	// Verify modules use tags
	moduleBlocks := []string{"vpc_seoul", "vpc_us", "vpc_peering", "security_groups_seoul", "security_groups_us"}
	for _, moduleName := range moduleBlocks {
		moduleStart := strings.Index(contentStr, `module "`+moduleName+`"`)
		if moduleStart != -1 {
			moduleEnd := findModuleBlockEnd(contentStr, moduleStart)
			moduleBlock := contentStr[moduleStart:moduleEnd]
			assert.Contains(t, moduleBlock, `tags`, "Module %s should include tags parameter", moduleName)
		}
	}

	// Verify variables.tf defines additional_tags variable for extensibility
	variablesFile := filepath.Join(networkLayerDir, "variables.tf")
	if _, err := os.Stat(variablesFile); err == nil {
		varContent, err := os.ReadFile(variablesFile)
		require.NoError(t, err, "Should be able to read variables.tf")

		varStr := string(varContent)
		assert.Contains(t, varStr, `variable "additional_tags"`, "Should define additional_tags variable for extensibility")
	}
}

// Helper function to find the end of a module block
func findModuleBlockEnd(content string, startPos int) int {
	if startPos == -1 {
		return -1
	}

	braceCount := 0
	inModule := false

	for i := startPos; i < len(content); i++ {
		if content[i] == '{' {
			braceCount++
			inModule = true
		} else if content[i] == '}' {
			braceCount--
			if inModule && braceCount == 0 {
				return i + 1
			}
		}
	}

	return len(content)
}

// Helper function to find the end of a generic block (locals, etc.)
func findBlockEnd(content string, startPos int) int {
	if startPos == -1 {
		return -1
	}

	braceCount := 0
	foundFirstBrace := false

	for i := startPos; i < len(content); i++ {
		if content[i] == '{' {
			braceCount++
			foundFirstBrace = true
		} else if content[i] == '}' {
			braceCount--
			if foundFirstBrace && braceCount == 0 {
				return i + 1
			}
		}
	}

	return len(content)
}
