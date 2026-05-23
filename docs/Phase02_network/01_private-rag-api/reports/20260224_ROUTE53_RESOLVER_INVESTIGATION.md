# Route53 Resolver Endpoint 조사

**발견 사항:**
- Endpoint ID: `rslvr-in-5b3dfa84cbeb4e66a`
- 문서에 기록된 IP: 10.10.1.10, 10.10.2.10
- 테스트 결과: Ping 응답 없음

**문제:** Terraform 코드에 Route53 Resolver 정의가 없음!

---

## 🔍 의심 사항

### 1️⃣ Route53 Resolver가 수동으로 생성됨
- Terraform으로 관리되지 않음
- 실제 IP가 문서와 다를 수 있음

### 2️⃣ 실제 배포된 IP 확인 필요
```
문서: 10.10.1.10, 10.10.2.10
실제: ??? (확인 필요)
```

### 3️⃣ VPN 연결 상태 확인 필요
- VPN이 제대로 연결되어 있는가?
- Seoul VPC (10.10.0.0/16)에 접근 가능한가?

---

## ✅ 확인 방법

### Step 1: AWS Console에서 Route53 Resolver 확인

**URL:** https://console.aws.amazon.com/route53resolver/

**확인할 것:**
1. Region: **ap-northeast-2 (Seoul)** 선택
2. 좌측 메뉴: "Inbound endpoints" 클릭
3. 테이블에서 `rslvr-in-5b3dfa84cbeb4e66a` 찾기
4. **IP addresses** 확인 (실제 IP가 뭔지)
5. **Status** 확인 (Active인지)

**기록할 정보:**
```
Endpoint ID: rslvr-in-5b3dfa84cbeb4e66a
Status: [Active/Inactive]
IP Address 1: 10.10.?.?
IP Address 2: 10.10.?.?
Subnets: [어느 Subnet에 배포되었는가]
Security Group: [어느 SG가 적용되었는가]
```

### Step 2: VPN 연결 상태 확인

**URL:** https://console.aws.amazon.com/vpc/

**확인할 것:**
1. Region: **ap-northeast-2 (Seoul)** 선택
2. 좌측 메뉴: "VPN connections" 클릭
3. VPN 연결 상태 확인
4. Status: **Available** 인지 확인

### Step 3: Seoul VPC 확인

**URL:** https://console.aws.amazon.com/vpc/

**확인할 것:**
1. Region: **ap-northeast-2 (Seoul)** 선택
2. VPCs 확인
3. CIDR: 10.10.0.0/16 맞는지 확인
4. Subnets 확인
5. Route Tables 확인

### Step 4: Security Group 확인

**URL:** https://console.aws.amazon.com/ec2/

**확인할 것:**
1. Region: **ap-northeast-2 (Seoul)** 선택
2. Security Groups 검색
3. Route53 Resolver의 Security Group 찾기 (sg-02892b260ed8b09c4)
4. Inbound 규칙 확인:
   - TCP 53 from 10.0.0.0/8 허용?
   - UDP 53 from 10.0.0.0/8 허용?

---

## 🚀 다음 단계

### 즉시 확인 필요
1. **AWS Console에서 Route53 Resolver의 실제 IP 확인**
2. **그 IP로 Ping 테스트**
3. **VPN 연결 상태 확인**

### 만약 IP가 다르면
```bash
# 새로운 IP로 테스트
ping <실제 IP 1>
ping <실제 IP 2>

# DNS 쿼리 테스트
nslookup aws.internal <실제 IP>
```

### 만약 VPN이 연결되지 않았으면
- VPN 연결 상태 확인
- VPN 터널 재연결
- On-Premises VPN 클라이언트 확인

---

## 📝 기록

**조사 일시:** 2026-02-24  
**발견:** Terraform에 Route53 Resolver 정의 없음  
**다음 단계:** AWS Console에서 실제 IP 확인

