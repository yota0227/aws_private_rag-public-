# Requirements Document

**Feature:** EDA Tool Guide 자산화 (Tool Guide RAG)

> **Created:** 2026-06-16
> **Updated:** 2026-06-18
> **Purpose:** EDA 툴 가이드 문서(Synopsys/Cadence/Siemens user guide·command reference·methodology guide)를 별도 파이프라인의 검색 가능한 RAG 자산으로 만들어, 엔지니어가 코드/스크립트 작성 중 근거 기반 툴 사용법을 조회할 수 있게 하는 MVP 요구사항 정의.
> **Spec / Project:** `.kiro/specs/eda-tool-guide-rag/`
> **Status:** Draft
> **Owner:** BOS-AI Private RAG

## Introduction

EDA Tool Guide 자산화는 EDA 벤더 툴 가이드 문서를 전용 corpus로 수집·파싱·임베딩하여, 엔지니어가 TCL·Makefile·툴 플로우 등 코드/스크립트를 작성할 때 정확한 명령어·옵션·플로우 단계를 추측이 아닌 근거(출처) 기반으로 조회할 수 있도록 하는 기능이다.

설계 원칙은 기존 `aws_private_rag` RTL RAG 스택(S3 업로드 + Cross-Region Replication, Bedrock 임베딩 + 벡터 인덱스, DynamoDB 객체/메타데이터, MCP 노출)을 **재사용**하는 것이다. 새 스택을 신설하지 않는다. 파싱은 `document_rag_parsing_embedding_strategy.md`의 결정론적 라벨 기반 파서 철학을 툴 가이드 구조(command/option 블록, flow 섹션, example)에 맞게 적용한다.

이 Tool Guide RAG는 RTL RAG와 **분리된 파이프라인·분리된 corpus·분리된 MCP 노출**로 운영되어, 파이프라인 단위로 접근 권한을 독립 관리할 수 있어야 한다. 권한 관리의 상세 설계(LiteLLM gateway, fine-grained corpus ACL)는 본 spec 범위가 아니며 방향성 참조(`NPU_SOC_RTL_RAG_MCP_Improvement_Report.md`)로만 둔다.

본 spec은 의도적으로 좁게 범위를 잡은 MVP다. 아래 "Non-Goals"의 항목은 본 spec에서 다루지 않는다.

### Non-Goals (범위 외 / 향후 단계)

- RTL RAG와 Tool Guide RAG를 결합한 cross-domain 질의.
- RTL RAG + Tool Guide를 함께 사용하는 Codex testbench 생성(사용자의 향후 비전).
- LiteLLM gateway 및 fine-grained corpus ACL 전체 설계(`NPU_SOC_RTL_RAG_MCP_Improvement_Report.md`는 방향 참조만).
- DV evaluation harness, agent orchestration, PD/timing(`llm_eda_rag_implementation_report.md` — 향후).

> **참고:** PDF 다이어그램·블록도·레지스터맵 페이지의 Vision 기반 파싱은 Requirement 7로 **본 spec 범위에 포함**된다.

## Glossary

- **Tool_Guide_Corpus**: EDA 툴 가이드 문서에서 추출한 객체를 저장하는 전용 corpus. RTL corpus와 prefix·인덱스 범위가 분리된다.
- **Tool_Guide_Ingestion**: 업로드된 툴 가이드 문서를 수집하여 파싱·임베딩 파이프라인으로 전달하는 처리 단위.
- **Tool_Guide_Parser**: 툴 가이드 문서를 결정론적 라벨/구조 규칙으로 파싱하여 command·option·flow·example 객체를 추출하는 컴포넌트.
- **Tool_Guide_Object**: 파서가 추출한 단위 레코드(command, option, flow_step, example, section). `object_type` 값은 정확히 이 집합 {command, option, flow_step, example, section}으로 닫혀 있다(추가 값 없음). 공통 스키마(id/object_type/canonical_text/metadata/evidence)를 따른다.
- **Tool_Guide_MCP**: Tool Guide Corpus를 조회하는 엔지니어용 MCP 도구 집합. RTL MCP 도구와 노출이 분리된다.
- **Tool_Guide_RAG**: Tool_Guide_Corpus·Tool_Guide_Ingestion·Tool_Guide_Parser·Tool_Guide_MCP를 포함하는 전체 파이프라인.
- **Evidence**: 객체가 유래한 출처 정보(문서명, doc_version, 페이지/섹션).
- **doc_version**: 툴 가이드 문서의 버전(툴 릴리스 또는 문서 리비전).
- **Vision_Parser**: PDF 페이지를 이미지로 렌더링하여 Bedrock Claude Vision으로 텍스트 설명을 생성하는 Tool_Guide_Parser의 선택적 서브컴포넌트.

## Requirements

### Requirement 1: 툴 가이드 문서 수집 (기존 인프라 재사용)

**User Story:** 엔지니어로서, EDA 툴 가이드 문서(PDF/Markdown)를 업로드하면 전용 Tool Guide Corpus에 수집되기를 원한다. 그래야 새 인프라 없이 기존 RTL RAG 스택 위에서 툴 가이드를 검색할 수 있다.

#### Acceptance Criteria

1. WHEN 사용자가 EDA 툴 가이드 문서를 지정된 S3 업로드 prefix에 등록하면, THE Tool_Guide_Ingestion SHALL 해당 문서를 기존 S3 업로드 + Cross-Region Replication 경로를 통해 수집한다.
2. WHEN 문서 수집이 완료되면, THE Tool_Guide_Ingestion SHALL 해당 문서를 Tool_Guide_Corpus prefix에 저장하고 RTL corpus prefix에는 기록하지 않는다.
3. WHERE 입력 문서 형식이 PDF 또는 Markdown인 경우, THE Tool_Guide_Ingestion SHALL 해당 문서를 파싱 대상으로 전달한다.
4. IF 업로드된 문서가 PDF 또는 Markdown이 아닌 형식인 경우, THEN THE Tool_Guide_Ingestion SHALL 처리를 중단하고, 원본 문서를 변경 없이 보존하며, 형식 미지원 사유를 식별 가능한 오류 상태로 기록한다.
5. THE Tool_Guide_Ingestion SHALL 기존 Bedrock 임베딩 모델·벡터 인덱스·DynamoDB 테이블·MCP 노출 메커니즘을 재사용하며, 신규 임베딩 모델·벡터 인덱스·DynamoDB 테이블을 생성하지 않는다.
6. WHEN 동일한 업로드 prefix와 파일명으로 문서가 재업로드되면, THE Tool_Guide_Ingestion SHALL 기존 항목을 최신 문서로 교체하고 중복 항목을 생성하지 않는다.

### Requirement 2: 툴 가이드 구조 기반 결정론적 파싱

**User Story:** 엔지니어로서, 툴 가이드의 command·option·flow·example 구조가 검색 가능한 단위 객체로 분해되기를 원한다. 그래야 특정 명령어나 옵션을 정확히 찾을 수 있다.

#### Acceptance Criteria

1. WHEN Tool_Guide_Parser가 툴 가이드 문서를 처리하면, THE Tool_Guide_Parser SHALL command 블록, option 정의, flow 섹션, example을 각각 별도의 Tool_Guide_Object로 추출한다.
2. THE Tool_Guide_Parser SHALL 각 Tool_Guide_Object의 텍스트 경계(시작·종료 오프셋), `type` 분류, `belongs_to` 관계를 라벨·구조 규칙 기반의 결정론적 추출만으로 결정하고, LLM 추론은 canonical_text 문장 생성 및 figure/예시 요약 등 보조 용도로만 사용한다.
3. WHEN 하나의 command 객체가 추출되면, THE Tool_Guide_Parser SHALL 해당 command에 속한 option 객체를 `belongs_to` 관계로 연결한다.
4. IF 추출된 option 객체가 어떤 command 객체에도 속하지 않는 경우, THEN THE Tool_Guide_Parser SHALL 해당 option을 `belongs_to` 관계가 없는 독립 Tool_Guide_Object로 보존한다.
5. IF 특정 구간이 정의된 구조 규칙으로 파싱되지 않는 경우, THEN THE Tool_Guide_Parser SHALL 해당 구간 원문을 section 객체로 보존하고, 추출된 모든 Tool_Guide_Object의 텍스트 경계 합집합이 원문 텍스트(공백 제외)의 100%를 커버하도록 한다.
6. THE Tool_Guide_Parser SHALL 각 Tool_Guide_Object에 대해 단일 임베딩 대상(canonical_text)을 생성한다.
7. WHEN 동일한 입력 문서를 2회 이상 반복 처리하면, THE Tool_Guide_Parser SHALL 추출된 Tool_Guide_Object의 개수, 각 객체의 텍스트 경계 오프셋, `type` 분류, `belongs_to` 관계가 모든 처리 회차에서 동일하도록 한다.
8. IF 입력 문서가 비어 있거나 지원되지 않는 형식인 경우, THEN THE Tool_Guide_Parser SHALL 추출을 중단하고 처리 불가 사유를 나타내는 오류를 반환하며 부분 추출 결과를 저장하지 않는다.

### Requirement 3: 툴 가이드 객체 메타데이터 스키마

**User Story:** 엔지니어로서, 검색 결과가 어떤 툴·버전·명령어·섹션에서 왔는지 메타데이터로 구분되기를 원한다. 그래야 다른 툴이나 다른 버전의 정보를 혼동하지 않는다.

#### Acceptance Criteria

1. THE Tool_Guide_Object SHALL `tool_name`, `tool_version`, `command`, `option`, `section`, `doc_version`, `object_type` 7개 메타데이터 필드를 모두 포함하며, 각 필드는 문자열 타입으로 항상 존재한다(값이 없을 경우 criterion 4의 미확인 표기를 따른다).
2. WHEN Tool_Guide_Object가 생성될 때, THE Tool_Guide_Parser SHALL `object_type` 필드 값을 사전(Glossary)에 정의된 허용 값 집합 중 하나로 설정하고, 허용 값에 없으면 해당 객체를 생성하지 않는다.
3. THE Tool_Guide_Object SHALL 출처 정보를 담은 `evidence` 필드를 포함하며, 이 필드는 `문서명`, `doc_version`, 그리고 `페이지` 또는 `섹션` 중 최소 1개를 반드시 포함한다.
4. IF 특정 메타데이터 필드 값 또는 `evidence` 하위 항목이 원문에서 확인되지 않는 경우, THEN THE Tool_Guide_Parser SHALL 해당 필드를 고정 문자열 `"미확인"`으로 표기하고, 추정값·임의값·기본값을 생성하지 않는다.
5. THE Tool_Guide_Object SHALL RTL corpus 객체와 동일한 공통 레코드 형태(`id`, `object_type`, `canonical_text`, `metadata`, `evidence` 5개 최상위 필드)를 따르며, 5개 필드를 모두 포함한다.
6. WHEN Tool_Guide_Parser가 `id` 및 `doc_id` 식별자를 생성할 때, THE Tool_Guide_Parser SHALL 식별자 생성 입력값(`tool_name`, `doc_version`, `filename`)을 결정론적으로 정규화(대소문자 통일 및 앞뒤 공백 제거)한 후 사용하여, 동일한 논리적 문서를 입력 대소문자·공백 변형과 무관하게 반복 수집하더라도 동일한 `id` 및 `doc_id`를 생성한다.

### Requirement 4: 엔지니어용 MCP 질의 도구 (근거 인용 포함)

**User Story:** 엔지니어로서, 코드/스크립트 작성 중 툴 가이드 corpus를 MCP로 질의하여 명령어·옵션·플로우 사용법을 출처와 함께 받기를 원한다. 그래야 추측 대신 근거 기반으로 스크립트를 작성할 수 있다.

#### Acceptance Criteria

1. THE Tool_Guide_MCP SHALL 툴명 또는 명령어 기준 검색 도구를 제공하며, 검색 문자열 입력을 최대 256자까지 허용한다.
2. THE Tool_Guide_MCP SHALL 자연어 질의 도구를 제공하며, 질의 입력을 최대 8,192자까지 허용한다.
3. WHEN Tool_Guide_MCP가 질의에 응답하면, THE Tool_Guide_MCP SHALL 관련도 내림차순으로 정렬된 최대 20개의 결과 항목을 반환한다.
4. WHEN Tool_Guide_MCP가 질의에 응답하면, THE Tool_Guide_MCP SHALL 각 결과 항목에 대해 출처(문서명, doc_version, 페이지 또는 섹션) 인용을 포함한다.
5. IF 결과 항목에 문서명·doc_version·페이지 또는 섹션 중 하나라도 누락된 경우, THEN THE Tool_Guide_MCP SHALL 해당 항목을 결과에서 제외하고 반환하지 않는다.
6. IF 질의에 대해 corpus에서 근거를 찾지 못한 경우, THEN THE Tool_Guide_MCP SHALL "현재 index에서 확인 불가"를 반환하고 근거 없는 명령어·옵션을 생성하지 않는다.
7. WHEN Tool_Guide_MCP가 질의를 수신하면, THE Tool_Guide_MCP SHALL 질의 수신 시점부터 10초 이내에 결과 또는 오류 응답을 반환한다.
8. WHERE 질의에 `tool_name` 또는 `tool_version`이 지정된 경우, THE Tool_Guide_MCP SHALL 해당 조건에 일치하는 객체로 검색 범위를 한정한다.
9. IF 질의의 `tool_name` 또는 `tool_version`과 일치하는 객체가 corpus에 없는 경우, THEN THE Tool_Guide_MCP SHALL 빈 결과와 함께 "일치하는 객체 없음"을 반환한다.
10. IF 질의가 문자 길이 검사를 통과했으나 임베딩 모델(Bedrock Titan Embed Text v2, 입력 토큰 윈도 8,192 토큰)의 입력 토큰 한도를 초과하는 경우, THEN THE Tool_Guide_MCP SHALL 해당 질의를 식별 가능한 토큰 한도 초과 오류로 거부하고 부분 결과를 반환하지 않는다(문자 길이 검사는 저비용 사전 검증 가드이며, 구속력 있는 강제 한도는 임베딩 모델의 입력 토큰 윈도이다).

### Requirement 5: 분리된 파이프라인 · 분리된 MCP · 파이프라인별 접근 제어

**User Story:** 운영자로서, Tool Guide RAG가 RTL RAG와 분리된 파이프라인·corpus·MCP로 운영되기를 원한다. 그래야 파이프라인 단위로 접근 권한을 독립적으로 관리할 수 있다.

#### Acceptance Criteria

1. THE Tool_Guide_Corpus SHALL RTL corpus와 저장소 및 벡터 인덱스를 공유하지 않는 독립 corpus로 구성되며, 고유 식별자로 구분된다.
2. THE Tool_Guide_MCP SHALL RTL RAG MCP 도구와 이름 및 노출 집합이 겹치지 않는 분리된 도구 집합으로 노출된다.
3. THE Tool_Guide_RAG SHALL 파이프라인(corpus + MCP 노출)을 단위로 접근 권한을 설정할 수 있도록, 다른 파이프라인과 중복되지 않는 단일 파이프라인 식별자를 부여받는다.
4. WHEN 사용자가 Tool Guide 파이프라인에 질의를 요청하면, THE Tool_Guide_MCP SHALL 해당 사용자의 Tool Guide 파이프라인 접근 권한 보유 여부를 검사한다.
5. IF 사용자가 Tool Guide 파이프라인에 대한 접근 권한이 없으면, THEN THE Tool_Guide_MCP SHALL Tool_Guide_Corpus 결과를 반환하지 않고 권한 없음을 나타내는 오류 응답을 반환한다.
6. WHILE 사용자가 Tool Guide 파이프라인에 대한 접근 권한을 보유한 상태인 경우, THE Tool_Guide_MCP SHALL Tool_Guide_Corpus 결과만 반환하며 RTL corpus 결과를 혼입하지 않는다.

### Requirement 6: 단계적 MVP 구현 (점진 도입)

**User Story:** 엔지니어로서, 첫 단계에서는 단일 문서·핵심 객체(command/option)만으로 빠르게 검증되기를 원한다. 그래야 과도한 초기 설계 없이 가치를 먼저 확인할 수 있다.

#### Acceptance Criteria

1. THE Tool_Guide_RAG SHALL 단일 툴 가이드 문서와 command·option 두 가지 객체 유형만으로 자연어 검색 질의를 처리하는 최소 동작(MVP) 범위를 제공하며, flow·example·section 등 그 외 객체 유형은 MVP 범위에서 제외한다.
2. WHEN 사용자가 1자 이상 8,192자 이하의 자연어 질의를 입력하면, THE Tool_Guide_RAG SHALL 인덱싱된 command·option 객체를 대상으로 검색하여 관련도 순으로 정렬된 결과 목록(최대 20건)을 반환한다.
3. IF 검색 결과가 0건이면, THEN THE Tool_Guide_RAG SHALL 빈 결과 목록과 함께 일치하는 항목이 없음을 나타내는 응답을 반환하고, 오류 없이 정상 상태를 유지한다.
4. IF 질의가 비어 있거나 8,192자를 초과하면, THEN THE Tool_Guide_RAG SHALL 해당 질의를 거부하고 입력 길이 위반을 나타내는 오류 응답을 반환한다.
5. WHERE 추가 문서 유형 또는 추가 객체 유형(flow·example·section)이 도입되는 경우, THE Tool_Guide_RAG SHALL 공통 객체 스키마의 기존 필드 정의와 기존 파이프라인 단계 구성을 수정하지 않고, 신규 유형을 추가 정의만으로 수용한다.

### Requirement 7: PDF 다이어그램 Vision 파싱 (텍스트 희소 페이지 보완)

**User Story:** 엔지니어로서, 툴 가이드 PDF의 다이어그램·블록도·레지스터맵 페이지가 텍스트가 거의 없더라도 내용이 검색되기를 원한다. 그래야 "Clock domain crossing 다이어그램 찾아줘" 같은 질의에도 시각적 설계 정보를 근거로 받을 수 있다.

#### Acceptance Criteria

1. WHERE PDF 페이지의 추출된 텍스트 길이가 100자 미만(비공백 기준)인 경우, THE Tool_Guide_Parser SHALL 해당 페이지를 Vision 처리 대상으로 분류한다.
2. WHEN Vision 처리 대상 페이지가 감지되면, THE Tool_Guide_Parser SHALL 해당 페이지를 이미지(PNG)로 렌더링하여 Bedrock Converse API(Claude)에 전달하고, 다이어그램의 구성 요소·신호 흐름·레이블을 포함한 텍스트 설명을 생성한다.
3. WHEN Vision 처리가 성공하면, THE Tool_Guide_Parser SHALL 생성된 설명을 해당 페이지의 section 또는 example 객체의 canonical_text로 저장하며, 기존 텍스트 기반 파싱과 동일한 공통 스키마(R3.5)를 따른다.
4. IF Vision 처리가 실패하거나 비활성화 설정인 경우, THEN THE Tool_Guide_Parser SHALL 해당 페이지를 기존 방식(원문 텍스트 보존 또는 section 객체)으로 처리하고 파싱 전체를 중단하지 않는다.
5. THE Tool_Guide_Parser SHALL Vision 처리 여부를 환경 변수(`ENABLE_VISION_PARSING`, 기본값 false)로 제어할 수 있도록 한다(비활성화 시 추가 비용 없음).
6. WHEN Vision 처리를 수행할 때, THE Tool_Guide_Parser SHALL 임베딩은 기존 Titan Embed v2를 재사용하며 신규 임베딩 모델을 도입하지 않는다(R1.5 준수).
