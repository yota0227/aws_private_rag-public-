# Transit Gateway 마이그레이션 가이드

## 개요

현재 VPN Gateway 기반 아키텍처를 Transit Gateway 기반으로 마이그레이션합니다.

### 현재 상태
- 로깅 파이프라인 VPC (10.200.0.0/16): VGW (`vgw-0d54d0b0af6515dec`)로 VPN 연결됨
- BOS-AI 프론트엔드 VPC (10.10.0.0/16): VGW (`vgw-0461cd4d6a4463f67`) 있지만 VPN 연결 없음
- 각 VPC가 독립적으로 VGW 사용

### 목표 상태
- Transit Gateway 생성
- 2개 VPC를 TGW에 연결
- VPN 연결을 TGW로 마이그레이션
- 온프렘에서 2개 VPC 모두 접근 가능

## 마이그레이션 단계

### Phase 1: 준비 및 백업

1. **현재 상태 백업**
```bash
# VPC 정보 백업
aws ec2 describe-vpcs --region ap-northeast-2 > backup/vpcs-$(date +%Y%m%d).json

# VPN Gateway 정보 백업
aws ec2 describe-vpn-gateways --region ap-northeast-2 > backup/vgws-$(date +%Y%m%d).json

# VPN 연결 정보 백업
aws ec2 describe-vpn-connections --region ap-northeast-2 > backup/vpn-connections-$(date +%Y%m%d).json

# Route Table 정보 백업
aws ec2 describe-route-tables --region ap-northeast-2 > backup/route-tables-$(date +%Y%m%d).json
```

2. **Terraform State 백업**
```bash
cd environments/network-layer
terraform state pull > backup/terraform-state-$(date +%Y%m%d).json
```

### Phase 2: Transit Gateway 생성

1. **기존 main.tf 백업**
```bash
cd environments/network-layer
cp main.tf main.tf.backup
cp outputs.tf outputs.tf.backup
```

2. **새로운 TGW 설정 적용**
```bash
# main-tgw.tf를 main.tf로 교체
mv main.tf main-vgw.tf
mv main-tgw.tf main.tf

# outputs-tgw.tf를 outputs.tf로 교체
mv outputs.tf outputs-vgw.tf
mv outputs-tgw.tf outputs.tf
```

3. **Terraform 초기화 및 계획**
```bash
terraform init -upgrade
terraform plan -out=tgw-migration.tfplan
```

4. **변경사항 검토**
- TGW 생성 확인
- VPC 어태치먼트 확인
- 라우팅 테이블 변경 확인

### Phase 3: 기존 리소스 Import

1. **로깅 파이프라인 VPC Import**
```bash
# VPC Import
terraform import 'module.vpc_logging.aws_vpc.main' vpc-066c464f9c750ee9e

# Subnet Import
terraform import 'module.vpc_logging.aws_subnet.private[0]' subnet-0f027e9de8e26c18f
terraform import 'module.vpc_logging.aws_subnet.private[1]' subnet-0625d992edf151017
terraform import 'module.vpc_logging.aws_subnet.public[0]' subnet-06d3c439cedf14742
terraform import 'module.vpc_logging.aws_subnet.public[1]' subnet-0a9ba13fade9c4c66
```

2. **BOS-AI 프론트엔드 VPC Import**
```bash
# VPC Import
terraform import 'module.vpc_frontend.aws_vpc.main' vpc-0f759f00e5df658d1

# Subnet Import
terraform import 'module.vpc_frontend.aws_subnet.private[0]' subnet-01295edee81960d96
terraform import 'module.vpc_frontend.aws_subnet.private[1]' subnet-082252d39635f17ee
```

### Phase 4: TGW 배포

1. **TGW 및 VPC 어태치먼트 생성**
```bash
terraform apply tgw-migration.tfplan
```

2. **TGW 상태 확인**
```bash
# TGW 확인
aws ec2 describe-transit-gateways --region ap-northeast-2

# VPC 어태치먼트 확인
aws ec2 describe-transit-gateway-vpc-attachments --region ap-northeast-2
```

### Phase 5: VPN 마이그레이션

1. **Customer Gateway 정보 확인**
```bash
aws ec2 describe-customer-gateways --region ap-northeast-2
```

2. **TGW VPN 어태치먼트 생성**
```bash
# Customer Gateway ID 확인 (cgw-00d18a496243b5184)
CGW_ID="cgw-00d18a496243b5184"
TGW_ID=$(terraform output -raw transit_gateway_id)

# VPN 연결 생성
aws ec2 create-vpn-connection \
  --type ipsec.1 \
  --customer-gateway-id $CGW_ID \
  --transit-gateway-id $TGW_ID \
  --options TunnelInsideIpVersion=ipv4,StaticRoutesOnly=false \
  --tag-specifications "ResourceType=vpn-connection,Tags=[{Key=Name,Value=tgw-vpn-bos-ai-prod}]" \
  --region ap-northeast-2
```

3. **VPN 연결 상태 확인**
```bash
aws ec2 describe-vpn-connections --region ap-northeast-2 \
  --filters "Name=transit-gateway-id,Values=$TGW_ID"
```

4. **온프렘 방화벽 설정 업데이트**
- 새로운 VPN 터널 정보를 온프렘 방화벽에 설정
- BGP 설정 확인 (ASN: 64512)

### Phase 6: 라우팅 검증

1. **TGW 라우팅 테이블 확인**
```bash
# TGW 라우팅 테이블 확인
TGW_RT_ID=$(aws ec2 describe-transit-gateways --region ap-northeast-2 \
  --transit-gateway-ids $TGW_ID \
  --query 'TransitGateways[0].Options.AssociationDefaultRouteTableId' \
  --output text)

aws ec2 describe-transit-gateway-route-tables \
  --transit-gateway-route-table-ids $TGW_RT_ID \
  --region ap-northeast-2
```

2. **VPC 라우팅 테이블 확인**
```bash
# 로깅 VPC 라우팅 확인
aws ec2 describe-route-tables --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-066c464f9c750ee9e"

# 프론트엔드 VPC 라우팅 확인
aws ec2 describe-route-tables --region ap-northeast-2 \
  --filters "Name=vpc-id,Values=vpc-0f759f00e5df658d1"
```

3. **연결 테스트**
```bash
# 온프렘에서 로깅 VPC로 ping
ping 10.200.1.10

# 온프렘에서 프론트엔드 VPC로 ping
ping 10.10.1.10

# 로깅 VPC에서 프론트엔드 VPC로 ping
ping 10.10.1.10
```

### Phase 7: 기존 VGW 정리

**주의: VPN 연결이 안정적으로 작동하는 것을 확인한 후에만 진행**

1. **기존 VPN 연결 삭제**
```bash
# 기존 VPN 연결 ID 확인
OLD_VPN_ID="vpn-0acd5eff60174538a"

# VPN 연결 삭제
aws ec2 delete-vpn-connection \
  --vpn-connection-id $OLD_VPN_ID \
  --region ap-northeast-2
```

2. **VGW 분리 및 삭제**
```bash
# 로깅 VPC의 VGW 분리
aws ec2 detach-vpn-gateway \
  --vpn-gateway-id vgw-0d54d0b0af6515dec \
  --vpc-id vpc-066c464f9c750ee9e \
  --region ap-northeast-2

# 프론트엔드 VPC의 VGW 분리
aws ec2 detach-vpn-gateway \
  --vpn-gateway-id vgw-0461cd4d6a4463f67 \
  --vpc-id vpc-0f759f00e5df658d1 \
  --region ap-northeast-2

# VGW 삭제 (분리 후 5분 대기)
sleep 300
aws ec2 delete-vpn-gateway \
  --vpn-gateway-id vgw-0d54d0b0af6515dec \
  --region ap-northeast-2

aws ec2 delete-vpn-gateway \
  --vpn-gateway-id vgw-0461cd4d6a4463f67 \
  --region ap-northeast-2
```

## 롤백 절차

마이그레이션 중 문제 발생 시:

1. **TGW VPN 연결 문제 시**
```bash
# 기존 VPN 연결이 아직 살아있다면 그대로 사용
# TGW VPN 연결만 삭제
aws ec2 delete-vpn-connection --vpn-connection-id <NEW_VPN_ID> --region ap-northeast-2
```

2. **TGW 완전 롤백**
```bash
# TGW 어태치먼트 삭제
aws ec2 delete-transit-gateway-vpc-attachment \
  --transit-gateway-attachment-id <ATTACHMENT_ID> \
  --region ap-northeast-2

# TGW 삭제
aws ec2 delete-transit-gateway \
  --transit-gateway-id <TGW_ID> \
  --region ap-northeast-2

# Terraform 설정 복원
cd environments/network-layer
mv main-vgw.tf main.tf
mv outputs-vgw.tf outputs.tf
terraform apply
```

## 검증 체크리스트

- [ ] TGW 생성 완료
- [ ] 로깅 VPC TGW 어태치먼트 생성
- [ ] 프론트엔드 VPC TGW 어태치먼트 생성
- [ ] TGW VPN 연결 생성
- [ ] VPN 터널 상태 UP
- [ ] BGP 세션 Established
- [ ] 온프렘 → 로깅 VPC 연결 확인
- [ ] 온프렘 → 프론트엔드 VPC 연결 확인
- [ ] 로깅 VPC ↔ 프론트엔드 VPC 연결 확인
- [ ] 기존 VGW 정리 완료

## 예상 다운타임

- TGW 생성: 다운타임 없음
- VPN 마이그레이션: 약 5-10분 (새 VPN 터널 설정 시간)
- 기존 VGW 정리: 다운타임 없음 (TGW VPN이 이미 작동 중)

## 비용 영향

- TGW 시간당 비용: $0.05/hour
- TGW 데이터 처리 비용: $0.02/GB
- VGW 제거로 인한 비용 절감: 미미함 (VGW는 무료)
- 순 증가 비용: 월 약 $36 + 데이터 전송 비용

## 문의사항

문제 발생 시 연락처:
- 담당자: [이름]
- 이메일: [이메일]
- 긴급 연락처: [전화번호]
