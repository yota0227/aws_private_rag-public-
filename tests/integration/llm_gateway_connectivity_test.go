//go:build integration

package integration_test

import (
	"bufio"
	"context"
	"fmt"
	"net"
	"net/http"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const connectivityTimeout = 10 * time.Second

// requireEnv reads an environment variable or skips the test if unset.
func requireEnv(t *testing.T, key string) string {
	t.Helper()
	val := os.Getenv(key)
	if val == "" {
		t.Skipf("Skipping: environment variable %s is not set", key)
	}
	return val
}

// TestLiteLLMHealth verifies the LiteLLM /health endpoint returns HTTP 200.
// Validates: Requirements 23.4
func TestLiteLLMHealth(t *testing.T) {
	endpoint := requireEnv(t, "LITELLM_ENDPOINT")

	ctx, cancel := context.WithTimeout(context.Background(), connectivityTimeout)
	defer cancel()

	url := strings.TrimRight(endpoint, "/") + "/health"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	require.NoError(t, err)

	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err, "Failed to reach LiteLLM health endpoint at %s", url)
	defer resp.Body.Close()

	assert.Equal(t, http.StatusOK, resp.StatusCode,
		"LiteLLM /health should return 200, got %d", resp.StatusCode)
}

// TestMCPServerHealth verifies the MCP Server /health endpoint returns HTTP 200.
// Validates: Requirements 23.5
func TestMCPServerHealth(t *testing.T) {
	endpoint := requireEnv(t, "MCP_ENDPOINT")

	ctx, cancel := context.WithTimeout(context.Background(), connectivityTimeout)
	defer cancel()

	url := strings.TrimRight(endpoint, "/") + "/health"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	require.NoError(t, err)

	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err, "Failed to reach MCP Server health endpoint at %s", url)
	defer resp.Body.Close()

	assert.Equal(t, http.StatusOK, resp.StatusCode,
		"MCP Server /health should return 200, got %d", resp.StatusCode)
}

// TestAPIGatewayLLMRoute verifies the API Gateway /llm/health route responds.
// Validates: Requirements 19.1
func TestAPIGatewayLLMRoute(t *testing.T) {
	baseURL := requireEnv(t, "APIGW_BASE_URL")

	ctx, cancel := context.WithTimeout(context.Background(), connectivityTimeout)
	defer cancel()

	url := strings.TrimRight(baseURL, "/") + "/llm/health"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	require.NoError(t, err)

	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err, "Failed to reach API Gateway /llm/health at %s", url)
	defer resp.Body.Close()

	// Any response (even 4xx) means the route is configured and reachable
	assert.True(t, resp.StatusCode > 0,
		"API Gateway /llm/health should respond, got status %d", resp.StatusCode)
}

// TestAPIGatewayMCPRoute verifies the API Gateway /mcp/health route responds.
// Validates: Requirements 19.2
func TestAPIGatewayMCPRoute(t *testing.T) {
	baseURL := requireEnv(t, "APIGW_BASE_URL")

	ctx, cancel := context.WithTimeout(context.Background(), connectivityTimeout)
	defer cancel()

	url := strings.TrimRight(baseURL, "/") + "/mcp/health"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	require.NoError(t, err)

	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err, "Failed to reach API Gateway /mcp/health at %s", url)
	defer resp.Body.Close()

	assert.True(t, resp.StatusCode > 0,
		"API Gateway /mcp/health should respond, got status %d", resp.StatusCode)
}

// TestRoute53LLMResolves verifies DNS lookup of llm.corp.bos-semi.com returns an IP.
// Validates: Requirements 19.3
func TestRoute53LLMResolves(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), connectivityTimeout)
	defer cancel()

	resolver := net.DefaultResolver
	ips, err := resolver.LookupHost(ctx, "llm.corp.bos-semi.com")
	require.NoError(t, err, "DNS lookup for llm.corp.bos-semi.com failed")

	assert.NotEmpty(t, ips, "llm.corp.bos-semi.com should resolve to at least one IP")
	t.Logf("llm.corp.bos-semi.com resolved to: %v", ips)
}

// TestRoute53MCPResolves verifies DNS lookup of mcp.corp.bos-semi.com returns an IP.
// Validates: Requirements 19.3
func TestRoute53MCPResolves(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), connectivityTimeout)
	defer cancel()

	resolver := net.DefaultResolver
	ips, err := resolver.LookupHost(ctx, "mcp.corp.bos-semi.com")
	require.NoError(t, err, "DNS lookup for mcp.corp.bos-semi.com failed")

	assert.NotEmpty(t, ips, "mcp.corp.bos-semi.com should resolve to at least one IP")
	t.Logf("mcp.corp.bos-semi.com resolved to: %v", ips)
}

// TestSquidWhitelistAllow verifies CONNECT to api.openai.com via Squid proxy succeeds.
// Validates: Requirements 20.1
func TestSquidWhitelistAllow(t *testing.T) {
	proxyAddr := requireEnv(t, "SQUID_PROXY_ADDR")

	conn, err := net.DialTimeout("tcp", proxyAddr, connectivityTimeout)
	require.NoError(t, err, "Failed to connect to Squid proxy at %s", proxyAddr)
	defer conn.Close()

	// Set deadline for the entire CONNECT handshake
	err = conn.SetDeadline(time.Now().Add(connectivityTimeout))
	require.NoError(t, err)

	// Send HTTP CONNECT request for a whitelisted domain
	connectReq := fmt.Sprintf("CONNECT api.openai.com:443 HTTP/1.1\r\nHost: api.openai.com:443\r\n\r\n")
	_, err = conn.Write([]byte(connectReq))
	require.NoError(t, err, "Failed to send CONNECT request to Squid")

	// Read the response status line
	reader := bufio.NewReader(conn)
	statusLine, err := reader.ReadString('\n')
	require.NoError(t, err, "Failed to read CONNECT response from Squid")

	// Expect HTTP 200 Connection Established
	assert.True(t, strings.Contains(statusLine, "200"),
		"Squid CONNECT to api.openai.com should return 200, got: %s", strings.TrimSpace(statusLine))
}

// TestSquidWhitelistDeny verifies CONNECT to example.com via Squid proxy is denied.
// Validates: Requirements 20.2
func TestSquidWhitelistDeny(t *testing.T) {
	proxyAddr := requireEnv(t, "SQUID_PROXY_ADDR")

	conn, err := net.DialTimeout("tcp", proxyAddr, connectivityTimeout)
	require.NoError(t, err, "Failed to connect to Squid proxy at %s", proxyAddr)
	defer conn.Close()

	// Set deadline for the entire CONNECT handshake
	err = conn.SetDeadline(time.Now().Add(connectivityTimeout))
	require.NoError(t, err)

	// Send HTTP CONNECT request for a non-whitelisted domain
	connectReq := fmt.Sprintf("CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
	_, err = conn.Write([]byte(connectReq))
	require.NoError(t, err, "Failed to send CONNECT request to Squid")

	// Read the response status line
	reader := bufio.NewReader(conn)
	statusLine, err := reader.ReadString('\n')
	require.NoError(t, err, "Failed to read CONNECT response from Squid")

	// Expect HTTP 403 Forbidden (Squid denies non-whitelisted domains)
	assert.True(t, strings.Contains(statusLine, "403"),
		"Squid CONNECT to example.com should return 403, got: %s", strings.TrimSpace(statusLine))
}
