# 현재 VPC 설정 문서

## 문서 정보

- **작성일**: 2026-02-20
- **작성자**: Kiro AI
- **목적**: BOS-AI VPC 통합 마이그레이션 전 현재 상태 기록
- **관련 스펙**: `.kiro/specs/bos-ai-vpc-consolidation/`

## 개요

이 문서는 BOS-AI VPC 통합 마이그레이션 프로젝트의 일환으로 현재 VPC 설정을 문서화합니다. 마이그레이션 전 상태를 정확히 기록하여 변경 사항 추적 및 롤백 계획 수립에 활용합니다.

## 1. 서울 PoC VPC (vpc-066c464f9c750ee9e)

### 1.1 기본 정보

| 항목 | 값 |
|------|-----|
| VPC ID | vpc-066c464f9c750ee9e |
| VPC 이름 | (현재 이름 미정 - 마이그레이션 후: vpc-bos-ai-seoul-prod-01) |
| CIDR 블록 | 10.200.0.0/16 |
| 리전 | ap-northeast-2 (서울) |
| DNS 호스트네임 | 활성화 |
| DNS 해석 | 활성화 |
| 용도 | 로깅 인프라, VPN 연결 (온프레미스 접점) |

### 1.2 서브넷 구성

#### Private 서브넷

| 서브넷 이름 | CIDR | 가용 영역 | 용도 |
|------------|------|----------|------|
| (미정 - 마이그레이션 후: sn-private-bos-ai-seoul-prod-01a) | 10.200.1.0/24 | ap-northeast-2a | EC2 로그 수집기, Lambda, OpenSearch |
| (미정 - 마이그레이션 후: sn-private-bos-ai-seoul-prod-01c) | 10.200.2.0/24 | ap-northeast-2c | Lambda, OpenSearch (Multi-AZ) |

#### Public 서브넷

| 서브넷 이름 | CIDR | 가용 영역 | 용도 |
|------------|------|----------|------|
| (미정 - 마이그레이션 후: sn-public-bos-ai-seoul-prod-01a) | 10.200.10.0/24 | ap-northeast-2a | NAT Gateway, Bastion |
| (미정 - 마이그레이션 후: sn-public-bos-ai-seoul-prod-01c) | 10.200.20.0/24 | ap-northeast-2c | 예비 |

**총 서브넷 수**: 4개 (Private 2개, Public 2개)

### 1.3 라우팅 테이블

#### Private Route Table

| 대상 (Destination) | 타겟 (Target) | 용도 |
|-------------------|--------------|------|
| 10.200.0.0/16 | local | VPC 내부 통신 |
| 0.0.0.0/0 | nat-gateway | 인터넷 아웃바운드 |
| 192.128.1.0/24 | vgw-0d54d0b0af6515dec | 온프레미스 에이전트 |
| 192.128.10.0/24 | vgw-0d54d0b0af6515dec | 온프레미스 FTP |
| 192.128.20.0/24 | vgw-0d54d0b0af6515dec | 온프레미스 OpenSearch |

**연결된 서브넷**: Private 서브넷 2개

#### Public Route Table

| 대상 (Destination) | 타겟 (Target) | 용도 |
|-------------------|--------------|------|
| 10.200.0.0/16 | local | VPC 내부 통신 |
| 0.0.0.0/0 | igw-xxxxx | 인터넷 게이트웨이 |

**연결된 서브넷**: Public 서브넷 2개

### 1.4 VPN Gateway

| 항목 | 값 |
|------|-----|
| VPN Gateway ID | vgw-0d54d0b0af6515dec |
| 상태 | attached |
| 연결된 VPC | vpc-066c464f9c750ee9e |
| Amazon Side ASN | 64512 (기본값) |
| 용도 | 온프레미스 네트워크 연결 |

**VPN 연결 대상**:
- 온프레미스 에이전트: 192.128.1.0/24
- 온프레미스 FTP: 192.128.10.0/24
- 온프레미스 OpenSearch: 192.128.20.0/24

### 1.5 NAT Gateway

| NAT Gateway | 가용 영역 | Elastic IP | 서브넷 |
|-------------|----------|------------|--------|
| nat-xxxxx | ap-northeast-2a | eipalloc-xxxxx | Public 서브넷 (10.200.10.0/24) |

**참고**: 현재 1개의 NAT Gateway만 사용 중 (비용 최적화)

### 1.6 Internet Gateway

| 항목 | 값 |
|------|-----|
| Internet Gateway ID | igw-xxxxx |
| 상태 | attached |
| 연결된 VPC | vpc-066c464f9c750ee9e |

### 1.7 Route53 Resolver 엔드포인트

#### Inbound Endpoint

| 항목 | 값 |
|------|-----|
| Resolver Endpoint ID | rslvr-in-79867dcffe644a378 |
| 이름 | ibe-onprem-itdev-int-poc-01 |
| 용도 | 온프레미스에서 AWS 리소스 도메인 해석 |
| IP 주소 | 10.200.1.x, 10.200.2.x (프라이빗 서브넷) |
| Security Group | sg-route53-resolver-xxxxx |

#### Outbound Endpoint

| 항목 | 값 |
|------|-----|
| Resolver Endpoint ID | rslvr-out-528276266e13403aa |
| 이름 | obe-onprem-itdev-int-poc-01 |
| 용도 | AWS에서 온프레미스 도메인 해석 |
| IP 주소 | 10.200.1.x, 10.200.2.x (프라이빗 서브넷) |
| Security Group | sg-route53-resolver-xxxxx |

### 1.8 기존 리소스

#### EC2 인스턴스

| 인스턴스 이름 | 인스턴스 타입 | 서브넷 | 용도 |
|--------------|--------------|--------|------|
| ec2-logclt-itdev-int-poc-01 | (미정) | Private 서브넷 | 로그 수집기 |
| (Grafana 서버) | (미정) | Private 서브넷 | 모니터링 대시보드 |
| (EKS 노드 등) | (미정) | Private 서브넷 | 기타 워크로드 |

**총 EC2 인스턴스**: 6개

#### OpenSearch Managed

| 항목 | 값 |
|------|-----|
| 도메인 이름 | open-mon-itdev-int-poc-001 |
| 엔진 버전 | (미정) |
| 인스턴스 타입 | (미정) |
| 서브넷 | Private 서브넷 |
| Security Group | sg-os-open-mon-int-poc-01 |

#### VPC 엔드포인트

| 엔드포인트 이름 | 서비스 | 타입 | 용도 |
|----------------|--------|------|------|
| vpce-firehose-itdev-int-poc-01 | com.amazonaws.ap-northeast-2.kinesis-firehose | Interface | 로깅 파이프라인 |

### 1.9 Security Groups

| Security Group 이름 | 용도 | Inbound 규칙 | Outbound 규칙 |
|--------------------|------|-------------|--------------|
| sg-logclt-itdev-int-poc-01 | 로그 수집기 | SSH, Syslog from 온프레미스 | HTTPS to Firehose, OpenSearch |
| sg-gra-itdev-int-poc-01 | Grafana | Port 3000, SSH from 온프레미스 | Port 9200 to OpenSearch |
| sg-os-open-mon-int-poc-01 | OpenSearch Managed | Port 443/9200 from 로그 수집기, Grafana, 온프레미스 | All to 0.0.0.0/0 |
| sg-route53-resolver-xxxxx | Route53 Resolver | Port 53 from VPC CIDR, 온프레미스 | Port 53 to all |

**참고**: Security Group 규칙 상세 내용은 `docs/current-security-groups.md` 참조

---

## 2. 서울 BOS-AI-RAG VPC (vpc-0f759f00e5df658d1)

### 2.1 기본 정보

| 항목 | 값 |
|------|-----|
| VPC ID | vpc-0f759f00e5df658d1 |
| VPC 이름 | (현재 이름 미정) |
| CIDR 블록 | 10.10.0.0/16 |
| 리전 | ap-northeast-2 (서울) |
| DNS 호스트네임 | 활성화 |
| DNS 해석 | 활성화 |
| 용도 | AI 워크로드 (격리된 환경, 마이그레이션 대상) |
| 상태 | **격리됨 (VPN 연결 없음)** |

### 2.2 서브넷 구성

#### Private 서브넷

| 서브넷 이름 | CIDR | 가용 영역 | 용도 |
|------------|------|----------|------|
| (미정) | 10.10.1.0/24 | ap-northeast-2a | Lambda, OpenSearch (계획) |
| (미정) | 10.10.2.0/24 | ap-northeast-2c | Lambda, OpenSearch (계획) |

**총 서브넷 수**: 2개 (Private only, Public 서브넷 없음)

**참고**: 이 VPC는 프라이빗 서브넷만 가지고 있으며, 인터넷 게이트웨이가 없습니다.

### 2.3 라우팅 테이블

#### Private Route Table

| 대상 (Destination) | 타겟 (Target) | 용도 |
|-------------------|--------------|------|
| 10.10.0.0/16 | local | VPC 내부 통신 |
| 10.20.0.0/16 | pcx-xxxxx | 버지니아 VPC 피어링 (기존) |

**연결된 서브넷**: Private 서브넷 2개

**참고**: 
- NAT Gateway 없음 (외부 인터넷 접근 불가)
- VPN Gateway 연결 없음 (온프레미스 접근 불가)

### 2.4 VPN Gateway

| 항목 | 값 |
|------|-----|
| VPN Gateway ID | vgw-0461cd4d6a4463f67 |
| 상태 | **detached (사용 안 함)** |
| 연결된 VPC | 없음 |
| 용도 | 미사용 (마이그레이션 후 삭제 예정) |

**참고**: 이 VPN Gateway는 생성되었으나 VPC에 연결되지 않았으며, 온프레미스 연결이 없습니다.

### 2.5 VPC Peering (기존)

| 항목 | 값 |
|------|-----|
| Peering Connection ID | pcx-xxxxx |
| Requester VPC | vpc-0f759f00e5df658d1 (서울 BOS-AI-RAG) |
| Accepter VPC | vpc-xxxxxxxx (버지니아 백엔드 VPC) |
| Accepter VPC CIDR | 10.20.0.0/16 |
| 상태 | active |
| DNS Resolution | 활성화 (양방향) |

**참고**: 이 피어링 연결은 마이그레이션 후 삭제되고, 새로운 피어링 연결(서울 통합 VPC ↔ 버지니아 VPC)로 대체됩니다.

### 2.6 리소스 현황

#### OpenSearch Serverless

| 항목 | 값 |
|------|-----|
| 컬렉션 이름 | (미배포) |
| 상태 | **계획만 존재, 실제 배포 안 됨** |

#### Lambda 함수

| 항목 | 값 |
|------|-----|
| 함수 이름 | (미배포) |
| 상태 | **계획만 존재, 실제 배포 안 됨** |

**참고**: 이 VPC에는 실제 배포된 리소스가 없으며, 계획만 존재합니다. 마이그레이션 시 서울 통합 VPC에 새로 배포됩니다.

---

## 3. 버지니아 백엔드 VPC (10.20.0.0/16)

### 3.1 기본 정보

| 항목 | 값 |
|------|-----|
| VPC ID | vpc-xxxxxxxx (미확인) |
| CIDR 블록 | 10.20.0.0/16 |
| 리전 | us-east-1 (버지니아) |
| 용도 | 백엔드 레이어 (S3 문서 저장소) |

**참고**: 이 VPC는 마이그레이션 범위에 포함되지 않으며, 기존 상태를 유지합니다.

### 3.2 VPC Peering

현재 서울 BOS-AI-RAG VPC와 피어링 연결되어 있으며, 마이그레이션 후 서울 통합 VPC와 새로운 피어링 연결이 생성됩니다.

---

## 4. 네트워크 다이어그램

### 4.1 현재 상태 (As-Is)

```
온프레미스 (192.128.x.x)
    ↓ VPN (vgw-0d54d0b0af6515dec)
서울 PoC VPC (10.200.0.0/16)
    - 로깅 인프라 (EC2, OpenSearch Managed, Grafana)
    - Route53 Resolver (Inbound/Outbound)
    - NAT Gateway (1개)

서울 BOS-AI-RAG VPC (10.10.0.0/16) [격리됨]
    - VPN 연결 없음
    - 배포된 리소스 없음
    ↓ VPC Peering (pcx-xxxxx)
버지니아 백엔드 VPC (10.20.0.0/16)
    - S3 문서 저장소
```

### 4.2 목표 상태 (To-Be)

```
온프레미스 (192.128.x.x)
    ↓ VPN (vgw-0d54d0b0af6515dec)
서울 통합 VPC (10.200.0.0/16)
    - 로깅 인프라 (기존 유지)
    - AI 워크로드 (OpenSearch Serverless, Lambda, Bedrock)
    - Route53 Resolver (기존 유지)
    - NAT Gateway (1개)
    ↓ VPC Peering (신규 생성)
버지니아 백엔드 VPC (10.20.0.0/16)
    - S3 문서 저장소 (기존 유지)
```

---

## 5. CIDR 블록 요약

| VPC | CIDR 블록 | 서브넷 수 | 사용 가능 IP | 용도 |
|-----|----------|----------|-------------|------|
| 서울 PoC VPC | 10.200.0.0/16 | 4개 | 65,536 | 로깅 인프라, VPN 연결 |
| 서울 BOS-AI-RAG VPC | 10.10.0.0/16 | 2개 | 65,536 | **마이그레이션 대상 (삭제 예정)** |
| 버지니아 백엔드 VPC | 10.20.0.0/16 | (미확인) | 65,536 | 백엔드 레이어 |

**CIDR 충돌 확인**:
- ✅ 10.200.0.0/16 vs 10.10.0.0/16: 충돌 없음
- ✅ 10.200.0.0/16 vs 10.20.0.0/16: 충돌 없음
- ✅ 10.10.0.0/16 vs 10.20.0.0/16: 충돌 없음

---

## 6. 마이그레이션 영향 분석

### 6.1 변경 사항

#### 서울 PoC VPC (vpc-066c464f9c750ee9e)
- **네이밍 변경**: 모든 리소스 이름을 새로운 네이밍 규칙에 맞게 변경
- **AI 워크로드 추가**: OpenSearch Serverless, Lambda, Bedrock KB 배포
- **VPC 피어링 추가**: 버지니아 VPC와 새로운 피어링 연결 생성
- **VPC 엔드포인트 추가**: Bedrock, S3, Secrets Manager 엔드포인트 생성
- **Security Group 추가**: AI 워크로드용 보안 그룹 생성

#### 서울 BOS-AI-RAG VPC (vpc-0f759f00e5df658d1)
- **완전 삭제**: 마이그레이션 완료 후 VPC 전체 삭제
- **VPN Gateway 삭제**: vgw-0461cd4d6a4463f67 삭제
- **VPC Peering 삭제**: 기존 피어링 연결 삭제

### 6.2 유지 사항

#### 서울 PoC VPC
- ✅ VPC CIDR 블록 (10.200.0.0/16) 유지
- ✅ 서브넷 CIDR 블록 유지
- ✅ VPN Gateway (vgw-0d54d0b0af6515dec) 유지
- ✅ 기존 로깅 인프라 (EC2, OpenSearch Managed, Grafana) 유지
- ✅ Route53 Resolver 엔드포인트 유지
- ✅ NAT Gateway 유지

#### 버지니아 백엔드 VPC
- ✅ 모든 리소스 변경 없음

---

## 7. 검증 체크리스트

### 7.1 문서화 완료 항목

- [x] 서울 PoC VPC 기본 정보
- [x] 서울 PoC VPC 서브넷 구성
- [x] 서울 PoC VPC 라우팅 테이블
- [x] 서울 PoC VPC VPN Gateway
- [x] 서울 PoC VPC NAT Gateway
- [x] 서울 PoC VPC Internet Gateway
- [x] 서울 PoC VPC Route53 Resolver
- [x] 서울 PoC VPC 기존 리소스 (EC2, OpenSearch)
- [x] 서울 BOS-AI-RAG VPC 기본 정보
- [x] 서울 BOS-AI-RAG VPC 서브넷 구성
- [x] 서울 BOS-AI-RAG VPC 라우팅 테이블
- [x] 서울 BOS-AI-RAG VPC VPN Gateway (미사용)
- [x] 서울 BOS-AI-RAG VPC VPC Peering
- [x] 버지니아 백엔드 VPC 기본 정보
- [x] CIDR 블록 충돌 확인
- [x] 네트워크 다이어그램 (As-Is, To-Be)

### 7.2 추가 문서화 필요 항목

- [x] Security Group 규칙 상세 (작업 1.3 완료 - `docs/current-security-groups.md` 참조)
- [ ] IAM Role 및 정책 상세 (작업 1.4에서 수행)
- [ ] 실제 AWS 리소스 ID 확인 (AWS CLI 또는 Console에서 확인)

---

## 8. 참고 자료

### 8.1 관련 문서

- 요구사항 문서: `.kiro/specs/bos-ai-vpc-consolidation/requirements.md`
- 설계 문서: `.kiro/specs/bos-ai-vpc-consolidation/design.md`
- 작업 목록: `.kiro/specs/bos-ai-vpc-consolidation/tasks.md`

### 8.2 AWS CLI 명령어

#### VPC 정보 확인
```bash
# 서울 PoC VPC 확인
aws ec2 describe-vpcs --vpc-ids vpc-066c464f9c750ee9e --region ap-northeast-2

# 서울 BOS-AI-RAG VPC 확인
aws ec2 describe-vpcs --vpc-ids vpc-0f759f00e5df658d1 --region ap-northeast-2
```

#### 서브넷 정보 확인
```bash
# 서울 PoC VPC 서브넷 확인
aws ec2 describe-subnets --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" --region ap-northeast-2

# 서울 BOS-AI-RAG VPC 서브넷 확인
aws ec2 describe-subnets --filters "Name=vpc-id,Values=vpc-0f759f00e5df658d1" --region ap-northeast-2
```

#### 라우팅 테이블 확인
```bash
# 서울 PoC VPC 라우팅 테이블 확인
aws ec2 describe-route-tables --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" --region ap-northeast-2

# 서울 BOS-AI-RAG VPC 라우팅 테이블 확인
aws ec2 describe-route-tables --filters "Name=vpc-id,Values=vpc-0f759f00e5df658d1" --region ap-northeast-2
```

#### VPN Gateway 확인
```bash
# VPN Gateway 확인
aws ec2 describe-vpn-gateways --vpn-gateway-ids vgw-0d54d0b0af6515dec vgw-0461cd4d6a4463f67 --region ap-northeast-2
```

#### VPC Peering 확인
```bash
# VPC Peering 연결 확인
aws ec2 describe-vpc-peering-connections --filters "Name=requester-vpc-info.vpc-id,Values=vpc-0f759f00e5df658d1" --region ap-northeast-2
```

---

## 9. 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|----------|--------|
| 2026-02-20 | 1.0 | 초기 문서 작성 | Kiro AI |

---

**문서 끝**
