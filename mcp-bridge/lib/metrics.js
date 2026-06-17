// lib/metrics.js — latency 백분위 (rolling 5분 윈도우)
//
// Feature: mcp-tool-optimization (Task 7, Req 6.6)
//
// 도구 호출 latency(ms)를 메모리 내 rolling 5분 윈도우에 적재하고,
// 요청 시 p50/p95/p99(ms)를 계산한다. 윈도우 밖(5분 초과) 샘플은 만료되어
// 계산에서 제외된다.
//
// 식별자-free: 사용자/팀/corpus 등 어떤 식별자도 저장하지 않는다.
// 샘플은 { t, latency_ms }만 보관하며, tool 키는 메트릭 라벨일 뿐 호출자
// 식별자가 아니다(Req 6.8/6.9 관측성 화이트리스트와 일관).
//
// "now"는 주입 가능하다(setClock). 테스트는 실제 대기 없이 시간을 시뮬레이션한다.

'use strict';

// rolling 윈도우 크기 = 5분
const WINDOW_MS = 5 * 60 * 1000;

// tool -> [ { t: epoch_ms, latency_ms } ... ]
const samples = new Map();

// 주입 가능한 시계. 기본은 실시간 Date.now.
let clock = Date.now;

/**
 * 시계 함수를 주입한다(테스트용). nowMs를 반환하는 함수여야 한다.
 * @param {() => number} fn
 */
function setClock(fn) {
  if (typeof fn !== 'function') {
    throw new TypeError('setClock expects a function returning epoch milliseconds');
  }
  clock = fn;
}

/** 시계를 실시간(Date.now)으로 되돌린다. */
function resetClock() {
  clock = Date.now;
}

/** 모든 적재 샘플을 비운다(테스트 격리용). */
function reset() {
  samples.clear();
}

/** 현재 시각(ms). 주입된 시계를 사용한다. */
function nowMs() {
  return clock();
}

/**
 * tool 버킷에서 윈도우 밖 샘플을 제거한다.
 * 샘플은 (now - t) <= WINDOW_MS 인 경우에만 유지된다.
 * @param {Array<{t:number, latency_ms:number}>} bucket
 * @param {number} now
 * @returns {Array<{t:number, latency_ms:number}>}
 */
function pruneBucket(bucket, now) {
  const cutoff = now - WINDOW_MS;
  return bucket.filter((s) => s.t >= cutoff);
}

/**
 * 도구 호출 latency 샘플을 적재한다.
 * @param {string} tool 도구 이름(메트릭 라벨)
 * @param {number} latency_ms 측정된 latency(ms)
 */
function record(tool, latency_ms) {
  if (typeof tool !== 'string' || tool.length === 0) {
    throw new TypeError('record expects a non-empty tool name');
  }
  if (typeof latency_ms !== 'number' || !Number.isFinite(latency_ms)) {
    throw new TypeError('record expects a finite numeric latency_ms');
  }
  const now = nowMs();
  let bucket = samples.get(tool);
  if (!bucket) {
    bucket = [];
    samples.set(tool, bucket);
  }
  bucket.push({ t: now, latency_ms });
  // 적재 시점에 만료 샘플을 정리해 메모리 증가를 억제한다.
  samples.set(tool, pruneBucket(bucket, now));
}

/**
 * 정렬된(오름차순) latency 배열에서 백분위 값을 nearest-rank 방식으로 계산.
 * p ∈ [0,1]. 빈 배열이면 0을 반환한다.
 * nearest-rank는 p가 커질수록 인덱스가 단조 증가하므로 p50<=p95<=p99를 보장한다.
 * @param {number[]} sorted
 * @param {number} p
 * @returns {number}
 */
function percentile(sorted, p) {
  const n = sorted.length;
  if (n === 0) return 0;
  let idx = Math.ceil(p * n) - 1;
  if (idx < 0) idx = 0;
  if (idx > n - 1) idx = n - 1;
  return sorted[idx];
}

/**
 * 현재 rolling 5분 윈도우 기준 백분위를 계산한다.
 * 윈도우 밖 샘플은 제외된다.
 * @param {string} tool
 * @returns {{p50:number, p95:number, p99:number}}
 */
function percentiles(tool) {
  const now = nowMs();
  const bucket = samples.get(tool) || [];
  const inWindow = pruneBucket(bucket, now);
  // 만료 샘플을 영구적으로 정리한다.
  if (inWindow.length !== bucket.length) {
    samples.set(tool, inWindow);
  }
  const sorted = inWindow.map((s) => s.latency_ms).sort((a, b) => a - b);
  return {
    p50: percentile(sorted, 0.5),
    p95: percentile(sorted, 0.95),
    p99: percentile(sorted, 0.99),
  };
}

module.exports = {
  record,
  percentiles,
  // 헬퍼(테스트용)
  setClock,
  resetClock,
  reset,
  WINDOW_MS,
};
