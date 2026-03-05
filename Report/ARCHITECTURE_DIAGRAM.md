# BOS-AI RAG 아키텍처 다이어그램

## 전체 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           온프렘 (192.128.0.0/16)                         │
│                                                                            │
│                    사용자 PC / 애플리케이션                               │
│              문서 업로드 | RAG 질의 | 결과 조회                           │
│                                                                            │
│                         FortiGate 60F v7.4.11                             │
│              Tunnel 1: 3.38.69.188 | Tunnel 2: 43.200.222.199            │
│                          BGP ASN: 65000                                   │
└──────────────────────────────────────────────────────────────────────────┘
                                    ↓ VPN (IPsec)
┌──────────────────────────────────────────────────────────────────────────┐
│                        AWS Transit Gateway                                │
│                      (tgw-0897383168475b532)                             │
│                                                                            │
│         라우팅 테이블 (각 VPC별 독립적 정책)                             │
│    온프렘 (192.128.0.0/16) → 각 VPC로 라우팅                            │
│    VPC 간 라우팅 (TGW 경유)                                             │
└──────────────────────────────────────────────────────────────────────────┘
              ↓                        ↓                        ↓
    ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
    │  Logging VPC        │  │ Private RAG VPC     │  │  US Backend VPC     │
    │  (10.200.0.0/16)    │  │ (10.10.0.0/16)      │  │  (10.20.0.0/16)     │
    │  ap-northeast-2     │  │ ap-northeast-2      │  │  us-east-1          │
    │                     │  │                     │  │                     │
    │ ┌─────────────────┐ │  │ ┌─────────────────┐ │  │ ┌─────────────────┐ │
    │ │ Route53         │ │  │ │ API Gateway     │ │  │ │ Bedrock KB      │ │
    │ │ Resolver        │ │  │ │ (Private)       │ │  │ │ ID:             │ │
    │ │ Inbound         │ │  │ │ r0qa9lzhgi      │ │  │ │ FNNOP3VBZV      │ │
    │ │ 10.10.1.34      │ │  │ └─────────────────┘ │  │ └─────────────────┘ │
    │ │ 10.10.2.144     │ │  │         ↓           │  │         ↓           │
    │ │                 │ │  │ ┌─────────────────┐ │  │ ┌─────────────────┐ │
    │ │ DNS 쿼리 응답   │ │  │ │ Lambda          │ │  │ │ OpenSearch      │ │
    │ │                 │ │  │ │ document-       │ │  │ │ Serverless      │ │
    │ │ CloudTrail      │ │  │ │ processor       │ │  │ │ bos-ai-vectors  │ │
    │ │ CloudWatch      │ │  │ │ Python 3.12     │ │  │ │                 │ │
    │ │                 │ │  │ │ 512MB           │ │  │ │ VPC Endpoint    │ │
    │ │ EC2 로그 수집기 │ │  │ │                 │ │  │ │ (Seoul):        │ │
    │ │                 │ │  │ │ VPC:            │ │  │ │ vpce-013aa      │ │
    │ │ Grafana         │ │  │ │ 10.10.1.0/24    │ │  │ └─────────────────┘ │
    │ │ 대시보드        │ │  │ │ 10.10.2.0/24    │ │  │         ↑           │
    │ └─────────────────┘ │  │ └─────────────────┘ │  │ ┌─────────────────┐ │
    │                     │  │         ↓           │  │ │ S3 (Virginia)   │ │
    │                     │  │ ┌─────────────────┐ │  │ │ bos-ai-         │ │
    │                     │  │ │ S3 (Seoul)      │ │  │ │ documents-us    │ │
    │                     │  │ │ bos-ai-         │ │  │ │                 │ │
    │                     │  │ │ documents-      │ │  │ │ Bedrock KB      │ │
    │                     │  │ │ seoul-v3        │ │  │ │ 데이터 소스     │ │
    │                     │  │ │                 │ │  │ │                 │ │
    │                     │  │ │ VPC Endpoint    │ │  │ │ 크로스 리전     │ │
    │                     │  │ │ 경유만 접근     │ │  │ │ 복제 대상       │ │
    │                     │  │ │                 │ │  │ └─────────────────┘ │
    │                     │  │ │ 크로스 리전     │ │  │                     │
    │                     │  │ │ 복제 소스       │ │  │                     │
    │                     │  │ └─────────────────┘ │  │                     │
    │                     │  │         ↓           │  │                     │
    │                     │  │ ┌─────────────────┐ │  │                     │
    │                     │  │ │ VPC Endpoints   │ │  │                     │
    │                     │  │ │ execute-api     │ │  │                     │
    │                     │  │ │ S3 Gateway      │ │  │                     │
    │                     │  │ │ CloudWatch      │ │  │                     │
    │                     │  │ │ Secrets Mgr     │ │  │                     │
    │                     │  │ │ OpenSearch      │ │  │                     │
    │                     │  │ │ Bedrock         │ │  │                     │
    │                     │  │ └─────────────────┘ │  │                     │
    │                     │  │                     │  │                     │
    │                     │  └─────────────────────┘  └─────────────────────┘
    │                     │           ↑                        ↑
    │                     │           └────────────────────────┘
    │                     │           VPC Peering
    │                     │      (pcx-0a44f0b90565313f7)
    │                     │
    └─────────────────────┘
```

## 데이터 흐름

### 1. 문서 업로드 흐름

```
온프렘 사용자
    ↓
POST /rag/documents
    ↓
API Gateway (Private)
    ├─ 정책 검증: 192.128.0.0/16 ✓
    ├─ VPC Endpoint 경유 ✓
    ↓
Lambda (document-processor)
    ├─ 문서 수신
    ├─ 메타데이터 추출
    ├─ 파일 검증
    ↓
S3 (Seoul) - bos-ai-documents-seoul-v3
    ├─ 문서 저장
    ├─ KMS 암호화
    ├─ 버전 관리
    ↓
S3 크로스 리전 복제
    ├─ 자동 트리거
    ├─ 15분 이내 완료
    ├─ KMS 키 자동 재암호화
    ↓
S3 (Virginia) - bos-ai-documents-us
    ├─ 복제 완료
    ↓
Bedrock Knowledge Base
    ├─ 자동 인덱싱 시작
    ├─ 문서 청킹
    ├─ 임베딩 생성 (Titan Embed)
    ↓
OpenSearch Serverless (Virginia)
    ├─ 벡터 저장
    ├─ 인덱싱 완료
    ↓
Lambda 응답
    └─ 업로드 완료 메시지
```

### 2. RAG 질의 흐름

```
온프렘 사용자
    ↓
POST /rag/query
    ├─ 질의: "문서에서 XXX에 대해 설명해줘"
    ↓
API Gateway (Private)
    ├─ 정책 검증: 192.128.0.0/16 ✓
    ↓
Lambda (document-processor)
    ├─ 질의 수신
    ├─ 질의 임베딩 생성 (Titan Embed)
    ↓
OpenSearch Serverless (Virginia)
    ├─ 벡터 검색
    ├─ 유사 문서 5개 검색
    ├─ 관련도 점수 계산
    ↓
Bedrock Knowledge Base
    ├─ 검색된 문서 컨텍스트 전달
    ├─ 질의 + 컨텍스트 조합
    ↓
Bedrock Model (Claude)
    ├─ 응답 생성
    ├─ 컨텍스트 기반 답변
    ↓
Lambda
    ├─ 응답 포맷팅
    ├─ 메타데이터 추가
    ↓
API Gateway
    ↓
온프렘 사용자
    └─ 응답 수신
```

### 3. DNS 해석 흐름

```
온프렘 사용자
    ↓
nslookup rag.corp.bos-semi.com
    ↓
온프렘 DNS 서버
    ├─ 사내 DNS에 미등록
    ├─ Route53 Resolver로 포워딩
    ↓
Route53 Resolver Inbound (10.10.1.34 또는 10.10.2.144)
    ├─ DNS 쿼리 수신
    ├─ AWS Private Hosted Zone 조회
    ↓
Route53 Private Hosted Zone (Z04599582HCRH2UPCSS34)
    ├─ rag.corp.bos-semi.com 조회
    ├─ execute-api VPC Endpoint DNS 이름 반환
    ├─ vpce-0e5f61dd7bd52882e-zlb2sxlo.execute-api.ap-northeast-2.vpce.amazonaws.com
    ↓
온프렘 DNS 서버
    ├─ VPC Endpoint DNS 이름 → IP 해석
    ├─ 10.10.1.21 (AZ-a)
    ├─ 10.10.2.75 (AZ-b)
    ↓
온프렘 사용자
    └─ IP 주소 수신
```

---

**작성일**: 2026-03-06  
**버전**: 1.0
