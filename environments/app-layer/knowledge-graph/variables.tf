# Variables for App Layer - Knowledge Graph (Neptune)
# Neptune은 Virginia Backend VPC에 배포
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

variable "neptune_instance_class" {
  description = "Neptune 인스턴스 클래스 (비용 최적화: db.t4g.medium 권장)"
  type        = string
  default     = "db.t4g.medium"
}
