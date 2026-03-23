# VPN 마이그레이션 완료 보고서
작성일: 2026-03-23
작업자: seungil.woo
상태: 완료

---

## 1. 작업 개요

기존 VGW(Virtual Private Gateway) 기반 VPN을 TGW(Transit Gateway) 기반 VPN으로 완전 전환하고,
Logging VPC의 TGW 연결을 복구하여 전체 네트워크 현행화를 완료하였습니다.

---

## 2. 변경 전/후 비교

### VPN 구성

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| VPN 방식 | VGW (Virtual Private Gateway) | TGW (Transit Gateway) |
| 터널 수 | 4개 (AWS-T1/T2 VGW, AWS-TGW-T1/T2) | 2개 (AWS-TGW-T1/T2) |
| BGP 상태 | T2 미연결 | T1/T2 모두 Established |
| BGP 경로 수신 | 일부 | 12개 경로 |
| Fortigate Phase1 | AWS-T1, AWS-T2, AWS-TGW-T1, AWS-TGW-T2 | AWS-TGW-T1, AWS-TGW-T2 |

### Logging VPC 라우팅

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 라우팅 방식 | VGW propagation | TGW static route |
| OnPrem 경로 | 192.128.0.0/16 via VGW | 192.128.0.0/16 via TGW |
| TGW Attachment | 서브넷 없음 | subnet-0f027e9de8e26c18f, subnet-0625d992edf151017 |
| OnPrem 연결성 | 불가 | ping 성공 (0% 손실, 8-22ms) |

---

## 3. 수행 작업 상세

### TASK 4: VPN 터널 수정 (AWS-TGW-T2 BGP 연결)
- 문제: AWS-TGW-T2 IPsec UP이지만 BGP 미연결
- 원인: Fortigate Phase 2 설정 (pfs disable, replay disable) - AWS와 협상 실패
- 수정: pfs enable, dhgrp 2, replay enable 설정 후 터널 리셋
- 결과: BGP Established, 12 BGP Routes 수신

### TASK 5: Logging VPC 라우팅 전환 (VGW to TGW)
- VGW propagation 비활성화 (rtb-078c8f8a00c2960f7, rtb-0446cd3e4c6a6f2ce)
- 192.128.0.0/16 to TGW static 라우트 추가
- 기존 VPN (vpn-0acd5eff60174538a, VGW) 삭제
- VGW (vgw-0d54d0b0af6515dec) detach

### TASK 6: Logging VPC TGW Attachment 서브넷 등록
- 문제: 기존 attachment (tgw-attach-027263ebc6158c1d1)에 서브넷 없음
- 해결: 기존 attachment 삭제 후 신규 생성
- 결과: tgw-attach-05eef146458df2e49 생성, 서브넷 2개 등록

### TASK 7: 기존 VPN/VGW 완전 삭제
- VPN (vpn-04a1f8180ad2962ce) 삭제
- VGW (vgw-0d54d0b0af6515dec) 삭제

### TASK 8: Fortigate 정리
- AWS-T1, AWS-T2 Phase 1 삭제 완료
- AWS-TGW-T1, AWS-TGW-T2만 유지

### TASK 9: Terraform 현행화
- Logging VPC TGW attachment state 교체 (import)
  - 구: tgw-attach-027263ebc6158c1d1
  - 신: tgw-attach-05eef146458df2e49
- terraform apply 완료 (5 added, 30 changed, 0 destroyed)
  - 변경 내용: 태그 업데이트 (IGW, NAT GW, 서브넷, VPC, attachment)

---

## 4. 최종 검증 결과

### VPN 터널 상태
| 터널 | IP | 상태 | BGP |
|------|-----|------|-----|
| AWS-TGW-T1 | 3.38.69.188 | UP | 12 BGP ROUTES |
| AWS-TGW-T2 | 43.200.222.199 | UP | 12 BGP ROUTES |

### TGW Attachment 상태
| Attachment ID | VPC | 상태 | 서브넷 수 |
|--------------|-----|------|--------|
| tgw-attach-05eef146458df2e49 | vpc-066c464f9c750ee9e (Logging) | available | 2 |
| tgw-attach-066855ae90345791b | vpc-0a118e1bf21d0c057 (Frontend) | available | 2 |

### TGW 라우팅 테이블 (tgw-rtb-06ab3b805ab879efb)
| 목적지 | 경로 | 타입 |
|--------|------|------|
| 10.10.0.0/16 | Frontend VPC | propagated |
| 10.200.0.0/16 | Logging VPC | propagated |
| 10.20.0.0/16 | Frontend VPC | static |
| 192.128.x.x/24 | VPN (OnPrem) | propagated |

### Logging VPC Private RT 라우팅
| 목적지 | 경로 |
|--------|------|
| 10.200.0.0/16 | local |
| 10.10.0.0/16 | TGW |
| 192.128.0.0/16 | TGW |
| 0.0.0.0/0 | NAT GW |

### CloudWatch 트래픽 (최근 24시간)
| 항목 | BytesIn | BytesOut |
|------|---------|----------|
| TGW 전체 | 5.7MB | - |
| Logging VPC Attachment | 1.09MB | 5.27MB |
| VPN Attachment | 5.27MB | 1.09MB |

OnPrem - Logging VPC 간 트래픽 정상 흐름 확인.

---

## 5. 현재 네트워크 아키텍처

```
OnPrem (192.128.0.0/16)
    |
    | IPsec VPN (TGW-T1/T2, BGP)
    |
    v
Transit Gateway (tgw-0897383168475b532)
    |-- Logging VPC (10.200.0.0/16)  tgw-attach-05eef146458df2e49
    |-- Frontend VPC (10.10.0.0/16)  tgw-attach-066855ae90345791b
    +-- VPN Attachment               tgw-attach-025c13761b6d6338d

Frontend VPC <-> US Backend VPC (10.20.0.0/16) [VPC Peering: pcx-0a44f0b90565313f7]
```

---

## 6. 비용 절감 요약 (TASK 1-2)

| 삭제 리소스 | 월 절감액 |
|------------|---------|
| OpenSearch Serverless x2 | ~$700 |
| Bedrock KB x2 | ~$200 |
| Aurora PostgreSQL x2 | ~$800 |
| ACM Private CA | ~$400 |
| EKS 클러스터 | ~$50 |
| 합계 | ~$2,150/월 |

---

## 7. 잔여 이슈

- rtb-07af60b34e159cc04 (이름 없는 RT): main RT로 추정, 정리 검토
- Logging VPC NAT GW: 로그 파이프라인 용도로 현재 정상, 불필요 시 제거 검토
