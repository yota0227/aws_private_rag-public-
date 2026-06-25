# BOS-AI Tool Guide RAG — MCP Bridge (port 3101)

> **Created:** 2026-06-17
> **Updated:** 2026-06-17
> **Purpose:** EDA Tool Guide(Document RAG)를 NPU/RTL RAG(:3100)와 권한 분리된 독립 MCP 서비스(:3101)로 노출하는 브리지의 배포/운영 절차.
> **Spec / Project:** `.kiro/specs/eda-tool-guide-rag/` + 운영 BOS-AI Private RAG
> **Status:** Draft
> **Owner:** Infra/DevOps

NPU/RTL RAG MCP(:3100)와 **완전히 분리된** 독립 MCP 서비스다. 권한 분리(`pipeline=tool-guide`)를 위해 별도 포트/프로세스/도구 집합으로 운영한다.

## 아키텍처

```
Kiro/Obot --Streamable HTTP /mcp--> Tool Guide MCP Bridge (:3101)
                                       | Lambda invoke {action:"search"}
                                       v
                       lambda-tool-guide-parser-seoul-dev
                       (query 임베딩 -> Qdrant tool-guide-knowledge-base 검색)
```

RTL MCP(:3100)는 API Gateway → document-processor Lambda를 호출하지만, Tool Guide
브리지는 **Lambda(`lambda-tool-guide-parser-seoul-dev`)를 직접 invoke**한다.
따라서 브리지를 띄우는 호스트는 해당 Lambda에 대한 `lambda:InvokeFunction` 권한이
필요하다 (EC2 instance profile 또는 IAM 자격 증명).

## 노출 MCP 도구

RTL MCP와 이름이 겹치지 않도록 `tool_guide_` 접두사를 사용한다 (R5.2 권한 분리).

| 도구 | 용도 | query 한도 |
|------|------|-----------|
| `tool_guide_search` | 명령어/옵션/심볼 검색 | 256자 |
| `tool_guide_query` | 자연어 질의(근거 인용 포함) | 8192자 |

공통 선택 파라미터: `tool_name`, `tool_version`, `max_results`(기본 20, 상한 20).

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PORT` | 3101 | 브리지 포트 (RTL=3100과 분리) |
| `AWS_REGION` | ap-northeast-2 | Lambda 리전 (Seoul) |
| `TOOL_GUIDE_LAMBDA` | lambda-tool-guide-parser-seoul-dev | 검색 백엔드 Lambda 이름 |

## 1단계: 개발 환경(server02) 배포 및 테스트

> server02(192.128.20.241)는 테스트 MCP 호스트다. 운영 배포 전 여기서 먼저 검증한다.

```bash
# 1. 코드 복사 (로컬 -> server02)
scp -r mcp-bridge-toolguide/ user@server02:/root/bos-ai-toolguide-mcp-bridge/

# 2. 의존성 설치
cd /root/bos-ai-toolguide-mcp-bridge
npm install

# 3. AWS 자격 증명 확인 (Lambda invoke 권한 필요)
#    - EC2 instance profile 또는 ~/.aws/credentials
aws sts get-caller-identity

# 4. 단독 실행 (포그라운드 테스트)
PORT=3101 AWS_REGION=ap-northeast-2 \
  TOOL_GUIDE_LAMBDA=lambda-tool-guide-parser-seoul-dev \
  node server.js

# 5. 헬스체크
curl http://localhost:3101/health
```

헬스 응답 예시:

```json
{
  "status": "ok",
  "service": "tool-guide-mcp",
  "lambda": "lambda-tool-guide-parser-seoul-dev",
  "streamableSessions": 0,
  "sseSessions": 0
}
```

검색 동작 테스트(MCP 세션 없이 Lambda 백엔드만 확인하려면 AWS CLI 사용):

```bash
aws lambda invoke --function-name lambda-tool-guide-parser-seoul-dev \
  --payload '{"action":"search","query":"elaborate command options","max_results":5}' \
  --cli-binary-format raw-in-base64-out /tmp/out.json
cat /tmp/out.json
```

## 2단계: systemd 서비스 등록 (상시 구동)

```bash
# 서비스 파일 배치
cp bos-ai-toolguide-mcp.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable bos-ai-toolguide-mcp
systemctl start bos-ai-toolguide-mcp
systemctl status bos-ai-toolguide-mcp

# 로그
journalctl -u bos-ai-toolguide-mcp -f
```

## 3단계: 운영 EC2 배포

운영 MCP 호스트(`i-0274fe4da3ecd8f7f`)에 동일 절차로 배포한다. RTL MCP(:3100)와
**포트/프로세스가 분리**되어 있으므로 기존 서비스에 영향이 없다.

- 운영 EC2 instance profile에 `lambda:InvokeFunction`
  (`lambda-tool-guide-parser-seoul-dev`) 권한을 부여한다.
- 리버스 프록시(nginx)를 쓰는 경우 `/toolguide/mcp` → `localhost:3101/mcp`
  형태로 별도 경로를 추가한다 (RTL은 기존 경로 유지).

## Kiro 연결 (SSH 터널)

Kiro는 HTTPS 또는 localhost만 허용하므로 SSH 터널로 포트를 포워딩한다.

```bash
# localhost:3101 -> 운영MCP:3101
ssh -L 3101:localhost:3101 user@<운영MCP호스트>
```

`.kiro/settings/mcp.json` 예시 (RTL :3100과 별도 항목):

```json
{
  "mcpServers": {
    "bos-ai-rag": {
      "url": "http://localhost:3100/mcp"
    },
    "bos-ai-tool-guide": {
      "url": "http://localhost:3101/mcp"
    }
  }
}
```

## 트러블슈팅

| 증상 | 원인/확인 |
|------|-----------|
| `Lambda 오류: AccessDenied` | 호스트 IAM에 `lambda:InvokeFunction` 권한 없음 |
| `검색 결과가 없습니다` | Qdrant `tool-guide-knowledge-base` 적재 여부, `tool_name` 필터 과도 |
| 포트 충돌 | :3101이 이미 사용 중인지 확인 (`ss -tlnp | grep 3101`) |
| Kiro 연결 실패 | SSH 터널 활성 여부, `curl http://localhost:3101/health` |

## 권한 분리 원칙 (요약)

- RTL/NPU RAG: `:3100`, 도구 `search_rtl`/`rag_query` 등, document-processor Lambda
- Tool Guide RAG: `:3101`, 도구 `tool_guide_search`/`tool_guide_query`, tool-guide-parser Lambda
- 두 서비스는 프로세스·포트·Lambda·Qdrant 컬렉션이 분리되어 상호 간섭이 없다.
