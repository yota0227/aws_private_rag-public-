# 요구사항 문서: Hardware TDD 파이프라인

## 소개

Hardware TDD 파이프라인은 SoC 개발에서 HDD(Hardware Design Document) → 테스트벤치 → RTL → 검증 → 피드백의 TDD(Test-Driven Development) 루프를 LLM + RAG 기반으로 자동화하는 시스템이다. 현재 `rtl-auto-analysis-pipeline` 스펙에서 RTL → as-built HDD 자동 추출(LLM-5)을 구현 중이며, v6까지 85% 품질 달성이 목표이다. 본 스펙은 그 이후 단계로, 나머지 TDD 루프 구성 요소를 완성한다.

SoC 개발에서 HDD는 RTL보다 먼저 작성되어야 하지만, 현실에서는 RTL이 먼저 구현되고 HDD는 outdated되거나 아예 없는 경우가 많다. 이 스펙은 다음 TDD 루프를 자동화한다:

1. HDD (설계 의도) 작성/갱신
2. HDD → UVM 테스트벤치/어서션 자동 생성 [LLM-2]
3. RTL 구현 (엔지니어 + LLM 스켈레톤 보조) [LLM-3]
4. 시뮬레이션 → FAIL → 실패 분석 [LLM-4]
5. RTL → as-built HDD 추출 [LLM-5] (rtl-auto-analysis-pipeline에서 구현 중)
6. 초안 HDD vs as-built HDD diff 분석 [LLM-6]
7. HDD 업데이트 → 테스트벤치 재생성 → 반복

본 스펙은 LLM-2(테스트벤치 생성), LLM-4(실패 분석), LLM-6(HDD diff 분석), Neptune Knowledge Graph 통합, 피드백 루프 자동화를 다룬다.

## 용어 정의

- **HDD**: Hardware Design Document — RTL 구현 전에 작성되는 하드웨어 설계 의도 문서. 모듈 개요, 기능 상세, 인터페이스 사양, 클럭/리셋 구조, 검증 체크리스트를 포함한다
- **As_Built_HDD**: RTL 코드에서 자동 추출된 HDD. `rtl-auto-analysis-pipeline`의 HDD_Section_Generator가 생성하며, 실제 구현 상태를 반영한다
- **Draft_HDD**: 엔지니어가 RTL 구현 전에 작성한 초안 HDD. 설계 의도를 담고 있으며, As_Built_HDD와 비교하여 괴리를 탐지한다
- **UVM**: Universal Verification Methodology — SystemVerilog 기반 검증 방법론. 테스트벤치, 시퀀서, 드라이버, 모니터, 스코어보드로 구성된다
- **UVM_Testbench_Generator**: HDD의 각 requirement를 SystemVerilog assertion과 UVM 테스트벤치로 변환하는 LLM 기반 컴포넌트 [LLM-2]
- **Simulation_Failure_Analyzer**: 시뮬레이션 로그를 파싱하여 실패 원인을 분석하고 수정 제안을 생성하는 LLM 기반 컴포넌트 [LLM-4]
- **HDD_Diff_Analyzer**: Draft_HDD와 As_Built_HDD를 비교하여 괴리를 탐지하고 분류하는 LLM 기반 컴포넌트 [LLM-6]
- **SVA**: SystemVerilog Assertion — RTL 설계의 속성을 형식적으로 검증하기 위한 어서션 언어
- **Coverage_Point**: 시뮬레이션에서 특정 조건이 실행되었는지 추적하는 커버리지 측정 포인트
- **Corner_Case**: 정상 동작 범위의 경계 조건에서 발생하는 특수 시나리오
- **Neptune_Knowledge_Graph**: Amazon Neptune 그래프 데이터베이스에 저장되는 RTL 모듈 간 관계 그래프
- **Feedback_Store**: 프롬프트, 결과, 엔지니어 피드백을 저장하는 DynamoDB 테이블
- **Pipeline_ID**: S3 디렉토리 네이밍에서 파생되는 파이프라인 식별자 (예: `tt_20260221`). `{chip_type}_{date}` 형식
- **TDD_Loop**: HDD → 테스트벤치 → RTL → 시뮬레이션 → 실패 분석 → HDD 갱신의 반복 주기
- **Hit_Rate**: 피드백이 후속 HDD 생성에 실제로 반영된 비율
- **RTL_S3_Bucket**: RTL 소스 코드가 업로드되는 S3 버킷 (`bos-ai-rtl-src-{account_id}`, Seoul 리전)
- **RTL_OpenSearch_Index**: RTL 파싱 및 분석 결과가 인덱싱되는 OpenSearch Serverless 인덱스 (us-east-1)
- **Bedrock_Claude**: Amazon Bedrock에서 제공하는 Claude LLM 모델 (us-east-1)
- **Titan_Embeddings**: Amazon Titan Embed Text v2 모델로 생성되는 벡터 임베딩


## 요구사항

### 요구사항 1: HDD → UVM 테스트벤치 자동 생성 (LLM-2)

**사용자 스토리:** 검증 엔지니어로서, HDD의 각 requirement가 SystemVerilog assertion과 UVM 테스트벤치로 자동 변환되기를 원한다. 이를 통해 수동으로 테스트벤치를 작성하는 시간을 절약하고, HDD 기반 TDD 루프를 시작할 수 있다.

#### 수용 기준

1. WHEN HDD 문서가 S3의 `rtl-parsed/hdd/` 경로에 존재하면, THE UVM_Testbench_Generator SHALL HDD의 각 기능 상세 섹션을 파싱하여 개별 requirement 항목을 추출한다
2. WHEN requirement 항목이 추출되면, THE UVM_Testbench_Generator SHALL Bedrock_Claude를 호출하여 각 requirement를 SVA(SystemVerilog Assertion)로 변환한다
3. THE UVM_Testbench_Generator SHALL 각 SVA에 대해 다음 정보를 포함한다: assertion_id, source_requirement, assertion_type(immediate, concurrent, cover), assertion_code, description
4. WHEN SVA가 생성되면, THE UVM_Testbench_Generator SHALL 각 assertion에 대응하는 Coverage_Point를 자동 정의한다 (functional coverage bin 포함)
5. THE UVM_Testbench_Generator SHALL HDD의 인터페이스 사양과 파라미터 범위를 분석하여 Corner_Case 시나리오를 자동 도출한다 (최소값, 최대값, 경계값, 오버플로우 조건)
6. THE UVM_Testbench_Generator SHALL UVM 환경 스켈레톤(env, agent, driver, monitor, scoreboard, sequence)을 생성하여 RTL_S3_Bucket의 `tdd-artifacts/{pipeline_id}/testbench/` 경로에 저장한다
7. WHILE UVM_Testbench_Generator가 LLM을 호출하는 동안, THE UVM_Testbench_Generator SHALL 단일 LLM 호출당 입력 토큰 수를 100,000 토큰 이하로 제한하고, 초과 시 모듈 단위로 분할하여 호출한다
8. IF LLM 호출이 실패하거나 타임아웃(60초)이 발생하면, THEN THE UVM_Testbench_Generator SHALL 해당 모듈에 대해 최대 1회 재시도하고, 재시도 실패 시 해당 모듈을 건너뛰고 오류를 기록한다
9. THE UVM_Testbench_Generator SHALL 생성된 테스트벤치 파일 목록, 생성 일시, 소스 HDD 버전을 메타데이터로 RTL_OpenSearch_Index에 `analysis_type=uvm_testbench` 문서로 인덱싱한다
10. FOR ALL 생성된 SVA에 대해, 해당 SVA에서 참조하는 신호명은 소스 HDD의 인터페이스 사양에 정의된 신호명의 부분집합이어야 한다 (참조 무결성)
11. FOR ALL 생성된 UVM 테스트벤치에 대해, 테스트벤치를 파싱하여 추출한 assertion 목록은 원본 HDD requirement 목록과 1:1 대응해야 한다 (라운드트립 속성)


### 요구사항 2: RTL vs HDD 괴리 자동 탐지 (LLM-6)

**사용자 스토리:** 설계 엔지니어로서, RTL에서 추출한 As_Built_HDD와 원본 Draft_HDD 간의 괴리가 자동으로 탐지되기를 원한다. 이를 통해 인증 전에 HDD-RTL 불일치를 사전에 차단하고, 의도적 변경과 버그를 구분할 수 있다.

#### 수용 기준

1. WHEN As_Built_HDD와 Draft_HDD가 모두 S3에 존재하면, THE HDD_Diff_Analyzer SHALL 두 문서를 섹션별로 비교하여 차이점 목록을 생성한다
2. THE HDD_Diff_Analyzer SHALL 다음 변경 유형을 자동 탐지한다: 포트 추가/삭제/변경, 파라미터 값 변경, 인스턴스 추가/삭제, 클럭 도메인 변경, 기능 상세 불일치
3. WHEN 차이점이 탐지되면, THE HDD_Diff_Analyzer SHALL Bedrock_Claude를 호출하여 각 차이점을 다음 카테고리로 분류한다: intentional_change(의도적 변경), potential_bug(잠재적 버그), documentation_gap(문서 누락), optimization(최적화 변경)
4. THE HDD_Diff_Analyzer SHALL 각 차이점에 대해 다음 정보를 포함하는 diff 리포트를 생성한다: diff_id, section, change_type, category, draft_content, as_built_content, confidence_score, recommendation
5. THE HDD_Diff_Analyzer SHALL diff 리포트를 Markdown 형식으로 RTL_S3_Bucket의 `tdd-artifacts/{pipeline_id}/diff-reports/` 경로에 저장한다
6. THE HDD_Diff_Analyzer SHALL diff 리포트를 RTL_OpenSearch_Index에 `analysis_type=hdd_diff` 문서로 인덱싱하여 검색 가능하게 한다
7. WHEN Pipeline_ID에 대해 인증(sign-off) 요청이 발생하면, THE HDD_Diff_Analyzer SHALL 자동으로 최신 diff 분석을 실행하여 미해결 불일치가 있는지 확인한다
8. IF 미해결 불일치 중 potential_bug 카테고리가 1건 이상 존재하면, THEN THE HDD_Diff_Analyzer SHALL 인증 차단 경고를 생성하고 해당 불일치 목록을 포함한 알림을 발행한다
9. FOR ALL diff 리포트에 대해, 리포트에서 참조하는 모듈명과 신호명은 As_Built_HDD 또는 Draft_HDD에 존재하는 항목의 합집합의 부분집합이어야 한다 (참조 무결성)


### 요구사항 3: 시뮬레이션 실패 분석 (LLM-4)

**사용자 스토리:** 검증 엔지니어로서, 시뮬레이션 실패 시 어떤 assertion이 실패했는지, RTL과 HDD 어디서 괴리가 발생했는지 자동으로 분석되기를 원한다. 이를 통해 실패 원인을 빠르게 파악하고 수정 방향을 결정할 수 있다.

#### 수용 기준

1. WHEN 시뮬레이션 로그 파일이 S3의 `tdd-artifacts/{pipeline_id}/sim-logs/` 경로에 업로드되면, THE Simulation_Failure_Analyzer SHALL 로그 파일을 파싱하여 실패한 assertion 목록을 추출한다
2. THE Simulation_Failure_Analyzer SHALL 각 실패한 assertion에 대해 다음 정보를 추출한다: assertion_id, failure_time, failure_count, related_signals, error_message
3. WHEN 실패한 assertion 목록이 추출되면, THE Simulation_Failure_Analyzer SHALL Bedrock_Claude를 호출하여 각 실패에 대해 RTL 코드와 HDD 간의 괴리 지점을 추적한다
4. THE Simulation_Failure_Analyzer SHALL 각 실패에 대해 다음 정보를 포함하는 실패 분석 리포트를 생성한다: failure_id, assertion_id, root_cause_category(rtl_bug, hdd_ambiguity, testbench_error, timing_issue), affected_modules, suggested_fix, confidence_score
5. THE Simulation_Failure_Analyzer SHALL root_cause_category별로 실패를 그룹화하여 우선순위 기반 수정 가이드를 생성한다
6. THE Simulation_Failure_Analyzer SHALL 실패 분석 리포트를 Markdown 형식으로 RTL_S3_Bucket의 `tdd-artifacts/{pipeline_id}/failure-reports/` 경로에 저장한다
7. THE Simulation_Failure_Analyzer SHALL 실패 분석 결과를 RTL_OpenSearch_Index에 `analysis_type=sim_failure` 문서로 인덱싱하여 검색 가능하게 한다
8. WHEN suggested_fix가 RTL 코드 수정을 포함하면, THE Simulation_Failure_Analyzer SHALL 수정 대상 파일명, 수정 위치(라인 범위), 수정 내용 스니펫을 포함한다
9. IF 시뮬레이션 로그가 10MB를 초과하면, THEN THE Simulation_Failure_Analyzer SHALL 로그를 청크 단위(1MB)로 분할하여 순차적으로 파싱하고, 실패 관련 섹션만 LLM에 전달한다
10. WHILE Simulation_Failure_Analyzer가 LLM을 호출하는 동안, THE Simulation_Failure_Analyzer SHALL 단일 LLM 호출당 입력 토큰 수를 100,000 토큰 이하로 제한한다


### 요구사항 4: Neptune Knowledge Graph 통합

**사용자 스토리:** 설계 엔지니어로서, RTL 모듈 간 관계가 그래프 데이터베이스에 저장되어 신호 전파 경로 탐색과 교차 파일 관계 추적이 가능하기를 원한다. 이를 통해 "이 신호가 어디서 시작해서 어디까지 전파되는가?" 같은 복잡한 질의에 답변을 얻을 수 있다.

#### 수용 기준

1. WHEN 계층 트리와 데이터 흐름 그래프가 생성되면, THE Neptune_Knowledge_Graph SHALL RTL 모듈을 정점(vertex)으로, 모듈 간 인스턴스화/신호 연결 관계를 간선(edge)으로 저장한다
2. THE Neptune_Knowledge_Graph SHALL 각 정점에 다음 속성을 포함한다: module_name, pipeline_id, topic, clock_domains, hierarchy_path, file_path
3. THE Neptune_Knowledge_Graph SHALL 각 간선에 다음 속성을 포함한다: edge_type(instantiation, signal_connection, clock_crossing), signal_name, direction, bit_width
4. WHEN 신호 전파 경로 질의가 수신되면, THE Neptune_Knowledge_Graph SHALL Gremlin 쿼리를 사용하여 시작 모듈에서 목적 모듈까지의 신호 전파 경로를 탐색한다
5. THE Neptune_Knowledge_Graph SHALL 교차 파일 관계 추적을 지원하여, 하나의 모듈 변경이 영향을 미치는 모든 연관 모듈 목록을 반환한다
6. WHEN OpenSearch에서 텍스트 검색 결과가 반환되면, THE Neptune_Knowledge_Graph SHALL 해당 모듈의 그래프 이웃(1-hop, 2-hop) 정보를 보강하여 컨텍스트를 확장한다
7. THE Neptune_Knowledge_Graph SHALL OpenSearch(텍스트/벡터 검색) + DynamoDB(Claim/피드백 조회) + Neptune(그래프 탐색) 3저장소 통합 질의를 지원한다
8. THE Neptune_Knowledge_Graph SHALL Pipeline_ID별로 그래프를 논리적으로 격리하여, 서로 다른 파이프라인의 모듈 관계가 혼재되지 않도록 한다
9. IF Neptune 그래프 질의가 5초 이내에 응답하지 않으면, THEN THE Neptune_Knowledge_Graph SHALL 타임아웃을 반환하고, OpenSearch 단독 검색 결과로 폴백한다
10. THE Neptune_Knowledge_Graph SHALL Seoul 리전(ap-northeast-2)에 배포되며, BOS-AI Frontend VPC 내에서 VPC Endpoint를 통해 접근한다


### 요구사항 5: 피드백 루프 자동화

**사용자 스토리:** 설계 엔지니어로서, LLM이 생성한 결과에 대한 피드백이 자동으로 저장되고 다음 생성 시 컨텍스트로 활용되기를 원한다. 이를 통해 반복적인 수정 요청 없이 LLM 출력 품질이 점진적으로 개선된다.

#### 수용 기준

1. WHEN 엔지니어가 LLM 생성 결과(HDD, 테스트벤치, 실패 분석)에 피드백을 제출하면, THE Feedback_Store SHALL 다음 정보를 DynamoDB에 저장한다: feedback_id, pipeline_id, artifact_type(hdd, testbench, failure_report, diff_report), artifact_id, feedback_text, feedback_category(correction, addition, removal, style), timestamp
2. THE Feedback_Store SHALL Pipeline_ID를 파티션 키로 사용하여 파이프라인별 피드백을 논리적으로 격리한다
3. WHEN UVM_Testbench_Generator, HDD_Diff_Analyzer, 또는 Simulation_Failure_Analyzer가 LLM을 호출할 때, THE Feedback_Store SHALL 해당 Pipeline_ID와 artifact_type에 대한 이전 피드백을 조회하여 LLM 프롬프트의 컨텍스트로 전달한다
4. THE Feedback_Store SHALL 각 피드백에 TTL(Time-To-Live)을 설정하여 90일 후 자동 만료되도록 한다
5. THE Feedback_Store SHALL 피드백의 Hit_Rate를 추적한다: 피드백이 후속 LLM 생성에 반영되었는지 여부를 기록하고, 반영률이 10% 미만인 피드백을 "low_impact"로 태깅한다
6. WHEN low_impact 피드백이 30일 이상 유지되면, THE Feedback_Store SHALL 해당 피드백을 자동 아카이브하여 활성 컨텍스트에서 제외한다
7. THE Feedback_Store SHALL 피드백 조회 시 최신 피드백을 우선 반환하고, 단일 LLM 호출에 포함되는 피드백 컨텍스트를 최대 10건으로 제한한다
8. THE Feedback_Store SHALL 피드백 통계(총 건수, 카테고리별 분포, Hit_Rate 추이)를 RTL_OpenSearch_Index에 `analysis_type=feedback_stats` 문서로 인덱싱하여 대시보드에서 조회 가능하게 한다
9. IF 피드백 저장 시 DynamoDB 쓰기가 실패하면, THEN THE Feedback_Store SHALL 최대 2회 재시도하고, 재시도 실패 시 피드백을 S3의 `tdd-artifacts/{pipeline_id}/feedback-fallback/` 경로에 JSON 파일로 저장한다
10. FOR ALL 피드백 저장 및 조회 작업에 대해, 저장된 피드백을 조회하면 원본 피드백과 동일한 내용이 반환되어야 한다 (라운드트립 속성)


### 요구사항 6: TDD 루프 오케스트레이션

**사용자 스토리:** 설계 엔지니어로서, HDD 작성부터 테스트벤치 생성, 시뮬레이션 실패 분석, HDD 갱신까지의 전체 TDD 루프가 자동으로 조율되기를 원한다. 이를 통해 수동 개입 없이 설계-검증 반복 주기를 단축할 수 있다.

#### 수용 기준

1. WHEN Draft_HDD가 S3의 `tdd-artifacts/{pipeline_id}/draft-hdd/` 경로에 업로드되면, THE TDD_Loop SHALL UVM_Testbench_Generator를 자동으로 트리거하여 테스트벤치를 생성한다
2. WHEN 시뮬레이션 로그가 S3의 `tdd-artifacts/{pipeline_id}/sim-logs/` 경로에 업로드되면, THE TDD_Loop SHALL Simulation_Failure_Analyzer를 자동으로 트리거하여 실패 분석을 수행한다
3. WHEN As_Built_HDD가 `rtl-auto-analysis-pipeline`에 의해 생성되면, THE TDD_Loop SHALL HDD_Diff_Analyzer를 자동으로 트리거하여 Draft_HDD와의 괴리를 분석한다
4. THE TDD_Loop SHALL 각 TDD 반복 주기의 상태를 추적한다: iteration_id, pipeline_id, phase(draft_hdd, testbench_gen, simulation, failure_analysis, as_built_extraction, diff_analysis, hdd_update), status(pending, in_progress, completed, failed), timestamp
5. THE TDD_Loop SHALL 반복 주기 상태를 DynamoDB에 저장하고, RTL_OpenSearch_Index에 `analysis_type=tdd_iteration` 문서로 인덱싱한다
6. WHILE TDD_Loop가 실행되는 동안, THE TDD_Loop SHALL 각 단계의 입력/출력 아티팩트 경로를 기록하여 전체 파이프라인의 추적성(traceability)을 보장한다
7. IF TDD_Loop의 특정 단계에서 오류가 발생하면, THEN THE TDD_Loop SHALL 해당 단계를 최대 2회 재시도하고, 재시도 실패 시 오류 상태를 기록하며 엔지니어에게 알림을 발행한다
8. THE TDD_Loop SHALL Step Functions 상태 머신으로 구현되며, `rtl-auto-analysis-pipeline`의 Analysis_Orchestrator와 동일한 Seoul 리전 VPC 내에서 실행된다

### 요구사항 7: 인프라 및 보안 제약

**사용자 스토리:** 인프라 운영자로서, Hardware TDD 파이프라인이 기존 BOS-AI 인프라의 보안 및 네트워크 제약을 준수하기를 원한다. 이를 통해 기존 시스템과의 호환성을 유지할 수 있다.

#### 수용 기준

1. THE TDD_Loop SHALL Seoul 리전(ap-northeast-2)의 BOS-AI Frontend VPC 내에서 실행된다
2. THE UVM_Testbench_Generator, Simulation_Failure_Analyzer, HDD_Diff_Analyzer SHALL Python 3.12 런타임과 boto3 표준 라이브러리만 사용한다
3. THE TDD_Loop SHALL OpenSearch Serverless(us-east-1)에 접근할 때 VPC Peering 경로를 통해 접근한다
4. THE UVM_Testbench_Generator, Simulation_Failure_Analyzer, HDD_Diff_Analyzer SHALL Bedrock Claude 모델 호출 시 us-east-1 리전의 Bedrock 엔드포인트를 사용한다
5. THE TDD_Loop SHALL 모든 S3 객체에 대해 KMS 암호화(SSE-KMS)를 적용한다
6. THE TDD_Loop SHALL 모든 AWS 리소스에 Project=BOS-AI, Environment, ManagedBy 태그를 포함한다
7. THE UVM_Testbench_Generator, Simulation_Failure_Analyzer, HDD_Diff_Analyzer SHALL Lambda 실행 시간이 300초를 초과하지 않도록 작업을 분할한다
8. THE Neptune_Knowledge_Graph SHALL Neptune Serverless 인스턴스로 배포되며, BOS-AI Frontend VPC 내에서 VPC Endpoint를 통해 접근한다
9. THE Feedback_Store SHALL DynamoDB 테이블에 대해 KMS 암호화를 적용하고, Pipeline_ID 기반 파티셔닝으로 접근 격리를 보장한다
10. THE TDD_Loop SHALL `rtl-auto-analysis-pipeline`의 기존 인프라 리소스(S3 버킷, OpenSearch 인덱스, DynamoDB 테이블)를 재생성하지 않고 공유한다