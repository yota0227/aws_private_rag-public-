# Amazon Quick Suite 도입 계획서

> BOS Semi · ChatGPT Business → Amazon Quick Suite 전환 및 Private RAG 통합 운영 계획
> 작성일: 2026-03-23

---

## 1. 왜 지금, 왜 Quick Suite인가

월요일 아침. SoC팀 엔지니어가 인터럽트 컨트롤러 스펙을 찾고 있다.

Confluence를 뒤지고, SharePoint 폴더를 열고, 결국 옆자리 선배한테 물어본다. "그거 작년에 바뀌었는데, 어디 있더라..." 선배도 기억이 가물가물하다. 30분이 지나서야 PDF 하나를 찾아낸다. 이런 일이 하루에도 몇 번씩 반복된다.

우리는 이 문제를 풀려고 Private RAG를 만들었다. 그리고 잘 동작한다. 하지만 솔직히 말하면, 지금 우리 도구 환경은 좀 파편화되어 있다:

- **ChatGPT Business** — AI 채팅 (GPTs 공유)
- **Private RAG** — 기밀 문서 검색 (Air-Gapped)
- **Jira / Confluence / SharePoint** — 각각 따로 열어서 확인
- **BI 대시보드** — 없음
- **워크플로우 자동화** — 없음

엔지니어 입장에서는 "하나의 창에서 다 되면 좋겠다"는 게 솔직한 바람이다.

Quick Suite는 그 "하나의 창"이 될 수 있다. AI 채팅, BI, 자동화, 데이터 통합이 한 워크스페이스에 들어있고, 우리가 이미 구축한 Private RAG와 MCP로 연결된다. ChatGPT Business보다 싸거나 비슷한 가격에, 할 수 있는 게 훨씬 많다.

그리고 하나 더 — AWS와의 전략적 관계. 반도체 설계 회사가 Air-Gapped RAG + Quick Suite를 통합 운영하는 레퍼런스 케이스는 AWS 입장에서도 가치가 있다. 이건 협상 카드가 된다.

---

## 2. 3사 비교: 숫자로 보는 차이

"왜 Claude Enterprise가 아니라 Quick Suite야?"라는 질문이 나올 것이다. 답은 간단하다 — Quick Suite는 AI 채팅 *그 이상*이다.

| 기능 | ChatGPT Business | Quick Suite | Claude Enterprise |
|------|-----------------|-------------|-------------------|
| AI 채팅 | O (GPTs) | O (Chat Agent, Custom Agent) | O (Projects) |
| BI 대시보드 | X | O (Quick Sight) | X |
| 워크플로우 자동화 | X | O (Flows + Automate) | X |
| 딥 리서치 | O (Deep Research) | O (Quick Research) | O (Research) |
| 데이터 통합 인덱싱 | X | O (Quick Index, 50+ 소스) | X |
| Jira 연동 | GPTs 커스텀 | 네이티브 Action | MCP 커스텀 |
| Confluence 연동 | GPTs 커스텀 | 네이티브 Action + KB | MCP 커스텀 |
| SharePoint 연동 | GPTs 커스텀 | 네이티브 (19개 액션) | MCP 커스텀 |
| MCP 프로토콜 | X | O (내장 클라이언트) | O (내장) |
| Private RAG 연동 | 불가 | O (MCP + VPC 내부) | 제한적 |
| VPC Endpoint | X | O (PrivateLink) | X |
| 브라우저/오피스 확장 | X | O (Chrome, Edge, Teams 등) | X |
| AWS 빌링 통합 | X | O | X |
| 월 비용 (300명) | ~$7,500 | $6,200~$7,000 | ~$9,000+ |

한 줄 요약: ChatGPT Business는 "채팅만", Claude Enterprise는 "비싼 채팅", Quick Suite는 "채팅 + 그 외 전부".

### "Claude Enterprise가 낫지 않나?"에 대한 답변

이 질문은 반드시 나온다. 미리 준비해두자.

| 반론 | 우리의 답 |
|------|----------|
| "Claude Enterprise가 더 간단하잖아" | 간단한 건 맞다. 대신 BI 없고, 자동화 없고, 연동도 제한적이다. 결국 별도 도구를 또 붙여야 한다. |
| "Claude 모델이 더 좋다던데" | Quick Suite도 Bedrock 기반 Claude를 쓴다. 모델 품질은 동일하다. |
| "비용이 비슷하다면서" | Claude Enterprise $30/user × 300명 = $9,000/month. Quick Suite는 $6,600에 BI+자동화까지 포함이다. |
| "VPC 연동 된다며" | Claude Enterprise는 VPC Endpoint를 지원하지 않는다. 우리 Private RAG에 직접 연결이 안 된다. |
| "MCP 지원한다잖아" | 맞다. 하지만 Quick Suite는 MCP + OpenAPI + 50개 이상 네이티브 커넥터다. 생태계 규모가 다르다. |


---

## 3. Quick Suite, 뭐가 들어있나

다섯 가지 기능이 하나의 워크스페이스 안에서 돌아간다. 따로 설치할 것도, 따로 로그인할 것도 없다.

| 기능 | 한 줄 설명 | 우리가 쓸 곳 |
|------|-----------|-------------|
| **Quick Sight** | BI 대시보드, 데이터 시각화 | RAG 운영 메트릭, 프로젝트 현황, 스프린트 번다운 |
| **Quick Research** | AI 리서치 에이전트 (내부+외부) | 기술 조사, 경쟁사 분석, 보고서 자동 생성 |
| **Quick Flows** | 간단한 워크플로우 자동화 | 일상 반복 업무 — 보고서, 알림, 데이터 정리 |
| **Quick Automate** | 복잡한 멀티스텝 에이전트 자동화 | Jira→Confluence→RAG 연계 프로세스 |
| **Quick Index** | 50+ 데이터 소스 통합 인덱싱 | Confluence, SharePoint, S3 — 한 곳에서 검색 |

**리전**: 버지니아 (us-east-1). 우리 Private RAG Backend도 버지니아다. 같은 리전이라 VPC 연동이 깔끔하다.

**Private 접근**: Quick Sight는 VPC Endpoint (PrivateLink) 지원. 정적 자산(JS, CSS)은 CloudFront 경유하는데, Forward Proxy(Squid)로 화이트리스트 도메인만 허용하면 된다. IGW를 여는 게 아니라, 통제된 아웃바운드다.

---

## 4. Jira / Confluence / SharePoint 연동

Atlassian Cloud 환경이라 네이티브 연동이 바로 된다. Data Center였으면 골치 아팠을 텐데, 다행이다.

| 서비스 | 연동 타입 | 할 수 있는 것 | 인증 |
|--------|----------|-------------|------|
| Jira Cloud | Action Connector | 이슈 생성/수정/조회/검색 | OAuth 2.0 (3LO) |
| Confluence Cloud | Action + Knowledge Base | 페이지 CRUD + 스페이스 인덱싱 | OAuth 2.0 (3LO) |
| SharePoint | Action + Knowledge Base | 리스트/아이템/Excel (19개 액션) | OAuth 2.0 |

### 보안은 어떻게 되나

걱정되는 부분일 텐데, 정리하면 이렇다:

- **OAuth 3LO**: 사용자별 Atlassian 권한이 그대로 적용된다. Quick Suite가 별도 슈퍼 권한을 갖는 게 아니다.
- **Action Review**: Admin이 특정 액션을 "승인 필수"로 설정할 수 있다. 실수로 이슈 100개 생성하는 사고를 막을 수 있다.
- **감사 로그**: 모든 액션 호출이 CloudTrail에 기록된다.
- **통신 경로**: Quick Suite(AWS SaaS) ↔ Atlassian Cloud(SaaS) — SaaS 간 직접 통신이라 우리 VPC를 경유하지 않는다.


---

## 5. Private RAG 연동: MCP Bridge로 간다

두 가지 옵션을 검토했다. 결론부터 말하면, 옵션 A다.

### 옵션 A: MCP Bridge (채택)

```
Quick Suite (SaaS, us-east-1)
    │
    │  MCP 프로토콜 (HTTPS, PrivateLink)
    ▼
MCP Bridge (Fargate, Backend VPC 10.20.0.0/16)
    │
    │  HTTPS (VPC 내부)
    ▼
RAG API (API Gateway → Lambda → Bedrock KB + OpenSearch)
```

이미 Obot용으로 만들어둔 `server.js`를 그대로 쓴다. Fargate에 올리고 NLB + PrivateLink만 붙이면 끝.

### 옵션 B: OpenAPI + Lambda (검토 후 탈락)

```
Quick Suite (SaaS, us-east-1)
    │
    │  OpenAPI 3.0 (HTTPS, IAM Auth)
    ▼
API Gateway (신규, Public + IAM) → Lambda (신규) → RAG API
```

새로 다 만들어야 한다. 그리고 Public API Gateway가 필요하다 — Air-Gapped 원칙에 어긋난다.

### 왜 옵션 A인가

| 항목 | 옵션 A (MCP Bridge) | 옵션 B (OpenAPI + Lambda) |
|------|-------------------|-------------------------|
| 코드 재사용 | server.js 그대로 | 새로 작성 |
| 도구 추가 시 | Bridge 1곳만 수정 | Lambda + OpenAPI + Quick Suite 3곳 |
| Air-Gapped 유지 | PrivateLink로 완벽 | Public API GW 필요 — 원칙 위반 |
| Obot 기존 경로 | 공존 가능 | 이원화 |
| 월 비용 | ~$40 (Fargate) | ~$7 (서버리스) |
| 확장성 | MCP 생태계 확장 용이 | API별 개별 구현 |

비용은 옵션 B가 싸다. 하지만 $33 차이로 Air-Gapped를 포기할 이유는 없다.

---

## 6. 누가 만들고, 누가 쓰나 — Quick Automate 역할 분리

Quick Automate의 좋은 점은 "만드는 사람"과 "쓰는 사람"을 깔끔하게 나눌 수 있다는 것이다. 300명 전원이 Enterprise일 필요가 없다.

| 역할 | 할 수 있는 것 | 필요 티어 |
|------|-------------|----------|
| **Owner** | 자동화 접근 제어, 커넥터/자격증명 관리 | Enterprise |
| **Contributor** | 자동화 빌드/테스트/배포 | Enterprise |
| **Viewer** | 아이디어 제출, 자동화 실행, 승인 참여 | Professional |

### BOS Semi 라이선스 모델

| 그룹 | 인원 | 티어 | 역할 | 월 비용 |
|------|------|------|------|---------|
| IT/DevOps (메인테이너) | ~10명 | Enterprise ($40) | Owner + Contributor | $400 |
| 팀 리더/파워유저 | ~20명 | Enterprise ($40) | Contributor | $800 |
| 일반 엔지니어 | ~270명 | Professional ($20) | Viewer | $5,400 |
| **합계** | **~300명** | | | **$6,600/month** |

운영 방식은 이렇다: 엔지니어가 "이런 자동화 있으면 좋겠다"고 아이디어를 제출하면, IT/DevOps가 검토하고 구현한다. 중요한 단계에는 Human-in-the-loop 승인을 넣는다. 270명이 각자 자동화를 만들어대는 카오스는 없다.

---

## 7. Quick Index vs Private RAG — 둘 다 쓴다

"Quick Index가 있는데 왜 Private RAG를 유지해?"라는 질문과, "Private RAG가 있는데 왜 Quick Index를 써?"라는 질문이 동시에 나올 수 있다. 답은 간단하다 — 데이터의 성격이 다르다.

| 항목 | Quick Index | Private RAG (Bedrock KB) |
|------|------------|------------------------|
| 본질 | SaaS 통합 인덱싱 | 커스텀 벡터 검색 + LLM 생성 |
| 관리 | AWS 완전 관리형 | 우리가 직접 구성/관리 |
| 데이터 저장 | AWS 관리형 인덱스 | OpenSearch Serverless (우리 VPC) |
| 데이터 소스 | 50+ 커넥터 (자동 동기화) | S3 (파일 업로드) |
| 권한 모델 | 원본 시스템 ACL 상속 | IAM + Security Group |
| 네트워크 | SaaS (PrivateLink 가능) | VPC 내부 (Air-Gapped) |
| 비용 | 구독에 포함 | 인프라 비용 (가변) |

Quick Index는 편하다. Confluence 연결하면 알아서 인덱싱하고, 권한도 원본 그대로 따라간다. 하지만 RTL 코드나 Spec 문서를 SaaS 인덱스에 넣을 수는 없다. 그건 우리 VPC 안에 있어야 한다.

### Private RAG, 돈이 얼마나 드나

솔직한 비용 이야기. OpenSearch Serverless OCU가 가장 큰 비용 드라이버다.

**고정 비용 (데이터 양과 무관하게 매달 나가는 돈):**

| 리소스 | 월 비용 |
|--------|---------|
| OpenSearch Serverless (최소 2 OCU) | ~$350 |
| VPC Endpoints (5~8개) | ~$50~80 |
| API Gateway + Lambda + KMS + Route53 | ~$15 |
| **고정 소계** | **~$420~450** |

**데이터가 늘면 어떻게 되나:**

| 시나리오 | 문서 규모 | OpenSearch OCU | 월 총 비용 |
|---------|----------|---------------|-----------|
| 지금 (PoC) | ~1GB | 2 OCU (최소) | ~$450 |
| 중기 (Spec 추가) | ~10GB | 2~4 OCU | ~$450~800 |
| 목표 (Spec + RTL) | ~50~100GB | 4~8 OCU | ~$800~1,800 |
| 대규모 | ~500GB+ | 8~16 OCU | ~$1,800~3,500+ |

계단식으로 올라간다. 데이터가 10배 늘어도 비용이 10배 되진 않지만, 무시할 수준도 아니다. 이게 중장기에 S3 Vectors 전환을 검토하는 이유다.


---

## 8. 데이터 분류: 어디에 뭘 넣을 것인가

이 부분이 핵심이다. 모든 데이터를 한 곳에 넣는 건 편하지만, 반도체 설계 회사에서 그건 불가능하다.

| 분류 | 뭐가 해당되나 | 어디에 저장 | 누가 접근 |
|------|-------------|-----------|----------|
| **Level 1 (극비)** | RTL Code, Spec 문서, 설계 아키텍처 | Private RAG (Air-Gapped) | VPN + 인증 단말기 + 권한자만 |
| **Level 2 (내부)** | 주간 보고서, 테스트 결과, 기술 노트 | Private RAG | VPN + 권한자 |
| **Level 3 (일반)** | Confluence 위키, SharePoint, Jira | Quick Index (SaaS) | SSO + 원본 권한 |

Level 1~2는 회사 밖으로 나가면 안 되는 데이터다. VPC 안에서만 존재하고, VPN으로만 접근하고, 인증된 기기에서만 열 수 있다. Level 3는 이미 SaaS(Atlassian Cloud, SharePoint)에 있는 데이터니까 Quick Index로 인덱싱해도 보안 수준이 달라지지 않는다.

### 접근 통제 비교

| 조건 | Quick Index (범용) | Private RAG (민감) |
|------|-------------------|-------------------|
| 인증 | IAM Identity Center SSO | SSO + VPN 필수 |
| 단말기 | 제한 없음 (브라우저) | 인증된 기기만 |
| 네트워크 | 인터넷 (PrivateLink 가능) | VPN + VPC 내부만 |
| 암호화 | AWS 관리형 | KMS 고객 관리 키 (CMK) |
| 감사 | CloudTrail | CloudTrail + VPC Flow Logs |
| 데이터 위치 | AWS SaaS 영역 | 우리 VPC (10.20.0.0/16) |

---

## 9. 로드맵: 한 번에 다 바꾸지 않는다

### 단기 (PoC ~ 6개월): 현행 유지하면서 Quick Suite 얹기

지금 돌아가는 것은 건드리지 않는다. Private RAG는 그대로 두고, Quick Suite를 추가한다. ChatGPT Business는 검증이 끝나면 해지한다.

```
┌──────────────────────────────────────────────────────────┐
│                Quick Suite (SaaS, us-east-1)              │
│                                                          │
│  Chat Agent / Research / Automate / Sight                │
│       │                    │                             │
│  Quick Index (범용)    MCP Action (민감)                  │
│  ← Confluence Cloud    → Private RAG                     │
│  ← SharePoint            (MCP Bridge 경유)               │
│  ← Jira Cloud                                           │
└──────────┬───────────────────┬───────────────────────────┘
           │                   │ MCP (PrivateLink)
           │                   ▼
           │    ┌──────────────────────────────────┐
           │    │  Backend VPC (10.20.0.0/16)       │
           │    │  MCP Bridge (Fargate)              │
           │    │  → RAG API → Bedrock KB            │
           │    │  + OpenSearch Serverless            │
           │    │  [RTL, Spec, 설계 문서]             │
           │    └──────────────────────────────────┘
           │
     SaaS ↔ SaaS (직접)
```

**할 일 목록 (순서대로):**

| # | 작업 | 한 줄 설명 |
|---|------|-----------|
| 1 | Quick Suite 계정 설정 | 버지니아, IAM Identity Center 연동 |
| 2 | 라이선스 배포 | Enterprise 30명 + Professional 270명 |
| 3 | Quick Index 소스 연결 | Confluence, SharePoint, Jira |
| 4 | MCP Bridge 배포 | server.js → Fargate, NLB + PrivateLink |
| 5 | Quick Suite MCP 등록 | Admin → Integrations → MCP → Bridge 엔드포인트 |
| 6 | Spaces 구성 | 팀별 Space + 데이터/액션 매핑 |
| 7 | Quick Automate 파일럿 | IT/DevOps가 2~3개 워크플로우 시범 구축 |
| 8 | PoC 검증 | 10개 항목 테스트 (섹션 10 참조) |
| 9 | ChatGPT Business 해지 | 검증 완료 후 전환 |

**단기 비용:**

| 항목 | 월 비용 |
|------|---------|
| Quick Suite (30 Enterprise + 270 Professional) | $6,600 |
| Private RAG 인프라 (현행) | ~$450 |
| MCP Bridge Fargate + NLB + PrivateLink | ~$40 |
| **합계** | **~$7,090/month** |

참고로 ChatGPT Business가 지금 ~$7,500/month다. 비슷하거나 더 싸면서, 할 수 있는 게 비교가 안 된다.


### 중장기 (6개월 ~ 1년): Private RAG 경량화

Quick Suite가 안정되면, Private RAG의 가장 비싼 부분을 손본다. OpenSearch Serverless OCU 고정 비용을 없애는 게 목표다.

| 검토 항목 | 내용 | 언제 판단하나 |
|----------|------|-------------|
| S3 Vectors 전환 | OpenSearch OCU $350 → S3 Vectors $수십 | 서비스 안정성 확인 후 |
| 데이터 규모 모니터링 | OCU 자동 스케일 추이 관찰 | 월별 비용 리뷰 |
| Quick Index 보안 강화 | CMK 지원, VPC 배포 옵션 | AWS SA와 PoC 기간 중 협의 |
| 데이터 분류 재검토 | Level 2 → Quick Index 이관 가능? | 보안팀과 협의 |
| Bedrock 모델 업그레이드 | Claude 4+ 신규 모델 적용 | 모델 출시 시 |

S3 Vectors로 전환하면 비용 구조가 확 달라진다:

| 항목 | 월 비용 |
|------|---------|
| Quick Suite | $6,600 |
| Private RAG (S3 Vectors + Bedrock + Lambda) | ~$50~100 |
| MCP Bridge + PrivateLink | ~$40 |
| **합계** | **~$6,740/month** |

지금 ChatGPT Business에 쓰는 $7,500보다 $760 싸다. 그러면서 BI, 자동화, 통합 검색이 전부 포함이다.

---

## 10. PoC 검증: 이것만 통과하면 간다

10개 항목이다. 하나라도 실패하면 해당 영역을 보완하고 재검증한다.

| # | 뭘 테스트하나 | 통과 기준 |
|---|-------------|----------|
| 1 | Quick Suite 로그인 | IAM Identity Center SSO 정상 동작 |
| 2 | Confluence 인덱싱 | Quick Index로 문서 검색, 결과 정확 |
| 3 | SharePoint 인덱싱 | 파일 검색 정상 |
| 4 | Jira 액션 | 이슈 생성/조회 CRUD 정상 |
| 5 | Private RAG 질의 | MCP Bridge 경유, 기술 문서 기반 답변 정확 |
| 6 | Quick Research | 내부+외부 데이터 기반 리서치 보고서 품질 |
| 7 | Quick Sight 대시보드 | 데이터 시각화 정상 |
| 8 | Quick Automate 워크플로우 | Jira→RAG→Confluence 연계 동작 |
| 9 | Private 접근 | PrivateLink 경유 VPN 접근 정상 |
| 10 | 권한 분리 | Professional 사용자가 Automate 작성 불가 확인 |

---

## 11. 실제로 쓰면 이런 느낌이다

### 엔지니어가 스펙을 찾을 때

```
엔지니어: "SoC 인터럽트 컨트롤러의 우선순위 처리 방식은?"

Quick Suite AI:
  📄 [Private RAG] SoC_Interrupt_Controller_Spec_v2.3.pdf, 섹션 4.2:
  "8레벨 우선순위 지원, 레벨/엣지 트리거 모두 지원,
   동일 우선순위 시 인터럽트 번호 낮은 것 우선"

  📝 [Confluence] 2026-02 SoC 설계 리뷰 회의록:
  "인터럽트 우선순위 변경 논의 — 차기 버전에서 16레벨로 확장 예정"
```

두 곳에서 답이 온다. Private RAG에서는 공식 스펙을, Quick Index에서는 최근 회의록을. 예전 같으면 30분 걸렸을 일이 10초면 끝난다.

### 팀 리더가 현황을 볼 때

```
팀 리더: "이번 주 SoC팀 현황 보여줘"

Quick Suite:
  📊 Jira: 이슈 12개 진행 중, 3개 블로커
  📈 Quick Sight: 스프린트 번다운 차트
  📄 Private RAG: 최근 테스트 결과 요약
```

Jira 열고, 대시보드 열고, RAG 따로 열 필요 없다. 한 번의 질문으로 전부 나온다.

### 자동화가 돌아갈 때

```
[트리거] Jira 이슈 상태 → "Done"

  1. Confluence에 완료 보고서 자동 생성
  2. Private RAG에서 관련 Spec 문서 참조 추가
  3. 팀 리더에게 알림
  4. Quick Sight 대시보드 자동 갱신
```

사람이 할 일: 없음. Quick Automate가 알아서 한다.


---

## 12. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                      사내 네트워크 (192.128.0.0/16)               │
│                                                                 │
│  👤 엔지니어 → Quick Suite (브라우저/확장)                        │
│  👤 엔지니어 → Obot (챗봇) → MCP Bridge (localhost:3100)         │
│  👤 관리자   → 웹 UI → 문서 업로드                                │
│                                                                 │
└────────────────┬──────────────────────┬─────────────────────────┘
                 │ VPN (TGW)            │ 인터넷 (Proxy 통제)
                 ▼                      ▼
┌────────────────────────┐  ┌──────────────────────────────────┐
│  AWS 서울 (Frontend)    │  │  Quick Suite (SaaS, us-east-1)   │
│                        │  │                                  │
│  API GW → Lambda       │  │  Chat / Research / Automate      │
│  Route53 (DNS)         │  │  Quick Sight (BI)                │
│  S3 (서울)             │  │  Quick Index                     │
│                        │  │    ← Confluence Cloud            │
└───────────┬────────────┘  │    ← SharePoint                  │
            │ VPC Peering   │    ← Jira Cloud [Action]         │
            ▼               │                                  │
┌───────────────────────┐   │  MCP Action ──┐                  │
│  AWS 버지니아 (Backend) │   └───────────────┼──────────────────┘
│                       │                   │ PrivateLink
│  Bedrock KB + Claude  │◄──────────────────┘
│  OpenSearch Serverless│   MCP Bridge (Fargate)
│  S3 (버지니아)        │   → RAG API
│                       │
│  [RTL Code, Spec,     │
│   설계 아키텍처]       │
│  Air-Gapped, KMS 암호화│
└───────────────────────┘
```

---

> **작성**: IT/DevOps · 2026-03-23
> **상태**: PoC 진행 중
> **다음**: PoC 검증 10개 항목 통과 → ChatGPT Business 해지 → 전사 롤아웃
