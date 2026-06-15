# Neptune Graph Knowledge 모듈 변수 정의
# Virginia Backend VPC에 배포, Seoul Lambda는 VPC Peering 경유 접근
# Requirements: 16.1, 16.2, 16.3, 16.14

variable "project_name" {
  description = "프로젝트명 (리소스 네이밍에 사용)"
  type        = string
}

variable "environment" {
  description = "환경명 (dev, staging, prod)"
  type        = string
}

variable "vpc_id" {
  description = "Neptune 클러스터가 배포될 VPC ID (Virginia Backend VPC)"
  type        = string
}

variable "private_subnet_ids" {
  description = "Neptune 서브넷 그룹에 사용할 Private Subnet ID 목록 (Virginia)"
  type        = list(string)
}

variable "kms_key_arn" {
  description = "Neptune 스토리지 암호화에 사용할 KMS CMK ARN (Virginia)"
  type        = string
}

variable "neptune_instance_class" {
  description = "Neptune 인스턴스 클래스 (비용 최적화: db.t4g.medium 권장)"
  type        = string
  default     = "db.t4g.medium"
}

variable "seoul_vpc_cidr" {
  description = "Seoul Frontend VPC CIDR (VPC Peering 경유 Neptune 접근 허용 대상)"
  type        = string
  default     = "10.10.0.0/16"
}

variable "common_tags" {
  description = "공통 태그"
  type        = map(string)
  default     = {}
}
