# BOS-AI VPC 통합 마이그레이션 - 현재 상태

**작성일**: 2026-02-26  
**상태**: 온프렘 VPN 설정 대기 중  
**진행률**: Phase 1-8 완료, Phase 9 준비 중

---

## 📊 진행 상황 요약

### ✅ 완료된 작업 (Phase 1-8)

#### Phase 1-2: 준비 및 네이밍 변경
- [x] VPC 리소스 태그 업데이트
- [x] Security Group 이름 및 태그 업데이트
- [x] Route53 Resolver 엔드포인트 이름 변경

#### Phase 3-7: 신규 리소스 배포
- [x] VPC 엔드포인트 구성 (Bedrock, Secrets Manager, CloudWatch Logs, S3)
- [x] OpenSearch Serverless 배포
- [x] Lambda 함수 배포
- [x] Bedrock Knowledge Base 설정
- [x] VPC 피어링 구성 (프론트엔드 ↔ 버지니아)

#### Phase 8: 통합 테스트
- [x] 전체 파이프라인 테스트 (Bedrock KB 쿼리 성공)

### 🔄 진행 중인 작업 (Phase 9)

#### Transit Gateway 마이그레이션
- [x] 프론트엔드 VPC CIDR 수정 (10.200.0.0/16 → 10.10.0.0/16)
- [x] 프론트엔드 VPC 재생성
- [x] VPC 피어링 재설정
- [x] Transit Gateway 생성
- [x] TGW VPC 어태치먼트 설정
- [x] TGW 라우팅 설정
- [x] TGW VPN 연결 생성
- [ ] **온프렘 방화벽 VPN 설정** ← 현재 단계
- [ ] Ping 테스트 수행
- [ ] 기존 VPN 정리

---

## 🏗️ 최종 아키텍처

```
온프렘 (192.128.0.0/16)
    ↓ VPN (vpn-0b2b65e9414092369) - 설정 대기 중
Transit Gateway (tgw-0897383168475b532)
    ├─ 로깅 파이프라인 VPC (10.200.0.0/16)
    │   ├─ Private Subnet 1: 10.200.1.0/24 (ap-northeast-2a)
    │   ├─ Private Subnet 2: 10.200.2.0/24 (ap-northeast-2c)
    │   ├─ Route53 Resolver Inbound Endpoint
    │   │   ├─ 10.200.1.178 (Subnet 1)
    │   │   └─ 10.200.2.123 (Subnet 2)
    │   ├─ EC2 로그 수집기 (10.200.1.159)
    │   ├─ EC2 모니터링 (10.200.1.90)
    │   └─ EC2 Grafana (10.200.1.139)
    │
    └─ BOS-AI 프론트엔드 VPC (10.10.0.0/16)
        ├─ Private Subnet 1: 10.10.1.0/24 (ap-northeast-2a)
        ├─ Private Subnet 2: 10.10.2.0/24 (ap-northeast-2c)
        ├─ Lambda (문서 처리)
        ├─ OpenSearch Serverless
        ├─ Bedrock Knowledge Base
        └─ VPC Peering (pcx-0a44f0b90565313f7)
            ↓
            버지니아 백엔드 VPC (10.20.0.0/16)
            ├─ Private Subnet 1: 10.20.1.0/24 (us-east-1a)
            ├─ Private Subnet 2: 10.20.2.0/24 (us-east-1b)
            ├─ Private Subnet 3: 10.20.3.0/24 (us-east-1c)
            ├─ S3 (데이터 저장소)
            └─ VPC Endpoints
```

---

## 📋 AWS 리소스 정보

### VPC 정보

| VPC 이름 | VPC ID | CIDR | 리전 | 상태 |
|---------|--------|------|------|------|
| vpc-logging-pipeline-seoul-prod | `vpc-066c464f9c750ee9e` | 10.200.0.0/16 | ap-northeast-2 | Active |
| bos-ai-seoul-vpc-prod | `vpc-0a118e1bf21d0c057` | 10.10.0.0/16 | ap-northeast-2 | Active |
| bos-ai-us-vpc-prod | `vpc-0ed37ff82027c088f` | 10.20.0.0/16 | us-east-1 | Active |

### Transit Gateway 정보

| 리소스 | ID | 상태 |
|--------|-----|------|
| Transit Gateway | `tgw-0897383168475b532` | Active |
| TGW 라우팅 테이블 | `tgw-rtb-06ab3b805ab879efb` | Available |
| 로깅 VPC 어태치먼트 | `tgw-attach-027263ebc6158c1d1` | Available |
| 프론트엔드 VPC 어태치먼트 | `tgw-attach-066855ae90345791b` | Available |

### VPN 정보

| VPN | ID | 상태 | 대상 |
|-----|-----|------|------|
| **새 TGW VPN** | `vpn-0b2b65e9414092369` | **Pending** | Transit Gateway |
| 기존 VGW VPN | `vpn-0acd5eff60174538a` | Available | VPN Gateway (삭제 예정) |

### VPC 피어링 정보

| 피어링 | ID | 상태 | 연결 |
|--------|-----|------|------|
| 프론트엔드 ↔ 백엔드 | `pcx-0a44f0b90565313f7` | Active | 10.10.0.0/16 ↔ 10.20.0.0/16 |

---

## 🔌 Ping 테스트 엔드포인트

### 로깅 파이프라인 VPC (10.200.0.0/16)

```
Route53 Resolver Inbound Endpoint:
  - 10.200.1.178 (Subnet 1, ap-northeast-2a)
  - 10.200.2.123 (Subnet 2, ap-northeast-2c)

EC2 인스턴스:
  - 10.200.1.159 (ec2-logclt-itdev-int-poc-01) - 로그 수집기
  - 10.200.1.90 (ec2test-open-mon-itdev-int-poc-01) - 모니터링
  - 10.200.1.139 (ec2-gra-itdev-int-poc-01) - Grafana
```

### BOS-AI 프론트엔드 VPC (10.10.0.0/16)

```
Private Subnets:
  - 10.10.1.0/24 (ap-northeast-2a)
  - 10.10.2.0/24 (ap-northeast-2c)
```

### 버지니아 백엔드 VPC (10.20.0.0/16)

```
Private Subnets:
  - 10.20.1.0/24 (us-east-1a)
  - 10.20.2.0/24 (us-east-1b)
  - 10.20.3.0/24 (us-east-1c)
```

---

## 📝 다음 단계

### 1단계: 온프렘 방화벽 VPN 설정 (내일)

**담당**: 온프렘 네트워크 팀

**작업**:
1. 기존 VPN 연결 종료
2. 새 TGW VPN 연결 설정
   - Tunnel 1: 3.38.69.188 (AWS) ↔ 211.170.236.130 (온프렘)
   - Tunnel 2: 43.200.222.199 (AWS) ↔ 211.170.236.130 (온프렘)
3. BGP 세션 설정 (ASN: AWS 64512, 온프렘 65000)
4. 라우팅 설정

**참고 문서**: `docs/vpn-migration-and-testing-guide.md`

### 2단계: Ping 테스트 (내일)

**담당**: 온프렘 네트워크 팀

**테스트 항목**:
- Route53 Resolver Inbound: 10.200.1.178, 10.200.2.123
- EC2 인스턴스: 10.200.1.159, 10.200.1.90, 10.200.1.139
- 프론트엔드 VPC: 10.10.1.1, 10.10.2.1
- 버지니아 VPC: 10.20.1.1, 10.20.2.1

**예상 결과**: 모든 엔드포인트에서 응답 (TTL: 255, 지연시간 < 200ms)

### 3단계: 기존 VPN 정리 (테스트 성공 후)

**담당**: AWS 담당자

**작업**:
1. 기존 VPN 연결 삭제 (vpn-0acd5eff60174538a)
2. VPN Gateway 분리 (vgw-0d54d0b0af6515dec)
3. VPN Gateway 삭제

---

## 📊 성능 지표

### 예상 지연시간

| 경로 | 예상 지연시간 |
|------|--------------|
| 온프렘 → 로깅 VPC | 50-100ms |
| 온프렘 → 프론트엔드 VPC | 50-100ms |
| 온프렘 → 버지니아 VPC | 150-200ms |
| 프론트엔드 VPC → 버지니아 VPC | 100-150ms |

### 대역폭

| 연결 | 대역폭 |
|------|--------|
| VPN (온프렘 ↔ TGW) | 1.25 Gbps (AWS 제한) |
| VPC 피어링 (프론트엔드 ↔ 버지니아) | 무제한 |
| TGW (VPC 간) | 무제한 |

---

## 🔐 보안 설정

### Security Group 규칙

#### 로깅 VPC
- Inbound: 온프렘 (192.128.0.0/16)에서 모든 트래픽 허용
- Outbound: 모든 트래픽 허용

#### 프론트엔드 VPC
- Inbound: 온프렘 (192.128.0.0/16)에서 모든 트래픽 허용
- Outbound: 모든 트래픽 허용

#### 버지니아 VPC
- Inbound: 프론트엔드 VPC (10.10.0.0/16)에서 모든 트래픽 허용
- Outbound: 모든 트래픽 허용

### VPC 엔드포인트 정책

- Bedrock Runtime: 프론트엔드 VPC에서만 접근
- Secrets Manager: 프론트엔드 VPC에서만 접근
- CloudWatch Logs: 프론트엔드 VPC에서만 접근
- S3: 모든 VPC에서 접근

---

## 📞 연락처

| 역할 | 이름 | 연락처 |
|------|------|--------|
| AWS 담당자 | [이름] | [이메일] |
| 온프렘 네트워크 팀 | [이름] | [연락처] |
| 긴급 연락처 | [이름] | [전화번호] |

---

## 📚 참고 문서

- `docs/vpn-migration-and-testing-guide.md` - VPN 마이그레이션 및 테스트 가이드
- `docs/tgw-migration-guide.md` - Transit Gateway 마이그레이션 가이드
- `.kiro/specs/bos-ai-vpc-consolidation/requirements.md` - 요구사항
- `.kiro/specs/bos-ai-vpc-consolidation/design.md` - 설계 문서
- `.kiro/specs/bos-ai-vpc-consolidation/tasks.md` - 작업 목록

---

## 체크리스트

### 온프렘 방화벽 설정 전
- [ ] 기존 VPN 연결 정보 백업
- [ ] 새 VPN 설정 정보 확인
- [ ] 테스트 일정 확인
- [ ] 롤백 계획 수립

### 온프렘 방화벽 설정 후
- [ ] VPN 터널 1 상태 확인
- [ ] VPN 터널 2 상태 확인
- [ ] BGP 세션 상태 확인
- [ ] 라우팅 테이블 확인

### Ping 테스트
- [ ] Route53 Resolver Inbound 1 (10.200.1.178)
- [ ] Route53 Resolver Inbound 2 (10.200.2.123)
- [ ] EC2 로그 수집기 (10.200.1.159)
- [ ] EC2 모니터링 (10.200.1.90)
- [ ] EC2 Grafana (10.200.1.139)
- [ ] 프론트엔드 VPC 1 (10.10.1.1)
- [ ] 프론트엔드 VPC 2 (10.10.2.1)
- [ ] 버지니아 VPC 1 (10.20.1.1)
- [ ] 버지니아 VPC 2 (10.20.2.1)

### 기존 VPN 정리
- [ ] 새 VPN 안정성 확인 (24시간)
- [ ] 기존 VPN 연결 삭제
- [ ] VPN Gateway 분리
- [ ] VPN Gateway 삭제
- [ ] 온프렘 방화벽 정리

---

**마지막 업데이트**: 2026-02-26  
**다음 검토**: 2026-02-27 (테스트 후)
