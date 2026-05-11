# N1B0 NPU — Full Hardware Design Document

> **Pipeline ID:** tt_20260221
> **Version:** v6a (Multi-topic Integrated)
> **RAG:** v4.1 + Package Parser
> **Method:** 5-round topic search → unified synthesis
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

N1B0 is the Trinity NPU integrated into the N1 SoC. The top module `trinity` instantiates a tile mesh connected by a 2D NoC fabric.

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

- `EnableDynamicRouting = 1'b1` — Dynamic NoC routing enabled
- Combined NIU+Router tiles at X=1,2 (Y=4+Y=3 dual-row)
- ROUTER placeholder at Y=3 is empty by design — router logic embedded in NOC2AXI_ROUTER_NE/NW_OPT
- EDC serial ring with toggle-handshake protocol
- Per-column clock arrays, per-tile reset

---

## 2. Package Constants and Grid

**File:** `used_in_n1/rtl/targets/4x5/trinity_pkg.sv`

### 2.1 Tile Type Enum (`tile_t`, 3-bit)

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

### 2.2 NoC Enums

| Enum | Members | Description |
|------|---------|-------------|
| `noc_axis_t` | Y_AXIS=1'b0, X_AXIS=1'b1 | NoC routing axis selection |
| `noc_direction_t` | POSITIVE=1'b0, NEGATIVE=1'b1 | NoC routing direction |

### 2.3 Clock Routing Struct

`trinity_clock_routing_t` — packed struct with 8 fields:

| Field | Description |
|-------|-------------|
| `ai_clk` | AI compute clock |
| `noc_clk` | NoC fabric clock |
| `dm_clk` | Data movement clock |
| `ai_clk_reset_n` | AI clock domain reset |
| `noc_clk_reset_n` | NoC clock domain reset |
| `dm_uncore_clk_reset_n` | DM uncore reset |
| `tensix_reset_n` | Per-tile Tensix reset |
| `power_good` | Power good signal |

### 2.4 Grid Layout

```
         X=0              X=1                   X=2                  X=3
        ┌────────────┬─────────────────────────────────────┬────────────┐
Y=4:    │ NOC2AXI_   │ NOC2AXI_ROUTER_       NOC2AXI_ROUTER│ NOC2AXI_   │
        │ NE_OPT     │ NE_OPT                _NW_OPT       │ NW_OPT     │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=3:    │ DISPATCH_E │ [ROUTER placeholder]  [ROUTER phdr]  │ DISPATCH_W │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=2:    │ TENSIX     │ TENSIX                TENSIX          │ TENSIX     │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=1:    │ TENSIX     │ TENSIX                TENSIX          │ TENSIX     │
        ├────────────┼─────────────────────────────────────-┼────────────┤
Y=0:    │ TENSIX     │ TENSIX                TENSIX          │ TENSIX     │
        └────────────┴─────────────────────────────────────-┴────────────┘
```

---

## 3. Top-Level Ports

**Module:** `trinity` (from `used_in_n1/rtl/trinity.sv`)

### 3.1 Clock and Reset

| Port | Width | Description |
|------|-------|-------------|
| `i_axi_clk` | 1 | AXI bus clock |
| `i_noc_clk` | 1 | NoC fabric clock |
| `i_noc_reset_n` | 1 | NoC active-low reset |
| `i_ai_clk` | [SizeX-1:0] | Per-column AI compute clock |
| `i_ai_reset_n` | [SizeX-1:0] | Per-column AI reset |
| `i_tensix_reset_n` | [NumTensix-1:0] | Per-tile Tensix reset (12 bits) |
| `i_edc_reset_n` | 1 | EDC subsystem reset |

### 3.2 EDC APB Interface

| Port | Description |
|------|-------------|
| `i_edc_apb_*` | EDC APB slave interface (per-column) |

### 3.3 Key Instances (from `trinity.sv` module_parse)

| Instance Name | Module | Description |
|---------------|--------|-------------|
| `tt_tensix_with_l1` | `tt_tensix_with_l1` | Tensix compute tile (×12) |
| `tt_dispatch_top_inst_east` | `tt_dispatch_top_east` | East dispatch |
| `tt_dispatch_top_inst_west` | `tt_dispatch_top_west` | West dispatch |
| `edc_direct_conn_nodes` | `tt_edc1_intf_connector` | EDC direct connections |
| `edc_loopback_conn_nodes` | `tt_edc1_intf_connector` | EDC loopback connections |

---

## 4. Module Hierarchy

```
trinity (top) — used_in_n1/rtl/trinity.sv
│
├── [Y=0..2, X=0..3] tt_tensix_with_l1 [×12]
│   ├── SFPU
│   │   ├── tt_sfpu_lregs
│   │   │   Register file: transpose/shift, data/parity R/W,
│   │   │   diagnostic data, error injection, parity error reporting
│   │   └── tt_sfpu_instrn_resources_used
│   │       Instruction resource analysis: R/W hazards, stall conditions
│   ├── FPU
│   ├── TDMA
│   │   └── tt_tdma_thread_context
│   │       Address gen + control signals for multi-channel DMA,
│   │       RTS/RTR control, instruction-based configuration
│   ├── L1 Cache / SRAM
│   ├── DEST Register File
│   └── SRCB Register File
│
├── [X=0, Y=3] tt_dispatch_top_east (DISPATCH_E)
├── [X=3, Y=3] tt_dispatch_top_west (DISPATCH_W)
│
├── [X=0, Y=4] trinity_noc2axi_ne_opt (Corner NIU)
├── [X=1, Y=4+3] trinity_noc2axi_router_ne_opt (Combined NIU+Router)
│   ├── noc2axi_router logic
│   ├── tt_mem_wrap_32x1024_2p_nomask (ATT SRAM: 32b × 1024, dual-port)
│   └── noc_routing_translation_selftest (BIST)
├── [X=2, Y=4+3] trinity_noc2axi_router_nw_opt (Combined NIU+Router)
├── [X=3, Y=4] trinity_noc2axi_nw_opt (Corner NIU)
│
├── [X=1,2, Y=3] ROUTER placeholder [×2] — EMPTY by design
│
├── EDC Ring
│   ├── tt_edc1_intf_connector (direct_conn + loopback_conn)
│   ├── tt_edc1_serial_bus_repeater [×N] (i_clk, i_reset_n; assertion property)
│   ├── tt_edc1_biu_soc_apb4_wrap → edc1_biu_soc_apb4_inner
│   │   APB4: s_apb_{psel,penable,pwrite,pprot,paddr,pwdata,pstrb}
│   │   → s_apb_{pready,prdata,pslverr}
│   │   IRQs: fatal_err_irq, crit_err_irq, cor_err_irq, pkt_sent_irq, pkt_rcvd_irq
│   └── tt_edc1_noc_sec_block_reg → edc1_noc_sec_block_reg_inner
│       i_clk, i_reset_n, i_reg_cs, i_reg_wr_en, i_reg_addr, i_reg_wr_data
│
├── NoC Fabric
│   ├── tt_noc_repeaters_cardinal [×N] — Cardinal-direction repeaters
│   ├── noc_arbiter_tree [×M] — Priority-based tree arbitration (multiple instances)
│   ├── tt_noc_secded_chk_corr_116_10 [×N] — SECDED ECC (116-bit data + 10-bit check)
│   ├── tt_upf_async_fifo [×N] — Async FIFO for CDC (separate write/read clocks)
│   ├── tt_noc_async_fifo_wr_side_reset [×N] — FIFO reset gen (clock + power_good based)
│   ├── tt_noc_sync3_pulse [×N] — 3-stage pulse synchronizer
│   ├── tt_skid_buffer_new_assertion_off [×N] — I/O decoupling skid buffers
│   ├── tt_harvest_robust_sync [×N] — Harvest signal sync (multi-replication)
│   └── tt_niu_mst_timeout [×N] — AXI master timeout watchdog
│
├── Clock Distribution
│   ├── tt_clkdiv2 [×N] — Divide-by-2 dividers
│   ├── tt_clkbuf [×N] — Clock buffers
│   ├── tt_clkgater / tt_clk_gater [×N] — Clock gating cells
│   └── (interconnected to form clock distribution network)
│
├── SMN Subsystem
│   ├── tt_smn_clkdiv (5 in / 3 out) — Clock domain generation
│   └── tt_smn_repeater_struct (16 in / 8 out) — SMN data/control repeater
│
└── DFX
    ├── tt_instrn_engine_wrapper_dfx (11 in / 9 out) — iJTAG + clock signals
    └── tt_disp_eng_l1_partition_dfx — iJTAG chain (receives from noc_niu_router_dfx, sends to dfd)
```

---

## 5. Compute Tile — Tensix

Each `tt_tensix_with_l1` tile contains the following sub-blocks:

### 5.1 SFPU (Scalar Floating-Point Unit)

**`tt_sfpu_lregs`** — Local register file:
- Register read/write operations with diagnostic data access
- Support for transposing or shifting data
- Data/parity read-write with parity error reporting
- Error injection capability (DFT)

**`tt_sfpu_instrn_resources_used`** — Instruction resource tracker:
- Analyzes SFPU instructions for register read/write hazards
- Tracks SFPU instruction status and stall conditions
- Input ports for instruction data, output ports for hazard/stall signals

### 5.2 TDMA (Tensix DMA Engine)

**`tt_tdma_thread_context`** — Thread context manager:
- Generates addresses and control signals for multiple DMA channels
- Based on input instruction and configuration parameters
- Manages RTS/RTR (request-to-send/ready-to-receive) control signals
- Part of a NoC-based data movement system

### 5.3 L1 Cache / SRAM

- Per-tile SRAM scratchpad
- Connected to EDC ring via `sram` modport for ECC protection

### 5.4 Register Files

| Register | Purpose |
|----------|---------|
| DEST | FPU accumulation output |
| SRCB | FPU source operand B |

---

## 6. Dispatch Engine

| Instance | Module | Position | Tile Type |
|----------|--------|----------|-----------|
| `tt_dispatch_top_inst_east` | `tt_dispatch_top_east` | (X=0, Y=3) | DISPATCH_E (3'd5) |
| `tt_dispatch_top_inst_west` | `tt_dispatch_top_west` | (X=3, Y=3) | DISPATCH_W (3'd6) |

The Dispatch pipeline includes a `noc2axi_router_nw_opt` bridge component with `tt_mem_wrap_32x1024_2p_nomask` SRAM for routing translation.

---

## 7. NoC Fabric

### 7.1 Configuration

| Parameter | Value |
|-----------|-------|
| `EnableDynamicRouting` | 1'b1 (enabled) |
| `noc_axis_t` | Y_AXIS=1'b0, X_AXIS=1'b1 |
| `noc_direction_t` | POSITIVE=1'b0, NEGATIVE=1'b1 |

### 7.2 NoC Modules

| Module | Function | Instances |
|--------|----------|-----------|
| `tt_noc_repeaters_cardinal` | Cardinal-direction signal repeaters, connects input/output NoC packages | Multiple |
| `noc_arbiter_tree` | Tree-based priority arbitration for multiple requestors | Multiple |
| `tt_noc_secded_chk_corr_116_10` | SECDED ECC: 116-bit data + 10-bit check bits | Multiple |
| `tt_upf_async_fifo` | Async FIFO for CDC (separate write/read clock domains) | Multiple |
| `tt_noc_async_fifo_wr_side_reset` | Reset generation for async FIFO (clock + power_good based) | Multiple |
| `tt_noc_sync3_pulse` | 3-stage pulse synchronizer between clock domains | Multiple |
| `tt_skid_buffer_new_assertion_off` | Skid buffer for I/O decoupling | Multiple |
| `tt_harvest_robust_sync` | Harvest signal synchronizer (multi-replication for reliability) | Multiple |
| `tt_niu_mst_timeout` | AXI master timeout watchdog (configurable timeout → interrupt) | Multiple |

---

## 8. NIU — AXI Bridge Tiles

### 8.1 Corner NIU (NE/NW_OPT)

| Tile | Position | Type |
|------|----------|------|
| `trinity_noc2axi_ne_opt` | (X=0, Y=4) | NOC2AXI_NE_OPT (3'd1) |
| `trinity_noc2axi_nw_opt` | (X=3, Y=4) | NOC2AXI_NW_OPT (3'd4) |

### 8.2 Combined NIU+Router (NOC2AXI_ROUTER_NE/NW_OPT)

| Tile | Position | Type |
|------|----------|------|
| `trinity_noc2axi_router_ne_opt` | (X=1, Y=4+3) | NOC2AXI_ROUTER_NE_OPT (3'd2) |
| `trinity_noc2axi_router_nw_opt` | (X=2, Y=4+3) | NOC2AXI_ROUTER_NW_OPT (3'd3) |

These combined tiles embed both NOC2AXI bridge logic and Router logic in a single dual-row tile. The ROUTER placeholder at Y=3 (tile_t=3'd7) is empty — its logic lives here.

### 8.3 ATT (Address Translation Table)

- `tt_mem_wrap_32x1024_2p_nomask` — 32-bit × 1024-entry dual-port SRAM, no write mask
- `noc_routing_translation_selftest` — Built-in self-test for ATT

---

## 9. Clock Architecture

### 9.1 Clock Routing Structure

The `trinity_clock_routing_t` struct defines the per-tile clock/reset bundle:

| Field | Type | Description |
|-------|------|-------------|
| `ai_clk` | clock | AI compute clock (per-column: `i_ai_clk[SizeX-1:0]`) |
| `noc_clk` | clock | NoC fabric clock (global: `i_noc_clk`) |
| `dm_clk` | clock | Data movement clock |
| `ai_clk_reset_n` | reset | AI clock domain reset |
| `noc_clk_reset_n` | reset | NoC clock domain reset |
| `dm_uncore_clk_reset_n` | reset | DM uncore reset |
| `tensix_reset_n` | reset | Per-tile Tensix reset |
| `power_good` | signal | Power good indicator |

### 9.2 Clock Distribution Modules

| Module | Function |
|--------|----------|
| `tt_clkdiv2` | Divide-by-2 clock dividers |
| `tt_clkbuf` | Clock buffers for fanout/drive strength |
| `tt_clkgater` / `tt_clk_gater` | Clock gating cells for power management |
| `tt_smn_clkdiv` (5 in / 3 out) | SMN clock domain generation from noc_clk |

Clock buffer, gating, and divider modules are interconnected to form a clock distribution network.

---

## 10. Reset Architecture

### 10.1 Reset Signals

| Signal | Width | Description |
|--------|-------|-------------|
| `i_noc_reset_n` | 1 | Global NoC reset |
| `i_ai_reset_n` | [SizeX-1:0] | Per-column AI reset |
| `i_tensix_reset_n` | [NumTensix-1:0] | Per-tile Tensix reset (12 bits) |
| `i_edc_reset_n` | 1 | EDC subsystem reset |
| `trinity_clock_routing_t.tensix_reset_n` | per-tile | Reset via clock routing struct |
| `trinity_clock_routing_t.power_good` | per-tile | Power good signal |

### 10.2 Router Reset

`trinity_router.sv` ports include:
- `i_ai_reset_n`, `i_nocclk_reset_n`
- `i_dm_uncore_reset_n[SizeY-1:0]` — per-row DM uncore reset

---

## 11. EDC — Error Detection and Correction

### 11.1 EDC Interface (`tt_edc_pkg.sv`)

| Modport | Signals |
|---------|---------|
| `ingress` | input req_tgl, output ack_tgl, input cor_err, output err_inj_vec |
| `egress` | output req_tgl, input ack_tgl, output cor_err, input err_inj_vec |
| `edc_node` | Bidirectional (both ingress + egress) |
| `sram` | input err_inj_vec, output cor_err |

Toggle-handshake protocol: `req_tgl` transition → node processes → `ack_tgl` transition.

### 11.2 EDC Modules

| Module | Function |
|--------|----------|
| `tt_edc1_intf_connector` | Structural glue — direct + loopback connection nodes (portless) |
| `tt_edc1_serial_bus_repeater` | Ring signal repeater (i_clk, i_reset_n; contains assertion property) |
| `tt_edc1_biu_soc_apb4_wrap` | APB4 BIU wrapper → `edc1_biu_soc_apb4_inner` |
| `tt_edc1_noc_sec_block_reg` | NoC security config registers → `edc1_noc_sec_block_reg_inner` |

### 11.3 BIU APB4 Interface

**Input:** `s_apb_psel`, `s_apb_penable`, `s_apb_pwrite`, `s_apb_pprot`, `s_apb_paddr`, `s_apb_pwdata`, `s_apb_pstrb`

**Output:** `s_apb_pready`, `s_apb_prdata`, `s_apb_pslverr`

**Interrupts:** `fatal_err_irq`, `crit_err_irq`, `cor_err_irq`, `pkt_sent_irq`, `pkt_rcvd_irq`

### 11.4 NoC Security Block

`tt_edc1_noc_sec_block_reg`: `i_clk`, `i_reset_n`, `i_reg_cs`, `i_reg_wr_en`, `i_reg_addr`, `i_reg_wr_data` + NoC security configuration outputs.

---

## 12. SRAM Inventory

| SRAM Macro | Width | Depth | Ports | Write Mask | Usage |
|------------|-------|-------|-------|------------|-------|
| `tt_mem_wrap_32x1024_2p_nomask` | 32 bits | 1024 | Dual-port | None | ATT routing translation table |

All SRAM instances connected to EDC ring via `sram` modport for runtime ECC and DFT error injection.

---

## 13. DFX Hierarchy

### 13.1 DFX Modules

| Module | Ports | Function |
|--------|-------|----------|
| `tt_instrn_engine_wrapper_dfx` | 11 in / 9 out | iJTAG-related and clock-related signals |
| `tt_disp_eng_l1_partition_dfx` | — | iJTAG chain: receives from `tt_disp_eng_noc_niu_router_dfx`, sends to `dfd` module |
| `noc_routing_translation_selftest` | — | BIST for ATT SRAM |

### 13.2 EDC-Based Memory Test

- `err_inj_vec` → flip specific SRAM bits for error injection
- `cor_err` → verify correctable error detection
- Accessible via iJTAG SIB hierarchy

---

## 14. RTL File Reference

| # | File Path | Content |
|---|-----------|---------|
| 1 | `used_in_n1/rtl/targets/4x5/trinity_pkg.sv` | Package: tile_t enum (8 types), noc_axis_t, noc_direction_t, trinity_clock_routing_t struct, EnableDynamicRouting |
| 2 | `used_in_n1/rtl/trinity.sv` | Top module: trinity — ports, instances, generate blocks |
| 3 | `used_in_n1/mem_port/rtl/trinity.sv` | Top module variant (mem_port build) |
| 4 | `used_in_n1/legacy/no_mem_port/rtl/trinity.sv` | Top module variant (legacy, no mem_port) |
| 5 | `rtl/trinity_router.sv` | Router module (placeholder in N1B0) |
| 6 | `tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC interface package (4 modports) |
| 7 | `used_in_n1/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package — N1 integration variant |
| 8 | `used_in_n1/legacy/no_mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package — legacy variant |
| 9 | `used_in_n1/mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package — mem_port variant |
| 10 | `used_in_n1/make_enc/260223_no_srun/org/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package — encrypted build |

---

## Appendix: Search Metadata

| Round | Query | Results | Key Facts |
|-------|-------|---------|-----------|
| R1 | Chip-level (package, ports, hierarchy) | 20 | tile_t 8종, clock_routing_t, EnableDynamicRouting, trinity.sv ports/instances, DFX iJTAG |
| R2 | EDC topic | 8 | BIU APB4 + 5 IRQ, noc_sec_block_reg, serial_bus_repeater, intf_connector |
| R3 | NoC topic | 17 | 10 unique modules (repeaters, arbiter, SECDED, async FIFO, sync, harvest, timeout) |
| R4 | Overlay+SFPU+TDMA | 20 | TDMA HDD, SFPU HDD + lregs + instrn_resources, SMN repeater, FDS 106/41 + 68/41 |
| R5 | DFX+SRAM+EDC_pkg | 20 | tt_edc_pkg.sv 4 modports (5 variants), DFX HDD, iJTAG chain modules |
| **Total** | | **85** | **~40 unique facts** |

---

*End of Document — N1B0 NPU HDD v6a (Multi-topic Integrated)*