# 사내 DNS 조건부 포워딩 설정 가이드

## 개요

Private RAG API(rag.corp.bos-semi.com)에 온프렘에서 접근하기 위해, 사내 DNS 서버에 **조건부 포워딩**을 설정한다.

**핵심 원칙:** `*.corp.bos-semi.com` 도메인 쿼리만 Route53 Resolver로 전달하고, 나머지 도메인은 기존 DNS 해석 경로를 유지한다.

> ⚠️ **주의:** 이전에 Route53 Endpoint를 사내 DNS에 무조건 등록하여 SaaS 서비스(S3, DynamoDB 등) 파일 업로드 오류가 발생한 경험이 있음. 반드시 조건부 포워딩만 적용할 것.

## 사전 조건

- Route53 Resolver Inbound Endpoint가 Private RAG VPC(10.10.0.0/16)에 생성 완료
- Resolver Inbound IP 주소 확인 (Terraform output에서 확인)

```bash
# Terraform output으로 Resolver IP 확인
cd environments/network-layer
terraform output resolver_inbound_ip_addresses
```

## 설정 절차

### 1. Route53 Resolver Inbound IP 확인

Terraform 배포 후 할당된 IP 주소를 확인한다:
- AZ-a (10.10.1.0/24): `<resolver_ip_1>`
- AZ-c (10.10.2.0/24): `<resolver_ip_2>`

### 2. 사내 DNS 서버 조건부 포워딩 설정

**Windows DNS Server:**

```powershell
# 조건부 포워딩 추가
Add-DnsServerConditionalForwarderZone `
  -Name "corp.bos-semi.com" `
  -MasterServers <resolver_ip_1>,<resolver_ip_2> `
  -ReplicationScope "Forest"
```

**Linux BIND:**
```
# /etc/named.conf에 추가
zone "corp.bos-semi.com" {
    type forward;
    forward only;
    forwarders { <resolver_ip_1>; <resolver_ip_2>; };
};
```

### 3. 설정 후 검증

#### Step 1: RAG API DNS 해석 확인
```bash
nslookup rag.corp.bos-semi.com
# 기대 결과: VPC Endpoint의 Private IP (10.10.x.x) 반환
```

#### Step 2: 기존 SaaS 서비스 DNS 해석 확인 (최소 5개)
```bash
nslookup s3.amazonaws.com
nslookup dynamodb.ap-northeast-2.amazonaws.com
nslookup sqs.ap-northeast-2.amazonaws.com
nslookup sns.ap-northeast-2.amazonaws.com
nslookup sts.amazonaws.com
# 기대 결과: 모든 서비스가 기존 Public IP로 정상 해석
```

#### Step 3: RAG API 헬스체크
```bash
curl -k https://rag.corp.bos-semi.com/rag/health
# 기대 결과: HTTP 200 + 상태 정보 반환
```

#### Step 4: 기존 SaaS 서비스 기능 테스트
```bash
# S3 파일 업로드 테스트
aws s3 cp test.txt s3://existing-bucket/test.txt

# 기존 서비스 정상 동작 확인
```

## 롤백 절차

SaaS 서비스 DNS 해석 실패 시 즉시 실행:

**Windows DNS Server:**
```powershell
Remove-DnsServerConditionalForwarderZone -Name "corp.bos-semi.com" -Force
```

**Linux BIND:**
```bash
# /etc/named.conf에서 corp.bos-semi.com zone 블록 삭제
sudo systemctl restart named
```

**목표 롤백 시간: 1분 이내**

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| rag.corp.bos-semi.com 해석 실패 | Resolver IP 오류 또는 VPN 연결 문제 | Resolver IP 확인, VPN 상태 확인 |
| SaaS 서비스 DNS 해석 실패 | 조건부 포워딩이 아닌 전체 포워딩 설정됨 | 즉시 롤백, 조건부 포워딩만 재설정 |
| DNS 응답 지연 | Resolver Endpoint 과부하 | CloudWatch 메트릭 확인 |
