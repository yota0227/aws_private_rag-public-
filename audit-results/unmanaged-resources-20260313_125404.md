# AWS 미관리 리소스 감사 보고서
생성일: 2026-03-13 12:54:04


## Region: ap-northeast-2
---
[0;36m[ap-northeast-2] ManagedBy 태그 없는 리소스 조회 중...[0m
  전체 태그된 리소스: 0
  Terraform 관리: 0
  [1;33m미관리 (수동 생성 추정): 0[0m

[0;36m[ap-northeast-2] 비용 발생 가능 리소스 전수 조사...[0m

[0;32m  [EC2 Instances][0m

[0;32m  [NAT Gateways] (~$32/월 + 데이터 처리)[0m

[0;32m  [Elastic IPs] (미사용 시 $3.6/월)[0m

[0;32m  [VPC Endpoints] (Interface: ~$7.2/월 each)[0m

[0;32m  [Transit Gateways] (~$36/월 per attachment)[0m

[0;32m  [VPN Connections] (~$36/월)[0m

[0;32m  [Lambda Functions][0m

[0;32m  [S3 Buckets] (전체 계정)[0m

[0;32m  [OpenSearch Serverless][0m

[0;32m  [Bedrock Knowledge Bases][0m

[0;32m  [API Gateways][0m

[0;32m  [KMS Keys] ($1/월 per key)[0m

[0;32m  [CloudWatch Log Groups] (저장 비용 발생)[0m

[0;32m  [Secrets Manager] ($0.40/월 per secret)[0m

[0;32m  [Route53 Resolver Endpoints] ($0.125/hr per ENI)[0m

[0;32m  [DynamoDB Tables][0m


## Region: us-east-1
---
[0;36m[us-east-1] ManagedBy 태그 없는 리소스 조회 중...[0m
  전체 태그된 리소스: 0
  Terraform 관리: 0
  [1;33m미관리 (수동 생성 추정): 0[0m

[0;36m[us-east-1] 비용 발생 가능 리소스 전수 조사...[0m

[0;32m  [EC2 Instances][0m

[0;32m  [NAT Gateways] (~$32/월 + 데이터 처리)[0m

[0;32m  [Elastic IPs] (미사용 시 $3.6/월)[0m

[0;32m  [VPC Endpoints] (Interface: ~$7.2/월 each)[0m

[0;32m  [Transit Gateways] (~$36/월 per attachment)[0m

[0;32m  [VPN Connections] (~$36/월)[0m

[0;32m  [Lambda Functions][0m

[0;32m  [OpenSearch Serverless][0m

[0;32m  [Bedrock Knowledge Bases][0m

[0;32m  [API Gateways][0m

[0;32m  [KMS Keys] ($1/월 per key)[0m

[0;32m  [CloudWatch Log Groups] (저장 비용 발생)[0m

[0;32m  [Secrets Manager] ($0.40/월 per secret)[0m

[0;32m  [Route53 Resolver Endpoints] ($0.125/hr per ENI)[0m

[0;32m  [DynamoDB Tables][0m


---
## 다음 단계
1. [미관리] 표시된 리소스 -> Terraform import 또는 삭제 결정
2. [미사용-비용발생] 표시된 리소스 -> 즉시 삭제 검토
3. CloudWatch Log Groups 보존 기간 설정 (무제한 -> 30일 등)
4. 사용하지 않는 VPC Endpoint 제거
