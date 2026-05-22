#!/bin/bash
# MCP Server EC2 User Data Script
# Installs Node.js 20, retrieves secrets, deploys MCP server, configures systemd
set -euo pipefail

LOG_FILE="/var/log/user-data.log"
exec > >(tee -a "$LOG_FILE") 2>&1

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "=== MCP Server User Data Script Started ==="

# =============================================================================
# 1. Install Node.js 20
# =============================================================================
log "Installing Node.js 20..."
dnf module enable nodejs:20 -y
dnf install nodejs -y
node --version
npm --version
log "Node.js 20 installed successfully"

# =============================================================================
# 2. Retrieve MCP API Key from Secrets Manager (retry 3x exponential backoff)
# =============================================================================
log "Retrieving MCP API key from Secrets Manager..."

MCP_API_KEY=""
MAX_RETRIES=3
RETRY_DELAY=2

for i in $(seq 1 $MAX_RETRIES); do
  MCP_API_KEY=$(aws secretsmanager get-secret-value \
    --secret-id "llm-gateway/mcp-api-key" \
    --region "${aws_region}" \
    --query 'SecretString' \
    --output text 2>/dev/null) && break

  log "WARNING: Secrets Manager retrieval attempt $i/$MAX_RETRIES failed, retrying in $${RETRY_DELAY}s..."
  sleep $RETRY_DELAY
  RETRY_DELAY=$((RETRY_DELAY * 2))
done

if [ -z "$MCP_API_KEY" ]; then
  log "ERROR: Failed to retrieve MCP API key after $MAX_RETRIES attempts"
  exit 1
fi
log "MCP API key retrieved successfully"

# =============================================================================
# 3. Create MCP Server application directory
# =============================================================================
log "Setting up MCP Server application..."
mkdir -p /opt/mcp-server

# =============================================================================
# 4. Create package.json
# =============================================================================
cat > /opt/mcp-server/package.json << 'PACKAGE_EOF'
${package_json}
PACKAGE_EOF

# =============================================================================
# 5. Create server.js
# =============================================================================
cat > /opt/mcp-server/server.js << 'SERVER_EOF'
${server_js}
SERVER_EOF

log "MCP Server application files created"

# =============================================================================
# 6. Install npm dependencies
# =============================================================================
log "Installing npm dependencies..."
cd /opt/mcp-server
npm install --production
log "npm dependencies installed successfully"

# =============================================================================
# 7. Create systemd service
# =============================================================================
log "Creating systemd service..."
cat > /etc/systemd/system/mcp-server.service << EOF
[Unit]
Description=BOS-AI MCP Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/mcp-server
Environment=NODE_ENV=production
Environment=MCP_API_KEY=$MCP_API_KEY
Environment=AWS_REGION=${aws_region}
ExecStartPre=/bin/bash -c 'sleep 2'
ExecStart=/usr/bin/node /opt/mcp-server/server.js
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mcp-server

[Install]
WantedBy=multi-user.target
EOF

log "systemd service created"

# =============================================================================
# 8. Install and configure CloudWatch Agent
# =============================================================================
log "Installing CloudWatch Agent..."
dnf install amazon-cloudwatch-agent -y

cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CW_EOF'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/user-data.log",
            "log_group_name": "/llm-gateway/mcp-server",
            "log_stream_name": "{instance_id}/user-data",
            "retention_in_days": 30
          }
        ]
      },
      "journald": {
        "collect_list": [
          {
            "unit": "mcp-server",
            "log_group_name": "/llm-gateway/mcp-server",
            "log_stream_name": "{instance_id}/mcp-server",
            "retention_in_days": 30
          }
        ]
      }
    }
  },
  "metrics": {
    "namespace": "LLMGateway/MCP",
    "metrics_collected": {
      "disk": {
        "measurement": ["used_percent"],
        "resources": ["/"]
      },
      "mem": {
        "measurement": ["mem_used_percent"]
      }
    }
  }
}
CW_EOF

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
  -s

log "CloudWatch Agent configured and started"

# =============================================================================
# 9. Enable and start MCP Server service
# =============================================================================
log "Starting MCP Server..."
systemctl daemon-reload
systemctl enable mcp-server
systemctl start mcp-server

log "Waiting for MCP Server to be ready..."
sleep 5

# Verify health endpoint
if curl -sf http://localhost:3000/health > /dev/null 2>&1; then
  log "MCP Server health check PASSED"
else
  log "WARNING: MCP Server health check did not pass yet (may still be starting)"
fi

log "=== MCP Server User Data Script Completed ==="
