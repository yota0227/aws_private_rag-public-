# LLM Gateway — Admin 운영 가이드

## 개요

LLM Gateway는 3개 EC2 인스턴스로 구성된 통합 AI 개발 인프라다:
- **LiteLLM Proxy** (Logging VPC) — OpenAI-compatible API, Virtual Key 관리
- **MCP Server** (Frontend VPC) — 17개 RAG/Neptune/HDD 도구
- **Squid Forward Proxy** (Logging VPC) — 도메인 화이트리스트 인터넷 접근

---

## 1. 배포 절차

### 1.1 사전 조건

- Terraform >= 1.5.0, AWS CLI 설정 완료
- S3 backend 접근 권한 (s3-bos-ai-terraform-state-seoul-prod)
- Seoul 리전 VPC, TGW 등 network-layer 배포 완료

### 1.2 Network Layer 배포 (Squid + Routes)

```bash
cd environments/network-layer
terraform init
terraform plan -out=plan.tfplan

# plan 검토: 기존 리소스에 destructive 변경 없는지 확인
terraform show plan.tfplan | grep -E "destroy|replace"

# 문제 없으면 적용
terraform apply plan.tfplan
```

### 1.3 App Layer 배포 (LiteLLM + MCP + API GW + DNS)

```bash
cd environments/app-layer/bedrock-rag
terraform init -upgrade   # random provider 추가됨
terraform plan -out=plan.tfplan

# plan 검토
terraform apply plan.tfplan
```

### 1.4 배포 후 확인

```bash
# LiteLLM 헬스체크
curl http://<litellm-private-ip>:4000/health

# MCP Server 헬스체크
curl http://<mcp-private-ip>:3000/health

# Squid 연결 확인 (온프레미스에서)
curl -x http://<squid-private-ip>:3128 https://api.openai.com
```

---

## 2. Virtual Key 관리 (팀/사용자 생성)

### 2.1 Master Key 확인

Master Key는 Secrets Manager에 저장됨:
```bash
aws secretsmanager get-secret-value \
  --secret-id "llm-gateway/litellm-master-key" \
  --region ap-northeast-2 \
  --query 'SecretString' --output text
```

### 2.2 팀 생성

```bash
MASTER_KEY="<위에서 확인한 키>"
LITELLM_URL="https://llm.corp.bos-semi.com/prod/llm"

# 팀 생성 (예: SoC Design팀, 월 $100 예산)
curl -X POST "${LITELLM_URL}/team/new" \
  -H "Authorization: Bearer ${MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "team-soc-design",
    "team_alias": "SoC Design팀",
    "max_budget": 100.0,
    "budget_duration": "1mo",
    "models": ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", "claude-3-haiku"]
  }'
```

### 2.3 사용자 Virtual Key 발급

```bash
# 개별 사용자 키 발급 (90일 유효, 월 $20 예산)
curl -X POST "${LITELLM_URL}/key/generate" \
  -H "Authorization: Bearer ${MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "hong.gildong",
    "team_id": "team-soc-design",
    "key_alias": "홍길동 개인키",
    "max_budget": 20.0,
    "budget_duration": "1mo",
    "models": ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", "claude-3-haiku"],
    "duration": "90d"
  }'

# 응답:
# { "key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "expires": "2026-08-17T..." }
# → 이 sk-xxx 키를 사용자에게 전달
```

### 2.4 키/사용량 조회

```bash
# 전체 키 목록
curl "${LITELLM_URL}/key/list" -H "Authorization: Bearer ${MASTER_KEY}"

# 특정 키 사용량
curl "${LITELLM_URL}/key/info?key=sk-xxxxxx" -H "Authorization: Bearer ${MASTER_KEY}"

# 팀 예산 현황
curl "${LITELLM_URL}/team/info?team_id=team-soc-design" -H "Authorization: Bearer ${MASTER_KEY}"
```

### 2.5 키 삭제 (퇴사자/만료)

```bash
curl -X POST "${LITELLM_URL}/key/delete" \
  -H "Authorization: Bearer ${MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"keys": ["sk-xxxxxx"]}'
```

---

## 3. 모델 관리

### 3.1 현재 모델 목록

| Model Name | Provider | 경로 |
|------------|----------|------|
| gpt-4o | OpenAI | NAT → Internet |
| gpt-4o-mini | OpenAI | NAT → Internet |
| o3-mini | OpenAI | NAT → Internet |
| claude-3-5-sonnet | Bedrock | TGW → Peering → Virginia |
| claude-3-haiku | Bedrock | TGW → Peering → Virginia |
| claude-3-opus | Bedrock | TGW → Peering → Virginia |
| titan-embed-text-v2 | Bedrock | TGW → Peering → Virginia |

### 3.2 모델 추가/삭제

```bash
# SSM으로 LiteLLM EC2 접속
aws ssm start-session --target <litellm-instance-id> --region ap-northeast-2

# config.yaml 편집
sudo vi /data/litellm/config.yaml

# 컨테이너 재시작
cd /data && sudo docker compose restart litellm

# 확인
curl http://localhost:4000/v1/models
```

---

## 4. Squid 화이트리스트 관리

### 4.1 도메인 추가

```bash
aws ssm start-session --target <squid-instance-id>
echo ".new-service.com" | sudo tee -a /etc/squid/whitelist.txt
sudo squid -k parse && sudo systemctl reload squid
```

### 4.2 현재 화이트리스트

- `.kiro.dev` — Kiro CLI 인증
- `api.openai.com` — OpenAI API (Codex CLI 직접 접근 시)
- `api.anthropic.com` — Anthropic API (Claude Code 직접 접근 시)
- `.amazoncognito.com` — AWS Cognito 인증

---

## 5. 모니터링

### 5.1 CloudWatch 알람 (SNS → llm-gateway-alerts)

| 알람 | 조건 | 대응 |
|------|------|------|
| litellm-cpu-high | CPU > 80% 5분 | 스케일업(t3.large) 검토 |
| litellm-status-check-failed | 2회 연속 | docker compose 상태 확인 |
| mcp-cpu-high | CPU > 80% 5분 | 동시 접속 수 확인 |
| squid-cpu-high | CPU > 70% 5분 | 접속 로그 분석 |

### 5.2 로그 조회

```bash
aws logs tail /llm-gateway/litellm --follow --region ap-northeast-2
aws logs tail /llm-gateway/mcp-server --follow --region ap-northeast-2
aws logs tail /llm-gateway/squid --follow --region ap-northeast-2
```

---

## 6. 백업 및 복구

- **자동**: 매일 03:00 KST → pg_dump → S3 (로컬 7일, S3 90일)
- **수동**: `sudo /data/scripts/backup-postgres.sh`
- **복구**: docker stop → pg_restore → docker start → /health 확인

---

## 7. 업데이트/롤백

```bash
# LiteLLM 버전 업데이트
aws ssm start-session --target <litellm-instance-id>
cd /data
sudo sed -i 's/litellm:v1.61.4/litellm:v1.62.0/' docker-compose.yml
sudo docker compose pull litellm && sudo docker compose up -d litellm

# 120초 내 헬스체크 실패 시 → 이전 버전으로 롤백
sudo sed -i 's/litellm:v1.62.0/litellm:v1.61.4/' docker-compose.yml
sudo docker compose up -d litellm
```

---

## 8. 사내 DNS 도메인 바인딩

LLM Gateway 서비스 도메인을 사내 DNS에 등록하여 엔지니어들이 VPN 환경에서 접근할 수 있게 합니다.

### 8.1 도메인 목록

| 도메인 | 대상 IP | 포트 | 용도 |
|--------|---------|------|------|
| `llm.corp.bos-semi.com` | LiteLLM EC2 Private IP | 4000 | LLM API (OpenAI-compatible) |
| `mcp.corp.bos-semi.com` | MCP Server EC2 Private IP (server02) | 3100 | MCP Streamable HTTP/SSE |
| `rag.corp.bos-semi.com` | API Gateway VPC Endpoint IP | 443 | RAG Document API |

### 8.2 사내 DNS 서버 설정 (BIND)

사내 BIND 서버 (예: `ns1.corp.bos-semi.com`)에서 zone 파일 수정:

```bash
# /etc/named/zones/corp.bos-semi.com.zone

; LLM Gateway 서비스 (Seoul VPC Private IP)
llm     IN  A   <LiteLLM EC2 Private IP>     ; Logging VPC
mcp     IN  A   192.128.20.241               ; server02 (온프레미스)
rag     IN  A   <API GW VPC Endpoint IP>      ; Frontend VPC

; HTTPS용 (TLS termination 필요 시 reverse proxy 사용)
; nginx/caddy를 앞에 두고 cert 적용 권장
```

### 8.3 IP 확인 방법

```bash
# LiteLLM EC2 Private IP
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=ec2-litellm-bos-ai-seoul-prod" \
  --region ap-northeast-2 \
  --query "Reservations[0].Instances[0].PrivateIpAddress" --output text

# MCP Server (server02 — 온프레미스)
# 192.128.20.241 (고정)

# API Gateway VPC Endpoint IP
aws ec2 describe-vpc-endpoints \
  --filters "Name=service-name,Values=*execute-api*" \
  --region ap-northeast-2 \
  --query "VpcEndpoints[0].NetworkInterfaceIds" --output text
# → 각 ENI의 private IP를 확인:
aws ec2 describe-network-interfaces --network-interface-ids <eni-id> \
  --query "NetworkInterfaces[0].PrivateIpAddress" --output text
```

### 8.4 DNS 변경 후 확인

```bash
# 온프레미스에서 resolve 확인
nslookup llm.corp.bos-semi.com
nslookup mcp.corp.bos-semi.com

# 헬스체크
curl https://llm.corp.bos-semi.com/health
curl https://mcp.corp.bos-semi.com/health
```

### 8.5 HTTPS 설정 (선택)

사내 CA 인증서로 TLS 적용 시:

1. **server02 (MCP)**: Caddy 또는 Nginx reverse proxy 설정
   ```
   # Caddy 예시 (자동 HTTPS with 사내 CA)
   mcp.corp.bos-semi.com {
     reverse_proxy localhost:3100
     tls /etc/ssl/bos-semi-ca/mcp.crt /etc/ssl/bos-semi-ca/mcp.key
   }
   ```

2. **LiteLLM EC2**: 동일하게 Nginx/Caddy로 4000 → 443 프록시

3. 사내 CA cert를 엔지니어 PC에 trust store로 추가하면 브라우저/CLI에서 인증서 경고 없음

### 8.6 Route53 Private Hosted Zone (AWS 내부용)

Lambda/EC2 간 내부 통신은 Route53 Private Hosted Zone(`corp.bos-semi.com`)으로 이미 설정됨:

```
rag.corp.bos-semi.com → API Gateway VPC Endpoint (ALIAS)
```

이 설정은 `environments/network-layer/`의 Route53 Terraform에서 관리.

---

## 9. 신규 서비스 투입 체크리스트

새로운 LLM/MCP 관련 서비스 추가 시:

- [ ] EC2/Container 배포 (Terraform)
- [ ] Security Group ingress/egress 설정
- [ ] 사내 DNS A 레코드 추가 (§8.2)
- [ ] HTTPS 인증서 설정 (§8.5)
- [ ] 엔지니어 가이드 업데이트 (USER_GUIDE.md)
- [ ] VPN 라우팅 확인 (TGW/VPC Peering)
- [ ] CloudWatch 알람 설정
- [ ] 백업 스크립트 적용
