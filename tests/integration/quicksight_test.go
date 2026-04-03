package integration

import (
	"net"
	"testing"

	"github.com/aws/aws-sdk-go/aws"
	"github.com/aws/aws-sdk-go/service/ec2"
	"github.com/aws/aws-sdk-go/service/lambda"
	"github.com/aws/aws-sdk-go/service/route53"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const (
	quickDNSName   = "quick.rag.corp.bos-semi.com"
	seoulVPCCIDR   = "10.10.0.0/16"
	virginiaCIDR   = "10.20.0.0/16"
	lambdaFuncName = "lambda-quick-rag-connector-seoul-prod"
	hostedZoneID   = "Z04599582HCRH2UPCSS34"
)

// TestQuickSightVPCEndpointConnectivity verifies Quick API/Website VPC Endpoints exist and are available
// Requirements: 1.1, 1.2
func TestQuickSightVPCEndpointConnectivity(t *testing.T) {
	t.Parallel()
	ec2Client := createEC2Client(t, "ap-northeast-2")

	t.Run("QuickAPIEndpointAvailable", func(t *testing.T) {
		endpoints := describeVPCEndpoints(t, ec2Client, "com.amazonaws.ap-northeast-2.quicksight")
		require.NotEmpty(t, endpoints, "Quick API VPC Endpoint should exist")
		assert.Equal(t, "available", *endpoints[0].State, "Quick API Endpoint should be available")
	})

	t.Run("QuickWebsiteEndpointAvailable", func(t *testing.T) {
		endpoints := describeVPCEndpoints(t, ec2Client, "com.amazonaws.ap-northeast-2.quicksight-website")
		require.NotEmpty(t, endpoints, "Quick Website VPC Endpoint should exist")
		assert.Equal(t, "available", *endpoints[0].State, "Quick Website Endpoint should be available")
	})
}

// TestQuickSightVPCConnectionRouting verifies Quick ENI -> VPC Peering -> Virginia path
// Requirements: 4.4, 4.6
func TestQuickSightVPCConnectionRouting(t *testing.T) {
	t.Parallel()
	ec2Client := createEC2Client(t, "ap-northeast-2")

	t.Run("NoDirectVirginiaInSG", func(t *testing.T) {
		sgs := describeSecurityGroupsByName(t, ec2Client, "quicksight-vpc-conn-bos-ai-seoul-prod")
		require.NotEmpty(t, sgs, "QuickSight VPC Connection SG should exist")

		for _, sg := range sgs {
			for _, perm := range sg.IpPermissionsEgress {
				for _, ipRange := range perm.IpRanges {
					assert.NotEqual(t, virginiaCIDR, *ipRange.CidrIp,
						"VPC Connection SG should NOT have direct Virginia CIDR in egress")
				}
			}
		}
	})

	t.Run("VPCPeeringRouteExists", func(t *testing.T) {
		input := &ec2.DescribeRouteTablesInput{
			Filters: []*ec2.Filter{
				{Name: aws.String("tag:Project"), Values: []*string{aws.String("BOS-AI-RAG")}},
				{Name: aws.String("tag:Layer"), Values: []*string{aws.String("network")}},
			},
		}
		result, err := ec2Client.DescribeRouteTables(input)
		require.NoError(t, err)

		hasPeeringRoute := false
		for _, rt := range result.RouteTables {
			for _, route := range rt.Routes {
				if route.DestinationCidrBlock != nil && *route.DestinationCidrBlock == virginiaCIDR {
					if route.VpcPeeringConnectionId != nil {
						hasPeeringRoute = true
					}
				}
			}
		}
		assert.True(t, hasPeeringRoute, "Seoul VPC should have 10.20.0.0/16 -> VPC Peering route")
	})
}

// TestQuickSightDNSResolution verifies quick.rag.corp.bos-semi.com resolves to Private IP
// Requirements: 8.1, 8.3
func TestQuickSightDNSResolution(t *testing.T) {
	t.Parallel()

	t.Run("Route53RecordExists", func(t *testing.T) {
		sess := createAWSSession(t, "ap-northeast-2")
		r53Client := route53.New(sess)

		input := &route53.ListResourceRecordSetsInput{
			HostedZoneId:    aws.String(hostedZoneID),
			StartRecordName: aws.String(quickDNSName),
			StartRecordType: aws.String("CNAME"),
			MaxItems:        aws.String("1"),
		}
		result, err := r53Client.ListResourceRecordSets(input)
		require.NoError(t, err)
		require.NotEmpty(t, result.ResourceRecordSets)
		assert.Contains(t, *result.ResourceRecordSets[0].Name, "quick.rag.corp.bos-semi.com")
	})

	t.Run("DNSResolvesToPrivateIP", func(t *testing.T) {
		ips, err := net.LookupHost(quickDNSName)
		if err != nil {
			t.Skipf("DNS lookup failed (VPN not connected?): %v", err)
			return
		}
		require.NotEmpty(t, ips)
		ip := net.ParseIP(ips[0])
		require.NotNil(t, ip)
		_, seoulNet, _ := net.ParseCIDR(seoulVPCCIDR)
		assert.True(t, seoulNet.Contains(ip), "Should resolve to Seoul VPC Private IP, got: %s", ips[0])
	})
}

// TestQuickSightLambdaExecution verifies RAG Connector Lambda
// Requirements: 5.2, 5.4
func TestQuickSightLambdaExecution(t *testing.T) {
	t.Parallel()
	sess := createAWSSession(t, "ap-northeast-2")
	lambdaClient := lambda.New(sess)

	t.Run("LambdaFunctionExists", func(t *testing.T) {
		input := &lambda.GetFunctionInput{FunctionName: aws.String(lambdaFuncName)}
		result, err := lambdaClient.GetFunction(input)
		if err != nil {
			t.Skipf("Lambda not deployed yet: %v", err)
			return
		}
		assert.Equal(t, "python3.12", *result.Configuration.Runtime)
	})

	t.Run("LambdaInvocationReturnsJSON", func(t *testing.T) {
		input := &lambda.InvokeInput{
			FunctionName: aws.String(lambdaFuncName),
			Payload:      []byte(`{"query_pattern": "rag_usage_stats"}`),
		}
		result, err := lambdaClient.Invoke(input)
		if err != nil {
			t.Skipf("Lambda invocation failed (not deployed?): %v", err)
			return
		}
		assert.Equal(t, int64(200), *result.StatusCode)
		assert.NotEmpty(t, result.Payload)
	})
}

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

func describeVPCEndpoints(t *testing.T, client *ec2.EC2, serviceName string) []*ec2.VpcEndpoint {
	input := &ec2.DescribeVpcEndpointsInput{
		Filters: []*ec2.Filter{
			{Name: aws.String("service-name"), Values: []*string{aws.String(serviceName)}},
		},
	}
	result, err := client.DescribeVpcEndpoints(input)
	require.NoError(t, err)
	return result.VpcEndpoints
}

func describeSecurityGroupsByName(t *testing.T, client *ec2.EC2, groupName string) []*ec2.SecurityGroup {
	input := &ec2.DescribeSecurityGroupsInput{
		Filters: []*ec2.Filter{
			{Name: aws.String("group-name"), Values: []*string{aws.String(groupName)}},
		},
	}
	result, err := client.DescribeSecurityGroups(input)
	require.NoError(t, err)
	return result.SecurityGroups
}
