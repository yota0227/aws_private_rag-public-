# RTL 인덱싱 네트워크 경로 분석 리포트

**작성일**: 2026-05-23
**목적**: Lambda 기반 RTL 인덱싱 시 네트워크 경로 분석 및 차단 포인트 식별
**상태**: SG Egress 포트 6333 미허용으로 Qdrant 접근 불가 확인

---

## 1. 시스템 구성 요소

| 구성 요소 | 위치 | IP/엔드포인트 | 역할 |
|----------|------|--------------|------|
| 개발자 PC (집) | 인터넷 | 공인 IP | reindex 스크립트 실행, Lambda 호출 |
| 사내 PC | 192.128.0.0/16 | 사설 IP | 동일 스크립트 실행 가능 |
| AWS Lambda API | 퍼블릭 | lambda.ap-northeast-2.amazonaws.com | Lambda invoke 엔드포인트 |
| RTL Parser Lambda | Frontend VPC (10.10.0.0/16) | ENI 할당 | RTL 파싱 + 임베딩 + 인덱싱 |
| S3 버킷 | Seoul 리전 | bos-ai-rtl-src-533335672315 | RTL 소스 파일 저장 |
| Bedrock Titan Embed | Virginia (us-east-1) | bedrock-runtime.us-east-1 | 벡터 임베딩 생성 |
| Qdrant | Backend VPC (10.20.0.0/16) | 10.20.1.217:6333 | 벡터 DB 저장/검색 |

---

## 2. 네트워크 경로 다이어그램 — 집에서 접근

```
┌─────────────────────────────────────────────────────────────────────────┐
│  개발자 PC (집, 인터넷)                                                  │
│  └─ python3 reindex_all_rtl.py                                          │
│     └─ boto3.client('lambda').invoke(InvocationType='Event')            │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │ ① HTTPS (TCP 443)
                                 │ 목적지: lambda.ap-northeast-2.amazonaws.com
                                 │ 인증: AWS IAM Credentials (Access Key)
                                 │ 경로: 인터넷 → AWS 퍼블릭 엔드포인트
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  AWS Lambda Service (Control Plane)                                      │
│  - IAM 인증 확인                                                         │
│  - Event 큐에 적재 (비동기)                                              │
│  - Lambda 실행 환경 생성 (Frontend VPC ENI 부착)                         │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │ ② Lambda 실행 시작
                                 │ VPC ENI를 통해 네트워크 접근
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Seoul (ap-northeast-2) — Frontend VPC (10.10.0.0/16)                   │
│                                                                          │
│  ┌─────────────────────────────────────────────────┐                    │
│  │  Lambda 실행 환경                                │                    │
│  │  - VPC: vpc-0a118e1bf21d0c057                    │                    │
│  │  - Subnet: subnet-0ec356f8f9af0ffca              │                    │
│  │  - SG: sg-047612d9bc16a5ff6                      │                    │
│  │  - ENI: 10.10.x.x (동적 할당)                    │                    │
│  │                                                   │                    │
│  │  handler.py 실행 흐름:                            │                    │
│  │  1. S3 GetObject (RTL 파일 읽기)                  │                    │
│  │  2. 정규식 파싱                                   │                    │
│  │  3. Bedrock Titan Embed 호출 (임베딩 생성)        │                    │
│  │  4. Qdrant upsert (벡터 저장)  ← ❌ 여기서 실패   │                    │
│  └────────┬──────────┬──────────┬────────────────────┘                    │
│           │          │          │                                         │
│   ┌───────▼──┐  ┌───▼────┐  ┌──▼─────────────────┐                      │
│   │ ③ S3     │  │④ Bedrock│  │⑤ Qdrant           │                      │
│   │ Gateway  │  │ VPC     │  │ TCP 6333           │                      │
│   │ Endpoint │  │ Endpoint│  │ → 10.20.1.217      │                      │
│   │ ✅ 성공  │  │ ✅ 성공 │  │ ❌ SG Egress 차단! │                      │
│   └──────────┘  └────────┘  └────────────────────┘                      │
│                                     │                                    │
│  ┌──────────────────────────────────┼──────────────────────────────────┐ │
│  │  SG Egress 규칙 (sg-047612d9bc16a5ff6)                              │ │
│  │                                                                      │ │
│  │  허용:                                                               │ │
│  │  ✅ TCP 443 → 10.10.0.0/16 (Seoul VPC Endpoints)                   │ │
│  │  ✅ TCP 443 → 10.20.0.0/16 (Virginia via Peering)                  │ │
│  │  ✅ TCP 443 → S3 Prefix List (Gateway Endpoint)                    │ │
│  │                                                                      │ │
│  │  차단:                                                               │ │
│  │  ❌ TCP 6333 → 어디든 (규칙 없음!)                                  │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘

  ※ SG에서 차단되므로 아래 경로는 도달하지 않음
  ※ 만약 SG가 열려있다면:

┌──────────────────────────────────────────────────────────────────────────┐
│  VPC Peering (pcx-0a44f0b90565313f7) — Active                            │
│  Seoul Route Table: 10.20.0.0/16 → pcx-0a44f ✅                         │
│  Virginia Main RT:  10.10.0.0/16 → pcx-0a44f ✅                         │
└──────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Virginia (us-east-1) — Backend VPC (10.20.0.0/16)                       │
│                                                                          │
│  ┌────────────────────────────────────────────────────┐                  │
│  │  Qdrant EC2 (i-0d520340617eb5484)                  │                  │
│  │  - IP: 10.20.1.217                                 │                  │
│  │  - Port: 6333 (REST), 6334 (gRPC)                  │                  │
│  │  - SG Inbound:                                     │                  │
│  │    ✅ TCP 6333 ← 10.10.0.0/16                     │                  │
│  │    ✅ TCP 6333 ← 10.20.0.0/16                     │                  │
│  │    ✅ TCP 6334 ← 10.10.0.0/16                     │                  │
│  └────────────────────────────────────────────────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 네트워크 경로 다이어그램 — 회사에서 접근 (192.128.0.0/16)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  사내 PC (192.128.0.0/16, 온프레미스)                                    │
│  └─ python3 reindex_all_rtl.py                                          │
│     └─ boto3.client('lambda').invoke(InvocationType='Event')            │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │ ① HTTPS (TCP 443)
                                 │ 목적지: lambda.ap-northeast-2.amazonaws.com
                                 │
                                 │ 경로 A (현재): 인터넷 → AWS 퍼블릭 API
                                 │ 경로 B (가능): VPN → TGW → Lambda VPC Endpoint
                                 │
                                 │ ★ 어떤 경로든 Lambda 내부 동작은 동일
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  AWS Lambda Service (Control Plane)                                      │
│  (이후 흐름은 "집에서 접근"과 100% 동일)                                 │
│                                                                          │
│  Lambda 실행 → S3 ✅ → Bedrock ✅ → Qdrant ❌ (SG 차단)                │
└─────────────────────────────────────────────────────────────────────────┘
```

**핵심**: Lambda invoke 호출자의 위치(집/회사)는 Lambda 내부 네트워크 동작에 영향 없음.
Lambda는 항상 Frontend VPC ENI를 통해 외부 접근하므로, SG/Route Table이 동일하게 적용됨.

---

## 4. Obot에서 RAG 검색 시 경로 (참고 — 인덱싱과 별개)

```
사내 Obot (192.128.0.0/16)
  → VPN → TGW → Frontend VPC
  → MCP Bridge (온프레미스 server.js)
  → Lambda invoke (document-processor)
  → Lambda invoke (rtl-parser, action=search)
  → Qdrant 검색 ← ❌ 동일하게 SG 차단
```

---

## 5. 각 단계별 프로토콜/포트 상세

| 단계 | 출발 | 도착 | 프로토콜/포트 | 경로 | 상태 |
|------|------|------|-------------|------|------|
| ① PC → Lambda API | PC | lambda.ap-northeast-2 | HTTPS/443 | 인터넷 | ✅ |
| ② Lambda → S3 | Lambda ENI | S3 Gateway Endpoint | HTTPS/443 | VPC 내부 | ✅ |
| ③ Lambda → Bedrock | Lambda ENI | bedrock-runtime Endpoint | HTTPS/443 | VPC Peering | ✅ |
| ④ Lambda → Qdrant | Lambda ENI | 10.20.1.217 | TCP/6333 | VPC Peering | ❌ |
| ⑤ Qdrant → Lambda (응답) | 10.20.1.217 | Lambda ENI | TCP/ephemeral | VPC Peering | ✅ (RT 있음) |

---

## 6. 차단 원인 상세

### 유일한 차단 포인트: Lambda SG Egress

```
Security Group: sg-047612d9bc16a5ff6
Name: rtl-parser-lambda-sg-dev

현재 Egress Rules:
┌──────────┬──────┬─────────────────┬─────────────────────────────────────┐
│ Protocol │ Port │ Destination     │ Description                         │
├──────────┼──────┼─────────────────┼─────────────────────────────────────┤
│ TCP      │ 443  │ 10.10.0.0/16    │ HTTPS to Seoul VPC Endpoints        │
│ TCP      │ 443  │ 10.20.0.0/16    │ HTTPS to Virginia via VPC Peering   │
│ TCP      │ 443  │ S3 Prefix List  │ HTTPS to S3 via Gateway Endpoint    │
└──────────┴──────┴─────────────────┴─────────────────────────────────────┘

추가 필요:
┌──────────┬──────┬─────────────────┬─────────────────────────────────────┐
│ TCP      │ 6333 │ 10.20.0.0/16    │ Qdrant REST API via VPC Peering     │
└──────────┴──────┴─────────────────┴─────────────────────────────────────┘
```

---

## 7. 보안 분석

| # | 항목 | 현재 상태 | 리스크 | 권장 조치 |
|---|------|----------|--------|----------|
| 1 | Lambda invoke 인증 | IAM Access Key (인터넷 경유) | 키 유출 시 누구나 호출 가능 | ⚠️ IP 조건 추가 또는 IAM 권한 최소화 |
| 2 | Qdrant 인증 | 없음 (SG만 의존) | SG가 유일한 방어선 | ⚠️ Qdrant API Key 설정 권장 |
| 3 | Qdrant SG Inbound | 10.10.0.0/16 CIDR 전체 허용 | VPC 내 모든 리소스 접근 가능 | ⚠️ Lambda SG ID로 source 제한 |
| 4 | Bedrock 접근 | VPC Endpoint + IAM Role | 적절 | ✅ |
| 5 | S3 접근 | Gateway Endpoint + IAM Role | 적절 | ✅ |
| 6 | Lambda→Qdrant 구간 | VPC Peering (암호화 없음) | AWS 내부 네트워크이므로 수용 가능 | ✅ |

---

## 8. 수정 조치

**즉시 수정 (1건)**:
- Lambda SG (`sg-047612d9bc16a5ff6`) Egress에 TCP 6333 → 10.20.0.0/16 규칙 추가

**Terraform 코드 위치**: `environments/app-layer/bedrock-rag/rtl-parser-lambda.tf`

---

## 9. 수정 후 예상 흐름

```
Lambda (10.10.x.x)
  → TCP 6333 → SG Egress ✅ (규칙 추가)
  → Route Table: 10.20.0.0/16 → pcx-0a44f ✅
  → VPC Peering 통과 ✅
  → Qdrant SG Inbound: TCP 6333 ← 10.10.0.0/16 ✅
  → Qdrant 10.20.1.217:6333 도달 ✅
  → 응답: Qdrant → Virginia RT (10.10→Peering) ✅ → Lambda ✅
```
