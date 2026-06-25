// Property/unit tests for evidence-first 검증 로직 (Task 13.4/13.5/13.7/13.9)
//
// Spec: .kiro/specs/mcp-tool-optimization/
// Runner: node:test ; Property library: fast-check (numRuns >= 100).
//
// 대상: lib/evidence.js의 순수 로직.
//   - Property 15/16: computeCoverage + segmentSentences (rag_validate_answer 13.3의 핵심).
//   - Property 17/18: 가드 프리미티브 markUnsupportedSegments / containsUnresolvedLatest
//     (generate_hdd_section 13.6 / publish_markdown 13.8의 결정적 부분).
//
// 주의: rag_validate_answer / publish_markdown / generate_hdd_section의 완전한
// end-to-end 동작은 server.js 핸들러 + 백엔드(ragApi)에 의존하므로 본 단위 테스트는
// 백엔드 없이 검증 가능한 순수 로직에 한정한다(full e2e는 backend-dependent).

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fc = require("fast-check");

const {
  segmentSentences,
  computeCoverage,
  markUnsupportedSegments,
  containsUnresolvedLatest,
  UNVERIFIED_MARKER,
} = require("../lib/evidence");

const NUM_RUNS = 100;

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 15: 답변 검증 coverage
// Validates: Requirements 3.3, 3.4, 3.5
//
// 각 문장은 supported/unsupported로 라벨되고, evidence 0인 문장은 unsupported이며,
// 모든 unsupported 문장은 text와 position(index)과 함께 목록으로 반환된다.
// ---------------------------------------------------------------------------
test("Property 15: computeCoverage는 문장별 라벨 + 미지원 목록(text+position)을 정확히 산출한다", () => {
  fc.assert(
    fc.property(
      // (문장 텍스트, evidence 개수) 쌍 — 0개 개수가 unsupported를 만든다.
      fc.array(fc.tuple(fc.string({ minLength: 1 }), fc.nat(5)), {
        maxLength: 12,
      }),
      (pairs) => {
        const sentences = pairs.map((p) => p[0]);
        const counts = pairs.map((p) => p[1]);
        const lookup = (sentence, index) => counts[index];

        const cov = computeCoverage(sentences, lookup);

        // 모든 문장이 라벨된다(개수 보존).
        assert.equal(cov.total, sentences.length);
        assert.equal(cov.sentences.length, sentences.length);

        cov.sentences.forEach((s, i) => {
          assert.equal(s.index, i);
          assert.equal(s.text, sentences[i]);
          assert.equal(s.evidence_count, counts[i]);
          // evidence 0 ⇒ unsupported (Req 3.4).
          assert.equal(s.supported, counts[i] > 0);
        });

        // 미지원 목록 = 개수 0인 문장들, text+position 포함 (Req 3.5).
        const expected = sentences
          .map((t, i) => ({ t, i }))
          .filter((_, i) => counts[i] === 0);
        assert.equal(cov.unsupported_count, expected.length);
        assert.equal(cov.unsupported.length, expected.length);
        assert.equal(cov.supported_count, sentences.length - expected.length);

        cov.unsupported.forEach((u) => {
          assert.equal(typeof u.index, "number");
          assert.equal(typeof u.text, "string");
          assert.equal(counts[u.index], 0);
          assert.equal(u.text, sentences[u.index]);
        });
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test("Property 15: lookup 부재(모두 0)면 모든 문장이 unsupported (publish 가드 fallback 의미)", () => {
  fc.assert(
    fc.property(
      fc.array(fc.string({ minLength: 1 }), { minLength: 1, maxLength: 8 }),
      (sentences) => {
        const cov = computeCoverage(sentences, () => 0);
        assert.equal(cov.unsupported_count, cov.total);
        assert.equal(cov.supported_count, 0);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 16: 빈/공백 답변 거부
// Validates: Requirements 3.6
//
// rag_validate_answer는 빈/공백 answer를 Error_Schema로 거부한다(server 핸들러).
// 그 거부 결정의 토대가 되는 순수 로직 = segmentSentences가 빈/공백 입력에 대해
// 문장을 0개 산출한다는 점을 검증한다(핸들러는 answer.trim().length===0으로 거부).
// ---------------------------------------------------------------------------
test("Property 16: 전부 공백/빈 answer는 문장이 0개로 분할된다 (거부 토대)", () => {
  const whitespace = fc.stringOf(
    fc.constantFrom(" ", "\t", "\n", "\r", "\f", "\v"),
    { maxLength: 30 }
  );
  fc.assert(
    fc.property(whitespace, (s) => {
      // 빈 문자열 및 공백뿐인 문자열 → 의미 있는 문장 0개.
      assert.deepEqual(segmentSentences(s), []);
      const cov = computeCoverage(segmentSentences(s), () => 1);
      assert.equal(cov.total, 0);
      assert.equal(cov.unsupported_count, 0);
      assert.equal(cov.supported_count, 0);
    }),
    { numRuns: NUM_RUNS }
  );
  // 명시적 빈 문자열도 동일.
  assert.deepEqual(segmentSentences(""), []);
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 17: verified-only HDD 표기
// Validates: Requirements 3.7
//
// allow_unverified_inference=false일 때 지원 근거 0 세그먼트는 "확실하지 않음"으로
// 표기된다. 핸들러는 evidence.markUnsupportedSegments를 사용한다(여기서 검증).
// 완전한 HDD 생성 e2e는 백엔드(ragApi /generate-hdd) 의존이므로 제외한다.
// ---------------------------------------------------------------------------
test('Property 17: 마커 리터럴은 정확히 "확실하지 않음"이다', () => {
  assert.equal(UNVERIFIED_MARKER, "확실하지 않음");
});

test('Property 17: 미지원 세그먼트가 markdown에 있으면 그 뒤에 "확실하지 않음" 마커가 부착된다', () => {
  fc.assert(
    fc.property(
      // 마커/대괄호와 충돌하지 않는 단순 세그먼트 텍스트.
      fc.array(
        fc
          .stringOf(
            fc.constantFrom(
              ..."abcdefghijklmnopqrstuvwxyzABCDEFGHIJ0123456789가나다라마바 "
            ),
            { minLength: 3, maxLength: 20 }
          )
          .filter((s) => s.trim().length >= 3 && !s.includes("[")),
        { minLength: 1, maxLength: 4 }
      ),
      (segments) => {
        // 세그먼트들을 포함하는 markdown 구성(인덱스 prefix로 고유 키 보장).
        const md = segments.map((s, i) => `섹션${i}: ${s}.`).join("\n");
        const unsupported = segments.map((s, i) => ({ text: `섹션${i}: ${s}.` }));
        const out = markUnsupportedSegments(md, unsupported);
        // 마커가 최소 1회 존재.
        assert.ok(out.includes(UNVERIFIED_MARKER), "marker must be present");
        // 각 표기 대상 뒤에 마커가 부착됨.
        unsupported.forEach((u) => {
          assert.ok(out.includes(`${u.text} [${UNVERIFIED_MARKER}]`));
        });
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test("Property 17: 표기할 세그먼트를 특정 못해도 보수적 공지로 마커가 보장된다", () => {
  fc.assert(
    fc.property(fc.string(), (md) => {
      const out = markUnsupportedSegments(md, []);
      assert.ok(out.includes(UNVERIFIED_MARKER));
    }),
    { numRuns: NUM_RUNS }
  );
});

// ---------------------------------------------------------------------------
// Feature: mcp-tool-optimization, Property 18: publish 가드 (latest 검출 부분)
// Validates: Requirements 3.8, 3.9
//
// publish_markdown 가드의 결정적 부분 = 미해석 "latest" 토큰 검출
// (containsUnresolvedLatest). 미지원 문장 검출 부분은 Property 15(computeCoverage)에서
// 검증된다. 발행 거부 + 비저장의 full e2e는 server 핸들러 + 백엔드 의존이므로 제외한다.
// ---------------------------------------------------------------------------
test("Property 18: 단어 'latest'를 포함하면 미해석 참조로 검출된다", () => {
  // 결정적 예시.
  assert.equal(containsUnresolvedLatest("uses the latest snapshot"), true);
  assert.equal(containsUnresolvedLatest("LATEST"), true);
  assert.equal(containsUnresolvedLatest("snap_20260615_0930"), false);
  assert.equal(containsUnresolvedLatest("translatest"), false); // 단어 경계
  assert.equal(containsUnresolvedLatest("latestable"), false);
  assert.equal(containsUnresolvedLatest(""), false);
  assert.equal(containsUnresolvedLatest(undefined), false);

  // 속성: 토큰 경계로 둘러싼 "latest"는 항상 검출된다.
  fc.assert(
    fc.property(fc.string(), fc.string(), (a, b) => {
      const text = a + " latest " + b;
      assert.equal(containsUnresolvedLatest(text), true);
    }),
    { numRuns: NUM_RUNS }
  );
});
