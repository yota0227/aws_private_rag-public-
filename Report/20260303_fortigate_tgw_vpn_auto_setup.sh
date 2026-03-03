#!/bin/bash

# ============================================
# Fortigate 60F v7.4.11 - AWS TGW VPN 자동 설정
# 사용법: ./fortigate_tgw_vpn_auto_setup.sh <fortigate_ip> <admin_user> <admin_password>
# 예: ./fortigate_tgw_vpn_auto_setup.sh 192.168.1.1 admin password123
# ============================================

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 함수: 에러 처리
error_exit() {
    echo -e "${RED}[ERROR] $1${NC}"
    exit 1
}

# 함수: 성공 메시지
success_msg() {
    echo -e "${GREEN}[SUCCESS] $1${NC}"
}

# 함수: 정보 메시지
info_msg() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# 함수: 경고 메시지
warn_msg() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

# 파라미터 검증
if [ $# -lt 3 ]; then
    echo -e "${YELLOW}사용법:${NC}"
    echo "  $0 <fortigate_ip> <admin_user> <admin_password>"
    echo ""
    echo -e "${YELLOW}예:${NC}"
    echo "  $0 192.168.1.1 admin password123"
    echo ""
    echo -e "${YELLOW}또는 대화형 모드:${NC}"
    echo "  $0"
    exit 1
fi

FORTIGATE_IP=$1
ADMIN_USER=$2
ADMIN_PASSWORD=$3

# 대화형 모드
if [ $# -eq 0 ]; then
    read -p "Fortigate IP 주소: " FORTIGATE_IP
    read -p "Admin 사용자명: " ADMIN_USER
    read -sp "Admin 비밀번호: " ADMIN_PASSWORD
    echo ""
fi

info_msg "Fortigate 60F v7.4.11 - AWS TGW VPN 설정 시작"
info_msg "Target: $FORTIGATE_IP"
info_msg "User: $ADMIN_USER"
echo ""

# SSH 연결 테스트
info_msg "Fortigate 연결 테스트..."
if ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    $ADMIN_USER@$FORTIGATE_IP "get system status" > /dev/null 2>&1; then
    error_exit "Fortigate에 연결할 수 없습니다. IP, 사용자명, 비밀번호를 확인하세요."
fi
success_msg "Fortigate 연결 성공"
echo ""

# 설정 적용 함수
apply_config() {
    local config_name=$1
    local config_content=$2
    
    info_msg "적용 중: $config_name"
    
    # 임시 파일 생성
    local temp_file=$(mktemp)
    echo "$config_content" > "$temp_file"
    
    # SCP로 파일 전송
    scp -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "$temp_file" $ADMIN_USER@$FORTIGATE_IP:/tmp/config_temp.txt > /dev/null 2>&1
    
    # SSH로 설정 적용
    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        $ADMIN_USER@$FORTIGATE_IP << EOSSH
$config_content
EOSSH
    
    rm -f "$temp_file"
    success_msg "$config_name 적용 완료"
}

# ============================================
# 1. Tunnel 1 - Phase 1
# ============================================
info_msg "Step 1/8: Tunnel 1 - Phase 1 Interface 설정"
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    $ADMIN_USER@$FORTIGATE_IP << 'EOF'
config vpn ipsec phase1-interface
    edit "AWS-TGW-T1"
        set interface "wan1"
        set peertype any
        set peer 3.38.69.188
        set net-device enable
        set proposal aes128-sha1
        set comments "AWS TGW Tunnel 1"
        set dhgrp 2
        set lifetime 28800
        set authentication-method pre-shared-key
        set pre-shared-key "5RXxu5CEtzBY7bXGCP5YCN9smfYM00OP"
        set dpd on-idle
        set dpd-retrycount 3
        set dpd-retryinterval 10
    next
end
EOF
success_msg "Step 1/8 완료"
echo ""

# ============================================
# 2. Tunnel 1 - Phase 2
# ============================================
info_msg "Step 2/8: Tunnel 1 - Phase 2 Interface 설정"
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    $ADMIN_USER@$FORTIGATE_IP << 'EOF'
config vpn ipsec phase2-interface
    edit "AWS-TGW-T1-P2"
        set phase1name "AWS-TGW-T1"
        set proposal aes128-sha1
        set pfs group2
        set replay disable
        set keylifeseconds 3600
        set comments "AWS TGW Tunnel 1 Phase 2"
    next
end
EOF
success_msg "Step 2/8 완료"
echo ""

# ============================================
# 3. Tunnel 1 - VPN Interface
# ============================================
info_msg "Step 3/8: Tunnel 1 - VPN Interface 설정"
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    $ADMIN_USER@$FORTIGATE_IP << 'EOF'
config system interface
    edit "AWS-TGW-T1"
        set vdom "root"
        set ip 169.254.224.54 255.255.255.252
        set type tunnel
        set tunnel-type ipsec
        set remote-ip 169.254.224.53
        set interface "AWS-TGW-T1"
        set mtu-override enable
        set mtu 1436
    next
end
EOF
success_msg "Step 3/8 완료"
echo ""

# ============================================
# 4. Tunnel 2 - Phase 1
# ============================================
info_msg "Step 4/8: Tunnel 2 - Phase 1 Interface 설정"
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    $ADMIN_USER@$FORTIGATE_IP << 'EOF'
config vpn ipsec phase1-interface
    edit "AWS-TGW-T2"
        set interface "wan1"
        set peertype any
        set peer 43.200.222.199
        set net-device enable
        set proposal aes128-sha1
        set comments "AWS TGW Tunnel 2"
        set dhgrp 2
        set lifetime 28800
        set authentication-method pre-shared-key
        set pre-shared-key "pCgEtv28JG7mUDagkyRgqyclLSf7pyyf"
        set dpd on-idle
        set dpd-retrycount 3
        set dpd-retryinterval 10
    next
end
EOF
success_msg "Step 4/8 완료"
echo ""

# ============================================
# 5. Tunnel 2 - Phase 2
# ============================================
info_msg "Step 5/8: Tunnel 2 - Phase 2 Interface 설정"
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    $ADMIN_USER@$FORTIGATE_IP << 'EOF'
config vpn ipsec phase2-interface
    edit "AWS-TGW-T2-P2"
        set phase1name "AWS-TGW-T2"
        set proposal aes128-sha1
        set pfs group2
        set replay disable
        set keylifeseconds 3600
        set comments "AWS TGW Tunnel 2 Phase 2"
    next
end
EOF
success_msg "Step 5/8 완료"
echo ""

# ============================================
# 6. Tunnel 2 - VPN Interface
# ============================================
info_msg "Step 6/8: Tunnel 2 - VPN Interface 설정"
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    $ADMIN_USER@$FORTIGATE_IP << 'EOF'
config system interface
    edit "AWS-TGW-T2"
        set vdom "root"
        set ip 169.254.96.198 255.255.255.252
        set type tunnel
        set tunnel-type ipsec
        set remote-ip 169.254.96.197
        set interface "AWS-TGW-T2"
        set mtu-override enable
        set mtu 1436
    next
end
EOF
success_msg "Step 6/8 완료"
echo ""

# ============================================
# 7. BGP 설정
# ============================================
info_msg "Step 7/8: BGP 설정"
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    $ADMIN_USER@$FORTIGATE_IP << 'EOF'
config router bgp
    set as 65000
    set router-id 211.170.236.130
    set ebgp-multipath enable
    set graceful-restart enable
    set graceful-restart-time 120
    
    config neighbor
        edit "169.254.224.53"
            set remote-as 64512
            set holdtime-timer 30
            set keepalive-timer 10
            set connect-timer 10
            set description "AWS TGW Tunnel 1"
        next
    end
    
    config neighbor
        edit "169.254.96.197"
            set remote-as 64512
            set holdtime-timer 30
            set keepalive-timer 10
            set connect-timer 10
            set description "AWS TGW Tunnel 2"
        next
    end
    
    config redistribute "connected"
        set status enable
    end
end
EOF
success_msg "Step 7/8 완료"
echo ""

# ============================================
# 8. 방화벽 정책 설정
# ============================================
info_msg "Step 8/8: 방화벽 정책 설정"
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    $ADMIN_USER@$FORTIGATE_IP << 'EOF'
config firewall policy
    edit 100
        set name "Allow-to-AWS-TGW"
        set srcintf "port1" "port2" "port3" "port4" "port5"
        set dstintf "AWS-TGW-T1" "AWS-TGW-T2"
        set srcaddr "all"
        set dstaddr "all"
        set action accept
        set schedule "always"
        set service "ALL"
        set logtraffic all
        set comments "Allow traffic to AWS TGW"
    next
end

config firewall policy
    edit 101
        set name "Allow-from-AWS-TGW"
        set srcintf "AWS-TGW-T1" "AWS-TGW-T2"
        set dstintf "port1" "port2" "port3" "port4" "port5"
        set srcaddr "all"
        set dstaddr "all"
        set action accept
        set schedule "always"
        set service "ALL"
        set logtraffic all
        set comments "Allow traffic from AWS TGW"
    next
end
EOF
success_msg "Step 8/8 완료"
echo ""

# ============================================
# 설정 저장
# ============================================
info_msg "설정 저장 중..."
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    $ADMIN_USER@$FORTIGATE_IP "execute backup config"
success_msg "설정 저장 완료"
echo ""

# ============================================
# 검증
# ============================================
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}설정 완료${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""
echo -e "${BLUE}다음 단계:${NC}"
echo "1. Fortigate 콘솔에서 다음 명령어로 상태 확인:"
echo "   - diagnose vpn ipsec status"
echo "   - get router info bgp summary"
echo "   - get router info bgp neighbors"
echo ""
echo "2. AWS 콘솔에서 VPN 상태 확인:"
echo "   - VPN Connection: vpn-0b2b65e9414092369"
echo "   - 상태가 UP으로 변경되어야 함"
echo ""
echo "3. 라우팅 테이블 확인:"
echo "   - get router info routing-table all"
echo ""
