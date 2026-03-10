# Deep Dive: 컴포넌트 상세 설명

> 상위 문서: [BOS-AI Private RAG System Overview](../BOS-AI-Private-RAG-System-Overview.md)

---

## 1. Obot (사내 챗봇)

| 항목 | 값 |
|------|-----|
| 유형 | 오픈소스 챗봇 플랫폼 |
| 위치 | 온프레미스 |
| 역할 | 사용자 인터페이스, MCP Gateway |

Obot은 사내에서 운영하는 오픈소스 챗봇 플랫폼입니다. 사용자가 자연어로 질문하면 MCP(Model Context Protocol)를 통해 RAG API를 호출하고, 결과를 사용자에게 표시합니다.

```
사용자 ──→ Obot UI ──→ MCP Protocol ──→ RAG API (rag.corp.bos-semi.com)
                                              ↓
사용자 ←── Obot UI ←── MCP Protocol ←── AI 답변 반환
```

---

## 2. API Gateway (Private REST API)

| 항목 | 값 |
|------|-----|
| API ID | r0qa9lzhgi |
| 타입 | Private REST API |
| 도메인 | rag.corp.bos-semi.com |
| 접근 방식 | VPC Endpoint (execute-api) 전용 |

**엔드포인트:**

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | /rag/query | RAG 질의 (AI 답변 생성) |
| POST | /rag/documents | 문서 업로드 |
| GET | /rag/health | 시스템 상태 확인 |
| GET | /rag/upload | 웹 업로드 UI |

**Resource Policy:**
- VPC Endpoint에서 오는 요청만 허용
- 온프레미스 IP(192.128.0.0/16)에서만 접근 가능
- 그 외 모든 요청은 403 Forbidden

---

## 3. Lambda (document-processor)

| 항목 | 값 |
|------|-----|
| 함수명 | lambda-document-processor-seoul-prod |
| 런타임 | Python 3.12 |
| 메모리 | 512 MB |
| 타임아웃 | 300초 (5분) |
| VPC | Private RAG VPC (10.10.1.0/24, 10.10.2.0/24) |

Lambda는 RAG 시스템의 핵심 처리 엔진입니다. 두 가지 주요 기능을 수행합니다:

### 3.1 문서 처리

문서 유형에 따라 다른 청킹(분할) 전략을 적용합니다:

| 문서 유형 | 청킹 전략 | 청크 크기 | 설명 |
|----------|----------|----------|------|
| RTL 코드 | Semantic | 2000자 | module/function 구조 보존 |
| 스펙 문서 | Hierarchical | 1500자 | 섹션(#, ##) 기반 분할 |
| 다이어그램 | Fixed | 1000자 | 고정 크기 분할 |
| 일반 텍스트 | Semantic | 1000자 | 문장 경계 기반 분할 |

### 3.2 질의 처리

1. 사용자 질문 수신
2. Bedrock KB에 질의 전달
3. OpenSearch에서 유사 문서 검색
4. Claude AI가 답변 생성
5. 결과 반환

---

## 4. S3 (문서 저장소)

### 4.1 서울 S3 버킷

| 항목 | 값 |
|------|-----|
| 버킷명 | bos-ai-documents-seoul-v3 |
| 리전 | ap-northeast-2 (서울) |
| 암호화 | KMS |
| 버전 관리 | 활성화 |
| 접근 방식 | VPC Endpoint (S3 Gateway) 전용 |

**저장 구조:**
```
bos-ai-documents-seoul-v3/
  documents/
    soc/
      code/     ← RTL 코드, 테스트벤치
      spec/     ← 설계 스펙, 아키텍처 문서
```

### 4.2 버지니아 S3 버킷

| 항목 | 값 |
|------|-----|
| 버킷명 | bos-ai-documents-us |
| 리전 | us-east-1 (버지니아) |
| 용도 | Bedrock KB 데이터 소스 |

### 4.3 Cross-Region Replication

서울 S3에 업로드된 문서는 자동으로 버지니아 S3로 복제됩니다.

```
서울 S3 (업로드) ──→ 자동 복제 (5~15분) ──→ 버지니아 S3 (Bedrock KB 소스)
```

- 복제 시 KMS 키가 자동으로 재암호화됨
- 실패 시 자동 재시도
- 복제 상태는 S3 콘솔 또는 CLI로 확인 가능

---

## 5. Bedrock Knowledge Base

| 항목 | 값 |
|------|-----|
| KB ID | FNNOP3VBZV |
| 리전 | us-east-1 (버지니아) |
| 임베딩 모델 | Amazon Titan Embed Text v1 |
| 생성 모델 | Anthropic Claude |
| 데이터 소스 | S3 (bos-ai-documents-us) |
| Data Source ID | 211WMHQAOK |

**동작 방식:**

1. S3에 새 문서가 복제되면 인제스트 작업 시작
2. 문서를 청크로 분할
3. 각 청크를 Titan Embed 모델로 벡터화
4. 벡터를 OpenSearch Serverless에 저장
5. 질의 시 Claude가 검색된 문서를 참고하여 답변 생성

---

## 6. OpenSearch Serverless

| 항목 | 값 |
|------|-----|
| Collection ID | iw3pzcloa0en8d90hh7 |
| Collection 이름 | bos-ai-vectors |
| 리전 | us-east-1 (버지니아) |
| 인덱스 | bedrock-knowledge-base-index |
| VPC Endpoint (서울) | vpce-013aa002a16145cd0 |

OpenSearch Serverless는 벡터 데이터베이스 역할을 합니다. 문서의 임베딩 벡터를 저장하고, 질의 시 유사한 벡터를 빠르게 검색합니다.

**왜 Serverless인가?**
- 서버 관리 불필요
- 자동 스케일링
- 사용한 만큼만 비용 지불

---

## 7. Route53 (DNS)

### 7.1 Private Hosted Zone

| 항목 | 값 |
|------|-----|
| Zone ID | Z04599582HCRH2UPCSS34 |
| 도메인 | corp.bos-semi.com |
| 연결된 VPC | Private RAG VPC |

**레코드:**

| 이름 | 타입 | 값 |
|------|------|-----|
| rag.corp.bos-semi.com | A (Alias) | execute-api VPC Endpoint DNS |

### 7.2 Resolver Inbound Endpoint

| 항목 | 값 |
|------|-----|
| Endpoint ID | rslvr-in-93384eeb51fc4c4db |
| IP (AZ-a) | 10.10.1.34 |
| IP (AZ-c) | 10.10.2.144 |

온프레미스 DNS 서버가 `*.corp.bos-semi.com` 쿼리를 이 IP로 전달합니다.

---

## 8. 모니터링 컴포넌트

### CloudWatch

| 항목 | 모니터링 대상 |
|------|-------------|
| Lambda 메트릭 | 호출 수, 에러율, 지연시간, 메모리 사용량 |
| API Gateway 메트릭 | 요청 수, 에러율, 지연시간 |
| 알람 | Lambda 에러율 > 1%, API 응답 > 5초 |

### CloudTrail

모든 AWS API 호출을 기록합니다. 보안 감사 및 문제 추적에 활용됩니다.

### Grafana

Logging VPC에 위치한 Grafana 대시보드로 시각화된 모니터링을 제공합니다.

---

## 9. 성능 특성

| 경로 | 지연시간 |
|------|---------|
| 온프레미스 → Route53 Resolver | ~21ms |
| 온프레미스 → API Gateway | 50~100ms |
| Lambda → OpenSearch (벡터 검색) | 100~150ms |
| Lambda → Bedrock (답변 생성) | 150~200ms |
| 전체 RAG 질의 (end-to-end) | 300~500ms |

---

## 참고 문서

- [Lambda 소스 코드](../lambda/document-processor/handler.py)
- [운영 런북](OPERATIONAL_RUNBOOK.md)
- [데모 가이드](demo-guide.md)

---

> **작성일**: 2026-03-10  
> **상위 문서**: [BOS-AI Private RAG System Overview](../BOS-AI-Private-RAG-System-Overview.md)
