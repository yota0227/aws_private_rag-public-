"""
BOS-AI RAG Document Processor Lambda Handler
Seoul Private RAG VPC → Virginia Backend (Bedrock, OpenSearch) via VPC Peering
"""
import json
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """Main Lambda handler for Private RAG API Gateway"""
    logger.info(f"Event: {json.dumps(event)}")
    
    path = event.get('path', '')
    method = event.get('httpMethod', '')
    
    # Health check
    if '/health' in path:
        return response(200, {
            'status': 'healthy',
            'region': os.environ.get('LAMBDA_REGION', 'ap-northeast-2'),
            'backend_region': os.environ.get('BACKEND_REGION', 'us-east-1'),
            'function': context.function_name,
            'version': '1.0.0'
        })
    
    # RAG Query
    if '/query' in path and method == 'POST':
        body = json.loads(event.get('body', '{}')) if event.get('body') else {}
        query = body.get('query', '')
        if not query:
            return response(400, {'error': 'query field is required'})
        return response(200, {
            'message': 'RAG query endpoint ready - Bedrock KB integration pending',
            'query': query
        })
    
    # Document upload
    if '/documents' in path and method == 'POST':
        return response(200, {
            'message': 'Document upload endpoint ready - S3 integration pending'
        })
    
    return response(404, {'error': f'Not found: {method} {path}'})


def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'X-Request-Id': 'placeholder'
        },
        'body': json.dumps(body, ensure_ascii=False)
    }
