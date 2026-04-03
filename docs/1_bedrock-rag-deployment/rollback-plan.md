# BOS-AI VPC 통합 마이그레이션 롤백 계획

## 📋 개요

본 문서는 BOS-AI VPC 통합 마이그레이션 프로젝트의 각 Phase별 롤백 절차를 정의합니다.

**롤백 원칙:**
- 각 Phase는 독립적으로 롤백 가능
- 롤백 시 기존 서비스 중단 최소화
- 모든 롤백 작업은 Terraform을 통해 수행
- 롤백 전 현재 상태 백업 필수

---

## 🔄 Phase별 롤백 절차

### Phase 1: 준비 및 사전 작업

**롤백 필요성:** 없음 (문서화 작업만 수행)

**롤백 절차:**
- 백업 파일 삭제 (선택사항)
- 문서 파일 삭제 (선택사항)

**영향도:** 없음

---

### Phase 2: VPC 네이밍 변경

**현재 상태:**
- VPC 태그 변경 완료 (vpc-bos-ai-seoul-prod-01)
- 서브넷, Route Table, NAT Gateway, IGW 태그 변경 완료

**롤백 트리거:**
- 태그 변경으로 인한 자동화 스크립트 오류
- 모니터링 시스템 연동 실패
- 운영팀 혼란

**롤백 절차:**

1. **Terraform 코드 복원**
```bash
cd environments/network-layer
git checkout HEAD~1 tag-updates.tf
```

2. **이전 태그로 복원**
```bash
terraform plan -out=rollback-phase2.tfplan
terraform apply rollback-phase2.tfplan
```

3. **변경 확인**
```bash
# VPC 태그 확인
aws ec2 describe-vpcs --vpc-ids vpc-066c464f9c750ee9e \
  --region ap-northeast-2 --query 'Vpcs[0].Tags'

# 서브넷 태그 확인
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --region ap-northeast-2 --query 'Subnets[*].Tags'
```

**예상 소요 시간:** 10분

**영향도:** 낮음 (태그만 변경, 기능 영향 없음)

**롤백 검증:**
- [ ] VPC 태그가 이전 값으로 복원됨
- [ ] 서브넷 태그가 이전 값으로 복원됨
- [ ] Route Table 태그가 이전 값으로 복원됨
- [ ] 기존 기능 정상 동작 확인

---

### Phase 3: VPC 엔드포인트 구성

**현재 상태:**
- 6개 VPC 엔드포인트 생성 완료
  - Bedrock Runtime
  - Bedrock Agent Runtime
  - Secrets Manager
  - CloudWatch Logs
  - S3 Gateway
  - Kinesis Firehose
- Security Group 생성 완료 (vpc-endpoints-bos-ai-seoul-prod)

**롤백 트리거:**
- VPC 엔드포인트 연결 실패
- Private DNS 해석 오류
- 비용 초과
- 성능 저하

**롤백 절차:**

1. **현재 상태 백업**
```bash
# VPC 엔드포인트 목록 백업
aws ec2 describe-vpc-endpoints \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  > backups/vpc-endpoints-before-rollback.json
```

2. **VPC 엔드포인트 삭제**
```bash
cd environments/network-layer

# Terraform으로 삭제
terraform destroy -target=module.vpc_endpoints -auto-approve

# 또는 AWS CLI로 직접 삭제
aws ec2 delete-vpc-endpoints \
  --vpc-endpoint-ids vpce-xxxxx vpce-yyyyy \
  --region ap-northeast-2
```

3. **Security Group 삭제**
```bash
# VPC 엔드포인트 SG 삭제
aws ec2 delete-security-group \
  --group-id sg-xxxxx \
  --region ap-northeast-2
```

4. **Terraform 코드 제거**
```bash
git checkout HEAD~1 vpc-endpoints.tf
terraform plan
terraform apply
```

**예상 소요 시간:** 15분

**영향도:** 중간
- VPC 엔드포인트를 통한 접근 불가
- 인터넷 게이트웨이/NAT 게이트웨이를 통한 접근으로 전환
- 약간의 지연시간 증가 가능

**롤백 검증:**
- [ ] VPC 엔드포인트 모두 삭제됨
- [ ] Security Group 삭제됨
- [ ] 기존 서비스 정상 동작 (IGW/NAT 통해)
- [ ] CloudWatch Logs 정상 수집
- [ ] Bedrock API 호출 정상

---

### Phase 4: OpenSearch Serverless 배포

**현재 상태:**
- OpenSearch Serverless 컬렉션 존재 (버지니아, 기존 배포)
- Collection ID: iw3pzcloa0en8d90hh7
- 인덱스: bedrock-knowledge-base-index

**롤백 트리거:**
- OpenSearch 연결 실패
- 인덱싱 오류
- 비용 초과
- 성능 문제

**롤백 절차:**

⚠️ **주의:** OpenSearch Serverless는 기존에 배포된 리소스이므로 삭제 시 데이터 손실 발생!

**롤백 옵션 1: 컬렉션 유지 (권장)**
- 컬렉션은 그대로 두고 접근 정책만 조정
- 데이터 보존

**롤백 옵션 2: 컬렉션 삭제 (비권장)**

1. **데이터 백업**
```bash
# 인덱스 데이터 백업 (스냅샷)
# OpenSearch Serverless는 자동 스냅샷 지원
```

2. **컬렉션 삭제**
```bash
aws opensearchserverless delete-collection \
  --id iw3pzcloa0en8d90hh7 \
  --region us-east-1
```

3. **액세스 정책 삭제**
```bash
aws opensearchserverless delete-access-policy \
  --name bos-ai-vectors-access-policy \
  --type data \
  --region us-east-1
```

**예상 소요 시간:** 20분

**영향도:** 높음
- RAG 시스템 전체 중단
- 벡터 데이터 손실 (백업 없을 시)
- Knowledge Base 동작 불가

**롤백 검증:**
- [ ] 컬렉션 삭제 확인 (옵션 2 선택 시)
- [ ] 또는 액세스 정책 조정 확인 (옵션 1)
- [ ] 기존 시스템 영향 확인

---

### Phase 5: Lambda 배포

**현재 상태:**
- Lambda 함수 존재 (버지니아, 기존 배포)
- 함수명: document-processor
- VPC: vpc-0ed37ff82027c088f (버지니아)

**롤백 트리거:**
- Lambda 실행 오류
- VPC 연결 실패
- 타임아웃 발생
- 비용 초과

**롤백 절차:**

⚠️ **주의:** Lambda는 기존 배포된 리소스

**롤백 옵션 1: 함수 유지, 설정만 복원**
```bash
# 이전 버전으로 롤백
aws lambda update-function-configuration \
  --function-name document-processor \
  --environment Variables={...이전값...} \
  --region us-east-1
```

**롤백 옵션 2: 함수 삭제 (비권장)**
```bash
aws lambda delete-function \
  --function-name document-processor \
  --region us-east-1
```

**예상 소요 시간:** 10분

**영향도:** 높음
- 문서 처리 파이프라인 중단
- S3 이벤트 처리 불가

**롤백 검증:**
- [ ] Lambda 설정 복원 확인
- [ ] 테스트 실행 성공
- [ ] CloudWatch Logs 정상

---

### Phase 6: Bedrock Knowledge Base 설정

**현재 상태:**
- Knowledge Base 존재 (버지니아, 기존 배포)
- KB ID: FNNOP3VBZV
- Data Source ID: 211WMHQAOK

**롤백 트리거:**
- Knowledge Base 쿼리 실패
- 동기화 오류
- 비용 초과

**롤백 절차:**

⚠️ **주의:** Knowledge Base는 기존 배포된 리소스

**롤백 옵션 1: 설정만 복원**
```bash
# Data Source 설정 복원
aws bedrock-agent update-data-source \
  --knowledge-base-id FNNOP3VBZV \
  --data-source-id 211WMHQAOK \
  --data-source-configuration '...' \
  --region us-east-1
```

**롤백 옵션 2: Knowledge Base 삭제 (비권장)**
```bash
# Data Source 삭제
aws bedrock-agent delete-data-source \
  --knowledge-base-id FNNOP3VBZV \
  --data-source-id 211WMHQAOK \
  --region us-east-1

# Knowledge Base 삭제
aws bedrock-agent delete-knowledge-base \
  --knowledge-base-id FNNOP3VBZV \
  --region us-east-1
```

**예상 소요 시간:** 15분

**영향도:** 높음
- RAG 쿼리 불가
- 챗봇 서비스 중단

**롤백 검증:**
- [ ] Knowledge Base 설정 복원
- [ ] 쿼리 테스트 성공
- [ ] 동기화 정상 동작

---

### Phase 7: VPC 피어링 구성

**현재 상태:**
- VPC Peering 생성 완료
- Peering ID: pcx-06599e9d9a3fe573f
- 서울 (vpc-066c464f9c750ee9e) ↔ 버지니아 (vpc-0ed37ff82027c088f)
- 라우팅 테이블 업데이트 완료

**롤백 트리거:**
- 피어링 연결 실패
- 라우팅 충돌
- 보안 정책 위반
- 비용 초과

**롤백 절차:**

1. **현재 상태 백업**
```bash
# 피어링 정보 백업
aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids pcx-06599e9d9a3fe573f \
  --region ap-northeast-2 \
  > backups/vpc-peering-before-rollback.json

# 라우팅 테이블 백업
aws ec2 describe-route-tables \
  --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  > backups/route-tables-seoul-before-rollback.json
```

2. **라우팅 테이블에서 피어링 경로 삭제**
```bash
# 서울 Private Route Table
aws ec2 delete-route \
  --route-table-id rtb-078c8f8a00c2960f7 \
  --destination-cidr-block 10.20.0.0/16 \
  --region ap-northeast-2

# 버지니아 Private Route Tables (3개)
aws ec2 delete-route \
  --route-table-id rtb-xxxxx \
  --destination-cidr-block 10.200.0.0/16 \
  --region us-east-1
```

3. **VPC Peering Connection 삭제**
```bash
aws ec2 delete-vpc-peering-connection \
  --vpc-peering-connection-id pcx-06599e9d9a3fe573f \
  --region ap-northeast-2
```

4. **Terraform 코드 제거**
```bash
cd environments/network-layer
git checkout HEAD~1 peering.tf
terraform plan
terraform apply
```

**예상 소요 시간:** 10분

**영향도:** 중간
- 서울 ↔ 버지니아 직접 통신 불가
- 인터넷을 통한 통신으로 전환
- 지연시간 증가
- 비용 증가 (NAT Gateway 사용)

**롤백 검증:**
- [ ] VPC Peering 삭제됨
- [ ] 라우팅 테이블에서 피어링 경로 제거됨
- [ ] 기존 서비스 정상 동작 (인터넷 경유)
- [ ] 지연시간 측정

---

### Phase 8: 통합 테스트

**롤백 필요성:** 없음 (테스트만 수행)

**롤백 절차:**
- 테스트 데이터 삭제
- 테스트 리소스 정리

**영향도:** 없음

---

### Phase 9: 기존 VPC 제거

**현재 상태:**
- 기존 BOS-AI-RAG VPC 존재 (vpc-0f759f00e5df658d1)
- 아직 삭제 안 됨

**롤백 트리거:**
- 실수로 잘못된 VPC 삭제
- 필요한 리소스 발견

**롤백 절차:**

⚠️ **주의:** VPC 삭제는 되돌릴 수 없음!

**예방 조치:**
1. 삭제 전 모든 리소스 확인
2. 24시간 모니터링 후 삭제
3. 백업 확인

**롤백 불가:** VPC 삭제 후에는 재생성 필요

**재생성 절차:**
```bash
# Terraform 코드로 재생성
cd environments/network-layer
terraform plan -out=recreate-vpc.tfplan
terraform apply recreate-vpc.tfplan
```

**예상 소요 시간:** 30분

**영향도:** 높음 (잘못 삭제 시)

---

### Phase 10: 모니터링 및 문서화

**롤백 필요성:** 없음 (문서화 및 모니터링 설정)

**롤백 절차:**
- CloudWatch 알람 삭제
- Dashboard 삭제
- 문서 삭제

**영향도:** 낮음

---

## 🚨 롤백 트리거 조건

### 자동 롤백 트리거

다음 조건 발생 시 즉시 롤백 고려:

1. **서비스 중단**
   - 기존 서비스 5분 이상 중단
   - API 응답률 95% 미만
   - 에러율 5% 초과

2. **성능 저하**
   - 응답 시간 2배 이상 증가
   - Lambda 타임아웃 10% 초과
   - VPC 피어링 지연시간 200ms 초과

3. **비용 초과**
   - 일일 비용 예상치 150% 초과
   - VPC 엔드포인트 비용 $100/일 초과

4. **보안 이슈**
   - 보안 그룹 규칙 위반 감지
   - 비인가 접근 시도 감지
   - 데이터 유출 의심

### 수동 롤백 트리거

다음 조건 발생 시 팀 논의 후 롤백:

1. **운영 이슈**
   - 운영팀 교육 부족
   - 모니터링 도구 연동 실패
   - 문서 부족

2. **기술 부채**
   - 예상치 못한 복잡도 증가
   - 유지보수 어려움
   - 기술 스택 불일치

---

## 📞 긴급 연락망

### 롤백 승인 권한

| 역할 | 이름 | 연락처 | 승인 권한 |
|------|------|--------|-----------|
| 프로젝트 리더 | [이름] | [전화번호] | 전체 Phase |
| 인프라 담당 | [이름] | [전화번호] | Phase 1-7 |
| 개발 담당 | [이름] | [전화번호] | Phase 5-6 |
| 보안 담당 | [이름] | [전화번호] | 보안 관련 |

### 에스컬레이션 절차

1. **Level 1 (0-15분):** 담당 엔지니어 판단
2. **Level 2 (15-30분):** 팀 리더 승인
3. **Level 3 (30분+):** 프로젝트 리더 승인

### 긴급 연락 순서

1. Slack 채널: #bos-ai-infra-emergency
2. 전화: 담당자 직통
3. 이메일: team@example.com

---

## 📝 롤백 체크리스트

### 롤백 전

- [ ] 현재 상태 백업 완료
- [ ] 롤백 사유 문서화
- [ ] 롤백 승인 획득
- [ ] 영향 범위 분석 완료
- [ ] 롤백 절차 검토
- [ ] 팀원 통지

### 롤백 중

- [ ] 롤백 시작 시간 기록
- [ ] 각 단계 실행 로그 기록
- [ ] 에러 발생 시 즉시 보고
- [ ] 진행 상황 주기적 업데이트

### 롤백 후

- [ ] 롤백 완료 시간 기록
- [ ] 서비스 정상 동작 확인
- [ ] 모니터링 지표 확인
- [ ] 롤백 보고서 작성
- [ ] 사후 분석 회의 일정 수립
- [ ] 재발 방지 대책 수립

---

## 🔍 롤백 검증 절차

### 1. 기능 검증

```bash
# VPC 연결성 테스트
./scripts/test-vpc-connectivity.sh

# 서비스 헬스 체크
curl -X GET https://api.example.com/health

# Lambda 테스트
aws lambda invoke \
  --function-name document-processor \
  --payload '{"test": true}' \
  response.json
```

### 2. 성능 검증

```bash
# 응답 시간 측정
time curl -X GET https://api.example.com/test

# Lambda 실행 시간 확인
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=document-processor \
  --start-time 2026-02-22T00:00:00Z \
  --end-time 2026-02-22T23:59:59Z \
  --period 3600 \
  --statistics Average
```

### 3. 비용 검증

```bash
# 일일 비용 확인
aws ce get-cost-and-usage \
  --time-period Start=2026-02-22,End=2026-02-23 \
  --granularity DAILY \
  --metrics BlendedCost
```

---

## 📚 참고 문서

- [AWS VPC Peering 삭제 가이드](https://docs.aws.amazon.com/vpc/latest/peering/delete-vpc-peering-connection.html)
- [Terraform State 롤백](https://www.terraform.io/docs/cli/commands/state/index.html)
- [AWS OpenSearch Serverless 삭제](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-manage.html)

---

**문서 버전:** 1.0  
**최종 업데이트:** 2026-02-22  
**작성자:** BOS-AI 인프라팀
