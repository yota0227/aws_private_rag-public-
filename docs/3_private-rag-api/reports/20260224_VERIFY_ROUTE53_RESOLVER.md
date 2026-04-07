# Route53 Resolver Endpoint 실제 IP 확인

**문제:** Ping 응답 없음 (10.10.1.20, 10.10.2.10)  
**원인 추정:** 문서의 IP와 실제 배포된 IP가 다를 가능성

---

## 🔍 확인해야 할 것들

### 1️⃣ 문서에 기록된 IP vs 실제 배포된 IP

**문서에 기록된 IP:**
```
Route53 Resolver Endpoint IPs: 10.10.1.10, 10.10.2.10
```

**실제 테스트 결과:**
```
ping 10.10.1.20 → 응답 없음 (타임아웃)
ping 10.10.2.10 → 요청 시간이 만료되었습니다 (100% 손실)
```

**의심 사항:**
- 10.10.1.20은 뭐지? (문서에는 10.10.1.10이라고 했는데)
- 실제 Endpoint IP가 다를 수 있음

---

## 🛠️ 확인 방법

### 방법 1: AWS Console에서 직접 확인 (가장 확실)

**Step 1: AWS Console 접속**
- https://console.aws.amazon.com/route53resolver/
- Region: **ap-northeast-2 (Seoul)** 선택

**Step 2: Inbound Endpoints 확인**
- 좌측 메뉴: "Inbound endpoints"
- 테이블에서 확인할 항목:
  - Endpoint ID
  - Status (Active인지 확인)
  - **IP addresses** ← 이것이 실제 IP!

**Step 3: 실제 IP 기록**
```
Endpoint ID: rslvr-in-XXXXXXXXX
Status: Active
IP Addresses:
  - 10.10.?.? (AZ: ap-northeast-2a)
  - 10.10.?.? (AZ: ap-northeast-2c)
```

---

### 방법 2: Terraform State에서 확인

**Step 1: Terraform State 파일 확인**
```bash
cd environments/network-layer
terraform state show module.route53_resolver
```

**Step 2: 출력 확인**
```
resource "aws_route53_resolver_endpoint" "inbound" {
  ...
  ip_addresses = [
    "10.10.?.?",
    "10.10.?.?"
  ]
  ...
}
```

---

### 방법 3: AWS CLI로 확인 (SSL 문제 해결 후)

```bash
# SSL 검증 비활성화 (테스트용)
aws route53resolver list-resolver-endpoints \
  --region ap-northeast-2 \
  --no-verify-ssl \
  --query 'ResolverEndpoints[*].[Id,Status,IpAddresses]'
```

---

## 📊 가능한 시나리오

### 시나리오 1: IP 주소 오류
```
문서: 10.10.1.10, 10.10.2.10
실제: 10.10.1.50, 10.10.2.50 (또는 다른 IP)

→ 해결: 문서 업데이트 + 테스트 재실행
```

### 시나리오 2: Endpoint 미배포
```
Route53 Resolver Endpoint가 아직 배포되지 않음

→ 해결: Terraform apply 실행
```

### 시나리오 3: VPN 연결 문제
```
VPN 터널이 제대로 연결되지 않음
→ 10.10.x.x 대역 자체에 접근 불가

→ 해결: VPN 연결 상태 확인
```

### 시나리오 4: Security Group 차단
```
Route53 Resolver의 Security Group이 On-Premises 트래픽 차단

→ 해결: Security Group 규칙 수정
```

---

## ✅ 확인 체크리스트

### AWS Console에서 확인할 것

**Route53 Resolver:**
- [ ] Inbound Endpoints 존재하는가?
- [ ] Status가 Active인가?
- [ ] IP Addresses가 표시되는가?
- [ ] 실제 IP는 뭔가?

**VPC:**
- [ ] Seoul VPC (10.10.0.0/16) 존재하는가?
- [ ] Private Subnets 존재하는가?
- [ ] Route53 Resolver가 어느 Subnet에 배포되었는가?

**Security Groups:**
- [ ] Route53 Resolver의 Security Group 확인
- [ ] Inbound 규칙: TCP/UDP 53 from 10.0.0.0/8 허용?
- [ ] Outbound 규칙: All traffic 허용?

**VPN:**
- [ ] VPN Connection 상태: Active?
- [ ] VPN Gateway 상태: Available?
- [ ] Route Propagation: Enabled?

---

## 🚀 다음 단계

### 1단계: 실제 IP 확인
**AWS Console에서 Route53 Resolver Endpoint의 실제 IP를 확인하세요.**

### 2단계: IP 업데이트
```bash
# 확인된 실제 IP로 테스트
ping <실제 IP 1>
ping <실제 IP 2>
```

### 3단계: 문서 업데이트
```bash
# 확인된 IP로 모든 문서 업데이트
# ROUTE53_RESOLVER_CONNECTIVITY_TEST.md
# PROJECT_PROGRESS_AND_GOALS.md
# 등등
```

### 4단계: 재테스트
```bash
# 올바른 IP로 다시 테스트
nslookup aws.internal <실제 IP>
```

---

## 📝 기록

**테스트 일시:** 2026-02-24  
**테스트 환경:** Windows (On-Premises)  
**테스트 결과:**
- ping 10.10.1.20 → 응답 없음
- ping 10.10.2.10 → 100% 손실

**다음 확인:** AWS Console에서 실제 Endpoint IP 확인

