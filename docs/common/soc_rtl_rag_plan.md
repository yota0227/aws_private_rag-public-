# SoC RTL RAG 구축 계획

> **작성일:** 2026-06-18
> **기반:** NPU RAG v9.5 아키텍처 포크 + Spec RAG 시너지
> **목적:** SoC RTL 전체를 대상으로 하는 RAG 파이프라인 설계 개괄

---

## 1. 현황: NPU RAG v9.5 아키텍처

```
RTL 소스 (S3)
    ↓ rtl-parser Lambda
Qdrant (vector)          Neptune (graph)
    ↓                         ↓
document-processor Lambda (retrieval pipeline)
    ↓                         ↓
Claim DB (DynamoDB)      Bedrock KB
    ↓
MCP Bridge → LLM
```

**3개 저장소**: Qdrant(`bos-ai-rtl-vectors`) · DynamoDB Claim DB(`bos-ai-claim-db-dev`) · Neptune

---

## 2. SoC RAG의 핵심 차이: Ground Truth 부재 문제

| 구분 | NPU RAG | SoC RAG |
|------|---------|---------|
| Ground Truth | CLAUDE_DBS (51개 memory + N1B0 10개, 엔지니어 수동 검증) | **없음** |
| 품질 측정 | L1~L6 프레임워크 vs 검증된 Claim | RTL ↔ Spec RAG 교차 검증 |
| 타겟 파이프라인 | tt_20260221, tt_20260516 (Trinity/NPU) | SoC 전체 (다수 블록) |
| topic taxonomy | EDC/FPU/NIU 등 NPU-specific | SoC 블록별 재정의 필요 |

Ground Truth 없이 품질을 검증하려면 **Spec RAG와의 교차 검증**이 핵심이다.

---

## 3. 전체 구조: NPU RAG 포크 + Spec RAG 결합

```
SoC RTL 소스 (S3)                    SoC Spec/Databook (S3)
    ↓ rtl-parser-soc Lambda               ↓ document-processor (Bedrock KB)
Qdrant [soc-rtl 컬렉션]             Bedrock KB [soc-spec 네임스페이스]
Neptune [soc pipeline_id 격리]
    ↓                                     ↓
           SoC Claim DB (DynamoDB)
                   ↓
        Cross-Validation Engine  ← 핵심 신규 컴포넌트
                   ↓
             MCP Bridge (도구 추가)
```

---

## 4. 인프라 확장 계획

### Qdrant
- NPU: 기존 `bos-ai-rtl-vectors` 컬렉션 유지
- SoC: **신규 컬렉션 `soc-rtl-vectors`**
- 권고: 신규 컬렉션 분리 — NPU/SoC 간 인덱스 격리 명확, 재인덱싱 시 상호 영향 없음

### DynamoDB (Claim DB)
- 기존 테이블 공유 + `corpus` 필드 추가 (backward compatible)
- `corpus=npu` / `corpus=soc` 로 논리 격리
- pipeline_id 격리는 기존 v9.5 설계 그대로 활용

### Neptune
- 기존 Neptune 인스턴스 공유
- `pipeline_id` 기반 격리는 이미 v9.5에 설계됨
- SoC pipeline_id 컨벤션 확정 필요 (예: `soc_20260601`)

### Lambda
- `rtl-parser-soc`: 기존 rtl-parser 포크 — SoC-specific 파싱 로직 분리
- `document-processor`: 공유 가능 (corpus 라우팅 파라미터 추가)

---

## 5. Ground Truth 없는 품질 검증 전략

### 5-1. Spec RAG를 약한 Ground Truth로 활용

```
SoC Spec PDF/문서 → Bedrock KB (rag_query)
        ↓
    spec_claim 추출 (confidence: 0.7~0.8)
        ↓
RTL-extracted claim과 교차 비교
        ↓
    일치 → confidence 상승 / 불일치 → draft 마킹
```

- Spec에 명시된 포트 폭·파라미터·인터페이스가 RTL 파싱 결과와 일치하는지 자동 비교
- `generate_hdd_section` 결과를 spec 내용으로 `rag_validate_answer`로 검증

### 5-2. RTL 자기일관성 검증 (Neptune 활용)

```
Neptune graph에서:
  - 포트 연결 방향이 상위/하위 모듈에서 일치하는지
  - 신호 폭이 연결 경로 전체에서 동일한지
  - CDC 신호가 올바른 synchronizer를 거치는지
```

NPU RAG의 `find_clock_crossings`, `trace_signal_path`가 이미 이 기반이다.

### 5-3. 점진적 Ground Truth 축적

```
엔지니어 사용 → 답변에 피드백 → Claim DB에 confirmed 마킹
                                        ↓
                          hardware-tdd-pipeline의 Feedback_Store 패턴 적용
```

NPU CLAUDE_DBS와 동등한 **"SoC Engineer Verified Corpus"**를 점진적으로 구축한다.

---

## 6. 구현 로드맵

### Phase 1: 인프라 포크 (2주)
- Qdrant `soc-rtl-vectors` 컬렉션 생성 + Terraform
- DynamoDB `corpus` 필드 추가 (기존 테이블 backward compatible)
- Neptune pipeline_id 네이밍 컨벤션 확정
- `rtl-parser-soc` Lambda 포크

### Phase 2: SoC RTL 인제스트 (2주)
- SoC RTL 소스 S3 업로드 및 파이프라인 설정
- SoC topic taxonomy 정의 (NPU의 EDC/FPU/NIU → SoC 블록별 재정의)
- Qdrant + Neptune 초기 인덱싱
- `search_rtl`로 기본 검색 동작 확인

### Phase 3: Spec RAG 통합 (2주)
- SoC 스펙 문서(PDF/MD) Bedrock KB 업로드
- Spec claim 추출 파이프라인 (document-processor 활용)
- Spec claim → Claim DB 적재 (`source: spec_document`, `confidence: 0.7`)
- MCP `rag_query` + `search_rtl` 병행 활용 패턴 확립

### Phase 4: 교차 검증 프레임워크 (3주)
- RTL claim ↔ Spec claim 자동 매핑 (fact_key 기반)
- 불일치 탐지 → `draft` 마킹 + 알림
- Neptune 자기일관성 검사 쿼리 (포트 폭·방향 일치)
- 평가 데이터셋 자동 생성 (Spec Q&A 쌍)

### Phase 5: HDD 생성 품질 루프 (지속)
- hardware-tdd-pipeline 연동: RTL → as-built HDD → Spec HDD diff 분석
- 엔지니어 피드백 Feedback_Store 적재
- 점진적 SoC Verified Corpus 구축

---

## 7. MCP 도구 확장 (신규 필요)

| 도구 | 용도 |
|------|------|
| `search_rtl`의 `corpus=soc` 파라미터 | SoC/NPU corpus 분리 검색 |
| `validate_rtl_spec_consistency` | RTL claim vs Spec claim 교차 검증 |
| `list_soc_blocks` | SoC 블록 목록 및 커버리지 현황 |

> mcp-corpus-routing-acl spec에서 corpus 분리를 이미 설계 중이므로 해당 방향과 정합을 맞춘다.

---

## 8. 주요 결정 사항 요약

| 항목 | 결정 | 이유 |
|------|------|------|
| Qdrant | 신규 컬렉션 분리 | 재인덱싱/스키마 변경 시 NPU 영향 없음 |
| DynamoDB | 기존 테이블 공유 + corpus 필드 | 테이블 수 최소화, pipeline_id 격리는 기존 설계 활용 |
| Neptune | 공유 + pipeline_id 격리 | 기존 설계 그대로 활용 |
| Lambda | rtl-parser 포크 | SoC-specific 파싱 로직 분리 필요 |
| Ground Truth | Spec RAG 교차 검증 → 점진적 축적 | CLAUDE_DBS 없이 품질 측정 가능한 유일한 경로 |

---

## 9. 다음 단계

1. **SoC RTL 소스 공유** — 파일 수·모듈 수·블록 구성을 파악해야 인제스트 전략(Lambda timeout, 배치 크기) 구체화 가능
2. **SoC topic taxonomy 초안 작성** — 블록별 키워드 매핑 (Phase 1 시작 전 확정 필요)
3. **Spec 문서 목록 확인** — 어떤 데이터북/스펙 문서가 있는지 목록화
4. **`.kiro/specs/11_soc-rtl-rag/`** 스펙 작성 — 본 계획 기반으로 requirements.md / design.md 작성
