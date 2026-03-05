# BOS-AI RAG Infrastructure

AWS 기반 AI RAG(Retrieval-Augmented Generation) 시스템의 인프라 코드 및 배포 자동화 프로젝트입니다.

## 📋 프로젝트 개요

BOS-AI RAG는 온프렘 환경과 AWS 클라우드를 연결하여 대규모 문서 처리 및 AI 기반 검색 시스템을 구축합니다.

**주요 특징**:
- 🌐 **하이브리드 네트워크**: 온프렘 ↔ AWS VPN 연결
- 🔄 **VPC 통합**: Transit Gateway를 통한 다중 VPC 연결
- 🤖 **AI 워크로드**: AWS Bedrock, OpenSearch Serverless
- 📊 **로깅 파이프라인**: 중앙화된 보안 로깅 인프라
- 🔐 **보안**: VPC 엔드포인트, 보안 그룹, IAM 정책

## 🏗️ 아키텍처

```
온프렘 (192.128.0.0/16)
    ↓ VPN (IPsec Tunnels)
Transit Gateway (tgw-0897383168475b532)
    ├─ 로깅 파이프라인 VPC (10.200.0.0/16)
    │   ├─ Route53 Resolver Inbound Endpoint
    │   ├─ EC2 로그 수집기
    │   └─ 모니터링 (Grafana)
    │
    └─ BOS-AI 프론트엔드 VPC (10.10.0.0/16)
        ├─ Lambda (문서 처리)
        ├─ OpenSearch Serverless
        ├─ Bedrock Knowledge Base
        └─ VPC Peering
            ↓
            버지니아 백엔드 VPC (10.20.0.0/16)
            ├─ S3 (데이터 저장소)
            └─ VPC Endpoints
```

## 📁 프로젝트 구조

```
.
├── environments/              # 환경별 Terraform 설정
│   ├── network-layer/        # 네트워크 인프라 (VPC, TGW, VPN)
│   ├── ai-workload/          # AI 워크로드 (Lambda, Bedrock, OpenSearch)
│   └── monitoring/           # 모니터링 (CloudWatch, Grafana)
│
├── modules/                   # Terraform 모듈
│   ├── network/
│   │   ├── vpc/              # VPC 모듈
│   │   ├── transit-gateway/  # Transit Gateway 모듈
│   │   ├── peering/          # VPC Peering 모듈
│   │   ├── route53-resolver/ # Route53 Resolver 모듈
│   │   └── security-groups/  # Security Group 모듈
│   ├── ai-workload/
│   │   ├── bedrock/          # Bedrock Knowledge Base
│   │   ├── opensearch/       # OpenSearch Serverless
│   │   └── lambda/           # Lambda 함수
│   └── monitoring/
│       ├── cloudwatch/       # CloudWatch 설정
│       └── grafana/          # Grafana 대시보드
│
├── lambda/                    # Lambda 함수 코드
│   └── document-processor/   # 문서 처리 함수
│
├── docs/                      # 문서
│   ├── DEPLOYMENT_GUIDE.md   # 배포 가이드
│   ├── OPERATIONAL_RUNBOOK.md # 운영 가이드
│   ├── vpn-migration-and-testing-guide.md
│   ├── tgw-migration-guide.md
│   └── CURRENT_STATUS.md     # 현재 상태
│
├── Report/                    # 배포 보고서 및 테스트 결과
│   ├── 20260303_FORTIGATE_TGW_VPN_SETUP_GUIDE.md
│   ├── 20260303_VPN_CONNECTIVITY_TEST_RESULTS.md
│   ├── 20260303_ROUTE53_RESOLVER_ENDPOINT_TEST.md
│   └── 20260303_DNS_LOOKUP_TEST_RESULTS.md
│
├── scripts/                   # 배포 및 관리 스크립트
│   └── deploy-route53.ps1    # Route53 배포 스크립트
│
├── .kiro/                     # Kiro 스펙 및 설정
│   └── specs/
│       ├── aws-bedrock-rag-deployment/
│       ├── bos-ai-vpc-consolidation/
│       └── vpc-migration-seoul-unification/
│
└── README.md                  # 이 파일
```

## 🎓 팀원 교육

새로운 팀원이 시스템을 이해하고 배포할 수 있도록 다음 순서로 학습하세요:

**시작점**: [Report/README_TEAM_EDUCATION.md](Report/README_TEAM_EDUCATION.md) - 팀원 교육 자료 가이드

**학습 순서**:
1. [Report/TEAM_TRAINING_GUIDE.md](Report/TEAM_TRAINING_GUIDE.md) - 팀원 교육 가이드 (30분)
2. [Report/ARCHITECTURE_DETAILS.md](Report/ARCHITECTURE_DETAILS.md) - 아키텍처 상세 설명 (1시간)
3. [Report/DEPLOYMENT_PHASES.md](Report/DEPLOYMENT_PHASES.md) - 배포 3단계 상세 가이드 (1시간)
4. 실제 배포 및 테스트 (2-3시간)
5. [docs/OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md) - 운영 및 트러블슈팅 (필요시)

**예상 학습 시간**: 3-4시간 (이론 2시간 + 실습 2-3시간)

### 사전 요구사항

- Terraform >= 1.0
- AWS CLI >= 2.0
- Python >= 3.9 (Lambda 함수용)
- PowerShell >= 7.0 (배포 스크립트용)

### 환경 설정

1. **AWS 자격증명 설정**
```bash
aws configure
```

2. **Terraform 변수 설정**
```bash
cd environments/network-layer
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars 파일 수정
```

3. **Terraform 초기화**
```bash
terraform init
```

### 배포

**배포 3단계 상세 가이드**: [Report/DEPLOYMENT_PHASES.md](Report/DEPLOYMENT_PHASES.md)

#### 1단계: 네트워크 인프라 배포
```bash
cd environments/network-layer
terraform plan
terraform apply
```
**구성**: VPC, Transit Gateway, VPC Peering, Route53 Resolver, VPC Endpoints

#### 2단계: AI 워크로드 배포
```bash
cd environments/app-layer/bedrock-rag
terraform plan
terraform apply
```
**구성**: Lambda, API Gateway, S3, OpenSearch, Bedrock Knowledge Base

#### 3단계: 모니터링 설정
```bash
cd environments/monitoring
terraform plan
terraform apply
```
**구성**: CloudWatch, CloudTrail, 알람

## 📊 현재 상태

**마지막 업데이트**: 2026-03-03

### ✅ 완료된 작업

- [x] VPC 통합 마이그레이션 (Phase 1-8)
- [x] Transit Gateway 구성
- [x] VPC 피어링 설정
- [x] Route53 Resolver 배포
- [x] OpenSearch Serverless 배포
- [x] Bedrock Knowledge Base 설정
- [x] Lambda 함수 배포
- [x] **온프렘 VPN 설정 완료** (FortiGate 60F v7.4.11)
- [x] **VPN 연결성 검증** (양쪽 터널 UP, 14 라우트 각각)
- [x] **DNS 검증** (Route53 Resolver 정상 작동)

### 🔄 진행 중인 작업

- [ ] 성능 최적화
- [ ] 비용 최적화
- [ ] 재해 복구 계획 수립

## 🔌 VPN 연결 정보

### 온프렘 ↔ AWS Transit Gateway

**VPN 연결**: vpn-0b2b65e9414092369

**IPsec 터널**:
- Tunnel 1: 3.38.69.188 (AWS) ↔ 211.170.236.130 (온프렘)
- Tunnel 2: 43.200.222.199 (AWS) ↔ 211.170.236.130 (온프렘)

**BGP 설정**:
- AWS ASN: 64512
- 온프렘 ASN: 65000
- 각 터널당 14개 라우트 전파

**상태**: ✅ 정상 (양쪽 터널 UP)

## 📝 주요 문서

| 문서 | 설명 |
|------|------|
| [Report/DEPLOYMENT_PHASES.md](Report/DEPLOYMENT_PHASES.md) | **배포 3단계 상세 가이드** - 각 단계별 구성 요소 및 배포 방법 |
| [Report/ARCHITECTURE_DETAILS.md](Report/ARCHITECTURE_DETAILS.md) | **아키텍처 상세 설명** - 시스템 목적, 데이터 흐름, 보안, 성능 |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | 전체 배포 가이드 |
| [docs/OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md) | 운영 및 트러블슈팅 |
| [docs/vpn-migration-and-testing-guide.md](docs/vpn-migration-and-testing-guide.md) | VPN 마이그레이션 및 테스트 |
| [docs/tgw-migration-guide.md](docs/tgw-migration-guide.md) | Transit Gateway 마이그레이션 |
| [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md) | 현재 상태 및 진행 상황 |

## 🧪 테스트

### VPN 연결성 테스트

```bash
# 온프렘에서 AWS 엔드포인트 핑 테스트
ping 10.200.1.178  # Route53 Resolver Inbound 1
ping 10.200.2.123  # Route53 Resolver Inbound 2
ping 10.200.1.159  # EC2 로그 수집기
```

### DNS 테스트

```bash
# Route53 Resolver를 통한 DNS 쿼리
nslookup example.com 10.200.1.178
dig @10.200.1.178 example.com
```

### 성능 테스트

```bash
# 지연시간 측정
time nslookup example.com 10.200.1.178
# 예상 결과: 21ms 응답 시간
```

## 🔐 보안

### VPC 엔드포인트

- **Bedrock Runtime**: 프론트엔드 VPC에서만 접근
- **Secrets Manager**: 프론트엔드 VPC에서만 접근
- **CloudWatch Logs**: 프론트엔드 VPC에서만 접근
- **S3**: 모든 VPC에서 접근

### Security Group 규칙

- 온프렘 (192.128.0.0/16)에서 모든 트래픽 허용
- VPC 간 피어링 트래픽 허용
- 아웃바운드: 모든 트래픽 허용

### IAM 정책

- Lambda: Bedrock, OpenSearch, S3 접근 권한
- EC2: CloudWatch Logs, Secrets Manager 접근 권한

## 📊 성능 지표

| 경로 | 지연시간 | 상태 |
|------|---------|------|
| 온프렘 → Route53 Resolver | 21ms | ✅ |
| 온프렘 → 로깅 VPC | 50-100ms | ✅ |
| 온프렘 → 프론트엔드 VPC | 50-100ms | ✅ |
| 프론트엔드 VPC → 버지니아 VPC | 100-150ms | ✅ |

## 🛠️ 트러블슈팅

### VPN 연결 문제

1. **VPN 터널 상태 확인**
```bash
aws ec2 describe-vpn-connections --vpn-connection-ids vpn-0b2b65e9414092369
```

2. **BGP 라우트 확인**
```bash
aws ec2 search-transit-gateway-routes --transit-gateway-route-table-id tgw-rtb-06ab3b805ab879efb
```

3. **온프렘 방화벽 로그 확인**
```bash
# FortiGate CLI
diagnose vpn ipsec status
get router bgp summary
```

### DNS 해석 문제

1. **Route53 Resolver 상태 확인**
```bash
aws route53resolver describe-resolver-endpoints
```

2. **DNS 쿼리 테스트**
```bash
dig @10.200.1.178 example.com +trace
```

자세한 내용은 [OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md)를 참고하세요.

## 📞 연락처

- **AWS 담당자**: [이름] ([이메일])
- **온프렘 네트워크 팀**: [이름] ([연락처])
- **긴급 연락처**: [이름] ([전화번호])

## 📄 라이선스

이 프로젝트는 내부 사용 목적으로만 제공됩니다.

## 🔄 버전 히스토리

| 버전 | 날짜 | 변경사항 |
|------|------|---------|
| 1.0 | 2026-03-03 | 초기 배포 완료, VPN 연결성 검증 완료 |
| 0.9 | 2026-02-26 | Transit Gateway 마이그레이션 완료 |
| 0.8 | 2026-02-20 | VPC 통합 마이그레이션 완료 |

---

**마지막 업데이트**: 2026-03-03  
**상태**: ✅ 프로덕션 준비 완료
