# v5.1 Review — 정답지 비교 + v4 → v5 → v5.1 진화 분석

**Review Date:** 2026-04-28
**Reviewer:** Claude (Opus 4.7)
**Scope:** `test_rtl/rag_result/v5.1/` 5개 문서 vs `test_rtl/Sample/ORG/` 정답지
**Progression:** v4 (RAG v3.x) → v5 (RAG v4.0) → v5.1 (RAG v4.1)

---

## 0. TL;DR

| Dim | v4 | v5 | v5.1 | Δ |
|-----|----|----|------|---|
| Grounded coverage | ~17% | 18% | **59%** | **+41pp** (3.3×) |
| No Grounding 완성도 | 부분 (399줄) | 붕괴 (123줄) | **완전 (494줄)** | 회복 |
| Ground truth 정확도 | 낮음 | 낮음 | **중간** | 주요 모듈명 일치 |
| 여전한 gap | 구조/파라미터 | 구조/파라미터 | 알고리즘/수치 파라미터 | 정성 → 정량 |

**한 줄 결론:** v5.1은 **RAG 튜닝의 승리**다. `module_parse` boost를 0.3 → 1.5로 올려 RTL 모듈 이름·포트가 복구됐고, 정답지 대비 **골격은 맞지만 알고리즘 본문(DOR, ATT, FDS 등)과 수치 파라미터는 여전히 KB에 없거나 누락**되어 있다.

---

## 1. v5.1 vs 정답지 (Sample/ORG) 상세 비교

### 1.1 Chip-level: `v5.1_chip_grounded.md` vs `N1B0_NPU_HDD_v0.1.md`

| 섹션 | 정답지 (1291줄) | v5.1 Grounded (295줄) | 일치도 |
|------|----------------|----------------------|--------|
| **1. Overview** | 4×5 mesh, 12 Tensix, N1B0 차이 테이블 | "KB-confirmed 17 modules" 리스트 | ⚠️ 골격만 |
| **2. Package Constants** | `SizeX=4, SizeY=5, NumTensix=12, NumNoc2Axi=4` 등 9개 + tile_t 8개 enum + EndpointIndex 테이블 | `[NOT IN KB]` | ❌ 완전 누락 |
| **3. Top-Level Ports** | `i_ai_clk[3:0]`, `i_edc_apb_*`, PRTN/ISO_EN 상세 + AXI 게스킷 | `[NOT IN KB]` | ❌ 완전 누락 |
| **4. Module Hierarchy** | trinity → gen_tensix_neo / dispatch_e/w / NOC2AXI_ROUTER 전체 | 평면화된 17개 모듈 리스트 | ⚠️ 부분 |
| **5. SFPU** | `tt_sfpu` 내부 (EXP/LOG/GELU 등 14 format) | `tt_sfpu_lregs`, `tt_sfpu_instrn_resources_used` verbatim | ✅ 모듈명 일치 |
| **6. SMN** | — (N1B0 HDD에는 없음) | `tt_smn_clkdiv 5/3`, `tt_smn_repeater_struct 16/8` | ✅ 추가 정보 |
| **7. TDMA** | tt_tdma 상세 (Unpack CH0/CH1 등) | `tt_tdma_thread_context` 한 줄 | ❌ 얕음 |
| **8. NoC** | DOR/Tendril/Dynamic + 5포트 + 928-bit routing list | `tt_upf_async_fifo`, `tt_niu_mst_timeout` 3개 모듈만 | ❌ 알고리즘 부재 |
| **9. EDC** | node_id 구조, U-shape ring, harvest demux/mux 상세 | `tt_edc1_serial_bus_repeater`, `tt_edc1_noc_sec_block_reg` 2개 | ❌ 토폴로지 부재 |
| **10. Overlay** | — (N1B0 HDD 기준 없음) | FDS tensixneo/dispatch reg, L1 CSR 포트수 | ✅ 보강 |
| **11. Clock** | ai_clk/noc_clk/dm_clk/axi_clk 4도메인 + clock_routing_t struct | `tt_clkbuf`, `tt_clkgater`, `tt_clkdiv2` 셀만 | ❌ 도메인 매트릭스 부재 |
| **12. Reset** | reset tree + harvest reset 전체 | `[NOT IN KB]` | ❌ |
| **13. SRAM** | 12 tiles × 16 banks × 3072×128 + LDM/VC/ATT 전체 | `tt_mem_wrap_32x1024_2p_nomask` 1개 | ❌ 얕음 |
| **14. DFX** | 4개 DFX 모듈 + IJTAG 체인 | `noc_routing_translation_selftest` 1개 | ❌ 얕음 |

**정답지 대비 v5.1 Grounded 점수: ~30%** (모듈 이름은 잡아내나, 알고리즘·구조·파라미터는 KB에 조각으로만 존재)

### 1.2 Chip-level: `v5.1_chip_no_grounding.md` vs `N1B0_NPU_HDD_v0.1.md`

| 항목 | 정답지 | v5.1 No Grounding | 평가 |
|------|--------|-------------------|------|
| Grid 배치 | **SizeX=4, SizeY=5** (4열×5행) | ❌ "GridSizeX=5, GridSizeY=4" (뒤집힘) | **틀림** |
| Tensix 개수 | 12 (Y=0..2, X=0..3) | 12 ✅ | 맞음 |
| 비-Tensix 타일 | NOC2AXI×4 + Dispatch×2 + Router placeholder×2 | "ETH×2 + DRAM×2 + PCI×1 + ARC×1 + ROUTER×2" | ❌ 전혀 다름 (일반 SoC 스테레오타입) |
| EDC 인터페이스 | `edc_apb_psel/paddr/pwdata[3:0]` per-column, 5 IRQ per column | "tt_edc_pkg.sv 4 modports: ingress/egress/edc_node/sram" | ✅ 모듈명 정확 but 상세 틀림 |
| Clock 도메인 | ai_clk/noc_clk/dm_clk/axi_clk/ref_clk (PRTN_CLK 별도) | "ai_clk/noc_clk/dm_clk/ref_clk" | ⚠️ axi_clk 누락, ref_clk 용도 틀림 |
| Routing algorithm | DOR (X-first), Tendril, Dynamic (928-bit list) | "DOR / Tendril / Dynamic" 이름만 | ⚠️ 내부 동작 환각 |
| Flit 구조 | 2083-bit (32 parity + 3 type + 2048 payload), 512-bit common header | "116-bit data + 10-bit SECDED, HEAD/BODY/TAIL/SINGLE" | ❌ 완전히 다름 |
| ATT | 16-mask × 1024-endpoint × 32-routing tables | 언급 없음 | ❌ |

**정답지 대비 v5.1 No Grounding 점수: ~20%** (모듈 이름은 KB에서 잘 가져왔으나, 전체 구조를 **상상**하는 부분에서 사실과 반대되는 정보 다수)

### 1.3 EDC: `v5.1_edc.md` vs `EDC_HDD_V0.3.md` (2894줄 정답지)

| 섹션 | 정답지 | v5.1 EDC (107줄) |
|------|--------|------------------|
| 링 토폴로지 | 컬럼별 독립 U-shape ring, Y=4에서 down → Y=0에서 U-turn → loopback up | `[NOT IN KB] — U-shape not returned` |
| Harvest bypass | mux/demux 페어 RTL 구조 + eFuse boot 로직 | `[NOT IN KB]` |
| Node_id master decode | part[4:0]/subp[2:0]/inst[7:0] 마스터 테이블 (0x10~0x1E) | `[NOT IN KB]` |
| BIU | APB4 상세 + 5개 IRQ | ✅ **정확히 일치** (`s_apb_{psel,penable,pwrite,pprot,paddr,pwdata,pstrb}` + 5 IRQ) |
| 패킷 포맷 | 16b data + 1b parity, max 12 frags | `[NOT IN KB]` |
| Serial bus | req_tgl/ack_tgl/data/data_p/async_init/err | `i_clk, i_reset_n` 만 |

**v5.1 EDC 점수: ~25%** (BIU 포트는 완벽, 나머지는 KB 부재로 [NOT IN KB])

### 1.4 NoC: `v5.1_noc.md` vs `router_decode_HDD_v0.5.md`

| 섹션 | 정답지 | v5.1 NoC (99줄) |
|------|--------|-----------------|
| 5-port router | NIU/Y+/X+/Y-/X- | `[NOT IN KB]` |
| DOR 의사코드 | XY vs YX, tendril, force_dim 전체 분기 | `[NOT IN KB]` |
| ATT 3-stage | Mask(16) → Endpoint(1024) → Routing(32) | `[NOT IN KB]` |
| Flit format | 2048 payload + 3 type + 32 parity | SECDED: `DATA_WIDTH=116, ECC_WIDTH=10` ✅ (다른 변형) |
| 보조 모듈 | — | `tt_noc_repeaters_cardinal`, `tt_skid_buffer_new_assertion_off`, `tt_upf_async_fifo`, `tt_noc_async_fifo_wr_side_reset`, `tt_noc_sync3_pulse`, `tt_harvest_robust_sync`, `tt_niu_mst_timeout` ✅ |
| NIU HDL path | `trinity.gen_x[X].gen_y[Y]...reg_intf[0].risc_reg_if` | `[NOT IN KB]` |
| AXI gasket | 56-bit [55:52]rsvd/[51:46]Y/[45:40]X/[39:0]local | `[NOT IN KB]` |

**v5.1 NoC 점수: ~30%** (보조 모듈 리스트는 풍부하나, 라우팅 알고리즘과 ATT 부재)

### 1.5 Overlay: `v5.1_overlay.md` vs `overlay_HDD_v0.3.md`

| 섹션 | 정답지 | v5.1 Overlay (100줄) |
|------|--------|----------------------|
| 8 harts RV64GC | `NUM_CLUSTER_CPUS=8`, Quasar cluster | `[NOT IN KB]` |
| iDMA | 24 client / 2 BE / 32 TID / FIFO=42 | `[NOT IN KB]` |
| ROCC | CUSTOM_0~3, per-hart, 2× parallel addr gen | `[NOT IN KB]` |
| FDS | 3 droop source / 16 IRQ group / 32-bit AD counter + regfile | `tt_fds_tensixneo_reg (106/41)`, `tt_fds_dispatch_reg (68/41)` 포트수 ✅ |
| L1 CSR | tt_t6_l1_partition + flex-client RW/RD/WR | `tt_cluster_ctrl_t6_l1_csr_reg (38/97)` ✅ 포트수 |
| SMN | AXI4-Lite daisy → APB master | `[NOT IN KB]` |
| NIU/router VC | 5 VC × 64×2048 SRAM | `[NOT IN KB]` |

**v5.1 Overlay 점수: ~20%** (FDS 모듈 포트수는 정확, 나머지 대부분 부재)

---

## 2. v4 → v5 → v5.1 진화 분석

### 2.1 RAG 설정 변화

| | v4 (v3.x) | v5 (v4.0) | v5.1 (v4.1) |
|---|-----------|-----------|-------------|
| analysis_type 필터 | 없음 (`"HDD"`만) | ✅ passthrough | ✅ passthrough |
| claim boost | 1.0 | 3.0 | 3.0 |
| hdd boost | 1.0 | 2.0 | 2.0 |
| **module_parse boost** | 1.0 | **0.3** ⬇ | **1.5** ⬆ |
| 대표 검색량 | 20/115 | 20 | 20 |

### 2.2 Grounded 모드 출력 길이·커버리지

| | v4b (217줄) | v5 (216줄) | v5.1 (295줄) |
|---|-------------|------------|--------------|
| HDD 섹션 검색 | 5 found | 2 (analysis_type 필터 효과) | 2 |
| Claims | 많음 (claim 3개만 visible) | **14개** | **11개** |
| Module_parse | 많음 (17개 visible) | **없음 (0.3 boost 탓)** | **9개 복귀** |
| Coverage 선언 | N/A | **18%** | **59%** |
| 핵심 모듈명 (lregs, tdma_thread_context 등) | 일부 | 부분 | ✅ 17개 |
| 포트수 (106/41, 38/97, 16/8) | ❌ | ❌ | ✅ |

**핵심 인사이트:** v4 → v5는 analysis_type 필터를 더해 정확도를 노렸으나 `module_parse boost=0.3` 때문에 모듈 이름·포트가 완전히 사라짐. **v5.1에서 `module_parse boost=1.5`로 복원**하자마자 17개 RTL 모듈이 돌아오고 coverage 3.3× 개선.

### 2.3 No Grounding 모드 — 붕괴 → 회복

| | v4a (399줄) | v5 (123줄) | v5.1 (494줄) |
|---|-------------|------------|--------------|
| 섹션 수 | 14 (Appendix 포함) | 9 (부분) | **14 완전** |
| [NOT IN KB] 빈도 | 높음 | 매우 높음 | 낮음 (No Grounding이니 허용됨) |
| RTL 모듈 인용 | 7개 | 5개 | **20개+ (Appendix에 전체 테이블)** |
| 환각 경향 | 중간 | 적음 (정보 없음) | **중간 (상상 추가)** |
| 구조 (ASCII 다이어그램) | 없음 | 없음 | ✅ 그리드, 트리 |

**인사이트:** v5에서 No Grounding 모드는 `module_parse=0.3` 탓에 RAG 결과 자체가 얇아 LLM이 쓸 컨텍스트가 부족 → **문서 생성이 중간에 truncate**. v5.1에서 module_parse 복원과 함께 완전한 문서 생성 능력도 돌아옴.

### 2.4 토픽별 문서 진화

| 문서 | v4 | v5 | v5.1 | 개선 포인트 |
|------|----|----|------|-------------|
| EDC | 441줄 (혼재) | 107줄 (간결하나 [NOT IN KB] 많음) | 107줄 | **변화 미미** — 토픽 한정 검색 결과 자체가 8개로 고정 |
| NoC | 415줄 | 99줄 | 99줄 | 동일 — 14개 결과 |
| Overlay | 479줄 | 100줄 | 100줄 | 동일 — 7개 결과 |
| chip_grounded | 217줄 (17% coverage) | 216줄 (18%) | **295줄 (59%)** | **여기만 3.3× 도약** |
| chip_no_grounding | 399줄 | 123줄 (truncated) | **494줄** | **완전 회복** |

**결론:** **module_parse boost 변경의 효과는 "chip-level" 쿼리에서만** 나타난다. 왜냐하면 토픽별 쿼리(EDC/NoC/Overlay)는 이미 topic 필터로 claim이 우세하게 매칭되기 때문. 반면 chip-level 쿼리는 module_parse 기여가 결정적이었다.

---

## 3. 정답지와의 근본적 격차 — 왜 v5.1도 여전히 30~59%인가

### 3.1 KB에 있는 것 vs 없는 것

| 카테고리 | KB 포함 | KB 부재 |
|----------|---------|---------|
| **모듈 이름** | ✅ tt_fds_tensixneo_reg, tt_cluster_ctrl_t6_l1_csr_reg, tt_niu_mst_timeout 등 17개 | — |
| **포트 수/이름** | ✅ FDS (106/41), L1 CSR (38/97), BIU APB4 전체 | — |
| **RTL 파일 경로** | ✅ tt_edc_pkg.sv 3 variants | 대부분 module_parse에 없음 |
| **HDD overview 문장** | ✅ SFPU/NoC 각 1~2 문장 verbatim | — |
| **파라미터 상수** | 부분 (DATA_WIDTH=116, TABLE_DEPTH=1024) | ❌ SizeX=4, SizeY=5, NumTensix=12, tile_t enum, 4×5 grid 전개 |
| **알고리즘 본문** | ❌ | DOR pseudo code, ATT 3-stage lookup, FDS CDC FIFO, harvest boot logic |
| **토폴로지 그림** | ❌ | EDC U-shape ring, grid 배치, clock routing 트리 |
| **데이터 구조 정의** | ❌ | `noc_header_address_t`, `noc_common_hdr_t`, `trinity_clock_routing_t` |
| **타이밍/CDC** | ❌ | async_fifo 위치, sync3r, MCP setup/hold |
| **주소 맵** | ❌ | AXI 56-bit [55:52]rsvd/[51:46]Y/..., SMN 8 ranges |

### 3.2 근본 원인

1. **module_parse는 "껍데기"만 담는다** — 모듈 선언부의 포트 리스트 수준. 항상 ModuleName, In/Out 카운트, 포트명 목록 정도.
2. **claim은 "한 줄 요약"만 담는다** — "tt_sfpu_lregs: register file with support for transposing or shifting data" 수준.
3. **hdd_section도 "overview" 수준** — 각 섹션의 첫 문단 수준만 색인된 듯.
4. 결과적으로 **"알고리즘 본문"·"데이터 구조 본문"·"주소 맵 테이블"은 KB 자체에 없음.**

정답지의 깊이(예: 정답지 EDC_HDD_V0.3.md = 2894줄, DOR pseudo code 전체, node_id 마스터 테이블 전체)를 RAG로 복원하려면 **KB chunking 전략을 "이름 레벨" → "섹션 레벨" → "pseudo code 블록 레벨"로 확장**해야 한다.

---

## 4. No Grounding 모드에서 드러난 v5.1 환각 패턴

**Grid 배치 뒤집기 (Critical):**
- 정답지: `SizeX=4, SizeY=5` (4 columns × 5 rows)
- v5.1 No Grounding: `GridSizeX=5, GridSizeY=4` (5 cols × 4 rows) ❌

**비-Tensix 타일 종류 환각:**
- 정답지: NOC2AXI (4개) + Dispatch (2개) + ROUTER placeholder (2개)
- v5.1: "ETH×2 + DRAM×2 + PCI×1 + ARC×1 + ROUTER×2" ❌ (일반 SoC에서 가져온 것으로 추정)

**Flit 폭 환각:**
- 정답지: 2048-bit payload
- v5.1: "116-bit data + 10-bit SECDED ECC" (이건 `tt_noc_secded_chk_corr_116_10` KB 결과를 flit 폭으로 오해)

**Clock 도메인 수 환각:**
- 정답지: 5개 (ai_clk, noc_clk, dm_clk, axi_clk, ref_clk)
- v5.1: 4개 (axi_clk 누락, dm_clk 용도 혼동)

**왜 중요한가:** No Grounding 모드를 실제 HDD 초안 후보로 쓰려면, 이런 "골격 환각"이 downstream 검증 엔지니어에게 혼란을 준다. **Grounded + 사람 보강** 조합이 훨씬 안전하다.

---

## 5. 권고

### 5.1 즉시 유지
- ✅ `module_parse boost = 1.5` — v5.1의 핵심 성과, 절대 되돌리지 말 것
- ✅ `analysis_type` passthrough — 토픽별 쿼리 정확도에 기여
- ✅ `claim boost = 3.0, hdd boost = 2.0` — 현행 유지

### 5.2 다음 RAG 버전(v4.2 or v5)에서 시도할 것

1. **KB chunking 확장 (가장 효과 큼)**
   - 현재: 모듈 헤더 + 1~2문장 overview
   - 목표: **RTL 파일 내 섹션별 ASCII 다이어그램, pseudo code 블록, `typedef struct` 블록**도 인덱싱
   - 효과 예상: Grounded 59% → 80%+

2. **`trinity_pkg.sv` 같은 패키지 파일에 특별 파서 적용**
   - `SizeX=4, SizeY=5, NumTensix=12, tile_t enum 8개` 같은 상수 테이블을 **구조화된 claim**으로 추출
   - 현재 이 값이 `[NOT IN KB]`인 이유: module_parse는 module 선언만 보고 package 상수는 놓치는 듯

3. **`.md` 파일(정답지)도 KB에 포함하여 style 학습**
   - `N1B0_NPU_HDD_v0.1.md`, `EDC_HDD_V0.3.md` 등을 KB에 추가
   - 단, "정답 유출" 방지를 위해 **한번 human-validated HDD**만 등록 (RAG Farm 전략 ③번과 연동)

4. **No Grounding 환각 감소**
   - 프롬프트에 "If you don't see SizeX/SizeY in KB, do not guess — default to `[NOT IN KB]`" 명시
   - 현재는 일반 SoC 지식으로 채우는 경향

5. **max_results 증가 실험**
   - 현재 chip-level 20 → 30~50로 올리면 tile 카운트, 주소 맵 등 세부 claim이 더 들어올 가능성
   - v4에서 "20 of 115 results"라 했으니, 검색 풀은 충분

### 5.3 장기 (RAG Farm 연계)

정답지 수준의 HDD를 자동 생성하려면 RTL RAG 혼자서는 한계. **Spec RAG에 프로토콜 사양서(AXI/APB) + Sample HDD 템플릿을 올려서 RTL RAG와 합치는 듀얼 검색**이 다음 단계. (Strategy doc 1.2 참조)

---

## 6. 코멘트

- v5 리뷰에서 지목한 `module_parse boost 0.3 → 1.5` 수정이 **예측대로 작동**했다 — 이는 RAG 튜닝 루프가 실제로 돌아간다는 좋은 신호.
- v5.1 chip_no_grounding의 494줄짜리 완성품은 **첫인상은 좋지만 검증에 위험**. Grounded 모드와 반드시 교차 검토 필요.
- 정답지의 정보 밀도(N1B0_NPU_HDD_v0.1.md 1291줄, EDC_HDD_V0.3.md 2894줄)는 **사람이 RTL 다 읽고 쓴 결과**. RAG가 이 수준까지 가려면 chunking 전략 근본 개선 + Spec RAG 합류가 필수.

---

*Review complete — 2026-04-28*
