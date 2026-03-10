# 요구사항 문서: 다중 파일/디렉토리 업로드

## 소개

BOS-AI RAG 시스템의 웹 UI에서 다중 파일 선택 및 디렉토리(폴더) 업로드를 지원하는 기능이다. 현재 시스템은 단일 파일 업로드만 가능하며, 다수의 문서를 한 번에 업로드하려면 파일을 하나씩 반복 선택해야 한다. 이 기능은 zip/tar.gz 압축 파일 업로드 방식과 웹 UI 다중 파일 선택 방식을 결합하여, 대량 문서를 효율적으로 업로드하고 Bedrock Knowledge Base에 임베딩할 수 있도록 한다.

아키텍트 리뷰를 반영하여 다음 사항을 개선하였다:
- API Gateway 29초 타임아웃 제약을 고려하여 압축 해제를 비동기 처리로 전환
- Lambda /tmp 디스크 용량을 1024MB(1GB)로 확대
- Pre-signed URL 업로드 방식을 도입하여 API Gateway 페이로드 제한 및 Base64 오버헤드 제거

## 용어 정의

- **Upload_UI**: `/rag/upload` 엔드포인트에서 제공되는 웹 기반 파일 업로드 인터페이스
- **Lambda_Processor**: `lambda-document-processor-seoul-prod` Lambda 함수 (Python 3.12, 3072MB /tmp 디스크, 300초 타임아웃)
- **DynamoDB_Table**: Extraction_Task 상태 추적용 DynamoDB 테이블 (task_id, status, 처리 결과 등을 실시간 기록·조회)
- **S3_Bucket**: Seoul 리전 S3 버킷 `bos-ai-documents-seoul-v3`, 경로 구조 `documents/{team}/{category}/{filename}`
- **API_Gateway**: Private REST API Gateway (`r0qa9lzhgi`), 요청당 페이로드 제한 약 10MB, 통합 타임아웃 29초
- **Pre_Signed_URL**: Lambda_Processor가 생성하는 S3 직접 업로드용 임시 서명 URL (유효기간 제한)
- **Multipart_Upload**: 대용량 파일을 3.5MB 청크로 분할하여 base64 인코딩 후 순차 전송하는 기존 업로드 메커니즘 (레거시, Pre_Signed_URL로 대체 예정)
- **Archive_File**: zip 또는 tar.gz 형식의 압축 파일
- **Extraction_Task**: 압축 해제 비동기 작업을 식별하는 고유 ID 기반 작업 단위
- **KB_Sync**: Bedrock Knowledge Base 데이터 소스 동기화 (ingestion job)
- **MCP_Bridge**: Obot 연동을 위한 MCP Streamable HTTP 브릿지 서버 (192.128.20.241:3100)
- **Team_Category**: 팀/카테고리 분류 체계 (예: `soc/code`, `soc/spec`)

## 요구사항

### 요구사항 1: 웹 UI 다중 파일 선택

**사용자 스토리:** 개발자로서, 웹 UI에서 여러 파일을 한 번에 선택하여 업로드하고 싶다. 그래야 반복적인 단일 파일 선택 작업 없이 대량 문서를 효율적으로 업로드할 수 있다.

#### 인수 조건

1. WHEN 사용자가 파일 선택 대화상자를 열면, THE Upload_UI SHALL 다중 파일 선택을 허용한다
2. WHEN 사용자가 드래그 앤 드롭 영역에 여러 파일을 드롭하면, THE Upload_UI SHALL 드롭된 모든 파일을 대기 목록에 추가한다
3. WHEN 사용자가 파일을 추가 선택하면, THE Upload_UI SHALL 기존 대기 목록에 새 파일을 병합하되 동일 파일명의 중복을 방지한다
4. THE Upload_UI SHALL 대기 목록에 있는 각 파일의 이름, 크기, 상태를 표시한다
5. WHEN 사용자가 대기 목록에서 개별 파일의 제거 버튼을 클릭하면, THE Upload_UI SHALL 해당 파일을 대기 목록에서 제거한다

### 요구사항 2: 디렉토리(폴더) 업로드

**사용자 스토리:** 개발자로서, 웹 UI에서 폴더를 통째로 선택하여 내부 파일을 일괄 업로드하고 싶다. 그래야 디렉토리 구조의 문서를 한 번에 처리할 수 있다.

#### 인수 조건

1. THE Upload_UI SHALL 디렉토리 선택 버튼을 파일 선택 버튼과 별도로 제공한다
2. WHEN 사용자가 디렉토리를 선택하면, THE Upload_UI SHALL 해당 디렉토리 내의 모든 파일을 재귀적으로 탐색하여 대기 목록에 추가한다
3. WHEN 사용자가 디렉토리를 드래그 앤 드롭 영역에 드롭하면, THE Upload_UI SHALL 해당 디렉토리 내의 모든 파일을 재귀적으로 탐색하여 대기 목록에 추가한다
4. WHILE 디렉토리 내 파일을 탐색하는 동안, THE Upload_UI SHALL 숨김 파일(`.`으로 시작하는 파일)과 시스템 파일(`__MACOSX`, `Thumbs.db`, `.DS_Store`)을 제외한다
5. THE Upload_UI SHALL 디렉토리에서 추가된 각 파일의 상대 경로를 파일명에 포함하여 표시한다 (예: `subdir/file.txt`)

### 요구사항 3: 압축 파일 업로드 및 비동기 자동 해제

**사용자 스토리:** 개발자로서, zip 또는 tar.gz 압축 파일을 업로드하면 Lambda에서 비동기로 압축을 해제하여 개별 파일로 S3에 저장하고 싶다. 그래야 API Gateway 타임아웃 제약 없이 대용량 압축 파일을 안정적으로 처리할 수 있다.

#### 인수 조건

1. WHEN 사용자가 zip 또는 tar.gz 형식의 Archive_File을 업로드하면, THE Lambda_Processor SHALL 해당 파일을 S3_Bucket의 임시 경로에 저장한 후 Extraction_Task를 생성하여 비동기 압축 해제를 시작한다
2. WHEN Archive_File의 압축 해제가 완료되면, THE Lambda_Processor SHALL 해제된 각 파일을 `documents/{team}/{category}/{filename}` 경로로 S3_Bucket에 개별 저장한다
3. WHILE Archive_File 내부에 하위 디렉토리가 존재하면, THE Lambda_Processor SHALL 하위 디렉토리 구조를 평탄화(flatten)하여 파일명만 사용하거나, 디렉토리 경로를 파일명 접두사로 변환한다 (예: `subdir/file.txt` → `subdir_file.txt`)
4. IF Archive_File의 압축 해제 후 총 크기가 Lambda_Processor의 `/tmp` 디스크 용량(3072MB)을 초과하면, THEN THE Lambda_Processor SHALL Extraction_Task 상태를 "실패"로 갱신하고 오류 사유를 DynamoDB_Table에 기록하며 임시 파일을 정리한다
5. IF Archive_File 내부에 지원하지 않는 파일 형식이 포함되어 있으면, THEN THE Lambda_Processor SHALL 해당 파일을 건너뛰고 처리 결과 요약에 건너뛴 파일 목록을 포함한다
6. WHEN Archive_File의 모든 파일 처리가 완료되면, THE Lambda_Processor SHALL Extraction_Task 상태를 "완료"로 DynamoDB_Table에 갱신하고 처리 결과 요약(성공 파일 수, 건너뛴 파일 수, 오류 파일 수)을 기록한다

### 요구사항 4: 순차 업로드 및 진행률 표시

**사용자 스토리:** 개발자로서, 다중 파일 업로드 시 각 파일의 업로드 진행률과 전체 진행 상황을 확인하고 싶다. 그래야 업로드 상태를 실시간으로 파악할 수 있다.

#### 인수 조건

1. WHEN 사용자가 업로드를 시작하면, THE Upload_UI SHALL 대기 목록의 파일을 순차적으로 하나씩 업로드한다
2. WHILE 파일 업로드가 진행되는 동안, THE Upload_UI SHALL 현재 파일의 청크 단위 진행률을 프로그레스 바로 표시한다
3. WHILE 다중 파일 업로드가 진행되는 동안, THE Upload_UI SHALL 전체 진행 상황을 "N/M 파일 완료" 형식으로 표시한다
4. WHEN 개별 파일 업로드가 완료되면, THE Upload_UI SHALL 해당 파일의 상태를 "완료"로 갱신하고 다음 파일의 업로드를 시작한다
5. IF 개별 파일 업로드 중 오류가 발생하면, THEN THE Upload_UI SHALL 해당 파일의 상태를 "오류"로 표시하고 나머지 파일의 업로드를 계속 진행한다
6. WHEN 모든 파일의 업로드가 완료되면, THE Upload_UI SHALL 전체 결과 요약(성공 수, 실패 수)을 토스트 메시지로 표시한다

### 요구사항 5: KB 동기화 최적화

**사용자 스토리:** 개발자로서, 다중 파일 업로드 시 Bedrock KB 동기화가 모든 파일 업로드 완료 후 한 번만 실행되기를 원한다. 그래야 불필요한 중복 동기화를 방지하고 시스템 리소스를 절약할 수 있다.

#### 인수 조건

1. WHILE 다중 파일 업로드가 진행되는 동안, THE Lambda_Processor SHALL 개별 파일 완료 시 KB_Sync를 트리거하지 않는다
2. WHEN 다중 파일 업로드의 마지막 파일이 완료되면, THE Lambda_Processor SHALL KB_Sync를 한 번 트리거한다
3. THE Upload_UI SHALL 업로드 완료 API 호출 시 `skip_sync` 파라미터를 포함하여 개별 파일의 KB_Sync 실행 여부를 제어한다
4. WHEN 압축 파일의 비동기 해제 처리가 완료되면, THE Lambda_Processor SHALL KB_Sync를 한 번 트리거한다

### 요구사항 6: 파일 유효성 검증

**사용자 스토리:** 개발자로서, 업로드 전에 파일의 형식과 크기가 유효한지 검증받고 싶다. 그래야 지원하지 않는 파일로 인한 업로드 실패를 사전에 방지할 수 있다.

#### 인수 조건

1. THE Upload_UI SHALL 지원 파일 형식을 PDF, TXT, DOCX, CSV, HTML, MD, zip, tar.gz로 제한한다
2. WHEN 사용자가 지원하지 않는 형식의 파일을 추가하면, THE Upload_UI SHALL 해당 파일을 대기 목록에 추가하지 않고 경고 메시지를 표시한다
3. IF 개별 파일의 크기가 100MB를 초과하면, THEN THE Upload_UI SHALL 해당 파일을 대기 목록에 추가하지 않고 크기 제한 초과 메시지를 표시한다
4. IF 압축 파일의 크기가 500MB를 초과하면, THEN THE Upload_UI SHALL 해당 파일을 대기 목록에 추가하지 않고 크기 제한 초과 메시지를 표시한다
5. WHEN 파일이 대기 목록에 추가되면, THE Upload_UI SHALL 파일 확장자를 기반으로 파일 유형 아이콘을 표시한다

### 요구사항 7: 압축 파일 비동기 처리 API 엔드포인트

**사용자 스토리:** 개발자로서, 압축 파일 업로드 완료 후 Lambda에서 비동기로 압축 해제 처리를 수행하는 전용 API 엔드포인트가 필요하다. 그래야 API Gateway의 29초 타임아웃 제약을 우회하여 대용량 압축 파일을 안정적으로 처리할 수 있다.

#### 인수 조건

1. THE API_Gateway SHALL `POST /rag/documents/extract` 엔드포인트를 제공한다
2. WHEN `/rag/documents/extract` 요청을 수신하면, THE Lambda_Processor SHALL 요청 본문에서 S3 키, 팀, 카테고리 정보를 추출하고 Extraction_Task ID를 생성하여 DynamoDB_Table에 초기 상태("대기중")로 기록한다
3. WHEN Extraction_Task ID가 생성되면, THE Lambda_Processor SHALL 비동기 호출(Event Invocation) 패턴 또는 SQS를 통해 실제 압축 해제 작업을 트리거하고, HTTP 202 Accepted 응답과 함께 `task_id`를 JSON 본문에 포함하여 즉시 반환한다
4. WHEN 비동기로 트리거된 압축 해제 작업이 시작되면, THE Lambda_Processor SHALL DynamoDB_Table의 Extraction_Task 상태를 "처리중"으로 갱신하고, S3_Bucket에서 Archive_File을 다운로드하여 `/tmp` 디렉토리에 압축을 해제한다
5. WHEN 압축 해제된 파일을 S3에 업로드 완료하면, THE Lambda_Processor SHALL 원본 Archive_File을 S3_Bucket에서 삭제하고 DynamoDB_Table의 Extraction_Task 상태를 "완료"로 갱신한다
6. THE API_Gateway SHALL `GET /rag/documents/extract-status` 엔드포인트를 제공한다
7. WHEN `/rag/documents/extract-status?task_id={task_id}` 요청을 수신하면, THE Lambda_Processor SHALL DynamoDB_Table에서 해당 Extraction_Task의 현재 상태(대기중, 처리중, 완료, 실패)와 처리 결과 요약을 조회하여 JSON 형식으로 반환한다
8. IF Extraction_Task 상태 조회 시 존재하지 않는 task_id가 전달되면, THEN THE Lambda_Processor SHALL HTTP 404 응답과 함께 오류 메시지를 반환한다

### 요구사항 8: MCP 브릿지 다중 업로드 도구

**사용자 스토리:** 개발자로서, MCP 브릿지를 통해 Obot에서 다중 파일 업로드 상태를 조회하고 싶다. 그래야 채팅 인터페이스에서도 업로드 현황을 확인할 수 있다.

#### 인수 조건

1. THE MCP_Bridge SHALL `rag_upload_status` 도구를 제공하여 최근 업로드 작업의 상태를 조회할 수 있도록 한다
2. WHEN `rag_upload_status` 도구가 호출되면, THE MCP_Bridge SHALL 최근 업로드된 파일 목록과 KB_Sync 상태를 반환한다
3. THE MCP_Bridge SHALL `rag_extract_status` 도구를 제공하여 Extraction_Task의 상태를 조회할 수 있도록 한다
4. WHEN `rag_extract_status` 도구가 task_id와 함께 호출되면, THE MCP_Bridge SHALL `GET /rag/documents/extract-status` 엔드포인트를 호출하여 해당 작업의 상태를 반환한다

### 요구사항 9: 업로드 완료 후 문서 목록 갱신

**사용자 스토리:** 개발자로서, 다중 파일 업로드 완료 후 문서 목록이 자동으로 갱신되기를 원한다. 그래야 업로드 결과를 즉시 확인할 수 있다.

#### 인수 조건

1. WHEN 모든 파일의 업로드가 완료되면, THE Upload_UI SHALL 문서 목록을 자동으로 다시 조회하여 갱신한다
2. WHEN 압축 파일의 Extraction_Task 상태가 "완료"로 확인되면, THE Upload_UI SHALL 문서 목록을 자동으로 다시 조회하여 갱신한다
3. THE Upload_UI SHALL 문서 목록 갱신 시 현재 선택된 팀/카테고리 필터를 유지한다
4. WHILE 압축 파일의 Extraction_Task가 "처리중" 상태인 동안, THE Upload_UI SHALL 5초 간격으로 `GET /rag/documents/extract-status` 엔드포인트를 폴링하여 상태를 갱신한다

### 요구사항 10: Pre-signed URL 기반 직접 업로드

**사용자 스토리:** 개발자로서, 파일을 API Gateway를 경유하지 않고 S3에 직접 업로드하고 싶다. 그래야 API Gateway의 10MB 페이로드 제한과 Base64 인코딩으로 인한 33% 데이터 오버헤드를 제거하고 업로드 성능을 개선할 수 있다.

#### 인수 조건

1. THE API_Gateway SHALL `POST /rag/documents/presign` 엔드포인트를 제공한다
2. WHEN `/rag/documents/presign` 요청을 수신하면, THE Lambda_Processor SHALL 요청 본문의 파일명, 팀, 카테고리 정보를 기반으로 S3_Bucket 대상 경로의 Pre_Signed_URL을 생성하여 반환한다
3. THE Lambda_Processor SHALL Pre_Signed_URL의 유효기간을 3600초(1시간)로 설정한다
4. WHEN Pre_Signed_URL을 수신하면, THE Upload_UI SHALL 해당 URL로 파일 바이너리를 HTTP PUT 요청으로 S3에 직접 업로드한다
5. WHEN Pre_Signed_URL을 통한 S3 직접 업로드가 완료되면, THE Upload_UI SHALL `POST /rag/documents/confirm` 엔드포인트를 호출하여 Lambda_Processor에 업로드 완료를 통지한다
6. WHEN `/rag/documents/confirm` 요청을 수신하면, THE Lambda_Processor SHALL 해당 파일의 메타데이터를 기록하고 후속 처리(압축 파일인 경우 Extraction_Task 생성)를 수행한다
7. IF Pre_Signed_URL 생성 요청 시 파일명 또는 팀/카테고리 정보가 누락되면, THEN THE Lambda_Processor SHALL HTTP 400 응답과 함께 누락된 필드를 명시하는 오류 메시지를 반환한다
8. IF Pre_Signed_URL의 유효기간이 만료된 후 업로드를 시도하면, THEN THE Upload_UI SHALL 새로운 Pre_Signed_URL을 자동으로 재요청하여 업로드를 재시도한다
