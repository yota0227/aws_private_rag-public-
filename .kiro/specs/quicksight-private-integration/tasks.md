# 구현 계획: Amazon Quick Private 통합

## 개요

기존 BOS-AI Private RAG 인프라에 Amazon Quick(QuickSight)을 완전 Private하게 통합한다.
배포는 기존 Terraform 레이어 구조를 준수하여 순서대로 진행한다:
Global IAM → Network Layer → App Layer → Lambda 소스 → MCP Bridge → OPA 정책 → 테스트.

## 태스크

- [x] 1. Global IAM 레이어 — Quick IAM 역할 및 Identity Center 그룹 생성
  - [x] 1.1 `environments/global/iam/`에 Quick IAM 역할 3개 추가
    - `role-quicksight-admin-bos-ai-seoul-prod`: Quick 계정/사용자/데이터소스 관리 권한
    - `role-quicksight-author-bos-ai-seoul-prod`: 대시보드 생성/편집, 데이터셋 조회 권한
    - `role-quicksight-viewer-bos-ai-seoul-prod`: 대시보드 조회 전용 권한
    - 모든 역할에 `aws:SourceIp`(192.128.0.0/16, 10.10.0.0/16) 및 `aws:sourceVpce` 조건 추가
    - 표준 태그(`Project`, `Environment`, `ManagedBy`, `Layer`) 적용
    - _요구사항: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 1.2 Property 13 속성 테스트 작성 — IAM 역할별 권한 분리 검증
    - **Property 13: Quick IAM 역할별 권한 분리**
    - **검증: 요구사항 9.1, 9.2, 9.3**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

  - [ ]* 1.3 Property 14 속성 테스트 작성 — IAM 역할 접근 조건 검증
    - **Property 14: Quick IAM 역할 접근 조건**
    - **검증: 요구사항 9.4, 9.5**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

  - [x] 1.4 `environments/global/iam/`에 IAM Identity Center 그룹 3개 추가
    - `QS_Admin_Users` → Quick ADMIN 역할 매핑
    - `QS_Author_Users` → Quick AUTHOR 역할 매핑
    - `QS_Viewer_Users` → Quick READER 역할 매핑
    - _요구사항: 2.6, 2.7_

  - [ ]* 1.5 Property 6 속성 테스트 작성 — GROUP_MAP 역할 매핑 검증
    - **Property 6: GROUP_MAP Quick 역할 매핑 정확성**
    - **검증: 요구사항 2.6, 2.7**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

- [x] 2. 체크포인트 — Global IAM 레이어 검증
  - `terraform validate && tflint` 실행하여 IAM 리소스 구성 확인
  - 모든 테스트 통과 여부 확인. 문제가 있으면 사용자에게 질문하세요.

- [x] 3. Network Layer — Quick VPC Endpoint, Security Group, Route53 DNS
  - [x] 3.1 `environments/network-layer/quicksight-security-groups.tf` 생성
    - `sg-quicksight-endpoints-bos-ai-seoul-prod` SG 생성
    - 인바운드: Seoul VPC CIDR(10.10.0.0/16) + 온프레미스 CIDR(192.128.0.0/16) → HTTPS(443)
    - 아웃바운드: 0.0.0.0/0 허용 금지, 명시적 CIDR만 허용
    - `sg-quicksight-vpc-conn-bos-ai-seoul-prod` SG 생성 (VPC Connection 전용)
    - VPC Connection SG 아웃바운드: Seoul VPC CIDR(10.10.0.0/16) HTTPS(443)만 허용, Virginia CIDR 직접 지정 금지
    - 표준 태그 적용
    - _요구사항: 1.3, 4.2, 4.3, 7.2_

  - [ ]* 3.2 Property 2 속성 테스트 작성 — SG 인바운드 규칙 CIDR/포트 제한 검증
    - **Property 2: Quick Security Group 인바운드 규칙 제한**
    - **검증: 요구사항 1.3, 4.3**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

  - [ ]* 3.3 Property 3 속성 테스트 작성 — VPC Connection SG Virginia 직접 접근 차단 검증
    - **Property 3: Quick VPC Connection Security Group Virginia 직접 접근 차단**
    - **검증: 요구사항 4.2, 4.5, 7.2**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

  - [x] 3.4 `environments/network-layer/quicksight-vpc-endpoints.tf` 생성
    - `vpce-quicksight-api-bos-ai-seoul-prod`: `com.amazonaws.ap-northeast-2.quicksight` Interface Endpoint, Private DNS ON
    - `vpce-quicksight-website-bos-ai-seoul-prod`: `com.amazonaws.ap-northeast-2.quicksight-website` Interface Endpoint, Private DNS ON
    - 서브넷: `module.vpc_frontend.private_subnet_ids` (기존 VPC Endpoint 전용 서브넷)
    - `precondition` 블록으로 리전별 서비스 가용 여부 확인 및 에러 안내 메시지 포함
    - 표준 태그 적용
    - _요구사항: 1.1, 1.2, 1.4, 1.5, 1.6_

  - [ ]* 3.5 Property 1 속성 테스트 작성 — Quick VPC Endpoint 구성 정확성 검증
    - **Property 1: Quick VPC Endpoint 구성 정확성**
    - **검증: 요구사항 1.1, 1.2, 1.4**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

  - [x] 3.6 `environments/network-layer/quicksight-dns.tf` 생성
    - 기존 Private Hosted Zone(`rag.corp.bos-semi.com`)에 CNAME 레코드 추가
    - `quick.rag.corp.bos-semi.com` → Quick API VPC Endpoint DNS 이름
    - `precondition`으로 Hosted Zone ID 및 VPC 연결 상태 확인, 실패 시 안내 메시지 포함
    - _요구사항: 8.1, 8.2, 8.3, 8.4_

  - [x] 3.7 Quick VPC Connection ENI 서브넷 라우팅 테이블 확인 및 보완
    - Quick ENI가 배치될 Private 서브넷의 라우팅 테이블에 `10.20.0.0/16 → pcx-xxx` 경로 존재 확인
    - 기존 `module.vpc_peering`이 해당 경로를 이미 설정하고 있는지 검증하는 `data` 소스 또는 `check` 블록 추가
    - Network ACL 규칙: 허용 CIDR(10.10.0.0/16, 10.20.0.0/16, 192.128.0.0/16) 외 트래픽 차단
    - _요구사항: 4.6, 7.1, 7.3_

  - [ ]* 3.8 Property 15 속성 테스트 작성 — 네트워크 격리 검증
    - **Property 15: Quick 네트워크 격리**
    - **검증: 요구사항 7.1, 7.3**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

- [x] 4. 체크포인트 — Network Layer 검증
  - `terraform validate && tflint` 실행하여 VPC Endpoint, SG, DNS 리소스 구성 확인
  - 모든 테스트 통과 여부 확인. 문제가 있으면 사용자에게 질문하세요.

- [x] 5. App Layer — Quick 계정, VPC Connection, S3, Lambda, 모니터링
  - [x] 5.1 `environments/app-layer/quicksight/` 디렉토리 구조 생성
    - `backend.tf`, `providers.tf`, `variables.tf`, `outputs.tf`, `terraform.tfvars.example` 생성
    - `locals` 블록에 `quicksight_tags` 정의 (`Project`, `Environment`, `ManagedBy`, `Layer`, `Service`)
    - _요구사항: 1.6, 3.7_

  - [x] 5.2 `environments/app-layer/quicksight/main.tf` — Quick 계정 및 VPC Connection 생성
    - `aws_quicksight_account_subscription`: Enterprise Edition, `IAM_IDENTITY_CENTER` 인증
    - 기존 계정 존재 시 `data` 소스로 참조, `lifecycle { prevent_destroy = true }` 적용
    - `aws_quicksight_vpc_connection`: Seoul VPC Private 서브넷에 ENI 배치
    - VPC Connection에 `sg-quicksight-vpc-conn-bos-ai-seoul-prod` SG 연결
    - `postcondition`으로 서브넷 가용 IP 확인, 부족 시 CIDR 확장 안내 메시지 포함
    - _요구사항: 2.1, 2.2, 2.5, 4.1, 4.8_

  - [x] 5.3 `environments/app-layer/quicksight/s3.tf` — Quick 전용 S3 버킷 생성
    - 버킷명: `s3-quicksight-data-bos-ai-seoul-prod`, Seoul 리전
    - 버전 관리 활성화, KMS CMK SSE-KMS 암호화, 퍼블릭 액세스 전체 차단
    - 버킷 정책: `aws:sourceVpce` 조건 (Quick API Endpoint + S3 Gateway Endpoint)
    - 수명 주기: 90일 → Intelligent-Tiering, 365일 → Glacier
    - S3 서버 액세스 로깅 활성화 (기존 로깅 버킷 대상)
    - 표준 태그 적용
    - _요구사항: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 5.4 Property 7 속성 테스트 작성 — S3 보안 구성 검증
    - **Property 7: Quick S3 버킷 보안 구성**
    - **검증: 요구사항 3.1, 3.2, 3.3, 3.4**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

  - [x] 5.5 `environments/app-layer/quicksight/main.tf`에 Quick 서비스 역할 및 데이터 소스 등록 추가
    - Quick 서비스 IAM 역할: `Quick_Data_S3` 읽기/쓰기, 기존 RAG S3 읽기 전용, OpenSearch `aoss:APIAccessAll` 읽기 전용
    - 와일드카드(`*`) 리소스 전체 권한 금지
    - Quick 데이터 소스 등록: `Quick_Data_S3` (서비스 역할 사용), OpenSearch (VPC Connection 경유)
    - Quick 데이터셋 SPICE 새로고침 스케줄: 1시간 간격
    - _요구사항: 2.3, 2.4, 4.4, 4.7, 5.10_

  - [ ]* 5.6 Property 5 속성 테스트 작성 — IAM 정책 최소 권한 검증
    - **Property 5: Quick 서비스 역할 최소 권한**
    - **검증: 요구사항 2.3, 2.4**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

  - [x] 5.7 `environments/app-layer/quicksight/lambda.tf` — RAG Connector Lambda 생성
    - 함수명: `lambda-quick-rag-connector-seoul-prod`, Python 3.12, 메모리 256MB, 타임아웃 60초
    - Seoul VPC Private 서브넷 배포, Reserved Concurrency: 10
    - 환경 변수: `RAG_API_ENDPOINT`, `CACHE_BUCKET`, `CACHE_TTL_SECONDS`
    - IAM 역할: RAG API 접근 권한 (하드코딩 자격 증명 금지)
    - API Gateway Usage Plan: Quick 전용 API Key, throttle 10 req/s, quota 5,000 req/day
    - _요구사항: 5.1, 5.3, 5.6, 5.7, 5.8_

  - [x] 5.8 `environments/app-layer/quicksight/monitoring.tf` — CloudWatch 알람 및 대시보드 생성
    - Lambda 스로틀 알람: `Throttles > 5` (5분간) → SNS 알림
    - Lambda 동시 실행 모니터링: `ConcurrentExecutions` 대시보드 위젯
    - Quick VPC Endpoint 상태 알람: 비정상 시 SNS 알림
    - Quick VPC Connection ENI 상태 알람: `!= available` 시 SNS 알림
    - Quick_Data_S3 크기/객체 수 대시보드 위젯
    - CloudTrail 이벤트 셀렉터: `quicksight:*` API 호출 기록
    - VPC Flow Logs: Quick 관련 ENI 활성화, CloudWatch Logs 저장
    - 모든 CloudWatch 로그 그룹 보존 기간: 90일
    - _요구사항: 5.11, 7.4, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 5.9 Property 4 속성 테스트 작성 — 필수 태그 존재 검증
    - **Property 4: Quick 리소스 필수 태그 존재**
    - **검증: 요구사항 1.6, 3.7, 9.6**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

  - [ ]* 5.10 Property 16 속성 테스트 작성 — CloudWatch 로그 보존 기간 검증
    - **Property 16: Quick CloudWatch 로그 보존 기간**
    - **검증: 요구사항 10.5**
    - `tests/properties/quicksight_test.go`에 gopter 기반 테스트 추가

  - [x] 5.11 RBAC Pipeline GROUP_MAP 확장 — Provisioner Lambda 수정
    - 기존 RBAC Pipeline의 Provisioner Lambda 소스에 Quick 서비스 항목 추가
    - `GROUP_MAP`에 `quicksight-admin`, `quicksight-author`, `quicksight-viewer` 키 및 그룹 ID 매핑 추가
    - IAM Identity Center 동기화를 통한 Quick 역할 자동 프로비저닝/해제 로직 확인
    - _요구사항: 2.6, 2.7, 2.8, 2.9_

- [x] 6. 체크포인트 — App Layer 검증
  - `terraform validate && tflint` 실행하여 Quick 계정, S3, Lambda, 모니터링 리소스 구성 확인
  - 모든 테스트 통과 여부 확인. 문제가 있으면 사용자에게 질문하세요.

- [x] 7. Lambda 소스 코드 — RAG Connector 구현
  - [x] 7.1 `lambda/quick-rag-connector/handler.py` 생성
    - RAG API 질의 전송 및 Quick 소비 가능한 JSON 배열 형식으로 응답 변환
    - 반환 필드: 질의 로그, 인용 통계, 검색 유형별 성능 데이터
    - IAM 역할 기반 인증 (boto3 기본 자격 증명 체인 사용, 하드코딩 금지)
    - _요구사항: 5.2, 5.4, 5.6_

  - [x] 7.2 `lambda/quick-rag-connector/handler.py`에 S3 캐싱 로직 추가
    - S3 캐시 키 패턴: `cache/{query_hash}/{timestamp}.json`
    - TTL 1시간 내 동일 질의 패턴 → 캐시 반환, TTL 만료 시 RAG API 재호출
    - S3 캐시 읽기/쓰기 실패 시 캐시 무시하고 RAG API 직접 호출, 에러 CloudWatch 기록
    - _요구사항: 5.9_

  - [x] 7.3 `lambda/quick-rag-connector/handler.py`에 에러 처리 로직 추가
    - RAG API 타임아웃: 60초, 최대 3회 지수 백오프 재시도
    - 4xx/5xx 응답: 에러 상세 CloudWatch 기록, 빈 데이터셋 + 에러 메시지 반환
    - Reserved Concurrency 초과(스로틀) 시 CloudWatch 알람 트리거
    - _요구사항: 5.5_

  - [x] 7.4 `lambda/quick-rag-connector/requirements.txt` 생성
    - boto3, standard library only (Python 3.12)
    - _요구사항: 5.1_

  - [ ]* 7.5 Property 9 속성 테스트 작성 — Lambda 응답 형식 변환 검증
    - **Property 9: RAG Connector Lambda 응답 형식 변환**
    - **검증: 요구사항 5.2, 5.4**
    - `tests/properties/quicksight_lambda_test.go`에 gopter 기반 테스트 추가

  - [ ]* 7.6 Property 10 속성 테스트 작성 — Lambda/MCP 에러 처리 검증
    - **Property 10: RAG Connector Lambda 에러 처리**
    - **검증: 요구사항 5.5, 6.5**
    - `tests/properties/quicksight_lambda_test.go`에 gopter 기반 테스트 추가

  - [ ]* 7.7 Property 11 속성 테스트 작성 — 캐시 라운드트립 검증
    - **Property 11: RAG Connector Lambda 캐시 라운드트립**
    - **검증: 요구사항 5.9**
    - `tests/properties/quicksight_lambda_test.go`에 gopter 기반 테스트 추가

  - [ ]* 7.8 Property 12 속성 테스트 작성 — 소스 코드 자격 증명 미포함 검증
    - **Property 12: Lambda 소스 코드 자격 증명 미포함**
    - **검증: 요구사항 5.6**
    - `tests/properties/quicksight_lambda_test.go`에 gopter 기반 테스트 추가

  - [x]* 7.9 Lambda 단위 테스트 작성 — `lambda/quick-rag-connector/test_handler.py`
    - 응답 변환 엣지 케이스, 캐시 히트/미스, 에러 조건 검증
    - _요구사항: 5.2, 5.4, 5.5, 5.9_

- [x] 8. 체크포인트 — Lambda 소스 코드 검증
  - `python -m pytest lambda/quick-rag-connector/test_handler.py` 실행하여 단위 테스트 통과 확인
  - 모든 테스트 통과 여부 확인. 문제가 있으면 사용자에게 질문하세요.

- [x] 9. MCP Bridge — Quick 연동 도구 추가
  - [x] 9.1 `mcp-bridge/server.mjs`에 `quick_dashboard_list` 도구 추가
    - Quick `ListDashboards` API 호출 → Quick API VPC Endpoint 경유 (퍼블릭 엔드포인트 사용 금지)
    - IAM 자격 증명(환경 변수 또는 인스턴스 프로파일) 기반 인증
    - API 호출 실패 시 `isError: true` 에러 메시지 반환 및 콘솔 로그 기록
    - _요구사항: 6.1, 6.3, 6.4, 6.5_

  - [x] 9.2 `mcp-bridge/server.mjs`에 `quick_dashboard_data` 도구 추가
    - 파라미터: `dashboardId` (string)
    - Quick `DescribeDashboard` API 호출 → Quick API VPC Endpoint 경유
    - API 호출 실패 시 `isError: true` 에러 메시지 반환 및 콘솔 로그 기록
    - _요구사항: 6.2, 6.3, 6.4, 6.5_

  - [ ]* 9.3 MCP Bridge Quick 도구 단위 테스트 작성 — `mcp-bridge/test/quicksight_tools_test.js`
    - 도구 등록 확인, API 호출 모킹, 에러 처리 검증
    - _요구사항: 6.1, 6.2, 6.5_

- [x] 10. OPA 정책 — `policies/quicksight-security.rego` 생성
  - [x] 10.1 `deny_quicksight_sg_virginia_direct` 규칙 구현
    - Quick VPC Connection SG 아웃바운드 규칙에 Virginia CIDR(10.20.0.0/16) 직접 지정 시 deny
    - _요구사항: 4.9_

  - [x] 10.2 `deny_quicksight_sg_open_egress` 규칙 구현
    - Quick 관련 SG에 0.0.0.0/0 아웃바운드 규칙 포함 시 deny
    - _요구사항: 7.5_

  - [x] 10.3 `deny_quicksight_s3_public` 규칙 구현
    - Quick S3 버킷 퍼블릭 액세스 차단 비활성화 시 deny
    - _요구사항: 7.6_

  - [ ]* 10.4 Property 8 속성 테스트 작성 — OPA 정책 위반 감지 검증
    - **Property 8: OPA 정책 보안 위반 감지**
    - **검증: 요구사항 4.9, 7.5, 7.6**
    - `tests/properties/quicksight_opa_test.go`에 gopter 기반 테스트 추가
    - 위반 케이스(deny 트리거), 정상 케이스(deny 미발생), 엣지 케이스 모두 포함

- [x] 11. 통합 테스트 작성 — `tests/integration/quicksight_test.go`
  - [x] 11.1 VPC Endpoint 연결성 테스트
    - Quick API/Website VPC Endpoint를 통한 실제 연결 확인
    - _요구사항: 1.1, 1.2_

  - [x] 11.2 VPC Connection 경로 테스트
    - Quick ENI → VPC Peering → Virginia OpenSearch 경로 확인
    - _요구사항: 4.4, 4.6_

  - [x] 11.3 DNS 해석 테스트
    - `quick.rag.corp.bos-semi.com` → VPC Endpoint Private IP 해석 확인
    - _요구사항: 8.1, 8.3_

  - [x] 11.4 Lambda 실행 테스트
    - RAG Connector Lambda 실제 호출 및 JSON 배열 응답 형식 확인
    - _요구사항: 5.2, 5.4_

  - [x] 11.5 RBAC 동기화 테스트
    - IAM Identity Center 그룹 변경 → Quick 역할 매핑 자동 반영 확인
    - _요구사항: 2.8, 2.9_

- [x] 12. 운영 가이드 문서 작성 — `docs/quicksight-guide.md`
  - [x] 12.1 Admin 가이드 — 사용자 추가/제거 절차
    - 전제 조건: VPN 연결 상태, IAM Identity Center 관리자 권한
    - RBAC Pipeline 자동화 경로: 내부 포털/Jira 승인 요청 → Webhook → SQS → Provisioner Lambda → IAM Identity Center 그룹 자동 추가 → Quick 역할 자동 동기화
    - 수동 경로 (긴급 시): AWS Console → IAM Identity Center → 그룹(QS_Admin/Author/Viewer_Users) → 사용자 추가
    - 역할별 권한 요약표 (Admin / Author / Viewer)
    - 사용자 제거 절차 (RBAC Pipeline 자동화 및 수동 경로)
    - 트러블슈팅: 동기화 지연 시 확인 방법 (CloudWatch Logs, Reconciler Lambda)

  - [x] 12.2 User 가이드 — Quick 접속 방법
    - 전제 조건: VPN 클라이언트 설치 및 연결 (스플릿 터널링 방식)
    - 접속 URL: `https://quick.rag.corp.bos-semi.com` (Private DNS 경유)
    - 접속 흐름: 온프레미스 PC → VPN → Route53 Private DNS → Quick Website VPC Endpoint → Quick 웹 콘솔
    - 정적 자산(CSS/JS)은 CloudFront를 통해 인터넷으로 직접 로드됨 (스플릿 터널링으로 자동 처리)
    - IAM Identity Center 로그인 절차 (SSO 포털 경유)
    - 역할별 사용 가능 기능 안내 (대시보드 조회 / 생성·편집 / 관리)
    - Obot 채팅에서 Quick 대시보드 조회 방법 (`quick_dashboard_list`, `quick_dashboard_data` MCP 도구)
    - 트러블슈팅: 접속 불가 시 체크리스트 (VPN 연결 여부, DNS 해석 확인, 권한 확인)

  - [x] 12.3 운영자 모니터링 가이드
    - CloudWatch 알람 목록 및 대응 방법 (Lambda 스로틀, VPC Endpoint 비정상, ENI 비정상)
    - VPC Flow Logs 조회 방법 (Quick 관련 트래픽 확인)
    - CloudTrail에서 Quick API 호출 감사 방법
    - SPICE 새로고침 실패 시 수동 트리거 방법

- [x] 13. 최종 체크포인트 — 전체 검증
  - `bash scripts/terraform-validate.sh` 실행하여 모든 환경 Terraform 구성 확인
  - `bash scripts/run-policy-tests.sh` 실행하여 OPA 정책 테스트 통과 확인
  - `bash scripts/run-integration-tests.sh` 실행하여 통합 테스트 통과 확인
  - 모든 테스트 통과 여부 확인. 문제가 있으면 사용자에게 질문하세요.

## 참고

- `*` 표시 태스크는 선택 사항으로, MVP 빠른 구현 시 건너뛸 수 있음
- 각 태스크는 특정 요구사항을 참조하여 추적 가능성 확보
- 체크포인트는 각 배포 레이어 완료 후 점진적 검증을 보장
- 속성 기반 테스트(gopter)는 보편적 정확성 속성을 검증하고, 단위 테스트는 특정 예시와 엣지 케이스를 검증
- 배포 순서: Global IAM → Network Layer → App Layer → Lambda → MCP Bridge → OPA → 테스트
