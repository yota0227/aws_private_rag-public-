# Infrastructure Tests

이 디렉토리는 AWS Bedrock RAG 인프라의 Terraform 구성을 검증하는 테스트를 포함합니다.

## 테스트 구조

```
tests/
├── properties/          # Property-based tests (보편적 속성 검증)
│   └── backend_properties_test.go
├── unit/               # Unit tests (특정 예제 및 엣지 케이스)
├── integration/        # Integration tests (종단 간 테스트)
└── policies/           # Policy-as-code tests (OPA/Conftest)
```

## 테스트 유형

### Property-Based Tests

보편적인 속성이 모든 유효한 입력에 대해 성립하는지 검증합니다.

**예시**: Property 25 - Terraform State Backend Configuration
- 모든 Terraform 구성이 S3 백엔드를 사용하는지 확인
- 암호화가 활성화되어 있는지 확인
- DynamoDB 테이블이 상태 잠금에 사용되는지 확인

### Unit Tests

특정 예제와 엣지 케이스를 검증합니다.

**예시**:
- 특정 CIDR 블록 구성 테스트
- IAM 정책 JSON 구조 테스트
- 리소스 이름 패턴 테스트

### Integration Tests

실제 AWS 환경에서 인프라를 배포하고 검증합니다.

**예시**:
- VPC 피어링 연결 테스트
- S3 복제 테스트
- Lambda 호출 테스트

## 실행 방법

### 전제 조건

1. Go 1.21 이상 설치
2. Terraform 1.5 이상 설치
3. AWS 자격 증명 구성

### Property Tests 실행

```bash
cd tests
go test -v ./properties/
```

특정 테스트만 실행:

```bash
go test -v ./properties/ -run TestProperty25
```

### 모든 테스트 실행

```bash
cd tests
go test -v ./...
```

### 테스트 타임아웃 설정

Integration 테스트는 시간이 오래 걸릴 수 있습니다:

```bash
go test -v -timeout 30m ./integration/
```

## 테스트 작성 가이드

### Property Test 작성

Property test는 다음 형식을 따라야 합니다:

```go
// Property {번호}: {속성 이름}
// Feature: aws-bedrock-rag-deployment, Property {번호}: {속성 설명}
// Validates: Requirements {요구사항 번호}
//
// {속성에 대한 자세한 설명}
func TestProperty{번호}_{속성이름}(t *testing.T) {
    t.Parallel()
    
    // 테스트 구현
}
```

### Unit Test 작성

Unit test는 특정 시나리오를 검증합니다:

```go
func TestVPCCreation_ValidCIDR(t *testing.T) {
    t.Parallel()
    
    // Given
    cidr := "10.10.0.0/16"
    
    // When
    result := validateCIDR(cidr)
    
    // Then
    assert.True(t, result)
}
```

## CI/CD 통합

### GitHub Actions

```yaml
name: Infrastructure Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Go
        uses: actions/setup-go@v4
        with:
          go-version: '1.21'
      
      - name: Run Tests
        run: |
          cd tests
          go test -v ./properties/
```

## 문제 해결

### 의존성 설치 오류

```bash
cd tests
go mod download
go mod tidy
```

### HCL 파싱 오류

HCL 파일이 올바른 형식인지 확인:

```bash
terraform fmt -check -recursive ../environments/
```

### AWS 자격 증명 오류

AWS 자격 증명이 올바르게 구성되었는지 확인:

```bash
aws sts get-caller-identity
```

## 참고 자료

- [Terratest Documentation](https://terratest.gruntwork.io/)
- [Go Testing Package](https://pkg.go.dev/testing)
- [Property-Based Testing](https://en.wikipedia.org/wiki/Property_testing)
