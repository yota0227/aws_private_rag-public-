FROM node:22-alpine

WORKDIR /app

# 의존성 설치
COPY package.json package-lock.json* ./
RUN npm ci --only=production

# 애플리케이션 코드
COPY server.js .

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3100/health', (r) => process.exit(r.statusCode === 200 ? 0 : 1))"

# 포트 노출
EXPOSE 3100

# 실행
CMD ["node", "server.js"]
