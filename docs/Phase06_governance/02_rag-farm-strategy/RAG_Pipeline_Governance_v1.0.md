# RAG 파이프라인 개발 거버넌스 아키텍처 v1.0

**문서 버전:** v1.0
**작성일:** 2026-05-12
**Supersedes:** [RAG_Pipeline_Governance_v0.1.md](./RAG_Pipeline_Governance_v0.1.md)
**관련 문서:** [RAG_Farm_Strategy_v1.5.md](./RAG_Farm_Strategy_v1.5.md)
**대상:** 경영진, Platform팀, 분리 멤버 (설계자 개발자 포함), 법무/컴플라이언스

---

## 0. v1.0에서 확정된 사항 (v0.1 대비 변경점 요약)

| 항목 | v0.1 | **v1.0** |
|------|------|---------|
| 개발자 범주 | Platform 내부 full-time | **외부 설계자 (본업: 설계, 부업: RAG 파서 개발)** 트랙 신설 |
| 개발 환경 | 일반 사내 PC | **폐쇄망 (인터넷 차단)** 필수 |
| Repo 구조 | 3-repo 분할 | **1-repo + CODEOWNERS + IP 접근 분리** |
| CI/CD | GitLab + Jenkins 혼합 안 | **사내 GitLab (폐쇄망) CI + GitLab Runner CD** — Jenkins 불사용 |
| 배포 트리거 | 수동 승인 다단계 | **`main` merge = 유일한 CD 트리거** (3중 잠금) |
| MR 승인자 | 2명 | **3 approval: Platform 1 + 설계자 peer 1 + LLM 봇 1** |
| 환경 분리 | 스테이징/프로덕션 | **dev 단일 (SNPS RAG Alpha 단계), 확산 시 분리 검토** |
| RTL/IP 접근 통제 | 묵시적 | **§7 명시 — 도메인별 소유권·CODEOWNERS·S3 prefix IAM 분리** |
| 법적 준거 | 미기술 | **§10 법적 선결 조건 섹션 신설 (EAR / 벤더 라이선스 / AI 활용)** |

---

## 1. 배경과 목적

### 1.1 배경

BOS-AI RAG Farm은 다음 단계로 확장됩니다 ([RAG_Farm_Strategy_v1.5.md](./RAG_Farm_Strategy_v1.5.md)):

- **Alpha**: NPU 분석팀 4인 (RTL RAG)
- **Beta**: HQ_DV + 추가 도메인
- **v10**: Spec RAG
- **신규 도메인**: **SNPS IP RAG** — 파이프라인 개발자가 **설계자 본인** (우리 팀 외부)

이 확장 과정에서 두 가지 구조적 변화가 발생합니다:

1. **개발자가 IP 취급 권한을 동시에 가짐** — 설계자는 이미 SNPS IP를 다루는 것이 본업. RAG 파이프라인 개발 권한이 추가되는 것
2. **개발자가 Platform팀 외부 인력** — AWS 인프라를 볼 수도 만질 수도 없어야 함. 동시에 그들이 개발하는 파서는 AWS Lambda로 배포되어야 함

### 1.2 근본 원칙

1. **아무나 RTL/IP를 만질 수 없다.** — 자사 RTL이든 구매 IP든, **도메인별 소유권이 명확**하고 CODEOWNERS + IAM으로 **기술적으로 분리**된다. 권한 있는 자만 편집·배포 가능.
2. **설계자는 폐쇄망에서만 작업한다.** — 인터넷 PC에서의 IP 취급은 벤더 NDA·수출통제 관점에서 **방어 불가능한 자세**. 폐쇄망은 편의 저하를 감수한 최소 요건.
3. **설계자에게 AWS는 시야 밖이다.** — GitLab `main` merge만이 AWS 배포를 일으키며, 그 경로는 AWS IAM · 네트워크 SG · Protected Branch **3중으로 강제**된다.
4. **호출 게이트웨이 강제.** — Bedrock 직접 호출 경로는 IAM Deny로 차단. LiteLLM 경유만 허용 (v0.1 유지).

### 1.3 목적

위 네 원칙을 **기술적 통제·프로세스 통제·법적 근거**로 실현하는 거버넌스 아키텍처를 정의합니다.

---

## 2. 역할 분리 모델 (v0.1 업데이트)

```
┌─────────────────────────────────────────────────────────┐
│  Platform Team                                           │
│  - AWS 계정·VPC·네트워크·VPN 엔드포인트                   │
│  - OpenSearch·Bedrock KB·S3 버킷·IAM                     │
│  - Lambda 런타임·CloudWatch                               │
│  - GitLab Runner 호스팅 (폐쇄망 내부)                     │
│  - LiteLLM Gateway 운영                                   │
│  - Jenkinsfile·GitLab CI/CD 파이프라인 스크립트            │
│  - CODEOWNERS / Protected Branch 설정                     │
│  - 비용·보안·컴플라이언스 모니터링                         │
└─────────────────────────────────────────────────────────┘
                         ↑ 자원 제공 + 거버넌스 통제
                         ↓ 사용 (제한된 경로)
┌─────────────────────────────────────────────────────────┐
│  Pipeline Developers (분리 멤버)                          │
│  ├─ Internal — NPU 분석팀 개발자 (RTL RAG)                │
│  └─ External — 설계자 (SNPS IP RAG, Spec RAG 예정)        │
│                                                           │
│  공통 권한/제약:                                           │
│  - 파서 코드 (본인 도메인만): 수정 가능                    │
│  - Lambda 핸들러 (본인 도메인만): 수정 가능                │
│  - 타 도메인 파서/핸들러: 읽기만 또는 접근 차단             │
│  - AWS 인프라: 접근 차단                                   │
│  - Bedrock 직접 호출: IAM Deny                           │
│  - LLM 호출: LiteLLM 경유만                              │
│  - 배포 수단: GitLab MR → merge 외 경로 없음              │
└─────────────────────────────────────────────────────────┘
```

**외부 설계자 트랙의 추가 제약:**

- **폐쇄망 PC에서만 작업** (인터넷 PC에서의 SNPS 코드 취급 금지)
- **AWS 콘솔/CLI 접근 불가**: VPN 엔드포인트 화이트리스트에도 설계자 PC IP 제외
- **본업이 RAG 개발이 아님**: CI/CD 복잡도 최소화, Jenkins UI 등 추가 도구 사용 금지

### 2.1 권한 매트릭스 (v1.0)

| 영역 | Platform팀 | 내부 개발자 (RTL) | **외부 설계자 (SNPS)** |
|------|----------|-----------------|--------------------|
| `parsers/rtl/` | 리뷰 | 읽기/수정 | **읽기만** |
| `parsers/snps_ip/` | 리뷰 | 읽기만 | **읽기/수정** |
| `parsers/spec/` | 리뷰 | 읽기만 | 읽기만 |
| Lambda 핸들러 (본인 도메인) | 리뷰 | 읽기/수정 | **읽기/수정** |
| Lambda 핸들러 (타 도메인) | 리뷰 | 읽기만 | **접근 차단** |
| CloudWatch 로그 (본인 Lambda) | 전체 | 본인 로그 그룹만 | **로그 직접 접근 불가 — Slack/Teams 알림만** |
| Bedrock 호출 | 관리 | LiteLLM 경유만 | **LiteLLM 경유만 (dev-snps-* 키)** |
| OpenSearch 인덱스 스키마 | 관리 | 읽기만 | **접근 차단** |
| S3 (RTL 원본) | 관리 | prefix 제한 읽기 | **접근 차단** |
| S3 (SNPS IP 원본) | 관리 | **접근 차단** | prefix 제한 읽기 |
| Terraform | 관리 | 접근 차단 | 접근 차단 |
| IAM / VPC | 관리 | 접근 차단 | 접근 차단 |
| Jenkinsfile / `.gitlab-ci.yml` | 관리 | 접근 차단 (CODEOWNERS) | 접근 차단 |
| GitLab Runner 호스트 | 관리 | 접근 차단 | 접근 차단 |

---

## 3. 전체 아키텍처 (v1.0)

```
┌─ 폐쇄망 (Closed Network, 인터넷 차단) ────────────────────┐
│                                                          │
│  ┌─ 설계자 PC ──────────────────────────────────┐         │
│  │  - Python venv / uv (사내 PyPI 미러 경유)    │         │
│  │  - 파서 로컬 스모크 (mock, AWS 없이)          │         │
│  │  - GitLab push/MR                             │         │
│  │  - AWS 엔드포인트 접근 권한 없음 ★            │         │
│  │  - LiteLLM dev-snps-* 키 (소량 쿼터)          │         │
│  └──────────────────┬───────────────────────────┘         │
│                     │ git push / MR                       │
│                     ↓                                     │
│  ┌─ 사내 GitLab (폐쇄망) ──────────────────────┐          │
│  │  - Group: bos-ai-rag                         │          │
│  │  - Protected Branches (main, release/*)      │          │
│  │  - CODEOWNERS (도메인별 + Platform 필수)      │          │
│  │  - MR Approval: 3 (Platform + peer + LLM봇)   │          │
│  │  - Push Rules: Signed Commit, Secret Scan    │          │
│  └──────────────────┬───────────────────────────┘          │
│                     │ main merge = CD 트리거 ★             │
│                     ↓                                     │
│  ┌─ GitLab Runner (폐쇄망 내부) ────────────────┐          │
│  │  - CI: lint · test · package                  │          │
│  │  - CD: AssumeRole via OIDC (main만)           │          │
│  │  - AWS 엔드포인트 접근 권한 보유자 ★           │          │
│  │  - 설계자/일반 개발자 SSH 접근 불가            │          │
│  └──────────────────┬───────────────────────────┘          │
│                     │                                     │
└─────────────────────┼─────────────────────────────────────┘
                      │ VPN 내부망 (엔드포인트 화이트리스트)
                      │ - sts.*.amazonaws.com
                      │ - lambda.*.amazonaws.com
                      │ - s3.*.amazonaws.com (배포 패키지 업로드용)
                      │ - LiteLLM Gateway (폐쇄망↔AWS)
                      ↓
┌─ AWS VPC (Private) ──────────────────────────────────────┐
│                                                          │
│  ┌─ Platform 영역 ──────────────┐                         │
│  │  Terraform·IAM·VPC·KMS        │                         │
│  │  S3 (도메인별 버킷·prefix)     │                         │
│  │  OpenSearch Serverless         │                         │
│  │  Bedrock KB                    │                         │
│  └──────────┬────────────────────┘                         │
│             ↓ 자원 제공                                     │
│  ┌─ Pipeline 영역 ──────────────┐                         │
│  │  Lambda (rag-pipeline-rtl-*)  │                         │
│  │  Lambda (rag-pipeline-snps-*) │                         │
│  │  Lambda (rag-pipeline-spec-*) │                         │
│  │     ↓ LLM 호출                 │                         │
│  │  LiteLLM Gateway (ECS Fargate)│                         │
│  │     ↓                          │                         │
│  │  Bedrock (VPC Endpoint)        │                         │
│  └────────────────────────────────┘                         │
│                                                          │
│  ┌─ MCP 서버 (검증용) ──────────┐                         │
│  │  read-only API for Claude     │                         │
│  │  → 설계자 Claude Desktop에서   │                         │
│  │    폐쇄망 VPN 경유 쿼리        │                         │
│  └────────────────────────────────┘                         │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Repo 구조 (단일 repo + 도메인 분리)

```
bos-ai-rag/  (사내 GitLab, 폐쇄망, 단일 repo)
│
├─ parsers/
│  ├─ rtl/           ← 내부 개발자 (NPU 분석팀)
│  ├─ snps_ip/       ← ★ 외부 설계자 전용 작업 영역
│  └─ spec/          ← 향후 (Spec RAG)
│
├─ lambda_handlers/
│  ├─ rtl_handler.py
│  ├─ snps_ip_handler.py
│  └─ spec_handler.py
│
├─ tests/
│  ├─ unit/          (269 단위 테스트, 도메인별)
│  └─ smoke/         (도메인별 canonical Q&A 5~10개)
│
├─ local-dev-kit/    (mock Bedrock/OpenSearch, pytest runner)
│
├─ .gitlab-ci.yml    ← Protected + CODEOWNERS=@platform-team
├─ Jenkinsfile       ← (사용 안 함, 참조용)
│
└─ infra/            ← Terraform·IAM·Helm 등 (접근 차단 대상)
```

### 4.1 CODEOWNERS 규칙

```
# Platform 전용 — 인프라·CI·IAM
/.gitlab-ci.yml          @platform-team
/infra/                  @platform-team
/lambda_handlers/**/*.yml @platform-team

# 도메인 소유권 — 각 도메인 lead + Platform
/parsers/rtl/            @rtl-rag-lead @platform-team
/parsers/snps_ip/        @snps-design-lead @platform-team
/parsers/spec/           @spec-rag-lead @platform-team

/lambda_handlers/rtl_handler.py       @rtl-rag-lead @platform-team
/lambda_handlers/snps_ip_handler.py   @snps-design-lead @platform-team
/lambda_handlers/spec_handler.py      @spec-rag-lead @platform-team

# 스모크 테스트 — 도메인 + Platform 공동 책임
/tests/smoke/rtl/        @rtl-rag-lead @platform-team
/tests/smoke/snps_ip/    @snps-design-lead @platform-team
```

**결과:**
- 설계자는 `parsers/snps_ip/` 외 경로 수정 시 **Platform 또는 타 도메인 lead 승인 필수** → 사실상 불가
- Jenkinsfile/Terraform은 설계자가 수정 시도해도 **CODEOWNERS 승인 벽**에 막힘

### 4.2 GitLab 설정 요약

| 기능 | 설정 | 목적 |
|------|------|------|
| Protected Branches | `main`, `release/*` | 리뷰 없는 merge 불가 |
| Push Rules | Signed Commit + Secret Scanning | 시크릿 커밋 방지 |
| MR Approval Rules | **3 approval** (Platform 1 + peer 1 + LLM 봇 1) | §5 참조 |
| Protected Variables | AWS OIDC 관련 | Protected 브랜치에서만 접근 |
| Mirror 금지 | 외부 GitHub 등 미러 push 설정 금지 | IP 외부 유출 방지 |

---

## 5. MR 승인 모델 — 3 Approval

### 5.1 승인자 구성

| 승인자 | 역할 | 관점 |
|-------|------|------|
| **Platform 1명** | 인프라·보안 | CI/CD·IAM·LiteLLM·secret 누출 등 통제 레이어 점검 |
| **도메인 peer 1명** | 도메인 정합성 | 파서가 도메인 RTL/IP를 올바르게 해석하는가. 스모크 회귀 리스크 |
| **LLM 봇 (Claude)** | 코드 품질·회귀 risk | 정적 분석·프롬프트 인젝션·secret 패턴 감지 |

**승인 불가 상황 대응:**
- peer 풀이 2명 미만이면 일시적으로 **Platform 1 + LLM 봇 1 = 2 approval**로 완화 (비상 절차, 문서화 필수)
- 이 경우 **merge 후 72시간 내** peer 소급 리뷰 의무화

### 5.2 LLM 리뷰 봇 아키텍처

```
[GitLab MR 생성 webhook]
   ↓
[Webhook Receiver Lambda (AWS VPC)]
   ↓
[LiteLLM Gateway 경유 Claude 호출]
   ↓
[LLM 리뷰 결과 → GitLab MR 댓글]
```

**LLM 리뷰 프롬프트 핵심 항목:**
- 기존 스모크 쿼리 회귀 가능성
- 파서 coverage 누락 (신규 모듈 타입 등)
- Secret·credential 하드코딩 감지
- 프롬프트 인젝션 취약 패턴
- **RTL/IP 원본 파일이 커밋에 실수 포함됐는지**

**LLM 봇은 "의견 제공"만.** 자동 approve/block 권한 없음. 사람 승인자(peer, Platform)가 이를 참고해 판단.

### 5.3 배경: 왜 3 approval인가

- 설계자 peer 혼자는 **파이프라인/AWS 통제 관점 부족**
- Platform 혼자는 **도메인 코드 정합성 판단 어려움**
- LLM 봇은 **24/7 가용 + 일관된 정적 체크** 제공 → 사람 리뷰어의 load 완화

---

## 6. "merge = 유일한 CD 경로" 3중 잠금

`main` 브랜치 merge 외의 경로로 AWS에 배포될 수 없음을 **기술적으로 강제**합니다.

### 잠금 1: AWS IAM Trust Policy — Runner + main branch 조건

```json
{
  "Role": "SNPSPipelineDeployer",
  "AssumeRolePolicy": {
    "Principal": {
      "Federated": "arn:aws:iam::ACCT:oidc-provider/gitlab.internal/..."
    },
    "Condition": {
      "StringEquals": {
        "gitlab.internal:sub": "project_path:bos-ai-rag:ref_type:branch:ref:main",
        "gitlab.internal:project_path": "bos-ai-rag"
      }
    }
  }
}
```

- `ref:main` 조건 → feature 브랜치에서는 AssumeRole 실패
- 설계자 PC에는 OIDC 토큰 발급 주체 ID가 없어 **AssumeRole 시도 자체 불가**

### 잠금 2: VPN + Security Group — Runner IP만 엔드포인트 통과

- 설계자 PC 대역 → AWS Lambda/STS/S3 엔드포인트 **네트워크 레벨 차단**
- **GitLab Runner 호스트 IP만 화이트리스트**
- 설계자가 `aws cli` 몰래 설치해도 TCP 연결 실패

### 잠금 3: GitLab Protected Branch + CODEOWNERS

- `main` Protected → direct push 불가, MR merge만 가능
- `.gitlab-ci.yml` CODEOWNERS = `@platform-team` → 설계자 수정 시 승인 벽
- `.gitlab-ci.yml`의 `deploy` job: `only: - main`

**세 잠금이 동시에 유지되어야 "merge 외 경로 없음"이 보안적으로 성립.** 하나라도 빠지면 우회 가능 — 감사 대응용으로 이 세 가지를 **체크리스트화하여 분기별 점검**.

---

## 7. ★ RTL/IP 접근 통제 — "아무나 만질 수 없다"

이것은 v1.0의 **가장 중요한 신설 섹션**입니다. 자사 RTL이든 구매 IP든, 도메인별로 엄격히 분리됩니다.

### 7.1 도메인 분류와 소유권

| 도메인 | RTL/IP 성격 | 소유권 | 기술적 분리 |
|-------|-----------|-------|----------|
| **RTL (Trinity 등)** | 자사 RTL | NPU 분석팀 + Platform | S3 prefix `rtl/*`, IAM group `rtl-rag-users` |
| **SNPS IP** | **벤더 구매 IP (EAR 대상)** | SNPS 설계팀 + Platform | S3 prefix `snps_ip/*`, **IAM group `snps-design-users` — 내부 RTL 개발자도 접근 불가** |
| **Spec** | 자사 문서 (하이브리드) | DV팀 + Platform | S3 prefix `spec/*` |

### 7.2 5중 분리 통제

| 계층 | 통제 수단 | RTL 예시 | SNPS IP 예시 |
|------|---------|---------|-----------|
| **1. 파일 시스템 (repo)** | CODEOWNERS | `parsers/rtl/` → NPU 분석팀 | `parsers/snps_ip/` → 설계팀 |
| **2. S3 버킷 prefix** | IAM policy prefix condition | `s3://bos-ai-rag/rtl/**` | `s3://bos-ai-rag/snps_ip/**` |
| **3. OpenSearch 인덱스** | 인덱스별 IAM policy | `rtl-*` 인덱스 | `snps-*` 인덱스 (별도 collection 권장) |
| **4. Lambda 함수** | Resource Naming + IAM | `rag-pipeline-rtl-*` | `rag-pipeline-snps-*` |
| **5. LiteLLM API 키** | 키별 모델·쿼터 제한 | `dev-rtl-*`, `prod-rtl-*` | `dev-snps-*`, `prod-snps-*` |

**교차 접근 시나리오:**
- 내부 RTL 개발자가 SNPS IP를 보려 시도 → S3 IAM 거부 + OpenSearch 인덱스 거부 + CODEOWNERS 승인 벽 = **3중 차단**
- SNPS 설계자가 RTL RAG 코드를 수정 시도 → `parsers/rtl/` CODEOWNERS 승인 벽 = **1중 차단 (단일 벽이지만 절차적으로 명확)**

### 7.3 구매 IP의 특수 취급

SNPS IP는 자사 RTL보다 **엄격한 기준선**을 적용합니다:

- **OpenSearch collection 별도 분리** (인덱스 레벨이 아닌 collection 레벨) → 네트워크·암호화 키까지 분리
- **KMS 키 분리**: `kms-snps-ip` 키로 S3 객체·OpenSearch 데이터 암호화. 이 키 접근자는 설계자 + Platform만
- **감사 로그 별도 보관**: S3 access log·CloudTrail 이벤트 중 `snps_ip/*` 관련은 별도 prefix로 장기 보관 (컴플라이언스 대응)
- **라이선스 메타데이터**: 각 IP 파일에 `LICENSE_TAG`, `EAR_ECCN`, `VENDOR_NDA_REF` 속성 부여 — RAG 출력에서도 태그 유지

### 7.4 접근 권한 부여·해지 절차

| 이벤트 | 필요 조치 | 담당 |
|-------|---------|------|
| 신규 설계자 온보딩 | 수출통제 교육 이수 → IAM group 가입 → LiteLLM 키 발급 → repo 접근권 부여 | Platform + 법무 |
| 설계자 퇴사·이동 | IAM group 제거 → LiteLLM 키 revoke → repo 접근권 회수 → 접근 이력 감사 | Platform (24시간 내) |
| 신규 IP 도입 | S3 prefix·KMS 키 생성 → CODEOWNERS 업데이트 → 라이선스 메타데이터 작성 | Platform + 설계 lead |
| 분기별 권한 감사 | 미사용 계정 탐지, 권한 중복 제거, 감사 로그 샘플링 검토 | Platform (분기별) |

---

## 8. LiteLLM 게이트웨이 (v0.1 유지 + 도메인별 분리 강화)

### 8.1 API 키 정책 (v0.1 확장)

| 키 유형 | 발급 대상 | 쿼터 | 허용 모델 | 도메인 제한 |
|--------|---------|------|----------|----------|
| `dev-rtl-*` | 내부 개발자 로컬 | 낮음 | Haiku | RTL 데이터만 |
| `prod-rtl-*` | RTL Lambda | 높음 | Sonnet, Opus | RTL 데이터만 |
| `dev-snps-*` | **설계자 폐쇄망 PC** | **낮음** | **Haiku** | **SNPS IP 데이터만** |
| `prod-snps-*` | SNPS Lambda | 중간 | Sonnet | SNPS IP 데이터만 |
| `alpha-user-*` | Alpha 유저 | 제한적 | Sonnet | 유저가 속한 도메인만 |

**도메인 제한 메커니즘:**
- LiteLLM 요청에 `X-Domain: snps_ip` 헤더 필수
- 키별 허용 도메인 리스트 사전 등록 → 불일치 시 401
- 도메인 간 cross-call 방지 (SNPS 키로 RTL 프롬프트 호출 차단)

### 8.2 폐쇄망 LiteLLM 접근

- 설계자 PC는 **VPN 경유 LiteLLM 엔드포인트 도달 가능** (SNPS IP 취급에 LLM 필요한 유일한 외부 의존)
- LiteLLM 엔드포인트는 VPN 화이트리스트에 포함
- **Bedrock 직접 엔드포인트는 설계자 PC 네트워크에 차단** (IAM Deny + SG 차단 이중)

---

## 9. IAM 거버넌스 (v0.1 유지 + 도메인 확장)

### 9.1 Permissions Boundary — 도메인별 prefix 강제

```json
{
  "Sid": "AllowSNPSPipelineDev",
  "Effect": "Allow",
  "Action": [
    "lambda:UpdateFunctionCode",
    "lambda:PublishVersion",
    "lambda:GetFunction"
  ],
  "Resource": "arn:aws:lambda:*:*:function:rag-pipeline-snps-*"
},
{
  "Sid": "DenyOtherDomains",
  "Effect": "Deny",
  "Action": "lambda:*",
  "NotResource": "arn:aws:lambda:*:*:function:rag-pipeline-snps-*"
}
```

핵심: **도메인 boundary를 prefix 단위로 기술적 강제**. SNPS 설계자의 권한은 `rag-pipeline-snps-*`에만 동작, 타 도메인 Lambda 건드릴 수 없음.

### 9.2 Role 구성 (v1.0)

| Role | 대상 | 도메인 | Boundary |
|------|------|-------|---------|
| `RTLPipelineDev` | 내부 RTL 개발자 | `rag-pipeline-rtl-*` | 필수 |
| `SNPSPipelineDev` | **설계자** | **`rag-pipeline-snps-*`** | **필수** |
| `SpecPipelineDev` | Spec 개발자 (향후) | `rag-pipeline-spec-*` | 필수 |
| `SNPSPipelineDeployer` | **GitLab Runner (SNPS)** | SNPS 배포 전용 | OIDC 전용 |
| `LiteLLMService` | ECS Task | 전역 Bedrock 호출 | — |
| `PlatformAdmin` | Platform팀 | 인프라 전반 | MFA 필수 |

---

## 10. 법적 선결 조건 (신설)

이 섹션은 **기술팀 판단이 아닌 법무/컴플라이언스/경영진 결정 대상**입니다. 기술 구현 착수 전 **필수 확인**.

### 10.1 미국 수출통제 (EAR) — SNPS는 미국 기업

- Synopsys IP/EDA 도구는 미국 EAR (Export Administration Regulations) 적용 대상
- 대부분 이중용도 품목 (ECCN `3D991`, `3E991` 계열)
- **2022년 10월 BIS 반도체 수출통제 강화**: 첨단 프로세스 관련 EDA/IP는 중국 등 통제 강화
- **Deemed Export**: 미국 기술을 미국 내에서 non-US person에게 공개해도 "수출"로 간주 — 국내에서도 국적에 따라 제약

### 10.2 "AI 활용"에 대한 벤더 라이선스 제약

- 최근 EDA 벤더들이 라이선스에 **AI 학습·파인튜닝 금지** 조항 추가 추세
- **추론 vs 학습 구분**: OpenAI ChatGPT 개인 계정은 학습에 사용될 수 있음 (위험). Bedrock은 AWS 계약상 학습 미사용 명시 → **LiteLLM + Bedrock 아키텍처의 법적 정당성**
- 사내 RAG에 벤더 IP 인덱싱이 **"내부 사용"** vs **"2차 저작물 생성"**인지 계약서 precise wording 확인 필요

### 10.3 실무 체크리스트 (기술 착수 전 필수)

- [ ] SNPS 라이선스 계약서의 **"authorized environment / permitted use"** 조항 확인
- [ ] SNPS 라이선스에 **AI/LLM 활용 관련 조항** 여부 확인 (2024~2025 개정분 포함)
- [ ] 설계자·리뷰어·Platform 접근자 **국적 현황** 파악 → Deemed Export 대상자 유무
- [ ] 인덱싱 대상 IP의 **ECCN 번호** 파악
- [ ] 사내 수출통제 담당자에게 **"BOS-AI RAG에 SNPS IP 인덱싱"** 공식 승인 요청
- [ ] **Bedrock의 데이터 비학습 조항**을 AWS 계약서에서 인용 가능하도록 자료화
- [ ] 벤더(Synopsys) 고지·동의 필요성 법무 검토
- [ ] 감사 발생 시 제시할 **"폐쇄망 + 접근 통제" 증거** 체계 확보 (CloudTrail, GitLab 감사 로그, IAM 감사 로그)

### 10.4 "왜 폐쇄망인가" 공식 입장

> "인터넷 PC 환경의 DLP·ZTNA 통제에도 불구하고 IDE AI 코파일럿의 자동 송출, GitHub 개인 repo로의 오배치, 클립보드·ChatGPT 우회 등 근본 차단 불가한 유출 경로가 다수 존재합니다. SNPS IP는 미국 EAR + 벤더 라이선스의 이중 규제 대상이며, 감사·분쟁 발생 시 '우리는 인터넷 격리 환경에서 취급했다'는 자세가 법적·계약적 방어의 기본선입니다. 폐쇄망 선택은 편의 저하를 감수한 벤더 NDA·수출통제 준수의 최소 요건입니다."

---

## 11. 로컬 개발 환경 (폐쇄망 전제)

### 11.1 설계자 PC 제공 항목

| 항목 | 제공 방식 | 비고 |
|------|---------|------|
| 파서 소스 코드 | 사내 GitLab clone | 폐쇄망 내부 |
| Python 환경 | 사내 PyPI 미러 경유 uv/venv | ★ PyPI 미러 선결 |
| Docker 이미지 | 사내 Docker Registry 미러 | ★ 선결 |
| Mock Bedrock/OpenSearch | `local-dev-kit/` stub | 오프라인 동작 |
| AWS SAM Local | (선택적) | 로컬 Lambda 실행 |
| LiteLLM `dev-snps-*` 키 | Platform 발급 | VPN 경유 |
| Claude Desktop + MCP 클라이언트 | 폐쇄망 설치판 | 검증용 |
| 단위 테스트 러너 | pytest + 도메인 회귀 | 오프라인 동작 |

### 11.2 설계자가 할 수 있는 것 / 없는 것

| 작업 | 가능 여부 |
|------|---------|
| `parsers/snps_ip/` 코드 수정 | 가능 |
| 단위 테스트 (mock, 오프라인) | 가능 |
| 로컬 통합 테스트 (mock) | 가능 |
| LiteLLM 개발 키로 Bedrock 테스트 (VPN 경유) | 가능 (쿼터 제한) |
| Lambda 로컬 실행 (SAM Local) | 가능 |
| **실 Lambda 배포** | **불가 — MR merge 경유만** |
| **AWS 콘솔 접근** | **불가** |
| **AWS CLI 직접 호출** | **불가 (네트워크 차단)** |
| **Jenkins UI 접근** | **불가 (사용 자체 안 함, v0.1→v1.0 변경)** |
| **MCP 서버로 배포 결과 쿼리** | 가능 (read-only, VPN 경유) |
| **타 도메인 (RTL) 파서 수정** | **불가 (CODEOWNERS 차단)** |

### 11.3 배포 플로우 (v1.0 간소화)

```
[설계자 로컬: parsers/snps_ip/ 수정]
   ↓ pytest 스모크 (mock, 오프라인)
   ↓ git push feature branch
[사내 GitLab: MR 생성]
   ├─ CI 자동 실행
   │   ├─ 린트 (ruff, mypy)
   │   ├─ 단위 테스트
   │   ├─ 보안 스캔 (Secret, SAST)
   │   └─ Lambda 패키지 빌드
   ├─ LLM 리뷰 봇 댓글 자동 생성
   ├─ Platform 승인
   └─ 설계자 peer 승인
   ↓ 3 approval 충족 + merge to main
[GitLab Runner 자동 실행]
   ├─ OIDC → AssumeRole (SNPSPipelineDeployer, main 전용)
   ├─ aws lambda update-function-code (rag-pipeline-snps-*)
   ├─ aws lambda invoke (인덱스 재생성 이벤트)
   ├─ 스모크 쿼리 5~10개 실행
   └─ Slack/Teams 알림 (성공/실패, 10분 이내)
   ↓
[설계자: Claude Desktop + MCP로 검증]
   (read-only, VPN 경유, AWS 콘솔 접근 없음)
```

**설계자 입장 액티브 스텝: 3개 (로컬 수정 → MR → MCP 검증).** 나머지는 자동 + 리뷰어 워크플로우.

---

## 12. 도입 로드맵 (v1.0)

| 단계 | 작업 | 주체 | 기간 | 의존성 |
|------|------|------|------|-------|
| 0 | **법적 선결 조건 점검 (§10)** | **법무 + Platform** | **2주** | — |
| 1 | 사내 PyPI/Docker 미러 확보 | 사내 Ops | 1주 | — |
| 2 | 사내 GitLab 프로젝트 구조 + OIDC | Platform + Ops | 3일 | — |
| 3 | CODEOWNERS + Protected Branch 설정 | Platform | 2일 | 2 |
| 4 | GitLab Runner (폐쇄망) 구축 | Platform | 1주 | 1, 2 |
| 5 | LiteLLM ECS 배포 + 도메인 키 정책 | Platform | 1주 | VPC 확보 |
| 6 | Permissions Boundary + 도메인 IAM Role | Platform | 1주 | — |
| 7 | S3/OpenSearch 도메인 분리 구조 (§7.2) | Platform | 1주 | — |
| 8 | LLM 리뷰 봇 (Lambda + LiteLLM 연동) | Platform | 3~5일 | 5 |
| 9 | 로컬 개발 키트 (mock + 스모크 + README) | Platform + 도메인 lead | 1주 | 2 |
| 10 | GitLab CI/CD 파이프라인 작성 | Platform | 1주 | 3, 4, 6 |
| 11 | 폐쇄망 PC 셋업 (설계자 1명 pilot) | Platform + IT | 3일 | 1, 9 |
| 12 | 설계자 온보딩 (1명 → 전체) | 공동 | 2주 | 0~11 완료 |

**총 약 6~8주.** Phase 0 (법적 선결)은 기술 작업과 병행 가능하되, **Phase 12 온보딩 전 완료 필수**.

---

## 13. 주의할 함정 (v0.1 확장)

### 13.1 폐쇄망 관련 신규 함정

| 함정 | 왜 위험한가 | 대응 |
|------|-----------|------|
| 설계자가 "편의상" 사내 인터넷 PC에서 작업 | 폐쇄망 격리 무력화, 본 문서 §10.4 방어 논리 붕괴 | 물리 분리 PC + 사내 정책 + 주기 감사 |
| 폐쇄망에서 사내 GitHub 등 외부 Git mirror 접근 | 조직 repo로 실수 push 시 IP 유출 | GitLab mirror 설정 금지 + 사내 GitHub에 SNPS 경로 차단 |
| PyPI 미러에 검증 안 된 패키지 동기화 | Supply chain 공격 | 화이트리스트 기반 + 서명 검증 |
| VPN 엔드포인트 화이트리스트 과다 허용 | 실제 필요 이상의 AWS 서비스 접근 가능 | 최소 권한 원칙, 분기별 점검 |

### 13.2 도메인 분리 관련 함정

| 함정 | 왜 위험한가 | 대응 |
|------|-----------|------|
| CODEOWNERS 우회 (force push 등) | 도메인 분리 붕괴 | Protected Branch + Push Rules + 감사 로그 |
| S3 prefix IAM 정책에 와일드카드 과다 | 타 도메인 S3 접근 가능 | 명시적 prefix, IAM Analyzer 주기 점검 |
| OpenSearch 단일 collection 공유 | 도메인 데이터 혼재 | Collection 단위 분리 (특히 SNPS IP) |
| LiteLLM 키 공유 (개발자간) | 도메인 경계 무력화 | 키는 개인별, 주기적 rotation |

### 13.3 MR 승인 관련 함정

| 함정 | 왜 위험한가 | 대응 |
|------|-----------|------|
| peer 풀 부족 → 동일인 반복 승인 | 실질 검토 없이 형식적 승인 | peer 3명 이상 확보, 동일인 연속 승인 제한 |
| LLM 봇이 자동 approve 수행 | 사람 리뷰 무력화 | 봇은 의견만, approve 권한 없음 (§5.2) |
| Platform 승인자 부재 시 지연 | 업무 병목 | Platform 내 순번제, back-up 승인자 지정 |

---

## 14. 보고용 요약

> **"BOS-AI RAG Farm v1.0 거버넌스는 네 가지 원칙 위에 섭니다. (1) 도메인별 RTL/IP 소유권을 CODEOWNERS·IAM·S3 prefix·KMS 키로 5중 분리하여 아무나 자사 RTL이나 구매 IP를 만질 수 없습니다. (2) 외부 설계자는 폐쇄망 PC에서만 SNPS IP를 취급하며, 이는 벤더 NDA·미국 EAR 수출통제 준수의 최소 요건입니다. (3) `main` 브랜치 merge만이 AWS 배포를 일으키며, 이 경로는 IAM Trust Policy·네트워크 Security Group·GitLab Protected Branch 3중으로 기술적 강제됩니다. (4) Bedrock 직접 호출은 IAM으로 원천 차단되고 모든 LLM 호출은 LiteLLM을 경유하여 팀별·도메인별 쿼터·비용·감사 로그를 중앙 통제합니다. 설계자는 AWS 인프라를 볼 수도 만질 수도 없으며, 본업(설계)에 최소한의 간섭만으로 RAG 파이프라인 기여가 가능한 구조입니다."**

### 핵심 4가지

1. **RTL/IP 접근 분리** — CODEOWNERS + S3 prefix + OpenSearch collection + KMS + LiteLLM 키 5중
2. **폐쇄망 개발** — 인터넷 격리 + VPN 경유 AWS 엔드포인트 화이트리스트
3. **merge = 유일 CD 경로** — IAM + SG + Protected Branch 3중 잠금
4. **LLM/IAM 통제** — LiteLLM 경유 강제 + Permissions Boundary + 도메인 Role 분리

---

## 15. 오픈 이슈

- [ ] 법적 선결 조건 §10.3 체크리스트 완료 (법무·수출통제 담당 확정)
- [ ] 사내 PyPI/Docker 미러 현황 파악 + 필요시 신규 구축
- [ ] MCP 서버 호스팅 위치 확정 (AWS Lambda/ECS vs 폐쇄망 내부)
- [ ] 설계자 peer 리뷰어 pool 확보 (3명 이상)
- [ ] 폐쇄망 PC 조달·셋업 책임 부서 확정 (IT·보안팀)
- [ ] Slack/Teams 알림 채널 (도메인별)
- [ ] 배포 실패 시 자동 롤백 정책 (Lambda alias versioning)
- [ ] LLM 리뷰 봇 프롬프트 관리·버전 관리 방식
- [ ] SNPS IP용 OpenSearch collection 별도 분리 비용 검토
- [ ] 분기별 권한 감사 자동화 (IAM Access Analyzer, GitLab 감사 로그)
- [ ] 감사 로그 보관 기간 (컴플라이언스 요구 반영)

---

*End of Document — v1.0*
