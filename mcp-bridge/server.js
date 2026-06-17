/**
 * BOS-AI RAG MCP Bridge
 * 
 * MCP Server → Lambda 직접 invoke → Qdrant/Neptune/Bedrock KB
 * API Gateway 제거됨 (2026-05-29) — Lambda 직접 invoke로 전환
 */
const express = require("express");
const http = require("http");
const https = require("https");
const crypto = require("crypto");
const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const { StreamableHTTPServerTransport } = require("@modelcontextprotocol/sdk/server/streamableHttp.js");
const { SSEServerTransport } = require("@modelcontextprotocol/sdk/server/sse.js");

const { z } = require("zod");

// 횡단 관심사 lib 모듈 (Task 6/7/4에서 구현됨) — withTool 래퍼가 사용한다.
const logging = require("./lib/logging");
const metrics = require("./lib/metrics");
const errors = require("./lib/errors");

// 출력 품질 lib 모듈 (Task 10.2/11/12) — 도구 설명·envelope·Resource_URI.
const envelope = require("./lib/envelope");
const uri = require("./lib/uri");
const { TOOL_DESCRIPTIONS } = require("./lib/tool-descriptions");

// Evidence-first lib 모듈 (Task 13) — 문장 분할·coverage·가드 프리미티브.
const evidence = require("./lib/evidence");

// 비동기 Job 프레임워크 (Task 16) — dispatcher + 상태 저장소.
// rag_task_status(16.5)와 regenerate_stale_hdd(16.7)가 동일 store를 공유하도록
// 모듈 수준에서 단일 dispatcher/store를 생성한다.
const { createDispatcher } = require("./lib/jobs/dispatcher");
const { defaultStore, JOB_STATUS } = require("./lib/jobs/store");
const jobDispatcher = createDispatcher({ store: defaultStore });

const PORT = process.env.PORT || 3100;
const AWS_REGION = process.env.AWS_REGION || "ap-northeast-2";
const LAMBDA_FUNCTION = process.env.LAMBDA_FUNCTION || "lambda-document-processor-seoul-prod";
const RTL_LAMBDA_FUNCTION = process.env.RTL_LAMBDA_FUNCTION || "lambda-rtl-parser-seoul-dev";

// AWS SDK Lambda client (lazy init)
let _lambdaClient = null;
function getLambdaClient() {
  if (!_lambdaClient) {
    const { LambdaClient } = require("@aws-sdk/client-lambda");
    _lambdaClient = new LambdaClient({ region: AWS_REGION });
  }
  return _lambdaClient;
}

// RAG API base URL (fallback for environments without Lambda access)
const RAG_API_BASE = process.env.RAG_API_BASE || "";

/**
 * Invoke Lambda directly (replaces API Gateway HTTP calls)
 * Formats request as API Gateway event for document-processor Lambda
 */
function ragApi(method, path, body) {
  // If RAG_API_BASE is set, use HTTP (legacy/fallback mode)
  if (RAG_API_BASE) {
    return ragApiHttp(method, path, body);
  }

  // Lambda direct invoke mode
  const { InvokeCommand } = require("@aws-sdk/client-lambda");
  const client = getLambdaClient();

  // Determine which Lambda to invoke
  // /search-rtl goes directly to rtl-parser Lambda
  const isRtlSearch = path === "/search-rtl";
  const functionName = isRtlSearch ? RTL_LAMBDA_FUNCTION : LAMBDA_FUNCTION;

  let payload;
  if (isRtlSearch) {
    // RTL Parser Lambda expects {action: "search", query, ...}
    payload = { action: "search", ...body };
  } else {
    // Document Processor Lambda expects API Gateway event format
    payload = {
      httpMethod: method,
      path: "/rag" + path,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : null,
      queryStringParameters: null,
    };
    // Handle GET with query params
    if (method === "GET" && path.includes("?")) {
      const [basePath, qs] = path.split("?");
      payload.path = "/rag" + basePath;
      const params = {};
      qs.split("&").forEach(p => { const [k,v] = p.split("="); params[k] = decodeURIComponent(v); });
      payload.queryStringParameters = params;
    }
  }

  return client.send(new InvokeCommand({
    FunctionName: functionName,
    InvocationType: "RequestResponse",
    Payload: Buffer.from(JSON.stringify(payload)),
  })).then(response => {
    const result = JSON.parse(Buffer.from(response.Payload).toString());

    if (isRtlSearch) {
      // RTL Parser returns results directly
      return result;
    }

    // Document Processor returns API Gateway response format
    if (result.statusCode && result.body) {
      try { return JSON.parse(result.body); }
      catch(e) { return { raw: result.body }; }
    }
    return result;
  }).catch(err => {
    console.error("[Lambda invoke error]", functionName, path, err.message);
    return { error: "Lambda invoke failed: " + err.message };
  });
}

/**
 * HTTP fallback (for environments without Lambda access, e.g. on-prem server02)
 */
function ragApiHttp(method, path, body) {
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

/**
 * withTool(toolName, handler) — 도구 핸들러 횡단 관심사 래퍼 (Task 8.1, Req 6.1~6.5, 6.7)
 *
 * 도구 핸들러를 감싸 다음을 일원화한다:
 *  - request_id 확보: extra/args에 들어온 값이 있으면 재사용(logging.resolveRequestId),
 *    없으면 logging.newRequestId()로 생성(resolveRequestId 내부에서 처리).
 *  - latency 측정: process.hrtime.bigint() 기준 ms.
 *  - 성공: metrics.record + 구조화 로그 1건(outcome="success"), 핸들러 결과를 그대로 반환.
 *  - 예외: metrics.record + 구조화 로그 1건(outcome="failure", error_category),
 *    errors.renderError(errors.makeError(classify, message))로 변환해 반환.
 *  - 핸들러에는 두 번째 인자로 context { request_id }를 전달해 request_id를 thread할 수 있게 한다.
 *
 * NOTE(Task 8.1): 이 단계에서는 래퍼 정의만 추가하며, 17개 도구에 적용(8.2)하지 않는다.
 *
 * @param {string} toolName 메트릭/로그 라벨로 쓰일 도구 이름
 * @param {(args: object, ctx: { request_id: string }) => Promise<any>} handler 실제 도구 핸들러
 * @returns {(args: object, extra: object) => Promise<any>} MCP가 호출하는 래핑된 핸들러
 */
function withTool(toolName, handler) {
  return async (args, extra) => {
    // 들어온 request_id 후보를 extra/args에서 탐색 (있으면 재사용, 없으면 생성).
    const incoming =
      (extra && (extra.request_id || extra.requestId)) ||
      (extra &&
        extra.requestInfo &&
        extra.requestInfo.headers &&
        (extra.requestInfo.headers["x-request-id"] ||
          extra.requestInfo.headers["mcp-request-id"])) ||
      (args && args.request_id);
    const request_id = logging.resolveRequestId(incoming);

    const start = process.hrtime.bigint();
    const elapsedMs = () => Number(process.hrtime.bigint() - start) / 1e6;

    try {
      const result = await handler(args, { request_id });
      const latency_ms = elapsedMs();
      metrics.record(toolName, latency_ms);
      logging.emit({
        request_id,
        tool: toolName,
        latency_ms,
        outcome: "success",
        timestamp: logging.isoUtc(),
      });
      return result;
    } catch (err) {
      const latency_ms = elapsedMs();
      metrics.record(toolName, latency_ms);
      const error_category = errors.classify(err);
      logging.emit({
        request_id,
        tool: toolName,
        latency_ms,
        outcome: "failure",
        error_category,
        timestamp: logging.isoUtc(),
      });
      return errors.renderError(
        errors.makeError(error_category, err && err.message)
      );
    }
  };
}

/**
 * safeBuildUri(scheme, id) -> string | null
 *
 * lib/uri.buildUri로 Resource_URI를 만들되, 잘못된 입력(빈/공백 식별자 등)이면
 * throw 대신 null을 반환한다(Task 11/12). 호출부는 null을 걸러 well-formed URI만
 * envelope에 부착한다(Req 2.1, 2.2, 8.3 / Property 7, 8).
 */
function safeBuildUri(scheme, id) {
  if (id === undefined || id === null) return null;
  const sid = String(id).trim();
  if (sid.length === 0) return null;
  try {
    return uri.buildUri(scheme, sid);
  } catch (e) {
    return null;
  }
}

/**
 * resolveEnvelopeSnapshot(resp) -> string
 *
 * 성공 응답의 resolved_snapshot을 해석한다(Req 2.4~2.6 / Property 10).
 * 현재 검색/그래프 도구에는 스냅샷 입력이 없으므로 requestedSnapshot은 undefined이며,
 * 백엔드 응답의 resolved_snapshot/snapshot을 구체값으로 사용한다. 백엔드가 구체값을
 * 주지 않거나 리터럴 "latest"면, 절대 "latest"를 내보내지 않도록 index_version 기반의
 * 안전한 구체 식별자("unknown" 포함)로 fallback한다(OQ-1).
 */
function resolveEnvelopeSnapshot(resp) {
  let backendResolved = (resp && (resp.resolved_snapshot || resp.snapshot)) || "";
  backendResolved =
    typeof backendResolved === "string" ? backendResolved : String(backendResolved);
  if (backendResolved.trim().length === 0 || backendResolved === envelope.LATEST) {
    backendResolved = envelope.resolveIndexVersion(resp && resp.index_version);
  }
  return envelope.resolveSnapshot(undefined, backendResolved);
}

/**
 * withEnvelope(text, resp, resourceUris, ctx) -> MCP tool 성공 응답
 *
 * 기존 사람이 읽는 텍스트(text)를 prefix로 보존하고, 말미에 구조화 요약 블록
 * (index_version / resolved_snapshot / resource_uris? / request_id)을 덧붙인다
 * (Req 2.3~2.6, 2.10, 2.11). resourceUris 중 well-formed만 부착되고 없으면 생략된다.
 * 성공 경로 전용이며, 에러는 lib/errors 경로(renderError)로만 반환한다(Req 2.9).
 */
function withEnvelope(text, resp, resourceUris, ctx) {
  const enriched = envelope.appendEnvelope(text, {
    index_version: resp && resp.index_version,
    resolved_snapshot: resolveEnvelopeSnapshot(resp),
    resource_uris: resourceUris,
    request_id: ctx && ctx.request_id,
  });
  return { content: [{ type: "text", text: enriched }] };
}

/**
 * backendValidateAnswer(answer) -> Promise<object|null>   (Task 13.3 / 13.8)
 *
 * 백엔드의 문장별 근거 검증 엔드포인트를 호출한다.
 *
 * OQ(Open Question): 백엔드 `/validate-answer` 엔드포인트 존재 여부는 미확정이다
 * (design Open Questions에 연계). 엔드포인트가 없거나 오류면 null을 반환하여 호출부가
 * fallback(문장을 unsupported(count 0)로 표기)으로 동작하게 한다 — 즉, 검증 도구는
 * 실패하지 않고 일관된 per-sentence 결과를 반환한다.
 *
 * 응답이 per-sentence evidence를 담은 `sentences` 배열을 가질 때에만 "백엔드 가용"으로
 * 간주한다(그 외 형태/오류 응답은 fallback).
 */
function backendValidateAnswer(answer) {
  return ragApi("POST", "/validate-answer", { answer })
    .then((resp) => {
      if (resp && !resp.error) return resp;
      return null;
    })
    .catch(() => null);
}

/**
 * computeAnswerCoverage(answer) -> Promise<{ coverage, backend, backendAvailable }>
 *
 * rag_validate_answer(13.3)와 publish_markdown 가드(13.8)가 공유하는 검증 로직.
 *  1) evidence.segmentSentences로 문장 분할.
 *  2) backendValidateAnswer로 문장별 근거를 조회(가능하면).
 *  3) evidence.computeCoverage로 문장별 supported/unsupported 라벨링.
 *
 * 백엔드 가용 시(`sentences` 배열 보유) per-sentence evidence 개수를 사용하고,
 * 불가용 시 lookup이 0을 반환하여 모든 문장을 unsupported로 표기한다(OQ fallback).
 * backendAvailable 플래그를 함께 반환하여, publish 가드가 백엔드 신호가 실제로 있을
 * 때에만 미지원 문장 기준으로 발행을 거부하도록 한다(하위 호환 보존).
 */
function computeAnswerCoverage(answer) {
  const sentences = evidence.segmentSentences(answer);
  return backendValidateAnswer(answer).then((backend) => {
    const backendAvailable = !!(backend && Array.isArray(backend.sentences));
    let lookup;
    if (backendAvailable) {
      const bs = backend.sentences;
      // OQ: per-sentence 응답 형태 미확정 — evidence 배열 / evidence_count / supported를 모두 수용.
      lookup = (sentence, index) => {
        const entry = bs[index];
        if (!entry) return 0;
        if (Array.isArray(entry.evidence)) return entry.evidence.length;
        if (typeof entry.evidence_count === "number") return entry.evidence_count;
        if (typeof entry.supported === "boolean") return entry.supported ? 1 : 0;
        return 0;
      };
    } else {
      // Fallback: 백엔드 검증 엔드포인트 불가용 → 모든 문장 unsupported(count 0).
      lookup = () => 0;
    }
    const coverage = evidence.computeCoverage(sentences, lookup);
    return { coverage, backend, backendAvailable };
  });
}

function createMcpServer() {
  const mcp = new McpServer({ name: "bos-ai-rag", version: "1.0.0" });

  mcp.tool(
    "rag_query",
    TOOL_DESCRIPTIONS.rag_query,
    { query: z.string().describe("질의 내용 (한국어/영어 모두 가능)") },
    withTool("rag_query", async (args, extra) => {
      try {
        const resp = await ragApi("POST", "/query", { query: args.query });
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
        let text = resp.answer || resp.message || JSON.stringify(resp);
        const resourceUris = [];
        if (resp.citations?.length > 0) {
          text += "\n\n--- 참조 문서 ---";
          resp.citations.forEach((c, i) => {
            if (c.references?.length > 0) text += "\n[" + (i+1) + "] " + c.references.join(", ");
            if (Array.isArray(c.references)) {
              c.references.forEach((ref) => {
                const u = safeBuildUri("rag", ref);
                if (u) resourceUris.push(u);
              });
            }
          });
        }
        return withEnvelope(text, resp, resourceUris, extra);
      } catch(err) {
        return { content: [{ type: "text", text: "RAG API 호출 실패: " + err.message }], isError: true };
      }
    })
  );

  mcp.tool(
    "rag_list_documents",
    TOOL_DESCRIPTIONS.rag_list_documents,
    {
      team: z.string().optional().describe("팀 필터 (예: soc). 생략 시 전체 조회"),
      category: z.string().optional().describe("카테고리 필터 (예: code, spec). 생략 시 전체 조회")
    },
    withTool("rag_list_documents", async (args, extra) => {
      try {
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
    })
  );

  mcp.tool(
    "rag_categories",
    TOOL_DESCRIPTIONS.rag_categories,
    {},
    withTool("rag_categories", async () => {
      try {
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
    })
  );

  mcp.tool(
    "rag_upload_status",
    TOOL_DESCRIPTIONS.rag_upload_status,
    {
      team: z.string().optional().describe("팀 필터 (선택)"),
      category: z.string().optional().describe("카테고리 필터 (선택)")
    },
    withTool("rag_upload_status", async (args, extra) => {
      try {
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
    })
  );

  mcp.tool(
    "rag_extract_status",
    TOOL_DESCRIPTIONS.rag_extract_status,
    {
      task_id: z.string().describe("Extraction Task ID (필수)")
    },
    withTool("rag_extract_status", async (args, extra) => {
      try {
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
    })
  );

  mcp.tool(
    "rag_delete_document",
    TOOL_DESCRIPTIONS.rag_delete_document,
    {
      s3_key: z.string().describe("삭제할 파일의 S3 키 (예: documents/soc/code/filename.pdf)")
    },
    withTool("rag_delete_document", async (args, extra) => {
      try {
        const resp = await ragApi("POST", "/documents/delete", { s3_key: args.s3_key });
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };
        let text = "✅ 문서 삭제 완료\n";
        text += "  삭제된 파일: " + resp.key + "\n";
        text += "  KB Sync: " + (resp.kb_sync || "unknown");
        return { content: [{ type: "text", text }] };
      } catch(err) {
        return { content: [{ type: "text", text: "문서 삭제 실패: " + err.message }], isError: true };
      }
    })
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
    TOOL_DESCRIPTIONS.search_rtl,
    {
      query: z.string().describe("검색어 (모듈명, 신호명, 레지스터명, 키워드 등)"),
      pipeline_id: z.string().optional().describe("파이프라인 ID 필터 (예: tt_20260221, tt_20260516). 생략 시 전체 검색"),
      topic: z.string().optional().describe("토픽 필터 (예: NoC, FPU, EDC, Overlay, Hierarchy). 생략 시 전체 검색"),
      max_results: z.number().optional().default(50).describe("최대 결과 수 (기본값: 50)")
    },
    withTool("search_rtl", async (args, extra) => {
      try {
        const requestedMax = args.max_results || 50;
        const body = { query: args.query, max_results: Math.min(requestedMax * 3, 200) };
        if (args.pipeline_id) body.pipeline_id = args.pipeline_id;
        if (args.topic) body.topic = args.topic;

        const resp = await ragApi("POST", "/search-rtl", body);
        if (resp.error) return { content: [{ type: "text", text: "오류: " + resp.error }], isError: true };

        const rawResults = resp.results || [];
        const totalHits = resp.total_hits || 0;
        const results = dedupResults(rawResults, requestedMax);

        if (results.length === 0) {
          return withEnvelope("\"" + args.query + "\" 검색 결과가 없습니다. (total_hits: " + totalHits + ")", resp, [], extra);
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
        const resourceUris = [];
        results.forEach(function(r) {
          if (r.module_name) {
            const um = safeBuildUri("rtl", "module/" + r.module_name);
            if (um) resourceUris.push(um);
          }
          if (r.file_path) {
            const uf = safeBuildUri("rtl", "file/" + r.file_path);
            if (uf) resourceUris.push(uf);
          }
        });
        return withEnvelope(text, resp, resourceUris, extra);
      } catch(err) {
        return { content: [{ type: "text", text: "RTL 검색 실패: " + err.message }], isError: true };
      }
    })
  );

  mcp.tool(
    "search_archive",
    TOOL_DESCRIPTIONS.search_archive,
    {
      query: z.string().describe("검색 질의 (한국어/영어 모두 가능)"),
      topic: z.string().optional().describe("topic 필터 (예: ucie/phy/ltssm)"),
      source: z.string().optional().describe("source 필터 (예: archive_md, rtl_parsed, manual_upload)"),
      max_results: z.number().optional().default(5).describe("최대 결과 수 (기본값 5)")
    },
    withTool("search_archive", async (args, extra) => {
      try {
        const body = { query: args.query };
        if (args.topic) body.topic = args.topic;
        if (args.source) body.source = args.source;
        if (args.max_results) body.max_results = args.max_results;
        const resp = await ragApi("POST", "/search-archive", body);
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error }) }], isError: true };
        let text = "📚 Archive 검색 결과 (" + (resp.count || 0) + "건)\n";
        text += "질의: " + args.query + "\n";
        if (resp.filters) text += "필터: " + JSON.stringify(resp.filters) + "\n";
        text += "\n" + (resp.answer || "결과 없음");
        const resourceUris = [];
        if (resp.results && resp.results.length > 0) {
          text += "\n\n--- 참조 문서 ---";
          resp.results.forEach((r, i) => {
            text += "\n[" + (i+1) + "] " + (r.uri || "unknown");
            if (r.score) text += " (score: " + r.score + ")";
            if (r.uri) {
              if (uri.isWellFormed(r.uri)) {
                resourceUris.push(r.uri);
              } else {
                const u = safeBuildUri("rag", r.uri);
                if (u) resourceUris.push(u);
              }
            }
          });
        }
        return withEnvelope(text, resp, resourceUris, extra);
      } catch(err) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "search_archive 실패: " + err.message }) }], isError: true };
      }
    })
  );

  mcp.tool(
    "get_evidence",
    TOOL_DESCRIPTIONS.get_evidence,
    {
      claim_id: z.string().describe("조회할 Claim ID (UUID)")
    },
    withTool("get_evidence", async (args, extra) => {
      try {
        const resp = await ragApi("POST", "/get-evidence", { claim_id: args.claim_id });
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error }) }], isError: true };
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
        return { content: [{ type: "text", text }] };
      } catch(err) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "get_evidence 실패: " + err.message }) }], isError: true };
      }
    })
  );

  mcp.tool(
    "list_verified_claims",
    TOOL_DESCRIPTIONS.list_verified_claims,
    {
      topic: z.string().describe("topic 식별자 (예: ucie/phy/ltssm)")
    },
    withTool("list_verified_claims", async (args, extra) => {
      try {
        const resp = await ragApi("POST", "/list-verified-claims", { topic: args.topic });
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error }) }], isError: true };
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
        const resourceUris = [];
        if (resp.claims && resp.claims.length > 0) {
          resp.claims.forEach((c) => {
            if (c && c.claim_id) {
              const u = safeBuildUri("claim", c.claim_id);
              if (u) resourceUris.push(u);
            }
          });
        }
        return withEnvelope(text, resp, resourceUris, extra);
      } catch(err) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "list_verified_claims 실패: " + err.message }) }], isError: true };
      }
    })
  );

  // ========================================================================
  // Task 13.3: rag_validate_answer (신규, 가산) — 답변 문장별 근거 검증
  // Requirements: 3.3, 3.4, 3.5, 3.6, 4.9
  // ========================================================================
  mcp.tool(
    "rag_validate_answer",
    TOOL_DESCRIPTIONS.rag_validate_answer,
    {
      answer: z.string().describe("검증할 답변 텍스트")
    },
    withTool("rag_validate_answer", async (args, extra) => {
      // 빈/공백 answer는 Error_Schema 반환 (Req 3.6).
      if (typeof args.answer !== "string" || args.answer.trim().length === 0) {
        return errors.renderError(
          errors.makeError(
            errors.ERROR_CODES.UPSTREAM_ERROR,
            "answer가 비어있거나 공백뿐입니다. 검증할 답변 텍스트를 입력하세요."
          )
        );
      }

      const { coverage, backend } = await computeAnswerCoverage(args.answer);

      // 사람이 읽는 텍스트 요약 (Req 3.3, 3.5).
      let text = "🔎 답변 근거 검증 결과\n";
      text += "  문장 수: " + coverage.total + "\n";
      text += "  supported: " + coverage.supported_count + "\n";
      text += "  unsupported: " + coverage.unsupported_count + "\n";
      if (coverage.sentences.length > 0) {
        text += "\n--- 문장별 라벨 ---\n";
        coverage.sentences.forEach((s) => {
          text += "  [" + (s.index + 1) + "] " + (s.supported ? "supported" : "unsupported") +
            " (evidence: " + s.evidence_count + ") — " + s.text + "\n";
        });
      }
      if (coverage.unsupported.length > 0) {
        text += "\n--- 미지원 문장 목록 (text + position) ---\n";
        coverage.unsupported.forEach((u) => {
          text += "  position " + u.index + ": " + u.text + "\n";
        });
      }

      // 성공 경로: 텍스트 말미에 구조화 coverage 블록을 가산한다(content[].text 유지, Req 4.9).
      const structured = {
        sentences: coverage.sentences,
        unsupported: coverage.unsupported,
        supported_count: coverage.supported_count,
        unsupported_count: coverage.unsupported_count,
        total: coverage.total,
        index_version: envelope.resolveIndexVersion(backend && backend.index_version),
        request_id: extra && extra.request_id,
      };
      text += "\n\n--- structured ---\n" + JSON.stringify(structured);
      return { content: [{ type: "text", text }] };
    })
  );

  // ========================================================================
  // Phase 4: MCP Tool 확장 — generate_hdd_section, publish_markdown
  // Requirements: 10.1, 10.4
  // ========================================================================

  mcp.tool(
    "generate_hdd_section",
    TOOL_DESCRIPTIONS.generate_hdd_section,
    {
      topic: z.string().describe("topic 식별자 (예: ucie/phy/ltssm)"),
      section_title: z.string().describe("생성할 HDD 섹션 제목"),
      include_evidence: z.boolean().optional().default(true).describe("evidence 각주 포함 여부 (기본값 true)"),
      allow_unverified_inference: z.boolean().optional().default(true).describe("미검증 추론 허용 여부 (기본값 true, 기존 동작 보존). false면 지원 근거가 없는 세그먼트를 \"확실하지 않음\" 마커로 표기")
    },
    withTool("generate_hdd_section", async (args, extra) => {
      try {
        const body = {
          topic: args.topic,
          section_title: args.section_title,
          include_evidence: args.include_evidence,
          allow_unverified_inference: args.allow_unverified_inference
        };
        const resp = await ragApi("POST", "/generate-hdd", body);
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error }) }], isError: true };
        let text = "📝 HDD 섹션 생성 완료\n";
        text += "  Topic: " + resp.topic + "\n";
        text += "  섹션 제목: " + resp.section_title + "\n";
        text += "  사용된 Claim 수: " + (resp.claims_used || 0) + "\n";
        text += "  Evidence 포함: " + (resp.include_evidence ? "예" : "아니오") + "\n";
        text += "  면책 조항: " + (resp.disclaimer || "") + "\n";
        text += "\n--- 생성된 마크다운 ---\n\n";
        // verified-only 모드(Task 13.6, Req 3.7): allow_unverified_inference=false면
        // 지원 근거 0 세그먼트를 "확실하지 않음" 마커로 표기한다. 기본(true)은 기존 출력 보존.
        let markdown = resp.markdown || "(내용 없음)";
        if (args.allow_unverified_inference === false) {
          // 백엔드가 coverage 정보를 주면 그 세그먼트를 표기, 없으면 보수적 공지로 마커 보장.
          const unsupportedSegments = resp.unsupported_segments || resp.unsupported || [];
          markdown = evidence.markUnsupportedSegments(markdown, unsupportedSegments);
        }
        text += markdown;
        return { content: [{ type: "text", text }] };
      } catch(err) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "generate_hdd_section 실패: " + err.message }) }], isError: true };
      }
    })
  );

  mcp.tool(
    "publish_markdown",
    TOOL_DESCRIPTIONS.publish_markdown,
    {
      content: z.string().describe("출판할 마크다운 콘텐츠"),
      filename: z.string().describe("저장할 파일명 (예: ucie_phy_hdd.md)"),
      topic: z.string().optional().describe("관련 topic (지정 시 해당 topic의 claim 승인 상태를 확인)")
    },
    withTool("publish_markdown", async (args, extra) => {
      try {
        // ── Pre-save 가드 (Task 13.8, Req 3.8/3.9) ──────────────────────────
        // 백엔드 저장(ragApi POST /publish-markdown) 호출 *이전*에 콘텐츠를 검사하여
        // 거부 시 어떤 부분도 저장되지 않도록 한다(부분 저장 원천 차단).

        // (Req 3.9) 미해석 "latest" 참조 → 발행 거부. 순수·결정적 검사.
        if (evidence.containsUnresolvedLatest(args.content)) {
          return errors.renderError(
            errors.makeError(
              errors.ERROR_CODES.UPSTREAM_ERROR,
              "발행 거부: 미해석 'latest' 참조가 콘텐츠에 포함되어 있습니다. 구체 스냅샷/버전으로 치환 후 다시 시도하세요."
            )
          );
        }

        // (Req 3.8) 미지원 문장 1개 이상 → 발행 거부.
        // rag_validate_answer와 동일한 검증 경로(computeAnswerCoverage)를 공유한다.
        // 백엔드 검증 신호가 실제로 가용할 때에만 미지원 기준으로 거부하여(하위 호환),
        // 검증 엔드포인트 부재 시(OQ) 정상 발행을 막지 않는다.
        const { coverage, backendAvailable } = await computeAnswerCoverage(args.content);
        if (backendAvailable && coverage.unsupported_count > 0) {
          return errors.renderError(
            errors.makeError(
              errors.ERROR_CODES.UPSTREAM_ERROR,
              "발행 거부: 지원 근거가 없는 문장이 " + coverage.unsupported_count +
                "개 있습니다. 근거를 보강한 뒤 다시 시도하세요."
            )
          );
        }

        const body = {
          content: args.content,
          filename: args.filename
        };
        if (args.topic) body.topic = args.topic;
        const resp = await ragApi("POST", "/publish-markdown", body);
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error }) }], isError: true };
        let text = "📄 마크다운 출판 완료\n";
        text += "  S3 Key: " + resp.s3_key + "\n";
        text += "  Bucket: " + resp.bucket + "\n";
        text += "  파일명: " + resp.filename + "\n";
        text += "  Topic: " + (resp.topic || "general") + "\n";
        text += "  메타데이터: " + resp.metadata_key + "\n";
        text += "  Source: " + resp.source + "\n";
        text += "  Generation Basis: " + resp.generation_basis + "\n";
        return { content: [{ type: "text", text }] };
      } catch(err) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "publish_markdown 실패: " + err.message }) }], isError: true };
      }
    })
  );

  // ========================================================================
  // Phase 6: MCP Tool 확장 — Neptune Graph DB 도구
  // Requirements: 16.9, 16.10, 16.11
  // ========================================================================

  mcp.tool(
    "trace_signal_path",
    TOOL_DESCRIPTIONS.trace_signal_path,
    {
      module_name: z.string().describe("시작 모듈명 (예: BLK_UCIE)"),
      signal_name: z.string().describe("추적할 신호명 (예: tx_data)")
    },
    withTool("trace_signal_path", async (args, extra) => {
      try {
        const resp = await ragApi("POST", "/trace-signal-path", { module_name: args.module_name, signal_name: args.signal_name });
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error }) }], isError: true };
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
        const resourceUris = [];
        paths.forEach((p) => {
          const nodes = Array.isArray(p.nodes) ? p.nodes : [];
          nodes.forEach((n) => {
            const u = safeBuildUri("graph", "node/" + (n && n.name ? n.name : n));
            if (u) resourceUris.push(u);
          });
        });
        if (resourceUris.length === 0 && paths.length > 0) {
          const su = safeBuildUri("graph", "signal/" + args.module_name + "/" + args.signal_name);
          if (su) resourceUris.push(su);
        }
        return withEnvelope(text, resp, resourceUris, extra);
      } catch(err) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "trace_signal_path 실패: " + err.message }) }], isError: true };
      }
    })
  );

  mcp.tool(
    "find_instantiation_tree",
    TOOL_DESCRIPTIONS.find_instantiation_tree,
    {
      module_name: z.string().describe("조회할 모듈명 (예: BLK_UCIE)"),
      depth: z.number().optional().default(3).describe("탐색 깊이 (기본값 3)")
    },
    withTool("find_instantiation_tree", async (args, extra) => {
      try {
        const resp = await ragApi("POST", "/find-instantiation-tree", { module_name: args.module_name, depth: args.depth });
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error }) }], isError: true };
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
        const resourceUris = [];
        const rootUri = safeBuildUri("graph", "module/" + args.module_name);
        if (rootUri) resourceUris.push(rootUri);
        treeData.forEach((node) => {
          if (node && node.module_name) {
            const u = safeBuildUri("graph", "module/" + node.module_name);
            if (u) resourceUris.push(u);
          }
        });
        return withEnvelope(text, resp, resourceUris, extra);
      } catch(err) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "find_instantiation_tree 실패: " + err.message }) }], isError: true };
      }
    })
  );

  mcp.tool(
    "find_clock_crossings",
    TOOL_DESCRIPTIONS.find_clock_crossings,
    {
      module_name: z.string().describe("조회할 모듈명 (예: BLK_UCIE)")
    },
    withTool("find_clock_crossings", async (args, extra) => {
      try {
        const resp = await ragApi("POST", "/find-clock-crossings", { module_name: args.module_name });
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error }) }], isError: true };
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
        const resourceUris = [];
        const ccRoot = safeBuildUri("graph", "module/" + args.module_name);
        if (ccRoot) resourceUris.push(ccRoot);
        if (resp.crossings && resp.crossings.length > 0) {
          resp.crossings.forEach((c) => {
            if (c && c.signal_name) {
              const u = safeBuildUri("graph", "signal/" + args.module_name + "/" + c.signal_name);
              if (u) resourceUris.push(u);
            }
          });
        }
        return withEnvelope(text, resp, resourceUris, extra);
      } catch(err) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "find_clock_crossings 실패: " + err.message }) }], isError: true };
      }
    })
  );

  // ========================================================================
  // Phase 9: Graph Export 도구
  // Requirements: 32.1, 32.5
  // ========================================================================

  mcp.tool(
    "graph_export",
    TOOL_DESCRIPTIONS.graph_export,
    {
      scope: z.enum(["chip", "module", "signal"]).describe("조회 범위: chip(최상위 인스턴스), module(내부 상세), signal(신호 전파 경로)"),
      root_module: z.string().describe("시작 모듈명 (예: BLK_UCIE)"),
      depth: z.number().optional().default(3).describe("탐색 깊이 (기본값 3, scope=module 시 무시)"),
      signal_filter: z.string().optional().describe("신호 필터 (scope=signal 시 필수)")
    },
    withTool("graph_export", async (args, extra) => {
      try {
        const body = { scope: args.scope, root_module: args.root_module };
        if (args.depth !== undefined) body.depth = args.depth;
        if (args.signal_filter) body.signal_filter = args.signal_filter;
        const resp = await ragApi("POST", "/graph-export", body);
        if (resp.error) return { content: [{ type: "text", text: JSON.stringify({ error: resp.error }) }], isError: true };
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
        const resourceUris = [];
        const geRoot = safeBuildUri("graph", "module/" + args.root_module);
        if (geRoot) resourceUris.push(geRoot);
        if (resp.nodes && resp.nodes.length > 0) {
          resp.nodes.slice(0, 10).forEach((node) => {
            const u = safeBuildUri("graph", "node/" + (node && (node.id || node.label)));
            if (u) resourceUris.push(u);
          });
        }
        return withEnvelope(text, resp, resourceUris, extra);
      } catch(err) {
        return { content: [{ type: "text", text: JSON.stringify({ error: "graph_export 실패: " + err.message }) }], isError: true };
      }
    })
  );

  // ========================================================================
  // Task 16.7: regenerate_stale_hdd 비동기 job 전환 (Req 5.1, 5.2, 1.7)
  // ------------------------------------------------------------------------
  // 기존 동기 블로킹(ragApi await)을 jobDispatcher.createJob으로 전환한다.
  // 핸들러는 백그라운드 작업의 소요 시간과 무관하게 즉시(2초 이내) job_id와
  // job:// 상태 URI를 content[].text 안에 반환한다(Property 22). 실제 장시간
  // 작업은 runner = () => ragApi(...)가 백그라운드에서 수행하고, 사용자는
  // rag_task_status(job_id)로 완료를 polling한다.
  //
  // 도구 이름·스키마({}, 입력 없음)는 불변 — 하위 호환 보존(시그니처 보존 자명).
  //
  // NOTE(reindex): 이 브리지에는 reindex 도구가 등록되어 있지 않다. tasks.md
  // 16.7의 "reindex 전환"은 현재 대상 도구가 없으므로 구현하지 않는다. 향후
  // reindex 도구(예: rag_reindex_document/rag_reindex_corpus, 별도 spec 소관)가
  // 추가되면 동일한 jobDispatcher.createJob 패턴으로 비동기 job 핸들을 반환하도록
  // 구현하면 된다(아래 regenerate_stale_hdd와 동형).
  // ========================================================================
  mcp.tool(
    "regenerate_stale_hdd",
    TOOL_DESCRIPTIONS.regenerate_stale_hdd,
    {},
    withTool("regenerate_stale_hdd", async (args, extra) => {
      // 비블로킹 dispatch: runner는 백그라운드에서 장시간 작업을 수행한다.
      const runner = () => ragApi("POST", "/hdd/regenerate-stale", {});
      const { job_id, status_uri } = jobDispatcher.createJob(
        "regenerate_stale_hdd",
        {},
        runner
      );

      let text = "🔄 Stale HDD 재생성 작업을 시작했습니다 (비동기).\n";
      text += "  상태: queued\n";
      text += "  job_id: " + job_id + "\n";
      text += "  status_uri: " + status_uri + "\n";
      text += "\n  ℹ️ 장시간 작업입니다. 'rag_task_status' 도구에 위 job_id를 전달해 진행 상태를 확인하세요.";
      return { content: [{ type: "text", text }] };
    })
  );

  // ========================================================================
  // Task 15.1: rag_index_status (신규, 가산) — 인덱스 상태 조회 (입력 없음)
  // Requirements: 4.1, 4.2, 4.9
  // ------------------------------------------------------------------------
  // 인덱스별 { index_version, last_updated_at(ISO 8601 UTC), embedding_model }
  // 리스트를 반환한다. 백엔드가 아무것도/빈 결과를 주면 빈 리스트를 반환하며
  // Error_Schema를 반환하지 않는다(Req 4.2). invalid_uri/not_found 외 실패는
  // upstream_error로 분류한다(Req 4.8). 응답은 content[].text 가산 형식(Req 4.9).
  //
  // OQ: 백엔드 /index-status 엔드포인트 존재 여부는 미확정(design Open Question 1
  // 연계). 엔드포인트가 없거나 오류면 graceful하게 빈 리스트로 fallback한다(짧은
  // 안내 포함) — 즉, 인덱스 부재와 동일하게 취급하여 도구가 실패하지 않는다.
  // ========================================================================
  mcp.tool(
    "rag_index_status",
    TOOL_DESCRIPTIONS.rag_index_status,
    {},
    withTool("rag_index_status", async (args, extra) => {
      const resp = await ragApi("POST", "/index-status", {});

      // 백엔드 오류: 엔드포인트 부재(not found류)는 빈 리스트로 graceful fallback,
      // 그 외 명시적 실패는 upstream_error.
      let endpointMissing = false;
      if (resp && resp.error) {
        const msg = String(resp.error);
        const looksNotFound = /not found|404|no such|unknown (path|route)/i.test(msg);
        if (!looksNotFound) {
          return errors.renderError(
            errors.makeError(errors.ERROR_CODES.UPSTREAM_ERROR, "rag_index_status 실패: " + msg)
          );
        }
        // not-found류 → 엔드포인트 미구현으로 간주하고 빈 리스트로 진행.
        endpointMissing = true;
      }

      // 응답에서 인덱스 배열을 유연하게 추출(indexes/indices/results).
      const rawList =
        (resp && (resp.indexes || resp.indices || resp.results)) || [];
      const list = Array.isArray(rawList)
        ? rawList.map((idx) => ({
            index_version:
              (idx && (idx.index_version || idx.version)) || "unknown",
            last_updated_at:
              (idx &&
                (idx.last_updated_at ||
                  idx.last_success_at ||
                  idx.updated_at)) ||
              null,
            embedding_model:
              (idx && (idx.embedding_model || idx.model)) || "unknown",
          }))
        : [];

      let text;
      if (list.length === 0) {
        text = "📈 인덱스 상태: 보고된 인덱스가 없습니다. (빈 리스트)";
        if (endpointMissing) {
          text += "\n  ℹ️ 백엔드 인덱스 상태 엔드포인트가 아직 제공되지 않을 수 있습니다.";
        }
      } else {
        text = "📈 인덱스 상태 (" + list.length + "개):\n";
        list.forEach((idx, i) => {
          text += "\n[" + (i + 1) + "] index_version: " + idx.index_version + "\n";
          text += "    last_updated_at: " + (idx.last_updated_at || "unknown") + "\n";
          text += "    embedding_model: " + idx.embedding_model + "\n";
        });
      }

      // 구조화 블록(content[].text 말미 가산, Req 4.9).
      const structured = {
        indexes: list,
        count: list.length,
        request_id: extra && extra.request_id,
      };
      text += "\n\n--- structured ---\n" + JSON.stringify(structured);
      return { content: [{ type: "text", text }] };
    })
  );

  // ========================================================================
  // Task 15.3: rag_read_resource (신규, 가산) — Resource_URI로 원문/스팬 재조회
  // Requirements: 4.3, 4.4, 4.5, 4.8, 4.9
  // ------------------------------------------------------------------------
  // - malformed URI → invalid_uri, 부분 콘텐츠 없음(Req 4.4).
  // - well-formed지만 자원 부재 → not_found(Req 4.5).
  // - 존재 → 원문/스팬을 content[].text로 반환(Req 4.3).
  // - 그 외 실패 → upstream_error(Req 4.8). 응답은 content[].text 가산 형식(Req 4.9).
  // ========================================================================
  mcp.tool(
    "rag_read_resource",
    TOOL_DESCRIPTIONS.rag_read_resource,
    {
      resource_uri: z
        .string()
        .describe(
          "재조회할 Resource_URI. 6개 스킴(rag/rtl/graph/claim/job/index) 중 하나의 well-formed URI (예: rtl://module/tt_noc_router)"
        ),
    },
    withTool("rag_read_resource", async (args, extra) => {
      // 1) well-formed 검증. malformed면 invalid_uri, 부분 콘텐츠 없음(Req 4.4).
      if (!uri.isWellFormed(args.resource_uri)) {
        return errors.renderError(
          errors.makeError(
            errors.ERROR_CODES.INVALID_URI,
            "malformed Resource_URI입니다. <scheme>://<id> 형태이며 스킴은 rag/rtl/graph/claim/job/index 중 하나여야 합니다: " +
              String(args.resource_uri)
          )
        );
      }

      // 2) parse 후 백엔드에서 원문/스팬 조회.
      const parsed = uri.parseUri(args.resource_uri);
      const resp = await ragApi("POST", "/read-resource", {
        resource_uri: args.resource_uri,
      });

      // 3) 백엔드 오류 분류: not-found류 → not_found, 그 외 → upstream_error(Req 4.5/4.8).
      if (resp && resp.error) {
        const msg = String(resp.error);
        const looksNotFound = /not found|404|no such|does not exist|absent/i.test(msg);
        return errors.renderError(
          errors.makeError(
            looksNotFound ? errors.ERROR_CODES.NOT_FOUND : errors.ERROR_CODES.UPSTREAM_ERROR,
            "rag_read_resource: " + msg
          )
        );
      }

      // 4) 부재(빈/absent) → not_found(Req 4.5).
      const content =
        resp && (resp.content || resp.text || resp.span || resp.body);
      const found =
        resp &&
        (resp.found === true ||
          (resp.found === undefined &&
            content !== undefined &&
            content !== null &&
            String(content).length > 0));
      if (!found) {
        return errors.renderError(
          errors.makeError(
            errors.ERROR_CODES.NOT_FOUND,
            "Resource_URI가 가리키는 자원을 찾을 수 없습니다: " + args.resource_uri
          )
        );
      }

      // 5) 존재 → 원문/스팬 반환(Req 4.3).
      let text = "📄 Resource 원문/스팬\n";
      text += "  resource_uri: " + args.resource_uri + "\n";
      text += "  scheme: " + parsed.scheme + "\n";
      if (resp.source_path) text += "  path: " + resp.source_path + "\n";
      if (resp.line_start) {
        text += "  lines: " + resp.line_start + "-" + (resp.line_end || "") + "\n";
      }
      text += "\n--- content ---\n";
      text += typeof content === "string" ? content : JSON.stringify(content);

      const structured = {
        resource_uri: args.resource_uri,
        scheme: parsed.scheme,
        request_id: extra && extra.request_id,
      };
      text += "\n\n--- structured ---\n" + JSON.stringify(structured);
      return { content: [{ type: "text", text }] };
    })
  );

  // ========================================================================
  // Task 16.5: rag_task_status (신규, 가산) — 비동기 job 상태 polling
  // Requirements: 4.6, 4.7, 4.8, 4.9, 5.6, 5.7, 5.8
  // ------------------------------------------------------------------------
  // 공유 defaultStore에서 job 레코드를 조회한다.
  // - 미지 job_id → not_found(Req 4.7).
  // - 알려진 job → status ∈ {queued,running,done,failed} 중 하나(Req 4.6, 5.4).
  //   queued/running → 최종 결과 없이 현재 상태만(Req 5.6).
  //   done → 결과 포함(Req 5.7). failed → 에러 표시(Req 5.8).
  // 응답은 content[].text 가산 형식(Req 4.9).
  // ========================================================================
  mcp.tool(
    "rag_task_status",
    TOOL_DESCRIPTIONS.rag_task_status,
    {
      job_id: z
        .string()
        .describe(
          "조회할 job 식별자. regenerate_stale_hdd 등 장시간 작업이 반환한 job:// URI의 식별자"
        ),
    },
    withTool("rag_task_status", async (args, extra) => {
      const rec = defaultStore.get(args.job_id);

      // 미지 job → not_found(Req 4.7).
      if (!rec) {
        return errors.renderError(
          errors.makeError(
            errors.ERROR_CODES.NOT_FOUND,
            "알려지지 않은 job_id입니다: " + String(args.job_id)
          )
        );
      }

      let text = "🧭 Job 상태\n";
      text += "  job_id: " + rec.job_id + "\n";
      text += "  type: " + (rec.type || "unknown") + "\n";
      text += "  status: " + rec.status + "\n";
      if (rec.created_at) text += "  created_at: " + rec.created_at + "\n";
      if (rec.updated_at) text += "  updated_at: " + rec.updated_at + "\n";

      // 구조화 블록 — 상태에 따라 result/error를 선택적으로 포함.
      const structured = {
        job_id: rec.job_id,
        type: rec.type,
        status: rec.status,
        created_at: rec.created_at,
        updated_at: rec.updated_at,
        request_id: extra && extra.request_id,
      };

      if (rec.status === JOB_STATUS.DONE) {
        // 성공 완료 → 결과 포함(Req 5.7).
        text += "\n  ✅ 완료 — 결과가 포함되었습니다.";
        structured.result = rec.result === undefined ? null : rec.result;
      } else if (rec.status === JOB_STATUS.FAILED) {
        // 실패 → 에러 표시(Req 5.8).
        text += "\n  ❌ 실패: " + (rec.error || "알 수 없는 오류");
        structured.error = rec.error || "알 수 없는 오류";
      } else {
        // queued/running → 최종 결과 없이 현재 상태만(Req 5.6).
        text += "\n  ⏳ 아직 진행 중입니다. 잠시 후 다시 polling하세요. (최종 결과 없음)";
      }

      text += "\n\n--- structured ---\n" + JSON.stringify(structured);
      return { content: [{ type: "text", text }] };
    })
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
