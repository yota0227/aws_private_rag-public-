# N1B0 NPU — Full Hardware Design Document

> **Pipeline ID:** tt_20260221
> **Version:** v6c
> **RAG:** v4.1 + Package Parser v2
> **Method:** 5-round topic search → per-topic files → merge
> **Sources:** v6c_chip_no_grounding, v6c_chip_grounded, v6c_edc, v6c_noc, v6c_overlay
> **Generated:** 2026-04-28

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

**File:** `used_in_n1/rtl/targets/4x5/trinity_pkg.sv` *(from v6c_chip_no_grounding)*

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

*(from v6c_chip_no_grounding)*

| Port | Width | Description |
|------|-------|-------------|
| i_axi_clk | 1 | AXI clock |
| i_noc_clk | 1 | NoC clock |
| i_noc_reset_n | 1 | NoC reset |
| i_ai_clk[SizeX-1:0] | 4 | AI clock per column |
| i_ai_reset_n[SizeX-1:0] | 4 | AI reset per column |
| i_tensix_reset_n[NumTensix-1:0] | 12 | Per-Tensix reset |
| i_edc_reset_n | 1 | EDC reset |
| i_edc_apb_* | per-column | EDC APB |

---

## 4. Module Hierarchy

*(merged from all 5 sources)*

```
trinity (top)
├── tt_tensix_with_l1 [×12] — Y=0..2
│   ├── tt_sfpu_lregs (from overlay)
│   ├── tt_sfpu_instrn_resources_used (from overlay)
│   └── tt_tdma_thread_context (from overlay)
├── tt_dispatch_top_east EP=3 (from chip)
├── tt_dispatch_top_west EP=18 (from chip)
├── trinity_noc2axi_ne_opt EP=4 (from chip)
├── trinity_noc2axi_router_ne_opt EP=9/8 (from chip)
├── trinity_noc2axi_router_nw_opt EP=14/13 (from chip)
├── trinity_noc2axi_nw_opt EP=19 (from chip)
├── ROUTER placeholder [×2] — EMPTY
├── EDC (from edc): intf_connector, serial_bus_repeater, biu_apb4_wrap, noc_sec_block_reg
├── NoC (from noc): repeaters, arbiter, secded, async_fifo, sync3, harvest, skid, timeout
├── Clock (from chip): clkdiv2, clkbuf, clkgater
└── SMN (from overlay): smn_clkdiv(5/3), smn_repeater(16/8)
```

---

## 5. Compute Tile — Tensix

*(from v6c_overlay)*

**SFPU:** tt_sfpu_lregs (register file, transpose/shift, parity), tt_sfpu_instrn_resources_used (R/W hazards, stalls)

**TDMA:** tt_tdma_thread_context (multi-channel DMA, RTS/RTR, addr gen)

**L1:** tt_t6_l1_partition (16-bank SRAM, EDC sram modport)

**FDS:** tt_fds_tensixneo_reg(106/41), tt_fds_dispatch_reg(68/41), tt_cluster_ctrl_t6_l1_csr_reg(38/97)

---

## 6. Dispatch Engine

*(from v6c_chip_no_grounding)*

tt_dispatch_top_east (X=0,Y=3,EP=3), tt_dispatch_top_west (X=3,Y=3,EP=18)

---

## 7. NoC Fabric

*(from v6c_noc + chip)*

Config: EnableDynamicRouting=1, NumAxes=2, NumDirections=2

9 modules: repeaters_cardinal, arbiter_tree, secded_116_10, upf_async_fifo, async_fifo_wr_side_reset, sync3_pulse, skid_buffer, harvest_robust_sync, niu_mst_timeout

Bridge: noc2axi_router_nw_opt + tt_mem_wrap_32x1024_2p_nomask(ATT) + selftest(BIST)

---

## 8. NIU — AXI Bridge Tiles

*(from v6c_chip + noc)*

| Tile | Position | EP |
|------|----------|----|
| trinity_noc2axi_ne_opt | (X=0,Y=4) | 4 |
| trinity_noc2axi_router_ne_opt | (X=1,Y=4+3) | 9/8 |
| trinity_noc2axi_router_nw_opt | (X=2,Y=4+3) | 14/13 |
| trinity_noc2axi_nw_opt | (X=3,Y=4) | 19 |

---

## 9. Clock Architecture

*(from v6c_chip + overlay)*

**trinity_clock_routing_t:** ai_clk, noc_clk, dm_clk, ai_clk_reset_n, noc_clk_reset_n, dm_uncore_clk_reset_n, tensix_reset_n, power_good

Modules: tt_clkdiv2, tt_clkbuf, tt_clkgater, tt_smn_clkdiv(5/3)

---

## 10. Reset Architecture

*(from v6c_chip)*

i_noc_reset_n(1), i_ai_reset_n[3:0](4), i_tensix_reset_n[11:0](12), i_edc_reset_n(1)

---

## 11. EDC

*(from v6c_edc + overlay)*

**Interface (tt_edc_pkg.sv):** ingress/egress/edc_node/sram modports. Toggle-handshake: req_tgl/ack_tgl.

**Modules:** intf_connector, serial_bus_repeater(i_clk,i_reset_n), biu_soc_apb4_wrap→inner (APB4+5IRQs), noc_sec_block_reg→inner

---

## 12. SRAM Inventory

*(from v6c_noc)*

tt_mem_wrap_32x1024_2p_nomask (32b×1024, 2P, ATT)

---

## 13. DFX

*(from v6c_chip + overlay)*

tt_instrn_engine_wrapper_dfx(11/9, iJTAG), tt_disp_eng_l1_partition_dfx(iJTAG chain), noc_routing_translation_selftest(ATT BIST)

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

| Section | Source File |
|---------|------------|
| 1-3 Overview/Package/Ports | v6c_chip_no_grounding |
| 4 Hierarchy | all 5 files merged |
| 5 Tensix | v6c_overlay |
| 6 Dispatch | v6c_chip_no_grounding |
| 7-8 NoC/NIU | v6c_noc + chip |
| 9-10 Clock/Reset | v6c_chip + overlay |
| 11 EDC | v6c_edc + overlay |
| 12 SRAM | v6c_noc |
| 13 DFX | v6c_chip + overlay |
| 14 RTL Files | chip + overlay |

---

*End of Document — N1B0 NPU HDD v6c (Merged)*