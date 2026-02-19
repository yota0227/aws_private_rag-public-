terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      configuration_aliases = [aws.requester, aws.accepter]
    }
  }
}

resource "aws_vpc_peering_connection" "main" {
  provider = aws.requester

  vpc_id      = var.vpc_id
  peer_vpc_id = var.peer_vpc_id
  peer_region = var.peer_region
  auto_accept = false # Cross-region peering requires manual acceptance

  tags = merge(
    var.tags,
    {
      Name = "vpc-peering-${var.vpc_id}-to-${var.peer_vpc_id}"
    }
  )
}

resource "aws_vpc_peering_connection_accepter" "peer" {
  provider = aws.accepter

  vpc_peering_connection_id = aws_vpc_peering_connection.main.id
  auto_accept               = var.auto_accept

  tags = merge(
    var.tags,
    {
      Name = "vpc-peering-accepter-${var.peer_vpc_id}"
    }
  )
}

# Wait for peering connection to be active before adding routes
resource "time_sleep" "wait_for_peering" {
  depends_on = [aws_vpc_peering_connection_accepter.peer]

  create_duration = "30s"
}

# Add routes in requester VPC route tables
resource "aws_route" "requester_to_peer" {
  provider = aws.requester
  count    = length(var.requester_route_table_ids)

  route_table_id            = var.requester_route_table_ids[count.index]
  destination_cidr_block    = var.peer_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection.main.id

  depends_on = [time_sleep.wait_for_peering]
}

# Add routes in accepter VPC route tables
resource "aws_route" "accepter_to_requester" {
  provider = aws.accepter
  count    = length(var.accepter_route_table_ids)

  route_table_id            = var.accepter_route_table_ids[count.index]
  destination_cidr_block    = data.aws_vpc.requester.cidr_block
  vpc_peering_connection_id = aws_vpc_peering_connection.main.id

  depends_on = [time_sleep.wait_for_peering]
}

# Data source to get requester VPC CIDR
data "aws_vpc" "requester" {
  provider = aws.requester
  id       = var.vpc_id
}
