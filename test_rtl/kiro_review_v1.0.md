# N1B0_HDD_v0.1 RAG 산출 가능성 — 통합 리뷰 (Kiro)

**작성:** Kiro (IDE 기반 분석)
**작성일:** 2026-04-22
**입력 자료:**
- `claude_review_v0.1.md` — Claude Code CLI, RTL 직접 읽기 + 7계층 RCA
- `kiro_review_v0.1.md` — Kiro IDE, 파서 코드 열람 + 구현 상태 파악
- `obot_review_v0.1.md` — Obot 챗봇, 8회 검색 실험 + 런타임 데이터
- `claude_review_v1.0.md` — Claude Code, 3개 리뷰 통합본

---

## 1. 3개 플랫폼이 동일하게 지적한 것

세 플랫폼이 독립적으로 같은 결론에 도달:

> RTL 파서가 parameter/enum/struct/generate/assign을 추출하지 못하는 것이 모든 문제의 1차 원인

이건 맞아요. 그리고 이미 일부는 해결했어요.

---

## 2. 이미 해결된 것 (다른 리뷰에서 "미해결"로 분류한 항목)

| 항목 | claude_review | obot_review | 실제 상태 |
|------|-------------|-------------|-----------|
| chip_config (pkg 파라미터) | ❌ 미추출 | ❌ 없음 | ✅ 200개 pkg 파일 처리 완료, HDD 프롬프트에 포함 |
| edc_topology | 언급 없음 | ❌ assign 추적 없음 | ✅ 30개 EDC 모듈 분석, HDD에 반영 |
| noc_protocol | 언급 없음 | 부분 | ✅ 54개 NoC 모듈 분석, HDD에 반영 |
| overlay_deep | 언급 없음 | 부분 | ✅ 10개 Overlay 모듈 분석, HDD에 반영 |
| sram_inventory | ❌ 파이프라인 없음 | ❌ 없음 | ✅ 방금 구현 + 배포 완료 |
| variant_delta | ❌ 없음 | ❌ 없음 | ⚠️ 코드 구현됨, baseline RTL 업로드 필요 |
| HDD에 심화 분석 반영 | ❌ 미반영 | ❌ 미반영 | ✅ 방금 수정 — 5종 조회 + LLM 프롬프트 포함 |
| chip_config 타임아웃 | 언급 없음 | 언급 없음 | ✅ wildcard 쿼리로 해결 (200건 < 300초) |

claude_review_v0.1과 obot_review_v0.1은 오늘 오전 시점 기준이라 오후에 구현/배포한 내용이 반영 안 됨.

---

## 3. 진짜 남은 갭 (해결 안 된 것만)

### 3.1 Critical — 데이터 자체가 없음

| # | 항목 | 영향 섹션 | 해결 방안 | 난이도 |
|---|------|----------|----------|--------|
| 1 | 포트 비트폭/배열 추출 | §3 Top-Level Ports | 정규식 파서에 `[N:0]`, `[PARAM-1:0]` 패턴 추가 + pkg 값 치환 | 중 |
| 2 | generate 블록 분석 | §4 Hierarchy, §12 Verification | EMPTY block 감지, 조건부 인스턴스화 매핑 | 높 |
| 3 | assign 문 연결 추적 | §5 NoC, §6 Clock, §7 EDC, §8 Dispatch | 배열 인덱스 기반 연결 패턴 추출 | 높 |
| 4 | PRTN Daisy Chain | §9 | PRTN 포트 패턴 매칭 + 체인 토폴로지 재구성 | 중 |
| 5 | SFR 포트 그룹 | §10 Memory Config | SFR_* prefix 포트 추출 + 타일 매핑 | 중 |

### 3.2 Major — 데이터 있지만 정밀도 부족

| # | 항목 | 현재 상태 | 개선 방안 |
|---|------|----------|----------|
| 6 | Claim 모듈 귀속 오류 | FPU/Overlay가 noc2axi_router에 귀속 | HDD 생성 시 모듈-토픽 매핑 검증 |
| 7 | 검색 top-k=5 제한 | 전체의 7~13%만 조회 | max_results 파라미터 20으로 확대 |
| 8 | chip_variant 필터 없음 | Generic이 N1B0보다 높은 score | search_rtl에 chip_variant 파라미터 추가 |
| 9 | 토픽 분류 불완전 | NIU=0건, Tensix/Power/Memory 토픽 없음 | topic_classifier 규칙 확장 |

### 3.3 프롬프트 레벨 (코드 변경 없이 즉시 적용)

| # | 항목 | 적용 방법 |
|---|------|----------|
| 10 | Grounding 제약 없음 → Hallucination | 시스템 프롬프트에 "KB에 없으면 NOT IN KB 표기" 추가 |
| 11 | 영어 생성 강제 | "Generate in English" 지시 추가 |
| 12 | N1B0 섹션 우선순위 | CRITICAL/IMPORTANT/SUPPLEMENTARY 3등급 분류 |
| 13 | trinity_router 미사용 명시 | "ROUTER at Y=3 is EMPTY by design" 지시 |

---

## 4. 각 플랫폼의 고유 기여

| 플랫폼 | 고유 발견 | 다른 플랫폼에서 못 본 이유 |
|--------|----------|------------------------|
| Claude Code | MCP 병렬 호출 JSON 버그 원인 | 코드 직접 분석 필요 |
| Claude Code | S3 메타데이터 스키마 구체적 설계 | 인프라 코드 열람 필요 |
| Claude Code | 4개 trinity.sv 버전 충돌 메커니즘 | RTL 파일 직접 읽기 필요 |
| Kiro | chip_config/edc/noc/overlay 이미 해결 | 실제 코드 + 배포 상태 파악 |
| Kiro | PyVerilog AST 전환 가능성 | 파서 코드 구조 이해 필요 |
| Kiro | 정규식 파서의 구조적 한계 (RCA-8-A) | 파서 코드 직접 열람 |
| Obot | Claim 모듈 귀속 오류 (FPU→noc2axi) | 실제 검색 실험으로만 발견 |
| Obot | top-k=5 실제 커버리지 7.5% | 8회 검색 실험 데이터 |
| Obot | hdd_section 86건 단일 모듈 편중 | 런타임 데이터 분석 |

---

## 5. 개선 우선순위 (Kiro 관점)

### P0 — 즉시 (프롬프트만 수정, 코드 변경 없음)

1. Obot 시스템 프롬프트에 Grounding 제약 추가
2. 영어 생성 강제
3. N1B0 섹션 우선순위 3등급 분류
4. trinity_router EMPTY 명시 지시
5. prompt.md 섹션별 분할 쿼리 적용

### P1 — 단기 (2~4주, 파서/검색 수정)

1. MCP 병렬 호출 버그 수정 (server.js 순차 큐)
2. 포트 비트폭 추출 (handler.py 정규식 확장)
3. search_rtl에 max_results + chip_variant 파라미터 추가
4. topic_classifier에 Tensix/Power/Memory/NIU 토픽 추가
5. Claim 귀속 모듈 검증 로직

### P2 — 중기 (1~2개월, 신규 analysis_type)

1. generate_analysis — EMPTY block 감지, 조건부 인스턴스화
2. connectivity_trace — assign 문 연결 추적
3. prtn_power — PRTN 포트 그룹 + 체인 토폴로지
4. sfr_port_group — SFR 설정 신호 타일 매핑
5. PyVerilog AST 파서 전환 검토 (Phase 6b)

### P3 — 장기 (2~3개월)

1. HDD 자동 품질 검증 Lambda
2. baseline RTL 업로드 → variant_delta 활성화
3. cross_file_relationship 분석
4. 엔지니어 피드백 루프

---

## 6. 현실적 목표

| 항목 | 현재 | P0 후 | P1 후 | P2 후 |
|------|------|-------|-------|-------|
| 섹션 커버리지 | 50% | 60% | 70% | 85% |
| 파라미터 정확도 | 40% | 45% | 60% | 80% |
| Hallucination | 20% | 8% | 5% | 2% |
| N1B0 특이성 | 55% | 65% | 75% | 90% |

claude_review_v1.0의 목표치와 비교하면 좀 더 보수적이에요. 이유: 실제 배포/실행 경험상 "코드 수정 → 배포 → 검증" 사이클이 예상보다 오래 걸리고, Obot JSON 버그 같은 외부 의존성이 있어서.

---

## 7. claude_review_v1.0 대비 차이점

| 항목 | claude_review_v1.0 | kiro_review_v1.0 |
|------|-------------------|------------------|
| 이미 해결된 항목 반영 | ❌ (오전 시점 기준) | ✅ (오후 배포 반영) |
| 목표치 | 낙관적 (Phase 2: 85%) | 보수적 (Phase 2: 85%, 단 P1 선행 필수) |
| RCA 구조 | 8계층 21개 | 3등급 13개 (실행 가능성 중심) |
| 실행 순서 | Phase 0~3 병렬 가능 | P0→P1→P2 순차 (의존성 있음) |
| PyVerilog AST | 언급 없음 | P2에서 검토 (Phase 6b) |
| Claim 귀속 오류 | Obot 발견으로 기록 | P1에서 해결 (모듈-토픽 매핑 검증) |
