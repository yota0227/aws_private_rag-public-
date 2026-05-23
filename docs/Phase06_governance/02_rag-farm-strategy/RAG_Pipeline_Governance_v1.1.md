# RAG 파이프라인 거버넌스 v1.1 — 역할·워크플로우·시스템 구성

**문서 버전:** v1.1
**작성일:** 2026-05-12
**Supersedes:** [RAG_Pipeline_Governance_v1.0.md](./RAG_Pipeline_Governance_v1.0.md)
**관련 문서:** [RAG_Farm_Strategy_v1.5.md](./RAG_Farm_Strategy_v1.5.md)
**대상:** 경영진, Platform팀, 도메인 Lead, 분리 멤버 (설계자 개발자), Alpha/Beta 유저
**목적:** v1.0의 아키텍처 원칙 위에, **"누가 무엇을 어떻게 하는지"를 역할·워크플로우·시스템 사용법까지 구체화**

---

## TL;DR — SOC 디자인 엔지니어를 위한 5분 요약

이 문서가 길어서 다 읽기 부담스러운 SOC 엔지니어를 위해, 핵심 5문항으로 정리합니다. 자세한 내용은 본문 §1 이후를 참조.

### Q1. 이 RAG, 왜 만드나?

**AI 활용과 보안 거버넌스를 함께 확보**하기 위함입니다.

- 사내 RTL/IP는 ChatGPT나 Copilot 같은 외부 서비스에 올리기 어려움 (라이선스·NDA·수출통제 리스크)
- 동시에 "AI 사용 안 함"으로 가면 생산성 격차가 벌어질 수 있음
- 그래서 선택한 방식: **사내 폐쇄 환경 RAG** — IP는 사내에 두고, LLM 추론만 통제된 경로로 호출
- 이 시스템 자체가 **"IP를 안전하게 다루면서 AI를 활용하는 사내 표준 인프라"** 역할

### Q2. 어떻게 동작하나?

시스템에는 **서로 다른 두 가지 흐름**이 존재합니다. 같은 다이어그램에 섞으면 헷갈리므로 분리해서 봅니다.

---

#### 흐름 A — 데이터 적재 (Steward → S3 → 자동 인덱싱)

IP가 들어와서 RAG 인덱스에 반영되는 일회성 흐름. **Data Steward가 트리거**.

```
[폐쇄망 - Data Steward (RTL 데이터 관리자)]
   │ 라이선스·EAR 검토
   ↓ ① rag-inbox CLI로 S3 업로드 (VPN 경유)
[AWS VPC]
   ② S3 (도메인 prefix, KMS 암호화)
        │ ObjectCreated 이벤트
        ↓ (트리거)
   ③ Lambda Parser     IP 텍스트 → Chunk
        ↓
   ④ Lambda Indexer    Chunk → 임베딩 요청 → OpenSearch upsert
        │              (임베딩은 LiteLLM 경유 Bedrock Cohere)
        ↓
   ⑤ OpenSearch Serverless (벡터 인덱스)  ← RAG 인덱스 완성
        ↓
   Slack 알림: "indexed N chunks"
```

**한 줄로:** Steward 업로드 → S3 트리거 → Parser → Indexer → Bedrock 임베딩 → OpenSearch에 저장.

---

#### 흐름 B — 사용자 쿼리 (RAG 활용)

인덱스가 만들어진 다음, **사용자가 폐쇄망에서 AI Tool로 RAG를 활용**하는 반복 흐름.

```
[폐쇄망 - 사용자 (설계자 / 분석가 / End User)] ★ 반드시 폐쇄망
   │ Claude Desktop + MCP 클라이언트
   ↓ ⓐ 질문
[AWS VPC] (VPN 경유)
   ⓑ MCP Server
        ↓
   ⓒ Lambda Query     사용자 질문 → 관련 Chunk 검색
        ↓
   ⑤ OpenSearch Serverless (벡터 인덱스 조회)
        ↓ relevant chunks
   ⓓ LiteLLM Gateway   Claude 호출 (감사·쿼터·비용 기록)
        ↓
   ⓔ Bedrock Claude    응답 생성 (chunks를 컨텍스트로)
        ↓
   MCP 경유 응답
[폐쇄망 사용자에게 응답 표시]
```

**한 줄로:** 사용자 질문 → MCP → Query Lambda → OpenSearch 검색 → LiteLLM → Bedrock Claude → 응답.

---

#### 왜 사용자 쿼리도 폐쇄망에서만 가능한가 ★

이 부분이 거버넌스의 핵심입니다.

- RAG의 응답에는 **인덱싱된 RTL/IP 정보가 컨텍스트로 포함**되어 사용자에게 노출됩니다
- 즉 RAG를 일반망(인터넷 PC)에서 호출할 수 있게 하면, **폐쇄망 안에 있던 RTL/IP가 일반망으로 흘러나오는 것과 동일**해집니다
- 비유하면 사내 SoC GitLab을 그대로 인터넷에 노출시키는 것과 같은 효과
- 따라서 **AI Tool(Claude Desktop + MCP) 자체가 폐쇄망 PC에서만 동작**하도록 제한합니다
  - MCP 엔드포인트는 폐쇄망 VPN 경유로만 도달 가능
  - 일반망에서는 인증 자체가 거부됨
- Data Steward의 업로드 흐름과 사용자 쿼리 흐름이 **둘 다 폐쇄망 안에서만 일어나는 이유**가 여기에 있습니다

---

**중요:** 흐름 A의 ①에서 IP 업로드는 **Data Steward 권한자만 수행**합니다. 설계자라고 해서 자동으로 업로드 권한이 있는 것은 아니며, 도메인별로 지정된 Data Steward(보통 IP integration manager 또는 design lead)가 라이선스·EAR 검토 후 업로드합니다. 자세히는 §2.3 (3) Data Steward 참조.

**파서 코드 배포는 별도 흐름:** 설계자가 `parser.py`를 업데이트하면 사내 GitLab MR → Runner CD로 Lambda Parser(③)가 갱신됩니다. 이는 **흐름 A·B와 평행한 별개 흐름**으로 §5에서 상세히 다룹니다.

**구조의 특징:**
- **AWS 기반** — 사내 GPU 자체구축 대비 운영 부담이 작음 (현재 AWS credit 활용, 2027 중반까지)
- **폐쇄망 + VPN** — IP가 인터넷 영역에 닿지 않음
- **LiteLLM 단일 게이트웨이** — 모든 LLM 호출의 감사·쿼터·비용 정보가 한 곳에 모임
- **도메인별 분리 (S3 prefix · KMS · OpenSearch collection)** — 권한 있는 사람만 해당 도메인 RTL/IP에 접근

### Q3. RAG 개발한다고 했을 때, 나는 뭘 하나?

**한 줄로: Lambda에 올라갈 "파서"를 작성합니다.**

- 시스템 전체(임베딩·벡터 DB·LLM 호출·인프라)는 **Platform이 미리 구축해 둠**
- 설계자가 주로 작성하는 코드는 `parsers/{도메인}/parser.py` 안의 **`parse(raw_text, source_path) → list[Chunk]`** 함수
- AWS 콘솔·Terraform·Bedrock SDK·OpenSearch API 등은 Platform 영역이라 직접 다루지 않습니다 (권한도 따로 부여하지 않습니다)
- 본업이 SOC 설계인 분의 시간 부담을 줄이기 위한 의도적으로 좁힌 작업 범위입니다

**별도 안내:** RTL/IP 파일을 시스템에 올리는 작업(`rag-inbox upload`)은 **Data Steward 롤**을 받은 분이 수행합니다 — 라이선스·NDA·수출통제(EAR) 검토가 필요한 영역이기 때문에 도메인별로 1~2명만 권한을 받습니다. 설계자(파서 개발자)와는 별도 롤이며, 같은 사람이 두 롤을 겸임할 수도 있지만 권한·책임은 분리되어 발급됩니다. 자세히는 §2.3 (3) Data Steward 참조.

### Q4. 개발한 파서, 어떻게 시스템에 반영되나?

```
1. 폐쇄망 PC 로컬에서 parser.py 작성
2. pytest로 단위 + 스모크 통과 확인
3. 사내 GitLab에 MR(Merge Request) 생성
4. 3 approval 받음:
     - Platform 1명 (인프라·보안 관점)
     - 같은 도메인 peer 1명 (도메인 정합성)
     - LLM 봇 1명 (자동 정적 분석)
5. main 브랜치 merge → GitLab Runner 자동 배포
6. Lambda 업데이트 → 인덱스 재생성 자동 트리거
7. Claude Desktop + MCP로 결과 확인
```

**설계자 입장에서 능동적으로 하는 작업은 "MR 생성" 한 번**입니다. 배포는 merge 시 자동으로 진행되며, Jenkins UI 같은 추가 도구는 다룰 필요가 없습니다. 자세히는 §5 (E2E 워크플로우).

### Q5. 만약 내가 만들고 싶은 RAG가 따로 있다면?

**개인적으로 진행하기보다는, 계획을 정리해서 도메인 Lead 또는 Platform에 공유해 주시면 함께 검토해 보면 좋습니다.** 다음 두 가지를 함께 살펴보게 됩니다:

**(1) 보안 거버넌스 — 가장 먼저 살펴봄**
- 어떤 데이터를 다루는가 (자사 RTL / 구매 IP / 벤더 NDA 대상 등)
- 데이터 등급에 따라 폐쇄망·KMS·도메인 분리 적용 수준이 결정됨
- 이 검토에서 적합 판정이 나야 시스템 편입을 진행할 수 있습니다

**(2) 경제성 — RAG는 LLM 호출 비용이 따라옴**
- LLM 추론은 일정한 비용이 발생합니다. 일반적으로 두 가지 옵션이 있고 각각 부담이 다릅니다:
  - **로컬 GPU**: 서버급 GPU 구매 + 전력·냉각·유지보수 + 보안 인증 자체 부담
  - **인터넷 API (OpenAI 등)**: 사용량 과금 + IP 외부 송출 리스크 → 사내 IP에는 사용이 어려움
- BOS-AI RAG Farm은 이 두 가지 부담을 **AWS + credit 조합**으로 완화하고 있는 형태입니다
  - Credit은 2027년 중반까지 유효하고, 이후 실비 전환 예정
  - 그래서 처음부터 비용 효율적 구조를 함께 잡아두는 것이 안정적입니다
- 새 RAG 아이디어도 이 경제 구조 안에서 검토되며, 별도 GPU·별도 클라우드는 현재 환경에서 운영 부담이 큽니다

**(3) 절차**
- 도메인 Lead 또는 Platform에 간단한 제안서 공유
- 보안·경제성·기존 Contract와의 정합성 함께 검토
- 적합한 경우 **§4.5 신규 도메인 온보딩 절차**로 편입

### Q6. (보너스) BHRC가 다루는 RAG 범위는?

- **현재**: NPU RTL (Trinity 등 자사 RTL) 대상으로 RAG 개발 중. v9.x 단계
- **곧**: 자사 BOS RTL 도 대상에 포함 예정 — 같은 RAG로 활용 가능하게 확장 중
- **신규 추진**: **SNPS IP** — 본 v1.1 거버넌스의 직접 대상. 설계자 본인이 파서 개발자
- **고려 사항**: 컴플라이언스 (수출통제·벤더 라이선스·AI 학습 조항)는 도메인별로 별도 검증 — 단순한 기술 작업이 아님

---

> **요약의 요약:** 시스템은 이미 준비되어 있고, 설계자는 `parse()` 함수에 집중하면 됩니다. 그 외는 정의된 절차를 따르고, 새 RAG 아이디어는 보안·경제성 검토를 거쳐 시스템에 합류합니다. 이는 기술적 선호의 문제라기보다, 회사의 예산 구조와 보안 승인 환경에 맞춰 함께 정한 운영 방식입니다.

---

## 0. v1.0 → v1.1 변경점 요약

| 영역 | v1.0 | **v1.1** |
|------|------|---------|
| 초점 | 원칙·통제·보안 아키텍처 | **+ 역할별 일상 업무·워크플로우·시스템 사용법** |
| 역할 정의 | Platform vs 분리멤버 2분 | **5개 역할 상세 정의 (§2)** |
| 시스템 구성요소 | 단편 설명 | **§3에서 컴포넌트별 정리 — 폐쇄망·AWS·연결 레이어** |
| 업무 방식 | 추상적 | **§4에서 역할별 "온보딩/일상/문제대응" 3단계** |
| E2E 플로우 | merge→deploy 수준 | **§5에서 RTL 업로드 → 파서 개발 → 배포 → 인덱싱 → 검증 전 단계** |
| 후속 문서 | 미정 | **§7에서 3개 가이드 문서 범위·순서 확정** |
| Platform Contract | 묵시적 | **§3.5 신설 — RAG 스택 단일화 규약 (Credit·HW·보안 근거 + Issue Report + Technical Enforcement)** |
| SOC 엔지니어 onboarding | 없음 | **TL;DR 5분 요약 신설** (문서 최상단) |
| 데이터 업로드 권한 | 묵시적 (설계자 자유) | **§2.3 (3) Data Steward 롤 신설 — IP 업로드는 라이선스·EAR 검토를 거친 권한자만 수행. Developer와 분리 발급** |

---

## 1. 배경

v1.0은 "왜 폐쇄망이어야 하고 어떤 통제가 걸려야 하는가"를 정의했습니다. 하지만 실제 운영이 시작되면 다음 질문들에 답이 필요합니다:

- **설계자가 월요일 출근해서 무엇부터 해야 하나요?**
- **새 SNPS IP 파일이 들어왔을 때 어떤 경로로 S3에 올라갑니까?**
- **파서를 하나 만들었습니다. Lambda에 어떻게 반영되죠?**
- **인덱스 재생성은 누가 언제 실행합니까?**
- **Platform팀은 이 모든 걸 어떻게 모니터링하나요?**

v1.1은 **"프로세스·도구·인터페이스" 레벨의 구체성**을 제공합니다.

---

## 2. 역할 정의 (Who)

### 2.1 역할 매트릭스

| # | 역할 | 소속 | 본업 여부 | 주 사용 도구 | 접근 권한 |
|---|------|------|---------|----------|---------|
| 1 | **Platform 운영자** | Platform팀 | 본업 | AWS 콘솔, Terraform, GitLab, LiteLLM 관리 UI | AWS 전체, GitLab 전체, CODEOWNERS |
| 2 | **도메인 Lead** | RTL/SNPS/Spec 각 팀 | 부업 (주 업무의 20%) | GitLab MR, MCP 검증, Slack | 자기 도메인 repo 경로, 도메인 S3 prefix (read), MCP |
| 3 | **Data Steward (데이터 관리자)** ★ | RTL/SNPS/Spec 각 팀 (도메인별 별도 지정) | 부업 | `rag-inbox` CLI, MCP | **자기 도메인 IP 파일 업로드·태그·철회 권한 (도메인 내 유일)** |
| 4 | **도메인 Developer (설계자)** | SNPS 설계팀 등 | **부업** (주 업무의 10~15%) | 폐쇄망 PC, GitLab, 로컬 pytest, MCP | 자기 도메인 `parsers/*`, `lambda_handlers/*`, 로컬 mock. **IP 업로드 권한 없음** |
| 5 | **Reviewer** | 3명 혼합 | 부업 | GitLab MR | MR 승인 권한 |
| 6 | **End User (Alpha/Beta)** | NPU 분석팀, DV팀 등 | 본업 (RAG 사용자) | Claude Desktop + MCP | 도메인별 RAG 쿼리 |

**핵심 분리:** Data Steward(③)와 도메인 Developer(④)는 **별도 롤**입니다. 같은 사람이 겸임할 수는 있지만, **권한과 책임이 분리되어 발급**됩니다 — "내가 설계자니까 내 IP를 업로드한다"는 자동 권한이 아닙니다. §2.3에서 상세히 다룹니다.

### 2.2 각 역할의 책임·권한·목표

#### (1) Platform 운영자

- **책임**: 시스템 가용성, 보안 통제, 비용 관리, 신규 도메인 온보딩 지원, 장애 대응
- **권한**: AWS 전체, GitLab 관리자, LiteLLM 관리자, MCP 서버 운영
- **KPI**: 가용성 99%+, 배포 성공률 95%+, 감사 지적 0건, 온보딩 시간 < 2주
- **일상 비율**: 신규 구축 30% / 운영 40% / 장애 대응 20% / 도메인 지원 10%

#### (2) 도메인 Lead

- **책임**: 자기 도메인 RAG 품질, 스모크 테스트 maintain, MR 최종 승인, 설계자 온보딩
- **권한**: 자기 도메인 `parsers/*` CODEOWNERS, 스모크 테스트 수정, MR approve
- **KPI**: 자기 도메인 RAG accuracy, 스모크 커버리지, Alpha 유저 만족도
- **일상 비율**: MR 리뷰 40% / 스모크 관리 20% / 설계자 지원 30% / 기획 10%

#### (3) Data Steward (데이터 관리자) ★

- **책임**: 자기 도메인의 IP/RTL **데이터 라이프사이클 관리** — 업로드 자격 판단, 라이선스 메타 부착, 철회·아카이브
  - 어떤 IP를 RAG에 인덱싱할지 판단 (벤더 NDA·EAR 등급 검토)
  - `rag-inbox upload` 시점에 라이선스/ECCN/버전 태그 부착
  - IP 폐기 시 인덱스에서 철회·감사 로그 확인
  - 분기별 인덱싱 자산 목록 점검
- **권한**: 자기 도메인 `rag-inbox` CLI **업로드/철회/리인덱스 권한** (도메인 내 유일)
- **KPI**: 미승인 IP 인덱싱 건수 (0 유지), 라이선스 메타 누락률 (0 유지), IP 철회 SLA
- **일상 비율**: 부업, 도메인당 1~2명만 지정. 신규 IP 도입 시점에 활동 집중

**선임 기준 권장:**
- 도메인 내에서 **IP 라이선스·NDA·수출통제 사항**을 이미 인지하고 있는 사람 (예: IP integration manager, design lead)
- 사내 수출통제 교육 이수 완료
- 도메인 Lead 또는 Platform이 추천·승인

**Developer와 분리하는 이유:**
- 설계자가 자유롭게 IP를 인덱싱하면 라이선스·EAR 검토가 우회될 수 있음
- "이 IP는 RAG에 올려도 되는가"는 **법적·계약적 판단**이며 기술적 판단과 별개
- 감사 발생 시 "누가 왜 이 파일을 인덱싱했는가"를 단일 책임자로 추적 가능해야 함

#### (4) 도메인 Developer (설계자)

- **책임**: 파서 구현, Lambda 핸들러 수정, 단위 테스트, 로컬 스모크 통과
- **권한**: 폐쇄망 PC, 자기 도메인 `parsers/*` 쓰기, 로컬 LiteLLM dev 키
- **권한 없음**: **IP 파일 업로드·철회 (Data Steward 영역)**, 타 도메인 코드 수정, AWS 인프라
- **KPI**: PR 머지 성공률, 스모크 회귀 발생 건수 (낮을수록 좋음)
- **일상 비율**: 이 사람은 **본업이 설계**. RAG 작업은 주당 1~2회 PR 수준
- **핵심 경험 목표**: "설계 업무 방해 최소화. 파서 한 번 만들면 내가 원하는 질문에 답이 잘 나오도록 유지"

#### (5) Reviewer

- **Platform Reviewer** (1명, Platform팀에서 차출)
  - 관점: CI/CD·IAM·secret·LiteLLM 통제 레이어
  - 약 15분/MR
- **Peer Reviewer** (1명, 동일 도메인 또 다른 설계자)
  - 관점: 도메인 정합성, 파서 해석 오류
  - 약 30분/MR
- **LLM Bot Reviewer** (1봇, Claude via LiteLLM)
  - 관점: 정적 분석, 회귀 risk, secret 패턴, 프롬프트 인젝션
  - 자동 (MR 오픈 시 즉시)

#### (6) End User

- **책임**: RAG 쿼리, 결과 피드백 (Slack 채널)
- **권한**: 도메인 RAG MCP 접근 (Claude Desktop)
- **KPI (역산)**: 월간 쿼리 수, 피드백 positive rate
- **워크플로우**: v1.1의 직접 대상은 아님. 별도 **End User Guide**에서 다룸

---

## 3. 시스템 구성요소 (What must be built)

### 3.1 컴포넌트 맵

```
┌─ 폐쇄망 (Closed Network) ─────────────────────────────────────┐
│                                                              │
│  [1] 사용자/개발자 PC (폐쇄망 필수)                            │
│      모든 사용자(Steward·Developer·End User) 공통 요구:         │
│      ├─ 폐쇄망 OS 이미지                                       │
│      ├─ Claude Desktop + MCP 클라이언트  ← RAG 사용 (모든 사용자)│
│      │   ※ AI Tool 자체가 폐쇄망에서만 인증·동작                 │
│      │     (일반망 사용 시 RTL/IP가 일반망으로 흐름)             │
│      ├─ Steward 추가: rag-inbox CLI                            │
│      └─ Developer 추가:                                        │
│          ├─ VS Code / IDE                                     │
│          ├─ Python + uv (사내 PyPI 미러 경유)                  │
│          ├─ Git + GitLab CLI                                  │
│          ├─ Docker (사내 Registry 미러)                        │
│          └─ LiteLLM SDK (dev-{domain}-* 키)                    │
│                                                              │
│  [2] 사내 GitLab (기존 인프라 활용)                             │
│      ├─ bos-ai-rag Group                                     │
│      ├─ Protected Branches, CODEOWNERS                       │
│      ├─ OIDC Identity Provider                                │
│      └─ MR Webhook → LLM Bot                                  │
│                                                              │
│  [3] GitLab Runner 호스트 (신규 구축)                          │
│      ├─ 도메인별 Runner 태그 (rtl, snps, spec)                 │
│      ├─ Python 빌드 환경 (사내 미러 경유)                       │
│      ├─ AWS CLI + OIDC 통합                                   │
│      └─ VPN 엔드포인트 접근 권한                               │
│                                                              │
│  [4] 사내 PyPI Mirror (선결 조건, 기존 있으면 재사용)           │
│  [5] 사내 Docker Registry Mirror (선결)                       │
│  [6] RTL/IP Inbox System ★ (신규, §3.4에서 상세)              │
│                                                              │
└─────────────────────┬────────────────────────────────────────┘
                      │ VPN (화이트리스트 엔드포인트만)
                      ↓
┌─ AWS VPC (Platform 영역) ─────────────────────────────────────┐
│                                                              │
│  [7] S3 버킷 (도메인별 prefix, KMS 암호화)                      │
│      ├─ rtl/          (RTL 원본)                              │
│      ├─ snps_ip/      (SNPS IP 원본, 별도 KMS 키)              │
│      ├─ spec/         (Spec 원본)                             │
│      └─ lambda-pkgs/  (빌드된 Lambda zip)                      │
│                                                              │
│  [8] Lambda 함수 (도메인별)                                    │
│      ├─ rag-pipeline-rtl-parser-*                             │
│      ├─ rag-pipeline-snps-parser-*                            │
│      ├─ rag-pipeline-rtl-indexer                              │
│      ├─ rag-pipeline-snps-indexer                             │
│      ├─ rag-pipeline-rtl-query                                │
│      ├─ rag-pipeline-snps-query                               │
│      └─ rag-pipeline-llm-review-bot                           │
│                                                              │
│  [9] OpenSearch Serverless                                    │
│      ├─ rtl-collection                                        │
│      ├─ snps-ip-collection (별도 collection)                   │
│      └─ spec-collection                                       │
│                                                              │
│  [10] Bedrock (KB + Invoke)                                   │
│       VPC Endpoint only, direct call deny                    │
│                                                              │
│  [11] LiteLLM Gateway (ECS Fargate)                           │
│       ├─ ALB/NLB (VPN 내부 DNS)                                │
│       ├─ Redis (rate limit·cache)                            │
│       └─ RDS PostgreSQL (키·사용량)                            │
│                                                              │
│  [12] MCP Server (신규)                                        │
│       ├─ 도메인별 read-only API                                │
│       ├─ Claude Desktop 인증 (OAuth or key)                    │
│       └─ VPN 경유 폐쇄망 도달 가능                              │
│                                                              │
│  [13] 모니터링 · 알림                                           │
│       ├─ CloudWatch (로그·메트릭)                              │
│       ├─ CloudTrail (감사)                                     │
│       ├─ Slack/Teams Webhook (배포·장애 알림)                   │
│       └─ IAM Access Analyzer (분기별 권한 감사)                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 구축 우선순위

| 우선순위 | 컴포넌트 | 이유 |
|--------|---------|-----|
| **P0 (선결)** | [4] PyPI Mirror, [5] Docker Mirror | 폐쇄망 개발 자체가 불가 |
| **P0 (선결)** | [7] S3 도메인 분리 구조 | RTL 저장 없이 아무것도 못 함 |
| **P1 (기반)** | [2] GitLab 구성, [3] Runner, [6] Inbox | 개발·배포 파이프라인 뼈대 |
| **P1** | [11] LiteLLM + [10] Bedrock 연결 | LLM 호출 가능해짐 |
| **P2 (핵심)** | [8] Lambda (parser + indexer + query), [9] OpenSearch | RAG 본체 |
| **P2** | [12] MCP Server | 유저 인터페이스 |
| **P3** | [1] 설계자 PC 셋업 | 인프라 준비 후 단계 |
| **P3** | LLM Review Bot, [13] 모니터링 | 품질 레이어 |

### 3.3 도메인별 Lambda 함수 구성

각 도메인은 **3종 Lambda**로 구성:

| Lambda | 역할 | 트리거 | 호출자 |
|-------|------|------|------|
| `*-parser-*` | RTL/IP → 구조화된 chunk | S3 PutObject (`{domain}/raw/**`) 또는 manual invoke | Inbox, re-parse 이벤트 |
| `*-indexer` | chunk → 임베딩 → OpenSearch | parser 완료 이벤트 또는 manual invoke | parser, re-index 이벤트 |
| `*-query` | 유저 쿼리 → 리트리벌 → Claude 응답 | API Gateway / MCP 호출 | MCP, End User |

**배포 대상 = parser + indexer**. query Lambda는 변경 빈도 낮음 (Platform 소유).

### 3.4 RTL/IP Inbox 시스템 ★ (신규 설계 대상)

도메인 데이터(IP/RTL)는 AWS에 직접 접근하지 않고 **폐쇄망에서 S3로 안전하게 진입하는 전용 경로**가 필요합니다.

**누가 업로드하는가 — Data Steward로 한정**

Inbox는 **Data Steward 롤(§2.3 (3))에 부여된 권한자만 사용**합니다. 도메인 Developer(설계자)가 자동으로 사용할 수 있는 도구가 아닙니다. IAM 그룹과 OIDC 클레임으로 분리됩니다:

| 그룹 | 멤버 | 권한 |
|-----|-----|-----|
| `snps-data-stewards` | SNPS 도메인 Data Steward 1~2명 | `rag-inbox upload/reindex/remove` 가능 |
| `snps-developers` | SNPS 도메인 설계자(파서 개발자) | Inbox 사용 불가, MCP 조회만 |

**옵션 비교:**

| 옵션 | 설명 | 장점 | 단점 |
|-----|------|-----|-----|
| **A. GitLab LFS** | RTL을 Git LFS로 관리, Runner가 S3로 sync | 기존 GitLab 활용 | 대용량 RTL 부적합, 히스토리 부담 |
| **B. Web UI (폐쇄망)** | 폐쇄망 웹앱, 업로드 → presigned URL → S3 | Steward 친화 | 웹앱 구축·유지 비용 |
| **C. CLI Tool** ★ | `rag-inbox upload <file>` 폐쇄망 CLI, OIDC 토큰으로 presigned URL 획득 | 경량, 자동화 친화 | CLI 배포·업데이트 |
| **D. 파일 공유 드라이브 → 주기 sync** | 사내 공유 폴더에 올리면 Runner가 주기 pickup | 익숙함 | 감사 약함, 지연 발생 |

**권장: C (CLI Tool) + D (공유 폴더 폴백).**

```
[Data Steward PC] (도메인 내 권한자만)
   $ rag-inbox upload \
       --domain snps_ip \
       --file designware_axi.sv \
       --tag v2.1 \
       --license-tag "SNPS-NDA-2024" \
       --ear-eccn "3D991"
   ↓ (OIDC로 Platform API 인증)
[Inbox API (폐쇄망 Lambda 또는 AWS Lambda)]
   ↓ Steward 권한 확인 (IAM group: {domain}-data-stewards)
   ↓ 라이선스/EAR 메타 필수 항목 검증
   ↓ S3 presigned PUT URL 생성 (TTL 10분, snps_ip/raw/ prefix 한정)
[CLI이 파일 업로드 (VPN 경유)]
   ↓ S3 PutObject (KMS 암호화 + 메타 부착)
[S3 Event → parser Lambda 자동 트리거]
   ↓
[파싱 → indexer Lambda → OpenSearch]
   ↓
[Slack 알림 + Inbox 상태 DB 기록 (Steward 식별자 포함)]
```

**Inbox 명령어와 권한 요구:**

| 명령 | 설명 | 필요 권한 |
|-----|------|---------|
| `upload` | 파일 업로드 (라이선스·EAR·버전 태그 필수) | Data Steward |
| `list` | 도메인 내 인덱싱된 파일 목록 + 상태 | Data Steward, Lead, Developer (조회) |
| `status <job-id>` | 특정 업로드의 처리 단계별 상태 | Data Steward, Lead |
| `reindex <file>` | 파서 버전업 시 기존 파일 재인덱싱 | Data Steward |
| `remove <file>` | 인덱스 철회 (감사 로그 남김) | Data Steward + Platform 더블 승인 |

**감사/통제 장점:**
- 업로드 이벤트 전량 CloudTrail + Inbox DB 기록 (**누가 어떤 IP를 어떤 라이선스 등급으로 올렸는지** 단일 책임자 추적)
- 도메인 간 cross-upload 차단 (snps-data-stewards만 snps_ip/* 에 업로드 가능)
- 라이선스·EAR 메타 누락 업로드 자동 거부
- 대량 업로드·이상 패턴 탐지 (하루 100개 이상 등)
- 분기별 인덱싱 자산 점검 시 Steward별 활동 리포트 제공

---

## 3.5 Platform Contract — RAG 스택 공통 규약

### 3.5.1 왜 공통 규약이 필요한가

BOS-AI RAG Farm은 세 가지 외부 환경 위에 성립합니다. 이 환경들은 Platform팀이 단독으로 변경할 수 있는 영역이 아니므로, 공통 규약(Contract)도 그에 맞춰 설계되어 있습니다.

**(1) AWS Credit + 장기 경제 지속성**

- 2027년 중반까지 AWS credit으로 운영 비용을 상쇄하고 있습니다 (현재 월 $2,000+ 규모, credit 여유 있음)
- Credit은 AWS 서비스 사용을 전제로 제공되는 구조이므로, 타 스택을 함께 운영하면 credit 활용 효과가 떨어집니다
- 2027년 중반 이후에는 실비 전환이 예정되어 있고, 그 시점에도 시스템을 계속 사용해야 합니다 (그때까지 축적될 도메인·데이터·유저 때문)
- 단일 스택은 비용 예측과 최적화에 도움이 됩니다:
  - Sonnet → Haiku 일괄 교체 가능
  - OpenSearch 샤드·임베딩 호출량 공통 최적화
  - 도메인별 비용 분석 가능
- 도메인마다 스택이 다르면 비용 최적화 작업이 어려워지고, 실비 전환 시점에 운영 부담이 커질 수 있습니다
- 현재가 공통 규약을 잡기에 가장 좋은 시기입니다. 도메인·유저가 늘어난 뒤에는 통일이 어렵습니다

**(2) HW 자체구축의 경제적 부담**

- 동일 급 GPU 서버 구축 시 초기 CapEx + 전력·냉각·유지보수 비용 지속 발생
- 보안 거버넌스(RTL·IP 취급 수준)를 자체 호스팅으로 충족하면 AWS 대비 부담이 큽니다
- AWS + credit 조합이 이 두 부담을 함께 헷지하는 현실적 선택입니다

**(3) 보안 거버넌스 승인 완료**

- 사내 보안팀·법무·수출통제 담당이 현 스택(VPC·IAM·KMS·LiteLLM·OpenSearch)을 RTL/IP 취급용으로 이미 승인했습니다
- 다른 스택을 도입하려면 보안 재심사가 필요하고, 일반적으로 수개월이 소요됩니다

**정리:** Contract는 단순한 기술 선호의 결과가 아니라, **계약·예산·보안 승인이라는 외부 환경에 맞춘 공통 규약**입니다. Credit이 충분한 지금도 규약을 단단히 잡아두는 이유는, Credit 종료(2027 중반) 이후에도 시스템이 안정적으로 유지되도록 하는 설계 의도 때문입니다.

### 3.5.2 2단 구조 — Contract · Template

```
┌─────────────────────────────────────────────────────────┐
│  [Contract]  공통 필수 영역 (Platform 관리)               │
│  LLM 호출 경로, 벡터 DB, Lambda runtime, IAM, 메타 스키마 │
│       ↓ 이 위에서                                         │
│  [Template]  Platform 제공, 설계자 일부 수정              │
│  Lambda handler 골격, 공통 util, chunk 스키마              │
│       ↓ 그 안에서                                         │
│  [Freedom]   설계자 자유 구현 영역                         │
│  parsers/{domain}/parser.py 의 parse() 함수                │
└─────────────────────────────────────────────────────────┘
```

Contract 자체의 변경은 §3.5.1의 세 가지 외부 환경 모두에 영향을 주므로, 개별 개발 단위에서 수정하기는 어렵습니다. 대신 **Issue Report**(§3.5.6) 채널을 통해 문제를 공유하면 Platform이 검토합니다.

### 3.5.3 Contract — 공통 필수 영역

다음 항목은 시스템 일관성과 보안·감사를 위해 모든 도메인에서 공통으로 따르는 영역입니다.

| 영역 | 공통 규약 | 이유 |
|-----|---------|-----|
| **LLM 호출** | LiteLLM Gateway 경유 (`bedrock:InvokeModel` 직접 호출은 IAM에서 비활성화) | 감사·비용·쿼터 중앙 관리 |
| **임베딩 모델** | Platform 승인 모델 사용 (기본: Bedrock Cohere Embed v4 via LiteLLM) | 도메인 간 일관성 |
| **벡터 DB** | OpenSearch Serverless. 도메인별 collection은 Platform이 provision | 보안·백업·성능 중앙 관리 |
| **Lambda Runtime** | Python 3.12 + Platform 제공 base layer | 보안 패치·라이브러리 버전 관리 |
| **Lambda IAM Role** | Platform이 정의한 Role을 사용 | Permissions Boundary 유지 |
| **메타데이터 스키마** | `doc_id`, `chunk_idx`, `source_path`, `domain`, `ingested_at`, `kms_key_id` 필수 | Cross-domain 조회·감사 |
| **Handler 시그니처** | `parser_handler(event, context)`, `indexer_handler(event, context)` 통일 | Lambda 이벤트 chain 일관성 |
| **로깅 포맷** | Platform util `log_event()` 경유 structured JSON | CloudWatch Insights 일관성 |
| **시크릿 주입** | 환경변수 + KMS 복호화 권장 (코드 하드코딩은 지양) | IP 유출 방지·감사 |
| **외부 네트워크 호출** | Lambda VPC·엔드포인트는 Platform 관리. 추가 외부 호출은 사전 합의 필요 | 폐쇄망 원칙 유지 |

### 3.5.4 Template — 설계자의 작업 공간

Repo에는 항상 다음 구조가 준비되어 있습니다. 설계자는 **★ 표시된 영역**을 중심으로 작업합니다.

```
parsers/snps_ip/
├─ parser.py              ★ 설계자 자유 구현
│     def parse(raw_text: str, source_path: str) -> list[Chunk]:
│         """SystemVerilog/Verilog 등 IP 텍스트를 Chunk 리스트로 변환"""
│         ...
├─ patterns.py            ★ 설계자 자유 (헬퍼)
├─ __init__.py            (Platform 관리)
├─ requirements.txt       △ Platform allowlist 내에서 추가 가능
└─ README.md              ★ 파서 로직 설명

lambda_handlers/
└─ snps_ip_handler.py     (Platform 제공·관리)

tests/
├─ unit/snps_ip/          ★ 설계자 작성 (parser 단위 테스트)
└─ smoke/snps_ip/         △ Lead + Platform 공동 승인

platform_contract/        (Platform 소유 공통 모듈)
├─ chunk.py               # Chunk dataclass · 스키마 검증
├─ llm_client.py          # LiteLLM 래퍼
├_ logging_util.py        # structured 로깅
└─ metadata.py            # 필수 메타 필드 helper
```

설계자가 작성하는 코드의 대부분은 `parser.py` 한 파일에 집중됩니다. Bedrock·OpenSearch·IAM·S3 호출은 Platform template이 처리하므로, 설계자는 도메인 파싱 로직에만 집중하면 됩니다.

### 3.5.5 Chunk 스키마

모든 도메인 파서는 다음 형태로 반환:

```python
@dataclass
class Chunk:
    text: str                    # 임베딩 대상 텍스트
    metadata: dict               # 아래 필수 필드 포함
      # 필수:
      #   doc_id: str            (source_path + hash)
      #   chunk_idx: int
      #   source_path: str
      #   domain: str            ("rtl" | "snps_ip" | "spec")
      #   chunk_type: str        (도메인별 enum 권장)
      #   ingested_at: datetime
      # 선택 (도메인별):
      #   module_name: str       (RTL/SNPS)
      #   license_tag: str       (SNPS)
      #   ear_eccn: str          (SNPS)
      #   section_heading: str   (Spec)
    context_prefix: str | None   # Contextual Retrieval용
```

CI 단계에서 스키마를 자동 검증합니다. 필수 필드가 누락된 MR은 머지 전 단계에서 알림과 함께 멈춥니다.

### 3.5.6 Contract Issue Report — 문제 공유 채널

Contract 자체의 변경은 §3.5.1의 외부 환경에 영향을 주므로 개별 도메인에서 임의로 바꾸기 어렵습니다. 대신 Contract를 사용하면서 발견되는 문제는 다음 채널로 공유해 주시면 Platform이 검토합니다.

**공유하면 좋은 유형**
- Contract Template/Util의 버그
- 특정 도메인 파일이 Template으로 잘 처리되지 않는 구체 사례 (재현 가능한 형태)
- Chunk 스키마의 필수 필드가 도메인에 잘 맞지 않는 경우

**공유 형식 (GitLab issue template `rag-contract-issue.md`)**
```markdown
## 현상 (무엇이 잘 안 되는가)
- 재현 파일·쿼리·기대 결과·실제 결과

## 영향 범위
- 우리 도메인에서 빈도

## 해결 방안
이 섹션은 비워 두셔도 됩니다.
해결 방안은 Platform이 다른 도메인까지 고려해 설계합니다.
```

**Issue 단계에서 접수되지 않는 유형**

다음 유형은 §3.5.1 외부 환경에 직접 영향을 주거나 보안 승인 범위를 벗어나므로, Issue 채널보다는 **§4.5 신규 도메인/스택 검토 절차**로 안내드립니다.

- "타 RAG 스택 도입 요청" (LangChain / LlamaIndex / Milvus / Qdrant / Ollama / Azure OpenAI / 자체 GPU 등)
- 외부 라이브러리·외부 API 직접 호출이 포함된 MR

**처리 흐름**
1. Platform이 Issue 접수 후 원인 분석
2. Template 개선으로 해결 가능: 다음 sprint에 반영
3. Contract 확장이 적절: Platform이 일반화된 형태로 설계 후 전 도메인에 적용
4. 외부 환경 재검토가 필요: 경영진·보안·재무 검토 일정과 함께 회신
5. 도메인 특성상 현 Contract와 잘 맞지 않는 경우: 해당 도메인의 RAG Farm 합류 시점·범위 재논의

### 3.5.7 Contract 범위 밖 도구 — 사전 협의 대상

다음 카테고리는 보안 승인·credit 구조·LiteLLM 감사 경로의 범위를 벗어나기 때문에, **MR에 포함되기 전에 §4.5 신규 도메인/스택 검토 절차**를 거치는 것이 안전합니다. CI에서도 자동으로 감지되어 안내 메시지가 뜹니다.

| 카테고리 | 예시 | 사유 |
|---------|----------|-----|
| 타 RAG 프레임워크 | LangChain, LlamaIndex, Haystack, Dust | 보안 승인 범위 외, LiteLLM 감사 우회 가능 |
| 타 벡터 DB | FAISS, Milvus, Qdrant, Pinecone, Weaviate, Chroma | OpenSearch 통합 운영 외 |
| 타 LLM API | OpenAI 직접, Anthropic 직접(Bedrock 비경유), Azure OpenAI, Google Vertex | LiteLLM·Bedrock·credit 구조 외 |
| 로컬 LLM | Ollama, llama.cpp, vLLM 자체 호스팅 | HW 비용·보안 인증 별도 필요 |
| 자체 임베딩 | sentence-transformers 로컬, HuggingFace 직접 호출 | Platform 임베딩 일관성 외 |
| 외부 HTTP 호출 | requests/httpx로 임의 외부 API 호출 (LiteLLM 외) | 폐쇄망·감사 경로 외 |
| AWS SDK 직접 | boto3로 Bedrock·OpenSearch·S3 직접 호출 | platform_contract util 경유가 권장 |
| 자체 인프라 | EC2/ECS/EKS 별도 컴포넌트, 로컬 DB | 현재 Platform 운영 범위 외 |

위 도구들이 정말 필요한 경우, 도메인 Lead와 Platform이 함께 검토하여 **Contract 확장이 적절한지 / 별도 도메인으로 분리할지 / 다른 시점에 반영할지**를 정합니다.

### 3.5.8 설계자 온보딩 D3 — Contract 배경 브리핑 (30분)

§4.3 D3에 다음 세션을 배치합니다. 설계자가 Contract를 **시스템의 일관된 운영 규약**으로 자연스럽게 받아들이도록 돕는 것이 목적입니다.

| 분 | 내용 |
|----|-----|
| 0~10 | **3대 배경 환경 안내**: AWS credit 구조와 2027 중반 전환, HW 자체구축 부담, 보안 거버넌스 승인 완료 상태 |
| 10~15 | "흔히 떠올리는 RAG vs 우리 스택" — LangChain 그림 vs Bedrock+OpenSearch+LiteLLM 그림 비교 |
| 15~22 | 당신이 작성할 영역 = `parser.py` 중심 (Template 구조 투어) |
| 22~26 | Chunk 스키마와 메타데이터 |
| 26~30 | Issue Report 절차 + Contract 범위 밖 도구 안내 + Q&A |

**브리핑 핵심 메시지:**
> "현재 RAG Farm은 AWS credit 덕분에 운영 비용 부담이 거의 없습니다. 그래서 '비용 걱정 없이 실험해도 될 것'처럼 느껴질 수 있습니다.
>
> 다만 이 credit은 2027년 중반에 종료되고, 그 이후로는 실비 운영으로 전환됩니다. 그때까지 도메인·데이터·유저가 쌓이면서 시스템을 계속 사용해야 하는 상황이 되기 때문에, 지금부터 비용 효율적인 공통 구조를 잡아두는 것이 안정적입니다.
>
> 지금의 Contract는 'credit 기간의 운영 가이드라인'이자 'credit 종료 이후에도 시스템이 잘 유지되도록 하기 위한 설계'입니다. 지금 다양한 스택이 섞이면 나중에 비용 통제가 어려워질 수 있어, 미리 정리해 두는 편입니다.
>
> 여러분의 본업은 SOC 설계입니다. 그래서 RAG 기여 부담을 최소화할 수 있도록, 작업 범위를 `parse()` 함수에 집중시키고 그 외 인프라는 Platform이 담당하는 형태로 설계했습니다."

### 3.5.9 Technical Safeguards — 자동화된 가이드 레일

CI/Runtime 단계에서 Contract와의 정합성을 자동으로 점검해, 실수로 Contract 범위를 벗어나는 경우 **MR 단계에서 안내 메시지**가 뜨도록 설계했습니다. 사람의 주의력에만 의존하지 않기 위한 일반적인 안전 장치 수준입니다.

**(1) Python import 점검 (CI 정적 분석)**

`parsers/**/*.py` 경로의 import를 자동 검사합니다. 권장 외 라이브러리가 발견되면 MR에 코멘트가 달리고, Platform·peer 리뷰어에게 안내됩니다.

```python
ALLOWED_IN_PARSERS = {
    "re", "json", "pathlib", "dataclasses", "typing", "datetime",
    "platform_contract",       # Platform 제공 util
    "tree_sitter", "tree_sitter_verilog",  # 허용된 파싱 라이브러리
}
NEEDS_REVIEW = {
    "boto3", "botocore",            # AWS 직접 호출 → platform_contract 권장
    "langchain*", "llama_index*",   # 타 RAG 프레임워크
    "faiss", "qdrant_client",       # 타 벡터 DB
    "openai", "anthropic",          # LLM 직접 호출 (LiteLLM 경유 권장)
    "requests", "httpx", "urllib",  # 외부 HTTP (platform_contract 권장)
    "torch", "transformers",        # 로컬 모델 추론
}
```

`NEEDS_REVIEW` 라이브러리는 자동 차단이 아니라, **§3.5.6 Issue Report 또는 §4.5 신규 도메인/스택 검토 절차**로 안내됩니다.

**(2) Lambda Layer**

Platform이 제공하는 Lambda Layer에는 승인된 라이브러리들이 사전에 포함되어 있습니다. `requirements.txt`에 새 라이브러리를 추가하더라도 layer에 없으면 런타임에서 import 단계에서 안내가 뜹니다. 추가가 필요한 라이브러리는 §3.5.6 채널로 요청해 주시면 검토 후 layer에 반영합니다.

**(3) Runtime guard**

`parser_handler` 실행 직전 `platform_contract.runtime_guard()`가 호출되어 다음을 점검합니다:
- 예상 외 라이브러리 로드 여부
- 외부 네트워크 함수가 비정상적으로 교체된 흔적
- 이상 발견 시 빠르게 종료하고 CloudWatch + Slack에 알림

이 3중 점검은 **사람의 주의력을 보조하는 가이드 레일** 성격이며, 발견된 사례는 사후 분석을 통해 Contract 개선 자료로 활용됩니다.

---

## 4. 역할별 업무 방식 (How they work)

각 역할의 **"온보딩 / 일상 / 문제대응"** 3단계 시나리오.

### 4.1 Platform 운영자

#### 온보딩 (내부 인력 충원 시)
1. AWS 콘솔 + Terraform repo 권한 부여 (MFA 필수)
2. LiteLLM 관리 UI 계정 생성
3. GitLab 그룹 Maintainer 권한
4. 기존 Platform 담당자와 shadow 2주

#### 일상 (주간 반복)
| 빈도 | 작업 | 소요 |
|------|-----|------|
| 매일 | Slack 알림 모니터링 (배포·장애) | 15분 |
| 매일 | LiteLLM 비용·쿼터 대시보드 확인 | 10분 |
| 주간 | MR 리뷰 (Platform Reviewer 순번) | 2~3 MR × 15분 |
| 주간 | CloudWatch 알람 정리 | 30분 |
| 월간 | IAM Access Analyzer 리포트 검토 | 1시간 |
| 분기 | 권한 감사·rotation | 4시간 |
| 필요 시 | 도메인 신규 온보딩 지원 | §4.5 참조 |

#### 문제대응
- **배포 실패**: Slack 알림 → GitLab Runner 로그 확인 → CloudWatch → 원인 파악 → 필요시 Lambda alias rollback
- **LiteLLM 장애**: ALB health check → ECS task 재시작 → RDS 상태 → 원인 fix
- **이상 사용량**: 특정 키가 쿼터 초과 → 키 일시 정지 → 유저 확인 → 조치

### 4.2 도메인 Lead

#### 온보딩 (신규 도메인 추진 시)
1. Platform과 도메인 scope 합의 (1 meeting)
2. `parsers/{domain}/` 경로 생성·CODEOWNERS 등록 (Platform 지원)
3. 초기 스모크 테스트 5개 작성
4. 설계자 2~3명 선정, 교육 자료 준비

#### 일상
| 빈도 | 작업 | 소요 |
|------|-----|------|
| 주간 | 자기 도메인 MR 리뷰 (peer 역할) | 2~3 MR × 30분 |
| 주간 | Alpha 유저 피드백 Slack 채널 정리 | 30분 |
| 주간 | 스모크 쿼리 유지·확장 (회귀 감지) | 1시간 |
| 월간 | 설계자 1:1 (작업 만족도, 장벽) | 30분 × 설계자 수 |
| 필요시 | 새 IP 도입 시 scope·parser 설계 참여 | 가변 |

#### 문제대응
- **스모크 회귀 발생**: 원인 MR 파악 → roll-back or hotfix MR → 원인 분석 리포트
- **Alpha 유저 불만**: 피드백 분류 → parser 개선 vs Spec RAG 영역 판별 → 백로그 우선순위 조정

### 4.3 도메인 Developer (설계자) — 가장 중요한 섹션

#### 온보딩 (최초 1회, ~1주)
| Day | 활동 | 주체 |
|-----|-----|-----|
| D1 | 폐쇄망 PC 수령 (사내 IT 배포) | IT |
| D1 | 수출통제·NDA 교육 수강 (사내 규정) | 법무 |
| D2 | GitLab 계정·repo 접근권 (Platform이 발급) | Platform |
| D2 | LiteLLM `dev-snps-*` 키 수령 | Platform |
| D3 | **Contract 배경 브리핑 (30분, §3.5.8)** — Credit·HW·보안 3대 제약 + parser.py 범위 + 금지 패턴 | Platform |
| D3 | 도메인 Lead과 **"내가 기여할 파서 1개"** scope 합의 | Lead |
| D3 | **"Designer Guide for SNPS RAG.md"** 완독 (§7 참조) | 본인 |
| D4 | 로컬 셋업 (clone, uv sync, pytest 통과 확인) | 본인 + Lead 지원 |
| D5 | 튜토리얼 MR 생성 ("Hello World" 파서 수정) → merge → MCP로 쿼리 확인 | 본인 |

#### 일상 (주당 1~2 MR 가정)
| 트리거 | 활동 | 소요 |
|-------|-----|------|
| 새 IP 파일 도착 | `rag-inbox upload` CLI로 S3 업로드 | 5분 |
| 업로드 완료 후 | Slack 알림에서 파싱·인덱싱 성공 확인 | 2분 |
| 파싱 결과가 기대에 못 미침 | MCP로 샘플 쿼리 → gap 식별 | 30분 |
| gap 해결 | 로컬에서 `parsers/snps_ip/` 수정, `pytest tests/smoke/snps_ip/` 실행 | 1~3시간 |
| 통과 | feature branch push, MR 생성 | 5분 |
| LLM Bot 리뷰 댓글 → 수정 | 의견 반영 or 반박 댓글 | 15분 |
| Platform + peer 승인 후 merge | 자동 배포 + 스모크 자동 재실행 | (대기 10분) |
| 배포 성공 후 | MCP로 실제 쿼리 결과 확인 | 10분 |

**핵심 UX:** 설계자는 **AWS 콘솔을 한 번도 보지 않고** 전 과정 수행.

#### 문제대응
| 문제 | 첫 조치 | 에스컬레이션 |
|-----|--------|----------|
| 로컬 pytest 실패 | `local-dev-kit/README.md` 트러블슈팅 확인 | → peer → Lead |
| MR CI 실패 | GitLab CI 로그 확인 (린트·secret 스캔·빌드) | → peer → Platform (secret 스캔 블록 시) |
| 배포 후 MCP 쿼리 이상 | 스모크 테스트로 재현 → 새 MR로 hotfix | → Lead (회귀 분석) |
| AWS 로그를 보고 싶음 | **볼 수 없음.** Lead에게 특정 로그 요청 | Lead가 CloudWatch 확인 후 요약 공유 |
| `rag-inbox upload` 실패 | CLI 에러 메시지 → README 확인 | → Platform |

### 4.4 Reviewer (3명 조합)

#### Platform Reviewer 루틴 (MR당 15분)
1. CI 결과 확인 (린트·테스트·secret 스캔 모두 pass?)
2. diff에서 인프라 관련 경로 touch 여부 (CODEOWNERS가 잡아주지만 재확인)
3. Lambda 핸들러 변경 시 IAM Role 권한 초과 없는지
4. LLM 호출 코드가 LiteLLM 경유인지 (direct Bedrock call 없는지)
5. 승인 또는 변경 요청

#### Peer Reviewer 루틴 (MR당 30분)
1. 파서 로직이 도메인 IP 구조를 올바르게 해석하는가
2. 기존 스모크 테스트 영향 범위 추정
3. 코드 품질·가독성
4. 필요 시 로컬에서 직접 pytest 돌려보기

#### LLM Bot 루틴 (자동)
1. MR open → Webhook → Lambda
2. Diff + 기존 파서 코드 일부를 Claude에 프롬프트
3. 코멘트 자동 생성 (최대 10개 포인트)
4. Approve 권한 없음

### 4.5 도메인 신규 온보딩 (SNPS 예시)

Platform + 신규 도메인 Lead 공동 추진, **~4주 공수**.

| Week | 작업 | 주체 |
|------|-----|-----|
| W1 | 법적 선결 조건 점검 (v1.0 §10) | 법무 + Lead |
| W1 | 설계자 peer 풀 확정 (최소 3명) | Lead |
| W2 | S3 prefix·KMS 키·OpenSearch collection 생성 | Platform |
| W2 | IAM Role·Permissions Boundary 정의 | Platform |
| W2 | LiteLLM 키 정책 확장 (`dev-snps-*`, `prod-snps-*`) | Platform |
| W3 | GitLab repo 경로·CODEOWNERS 추가 | Platform + Lead |
| W3 | 초기 parser/indexer Lambda 뼈대 작성 | Platform + Lead |
| W3 | 스모크 테스트 5~10개 설정 | Lead |
| W4 | 설계자 1명 pilot 온보딩 (§4.3) | 공동 |
| W4 | 1 MR cycle 통과 검증 후 전체 공개 | 공동 |

---

## 5. E2E 워크플로우 — "RTL 들어와서 RAG로 질문 받기까지"

이 섹션이 v1.1의 **실행 청사진**입니다. 실제 예시로 흐름 추적.

**시나리오:**
- **김데이터** = SNPS 도메인 Data Steward (IP integration manager 역할)
- **홍길동** = SNPS 도메인 Developer (파서 개발자, 본업 SOC 설계)
- 두 사람은 다른 사람일 수도, 같은 사람이 두 롤 겸임할 수도 있음. **권한과 책임은 분리**.

`designware_axi_v2.1.sv` 신규 버전을 받아 RAG에 반영하는 흐름:

### 5.1 Stage 1 — IP 파일 업로드 (~5분, **Data Steward 작업**)

```
[D-day 09:00] 김데이터(Steward): SNPS 포털에서 IP 수령
          09:02 라이선스·EAR 등급 확인
                - 라이선스: SNPS-NDA-2024 (사내 인덱싱 허용)
                - ECCN: 3D991 (이중용도, 국내 인덱싱 허용)
                - 검토 OK
          09:05 파일 로컬 저장 (/work/snps_ip/designware_axi_v2.1.sv)
          09:06 $ rag-inbox upload \
                    --domain snps_ip \
                    --file designware_axi_v2.1.sv \
                    --tag "v2.1, 2026-05-12, from-vendor" \
                    --license-tag "SNPS-NDA-2024" \
                    --ear-eccn "3D991"
          09:06 CLI: OIDC 토큰 발급 중...
                      Steward 권한 확인 중 (snps-data-stewards)... OK
                      라이선스·EAR 메타 검증... OK
                      S3 presigned URL 수령
                      업로드 중... (2MB, 3초)
                      완료. Job ID: inbox-snps-20260512-090607
          09:07 Slack #snps-rag 채널에 자동 알림:
                "[Inbox] designware_axi_v2.1.sv received from 김데이터
                 → license=SNPS-NDA-2024, ECCN=3D991 → parser triggered"
```

**이면에서 벌어지는 일:**
- Inbox API가 김데이터의 IAM group(`snps-data-stewards`) 멤버십 확인
- 비-Steward(예: 홍길동)가 같은 명령을 실행하면 **권한 거부**
- S3 put은 `snps_ip/raw/designware_axi_v2.1.sv`로만 허용 (IAM condition)
- KMS `kms-snps-ip` 키로 서버 사이드 암호화
- 객체 메타에 `uploaded_by=김데이터`, `license=SNPS-NDA-2024`, `eccn=3D991` 부착
- Inbox DB에 업로드 이력 기록 (감사 추적)

**홍길동(Developer)의 위치:** 이 단계에 관여하지 않음. Slack 알림으로 "새 IP가 들어와 인덱싱 중"임을 인지만 함. 업로드 작업은 본인 본업(SOC 설계)을 방해하지 않음.

### 5.2 Stage 2 — 자동 파싱 (~2~10분, 파일 크기 따라)

```
[09:07] S3 ObjectCreated 이벤트 → rag-pipeline-snps-parser-* 트리거
        ├─ 파일 다운로드 (Lambda tmp)
        ├─ parser 모듈 로드 (parsers/snps_ip/*.py)
        ├─ SystemVerilog AST 파싱
        ├─ 모듈·포트·파라미터·always 블록 추출
        ├─ chunk 생성 (module 단위, 메타데이터 포함)
        └─ S3 put → snps_ip/parsed/designware_axi_v2.1.jsonl
[09:10] Parser 완료 이벤트 → rag-pipeline-snps-indexer 트리거
```

**파싱 실패 시:**
- CloudWatch에 에러 로그
- Slack 알림 (Lead 멘션)
- Inbox 상태 DB: `FAILED`
- 홍길동은 Lead에게 문의 → Lead가 로그 확인 후 원인 공유

### 5.3 Stage 3 — 임베딩·인덱싱 (~5~20분)

```
[09:10] Indexer Lambda 실행
        ├─ parsed jsonl 로드
        ├─ chunk별 contextual prefix 생성 (LiteLLM 경유 Haiku)
        ├─ 임베딩 생성 (Cohere Embed v4 via LiteLLM)
        ├─ OpenSearch snps-ip-collection에 upsert
        │   (doc_id = hash(file + chunk_idx))
        └─ 기존 버전(v2.0) 문서 soft-delete (retention 30일)
[09:25] Indexer 완료 → Slack 알림
        "[Index] designware_axi_v2.1: 184 chunks indexed"
```

### 5.4 Stage 4 — 검증 (~10분)

```
[09:25] 홍길동: Claude Desktop 열고 MCP SNPS 서버 연결
          $ "designware_axi_v2.1 의 AXI write response 채널에 대해 설명해줘"
          (Claude가 MCP tool 경유로 snps-ip-collection 쿼리)
          답변 검토: 모듈 이름, 핵심 신호, 지연 정책 등 맞는가?
        홍길동: "v2.0과 비교해서 BRESP 생성 타이밍 바뀐 부분이 반영됐는지 확인"
          → 답변에 v2.1의 새 타이밍 로직 언급됨. OK.
```

### 5.5 Stage 5 — parser 개선 (필요시, ~1~4시간)

v2.1 업로드 결과 파싱이 특정 struct를 놓친 것을 발견했다고 가정.

```
[10:00] 홍길동: 로컬에서 parsers/snps_ip/port_parser.py 수정
          ├─ 새 struct 패턴 추가
          ├─ pytest tests/unit/snps_ip/ 실행 → 통과
          ├─ pytest tests/smoke/snps_ip/ 실행 → 기존 4/5 통과, 1개 expected change
          └─ 스모크 기대값 업데이트 (Lead에 peer 리뷰 부탁 예정)
[10:30] git push origin feature/snps-port-parser-struct
        GitLab UI에서 MR 생성
        Description: "v2.1 검증 중 발견한 axi_port_t struct 파싱 누락 수정"
[10:31] CI 자동 실행 (5분)
[10:35] LLM Bot 리뷰 댓글 자동 등록 (회귀 리스크 낮음 판정)
[10:40] Peer (동료 설계자) 리뷰 → approve
[11:00] Platform Reviewer 리뷰 → approve
[11:05] MR merge → Runner 자동 CD
        ├─ Lambda 패키지 재빌드
        ├─ snps-parser Lambda 업데이트
        ├─ 기존 v2.1 파일에 대해 reparse trigger (옵션: manual or auto)
        └─ 스모크 자동 재실행 → 통과
[11:20] Slack 알림: "Deploy success, smoke 10/10"
[11:25] 홍길동: MCP로 재검증 → struct 이제 반영됨
```

### 5.6 Stage별 책임 요약

| Stage | 주 담당 | Platform 개입 | 자동화 |
|-------|-------|----------|------|
| 1. 업로드 | **Data Steward** (라이선스·EAR 검토 포함) | 없음 | CLI + S3 presigned |
| 2. 파싱 | 시스템 | 실패 시 | S3 이벤트 기반 |
| 3. 인덱싱 | 시스템 | 실패 시 | Lambda chain |
| 4. 검증 | Developer / Lead / End User | 없음 | MCP 수동 |
| 5. parser 개선 | Developer + Reviewer | MR 승인 + 장애 시 | CI/CD 자동 |

**Steward와 Developer 분리의 효과:**
- 업로드 시점에 **라이선스·EAR 검토가 누락 없이** 수행됨 (Steward의 책임)
- Developer는 본업 방해 없이 파서 작업에만 집중 (업로드 자격 판단 부담 없음)
- 감사 발생 시 "어떤 IP가 누구의 판단으로 인덱싱됐는가"가 단일 책임자로 추적됨

---

## 6. 시스템 사용 규칙 (정리)

### 6.1 "해야 할 일" (Do)

| 역할 | Do |
|------|---|
| **Data Steward** | IP 업로드 전 **라이선스·EAR 등급·NDA 조건 검토** 후 `rag-inbox` 사용 |
| **Data Steward** | 업로드 시 `--license-tag`, `--ear-eccn` 메타 필수 부착 |
| **Data Steward** | IP 폐기·계약 종료 시 인덱스에서 즉시 철회 (`rag-inbox remove`) |
| **Data Steward** | 분기별 도메인 인덱싱 자산 점검 리포트를 Lead·Platform에 공유 |
| Developer | 로컬 스모크 통과 후에만 MR 생성 |
| Developer | MR description에 **"어느 IP·어느 버전에 대한 대응인가"** 명시 |
| Developer | 배포 후 MCP로 최소 3개 질문 검증 후 Slack에 "verified" 코멘트 |
| Lead | 주간 스모크 커버리지 리포트 Slack 공유 |
| Lead | Steward와 Developer 롤이 **명시적으로 분리되어 부여**됐는지 분기 점검 |
| Platform | 배포 실패 30분 내 Slack 원인 요약 |
| Platform | Steward 그룹 멤버십 변경 시 감사 로그 보존 |
| 모두 | Secret·credential은 반드시 환경변수 (코드 하드코딩 금지) |

### 6.2 "하지 말아야 할 일" (Don't)

| 역할 | Don't |
|------|-------|
| **Developer** | **`rag-inbox upload` 시도 (Steward 권한 없으면 자동 거부됨)** |
| **Developer** | "내가 설계자니까 내 IP는 내가 올린다" 자동 권한 가정 |
| Developer | AWS CLI/SDK 로컬 설치 시도 (네트워크 차단됨, 시도 자체 policy 위반) |
| Developer | Jenkins·AWS 콘솔 접근 시도 (권한 없음) |
| Developer | RTL/IP 파일을 `rag-inbox` 외 경로로 업로드 (GitLab LFS, 공유 폴더 등) |
| Developer | 타 도메인 `parsers/*` 수정 시도 (CODEOWNERS 거부) |
| Developer | LLM 리뷰 봇을 approve 권한 있는 것처럼 취급 |
| **Steward** | 라이선스·EAR 검토 없이 IP 업로드 (메타 검증에 의해 자동 거부) |
| **Steward** | 타 도메인 prefix에 업로드 시도 (IAM 거부) |
| Lead | 자기 단독으로 3 approval 충족 (Platform도 반드시 승인) |
| Lead | Steward와 Developer 권한을 묶어서 일괄 발급 (분리 발급 원칙) |
| Platform | IAM 정책을 ticket 없이 수정 (모든 변경은 MR → CODEOWNERS) |
| 모두 | ChatGPT 개인 계정·Copilot·Cursor 등에 SNPS 코드 붙여넣기 (라이선스·EAR 위반 리스크) |
| **모든 사용자 (End User 포함)** | **일반망(인터넷 PC)에서 Claude Desktop/MCP로 RAG 호출 시도** — 응답에 RTL/IP가 포함되므로 일반망 노출 시 폐쇄망 격리가 무력화됨. AI Tool은 폐쇄망에서만 사용 |

---

## 7. 후속 문서 로드맵

이 v1.1 거버넌스 문서가 확정되면, 다음 **3개 가이드 문서**를 순서대로 작성합니다.

### 7.1 순서와 대상

```
[1] v1.1 거버넌스 (본 문서, 완료)
      ↓
[2] System Build Plan (Platform팀 내부용)
      ↓ 시스템 구축 완료 후
[3] Developer & Operator Guide (Platform·Lead·설계자 대상)
      ↓ 1차 온보딩 준비
[4] SNPS IP Parsing Guide (설계자 대상)
      → 실제 온보딩 시작
```

### 7.2 문서별 scope

#### [2] System Build Plan (`RAG_System_Build_Plan_v1.0.md`)

- **대상:** Platform팀 내부
- **목적:** §3 컴포넌트 맵 기반 6~8주 구축 실행 계획
- **담을 내용:**
  - 각 컴포넌트 상세 설계 (Terraform 모듈·IAM 정책 예시·Runner 구성 옵션)
  - RTL/IP Inbox CLI 설계 (§3.4 선택안 결정)
  - MCP 서버 아키텍처 상세
  - LLM Review Bot 구현 (Lambda + 프롬프트)
  - 모니터링·알림 구성
  - Week-by-week 구축 체크리스트

#### [3] Developer & Operator Guide (`RAG_Operator_Developer_Guide_v1.0.md`)

- **대상:** Platform 운영자 + 도메인 Lead + 일반 개발자
- **목적:** 시스템 구축 완료 후 **"어떻게 운영하고 일상 업무를 수행하는가"**
- **담을 내용:**
  - Platform 운영 루틴 (§4.1 확장)
  - 장애 대응 runbook (배포 실패, LiteLLM 장애, 인덱싱 멈춤 등)
  - 도메인 신규 온보딩 playbook
  - MR 리뷰 가이드라인 (Platform/peer/LLM Bot별)
  - 모니터링 대시보드 사용법
  - 권한 감사 실행법
  - IAM Role·LiteLLM 키 발급·회수 절차

#### [4] SNPS IP Parsing Guide (`SNPS_IP_Parsing_Guide_v1.0.md`) — 설계자 전용

- **대상:** 설계자 본인 (첫 온보딩부터 능숙하게 쓰기까지)
- **목적:** §4.3 설계자 일상을 **손에 잡히는 튜토리얼**로
- **담을 내용:**
  - 폐쇄망 PC 초기 셋업 (Step-by-step)
  - Git/GitLab 기초 (익숙하지 않은 설계자를 위해)
  - 로컬 개발 환경 구동 (`local-dev-kit` 사용법)
  - **"Hello World" parser MR** 튜토리얼 (온보딩 D5)
  - `rag-inbox` CLI 전체 명령어
  - 로컬 pytest·스모크 실행법
  - MR 작성법 + 리뷰 응대 tips
  - MCP로 결과 검증하는 법 (Claude Desktop 프롬프트 팁)
  - SystemVerilog/Verilog 파싱 패턴 예시 (자주 나오는 모듈 구조 → 파서 패턴)
  - **자주 만나는 실패 케이스 & 해결** (FAQ)
  - 언제 Lead에 에스컬레이트하나

### 7.3 작성 우선순위 근거

- [2] System Build Plan **선행**: 뭐가 있는지 정해져야 [3][4] 쓸 수 있음
- [3] Operator/Developer Guide **중행**: 시스템이 돌아가기 시작해야 운영 가이드가 의미 있음
- [4] SNPS IP Parsing Guide **후행**: 설계자 온보딩 시점에 딱 맞게 (너무 일찍 쓰면 현실과 괴리)

**총 문서 로드맵 기간:** 본 v1.1 승인 → [2] 2주 → 구축 6~8주 → [3] 병행 → 구축 완료 시 [4] 2주 → SNPS 설계자 온보딩 개시.

---

## 8. 오픈 이슈 (v1.0에서 이월 + v1.1 신규)

### 이월
- [ ] 법적 선결 조건 (v1.0 §10) — 법무·수출통제 담당 확정
- [ ] 사내 PyPI/Docker 미러 현황 확인
- [ ] MCP 서버 호스팅 위치 확정
- [ ] 설계자 peer 풀 확보 (3명 이상)
- [ ] 폐쇄망 PC 조달 책임 부서

### 신규 (v1.1)
- [ ] **RTL/IP Inbox 구현 옵션 확정** (§3.4 A/B/C/D 중)
- [ ] **도메인 peer 부재 시 비상 2-approval 운영 정책** 상세 (언제·얼마나)
- [ ] **Inbox 업로드 파일 크기·형식·검증 규칙** (예: SystemVerilog 구문 사전 검사?)
- [ ] **reparse 정책**: parser 업데이트 시 기존 IP 전체 재파싱 vs incremental
- [ ] **OpenSearch collection 분리 vs 공유**: SNPS IP 별도 collection 비용 평가
- [ ] **KMS 키별 접근 로그 보관 기간** 컴플라이언스 요구 확인
- [ ] **LLM Bot이 만들어낸 코멘트 품질 관리** (잘못된 판정 feedback loop)
- [ ] **MCP 인증 방식**: Claude Desktop에 OAuth? 장기 key? 도메인별 분리?
- [ ] **Alpha/Beta End User 가이드** 작성 시점 (§7 범위 밖이나 필요)

---

## 9. 보고용 요약

> **"v1.1 거버넌스는 v1.0의 통제 원칙 위에 '누가 무엇을 어떻게 하는가'를 구체화했습니다. 5개 역할(Platform 운영자·도메인 Lead·설계자 개발자·Reviewer·End User)의 온보딩·일상·문제대응을 정의하고, 폐쇄망부터 AWS까지 13개 시스템 컴포넌트의 역할과 구축 우선순위를 확정했습니다. 핵심은 설계자가 AWS 인프라를 한 번도 보지 않고 'rag-inbox CLI로 IP 업로드 → MR 경유 파서 개선 → MCP로 결과 검증' 세 단계로 전 워크플로우를 수행할 수 있다는 것입니다. RTL/IP 파일은 전용 Inbox CLI로만 S3에 진입하며, 도메인 경계는 CODEOWNERS·IAM·KMS·OpenSearch collection 레벨에서 중첩 분리됩니다. 이 v1.1이 확정되면 시스템 구축 계획서·운영/개발 가이드·SNPS IP 파싱 가이드 3종을 순차 작성하여 SNPS 설계자 온보딩까지 연결합니다."**

### 핵심 4가지

1. **5개 역할 정의** — Platform·Lead·Developer·Reviewer·EndUser의 책임/권한/KPI/일상비율
2. **13개 시스템 컴포넌트 + 구축 우선순위** — 폐쇄망·AWS·연결 레이어
3. **E2E 워크플로우** — IP 업로드부터 검증까지 5 Stage 실행 청사진
4. **3개 후속 문서 로드맵** — Build Plan → Operator/Developer Guide → SNPS IP Parsing Guide

---

*End of Document — v1.1*
