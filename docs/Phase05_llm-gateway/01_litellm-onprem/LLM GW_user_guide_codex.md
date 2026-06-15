# LLM Gateway 사용자 가이드 (Codex) — 계정 가입 & API 키 발급

> **Created:** 2026-06-08
> **Updated:** 2026-06-08
> **Purpose:** 일반 사용자가 초대 메일로 가입하고, 본인 API 키를 발급해 Codex CLI에 연결하기까지의 절차 안내 (OpenAI 모델 전용).
> **Spec / Project:** 운영 LiteLLM On-Prem
> **Status:** In Review
> **Owner:** IT/DevOps

---

## 0. 한눈에 보기

```
초대 메일 수신
   ▼
링크 클릭 → 비밀번호 설정 → 로그인
   ▼
'Virtual Keys' → '+ Create New Key' → 본인 키(sk-...) 생성
   ▼
Codex CLI 설정에 키 입력 → 사용
```

- 접속 주소: **http://llm.corp.bos-semi.com/ui**
- 로그인 ID: **본인 회사 이메일**
- 전제: **사내망(VPN) 연결** 상태여야 접속됩니다.

---

## 1. 계정 가입 (최초 1회)

1. **초대 메일** 을 받습니다 (발신: `BOS-AI LLM Gateway <bos.ai@bos-semi.com>`, 제목·본문 한/영 병기).
2. 메일 안의 **초대 링크** 를 클릭합니다.
3. **비밀번호를 설정** 합니다. (이 비밀번호로 이후 로그인)
4. 로그인하면 본인 대시보드가 열립니다.

> 메일을 못 받았거나 링크가 만료됐으면 IT/DevOps에 **재발송**을 요청하세요.
> 비밀번호를 잊으면 동일하게 재발송 요청 → 새 링크로 다시 설정합니다. (별도 "비밀번호 찾기" 없음)

---

## 2. API 키 발급

1. 로그인 후 좌측 메뉴 **`Virtual Keys`**.
2. **`+ Create New Key`** 클릭.
3. 항목 입력:
   - **Key Name (alias)**: 알아보기 쉬운 이름 (예: `codex-cli`)
   - **Models**: **비워두세요.** (비워두면 본인 팀에 허용된 모델이 자동 적용됩니다. 드롭다운에 개별 모델이 펼쳐 보여도 고를 필요 없습니다.)
   - 예산/만료/rate limit은 관리자 정책(월 $100)이 자동 적용
4. **Create** → `sk-...` 형태의 키가 **한 번만** 표시됩니다.
5. **즉시 복사해서 안전한 곳에 보관** 하세요. (창을 닫으면 다시 볼 수 없습니다 — 분실 시 새로 발급)

> 키는 OpenAI API Key와 동일한 형식(`sk-...`)이라, OpenAI 호환 도구에 그대로 넣으면 됩니다.

---

## 3. Codex CLI 연결

발급받은 키(`sk-...`)를 Codex 설정에 넣습니다.

`~/.codex/auth.json`:
```json
{
  "OPENAI_API_KEY": "sk-여기에_본인_키"
}
```

`~/.codex/config.toml`:
```toml
model = "gpt-5.1-codex-mini"
model_provider = "litellm"
model_reasoning_effort = "medium"

[model_providers.litellm]
name = "litellm"
base_url = "http://llm.corp.bos-semi.com/v1"
wire_api = "responses"
```

확인:
```bash
codex "간단한 파이썬 정렬 스크립트 만들어줘"
```

> `config.toml` 의 `openai_base_url`(단독)은 Codex가 무시합니다. 반드시 위처럼
> `model_provider` + `[model_providers.litellm]` 블록 + `wire_api = "responses"` 를 명시하세요.

---

## 4. 사용량 / 잔여 예산 확인

방법 1 — **UI**: 로그인 → `Usage` 메뉴에서 본인 사용량/모델별 내역 확인.

방법 2 — **CLI** (본인 키로):
```bash
curl -s "http://llm.corp.bos-semi.com/key/info?key=sk-본인키" \
  -H "Authorization: Bearer sk-본인키" | python3 -m json.tool
```
응답의 `spend`(사용액), `max_budget`(한도), `budget_duration`(리셋 주기) 확인.

---

## 5. 모델 선택 가이드 (OpenAI Codex 계열)

| 모델 | 용도 | 비용 | 속도 |
|------|------|------|------|
| gpt-5.1-codex-mini | 일상 코딩, 빠른 작업 | $ | ⚡ |
| gpt-5.1-codex-max | 깊은 추론 | $$ | 보통 |
| gpt-5.2-codex | frontier agentic 코딩 | $$ | 보통 |
| gpt-5.3-codex | CLI 기본 코딩 | $$ | 보통 |
| gpt-5.4 | 범용 최신 | $$ | 보통 |
| gpt-5.2 | frontier 범용 | $$ | 보통 |

> 위 6개(OpenAI)가 기본 제공 모델입니다.

---

## 6. 사용 한도 / Rate Limit

본인 키에는 폭주 방지를 위한 제한이 적용됩니다 (관리자 정책):

| 항목 | 값 | 의미 |
|------|-----|------|
| 월 예산 | $100 | 30일마다 리셋 |
| 분당 요청(RPM) | 30 | 분당 30회 |
| 분당 토큰(TPM) | 200,000 | 분당 20만 토큰 |
| 동시 요청 | 4 | 병렬 4개 |

> agent 자동화로 대량 호출 시 위 제한에 걸려 `429` 가 날 수 있습니다. 정상적인 작업엔 충분한 수준이며,
> 한도가 부족하면 IT/DevOps에 문의하세요.

---

## 7. 자주 묻는 질문 / 에러

| 상황 | 해결 |
|------|------|
| 초대 메일 못 받음 | IT/DevOps에 재발송 요청 |
| 비밀번호 잊음 | 재발송 요청 → 새 링크로 재설정 |
| 키를 잃어버림 | UI에서 새 키 생성 (기존 키는 삭제) |
| `401 Unauthorized` | 키 오타/만료 — 키 재확인 또는 재발급 |
| `429 Too Many Requests` | rate limit 또는 예산 초과 — 잠시 후 재시도/다음 달 대기/관리자 문의 |
| `400 invalid model` | 허용 안 된 모델 — 모델명 확인 (위 6개 사용) |
| 접속 자체가 안 됨 | 사내망(VPN) 연결 확인. `http://llm.corp.bos-semi.com/ui` |
| Codex가 OpenAI로 직행 | `config.toml`에 `model_provider="litellm"` 누락 — §3 재확인 |

---


## 8. 보안 수칙

- 발급받은 `sk-...` 키는 **개인 전용**. 타인과 공유 금지 (사용량이 본인 앞으로 집계됨).
- 키가 노출되면 즉시 UI에서 삭제하고 새로 발급하세요.
- 로그인 비밀번호와 API 키는 별개입니다.
