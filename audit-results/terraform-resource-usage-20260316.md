# Terraform 관리 리소스 사용 여부 분석 보고서
분석일: 2026-03-16

## 요약

| 구분 | 수량 | 상태 |
|------|------|------|
| 사용 중 (트래픽 있음) | 8개 | 유지 |
| 미사용 (트래픽 0) | 8개+ | 삭제/정리 검토 |
| **미사용 리소스 예상 절감** | | **~$72+/월** |

---

## 1. Seoul VPC Endpoints 트래픽 분석 (2026-02~03)

### Logging VPC (vpc-066c464f9c750ee9e) — vpc-endpoints.tf

| Endpoint ID | 서비스 | BytesProcessed | 판정 |
|-------------|--------|---------------|------|
| vpce-0824661c979a51be1 | bedrock-runtime | 0 | **미사용** |
| vpce-0fe1c967f088f06c7 | bedrock-agent-runtime | 0 | **미사용** |
| vpce-0ec5ee23ea57dfe96 | secretsmanager | 0 | **미사용** |
| vpce-0bf159bce53ad018f | logs | 0 | **미사용** |
| vpce-05857bc2c67999bb7 | S3 (Gateway) | N/A | Gateway는 무료 |
| vpce-05a50bee12aea987d | kinesis-firehose | ~3.7GB | 사용 중 (POC, Terraform 미관리) |

**분석**: Logging VPC의 Interface Endpoints 4개 모두 트래픽 0.
이 VPC는 원래 보안 로깅/모니터링 용도인데, Bedrock/Secretsmanager endpoint가 여기에 있을 이유가 없음.
Private RAG 시스템은 Frontend VPC에서 동작하므로, Logging VPC의 bedrock-runtime, bedrock-agent-runtime, secretsmanager, logs endpoint는 불필요.
**예상 절감: Interface 4개 x ~$7.2/월 = ~$29/월**

### Frontend VPC (vpc-0a118e1bf21d0c057) — vpc-endpoints-frontend.tf

| Endpoint ID | 서비스 | BytesProcessed | 판정 |
|-------------|--------|---------------|------|
| vpce-0e5f61dd7bd52882e | execute-api | 2월 ~10.5MB, 3월 ~258KB | **사용 중** |
| vpce-0947b538151ee50de | logs | 0 | 미사용 (Lambda 활성 시 필요) |
| vpce-073341b8f013a9d26 | secretsmanager | 0 | 미사용 (Lambda 활성 시 필요) |
| vpce-013aa002a16145cd0 | vpce-svc-07067649b697c5575 | 0 | **미사용** (Terraform 미관리) |
| vpce-08474f7814c698b6c | S3 (Gateway) | N/A | Gateway는 무료 |
| vpce-09627d3b36ff3dba0 | DynamoDB (Gateway) | N/A | Gateway는 무료 |

**분석**: execute-api만 실제 사용 중.
logs, secretsmanager는 Lambda 호출 시 필요하므로 유지 권장 (Lambda 3월 439건 호출).
vpce-svc PrivateLink는 Terraform 코드에 없는 수동 생성 리소스 → 삭제 검토.
**vpce-svc 삭제 시 절감: ~$7/월**

---

## 2. us-east-1 VPC Endpoints 트래픽 분석

### Backend VPC (vpc-0ed37ff82027c088f) — Terraform 미관리 (dev 태그)

| Endpoint ID | 서비스 | BytesProcessed | 판정 |
|-------------|--------|---------------|------|
| vpce-0e60493db3e96fe50 | bedrock-agent-runtime | 3월 ~640KB | **소량 사용** |
| vpce-0e3071e734b63f3d7 | bedrock-agent | 3월 ~20KB | **소량 사용** |
| vpce-0fe70be9fc4fd10ea | bedrock-runtime | 0 | **미사용** |
| vpce-081afbb1df0f56705 | aoss (OpenSearch) | 0 | **미사용** |
| vpce-0f017558595dedd41 | logs | 0 | **미사용** |
| vpce-075ba17f3151048ba | secretsmanager | 0 | **미사용** |
| vpce-02bc0177e44107c3f | S3 (Gateway) | N/A | Gateway는 무료 |

**분석**: bedrock-agent-runtime과 bedrock-agent만 소량 트래픽.
이 6개는 이전 감사에서 이미 "미관리 리소스"로 분류됨 (보고서 순위 8번, ~$43/월).

---

## 3. NAT Gateway

| 리소스 | 메트릭 | 2월 | 3월 | 판정 |
|--------|--------|-----|-----|------|
| nat-03dc6eb89ecb8f21c | ActiveConnectionCount | 5,158,381 | 2,280,943 | **사용 중** |
| nat-03dc6eb89ecb8f21c | BytesOutToDestination | ~2.5GB | ~776MB | **사용 중** |

**분석**: NAT Gateway 활발히 사용 중. 유지 필요. (~$32/월 고정 + 데이터 처리)

---

## 4. Transit Gateway

### Attachment 트래픽

| Attachment | 연결 대상 | BytesIn (2월) | BytesIn (3월) | 판정 |
|-----------|----------|--------------|--------------|------|
| tgw-attach-027263ebc6158c1d1 | Logging VPC | 0 | 0 | **미사용** |
| tgw-attach-066855ae90345791b | Frontend VPC | 0 | ~4.6MB | **사용 중** |
| tgw-attach-025c13761b6d6338d | VPN (prod) | 0 | ~47MB | **사용 중** |

### TGW 라우팅 테이블 분석

| 목적지 CIDR | 라우팅 대상 | 타입 | 상태 |
|-----------|-----------|------|------|
| 10.10.0.0/16 (Frontend VPC) | tgw-attach-066855ae90345791b | propagated | active |
| 10.20.0.0/16 (Virginia Backend) | tgw-attach-066855ae90345791b (Frontend VPC 경유) | static | active |
| 10.200.0.0/16 (Logging VPC) | tgw-attach-027263ebc6158c1d1 | propagated | active |
| 192.128.x.x/24 (OnPrem) | tgw-attach-025c13761b6d6338d (VPN) | propagated | active |

**분석**:
- Logging VPC로 가는 라우트는 **존재하지만 트래픽 0**
- 온프레미스 트래픽은 모두 VPN → Frontend VPC로 흐름
- Virginia Backend 접근도 Frontend VPC를 경유 (VPC Peering)
- Logging VPC는 내부 로깅/모니터링 용도일 뿐, 온프레미스에서 직접 접근 불필요

**결론**: Logging VPC TGW attachment는 라우팅 규칙상 존재하지만 실제 사용되지 않음.
**Logging VPC TGW attachment 삭제 가능: ~$36/월 절감**
(Logging VPC 자체는 NAT Gateway 때문에 유지 필요)

---

## 5. VPN (Prod)

| 리소스 | 메트릭 | 2월 | 3월 | 판정 |
|--------|--------|-----|-----|------|
| vpn-0b2b65e9414092369 | TunnelDataIn | ~750KB | ~70MB | **사용 중** |

유지 필요.

---

## 6. Lambda

| 함수 | Invocations (3월) | 최종 수정 | 판정 |
|------|-------------------|----------|------|
| lambda-document-processor-seoul-prod | 439건 | 2026-03-12 | **사용 중** |

유지 필요.

---

## 7. Route53 Resolver (Prod)

| Endpoint | 방향 | 쿼리 수 (3월) | 판정 |
|----------|------|-------------|------|
| rslvr-in-93384eeb51fc4c4db | INBOUND | 316건 | **사용 중** |
| rslvr-out-a23da4b7273e45628 | OUTBOUND | 1,117건 | **사용 중** |

유지 필요.

---

## 8. OpenSearch Serverless (Prod)

| 컬렉션 | SearchRequestRate (최근 45일) | 판정 |
|--------|---------------------------|------|
| bos-ai-vectors-prod (slgigf6wndoh9z6du8z8) | 0 | **거의 미사용** |

최소 2 OCU 상시 과금 = ~$700/월. RAG 핵심 컴포넌트이므로 삭제 불가.
시스템 본격 운영 전까지 비용 계속 발생.

---

## 9. DynamoDB

| 테이블 | ConsumedReadCapacityUnits (3월) | 판정 |
|--------|-------------------------------|------|
| rag-extraction-tasks-dev | 1 | 거의 미사용, 비용 미미 |

---

## 10. 비용 절감 가능 항목 요약

### 즉시 조치 가능 (Terraform 코드 수정 필요)

| 순위 | 리소스 | 위치 | 예상 절감 | 조치 |
|------|--------|------|----------|------|
| 1 | Logging VPC TGW Attachment | network-layer | ~$36/월 | TGW에서 분리 |
| 2 | Logging VPC Interface Endpoints x4 | vpc-endpoints.tf | ~$29/월 | 삭제 |
| 3 | Frontend VPC PrivateLink (vpce-svc) | 수동 생성 | ~$7/월 | 콘솔에서 삭제 |
| **소계** | | | **~$72/월** | |

### 검토 필요

| 리소스 | 상태 | 비용 | 비고 |
|--------|------|------|------|
| OpenSearch Serverless prod | 거의 미사용 | ~$700/월 | RAG 핵심, 삭제 불가 |
| us-east-1 VPC Endpoints x6 | 이전 감사에서 식별 | ~$43/월 | 보고서 순위 8번 |

---

## 11. 아키텍처 관찰 사항

### Logging VPC 역할 재검토 필요
- Interface Endpoints 4개 트래픽 0, TGW Attachment 트래픽 0
- NAT Gateway만 활발히 사용 중 (~$32/월)
- kinesis-firehose endpoint만 ~3.7GB 트래픽 (POC, Terraform 미관리)

### VPC Endpoint 중복 배치
- secretsmanager, logs: Logging VPC + Frontend VPC 양쪽에 존재 (Logging 쪽 미사용)
- bedrock-runtime, bedrock-agent-runtime: Logging VPC에만 존재 (미사용)
- Private RAG 아키텍처상 이 endpoints는 Frontend VPC에만 있으면 됨
