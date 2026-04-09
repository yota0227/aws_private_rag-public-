"""
BOS-AI RAG Document Processor Lambda Handler
Seoul Private RAG VPC → Virginia Backend (Bedrock, OpenSearch) via VPC Peering

Endpoints:
  GET  /rag/upload                  - 웹 업로드 UI 서빙
  POST /rag/documents/initiate      - S3 multipart upload 시작
  POST /rag/documents/upload-part   - chunk 업로드
  POST /rag/documents/complete      - multipart upload 완료 + KB sync
  GET  /rag/documents               - 업로드된 파일 목록
  POST /rag/query                   - RAG 질의 (Verification Pipeline 우선)
  GET  /rag/health                  - 헬스체크
  POST /rag/claims                  - Claim 생성
  POST /rag/claims/update-status    - Claim 상태 전이
  POST /rag/claims/approve          - Claim 승인 (Human Review Gate)
  POST /rag/claims/reject           - Claim 거부 (Human Review Gate)
  POST /rag/search-archive          - Archive 문서 검색 (Bedrock KB + 필터)
  POST /rag/get-evidence            - Claim evidence 조회
  POST /rag/list-verified-claims    - 검증된 Claim 목록 조회
  POST /rag/generate-hdd            - HDD 섹션 자동 생성
  POST /rag/publish-markdown        - 마크다운 출판
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
import hashlib
import random
import re
import boto3
from datetime import datetime
from decimal import Decimal

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
CLAIM_DB_TABLE = os.environ.get('CLAIM_DB_TABLE', 'bos-ai-claim-db-prod')
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
lambda_client = boto3.client('lambda', region_name='ap-northeast-2')
ALLOWED_EXTENSIONS = ['pdf', 'txt', 'docx', 'csv', 'html', 'md', 'v', 'sv', 'vhd', 'vhdl', 'vh', 'svh', 'py', 'c', 'h', 'cpp', 'hpp', 'json', 'yaml', 'yml', 'xml', 'tcl', 'sdc', 'xdc']
ARCHIVE_EXTENSIONS = ['zip', 'tar.gz']
SYSTEM_FILES = ['__MACOSX', 'Thumbs.db', '.DS_Store']

# Claim 상태 전이 규칙 (Requirements 5.2)
ALLOWED_TRANSITIONS = {
    "draft":      ["verified", "deprecated"],
    "verified":   ["conflicted", "deprecated"],
    "conflicted": ["verified", "deprecated"],
    "deprecated": []
}

# 문서 source 허용 값 (Requirements 6.5)
VALID_SOURCES = {"archive_md", "rtl_parsed", "codebeamer", "manual_upload", "system_generated"}


def handler(event, context):
    """Main Lambda handler for Private RAG API Gateway"""
    # 비동기 Lambda Event Invocation 처리
    if event.get('action') == 'process_extraction':
        return process_extraction(event)
    if event.get('action') == 'backfill_metadata':
        return backfill_metadata(event, context)
    if event.get('action') == 'ingest_claims':
        return ingest_claims(event, context)
    if event.get('action') == 'cross_check_claims':
        return cross_check_claims(event, context)


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

        # Claim CRUD 엔드포인트 (Phase 2)
        if '/claims/update-status' in path and method == 'POST':
            return update_claim_status(event)

        # Human Review Gate 엔드포인트 (Phase 4)
        if '/claims/approve' in path and method == 'POST':
            return approve_claim(event)
        if '/claims/reject' in path and method == 'POST':
            return reject_claim(event)

        if '/claims' in path and method == 'POST' and '/claims/' not in path:
            return create_claim(event)

        # HDD 생성 및 마크다운 출판 엔드포인트 (Phase 4)
        if '/generate-hdd' in path and method == 'POST':
            return generate_hdd_section(event)
        if '/publish-markdown' in path and method == 'POST':
            return publish_markdown(event)

        # MCP Tool 엔드포인트 (Phase 3)
        if '/search-archive' in path and method == 'POST':
            return search_archive(event)
        if '/get-evidence' in path and method == 'POST':
            return get_evidence(event)
        if '/list-verified-claims' in path and method == 'POST':
            return list_verified_claims(event)

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
    topic = body.get('topic', '')
    variant = body.get('variant', 'default')
    doc_version = body.get('doc_version', '1.0')
    source = body.get('source', 'manual_upload')

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
                                 version=version, source_system=source_system,
                                 topic=topic, variant=variant, doc_version=doc_version,
                                 source=source)
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
    """RAG 질의 처리 — Verification Pipeline 우선 실행, 폴백 시 Bedrock KB 검색
    Requirements: 9.1, 9.7
    """
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

    variant = body.get('variant', None)

    # Verification Pipeline 우선 실행 (Task 5.4)
    try:
        pipeline_result = verification_pipeline(query, variant=variant)
        response_time_ms = int((time.time() - start_time) * 1000)

        # 구조화 로그
        logger.info(json.dumps({
            'event': 'rag_query',
            'query_length': len(query),
            'response_time_ms': response_time_ms,
            'verification_pipeline': True,
            'fallback': pipeline_result.get('verification_metadata', {}).get('fallback', False),
            'claims_used': len(pipeline_result.get('verification_metadata', {}).get('claims_used', []))
        }))

        if response_time_ms > 30000:
            logger.warning(json.dumps({'event': 'slow_query', 'response_time_ms': response_time_ms, 'query_length': len(query)}))

        result = {
            'answer': pipeline_result.get('answer', ''),
            'citations': pipeline_result.get('citations', []),
            'verification_metadata': pipeline_result.get('verification_metadata', {}),
            'metadata': {
                'search_type': 'verification_pipeline',
                'query_length': len(query),
                'response_time_ms': response_time_ms
            }
        }

        return response(200, result)

    except Exception as e:
        logger.error(f"Verification Pipeline failed, falling back to direct Bedrock KB: {e}")
        return _handle_query_bedrock_kb(query, start_time, body)


def _handle_query_bedrock_kb(query, start_time, body):
    """기존 Bedrock KB 직접 검색 (Verification Pipeline 실패 시 폴백)"""
    search_type = os.environ.get('SEARCH_TYPE', 'HYBRID')
    results_count = int(os.environ.get('SEARCH_RESULTS_COUNT', '5'))

    filter_obj = body.get('filter', None)
    bedrock_filter = build_bedrock_filter(filter_obj) if filter_obj else None

    try:
        bedrock_runtime = boto3.client('bedrock-agent-runtime', region_name=BACKEND_REGION)

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

        logger.info(json.dumps({
            'event': 'rag_query', 'query_length': len(query), 'search_type': search_type,
            'citation_count': citation_count, 'response_time_ms': response_time_ms,
            'has_filter': bedrock_filter is not None, 'verification_pipeline': False
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


def create_metadata_file(s3_key, team='', category='', version='1.0', source_system='manual_upload',
                         bucket=None, topic='', variant='default', doc_version='1.0', source='manual_upload'):
    """S3 객체에 대한 .metadata.json 사이드카 파일 생성 (Bedrock KB 메타데이터 필터링 형식)
    Requirements 6.1, 6.2, 6.5: topic/variant/doc_version/source 필드 지원
    """
    if bucket is None:
        bucket = S3_BUCKET_SEOUL

    ext = s3_key.rsplit('.', 1)[-1].lower() if '.' in s3_key else ''
    document_type = DOCUMENT_TYPE_MAP.get(ext, 'other')

    # source 허용 값 검증 (Requirements 6.5)
    if source and source not in VALID_SOURCES:
        source = 'manual_upload'

    # topic 자동 추출 (Requirements 6.6) — topic이 비어있으면 파일 경로에서 유추
    if not topic:
        topic = extract_topic_from_path(s3_key)

    metadata = {
        'metadataAttributes': {
            'team': team or '',
            'category': category or '',
            'document_type': document_type,
            'upload_date': datetime.utcnow().isoformat() + 'Z',
            'version': version or '1.0',
            'source_system': source_system or 'manual_upload',
            'topic': topic or '',
            'variant': variant or 'default',
            'doc_version': doc_version or '1.0',
            'source': source or 'manual_upload'
        }
    }

    metadata_key = s3_key + '.metadata.json'

    # 동일 topic+variant에 새 doc_version 업로드 시 이전 버전 superseded_by 설정 (Requirements 6.3)
    if topic and variant:
        _update_superseded_metadata(bucket, topic, variant, s3_key, metadata_key)

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


# ============================================================================
# Document Ingestion 분리 — Topic/Variant/Version 유틸리티 (Task 3.9)
# Requirements: 6.1, 6.2, 6.3, 6.5, 6.6
# ============================================================================

def extract_topic_from_path(s3_key):
    """파일 경로에서 topic 자동 추출 (Requirements 6.6)
    예: documents/soc/ucie/phy_spec.md → ucie/phy
    """
    path = s3_key.replace(S3_PREFIX, '', 1) if s3_key.startswith(S3_PREFIX) else s3_key
    parts = path.split('/')
    if len(parts) < 3:
        return ''
    # parts[0]=team, parts[1]=category, parts[2:]=filename or subdirs
    # 파일명에서 확장자 제거 후 topic 구성
    sub_parts = parts[1:-1]  # category ~ 마지막 디렉토리 (파일명 제외)
    filename = parts[-1]
    name_no_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
    # 파일명에서 _spec, _doc 등 접미사 제거하여 topic 추출
    name_clean = re.sub(r'[_-](spec|doc|guide|manual|readme|overview)$', '', name_no_ext, flags=re.IGNORECASE)
    if sub_parts:
        return '/'.join(sub_parts) + '/' + name_clean if name_clean else '/'.join(sub_parts)
    return name_clean


def _update_superseded_metadata(bucket, topic, variant, new_s3_key, new_metadata_key):
    """동일 topic+variant의 이전 버전 메타데이터에 superseded_by 추가 (Requirements 6.3)"""
    try:
        prefix = S3_PREFIX
        resp = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=500)
        for obj in resp.get('Contents', []):
            key = obj['Key']
            if not key.endswith('.metadata.json') or key == new_metadata_key:
                continue
            try:
                meta_resp = s3_client.get_object(Bucket=bucket, Key=key)
                meta_content = json.loads(meta_resp['Body'].read().decode('utf-8'))
                attrs = meta_content.get('metadataAttributes', {})
                if attrs.get('topic') == topic and attrs.get('variant') == variant and 'superseded_by' not in attrs:
                    attrs['superseded_by'] = new_s3_key
                    s3_client.put_object(
                        Bucket=bucket, Key=key,
                        Body=json.dumps(meta_content, ensure_ascii=False).encode('utf-8'),
                        ContentType='application/json'
                    )
                    logger.info(f"Superseded metadata updated: {key} → {new_s3_key}")
            except Exception as e:
                logger.warning(f"Failed to check/update superseded metadata {key}: {e}")
    except Exception as e:
        logger.warning(f"Superseded metadata scan failed: {e}")


# ============================================================================
# Claim CRUD 함수 (Task 3.3)
# Requirements: 5.1~5.10, 14.1, 14.2
# ============================================================================

def _exponential_backoff_jitter(attempt):
    """Exponential Backoff with Full Jitter (base=100ms, max=2s)
    Design: sleep(min(2s, 100ms * 2^attempt * random(0,1)))
    """
    base_ms = 100
    max_ms = 2000
    sleep_ms = min(max_ms, base_ms * (2 ** attempt) * random.random())
    time.sleep(sleep_ms / 1000.0)


def _validate_claim_fields(body):
    """Claim 필드 유효성 검증 (Requirements 5.1, 5.6, 5.7)"""

    # evidence 최소 1개 (Requirements 5.1)
    evidence = body.get('evidence', [])
    if not evidence or not isinstance(evidence, list) or len(evidence) < 1:
        return response(400, {'error': 'evidence array must contain at least 1 item'})

    # confidence 0.0~1.0 (Requirements 5.6)
    confidence = body.get('confidence')
    if confidence is None or not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
        return response(400, {'error': 'confidence must be between 0.0 and 1.0'})

    # topic 계층적 형식 (Requirements 5.7)
    topic = body.get('topic', '')
    if not topic or '/' not in topic:
        return response(400, {'error': 'topic must be non-empty hierarchical format (slash-separated, e.g. ucie/phy/ltssm)'})

    # statement 10~500자
    statement = body.get('statement', '')
    if len(statement) < 10 or len(statement) > 500:
        return response(400, {'error': 'statement must be 10-500 characters'})

    # evidence 각 항목의 source_chunk 10~1000자, chunk_hash SHA-256
    for i, ev in enumerate(evidence):
        source_chunk = ev.get('source_chunk', '')
        if len(source_chunk) < 10 or len(source_chunk) > 1000:
            return response(400, {'error': f'evidence[{i}].source_chunk must be 10-1000 characters'})

    return None  # 검증 통과


def create_claim(event):
    """POST /rag/claims — 새 claim 생성
    Requirements: 5.1~5.7, 5.9
    """
    body = parse_body(event)

    # 필드 유효성 검증
    validation_error = _validate_claim_fields(body)
    if validation_error:
        return validation_error

    claim_id = str(uuid.uuid4())
    claim_family_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + 'Z'

    # evidence에 chunk_hash 자동 생성 (SHA-256)
    evidence = body.get('evidence', [])
    for ev in evidence:
        if not ev.get('chunk_hash'):
            ev['chunk_hash'] = hashlib.sha256(ev.get('source_chunk', '').encode('utf-8')).hexdigest()
        if not ev.get('extraction_date'):
            ev['extraction_date'] = now

    topic = body['topic']
    variant = body.get('variant', 'default')

    item = {
        'claim_id': claim_id,
        'version': 1,
        'topic': topic,
        'statement': body['statement'],
        'evidence': evidence,
        'confidence': Decimal(str(body['confidence'])),
        'status': 'draft',
        'variant': variant,
        'topic_variant': f"{topic}#{variant}",
        'claim_family_id': claim_family_id,
        'is_latest': True,
        'derived_from': body.get('derived_from', []),
        'created_at': now,
        'last_verified_at': now,
        'created_by': body.get('created_by', 'api:create_claim'),
        'approval_status': 'not_applicable'
    }

    # Optimistic locking: attribute_not_exists(claim_id) (Requirements 5.9)
    table = dynamodb.Table(CLAIM_DB_TABLE)
    try:
        table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(claim_id)'
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return response(409, {'error': 'claim_id already exists (duplicate)'})

    # Contradiction score 계산 (Requirements 5.5)
    _check_contradiction(table, topic, body['statement'], claim_id)

    logger.info(json.dumps({'event': 'claim_created', 'claim_id': claim_id, 'topic': topic, 'status': 'draft'}))
    return response(201, {
        'claim_id': claim_id,
        'version': 1,
        'status': 'draft',
        'claim_family_id': claim_family_id
    })


def _check_contradiction(table, topic, new_statement, new_claim_id):
    """동일 topic verified claim과 contradiction_score 계산 (Requirements 5.5)
    score >= 0.7 시 기존 claim status → conflicted, 새 claim derived_from에 기록
    """
    try:
        resp = table.query(
            IndexName='topic-index',
            KeyConditionExpression='topic = :t',
            FilterExpression='#s = :v AND is_latest = :il',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':t': topic, ':v': 'verified', ':il': True}
        )
        existing_claims = resp.get('Items', [])
        if not existing_claims:
            return

        # 간단한 문자열 유사도 기반 contradiction score 계산
        # 실제 프로덕션에서는 LLM 기반 비교로 교체
        for claim in existing_claims:
            existing_statement = claim.get('statement', '')
            score = _calculate_contradiction_score(new_statement, existing_statement)
            if score >= 0.7:
                # 기존 claim을 conflicted로 변경
                try:
                    table.update_item(
                        Key={'claim_id': claim['claim_id'], 'version': claim['version']},
                        UpdateExpression='SET #s = :cs',
                        ExpressionAttributeNames={'#s': 'status'},
                        ExpressionAttributeValues={':cs': 'conflicted'}
                    )
                    # 새 claim의 derived_from에 충돌 claim_id 기록
                    table.update_item(
                        Key={'claim_id': new_claim_id, 'version': 1},
                        UpdateExpression='SET derived_from = list_append(derived_from, :df)',
                        ExpressionAttributeValues={':df': [claim['claim_id']]}
                    )
                    logger.warning(json.dumps({
                        'event': 'contradiction_detected',
                        'new_claim_id': new_claim_id,
                        'conflicted_claim_id': claim['claim_id'],
                        'contradiction_score': score
                    }))
                except Exception as e:
                    logger.error(f"Failed to update contradiction: {e}")
    except Exception as e:
        logger.error(f"Contradiction check failed: {e}")


def _calculate_contradiction_score(statement_a, statement_b):
    """두 statement 간 contradiction score 계산 (0.0~1.0)
    간단한 토큰 겹침 기반 — 프로덕션에서는 LLM 기반 비교로 교체
    """
    tokens_a = set(statement_a.lower().split())
    tokens_b = set(statement_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union) if union else 0.0
    # 높은 유사도 = 잠재적 모순 (동일 주제에 대한 다른 주장)
    return jaccard


def update_claim_status(event):
    """POST /rag/claims/update-status — claim 상태 전이
    Requirements: 5.2, 5.3, 5.8, 5.9, 5.10, 14.1
    """
    body = parse_body(event)
    claim_id = body.get('claim_id', '')
    new_status = body.get('new_status', '')
    expected_version = body.get('expected_version')

    if not claim_id or not new_status:
        return response(400, {'error': 'claim_id and new_status are required'})
    if expected_version is None:
        return response(400, {'error': 'expected_version is required for optimistic locking'})

    table = dynamodb.Table(CLAIM_DB_TABLE)

    # 최대 3회 재시도 (Requirements 5.10)
    for attempt in range(3):
        try:
            # 현재 claim 조회
            result = table.get_item(Key={'claim_id': claim_id, 'version': int(expected_version)})
            item = result.get('Item')
            if not item:
                return response(404, {'error': 'claim not found', 'claim_id': claim_id, 'version': expected_version})

            current_status = item.get('status', '')

            # 상태 전이 검증 (Requirements 5.2, 5.3)
            allowed = ALLOWED_TRANSITIONS.get(current_status, [])
            if new_status not in allowed:
                return response(409, {
                    'error': f'transition from {current_status} to {new_status} not allowed',
                    'current_status': current_status,
                    'allowed_transitions': allowed
                })

            # 업데이트 표현식 구성
            now = datetime.utcnow().isoformat() + 'Z'
            update_expr = 'SET #s = :ns, last_verified_at = :now, version = version + :one'
            expr_names = {'#s': 'status'}
            expr_values = {':ns': new_status, ':now': now, ':one': 1, ':ev': int(expected_version)}

            # verified 전이 시 approval_status = pending_review (Requirements 14.1)
            if new_status == 'verified':
                update_expr += ', approval_status = :as, last_verified_at = :now'
                expr_values[':as'] = 'pending_review'

            # Optimistic locking (Requirements 5.9)
            table.update_item(
                Key={'claim_id': claim_id, 'version': int(expected_version)},
                UpdateExpression=update_expr,
                ConditionExpression='version = :ev',
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values
            )

            # deprecated 전이 시 하위 claim cascading (Requirements 5.8)
            if new_status == 'deprecated':
                _cascade_deprecated(table, claim_id)

            logger.info(json.dumps({
                'event': 'claim_status_updated', 'claim_id': claim_id,
                'from': current_status, 'to': new_status, 'version': int(expected_version) + 1
            }))
            return response(200, {
                'claim_id': claim_id,
                'status': new_status,
                'version': int(expected_version) + 1
            })

        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            if attempt < 2:
                logger.warning(f"Optimistic lock conflict for {claim_id}, retry {attempt + 1}/3")
                _exponential_backoff_jitter(attempt)
                # 최신 버전 다시 읽기
                try:
                    scan_resp = table.query(
                        KeyConditionExpression='claim_id = :cid',
                        ExpressionAttributeValues={':cid': claim_id},
                        ScanIndexForward=False, Limit=1
                    )
                    if scan_resp.get('Items'):
                        expected_version = scan_resp['Items'][0]['version']
                except Exception:
                    pass
                continue
            else:
                logger.error(f"Optimistic lock failed after 3 retries: {claim_id}")
                return response(409, {'error': 'version conflict after 3 retries', 'claim_id': claim_id})

    return response(500, {'error': 'unexpected error in update_claim_status'})


def _cascade_deprecated(table, deprecated_claim_id):
    """deprecated 전이 시 하위 claim status → conflicted (Requirements 5.8)"""
    try:
        # derived_from에 deprecated_claim_id를 포함하는 claim 검색
        scan_resp = table.scan(
            FilterExpression='contains(derived_from, :cid) AND #s <> :dep',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':cid': deprecated_claim_id, ':dep': 'deprecated'}
        )
        for item in scan_resp.get('Items', []):
            try:
                table.update_item(
                    Key={'claim_id': item['claim_id'], 'version': item['version']},
                    UpdateExpression='SET #s = :cs',
                    ExpressionAttributeNames={'#s': 'status'},
                    ExpressionAttributeValues={':cs': 'conflicted'}
                )
                logger.warning(json.dumps({
                    'event': 'deprecated_cascade',
                    'parent_claim_id': deprecated_claim_id,
                    'child_claim_id': item['claim_id'],
                    'new_status': 'conflicted'
                }))
            except Exception as e:
                logger.error(f"Cascade update failed for {item['claim_id']}: {e}")
    except Exception as e:
        logger.error(f"Deprecated cascade scan failed: {e}")


def search_archive(event):
    """POST /rag/search-archive — Bedrock KB 검색 + topic/source 메타데이터 필터
    Requirements: 8.1, 8.4, 8.5
    """
    body = parse_body(event)
    query = body.get('query', '')

    if not query:
        return response(400, {'error': 'missing required parameter: query'})

    topic = body.get('topic', '')
    source = body.get('source', '')
    max_results = int(body.get('max_results', 5))

    if not BEDROCK_KB_ID:
        return response(200, {
            'message': 'Bedrock KB ID not configured',
            'query': query,
            'results': []
        })

    try:
        bedrock_runtime = boto3.client('bedrock-agent-runtime', region_name=BACKEND_REGION)

        # 메타데이터 필터 구성 (topic/source)
        filter_conditions = []
        if topic:
            filter_conditions.append({'equals': {'key': 'topic', 'value': topic}})
        if source:
            if source not in VALID_SOURCES:
                return response(400, {'error': f'invalid source value: {source}. allowed: {sorted(VALID_SOURCES)}'})
            filter_conditions.append({'equals': {'key': 'source', 'value': source}})

        bedrock_filter = None
        if len(filter_conditions) == 1:
            bedrock_filter = filter_conditions[0]
        elif len(filter_conditions) > 1:
            bedrock_filter = {'andAll': filter_conditions}

        vector_config = {
            'searchType': os.environ.get('SEARCH_TYPE', 'HYBRID'),
            'numberOfResults': max_results
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

        # 응답 구조화
        results = []
        for c in resp.get('citations', []):
            for r in c.get('retrievedReferences', []):
                results.append({
                    'uri': r.get('location', {}).get('s3Location', {}).get('uri', ''),
                    'score': r.get('metadata', {}).get('score', r.get('score', None)),
                    'text': c.get('generatedResponsePart', {}).get('textResponsePart', {}).get('text', '')
                })

        return response(200, {
            'query': query,
            'answer': resp.get('output', {}).get('text', ''),
            'results': results,
            'count': len(results),
            'filters': {'topic': topic, 'source': source} if (topic or source) else None
        })

    except Exception as e:
        logger.error(f"search_archive error: {e}")
        return response(500, {'error': str(e)})


def get_evidence(event):
    """POST /rag/get-evidence — claim의 evidence 배열 반환
    Requirements: 8.2
    """
    body = parse_body(event)
    claim_id = body.get('claim_id', '')

    if not claim_id:
        return response(400, {'error': 'missing required parameter: claim_id'})

    table = dynamodb.Table(CLAIM_DB_TABLE)

    # 최신 버전의 claim 조회
    result = table.query(
        KeyConditionExpression='claim_id = :cid',
        ExpressionAttributeValues={':cid': claim_id},
        ScanIndexForward=False,
        Limit=1
    )
    items = result.get('Items', [])
    if not items:
        return response(404, {'error': 'claim not found', 'claim_id': claim_id})

    claim = items[0]
    evidence = claim.get('evidence', [])

    return response(200, {
        'claim_id': claim_id,
        'version': claim.get('version'),
        'evidence': evidence,
        'evidence_count': len(evidence)
    })


def list_verified_claims(event):
    """POST /rag/list-verified-claims — topic의 verified claim 목록 반환
    Requirements: 8.3 — topic-index GSI 사용, status=verified 필터
    """
    body = parse_body(event)
    topic = body.get('topic', '')

    if not topic:
        return response(400, {'error': 'missing required parameter: topic'})

    table = dynamodb.Table(CLAIM_DB_TABLE)

    result = table.query(
        IndexName='topic-index',
        KeyConditionExpression='topic = :t',
        FilterExpression='#s = :v AND is_latest = :il',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={':t': topic, ':v': 'verified', ':il': True}
    )

    claims = []
    for item in result.get('Items', []):
        claims.append({
            'claim_id': item.get('claim_id'),
            'version': item.get('version'),
            'statement': item.get('statement'),
            'confidence': float(item.get('confidence', 0)),
            'last_verified_at': item.get('last_verified_at'),
            'evidence_count': len(item.get('evidence', []))
        })

    return response(200, {
        'topic': topic,
        'claims': claims,
        'count': len(claims)
    })


# ============================================================================
# Human Review Gate 함수 (Task 7.1)
# Requirements: 14.1, 14.2, 14.3, 14.4, 14.6
# ============================================================================

def approve_claim(event):
    """POST /rag/claims/approve — claim 승인
    Requirements: 14.3 — approval_status='approved', approved_by, approved_at 설정
    Optimistic locking 적용
    """
    body = parse_body(event)
    claim_id = body.get('claim_id', '')
    expected_version = body.get('version')
    approved_by = body.get('approved_by', '')

    if not claim_id or expected_version is None or not approved_by:
        return response(400, {'error': 'claim_id, version, and approved_by are required'})

    table = dynamodb.Table(CLAIM_DB_TABLE)

    # 최대 3회 재시도 (optimistic locking)
    for attempt in range(3):
        try:
            # 현재 claim 조회
            result = table.get_item(Key={'claim_id': claim_id, 'version': int(expected_version)})
            item = result.get('Item')
            if not item:
                return response(404, {'error': 'claim not found', 'claim_id': claim_id, 'version': expected_version})

            # status가 verified인 경우만 승인 가능
            current_status = item.get('status', '')
            if current_status != 'verified':
                return response(409, {
                    'error': f'only verified claims can be approved, current status: {current_status}',
                    'current_status': current_status
                })

            now = datetime.utcnow().isoformat() + 'Z'

            # Optimistic locking으로 approval_status 업데이트
            table.update_item(
                Key={'claim_id': claim_id, 'version': int(expected_version)},
                UpdateExpression='SET approval_status = :as, approved_by = :ab, approved_at = :at',
                ConditionExpression='version = :ev',
                ExpressionAttributeValues={
                    ':as': 'approved',
                    ':ab': approved_by,
                    ':at': now,
                    ':ev': int(expected_version)
                }
            )

            logger.info(json.dumps({
                'event': 'claim_approved',
                'claim_id': claim_id,
                'version': int(expected_version),
                'approved_by': approved_by
            }))

            return response(200, {
                'claim_id': claim_id,
                'version': int(expected_version),
                'approval_status': 'approved',
                'approved_by': approved_by,
                'approved_at': now
            })

        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            if attempt < 2:
                logger.warning(f"Optimistic lock conflict for approve {claim_id}, retry {attempt + 1}/3")
                _exponential_backoff_jitter(attempt)
                try:
                    scan_resp = table.query(
                        KeyConditionExpression='claim_id = :cid',
                        ExpressionAttributeValues={':cid': claim_id},
                        ScanIndexForward=False, Limit=1
                    )
                    if scan_resp.get('Items'):
                        expected_version = scan_resp['Items'][0]['version']
                except Exception:
                    pass
                continue
            else:
                logger.error(f"Optimistic lock failed after 3 retries for approve: {claim_id}")
                return response(409, {'error': 'version conflict after 3 retries', 'claim_id': claim_id})

    return response(500, {'error': 'unexpected error in approve_claim'})


def reject_claim(event):
    """POST /rag/claims/reject — claim 거부
    Requirements: 14.4 — approval_status='rejected' 설정
    Optimistic locking 적용
    """
    body = parse_body(event)
    claim_id = body.get('claim_id', '')
    expected_version = body.get('version')
    rejected_by = body.get('rejected_by', '')
    rejection_reason = body.get('rejection_reason', '')

    if not claim_id or expected_version is None or not rejected_by:
        return response(400, {'error': 'claim_id, version, and rejected_by are required'})

    table = dynamodb.Table(CLAIM_DB_TABLE)

    # 최대 3회 재시도 (optimistic locking)
    for attempt in range(3):
        try:
            # 현재 claim 조회
            result = table.get_item(Key={'claim_id': claim_id, 'version': int(expected_version)})
            item = result.get('Item')
            if not item:
                return response(404, {'error': 'claim not found', 'claim_id': claim_id, 'version': expected_version})

            # status가 verified인 경우만 거부 가능
            current_status = item.get('status', '')
            if current_status != 'verified':
                return response(409, {
                    'error': f'only verified claims can be rejected, current status: {current_status}',
                    'current_status': current_status
                })

            now = datetime.utcnow().isoformat() + 'Z'

            # 업데이트 표현식 구성
            update_expr = 'SET approval_status = :as, rejected_by = :rb, rejected_at = :rt'
            expr_values = {
                ':as': 'rejected',
                ':rb': rejected_by,
                ':rt': now,
                ':ev': int(expected_version)
            }

            if rejection_reason:
                update_expr += ', rejection_reason = :rr'
                expr_values[':rr'] = rejection_reason

            # Optimistic locking
            table.update_item(
                Key={'claim_id': claim_id, 'version': int(expected_version)},
                UpdateExpression=update_expr,
                ConditionExpression='version = :ev',
                ExpressionAttributeValues=expr_values
            )

            logger.info(json.dumps({
                'event': 'claim_rejected',
                'claim_id': claim_id,
                'version': int(expected_version),
                'rejected_by': rejected_by,
                'rejection_reason': rejection_reason or None
            }))

            return response(200, {
                'claim_id': claim_id,
                'version': int(expected_version),
                'approval_status': 'rejected',
                'rejected_by': rejected_by,
                'rejection_reason': rejection_reason or None
            })

        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            if attempt < 2:
                logger.warning(f"Optimistic lock conflict for reject {claim_id}, retry {attempt + 1}/3")
                _exponential_backoff_jitter(attempt)
                try:
                    scan_resp = table.query(
                        KeyConditionExpression='claim_id = :cid',
                        ExpressionAttributeValues={':cid': claim_id},
                        ScanIndexForward=False, Limit=1
                    )
                    if scan_resp.get('Items'):
                        expected_version = scan_resp['Items'][0]['version']
                except Exception:
                    pass
                continue
            else:
                logger.error(f"Optimistic lock failed after 3 retries for reject: {claim_id}")
                return response(409, {'error': 'version conflict after 3 retries', 'claim_id': claim_id})

    return response(500, {'error': 'unexpected error in reject_claim'})


def _is_publishable(claim):
    """publishable 계산: status='verified' AND approval_status='approved'
    Requirements: 14.6
    """
    return claim.get('status') == 'verified' and claim.get('approval_status') == 'approved'


# ============================================================================
# HDD 섹션 생성 및 마크다운 출판 (Task 7.3)
# Requirements: 10.1~10.6, 14.5, 14.7
# ============================================================================

# 면책 조항 (Requirements 10.6)
HDD_DISCLAIMER = "이 문서는 AI가 검증된 claim을 기반으로 자동 생성하였습니다"


def generate_hdd_section(event):
    """POST /rag/generate-hdd — HDD 섹션 자동 생성
    Requirements: 10.1, 10.2, 10.3, 10.6
    - topic의 verified + approved claim 조회
    - Foundation_Model로 HDD 마크다운 생성
    - evidence 각주 포함 (include_evidence=true)
    - 면책 조항 자동 포함
    """
    body = parse_body(event)
    topic = body.get('topic', '')
    section_title = body.get('section_title', '')
    include_evidence = body.get('include_evidence', True)

    if not topic:
        return response(400, {'error': 'missing required parameter: topic'})
    if not section_title:
        return response(400, {'error': 'missing required parameter: section_title'})

    table = dynamodb.Table(CLAIM_DB_TABLE)

    # verified + approved claim 조회 (Requirements 10.2, 14.5)
    try:
        result = table.query(
            IndexName='topic-index',
            KeyConditionExpression='topic = :t',
            FilterExpression='#s = :v AND is_latest = :il',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':t': topic, ':v': 'verified', ':il': True}
        )
    except Exception as e:
        logger.error(f"Claim DB query failed for generate_hdd_section: {e}")
        return response(500, {'error': f'Claim DB query failed: {str(e)}'})

    # approved claim만 필터 (Requirements 14.5, 14.7)
    approved_claims = [c for c in result.get('Items', []) if _is_publishable(c)]

    if not approved_claims:
        return response(403, {
            'error': 'claim requires approval for critical topic',
            'topic': topic,
            'message': 'No verified+approved claims found for this topic. Claims must have approval_status=approved.'
        })

    # Foundation Model로 HDD 마크다운 생성 (Requirements 10.2)
    try:
        bedrock_runtime = boto3.client('bedrock-runtime', region_name=BACKEND_REGION)
        model_id = os.environ.get('FOUNDATION_MODEL_ARN', 'us.anthropic.claude-3-5-haiku-20241022-v1:0')

        # claim context 구성
        claims_context = ""
        footnotes = []
        for i, claim in enumerate(approved_claims):
            claims_context += f"\n[Claim {i+1}] (confidence: {claim.get('confidence', 'N/A')})\n"
            claims_context += f"  Statement: {claim.get('statement', '')}\n"
            for ev in claim.get('evidence', []):
                footnote_idx = len(footnotes) + 1
                footnotes.append({
                    'index': footnote_idx,
                    'source_document_id': ev.get('source_document_id', ''),
                    'source_chunk': ev.get('source_chunk', '')[:200],
                    'source_type': ev.get('source_type', ''),
                    'page_number': ev.get('page_number')
                })

        evidence_instruction = ""
        if include_evidence:
            evidence_instruction = "\n각 주장에 대해 [^N] 형식의 각주 번호를 포함하세요. 각주는 문서 끝에 배치됩니다."

        prompt = f"""다음 검증된 claim들을 기반으로 HDD(Hardware Design Description) 섹션을 마크다운 형식으로 작성하세요.

섹션 제목: {section_title}
주제: {topic}
{evidence_instruction}

검증된 Claim 목록:
{claims_context}

마크다운 형식으로 기술 문서 섹션을 작성하세요. 전문적이고 정확한 기술 문서 스타일을 유지하세요."""

        resp = bedrock_runtime.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
                'messages': [{'role': 'user', 'content': prompt}]
            })
        )

        resp_body = json.loads(resp['body'].read())
        markdown_content = resp_body.get('content', [{}])[0].get('text', '')

    except Exception as e:
        logger.error(f"HDD section generation failed: {e}")
        return response(500, {'error': f'HDD section generation failed: {str(e)}'})

    # evidence 각주 추가 (Requirements 10.3)
    if include_evidence and footnotes:
        markdown_content += "\n\n---\n\n### 참조 (Evidence)\n\n"
        for fn in footnotes:
            markdown_content += f"[^{fn['index']}]: {fn['source_document_id']}"
            if fn.get('page_number'):
                markdown_content += f" (p.{fn['page_number']})"
            if fn.get('source_type'):
                markdown_content += f" [{fn['source_type']}]"
            markdown_content += "\n"

    # 면책 조항 자동 포함 (Requirements 10.6)
    markdown_content += f"\n\n---\n\n> ⚠️ {HDD_DISCLAIMER}\n"

    logger.info(json.dumps({
        'event': 'hdd_section_generated',
        'topic': topic,
        'section_title': section_title,
        'claims_used': len(approved_claims),
        'include_evidence': include_evidence
    }))

    return response(200, {
        'topic': topic,
        'section_title': section_title,
        'markdown': markdown_content,
        'claims_used': len(approved_claims),
        'include_evidence': include_evidence,
        'disclaimer': HDD_DISCLAIMER
    })


def publish_markdown(event):
    """POST /rag/publish-markdown — 마크다운 출판
    Requirements: 10.4, 10.5, 14.5, 14.7
    - Seoul_S3 published/ 접두사에 저장
    - 메타데이터 자동 생성 (source='system_generated')
    - critical topic claim은 approval_status='approved'만 사용 (HTTP 403)
    """
    body = parse_body(event)
    content = body.get('content', '')
    filename = body.get('filename', '')
    topic = body.get('topic', '')

    if not content:
        return response(400, {'error': 'missing required parameter: content'})
    if not filename:
        return response(400, {'error': 'missing required parameter: filename'})

    # .md 확장자 보장
    if not filename.endswith('.md'):
        filename += '.md'

    # topic이 지정된 경우, 해당 topic의 claim이 모두 approved인지 확인 (Requirements 14.5, 14.7)
    if topic:
        table = dynamodb.Table(CLAIM_DB_TABLE)
        try:
            result = table.query(
                IndexName='topic-index',
                KeyConditionExpression='topic = :t',
                FilterExpression='#s = :v AND is_latest = :il',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':t': topic, ':v': 'verified', ':il': True}
            )
            verified_claims = result.get('Items', [])

            # verified claim 중 미승인 claim이 있으면 HTTP 403
            unapproved = [c for c in verified_claims if not _is_publishable(c)]
            if unapproved:
                return response(403, {
                    'error': 'claim requires approval for critical topic',
                    'topic': topic,
                    'unapproved_count': len(unapproved),
                    'message': f'{len(unapproved)} claims for topic "{topic}" are not approved. All claims must have approval_status=approved for publishing.'
                })
        except Exception as e:
            logger.error(f"Claim approval check failed for publish_markdown: {e}")
            return response(500, {'error': f'Claim approval check failed: {str(e)}'})

    # Seoul_S3 published/ 접두사에 저장 (Requirements 10.4)
    s3_key = f"published/{filename}"
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_SEOUL,
            Key=s3_key,
            Body=content.encode('utf-8'),
            ContentType='text/markdown; charset=utf-8',
            ServerSideEncryption='aws:kms'
        )
    except Exception as e:
        logger.error(f"Failed to save markdown to S3: {e}")
        return response(500, {'error': f'Failed to save markdown: {str(e)}'})

    # 메타데이터 자동 생성 (Requirements 10.5)
    now = datetime.utcnow().isoformat() + 'Z'
    metadata = {
        'metadataAttributes': {
            'source': 'system_generated',
            'document_type': 'markdown',
            'generation_basis': 'verified_claims',
            'upload_date': now,
            'topic': topic or 'general',
            'variant': 'default',
            'doc_version': '1.0'
        }
    }

    metadata_key = f"{s3_key}.metadata.json"
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_SEOUL,
            Key=metadata_key,
            Body=json.dumps(metadata, ensure_ascii=False).encode('utf-8'),
            ContentType='application/json',
            ServerSideEncryption='aws:kms'
        )
    except Exception as e:
        logger.warning(f"Metadata creation failed for {s3_key} (non-blocking): {e}")

    logger.info(json.dumps({
        'event': 'markdown_published',
        's3_key': s3_key,
        'filename': filename,
        'topic': topic or 'general',
        'content_length': len(content)
    }))

    return response(200, {
        'message': 'Markdown published successfully',
        's3_key': s3_key,
        'bucket': S3_BUCKET_SEOUL,
        'filename': filename,
        'topic': topic or 'general',
        'metadata_key': metadata_key,
        'source': 'system_generated',
        'generation_basis': 'verified_claims'
    })


# ============================================================================
# Verification Pipeline (Task 5.4)
# Requirements: 9.1~9.9
# ============================================================================

def verification_pipeline(query, variant=None):
    """8단계 Verification Pipeline 실행
    (1) 질문 수신 → (2) topic 식별 → (3) claim 검색 → (3.5) Neptune placeholder
    → (4) evidence 추적 → (5) 충돌 검사 → (6) 버전 확인 → (7) 답변 생성 → (8) evidence 첨부
    Requirements: 9.1~9.9
    """
    pipeline_start = time.time()
    step_times = {}

    # CloudWatch 메트릭 클라이언트
    try:
        cloudwatch = boto3.client('cloudwatch', region_name='ap-northeast-2')
    except Exception:
        cloudwatch = None

    def _log_step(step_name, start_ts):
        elapsed_ms = int((time.time() - start_ts) * 1000)
        step_times[step_name] = elapsed_ms
        logger.info(json.dumps({
            'event': 'verification_pipeline_step',
            'step': step_name,
            'execution_time_ms': elapsed_ms,
            'query_length': len(query)
        }))

    # (1) 질문 수신
    step_start = time.time()
    logger.info(json.dumps({'event': 'verification_pipeline_start', 'query_length': len(query), 'variant': variant}))
    _log_step('1_receive_query', step_start)

    # (2) Foundation Model로 topic 식별 (최대 3개)
    step_start = time.time()
    topics_identified = _identify_topics(query)
    _log_step('2_topic_identification', step_start)

    if not topics_identified:
        # topic 식별 실패 시 Bedrock KB 폴백
        return _bedrock_kb_fallback(query, pipeline_start, step_times, topics_identified)

    # (3) Claim DB에서 verified claim 검색
    step_start = time.time()
    table = dynamodb.Table(CLAIM_DB_TABLE)
    verified_claims = []

    for topic in topics_identified:
        try:
            if variant:
                # variant 파라미터 포함 시 topic-variant-index GSI 사용 (Requirements 9.9)
                topic_variant_key = f"{topic}#{variant}"
                result = table.query(
                    IndexName='topic-variant-index',
                    KeyConditionExpression='topic_variant = :tv',
                    FilterExpression='#s = :v AND is_latest = :il',
                    ExpressionAttributeNames={'#s': 'status'},
                    ExpressionAttributeValues={':tv': topic_variant_key, ':v': 'verified', ':il': True}
                )
            else:
                # topic-index GSI 사용 (Requirements 9.3)
                result = table.query(
                    IndexName='topic-index',
                    KeyConditionExpression='topic = :t',
                    FilterExpression='#s = :v AND is_latest = :il',
                    ExpressionAttributeNames={'#s': 'status'},
                    ExpressionAttributeValues={':t': topic, ':v': 'verified', ':il': True}
                )
            verified_claims.extend(result.get('Items', []))
        except Exception as e:
            logger.error(f"Claim DB query failed for topic {topic}: {e}")

    _log_step('3_claim_search', step_start)

    # Claim 없으면 Bedrock KB 폴백 (Requirements 9.7)
    if not verified_claims:
        return _bedrock_kb_fallback(query, pipeline_start, step_times, topics_identified)

    # (3.5) Neptune graph traversal — Phase 6 placeholder
    step_start = time.time()
    # TODO: Phase 6에서 Neptune Gremlin Read-Only 쿼리 추가
    _log_step('3.5_neptune_graph', step_start)

    # (4) Evidence 근거 추적
    step_start = time.time()
    all_evidence = []
    for claim in verified_claims:
        evidence_list = claim.get('evidence', [])
        for ev in evidence_list:
            ev['claim_id'] = claim.get('claim_id')
            all_evidence.append(ev)
    _log_step('4_evidence_tracking', step_start)

    # (5) 충돌 검사 — conflicted claim 존재 여부 확인 (Requirements 9.4)
    step_start = time.time()
    has_conflicts = False
    for topic in topics_identified:
        try:
            conflict_result = table.query(
                IndexName='topic-index',
                KeyConditionExpression='topic = :t',
                FilterExpression='#s = :cs',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':t': topic, ':cs': 'conflicted'}
            )
            if conflict_result.get('Items'):
                has_conflicts = True
                break
        except Exception as e:
            logger.error(f"Conflict check failed for topic {topic}: {e}")
    _log_step('5_conflict_check', step_start)

    # (6) 버전 확인 — is_latest=true만 사용 (이미 필터링됨)
    step_start = time.time()
    latest_claims = [c for c in verified_claims if c.get('is_latest', False)]
    _log_step('6_version_check', step_start)

    # (7) Foundation Model로 답변 생성 (Requirements 9.5)
    step_start = time.time()
    answer = _generate_answer_from_claims(query, latest_claims, has_conflicts)
    _log_step('7_answer_generation', step_start)

    # (8) Evidence 첨부
    step_start = time.time()
    claims_used = list(set(c.get('claim_id', '') for c in latest_claims))
    citations = []
    for claim in latest_claims:
        for ev in claim.get('evidence', []):
            citations.append({
                'text': ev.get('source_chunk', ''),
                'references': [{
                    'uri': ev.get('source_document_id', ''),
                    'claim_id': claim.get('claim_id', ''),
                    'source_type': ev.get('source_type', ''),
                    'page_number': ev.get('page_number')
                }]
            })
    _log_step('8_evidence_attachment', step_start)

    pipeline_execution_time_ms = int((time.time() - pipeline_start) * 1000)

    # KPI: AvgEvidenceCountPerAnswer (Requirements 15.5)
    avg_evidence = len(all_evidence) / max(len(latest_claims), 1)
    _publish_metric(cloudwatch, 'AvgEvidenceCountPerAnswer', avg_evidence, 'Count')

    logger.info(json.dumps({
        'event': 'verification_pipeline_complete',
        'pipeline_execution_time_ms': pipeline_execution_time_ms,
        'claims_used': len(claims_used),
        'topics_identified': topics_identified,
        'has_conflicts': has_conflicts,
        'fallback': False,
        'step_times': step_times
    }))

    return {
        'answer': answer,
        'citations': citations,
        'verification_metadata': {
            'claims_used': claims_used,
            'topics_identified': topics_identified,
            'has_conflicts': has_conflicts,
            'pipeline_execution_time_ms': pipeline_execution_time_ms,
            'fallback': False
        }
    }


def _identify_topics(query):
    """Foundation Model로 질의에서 topic 식별 (최대 3개)
    Requirements: 9.2
    """
    try:
        bedrock_runtime = boto3.client('bedrock-runtime', region_name=BACKEND_REGION)
        model_id = os.environ.get('FOUNDATION_MODEL_ARN', 'us.anthropic.claude-3-5-haiku-20241022-v1:0')

        prompt = f"""다음 질문에서 관련 기술 주제(topic)를 최대 3개 식별하세요.
topic은 계층적 형식(슬래시 구분)으로 반환하세요.
예: ["ucie/phy/ltssm", "ahb/signal/haddr", "soc/clock"]

JSON 배열만 반환하세요. 다른 텍스트는 포함하지 마세요.

질문: {query}"""

        resp = bedrock_runtime.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 256,
                'messages': [{'role': 'user', 'content': prompt}]
            })
        )

        resp_body = json.loads(resp['body'].read())
        content_text = resp_body.get('content', [{}])[0].get('text', '[]')

        json_match = re.search(r'\[.*?\]', content_text, re.DOTALL)
        if json_match:
            topics = json.loads(json_match.group())
            # 최대 3개로 제한
            return [t for t in topics if isinstance(t, str) and '/' in t][:3]
        return []

    except Exception as e:
        logger.error(f"Topic identification failed: {e}")
        return []


def _generate_answer_from_claims(query, claims, has_conflicts):
    """Verified claim 기반 답변 생성 (Requirements 9.5)"""
    try:
        bedrock_runtime = boto3.client('bedrock-runtime', region_name=BACKEND_REGION)
        model_id = os.environ.get('FOUNDATION_MODEL_ARN', 'us.anthropic.claude-3-5-haiku-20241022-v1:0')

        # claim context 구성
        claims_context = ""
        for i, claim in enumerate(claims):
            claims_context += f"\n[Claim {i+1}] (confidence: {claim.get('confidence', 'N/A')})\n"
            claims_context += f"  Statement: {claim.get('statement', '')}\n"
            for ev in claim.get('evidence', []):
                claims_context += f"  Evidence: {ev.get('source_chunk', '')[:200]}\n"

        conflict_warning = ""
        if has_conflicts:
            conflict_warning = "\n주의: 일부 정보에 충돌이 감지되었습니다. 답변에 이 사실을 언급하세요."

        prompt = f"""다음 검증된 claim들을 기반으로 질문에 답변하세요.
claim의 statement와 evidence만 사용하여 정확한 답변을 생성하세요.{conflict_warning}

검증된 Claim 목록:
{claims_context}

질문: {query}"""

        resp = bedrock_runtime.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 2048,
                'messages': [{'role': 'user', 'content': prompt}]
            })
        )

        resp_body = json.loads(resp['body'].read())
        answer = resp_body.get('content', [{}])[0].get('text', '')

        # 충돌 경고 메시지 추가 (Requirements 9.4)
        if has_conflicts and '충돌' not in answer:
            answer += "\n\n⚠️ 일부 정보에 충돌이 감지되었습니다. 최신 검증 결과를 확인하세요."

        return answer

    except Exception as e:
        logger.error(f"Answer generation from claims failed: {e}")
        return f"검증된 claim을 기반으로 답변을 생성하지 못했습니다: {str(e)}"


def _bedrock_kb_fallback(query, pipeline_start, step_times, topics_identified):
    """Claim DB에 관련 claim 없을 때 Bedrock KB 폴백 (Requirements 9.7)"""
    try:
        cloudwatch = boto3.client('cloudwatch', region_name='ap-northeast-2')
    except Exception:
        cloudwatch = None

    # KPI: BedrockKBFallbackRate 증가 (Requirements 15.4)
    _publish_metric(cloudwatch, 'BedrockKBFallbackRate', 1, 'Count')

    try:
        bedrock_runtime = boto3.client('bedrock-agent-runtime', region_name=BACKEND_REGION)

        vector_config = {
            'searchType': os.environ.get('SEARCH_TYPE', 'HYBRID'),
            'numberOfResults': int(os.environ.get('SEARCH_RESULTS_COUNT', '5'))
        }

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

        citations = []
        for c in resp.get('citations', []):
            refs = []
            for r in c.get('retrievedReferences', []):
                refs.append({
                    'uri': r.get('location', {}).get('s3Location', {}).get('uri', ''),
                    'score': r.get('metadata', {}).get('score', r.get('score', None))
                })
            citations.append({
                'text': c.get('generatedResponsePart', {}).get('textResponsePart', {}).get('text', ''),
                'references': refs
            })

        pipeline_execution_time_ms = int((time.time() - pipeline_start) * 1000)

        logger.info(json.dumps({
            'event': 'verification_pipeline_fallback',
            'pipeline_execution_time_ms': pipeline_execution_time_ms,
            'topics_identified': topics_identified,
            'step_times': step_times
        }))

        return {
            'answer': resp.get('output', {}).get('text', ''),
            'citations': citations,
            'verification_metadata': {
                'claims_used': [],
                'topics_identified': topics_identified,
                'has_conflicts': False,
                'pipeline_execution_time_ms': pipeline_execution_time_ms,
                'fallback': True
            }
        }

    except Exception as e:
        logger.error(f"Bedrock KB fallback failed: {e}")
        pipeline_execution_time_ms = int((time.time() - pipeline_start) * 1000)
        return {
            'answer': f'Verification Pipeline 및 Bedrock KB 폴백 모두 실패: {str(e)}',
            'citations': [],
            'verification_metadata': {
                'claims_used': [],
                'topics_identified': topics_identified,
                'has_conflicts': False,
                'pipeline_execution_time_ms': pipeline_execution_time_ms,
                'fallback': True
            }
        }


def _publish_metric(cloudwatch, metric_name, value, unit):
    """CloudWatch 커스텀 메트릭 발행 (BOS-AI/ClaimDB 네임스페이스)
    Requirements: 15.1~15.8
    """
    if not cloudwatch:
        return
    try:
        cloudwatch.put_metric_data(
            Namespace='BOS-AI/ClaimDB',
            MetricData=[{
                'MetricName': metric_name,
                'Value': float(value),
                'Unit': unit,
                'Timestamp': datetime.utcnow()
            }]
        )
    except Exception as e:
        logger.warning(f"Failed to publish metric {metric_name}: {e}")


# ============================================================================
# Claim Ingestion 파이프라인 (Task 3.12)
# Requirements: 7.1~7.7
# ============================================================================

def ingest_claims(event, context):
    """Lambda Event 비동기 호출 — 문서를 claim 단위로 분해
    Requirements: 7.1~7.7
    - 1회 최대 100건 문서 처리
    - Foundation_Model로 claim 추출 (statement + evidence 분리)
    - 각 claim을 Claim_DB에 status=draft, version=1로 저장
    - has_more + continuation_token 페이지네이션
    """
    s3_prefix = event.get('s3_prefix', S3_PREFIX)
    continuation_token = event.get('continuation_token', None)
    max_docs = min(event.get('max_docs', 100), 100)  # 최대 100건

    documents_processed = 0
    claims_created = 0
    documents_failed = 0
    last_key = None

    list_params = {
        'Bucket': S3_BUCKET_SEOUL,
        'Prefix': s3_prefix,
        'MaxKeys': max_docs
    }
    if continuation_token:
        list_params['StartAfter'] = continuation_token

    try:
        resp = s3_client.list_objects_v2(**list_params)
        objects = resp.get('Contents', [])

        table = dynamodb.Table(CLAIM_DB_TABLE)

        for obj in objects:
            key = obj['Key']
            last_key = key

            # 메타데이터 파일, 디렉토리 건너뛰기
            if key.endswith('.metadata.json') or key.endswith('/'):
                continue

            # 문서 수 제한
            if documents_processed >= max_docs:
                break

            try:
                # S3에서 문서 읽기
                doc_resp = s3_client.get_object(Bucket=S3_BUCKET_SEOUL, Key=key)
                doc_content = doc_resp['Body'].read().decode('utf-8', errors='replace')

                # 빈 문서 건너뛰기
                if not doc_content.strip():
                    documents_processed += 1
                    continue

                # topic 자동 추출
                topic = extract_topic_from_path(key)
                if not topic:
                    topic = 'uncategorized'

                # Foundation Model로 claim 추출 (Requirements 7.1, 7.2, 7.6)
                extracted_claims = _extract_claims_from_document(doc_content, key, topic)

                # 각 claim을 Claim_DB에 저장 (Requirements 7.3)
                for claim_data in extracted_claims:
                    try:
                        claim_id = str(uuid.uuid4())
                        claim_family_id = str(uuid.uuid4())
                        now = datetime.utcnow().isoformat() + 'Z'

                        # evidence에 chunk_hash 생성
                        for ev in claim_data.get('evidence', []):
                            if not ev.get('chunk_hash'):
                                ev['chunk_hash'] = hashlib.sha256(
                                    ev.get('source_chunk', '').encode('utf-8')
                                ).hexdigest()
                            ev['extraction_date'] = now
                            ev['source_document_id'] = key

                        variant = claim_data.get('variant', 'default')
                        item = {
                            'claim_id': claim_id,
                            'version': 1,
                            'topic': claim_data.get('topic', topic),
                            'statement': claim_data.get('statement', ''),
                            'evidence': claim_data.get('evidence', []),
                            'confidence': Decimal(str(claim_data.get('confidence', 0.5))),
                            'status': 'draft',
                            'variant': variant,
                            'topic_variant': f"{claim_data.get('topic', topic)}#{variant}",
                            'claim_family_id': claim_family_id,
                            'is_latest': True,
                            'derived_from': [],
                            'created_at': now,
                            'last_verified_at': now,
                            'created_by': 'system:ingest_claims',
                            'approval_status': 'not_applicable'
                        }

                        table.put_item(
                            Item=item,
                            ConditionExpression='attribute_not_exists(claim_id)'
                        )
                        claims_created += 1
                    except Exception as e:
                        logger.error(f"Failed to save claim from {key}: {e}")

                documents_processed += 1

            except Exception as e:
                # 개별 문서 실패 시 건너뛰고 계속 (Requirements 7.5)
                logger.error(json.dumps({
                    'event': 'claim_extraction_failed',
                    'document': key,
                    'error': str(e)
                }))
                documents_failed += 1
                documents_processed += 1

        has_more = (documents_processed >= max_docs) and resp.get('IsTruncated', False)
        result = {
            'documents_processed': documents_processed,
            'claims_created': claims_created,
            'documents_failed': documents_failed,
            'has_more': has_more
        }
        if has_more and last_key:
            result['continuation_token'] = last_key

        logger.info(json.dumps({'event': 'ingest_claims_complete', **result}))

        # KPI 메트릭 발행 (Requirements 15.2)
        try:
            cw = boto3.client('cloudwatch', region_name='ap-northeast-2')
            total_attempts = claims_created + documents_failed
            if total_attempts > 0:
                success_rate = (claims_created / total_attempts) * 100
                _publish_metric(cw, 'ClaimIngestionSuccessRate', success_rate, 'Percent')
        except Exception as metric_err:
            logger.warning(f"KPI metric publish failed after ingest_claims: {metric_err}")

        return result

    except Exception as e:
        logger.error(f"ingest_claims failed: {e}", exc_info=True)
        return {
            'error': str(e),
            'documents_processed': documents_processed,
            'claims_created': claims_created,
            'documents_failed': documents_failed + 1
        }


def _extract_claims_from_document(doc_content, s3_key, topic):
    """Foundation Model을 사용하여 문서에서 claim 추출 (Requirements 7.1, 7.2, 7.6)
    statement: LLM이 재구성한 정규화된 1문장 (10~500자)
    evidence.source_chunk: 원본 문서의 정확한 인용 (10~1000자)
    """
    try:
        bedrock_runtime = boto3.client('bedrock-runtime', region_name=BACKEND_REGION)

        # 문서 내용 truncation (Bedrock 입력 제한 대응)
        max_content_len = 50000
        truncated_content = doc_content[:max_content_len]

        prompt = f"""다음 기술 문서를 분석하여 개별 사실 진술(claim)로 분해하세요.

각 claim은 다음 형식의 JSON 배열로 반환하세요:
[
  {{
    "statement": "소스에서 도출된 정규화된 1문장 사실 진술 (10~500자, LLM이 명확성을 위해 재구성 가능)",
    "evidence": [
      {{
        "source_chunk": "원본 문서의 정확한 인용(verbatim excerpt, 10~1000자)",
        "source_type": "md",
        "source_path": "문서 내 위치"
      }}
    ],
    "confidence": 0.8,
    "topic": "{topic}"
  }}
]

중요 규칙:
- statement는 소스에서 도출된 정규화된 1문장 사실 진술로, LLM이 명확성을 위해 재구성할 수 있습니다.
- evidence.source_chunk는 원본 문서의 정확한 인용(verbatim excerpt)이어야 합니다.
- confidence는 0.0~1.0 범위의 확신도입니다.
- JSON 배열만 반환하세요. 다른 텍스트는 포함하지 마세요.

문서 내용:
{truncated_content}"""

        model_id = os.environ.get('FOUNDATION_MODEL_ARN', 'us.anthropic.claude-3-5-haiku-20241022-v1:0')

        resp = bedrock_runtime.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4096,
                'messages': [{'role': 'user', 'content': prompt}]
            })
        )

        resp_body = json.loads(resp['body'].read())
        content_text = resp_body.get('content', [{}])[0].get('text', '[]')

        # JSON 배열 파싱
        # LLM 응답에서 JSON 부분만 추출
        json_match = re.search(r'\[.*\]', content_text, re.DOTALL)
        if json_match:
            claims = json.loads(json_match.group())
        else:
            claims = []

        # 유효성 검증 및 필터링
        valid_claims = []
        for c in claims:
            stmt = c.get('statement', '')
            if len(stmt) < 10 or len(stmt) > 500:
                continue
            evidence = c.get('evidence', [])
            valid_evidence = []
            for ev in evidence:
                chunk = ev.get('source_chunk', '')
                if len(chunk) >= 10 and len(chunk) <= 1000:
                    valid_evidence.append(ev)
            if valid_evidence:
                c['evidence'] = valid_evidence
                valid_claims.append(c)

        return valid_claims

    except Exception as e:
        logger.error(f"LLM claim extraction failed for {s3_key}: {e}")
        return []


# ============================================================================
# Cross-Check 파이프라인 (Task 9.1)
# Requirements: 11.1~11.10
# ============================================================================

def _exponential_backoff_jitter(attempt, base_ms=100, max_ms=2000):
    """Exponential Backoff + Full Jitter (Requirements 5.10, 11.x)
    sleep = random(0, min(max_ms, base_ms * 2^attempt))
    """
    cap = min(max_ms, base_ms * (2 ** attempt))
    sleep_ms = random.uniform(0, cap)
    time.sleep(sleep_ms / 1000.0)


def _update_claim_with_retry(table, claim_id, current_version, update_expr,
                              expr_attr_names, expr_attr_values, max_retries=3):
    """Optimistic locking DynamoDB 업데이트 + Exponential Backoff (Requirements 5.9, 5.10)"""
    for attempt in range(max_retries):
        try:
            table.update_item(
                Key={'claim_id': claim_id, 'version': current_version},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
                ConditionExpression='version = :expected_version'
            )
            return True
        except Exception as e:
            if 'ConditionalCheckFailedException' in str(e):
                if attempt < max_retries - 1:
                    _exponential_backoff_jitter(attempt)
                    # 최신 버전 다시 읽기
                    try:
                        resp = table.get_item(Key={'claim_id': claim_id, 'version': current_version})
                        item = resp.get('Item')
                        if item:
                            current_version = item.get('version', current_version)
                            expr_attr_values[':expected_version'] = current_version
                    except Exception:
                        pass
                    continue
                logger.error(f"Optimistic locking failed after {max_retries} retries: claim_id={claim_id}")
                return False
            raise
    return False


def _llm_evaluate_claim(bedrock_runtime, claim, prompt_template, model_id):
    """Foundation Model로 claim 정확성 평가 → score (0.0~1.0)"""
    try:
        prompt = prompt_template.format(
            statement=claim.get('statement', ''),
            evidence=json.dumps(claim.get('evidence', []), ensure_ascii=False, default=str),
            topic=claim.get('topic', '')
        )
        resp = bedrock_runtime.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 256,
                'messages': [{'role': 'user', 'content': prompt}]
            })
        )
        resp_body = json.loads(resp['body'].read())
        content_text = resp_body.get('content', [{}])[0].get('text', '0.5')
        # 숫자 추출
        score_match = re.search(r'(\d+\.?\d*)', content_text)
        if score_match:
            score = float(score_match.group(1))
            return max(0.0, min(1.0, score))
        return 0.5
    except Exception as e:
        logger.warning(f"LLM claim evaluation failed: {e}")
        return 0.5


def _rule_based_check(claim):
    """Rule-based checker → score_3 (0.0~1.0) (Requirements 11.4)
    - evidence S3 존재 확인
    - statement 10~500자
    - topic 형식 유효
    """
    checks_passed = 0
    total_checks = 3

    # 1) statement 길이 검증
    stmt = claim.get('statement', '')
    if 10 <= len(stmt) <= 500:
        checks_passed += 1

    # 2) topic 형식 유효성 (비어있지 않고 슬래시 구분 계층적 형식)
    topic = claim.get('topic', '')
    if topic and re.match(r'^[a-zA-Z0-9_\-]+(/[a-zA-Z0-9_\-]+)*$', topic):
        checks_passed += 1

    # 3) evidence S3 존재 확인
    evidence = claim.get('evidence', [])
    if evidence:
        evidence_valid = True
        for ev in evidence:
            source_doc = ev.get('source_document_id', '')
            if source_doc:
                try:
                    s3_client.head_object(Bucket=S3_BUCKET_SEOUL, Key=source_doc)
                except Exception:
                    evidence_valid = False
                    break
            else:
                evidence_valid = False
                break
        if evidence_valid:
            checks_passed += 1
    # evidence 없으면 해당 체크 실패

    return checks_passed / total_checks if total_checks > 0 else 0.0


def _compute_claim_similarity(stmt_a, stmt_b):
    """두 claim statement 간 단순 유사도 계산 (0.0~1.0)
    단어 기반 Jaccard 유사도 사용
    """
    words_a = set(stmt_a.lower().split())
    words_b = set(stmt_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def cross_check_claims(event, context):
    """Lambda Event 비동기 호출 — draft claim 교차 검증 (Requirements 11.1~11.10)
    3단계 Cross-Check:
      1차: Foundation_Model로 claim 정확성 평가 → score_1
      2차: 다른 프롬프트 템플릿으로 재검증 → score_2
      3차: rule-based checker → score_3
    validation_risk_score = 1.0 - (score_1 * 0.4 + score_2 * 0.4 + score_3 * 0.2)
    """
    topic = event.get('topic', '')
    if not topic:
        return {'error': 'topic is required', 'total_processed': 0}

    claims_verified = 0
    claims_conflicted = 0
    claims_pending = 0
    total_processed = 0

    table = dynamodb.Table(CLAIM_DB_TABLE)
    model_id = os.environ.get('FOUNDATION_MODEL_ARN', 'us.anthropic.claude-3-5-haiku-20241022-v1:0')

    try:
        bedrock_runtime = boto3.client('bedrock-runtime', region_name=BACKEND_REGION)

        # 지정 topic의 draft claim 조회 (topic-index GSI 사용)
        draft_claims = []
        query_params = {
            'IndexName': 'topic-index',
            'KeyConditionExpression': 'topic = :t',
            'FilterExpression': '#s = :draft_status',
            'ExpressionAttributeNames': {'#s': 'status'},
            'ExpressionAttributeValues': {
                ':t': topic,
                ':draft_status': 'draft'
            }
        }
        resp = table.query(**query_params)
        draft_claims.extend(resp.get('Items', []))
        while resp.get('LastEvaluatedKey'):
            query_params['ExclusiveStartKey'] = resp['LastEvaluatedKey']
            resp = table.query(**query_params)
            draft_claims.extend(resp.get('Items', []))

        if not draft_claims:
            return {
                'claims_verified': 0,
                'claims_conflicted': 0,
                'claims_pending': 0,
                'total_processed': 0
            }

        # 1차 검증 프롬프트 템플릿
        prompt_1 = """다음 claim의 정확성을 평가하세요.

Topic: {topic}
Statement: {statement}
Evidence: {evidence}

이 claim이 evidence에 의해 뒷받침되는 정도를 0.0~1.0 사이의 숫자로만 답하세요.
1.0은 완벽히 뒷받침됨, 0.0은 전혀 뒷받침되지 않음을 의미합니다.
숫자만 답하세요."""

        # 2차 검증 프롬프트 템플릿 (다른 관점)
        prompt_2 = """기술 문서 검증자로서 다음 claim을 검토하세요.

주제: {topic}
진술: {statement}
근거 자료: {evidence}

다음 기준으로 평가하세요:
- 진술이 근거 자료와 일치하는가?
- 기술적으로 정확한 표현인가?
- 모호하거나 오해의 소지가 있는 부분이 없는가?

정확도를 0.0~1.0 사이의 숫자로만 답하세요."""

        for claim in draft_claims:
            try:
                claim_id = claim.get('claim_id', '')
                current_version = claim.get('version', 1)

                # 1차: LLM 정확성 평가 → score_1
                score_1 = _llm_evaluate_claim(bedrock_runtime, claim, prompt_1, model_id)

                # 2차: 다른 프롬프트로 재검증 → score_2
                score_2 = _llm_evaluate_claim(bedrock_runtime, claim, prompt_2, model_id)

                # 3차: rule-based checker → score_3
                score_3 = _rule_based_check(claim)

                # validation_risk_score 계산 (Requirements 11.5)
                validation_risk_score = 1.0 - (score_1 * 0.4 + score_2 * 0.4 + score_3 * 0.2)
                now = datetime.utcnow().isoformat() + 'Z'

                if validation_risk_score < 0.3:
                    # verified + confidence 업데이트 (Requirements 11.6)
                    new_confidence = Decimal(str(round(1.0 - validation_risk_score, 4)))
                    _update_claim_with_retry(
                        table, claim_id, current_version,
                        'SET #s = :new_status, confidence = :conf, last_verified_at = :now, approval_status = :pending',
                        {'#s': 'status'},
                        {
                            ':new_status': 'verified',
                            ':conf': new_confidence,
                            ':now': now,
                            ':pending': 'pending_review',
                            ':expected_version': current_version
                        }
                    )
                    claims_verified += 1
                    logger.info(json.dumps({
                        'event': 'claim_verified',
                        'claim_id': claim_id,
                        'validation_risk_score': validation_risk_score,
                        'scores': {'s1': score_1, 's2': score_2, 's3': score_3}
                    }))

                elif validation_risk_score < 0.7:
                    # draft 유지 + 수동 검토 경고 (Requirements 11.7)
                    claims_pending += 1
                    logger.warning(json.dumps({
                        'event': 'claim_manual_review_needed',
                        'claim_id': claim_id,
                        'validation_risk_score': validation_risk_score,
                        'scores': {'s1': score_1, 's2': score_2, 's3': score_3}
                    }))

                else:
                    # conflicted + ERROR 로그 (Requirements 11.8)
                    _update_claim_with_retry(
                        table, claim_id, current_version,
                        'SET #s = :new_status, last_verified_at = :now',
                        {'#s': 'status'},
                        {
                            ':new_status': 'conflicted',
                            ':now': now,
                            ':expected_version': current_version
                        }
                    )
                    claims_conflicted += 1
                    logger.error(json.dumps({
                        'event': 'claim_conflicted',
                        'claim_id': claim_id,
                        'validation_risk_score': validation_risk_score,
                        'scores': {'s1': score_1, 's2': score_2, 's3': score_3}
                    }))

                total_processed += 1

            except Exception as e:
                logger.error(f"Cross-check failed for claim {claim.get('claim_id', 'unknown')}: {e}")
                total_processed += 1

        # 중복 감지: 동일 topic verified claim 간 유사도 >= 0.9 (Requirements 11.10)
        try:
            verified_query = {
                'IndexName': 'topic-index',
                'KeyConditionExpression': 'topic = :t',
                'FilterExpression': '#s = :verified_status',
                'ExpressionAttributeNames': {'#s': 'status'},
                'ExpressionAttributeValues': {
                    ':t': topic,
                    ':verified_status': 'verified'
                }
            }
            v_resp = table.query(**verified_query)
            verified_claims = v_resp.get('Items', [])

            # 유사도 비교 — O(n^2) 이지만 topic 단위이므로 규모 제한적
            seen_deprecated = set()
            for i in range(len(verified_claims)):
                if verified_claims[i]['claim_id'] in seen_deprecated:
                    continue
                for j in range(i + 1, len(verified_claims)):
                    if verified_claims[j]['claim_id'] in seen_deprecated:
                        continue
                    sim = _compute_claim_similarity(
                        verified_claims[i].get('statement', ''),
                        verified_claims[j].get('statement', '')
                    )
                    if sim >= 0.9:
                        # 최신 유지, 이전 deprecated
                        ts_i = verified_claims[i].get('created_at', '')
                        ts_j = verified_claims[j].get('created_at', '')
                        if ts_i >= ts_j:
                            older = verified_claims[j]
                        else:
                            older = verified_claims[i]
                        now = datetime.utcnow().isoformat() + 'Z'
                        _update_claim_with_retry(
                            table, older['claim_id'], older.get('version', 1),
                            'SET #s = :dep_status, last_verified_at = :now',
                            {'#s': 'status'},
                            {
                                ':dep_status': 'deprecated',
                                ':now': now,
                                ':expected_version': older.get('version', 1)
                            }
                        )
                        seen_deprecated.add(older['claim_id'])
                        logger.info(json.dumps({
                            'event': 'duplicate_claim_deprecated',
                            'deprecated_claim_id': older['claim_id'],
                            'similarity': sim
                        }))
        except Exception as e:
            logger.warning(f"Duplicate detection failed: {e}")

        result = {
            'claims_verified': claims_verified,
            'claims_conflicted': claims_conflicted,
            'claims_pending': claims_pending,
            'total_processed': total_processed
        }

        logger.info(json.dumps({'event': 'cross_check_claims_complete', **result}))

        # KPI 메트릭 발행 (Requirements 15.3)
        try:
            cw = boto3.client('cloudwatch', region_name='ap-northeast-2')
            if total_processed > 0:
                _publish_metric(cw, 'ClaimVerificationPassRate',
                                (claims_verified / total_processed) * 100, 'Percent')
                _publish_metric(cw, 'ContradictionDetectionRate',
                                (claims_conflicted / total_processed) * 100, 'Percent')
        except Exception as metric_err:
            logger.warning(f"KPI metric publish failed after cross_check: {metric_err}")

        return result

    except Exception as e:
        logger.error(f"cross_check_claims failed: {e}", exc_info=True)
        return {
            'error': str(e),
            'claims_verified': claims_verified,
            'claims_conflicted': claims_conflicted,
            'claims_pending': claims_pending,
            'total_processed': total_processed
        }


# ============================================================================
# KPI Metrics 발행 (Task 9.5)
# Requirements: 15.1~15.7
# ============================================================================

def publish_kpi_metrics(metrics):
    """CloudWatch 커스텀 메트릭 일괄 발행 (네임스페이스: BOS-AI/ClaimDB)
    Requirements: 15.1~15.7

    metrics: dict — 메트릭 이름 → (값, 단위) 매핑
    예: {'ClaimIngestionSuccessRate': (95.0, 'Percent'), ...}

    지원 메트릭:
      - ClaimIngestionSuccessRate: (claims_created / (claims_created + documents_failed)) * 100
      - ClaimVerificationPassRate: (claims_verified / total_processed) * 100
      - ContradictionDetectionRate: (claims_conflicted / total_processed) * 100
      - BedrockKBFallbackRate: 폴백 발생 시 1 증가 (Count)
      - AvgEvidenceCountPerAnswer: 사용된 claim의 evidence 수 평균 (Count)
      - StaleClaimRatio: 30일 미검증 verified claim 비율 (Percent)
      - TopicCoverageRatio: verified claim 존재 topic 비율 (Percent)
    """
    if not metrics:
        return

    try:
        cw = boto3.client('cloudwatch', region_name='ap-northeast-2')
        for metric_name, (value, unit) in metrics.items():
            _publish_metric(cw, metric_name, value, unit)
        logger.info(f"Published {len(metrics)} KPI metrics to BOS-AI/ClaimDB")
    except Exception as e:
        logger.warning(f"publish_kpi_metrics failed: {e}")


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
