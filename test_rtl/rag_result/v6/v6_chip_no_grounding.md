# N1B0 NPU — Hardware Design Document

> **Pipeline ID:** tt_20260221 | **Version:** v6 (No Grounding) | **RAG:** v4.1 + Package Parser
> **Generated:** 2026-04-28

---

## 1. Overview

N1B0 is the Trinity NPU integrated into the N1 SoC. It is a tile mesh containing Tensix compute tiles, AXI bridge tiles (NIU/Router), dispatch tiles, and router placeholder tiles, connected by a 2D NoC fabric.

**KB-confirmed top module:** `trinity` (from `trinity.sv`)

**Key instances:** `tt_tensix_with_l1`, `tt_dispatch_top_east`, `tt_dispatch_top_west`, `tt_edc1_intf_connector`

**Key package constants (from `trinity_pkg.sv`):**
- `EnableDynamicRouting = 1'b1`
- `tile_t` enum: 8 tile types (TENSIX, NOC2AXI_NE/NW_OPT, NOC2AXI_ROUTER_NE/NW_OPT, DISPATCH_E/W, ROUTER)
- `trinity_clock_routing_t` struct: 8 clock/reset fields

---

## 2. Package Constants and Grid

**File:** `used_in_n1/rtl/targets/4x5/trinity_pkg.sv`

### 2.1 Tile Type Enum (`tile_t`, 3-bit)

| Value | Name | Position |
|-------|------|----------|
| 3'd0 | `TENSIX` | Y=0..2, X=0..3 (12 tiles) |
| 3'd1 | `NOC2AXI_NE_OPT` | (X=0, Y=4) |
| 3'd2 | `NOC2AXI_ROUTER_NE_OPT` | (X=1, Y=4+Y=3) |
| 3'd3 | `NOC2AXI_ROUTER_NW_OPT` | (X=2, Y=4+Y=3) |
| 3'd4 | `NOC2AXI_NW_OPT` | (X=3, Y=4) |
| 3'd5 | `DISPATCH_E` | (X=0, Y=3) |
| 3'd6 | `DISPATCH_W` | (X=3, Y=3) |
| 3'd7 | `ROUTER` | (X=1,2, Y=3) — **placeholder, empty by design** |

### 2.2 Other Enums

| Enum | Members |
|------|---------|
| `noc_axis_t` | Y_AXIS=1'b0, X_AXIS=1'b1 |
| `noc_direction_t` | POSITIVE=1'b0, NEGATIVE=1'b1 |

### 2.3 Grid Layout

```
         X=0              X=1                   X=2                  X=3
        ┌────────────┬─────────────────────────────────────┬────────────┐
Y=4:    │ NOC2AXI_   │ NOC2AXI_ROUTER_NE_OPT              │ NOC2AXI_   │
        │ NE_OPT     │              NOC2AXI_ROUTER_NW_OPT  │ NW_OPT     │
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

**Module:** `trinity` (from `trinity.sv`)

| Port | Width | Description |
|------|-------|-------------|
| `i_axi_clk` | 1 | AXI clock |
| `i_noc_clk` | 1 | NoC fabric clock |
| `i_noc_reset_n` | 1 | NoC active-low reset |
| `i_ai_clk` | [SizeX-1:0] | Per-column AI compute clock |
| `i_ai_reset_n` | [SizeX-1:0] | Per-column AI reset |
| `i_tensix_reset_n` | [NumTensix-1:0] | Per-tile Tensix reset |
| `i_edc_reset_n` | 1 | EDC reset |

---

## 4. Module Hierarchy

```
trinity (top)
├── tt_tensix_with_l1 [×12]               — Tensix (Y=0..2)
│   ├── tt_sfpu_lregs                     — SFPU register file
│   ├── tt_sfpu_instrn_resources_used     — Instruction hazard tracker
│   └── tt_tdma_thread_context            — Multi-channel DMA
├── tt_dispatch_top_east [×1]              — DISPATCH_E (X=0, Y=3)
├── tt_dispatch_top_west [×1]              — DISPATCH_W (X=3, Y=3)
├── trinity_noc2axi_ne_opt [×1]            — Corner NIU (X=0, Y=4)
├── trinity_noc2axi_router_ne_opt [×1]     — NIU+Router (X=1, Y=4+3)
├── trinity_noc2axi_router_nw_opt [×1]     — NIU+Router (X=2, Y=4+3)
├── trinity_noc2axi_nw_opt [×1]            — Corner NIU (X=3, Y=4)
├── [ROUTER placeholder] [×2]              — EMPTY (X=1,2, Y=3)
├── tt_edc1_intf_connector (direct + loopback)
├── tt_edc1_serial_bus_repeater [×N]
├── tt_edc1_biu_soc_apb4_wrap → edc1_biu_soc_apb4_inner
├── tt_edc1_noc_sec_block_reg → edc1_noc_sec_block_reg_inner
├── tt_clkdiv2 / tt_clkbuf / tt_clkgater [×N]
└── tt_smn_clkdiv / tt_smn_repeater_struct
```

---

## 5. Compute Tile — Tensix

- `tt_sfpu_lregs`: Register file, transpose/shift, parity error reporting
- `tt_sfpu_instrn_resources_used`: R/W hazard detection, stall conditions
- `tt_tdma_thread_context`: Address/control gen for multi-channel DMA

---

## 6. Dispatch Engine

- `tt_dispatch_top_east` (DISPATCH_E, X=0, Y=3)
- `tt_dispatch_top_west` (DISPATCH_W, X=3, Y=3)

---

## 7. NoC Fabric

- `EnableDynamicRouting = 1'b1`
- `noc_axis_t`: Y_AXIS / X_AXIS
- `noc_direction_t`: POSITIVE / NEGATIVE
- Modules: repeaters, arbiter_tree, SECDED, async FIFO, sync3_pulse, harvest_robust_sync, niu_mst_timeout

---

## 8. NIU — AXI Bridge Tiles

| Tile | Type | Position |
|------|------|----------|
| `trinity_noc2axi_ne_opt` | Corner NIU | (X=0, Y=4) |
| `trinity_noc2axi_router_ne_opt` | NIU+Router | (X=1, Y=4+3) |
| `trinity_noc2axi_router_nw_opt` | NIU+Router | (X=2, Y=4+3) |
| `trinity_noc2axi_nw_opt` | Corner NIU | (X=3, Y=4) |

---

## 9. Clock Architecture

### `trinity_clock_routing_t` struct

| Field | Description |
|-------|-------------|
| `ai_clk` | AI compute clock |
| `noc_clk` | NoC fabric clock |
| `dm_clk` | Data movement clock |
| `ai_clk_reset_n` | AI clock reset |
| `noc_clk_reset_n` | NoC clock reset |
| `dm_uncore_clk_reset_n` | DM uncore reset |
| `tensix_reset_n` | Per-tile Tensix reset |
| `power_good` | Power good signal |

---

## 10. Reset Architecture

- `i_noc_reset_n` — Global NoC reset
- `i_ai_reset_n[SizeX-1:0]` — Per-column AI reset
- `i_tensix_reset_n[NumTensix-1:0]` — Per-tile Tensix reset
- `trinity_clock_routing_t.power_good` — Power good

---

## 11. EDC

- `tt_edc_pkg.sv`: 4 modports (ingress/egress/edc_node/sram)
- `tt_edc1_biu_soc_apb4_wrap`: APB4 + 5 IRQs (fatal/crit/cor_err, pkt_sent/rcvd)
- `tt_edc1_noc_sec_block_reg`: NoC security config

---

## 12. SRAM Inventory

| SRAM | Size | Usage |
|------|------|-------|
| `tt_mem_wrap_32x1024_2p_nomask` | 32b × 1024, 2P | ATT routing translation |

---

## 13. DFX

- `noc_routing_translation_selftest` — ATT BIST
- `err_inj_vec` / `cor_err` — EDC error injection/detection

---

## 14. RTL File Reference

| File | Content |
|------|---------|
| `used_in_n1/rtl/targets/4x5/trinity_pkg.sv` | tile_t enum, clock struct, EnableDynamicRouting |
| `used_in_n1/rtl/trinity.sv` | Top module: trinity |
| `tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC interface (4 modports) |

---

*End of Document*