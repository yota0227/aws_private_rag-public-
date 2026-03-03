# VPN 및 Transit Gateway 연결성 분석

작성일: 2026-02-26

## 현재 상황

### 문제 증상
- On-Premises에서 VPN으로의 트래픽이 없음
- Seoul VPC와 VPN Gateway 간의 연결이 끊어진 것으로 보임

### 원인 분석

#### 1. 현재 네트워크 구조

```
On-Premises (192.128.0.0/16)
        │
        │ VPN
        ▼
Seoul VPC (10.10.0.0/16)
        │
        │ VPC Peering
        ▼
US VPC (10.20.0.0/16)
```

**문제점**: Seoul VPC에 VPN Gateway만 있고, **Transit Gateway (TGW)가 없음**

#### 2. 현재 배포된 리소스

**Network Layer (main.tf 분석)**:
- ✅ Seoul VPC: `vpc-0f759f00e5df658d1` (10.10.0.0/16)
- ✅ US VPC: `bos-ai-us-vpc-prod` (10.20.0.0/16)
- ✅ VPC Peering: Seoul ↔ US
- ✅ VPN Gateway: Seoul VPC에 연결
- ❌ **Transit Gateway: 없음**

#### 3. 왜 Transit Gateway가 필요한가?

현재 요구사항:
- **2개의 Seoul VPC가 있음**:
  1. 기존 서비스 VPC: `vpc-066c464f9c750ee9e` (10.200.0.0/16)
  2. BOS-AI VPC: `vpc-0f759f00e5df658d1` (10.10.0.0/16)

- **VPN 연결 요구사항**:
  - On-Premises → 기존 서비스 VPC (10.200.0.0/16)
  - On-Premises → BOS-AI VPC (10.10.0.0/16)
  - On-Premises → US VPC (10.20.0.0/16) via Seoul VPC

**VPN Gateway의 한계**:
- VPN Gateway는 **1개의 VPC에만 연결 가능**
- 현재 VPN Gateway는 BOS-AI VPC (10.10.0.0/16)에만 연결됨
- 기존 서비스 VPC (10.200.0.0/16)는 VPN Gateway가 없음

**Transit Gateway의 필요성**:
- Transit Gateway는 **여러 VPC를 중앙에서 관리**
- 1개의 TGW에 여러 VPC 연결 가능
- VPN 연결도 TGW에 연결 가능
- 모든 VPC 간 통신을 TGW를 통해 라우팅

## 올바른 네트워크 구조

### 현재 (잘못된) 구조
```
On-Premises
    │
    │ VPN
    ▼
VPN Gateway (Seoul VPC에만 연결)
    │
    ├─ Seoul VPC (10.10.0.0/16) ✅ 연결됨
    │
    └─ US VPC (10.20.0.0/16) via VPC Peering ✅ 연결됨

기존 서비스 VPC (10.200.0.0/16) ❌ 연결 안 됨
```

### 올바른 구조 (Transit Gateway 사용)
```
On-Premises
    │
    │ VPN
    ▼
Transit Gateway (중앙 허브)
    │
    ├─ VPN Attachment
    │
    ├─ Seoul VPC (10.10.0.0/16) Attachment
    │
    ├─ US VPC (10.20.0.0/16) Attachment
    │
    └─ 기존 서비스 VPC (10.200.0.0/16) Attachment
```

## 문제 진단

### 1. VPN Gateway 라우팅 확인

**Seoul VPC의 Route Table**:
- VPN Gateway 라우팅이 설정되어 있는가?
- 192.128.0.0/16 (On-Premises) → VPN Gateway로 라우팅되는가?

**확인 방법**:
```bash
# Seoul VPC의 Private Route Table 확인
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=vpc-0f759f00e5df658d1" \
  --region ap-northeast-2
```

### 2. VPN Gateway 상태 확인

**VPN Gateway 상태**:
- VPN Gateway가 정상 상태인가?
- VPN Connection이 정상 상태인가?

**확인 방법**:
```bash
# VPN Gateway 상태 확인
aws ec2 describe-vpn-gateways \
  --region ap-northeast-2

# VPN Connection 상태 확인
aws ec2 describe-vpn-connections \
  --region ap-northeast-2
```

### 3. VPN Gateway Route Propagation 확인

**Route Propagation 설정**:
- VPN Gateway Route Propagation이 활성화되어 있는가?
- Route Table에 VPN 라우트가 자동으로 추가되는가?

**확인 방법**:
```bash
# Route Propagation 상태 확인
aws ec2 describe-vpn-gateway-route-propagations \
  --region ap-northeast-2
```

## 해결 방안

### Option 1: Transit Gateway 도입 (권장)

**장점**:
- 여러 VPC를 중앙에서 관리
- 확장성 우수 (향후 VPC 추가 용이)
- 기존 서비스 VPC도 연결 가능
- 더 나은 라우팅 제어

**단점**:
- 추가 비용 (TGW 시간당 요금)
- 구현 복잡도 증가

**구현 단계**:
1. Transit Gateway 생성
2. VPN Attachment 생성
3. Seoul VPC Attachment 생성
4. US VPC Attachment 생성
5. 기존 서비스 VPC Attachment 생성 (선택)
6. Route Table 업데이트
7. VPN 연결 테스트

### Option 2: VPN Gateway 유지 + 기존 VPC 별도 관리

**장점**:
- 비용 절감
- 구현 간단

**단점**:
- 기존 서비스 VPC는 별도 VPN Gateway 필요
- 관리 복잡도 증가
- 확장성 제한

**구현 단계**:
1. 기존 서비스 VPC에 별도 VPN Gateway 생성
2. VPN Connection 추가 설정
3. Route Table 업데이트

## 권장 사항

**Transit Gateway 도입을 강력히 권장합니다.**

이유:
1. **현재 요구사항 충족**:
   - 2개의 Seoul VPC 모두 VPN 연결 가능
   - US VPC도 VPN을 통해 접근 가능

2. **향후 확장성**:
   - 새로운 VPC 추가 시 TGW에만 연결하면 됨
   - 모든 VPC 간 통신 자동으로 가능

3. **관리 용이성**:
   - 중앙 집중식 라우팅 관리
   - 정책 기반 라우팅 가능

4. **비용 효율성**:
   - 여러 VPN Gateway 대신 1개 TGW 사용
   - 장기적으로 비용 절감

## 다음 단계

### 즉시 확인 필요
1. ✅ VPN Gateway 상태 확인
2. ✅ Route Table 라우팅 확인
3. ✅ VPN Connection 상태 확인
4. ✅ Route Propagation 설정 확인

### 구현 필요
1. ⏳ Transit Gateway 생성
2. ⏳ VPN Attachment 생성
3. ⏳ VPC Attachments 생성
4. ⏳ Route Table 업데이트
5. ⏳ VPN 연결 테스트

## 참고 자료

### AWS 문서
- [Transit Gateway 개요](https://docs.aws.amazon.com/vpc/latest/tgw/)
- [VPN Gateway vs Transit Gateway](https://docs.aws.amazon.com/vpc/latest/privatelink/vpn-gateway-vs-transit-gateway.html)
- [Transit Gateway 라우팅](https://docs.aws.amazon.com/vpc/latest/tgw/tgw-route-tables.html)

### 현재 코드 위치
- Network Layer: `environments/network-layer/main.tf`
- VPN Gateway 설정: `environments/network-layer/main.tf` (라인 ~130)
- Route Propagation: `environments/network-layer/main.tf` (라인 ~160)

## 주의사항

- Transit Gateway 도입 시 기존 VPN Gateway와의 충돌 가능성 확인 필요
- Route Table 업데이트 시 기존 라우팅 규칙 검토 필요
- VPN 연결 테스트 후 프로덕션 적용
