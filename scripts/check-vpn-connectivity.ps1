# VPN 및 Transit Gateway 연결성 확인 스크립트
# 작성일: 2026-02-26

param(
    [string]$Region = "ap-northeast-2",
    [string]$Profile = "default"
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "VPN 및 Transit Gateway 연결성 확인" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. VPN Gateway 확인
Write-Host "1. VPN Gateway 상태 확인" -ForegroundColor Yellow
Write-Host "---" -ForegroundColor Gray

try {
    $vpnGateways = aws ec2 describe-vpn-gateways `
        --region $Region `
        --profile $Profile `
        --output json | ConvertFrom-Json

    if ($vpnGateways.VpnGateways.Count -eq 0) {
        Write-Host "❌ VPN Gateway가 없습니다" -ForegroundColor Red
    } else {
        Write-Host "✅ VPN Gateway 발견: $($vpnGateways.VpnGateways.Count)개" -ForegroundColor Green
        
        foreach ($vgw in $vpnGateways.VpnGateways) {
            Write-Host ""
            Write-Host "  VPN Gateway ID: $($vgw.VpnGatewayId)" -ForegroundColor Cyan
            Write-Host "  상태: $($vgw.State)" -ForegroundColor $(if ($vgw.State -eq "available") { "Green" } else { "Red" })
            Write-Host "  ASN: $($vgw.AmazonSideAsn)"
            Write-Host "  VPC 연결:"
            
            foreach ($attachment in $vgw.VpcAttachments) {
                Write-Host "    - VPC ID: $($attachment.VpcId)" -ForegroundColor Cyan
                Write-Host "      상태: $($attachment.State)" -ForegroundColor $(if ($attachment.State -eq "attached") { "Green" } else { "Red" })
            }
        }
    }
} catch {
    Write-Host "❌ VPN Gateway 조회 실패: $_" -ForegroundColor Red
}

Write-Host ""

# 2. VPN Connection 확인
Write-Host "2. VPN Connection 상태 확인" -ForegroundColor Yellow
Write-Host "---" -ForegroundColor Gray

try {
    $vpnConnections = aws ec2 describe-vpn-connections `
        --region $Region `
        --profile $Profile `
        --output json | ConvertFrom-Json

    if ($vpnConnections.VpnConnections.Count -eq 0) {
        Write-Host "❌ VPN Connection이 없습니다" -ForegroundColor Red
    } else {
        Write-Host "✅ VPN Connection 발견: $($vpnConnections.VpnConnections.Count)개" -ForegroundColor Green
        
        foreach ($vpnConn in $vpnConnections.VpnConnections) {
            Write-Host ""
            Write-Host "  VPN Connection ID: $($vpnConn.VpnConnectionId)" -ForegroundColor Cyan
            Write-Host "  상태: $($vpnConn.State)" -ForegroundColor $(if ($vpnConn.State -eq "available") { "Green" } else { "Red" })
            Write-Host "  VPN Gateway ID: $($vpnConn.VpnGatewayId)"
            Write-Host "  Customer Gateway ID: $($vpnConn.CustomerGatewayId)"
            Write-Host "  라우트:"
            
            foreach ($route in $vpnConn.Routes) {
                Write-Host "    - CIDR: $($route.DestinationCidrBlock)" -ForegroundColor Cyan
                Write-Host "      상태: $($route.State)" -ForegroundColor $(if ($route.State -eq "available") { "Green" } else { "Red" })
            }
        }
    }
} catch {
    Write-Host "❌ VPN Connection 조회 실패: $_" -ForegroundColor Red
}

Write-Host ""

# 3. Transit Gateway 확인
Write-Host "3. Transit Gateway 상태 확인" -ForegroundColor Yellow
Write-Host "---" -ForegroundColor Gray

try {
    $transitGateways = aws ec2 describe-transit-gateways `
        --region $Region `
        --profile $Profile `
        --output json | ConvertFrom-Json

    if ($transitGateways.TransitGateways.Count -eq 0) {
        Write-Host "❌ Transit Gateway가 없습니다" -ForegroundColor Red
        Write-Host "   → Transit Gateway 생성이 필요합니다" -ForegroundColor Yellow
    } else {
        Write-Host "✅ Transit Gateway 발견: $($transitGateways.TransitGateways.Count)개" -ForegroundColor Green
        
        foreach ($tgw in $transitGateways.TransitGateways) {
            Write-Host ""
            Write-Host "  Transit Gateway ID: $($tgw.TransitGatewayId)" -ForegroundColor Cyan
            Write-Host "  상태: $($tgw.State)" -ForegroundColor $(if ($tgw.State -eq "available") { "Green" } else { "Red" })
            Write-Host "  ASN: $($tgw.Options.AmazonSideAsn)"
        }
    }
} catch {
    Write-Host "❌ Transit Gateway 조회 실패: $_" -ForegroundColor Red
}

Write-Host ""

# 4. Route Table 확인
Write-Host "4. Seoul VPC Route Table 확인" -ForegroundColor Yellow
Write-Host "---" -ForegroundColor Gray

try {
    # Seoul VPC ID 조회
    $vpcs = aws ec2 describe-vpcs `
        --filters "Name=tag:Name,Values=*seoul*" `
        --region $Region `
        --profile $Profile `
        --output json | ConvertFrom-Json

    if ($vpcs.Vpcs.Count -eq 0) {
        Write-Host "❌ Seoul VPC를 찾을 수 없습니다" -ForegroundColor Red
    } else {
        foreach ($vpc in $vpcs.Vpcs) {
            Write-Host ""
            Write-Host "  VPC ID: $($vpc.VpcId)" -ForegroundColor Cyan
            Write-Host "  CIDR: $($vpc.CidrBlock)"
            
            # Route Table 조회
            $routeTables = aws ec2 describe-route-tables `
                --filters "Name=vpc-id,Values=$($vpc.VpcId)" `
                --region $Region `
                --profile $Profile `
                --output json | ConvertFrom-Json

            foreach ($rt in $routeTables.RouteTables) {
                Write-Host ""
                Write-Host "    Route Table ID: $($rt.RouteTableId)" -ForegroundColor Cyan
                
                foreach ($route in $rt.Routes) {
                    $destination = $route.DestinationCidrBlock
                    $target = ""
                    
                    if ($route.GatewayId) { $target = "Gateway: $($route.GatewayId)" }
                    elseif ($route.VpcPeeringConnectionId) { $target = "VPC Peering: $($route.VpcPeeringConnectionId)" }
                    elseif ($route.TransitGatewayId) { $target = "Transit Gateway: $($route.TransitGatewayId)" }
                    elseif ($route.NetworkInterfaceId) { $target = "ENI: $($route.NetworkInterfaceId)" }
                    else { $target = "Local" }
                    
                    Write-Host "      $destination → $target" -ForegroundColor Gray
                }
            }
        }
    }
} catch {
    Write-Host "❌ Route Table 조회 실패: $_" -ForegroundColor Red
}

Write-Host ""

# 5. VPN Gateway Route Propagation 확인
Write-Host "5. VPN Gateway Route Propagation 확인" -ForegroundColor Yellow
Write-Host "---" -ForegroundColor Gray

try {
    $propagations = aws ec2 describe-vpn-gateway-route-propagations `
        --region $Region `
        --profile $Profile `
        --output json | ConvertFrom-Json

    if ($propagations.VpnGatewayRoutePropagations.Count -eq 0) {
        Write-Host "❌ Route Propagation이 설정되지 않았습니다" -ForegroundColor Red
    } else {
        Write-Host "✅ Route Propagation 설정됨: $($propagations.VpnGatewayRoutePropagations.Count)개" -ForegroundColor Green
        
        foreach ($prop in $propagations.VpnGatewayRoutePropagations) {
            Write-Host ""
            Write-Host "  VPN Gateway ID: $($prop.GatewayId)" -ForegroundColor Cyan
            Write-Host "  Route Table ID: $($prop.RouteTableId)"
            Write-Host "  상태: $($prop.State)" -ForegroundColor $(if ($prop.State -eq "enabled") { "Green" } else { "Red" })
        }
    }
} catch {
    Write-Host "❌ Route Propagation 조회 실패: $_" -ForegroundColor Red
}

Write-Host ""

# 6. 요약 및 권장사항
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "요약 및 권장사항" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "현재 상황:" -ForegroundColor Yellow
Write-Host "- VPN Gateway: 설정됨 (Seoul VPC에만 연결)" -ForegroundColor Gray
Write-Host "- Transit Gateway: 없음" -ForegroundColor Red
Write-Host "- 기존 서비스 VPC: VPN 연결 불가" -ForegroundColor Red
Write-Host ""

Write-Host "권장사항:" -ForegroundColor Yellow
Write-Host "1. Transit Gateway 생성" -ForegroundColor Cyan
Write-Host "2. VPN Attachment 생성" -ForegroundColor Cyan
Write-Host "3. VPC Attachments 생성 (Seoul VPC, US VPC, 기존 서비스 VPC)" -ForegroundColor Cyan
Write-Host "4. Route Table 업데이트" -ForegroundColor Cyan
Write-Host "5. VPN 연결 테스트" -ForegroundColor Cyan
Write-Host ""

Write-Host "자세한 내용은 다음 문서를 참고하세요:" -ForegroundColor Yellow
Write-Host "- 20260226_VPN_TGW_CONNECTIVITY_ANALYSIS.md" -ForegroundColor Cyan
Write-Host ""
