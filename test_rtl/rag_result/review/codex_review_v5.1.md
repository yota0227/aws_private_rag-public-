# Codex Review: RAG v5.1 정답지 비교 및 v4 → v5 → v5.1 변화 분석

**작성일:** 2026-04-28  
**리뷰어:** Codex  
**비교 경로:** `C:\Users\Seung-IlWoo\aws_private_rag\test_rtl`  

---

## 0. 결론

v5.1은 v5의 "너무 짧고 빈칸 많은 결과"에서 상당히 회복했다. 특히 `chip_no_grounding`은 정답지와 비슷한 HDD 목차를 거의 복원했고, `chip_grounded`도 v5 대비 커버리지가 크게 올라갔다.

하지만 정답지 재현 관점에서는 아직 합격선이 아니다. 가장 큰 문제는 v5.1 `chip_no_grounding`이 문서 완성도는 좋아졌지만, 정답지의 핵심 좌표계인 `SizeX=4`, `SizeY=5`, `NOC2AXI_ROUTER_NE/NW_OPT`, `DISPATCH_E/W`, `PRTN`, `ISO_EN`, 정확한 top-level port 구조를 틀리거나 빠뜨린다는 점이다.

특히 `GridSizeX=5`, `GridSizeY=4`, `ARC/DRAM/ETH/PCI` 타일을 넣은 부분은 정답지 기준으로 큰 오답이다. v5.1은 문서 형태와 retrieval 폭은 살아났지만, N1B0 Trinity의 4x5 package/grid/port/hierarchy 핵심을 아직 고정하지 못했다.

한 문장으로 요약하면:

> **v5.1은 v5 대비 개선은 맞지만, 정답지 대비로는 "형태 회복 + factual drift 잔존" 상태다.**

---

## 1. 참고한 파일

### 정답지

| 파일 | 역할 |
|---|---|
| `test_rtl/Sample/N1B0_HDD_v0.1.md` | 주 비교 기준. Trinity N1B0 4x5 variant HDD |
| `test_rtl/Sample/N1B0_NPU_HDD_v0.1.md` | 보조 비교 기준. NPU 관점 확장 HDD |

### v4 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v4/v4a_chip_no_grounding.md` | 칩 전체 HDD, no grounding |
| `test_rtl/rag_result/v4/v4b_chip_grounded.md` | 칩 전체 HDD, grounded |
| `test_rtl/rag_result/v4/v4_edc.md` | EDC 서브시스템 HDD |
| `test_rtl/rag_result/v4/v4_noc.md` | NoC 서브시스템 HDD |
| `test_rtl/rag_result/v4/v4_overlay.md` | Overlay 서브시스템 HDD |

### v5 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v5/v5_chip_no_grounding.md` | 칩 전체 HDD, no grounding |
| `test_rtl/rag_result/v5/v5_chip_grounded.md` | 칩 전체 HDD, grounded |
| `test_rtl/rag_result/v5/v5_edc.md` | EDC 서브시스템 HDD |
| `test_rtl/rag_result/v5/v5_noc.md` | NoC 서브시스템 HDD |
| `test_rtl/rag_result/v5/v5_overlay.md` | Overlay 서브시스템 HDD |
| `test_rtl/codex_review_v5.md` | v4.1 → v5 기존 Codex 리뷰 |

### v5.1 산출물

| 파일 | 역할 |
|---|---|
| `test_rtl/rag_result/v5.1/v5.1_chip_no_grounding.md` | 칩 전체 HDD, no grounding |
| `test_rtl/rag_result/v5.1/v5.1_chip_grounded.md` | 칩 전체 HDD, grounded |
| `test_rtl/rag_result/v5.1/v5.1_edc.md` | EDC 서브시스템 HDD |
| `test_rtl/rag_result/v5.1/v5.1_noc.md` | NoC 서브시스템 HDD |
| `test_rtl/rag_result/v5.1/v5.1_overlay.md` | Overlay 서브시스템 HDD |

---

## 2. 정량 비교

### 2.1 Chip 문서

| 문서 | Lines | Bytes | Headings | Table rows | Code fences | `[NOT IN KB]` | 해석 |
|---|---:|---:|---:|---:|---:|---:|---|
| 정답지 `N1B0_HDD_v0.1` | 513 | 22330 | 40 | 186 | 24 | 0 | 기준 |
| 정답지 `N1B0_NPU_HDD_v0.1` | 1290 | 58380 | 105 | 303 | 52 | 0 | 확장 기준 |
| v4 `chip_no_grounding` | 399 | 17988 | 46 | 128 | 2 | 31 | 보수적 skeleton, 일부 정확 |
| v4 `chip_grounded` | 217 | 6477 | 35 | 26 | 0 | 29 | 좁고 빈칸 많음 |
| v5 `chip_no_grounding` | 123 | 7287 | 5 | 33 | 4 | 0 | 4섹션에서 종료 |
| v5 `chip_grounded` | 216 | 6953 | 32 | 8 | 2 | 16 | 구조는 있으나 내용 부족 |
| v5.1 `chip_no_grounding` | 494 | 21289 | 48 | 142 | 10 | 0 | 분량/목차는 회복, factual risk 큼 |
| v5.1 `chip_grounded` | 295 | 10009 | 33 | 82 | 2 | 13 | v5 대비 개선, 핵심 빈칸 잔존 |

해석:

- v5.1 `chip_no_grounding`은 정답지 `N1B0_HDD_v0.1`과 줄 수가 거의 비슷해졌다.
- v5에서 4섹션으로 끊겼던 문제가 v5.1에서는 14개 본문 섹션 + appendix로 회복됐다.
- 하지만 `no_grounding`은 `[NOT IN KB]`가 없어서 보기에는 완성 문서처럼 보이지만, 실제로는 정답지와 다른 grid/port/hierarchy가 섞인다.
- v5.1 `chip_grounded`는 v5보다 table rows가 늘고 coverage matrix도 생겼지만, package/top ports/file reference는 여전히 `[NOT IN KB]`다.

### 2.2 Subsystem 문서

| 문서 | v4 lines | v5 lines | v5.1 lines | v5.1 판정 |
|---|---:|---:|---:|---|
| EDC | 441 | 262 | 109 | 더 짧고 안전하지만 HDD로는 빈약 |
| NoC | 415 | 234 | 100 | key module list 중심, architecture 부족 |
| Overlay | 479 | 273 | 100 | FDS/CSR register block 중심, CPU/iDMA/ROCC 등 부족 |

해석:

- v5.1의 subsystem 문서는 KB-only 정책을 더 강하게 적용하면서 매우 짧아졌다.
- EDC/NoC/Overlay 각각 실제 모듈명은 남겼지만, 정답지나 실사용 HDD에 필요한 protocol, topology, register map, verification detail은 대부분 `[NOT IN KB]`가 됐다.
- v5.1 subsystem 문서는 "정확한 스켈레톤"으로는 유용하지만 "완성 HDD"로는 부족하다.

---

## 3. v5.1 vs 정답지 비교

### 3.1 Overview

정답지의 핵심:

- N1B0은 baseline Trinity 변형이다.
- 핵심 변화는 `trinity_noc2axi_n_opt + trinity_router` 분리 구조를 `trinity_noc2axi_router_ne/nw_opt` 통합 HPDF tile로 바꾼 것이다.
- 해당 통합 module은 Y=4 NOC2AXI와 Y=3 Router 기능을 함께 담당한다.

v5.1:

- AI accelerator SoC, 2D mesh NoC, Tensix compute tile 등 일반 설명은 있다.
- 하지만 HPDF 통합 tile이 N1B0의 핵심 변화라는 점이 거의 드러나지 않는다.
- `chip_no_grounding`은 ARC/DRAM/ETH/PCI tile을 포함한 일반 SoC grid로 설명해 정답지와 방향이 어긋난다.

판정: **부분 충족. 상위 설명은 있으나 N1B0-specific 핵심 변화가 약하다.**

### 3.2 Package Constants and Grid

정답지:

| Constant | Value |
|---|---:|
| `SizeX` | 4 |
| `SizeY` | 5 |
| `NumNodes` | 20 |
| `NumTensix` | 12 |
| `NumNoc2Axi` | 4 |
| `NumDispatch` | 2 |
| `NumApbNodes` | 4 |
| `NumDmComplexes` | 14 |

정답지의 tile map:

```text
Y=4   NOC2AXI_NE_OPT        NOC2AXI_ROUTER_NE_OPT    NOC2AXI_ROUTER_NW_OPT    NOC2AXI_NW_OPT
Y=3   DISPATCH_E             ROUTER (placeholder)     ROUTER (placeholder)     DISPATCH_W
Y=2   TENSIX                 TENSIX                   TENSIX                   TENSIX
Y=1   TENSIX                 TENSIX                   TENSIX                   TENSIX
Y=0   TENSIX                 TENSIX                   TENSIX                   TENSIX
```

v5.1 `chip_no_grounding`:

| Parameter | v5.1 value | 정답지 판정 |
|---|---:|---|
| `GridSizeX` | 5 | 오답. 정답지는 `SizeX=4` |
| `GridSizeY` | 4 | 오답. 정답지는 `SizeY=5` |
| `NumTensix` | 12 | 맞음 |
| `NumDRAM` | 2 | 정답지의 package constant가 아님 |
| `NumETH` | 2 | 정답지의 package constant가 아님 |
| `NumPCI` | 1 | 정답지의 package constant가 아님 |
| `NumARC` | 1 | 정답지의 package constant가 아님 |
| `NumRouter` | 2 | placeholder router 개념과 혼재 |

v5.1 `chip_grounded`:

- package constants는 `[NOT IN KB]`로 처리했다.
- 안전하지만 정답지 핵심 섹션은 재현하지 못했다.

판정: **v5.1의 가장 큰 실패 지점.**

### 3.3 Tile Enumeration and Endpoint Index

정답지:

- `tile_t` 3-bit enum 8종을 명시한다.
- `NOC2AXI_ROUTER_NE_OPT`, `NOC2AXI_ROUTER_NW_OPT`가 Y=4 + Y=3 dual-row tile로 동작한다.
- `ROUTER` enum은 placeholder이며 `gen_router` generate block은 empty다.
- `EndpointIndex = x * SizeY + y = x*5 + y` 전체 20개 mapping이 있다.

v5.1:

- `tile_t` enum이 없다.
- endpoint index table이 없다.
- placeholder `ROUTER`와 combined NOC2AXI-router 구조가 명확히 재현되지 않는다.
- `chip_grounded`는 `trinity_router is NOT instantiated`를 적었지만, package/grid와 endpoint mapping은 `[NOT IN KB]`다.

판정: **핵심 구조 미충족.**

### 3.4 Top-Level Ports

정답지 주요 port:

| Group | Examples |
|---|---|
| Clock/reset | `i_axi_clk`, `i_noc_clk`, `i_noc_reset_n`, `i_ai_clk[SizeX-1:0]`, `i_dm_clk[SizeX-1:0]`, `i_tensix_reset_n[NumTensix-1:0]`, `i_edc_reset_n` |
| APB | `i_reg_*[NumApbNodes]`, `o_reg_*[NumApbNodes]` |
| EDC APB + IRQ | `i_edc_apb_*[4]`, `o_edc_*_irq[4]` |
| AXI | `npu_out_*[SizeX]`, `npu_in_*[SizeX]` |
| PRTN | `PRTNUN_FC2UN_*`, `PRTNUN_UN2FC_*` |
| Isolation/DFT | `ISO_EN[11:0]`, `TIEL_DFT_MODESCAN` |

v5.1 `chip_no_grounding`:

- generic `ai_clk`, `noc_clk`, `dm_clk`, `ref_clk`, `reset_n`를 사용한다.
- PCI/ETH differential ports를 넣는다.
- 정답지의 `i_*` naming, per-column vector, APB arrays, AXI in/out, PRTN chain, `ISO_EN[11:0]`가 부족하다.
- EDC interface는 `tt_edc_pkg.sv` modport 기반으로 일부 잘 잡았지만 top-level `trinity` port 구조와는 다르다.

v5.1 `chip_grounded`:

- top-level ports는 `[NOT IN KB]`다.

판정: **정답지 대비 큰 갭.**

### 3.5 Module Hierarchy

정답지:

```text
trinity
├── [X=0,Y=4] trinity_noc2axi_ne_opt
├── [X=1,Y=4+3] trinity_noc2axi_router_ne_opt
│   ├── trinity_noc2axi_n_opt logic
│   └── trinity_router logic
├── [X=2,Y=4+3] trinity_noc2axi_router_nw_opt
│   ├── trinity_noc2axi_n_opt logic
│   └── trinity_router logic
├── [X=3,Y=4] trinity_noc2axi_nw_opt
├── [X=0,Y=3] tt_dispatch_top_east
├── [X=3,Y=3] tt_dispatch_top_west
└── [X=0..3,Y=0..2] tt_tensix_with_l1
```

v5.1:

- SFPU, TDMA, NoC, NIU, SMN, EDC, clock 등 실제 module name을 넓게 가져온 것은 좋다.
- 하지만 정답지의 generate block 위치, endpoint index, Y=4/Y=3 dual-row relation을 재현하지 못한다.
- `tensix_tile`, `tt_niu_top`, `tt_smn_top`, `tt_clock_top` 같은 wrapper 이름은 정답지와 직접 맞지 않는다.

판정: **모듈명 풍부함은 개선, 정답지 hierarchy 정확도는 부족.**

### 3.6 NoC

정답지:

- Y-axis and X-axis fabric connections를 설명한다.
- Y=3 Router row와 Y=4 NOC2AXI row 사이의 repeater count와 direction을 구분한다.
- `noc_east2west_req_repeaters_between_noc2axi`, `noc_west2east_req_repeaters_between_router` 같은 구체 naming과 count가 있다.

v5.1:

- `tt_noc_repeaters_cardinal`, `tt_noc_sync3_pulse`, `tt_noc_async_fifo_wr_side_reset`, `tt_noc_secded_chk_corr_116_10`, `tt_upf_async_fifo` 등 실제 module은 일부 잘 잡았다.
- 하지만 routing algorithm, endpoint map, inter-column repeater placement는 grounded 문서에서 대부분 `[NOT IN KB]`다.
- no-grounding에서는 DOR/Tendril/Dynamic, flit types, VC 등을 채웠지만 정답지의 row-specific repeater topology와 직접 연결되지 않는다.

판정: **실제 module fact는 좋아졌지만 정답지의 topology 재현은 부족.**

### 3.7 Clock and Reset

정답지:

- `i_ai_clk[SizeX-1:0]`, `i_dm_clk[SizeX-1:0]` per-column 구조가 중요하다.
- `trinity_clock_routing_t`, `clock_routing_out[x][y]`, combined router tile의 clock/reset propagation이 핵심이다.
- `i_tensix_reset_n[11:0]`, DM core/uncore reset 구조가 있다.

v5.1:

- `tt_clkdiv2`, `tt_clkbuf`, `tt_clkgater`, `tt_clk_gater`, `tt_smn_clkdiv` 등 cell/module fact는 잡았다.
- 하지만 정답지의 column-based clock routing and reset routing은 재현하지 못한다.
- generic reset chain과 power partition table은 정답지 기반이라기보다 LLM 보강에 가깝다.

판정: **clock cell 검색은 개선, N1B0 clock/reset architecture 재현은 부족.**

### 3.8 EDC

정답지:

- EDC ring, APB interface, IRQ, serial bus, harvest bypass, node connectivity가 필요하다.
- `tt_edc_pkg.sv` interface와 `ingress/egress/edc_node/sram` modport도 중요하다.

v5.1:

- `tt_edc_pkg.sv` modport 4개를 잘 잡았다.
- `tt_edc1_serial_bus_repeater`, `tt_edc1_biu_soc_apb4_wrap`, `tt_edc1_noc_sec_block_reg`, `tt_edc1_intf_connector` 등 실제 module도 잡았다.
- `fatal_err_irq`, `crit_err_irq`, `cor_err_irq`, `pkt_sent_irq`, `pkt_rcvd_irq` 같은 IRQ fact도 의미 있다.
- 하지만 grounded EDC 문서에서는 toggle handshake, packet format, node ID, ring topology, harvest bypass, CDC가 대부분 `[NOT IN KB]`다.

판정: **v5.1의 강점 영역. 단, 완성 HDD로는 아직 부족.**

### 3.9 PRTN, ISO, Memory Config

정답지:

- PRTN daisy chain은 N1B0 addition으로 명시된다.
- `ISO_EN[11:0]`는 power isolation control로 중요하다.
- memory config SFR ports도 별도 섹션이다.

v5.1:

- PRTN chain이 사실상 빠졌다.
- `ISO_EN[11:0]`도 재현되지 않는다.
- SRAM inventory는 `tt_mem_wrap_32x1024_2p_nomask` 중심이고, 정답지의 memory config SFR와는 성격이 다르다.

판정: **정답지 핵심 기능 누락.**

### 3.10 RTL File Reference

정답지:

- `used_in_n1/rtl/targets/4x5/trinity_pkg.sv`
- `used_in_n1/rtl/trinity.sv`
- `trinity_noc2axi_router_ne/nw_opt`
- `tt_dispatch_top_east/west`
- `tt_tensix_with_l1`
- EDC/NoC/clock/package related files

v5.1:

- EDC package file paths는 KB-confirmed로 일부 잡았다.
- 나머지는 inferred path가 많다.
- `chip_grounded`는 file paths를 `[NOT IN KB]`로 표시한다.

판정: **일부 개선, 전체 file map은 부족.**

---

## 4. v4 → v5 → v5.1 변화 분석

### 4.1 전체 흐름

| 축 | v4 | v5 | v5.1 |
|---|---|---|---|
| 전체 HDD 완성도 | 넓은 skeleton, 빈칸 많음 | 크게 후퇴. `no_grounding` 4섹션에서 종료 | `no_grounding`은 분량/목차 회복 |
| 정답지 핵심 grid | `4x5`, `SizeX=4`, `SizeY=5` 방향을 비교적 잘 잡음 | `5x4 + ARC/DRAM/ETH/PCI`로 오염 | 같은 오염 유지 |
| 실제 RTL 모듈명 | 제한적 | claim boost로 크게 개선 | 개선 유지. SFPU/TDMA/NoC/EDC/Clock module fact 증가 |
| Grounding 투명성 | `[NOT IN KB]` 많고 보수적 | 더 엄격하지만 커버리지 낮음 | coverage matrix 기준 59%까지 회복 |
| Subsystem 문서 | 가장 길고 풍부 | 절반 수준으로 축소 | 더 짧아짐. 정확하지만 너무 빈약 |
| Hallucination 위험 | 낮음~중간 | no-grounding에서 증가 | no-grounding은 높음, grounded는 낮음 |

### 4.2 v4의 성격

v4는 보수적인 문서였다. `v4a_chip_no_grounding.md`는 이름과 달리 "Only information present in search results" 원칙을 강하게 내세우고 `[NOT IN KB]`를 많이 표시한다.

장점:

- `SizeX=4`, `SizeY=5`, 4x5 grid, `NumTensix=12` 방향을 정답지와 가깝게 잡았다.
- `i_ai_clk[SizeX-1:0]`, `i_tensix_reset_n[NumTensix-1:0]` 등 top port의 실제 naming을 일부 포착했다.
- `trinity_router`가 empty라는 점을 유지했다.
- follow-up search suggestion이 유용했다.

단점:

- 문서 곳곳이 `[NOT IN KB]`라 완성 HDD로는 부족했다.
- FPU/SFPU/TDMA/NoC/EDC/Overlay 내부 module detail은 제한적이었다.
- 정답지의 endpoint table, tile enum, full top port, NOC repeater count 등은 재현하지 못했다.

v4는 "정답지 좌표계는 비교적 맞지만 내용이 빈약한 버전"에 가깝다.

### 4.3 v5의 성격

v5는 claim boost와 analysis_type pass-through의 효과가 드러난 실험 버전이다.

장점:

- `tt_sfpu_lregs`, `tt_sfpu_instrn_resources_used`, `tt_noc_secded_chk_corr_116_10`, `tt_upf_async_fifo`, `tt_noc_sync3_pulse`, `tt_niu_mst_timeout` 등 실제 RTL module name을 많이 드러냈다.
- subsystem topic 검색에서는 관련 claim을 더 잘 가져왔다.
- grounding 정책이 엄격해져 검증 불가능한 내용은 `[NOT IN KB]`로 빠지는 경향이 생겼다.

단점:

- `chip_no_grounding`이 4섹션에서 끝나 HDD로서 미완성이었다.
- `chip_grounded`는 `hdd_section` 필터에 갇혀 FPU/SFPU/SMN 중심으로 좁아졌다.
- `module_parse` 가중치가 낮아지면서 `tt_edc_pkg.sv`, top-level port, package/grid 같은 핵심 구조 데이터가 빠졌다.
- grid가 `5x4 + ARC/DRAM/ETH/PCI`로 오염되기 시작했다.

v5는 "module fact는 좋아졌지만 HDD 완성도와 정답지 좌표계가 무너진 버전"이다.

### 4.4 v5.1의 성격

v5.1은 v5의 미완성 문제를 일부 회복했다.

개선:

- `chip_no_grounding`이 494 lines로 늘어 정답지와 유사한 규모가 됐다.
- Compute, Dispatch, NoC, NIU, Clock, Reset, EDC, SRAM, DFX, RTL File Reference 등 HDD 목차가 복원됐다.
- `chip_grounded`도 v5 대비 table rows와 confirmed modules가 늘었다.
- coverage matrix에 따르면 v5 → v5.1 grounded coverage가 18% → 59%로 개선됐다고 자체 보고한다.
- `claim + hdd_section + module_parse`가 섞인 형태의 검색 결과가 다시 활용된 흔적이 있다.

퇴보 또는 잔존 문제:

- v5에서 생긴 `5x4 + ARC/DRAM/ETH/PCI` grid drift가 v5.1에서도 유지됐다.
- no-grounding 문서는 정답지에 없는 내용을 자연스럽게 채워 넣어 hallucination risk가 커졌다.
- grounded 문서는 안전하지만 package constants, top ports, reset, file reference 등 핵심이 여전히 `[NOT IN KB]`다.
- subsystem 문서는 v5보다 더 짧아져 실사용 HDD 가치가 낮아졌다.

v5.1은 "형태와 retrieval 폭은 회복했지만, 정답지 anchor가 약한 버전"이다.

---

## 5. v5.1 파일별 판정

### 5.1 `v5.1_chip_no_grounding.md`

좋은 점:

- 정답지와 비슷한 규모와 목차를 갖췄다.
- SFPU, TDMA, NoC, NIU, EDC, Clock, DFX 등 섹션을 모두 포함한다.
- 실제 module name이 많다.
- `tt_edc_pkg.sv` modport와 EDC module fact가 좋다.

문제:

- `GridSizeX=5`, `GridSizeY=4`는 정답지 기준 오답이다.
- ARC/DRAM/ETH/PCI tile layout은 `N1B0_HDD_v0.1`의 package/grid와 맞지 않는다.
- top-level ports가 generic SoC style로 생성됐다.
- PRTN, `ISO_EN[11:0]`, APB×4, NPU AXI in/out, endpoint table이 부족하다.
- `[NOT IN KB]`가 없어 완성도는 높아 보이나 검증 경계가 흐리다.

판정: **문서 형태는 v5 대비 대폭 개선. 정답지 factuality는 위험.**

### 5.2 `v5.1_chip_grounded.md`

좋은 점:

- KB-only rule이 명확하다.
- confirmed functional blocks 목록이 유용하다.
- SFPU, SMN, TDMA, NoC, EDC, Overlay, Clock, SRAM, DFX를 한 문서에서 넓게 다룬다.
- coverage matrix가 있어 현재 KB gap을 추적하기 쉽다.

문제:

- package constants와 top-level ports가 `[NOT IN KB]`라 정답지 핵심을 못 채운다.
- NoC routing/flit/VC, EDC topology/bypass, overlay CPU/L1/APB, reset, RTL files가 비어 있다.
- `Coverage 59%`는 항목 수 기준 자체 지표라, 정답지의 핵심 가중치 기준으로는 과대평가될 수 있다.

판정: **v5 대비 명확히 개선. 그러나 정답지 재현으로는 아직 부족.**

### 5.3 `v5.1_edc.md`

좋은 점:

- `tt_edc1_biu_soc_apb4_wrap`, `edc1_biu_soc_apb4_inner`, `tt_edc1_noc_sec_block_reg`, `tt_edc1_serial_bus_repeater`, `tt_edc1_intf_connector`를 잡았다.
- APB4 slave signal과 5개 IRQ를 포착했다.
- KB-only로 안전하다.

문제:

- toggle handshake, packet format, node ID, ring topology, harvest bypass, CDC, instance paths가 대부분 `[NOT IN KB]`다.
- 정답지나 EDC sample HDD에 필요한 동작 설명이 부족하다.

판정: **정확한 module skeleton. 완성 HDD는 아님.**

### 5.4 `v5.1_noc.md`

좋은 점:

- `tt_noc_repeaters_cardinal`, `noc_arbiter_tree`, `tt_skid_buffer_new_assertion_off`, `tt_noc_secded_chk_corr_116_10`, `tt_upf_async_fifo`, `tt_noc_sync3_pulse` 등 실제 module fact가 좋다.
- `DATA_WIDTH=116`, `ECC_WIDTH=10`, `TABLE_DEPTH=1024`, `TABLE_WIDTH=32` 등 key parameters 일부를 잡았다.

문제:

- routing algorithm, flit header fields, VC buffers, security fence, endpoint map, Y=3/Y=4 repeater placement가 없다.
- 정답지의 NoC fabric connection 구조와 직접 연결되지 않는다.

판정: **module fact는 개선, architecture는 부족.**

### 5.5 `v5.1_overlay.md`

좋은 점:

- `tt_fds_tensixneo_reg`, `tt_fds_dispatch_reg`, `tt_cluster_ctrl_t6_l1_csr_reg`와 port count를 잡았다.
- FDS register block 쪽은 실제 RTL fact로 유용하다.

문제:

- CPU cluster, L1 cache internals, iDMA, ROCC, LLK, SMN, APB map, parameters, clock, RTL file index가 대부분 `[NOT IN KB]`다.
- 정답지 `N1B0_HDD_v0.1`의 핵심 범위와는 다소 멀다.

판정: **FDS/CSR fact sheet에 가깝다. Overlay HDD로는 부족.**

---

## 6. 원인 분석

### 6.1 Retrieval은 좋아졌지만 anchor가 약하다

v5.1은 v5보다 검색 결과 폭이 넓다. `chip_no_grounding` appendix에 따르면 20 results 중 `4 HDD sections + 8 claims + 8 module_parse`를 사용했다.

문제는 retrieval 결과를 정답지 구조에 고정하는 anchor가 약하다는 점이다. 결과적으로 실제 module fact와 일반 SoC 지식이 섞이면서 `GridSizeX=5`, `GridSizeY=4`, ARC/DRAM/ETH/PCI tile 같은 drift가 생겼다.

### 6.2 Package/grid/top-port query가 여전히 약하다

정답지 재현의 핵심은 다음이다.

- `trinity_pkg.sv`
- `tile_t`
- `GridConfig`
- `EndpointIndex`
- `trinity.sv` top-level ports
- `PRTN`
- `ISO_EN`
- `NOC2AXI_ROUTER_NE/NW_OPT`

v5.1 grounded에서는 이 핵심들이 대부분 `[NOT IN KB]`다. 이는 claim/HDD section 검색은 좋아졌지만, package and top module parse retrieval이 아직 충분하지 않다는 뜻이다.

### 6.3 No-grounding이 빈칸을 너무 적극적으로 채운다

v5.1 `chip_no_grounding`은 문서로 읽기에는 좋다. 그러나 정답지와 비교하면 no-grounding이 generic accelerator/SoC knowledge로 빈칸을 채우면서 오답을 만든다.

정답지 비교 평가에서는 "완성도 높은 오답"이 "빈칸 많은 정직한 답"보다 더 위험할 수 있다.

### 6.4 Subsystem KB-only 문서는 너무 얇다

EDC/NoC/Overlay v5.1은 안전하지만 문서 가치가 떨어진다. claim 단위 fact만으로는 HDD에 필요한 topology, protocol, register map, timing, verification section을 만들 수 없다.

이 문제는 RAG 검색만이 아니라 source ingestion 범위 문제이기도 하다. RTL claim만으로는 "무엇이 있다"는 정보는 얻지만, "어떻게 동작한다"는 구조 설명을 만들기 어렵다.

---

## 7. 개선 권장사항

### 7.1 즉시 적용

| 우선순위 | 개선 | 기대 효과 |
|---|---|---|
| P0 | chip HDD 생성 전에 `trinity_pkg.sv`, `trinity.sv`, `tile_t`, `GridConfig`, `EndpointIndex`를 별도 검색하고 seed context로 고정 | `5x4` drift 방지, 정답지 grid 복원 |
| P0 | `GridSizeX=5`, `GridSizeY=4`, ARC/DRAM/ETH/PCI tile을 N1B0 Trinity HDD에서는 금지 또는 검증 실패 처리 | 가장 큰 factual error 차단 |
| P0 | `SizeX=4`, `SizeY=5`, `NumTensix=12`, `NumNoc2Axi=4`, `NumDispatch=2`, `NumApbNodes=4`를 required facts로 설정 | package constants 재현 |
| P0 | `PRTN`, `ISO_EN`, `i_ai_clk[SizeX-1:0]`, `i_dm_clk[SizeX-1:0]`, `i_tensix_reset_n[11:0]`, `i_edc_apb_*[4]` 전용 query 추가 | top-level port gap 축소 |
| P1 | chip grounded 검색에서 `hdd_section` 단독 필터 금지. `claim + module_parse + hdd_section` 혼합 유지 | v5의 18% coverage 문제 재발 방지 |

### 7.2 중기 개선

| 우선순위 | 개선 | 기대 효과 |
|---|---|---|
| P1 | `module_parse` 가중치를 낮추지 말고 package/top-module query에서는 최우선으로 사용 | 구조 정보 복원 |
| P1 | no-grounding 출력에도 `[INFERRED]`, `[FROM KB]`, `[FROM PRIOR SPEC]` 태그를 붙이기 | 완성도와 추적성 균형 |
| P1 | 정답지 섹션별 required facts checklist를 prompt에 넣기 | 빠진 섹션 자동 감지 |
| P2 | EDC/NoC/Overlay는 claim 검색 후 관련 source snippets/module_parse를 follow-up으로 재검색 | subsystem 문서 두께 회복 |

### 7.3 장기 방향

| 우선순위 | 개선 | 기대 효과 |
|---|---|---|
| P2 | RTL RAG와 Spec/Sample HDD RAG를 분리 구축 후 cross retrieval | "what"과 "how" 모두 확보 |
| P2 | 정답지 기반 evaluator 생성: grid/ports/hierarchy facts를 자동 채점 | regression 방지 |
| P3 | package parser에 enum, localparam, packed struct, generate block extraction 강화 | `tile_t`, `GridConfig`, endpoint 자동화 |

---

## 8. 최종 판정

| 평가 항목 | v5.1 판정 |
|---|---|
| v5 대비 개선 여부 | 개선 |
| 정답지 대비 package/grid 정확도 | 낮음 |
| 정답지 대비 top-level port 정확도 | 낮음 |
| 실제 RTL module name 포착 | 좋음 |
| EDC package/module fact | 좋음 |
| NoC module fact | 중간 이상 |
| HDD 문서 완성도 | no-grounding은 높음, grounded/subsystem은 낮음 |
| hallucination risk | no-grounding 높음, grounded 낮음 |
| 실사용 가능성 | 초안으로는 유용, 정답지 대체는 불가 |

최종적으로 v5.1은 다음 방향으로 해석하는 것이 적절하다.

- **v4:** 정답지 좌표계는 비교적 맞지만 빈칸이 많은 버전
- **v5:** module fact는 좋아졌지만 문서 완성도와 좌표계가 무너진 버전
- **v5.1:** 문서 형태와 retrieval 폭은 회복했지만, 정답지 anchor가 약해 factual drift가 남은 버전

가장 좋은 다음 단계는 v4의 `SizeX=4/SizeY=5` package/grid/top-port skeleton을 고정 anchor로 삼고, v5.1의 claim 기반 module facts를 그 위에 합치는 것이다.

---

*End of Review — Codex Review v5.1*
