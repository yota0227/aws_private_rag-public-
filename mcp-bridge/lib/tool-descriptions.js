/**
 * lib/tool-descriptions.js — 도구별 설명·disambiguation 상수
 *
 * Spec: .kiro/specs/mcp-tool-optimization/ (Task 10.1, design "lib/tool-descriptions.js")
 *
 * 도구별 설명 문자열을 한 곳에 모아 일관성과 상호 배타성을 보장한다.
 * 각 설명은 다음을 포함한다(Req 1.1, 1.2, 1.5, 1.8):
 *   (a) 목적
 *   (b) 각 입력의 의미
 *   (c) 최소 1개의 구체 예시
 *   (d) 겹치는 query 입력을 갖는 도구는 "이 도구를 쓸 때 / 다른 도구를 쓸 때"를
 *       형제 도구의 정확한 등록명을 인용해 명시
 *
 * 특히 rag_query / search_rtl / search_archive 3개는 서로를 정확한 등록명으로
 * 상호 참조한다. design.md의 "Tool-selection guidance 표"(Req 1.6)는
 * 아래 SELECTION_GUIDANCE 상수로 코드화되어 있다.
 *
 * 본 모듈은 순수 데이터(문자열/구조체)만 export한다. server.js나 도구 등록은
 * 본 모듈에서 변경하지 않는다(그 재배선은 Task 10.2 소관).
 *
 * CommonJS — server.js와 동일.
 */

/**
 * 기존 17개 도구의 정확한 등록명 (server.js와 1:1 일치, 변경 금지).
 */
const EXISTING_TOOL_NAMES = [
  "rag_query",
  "rag_list_documents",
  "rag_categories",
  "rag_upload_status",
  "rag_extract_status",
  "rag_delete_document",
  "search_rtl",
  "search_archive",
  "get_evidence",
  "list_verified_claims",
  "generate_hdd_section",
  "publish_markdown",
  "trace_signal_path",
  "find_instantiation_tree",
  "find_clock_crossings",
  "graph_export",
  "regenerate_stale_hdd",
];

/**
 * 신규 4개 도구의 정확한 등록명 (Task 13/15/16에서 등록될 예정, 설명만 선반영).
 */
const NEW_TOOL_NAMES = [
  "rag_validate_answer",
  "rag_index_status",
  "rag_read_resource",
  "rag_task_status",
];

/**
 * 도구명 -> 설명 문자열.
 *
 * 겹치는 query 입력을 갖는 검색 3종(rag_query / search_rtl / search_archive)은
 * 서로를 정확한 등록명으로 교차 인용하여 오선택을 방지한다(Req 1.2, 1.5).
 */
const TOOL_DESCRIPTIONS = {
  // ── 검색 3종 (query 입력이 겹침 → 상호 disambiguation 필수) ──────────────

  rag_query:
    "[목적] 업로드된 문서(스펙 PDF·설계 문서·주간 보고서 등)를 자연어로 질의해 답변을 생성합니다. " +
    "[입력] query(필수): 자연어 질의 내용으로 한국어/영어 모두 가능. " +
    "[예시] query=\"UCIE PHY 초기화 시퀀스를 요약해줘\" → 등록된 스펙/설계 문서에서 근거를 찾아 답변. " +
    "[이 도구를 쓸 때] 사람이 작성해 업로드한 문서(PDF·MD·보고서)에 대한 자연어 질의. " +
    "[다른 도구를 쓸 때] RTL/SoC 설계 데이터(모듈명·포트·신호·인스턴스·레지스터맵·계층구조)는 'search_rtl'을 사용하세요 " +
    "— rag_query는 RTL을 색인하지 않아 '근거 없음'으로 답할 수 있습니다. " +
    "Archive 문서를 topic/source 메타데이터로 필터링해 찾을 때는 'search_archive'를 사용하세요(rag_query는 아카이브 메타 필터를 지원하지 않습니다).",

  search_rtl:
    "[목적] 🔧 RTL/SoC 설계 데이터 검색 (1순위 도구). 모듈명·포트·신호·인스턴스·레지스터맵·계층구조·토픽 등 RTL 관련 질문에 가장 먼저 사용합니다. " +
    "RTL 코드(.v/.sv/.vhd)뿐 아니라 firmware 헤더, 레지스터맵(SVD/JSON), 설계 문서(MD/RST), timing constraint(SDC), device tree(DTS), filelist hierarchy도 검색됩니다. " +
    "[입력] query(필수): 모듈명·신호명·레지스터명·키워드. pipeline_id(선택): 파이프라인 ID 필터(예: tt_20260221, tt_20260516), 생략 시 전체 검색. " +
    "topic(선택): 토픽 필터(예: NoC, FPU, EDC, Overlay, Hierarchy), 생략 시 전체 검색. max_results(선택, 기본 50): 최대 결과 수. " +
    "[예시] query=\"tt_noc_router 포트 정리\", topic=\"NoC\" → 해당 모듈의 입출력 포트/신호를 반환. " +
    "[이 도구를 쓸 때] RTL/SoC 설계 산출물에 대한 모든 질의. " +
    "[다른 도구를 쓸 때] 업로드된 스펙 PDF·설계 문서·보고서에 대한 자연어 질의는 'rag_query'를 사용하세요(search_rtl은 RTL 전용). " +
    "Archive 문서를 topic/source 메타데이터로 필터링할 때는 'search_archive'를 사용하세요(아카이브 전용).",

  search_archive:
    "[목적] Archive 문서를 검색합니다. Bedrock KB 벡터 검색 + topic/source 메타데이터 필터를 지원합니다. 특정 주제나 출처의 아카이브 문서를 찾을 때 사용합니다. " +
    "[입력] query(필수): 검색 질의(한국어/영어 가능). topic(선택): topic 필터(예: ucie/phy/ltssm). " +
    "source(선택): source 필터(예: archive_md, rtl_parsed, manual_upload). max_results(선택, 기본 5): 최대 결과 수. " +
    "[예시] query=\"LTSSM 상태 전이\", topic=\"ucie/phy/ltssm\", source=\"archive_md\" → 해당 topic/source로 좁힌 아카이브 결과를 반환. " +
    "[이 도구를 쓸 때] Archive 문서를 topic/source 메타데이터로 필터링해 검색. " +
    "[다른 도구를 쓸 때] 업로드된 스펙 PDF·설계 문서에 대한 일반 자연어 질의는 'rag_query'를 사용하세요(search_archive는 KB 아카이브 메타필터 전용). " +
    "RTL/SoC 설계 데이터(모듈·포트·신호·인스턴스)는 'search_rtl'을 사용하세요(RTL 전용).",

  // ── 문서 관리 5종 (상호 배타) ─────────────────────────────────────────────

  rag_list_documents:
    "[목적] 업로드된 RAG 문서의 파일 목록을 조회합니다. 어떤 파일이 등록되어 있는지 확인하거나 파일 관리(삭제 등) 목적으로 사용합니다. " +
    "[입력] team(선택): 팀 필터(예: soc), 생략 시 전체 조회. category(선택): 카테고리 필터(예: code, spec), 생략 시 전체 조회. " +
    "[예시] team=\"soc\", category=\"spec\" → soc 팀의 spec 카테고리 문서 목록. " +
    "[이 도구를 쓸 때] 등록된 파일의 '목록' 확인. " +
    "[다른 도구를 쓸 때] 문서 내용 검색이나 질문 답변은 'rag_query'를 사용하세요. KB Sync 상태 확인은 'rag_upload_status'를 사용하세요.",

  rag_categories:
    "[목적] RAG 시스템에 등록된 팀/카테고리 목록을 조회합니다. " +
    "[입력] 없음. " +
    "[예시] (입력 없이 호출) → soc 등 등록된 팀과 각 팀의 카테고리 목록을 반환. " +
    "[이 도구를 쓸 때] 사용 가능한 team/category 값을 알아내 'rag_list_documents'·'search_rtl' 등의 필터 값으로 쓸 때.",

  rag_upload_status:
    "[목적] 최근 업로드된 RAG 문서 목록과 KB Sync 상태를 조회합니다. " +
    "[입력] team(선택): 팀 필터. category(선택): 카테고리 필터. " +
    "[예시] team=\"soc\" → soc 팀 최근 업로드 문서와 각 파일의 KB Sync 상태. " +
    "[이 도구를 쓸 때] 방금 올린 문서가 KB에 동기화됐는지 확인. " +
    "[다른 도구를 쓸 때] 인덱스 version·freshness·embedding model 같은 인덱스 상태는 'rag_index_status'를 사용하세요(rag_upload_status는 문서 KB sync 상태이지 인덱스 상태가 아님).",

  rag_extract_status:
    "[목적] 압축 파일 해제 작업(Extraction Task)의 상태를 조회합니다. " +
    "[입력] task_id(필수): Extraction Task ID. " +
    "[예시] task_id=\"extract-2026-0616-abc123\" → 해당 작업의 상태/처리 결과(성공·건너뜀·오류 수)를 반환. " +
    "[이 도구를 쓸 때] 업로드한 zip 등의 해제 작업 진행 상태 확인. " +
    "[다른 도구를 쓸 때] 비동기 재생성/재색인 job의 상태는 'rag_task_status'를 사용하세요(rag_extract_status는 압축 해제 작업 전용).",

  rag_delete_document:
    "[목적] RAG 지식 베이스에서 문서를 삭제합니다. S3에서 파일을 제거하고 KB Sync를 트리거합니다. " +
    "[입력] s3_key(필수): 삭제할 파일의 S3 키. " +
    "[예시] s3_key=\"documents/soc/code/filename.pdf\" → 해당 파일 삭제 + KB Sync 트리거. " +
    "[이 도구를 쓸 때] 등록된 문서를 영구 제거. 삭제 전 'rag_list_documents'로 정확한 s3_key를 확인하세요.",

  // ── claim / evidence ──────────────────────────────────────────────────────

  get_evidence:
    "[목적] 특정 Claim의 근거(evidence) 배열을 조회합니다. claim_id로 해당 claim의 원본 문서 참조·인용 텍스트·페이지 번호 등을 확인합니다. " +
    "[입력] claim_id(필수): 조회할 Claim ID(UUID). " +
    "[예시] claim_id=\"b1f9...uuid\" → 해당 claim을 뒷받침하는 evidence 목록(source/type/chunk/page/line). " +
    "[이 도구를 쓸 때] '특정 claim 한 건'의 근거를 claim 단위로 조회. " +
    "[다른 도구를 쓸 때] 검색은 'search_rtl'/'search_archive'/'rag_query'이며 근거 조회가 아닙니다. " +
    "답변 텍스트를 '문장 단위'로 근거 검증하려면 'rag_validate_answer'를 사용하세요(get_evidence는 claim 단위이지 답변 문장 단위가 아님).",

  list_verified_claims:
    "[목적] 특정 topic의 검증된(verified) Claim 목록을 조회합니다. 해당 주제에 대해 검증 완료된 지식 단위를 확인합니다. " +
    "[입력] topic(필수): topic 식별자(예: ucie/phy/ltssm). " +
    "[예시] topic=\"ucie/phy/ltssm\" → 해당 topic의 검증된 claim 목록(statement/confidence/last_verified/evidence_count). " +
    "[이 도구를 쓸 때] 검증 상태가 verified인 claim 목록을 topic별로 확인. " +
    "[다른 도구를 쓸 때] 'search_archive'는 검증 상태 필터가 아니라 메타데이터 검색입니다.",

  // ── HDD / 출판 ──────────────────────────────────────────────────────────

  generate_hdd_section:
    "[목적] 검증된 claim을 기반으로 HDD(Hardware Design Description) 섹션을 자동 생성합니다. 특정 topic의 검증+승인된 claim을 조합해 마크다운 섹션을 만듭니다. " +
    "[입력] topic(필수): topic 식별자(예: ucie/phy/ltssm). section_title(필수): 생성할 HDD 섹션 제목. " +
    "include_evidence(선택, 기본 true): evidence 각주 포함 여부. " +
    "[예시] topic=\"ucie/phy/ltssm\", section_title=\"LTSSM 상태 머신\", include_evidence=true → 근거 각주가 달린 마크다운 섹션. " +
    "[이 도구를 쓸 때] 검증된 claim으로 새 문서 섹션을 '생성'. " +
    "[다른 도구를 쓸 때] 단순 질의/검색은 'rag_query'를 사용하세요(generate_hdd_section은 생성이지 질의가 아님).",

  publish_markdown:
    "[목적] 마크다운 콘텐츠를 Seoul S3의 published/ 접두사에 저장해 출판합니다. 메타데이터가 자동 생성됩니다(source=system_generated, generation_basis=verified_claims). " +
    "[입력] content(필수): 출판할 마크다운 콘텐츠. filename(필수): 저장할 파일명(예: ucie_phy_hdd.md). " +
    "topic(선택): 관련 topic(지정 시 해당 topic의 claim 승인 상태를 확인). " +
    "[예시] filename=\"ucie_phy_hdd.md\", topic=\"ucie/phy/ltssm\", content=\"# UCIE PHY ...\" → published/에 저장. " +
    "[이 도구를 쓸 때] 검증된 콘텐츠를 최종 출판. 보통 'generate_hdd_section' 결과를 검토한 뒤 출판합니다.",

  // ── Neptune 그래프 도구 4종 ───────────────────────────────────────────────

  trace_signal_path:
    "[목적] RTL 모듈의 신호 전파 경로를 추적합니다. Neptune Graph DB에서 신호가 어떤 모듈/포트를 거쳐 전파되는지 경로를 반환합니다. " +
    "[입력] module_name(필수): 시작 모듈명(예: BLK_UCIE). signal_name(필수): 추적할 신호명(예: tx_data). " +
    "[예시] module_name=\"BLK_UCIE\", signal_name=\"tx_data\" → tx_data가 거치는 모듈/포트 경로 목록. " +
    "[이 도구를 쓸 때] '특정 신호 한 개'의 전파 경로 질의. " +
    "[다른 도구를 쓸 때] 그래프 부분집합을 통째로 추출하려면 'graph_export'를 사용하세요(graph_export는 부분그래프 추출이지 경로 추적이 아님).",

  find_instantiation_tree:
    "[목적] RTL 모듈의 인스턴스화 트리를 조회합니다. 지정 모듈이 어떤 하위 모듈을 인스턴스화하는지 트리 구조로 반환합니다. " +
    "[입력] module_name(필수): 조회할 모듈명(예: BLK_UCIE). depth(선택, 기본 3): 탐색 깊이. " +
    "[예시] module_name=\"BLK_UCIE\", depth=2 → 깊이 2까지의 하위 인스턴스 트리. " +
    "[이 도구를 쓸 때] '특정 모듈'의 하위 인스턴스 계층 질의. " +
    "[다른 도구를 쓸 때] 일반 그래프 부분집합 추출은 'graph_export'(scope=chip/module)를 사용하세요(특정 질의 전용이 아닌 추출).",

  find_clock_crossings:
    "[목적] RTL 모듈의 클럭 도메인 크로싱(CDC) 신호 목록을 조회합니다. 서로 다른 클럭 도메인 간 전달되는 신호를 식별합니다. " +
    "[입력] module_name(필수): 조회할 모듈명(예: BLK_UCIE). " +
    "[예시] module_name=\"BLK_UCIE\" → source/destination 도메인과 synchronizer를 포함한 크로싱 신호 목록. " +
    "[이 도구를 쓸 때] CDC 신호 식별 전용. " +
    "[다른 도구를 쓸 때] 일반 신호/모듈 키워드 검색은 'search_rtl'을 사용하세요(find_clock_crossings는 CDC 전용 그래프 질의).",

  graph_export:
    "[목적] Neptune 그래프의 부분집합을 JSON으로 내보냅니다. Chip/Module/Signal 3가지 scope로 그래프를 조회해 Schematic Viewer·외부 분석 도구에서 활용합니다. " +
    "[입력] scope(필수): chip(최상위 인스턴스)·module(내부 상세)·signal(신호 전파 경로) 중 하나. root_module(필수): 시작 모듈명(예: BLK_UCIE). " +
    "depth(선택, 기본 3, scope=module 시 무시): 탐색 깊이. signal_filter(선택, scope=signal 시 필수): 신호 필터. " +
    "[예시] scope=\"chip\", root_module=\"BLK_UCIE\", depth=3 → 최상위 인스턴스 노드/엣지 JSON. " +
    "[이 도구를 쓸 때] 그래프 '부분집합 전체'를 JSON으로 추출. " +
    "[다른 도구를 쓸 때] 단일 신호 경로는 'trace_signal_path', 단일 모듈 인스턴스 트리는 'find_instantiation_tree'를 사용하세요(이들은 특정 질의 전용).",

  // ── 장시간 작업 (job 반환) ────────────────────────────────────────────────

  regenerate_stale_hdd:
    "[목적] Stale 상태의 HDD 통합본 섹션을 일괄 재생성합니다. topic 전파로 stale 마킹된 섹션을 최신 claim 기반으로 다시 생성하고 placeholder를 실명으로 복구합니다. " +
    "[입력] 없음. " +
    "[예시] (입력 없이 호출) → 재생성 작업을 시작하고 job 핸들(job:// URI)을 반환. " +
    "[이 도구를 쓸 때] stale HDD 섹션 일괄 재생성(장시간 작업). 동기 결과를 기대하지 말고, 반환된 job_id를 'rag_task_status'로 polling해 완료를 확인하세요.",

  // ── 신규 4개 도구 (설명 선반영, 등록은 후속 task) ─────────────────────────

  rag_validate_answer:
    "[목적] (신규) 답변 텍스트를 문장 단위로 분할해 각 문장의 근거 유무를 검증합니다. 근거가 0건인 문장을 unsupported로 표기하고, 미지원 문장의 text/position 목록을 반환합니다. " +
    "[입력] answer(필수): 검증할 답변 텍스트. 빈 문자열/공백뿐이면 오류를 반환합니다. " +
    "[예시] answer=\"UCIE는 32 lane을 지원한다. 초기화는 LTSSM으로 수행된다.\" → 문장별 supported/unsupported 라벨과 미지원 문장 목록. " +
    "[이 도구를 쓸 때] 생성된 답변의 '문장별' 근거 검증. " +
    "[다른 도구를 쓸 때] 특정 claim 한 건의 근거 조회는 'get_evidence'를 사용하세요(get_evidence는 claim 단위이지 답변 문장 단위가 아님).",

  rag_index_status:
    "[목적] (신규) 인덱스별 상태를 조회합니다. 각 인덱스의 index_version, 마지막 성공 갱신 시각(ISO 8601 UTC), embedding model 식별자를 반환합니다. 인덱스가 없으면 빈 리스트를 반환합니다(오류 아님). " +
    "[입력] 없음. " +
    "[예시] (입력 없이 호출) → [{ index_version, last_updated_at, embedding_model }, ...]. " +
    "[이 도구를 쓸 때] 인덱스의 version·freshness·embedding model 확인. " +
    "[다른 도구를 쓸 때] 개별 문서의 KB Sync 상태는 'rag_upload_status'를 사용하세요(그쪽은 문서 동기화 상태이지 인덱스 상태가 아님).",

  rag_read_resource:
    "[목적] (신규) Resource_URI로 원문 또는 스팬을 재조회합니다. well-formed이고 존재하는 자원이면 원문/스팬을 반환합니다. " +
    "[입력] resource_uri(필수): 6개 스킴(rag/rtl/graph/claim/job/index) 중 하나의 well-formed URI(예: rtl://module/tt_noc_router). " +
    "malformed면 invalid_uri(부분 콘텐츠 없음), well-formed지만 부재면 not_found를 반환합니다. " +
    "[예시] resource_uri=\"rag://doc/ucie_spec#L10-L20\" → 해당 문서 스팬 원문. " +
    "[이 도구를 쓸 때] 검색 결과/근거에 부착된 Resource_URI로 원문을 직접 재조회. " +
    "[다른 도구를 쓸 때] 새로 찾으려면 'search_rtl'/'search_archive'/'rag_query'를 사용하세요(이들은 검색이지 URI 직접 조회가 아님).",

  rag_task_status:
    "[목적] (신규) 비동기 job의 진행 상태를 polling합니다. 알려진 job은 queued|running|done|failed 중 정확히 하나의 상태를 반환하며, done이면 결과를 포함합니다. 미지의 job_id는 not_found를 반환합니다. " +
    "[입력] job_id(필수): 조회할 job 식별자. 'regenerate_stale_hdd' 등 장시간 작업이 반환한 job:// URI의 식별자입니다. " +
    "[예시] job_id=\"a1b2c3-uuid\" → { status: \"running\" } 또는 status=done과 함께 결과. " +
    "[이 도구를 쓸 때] 'regenerate_stale_hdd'·reindex 등 장시간 작업의 완료 여부 polling. " +
    "[다른 도구를 쓸 때] 압축 해제 작업 상태는 'rag_extract_status'를 사용하세요(rag_task_status는 비동기 job 전용).",
};

/**
 * Tool-selection guidance 표 (design.md Req 1.6).
 * 질문 유형마다 정확히 하나의 권장 도구를 매핑하고, 쓰지 말아야 할 도구와 이유를 명시한다.
 *
 * 각 항목: { questionType, recommendedTool, avoid: [{ tool, reason }], note? }
 * recommendedTool / avoid[].tool 은 모두 정확한 등록명이다.
 */
const SELECTION_GUIDANCE = [
  {
    questionType: "RTL/SoC 설계 데이터: 모듈명·포트·신호·인스턴스·레지스터맵·계층구조",
    recommendedTool: "search_rtl",
    avoid: [
      { tool: "rag_query", reason: "RTL 미색인 → '근거 없음'" },
      { tool: "search_archive", reason: "아카이브 전용" },
    ],
  },
  {
    questionType: "업로드된 스펙 PDF·설계 문서·주간 보고서 자연어 질의",
    recommendedTool: "rag_query",
    avoid: [
      { tool: "search_rtl", reason: "RTL 전용" },
      { tool: "search_archive", reason: "KB 아카이브 메타필터 전용" },
    ],
  },
  {
    questionType: "Archive 문서 topic/source 메타데이터 필터 검색",
    recommendedTool: "search_archive",
    avoid: [
      { tool: "rag_query", reason: "아카이브 필터 미지원" },
      { tool: "search_rtl", reason: "RTL 전용" },
    ],
  },
  {
    questionType: "특정 claim의 근거 조회",
    recommendedTool: "get_evidence",
    avoid: [
      { tool: "search_rtl", reason: "검색이지 근거 조회 아님" },
      { tool: "search_archive", reason: "검색이지 근거 조회 아님" },
      { tool: "rag_query", reason: "검색이지 근거 조회 아님" },
    ],
  },
  {
    questionType: "topic의 검증된 claim 목록",
    recommendedTool: "list_verified_claims",
    avoid: [{ tool: "search_archive", reason: "검증 상태 필터 아님" }],
  },
  {
    questionType: "답변 텍스트의 문장별 근거 검증",
    recommendedTool: "rag_validate_answer",
    avoid: [{ tool: "get_evidence", reason: "claim 단위이지 답변 문장 단위 아님" }],
  },
  {
    questionType: "Resource_URI로 원문/스팬 재조회",
    recommendedTool: "rag_read_resource",
    avoid: [
      { tool: "search_rtl", reason: "검색이지 URI 직접 조회 아님" },
      { tool: "search_archive", reason: "검색이지 URI 직접 조회 아님" },
      { tool: "rag_query", reason: "검색이지 URI 직접 조회 아님" },
    ],
  },
  {
    questionType: "인덱스 version/freshness/embedding model",
    recommendedTool: "rag_index_status",
    avoid: [{ tool: "rag_upload_status", reason: "문서 KB sync 상태이지 인덱스 상태 아님" }],
  },
  {
    questionType: "비동기 job 진행 상태 polling",
    recommendedTool: "rag_task_status",
    avoid: [],
  },
  {
    questionType: "신호 전파 경로",
    recommendedTool: "trace_signal_path",
    avoid: [{ tool: "graph_export", reason: "부분그래프 추출이지 경로 추적 아님" }],
  },
  {
    questionType: "인스턴스화 트리",
    recommendedTool: "find_instantiation_tree",
    avoid: [{ tool: "graph_export", reason: "부분그래프 추출이지 특정 질의 아님" }],
  },
  {
    questionType: "클럭 도메인 크로싱",
    recommendedTool: "find_clock_crossings",
    avoid: [{ tool: "search_rtl", reason: "CDC 전용 그래프 질의가 아님" }],
  },
  {
    questionType: "그래프 부분집합 JSON 추출",
    recommendedTool: "graph_export",
    avoid: [
      { tool: "trace_signal_path", reason: "특정 질의 전용" },
      { tool: "find_instantiation_tree", reason: "특정 질의 전용" },
    ],
  },
  {
    questionType: "검증 claim 기반 HDD 섹션 생성",
    recommendedTool: "generate_hdd_section",
    avoid: [{ tool: "rag_query", reason: "생성이지 질의 아님" }],
  },
  {
    questionType: "검증 콘텐츠 출판",
    recommendedTool: "publish_markdown",
    avoid: [],
  },
  {
    questionType: "문서 목록 조회",
    recommendedTool: "rag_list_documents",
    avoid: [],
  },
  {
    questionType: "팀/카테고리 목록 조회",
    recommendedTool: "rag_categories",
    avoid: [],
  },
  {
    questionType: "업로드/ KB Sync 상태 조회",
    recommendedTool: "rag_upload_status",
    avoid: [{ tool: "rag_index_status", reason: "인덱스 상태이지 문서 sync 상태 아님" }],
  },
  {
    questionType: "압축 해제(Extraction) 작업 상태 조회",
    recommendedTool: "rag_extract_status",
    avoid: [{ tool: "rag_task_status", reason: "비동기 job 전용" }],
  },
  {
    questionType: "문서 삭제",
    recommendedTool: "rag_delete_document",
    avoid: [],
  },
  {
    questionType: "stale HDD 일괄 재생성(장시간)",
    recommendedTool: "regenerate_stale_hdd",
    avoid: [],
    note: "동기 결과를 기대하지 말 것 — job 반환 후 rag_task_status로 polling",
  },
];

/**
 * 모든 도구 등록명(기존 17 + 신규 4 = 21).
 */
const ALL_TOOL_NAMES = EXISTING_TOOL_NAMES.concat(NEW_TOOL_NAMES);

module.exports = {
  EXISTING_TOOL_NAMES,
  NEW_TOOL_NAMES,
  ALL_TOOL_NAMES,
  TOOL_DESCRIPTIONS,
  SELECTION_GUIDANCE,
};
