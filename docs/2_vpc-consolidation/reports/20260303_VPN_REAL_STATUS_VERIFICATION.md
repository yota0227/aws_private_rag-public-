# VPN 실제 상태 검증 보고서

작성일: 2026-03-03 (재검증)
VPN Connection ID: vpn-0b2b65e9414092369

---

## 🎉 **긴급 업데이트: 터널이 UP 상태로 변경됨!**

### AWS 콘솔 현재 상태

```
Tunnel 1 (3.38.69.188):
  Status: ✅ UP
  Message: 14 BGP ROUTES
  AcceptedRouteCount: 14

Tunnel 2 (43.200.222.199):
  Status: ✅ UP
  Message: 14 BGP ROUTES
  AcceptedRouteCount: 14
```

**이전 상태 (2026-03-03 18:54:18):**
```
Tunnel 1: DOWN
Tunnel 2: DOWN
```

**현재 상태:**
```
Tunnel 1: UP ✅
Tunnel 2: UP ✅
```

---

## ✅ 검증된 설정 정보

### Tunnel 1 설정

| 항목 | 값 |
|------|-----|
| **AWS Outside IP** | 3.38.69.188 |
| **Tunnel Inside CIDR** | 169.254.224.52/30 |
| **AWS Tunnel Inside IP** | 169.254.224.53 |
| **On-Prem Tunnel Inside IP** | 169.254.224.54 |
| **Pre-Shared Key** | 5RXxu5CEtzBY7bXGCP5YCN9smfYM00OP |
| **On-Prem Public IP** | 211.170.236.130 |
| **BGP ASN (On-Prem)** | 65000 |
| **BGP ASN (AWS)** | 64512 |

### Tunnel 2 설정

| 항목 | 값 |
|------|-----|
| **AWS Outside IP** | 43.200.222.199 |
| **Tunnel Inside CIDR** | 169.254.96.196/30 |
| **AWS Tunnel Inside IP** | 169.254.96.197 |
| **On-Prem Tunnel Inside IP** | 169.254.96.198 |
| **Pre-Shared Key** | pCgEtv28JG7mUDagkyRgqyclLSf7pyyf |
| **On-Prem Public IP** | 211.170.236.130 |
| **BGP ASN (On-Prem)** | 65000 |
| **BGP ASN (AWS)** | 64512 |

---

## 🔍 IKE/IPsec 파라미터 (양쪽 터널 동일)

### IKE Phase 1
```
Authentication Protocol: SHA1
Encryption Protocol: AES-128-CBC
Lifetime: 28800 seconds (8 hours)
Perfect Forward Secrecy: Group 2 (DH Group 2)
Mode: Main
```

### IPsec Phase 2
```
Protocol: ESP
Authentication Protocol: HMAC-SHA1-96
Encryption Protocol: AES-128-CBC
Lifetime: 3600 seconds (1 hour)
Perfect Forward Secrecy: Group 2 (DH Group 2)
Mode: Tunnel
TCP MSS Adjustment: 1379
```

---

## 📊 Fortigate vs AWS 설정 비교

### ✅ 일치하는 항목

| 항목 | Fortigate | AWS | 상태 |
|------|-----------|-----|------|
| **Tunnel 1 Outside IP** | 3.38.69.188 | 3.38.69.188 | ✅ |
| **Tunnel 2 Outside IP** | 43.200.222.199 | 43.200.222.199 | ✅ |
| **Tunnel 1 Inside IP** | 169.254.224.54 | 169.254.224.54 | ✅ |
| **Tunnel 2 Inside IP** | 169.254.96.198 | 169.254.96.198 | ✅ |
| **PSK Tunnel 1** | 5RXxu5CEtzBY7bXGCP5YCN9smfYM00OP | 5RXxu5CEtzBY7bXGCP5YCN9smfYM00OP | ✅ |
| **PSK Tunnel 2** | pCgEtv28JG7mUDagkyRgqyclLSf7pyyf | pCgEtv28JG7mUDagkyRgqyclLSf7pyyf | ✅ |
| **IKE Proposal** | AES128-SHA1 | AES-128-CBC + SHA1 | ✅ |
| **IPsec Proposal** | AES128-SHA1 | AES-128-CBC + HMAC-SHA1-96 | ✅ |
| **DH Group** | 2 | 2 | ✅ |
| **BGP ASN (On-Prem)** | 65000 | 65000 | ✅ |
| **BGP ASN (AWS)** | 64512 | 64512 | ✅ |

---

## 🎯 현재 상황 분석

### 이전 문제 (해결됨)
- ❌ AWS 터널 상태: DOWN
- ❌ BGP 이웃: Idle
- ❌ 라우트 수신: 0개

### 현재 상황 (정상)
- ✅ AWS 터널 상태: UP
- ✅ BGP 이웃: 연결 예상 (재확인 필요)
- ✅ 라우트 수신: 14개 (각 터널당)

---

## 🔥 다음 확인 사항

### 1. Fortigate BGP 상태 재확인
```bash
get router info bgp summary
get router info bgp neighbors
```

**예상 결과:**
```
169.254.224.53  4  64512  MsgRcvd  MsgSent  TblVer  Up/Down  State/PfxRcd
169.254.96.197  4  64512  MsgRcvd  MsgSent  TblVer  Up/Down  State/PfxRcd
```

상태가 `Established`로 변경되어야 함

### 2. Fortigate 라우팅 테이블 확인
```bash
get router info routing-table all
```

**예상 결과:**
- AWS VPC 라우트 (10.10.0.0/16, 10.200.0.0/16 등)가 BGP로 학습됨
- 라우팅 경로가 AWS-TGW-T1 또는 AWS-TGW-T2를 통해 설정됨

### 3. 연결성 테스트
```bash
# On-Prem에서 실행
ping 169.254.224.53  # Tunnel 1 AWS 측
ping 169.254.96.197  # Tunnel 2 AWS 측
ping 10.10.10.x      # Seoul VPC
ping 10.200.x.x      # 기존 서비스 VPC
```

---

## 📋 체크리스트

- [x] AWS VPN 터널 상태 확인: UP ✅
- [x] BGP 라우트 수신 확인: 14개 ✅
- [x] PSK 일치 확인: 일치 ✅
- [x] Outside IP 일치 확인: 일치 ✅
- [x] Inside IP 일치 확인: 일치 ✅
- [ ] Fortigate BGP 이웃 상태 확인 (재확인 필요)
- [ ] Fortigate 라우팅 테이블 확인 (재확인 필요)
- [ ] 연결성 테스트 (On-Prem → AWS)

---

## 🎊 결론

**AWS 측 설정은 완벽하게 정상입니다.**

- ✅ 모든 파라미터 일치
- ✅ 터널 상태 UP
- ✅ BGP 라우트 수신 중 (14개)

**다음 단계:**
Fortigate에서 BGP 이웃 상태를 재확인하고, 라우팅 테이블에 AWS 라우트가 학습되었는지 확인하면 됩니다.

