"""Install Qdrant on EC2 via SSM (manual execution of user data script)."""
import boto3
import time

ssm = boto3.client('ssm', region_name='us-east-1')

commands = [
    'set -e',
    'cd /opt',
    'mkdir -p qdrant && cd qdrant',
    # Download from S3
    'aws s3 cp s3://bos-ai-rtl-src-533335672315/tools/qdrant-x86_64-unknown-linux-musl.tar.gz ./qdrant.tar.gz --region us-east-1',
    'tar xzf qdrant.tar.gz',
    'rm -f qdrant.tar.gz',
    'chmod +x /opt/qdrant/qdrant',
    # Directories
    'mkdir -p /opt/qdrant/storage /opt/qdrant/snapshots /opt/qdrant/config',
    # Config
    'cat > /opt/qdrant/config/config.yaml << EOF\n'
    'storage:\n'
    '  storage_path: /opt/qdrant/storage\n'
    '  snapshots_path: /opt/qdrant/snapshots\n'
    '  on_disk_payload: true\n'
    'service:\n'
    '  host: 0.0.0.0\n'
    '  http_port: 6333\n'
    '  grpc_port: 6334\n'
    '  enable_tls: false\n'
    'cluster:\n'
    '  enabled: false\n'
    'telemetry_disabled: true\n'
    'EOF',
    # Systemd service
    'cat > /etc/systemd/system/qdrant.service << EOF\n'
    '[Unit]\n'
    'Description=Qdrant Vector Database\n'
    'After=network.target\n'
    '[Service]\n'
    'Type=simple\n'
    'ExecStart=/opt/qdrant/qdrant --config-path /opt/qdrant/config/config.yaml\n'
    'Restart=always\n'
    'RestartSec=5\n'
    'LimitNOFILE=65536\n'
    'WorkingDirectory=/opt/qdrant\n'
    '[Install]\n'
    'WantedBy=multi-user.target\n'
    'EOF',
    # Start
    'systemctl daemon-reload',
    'systemctl enable qdrant',
    'systemctl start qdrant',
    'sleep 5',
    # Health check
    'curl -s http://localhost:6333/healthz || echo "HEALTH CHECK FAILED"',
    # Create collection
    'curl -X PUT "http://localhost:6333/collections/rtl-knowledge-base" '
    '-H "Content-Type: application/json" '
    '-d \'{"vectors":{"size":1024,"distance":"Cosine"},"optimizers_config":{"memmap_threshold":20000},"on_disk_payload":true}\'',
    'echo',
    'echo "=== DONE ==="',
]

print("Sending SSM command to install Qdrant...")
resp = ssm.send_command(
    InstanceIds=['i-0d520340617eb5484'],
    DocumentName='AWS-RunShellScript',
    Parameters={'commands': commands},
    TimeoutSeconds=120,
)
cmd_id = resp['Command']['CommandId']
print(f"Command ID: {cmd_id}")

# Wait for completion
for i in range(24):
    time.sleep(5)
    try:
        result = ssm.get_command_invocation(
            CommandId=cmd_id,
            InstanceId='i-0d520340617eb5484'
        )
        if result['Status'] in ('Success', 'Failed', 'TimedOut', 'Cancelled'):
            print(f"\nStatus: {result['Status']}")
            print(f"Output:\n{result['StandardOutputContent'][-1000:]}")
            if result['StandardErrorContent']:
                print(f"Errors:\n{result['StandardErrorContent'][-500:]}")
            break
    except Exception:
        pass
    print(".", end="", flush=True)
