package integration

import (
	"testing"
	"time"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/ec2"
	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	test_structure "github.com/gruntwork-io/terratest/modules/test-structure"
)

// TestVPCPeeringConnectivity tests VPC peering connection establishment and routing
func TestVPCPeeringConnectivity(t *testing.T) {
	t.Parallel()

	// Setup test directory
	workingDir := "../../environments/network-layer"
	
	// Save data to disk for cleanup
	defer test_structure.RunTestStage(t, "cleanup", func() {
		terraformOptions := test_structure.LoadTerraformOptions(t, workingDir)
		terraform.Destroy(t, terraformOptions)
	})

	test_structure.RunTestStage(t, "setup", func() {
		terraformOptions := &terraform.Options{
			TerraformDir: workingDir,
			Vars: map[string]interface{}{
				"seoul_vpc_cidr":              "10.10.0.0/16",
				"us_vpc_cidr":                 "10.20.0.0/16",
				"seoul_private_subnet_cidrs":  []string{"10.10.1.0/24", "10.10.2.0/24"},
				"us_private_subnet_cidrs":     []string{"10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"},
				"seoul_availability_zones":    []string{"ap-northeast-2a", "ap-northeast-2c"},
				"us_availability_zones":       []string{"us-east-1a", "us-east-1b", "us-east-1c"},
				"environment":                 "test",
				"project":                     "BOS-AI-RAG-Test",
			},
			NoColor: true,
		}

		test_structure.SaveTerraformOptions(t, workingDir, terraformOptions)
		terraform.InitAndApply(t, terraformOptions)
	})

	test_structure.RunTestStage(t, "validate", func() {
		terraformOptions := test_structure.LoadTerraformOptions(t, workingDir)

		// Test 1: Verify VPC Peering Connection exists
		t.Run("VPCPeeringConnectionExists", func(t *testing.T) {
			peeringConnectionID := terraform.Output(t, terraformOptions, "peering_connection_id")
			assert.NotEmpty(t, peeringConnectionID, "VPC Peering Connection ID should not be empty")
		})

		// Test 2: Verify VPC Peering Connection is active
		t.Run("VPCPeeringConnectionActive", func(t *testing.T) {
			peeringConnectionID := terraform.Output(t, terraformOptions, "peering_connection_id")
			
			// Create EC2 client for Seoul region
			ec2Client := createEC2Client(t, "ap-northeast-2")
			
			// Describe peering connection
			input := &ec2.DescribeVpcPeeringConnectionsInput{
				VpcPeeringConnectionIds: []*string{aws.String(peeringConnectionID)},
			}
			
			result, err := ec2Client.DescribeVpcPeeringConnections(input)
			require.NoError(t, err, "Failed to describe VPC peering connection")
			require.Len(t, result.VpcPeeringConnections, 1, "Expected exactly one peering connection")
			
			peeringConnection := result.VpcPeeringConnections[0]
			assert.Equal(t, "active", *peeringConnection.Status.Code, "VPC Peering Connection should be active")
		})

		// Test 3: Verify bidirectional routing
		t.Run("BidirectionalRoutingConfigured", func(t *testing.T) {
			seoulVPCID := terraform.Output(t, terraformOptions, "seoul_vpc_id")
			usVPCID := terraform.Output(t, terraformOptions, "us_vpc_id")
			peeringConnectionID := terraform.Output(t, terraformOptions, "peering_connection_id")
			
			// Check Seoul VPC route tables
			seoulEC2Client := createEC2Client(t, "ap-northeast-2")
			seoulRoutes := getRouteTablesForVPC(t, seoulEC2Client, seoulVPCID)
			
			seoulHasPeeringRoute := false
			for _, routeTable := range seoulRoutes {
				for _, route := range routeTable.Routes {
					if route.VpcPeeringConnectionId != nil && *route.VpcPeeringConnectionId == peeringConnectionID {
						if route.DestinationCidrBlock != nil && *route.DestinationCidrBlock == "10.20.0.0/16" {
							seoulHasPeeringRoute = true
							break
						}
					}
				}
			}
			assert.True(t, seoulHasPeeringRoute, "Seoul VPC should have route to US VPC via peering")
			
			// Check US VPC route tables
			usEC2Client := createEC2Client(t, "us-east-1")
			usRoutes := getRouteTablesForVPC(t, usEC2Client, usVPCID)
			
			usHasPeeringRoute := false
			for _, routeTable := range usRoutes {
				for _, route := range routeTable.Routes {
					if route.VpcPeeringConnectionId != nil && *route.VpcPeeringConnectionId == peeringConnectionID {
						if route.DestinationCidrBlock != nil && *route.DestinationCidrBlock == "10.10.0.0/16" {
							usHasPeeringRoute = true
							break
						}
					}
				}
			}
			assert.True(t, usHasPeeringRoute, "US VPC should have route to Seoul VPC via peering")
		})

		// Test 4: Verify VPC CIDR blocks don't overlap
		t.Run("VPCCIDRsDoNotOverlap", func(t *testing.T) {
			seoulVPCCIDR := terraform.Output(t, terraformOptions, "seoul_vpc_cidr")
			usVPCCIDR := terraform.Output(t, terraformOptions, "us_vpc_cidr")
			
			assert.NotEqual(t, seoulVPCCIDR, usVPCCIDR, "VPC CIDRs should not be identical")
			assert.Equal(t, "10.10.0.0/16", seoulVPCCIDR, "Seoul VPC CIDR should be 10.10.0.0/16")
			assert.Equal(t, "10.20.0.0/16", usVPCCIDR, "US VPC CIDR should be 10.20.0.0/16")
		})

		// Test 5: Verify no Internet Gateways attached
		t.Run("NoInternetGatewayAttached", func(t *testing.T) {
			seoulVPCID := terraform.Output(t, terraformOptions, "seoul_vpc_id")
			usVPCID := terraform.Output(t, terraformOptions, "us_vpc_id")
			
			// Check Seoul VPC
			seoulEC2Client := createEC2Client(t, "ap-northeast-2")
			seoulIGWs := getInternetGatewaysForVPC(t, seoulEC2Client, seoulVPCID)
			assert.Empty(t, seoulIGWs, "Seoul VPC should not have Internet Gateway (No-IGW policy)")
			
			// Check US VPC
			usEC2Client := createEC2Client(t, "us-east-1")
			usIGWs := getInternetGatewaysForVPC(t, usEC2Client, usVPCID)
			assert.Empty(t, usIGWs, "US VPC should not have Internet Gateway (No-IGW policy)")
		})

		// Test 6: Verify multi-AZ subnet distribution
		t.Run("MultiAZSubnetDistribution", func(t *testing.T) {
			seoulVPCID := terraform.Output(t, terraformOptions, "seoul_vpc_id")
			usVPCID := terraform.Output(t, terraformOptions, "us_vpc_id")
			
			// Check Seoul VPC subnets
			seoulEC2Client := createEC2Client(t, "ap-northeast-2")
			seoulSubnets := getSubnetsForVPC(t, seoulEC2Client, seoulVPCID)
			seoulAZs := make(map[string]bool)
			for _, subnet := range seoulSubnets {
				seoulAZs[*subnet.AvailabilityZone] = true
			}
			assert.GreaterOrEqual(t, len(seoulAZs), 2, "Seoul VPC should have subnets in at least 2 AZs")
			
			// Check US VPC subnets
			usEC2Client := createEC2Client(t, "us-east-1")
			usSubnets := getSubnetsForVPC(t, usEC2Client, usVPCID)
			usAZs := make(map[string]bool)
			for _, subnet := range usSubnets {
				usAZs[*subnet.AvailabilityZone] = true
			}
			assert.GreaterOrEqual(t, len(usAZs), 2, "US VPC should have subnets in at least 2 AZs")
		})
	})
}

// TestVPCPeeringPerformance tests network latency across VPC peering
func TestVPCPeeringPerformance(t *testing.T) {
	t.Parallel()

	workingDir := "../../environments/network-layer"
	
	test_structure.RunTestStage(t, "validate_performance", func() {
		terraformOptions := test_structure.LoadTerraformOptions(t, workingDir)
		
		// Test: Verify peering connection has acceptable latency
		t.Run("PeeringConnectionLatency", func(t *testing.T) {
			peeringConnectionID := terraform.Output(t, terraformOptions, "peering_connection_id")
			
			// Create EC2 client
			ec2Client := createEC2Client(t, "ap-northeast-2")
			
			// Describe peering connection
			input := &ec2.DescribeVpcPeeringConnectionsInput{
				VpcPeeringConnectionIds: []*string{aws.String(peeringConnectionID)},
			}
			
			start := time.Now()
			_, err := ec2Client.DescribeVpcPeeringConnections(input)
			elapsed := time.Since(start)
			
			require.NoError(t, err, "Failed to describe VPC peering connection")
			assert.Less(t, elapsed.Milliseconds(), int64(5000), "API call should complete within 5 seconds")
		})
	})
}

// Helper functions

func createEC2Client(t *testing.T, region string) *ec2.EC2 {
	sess := createAWSSession(t, region)
	return ec2.New(sess)
}

func getRouteTablesForVPC(t *testing.T, client *ec2.EC2, vpcID string) []*ec2.RouteTable {
	input := &ec2.DescribeRouteTablesInput{
		Filters: []*ec2.Filter{
			{
				Name:   aws.String("vpc-id"),
				Values: []*string{aws.String(vpcID)},
			},
		},
	}
	
	result, err := client.DescribeRouteTables(input)
	require.NoError(t, err, "Failed to describe route tables")
	
	return result.RouteTables
}

func getInternetGatewaysForVPC(t *testing.T, client *ec2.EC2, vpcID string) []*ec2.InternetGateway {
	input := &ec2.DescribeInternetGatewaysInput{
		Filters: []*ec2.Filter{
			{
				Name:   aws.String("attachment.vpc-id"),
				Values: []*string{aws.String(vpcID)},
			},
		},
	}
	
	result, err := client.DescribeInternetGateways(input)
	require.NoError(t, err, "Failed to describe internet gateways")
	
	return result.InternetGateways
}

func getSubnetsForVPC(t *testing.T, client *ec2.EC2, vpcID string) []*ec2.Subnet {
	input := &ec2.DescribeSubnetsInput{
		Filters: []*ec2.Filter{
			{
				Name:   aws.String("vpc-id"),
				Values: []*string{aws.String(vpcID)},
			},
		},
	}
	
	result, err := client.DescribeSubnets(input)
	require.NoError(t, err, "Failed to describe subnets")
	
	return result.Subnets
}
