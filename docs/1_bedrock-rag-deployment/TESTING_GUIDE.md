# Testing Guide

## Overview

이 가이드는 AWS Bedrock RAG 인프라의 테스트 전략과 실행 방법을 설명합니다.

## Testing Strategy

프로젝트는 다층 테스트 전략을 사용합니다:

1. **Terraform Validation**: 구문 및 구성 검증
2. **Policy-as-Code Tests**: 보안, 규정 준수, 비용 최적화 정책 검증
3. **Property-Based Tests**: 범용 속성 검증
4. **Unit Tests**: 특정 시나리오 및 엣지 케이스 검증
5. **Integration Tests**: 실제 AWS 리소스 배포 및 통합 검증

## Test Types

### 1. Terraform Validation

**목적**: Terraform 코드의 구문 및 구성 검증

**도구**: 
- `terraform fmt`: 코드 포맷팅 검증
- `terraform validate`: 구성 유효성 검증
- `tflint`: 정적 분석 및 모범 사례 검증

**실행 방법**:
```bash
./scripts/terraform-validate.sh
```

**검증 항목**:
- Terraform 구문 오류
- 변수 타입 및 검증 규칙
- 리소스 구성 오류
- 모범 사례 위반
- 하드코딩된 자격 증명
- 누락된 태그

### 2. Policy-as-Code Tests

**목적**: 보안, 규정 준수, 비용 최적화 정책 검증

**도구**: OPA (Open Policy Agent) / Conftest

**정책 파일**:
- `policies/security.rego`: 보안 정책
- `policies/compliance.rego`: 규정 준수 정책
- `policies/cost.rego`: 비용 최적화 정책

**실행 방법**:
```bash
# 모든 정책 테스트
./scripts/run-policy-tests.sh

# 보안 정책만 테스트
./scripts/run-policy-tests.sh --security

# 규정 준수 정책만 테스트
./scripts/run-policy-tests.sh --compliance

# 비용 정책만 테스트
./scripts/run-policy-tests.sh --cost

# 특정 디렉토리만 테스트
./scripts/run-policy-tests.sh --dir environments/network-layer
```

**검증 항목**:

**보안 정책**:
- S3 버킷 버전 관리 및 암호화
- IAM 정책 최소 권한 원칙
- KMS 키 자동 로테이션
- VPC 보안 그룹 규칙
- CloudTrail 로깅
- 리소스 태깅

**규정 준수 정책**:
- 데이터 보존 정책
- 백업 구성
- 모니터링 및 로깅
- 고가용성 구성
- 상태 관리
- 멀티 리전 구성

**비용 최적화 정책**:
- S3 라이프사이클 정책
- Lambda 리소스 할당
- OpenSearch OCU 사용량
- CloudWatch 로그 보존
- 비용 할당 태그

### 3. Property-Based Tests

**목적**: 모든 유효한 입력에 대해 범용 속성 검증

**도구**: Go + Gopter

**위치**: `tests/properties/`

**실행 방법**:
```bash
cd tests
go test ./properties/... -v
```

**주요 속성**:
- VPC CIDR 비중첩
- VPC Peering 양방향 라우팅
- 멀티 AZ 서브넷 분산
- No-IGW 정책
- S3 버킷 보안 구성
- Lambda 리소스 제약
- IAM 정책 제한
- KMS 키 정책

### 4. Unit Tests

**목적**: 특정 시나리오 및 엣지 케이스 검증

**도구**: Go + Testify

**위치**: `tests/unit/`

**실행 방법**:
```bash
cd tests
go test ./unit/... -v
```

**검증 항목**:
- VPN import 구성
- Lambda 함수 로직
- 문서 청킹 전략
- 오류 처리

### 5. Integration Tests

**목적**: 실제 AWS 리소스 배포 및 통합 검증

**도구**: Terratest

**위치**: `tests/integration/`

**실행 방법**:
```bash
# 모든 통합 테스트
./scripts/run-integration-tests.sh

# 특정 테스트만 실행
./scripts/run-integration-tests.sh -r TestVPCPeering

# 클린업 건너뛰기 (디버깅용)
./scripts/run-integration-tests.sh -s

# 타임아웃 및 병렬 실행 조정
./scripts/run-integration-tests.sh -t 90m -p 4
```

**테스트 파일**:
- `vpc_peering_test.go`: VPC Peering 연결 및 라우팅
- `s3_replication_test.go`: S3 교차 리전 복제
- `lambda_invocation_test.go`: Lambda 함수 호출 및 S3 이벤트
- `bedrock_kb_test.go`: Bedrock Knowledge Base 및 OpenSearch

**비용 주의**: 통합 테스트는 실제 AWS 리소스를 배포하므로 비용이 발생합니다 (~$5-15/실행).

## Test Execution Order

권장 테스트 실행 순서:

1. **Terraform Validation** (빠름, 무료)
   ```bash
   ./scripts/terraform-validate.sh
   ```

2. **Policy-as-Code Tests** (빠름, 무료)
   ```bash
   ./scripts/run-policy-tests.sh
   ```

3. **Property-Based Tests** (중간, 무료)
   ```bash
   cd tests && go test ./properties/... -v
   ```

4. **Unit Tests** (빠름, 무료)
   ```bash
   cd tests && go test ./unit/... -v
   ```

5. **Integration Tests** (느림, 비용 발생)
   ```bash
   ./scripts/run-integration-tests.sh
   ```

## CI/CD Integration

### Pre-commit Hooks

`.git/hooks/pre-commit`:
```bash
#!/bin/bash
set -e

echo "Running pre-commit checks..."

# Terraform validation
./scripts/terraform-validate.sh

# Policy tests
./scripts/run-policy-tests.sh

echo "Pre-commit checks passed!"
```

### GitHub Actions

`.github/workflows/test.yml`:
```yaml
name: Tests

on: [push, pull_request]

jobs:
  validation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
      - name: Terraform Validation
        run: ./scripts/terraform-validate.sh
      
  policy-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Conftest
        run: |
          wget https://github.com/open-policy-agent/conftest/releases/download/v0.48.0/conftest_0.48.0_Linux_x86_64.tar.gz
          tar xzf conftest_0.48.0_Linux_x86_64.tar.gz
          sudo mv conftest /usr/local/bin/
      - name: Run Policy Tests
        run: ./scripts/run-policy-tests.sh
  
  property-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Go
        uses: actions/setup-go@v4
        with:
          go-version: '1.21'
      - name: Run Property Tests
        run: |
          cd tests
          go test ./properties/... -v
  
  integration-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    steps:
      - uses: actions/checkout@v3
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - name: Run Integration Tests
        run: ./scripts/run-integration-tests.sh
```

## Test Coverage

### Current Coverage

- **Terraform Validation**: 100% (모든 .tf 파일)
- **Policy Tests**: 47개 정책 규칙
- **Property Tests**: 47개 속성
- **Unit Tests**: 주요 컴포넌트
- **Integration Tests**: 4개 주요 통합 시나리오

### Coverage Goals

- Terraform Validation: 100% ✓
- Policy Tests: 모든 보안 및 규정 준수 요구사항 ✓
- Property Tests: 모든 설계 속성 ✓
- Unit Tests: 80%+ 코드 커버리지
- Integration Tests: 주요 워크플로우 ✓

## Troubleshooting

### Terraform Validation Failures

**문제**: 포맷 오류
```bash
terraform fmt -recursive .
```

**문제**: 구성 오류
- 변수 타입 확인
- 리소스 종속성 확인
- Provider 구성 확인

### Policy Test Failures

**문제**: 태그 누락
```hcl
tags = {
  Project     = "BOS-AI-RAG"
  Environment = "prod"
  ManagedBy   = "Terraform"
  CostCenter  = "AI-Infrastructure"
}
```

**문제**: 보안 구성 누락
- S3 버전 관리 활성화
- KMS 암호화 구성
- IAM 최소 권한 정책

### Property Test Failures

**문제**: 반례 발견
1. 반례 분석
2. 코드 또는 테스트 수정
3. 재실행

### Integration Test Failures

**문제**: AWS 권한 부족
- IAM 권한 확인
- AWS 자격 증명 확인

**문제**: 리소스 할당량 초과
- AWS Service Quotas 확인
- 할당량 증가 요청

**문제**: Bedrock 모델 액세스 거부
- AWS Console → Bedrock → Model access
- 필요한 모델 활성화

## Best Practices

1. **로컬에서 먼저 테스트**: CI/CD 전에 로컬에서 모든 테스트 실행
2. **점진적 테스트**: 빠른 테스트부터 느린 테스트 순으로 실행
3. **비용 모니터링**: 통합 테스트 비용 추적
4. **클린업 확인**: 통합 테스트 후 리소스 정리 확인
5. **테스트 격리**: 각 테스트는 독립적으로 실행 가능해야 함
6. **의미 있는 오류 메시지**: 실패 시 명확한 오류 메시지 제공
7. **문서화**: 새로운 테스트 추가 시 문서 업데이트

## Cost Management

### Test Cost Estimation

| Test Type | Duration | Cost | Frequency |
|-----------|----------|------|-----------|
| Terraform Validation | 1-2분 | $0 | 매 커밋 |
| Policy Tests | 1-2분 | $0 | 매 커밋 |
| Property Tests | 5-10분 | $0 | 매 커밋 |
| Unit Tests | 2-5분 | $0 | 매 커밋 |
| Integration Tests | 30-60분 | $5-15 | 일일/주간 |

### Cost Optimization

1. **선택적 실행**: 필요한 테스트만 실행
2. **병렬 실행**: 통합 테스트 병렬화로 시간 단축
3. **스케줄링**: 통합 테스트는 야간 또는 주간 실행
4. **리소스 재사용**: 가능한 경우 테스트 리소스 재사용
5. **즉시 클린업**: 테스트 완료 후 즉시 리소스 삭제

## References

- [Terraform Testing Best Practices](https://www.terraform.io/docs/language/modules/testing-experiment.html)
- [OPA Policy Language](https://www.openpolicyagent.org/docs/latest/policy-language/)
- [Terratest Documentation](https://terratest.gruntwork.io/)
- [Property-Based Testing](https://hypothesis.works/articles/what-is-property-based-testing/)
- [AWS Testing Best Practices](https://docs.aws.amazon.com/wellarchitected/latest/framework/test-and-validate.html)
