# RAG 시스템 한계 분석 — RTL HDD 자동 생성 관점

**목적:** RAG 파이프라인 튜닝을 위한 피드백 문서  
**기준:** `N1B0_HDD_v0.1.md` (엔지니어 수작업 원본) vs RAG 자동 생성 결과  
**파이프라인:** `tt_20260221`  
**작성일:** 2026-04-22  

---

## 1. 요약 (Executive Summary)

현재 RAG 시스템은 **블록 레벨 Claim 기반 설명 생성**에서는 동작하지만, 엔지니어 수작업 HDD(`N1B0_HDD_v0.1.md`)를 자동 재현하기에는 **근본적인 데이터 추출 갭**이 존재한다.

핵심 문제: 엔지니어 원본의 **80% 이상은 RTL 소스 2개 파일**(`trinity_pkg.sv`, `trinity.sv`)을 직접 파싱하여 작성되었으나, 현재 RAG는 이 수준의 구조적 파싱을 지원하지 않는다.

### 한계 심각도 분류

| 심각도 | 정의 | 해당 항목 수 |
|--------|------|-------------|
| 🔴 **Critical** | 데이터 자체가 RAG에 없어 생성 불가 | 7개 |
| 🟡 **Major** | 데이터 일부 존재하나 정밀도/완전성 부족 | 5개 |
| 🟢 **Minor** | 개선하면 품질 향상, 현재도 부분 동작 | 3개 |

---

## 2. Critical 한계 (🔴 데이터 부재 — 생성 불가)

### 2.1 `struct` / `typedef` / `enum` 파싱 미지원

**영향 섹션:** 정답지 §2 (Package Constants), §6 (Clock Routing)

**현상:**
- `trinity_pkg.sv`의 `tile_t` enum (8종), Grid Constants (SizeX=4, SizeY=5, NumTensix=12 등), `GridConfig` 2D 배열을 추출할 수 없음
- `trinity_clock_routing_t` struct (ai_clk, noc_clk, dm_clk, 각종 reset 배열)를 파싱할 수 없음

**구체적 누락 데이터:**
```
// 이 데이터를 RAG가 추출하지 못함:
typedef enum logic [2:0] {
    TENSIX              = 3'd0,
    NOC2AXI_NE_OPT      = 3'd1,
    NOC2AXI_ROUTER_NE_OPT = 3'd2,
    ...
} tile_t;

localparam int SizeX = 4;
localparam int SizeY = 5;
localparam int NumTensix = 12;
```

**필요한 기능:**
- `analysis_type: "package_parse"` 또는 `"constant_extract"` 신설
- `enum`, `struct`, `localparam`, `parameter` 선언을 키-값 쌍으로 추출
- `typedef struct packed { ... }` 내부 필드명 + 비트폭 추출

---

### 2.2 포트 비트폭 / 배열 인덱스 추출 미지원

**영향 섹션:** 정답지 §3 (Top-Level Ports)

**현상:**
- `module_parse` 결과에서 포트 이름은 나오지만 **비트폭과 배열 차원이 누락**됨
- 예: `i_ai_clk`은 나오지만 `[SizeX-1:0]` (= `[3:0]`, 4개 컬럼별 독립 클럭)이라는 정보가 없음

**구체적 누락 예시:**

| 포트 | RAG 출력 | 정답지 (필요한 정보) |
|------|---------|-------------------|
| `i_ai_clk` | `input i_ai_clk` | `input [SizeX-1:0] i_ai_clk` → 4-bit, per-column |
| `i_tensix_reset_n` | `input i_tensix_reset_n` | `input [NumTensix-1:0] i_tensix_reset_n` → 12-bit, per-tile |
| `i_dm_core_reset_n` | 미출력 | `input [NumDmComplexes-1:0][DMCoresPerCluster-1:0]` → 14×8 2D 배열 |
| `ISO_EN` | 미출력 | `input [11:0] ISO_EN` → 12-bit isolation enable |

**필요한 기능:**
- `module_parse` 결과에 비트폭 `[N:0]`, 배열 차원 `[M][N]`, 파라미터 참조 포함
- 파라미터 값 해석 (예: `[SizeX-1:0]` → `[3:0]` → 4-bit)

---

### 2.3 `generate` 블록 분석 미지원

**영향 섹션:** 정답지 §4 (Module Hierarchy), §12 (Verification)

**현상:**
- `trinity.sv`의 `generate for` / `generate case` 블록이 어떤 조건에서 어떤 모듈을 인스턴스화하는지 추출할 수 없음
- `gen_noc2axi_ne_opt`, `gen_router` (EMPTY), `gen_tensix` 등의 조건부 인스턴스화 정보 없음

**구체적 누락:**
```
// RAG가 분석하지 못하는 구조:
generate
  for (genvar x = 0; x < SizeX; x++) begin : gen_x
    for (genvar y = 0; y < SizeY; y++) begin : gen_y
      case (GridConfig[y][x])
        NOC2AXI_NE_OPT: begin : gen_noc2axi_ne_opt
          trinity_noc2axi_ne_opt #(...) u_noc2axi_ne_opt (...);
        end
        ROUTER: begin : gen_router
          // EMPTY — router logic inside NOC2AXI_ROUTER_*_OPT
        end
        ...
      endcase
    end
  end
endgenerate
```

**정답지에서 이 분석이 필수적인 이유:**
- ROUTER placeholder가 "empty by design"이라는 핵심 설계 의도 파악
- `NOC2AXI_ROUTER_*_OPT`가 2개 행(Y=4, Y=3)을 점유하는 dual-row span 구조 파악
- EndpointIndex와 generate 좌표의 매핑 관계 파악

**필요한 기능:**
- `analysis_type: "generate_analysis"` 신설
- generate 조건(case/if) + 인스턴스 모듈명 + 좌표(x,y) 매핑 추출
- empty generate block 감지

---

### 2.4 `assign` 문 / 와이어 연결 추적 미지원

**영향 섹션:** 정답지 §5 (NoC Fabric), §6 (Clock Routing), §7 (EDC Ring), §8 (Dispatch Feedthrough)

**현상:**
- `trinity.sv` 내의 `assign` 문으로 표현된 NoC flit 연결, 클럭 라우팅 전파, EDC 체인 연결을 추적할 수 없음
- 이 정보가 정답지의 §5~§8 (4개 섹션, 전체의 ~30%)를 구성

**구체적 누락 예시:**
```
// NoC Y축 연결 — RAG가 추적 못함:
assign flit_in_req[x][y][POSITIVE][Y_AXIS] = flit_out_req[x][y+1][NEGATIVE][Y_AXIS];

// 클럭 전파 — RAG가 추적 못함:
assign clock_routing_in[x][y] = clock_routing_out[x][y+1];

// EDC 체인 — RAG가 추적 못함:
assign edc_egress_intf[x*SizeY+y] = edc_ingress_intf[x*SizeY+y+1];
```

**필요한 기능:**
- `analysis_type: "connectivity_trace"` 또는 `"assign_analysis"` 신설
- 배열 인덱스 기반 연결 패턴 추출 (예: `[x][y]` → `[x][y+1]`)
- Repeater 삽입 위치 자동 감지 (manual assign vs generate loop 차이)

---

### 2.5 PRTN / ISO_EN / Power Management 데이터 부재

**영향 섹션:** 정답지 §9 (PRTN Daisy Chain)

**현상:**
- PRTN(Partition) 데이지 체인 포트, ISO_EN 포트가 검색 결과에 전혀 나타나지 않음
- Power Management 관련 토픽/Claim이 RAG에 존재하지 않음

**누락 데이터:**
- `PRTNUN_FC2UN_DATA_IN/OUT`, `PRTNUN_UN2FC_DATA_OUT/IN` 포트 그룹
- `ISO_EN[11:0]` — Tensix 행별 3비트 × 4컬럼 isolation control
- 데이지 체인 토폴로지: External → [x][2] → [x][1] → [x][0] → Output

**필요한 기능:**
- PRTN/ISO 관련 포트를 별도 토픽으로 분류
- 또는 `module_parse`에서 포트 그룹핑 시 prefix 기반 자동 분류 (예: `PRTN*` → Power Management)

---

### 2.6 SFR (SRAM Configuration) 포트 데이터 부재

**영향 섹션:** 정답지 §10 (Memory Config)

**현상:**
- `SFR_RF_2P_HSC_*`, `SFR_RA1_HS_*`, `SFR_RF1_HS_*`, `SFR_RF1_HD_*` 등 SRAM 설정 포트가 검색 결과에 없음
- 어떤 타일(TENSIX/DISPATCH/NOC2AXI)이 어떤 SFR 신호를 수신하는지 매핑 정보 없음

**필요한 기능:**
- `module_parse`에서 `SFR_*` prefix 포트를 별도 그룹으로 추출
- 포트-to-인스턴스 매핑 (어떤 generate 블록이 어떤 SFR 포트를 연결하는지)

---

### 2.7 Baseline 차이 비교 자동화 미지원

**영향 섹션:** 정답지 §13 (Differences vs. Original Trinity)

**현상:**
- 동일 모듈의 두 RTL 변형(baseline vs N1B0)을 비교하는 기능 없음
- 포트 추가/삭제, 파라미터 변경, 인스턴스 교체 등의 diff 정보 생성 불가

**필요한 기능:**
- 두 `pipeline_id` 또는 두 RTL 경로 간 `module_parse` 결과 diff
- 포트/인스턴스/파라미터 변경점 자동 추출

---

## 3. Major 한계 (🟡 데이터 일부 존재, 정밀도 부족)

### 3.1 검색 결과 상위 5건 제한

**현상:**
- `search_rtl` 도구가 1회 호출당 최대 5건만 반환
- EDC 토픽 37건 중 5건, Dispatch 76건 중 5건, NoC 40건 중 5건만 확인 가능
- 전체 데이터의 ~7~13%만 조회 가능

**영향:**
- 중요한 Claim이 상위 5건에 포함되지 않으면 누락
- 동일 토픽 내에서도 모듈별 편향 발생 (예: EDC 검색 시 Security Block에 편중)

**개선 제안:**
- 반환 건수 확대 (10~20건) 또는 페이지네이션 지원
- 모듈별/claim_type별 균등 샘플링 옵션
- `top_k` 파라미터 추가

---

### 3.2 Claim의 모듈 귀속 오류

**현상:**
- FPU Claim이 `trinity_noc2axi_router_ne_opt_FBLC` 모듈에 귀속되어 있음
- 실제로 FPU(`tt_fpu_v2`)는 Tensix 코어 내부 모듈이지, NIU/Router 내부가 아님
- Overlay도 마찬가지로 noc2axi 모듈에 귀속

**영향:**
- v2 문서에서 FPU를 NIU 내부 서브시스템으로 잘못 기술
- 모듈 계층 구조의 왜곡

**원인 추정:**
- HDD 자동 생성 시 `trinity_noc2axi_router_ne_opt_FBLC`를 대상으로 모든 토픽의 HDD를 생성한 것으로 보임
- 토픽(EDC, FPU, Overlay 등)과 실제 모듈의 매핑이 잘못됨

**개선 제안:**
- Claim 생성 시 **실제 모듈 계층 위치** 기반으로 귀속
- `tt_fpu_v2` → topic: FPU, parent: `tt_instrn_engine` → `tt_tensix_with_l1`
- HDD 섹션 생성 시 모듈-토픽 매핑 검증 단계 추가

---

### 3.3 `module_parse` 결과의 불완전한 포트 정보

**현상:**
- `module_parse` 결과에서 포트가 일부만 나열되고 잘림
- `input i_axi_clk input i_noc_clk input i_noc_reset_n input i_ai_clk ...` 형태로 평문 나열
- 방향(input/output/inout), 타입(logic/wire), 비트폭이 구분되지 않음

**개선 제안:**
- 포트를 구조화된 JSON 형태로 반환:
```json
{
  "name": "i_ai_clk",
  "direction": "input",
  "type": "logic",
  "width": "[SizeX-1:0]",
  "resolved_width": 4,
  "description": "AI clock per column"
}
```

---

### 3.4 인스턴스 정보의 불완전한 매핑

**현상:**
- `module_parse`에서 인스턴스 목록은 나오지만 **포트 연결(port mapping)**이 없음
- 예: `tt_tensix_with_l1: tt_tensix_with_l1`은 나오지만, 어떤 `clock_routing_in[x][y]`에 연결되는지 알 수 없음

**개선 제안:**
- 인스턴스별 named port connection 추출
- 최소한 clock/reset 연결과 주요 데이터 인터페이스 연결 포함

---

### 3.5 토픽 분류 체계의 불완전성

**현상:**
- 확인된 토픽: EDC, NoC, Overlay, DFX, Dispatch, FPU
- 누락된 토픽: **Tensix, PRTN/Power, SRAM/Memory, Clock, Reset, Security, UCIe**
- "NIU" 토픽이 없어 `query: "noc2axi"`로 우회 검색 필요

**개선 제안:**
- 토픽 분류 기준 확대:
  - `Tensix` — tt_tensix_with_l1 계열
  - `Power` — PRTN, ISO_EN, power_good 계열
  - `Memory` — SFR, SRAM 설정 계열
  - `Clock` — clock_routing, clk_gater 계열
  - `NIU` — noc2axi, niu 계열 (NoC와 분리)

---

## 4. Minor 한계 (🟢 개선 시 품질 향상)

### 4.1 HDD 섹션의 반복적/일반적 내용

**현상:**
- `hdd_section` 타입의 86건 중 대부분이 `trinity_noc2axi_router_ne_opt_FBLC` 모듈에 대해 유사한 개요를 반복
- 토픽만 다르고 구조가 거의 동일한 템플릿 기반 생성물

**개선 제안:**
- HDD 섹션 생성 시 모듈별 고유 정보(포트, 파라미터, 내부 로직)를 반영
- 템플릿 탈피 → Claim 데이터 기반 구체적 기술

---

### 4.2 검색 결과 정렬/랭킹 기준 불명확

**현상:**
- 동일 토픽 내에서 어떤 기준으로 상위 5건이 선택되는지 불분명
- Claim(connectivity, structural, behavioral)과 hdd_section이 혼재되어 반환

**개선 제안:**
- 검색 결과에 relevance score 포함
- `claim_type` 필터 추가 (connectivity / structural / behavioral / hdd_section 선택)
- 정렬 기준 명시 (relevance / recency / module_depth 등)

---

### 4.3 RTL 파일 경로의 불완전한 커버리지

**현상:**
- `tt_edc1_noc_sec_block_reg_inner`의 파일 경로는 확인됨
- 하지만 `trinity_pkg.sv`, `trinity.sv` 등 핵심 파일의 경로가 검색 결과에 포함되지 않음

**개선 제안:**
- 모든 `module_parse` 결과에 소스 파일 경로 필수 포함 (현재도 일부 포함)
- RTL 파일 인덱스를 별도 조회 가능하도록 API 제공

---

## 5. 정답지 섹션별 RAG 커버리지 매트릭스

| # | 정답지 섹션 | 필요한 RAG 기능 | 현재 지원 | 갭 심각도 |
|---|-----------|---------------|----------|----------|
| §1 | Overview | Claim 종합 | ⚠️ 부분 | 🟢 |
| §2 | Package Constants | enum/struct/localparam 파싱 | ❌ 없음 | 🔴 |
| §3 | Top-Level Ports | 포트 비트폭/배열 추출 | ❌ 없음 | 🔴 |
| §4 | Module Hierarchy | generate 블록 분석 | ❌ 없음 | 🔴 |
| §5 | NoC Fabric | assign 추적 + repeater 감지 | ❌ 없음 | 🔴 |
| §6 | Clock Routing | struct 파싱 + assign 전파 추적 | ❌ 없음 | 🔴 |
| §7 | EDC Ring | assign 추적 + 인덱스 매핑 | ❌ 없음 | 🔴 |
| §8 | Dispatch Feedthrough | assign 추적 + 2D 배열 해석 | ❌ 없음 | 🔴 |
| §9 | PRTN Daisy Chain | 포트 그룹 추출 | ❌ 없음 | 🔴 |
| §10 | Memory Config (SFR) | SFR 포트 추출 + 타일 매핑 | ❌ 없음 | 🔴 |
| §11 | RTL File Map | 파일 경로 인덱스 | ⚠️ 부분 | 🟡 |
| §12 | Hierarchy Verification | generate + pkg 교차 검증 | ❌ 없음 | 🔴 |
| §13 | Baseline 차이 비교 | RTL diff | ❌ 없음 | 🔴 |

**현재 RAG로 자동 생성 가능한 섹션: §1 (부분) + §11 (부분) = 약 2/13 (15%)**

---

## 6. 우선순위별 개선 로드맵 제안

### Phase 1: 즉시 개선 (현재 인프라 내)

| 항목 | 액션 | 난이도 | 효과 |
|------|------|--------|------|
| 검색 반환 건수 | `top_k` 파라미터 추가 (5 → 20) | 낮음 | 데이터 커버리지 4배 |
| Claim 모듈 귀속 | HDD 생성 시 모듈-토픽 매핑 검증 | 중간 | FPU/Overlay 오귀속 해결 |
| 토픽 분류 확대 | Tensix, Power, Memory, Clock, NIU 추가 | 중간 | 검색 정밀도 향상 |
| 포트 구조화 | `module_parse` 결과를 JSON 형태로 | 중간 | 비트폭/방향 정보 확보 |

### Phase 2: 파이프라인 확장 (신규 analysis_type)

| 항목 | 신규 analysis_type | 난이도 | 커버 섹션 |
|------|-------------------|--------|----------|
| 패키지 파싱 | `package_parse` | 중간 | §2 (Constants, enum, struct) |
| 포트 상세 추출 | `port_detail` | 중간 | §3 (비트폭, 배열, 파라미터) |
| Generate 분석 | `generate_analysis` | 높음 | §4, §12 (계층, 검증) |
| Assign 추적 | `connectivity_trace` | 높음 | §5, §6, §7, §8 (NoC, Clock, EDC, Dispatch) |

### Phase 3: 고급 기능 (장기)

| 항목 | 설명 | 난이도 | 커버 섹션 |
|------|------|--------|----------|
| RTL Diff | 두 변형 간 포트/인스턴스/파라미터 차이 자동 추출 | 높음 | §13 |
| Cross-file 추적 | `trinity_pkg.sv` ↔ `trinity.sv` 간 참조 해석 | 높음 | §2 ↔ §4 교차 검증 |
| 자동 검증 | Package 선언 vs RTL 인스턴스 일관성 체크 | 높음 | §12 |

---

## 7. 핵심 메트릭 (현재 vs 목표)

| 메트릭 | 현재 | Phase 1 후 | Phase 2 후 | Phase 3 후 |
|--------|------|-----------|-----------|-----------|
| 정답지 섹션 커버리지 | 15% (2/13) | 25% (3/13) | 70% (9/13) | 95% (12/13) |
| 포트 정보 정밀도 | ~20% (이름만) | ~50% (방향+이름) | ~90% (비트폭+배열) | ~98% |
| 모듈 계층 정확도 | ~30% (1단계) | ~40% | ~80% (generate 포함) | ~95% |
| 연결 정보 커버리지 | 0% | 0% | ~60% (assign 추적) | ~85% |
| Claim 모듈 귀속 정확도 | ~50% | ~80% | ~90% | ~95% |

---

## 8. 검색 실험 결과 요약 (이번 세션)

| # | 검색 조건 | 결과 건수 | 유용성 | 비고 |
|---|----------|----------|--------|------|
| 1 | query="EDC" | 101건/5건 반환 | 중간 | hdd_section 중복 많음 |
| 2 | pipeline=tt_20260221, analysis=hdd_section | 86건/5건 반환 | 낮음 | 모두 동일 모듈 대상 |
| 3 | pipeline=tt_20260221, topic=EDC | 37건/5건 반환 | 높음 | Claim 3종 + topic + hdd_section 혼합 |
| 4 | pipeline=tt_20260221, topic=EDC (2차) | 35건/5건 반환 | 높음 | Claim 기반 구조 분석 가능 |
| 5 | pipeline=tt_20260221, topic=NoC | 40건/5건 반환 | 중간 | Repeater/Arbiter Claim 확보 |
| 6 | pipeline=tt_20260221, topic=Dispatch | 76건/5건 반환 | 낮음 | hdd_section만 5건, Claim 0건 |
| 7 | pipeline=tt_20260221, query=noc2axi | 711건/5건 반환 | 중간 | FPU/Overlay 토픽 발견, 오귀속 확인 |
| 8 | pipeline=tt_20260221, query=HDD | 86건/5건 반환 | 낮음 | 토픽 목록 파악에만 유용 |
| 9 | pipeline=tt_20260221, topic=NIU | 0건 | 없음 | NIU 토픽 미존재 |

**총 8회 검색, 유효 Claim 획득: ~15건, 정답지 재현에 필요한 데이터: ~200+ 데이터포인트**

---

## 9. 결론

현재 RAG 시스템은 **"RTL에 대해 이야기하는"** 수준이지, **"RTL을 정밀하게 분석하는"** 수준이 아니다.

엔지니어 원본(`N1B0_HDD_v0.1.md`)은 RTL 소스를 **줄 단위로 읽고 해석**하여 작성되었으며, 이를 자동화하려면 RAG의 역할을 "문서 검색 엔진"에서 **"RTL 구조 분석 엔진"**으로 확장해야 한다.

**가장 임팩트 큰 단일 개선:** `trinity_pkg.sv`와 `trinity.sv`를 대상으로 한 **`package_parse` + `port_detail` + `generate_analysis`** 3개 analysis_type 추가 → 정답지의 §2, §3, §4를 즉시 자동 생성 가능 (커버리지 15% → 45%)

---

*End of RAG Limitations Feedback v1*
