#!/bin/bash
# Terraform State Backup Script
# Task: 1.1 Terraform state 파일 백업
# Purpose: 현재 Terraform state 파일을 백업하여 롤백 시 복원할 수 있도록 준비
#
# This script backs up:
# 1. Remote Terraform state files from S3
# 2. Local Terraform configuration files
# 3. DynamoDB lock table state (for reference)

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
BACKUP_ROOT="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
STATE_BUCKET="bos-ai-terraform-state"
DYNAMODB_TABLE="terraform-state-lock"
REGION="ap-northeast-2"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials are not configured. Please configure AWS CLI."
        exit 1
    fi
    
    log_info "Prerequisites check passed."
}

# Create backup directory structure
create_backup_structure() {
    log_info "Creating backup directory structure..."
    
    mkdir -p "${BACKUP_DIR}/s3-state-files"
    mkdir -p "${BACKUP_DIR}/local-configs"
    mkdir -p "${BACKUP_DIR}/metadata"
    
    log_info "Backup directory created: ${BACKUP_DIR}"
}

# Backup S3 state files
backup_s3_state_files() {
    log_info "Backing up Terraform state files from S3..."
    
    # List all state files in the bucket
    STATE_FILES=$(aws s3 ls "s3://${STATE_BUCKET}/" --recursive --region "${REGION}" | grep ".tfstate" | awk '{print $4}')
    
    if [ -z "$STATE_FILES" ]; then
        log_warn "No state files found in S3 bucket: ${STATE_BUCKET}"
        return
    fi
    
    # Download each state file
    echo "$STATE_FILES" | while read -r state_file; do
        log_info "Downloading: ${state_file}"
        aws s3 cp "s3://${STATE_BUCKET}/${state_file}" "${BACKUP_DIR}/s3-state-files/${state_file}" --region "${REGION}"
    done
    
    # Also backup the entire bucket structure for safety
    log_info "Creating full S3 bucket sync..."
    aws s3 sync "s3://${STATE_BUCKET}/" "${BACKUP_DIR}/s3-state-files/full-backup/" --region "${REGION}"
    
    log_info "S3 state files backed up successfully."
}

# Backup local Terraform configurations
backup_local_configs() {
    log_info "Backing up local Terraform configuration files..."
    
    # Backup environments directory
    if [ -d "environments" ]; then
        cp -r environments "${BACKUP_DIR}/local-configs/"
        log_info "Environments directory backed up."
    else
        log_warn "Environments directory not found."
    fi
    
    # Backup modules directory
    if [ -d "modules" ]; then
        cp -r modules "${BACKUP_DIR}/local-configs/"
        log_info "Modules directory backed up."
    else
        log_warn "Modules directory not found."
    fi
    
    # Backup any .tfvars files in root
    if ls *.tfvars 2>/dev/null; then
        cp *.tfvars "${BACKUP_DIR}/local-configs/" 2>/dev/null || true
        log_info "Root tfvars files backed up."
    fi
    
    log_info "Local configuration files backed up successfully."
}

# Backup DynamoDB lock table state
backup_dynamodb_state() {
    log_info "Backing up DynamoDB lock table state..."
    
    # Export current lock table items (if any)
    aws dynamodb scan \
        --table-name "${DYNAMODB_TABLE}" \
        --region "${REGION}" \
        --output json > "${BACKUP_DIR}/metadata/dynamodb-locks.json" 2>/dev/null || {
        log_warn "Could not export DynamoDB lock table (table may be empty or not exist)."
        echo '{"Items": []}' > "${BACKUP_DIR}/metadata/dynamodb-locks.json"
    }
    
    log_info "DynamoDB state backed up."
}

# Create backup metadata
create_backup_metadata() {
    log_info "Creating backup metadata..."
    
    cat > "${BACKUP_DIR}/metadata/backup-info.txt" <<EOF
Terraform State Backup
======================
Backup Date: $(date)
Backup Directory: ${BACKUP_DIR}
S3 Bucket: ${STATE_BUCKET}
DynamoDB Table: ${DYNAMODB_TABLE}
Region: ${REGION}

AWS Account Information:
$(aws sts get-caller-identity)

Backed Up State Files:
$(aws s3 ls "s3://${STATE_BUCKET}/" --recursive --region "${REGION}" | grep ".tfstate" || echo "No state files found")

Git Information:
Branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "Not in git repository")
Commit: $(git rev-parse HEAD 2>/dev/null || echo "Not in git repository")
Status: 
$(git status --short 2>/dev/null || echo "Not in git repository")

Purpose: Pre-migration backup for BOS-AI VPC consolidation (Task 1.1)
EOF
    
    log_info "Backup metadata created."
}

# Verify backup integrity
verify_backup() {
    log_info "Verifying backup integrity..."
    
    local error_count=0
    
    # Check if S3 state files were backed up
    if [ ! -d "${BACKUP_DIR}/s3-state-files" ] || [ -z "$(ls -A ${BACKUP_DIR}/s3-state-files 2>/dev/null)" ]; then
        log_warn "S3 state files backup is empty or missing."
        ((error_count++))
    fi
    
    # Check if local configs were backed up
    if [ ! -d "${BACKUP_DIR}/local-configs" ] || [ -z "$(ls -A ${BACKUP_DIR}/local-configs 2>/dev/null)" ]; then
        log_warn "Local configs backup is empty or missing."
        ((error_count++))
    fi
    
    # Check if metadata was created
    if [ ! -f "${BACKUP_DIR}/metadata/backup-info.txt" ]; then
        log_warn "Backup metadata is missing."
        ((error_count++))
    fi
    
    if [ $error_count -eq 0 ]; then
        log_info "Backup verification passed."
        return 0
    else
        log_warn "Backup verification completed with ${error_count} warnings."
        return 1
    fi
}

# Create a symlink to latest backup
create_latest_symlink() {
    log_info "Creating symlink to latest backup..."
    
    cd "${BACKUP_ROOT}"
    rm -f latest
    ln -s "${TIMESTAMP}" latest
    cd - > /dev/null
    
    log_info "Symlink created: ${BACKUP_ROOT}/latest -> ${TIMESTAMP}"
}

# Main execution
main() {
    echo "========================================"
    echo "Terraform State Backup Script"
    echo "Task 1.1: Terraform state 파일 백업"
    echo "========================================"
    echo ""
    
    check_prerequisites
    create_backup_structure
    backup_s3_state_files
    backup_local_configs
    backup_dynamodb_state
    create_backup_metadata
    verify_backup
    create_latest_symlink
    
    echo ""
    echo "========================================"
    log_info "Backup completed successfully!"
    echo "========================================"
    echo ""
    echo "Backup location: ${BACKUP_DIR}"
    echo "Latest backup: ${BACKUP_ROOT}/latest"
    echo ""
    echo "To restore from this backup:"
    echo "  1. For S3 state: aws s3 sync ${BACKUP_DIR}/s3-state-files/full-backup/ s3://${STATE_BUCKET}/ --region ${REGION}"
    echo "  2. For local configs: cp -r ${BACKUP_DIR}/local-configs/* ."
    echo ""
}

# Run main function
main "$@"
