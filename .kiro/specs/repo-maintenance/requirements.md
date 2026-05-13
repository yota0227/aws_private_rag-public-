# 요구사항 문서: 레포지토리 메인터넌스

## 소개

Codex(OpenAI) 코드 리뷰 결과를 기반으로 BOS-AI Private RAG 레포지토리의 기술 부채와 보안/정합성 문제를 체계적으로 해결한다. 발견된 9가지 문제를 P0(즉시), P1(단기), P2(중기) 우선순위로 분류하여 순차적으로 수정한다.

## 용어 정의

- **Build_Pipeline**: Lambda 배포 패키지(zip)를 소스 코드로부터 생성하고 Terraform이 참조하는 빌드 프로세스
- **Repo_Hygiene_Tool**: Git에서 tracked된 불필요 아티팩트를 식별하고 제거하는 스크립트 또는 프로세스
- **MCP_Bridge**: Node.js 기반 MCP SSE 브릿지 서버 (Obot ↔ RAG API Gateway 연결)
- **Network_Policy**: OpenSearch Serverless의 네트워크 접근 정책 (AllowFromPublic 설정 포함)
- **VPC_Module**: `modules/network/vpc/main.tf`에 정의된 재사용 가능한 VPC Terraform 모듈
- **API_Gateway**: `environments/app-layer/bedrock-rag/api-gateway.tf`에 정의된 Private REST API
- **Document_Processor**: `environments/app-layer/bedrock-rag/lambda_src/index.py`의 Lambda 함수
- **Terraform_Formatter**: `terraform fmt` 명령으로 HCL 코드 스타일을 표준화하는 도구
- **Private_Principle**: product.md에 명시된 "IGW/NAT 없음, 퍼블릭 엔드포인트 없음" 설계 원칙

## 요구사항

### 요구사항 1: Lambda 배포 패키지 소스 동기화 (P0)

**사용자 스토리:** 인프라 운영자로서, Lambda 소스 코드 변경이 실제 배포에 반영되도록 하고 싶다. 그래야 코드 수정 후 배포 누락으로 인한 장애를 방지할 수 있다.

#### 인수 조건

1. WHEN 소스 코드(`lambda_src/`, `lambda/document-processor/`)가 변경될 때, THE Build_Pipeline SHALL 변경된 소스로부터 새로운 배포 zip 파일을 생성하여 `source_code_hash`가 갱신되도록 한다
2. THE Build_Pipeline SHALL `lambda-deployment-package.zip`과 `rtl-parser-deployment-package.zip`을 소스 디렉토리로부터 자동 생성하는 빌드 스크립트를 제공한다
3. IF 배포 zip 파일이 소스 코드와 해시가 불일치하면, THEN THE Build_Pipeline SHALL 빌드 스크립트 실행 시 경고 메시지를 출력한다
4. THE Build_Pipeline SHALL `.gitignore`에 `lambda-deployment-package.zip`, `lambda-deploy.zip`, `rtl-parser-deployment-package.zip`을 추가하여 바이너리 아티팩트가 Git에 추적되지 않도록 한다

### 요구사항 2: 레포지토리 위생 정리 (P0)

**사용자 스토리:** 개발자로서, 레포지토리에서 불필요한 아티팩트와 중첩 복제본을 제거하고 싶다. 그래야 레포 크기를 줄이고 혼란을 방지할 수 있다.

#### 인수 조건

1. THE Repo_Hygiene_Tool SHALL `__pycache__/`, `*.pyc`, `package.zip`, `*.tfplan`, `terraform_*.log` 파일을 Git 추적에서 제거한다
2. THE Repo_Hygiene_Tool SHALL `backups/backups/`, `backup_before_pull_20260226_164722/` 등 중첩 복제본 디렉토리를 식별하고 제거한다
3. THE Repo_Hygiene_Tool SHALL `.gitignore`에 `__pycache__/`, `*.pyc`, `**/*.tfplan`, `**/terraform_*.log`, `**/lambda-deployment-package.zip`, `**/lambda-deploy.zip`, `**/*.zip` (Lambda 패키지) 패턴을 추가한다
4. WHEN 정리 스크립트가 실행되면, THE Repo_Hygiene_Tool SHALL 제거 대상 파일 목록을 출력하고 확인 후 `git rm --cached`를 실행한다
5. THE Repo_Hygiene_Tool SHALL `.terraform/` 디렉토리, `.terraform.lock.hcl` 파일이 Git에 추적되지 않도록 `.gitignore` 규칙을 검증한다

### 요구사항 3: MCP Bridge 빌드 정합성 (P0)

**사용자 스토리:** 개발자로서, MCP Bridge Docker 이미지가 정상적으로 빌드되도록 하고 싶다. 그래야 배포 시 빌드 실패를 방지할 수 있다.

#### 인수 조건

1. THE MCP_Bridge SHALL `package-lock.json` 파일을 레포지토리에 포함하여 `npm ci` 명령이 정상 실행되도록 한다
2. THE MCP_Bridge SHALL `package.json`의 `dependencies`에 `zod` 패키지를 추가한다 (`server.js`에서 `require('zod')` 사용)
3. WHEN `docker build`가 실행되면, THE MCP_Bridge SHALL 빌드 오류 없이 이미지를 생성한다
4. THE MCP_Bridge SHALL `package.json`에서 사용하지 않는 의존성(`@aws-sdk/client-quicksight`)을 제거한다

### 요구사항 4: OpenSearch 네트워크 정책 Private 전환 (P1)

**사용자 스토리:** 보안 담당자로서, OpenSearch Serverless가 VPC 엔드포인트를 통해서만 접근 가능하도록 하고 싶다. 그래야 Private_Principle을 준수할 수 있다.

#### 인수 조건

1. THE Network_Policy SHALL `AllowFromPublic`을 `false`로 변경한다
2. THE Network_Policy SHALL `AllowFromPublic = false` 설정 시 VPC 엔드포인트 ID를 `SourceVPCEs` 목록에 명시한다
3. WHEN OpenSearch 네트워크 정책이 적용되면, THE Network_Policy SHALL VPC 엔드포인트를 통한 접근만 허용하고 퍼블릭 접근을 차단한다
4. IF `AllowFromPublic`이 `true`로 설정된 Terraform 코드가 존재하면, THEN THE Network_Policy SHALL `terraform plan` 실행 시 해당 설정을 감지하고 수정을 요구한다

### 요구사항 5: VPC 모듈 Public Subnet/IGW/NAT 제거 (P1)

**사용자 스토리:** 네트워크 엔지니어로서, VPC 모듈에서 Public Subnet, IGW, NAT Gateway 관련 코드를 제거하거나 비활성화하고 싶다. 그래야 Private_Principle과 실제 인프라 코드가 일치한다.

#### 인수 조건

1. THE VPC_Module SHALL `public_subnet_cidrs` 변수의 기본값을 빈 리스트(`[]`)로 설정한다
2. THE VPC_Module SHALL `enable_nat_gateway` 변수의 기본값을 `false`로 설정한다
3. WHEN `public_subnet_cidrs`가 빈 리스트이면, THE VPC_Module SHALL IGW, Public Route Table, NAT Gateway 리소스를 생성하지 않는다
4. THE VPC_Module SHALL `environments/network-layer/main.tf`의 `vpc_logging` 모듈에서 `public_subnet_cidrs`와 `enable_nat_gateway` 설정을 제거하거나 빈 값으로 변경한다
5. IF Logging VPC에 NAT Gateway가 운영상 필요한 경우, THEN THE VPC_Module SHALL 해당 사유를 주석으로 명시하고 product.md에 예외 사항을 문서화한다

### 요구사항 6: API Gateway 인증 강화 (P1)

**사용자 스토리:** 보안 담당자로서, API Gateway 메서드에 IAM 인증 또는 Lambda Authorizer를 적용하고 싶다. 그래야 VPCE 제한 외에 추가적인 접근 제어가 가능하다.

#### 인수 조건

1. THE API_Gateway SHALL 모든 메서드의 `authorization` 속성을 `"NONE"`에서 `"AWS_IAM"` 또는 커스텀 Authorizer로 변경한다
2. WHEN API 요청이 인증 없이 수신되면, THE API_Gateway SHALL HTTP 403 응답을 반환한다
3. THE API_Gateway SHALL `/rag/health` 엔드포인트는 헬스체크 목적으로 `authorization = "NONE"`을 유지할 수 있으며, 해당 예외를 주석으로 문서화한다
4. IF IAM 인증이 적용되면, THEN THE API_Gateway SHALL 온프레미스 클라이언트(Obot/MCP Bridge)가 SigV4 서명을 사용하여 API를 호출할 수 있도록 IAM 역할과 정책을 제공한다

### 요구사항 7: Provider/Region 경계 명확화 (P2)

**사용자 스토리:** 인프라 운영자로서, 멀티 리전 모듈 호출 시 provider가 명시적으로 전달되도록 하고 싶다. 그래야 리소스가 의도하지 않은 리전에 생성되는 것을 방지할 수 있다.

#### 인수 조건

1. THE Build_Pipeline SHALL `environments/app-layer/bedrock-rag/main.tf`에서 `s3_pipeline` 모듈 호출 시 `providers` 블록을 명시적으로 전달한다
2. WHEN Terraform 모듈이 멀티 리전 리소스를 생성하면, THE Build_Pipeline SHALL 해당 모듈에 `providers` 매핑을 명시적으로 선언한다
3. THE Build_Pipeline SHALL 모든 environment 디렉토리의 모듈 호출에서 provider 전달 누락이 없는지 검증하는 체크리스트를 제공한다

### 요구사항 8: 업로드/압축 해제 경로 검증 (P2)

**사용자 스토리:** 보안 담당자로서, 파일 업로드 및 압축 해제 시 경로 순회(Path Traversal) 공격을 방지하고 싶다. 그래야 악의적인 파일명으로 인한 S3 키 오염을 차단할 수 있다.

#### 인수 조건

1. WHEN 압축 파일이 해제될 때, THE Document_Processor SHALL 각 파일의 경로가 지정된 추출 디렉토리 내에 있는지 검증한다
2. IF 압축 파일 내 항목의 경로가 `../` 또는 절대 경로를 포함하면, THEN THE Document_Processor SHALL 해당 항목을 건너뛰고 경고 로그를 기록한다
3. WHEN S3 객체 키가 생성될 때, THE Document_Processor SHALL 파일명에서 특수 문자(`..`, `/`, `\`, null byte)를 제거하거나 거부한다
4. THE Document_Processor SHALL `zipfile.extractall()` 대신 개별 파일을 순회하며 경로를 검증한 후 추출하는 안전한 추출 함수를 사용한다
5. THE Document_Processor SHALL `tarfile.extractall()` 대신 `tarfile.data_filter` 또는 수동 경로 검증을 적용한다

### 요구사항 9: Terraform 코드 포맷 표준화 (P2)

**사용자 스토리:** 개발자로서, 모든 Terraform 코드가 `terraform fmt` 표준을 준수하도록 하고 싶다. 그래야 코드 리뷰 시 포맷 차이로 인한 불필요한 diff를 줄일 수 있다.

#### 인수 조건

1. THE Terraform_Formatter SHALL `modules/network/` 디렉토리의 모든 `.tf` 파일에 `terraform fmt`를 적용한다
2. THE Terraform_Formatter SHALL 레포지토리 전체에 `terraform fmt -recursive`를 실행하여 포맷 불일치를 수정한다
3. WHEN CI/CD 파이프라인이 실행되면, THE Terraform_Formatter SHALL `terraform fmt -check -recursive`를 실행하여 포맷 불일치 시 빌드를 실패시킨다
4. THE Terraform_Formatter SHALL 포맷 검증 스크립트를 `scripts/` 디렉토리에 추가한다
