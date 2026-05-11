# N1B0 NPU — Full Hardware Design Document

> **Pipeline ID:** tt_20260221
> **Version:** v6c (Multi-topic Integrated)
> **RAG:** v4.1 + Package Parser v2 (localparam int 지원)
> **Method:** 5-round topic search (72 results) → unified synthesis
> **Generated:** 2026-04-28

---

## Table of Contents

1. [Overview](#1-overview)
2. [Package Constants and Grid](#2-package-constants-and-grid)
3. [Top-Level Ports](#3-top-level-ports)
4. [Module Hierarchy](#4-module-hierarchy)
5. [Compute Tile — Tensix](#5-compute-tile--tensix)
6. [Dispatch Engine](#6-dispatch-engine)
7. [NoC Fabric](#7-noc-fabric)
8. [NIU — AXI Bridge Tiles](#8-niu--axi-bridge-tiles)
9. [Clock Architecture](#9-clock-architecture)
10. [Reset Architecture](#10-reset-architecture)
11. [EDC — Error Detection and Correction](#11-edc--error-detection-and-correction)
12. [SRAM Inventory](#12-sram-inventory)
13. [DFX Hierarchy](#13-dfx-hierarchy)
14. [RTL File Reference](#14-rtl-file-reference)

---

## 1. Overview

N1B0 is the Trinity NPU integrated into the N1 SoC. The top module `trinity` implements a **4-column × 5-row tile mesh** (SizeX=4, SizeY=5) containing 20 tiles connected by a 2D NoC fabric.

### 1.1 Tile Composition

| Tile Type | Count | RTL Module | Grid Position |
|-----------|-------|------------|---------------|
| TENSIX | 12 | `tt_tensix_with_l1` | Y=0..2, X=0..3 |
| NOC2AXI_NE_OPT | 1 | `trinity_noc2axi_ne_opt` | (X=0, Y=4) |
| NOC2AXI_ROUTER_NE_OPT | 1 | `trinity_noc2axi_router_ne_opt` | (X=1, Y=4+3) |
| NOC2AXI_ROUTER_NW_OPT | 1 | `trinity_noc2axi_router_nw_opt` | (X=2, Y=4+3) |
| NOC2AXI_NW_OPT | 1 | `trinity_noc2axi_nw_opt` | (X=3, Y=4) |
| DISPATCH_E | 1 | `tt_dispatch_top_east` | (X=0, Y=3) |
| DISPATCH_W | 1 | `tt_dispatch_top_west` | (X=3, Y=3) |
| ROUTER | 2 | (empty placeholder) | (X=1,2, Y=3) |
| **Total** | **20** | | |

### 1.2 Key Design Features

| Feature | Value |
|---------|-------|
| Grid | SizeX=4, SizeY=5 (20 tiles) |
| NumTensix | 12 |
| DMCoresPerCluster | 8 |
| EnableDynamicRouting | 1 |
| Clock routing | Per-column (`i_ai_clk[SizeX-1:0]`) |
| EDC protocol | Toggle-handshake (req_tgl/ack_tgl) |
| ROUTER placeholder | Empty — logic in NOC2AXI_ROUTER tiles |

---

## 2. Package Constants and Grid

**File:** `used_in_n1/rtl/targets/4x5/trinity_pkg.sv`

### 2.1 Constants (13 localparams — KB confirmed)

| Constant | Value | Description |
|----------|-------|-------------|
| `SizeX` | 4 | Columns |
| `SizeY` | 5 | Rows |
| `NumNodes` | 20 | SizeX × SizeY |
| `NumTensix` | 12 | TENSIX tiles (Y=0..2) |
| `NumNoc2Axi` | 4 | NOC2AXI tiles (Y=4) |
| `NumDispatch` | 2 | Dispatch tiles (Y=3) |
| `NumApbNodes` | 4 | APB buses (per column) |
| `NumDmComplexes` | 14 | NumTensix + NumDispatch |
| `DMCoresPerCluster` | 8 | DM cores per tile |
| `TensixPerCluster` | 4 | Tensix per cluster |
| `EnableDynamicRouting` | 1'b1 | Dynamic routing enabled |
| `NumAxes` | 2 | NoC axes |
| `NumDirections` | 2 | NoC directions |

### 2.2 Tile Type Enum (`tile_t`, 3-bit)

| Value | Name | RTL Module | Position |
|-------|------|------------|----------|
| 3'd0 | `TENSIX` | `tt_tensix_with_l1` | Y=0..2, X=0..3 |
| 3'd1 | `NOC2AXI_NE_OPT` | `trinity_noc2axi_ne_opt` | (X=0, Y=4) |
| 3'd2 | `NOC2AXI_ROUTER_NE_OPT` | `trinity_noc2axi_router_ne_opt` | (X=1, Y=4+3) |
| 3'd3 | `NOC2AXI_ROUTER_NW_OPT` | `trinity_noc2axi_router_nw_opt` | (X=2, Y=4+3) |
| 3'd4 | `NOC2AXI_NW_OPT` | `trinity_noc2axi_nw_opt` | (X=3, Y=4) |
| 3'd5 | `DISPATCH_E` | `tt_dispatch_top_east` | (X=0, Y=3) |
| 3'd6 | `DISPATCH_W` | `tt_dispatch_top_west` | (X=3, Y=3) |
| 3'd7 | `ROUTER` | (empty) | (X=1,2, Y=3) |

### 2.3 Endpoint Index Table (`EP = x * 5 + y`)

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
| 1 | 3 | ROUTER (placeholder) | 8 |
| 1 | 4 | NOC2AXI_ROUTER_NE_OPT | 9 |
| 2 | 0 | TENSIX | 10 |
| 2 | 1 | TENSIX | 11 |
| 2 | 2 | TENSIX | 12 |
| 2 | 3 | ROUTER (placeholder) | 13 |
| 2 | 4 | NOC2AXI_ROUTER_NW_OPT | 14 |
| 3 | 0 | TENSIX | 15 |
| 3 | 1 | TENSIX | 16 |
| 3 | 2 | TENSIX | 17 |
| 3 | 3 | DISPATCH_W | 18 |
| 3 | 4 | NOC2AXI_NW_OPT | 19 |

### 2.4 NoC Enums

| Enum | Members |
|------|---------|
| `noc_axis_t` | Y_AXIS=1'b0, X_AXIS=1'b1 |
| `noc_direction_t` | POSITIVE=1'b0, NEGATIVE=1'b1 |

### 2.5 Block Diagram

```
         X=0              X=1                   X=2                  X=3
        ┌────────────┬─────────────────────────────────────┬────────────┐
Y=4:    │ NIU_NE     │ NIU_ROUTER_NE          NIU_ROUTER_NW│ NIU_NW     │
        │ EP=4       │ EP=9                   EP=14         │ EP=19      │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=3:    │ DISPATCH_E │ [ROUTER placeholder]  [ROUTER phdr]  │ DISPATCH_W │
        │ EP=3       │ EP=8 (inside _NE_OPT) EP=13(_NW_OPT)│ EP=18      │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=2:    │ T6[0][2]   │ T6[1][2]              T6[2][2]       │ T6[3][2]   │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=1:    │ T6[0][1]   │ T6[1][1]              T6[2][1]       │ T6[3][1]   │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=0:    │ T6[0][0]   │ T6[1][0]              T6[2][0]       │ T6[3][0]   │
        └────────────┴─────────────────────────────────────-┴────────────┘
```

---

## 3. Top-Level Ports

**Module:** `trinity` — **File:** `used_in_n1/rtl/trinity.sv`

### 3.1 Clocks and Resets

| Port | Width | Description |
|------|-------|-------------|
| `i_axi_clk` | 1 | AXI bus clock (global) |
| `i_noc_clk` | 1 | NoC clock (global) |
| `i_noc_reset_n` | 1 | NoC reset |
| `i_ai_clk[SizeX-1:0]` | 4 | AI clock per column |
| `i_ai_reset_n[SizeX-1:0]` | 4 | AI reset per column |
| `i_tensix_reset_n[NumTensix-1:0]` | 12 | Per-Tensix reset |
| `i_edc_reset_n` | 1 | EDC reset |

### 3.2 EDC APB + IRQs

| Port | Description |
|------|-------------|
| `i_edc_apb_{psel,paddr,pwdata,pstrb}` | EDC APB slave (per-column) |
| `o_edc_apb_{pready,prdata}` | EDC APB response |
| `o_edc_{fatal,crit,cor}_err_irq` | Error interrupts |
| `o_edc_pkt_{sent,rcvd}_irq` | Packet interrupts |

### 3.3 Key Instances

| Instance | Module |
|----------|--------|
| `tt_tensix_with_l1` | Tensix (×12) |
| `tt_dispatch_top_inst_east` | `tt_dispatch_top_east` |
| `tt_dispatch_top_inst_west` | `tt_dispatch_top_west` |
| `edc_direct_conn_nodes` | `tt_edc1_intf_connector` |
| `edc_loopback_conn_nodes` | `tt_edc1_intf_connector` |

---

## 4. Module Hierarchy

```
trinity (top)
├── [Y=0..2, X=0..3] tt_tensix_with_l1 [×12]
│   ├── tt_sfpu_lregs — SFPU register file
│   ├── tt_sfpu_instrn_resources_used — Instruction hazard tracker
│   └── tt_tdma_thread_context — Multi-channel DMA
├── [X=0, Y=3] tt_dispatch_top_east (EP=3)
├── [X=3, Y=3] tt_dispatch_top_west (EP=18)
├── [X=0, Y=4] trinity_noc2axi_ne_opt (EP=4)
├── [X=1, Y=4+3] trinity_noc2axi_router_ne_opt (EP=9/8)
├── [X=2, Y=4+3] trinity_noc2axi_router_nw_opt (EP=14/13)
├── [X=3, Y=4] trinity_noc2axi_nw_opt (EP=19)
├── [X=1,2, Y=3] ROUTER placeholder — EMPTY
├── EDC: tt_edc1_{intf_connector, serial_bus_repeater, biu_soc_apb4_wrap, noc_sec_block_reg}
├── NoC: repeaters_cardinal, arbiter_tree, secded_116_10, upf_async_fifo, sync3_pulse, harvest_robust_sync, skid_buffer, niu_mst_timeout
├── Clock: tt_clkdiv2, tt_clkbuf, tt_clkgater
└── SMN: tt_smn_clkdiv (5/3), tt_smn_repeater_struct (16/8)
```

---

## 5. Compute Tile — Tensix

**Module:** `tt_tensix_with_l1` (×12) | **Position:** Y=0..2, X=0..3

### 5.1 SFPU

- `tt_sfpu_lregs`: Register file — transpose/shift, data/parity R/W, parity error reporting, error injection
- `tt_sfpu_instrn_resources_used`: R/W hazards, stall conditions, SFPU instruction status

### 5.2 TDMA

- `tt_tdma_thread_context`: Address/control gen for multi-channel DMA, RTS/RTR control
- TDMA manages address generation, thread context, and RTS/RTR for NoC-based system

### 5.3 L1 Cache

- `tt_t6_l1_partition`: 16-bank SRAM, EDC via `sram` modport

### 5.4 Register Files

DEST (FPU accumulation), SRCB (FPU operand B)

---

## 6. Dispatch Engine

| Instance | Module | Position | EP |
|----------|--------|----------|----|
| `tt_dispatch_top_inst_east` | `tt_dispatch_top_east` | (X=0, Y=3) | 3 |
| `tt_dispatch_top_inst_west` | `tt_dispatch_top_west` | (X=3, Y=3) | 18 |

---

## 7. NoC Fabric

### 7.1 Configuration

| Parameter | Value |
|-----------|-------|
| `EnableDynamicRouting` | 1 |
| `NumAxes` | 2 |
| `NumDirections` | 2 |

### 7.2 Modules (9 unique)

| Module | Function |
|--------|----------|
| `tt_noc_repeaters_cardinal` | Cardinal-direction repeaters |
| `noc_arbiter_tree` | Tree-based priority arbitration |
| `tt_noc_secded_chk_corr_116_10` | SECDED ECC (116b + 10b) |
| `tt_upf_async_fifo` | Async FIFO for CDC |
| `tt_noc_async_fifo_wr_side_reset` | FIFO reset gen |
| `tt_noc_sync3_pulse` | 3-stage pulse sync |
| `tt_skid_buffer_new_assertion_off` | I/O decoupling |
| `tt_harvest_robust_sync` | Harvest signal sync |
| `tt_niu_mst_timeout` | AXI master timeout |

---

## 8. NIU — AXI Bridge Tiles

| Tile | Type | Position | EP |
|------|------|----------|----|
| `trinity_noc2axi_ne_opt` | Corner NIU | (X=0, Y=4) | 4 |
| `trinity_noc2axi_router_ne_opt` | NIU+Router | (X=1, Y=4+3) | 9/8 |
| `trinity_noc2axi_router_nw_opt` | NIU+Router | (X=2, Y=4+3) | 14/13 |
| `trinity_noc2axi_nw_opt` | Corner NIU | (X=3, Y=4) | 19 |

ATT: `tt_mem_wrap_32x1024_2p_nomask` (32b×1024, 2P) + `noc_routing_translation_selftest`

---

## 9. Clock Architecture

### `trinity_clock_routing_t` struct (8 fields)

| Field | Description |
|-------|-------------|
| `ai_clk` | AI compute clock (per-column) |
| `noc_clk` | NoC fabric clock (global) |
| `dm_clk` | Data movement clock |
| `ai_clk_reset_n` | AI reset |
| `noc_clk_reset_n` | NoC reset |
| `dm_uncore_clk_reset_n` | DM uncore reset |
| `tensix_reset_n` | Per-tile reset |
| `power_good` | Power good |

Modules: `tt_clkdiv2`, `tt_clkbuf`, `tt_clkgater`, `tt_smn_clkdiv` (5/3)

---

## 10. Reset Architecture

| Signal | Width | Description |
|--------|-------|-------------|
| `i_noc_reset_n` | 1 | Global NoC |
| `i_ai_reset_n[SizeX-1:0]` | 4 | Per-column AI |
| `i_tensix_reset_n[NumTensix-1:0]` | 12 | Per-tile Tensix |
| `i_edc_reset_n` | 1 | EDC |

---

## 11. EDC

### Interface (`tt_edc_pkg.sv`, 4 modports)

| Modport | Signals |
|---------|---------|
| `ingress` | in req_tgl, out ack_tgl, in cor_err, out err_inj_vec |
| `egress` | out req_tgl, in ack_tgl, out cor_err, in err_inj_vec |
| `edc_node` | Bidirectional |
| `sram` | in err_inj_vec, out cor_err |

### Modules

| Module | Function |
|--------|----------|
| `tt_edc1_intf_connector` | Direct + loopback nodes (portless) |
| `tt_edc1_serial_bus_repeater` | Ring repeater (i_clk, i_reset_n) |
| `tt_edc1_biu_soc_apb4_wrap` → inner | APB4 BIU + 5 IRQs |
| `tt_edc1_noc_sec_block_reg` → inner | NoC security config |

---

## 12. SRAM Inventory

| SRAM | Size | Ports | Usage |
|------|------|-------|-------|
| `tt_mem_wrap_32x1024_2p_nomask` | 32b×1024 | 2P | ATT |

---

## 13. DFX Hierarchy

| Module | Function |
|--------|----------|
| `tt_instrn_engine_wrapper_dfx` (11in/9out) | iJTAG + clock |
| `tt_disp_eng_l1_partition_dfx` | iJTAG chain |
| `noc_routing_translation_selftest` | ATT BIST |

---

## 14. RTL File Reference

| # | File | Content |
|---|------|---------|
| 1 | `used_in_n1/rtl/targets/4x5/trinity_pkg.sv` | 13 localparams, tile_t, clock struct, NoC enums |
| 2 | `used_in_n1/rtl/trinity.sv` | Top module |
| 3 | `used_in_n1/mem_port/rtl/trinity.sv` | Top (mem_port) |
| 4 | `used_in_n1/legacy/no_mem_port/rtl/trinity.sv` | Top (legacy) |
| 5 | `rtl/trinity_router.sv` | Router (placeholder) |
| 6-10 | `tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` (5 variants) | EDC interface |

---

*End of Document — N1B0 NPU HDD v6c*