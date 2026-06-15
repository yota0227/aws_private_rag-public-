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

const { z } = require("zod");

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
    "BOS-AI RAG 지식 베이스에 질의합니다. 문서 내용 검색, 키워드 검색, 기술 질문 등 모든 지식 검색은 이 툴을 사용하세요. 파일명을 몰라도 됩니다 — 키워드나 자연어로 질의하면 관련 문서를 찾아 답변합니다. 업로드된 SoC 코드, 스펙 문서, 주간 보고서 등을 검색합니다.",
    { query: z.string().describe("질의 내용 (한국어/영어 모두 가능)") },
    async (args, extra) => {
      try {
        console.log("[TOOL] rag_query: " + args.query);
        const resp = await ragApi("POST", "/query", { query: args.query });
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
    "업로드된 RAG 문서의 파일 목록을 조회합니다. 어떤 파일이 등록되어 있는지 확인하거나 파일 관리(삭제 등) 목적으로만 사용하세요. 문서 내용 검색이나 질문 답변은 rag_query를 사용하세요.",
    {
      team: z.string().optional().describe("팀 필터 (예: soc). 생략 시 전체 조회"),
      category: z.string().optional().describe("카테고리 필터 (예: code, spec). 생략 시 전체 조회")
    },
    async (args, extra) => {
      try {
        console.log("[TOOL] rag_list_documents: team=" + (args.team||"all") + " category=" + (args.category||"all"));
        let path = "/documents";
        const qs = [];
        if (args.team) qs.push("team=" + encodeURIComponent(args.team));
        if (args.category) qs.push("category=" + encodeURIComponent(args.category));
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
      team: z.string().optional().describe("팀 필터 (선택)"),
      category: z.string().optional().describe("카테고리 필터 (선택)")
    },
    async (args, extra) => {
      try {
        console.log("[TOOL] rag_upload_status: team=" + (args.team||"all") + " category=" + (args.category||"all"));
        let path = "/documents";
        const qs = [];
        if (args.team) qs.push("team=" + encodeURIComponent(args.team));
        if (args.category) qs.push("category=" + encodeURIComponent(args.category));
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
      task_id: z.string().describe("Extraction Task ID (필수)")
    },
    async (args, extra) => {
      try {
        console.log("[TOOL] rag_extract_status: task_id=" + args.task_id);
        const resp = await ragApi("GET", "/documents/extract-status?task_id=" + encodeURIComponent(args.task_id));
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
      s3_key: z.string().describe("삭제할 파일의 S3 키 (예: documents/soc/code/filename.pdf)")
    },
    async (args, extra) => {
      try {
        console.log("[TOOL] rag_delete_document: s3_key=" + args.s3_key);
        const resp = await ragApi("POST", "/documents/delete", { s3_key: args.s3_key });
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

  // ========================================================================
  // Phase 3: MCP Tool 분리 — search_archive, get_evidence, list_verified_claims
  // + search_rtl (v9.1: with client-side dedup)
  // Requirements: 8.1, 8.2, 8.3, 8.6
  // ========================================================================

  // v9.1: Client-side dedup helper functions
  function dedupResults(results, maxResults) {
    const seen = new Set();
    const deduped = [];
    for (const r of results) {
      const fp = getResultFingerprint(r);
      if (seen.has(fp)) continue;
      seen.add(fp);
      deduped.push(r);
      if (deduped.length >= maxResults) break;
    }
    if (deduped.length < results.length) {
      console.log("[DEDUP] " + results.length + " → " + deduped.length + " (removed " + (results.length - deduped.length) + " duplicates)");
    }
    return deduped;
  }

  function getResultFingerprint(r) {
    const type = r.analysis_type || "";
    if (type === "claim") {
      return "claim:" + (r.claim_text || "").substring(0, 200);
    } else if (type === "hdd_section") {
      return "hdd:" + (r.topic || "") + ":" + (r.hdd_section_title || "");
    } else if (type === "module_parse" || type === "module_parse_chunk") {
      return "mp:" + (r.module_name || "") + ":" + type + ":" + (r.sub_record_type || "");
    } else {
      const basename = (r.file_path || "").split("/").pop() || "";
      return "other:" + (r.module_name || "") + ":" + basename;
    }
  }

  mcp.tool(
    "search_rtl",
    "RTL 및 SoC 설계 데이터를 검색합니다. 모듈명, 포트, 인스턴스, 토픽 등으로 검색 가능합니다. RTL 코드뿐 아니라 firmware 헤더, 레지스터맵(SVD/JSON), 설계 문서(MD/RST), timing constraint(SDC), device tree(DTS), filelist hierarchy 등도 검색됩니다.",
    {
      query: z.string().describe("검색어 (모듈명, 신호명, 레지스터명, 키워드 등)"),
      pipeline_id: z.string().optional().describe("파이프라인 ID 필터 (예: tt_20260221, tt_20260516). 생략 시 전체 검색"),
      topic: z.string().optional().describe("토픽 필터 (예: NoC, FPU, EDC, Overlay, Hierarchy). 생략 시 전체 검색"),
      max_results: z.number().optional().default(50).describe("최대 결과 수 (기본값: 50)")
    },
    async (args, extra) => {
      const startTime = Date.now();
      try {
        const requestedMax = args.max_results || 50;
        console.log("[TOOL] search_rtl: query=" + args.query + " pipeline_id=" + (args.pipeline_id||"all") + " topic=" + (args.topic||"all") + " max=" + requestedMax);
        const body = { query: args.query, source: "rtl_parsed", max_results: Math.min(requestedMax * 3, 200) };
        if (args.pipeline_id) body.pipeline_id = args.pipeline_id;
        if (args.topic) body.topic = args.topic;

        const resp = await ragApi("POST", "/search-archive", body);
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };

        const rawResults = resp.results || [];
        const totalHits = resp.total_hits || 0;
        const results = dedupResults(rawResults, requestedMax);

        if (results.length === 0) {
          return { content: [{ type: "text", text: "\"" + args.query + "\" 검색 결과가 없습니다. (total_hits: " + totalHits + ")" }] };
        }

        let text = "RTL 검색 결과 (" + results.length + "/" + totalHits + "건):\n";
        results.forEach(function(r, i) {
          text += "\n[" + (i+1) + "] " + (r.module_name || "(no name)");
          if (r.topic) text += " | 토픽: " + (Array.isArray(r.topic) ? r.topic.join(", ") : r.topic);
          if (r.analysis_type) text += " | 유형: " + r.analysis_type;
          if (r.pipeline_id) text += " | 파이프라인: " + r.pipeline_id;
          // Signal path edge rendering
          if (r.analysis_type === "signal_path_edge") {
            text += "\n    " + (r.edge_type || "") + ": `" + (r.src || "") + "` → `" + (r.dst || "") + "`";
            if (r.category) text += " [" + r.category + "]";
            if (r.raw_text) text += "\n    evidence: " + r.raw_text.substring(0, 300);
          }
          // Phase 2/3: 보조 파일 타입 렌더링
          if (r.analysis_type === "filelist_hierarchy") {
            text += "\n    📂 " + (r.claim_text || "");
            if (r.instance_list) text += "\n    파일: " + r.instance_list.substring(0, 300) + (r.instance_list.length > 300 ? "..." : "");
          }
          if (["config_data", "register_map", "firmware_header", "firmware_source", "documentation", "design_constraint", "device_tree", "script", "structured_data"].indexOf(r.analysis_type) >= 0) {
            text += "\n    📄 [" + r.analysis_type + "] " + (r.parsed_summary || "").substring(0, 300);
          }
          if (r.claim_text) text += "\n    Claim: " + r.claim_text.substring(0, 500);
          if (r.claim_type) text += " [" + r.claim_type + "]";
          if (r.hdd_section_title) text += "\n    HDD: " + r.hdd_section_title;
          if (r.hdd_content) text += "\n    " + r.hdd_content.substring(0, 800);
          if (r.port_list) text += "\n    포트: " + r.port_list.substring(0, 800) + (r.port_list.length > 800 ? "..." : "");
          if (r.instance_list) text += "\n    인스턴스: " + r.instance_list.substring(0, 800) + (r.instance_list.length > 800 ? "..." : "");
          if (r.parameter_list) text += "\n    파라미터: " + r.parameter_list;
          if (r.file_path) text += "\n    파일: " + r.file_path;
        });
        text += "\n\nexecution_time_ms: " + execution_time_ms;
        return { content: [{ type: "text", text: text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: "RTL 검색 실패: " + err.message }], isError: true };
      }
    }
  );

  mcp.tool(
    "search_archive",
    "Archive 문서를 검색합니다. Bedrock KB 벡터 검색 + topic/source 메타데이터 필터를 지원합니다. 특정 주제나 출처의 문서를 찾을 때 사용하세요.",
    {
      query: z.string().describe("검색 질의 (한국어/영어 모두 가능)"),
      topic: z.string().optional().describe("topic 필터 (예: ucie/phy/ltssm)"),
      source: z.string().optional().describe("source 필터 (예: archive_md, rtl_parsed, manual_upload)"),
      max_results: z.number().optional().default(5).describe("최대 결과 수 (기본값 5)")
    },
    async (args, extra) => {
      const startTime = Date.now();
      try {
        console.log("[TOOL] search_archive: query=" + args.query + " topic=" + (args.topic||"all") + " source=" + (args.source||"all"));
        const body = { query: args.query };
        if (args.topic) body.topic = args.topic;
        if (args.source) body.source = args.source;
        if (args.max_results) body.max_results = args.max_results;
        const resp = await ragApi("POST", "/search-archive", body);
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error, execution_time_ms }) }], isError: true };
        let text = "📚 Archive 검색 결과 (" + (resp.count || 0) + "건)\n";
        text += "질의: " + args.query + "\n";
        if (resp.filters) text += "필터: " + JSON.stringify(resp.filters) + "\n";
        text += "\n" + (resp.answer || "결과 없음");
        if (resp.results && resp.results.length > 0) {
          text += "\n\n--- 참조 문서 ---";
          resp.results.forEach((r, i) => {
            text += "\n[" + (i+1) + "] " + (r.uri || "unknown");
            if (r.score) text += " (score: " + r.score + ")";
          });
        }
        text += "\n\nexecution_time_ms: " + execution_time_ms;
        return { content: [{ type: "text", text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: JSON.stringify({ error: "search_archive 실패: " + err.message, execution_time_ms }) }], isError: true };
      }
    }
  );

  mcp.tool(
    "get_evidence",
    "특정 Claim의 근거(evidence) 배열을 조회합니다. claim_id로 해당 claim의 원본 문서 참조, 인용 텍스트, 페이지 번호 등을 확인할 수 있습니다.",
    {
      claim_id: z.string().describe("조회할 Claim ID (UUID)")
    },
    async (args, extra) => {
      const startTime = Date.now();
      try {
        console.log("[TOOL] get_evidence: claim_id=" + args.claim_id);
        const resp = await ragApi("POST", "/get-evidence", { claim_id: args.claim_id });
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error, execution_time_ms }) }], isError: true };
        let text = "📋 Evidence 조회 결과\n";
        text += "  Claim ID: " + resp.claim_id + "\n";
        text += "  Version: " + resp.version + "\n";
        text += "  Evidence 수: " + (resp.evidence_count || 0) + "\n";
        if (resp.evidence && resp.evidence.length > 0) {
          resp.evidence.forEach((ev, i) => {
            text += "\n  [Evidence " + (i+1) + "]\n";
            text += "    Source: " + (ev.source_document_id || "unknown") + "\n";
            text += "    Type: " + (ev.source_type || "unknown") + "\n";
            text += "    Chunk: " + (ev.source_chunk || "").substring(0, 200) + "\n";
            if (ev.page_number) text += "    Page: " + ev.page_number + "\n";
            if (ev.source_path) text += "    Path: " + ev.source_path + "\n";
            if (ev.line_start) text += "    Lines: " + ev.line_start + "-" + (ev.line_end || "") + "\n";
          });
        }
        text += "\nexecution_time_ms: " + execution_time_ms;
        return { content: [{ type: "text", text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: JSON.stringify({ error: "get_evidence 실패: " + err.message, execution_time_ms }) }], isError: true };
      }
    }
  );

  mcp.tool(
    "list_verified_claims",
    "특정 topic의 검증된(verified) Claim 목록을 조회합니다. 해당 주제에 대해 검증 완료된 지식 단위를 확인할 수 있습니다.",
    {
      topic: z.string().describe("topic 식별자 (예: ucie/phy/ltssm)")
    },
    async (args, extra) => {
      const startTime = Date.now();
      try {
        console.log("[TOOL] list_verified_claims: topic=" + args.topic);
        const resp = await ragApi("POST", "/list-verified-claims", { topic: args.topic });
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error, execution_time_ms }) }], isError: true };
        let text = "✅ 검증된 Claim 목록 (topic: " + resp.topic + ")\n";
        text += "총 " + (resp.count || 0) + "건\n";
        if (resp.claims && resp.claims.length > 0) {
          resp.claims.forEach((c, i) => {
            text += "\n[" + (i+1) + "] " + c.claim_id + " (v" + c.version + ")\n";
            text += "    Statement: " + (c.statement || "").substring(0, 150) + "\n";
            text += "    Confidence: " + c.confidence + "\n";
            text += "    Last Verified: " + (c.last_verified_at || "unknown") + "\n";
            text += "    Evidence Count: " + (c.evidence_count || 0) + "\n";
          });
        } else {
          text += "\n해당 topic에 검증된 claim이 없습니다.";
        }
        text += "\n\nexecution_time_ms: " + execution_time_ms;
        return { content: [{ type: "text", text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: JSON.stringify({ error: "list_verified_claims 실패: " + err.message, execution_time_ms }) }], isError: true };
      }
    }
  );

  // ========================================================================
  // Phase 4: MCP Tool 확장 — generate_hdd_section, publish_markdown
  // Requirements: 10.1, 10.4
  // ========================================================================

  mcp.tool(
    "generate_hdd_section",
    "검증된 claim을 기반으로 HDD(Hardware Design Description) 섹션을 자동 생성합니다. 특정 topic의 검증+승인된 claim을 조합하여 마크다운 형식의 기술 문서 섹션을 생성합니다.",
    {
      topic: z.string().describe("topic 식별자 (예: ucie/phy/ltssm)"),
      section_title: z.string().describe("생성할 HDD 섹션 제목"),
      include_evidence: z.boolean().optional().default(true).describe("evidence 각주 포함 여부 (기본값 true)")
    },
    async (args, extra) => {
      const startTime = Date.now();
      try {
        console.log("[TOOL] generate_hdd_section: topic=" + args.topic + " title=" + args.section_title + " evidence=" + args.include_evidence);
        const body = {
          topic: args.topic,
          section_title: args.section_title,
          include_evidence: args.include_evidence
        };
        const resp = await ragApi("POST", "/generate-hdd", body);
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error, execution_time_ms }) }], isError: true };
        let text = "📝 HDD 섹션 생성 완료\n";
        text += "  Topic: " + resp.topic + "\n";
        text += "  섹션 제목: " + resp.section_title + "\n";
        text += "  사용된 Claim 수: " + (resp.claims_used || 0) + "\n";
        text += "  Evidence 포함: " + (resp.include_evidence ? "예" : "아니오") + "\n";
        text += "  면책 조항: " + (resp.disclaimer || "") + "\n";
        text += "\n--- 생성된 마크다운 ---\n\n";
        text += resp.markdown || "(내용 없음)";
        text += "\n\nexecution_time_ms: " + execution_time_ms;
        return { content: [{ type: "text", text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: JSON.stringify({ error: "generate_hdd_section 실패: " + err.message, execution_time_ms }) }], isError: true };
      }
    }
  );

  mcp.tool(
    "publish_markdown",
    "마크다운 콘텐츠를 Seoul S3의 published/ 접두사에 저장하여 출판합니다. 메타데이터가 자동 생성됩니다 (source=system_generated, generation_basis=verified_claims).",
    {
      content: z.string().describe("출판할 마크다운 콘텐츠"),
      filename: z.string().describe("저장할 파일명 (예: ucie_phy_hdd.md)"),
      topic: z.string().optional().describe("관련 topic (지정 시 해당 topic의 claim 승인 상태를 확인)")
    },
    async (args, extra) => {
      const startTime = Date.now();
      try {
        console.log("[TOOL] publish_markdown: filename=" + args.filename + " topic=" + (args.topic || "none"));
        const body = {
          content: args.content,
          filename: args.filename
        };
        if (args.topic) body.topic = args.topic;
        const resp = await ragApi("POST", "/publish-markdown", body);
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error, execution_time_ms }) }], isError: true };
        let text = "📄 마크다운 출판 완료\n";
        text += "  S3 Key: " + resp.s3_key + "\n";
        text += "  Bucket: " + resp.bucket + "\n";
        text += "  파일명: " + resp.filename + "\n";
        text += "  Topic: " + (resp.topic || "general") + "\n";
        text += "  메타데이터: " + resp.metadata_key + "\n";
        text += "  Source: " + resp.source + "\n";
        text += "  Generation Basis: " + resp.generation_basis + "\n";
        text += "\nexecution_time_ms: " + execution_time_ms;
        return { content: [{ type: "text", text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: JSON.stringify({ error: "publish_markdown 실패: " + err.message, execution_time_ms }) }], isError: true };
      }
    }
  );

  // ========================================================================
  // Phase 6: MCP Tool 확장 — Neptune Graph DB 도구
  // Requirements: 16.9, 16.10, 16.11
  // ========================================================================

  mcp.tool(
    "trace_signal_path",
    "RTL 모듈의 신호 전파 경로를 추적합니다. Neptune Graph DB에서 신호가 어떤 모듈/포트를 거쳐 전파되는지 경로를 반환합니다.",
    {
      module_name: z.string().describe("시작 모듈명 (예: BLK_UCIE)"),
      signal_name: z.string().describe("추적할 신호명 (예: tx_data)")
    },
    async (args, extra) => {
      const startTime = Date.now();
      try {
        console.log("[TOOL] trace_signal_path: module_name=" + args.module_name + " signal_name=" + args.signal_name);
        const resp = await ragApi("POST", "/trace-signal-path", { module_name: args.module_name, signal_name: args.signal_name });
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error, execution_time_ms }) }], isError: true };
        let text = "🔍 신호 전파 경로 추적\n";
        text += "  모듈: " + args.module_name + "\n";
        text += "  신호: " + args.signal_name + "\n";
        const paths = resp.signal_path || [];
        text += "  경로 수: " + paths.length + "\n";
        if (paths.length > 0) {
          text += "\n--- 경로 ---\n";
          paths.forEach((p, i) => {
            if (p.nodes && p.nodes.length > 0) {
              text += "  [" + (i+1) + "] " + p.nodes.map(n => (n.name || n)).join(" → ") + "\n";
            } else if (p.hierarchy) {
              text += "  [" + (i+1) + "] " + (Array.isArray(p.hierarchy) ? p.hierarchy.join(" → ") : p.hierarchy) + "\n";
            } else {
              text += "  [" + (i+1) + "] " + JSON.stringify(p) + "\n";
            }
          });
        } else {
          text += "\n해당 신호의 전파 경로를 찾을 수 없습니다.";
        }
        text += "\n\nexecution_time_ms: " + execution_time_ms;
        return { content: [{ type: "text", text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: JSON.stringify({ error: "trace_signal_path 실패: " + err.message, execution_time_ms }) }], isError: true };
      }
    }
  );

  mcp.tool(
    "find_instantiation_tree",
    "RTL 모듈의 인스턴스화 트리를 조회합니다. 지정된 모듈이 어떤 하위 모듈을 인스턴스화하는지 트리 구조로 반환합니다.",
    {
      module_name: z.string().describe("조회할 모듈명 (예: BLK_UCIE)"),
      depth: z.number().optional().default(3).describe("탐색 깊이 (기본값 3)")
    },
    async (args, extra) => {
      const startTime = Date.now();
      try {
        console.log("[TOOL] find_instantiation_tree: module_name=" + args.module_name + " depth=" + args.depth);
        const resp = await ragApi("POST", "/find-instantiation-tree", { module_name: args.module_name, depth: args.depth });
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error, execution_time_ms }) }], isError: true };
        let text = "🌳 인스턴스화 트리\n";
        text += "  루트 모듈: " + args.module_name + "\n";
        text += "  탐색 깊이: " + args.depth + "\n";
        const treeData = resp.instantiation_tree || resp.tree || resp.nodes || [];
        text += "  총 노드 수: " + treeData.length + "\n";
        if (treeData.length > 0) {
          text += "\n--- 트리 구조 ---\n";
          treeData.forEach((node, i) => {
            if (node.hierarchy && Array.isArray(node.hierarchy)) {
              const indent = "  ".repeat(node.depth || 1);
              text += indent + node.hierarchy.join(" → ") + "\n";
            } else if (node.module_name) {
              const indent = "  ".repeat((node.depth || 0) + 1);
              text += indent + (node.instance_name ? node.instance_name + ": " : "") + node.module_name + "\n";
            } else {
              text += "  " + JSON.stringify(node) + "\n";
            }
          });
        } else {
          text += "\n해당 모듈의 인스턴스화 트리를 찾을 수 없습니다.";
        }
        text += "\n\nexecution_time_ms: " + execution_time_ms;
        return { content: [{ type: "text", text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: JSON.stringify({ error: "find_instantiation_tree 실패: " + err.message, execution_time_ms }) }], isError: true };
      }
    }
  );

  mcp.tool(
    "find_clock_crossings",
    "RTL 모듈의 클럭 도메인 크로싱 신호 목록을 조회합니다. 서로 다른 클럭 도메인 간 전달되는 신호를 식별합니다.",
    {
      module_name: z.string().describe("조회할 모듈명 (예: BLK_UCIE)")
    },
    async (args, extra) => {
      const startTime = Date.now();
      try {
        console.log("[TOOL] find_clock_crossings: module_name=" + args.module_name);
        const resp = await ragApi("POST", "/find-clock-crossings", { module_name: args.module_name });
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error, execution_time_ms }) }], isError: true };
        let text = "⚡ 클럭 도메인 크로싱 신호\n";
        text += "  모듈: " + args.module_name + "\n";
        text += "  크로싱 신호 수: " + (resp.crossings ? resp.crossings.length : 0) + "\n";
        if (resp.crossings && resp.crossings.length > 0) {
          text += "\n--- 크로싱 신호 목록 ---\n";
          resp.crossings.forEach((c, i) => {
            text += "  [" + (i+1) + "] " + (c.signal_name || "unknown") + "\n";
            text += "      Source Domain: " + (c.source_domain || "unknown") + "\n";
            text += "      Destination Domain: " + (c.destination_domain || "unknown") + "\n";
            if (c.synchronizer) text += "      Synchronizer: " + c.synchronizer + "\n";
          });
        } else {
          text += "\n해당 모듈에서 클럭 도메인 크로싱 신호를 찾을 수 없습니다.";
        }
        text += "\n\nexecution_time_ms: " + execution_time_ms;
        return { content: [{ type: "text", text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: JSON.stringify({ error: "find_clock_crossings 실패: " + err.message, execution_time_ms }) }], isError: true };
      }
    }
  );

  // ========================================================================
  // Phase 9: Graph Export 도구
  // Requirements: 32.1, 32.5
  // ========================================================================

  mcp.tool(
    "graph_export",
    "Neptune 그래프의 부분집합을 JSON으로 내보냅니다. Chip/Module/Signal 3가지 scope로 그래프를 조회하여 Schematic Viewer 및 외부 분석 도구에서 활용할 수 있습니다.",
    {
      scope: z.enum(["chip", "module", "signal"]).describe("조회 범위: chip(최상위 인스턴스), module(내부 상세), signal(신호 전파 경로)"),
      root_module: z.string().describe("시작 모듈명 (예: BLK_UCIE)"),
      depth: z.number().optional().default(3).describe("탐색 깊이 (기본값 3, scope=module 시 무시)"),
      signal_filter: z.string().optional().describe("신호 필터 (scope=signal 시 필수)")
    },
    async (args, extra) => {
      const startTime = Date.now();
      try {
        console.log("[TOOL] graph_export: scope=" + args.scope + " root_module=" + args.root_module + " depth=" + args.depth + " signal_filter=" + (args.signal_filter || "none"));
        const body = { scope: args.scope, root_module: args.root_module };
        if (args.depth !== undefined) body.depth = args.depth;
        if (args.signal_filter) body.signal_filter = args.signal_filter;
        const resp = await ragApi("POST", "/graph-export", body);
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error, execution_time_ms }) }], isError: true };
        let text = "📊 Graph Export 결과\n";
        text += "  Scope: " + args.scope + "\n";
        text += "  Root Module: " + args.root_module + "\n";
        text += "  Depth: " + (args.depth || 3) + "\n";
        if (args.signal_filter) text += "  Signal Filter: " + args.signal_filter + "\n";
        const metadata = resp.metadata || {};
        text += "  노드 수: " + (metadata.node_count || (resp.nodes ? resp.nodes.length : 0)) + "\n";
        text += "  엣지 수: " + (metadata.edge_count || (resp.edges ? resp.edges.length : 0)) + "\n";
        if (metadata.truncated) text += "  ⚠️ 노드 상한(1000개) 초과 — 상위 노드만 반환됨\n";
        if (metadata.neptune_fallback) text += "  ⚠️ Neptune 불가용 — 빈 그래프 반환\n";
        if (resp.nodes && resp.nodes.length > 0) {
          text += "\n--- 노드 (상위 10개) ---\n";
          resp.nodes.slice(0, 10).forEach((node, i) => {
            text += "  [" + (i+1) + "] " + (node.label || node.id || "unknown") + " (type: " + (node.type || "unknown") + ")\n";
          });
          if (resp.nodes.length > 10) text += "  ... 외 " + (resp.nodes.length - 10) + "개\n";
        }
        if (resp.edges && resp.edges.length > 0) {
          text += "\n--- 엣지 (상위 10개) ---\n";
          resp.edges.slice(0, 10).forEach((edge, i) => {
            text += "  [" + (i+1) + "] " + (edge.source || "?") + " —[" + (edge.label || "?") + "]→ " + (edge.target || "?") + "\n";
          });
          if (resp.edges.length > 10) text += "  ... 외 " + (resp.edges.length - 10) + "개\n";
        }
        if ((!resp.nodes || resp.nodes.length === 0) && (!resp.edges || resp.edges.length === 0)) {
          text += "\n그래프 데이터가 없습니다.";
        }
        text += "\n\nexecution_time_ms: " + execution_time_ms;
        return { content: [{ type: "text", text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: JSON.stringify({ error: "graph_export 실패: " + err.message, execution_time_ms }) }], isError: true };
      }
    }
  );

  // regenerate_stale_hdd — Stale HDD 일괄 재생성 (Requirements 34.8)
  mcp.tool(
    "regenerate_stale_hdd",
    "Stale 상태의 HDD 통합본 섹션을 일괄 재생성합니다. topic 전파로 인해 stale 마킹된 섹션들을 최신 claim 기반으로 다시 생성하고 placeholder를 실명으로 복구합니다.",
    {},
    async (args, extra) => {
      const startTime = Date.now();
      try {
        console.log("[TOOL] regenerate_stale_hdd: triggered");
        const resp = await ragApi("POST", "/hdd/regenerate-stale", {});
        const execution_time_ms = Date.now() - startTime;
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error, execution_time_ms }) }], isError: true };
        let text = "🔄 Stale HDD 재생성 결과\n";
        text += "  재생성 완료: " + (resp.sections_regenerated || 0) + "개 섹션\n";
        text += "  건너뛴 섹션: " + (resp.sections_skipped || 0) + "개\n";
        text += "  미해결 placeholder: " + (resp.unresolved_placeholder_count || 0) + "개\n";
        text += "  실행 시간: " + execution_time_ms + "ms\n";
        if (resp.sections_regenerated === 0 && resp.sections_skipped === 0) {
          text += "\n  ℹ️ stale 상태의 HDD 섹션이 없습니다.";
        }
        return { content: [{ type: "text", text }] };
      } catch(err) {
        const execution_time_ms = Date.now() - startTime;
        return { content: [{ type: "text", text: JSON.stringify({ error: "regenerate_stale_hdd 실패: " + err.message, execution_time_ms }) }], isError: true };
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
