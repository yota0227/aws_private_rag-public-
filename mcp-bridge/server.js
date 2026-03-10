/**
 * BOS-AI RAG MCP SSE Bridge
 * 
 * Obot → localhost:3100 (MCP Streamable HTTP + SSE) → Seoul Private API Gateway → Lambda → Virginia Bedrock KB
 */
const express = require("express");
const http = require("http");
const https = require("https");
const crypto = require("crypto");
const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const { StreamableHTTPServerTransport } = require("@modelcontextprotocol/sdk/server/streamableHttp.js");
const { SSEServerTransport } = require("@modelcontextprotocol/sdk/server/sse.js");

const RAG_API_BASE = process.env.RAG_API_BASE || "https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag";
const PORT = process.env.PORT || 3100;

function ragApi(method, path, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(RAG_API_BASE + path);
    const options = {
      hostname: url.hostname,
      port: url.port || 443,
      path: url.pathname + url.search,
      method,
      headers: { "Content-Type": "application/json" },
      timeout: 60000
    };
    const req = https.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => { data += chunk; });
      res.on("end", () => {
        try { resolve(JSON.parse(data)); }
        catch(e) { resolve({ raw: data }); }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("Request timeout")); });
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

function createMcpServer() {
  const mcp = new McpServer({ name: "bos-ai-rag", version: "1.0.0" });

  mcp.tool(
    "rag_query",
    "BOS-AI RAG 지식 베이스에 질의합니다. 업로드된 SoC 코드, 스펙 문서 등을 검색하여 답변합니다.",
    { query: { type: "string", description: "질의 내용 (한국어/영어 모두 가능)" } },
    async (params) => {
      try {
        console.log("[TOOL] rag_query: " + params.query);
        const resp = await ragApi("POST", "/query", { query: params.query });
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
        let text = resp.answer || resp.message || JSON.stringify(resp);
        if (resp.citations?.length > 0) {
          text += "\n\n--- 참조 문서 ---";
          resp.citations.forEach((c, i) => {
            if (c.references?.length > 0) text += "\n[" + (i+1) + "] " + c.references.join(", ");
          });
        }
        return { content: [{ type: "text", text }] };
      } catch(err) {
        return { content: [{ type: "text", text: "RAG API 호출 실패: " + err.message }], isError: true };
      }
    }
  );

  mcp.tool(
    "rag_list_documents",
    "업로드된 RAG 문서 목록을 조회합니다. 팀/카테고리로 필터링 가능합니다.",
    {
      team: { type: "string", description: "팀 필터 (예: soc). 생략 시 전체 조회" },
      category: { type: "string", description: "카테고리 필터 (예: code, spec). 생략 시 전체 조회" }
    },
    async (params) => {
      try {
        console.log("[TOOL] rag_list_documents: team=" + (params.team||"all") + " category=" + (params.category||"all"));
        let path = "/documents";
        const qs = [];
        if (params.team) qs.push("team=" + encodeURIComponent(params.team));
        if (params.category) qs.push("category=" + encodeURIComponent(params.category));
        if (qs.length > 0) path += "?" + qs.join("&");
        const resp = await ragApi("GET", path);
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
        if (!resp.files?.length) return { content: [{ type: "text", text: "업로드된 문서가 없습니다." }] };
        let text = "총 " + resp.count + "개 문서:\n";
        resp.files.forEach((f) => {
          const size = f.size < 1048576 ? (f.size/1024).toFixed(1)+" KB" : (f.size/1048576).toFixed(1)+" MB";
          text += "\n- [" + f.team + "/" + f.category + "] " + f.filename + " (" + size + ")";
        });
        return { content: [{ type: "text", text }] };
      } catch(err) {
        return { content: [{ type: "text", text: "문서 목록 조회 실패: " + err.message }], isError: true };
      }
    }
  );

  mcp.tool(
    "rag_categories",
    "RAG 시스템에 등록된 팀/카테고리 목록을 조회합니다.",
    {},
    async () => {
      try {
        console.log("[TOOL] rag_categories");
        const resp = await ragApi("GET", "/categories");
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
        let text = "등록된 팀/카테고리:\n";
        const teams = resp.teams || {};
        Object.keys(teams).forEach((key) => {
          const info = teams[key];
          text += "\n- " + info.name + " (" + key + "): " + info.categories.join(", ");
        });
        return { content: [{ type: "text", text }] };
      } catch(err) {
        return { content: [{ type: "text", text: "카테고리 조회 실패: " + err.message }], isError: true };
      }
    }
  );

  mcp.tool(
    "rag_upload_status",
    "최근 업로드된 RAG 문서 목록과 KB Sync 상태를 조회합니다.",
    {
      team: { type: "string", description: "팀 필터 (선택)" },
      category: { type: "string", description: "카테고리 필터 (선택)" }
    },
    async (params) => {
      try {
        console.log("[TOOL] rag_upload_status: team=" + (params.team||"all") + " category=" + (params.category||"all"));
        let path = "/documents";
        const qs = [];
        if (params.team) qs.push("team=" + encodeURIComponent(params.team));
        if (params.category) qs.push("category=" + encodeURIComponent(params.category));
        if (qs.length > 0) path += "?" + qs.join("&");
        const resp = await ragApi("GET", path);
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
        if (!resp.files?.length) return { content: [{ type: "text", text: "최근 업로드된 문서가 없습니다." }] };
        let text = "📄 최근 업로드 상태 (총 " + resp.count + "개):\n";
        resp.files.forEach((f) => {
          const size = f.size < 1048576 ? (f.size/1024).toFixed(1)+" KB" : (f.size/1048576).toFixed(1)+" MB";
          const sync = f.kb_sync || "unknown";
          text += "\n- [" + f.team + "/" + f.category + "] " + f.filename + " (" + size + ") — KB Sync: " + sync;
        });
        return { content: [{ type: "text", text }] };
      } catch(err) {
        return { content: [{ type: "text", text: "업로드 상태 조회 실패: " + err.message }], isError: true };
      }
    }
  );

  mcp.tool(
    "rag_extract_status",
    "압축 파일 해제 작업(Extraction Task)의 상태를 조회합니다.",
    {
      task_id: { type: "string", description: "Extraction Task ID (필수)" }
    },
    async (params) => {
      try {
        console.log("[TOOL] rag_extract_status: task_id=" + params.task_id);
        const resp = await ragApi("GET", "/documents/extract-status?task_id=" + encodeURIComponent(params.task_id));
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
        let text = "📦 Extraction Task 상태\n";
        text += "  Task ID: " + resp.task_id + "\n";
        text += "  상태: " + resp.status + "\n";
        text += "  생성: " + resp.created_at + "\n";
        text += "  갱신: " + resp.updated_at + "\n";
        if (resp.results) {
          const r = resp.results;
          text += "\n  📊 처리 결과:\n";
          text += "    전체: " + r.total_files + "개\n";
          text += "    성공: " + r.success_count + "개\n";
          text += "    건너뜀: " + r.skipped_count + "개\n";
          text += "    오류: " + r.error_count + "개\n";
          if (r.skipped_files?.length > 0) {
            text += "    건너뛴 파일: " + r.skipped_files.join(", ") + "\n";
          }
          if (r.kb_sync) {
            text += "    KB Sync: " + r.kb_sync + "\n";
          }
        }
        return { content: [{ type: "text", text }] };
      } catch(err) {
        return { content: [{ type: "text", text: "Extraction 상태 조회 실패: " + err.message }], isError: true };
      }
    }
  );

  mcp.tool(
    "rag_delete_document",
    "RAG 지식 베이스에서 문서를 삭제합니다. S3에서 파일을 제거하고 KB Sync를 트리거합니다.",
    {
      s3_key: { type: "string", description: "삭제할 파일의 S3 키 (예: documents/soc/code/filename.pdf)" }
    },
    async (params) => {
      try {
        console.log("[TOOL] rag_delete_document: s3_key=" + params.s3_key);
        const resp = await ragApi("POST", "/documents/delete", { s3_key: params.s3_key });
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
        let text = "✅ 문서 삭제 완료\n";
        text += "  삭제된 파일: " + resp.key + "\n";
        text += "  KB Sync: " + (resp.kb_sync || "unknown");
        return { content: [{ type: "text", text }] };
      } catch(err) {
        return { content: [{ type: "text", text: "문서 삭제 실패: " + err.message }], isError: true };
      }
    }
  );

  return mcp;
}

// Express app
const app = express();
app.use(express.json());

// 모든 요청 로깅 (디버그)
app.use((req, res, next) => {
  if (req.path !== "/health") {
    console.log("[" + new Date().toISOString() + "] " + req.method + " " + req.url);
  }
  next();
});

// OAuth discovery — "인증 불필요" 응답 (Obot OAuth 우회)
app.get("/.well-known/oauth-authorization-server", (req, res) => {
  res.status(404).json({ error: "No authorization server" });
});
app.get("/.well-known/oauth-protected-resource", (req, res) => {
  res.status(404).json({ error: "No protected resource" });
});
app.get("/.well-known/openid-configuration", (req, res) => {
  res.status(404).json({ error: "No OpenID configuration" });
});

// === Streamable HTTP transport (Obot이 사용하는 방식) ===
const streamableSessions = {};

// POST /mcp — Streamable HTTP 엔드포인트 (initialize + tool calls)
app.post("/mcp", async (req, res) => {
  const sessionId = req.headers["mcp-session-id"];
  const method = req.body?.method || (Array.isArray(req.body) ? "batch" : "unknown");
  console.log("[" + new Date().toISOString() + "] POST /mcp session=" + (sessionId || "new") + " method=" + method);

  if (sessionId && streamableSessions[sessionId]) {
    const session = streamableSessions[sessionId];
    await session.transport.handleRequest(req, res, req.body);
    return;
  }

  // 새 세션 생성 (initialize 요청)
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: () => crypto.randomUUID() });
  const mcp = createMcpServer();

  transport.onclose = () => {
    const sid = transport.sessionId;
    if (sid) delete streamableSessions[sid];
    console.log("[" + new Date().toISOString() + "] Streamable session closed: " + sid);
  };

  await mcp.connect(transport);

  // handleRequest 호출 — 이 안에서 sessionId가 설정됨
  await transport.handleRequest(req, res, req.body);

  // handleRequest 이후 세션 저장
  const newSessionId = transport.sessionId;
  if (newSessionId && !streamableSessions[newSessionId]) {
    streamableSessions[newSessionId] = { transport, mcp, connectedAt: new Date() };
    console.log("[" + new Date().toISOString() + "] Streamable session created: " + newSessionId);
  }
});

// GET /mcp — SSE 스트림 (서버→클라이언트 알림용)
app.get("/mcp", async (req, res) => {
  const sessionId = req.headers["mcp-session-id"];
  console.log("[" + new Date().toISOString() + "] GET /mcp (SSE stream) session=" + sessionId);
  if (!sessionId || !streamableSessions[sessionId]) {
    res.status(400).json({ error: "Invalid or missing session" });
    return;
  }
  const session = streamableSessions[sessionId];
  await session.transport.handleRequest(req, res);
});

// DELETE /mcp — 세션 종료
app.delete("/mcp", async (req, res) => {
  const sessionId = req.headers["mcp-session-id"];
  console.log("[" + new Date().toISOString() + "] DELETE /mcp session=" + sessionId);
  if (sessionId && streamableSessions[sessionId]) {
    const session = streamableSessions[sessionId];
    await session.transport.close();
    delete streamableSessions[sessionId];
  }
  res.status(200).json({ status: "closed" });
});

// === Legacy SSE transport (기존 SSE 클라이언트 호환) ===
const sseSessions = {};

app.get("/sse", (req, res) => {
  const transport = new SSEServerTransport("/messages", res);
  const sessionId = transport.sessionId;
  sseSessions[sessionId] = { transport, connectedAt: new Date() };
  console.log("[" + new Date().toISOString() + "] SSE session opened: " + sessionId);

  transport.onerror = (err) => {
    console.error("[" + new Date().toISOString() + "] SSE transport error [" + sessionId + "]: " + err);
  };
  transport.onclose = () => {
    delete sseSessions[sessionId];
    console.log("[" + new Date().toISOString() + "] SSE session closed: " + sessionId);
  };

  const mcp = createMcpServer();
  mcp.connect(transport).catch((err) => {
    console.error("[" + new Date().toISOString() + "] SSE connect error: " + err);
  });
});

app.post("/messages", (req, res) => {
  const sessionId = req.query.sessionId;
  console.log("[" + new Date().toISOString() + "] POST /messages sessionId=" + sessionId);
  const session = sseSessions[sessionId];
  if (!session) {
    console.log("[" + new Date().toISOString() + "] Invalid session: " + sessionId);
    res.status(400).json({ error: "Invalid session" });
    return;
  }
  session.transport.handlePostMessage(req, res);
});

// Health check
app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    ragApi: RAG_API_BASE,
    streamableSessions: Object.keys(streamableSessions).length,
    sseSessions: Object.keys(sseSessions).length
  });
});

const server = http.createServer(app);
server.keepAliveTimeout = 65000;
server.headersTimeout = 66000;

server.listen(PORT, () => {
  console.log("=== BOS-AI RAG MCP Bridge ===");
  console.log("  Streamable HTTP: http://localhost:" + PORT + "/mcp");
  console.log("  Legacy SSE:      http://localhost:" + PORT + "/sse");
  console.log("  Health:          http://localhost:" + PORT + "/health");
  console.log("  RAG API:         " + RAG_API_BASE);
  console.log("  Node.js:         " + process.version);
  console.log("=============================");
});

process.on("SIGTERM", () => {
  console.log("Shutting down...");
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 10000);
});
