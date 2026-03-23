# AWS 리소스 감사 보고서
생성일: 2026-03-13

## 요약

| 구분 | 수량 | 예상 월 비용 |
|------|------|-------------|
| Terraform 관리 리소스 | ~20개 | 코드 기반 |
| 콘솔/수동 생성 리소스 (미관리) | ~25개+ | 비용 누수 |
| **총 예상 비용 누수** | | **$2,500~3,000/월** |

---

## 1. 콘솔에서 수동 생성된 리소스 (Terraform 코드에 없음) - 비용 누수

### [심각] ACM Private CA - 예상 ~$400/월
- arn:aws:acm-pca:ap-northeast-2:533335672315:certificate-authority/7a215b99-...
- 상태: ACTIVE, ROOT
- Private CA는 월 $400 고정 비용
- 판단: POC 태그. 사용 여부 즉시 확인 필요

### [심각] OpenSearch Serverless (Bedrock Quick Create) - 예상 ~$1,400/월
- bedrock-knowledge-base-hk95ww (essf488s9haohijpnika) - ACTIVE
  - 연동 KB: kb-aspice-itdev-int-poc-02 (LLV8M0K1E5) - ASPICE 문서용
  - 벡터 스토어: OpenSearch Serverless
  - **최근 30일 SearchRequestRate: 0.0 (사용 없음)**
- bedrock-knowledge-base-gdablj (nb5y4sbia3jx0b20kfo2) - ACTIVE
  - 연동 KB: bedrock-test-itdev-int-poc-01 (81LRBCC2FC) - 테스트용
  - 벡터 스토어: Aurora PostgreSQL (아래 항목)
  - **최근 30일 SearchRequestRate: 0.0 (사용 없음)**
- **두 컬렉션 모두 최근 30일간 검색 요청 0건 = 완전 미사용**
- 판단: Bedrock Quick Create로 콘솔에서 자동 생성. 즉시 삭제 권장

참고: Terraform 코드의 bos-ai-vectors-prod (slgigf6wndoh9z6du8z8)는
2/27 주간에 1건의 검색 요청 있음 = 실제 BOS-AI RAG 시스템용

### [심각] OpenSearch Managed (비 Serverless) - 예상 ~$300/월
- open-mon-itdev-int-poc-001 (OpenSearch 2.19)
- 인스턴스: r7g.large.search x 2대
- Terraform 코드에 없음. 콘솔에서 수동 생성
- 판단: POC 모니터링용. r7g.large x 2는 비용이 큼

### [심각] EKS 클러스터 - 예상 ~$200+/월
- extravagant-alternative-ladybug (ACTIVE, 2025-09-17 생성)
- EC2 노드 2대: c6g.large x 2 (running)
- EBS 볼륨 2개 포함
- Terraform 코드에 EKS 관련 리소스 전혀 없음
- 판단: BOS-AI 프로젝트와 무관. 삭제 검토 필요

### [심각] Aurora PostgreSQL Serverless 2개 - 예상 ~$150+/월
- knowledgebasequickcreateaurora-49d-auroradbcluster-seqmhhsnwj2y
  - 연동: bedrock-test-itdev-int-poc-01 (81LRBCC2FC)의 벡터 스토어
  - **최근 7일 DatabaseConnections Maximum: 0.0 (접속 없음)**
- knowledgebasequickcreateaurora-4a4-auroradbcluster-ducq4ylhg64e
  - **최근 7일 DatabaseConnections Maximum: 0.0 (접속 없음)**
- 두 클러스터 모두 Bedrock Quick Create로 콘솔에서 자동 생성
- **DB 접속이 전혀 없음 = 완전 미사용. 즉시 삭제 권장**

### [높음] Route53 Resolver Endpoints (POC) - ~$180/월
- rslvr-in-79867dcffe644a378 (ibe-onprem-itdev-int-poc-01, INBOUND, 2 IP)
- rslvr-out-528276266e13403aa (obe-onprem-itdev-int-poc-01, OUTBOUND, 2 IP)
- ENI 4개 x $0.125/hr = ~$180/월
- Terraform 코드에 없는 POC용 Resolver

### [높음] EC2 인스턴스 (비 EKS)

| 인스턴스 | 타입 | 상태 | 이름 |
|----------|------|------|------|
| i-08f5a2c1c824e655b | t3.micro | stopped | ec2test-open-mon-itdev-int-poc-01 |
| i-0ca869f51d9668105 | t3.small | running | ec2-logclt-itdev-int-poc-01 |
| i-00f27803ecd6f5895 | t3.medium | running | ec2-gra-itdev-int-poc-01 |
| i-0080053aa5c999016 | c6g.2xlarge | stopped | arm-test-jeong |

- stopped 인스턴스도 EBS 비용 발생
- 예상: ~$50+/월

### [높음] Elastic IP 미사용 2개 - $7.2/월
- eipalloc-0e04ddd3c0beb1dcd (3.34.151.65) - EIP-x86-m6a2x-01 - 미연결
- eipalloc-05a9321a4ef897554 (43.200.28.204) - EIP-arm-g5gmetal-01 - 미연결

### [중간] VPN Connection (POC) - ~$36/월
- vpn-0acd5eff60174538a (vpn-fgt-itdev-int-poc-001)
- Customer Gateway: cgw-00d18a496243b5184 (cgw-fortigate-itdev-int-poc-01)

### [중간] Kinesis Firehose 2개 - ~$30+/월
- fh-open-mon-itdev-int-poc-01
- fh-open-mon-itdev-int-poc-02

### [중간] us-east-1 VPC Endpoints 6개 - ~$43/월

| Endpoint | 타입 | 서비스 | 이름 |
|----------|------|--------|------|
| vpce-081afbb1df0f56705 | Interface | aoss | bos-ai-opensearch-endpoint-dev |
| vpce-0e60493db3e96fe50 | Interface | bedrock-agent-runtime | bos-ai-bedrock-agent-runtime-endpoint-dev |
| vpce-0fe70be9fc4fd10ea | Interface | bedrock-runtime | bos-ai-bedrock-runtime-endpoint-dev |
| vpce-0f017558595dedd41 | Interface | logs | bos-ai-logs-endpoint-dev |
| vpce-075ba17f3151048ba | Interface | secretsmanager | bos-ai-secretsmanager-endpoint-dev |
| vpce-0e3071e734b63f3d7 | Interface | bedrock-agent | (이름 없음) |

### [낮음] S3 버킷 (Terraform 외)
- ana-s3-bucket-533335672315
- aws-athena-query-results-ap-northeast-2-533335672315
- aws-cloudtrail-logs-533335672315-81a6ce1b
- bedrock-agentcore-runtime-533335672315-us-east-1-ndyb2vs8sh
- bos-eagle-n-demo
- bos-semi-artifacts
- bos-semi-demo-contents
- bos-semi-public
- bos-sw-release
- config-bucket-533335672315
- fluent-bit-intermediate-533335672315
- s3-aspice-itdev-int-poc-02
- s3-open-mon-itdev-int-poc-01
- s3-vectordb-itdev-int-poc-01

### [낮음] CloudWatch Log Groups (보존 무제한)

| Log Group | 크기 | 보존 |
|-----------|------|------|
| /aws/eks/extravagant-alternative-ladybug/cluster | 35.1 GB | 무제한 |
| /aws/kinesisfirehose/fh-open-mon-itdev-int-poc-01 | 57.2 MB | 무제한 |
| /aws/OpenSearchService/domains/open-mon-itdev-int-poc-001 | 0.2 MB | 무제한 |
| /aws/lambda/lambda-document-processor-seoul-prod | 0.2 MB | 무제한 |

---

## 2. Terraform 관리 리소스 (코드에 있음)

### Seoul (ap-northeast-2)
- VPC 2개: vpc-logging-seoul-prod, bos-ai-seoul-vpc-prod
- Transit Gateway: tgw-bos-ai-seoul-prod (Attachment 3개)
- VPN: tgw-vpn-bos-ai-prod
- NAT Gateway: vpc-logging-seoul-prod-nat-1 + EIP
- VPC Endpoints (prod): bedrock-agent-runtime, bedrock-runtime, logs, secretsmanager, S3 x2, execute-api, dynamodb, opensearch
- Route53 Resolver: resolver-outbound-private-rag-prod, resolver-inbound-private-rag-prod
- Lambda: lambda-document-processor-seoul-prod
- S3: bos-ai-terraform-state, bos-ai-terraform-state-logs, bos-ai-cloudtrail-logs, bos-ai-documents-seoul-v2
- DynamoDB: terraform-state-lock, rag-extraction-tasks-dev

### Virginia (us-east-1)
- VPC: bos-ai-us-vpc-prod (10.20.0.0/16)
- VPC Peering: pcx-0a44f0b90565313f7 (Seoul <-> Virginia)

---

## 3. 비용 누수 예상 요약 (우선순위순)

| 순위 | 리소스 | 예상 월 비용 | 조치 |
|------|--------|-------------|------|
| 1 | OpenSearch Serverless x2 (Bedrock KB) | ~$1,400 | 사용 확인 후 삭제 |
| 2 | ACM Private CA | ~$400 | 즉시 비활성화 검토 |
| 3 | OpenSearch Managed (r7g.large x2) | ~$300 | POC 완료 시 삭제 |
| 4 | EKS 클러스터 + 노드 | ~$200 | BOS-AI 무관, 삭제 |
| 5 | Route53 Resolver POC x2 | ~$180 | 사용 확인 |
| 6 | Aurora PostgreSQL x2 | ~$150 | Bedrock Quick Create 잔여물 |
| 7 | EC2 인스턴스 (4대) | ~$50 | running 2대 확인, stopped 삭제 |
| 8 | us-east-1 VPC Endpoints x6 | ~$43 | dev 환경 필요 여부 |
| 9 | VPN POC | ~$36 | 사용 확인 |
| 10 | Kinesis Firehose x2 | ~$30 | POC 완료 시 삭제 |
| 11 | Elastic IP 미사용 x2 | ~$7 | 즉시 릴리스 |
| **합계** | | **~$2,796/월** | |

---

## 4. 즉시 조치 권고

### 1순위: 확인 후 삭제 (월 ~$2,450 절감 가능)
- ACM Private CA 비활성화
- OpenSearch Serverless 컬렉션 2개 삭제 (+ Bedrock KB 2개)
- OpenSearch Managed 도메인 삭제
- EKS 클러스터 삭제
- Aurora PostgreSQL 2개 삭제

### 2순위: 정리 (월 ~$280 절감 가능)
- POC Route53 Resolver 2개 삭제
- 미사용 Elastic IP 2개 릴리스
- stopped EC2 인스턴스 종료 (EBS 삭제)
- POC VPN 삭제

### 3순위: 최적화
- CloudWatch Log Groups 보존 기간 설정 (특히 EKS 35GB)
- 미사용 S3 버킷 정리
- us-east-1 dev VPC Endpoints 필요 여부 확인
