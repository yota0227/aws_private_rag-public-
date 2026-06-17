/**
 * lib/envelope.js — 출력 envelope (텍스트 말미 구조화 요약 블록)
 *
 * Spec: .kiro/specs/mcp-tool-optimization/ (Task 5, design "lib/envelope.js")
 *
 * 기존 사람이 읽는 텍스트(`text`)를 그대로 prefix로 보존하고, 그 **말미**에
 * 기계 파싱 가능한 구조화 요약 블록을 덧붙인다. 이는 기존 `execution_time_ms:`
 * 라인과 동일한 "텍스트 끝 부가정보" 패턴의 가산적(additive) 확장이다(Req 2.10, 2.11).
 *
 * 부착 필드:
 *   - index_version    : 비어있지 않은 인덱스 상태 식별자. 백엔드 미지원 시 "unknown" fallback (Req 2.3, OQ-1)
 *   - resolved_snapshot: 항상 구체 버전, 절대 리터럴 "latest" 아님 (Req 2.4~2.6)
 *   - resource_uris?   : addressable 결과별 well-formed Resource_URI. 없으면 필드 생략 (Req 2.1, 2.2)
 *   - request_id       : 호출 추적 식별자
 *
 * envelope는 **성공 응답 전용**이다. 에러 응답은 lib/errors.renderError로
 * Error_Schema만 반환하며 이 모듈의 부가필드를 부착하지 않는다(Req 2.9, Property 12).
 *
 * CommonJS — server.js와 동일.
 */

const { isWellFormed } = require("./uri");

// 텍스트 말미 구조화 블록 구분자. 기존 텍스트 prefix와 시각적으로 분리한다.
const ENVELOPE_SEPARATOR = "\n\n--- structured ---\n";

// resolved_snapshot이 절대 될 수 없는 리터럴 (Req 2.6).
const LATEST = "latest";

/**
 * 값이 "비어있음"인지 판정한다.
 * undefined/null, 또는 trim 후 빈 문자열을 비어있음으로 본다.
 */
function isEmptyValue(v) {
  if (v === undefined || v === null) return true;
  if (typeof v === "string" && v.trim().length === 0) return true;
  return false;
}

/**
 * resolved_snapshot 불변식 위반(리터럴 "latest" 또는 구체값 부재)을
 * upstream_error로 신호하는 에러를 생성한다.
 * lib/errors.classify가 err.code === "upstream_error"를 upstream_error로 매핑한다.
 */
function upstreamSnapshotError(requestedSnapshot, backendResolved) {
  const e = new Error(
    "resolved_snapshot invariant violation: cannot resolve to a concrete snapshot " +
      `(requested=${String(requestedSnapshot)}, backend=${String(backendResolved)})`
  );
  e.code = "upstream_error";
  return e;
}

/**
 * resolveSnapshot(requestedSnapshot, backendResolved) -> string
 *
 * 스냅샷 해석 규칙 (Req 2.4, 2.5, 2.6 / Property 10):
 *   - 요청이 "latest"이거나 미지정(빈 값) → 백엔드가 해석한 구체 스냅샷을 사용한다(Req 2.4).
 *   - 요청이 구체 스냅샷 → 그 값을 그대로 echo한다(Req 2.5).
 *   - 결과는 어느 경우에도 리터럴 "latest"가 될 수 없으며, 비어있을 수도 없다(Req 2.6).
 *     불변식 위반 시 upstream_error로 처리한다(throw).
 */
function resolveSnapshot(requestedSnapshot, backendResolved) {
  let resolved;
  if (isEmptyValue(requestedSnapshot) || requestedSnapshot === LATEST) {
    // latest/미지정 → 백엔드 해석 구체값
    resolved = backendResolved;
  } else {
    // 구체 스냅샷 → echo
    resolved = requestedSnapshot;
  }

  // 불변식: 절대 "latest" 아님, 절대 비어있지 않음 (Req 2.6)
  if (isEmptyValue(resolved) || resolved === LATEST) {
    throw upstreamSnapshotError(requestedSnapshot, backendResolved);
  }
  return resolved;
}

/**
 * resolveIndexVersion(indexVersion) -> string
 *
 * index_version은 항상 비어있지 않아야 한다(Req 2.3). 백엔드가 제공하지 않으면
 * OQ-1 결정에 따라 "unknown"으로 fallback한다.
 */
function resolveIndexVersion(indexVersion) {
  if (typeof indexVersion === "string" && indexVersion.trim().length > 0) {
    return indexVersion;
  }
  return "unknown";
}

/**
 * filterResourceUris(candidates) -> string[]
 *
 * 후보 Resource_URI 목록에서 well-formed인 것만 남기고(중복 제거, 입력 순서 보존)
 * 반환한다(Req 2.1, 2.2, 8.3 / Property 7, 8).
 *   - non-addressable(빈/null/placeholder/malformed)은 제외된다.
 *   - 동일 입력에 대해 결정적으로 동일한 결과를 반환한다(stable).
 *   - 동일 URI는 한 번만 포함한다(unique).
 */
function filterResourceUris(candidates) {
  if (!Array.isArray(candidates)) return [];
  const seen = new Set();
  const out = [];
  for (const c of candidates) {
    if (isWellFormed(c) && !seen.has(c)) {
      seen.add(c);
      out.push(c);
    }
  }
  return out;
}

/**
 * appendEnvelope(text, meta) -> string
 *
 * 기존 텍스트를 prefix로 보존하고 말미에 구조화 요약 블록을 덧붙인다.
 *
 * meta:
 *   - index_version    : 인덱스 상태 식별자(없으면 "unknown" fallback)
 *   - resolved_snapshot: 이미 해석된 구체 스냅샷(resolveSnapshot 결과). 리터럴 "latest"/빈값이면
 *                        불변식 위반으로 upstream_error를 throw한다(Req 2.6, Property 12 보호).
 *   - resource_uris    : 후보 Resource_URI 배열. well-formed만 부착하고 없으면 필드 생략.
 *   - request_id       : 호출 추적 식별자.
 *
 * 반환 JSON 키 순서: index_version, resolved_snapshot, resource_uris?, request_id.
 */
function appendEnvelope(text, meta) {
  const m = meta || {};

  // resolved_snapshot 불변식 재확인 — appendEnvelope는 성공 경로에서만 호출되며,
  // 리터럴 "latest"/빈값이 최종 응답에 새어 나가지 못하도록 마지막 방어선을 둔다.
  const resolvedSnapshot = m.resolved_snapshot;
  if (isEmptyValue(resolvedSnapshot) || resolvedSnapshot === LATEST) {
    throw upstreamSnapshotError(m.requested_snapshot, resolvedSnapshot);
  }

  // 키 순서를 명시적으로 구성한다.
  const structured = {};
  structured.index_version = resolveIndexVersion(m.index_version);
  structured.resolved_snapshot = resolvedSnapshot;

  const uris = filterResourceUris(m.resource_uris);
  if (uris.length > 0) {
    // addressable 결과가 하나라도 있을 때만 필드를 부착한다(Req 2.2 / Property 8).
    structured.resource_uris = uris;
  }

  structured.request_id = m.request_id;

  const base = typeof text === "string" ? text : "";
  return base + ENVELOPE_SEPARATOR + JSON.stringify(structured);
}

module.exports = {
  ENVELOPE_SEPARATOR,
  LATEST,
  appendEnvelope,
  resolveSnapshot,
  resolveIndexVersion,
  filterResourceUris,
};
