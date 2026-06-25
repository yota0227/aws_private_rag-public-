# MCP Bridge Tests

> **Created:** 2026-06-16
> **Updated:** 2026-06-16
> **Purpose:** `mcp-bridge/` 도구 계층의 `node:test` + `fast-check` 테스트 하니스와 속성 테스트 태그 컨벤션을 정의한다.
> **Spec / Project:** `.kiro/specs/mcp-tool-optimization/`
> **Status:** Draft
> **Owner:** Infra/DevOps + RAG MCP

## 실행 방법

```bash
cd mcp-bridge
npm install        # fast-check (devDependency) 설치
npm test           # = node --test  (1회 실행, watch 모드 아님)
```

- 러너: 내장 `node:test`.
- 속성 라이브러리: `fast-check` (직접 구현 금지).
- 단일 실행: watch 모드 대신 `node --test`(1회 실행)로 수행한다.

## 속성 테스트 태그 컨벤션

각 속성 테스트는 대응하는 design.md의 Correctness Property를 **파일/테스트 상단 주석**으로 참조한다. 형식은 다음과 같다:

```js
// Feature: mcp-tool-optimization, Property N: <property title>
// Validates: Requirements X.Y, Z.W
```

예시:

```js
// Feature: mcp-tool-optimization, Property 4: Resource_URI 라운드트립
// Validates: Requirements 8.4, 5.5
```

## 규칙

- 각 속성 테스트는 **최소 100회 반복**(`{ numRuns: 100 }` 이상)으로 실행한다.
- 테스트 파일은 `*.test.js`로 명명하고 `mcp-bridge/tests/` 아래에 둔다.
- 순수 로직(`lib/` 모듈)을 대상으로 하며, Lambda·DynamoDB 호출은 주입(injection)으로 mock 한다(폐쇄망·비용 회피).
- 인프라(Go/gopter, `tests/`)와 Lambda(Python, `rtl_parser_src/`) 테스트는 본 spec 범위 밖이며 변경하지 않는다.

## 현재 파일

- `harness.test.js` — 러너와 fast-check 동작을 확인하는 최소 smoke 테스트(프로덕션 코드 미참조).
