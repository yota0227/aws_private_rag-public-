// Property tests for lib/logging.js
//
// Runner: node:test. Property library: fast-check ({ numRuns >= 100 }).
// Target: pure logic in mcp-bridge/lib/logging.js (no Lambda/DynamoDB calls).

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fc = require('fast-check');

const logging = require('../lib/logging');

// Fields that MUST never appear in an emitted observability record (Req 6.8, 6.9).
const FORBIDDEN_FIELDS = [
  'user_id',
  'team_id',
  'user',
  'team',
  'corpus_allowed',
  'corpus_denied',
  'corpusAllowed',
  'corpusDenied',
];

// Feature: mcp-tool-optimization, Property 25: request_id 재사용/생성 유일성
// Validates: Requirements 6.3, 6.4
test('Property 25: incoming request_id is reused; absent request_id is generated uniquely', () => {
  // Part A — when an incoming request_id is present (non-empty), it is reused verbatim.
  fc.assert(
    fc.property(
      // non-empty, non-whitespace incoming id
      fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
      fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
      (incomingId, tool) => {
        const resolved = logging.resolveRequestId(incomingId);
        assert.equal(resolved, incomingId);

        const emitted = logging.emit(
          { request_id: incomingId, tool, latency_ms: 1, outcome: 'success' },
          () => {}
        );
        assert.equal(emitted.request_id, incomingId);
      }
    ),
    { numRuns: 100 }
  );

  // Part B — when request_id is absent/empty/whitespace, a fresh one is generated,
  // and many generated ids are mutually distinct (process-lifetime uniqueness).
  fc.assert(
    fc.property(
      fc.constantFrom(undefined, null, '', '   ', '\t', '\n'),
      (absent) => {
        const generated = logging.resolveRequestId(absent);
        assert.equal(typeof generated, 'string');
        assert.ok(generated.trim().length > 0);

        // emit with no request_id must still produce a non-empty generated one.
        const emitted = logging.emit(
          { tool: 'rag_query', latency_ms: 2, outcome: 'success' },
          () => {}
        );
        assert.equal(typeof emitted.request_id, 'string');
        assert.ok(emitted.request_id.trim().length > 0);
      }
    ),
    { numRuns: 100 }
  );

  // Part C — generated ids do not collide across a batch (uniqueness).
  const seen = new Set();
  const N = 1000;
  for (let i = 0; i < N; i += 1) {
    const id = logging.newRequestId();
    assert.ok(!seen.has(id), `duplicate generated request_id: ${id}`);
    seen.add(id);
  }
  assert.equal(seen.size, N);
});

// Feature: mcp-tool-optimization, Property 27: 관측성 출력 필드 화이트리스트
// Validates: Requirements 6.8, 6.9
test('Property 27: emitted record contains no identity or corpus audit fields', () => {
  fc.assert(
    fc.property(
      // arbitrary extra object that may include forbidden fields plus random keys
      fc.record({
        request_id: fc.option(fc.string({ minLength: 1 }), { nil: undefined }),
        tool: fc.string({ minLength: 1 }).filter((s) => s.trim() !== ''),
        latency_ms: fc.integer({ min: 0, max: 1_000_000 }),
        outcome: fc.constantFrom('success', 'failure'),
        error_category: fc.option(fc.string(), { nil: undefined }),
        // injected forbidden identity / corpus audit fields
        user_id: fc.string(),
        team_id: fc.string(),
        user: fc.string(),
        team: fc.string(),
        corpus_allowed: fc.array(fc.string()),
        corpus_denied: fc.array(fc.string()),
        corpusAllowed: fc.array(fc.string()),
        corpusDenied: fc.array(fc.string()),
      }),
      // arbitrary additional bag of unknown keys
      fc.dictionary(fc.string(), fc.anything()),
      (base, extraBag) => {
        const input = { ...extraBag, ...base };

        let captured = null;
        const emitted = logging.emit(input, (line) => {
          captured = line;
        });

        // The returned (sanitized) record must contain none of the forbidden fields.
        for (const field of FORBIDDEN_FIELDS) {
          assert.ok(
            !Object.prototype.hasOwnProperty.call(emitted, field),
            `forbidden field present in emitted record: ${field}`
          );
        }

        // Every emitted key must be in the whitelist.
        for (const key of Object.keys(emitted)) {
          assert.ok(
            logging.LOG_FIELD_WHITELIST.includes(key),
            `non-whitelisted field emitted: ${key}`
          );
        }

        // The serialized log line must also not contain forbidden field keys
        // as JSON object keys.
        assert.equal(typeof captured, 'string');
        const parsed = JSON.parse(captured);
        for (const field of FORBIDDEN_FIELDS) {
          assert.ok(
            !Object.prototype.hasOwnProperty.call(parsed, field),
            `forbidden field serialized in log line: ${field}`
          );
        }

        // Exactly one log line emitted (no embedded raw newlines; JSON escapes them).
        assert.ok(!captured.includes('\n'));
      }
    ),
    { numRuns: 100 }
  );
});
