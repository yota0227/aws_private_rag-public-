# LiteLLM On-Prem PoC 결과 및 운영 구축 계획

> **Created:** 2026-06-02
> **Updated:** 2026-06-04
> **Purpose:** server01 LiteLLM PoC 결과 + 운영 서버 비파괴 배포 절차 + 운영 계획을 한 문서로 종합. 실제 운영 서버(swgr1sv1)에 안전하게 배포하기 위한 의존성 검증 중심 가이드.
> **Spec / Project:** `.kiro/specs/llm-gateway/`
> **Status:** In Review
> **Owner:** Infra/DevOps

> 환경: server01 / swgr1sv1 (192.128.20.240) / bos-login 서버 (Apptainer + Codex CLI)
> PoC 기간: 2026-05-27 ~ 2026-06-02

---

## Part 1. PoC 결과 요약

### 1.1 검증 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│  bos-login 서버 (사용자 접속)                                  │
│  ┌──────────────────────┐                                    │
│  │ Apptainer (codex.sif)│                                    │
│  │  - Codex CLI v0.112.0│──────┐                             │
│  │  - ~/.codex/auth.json│      │                             │
│  └──────────────────────┘      │                             │
└────────────────────────────────┼─────────────────────────────┘
                                 │ HTTP :4000
┌────────────────────────────────▼─────────────────────────────┐
│  server01 (192.128.20.240)                                    │
│  ┌─────────────────┐  ┌──────────────┐                       │
│  │ LiteLLM Proxy   │──│ PostgreSQL   │                       │
│  │ (Docker)        │  │ (Docker)     │                       │
│  └────────┬────────┘  └──────────────┘                       │
└───────────┼──────────────────────────────────────────────────┘
            │ HTTPS :443
    ┌───────┴──────────────┐
    │                      │
┌───▼───┐           ┌─────▼──────┐
│OpenAI │           │ AWS Bedrock│
│  API  │           │ (Claude)   │
└───────┘           └────────────┘
```

추가 클라이언트:
- **Claude Code VSCode** → LiteLLM (Anthropic Messages API `/v1/messages`)
- **Kiro** → MCP 서버 (SSH 터널 경유)

> **MCP 경로 (06-03/06-04 추가):** Codex CLI → LiteLLM Gateway(`:4000/mcp`, Bearer) 또는 직접(`https://mcp.bossemi-ai.com/mcp`) → Nginx(10.10.1.62, Let's Encrypt) → MCP Node.js(10.10.1.10:3000). 위 다이어그램은 PoC 초기의 LLM 경로만 표현한 것으로, MCP는 별도 경로다 (1.4 참조).

### 1.2 검증 항목별 결과

> 아래 표는 **현재(2026-06-04) 최종 상태**를 반영한다. PoC 초기(05-27~06-02) 시점에는 #7 조건부·#8 실패였으나, 06-03 공인 인증서 적용 + 06-04 Codex 통합으로 모두 해결됨(상세는 1.5 변경 이력).

| # | 검증 항목 | 결과 | 비고 |
|---|---|---|---|
| 1 | Codex CLI ↔ LiteLLM 연동 | ✅ 성공 | `config.toml`에 `model_provider` + `base_url` + `wire_api="responses"` 명시 (env 방식 대체) |
| 2 | OpenAI 모델 라우팅 (6개) | ✅ 성공 | gpt-5.1-codex-mini ~ gpt-5.4 |
| 3 | Bedrock Claude 모델 라우팅 (6개) | ✅ 성공 | Bearer token + cross-region profile |
| 4 | Claude Code VSCode ↔ LiteLLM | ✅ 성공 | `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` |
| 5 | 예산/사용량 추적 | ✅ 성공 | 팀/유저/키 레벨 모두 동작 |
| 6 | UI 대시보드 | ✅ 성공 | 비용, 토큰, 요청 수 실시간 확인 |
| 7 | LiteLLM MCP Gateway | ✅ 성공 | 공인 cert 적용으로 entrypoint SSL 패치 불필요. Network Access=Public + access group으로 팀 통제 |
| 8 | Codex CLI ↔ MCP 연결 | ✅ 성공 | 공인 도메인 `mcp.bossemi-ai.com`(Let's Encrypt)으로 해결. LiteLLM Gateway 경유 17개 도구 정상 |

### 1.3 발견된 제약사항

#### Codex CLI 연결 설정 (해결됨)
- `config.toml`의 `openai_base_url`(단독)은 Codex CLI가 무시함 → **`model_provider` + `[model_providers.litellm]` 블록**으로 명시해야 함
- v0.112는 `wire_api = "chat"` 폐기 → **`wire_api = "responses"`** 필수
- `model_provider` 누락 시 codex가 기본 OpenAI(api.openai.com)로 직행 → 사내망 SSE 끊김(`stream disconnected`)이 발생했었음 (이게 초기 "프롬프트 안 먹힘"의 진짜 원인)
- Apptainer 공유 배포 시: wrapper의 `APPTAINERENV_OPENAI_BASE_URL`로 주입하는 방식도 가능 (`APPTAINERENV_` prefix 필수)

#### Codex CLI 자동 모델 마이그레이션
- v0.112.0이 `gpt-5.1-codex-mini` → `gpt-5.4` 강제 변환
- `config.toml`에 `[notice.model_migrations]` 자동 추가됨
- 해결: LiteLLM에 CLI가 사용하는 모든 모델명 등록

#### SSL 인증서 (MCP 연동) — 해결됨 (2026-06-03)
- (초기 문제) MCP 서버 `mcp.corp.bos-semi.com`가 self-signed, CN 불일치 → Codex(Rust reqwest + webpki-roots)가 거부. `SSL_CERT_FILE`/`REQWEST_DANGER_ACCEPT_INVALID_CERTS` 모두 무시됨
- (해결) **공인 도메인 `bossemi-ai.com` 등록(Route53) → Let's Encrypt DNS-01 발급 → Nginx(10.10.1.62)에 `mcp.bossemi-ai.com` cert 적용.** Codex가 trust-store 변경 없이 연결 성공
- 결과: **LiteLLM의 entrypoint `ssl_config=False` 패치는 더 이상 불필요** (공인 cert라 정상 검증됨). 운영 배포 시 entrypoint 패치 제거 가능

#### Apptainer 환경
- 환경변수 전달: `APPTAINERENV_` prefix 필수
- Home 디렉토리: wrapper에서 `--home "$POLICY_HOME"` 으로 bind mount
- `~/.codex/` 디렉토리가 컨테이너 안에 그대로 보임 → `auth.json` 개인별 분리 가능

### 1.4 MCP 연동 현황 (2026-06-04 기준)

| 경로 | 상태 | 조건 |
|---|---|---|
| LiteLLM → MCP 서버 | ✅ 동작 | 공인 cert(`mcp.bossemi-ai.com`). Network Access=Public + access group |
| Kiro → MCP 서버 | ✅ 동작 | SSH 터널(`localhost:3100`) 경유 |
| Codex CLI → MCP (직접) | ✅ 동작 | `https://mcp.bossemi-ai.com/mcp` 공인 cert, 17개 도구 |
| Codex CLI → MCP (LiteLLM Gateway) | ✅ 동작 | `http://192.128.20.240:4000/mcp` + `Authorization: Bearer <virtual key>`. 팀별 통제 + 실제 MCP URL 은닉 |
| Claude Code VSCode → MCP 서버 | ❌ 미지원 | `.mcp.json` 인식 안 됨 (SSH 환경) |

**권장 운영 방식:** Codex CLI는 **LiteLLM Gateway 경유**(`:4000/mcp`)로 MCP를 사용 → virtual key 하나로 LLM 예산 + MCP 도구 권한을 팀별 통제하고, 실제 MCP 엔드포인트(`mcp.bossemi-ai.com`)는 유저에게 노출하지 않음.

### 1.5 변경 이력 (PoC → 운영)

| 날짜 | 변경 |
|------|------|
| 05-27~06-02 | PoC: LiteLLM(server01) + OpenAI/Bedrock 라우팅, 예산/UI 검증. MCP는 self-signed라 Codex 직접연결 실패(#8), LiteLLM은 SSL 패치로 우회(#7) |
| 06-02 | LiteLLM On-Prem(server01) 확정, AWS LiteLLM EC2 미사용 |
| 06-03 | 공인 도메인 `bossemi-ai.com` 등록 + Let's Encrypt(DNS-01) + Nginx 적용 → MCP 공인 cert화 |
| 06-04 | Codex CLI 통합 완료: LLM(`model_provider`+`wire_api=responses`) + MCP(LiteLLM Gateway + Bearer) 모두 LiteLLM 경유. #7/#8 해결 |

---

## Part 2. 구축 가이드 (운영 서버 비파괴 배포)

> **운영 서버 원칙:** 이 서버(swgr1sv1)는 이미 다른 서비스가 돌고 있을 수 있는 운영 환경이다.
> **기존 패키지/버전을 제거·교체하지 않는다.** 모든 단계는 "있으면 재사용, 없을 때만 추가"를 따른다.
> 확인된 환경: **Docker 27.4.1** 설치됨 (Compose v2 플러그인 포함) → Docker 설치 단계 불필요.

### 2.0 Step-by-Step 설치

#### 사전 요구사항
- Linux 서버 (Ubuntu 계열 가정, 다른 배포판도 Docker만 있으면 됨)
- sudo 권한
- 인터넷 접속 (Docker 이미지 pull, OpenAI/Bedrock API 호출)
- **Docker Engine + Compose v2** (이미 설치돼 있으면 그대로 사용)

#### Step 0. 사전 의존성 검증 (읽기 전용 — 아무것도 바꾸지 않음)

배포 전 반드시 실행. 하나라도 빨간불이면 멈추고 점검한다.

```bash
echo "=== [0-1] Docker / Compose 버전 ==="
docker --version || { echo "Docker 없음 → Step 1 진행"; }
docker compose version || echo "compose v2 없음 → Step 1 참고"

echo "=== [0-2] 포트 점유 확인 (4000=LiteLLM, 5432=postgres) ==="
# 점유 중이면 기존 서비스와 충돌 → 포트 변경 또는 중단 검토
sudo ss -ltnp | grep -E ':4000|:5432' || echo "4000/5432 비어있음 (정상)"

echo "=== [0-3] 기존 컨테이너 목록 (이름 충돌 확인) ==="
# litellm-proxy / litellm-postgres 이름이 이미 있으면 충돌
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -iE 'litellm|postgres' || echo "충돌 컨테이너 없음 (정상)"

echo "=== [0-4] 기존 docker volume 충돌 확인 ==="
docker volume ls | grep -i 'litellm\|postgres' || echo "충돌 volume 없음"

echo "=== [0-5] 디스크 여유 (이미지+DB 최소 5GB 권장) ==="
df -h /var/lib/docker /opt 2>/dev/null

echo "=== [0-6] 외부 도달성 (이미지 pull + API) ==="
curl -sS --max-time 8 -o /dev/null -w 'ghcr=%{http_code}\n' https://ghcr.io/ || echo "ghcr 실패"
curl -sS --max-time 8 -o /dev/null -w 'openai=%{http_code}\n' https://api.openai.com/v1/models || echo "openai 도달 실패(키 없으면 401 정상)"
curl -sS --max-time 8 -o /dev/null -w 'bedrock=%{http_code}\n' https://bedrock-runtime.us-east-1.amazonaws.com/ || echo "bedrock 도달 실패"
```

**판정 기준:**
- `4000`/`5432`가 이미 점유 중 → docker-compose의 호스트 포트를 다른 값으로 바꾸거나(예: `14000:4000`), 점유 서비스 확인 후 진행
- `litellm-proxy`/`litellm-postgres` 이름의 컨테이너가 이미 있음 → 기존 배포 존재. 새로 만들지 말고 기존 것 업데이트 절차(Part 3.x)로
- ghcr 접근 불가 → 이미지 pull 불가, 사내 레지스트리/프록시 경유 필요

#### Step 1. Docker 확인 (설치돼 있으면 건너뜀 — 제거/재설치 금지)

> ⚠️ **운영 서버에서 Docker를 제거하거나 재설치하지 않는다.** 기존 컨테이너가 전부 중단될 수 있다.
> swgr1sv1은 Docker 27.4.1이 이미 설치돼 있으므로 **이 단계 전체를 건너뛴다.**

```bash
# 이미 있는지만 확인 (있으면 끝)
if command -v docker >/dev/null 2>&1; then
    echo "Docker 설치됨: $(docker --version) → 설치 단계 건너뜀"
    docker compose version >/dev/null 2>&1 && echo "Compose v2 사용 가능" \
        || echo "주의: Compose v2 플러그인 없음 → docker-compose-plugin만 추가 설치 검토"
else
    echo "Docker 미설치 → 아래 신규 설치 절차 진행"
fi
```

**Docker가 전혀 없을 때만** (신규 서버 한정) 아래를 실행한다. **기존 Docker가 있으면 절대 실행하지 말 것** (remove 단계 없음):

```bash
# 신규 설치 전용 — 기존 Docker 있으면 실행 금지
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # 로그아웃 후 적용
```

#### Step 2. 프로젝트 디렉토리 생성

```bash
sudo mkdir -p /opt/litellm/{config,certs,docs}
cd /opt/litellm
```

#### Step 3. 환경변수 파일 생성 (.env)

> ⚠️ **반드시 아래 "랜덤 생성 방식"을 쓴다.** heredoc에 `'EOF'`(따옴표)를 쓰면 `$(openssl ...)`가 **문자 그대로 저장되어** 키가 깨진다. 따옴표 없는 `EOF` + 변수 사전 생성 방식만 사용.

```bash
# 비밀번호/키를 먼저 셸 변수로 생성
PG_PASS=$(openssl rand -hex 24)
MASTER=$(openssl rand -hex 32)
SALT=$(openssl rand -hex 32)

# 따옴표 없는 EOF → 변수 치환됨
cat > /opt/litellm/.env << EOF
POSTGRES_PASSWORD=${PG_PASS}
LITELLM_MASTER_KEY=sk-${MASTER}
LITELLM_SALT_KEY=sk-${SALT}
OPENAI_API_KEY=sk-proj-<YOUR_OPENAI_KEY>
AWS_REGION=us-east-1
AWS_BEARER_TOKEN_BEDROCK=<YOUR_BEDROCK_TOKEN>
STORE_MODEL_IN_DB=True
EOF

chmod 600 /opt/litellm/.env
```

> **중요:** `OPENAI_API_KEY`와 `AWS_BEARER_TOKEN_BEDROCK`를 실제 값으로 교체.
> 생성 후 `cat /opt/litellm/.env`로 `POSTGRES_PASSWORD`/`sk-...`가 **리터럴이 아닌 실제 랜덤 값**인지 확인.

#### Step 4. config.yaml 생성

```bash
cat > /opt/litellm/config/config.yaml << 'EOF'
model_list:
  # OpenAI Codex 모델
  - model_name: gpt-5.1-codex-mini
    litellm_params:
      model: openai/gpt-5.1-codex-mini
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-5.1-codex-max
    litellm_params:
      model: openai/gpt-5.1-codex-max
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-5.2-codex
    litellm_params:
      model: openai/gpt-5.2-codex
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-5.3-codex
    litellm_params:
      model: openai/gpt-5.3-codex
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-5.4
    litellm_params:
      model: openai/gpt-5.4
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-5.2
    litellm_params:
      model: openai/gpt-5.2
      api_key: os.environ/OPENAI_API_KEY

  # Bedrock Claude 모델
  - model_name: claude-haiku-4-5
    litellm_params:
      model: bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0
      aws_region_name: os.environ/AWS_REGION

  - model_name: claude-sonnet-4-6
    litellm_params:
      model: bedrock/us.anthropic.claude-sonnet-4-6
      aws_region_name: os.environ/AWS_REGION

  - model_name: claude-opus-4-6
    litellm_params:
      model: bedrock/us.anthropic.claude-opus-4-6-v1
      aws_region_name: os.environ/AWS_REGION

  - model_name: claude-opus-4-7
    litellm_params:
      model: bedrock/us.anthropic.claude-opus-4-7
      aws_region_name: os.environ/AWS_REGION

  - model_name: claude-opus-4-8
    litellm_params:
      model: bedrock/us.anthropic.claude-opus-4-8
      aws_region_name: os.environ/AWS_REGION

  - model_name: claude-opus-4-1
    litellm_params:
      model: bedrock/us.anthropic.claude-opus-4-1-20250805-v1:0
      aws_region_name: os.environ/AWS_REGION

general_settings:
  database_url: os.environ/DATABASE_URL

litellm_settings:
  drop_params: true

  default_key_generate_params:
    models:
      - gpt-5.1-codex-mini
      - gpt-5.1-codex-max
      - gpt-5.2-codex
      - gpt-5.3-codex
      - gpt-5.4
      - gpt-5.2
      - claude-sonnet-4-6
      - claude-opus-4-8
      - claude-opus-4-7
      - claude-opus-4-6
      - claude-opus-4-1
      - claude-haiku-4-5
    max_budget: 10
    budget_duration: 30d
    rpm_limit: 60
    tpm_limit: 2000000
    max_parallel_requests: 2
EOF
```

#### Step 5. entrypoint.sh 생성 (MCP SSL 패치)

```bash
cat > /opt/litellm/config/entrypoint.sh << 'EOF'
#!/bin/bash
# MCP 서버 self-signed 인증서 우회 패치
# LiteLLM MCP client만 영향 — OpenAI/Bedrock 연결 무관
MCP_CLIENT="/app/.venv/lib/python3.13/site-packages/litellm/experimental_mcp_client/client.py"
if [ -f "$MCP_CLIENT" ] && ! grep -q "ssl_config = False" "$MCP_CLIENT"; then
    sed -i 's/ssl_config = get_ssl_configuration(self.ssl_verify)/ssl_config = False/' "$MCP_CLIENT"
    find /app/.venv/lib/python3.13/site-packages/litellm/experimental_mcp_client/__pycache__ -name "client*" -delete 2>/dev/null
fi
exec docker/prod_entrypoint.sh "$@"
EOF

chmod +x /opt/litellm/config/entrypoint.sh
```

> **Note:** 공인 CA 인증서 적용 후에는 이 파일과 docker-compose의 entrypoint 관련 설정을 제거해도 됩니다.

#### Step 6. docker-compose.yml 생성

```bash
cat > /opt/litellm/docker-compose.yml << 'EOF'
services:
  postgres:
    image: postgres:16
    container_name: litellm-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: litellm
      POSTGRES_USER: litellm
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U litellm -d litellm"]
      interval: 10s
      timeout: 5s
      retries: 10

  litellm:
    image: ghcr.io/berriai/litellm:main-stable
    container_name: litellm-proxy
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "4000:4000"
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://litellm:${POSTGRES_PASSWORD}@postgres:5432/litellm
    volumes:
      - ./config/config.yaml:/app/config.yaml:ro
      - ./config/entrypoint.sh:/entrypoint.sh:ro
    entrypoint: ["/entrypoint.sh"]
    command:
      - "--config"
      - "/app/config.yaml"
      - "--host"
      - "0.0.0.0"
      - "--port"
      - "4000"

volumes:
  postgres_data:
EOF
```

#### Step 7. 서비스 시작

> 이 compose 프로젝트는 `/opt/litellm` 디렉토리에 독립적으로 뜬다. **기존에 돌고 있는 다른 컨테이너에는 영향 없다** (별도 프로젝트명·별도 volume). 단 Step 0에서 포트/이름 충돌이 없음을 확인한 뒤 실행한다.

```bash
cd /opt/litellm
docker compose pull
docker compose up -d
```

시작 확인 (30초 대기 후):
```bash
docker compose ps
# postgres: healthy, litellm: running

docker logs litellm-proxy --tail 5
# "Uvicorn running on http://0.0.0.0:4000" 확인
```

#### Step 8. 동작 검증

```bash
# .env에서 MASTER KEY 읽기
MASTER_KEY=$(grep LITELLM_MASTER_KEY /opt/litellm/.env | cut -d= -f2)

# 모델 목록 확인
curl -s -H "Authorization: Bearer $MASTER_KEY" http://localhost:4000/v1/models \
  | python3 -m json.tool | grep '"id"'

# Claude 모델 테스트
curl -s -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}' \
  | python3 -m json.tool | grep '"content"'

# OpenAI 모델 테스트 (Responses API)
curl -s -X POST http://localhost:4000/v1/responses \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-5.1-codex-mini", "input": "hello"}' \
  | python3 -m json.tool | head -5
```

#### Step 9. 팀 생성 및 첫 번째 Virtual Key 발급

```bash
MASTER_KEY=$(grep LITELLM_MASTER_KEY /opt/litellm/.env | cut -d= -f2)

# 팀 생성
curl -s -X POST http://localhost:4000/team/new \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "team_alias": "IT/Devops",
    "models": ["all-proxy-models"],
    "max_budget": 100
  }' | python3 -m json.tool | grep '"team_id"'
# → team_id 메모

# Virtual Key 생성 (위 team_id 입력)
curl -s -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "key_alias": "username-personal",
    "team_id": "<TEAM_ID>",
    "max_budget": 10,
    "budget_duration": "30d"
  }' | python3 -m json.tool | grep '"key"'
# → sk-xxxx 키를 사용자에게 전달
```

#### Step 10. UI 접근

브라우저에서: `http://<SERVER_IP>:4000/ui`

로그인: Master Key 입력

#### Step 11. 방화벽 설정 (UFW)

> ⚠️ **운영 서버에서 UFW를 처음 켜는 것은 위험하다.** `ufw enable` 시 기본 정책이 모든 inbound deny로 바뀌어 **기존 SSH/서비스 연결이 끊길 수 있다.** 이미 FortiGate로 망 경계를 통제 중이면 **UFW는 건드리지 않는 것을 권장**한다.

```bash
# UFW가 이미 active인지 먼저 확인
sudo ufw status

# (UFW를 이미 운영 중인 경우에만) LiteLLM 포트를 내부 대역에만 허용
sudo ufw allow from 192.128.0.0/16 to any port 4000 proto tcp comment "LiteLLM from internal"

# FortiGate에서 4000 포트를 통제한다면 UFW 설정 불필요
```

FortiGate 커스텀 서비스: `LiteLLM-4000` (TCP 4000) — 출발지 사내 대역만 허용.

#### Step 12. 롤백 / 제거 절차 (이 배포만 깨끗이 되돌리기)

> 이 스택은 독립 compose 프로젝트라 **이것만 정확히 제거**할 수 있다. 다른 컨테이너·이미지는 건드리지 않는다.

```bash
cd /opt/litellm

# 컨테이너만 중지 (데이터 보존)
docker compose down

# 컨테이너 + 이 프로젝트 volume까지 제거 (DB 데이터 삭제 — 주의)
docker compose down -v

# 이미지까지 정리하려면 (이 이미지만 명시적으로)
docker rmi ghcr.io/berriai/litellm:main-stable postgres:16 2>/dev/null || true
```

> ⚠️ `docker system prune -a` 같은 **전역 정리 명령은 절대 쓰지 말 것** — 서버의 다른 서비스 이미지/볼륨까지 날아간다. 항상 `docker compose down`(이 프로젝트 한정) 또는 이미지명을 명시한 `docker rmi`만 사용한다.

---

## Part 3. 운영 계획

### 3.1 인프라 구성

| 구성요소 | 이미지/서비스 | 역할 |
|---|---|---|
| LiteLLM Proxy | `ghcr.io/berriai/litellm:main-stable` | API 게이트웨이, 모델 라우팅 |
| PostgreSQL 16 | `postgres:16` | 키/사용량/설정 저장 |
| Nginx | (추후) | HTTPS 종단, MCP 프록시 |

```yaml
# docker-compose.yml 핵심 구조
services:
  postgres:
    image: postgres:16
    healthcheck: pg_isready
  litellm:
    image: ghcr.io/berriai/litellm:main-stable
    ports: ["4000:4000"]
    env_file: .env
    volumes:
      - ./config/config.yaml:/app/config.yaml:ro
      - ./config/entrypoint.sh:/entrypoint.sh:ro  # MCP SSL 패치용
    entrypoint: ["/entrypoint.sh"]
```

### 3.2 Apptainer Wrapper 수정사항

`/Infra/systems/bosai/codex/codex` 파일에 추가할 내용:

```bash
# LiteLLM 프록시 URL (모든 사용자 공통)
export APPTAINERENV_OPENAI_BASE_URL="http://<LITELLM_SERVER_IP>:4000/v1"
```

추가 검토 사항:
- MCP 공인 인증서 적용 후에는 별도 SSL 관련 환경변수 불필요
- `config.toml`의 `openai_base_url`은 동작하지 않으므로 환경변수가 유일한 방법

### 3.3 모델 등록

#### OpenAI Codex 모델 (Codex CLI용)

| model_name | upstream 모델 | 용도 |
|---|---|---|
| gpt-5.1-codex-mini | openai/gpt-5.1-codex-mini | 저렴, 빠름 |
| gpt-5.1-codex-max | openai/gpt-5.1-codex-max | deep reasoning |
| gpt-5.2-codex | openai/gpt-5.2-codex | frontier agentic |
| gpt-5.3-codex | openai/gpt-5.3-codex | CLI 기본값 |
| gpt-5.4 | openai/gpt-5.4 | CLI 자동 migrate 대상 |
| gpt-5.2 | openai/gpt-5.2 | frontier general |

#### Bedrock Claude 모델

| model_name | upstream 모델 | 비고 |
|---|---|---|
| claude-haiku-4-5 | bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0 | 빠른 응답 |
| claude-sonnet-4-6 | bedrock/us.anthropic.claude-sonnet-4-6 | 중간 성능 |
| claude-opus-4-6 | bedrock/us.anthropic.claude-opus-4-6-v1 | 고성능 |
| claude-opus-4-7 | bedrock/us.anthropic.claude-opus-4-7 | 고성능 |
| claude-opus-4-8 | bedrock/us.anthropic.claude-opus-4-8 | 최신 |
| claude-opus-4-1 | bedrock/us.anthropic.claude-opus-4-1-20250805-v1:0 | legacy |

**Bedrock 인증:** `AWS_BEARER_TOKEN_BEDROCK` 환경변수 (`.env`에 설정)  
**Cross-region:** `us.` prefix 필수 (inference profile)

#### 모델 ID 조회 방법

```bash
curl -s "https://bedrock.us-east-1.amazonaws.com/foundation-models" \
  -H "Authorization: Bearer $AWS_BEARER_TOKEN_BEDROCK" \
  | python3 -m json.tool | grep '"modelId".*claude'
```

### 3.4 키 관리 프로세스

#### 계층 구조

```
Team (예: IT/Devops)
  └─ User (예: seungil.woo)
       └─ Virtual Key (예: sk-xzdnIFTHmWs--_UGDBc0zQ)
```

#### 기본값 (config.yaml `default_key_generate_params`)

| 항목 | 값 | 비고 |
|---|---|---|
| max_budget | 운영 시 결정 | PoC에서는 $1~$10 |
| budget_duration | 30d | 월간 리셋 |
| rpm_limit | 60 | 분당 요청 |
| tpm_limit | 2,000,000 | 분당 토큰 |
| max_parallel_requests | 2 | 동시 요청 |
| models | 전체 12개 | 모든 모델 허용 |

#### MCP Access Group
- 팀 단위로 Access Group 할당
- MCP 서버별로 접근 가능한 팀 제한 가능

### 3.5 사용자 온보딩 절차

#### 관리자 작업
1. LiteLLM UI에서 Virtual Key 생성 (팀/유저 지정)
2. 생성된 `sk-xxxx` 키를 사용자에게 전달

#### 사용자 작업 (1회)
1. `~/.codex/auth.json` 생성 (LiteLLM virtual key):
```json
{
  "OPENAI_API_KEY": "sk-xxxx"
}
```

2. `~/.codex/config.toml` (LLM + MCP 모두 LiteLLM 경유 — 검증된 최종 형태):
```toml
model = "gpt-5.1-codex-mini"
model_provider = "litellm"
model_reasoning_effort = "medium"

[model_providers.litellm]
name = "litellm"
base_url = "http://192.128.20.240:4000/v1"
wire_api = "responses"

[mcp_servers.bos-ai-rag]
url = "http://192.128.20.240:4000/mcp"
http_headers = { Authorization = "Bearer sk-xxxx" }   # virtual key (auth.json과 동일)
startup_timeout_sec = 60
tool_timeout_sec = 120
```

3. `codex` 실행 → `/mcp`로 17개 도구 확인, 프롬프트 동작 확인

> 참고: MCP를 LiteLLM Gateway가 아닌 **직접** 쓰려면 `url = "https://mcp.bossemi-ai.com/mcp"`(헤더 불필요)도 가능. 단 팀별 통제를 위해 **Gateway 경유를 권장**.

### 3.6 방화벽 정책

| 출발지 | 목적지 | 포트 | 프로토콜 | 용도 |
|---|---|---|---|---|
| bos-login 서버 | LiteLLM 서버 (server01) | 4000 | TCP | Codex → LiteLLM (LLM + MCP Gateway) |
| LiteLLM 서버 | api.openai.com | 443 | HTTPS | OpenAI 모델 호출 |
| LiteLLM 서버 | bedrock-runtime.us-east-1.amazonaws.com | 443 | HTTPS | Bedrock 모델 호출 |
| LiteLLM 서버 | mcp.bossemi-ai.com (Nginx 10.10.1.62) | 443 | HTTPS | MCP Gateway 백엔드 |
| bos-login 서버 | mcp.bossemi-ai.com | 443 | HTTPS | Codex CLI MCP 직접 연결(선택) |

FortiGate 커스텀 서비스:
- `LiteLLM-4000`: TCP 포트 4000

### 3.7 MCP 인증서 (해결 완료 — 2026-06-03)

#### 적용 결과
- 공인 도메인 **`bossemi-ai.com`** Route53 등록 (auto-renew/privacy ON, 만료 2027-06-02)
- **Let's Encrypt** cert를 DNS-01(certbot + dns-route53)로 발급, `mcp.bossemi-ai.com` 대상 (만료 2026-09-01)
- **Nginx(10.10.1.62)** 에 cert 적용, `mcp.bossemi-ai.com` vhost 추가 (기존 `mcp.corp.bos-semi.com` 병행 유지)
- Codex CLI(Rust webpki-roots)가 **trust-store 변경 없이** 연결 성공

#### 현재 구조
```
Codex CLI → http://192.128.20.240:4000/mcp (LiteLLM Gateway, Bearer)
                    │  (또는 직접: https://mcp.bossemi-ai.com/mcp)
              LiteLLM (virtual key/팀 검사)
                    │
              Nginx (Let's Encrypt cert, mcp.bossemi-ai.com:443)
                    │
              MCP Node.js (10.10.1.10:3000, HTTP 내부)
```

#### 갱신 주의
- 이번 cert는 PC/WSL에서 **수동 발급**한 것 → certbot timer 자동갱신 미연결. **만료 2026-09-01 전(8월 중순)** 수동 갱신 필요.
- 항구적 자동화는 별도 작업(NAT 임시 egress 토글 또는 Logging VPC 발급 머신 + S3 동기화).

### 3.8 모니터링/운영

| 항목 | 방법 |
|---|---|
| 사용량/비용 | LiteLLM UI 대시보드 (`http://<server>:4000/ui`) |
| 키 예산 초과 | 자동 차단 + UI 알림 |
| 서비스 상태 | `docker compose ps`, health endpoint |
| MCP 인증서 갱신 | **수동** (만료 2026-09-01, 8월 중순 갱신). 자동화 미연결 |
| 모델 추가 | config.yaml 수정 → `docker compose restart litellm` |

### 3.9 Claude Code VSCode 설정 (선택)

사용자가 VSCode에서 Claude Code를 LiteLLM 경유로 사용하려면:

```json
// VSCode settings.json (claudeCode.environmentVariables)
{
  "claudeCode.environmentVariables": [
    { "name": "ANTHROPIC_BASE_URL", "value": "http://<LITELLM_SERVER_IP>:4000" },
    { "name": "ANTHROPIC_AUTH_TOKEN", "value": "sk-xxxx" }
  ]
}
```

또는 `~/.claude/settings.json`:
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://<LITELLM_SERVER_IP>:4000",
    "ANTHROPIC_AUTH_TOKEN": "sk-xxxx"
  }
}
```

---

## 부록: 현재 PoC 환경 설정 파일

### .env
```
POSTGRES_PASSWORD=<generated>
LITELLM_MASTER_KEY=sk-<master-key>
LITELLM_SALT_KEY=sk-<salt-key>
OPENAI_API_KEY=sk-proj-<openai-key>
AWS_REGION=us-east-1
AWS_BEARER_TOKEN_BEDROCK=ABSK<token>
STORE_MODEL_IN_DB=True
```

### entrypoint.sh (MCP SSL 패치)
```bash
#!/bin/bash
MCP_CLIENT="/app/.venv/lib/python3.13/site-packages/litellm/experimental_mcp_client/client.py"
if [ -f "$MCP_CLIENT" ] && ! grep -q "ssl_config = False" "$MCP_CLIENT"; then
    sed -i 's/ssl_config = get_ssl_configuration(self.ssl_verify)/ssl_config = False/' "$MCP_CLIENT"
    find /app/.venv/lib/python3.13/site-packages/litellm/experimental_mcp_client/__pycache__ -name "client*" -delete 2>/dev/null
fi
exec docker/prod_entrypoint.sh "$@"
```

> **Note (2026-06-04):** MCP가 이미 공인 인증서(`mcp.bossemi-ai.com`, Let's Encrypt)로 전환됨 → **이 entrypoint SSL 패치는 더 이상 필요 없다.** 운영 배포 시 `entrypoint.sh`와 docker-compose의 `entrypoint:`/관련 volume 마운트를 제거하고, LiteLLM 기본 entrypoint를 사용하면 된다. (이 부록은 PoC 시점 기록용으로 보존)
