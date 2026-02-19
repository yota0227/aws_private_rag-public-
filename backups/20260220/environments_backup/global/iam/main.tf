# 1. 완장(Role) 본체 및 신뢰 관계 정의
resource "aws_iam_role" "engineer_role" {
  name = "BOS-AI-Engineer-Role"

  # 누가 이 완장을 찰 수 있는가?
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          # 두목님의 실제 계정 ARN (로그에 찍힌 값 기준)
          AWS = "arn:aws:iam::533335672315:user/seungil.woo"
        }
        # 보안 Condition을 잠시 제거하여 집(WFH)에서도 접속 가능하게 조치
      }
    ]
  })

  tags = {
    Project = "BOS-AI-TF"
    Owner   = "Seungil.Woo"
  }
}

# 2. 삭제되었던 관리자 권한 다시 연결
resource "aws_iam_role_policy_attachment" "admin_attach" {
  role       = aws_iam_role.engineer_role.name
  # 'iam' 섹션이 포함된 정확한 ARN으로 수정
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}