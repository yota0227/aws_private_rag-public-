/**
 * lib/errors.js — Error_Schema 생성·분류·렌더링
 *
 * Spec: .kiro/specs/mcp-tool-optimization/ (Task 4, design "lib/errors.js")
 *
 * 닫힌 3개 error_code 집합(invalid_uri / not_found / upstream_error)으로
 * 모든 도구 에러를 정규화한다. 에러 응답은 Error_Schema(error_code + message)만
 * 담으며, 부분적인 Resource_URI / index_version / resolved_snapshot 필드를
 * 절대 부착하지 않는다(Req 2.9).
 *
 * 기존 server.js의 에러 응답 형식 `{ content: [{ type: "text", text }], isError: true }`
 * 를 그대로 유지한다(Req 2.10).
 *
 * CommonJS — server.js와 동일.
 */

const { InvalidUriError } = require("./uri");

/**
 * 닫힌 3개 error_code 집합 (Req 2.7, 2.8, 4.8).
 */
const ERROR_CODES = {
  INVALID_URI: "invalid_uri",
  NOT_FOUND: "not_found",
  UPSTREAM_ERROR: "upstream_error",
};

const VALID_CODES = new Set([
  ERROR_CODES.INVALID_URI,
  ERROR_CODES.NOT_FOUND,
  ERROR_CODES.UPSTREAM_ERROR,
]);

/**
 * makeError(code, message) -> { error_code, message }
 *
 * 정확히 1개의 유효한 코드와 비어있지 않은 메시지를 가진 Error_Schema를 생성한다(Req 2.7).
 * - 유효하지 않은 code는 보수적으로 upstream_error로 정규화한다.
 * - 비어있거나 공백뿐인 message는 코드 기반의 비어있지 않은 기본 메시지로 대체한다.
 */
function makeError(code, message) {
  const error_code = VALID_CODES.has(code) ? code : ERROR_CODES.UPSTREAM_ERROR;
  let msg = typeof message === "string" ? message.trim() : "";
  if (msg.length === 0) {
    msg = `unspecified ${error_code} error`;
  }
  return { error_code, message: msg };
}

/**
 * classify(err) -> code
 *
 * 임의의 에러를 닫힌 3개 코드 중 정확히 하나로 분류한다.
 * - URI 파싱/스킴/식별자 위반(InvalidUriError 또는 err.code === "invalid_uri") -> invalid_uri (Req 8.5, 8.6, 4.4)
 * - 자원/job/claim 부재 신호(err.code === "not_found") -> not_found (Req 4.5, 4.7)
 * - 그 외 일체 -> upstream_error (Req 2.8, 4.8)
 */
function classify(err) {
  if (err instanceof InvalidUriError) {
    return ERROR_CODES.INVALID_URI;
  }
  const code = err && typeof err === "object" ? err.code : undefined;
  if (code === ERROR_CODES.INVALID_URI) {
    return ERROR_CODES.INVALID_URI;
  }
  if (code === ERROR_CODES.NOT_FOUND) {
    return ERROR_CODES.NOT_FOUND;
  }
  return ERROR_CODES.UPSTREAM_ERROR;
}

/**
 * renderError(errObj) -> MCP tool response
 *
 * Error_Schema({ error_code, message })를 기존 server.js 에러 응답 형식
 * `{ content: [{ type: "text", text }], isError: true }`에 담아 반환한다.
 * 텍스트에는 Error_Schema만 직렬화하며, 부분 Resource_URI / index_version /
 * resolved_snapshot 필드를 부착하지 않는다(Req 2.9).
 *
 * errObj가 정규 Error_Schema가 아니면 makeError로 정규화한다.
 */
function renderError(errObj) {
  let schema;
  if (
    errObj &&
    typeof errObj === "object" &&
    typeof errObj.error_code === "string" &&
    VALID_CODES.has(errObj.error_code) &&
    typeof errObj.message === "string" &&
    errObj.message.trim().length > 0
  ) {
    schema = { error_code: errObj.error_code, message: errObj.message };
  } else {
    schema = makeError(errObj && errObj.error_code, errObj && errObj.message);
  }
  return {
    content: [{ type: "text", text: JSON.stringify(schema) }],
    isError: true,
  };
}

module.exports = {
  ERROR_CODES,
  makeError,
  classify,
  renderError,
};
