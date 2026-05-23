#!/bin/bash
# Fortigate 60F v7.4.11 - AWS TGW VPN 설정 스크립트
# 작성일: 2026-03-03
# VPN Connection ID: vpn-0b2b65e9414092369

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Fortigate 60F - AWS TGW VPN 설정${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""

# ============================================
# 1. Phase 1 Interface 설정 - Tunnel 1
# ============================================
echo -e "${GREEN}[1/8] Tunnel 1 - Phase 1 Interface 설정${NC}"
cat << 'EOF'
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
echo ""

# ============================================
# 2. Phase 2 Interface 설정 - Tunnel 1
# ============================================
echo -e "${GREEN}[2/8] Tunnel 1 - Phase 2 Interface 설정${NC}"
cat << 'EOF'
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
echo ""

# ============================================
# 3. VPN Interface 설정 - Tunnel 1
# ============================================
echo -e "${GREEN}[3/8] Tunnel 1 - VPN Interface 설정${NC}"
cat << 'EOF'
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
echo ""

# ============================================
# 4. Phase 1 Interface 설정 - Tunnel 2
# ============================================
echo -e "${GREEN}[4/8] Tunnel 2 - Phase 1 Interface 설정${NC}"
cat << 'EOF'
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
echo ""

# ============================================
# 5. Phase 2 Interface 설정 - Tunnel 2
# ============================================
echo -e "${GREEN}[5/8] Tunnel 2 - Phase 2 Interface 설정${NC}"
cat << 'EOF'
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
echo ""

# ============================================
# 6. VPN Interface 설정 - Tunnel 2
# ============================================
echo -e "${GREEN}[6/8] Tunnel 2 - VPN Interface 설정${NC}"
cat << 'EOF'
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
echo ""

# ============================================
# 7. BGP 설정
# ============================================
echo -e "${GREEN}[7/8] BGP 설정${NC}"
cat << 'EOF'
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
echo ""

# ============================================
# 8. 방화벽 정책 설정
# ============================================
echo -e "${GREEN}[8/8] 방화벽 정책 설정${NC}"
cat << 'EOF'
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
echo ""

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}설정 완료${NC}"
echo -e "${YELLOW}========================================${NC}"
echo ""
echo -e "${YELLOW}다음 단계:${NC}"
echo "1. 위의 모든 명령어를 Fortigate CLI에 복사하여 붙여넣기"
echo "2. 설정 저장: execute backup config"
echo "3. 터널 상태 확인: diagnose vpn ipsec status"
echo "4. BGP 상태 확인: get router info bgp summary"
echo "5. AWS 콘솔에서 VPN 상태 확인"
echo ""
