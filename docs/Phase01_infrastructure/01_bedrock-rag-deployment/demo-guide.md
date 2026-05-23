# BOS-AI RAG 시스템 시연 가이드

## 📋 시스템 개요

**아키텍처:**
- 서울 리전: VPC 엔드포인트, S3 (사용자 업로드)
- 버지니아 리전: Bedrock KB, OpenSearch Serverless, Lambda, S3 (데이터 소스)
- VPC 피어링: 서울 ↔ 버지니아 (10.200.0.0/16 ↔ 10.20.0.0/16)

---

## 🔗 Bedrock Knowledge Base 엔드포인트 정보

### Knowledge Base ID
```
FNNOP3VBZV
```

### Knowledge Base ARN
```
arn:aws:bedrock:us-east-1:533335672315:knowledge-base/FNNOP3VBZV
```

### 리전
```
us-east-1 (버지니아)
```

### 임베딩 모델
```
amazon.titan-embed-text-v1
```

### OpenSearch 컬렉션
```
Collection ID: iw3pzcloa0en8d90hh7
Endpoint: https://iw3pzcloa0en8d90hh7.us-east-1.aoss.amazonaws.com
Index: bedrock-knowledge-base-index
```

---

## 🤖 Obot 연결 방법

### 1. Bedrock Agent Runtime API 사용

**엔드포인트:**
```
https://bedrock-agent-runtime.us-east-1.amazonaws.com
```

**API 호출 예시 (Python):**
```python
import boto3

# Bedrock Agent Runtime 클라이언트 생성
client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

# Knowledge Base 쿼리
response = client.retrieve_and_generate(
    input={
        'text': '여기에 질문을 입력하세요'
    },
    retrieveAndGenerateConfiguration={
        'type': 'KNOWLEDGE_BASE',
        'knowledgeBaseConfiguration': {
            'knowledgeBaseId': 'FNNOP3VBZV',
            'modelArn': 'arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2'
        }
    }
)

print(response['output']['text'])
```

**API 호출 예시 (AWS CLI):**
```bash
aws bedrock-agent-runtime retrieve-and-generate \
  --region us-east-1 \
  --input '{"text":"AWS Lambda에 대해 설명해주세요"}' \
  --retrieve-and-generate-configuration '{
    "type": "KNOWLEDGE_BASE",
    "knowledgeBaseConfiguration": {
      "knowledgeBaseId": "FNNOP3VBZV",
      "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2"
    }
  }'
```

### 2. 서울 VPC 엔드포인트를 통한 접근

서울 VPC 내부에서 접근 시 VPC 엔드포인트 사용:
```
vpce-xxxxx.bedrock-agent-runtime.ap-northeast-2.vpce.amazonaws.com
```

---

## 📤 S3 파일 업로드 가이드

### 방법 1: AWS CLI 사용 (추천)

#### 서울 S3 버킷에 업로드 (사용자 업로드용)
```bash
# 단일 파일 업로드
aws s3 cp your-document.pdf s3://bos-ai-documents-seoul/

# 폴더 전체 업로드
aws s3 cp ./documents/ s3://bos-ai-documents-seoul/ --recursive

# 특정 확장자만 업로드
aws s3 cp ./documents/ s3://bos-ai-documents-seoul/ --recursive --exclude "*" --include "*.pdf"
```

#### 버지니아 S3 버킷에 직접 업로드 (임베딩용)
```bash
# 단일 파일 업로드
aws s3 cp your-document.pdf s3://bos-ai-documents-us/

# 폴더 전체 업로드
aws s3 cp ./documents/ s3://bos-ai-documents-us/ --recursive
```

### 방법 2: AWS Console 사용

1. AWS Console 로그인
2. S3 서비스로 이동
3. 버킷 선택:
   - 서울: `bos-ai-documents-seoul`
   - 버지니아: `bos-ai-documents-us`
4. "Upload" 버튼 클릭
5. 파일 선택 후 업로드

### 방법 3: Python boto3 사용

```python
import boto3

s3 = boto3.client('s3', region_name='ap-northeast-2')

# 서울 버킷에 업로드
s3.upload_file(
    'local-file.pdf',
    'bos-ai-documents-seoul',
    'documents/local-file.pdf'
)

# 버지니아 버킷에 업로드 (임베딩용)
s3_us = boto3.client('s3', region_name='us-east-1')
s3_us.upload_file(
    'local-file.pdf',
    'bos-ai-documents-us',
    'documents/local-file.pdf'
)
```

---

## 🔄 Knowledge Base 동기화

파일 업로드 후 Knowledge Base에 반영하려면 동기화 필요:

### AWS CLI로 동기화
```bash
# 동기화 시작
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id FNNOP3VBZV \
  --data-source-id 211WMHQAOK \
  --region us-east-1

# 동기화 상태 확인
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id FNNOP3VBZV \
  --data-source-id 211WMHQAOK \
  --region us-east-1 \
  --max-results 1
```

### Python으로 동기화
```python
import boto3

client = boto3.client('bedrock-agent', region_name='us-east-1')

# 동기화 시작
response = client.start_ingestion_job(
    knowledgeBaseId='FNNOP3VBZV',
    dataSourceId='211WMHQAOK'
)

print(f"Ingestion Job ID: {response['ingestionJob']['ingestionJobId']}")
print(f"Status: {response['ingestionJob']['status']}")
```

---

## 🧪 시연 시나리오

### 1. 파일 업로드
```bash
# 테스트 문서 업로드
echo "AWS Lambda는 서버리스 컴퓨팅 서비스입니다." > test-doc.txt
aws s3 cp test-doc.txt s3://bos-ai-documents-us/demo/test-doc.txt
```

### 2. Knowledge Base 동기화
```bash
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id FNNOP3VBZV \
  --data-source-id 211WMHQAOK \
  --region us-east-1
```

### 3. 쿼리 테스트
```bash
aws bedrock-agent-runtime retrieve-and-generate \
  --region us-east-1 \
  --input '{"text":"Lambda에 대해 설명해주세요"}' \
  --retrieve-and-generate-configuration '{
    "type": "KNOWLEDGE_BASE",
    "knowledgeBaseConfiguration": {
      "knowledgeBaseId": "FNNOP3VBZV",
      "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-v2"
    }
  }'
```

---

## 📊 시연 체크리스트

- [ ] VPC 피어링 상태 확인 (ACTIVE)
- [ ] OpenSearch 컬렉션 상태 확인 (ACTIVE)
- [ ] Bedrock KB 상태 확인 (ACTIVE)
- [ ] S3 버킷 접근 가능 확인
- [ ] 테스트 문서 업로드
- [ ] Knowledge Base 동기화
- [ ] 쿼리 테스트 성공
- [ ] Obot 연결 테스트

---

## 🔧 트러블슈팅

### 권한 오류 발생 시
```bash
# IAM Role 확인
aws iam get-role --role-name bos-ai-bedrock-kb-role-dev

# S3 버킷 정책 확인
aws s3api get-bucket-policy --bucket bos-ai-documents-us
```

### 동기화 실패 시
```bash
# 최근 동기화 작업 상태 확인
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id FNNOP3VBZV \
  --data-source-id 211WMHQAOK \
  --region us-east-1 \
  --max-results 5
```

### 연결 테스트
```bash
# VPC 피어링 확인
aws ec2 describe-vpc-peering-connections \
  --vpc-peering-connection-ids pcx-06599e9d9a3fe573f \
  --region ap-northeast-2

# OpenSearch 상태 확인
aws opensearchserverless batch-get-collection \
  --ids iw3pzcloa0en8d90hh7 \
  --region us-east-1
```

---

## 📞 지원 정보

- **Knowledge Base ID**: FNNOP3VBZV
- **Data Source ID**: 211WMHQAOK
- **OpenSearch Collection ID**: iw3pzcloa0en8d90hh7
- **리전**: us-east-1 (버지니아)
- **S3 버킷 (서울)**: bos-ai-documents-seoul
- **S3 버킷 (버지니아)**: bos-ai-documents-us

---

**시연 성공을 기원합니다! 🎉**
