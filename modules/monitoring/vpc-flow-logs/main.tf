# VPC Flow Logs
resource "aws_flow_log" "main" {
  vpc_id          = var.vpc_id
  traffic_type    = var.traffic_type
  iam_role_arn    = var.iam_role_arn
  log_destination = var.cloudwatch_log_group_arn

  log_format = "$${version} $${account-id} $${interface-id} $${srcaddr} $${dstaddr} $${srcport} $${dstport} $${protocol} $${packets} $${bytes} $${start} $${end} $${action} $${log-status}"

  tags = merge(
    var.tags,
    {
      Name = "${var.vpc_name}-flow-logs"
      VPC  = var.vpc_name
    }
  )
}
