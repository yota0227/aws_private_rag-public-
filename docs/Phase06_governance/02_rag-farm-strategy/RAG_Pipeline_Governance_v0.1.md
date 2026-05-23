# RAG 파이프라인 개발 거버넌스 아키텍처

**문서 버전:** v0.1
**작성일:** 2026-05-06
**관련 문서:** [RAG_Farm_Strategy_v1.5.md](./RAG_Farm_Strategy_v1.5.md)
**대상:** 경영진, Platform팀, 분리 멤버

---

## 1. 배경과 목적

### 1.1 배경

BOS-AI RAG Farm이 Alpha(NPU 분석팀 4인) → Beta(HQ_DV) → v10(Spec RAG) 단계로 확장되면서, **파이프라인 개발자의 범위도 확대**됩니다. 경영진 지침에 따라 다음 원칙을 적용합니다.

- **AWS 아키텍처·운영 전반은 Platform팀(우리)이 담당**
- **파이프라인(파서·프롬프트·Lambda 핸들러) 개발·배포는 분리 멤버가 담당**
- 분리 멤버는 **로컬에서 개발**하고 **Lambda로 배포만** 할 수 있는 환경 필요
- 분리 멤버 권한은 **거버넌스로 엄격히 통제**

### 1.2 목적

이 문서는 위 원칙을 실현하기 위한 거버넌스 아키텍처를 정의합니다.

---

## 2. 역할 분리 모델

```
┌─────────────────────────────────────────────────────────┐
│  Platform Team (우리)                                    │
│  - AWS 계정·VPC·네트워크                                  │
│  - OpenSearch·Bedrock KB·S3 버킷                         │
│  - Lambda 런타임·IAM 역할·CloudWatch                      │
│  - CI/CD 파이프라인 (배포 채널 소유)                       │
│  - LiteLLM Gateway 운영                                   │
│  - 비용·보안·컴플라이언스                                  │
└─────────────────────────────────────────────────────────┘
                         ↑ 자원 제공
                         ↓ 사용
┌─────────────────────────────────────────────────────────┐
│  Pipeline Developers (분리 멤버)                          │
│  - 파서 코드 (Python)                                     │
│  - 프롬프트 튜닝                                          │
│  - Lambda 함수 소스 배포                                   │
│  - 테스트·회귀검증                                        │
└─────────────────────────────────────────────────────────┘
```

**핵심 원칙:** 분리 멤버는 **코드만** 다루고, **인프라는 손 못 댄다.**

### 2.1 권한 매트릭스

| 영역 | Platform팀 | 분리 멤버 |
|------|----------|---------|
| 파서 코드 (src/) | 리뷰 | 읽기/수정 |
| Lambda 핸들러 코드 | 리뷰 | 읽기/수정 |
| CloudWatch 로그 (본인 Lambda) | 전체 | 본인 로그 그룹만 |
| Bedrock 호출 | 관리 | **LiteLLM 경유만** |
| OpenSearch 인덱스 스키마 | 관리 | 읽기만 |
| Terraform (`*.tf`) | 관리 | 접근 차단 |
| IAM 정책 | 관리 | 접근 차단 |
| S3 버킷 정책 | 관리 | 접근 차단 |
| VPC / 네트워크 | 관리 | 접근 차단 |

---

## 3. 전체 아키텍처

```
┌─ 분리 멤버 PC ────────────────────────────┐
│  로컬 개발 환경                            │
│  - Python venv / uv                       │
│  - 파서 유닛 테스트 (AWS 없이 실행)         │
│  - Mock Bedrock/OpenSearch (로컬 stub)    │
│  - AWS SAM Local (Lambda 로컬 실행)        │
│  - LiteLLM 개발용 키 사용                  │
└────────────────────┬──────────────────────┘
                     │ git push / MR
                     ↓
┌─ 사내 GitLab ─────────────────────────────┐
│  - Group: bos-ai-rag                      │
│  - Protected Branches (main)              │
│  - CODEOWNERS (Platform 승인 필수)         │
│  - Merge Request Approval Rules           │
│  - GitLab CI (OIDC → AWS)                 │
└────────────────────┬──────────────────────┘
                     │ 배포 (OIDC 단기 토큰)
                     ↓
┌─ AWS VPC (Private) ───────────────────────┐
│                                            │
│  ┌─ Platform 영역 ──────────────┐          │
│  │  Terraform, IAM, VPC, KB      │          │
│  │  OpenSearch, Bedrock KB       │          │
│  └──────────┬────────────────────┘          │
│             ↓ 자원 제공                     │
│  ┌─ Pipeline 영역 ──────────────┐          │
│  │  Lambda (파서·핸들러)         │          │
│  │     ↓ LLM 호출                │          │
│  │  LiteLLM Gateway (ECS Fargate)│          │
│  │     ↓ (인증·쿼터·로깅)         │          │
│  │  Bedrock (VPC Endpoint)       │          │
│  └────────────────────────────────┘          │
└────────────────────────────────────────────┘
```

---

## 4. 저장소 — 사내 GitLab

### 4.1 사내 GitLab을 선택하는 이유

| 항목 | 사내 GitLab | GitHub (Enterprise/Cloud) |
|------|------------|--------------------------|
| IP/소스코드 사외 반출 | 내부망 내 유지 | 클라우드 경유 (정책 검토 필요) |
| 인증 연동 | 사내 LDAP/SSO 기연동 | 별도 설정 |
| 분리 멤버 계정 관리 | 기존 사번 기반 즉시 | 신규 발급 필요 |
| AWS 연동 | GitLab Runner + OIDC | GitHub Actions + OIDC |
| 비용 | 기존 라이선스 활용 | 추가 계약 |

RAG Farm 보안 원칙(사외 반출 리스크 통제)과 일관됩니다.

### 4.2 프로젝트 구조

```
bos-ai-rag/ (Group)
├─ platform-infra/          ← Platform팀 전용
│   ├─ terraform/
│   ├─ iam-policies/
│   └─ .gitlab-ci.yml (인프라 배포)
│
├─ pipeline-parsers/         ← 분리 멤버 주 작업
│   ├─ src/
│   │   ├─ package_parser/
│   │   ├─ port_classifier/
│   │   ├─ generate_parser/
│   │   └─ ...
│   ├─ tests/                (269 단위 테스트)
│   ├─ .gitlab-ci.yml        (Protected, Platform 작성)
│   └─ local-dev-kit/
│       ├─ mock_bedrock/
│       ├─ mock_opensearch/
│       └─ README.md
│
├─ pipeline-lambda/          ← Lambda 핸들러 코드
│   ├─ src/
│   ├─ tests/
│   └─ .gitlab-ci.yml
│
└─ dev-tools/                ← 로컬 개발 유틸리티
```

### 4.3 GitLab 거버넌스 설정

| 기능 | 설정 | 목적 |
|------|------|------|
| Protected Branches | `main`, `release/*` | 리뷰 없이 merge 불가 |
| CODEOWNERS | `.gitlab-ci.yml`, `terraform/`, `iam-policies/` → Platform팀 | 인프라 경로 수정 시 Platform 승인 |
| Merge Request Approval | 코드 2명 / 인프라 1명(Platform) | 다중 검토 강제 |
| Protected Variables | AWS 배포 자격증명 | Protected 브랜치에서만 접근 |
| Push Rules | Signed Commit, Secret Scanning | 시크릿 커밋 방지 |

### 4.4 AWS 연동 — OIDC 기반

**장기 AWS 액세스 키를 CI 변수에 절대 넣지 않습니다.** 모든 배포는 OIDC로 단기 토큰 발급.

```
GitLab CI 실행
    ↓
GitLab OIDC Identity Provider (JWT 발급)
    ↓
AWS IAM (OIDC Provider로 등록됨)
    ↓
AssumeRoleWithWebIdentity (1시간 유효 토큰)
    ↓
Lambda 코드 배포
```

---

## 5. LiteLLM 게이트웨이

### 5.1 왜 Bedrock 직접 호출 대신 LiteLLM을 두는가

```
[Lambda (파서)]  →  [LiteLLM Gateway]  →  [Bedrock]
                          ↓
                     통제 레이어:
                     ├─ 팀별/프로젝트별 API Key
                     ├─ 모델별 쿼터·레이트리밋
                     ├─ 비용 추적 (per-user, per-project)
                     ├─ 로깅·감사 (모든 호출 기록)
                     ├─ 프롬프트 인젝션 필터
                     ├─ PII 마스킹
                     └─ 모델 라우팅 (dev=Haiku, prod=Sonnet)
```

| 항목 | Bedrock 직접 | LiteLLM 경유 |
|------|------------|-------------|
| 비용 가시성 | CloudWatch만, 팀별 구분 어려움 | 팀/사용자/프로젝트별 실시간 집계 |
| 쿼터 통제 | AWS 계정 단위 (거칠음) | API Key 단위 정밀 제어 |
| 모델 교체 | 코드 수정 | 게이트웨이 설정만 변경 |
| 감사 로그 | CloudTrail (요약) | 프롬프트·응답 전체 기록 |
| 개발자 실수 방어 | 제한 없음 | 레이트리밋·스팸 차단 |

### 5.2 배포 아키텍처

```
┌─ VPC (Private) ──────────────────────────────────┐
│                                                   │
│  Lambda (파서)                                    │
│       ↓ (VPC endpoint, 내부 DNS)                  │
│  ALB / NLB                                        │
│       ↓                                           │
│  ECS Fargate (LiteLLM Proxy, 2+ task)             │
│       ↓                                           │
│  ├─ Redis (Rate limit · Response cache)          │
│  ├─ PostgreSQL (Usage · API Keys · Audit)        │
│  └─ Bedrock VPC Endpoint                         │
│              ↓                                    │
└─────────────────────────────────────────────────┘
              → Bedrock
```

### 5.3 API Key 정책

| 키 유형 | 발급 대상 | 쿼터 | 허용 모델 | 환경 |
|--------|---------|------|----------|------|
| `dev-*` | 분리 멤버 로컬 개발 | 낮음 | Haiku (개발용) | 로컬 PC |
| `staging-*` | 스테이징 Lambda | 중간 | Sonnet, Haiku | AWS 스테이징 |
| `prod-*` | 프로덕션 Lambda | 높음 | Sonnet, Opus | AWS 프로덕션 |
| `alpha-user-*` | Alpha 유저별 | 제한적 | Sonnet | 프로덕션 |

### 5.4 운영상 이점 (Alpha/Beta 맥락)

- **NPU 분석팀 4명 각자의 호출량·비용 실시간 집계**
- 이상 패턴 감지 (특정 유저가 갑자기 호출 100배 증가 등)
- 모델 교체(Opus → Sonnet) 시 **코드 수정 없이 설정만 변경**
- 향후 Claude API / Azure OpenAI 추가 시 **멀티 프로바이더 투명 라우팅**

---

## 6. IAM 거버넌스 — 3계층

### 6.1 Layer 1: Permissions Boundary (최상위 울타리)

분리 멤버 IAM 엔티티에 **Permissions Boundary** 강제 부착. 이 경계 밖으로는 어떤 정책도 효력 없음.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowPipelineDev",
      "Effect": "Allow",
      "Action": [
        "lambda:UpdateFunctionCode",
        "lambda:PublishVersion",
        "lambda:GetFunction"
      ],
      "Resource": "arn:aws:lambda:*:*:function:rag-pipeline-*"
    },
    {
      "Sid": "AllowOwnLogs",
      "Effect": "Allow",
      "Action": "logs:*",
      "Resource": "arn:aws:logs:*:*:log-group:/aws/lambda/rag-pipeline-*"
    },
    {
      "Sid": "DenyInfrastructure",
      "Effect": "Deny",
      "Action": [
        "iam:*",
        "ec2:*",
        "vpc:*",
        "kms:CreateKey",
        "kms:ScheduleKeyDeletion",
        "bedrock-agent:Create*",
        "bedrock-agent:Update*",
        "bedrock-agent:Delete*",
        "aoss:Create*",
        "aoss:Delete*",
        "s3:DeleteBucket",
        "s3:PutBucketPolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyDirectBedrock",
      "Effect": "Deny",
      "Action": "bedrock:InvokeModel",
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:PrincipalTag/BedrockAccess": "via-litellm"
        }
      }
    }
  ]
}
```

### 6.2 Layer 2: Role 분리

| Role | 대상 | 권한 | 비고 |
|------|------|------|------|
| `PipelineDev` | 분리 멤버 | 개발·디버깅 | Permissions Boundary 필수 |
| `PipelineDeployer` | GitLab CI | Lambda 코드 배포 | 사람은 못 씀, OIDC 전용 |
| `LiteLLMService` | ECS Task | Bedrock 호출 | LiteLLM Gateway만 보유 |
| `PlatformAdmin` | Platform팀 | 인프라 전반 | MFA 필수 |

### 6.3 Layer 3: Resource Naming 규칙

- Lambda 함수명: `rag-pipeline-*` prefix 강제
- 분리 멤버 권한은 해당 prefix에만 동작
- 이 prefix 밖 함수는 Platform팀만 생성·수정 가능

---

## 7. 로컬 개발 환경

### 7.1 분리 멤버 PC에 제공되는 것

| 항목 | 제공 방식 |
|------|---------|
| 파서 소스 코드 | GitLab clone |
| Python 환경 (venv/uv) | README 가이드 |
| Mock Bedrock/OpenSearch | `local-dev-kit/` 내 stub |
| AWS SAM Local | README 가이드 |
| LiteLLM 개발용 키 | Platform팀 발급 (dev-* 키) |
| 단위 테스트 러너 | `pytest` + 269개 회귀 케이스 |

### 7.2 분리 멤버가 로컬에서 할 수 있는 것

| 작업 | 가능 여부 |
|------|---------|
| 파서 코드 수정 | 가능 |
| 단위 테스트 실행 (AWS 연결 불필요) | 가능 |
| Mock 환경에서 통합 테스트 | 가능 |
| LiteLLM 개발 키로 Bedrock 테스트 | 가능 (쿼터 제한) |
| Lambda 로컬 실행 (SAM Local) | 가능 |
| 실 Lambda 배포 | **불가 — CI/CD로만** |
| 실 AWS 인프라 변경 | **불가 — Platform 전용** |

### 7.3 배포 플로우

```
[로컬 개발]
   ↓ git commit
[GitLab push]
   ↓ MR 생성
[CI 단계]
   ├─ 린트 (ruff, mypy)
   ├─ 단위 테스트 (269개 회귀)
   ├─ 보안 스캔 (Secret scanning, SAST)
   └─ Lambda 패키지 빌드
   ↓ Platform팀 리뷰 + CODEOWNERS 승인
[merge to main]
   ↓ 자동 배포
[스테이징 Lambda 배포]
   ↓ 스모크 테스트 (자동)
   ↓ 수동 승인
[프로덕션 Lambda 배포]
```

---

## 8. 도입 로드맵

| 단계 | 작업 | 주체 | 기간 | 의존성 |
|------|------|------|------|-------|
| 1 | 사내 GitLab 프로젝트 구조 세팅 + OIDC 연동 | Platform + 사내 Ops | 3일 | GitLab 관리자 협의 |
| 2 | Platform vs Pipeline repo 분리 | Platform | 3일 | 1 완료 |
| 3 | LiteLLM ECS Fargate 배포 (스테이징) | Platform | 1주 | VPC 확보 |
| 4 | LiteLLM 키 발급·쿼터 정책 설계 | Platform | 3일 | 3 완료 |
| 5 | Permissions Boundary 정의 + 샌드박스 계정 1개 | Platform | 1주 | — |
| 6 | 로컬 개발 키트 (Mock + 테스트 러너 + README) | Platform | 1주 | 2 완료 |
| 7 | GitLab CI/CD 배포 파이프라인 구축 (스테이징·프로덕션 분리) | Platform | 1주 | 2,5 완료 |
| 8 | 분리 멤버 온보딩 (1명씩 순차) | 공동 | 2주 | 1~7 완료 |

**총 약 4~5주.** Alpha(NPU 분석팀) 운영 중 병행 진행 가능.

---

## 9. 주의할 함정

### 9.1 GitLab 관련

| 함정 | 왜 위험한가 | 대응 |
|------|-----------|------|
| 자격증명을 CI 변수에 직접 저장 | 유출 시 광범위 피해 | OIDC 전용, 장기 키 금지 |
| `.gitlab-ci.yml`을 분리 멤버가 수정 가능 | 배포 스크립트 우회 | Protected + CODEOWNERS |
| Runner를 외부 호스팅 | 사외 반출 리스크 | 사내 or AWS VPC 내 Runner |
| 시크릿을 코드에 커밋 | IP 유출 | Secret Scanning + Pre-commit hook |

### 9.2 LiteLLM 관련

| 함정 | 왜 위험한가 | 대응 |
|------|-----------|------|
| SaaS 버전 사용 | IP·프롬프트 사외 반출 | 자체 호스팅 (VPC 내부) |
| Bedrock 직접 호출 경로 허용 | LiteLLM 우회 가능 | IAM Deny로 원천 차단 |
| DB 백업 미구비 | 과금·사용량 데이터 손실 | RDS 자동 백업 |
| 단일 Fargate task | 장애 시 전체 RAG 중단 | 2+ task, ALB 헬스체크 |
| 개발 키로 프로덕션 모델 호출 | 비용 통제 실패 | 키별 허용 모델 목록 명시 |

### 9.3 IAM 관련

| 함정 | 왜 위험한가 | 대응 |
|------|-----------|------|
| Terraform 접근 허용 | IAM 조작으로 권한 상승 | 절대 금지 |
| CloudWatch 전체 읽기 허용 | 타 팀 로그 노출 | 자기 로그 그룹만 |
| `bedrock:InvokeModel` 전체 허용 | LiteLLM 우회 | 태그 기반 조건부 Deny |
| Role의 AssumeRole 권한 과다 | 측면 이동 가능 | Trust policy 최소화 |

---

## 10. 보고용 요약

> **"사내 GitLab을 파이프라인 repo로 사용하여 IP 사외 반출 없이 분리 개발 체제를 구축합니다. Bedrock 호출은 LiteLLM 게이트웨이를 경유시켜 팀별 쿼터·비용·감사 로그를 중앙 통제합니다. 분리 멤버는 로컬에서 개발하고 GitLab CI/CD로만 Lambda에 배포되며, IAM Permissions Boundary로 인프라 접근과 Bedrock 직접 호출 경로는 원천 차단합니다. 이 구조 덕에 백여 명 규모 확장 시에도 거버넌스를 유지할 수 있습니다."**

### 핵심 3가지

1. **저장소 분리** — 사내 GitLab + OIDC + Protected Branches + CODEOWNERS
2. **호출 게이트웨이** — LiteLLM 경유 강제 (직접 Bedrock 호출 IAM Deny)
3. **IAM 3계층** — Permissions Boundary + Role 분리 + Resource Naming

---

## 11. 오픈 이슈

후속 논의 필요 사항:

- [ ] 사내 GitLab 관리자 협의 (OIDC Provider 등록, 리소스 할당)
- [ ] Runner 호스팅 방식 결정 (사내 물리 vs AWS EC2)
- [ ] LiteLLM DB 선택 (RDS PostgreSQL vs Aurora Serverless)
- [ ] 스테이징 환경 KB 데이터 (프로덕션 복제 vs 별도 샘플)
- [ ] 분리 멤버 선정 기준 및 온보딩 체크리스트
- [ ] 비용 책임 분리 (Platform vs Pipeline 팀별 예산)
- [ ] 감사 로그 보관 기간 (컴플라이언스 요구)

---

*End of Document*
