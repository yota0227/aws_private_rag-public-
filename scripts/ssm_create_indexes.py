"""Create Qdrant payload indexes for text search and filtering."""
import boto3
import time

ssm = boto3.client('ssm', region_name='us-east-1')

commands = []
# Keyword indexes (exact match filtering)
for field in ['pipeline_id', 'topic', 'analysis_type', 'module_name']:
    commands.append(
        f'curl -s -X PUT "http://localhost:6333/collections/rtl-knowledge-base/index" '
        f'-H "Content-Type: application/json" '
        f'-d \'{{"field_name":"{field}","field_schema":"keyword"}}\''
    )

# Text indexes (full-text search)
for field in ['parsed_summary', 'claim_text', 'hdd_content', 'port_list', 'instance_list']:
    commands.append(
        f'curl -s -X PUT "http://localhost:6333/collections/rtl-knowledge-base/index" '
        f'-H "Content-Type: application/json" '
        f'-d \'{{"field_name":"{field}","field_schema":"text"}}\''
    )

commands.append('echo')
commands.append('echo "=== INDEXES CREATED ==="')

resp = ssm.send_command(
    InstanceIds=['i-0d520340617eb5484'],
    DocumentName='AWS-RunShellScript',
    Parameters={'commands': commands},
    TimeoutSeconds=30,
)
cmd_id = resp['Command']['CommandId']
print(f"Command: {cmd_id}")

time.sleep(10)
r = ssm.get_command_invocation(CommandId=cmd_id, InstanceId='i-0d520340617eb5484')
print(f"Status: {r['Status']}")
print(r['StandardOutputContent'][-500:])
