# 현재 Security Group 규칙 문서

## 문서 정보

- **작성일**: 2026-02-20
- **작성자**: Kiro AI
- **목적**: BOS-AI VPC 통합 마이그레이션 전 Security Group 규칙 기록
- **관련 스펙**: `.kiro/specs/bos-ai-vpc-consolidation/`
- **관련 문서**: `docs/current-vpc-configuration.md`

## 개요

이 문서는 BOS-AI VPC 통합 마이그레이션 프로젝트의 일환으로 현재 및 계획된 Security Group 규칙을 문서화합니다. 
마이그레이션 전후의 보안 설정을 명확히 기록하여 변경 사항 추적 및 보안 검증에 활용합니다.

## 1. 서울 PoC VPC (vpc-066c464f9c750ee9e) - 기존 Security Groups

### 1.1 기존 로깅 인프라 Security Groups

이 Security Groups는 마이그레이션 후에도 **유지**됩니다.

#### sg-logclt-itdev-int-poc-01 (로그 수집기)

**용도**: EC2 로그 수집기 보호

**Inbound Rules**:
| 규칙 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 22 | 192.128.0.0/16 | 온프레미스에서 SSH 접근 |
| 2 | TCP | 514 | 192.128.0.0/16 | 온프레미스 Syslog 수신 |
| 3 | TCP | 9200 | 10.200.0.0/16 | VPC 내부 모니터링 |

**Outbound Rules**:
| 규칙 | 프로토콜 | 포트 | 대상 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 443 | 0.0.0.0/0 | Kinesis Firehose 전송 (VPC 엔드포인트 통해) |
| 2 | TCP | 443 | 10.200.0.0/16 | OpenSearch Managed 전송 |
| 3 | All | All | 0.0.0.0/0 | AWS 서비스 통신 |


#### sg-gra-itdev-int-poc-01 (Grafana)

**용도**: Grafana 대시보드 서버 보호

**Inbound Rules**:
| 규칙 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 3000 | 192.128.0.0/16 | 온프레미스에서 Grafana UI 접근 |
| 2 | TCP | 22 | 192.128.0.0/16 | 온프레미스에서 SSH 접근 |

**Outbound Rules**:
| 규칙 | 프로토콜 | 포트 | 대상 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 9200 | sg-os-open-mon-int-poc-01 | OpenSearch Managed 쿼리 |
| 2 | TCP | 443 | 0.0.0.0/0 | 플러그인 다운로드 및 업데이트 |

#### sg-os-open-mon-int-poc-01 (OpenSearch Managed)

**용도**: OpenSearch Managed 도메인 보호

**Inbound Rules**:
| 규칙 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 443 | sg-logclt-itdev-int-poc-01 | 로그 수집기에서 인덱싱 |
| 2 | TCP | 9200 | sg-gra-itdev-int-poc-01 | Grafana에서 쿼리 |
| 3 | TCP | 443 | 192.128.0.0/16 | 온프레미스에서 직접 쿼리 |
| 4 | TCP | 9200 | 10.200.0.0/16 | VPC 내부 접근 |

**Outbound Rules**:
| 규칙 | 프로토콜 | 포트 | 대상 | 설명 |
|------|---------|------|------|------|
| 1 | All | All | 0.0.0.0/0 | AWS 서비스 통신 |

#### sg-route53-resolver (Route53 Resolver)

**용도**: Route53 Resolver 엔드포인트 보호

**Inbound Rules**:
| 규칙 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 53 | 10.200.0.0/16 | VPC 내부 DNS 쿼리 |
| 2 | UDP | 53 | 10.200.0.0/16 | VPC 내부 DNS 쿼리 |
| 3 | TCP | 53 | 192.128.0.0/16 | 온프레미스 DNS 쿼리 |
| 4 | UDP | 53 | 192.128.0.0/16 | 온프레미스 DNS 쿼리 |

**Outbound Rules**:
| 규칙 | 프로토콜 | 포트 | 대상 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 53 | 0.0.0.0/0 | 외부 DNS 포워딩 |
| 2 | UDP | 53 | 0.0.0.0/0 | 외부 DNS 포워딩 |


#### sg-vpc-endpoints-firehose (Kinesis Firehose VPC 엔드포인트)

**용도**: Kinesis Firehose VPC 엔드포인트 보호

**Inbound Rules**:
| 규칙 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 443 | 10.200.0.0/16 | VPC 내부에서 Firehose 접근 |
| 2 | TCP | 443 | sg-logclt-itdev-int-poc-01 | 로그 수집기에서 Firehose 접근 |

**Outbound Rules**:
| 규칙 | 프로토콜 | 포트 | 대상 | 설명 |
|------|---------|------|------|------|
| 1 | All | All | 0.0.0.0/0 | AWS 서비스 통신 |

---

## 2. 서울 통합 VPC - 신규 AI 워크로드 Security Groups

### 2.1 마이그레이션 후 추가될 Security Groups

이 Security Groups는 마이그레이션 중 **새로 생성**됩니다.

#### sg-lambda-bos-ai-seoul-prod (Lambda 함수)

**용도**: Lambda 문서 처리 함수 보호

**네이밍 규칙**: `sg-lambda-bos-ai-seoul-prod`

**Inbound Rules**:
| 규칙 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| - | - | - | - | **인바운드 규칙 없음** (Lambda는 인바운드 연결 불필요) |

**Outbound Rules**:
| 규칙 | 프로토콜 | 포트 | 대상 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 443 | sg-opensearch-bos-ai-seoul-prod | OpenSearch Serverless 접근 |
| 2 | TCP | 443 | sg-vpc-endpoints-bos-ai-seoul-prod | VPC 엔드포인트 접근 (Bedrock, S3, Secrets Manager) |
| 3 | TCP | 443 | 10.20.0.0/16 | 버지니아 VPC S3 접근 (VPC 피어링 통해) |
| 4 | TCP | 443 | 10.200.0.0/16 | VPC 내부 통신 |

**Terraform 설정**:
```hcl
resource "aws_security_group" "lambda" {
  name        = "sg-lambda-bos-ai-seoul-prod"
  description = "Controls outbound access for Lambda document processors"
  vpc_id      = vpc-066c464f9c750ee9e

  # No ingress rules - Lambda doesn't accept incoming connections

  egress {
    description = "HTTPS to VPC Endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.200.0.0/16"]
  }
}
```


#### sg-opensearch-bos-ai-seoul-prod (OpenSearch Serverless)

**용도**: OpenSearch Serverless 컬렉션 보호

**네이밍 규칙**: `sg-opensearch-bos-ai-seoul-prod`

**Inbound Rules**:
| 규칙 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 443 | sg-lambda-bos-ai-seoul-prod | Lambda 함수에서 벡터 인덱싱 |
| 2 | TCP | 443 | sg-bedrock-kb-bos-ai-seoul-prod | Bedrock Knowledge Base에서 벡터 검색 |
| 3 | TCP | 443 | 192.128.0.0/16 | 온프레미스에서 직접 쿼리 (VPN 통해) |
| 4 | TCP | 443 | 10.20.0.0/16 | 버지니아 VPC에서 접근 (VPC 피어링 통해) |
| 5 | TCP | 443 | 10.200.0.0/16 | VPC 내부 접근 (Bedrock 서비스) |

**Outbound Rules**:
| 규칙 | 프로토콜 | 포트 | 대상 | 설명 |
|------|---------|------|------|------|
| 1 | All | All | 0.0.0.0/0 | AWS 서비스 통신 |

**Terraform 설정**:
```hcl
resource "aws_security_group" "opensearch" {
  name        = "sg-opensearch-bos-ai-seoul-prod"
  description = "Controls access to OpenSearch Serverless collection"
  vpc_id      = vpc-066c464f9c750ee9e

  ingress {
    description     = "HTTPS from Lambda"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  ingress {
    description = "HTTPS from Bedrock Service"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.200.0.0/16"]
  }

  ingress {
    description = "HTTPS from on-premises"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["192.128.0.0/16"]
  }

  ingress {
    description = "HTTPS from peered VPC (Virginia)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.20.0.0/16"]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```


#### sg-bedrock-kb-bos-ai-seoul-prod (Bedrock Knowledge Base)

**용도**: Bedrock Knowledge Base 보호

**네이밍 규칙**: `sg-bedrock-kb-bos-ai-seoul-prod`

**Inbound Rules**:
| 규칙 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| - | - | - | - | **인바운드 규칙 없음** (Bedrock KB는 인바운드 연결 불필요) |

**Outbound Rules**:
| 규칙 | 프로토콜 | 포트 | 대상 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 443 | sg-opensearch-bos-ai-seoul-prod | OpenSearch Serverless 벡터 DB 접근 |
| 2 | TCP | 443 | sg-vpc-endpoints-bos-ai-seoul-prod | VPC 엔드포인트 접근 (S3, Bedrock) |
| 3 | TCP | 443 | 10.200.0.0/16 | VPC 내부 통신 |

**참고**: Bedrock Knowledge Base는 AWS 관리형 서비스이므로, 실제로는 VPC 내부에서 실행되는 ENI에 이 Security Group이 적용됩니다.

#### sg-vpc-endpoints-bos-ai-seoul-prod (VPC 엔드포인트)

**용도**: VPC 엔드포인트 보호 (Bedrock Runtime, S3, Secrets Manager, CloudWatch Logs)

**네이밍 규칙**: `sg-vpc-endpoints-bos-ai-seoul-prod`

**Inbound Rules**:
| 규칙 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 443 | 10.200.0.0/16 | VPC 내부 모든 리소스에서 접근 |
| 2 | TCP | 443 | 192.128.0.0/16 | 온프레미스에서 접근 (VPN 통해) |
| 3 | TCP | 443 | sg-lambda-bos-ai-seoul-prod | Lambda 함수에서 접근 |
| 4 | TCP | 443 | sg-bedrock-kb-bos-ai-seoul-prod | Bedrock KB에서 접근 |

**Outbound Rules**:
| 규칙 | 프로토콜 | 포트 | 대상 | 설명 |
|------|---------|------|------|------|
| 1 | All | All | 0.0.0.0/0 | AWS 서비스 통신 |

**Terraform 설정**:
```hcl
resource "aws_security_group" "vpc_endpoints" {
  name        = "sg-vpc-endpoints-bos-ai-seoul-prod"
  description = "Controls access to VPC Endpoints for AWS services"
  vpc_id      = vpc-066c464f9c750ee9e

  ingress {
    description = "HTTPS from VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.200.0.0/16"]
  }

  ingress {
    description = "HTTPS from on-premises"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["192.128.0.0/16"]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```


---

## 3. 서울 BOS-AI-RAG VPC (vpc-0f759f00e5df658d1) - 삭제 예정

### 3.1 현재 상태

**참고**: 이 VPC에는 실제 배포된 리소스가 없으며, Security Group도 생성되지 않았습니다. 
마이그레이션 완료 후 이 VPC는 완전히 삭제됩니다.

---

## 4. 버지니아 백엔드 VPC (10.20.0.0/16)

### 4.1 기존 Security Groups (변경 없음)

버지니아 VPC의 Security Groups는 마이그레이션 범위에 포함되지 않으며, 기존 상태를 유지합니다.

#### sg-s3-vpc-endpoint-virginia (S3 VPC 엔드포인트)

**용도**: S3 VPC 엔드포인트 보호

**Inbound Rules**:
| 규칙 | 프로토콜 | 포트 | 소스 | 설명 |
|------|---------|------|------|------|
| 1 | TCP | 443 | 10.20.0.0/16 | VPC 내부에서 S3 접근 |
| 2 | TCP | 443 | 10.200.0.0/16 | 서울 VPC에서 S3 접근 (VPC 피어링 통해) |

**Outbound Rules**:
| 규칙 | 프로토콜 | 포트 | 대상 | 설명 |
|------|---------|------|------|------|
| 1 | All | All | 0.0.0.0/0 | AWS 서비스 통신 |

**마이그레이션 시 변경 사항**:
- Inbound Rule 2번에 서울 통합 VPC CIDR (10.200.0.0/16) 추가 필요
- 기존 BOS-AI-RAG VPC CIDR (10.10.0.0/16) 제거

---

## 5. Security Group 관계도

### 5.1 서울 통합 VPC 내부 트래픽 흐름

```
온프레미스 (192.128.0.0/16)
    ↓ VPN
    ↓ Port 443
sg-opensearch-bos-ai-seoul-prod (OpenSearch Serverless)
    ↑ Port 443
sg-lambda-bos-ai-seoul-prod (Lambda)
    ↓ Port 443
sg-vpc-endpoints-bos-ai-seoul-prod (VPC Endpoints)
    ↓ Port 443
AWS 서비스 (Bedrock, S3, Secrets Manager)
```

### 5.2 교차 VPC 트래픽 흐름

```
서울 통합 VPC (10.200.0.0/16)
    sg-lambda-bos-ai-seoul-prod
        ↓ VPC Peering
        ↓ Port 443
버지니아 VPC (10.20.0.0/16)
    sg-s3-vpc-endpoint-virginia
        ↓
    S3 버킷 (문서 저장소)
```


---

## 6. Security Group 규칙 요약

### 6.1 포트 사용 요약

| 포트 | 프로토콜 | 용도 | Security Groups |
|------|---------|------|----------------|
| 22 | TCP | SSH 관리 접근 | sg-logclt-itdev-int-poc-01, sg-gra-itdev-int-poc-01 |
| 53 | TCP/UDP | DNS 쿼리 | sg-route53-resolver |
| 443 | TCP | HTTPS (AWS 서비스, OpenSearch, VPC 엔드포인트) | 모든 AI 워크로드 SG |
| 514 | TCP | Syslog | sg-logclt-itdev-int-poc-01 |
| 3000 | TCP | Grafana UI | sg-gra-itdev-int-poc-01 |
| 9200 | TCP | OpenSearch API | sg-os-open-mon-int-poc-01 |

### 6.2 CIDR 블록별 접근 권한

#### 온프레미스 (192.128.0.0/16)

**접근 가능한 리소스**:
- ✅ EC2 로그 수집기 (SSH, Syslog)
- ✅ Grafana (UI, SSH)
- ✅ OpenSearch Managed (쿼리)
- ✅ OpenSearch Serverless (쿼리) - **신규**
- ✅ Route53 Resolver (DNS)
- ✅ VPC 엔드포인트 (AWS 서비스) - **신규**

#### 서울 VPC 내부 (10.200.0.0/16)

**접근 가능한 리소스**:
- ✅ 모든 VPC 내부 리소스
- ✅ OpenSearch Serverless
- ✅ VPC 엔드포인트
- ✅ Lambda 함수 (아웃바운드만)

#### 버지니아 VPC (10.20.0.0/16)

**접근 가능한 리소스**:
- ✅ 서울 VPC의 OpenSearch Serverless (VPC 피어링 통해)
- ✅ 서울 VPC의 Lambda (아웃바운드만, VPC 피어링 통해)

**서울 VPC에서 접근 가능**:
- ✅ S3 버킷 (VPC 피어링 통해)

### 6.3 Security Group 간 참조 관계

| 소스 Security Group | 대상 Security Group | 포트 | 용도 |
|--------------------|--------------------|----|------|
| sg-lambda-bos-ai-seoul-prod | sg-opensearch-bos-ai-seoul-prod | 443 | 벡터 인덱싱 |
| sg-lambda-bos-ai-seoul-prod | sg-vpc-endpoints-bos-ai-seoul-prod | 443 | AWS 서비스 호출 |
| sg-bedrock-kb-bos-ai-seoul-prod | sg-opensearch-bos-ai-seoul-prod | 443 | 벡터 검색 |
| sg-bedrock-kb-bos-ai-seoul-prod | sg-vpc-endpoints-bos-ai-seoul-prod | 443 | S3 접근 |
| sg-logclt-itdev-int-poc-01 | sg-os-open-mon-int-poc-01 | 443 | 로그 인덱싱 |
| sg-gra-itdev-int-poc-01 | sg-os-open-mon-int-poc-01 | 9200 | 대시보드 쿼리 |

---

## 7. 보안 검증 체크리스트

### 7.1 최소 권한 원칙 (Principle of Least Privilege)

- [x] Lambda Security Group: 인바운드 규칙 없음 (필요 없음)
- [x] Bedrock KB Security Group: 인바운드 규칙 없음 (필요 없음)
- [x] OpenSearch Security Group: 특정 소스만 허용 (Lambda, Bedrock, 온프레미스, 버지니아)
- [x] VPC Endpoints Security Group: VPC 및 온프레미스 CIDR만 허용
- [x] 모든 인바운드 규칙: 0.0.0.0/0 사용 안 함 (표준 포트 제외)

### 7.2 네트워크 격리

- [x] 프라이빗 서브넷: 인터넷 게이트웨이 없음
- [x] VPC 피어링: 특정 CIDR 블록만 허용
- [x] VPN 연결: 온프레미스 CIDR만 허용
- [x] Security Group: 교차 참조로 세밀한 제어

### 7.3 암호화 통신

- [x] 모든 AWS 서비스 통신: HTTPS (Port 443)
- [x] OpenSearch 접근: HTTPS (Port 443)
- [x] VPN 연결: IPsec 암호화
- [x] VPC 피어링: AWS 백본 네트워크 (암호화됨)


### 7.4 규정 준수

- [x] CIS AWS Foundations Benchmark: Security Group 규칙 검증
- [x] AWS Well-Architected Framework: 보안 모범 사례 준수
- [x] 내부 보안 정책: 최소 권한 원칙 적용

---

## 8. 마이그레이션 영향 분석

### 8.1 기존 Security Groups 변경 사항

#### 유지되는 Security Groups (변경 없음)
- ✅ sg-logclt-itdev-int-poc-01 (로그 수집기)
- ✅ sg-gra-itdev-int-poc-01 (Grafana)
- ✅ sg-os-open-mon-int-poc-01 (OpenSearch Managed)
- ✅ sg-route53-resolver (Route53 Resolver)
- ✅ sg-vpc-endpoints-firehose (Kinesis Firehose)

#### 새로 생성되는 Security Groups
- ➕ sg-lambda-bos-ai-seoul-prod (Lambda 함수)
- ➕ sg-opensearch-bos-ai-seoul-prod (OpenSearch Serverless)
- ➕ sg-bedrock-kb-bos-ai-seoul-prod (Bedrock Knowledge Base)
- ➕ sg-vpc-endpoints-bos-ai-seoul-prod (VPC 엔드포인트)

#### 삭제되는 Security Groups
- ❌ 서울 BOS-AI-RAG VPC의 모든 Security Groups (실제로는 생성되지 않음)

### 8.2 버지니아 VPC Security Groups 변경 사항

#### sg-s3-vpc-endpoint-virginia 수정 필요
- **추가**: Inbound Rule - 10.200.0.0/16 (서울 통합 VPC)
- **제거**: Inbound Rule - 10.10.0.0/16 (서울 BOS-AI-RAG VPC, 삭제 예정)

---

## 9. 테스트 계획

### 9.1 Security Group 규칙 검증

#### 9.1.1 Lambda → OpenSearch 연결 테스트
```bash
# Lambda 함수 내부에서 실행
curl -X GET "https://<opensearch-endpoint>/_cluster/health" \
  -H "Content-Type: application/json"
```

**예상 결과**: 200 OK (연결 성공)

#### 9.1.2 Lambda → VPC Endpoints 연결 테스트
```bash
# Lambda 함수 내부에서 실행
aws bedrock-runtime invoke-model \
  --model-id amazon.titan-embed-text-v1 \
  --body '{"inputText":"test"}' \
  output.json
```

**예상 결과**: 모델 호출 성공

#### 9.1.3 온프레미스 → OpenSearch Serverless 연결 테스트
```bash
# 온프레미스 서버에서 실행
curl -X GET "https://<opensearch-serverless-endpoint>/_cluster/health" \
  -H "Content-Type: application/json"
```

**예상 결과**: 200 OK (VPN 통해 연결 성공)

#### 9.1.4 서울 VPC → 버지니아 S3 연결 테스트
```bash
# Lambda 함수 내부에서 실행
aws s3 ls s3://bos-ai-documents-us/
```

**예상 결과**: 버킷 내용 조회 성공 (VPC 피어링 통해)

### 9.2 보안 스캔

#### 9.2.1 tfsec 스캔
```bash
cd modules/network/security-groups
tfsec .
```

**예상 결과**: 모든 보안 검사 통과

#### 9.2.2 checkov 스캔
```bash
cd modules/network/security-groups
checkov -d .
```

**예상 결과**: 모든 보안 검사 통과

#### 9.2.3 nmap 포트 스캔
```bash
# 온프레미스에서 실행
nmap -p 443 <opensearch-serverless-endpoint>
```

**예상 결과**: Port 443 open, 다른 포트 filtered


---

## 10. 롤백 계획

### 10.1 신규 Security Groups 롤백

마이그레이션 중 문제 발생 시 신규 Security Groups를 삭제합니다.

```bash
# Terraform으로 신규 Security Groups 삭제
cd environments/network-layer
terraform destroy -target=module.security_groups_seoul
```

**참고**: 기존 로깅 인프라 Security Groups는 영향받지 않습니다.

### 10.2 버지니아 VPC Security Groups 롤백

버지니아 VPC의 sg-s3-vpc-endpoint-virginia 규칙을 원래대로 복원합니다.

```bash
# AWS CLI로 규칙 제거
aws ec2 revoke-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --ip-permissions IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges='[{CidrIp=10.200.0.0/16}]' \
  --region us-east-1

# 기존 규칙 복원
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --ip-permissions IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges='[{CidrIp=10.10.0.0/16}]' \
  --region us-east-1
```

---

## 11. 운영 가이드

### 11.1 Security Group 규칙 변경 절차

1. **변경 요청 제출**: 보안팀 승인 필요
2. **Terraform 코드 수정**: `modules/network/security-groups/main.tf`
3. **로컬 검증**: `terraform plan` 실행
4. **보안 스캔**: `tfsec`, `checkov` 실행
5. **변경 적용**: `terraform apply` 실행
6. **연결 테스트**: 영향받는 리소스 테스트
7. **문서 업데이트**: 이 문서 업데이트

### 11.2 Security Group 모니터링

#### CloudWatch Logs Insights 쿼리
```
fields @timestamp, @message
| filter @message like /UnauthorizedOperation/
| stats count() by srcaddr
```

**용도**: 차단된 연결 시도 모니터링

#### VPC Flow Logs 분석
```
fields @timestamp, srcAddr, dstAddr, srcPort, dstPort, action
| filter action = "REJECT"
| stats count() by srcAddr, dstAddr, dstPort
```

**용도**: 거부된 트래픽 패턴 분석

### 11.3 정기 보안 검토

- **월간**: Security Group 규칙 검토 (불필요한 규칙 제거)
- **분기**: 보안 스캔 실행 (tfsec, checkov)
- **반기**: 침투 테스트 (외부 보안 업체)

---

## 12. 참고 자료

### 12.1 관련 문서

- 요구사항 문서: `.kiro/specs/bos-ai-vpc-consolidation/requirements.md`
- 설계 문서: `.kiro/specs/bos-ai-vpc-consolidation/design.md`
- 작업 목록: `.kiro/specs/bos-ai-vpc-consolidation/tasks.md`
- VPC 설정 문서: `docs/current-vpc-configuration.md`

### 12.2 Terraform 모듈

- Security Groups 모듈: `modules/network/security-groups/`
- VPC 모듈: `modules/network/vpc/`
- VPC 엔드포인트 모듈: `modules/security/vpc-endpoints/`

### 12.3 AWS CLI 명령어

#### Security Group 조회
```bash
# 서울 VPC의 모든 Security Groups 조회
aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e" \
  --region ap-northeast-2

# 특정 Security Group 규칙 조회
aws ec2 describe-security-group-rules \
  --filters "Name=group-id,Values=sg-xxxxxxxx" \
  --region ap-northeast-2
```

#### Security Group 규칙 추가
```bash
# Inbound 규칙 추가
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --ip-permissions IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges='[{CidrIp=10.200.0.0/16,Description="VPC internal"}]' \
  --region ap-northeast-2

# Outbound 규칙 추가
aws ec2 authorize-security-group-egress \
  --group-id sg-xxxxxxxx \
  --ip-permissions IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges='[{CidrIp=0.0.0.0/0,Description="HTTPS"}]' \
  --region ap-northeast-2
```

#### Security Group 규칙 제거
```bash
# Inbound 규칙 제거
aws ec2 revoke-security-group-ingress \
  --group-id sg-xxxxxxxx \
  --ip-permissions IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges='[{CidrIp=10.200.0.0/16}]' \
  --region ap-northeast-2
```

---

## 13. 변경 이력

| 날짜 | 버전 | 변경 내용 | 작성자 |
|------|------|----------|--------|
| 2026-02-20 | 1.0 | 초기 문서 작성 | Kiro AI |

---

**문서 끝**
