// lib/logging.js — 구조화 로깅 (Req 6.1~6.5, 6.7~6.9)
//
// CloudWatch Logs로 도구 호출당 정확히 1건의 JSON 레코드를 방출한다.
// 필드: request_id, tool, latency_ms, outcome ∈ {success, failure},
//       timestamp(UTC ISO 8601), 실패 시 error_category.
//
// request_id는 들어온 것을 재사용하고, 없으면 프로세스 수명 내 유일한 값을
// crypto.randomUUID()로 생성한다.
//
// 식별자-free 관측성: 사용자/팀 식별자 및 corpus allowed/denied 감사 필드를
// 포함하지 않는다(Req 6.8, 6.9). 명시적 화이트리스트로 허용된 필드만 방출한다.

'use strict';

const crypto = require('node:crypto');

// 방출 가능한 필드의 닫힌 화이트리스트 (Req 6.8, 6.9).
// 이 집합 밖의 모든 키(예: user_id, team_id, corpus_allowed, corpus_denied)는
// 입력에 존재하더라도 방출 레코드에서 제외된다.
const LOG_FIELD_WHITELIST = Object.freeze([
  'request_id',
  'tool',
  'latency_ms',
  'outcome',
  'timestamp',
  'error_category',
]);

const OUTCOMES = Object.freeze(['success', 'failure']);

/**
 * 프로세스 수명 내 유일한 request_id를 생성한다 (Req 6.3).
 * @returns {string} RFC4122 v4 UUID
 */
function newRequestId() {
  return crypto.randomUUID();
}

/**
 * 들어온 request_id가 있으면 그대로 재사용하고, 없으면 새로 생성한다
 * (Req 6.3, 6.4). 비어있거나 공백뿐인 값은 부재로 간주한다.
 * @param {string|undefined|null} incoming
 * @returns {string}
 */
function resolveRequestId(incoming) {
  if (typeof incoming === 'string' && incoming.trim() !== '') {
    return incoming;
  }
  return newRequestId();
}

/**
 * 현재 시각을 UTC ISO 8601 문자열로 반환한다.
 * @returns {string}
 */
function isoUtc() {
  return new Date().toISOString();
}

/**
 * 입력 레코드를 화이트리스트로 필터링하여, 허용된 필드만 가진 정규 레코드를
 * 만든다. 화이트리스트 밖의 모든 필드(식별자/감사 필드 포함)는 제거된다.
 * timestamp가 없으면 채우고, request_id가 없으면 생성한다.
 * @param {object} record
 * @returns {object} 방출될 정규 레코드 (화이트리스트 필드만)
 */
function sanitize(record) {
  const input = record && typeof record === 'object' ? record : {};
  const out = {};
  for (const key of LOG_FIELD_WHITELIST) {
    if (input[key] !== undefined) {
      out[key] = input[key];
    }
  }
  // 필수 필드 보정 — 식별자 없이 가능한 값으로만 채운다.
  if (out.request_id === undefined) {
    out.request_id = newRequestId();
  }
  if (out.timestamp === undefined) {
    out.timestamp = isoUtc();
  }
  return out;
}

/**
 * 도구 호출당 정확히 1건의 구조화 JSON 로그 라인을 방출한다 (Req 6.1, 6.2).
 *
 * 기본 sink는 stdout으로 한 줄 JSON을 쓴다(CloudWatch Logs 적합).
 * 테스트에서는 sink를 주입하여 stdout 오염 없이 레코드를 포착할 수 있다.
 * 어떤 입력 필드가 와도 화이트리스트 밖 필드는 절대 방출되지 않는다.
 *
 * @param {object} record - { request_id, tool, latency_ms, outcome, timestamp?, error_category? }
 * @param {(line: string) => void} [sink] - 방출 싱크 (기본: stdout 한 줄)
 * @returns {object} 실제로 방출된 정규 레코드 (검증/테스트 편의용)
 */
function emit(record, sink) {
  const sanitized = sanitize(record);
  const line = JSON.stringify(sanitized);
  const write =
    typeof sink === 'function'
      ? sink
      : (l) => process.stdout.write(l + '\n');
  write(line);
  return sanitized;
}

module.exports = {
  LOG_FIELD_WHITELIST,
  OUTCOMES,
  newRequestId,
  resolveRequestId,
  isoUtc,
  sanitize,
  emit,
};
