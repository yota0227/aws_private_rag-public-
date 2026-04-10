# Neptune Graph DB 클러스터 및 인스턴스 구성
# RTL Knowledge Graph용 AWS Neptune 리소스
# Requirements: 16.1, 16.2, 16.14

locals {
  # 공통 태그 병합: 필수 태그 + 사용자 지정 태그
  tags = merge(var.common_tags, {
    Project     = "BOS-AI"
    Environment = var.environment
    ManagedBy   = "terraform"
    Layer       = "app"
  })
}

# Neptune 서브넷 그룹 — Private Subnet에만 배포
resource "aws_neptune_subnet_group" "main" {
  name       = "${var.project_name}-neptune-subnet-${var.environment}"
  subnet_ids = var.private_subnet_ids

  tags = merge(local.tags, {
    Name = "${var.project_name}-neptune-subnet-${var.environment}"
  })
}

# Neptune 클러스터 — KMS 암호화, IAM DB 인증, 백업 구성
resource "aws_neptune_cluster" "main" {
  cluster_identifier = "${var.project_name}-neptune-${var.environment}"
  engine             = "neptune"
  engine_version     = "1.3.1.0"

  # 암호화 설정 (Requirements: 16.2)
  storage_encrypted = true
  kms_key_arn       = var.kms_key_arn

  # 네트워크 설정
  vpc_security_group_ids    = [aws_security_group.neptune.id]
  neptune_subnet_group_name = aws_neptune_subnet_group.main.name

  # IAM DB 인증 활성화
  iam_database_authentication_enabled = true

  # 백업 설정
  backup_retention_period   = 7
  preferred_backup_window   = "03:00-04:00"
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project_name}-neptune-final-${var.environment}"

  # 변경 적용 정책 — 유지보수 윈도우에 적용
  apply_immediately = false

  tags = merge(local.tags, {
    Name    = "${var.project_name}-neptune-${var.environment}"
    Purpose = "RTL Knowledge Graph"
  })
}

# Neptune 클러스터 인스턴스 — 비용 최적화 db.t4g.medium
resource "aws_neptune_cluster_instance" "main" {
  identifier         = "${var.project_name}-neptune-instance-${var.environment}"
  cluster_identifier = aws_neptune_cluster.main.id
  instance_class     = var.neptune_instance_class
  engine             = "neptune"

  tags = merge(local.tags, {
    Name    = "${var.project_name}-neptune-instance-${var.environment}"
    Purpose = "RTL Knowledge Graph Instance"
  })
}
