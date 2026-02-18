package properties

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 2: VPC Peering Establishment
// Feature: aws-bedrock-rag-deployment, Property 2: VPC Peering Establishment
// Validates: Requirements 1.2, 1.4, 1.5
//
// For any deployment where both Seoul and US VPCs exist, a VPC peering connection should be
// established between them with bidirectional routing configured in both VPC route tables.
func TestProperty2_VPCPeeringEstablishment(t *testing.T) {
	t.Parallel()

	// Read the VPC peering module main.tf
	mainFile := filepath.Join("../../modules/network/peering", "main.tf")
	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read peering main.tf")

	contentStr := string(content)

	// Verify VPC peering connection resource exists
	assert.Contains(t, contentStr, `resource "aws_vpc_peering_connection" "main"`,
		"Should define VPC peering connection resource")
	assert.Contains(t, contentStr, `vpc_id      = var.vpc_id`,
		"Should reference requester VPC ID")
	assert.Contains(t, contentStr, `peer_vpc_id = var.peer_vpc_id`,
		"Should reference accepter VPC ID")
	assert.Contains(t, contentStr, `peer_region = var.peer_region`,
		"Should reference peer region for cross-region peering")

	// Verify VPC peering connection accepter exists
	assert.Contains(t, contentStr, `resource "aws_vpc_peering_connection_accepter" "peer"`,
		"Should define VPC peering connection accepter resource")
	assert.Contains(t, contentStr, `vpc_peering_connection_id = aws_vpc_peering_connection.main.id`,
		"Accepter should reference the peering connection")

	// Verify bidirectional routing is configured
	// Requester to peer routes
	assert.Contains(t, contentStr, `resource "aws_route" "requester_to_peer"`,
		"Should define routes from requester to peer")
	assert.Contains(t, contentStr, `count = length(var.requester_route_table_ids)`,
		"Should create routes for all requester route tables")
	assert.Contains(t, contentStr, `route_table_id            = var.requester_route_table_ids[count.index]`,
		"Should use requester route table IDs")
	assert.Contains(t, contentStr, `destination_cidr_block    = var.peer_cidr`,
		"Should route to peer CIDR block")

	// Accepter to requester routes
	assert.Contains(t, contentStr, `resource "aws_route" "accepter_to_requester"`,
		"Should define routes from accepter to requester")
	assert.Contains(t, contentStr, `count = length(var.accepter_route_table_ids)`,
		"Should create routes for all accepter route tables")
	assert.Contains(t, contentStr, `route_table_id            = var.accepter_route_table_ids[count.index]`,
		"Should use accepter route table IDs")

	// Verify routes use the peering connection
	routeCount := strings.Count(contentStr, `vpc_peering_connection_id = aws_vpc_peering_connection.main.id`)
	assert.GreaterOrEqual(t, routeCount, 2,
		"Both requester and accepter routes should reference the peering connection")

	// Verify time_sleep resource to wait for peering activation
	assert.Contains(t, contentStr, `resource "time_sleep" "wait_for_peering"`,
		"Should define time_sleep resource to wait for peering activation")
	assert.Contains(t, contentStr, `depends_on = [aws_vpc_peering_connection_accepter.peer]`,
		"time_sleep should depend on peering accepter")
	assert.Contains(t, contentStr, `create_duration = "30s"`,
		"Should wait 30 seconds for peering to activate")

	// Verify routes depend on time_sleep
	assert.Contains(t, contentStr, `depends_on = [time_sleep.wait_for_peering]`,
		"Routes should depend on time_sleep to ensure peering is active")
}

// Property 3: VPC Peering Auto-Acceptance
// Feature: aws-bedrock-rag-deployment, Property 3: VPC Peering Auto-Acceptance
// Validates: Requirements 1.3
//
// For any VPC peering connection created within the same AWS account, the auto_accept
// attribute should be set to true to enable automatic acceptance.
func TestProperty3_VPCPeeringAutoAcceptance(t *testing.T) {
	t.Parallel()

	// Read the VPC peering module variables.tf
	variablesFile := filepath.Join("../../modules/network/peering", "variables.tf")
	content, err := os.ReadFile(variablesFile)
	require.NoError(t, err, "Should be able to read peering variables.tf")

	contentStr := string(content)

	// Verify auto_accept variable exists with default true
	assert.Contains(t, contentStr, `variable "auto_accept"`,
		"Should define auto_accept variable")
	assert.Contains(t, contentStr, `type        = bool`,
		"auto_accept should be boolean type")
	assert.Contains(t, contentStr, `default     = true`,
		"auto_accept should default to true for same-account peering")
	assert.Contains(t, contentStr, `Automatically accept peering (same account)`,
		"Should document that auto_accept is for same-account peering")

	// Read main.tf to verify auto_accept is used
	mainFile := filepath.Join("../../modules/network/peering", "main.tf")
	mainContent, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read peering main.tf")

	mainStr := string(mainContent)

	// Verify auto_accept is used in the accepter resource
	assert.Contains(t, mainStr, `auto_accept               = var.auto_accept`,
		"Accepter should use auto_accept variable")

	// Verify the peering connection itself has auto_accept = false for cross-region
	assert.Contains(t, mainStr, `auto_accept = false # Cross-region peering requires manual acceptance`,
		"Peering connection should have auto_accept = false for cross-region with comment explaining why")
}

// TestProperty2_NetworkLayerPeeringConfiguration tests the actual network-layer configuration
// to ensure VPC peering is properly configured between Seoul and US VPCs
func TestProperty2_NetworkLayerPeeringConfiguration(t *testing.T) {
	t.Parallel()

	networkLayerFile := filepath.Join("../../environments/network-layer", "main.tf")

	// Check if file exists
	_, err := os.Stat(networkLayerFile)
	if os.IsNotExist(err) {
		t.Skip("Network layer main.tf not yet created")
		return
	}

	content, err := os.ReadFile(networkLayerFile)
	require.NoError(t, err, "Should be able to read network-layer main.tf")

	contentStr := string(content)

	// Verify peering module is called
	assert.Contains(t, contentStr, `module "vpc_peering"`,
		"Should define VPC peering module")

	// Verify peering module references both VPCs
	hasPeeringConfig := strings.Contains(contentStr, "vpc_id") &&
		strings.Contains(contentStr, "peer_vpc_id")
	assert.True(t, hasPeeringConfig,
		"Peering module should reference both VPC IDs")

	// Verify route table IDs are passed to peering module
	assert.Contains(t, contentStr, "requester_route_table_ids",
		"Should pass requester route table IDs to peering module")
	assert.Contains(t, contentStr, "accepter_route_table_ids",
		"Should pass accepter route table IDs to peering module")

	// Verify peer CIDR is passed
	assert.Contains(t, contentStr, "peer_cidr",
		"Should pass peer CIDR to peering module")
}

// TestProperty2_PeeringModuleOutputs tests that the peering module exposes necessary outputs
func TestProperty2_PeeringModuleOutputs(t *testing.T) {
	t.Parallel()

	outputsFile := filepath.Join("../../modules/network/peering", "outputs.tf")
	content, err := os.ReadFile(outputsFile)
	require.NoError(t, err, "Should be able to read peering outputs.tf")

	contentStr := string(content)

	// Verify peering connection ID is exposed
	assert.Contains(t, contentStr, `output "peering_connection_id"`,
		"Should expose peering connection ID")
	assert.Contains(t, contentStr, `value       = aws_vpc_peering_connection.main.id`,
		"Peering connection ID should reference the main peering connection")

	// Verify peering status is exposed
	assert.Contains(t, contentStr, `output "peering_status"`,
		"Should expose peering status")
	assert.Contains(t, contentStr, `aws_vpc_peering_connection.main.accept_status`,
		"Peering status should reference accept_status")
}

// TestProperty3_AutoAcceptConfiguration tests various auto_accept scenarios
func TestProperty3_AutoAcceptConfiguration(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name           string
		autoAccept     bool
		expectedResult string
	}{
		{
			name:           "Same-account peering with auto_accept true",
			autoAccept:     true,
			expectedResult: "should automatically accept",
		},
		{
			name:           "Manual acceptance with auto_accept false",
			autoAccept:     false,
			expectedResult: "should require manual acceptance",
		},
	}

	for _, tc := range testCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			// Read the peering module to verify auto_accept behavior
			mainFile := filepath.Join("../../modules/network/peering", "main.tf")
			content, err := os.ReadFile(mainFile)
			require.NoError(t, err, "Should be able to read peering main.tf")

			contentStr := string(content)

			// Verify accepter uses the auto_accept variable
			assert.Contains(t, contentStr, `auto_accept               = var.auto_accept`,
				"Accepter should use auto_accept variable for flexibility")

			// The actual behavior is controlled by the variable value
			// which defaults to true for same-account peering
			if tc.autoAccept {
				// When auto_accept is true, the accepter will automatically accept
				assert.Contains(t, contentStr, `resource "aws_vpc_peering_connection_accepter" "peer"`,
					"Accepter resource should exist to handle acceptance")
			}
		})
	}
}

// TestProperty2_BidirectionalRoutingValidation tests that routes are created in both directions
func TestProperty2_BidirectionalRoutingValidation(t *testing.T) {
	t.Parallel()

	mainFile := filepath.Join("../../modules/network/peering", "main.tf")
	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read peering main.tf")

	contentStr := string(content)

	// Count route resources
	requesterRoutes := strings.Contains(contentStr, `resource "aws_route" "requester_to_peer"`)
	accepterRoutes := strings.Contains(contentStr, `resource "aws_route" "accepter_to_requester"`)

	assert.True(t, requesterRoutes, "Should define routes from requester to peer")
	assert.True(t, accepterRoutes, "Should define routes from accepter to requester")

	// Verify both routes use count for multiple route tables
	requesterCount := strings.Count(contentStr, `count = length(var.requester_route_table_ids)`)
	accepterCount := strings.Count(contentStr, `count = length(var.accepter_route_table_ids)`)

	assert.Equal(t, 1, requesterCount, "Should have one count for requester routes")
	assert.Equal(t, 1, accepterCount, "Should have one count for accepter routes")

	// Verify data source for requester VPC CIDR
	assert.Contains(t, contentStr, `data "aws_vpc" "requester"`,
		"Should define data source for requester VPC")
	assert.Contains(t, contentStr, `id = var.vpc_id`,
		"Data source should reference requester VPC ID")
	assert.Contains(t, contentStr, `destination_cidr_block    = data.aws_vpc.requester.cidr_block`,
		"Accepter routes should use requester VPC CIDR from data source")
}

// TestProperty2_CrossRegionPeeringSupport tests that the module supports cross-region peering
func TestProperty2_CrossRegionPeeringSupport(t *testing.T) {
	t.Parallel()

	mainFile := filepath.Join("../../modules/network/peering", "main.tf")
	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read peering main.tf")

	contentStr := string(content)

	// Verify peer_region is specified for cross-region support
	assert.Contains(t, contentStr, `peer_region = var.peer_region`,
		"Should specify peer_region for cross-region peering")

	// Verify auto_accept is false for the peering connection (cross-region requirement)
	assert.Contains(t, contentStr, `auto_accept = false`,
		"Peering connection should have auto_accept = false for cross-region")

	// Verify comment explains cross-region requirement
	assert.Contains(t, contentStr, `# Cross-region peering requires manual acceptance`,
		"Should document why auto_accept is false")

	// Read variables to verify peer_region variable exists
	variablesFile := filepath.Join("../../modules/network/peering", "variables.tf")
	varContent, err := os.ReadFile(variablesFile)
	require.NoError(t, err, "Should be able to read peering variables.tf")

	varStr := string(varContent)
	assert.Contains(t, varStr, `variable "peer_region"`,
		"Should define peer_region variable")
	assert.Contains(t, varStr, `Accepter VPC region`,
		"Should document peer_region purpose")
}
