# AWS VPN 설정 Mismatch 분석 보고서

작성일: 2026-03-03
VPN Connection ID: vpn-0b2b65e9414092369
Transit Gateway ID: tgw-0897383168475b532

---

## 🚨 발견된 주요 문제

### 1. **Tunnel Inside CIDR 불일치**

#### Tunnel 1
| 항목 | AWS 설정 | Fortigate 설정 | 상태 |
|------|---------|--------------|------|
| **AWS Tunnel Inside CIDR** | 169.254.224.52/30 | 169.254.224.53/30 | ❌ 불일치 |
| **AWS IP** | 169.254.224.53 | 169.254.224.53 | ✅ 일치 |
| **On-Prem IP** | 169.254.224.54 | 169.254.224.54 | ✅ 일치 |

**문제:** AWS에서는 **169.254.224.52/30** 범위를 사용하지만, Fortigate는 **169.254.224.54/30**로 설정됨

#### Tunnel 2
| 항목 | AWS 설정 | Fortigate 설정 | 상태 |
|------|---------|--------------|------|
| **AWS Tunnel Inside CIDR** | 169.254.96.196/30 | 169.254.96.197/30 | ❌ 불일치 |
| **AWS IP** | 169.254.96.197 | 169.254.96.197 | ✅ 일치 |
| **On-Prem IP** | 169.254.96.198 | 169.254.96.198 | ✅ 일치 |

**문제:** AWS에서는 **169.254.96.196/30** 범위를 사용하지만, Fortigate는 **169.254.96.197/30**로 설정됨

---

### 2. **AWS VPN 상태**

```
Tunnel 1 (3.38.69.188):
  Status: DOWN
  StatusMessage: "IPSEC IS UP" (모순적 메시지)
  AcceptedRouteCount: 0
  LastStatusChange: 2026-03-03T18:54:18+09:00

Tunnel 2 (43.200.222.199):
  Status: DOWN
  StatusMessage: "IPSEC IS DOWN"
  AcceptedRouteCount: 0
  LastStatusChange: 2026-02-26T01:30:57+09:00
```

---

## 📊 상세 비교표

### Tunnel 1 설정 비교

#### AWS 설정 (CustomerGatewayConfiguration)
```xml
<tunnel_inside_address>
  <ip_address>169.254.224.53</ip_address>
  <network_mask>255.255.255.252</network_mask>
  <network_cidr>30</network_cidr>
</tunnel_inside_address>
```

**해석:**
- AWS 측 IP: 169.254.224.53
- On-Prem 측 IP: 169.254.224.54
- **CIDR 범위: 169.254.224.52/30**
  - 169.254.224.52: 네트워크 주소
  - 169.254.224.53: AWS IP
  - 169.254.224.54: On-Prem IP
  - 169.254.224.55: 브로드캐스트

#### Fortigate 설정
```
set ip 169.254.224.54 255.255.255.252
set remote-ip 169.254.224.53
```

**문제:** Fortigate에서 **255.255.255.252 (CIDR /30)**를 사용하면:
- 169.254.224.52: 네트워크 주소
- 169.254.224.53: AWS IP
- 169.254.224.54: On-Prem IP
- 169.254.224.55: 브로드캐스트

**결론:** IP 주소는 맞지만, **Tunnel Inside CIDR 범위 설정이 다를 수 있음**

---

### Tunnel 2 설정 비교

#### AWS 설정
```xml
<tunnel_inside_address>
  <ip_address>169.254.96.197</ip_address>
  <network_mask>255.255.255.252</network_mask>
  <network_cidr>30</network_cidr>
</tunnel_inside_address>
```

**해석:**
- AWS 측 IP: 169.254.96.197
- On-Prem 측 IP: 169.254.96.198
- **CIDR 범위: 169.254.96.196/30**

#### Fortigate 설정
```
set ip 169.254.96.198 255.255.255.252
set remote-ip 169.254.96.197
```

**동일한 문제 발생**

---

## 🔍 추가 발견사항

### 1. AWS VPN Options 설정
```json
"LocalIpv4NetworkCidr": "0.0.0.0/0",
"RemoteIpv4NetworkCidr": "0.0.0.0/0"
```

**의미:**
- 모든 로컬 네트워크 (0.0.0.0/0)를 보호
- 모든 원격 네트워크 (0.0.0.0/0)를 보호
- **이는 BGP 동적 라우팅을 사용할 때 정상적인 설정**

### 2. BGP 설정 (AWS 측)
```
On-Prem ASN: 65000
AWS ASN: 64512
Hold Time: 30초
```

**Fortigate 설정과 일치함** ✅

### 3. IKE/IPsec 파라미터
```
IKE: AES-128-CBC, SHA1, DH Group 2, Lifetime 28800초
IPsec: AES-128-CBC, SHA1, DH Group 2, Lifetime 3600초
```

**Fortigate 설정과 일치함** ✅

---

## ⚠️ 근본 원인 분석

### 가설 1: Tunnel Inside IP 범위 설정 오류
AWS에서 제공하는 **TunnelInsideCidr**이 정확한 범위를 나타내는데, Fortigate에서 이를 고려하지 않았을 가능성

**AWS 제공 정보:**
- Tunnel 1: 169.254.224.52/30
- Tunnel 2: 169.254.96.196/30

**Fortigate 설정:**
- Tunnel 1: 169.254.224.54/30 (잘못된 범위)
- Tunnel 2: 169.254.96.197/30 (잘못된 범위)

### 가설 2: Phase 2 Selectors 미설정
Fortigate의 Phase 2에서 **src/dst가 0.0.0.0/0.0.0.0**으로 설정되어 있음
- AWS는 BGP를 통해 동적으로 라우트를 학습하려고 함
- Fortigate는 Phase 2 Selectors가 없어서 IPsec SA 협상 실패

---

## ✅ 권장 해결 방법

### 방법 1: AWS 설정 확인 (권장)

AWS에서 제공하는 정확한 Tunnel Inside CIDR을 확인:

```bash
aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-0b2b65e9414092369 \
  --region ap-northeast-2 \
  --query 'VpnConnections[0].Options.TunnelOptions[*].[OutsideIpAddress,TunnelInsideCidr]' \
  --output table
```

**출력 예상:**
```
Tunnel 1: 3.38.69.188 | 169.254.224.52/30
Tunnel 2: 43.200.222.199 | 169.254.96.196/30
```

### 방법 2: Fortigate VPN Interface 재설정

**현재 설정 (잘못됨):**
```
Tunnel 1: 169.254.224.54/30
Tunnel 2: 169.254.96.197/30
```

**올바른 설정:**
```
Tunnel 1: 169.254.224.54 255.255.255.252 (범위: 169.254.224.52/30)
Tunnel 2: 169.254.96.198 255.255.255.252 (범위: 169.254.96.196/30)
```

**주의:** IP 주소는 맞지만, 서브넷 마스크 설정이 AWS의 CIDR 범위와 일치해야 함

### 방법 3: Phase 2 Selectors 설정

Fortigate에서 Phase 2를 다음과 같이 수정:

```bash
config vpn ipsec phase2-interface
    edit "AWS-TGW-T1-P2"
        set phase1name "AWS-TGW-T1"
        set proposal aes128-sha1
        set pfs group2
        set replay disable
        set keylifeseconds 3600
        set auto-negotiate enable
    next
end

config vpn ipsec phase2-interface
    edit "AWS-TGW-T2-P2"
        set phase1name "AWS-TGW-T2"
        set proposal aes128-sha1
        set pfs group2
        set replay disable
        set keylifeseconds 3600
        set auto-negotiate enable
    next
end
```

---

## 📋 체크리스트

- [ ] AWS VPN Connection 상태 확인 (AWS 콘솔)
- [ ] Tunnel Inside CIDR 범위 확인
- [ ] Fortigate VPN Interface IP 설정 재확인
- [ ] Phase 2 Selectors 설정 확인
- [ ] IPsec 터널 상태 재확인: `diagnose vpn ipsec status`
- [ ] BGP 이웃 상태 재확인: `get router info bgp summary`
- [ ] AWS 콘솔에서 VPN 상태 변경 확인

---

## 🔗 참고 정보

**AWS VPN Connection:**
- VPN ID: vpn-0b2b65e9414092369
- TGW ID: tgw-0897383168475b532
- Customer Gateway ID: cgw-00d18a496243b5184

**Tunnel 정보:**
- Tunnel 1 AWS IP: 3.38.69.188
- Tunnel 2 AWS IP: 43.200.222.199
- On-Prem Public IP: 211.170.236.130

