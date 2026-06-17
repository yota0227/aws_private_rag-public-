/**
 * lib/uri.js — Resource_URI parser / builder / validator
 *
 * Spec: .kiro/specs/mcp-tool-optimization/ (Task 3, design "lib/uri.js")
 *
 * 6개 스킴의 닫힌 집합(rag, rtl, graph, claim, job, index)만 인정하는
 * "<scheme>://<id>" 형태의 출력/재조회 식별자 규약이다.
 *
 * 식별자 규약일 뿐 접근제어를 함의하지 않는다(Req 8.7). 이 모듈은
 * corpus/access-control 개념을 유도하거나 참조하지 않는다.
 *
 * CommonJS — server.js와 동일.
 */

// 닫힌 6개 스킴 집합 (Req 8.1). 대소문자 구분(소문자만 유효).
const SCHEMES = ["rag", "rtl", "graph", "claim", "job", "index"];

const SCHEME_SET = new Set(SCHEMES);
const SEPARATOR = "://";

/**
 * Resource_URI 위반 시 던지는 커스텀 에러.
 * lib/errors.js가 이 에러를 invalid_uri 코드로 매핑한다.
 */
class InvalidUriError extends Error {
  constructor(message) {
    super(message);
    this.name = "InvalidUriError";
    this.code = "invalid_uri";
  }
}

/**
 * 식별자(id) 구성요소가 유효한지 검사한다.
 * 비어있지 않고 공백(whitespace)을 포함하지 않아야 한다(Req 8.2, 8.6).
 * 프래그먼트(예: "#section=8.2", "#L120-L180")는 공백이 없으므로
 * id의 일부로 그대로 허용되어 round-trip에서 보존된다.
 */
function isValidId(id) {
  return typeof id === "string" && id.length > 0 && !/\s/.test(id);
}

/**
 * 문자열을 { scheme, id }로 분해한다(검증 없이 구조만).
 * "<scheme>://<id>" 형태가 아니면 null을 반환한다.
 * id는 첫 "://" 이후 전체(프래그먼트 포함)를 보존한다.
 */
function splitUri(uri) {
  if (typeof uri !== "string") return null;
  const sepIndex = uri.indexOf(SEPARATOR);
  if (sepIndex < 0) return null;
  const scheme = uri.slice(0, sepIndex);
  const id = uri.slice(sepIndex + SEPARATOR.length);
  return { scheme, id };
}

/**
 * parseUri(uri) -> { scheme, id }
 * 미지원 스킴(Req 8.5) 또는 비었/공백 포함 식별자(Req 8.2, 8.6)면
 * InvalidUriError를 던진다.
 */
function parseUri(uri) {
  const parts = splitUri(uri);
  if (parts === null) {
    throw new InvalidUriError(
      `malformed Resource_URI (expected "<scheme>://<id>"): ${String(uri)}`
    );
  }
  const { scheme, id } = parts;
  if (!SCHEME_SET.has(scheme)) {
    throw new InvalidUriError(`unsupported Resource_URI scheme: ${scheme}`);
  }
  if (!isValidId(id)) {
    throw new InvalidUriError(
      `empty or whitespace-containing identifier in Resource_URI: ${String(uri)}`
    );
  }
  return { scheme, id };
}

/**
 * buildUri(scheme, id) -> "<scheme>://<id>"
 * parseUri와 동일한 검증을 적용하고, 위반 시 InvalidUriError를 던진다.
 */
function buildUri(scheme, id) {
  if (!SCHEME_SET.has(scheme)) {
    throw new InvalidUriError(`unsupported Resource_URI scheme: ${String(scheme)}`);
  }
  if (!isValidId(id)) {
    throw new InvalidUriError(
      `empty or whitespace-containing identifier for Resource_URI: ${String(id)}`
    );
  }
  return `${scheme}${SEPARATOR}${id}`;
}

/**
 * isWellFormed(uri) -> boolean
 * 6개 스킴 prefix 중 하나 + 비어있지 않고 공백 없는 식별자일 때에만 true.
 * 절대 throw하지 않는다(Req 8.1, 8.2).
 */
function isWellFormed(uri) {
  const parts = splitUri(uri);
  if (parts === null) return false;
  return SCHEME_SET.has(parts.scheme) && isValidId(parts.id);
}

module.exports = {
  SCHEMES,
  InvalidUriError,
  parseUri,
  buildUri,
  isWellFormed,
};
