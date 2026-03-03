package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 23: Security Group Default Deny
// Feature: aws-bedrock-rag-deployment, Property 23: Security Group Default Deny
// Validates: Requirements 5.10
//
// For any security group created by the module, inbound rules should follow a default-deny pattern,
// only allowing traffic from explicitly trusted sources.
func TestProperty23_SecurityGroupDefaultDeny(t *testing.T) {
	t.Parallel()

	// Read the security groups module main.tf
	mainFile := filepath.Join("../../modules/network/security-groups", "main.tf")
	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read security-groups main.tf")

	contentStr := string(content)

	// Test cases for each security group
	testCases := []struct {
		name                string
		sgResourceName      string
		shouldHaveIngress   bool
		allowedSources      []string
		description         string
	}{
		{
			name:              "Lambda Security Group",
			sgResourceName:    `resource "aws_security_group" "lambda"`,
			shouldHaveIngress: false,
			allowedSources:    []string{},
			description:       "Lambda SG should have no ingress rules (default deny all inbound)",
		},
		{
			name:              "OpenSearch Security Group",
			sgResourceName:    `resource "aws_security_group" "opensearch"`,
			shouldHaveIngress: true,
			allowedSources:    []string{"security_groups", "var.vpc_cidr", "var.peer_vpc_cidr"},
			description:       "OpenSearch SG should only allow from Lambda SG and VPC CIDRs",
		},
		{
			name:              "VPC Endpoints Security Group",
			sgResourceName:    `resource "aws_security_group" "vpc_endpoints"`,
			shouldHaveIngress: true,
			allowedSources:    []string{"var.vpc_cidr", "var.peer_vpc_cidr"},
			description:       "VPC Endpoints SG should only allow from VPC and peer VPC CIDRs",
		},
	}

	for _, tc := range testCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			// Extract the security group block
			sgBlock := extractSecurityGroupBlock(contentStr, tc.sgResourceName)
			require.NotEmpty(t, sgBlock, "Should find security group resource: %s", tc.sgResourceName)

			if !tc.shouldHaveIngress {
				// Verify NO ingress rules are defined (default deny)
				assert.NotContains(t, sgBlock, "ingress {", "%s should not have any ingress rules", tc.name)
				assert.Contains(t, sgBlock, "# Default deny inbound", "%s should have comment about default deny", tc.name)
			} else {
				// Verify ingress rules only allow from trusted sources
				assert.Contains(t, sgBlock, "ingress {", "%s should have ingress rules", tc.name)

				// Check that all ingress rules specify trusted sources
				ingressBlocks := extractIngressBlocks(sgBlock)
				require.NotEmpty(t, ingressBlocks, "%s should have at least one ingress block", tc.name)

				for _, ingressBlock := range ingressBlocks {
					// Verify ingress has description
					assert.Contains(t, ingressBlock, "description", "Ingress rule should have description")

					// Verify ingress specifies trusted source
					hasTrustedSource := false
					for _, source := range tc.allowedSources {
						if strings.Contains(ingressBlock, source) {
							hasTrustedSource = true
							break
						}
					}
					assert.True(t, hasTrustedSource, "Ingress rule should specify trusted source from: %v", tc.allowedSources)

					// Verify no wildcard CIDR (0.0.0.0/0) in ingress
					if strings.Contains(ingressBlock, "cidr_blocks") {
						assert.NotContains(t, ingressBlock, `"0.0.0.0/0"`, "Ingress should not allow from 0.0.0.0/0")
					}
				}
			}

			// Verify egress rules exist (security groups need egress for functionality)
			assert.Contains(t, sgBlock, "egress {", "%s should have egress rules", tc.name)
		})
	}
}

// TestProperty23_NoUnrestrictedIngressRules verifies that no security group
// allows unrestricted inbound access from the internet
func TestProperty23_NoUnrestrictedIngressRules(t *testing.T) {
	t.Parallel()

	mainFile := filepath.Join("../../modules/network/security-groups", "main.tf")
	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read security-groups main.tf")

	contentStr := string(content)

	// Find all ingress blocks
	lines := strings.Split(contentStr, "\n")
	inIngressBlock := false
	ingressLineNumber := 0

	for i, line := range lines {
		trimmed := strings.TrimSpace(line)

		if strings.Contains(trimmed, "ingress {") {
			inIngressBlock = true
			ingressLineNumber = i + 1
			continue
		}

		if inIngressBlock && trimmed == "}" {
			inIngressBlock = false
			continue
		}

		// Check for unrestricted CIDR in ingress blocks
		if inIngressBlock && strings.Contains(trimmed, `cidr_blocks`) && strings.Contains(trimmed, `"0.0.0.0/0"`) {
			t.Errorf("Line %d: Ingress rule should not allow unrestricted access from 0.0.0.0/0", ingressLineNumber)
		}
	}
}

// TestProperty23_IngressRulesHaveDescriptions verifies that all ingress rules
// have descriptions explaining their purpose
func TestProperty23_IngressRulesHaveDescriptions(t *testing.T) {
	t.Parallel()

	mainFile := filepath.Join("../../modules/network/security-groups", "main.tf")
	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read security-groups main.tf")

	contentStr := string(content)

	// Extract all ingress blocks
	ingressBlocks := extractAllIngressBlocks(contentStr)

	for i, block := range ingressBlocks {
		// Skip dynamic ingress blocks (they inherit description from the parent)
		if strings.Contains(block, "dynamic \"ingress\"") {
			continue
		}

		assert.Contains(t, block, "description", "Ingress block %d should have a description field", i+1)
	}
}

// TestProperty23_SecurityGroupsHaveDescriptions verifies that all security groups
// have meaningful descriptions
func TestProperty23_SecurityGroupsHaveDescriptions(t *testing.T) {
	t.Parallel()

	mainFile := filepath.Join("../../modules/network/security-groups", "main.tf")
	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read security-groups main.tf")

	contentStr := string(content)

	// Find all security group resources
	sgResources := []string{
		`resource "aws_security_group" "lambda"`,
		`resource "aws_security_group" "opensearch"`,
		`resource "aws_security_group" "vpc_endpoints"`,
	}

	for _, sgResource := range sgResources {
		assert.Contains(t, contentStr, sgResource, "Should define security group: %s", sgResource)

		sgBlock := extractSecurityGroupBlock(contentStr, sgResource)
		assert.Contains(t, sgBlock, "description", "Security group should have description field")
		assert.NotContains(t, sgBlock, `description = ""`, "Security group description should not be empty")
	}
}

// TestProperty23_IngressPortRestrictions verifies that ingress rules only allow
// specific ports (not all ports)
func TestProperty23_IngressPortRestrictions(t *testing.T) {
	t.Parallel()

	mainFile := filepath.Join("../../modules/network/security-groups", "main.tf")
	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read security-groups main.tf")

	contentStr := string(content)

	// Extract all ingress blocks
	ingressBlocks := extractAllIngressBlocks(contentStr)

	for i, block := range ingressBlocks {
		// Skip dynamic blocks
		if strings.Contains(block, "dynamic \"ingress\"") {
			continue
		}

		// Verify specific ports are defined (not -1 for all protocols)
		if strings.Contains(block, "from_port") {
			// Should not allow all ports (0 to 65535 or protocol -1 in ingress)
			if strings.Contains(block, "from_port   = 0") && strings.Contains(block, "to_port     = 0") {
				assert.Contains(t, block, `protocol    = "tcp"`, "Ingress block %d: If using port 0, should specify protocol", i+1)
			}

			// Should not use protocol -1 (all protocols) in ingress
			assert.NotContains(t, block, `protocol    = "-1"`, "Ingress block %d should not allow all protocols", i+1)
		}
	}
}

// Helper function to extract a security group block from content
func extractSecurityGroupBlock(content, sgResourceName string) string {
	lines := strings.Split(content, "\n")
	inBlock := false
	blockLines := []string{}
	braceCount := 0

	for _, line := range lines {
		if strings.Contains(line, sgResourceName) {
			inBlock = true
		}

		if inBlock {
			blockLines = append(blockLines, line)

			// Count braces to find the end of the block
			braceCount += strings.Count(line, "{")
			braceCount -= strings.Count(line, "}")

			if braceCount == 0 && len(blockLines) > 1 {
				break
			}
		}
	}

	return strings.Join(blockLines, "\n")
}

// Helper function to extract ingress blocks from a security group block
func extractIngressBlocks(sgBlock string) []string {
	var blocks []string
	lines := strings.Split(sgBlock, "\n")
	inIngressBlock := false
	currentBlock := []string{}
	braceCount := 0

	for _, line := range lines {
		trimmed := strings.TrimSpace(line)

		if strings.HasPrefix(trimmed, "ingress {") {
			inIngressBlock = true
			currentBlock = []string{line}
			braceCount = 1
			continue
		}

		if inIngressBlock {
			currentBlock = append(currentBlock, line)
			braceCount += strings.Count(line, "{")
			braceCount -= strings.Count(line, "}")

			if braceCount == 0 {
				blocks = append(blocks, strings.Join(currentBlock, "\n"))
				inIngressBlock = false
				currentBlock = []string{}
			}
		}
	}

	return blocks
}

// Helper function to extract all ingress blocks from content
func extractAllIngressBlocks(content string) []string {
	var blocks []string
	lines := strings.Split(content, "\n")
	inIngressBlock := false
	inDynamicIngress := false
	currentBlock := []string{}
	braceCount := 0

	for _, line := range lines {
		trimmed := strings.TrimSpace(line)

		// Check for dynamic ingress
		if strings.Contains(trimmed, `dynamic "ingress"`) {
			inDynamicIngress = true
			currentBlock = []string{line}
			braceCount = 0
			continue
		}

		// Check for regular ingress
		if strings.HasPrefix(trimmed, "ingress {") && !inDynamicIngress {
			inIngressBlock = true
			currentBlock = []string{line}
			braceCount = 1
			continue
		}

		if inIngressBlock || inDynamicIngress {
			currentBlock = append(currentBlock, line)
			braceCount += strings.Count(line, "{")
			braceCount -= strings.Count(line, "}")

			if braceCount == 0 && len(currentBlock) > 1 {
				blocks = append(blocks, strings.Join(currentBlock, "\n"))
				inIngressBlock = false
				inDynamicIngress = false
				currentBlock = []string{}
			}
		}
	}

	return blocks
}
