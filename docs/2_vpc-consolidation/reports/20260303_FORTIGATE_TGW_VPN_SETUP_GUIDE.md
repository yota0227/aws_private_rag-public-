# Fortigate에서 AWS TGW VPN 설정 가이드

작성일: 2026-03-03
VPN Connection ID: vpn-0b2b65e9414092369
Transit Gateway ID: tgw-0897383168475b532

---

## 📋 AWS 설정 정보

### VPN 기본 정보
- **VPN Connection ID**: vpn-0b2b65e9414092369
- **Transit Gateway ID**: tgw-0897383168475b532
- **Customer Gateway ID**: cgw-00d18a496243b5184
- **On-Prem Public IP**: 211.170.236.130
- **On-Prem BGP ASN**: 65000

---

## 🔐 Tunnel 1 설정

### AWS 측 정보
| 항목 | 값 |
|------|-----|
| **AWS Public IP** | 3.38.69.188 |
| **AWS Tunnel Inside IP** | 169.254.224.53/30 |
| **AWS BGP ASN** | 64512 |
| **Pre-Shared Key** | `5RXxu5CEtzBY7bXGCP5YCN9smfYM00OP` |

### On-Prem 측 정보
| 항목 | 값 |
|------|-----|
| **On-Prem Public IP** | 211.170.236.130 |
| **On-Prem Tunnel Inside IP** | 169.254.224.54/30 |
| **On-Prem BGP ASN** | 65000 |

### IKE Phase 1 설정
```
Authentication Protocol: SHA1
Encryption Protocol: AES-128-CBC
Lifetime: 28800 seconds (8 hours)
Perfect Forward Secrecy: Group 2 (DH Group 2)
Mode: Main
Pre-Shared Key: 5RXxu5CEtzBY7bXGCP5YCN9smfYM00OP
```

### IPsec Phase 2 설정
```
Protocol: ESP
Authentication Protocol: HMAC-SHA1-96
Encryption Protocol: AES-128-CBC
Lifetime: 3600 seconds (1 hour)
Perfect Forward Secrecy: Group 2 (DH Group 2)
Mode: Tunnel
TCP MSS Adjustment: 1379
Dead Peer Detection:
  - Interval: 10 seconds
  - Retries: 3
```

---

## 🔐 Tunnel 2 설정

### AWS 측 정보
| 항목 | 값 |
|------|-----|
| **AWS Public IP** | 43.200.222.199 |
| **AWS Tunnel Inside IP** | 169.254.96.197/30 |
| **AWS BGP ASN** | 64512 |
| **Pre-Shared Key** | `pCgEtv28JG7mUDagkyRgqyclLSf7pyyf` |

### On-Prem 측 정보
| 항목 | 값 |
|------|-----|
| **On-Prem Public IP** | 211.170.236.130 |
| **On-Prem Tunnel Inside IP** | 169.254.96.198/30 |
| **On-Prem BGP ASN** | 65000 |

### IKE Phase 1 설정
```
Authentication Protocol: SHA1
Encryption Protocol: AES-128-CBC
Lifetime: 28800 seconds (8 hours)
Perfect Forward Secrecy: Group 2 (DH Group 2)
Mode: Main
Pre-Shared Key: pCgEtv28JG7mUDagkyRgqyclLSf7pyyf
```

### IPsec Phase 2 설정
```
Protocol: ESP
Authentication Protocol: HMAC-SHA1-96
Encryption Protocol: AES-128-CBC
Lifetime: 3600 seconds (1 hour)
Perfect Forward Secrecy: Group 2 (DH Group 2)
Mode: Tunnel
TCP MSS Adjustment: 1379
Dead Peer Detection:
  - Interval: 10 seconds
  - Retries: 3
```

---

## 🔧 Fortigate CLI 설정 명령어

### Tunnel 1 설정

```bash
# Phase 1 설정
config vpn ipsec phase1-interface
    edit "AWS-TGW-T1"
        set interface "wan1"
        set peertype any
        set peer 3.38.69.188
        set net-device enable
        set proposal aes128-sha1
        set comments "AWS TGW Tunnel 1"
        set dhgrp 2
        set lifetime 28800
        set authentication-method pre-shared-key
        set pre-shared-key "5RXxu5CEtzBY7bXGCP5YCN9smfYM00OP"
        set dpd on-idle
        set dpd-retrycount 3
        set dpd-retryinterval 10
    next
end

# Phase 2 설정
config vpn ipsec phase2-interface
    edit "AWS-TGW-T1-P2"
        set phase1name "AWS-TGW-T1"
        set proposal aes128-sha1
        set pfs group2
        set replay disable
        set keylifeseconds 3600
        set comments "AWS TGW Tunnel 1 Phase 2"
    next
end

# VPN Interface 설정
config system interface
    edit "AWS-TGW-T1"
        set vdom "root"
        set ip 169.254.224.54 255.255.255.252
        set type tunnel
        set tunnel-type ipsec
        set remote-ip 169.254.224.53
        set interface "AWS-TGW-T1"
    next
end
```

### Tunnel 2 설정

```bash
# Phase 1 설정
config vpn ipsec phase1-interface
    edit "AWS-TGW-T2"
        set interface "wan1"
        set peertype any
        set peer 43.200.222.199
        set net-device enable
        set proposal aes128-sha1
        set comments "AWS TGW Tunnel 2"
        set dhgrp 2
        set lifetime 28800
        set authentication-method pre-shared-key
        set pre-shared-key "pCgEtv28JG7mUDagkyRgqyclLSf7pyyf"
        set dpd on-idle
        set dpd-retrycount 3
        set dpd-retryinterval 10
    next
end

# Phase 2 설정
config vpn ipsec phase2-interface
    edit "AWS-TGW-T2-P2"
        set phase1name "AWS-TGW-T2"
        set proposal aes128-sha1
        set pfs group2
        set replay disable
        set keylifeseconds 3600
        set comments "AWS TGW Tunnel 2 Phase 2"
    next
end

# VPN Interface 설정
config system interface
    edit "AWS-TGW-T2"
        set vdom "root"
        set ip 169.254.96.198 255.255.255.252
        set type tunnel
        set tunnel-type ipsec
        set remote-ip 169.254.96.197
        set interface "AWS-TGW-T2"
    next
end
```

### BGP 설정

```bash
# BGP 라우터 설정
config router bgp
    set as 65000
    set router-id 211.170.236.130
    
    # Tunnel 1 Neighbor
    config neighbor
        edit "169.254.224.53"
            set remote-as 64512
            set holdtime-timer 30
            set keepalive-timer 10
        next
    end
    
    # Tunnel 2 Neighbor
    config neighbor
        edit "169.254.96.197"
            set remote-as 64512
            set holdtime-timer 30
            set keepalive-timer 10
        next
    end
    
    # Redistribute connected routes
    config redistribute "connected"
        set status enable
    end
end
```

### 방화벽 정책 설정

```bash
# AWS로 향하는 트래픽 허용
config firewall policy
    edit 1
        set name "Allow-to-AWS-TGW"
        set srcintf "internal"
        set dstintf "AWS-TGW-T1" "AWS-TGW-T2"
        set srcaddr "all"
        set dstaddr "all"
        set action accept
        set schedule "always"
        set service "ALL"
        set logtraffic all
    next
end

# AWS에서 들어오는 트래픽 허용
config firewall policy
    edit 2
        set name "Allow-from-AWS-TGW"
        set srcintf "AWS-TGW-T1" "AWS-TGW-T2"
        set dstintf "internal"
        set srcaddr "all"
        set dstaddr "all"
        set action accept
        set schedule "always"
        set service "ALL"
        set logtraffic all
    next
end
```

---

## ✅ 검증 단계

### 1. IPsec 터널 상태 확인
```bash
# Fortigate CLI에서
diagnose vpn ipsec status

# 예상 출력:
# vd: root/0
# name: AWS-TGW-T1
# version: 1
# interface: wan1 3
# addr: 211.170.236.130 -> 3.38.69.188
# created: 1234567890
# IKE SA: created 1/1
# IPsec SA: created 1/1
```

### 2. BGP 상태 확인
```bash
# Fortigate CLI에서
get router info bgp summary

# 예상 출력:
# BGP router identifier 211.170.236.130, local AS number 65000
# Neighbor        V    AS MsgRcvd MsgSent   TblVer  InQ OutQ Up/Down  State/PfxRcd
# 169.254.224.53  4 64512    100    100        5    0    0 00:10:00        4
# 169.254.96.197  4 64512    100    100        5    0    0 00:10:00        4
```

### 3. AWS 콘솔에서 확인
```bash
# AWS CLI에서
aws ec2 describe-vpn-connections \
  --vpn-connection-ids vpn-0b2b65e9414092369 \
  --region ap-northeast-2

# 예상 상태:
# Status: UP (양쪽 터널)
# AcceptedRouteCount: 4 (각 터널당)
```

### 4. 라우팅 테이블 확인
```bash
# Fortigate CLI에서
get router info routing-table all

# AWS에서 학습한 라우트가 보여야 함
```

---

## 🔍 트러블슈팅

### 터널이 UP되지 않는 경우

1. **Pre-Shared Key 확인**
   - 양쪽 PSK가 정확히 일치하는지 확인
   - 특수문자 확인

2. **Public IP 확인**
   - On-Prem Public IP: 211.170.236.130
   - AWS Tunnel 1: 3.38.69.188
   - AWS Tunnel 2: 43.200.222.199

3. **방화벽 규칙 확인**
   - UDP 500 (IKE) 허용
   - UDP 4500 (IPsec NAT-T) 허용
   - ESP (Protocol 50) 허용

4. **로그 확인**
   ```bash
   diagnose debug application ike -1
   diagnose debug application ipsec -1
   ```

### BGP 이웃이 연결되지 않는 경우

1. **Tunnel Inside IP 확인**
   - Tunnel 1: 169.254.224.54/30 ↔ 169.254.224.53/30
   - Tunnel 2: 169.254.96.198/30 ↔ 169.254.96.197/30

2. **BGP ASN 확인**
   - On-Prem: 65000
   - AWS: 64512

3. **BGP 로그 확인**
   ```bash
   diagnose debug application bgpd -1
   ```

---

## 📝 체크리스트

- [ ] Tunnel 1 Phase 1 설정 완료
- [ ] Tunnel 1 Phase 2 설정 완료
- [ ] Tunnel 1 VPN Interface 설정 완료
- [ ] Tunnel 2 Phase 1 설정 완료
- [ ] Tunnel 2 Phase 2 설정 완료
- [ ] Tunnel 2 VPN Interface 설정 완료
- [ ] BGP 설정 완료
- [ ] 방화벽 정책 설정 완료
- [ ] IPsec 터널 상태 확인 (UP)
- [ ] BGP 이웃 상태 확인 (Established)
- [ ] AWS 콘솔에서 VPN 상태 확인 (UP)
- [ ] 라우팅 테이블 확인 (AWS 라우트 학습됨)
- [ ] 연결성 테스트 (Ping 테스트)

---

## 📞 참고 정보

- **AWS VPN Connection**: vpn-0b2b65e9414092369
- **Transit Gateway**: tgw-0897383168475b532
- **Customer Gateway**: cgw-00d18a496243b5184
- **AWS Region**: ap-northeast-2 (Seoul)

