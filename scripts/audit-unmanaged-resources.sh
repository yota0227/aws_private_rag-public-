#!/bin/bash
# =============================================================================
# AWS 미관리 리소스 탐지 스크립트
# Goal 1: Terraform으로 관리되지 않는 (콘솔에서 수동 생성된) 리소스 식별
# Goal 2: 비용 발생 리소스 중 Terraform 코드에 없는 것 = 비용 누수 후보
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

REGIONS=("ap-northeast-2" "us-east-1")
OUTPUT_DIR="audit-results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="${OUTPUT_DIR}/unmanaged-resources-${TIMESTAMP}.md"

mkdir -p "$OUTPUT_DIR"

echo -e "${BLUE}=== AWS 미관리 리소스 감사 시작 ===${NC}"
echo ""

# =============================================================================
# 1단계: ManagedBy 태그가 없는 리소스 탐지 (콘솔 생성 리소스)
# =============================================================================
detect_untagged_resources() {
    local region=$1
    echo -e "${CYAN}[$region] ManagedBy 태그 없는 리소스 조회 중...${NC}"

    local all_resources
    all_resources=$(aws resourcegroupstaggingapi get-resources \
        --region "$region" \
        --no-paginate \
        --output json 2>/dev/null || echo '{"ResourceTagMappingList":[]}')

    local managed_resources
    managed_resources=$(aws resourcegroupstaggingapi get-resources \
        --region "$region" \
        --tag-filters Key=ManagedBy,Values=Terraform \
        --no-paginate \
        --output json 2>/dev/null || echo '{"ResourceTagMappingList":[]}')

    local all_count
    all_count=$(echo "$all_resources" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('ResourceTagMappingList',[])))" 2>/dev/null || echo "0")
    local managed_count
    managed_count=$(echo "$managed_resources" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('ResourceTagMappingList',[])))" 2>/dev/null || echo "0")

    echo -e "  전체 태그된 리소스: ${all_count}"
    echo -e "  Terraform 관리: ${managed_count}"
    echo -e "  ${YELLOW}미관리 (수동 생성 추정): $((all_count - managed_count))${NC}"

    echo "$all_resources" | python3 -c "
import sys, json

data = json.load(sys.stdin)
resources = data.get('ResourceTagMappingList', [])

unmanaged = []
for r in resources:
    tags = {t['Key']: t['Value'] for t in r.get('Tags', [])}
    if tags.get('ManagedBy') != 'Terraform':
        unmanaged.append({
            'arn': r['ResourceARN'],
            'tags': tags
        })

for r in unmanaged:
    arn = r['arn']
    parts = arn.split(':')
    service = parts[2] if len(parts) > 2 else 'unknown'
    name = r['tags'].get('Name', 'N/A')
    print(f'  [{service}] {name} -> {arn}')
" 2>/dev/null || echo "  (파싱 실패)"
}

# =============================================================================
# 2단계: 비용 발생 리소스 직접 조회 (태그 유무 관계없이)
# =============================================================================
detect_cost_resources() {
    local region=$1
    echo ""
    echo -e "${CYAN}[$region] 비용 발생 가능 리소스 전수 조사...${NC}"

    # --- EC2 인스턴스 ---
    echo -e "\n${GREEN}  [EC2 Instances]${NC}"
    aws ec2 describe-instances \
        --region "$region" \
        --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,State.Name,Tags[?Key==`Name`].Value|[0],Tags[?Key==`ManagedBy`].Value|[0]]' \
        --output text 2>/dev/null | while read -r id type state name managed; do
        if [ "$state" != "terminated" ]; then
            local flag=""
            [ "$managed" != "Terraform" ] && flag="${RED}[미관리]${NC}"
            echo -e "    $flag $id ($type) - $state - $name"
        fi
    done || true

    # --- NAT Gateways ---
    echo -e "\n${GREEN}  [NAT Gateways] (~\$32/월 + 데이터 처리)${NC}"
    aws ec2 describe-nat-gateways \
        --region "$region" \
        --filter "Name=state,Values=available" \
        --query 'NatGateways[*].[NatGatewayId,VpcId,State,Tags[?Key==`Name`].Value|[0],Tags[?Key==`ManagedBy`].Value|[0]]' \
        --output text 2>/dev/null | while read -r id vpc state name managed; do
        local flag=""
        [ "$managed" != "Terraform" ] && flag="${RED}[미관리]${NC}"
        echo -e "    $flag $id ($vpc) - $name"
    done || true

    # --- Elastic IPs ---
    echo -e "\n${GREEN}  [Elastic IPs] (미사용 시 \$3.6/월)${NC}"
    aws ec2 describe-addresses \
        --region "$region" \
        --query 'Addresses[*].[AllocationId,PublicIp,AssociationId,Tags[?Key==`Name`].Value|[0],Tags[?Key==`ManagedBy`].Value|[0]]' \
        --output text 2>/dev/null | while read -r id ip assoc name managed; do
        local flag=""
        [ "$managed" != "Terraform" ] && flag="${RED}[미관리]${NC}"
        local unused=""
        [ "$assoc" = "None" ] && unused="${YELLOW}[미사용-비용발생]${NC}"
        echo -e "    $flag $unused $id ($ip) - $name"
    done || true

    # --- VPC Endpoints ---
    echo -e "\n${GREEN}  [VPC Endpoints] (Interface: ~\$7.2/월 each)${NC}"
    aws ec2 describe-vpc-endpoints \
        --region "$region" \
        --query 'VpcEndpoints[*].[VpcEndpointId,VpcEndpointType,ServiceName,State,Tags[?Key==`Name`].Value|[0],Tags[?Key==`ManagedBy`].Value|[0]]' \
        --output text 2>/dev/null | while read -r id type svc state name managed; do
        local flag=""
        [ "$managed" != "Terraform" ] && flag="${RED}[미관리]${NC}"
        echo -e "    $flag $id ($type) - $svc - $name"
    done || true

    # --- Transit Gateways ---
    echo -e "\n${GREEN}  [Transit Gateways] (~\$36/월 per attachment)${NC}"
    aws ec2 describe-transit-gateways \
        --region "$region" \
        --query 'TransitGateways[*].[TransitGatewayId,State,Tags[?Key==`Name`].Value|[0],Tags[?Key==`ManagedBy`].Value|[0]]' \
        --output text 2>/dev/null | while read -r id state name managed; do
        local flag=""
        [ "$managed" != "Terraform" ] && flag="${RED}[미관리]${NC}"
        echo -e "    $flag $id - $state - $name"
    done || true

    aws ec2 describe-transit-gateway-attachments \
        --region "$region" \
        --query 'TransitGatewayAttachments[*].[TransitGatewayAttachmentId,ResourceType,State,Tags[?Key==`Name`].Value|[0]]' \
        --output text 2>/dev/null | while read -r id rtype state name; do
        echo -e "      Attachment: $id ($rtype) - $state - $name"
    done || true

    # --- VPN Connections ---
    echo -e "\n${GREEN}  [VPN Connections] (~\$36/월)${NC}"
    aws ec2 describe-vpn-connections \
        --region "$region" \
        --query 'VpnConnections[?State!=\`deleted\`].[VpnConnectionId,State,Tags[?Key==\`Name\`].Value|[0],Tags[?Key==\`ManagedBy\`].Value|[0]]' \
        --output text 2>/dev/null | while read -r id state name managed; do
        local flag=""
        [ "$managed" != "Terraform" ] && flag="${RED}[미관리]${NC}"
        echo -e "    $flag $id - $state - $name"
    done || true

    # --- Lambda Functions ---
    echo -e "\n${GREEN}  [Lambda Functions]${NC}"
    local account_id
    account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
    aws lambda list-functions \
        --region "$region" \
        --query 'Functions[*].[FunctionName,Runtime,MemorySize,LastModified]' \
        --output text 2>/dev/null | while read -r name runtime mem modified; do
        local tags
        tags=$(aws lambda list-tags \
            --region "$region" \
            --resource "arn:aws:lambda:${region}:${account_id}:function:${name}" \
            --query 'Tags.ManagedBy' \
            --output text 2>/dev/null || echo "None")
        local flag=""
        [ "$tags" != "Terraform" ] && flag="${RED}[미관리]${NC}"
        echo -e "    $flag $name ($runtime, ${mem}MB) - Last: $modified"
    done || true

    # --- S3 Buckets (글로벌, Seoul에서만 조회) ---
    if [ "$region" = "ap-northeast-2" ]; then
        echo -e "\n${GREEN}  [S3 Buckets] (전체 계정)${NC}"
        aws s3api list-buckets \
            --query 'Buckets[*].[Name,CreationDate]' \
            --output text 2>/dev/null | while read -r name created; do
            local tags
            tags=$(aws s3api get-bucket-tagging \
                --bucket "$name" \
                --query 'TagSet[?Key==`ManagedBy`].Value|[0]' \
                --output text 2>/dev/null || echo "None")
            local flag=""
            [ "$tags" != "Terraform" ] && flag="${RED}[미관리]${NC}"
            echo -e "    $flag $name (Created: $created)"
        done || true
    fi

    # --- OpenSearch Serverless ---
    echo -e "\n${GREEN}  [OpenSearch Serverless]${NC}"
    aws opensearchserverless list-collections \
        --region "$region" \
        --query 'collectionSummaries[*].[name,id,status]' \
        --output text 2>/dev/null | while read -r name id status; do
        echo -e "    $name ($id) - $status"
    done || true

    # --- Bedrock Knowledge Bases ---
    echo -e "\n${GREEN}  [Bedrock Knowledge Bases]${NC}"
    aws bedrock-agent list-knowledge-bases \
        --region "$region" \
        --query 'knowledgeBaseSummaries[*].[name,knowledgeBaseId,status]' \
        --output text 2>/dev/null | while read -r name id status; do
        echo -e "    $name ($id) - $status"
    done || true

    # --- API Gateways ---
    echo -e "\n${GREEN}  [API Gateways]${NC}"
    aws apigateway get-rest-apis \
        --region "$region" \
        --query 'items[*].[name,id,createdDate]' \
        --output text 2>/dev/null | while read -r name id created; do
        echo -e "    $name ($id) - Created: $created"
    done || true

    # --- KMS Keys (Customer managed only) ---
    echo -e "\n${GREEN}  [KMS Keys] (\$1/월 per key)${NC}"
    aws kms list-keys \
        --region "$region" \
        --query 'Keys[*].KeyId' \
        --output text 2>/dev/null | tr '\t' '\n' | while read -r keyid; do
        [ -z "$keyid" ] && continue
        local info
        info=$(aws kms describe-key \
            --region "$region" \
            --key-id "$keyid" \
            --query 'KeyMetadata.[Description,KeyManager,KeyState]' \
            --output text 2>/dev/null || echo "N/A")
        if echo "$info" | grep -q "CUSTOMER"; then
            echo -e "    $keyid - $info"
        fi
    done || true

    # --- CloudWatch Log Groups ---
    echo -e "\n${GREEN}  [CloudWatch Log Groups] (저장 비용 발생)${NC}"
    aws logs describe-log-groups \
        --region "$region" \
        --query 'logGroups[*].[logGroupName,storedBytes,retentionInDays]' \
        --output text 2>/dev/null | while read -r name bytes retention; do
        local size_mb
        size_mb=$(echo "scale=2; ${bytes:-0} / 1048576" | bc 2>/dev/null || echo "0")
        local ret_display="${retention:-무제한}"
        [ "$ret_display" = "None" ] && ret_display="무제한"
        echo -e "    $name (${size_mb}MB, 보존: ${ret_display}일)"
    done || true

    # --- Secrets Manager ---
    echo -e "\n${GREEN}  [Secrets Manager] (\$0.40/월 per secret)${NC}"
    aws secretsmanager list-secrets \
        --region "$region" \
        --query 'SecretList[*].[Name,LastAccessedDate]' \
        --output text 2>/dev/null | while read -r name accessed; do
        echo -e "    $name (Last accessed: $accessed)"
    done || true

    # --- Route53 Resolver Endpoints ---
    echo -e "\n${GREEN}  [Route53 Resolver Endpoints] (\$0.125/hr per ENI)${NC}"
    aws route53resolver list-resolver-endpoints \
        --region "$region" \
        --query 'ResolverEndpoints[*].[Id,Name,Direction,Status,IpAddressCount]' \
        --output text 2>/dev/null | while read -r id name dir status ips; do
        echo -e "    $name ($id) - $dir - $status - ${ips} IPs"
    done || true

    # --- DynamoDB Tables ---
    echo -e "\n${GREEN}  [DynamoDB Tables]${NC}"
    aws dynamodb list-tables \
        --region "$region" \
        --query 'TableNames[*]' \
        --output text 2>/dev/null | tr '\t' '\n' | while read -r name; do
        [ -z "$name" ] && continue
        local billing
        billing=$(aws dynamodb describe-table \
            --region "$region" \
            --table-name "$name" \
            --query 'Table.BillingModeSummary.BillingMode' \
            --output text 2>/dev/null || echo "PROVISIONED")
        echo -e "    $name ($billing)"
    done || true
}

# =============================================================================
# 실행
# =============================================================================
{
    echo "# AWS 미관리 리소스 감사 보고서"
    echo "생성일: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    for region in "${REGIONS[@]}"; do
        echo ""
        echo "## Region: $region"
        echo "---"
        detect_untagged_resources "$region"
        detect_cost_resources "$region"
        echo ""
    done

    echo ""
    echo "---"
    echo "## 다음 단계"
    echo "1. [미관리] 표시된 리소스 -> Terraform import 또는 삭제 결정"
    echo "2. [미사용-비용발생] 표시된 리소스 -> 즉시 삭제 검토"
    echo "3. CloudWatch Log Groups 보존 기간 설정 (무제한 -> 30일 등)"
    echo "4. 사용하지 않는 VPC Endpoint 제거"
} 2>&1 | tee "$REPORT_FILE"

echo ""
echo -e "${GREEN}보고서 저장됨: ${REPORT_FILE}${NC}"
echo -e "${YELLOW}팁: 결과를 Terraform import 계획에 활용하세요${NC}"
