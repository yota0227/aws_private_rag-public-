# N1B0_HDD_v0.1 분석 및 RAG 산출 가능성 평가 (Kiro)

## 문서 특성

이 문서는 "칩 레벨 통합 HDD"로, trinity.sv 탑 모듈의 구조를 RTL 소스 코드에서 직접 추출한 정보로 구성됨. 엔지니어가 RTL을 읽으면서 작성한 것이 아니라, RTL 파싱 + 구조 분석으로 자동 생성된 문서.

핵심: 이 문서의 정보는 거의 100% RTL 소스 코드에서 추출 가능한 데이터.

---

## 섹션별 RAG 산출 가능성

| # | 섹션 | 내용 요약 | RAG 산출 | 현재 상태 | 갭 |
|---|------|----------|---------|----------|-----|
| 1 | Overview | N1B0 vs Baseline 차이점 요약 | ✅ 가능 | ⚠️ 부분 | variant_delta 분석 결과를 HDD에 반영하면 됨 |
| 2 | Package Constants | SizeX/Y, NumTensix, tile_t enum, GridConfig, Endpoint Table, Helper Functions | ✅ 가능 | ✅ 방금 해결 | chip_config 분석이 200개 pkg 파일 처리 완료. HDD 프롬프트에 포함됨 |
| 3 | Top-Level Ports | 파라미터(AXI_SLV_*), 클럭/리셋 배열 폭, APB ×4, EDC APB+IRQ, AXI Slave/Master, SFR, PRTN, ISO_EN | ⚠️ 부분 가능 | ❌ 부족 | 포트 비트폭/배열 인덱스가 module_parse에서 정확히 추출 안 됨. 정규식 파서가 [SizeX-1:0] 같은 파라미터 참조 폭을 해석 못함 |
| 4 | Module Hierarchy | Level-1 인스턴스 맵, NOC2AXI_ROUTER dual-row 설명, 포트 그룹 매핑 | ✅ 가능 | ⚠️ 부분 | hierarchy 추출은 됨. 하지만 "dual-row span" 같은 설계 의도 설명은 LLM이 claim에서 추론해야 함 |
| 5 | NoC Fabric | Y축/X축 연결, 리피터 4/6 스테이지, 수동 assign | ✅ 가능 | ⚠️ 부분 | noc_protocol 분석 + 리피터 인스턴스 정보는 있음. 하지만 "manual assigns" 같은 코딩 스타일 차이는 RTL diff 수준 |
| 6 | Clock & Reset Routing | clock_routing_t struct, 진입점, 전파 경로, NOC2AXI_ROUTER 예외 | ⚠️ 부분 가능 | ❌ 부족 | struct 필드 추출은 가능. 전파 경로 설명은 LLM 추론 필요 |
| 7 | EDC Ring | per-tile 인터페이스, 컬럼별 체인, loopback, NOC2AXI_ROUTER 예외 | ✅ 가능 | ✅ 방금 해결 | edc_topology 분석 결과가 HDD 프롬프트에 포함됨 |
| 8 | Dispatch Feedthrough | de_to_t6 신호, 수평/수직 브로드캐스트, NOC2AXI_ROUTER 피드스루 | ⚠️ 부분 가능 | ❌ 없음 | "feedthrough" 개념을 명시적으로 식별하는 로직 없음 |
| 9 | PRTN Daisy Chain | 파티션 체인 토폴로지, per-column Y=2→1→0 | ❌ 현재 불가 | ❌ 없음 | PRTN 전용 분석 스테이지 없음 |
| 10 | Memory Config (SFR) | SRAM 설정 신호 브로드캐스트 테이블 | ⚠️ 부분 가능 | ❌ 부족 | SFR 설정 신호 브로드캐스트 매핑은 별도 분석 필요 |
| 11 | RTL File Map | 모듈 → 파일 경로 매핑 | ✅ 가능 | ✅ 있음 | module_parse의 file_path 필드에서 직접 추출 가능 |
| 12 | Hierarchy Verification | Package ↔ RTL 일관성 체크, N1B0 관찰 사항 | ⚠️ 부분 가능 | ❌ 없음 | chip_config + hierarchy 교차 검증 로직이 없음 |
| 13 | Differences vs Baseline | N1B0 vs Baseline 비교 테이블 | ✅ 가능 | ⚠️ 부분 | variant_delta 구현됨. baseline RTL 별도 업로드 필요 |

---

## 종합 평가

| 평가 항목 | 점수 | 설명 |
|-----------|------|------|
| 데이터 추출 가능성 | 85% | 13개 섹션 중 11개는 RTL 파싱 데이터에서 추출 가능 |
| 현재 RAG 커버리지 | 50% | chip_config + edc_topology + noc_protocol 반영 후 |
| 즉시 개선 가능 | 70% | LLM 프롬프트 튜닝 + 기존 데이터 활용으로 도달 가능 |
| 추가 개발 필요 | 85% | 포트 비트폭, PRTN, SFR, 교차 검증 추가 시 |

---

## 현재 RAG로 산출 가능한 것 (즉시)

1. Package Constants (섹션 2) — chip_config 분석 완료
2. Module Hierarchy (섹션 4) — hierarchy 추출 완료
3. EDC Ring (섹션 7) — edc_topology 분석 완료
4. NoC Fabric (섹션 5) — noc_protocol 분석 완료
5. RTL File Map (섹션 11) — module_parse file_path
6. Differences vs Baseline (섹션 13) — variant_delta (baseline 업로드 필요)

## 현재 RAG로 부족한 것 (추가 개발 필요)

| 우선순위 | 항목 | 해결 방안 |
|---------|------|----------|
| P0 | 포트 비트폭 정확 추출 | PyVerilog AST 전환 또는 pkg 파라미터 치환 로직 |
| P1 | Clock Routing Struct | chip_config에서 struct 필드 추출 + LLM 전파 경로 추론 |
| P1 | Dispatch Feedthrough | dataflow에 feedthrough 패턴 감지 추가 |
| P2 | PRTN Daisy Chain | 새 분석 스테이지 (PRTN 포트 패턴 + 체인 토폴로지) |
| P2 | Memory Config SFR | sram_inventory에 SFR 신호 매핑 추가 |
| P2 | Hierarchy Verification | chip_config + hierarchy 교차 검증 자동화 |
