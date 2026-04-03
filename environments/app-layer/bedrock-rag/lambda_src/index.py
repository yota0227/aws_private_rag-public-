"""
BOS-AI RAG Document Processor Lambda Handler
Seoul Private RAG VPC → Virginia Backend (Bedrock, OpenSearch) via VPC Peering

Endpoints:
  GET  /rag/upload                  - 웹 업로드 UI 서빙
  POST /rag/documents/initiate      - S3 multipart upload 시작
  POST /rag/documents/upload-part   - chunk 업로드
  POST /rag/documents/complete      - multipart upload 완료 + KB sync
  GET  /rag/documents               - 업로드된 파일 목록
  POST /rag/query                   - RAG 질의
  GET  /rag/health                  - 헬스체크
"""
import json
import os
import logging
import base64
import uuid
import zipfile
import tarfile
import shutil
import tempfile
import time
import boto3
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET_SEOUL = os.environ.get('S3_BUCKET_SEOUL', 'bos-ai-documents-seoul-v3')
S3_PREFIX = 'documents/'
BEDROCK_KB_ID = os.environ.get('BEDROCK_KB_ID', '')
BEDROCK_KB_DATA_SOURCE_ID = os.environ.get('BEDROCK_KB_DATA_SOURCE_ID', '')
BACKEND_REGION = os.environ.get('BACKEND_REGION', 'us-east-1')

# 팀/카테고리 정의 (카테고리 추가 시 여기만 수정)
TEAMS = {
    'soc': {'name': 'SoC', 'categories': ['code', 'spec']}
}
VALID_CATEGORIES = {f"{t}/{c}" for t, info in TEAMS.items() for c in info['categories']}

s3_client = boto3.client('s3', region_name='ap-northeast-2')

# 비동기 압축 해제 관련 설정
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'rag-extraction-tasks-dev')
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
lambda_client = boto3.client('lambda', region_name='ap-northeast-2')
ALLOWED_EXTENSIONS = ['pdf', 'txt', 'docx', 'csv', 'html', 'md', 'v', 'sv', 'vhd', 'vhdl', 'vh', 'svh', 'py', 'c', 'h', 'cpp', 'hpp', 'json', 'yaml', 'yml', 'xml', 'tcl', 'sdc', 'xdc']
ARCHIVE_EXTENSIONS = ['zip', 'tar.gz']
SYSTEM_FILES = ['__MACOSX', 'Thumbs.db', '.DS_Store']


def handler(event, context):
    """Main Lambda handler for Private RAG API Gateway"""
    # 비동기 Lambda Event Invocation 처리
    if event.get('action') == 'process_extraction':
        return process_extraction(event)
    if event.get('action') == 'backfill_metadata':
        return backfill_metadata(event, context)


    logger.info(f"Event path: {event.get('path')}, method: {event.get('httpMethod')}")

    path = event.get('path', '')
    method = event.get('httpMethod', '')

    try:
        # 웹 업로드 UI
        if '/upload' in path and method == 'GET':
            return serve_upload_ui()

        # Multipart upload 시작
        if '/documents/initiate' in path and method == 'POST':
            return initiate_upload(event)

        # Chunk 업로드
        if '/documents/upload-part' in path and method == 'POST':
            return upload_part(event)

        # Multipart upload 완료
        if '/documents/complete' in path and method == 'POST':
            return complete_upload(event)

        # Pre-signed URL 생성
        if '/documents/presign' in path and method == 'POST':
            return presign_upload(event)

        # 업로드 완료 확인
        if '/documents/confirm' in path and method == 'POST':
            return confirm_upload(event)

        # 압축 해제 상태 조회 (extract-status를 extract보다 먼저 매칭)
        if '/documents/extract-status' in path and method == 'GET':
            return get_extraction_status(event)

        # 비동기 압축 해제 시작
        if '/documents/extract' in path and method == 'POST':
            return start_extraction(event)

        # 파일 삭제
        if '/documents/delete' in path and method == 'POST':
            return delete_document(event)

        # 파일 목록
        if '/documents' in path and method == 'GET':
            return list_documents(event)

        # 카테고리 목록 (UI용)
        if '/categories' in path and method == 'GET':
            return response(200, {'teams': TEAMS})

        # Health check
        if '/health' in path:
            return response(200, {
                'status': 'healthy',
                'region': os.environ.get('LAMBDA_REGION', 'ap-northeast-2'),
                'backend_region': BACKEND_REGION,
                'function': context.function_name,
                'version': '2.0.0'
            })

        # RAG Query
        if '/query' in path and method == 'POST':
            return handle_query(event)

        return response(404, {'error': f'Not found: {method} {path}'})

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return response(500, {'error': str(e)})


# ============================================================================
# Multipart Upload Handlers
# ============================================================================

def initiate_upload(event):
    """S3 multipart upload 시작 - upload_id 반환"""
    body = parse_body(event)
    filename = body.get('filename', '')
    content_type = body.get('content_type', 'application/octet-stream')
    team = body.get('team', '')
    category = body.get('category', '')

    if not filename:
        return response(400, {'error': 'filename is required'})
    if not team or not category:
        return response(400, {'error': 'team and category are required'})
    if f"{team}/{category}" not in VALID_CATEGORIES:
        return response(400, {'error': f'Invalid team/category: {team}/{category}. Valid: {sorted(VALID_CATEGORIES)}'})

    # S3 key: documents/{team}/{category}/{filename}
    key = f"{S3_PREFIX}{team}/{category}/{filename}"

    resp = s3_client.create_multipart_upload(
        Bucket=S3_BUCKET_SEOUL,
        Key=key,
        ContentType=content_type,
        ServerSideEncryption='aws:kms',
        Metadata={
            'uploaded-by': 'rag-web-ui',
            'upload-time': datetime.utcnow().isoformat(),
            'team': team,
            'category': category
        }
    )

    logger.info(f"Initiated multipart upload: {key}, upload_id: {resp['UploadId']}")
    return response(200, {
        'upload_id': resp['UploadId'],
        'key': key
    })


def upload_part(event):
    """개별 chunk를 S3에 업로드"""
    body = parse_body(event)
    upload_id = body.get('upload_id', '')
    key = body.get('key', '')
    part_number = int(body.get('part_number', 0))
    chunk_data = body.get('data', '')  # base64 encoded

    if not all([upload_id, key, part_number, chunk_data]):
        return response(400, {'error': 'upload_id, key, part_number, data are required'})

    decoded = base64.b64decode(chunk_data)

    resp = s3_client.upload_part(
        Bucket=S3_BUCKET_SEOUL,
        Key=key,
        UploadId=upload_id,
        PartNumber=part_number,
        Body=decoded
    )

    logger.info(f"Uploaded part {part_number} for {key}, ETag: {resp['ETag']}")
    return response(200, {
        'etag': resp['ETag'],
        'part_number': part_number
    })


def complete_upload(event):
    """Multipart upload 완료 + Bedrock KB sync 트리거"""
    body = parse_body(event)
    upload_id = body.get('upload_id', '')
    key = body.get('key', '')
    parts = body.get('parts', [])  # [{'PartNumber': 1, 'ETag': '...'}, ...]

    if not all([upload_id, key, parts]):
        return response(400, {'error': 'upload_id, key, parts are required'})

    # Complete multipart upload
    resp = s3_client.complete_multipart_upload(
        Bucket=S3_BUCKET_SEOUL,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={'Parts': parts}
    )

    logger.info(f"Completed multipart upload: {key}, Location: {resp.get('Location')}")

    # Bedrock KB sync (if configured)
    sync_result = trigger_kb_sync()

    return response(200, {
        'message': 'Upload complete',
        'key': key,
        'bucket': S3_BUCKET_SEOUL,
        'location': resp.get('Location', ''),
        'kb_sync': sync_result
    })


# ============================================================================
# Pre-signed URL Upload Handlers
# ============================================================================

def presign_upload(event):
    """Pre-signed URL 생성 — 클라이언트가 S3에 직접 업로드할 수 있는 서명 URL 반환"""
    body = parse_body(event)
    filename = body.get('filename', '')
    team = body.get('team', '')
    category = body.get('category', '')
    content_type = body.get('content_type', 'application/octet-stream')

    # 필수 필드 검증
    missing = [f for f in ['filename', 'team', 'category'] if not body.get(f)]
    if missing:
        return response(400, {
            'error': f'{", ".join(missing)} are required',
            'missing_fields': missing
        })

    # team/category 유효성 검증
    if f"{team}/{category}" not in VALID_CATEGORIES:
        return response(400, {
            'error': f'Invalid team/category: {team}/{category}. Valid: {sorted(VALID_CATEGORIES)}'
        })

    key = f"{S3_PREFIX}{team}/{category}/{filename}"

    presigned_url = s3_client.generate_presigned_url(
        'put_object',
        Params={
            'Bucket': S3_BUCKET_SEOUL,
            'Key': key,
            'ContentType': content_type
        },
        ExpiresIn=3600
    )

    logger.info(f"Generated presigned URL for: {key}")
    return response(200, {
        'presigned_url': presigned_url,
        's3_key': key,
        'expires_in': 3600
    })


def confirm_upload(event):
    """업로드 완료 확인 — S3 파일 존재 확인 + 메타데이터 생성 + 선택적 KB Sync"""
    body = parse_body(event)
    s3_key = body.get('s3_key', '')
    skip_sync = body.get('skip_sync', False)
    is_archive = body.get('is_archive', False)
    team = body.get('team', '')
    category = body.get('category', '')
    version = body.get('version', '1.0')
    source_system = body.get('source_system', 'manual_upload')

    if not s3_key:
        return response(400, {'error': 's3_key is required'})

    # S3 파일 존재 확인
    try:
        s3_client.head_object(Bucket=S3_BUCKET_SEOUL, Key=s3_key)
    except s3_client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            return response(404, {'error': 'File not found in S3', 's3_key': s3_key})
        raise

    # 메타데이터 파일 생성
    metadata_created = False
    if not is_archive:
        try:
            create_metadata_file(s3_key, team=team, category=category,
                                 version=version, source_system=source_system)
            metadata_created = True
        except Exception as e:
            logger.warning(f"Metadata creation failed (non-blocking): {str(e)}")

    # KB Sync 제어: archive 파일은 extract 완료 후 sync하므로 여기서 skip
    sync_result = 'skipped'
    if not skip_sync and not is_archive:
        sync_result = trigger_kb_sync()

    logger.info(f"Upload confirmed: {s3_key}, metadata: {metadata_created}, kb_sync: {sync_result}")
    return response(200, {
        'message': 'Upload confirmed',
        'key': s3_key,
        'metadata_created': metadata_created,
        'kb_sync': sync_result
    })


# ============================================================================
# Async Extraction Handlers
# ============================================================================

def start_extraction(event):
    """비동기 압축 해제 시작 — DynamoDB에 Task 생성 + Lambda Event 호출"""
    body = parse_body(event)
    s3_key = body.get('s3_key', '')
    team = body.get('team', '')
    category = body.get('category', '')

    if not s3_key:
        return response(400, {'error': 's3_key is required'})

    now = datetime.utcnow()
    task_id = f"ext-{now.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8]}"

    # DynamoDB에 초기 레코드 생성
    table = dynamodb.Table(DYNAMODB_TABLE)
    table.put_item(Item={
        'task_id': task_id,
        'status': '대기중',
        's3_key': s3_key,
        'team': team,
        'category': category,
        'created_at': now.isoformat(),
        'updated_at': now.isoformat(),
        'ttl': int(time.time()) + 7 * 24 * 3600  # 7일 후 자동 삭제
    })

    # Lambda 비동기 호출
    lambda_client.invoke(
        FunctionName=os.environ['AWS_LAMBDA_FUNCTION_NAME'],
        InvocationType='Event',
        Payload=json.dumps({
            'action': 'process_extraction',
            'task_id': task_id,
            's3_key': s3_key,
            'team': team,
            'category': category
        })
    )

    logger.info(f"Extraction task created: {task_id} for {s3_key}")
    return response(202, {
        'task_id': task_id,
        'status': '대기중',
        'message': 'Extraction task created'
    })


def process_extraction(event):
    """실제 압축 해제 로직 — 비동기 Lambda Event Invocation으로 실행"""
    task_id = event.get('task_id')
    s3_key = event.get('s3_key')
    team = event.get('team', '')
    category = event.get('category', '')

    table = dynamodb.Table(DYNAMODB_TABLE)
    tmp_dir = None

    try:
        # 상태를 "처리중"으로 갱신
        table.update_item(
            Key={'task_id': task_id},
            UpdateExpression='SET #s = :s, updated_at = :u',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': '처리중', ':u': datetime.utcnow().isoformat()}
        )

        # S3에서 Archive 다운로드
        tmp_dir = tempfile.mkdtemp(dir='/tmp')
        filename = os.path.basename(s3_key)
        archive_path = os.path.join(tmp_dir, filename)
        s3_client.download_file(S3_BUCKET_SEOUL, s3_key, archive_path)

        # 압축 해제
        extract_dir = os.path.join(tmp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)

        if filename.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zf:
                zf.extractall(extract_dir)
        elif filename.endswith('.tar.gz') or filename.endswith('.tgz'):
            with tarfile.open(archive_path, 'r:gz') as tf:
                tf.extractall(extract_dir)
        else:
            raise ValueError(f"Unsupported archive format: {filename}")

        # 해제된 파일 처리
        success_files = []
        skipped_files = []
        error_files = []

        for root, dirs, files in os.walk(extract_dir):
            for fname in files:
                filepath = os.path.join(root, fname)
                rel_path = os.path.relpath(filepath, extract_dir)

                # flatten_path로 파일명 변환 + 필터링
                flat_name = flatten_path(rel_path)
                if flat_name is None:
                    skipped_files.append(rel_path)
                    continue

                # 확장자 검증
                ext = flat_name.rsplit('.', 1)[-1].lower() if '.' in flat_name else ''
                if ext not in ALLOWED_EXTENSIONS:
                    skipped_files.append(rel_path)
                    continue

                # S3에 업로드
                try:
                    dest_key = f"{S3_PREFIX}{team}/{category}/{flat_name}"
                    s3_client.upload_file(filepath, S3_BUCKET_SEOUL, dest_key)
                    # 메타데이터 파일 생성
                    try:
                        create_metadata_file(dest_key, team=team, category=category)
                    except Exception as meta_err:
                        logger.warning(f"Metadata creation failed for {flat_name} (non-blocking): {meta_err}")
                    success_files.append(flat_name)
                except Exception as upload_err:
                    logger.error(f"Failed to upload {flat_name}: {upload_err}")
                    error_files.append(flat_name)

        # 원본 Archive S3 삭제
        s3_client.delete_object(Bucket=S3_BUCKET_SEOUL, Key=s3_key)

        # KB Sync
        sync_result = trigger_kb_sync()

        # 결과 기록
        total_files = len(success_files) + len(skipped_files) + len(error_files)
        results = {
            'total_files': total_files,
            'success_count': len(success_files),
            'skipped_count': len(skipped_files),
            'error_count': len(error_files),
            'success_files': success_files,
            'skipped_files': skipped_files,
            'error_files': error_files,
            'kb_sync': sync_result
        }

        table.update_item(
            Key={'task_id': task_id},
            UpdateExpression='SET #s = :s, updated_at = :u, results = :r',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':s': '완료',
                ':u': datetime.utcnow().isoformat(),
                ':r': results
            }
        )

        logger.info(f"Extraction complete: {task_id}, {total_files} files processed")
        return {'status': '완료', 'task_id': task_id, 'results': results}

    except Exception as e:
        logger.error(f"Extraction failed: {task_id}, error: {str(e)}", exc_info=True)
        try:
            table.update_item(
                Key={'task_id': task_id},
                UpdateExpression='SET #s = :s, updated_at = :u, error_message = :e',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':s': '실패',
                    ':u': datetime.utcnow().isoformat(),
                    ':e': str(e)
                }
            )
        except Exception:
            logger.error(f"Failed to update DynamoDB status for {task_id}")
        return {'status': '실패', 'task_id': task_id, 'error': str(e)}

    finally:
        # /tmp 정리
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def get_extraction_status(event):
    """Extraction Task 상태 조회"""
    params = event.get('queryStringParameters') or {}
    task_id = params.get('task_id', '')

    if not task_id:
        return response(400, {'error': 'task_id is required'})

    table = dynamodb.Table(DYNAMODB_TABLE)
    result = table.get_item(Key={'task_id': task_id})
    item = result.get('Item')

    if not item:
        return response(404, {'error': 'Task not found', 'task_id': task_id})

    return response(200, {
        'task_id': item.get('task_id'),
        'status': item.get('status'),
        'created_at': item.get('created_at'),
        'updated_at': item.get('updated_at'),
        'results': item.get('results'),
        'error_message': item.get('error_message')
    })


def trigger_kb_sync():
    """Bedrock Knowledge Base 데이터 소스 동기화"""
    if not BEDROCK_KB_ID or not BEDROCK_KB_DATA_SOURCE_ID:
        return 'skipped - KB ID or Data Source ID not configured'

    try:
        from botocore.config import Config
        from botocore.exceptions import ClientError
        bedrock_config = Config(
            connect_timeout=5,
            read_timeout=10,
            retries={'max_attempts': 1}
        )
        bedrock_agent = boto3.client('bedrock-agent', region_name=BACKEND_REGION, config=bedrock_config)
        resp = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=BEDROCK_KB_ID,
            dataSourceId=BEDROCK_KB_DATA_SOURCE_ID
        )
        job_id = resp['ingestionJob']['ingestionJobId']
        logger.info(f"KB sync started: job_id={job_id}")
        return f'sync started - job_id: {job_id}'
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'ConflictException':
            logger.warning(f"KB sync skipped - already in progress: {str(e)}")
            return 'sync skipped - already in progress'
        logger.error(f"KB sync failed: {str(e)}")
        return f'sync failed - {str(e)}'
    except Exception as e:
        logger.error(f"KB sync failed: {str(e)}")
        return f'sync failed - {str(e)}'


# ============================================================================
# Document List & Query Handlers
# ============================================================================

def delete_document(event):
    """S3에서 문서 삭제 + KB Sync 트리거"""
    body = parse_body(event)
    s3_key = body.get('s3_key', '')

    if not s3_key:
        return response(400, {'error': 's3_key is required'})

    # documents/ 프리픽스 내 파일만 삭제 허용 (보안)
    if not s3_key.startswith(S3_PREFIX):
        return response(403, {'error': 'Cannot delete files outside documents/ prefix'})

    try:
        s3_client.head_object(Bucket=S3_BUCKET_SEOUL, Key=s3_key)
    except Exception as e:
        if '404' in str(e) or 'NoSuchKey' in str(e):
            return response(404, {'error': 'File not found', 's3_key': s3_key})
        raise

    s3_client.delete_object(Bucket=S3_BUCKET_SEOUL, Key=s3_key)
    logger.info(f"Deleted document: {s3_key}")

    sync_result = trigger_kb_sync()

    return response(200, {
        'message': 'Document deleted',
        'key': s3_key,
        'kb_sync': sync_result
    })


def list_documents(event=None):
    """Seoul S3 버킷의 문서 목록 조회 (team/category 필터 지원)"""
    try:
        # query parameter에서 team/category 필터
        params = (event or {}).get('queryStringParameters') or {}
        team = params.get('team', '')
        category = params.get('category', '')

        if team and category:
            prefix = f"{S3_PREFIX}{team}/{category}/"
        elif team:
            prefix = f"{S3_PREFIX}{team}/"
        else:
            prefix = S3_PREFIX

        resp = s3_client.list_objects_v2(
            Bucket=S3_BUCKET_SEOUL,
            Prefix=prefix,
            MaxKeys=100
        )

        files = []
        for obj in resp.get('Contents', []):
            key = obj['Key']
            if key.endswith('/'):
                continue
            # key에서 team/category 파싱: documents/{team}/{category}/{filename}
            parts = key.replace(S3_PREFIX, '').split('/', 2)
            file_team = parts[0] if len(parts) >= 3 else ''
            file_cat = parts[1] if len(parts) >= 3 else ''
            file_name = parts[2] if len(parts) >= 3 else parts[-1]

            files.append({
                'key': key,
                'filename': file_name,
                'team': file_team,
                'category': file_cat,
                'size': obj['Size'],
                'last_modified': obj['LastModified'].isoformat()
            })

        return response(200, {
            'files': files,
            'count': len(files),
            'bucket': S3_BUCKET_SEOUL
        })
    except Exception as e:
        logger.error(f"List documents error: {str(e)}")
        return response(500, {'error': str(e)})


def handle_query(event):
    """RAG 질의 처리 - Hybrid Search, 필터, 구조화 로그 지원"""
    start_time = time.time()
    body = parse_body(event)
    query = body.get('query', '')
    if not query:
        return response(400, {'error': 'query field is required'})

    if not BEDROCK_KB_ID:
        return response(200, {
            'message': 'RAG query endpoint ready - Bedrock KB ID not configured',
            'query': query
        })

    # 검색 설정 (환경 변수에서 읽기)
    search_type = os.environ.get('SEARCH_TYPE', 'HYBRID')
    results_count = int(os.environ.get('SEARCH_RESULTS_COUNT', '5'))

    # 필터 구성
    filter_obj = body.get('filter', None)
    bedrock_filter = build_bedrock_filter(filter_obj) if filter_obj else None

    try:
        bedrock_runtime = boto3.client('bedrock-agent-runtime', region_name=BACKEND_REGION)

        # vectorSearchConfiguration 구성
        vector_config = {
            'searchType': search_type,
            'numberOfResults': results_count
        }
        if bedrock_filter:
            vector_config['filter'] = bedrock_filter

        resp = bedrock_runtime.retrieve_and_generate(
            input={'text': query},
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': BEDROCK_KB_ID,
                    'modelArn': os.environ.get('FOUNDATION_MODEL_ARN',
                        'us.anthropic.claude-3-5-haiku-20241022-v1:0'),
                    'retrievalConfiguration': {
                        'vectorSearchConfiguration': vector_config
                    }
                }
            }
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        # 응답 구조 개선 - score, version, source_system 포함
        citations = []
        for c in resp.get('citations', []):
            refs = []
            for r in c.get('retrievedReferences', []):
                ref = {
                    'uri': r.get('location', {}).get('s3Location', {}).get('uri', ''),
                    'score': r.get('metadata', {}).get('score', r.get('score', None))
                }
                meta = r.get('metadata', {})
                if meta.get('version'):
                    ref['version'] = meta['version']
                if meta.get('source_system'):
                    ref['source_system'] = meta['source_system']
                refs.append(ref)
            citations.append({
                'text': c.get('generatedResponsePart', {}).get('textResponsePart', {}).get('text', ''),
                'references': refs
            })

        citation_count = sum(len(c.get('references', [])) for c in citations)

        # 구조화 로그
        logger.info(json.dumps({
            'event': 'rag_query', 'query_length': len(query), 'search_type': search_type,
            'citation_count': citation_count, 'response_time_ms': response_time_ms,
            'has_filter': bedrock_filter is not None
        }))

        if citation_count == 0:
            logger.warning(json.dumps({'event': 'no_citation_query', 'query_length': len(query), 'search_type': search_type}))

        if response_time_ms > 30000:
            logger.warning(json.dumps({'event': 'slow_query', 'response_time_ms': response_time_ms, 'query_length': len(query)}))

        return response(200, {
            'answer': resp['output']['text'],
            'citations': citations,
            'metadata': {
                'search_type': search_type,
                'results_count': results_count,
                'query_length': len(query),
                'response_time_ms': response_time_ms
            }
        })

    except Exception as e:
        from botocore.exceptions import ClientError
        if isinstance(e, ClientError):
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'ValidationException':
                logger.error(json.dumps({'event': 'query_error', 'error_type': 'ValidationException', 'message': str(e)}))
                return response(400, {'error': f'Validation error: {str(e)}'})
            elif error_code == 'ThrottlingException':
                logger.warning(json.dumps({'event': 'query_error', 'error_type': 'ThrottlingException', 'message': str(e)}))
                return response(429, {'error': f'Rate limit exceeded: {str(e)}'})
        logger.error(f"RAG query error: {str(e)}")
        return response(500, {'error': str(e)})


# ============================================================================
# Web Upload UI
# ============================================================================

def serve_upload_ui():
    """웹 업로드 페이지 HTML 서빙"""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/html; charset=utf-8'
        },
        'body': get_upload_html()
    }


# ============================================================================
# Utility Functions
# ============================================================================

# ============================================================================
# RAG Search Optimization — Utility Functions
# ============================================================================

DOCUMENT_TYPE_MAP = {'pdf': 'pdf', 'txt': 'text', 'md': 'markdown', 'v': 'rtl', 'sv': 'rtl', 'vhd': 'rtl', 'vhdl': 'rtl', 'vh': 'rtl', 'svh': 'rtl', 'py': 'code', 'c': 'code', 'h': 'code', 'cpp': 'code', 'hpp': 'code', 'tcl': 'script', 'sdc': 'constraint', 'xdc': 'constraint'}


def create_metadata_file(s3_key, team='', category='', version='1.0', source_system='manual_upload', bucket=None):
    """S3 객체에 대한 .metadata.json 사이드카 파일 생성 (Bedrock KB 메타데이터 필터링 형식)"""
    if bucket is None:
        bucket = S3_BUCKET_SEOUL

    ext = s3_key.rsplit('.', 1)[-1].lower() if '.' in s3_key else ''
    document_type = DOCUMENT_TYPE_MAP.get(ext, 'other')

    metadata = {
        'metadataAttributes': {
            'team': team or '',
            'category': category or '',
            'document_type': document_type,
            'upload_date': datetime.utcnow().isoformat() + 'Z',
            'version': version or '1.0',
            'source_system': source_system or 'manual_upload'
        }
    }

    metadata_key = s3_key + '.metadata.json'
    s3_client.put_object(
        Bucket=bucket,
        Key=metadata_key,
        Body=json.dumps(metadata, ensure_ascii=False).encode('utf-8'),
        ContentType='application/json'
    )
    logger.info(f"Metadata file created: {metadata_key}")
    return metadata_key


def build_bedrock_filter(filter_obj):
    """filter 객체를 Bedrock KB 필터 구문으로 변환"""
    conditions = []
    if filter_obj.get('team'):
        conditions.append({'equals': {'key': 'team', 'value': filter_obj['team']}})
    if filter_obj.get('category'):
        conditions.append({'equals': {'key': 'category', 'value': filter_obj['category']}})
    if filter_obj.get('source_system'):
        conditions.append({'equals': {'key': 'source_system', 'value': filter_obj['source_system']}})

    if len(conditions) == 0:
        return None
    elif len(conditions) == 1:
        return conditions[0]
    else:
        return {'andAll': conditions}


def parse_team_category_from_key(s3_key):
    """S3 키 경로에서 team/category 파싱 (documents/{team}/{category}/{filename})"""
    parts = s3_key.replace(S3_PREFIX, '', 1).split('/')
    if len(parts) >= 3:
        return parts[0], parts[1]
    return '', ''


def backfill_metadata(event, context):
    """기존 문서에 대한 메타데이터 일괄 생성 (Lambda Event 비동기 호출 전용)"""
    continuation_token = event.get('continuation_token', None)
    max_items = 500
    processed_count = 0
    skipped_count = 0
    error_count = 0

    list_params = {
        'Bucket': S3_BUCKET_SEOUL,
        'Prefix': S3_PREFIX,
        'MaxKeys': 1000
    }
    if continuation_token:
        list_params['StartAfter'] = continuation_token

    last_key = None

    try:
        resp = s3_client.list_objects_v2(**list_params)
        objects = resp.get('Contents', [])

        for obj in objects:
            if context and context.get_remaining_time_in_millis() < 30000:
                logger.info(f"Backfill paused: remaining time < 30s, processed={processed_count}")
                break

            if processed_count >= max_items:
                break

            key = obj['Key']
            last_key = key

            if key.endswith('.metadata.json') or key.endswith('/'):
                continue

            # 이미 메타데이터가 있는지 확인
            metadata_key = key + '.metadata.json'
            try:
                s3_client.head_object(Bucket=S3_BUCKET_SEOUL, Key=metadata_key)
                skipped_count += 1
                continue
            except Exception:
                pass

            try:
                team, category = parse_team_category_from_key(key)
                create_metadata_file(key, team=team, category=category)
                processed_count += 1
            except Exception as e:
                logger.error(f"Backfill error for {key}: {str(e)}")
                error_count += 1

        if processed_count > 0:
            trigger_kb_sync()

        has_more = (processed_count >= max_items) or (context and context.get_remaining_time_in_millis() < 30000)
        result = {
            'processed_count': processed_count,
            'skipped_count': skipped_count,
            'error_count': error_count,
            'has_more': has_more
        }
        if has_more and last_key:
            result['continuation_token'] = last_key

        logger.info(f"Backfill complete: {json.dumps(result)}")
        return result

    except Exception as e:
        logger.error(f"Backfill failed: {str(e)}", exc_info=True)
        return {'error': str(e), 'processed_count': processed_count, 'error_count': error_count + 1}


# ============================================================================
# Utility Functions
# ============================================================================

def flatten_path(filepath):
    """경로 평탄화 — 디렉토리 구분자를 _로 변환, 숨김/시스템 파일 필터링"""
    # 경로 구성 요소 분리
    parts = filepath.replace('\\', '/').split('/')

    # 숨김 파일 또는 시스템 파일 필터링
    for part in parts:
        if part.startswith('.'):
            return None
        if part in SYSTEM_FILES:
            return None

    # / → _ 변환
    return '_'.join(parts)

def parse_body(event):
    """이벤트 body 파싱 (base64 인코딩 처리 포함)"""
    body = event.get('body', '{}')
    if event.get('isBase64Encoded') and body:
        body = base64.b64decode(body).decode('utf-8')
    return json.loads(body) if body else {}


def response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(body, ensure_ascii=False, default=str)
    }


def get_upload_html():
    """업로드 웹 UI HTML - 다중 파일/디렉토리 업로드 + Pre-signed URL 플로우"""
    return '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BOS-AI RAG Document Upload</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center}
.container{max-width:750px;width:100%;padding:2rem}
h1{font-size:1.5rem;margin-bottom:.5rem;color:#38bdf8}
.subtitle{color:#94a3b8;margin-bottom:1.5rem;font-size:.9rem}
.selector-row{display:flex;gap:1rem;margin-bottom:1.5rem}
.selector-group{flex:1}
.selector-group label{display:block;font-size:.8rem;color:#94a3b8;margin-bottom:.4rem}
.selector-group select{width:100%;padding:.6rem .8rem;background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:8px;font-size:.9rem;cursor:pointer}
.selector-group select:focus{outline:none;border-color:#38bdf8}
.drop-zone{border:2px dashed #334155;border-radius:12px;padding:2.5rem;text-align:center;cursor:pointer;transition:all .2s}
.drop-zone:hover,.drop-zone.dragover{border-color:#38bdf8;background:rgba(56,189,248,.05)}
.drop-zone.disabled{opacity:.4;cursor:not-allowed;pointer-events:none}
.drop-zone p{color:#94a3b8;margin-top:.5rem}
.drop-zone .icon{font-size:2.5rem;margin-bottom:.5rem}
input[type=file]{display:none}
.btn-row{display:flex;gap:.75rem;margin-top:1rem}
.btn{background:#38bdf8;color:#0f172a;border:none;padding:.75rem 1.5rem;border-radius:8px;font-weight:600;cursor:pointer;font-size:.9rem;transition:background .2s}
.btn:hover{background:#7dd3fc}
.btn:disabled{background:#334155;color:#64748b;cursor:not-allowed}
.btn-secondary{background:#334155;color:#e2e8f0}
.btn-secondary:hover{background:#475569}
.btn-secondary:disabled{background:#1e293b;color:#64748b;cursor:not-allowed}
.file-list{margin-top:1.5rem;max-height:400px;overflow-y:auto}
.file-item{background:#1e293b;border-radius:8px;padding:.75rem 1rem;margin-bottom:.5rem;display:flex;align-items:center;gap:.75rem}
.file-icon{font-size:1.3rem;flex-shrink:0;width:28px;text-align:center}
.file-info{flex:1;min-width:0}
.file-name{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.9rem}
.file-size{color:#64748b;font-size:.75rem}
.file-tag{display:inline-block;background:#334155;color:#94a3b8;font-size:.65rem;padding:.1rem .4rem;border-radius:4px;margin-top:.2rem}
.progress-bar{width:100%;height:5px;background:#334155;border-radius:3px;margin-top:.4rem;overflow:hidden}
.progress-fill{height:100%;background:#38bdf8;border-radius:3px;transition:width .3s;width:0}
.status{font-size:.7rem;margin-top:.2rem}
.status.uploading{color:#38bdf8}
.status.done{color:#4ade80}
.status.error{color:#f87171}
.status.extracting{color:#fbbf24}
.btn-remove{background:none;border:none;color:#64748b;cursor:pointer;font-size:1.1rem;padding:.2rem;flex-shrink:0}
.btn-remove:hover{color:#f87171}
.btn-delete{background:none;border:1px solid #475569;color:#94a3b8;border-radius:6px;padding:.3rem .6rem;cursor:pointer;font-size:.75rem}
.btn-delete:hover{border-color:#f87171;color:#f87171}
.overall-progress{margin-top:1rem;padding:.75rem 1rem;background:#1e293b;border-radius:8px;display:none}
.overall-progress .label{font-size:.85rem;color:#94a3b8;margin-bottom:.4rem}
.overall-progress .progress-bar{height:8px}
.overall-progress .progress-fill{background:#38bdf8}
.extraction-status{margin-top:.3rem;font-size:.7rem;display:flex;align-items:center;gap:.3rem}
.extraction-status .spinner{display:inline-block;width:10px;height:10px;border:2px solid #fbbf24;border-top-color:transparent;border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.doc-list{margin-top:2rem;border-top:1px solid #1e293b;padding-top:1.5rem}
.doc-list h2{font-size:1.1rem;color:#38bdf8;margin-bottom:1rem}
.filter-row{display:flex;gap:.75rem;margin-bottom:1rem}
.filter-row select{padding:.4rem .6rem;background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:6px;font-size:.8rem}
.doc-item{background:#1e293b;border-radius:8px;padding:.75rem 1rem;margin-bottom:.5rem;display:flex;justify-content:space-between;align-items:center}
.doc-item .name{font-size:.9rem}
.doc-item .meta{color:#64748b;font-size:.75rem;text-align:right}
.doc-item .tag{color:#38bdf8;font-size:.7rem}
.empty{color:#64748b;text-align:center;padding:1rem}
.toast{position:fixed;top:1rem;right:1rem;padding:1rem 1.5rem;border-radius:8px;font-size:.9rem;z-index:100;animation:slideIn .3s;max-width:350px}
.toast.success{background:#065f46;color:#4ade80}
.toast.error{background:#7f1d1d;color:#f87171}
.toast.warning{background:#78350f;color:#fbbf24}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
.warning-msg{color:#fbbf24;font-size:.8rem;margin-top:.5rem;padding:.5rem .75rem;background:rgba(251,191,36,.08);border-radius:6px;display:none}
</style>
</head>
<body>
<div class="container">
<h1>📄 BOS-AI RAG Document Upload</h1>
<p class="subtitle">파일을 업로드하면 Seoul S3 → Virginia S3 → Bedrock KB로 자동 임베딩됩니다</p>

<div class="selector-row">
  <div class="selector-group">
    <label>팀 (Team)</label>
    <select id="teamSelect" onchange="onTeamChange()">
      <option value="">-- 팀 선택 --</option>
    </select>
  </div>
  <div class="selector-group">
    <label>카테고리 (Category)</label>
    <select id="categorySelect" onchange="onCategoryChange()">
      <option value="">-- 카테고리 선택 --</option>
    </select>
  </div>
</div>

<div class="drop-zone disabled" id="dropZone">
  <div class="icon">📁</div>
  <p id="dropZoneText">팀과 카테고리를 먼저 선택하세요</p>
  <p style="font-size:.75rem;color:#475569">PDF, TXT, DOCX, CSV, HTML, MD 지원 · 파일 및 폴더 드래그 가능</p>
</div>
<input type="file" id="fileInput" multiple>
<input type="file" id="dirInput" webkitdirectory>

<div class="btn-row">
  <button class="btn" id="btnSelectFiles" disabled onclick="document.getElementById('fileInput').click()">📄 파일 선택</button>
  <button class="btn btn-secondary" id="btnSelectDir" disabled onclick="document.getElementById('dirInput').click()">📂 폴더 선택</button>
</div>

<div class="warning-msg" id="warningMsg"></div>

<div class="file-list" id="fileList"></div>

<div class="overall-progress" id="overallProgress">
  <div class="label" id="overallLabel">0/0 파일 완료</div>
  <div class="progress-bar"><div class="progress-fill" id="overallFill"></div></div>
</div>

<button class="btn" id="uploadBtn" disabled onclick="startUpload()" style="margin-top:1rem;width:100%">⬆ 업로드 시작</button>

<div class="doc-list">
  <h2>📋 업로드된 문서 목록</h2>
  <div class="filter-row">
    <select id="filterTeam" onchange="loadDocuments()">
      <option value="">전체 팀</option>
    </select>
    <select id="filterCategory" onchange="loadDocuments()">
      <option value="">전체 카테고리</option>
    </select>
  </div>
  <div id="docList"><div class="empty">로딩 중...</div></div>
</div>
</div>

<script>
/* === Constants === */
const API_BASE = window.location.pathname.replace(/\\/upload$/, '');
const ALLOWED_EXTENSIONS = ['pdf', 'txt', 'docx', 'csv', 'html', 'md', 'v', 'sv', 'vhd', 'vhdl', 'vh', 'svh', 'py', 'c', 'h', 'cpp', 'hpp', 'json', 'yaml', 'yml', 'xml', 'tcl', 'sdc', 'xdc'];
const MAX_FILE_SIZE = 100 * 1024 * 1024;
const ARCHIVE_EXTENSIONS = [];
const SYSTEM_FILES = ['__MACOSX', 'Thumbs.db', '.DS_Store'];
const FILE_ICONS = {pdf:'📕',txt:'📝',docx:'📘',csv:'📊',html:'🌐',md:'📓'};

let pendingFiles = [];
let teamsData = {};
let selectedTeam = '';
let selectedCategory = '';
let isUploading = false;

/* === File Validation (Task 6.3) === */
function getFileExtension(filename) {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.tar.gz')) return 'tar.gz';
  const parts = lower.split('.');
  return parts.length > 1 ? parts[parts.length - 1] : '';
}

function isArchive(filename) {
  return ARCHIVE_EXTENSIONS.includes(getFileExtension(filename));
}

function validateFile(file) {
  const name = file._relativePath || file.name;
  const ext = getFileExtension(name);
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return {valid: false, reason: '지원하지 않는 형식: .' + (ext || '(없음)')};
  }
  if (isArchive(name)) {
    if (file.size > MAX_ARCHIVE_SIZE) {
      return {valid: false, reason: '압축 파일 크기 제한 초과 (최대 500MB)'};
    }
  } else {
    if (file.size > MAX_FILE_SIZE) {
      return {valid: false, reason: '파일 크기 제한 초과 (최대 100MB)'};
    }
  }
  return {valid: true, reason: ''};
}

function getFileIcon(filename) {
  const ext = getFileExtension(filename);
  return FILE_ICONS[ext] || '📄';
}

/* === Directory Traversal (Task 6.2) === */
function getFile(entry) {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

async function readAllEntries(reader) {
  const all = [];
  let batch;
  do {
    batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
    all.push(...batch);
  } while (batch.length > 0);
  return all;
}

async function traverseDirectory(entry, path) {
  path = path || '';
  const results = [];
  if (entry.isFile) {
    const baseName = entry.name;
    if (baseName.startsWith('.')) return results;
    if (SYSTEM_FILES.includes(baseName)) return results;
    try {
      const file = await getFile(entry);
      Object.defineProperty(file, '_relativePath', {value: path + baseName, writable: true});
      results.push(file);
    } catch(e) { /* skip unreadable */ }
  } else if (entry.isDirectory) {
    if (entry.name.startsWith('.') || SYSTEM_FILES.includes(entry.name)) return results;
    const reader = entry.createReader();
    const entries = await readAllEntries(reader);
    for (const child of entries) {
      const sub = await traverseDirectory(child, path + entry.name + '/');
      results.push(...sub);
    }
  }
  return results;
}

/* === File Queue Management (Task 6.4) === */
function addFiles(fileList) {
  const warnings = [];
  const arr = Array.isArray(fileList) ? fileList : Array.from(fileList);
  for (const f of arr) {
    const displayName = f._relativePath || f.name;
    const validation = validateFile(f);
    if (!validation.valid) {
      warnings.push(displayName + ': ' + validation.reason);
      continue;
    }
    const key = displayName;
    if (!pendingFiles.find(p => (p._relativePath || p.name) === key)) {
      pendingFiles.push(f);
    }
  }
  if (warnings.length > 0) {
    showWarning(warnings.join('\\n'));
  }
  renderFileList();
}

function removeFile(idx) {
  pendingFiles.splice(idx, 1);
  renderFileList();
}

function showWarning(msg) {
  const el = document.getElementById('warningMsg');
  el.textContent = msg;
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 5000);
}

/* === Team/Category Selection === */
async function loadCategories() {
  try {
    const resp = await fetch(API_BASE + '/categories');
    const data = await resp.json();
    teamsData = data.teams;
  } catch(e) {
    teamsData = {soc:{name:'SoC',categories:['code','spec']}};
  }
  const teamSel = document.getElementById('teamSelect');
  const filterTeam = document.getElementById('filterTeam');
  for (const [key, info] of Object.entries(teamsData)) {
    teamSel.add(new Option(info.name, key));
    filterTeam.add(new Option(info.name, key));
  }
}

function onTeamChange() {
  selectedTeam = document.getElementById('teamSelect').value;
  const catSel = document.getElementById('categorySelect');
  catSel.innerHTML = '<option value="">-- 카테고리 선택 --</option>';
  selectedCategory = '';
  if (selectedTeam && teamsData[selectedTeam]) {
    for (const c of teamsData[selectedTeam].categories) {
      catSel.add(new Option(c, c));
    }
  }
  updateDropZone();
}

function onCategoryChange() {
  selectedCategory = document.getElementById('categorySelect').value;
  updateDropZone();
}

function updateDropZone() {
  const dz = document.getElementById('dropZone');
  const enabled = selectedTeam && selectedCategory;
  if (enabled) {
    dz.classList.remove('disabled');
    document.getElementById('dropZoneText').textContent = '파일 또는 폴더를 드래그하거나 아래 버튼으로 선택';
  } else {
    dz.classList.add('disabled');
    document.getElementById('dropZoneText').textContent = '팀과 카테고리를 먼저 선택하세요';
  }
  document.getElementById('btnSelectFiles').disabled = !enabled;
  document.getElementById('btnSelectDir').disabled = !enabled;
}

/* === Drop Zone & File Input Events (Task 6.1) === */
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const dirInput = document.getElementById('dirInput');

dropZone.addEventListener('click', () => {
  if (selectedTeam && selectedCategory && !isUploading) fileInput.click();
});
dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  if (selectedTeam && selectedCategory) dropZone.classList.add('dragover');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', async e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  if (!selectedTeam || !selectedCategory || isUploading) return;
  const items = e.dataTransfer.items;
  if (!items) { addFiles(e.dataTransfer.files); return; }
  const collected = [];
  const promises = [];
  for (let i = 0; i < items.length; i++) {
    const entry = items[i].webkitGetAsEntry && items[i].webkitGetAsEntry();
    if (entry) {
      promises.push(traverseDirectory(entry, ''));
    }
  }
  const results = await Promise.all(promises);
  for (const r of results) collected.push(...r);
  if (collected.length > 0) addFiles(collected);
});

fileInput.addEventListener('change', e => {
  if (e.target.files.length > 0) addFiles(e.target.files);
  e.target.value = '';
});
dirInput.addEventListener('change', e => {
  if (e.target.files.length > 0) {
    const files = Array.from(e.target.files).filter(f => {
      const path = f.webkitRelativePath || f.name;
      const parts = path.split('/');
      for (const p of parts) {
        if (p.startsWith('.') || SYSTEM_FILES.includes(p)) return false;
      }
      return true;
    }).map(f => {
      const rel = f.webkitRelativePath || f.name;
      Object.defineProperty(f, '_relativePath', {value: rel, writable: true});
      return f;
    });
    addFiles(files);
  }
  e.target.value = '';
});

/* === Render File List === */
function renderFileList() {
  const el = document.getElementById('fileList');
  document.getElementById('uploadBtn').disabled = pendingFiles.length === 0 || isUploading;
  if (pendingFiles.length === 0) { el.innerHTML = ''; return; }
  el.innerHTML = pendingFiles.map((f, i) => {
    const name = f._relativePath || f.name;
    const icon = getFileIcon(name);
    return '<div class="file-item" id="file-' + i + '">' +
      '<div class="file-icon">' + icon + '</div>' +
      '<div class="file-info">' +
        '<div class="file-name" title="' + name + '">' + name + '</div>' +
        '<div class="file-size">' + formatSize(f.size) + (isArchive(name) ? ' (압축)' : '') + '</div>' +
        '<div class="file-tag">' + selectedTeam + '/' + selectedCategory + '</div>' +
        '<div class="progress-bar"><div class="progress-fill" id="prog-' + i + '"></div></div>' +
        '<div class="status" id="status-' + i + '"></div>' +
      '</div>' +
      '<button class="btn-remove" onclick="removeFile(' + i + ')" id="rm-' + i + '">✕</button>' +
    '</div>';
  }).join('');
}

/* === Pre-signed URL Upload (Task 7.1) === */
async function uploadFilePresigned(file, idx, isLast) {
  const statusEl = document.getElementById('status-' + idx);
  const progEl = document.getElementById('prog-' + idx);
  const displayName = file._relativePath || file.name;

  statusEl.className = 'status uploading';
  statusEl.textContent = 'Pre-signed URL 요청 중...';

  /* Step 1: Get pre-signed URL */
  let presignData;
  try {
    presignData = await apiPost('/documents/presign', {
      filename: displayName.split('/').pop(),
      team: selectedTeam,
      category: selectedCategory,
      content_type: file.type || 'application/octet-stream'
    });
  } catch(e) {
    throw new Error('Presign 실패: ' + e.message);
  }

  /* Step 2: PUT to S3 via XMLHttpRequest for progress */
  statusEl.textContent = '업로드 중...';
  const putToS3 = (url) => new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url, true);
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        progEl.style.width = pct + '%';
        statusEl.textContent = '업로드 중... ' + pct + '%';
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr);
      else reject(new Error('S3 PUT 실패: HTTP ' + xhr.status));
    };
    xhr.onerror = () => reject(new Error('네트워크 오류'));
    xhr.send(file);
  });

  try {
    await putToS3(presignData.presigned_url);
  } catch(e) {
    /* Retry on 403 (expired pre-signed URL) */
    if (e.message && e.message.includes('403')) {
      statusEl.textContent = 'URL 만료, 재요청 중...';
      presignData = await apiPost('/documents/presign', {
        filename: displayName.split('/').pop(),
        team: selectedTeam,
        category: selectedCategory,
        content_type: file.type || 'application/octet-stream'
      });
      await putToS3(presignData.presigned_url);
    } else {
      throw e;
    }
  }

  /* Step 3: Confirm upload */
  statusEl.textContent = '업로드 확인 중...';
  const archiveFile = isArchive(displayName);
  const confirmResp = await apiPost('/documents/confirm', {
    s3_key: presignData.s3_key,
    filename: displayName.split('/').pop(),
    team: selectedTeam,
    category: selectedCategory,
    skip_sync: !isLast || archiveFile,
    is_archive: archiveFile
  });

  /* Step 4: If archive, trigger extraction */
  if (isArchive(displayName)) {
    statusEl.textContent = '압축 해제 요청 중...';
    const extractResp = await apiPost('/documents/extract', {
      s3_key: presignData.s3_key,
      team: selectedTeam,
      category: selectedCategory
    });
    statusEl.className = 'status extracting';
    statusEl.innerHTML = '<span class="extraction-status"><span class="spinner"></span> 압축 해제 중 (task: ' + extractResp.task_id + ')</span>';
    startPolling(extractResp.task_id, idx);
  } else {
    progEl.style.width = '100%';
    progEl.style.background = '#4ade80';
    statusEl.className = 'status done';
    statusEl.textContent = '\\u2713 완료' + (confirmResp.kb_sync ? ' (KB sync: ' + confirmResp.kb_sync + ')' : '');
  }
}

/* === Upload Orchestration (Task 7.2) === */
async function startUpload() {
  if (pendingFiles.length === 0 || isUploading) return;
  isUploading = true;
  document.getElementById('uploadBtn').disabled = true;
  document.querySelectorAll('.btn-remove').forEach(b => b.style.display = 'none');
  document.getElementById('teamSelect').disabled = true;
  document.getElementById('categorySelect').disabled = true;
  document.getElementById('btnSelectFiles').disabled = true;
  document.getElementById('btnSelectDir').disabled = true;

  const overallEl = document.getElementById('overallProgress');
  overallEl.style.display = 'block';
  const total = pendingFiles.length;
  let successCount = 0;
  let failCount = 0;

  for (let i = 0; i < total; i++) {
    const isLast = (i === total - 1);
    document.getElementById('overallLabel').textContent = (successCount + failCount) + '/' + total + ' 파일 완료';
    document.getElementById('overallFill').style.width = Math.round(((successCount + failCount) / total) * 100) + '%';
    try {
      await uploadFilePresigned(pendingFiles[i], i, isLast);
      successCount++;
    } catch(e) {
      failCount++;
      const statusEl = document.getElementById('status-' + i);
      const progEl = document.getElementById('prog-' + i);
      if (statusEl) {
        statusEl.className = 'status error';
        statusEl.textContent = '\\u2717 오류: ' + e.message;
      }
      if (progEl) progEl.style.background = '#f87171';
    }
  }

  /* Final overall progress */
  document.getElementById('overallLabel').textContent = total + '/' + total + ' 파일 완료';
  document.getElementById('overallFill').style.width = '100%';

  /* Summary toast */
  if (failCount === 0) {
    toast('모든 파일 업로드 완료 (' + successCount + '개 성공)', 'success');
  } else {
    toast('업로드 완료: ' + successCount + '개 성공, ' + failCount + '개 실패', failCount === total ? 'error' : 'warning');
  }

  /* Reset UI state */
  isUploading = false;
  pendingFiles = [];
  document.getElementById('teamSelect').disabled = false;
  document.getElementById('categorySelect').disabled = false;
  updateDropZone();
  setTimeout(() => {
    renderFileList();
    overallEl.style.display = 'none';
    loadDocuments();
  }, 2000);
}

/* === Extraction Status Polling (Task 7.3) === */
function startPolling(taskId, fileIdx) {
  let attempts = 0;
  const interval = setInterval(async () => {
    attempts++;
    if (attempts > 60) {
      clearInterval(interval);
      const statusEl = document.getElementById('status-' + fileIdx);
      if (statusEl) {
        statusEl.className = 'status error';
        statusEl.textContent = '\\u2717 압축 해제 상태 확인 시간 초과';
      }
      return;
    }
    try {
      const resp = await fetch(API_BASE + '/documents/extract-status?task_id=' + encodeURIComponent(taskId));
      if (!resp.ok) return;
      const data = await resp.json();
      const statusEl = document.getElementById('status-' + fileIdx);
      if (!statusEl) { clearInterval(interval); return; }

      if (data.status === '완료') {
        clearInterval(interval);
        const r = data.results || {};
        statusEl.className = 'status done';
        statusEl.textContent = '\\u2713 압축 해제 완료 (성공: ' + (r.success_count || 0) + ', 건너뜀: ' + (r.skipped_count || 0) + ')';
        const progEl = document.getElementById('prog-' + fileIdx);
        if (progEl) { progEl.style.width = '100%'; progEl.style.background = '#4ade80'; }
        loadDocuments();
      } else if (data.status === '실패') {
        clearInterval(interval);
        statusEl.className = 'status error';
        statusEl.textContent = '\\u2717 압축 해제 실패: ' + (data.error_message || '알 수 없는 오류');
        const progEl = document.getElementById('prog-' + fileIdx);
        if (progEl) progEl.style.background = '#f87171';
      } else if (data.status === '처리중') {
        statusEl.innerHTML = '<span class="extraction-status"><span class="spinner"></span> 압축 해제 처리중...</span>';
      }
    } catch(e) {
      /* Network error during polling - keep trying */
    }
  }, 5000);
}

/* === API Helper === */
async function apiPost(path, body) {
  const resp = await fetch(API_BASE + path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || 'Request failed');
  return data;
}

/* === Utilities === */
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
  return (bytes / 1073741824).toFixed(1) + ' GB';
}

function toast(msg, type) {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

/* === Document List (Task 7.4) === */
async function loadDocuments() {
  try {
    const ft = document.getElementById('filterTeam').value;
    const fc = document.getElementById('filterCategory').value;
    const params = new URLSearchParams();
    if (ft) params.set('team', ft);
    if (fc) params.set('category', fc);
    const qs = params.toString();
    const resp = await fetch(API_BASE + '/documents' + (qs ? '?' + qs : ''));
    const data = await resp.json();
    const el = document.getElementById('docList');
    if (!data.files || data.files.length === 0) {
      el.innerHTML = '<div class="empty">업로드된 문서가 없습니다</div>';
      return;
    }
    el.innerHTML = data.files.map(f => {
      var safeKey = f.key.replace(/&/g,"&amp;").replace(/"/g,"&quot;");
      return '<div class="doc-item"><div>' +
        '<span class="name">' + f.filename + '</span>' +
        '<div class="tag">' + f.team + '/' + f.category + '</div>' +
        '</div><div style="display:flex;align-items:center;gap:.75rem">' +
        '<span class="meta">' + formatSize(f.size) + '<br>' +
        new Date(f.last_modified).toLocaleString("ko-KR") + '</span>' +
        '<button class="btn-delete" data-key="' + safeKey + '" onclick="deleteDocument(this.dataset.key)">🗑 삭제</button>' +
        '</div></div>';
    }).join('');
  } catch (err) {
    document.getElementById('docList').innerHTML = '<div class="empty">목록 조회 실패</div>';
  }
}

/* === Delete Document === */
async function deleteDocument(s3Key) {
  if (!confirm('정말 삭제하시겠습니까?\\n' + s3Key)) return;
  try {
    await apiPost('/documents/delete', { s3_key: s3Key });
    toast('삭제 완료', 'success');
    loadDocuments();
  } catch(e) {
    toast('삭제 실패: ' + e.message, 'error');
  }
}

/* === Init === */
loadCategories().then(() => loadDocuments());
</script>
</body>
</html>'''
