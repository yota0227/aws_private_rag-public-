"""Start Qdrant service on EC2 via SSM (binary already downloaded)."""
import boto3
import time

ssm = boto3.client('ssm', region_name='us-east-1')

commands = [
    'chmod +x /opt/qdrant/qdrant',
    'mkdir -p /opt/qdrant/storage /opt/qdrant/snapshots /opt/qdrant/config',
    # Write config
    'echo "storage:" > /opt/qdrant/config/config.yaml',
    'echo "  storage_path: /opt/qdrant/storage" >> /opt/qdrant/config/config.yaml',
    'echo "  snapshots_path: /opt/qdrant/snapshots" >> /opt/qdrant/config/config.yaml',
    'echo "  on_disk_payload: true" >> /opt/qdrant/config/config.yaml',
    'echo "service:" >> /opt/qdrant/config/config.yaml',
    'echo "  host: 0.0.0.0" >> /opt/qdrant/config/config.yaml',
    'echo "  http_port: 6333" >> /opt/qdrant/config/config.yaml',
    'echo "  grpc_port: 6334" >> /opt/qdrant/config/config.yaml',
    'echo "  enable_tls: false" >> /opt/qdrant/config/config.yaml',
    'echo "cluster:" >> /opt/qdrant/config/config.yaml',
    'echo "  enabled: false" >> /opt/qdrant/config/config.yaml',
    'echo "telemetry_disabled: true" >> /opt/qdrant/config/config.yaml',
    # Write systemd unit
    'echo "[Unit]" > /etc/systemd/system/qdrant.service',
    'echo "Description=Qdrant Vector Database" >> /etc/systemd/system/qdrant.service',
    'echo "After=network.target" >> /etc/systemd/system/qdrant.service',
    'echo "[Service]" >> /etc/systemd/system/qdrant.service',
    'echo "Type=simple" >> /etc/systemd/system/qdrant.service',
    'echo "ExecStart=/opt/qdrant/qdrant --config-path /opt/qdrant/config/config.yaml" >> /etc/systemd/system/qdrant.service',
    'echo "Restart=always" >> /etc/systemd/system/qdrant.service',
    'echo "RestartSec=5" >> /etc/systemd/system/qdrant.service',
    'echo "LimitNOFILE=65536" >> /etc/systemd/system/qdrant.service',
    'echo "WorkingDirectory=/opt/qdrant" >> /etc/systemd/system/qdrant.service',
    'echo "[Install]" >> /etc/systemd/system/qdrant.service',
    'echo "WantedBy=multi-user.target" >> /etc/systemd/system/qdrant.service',
    # Start service
    'systemctl daemon-reload',
    'systemctl enable qdrant',
    'systemctl restart qdrant',
    'sleep 5',
    # Health check
    'curl -s http://localhost:6333/healthz || echo "HEALTH_FAIL"',
    'echo "---"',
    # Create collection
    'curl -s -X PUT "http://localhost:6333/collections/rtl-knowledge-base" -H "Content-Type: application/json" -d \'{"vectors":{"size":1024,"distance":"Cosine"},"optimizers_config":{"memmap_threshold":20000},"on_disk_payload":true}\'',
    'echo ""',
    'echo "=== DONE ==="',
]

resp = ssm.send_command(
    InstanceIds=['i-0d520340617eb5484'],
    DocumentName='AWS-RunShellScript',
    Parameters={'commands': commands},
    TimeoutSeconds=60,
)
cmd_id = resp['Command']['CommandId']
print(f"Command: {cmd_id}")

for i in range(12):
    time.sleep(5)
    try:
        r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId='i-0d520340617eb5484')
        if r['Status'] in ('Success', 'Failed', 'TimedOut'):
            print(f"Status: {r['Status']}")
            print(r['StandardOutputContent'][-500:])
            if r['StandardErrorContent']:
                print(f"ERR: {r['StandardErrorContent'][-300:]}")
            break
    except Exception:
        pass
    print(".", end="", flush=True)
