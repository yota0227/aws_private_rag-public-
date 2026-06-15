#!/usr/bin/env python3
"""
onboard_users.py - LiteLLM 사용자 온보딩 자동화 (멱등)

목적:
  users.csv(email, team_name) 명단을 읽어
    1) 없는 유저만 internal_user 로 생성 (팀 소속 + 예산 + 모델)
    2) 각 유저별 초대 링크(invitation) 발급
    3) office365 SMTP 로 개인별 초대 메일 발송
  이미 가입한 유저는 건너뛴다 -> 초기 벌크/신규 추가 동일 도구.

사용:
  # 환경변수로 master key, smtp 비번 주입 (셸 히스토리에 안 남게)
  export LITELLM_MASTER_KEY=sk-xxxx
  export SMTP_PASSWORD=xxxx
  py onboard_users.py users.csv --teams-map teams_created.csv

  # 메일 발송 없이 생성/링크만 (드라이런)
  py onboard_users.py users.csv --teams-map teams_created.csv --no-email

  # 미가입자에게 링크 재발송
  py onboard_users.py users.csv --teams-map teams_created.csv --resend-pending

주의:
  - INVITATION_URL_TEMPLATE 은 UI의 "copy invitation link" 에서 확인한
    실제 형식으로 맞출 것 (LiteLLM 버전마다 다름).
  - 표준 라이브러리만 사용 (requests 불필요). Python 3.9+.
"""

import argparse
import csv
import json
import os
import smtplib
import subprocess
import sys
import time
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.utils import formataddr

# 환경 설정 (필요 시 수정)
LITELLM_BASE = os.environ.get("LITELLM_BASE", "http://localhost:4000")
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "http://llm.corp.bos-semi.com")

# 초대 링크 형식 - UI의 invitation link 복사값으로 검증/수정할 것
INVITATION_URL_TEMPLATE = "{public}/ui?invitation_id={invite_id}"

# 신규 유저 기본 정책 (config.yaml 의 default_internal_user_params 와 일치)
DEFAULT_MAX_BUDGET = 100
DEFAULT_BUDGET_DURATION = "30d"
DEFAULT_MODELS = ["openai-models"]  # 팀에서 상속되지만 안전하게 명시

# SMTP (office365) - .env 와 동일 값
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.office365.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "bos.ai@bos-semi.com")
SMTP_SENDER = os.environ.get("SMTP_SENDER_EMAIL", SMTP_USERNAME)
SMTP_SENDER_NAME = os.environ.get("SMTP_SENDER_NAME", "BOS-AI LLM Gateway")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")  # 필수 (--no-email 이면 생략 가능)

MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY")

# 이메일 -> user_id 조회용 postgres 컨테이너 (find_user 가 사용)
PG_CONTAINER = os.environ.get("PG_CONTAINER", "litellm-postgres")
PG_USER = os.environ.get("PG_USER", "litellm")
PG_DB = os.environ.get("PG_DB", "litellm")

EMAIL_SUBJECT = "[BOS-AI] LLM Gateway 계정 초대 / Account Invitation - 비밀번호를 설정하세요 / Set your password"
EMAIL_BODY_TMPL = """\
안녕하세요,
Hello,

BOS-AI LLM Gateway 사용자 계정이 생성되었습니다.
A BOS-AI LLM Gateway user account has been created for you.

아래 링크에서 비밀번호를 설정한 뒤 로그인하면, 본인 API 키를 직접 발급할 수 있습니다.
Set your password via the link below, then log in to issue your own API key.

  초대 링크 / Invitation link: {invite_url}

[다음 단계 / Next steps]
  1. 위 링크 접속 -> 비밀번호 설정 -> 로그인
     Open the link above -> set a password -> log in
  2. 좌측 'Virtual Keys' -> '+ Create New Key' 로 본인 키(sk-...) 생성
     Go to 'Virtual Keys' -> '+ Create New Key' to create your key (sk-...)
  3. Codex CLI 등에 키 입력 (사용자 가이드 참조)
     Put the key into Codex CLI, etc. (see the User Guide)

- 접속 주소 / URL: {public}/ui
- 월 사용 한도 / Monthly budget: ${budget}
- 문의 / Contact: IT/DevOps

이 메일은 자동 발송되었습니다.
This is an automated message.
"""


def api(method, path, payload=None):
    """LiteLLM admin API 호출 (master key)."""
    url = f"{LITELLM_BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {MASTER_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"error": body}
    except Exception as e:
        return 0, {"error": repr(e)}


def load_team_map(path):
    """teams_created.csv (team_alias,team_id) -> dict."""
    m = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#") or row[0] == "team_alias":
                continue
            if len(row) >= 2:
                m[row[0].strip()] = row[1].strip()
    return m


def load_users(path):
    """users.csv (email,team_name) -> list[(email, team_name)] (주석/빈줄 무시)."""
    users = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row:
                continue
            first = row[0].strip()
            if not first or first.startswith("#") or first == "user_email":
                continue
            email = first
            team = row[1].strip() if len(row) >= 2 and row[1].strip() else ""
            users.append((email, team))
    return users


def find_user(email):
    """이메일로 기존 user_id 조회.
    LiteLLM user_id 는 UUID 이고 이메일로 조회하는 API가 없으므로
    postgres LiteLLM_UserTable 을 직접 조회한다.
    -> user_id(str) 또는 None.
    """
    sql = (
        "SELECT user_id FROM \"LiteLLM_UserTable\" "
        "WHERE user_email = '%s' LIMIT 1;" % email.replace("'", "''")
    )
    try:
        out = subprocess.run(
            ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB,
             "-tA", "-c", sql],
            capture_output=True, text=True, timeout=20,
        )
        uid = out.stdout.strip().splitlines()
        if uid and uid[0].strip():
            return uid[0].strip()
    except Exception as e:
        print(f"    (find_user 조회 실패: {e!r})")
    return None


def create_user(email, team_id):
    payload = {
        "user_email": email,
        "user_role": "internal_user",
        "max_budget": DEFAULT_MAX_BUDGET,
        "budget_duration": DEFAULT_BUDGET_DURATION,
        "models": DEFAULT_MODELS,
        "auto_create_key": False,   # 유저만 생성, 키는 본인이 로그인 후 직접 발급(self-serve)
    }
    if team_id:
        payload["teams"] = [team_id]
    status, body = api("POST", "/user/new", payload)
    if status == 200:
        return body.get("user_id"), None
    if status in (409, 400):
        uid = find_user(email)
        if uid:
            return uid, "exists"
    return None, f"{status}:{body.get('error') or body}"


def new_invitation(user_id):
    status, body = api("POST", "/invitation/new", {"user_id": user_id})
    if status == 200:
        return body.get("id")
    return None


def send_invite_email(to_email, invite_url, smtp):
    body = EMAIL_BODY_TMPL.format(
        invite_url=invite_url, public=PUBLIC_BASE, budget=DEFAULT_MAX_BUDGET
    )
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = EMAIL_SUBJECT
    msg["From"] = formataddr((SMTP_SENDER_NAME, SMTP_SENDER))
    msg["To"] = to_email
    smtp.sendmail(SMTP_SENDER, [to_email], msg.as_string())


def open_smtp():
    s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
    s.ehlo()
    s.starttls()
    s.ehlo()
    s.login(SMTP_USERNAME, SMTP_PASSWORD)
    return s


def main():
    ap = argparse.ArgumentParser(description="LiteLLM 사용자 온보딩 (멱등)")
    ap.add_argument("users_csv", help="user_email,team_name 명단 CSV")
    ap.add_argument("--teams-map", default="teams_created.csv",
                    help="team_alias,team_id 매핑 CSV")
    ap.add_argument("--no-email", action="store_true", help="메일 발송 생략(생성/링크만)")
    ap.add_argument("--resend-pending", action="store_true",
                    help="기존 유저에게도 링크 재발송")
    args = ap.parse_args()

    if not MASTER_KEY:
        sys.exit("ERROR: 환경변수 LITELLM_MASTER_KEY 가 필요합니다.")
    if not args.no_email and not SMTP_PASSWORD:
        sys.exit("ERROR: 메일 발송엔 환경변수 SMTP_PASSWORD 가 필요합니다. (--no-email 로 생략 가능)")

    team_map = load_team_map(args.teams_map)
    users = load_users(args.users_csv)
    print(f"명단 {len(users)}명, 팀 매핑 {len(team_map)}개 로드")

    smtp = None
    if not args.no_email:
        try:
            smtp = open_smtp()
            print(f"SMTP 로그인 OK ({SMTP_USERNAME})")
        except Exception as e:
            sys.exit(f"ERROR: SMTP 로그인 실패 - {e!r}")

    sent, skipped, failed = 0, 0, []
    results = []

    for email, team_name in users:
        team_id = team_map.get(team_name, "")
        if team_name and not team_id:
            print(f"  ! {email}: 팀 '{team_name}' 매핑 없음 -> 팀 없이 진행")

        existing = find_user(email)
        if existing:
            uid, note = existing, "exists"
        else:
            uid, note = create_user(email, team_id)
            if not uid:
                print(f"  X {email}: 생성 실패 ({note})")
                failed.append((email, note))
                continue

        if note == "exists" and not args.resend_pending:
            skipped += 1
            print(f"  = {email}: 이미 존재 -> skip")
            continue

        invite_id = new_invitation(uid)
        if not invite_id:
            print(f"  X {email}: invitation 발급 실패")
            failed.append((email, "invitation_failed"))
            continue
        invite_url = INVITATION_URL_TEMPLATE.format(public=PUBLIC_BASE, invite_id=invite_id)
        results.append((email, note or "new", invite_url))

        if smtp:
            try:
                send_invite_email(email, invite_url, smtp)
                sent += 1
                print(f"  O {email}: {note or 'new'} -> 메일 발송 OK")
                time.sleep(0.3)
            except Exception as e:
                print(f"  X {email}: 메일 발송 실패 - {e!r}")
                failed.append((email, f"send_failed:{e!r}"))
        else:
            print(f"  O {email}: {note or 'new'} -> 링크 {invite_url}")

    if smtp:
        try:
            smtp.quit()
        except Exception:
            pass

    with open("onboard_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_email", "status", "invite_url"])
        w.writerows(results)

    print("\n==== 요약 ====")
    print(f"  메일발송: {sent}  skip(기존): {skipped}  실패: {len(failed)}")
    print(f"  링크 백업: onboard_results.csv")
    if failed:
        with open("onboard_failed.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([["user_email", "reason"]] + failed)
        print(f"  실패 명단: onboard_failed.csv")


if __name__ == "__main__":
    main()
