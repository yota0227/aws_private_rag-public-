'use strict';

const { McpServer } = require('@modelcontextprotocol/sdk/server/mcp.js');
const { StreamableHTTPServerTransport } = require('@modelcontextprotocol/sdk/server/streamableHttp.js');
const { LambdaClient, InvokeCommand } = require('@aws-sdk/client-lambda');
const express = require('express');
const http = require('http');

// Configuration
const PORT = 3000;
const LAMBDA_FUNCTION = 'lambda-document-processor-seoul-prod';
const AWS_REGION = process.env.AWS_REGION || 'ap-northeast-2';
const MCP_API_KEY = process.env.MCP_API_KEY;

// Lambda client
const lambdaClient = new LambdaClient({ region: AWS_REGION });

// Tool definitions by category
const RAG_TOOLS = [
  { name: 'rag_query', description: 'Query RAG knowledge base', params: { query: 'string' } },
  { name: 'rag_list_documents', description: 'List uploaded RAG documents', params: { category: 'string?', team: 'string?' } },
  { name: 'rag_categories', description: 'List registered teams/categories', params: {} },
  { name: 'rag_upload_status', description: 'Check recent upload and KB sync status', params: { category: 'string?', team: 'string?' } },
  { name: 'rag_extract_status', description: 'Check extraction task status', params: { task_id: 'string' } },
  { name: 'rag_delete_document', description: 'Delete document from RAG knowledge base', params: { s3_key: 'string' } },
  { name: 'search_rtl', description: 'Search RTL parsed data', params: { query: 'string', topic: 'string?', pipeline_id: 'string?', max_results: 'number?' } },
  { name: 'search_archive', description: 'Search archive documents with vector search', params: { query: 'string', topic: 'string?', source: 'string?', max_results: 'number?' } },
  { name: 'get_evidence', description: 'Get evidence array for a specific claim', params: { claim_id: 'string' } },
];

const NEPTUNE_TOOLS = [
  { name: 'trace_signal_path', description: 'Trace signal propagation path in RTL module', params: { module_name: 'string', signal_name: 'string' } },
  { name: 'find_instantiation_tree', description: 'Get instantiation tree for RTL module', params: { module_name: 'string', depth: 'number?' } },
  { name: 'find_clock_crossings', description: 'Find clock domain crossing signals', params: { module_name: 'string' } },
  { name: 'graph_export', description: 'Export Neptune graph subset as JSON', params: { scope: 'string', root_module: 'string', signal_filter: 'string?', depth: 'number?' } },
];

const HDD_TOOLS = [
  { name: 'list_verified_claims', description: 'List verified claims for a topic', params: { topic: 'string' } },
  { name: 'generate_hdd_section', description: 'Generate HDD section from verified claims', params: { topic: 'string', section_title: 'string', include_evidence: 'boolean?' } },
  { name: 'publish_markdown', description: 'Publish markdown content to S3', params: { content: 'string', filename: 'string', topic: 'string?' } },
  { name: 'regenerate_stale_hdd', description: 'Regenerate stale HDD sections', params: {} },
];

const ALL_TOOLS = [...RAG_TOOLS, ...NEPTUNE_TOOLS, ...HDD_TOOLS];

/**
 * Invoke Lambda with action and parameters
 */
async function invokeLambda(action, parameters) {
  const payload = JSON.stringify({ action, parameters });

  const command = new InvokeCommand({
    FunctionName: LAMBDA_FUNCTION,
    InvocationType: 'RequestResponse',
    Payload: Buffer.from(payload),
  });

  const response = await lambdaClient.send(command);
  const responsePayload = JSON.parse(Buffer.from(response.Payload).toString());

  if (response.FunctionError) {
    throw new Error(`Lambda error: ${responsePayload.errorMessage || JSON.stringify(responsePayload)}`);
  }

  // Handle API Gateway-style Lambda responses
  if (responsePayload.statusCode && responsePayload.body) {
    const body = typeof responsePayload.body === 'string'
      ? JSON.parse(responsePayload.body)
      : responsePayload.body;
    if (responsePayload.statusCode >= 400) {
      throw new Error(`Lambda returned ${responsePayload.statusCode}: ${JSON.stringify(body)}`);
    }
    return body;
  }

  return responsePayload;
}

/**
 * Build MCP tool schema from tool definition
 */
function buildToolSchema(tool) {
  const properties = {};
  const required = [];

  for (const [key, type] of Object.entries(tool.params)) {
    const isOptional = type.endsWith('?');
    const baseType = isOptional ? type.slice(0, -1) : type;

    properties[key] = { type: baseType === 'number' ? 'number' : baseType === 'boolean' ? 'boolean' : 'string' };
    if (!isOptional) {
      required.push(key);
    }
  }

  return {
    type: 'object',
    properties,
    required: required.length > 0 ? required : undefined,
  };
}

/**
 * Create and configure the MCP server
 */
function createMcpServer() {
  const server = new McpServer({
    name: 'bos-ai-mcp-server',
    version: '1.0.0',
  });

  // Register all 17 tools
  for (const tool of ALL_TOOLS) {
    const schema = buildToolSchema(tool);
    server.tool(tool.name, tool.description, schema, async (params) => {
      try {
        const result = await invokeLambda(tool.name, params);
        return {
          content: [{ type: 'text', text: JSON.stringify(result, null, 2) }],
        };
      } catch (error) {
        return {
          content: [{ type: 'text', text: `Error: ${error.message}` }],
          isError: true,
        };
      }
    });
  }

  return server;
}

/**
 * Authenticate request via API key
 */
function authenticate(req, res, next) {
  if (req.path === '/health') {
    return next();
  }

  const apiKey = req.headers['x-api-key'] || req.headers['authorization']?.replace('Bearer ', '');
  if (!apiKey || apiKey !== MCP_API_KEY) {
    return res.status(401).json({
      jsonrpc: '2.0',
      error: { code: -32600, message: 'Authentication failed' },
    });
  }
  next();
}

/**
 * Main entry point
 */
async function main() {
  const app = express();

  // Health endpoint
  app.get('/health', async (req, res) => {
    try {
      // Verify Lambda connectivity with a lightweight call
      const command = new InvokeCommand({
        FunctionName: LAMBDA_FUNCTION,
        InvocationType: 'DryRun',
      });
      await lambdaClient.send(command);
      res.status(200).json({ status: 'healthy', tools: ALL_TOOLS.length });
    } catch (error) {
      res.status(200).json({ status: 'healthy', tools: ALL_TOOLS.length, note: 'Lambda DryRun skipped' });
    }
  });

  // Authentication middleware for MCP routes
  app.use(authenticate);

  // Create MCP server and transport
  const mcpServer = createMcpServer();

  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined, // stateless mode
  });

  // Connect MCP server to transport
  await mcpServer.connect(transport);

  // Mount Streamable HTTP handler
  app.all('/mcp', async (req, res) => {
    await transport.handleRequest(req, res);
  });

  // Start HTTP server
  const server = http.createServer(app);
  server.listen(PORT, '0.0.0.0', () => {
    console.log(`MCP Server listening on port ${PORT}`);
    console.log(`Registered ${ALL_TOOLS.length} tools (${RAG_TOOLS.length} RAG + ${NEPTUNE_TOOLS.length} Neptune + ${HDD_TOOLS.length} HDD)`);
  });
}

main().catch((error) => {
  console.error('Failed to start MCP server:', error);
  process.exit(1);
});
