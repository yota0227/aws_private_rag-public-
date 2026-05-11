# N1B0 NPU — Full Hardware Design Document

> **Pipeline ID:** tt_20260221
> **Version:** v7
> **RAG:** v4.1 + Package Parser v2 + Port Classifier + MCP 800char
> **Method:** 5-round topic search → per-topic files → merge
> **Sources:** v7_chip_no_grounding, v7_chip_grounded, v7_edc, v7_noc, v7_overlay
> **Generated:** 2026-05-01

---

## 1. Overview

N1B0 is the Trinity NPU integrated into the N1 SoC. Top module `trinity` implements a **4×5 tile mesh** (SizeX=4, SizeY=5, 20 tiles).

| Tile Type | Count | RTL Module | Position |
|-----------|-------|------------|----------|
| TENSIX | 12 | `tt_tensix_with_l1` | Y=0..2, X=0..3 |
| NOC2AXI_NE_OPT | 1 | `trinity_noc2axi_ne_opt` | (X=0, Y=4) |
| NOC2AXI_ROUTER_NE_OPT | 1 | `trinity_noc2axi_router_ne_opt` | (X=1, Y=4+3) |
| NOC2AXI_ROUTER_NW_OPT | 1 | `trinity_noc2axi_router_nw_opt` | (X=2, Y=4+3) |
| NOC2AXI_NW_OPT | 1 | `trinity_noc2axi_nw_opt` | (X=3, Y=4) |
| DISPATCH_E | 1 | `tt_dispatch_top_east` | (X=0, Y=3) |
| DISPATCH_W | 1 | `tt_dispatch_top_west` | (X=3, Y=3) |
| ROUTER | 2 | (empty) | (X=1,2, Y=3) |

EnableDynamicRouting=1, DMCoresPerCluster=8, ROUTER placeholder empty by design.

---

## 2. Package Constants and Grid

**File:** `used_in_n1/rtl/targets/4x5/trinity_pkg.sv` *(from v7_chip_no_grounding)*

### 2.1 Constants (13 localparams)

| Constant | Value |
|----------|-------|
| SizeX | 4 |
| SizeY | 5 |
| NumNodes | 20 |
| NumTensix | 12 |
| NumNoc2Axi | 4 |
| NumDispatch | 2 |
| NumApbNodes | 4 |
| NumDmComplexes | 14 |
| DMCoresPerCluster | 8 |
| TensixPerCluster | 4 |
| EnableDynamicRouting | 1'b1 |
| NumAxes | 2 |
| NumDirections | 2 |

### 2.2 tile_t enum (3-bit, 8 members)

| Value | Name | Position |
|-------|------|----------|
| 3'd0 | TENSIX | Y=0..2, X=0..3 |
| 3'd1 | NOC2AXI_NE_OPT | (X=0, Y=4) |
| 3'd2 | NOC2AXI_ROUTER_NE_OPT | (X=1, Y=4+3) |
| 3'd3 | NOC2AXI_ROUTER_NW_OPT | (X=2, Y=4+3) |
| 3'd4 | NOC2AXI_NW_OPT | (X=3, Y=4) |
| 3'd5 | DISPATCH_E | (X=0, Y=3) |
| 3'd6 | DISPATCH_W | (X=3, Y=3) |
| 3'd7 | ROUTER | (X=1,2, Y=3) — empty |

### 2.3 Endpoint Index (EP = x*5+y)

| X | Y | Tile | EP |
|---|---|------|----|
| 0 | 0 | TENSIX | 0 |
| 0 | 1 | TENSIX | 1 |
| 0 | 2 | TENSIX | 2 |
| 0 | 3 | DISPATCH_E | 3 |
| 0 | 4 | NOC2AXI_NE_OPT | 4 |
| 1 | 0 | TENSIX | 5 |
| 1 | 1 | TENSIX | 6 |
| 1 | 2 | TENSIX | 7 |
| 1 | 3 | ROUTER | 8 |
| 1 | 4 | NOC2AXI_ROUTER_NE_OPT | 9 |
| 2 | 0 | TENSIX | 10 |
| 2 | 1 | TENSIX | 11 |
| 2 | 2 | TENSIX | 12 |
| 2 | 3 | ROUTER | 13 |
| 2 | 4 | NOC2AXI_ROUTER_NW_OPT | 14 |
| 3 | 0 | TENSIX | 15 |
| 3 | 1 | TENSIX | 16 |
| 3 | 2 | TENSIX | 17 |
| 3 | 3 | DISPATCH_W | 18 |
| 3 | 4 | NOC2AXI_NW_OPT | 19 |

### 2.4 NoC Enums

noc_axis_t: Y_AXIS=1'b0, X_AXIS=1'b1 | noc_direction_t: POSITIVE=1'b0, NEGATIVE=1'b1

### 2.5 Grid

```
         X=0              X=1                   X=2                  X=3
Y=4:    │ NIU_NE EP=4 │ NIU_ROUTER_NE EP=9   NIU_ROUTER_NW EP=14│ NIU_NW EP=19│
Y=3:    │ DISP_E EP=3 │ [ROUTER EP=8]        [ROUTER EP=13]      │ DISP_W EP=18│
Y=2:    │ T6[0][2]    │ T6[1][2]             T6[2][2]             │ T6[3][2]    │
Y=1:    │ T6[0][1]    │ T6[1][1]             T6[2][1]             │ T6[3][1]    │
Y=0:    │ T6[0][0]    │ T6[1][0]             T6[2][0]             │ T6[3][0]    │
```

---

## 3. Top-Level Ports

*(from v7_chip_no_grounding — 800char expanded, Port Classifier applied)*

### 3.1 Clock & Reset Ports

| Port | Width | Direction | Description |
|------|-------|-----------|-------------|
| i_axi_clk | 1 | input | AXI clock |
| i_noc_clk | 1 | input | NoC clock |
| i_noc_reset_n | 1 | input | NoC reset (active-low) |
| i_ai_clk[SizeX-1:0] | 4 | input | AI clock per column |
| i_ai_reset_n[SizeX-1:0] | 4 | input | AI reset per column (active-low) |
| i_tensix_reset_n[NumTensix-1:0] | 12 | input | Per-Tensix reset (active-low) |
| i_edc_reset_n | 1 | input | EDC reset (active-low) |
| i_dm_clk[SizeX-1:0] | 4 | input | DM clock per column *(v7 new)* |
| i_dm_core_reset_n[NumDmComplexes-1:0][DMCoresPerCluster-1:0] | 14×8 | input | Per-DM-core reset (active-low) *(v7 new)* |
| i_dm_uncore_reset_n[NumDmComplexes-1:0] | 14 | input | Per-DM-complex uncore reset (active-low) *(v7 new)* |

### 3.2 APB Register Ports *(v7 new)*

| Port | Width | Direction | Description |
|------|-------|-----------|-------------|
| i_reg_psel | 1 | input | APB select |
| i_reg_paddr[31:0] | 32 | input | APB address |
| i_reg_penable | 1 | input | APB enable |
| i_reg_pwrite | 1 | input | APB write |
| i_reg_pwdata[31:0] | 32 | input | APB write data |
| o_reg_pready | 1 | output | APB ready |
| o_reg_prdata[31:0] | 32 | output | APB read data |
| o_reg_pslverr | 1 | output | APB slave error |

### 3.3 EDC APB Ports *(v7 new — full signal list)*

| Port | Width | Direction | Description |
|------|-------|-----------|-------------|
| i_edc_apb_psel | 1 | input | EDC APB select |
| i_edc_apb_penable | 1 | input | EDC APB enable |
| i_edc_apb_pwrite | 1 | input | EDC APB write |
| i_edc_apb_pprot[2:0] | 3 | input | EDC APB protection |
| i_edc_apb_paddr[5:0] | 6 | input | EDC APB address |
| i_edc_apb_pwdata[31:0] | 32 | input | EDC APB write data |
| i_edc_apb_pstrb[3:0] | 4 | input | EDC APB write strobe |
| o_edc_apb_pready | 1 | output | EDC APB ready |
| o_edc_apb_prdata[31:0] | 32 | output | EDC APB read data |

### 3.4 Port Classifier Claims *(v7 new)*

| Claim Category | Count | Ports |
|----------------|-------|-------|
| AI_Clock_Reset | 2 | i_ai_clk, i_ai_reset_n |
| Tensix_Reset | 1 | i_tensix_reset_n |
| DM_Clock_Reset | 3 | i_dm_clk, i_dm_core_reset_n, i_dm_uncore_reset_n |

---

## 4. Module Hierarchy

*(merged from all 5 v7 sources)*

```
trinity (top)
├── tt_tensix_with_l1 [×12] — Y=0..2
│   ├── tt_sfpu_lregs (from overlay)
│   ├── tt_sfpu_instrn_resources_used (from overlay)
│   ├── tt_tdma_xy_address_controller (from overlay, v7 new)
│   ├── tt_tdma_thread_context (from overlay)
│   ├── tt_tdma_rts_rtr_pipe_stage (from overlay, v7 new)
│   └── RF_2P_HSC_LVT_32X136M1FB1WM0DR0 (SRAM macro, v7 new)
├── tt_dispatch_top_east EP=3 (from chip)
├── tt_dispatch_top_west EP=18 (from chip)
├── trinity_noc2axi_ne_opt EP=4 (from chip)
├── trinity_noc2axi_router_ne_opt EP=9/8 (from chip)
├── trinity_noc2axi_router_nw_opt EP=14/13 (from chip)
├── trinity_noc2axi_nw_opt EP=19 (from chip)
├── ROUTER placeholder [×2] — EMPTY
├── EDC (from edc):
│   ├── tt_edc1_intf_connector (portless)
│   ├── tt_edc1_serial_bus_repeater (i_clk, i_reset_n; assertion)
│   ├── tt_edc1_biu_soc_apb4_wrap → inner (APB4 + 5 IRQs)
│   ├── tt_edc1_noc_sec_block_reg → inner (NoC security)
│   └── RF_2P_HSC_LVT_32X136M1FB1WM0DR0 [×2] (SRAM macro, v7 new)
├── NoC (from noc):
│   ├── repeaters_cardinal, arbiter_tree, secded_116_10
│   ├── upf_async_fifo, async_fifo_wr_side_reset, sync3_pulse
│   ├── skid_buffer, harvest_robust_sync, niu_mst_timeout
│   └── RF_2P_HSC_LVT_32X136M1FB1WM0DR0 [×2+] (SRAM macro, v7 new)
├── DFX (from chip_grounded):
│   ├── tt_disp_eng_l1_partition_dfx (iJTAG chain)
│   │   ← receives from noc_niu_router_dfx
│   │   → sends to dfd
│   └── RF_2P_HSC_LVT_32X136M1FB1WM0DR0 [×3+] (SRAM macro, v7 new)
├── Clock (from chip): clkdiv2, clkbuf, clkgater
└── SMN (from overlay): smn_clkdiv(5/3), smn_repeater(16/8)
```

---

## 5. Compute Tile — Tensix

*(from v7_overlay — TDMA expanded to 3 sub-modules)*

### 5.1 SFPU

- **tt_sfpu_lregs:** register file, transpose/shift, parity
- **tt_sfpu_instrn_resources_used:** R/W hazards, stalls

### 5.2 TDMA *(v7: 3 sub-modules, up from 1 in v6c)*

- **tt_tdma_xy_address_controller:** DMA address generation *(v7 new)*
- **tt_tdma_thread_context:** thread context, multi-channel DMA
- **tt_tdma_rts_rtr_pipe_stage:** pipelined RTS/RTR arbitration *(v7 new)*

### 5.3 L1

- **tt_t6_l1_partition:** 16-bank SRAM, EDC sram modport

### 5.4 FDS Registers

- tt_fds_tensixneo_reg(106/41)
- tt_fds_dispatch_reg(68/41)
- tt_cluster_ctrl_t6_l1_csr_reg(38/97)

---

## 6. Dispatch Engine

*(from v7_chip_no_grounding)*

tt_dispatch_top_east (X=0, Y=3, EP=3), tt_dispatch_top_west (X=3, Y=3, EP=18)

---

## 7. NoC Fabric

*(from v7_noc + chip)*

Config: EnableDynamicRouting=1, NumAxes=2, NumDirections=2

9 modules: repeaters_cardinal, arbiter_tree, secded_116_10, upf_async_fifo, async_fifo_wr_side_reset, sync3_pulse, skid_buffer, harvest_robust_sync, niu_mst_timeout

Bridge: noc2axi_router_nw_opt + tt_mem_wrap_32x1024_2p_nomask(ATT) + selftest(BIST)

SRAM macro *(v7 new)*: RF_2P_HSC_LVT_32X136M1FB1WM0DR0 (×2+) — 32×136 dual-port, HSC LVT

---

## 8. NIU — AXI Bridge Tiles

*(from v7_chip + noc)*

| Tile | Position | EP |
|------|----------|----|
| trinity_noc2axi_ne_opt | (X=0, Y=4) | 4 |
| trinity_noc2axi_router_ne_opt | (X=1, Y=4+3) | 9/8 |
| trinity_noc2axi_router_nw_opt | (X=2, Y=4+3) | 14/13 |
| trinity_noc2axi_nw_opt | (X=3, Y=4) | 19 |

---

## 9. Clock Architecture

*(from v7_chip + overlay)*

**trinity_clock_routing_t:** ai_clk, noc_clk, dm_clk, ai_clk_reset_n, noc_clk_reset_n, dm_uncore_clk_reset_n, tensix_reset_n, power_good

Modules: tt_clkdiv2, tt_clkbuf, tt_clkgater, tt_smn_clkdiv(5/3)

v7 additions: i_dm_clk[SizeX-1:0] provides per-column DM clock domain alongside existing ai_clk and noc_clk.

---

## 10. Reset Architecture

*(from v7_chip — expanded with DM resets)*

### 10.1 Reset Signals

| Reset | Width | Scope |
|-------|-------|-------|
| i_noc_reset_n | 1 | Global NoC |
| i_ai_reset_n[3:0] | 4 | Per-column AI |
| i_tensix_reset_n[11:0] | 12 | Per-Tensix |
| i_edc_reset_n | 1 | EDC |
| i_dm_core_reset_n[13:0][7:0] | 14×8 | Per-DM-core *(v7 new)* |
| i_dm_uncore_reset_n[13:0] | 14 | Per-DM-complex uncore *(v7 new)* |

### 10.2 Port Classifier Mapping *(v7 new)*

- **AI_Clock_Reset(2):** i_ai_clk, i_ai_reset_n
- **Tensix_Reset(1):** i_tensix_reset_n
- **DM_Clock_Reset(3):** i_dm_clk, i_dm_core_reset_n, i_dm_uncore_reset_n

---

## 11. EDC

*(from v7_edc + chip_grounded)*

### 11.1 Interface (tt_edc_pkg.sv)

4 modports: ingress / egress / edc_node / sram. Toggle-handshake: req_tgl / ack_tgl.

### 11.2 Modules

- **tt_edc1_intf_connector:** portless connector
- **tt_edc1_serial_bus_repeater:** i_clk, i_reset_n; assertion-based verification
- **tt_edc1_biu_soc_apb4_wrap → inner:** APB4 bridge + 5 IRQs
  - In: s_apb_{psel, penable, pwrite, pprot, paddr, pwdata, pstrb}
  - Out: s_apb_{pready, prdata, pslverr} + 5 IRQs
- **tt_edc1_noc_sec_block_reg → inner:** NoC security register block

### 11.3 SRAM Macros *(v7 new)*

RF_2P_HSC_LVT_32X136M1FB1WM0DR0 (×2) — 32×136 dual-port, HSC LVT

---

## 12. SRAM Inventory

*(from v7_noc + edc + chip_grounded + overlay — consolidated)*

| SRAM Macro | Geometry | Type | Instances | Source |
|------------|----------|------|-----------|--------|
| tt_mem_wrap_32x1024_2p_nomask | 32b×1024 | 2P | ATT | v7_noc |
| RF_2P_HSC_LVT_32X136M1FB1WM0DR0 | 32×136 | Dual-port, HSC LVT | ×2 (EDC) + ×2+ (NoC) + ×3+ (DFX) | v7_edc, v7_noc, v7_chip_grounded |

*(v7 new: RF_2P_HSC_LVT_32X136M1FB1WM0DR0 discovered across EDC, NoC, and DFX sub-modules)*

---

## 13. DFX

*(from v7_chip_grounded + overlay)*

### 13.1 iJTAG Chain *(v7 enhanced)*

- **tt_instrn_engine_wrapper_dfx** (11/9, iJTAG)
- **tt_disp_eng_l1_partition_dfx** (iJTAG chain)
  - ← receives from **noc_niu_router_dfx** *(v7 new: upstream identified)*
  - → sends to **dfd** *(v7 new: downstream identified)*
- **noc_routing_translation_selftest** (ATT BIST)

### 13.2 DFX SRAM *(v7 new)*

RF_2P_HSC_LVT_32X136M1FB1WM0DR0 (×3+) — used within DFX partition

---

## 14. RTL File Reference

| # | File | Content |
|---|------|---------|
| 1 | used_in_n1/rtl/targets/4x5/trinity_pkg.sv | 13 localparams, tile_t, clock struct |
| 2 | used_in_n1/rtl/trinity.sv | Top module |
| 3-4 | mem_port/legacy variants | Top variants |
| 5 | rtl/trinity_router.sv | Router (placeholder) |
| 6-10 | tt_edc_pkg.sv (5 variants) | EDC interface |

---

## Appendix: Source Traceability

| Section | Primary Source | v7 Enhancements |
|---------|---------------|-----------------|
| 1 Overview | v7_chip_no_grounding | — |
| 2 Package/Grid | v7_chip_no_grounding | — |
| 3 Top-Level Ports | v7_chip_no_grounding | DM clk/reset ports, full APB register ports, full EDC APB ports, Port Classifier claims |
| 4 Hierarchy | all 5 v7 files merged | TDMA 3 sub-modules, RF_2P SRAM macro across EDC/NoC/DFX, iJTAG chain topology |
| 5 Tensix | v7_overlay | tt_tdma_xy_address_controller, tt_tdma_rts_rtr_pipe_stage (2 new TDMA sub-modules) |
| 6 Dispatch | v7_chip_no_grounding | — |
| 7 NoC | v7_noc + chip | RF_2P_HSC_LVT_32X136M1FB1WM0DR0 SRAM macro |
| 8 NIU | v7_chip + noc | — |
| 9 Clock | v7_chip + overlay | i_dm_clk per-column DM clock domain |
| 10 Reset | v7_chip | i_dm_core_reset_n, i_dm_uncore_reset_n; Port Classifier mapping |
| 11 EDC | v7_edc + chip_grounded | RF_2P_HSC_LVT_32X136M1FB1WM0DR0 (×2), full BIU APB4 signal list |
| 12 SRAM | v7_noc + edc + chip_grounded | Consolidated RF_2P inventory across all sub-systems |
| 13 DFX | v7_chip_grounded + overlay | iJTAG chain: noc_niu_router_dfx → tt_disp_eng_l1_partition_dfx → dfd; RF_2P (×3+) |
| 14 RTL Files | chip + overlay | — |

---

### v7 Delta Summary (vs v6c)

| # | Enhancement | Detail |
|---|-------------|--------|
| 1 | DM Clock/Reset ports | i_dm_clk[SizeX-1:0], i_dm_core_reset_n[14][8], i_dm_uncore_reset_n[14] |
| 2 | Full APB register ports | i_reg_psel/paddr/penable/pwrite/pwdata, o_reg_pready/prdata/pslverr |
| 3 | Full EDC APB ports | i_edc_apb_psel/penable/pwrite/pprot[2:0]/paddr[5:0]/pwdata[31:0]/pstrb[3:0], o_edc_apb_pready/prdata[31:0] |
| 4 | Port Classifier claims | AI_Clock_Reset(2), Tensix_Reset(1), DM_Clock_Reset(3) |
| 5 | TDMA sub-modules expanded | +tt_tdma_xy_address_controller, +tt_tdma_rts_rtr_pipe_stage (total 3) |
| 6 | RF_2P SRAM macro | RF_2P_HSC_LVT_32X136M1FB1WM0DR0 (32×136 dual-port) across EDC(×2), NoC(×2+), DFX(×3+) |
| 7 | DFX iJTAG chain topology | noc_niu_router_dfx → tt_disp_eng_l1_partition_dfx → dfd |

---

*End of Document — N1B0 NPU HDD v7 (Merged)*
