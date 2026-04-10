# Neptune Graph Knowledge 모듈 변수 정의
# Requirements: 16.1, 16.2, 16.3, 16.14

variable "project_name" {
  description = "프로젝트명 (리소스 네이밍에 사용)"
  type        = string
  default     = "bos-ai"
}

variable "environment" {
  description = "환경명 (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "vpc_id" {
  description = "Neptune 클러스터가 배포될 VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "Neptune 서브넷 그룹에 사용할 Private Subnet ID 목록"
  type        = list(string)
}

variable "kms_key_arn" {
  description = "Neptune 스토리지 암호화에 사용할 KMS CMK ARN"
  type        = string
}

variable "neptune_instance_class" {
  description = "Neptune 인스턴스 클래스 (비용 최적화: db.t4g.medium 권장)"
  type        = string
  default     = "db.t4g.medium"
}

variable "rtl_parser_lambda_sg_id" {
  description = "RTL Parser Lambda Security Group ID (Neptune 8182 포트 인바운드 허용 대상)"
  type        = string
}

variable "lambda_handler_sg_id" {
  description = "Lambda Handler Security Group ID (Neptune 8182 포트 인바운드 허용 대상)"
  type        = string
}

variable "common_tags" {
  description = "모든 리소스에 적용할 공통 태그"
  type        = map(string)
  default     = {}
}
