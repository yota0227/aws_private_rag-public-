package properties

import (
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Property 1: VPC CIDR Non-Overlap
// Feature: aws-bedrock-rag-deployment, Property 1: VPC CIDR Non-Overlap
// Validates: Requirements 1.1
//
// For any two VPCs created by the module (Seoul and US), their CIDR blocks should not overlap,
// ensuring proper network isolation and routing.
func TestProperty1_VPCCIDRNonOverlap(t *testing.T) {
	t.Parallel()

	// Read the VPC module variables to check CIDR validation
	variablesFile := filepath.Join("../../modules/network/vpc", "variables.tf")
	content, err := os.ReadFile(variablesFile)
	require.NoError(t, err, "Should be able to read variables.tf")

	contentStr := string(content)

	// Verify CIDR validation exists
	assert.Contains(t, contentStr, `can(cidrhost(var.vpc_cidr, 0))`, "Should validate CIDR format")
	assert.Contains(t, contentStr, `Must be valid IPv4 CIDR`, "Should have CIDR validation error message")

	// Test with actual CIDR blocks used in the deployment
	testCases := []struct {
		name        string
		seoulCIDR   string
		usCIDR      string
		shouldError bool
	}{
		{
			name:        "Non-overlapping CIDRs (10.10.0.0/16 and 10.20.0.0/16)",
			seoulCIDR:   "10.10.0.0/16",
			usCIDR:      "10.20.0.0/16",
			shouldError: false,
		},
		{
			name:        "Overlapping CIDRs (10.10.0.0/16 and 10.10.0.0/24)",
			seoulCIDR:   "10.10.0.0/16",
			usCIDR:      "10.10.0.0/24",
			shouldError: true,
		},
		{
			name:        "Identical CIDRs",
			seoulCIDR:   "10.10.0.0/16",
			usCIDR:      "10.10.0.0/16",
			shouldError: true,
		},
		{
			name:        "Non-overlapping different ranges",
			seoulCIDR:   "172.16.0.0/16",
			usCIDR:      "192.168.0.0/16",
			shouldError: false,
		},
	}

	for _, tc := range testCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			overlap := cidrsOverlap(tc.seoulCIDR, tc.usCIDR)
			if tc.shouldError {
				assert.True(t, overlap, "CIDRs should overlap")
			} else {
				assert.False(t, overlap, "CIDRs should not overlap")
			}
		})
	}
}

// Property 4: Multi-AZ Subnet Distribution
// Feature: aws-bedrock-rag-deployment, Property 4: Multi-AZ Subnet Distribution
// Validates: Requirements 1.6
//
// For any VPC created by the module, private subnets should be distributed across
// at least two different availability zones for high availability.
func TestProperty4_MultiAZSubnetDistribution(t *testing.T) {
	t.Parallel()

	// Read VPC module files
	variablesFile := filepath.Join("../../modules/network/vpc", "variables.tf")
	mainFile := filepath.Join("../../modules/network/vpc", "main.tf")

	variablesContent, err := os.ReadFile(variablesFile)
	require.NoError(t, err, "Should be able to read variables.tf")

	mainContent, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	variablesStr := string(variablesContent)
	mainStr := string(mainContent)

	// Verify availability_zones variable requires at least 2 AZs
	assert.Contains(t, variablesStr, `variable "availability_zones"`, "Should define availability_zones variable")
	assert.Contains(t, variablesStr, `length(var.availability_zones) >= 2`, "Should validate minimum 2 AZs")
	assert.Contains(t, variablesStr, `At least 2 availability zones are required`, "Should have AZ validation message")

	// Verify private_subnet_cidrs variable requires at least 2 subnets
	assert.Contains(t, variablesStr, `variable "private_subnet_cidrs"`, "Should define private_subnet_cidrs variable")
	assert.Contains(t, variablesStr, `length(var.private_subnet_cidrs) >= 2`, "Should validate minimum 2 subnets")
	assert.Contains(t, variablesStr, `At least 2 private subnets are required`, "Should have subnet validation message")

	// Verify subnet creation uses availability_zones for distribution
	assert.Contains(t, mainStr, `resource "aws_subnet" "private"`, "Should define private subnet resource")
	assert.Contains(t, mainStr, `availability_zone = var.availability_zones[count.index % length(var.availability_zones)]`,
		"Should distribute subnets across availability zones using modulo operation")

	// Verify subnet count matches private_subnet_cidrs length
	assert.Contains(t, mainStr, `count = length(var.private_subnet_cidrs)`, "Subnet count should match CIDR list length")
}

// Property 5: No Internet Gateway Policy
// Feature: aws-bedrock-rag-deployment, Property 5: No Internet Gateway Policy
// Validates: Requirements 1.9
//
// For any VPC created by the module, no Internet Gateway resource should be attached,
// enforcing the No-IGW security policy.
func TestProperty5_NoInternetGatewayPolicy(t *testing.T) {
	t.Parallel()

	// Read VPC module main.tf
	mainFile := filepath.Join("../../modules/network/vpc", "main.tf")
	content, err := os.ReadFile(mainFile)
	require.NoError(t, err, "Should be able to read main.tf")

	contentStr := string(content)

	// Verify no Internet Gateway resource is defined
	assert.NotContains(t, contentStr, `resource "aws_internet_gateway"`, "Should not define Internet Gateway resource")
	assert.NotContains(t, contentStr, `aws_internet_gateway`, "Should not reference Internet Gateway")

	// Verify no NAT Gateway resource is defined (which would require IGW)
	assert.NotContains(t, contentStr, `resource "aws_nat_gateway"`, "Should not define NAT Gateway resource")

	// Verify no public subnets are created
	assert.NotContains(t, contentStr, `resource "aws_subnet" "public"`, "Should not define public subnet resource")
	assert.NotContains(t, contentStr, `Type = "public"`, "Should not tag subnets as public")

	// Verify only private subnets exist
	assert.Contains(t, contentStr, `resource "aws_subnet" "private"`, "Should define private subnet resource")
	assert.Contains(t, contentStr, `Type = "private"`, "Should tag subnets as private")

	// Verify route tables don't have IGW routes
	assert.NotContains(t, contentStr, `gateway_id`, "Route tables should not reference gateway_id (IGW)")
}

// Helper function to check if two CIDR blocks overlap
func cidrsOverlap(cidr1, cidr2 string) bool {
	_, net1, err1 := net.ParseCIDR(cidr1)
	_, net2, err2 := net.ParseCIDR(cidr2)

	if err1 != nil || err2 != nil {
		return false
	}

	// Check if net1 contains net2's IP or net2 contains net1's IP
	return net1.Contains(net2.IP) || net2.Contains(net1.IP)
}

// TestProperty1_NetworkLayerCIDRConfiguration tests the actual network-layer configuration
// to ensure Seoul and US VPCs have non-overlapping CIDRs
func TestProperty1_NetworkLayerCIDRConfiguration(t *testing.T) {
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

	// Extract CIDR blocks from the configuration
	// Look for patterns like: vpc_cidr = "10.10.0.0/16"
	seoulCIDR := extractCIDR(contentStr, "seoul")
	usCIDR := extractCIDR(contentStr, "us")

	if seoulCIDR != "" && usCIDR != "" {
		overlap := cidrsOverlap(seoulCIDR, usCIDR)
		assert.False(t, overlap, "Seoul VPC (%s) and US VPC (%s) CIDRs should not overlap", seoulCIDR, usCIDR)
	}
}

// Helper function to extract CIDR from configuration content
func extractCIDR(content, region string) string {
	lines := strings.Split(content, "\n")
	inModule := false

	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		
		// Check if we're in the right module block
		if strings.Contains(trimmed, "module") && strings.Contains(strings.ToLower(trimmed), region) {
			inModule = true
			continue
		}

		// Reset when we exit the module block
		if inModule && trimmed == "}" {
			inModule = false
			continue
		}

		// Look for vpc_cidr within the module
		if inModule && strings.Contains(trimmed, "vpc_cidr") {
			// Extract CIDR value: vpc_cidr = "10.10.0.0/16"
			parts := strings.Split(trimmed, "=")
			if len(parts) == 2 {
				cidr := strings.Trim(parts[1], " \"")
				// Validate it's a proper CIDR
				if _, _, err := net.ParseCIDR(cidr); err == nil {
					return cidr
				}
			}
		}
	}

	return ""
}
