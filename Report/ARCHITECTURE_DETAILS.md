# BOS-AI RAG 아키텍처 상세 설명

## 📐 시스템 목적

**목표**: 온프렘 환경의 대규모 문서를 AWS 클라우드의 AI 모델과 연결하여 검색 및 생성 기능을 제공하는 하이브리드 RAG 시스템 구축

**핵심 요구사항**:
1. 온프렘과 AWS 간 안전한 네트워크 연결
2. 문서 자동 처리 및 벡터화
3. 대규모 벡터 검색 (OpenSearch Serverless)
4. AI 기반 응답 생성 (Bedrock)
5. 중앙화된 로깅 및 모니터링

---

## 🏗️ 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                      온프렘 (192.128.0.0/16)                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  사용자 PC / 애플리케이션                                  │  │
│  │  - 문서 업로드                                            │  │
│  │  - RAG 질의                                              │  │
│  │  - 결과 조회                                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            ↓ VPN (IPsec)                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FortiGate 60F v7.4.11                                   │  │
│  │  - IPsec Tunnel 1: 3.38.69.188                          │  │
│  │  - IPsec Tunnel 2: 43.200.222.199                       │  │
│  │  - BGP ASN: 65000                                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            ↓ 인터넷
┌─────────────────────────────────────────────────────────────────┐
│                    AWS Transit Gateway                           │
│                  (tgw-0897383168475b532)                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  라우팅 테이블 (각 VPC별 독립적 정책)                     │  │
│  │  - 온프렘 (192.128.0.0/16) → 각 VPC로 라우팅            │  │
│  │  - VPC 간 라우팅 (TGW 경유)                             │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
        ↓                    ↓                    ↓
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Logging VPC      │  │ Private RAG VPC  │  │ US Backend VPC   │
│ (10.200.0.0/16)  │  │ (10.10.0.0/16)   │  │ (10.20.0.0/16)   │
│ ap-northeast-2   │  │ ap-northeast-2   │  │ us-east-1        │
│                  │  │                  │  │                  │
│ ┌──────────────┐ │  │ ┌──────────────┐ │  │ ┌──────────────┐ │
│ │ Route53      │ │  │ │ API Gateway  │ │  │ │ Bedrock KB   │ │
│ │ Resolver     │ │  │ │ (Private)    │ │  │ │              │ │
│ │ Inbound      │ │  │ │              │ │  │ │ ID:          │ │
│ │ 10.10.1.34   │ │  │ │ r0qa9lzhgi   │ │  │ │ FNNOP3VBZV   │ │
│ │ 10.10.2.144  │ │  │ └──────────────┘ │  │ └──────────────┘ │
│ │              │ │  │        ↓          │  │        ↓         │
│ │ DNS 쿼리     │ │  │ ┌──────────────┐ │  │ ┌──────────────┐ │
│ │ 응답         │ │  │ │ Lambda       │ │  │ │ OpenSearch   │ │
│ │              │ │  │ │ document-    │ │  │ │ Serverless   │ │
│ │ CloudTrail   │ │  │ │ processor    │ │  │ │              │ │
│ │ CloudWatch   │ │  │ │              │ │  │ │ Collection:  │ │
│ │              │ │  │ │ Python 3.12  │ │  │ │ bos-ai-      │ │
│ │ EC2 로그     │ │  │ │ 512MB        │ │  │ │ vectors      │ │
│ │ 수집기       │ │  │ │              │ │  │ │              │ │
│ │              │ │  │ │ VPC:         │ │  │ │ VPC Endpoint │ │
│ │ Grafana      │ │  │ │ 10.10.1.0/24 │ │  │ │ (Seoul):     │ │
│ │ 대시보드     │ │  │ │ 10.10.2.0/24 │ │  │ │ vpce-013aa   │ │
│ │              │ │  │ └──────────────┘ │  │ └──────────────┘ │
│ └──────────────┘ │  │        ↓          │  │        ↑         │
│                  │  │ ┌──────────────┐ │  │ ┌──────────────┐ │
│                  │  │ │ S3 (Seoul)   │ │  │ │ S3 (Virginia)│ │
│                  │  │ │              │ │  │ │              │ │
│                  │  │ │ bos-ai-      │ │  │ │ bos-ai-      │ │
│                  │  │ │ documents-   │ │  │ │ documents-us │ │
│                  │  │ │ seoul-v3     │ │  │ │              │ │
│                  │  │ │              │ │  │ │ Bedrock KB   │ │
│                  │  │ │ VPC Endpoint │ │  │ │ 데이터 소스  │ │
│                  │  │ │ 경유만 접근  │ │  │ │              │ │
│                  │  │ │              │ │  │ │ 크로스 리전  │ │
│                  │  │ │ 크로스 리전  │ │  │ │ 복제 대상    │ │
│                  │  │ │ 복제 소스    │ │  │ │              │ │
│                  │  │ └──────────────┘ │  │ └──────────────┘ │
│                  │  │        ↓          │  │                  │
│                  │  │ ┌──────────────┐ │  │                  │
│                  │  │ │ VPC Endpoints│ │  │                  │
│                  │  │ │              │ │  │                  │
│                  │  │ │ execute-api  │ │  │                  │
│                  │  │ │ S3 Gateway   │ │  │                  │
│                  │  │ │ CloudWatch   │ │  │                  │
│                  │  │ │ Secrets Mgr  │ │  │                  │
│                  │  │ │ OpenSearch   │ │  │                  │
│                  │  │ │ Bedrock      │ │  │                  │
│                  │  │ └──────────────┘ │  │                  │
│                  │  │                  │  │                  │
│                  │  └──────────────────┘  └──────────────────┘
│                  │         ↑                      ↑
│                  │         └──────────────────────┘
│                  │         VPC Peering
│                  │    (pcx-0a44f0b90565313f7)
│                  │
└──────────────────┘
```

---

## 🔄 데이터 흐름 (상세)

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

## 🔐 보안 아키텍처

### 네트워크 보안

**1. VPN 연결**
- IPsec 터널 2개 (고가용성)
- BGP 동적 라우팅
- 온프렘 ASN: 65000
- AWS ASN: 64512

**2. VPC 격리**
- 각 VPC는 독립적 라우팅 정책
- TGW 라우트 테이블로 트래픽 제어
- VPC 간 통신은 명시적 라우트만 허용

**3. VPC Endpoints**
- Private Link 기술 사용
- 인터넷 게이트웨이 불필요
- 온프렘 CIDR (192.128.0.0/16)에서만 접근

### 애플리케이션 보안

**1. API Gateway 정책**
```json
{
  "Effect": "Allow",
  "Principal": "*",
  "Action": "execute-api:Invoke",
  "Resource": "execute-api:/*",
  "Condition": {
    "IpAddress": {
      "aws:SourceIp": "192.128.0.0/16"  // 온프렘만
    }
  }
}
```

**2. S3 버킷 정책**
- VPC Endpoint 경유만 접근
- Terraform IAM 사용자 예외
- S3 복제 역할 예외

**3. IAM 정책**
- Lambda: 최소 권한 원칙
- Bedrock KB: OpenSearch + S3 접근만
- 각 역할별 명시적 권한

### 데이터 보안

**1. 암호화**
- 전송 중: TLS 1.2 (API Gateway, VPC Endpoints)
- 저장 중: KMS 암호화 (S3, OpenSearch)
- 크로스 리전: KMS 키 자동 재암호화

**2. 접근 제어**
- 온프렘 CIDR 기반 필터링
- VPC Endpoint 기반 격리
- IAM 정책 기반 권한 관리

---

## 📊 성능 특성

### 지연시간 (Latency)

| 경로 | 지연시간 | 비고 |
|------|---------|------|
| 온프렘 → Route53 Resolver | 21ms | DNS 쿼리 |
| 온프렘 → API Gateway | 50-100ms | 문서 업로드 |
| Lambda → OpenSearch | 100-150ms | 벡터 검색 |
| Lambda → Bedrock | 150-200ms | 응답 생성 |
| **전체 RAG 질의** | **300-500ms** | 평균 응답 시간 |

### 처리량 (Throughput)

| 컴포넌트 | 용량 | 비고 |
|---------|------|------|
| Lambda | 1000 req/s | 동시 실행 제한 |
| API Gateway | 10,000 req/s | 기본 제한 |
| OpenSearch | 100 req/s | 컬렉션 크기 의존 |
| Bedrock | 100 req/s | 모델 제한 |

### 저장소 (Storage)

| 서비스 | 용량 | 비고 |
|--------|------|------|
| S3 (Seoul) | 무제한 | 비용 기반 |
| S3 (Virginia) | 무제한 | 비용 기반 |
| OpenSearch | 100GB | 컬렉션 크기 |

---

## 🔄 고가용성 설계

### 1. 다중 가용 영역 (Multi-AZ)

**Seoul (ap-northeast-2)**
- AZ-a: 10.10.1.0/24
- AZ-b: 10.10.2.0/24
- Lambda: 양쪽 AZ에 배포
- VPC Endpoints: 양쪽 AZ에 배포

**Virginia (us-east-1)**
- OpenSearch: 자동 다중 AZ
- Bedrock: 자동 다중 AZ

### 2. 자동 페일오버

**VPN 터널**
- Tunnel 1 실패 → Tunnel 2 자동 전환
- BGP 헬스 체크 (10초)

**API Gateway**
- 다중 AZ 자동 배포
- 한 AZ 실패 → 다른 AZ 자동 전환

**Lambda**
- 다중 AZ 자동 배포
- 한 AZ 실패 → 다른 AZ 자동 전환

### 3. 데이터 복제

**S3 크로스 리전 복제**
- Seoul → Virginia 자동 복제
- 15분 이내 완료
- 실패 시 자동 재시도

---

## 📈 확장성 (Scalability)

### 수평 확장 (Horizontal Scaling)

**Lambda**
- 자동 스케일링: 0 → 1000 동시 실행
- 콜드 스타트: ~1초
- 웜 스타트: ~100ms

**OpenSearch Serverless**
- 자동 스케일링: 요청 기반
- 최대 100 OCU (OpenSearch Compute Units)

**Bedrock**
- 자동 스케일링: 요청 기반
- 최대 100 req/s (기본)

### 수직 확장 (Vertical Scaling)

**Lambda**
- 메모리: 128MB → 10GB
- CPU: 메모리에 비례

**OpenSearch**
- 컬렉션 크기: 증가 가능
- 인덱스 샤드: 자동 관리

---

## 🛠️ 운영 고려사항

### 모니터링

**CloudWatch 메트릭**
- Lambda: 호출 수, 에러율, 지연시간, 메모리 사용량
- API Gateway: 요청 수, 에러율, 지연시간
- OpenSearch: 인덱싱 속도, 검색 지연시간
- Bedrock: 토큰 사용량, 응답 시간

**CloudTrail 로깅**
- 모든 AWS API 호출 기록
- 90일 보존
- S3에 저장

### 알람

**중요 알람**
- Lambda 에러율 > 1%
- API 응답 시간 > 5초
- OpenSearch 인덱싱 실패
- S3 복제 지연 > 30분

### 백업 및 복구

**S3 버전 관리**
- 모든 객체 버전 유지
- 실수로 삭제된 파일 복구 가능

**OpenSearch 스냅샷**
- 정기적 스냅샷 (일일)
- S3에 저장
- 복구 시간: ~1시간

---

## 💰 비용 최적화

### 비용 드라이버

| 서비스 | 비용 | 최적화 |
|--------|------|--------|
| Lambda | 호출 수 + 실행 시간 | 함수 최적화 |
| API Gateway | 요청 수 | 캐싱 활용 |
| OpenSearch | OCU (시간당) | 자동 스케일링 |
| Bedrock | 토큰 수 | 프롬프트 최적화 |
| S3 | 저장소 + 전송 | 라이프사이클 정책 |
| VPC Endpoints | 시간당 + 처리량 | 필요한 것만 배포 |

### 예상 월 비용 (100GB 문서 기준)

- Lambda: $50-100
- API Gateway: $20-50
- OpenSearch: $200-300
- Bedrock: $100-200
- S3: $50-100
- VPC Endpoints: $50-100
- **합계: $470-850/월**

---

## 🔗 관련 문서

- [배포 3단계 상세 가이드](DEPLOYMENT_PHASES.md)
- [VPN 연결성 테스트](20260303_VPN_CONNECTIVITY_TEST_RESULTS.md)
- [AWS 리소스 인벤토리](20260303_AWS_RESOURCES_INVENTORY.md)

---

**작성일**: 2026-03-06  
**버전**: 1.0  
**상태**: 배포 완료
