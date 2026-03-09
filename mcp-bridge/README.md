# BOS-AI RAG MCP SSE Bridge

Obot에서 Seoul Private RAG API Gateway를 MCP tool로 사용하기 위한 SSE 브릿지입니다.

## 아키텍처

```
Obot (Docker) → MCP SSE Bridge (Docker) → Seoul Private API Gateway → Lambda → Virginia Bedrock KB
```

## 빠른 시작

### 1. Docker 이미지 빌드

```bash
cd mcp-bridge
docker build -t bos-ai-rag-mcp:latest .
```

### 2. 단독 실행 (테스트용)

```bash
docker run -d \
  --name bos-ai-rag-mcp \
  -p 3100:3100 \
  -e RAG_API_BASE=https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag \
  bos-ai-rag-mcp:latest
```

### 3. Docker Compose로 Obot과 함께 배포

기존 Obot docker-compose.yml에 다음을 추가:

```yaml
services:
  bos-ai-rag-mcp:
    build:
      context: ./mcp-bridge
      dockerfile: Dockerfile
    container_name: bos-ai-rag-mcp-bridge
    ports:
      - "3100:3100"
    environment:
      - PORT=3100
      - RAG_API_BASE=https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag
      - NODE_ENV=production
    restart: always
    networks:
      - obot-network
    healthcheck:
      test: ["CMD", "node", "-e", "require('http').get('http://localhost:3100/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1))"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s

networks:
  obot-network:
    external: true
```

그 다음:

```bash
docker-compose up -d
```

## Obot에 MCP Server 등록

1. Obot 웹 UI → Model Providers → Custom MCP Server
2. Server Type: **Remote Server**
3. URL: `http://bos-ai-rag-mcp-bridge:3100/sse` (Docker Compose 사용 시)
   또는 `http://localhost:3100/sse` (단독 실행 시)

## 사용 가능한 MCP Tools

### 1. rag_query
RAG 지식 베이스에 질의합니다.

**파라미터:**
- `query` (string): 질의 내용

**예시:**
```
Obot: "SoC의 RTL 코드에서 clock domain crossing 처리 방법을 설명해줘"
→ rag_query(query="clock domain crossing RTL implementation")
```

### 2. rag_list_documents
업로드된 문서 목록을 조회합니다.

**파라미터:**
- `team` (string, optional): 팀 필터 (예: soc)
- `category` (string, optional): 카테고리 필터 (예: code, spec)

**예시:**
```
Obot: "업로드된 SoC 코드 문서 목록을 보여줘"
→ rag_list_documents(team="soc", category="code")
```

### 3. rag_categories
등록된 팀/카테고리 목록을 조회합니다.

**파라미터:** 없음

**예시:**
```
Obot: "RAG에 어떤 팀/카테고리가 있어?"
→ rag_categories()
```

## 헬스체크

```bash
curl http://localhost:3100/health
```

응답:
```json
{
  "status": "ok",
  "ragApi": "https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag",
  "sessions": 0
}
```

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PORT` | 3100 | 브릿지 포트 |
| `RAG_API_BASE` | https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag | Seoul Private API Gateway 엔드포인트 |
| `NODE_ENV` | development | 실행 환경 (production 권장) |

## 로그 확인

```bash
# Docker 단독 실행
docker logs -f bos-ai-rag-mcp

# Docker Compose
docker-compose logs -f bos-ai-rag-mcp
```

## 트러블슈팅

### MCP 연결 실패
- 브릿지가 실행 중인지 확인: `curl http://localhost:3100/health`
- Seoul Private API Gateway 접근 가능 확인: `curl https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag/health`
- Docker 네트워크 확인: `docker network ls`

### 느린 응답
- RAG API 응답 시간 확인 (임베딩 검색 + LLM 생성 시간)
- Lambda 타임아웃 설정 확인 (현재 300초)

## 빌드 및 배포

### 이미지 빌드 및 푸시 (선택사항)

```bash
# Docker Hub에 푸시
docker build -t your-registry/bos-ai-rag-mcp:latest .
docker push your-registry/bos-ai-rag-mcp:latest
```

### Kubernetes 배포 (선택사항)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: bos-ai-rag-mcp
spec:
  replicas: 1
  selector:
    matchLabels:
      app: bos-ai-rag-mcp
  template:
    metadata:
      labels:
        app: bos-ai-rag-mcp
    spec:
      containers:
      - name: bos-ai-rag-mcp
        image: bos-ai-rag-mcp:latest
        ports:
        - containerPort: 3100
        env:
        - name: PORT
          value: "3100"
        - name: RAG_API_BASE
          value: "https://r0qa9lzhgi.execute-api.ap-northeast-2.amazonaws.com/dev/rag"
        - name: NODE_ENV
          value: "production"
        livenessProbe:
          httpGet:
            path: /health
            port: 3100
          initialDelaySeconds: 5
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 3100
          initialDelaySeconds: 5
          periodSeconds: 10
```

## 라이선스

BOS-AI Project
