#!/bin/bash
set -euo pipefail

# =============================================================================
# LiteLLM EC2 User Data Script
# Requirements: 1.7, 2.1-2.5, 3.3, 16.4, 16.5, 18.1-18.6, 22.1-22.4,
#               23.9, 24.1-24.3, 25.4, 26.1, 26.6
# =============================================================================

LOG_FILE="/var/log/user-data.log"
exec > >(tee -a "$LOG_FILE") 2>&1

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "========== LiteLLM EC2 User Data Start =========="

# =============================================================================
# 1. Format and mount data volume (Requirement 1.5)
# =============================================================================
log "Formatting and mounting data volume..."

# Wait for the device to appear (nitro uses nvme1n1 for /dev/sdf)
DEVICE=""
for i in $(seq 1 30); do
  if [ -b /dev/nvme1n1 ]; then
    DEVICE="/dev/nvme1n1"
    break
  elif [ -b /dev/sdf ]; then
    DEVICE="/dev/sdf"
    break
  fi
  log "Waiting for data volume to appear... attempt $i/30"
  sleep 2
done

if [ -z "$DEVICE" ]; then
  log "ERROR: Data volume not found after 60 seconds"
  exit 1
fi

log "Data volume found at $DEVICE"

# Format only if not already formatted
if ! blkid "$DEVICE" | grep -q xfs; then
  log "Formatting $DEVICE as xfs..."
  mkfs.xfs "$DEVICE"
fi

mkdir -p /data
mount "$DEVICE" /data

# Add to fstab for persistence
if ! grep -q "/data" /etc/fstab; then
  UUID=$(blkid -s UUID -o value "$DEVICE")
  echo "UUID=$UUID /data xfs defaults,nofail 0 2" >> /etc/fstab
fi

mkdir -p /data/litellm /data/postgres /data/backups /data/scripts
log "Data volume mounted at /data"

# =============================================================================
# 2. Install Docker and Docker Compose (Requirement 18.1)
# =============================================================================
log "Installing Docker and Docker Compose..."

dnf update -y
dnf install -y docker aws-cli jq

systemctl enable docker
systemctl start docker

# Install Docker Compose plugin
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/download/v2.29.2/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

log "Docker and Docker Compose installed"
docker --version
docker compose version

# =============================================================================
# 3. Retrieve secrets from Secrets Manager (Requirements 16.4, 16.5)
# =============================================================================
log "Retrieving secrets from Secrets Manager..."

REGION="${region}"

get_secret() {
  local secret_name="$1"
  local max_retries=3
  local retry=0
  local backoff=2

  while [ $retry -lt $max_retries ]; do
    local value
    value=$(aws secretsmanager get-secret-value \
      --secret-id "$secret_name" \
      --region "$REGION" \
      --query 'SecretString' \
      --output text 2>/dev/null) && {
      echo "$value"
      return 0
    }

    retry=$((retry + 1))
    log "WARNING: Failed to retrieve secret '$secret_name' (attempt $retry/$max_retries). Retrying in $${backoff}s..."
    sleep $backoff
    backoff=$((backoff * 2))
  done

  log "ERROR: Failed to retrieve secret '$secret_name' after $max_retries attempts"
  return 1
}

LITELLM_MASTER_KEY=$(get_secret "${litellm_master_key_arn}")
POSTGRES_PASSWORD=$(get_secret "${postgres_password_arn}")

if [ -z "$LITELLM_MASTER_KEY" ] || [ -z "$POSTGRES_PASSWORD" ]; then
  log "ERROR: Failed to retrieve required secrets. Aborting."
  exit 1
fi

log "Secrets retrieved successfully"

# =============================================================================
# 4. Create LiteLLM config.yaml (Requirements 2.2, 2.3, 18.3)
# =============================================================================
log "Creating LiteLLM config.yaml..."

cat > /data/litellm/config.yaml << 'LITELLM_CONFIG'
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY
  - model_name: gpt-4o-mini
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY
  - model_name: o3-mini
    litellm_params:
      model: openai/o3-mini
      api_key: os.environ/OPENAI_API_KEY
  - model_name: claude-3-5-sonnet
    litellm_params:
      model: bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0
      aws_region_name: us-east-1
  - model_name: claude-3-haiku
    litellm_params:
      model: bedrock/anthropic.claude-3-haiku-20240307-v1:0
      aws_region_name: us-east-1
  - model_name: claude-3-opus
    litellm_params:
      model: bedrock/anthropic.claude-3-opus-20240229-v1:0
      aws_region_name: us-east-1
  - model_name: titan-embed-text-v2
    litellm_params:
      model: bedrock/amazon.titan-embed-text-v2:0
      aws_region_name: us-east-1

general_settings:
  database_url: os.environ/DATABASE_URL
  master_key: os.environ/LITELLM_MASTER_KEY
  max_parallel_requests: 50

router_settings:
  num_retries: 2
  timeout: 120
  max_parallel_requests: 50
LITELLM_CONFIG

log "LiteLLM config.yaml created"

# =============================================================================
# 5. Create docker-compose.yml (Requirements 18.2, 18.4, 18.5, 25.4, 26.1)
# =============================================================================
log "Creating docker-compose.yml..."

cat > /data/docker-compose.yml << EOF
services:
  litellm:
    image: ghcr.io/berriai/litellm:v1.61.4
    container_name: litellm
    ports:
      - "4000:4000"
    environment:
      DATABASE_URL: postgresql://litellm:$${POSTGRES_PASSWORD}@postgres:5432/litellm
      LITELLM_MASTER_KEY: $${LITELLM_MASTER_KEY}
      OPENAI_API_KEY: $${OPENAI_API_KEY:-placeholder}
    volumes:
      - /data/litellm/config.yaml:/app/config.yaml
    command: ["--config", "/app/config.yaml"]
    deploy:
      resources:
        limits:
          memory: 3G
    restart: always
    depends_on:
      - postgres

  postgres:
    image: postgres:16-alpine
    container_name: postgres
    environment:
      POSTGRES_DB: litellm
      POSTGRES_USER: litellm
      POSTGRES_PASSWORD: $${POSTGRES_PASSWORD}
    volumes:
      - /data/postgres:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 1G
    restart: always
EOF

log "docker-compose.yml created"

# =============================================================================
# 6. Create backup script (Requirements 24.1, 24.2, 24.3)
# =============================================================================
log "Creating PostgreSQL backup script..."

cat > /data/scripts/backup-postgres.sh << 'BACKUP_SCRIPT'
#!/bin/bash
set -euo pipefail

LOG_FILE="/var/log/user-data.log"
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [BACKUP] $1" >> "$LOG_FILE"
}

BACKUP_DIR=/data/backups
DATE=$(date +%Y%m%d)
FILENAME="postgres-$${DATE}.sql.gz"

log "Starting PostgreSQL backup..."

# Dump and compress
docker exec postgres pg_dump -U litellm litellm | gzip > "$${BACKUP_DIR}/$${FILENAME}"
log "Backup created: $${BACKUP_DIR}/$${FILENAME}"

# Upload to S3
aws s3 cp "$${BACKUP_DIR}/$${FILENAME}" \
  s3://s3-bos-ai-backups-seoul-prod/llm-gateway/postgres/$${FILENAME} \
  --region ap-northeast-2
log "Backup uploaded to S3"

# Retain only last 7 local backups
ls -t $${BACKUP_DIR}/postgres-*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
log "Old local backups cleaned (keeping last 7)"

log "PostgreSQL backup completed successfully"
BACKUP_SCRIPT

chmod +x /data/scripts/backup-postgres.sh
log "Backup script created"

# =============================================================================
# 7. Set up cron job for backup (Requirement 24.1 — 03:00 KST)
# =============================================================================
log "Setting up backup cron job..."

# Set timezone to KST
timedatectl set-timezone Asia/Seoul

echo "0 3 * * * root /data/scripts/backup-postgres.sh" > /etc/cron.d/postgres-backup
chmod 644 /etc/cron.d/postgres-backup

log "Backup cron job configured for 03:00 KST daily"

# =============================================================================
# 8. Install and configure CloudWatch Agent (Requirement 23.9)
# =============================================================================
log "Installing CloudWatch Agent..."

dnf install -y amazon-cloudwatch-agent

cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CW_CONFIG'
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "root"
  },
  "metrics": {
    "namespace": "LLMGateway/LiteLLM",
    "metrics_collected": {
      "disk": {
        "measurement": ["used_percent", "inodes_free"],
        "metrics_collection_interval": 60,
        "resources": ["/", "/data"]
      },
      "mem": {
        "measurement": ["mem_used_percent", "mem_available"],
        "metrics_collection_interval": 60
      }
    }
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/user-data.log",
            "log_group_name": "/llm-gateway/litellm",
            "log_stream_name": "{instance_id}/user-data",
            "retention_in_days": 30
          }
        ]
      }
    }
  }
}
CW_CONFIG

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

log "CloudWatch Agent installed and configured"

# =============================================================================
# 9. Start containers (Requirement 18.5)
# =============================================================================
log "Starting Docker Compose services..."

cd /data
docker compose up -d

log "Docker Compose services started"

# Wait for services to be healthy
sleep 10
docker compose ps

log "========== LiteLLM EC2 User Data Complete =========="
