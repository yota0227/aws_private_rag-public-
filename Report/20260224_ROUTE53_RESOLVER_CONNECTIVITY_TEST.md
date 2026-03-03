# Route53 Resolver Endpoint 연결성 테스트

**Date:** 2026-02-24  
**Objective:** Route53 Resolver Endpoint (Seoul)까지의 통신 정상 여부 확인  
**Status:** 테스트 계획 수립

---

## 🎯 테스트 목표

```
On-Premises
    ↓ (VPN Tunnel)
    ↓
Seoul VPC (10.10.0.0/16)
    ↓
Route53 Resolver Endpoint (10.10.1.10, 10.10.2.10)
    ↓
Route53 Private Hosted Zone (aws.internal)
    ↓
✅ 응답 수신
```

**확인할 것:**
1. On-Premises → Seoul VPC 네트워크 연결 ✅
2. Route53 Resolver Endpoint 응답성 ✅
3. DNS 쿼리 포워딩 작동 ✅

---

## 📋 테스트 단계

### Phase 1: 기본 네트워크 연결 확인

#### 1-1. VPN 터널 상태 확인
```bash
# On-Premises에서 실행
# VPN 연결 상태 확인
ping 10.10.1.10  # Route53 Resolver IP (Seoul VPC)
ping 10.10.2.10  # Route53 Resolver IP (Seoul VPC)

# 예상 결과:
# PING 10.10.1.10 (10.10.1.10) 56(84) bytes of data.
# 64 bytes from 10.10.1.10: icmp_seq=1 ttl=64 time=50.2 ms
# 64 bytes from 10.10.1.10: icmp_seq=2 ttl=64 time=49.8 ms
```

#### 1-2. Seoul VPC 내부 리소스 접근 확인
```bash
# On-Premises에서 실행
# Seoul VPC의 다른 리소스 접근 테스트
ping 10.10.1.50   # Seoul VPC 내부 IP (예시)
ping 10.10.101.10 # Seoul VPC Public Subnet (예시)

# 예상 결과: 응답 수신 (TTL 감소)
```

---

### Phase 2: Route53 Resolver Endpoint 응답성 확인

#### 2-1. DNS 포트 연결성 테스트
```bash
# On-Premises에서 실행
# TCP 53 포트 (DNS) 연결 테스트
nc -zv 10.10.1.10 53
nc -zv 10.10.2.10 53

# 예상 결과:
# Connection to 10.10.1.10 53 port [tcp/domain] succeeded!
# Connection to 10.10.2.10 53 port [tcp/domain] succeeded!
```

#### 2-2. UDP 53 포트 연결성 테스트
```bash
# On-Premises에서 실행
# UDP 53 포트 (DNS) 연결 테스트
nc -zuv 10.10.1.10 53
nc -zuv 10.10.2.10 53

# 예상 결과:
# Connection to 10.10.1.10 53 port [udp/domain] succeeded!
```

---

### Phase 3: DNS 쿼리 테스트

#### 3-1. 기본 DNS 쿼리 (aws.internal 도메인)
```bash
# On-Premises에서 실행
# Route53 Resolver에 DNS 쿼리 전송
nslookup aws.internal 10.10.1.10

# 예상 결과:
# Server:  10.10.1.10
# Address: 10.10.1.10#53
# 
# Name:    aws.internal
# Address: <Private Hosted Zone IP>
```

#### 3-2. 와일드카드 쿼리 테스트
```bash
# On-Premises에서 실행
# 아직 레코드가 없으므로 NXDOMAIN 응답 예상
nslookup bedrock-runtime.us-east-1.aws.internal 10.10.1.10

# 예상 결과 (현재):
# Server:  10.10.1.10
# Address: 10.10.1.10#53
# 
# ** server can't find bedrock-runtime.us-east-1.aws.internal: NXDOMAIN
# (이것이 정상! 레코드가 아직 없으니까)
```

#### 3-3. 외부 도메인 쿼리 테스트
```bash
# On-Premises에서 실행
# Route53 Resolver가 외부 DNS도 포워딩하는지 확인
nslookup google.com 10.10.1.10

# 예상 결과:
# Server:  10.10.1.10
# Address: 10.10.1.10#53
# 
# Non-authoritative answer:
# Name:    google.com
# Address: 142.250.185.46
```

---

### Phase 4: 상세 DNS 쿼리 분석

#### 4-1. dig를 이용한 상세 분석
```bash
# On-Premises에서 실행
# 더 상세한 DNS 정보 확인
dig @10.10.1.10 aws.internal

# 예상 결과:
# ; <<>> DiG 9.16.1-Ubuntu <<>> @10.10.1.10 aws.internal
# ; (1 server found)
# ;; global options: +cmd
# ;; Got answer:
# ;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 12345
# ;; flags: qr rd ra; QUERY: 1, ANSWER: 0, AUTHORITY: 0, ADDITIONAL: 0
# 
# ;; QUESTION SECTION:
# ;aws.internal.			IN	A
# 
# ;; Query time: 45 msec
# ;; SERVER: 10.10.1.10#53(10.10.1.10)
# ;; WHEN: Mon Feb 24 10:00:00 UTC 2026
# ;; MSG SIZE  rcvd: 28
```

#### 4-2. 쿼리 응답 시간 측정
```bash
# On-Premises에서 실행
# 여러 번 쿼리해서 응답 시간 확인
for i in {1..5}; do
  dig @10.10.1.10 aws.internal | grep "Query time"
done

# 예상 결과:
# Query time: 45 msec
# Query time: 42 msec
# Query time: 48 msec
# Query time: 44 msec
# Query time: 46 msec
# (평균 45ms 정도, 안정적)
```

---

### Phase 5: Security Group 및 네트워크 ACL 확인

#### 5-1. Route53 Resolver Security Group 확인
```bash
# AWS CLI로 실행 (Seoul Region)
aws ec2 describe-security-groups \
  --region ap-northeast-2 \
  --filters "Name=group-name,Values=*route53*" \
  --query 'SecurityGroups[*].[GroupId,GroupName,IpPermissions]'

# 확인 사항:
# ✅ Inbound: TCP/UDP 53 from 10.0.0.0/8 (On-Premises CIDR)
# ✅ Outbound: All traffic allowed
```

#### 5-2. VPC 네트워크 ACL 확인
```bash
# AWS CLI로 실행 (Seoul Region)
aws ec2 describe-network-acls \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-XXXXXXXXX" \
  --query 'NetworkAcls[*].[NetworkAclId,Entries]'

# 확인 사항:
# ✅ Inbound: TCP/UDP 53 허용
# ✅ Outbound: TCP/UDP 53 허용
```

---

## 🔍 문제 해결 가이드

### 문제 1: Ping 실패 (10.10.1.10 응답 없음)

**원인:**
- VPN 터널 미연결
- Route53 Resolver Endpoint 미배포
- Security Group 차단

**해결:**
```bash
# 1. VPN 상태 확인
aws ec2 describe-vpn-connections \
  --region ap-northeast-2 \
  --query 'VpnConnections[*].[VpnConnectionId,State]'

# 2. Route53 Resolver 상태 확인
aws route53resolver describe-resolver-endpoints \
  --region ap-northeast-2 \
  --query 'ResolverEndpoints[*].[Id,Status,IpAddressCount]'

# 3. Security Group 확인
aws ec2 describe-security-groups \
  --region ap-northeast-2 \
  --query 'SecurityGroups[?Tags[?Key==`Name` && Value==`*resolver*`]]'
```

### 문제 2: DNS 쿼리 타임아웃

**원인:**
- Route53 Resolver 응답 없음
- 네트워크 경로 문제
- DNS 포트 차단

**해결:**
```bash
# 1. 더 긴 타임아웃으로 재시도
dig @10.10.1.10 +timeout=10 aws.internal

# 2. TCP DNS 쿼리 시도 (UDP 대신)
dig @10.10.1.10 +tcp aws.internal

# 3. 다른 Resolver IP 시도
nslookup aws.internal 10.10.2.10
```

### 문제 3: NXDOMAIN 응답 (도메인 없음)

**원인:**
- 정상 동작 (레코드가 아직 없음)
- Route53 Private Hosted Zone 미연결

**확인:**
```bash
# Route53 Hosted Zone 상태 확인
aws route53 get-hosted-zone \
  --id Z08304561GR4R43JANCB3 \
  --query 'HostedZone.[Id,Name,Config.PrivateZone]'

# VPC 연결 확인
aws route53 list-vpc-association-authorizations \
  --hosted-zone-id Z08304561GR4R43JANCB3
```

---

## 📊 테스트 결과 기록

### 테스트 환경
```
On-Premises DNS Server: [IP 주소]
Route53 Resolver Endpoint: 10.10.1.10, 10.10.2.10
Seoul VPC: 10.10.0.0/16
VPN Connection: [상태]
```

### 테스트 결과

| 테스트 항목 | 명령어 | 예상 결과 | 실제 결과 | 상태 |
|-----------|--------|---------|---------|------|
| Ping 10.10.1.10 | `ping 10.10.1.10` | 응답 수신 | ? | ⏳ |
| Ping 10.10.2.10 | `ping 10.10.2.10` | 응답 수신 | ? | ⏳ |
| TCP 53 연결 | `nc -zv 10.10.1.10 53` | 성공 | ? | ⏳ |
| UDP 53 연결 | `nc -zuv 10.10.1.10 53` | 성공 | ? | ⏳ |
| DNS 쿼리 | `nslookup aws.internal 10.10.1.10` | 응답 수신 | ? | ⏳ |
| 외부 DNS | `nslookup google.com 10.10.1.10` | 응답 수신 | ? | ⏳ |
| 응답 시간 | `dig @10.10.1.10 aws.internal` | 40-50ms | ? | ⏳ |

---

## 🚀 다음 단계

### 테스트 완료 후
1. ✅ 모든 테스트 통과 → DNS 레코드 추가 진행
2. ⚠️ 일부 실패 → 문제 해결 후 재시도
3. ❌ 대부분 실패 → 인프라 재검토

### 성공 시나리오
```
✅ Route53 Resolver Endpoint 정상 작동
    ↓
✅ DNS 레코드 추가 (Terraform)
    ↓
✅ On-Premises DNS 설정 (BIND/Unbound)
    ↓
✅ 폐쇄망 AWS 엔드포인트 호출 가능
```

---

## 📝 테스트 스크립트

### 자동화 테스트 스크립트 (test-route53-resolver.sh)

```bash
#!/bin/bash

echo "=== Route53 Resolver Endpoint 연결성 테스트 ==="
echo ""

# 테스트 대상 IP
RESOLVER_IPS=("10.10.1.10" "10.10.2.10")

for IP in "${RESOLVER_IPS[@]}"; do
  echo "테스트 대상: $IP"
  echo "---"
  
  # 1. Ping 테스트
  echo "1. Ping 테스트..."
  if ping -c 1 -W 2 $IP > /dev/null 2>&1; then
    echo "   ✅ Ping 성공"
  else
    echo "   ❌ Ping 실패"
  fi
  
  # 2. TCP 53 테스트
  echo "2. TCP 53 포트 테스트..."
  if nc -zv -w 2 $IP 53 > /dev/null 2>&1; then
    echo "   ✅ TCP 53 연결 성공"
  else
    echo "   ❌ TCP 53 연결 실패"
  fi
  
  # 3. DNS 쿼리 테스트
  echo "3. DNS 쿼리 테스트..."
  RESULT=$(nslookup aws.internal $IP 2>&1 | grep -c "aws.internal")
  if [ $RESULT -gt 0 ]; then
    echo "   ✅ DNS 쿼리 성공"
    nslookup aws.internal $IP | head -5
  else
    echo "   ❌ DNS 쿼리 실패"
  fi
  
  echo ""
done

echo "=== 테스트 완료 ==="
```

**실행:**
```bash
chmod +x test-route53-resolver.sh
./test-route53-resolver.sh
```

---

**Last Updated:** 2026-02-24  
**Status:** 테스트 계획 수립 완료  
**Next Action:** On-Premises에서 테스트 실행

