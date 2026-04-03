# BOS-AI Private RAG 시스템 개요

> 이 문서는 BOS-AI Private RAG 시스템의 전체적인 구조와 동작 방식을 설명합니다.  
> 사내 구성원 누구나 읽고 시스템을 이해할 수 있도록 작성되었습니다.

---

## 1. 배경

### 왜 이 시스템이 필요한가?

반도체 설계 업무에서는 RTL 코드, 설계 스펙, 아키텍처 문서 등 방대한 기술 문서가 생산됩니다. 이 문서들 속에서 필요한 정보를 빠르게 찾는 것은 엔지니어의 생산성에 직결됩니다.

기존에는 문서를 직접 검색하거나 동료에게 물어봐야 했지만, AI 기술(특히 LLM)을 활용하면 자연어로 질문하고 문서 기반의 정확한 답변을 받을 수 있습니다. 이것이 **RAG(Retrieval-Augmented Generation)** 기술입니다.

다만, 사내 기술 문서는 외부에 노출되어서는 안 되는 민감한 자산입니다. 따라서 **인터넷에 전혀 노출되지 않는 완전 Private 환경**에서 RAG 시스템을 운영해야 합니다.

### RAG란?

**RAG(Retrieval-Augmented Generation)**는 AI가 답변을 생성할 때, 미리 저장된 문서에서 관련 내용을 검색(Retrieval)한 뒤 그 내용을 바탕으로 답변을 생성(Generation)하는 기술입니다.

```
사용자 질문: "이 IP의 인터럽트 처리 방식은?"
        ↓
   [1] 벡터 검색: 질문과 유사한 문서 조각을 찾음
        ↓
   [2] AI 생성: 찾은 문서를 참고하여 답변 작성
        ↓
답변: "해당 IP는 레벨 트리거 방식의 인터럽트를 사용하며..."
```

일반적인 ChatGPT와 다른 점은, **우리 회사의 문서만을 기반으로 답변**한다는 것입니다.

---

## 2. 목적

이 시스템의 핵심 목적은 다음과 같습니다:

| 목적 | 설명 |
|------|------|
| 사내 문서 AI 검색 | 자연어로 질문하면 사내 문서 기반의 정확한 답변 제공 |
| 완전 Private 운영 | 인터넷에 노출 없이 사내 네트워크에서만 접근 가능 |
| 자동화된 문서 파이프라인 | 문서 업로드 → 자동 임베딩 → 즉시 검색 가능 |
| 팀별 지식 관리 | 팀/카테고리별 문서 분류로 검색 정확도 향상 |

---

## 3. 시스템 구조 (아키텍처)

### 3.1 전체 구성도

시스템은 크게 **4개 영역**으로 나뉩니다:

```
┌─────────────────────────────────────────────────────────┐
│                    사내 네트워크 (온프레미스)                │
│                                                         │
│   👤 사용자 ──→ Obot (챗봇) ──→ MCP Bridge ──→ RAG API  │
│                                 (localhost:3100)         │
│   👤 사용자 ──→ 웹 UI ──→ 문서 업로드                     │
│                                                         │
└────────────────────────┬────────────────────────────────┘
                         │ VPN (IPsec, TGW 경유)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              AWS 서울 리전 (Frontend)                     │
│                                                         │
│   API Gateway ──→ Lambda (문서 처리, Python 3.12)        │
│   Route53 (DNS) ──→ rag.corp.bos-semi.com               │
│   S3 (서울) ──→ 문서 임시 저장                            │
│                                                         │
└────────────────────────┬────────────────────────────────┘
                         │ VPC Peering (리전 간 연결)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              AWS 버지니아 리전 (Backend)                   │
│                                                         │
│   Bedrock (Claude AI + Titan Embeddings) ──→ 답변 생성   │
│   OpenSearch Serverless ──→ 벡터 검색                    │
│   S3 (버지니아) ──→ 문서 원본 저장                        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 3.2 왜 서울과 버지니아 두 리전을 사용하나?

AWS Bedrock의 Knowledge Base 기능은 현재 **버지니아(us-east-1) 리전에서 가장 안정적으로 제공**됩니다. 반면, 사내 네트워크와의 VPN 연결은 **서울(ap-northeast-2) 리전**이 지연시간이 짧아 유리합니다.

따라서 다음과 같이 역할을 분리했습니다:

| 리전 | 역할 | 이유 |
|------|------|------|
| 서울 (Frontend) | 사용자 접점, API, 문서 수신 | 낮은 지연시간, VPN 연결 |
| 버지니아 (Backend) | AI 처리, 벡터 검색, 문서 저장 | Bedrock KB 최적 리전 |

두 리전은 **VPC Peering**으로 직접 연결되어 있어, 인터넷을 거치지 않고 AWS 내부 네트워크로 통신합니다.

### 3.3 네트워크 구성

사내 네트워크와 AWS는 **IPsec VPN + Transit Gateway(TGW)**로 연결됩니다. 2026년 3월 기존 VGW 기반 VPN을 TGW 기반으로 완전 전환하여, 모든 VPC가 TGW를 통해 통합 라우팅됩니다.

```
사내 네트워크 (192.128.0.0/16)
    │
    │  IPsec VPN (터널 2개, BGP 동적 라우팅, 고가용성)
    │  vpn-0b2b65e9414092369
    │
    ▼
Transit Gateway (tgw-0897383168475b532, 중앙 라우터)
    │
    ├──→ Frontend VPC (10.10.0.0/16) ── 서울, RAG 전용
    │    tgw-attach-066855ae90345791b
    │         └──→ VPC Peering (pcx-0a44f0b90565313f7)
    │                  └──→ Backend VPC (10.20.0.0/16) ── 버지니아
    │
    └──→ Logging VPC (10.200.0.0/16) ── 서울, 로그 수집/분석
         tgw-attach-05eef146458df2e49
```

| 리소스 | ID | 비고 |
|--------|-----|------|
| Transit Gateway | tgw-0897383168475b532 | 중앙 라우터 |
| TGW Route Table | tgw-rtb-06ab3b805ab879efb | 통합 라우팅 테이블 |
| VPN Connection | vpn-0b2b65e9414092369 | BGP 12 routes, 터널 2개 UP |
| Frontend VPC | vpc-0a118e1bf21d0c057 | 10.10.0.0/16, 서울 |
| Backend VPC | vpc-0ed37ff82027c088f | 10.20.0.0/16, 버지니아 |
| Logging VPC | vpc-066c464f9c750ee9e | 10.200.0.0/16, 서울 |
| VPC Peering | pcx-0a44f0b90565313f7 | 서울 ↔ 버지니아 |

> 상세 내용: [docs/deep-dive-network-architecture.md](docs/deep-dive-network-architecture.md)  
> VPN 마이그레이션 상세: [docs/vpn-migration-report-20260323.md](docs/vpn-migration-report-20260323.md)

### 3.4 주요 컴포넌트 설명

| 컴포넌트 | 역할 | 위치 |
|---------|------|------|
| Obot | 사내 챗봇 플랫폼, MCP Gateway 역할 | 온프레미스 |
| MCP Bridge | Obot과 RAG API를 연결하는 브릿지 서버 (Streamable HTTP + Legacy SSE) | 온프레미스 (localhost:3100) |
| API Gateway | RAG API 진입점 (Private, VPC Endpoint 전용) | 서울 |
| Lambda | 문서 처리, 질의 처리 함수 (Python 3.12) | 서울 |
| S3 (서울) | 업로드된 문서 임시 저장 | 서울 |
| S3 (버지니아) | 문서 원본 저장, Bedrock KB 데이터 소스 | 버지니아 |
| Bedrock KB | 문서 임베딩 및 AI 답변 생성 (Claude + Titan Embeddings) | 버지니아 |
| OpenSearch Serverless | 벡터 데이터베이스 (유사 문서 검색) | 버지니아 |
| Route53 | DNS 해석 (rag.corp.bos-semi.com) | 서울 |
| Transit Gateway | VPC 간 라우팅 중앙 관리 | 서울 |

> 상세 내용: [docs/deep-dive-component-details.md](docs/deep-dive-component-details.md)

---

## 4. 데이터 흐름

### 4.1 문서 업로드 흐름

사용자가 문서를 업로드하면 자동으로 AI가 검색할 수 있는 형태로 변환됩니다:

```
① 사용자가 웹 UI에서 파일 선택 & 업로드
        ↓
② API Gateway → Lambda가 문서를 수신
        ↓
③ S3 (서울)에 문서 저장
        ↓  (자동 복제, 약 5~15분)
④ S3 (버지니아)에 복제 완료
        ↓
⑤ Bedrock KB가 문서를 읽고 벡터(임베딩)로 변환
        ↓
⑥ OpenSearch에 벡터 저장 → 검색 가능 상태
```

### 4.2 RAG 질의 흐름

사용자가 Obot 챗봇에서 질문하면 다음과 같이 처리됩니다:

```
① 사용자가 Obot에서 질문 입력
        ↓
② Obot → MCP Bridge (localhost:3100) → RAG API 호출
        ↓
③ API Gateway → Lambda가 질문 수신
        ↓
④ OpenSearch에서 질문과 유사한 문서 조각 검색
        ↓
⑤ Bedrock (Claude AI)가 검색된 문서를 참고하여 답변 생성
        ↓
⑥ 답변이 MCP Bridge → Obot 챗봇에 표시
```

MCP Bridge는 두 가지 전송 방식을 지원합니다:
- **Streamable HTTP**: `http://localhost:3100/mcp` (Obot 기본 연결 방식)
- **Legacy SSE**: `http://localhost:3100/sse` (기존 SSE 클라이언트 호환)

### 4.3 DNS 해석 흐름

사용자가 `rag.corp.bos-semi.com`에 접근할 때의 DNS 처리:

```
① 사용자 PC에서 rag.corp.bos-semi.com 접속 시도
        ↓
② 사내 DNS 서버가 *.corp.bos-semi.com 쿼리를 Route53으로 전달
   (조건부 포워딩: 이 도메인만 AWS로 전달, 나머지는 기존 경로 유지)
        ↓
③ Route53 Resolver가 Private Hosted Zone에서 IP 조회
        ↓
④ VPC Endpoint의 Private IP 반환 (10.10.x.x)
        ↓
⑤ 사용자 PC가 해당 IP로 HTTPS 요청 전송
```

> 상세 내용: [docs/deep-dive-data-flow.md](docs/deep-dive-data-flow.md)

---

## 5. 보안 정책

이 시스템은 **완전 Air-Gapped(인터넷 격리)** 환경으로 설계되었습니다.

### 5.1 네트워크 격리

| 보안 항목 | 상태 | 설명 |
|----------|------|------|
| Internet Gateway | 없음 | Private RAG VPC에 인터넷 연결 자체가 없음 |
| NAT Gateway | 없음 | 외부로 나가는 경로 자체가 없음 |
| 0.0.0.0/0 라우팅 | 없음 | 인터넷 라우팅 규칙 자체가 없음 |
| API Gateway 타입 | Private | VPC Endpoint를 통해서만 접근 가능 |
| AWS 서비스 접근 | VPC Endpoint 전용 | 모든 AWS 서비스를 Private Link로 접근 |

쉽게 말해, **인터넷에서 이 시스템의 존재 자체를 알 수 없습니다.**

### 5.2 접근 제어

| 계층 | 제어 방식 | 허용 범위 |
|------|----------|----------|
| 네트워크 | Security Group | 사내 IP(192.128.0.0/16)만 허용 |
| API | Resource Policy | VPC Endpoint 경유 요청만 허용 |
| DNS | 조건부 포워딩 | *.corp.bos-semi.com만 AWS로 전달 |
| 데이터 | S3 Bucket Policy | VPC Endpoint 경유만 접근 가능 |
| 권한 | IAM 최소 권한 | 각 서비스별 필요한 권한만 부여 |

### 5.3 데이터 암호화

| 구간 | 암호화 방식 |
|------|-----------|
| 전송 중 (VPN) | IPsec 암호화 |
| 전송 중 (API) | TLS 1.2 |
| 저장 중 (S3) | KMS 암호화 |
| 저장 중 (OpenSearch) | KMS 암호화 |

### 5.4 DNS 조건부 포워딩 (중요)

이전에 사내 DNS에 Route53 Endpoint를 **무조건 등록**하여 SaaS 서비스(S3, DynamoDB 등)의 파일 업로드 오류가 발생한 적이 있습니다.

이를 방지하기 위해 **조건부 포워딩**을 적용합니다:
- `*.corp.bos-semi.com` 도메인 쿼리만 Route53으로 전달
- 그 외 모든 도메인은 기존 DNS 경로 유지
- 문제 발생 시 1분 이내 롤백 가능

> 상세 내용: [docs/deep-dive-security-policy.md](docs/deep-dive-security-policy.md)

---

## 6. 사용자 경험 (UX)

### 6.1 RAG 질의 (Obot 챗봇)

사내 네트워크에 연결된 상태에서 Obot 챗봇을 통해 질문합니다:

```
사용자: "SoC의 인터럽트 컨트롤러 스펙에서 우선순위 처리 방식은?"

Obot: "해당 SoC의 인터럽트 컨트롤러는 8레벨 우선순위를 지원하며,
       레벨 트리거와 엣지 트리거를 모두 지원합니다.
       우선순위가 같은 경우 인터럽트 번호가 낮은 것이 우선 처리됩니다.
       
       [출처: SoC_Interrupt_Controller_Spec_v2.3.pdf, 섹션 4.2]"
```

Obot은 MCP Bridge(localhost:3100)를 통해 RAG API를 호출하고, Bedrock KB가 관련 문서를 검색하여 Claude AI가 답변을 생성합니다.

**MCP 연결 정보:**

| 방식 | URL | 용도 |
|------|-----|------|
| Streamable HTTP | `http://localhost:3100/mcp` | Obot 기본 연결 (권장) |
| Legacy SSE | `http://localhost:3100/sse` | 기존 SSE 클라이언트 호환 |
| Health Check | `http://localhost:3100/health` | 서버 상태 확인 |

**MCP 도구 목록 (6개):**

| 도구 | 설명 |
|------|------|
| `rag_query` | RAG 지식 베이스에 자연어 질의 (문서 검색 + AI 답변) |
| `rag_list_documents` | 업로드된 문서 파일 목록 조회 (팀/카테고리 필터) |
| `rag_categories` | 등록된 팀/카테고리 목록 조회 |
| `rag_upload_status` | 최근 업로드 문서의 KB Sync 상태 조회 |
| `rag_extract_status` | 압축 파일 해제 작업(Extraction Task) 상태 조회 |
| `rag_delete_document` | RAG 지식 베이스에서 문서 삭제 (S3 삭제 + KB Sync) |

### 6.2 문서 업로드 (웹 UI)

브라우저에서 업로드 페이지에 접속합니다 (사내 네트워크 필수):

**업로드 절차:**
1. 팀 선택 (예: SoC)
2. 카테고리 선택 (code 또는 spec)
3. 파일 드래그 앤 드롭 또는 선택
4. 업로드 시작 클릭

**지원 파일 형식:**

| 형식 | 확장자 | 용도 |
|------|--------|------|
| PDF | `.pdf` | 스펙 문서, 데이터시트 |
| 텍스트 | `.txt` | 코드, 로그, 설정 파일 |
| Word | `.docx` | 설계 문서, 보고서 |
| Markdown | `.md` | 기술 문서 |
| CSV | `.csv` | 테스트 결과, 데이터 |
| HTML | `.html` | 웹 문서 |

업로드 후 약 15~30분이면 AI가 검색할 수 있는 상태가 됩니다.

> 상세 내용: [docs/rag-upload-guide.md](docs/rag-upload-guide.md)

### 6.3 관리자 운영

관리자는 다음 작업을 수행할 수 있습니다:

| 작업 | 방법 | 참고 문서 |
|------|------|----------|
| 시스템 상태 확인 | CloudWatch 대시보드 | [docs/OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md) |
| 팀/카테고리 추가 | Lambda 코드 수정 후 배포 | [docs/rag-upload-guide.md](docs/rag-upload-guide.md) |
| 인프라 배포/변경 | Terraform apply | [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) |
| 장애 대응 | 운영 런북 참조 | [docs/OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md) |
| 롤백 | Phase별 롤백 절차 | [docs/rollback-plan.md](docs/rollback-plan.md) |

---

## 7. 기술 스택 요약

| 영역 | 기술 |
|------|------|
| IaC (인프라 코드) | Terraform |
| AI 모델 | AWS Bedrock (Claude, Titan Embeddings) |
| 벡터 DB | OpenSearch Serverless |
| 서버리스 컴퓨팅 | AWS Lambda (Python 3.12) |
| API | Amazon API Gateway (Private REST API) |
| 스토리지 | Amazon S3 (Cross-Region Replication) |
| 네트워크 | VPC, Transit Gateway, VPC Peering, VPC Endpoints |
| DNS | Route53 Private Hosted Zone, Resolver Endpoints |
| 보안 | KMS, IAM, Security Groups, VPC Endpoints |
| 모니터링 | CloudWatch, CloudTrail, Grafana |
| 챗봇 | Obot (오픈소스) + MCP Bridge (Node.js, Express + @modelcontextprotocol/sdk) |
| BI/분석 | Amazon Quick (QuickSight) Enterprise Edition — VPC Endpoint Private 접근 |

---

## 8. 딥다이브 문서 목록

더 자세한 내용이 필요하면 아래 문서를 참고하세요:

| 문서 | 설명 |
|------|------|
| [docs/3_private-rag-api/deep-dive-network-architecture.md](docs/3_private-rag-api/deep-dive-network-architecture.md) | 네트워크 아키텍처 상세 (VPC, TGW, VPN, Peering) |
| [docs/3_private-rag-api/deep-dive-component-details.md](docs/3_private-rag-api/deep-dive-component-details.md) | 각 컴포넌트 상세 설명 (Lambda, Bedrock, OpenSearch 등) |
| [docs/3_private-rag-api/deep-dive-data-flow.md](docs/3_private-rag-api/deep-dive-data-flow.md) | 데이터 흐름 상세 (업로드, 질의, DNS) |
| [docs/3_private-rag-api/deep-dive-security-policy.md](docs/3_private-rag-api/deep-dive-security-policy.md) | 보안 정책 상세 (네트워크 격리, IAM, 암호화) |
| [docs/3_private-rag-api/rag-upload-guide.md](docs/3_private-rag-api/rag-upload-guide.md) | 문서 업로드 사용자 가이드 |
| [docs/1_bedrock-rag-deployment/DEPLOYMENT_GUIDE.md](docs/1_bedrock-rag-deployment/DEPLOYMENT_GUIDE.md) | 인프라 배포 가이드 |
| [docs/3_private-rag-api/OPERATIONAL_RUNBOOK.md](docs/3_private-rag-api/OPERATIONAL_RUNBOOK.md) | 운영 및 트러블슈팅 가이드 |
| [docs/3_private-rag-api/dns-conditional-forwarding-guide.md](docs/3_private-rag-api/dns-conditional-forwarding-guide.md) | DNS 조건부 포워딩 설정 가이드 |
| [docs/2_vpc-consolidation/architecture-as-is-to-be.md](docs/2_vpc-consolidation/architecture-as-is-to-be.md) | As-Is / To-Be 아키텍처 비교 |
| [docs/2_vpc-consolidation/vpn-migration-report-20260323.md](docs/2_vpc-consolidation/vpn-migration-report-20260323.md) | VPN 마이그레이션 보고서 (VGW→TGW 전환) |
| [docs/1_bedrock-rag-deployment/rollback-plan.md](docs/1_bedrock-rag-deployment/rollback-plan.md) | 롤백 계획 |
| [docs/8_quicksight-private-integration/quicksight-guide.md](docs/8_quicksight-private-integration/quicksight-guide.md) | Amazon Quick 운영 가이드 (Admin/User/모니터링) |
| [docs/README.md](docs/README.md) | 문서 디렉토리 구조 및 스펙 매핑 |

---

## 9. 비용 최적화 (2026년 3월)

2026년 3월 인프라 감사를 통해 미사용/중복 리소스를 정리하여 월 약 $2,150의 비용을 절감했습니다.

| 삭제 리소스 | 절감 비용 (월) |
|------------|---------------|
| 중복 OpenSearch Serverless 컬렉션 x2 | ~$700 |
| 중복 Bedrock Knowledge Base x2 | ~$50 |
| 미사용 Aurora PostgreSQL 클러스터 x2 | ~$900 |
| ACM Private CA | ~$400 |
| 미사용 EKS 클러스터 | ~$100 |
| **합계** | **~$2,150/월** |

또한 VPN 아키텍처를 VGW 기반에서 TGW 기반으로 통합하여 네트워크 관리 복잡도를 줄이고, 기존 VPN/VGW를 완전 삭제했습니다.

---

> **작성일**: 2026-04-03 (최종 업데이트)  
> **대상**: 사내 전체 구성원 및 관심 있는 엔지니어  
> **문의**: IT/DevOps 팀
