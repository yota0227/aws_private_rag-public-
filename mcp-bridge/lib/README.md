# MCP Bridge lib/

> **Created:** 2026-06-16
> **Updated:** 2026-06-16
> **Purpose:** `server.js`의 횡단 관심사(Resource_URI·envelope·error·logging·metrics·jobs 등)를 테스트 가능한 순수 모듈로 추출하는 디렉토리. 본 디렉토리의 모듈은 이후 태스크에서 추가된다.
> **Spec / Project:** `.kiro/specs/mcp-tool-optimization/`
> **Status:** Draft
> **Owner:** Infra/DevOps + RAG MCP

## 개요

`server.js`는 얇은 wiring 계층으로 남기고, 도구 핸들러가 공유하는 횡단 관심사는 이 디렉토리의 CommonJS 모듈로 추출한다. design.md의 진화 전략에 따라 다음 모듈이 순차적으로 추가될 예정이다:

- `uri.js` — Resource_URI parse/build/validate (6 schemes, round-trip)
- `errors.js` — Error_Schema 생성·분류 (invalid_uri / not_found / upstream_error)
- `envelope.js` — 텍스트 말미 구조화 요약 블록 append (index_version / resolved_snapshot / resource_uris)
- `logging.js` — 구조화 JSON 로깅 (request_id / tool / latency_ms / outcome / timestamp)
- `metrics.js` — rolling 5분 윈도우 latency 수집, p50/p95/p99
- `tool-descriptions.js` — 도구 설명·disambiguation 상수
- `evidence.js` — get_evidence 정규화, 문장 분할, coverage 판정
- `jobs/dispatcher.js`, `jobs/store.js` — 비동기 Job 프레임워크

## 규칙

- 언어/런타임: Node.js(CommonJS, `server.js`와 동일).
- 모든 모듈은 순수 로직 중심으로 작성하여 `mcp-bridge/tests/`에서 `node:test` + `fast-check`로 검증 가능하게 한다.
- Lambda·DynamoDB 등 외부 호출은 주입(injection)으로 추상화한다.
