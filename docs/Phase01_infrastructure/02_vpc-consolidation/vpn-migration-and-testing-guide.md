# VPN 마이그레이션 및 연결 테스트 가이드

**작성일**: 2026-02-26  
**상태**: 온프렘 방화벽 설정 대기 중  
**목표**: Transit Gateway VPN으로 마이그레이션 및 연결 검증

---

## 📋 목차

1. [현재 상태](#현재-상태)
2. [온프렘 방화벽 설정](#온프렘-방화벽-설정)
3. [Ping 테스트 엔드포인트](#ping-테스트-엔드포인트)
4. [테스트 절차](#테스트-절차)
5. [기존 VPN 정리](#기존-vpn-정리)
6. [트러블슈팅](#트러블슈팅)

---

## 현재 상태

### AWS 인프라 구조

```
온프렘 (192.128.0.0/16)
    ↓ VPN (새로 설정할 것)
Transit Gateway (tgw-0897383168475b532)
    ├─ 로깅 파이프라인 VPC (10.200.0.0/16)
    │   ├─ Private Subnet 1: 10.200.1.0/24 (ap-northeast-2a)
    │   ├─ Private Subnet 2: 10.200.2.0/24 (ap-northeast-2c)
    │   └─ Route53 Resolver Inbound Endpoint
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
            ├─ S3 (데이터 저장소)
            └─ VPC Endpoints
```

### AWS 리소스 정보

| 리소스 | ID | 상태 |
|--------|-----|------|
| Transit Gateway | `tgw-0897383168475b532` | Active |
| 로깅 VPC | `vpc-066c464f9c750ee9e` | Active |
| 프론트엔드 VPC | `vpc-0a118e1bf21d0c057` | Active |
| 백엔드 VPC (버지니아) | `vpc-0ed37ff82027c088f` | Active |
| VPC 피어링 | `pcx-0a44f0b90565313f7` | Active |
| **새 VPN 연결** | `vpn-0b2b65e9414092369` | **Pending** |
| **기존 VPN 연결** | `vpn-0acd5eff60174538a` | Available (삭제 예정) |

---

## 온프렘 방화벽 설정

### 1단계: 기존 VPN 연결 종료

**기존 VPN 정보:**
- VPN ID: `vpn-0acd5eff60174538a`
- VPN Gateway: `vgw-0d54d0b0af6515dec`
- 연결 대상: 로깅 VPC (10.200.0.0/16)

**작업:**
1. 온프렘 방화벽에서 기존 VPN 터널 비활성화
2. BGP 세션 종료
3. 기존 VPN 설정 제거

### 2단계: 새 TGW VPN 연결 설정

**새 VPN 정보:**
- VPN ID: `vpn-0b2b65e9414092369`
- Transit Gateway ID: `tgw-0897383168475b532`
- AWS ASN: `64512`
- 온프렘 ASN: `65000`

#### Tunnel 1 설정

```
AWS 측:
  - 외부 IP: 3.38.69.188
  - 내부 IP: 169.254.224.53/30
  - BGP ASN: 64512
  - Pre-shared Key: 5RXxu5CEtzBY7bXGCP5YCN9smfYM00OP

온프렘 측:
  - 외부 IP: 211.170.236.130
  - 내부 IP: 169.254.224.54/30
  - BGP ASN: 65000
  - Pre-shared Key: 5RXxu5CEtzBY7bXGCP5YCN9smfYM00OP

IPSec 설정:
  - 암호화: AES-128-CBC
  - 인증: HMAC-SHA1-96
  - DH Group: Group 2
  - Lifetime: 3600초
```

#### Tunnel 2 설정

```
AWS 측:
  - 외부 IP: 43.200.222.199
  - 내부 IP: 169.254.96.197/30
  - BGP ASN: 64512
  - Pre-shared Key: pCgEtv28JG7mUDagkyRgqyclLSf7pyyf

온프렘 측:
  - 외부 IP: 211.170.236.130
  - 내부 IP: 169.254.96.198/30
  - BGP ASN: 65000
  - Pre-shared Key: pCgEtv28JG7mUDagkyRgqyclLSf7pyyf

IPSec 설정:
  - 암호화: AES-128-CBC
  - 인증: HMAC-SHA1-96
  - DH Group: Group 2
  - Lifetime: 3600초
```

#### BGP 설정

```
BGP 라우팅 설정:
  - AWS에서 광고할 CIDR:
    * 10.200.0.0/16 (로깅 VPC)
    * 10.10.0.0/16 (프론트엔드 VPC)
    * 10.20.0.0/16 (버지니아 백엔드 VPC)
  
  - 온프렘에서 광고할 CIDR:
    * 192.128.0.0/16 (온프렘 네트워크)
```

### 3단계: VPN 연결 확인

온프렘 방화벽에서 다음을 확인하세요:

```bash
# VPN 터널 상태 확인
show vpn tunnel status

# BGP 세션 상태 확인
show bgp summary

# 라우팅 테이블 확인
show ip route bgp

# 예상 결과:
# - Tunnel 1: UP
# - Tunnel 2: UP
# - BGP 세션: Established
# - 수신 라우트: 10.200.0.0/16, 10.10.0.0/16, 10.20.0.0/16
```

---

## Ping 테스트 엔드포인트

### 테스트 대상 엔드포인트

#### 1. 로깅 파이프라인 VPC

| 용도 | IP 주소 | 설명 |
|------|---------|------|
| **Route53 Resolver Inbound** | `10.200.1.178` | Subnet 1 (ap-northeast-2a) |
| **Route53 Resolver Inbound** | `10.200.2.123` | Subnet 2 (ap-northeast-2c) |
| **EC2 로그 수집기** | `10.200.1.159` | ec2-logclt-itdev-int-poc-01 |
| **EC2 모니터링** | `10.200.1.90` | ec2test-open-mon-itdev-int-poc-01 |
| **EC2 Grafana** | `10.200.1.139` | ec2-gra-itdev-int-poc-01 |

#### 2. BOS-AI 프론트엔드 VPC

| 용도 | IP 주소 | 설명 |
|------|---------|------|
| **Lambda 서브넷** | `10.10.1.0/24` | Private Subnet 1 (ap-northeast-2a) |
| **Lambda 서브넷** | `10.10.2.0/24` | Private Subnet 2 (ap-northeast-2c) |

#### 3. 버지니아 백엔드 VPC

| 용도 | IP 주소 | 설명 |
|------|---------|------|
| **S3 VPC Endpoint** | `10.20.1.0/24` | Private Subnet 1 (us-east-1a) |
| **S3 VPC Endpoint** | `10.20.2.0/24` | Private Subnet 2 (us-east-1b) |

---

## 테스트 절차

### 📅 테스트 일정

**날짜**: 내일 (2026-02-27)  
**시간**: 온프렘 방화벽 VPN 설정 후  
**담당자**: 온프렘 네트워크 팀

### 테스트 순서

#### Phase 1: 기본 연결 테스트 (5-10분)

```bash
# 1. 로깅 VPC Route53 Resolver Inbound Endpoint 테스트
ping 10.200.1.178
ping 10.200.2.123

# 예상 결과:
# PING 10.200.1.178 (10.200.1.178) 56(84) bytes of data.
# 64 bytes from 10.200.1.178: icmp_seq=1 ttl=255 time=XX.X ms
# 64 bytes from 10.200.1.178: icmp_seq=2 ttl=255 time=XX.X ms
# ...
# --- 10.200.1.178 statistics ---
# 4 packets transmitted, 4 received, 0% packet loss, time XXXms
```

#### Phase 2: 로깅 VPC 내부 리소스 테스트 (5-10분)

```bash
# 2. EC2 로그 수집기 테스트
ping 10.200.1.159

# 3. EC2 모니터링 테스트
ping 10.200.1.90

# 4. EC2 Grafana 테스트
ping 10.200.1.139

# 예상 결과: 모두 응답 (TTL: 255)
```

#### Phase 3: 프론트엔드 VPC 테스트 (5-10분)

```bash
# 5. 프론트엔드 VPC 서브넷 테스트
ping 10.10.1.1
ping 10.10.2.1

# 예상 결과: 응답 (TTL: 255)
```

#### Phase 4: 버지니아 백엔드 VPC 테스트 (5-10분)

```bash
# 6. 버지니아 백엔드 VPC 서브넷 테스트
ping 10.20.1.1
ping 10.20.2.1

# 예상 결과: 응답 (TTL: 255)
```

### 테스트 결과 기록

테스트 결과를 다음 형식으로 기록하세요:

```
테스트 날짜: 2026-02-27
테스트 시간: HH:MM ~ HH:MM
테스트자: [이름]

테스트 결과:
┌─────────────────────────────────────────────────────────────┐
│ 엔드포인트 | IP 주소 | 응답 | 지연시간 | 패킷손실 | 상태 |
├─────────────────────────────────────────────────────────────┤
│ Route53 Inbound 1 | 10.200.1.178 | ✓ | XX.X ms | 0% | ✓ |
│ Route53 Inbound 2 | 10.200.2.123 | ✓ | XX.X ms | 0% | ✓ |
│ EC2 로그 수집기 | 10.200.1.159 | ✓ | XX.X ms | 0% | ✓ |
│ EC2 모니터링 | 10.200.1.90 | ✓ | XX.X ms | 0% | ✓ |
│ EC2 Grafana | 10.200.1.139 | ✓ | XX.X ms | 0% | ✓ |
│ 프론트엔드 VPC 1 | 10.10.1.1 | ✓ | XX.X ms | 0% | ✓ |
│ 프론트엔드 VPC 2 | 10.10.2.1 | ✓ | XX.X ms | 0% | ✓ |
│ 버지니아 VPC 1 | 10.20.1.1 | ✓ | XX.X ms | 0% | ✓ |
│ 버지니아 VPC 2 | 10.20.2.1 | ✓ | XX.X ms | 0% | ✓ |
└─────────────────────────────────────────────────────────────┘

전체 상태: ✓ 성공
```

---

## 기존 VPN 정리

### ⚠️ 주의사항

**새 VPN이 안정적으로 작동하는 것을 확인한 후에만 진행하세요!**

### 정리 절차

#### 1단계: 기존 VPN 연결 삭제 (AWS)

```bash
# 기존 VPN 연결 삭제
aws ec2 delete-vpn-connection \
  --vpn-connection-id vpn-0acd5eff60174538a \
  --region ap-northeast-2

# 확인
aws ec2 describe-vpn-connections \
  --region ap-northeast-2 \
  --query 'VpnConnections[*].[VpnConnectionId,State]'
```

#### 2단계: VPN Gateway 분리 (AWS)

```bash
# 로깅 VPC에서 VPN Gateway 분리
aws ec2 detach-vpn-gateway \
  --vpn-gateway-id vgw-0d54d0b0af6515dec \
  --vpc-id vpc-066c464f9c750ee9e \
  --region ap-northeast-2

# 5분 대기
sleep 300

# VPN Gateway 삭제
aws ec2 delete-vpn-gateway \
  --vpn-gateway-id vgw-0d54d0b0af6515dec \
  --region ap-northeast-2

# 확인
aws ec2 describe-vpn-gateways \
  --region ap-northeast-2 \
  --query 'VpnGateways[*].[VpnGatewayId,State]'
```

#### 3단계: 온프렘 방화벽 정리

1. 기존 VPN 터널 설정 제거
2. 기존 BGP 설정 제거
3. 기존 라우팅 규칙 제거

---

## 트러블슈팅

### 문제 1: VPN 터널이 UP이 아님

**증상**: VPN 상태가 `pending` 또는 `down`

**해결 방법**:
1. 온프렘 방화벽에서 VPN 설정 확인
2. Pre-shared Key 일치 확인
3. 외부 IP 주소 확인
4. 방화벽 규칙 확인 (UDP 500, 4500 포트)

### 문제 2: BGP 세션이 Established가 아님

**증상**: BGP 세션 상태가 `Idle` 또는 `Connect`

**해결 방법**:
1. BGP ASN 확인 (AWS: 64512, 온프렘: 65000)
2. BGP 내부 IP 주소 확인
3. VPN 터널 상태 확인
4. 방화벽 규칙 확인 (TCP 179 포트)

### 문제 3: Ping이 응답하지 않음

**증상**: Ping 타임아웃

**해결 방법**:
1. VPN 연결 상태 확인
2. BGP 라우팅 확인
3. Security Group 규칙 확인
4. Route Table 확인

### 문제 4: 지연시간이 높음

**증상**: Ping 응답 시간이 200ms 이상

**해결 방법**:
1. VPN 터널 상태 확인
2. 네트워크 대역폭 확인
3. AWS 리전 간 거리 확인 (서울 ↔ 버지니아는 약 100-150ms)

---

## AWS CLI 명령어 참고

### VPN 상태 확인

```bash
# 모든 VPN 연결 조회
aws ec2 describe-vpn-connections --region ap-northeast-2

# 특정 VPN 연결 상세 정보
aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-0b2b65e9414092369 \
  --region ap-northeast-2

# VPN 연결 상태 모니터링
watch -n 5 'aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-0b2b65e9414092369 \
  --region ap-northeast-2 \
  --query "VpnConnections[0].State"'
```

### Transit Gateway 상태 확인

```bash
# TGW 정보 조회
aws ec2 describe-transit-gateways \
  --transit-gateway-ids tgw-0897383168475b532 \
  --region ap-northeast-2

# TGW VPC 어태치먼트 조회
aws ec2 describe-transit-gateway-vpc-attachments \
  --region ap-northeast-2

# TGW 라우팅 테이블 조회
aws ec2 search-transit-gateway-routes \
  --transit-gateway-route-table-id tgw-rtb-06ab3b805ab879efb \
  --region ap-northeast-2 \
  --filters "Name=state,Values=active,blackhole"
```

### VPC 라우팅 테이블 확인

```bash
# 로깅 VPC 라우팅 테이블
aws ec2 describe-route-tables \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e"

# 프론트엔드 VPC 라우팅 테이블
aws ec2 describe-route-tables \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-0a118e1bf21d0c057"
```

---

## 연락처

**문제 발생 시 연락처:**
- AWS 담당자: [이름]
- 온프렘 네트워크 팀: [연락처]
- 긴급 연락처: [전화번호]

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
