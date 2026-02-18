# AWS Bedrock RAG Infrastructure

AWS Bedrock 기반 RAG(Retrieval-Augmented Generation) 시스템을 위한 Terraform IaC 프로젝트입니다.

## 🏗️ 아키텍처

- **서울 리전 (ap-northeast-2)**: Transit Bridge, VPN 연결, 문서 저장
- **미국 리전 (us-east-1)**: AI 워크로드 (Bedrock, OpenSearch, Lambda)
- **VPC Peering**: 서울-미국 간 프라이빗 네트워크 연결
- **No-IGW 정책**: 모든 VPC에서 인터넷 게이트웨이 없음

## 📁 프로젝트 구조

```
bos-ai-infra/
├── modules/                    # 재사용 가능한 Terraform 모듈
│   ├── network/               # VPC, Peering, Security Groups
│   ├── security/              # KMS, IAM, VPC Endpoints
│   └── ai-workload/           # S3, Lambda, OpenSearch, Bedrock
├── environments/              # 환경별 배포 구성
│   ├── global/backend/        # Terraform 백엔드
│   ├── network-layer/         # 네트워크 레이어
│   └── app-layer/bedrock-rag/ # 애플리케이션 레이어
├── lambda/                    # Lambda 함수 코드
├── tests/                     # 테스트 코드
│   ├── properties/            # Property-based tests
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
├── policies/                  # Policy-as-Code (OPA)
├── scripts/                   # 유틸리티 스크립트
└── docs/                      # 문서
```

## 🚀 빠른 시작

### 사전 요구사항

- Terraform >= 1.5.0
- AWS CLI 구성 완료
- Go >= 1.21 (테스트용)
- Python >= 3.11 (Lambda용)

### 배포 순서

1. **Global Backend 배포**
```bash
cd environments/global/backend
terraform init
terraform apply
```

2. **Network Layer 배포**
```bash
cd environments/network-layer
terraform init
terraform apply
```

3. **App Layer 배포**
```bash
cd environments/app-layer/bedrock-rag
terraform init
terraform apply
```

자세한 배포 가이드는 [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)를 참조하세요.

## 🧪 테스트

### Terraform 검증
```bash
./scripts/terraform-validate.sh
```

### Policy-as-Code 테스트
```bash
./scripts/run-policy-tests.sh
```

### Property 테스트
```bash
cd tests
go test -v ./properties/
```

### 통합 테스트 (비용 발생 주의!)
```bash
./scripts/run-integration-tests.sh
```

자세한 테스트 가이드는 [TESTING_GUIDE.md](docs/TESTING_GUIDE.md)를 참조하세요.

## 💰 예상 비용

| 시나리오 | 월 예상 비용 | 설명 |
|---------|------------|------|
| Baseline | $787-965 | 100GB 저장, 10K 쿼리/월 |
| Medium | $1,760-2,305 | 500GB 저장, 50K 쿼리/월 |
| High | $4,170-5,910 | 2TB 저장, 200K 쿼리/월 |

비용 추정 스크립트:
```bash
./scripts/cost-estimation.sh [baseline|medium|high]
```

## 📚 문서

- [배포 가이드](docs/DEPLOYMENT_GUIDE.md) - 전체 배포 절차
- [운영 가이드](docs/OPERATIONAL_RUNBOOK.md) - 일상 운영 및 문제 해결
- [테스트 가이드](docs/TESTING_GUIDE.md) - 테스트 전략 및 실행 방법

## 🔒 보안

- **암호화**: 모든 데이터는 KMS 고객 관리형 키로 암호화
- **네트워크 격리**: PrivateLink를 통한 AWS 서비스 접근
- **최소 권한**: IAM 정책은 최소 권한 원칙 적용
- **감사**: CloudTrail로 모든 API 호출 로깅

## 🏷️ 주요 기능

- ✅ **Multi-Region**: 서울과 미국 리전에 걸친 배포
- ✅ **VPC Peering**: 리전 간 프라이빗 네트워크 연결
- ✅ **Cross-Region Replication**: S3 교차 리전 복제
- ✅ **Event-Driven**: S3 이벤트 → Lambda → Bedrock 파이프라인
- ✅ **Semantic Chunking**: 문서 타입별 최적화된 청킹 전략
- ✅ **Vector Search**: OpenSearch Serverless 벡터 DB
- ✅ **Monitoring**: CloudWatch 대시보드, 알람, 로그
- ✅ **Cost Optimization**: Intelligent-Tiering, Lifecycle 정책

## 🤝 기여

이슈나 풀 리퀘스트를 환영합니다!

## 📄 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.

## 📞 지원

문제가 발생하면 [Issues](../../issues)에 등록해주세요.
