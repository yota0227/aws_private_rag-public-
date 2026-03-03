package unit

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// TestVPNImportBlockSyntax tests that the import block syntax is correct
// Validates: Requirements 7.1, 7.2
func TestVPNImportBlockSyntax(t *testing.T) {
	t.Parallel()

	networkLayerDir := "../../environments/network-layer"
	mainFile := filepath.Join(networkLayerDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Verify import block structure is present (even if commented)
	assert.Contains(t, contentStr, `import {`, "Should contain import block structure")
	assert.Contains(t, contentStr, `to = aws_vpn_gateway.existing`, "Import block should target aws_vpn_gateway.existing")
	assert.Contains(t, contentStr, `id =`, "Import block should specify VPN Gateway ID")

	// Verify VPN Gateway resource is defined
	assert.Contains(t, contentStr, `resource "aws_vpn_gateway" "existing"`, "Should define VPN Gateway resource")

	// Extract VPN Gateway resource block
	vpnStart := strings.Index(contentStr, `resource "aws_vpn_gateway" "existing"`)
	require.NotEqual(t, -1, vpnStart, "VPN Gateway resource should exist")

	vpnEnd := findResourceBlockEnd(contentStr, vpnStart)
	vpnBlock := contentStr[vpnStart:vpnEnd]

	// Verify VPN Gateway configuration
	assert.Contains(t, vpnBlock, `vpc_id`, "VPN Gateway should specify vpc_id")
	assert.Contains(t, vpnBlock, `module.vpc_seoul.vpc_id`, "VPN Gateway should be attached to Seoul VPC")
	assert.Contains(t, vpnBlock, `amazon_side_asn`, "VPN Gateway should specify Amazon side ASN")
	assert.Contains(t, vpnBlock, `tags`, "VPN Gateway should have tags")
	assert.Contains(t, vpnBlock, `Imported = "true"`, "VPN Gateway should be tagged as imported")
}

// TestVPNGatewayAttachment tests that VPN Gateway is attached to Seoul VPC
// Validates: Requirements 7.2, 7.3
func TestVPNGatewayAttachment(t *testing.T) {
	t.Parallel()

	networkLayerDir := "../../environments/network-layer"
	mainFile := filepath.Join(networkLayerDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Verify VPN Gateway attachment resource exists
	assert.Contains(t, contentStr, `resource "aws_vpn_gateway_attachment" "seoul"`,
		"Should define VPN Gateway attachment resource")

	// Extract attachment resource block
	attachStart := strings.Index(contentStr, `resource "aws_vpn_gateway_attachment" "seoul"`)
	require.NotEqual(t, -1, attachStart, "VPN Gateway attachment resource should exist")

	attachEnd := findResourceBlockEnd(contentStr, attachStart)
	attachBlock := contentStr[attachStart:attachEnd]

	// Verify attachment configuration
	assert.Contains(t, attachBlock, `vpc_id         = module.vpc_seoul.vpc_id`,
		"Attachment should reference Seoul VPC")
	assert.Contains(t, attachBlock, `vpn_gateway_id = aws_vpn_gateway.existing.id`,
		"Attachment should reference VPN Gateway")
	assert.Contains(t, attachBlock, `depends_on`, "Attachment should have dependencies")
}

// TestVPNGatewayRoutePropagation tests that route propagation is configured
// Validates: Requirements 7.3
func TestVPNGatewayRoutePropagation(t *testing.T) {
	t.Parallel()

	networkLayerDir := "../../environments/network-layer"
	mainFile := filepath.Join(networkLayerDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Verify route propagation resource exists
	assert.Contains(t, contentStr, `resource "aws_vpn_gateway_route_propagation" "seoul_private"`,
		"Should define VPN Gateway route propagation resource")

	// Extract route propagation resource block
	propStart := strings.Index(contentStr, `resource "aws_vpn_gateway_route_propagation" "seoul_private"`)
	require.NotEqual(t, -1, propStart, "Route propagation resource should exist")

	propEnd := findResourceBlockEnd(contentStr, propStart)
	propBlock := contentStr[propStart:propEnd]

	// Verify route propagation configuration
	assert.Contains(t, propBlock, `count`, "Route propagation should use count for multiple route tables")
	assert.Contains(t, propBlock, `vpn_gateway_id = aws_vpn_gateway.existing.id`,
		"Route propagation should reference VPN Gateway")
	assert.Contains(t, propBlock, `route_table_id = module.vpc_seoul.private_route_table_ids[count.index]`,
		"Route propagation should reference Seoul private route tables")
	assert.Contains(t, propBlock, `depends_on`, "Route propagation should have dependencies")
}

// TestVPNGatewayOutputs tests that VPN Gateway outputs are defined
// Validates: Requirements 7.8, 12.4
func TestVPNGatewayOutputs(t *testing.T) {
	t.Parallel()

	networkLayerDir := "../../environments/network-layer"
	outputsFile := filepath.Join(networkLayerDir, "outputs.tf")

	content, err := os.ReadFile(outputsFile)
	require.NoError(t, err, "Should be able to read outputs.tf")

	contentStr := string(content)

	// Verify VPN Gateway outputs are defined
	requiredOutputs := []struct {
		name        string
		description string
	}{
		{"vpn_gateway_id", "ID of the VPN Gateway"},
		{"vpn_gateway_state", "State of the VPN Gateway"},
		{"vpn_gateway_amazon_side_asn", "Amazon side ASN"},
		{"vpn_gateway_attachment_state", "State of the VPN Gateway attachment"},
	}

	for _, output := range requiredOutputs {
		assert.Contains(t, contentStr, `output "`+output.name+`"`,
			"Should define %s output", output.name)

		// Extract output block
		outputStart := strings.Index(contentStr, `output "`+output.name+`"`)
		if outputStart != -1 {
			outputEnd := findResourceBlockEnd(contentStr, outputStart)
			outputBlock := contentStr[outputStart:outputEnd]

			assert.Contains(t, outputBlock, `description`, "Output %s should have description", output.name)
			assert.Contains(t, outputBlock, `value`, "Output %s should have value", output.name)
		}
	}
}

// TestVPNGatewayTags tests that VPN Gateway has proper tags
// Validates: Requirements 7.7, 11.5
func TestVPNGatewayTags(t *testing.T) {
	t.Parallel()

	networkLayerDir := "../../environments/network-layer"
	mainFile := filepath.Join(networkLayerDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Extract VPN Gateway resource block
	vpnStart := strings.Index(contentStr, `resource "aws_vpn_gateway" "existing"`)
	require.NotEqual(t, -1, vpnStart, "VPN Gateway resource should exist")

	vpnEnd := findResourceBlockEnd(contentStr, vpnStart)
	vpnBlock := contentStr[vpnStart:vpnEnd]

	// Verify tags are merged with common tags
	assert.Contains(t, vpnBlock, `tags = merge(`, "VPN Gateway should merge tags")
	assert.Contains(t, vpnBlock, `local.seoul_tags`, "VPN Gateway should use Seoul tags")

	// Verify specific tags
	assert.Contains(t, vpnBlock, `Name`, "VPN Gateway should have Name tag")
	assert.Contains(t, vpnBlock, `Imported = "true"`, "VPN Gateway should have Imported tag")
	assert.Contains(t, vpnBlock, `Purpose`, "VPN Gateway should have Purpose tag")
}

// TestVPNGatewayDependencies tests that VPN Gateway has proper dependencies
// Validates: Requirements 7.3
func TestVPNGatewayDependencies(t *testing.T) {
	t.Parallel()

	networkLayerDir := "../../environments/network-layer"
	mainFile := filepath.Join(networkLayerDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Extract VPN Gateway resource block
	vpnStart := strings.Index(contentStr, `resource "aws_vpn_gateway" "existing"`)
	require.NotEqual(t, -1, vpnStart, "VPN Gateway resource should exist")

	vpnEnd := findResourceBlockEnd(contentStr, vpnStart)
	vpnBlock := contentStr[vpnStart:vpnEnd]

	// Verify VPN Gateway depends on Seoul VPC
	assert.Contains(t, vpnBlock, `depends_on`, "VPN Gateway should have dependencies")
	assert.Contains(t, vpnBlock, `module.vpc_seoul`, "VPN Gateway should depend on Seoul VPC")

	// Extract VPN Gateway attachment block
	attachStart := strings.Index(contentStr, `resource "aws_vpn_gateway_attachment" "seoul"`)
	require.NotEqual(t, -1, attachStart, "VPN Gateway attachment should exist")

	attachEnd := findResourceBlockEnd(contentStr, attachStart)
	attachBlock := contentStr[attachStart:attachEnd]

	// Verify attachment depends on VPC and VPN Gateway
	assert.Contains(t, attachBlock, `depends_on`, "Attachment should have dependencies")
	assert.Contains(t, attachBlock, `module.vpc_seoul`, "Attachment should depend on Seoul VPC")
	assert.Contains(t, attachBlock, `aws_vpn_gateway.existing`, "Attachment should depend on VPN Gateway")

	// Extract route propagation block
	propStart := strings.Index(contentStr, `resource "aws_vpn_gateway_route_propagation" "seoul_private"`)
	require.NotEqual(t, -1, propStart, "Route propagation should exist")

	propEnd := findResourceBlockEnd(contentStr, propStart)
	propBlock := contentStr[propStart:propEnd]

	// Verify route propagation depends on attachment
	assert.Contains(t, propBlock, `depends_on`, "Route propagation should have dependencies")
	assert.Contains(t, propBlock, `aws_vpn_gateway_attachment.seoul`, "Route propagation should depend on attachment")
}

// TestVPNImportDocumentation tests that import documentation is present
// Validates: Requirements 7.8
func TestVPNImportDocumentation(t *testing.T) {
	t.Parallel()

	networkLayerDir := "../../environments/network-layer"
	mainFile := filepath.Join(networkLayerDir, "main.tf")

	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Verify import documentation is present
	assert.Contains(t, contentStr, "Import existing VPN Gateway", "Should have import section header")
	assert.Contains(t, contentStr, "Requirements: 7.1, 7.2, 7.3", "Should reference requirements")
	assert.Contains(t, contentStr, "aws ec2 describe-vpn-gateways", "Should document AWS CLI command")
	assert.Contains(t, contentStr, "terraform plan", "Should document Terraform plan step")
	assert.Contains(t, contentStr, "terraform apply", "Should document Terraform apply step")

	// Verify helper script exists
	scriptPath := "../../scripts/identify-vpn-gateway.sh"
	_, err = os.Stat(scriptPath)
	assert.NoError(t, err, "Helper script should exist")

	if err == nil {
		// Verify script is executable
		info, err := os.Stat(scriptPath)
		require.NoError(t, err)
		mode := info.Mode()
		assert.True(t, mode&0111 != 0, "Script should be executable")

		// Verify script content
		scriptContent, err := os.ReadFile(scriptPath)
		require.NoError(t, err)
		scriptStr := string(scriptContent)

		assert.Contains(t, scriptStr, "describe-vpn-gateways", "Script should use describe-vpn-gateways")
		assert.Contains(t, scriptStr, "ap-northeast-2", "Script should target Seoul region")
		assert.Contains(t, scriptStr, "Import Instructions", "Script should provide import instructions")
	}
}

// Helper function to find the end of a resource block
func findResourceBlockEnd(content string, startPos int) int {
	if startPos == -1 {
		return -1
	}

	braceCount := 0
	inResource := false

	for i := startPos; i < len(content); i++ {
		if content[i] == '{' {
			braceCount++
			inResource = true
		} else if content[i] == '}' {
			braceCount--
			if inResource && braceCount == 0 {
				return i + 1
			}
		}
	}

	return len(content)
}
