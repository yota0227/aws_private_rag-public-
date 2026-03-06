# rag.corp.bos-semi.com 도메인 테스트 계획

## 배포 상태 확인 완료 ✅

### 생성된 리소스
- **Route53 Private Hosted Zone**: Z04599582HCRH2UPCSS34
- **DNS Record**: rag.corp.bos-semi.com → vpce-0e5f61dd7bd52882e-zlb2sxlo.execute-api.ap-northeast-2.vpce.amazonaws.com
- **API Gateway**: r0qa9lzhgi (Private type)
- **Lambda Function**: lambda-document-processor-seoul-prod
- **VPC Endpoint**: vpce-0e5f61dd7bd52882e (execute-api)

## 테스트 방법

### 1. DNS 조회 테스트 (온프렘 Fortigate에서)
```bash
# Private RAG VPC의 Route53 Resolver Inbound Endpoint로 조회
nslookup rag.corp.bos-semi.com 10.10.1.34
# 또는
dig @10.10.1.34 rag.corp.bos-semi.com

# 예상 결과:
# rag.corp.bos-semi.com. 300 IN A 10.10.x.x (VPC Endpoint의 Private IP)
```

### 2. API 호출 테스트 (온프렘 Fortigate에서)
```bash
# Health Check 엔드포인트
curl -k https://rag.corp.bos-semi.com/dev/rag/health

# 예상 결과:
# {"status": "healthy"}
```

### 3. Lambda 함수 테스트 (AWS Console에서)
```bash
# AWS Console → Lambda → lambda-document-processor-seoul-prod
# Test 탭에서 다음 payload로 테스트:
{
  "Records": [
    {
      "s3": {
        "bucket": {
          "name": "bos-ai-documents-seoul-v3"
        },
        "object": {
          "key": "test-document.pdf"
        }
      }
    }
  ]
}
```

## 주의사항
- Private API Gateway는 VPC Endpoint를 통해서만 접근 가능
- 온프렘에서는 VPN을 통해 Private RAG VPC(10.10.0.0/16)에 연결되어야 함
- Route53 Resolver Inbound Endpoint (10.10.1.34, 10.10.2.144)를 통해 DNS 조회
- API 호출 시 Host 헤더는 자동으로 VPC Endpoint DNS로 변환됨

## 다음 단계
1. 온프렘에서 DNS 조회 테스트
2. API 호출 테스트
3. Lambda 함수 테스트
4. S3 업로드 → Lambda 트리거 → Bedrock KB 동기화 테스트
