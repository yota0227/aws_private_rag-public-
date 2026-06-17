# MCP 브리지 QuickSight 도구 처분 결정

> **Created:** 2026-06-16
> **Updated:** 2026-06-16
> **Purpose:** MCP 브리지에서 QuickSight 도구(`quick_dashboard_list`/`quick_dashboard_data`)와 stale `server.mjs`를 제거한 결정·근거·복원 방법을 기록(spec `mcp-tool-optimization` Task 18.1/18.2 산출물).
> **Spec / Project:** `.kiro/specs/mcp-tool-optimization/`
> **Status:** Stable
> **Owner:** Infra/DevOps + RAG MCP

## 결정 (Decision)

MCP 브리지에서 QuickSight 도구 **`quick_dashboard_list`, `quick_dashboard_data`를 제거**한다. 함께, 이 도구들만 정의하던 stale 변형 파일 **`mcp-bridge/server.mjs`를 삭제**하고, 그 파일에서만 쓰이던 **`@aws-sdk/client-quicksight` 의존성을 `package.json`에서 제거**한다.

활성 entrypoint인 `mcp-bridge/server.js`(21개 도구)는 변경하지 않는다 — QuickSight 도구는 애초에 `server.js`에 존재한 적이 없으므로 제거로 인한 도구 계약 변화는 없다.

## 근거 (Rationale)

1. **활성 entrypoint에 없었음** — `package.json`의 `start`(`node server.js`)와 systemd 유닛(`bos-ai-rag-mcp.service`의 `ExecStart ... node server.js`)이 모두 `server.js`를 가리킨다. QuickSight 도구는 stale `server.mjs`에만 정의되어 있었고, 운영 중 활성 브리지(`server.js`)는 이 도구를 노출한 적이 없다.
2. **stale drift** — `server.mjs`는 구버전 SDK import 경로(`@modelcontextprotocol/sdk/dist/cjs/...`)를 사용하는 오래된 변형으로, 단일 진실 원천(single source of truth) 원칙에 어긋난다. QuickSight 두 도구 외에 `server.js`가 갖지 못한 고유 기능은 없다.
3. **스코프 분리** — QuickSight 통합은 별도 spec **`9_quicksight-private-integration`** 소관이다. 도구 계층 최적화(`mcp-tool-optimization`) 범위에 QuickSight를 남기면 두 spec의 책임이 흐려진다.
4. **의존성 정리** — `@aws-sdk/client-quicksight`는 `server.mjs`에서만 참조되었으므로 server.mjs 삭제 후 미사용 의존성으로 남는다. 함께 제거하여 설치 표면을 줄인다.

## 제거 대상 (What Was Removed)

| 항목 | 위치 | 비고 |
|------|------|------|
| `server.mjs` | `mcp-bridge/server.mjs` | stale drift 변형. QuickSight 도구 2개를 정의한 유일한 파일 |
| `quick_dashboard_list` 도구 | (server.mjs 내) | `ListDashboards` 호출 |
| `quick_dashboard_data` 도구 | (server.mjs 내) | `DescribeDashboard` 호출 |
| `@aws-sdk/client-quicksight` | `mcp-bridge/package.json` `dependencies` | server.mjs 전용 의존성 |

### 변경하지 않은 항목

- `mcp-bridge/server.js` — 활성 entrypoint, 21개 도구 그대로 유지.
- `package.json`의 `@modelcontextprotocol/sdk`, `express`, `start`(→ `server.js`), `test`(`node --test`) 스크립트, `fast-check` devDependency.
- 인프라 레벨 QuickSight 리소스(`environments/network-layer/quicksight-*.tf`, `policies/quicksight-security.rego`)와 spec `9_quicksight-private-integration` — 본 결정의 범위 밖.
- 참고: `mcp-bridge/docker-compose.yml`의 `QS_REGION`/`QS_ACCOUNT_ID` 환경변수는 과거 server.mjs QuickSight 도구용 잔재이며 현재 동작에 영향을 주지 않는다(본 작업 범위 밖, 추후 정리 후보).

## 복원 방법 (How to Restore)

이 변경은 git으로 되돌릴 수 있다. 향후 **QuickSight-over-MCP**가 필요하면 다음을 고려한다.

1. `server.mjs`와 도구 정의 복원이 필요하면 git 이력에서 복구:
   ```bash
   # 삭제 직전 커밋 확인
   git log --oneline -- mcp-bridge/server.mjs
   # 해당 파일 복원 (<commit>은 삭제 직전 커밋 해시)
   git checkout <commit> -- mcp-bridge/server.mjs
   ```
2. 의존성 복원:
   ```bash
   # package.json dependencies에 다시 추가하거나
   npm install @aws-sdk/client-quicksight@^3.0.0
   ```
3. **권장 경로:** stale `server.mjs`를 되살리는 대신, QuickSight 도구를 활성 entrypoint `server.js`에 (현재 SDK import 규약·`withTool` 래퍼·envelope 패턴에 맞춰) 신규 추가하고, 그 작업은 소유 spec **`9_quicksight-private-integration`** 에서 진행한다.

## 추적성 (Traceability)

- **무엇을:** `server.mjs` 삭제, `package.json`에서 `@aws-sdk/client-quicksight` 제거, 본 결정 문서 작성.
- **왜:** stale drift 해소 + 단일 entrypoint 확정 + 스코프 분리(QuickSight는 spec 9 소관).
- **어떻게 검증:** `server.mjs` 부재 확인, `node --check server.js` (exit 0), `node --test` 전체 통과, `package.json`에 quicksight 의존성 부재 + 나머지 deps/scripts 유지 확인.
- **롤백:** 위 "복원 방법" — git revert/checkout.

## 관련 Requirements

`mcp-tool-optimization` Requirement 7.1~7.8 (단일 진실 원천 통합 / QuickSight 처분 결정·문서화 / 의존성 정리 / 기존 도구 계약 보존).
