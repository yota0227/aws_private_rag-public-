// Property tests for lib/evidence.js — get_evidence 정규화
//
// Spec: .kiro/specs/mcp-tool-optimization/ (Task 13.2 + Property 14)
// Runner: node:test ; Property library: fast-check (numRuns >= 100).

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fc = require("fast-check");

const {
  normalizeEvidence,
  normalizeEvidenceList,
} = require("../lib/evidence");
const { isWellFormed } = require("../lib/uri");

const NUM_RUNS = 100;

// 백엔드 evidence 항목 generator — 모든 필드는 선택적(누락/이상치 포함).
const backendEvidence = fc.record(
  {
    source_document_id: fc.option(fc.string(), { nil: undefined }),
    source_type: fc.option(
      fc.oneof(
        fc.constantFrom("pdf", "rtl", "claim", "verilog", "vhdl", ""),
        fc.string()
      ),
      { nil: undefined }
    ),
    source_chunk: fc.option(fc.string(), { nil: undefined }),
    page_number: fc.option(fc.integer({ min: 0, max: 5000 }), { nil: undefined }),
    source_path: fc.option(fc.string(), { nil: undefined }),
    line_start: fc.option(
      fc.oneof(fc.integer({ min: 0, max: 100000 }), fc.string()),
      { nil: undefined }
    ),
    line_end: fc.option(
      fc.oneof(fc.integer({ min: 0, max: 100000 }), fc.string()),
      { nil: undefined }
    ),
    support_level: fc.option(
      fc.oneof(fc.constantFrom("strong", "weak", ""), fc.string()),
      { nil: undefined }
    ),
    confidence: fc.option(
      fc.oneof(
        fc.double({ min: -10, max: 10, noNaN: true }),
        fc.double({ noNaN: false }), // NaN/Infinity 포함 이상치
        fc.string()
      ),
      { nil: undefined }
    ),
  },
  { requiredKeys: [] }
);

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 14: Evidence 정규화
// Validates: Requirements 3.1, 3.2
// ---------------------------------------------------------------------------
test("Property 14: 정규화된 각 항목은 비어있지 않은 source_type/support_level + [0,1] confidence를 가진다", () => {
  fc.assert(
    fc.property(fc.array(backendEvidence, { maxLength: 12 }), (rawList) => {
      const normalized = normalizeEvidenceList(rawList);

      // 입력 개수 보존 (정규화는 항목을 잃거나 추가하지 않는다).
      assert.equal(normalized.length, rawList.length);

      for (const item of normalized) {
        // source_type: 비어있지 않은 문자열.
        assert.equal(typeof item.source_type, "string");
        assert.ok(item.source_type.length > 0, "source_type must be non-empty");

        // support_level: 비어있지 않은 문자열.
        assert.equal(typeof item.support_level, "string");
        assert.ok(
          item.support_level.length > 0,
          "support_level must be non-empty"
        );

        // confidence: [0,1] 포함 범위의 유한 숫자.
        assert.equal(typeof item.confidence, "number");
        assert.ok(Number.isFinite(item.confidence));
        assert.ok(item.confidence >= 0 && item.confidence <= 1);

        // source_uri: 존재한다면 반드시 well-formed.
        if (Object.prototype.hasOwnProperty.call(item, "source_uri")) {
          assert.equal(typeof item.source_uri, "string");
          assert.ok(
            isWellFormed(item.source_uri),
            `source_uri must be well-formed: ${item.source_uri}`
          );
        }

        // span: 존재한다면 line_start/line_end 중 최소 하나가 정수.
        if (Object.prototype.hasOwnProperty.call(item, "span")) {
          const { line_start, line_end } = item.span;
          const hasStart = Number.isInteger(line_start);
          const hasEnd = Number.isInteger(line_end);
          assert.ok(
            hasStart || hasEnd,
            "span must carry at least one integer line bound"
          );
        }
      }
    }),
    { numRuns: NUM_RUNS }
  );
});

test("Property 14: 빈/없는 evidence 리스트는 에러 없이 빈 리스트를 반환한다 (Req 3.2)", () => {
  // 명시적 빈 배열.
  assert.deepEqual(normalizeEvidenceList([]), []);
  // 부재(undefined/null) 및 비배열 입력도 [] (Error 아님).
  assert.deepEqual(normalizeEvidenceList(undefined), []);
  assert.deepEqual(normalizeEvidenceList(null), []);
  assert.deepEqual(normalizeEvidenceList({}), []);

  fc.assert(
    fc.property(
      fc.oneof(
        fc.constant(undefined),
        fc.constant(null),
        fc.integer(),
        fc.string(),
        fc.object()
      ),
      (notAList) => {
        const result = normalizeEvidenceList(notAList);
        assert.ok(Array.isArray(result));
        assert.equal(result.length, 0);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test("Property 14: well-formed URI를 만들 수 없으면 source_uri를 생략한다 (나쁜 URI 미방출)", () => {
  fc.assert(
    fc.property(
      // 공백을 포함하거나 비어있는 식별자 베이스 — well-formed URI 불가.
      fc.string().filter((s) => /\s/.test(s) || s.trim().length === 0),
      (pathWithSpace) => {
        const norm = normalizeEvidence({
          source_path: pathWithSpace,
          source_type: "pdf",
        });
        // source_uri가 있다면 반드시 well-formed (공백 입력이면 보통 생략됨).
        if (Object.prototype.hasOwnProperty.call(norm, "source_uri")) {
          assert.ok(isWellFormed(norm.source_uri));
        }
      }
    ),
    { numRuns: NUM_RUNS }
  );
});
