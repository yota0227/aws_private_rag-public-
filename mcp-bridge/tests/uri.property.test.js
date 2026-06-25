// Property tests for lib/uri.js — Resource_URI parser / builder / validator
//
// Spec: .kiro/specs/mcp-tool-optimization/ (Task 3.2, 3.3 + Property 6)
// Runner: node:test ; Property library: fast-check (numRuns >= 100).

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fc = require("fast-check");

const {
  SCHEMES,
  InvalidUriError,
  parseUri,
  buildUri,
  isWellFormed,
} = require("../lib/uri");

const NUM_RUNS = 100;

// 공백이 없는 식별자 문자 집합 (letters, digits, 흔한 URI/프래그먼트 기호).
const ID_CHARS =
  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/._-:#=";

// 비어있지 않고 공백 없는 유효 식별자 generator.
const validId = fc
  .array(fc.constantFrom(...ID_CHARS.split("")), { minLength: 1, maxLength: 40 })
  .map((chars) => chars.join(""));

// 선택적 프래그먼트 generator (없음 | #section=... | #L<a>-L<b>).
const fragment = fc.oneof(
  fc.constant(""),
  validId.map((s) => `#section=${s}`),
  fc
    .tuple(fc.integer({ min: 1, max: 9999 }), fc.integer({ min: 1, max: 9999 }))
    .map(([a, b]) => `#L${a}-L${b}`)
);

const scheme = fc.constantFrom(...SCHEMES);

// 프래그먼트를 포함할 수 있는 well-formed id.
const idWithFragment = fc
  .tuple(validId, fragment)
  .map(([base, frag]) => base + frag);

// well-formed Resource_URI generator.
const wellFormedUri = fc
  .tuple(scheme, idWithFragment)
  .map(([s, id]) => `${s}://${id}`);

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 4: Resource_URI 라운드트립
// Validates: Requirements 8.4, 5.5
// ---------------------------------------------------------------------------
test("Property 4: well-formed URI는 parse 후 build하면 동일하다 (round-trip)", () => {
  fc.assert(
    fc.property(scheme, idWithFragment, (s, id) => {
      const u = `${s}://${id}`;
      const parsed = parseUri(u);
      assert.equal(parsed.scheme, s);
      assert.equal(parsed.id, id);
      const rebuilt = buildUri(parsed.scheme, parsed.id);
      assert.equal(rebuilt, u);
    }),
    { numRuns: NUM_RUNS }
  );
});

test("Property 4: job://<job_id>는 round-trip으로 job_id가 복원된다", () => {
  fc.assert(
    fc.property(validId, (jobId) => {
      const statusUri = buildUri("job", jobId);
      assert.equal(statusUri, `job://${jobId}`);
      const parsed = parseUri(statusUri);
      assert.equal(parsed.scheme, "job");
      // rag_task_status가 해석 가능한 동일 job_id가 복원된다.
      assert.equal(parsed.id, jobId);
    }),
    { numRuns: NUM_RUNS }
  );
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 5: well-formed 판정 규칙
// Validates: Requirements 8.1, 8.2
// ---------------------------------------------------------------------------
test("Property 5: isWellFormed는 유효 스킴 + 비어있지 않은 공백없는 id일 때만 true", () => {
  // 임의 문자열에 대해 isWellFormed의 결과가 정의(scheme∈SCHEMES ∧ 유효 id)와 동치여야 한다.
  fc.assert(
    fc.property(fc.string(), (raw) => {
      const sepIndex = raw.indexOf("://");
      let expected = false;
      if (sepIndex >= 0) {
        const s = raw.slice(0, sepIndex);
        const id = raw.slice(sepIndex + 3);
        expected = SCHEMES.includes(s) && id.length > 0 && !/\s/.test(id);
      }
      assert.equal(isWellFormed(raw), expected);
    }),
    { numRuns: NUM_RUNS }
  );
});

test("Property 5: 구성된 well-formed URI는 항상 isWellFormed true", () => {
  fc.assert(
    fc.property(wellFormedUri, (u) => {
      assert.equal(isWellFormed(u), true);
    }),
    { numRuns: NUM_RUNS }
  );
});

test("Property 5: 유효 스킴이라도 id에 공백이 있으면 isWellFormed false", () => {
  fc.assert(
    fc.property(
      scheme,
      validId,
      fc.constantFrom(" ", "\t", "\n"),
      validId,
      (s, a, ws, b) => {
        const u = `${s}://${a}${ws}${b}`;
        assert.equal(isWellFormed(u), false);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 6: 잘못된 URI는 invalid_uri로 신호
// Validates: Requirements 8.5, 8.6, 4.4
// ---------------------------------------------------------------------------
test("Property 6: 미지원 스킴은 parseUri/buildUri가 InvalidUriError를 던진다", () => {
  fc.assert(
    fc.property(
      // SCHEMES에 없는 스킴 문자열 (공백/콜론/슬래시 제외하여 separator 모호성 방지).
      fc
        .string({ minLength: 1, maxLength: 12 })
        .filter((s) => !SCHEMES.includes(s) && !/[\s:/]/.test(s)),
      validId,
      (badScheme, id) => {
        assert.throws(() => parseUri(`${badScheme}://${id}`), InvalidUriError);
        assert.throws(() => buildUri(badScheme, id), InvalidUriError);
        assert.equal(isWellFormed(`${badScheme}://${id}`), false);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test("Property 6: 비었거나 공백뿐인 식별자는 InvalidUriError를 던진다", () => {
  fc.assert(
    fc.property(
      scheme,
      // 빈 문자열 또는 공백만으로 구성된 식별자.
      fc.oneof(
        fc.constant(""),
        fc
          .array(fc.constantFrom(" ", "\t", "\n"), { minLength: 1, maxLength: 5 })
          .map((a) => a.join(""))
      ),
      (s, badId) => {
        // parseUri: "<scheme>://<badId>" 형태로 검증.
        assert.throws(() => parseUri(`${s}://${badId}`), InvalidUriError);
        // buildUri: 식별자 직접 검증.
        assert.throws(() => buildUri(s, badId), InvalidUriError);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test("Property 6: 잘못된 입력에 대해 잘못된 Resource_URI를 반환하지 않는다", () => {
  // parseUri는 잘못된 URI를 정상값처럼 돌려주지 않고 throw해야 한다.
  fc.assert(
    fc.property(
      fc.constantFrom(
        "no-separator-here",
        "://emptyscheme",
        "rag:/single-slash",
        ""
      ),
      (badUri) => {
        assert.throws(() => parseUri(badUri), InvalidUriError);
        assert.equal(isWellFormed(badUri), false);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});
