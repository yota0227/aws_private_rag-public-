/**
 * lib/evidence.js — Evidence-first 컴포넌트
 *
 * Spec: .kiro/specs/mcp-tool-optimization/ (Task 13.1, design "Evidence-first 컴포넌트")
 *
 * 두 가지 책임을 가진 순수(pure) 로직 모듈이다(부수효과 없음, 주입 가능):
 *
 *  1) get_evidence 정규화 (Req 3.1, 3.2)
 *     백엔드 evidence 항목(source_document_id / source_type / source_chunk /
 *     page_number / source_path / line_start / line_end)을 정규 스키마
 *     (source_uri / source_type / support_level / confidence(0..1) / span)로 매핑.
 *     evidence가 0건이면 빈 리스트를 반환하고 Error_Schema를 반환하지 않는다.
 *
 *  2) 문장 분할 + coverage 판정 (Task 13.3 rag_validate_answer에서 재사용)
 *     segmentSentences(text) 와 computeCoverage(sentences, evidenceLookup)는
 *     evidence-lookup을 주입받는 순수 함수다. 문장에 연결된 evidence가 0건이면
 *     unsupported로 라벨링한다.
 *
 * CommonJS — server.js와 동일.
 */

const { buildUri, isWellFormed } = require("./uri");

// 백엔드 source_type 누락 시 보수적 기본값 (비어있지 않게 보정, Req 3.1).
const DEFAULT_SOURCE_TYPE = "unknown";

// 백엔드 support 신호 누락 시 보수적 기본값(약한 근거로 간주).
const DEFAULT_SUPPORT_LEVEL = "weak";

// confidence 누락/비정상 시 보수적 기본값.
const DEFAULT_CONFIDENCE = 0;

// RTL로 간주하는 source_type / 파일 확장자.
const RTL_TYPES = new Set(["rtl", "verilog", "systemverilog", "vhdl"]);
const RTL_EXT_RE = /\.(v|sv|svh|svp|vh|vhd|vhdl)$/i;

// ---------------------------------------------------------------------------
// 내부 헬퍼
// ---------------------------------------------------------------------------

/** 비어있지 않은 trim 문자열이면 그 값을, 아니면 null을 반환. */
function nonEmptyString(value) {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/** 정수로 해석 가능하면 정수, 아니면 null. */
function toInt(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.trunc(n);
}

/** confidence를 [0, 1] 폐구간으로 클램프. 비정상 입력은 보수적 기본값. */
function clampConfidence(value) {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return DEFAULT_CONFIDENCE;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

/** 백엔드 신호로부터 support_level을 도출(없으면 보수적 기본값). */
function deriveSupportLevel(item) {
  const explicit = nonEmptyString(item.support_level);
  if (explicit) return explicit;
  return DEFAULT_SUPPORT_LEVEL;
}

/** line_start/line_end가 하나라도 있으면 span 객체, 없으면 null. */
function deriveSpan(item) {
  const ls = toInt(item.line_start);
  const le = toInt(item.line_end);
  if (ls === null && le === null) return null;
  const span = {};
  if (ls !== null) span.line_start = ls;
  if (le !== null) span.line_end = le;
  return span;
}

/** source_type/path를 보고 RTL이면 "rtl", 아니면 "rag" 스킴 선택. */
function pickScheme(item, sourceType) {
  if (RTL_TYPES.has(sourceType.toLowerCase())) return "rtl";
  const path = nonEmptyString(item.source_path);
  if (path && RTL_EXT_RE.test(path)) return "rtl";
  return "rag";
}

/**
 * well-formed Resource_URI를 구성한다(Req 3.1, 8.x).
 * source_path를 우선, 없으면 source_document_id를 식별자 베이스로 사용.
 * line 정보가 있으면 "#L<start>-L<end>" 프래그먼트를 부착한다.
 * well-formed URI를 만들 수 없으면(베이스 없음/공백 포함 등) undefined를 반환하여
 * 호출부에서 source_uri 필드를 생략하게 한다 — 잘못된 URI를 절대 방출하지 않는다.
 */
function buildSourceUri(item, sourceType) {
  const base =
    nonEmptyString(item.source_path) || nonEmptyString(item.source_document_id);
  if (!base) return undefined;

  const scheme = pickScheme(item, sourceType);
  const ls = toInt(item.line_start);
  const le = toInt(item.line_end);

  let id = base;
  if (ls !== null) {
    id += le !== null ? `#L${ls}-L${le}` : `#L${ls}`;
  }

  // buildUri는 공백 포함/빈 식별자에 대해 throw → 그 경우 source_uri 생략.
  let uri;
  try {
    uri = buildUri(scheme, id);
  } catch (_e) {
    // 프래그먼트 없이 베이스만으로 한 번 더 시도.
    try {
      uri = buildUri(scheme, base);
    } catch (_e2) {
      return undefined;
    }
  }
  // 방어적 최종 검증(불변식): 반환 전 well-formed 확인.
  return isWellFormed(uri) ? uri : undefined;
}

// ---------------------------------------------------------------------------
// 공개 API
// ---------------------------------------------------------------------------

/**
 * normalizeEvidence(rawItem, opts?) -> 정규화된 evidence 객체
 *
 * 필드:
 *   source_type   : 비어있지 않은 문자열(기본값 "unknown")
 *   support_level : 비어있지 않은 문자열(기본값 "weak")
 *   confidence    : [0,1] 클램프된 숫자
 *   span          : { line_start?, line_end? } — line 정보가 있을 때만
 *   source_uri    : well-formed Resource_URI — 구성 가능할 때만(아니면 생략)
 */
function normalizeEvidence(rawItem, _opts = {}) {
  const item = rawItem && typeof rawItem === "object" ? rawItem : {};

  const sourceType = nonEmptyString(item.source_type) || DEFAULT_SOURCE_TYPE;

  const normalized = {
    source_type: sourceType,
    support_level: deriveSupportLevel(item),
    confidence: clampConfidence(item.confidence),
  };

  const span = deriveSpan(item);
  if (span) normalized.span = span;

  const sourceUri = buildSourceUri(item, sourceType);
  if (sourceUri) normalized.source_uri = sourceUri;

  return normalized;
}

/**
 * normalizeEvidenceList(rawList) -> 정규화된 evidence 객체 배열
 * 비었거나 없는 리스트면 [] 반환(Error_Schema 아님) — Property 14 / Req 3.2.
 */
function normalizeEvidenceList(rawList) {
  if (!Array.isArray(rawList)) return [];
  return rawList.map((item) => normalizeEvidence(item));
}

/**
 * segmentSentences(text) -> string[]
 * 텍스트를 문장 단위로 분할한다. 문장 종결부호(. ! ? 。) 또는 줄바꿈을 경계로 사용.
 * 종결부호/공백만으로 이루어진 조각은 버린다. 순수 함수.
 */
function segmentSentences(text) {
  if (typeof text !== "string") return [];
  const out = [];
  // 종결부호로 끝나는 런 또는 종결부호 없는 마지막 런.
  const re = /[^.!?。\n]*[.!?。\n]|[^.!?。\n]+$/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m[0].length === 0) {
      re.lastIndex += 1; // zero-width 매치 방지
      continue;
    }
    // 실제 내용(종결부호/공백 제외)이 있는 경우에만 채택.
    const meaningful = m[0].replace(/[.!?。\s]+/gu, "");
    if (meaningful.length > 0) {
      out.push(m[0].trim());
    }
  }
  return out;
}

/**
 * computeCoverage(sentences, evidenceLookup) -> coverage 결과
 *
 * evidenceLookup은 주입되는 순수 조회 함수다: (sentence, index) => evidence
 *   - 배열 반환 시 그 length를 evidence 개수로 사용
 *   - 숫자 반환 시 그 값을 개수로 사용
 *   - truthy 단일 값 반환 시 1개로 간주
 *   - falsy/throw 시 0개
 * 문장의 evidence 개수가 0이면 unsupported로 라벨링한다(Req 3.4).
 *
 * 반환:
 *   {
 *     sentences: [{ index, text, evidence_count, supported }],
 *     unsupported: [{ index, text }],
 *     supported_count, unsupported_count, total
 *   }
 */
function computeCoverage(sentences, evidenceLookup) {
  const list = Array.isArray(sentences) ? sentences : [];
  const lookup =
    typeof evidenceLookup === "function" ? evidenceLookup : () => [];

  const labeled = list.map((sentence, index) => {
    let count = 0;
    try {
      const r = lookup(sentence, index);
      if (Array.isArray(r)) count = r.length;
      else if (typeof r === "number" && Number.isFinite(r))
        count = Math.max(0, Math.trunc(r));
      else if (r) count = 1;
    } catch (_e) {
      count = 0;
    }
    return {
      index,
      text: sentence,
      evidence_count: count,
      supported: count > 0,
    };
  });

  const unsupported = labeled
    .filter((s) => !s.supported)
    .map((s) => ({ index: s.index, text: s.text }));

  return {
    sentences: labeled,
    unsupported,
    supported_count: labeled.length - unsupported.length,
    unsupported_count: unsupported.length,
    total: labeled.length,
  };
}

// ---------------------------------------------------------------------------
// Evidence-first 가드 프리미티브 (Task 13.6 / 13.8) — 순수 함수, 주입 불필요.
//
// server.js의 generate_hdd_section(verified-only)와 publish_markdown(pre-save 가드)이
// 공유하는 결정적(deterministic) 검출 로직을 lib에 두어 백엔드 없이 단위 테스트 가능하게 한다.
// (답변 coverage 판정은 ragApi 호출이 필요하므로 server.js의 로컬 async 헬퍼에 남긴다.)
// ---------------------------------------------------------------------------

// Task 13.6 — verified-only HDD 마커 리터럴 (Property 17, Req 3.7).
// allow_unverified_inference=false일 때 지원 근거 0 세그먼트를 이 마커로 표기한다.
const UNVERIFIED_MARKER = "확실하지 않음";

/**
 * containsUnresolvedLatest(text) -> boolean   (Task 13.8, Property 18, Req 3.9)
 *
 * 스냅샷/버전 참조로 쓰인 미해석 리터럴 토큰 "latest"를 단어 경계로 탐지한다.
 * 대소문자 무시. "translatest"/"latestable" 같은 부분 일치는 단어 경계로 제외된다.
 * 순수 함수 — 부수효과 없음.
 */
function containsUnresolvedLatest(text) {
  if (typeof text !== "string") return false;
  return /\blatest\b/i.test(text);
}

/**
 * markUnsupportedSegments(markdown, unsupportedSegments) -> string   (Task 13.6, Property 17, Req 3.7)
 *
 * 지원 근거가 0인 생성 세그먼트를 UNVERIFIED_MARKER로 표기한다.
 *   - unsupportedSegments: 문자열 또는 { text } / { segment } 객체의 배열.
 *   - markdown 내에서 세그먼트 텍스트를 찾으면 그 뒤에 " [확실하지 않음]"을 부착한다.
 *   - 표기할 세그먼트를 하나도 특정하지 못하면(백엔드 coverage 미제공 등) 보수적으로
 *     상단에 미검증 추론 비활성화 공지를 덧붙여 마커가 최소 1회 존재함을 보장한다.
 * 순수 함수 — 부수효과 없음.
 */
function markUnsupportedSegments(markdown, unsupportedSegments) {
  const md = typeof markdown === "string" ? markdown : "";
  const segs = Array.isArray(unsupportedSegments) ? unsupportedSegments : [];
  let out = md;
  let marked = 0;
  for (const seg of segs) {
    const segText =
      typeof seg === "string" ? seg : seg && (seg.text || seg.segment);
    const t = typeof segText === "string" ? segText.trim() : "";
    if (t.length > 0 && out.includes(t)) {
      out = out.split(t).join(`${t} [${UNVERIFIED_MARKER}]`);
      marked += 1;
    }
  }
  if (marked === 0) {
    out =
      `> [${UNVERIFIED_MARKER}] 미검증 추론이 비활성화되었습니다(allow_unverified_inference=false). ` +
      `지원 근거가 없는 내용은 본 마커로 표기됩니다.\n\n` +
      out;
  }
  return out;
}

module.exports = {
  normalizeEvidence,
  normalizeEvidenceList,
  segmentSentences,
  computeCoverage,
  // Evidence-first 가드 프리미티브 (Task 13.6 / 13.8)
  UNVERIFIED_MARKER,
  containsUnresolvedLatest,
  markUnsupportedSegments,
  // 기본값 상수(테스트/재사용 편의)
  DEFAULT_SOURCE_TYPE,
  DEFAULT_SUPPORT_LEVEL,
  DEFAULT_CONFIDENCE,
};
