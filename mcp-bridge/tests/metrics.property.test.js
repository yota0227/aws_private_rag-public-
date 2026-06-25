// Feature: mcp-tool-optimization, Property 26: latency 백분위 단조성 + 윈도우
// Validates: Requirements 6.6
//
// 임의의 latency 샘플 집합에 대해:
//   (a) 산출된 백분위는 p50 <= p95 <= p99 (ms) 를 만족한다.
//   (b) rolling 5분 윈도우 밖의 샘플은 계산에서 제외된다.
// 주입 가능한 시계(setClock)로 실제 대기 없이 시간을 진행시켜 윈도우 만료를 검증한다.

'use strict';

const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fc = require('fast-check');

const metrics = require('../lib/metrics');

const TOOL = 'search_rtl';

// 시뮬레이션 시계: mutable 변수를 metrics에 주입한다.
let simNow = 0;
function setSimNow(v) {
  simNow = v;
}

beforeEach(() => {
  metrics.reset();
  simNow = 1_000_000; // 임의의 0 아닌 기준 시각
  metrics.setClock(() => simNow);
});

afterEach(() => {
  metrics.reset();
  metrics.resetClock();
});

test('Property 26a: 백분위는 p50 <= p95 <= p99 단조성을 만족한다', () => {
  fc.assert(
    fc.property(
      // 비어있지 않은 latency 샘플 집합 (0..60000 ms)
      fc.array(fc.double({ min: 0, max: 60000, noNaN: true }), { minLength: 1, maxLength: 200 }),
      (latencies) => {
        metrics.reset();
        for (const ms of latencies) {
          metrics.record(TOOL, ms);
        }
        const { p50, p95, p99 } = metrics.percentiles(TOOL);
        return p50 <= p95 && p95 <= p99;
      }
    ),
    { numRuns: 200 }
  );
});

test('Property 26b: rolling 5분 윈도우 밖 샘플은 계산에서 제외된다', () => {
  const WINDOW_MS = metrics.WINDOW_MS;
  fc.assert(
    fc.property(
      // 윈도우 안에 머무를 "최근" 샘플들
      fc.array(fc.double({ min: 0, max: 1000, noNaN: true }), { minLength: 1, maxLength: 50 }),
      // 윈도우 밖으로 만료될 "오래된" 샘플들 (값이 명확히 더 큼)
      fc.array(fc.double({ min: 100000, max: 200000, noNaN: true }), { minLength: 1, maxLength: 50 }),
      // 오래된 샘플을 만료시키기 위한 추가 경과 시간 (> 0)
      fc.integer({ min: 1, max: 10 * 60 * 1000 }),
      (recent, old, advance) => {
        metrics.reset();

        // t0: 오래된(큰 값) 샘플 적재
        setSimNow(1_000_000);
        for (const ms of old) {
          metrics.record(TOOL, ms);
        }

        // 시간을 윈도우 크기보다 더 진행시켜 오래된 샘플을 만료시킨다.
        setSimNow(1_000_000 + WINDOW_MS + advance);
        for (const ms of recent) {
          metrics.record(TOOL, ms);
        }

        const { p50, p95, p99 } = metrics.percentiles(TOOL);

        // 오래된 샘플(>=100000)이 제외되었다면 모든 백분위는 recent 최대값(<=1000) 이하다.
        const recentMax = Math.max(...recent);
        return p50 <= recentMax && p95 <= recentMax && p99 <= recentMax;
      }
    ),
    { numRuns: 200 }
  );
});

test('Property 26b-edge: 모든 샘플이 만료되면 빈 윈도우로 처리된다', () => {
  const WINDOW_MS = metrics.WINDOW_MS;
  metrics.reset();
  setSimNow(1_000_000);
  metrics.record(TOOL, 500);
  metrics.record(TOOL, 1500);

  // 정확히 윈도우 안(경계 포함)에서는 유지
  setSimNow(1_000_000 + WINDOW_MS);
  let p = metrics.percentiles(TOOL);
  assert.ok(p.p50 <= p.p95 && p.p95 <= p.p99);
  assert.ok(p.p99 > 0);

  // 윈도우를 1ms 넘기면 모두 만료 → 0
  setSimNow(1_000_000 + WINDOW_MS + 1);
  p = metrics.percentiles(TOOL);
  assert.deepEqual(p, { p50: 0, p95: 0, p99: 0 });
});
