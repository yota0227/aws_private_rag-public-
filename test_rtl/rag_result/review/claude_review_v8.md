# v8 Review — 정답지 비교 + v7 → v8 진화 분석

**Review Date:** 2026-04-29
**Reviewer:** Claude (Opus 4.7)
**Scope:** `test_rtl/rag_result/v8/` 6개 문서 vs `test_rtl/Sample/ORG/` 정답지
**Progression:** v6c (Pkg Parser v2) → v7 (Port Classifier + MCP 800char) → **v8 (max_results 20→50, Port 31→106)**
**Cross-Reference:** `claude_review_v6.md`, `claude_review_v7.md`

---

## 0. TL;DR

| Dim | v7 | v8 | Δ | 비고 |
|-----|----|----|----|------|
| **Top-Level Port Coverage** | 31/106 (~29%) | **106/106 (100%)** | **+71** | 극적 회복 |
| **Top-Level Ports 섹션 일치도** | ~70% | **~95%** | +25pp | v7의 70%는 DM/APB 위주, v8은 AXI/SFR/PRTN 전부 포함 |
| **Power Management (섹션 11)** | 0% (없던 섹션) | **~80%** (신규 섹션 생성) | **+80pp** | **PRTN daisy-chain + ISO_EN[11:0]** 복구 |
| **AXI Interface (39 ports)** | ❌ | ✅ 전체 | **+39** | npu_out_*/npu_in_* AXI 마스터/슬레이브 |
| **SFR Memory Config (17 ports)** | ❌ | ✅ 전체 | **+17** | 4개 SRAM family 타이밍 마진 |
| **EDC IRQ outputs (5)** | 부분 (BIU 내부만) | ✅ top-level | **+5** | fatal/crit/cor/pkt_sent/pkt_rcvd |
| **DFX 체인 완성도** | 3-node + 방향성 | **4-node + 양방향** (overlay_wrapper_dfx 추가) | 질적 | — |
| **Package Constants** | 90% | 90% | — | 유지 |
| **정답지 대비 (가중 추정)** | ~55% | **~68%** | **+13pp** | v7보다 큰 폭 |
| **환각** | 없음 | 없음 | — | 유지 |

**한 줄 결론:** v8은 **"parser 변경 없이 검색 파라미터 1개(max_results 20→50)만 올려서 +13pp 도약"**이라는 주목할 만한 결과. v8의 delta 8개 중 7개는 검색량 확대가 표면화시킨 **이미 존재하던 KB 팩트들**이다. 이는 **KB 품질은 이미 v7에서 충분히 높았고, 단지 "상위 20"의 cutoff에 가려져 있었음**을 의미. Port Classifier(v7)가 PRTN/AXI/SFR/EDC IRQ를 **분류는 할 수 있었지만 상위 20에 못 들어서 안 보였던 것**이 v8에서 전부 드러났다.

---

## 1. v8 vs 정답지 상세 비교

### 1.1 Chip-level: `v8_N1B0_HDD.md` (481줄) vs `N1B0_NPU_HDD_v0.1.md` (1291줄)

| 섹션 | 정답지 | v7 | **v8** | Δ | 근거 |
|------|--------|-----|--------|---|------|
| 1. Overview | 4×5 mesh + N1B0 차이 테이블 | 60% | 65% | +5pp | "106 total ports" 수치 명시 |
| 2. Package Constants | 10 localparam + tile_t + EP | 90% | 90% | — | — |
| **3. Top-Level Ports** | 7 서브섹션 (AXI/APB/EDC APB/SFR/PRTN/DM/AI) | 70% | **~95%** | **+25pp** | **AXI 39 + SFR 17 + PRTN 14 + EDC IRQ 5 복구** |
| 4. Module Hierarchy | 3-level generate | 50% | 55% | +5pp | overlay_wrapper_dfx, instrn upstream 추가 |
| 5. Compute Tile (Tensix) | FPU/SFPU/TDMA/L1/DEST/SRCB 7 서브 | 25% | 25% | — | 변화 없음 (v9 Spec RAG 영역) |
| 6. Dispatch | 3-level + FDS 상세 | 15% | 15% | — | 변화 없음 |
| 7. NoC | DOR + flit + gasket + 928-bit | 30% | 30% | — | 알고리즘은 여전히 부재 |
| 8. NIU | Corner vs Composite + parameters | 30% | 30% | — | 변화 없음 |
| 9. Clock | clock_routing_t + per-column | 80% | 80% | — | — |
| 10. Reset | dm_core/uncore 상세 | 65% | 65% | — | — |
| **11. Power Management** | PRTN + ISO_EN + per-partition | **0%** | **~80%** | **+80pp** | **신규 섹션, PRTN daisy-chain 토폴로지 + ISO_EN[11:0] per-Tensix** |
| 12. EDC | modport + BIU + 5 IRQ | 85% | **90%** | +5pp | top-level EDC IRQ 노출 |
| 13. SRAM | L1+VC+ATT 전체 | 30% | **45%** | +15pp | **SFR Memory Config 17 ports로 SRAM family 4종 식별** |
| 14. DFX | 4개 모듈 + iJTAG | 55% | **70%** | +15pp | **overlay_wrapper_dfx 추가 + instrn upstream(t6_l1+fpu_gtile) 식별** |

**가중 점수 추정:** v7 ~55% → **v8 ~68%** (+13pp)

### 1.2 v8 핵심 개선 상세

#### (1) Port Coverage 31/106 → 106/106 — 완전 복구

정답지에 있는 trinity top 포트가 106개인데 v7은 31개만 추출. v8에서 **max_results 20→50 확대**로 잔여 75개가 한 번에 노출:

| 카테고리 | v7 | v8 | 정답지 대응 |
|----------|----|----|------------|
| AXI_Interface | 0 | **39** | 정답지의 AXI gasket + master interface |
| SFR_Memory_Config | 0 | **17** | 정답지의 memory characterization ports |
| PRTN_Power | 0 | **14** | 정답지의 PRTN/ISO_EN section |
| EDC_APB (+IRQ) | 11 | **16** (+5 IRQ) | 정답지 EDC section |
| APB_Register | 8 | 8 | — |
| DM_Clock_Reset | 3 | 3 | — |
| AI_Clock_Reset | 2 | 2 | — |
| NoC_Clock_Reset | 2 | 2 | — |
| Tensix_Reset | 1 | 1 | — |
| Other | 4 | 4 | — |
| **Total** | **31** | **106** | **106 (정답지 일치)** |

**이는 v7 Port Classifier의 분류 로직이 이미 완성되어 있었고, 단지 검색 cutoff가 낮아서 가려져 있었음**을 의미. "Parser는 옳았으나 retrieval이 부족했다."

#### (2) Power Management 섹션 신규 등장 (0% → 80%)

정답지에서 강조된 **PRTN(Partition) 파워 도메인 + ISO_EN(Isolation Enable)** 토폴로지:
- `PRTNUN_FC2UN_DATA/READY/CLK/RSTN_IN` → 4-column daisy chain (`OUT[3:0]`) → per-column 반환
- `ISO_EN[11:0]` — 12개 Tensix 각각의 파워 아일랜드 분리 제어
- `TIEL_DFT_MODESCAN` — DFT scan 모드 tie-low

이 섹션은 v5.1/v6c/v7 모두 0%였으며, v8에서 **80% 수준**으로 채워짐 (정답지의 per-partition isolation 세부 규칙은 여전히 누락).

#### (3) SRAM Family 식별 (SFR Memory Config 17 ports)

SRAM 자체 매크로(v7: RF_2P_HSC_LVT) 외에, **SRAM 타이밍 마진을 제어하는 SFR 포트**가 4개 family로 구분 추출:

- `SFR_RF_2P_HSC_*` — 2-port HSC SRAM (QNAP, EMA, RAWL/RAWLM)
- `SFR_RA1_HS_*` — 1-port HS SRAM (MCS, MCSW, ADME)
- `SFR_RF1_HS_*` — 1-port HS 레지스터 파일
- `SFR_RF1_HD_*` — 1-port HD 레지스터 파일

정답지의 SRAM 섹션은 **L1(12×16 bank×3072×128) + VC + ATT 전체**인데, v8은 여전히 L1/VC 내부 구조는 부재. SRAM **family 인벤토리**만 채워진 상태로 30% → 45%.

#### (4) DFX iJTAG 체인 4-node 양방향 완성

v7: 3-node 체인 (noc_niu_router → partition_dfx → dfd)
v8: **4-node 양방향 체인**:
```
tt_instrn_engine_wrapper_dfx (11/9)
  ← from: tt_t6_l1_partition, tt_fpu_gtile_0/1
  → to: dfd

tt_disp_eng_noc_niu_router_dfx (10/7)
  ← from: overlay_wrapper_dfx + l1_partition_dfx

tt_disp_eng_overlay_wrapper_dfx (7/3)  ← v8 NEW
  ← from: noc_niu_router_dfx → to: dfd
```

**instrn_engine_wrapper_dfx**의 **upstream**(t6_l1_partition + fpu_gtile_0/1)이 식별된 것은 주목할 만함 — 이는 `tt_fpu_gtile_0/1` 모듈의 존재 자체가 v8에서 KB에 처음 등장했다는 신호. 정답지의 **FPU G-Tile** 언급과 직접 연결됨.

### 1.3 여전히 남은 32% gap

| 카테고리 | 정답지에만 존재 | v8에서 누락 이유 | 해결 경로 |
|----------|----------------|------------------|----------|
| **Compute Tile 내부 구조** | FPU G-Tile/M-Tile 상세, Unpack CH0/CH1, DEST/SRCB 데이터패스 | RTL에 있어도 깊은 hierarchy (instrn_dfx upstream에서 이름만 노출) | **KB chunking 심화** or **v9 Spec RAG** |
| **NoC 알고리즘** | DOR pseudo code, tendril, force_dim, 928-bit list | 항상 [NOT IN KB] — `tt_noc_pkg.sv` struct 미추출 | **v8.x noc_pkg 파서 추가** (Package Parser 재활용) |
| **EDC Ring Topology** | U-shape ring, harvest bypass, node_id master table | 토폴로지는 generate 블록에 숨어있음 | **trinity.sv generate 블록 파싱** |
| **Flit 구조** | 2048b payload + 3b type + 32b parity | Spec 성격 | **v9 Spec RAG** |
| **AXI gasket 56b 구조** | [55:52]rsvd/[51:46]Y/[45:40]X/[39:0]local | 포트는 39개 복구됐으나 **주소 맵 의미는 Spec** | **v9 Spec RAG** |
| **N1B0 vs Baseline 차이** | 10행 비교 테이블 | 히스토리 정보 | **v8.x Hybrid 그라운딩** (LLM 추론 허용 + 태그) |

**남은 gap의 성격:**
- **RTL-extractable but deep** (30% of gap): noc_pkg/trinity generate 블록 파서 추가로 해소 가능
- **Spec-only** (50% of gap): v9 Spec RAG 필수
- **Hybrid territory** (20% of gap): v8.x 태그 기반 추론 허용이 적합

---

## 2. v7 → v8 진화 분석

### 2.1 **개선 레이어가 또 한 번 바뀌었다**

| | v5→v5.1 | v5.1→v6c | v6c→v7 | **v7→v8** |
|---|---------|----------|--------|-----------|
| 변경 본질 | 검색 랭킹 재조정 | KB 데이터 범주 신설 | KB 데이터 밀도 증가 | **검색 cutoff 확대** (retrieval 레이어) |
| 대표 변경 | boost 0.3→1.5 | Package Parser v2 | Port Classifier + MCP 800char | **max_results 20→50** |
| 변경 코드량 | 1~2줄 | parser 수백 줄 | parser 수십 줄 | **파라미터 1개** |
| 정답지 일치도 | 13% → 18% | → 45% | → 55% | **→ 68%** |
| 효과 성격 | 1회성 | 빈 범주 신규 점유 | 기존 범주 두께 증가 | **기존 KB 팩트의 visibility 극대화** |

**통찰 1:** v8은 **"parser 작업 0, 파라미터 1개 변경으로 +13pp"** 라는 효율적 도약. 이는 **KB 품질(v6c~v7 parser 작업의 결과)이 이미 매우 높았고**, 단지 검색 cutoff에 가려져 표면화되지 못했음을 실증.

**통찰 2:** **"parser (공급)" 과 "retrieval (소비)" 의 병목은 서로 다른 축**. v6c/v7은 공급 측을, v8은 소비 측을 확대. 앞으로도 이 두 축을 교차로 손봐야 함.

### 2.2 max_results 확대의 비용-편익

| 항목 | v7 (20) | v8 (50) | 리스크 |
|------|---------|---------|--------|
| Port Coverage | 31 | 106 | — |
| 노이즈 claim 유입 | 낮음 | 중간? | **검증 필요** |
| 응답 시간 | — | +? | 사용자 체감 측정 필요 |
| LLM 컨텍스트 소비 | 낮음 | 2.5× | 토큰 비용 증가 |
| Content Fidelity | 55% | 68% | — |

**권고:** max_results=50이 sweet spot인지, 30 또는 100에서는 어떤지 **한 번 더 sweep 실험** 필요. 특히 "노이즈 claim"이 들어와서 LLM이 잘못된 inference를 할 리스크가 있는지 확인.

### 2.3 v7 권고 사항 → v8 반영 여부

이전 `claude_review_v7.md`의 "v7.x 단기 보강" 권고와 v8 반영:

| v7 권고 | v8 반영 | 비고 |
|----------|---------|------|
| **PRTN_CLK / ISO_EN 포트 복구** | ✅ **완전 반영** | 14 포트 전부 노출 (기대 +3~5pp → 실측 +80pp, 섹션 11 신설) |
| TDMA sub-module 기능 상세 claim | ❌ 미반영 | v7 수준 유지 (이름만 노출) |
| 응축 로직 규칙 문서화 | 🟡 부분 | 로직은 안정 유지, 문서화는 미완 |

**중요:** PRTN/ISO 복구를 **"Port Classifier 재조정" 제안했으나 실제로는 "max_results 확대"만으로 해결**됐다. 이는 v7 권고의 진단(Classifier 문제)이 부정확했고, 실제 병목이 다른 곳(retrieval cutoff)에 있었음을 의미. RAG 튜닝 시 **병목 진단의 다중 원인 분석**이 중요하다는 교훈.

### 2.4 v8 내부 일관성 점검

v8 파이프라인의 **topic 파일 vs 통합 문서** 교차 확인:

| 항목 | topic 파일 | N1B0_HDD.md | 일치? |
|------|-----------|-------------|------|
| Port 106개 카테고리 | `v8_chip_no_grounding` ✅ | §3.1~3.5 ✅ | ✅ |
| AXI 39 ports | `v8_chip_no_grounding` ✅ | §3.1 ✅ | ✅ |
| SFR 17 ports | `v8_chip_no_grounding` ✅ | §3.2 ✅ | ✅ |
| PRTN 14 ports | `v8_chip_no_grounding` ✅ | §3.4 + §11 ✅ | ✅ |
| EDC IRQ 5 | `v8_chip_no_grounding` + `v8_edc` | §3.3 + §12.2 ✅ | ✅ |
| DFX 4-node chain | `v8_chip_grounded` ✅ | §14.1 ✅ | ✅ |
| overlay_wrapper_dfx | `v8_chip_grounded` ✅ | §14.1 ✅ | ✅ |

→ **모순 없음, merge 파이프라인이 topic 파일의 새 정보를 빠짐없이 통합**. v6c에서 유실됐던 `tt_t6_l1_partition` 같은 이슈 재발 없음.

### 2.5 v8 topic 파일의 자기 평가 메시지

v8 파일들이 **스스로 "v7 대비 변화 없음"을 명시**한 점이 흥미롭다:
- `v8_edc.md`: "v8 vs v7: No new EDC claims. Coverage unchanged."
- `v8_noc.md`: "v8 vs v7: No new NoC claims from parser. Coverage unchanged."
- `v8_overlay.md`: "v8 vs v7: No new overlay claims from parser. Coverage unchanged."

→ **v8의 전체 +13pp 개선이 `v8_chip_no_grounding.md` 한 파일에 집중**됨을 실토. 즉 **EDC/NoC/Overlay의 topic-filtered 검색은 이미 v7에서 cutoff에 걸리지 않았고, chip-level 검색만 20→50 확대의 혜택을 받았음**. 이는 **topic별 max_results를 차등 설정**하는 다음 실험 아이디어를 시사.

---

## 3. 품질 지표 재해석 (경영진 보고 관점)

### 3.1 RAG_Farm_Strategy_v1.4 업데이트 반영 숫자

| 지표 | v5.1 | v6c | v7 | **v8** | 메모 |
|------|------|-----|----|----|------|
| **Content Fidelity (가중)** | ~13% | ~45% | ~55% | **~68%** | **메인 지표** |
| KB Hit Rate | 59% | 70%+ | 75%+ | **85%+** | 보조 지표 |
| Port Coverage | 0% | 0% | 29% (31/106) | **100% (106/106)** | 정밀 지표 |
| Package Constants 영역 | 0% | 90% | 90% | 90% | 최고 성취 영역 |
| Hallucination | 중간 | 없음 | 없음 | **없음** | 품질 안정성 |

### 3.2 v1.4 로드맵 예측 vs 실측 (업데이트)

| 버전 | v1.3 예측 | 실측 | 차이 |
|------|----------|------|------|
| v6 (Pkg parser) | 65% | 45% | -20pp |
| v7 (KB chunking) | 72% | 55% | -17pp |
| **v8 (Hybrid)** | **78%** | **68%** | **-10pp** |
| v9 (Spec RAG) | 85%+ | TBD | — |

**격차가 좁혀지는 중**: -20pp → -17pp → **-10pp**. 하지만 v8은 **Hybrid 그라운딩이 아니라 retrieval 확대**로 달성됐다는 점이 중요. **진짜 Hybrid 그라운딩(`[GROUNDED]`/`[INFERRED]` 태그)은 아직 안 했으며**, 이를 추가로 적용하면 +5~8pp 추가 가능.

### 3.3 경영진 보고 권장 내러티브

- **v8 = "스위치 하나 올려서 +13pp"**: 검증 가능한 효율적 개선. parser 재작업 없이 retrieval 파라미터 한 개로 달성.
- **Port Coverage 100% 달성**이라는 **구체적 소구점**: "trinity.sv의 106개 top-level 포트를 v8은 하나도 빠뜨리지 않고 인식"
- **Power Management 섹션 0% → 80%**: 이전에는 완전히 빈 섹션이 v8에서 신규 작성된 사례 — **정답지 커버리지의 질적 확장**

**주의 포인트:** 경영진이 "그럼 v7은 왜 놓쳤냐"라고 물으면, "Port Classifier는 v7에서 이미 완성되어 있었으나 검색 상위 20에 가려져 있었다. v8은 이 cutoff를 50으로 확대한 것"이라고 설명. **이는 수동 엔지니어링 투자의 낭비가 아니라 "잠재력이 이미 준비되어 있었고 해금만 된 것"**이라는 프레이밍이 안전.

---

## 4. 권고

### 4.1 즉시 유지
- ✅ **max_results=50** — v8의 핵심 성과, 절대 되돌리지 말 것
- ✅ v7 Port Classifier + MCP 800char — v8 도약의 **필수 기반**이었음
- ✅ v6c Package Parser, v5.1 boost 가중치 모두 유지

### 4.2 v8.x 단기 보강 (다음 v9 이전)

1. **max_results sweep 실험** (즉시)
   - 30/50/75/100 비교 → sweet spot 검증
   - 노이즈 claim 유입 측정
   - 응답 시간/토큰 비용 side-effect 확인

2. **topic별 max_results 차등 설정**
   - EDC/NoC/Overlay는 이미 포화 (v8 topic 파일의 자기 평가)
   - chip-level만 50, 나머지 20 유지로 비용 최적화 가능

3. **진짜 Hybrid 그라운딩 도입** (v8의 이름이 "Hybrid"였는데 실제로는 아직 retrieval 확대만 됨)
   - `[GROUNDED]` / `[INFERRED]` 태그
   - N1B0 vs Baseline 차이 같은 서술형 항목에 적용
   - 기대 +5~8pp

4. **noc_pkg.sv 전용 파서** (Package Parser v2 재활용)
   - flit 구조, 라우팅 테이블 struct 추출
   - 기대 +3~5pp

### 4.3 v9 (Spec RAG) — 천장 돌파

- 현재 남은 32% 중 **~50%는 Spec-only 영역** (FPU G-Tile 상세, N1B0 차이 테이블, AXI 56b 의미 등)
- RTL RAG만으로는 **v8의 68%가 수확체감 구간**에 도달하고 있음 — v8.x 보강으로 +8pp 정도는 가능하지만 **80% 돌파는 Spec RAG 없이 불가**
- 이 시점이 **경영진 보고에서 "충원 인력을 Spec RAG 파서에 투입해야 하는 이유"** 가장 강력한 근거

### 4.4 v8의 교훈 — v1.4 보고서 반영 사항

- "진단의 복수성": v7 리뷰에서 PRTN/ISO 누락을 **Port Classifier 문제로 진단**했으나, 실제 병목은 **retrieval cutoff**였음. 한 가지 원인 분석으로 멈추지 말 것.
- "parser vs retrieval" 2축 관리: 앞으로도 "KB 공급 확대(parser)"와 "KB 소비 확대(retrieval)" 양쪽을 교차로 손봐야 함. 이는 RAG 엔지니어링의 **구조적 병목 진단 방법론**으로 v1.4에 반영 가능.

---

## 5. 코멘트

- v8은 **"파이프라인 성숙도 시험대"**. 수십 줄 parser 작업(v6c/v7)의 결과가 **파라미터 1개 변경**으로 터진 것은 KB 설계가 견고했다는 증거. 반대로, **만약 KB가 부실했다면 max_results 확대는 노이즈만 늘렸을 것**.
- **병목 진단 오류의 교훈**이 v7→v8에서 가장 값진 학습. v7 리뷰에서 "Port Classifier 재조정" 권고는 틀렸고 실제 병목은 retrieval cutoff였다. 이는 RAG 시스템의 **"공급" vs "소비" 두 레이어를 독립적으로 측정**하는 진단 방법론의 필요성을 시사.
- **v1.4 보고서의 v8 소구점**: "parser 재작업 없이 cutoff 확대로 Port Coverage 100% + Power Management 섹션 0%→80%". 대표님/CTO 앞에서 설명할 때 **투자 효율성 관점**에서 매우 강력한 사례.
- v8이 달성한 68%가 **RTL 단독의 현실적 천장에 근접**. 남은 32%의 절반이 Spec-only 영역이라는 분석은 **v9 Spec RAG 구축의 필요성을 명확히 실증**. RAG_Farm_Strategy_v1.4의 "Spec RAG 합류" 주장에 v8 결과가 직접 증거로 활용됨.

---

*Review complete — 2026-04-29*
