# Neptune Graph Knowledge 모듈 출력값
# Requirements: 16.1, 16.2, 16.3

output "neptune_cluster_endpoint" {
  description = "Neptune 클러스터 Writer 엔드포인트"
  value       = aws_neptune_cluster.main.endpoint
}

output "neptune_cluster_reader_endpoint" {
  description = "Neptune 클러스터 Reader 엔드포인트"
  value       = aws_neptune_cluster.main.reader_endpoint
}

output "neptune_cluster_id" {
  description = "Neptune 클러스터 ID"
  value       = aws_neptune_cluster.main.id
}

output "neptune_security_group_id" {
  description = "Neptune 전용 Security Group ID"
  value       = aws_security_group.neptune.id
}

output "neptune_subnet_group_name" {
  description = "Neptune 서브넷 그룹 이름"
  value       = aws_neptune_subnet_group.main.name
}
