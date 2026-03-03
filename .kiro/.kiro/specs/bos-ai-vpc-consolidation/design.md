# BOS-AI VPC 통합 마이그레이션 설계

## 1. 아키텍처 개요

### 1.1 현재 상태 (As-Is)
```
온프레미스 (192.128.x.x)
    ↓ VPN (vgw-0d54d0b0af6515dec)
서울 PoC VPC (10.200.0.0/16)
    - 로깅 인프라만 존재
    - OpenSearch Managed
    - EC2 로그 수집기

서울 BOS-AI-RAG VPC (10.10.0.0/16) [격리됨]
    ↓ VPC Peering
버지니아 VPC (10.20.0.0/16)
```

### 1.2 목표 상태 (To-Be)
```
온프레미스 (192.128.x.x)
    ↓ VPN (vgw-0d54d0b0af6515dec)
서울 통합 VPC (10.200.0.0/16)
    - 로깅 인프라
    - AI 워크로드 (OpenSearch Serverless, Lambda, Bedrock)
    ↓ VPC Peering (신규)
버지니아 백엔드 VPC (10.20.0.0/16)
```

## 2. 네트워크 설계

### 2.1 VPC 구성

**서울 통합 VPC (vpc-bos-ai-seoul-prod-01)**
- CIDR: 10.200.0.0/16
- Region: ap-northeast-2
- 용도: 온프레미스 접점, 로깅, AI 워크로드

**서브넷 구성:**
| 이름 | CIDR | AZ | 타입 | 용도 |
|------|------|-----|------|------|
| sn-private-bos-ai-seoul-prod-01a | 10.200.1.0/24 | 2a | Private | Lambda, OpenSearch, 로그 수집기 |
| sn-private-bos-ai-seoul-prod-01c | 10.200.2.0/24 | 2c | Private | Lambda, OpenSearch (Multi-AZ) |
| sn-public-bos-ai-seoul-prod-01a | 10.200.10.0/24 | 2a | Public | NAT Gateway, Bastion |
| sn-public-bos-ai-seoul-prod-01c | 10.200.20.0/24 | 2c | Public | 예비 |

### 2.2 라우팅 테이블 설계

**Private Route Table (rtb-private-bos-ai-seoul-prod-01)**
| Destination | Target | 용도 |
|-------------|--------|------|
| 10.200.0.0/16 | local | VPC 내부 통신 |
| 0.0.0.0/0 | nat-gateway | 인터넷 아웃바운드 |
| 192.128.1.0/24 | vgw-0d54d0b0af6515dec | 온프레미스 에이전트 |
| 192.128.10.0/24 | vgw-0d54d0b0af6515dec | 온프레미스 FTP |
| 192.128.20.0/24 | vgw-0d54d0b0af6515dec | 온프레미스 OpenSearch |
| 10.20.0.0/16 | pcx-xxxxx | 버지니아 VPC 피어링 |

**Public Route Table (rtb-public-bos-ai-seoul-prod-01)**
| Destination | Target | 용도 |
|-------------|--------|------|
| 10.200.0.0/16 | local | VPC 내부 통신 |
| 0.0.0.0/0 | igw-xxxxx | 인터넷 게이트웨이 |

### 2.3 VPC 피어링 설계

**Peering Connection: pcx-seoul-virginia**
- Requester: vpc-bos-ai-seoul-prod-01 (10.200.0.0/16)
- Accepter: vpc-bos-ai-virginia-backend-prod (10.20.0.0/16)
- DNS Resolution: Enabled (양방향)
- 용도: Lambda → S3 문서 접근, 데이터 동기화

**버지니아 VPC Route Table 업데이트:**
| Destination | Target | 용도 |
|-------------|--------|------|
| 10.200.0.0/16 | pcx-seoul-virginia | 서울 VPC 접근 |

## 3. 보안 설계

### 3.1 Security Group 설계

**sg-opensearch-bos-ai-seoul-prod**

- 용도: OpenSearch Serverless 컬렉션 보호
- Inbound Rules:
  - Port 443 from sg-lambda-bos-ai-seoul-prod (Lambda 접근)
  - Port 443 from sg-bedrock-kb-bos-ai-seoul-prod (Bedrock KB 접근)
  - Port 443 from 192.128.0.0/16 (온프레미스 접근)
  - Port 443 from 10.20.0.0/16 (버지니아 VPC 접근)
- Outbound Rules:
  - All traffic to 0.0.0.0/0

**sg-lambda-bos-ai-seoul-prod**
- 용도: Lambda 함수 보호
- Inbound Rules: None (Lambda는 인바운드 불필요)
- Outbound Rules:
  - Port 443 to sg-opensearch-bos-ai-seoul-prod (OpenSearch 접근)
  - Port 443 to sg-vpc-endpoints-bos-ai-seoul-prod (VPC 엔드포인트 접근)
  - Port 443 to 10.20.0.0/16 (버지니아 S3 접근)

**sg-bedrock-kb-bos-ai-seoul-prod**
- 용도: Bedrock Knowledge Base 보호
- Inbound Rules: None
- Outbound Rules:
  - Port 443 to sg-opensearch-bos-ai-seoul-prod (벡터 DB 접근)
  - Port 443 to sg-vpc-endpoints-bos-ai-seoul-prod (S3 접근)

**sg-vpc-endpoints-bos-ai-seoul-prod**
- 용도: VPC 엔드포인트 보호
- Inbound Rules:
  - Port 443 from 10.200.0.0/16 (VPC 내부 모든 리소스)
  - Port 443 from 192.128.0.0/16 (온프레미스)
- Outbound Rules:
  - All traffic to 0.0.0.0/0

**기존 Security Group 유지:**
- sg-logclt-itdev-int-poc-01 (로그 수집기)
- sg-gra-itdev-int-poc-01 (Grafana)
- sg-os-open-mon-int-poc-01 (OpenSearch Managed)

### 3.2 Network ACL 설계
기본 NACL 사용 (모든 트래픽 허용), Security Group으로 세밀한 제어

### 3.3 IAM Role 설계

**role-lambda-document-processor-seoul-prod**
- 용도: Lambda 문서 처리 함수
- 권한:
  - S3: GetObject, PutObject (버지니아 문서 버킷)
  - OpenSearch: ESHttpPost, ESHttpPut (벡터 인덱싱)
  - Bedrock: InvokeModel (임베딩 생성)
  - Secrets Manager: GetSecretValue (OpenSearch 자격증명)
  - CloudWatch Logs: CreateLogGroup, CreateLogStream, PutLogEvents
  - EC2: CreateNetworkInterface, DescribeNetworkInterfaces, DeleteNetworkInterface (VPC 접근)

**role-bedrock-kb-seoul-prod**
- 용도: Bedrock Knowledge Base
- 권한:
  - S3: GetObject, ListBucket (문서 소스)
  - OpenSearch Serverless: APIAccessAll (벡터 저장)
  - Bedrock: InvokeModel (임베딩 모델)

**role-opensearch-serverless-seoul-prod**
- 용도: OpenSearch Serverless 서비스 역할
- 권한:
  - VPC: CreateNetworkInterface, DescribeNetworkInterfaces (VPC 엔드포인트)

## 4. VPC 엔드포인트 설계

### 4.1 Interface Endpoints

**vpce-bedrock-runtime-seoul-prod**
- Service: com.amazonaws.ap-northeast-2.bedrock-runtime
- Type: Interface
- Subnets: sn-private-bos-ai-seoul-prod-01a, sn-private-bos-ai-seoul-prod-01c
- Security Group: sg-vpc-endpoints-bos-ai-seoul-prod
- Private DNS: Enabled

**vpce-secretsmanager-seoul-prod**
- Service: com.amazonaws.ap-northeast-2.secretsmanager
- Type: Interface
- Subnets: sn-private-bos-ai-seoul-prod-01a, sn-private-bos-ai-seoul-prod-01c
- Security Group: sg-vpc-endpoints-bos-ai-seoul-prod
- Private DNS: Enabled

**vpce-logs-seoul-prod**
- Service: com.amazonaws.ap-northeast-2.logs
- Type: Interface
- Subnets: sn-private-bos-ai-seoul-prod-01a, sn-private-bos-ai-seoul-prod-01c
- Security Group: sg-vpc-endpoints-bos-ai-seoul-prod
- Private DNS: Enabled

**기존 유지:**
- vpce-firehose-itdev-int-poc-01 (로깅 파이프라인용)

### 4.2 Gateway Endpoints

**vpce-s3-seoul-prod**
- Service: com.amazonaws.ap-northeast-2.s3
- Type: Gateway
- Route Tables: rtb-private-bos-ai-seoul-prod-01
- Policy: Allow all (추후 제한 가능)

## 5. Route53 Resolver 설계

### 5.1 기존 Resolver 엔드포인트 활용

**Inbound Endpoint (rslvr-in-79867dcffe644a378)**
- 이름: ibe-onprem-itdev-int-poc-01 → ibe-bos-ai-seoul-prod
- 용도: 온프레미스에서 AWS 리소스 도메인 해석
- IP 주소: 10.200.1.x, 10.200.2.x (프라이빗 서브넷)
- Security Group: sg-route53-resolver-bos-ai-seoul-prod

**Outbound Endpoint (rslvr-out-528276266e13403aa)**
- 이름: obe-onprem-itdev-int-poc-01 → obe-bos-ai-seoul-prod
- 용도: AWS에서 온프레미스 도메인 해석
- IP 주소: 10.200.1.x, 10.200.2.x (프라이빗 서브넷)
- Security Group: sg-route53-resolver-bos-ai-seoul-prod

### 5.2 Resolver Rules

**AWS 서비스 도메인 포워딩 (신규)**
- bedrock-runtime.ap-northeast-2.amazonaws.com → VPC DNS
- s3.ap-northeast-2.amazonaws.com → VPC DNS
- secretsmanager.ap-northeast-2.amazonaws.com → VPC DNS

**온프레미스 도메인 포워딩 (기존 유지)**
- internal.company.com → 온프레미스 DNS 서버

## 6. OpenSearch Serverless 설계

### 6.1 컬렉션 구성

**Collection: bos-ai-rag-vectors-prod**
- Type: Vectorsearch
- Standby Replicas: Enabled
- Encryption: AWS managed key

### 6.2 VPC 엔드포인트

**VPC Endpoint: vpce-opensearch-serverless-seoul-prod**
- VPC: vpc-bos-ai-seoul-prod-01
- Subnets: sn-private-bos-ai-seoul-prod-01a, sn-private-bos-ai-seoul-prod-01c
- Security Group: sg-opensearch-bos-ai-seoul-prod

### 6.3 액세스 정책

**Data Access Policy:**
```json
{
  "Rules": [
    {
      "ResourceType": "collection",
      "Resource": ["collection/bos-ai-rag-vectors-prod"],
      "Permission": ["aoss:*"],
      "Principal": [
        "arn:aws:iam::533335672315:role/role-lambda-document-processor-seoul-prod",
        "arn:aws:iam::533335672315:role/role-bedrock-kb-seoul-prod"
      ]
    }
  ]
}
```

**Network Policy:**
```json
{
  "Rules": [
    {
      "ResourceType": "collection",
      "Resource": ["collection/bos-ai-rag-vectors-prod"],
      "SourceVPCEs": ["vpce-opensearch-serverless-seoul-prod"]
    }
  ]
}
```

### 6.4 인덱스 매핑
기존 설계 유지 (modules/ai-workload/bedrock-rag/opensearch_index_mapping.json)

## 7. Lambda 설계

### 7.1 함수 구성

**Function: lambda-document-processor-seoul-prod**
- Runtime: Python 3.12
- Memory: 512 MB
- Timeout: 300s
- VPC: vpc-bos-ai-seoul-prod-01
- Subnets: sn-private-bos-ai-seoul-prod-01a, sn-private-bos-ai-seoul-prod-01c
- Security Group: sg-lambda-bos-ai-seoul-prod
- Role: role-lambda-document-processor-seoul-prod

### 7.2 환경 변수
```
OPENSEARCH_ENDPOINT=vpce-xxxxx.aoss.ap-northeast-2.on.aws
OPENSEARCH_INDEX=bos-ai-documents
BEDROCK_MODEL_ID=amazon.titan-embed-text-v1
S3_BUCKET_VIRGINIA=bos-ai-documents-us
SECRET_NAME=opensearch/bos-ai-rag-prod
```

### 7.3 트리거
- S3 Event (버지니아 버킷: bos-ai-documents-us)
- EventBridge (스케줄 동기화)

## 8. Bedrock Knowledge Base 설계

### 8.1 Knowledge Base 구성

**Name: bos-ai-kb-seoul-prod**
- Foundation Model: amazon.titan-embed-text-v1
- Vector Store: OpenSearch Serverless (bos-ai-rag-vectors-prod)
- Data Source: S3 (bos-ai-documents-us, bos-ai-documents-seoul)

### 8.2 VPC 설정
- VPC: vpc-bos-ai-seoul-prod-01
- Subnets: sn-private-bos-ai-seoul-prod-01a, sn-private-bos-ai-seoul-prod-01c
- Security Group: sg-bedrock-kb-bos-ai-seoul-prod

## 9. 마이그레이션 전략

### 9.1 단계별 접근

**Phase 1: 준비 (사전 작업)**
1. 현재 상태 백업 (Terraform state, 설정 파일)
2. 네이밍 규칙 확정 및 문서화
3. 롤백 계획 수립

**Phase 2: VPC 네이밍 변경**
1. Terraform 변수 파일 업데이트
2. 태그 변경 (VPC, 서브넷, Security Group 등)
3. 문서 업데이트
4. 검증 (리소스 ID 변경 없음 확인)

**Phase 3: VPC 엔드포인트 구성**
1. Bedrock Runtime 엔드포인트 생성
2. Secrets Manager 엔드포인트 생성
3. S3 Gateway 엔드포인트 생성
4. 연결 테스트

**Phase 4: OpenSearch Serverless 배포**
1. 컬렉션 생성
2. VPC 엔드포인트 생성
3. 액세스 정책 설정
4. 인덱스 생성
5. 연결 테스트

**Phase 5: Lambda 배포**
1. Lambda 함수 생성 (VPC 설정 포함)
2. IAM Role 연결
3. 환경 변수 설정
4. S3 트리거 설정
5. 테스트 문서 처리

**Phase 6: Bedrock Knowledge Base 설정**
1. Knowledge Base 생성
2. 데이터 소스 연결
3. 동기화 실행
4. 쿼리 테스트

**Phase 7: VPC 피어링 구성**
1. Peering Connection 생성
2. 서울 VPC 라우팅 테이블 업데이트
3. 버지니아 VPC 라우팅 테이블 업데이트
4. Security Group 규칙 추가
5. 연결 테스트

**Phase 8: 통합 테스트**
1. 온프레미스 → 서울 VPC 연결 테스트
2. 서울 VPC → 버지니아 VPC 연결 테스트
3. 전체 파이프라인 테스트 (문서 업로드 → 임베딩 → 검색)
4. 기존 로깅 인프라 정상 동작 확인

**Phase 9: 기존 VPC 제거**
1. BOS-AI-RAG VPC 리소스 확인 (모두 마이그레이션됨)
2. VPC 피어링 연결 삭제
3. VPN Gateway 분리
4. VPC 삭제
5. Terraform state 정리

### 9.2 롤백 계획

**각 Phase별 롤백 절차:**
- Phase 2: 태그 원복 (리소스 변경 없음)
- Phase 3-6: 신규 리소스 삭제
- Phase 7: 피어링 연결 삭제, 라우팅 원복
- Phase 9: VPC 재생성 (백업에서 복원)

**롤백 트리거:**
- 기존 로깅 인프라 장애 발생
- 온프레미스 연결 중단
- 성능 저하 (지연시간 >100ms)
- 보안 스캔 실패

## 10. 테스트 계획

### 10.1 단위 테스트

**네트워크 연결 테스트:**
- 온프레미스 → 서울 VPC (ping, traceroute)
- 서울 VPC → 버지니아 VPC (ping, traceroute)
- Lambda → OpenSearch (curl, SDK)
- Lambda → S3 (aws s3 ls)

**보안 테스트:**
- Security Group 규칙 검증 (nmap)
- IAM Role 권한 검증 (aws sts assume-role)
- VPC 엔드포인트 접근 검증 (nslookup, curl)

### 10.2 통합 테스트

**전체 파이프라인 테스트:**
1. 버지니아 S3에 테스트 문서 업로드
2. Lambda 함수 자동 트리거 확인
3. Bedrock 임베딩 생성 확인
4. OpenSearch Serverless 인덱싱 확인
5. Knowledge Base 쿼리 테스트
6. 온프레미스에서 결과 조회

**기존 인프라 테스트:**
1. 온프레미스 로그 수집 정상 동작
2. Firehose 전송 정상 동작
3. OpenSearch Managed 인덱싱 정상 동작
4. Grafana 대시보드 정상 표시

### 10.3 성능 테스트

**지연시간 측정:**
- 온프레미스 → 서울 VPC: <50ms
- 서울 VPC → 버지니아 VPC: <200ms
- Lambda 실행 시간: <10s (문서당)

**처리량 측정:**
- Lambda 동시 실행: 10개
- 문서 처리 속도: 100개/분

## 11. 모니터링 및 알람

### 11.1 CloudWatch Metrics

**VPC 메트릭:**
- VPC Flow Logs (모든 트래픽 기록)
- NAT Gateway 바이트 전송량
- VPC Peering 바이트 전송량

**Lambda 메트릭:**
- Invocations, Errors, Duration
- Concurrent Executions
- Throttles

**OpenSearch 메트릭:**
- IndexingRate, SearchRate
- ClusterStatus
- StorageUsed

### 11.2 CloudWatch Alarms

**네트워크 알람:**
- VPN 연결 상태 (Down)
- NAT Gateway 오류율 (>1%)
- VPC Peering 연결 상태 (Down)

**애플리케이션 알람:**
- Lambda 오류율 (>5%)
- Lambda 제한 (Throttles >0)
- OpenSearch 클러스터 상태 (Red)

### 11.3 CloudWatch Dashboards

**대시보드: bos-ai-seoul-prod-overview**
- VPC 트래픽 (온프레미스, 버지니아)
- Lambda 실행 통계
- OpenSearch 인덱싱 통계
- 비용 추이

## 12. 비용 분석

### 12.1 예상 비용 (월간)

**VPC 관련:**
- NAT Gateway: $32 (1개 × $0.045/시간)
- VPC Peering 데이터 전송: $10 (100GB × $0.01/GB)
- VPC Endpoints: $21 (3개 × $0.01/시간)

**컴퓨팅:**
- Lambda: $20 (100만 요청, 512MB, 10s)
- OpenSearch Serverless: $700 (OCU 기준)

**스토리지:**
- S3: $23 (1TB)
- OpenSearch 인덱스: 포함 (OCU에 포함)

**데이터 전송:**
- 서울 → 버지니아: $90 (1TB × $0.09/GB)

**총 예상 비용: ~$900/월**

### 12.2 비용 절감 방안
- VPC 통합으로 중복 리소스 제거 (~$200 절감)
- VPC Endpoints로 NAT Gateway 사용 감소 (~$50 절감)
- S3 Intelligent-Tiering 적용 (~$100 절감)

## 13. 보안 및 컴플라이언스

### 13.1 보안 체크리스트
- [ ] 모든 통신은 프라이빗 네트워크 사용
- [ ] Security Group 최소 권한 원칙 적용
- [ ] IAM Role 서비스별 분리
- [ ] VPC Flow Logs 활성화
- [ ] CloudTrail 로깅 활성화
- [ ] 암호화 전송 (TLS 1.2+)
- [ ] 암호화 저장 (KMS)

### 13.2 컴플라이언스
- AWS Well-Architected Framework 준수
- CIS AWS Foundations Benchmark 준수
- 내부 보안 정책 준수

## 14. 운영 가이드

### 14.1 일상 운영 작업
- CloudWatch 대시보드 모니터링
- 알람 확인 및 대응
- 비용 추이 확인
- 로그 검토

### 14.2 정기 유지보수
- 월간: Security Group 규칙 검토
- 분기: IAM Role 권한 검토
- 반기: 아키텍처 최적화 검토

### 14.3 장애 대응
- VPN 연결 장애: AWS Support 연락, 온프레미스 네트워크 팀 협조
- Lambda 오류: CloudWatch Logs 확인, 코드 롤백
- OpenSearch 장애: 스냅샷 복원, AWS Support 연락

## 15. 문서 및 다이어그램

### 15.1 네트워크 다이어그램
(Terraform 배포 후 자동 생성)

### 15.2 데이터 흐름 다이어그램
```
온프레미스 로그
    ↓ VPN
EC2 로그 수집기
    ↓ VPC Endpoint
Kinesis Firehose
    ↓
OpenSearch Managed

온프레미스 사용자
    ↓ VPN
Bedrock Knowledge Base
    ↓ VPC Endpoint
OpenSearch Serverless
    ↑
Lambda (문서 처리)
    ↑ VPC Peering
S3 (버지니아)
```

### 15.3 보안 경계 다이어그램
(Security Group 관계도)

## 16. 정확성 속성 (Correctness Properties)

### 16.1 네트워크 연결성 속성

**Property 1.1: VPN 라우팅 일관성**
**Validates: Requirements 2.1, NFR-1**
```
∀ destination ∈ [192.128.1.0/24, 192.128.10.0/24, 192.128.20.0/24]:
  route_table_entry(destination) = vgw-0d54d0b0af6515dec
```
모든 온프레미스 대역에 대한 라우팅이 VPN Gateway를 가리켜야 함

**Property 1.2: VPC 피어링 양방향 라우팅**
**Validates: Requirements 2.2, 3.5**
```
seoul_route_table.has_route(10.20.0.0/16, pcx-seoul-virginia) ∧
virginia_route_table.has_route(10.200.0.0/16, pcx-seoul-virginia)
```
양방향 라우팅이 모두 설정되어야 함

### 16.2 보안 속성

**Property 2.1: Security Group 최소 권한**
**Validates: Requirements NFR-1**
```
∀ sg ∈ security_groups:
  ∀ rule ∈ sg.inbound_rules:
    rule.source ≠ 0.0.0.0/0 ∨ rule.port ∈ [80, 443]
```
모든 인바운드 규칙은 특정 소스를 지정하거나 표준 포트만 허용

**Property 2.2: VPC 엔드포인트 프라이빗 DNS**
**Validates: Requirements 2.3, 3.6**
```
∀ vpce ∈ interface_endpoints:
  vpce.private_dns_enabled = true
```
모든 Interface 엔드포인트는 Private DNS가 활성화되어야 함

### 16.3 고가용성 속성

**Property 3.1: Multi-AZ 배포**
**Validates: Requirements NFR-2**
```
∀ resource ∈ [lambda, opensearch_serverless]:
  |resource.subnets| ≥ 2 ∧
  ∀ i,j ∈ resource.subnets: i.az ≠ j.az
```
모든 중요 리소스는 최소 2개 AZ에 배포되어야 함

**Property 3.2: VPC 엔드포인트 이중화**
**Validates: Requirements NFR-2**
```
∀ vpce ∈ interface_endpoints:
  |vpce.subnets| ≥ 2
```
모든 Interface 엔드포인트는 최소 2개 서브넷에 배포되어야 함

### 16.4 데이터 무결성 속성

**Property 4.1: 기존 로깅 파이프라인 보존**
**Validates: Requirements 2.5, NFR-2**
```
∀ resource ∈ [ec2_log_collector, firehose_endpoint, opensearch_managed]:
  resource.state = "running" ∧
  resource.vpc_id = vpc-bos-ai-seoul-prod-01
```
마이그레이션 후에도 기존 로깅 리소스가 동일 VPC에서 정상 동작해야 함

**Property 4.2: OpenSearch 인덱스 매핑 일관성**
**Validates: Requirements 3.2**
```
opensearch_serverless.index_mapping = 
  file("opensearch_index_mapping.json")
```
인덱스 매핑이 설계 문서와 일치해야 함

### 16.5 네이밍 일관성 속성

**Property 5.1: 리소스 네이밍 규칙**
**Validates: Requirements 2.4, 3.1**
```
∀ resource ∈ all_resources:
  resource.name matches "^(vpc|sn|sg|rtb|vpce)-.*-bos-ai-seoul-prod-.*$"
```
모든 리소스 이름이 표준 네이밍 규칙을 따라야 함

**Property 5.2: 태그 일관성**
**Validates: Requirements 2.4, NFR-4**
```
∀ resource ∈ all_resources:
  resource.tags.contains("Project") ∧
  resource.tags.contains("Environment") ∧
  resource.tags.contains("ManagedBy") ∧
  resource.tags["ManagedBy"] = "Terraform"
```
모든 리소스가 필수 태그를 가져야 함

### 16.6 IAM 권한 속성

**Property 6.1: Lambda 최소 권한**
**Validates: Requirements NFR-1**
```
lambda_role.policies ⊆ {
  "s3:GetObject", "s3:PutObject",
  "aoss:APIAccessAll",
  "bedrock:InvokeModel",
  "secretsmanager:GetSecretValue",
  "logs:*",
  "ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces"
}
```
Lambda Role이 필요한 권한만 가져야 함

**Property 6.2: 교차 계정 접근 금지**
**Validates: Requirements NFR-1**
```
∀ role ∈ iam_roles:
  ∀ principal ∈ role.trust_policy.principals:
    principal.account = "533335672315"
```
모든 IAM Role이 동일 계정 내에서만 사용되어야 함

### 16.7 성능 속성

**Property 7.1: VPC 피어링 지연시간**
**Validates: Requirements NFR-3**
```
latency(seoul_vpc, virginia_vpc) < 200ms
```
VPC 피어링 지연시간이 200ms 미만이어야 함

**Property 7.2: Lambda 실행 시간**
**Validates: Requirements NFR-3**
```
∀ invocation ∈ lambda_invocations:
  invocation.duration < 10000ms
```
Lambda 실행 시간이 10초 미만이어야 함

## 17. 테스트 전략

### 17.1 Property-Based Testing
각 정확성 속성에 대해 다음 테스트를 수행:
- 라우팅 테이블 검증 (Property 1.1, 1.2)
- Security Group 규칙 검증 (Property 2.1)
- Multi-AZ 배포 검증 (Property 3.1, 3.2)
- 네이밍 규칙 검증 (Property 5.1, 5.2)
- IAM 권한 검증 (Property 6.1, 6.2)

### 17.2 Integration Testing
- 전체 파이프라인 테스트 (온프레미스 → 서울 → 버지니아)
- 장애 시나리오 테스트 (AZ 장애, VPN 장애)
- 성능 테스트 (지연시간, 처리량)

### 17.3 Regression Testing
- 기존 로깅 인프라 정상 동작 확인
- 온프레미스 연결 정상 동작 확인

## 18. 참고 자료

### 18.1 AWS 문서
- VPC Peering Guide
- OpenSearch Serverless Developer Guide
- Bedrock Knowledge Base Guide
- Route53 Resolver Guide

### 18.2 내부 문서
- 기존 로깅 인프라 구축 가이드
- 온프레미스 네트워크 다이어그램
- 보안 정책 문서

### 18.3 Terraform 모듈
- modules/network/vpc
- modules/network/security-groups
- modules/security/vpc-endpoints
- modules/ai-workload/bedrock-rag
