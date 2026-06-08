# LiteLLM On-Prem 운영 가이드 (Admin)

> **Created:** 2026-06-08
> **Updated:** 2026-06-08
> **Purpose:** swgr1sv1(192.128.10.102)에 Docker로 구축한 LiteLLM Gateway의 운영(팀/모델 그룹/사용자 온보딩/SMTP/백업/마이그레이션) 전체를 관리자가 수행하기 위한 실무 가이드.
> **Spec / Project:** `.kiro/specs/llm-gateway/` + 운영 LiteLLM On-Prem
> **Status:** In Review
> **Owner:** IT/DevOps

## Revision History

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|----------|--------|
| 2026-06-08 | 1.1 | 팀 멤버 키 생성 권한(`/team/permissions_update`), `auto_create_key:false`, rate limit 확정값(30/200K/4), 예산 전략(개인 $100 1개월), 모델 그룹 UI 동작, 메일 한영병기 반영 | IT/DevOps |
| 2026-06-08 | 1.0 | 초판 (on-prem Docker 전환) | IT/DevOps |

---

## 0. 아키텍처 요약

```
사용자/Codex (사내)
   │  http://llm.corp.bos-semi.com   (사내 DNS .101 -> 192.128.10.102)
   ▼  :80
nginx 컨테이너 (litellm-nginx, swgr1sv1)
   │  http://litellm:4000  (compose 내부 네트워크)
   ▼
litellm 컨테이너 (litellm-proxy)  ── postgres 컨테이너 (litellm-postgres, named volume)
   │ HTTPS :443
   ├─ OpenAI API
   └─ AWS Bedrock (Claude)
```

| 항목 | 값 |
|------|-----|
| 운영 서버 | swgr1sv1 = **192.128.10.102** (PoC server01=192.128.20.240 와 다름) |
| 배포 경로 | `/opt/litellm/` (compose 프로젝트, 자족적) |
| 진입 도메인 | `http://llm.corp.bos-semi.com` (HTTP, 사내망 전용) |
| 사용자 접속 포트 | **80** (nginx). 4000은 내부 전용 |
| LiteLLM 버전 | v1.87.1 (digest 핀) |
| DNS | 사내 BIND(.101 primary, .102 secondary), unbound @8853 forward |
| SMTP | office365 (`bos.ai@bos-semi.com` 발신) |

> **HTTP 사용 주의:** 내부망 전용이라 HTTP로 운영. 사용자 UI 로그인 시 비밀번호가 평문 전송된다. 추후 TLS 적용 지점은 nginx 컨테이너다.

---

## 1. 디렉토리 / 파일 구조 (`/opt/litellm`)

```
/opt/litellm/
├── docker-compose.yml         # postgres + litellm(digest pin) + nginx
├── .env                       # 시크릿: master key, OpenAI/Bedrock, SMTP, PROXY_BASE_URL (chmod 600)
├── config/
│   └── config.yaml            # 모델 목록 + access_groups + self-serve 정책 + smtp callback
├── nginx/
│   └── conf.d/litellm.conf    # :80 -> litellm:4000 리버스 프록시 (SSE 스트리밍 대응)
├── teams_created.csv          # team_alias,team_id 매핑 (온보딩 시 참조)
└── (백업) *.bak, *.bak2 ...
```

---

## 2. 일상 운영 명령

```bash
cd /opt/litellm

# 상태 확인
docker compose ps
docker logs litellm-proxy --tail 20

# config.yaml 변경 반영 (volume 마운트라 force-recreate 필요!)
docker compose up -d --force-recreate litellm
sleep 30 && docker logs litellm-proxy --tail 10 | grep "Uvicorn running"
curl -s http://localhost:4000/health/liveliness ; echo

# 전체 재기동
docker compose restart
```

> **중요:** `config.yaml`은 volume 마운트라 내용만 바꾸면 compose가 재시작을 안 한다.
> 반드시 `--force-recreate litellm` 로 컨테이너를 다시 띄워야 새 config가 로드된다.
> 적용 후 `docker inspect litellm-proxy --format '{{.State.StartedAt}}'` 로 재시작 시각을 확인할 것.

Master Key 확인:
```bash
grep LITELLM_MASTER_KEY /opt/litellm/.env | cut -d= -f2
```

---

## 3. 모델 & Access Group 관리

모델은 provider 단위 그룹으로 관리한다 (config.yaml `model_info.access_groups`):

| Access Group | 포함 모델 |
|--------------|-----------|
| `openai-models` | gpt-5.1-codex-mini/max, gpt-5.2-codex, gpt-5.3-codex, gpt-5.4, gpt-5.2 |
| `anthropic-models` | claude-haiku-4-5, sonnet-4-6, opus-4-6/4-7/4-8/4-1 |

팀/유저엔 모델명 대신 **그룹명**(`openai-models` 등)을 부여한다. 모델을 그룹에 추가/제거해도 팀·키는 수정 불필요.

모델 추가 시:
```yaml
# config/config.yaml 의 model_list 에 추가
- model_name: <새모델>
  litellm_params:
    model: <provider/모델ID>
    api_key: os.environ/OPENAI_API_KEY   # 또는 aws_region_name
  model_info:
    access_groups: ["openai-models"]      # 또는 anthropic-models
```
저장 후 `docker compose up -d --force-recreate litellm`.

검증:
```bash
MASTER_KEY=$(grep LITELLM_MASTER_KEY /opt/litellm/.env | cut -d= -f2)
curl -s http://localhost:4000/v1/models -H "Authorization: Bearer $MASTER_KEY" \
  | python3 -m json.tool | grep '"id"'
```

---

## 4. 팀 관리

조직별 팀이 권한의 단위다 (모델 그룹 + 예산 + MCP access group 상속).

현재 팀 (teams_created.csv 참조):
`hq_dv, hq_design1, hq_design2, hq_itdevops, hq_pmse, hq_aimm, hq_pdi, hq_coresw, hq_library, hq_archi, bhrc, bhrc_design1/2, bhrc_dv1/2/3, bhrc_pdi1/2, bhrc_dft, bhrc_core` (20개)

팀 일괄 생성 / 추가:
```bash
MASTER_KEY=$(grep LITELLM_MASTER_KEY /opt/litellm/.env | cut -d= -f2)
curl -s -X POST http://localhost:4000/team/new \
  -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"team_alias":"<팀이름>","models":["openai-models"]}' \
  | python3 -m json.tool | grep -E '"team_id"|"team_alias"'
```

팀에 Claude 추가 (특정 팀만):
```bash
curl -s -X POST http://localhost:4000/team/update \
  -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"team_id":"<TEAM_ID>","models":["openai-models","anthropic-models"]}'
```

팀 목록:
```bash
curl -s http://localhost:4000/team/list -H "Authorization: Bearer $MASTER_KEY" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); d=d if isinstance(d,list) else d.get('teams',d); [print(t.get('team_alias'),t.get('team_id'),t.get('models')) for t in d]"
```

### 4.1 팀 멤버 키 생성 권한 (필수 — 안 주면 멤버가 키 못 만듦)

> **함정:** 팀에 `team_member_permissions` 가 없으면 멤버가 키 생성 시
> `Team member does not have permission to generate key for this team` 에러가 난다.
> 그리고 **이 권한은 `/team/update` 로는 안 먹고, 전용 엔드포인트 `/team/permissions_update` 로만** 설정된다.

허용 가능한 permission 문자열 확인:
```bash
MASTER_KEY=$(grep LITELLM_MASTER_KEY /opt/litellm/.env | cut -d= -f2)
curl -s "http://localhost:4000/team/permissions_list?team_id=<TEAM_ID>" \
  -H "Authorization: Bearer $MASTER_KEY" | python3 -m json.tool
# all_available_permissions 에서 정확한 문자열 확인 (/key/generate, /key/list, /key/info 등)
```

전체 팀 일괄 적용 (teams_created.csv 기반):
```bash
MASTER_KEY=$(grep LITELLM_MASTER_KEY /opt/litellm/.env | cut -d= -f2)
while IFS=, read -r alias tid; do
  [ "$alias" = "team_alias" ] && continue; [ -z "$tid" ] && continue
  curl -s -X POST http://localhost:4000/team/permissions_update \
    -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" \
    -d "{\"team_id\":\"$tid\",\"team_member_permissions\":[\"/key/generate\",\"/key/list\",\"/key/info\"]}" >/dev/null \
    && echo "OK: $alias" || echo "FAIL: $alias"
done < /opt/litellm/teams_created.csv
```

> 신규 팀은 config.yaml 의 `default_team_params.team_member_permissions` 로 자동 적용된다.
> 단 **기존 팀엔 소급 안 되므로** 위 일괄 명령으로 적용해야 한다.

검증:
```bash
curl -s "http://localhost:4000/team/permissions_list?team_id=<TEAM_ID>" \
  -H "Authorization: Bearer $MASTER_KEY" | python3 -m json.tool | grep -A4 '"team_member_permissions"'
```

---

## 5. 사용자 온보딩 (핵심 — 시스템화)

### 5.1 운영 모델

- **자동화 스크립트 `onboard_users.py`** 가 `users.csv` 명단을 읽어 **없는 유저만** 생성 + 초대링크 발급 + office365 메일 발송 (멱등).
- 초기 200명 벌크든 신규 1명이든 **같은 도구**. `users.csv`가 단일 원천.

### 5.2 LiteLLM 메일 동작 (중요 — 함정)

> **개별 `/user/new` API 와 `/invitation/new` API 는 메일을 발송하지 않는다** (유저/링크 객체만 생성). LiteLLM의 알려진 동작(GitHub #13961, #3934).
> 따라서 메일 발송은 **(a) UI Bulk Invite** 또는 **(b) `onboard_users.py`가 office365로 직접 발송** 으로 한다. 본 운영은 **(b)** 를 표준으로 한다 (통제력·재현성 우수).

### 5.2.1 자동 키 생성 끄기 (auto_create_key=false)

> **함정:** `/user/new` 는 기본적으로 유저 생성 시 키를 1개 자동 발급한다(`auto_create_key` 기본 True).
> 그러면 "자동 키 1개 + 유저가 직접 만든 키"가 공존해 혼선이 생긴다.
> self-serve 취지(유저가 로그인 후 직접 키 발급)에 맞춰 **`auto_create_key: false`** 로 끈다.
> `onboard_users.py` 의 `create_user` payload에 이미 반영됨 → 유저만 생성, 키는 본인이 발급.

기존에 잘못 생성된 자동 키 정리:
```bash
MASTER_KEY=$(grep LITELLM_MASTER_KEY /opt/litellm/.env | cut -d= -f2)
# alias 없고 team_id NULL 인 자동 키 후보 확인 (litellm-dashboard 세션 토큰은 제외됨)
docker exec litellm-postgres psql -U litellm -d litellm -c \
  "SELECT token, user_id FROM \"LiteLLM_VerificationToken\" WHERE team_id IS NULL AND key_alias IS NULL;"
# 확인된 token 으로 삭제
curl -s -X POST http://localhost:4000/key/delete \
  -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"keys":["<token1>","<token2>"]}' | python3 -m json.tool
```

### 5.2.2 초대 메일 본문 (한/영 병기)

`onboard_users.py` 의 `EMAIL_SUBJECT` / `EMAIL_BODY_TMPL` 은 한국어/영어 병기로 작성됨.
발신자는 `BOS-AI LLM Gateway <bos.ai@bos-semi.com>`. 본문 문구 변경 시 이 두 상수만 수정.

### 5.3 신규 사용자 추가 절차

1. `users.csv` 맨 아래에 줄 추가 (날짜 주석과 함께):
   ```
   # --- 2026-06-15 추가 (신규 입사) ---
   lee.younghee@bos-semi.com,hq_archi
   ```
2. 실행 (서버 또는 API 접근 가능한 곳에서):
   ```bash
   export LITELLM_MASTER_KEY=$(grep LITELLM_MASTER_KEY /opt/litellm/.env | cut -d= -f2)
   export SMTP_PASSWORD='<bos.ai 계정 비번>'
   py onboard_users.py users.csv --teams-map /opt/litellm/teams_created.csv
   ```
   - 기존 유저는 자동 skip, 신규만 생성 + 메일 발송
   - 결과: `onboard_results.csv`(링크 백업), 실패 시 `onboard_failed.csv`

### 5.4 초대 링크 형식 확인 (최초 1회)

`onboard_users.py` 의 `INVITATION_URL_TEMPLATE` 은 UI의 "copy invitation link" 실제값과 일치해야 한다.
UI(Internal Users -> 유저 -> invitation link 복사)에서 형식 확인 후 스크립트 상수 수정.

### 5.5 비밀번호 분실 / 재초대

비밀번호 재설정 기능은 없다. **invitation 재발급**으로 처리:
```bash
py onboard_users.py users.csv --teams-map /opt/litellm/teams_created.csv --resend-pending
```
또는 특정 유저만 UI에서 invitation link 재생성 후 전달.

> 보안: invitation link는 1회용으로 취급. 비번 설정 후 만료시키는 게 안전 (재사용 시 비번 변경 가능).

---

## 6. 사용자 / 키 관리

### 6.1 핵심 주의 — user_id는 UUID다

`user/info`, `user/delete` 등은 **이메일이 아니라 user_id(UUID)** 를 받는다. 이메일로 조회하면 404가 난다(없어서가 아님).

유저 조회 / user_id 확인:
```bash
MASTER_KEY=$(grep LITELLM_MASTER_KEY /opt/litellm/.env | cut -d= -f2)
docker exec litellm-postgres psql -U litellm -d litellm -c \
  "SELECT user_id, user_email, user_role FROM \"LiteLLM_UserTable\" WHERE user_email LIKE '%<검색어>%';"
```

### 6.2 유저 삭제 (퇴사자)

```bash
# 1) UUID 확인 (위 SQL)
# 2) UUID로 삭제 (UI Internal Users 에서 삭제해도 DB까지 정리됨)
curl -s -X POST http://localhost:4000/user/delete \
  -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" \
  -d '{"user_ids":["<UUID>"]}' | python3 -m json.tool
```

> 유저 삭제는 DB까지 정상 삭제된다(별도 DB 클리닝 불필요). 단, 유저가 만든 **virtual key는 별도로 남을 수 있으므로** 삭제 시 연결된 키도 확인/정리한다.

### 6.3 사용량 / 예산 조회

```bash
# 특정 키 사용량
curl -s "http://localhost:4000/key/info?key=sk-xxxx" -H "Authorization: Bearer $MASTER_KEY" \
  | python3 -m json.tool | grep -E '"spend"|"max_budget"|"team_id"'

# 유저별/팀별 spend 는 UI Usage 대시보드에서 확인 (http://llm.corp.bos-semi.com/ui)
```

### 6.4 self-serve 정책 & 예산/Rate Limit (config.yaml)

**예산 (조건: 1개월 개인 기준 운영)**
- `max_internal_user_budget: 100` / `internal_user_budget_duration: 30d` — 1인당 월 $100
- 팀 예산(`team max_budget`)은 **설정 안 함** → 개인 $100만 적용. 개인/팀 예산은 **독립**(자동 합산/풀링 아님).
- **전략**: 1개월간 개인 $100로 운영 → 사용량 데이터 확보 → 필요 시 팀 예산(풀) 전환 검토.

**Rate Limit (agent 폭주 억제 — `default_key_generate_params`)**
| 항목 | 기본값 | 상한(`upperbound`) | 근거 |
|------|--------|--------------------|------|
| rpm_limit | 30 | 60 | 분당 요청. 사람+agent 충분, 연타 폭주 억제 |
| tpm_limit | 200,000 | 500,000 | 분당 토큰. 분당 비용 상한 효과 (하루치 단번 소진 방지) |
| max_parallel_requests | 4 | 8 | 동시 요청. agent 병렬 폭주 억제 |
| max_budget | 100 | 100 | 키 1개 예산 = 유저 예산과 일치 (키 $10에서 막히던 혼란 제거) |

> 월 $100÷30일 ≈ 하루 $3.3가 정상 페이스. tpm 20만이면 분당 비용이 제한돼 agent가 하루치를 몇 분에 태우는 걸 막는다. 1개월 운영 후 빡빡하면 상향.

**모델 노출 (그룹만)**
- `default_internal_user_params.models: ["openai-models"]` / `default_key_generate_params.models: ["openai-models"]` — 개별 모델명 대신 그룹만.
- **UI 동작 주의:** UI 키 생성 드롭다운은 그룹을 개별 모델로 **펼쳐서** 보여준다(LiteLLM 기본 동작, config로 못 막음). 단 권한은 팀/유저 `models`로 제한되므로 기능/보안 문제는 없다.
- **권장:** 유저는 키 생성 시 **Models를 비워두면** 팀 권한이 자동 상속된다 → 드롭다운 고민 불필요.

**역할 (role)**
- `default_internal_user_params.user_role: internal_user`. **단, UI/API에서 role을 명시 지정하면 default보다 우선**된다.
- **함정:** UI `+ Invite User` 는 기본 role이 `internal_user_viewer`(키 생성 불가)로 들어가는 경우가 있다. **`onboard_users.py` 는 role을 `internal_user`로 명시**하므로 이 함정을 회피한다 → 스크립트 온보딩 권장.

---

## 7. SMTP (office365)

`.env` 설정:
```
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_TLS=True
SMTP_USERNAME=bos.ai@bos-semi.com       # 로그인 계정
SMTP_SENDER_EMAIL=bos.ai@bos-semi.com   # 발신 주소 = 로그인 계정과 동일해야 함!
SMTP_PASSWORD=<bos.ai 계정 비번>
EMAIL_INCLUDE_API_KEY=false
```
config.yaml: `litellm_settings.callbacks: ["smtp_email"]`

> **발신주소 = 로그인 계정 필수.** `SMTP_USERNAME(system@)` 으로 로그인하면서 `SENDER(bos.ai@)` 로 보내면
> office365가 `554 SendAsDenied` 로 거부한다. 다른 주소로 발신하려면 Exchange에서 "Send As" 권한 부여 필요.

연결/인증 테스트:
```bash
docker exec litellm-proxy python3 -c "
import smtplib, os
s=smtplib.SMTP('smtp.office365.com',587,timeout=15); s.ehlo(); s.starttls(); s.ehlo()
s.login(os.environ['SMTP_USERNAME'], os.environ['SMTP_PASSWORD']); print('LOGIN OK'); s.quit()
"
```

---

## 8. 백업 / 복구

상태는 전부 postgres(named volume `postgres_data`)에 있다 (키/유저/사용량/모델설정).

```bash
# 백업
docker compose exec postgres pg_dump -U litellm litellm > /opt/litellm/backup_$(date +%Y%m%d).sql

# 복구
docker compose exec -T postgres psql -U litellm litellm < /opt/litellm/backup_YYYYMMDD.sql
```
`.env`, `config/`, `nginx/`, `docker-compose.yml`, `teams_created.csv` 도 함께 백업한다.

---

## 9. 마이그레이션 (다른 서버로 이전)

DNS 이름이 IP를 추상화하므로 "DNS 한 줄 + DB 덤프"로 이전한다.

```
사전: DNS TTL을 짧게(300s) 낮춤. 이미지 digest 핀 확인.
1. 새 호스트: Docker 확인, /opt/litellm 전체 rsync
2. DB 백업:  docker compose exec postgres pg_dump -U litellm litellm > litellm.sql
3. 전송:     litellm.sql + /opt/litellm/{.env,config,nginx,docker-compose.yml,teams_created.csv}
4. 복원:     docker compose up -d postgres
             docker compose exec -T postgres psql -U litellm litellm < litellm.sql
             docker compose up -d litellm nginx
5. 검증:     새 IP로 직접 curl (DNS 안 바꾼 상태) -> /health, /v1/models, 키 1개 호출
6. 컷오버:   .101 BIND zone 의 llm A레코드를 새 IP로 변경 + serial 증가 + rndc reload
             (반영 안 되면 unbound-control flush llm.corp.bos-semi.com)
7. 검증:     llm.corp.bos-semi.com 으로 정상 확인
8. 정리:     유예 후 구 호스트 docker compose down
롤백: 6번 DNS를 구 IP로 되돌림 (구 스택 유예기간 유지)
```

---

## 10. DNS 운영 메모

- `corp.bos-semi.com` zone: **.101 BIND primary** (`/var/cache/bind/corp.bos-semi.com.zone`, `type master`, `allow-update none` -> 수동 편집), .102 secondary
- 클라이언트는 .101 unbound(:53) -> @8853 forward -> BIND
- 레코드 변경: zone 파일 수정 + **SOA serial 증가(YYYYMMDDNN)** + `rndc reload corp.bos-semi.com`
- 캐시 잔존 시: `unbound-control flush <도메인>` (TTL 1H)
- **알려진 이슈**: secondary(.102) zone transfer 가 notify 포트 비대칭(.101 -> .102:53 notify vs secondary masters :8853)으로 자동 전파 안 됨. 수동 `rndc retransfer corp.bos-semi.com` 로 동기화. (별도 개선 과제)

---

## 11. 트러블슈팅 빠른 참조

| 증상 | 원인 | 대응 |
|------|------|------|
| `502 Bad Gateway` | litellm 부팅 중 (recreate 직후) | 30초 대기, `docker logs`에 Uvicorn 확인 |
| config 변경 무반영 | volume이라 재시작 안 됨 | `up -d --force-recreate litellm` + StartedAt 확인 |
| 도메인 resolve 안 됨(.102 자신) | .102가 .101 DNS 미사용 | 정상. 서비스 동작 무관 (클라이언트는 .101로 resolve) |
| 메일 안 감 | user/new는 발송 안 함 / SendAsDenied | onboard_users.py 직접 발송 / 발신=로그인계정 통일 |
| 유저 키 생성 막힘 | role=viewer 또는 models 비어있음 | role=internal_user + 팀(openai-models) 소속 |
| 키 생성 시 "Team member does not have permission" | 팀에 team_member_permissions 없음 | `/team/permissions_update` 로 `/key/generate` 부여 (§4.1) |
| 유저당 키가 2개(자동+본인) | user/new 의 auto_create_key 기본 True | `auto_create_key:false` (§5.2.1), 기존 자동키 정리 |
| 메일 본문 비번 깨짐 | 비번 복붙 시 비-ASCII 혼입 | .env 비번 직접 타이핑, 따옴표로 감쌈 |
| 드롭다운에 개별 모델 다 보임 | LiteLLM UI가 그룹을 펼침(기본동작) | 무해. 유저는 Models 비워두고 생성 권장 |
| user/info 404 | 이메일로 조회함 | user_id(UUID)로 조회 |

---

## 부록 A. 초기 구축 검증 완료 항목 (2026-06-08)

- [x] Docker compose (postgres/litellm/nginx) 기동
- [x] 모델 12종 (OpenAI 6 + Bedrock Claude 6) 라우팅
- [x] nginx :80 -> litellm:4000, `http://llm.corp.bos-semi.com` 클라이언트 접속
- [x] access_groups (openai-models / anthropic-models)
- [x] 팀 20개 생성
- [x] self-serve 정책 ($100/internal_user)
- [x] SMTP office365 (bos.ai@ 발신, LOGIN/SENT OK)
- [x] 팀 멤버 키 생성 권한 (`/team/permissions_update`, 20개 팀 일괄)
- [x] onboard_users.py: auto_create_key=false + 한영 병기 메일 + 멱등(DB 조회)
- [x] rate limit (rpm30/tpm200K/parallel4) + 모델 그룹 노출
- [ ] onboard_users.py 벌크 발송 실검증 (서버 스크립트 교체 후)
- [ ] 자가발급 키로 모델 호출 end-to-end 검증
- [ ] 4000 호스트 노출 제거 (127.0.0.1 바인딩, 보안 정리)
