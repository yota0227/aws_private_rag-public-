// Property tests for lib/envelope.js — 출력 envelope (텍스트 말미 구조화 블록)
//
// Spec: .kiro/specs/mcp-tool-optimization/ (Task 5.2~5.7)
// Runner: node:test ; Property library: fast-check (numRuns >= 100).

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fc = require("fast-check");

const {
  ENVELOPE_SEPARATOR,
  LATEST,
  appendEnvelope,
  resolveSnapshot,
  filterResourceUris,
} = require("../lib/envelope");

const { isWellFormed } = require("../lib/uri");
const { renderError } = require("../lib/errors");

const NUM_RUNS = 100;

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

const SCHEMES = ["rag", "rtl", "graph", "claim", "job", "index"];

const ID_CHARS =
  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/._-:#=";

const validId = fc
  .array(fc.constantFrom(...ID_CHARS.split("")), { minLength: 1, maxLength: 40 })
  .map((chars) => chars.join(""));

const scheme = fc.constantFrom(...SCHEMES);

const wellFormedUri = fc.tuple(scheme, validId).map(([s, id]) => `${s}://${id}`);

// 명백히 non-addressable / malformed 한 후보값들.
const badUriValue = fc.oneof(
  fc.constant(""),
  fc.constant("   "),
  fc.constant(null),
  fc.constant(undefined),
  fc.constant("placeholder"),
  fc.constant("no-scheme-here"),
  fc.constant("://emptyscheme"),
  fc.constant("unknown://id"), // 미지원 스킴
  validId.map((id) => `bogus://${id}`) // 미지원 스킴
);

// 비어있지 않은 구체(=non-"latest") 스냅샷.
const concreteSnapshot = fc
  .string({ minLength: 1, maxLength: 20 })
  .filter((s) => s.trim().length > 0 && s !== LATEST);

// 비어있지 않은 index_version.
const nonEmptyIndexVersion = fc
  .string({ minLength: 1, maxLength: 20 })
  .filter((s) => s.trim().length > 0);

// "비어있음"으로 취급되는 index_version 후보 (fallback "unknown" 기대).
const emptyIndexVersion = fc.oneof(
  fc.constant(undefined),
  fc.constant(null),
  fc.constant(""),
  fc.constant("   "),
  fc.constant(42), // 비-문자열
  fc.constant({})
);

// envelope 블록 JSON을 추출/파싱한다. (구조화 블록은 항상 말미이므로 lastIndexOf 사용)
function parseEnvelope(output) {
  const idx = output.lastIndexOf(ENVELOPE_SEPARATOR);
  assert.ok(idx >= 0, "envelope separator must be present");
  const jsonPart = output.slice(idx + ENVELOPE_SEPARATOR.length);
  return JSON.parse(jsonPart);
}

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 9: 모든 retrieval 결과에 비어있지 않은 index_version
// Validates: Requirements 2.3
// ---------------------------------------------------------------------------
test("Property 9: index_version은 항상 비어있지 않다 (백엔드 미제공 시 'unknown' fallback)", () => {
  fc.assert(
    fc.property(
      fc.string(),
      fc.oneof(nonEmptyIndexVersion, emptyIndexVersion),
      concreteSnapshot,
      (text, indexVersion, snapshot) => {
        const out = appendEnvelope(text, {
          index_version: indexVersion,
          resolved_snapshot: snapshot,
          request_id: "req-1",
        });
        const env = parseEnvelope(out);
        assert.equal(typeof env.index_version, "string");
        assert.ok(env.index_version.trim().length > 0, "index_version non-empty");
        // 비어있는 입력이면 'unknown'으로 채워진다.
        if (typeof indexVersion !== "string" || indexVersion.trim().length === 0) {
          assert.equal(env.index_version, "unknown");
        } else {
          assert.equal(env.index_version, indexVersion);
        }
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 10: resolved_snapshot 해석 — 절대 "latest" 아님
// Validates: Requirements 2.4, 2.5, 2.6
// ---------------------------------------------------------------------------
test("Property 10: latest/미지정 요청 → 백엔드 구체값으로 해석되고 'latest'가 아니다", () => {
  fc.assert(
    fc.property(
      fc.oneof(fc.constant(LATEST), fc.constant(undefined), fc.constant(null), fc.constant("")),
      concreteSnapshot,
      (requested, backendResolved) => {
        const resolved = resolveSnapshot(requested, backendResolved);
        assert.equal(resolved, backendResolved);
        assert.notEqual(resolved, LATEST);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test("Property 10: 구체 스냅샷 요청 → 동일 값 echo (절대 'latest' 아님)", () => {
  fc.assert(
    fc.property(concreteSnapshot, concreteSnapshot, (requested, backendResolved) => {
      const resolved = resolveSnapshot(requested, backendResolved);
      // 구체 요청은 backend 값과 무관하게 그대로 echo된다.
      assert.equal(resolved, requested);
      assert.notEqual(resolved, LATEST);
    }),
    { numRuns: NUM_RUNS }
  );
});

test("Property 10: 구체값을 해석할 수 없으면(backend도 latest/빈값) upstream_error를 throw", () => {
  fc.assert(
    fc.property(
      fc.oneof(fc.constant(LATEST), fc.constant(undefined), fc.constant(null), fc.constant("")),
      fc.oneof(fc.constant(LATEST), fc.constant(undefined), fc.constant(null), fc.constant("  ")),
      (requested, backendResolved) => {
        assert.throws(
          () => resolveSnapshot(requested, backendResolved),
          (err) => err && err.code === "upstream_error"
        );
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test("Property 10: 최종 envelope의 resolved_snapshot은 결코 'latest'가 아니다", () => {
  fc.assert(
    fc.property(
      fc.string(),
      fc.oneof(fc.constant(LATEST), fc.constant(undefined), concreteSnapshot),
      concreteSnapshot,
      (text, requested, backendResolved) => {
        const resolved = resolveSnapshot(requested, backendResolved);
        const out = appendEnvelope(text, {
          index_version: "idx_1",
          resolved_snapshot: resolved,
          request_id: "req-1",
        });
        const env = parseEnvelope(out);
        assert.notEqual(env.resolved_snapshot, LATEST);
        assert.ok(String(env.resolved_snapshot).length > 0);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 8: non-addressable 결과는 URI 필드를 생략
// Validates: Requirements 2.2
// ---------------------------------------------------------------------------
test("Property 8: well-formed URI가 하나도 없으면 resource_uris 필드를 아예 생략", () => {
  fc.assert(
    fc.property(
      fc.string(),
      fc.oneof(
        fc.constant(undefined),
        fc.constant([]),
        fc.array(badUriValue, { minLength: 0, maxLength: 6 })
      ),
      (text, candidates) => {
        const out = appendEnvelope(text, {
          index_version: "idx_1",
          resolved_snapshot: "snap_1",
          resource_uris: candidates,
          request_id: "req-1",
        });
        const env = parseEnvelope(out);
        // 빈/null/placeholder/malformed만 있으면 필드 자체가 없어야 한다.
        assert.ok(!("resource_uris" in env), "resource_uris field must be omitted");
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 7: 반환되는 URI는 항상 well-formed이고 자원에 대해 안정·유일
// Validates: Requirements 8.3, 2.1
// ---------------------------------------------------------------------------
test("Property 7: 부착된 모든 resource_uris는 well-formed이고 유일하다", () => {
  fc.assert(
    fc.property(
      fc.string(),
      fc.array(fc.oneof(wellFormedUri, badUriValue), { minLength: 0, maxLength: 12 }),
      (text, candidates) => {
        const out = appendEnvelope(text, {
          index_version: "idx_1",
          resolved_snapshot: "snap_1",
          resource_uris: candidates,
          request_id: "req-1",
        });
        const env = parseEnvelope(out);
        const expected = filterResourceUris(candidates);
        if (expected.length === 0) {
          assert.ok(!("resource_uris" in env));
        } else {
          assert.deepEqual(env.resource_uris, expected);
          // 모두 well-formed
          for (const u of env.resource_uris) {
            assert.equal(isWellFormed(u), true);
          }
          // 유일성
          assert.equal(new Set(env.resource_uris).size, env.resource_uris.length);
        }
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test("Property 7: 동일 입력에 대해 결정적으로 동일한 URI 집합을 산출한다 (stable)", () => {
  fc.assert(
    fc.property(
      fc.string(),
      fc.array(fc.oneof(wellFormedUri, badUriValue), { minLength: 0, maxLength: 12 }),
      (text, candidates) => {
        const meta = {
          index_version: "idx_1",
          resolved_snapshot: "snap_1",
          resource_uris: candidates,
          request_id: "req-1",
        };
        const a = appendEnvelope(text, meta);
        const b = appendEnvelope(text, meta);
        assert.equal(a, b);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 13: 응답 형식 불변성 + 가산성
// Validates: Requirements 2.10, 2.11, 4.9, 8.8
// ---------------------------------------------------------------------------
test("Property 13: 원본 텍스트는 prefix로 보존되고 구조화 블록은 말미에만 추가된다", () => {
  fc.assert(
    fc.property(
      fc.string(),
      nonEmptyIndexVersion,
      concreteSnapshot,
      fc.array(fc.oneof(wellFormedUri, badUriValue), { minLength: 0, maxLength: 8 }),
      (text, indexVersion, snapshot, candidates) => {
        const out = appendEnvelope(text, {
          index_version: indexVersion,
          resolved_snapshot: snapshot,
          resource_uris: candidates,
          request_id: "req-1",
        });
        // 1) 원본 텍스트 + 구분자가 정확히 prefix로 보존된다(중간 삽입 없음 → additive only).
        assert.ok(
          out.startsWith(text + ENVELOPE_SEPARATOR),
          "original text + separator preserved as prefix"
        );
        assert.equal(out.slice(0, text.length), text);
        // 2) 말미는 유효한 JSON 구조화 블록이며 기존 텍스트 뒤에만 존재한다.
        const tail = out.slice(text.length + ENVELOPE_SEPARATOR.length);
        const env = JSON.parse(tail);
        assert.equal(typeof env.index_version, "string");
        assert.equal(typeof env.resolved_snapshot, "string");
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 12: 에러 응답은 Error_Schema만 포함
// Validates: Requirements 2.9
// (errors.property.test.js에서 주로 다루며, 여기서는 appendEnvelope가
//  에러 경로에 적용되지 않음을 확인하는 보조 단언을 둔다.)
// ---------------------------------------------------------------------------
test("Property 12(보조): 에러 출력(renderError)은 envelope 부가필드/구분자를 담지 않는다", () => {
  const rendered = renderError({ error_code: "upstream_error", message: "boom" });
  const text = rendered.content[0].text;
  // 에러 응답에는 envelope 구분자가 없어야 한다(appendEnvelope 미적용).
  assert.ok(!text.includes(ENVELOPE_SEPARATOR), "error path must not append envelope block");
  const parsed = JSON.parse(text);
  assert.deepEqual(Object.keys(parsed).sort(), ["error_code", "message"]);
  for (const f of ["resource_uris", "index_version", "resolved_snapshot"]) {
    assert.ok(!(f in parsed), `error output must not carry ${f}`);
  }
});
