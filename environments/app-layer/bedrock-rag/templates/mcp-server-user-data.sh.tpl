#!/bin/bash
# MCP Server EC2 User Data Script
# DNF 완전 제거 — S3에서만 설치 (NAT 없는 환경)

LOG_FILE="/var/log/user-data.log"
exec > >(tee -a "$LOG_FILE") 2>&1

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "=== MCP Server User Data Script Started ==="

REGION="${aws_region}"
S3_BUCKET="bos-ai-rtl-src-533335672315"

# =============================================================================
# 1. Install Node.js 20 from S3 (NO dnf - no internet needed)
# =============================================================================
log "Installing Node.js 20 from S3..."

NODE_TARBALL="node-v20.18.0-linux-x64.tar.gz"
aws s3 cp "s3://$${S3_BUCKET}/deploy/$${NODE_TARBALL}" /tmp/ --region "$REGION"
tar -xzf "/tmp/$${NODE_TARBALL}" -C /usr/local --strip-components=1
log "Node.js installed: $(/usr/local/bin/node --version)"

# =============================================================================
# 2. Download MCP Server app from S3
# =============================================================================
log "Downloading MCP Server app from S3..."

aws s3 cp "s3://$${S3_BUCKET}/deploy/mcp-server.tar.gz" /tmp/mcp-server.tar.gz --region "$REGION"
rm -rf /opt/mcp-server
mkdir -p /tmp/mcp-unpack
tar -xzf /tmp/mcp-server.tar.gz -C /tmp/mcp-unpack
mv /tmp/mcp-unpack/mcp-server-build /opt/mcp-server

# Override server.js with auth-removed version
aws s3 cp "s3://$${S3_BUCKET}/deploy/mcp-server-noauth.js" /opt/mcp-server/server.js --region "$REGION" || true
log "MCP Server deployed: $(ls /opt/mcp-server)"

# =============================================================================
# 3. Skip API Key retrieval (auth removed — network isolation is sufficient)
# =============================================================================
MCP_API_KEY=""
log "Auth disabled — network isolation mode"

# =============================================================================
# 4. Create systemd service
# =============================================================================
cat > /etc/systemd/system/mcp-server.service << EOF
[Unit]
Description=BOS-AI MCP Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/mcp-server
Environment=NODE_ENV=production
Environment=MCP_API_KEY=$MCP_API_KEY
Environment=AWS_REGION=$REGION
ExecStart=/usr/local/bin/node /opt/mcp-server/server.js
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable mcp-server
systemctl start mcp-server
sleep 5

curl -sf http://localhost:3000/health && log "Health check PASSED" || log "WARNING: Health check pending"

log "=== MCP Server User Data Script Completed ==="
