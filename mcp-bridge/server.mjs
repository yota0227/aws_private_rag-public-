/**
 * BOS-AI RAG MCP SSE Bridge
 * 
 * Obot → localhost:3100/sse (MCP SSE) → Seoul Private API Gateway → Lambda → Virginia Bedrock KB
 * 
 * MCP Tools:
 *   - rag_query: RAG 질의 (임베딩된 문서 검색 + LLM 답변)
 *   - rag_list_documents: 업로드된 문서 목록 조회
 *   - rag_categories: 팀/카테고리 목록 조회
 */
const express = require("express");
const http = require("http");
const https = require("https");
const { McpServer } = require("@modelcontextprotocol/sdk/dist/cjs/server/mcp.js");
const { SSEServerTransport } = require("@modelcontextprotocol/sdk/dist/cjs/server/sse.js");

// Seoul Private API Gateway 엔드포인트
const RAG_API_BASE = process.env.RAG_API_BASE || "https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag";
const PORT = process.env.PORT || 3100;

// HTTP(S) 요청 헬퍼
function ragApi(method, path, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(RAG_API_BASE + path);
    const options = {
      hostname: url.hostname,
      port: url.port || 443,
      path: url.pathname + url.search,
      method: method,
      headers: { "Content-Type": "application/json" },
      timeout: 60000
    };

    const req = https.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => { data += chunk; });
      res.on("end", () => {
        try {
          resolve(JSON.parse(data));
        } catch(e) {
          resolve({ raw: data });
        }
      });
    });

    req.on("error", (err) => { reject(err); });
    req.on("timeout", () => { req.destroy(); reject(new Error("Request timeout")); });

    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

// MCP Server 생성
const mcpServer = new McpServer({
  name: "bos-ai-rag",
  version: "1.0.0"
});

// Tool 1: RAG 질의
mcpServer.tool(
  "rag_query",
  "BOS-AI RAG 지식 베이스에 질의합니다. 업로드된 SoC 코드, 스펙 문서 등을 검색하여 답변합니다.",
  {
    query: { type: "string", description: "질의 내용 (한국어/영어 모두 가능)" }
  },
  async (params) => {
    try {
      const resp = await ragApi("POST", "/query", { query: params.query });
      if (resp.error) {
        return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
      }
      let text = resp.answer || resp.message || JSON.stringify(resp);
      if (resp.citations && resp.citations.length > 0) {
        text += "\n\n--- 참조 문서 ---";
        resp.citations.forEach((c, i) => {
          if (c.references && c.references.length > 0) {
            text += "\n[" + (i + 1) + "] " + c.references.join(", ");
          }
        });
      }
      return { content: [{ type: "text", text: text }] };
    } catch(err) {
      return { content: [{ type: "text", text: "RAG API 호출 실패: " + err.message }], isError: true };
    }
  }
);

// Tool 2: 문서 목록 조회
mcpServer.tool(
  "rag_list_documents",
  "업로드된 RAG 문서 목록을 조회합니다. 팀/카테고리로 필터링 가능합니다.",
  {
    team: { type: "string", description: "팀 필터 (예: soc). 생략 시 전체 조회" },
    category: { type: "string", description: "카테고리 필터 (예: code, spec). 생략 시 전체 조회" }
  },
  async (params) => {
    try {
      let path = "/documents";
      const qs = [];
      if (params.team) qs.push("team=" + encodeURIComponent(params.team));
      if (params.category) qs.push("category=" + encodeURIComponent(params.category));
      if (qs.length > 0) path += "?" + qs.join("&");

      const resp = await ragApi("GET", path);
      if (resp.error) {
        return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
      }
      if (!resp.files || resp.files.length === 0) {
        return { content: [{ type: "text", text: "업로드된 문서가 없습니다." }] };
      }
      let text = "총 " + resp.count + "개 문서:\n";
      resp.files.forEach((f) => {
        const size = f.size < 1048576
          ? (f.size / 1024).toFixed(1) + " KB"
          : (f.size / 1048576).toFixed(1) + " MB";
        text += "\n- [" + f.team + "/" + f.category + "] " + f.filename + " (" + size + ")";
      });
      return { content: [{ type: "text", text: text }] };
    } catch(err) {
      return { content: [{ type: "text", text: "문서 목록 조회 실패: " + err.message }], isError: true };
    }
  }
);

// Tool 3: 카테고리 목록
mcpServer.tool(
  "rag_categories",
  "RAG 시스템에 등록된 팀/카테고리 목록을 조회합니다.",
  {},
  async () => {
    try {
      const resp = await ragApi("GET", "/categories");
      if (resp.error) {
        return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
      }
      let text = "등록된 팀/카테고리:\n";
      const teams = resp.teams || {};
      Object.keys(teams).forEach((key) => {
        const info = teams[key];
        text += "\n- " + info.name + " (" + key + "): " + info.categories.join(", ");
      });
      return { content: [{ type: "text", text: text }] };
    } catch(err) {
      return { content: [{ type: "text", text: "카테고리 조회 실패: " + err.message }], isError: true };
    }
  }
);

// Express + SSE Transport
const app = express();
app.use(express.json());

const sessions = {};

app.get("/health", (req, res) => {
  res.json({ status: "ok", ragApi: RAG_API_BASE, sessions: Object.keys(sessions).length });
});

app.get("/sse", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");

  const transport = new SSEServerTransport("/messages", res);
  const sessionId = transport.sessionId;
  sessions[sessionId] = { transport: transport, connectedAt: new Date() };

  console.log("[" + new Date().toISOString() + "] MCP session opened: " + sessionId);

  transport.onclose = () => {
    delete sessions[sessionId];
    console.log("[" + new Date().toISOString() + "] MCP session closed: " + sessionId);
  };

  mcpServer.connect(transport);
});

app.post("/messages", (req, res) => {
  const sessionId = req.query.sessionId;
  const session = sessions[sessionId];
  if (!session) {
    res.status(400).json({ error: "Invalid session" });
    return;
  }
  session.transport.handlePostMessage(req, res);
});

// Start
const server = http.createServer(app);
server.keepAliveTimeout = 65000;
server.headersTimeout = 66000;

server.listen(PORT, () => {
  console.log("=== BOS-AI RAG MCP Bridge ===");
  console.log("  MCP SSE:  http://localhost:" + PORT + "/sse");
  console.log("  Health:   http://localhost:" + PORT + "/health");
  console.log("  RAG API:  " + RAG_API_BASE);
  console.log("=============================");
});

process.on("SIGTERM", () => {
  console.log("Shutting down...");
  server.close(() => { process.exit(0); });
  setTimeout(() => { process.exit(1); }, 10000);
});
