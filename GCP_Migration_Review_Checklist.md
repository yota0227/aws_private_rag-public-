# BOS-AI Private RAG — GCP 전환 검토 체크리스트

> Google Cloud 영업팀 전달용. Gemini Enterprise + Vertex AI 기반 구현 가능 여부 확인 요청.
> 작성일: 2026-03-31

---

## 1. 보안 요건

| # | 필수 요건 | 확인 요청 사항 |
|---|----------|--------------|
| S-1 | 완전 Air-Gapped 네트워크 | IGW/NAT 없이 Private Service Connect만으로 AI 서비스(Vertex AI, 벡터DB, 스토리지) 전체 접근이 가능한가? |
| S-2 | 온프레미스 VPN 하이브리드 연결 | IPsec VPN으로 온프레미스(192.128.0.0/16)와 GCP VPC를 연결하고, 다수 VPC + VPN을 허브로 묶는 구성이 가능한가? |
| S-3 | 멀티 리전 Private 통신 | 서울 ↔ 미국 리전 간 인터넷을 경유하지 않는 Private 통신 경로가 보장되는가? (GCP Global VPC 특성 활용 가능 여부) |
| S-4 | Private DNS + 온프레미스 조건부 포워딩 | Private DNS Zone + DNS Forwarding으로 온프레미스에서 특정 도메인만 GCP 내부 IP로 해석하는 구성이 가능한가? |
| S-5 | 고객 관리형 암호화 키 (CMEK) | 스토리지, AI 서비스, 벡터DB 전체에 CMEK 적용이 가능한가? |
| S-6 | VPC Service Controls (데이터 유출 방지) | AI 서비스와 스토리지를 보안 경계(Perimeter)로 묶어 데이터 유출을 원천 차단할 수 있는가? |
| S-7 | 서비스별 최소 권한 IAM | 서비스 컴포넌트마다 별도 Service Account + 리소스 수준 권한 제한이 가능한가? |
| S-8 | 중앙 ID 관리 + SCIM/OIDC | Cloud Identity를 중앙 IdP로 SAML SSO + SCIM 자동 프로비저닝 + OIDC JIT 프로비저닝이 가능한가? |
| S-9 | IP 기반 WAF + API 인증 | Cloud Armor IP 제한 + API Key + HMAC 서명 검증으로 웹훅 보안이 가능한가? |
| S-10 | 전체 API 감사 로깅 + 네트워크 트래픽 로깅 | 모든 API 호출 감사 로그 + VPC Flow Logs가 지원되는가? |

---

## 2. 기능 요건

| # | 필수 요건 | 확인 요청 사항 |
|---|----------|--------------|
| F-1 | 관리형 RAG 오케스트레이션 | 데이터 소스 연결 → 자동 임베딩 → 검색+생성 통합 API를 하나의 관리형 서비스로 제공하는가? |
| F-2 | Serverless 벡터 데이터베이스 | HNSW 기반 벡터 검색을 Serverless로 제공하며, VPC 내부에서만 접근 가능한 구성이 되는가? |
| F-3 | Hybrid Search (시맨틱 + 키워드) | 벡터 유사도 검색과 키워드 텍스트 매칭을 결합한 Hybrid Search가 지원되는가? |
| F-4 | 메타데이터 기반 검색 필터링 | 문서에 부착된 메타데이터(팀, 카테고리, ASPICE 프로세스 등)로 검색 결과를 필터링할 수 있는가? |
| F-5 | 커스텀 청킹 (RTL 코드 구조 보존) | 문서 유형별(RTL 코드, 스펙, 다이어그램) 커스텀 청킹 전략을 적용할 수 있는가? |
| F-6 | 크로스 리전 자동 데이터 복제 | 서울 → 미국 리전으로 오브젝트 스토리지 자동 복제 (15분 이내 SLA)가 가능한가? |
| F-7 | 이벤트 기반 서버리스 파이프라인 | 스토리지 이벤트 → 서버리스 함수 → AI 수집 작업 트리거의 이벤트 드리븐 파이프라인이 가능한가? |
| F-8 | Private API Gateway | VPC 내부에서만 접근 가능한 Private REST API + 접근 정책 제한이 가능한가? |
| F-9 | Private BI 서비스 | BI 도구를 완전 Private 환경에서 운영하고, 벡터DB와 RAG API에 VPC 내부 경로로 연결 가능한가? |
| F-10 | 비동기 작업 처리 + 상태 추적 | 메시지 큐 + 서버리스 함수 + NoSQL 상태 추적 + DLQ 패턴이 가능한가? |
| F-11 | Signed URL 직접 업로드 | Private 네트워크(VPC Service Controls) 환경에서도 Signed URL을 통한 클라이언트 직접 업로드가 동작하는가? |
| F-12 | IaC (Terraform) 완전 지원 | 위 모든 서비스를 Terraform Google Provider로 100% 프로비저닝 가능한가? |

---

## 3. AI 활용 Use Case

| # | Use Case | 확인 요청 사항 |
|---|----------|--------------|
| U-1 | 반도체 RTL/설계 문서 RAG 질의 | Gemini가 한국어 + Verilog/SystemVerilog RTL 코드 + 반도체 설계 스펙을 이해하고 정확한 답변을 생성할 수 있는가? PoC 제공 가능한가? |
| U-2 | ASPICE 프로세스 기반 문서 검색 | "SWE.1 요구사항 분석 관련 문서 보여줘" 같은 자연어 질의에서 ASPICE 메타데이터 필터링 검색이 가능한가? |
| U-3 | CodeBeamer ALM 문서 자동 수집 | 온프레미스 CodeBeamer에서 VPN을 통해 문서를 수집하고 RAG에 자동 반영하는 파이프라인 구성이 가능한가? |
| U-4 | RAG 검색 품질 모니터링 | 검색 응답 시간, 인용 수, no-citation 비율 등을 BI 대시보드로 시각화 + 이상 감지 알림이 가능한가? |
| U-5 | LLM 서비스 라이선스 자동 관리 | 승인 → IdP 그룹 관리 → SaaS SCIM 프로비저닝 → 드리프트 감지까지 엔드투엔드 자동화가 가능한가? |
| U-6 | 멀티모달 문서 처리 | 반도체 회로도/블록 다이어그램이 포함된 PDF에서 텍스트+이미지를 함께 이해하는 멀티모달 RAG가 가능한가? |
| U-7 | 내부 문서 Grounding | Google Search Grounding이 아닌, 내부 문서만으로 Grounding하는 방식이 Private 환경에서 지원되는가? |

---

## 참고: 현재 아키텍처 요약

```
온프레미스(192.128.0.0/16) → VPN → 허브
  ├── 서울 Frontend VPC (10.10.0.0/16): API, 서버리스 함수, 서비스 엔드포인트
  ├── 서울 Logging VPC (10.200.0.0/16): 모니터링
  ├── 서울 DMZ VPC (10.30.0.0/16): RBAC 프로비저닝 (NAT 허용)
  └── 미국 Backend VPC (10.20.0.0/16): AI 모델, 벡터DB, 스토리지

문서: 온프렘 업로드 → 서울 스토리지 → 리전 복제 → 미국 스토리지 → AI 수집 → 벡터 인덱싱
질의: 온프렘 챗봇 → API → 서버리스 함수 → AI 검색+생성 → 응답
```

## 비용 비교 요청

현재 월 $787~$965 (Low), $1,760~$2,305 (Medium). 동일 워크로드 기준 GCP 비용 산출 요청:
- 문서 저장: 100GB / 500GB, 월간 질의: 10K / 50K, 임베딩: 1M / 5M 토큰/월
