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
import boto3
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET_SEOUL = os.environ.get('S3_BUCKET_SEOUL', 'bos-ai-documents-seoul-v3')
S3_PREFIX = 'documents/'
BEDROCK_KB_ID = os.environ.get('BEDROCK_KB_ID', '')
BEDROCK_KB_DATA_SOURCE_ID = os.environ.get('BEDROCK_KB_DATA_SOURCE_ID', '')
BACKEND_REGION = os.environ.get('BACKEND_REGION', 'us-east-1')

s3_client = boto3.client('s3', region_name='ap-northeast-2')


def handler(event, context):
    """Main Lambda handler for Private RAG API Gateway"""
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

        # 파일 목록
        if '/documents' in path and method == 'GET':
            return list_documents()

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

    if not filename:
        return response(400, {'error': 'filename is required'})

    key = f"{S3_PREFIX}{filename}"

    resp = s3_client.create_multipart_upload(
        Bucket=S3_BUCKET_SEOUL,
        Key=key,
        ContentType=content_type,
        ServerSideEncryption='aws:kms',
        Metadata={
            'uploaded-by': 'rag-web-ui',
            'upload-time': datetime.utcnow().isoformat()
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


def trigger_kb_sync():
    """Bedrock Knowledge Base 데이터 소스 동기화"""
    if not BEDROCK_KB_ID or not BEDROCK_KB_DATA_SOURCE_ID:
        return 'skipped - KB ID or Data Source ID not configured'

    try:
        bedrock_agent = boto3.client('bedrock-agent', region_name=BACKEND_REGION)
        resp = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=BEDROCK_KB_ID,
            dataSourceId=BEDROCK_KB_DATA_SOURCE_ID
        )
        job_id = resp['ingestionJob']['ingestionJobId']
        logger.info(f"KB sync started: job_id={job_id}")
        return f'sync started - job_id: {job_id}'
    except Exception as e:
        logger.error(f"KB sync failed: {str(e)}")
        return f'sync failed - {str(e)}'


# ============================================================================
# Document List & Query Handlers
# ============================================================================

def list_documents():
    """Seoul S3 버킷의 문서 목록 조회"""
    try:
        resp = s3_client.list_objects_v2(
            Bucket=S3_BUCKET_SEOUL,
            Prefix=S3_PREFIX,
            MaxKeys=100
        )

        files = []
        for obj in resp.get('Contents', []):
            if obj['Key'] == S3_PREFIX:
                continue
            files.append({
                'key': obj['Key'],
                'filename': obj['Key'].replace(S3_PREFIX, ''),
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
    """RAG 질의 처리"""
    body = parse_body(event)
    query = body.get('query', '')
    if not query:
        return response(400, {'error': 'query field is required'})

    if not BEDROCK_KB_ID:
        return response(200, {
            'message': 'RAG query endpoint ready - Bedrock KB ID not configured',
            'query': query
        })

    try:
        bedrock_runtime = boto3.client('bedrock-agent-runtime', region_name=BACKEND_REGION)
        resp = bedrock_runtime.retrieve_and_generate(
            input={'text': query},
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': BEDROCK_KB_ID,
                    'modelArn': os.environ.get('FOUNDATION_MODEL_ARN',
                        'arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2')
                }
            }
        )
        return response(200, {
            'answer': resp['output']['text'],
            'citations': [
                {
                    'text': c.get('generatedResponsePart', {}).get('textResponsePart', {}).get('text', ''),
                    'references': [
                        r.get('location', {}).get('s3Location', {}).get('uri', '')
                        for r in c.get('retrievedReferences', [])
                    ]
                }
                for c in resp.get('citations', [])
            ]
        })
    except Exception as e:
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
    """업로드 웹 UI HTML"""
    return '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BOS-AI RAG Document Upload</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center}
.container{max-width:700px;width:100%;padding:2rem}
h1{font-size:1.5rem;margin-bottom:.5rem;color:#38bdf8}
.subtitle{color:#94a3b8;margin-bottom:2rem;font-size:.9rem}
.drop-zone{border:2px dashed #334155;border-radius:12px;padding:3rem;text-align:center;cursor:pointer;transition:all .2s}
.drop-zone:hover,.drop-zone.dragover{border-color:#38bdf8;background:rgba(56,189,248,.05)}
.drop-zone p{color:#94a3b8;margin-top:.5rem}
.drop-zone .icon{font-size:2.5rem;margin-bottom:.5rem}
input[type=file]{display:none}
.file-list{margin-top:1.5rem}
.file-item{background:#1e293b;border-radius:8px;padding:1rem;margin-bottom:.75rem;display:flex;align-items:center;gap:1rem}
.file-info{flex:1;min-width:0}
.file-name{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.file-size{color:#64748b;font-size:.8rem}
.progress-bar{width:100%;height:6px;background:#334155;border-radius:3px;margin-top:.5rem;overflow:hidden}
.progress-fill{height:100%;background:#38bdf8;border-radius:3px;transition:width .3s;width:0}
.status{font-size:.75rem;margin-top:.25rem}
.status.uploading{color:#38bdf8}
.status.done{color:#4ade80}
.status.error{color:#f87171}
.btn{background:#38bdf8;color:#0f172a;border:none;padding:.75rem 1.5rem;border-radius:8px;font-weight:600;cursor:pointer;font-size:.9rem;margin-top:1rem;transition:background .2s}
.btn:hover{background:#7dd3fc}
.btn:disabled{background:#334155;color:#64748b;cursor:not-allowed}
.btn-remove{background:none;border:none;color:#64748b;cursor:pointer;font-size:1.2rem;padding:.25rem}
.btn-remove:hover{color:#f87171}
.doc-list{margin-top:2rem;border-top:1px solid #1e293b;padding-top:1.5rem}
.doc-list h2{font-size:1.1rem;color:#38bdf8;margin-bottom:1rem}
.doc-item{background:#1e293b;border-radius:8px;padding:.75rem 1rem;margin-bottom:.5rem;display:flex;justify-content:space-between;align-items:center}
.doc-item .name{font-size:.9rem}
.doc-item .meta{color:#64748b;font-size:.75rem}
.empty{color:#64748b;text-align:center;padding:1rem}
.toast{position:fixed;top:1rem;right:1rem;padding:1rem 1.5rem;border-radius:8px;font-size:.9rem;z-index:100;animation:slideIn .3s}
.toast.success{background:#065f46;color:#4ade80}
.toast.error{background:#7f1d1d;color:#f87171}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
</style>
</head>
<body>
<div class="container">
<h1>📄 BOS-AI RAG Document Upload</h1>
<p class="subtitle">파일을 업로드하면 자동으로 Seoul S3 → Virginia S3 → Bedrock KB로 임베딩됩니다</p>

<div class="drop-zone" id="dropZone">
  <div class="icon">📁</div>
  <p>파일을 드래그하거나 클릭하여 선택</p>
  <p style="font-size:.75rem;color:#475569">PDF, TXT, DOCX, CSV, HTML, MD 지원 | 제한 없음</p>
</div>
<input type="file" id="fileInput" multiple>

<div class="file-list" id="fileList"></div>
<button class="btn" id="uploadBtn" disabled onclick="startUpload()">업로드 시작</button>

<div class="doc-list">
  <h2>📋 업로드된 문서 목록</h2>
  <div id="docList"><div class="empty">로딩 중...</div></div>
</div>
</div>

<script>
const CHUNK_SIZE = 3.5 * 1024 * 1024; // 3.5MB (base64 인코딩 후 ~4.7MB, Lambda 6MB 제한 고려)
const API_BASE = window.location.pathname.replace(/\\/upload$/, '');
let pendingFiles = [];

// Drop zone
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  addFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', e => addFiles(e.target.files));

function addFiles(files) {
  for (const f of files) {
    if (!pendingFiles.find(p => p.name === f.name)) {
      pendingFiles.push(f);
    }
  }
  renderFileList();
}

function removeFile(idx) {
  pendingFiles.splice(idx, 1);
  renderFileList();
}

function renderFileList() {
  const el = document.getElementById('fileList');
  document.getElementById('uploadBtn').disabled = pendingFiles.length === 0;
  el.innerHTML = pendingFiles.map((f, i) => `
    <div class="file-item" id="file-${i}">
      <div class="file-info">
        <div class="file-name">${f.name}</div>
        <div class="file-size">${formatSize(f.size)}</div>
        <div class="progress-bar"><div class="progress-fill" id="prog-${i}"></div></div>
        <div class="status" id="status-${i}"></div>
      </div>
      <button class="btn-remove" onclick="removeFile(${i})" id="rm-${i}">✕</button>
    </div>
  `).join('');
}

async function startUpload() {
  document.getElementById('uploadBtn').disabled = true;
  document.querySelectorAll('.btn-remove').forEach(b => b.style.display = 'none');

  for (let i = 0; i < pendingFiles.length; i++) {
    await uploadFile(pendingFiles[i], i);
  }

  toast('모든 파일 업로드 완료', 'success');
  pendingFiles = [];
  setTimeout(() => { renderFileList(); loadDocuments(); }, 1500);
}

async function uploadFile(file, idx) {
  const statusEl = document.getElementById(`status-${idx}`);
  const progEl = document.getElementById(`prog-${idx}`);

  try {
    // 1. Initiate
    statusEl.className = 'status uploading';
    statusEl.textContent = '업로드 준비 중...';

    const initResp = await api('POST', '/documents/initiate', {
      filename: file.name,
      content_type: file.type || 'application/octet-stream'
    });

    const { upload_id, key } = initResp;
    const totalParts = Math.ceil(file.size / CHUNK_SIZE);
    const parts = [];

    // 2. Upload parts
    for (let partNum = 1; partNum <= totalParts; partNum++) {
      const start = (partNum - 1) * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunk = file.slice(start, end);
      const b64 = await toBase64(chunk);

      statusEl.textContent = `업로드 중... (${partNum}/${totalParts})`;

      const partResp = await api('POST', '/documents/upload-part', {
        upload_id, key,
        part_number: partNum,
        data: b64
      });

      parts.push({ PartNumber: partNum, ETag: partResp.etag });
      progEl.style.width = `${Math.round((partNum / totalParts) * 100)}%`;
    }

    // 3. Complete
    statusEl.textContent = '완료 처리 중...';
    const completeResp = await api('POST', '/documents/complete', {
      upload_id, key, parts
    });

    statusEl.className = 'status done';
    statusEl.textContent = `✓ 완료 (KB sync: ${completeResp.kb_sync || 'done'})`;
    progEl.style.width = '100%';
    progEl.style.background = '#4ade80';

  } catch (err) {
    statusEl.className = 'status error';
    statusEl.textContent = `✗ 오류: ${err.message}`;
    progEl.style.background = '#f87171';
  }
}

async function api(method, path, body) {
  const resp = await fetch(API_BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function toBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
  return (bytes / 1073741824).toFixed(1) + ' GB';
}

function toast(msg, type) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

async function loadDocuments() {
  try {
    const data = await api('GET', '/documents');
    const el = document.getElementById('docList');
    if (!data.files || data.files.length === 0) {
      el.innerHTML = '<div class="empty">업로드된 문서가 없습니다</div>';
      return;
    }
    el.innerHTML = data.files.map(f => `
      <div class="doc-item">
        <span class="name">${f.filename}</span>
        <span class="meta">${formatSize(f.size)} | ${new Date(f.last_modified).toLocaleString('ko-KR')}</span>
      </div>
    `).join('');
  } catch (err) {
    document.getElementById('docList').innerHTML = '<div class="empty">목록 조회 실패</div>';
  }
}

// 페이지 로드 시 문서 목록 조회
loadDocuments();
</script>
</body>
</html>'''
