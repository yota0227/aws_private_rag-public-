# Network Layer

이 디렉토리는 AWS Bedrock RAG 시스템의 네트워크 레이어를 정의합니다. 서울과 미국 리전에 VPC를 생성하고, VPC 피어링을 통해 연결하며, 보안 그룹을 구성합니다.

## Architecture

- **Seoul VPC (10.10.0.0/16)**: Transit Bridge 역할, VPN 연결 지점
- **US VPC (10.20.0.0/16)**: AI 워크로드 호스팅 (Bedrock, OpenSearch, Lambda)
- **VPC Peering**: 서울-미국 간 프라이빗 네트워크 연결
- **Security Groups**: Lambda, OpenSearch, VPC Endpoints용 보안 그룹

## Requirements

- Terraform >= 1.5.0
- AWS CLI configured with appropriate credentials
- S3 backend bucket and DynamoDB table (created by global/backend)

## Deployment

### 1. Initialize Terraform

```bash
cd environments/network-layer
terraform init
```

### 2. Configure Variables

Copy the example variables file and customize:

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your specific values
```

### 3. Plan Deployment

```bash
terraform plan
```

### 4. Apply Configuration

```bash
terraform apply
```

## Outputs

이 레이어는 다음 출력값을 제공하며, app-layer에서 `terraform_remote_state`를 통해 참조할 수 있습니다:

- **VPC IDs**: `seoul_vpc_id`, `us_vpc_id`
- **Subnet IDs**: `seoul_private_subnet_ids`, `us_private_subnet_ids`
- **Security Group IDs**: `us_lambda_security_group_id`, `us_opensearch_security_group_id`, `us_vpc_endpoints_security_group_id`
- **Peering Connection**: `vpc_peering_connection_id`, `vpc_peering_status`

## Key Features

### No-IGW Policy

두 VPC 모두 Internet Gateway를 생성하지 않아 외부 인터넷 접근을 원천 차단합니다.

### Multi-AZ High Availability

각 VPC는 최소 2개의 가용 영역에 걸쳐 서브넷을 분산하여 고가용성을 보장합니다.

### VPC Peering

서울과 미국 VPC 간 자동 수락 피어링 연결을 설정하고, 양방향 라우팅을 구성합니다.

### Security Groups

- **Lambda SG**: Bedrock, S3, OpenSearch VPC 엔드포인트로의 아웃바운드 HTTPS 허용
- **OpenSearch SG**: Lambda와 Bedrock 서비스로부터의 인바운드 HTTPS 허용
- **VPC Endpoints SG**: VPC CIDR 및 피어링된 VPC CIDR로부터의 인바운드 HTTPS 허용

## Common Tags

모든 리소스에 다음 태그가 자동으로 적용됩니다:

- `Project`: BOS-AI-RAG
- `Environment`: dev/staging/prod
- `ManagedBy`: Terraform
- `Layer`: network
- `Region`: ap-northeast-2 또는 us-east-1

## Validation

### Requirements Validated

- **1.1**: Seoul과 US 리전에 겹치지 않는 CIDR 블록으로 VPC 생성
- **1.2**: VPC 피어링 연결 설정
- **1.4**: 양방향 트래픽 흐름을 위한 라우트 테이블 구성
- **1.6**: 고가용성을 위한 다중 AZ 프라이빗 서브넷 생성
- **1.7**: 최소 권한 보안 그룹 구성
- **1.9**: No-IGW 정책 적용
- **9.1**: 멀티 리전 배포를 위한 프로바이더 별칭 지원
- **9.2**: 서울과 미국 리전에 네트워크 인프라 배포
- **11.5**: 비용 할당 태그 적용
- **12.1, 12.2**: 모듈 구조 및 재사용성

## Troubleshooting

### VPC Peering Not Active

피어링 연결이 활성화되지 않은 경우:

```bash
aws ec2 describe-vpc-peering-connections --region ap-northeast-2
```

### Route Table Issues

라우트 테이블 확인:

```bash
aws ec2 describe-route-tables --region ap-northeast-2 --filters "Name=vpc-id,Values=<vpc-id>"
aws ec2 describe-route-tables --region us-east-1 --filters "Name=vpc-id,Values=<vpc-id>"
```

### Security Group Rules

보안 그룹 규칙 확인:

```bash
aws ec2 describe-security-groups --region us-east-1 --filters "Name=vpc-id,Values=<vpc-id>"
```

## Next Steps

네트워크 레이어 배포 후:

1. VPC 피어링 연결이 `active` 상태인지 확인
2. 라우트 테이블에 피어링 라우트가 추가되었는지 확인
3. app-layer 배포 진행
