// Property tests for lib/errors.js (Task 4.2, 4.3)
//
// Runner: node:test, Property library: fast-check ({ numRuns: 100 } 이상)
// Spec: .kiro/specs/mcp-tool-optimization/

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fc = require("fast-check");

const { ERROR_CODES, makeError, classify, renderError } = require("../lib/errors");
const { InvalidUriError } = require("../lib/uri");

const ALL_CODES = [
  ERROR_CODES.INVALID_URI,
  ERROR_CODES.NOT_FOUND,
  ERROR_CODES.UPSTREAM_ERROR,
];

// 임의의 에러 유사 객체 생성기 — invalid_uri/not_found 신호와 그 외를 골고루 포함.
function arbitraryError() {
  return fc.oneof(
    // InvalidUriError 인스턴스 (uri.js 위반 경로)
    fc.string().map((m) => new InvalidUriError(m)),
    // err.code === "invalid_uri" 신호를 가진 일반 Error
    fc.string().map((m) => {
      const e = new Error(m);
      e.code = "invalid_uri";
      return e;
    }),
    // err.code === "not_found" 신호
    fc.string().map((m) => {
      const e = new Error(m);
      e.code = "not_found";
      return e;
    }),
    // 임의 코드(닫힌 집합 밖) 또는 코드 없는 일반 Error -> upstream_error 기대
    fc
      .record({
        msg: fc.string(),
        code: fc.option(fc.string(), { nil: undefined }),
      })
      .map(({ msg, code }) => {
        const e = new Error(msg);
        if (code !== undefined) e.code = code;
        return e;
      }),
    // 비-Error 값들 (문자열/숫자/null 등) — robust 분류
    fc.constantFrom(null, undefined, 42, "boom", {})
  );
}

// Feature: mcp-tool-optimization, Property 11: 에러 분류 단일성
// Validates: Requirements 2.7, 2.8, 4.8
test("Property 11: classify는 닫힌 3개 코드 중 정확히 하나를 반환", () => {
  fc.assert(
    fc.property(arbitraryError(), (err) => {
      const code = classify(err);
      assert.ok(ALL_CODES.includes(code), `code must be one of the closed set: ${code}`);
    }),
    { numRuns: 200 }
  );
});

// Feature: mcp-tool-optimization, Property 11: 에러 분류 단일성
// Validates: Requirements 2.7, 2.8, 4.8
test("Property 11: invalid_uri/not_found 신호가 아닌 에러는 upstream_error로 분류", () => {
  fc.assert(
    fc.property(
      fc.record({
        msg: fc.string(),
        // 닫힌 신호 코드(invalid_uri/not_found)를 제외한 임의 코드
        code: fc.option(
          fc.string().filter((s) => s !== "invalid_uri" && s !== "not_found"),
          { nil: undefined }
        ),
      }),
      ({ msg, code }) => {
        const e = new Error(msg);
        if (code !== undefined) e.code = code;
        assert.equal(classify(e), ERROR_CODES.UPSTREAM_ERROR);
      }
    ),
    { numRuns: 200 }
  );
});

// Feature: mcp-tool-optimization, Property 11: 에러 분류 단일성
// Validates: Requirements 2.7, 2.8, 4.8
test("Property 11: makeError는 항상 1개 유효 코드 + 비어있지 않은 메시지", () => {
  fc.assert(
    fc.property(
      // 임의 code(유효/무효 모두) + 임의 message(빈 문자열/공백 포함)
      fc.oneof(fc.constantFrom(...ALL_CODES), fc.string(), fc.constant(undefined)),
      fc.oneof(fc.string(), fc.constant(undefined), fc.constant("   ")),
      (code, message) => {
        const out = makeError(code, message);
        assert.ok(ALL_CODES.includes(out.error_code), "error_code in closed set");
        assert.equal(typeof out.message, "string");
        assert.ok(out.message.trim().length > 0, "message non-empty");
        // 유효 코드를 넘기면 그대로 보존
        if (ALL_CODES.includes(code)) {
          assert.equal(out.error_code, code);
        }
      }
    ),
    { numRuns: 200 }
  );
});

// Feature: mcp-tool-optimization, Property 12: 에러 응답은 Error_Schema만 포함
// Validates: Requirements 2.9
test("Property 12: renderError 출력은 Error_Schema만 담고 부분필드를 부착하지 않음", () => {
  const FORBIDDEN = ["resource_uri", "resource_uris", "index_version", "resolved_snapshot"];
  fc.assert(
    fc.property(arbitraryError(), (err) => {
      const code = classify(err);
      const message = (err && err.message) || "x";
      const rendered = renderError(makeError(code, message));

      // 기존 server.js 에러 응답 형식 보존
      assert.equal(rendered.isError, true);
      assert.ok(Array.isArray(rendered.content));
      assert.equal(rendered.content.length, 1);
      assert.equal(rendered.content[0].type, "text");
      assert.equal(typeof rendered.content[0].text, "string");

      // 텍스트는 Error_Schema(JSON)만 — 부분 envelope 필드 부재.
      // (message 본문에는 임의 문자열이 들어갈 수 있으므로 raw substring이 아니라
      //  파싱된 스키마의 키 집합으로 정확히 검증한다.)
      const parsed = JSON.parse(rendered.content[0].text);
      assert.deepEqual(Object.keys(parsed).sort(), ["error_code", "message"]);
      assert.ok(ALL_CODES.includes(parsed.error_code));
      assert.ok(parsed.message.length > 0);
      for (const f of FORBIDDEN) {
        assert.ok(!(f in parsed), `Error_Schema must not contain ${f}`);
      }
    }),
    { numRuns: 200 }
  );
});
