# VPN 연결성 테스트 계획

작성일: 2026-03-03
테스트 대상: On-Prem → AWS TGW VPN

---

## 📋 테스트 환경

### AWS 리소스

**기존 서비스 VPC (10.200.0.0/16) - 실행 중인 인스턴스:**
- `ec2-logclt-itdev-int-poc-01`: 10.200.1.159 (running)
- `ec2-gra-itdev-int-poc-01`: 10.200.1.139 (running)
- `ec2test-open-mon-itdev-poc-01`: 10.200.1.90 (stopped)

**Seoul VPC (10.10.0.0/16):**
- 인스턴스 없음 (테스트용 생성 필요)

**Route53 Resolver 엔드포인트:**
- Inbound: `ibe-onprem-itdev-int-poc-01` (OPERATIONAL)
- Outbound: `obe-onprem-itdev-int-poc-01` (OPERATIONAL)

---

## 🎯 테스트 시나리오

### Phase 1: 기본 연결성 테스트

**목표:** VPN 터널이 정상 작동하는지 확인

```bash
# On-Prem에서 실행

# 1. Tunnel Inside IP 핑 테스트
ping 169.254.224.53  # AWS-TGW-T1
ping 169.254.96.197  # AWS-TGW-T2

# 2. VPC 엔드포인트 핑 테스트
ping 10.200.1.159    # 기존 서비스 VPC (running)
ping 10.200.1.139    # 기존 서비스 VPC (running)

# 3. 트래픽 흐름 확인
traceroute 10.200.1.159
```

**예상 결과:**
- ✅ Tunnel Inside IP: 응답 있음
- ✅ VPC 엔드포인트: 응답 있음
- ✅ Traceroute: VPN 터널을 통해 라우팅됨

---

### Phase 2: 애플리케이션 연결성 테스트

**목표:** 실제 서비스 접근 가능 여부 확인

```bash
# On-Prem에서 실행

# 1. SSH 연결 테스트
ssh -v ec2-user@10.200.1.159

# 2. HTTP/HTTPS 연결 테스트
curl -v http://10.200.1.159:80
curl -v https://10.200.1.159:443

# 3. DNS 쿼리 테스트 (Route53 Resolver)
nslookup example.com 10.10.x.x  # Resolver Inbound IP
```

**예상 결과:**
- ✅ SSH: 연결 성공
- ✅ HTTP/HTTPS: 응답 있음
- ✅ DNS: AWS 내부 DNS 해석

---

### Phase 3: 성능 테스트

**목표:** VPN 성능 확인

```bash
# On-Prem에서 실행

# 1. 대역폭 테스트
iperf3 -c 10.200.1.159 -t 10

# 2. 지연시간 측정
ping -c 100 10.200.1.159 | grep avg

# 3. 패킷 손실률 확인
ping -c 1000 10.200.1.159 | grep loss
```

**예상 결과:**
- ✅ 대역폭: 100+ Mbps
- ✅ 지연시간: < 50ms
- ✅ 패킷 손실: < 1%

---

## 🔧 테스트 실행 순서

### Step 1: 기본 연결성 확인 (필수)
```bash
# On-Prem에서
ping 169.254.224.53
ping 169.254.96.197
ping 10.200.1.159
```

### Step 2: Fortigate 로그 확인
```bash
# Fortigate에서
diagnose vpn ipsec status
get router info bgp summary
```

### Step 3: AWS 콘솔 확인
```bash
# AWS CLI
aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-0b2b65e9414092369 \
  --region ap-northeast-2
```

### Step 4: 애플리케이션 테스트 (선택)
```bash
# On-Prem에서
ssh -v ec2-user@10.200.1.159
```

---

## 📊 테스트 결과 기록

### 테스트 1: Tunnel Inside IP 핑

| 대상 IP | 상태 | 응답시간 | 패킷손실 |
|---------|------|---------|---------|
| 169.254.224.53 | ⏳ | - | - |
| 169.254.96.197 | ⏳ | - | - |

### 테스트 2: VPC 엔드포인트 핑

| 대상 IP | VPC | 상태 | 응답시간 | 패킷손실 |
|---------|-----|------|---------|---------|
| 10.200.1.159 | 기존 서비스 | ⏳ | - | - |
| 10.200.1.139 | 기존 서비스 | ⏳ | - | - |

### 테스트 3: 애플리케이션 연결

| 서비스 | 대상 | 상태 | 응답시간 |
|--------|------|------|---------|
| SSH | 10.200.1.159 | ⏳ | - |
| HTTP | 10.200.1.159 | ⏳ | - |

---

## ⚠️ 주의사항

1. **보안 그룹 확인**
   - AWS 인스턴스의 보안 그룹이 On-Prem CIDR (192.128.0.0/16)을 허용하는지 확인
   - 필요시 인바운드 규칙 추가

2. **라우팅 테이블 확인**
   - VPC 라우팅 테이블에 On-Prem CIDR (192.128.0.0/16)이 TGW로 라우팅되는지 확인

3. **방화벽 규칙 확인**
   - Fortigate 방화벽 정책이 AWS 트래픽을 허용하는지 확인

4. **DNS 설정**
   - Route53 Resolver Inbound Endpoint IP 확인
   - On-Prem DNS 포워더 설정 확인

---

## 🎯 성공 기준

| 항목 | 기준 | 상태 |
|------|------|------|
| **Tunnel Inside IP 핑** | 응답 있음 | ⏳ |
| **VPC 엔드포인트 핑** | 응답 있음 | ⏳ |
| **SSH 연결** | 연결 성공 | ⏳ |
| **DNS 쿼리** | 해석 성공 | ⏳ |
| **패킷 손실** | < 1% | ⏳ |
| **지연시간** | < 50ms | ⏳ |

---

## 📞 문제 해결

### 핑이 응답하지 않는 경우

1. **Fortigate 방화벽 정책 확인**
   ```bash
   get firewall policy
   ```

2. **AWS 보안 그룹 확인**
   ```bash
   aws ec2 describe-security-groups \
     --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
     --region ap-northeast-2
   ```

3. **라우팅 테이블 확인**
   ```bash
   aws ec2 describe-route-tables \
     --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
     --region ap-northeast-2
   ```

### SSH 연결이 실패하는 경우

1. **보안 그룹에 SSH (22) 허용 추가**
2. **On-Prem 방화벽에서 SSH 트래픽 허용**
3. **EC2 인스턴스 상태 확인** (running 상태인지)

