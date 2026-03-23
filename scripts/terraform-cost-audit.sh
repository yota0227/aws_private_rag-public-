#!/bin/bash
# =============================================================================
# Terraform 코드 기반 비용 리소스 분석 스크립트
# Goal 2: 코드에 정의된 리소스 vs 실제 AWS 리소스 비교 → 비용 누수 식별
#
# 동작 방식:
#   1) Terraform 코드에서 모든 aws_* 리소스 추출
#   2) 실제 AWS에서 비용 발생 리소스 조회
#   3) 코드에 없는데 AWS에 있는 리소스 = 비용 누수 후보
#   4) 코드에 있는데 AWS에 없는 리소스 = 미배포 또는 삭제됨
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

OUTPUT_DIR="audit-results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="${OUTPUT_DIR}/cost-drift-analysis-${TIMESTAMP}.md"
TF_RESOURCES_FILE="${OUTPUT_DIR}/tf-defined-resources.txt"

mkdir -p "$OUTPUT_DIR"

echo -e "${BLUE}=== Terraform 코드 기반 비용 분석 ===${NC}"
echo ""

# =============================================================================
# 1단계: Terraform 코드에서 비용 발생 리소스 추출
# =============================================================================
extract_tf_resources() {
    echo -e "${CYAN}[1단계] Terraform 코드에서 리소스 추출 중...${NC}"

    local cost_resource_types=(
        "aws_instance"
        "aws_nat_gateway"
        "aws_eip"
        "aws_vpc_endpoint"
        "aws_ec2_transit_gateway"
        "aws_ec2_transit_gateway_vpc_attachment"
        "aws_vpn_connection"
        "aws_vpn_gateway"
        "aws_customer_gateway"
        "aws_lambda_function"
        "aws_s3_bucket"
        "aws_opensearchserverless_collection"
        "aws_bedrockagent_knowledge_base"
        "aws_bedrockagent_data_source"
        "aws_api_gateway_rest_api"
        "aws_apigatewayv2_api"
        "aws_kms_key"
        "aws_cloudwatch_log_group"
        "aws_cloudtrail"
        "aws_secretsmanager_secret"
        "aws_dynamodb_table"
        "aws_route53_resolver_endpoint"
        "aws_route53_zone"
        "aws_cloudwatch_metric_alarm"
        "aws_sns_topic"
        "aws_sqs_queue"
        "aws_cloudwatch_event_bus"
        "aws_cloudwatch_event_rule"
    )

    echo "" > "$TF_RESOURCES_FILE"

    echo -e "\n${GREEN}  비용 발생 리소스 (Terraform 코드 기준):${NC}"
    echo ""

    for rtype in "${cost_resource_types[@]}"; do
        local matches
        matches=$(grep -rn "resource \"${rtype}\"" \
            environments/ modules/ \
            2>/dev/null || true)

        if [ -n "$matches" ]; then
            local count
            count=$(echo "$matches" | wc -l)
            echo -e "  ${GREEN}${rtype}${NC} (${count}개)"
            echo "$matches" | while read -r line; do
                local file
                file=$(echo "$line" | cut -d: -f1)
                local resource_name
                resource_name=$(echo "$line" | grep -oP '"[^"]+"\s+"([^"]+)"' | tail -1 | tr -d '"')
                echo "    - $resource_name ($file)"
                echo "${rtype}|${resource_name}|${file}" >> "$TF_RESOURCES_FILE"
            done
        fi
    done

    local total
    total=$(wc -l < "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    echo ""
    echo -e "  ${YELLOW}총 비용 발생 리소스: ${total}개${NC}"
}

# =============================================================================
# 2단계: 비용 영향도 분석
# =============================================================================
analyze_cost_impact() {
    echo ""
    echo -e "${CYAN}[2단계] 비용 영향도 분석...${NC}"
    echo ""

    echo -e "${GREEN}  === 높은 비용 (월 \$100+) ===${NC}"

    local oss_count
    oss_count=$(grep -c "aws_opensearchserverless_collection" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    if [ "$oss_count" -gt 0 ]; then
        echo -e "  ${RED}OpenSearch Serverless${NC}: ${oss_count}개 컬렉션"
        echo "    예상: 최소 4 OCU x \$0.24/hr x 730hr = ~\$700/월"
    fi

    local tgw_count
    tgw_count=$(grep -c "aws_ec2_transit_gateway\"" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    local tgw_attach_count
    tgw_attach_count=$(grep -c "aws_ec2_transit_gateway_vpc_attachment" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    if [ "$tgw_count" -gt 0 ]; then
        echo -e "  ${RED}Transit Gateway${NC}: ${tgw_count}개 TGW, ${tgw_attach_count}개 Attachment"
        echo "    예상: Attachment당 \$0.05/hr = ~\$36/월/attachment"
    fi

    local vpn_count
    vpn_count=$(grep -c "aws_vpn_connection" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    if [ "$vpn_count" -gt 0 ]; then
        echo -e "  ${RED}VPN Connection${NC}: ${vpn_count}개"
        echo "    예상: \$0.05/hr = ~\$36/월/connection"
    fi

    local nat_count
    nat_count=$(grep -c "aws_nat_gateway" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    if [ "$nat_count" -gt 0 ]; then
        echo -e "  ${RED}NAT Gateway${NC}: ${nat_count}개"
        echo "    예상: \$0.045/hr + \$0.045/GB = ~\$32/월 + 데이터"
    fi

    echo ""
    echo -e "${GREEN}  === 중간 비용 (월 \$10-100) ===${NC}"

    local vpce_count
    vpce_count=$(grep -c "aws_vpc_endpoint" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    if [ "$vpce_count" -gt 0 ]; then
        echo -e "  ${YELLOW}VPC Endpoints${NC}: ${vpce_count}개"
        echo "    예상: Interface 타입 \$0.01/hr = ~\$7.2/월/endpoint"
        echo "    총 예상: ~\$$(echo "$vpce_count * 7" | bc)/월"
    fi

    local r53_count
    r53_count=$(grep -c "aws_route53_resolver_endpoint" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    if [ "$r53_count" -gt 0 ]; then
        echo -e "  ${YELLOW}Route53 Resolver${NC}: ${r53_count}개 Endpoint"
        echo "    예상: ENI당 \$0.125/hr = ~\$90/월/endpoint (2 ENI)"
    fi

    local s3_count
    s3_count=$(grep -c "aws_s3_bucket\"" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    if [ "$s3_count" -gt 0 ]; then
        echo -e "  ${YELLOW}S3 Buckets${NC}: ${s3_count}개"
        echo "    비용: 저장량 + 요청 수 + 크로스리전 복제에 따라 변동"
    fi

    echo ""
    echo -e "${GREEN}  === 낮은 비용 (월 \$10 미만) ===${NC}"

    local kms_count
    kms_count=$(grep -c "aws_kms_key" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    [ "$kms_count" -gt 0 ] && echo -e "  KMS Keys: ${kms_count}개 (~\$${kms_count}/월)"

    local sm_count
    sm_count=$(grep -c "aws_secretsmanager_secret\"" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    [ "$sm_count" -gt 0 ] && echo -e "  Secrets Manager: ${sm_count}개 (~\$$(echo "scale=1; $sm_count * 0.4" | bc)/월)"

    local ddb_count
    ddb_count=$(grep -c "aws_dynamodb_table" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    [ "$ddb_count" -gt 0 ] && echo -e "  DynamoDB Tables: ${ddb_count}개 (PAY_PER_REQUEST)"

    local cw_count
    cw_count=$(grep -c "aws_cloudwatch_log_group" "$TF_RESOURCES_FILE" 2>/dev/null || echo "0")
    [ "$cw_count" -gt 0 ] && echo -e "  CloudWatch Log Groups: ${cw_count}개 (저장량 기반)"
}

# =============================================================================
# 3단계: 비용 최적화 권고사항
# =============================================================================
generate_recommendations() {
    echo ""
    echo -e "${CYAN}[3단계] 비용 최적화 권고사항${NC}"
    echo ""

    echo -e "${GREEN}  === 즉시 확인 필요 ===${NC}"
    echo "  1. 콘솔에서 수동 생성된 리소스 확인"
    echo "     -> bash scripts/audit-unmanaged-resources.sh"
    echo ""
    echo "  2. 미사용 VPC Endpoint 정리"
    echo "     -> Interface Endpoint는 사용하지 않아도 시간당 과금"
    echo ""
    echo "  3. CloudWatch Log Groups 보존 기간 설정"
    echo "     -> 무제한 보존 = 저장 비용 계속 증가"
    echo "     -> 30일 또는 90일 보존 정책 권장"
    echo ""

    echo -e "${GREEN}  === 중기 최적화 ===${NC}"
    echo "  4. OpenSearch Serverless OCU 모니터링"
    echo "     -> 최소 4 OCU 항상 실행 (가장 큰 고정 비용)"
    echo ""
    echo "  5. S3 Lifecycle Policy 적용"
    echo "     -> 오래된 문서를 Glacier로 이동"
    echo ""
    echo "  6. Transit Gateway Attachment 최적화"
    echo "     -> 사용하지 않는 VPC Attachment 제거"
    echo ""

    echo -e "${GREEN}  === AWS 비용 관리 도구 ===${NC}"
    echo "  7. Cost Explorer 서비스별 비용 추이 확인"
    echo "  8. Budgets 알림 설정 (cost-management 모듈 활용)"
    echo "  9. Cost Allocation Tags 활성화 (Project, Environment, Layer)"
}

# =============================================================================
# 보너스: AWS Cost Explorer 빠른 조회
# =============================================================================
quick_cost_check() {
    echo ""
    echo -e "${CYAN}[보너스] 최근 30일 서비스별 비용 조회...${NC}"
    echo ""

    local end_date
    end_date=$(date +%Y-%m-%d)
    local start_date
    start_date=$(date -d "30 days ago" +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d 2>/dev/null || echo "")

    if [ -z "$start_date" ]; then
        echo -e "  ${YELLOW}날짜 계산 실패 - 수동으로 확인하세요:${NC}"
        echo "  aws ce get-cost-and-usage \\"
        echo "    --time-period Start=2026-02-13,End=2026-03-13 \\"
        echo "    --granularity MONTHLY \\"
        echo "    --metrics BlendedCost \\"
        echo "    --group-by Type=DIMENSION,Key=SERVICE \\"
        echo "    --output table"
        return
    fi

    aws ce get-cost-and-usage \
        --time-period "Start=${start_date},End=${end_date}" \
        --granularity MONTHLY \
        --metrics "BlendedCost" \
        --group-by Type=DIMENSION,Key=SERVICE \
        --query 'ResultsByTime[*].Groups[?Metrics.BlendedCost.Amount!=`0`].[Keys[0],Metrics.BlendedCost.Amount]' \
        --output table 2>/dev/null || echo -e "  ${YELLOW}Cost Explorer 접근 불가 (ce:GetCostAndUsage 권한 필요)${NC}"
}

# =============================================================================
# 실행
# =============================================================================
{
    echo "# Terraform 코드 기반 비용 분석 보고서"
    echo "생성일: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    extract_tf_resources
    analyze_cost_impact
    generate_recommendations
    quick_cost_check

    echo ""
    echo "---"
    echo "## 실행 명령어 요약"
    echo ""
    echo "# 미관리 리소스 탐지"
    echo "bash scripts/audit-unmanaged-resources.sh"
    echo ""
    echo "# 최근 비용 조회 (날짜 조정 필요)"
    echo "aws ce get-cost-and-usage --time-period Start=2026-02-13,End=2026-03-13 --granularity MONTHLY --metrics BlendedCost --group-by Type=DIMENSION,Key=SERVICE --output table"
    echo ""
    echo "# 프로젝트 태그별 비용 조회"
    echo "aws ce get-cost-and-usage --time-period Start=2026-02-13,End=2026-03-13 --granularity MONTHLY --metrics BlendedCost --group-by Type=TAG,Key=Project --output table"
} 2>&1 | tee "$REPORT_FILE"

echo ""
echo -e "${GREEN}보고서 저장됨: ${REPORT_FILE}${NC}"
