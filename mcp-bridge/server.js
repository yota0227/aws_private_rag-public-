const express = require("express");
const http = require("http");
const https = require("https");

const RAG_API_BASE = process.env.RAG_API_BASE || "https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag";
const PORT = process.env.PORT || 3100;

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

const app = express();
app.use(express.json());

app.get("/health", (req, res) => {
  res.json({ status: "ok", ragApi: RAG_API_BASE });
});

app.get("/sse", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");

  const sessionId = Math.random().toString(36).substring(7);
  console.log("[" + new Date().toISOString() + "] SSE session opened: " + sessionId);

  res.write(":connected\n\n");

  const interval = setInterval(() => {
    res.write(":ping\n\n");
  }, 30000);

  req.on("close", () => {
    clearInterval(interval);
    console.log("[" + new Date().toISOString() + "] SSE session closed: " + sessionId);
  });
});

app.post("/messages", (req, res) => {
  res.json({ status: "ok" });
});

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
