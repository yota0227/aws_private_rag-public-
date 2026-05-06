# Tech Stack & Build System

## Infrastructure as Code

- Terraform (>= 1.0) — all AWS resources are managed via Terraform
- TFLint with AWS plugin (v0.29.0) and recommended Terraform preset
- TFLint enforces: snake_case naming, documented variables/outputs, typed variables, required tags (Project, Environment, ManagedBy)
- OPA/Rego policies in `policies/` for security, cost, and compliance validation

## AWS Services

- Bedrock (Claude + Titan Embeddings) — AI model and embedding generation
- OpenSearch Serverless — vector database
- Lambda (Python 3.12) — document processing
- API Gateway (Private REST) — RAG API entry point
- S3 with cross-region replication (Seoul → Virginia)
- Transit Gateway, VPC Peering, VPC Endpoints
- Route53 Private Hosted Zone + Resolver Endpoints
- KMS, IAM, CloudWatch, CloudTrail

## Application Code

- Python 3.12 for Lambda functions (boto3, standard library only)
- Node.js for MCP bridge server (Express + @modelcontextprotocol/sdk)
- Go 1.21 for infrastructure tests (testify + gopter for property-based testing)

## Testing

- Unit tests: `tests/unit/` (Go)
- Integration tests: `tests/integration/` (Go) — VPC peering, S3 replication, Lambda invocation, Bedrock KB
- Property-based tests: `tests/properties/` (Go, gopter) — comprehensive coverage of all infrastructure layers
- Policy tests: OPA/Rego in `policies/`

## Local Python Environment

- **Python 경로:** `C:\Users\Seung-IlWoo\AppData\Local\Programs\Python\Python313\python.exe`
- **런처:** `py` (C:\Users\Seung-IlWoo\AppData\Local\Programs\Python\Launcher\py.exe)
- **버전:** Python 3.13.9
- **실행 방법:** 항상 `py` 명령어를 사용한다. `python` 또는 `python3`는 Windows App Alias로 동작하지 않음.
- **테스트 실행:** `py -m pytest` (rtl_parser_src 디렉토리에서)
- **패키지 설치:** `py -m pip install <package>`
- **주의:** Lambda 배포 대상은 Python 3.12이지만, 로컬 개발/테스트는 Python 3.13으로 수행. 3.12 전용 기능은 사용하지 않는다.

## Common Commands

```bash
# Python 테스트 실행 (RTL Parser)
cd environments/app-layer/bedrock-rag/rtl_parser_src
py -m pytest -v

# 특정 테스트 파일 실행
py -m pytest test_package_extractor_functions.py -v

# Terraform workflow (run from an environment directory)
terraform init
terraform plan
terraform apply

# Validate Terraform
terraform validate
tflint

# Run policy tests
bash scripts/run-policy-tests.sh

# Run integration tests
bash scripts/run-integration-tests.sh

# Validate Terraform across all environments
bash scripts/terraform-validate.sh

# Lambda: Python dependencies
py -m pip install -r lambda/document-processor/requirements.txt

# MCP bridge
cd mcp-bridge && npm install && npm start
```

## Terraform Conventions

- Backend: S3 + DynamoDB for state locking
- Provider aliases: `aws.seoul` (ap-northeast-2), `aws.us_east` (us-east-1)
- Common tags defined in `locals` block and merged per resource
- Variables use `.tfvars.example` files as templates (actual `.tfvars` are gitignored)
- Each module follows the standard `main.tf`, `variables.tf`, `outputs.tf` pattern
