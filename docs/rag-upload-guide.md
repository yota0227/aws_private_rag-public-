# BOS-AI RAG 문서 업로드 가이드

## 1. 개요

BOS-AI RAG 시스템은 사내 문서를 업로드하면 자동으로 AI가 검색·활용할 수 있는 형태로 변환(임베딩)합니다.

**데이터 흐름:**
```
웹 UI에서 파일 선택 → Seoul S3 업로드 → Virginia S3 자동 복제 → Bedrock KB 임베딩
```

업로드된 문서는 RAG 질의 시 AI가 참조하는 지식 베이스로 활용됩니다.

---

## 2. 접속 방법

브라우저에서 아래 URL로 접속합니다 (사내 네트워크 필수):

```
https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag/upload
```

> ⚠️ 사내 VPN 또는 사내 네트워크에 연결된 상태에서만 접근 가능합니다.

---

## 3. 업로드 절차

### Step 1: 팀 선택
- 화면 상단의 **팀 (Team)** 드롭다운에서 소속 팀을 선택합니다.
- 현재 등록된 팀: `SoC`

### Step 2: 카테고리 선택
- **카테고리 (Category)** 드롭다운에서 문서 유형을 선택합니다.
- `code` — RTL/SW 소스 코드, 테스트벤치, 스크립트 등
- `spec` — 설계 스펙, 아키텍처 문서, 데이터시트, 매뉴얼 등

### Step 3: 파일 선택
- 드래그 앤 드롭 또는 클릭하여 파일을 선택합니다.
- 여러 파일을 한 번에 선택할 수 있습니다.

### Step 4: 업로드 시작
- **업로드 시작** 버튼을 클릭합니다.
- 각 파일의 진행률이 표시됩니다.
- 완료 시 KB sync 상태가 표시됩니다.

### 지원 파일 형식
| 형식 | 확장자 | 용도 |
|------|--------|------|
| PDF | `.pdf` | 스펙 문서, 데이터시트 |
| 텍스트 | `.txt` | 코드, 로그, 설정 파일 |
| Word | `.docx` | 설계 문서, 보고서 |
| CSV | `.csv` | 테스트 결과, 데이터 |
| HTML | `.html` | 웹 문서 |
| Markdown | `.md` | 기술 문서 |

---

## 4. 업로드 후 처리 과정

업로드 완료 후 자동으로 다음 과정이 진행됩니다:

```
1. Seoul S3 저장 (즉시)
   └─ documents/soc/code/파일명 또는 documents/soc/spec/파일명

2. Virginia S3 복제 (약 5~15분)
   └─ Cross-Region Replication으로 자동 복제

3. Bedrock KB 임베딩 (약 10~30분, 문서 크기에 따라 다름)
   └─ 문서를 벡터로 변환하여 검색 가능한 상태로 저장
```

> 임베딩 완료까지 최대 30분 정도 소요될 수 있습니다.

---

## 5. 문서 목록 확인

업로드 페이지 하단에서 업로드된 문서 목록을 확인할 수 있습니다.
- **전체 팀** / **전체 카테고리** 필터로 원하는 문서만 조회 가능

---

## 6. 팀/카테고리 분류 기준

### 왜 분류가 필요한가?
RAG 질의 시 모든 문서를 검색하면 불필요한 컨텍스트가 포함되어 답변 품질이 떨어집니다.
팀/카테고리로 분류하면 질의 시 관련 문서만 검색하여 정확도를 높일 수 있습니다.

### S3 저장 구조
```
bos-ai-documents-seoul-v3/
  documents/
    soc/
      code/     ← RTL 코드, 테스트벤치, SW 코드
      spec/     ← 설계 스펙, 아키텍처 문서
```

### 분류 가이드
| 카테고리 | 이런 파일을 올려주세요 | 이런 파일은 아닙니다 |
|----------|----------------------|---------------------|
| `code` | RTL 소스(.v, .sv), C/C++ 코드, Python 스크립트, 테스트벤치, Makefile | 설계 문서, 회의록 |
| `spec` | 마이크로아키텍처 스펙, IP 데이터시트, 인터페이스 정의서, 설계 리뷰 문서 | 소스 코드 파일 |

---

## 7. 새 팀/카테고리 추가 방법 (관리자용)

새로운 팀이나 카테고리를 추가하려면 Lambda 코드의 `TEAMS` 딕셔너리를 수정합니다.

### 파일 위치
```
environments/app-layer/bedrock-rag/lambda_src/index.py
```

### 현재 설정
```python
TEAMS = {
    'soc': {'name': 'SoC', 'categories': ['code', 'spec']}
}
```

### 예시: SW팀 추가
```python
TEAMS = {
    'soc': {'name': 'SoC', 'categories': ['code', 'spec']},
    'sw':  {'name': 'SW',  'categories': ['code', 'spec', 'design']}
}
```

### 예시: SoC팀에 카테고리 추가
```python
TEAMS = {
    'soc': {'name': 'SoC', 'categories': ['code', 'spec', 'verification']}
}
```

### 수정 후 배포 절차
```bash
# 1. 코드 패키징
cp environments/app-layer/bedrock-rag/lambda_src/index.py index.py
zip lambda-deploy.zip index.py

# 2. Lambda 배포
aws lambda update-function-code \
  --function-name lambda-document-processor-seoul-prod \
  --zip-file fileb://lambda-deploy.zip \
  --profile mgmt

# 3. 정리
rm index.py lambda-deploy.zip
```

> 웹 UI는 Lambda에서 팀/카테고리 목록을 동적으로 가져오므로, Lambda만 배포하면 UI에 자동 반영됩니다.

---

## 8. 주의사항

- 동일한 파일명으로 같은 팀/카테고리에 재업로드하면 기존 파일을 덮어씁니다.
- 대용량 파일은 자동으로 분할 업로드(multipart)됩니다.
- 업로드 중 브라우저를 닫지 마세요.
- 민감한 정보(개인정보, 보안 키 등)가 포함된 파일은 업로드하지 마세요.

---

## 9. 문의

시스템 관련 문의: AI 인프라팀
