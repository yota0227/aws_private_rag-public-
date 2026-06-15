"""Check Qdrant status via SSM."""
import boto3
import time

ssm = boto3.client('ssm', region_name='us-east-1')

resp = ssm.send_command(
    InstanceIds=['i-0d520340617eb5484'],
    DocumentName='AWS-RunShellScript',
    Parameters={'commands': [
        'curl -s http://localhost:6333/healthz',
        'echo "---"',
        'curl -s http://localhost:6333/collections',
        'echo "---"',
        'cat /var/log/qdrant-setup.log 2>/dev/null | tail -10',
    ]}
)
cmd_id = resp['Command']['CommandId']
print(f"Command: {cmd_id}")

time.sleep(5)

result = ssm.get_command_invocation(
    CommandId=cmd_id,
    InstanceId='i-0d520340617eb5484'
)
print(f"Status: {result['Status']}")
print(f"Output:\n{result['StandardOutputContent']}")
if result['StandardErrorContent']:
    print(f"Errors:\n{result['StandardErrorContent'][:500]}")
