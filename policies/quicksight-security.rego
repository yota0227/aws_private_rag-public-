package main

# QuickSight Security Policies
# Requirements: 4.9, 7.5, 7.6
#
# 1. deny_quicksight_sg_virginia_direct
#    - Quick VPC Connection SG에 Virginia CIDR(10.20.0.0/16) 직접 아웃바운드 금지
#
# 2. deny_quicksight_sg_open_egress
#    - Quick 관련 SG에 0.0.0.0/0 아웃바운드 금지
#
# 3. deny_quicksight_s3_public
#    - Quick S3 버킷 퍼블릭 액세스 차단 비활성화 시 deny

virginia_cidr := "10.20.0.0/16"

#######################
# Rule 1: Virginia 직접 접근 차단
#######################

deny[msg] {
    resource := input.resource.aws_security_group[name]
    contains(name, "quicksight")
    contains(name, "vpc_conn")
    rule := resource.egress[_]
    rule.cidr_blocks[_] == virginia_cidr
    msg := sprintf(
        "Security group '%s' has direct outbound rule to Virginia CIDR (%s). QuickSight VPC Connection must route through Seoul VPC Peering only (Requirement 4.9)",
        [name, virginia_cidr]
    )
}

#######################
# Rule 2: 0.0.0.0/0 아웃바운드 금지
#######################

deny[msg] {
    resource := input.resource.aws_security_group[name]
    contains(name, "quicksight")
    rule := resource.egress[_]
    rule.cidr_blocks[_] == "0.0.0.0/0"
    msg := sprintf(
        "Security group '%s' has open egress (0.0.0.0/0). QuickSight SGs must restrict outbound to explicit CIDRs only (Requirement 7.5)",
        [name]
    )
}

#######################
# Rule 3: S3 퍼블릭 액세스 차단
#######################

deny[msg] {
    resource := input.resource.aws_s3_bucket_public_access_block[name]
    contains(name, "quicksight")
    not resource.block_public_acls == true
    msg := sprintf("S3 bucket '%s' must have block_public_acls enabled (Requirement 7.6)", [name])
}

deny[msg] {
    resource := input.resource.aws_s3_bucket_public_access_block[name]
    contains(name, "quicksight")
    not resource.block_public_policy == true
    msg := sprintf("S3 bucket '%s' must have block_public_policy enabled (Requirement 7.6)", [name])
}

deny[msg] {
    resource := input.resource.aws_s3_bucket_public_access_block[name]
    contains(name, "quicksight")
    not resource.ignore_public_acls == true
    msg := sprintf("S3 bucket '%s' must have ignore_public_acls enabled (Requirement 7.6)", [name])
}

deny[msg] {
    resource := input.resource.aws_s3_bucket_public_access_block[name]
    contains(name, "quicksight")
    not resource.restrict_public_buckets == true
    msg := sprintf("S3 bucket '%s' must have restrict_public_buckets enabled (Requirement 7.6)", [name])
}
