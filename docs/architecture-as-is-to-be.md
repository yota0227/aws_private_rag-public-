# Private RAG API 아키텍처 비교 문서 (As-Is / To-Be)

## 1. As-Is (현재 상태)

### 네트워크 토폴로지
| 구성 요소 | 위치 | 상태 |
|----------|------|------|
| Route53 Resolver Inbound | Logging VPC (10.200.0.0/16) | rslvr-in-79867dcffe644a378 (10.200.1.178, 10.200.2.123) |
| Route53 Resolver Outbound | Logging VPC (10.200.0.0/16) | rslvr-out-528276266e13403aa |
| VPC Endpoints (서울) | Logging VPC | Kinesis Firehose, S3, Secrets Manager, Bedrock Runtime |
| Lambda (document-processor) | US Backend VPC (10.20.0.0/16) | 버지니아 리전 |
| API Gateway | 없음 | - |
| Private Hosted Zone | 없음 | - |
| 사내 DNS 조건부 포워딩 | 없음 | - |
| S3 데이터 업로드 | bos-ai-documents-seoul (실제 버지니아) | 서울 리전 S3 버킷 없음 |

### DNS 해석 경로 (As-Is)
```
온프렘 → 사내 DNS → (Route53 Endpoint 직접 등록) → Logging VPC Resolver
```
⚠️ 이전에 무조건 등록으로 SaaS 서비스 장애 발생

## 2. To-Be (목표 상태)

### 네트워크 토폴로지
| 구성 요소 | 위치 | 상태 |
|----------|------|------|
| Route53 Resolver Inbound | Private RAG VPC (10.10.0.0/16) | 신규 생성 (10.10.1.x, 10.10.2.x) |
| Route53 Resolver Outbound | Private RAG VPC (10.10.0.0/16) | 신규 생성 |
| VPC Endpoints (Frontend) | Private RAG VPC | execute-api, CloudWatch Logs, Secrets Manager, S3 Gateway |
| Lambda (document-processor) | Private RAG VPC (10.10.0.0/16) | 서울 리전으로 이전 |
| Private API Gateway | 서울 리전 (Private REST API) | VPC Endpoint 통해서만 접근 |
| Private Hosted Zone | corp.bos-semi.com → Private RAG VPC | rag.corp.bos-semi.com Alias |
| 사내 DNS 조건부 포워딩 | *.corp.bos-semi.com만 | Route53 Resolver Inbound IP |
| S3 데이터 업로드 | bos-ai-documents-seoul-v2 (ap-northeast-2) | Cross-Region Replication → 버지니아 |

## 3. 변경 대상 리소스 목록

| 리소스 | 리소스 ID | 변경 유형 | 위치 | 영향 범위 |
|--------|----------|----------|------|----------|
| Route53 Resolver Inbound | rslvr-in-79867dcffe644a378 | 삭제 | Logging VPC | DNS 해석 경로 변경 |
| Route53 Resolver Outbound | rslvr-out-528276266e13403aa | 삭제 | Logging VPC | DNS 포워딩 경로 변경 |
| Route53 Resolver Inbound (신규) | TBD | 생성 | Private RAG VPC | 온프렘 DNS 해석 |
| Route53 Resolver Outbound (신규) | TBD | 생성 | Private RAG VPC | AWS→온프렘 DNS |
| Private API Gateway | TBD | 생성 | 서울 리전 | API 접근점 |
| VPC Endpoint (execute-api) | TBD | 생성 | Private RAG VPC | API Gateway 접근 |
| VPC Endpoint (CloudWatch Logs) | TBD | 생성 | Private RAG VPC | 로그 전송 |
| VPC Endpoint (Secrets Manager) | TBD | 생성 | Private RAG VPC | 시크릿 조회 |
| VPC Endpoint (S3 Gateway) | TBD | 생성 | Private RAG VPC | S3 접근 |
| Private Hosted Zone | TBD | 생성 | Private RAG VPC | DNS 도메인 |
| Lambda (document-processor) | 기존 | 이전 | 버지니아→서울 | RAG 처리 |
| S3 버킷 (서울) | TBD | 생성 | ap-northeast-2 | 문서 업로드 |
| S3 Cross-Region Replication | TBD | 생성 | 서울→버지니아 | 문서 복제 |

## 4. 트래픽 흐름 (To-Be)

### 데이터 플레인 (API 호출)
```
1. 온프렘 클라이언트 (192.128.0.0/16)
   ↓ VPN 터널 (IPsec)
2. Transit Gateway (tgw-0897383168475b532)
   ↓ TGW Route Table → Private RAG VPC Attachment
3. Private RAG VPC (10.10.0.0/16)
   ↓ VPC Endpoint (execute-api) ENI
4. Private API Gateway (REST API, Private)
   ↓ Lambda Proxy Integration
5. Lambda document-processor (서울, 10.10.1.x/10.10.2.x)
   ↓ VPC Peering (pcx-0a44f0b90565313f7)
6. US Backend VPC (10.20.0.0/16)
   ↓ VPC Endpoint (Bedrock Runtime, OpenSearch, S3)
7. Bedrock / OpenSearch Serverless / S3
```

### DNS 해석 흐름
```
1. 온프렘 클라이언트
   ↓ DNS 쿼리: rag.corp.bos-semi.com
2. 사내 DNS 서버
   ↓ 조건부 포워딩 (*.corp.bos-semi.com만)
3. Route53 Resolver Inbound (Private RAG VPC, 10.10.1.x/10.10.2.x)
   ↓ Private Hosted Zone 조회
4. Private Hosted Zone (corp.bos-semi.com)
   ↓ rag.corp.bos-semi.com → A (Alias) → execute-api VPC Endpoint DNS
5. VPC Endpoint Private IP 반환 (10.10.x.x)
   ↓
6. 클라이언트가 반환된 IP로 HTTPS 요청 전송
```

### 데이터 업로드 흐름
```
1. 온프렘 (aws s3 cp/sync)
   ↓ VPN → TGW
2. Private RAG VPC (10.10.0.0/16)
   ↓ S3 Gateway VPC Endpoint
3. 서울 S3 버킷 (bos-ai-documents-seoul-v2, ap-northeast-2)
   ↓ S3 Cross-Region Replication (15분 이내)
4. 버지니아 S3 버킷 (bos-ai-documents-us, us-east-1)
   ↓ Bedrock Knowledge Base Data Source
5. Bedrock Knowledge Base → 임베딩 → OpenSearch Serverless
```

## 5. 보안 격리 요약

| 보안 항목 | 상태 |
|----------|------|
| Internet Gateway | Private RAG VPC에 없음 (완전 Air-Gapped) |
| NAT Gateway | Private RAG VPC에 없음 |
| 0.0.0.0/0 라우팅 | Private RAG VPC에 없음 |
| API Gateway 타입 | Private (VPC Endpoint 전용) |
| execute-api Private DNS | 비활성화 (PHZ 충돌 방지) |
| DNS 포워딩 | 조건부 (*.corp.bos-semi.com만) |
| S3 접근 | VPC Endpoint 전용 (Bucket Policy) |
