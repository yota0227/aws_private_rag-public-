# Deep Dive: 네트워크 아키텍처

> 상위 문서: [BOS-AI Private RAG System Overview](../BOS-AI-Private-RAG-System-Overview.md)

---

## 1. 네트워크 전체 구성

BOS-AI Private RAG 시스템은 3개의 VPC와 온프레미스 네트워크로 구성됩니다.

```
┌──────────────────────────────────────────────────────────────────────┐
│                    온프레미스 (192.128.0.0/16)                        │
│                                                                      │
│   FortiGate 60F v7.4.11                                             │
│   ├─ IPsec Tunnel 1: 3.38.69.188                                   │
│   └─ IPsec Tunnel 2: 43.200.222.199                                │
│   BGP ASN: 65000                                                     │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ Site-to-Site VPN (vpn-0b2b65e9414092369)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│              Transit Gateway (tgw-0897383168475b532)                  │
│              AWS ASN: 64512                                          │
│                                                                      │
│   라우팅 테이블:                                                      │
│   ├─ 192.128.0.0/16 → VPN Attachment                                │
│   ├─ 10.10.0.0/16  → Private RAG VPC Attachment                    │
│   └─ 10.200.0.0/16 → Logging VPC Attachment                        │
└──────┬──────────────────────────────┬────────────────────────────────┘
       │                              │
       ▼                              ▼
┌──────────────────────┐  ┌──────────────────────────────────────────┐
│ Logging VPC          │  │ Private RAG VPC (vpc-0a118e1bf21d0c057)  │
│ (10.200.0.0/16)      │  │ (10.10.0.0/16)                          │
│                      │  │                                          │
│ ├─ 10.200.1.0/24    │  │ ├─ 10.10.1.0/24 (AZ-a)                  │
│ │  (AZ-a)           │  │ │  Lambda, VPC Endpoints, Resolver       │
│ ├─ 10.200.2.0/24    │  │ ├─ 10.10.2.0/24 (AZ-c)                  │
│ │  (AZ-c)           │  │ │  Lambda, VPC Endpoints, Resolver       │
│ │                    │  │ │                                        │
│ ├─ EC2 로그 수집기   │  │ ├─ API Gateway (Private)                 │
│ ├─ Grafana           │  │ ├─ Lambda (document-processor)           │
│ └─ OpenSearch Managed│  │ ├─ Route53 Resolver Inbound/Outbound    │
│                      │  │ └─ VPC Endpoints (6개)                   │
└──────────────────────┘  └──────────────────┬───────────────────────┘
                                             │ VPC Peering
                                             │ (pcx-0a44f0b90565313f7)
                                             ▼
                          ┌──────────────────────────────────────────┐
                          │ US Backend VPC (10.20.0.0/16)            │
                          │ us-east-1 (버지니아)                      │
                          │                                          │
                          │ ├─ 10.20.1.0/24 (AZ-a)                  │
                          │ ├─ 10.20.2.0/24 (AZ-b)                  │
                          │ ├─ 10.20.3.0/24 (AZ-c)                  │
                          │ │                                        │
                          │ ├─ S3 (bos-ai-documents-us)             │
                          │ └─ VPC Endpoints                         │
                          │    (Bedrock, OpenSearch, S3)             │
                          └──────────────────────────────────────────┘
```

---

## 2. VPC 상세

### 2.1 Private RAG VPC (Frontend)

| 항목 | 값 |
|------|-----|
| VPC ID | vpc-0a118e1bf21d0c057 |
| CIDR | 10.10.0.0/16 |
| 리전 | ap-northeast-2 (서울) |
| Internet Gateway | **없음** (완전 격리) |
| NAT Gateway | **없음** |
| 용도 | RAG API 진입점, 사용자 접점 |

**서브넷:**

| 서브넷 | CIDR | AZ | 용도 |
|--------|------|----|------|
| Private-1 | 10.10.1.0/24 | ap-northeast-2a | Lambda, VPC Endpoints, Resolver |
| Private-2 | 10.10.2.0/24 | ap-northeast-2c | Lambda, VPC Endpoints, Resolver |

**라우팅 테이블:**

| 대상 | 타겟 | 용도 |
|------|------|------|
| 10.10.0.0/16 | local | VPC 내부 통신 |
| 192.128.0.0/16 | Transit Gateway | 온프레미스 통신 |
| 10.20.0.0/16 | VPC Peering | 버지니아 Backend 통신 |

### 2.2 US Backend VPC

| 항목 | 값 |
|------|-----|
| VPC ID | vpc-0ed37ff82027c088f |
| CIDR | 10.20.0.0/16 |
| 리전 | us-east-1 (버지니아) |
| 용도 | AI 서비스 (Bedrock, OpenSearch, S3) |

### 2.3 Logging VPC

| 항목 | 값 |
|------|-----|
| VPC ID | vpc-066c464f9c750ee9e |
| CIDR | 10.200.0.0/16 |
| 리전 | ap-northeast-2 (서울) |
| 용도 | 로그 수집, 모니터링 (Grafana) |

---

## 3. Transit Gateway

Transit Gateway는 모든 VPC와 온프레미스를 연결하는 **중앙 라우터** 역할을 합니다.

| 항목 | 값 |
|------|-----|
| TGW ID | tgw-0897383168475b532 |
| AWS ASN | 64512 |
| VPN 연결 | vpn-0b2b65e9414092369 |

**왜 Transit Gateway를 사용하나?**

VPC가 3개이고 온프레미스까지 연결해야 하므로, 각각 직접 연결하면 관리가 복잡해집니다. Transit Gateway를 사용하면:
- 중앙에서 라우팅 정책을 관리
- 새 VPC 추가 시 TGW에만 연결하면 됨
- 온프레미스 ↔ 모든 VPC 통신이 자동으로 가능

---

## 4. VPN 연결

온프레미스와 AWS는 Site-to-Site VPN으로 연결됩니다.

| 항목 | 값 |
|------|-----|
| VPN ID | vpn-0b2b65e9414092369 |
| 온프레미스 장비 | FortiGate 60F v7.4.11 |
| 터널 수 | 2개 (고가용성) |
| 터널 1 IP | 3.38.69.188 |
| 터널 2 IP | 43.200.222.199 |
| 온프레미스 ASN | 65000 |
| 라우팅 | BGP 동적 라우팅 |

**고가용성:** 터널이 2개이므로 하나가 장애가 나도 자동으로 다른 터널로 전환됩니다.

---

## 5. VPC Peering

서울 Private RAG VPC와 버지니아 Backend VPC는 VPC Peering으로 직접 연결됩니다.

| 항목 | 값 |
|------|-----|
| Peering ID | pcx-0a44f0b90565313f7 |
| 요청자 | Private RAG VPC (서울, 10.10.0.0/16) |
| 수락자 | US Backend VPC (버지니아, 10.20.0.0/16) |
| 용도 | Lambda → Bedrock/OpenSearch/S3 통신 |

**왜 VPC Peering을 사용하나?**

Lambda가 서울에 있고 Bedrock/OpenSearch가 버지니아에 있으므로, 두 VPC를 직접 연결해야 합니다. VPC Peering은:
- 인터넷을 거치지 않음 (AWS 내부 네트워크)
- 낮은 지연시간
- 추가 비용 없음 (데이터 전송 비용만)

---

## 6. VPC Endpoints

Private RAG VPC에서 AWS 서비스에 접근할 때 인터넷 대신 **VPC Endpoint(Private Link)**를 사용합니다.

| 서비스 | Endpoint ID | 타입 | 용도 |
|--------|-------------|------|------|
| execute-api | vpce-0e5f61dd7bd52882e | Interface | API Gateway 접근 |
| S3 | vpce-08474f7814c698b6c | Gateway | S3 접근 |
| CloudWatch Logs | vpce-0f017558595dedd41 | Interface | 로그 전송 |
| Secrets Manager | vpce-075ba17f3151048ba | Interface | 시크릿 관리 |
| OpenSearch AOSS | vpce-013aa002a16145cd0 | Interface | OpenSearch 접근 |
| Bedrock Runtime | vpce-0fe70be9fc4fd10ea | Interface | Bedrock 접근 |

**왜 VPC Endpoint를 사용하나?**

Private RAG VPC에는 Internet Gateway가 없으므로, AWS 서비스에 접근하려면 VPC Endpoint가 필수입니다. 이를 통해:
- 인터넷 없이 AWS 서비스 사용
- 트래픽이 AWS 내부 네트워크에서만 이동
- 보안 강화

---

## 7. Route53 Resolver

온프레미스에서 AWS 내부 도메인(rag.corp.bos-semi.com)을 해석하기 위해 Route53 Resolver를 사용합니다.

| 항목 | 값 |
|------|-----|
| Inbound Endpoint ID | rslvr-in-93384eeb51fc4c4db |
| Inbound IP (AZ-a) | 10.10.1.34 |
| Inbound IP (AZ-c) | 10.10.2.144 |
| Private Hosted Zone | corp.bos-semi.com (Z04599582HCRH2UPCSS34) |
| A 레코드 | rag.corp.bos-semi.com → execute-api VPC Endpoint |

**동작 방식:**
1. 사내 DNS 서버가 `*.corp.bos-semi.com` 쿼리를 Resolver Inbound IP로 전달
2. Resolver가 Private Hosted Zone에서 레코드 조회
3. VPC Endpoint의 Private IP 반환

---

## 참고 문서

- [VPN 마이그레이션 가이드](vpn-migration-and-testing-guide.md)
- [TGW 마이그레이션 가이드](tgw-migration-guide.md)
- [현재 VPC 설정](current-vpc-configuration.md)
- [DNS 조건부 포워딩 가이드](dns-conditional-forwarding-guide.md)

---

> **작성일**: 2026-03-10  
> **상위 문서**: [BOS-AI Private RAG System Overview](../BOS-AI-Private-RAG-System-Overview.md)
