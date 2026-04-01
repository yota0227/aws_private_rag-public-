# 요구사항 문서: Enterprise RBAC 자동 프로비저닝 플랫폼

## 소개

BOS Semi 전사 서비스에 대한 사용자 권한을 자동으로 관리하는 Enterprise RBAC 자동 프로비저닝 플랫폼을 구축한다. AWS IAM Identity Center를 전사 ID/접근 관리의 중앙 Source of Truth로 활용하며, 두 가지 통합 패턴을 지원한다: Pattern A (SaaS 서비스 — SAML SSO + SCIM 자동 프로비저닝)와 Pattern B (사내 서비스 — OIDC + Group Claims JIT 프로비저닝). 내부 포털 또는 Jira를 통한 승인 워크플로우에서 시작하여, IAM Identity Center 그룹 관리를 통해 SCIM 자동 동기화 및 OIDC JIT 프로비저닝까지 엔드투엔드 자동화를 달성한다.

초기 롤아웃은 LLM 서비스(ChatGPT Team, AWS Q)를 대상으로 하며, 향후 Jira, Confluence, 사내 Django 서비스 등으로 확장 시 GROUP_MAP 추가만으로 대응할 수 있도록 무제한 서비스 확장성을 Day 1부터 아키텍처에 내재한다.

## 용어 정의 (Glossary)

- **RBAC_Pipeline**: Enterprise RBAC 자동 프로비저닝 플랫폼 시스템 전체를 지칭
- **Provisioner_Lambda**: API Gateway 웹훅 요청을 수신하여 IAM Identity Center 그룹 멤버십을 관리하는 Python 3.12 Lambda 함수
- **Reconciler_Lambda**: 일간 스케줄로 IAM Identity Center 그룹 멤버십과 실제 SaaS 라이선스 간 드리프트를 감지하는 Lambda 함수
- **IP_Updater_Lambda**: 일간 스케줄로 Atlassian IP 범위를 폴링하여 WAF IP Set을 자동 갱신하는 Lambda 함수
- **DMZ_VPC**: 외부 SaaS 연동 전용으로 신규 생성되는 서울 리전 VPC (CIDR: 10.30.0.0/16)
- **Identity_Store_API**: AWS IAM Identity Center의 사용자 및 그룹 멤버십을 관리하는 AWS API — 전사 ID 관리의 중앙 Source of Truth
- **SCIM_Connector**: IAM Identity Center에서 외부 SaaS(ChatGPT, Atlassian)로 사용자/그룹 정보를 자동 동기화하는 프로토콜 연동 (Pattern A)
- **WAF_IPSet**: API Gateway 앞단에서 Atlassian IP 주소만 허용하는 AWS WAF IP Set 규칙
- **GROUP_MAP**: Provisioner_Lambda 내부에서 서비스명을 IAM Identity Center 그룹 ID로 매핑하는 딕셔너리 — 새 서비스 추가 시 이 매핑만 확장하면 됨
- **Webhook_Gateway**: 승인 워크플로우의 웹훅을 수신하는 Regional API Gateway (WAF 연동, SQS AWS 서비스 통합)
- **Provisioning_Queue**: Webhook_Gateway에서 수신한 프로비저닝 요청을 비동기로 전달하는 SQS 표준 큐
- **Provisioning_DLQ**: Provisioning_Queue에서 처리 실패한 메시지를 격리하는 SQS Dead Letter Queue
- **Transit_Gateway**: 서울 리전 내 모든 VPC와 VPN을 연결하는 중앙 허브
- **Pattern_A**: SaaS 서비스(Jira, Confluence, ChatGPT) 연동 방식 — SAML SSO + SCIM 자동 프로비저닝
- **Pattern_B**: 사내 서비스(Django) 연동 방식 — OIDC + Group Claims JIT 프로비저닝


## 요구사항

### 요구사항 1: 승인 웹훅 수신 및 검증

**사용자 스토리:** 인프라 관리자로서, 내부 승인 포털/Jira에서 발생한 RBAC 변경 요청을 안전하게 수신하고 싶다. 이를 통해 승인된 요청만 자동 프로비저닝 파이프라인에 진입할 수 있다.

#### 인수 조건

1. WHEN 승인 웹훅 요청이 수신되면, THE Webhook_Gateway SHALL WAF IP 검증 통과 후 요청 페이로드를 Provisioning_Queue(SQS)에 전송하고 HTTP 202 응답을 즉시 반환한다
2. WHEN SQS 메시지의 X-Hub-Signature 헤더에 포함된 HMAC SHA-256 서명이 페이로드 기반 해시와 일치하지 않는 경우, THE Provisioner_Lambda SHALL 에러를 CloudWatch Logs에 기록하고 해당 메시지를 정상 처리 완료하여 DLQ로 이동하지 않도록 한다
3. THE WAF_IPSet SHALL Webhook_Gateway 앞단에서 허용된 IP 주소 목록에 포함된 요청만 통과시킨다
4. WHEN SQS 메시지의 페이로드에 필수 필드(사용자 ID, 서비스명, 액션)가 누락된 경우, THE Provisioner_Lambda SHALL 에러를 CloudWatch Logs에 기록하고 해당 메시지를 정상 처리 완료하여 DLQ로 이동하지 않도록 한다
5. THE Webhook_Gateway SHALL 모든 수신 요청을 CloudWatch Logs에 기록한다
6. WHEN Provisioner_Lambda가 SQS 메시지 처리에 3회 연속 실패하면, THE Provisioning_Queue SHALL 해당 메시지를 Provisioning_DLQ로 이동시킨다


### 요구사항 2: IAM Identity Center 그룹 멤버십 관리

**사용자 스토리:** 인프라 관리자로서, 승인된 RBAC 변경 요청에 따라 IAM Identity Center 그룹에 사용자를 자동으로 추가/제거하고 싶다. 이를 통해 수동 작업 없이 권한이 프로비저닝된다.

#### 인수 조건

1. WHEN "추가" 액션이 포함된 유효한 요청을 수신하면, THE Provisioner_Lambda SHALL GROUP_MAP을 참조하여 해당 서비스의 IAM Identity Center 그룹에 사용자를 추가한다
2. WHEN "제거" 액션이 포함된 유효한 요청을 수신하면, THE Provisioner_Lambda SHALL GROUP_MAP을 참조하여 해당 서비스의 IAM Identity Center 그룹에서 사용자를 제거한다
3. WHEN 이미 그룹에 존재하는 사용자에 대해 "추가" 요청이 수신되면, THE Provisioner_Lambda SHALL 중복 추가 없이 "이미 멤버" 상태를 CloudWatch Logs에 기록하고 메시지를 정상 처리 완료한다 (멱등성 보장)
4. WHEN 그룹에 존재하지 않는 사용자에 대해 "제거" 요청이 수신되면, THE Provisioner_Lambda SHALL 에러 없이 "이미 비멤버" 상태를 CloudWatch Logs에 기록하고 메시지를 정상 처리 완료한다 (멱등성 보장)
5. WHEN Identity_Store_API 호출이 실패하면, THE Provisioner_Lambda SHALL 최대 3회까지 지수 백오프로 재시도한 후, 실패 시 에러 상세를 CloudWatch Logs에 기록하고 SQS 메시지 처리를 실패로 보고하여 재처리 또는 DLQ 이동을 유도한다
6. THE Provisioner_Lambda SHALL 모든 그룹 멤버십 변경 작업을 CloudTrail 감사 로그에 기록한다
7. WHEN GROUP_MAP에 존재하지 않는 서비스명이 요청되면, THE Provisioner_Lambda SHALL 지원되지 않는 서비스임을 CloudWatch Logs에 기록하고 해당 메시지를 정상 처리 완료하여 DLQ로 이동하지 않도록 한다

### 요구사항 3: SCIM 자동 동기화 (Pattern A)

**사용자 스토리:** 인프라 관리자로서, IAM Identity Center 그룹 변경이 외부 SaaS 서비스(ChatGPT Team, Jira, Confluence)에 자동으로 반영되길 원한다. 이를 통해 라이선스 할당/해제가 수동 개입 없이 이루어진다.

#### 인수 조건

1. WHEN IAM Identity Center 그룹에 사용자가 추가되면, THE SCIM_Connector SHALL 해당 SaaS 서비스에 사용자를 자동 프로비저닝하고 라이선스를 할당한다
2. WHEN IAM Identity Center 그룹에서 사용자가 제거되면, THE SCIM_Connector SHALL 해당 SaaS 서비스에서 사용자를 디프로비저닝하고 라이선스를 해제한다
3. THE RBAC_Pipeline SHALL SCIM 토큰을 AWS Secrets Manager에 저장하고, Provisioner_Lambda 실행 시 Secrets Manager에서 조회하여 사용한다
4. THE RBAC_Pipeline SHALL 각 SaaS 서비스별로 별도의 IAM Identity Center 그룹을 유지한다 (초기 롤아웃: LLM_ChatGPT_Team_Users, LLM_AWS_Q_Users — 향후 서비스 추가 시 그룹 확장)

### 요구사항 4: OIDC JIT 프로비저닝 (Pattern B)

**사용자 스토리:** 인프라 관리자로서, 사내 Django 서비스에 대해 OIDC 기반 JIT(Just-In-Time) 프로비저닝을 구현하고 싶다. 이를 통해 사용자가 최초 로그인 시 자동으로 적절한 권한이 부여된다.

#### 인수 조건

1. WHEN 사용자가 Django 서비스에 OIDC로 최초 로그인하면, THE RBAC_Pipeline SHALL IAM Identity Center 그룹 멤버십 기반의 Group Claims를 OIDC 토큰에 포함하여 전달한다
2. THE RBAC_Pipeline SHALL Django 서비스가 OIDC 토큰의 Group Claims를 파싱하여 사용자 역할을 결정할 수 있도록 그룹 정보를 표준 클레임 형식으로 제공한다


### 요구사항 5: DMZ VPC 네트워크 격리

**사용자 스토리:** 보안 관리자로서, RBAC 프로비저닝 Lambda가 기존 프라이빗 RAG 인프라와 격리된 전용 VPC에서 실행되길 원한다. 이를 통해 외부 SaaS 연동에 필요한 인터넷 접근이 기존 에어갭 환경에 영향을 주지 않는다.

#### 인수 조건

1. THE RBAC_Pipeline SHALL 서울 리전에 CIDR 10.30.0.0/16의 DMZ_VPC를 생성하고, 프라이빗 서브넷(10.30.1.0/24, 10.30.2.0/24)과 퍼블릭 서브넷(10.30.10.0/24)을 구성한다
2. THE DMZ_VPC SHALL Internet Gateway와 단일 NAT Gateway를 퍼블릭 서브넷에 배치하여 프라이빗 서브넷의 IP_Updater_Lambda가 외부 Atlassian IP 범위 API에 접근할 수 있도록 한다
3. THE DMZ_VPC SHALL Transit_Gateway에 연결(TGW Attachment)하여 온프레미스 네트워크(192.128.0.0/16) 및 기존 서울 VPC들과 내부 통신이 가능하도록 한다
4. THE DMZ_VPC SHALL Secrets Manager, CloudWatch Logs, Identity Store용 VPC Endpoint 3개를 프라이빗 서브넷에 배치하여 해당 서비스 트래픽이 AWS 내부 네트워크(PrivateLink)를 통해 전달되도록 한다
5. THE DMZ_VPC SHALL VPC Flow Logs를 활성화하여 모든 네트워크 트래픽을 CloudWatch Logs에 기록한다
6. THE DMZ_VPC SHALL 기존 Frontend VPC(10.10.0.0/16) 및 Logging VPC(10.200.0.0/16)와 CIDR이 겹치지 않도록 한다

### 요구사항 6: WAF 및 API 보안

**사용자 스토리:** 보안 관리자로서, 외부에서 수신되는 웹훅 요청에 대해 다층 보안을 적용하고 싶다. 이를 통해 허가되지 않은 접근으로부터 RBAC 파이프라인을 보호할 수 있다.

#### 인수 조건

1. THE RBAC_Pipeline SHALL Webhook_Gateway에 AWS WAF를 연동하고, WAF_IPSet에 Atlassian IP 범위만 허용하는 IP 기반 접근 제어 규칙을 적용한다
2. WHEN IP_Updater_Lambda가 일간 스케줄(EventBridge)로 실행되면, THE IP_Updater_Lambda SHALL Atlassian IP 범위 API(https://ip-ranges.atlassian.com)를 폴링하여 WAF_IPSet을 갱신한다
3. IF IP_Updater_Lambda가 Atlassian IP 범위 API 호출에 실패하면, THEN THE IP_Updater_Lambda SHALL 기존 WAF_IPSet을 유지하고 실패 상세를 CloudWatch Logs에 기록하며 SNS 알림을 발송한다
4. THE Webhook_Gateway SHALL API Key 인증을 요구하고, THE Provisioner_Lambda SHALL X-Hub-Signature 헤더의 HMAC SHA-256 서명을 Secrets Manager에 저장된 시크릿 키로 검증하여 페이로드 무결성을 확인한다
5. THE RBAC_Pipeline SHALL API Key와 HMAC SHA-256 서명 검증용 시크릿 키를 AWS Secrets Manager에 저장하고 관리한다

### 요구사항 7: SCIM 드리프트 감지 및 조정 (Reconciliation)

**사용자 스토리:** 인프라 관리자로서, IAM Identity Center 그룹 멤버십과 실제 SaaS 라이선스 상태 간의 불일치를 자동으로 감지하고 싶다. 이를 통해 미사용 라이선스를 회수하고 권한 드리프트를 방지할 수 있다.

#### 인수 조건

1. WHEN Reconciler_Lambda가 일간 스케줄(EventBridge)로 실행되면, THE Reconciler_Lambda SHALL IAM Identity Center 그룹 멤버십 목록과 각 SaaS 서비스의 실제 라이선스 할당 목록을 비교한다
2. WHEN 드리프트가 감지되면(IAM Identity Center 그룹에 없는 사용자가 SaaS 라이선스를 보유하거나, 그룹에 있는 사용자가 라이선스를 미보유), THE Reconciler_Lambda SHALL 드리프트 상세를 CloudWatch 커스텀 메트릭(drift_count)으로 발행하고 SNS 알림을 발송한다
3. THE Reconciler_Lambda SHALL Identity_Store_API의 페이지네이션을 처리하여 전체 그룹 멤버십 목록을 조회한다
4. THE Reconciler_Lambda SHALL 드리프트 감지 결과를 JSON 형식으로 CloudWatch Logs에 기록한다

### 요구사항 8: 모니터링 및 알림

**사용자 스토리:** 인프라 관리자로서, RBAC 파이프라인의 운영 상태를 실시간으로 모니터링하고 이상 발생 시 즉시 알림을 받고 싶다. 이를 통해 장애에 신속하게 대응할 수 있다.

#### 인수 조건

1. THE RBAC_Pipeline SHALL Provisioner_Lambda의 프로비저닝 지연 시간을 CloudWatch 커스텀 메트릭(provisioning_latency_ms)으로 발행한다
2. THE RBAC_Pipeline SHALL Reconciler_Lambda의 드리프트 감지 건수를 CloudWatch 커스텀 메트릭(drift_count)으로 발행한다
3. WHEN Provisioner_Lambda의 에러율이 5분간 10%를 초과하면, THE RBAC_Pipeline SHALL CloudWatch Alarm을 트리거하고 SNS 토픽을 통해 관리자에게 알림을 발송한다
4. WHEN Reconciler_Lambda 실행이 실패하면, THE RBAC_Pipeline SHALL CloudWatch Alarm을 트리거하고 SNS 토픽을 통해 관리자에게 알림을 발송한다
5. THE RBAC_Pipeline SHALL 모든 Lambda 함수의 실행 로그를 CloudWatch Logs에 30일간 보관한다

### 요구사항 9: IaC 구조 및 배포 레이어

**사용자 스토리:** DevOps 엔지니어로서, RBAC 파이프라인 인프라가 기존 Terraform 레이어 구조와 일관되게 관리되길 원한다. 이를 통해 기존 배포 워크플로우와 동일한 방식으로 운영할 수 있다.

#### 인수 조건

1. THE RBAC_Pipeline SHALL IAM Identity Center 그룹 리소스를 environments/global/iam/ 레이어에 정의한다
2. THE RBAC_Pipeline SHALL DMZ_VPC 네트워크 리소스를 environments/network-layer/ 레이어에 정의한다
3. THE RBAC_Pipeline SHALL API Gateway, Lambda, WAF 리소스를 environments/app-layer/enterprise-provisioning/ 레이어에 정의한다
4. THE RBAC_Pipeline SHALL 재사용 가능한 Terraform 모듈을 modules/security/enterprise-provisioner/에 정의하고, main.tf, variables.tf, outputs.tf 패턴을 따른다
5. THE RBAC_Pipeline SHALL 모든 리소스에 Project("BOS-AI"), Environment("prod"), ManagedBy("Terraform"), Layer 태그를 부여한다
6. THE RBAC_Pipeline SHALL Terraform 변수 파일 템플릿을 terraform.tfvars.example로 제공하고, 실제 terraform.tfvars는 .gitignore에 포함한다

### 요구사항 10: 비용 최적화

**사용자 스토리:** 인프라 관리자로서, RBAC 파이프라인의 추가 인프라 비용을 월 $100 이내로 유지하고 싶다. 이를 통해 라이선스 절감 효과(월 ~$1,700) 대비 합리적인 비용 구조를 달성할 수 있다.

#### 인수 조건

1. THE DMZ_VPC SHALL 단일 NAT Gateway만 사용하여 NAT Gateway 비용을 최소화한다
2. THE RBAC_Pipeline SHALL Lambda 함수의 메모리를 최소 필요량(128MB)으로 설정하고, 타임아웃을 30초 이내로 제한한다
3. THE RBAC_Pipeline SHALL VPC Endpoint를 Secrets Manager, CloudWatch Logs, Identity Store 세 개로 구성하여 고빈도 Identity Store API 트래픽의 NAT Gateway 데이터 처리 비용을 절감한다
4. THE RBAC_Pipeline SHALL WAF 규칙을 IP Set 기반 단일 규칙으로 구성하여 WAF 비용을 최소화한다