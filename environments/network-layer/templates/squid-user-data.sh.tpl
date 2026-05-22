#!/bin/bash
# ==============================================================================
# Squid Forward Proxy — User Data Script
# Installs and configures Squid proxy with domain whitelist
# ==============================================================================

exec > >(tee /var/log/user-data.log) 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Squid proxy setup..."

# ------------------------------------------------------------------------------
# 1. Install Squid
# ------------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Installing Squid..."
dnf install -y squid

# ------------------------------------------------------------------------------
# 2. Create domain whitelist
# ------------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Creating domain whitelist..."
cat > /etc/squid/whitelist.txt <<'WHITELIST'
.kiro.dev
api.openai.com
api.anthropic.com
.amazoncognito.com
WHITELIST

# ------------------------------------------------------------------------------
# 3. Backup original config
# ------------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backing up original squid.conf..."
cp /etc/squid/squid.conf /etc/squid/squid.conf.bak

# ------------------------------------------------------------------------------
# 4. Create Squid configuration
# ------------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Writing Squid configuration..."
cat > /etc/squid/squid.conf <<'SQUIDCONF'
# ==============================================================================
# Squid Forward Proxy Configuration
# LLM Gateway — Domain Whitelist Access Control
# ==============================================================================

# ACL definitions
acl onprem_network src 192.128.0.0/16
acl SSL_ports port 443
acl CONNECT method CONNECT
acl allowed_domains dstdomain "/etc/squid/whitelist.txt"

# Access control rules
http_access deny !onprem_network
http_access deny CONNECT !SSL_ports
http_access allow onprem_network allowed_domains
http_access deny all

# Security: suppress forwarding headers
via off
request_header_access X-Forwarded-For deny all

# Logging
access_log /var/log/squid/access.log

# Port
http_port 3128
SQUIDCONF

# ------------------------------------------------------------------------------
# 5. Validate Squid configuration
# ------------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validating Squid configuration..."
if ! squid -k parse; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Squid config validation failed, restoring backup..."
  cp /etc/squid/squid.conf.bak /etc/squid/squid.conf
fi

# ------------------------------------------------------------------------------
# 6. Install CloudWatch Agent
# ------------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Installing CloudWatch Agent..."
dnf install -y amazon-cloudwatch-agent

cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'CWAGENT'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/squid/access.log",
            "log_group_name": "/llm-gateway/squid",
            "log_stream_name": "{instance_id}/access",
            "retention_in_days": 30
          },
          {
            "file_path": "/var/log/user-data.log",
            "log_group_name": "/llm-gateway/squid",
            "log_stream_name": "{instance_id}/user-data",
            "retention_in_days": 30
          }
        ]
      }
    }
  },
  "metrics": {
    "namespace": "LLMGateway/Squid",
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
CWAGENT

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

# ------------------------------------------------------------------------------
# 7. Enable and start Squid
# ------------------------------------------------------------------------------
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Enabling and starting Squid service..."
systemctl enable --now squid

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Squid proxy setup complete."
