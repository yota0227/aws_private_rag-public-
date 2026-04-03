# Deep Dive: 데이터 흐름 상세

> 상위 문서: [BOS-AI Private RAG System Overview](../BOS-AI-Private-RAG-System-Overview.md)

---

## 1. 문서 업로드 흐름 (상세)

### 1.1 웹 UI 업로드

```
온프레미스 사용자
    │
    │  ① 브라우저에서 업로드 페이지 접속
    │     https://rag.corp.bos-semi.com/dev/rag/upload
    │
    ▼
사내 DNS 서버
    │
    │  ② rag.corp.bos-semi.com DNS 해석
    │     조건부 포워딩 → Route53 Resolver (10.10.1.34)
    │     → Private Hosted Zone → VPC Endpoint IP 반환
    │
    ▼
VPN 터널 (IPsec)
    │
    │  ③ HTTPS 요청이 VPN을 통해 AWS로 전달
    │
    ▼
Transit Gateway (tgw-0897383168475b532)
    │
    │  ④ 라우팅: 10.10.0.0/16 → Private RAG VPC Attachment
    │
    ▼
VPC Endpoint (execute-api, vpce-0e5f61dd7bd52882e)
    │
    │  ⑤ Private API Gateway로 요청 전달
    │
    ▼
API Gateway (r0qa9lzhgi, Private)
    │
    │  ⑥ Resource Policy 검증
    │     - VPC Endpoint 경유 확인 ✓
    │     - 소스 IP 192.128.0.0/16 확인 ✓
    │
    │  ⑦ POST /rag/documents → Lambda Proxy Integration
    │
    ▼
Lambda (lambda-document-processor-seoul-prod)
    │
    │  ⑧ 문서 수신 및 검증
    │     - 파일 형식 확인
    │     - 메타데이터 추출 (팀, 카테고리)
    │     - 문서 유형 판별 (RTL/Spec/Diagram/Text)
    │
    │  ⑨ S3에 문서 저장
    │     VPC Endpoint (S3 Gateway) 경유
    │
    ▼
S3 (서울, bos-ai-documents-seoul-v3)
    │
    │  ⑩ 문서 저장 완료
    │     - KMS 암호화 적용
    │     - 버전 관리 활성화
    │     - 경로: documents/{team}/{category}/{filename}
    │
    │  ⑪ S3 Cross-Region Replication 자동 트리거
    │     (약 5~15분 소요)
    │
    ▼
S3 (버지니아, bos-ai-documents-us)
    │
    │  ⑫ 복제 완료
    │     - KMS 키 자동 재암호화 (서울 KMS → 버지니아 KMS)
    │
    ▼
Bedrock Knowledge Base (FNNOP3VBZV)
    │
    │  ⑬ 인제스트 작업 시작
    │     - 문서 청킹 (유형별 전략 적용)
    │     - Titan Embed 모델로 벡터 생성
    │
    ▼
OpenSearch Serverless (bos-ai-vectors)
    │
    │  ⑭ 벡터 저장 완료
    │     - 인덱스: bedrock-knowledge-base-index
    │     → 이제 RAG 질의에서 검색 가능
    │
    ▼
Lambda → API Gateway → 사용자
    │
    └─ ⑮ 업로드 완료 응답 반환
```

### 1.2 업로드 소요 시간

| 단계 | 소요 시간 |
|------|----------|
| 업로드 (사용자 → S3 서울) | 즉시 (파일 크기에 따라) |
| Cross-Region Replication | 5~15분 |
| Bedrock KB 인제스트 | 10~30분 (문서 크기에 따라) |
| 전체 (업로드 → 검색 가능) | 약 15~45분 |

---

## 2. RAG 질의 흐름 (상세)

### 2.1 Obot 경유 질의

```
온프레미스 사용자
    │
    │  ① Obot 챗봇에서 질문 입력
    │     "SoC의 인터럽트 처리 방식은?"
    │
    ▼
Obot (사내 챗봇)
    │
    │  ② MCP(Model Context Protocol)로 RAG API 호출
    │     POST https://rag.corp.bos-semi.com/dev/rag/query
    │     Body: {"query": "SoC의 인터럽트 처리 방식은?"}
    │
    ▼
[DNS 해석 → VPN → TGW → VPC Endpoint → API Gateway]
    │
    │  ③ 네트워크 경로 (위 업로드 흐름의 ②~⑥과 동일)
    │
    ▼
Lambda (lambda-document-processor-seoul-prod)
    │
    │  ④ 질의 수신
    │
    │  ⑤ Bedrock KB에 Retrieve & Generate 요청
    │     VPC Peering (pcx-0a44f0b90565313f7) 경유
    │     → 버지니아 Backend VPC
    │
    ▼
Bedrock Knowledge Base (FNNOP3VBZV, 버지니아)
    │
    │  ⑥ 질의 벡터화
    │     Titan Embed 모델로 질문을 벡터로 변환
    │
    │  ⑦ OpenSearch 벡터 검색
    │     유사도가 높은 문서 청크 5개 검색
    │
    ▼
OpenSearch Serverless (bos-ai-vectors, 버지니아)
    │
    │  ⑧ 벡터 검색 결과 반환
    │     - 관련 문서 청크 5개
    │     - 유사도 점수
    │     - 원본 문서 메타데이터
    │
    ▼
Bedrock (Claude AI, 버지니아)
    │
    │  ⑨ 답변 생성
    │     - 검색된 문서 청크를 컨텍스트로 전달
    │     - 질문 + 컨텍스트 조합
    │     - Claude가 문서 기반 답변 생성
    │
    ▼
Lambda → API Gateway → VPN → Obot → 사용자
    │
    └─ ⑩ 답변 표시
         "해당 SoC의 인터럽트 컨트롤러는 8레벨 우선순위를 지원하며..."
         [출처: SoC_Interrupt_Controller_Spec_v2.3.pdf, 섹션 4.2]
```

### 2.2 질의 소요 시간

| 단계 | 소요 시간 |
|------|----------|
| DNS 해석 | ~21ms |
| 네트워크 (VPN → API Gateway) | 50~100ms |
| 벡터 검색 (OpenSearch) | 100~150ms |
| 답변 생성 (Claude) | 150~200ms |
| 전체 (end-to-end) | 300~500ms |

---

## 3. DNS 해석 흐름 (상세)

```
온프레미스 사용자 PC
    │
    │  ① nslookup rag.corp.bos-semi.com
    │
    ▼
사내 DNS 서버
    │
    │  ② 조건부 포워딩 규칙 확인
    │     "corp.bos-semi.com" → Route53 Resolver로 전달
    │     (다른 도메인은 기존 DNS 경로 유지)
    │
    ▼
Route53 Resolver Inbound (10.10.1.34 또는 10.10.2.144)
    │
    │  ③ Private Hosted Zone 조회
    │     Zone: corp.bos-semi.com (Z04599582HCRH2UPCSS34)
    │
    ▼
Private Hosted Zone
    │
    │  ④ 레코드 조회
    │     rag.corp.bos-semi.com → A (Alias)
    │     → vpce-0e5f61dd7bd52882e-zlb2sxlo.execute-api.ap-northeast-2.vpce.amazonaws.com
    │
    ▼
Route53 Resolver
    │
    │  ⑤ VPC Endpoint DNS → Private IP 해석
    │     10.10.1.21 (AZ-a) 또는 10.10.2.75 (AZ-c)
    │
    ▼
사내 DNS 서버 → 사용자 PC
    │
    └─ ⑥ IP 주소 반환: 10.10.1.21
         사용자 PC가 이 IP로 HTTPS 요청 전송
```

### 3.1 조건부 포워딩이 중요한 이유

이전에 사내 DNS에 Route53 Endpoint를 **무조건 등록**했을 때 발생한 문제:

```
[문제 상황]
사내 DNS → Route53 (모든 쿼리 전달)
    → s3.amazonaws.com → Private IP 반환 (VPC Endpoint IP)
    → SaaS 서비스가 Private IP로 접근 시도 → 실패!
    → 파일 업로드 오류 발생
```

조건부 포워딩으로 해결:

```
[정상 상황]
사내 DNS
    ├─ *.corp.bos-semi.com → Route53 Resolver (AWS Private)
    └─ 그 외 모든 도메인 → 기존 DNS (Public IP 정상 반환)
```

---

## 4. S3 Cross-Region Replication 흐름

```
S3 (서울, bos-ai-documents-seoul-v3)
    │
    │  ① 새 객체 업로드 감지
    │
    │  ② Replication Rule 확인
    │     - 소스: bos-ai-documents-seoul-v3
    │     - 대상: bos-ai-documents-us (버지니아)
    │     - 필터: 전체 객체
    │
    │  ③ IAM Role (S3 Replication Role) 사용
    │     - 소스 버킷 읽기 권한
    │     - 대상 버킷 쓰기 권한
    │     - KMS 복호화/암호화 권한
    │
    │  ④ 객체 복제 시작
    │     - 서울 KMS 키로 복호화
    │     - 버지니아 KMS 키로 재암호화
    │     - 메타데이터 포함 복제
    │
    ▼
S3 (버지니아, bos-ai-documents-us)
    │
    │  ⑤ 복제 완료
    │     - ReplicationStatus: COMPLETED
    │
    │  ⑥ Bedrock KB 인제스트 트리거
    │     (수동 또는 자동)
    │
    ▼
Bedrock KB → OpenSearch (벡터 저장)
```

### 4.1 복제 상태 확인

```bash
# 복제 상태 확인
aws s3api head-object \
  --bucket bos-ai-documents-seoul-v3 \
  --key documents/soc/spec/example.pdf \
  --query 'ReplicationStatus'

# 결과:
# PENDING  → 복제 대기 중
# COMPLETED → 복제 완료 ✓
# FAILED   → 복제 실패 (권한 확인 필요)
```

---

## 참고 문서

- [문서 업로드 가이드](rag-upload-guide.md)
- [DNS 조건부 포워딩 가이드](dns-conditional-forwarding-guide.md)
- [운영 런북](OPERATIONAL_RUNBOOK.md)

---

> **작성일**: 2026-03-10  
> **상위 문서**: [BOS-AI Private RAG System Overview](../BOS-AI-Private-RAG-System-Overview.md)
