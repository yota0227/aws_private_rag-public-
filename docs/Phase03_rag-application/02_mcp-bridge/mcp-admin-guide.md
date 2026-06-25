# BOS-AI RAG MCP Bridge — Admin 운영 가이드

> **Created:** 2026-06-17
> **Updated:** 2026-06-17
> **Purpose:** MCP Bridge 운영/개발 환경 구성, 배포 절차, 트러블슈팅을 Admin이 참고하기 위한 가이드.
> **Spec / Project:** `.kiro/specs/mcp-tool-optimization/`
> **Status:** Stable
> **Owner:** Infra/DevOps

---

## 1. 환경 구성 개요

BOS-AI RAG MCP Bridge는 두 환경으로 운영된다.

| 항목 | 운영 (Production) | 개발 (Development) |
|---|---|---|
| 서버 | EC2 (`i-0274fe4da3ecd8f7f`) | server02 (192.128.20.241) |
| 위치 | AWS Seoul (ap-northeast-2) | 온프레미스 |
| 작업 디렉토리 | `/opt/mcp-server/` | `~/bos-ai-rag-mcp-bridge/` |
| 서비스명 | `mcp-server.service` | `bos-ai-rag-mcp.service` |
| 포트 | 3000 | 3100 |
| 외부 엔드포인트 | `https://mcp.bossemi-ai.com/mcp` | SSH 터널 (`localhost:3101`) |
| IAM 자격증명 | EC2 인스턴스 프로파일 (`role-mcp-server-bos-ai-seoul-prod`) | IAM 사용자 (`server02-mcp-dev`) |
| `RAG_API_BASE` | 미설정 (Lambda direct invoke 모드) | 미설정 (Lambda direct invoke 모드) |
| Node.js | v20.18.0 | v22.16.0 |

---

## 2. 아키텍처

```
[Kiro / Obot / MCP Client]
        |
        | MCP Streamable HTTP (/mcp) 또는 Legacy SSE (/sse)
        |
+-------+----------+          +------------------------+
| 운영 MCP Bridge  |          | 개발 MCP Bridge         |
| EC2 :3000        |          | server02 :3100          |
| /opt/mcp-server  |          | SSH 터널: localhost:3101 |
+-------+----------+          +------------------------+
        |                                |
        | Lambda direct invoke           | Lambda direct invoke
        | (EC2 인스턴스 프로파일)          | (IAM 사용자 키)
        |                                |
+-------+--------------------------------+
|           AWS 백엔드                    |
|  lambda-document-processor-seoul-prod  |  문서 RAG, 검색, HDD
|  lambda-rtl-parser-seoul-dev           |  RTL 검색 (search_rtl)
|  Qdrant (벡터 인덱스)                   |
|  Neptune (그래프 DB)                    |
|  DynamoDB (Claim DB)                   |
|  Bedrock (Claude + Titan Embeddings)   |
+----------------------------------------+
```

### search_rtl 경로 참고

`search_rtl`은 API Gateway를 경유하지 않고 **Lambda direct invoke**로 직접 `lambda-rtl-parser-seoul-dev`를 호출한다. API Gateway에 `/search-rtl` 경로는 등록되어 있지 않다 — Lambda 응답이 오래 걸릴 수 있어 API Gateway 29초 타임아웃 제약을 피하기 위함이다.

나머지 경로는 `RAG_API_BASE` 미설정 시 동일하게 Lambda direct invoke로 동작한다. **현재 양 환경 모두 `RAG_API_BASE` 미설정 상태다.**

---

## 3. MCP Client 설정 및 접근 정책

### 3.1 접근 정책 (중요)

**사용자에게 서비스되는 MCP는 LiteLLM이 Gateway 역할을 한다. 팀별 권한은 LiteLLM에서 부여한다.**

```
[사용자 MCP Client]
        |
        v
[LiteLLM Gateway]  ← 팀별 virtual key, 도구 노출 권한 관리
        |
        v
[bos-ai-rag MCP Bridge]  ← 운영 EC2 (https://mcp.bossemi-ai.com/mcp)
        |
        v
[AWS 백엔드]  ← Lambda, Qdrant, Neptune, Bedrock
```

- **운영 엔드포인트**: LiteLLM을 통해 제공 (팀별 virtual key 필요)
- **Admin/개발 직접 접근**: `https://mcp.bossemi-ai.com/mcp` 또는 SSH 터널 직접 연결
- LiteLLM virtual key 발급 및 팀 권한 정책은 LiteLLM 관리자(Infra/DevOps)에게 문의

---

### 3.2 MCP Client별 설정 방법

#### Kiro

`.kiro/settings/mcp.json` (workspace 레벨):

```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "url": "https://mcp.bossemi-ai.com/mcp",
      "autoApprove": ["search_rtl"]
    }
  }
}
```

개발 서버 직접 연결 (Admin/개발용):
```json
{
  "mcpServers": {
    "bos-ai-rag-dev": {
      "url": "http://localhost:3101/mcp",
      "autoApprove": ["search_rtl"]
    }
  }
}
```

> dev 연결 시 SSH 터널 필요: `ssh -N -L 3101:localhost:3100 root@server02`

---

#### VS Code — GitHub Copilot

`.vscode/mcp.json` 또는 Command Palette → **MCP: Add Server** → Streamable HTTP:

```json
{
  "mcp": {
    "servers": {
      "bos-ai-rag": {
        "type": "http",
        "url": "https://mcp.bossemi-ai.com/mcp"
      }
    }
  }
}
```

---

#### VS Code — Claude Code (Anthropic)

Command Palette → **Claude: Configure MCP Servers** 또는 `~/.config/claude-code/mcp_servers.json`:

```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "type": "streamable-http",
      "url": "https://mcp.bossemi-ai.com/mcp"
    }
  }
}
```

---

## 4. 파일 구조

```
/opt/mcp-server/          (운영)
~/bos-ai-rag-mcp-bridge/  (개발 server02)
├── server.js              # 활성 entrypoint (package.json start: node server.js)
├── lib/
│   ├── uri.js             # Resource_URI parser/validator/builder (6 schemes)
│   ├── errors.js          # Error_Schema 생성/분류 (invalid_uri/not_found/upstream_error)
│   ├── envelope.js        # 텍스트 말미 구조화 블록 (--- structured ---)
│   ├── logging.js         # CloudWatch 구조화 JSON 로깅 (request_id, tool, latency)
│   ├── metrics.js         # Rolling 5분 p50/p95/p99 latency 메트릭
│   ├── evidence.js        # get_evidence 정규화, 문장 coverage 판정
│   ├── tool-descriptions.js  # 도구별 설명/disambiguation 상수, Tool-selection 표
│   └── jobs/
│       ├── store.js       # Job 상태 저장소 (in-memory; DynamoDB 교체 가능)
│       └── dispatcher.js  # Job_Dispatcher — 비동기 job 생성/실행/상태 전이
├── package.json           # start: node server.js, test: node --test
├── node_modules/
└── tests/                 # node:test + fast-check 속성 테스트 (57개)
```

---

## 5. 등록된 MCP 도구 (21개)

### 기존 17개 (계약 불변)

| 그룹 | 도구 |
|---|---|
| 검색 | `rag_query`, `search_rtl`, `search_archive` |
| 문서 관리 | `rag_list_documents`, `rag_categories`, `rag_upload_status`, `rag_extract_status`, `rag_delete_document` |
| Evidence/Claim | `get_evidence`, `list_verified_claims` |
| HDD/출판 | `generate_hdd_section`, `publish_markdown`, `regenerate_stale_hdd` |
| 그래프 | `trace_signal_path`, `find_instantiation_tree`, `find_clock_crossings`, `graph_export` |

### 신규 4개 (mcp-tool-optimization 스펙)

| 도구 | 역할 |
|---|---|
| `rag_validate_answer` | 답변 문장별 근거 검증 (hallucination 점검) |
| `rag_index_status` | 인덱스 version/freshness/embedding model 조회 |
| `rag_read_resource` | Resource_URI로 원문/스팬 재조회 |
| `rag_task_status` | 비동기 job 상태 polling |

---

## 6. 운영 배포 절차 (EC2, 폐쇄망)

운영 EC2는 외부 인터넷 없음. **S3 경유** 방식을 사용한다.

```powershell
# 1. 로컬에서 S3에 업로드
aws s3 cp mcp-bridge/server.js s3://bos-ai-documents-seoul-v3/mcp-deploy/server.js --region ap-northeast-2
aws s3 sync mcp-bridge/lib/ s3://bos-ai-documents-seoul-v3/mcp-deploy/lib/ --region ap-northeast-2

# 2. EC2 역할에 임시 S3 읽기 권한 추가 (배포 후 반드시 제거)
# policy.json: s3:GetObject + s3:ListBucket on bos-ai-documents-seoul-v3/mcp-deploy/*
aws iam put-role-policy --role-name "role-mcp-server-bos-ai-seoul-prod" \
  --policy-name "mcp-deploy-s3-temp" \
  --policy-document file://policy.json

# 3. SSM으로 EC2에서 파일 내려받기 + 재시작
aws ssm send-command --instance-ids "i-0274fe4da3ecd8f7f" \
  --document-name "AWS-RunShellScript" \
  --parameters commands=["cd /opt/mcp-server && cp server.js server.js.bak && aws s3 cp s3://bos-ai-documents-seoul-v3/mcp-deploy/server.js . --region ap-northeast-2 && aws s3 sync s3://bos-ai-documents-seoul-v3/mcp-deploy/lib/ ./lib/ --region ap-northeast-2 && systemctl restart mcp-server"] \
  --region ap-northeast-2

# 4. 결과 확인
aws ssm list-command-invocations --command-id "<id>" --details --region ap-northeast-2

# 5. 임시 리소스 정리 (필수)
aws s3 rm s3://bos-ai-documents-seoul-v3/mcp-deploy/ --recursive --region ap-northeast-2
aws iam delete-role-policy --role-name "role-mcp-server-bos-ai-seoul-prod" --policy-name "mcp-deploy-s3-temp"
```

> ⚠️ EC2 환경에서 `npm install`은 외부 레지스트리 접근 불가. 신규 패키지 추가 시 `node_modules`째 S3에 올리거나 패키지를 개별 업로드해야 한다.

---

## 7. 개발 서버(server02) 배포 절차

```bash
# 로컬에서 실행
scp -r mcp-bridge/server.js mcp-bridge/lib/ root@server02:~/bos-ai-rag-mcp-bridge/

# server02에서 실행
cd ~/bos-ai-rag-mcp-bridge
systemctl daemon-reload
systemctl restart bos-ai-rag-mcp
systemctl status bos-ai-rag-mcp
curl http://localhost:3100/health
```

---

## 8. IAM 자격증명 관리

### 운영 EC2

인스턴스 프로파일 `profile-mcp-server-bos-ai-seoul-prod`이 자동으로 자격증명을 제공한다. 별도 설정 불필요.

### 개발 server02

IAM 사용자 `server02-mcp-dev` (`/bos-ai/`) access key를 `~/.aws/credentials`에 등록한다.

- **권한**: `lambda:InvokeFunction` on `lambda-rtl-parser-seoul-dev` only (최소 권한)
- **Terraform**: `environments/global/iam/server02-lambda-invoke.tf`
- **key 갱신 절차**:
  1. IAM 콘솔 → `server02-mcp-dev` → Security credentials → 기존 키 비활성화
  2. 신규 키 발급
  3. server02에서 `aws configure` 재등록
  4. `systemctl restart bos-ai-rag-mcp`
- **교체 주기**: 90일 권장

---

## 9. 서비스 환경변수

| 변수 | 운영 | 개발 | 설명 |
|---|---|---|---|
| `PORT` | `3000` | `3100` | 리슨 포트 |
| `RAG_API_BASE` | (미설정) | (미설정) | 설정 시 HTTP fallback, 미설정 시 Lambda direct invoke |
| `AWS_REGION` | `ap-northeast-2` | (SDK 기본값) | Lambda invoke 리전 |
| `LAMBDA_FUNCTION` | `lambda-document-processor-seoul-prod` | (기본값) | 문서 처리 Lambda |
| `RTL_LAMBDA_FUNCTION` | `lambda-rtl-parser-seoul-dev` | (기본값) | RTL 검색 Lambda |
| `NODE_ENV` | `production` | — | |

서비스 파일:
- 운영: `/etc/systemd/system/mcp-server.service`
- 개발: `/etc/systemd/system/bos-ai-rag-mcp.service`

---

## 10. 헬스체크 및 검증

```bash
# 운영 — SSM으로
aws ssm send-command --instance-ids "i-0274fe4da3ecd8f7f" \
  --document-name "AWS-RunShellScript" \
  --parameters commands=["curl -s http://localhost:3000/health"] \
  --region ap-northeast-2

# 개발 server02 — 직접
curl http://localhost:3100/health
```

정상 응답:
```json
{"status": "ok", "ragApi": "", "streamableSessions": 0, "sseSessions": 0}
```
`ragApi`가 비어있으면 Lambda direct invoke 모드 정상.

**기능 검증**: Kiro에서 `search_rtl("tt_noc_router")` 결과에 `--- structured ---` 블록 + `resource_uris`가 붙으면 신규 코드 정상 동작.

---

## 11. 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| `Server not initialized` | Kiro MCP 세션 초기화 안 됨 | Kiro MCP 패널에서 해당 서버 Reconnect |
| `fetch failed` | SSH 터널 끊김 (dev) | `ssh -N -L 3101:localhost:3100 root@server02` 재실행 |
| `Cannot find module '@aws-sdk/client-lambda'` | node_modules 누락 | `npm install @aws-sdk/client-lambda` |
| `Unable to locate credentials` | IAM 자격증명 없음 | `aws configure` 또는 인스턴스 프로파일 확인 |
| `Missing Authentication Token` (search_rtl) | `RAG_API_BASE` 설정됨 + `/search-rtl` 경로 없음 | 서비스 파일에서 `RAG_API_BASE` 주석처리 후 `daemon-reload` + `restart` |
| structured 블록 없음 | 구 버전 server.js 실행 중 | 배포 절차(6절) 재수행 |
| search_rtl 0건 | `RAG_API_BASE` 설정 상태 | 위와 동일 |

---

## 12. 관련 스펙 및 문서

| 문서 | 위치 |
|---|---|
| MCP 도구 최적화 스펙 | `.kiro/specs/mcp-tool-optimization/` |
| Multi-RAG corpus 라우팅 스펙 (보류) | `.kiro/specs/mcp-corpus-routing-acl/` |
| 엔드유저 도구 사용 가이드 | `docs/common/mcp-tool-usage-guide.md` |
| 엔드유저 프롬프트 예시 | `docs/common/mcp-user-prompt-guide.md` |
| QuickSight 도구 처분 결정 | `docs/common/mcp-quicksight-tool-disposition.md` |
| NPU/SOC MCP 개선 방향 보고서 | `docs/common/NPU_SOC_RTL_RAG_MCP_Improvement_Report.md` |
| server02 IAM Terraform | `environments/global/iam/server02-lambda-invoke.tf` |

---

## 13. 향후 개선 사항

### Multi-RAG 단계 (보류 — `mcp-corpus-routing-acl` spec)

두 번째 RAG 도메인(예: CPU/SoC) 추가 시:

1. 도메인별 MCP 서버 분리 (`bos-npu-rag-mcp`, `bos-cpu-rag-mcp`)
2. LiteLLM access group을 서버 단위로 유지 → 도메인 격리 자연스럽게 달성
3. corpus_id 표준화, 2단계 ACL, Resource URI 고도화

### 단기 개선 과제

| 항목 | 설명 | 우선순위 |
|---|---|---|
| job 상태 영속화 | 현재 in-memory → 프로세스 재시작 시 소실. DynamoDB `bos-ai-mcp-jobs` 테이블로 교체 | 중 |
| 백엔드 index_version 지원 | Lambda 응답에 `index_version`/`resolved_snapshot` 추가 시 structured 블록이 실제 값 반환 (현재 `"unknown"`) | 중 |
| `@aws-sdk/client-lambda` package.json 명시 | 현재 server02에서 별도 설치 필요. `dependencies`에 추가하면 표준 배포에 포함 | 낮음 |
