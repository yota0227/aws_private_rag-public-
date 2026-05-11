# RAG HDD 품질 개선 — Kiro 실행 계획 v1.1

**작성:** Kiro
**작성일:** 2026-04-22
**목적:** 구현 가능한 개선 항목만 정리. 분석은 끝났으니 뭘 고칠지, 어떤 순서로 할지만.

---

## 현재 위치

오늘 해결한 것:
- chip_config 200개 pkg 파일 처리 (타임아웃 해결)
- sram_inventory 신규 구현 + 배포
- HDD Generator에 심화 분석 5종 조회 + LLM 프롬프트 포함
- 10개 토픽 HDD 재생성 트리거

아직 안 한 것: 아래 전부

---

## 개선 항목 (구현 순서대로)

### Round 1 — 코드 변경 없음, 프롬프트만

| # | 뭘 하나 | 어디서 | 효과 |
|---|--------|--------|------|
| 1 | prompt.md에 Grounding 제약 추가 | `test_rtl/rag_result/prompt.md` | Hallucination 20%→8% |
| 2 | "Generate in English" 지시 | prompt.md | 한국어 혼재 제거 |
| 3 | trinity_router EMPTY 명시 | prompt.md | 계층 역전 오류 제거 |
| 4 | max_results=20 요청 | prompt.md | 데이터 커버리지 4배 |

예상 소요: 30분. Obot에서 바로 테스트 가능.

---

### Round 2 — 파서 코드 수정 (handler.py)

| # | 뭘 하나 | 파일 | 구체적 변경 |
|---|--------|------|-----------|
| 5 | 포트 비트폭 추출 | `handler.py` `parse_rtl_to_ast()` | 정규식에 `\[[\w\s:\-\+]+\]` 캡처 추가. `input [SizeX-1:0] i_ai_clk` → `"input [SizeX-1:0] i_ai_clk"` |
| 6 | pkg 파라미터 값 치환 | `handler.py` 또는 신규 함수 | chip_config 결과에서 `SizeX=4` 가져와서 `[SizeX-1:0]` → `[3:0]` 치환 |
| 7 | SFR 포트 그룹 분류 | `topic_classifier.py` | `SFR_*` prefix → `Memory` 토픽 추가 |
| 8 | PRTN 포트 그룹 분류 | `topic_classifier.py` | `PRTN*`, `ISO_EN` → `Power` 토픽 추가 |
| 9 | NIU 토픽 분리 | `topic_classifier.py` | `tt_noc2axi_*`, `tt_niu_*` → `NIU` 토픽 (NoC와 분리) |

예상 소요: 반나절. 단위 테스트 포함.

---

### Round 3 — 검색 인터페이스 확장

| # | 뭘 하나 | 파일 | 구체적 변경 |
|---|--------|------|-----------|
| 10 | max_results 파라미터 | `handler.py` `_search_rtl()` | `max_results` 기본값 5→20, event에서 읽기 |
| 11 | analysis_type 필터 | `handler.py` `_search_rtl()` | 이미 있음 — MCP Bridge에서 전달만 추가 |
| 12 | MCP Bridge search_rtl 확장 | 온프레미스 `server.js` | `max_results`, `analysis_type` 파라미터 추가 |

예상 소요: 2시간. 서버 접속 필요.

---

### Round 4 — Claim 귀속 오류 수정

| # | 뭘 하나 | 파일 | 구체적 변경 |
|---|--------|------|-----------|
| 13 | HDD 생성 시 토픽-모듈 매핑 검증 | `analysis_handler.py` `handle_hdd_generation()` | claim의 module_name이 해당 토픽의 실제 모듈 계층에 속하는지 검증. 불일치 시 제외. |
| 14 | Claim 생성 시 모듈 계층 기반 귀속 | `analysis_handler.py` `handle_claim_generation()` | classify_topic 결과와 hierarchy 위치 교차 검증 |

예상 소요: 반나절.

---

### Round 5 — 신규 analysis_type (큰 작업)

| # | 뭘 하나 | 난이도 | 커버 섹션 |
|---|--------|--------|----------|
| 15 | generate_analysis | 높음 | §4 Hierarchy, §12 Verification |
| 16 | connectivity_trace (assign 추적) | 높음 | §5 NoC, §6 Clock, §7 EDC, §8 Dispatch |
| 17 | prtn_power | 중간 | §9 PRTN Chain |

이건 별도 스펙으로 파는 게 맞아요. 각각 요구사항 → 설계 → 구현 → 테스트 사이클 필요.

---

## 안 할 것 (지금은)

| 항목 | 이유 |
|------|------|
| PyVerilog AST 전환 | Lambda에 PyVerilog 의존성 추가하려면 ECR 컨테이너 전환 필요. 비용 대비 효과 불확실. Round 2의 정규식 확장으로 80% 커버 가능. |
| S3 메타데이터 chip_variant | 기존 업로드된 9,465개 파일 재태깅 필요. pipeline_id로 이미 격리되어 있어서 급하지 않음. |
| HDD 자동 품질 검증 Lambda | Round 1~4 개선 후 수동 검증으로 충분. 자동화는 반복 사이클이 안정화된 후. |
| MCP 병렬 호출 버그 | Obot 측 문제. "도구 1회만 호출" 프롬프트로 우회 중. 서버 inotify 이슈도 있어서 근본 해결은 Obot 업데이트 대기. |

---

## 실행 순서 요약

```
Round 1 (프롬프트) → Obot에서 v3 HDD 테스트
    ↓ 결과 확인
Round 2 (파서 수정) → Lambda 배포 → 재파싱 → v4 HDD 테스트
    ↓ 결과 확인
Round 3 (검색 확장) → MCP Bridge 업데이트 → v5 HDD 테스트
    ↓ 결과 확인
Round 4 (귀속 수정) → Lambda 배포 → Claim 재생성 → v6 HDD 테스트
    ↓ 결과 확인
Round 5 (신규 분석) → 별도 스펙 → 구현 → v7 HDD 테스트
```

각 Round 후 Sample 대비 비교해서 커버리지 측정. 목표 도달하면 멈춤.

| Round | 예상 커버리지 | 예상 Hallucination |
|-------|-------------|-------------------|
| 현재 | 50% | 20% |
| Round 1 후 | 60% | 8% |
| Round 2 후 | 68% | 5% |
| Round 3 후 | 72% | 5% |
| Round 4 후 | 75% | 3% |
| Round 5 후 | 85% | 2% |
