/**
 * tests/tool-descriptions.unit.test.js
 *
 * Spec: .kiro/specs/mcp-tool-optimization/ (Task 10.1)
 *
 * lib/tool-descriptions.js의 상수 모듈에 대한 최소 sanity 단위 테스트.
 * (Property 1/2/3 본격 검증은 Task 10.3/10.4/10.5에서 server.js 재배선 후 수행)
 *
 * 검증:
 *  - 21개 도구명(기존 17 + 신규 4) 각각에 비어있지 않은 description 존재
 *  - rag_query / search_rtl / search_archive 설명이 서로를 정확한 등록명으로 상호 참조
 *  - SELECTION_GUIDANCE가 유효한 등록명만 매핑
 */

const { test } = require("node:test");
const assert = require("node:assert");

const {
  EXISTING_TOOL_NAMES,
  NEW_TOOL_NAMES,
  ALL_TOOL_NAMES,
  TOOL_DESCRIPTIONS,
  SELECTION_GUIDANCE,
} = require("../lib/tool-descriptions");

test("정확히 21개 도구명(기존 17 + 신규 4)이 정의된다", () => {
  assert.strictEqual(EXISTING_TOOL_NAMES.length, 17);
  assert.strictEqual(NEW_TOOL_NAMES.length, 4);
  assert.strictEqual(ALL_TOOL_NAMES.length, 21);
  // 중복 없음
  assert.strictEqual(new Set(ALL_TOOL_NAMES).size, 21);
});

test("모든 도구명에 비어있지 않은 description이 존재한다", () => {
  for (const name of ALL_TOOL_NAMES) {
    const desc = TOOL_DESCRIPTIONS[name];
    assert.ok(typeof desc === "string", `${name} description은 문자열이어야 함`);
    assert.ok(desc.trim().length > 0, `${name} description은 비어있지 않아야 함`);
  }
});

test("TOOL_DESCRIPTIONS에 정의된 키가 ALL_TOOL_NAMES와 정확히 일치한다", () => {
  const descKeys = Object.keys(TOOL_DESCRIPTIONS).sort();
  const names = ALL_TOOL_NAMES.slice().sort();
  assert.deepStrictEqual(descKeys, names);
});

test("rag_query / search_rtl / search_archive 설명이 서로를 정확한 등록명으로 상호 참조한다", () => {
  const trio = ["rag_query", "search_rtl", "search_archive"];
  for (const self of trio) {
    const desc = TOOL_DESCRIPTIONS[self];
    for (const other of trio) {
      if (other === self) continue;
      assert.ok(
        desc.includes(other),
        `${self} 설명은 형제 도구 ${other}를 정확한 등록명으로 언급해야 함`
      );
    }
  }
});

test("각 설명은 목적·예시 마커를 포함한다", () => {
  for (const name of ALL_TOOL_NAMES) {
    const desc = TOOL_DESCRIPTIONS[name];
    assert.ok(desc.includes("[목적]"), `${name} 설명에 [목적] 포함`);
    assert.ok(desc.includes("[예시]"), `${name} 설명에 [예시] 포함`);
  }
});

test("SELECTION_GUIDANCE는 유효한 등록명만 매핑한다", () => {
  const valid = new Set(ALL_TOOL_NAMES);
  assert.ok(SELECTION_GUIDANCE.length > 0);
  for (const row of SELECTION_GUIDANCE) {
    assert.ok(typeof row.questionType === "string" && row.questionType.length > 0);
    assert.ok(valid.has(row.recommendedTool), `권장 도구 ${row.recommendedTool}는 등록명이어야 함`);
    assert.ok(Array.isArray(row.avoid));
    for (const a of row.avoid) {
      assert.ok(valid.has(a.tool), `회피 도구 ${a.tool}는 등록명이어야 함`);
      assert.ok(typeof a.reason === "string" && a.reason.length > 0);
    }
  }
});
