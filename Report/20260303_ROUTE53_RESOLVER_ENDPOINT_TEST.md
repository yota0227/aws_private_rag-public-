# Route53 Resolver 엔드포인트 테스트 보고서

작성일: 2026-03-03
테스트 대상: Route53 Resolver Inbound Endpoint

---

## 📋 **Route53 Resolver Inbound Endpoint 정보**

### 엔드포인트 상세 정보

| 항목 | 값 |
|------|-----|
| **Endpoint ID** | rslvr-in-79867dcffe644a378 |
| **Name** | ibe-onprem-itdev-int-poc-01 |
| **Direction** | INBOUND |
| **Status** | ✅ OPERATIONAL |
| **VPC** | vpc-066c464f9c750ee9e (기존 서비스 VPC) |
| **IP Count** | 2 |
| **Type** | IPV4 |
| **Protocol** | Do53 (DNS over 53) |

### 엔드포인트 IP 주소

| IP 주소 | Subnet | Status | 용도 |
|---------|--------|--------|------|
| **10.200.1.178** | subnet-0f027e9de8e26c18f | ✅ ATTACHED | Primary |
| **10.200.2.123** | subnet-0625d992edf151017 | ✅ ATTACHED | Secondary |

---

## 🎯 **DNS Lookup 테스트 계획**

### On-Prem에서 실행할 명령어

```bash
# 1. Primary Endpoint로 DNS 쿼리
nslookup example.com 10.200.1.178
dig @10.200.1.178 example.com

# 2. Secondary Endpoint로 DNS 쿼리
nslookup example.com 10.200.2.123
dig @10.200.2.123 example.com

# 3. AWS 내부 도메인 쿼리 (예: EC2 인스턴스)
nslookup ip-10-200-1-159.ap-northeast-2.compute.internal 10.200.1.178

# 4. 성능 테스트
time nslookup example.com 10.200.1.178
```

---

## 🔍 **Route53 Resolver 규칙**

### 현재 설정된 규칙

#### 1. Internet Resolver (기본)
```
Rule ID: rslvr-autodefined-rr-internet-resolver
Domain: . (모든 도메인)
Type: RECURSIVE
Status: COMPLETE
Owner: Route 53 Resolver
```

#### 2. Custom Forward Rule
```
Rule ID: rslvr-rr-d879d3d2796348d38
Name: rule-dns-itdev-int-poc-01
Domain: . (모든 도메인)
Type: FORWARD
Status: COMPLETE
Target IPs:
  - 168.126.63.1:53 (DNS 포워더)
  - 168.126.63.2:53 (DNS 포워더)
Outbound Endpoint: rslvr-out-528276266e13403aa
```

---

## 🚀 **DNS 쿼리 흐름**

### On-Prem → Route53 Resolver → AWS

```
On-Prem DNS Client (192.128.x.x)
    ↓
DNS Query (port 53)
    ↓
VPN Tunnel (TGW)
    ↓
Route53 Resolver Inbound Endpoint (10.200.1.178 또는 10.200.2.123)
    ↓
Route53 Resolver Rules
    ↓
AWS Route53 또는 Custom DNS Server
    ↓
DNS Response
    ↓
On-Prem DNS Client
```

---

## ✅ **연결성 검증**

### 필수 조건 확인

| 항목 | 상태 | 확인 |
|------|------|------|
| **VPN 연결** | ✅ UP | 완료 |
| **라우팅** | ✅ Active | 완료 |
| **Route53 Endpoint** | ✅ OPERATIONAL | 완료 |
| **Endpoint IP** | ✅ ATTACHED | 완료 |
| **보안 그룹** | ⏳ 확인 필요 | - |
| **DNS 포워더** | ⏳ 확인 필요 | - |

---

## 🔧 **DNS Lookup 테스트 결과**

### 테스트 1: Primary Endpoint (10.200.1.178)

**명령어:**
```bash
nslookup example.com 10.200.1.178
```

**예상 결과:**
```
Server:         10.200.1.178
Address:        10.200.1.178#53

Name:   example.com
Address: 93.184.216.34
```

**상태:** ⏳ 테스트 대기

---

### 테스트 2: Secondary Endpoint (10.200.2.123)

**명령어:**
```bash
nslookup example.com 10.200.2.123
```

**예상 결과:**
```
Server:         10.200.2.123
Address:        10.200.2.123#53

Name:   example.com
Address: 93.184.216.34
```

**상태:** ⏳ 테스트 대기

---

### 테스트 3: AWS 내부 도메인

**명령어:**
```bash
nslookup ip-10-200-1-159.ap-northeast-2.compute.internal 10.200.1.178
```

**예상 결과:**
```
Server:         10.200.1.178
Address:        10.200.1.178#53

Name:   ip-10-200-1-159.ap-northeast-2.compute.internal
Address: 10.200.1.159
```

**상태:** ⏳ 테스트 대기

---

## 📊 **성능 지표**

### DNS 응답 시간 (예상)

| 쿼리 대상 | 응답 시간 | 상태 |
|----------|----------|------|
| 인터넷 도메인 | < 100ms | ⏳ |
| AWS 내부 도메인 | < 50ms | ⏳ |
| 캐시된 도메인 | < 10ms | ⏳ |

---

## 🎯 **다음 단계**

### 1️⃣ On-Prem DNS 포워더 설정

**목표:** On-Prem DNS 서버가 Route53 Resolver로 쿼리를 포워드하도록 설정

```bash
# On-Prem DNS 서버 설정 예시 (BIND)
zone "." {
    type forward;
    forwarders { 10.200.1.178; 10.200.2.123; };
    forward only;
};
```

### 2️⃣ DNS 쿼리 테스트

```bash
# On-Prem에서
nslookup example.com
dig example.com
```

### 3️⃣ 성능 모니터링

```bash
# DNS 응답 시간 측정
time nslookup example.com 10.200.1.178

# 대량 쿼리 테스트
for i in {1..100}; do nslookup example.com 10.200.1.178; done
```

---

## ⚠️ **주의사항**

### 보안 그룹 확인

Route53 Resolver Inbound Endpoint의 보안 그룹이 다음을 허용하는지 확인:

```
Inbound Rule:
  Protocol: UDP
  Port: 53
  Source: On-Prem CIDR (192.128.0.0/16)
```

### DNS 포워더 설정

On-Prem DNS 서버가 Route53 Resolver Inbound Endpoint로 쿼리를 포워드하도록 설정해야 함

---

## 📞 **참고 정보**

- **Inbound Endpoint ID**: rslvr-in-79867dcffe644a378
- **Primary IP**: 10.200.1.178
- **Secondary IP**: 10.200.2.123
- **VPC**: vpc-066c464f9c750ee9e (기존 서비스 VPC)
- **Status**: OPERATIONAL

---

## 🎊 **최종 평가**

**Route53 Resolver 엔드포인트: ✅ 준비 완료**

- ✅ Inbound Endpoint: OPERATIONAL
- ✅ IP 주소: 2개 (Primary + Secondary)
- ✅ VPN 연결: 정상
- ✅ 라우팅: 정상
- ⏳ DNS 쿼리: 테스트 대기

**다음 단계:**
1. On-Prem DNS 포워더 설정
2. DNS 쿼리 테스트
3. 성능 모니터링

