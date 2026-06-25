/**
 * BOS-AI Tool Guide RAG — MCP Bridge (separate service, port 3101)
 *
 * 이 브리지는 NPU/RTL RAG MCP(:3100)와 **완전히 분리된** 독립 MCP 서비스다.
 * 권한 분리(pipeline=tool-guide)를 위해 별도 포트/프로세스/도구 집합으로 운영한다.
 *
 * 아키텍처:
 *   Kiro/Obot --Streamable HTTP /mcp--> 이 브리지(:3101)
 *                                          | Lambda invoke {action:"search"}
 *                                          v
 *                          lambda-tool-guide-parser-seoul-dev
 *                          (query 임베딩 -> Qdrant tool-guide-knowledge-base 검색)
 *
 * 노출 도구 (RTL MCP와 이름이 겹치지 않음 - R5.2):
 *   - tool_guide_search : 심볼/명령어 검색 (query <= 256자)
 *   - tool_guide_query  : 자연어 질의     (query <= 8192자)
 *
 * Spec: .kiro/specs/eda-tool-guide-rag/ (C5 Tool_Guide_MCP, 가정 4)
 */
const express = require("express");
const http = require("http");
const crypto = require("crypto");
const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const { StreamableHTTPServerTransport } = require("@modelcontextprotocol/sdk/server/streamableHttp.js");
const { SSEServerTransport } = require("@modelcontextprotocol/sdk/server/sse.js");
const { z } = require("zod");

const PORT = process.env.PORT || 3101;
const AWS_REGION = process.env.AWS_REGION || "ap-northeast-2";
const TOOL_GUIDE_LAMBDA = process.env.TOOL_GUIDE_LAMBDA || "lambda-tool-guide-parser-seoul-dev";

const SEARCH_MAX_CHARS = 256;
const QUERY_MAX_CHARS = 8192;

// Grounding directive prepended to every search response so the consuming LLM
// (Kiro / Obot / etc.) answers strictly from the cited evidence below and says
// "I don't know" when the answer is absent — hallucination 0 (user policy).
const GROUNDING_NOTICE =
  "[근거 기반 답변 지침 / GROUNDING — 반드시 준수]\n" +
  "1) 아래 검색 결과에 '명시적으로 적힌' 내용만 근거로 사용하라.\n" +
  "2) 결과에 없거나 불확실하면 추측하지 말고 반드시 '근거 없음 — 모름'이라고 답하라 (할루시네이션 0).\n" +
  "3) 모든 주장에는 출처(파일명·페이지)를 붙여라.\n" +
  "4) 결과 텍스트가 잘려 있거나 표/다이어그램 라벨만 있으면 단정하지 말고 한계를 밝혀라.\n" +
  "(EN) Answer ONLY from the cited results below. If the answer is not present, say you do not know — never guess. Cite source file and page for every claim.\n" +
  "--------------------------------------------------\n";

let _lambdaClient = null;
function getLambdaClient() {
  if (!_lambdaClient) {
    const { LambdaClient } = require("@aws-sdk/client-lambda");
    _lambdaClient = new LambdaClient({ region: AWS_REGION });
  }
  return _lambdaClient;
}

async function searchToolGuide(body) {
  const { InvokeCommand } = require("@aws-sdk/client-lambda");
  const client = getLambdaClient();
  const payload = { action: "search", ...body };
  const cmd = new InvokeCommand({
    FunctionName: TOOL_GUIDE_LAMBDA,
    InvocationType: "RequestResponse",
    Payload: Buffer.from(JSON.stringify(payload)),
  });
  const resp = await client.send(cmd);
  const raw = Buffer.from(resp.Payload).toString("utf-8");
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    throw new Error("Lambda 응답 파싱 실패: " + raw.substring(0, 200));
  }
  if (resp.FunctionError) {
    throw new Error("Lambda 오류: " + (parsed.errorMessage || resp.FunctionError));
  }
  return parsed;
}

function renderResults(query, resp) {
  const results = resp.results || [];
  if (results.length === 0) {
    return GROUNDING_NOTICE +
      "\"" + query + "\": " + (resp.message || "검색 결과가 없습니다.") +
      "\n→ 근거가 없으므로 답변은 '근거 없음 — 모름'으로 하라. 추측 금지.";
  }
  let text = GROUNDING_NOTICE + "Tool Guide 검색 결과 (" + results.length + "건):\n";
  results.forEach(function (r, i) {
    text += "\n[" + (i + 1) + "] " + (r.tool_name || "(unknown)") +
            " " + (r.tool_version || "") + " | " + (r.object_type || "");
    if (r.command && r.command !== "미확인") text += " | command: " + r.command;
    if (r.option && r.option !== "미확인") text += " | option: " + r.option;
    if (r.canonical_text) text += "\n    " + r.canonical_text.substring(0, 500);
    const c = r.citation || {};
    const loc = (c.page != null) ? ("p." + c.page) : (c.section || "");
    text += "\n    출처: " + (c.source_file || "?") + " (" + (c.doc_version || "?") + ") " + loc;
  });
  return text;
}

function createMcpServer() {
  const mcp = new McpServer({ name: "bos-ai-tool-guide-rag", version: "1.0.0" });

  mcp.tool(
    "tool_guide_search",
    "[목적] EDA 툴 가이드(Document RAG)에서 명령어/옵션/심볼을 검색합니다. " +
      "RTL/SoC 설계 데이터(search_rtl)나 업로드 문서 일반 질의(rag_query)와 분리된 " +
      "전용 Tool Guide corpus만 조회합니다. [입력] query(필수, 최대 256자): 명령어/옵션/심볼명. " +
      "tool_name(선택): 툴 필터. tool_version(선택): 버전 필터. " +
      "[예시] query=\"elaborate\", tool_name=\"VCS\" -> VCS의 elaborate 명령 설명/옵션 반환. " +
      "[중요] 반환된 검색 결과(인용 출처)에 명시된 내용만으로 답하라. 결과에 없으면 '모름'이라고 답하고 추측하지 말 것(할루시네이션 0).",
    {
      query: z.string().describe("검색어 (명령어/옵션/심볼명, 최대 256자)"),
      tool_name: z.string().optional().describe("툴명 필터 (예: VCS)"),
      tool_version: z.string().optional().describe("툴 버전 필터 (예: ver.1)"),
      max_results: z.number().optional().default(20).describe("최대 결과 수 (기본 20)"),
    },
    async (args) => {
      try {
        const q = (args.query || "").trim();
        if (q.length === 0 || q.length > SEARCH_MAX_CHARS) {
          return { content: [{ type: "text", text: "error:input_length - query는 1~" + SEARCH_MAX_CHARS + "자여야 합니다." }], isError: true };
        }
        const resp = await searchToolGuide({
          query: q, tool_name: args.tool_name, tool_version: args.tool_version,
          max_results: Math.min(args.max_results || 20, 20),
        });
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error + " " + (resp.message || "") }], isError: true };
        return { content: [{ type: "text", text: renderResults(q, resp) }] };
      } catch (err) {
        return { content: [{ type: "text", text: "Tool Guide 검색 실패: " + err.message }], isError: true };
      }
    }
  );

  mcp.tool(
    "tool_guide_query",
    "[목적] EDA 툴 가이드(Document RAG)에 자연어로 질문해 사용법을 근거(출처)와 함께 받습니다. " +
      "RTL 설계 데이터(search_rtl)와 분리된 전용 Tool Guide corpus만 조회합니다. " +
      "[입력] query(필수, 최대 8192자): 자연어 질문. tool_name/tool_version(선택): 범위 한정. " +
      "[예시] query=\"VCS에서 design을 elaborate하는 옵션 알려줘\" -> 근거 인용과 함께 답변. " +
      "[중요] 반환된 검색 결과(인용 출처)에 명시된 내용만으로 답하라. 결과에 없으면 '모름'이라고 답하고 추측하지 말 것(할루시네이션 0).",
    {
      query: z.string().describe("자연어 질의 (최대 8192자)"),
      tool_name: z.string().optional().describe("툴명 필터 (예: VCS)"),
      tool_version: z.string().optional().describe("툴 버전 필터"),
      max_results: z.number().optional().default(20).describe("최대 결과 수 (기본 20)"),
    },
    async (args) => {
      try {
        const q = (args.query || "").trim();
        if (q.length === 0 || q.length > QUERY_MAX_CHARS) {
          return { content: [{ type: "text", text: "error:input_length - query는 1~" + QUERY_MAX_CHARS + "자여야 합니다." }], isError: true };
        }
        const resp = await searchToolGuide({
          query: q, tool_name: args.tool_name, tool_version: args.tool_version,
          max_results: Math.min(args.max_results || 20, 20),
        });
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error + " " + (resp.message || "") }], isError: true };
        return { content: [{ type: "text", text: renderResults(q, resp) }] };
      } catch (err) {
        return { content: [{ type: "text", text: "Tool Guide 질의 실패: " + err.message }], isError: true };
      }
    }
  );

  return mcp;
}

const app = express();
app.use(express.json({ limit: "1mb" }));

app.use((req, res, next) => {
  if (req.path !== "/health") {
    console.log("[" + new Date().toISOString() + "] " + req.method + " " + req.url);
  }
  next();
});

app.get("/.well-known/oauth-authorization-server", (req, res) => res.status(404).json({ error: "No authorization server" }));
app.get("/.well-known/oauth-protected-resource", (req, res) => res.status(404).json({ error: "No protected resource" }));
app.get("/.well-known/openid-configuration", (req, res) => res.status(404).json({ error: "No OpenID configuration" }));

const streamableSessions = {};

app.post("/mcp", async (req, res) => {
  const sessionId = req.headers["mcp-session-id"];
  if (sessionId && streamableSessions[sessionId]) {
    await streamableSessions[sessionId].transport.handleRequest(req, res, req.body);
    return;
  }
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: () => crypto.randomUUID() });
  const mcp = createMcpServer();
  transport.onclose = () => {
    const sid = transport.sessionId;
    if (sid) delete streamableSessions[sid];
  };
  await mcp.connect(transport);
  await transport.handleRequest(req, res, req.body);
  const newSessionId = transport.sessionId;
  if (newSessionId && !streamableSessions[newSessionId]) {
    streamableSessions[newSessionId] = { transport, mcp, connectedAt: new Date() };
    console.log("[" + new Date().toISOString() + "] Streamable session created: " + newSessionId);
  }
});

app.get("/mcp", async (req, res) => {
  const sessionId = req.headers["mcp-session-id"];
  if (!sessionId || !streamableSessions[sessionId]) {
    res.status(400).json({ error: "Invalid or missing session" });
    return;
  }
  await streamableSessions[sessionId].transport.handleRequest(req, res);
});

app.delete("/mcp", async (req, res) => {
  const sessionId = req.headers["mcp-session-id"];
  if (sessionId && streamableSessions[sessionId]) {
    await streamableSessions[sessionId].transport.close();
    delete streamableSessions[sessionId];
  }
  res.status(200).json({ status: "closed" });
});

const sseSessions = {};
app.get("/sse", (req, res) => {
  const transport = new SSEServerTransport("/messages", res);
  const sessionId = transport.sessionId;
  sseSessions[sessionId] = { transport, connectedAt: new Date() };
  transport.onclose = () => { delete sseSessions[sessionId]; };
  const mcp = createMcpServer();
  mcp.connect(transport).catch((err) => console.error("SSE connect error: " + err));
});
app.post("/messages", (req, res) => {
  const sessionId = req.query.sessionId;
  const session = sseSessions[sessionId];
  if (!session) { res.status(400).json({ error: "Invalid session" }); return; }
  session.transport.handlePostMessage(req, res);
});

app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    service: "tool-guide-mcp",
    lambda: TOOL_GUIDE_LAMBDA,
    streamableSessions: Object.keys(streamableSessions).length,
    sseSessions: Object.keys(sseSessions).length,
  });
});

const server = http.createServer(app);
server.keepAliveTimeout = 65000;
server.headersTimeout = 66000;

server.listen(PORT, () => {
  console.log("=== BOS-AI Tool Guide RAG MCP Bridge ===");
  console.log("  Streamable HTTP: http://localhost:" + PORT + "/mcp");
  console.log("  Health:          http://localhost:" + PORT + "/health");
  console.log("  Lambda:          " + TOOL_GUIDE_LAMBDA);
  console.log("  Node.js:         " + process.version);
  console.log("========================================");
});

process.on("SIGTERM", () => {
  console.log("Shutting down...");
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 10000);
});
