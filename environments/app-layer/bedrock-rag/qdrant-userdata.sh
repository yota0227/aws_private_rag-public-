#!/bin/bash
set -e
exec > /var/log/qdrant-setup.log 2>&1

echo "=== Qdrant Setup Start ==="
date

# System update
dnf update -y --quiet

# Download Qdrant binary from S3 (no internet needed, S3 Gateway Endpoint)
QDRANT_VERSION="1.14.0"
QDRANT_TARBALL="qdrant-x86_64-unknown-linux-musl.tar.gz"
S3_PATH="s3://bos-ai-rtl-src-533335672315/tools/${QDRANT_TARBALL}"

mkdir -p /opt/qdrant
cd /opt/qdrant

echo "Downloading Qdrant from S3..."
aws s3 cp "${S3_PATH}" "./${QDRANT_TARBALL}" --region us-east-1
tar xzf "${QDRANT_TARBALL}"
rm -f "${QDRANT_TARBALL}"
chmod +x /opt/qdrant/qdrant

# Create directories
mkdir -p /opt/qdrant/storage
mkdir -p /opt/qdrant/snapshots
mkdir -p /opt/qdrant/config

# Qdrant configuration
cat > /opt/qdrant/config/config.yaml <<'QDRANT_CONFIG'
storage:
  storage_path: /opt/qdrant/storage
  snapshots_path: /opt/qdrant/snapshots
  on_disk_payload: true

service:
  host: 0.0.0.0
  http_port: 6333
  grpc_port: 6334
  enable_tls: false

cluster:
  enabled: false

telemetry_disabled: true
QDRANT_CONFIG

# Create systemd service
cat > /etc/systemd/system/qdrant.service <<'SYSTEMD'
[Unit]
Description=Qdrant Vector Database
After=network.target

[Service]
Type=simple
ExecStart=/opt/qdrant/qdrant --config-path /opt/qdrant/config/config.yaml
Restart=always
RestartSec=5
LimitNOFILE=65536
WorkingDirectory=/opt/qdrant

[Install]
WantedBy=multi-user.target
SYSTEMD

# Start Qdrant
systemctl daemon-reload
systemctl enable qdrant
systemctl start qdrant

# Wait for Qdrant to be ready
echo "Waiting for Qdrant to start..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:6333/healthz > /dev/null 2>&1; then
    echo "Qdrant is ready!"
    break
  fi
  sleep 2
done

# Create RTL collection (1024 dimensions for Titan Embeddings v2)
echo "Creating rtl-knowledge-base collection..."
curl -X PUT "http://localhost:6333/collections/rtl-knowledge-base" \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 1024,
      "distance": "Cosine"
    },
    "optimizers_config": {
      "memmap_threshold": 20000,
      "indexing_threshold": 10000
    },
    "on_disk_payload": true
  }'

echo ""
echo "=== Qdrant Setup Complete ==="
echo "Endpoint: http://$(hostname -I | awk '{print $1}'):6333"
date
