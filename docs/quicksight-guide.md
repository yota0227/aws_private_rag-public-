# Amazon Quick (QuickSight) 운영 가이드

> BOS-AI Private RAG 인프라 통합 환경 기준

---

## 목차

1. [개요](#1-개요)
2. [Admin 가이드 — 사용자 추가/제거](#2-admin-가이드--사용자-추가제거)
3. [User 가이드 — Quick 접속 방법](#3-user-가이드--quick-접속-방법)
4. [역할별 기능 안내](#4-역할별-기능-안내)
5. [Obot 채팅에서 Quick 사용](#5-obot-채팅에서-quick-사용)
6. [운영자 모니터링 가이드](#6-운영자-모니터링-가이드)
7. [트러블슈팅](#7-트러블슈팅)

---

## 1. 개요

### 아키텍처 요약

BOS-AI Quick은 완전 Private 환경에서 운영됩니다. 모든 트래픽은 VPN → VPC Endpoint 경로를 통해 AWS 내부 네트워크에서만 흐릅니다.

```
온프레미스 PC
    │
    ├─ VPN (스플릿 터널링)
    │       │
    │       ├─ quick.rag.corp.bos-semi.com
    │       │       → Route53 Private DNS
    │       │       → Quick Website VPC Endpoint (PrivateLink)
    │       │       → Quick 웹 콘솔
    │       │
    │       └─ Quick API 호출
    │               → Quick API VPC Endpoint (PrivateLink)
    │               → Quick Service
    │
    └─ CloudFront (정적 자산: CSS/JS)
            → 인터넷 직접 접근 (스플릿 터널링으로 자동 처리)
```

### 접속 URL

| 용도 | URL |
|------|-----|
| Quick 웹 콘솔 | `https://quick.rag.corp.bos-semi.com` |
| AWS SSO 포털 | `https://bos-semi.awsapps.com/start` |

### 역할 구조

| IAM Identity Center 그룹 | Quick 역할 | 권한 수준 |
|--------------------------|-----------|----------|
| `QS_Admin_Users` | ADMIN | 계정/사용자/데이터소스 관리 |
| `QS_Author_Users` | AUTHOR | 대시보드 생성/편집 |
| `QS_Viewer_Users` | READER | 대시보드 조회만 |

---

## 2. Admin 가이드 — 사용자 추가/제거

### 전제 조건

- VPN 연결 상태
- IAM Identity Center 관리자 권한 또는 내부 포털 승인 권한

---

### 2.1 사용자 추가 (자동화 경로 — 권장)

RBAC Pipeline을 통한 자동화 흐름입니다. 일반적인 경우 이 방법을 사용하세요.

**흐름:**
```
내부 포털 또는 Jira 승인 요청
    → Webhook 수신 (RBAC Pipeline)
    → SQS 큐 → Provisioner Lambda 실행
    → IAM Identity Center 그룹 자동 추가
        (QS_Admin_Users / QS_Author_Users / QS_Viewer_Users)
    → Quick 계정에 자동 동기화 (수 분 이내)
    → 사용자 Quick 접속 가능
```

**요청 시 필요 정보:**
- 사용자 이메일 (IAM Identity Center 등록 이메일)
- 부여할 역할: `quicksight-admin` / `quicksight-author` / `quicksight-viewer`

---

### 2.2 사용자 추가 (수동 경로 — 긴급 시)

RBAC Pipeline이 동작하지 않거나 긴급하게 권한을 부여해야 할 때 사용합니다.

**단계:**

1. VPN 연결 확인
2. AWS Console 접속 → IAM Identity Center
3. 좌측 메뉴 → **그룹** 클릭
4. 해당 그룹 선택:
   - 관리자 권한: `QS_Admin_Users`
   - 작성자 권한: `QS_Author_Users`
   - 조회 권한: `QS_Viewer_Users`
5. **그룹에 사용자 추가** 클릭
6. 사용자 이메일로 검색 후 추가
7. Quick 동기화 대기 (최대 5분)

> **주의**: 수동 추가 후 RBAC Pipeline의 Reconciler Lambda가 다음 일간 실행 시 드리프트를 감지할 수 있습니다. 수동 추가 사실을 RBAC 담당자에게 공유하세요.

---

### 2.3 사용자 제거

**자동화 경로:**
- 내부 포털/Jira에서 권한 제거 요청 → RBAC Pipeline 자동 처리

**수동 경로:**
1. AWS Console → IAM Identity Center → 그룹
2. 해당 그룹에서 사용자 선택 → **그룹에서 제거**
3. Quick 동기화 대기 (최대 5분)
4. 사용자의 Quick 세션은 즉시 만료되지 않을 수 있음 — 즉시 차단이 필요하면 Quick Console에서 해당 사용자 비활성화 추가 조치 필요

---

### 2.4 동기화 상태 확인

IAM Identity Center 그룹 변경 후 Quick에 반영되지 않는 경우:

```bash
# CloudWatch Logs에서 Provisioner Lambda 실행 로그 확인
aws logs filter-log-events \
  --log-group-name /aws/lambda/rbac-provisioner \
  --filter-pattern "quicksight" \
  --region ap-northeast-2
```

또는 AWS Console → CloudWatch → 로그 그룹 → `/aws/lambda/rbac-provisioner` 에서 확인

---

## 3. User 가이드 — Quick 접속 방법

### 전제 조건

- [ ] VPN 클라이언트 설치 및 설정 완료
- [ ] IAM Identity Center 계정 활성화 (초대 이메일 수락)
- [ ] `QS_Admin_Users`, `QS_Author_Users`, `QS_Viewer_Users` 중 하나의 그룹에 추가됨

---

### 3.1 VPN 연결

Quick 접속 전 반드시 VPN을 연결해야 합니다.

1. VPN 클라이언트 실행
2. BOS-Semi 프로파일 선택 후 연결
3. 연결 상태 확인 (스플릿 터널링 방식 — AWS 트래픽만 VPN 경유)

> **참고**: VPN 연결 후 `quick.rag.corp.bos-semi.com` DNS가 Private IP로 해석됩니다. VPN 없이는 접속 불가합니다.

---

### 3.2 Quick 웹 콘솔 접속

1. 브라우저에서 `https://quick.rag.corp.bos-semi.com` 접속
2. **AWS IAM Identity Center로 로그인** 클릭
3. SSO 포털(`https://bos-semi.awsapps.com/start`)로 리다이렉트
4. 회사 이메일과 비밀번호 입력
5. MFA 인증 (설정된 경우)
6. Quick 대시보드 화면 진입

**접속 흐름 요약:**
```
브라우저 → quick.rag.corp.bos-semi.com
    → VPN → Route53 Private DNS
    → Quick Website VPC Endpoint
    → Quick 웹 콘솔 로드
    → IAM Identity Center SSO 로그인
    → 역할에 따른 대시보드 접근
```

> **참고**: 페이지 로드 시 CSS/JS 등 정적 자산은 CloudFront를 통해 인터넷에서 직접 로드됩니다. 스플릿 터널링 환경에서는 자동으로 처리되므로 별도 설정이 필요 없습니다.

---

### 3.3 첫 접속 시 확인 사항

- 역할에 맞는 메뉴가 표시되는지 확인
  - ADMIN: 관리 메뉴 포함
  - AUTHOR: 대시보드 생성/편집 버튼 표시
  - READER: 대시보드 조회만 가능
- RAG 데이터 대시보드가 목록에 표시되는지 확인
- 데이터가 표시되지 않으면 SPICE 새로고침 대기 (최대 1시간 간격 자동 갱신)

---

## 4. 역할별 기능 안내

### ADMIN (QS_Admin_Users)

| 기능 | 가능 여부 |
|------|----------|
| 대시보드 조회 | O |
| 대시보드 생성/편집 | O |
| 데이터셋 생성/편집 | O |
| 데이터 소스 관리 | O |
| 사용자/그룹 관리 | O |
| Quick 계정 설정 | O |

### AUTHOR (QS_Author_Users)

| 기능 | 가능 여부 |
|------|----------|
| 대시보드 조회 | O |
| 대시보드 생성/편집 | O |
| 데이터셋 조회 | O |
| 데이터셋 생성/편집 | O |
| 데이터 소스 관리 | X |
| 사용자/그룹 관리 | X |

### READER (QS_Viewer_Users)

| 기능 | 가능 여부 |
|------|----------|
| 대시보드 조회 | O |
| 대시보드 생성/편집 | X |
| 데이터셋 접근 | X |
| 데이터 소스 관리 | X |
| 사용자/그룹 관리 | X |

---

## 5. Obot 채팅에서 Quick 사용

MCP Bridge를 통해 Obot 채팅에서 Quick 대시보드 정보를 조회할 수 있습니다.

### 사용 가능한 명령

**대시보드 목록 조회:**
```
Obot에서: "Quick 대시보드 목록 보여줘"
```
내부적으로 `quick_dashboard_list` MCP 도구가 호출되어 사용 가능한 대시보드 목록을 반환합니다.

**특정 대시보드 데이터 조회:**
```
Obot에서: "RAG 성능 대시보드 데이터 보여줘"
```
내부적으로 `quick_dashboard_data` MCP 도구가 호출되어 해당 대시보드의 데이터셋 요약 정보를 반환합니다.

### 주요 대시보드

| 대시보드명 | 내용 |
|-----------|------|
| RAG 질의 현황 | 최근 질의 로그, 응답 시간 분포 |
| RAG 인용 통계 | 문서별 인용 빈도, 검색 유형별 성능 |
| 시스템 성능 | Lambda 실행 시간, 에러율, 스로틀 현황 |

---

## 6. 운영자 모니터링 가이드

### 6.1 CloudWatch 알람 목록

| 알람명 | 조건 | 대응 방법 |
|--------|------|----------|
| `quicksight-lambda-throttle-alarm` | Lambda 스로틀 5분간 5회 초과 | SPICE 새로고침 빈도 조정 또는 Reserved Concurrency 상향 검토 |
| `quicksight-vpce-status-alarm` | VPC Endpoint 비정상 | AWS Console → VPC → Endpoints 상태 확인, 필요 시 재생성 |
| `quicksight-vpc-conn-eni-alarm` | VPC Connection ENI 비정상 | Quick VPC Connection 재생성 검토 |

### 6.2 Lambda 스로틀 대응

```bash
# Lambda 스로틀 현황 확인
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Throttles \
  --dimensions Name=FunctionName,Value=lambda-quick-rag-connector-seoul-prod \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 300 \
  --statistics Sum \
  --region ap-northeast-2
```

스로틀이 지속되면 SPICE 새로고침 간격을 2시간으로 조정하거나 Reserved Concurrency를 20으로 상향하는 것을 검토하세요.

### 6.3 VPC Flow Logs 조회

Quick 관련 트래픽 이상 감지 시:

```bash
# CloudWatch Logs Insights로 Quick ENI 트래픽 조회
aws logs start-query \
  --log-group-name /aws/vpc/flowlogs/bos-ai-seoul-prod \
  --start-time $(date -d '1 hour ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, srcAddr, dstAddr, action | filter dstAddr like "10.10" | sort @timestamp desc | limit 50' \
  --region ap-northeast-2
```

### 6.4 CloudTrail Quick API 감사

```bash
# 최근 1시간 Quick API 호출 조회
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=quicksight.amazonaws.com \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ) \
  --region ap-northeast-2
```

### 6.5 SPICE 새로고침 수동 트리거

SPICE 데이터가 오래되었거나 즉시 갱신이 필요한 경우:

```bash
# 데이터셋 ID 조회
aws quicksight list-data-sets \
  --aws-account-id $(aws sts get-caller-identity --query Account --output text) \
  --region ap-northeast-2

# SPICE 새로고침 수동 트리거
aws quicksight create-ingestion \
  --aws-account-id $(aws sts get-caller-identity --query Account --output text) \
  --data-set-id <DATASET_ID> \
  --ingestion-id manual-refresh-$(date +%Y%m%d%H%M%S) \
  --region ap-northeast-2
```

---

## 7. 트러블슈팅

### 7.1 Quick 웹 콘솔 접속 불가

**체크리스트:**

- [ ] VPN 연결 상태 확인 (`ping 10.10.0.1` 응답 여부)
- [ ] DNS 해석 확인:
  ```bash
  nslookup quick.rag.corp.bos-semi.com
  # 결과가 10.10.x.x Private IP여야 함
  # Public IP가 반환되면 VPN 미연결 상태
  ```
- [ ] IAM Identity Center 계정 활성화 여부 확인 (초대 이메일 수락 여부)
- [ ] 그룹 멤버십 확인: AWS Console → IAM Identity Center → 사용자 → 그룹 탭

**DNS가 Public IP를 반환하는 경우:**
→ VPN 재연결 후 재시도

**로그인 후 권한 오류가 발생하는 경우:**
→ IAM Identity Center 그룹 동기화 대기 (최대 5분) 후 재시도
→ 해결되지 않으면 Admin에게 그룹 멤버십 확인 요청

---

### 7.2 대시보드 데이터가 표시되지 않음

- SPICE 새로고침 스케줄 확인 (기본 1시간 간격)
- 마지막 새로고침 시간 확인: Quick Console → 데이터셋 → 새로고침 기록
- 필요 시 수동 새로고침 (6.5 참고)
- RAG Connector Lambda 에러 확인:
  ```bash
  aws logs filter-log-events \
    --log-group-name /aws/lambda/lambda-quick-rag-connector-seoul-prod \
    --filter-pattern "ERROR" \
    --region ap-northeast-2
  ```

---

### 7.3 Obot 채팅에서 Quick 도구 오류

- MCP Bridge 서버 실행 상태 확인
- VPN 연결 상태 확인 (MCP Bridge도 VPN 경유 필요)
- MCP Bridge 로그에서 Quick API 호출 에러 확인:
  ```bash
  journalctl -u mcp-bridge -n 50
  ```

---

### 7.4 사용자 추가 후 Quick에 반영 안 됨

1. IAM Identity Center 그룹 멤버십 확인 (AWS Console)
2. RBAC Pipeline Provisioner Lambda 실행 로그 확인 (6.1 참고)
3. Quick 동기화 대기 (최대 5분)
4. 여전히 반영 안 되면 Quick Console에서 수동으로 사용자 확인:
   - Quick Console → 관리 → 사용자 관리

---

*최종 업데이트: 2026-04-01*
*문의: DevOps 팀 (infra@bos-semi.com)*
