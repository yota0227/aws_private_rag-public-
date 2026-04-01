# 구현 계획: 전사 Enterprise RBAC 자동 프로비저닝 파이프라인

## 개요

승인 웹훅 → SQS 비동기 큐 → IAM Identity Center 그룹 관리 → SCIM 자동 동기화를 구현하는 전사 Enterprise RBAC 파이프라인을 기존 Terraform 레이어 구조에 맞춰 단계적으로 구축한다. 본 시스템은 IAM Identity Center를 단일 Source of Truth로 활용하여 전사 기업 서비스의 사용자 권한을 통합 관리하는 범용 플랫폼으로, GROUP_MAP 아키텍처를 통해 코드 변경 없이 신규 서비스를 추가할 수 있다. 초기 적용 대상은 LLM 서비스(ChatGPT Team, AWS Q)이며, 향후 Jira, Confluence, 사내 서비스로 확장한다. 배포 순서(Global IAM → Network → App)를 따르며, 각 단계에서 속성 기반 테스트로 정확성을 검증한다.

## Tasks

- [ ] 1. IAM Identity Center 그룹 정의 (Global Layer)
  - [ ] 1.1 `environments/global/iam/main.tf`에 서비스별 IAM Identity Center 그룹 리소스 추가
    - `aws_identitystore_group` 리소스로 `LLM_ChatGPT_Team_Users`, `LLM_AWS_Q_Users` 그룹 정의
    - `identity_store_id`는 기존 로컬 변수 또는 data source에서 참조
    - 공통 태그(Project, Environment, ManagedBy, Layer) 적용
    - _Requirements: 3.4, 9.1, 9.5_

  - [ ] 1.2 `environments/global/iam/variables.tf`에 Identity Store ID 변수 추가 및 `outputs.tf`에 그룹 ID 출력 정의
    - 그룹 ID를 다른 레이어에서 참조할 수 있도록 output 정의
    - _Requirements: 3.4, 9.1_

  - [ ]* 1.3 Property 18 속성 테스트 작성: 서비스별 Identity Center 그룹 분리
    - **Property 18: 서비스별 Identity Center 그룹 분리**
    - `tests/properties/enterprise_rbac_properties_test.go`에 Go + gopter 테스트 추가
    - IAM Identity Center 그룹 리소스가 서비스별로 분리 정의되어 있는지 검증
    - **Validates: Requirements 3.4**


- [ ] 2. DMZ VPC 네트워크 구성 (Network Layer)
  - [ ] 2.1 `environments/network-layer/main.tf`에 DMZ VPC 모듈 인스턴스 추가
    - 기존 `modules/network/vpc` 모듈 재사용
    - CIDR 10.30.0.0/16, 프라이빗 서브넷 2개(10.30.1.0/24, 10.30.2.0/24), 퍼블릭 서브넷 1개(10.30.10.0/24)
    - `enable_nat_gateway = true`, `single_nat_gateway = true` (IP Updater Lambda의 외부 Atlassian IP API 접근용)
    - 공통 태그 + `Layer = "network"`, `VPCType = "DMZ"` 태그 적용
    - _Requirements: 5.1, 5.2, 10.1, 9.5_

  - [ ] 2.2 DMZ VPC Transit Gateway Attachment 및 라우팅 테이블 구성
    - TGW Attachment 리소스 추가 (기존 TGW 참조)
    - 프라이빗 서브넷 라우팅: 온프레미스(192.128.0.0/16) → TGW, 기존 VPC CIDR → TGW
    - 퍼블릭 서브넷 라우팅: 0.0.0.0/0 → IGW
    - 기존 VPC 라우팅 테이블에 DMZ CIDR(10.30.0.0/16) → TGW 경로 추가
    - _Requirements: 5.3, 5.6_

  - [ ] 2.3 DMZ VPC Security Group 정의
    - Lambda용 SG: Egress TCP 443 → 0.0.0.0/0 (NAT GW 경유, IP Updater Lambda 전용), Egress TCP 443 → VPC Endpoint 서브넷
    - VPC Endpoint용 SG: Ingress TCP 443 ← 10.30.0.0/16 (Secrets Manager, CloudWatch Logs, Identity Store)
    - _Requirements: 5.1_

  - [ ] 2.4 DMZ VPC VPC Endpoint 구성 (Secrets Manager, CloudWatch Logs, Identity Store)
    - 프라이빗 서브넷에 Interface 타입 VPC Endpoint 3개 배치
    - Secrets Manager(`com.amazonaws.ap-northeast-2.secretsmanager`)
    - CloudWatch Logs(`com.amazonaws.ap-northeast-2.logs`)
    - Identity Store(`com.amazonaws.ap-northeast-2.identitystore`)
    - _Requirements: 5.4, 10.3_

  - [ ] 2.5 DMZ VPC Flow Logs 활성화
    - VPC Flow Logs → CloudWatch Logs 로그 그룹 (보관 30일)
    - _Requirements: 5.5, 8.5_

  - [ ] 2.6 `environments/network-layer/variables.tf`에 DMZ VPC 관련 변수 추가 및 `terraform.tfvars.example` 업데이트
    - _Requirements: 9.6_

  - [ ]* 2.7 Property 6 속성 테스트 작성: VPC CIDR 비중첩
    - **Property 6: VPC CIDR 비중첩**
    - `tests/properties/enterprise_rbac_properties_test.go`에 DMZ VPC CIDR(10.30.0.0/16) 추가하여 기존 cidrsOverlap 헬퍼 활용
    - **Validates: Requirements 5.6**

- [ ] 3. 체크포인트 — Global/Network 레이어 검증
  - 모든 테스트 통과 확인, `terraform validate` 및 `tflint` 실행, 사용자에게 질문 사항 확인

- [ ] 4. Terraform 모듈 구조 생성 (modules/security/enterprise-provisioner/)
  - [ ] 4.1 `modules/security/enterprise-provisioner/` 디렉토리에 main.tf, variables.tf, outputs.tf 생성
    - variables.tf: VPC ID, 서브넷 ID, 그룹 ID 맵, 시크릿 ARN 등 입력 변수 정의
    - outputs.tf: API Gateway URL, Lambda ARN, WAF WebACL ARN 등 출력 정의
    - main.tf: 리소스 정의를 위한 기본 구조 (이후 태스크에서 채움)
    - _Requirements: 9.4, 9.5_

  - [ ] 4.2 `modules/security/enterprise-provisioner/iam.tf` 생성 — Lambda 실행 역할 및 IAM 정책
    - Provisioner Lambda 역할: Identity Store API (VPC Endpoint), Secrets Manager 읽기, CloudWatch Logs/Metrics, VPC 접근, SQS 수신(ReceiveMessage, DeleteMessage, GetQueueAttributes)
    - Reconciler Lambda 역할: Identity Store API (VPC Endpoint), CloudWatch Logs/Metrics, SNS Publish
    - IP Updater Lambda 역할: WAF IP Set 갱신, CloudWatch Logs, SNS Publish
    - API Gateway 역할: SQS SendMessage 권한
    - 최소 권한 원칙 적용
    - _Requirements: 9.4, 9.5_

  - [ ]* 4.3 Property 13 속성 테스트 작성: Terraform 모듈 파일 패턴
    - **Property 13: Terraform 모듈 파일 패턴**
    - `tests/properties/enterprise_rbac_properties_test.go`에 modules/security/enterprise-provisioner/ 디렉토리의 main.tf, variables.tf, outputs.tf 존재 확인 테스트 추가
    - **Validates: Requirements 9.4**


- [ ] 5. Provisioner Lambda 구현
  - [ ] 5.1 `lambda/enterprise-provisioner/handler.py` 생성 — 핵심 프로비저닝 로직
    - GROUP_MAP 환경 변수 파싱 (Lambda 초기화 시)
    - HMAC SHA-256 서명 검증 (X-Hub-Signature 헤더 vs Secrets Manager 키 기반 페이로드 해시, hmac.compare_digest 사용)
    - SQS 이벤트(Records[].body) 파싱 및 필수 필드(user_id, service_name, action) 검증
    - GROUP_MAP에서 서비스명 → 그룹 ID 조회
    - Identity Store API 호출 (VPC Endpoint 경유): add → CreateGroupMembership, remove → DeleteGroupMembership
    - 멱등성 처리: 이미 멤버/비멤버 시 로그 기록 후 정상 소비
    - HMAC 실패/검증 에러: 로그 기록 후 메시지 정상 소비 (DLQ 이동 방지)
    - 지수 백오프 재시도 (최대 3회, 1s/2s/4s), 실패 시 예외 발생 → SQS 재처리/DLQ 이동
    - CloudWatch 커스텀 메트릭 발행 (provisioning_latency_ms)
    - _Requirements: 1.1, 1.2, 1.4, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 6.4, 8.1_

  - [ ]* 5.2 Property 1 속성 테스트 작성: 페이로드 검증
    - **Property 1: 페이로드 검증 — 잘못된 입력 거부**
    - `lambda/enterprise-provisioner/test_handler.py`에 Python hypothesis 테스트 작성
    - 랜덤 페이로드 생성, 필수 필드 누락 조합 시 에러 로그 기록 및 메시지 정상 소비 검증
    - **Validates: Requirements 1.4, 2.7**

  - [ ]* 5.3 Property 2 속성 테스트 작성: HMAC SHA-256 서명 검증 실패 시 거부
    - **Property 2: HMAC SHA-256 서명 검증 실패 시 거부**
    - `lambda/enterprise-provisioner/test_handler.py`에 Python hypothesis 테스트 작성
    - 랜덤 페이로드/서명 생성, 유효/무효 HMAC SHA-256 조합 시 메시지 정상 소비 및 에러 로그 검증
    - **Validates: Requirements 1.2, 6.4**

  - [ ]* 5.4 Property 3 속성 테스트 작성: GROUP_MAP 기반 올바른 API 라우팅
    - **Property 3: GROUP_MAP 기반 올바른 API 라우팅**
    - `lambda/enterprise-provisioner/test_handler.py`에 Python hypothesis 테스트 작성
    - 유효한 요청에 대해 올바른 Identity Store API 호출 검증 (mock)
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 5.5 Property 4 속성 테스트 작성: 멱등성
    - **Property 4: 멱등성 — 중복 작업 안전성**
    - `lambda/enterprise-provisioner/test_handler.py`에 Python hypothesis 테스트 작성
    - 이미 멤버/비멤버 시나리오에서 로그 기록 및 메시지 정상 소비 검증 (mock)
    - **Validates: Requirements 2.3, 2.4**

  - [ ]* 5.6 Property 5 속성 테스트 작성: 지수 백오프 재시도
    - **Property 5: 지수 백오프 재시도**
    - `lambda/enterprise-provisioner/test_handler.py`에 Python hypothesis 테스트 작성
    - API 실패 시뮬레이션, 재시도 횟수(3회) 및 지연 간격 검증, 최종 실패 시 예외 발생 확인
    - **Validates: Requirements 2.5**

- [ ] 6. Reconciler Lambda 구현
  - [ ] 6.1 `lambda/enterprise-reconciler/handler.py` 생성 — 드리프트 감지 로직
    - Identity Store API 페이지네이션 처리하여 전체 그룹 멤버십 조회
    - SaaS 라이선스 API 호출하여 실제 할당 목록 조회
    - 대칭 차집합 계산: missing_license = (IC 멤버 - SaaS), orphan_license = (SaaS - IC 멤버)
    - 드리프트 보고서 JSON 형식으로 CloudWatch Logs에 기록
    - drift_count CloudWatch 커스텀 메트릭 발행
    - 드리프트 감지 시 SNS 알림 발송
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.2_

  - [ ]* 6.2 Property 9 속성 테스트 작성: 드리프트 감지 정확성
    - **Property 9: 드리프트 감지 정확성**
    - `lambda/enterprise-reconciler/test_handler.py`에 Python hypothesis 테스트 작성
    - 랜덤 멤버/라이선스 목록 생성, 대칭 차집합 결과 검증
    - **Validates: Requirements 7.2**

  - [ ]* 6.3 Property 10 속성 테스트 작성: 페이지네이션 완전성
    - **Property 10: 페이지네이션 완전성**
    - `lambda/enterprise-reconciler/test_handler.py`에 Python hypothesis 테스트 작성
    - 랜덤 페이지 수/크기 생성, 전체 멤버 수집 검증 (mock)
    - **Validates: Requirements 7.3**

  - [ ]* 6.4 Property 11 속성 테스트 작성: 드리프트 보고서 JSON 스키마
    - **Property 11: 드리프트 보고서 JSON 스키마**
    - `lambda/enterprise-reconciler/test_handler.py`에 Python hypothesis 테스트 작성
    - 랜덤 드리프트 결과 생성, JSON 파싱 및 필수 필드 존재 검증
    - **Validates: Requirements 7.4**

- [ ] 7. IP Updater Lambda 구현
  - [ ] 7.1 `lambda/enterprise-ip-updater/handler.py` 생성 — WAF IP Set 갱신 로직
    - urllib(표준 라이브러리)로 `https://ip-ranges.atlassian.com` HTTPS GET 호출
    - 응답 파싱하여 CIDR 목록 추출
    - 빈 IP 목록 반환 시 안전장치: 갱신하지 않고 에러 로그 기록
    - WAF API로 IP Set 갱신
    - 실패 시: 기존 IP Set 유지, CloudWatch Logs에 에러 기록, SNS 알림 발송
    - _Requirements: 6.2, 6.3_

  - [ ]* 7.2 Property 8 속성 테스트 작성: IP Updater 실패 안전성
    - **Property 8: IP Updater 실패 안전성**
    - `lambda/enterprise-ip-updater/test_handler.py`에 Python hypothesis 테스트 작성
    - API 실패 시뮬레이션, 기존 WAF IP Set 미변경 검증
    - **Validates: Requirements 6.3**

- [ ] 8. 체크포인트 — Lambda 함수 검증
  - 모든 Lambda 함수의 단위 테스트 및 속성 테스트 통과 확인, 사용자에게 질문 사항 확인


- [ ] 9. API Gateway + WAF 구성 (App Layer)
  - [ ] 9.1 `environments/app-layer/enterprise-provisioning/` 디렉토리 생성 및 기본 Terraform 파일 구성
    - main.tf, variables.tf, outputs.tf, backend.tf, providers.tf 생성
    - `modules/security/enterprise-provisioner/` 모듈 참조
    - terraform.tfvars.example 템플릿 제공
    - _Requirements: 9.3, 9.6_

  - [ ] 9.2 `modules/security/enterprise-provisioner/main.tf`에 API Gateway + SQS 리소스 정의
    - Regional REST API Gateway 생성
    - POST /provision 리소스 및 메서드 정의
    - API Key 사용량 계획(Usage Plan) 구성
    - SQS AWS 서비스 통합 설정 (Lambda 프록시 대신)
    - SQS 표준 큐(`rbac-provisioning-queue`, 메시지 보관 4일) 및 DLQ(`rbac-provisioning-dlq`, maxReceiveCount: 3, 메시지 보관 14일) 생성
    - SQS Event Source Mapping → Provisioner Lambda (batchSize: 1)
    - API Gateway 매핑 템플릿: X-Hub-Signature 헤더를 SQS 메시지 본문에 포함
    - 액세스 로그 활성화 (CloudWatch Logs)
    - _Requirements: 1.1, 1.5, 1.6, 6.4_

  - [ ] 9.3 `modules/security/enterprise-provisioner/main.tf`에 WAF WebACL 및 IP Set 리소스 정의
    - WAF IP Set 리소스 (초기 Atlassian IP 범위)
    - WAF WebACL: IP Set 기반 단일 허용 규칙
    - WebACL → API Gateway 연동
    - _Requirements: 1.3, 6.1, 10.4_

  - [ ] 9.4 `modules/security/enterprise-provisioner/main.tf`에 Lambda 함수 리소스 정의
    - Provisioner Lambda: VPC 내 배치, 메모리 128MB, 타임아웃 30초, SQS Event Source Mapping 트리거
    - Reconciler Lambda: VPC 내 배치, 메모리 128MB, 타임아웃 30초
    - IP Updater Lambda: VPC 내 배치, 메모리 128MB, 타임아웃 30초
    - 환경 변수: GROUP_MAP_JSON, IDENTITY_STORE_ID, SECRET_ARN, SQS_QUEUE_URL 등
    - _Requirements: 10.2_

  - [ ] 9.5 Secrets Manager 리소스 정의
    - `rbac/webhook-secret`, `rbac/scim-tokens`, `rbac/saas-api-keys` 시크릿 리소스
    - Lambda 실행 역할에 시크릿 읽기 권한 부여
    - _Requirements: 3.3, 6.5_

  - [ ]* 9.6 Property 7 속성 테스트 작성: WAF 단일 IP Set 규칙
    - **Property 7: WAF 단일 IP Set 규칙**
    - `tests/properties/enterprise_rbac_properties_test.go`에 WAF Terraform 파일 파싱, 규칙 수 검증
    - **Validates: Requirements 1.3, 6.1, 10.4**

  - [ ]* 9.7 Property 14 속성 테스트 작성: Lambda 리소스 제약
    - **Property 14: Lambda 리소스 제약**
    - `tests/properties/enterprise_rbac_properties_test.go`에 Lambda 메모리 128MB, 타임아웃 30초 이내 검증
    - **Validates: Requirements 10.2**

  - [ ]* 9.8 Property 17 속성 테스트 작성: Secrets Manager 리소스 정의
    - **Property 17: Secrets Manager 리소스 정의**
    - `tests/properties/enterprise_rbac_properties_test.go`에 시크릿 리소스 및 IAM 정책 검증
    - **Validates: Requirements 3.3, 6.5**

- [ ] 10. EventBridge 스케줄 및 모니터링 구성
  - [ ] 10.1 `modules/security/enterprise-provisioner/eventbridge.tf` 생성 — EventBridge 스케줄 규칙
    - Reconciler Lambda: 일간 스케줄 (cron)
    - IP Updater Lambda: 일간 스케줄 (cron)
    - Lambda 실행 권한(permission) 리소스 추가
    - _Requirements: 6.2, 7.1_

  - [ ] 10.2 `modules/security/enterprise-provisioner/monitoring.tf` 생성 — CloudWatch 알람 및 SNS
    - SNS 토픽 생성 (RBAC 파이프라인 알림용)
    - Provisioner Lambda 에러율 알람: 5분간 에러율 > 10% → SNS
    - Reconciler Lambda 실행 실패 알람 → SNS
    - 모든 Lambda 함수의 CloudWatch Logs 로그 그룹 (보관 30일)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 10.3 Property 15 속성 테스트 작성: 로그 보관 기간
    - **Property 15: 로그 보관 기간**
    - `tests/properties/enterprise_rbac_properties_test.go`에 CloudWatch 로그 그룹 retention 30일 검증
    - **Validates: Requirements 8.5**

  - [ ]* 10.4 Property 16 속성 테스트 작성: CloudWatch 알람 및 SNS 알림
    - **Property 16: CloudWatch 알람 및 SNS 알림**
    - `tests/properties/enterprise_rbac_properties_test.go`에 알람 리소스 및 SNS 액션 검증
    - **Validates: Requirements 8.3, 8.4**

- [ ] 11. 필수 태그 및 전체 통합
  - [ ] 11.1 모든 Terraform 리소스에 필수 태그(Project, Environment, ManagedBy, Layer) 적용 확인 및 누락 보완
    - environments/global/iam/, environments/network-layer/, environments/app-layer/enterprise-provisioning/, modules/security/enterprise-provisioner/ 전체 검토
    - _Requirements: 9.5_

  - [ ] 11.2 `environments/app-layer/enterprise-provisioning/main.tf`에서 모듈 호출 및 전체 와이어링
    - modules/security/enterprise-provisioner/ 모듈 호출
    - Global IAM 레이어 출력(그룹 ID)을 data source 또는 변수로 참조
    - Network 레이어 출력(VPC ID, 서브넷 ID)을 data source 또는 변수로 참조
    - _Requirements: 9.3, 9.4_

  - [ ]* 11.3 Property 12 속성 테스트 작성: 필수 태그 부여
    - **Property 12: 필수 태그 부여**
    - `tests/properties/enterprise_rbac_properties_test.go`에 모든 RBAC 리소스의 필수 태그 검증
    - **Validates: Requirements 9.5**

- [ ] 12. 최종 체크포인트 — 전체 검증
  - 모든 테스트 통과 확인 (Go 속성 테스트, Python 속성 테스트, terraform validate, tflint)
  - 사용자에게 질문 사항 확인

## 참고 사항

- `*` 표시된 태스크는 선택 사항이며 빠른 MVP를 위해 건너뛸 수 있음
- 각 태스크는 추적 가능성을 위해 구체적 요구사항을 참조함
- 체크포인트에서 점진적 검증을 수행하여 조기에 문제를 발견함
- 속성 테스트는 보편적 정확성 속성을 검증하고, 단위 테스트는 구체적 예제와 엣지 케이스를 검증함
- 배포 순서: Global IAM (Task 1) → Network (Task 2) → App (Task 9~11)