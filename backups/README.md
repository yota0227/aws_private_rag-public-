# Terraform State Backups

이 디렉토리는 BOS-AI VPC 통합 마이그레이션 프로젝트의 Terraform state 파일 백업을 저장합니다.

## 백업 구조

각 백업 디렉토리는 다음과 같은 구조를 가집니다:

```
backups/
├── latest -> 20260220_010646  (최신 백업으로의 심볼릭 링크)
├── 20260220_010646/           (타임스탬프 형식: YYYYMMDD_HHMMSS)
│   ├── s3-state-files/        (S3에서 다운로드한 state 파일)
│   │   ├── app-layer/
│   │   │   └── bedrock-rag/
│   │   │       └── terraform.tfstate
│   │   ├── network-layer/
│   │   │   └── terraform.tfstate
│   │   └── full-backup/       (전체 S3 버킷 동기화)
│   ├── local-configs/         (로컬 Terraform 설정 파일)
│   │   ├── environments/
│   │   └── modules/
│   └── metadata/              (백업 메타데이터)
│       ├── backup-info.txt    (백업 정보)
│       └── dynamodb-locks.json (DynamoDB 락 테이블 상태)
```

## 백업 생성

새로운 백업을 생성하려면:

```bash
./scripts/backup-terraform-state.sh
```

이 스크립트는 다음을 백업합니다:
1. S3 버킷의 모든 Terraform state 파일
2. 로컬 Terraform 설정 파일 (environments/, modules/)
3. DynamoDB 락 테이블 상태
4. 백업 메타데이터 (날짜, AWS 계정, Git 정보 등)

## 백업 복원

### 1. S3 State 파일 복원

전체 S3 버킷을 복원:

```bash
BACKUP_DIR="backups/latest"  # 또는 특정 백업 디렉토리
aws s3 sync ${BACKUP_DIR}/s3-state-files/full-backup/ s3://bos-ai-terraform-state/ --region ap-northeast-2
```

특정 state 파일만 복원:

```bash
BACKUP_DIR="backups/latest"
aws s3 cp ${BACKUP_DIR}/s3-state-files/network-layer/terraform.tfstate \
  s3://bos-ai-terraform-state/network-layer/terraform.tfstate \
  --region ap-northeast-2
```

### 2. 로컬 설정 파일 복원

```bash
BACKUP_DIR="backups/latest"
cp -r ${BACKUP_DIR}/local-configs/environments/* environments/
cp -r ${BACKUP_DIR}/local-configs/modules/* modules/
```

### 3. 복원 후 검증

```bash
# Terraform 초기화
cd environments/network-layer
terraform init

# State 확인
terraform state list

# Plan 실행 (변경사항이 없어야 함)
terraform plan
```

## 백업 보관 정책

- **즉시 백업**: 각 마이그레이션 Phase 시작 전
- **보관 기간**: 
  - 최근 7일: 모든 백업 보관
  - 7-30일: 주간 백업만 보관
  - 30일 이상: 월간 백업만 보관
- **중요 백업**: Phase 1 시작 전 백업은 영구 보관

## 롤백 시나리오

### 시나리오 1: Phase 2 (네이밍 변경) 롤백

태그만 변경되었으므로 간단한 롤백:

```bash
cd environments/network-layer
terraform apply -var-file=backups/latest/local-configs/environments/network-layer/terraform.tfvars
```

### 시나리오 2: Phase 3-7 (신규 리소스 배포) 롤백

신규 리소스 삭제:

```bash
# 신규 리소스 제거
terraform destroy -target=module.opensearch_serverless
terraform destroy -target=module.lambda_functions
terraform destroy -target=module.bedrock_kb

# State 복원 (필요시)
aws s3 sync backups/latest/s3-state-files/full-backup/ s3://bos-ai-terraform-state/ --region ap-northeast-2
```

### 시나리오 3: 전체 롤백

완전한 롤백이 필요한 경우:

```bash
# 1. S3 state 복원
aws s3 sync backups/latest/s3-state-files/full-backup/ s3://bos-ai-terraform-state/ --region ap-northeast-2

# 2. 로컬 설정 복원
cp -r backups/latest/local-configs/* .

# 3. Terraform 재초기화
cd environments/network-layer
terraform init -reconfigure

# 4. 현재 상태 확인
terraform plan

# 5. 필요시 apply
terraform apply
```

## 백업 검증

백업이 올바르게 생성되었는지 확인:

```bash
# 백업 메타데이터 확인
cat backups/latest/metadata/backup-info.txt

# State 파일 존재 확인
ls -lh backups/latest/s3-state-files/network-layer/terraform.tfstate
ls -lh backups/latest/s3-state-files/app-layer/bedrock-rag/terraform.tfstate

# State 파일 유효성 확인 (JSON 형식)
jq . backups/latest/s3-state-files/network-layer/terraform.tfstate > /dev/null && echo "Valid JSON"
```

## 주의사항

1. **민감 정보**: State 파일에는 민감한 정보가 포함될 수 있으므로 백업 디렉토리 접근 권한을 제한하세요.
2. **버전 관리**: 백업 디렉토리는 `.gitignore`에 추가되어 Git에 커밋되지 않습니다.
3. **S3 버전 관리**: S3 버킷에는 버전 관리가 활성화되어 있어 추가 복원 옵션을 제공합니다.
4. **DynamoDB 락**: 복원 중에는 다른 사용자가 Terraform을 실행하지 않도록 주의하세요.

## 긴급 연락처

백업/복원 중 문제 발생 시:
- 인프라 팀: [연락처 추가 필요]
- AWS Support: [케이스 생성]

## 참고 문서

- [Terraform State 관리 가이드](../docs/OPERATIONAL_RUNBOOK.md)
- [마이그레이션 설계 문서](../.kiro/specs/bos-ai-vpc-consolidation/design.md)
- [롤백 계획](../.kiro/specs/bos-ai-vpc-consolidation/requirements.md#3-롤백-계획-수립)
