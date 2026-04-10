# Variables for App Layer - Knowledge Graph (Neptune)
# Requirements: 16.4, 16.5, 16.15

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

variable "kms_key_arn" {
  description = "KMS CMK ARN for Neptune encryption"
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

variable "rtl_parser_lambda_role_name" {
  description = "RTL Parser Lambda IAM Role name for Neptune write policy attachment"
  type        = string
}
