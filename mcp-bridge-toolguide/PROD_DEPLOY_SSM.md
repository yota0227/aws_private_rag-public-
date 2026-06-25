# Tool Guide MCP — 운영 배포 (A안: 기존 MCP EC2에 :3001 추가, SSM 무중단)

> **Created:** 2026-06-25
> **Updated:** 2026-06-25
> **Purpose:** 운영 Tool Guide MCP를 기존 MCP EC2(i-0274fe4da3ecd8f7f, 10.10.1.10)에 :3001 브리지로 추가하고, EC2/nginx 교체 없이 SSM/CLI로 무중단 반영하는 절차 + 실제 진행 상태.
> **Spec / Project:** `.kiro/specs/eda-tool-guide-rag/` + 운영 BOS-AI Private RAG
> **Status:** In Review
> **Owner:** Infra/DevOps

## 실제 운영 토폴로지 (검증됨, 2026-06-25)

RTL MCP 운영 경로는 **API Gateway를 거치지 않는다.** nginx가 MCP EC2로 직결한다:

```
On-prem/VPN → nginx(10.10.1.62, i-0d6c14b816debaec3, Let's Encrypt cert)
            → http://10.10.1.10:3000/  (MCP EC2, RTL 브리지)
```

- 공인 도메인: **`bossemi-ai.com`** (Route53 public zone `Z00056451IP3ARPARY4ZW`). `mcp.bossemi-ai.com` A → 10.10.1.62.
- cert: `/etc/nginx/ssl/mcp-bossemi-ai-*.pem` (Let's Encrypt, **외부 certbot+route53 DNS-01로 발급 후 수동 복사**. nginx 박스엔 certbot 없음, 폐쇄망이라 ACME 직접 불가).
- nginx/cert/직결 config는 **Terraform 밖에서 수동·SSM으로 운영** (user-data 템플릿은 부트스트랩 흔적일 뿐 실물과 drift).

> 그래서 Tool Guide도 **API GW 없이** nginx 직결로 미러링한다. `corp.bos-semi.com`(사설존/self-signed)은 쓰지 않는다.

## Tool Guide 목표 경로

```
On-prem/VPN → nginx(toolguide.bossemi-ai.com vhost, 전용 cert)
            → http://10.10.1.10:3001/  (MCP EC2, Tool Guide 브리지)
            → lambda-tool-guide-parser-seoul-dev
```

권한 분리: RTL(:3000, mcp.bossemi-ai.com, document-processor Lambda)와 프로세스·포트·Lambda·서브도메인·cert·LiteLLM 항목까지 전부 분리.

---

## 진행 상태 (체크리스트) — 2026-06-25 LIVE

**`https://toolguide.bossemi-ai.com/mcp` 운영 동작 확인 완료** (cert 검증 포함 health 200). 남은 건 #7 LiteLLM뿐.

| # | 항목 | 방식 | 담당 | 상태 |
|---|------|------|------|------|
| 2 | instance profile에 tool-guide Lambda invoke (role-mcp-server-bos-ai-seoul-prod) | Terraform | Kiro | DONE |
| 3 | MCP EC2 SG **인바운드** 3001 (sg-09168f4462a808600) | Terraform | Kiro | DONE |
| 3b | nginx SG **egress** 3001 (sg-0bb8fdd12816c6833) — 실제 막혔던 지점 | Terraform | Kiro | DONE |
| 6 | `toolguide.bossemi-ai.com` A 10.10.1.62 (zone Z00056451IP3ARPARY4ZW) | Route53 CLI | Kiro | DONE |
| A | 브리지 배포 (EC2의 RTL node_modules 재사용 + server.js를 S3 경유) | S3+SSM | Kiro | DONE |
| 1 | MCP EC2 `tool-guide-mcp` systemd(:3001) 기동 | SSM | Kiro | DONE |
| B | `toolguide.bossemi-ai.com` Let's Encrypt cert 발급 (WSL certbot+route53) | certbot | 사용자 | DONE |
| 5 | nginx vhost + cert 배치 + reload (cert/conf base64→SSM 주입) | SSM | Kiro | DONE |
| 7 | LiteLLM에 `https://toolguide.bossemi-ai.com/mcp` 별도 MCP 서버 등록 | 수동 | 사용자 | TODO |

> Terraform 변경은 **#2/#3/#3b만** (plain `terraform apply` 안전, 인스턴스 교체 없음).
> 이전에 시도했던 API GW `/toolguide` 라우트와 user-data 템플릿 수정은 **실물 경로와 무관**해서 되돌렸다.
>
> **막혔던 근본 원인(기록)**: 504 Gateway Time-out → 호스트 방화벽/인바운드 SG 아니라
> **nginx SG egress에 3001이 없어서**(3000만 수동 추가돼 있던 drift)였다. egress 3001 추가로 해결.
>
> **아티팩트 메모**: 브리지 node_modules는 별도 빌드 없이 MCP EC2의 RTL 브리지
> `/opt/mcp-server/node_modules`를 복사해 재사용(deps 동일: sdk/lambda/express/zod). server.js·package.json·
> systemd unit·nginx conf는 `s3://bos-ai-rtl-src-533335672315/deploy/toolguide/`에 보존(재배포용).
>
> **cert 전달 경로 메모(보안)**: nginx 박스는 S3·인터넷 도달 불가라 cert를 base64로 SSM Run Command에
> 실어 주입했다 → privkey가 **SSM 명령 이력(~30일)에 남는다.** 민감하면 만료 갱신 시 cert 재발급으로 자연 교체.

---

## 사용자 작업 A: 브리지 아티팩트 업로드 (server02)

MCP EC2는 폐쇄망(NAT 없음) -> S3에서만 받는다. 로컬엔 node가 없어 node_modules를 못 만드니
이미 동작 중인 server02 브리지를 그대로 묶는다.

```bash
# server02에서
cd /root
tar -czf /tmp/tool-guide-mcp.tar.gz -C /root bos-ai-toolguide-bridge
aws s3 cp /tmp/tool-guide-mcp.tar.gz \
  s3://bos-ai-rtl-src-533335672315/deploy/tool-guide-mcp.tar.gz \
  --region ap-northeast-2
```

업로드되면 Kiro에게 알려주면 #1(SSM 브리지 기동)을 진행한다.

## 사용자 작업 B: toolguide cert 발급

`mcp.bossemi-ai.com`과 동일한 기존 절차(인터넷 가능한 호스트에서 certbot + dns-route53 DNS-01)로
**`toolguide.bossemi-ai.com`** cert를 발급한다. 권장: 향후 편의를 위해 SAN(mcp+toolguide) 또는
와일드카드 `*.bossemi-ai.com`로 발급. 발급 후 nginx 박스(i-0d6c14b816debaec3)에 복사:

```
/etc/nginx/ssl/toolguide-bossemi-ai-fullchain.pem
/etc/nginx/ssl/toolguide-bossemi-ai-privkey.pem
```

(와일드카드면 mcp와 같은 파일을 가리켜도 됨 — 그 경우 #5 vhost의 cert 경로만 맞춰주면 된다.)
복사 완료되면 Kiro에게 알려주면 #5(nginx vhost)를 진행한다.

## 사용자 작업 7: LiteLLM 등록

RTL(`https://mcp.bossemi-ai.com/mcp`)과 **별도 MCP 서버**로 등록 + 별도 권한 그룹:
- 이름: `bos-ai-tool-guide`
- URL: `https://toolguide.bossemi-ai.com/mcp`
- 도구: `tool_guide_search`, `tool_guide_query`

---

## Kiro 작업 #1: MCP EC2에 브리지 기동 (A 완료 후, SSM)

```bash
aws ssm send-command \
  --region ap-northeast-2 \
  --document-name "AWS-RunShellScript" \
  --targets "Key=InstanceIds,Values=i-0274fe4da3ecd8f7f" \
  --comment "Deploy Tool Guide MCP bridge :3001" \
  --parameters 'commands=[
    "set -e",
    "aws s3 cp s3://bos-ai-rtl-src-533335672315/deploy/tool-guide-mcp.tar.gz /tmp/tg.tar.gz --region ap-northeast-2",
    "rm -rf /opt/tool-guide-mcp /tmp/tg && mkdir -p /tmp/tg",
    "tar -xzf /tmp/tg.tar.gz -C /tmp/tg",
    "TG=$(dirname $(find /tmp/tg -maxdepth 3 -name server.js | head -n1))",
    "mv $TG /opt/tool-guide-mcp",
    "printf \"[Unit]\\nDescription=BOS-AI Tool Guide MCP Bridge :3001\\nAfter=network.target\\n\\n[Service]\\nType=simple\\nUser=root\\nWorkingDirectory=/opt/tool-guide-mcp\\nEnvironment=PORT=3001\\nEnvironment=AWS_REGION=ap-northeast-2\\nEnvironment=TOOL_GUIDE_LAMBDA=lambda-tool-guide-parser-seoul-dev\\nExecStart=/usr/local/bin/node /opt/tool-guide-mcp/server.js\\nRestart=always\\nRestartSec=5\\nStandardOutput=journal\\nStandardError=journal\\n\\n[Install]\\nWantedBy=multi-user.target\\n\" > /etc/systemd/system/tool-guide-mcp.service",
    "systemctl daemon-reload && systemctl enable tool-guide-mcp && systemctl restart tool-guide-mcp",
    "sleep 5",
    "curl -sf http://localhost:3001/health || (journalctl -u tool-guide-mcp -n 30 --no-pager; exit 1)"
  ]'
```

> 노드 경로는 RTL 브리지와 동일하게 `/usr/local/bin/node`. RTL `:3000`은 무손상.

## Kiro 작업 #5: nginx vhost 추가 (B 완료 후, SSM 무중단)

기존 `mcp-bossemi-ai.conf`를 그대로 미러링(직결 `:3001`, 전용 cert). 별도 파일로 추가 후 `nginx -t && nginx -s reload`.

```bash
aws ssm send-command \
  --region ap-northeast-2 \
  --document-name "AWS-RunShellScript" \
  --targets "Key=InstanceIds,Values=i-0d6c14b816debaec3" \
  --comment "Add toolguide.bossemi-ai.com vhost" \
  --parameters 'commands=[
    "set -e",
    "cat > /etc/nginx/conf.d/toolguide-bossemi-ai.conf <<EOF",
    "server {",
    "    listen 443 ssl;",
    "    http2 on;",
    "    server_name toolguide.bossemi-ai.com;",
    "    ssl_certificate     /etc/nginx/ssl/toolguide-bossemi-ai-fullchain.pem;",
    "    ssl_certificate_key /etc/nginx/ssl/toolguide-bossemi-ai-privkey.pem;",
    "    ssl_protocols TLSv1.2 TLSv1.3;",
    "    location / {",
    "        proxy_pass http://10.10.1.10:3001/;",
    "        proxy_http_version 1.1;",
    "        proxy_set_header Host \\$host;",
    "        proxy_set_header X-Forwarded-For \\$remote_addr;",
    "        proxy_set_header Upgrade \\$http_upgrade;",
    "        proxy_set_header Connection \"upgrade\";",
    "        proxy_read_timeout 3600s;",
    "    }",
    "}",
    "EOF",
    "nginx -t && nginx -s reload && echo reloaded"
  ]'
```

> `nginx -t` 실패 시 reload 안 됨 -> 기존(RTL) 설정 유지. 와일드카드 cert를 쓰면 위 cert 경로 2줄을
> 와일드카드 파일로 바꾼다.

---

## 검증 (end-to-end)

1. MCP EC2: `curl http://localhost:3001/health` -> `{"status":"ok","service":"tool-guide-mcp",...}`
2. nginx 경유(사내망): `curl https://toolguide.bossemi-ai.com/health` -> ok (cert 정상이면 `-k` 불필요)
3. Kiro `.kiro/settings/mcp.json`:
```json
{
  "mcpServers": {
    "bos-ai-tool-guide": {
      "url": "https://toolguide.bossemi-ai.com/mcp",
      "autoApprove": ["tool_guide_search"]
    }
  }
}
```
4. 실제 검증 질의(GIC720 multichip init 등)로 근거 인용 + "할루시네이션 0" 헤더 확인.

---

## 롤백

| 변경 | 롤백 |
|------|------|
| #2 IAM | `mcp_lambda_invoke`에서 ToolGuide statement 제거 후 apply |
| #3 SG | `aws_security_group_rule.mcp_inbound_toolguide` 제거 후 apply |
| #6 DNS | `toolguide.bossemi-ai.com` A레코드 DELETE |
| #1 브리지 | `systemctl disable --now tool-guide-mcp` (RTL :3000 무영향) |
| #5 nginx | `rm /etc/nginx/conf.d/toolguide-bossemi-ai.conf && nginx -s reload` |
| #7 LiteLLM | MCP 서버 등록 해제 |
