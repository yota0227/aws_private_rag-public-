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
  "BOS-AI RAG 지식 베이스에 질의합니다. 업로드된 SoC 코드, 스펙 문서 등을 검색하여 답변합니다. team/category로 검색 범위를 좁힐 수 있습니다.",
  {
    query: { type: "string", description: "질의 내용 (한국어/영어 모두 가능)" },
    team: { type: "string", description: "팀 필터 (예: soc). 생략 시 전체 검색" },
    category: { type: "string", description: "카테고리 필터 (예: code, spec). 생략 시 전체 검색" },
    source_system: { type: "string", description: "소스 시스템 필터 (예: manual_upload, codebeamer). 생략 시 전체 검색" }
  },
  async (params) => {
    try {
      const body = { query: params.query };
      const filter = {};
      if (params.team) filter.team = params.team;
      if (params.category) filter.category = params.category;
      if (params.source_system) filter.source_system = params.source_system;
      if (Object.keys(filter).length > 0) body.filter = filter;

      const resp = await ragApi("POST", "/query", body);
      if (resp.error) {
        return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
      }
      let text = resp.answer || resp.message || JSON.stringify(resp);
      if (resp.citations && resp.citations.length > 0) {
        text += "\n\n--- 참조 문서 ---";
        resp.citations.forEach((c, i) => {
          if (c.references && c.references.length > 0) {
            c.references.forEach((ref, j) => {
              const uri = typeof ref === "string" ? ref : ref.uri || "";
              const score = ref.score ? ` (score: ${ref.score})` : "";
              text += `\n[${i + 1}.${j + 1}] ${uri}${score}`;
            });
          }
        });
      }
      if (resp.metadata) {
        text += `\n\n검색 유형: ${resp.metadata.search_type}, 응답 시간: ${resp.metadata.response_time_ms}ms`;
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

// QuickSight 클라이언트 (VPC Endpoint 경유 - Private DNS)
const { QuickSightClient, ListDashboardsCommand, DescribeDashboardCommand } = require("@aws-sdk/client-quicksight");

const QS_REGION = process.env.QS_REGION || "ap-northeast-2";
const QS_ACCOUNT_ID = process.env.QS_ACCOUNT_ID || "";

// QuickSight 클라이언트 - VPC Endpoint Private DNS 자동 사용 (Private DNS ON 설정됨)
const qsClient = new QuickSightClient({ region: QS_REGION });

// Tool 4: Quick 대시보드 목록 조회
mcpServer.tool(
  "quick_dashboard_list",
  "Amazon Quick(QuickSight) 대시보드 목록을 조회합니다. RAG 성능, 질의 현황, 시스템 모니터링 대시보드를 확인할 수 있습니다.",
  {},
  async () => {
    try {
      const cmd = new ListDashboardsCommand({ AwsAccountId: QS_ACCOUNT_ID });
      const resp = await qsClient.send(cmd);
      const dashboards = resp.DashboardSummaryList || [];

      if (dashboards.length === 0) {
        return { content: [{ type: "text", text: "등록된 Quick 대시보드가 없습니다." }] };
      }

      let text = `Quick 대시보드 목록 (총 ${dashboards.length}개):\n`;
      dashboards.forEach((d, i) => {
        text += `\n[${i + 1}] ${d.Name}`;
        text += `\n    ID: ${d.DashboardId}`;
        text += `\n    최종 수정: ${d.LastUpdatedTime ? new Date(d.LastUpdatedTime).toLocaleString("ko-KR") : "-"}`;
      });
      text += "\n\n대시보드 상세 데이터는 quick_dashboard_data 도구를 사용하세요.";

      return { content: [{ type: "text", text }] };
    } catch (err) {
      console.error("[Quick] dashboard_list error:", err.message);
      return { content: [{ type: "text", text: `Quick 대시보드 목록 조회 실패: ${err.message}` }], isError: true };
    }
  }
);

// Tool 5: Quick 대시보드 데이터 조회
mcpServer.tool(
  "quick_dashboard_data",
  "지정된 Quick(QuickSight) 대시보드의 상세 정보와 데이터셋 요약을 조회합니다.",
  {
    dashboardId: { type: "string", description: "대시보드 ID (quick_dashboard_list로 확인 가능)" }
  },
  async (params) => {
    try {
      const cmd = new DescribeDashboardCommand({
        AwsAccountId: QS_ACCOUNT_ID,
        DashboardId: params.dashboardId
      });
      const resp = await qsClient.send(cmd);
      const d = resp.Dashboard;

      if (!d) {
        return { content: [{ type: "text", text: `대시보드를 찾을 수 없습니다: ${params.dashboardId}` }], isError: true };
      }

      const version = d.Version || {};
      let text = `📊 ${d.Name}\n`;
      text += `\nID: ${d.DashboardId}`;
      text += `\n상태: ${version.Status || "-"}`;
      text += `\n설명: ${version.Description || "없음"}`;
      text += `\n생성일: ${d.CreatedTime ? new Date(d.CreatedTime).toLocaleString("ko-KR") : "-"}`;
      text += `\n최종 수정: ${d.LastUpdatedTime ? new Date(d.LastUpdatedTime).toLocaleString("ko-KR") : "-"}`;

      if (version.DataSetArns && version.DataSetArns.length > 0) {
        text += `\n\n연결된 데이터셋 (${version.DataSetArns.length}개):`;
        version.DataSetArns.forEach((arn, i) => {
          const datasetId = arn.split("/").pop();
          text += `\n  [${i + 1}] ${datasetId}`;
        });
      }

      if (version.Errors && version.Errors.length > 0) {
        text += `\n\n⚠️ 오류 (${version.Errors.length}개):`;
        version.Errors.forEach((e) => {
          text += `\n  - ${e.Type}: ${e.Message}`;
        });
      }

      return { content: [{ type: "text", text }] };
    } catch (err) {
      console.error("[Quick] dashboard_data error:", err.message);
      return { content: [{ type: "text", text: `Quick 대시보드 데이터 조회 실패: ${err.message}` }], isError: true };
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
