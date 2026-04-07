# 요구사항 문서: Amazon Quick Private 통합

## 소개

BOS-AI Private RAG 인프라에 Amazon Quick(구 QuickSight)을 완전 Private하게 통합하는 기능이다. 현재 BOS-AI 시스템은 IGW/NAT 없이 VPN + VPC Endpoint + VPC Peering만으로 운영되는 완전 폐쇄형 아키텍처이며, Quick 통합 시에도 동일한 보안 수준을 유지해야 한다. Quick에서 업로드/사용하는 데이터는 자체 S3에 저장하여 데이터 주권을 확보하고, 기존 Bedrock + OpenSearch 기반 RAG 시스템을 Quick 대시보드에서 참조할 수 있도록 하며, MCP 브릿지 서버와의 연결을 지원한다. 모든 트래픽은 Private 네트워크 내에서만 흐르도록 통제한다.

Quick VPC Endpoint는 웹사이트용(`com.amazonaws.{region}.quicksight-website`)과 API용(`com.amazonaws.{region}.quicksight`)이 존재하며, CloudFront(정적 자산), execute-api(메트릭), signin.aws는 VPC Endpoint를 지원하지 않는다. API 전용 사용 시 완전 Private 구성이 가능하나, 웹 콘솔 사용 시 일부 제한적 인터넷 접근이 필요하다.

## 용어집

- **Quick**: Amazon Quick(구 Amazon QuickSight)으로, AWS의 BI(Business Intelligence) 서비스. 대시보드, 시각화, 임베디드 분석 기능을 제공
- **Quick_Account**: Quick 서비스의 계정 구성으로, Enterprise Edition 기반으로 설정되며 IAM Identity Center 또는 IAM 기반 인증을 사용
- **Quick_VPC_Connection**: Quick이 VPC 내 데이터 소스(OpenSearch, RDS 등)에 접근하기 위한 ENI 기반 네트워크 연결
- **Quick_API_Endpoint**: `com.amazonaws.{region}.quicksight` VPC Endpoint로, Quick API 호출을 Private 네트워크 내에서 처리
- **Quick_Website_Endpoint**: `com.amazonaws.{region}.quicksight-website` VPC Endpoint로, Quick 웹 콘솔 접근을 Private 네트워크 내에서 처리
- **Quick_Data_S3**: Quick 전용 S3 버킷으로, Quick에서 업로드하거나 SPICE로 가져온 데이터를 저장하는 자체 관리 버킷
- **Seoul_VPC**: BOS-AI Frontend VPC(10.10.0.0/16, ap-northeast-2)로, Lambda, API Gateway, VPC Endpoints가 배포된 서울 리전 VPC
- **Virginia_VPC**: BOS-AI Backend VPC(10.20.0.0/16, us-east-1)로, Bedrock, OpenSearch Serverless, S3가 배포된 버지니아 리전 VPC
- **Transit_Gateway**: 온프레미스(192.128.0.0/16)와 AWS VPC를 연결하는 IPsec VPN 종단점
- **OpenSearch_Collection**: Virginia 리전의 OpenSearch Serverless 벡터 컬렉션으로, RAG 임베딩 벡터를 저장하고 검색하는 벡터 데이터베이스
- **MCP_Bridge**: 온프레미스 Obot 서버에서 실행되는 Node.js MCP SSE 브릿지 서버로, 사용자 질의를 API Gateway를 통해 Lambda로 전달
- **Private_Hosted_Zone**: Route53 Private Hosted Zone(rag.corp.bos-semi.com)으로, VPC 내부 DNS 해석을 담당
- **SPICE**: Quick의 인메모리 계산 엔진(Super-fast, Parallel, In-memory Calculation Engine)으로, 데이터를 캐싱하여 빠른 대시보드 렌더링을 제공
- **RAG_API**: API Gateway Private REST API로, RAG 질의를 처리하는 기존 엔드포인트
- **RBAC_Pipeline**: Enterprise RBAC 자동 프로비저닝 플랫폼(.kiro/specs/7_enterprise-rbac-pipeline/)으로, IAM Identity Center를 중앙 Source of Truth로 활용하여 전사 서비스의 사용자 권한을 자동 관리하는 시스템
- **GROUP_MAP**: RBAC_Pipeline의 Provisioner_Lambda 내부에서 서비스명을 IAM Identity Center 그룹 ID로 매핑하는 딕셔너리. 새 서비스 추가 시 이 매핑만 확장하면 됨
- **Provisioner_Lambda**: RBAC_Pipeline의 핵심 Lambda 함수로, 승인된 요청에 따라 IAM Identity Center 그룹 멤버십을 관리
- **QS_Admin_Users**: Quick 관리자 역할에 매핑되는 IAM Identity Center 그룹
- **QS_Author_Users**: Quick 작성자 역할에 매핑되는 IAM Identity Center 그룹
- **QS_Viewer_Users**: Quick 뷰어 역할에 매핑되는 IAM Identity Center 그룹

## 요구사항

### 요구사항 1: Quick VPC Endpoint를 통한 Private 네트워크 접근

**사용자 스토리:** DevOps 엔지니어로서, Quick 서비스 접근을 VPC Endpoint(PrivateLink)로 구성하여, 모든 Quick API 트래픽이 Private 네트워크 내에서만 흐르도록 하고 싶다.

#### 인수 조건

1. THE Terraform 구성 SHALL Seoul_VPC에 Quick_API_Endpoint(`com.amazonaws.ap-northeast-2.quicksight`)를 Interface 타입 VPC Endpoint로 생성하며, Private DNS를 활성화한다.
2. THE Terraform 구성 SHALL Seoul_VPC에 Quick_Website_Endpoint(`com.amazonaws.ap-northeast-2.quicksight-website`)를 Interface 타입 VPC Endpoint로 생성하며, Private DNS를 활성화한다.
3. THE Terraform 구성 SHALL 각 Quick VPC Endpoint에 전용 Security Group을 생성하며, 인바운드 규칙으로 Seoul_VPC CIDR(10.10.0.0/16)과 온프레미스 CIDR(192.128.0.0/16)에서 HTTPS(443) 트래픽만 허용한다.
4. THE Terraform 구성 SHALL Quick VPC Endpoint를 Seoul_VPC의 Private 서브넷(VPC Endpoint 전용 서브넷)에 배치한다.
5. IF Quick VPC Endpoint 생성이 실패하면, THEN THE Terraform 구성 SHALL 에러 메시지에 해당 리전의 Quick VPC Endpoint 서비스 가용 여부 확인을 안내하는 설명을 포함한다.
6. THE Terraform 구성 SHALL Quick VPC Endpoint에 프로젝트 표준 태그(Name, Project: BOS-AI, Environment: prod, ManagedBy: terraform, Layer: network)를 부여한다.

### 요구사항 2: Quick 계정 및 Enterprise Edition 구성 (RBAC 파이프라인 연계)

**사용자 스토리:** DevOps 엔지니어로서, Quick Enterprise Edition 계정을 Terraform으로 프로비저닝하고, 기존 Enterprise RBAC 자동 프로비저닝 파이프라인과 연계하여 사용자 관리를 IAM Identity Center 기반으로 자동화하고 싶다.

#### 인수 조건

1. THE Terraform 구성 SHALL Quick 계정을 Enterprise Edition으로 생성하며, 인증 방식을 IAM Identity Center로 설정하여 RBAC_Pipeline과 통합한다.
2. THE Terraform 구성 SHALL Quick 계정의 기본 네임스페이스에 관리자 사용자를 IAM Identity Center 그룹 기반으로 등록한다.
3. THE Terraform 구성 SHALL Quick 서비스 역할(IAM Role)을 생성하며, Quick_Data_S3 버킷에 대한 읽기/쓰기 권한과 기존 RAG 관련 S3 버킷에 대한 읽기 전용 권한을 부여한다.
4. THE Terraform 구성 SHALL Quick 서비스 역할에 OpenSearch_Collection에 대한 읽기 전용 접근 권한(`aoss:APIAccessAll`)을 부여한다.
5. IF Quick 계정이 이미 존재하면, THEN THE Terraform 구성 SHALL 기존 계정을 data source로 참조하여 중복 생성을 방지한다.
6. THE Terraform 구성 SHALL IAM Identity Center에 Quick 역할별 그룹(QS_Admin_Users, QS_Author_Users, QS_Viewer_Users)을 생성하고, RBAC_Pipeline의 GROUP_MAP에 Quick 서비스 항목(`quicksight-admin`, `quicksight-author`, `quicksight-viewer`)을 추가한다.
7. THE Terraform 구성 SHALL Quick 계정의 사용자 프로비저닝을 IAM Identity Center 그룹 멤버십 기반으로 구성하여, QS_Admin_Users 그룹 멤버는 관리자 역할, QS_Author_Users 그룹 멤버는 작성자 역할, QS_Viewer_Users 그룹 멤버는 뷰어 역할로 자동 매핑되도록 한다.
8. WHEN RBAC_Pipeline의 Provisioner_Lambda가 Quick 관련 그룹에 사용자를 추가하면, THE Quick 계정 SHALL IAM Identity Center 동기화를 통해 해당 사용자를 적절한 Quick 역할로 자동 프로비저닝한다.
9. WHEN RBAC_Pipeline의 Provisioner_Lambda가 Quick 관련 그룹에서 사용자를 제거하면, THE Quick 계정 SHALL IAM Identity Center 동기화를 통해 해당 사용자의 Quick 접근 권한을 자동으로 해제한다.

### 요구사항 3: Quick 전용 S3 버킷을 통한 데이터 주권 확보

**사용자 스토리:** 보안 담당자로서, Quick에서 업로드하거나 사용하는 모든 데이터가 자체 관리 S3 버킷에 저장되어, 데이터 주권을 확보하고 접근을 통제하고 싶다.

#### 인수 조건

1. THE Terraform 구성 SHALL Quick_Data_S3 버킷(`s3-quicksight-data-bos-ai-seoul-prod`)을 Seoul 리전에 생성하며, 버전 관리를 활성화한다.
2. THE Terraform 구성 SHALL Quick_Data_S3 버킷에 KMS 고객 관리형 키(CMK)를 사용한 서버 측 암호화(SSE-KMS)를 적용한다.
3. THE Terraform 구성 SHALL Quick_Data_S3 버킷에 퍼블릭 액세스 차단(Block Public Access)을 모든 항목에 대해 활성화한다.
4. THE Terraform 구성 SHALL Quick_Data_S3 버킷 정책에서 VPC Endpoint를 통한 접근만 허용하는 조건(`aws:sourceVpce`)을 설정한다.
5. THE Terraform 구성 SHALL Quick_Data_S3 버킷에 수명 주기 정책을 설정하여, 90일 이후 Intelligent-Tiering으로 전환하고 365일 이후 Glacier로 전환한다.
6. THE Terraform 구성 SHALL Quick_Data_S3 버킷에 S3 서버 액세스 로깅을 활성화하여 기존 로깅 버킷에 로그를 저장한다.
7. THE Terraform 구성 SHALL Quick_Data_S3 버킷에 프로젝트 표준 태그를 부여한다.

### 요구사항 4: Quick VPC Connection을 통한 데이터 소스 연결 (Virginia 직접 접근 차단)

**사용자 스토리:** 데이터 분석가로서, Quick에서 기존 BOS-AI RAG 시스템의 OpenSearch 데이터를 직접 조회하여 대시보드를 구성할 수 있도록, Quick과 VPC 내 데이터 소스 간 네트워크 연결을 구성하고 싶다. 단, Virginia 리전에 대한 직접 접근은 차단하고, 모든 트래픽은 Seoul_VPC를 경유하여 VPC Peering을 통해서만 Virginia_VPC에 도달해야 한다.

#### 인수 조건

1. THE Terraform 구성 SHALL Quick_VPC_Connection을 생성하여 Quick이 Seoul_VPC의 Private 서브넷에 ENI를 배치하도록 구성한다.
2. THE Terraform 구성 SHALL Quick_VPC_Connection에 전용 Security Group을 생성하며, 아웃바운드 규칙으로 Seoul_VPC CIDR(10.10.0.0/16) 내 VPC Peering 경유 경로와 RAG_API 포트(443)로의 트래픽만 허용한다.
3. THE Terraform 구성 SHALL Quick_VPC_Connection의 Security Group에 인바운드 규칙으로 Quick 서비스 ENI로부터의 응답 트래픽을 허용한다.
4. THE Terraform 구성 SHALL Quick에서 OpenSearch_Collection을 데이터 소스로 등록하며, Quick_VPC_Connection → Seoul_VPC → VPC Peering → Virginia_VPC 경로를 통해 접근하도록 구성한다. Quick_VPC_Connection이 Virginia_VPC(10.20.0.0/16)에 직접 연결하는 것을 허용하지 않는다.
5. THE Terraform 구성 SHALL Quick_VPC_Connection의 Security Group 아웃바운드 규칙에서 Virginia_VPC CIDR(10.20.0.0/16)을 직접 대상으로 지정하지 않으며, Seoul_VPC의 VPC Peering 라우팅을 통해서만 Virginia_VPC 트래픽이 전달되도록 한다.
6. THE Terraform 구성 SHALL Seoul_VPC의 라우팅 테이블에 Virginia_VPC CIDR(10.20.0.0/16) 대상 트래픽을 기존 VPC Peering Connection으로 라우팅하는 경로가 Quick_VPC_Connection ENI가 배치된 서브넷에도 적용되도록 구성한다.
7. THE Terraform 구성 SHALL Quick에서 Quick_Data_S3를 데이터 소스로 등록하며, Quick 서비스 역할을 통해 접근하도록 구성한다.
8. IF Quick_VPC_Connection 생성 시 서브넷의 가용 IP가 부족하면, THEN THE Terraform 구성 SHALL 에러 메시지에 서브넷 CIDR 확장 또는 대체 서브넷 사용을 안내하는 설명을 포함한다.
9. THE OPA 정책 SHALL Quick_VPC_Connection의 Security Group에 Virginia_VPC CIDR(10.20.0.0/16)을 직접 대상으로 하는 아웃바운드 규칙이 포함되지 않았는지 검증하는 규칙을 포함한다.

### 요구사항 5: Quick에서 RAG API 연동 (비용/성능 최적화 포함)

**사용자 스토리:** 데이터 분석가로서, Quick 대시보드에서 기존 BOS-AI RAG 시스템에 질의를 보내고 결과를 시각화하여, RAG 시스템의 검색 품질과 사용 패턴을 분석하고 싶다. 동시에 Lambda 사용량 폭발을 방지하기 위한 비용/성능 최적화 전략이 적용되어야 한다.

#### 인수 조건

1. THE Terraform 구성 SHALL Quick에서 RAG_API를 커스텀 데이터 소스로 연결하기 위한 Lambda 함수(`lambda-quick-rag-connector-seoul-prod`)를 생성한다.
2. THE Lambda 함수 SHALL RAG_API에 질의를 전송하고 응답을 Quick이 소비할 수 있는 테이블 형식(JSON 배열)으로 변환한다.
3. THE Lambda 함수 SHALL Seoul_VPC의 Private 서브넷에 배포되며, RAG_API의 VPC Endpoint를 통해 통신한다.
4. WHEN Quick 대시보드에서 RAG 데이터 새로고침을 요청하면, THE Lambda 함수 SHALL RAG_API로부터 최근 질의 로그, 인용 통계, 검색 유형별 성능 데이터를 조회하여 반환한다.
5. IF RAG_API 호출이 실패하면, THEN THE Lambda 함수 SHALL 에러를 CloudWatch에 기록하고 Quick에 빈 데이터셋과 에러 메시지를 반환한다.
6. THE Lambda 함수 SHALL IAM 역할을 통해 RAG_API에 접근하며, 별도의 API 키나 자격 증명을 코드에 포함하지 않는다.
7. THE Terraform 구성 SHALL Lambda 함수에 Reserved Concurrency를 설정하여(최대 동시 실행 수 10개), Quick에서의 대량 호출로 인한 Lambda 사용량 폭발을 방지하고 계정 전체 Lambda 동시 실행 한도에 영향을 주지 않도록 한다.
8. THE Terraform 구성 SHALL RAG_API 앞단의 API Gateway에 사용량 계획(Usage Plan)을 설정하여, Quick 전용 API Key에 대해 초당 요청 수(throttle rate: 10 req/s)와 일일 요청 할당량(quota: 5,000 req/day)을 제한한다.
9. THE Lambda 함수 SHALL RAG_API 응답 결과를 Quick_Data_S3에 캐싱하고, 동일한 질의 패턴에 대해 캐시 유효 기간(TTL: 1시간) 내에는 RAG_API를 재호출하지 않고 캐싱된 데이터를 반환한다.
10. THE Terraform 구성 SHALL Quick 데이터셋의 SPICE 새로고침 스케줄을 설정하여, RAG 데이터를 실시간이 아닌 주기적(기본 1시간 간격)으로 갱신하도록 구성하고, SPICE 캐시를 통해 대시보드 조회 시 Lambda 호출을 최소화한다.
11. THE Terraform 구성 SHALL CloudWatch에 Lambda 함수의 동시 실행 수(ConcurrentExecutions)와 스로틀 횟수(Throttles)를 모니터링하는 알람을 생성하며, 스로틀이 5분간 5회를 초과하면 SNS 토픽으로 알림을 전송한다.

### 요구사항 6: MCP 브릿지 서버와 Quick 연결

**사용자 스토리:** 반도체 설계 엔지니어로서, MCP 브릿지를 통해 Quick 대시보드 데이터를 Obot 채팅에서 조회할 수 있도록, MCP 브릿지에 Quick 연동 도구를 추가하고 싶다.

#### 인수 조건

1. THE MCP_Bridge SHALL `quick_dashboard_list` 도구를 추가하여, Quick API를 통해 사용 가능한 대시보드 목록을 조회하고 반환한다.
2. THE MCP_Bridge SHALL `quick_dashboard_data` 도구를 추가하여, 지정된 대시보드 ID의 데이터셋 요약 정보를 조회하고 반환한다.
3. THE MCP_Bridge SHALL Quick API 호출 시 Quick_API_Endpoint(VPC Endpoint)를 통해 통신하며, 퍼블릭 엔드포인트를 사용하지 않는다.
4. WHEN `quick_dashboard_list` 또는 `quick_dashboard_data` 도구가 호출되면, THE MCP_Bridge SHALL IAM 자격 증명(환경 변수 또는 인스턴스 프로파일)을 사용하여 Quick API에 인증한다.
5. IF Quick API 호출이 실패하면, THEN THE MCP_Bridge SHALL 에러 메시지를 사용자에게 반환하고 로그에 기록한다.

### 요구사항 7: Private 네트워크 트래픽 통제 및 검증

**사용자 스토리:** 보안 담당자로서, Quick 관련 모든 트래픽이 Private 네트워크 내에서만 흐르는지 검증하고, 인터넷으로의 트래픽 유출을 방지하고 싶다.

#### 인수 조건

1. THE Terraform 구성 SHALL Quick 관련 서브넷의 라우팅 테이블에 인터넷 게이트웨이(IGW) 또는 NAT 게이트웨이로의 경로가 포함되지 않도록 구성한다.
2. THE Terraform 구성 SHALL Quick 관련 Security Group의 아웃바운드 규칙에서 0.0.0.0/0 대상 트래픽을 허용하지 않으며, 명시적으로 허용된 CIDR 대상으로만 트래픽을 제한한다.
3. THE Terraform 구성 SHALL Quick 관련 서브넷에 Network ACL을 적용하여, 허용된 VPC CIDR(10.10.0.0/16, 10.20.0.0/16, 192.128.0.0/16)과 AWS 서비스 CIDR 외의 트래픽을 차단한다.
4. THE Terraform 구성 SHALL VPC Flow Logs를 Quick 관련 ENI에 대해 활성화하여, 모든 트래픽을 CloudWatch Logs에 기록한다.
5. THE OPA 정책 SHALL Quick 관련 Security Group에 0.0.0.0/0 아웃바운드 규칙이 포함되지 않았는지 검증하는 규칙을 포함한다.
6. THE OPA 정책 SHALL Quick 관련 S3 버킷에 퍼블릭 액세스 차단이 활성화되어 있는지 검증하는 규칙을 포함한다.

### 요구사항 8: Route53 Private DNS 구성

**사용자 스토리:** DevOps 엔지니어로서, 온프레미스에서 Quick 서비스에 접근할 때 Private DNS를 통해 VPC Endpoint로 라우팅되도록, DNS 구성을 확장하고 싶다.

#### 인수 조건

1. THE Terraform 구성 SHALL Private_Hosted_Zone에 Quick API 엔드포인트에 대한 CNAME 또는 Alias 레코드를 생성하여, `quick.rag.corp.bos-semi.com`이 Quick_API_Endpoint의 DNS 이름으로 해석되도록 한다.
2. THE Terraform 구성 SHALL 기존 Route53 Resolver Endpoints를 활용하여, 온프레미스 DNS 서버에서 `quick.rag.corp.bos-semi.com` 도메인의 조건부 전달(Conditional Forwarding)이 가능하도록 구성한다.
3. WHEN 온프레미스 클라이언트가 `quick.rag.corp.bos-semi.com`을 조회하면, THE Route53 Resolver SHALL 해당 요청을 Private_Hosted_Zone으로 전달하여 Quick_API_Endpoint의 Private IP를 반환한다.
4. IF Private_Hosted_Zone에 Quick 관련 레코드 생성이 실패하면, THEN THE Terraform 구성 SHALL 에러 메시지에 Hosted Zone ID와 VPC 연결 상태 확인을 안내하는 설명을 포함한다.

### 요구사항 9: Quick 접근 제어 및 IAM 정책

**사용자 스토리:** 보안 담당자로서, Quick 서비스에 대한 접근을 최소 권한 원칙에 따라 제어하고, 역할별로 적절한 권한을 부여하고 싶다.

#### 인수 조건

1. THE Terraform 구성 SHALL Quick 관리자 IAM 역할(`role-quicksight-admin-bos-ai-seoul-prod`)을 생성하며, Quick 계정 관리, 사용자 관리, 데이터 소스 관리 권한을 부여한다.
2. THE Terraform 구성 SHALL Quick 뷰어 IAM 역할(`role-quicksight-viewer-bos-ai-seoul-prod`)을 생성하며, 대시보드 조회 권한만 부여한다.
3. THE Terraform 구성 SHALL Quick 작성자 IAM 역할(`role-quicksight-author-bos-ai-seoul-prod`)을 생성하며, 대시보드 생성/편집 및 데이터셋 조회 권한을 부여한다.
4. THE Terraform 구성 SHALL 모든 Quick IAM 역할에 IP 기반 조건(`aws:SourceIp`)을 추가하여, 온프레미스 CIDR(192.128.0.0/16)과 VPC CIDR(10.10.0.0/16)에서의 접근만 허용한다.
5. THE Terraform 구성 SHALL Quick IAM 역할에 VPC Endpoint 조건(`aws:sourceVpce`)을 추가하여, Quick_API_Endpoint를 통한 접근만 허용한다.
6. THE Terraform 구성 SHALL 모든 Quick IAM 정책에 프로젝트 표준 태그를 부여한다.

### 요구사항 10: Quick 통합 모니터링 및 로깅

**사용자 스토리:** DevOps 엔지니어로서, Quick 서비스의 사용 현황과 오류를 모니터링하여, 문제를 조기에 감지하고 대응하고 싶다.

#### 인수 조건

1. THE Terraform 구성 SHALL CloudTrail에서 Quick 관련 API 호출(`quicksight:*`)을 기록하도록 이벤트 셀렉터를 구성한다.
2. THE Terraform 구성 SHALL CloudWatch에 Quick VPC Endpoint의 상태를 모니터링하는 알람을 생성하며, Endpoint 상태가 비정상일 때 SNS 토픽으로 알림을 전송한다.
3. THE Terraform 구성 SHALL CloudWatch에 Quick_Data_S3 버킷의 크기와 객체 수를 모니터링하는 대시보드 위젯을 생성한다.
4. WHEN Quick VPC Connection의 네트워크 인터페이스 상태가 `available`이 아닌 경우, THE CloudWatch 알람 SHALL SNS 토픽으로 알림을 전송한다.
5. THE Terraform 구성 SHALL Quick 관련 모든 CloudWatch 로그 그룹에 90일 보존 기간을 설정한다.
