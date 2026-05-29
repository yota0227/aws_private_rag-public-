# RTL RAG 파이프라인 — SoC Engineer 편

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-05-04 | 초판. 원본(rtl-rag-pipeline-architecture.md)에서 SoC Engineer 관점으로 분리 |
| v2.0 | 2026-05-08 | v9.2 기준 업데이트. Phase 7~8 파서 8종 반영, 정답지 대비 80%+ 달성 |
| v3.0 | 2026-05-29 | **v9.4a 기준 전면 업데이트.** 10종 파서(Port Binding/Signal Path Graph/DFX Auto Extractor 추가), assign 부분 지원, AOSS→Qdrant 전환, 정답지 대비 82% |

**대상:** SoC 설계/검증 엔지니어
**목적:** 이 시스템이 RTL 코드를 어떻게 읽고 있는지 이해하고, "이 부분은 이렇게 파싱하면 더 잘 잡힌다"는 개선 의견을 준다.

---

## 1. 이 시스템이 하는 일

RTL 소스 코드를 자동으로 읽어서 **HDD(Hardware Design Document) 초안**을 만든다.

```
여러분이 작성한 RTL (.sv/.v/.svh)
    ↓
자동 파싱 (모듈 구조, 패키지 상수, 포트 분류)
    ↓
지식 베이스(KB)에 저장
    ↓
자연어로 질문하면 KB에서 찾아서 HDD 섹션을 생성
```

**현재 대상:** Trinity/N1B0 RTL (`tt_20260221`, 9,465개 파일)
**정답지(엔지니어 수동 작성 HDD) 대비:** 82% 일치 (v9.4a 기준, v1.0 작성 시점 68%에서 개선)

**이 문서의 목적:** 시스템이 RTL의 어떤 부분을 잡고 있고, 어떤 부분을 못 잡고 있는지 보여드린다. 여러분의 RTL 도메인 지식으로 "이 부분은 이렇게 접근하면 된다"는 피드백을 주시면 파이프라인을 개선할 수 있다.

---

## 2. RTL에서 무엇을 추출하는가

### 2.1 현재 잡고 있는 것 — 10가지 파서 (v9.4a 기준)

#### 파서 ①: 기본 모듈 파서 — "뼈대 추출"

모든 RTL 파일에서 **모듈의 외형**을 추출한다. 사람으로 치면 "이 블록의 이름, 입출력 핀, 내부에 뭘 인스턴스했는지"를 읽는 것이다.

| 추출 항목 | RTL 예시 | 추출 결과 |
|-----------|---------|----------|
| 모듈명 | `module trinity (` | `trinity` |
| 포트 (방향 + 비트폭 + 이름) | `input [SizeX-1:0] i_ai_clk` | `input, [SizeX-1:0], i_ai_clk` |
| 파라미터 | `parameter DATA_WIDTH = 32` | `DATA_WIDTH = 32` |
| 인스턴스 | `tt_dispatch_top u_dispatch (` | `u_dispatch: tt_dispatch_top` |

**비유:** Schematic에서 심볼(symbol)만 읽는 것. 핀 이름과 연결된 인스턴스는 알지만, 내부 로직은 모른다.

#### 파서 ②: Package Parser — "설정 상수 추출"

`*_pkg.sv` 파일에서 **칩 구성을 결정하는 상수와 타입**을 추출한다.

| RTL 코드 | 추출 결과 (자연어 claim) |
|----------|----------------------|
| `localparam int SizeX = 4;` | "Package 'trinity_pkg' defines localparam SizeX = 4" |
| `localparam int SizeY = 5;` | "Package 'trinity_pkg' defines localparam SizeY = 5" |
| `typedef enum logic [2:0] {TENSIX=3'd0, ROUTER=3'd1, ...} tile_t;` | "...defines typedef enum 'tile_t' with 8 members: TENSIX=0, ROUTER=1, ..." |
| `typedef struct packed {...} trinity_clock_routing_t;` | "...defines typedef struct 'trinity_clock_routing_t' with 8 fields" |

**왜 중요한가:** `SizeX=4, SizeY=5`를 모르면 "4×5 그리드"라는 칩의 기본 구조를 기술할 수 없다. `tile_t`를 모르면 타일 종류(TENSIX, ROUTER, DRAM 등)를 나열할 수 없다.

#### 파서 ③: Port Classifier — "포트 기능 분류"

포트가 많은 모듈(10개 이상)에서 **포트 이름 패턴을 보고 기능별로 그룹핑**한다.

trinity.sv의 106개 포트를 9개 카테고리로 분류한 결과:

| 카테고리 | 매칭 기준 (포트 이름 패턴) | 포트 수 | 의미 |
|----------|-------------------------|--------|------|
| **PRTN_Power** | `PRTNUN_*`, `ISO_EN*`, `power_good*` | 14 | 전원 파티션, 아이솔레이션 |
| **EDC_APB** | `edc_apb_*`, `edc_*irq`, `i_edc_*` | 16 | EDC 서브시스템 APB + IRQ |
| **AXI_Interface** | `npu_out_*`, `npu_in_*`, `axi_*` | 39 | 외부 AXI 버스 |
| **APB_Register** | `i_reg_*`, `o_reg_*` | 8 | SFR 레지스터 접근 |
| **DM_Clock_Reset** | `i_dm_clk`, `i_dm_*_reset` | 3 | DM 도메인 |
| **AI_Clock_Reset** | `i_ai_clk`, `i_ai_reset` | 2 | AI 도메인 |
| **NoC_Clock_Reset** | `i_noc_clk`, `i_noc_reset` | 2 | NoC 도메인 |
| **Tensix_Reset** | `i_tensix_reset` | 1 | Tensix 코어 리셋 |
| **SFR_Memory_Config** | `SFR_*`, `sfr_*` | 17 | SRAM 설정 |
| Other | (위에 해당 안 되는 것) | 4 | 미분류 |
| **합계** | | **106** | |

**왜 필요한가:** 106개 포트를 한꺼번에 나열하면 AI가 중요한 포트를 놓친다. "Power 관련 포트가 뭐야?"라고 물었을 때 PRTN_Power 14개를 정확히 답하려면 미리 분류해둬야 한다.

### 2.2 정리 — 파서가 보는 RTL의 범위 (v9.2 기준)

```
RTL 코드 전체
├── ✅ 모듈 선언 (module ... endmodule)        ← 기본 파서
│   ├── ✅ 포트 목록 (input/output/inout)       ← 기본 파서 + Port Classifier
│   ├── ✅ 파라미터 (parameter/localparam)      ← 기본 파서
│   └── ✅ 인스턴스 (모듈타입 인스턴스명)        ← 기본 파서
│
├── ✅ 패키지 파일 (*_pkg.sv)                   ← Package Parser (확장됨)
│   ├── ✅ localparam (SizeX, SizeY, ...)
│   ├── ✅ typedef enum (tile_t, ...)
│   ├── ✅ typedef struct (clock_routing_t, ...) + 필드별 비트폭 + 중첩 struct
│   ├── ✅ function / task 시그니처 + 본문 요약  ← v9 신규
│   └── ✅ EP Index Table 계산 (EP = X×SizeY+Y) ← v9.2 신규
│
├── ✅ always_ff 블록 (클럭 도메인 추출)         ← Always Block Parser (v9 신규)
│   ├── ✅ 클럭 도메인 식별 (AI, NoC, DM 등)
│   ├── ✅ CDC 경고 (2+ 도메인 감지 시)
│   └── ✅ 리셋 신호 추출
│
├── ✅ generate for/if 블록                      ← Generate Block Parser (v9 신규)
│   ├── ✅ 토폴로지 패턴 인식 (daisy-chain, ring, feedthrough, 2D array)
│   ├── ✅ 조건부 bypass 감지
│   ├── ✅ 인스턴스-위치 매핑 (X,Y 좌표)         ← v9.2 신규
│   └── ✅ NoC repeater 추출                     ← v9.2 신규
│
├── ✅ wire 선언                                 ← Wire Declaration Parser (v9.2 신규)
│   ├── ✅ struct 타입 wire (clock_routing_t 등)
│   ├── ✅ 배열 차원 파싱 ([SizeX][SizeY] 등)
│   ├── ✅ 목적 유추 (dispatch feedthrough, clock distribution 등)
│   └── ✅ 비트폭 표현식 평가 (SizeX-1 → 3)     ← Bitwidth Evaluator (v9 신규)
│
├── ❌ always_comb 블록 (조합 로직)              ← 미지원
│   ├── FSM 상태 전이
│   └── mux 선택 로직
│
├── ❌ assign 문                                 ← 미지원
│   └── 신호 구동 관계
│
└── ❌ interface / modport                       ← 미지원
    └── 구조화된 포트 번들
```

---

## 3. v9.2에서 해결된 것과 남은 갭

아래는 v1.0 시점에서 "못 잡고 있는 것"으로 분류했던 사례들의 현재 상태다.

### 3.1 ✅ 해결됨: Generate 블록 — 배선 토폴로지

**v9.2 상태:** Generate Block Parser가 4가지 토폴로지 패턴(daisy-chain, ring, feedthrough, 2D array)을 자동 인식한다. 조건부 bypass도 감지한다.

**정답지에 있는 내용:**
> "EDC는 U-shape ring topology로 연결되며, harvest된 타일은 bypass된다."

**RTL에 있는 곳:** `trinity.sv`의 `generate for` 블록

```systemverilog
// 예시 (실제 코드 구조)
generate
  for (genvar x = 0; x < SizeX; x++) begin : gen_edc_col
    for (genvar y = 0; y < SizeY; y++) begin : gen_edc_row
      if (tile_type[x][y] != HARVESTED) begin
        // EDC 인스턴스 연결
        tt_edc u_edc (
          .i_serial_in  (edc_chain[x][y]),
          .o_serial_out (edc_chain[x][y+1]),
          ...
        );
      end else begin
        // Bypass
        assign edc_chain[x][y+1] = edc_chain[x][y];
      end
    end
  end
endgenerate
```

**v9.2 결과:** claim 예시: `"Module 'unknown' has generate block 'gen_l1_dcache_tag_edc' with daisy-chain topology connecting l1_dcache_tag_edc_egress_intf across inst (NUM_DCACHE_TAG_ECC_SOURCES elements)"`

**남은 질문:** 인덱스 패턴에서 "U-shape"과 "linear chain"을 구분하는 추가 휴리스틱이 필요한가?

### 3.2 ✅ 부분 해결: Always 블록 — 클럭 도메인 추출

**v9.2 상태:** Always Block Parser가 `always_ff` 블록에서 클럭 도메인을 추출한다. `@(posedge i_ai_clk)` → "AI 도메인". 2개 이상 도메인 감지 시 CDC 경고 claim을 생성한다.

**아직 못 잡는 것:** FSM 상태 전이, `always_comb` 내부 로직 (DOR 라우팅 알고리즘 등)

**정답지에 있는 내용:**
> "NoC는 DOR(Dimension-Ordered Routing) 알고리즘을 사용하며, X-first 순서로 라우팅한다."

**RTL에 있는 곳:** `tt_noc_router.sv`의 `always_comb` 블록

```systemverilog
// 예시 (실제 코드 구조)
always_comb begin
  case (route_state)
    ROUTE_X: begin
      if (dest_x != curr_x)
        next_port = (dest_x > curr_x) ? PORT_EAST : PORT_WEST;
      else
        route_state_next = ROUTE_Y;
    end
    ROUTE_Y: begin
      if (dest_y != curr_y)
        next_port = (dest_y > curr_y) ? PORT_NORTH : PORT_SOUTH;
      else
        next_port = PORT_LOCAL;
    end
  endcase
end
```

**질문:** 이 `case` 문에서 "DOR, X-first"라는 알고리즘 이름을 추론할 수 있는가? 아니면 이건 Spec 문서에서만 얻을 수 있는 정보인가?

### 3.3 ✅ 해결됨: Wire 선언 — 신호 구동 관계 (Dispatch Feedthrough)

**v9.2 상태:** Wire Declaration Parser가 `de_to_t6_coloumn`, `t6_to_de` 등 dispatch feedthrough wire를 자동 추출한다. 배열 차원과 목적(dispatch-to-tensix feedthrough)을 유추한다.

**v9.2 결과:** claim 예시: `"Wire 'de_to_t6_coloumn' of type 'tt_chip_global_pkg::de_to_t6_t' with dimensions [trinity_pkg::SizeX, trinity_pkg::SizeY-1] (4×4 array) for dispatch-to-tensix feedthrough"`

**정답지에 있는 내용:**
> "Dispatch Engine은 column 방향으로 feedthrough 구조를 가지며, `de_to_t6_column`과 `t6_to_de` 신호로 연결된다."

**RTL에 있는 곳:** `trinity.sv`의 `assign` 문 + `generate` 블록

```systemverilog
// 예시 (실제 코드 구조)
generate
  for (genvar y = 0; y < SizeY; y++) begin : gen_dispatch_col
    assign de_to_t6_column[y] = (y == 0) ? dispatch_out : t6_to_de[y-1];
  end
endgenerate
```

**질문:** `de_to_t6_column[y] = (y==0) ? dispatch_out : t6_to_de[y-1]` 패턴에서 "column feedthrough (daisy-chain)"이라는 구조를 자동으로 인식할 수 있는가? 어떤 패턴이 feedthrough의 시그니처인가?

### 3.4 ✅ 해결됨: Package 함수 — 인덱스 계산

**v9.2 상태:** Package Function/Task Extractor가 함수 시그니처 + 본문 20줄 이하 시 1줄 요약을 추출한다. `getTensixIndex`, `getNoc2AxiIndex`, `getApbIndex`, `getDmIndex` 등 헬퍼 함수가 모두 추출된다.

**v9.2 결과:** claim 예시: `"Package 'trinity_pkg' defines function 'isEastEdge(int x) → bit' [automatic]"`

**정답지에 있는 내용:**
> "Tensix 타일의 인덱스는 `getTensixIndex(x, y)` 함수로 계산되며, harvested 타일을 건너뛴다."

**RTL에 있는 곳:** `trinity_pkg.sv`의 `function`

```systemverilog
// 예시 (실제 코드 구조)
function automatic int getTensixIndex(int x, int y);
  int idx = 0;
  for (int i = 0; i < x; i++)
    for (int j = 0; j < y; j++)
      if (tile_map[i][j] == TENSIX) idx++;
  return idx;
endfunction
```

**질문:** 이 함수의 로직("harvested 타일을 건너뛰며 카운트")을 자동으로 요약할 수 있는가? 아니면 함수 시그니처(`getTensixIndex(int x, int y) → int`)만 추출해도 충분한가?

### 3.5 ✅ 해결됨: Clock Routing — 2D 배열 배선

**v9.2 상태:** Wire Declaration Parser가 `trinity_clock_routing_t clock_routing_in[SizeX][SizeY]` 패턴을 인식하고, struct 타입 참조 + 배열 차원 + 목적(clock distribution)을 claim으로 생성한다.

**v9.2 결과:** claim 예시: `"Wire 'clock_routing_in' of type 'trinity_pkg::trinity_clock_routing_t' with dimensions [SizeX-1:0, SizeY-1:0] (4×5 array) for clock distribution"`

### 3.6 ❌ 남은 갭: always_comb FSM 로직

**정답지에 있는 내용:**
> "NoC는 DOR(Dimension-Ordered Routing) 알고리즘을 사용하며, X-first 순서로 라우팅한다."

**현재 상태:** `always_comb` 내부의 FSM 상태 전이, case 문 로직은 아직 파싱하지 않는다. 알고리즘 이름(DOR, Tendril 등)은 Spec 문서 또는 주석에서만 얻을 수 있다.

### 3.7 ❌ 남은 갭: assign 문 신호 구동 관계

**현재 상태:** `assign` 문의 좌변→우변 구동 관계는 아직 추출하지 않는다. Wire Declaration Parser가 wire 선언 자체는 잡지만, assign을 통한 연결 관계는 미지원.

**정답지에 있는 내용:**
> "클럭은 `clock_routing_in[SizeX][SizeY]` / `clock_routing_out[SizeX][SizeY]` 2D 배열로 각 타일에 분배된다."

**RTL에 있는 곳:** `trinity.sv`의 wire 선언 + generate 블록

```systemverilog
// 예시 (실제 코드 구조)
trinity_clock_routing_t clock_routing_in  [SizeX][SizeY];
trinity_clock_routing_t clock_routing_out [SizeX][SizeY];

generate
  for (genvar x = 0; x < SizeX; x++) begin : gen_clk_x
    for (genvar y = 0; y < SizeY; y++) begin : gen_clk_y
      assign clock_routing_in[x][y].ai_clk = i_ai_clk;
      // ... 타일별 클럭 연결
    end
  end
endgenerate
```

**질문:** `struct_type signal_name [SizeX][SizeY]` 패턴을 보면 "2D 배열 분배 구조"라고 자동 인식할 수 있는가? 이 패턴이 클럭 라우팅에만 쓰이는가, 아니면 다른 용도로도 쓰이는가?

---

## 4. 개선 의견을 구하는 영역

위 사례들을 종합하면, 다음 5가지 영역에서 SoC 엔지니어의 도메인 지식이 필요하다.

### 4.1 Generate 블록 토폴로지 인식

| 질문 | 배경 |
|------|------|
| Generate 블록에서 반복되는 배선 패턴(ring, mesh, daisy-chain, tree)을 어떻게 구분하는가? | 인덱스 패턴(`[x][y]`, `[y-1]`, `[x+1]`)만으로 토폴로지를 추론할 수 있는지 |
| Harvest bypass 패턴을 일반화할 수 있는가? | `if (tile_type != HARVESTED)` 외에 다른 조건부 bypass 패턴이 있는지 |

### 4.2 Always 블록 동작 요약

| 질문 | 배경 |
|------|------|
| FSM의 상태 이름(`IDLE`, `ROUTE_X`, `ROUTE_Y`)에서 동작을 요약할 수 있는가? | 상태 이름이 의미 있는 경우와 `S0`, `S1` 같은 경우의 비율 |
| `always_ff`에서 클럭 도메인을 추출하는 것만으로도 가치가 있는가? | `@(posedge i_ai_clk)` → "이 로직은 AI 도메인" |

### 4.3 Package 함수/태스크

| 질문 | 배경 |
|------|------|
| `function`의 시그니처만 추출해도 HDD에 충분한가? | 아니면 함수 본문의 로직 요약이 필요한가 |
| 자주 쓰이는 유틸리티 함수 패턴이 있는가? | 인덱스 계산, 좌표 변환, 설정 조회 등 |

### 4.4 포트 분류 카테고리

| 질문 | 배경 |
|------|------|
| 현재 9개 카테고리가 적절한가? | 빠진 카테고리(예: DFT, JTAG, Scan)가 있는지 |
| 카테고리 이름이 직관적인가? | 예: `PRTN_Power`보다 `Power_Partition`이 나은지 |
| 다른 칩/블록에도 이 카테고리가 재사용 가능한가? | Trinity 전용인지, 범용적인지 |

### 4.5 비트폭 해석

| 질문 | 배경 |
|------|------|
| `[SizeX-1:0]`을 `[3:0]`으로 평가해야 하는가? | 현재는 문자열 그대로 저장 |
| 비트폭이 HDD에서 중요한 정보인가? | 아니면 "multi-bit"/"single-bit" 정도면 충분한가 |

---

## 5. 피드백 방법

**가장 도움이 되는 피드백 형태:**

```
[섹션 3.X 관련]
- 이 RTL 패턴은 <패턴 이름>이라고 부른다
- <파일명>의 <라인 범위>를 보면 이 패턴이 있다
- 이걸 파싱하려면 <접근 방법>이 효과적이다
- HDD에서 이 정보는 <섹션명>에 들어간다
```

**예시:**
```
[섹션 3.1 관련 — EDC Ring Topology]
- 이건 "serial scan chain with bypass" 패턴이다
- tt_edc_top.sv의 generate 블록을 보면 된다
- 연결 방향은 인스턴스의 .i_serial_in / .o_serial_out 포트명으로 판단 가능
- HDD에서는 "EDC Subsystem" 섹션의 "Topology" 항목에 들어간다
```

---

*피드백: Confluence 댓글 또는 Slack #bos-ai-rag*
