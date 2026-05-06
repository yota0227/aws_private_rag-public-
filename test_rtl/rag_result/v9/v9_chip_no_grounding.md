# Trinity N1B0 NPU — Hardware Design Document (HDD)

**Pipeline ID:** tt_20260221
**RAG Version:** v9
**Generated:** 2026-05-06
**Grounding Mode:** None (raw RAG output)

---

## 1. Overview

Trinity N1B0 is a Neural Processing Unit (NPU) SoC designed for AI/ML inference and training workloads. The chip is organized as a 4×5 2D mesh grid of heterogeneous tiles interconnected by a Network-on-Chip (NoC) fabric. The top-level module `trinity` instantiates compute tiles (Tensix), dispatch engines, NoC routers, NIU (Network Interface Units), and EDC (Error Detection and Correction) subsystems.

Key characteristics:
- 4×5 grid (20 nodes total)
- 12 Tensix compute tiles
- 4 NoC-to-AXI bridges (NIU)
- 2 Dispatch engines (East/West)
- EDC ring topology for error management
- Multi-clock domain architecture (AI, NoC, DM)

---

## 2. Package Constants and Grid

Source: `trinity_pkg.sv` (targets/4x5/)

| Parameter | Value | Description |
|-----------|-------|-------------|
| SizeX | 4 | Grid columns |
| SizeY | 5 | Grid rows |
| NumNodes | 20 | Total grid nodes (4×5) |
| NumTensix | 12 | Compute tiles |
| NumNoc2Axi | 4 | AXI bridge count |
| NumDispatch | 2 | Dispatch engines (East + West) |
| NumApbNodes | 4 | APB register nodes |
| NumDmComplexes | 14 | DM complex count |
| EnableDynamicRouting | 1'b1 | Dynamic routing enabled |
| TensixPerCluster | 4 | Tensix tiles per cluster |
| DMCoresPerCluster | 8 | DM cores per cluster |
| NumAxes | 2 | Routing axes (X, Y) |
| NumDirections | 2 | Routing directions per axis |

### Package Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| isEastEdge | `bit isEastEdge(int x)` [automatic] | Returns x == SizeX - 1 |

---

## 3. Top-Level Ports

Module `trinity` has **106 total ports** in the N1B0 variant:

| Category | Count | Key Signals |
|----------|-------|-------------|
| AXI_Interface | 39 | AXI slave/master bus signals |
| NoC_Clock_Reset | 2 | `i_noc_clk`, `i_noc_reset_n` |
| AI_Clock_Reset | 2 | `i_ai_clk [SizeX-1:0]`, `i_ai_reset_n [SizeX-1:0]` |
| Tensix_Reset | 1 | `i_tensix_reset_n [NumTensix-1:0]` |
| EDC_APB | 16 | EDC APB bus + IRQ outputs |
| DM_Clock_Reset | 3 | `i_dm_clk [SizeX-1:0]`, `i_dm_core_reset_n [NumDmComplexes-1:0][DMCoresPerCluster-1:0]`, `i_dm_uncore_reset_n [NumDmComplexes-1:0]` |
| APB_Register | 8 | `i_reg_psel`, `i_reg_paddr[31:0]`, `i_reg_penable`, `i_reg_pwrite`, `i_reg_pwdata[31:0]`, `o_reg_pready`, `o_reg_prdata[31:0]`, `o_reg_pslverr` |
| SFR_Memory_Config | 17 | SRAM configuration ports |
| PRTN_Power | 14 | Power partition chain signals |
| Other | 4 | Miscellaneous |

### Clock Architecture

| Clock | Width | Domain | Description |
|-------|-------|--------|-------------|
| i_axi_clk | 1 | AXI | AXI bus clock |
| i_noc_clk | 1 | NoC | Network-on-Chip clock |
| i_ai_clk | [SizeX-1:0] (4-bit) | AI | Per-column AI compute clock |
| i_dm_clk | [SizeX-1:0] (4-bit) | DM | Per-column data movement clock |

### Reset Architecture

| Reset | Width | Description |
|-------|-------|-------------|
| i_noc_reset_n | 1 | NoC domain reset |
| i_ai_reset_n | [SizeX-1:0] | Per-column AI reset |
| i_tensix_reset_n | [NumTensix-1:0] (12-bit) | Per-tile Tensix reset |
| i_dm_core_reset_n | [NumDmComplexes-1:0][DMCoresPerCluster-1:0] (14×8) | Per-core DM reset |
| i_dm_uncore_reset_n | [NumDmComplexes-1:0] (14-bit) | Per-complex DM uncore reset |
| i_edc_reset_n | 1 | EDC domain reset |

---

## 4. Module Hierarchy

```
trinity (top)
├── tt_tensix_with_l1 [×12]          — Compute tile with L1 cache
├── tt_dispatch_top_inst_east         — East dispatch engine (tt_dispatch_top_east)
├── tt_dispatch_top_inst_west         — West dispatch engine (tt_dispatch_top_west)
├── edc_direct_conn_nodes             — EDC direct connection (tt_edc1_intf_connector)
├── edc_loopback_conn_nodes           — EDC loopback connection (tt_edc1_intf_connector)
├── [NoC routers]                     — 2D mesh routing fabric
└── [NIU bridges]                     — NoC-to-AXI interface units
```

Note: `trinity_router` is NOT instantiated in N1B0 (EMPTY by design).

---

## 5. Compute Tile (Tensix)

Each Tensix tile (`tt_tensix_with_l1`) contains:
- FPU (Floating-Point Unit) — G-Tile and M-Tile variants
- SFPU (Sparse Floating-Point Unit) — register file with transpose/shift, instruction hazard detection
- TDMA (Time-Division Multiple Access) — DMA address generation, thread context, RTS/RTR pipeline
- L1 Cache
- DEST/SRCB register files

12 Tensix tiles are distributed across the 4×5 grid, organized in clusters of 4 (TensixPerCluster = 4).

---

## 6. Dispatch Engine

Two dispatch engines manage instruction distribution:
- **tt_dispatch_top_east** — East-side dispatch
- **tt_dispatch_top_west** — West-side dispatch

---

## 7. NoC Fabric

The NoC implements a 2D mesh topology with:
- **Routing algorithms:** DIM_ORDER, TENDRIL, DYNAMIC (EnableDynamicRouting = 1)
- **Repeaters:** `tt_noc_repeaters_cardinal` for inter-column signal regeneration
- **Arbitration:** `noc_arbiter_tree` — tree-based priority arbitration
- **Error protection:** `tt_noc_secded_chk_corr_116_10` — SECDED on 116-bit data with 10-bit check
- **CDC:** `tt_noc_sync3_pulse` — 3-stage pulse synchronizer between clock domains
- **Async FIFO:** `tt_upf_async_fifo` — write/read clocks at different frequencies
- **Skid buffer:** `tt_skid_buffer_new_assertion_off` — input/output decoupling
- **Harvest sync:** `tt_harvest_robust_sync` — robust multi-replication synchronizer

---

## 8. NIU (Network Interface Unit)

- **Timeout:** `tt_niu_mst_timeout` — configurable timeout with interrupt generation
- AXI bridge connecting NoC flit protocol to AXI4 bus
- Address Translation Table (ATT)
- SMN security enforcement

---

## 9. EDC (Error Detection and Correction)

### EDC APB Interface (16 ports)

| Signal | Direction | Width | Description |
|--------|-----------|-------|-------------|
| i_edc_reset_n | input | 1 | EDC reset |
| i_edc_apb_psel | input | 1 | APB select |
| i_edc_apb_penable | input | 1 | APB enable |
| i_edc_apb_pwrite | input | 1 | APB write |
| i_edc_apb_pprot | input | [2:0] | APB protection |
| i_edc_apb_paddr | input | [5:0] | APB address |
| i_edc_apb_pwdata | input | [31:0] | APB write data |
| i_edc_apb_pstrb | input | [3:0] | APB strobe |
| o_edc_apb_pready | output | 1 | APB ready |
| o_edc_apb_prdata | output | [31:0] | APB read data |
| o_edc_apb_pslverr | output | 1 | APB slave error |
| o_edc_fatal_err_irq | output | 1 | Fatal error IRQ |
| o_edc_crit_err_irq | output | 1 | Critical error IRQ |
| o_edc_cor_err_irq | output | 1 | Correctable error IRQ |
| o_edc_pkt_sent_irq | output | 1 | Packet sent IRQ |
| o_edc_pkt_rcvd_irq | output | 1 | Packet received IRQ |

### EDC Topology

- Ring topology with `tt_edc1_intf_connector` instances
- Direct connection nodes + loopback connection nodes
- Harvest bypass mechanism

---

## 10. Power Management (PRTN)

14 PRTN_Power ports implement a 4-column daisy-chain power partition:

| Signal | Direction | Width | Description |
|--------|-----------|-------|-------------|
| TIEL_DFT_MODESCAN | input | 1 | DFT mode scan tie-low |
| PRTNUN_FC2UN_DATA_IN | input | 1 | FC-to-UN data input |
| PRTNUN_FC2UN_READY_IN | input | 1 | FC-to-UN ready input |
| PRTNUN_FC2UN_CLK_IN | input | 1 | FC-to-UN clock input |
| PRTNUN_FC2UN_RSTN_IN | input | 1 | FC-to-UN reset input |
| PRTNUN_UN2FC_DATA_OUT | output | [3:0] | UN-to-FC data (4 columns) |
| PRTNUN_UN2FC_INTR_OUT | output | [3:0] | UN-to-FC interrupt (4 columns) |
| PRTNUN_FC2UN_DATA_OUT | output | [3:0] | FC-to-UN data chain (4 columns) |
| PRTNUN_FC2UN_READY_OUT | output | [3:0] | FC-to-UN ready chain (4 columns) |
| PRTNUN_FC2UN_CLK_OUT | output | [3:0] | FC-to-UN clock chain (4 columns) |
| PRTNUN_FC2UN_RSTN_OUT | output | [3:0] | FC-to-UN reset chain (4 columns) |
| PRTNUN_UN2FC_DATA_IN | input | [3:0] | UN-to-FC data return (4 columns) |
| PRTNUN_UN2FC_INTR_IN | input | [3:0] | UN-to-FC interrupt return (4 columns) |
| ISO_EN | input | [11:0] | Power island isolation enable (12 tiles) |

---

## 11. RTL File Reference

| File | Description |
|------|-------------|
| `rtl/trinity.sv` | Top-level module |
| `rtl/targets/4x5/trinity_pkg.sv` | Package constants (4×5 configuration) |
| `used_in_n1/rtl/trinity.sv` | N1B0 variant (106 ports, PRTN + SFR) |
| `used_in_n1/mem_port/rtl/trinity.sv` | N1B0 with memory port variant |

---

*Generated from RAG v9 pipeline (tt_20260221). No grounding tags applied.*
