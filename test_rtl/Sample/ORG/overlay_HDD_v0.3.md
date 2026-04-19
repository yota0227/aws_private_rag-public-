# Trinity Overlay — Hardware Design Document

**Document:** overlay_HDD_v0.3.md
**Chip:** Trinity (4×5 NoC Mesh)
**RTL Snapshot:** 20260221
**Primary Sources:** `tt_overlay_wrapper.sv`, `tt_overlay_pkg.sv`, `tt_overlay_noc_wrap.sv`, `tt_overlay_smn_wrapper.sv`, `tt_overlay_clock_reset_ctrl.sv`, `tt_overlay_edc_wrapper.sv`, `tt_overlay_noc_niu_router.sv`, `tt_idma_wrapper.sv`, `tt_idma_pkg.sv`, `tt_rocc_accel.sv`, `tt_rocc_pkg.sv`, `tt_dispatch_engine.sv`, `tt_fds_wrapper.sv`, `tt_fds.sv`, `trinity_hierarchy.csv`
**Audience:** Verification Engineers · Software Engineers · Hardware Engineers

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v0.1 | 2026-03-17 | (RTL-derived) | Initial release |
| v0.2 | 2026-03-17 | (RTL-derived) | Expanded: L1 access path, iDMA usage guide, ROCC architecture, Dispatch Engine details, SMN detail, FDS detail, Tensix access |
| v0.3 | 2026-03-17 | (RTL-derived) | ASCII block diagrams for every section; additional HW-level detail from hierarchy CSV and internal RTL wire types |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Trinity Grid and Tile Placement](#2-trinity-grid-and-tile-placement)
3. [Feature Summary](#3-feature-summary)
4. [Overall Architecture — Top-level Block Diagram](#4-overall-architecture--top-level-block-diagram)
5. [Sub-module Hierarchy](#5-sub-module-hierarchy)
6. [Feature Details](#6-feature-details)
   - 6.1 [Clock and Reset Architecture](#61-clock-and-reset-architecture)
   - 6.2 [NoC Interface — NIU and Router](#62-noc-interface--niu-and-router)
   - 6.3 [Cluster CPU Subsystem](#63-cluster-cpu-subsystem)
   - 6.4 [L1 Cache — Access Path and Methods](#64-l1-cache--access-path-and-methods)
   - 6.5 [iDMA Engine](#65-idma-engine)
   - 6.6 [ROCC Accelerator](#66-rocc-accelerator)
   - 6.7 [LLK (Low-Latency Kernel) Interface](#67-llk-low-latency-kernel-interface)
   - 6.8 [Dispatch Engine](#68-dispatch-engine)
   - 6.9 [SMN (System Maintenance Network)](#69-smn-system-maintenance-network)
   - 6.10 [EDC (Error Detection and Correction)](#610-edc-error-detection-and-correction)
   - 6.11 [FDS (Frequency / Droop Sensor)](#611-fds-frequency--droop-sensor)
   - 6.12 [Tensix and L1 Access from the Overlay](#612-tensix-and-l1-access-from-the-overlay)
   - 6.13 [Harvest Support](#613-harvest-support)
   - 6.14 [Register Access via APB / EDC Bridge](#614-register-access-via-apb--edc-bridge)
   - 6.15 [iJTAG / DFD Interface](#615-ijtag--dfd-interface)
7. [Control Path: Processor to Data Bus](#7-control-path-processor-to-data-bus)
8. [Key Parameters](#8-key-parameters)
9. [Clock and Reset Summary](#9-clock-and-reset-summary)
10. [APB Register Interfaces](#10-apb-register-interfaces)
11. [Worked Example: CPU Issues a NoC Write](#11-worked-example-cpu-issues-a-noc-write)
12. [Verification Checklist](#12-verification-checklist)
13. [Key RTL File Index](#13-key-rtl-file-index)

---

## 1. Overview

The **Overlay** is the per-tile infrastructure hub of the Trinity chip. It sits alongside each Tensix compute tile and the Dispatch Engine tiles, providing the connective tissue between the cluster CPUs, tensor compute cores, L1 cache, NoC mesh, and system management networks.

Every Tensix tile (Y=1–4, X=0–3) instantiates `tt_overlay_wrapper`. The two Dispatch Engine tiles (Y=0, X=1/X=2) instantiate `tt_disp_eng_overlay_wrapper`, which is a variant of the same overlay with `IS_DISPATCH=1`, `HAS_SMN_INST=0`, and SMN direction ports swapped from N↔S to E↔S.

The overlay is **not** a simple pass-through: it actively manages clocks, resets, register access, memory arbitration, and inter-tile communication for every cycle of operation.

---

## 2. Trinity Grid and Tile Placement

```
        X=0              X=1              X=2              X=3
      ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
Y=0   │NOC2AXI W │    │DISPATCH W│    │DISPATCH E│    │NOC2AXI E │
      │(DRAM AXI)│    │IS_DISP=1 │    │IS_DISP=1 │    │(DRAM AXI)│
      └──────────┘    └──────────┘    └──────────┘    └──────────┘
      ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
Y=1   │ TENSIX   │    │ TENSIX   │    │ TENSIX   │    │ TENSIX   │
      │+overlay  │    │+overlay  │    │+overlay  │    │+overlay  │
      └──────────┘    └──────────┘    └──────────┘    └──────────┘
Y=2   │ TENSIX   │    │ TENSIX   │    │ TENSIX   │    │ TENSIX   │
      │+overlay  │ ...                                │+overlay  │
Y=3   │ TENSIX   │                                    │ TENSIX   │
Y=4   │ TENSIX   │    │ TENSIX   │    │ TENSIX   │    │ TENSIX   │
      └──────────┘    └──────────┘    └──────────┘    └──────────┘

SMN ring: N↔S through Tensix tiles (Y=1–4); E↔S at Dispatch tiles (Y=0,X=1/2)
NoC mesh: 4-port (N/S/E/W) at every tile
EDC ring: continuous serial loop through all tiles column-by-column
```

Overlay instantiation per tile:
- **Tensix tile** (`gen_tensix_neo[Y][X]`): `tt_tensix_with_l1` → `overlay_noc_wrap` → `overlay_noc_niu_router` → `neo_overlay_wrapper` → `overlay_wrapper`
- **Dispatch tile**: `tt_dispatch_top_east/west` → `tt_dispatch_engine` → `disp_eng_overlay_wrapper` (DISPATCH_INST=1, HAS_SMN_INST=0)

---

## 3. Feature Summary

| Feature | Hardware Module | Key Parameters |
|---------|----------------|----------------|
| Multi-clock / reset | `tt_overlay_clock_reset_ctrl` | 5 clock domains, 16-cycle reset count |
| NoC NIU + Router | `tt_overlay_noc_niu_router` | 4-port mesh, 5 VC buffers (64×2048 SRAM each) |
| Cluster CPUs | `tt_overlay_cpu_wrapper` | 8× RISC-V, 64 IRQs, 52-bit reset vector |
| L1 cache | `tt_t6_l1_partition` / `tt_t6_l1_wrap2` | 1024×128 per sub-bank; RW/RD/WR flex-client ports |
| iDMA | `tt_idma_wrapper` | 24 clients, 2 back-ends, 2D S/G, 32 TIDs, FIFO=42 |
| ROCC | `tt_rocc_accel` ×8 | CUSTOM_0–3 opcodes, per-hart, 2× parallel addr gen |
| LLK counters | `tt_overlay_tile_counters_with_comparators` | 4 channels × 4 cores |
| Dispatch link | FDS IS_DISPATCH wiring | `de_to_t6_t` / `t6_to_de_t` sideband structs |
| SMN | `tt_overlay_smn_wrapper` | AXI4-Lite daisy-chain, APB master output |
| EDC | `tt_overlay_edc_wrapper` | EDC1 serial bus, harvest demux, security controller |
| FDS | `tt_fds_wrapper` / `tt_fds` | 3 droop sources, 16 IRQ groups, noc→core CDC FIFO |
| Harvest | `tt_overlay_wrapper_harvest_trinity` | `i_overlay_harvested`, `i_remap_x_size` |
| APB register bus | `tt_overlay_wrapper_reg_logic` | 26-bit addr, 32-bit data, 7 sub-buses |
| iJTAG / DFD | pass-through ports | `i_ijtag_tck_to_dfd`, `o_ijtag_so_from_dfd` |

---

## 4. Overall Architecture — Top-level Block Diagram

```
                          ╔═══════════════════════════════════════════════════════════╗
                          ║                  tt_overlay_wrapper                       ║
                          ║                                                           ║
 Ext Clocks / Resets      ║  ┌────────────────────────────────────────────────────┐  ║
 i_core_clk    ──────────►║  │             tt_overlay_clock_reset_ctrl            │  ║
 i_aiclk       ──────────►║  │  ┌─────────┐ ┌──────────┐ ┌──────────────────────┐│  ║
 i_nocclk      ──────────►║  │  │ core_clk│ │ ai_clk   │ │ noc_clk  / ref_clk   ││  ║
 i_ref_clk     ──────────►║  │  │  gate   │ │  gate    │ │   gate / PLL-ref     ││  ║
 i_*_reset_n   ──────────►║  │  └────┬────┘ └────┬─────┘ └──────────┬───────────┘│  ║
                          ║  └───────┼────────────┼──────────────────┼────────────┘  ║
                          ║          │core         │ai                │noc            ║
                          ║  ┌───────▼──────────────────────────────────────────┐    ║
 SMN ring                 ║  │             tt_overlay_cpu_wrapper                │    ║
 i_smn_req_n_s ──────────►║  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ... │    ║
 o_smn_req_n_s ◄──────────║  │  │HART0│ │HART1│ │HART2│ │HART3│ │HART4│     │    ║
                          ║  │  └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘     │    ║
                          ║  │     └───────┴───────┴───────┴───────┘         │    ║
                          ║  │                 ROCC (×8 per hart)              │    ║
                          ║  └────────────────────────┬─────────────────────────┘    ║
                          ║                           │ OBI / TileLink               ║
                          ║  ┌────────────────────────▼─────────────────────────┐    ║
 APB reg bus              ║  │     tt_overlay_memory_wrapper  (L1 Banks)         │    ║
 (EDC bridge) ◄──────────►║  │  ┌────────────────────────────────────────────┐  │    ║
                          ║  │  │  tt_t6_l1_partition                         │  │    ║
                          ║  │  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐      │  │    ║
                          ║  │  │  │Bank 0│ │Bank 1│ │Bank 2│ │Bank 3│ ...  │  │    ║
                          ║  │  │  │1024×│ │1024×│ │1024×│ │1024×│       │  │    ║
                          ║  │  │  │128b  │ │128b  │ │128b  │ │128b  │       │  │    ║
                          ║  │  │  └──────┘ └──────┘ └──────┘ └──────┘      │  │    ║
                          ║  │  └──────────────────────────────────────────┘  │    ║
                          ║  └────────────────────────┬──────────────────────┘    ║
                          ║                           │ flex-client (RW/RD/WR)     ║
                          ║  ┌────────────────────────▼─────────────────────────┐  ║
 NoC mesh ports           ║  │      tt_overlay_noc_wrap / noc_niu_router         │  ║
 N/S/E/W flits ◄─────────►║  │  ┌──────────────────────────────────────────┐    │  ║
                          ║  │  │  NIU (inject / eject)                     │    │  ║
                          ║  │  │  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐      │    │  ║
                          ║  │  │  │VC0│  │VC1│  │VC2│  │VC3│  │VC4│      │    │  ║
                          ║  │  │  │64×│  │64×│  │64×│  │64×│  │64×│      │    │  ║
                          ║  │  │  │2048│ │2048│ │2048│ │2048│ │2048│     │    │  ║
                          ║  │  │  └───┘  └───┘  └───┘  └───┘  └───┘      │    │  ║
                          ║  │  │  Router (DOR X-first, N/S/E/W/local)      │    │  ║
                          ║  │  └──────────────────────────────────────────┘    │  ║
                          ║  └──────────────────────────────────────────────────┘  ║
                          ║                                                           ║
 iDMA flit                ║  ┌─────────────────┐    ┌─────────────────────────────┐  ║
 (NoC inject) ◄──────────►║  │  tt_idma_wrapper│    │  tt_fds_wrapper             │  ║
                          ║  │  24 clients→2 BE│    │  3 droop sources → 16 IRQs  │  ║
                          ║  └─────────────────┘    └─────────────────────────────┘  ║
                          ║                                                           ║
 DE sideband              ║  ┌─────────────────────────────────────────────────────┐  ║
 o_de_to_t6[1:0] ◄───────►║  │  Dispatch sideband (de_to_t6_t / t6_to_de_t)       │  ║
 i_t6_to_de      ◄───────►║  └─────────────────────────────────────────────────────┘  ║
                          ║                                                           ║
 EDC ring                 ║  ┌─────────────────────────────────────────────────────┐  ║
 i_edc_ingress ──────────►║  │  tt_overlay_edc_wrapper                             │  ║
 o_edc_egress  ◄──────────║  │  (in/out/loopback repeaters + harvest demux)         │  ║
                          ║  └─────────────────────────────────────────────────────┘  ║
                          ╚═══════════════════════════════════════════════════════════╝
```

---

## 5. Sub-module Hierarchy

Full instantiation path (from `trinity_hierarchy.csv`):

```
trinity
└── gen_tensix_neo[Y][X]
    └── tt_tensix_with_l1
        └── overlay_noc_wrap
            └── overlay_noc_niu_router
                └── neo_overlay_wrapper
                    └── overlay_wrapper          ← tt_overlay_wrapper
                        ├── tt_overlay_clock_reset_ctrl
                        ├── tt_overlay_smn_wrapper
                        │    └── tt_smn                    (HAS_SMN_INST=1)
                        ├── tt_overlay_edc_wrapper
                        │    ├── tt_edc1_serial_bus_repeater  (×EDC_IN_REP_NUM)
                        │    ├── tt_edc1_serial_bus_demux     (harvest bypass)
                        │    └── tt_edc1_noc_sec_controller   (security)
                        ├── tt_overlay_noc_wrap
                        │    └── tt_overlay_noc_niu_router
                        │         └── tt_trinity_noc_niu_router_inst
                        │              └── noc_niu_router_inst
                        │                   ├── niu
                        │                   └── router
                        │                        └── tt_mem_wrap_64x2048_2p_nomask  (×5 VCs)
                        ├── tt_overlay_cpu_wrapper
                        │    └── quasar_cpu_cluster
                        │         └── hart[0..7]
                        ├── tt_overlay_memory_wrapper
                        │    └── tt_t6_l1_partition
                        │         └── u_l1w2 (tt_t6_l1_wrap2)
                        │              └── u_l1_mem_wrap
                        │                   └── tt_mem_wrap_1024x128_sp  (per bank)
                        ├── tt_overlay_flex_client_csr_wrapper
                        ├── tt_overlay_axi_to_l1_if
                        ├── tt_overlay_apb_to_l1_if
                        ├── tt_overlay_noc_snoop_tl_master
                        ├── tt_idma_wrapper
                        │    ├── tt_idma_cmd_buffer_frontend    (24→2 arbiter)
                        │    └── tt_idma_backend_r_init_rw_obi_top  (×IDMA_NUM_BE=2)
                        ├── tt_rocc_accel  [×8, one per hart]
                        │    ├── tt_rocc_cmd_buf
                        │    ├── tt_rocc_address_gen            (×PARALLEL_ADDRESS_GEN=2)
                        │    ├── tt_rocc_context_switch
                        │    └── tt_rocc_interrupt_event
                        ├── tt_overlay_tile_counters_with_comparators
                        ├── tt_fds_wrapper
                        │    ├── tt_fds_delay_model
                        │    └── tt_fds
                        │         └── tt_fds_regfile
                        ├── tt_overlay_edc_apb_bridge
                        ├── tt_overlay_wrapper_reg_logic
                        ├── tt_overlay_reg_xbar_slave_decode
                        ├── tt_overlay_flit_vc_arb
                        └── tt_overlay_wrapper_harvest_trinity

Dispatch tile:
trinity → tt_dispatch_top_east/west
    └── tt_dispatch_engine
         └── disp_eng_overlay_wrapper   (DISPATCH_INST=1, HAS_SMN_INST=0)
              └── tt_disp_eng_l1_partition
```

---

## 6. Feature Details

### 6.1 Clock and Reset Architecture

**Hardware:** `tt_overlay_clock_reset_ctrl`

#### Block Diagram

```
External clock/reset inputs
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│              tt_overlay_clock_reset_ctrl                   │
│                                                           │
│  i_core_clk ──► [SMN-controlled gate] ──► o_core_clk     │
│  i_aiclk    ──► [SMN-controlled gate] ──► o_aiclk        │
│  i_aiclk    ──► [always-on path]      ──► o_ai_aon_clk   │
│  i_nocclk   ──► [SMN-controlled gate] ──► o_nocclk       │
│  i_ref_clk  ──► [direct / PLL ref]   ──► o_ref_clk       │
│                                                           │
│  i_core_clk_reset_n_pre_sync[7:0]                        │
│       ──► [16-cycle sync, per hart] ──► o_hart_reset_n[7:0]│
│                                                           │
│  SMN inputs:                                              │
│  i_smn_core_clk_en  ──► core_clk gate enable             │
│  i_smn_ai_clk_en    ──► ai_clk gate enable               │
│  i_smn_noc_clk_en   ──► noc_clk gate enable              │
│  i_smn_reset_n[7:0] ──► per-hart reset override          │
└───────────────────────────────────────────────────────────┘
```

**Clock domain matrix:**

| Domain | Source | Gated by SMN | Users |
|--------|--------|-------------|-------|
| `core_clk` | `i_core_clk` | Yes | CPU pipeline, L1, iDMA frontend, ROCC |
| `ai_clk` | `i_aiclk` | Yes | Tensix matrix engine (FPU tiles) |
| `ai_aon_clk` | `i_aiclk` | No | Always-on uncore registers |
| `noc_clk` | `i_nocclk` | Yes | NoC flit datapath, iDMA backend |
| `ref_clk` | `i_ref_clk` | No | PLL reference, reset sync counters |

Reset synchronizer constants:
```systemverilog
localparam int unsigned REF_CLK_RESET_CYCLES    = 16;
localparam int unsigned CORE_CLK_RESET_CYCLES   = 16;
localparam int unsigned UNCORE_CLK_RESET_CYCLES = 16;
localparam int unsigned AI_CLK_RESET_CYCLES     = 16;
```

Each hart has its own reset line `o_hart_reset_n[i]`, allowing individual RISC-V core reset without affecting neighbors. The SMN can assert/deassert these independently.

---

### 6.2 NoC Interface — NIU and Router

**Hardware:** `tt_overlay_noc_wrap` → `tt_overlay_noc_niu_router` → `tt_trinity_noc_niu_router_inst`

#### Block Diagram

```
        N neighbor                       S neighbor
  i_flit_in_req_N[FLIT_W-1:0]    i_flit_in_req_S[FLIT_W-1:0]
  o_flit_out_req_N[FLIT_W-1:0]   o_flit_out_req_S[FLIT_W-1:0]
            │ ▲                             │ ▲
            ▼ │  [flit repeaters: N↔S]      ▼ │
   ┌─────────────────────────────────────────────────┐
   │          tt_overlay_noc_niu_router               │
   │                                                  │
   │  ┌──────────────────────────────────────────┐   │
   │  │                 Router                    │   │
   │  │                                           │   │
   │  │  VC input buffers (per direction):        │   │
   │  │  ┌─────────────────────────────────────┐ │   │
   │  │  │  North port: tt_mem_wrap_64x2048_2p  │ │   │
   │  │  │  South port: tt_mem_wrap_64x2048_2p  │ │   │
   │  │  │  East  port: tt_mem_wrap_64x2048_2p  │ │   │
   │  │  │  West  port: tt_mem_wrap_64x2048_2p  │ │   │
   │  │  │  NIU   port: tt_mem_wrap_64x2048_2p  │ │   │
   │  │  └─────────────────────────────────────┘ │   │
   │  │                                           │   │
   │  │  Routing algorithm:                       │   │
   │  │    - DOR (Dimension-Order Routing) X-first│   │
   │  │    - Tendril extensions for Dispatch edge │   │
   │  │    - ATT table for endpoint remapping     │   │
   │  └─────────────────┬─────────────────────────┘   │
   │                    │ local inject/eject            │
   │  ┌─────────────────▼─────────────────────────┐   │
   │  │               NIU                          │   │
   │  │  inject: CPU→NoC flit arbiter              │   │
   │  │  eject:  NoC→CPU snoop master              │   │
   │  │  node_id: i_local_nodeid_x/y               │   │
   │  └──────────────────────────────────────────┘    │
   └─────────────────────────────────────────────────┘
            │ ▲                             │ ▲
            ▼ │                             ▼ │
   i/o_flit_in/out_req_E              i/o_flit_in/out_req_W
        E neighbor                        W neighbor
```

**VC buffer physical spec** (from `trinity_hierarchy.csv`):
- Module: `tt_mem_wrap_64x2048_2p_nomask_router_input_port_selftest`
- Depth × Width: 64 entries × 2048-bit
- Count: 5 (one per direction: N, S, E, W, NIU)

**Key parameters:**
```systemverilog
NOC_FLIT_REPEATERS_NORTH_TO_SOUTH  // parameterized per placement
NOC_FLIT_REPEATERS_SOUTH_TO_NORTH
// Node ID forwarded to L1 partition and adjacent tiles
o_local_nodeid_x_to_t6_l1_partition
o_nxt_node_id_x, o_nxt_node_id_y
```

---

### 6.3 Cluster CPU Subsystem

**Hardware:** `tt_overlay_cpu_wrapper` → `quasar_cpu_cluster`

#### Block Diagram

```
  i_core_clk (gated)        i_hart_reset_n[7:0]
         │                         │
         ▼                         ▼
┌────────────────────────────────────────────────────────┐
│                 tt_overlay_cpu_wrapper                  │
│                                                        │
│  ┌────────┐ ┌────────┐ ┌────────┐ ... ┌────────┐      │
│  │ HART 0 │ │ HART 1 │ │ HART 2 │     │ HART 7 │      │
│  │ RV64GC │ │ RV64GC │ │ RV64GC │     │ RV64GC │      │
│  │ +icache│ │ +icache│ │ +icache│     │ +icache│      │
│  │ +dcache│ │ +dcache│ │ +dcache│     │ +dcache│      │
│  └───┬────┘ └───┬────┘ └───┬────┘     └───┬────┘      │
│      │          │          │              │            │
│      └──────────┴────────────────────────┘            │
│                            │                           │
│                    ┌───────▼──────────┐                │
│                    │  ROCC interface   │                │
│                    │  (per-hart cmd/  │                │
│                    │   resp bus)      │                │
│                    └───────┬──────────┘                │
│                            │                           │
│    ┌───────────────────────▼──────────────────────┐   │
│    │     APB register buses (outbound)             │   │
│    │  cluster_ctrl_apb  smn_mst_apb  edc_mst_apb  │   │
│    │  overlay_mst_apb   t6l1_slv_apb              │   │
│    └──────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────┘

Constants:
  NUM_CLUSTER_CPUS      = 8
  NUM_INTERRUPTS        = 64  (56 internal + 8 external)
  RESET_VECTOR_WIDTH    = 52
  NUM_RW_SUB_PORTS_CPU  = 4   (L1 RW sub-ports per CPU)
```

Each CPU hart is a standard RISC-V (Quasar core), RV64GC ISA, with per-hart:
- I-cache → L1 instruction port
- D-cache → L1 RW flex-client port
- ROCC co-processor interface (CUSTOM_0–3 opcodes)
- 64 interrupt lines (PLIC-mapped)

---

### 6.4 L1 Cache — Access Path and Methods

**Hardware:** `tt_overlay_memory_wrapper` → `tt_t6_l1_partition` → `tt_t6_l1_wrap2` → `tt_mem_wrap_1024x128_sp`

#### Physical SRAM Macro

```
  tt_t6_l1_partition
  └── u_l1w2 (tt_t6_l1_wrap2)
       └── u_l1_mem_wrap
            └── tt_mem_wrap_1024x128_sp   ← one per sub-bank
                  depth  = 1024 entries
                  width  = 128 bits (16 bytes)
                  ports  = single-port (SP)
```

Total L1 size = num_banks × 1024 × 16 bytes = configurable via `L1_CFG`.

#### Access Pipeline

```
                  ┌────────────────────────────────────────────────────┐
                  │               L1 Access Pipeline                    │
                  │                                                      │
  Request phase:  │  Requester → pre_sbank_intf (addr decode/pre-arb)   │
                  │                    │                                 │
                  │                    ▼                                 │
  Arbitration:    │           arb_intf (winner selected,                │
                  │                bank assigned, tag check)             │
                  │                    │                                 │
                  │                    ▼                                 │
  SRAM access:    │           tt_mem_wrap_1024x128_sp                   │
                  │             (1-cycle latency, pipelined)             │
                  │                    │                                 │
  Response:       │           resp_data returned to requester            │
                  └────────────────────────────────────────────────────┘
```

#### All Access Methods and Their Hardware Paths

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        L1 Access Port Map                                │
│                                                                          │
│  RW ports (bidirectional)                                                │
│  ┌──────────────────────────────────────────────────────┐               │
│  │ CPU hart[0..7] D-cache                               │               │
│  │   → o_t6_l1_pre_sbank_rw_intf[0..CPU×4-1]           │               │
│  │   → o_t6_l1_arb_rw_intf[N]   (post-arb)             │               │
│  │                                                      │               │
│  │ T6L1 Debug (APB→L1 bridge)                           │               │
│  │   → tt_overlay_apb_to_l1_if → arb_rw_intf           │               │
│  │                                                      │               │
│  │ NoC Atomic (read-modify-write from NoC)              │               │
│  │   → i_noc_flex_rw_intf_atomic_send                   │               │
│  │   → tt_overlay_noc_snoop_tl_master → arb_rw_intf    │               │
│  └──────────────────────────────────────────────────────┘               │
│                                                                          │
│  RD ports (read-only)                                                    │
│  ┌──────────────────────────────────────────────────────┐               │
│  │ iDMA back-end reads                                  │               │
│  │   → tt_idma_backend_r_init_rw_obi_top                │               │
│  │   → OBI memory interface                             │               │
│  │   → o_t6_l1_arb_rd_intf[0..IDMA_NUM_BE-1]           │               │
│  └──────────────────────────────────────────────────────┘               │
│                                                                          │
│  WR ports (write-only)                                                   │
│  ┌──────────────────────────────────────────────────────┐               │
│  │ NoC inbound snoop (remote tile writes this L1)       │               │
│  │   → NIU eject → tt_overlay_noc_snoop_tl_master      │               │
│  │   → TileLink WR port → o_t6_l1_arb_wr_intf[N]       │               │
│  │                                                      │               │
│  │ AXI inbound (from NOC2AXI bridge or JTAG)            │               │
│  │   → tt_overlay_axi_to_l1_if → arb_wr_intf           │               │
│  └──────────────────────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────────────────────┘
```

**Sub-port counts:**
```systemverilog
NUM_RW_SUB_PORTS_CPU        = 4   // CPU load/store (4 of 8 harts share one RW port)
NUM_RW_SUB_PORTS_T6L1_DEBUG = 1   // APB debug read/write
NUM_RW_SUB_PORTS_NOC_ATOMIC = 1   // NoC atomic RMW
NUM_RW_SUB_PORTS_OVERLAY    = 5   // aggregate overlay sub-ports on single RW
```

**SW init sequence (L1 must be scrubbed before first use):**
1. Assert per-hart reset (`o_hart_reset_n[i] = 0`)
2. Enable L1 clock via SMN clock enable
3. Scrub all L1 banks with ECC-clean writes using APB→L1 bridge (`tt_overlay_apb_to_l1_if`)
4. Set `L1_PHASE_ROOT` configuration register
5. Deassert hart reset

---

### 6.5 iDMA Engine

**Hardware:** `tt_idma_wrapper` → `tt_idma_cmd_buffer_frontend` + `tt_idma_backend_r_init_rw_obi_top`

#### Architecture Block Diagram

```
  CPU harts [0..7] → ROCC CUSTOM_1 cmd → idma_flit_t struct (via NoC or direct)
                                                │
  Other overlay clients [8..23] ───────────────┘
                                                │
                                                ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │               tt_idma_cmd_buffer_frontend                           │
  │                                                                     │
  │   client[0..23]                                                     │
  │   ┌──────┐ ┌──────┐ ... ┌──────┐                                   │
  │   │ FIFO │ │ FIFO │     │ FIFO │  (per-client FIFO)                │
  │   └──┬───┘ └──┬───┘     └──┬───┘                                   │
  │      └────────┴────────────┘                                        │
  │                    │ 24:2 weighted round-robin arbiter               │
  │                    ▼                                                 │
  │          trid[4:0] assignment (32 outstanding TIDs)                 │
  │          vc[1:0] selection                                          │
  │          payload_buf staging                                        │
  │                    │                                                 │
  │   CDC FIFO (core_clk → noc_clk domain crossing)                    │
  └────────────────────┬────────────────────────────────────────────────┘
                       │ FIFO depth = IDMA_FIFO_DEPTH = 42
                       │
                       ▼
  ┌────────────────────────────────────────────────────────────────────┐
  │       tt_idma_backend_r_init_rw_obi_top  ×IDMA_NUM_BE = 2         │
  │                                                                    │
  │   Back-end 0                    Back-end 1                        │
  │   ┌───────────────────┐         ┌───────────────────┐             │
  │   │  2D address gen   │         │  2D address gen   │             │
  │   │  outer loop (Y)   │         │  outer loop (Y)   │             │
  │   │  inner loop (X)   │         │  inner loop (X)   │             │
  │   │  stride/size cfg  │         │  stride/size cfg  │             │
  │   └────────┬──────────┘         └────────┬──────────┘             │
  │            │ OBI req                     │ OBI req                 │
  │            ▼                             ▼                         │
  │   ┌──────────────────────────────────────────────────────────┐    │
  │   │            OBI memory interface (to L1 RD port)           │    │
  │   │   o_mem_req[BE][port]  o_mem_addr[BE][port]               │    │
  │   │   i_mem_rvalid[BE][port]  i_mem_rdata[BE][port]           │    │
  │   └──────────────────────────────────────────────────────────┘    │
  │                                                                    │
  │   NoC inject: response flit → tt_overlay_flit_vc_arb → NIU        │
  │   Atomic accumulate: IDMA_L1_ACC_ATOMIC = 16 channels              │
  └────────────────────────────────────────────────────────────────────┘
```

#### idma_flit_t Internal Structure

```systemverilog
typedef struct packed {
  logic [L1_ACCUM_CFG_REG_W-1:0] l1_accum_cfg_reg;  // accumulate config
  logic [4:0]                     trid;               // transaction ID (0–31)
  logic [1:0]                     vc;                 // virtual channel
  logic [PAYLOAD_W-1:0]           payload;            // DMA descriptor
} idma_flit_t;
```

#### Key Constants

```systemverilog
IDMA_NUM_MEM_PORTS        = 2    // L1 RD port instances
IDMA_NUM_TRANSACTION_ID   = 32   // outstanding TID slots
IDMA_FIFO_DEPTH           = 42   // cmd buffer FIFO
IDMA_CMD_BUF_NUM_CLIENTS  = 24   // frontend clients
NumDim                    = 2    // 2D scatter/gather
IDMA_L1_ACC_ATOMIC        = 16   // accumulate channels
```

#### Access Masters

| Client Index | Source | Interface Type |
|-------------|--------|----------------|
| 0–7 | CPU harts (ROCC CUSTOM_1) | `idma_flit_t` via cmd buffer |
| 8–9 | Dispatch Engine sideband | `de_to_t6_t` / `t6_to_de_t` |
| 10–23 | Reserved / tile-specific | iDMA cmd port |

#### Source and Destination Memory

| Role | Memory | Access Port |
|------|--------|------------|
| Source (read) | Local L1 SRAM | iDMA RD back-end → L1 RD flex-client |
| Source (read) | Remote L1 (other tile) | iDMA injects NoC read request → remote NIU |
| Destination (write) | Local L1 SRAM | NoC snoop WR port (response packet) |
| Destination (write) | Remote L1 | iDMA injects NoC write packet |
| Destination (write) | DRAM (via NOC2AXI) | NoC write → NOC2AXI tile → AXI |

#### Basic Usage Guide (6 steps)

1. **Allocate a client ID** — each RISC-V hart owns its own client slot (0–7)
2. **Build the descriptor** — fill `src_addr`, `dst_addr`, `length`, 2D stride fields
3. **Issue ROCC CUSTOM_1 instruction** — `funct7=iDMA_CMD_FUNCT7`, `rs1=descriptor_ptr`, `rs2=0`
4. **Poll or interrupt** — read `IDMA_STATUS_REG` CSR or wait for `o_transfer_done_irq[trid]`
5. **Check completion** — verify `trid` cleared from `o_pending_trid_bitmap`
6. **Release** — for pipelined use, trid is auto-released after response

#### Advanced Usage

**2D Scatter/Gather:**
```
cfg: outer_count=NUM_ROWS, outer_stride=ROW_STRIDE
     inner_count=NUM_COLS, inner_stride=COL_STRIDE
Maps a 2D matrix region without software loop overhead.
```

**Context Switch with L1 accumulate:**
```
l1_accum_cfg_reg.enable = 1
l1_accum_cfg_reg.channel = CH_ID  (0–15)
Atomically accumulates result into L1 accumulate buffer.
Used for tensor partial-sum reduction.
```

**Multi-client pipelining:**
```
Clients 0–7 can each have up to IDMA_NUM_TRANSACTION_ID/8 ≈ 4 in-flight TIDs.
24:2 arbiter issues up to 2 simultaneous back-end transactions.
```

---

### 6.6 ROCC Accelerator

**Hardware:** `tt_rocc_accel` (instantiated ×8, one per hart)

#### Block Diagram (per hart)

```
  CPU hart[i]
      │ RISC-V CUSTOM_0/1/2/3 instruction
      │ (rs1, rs2, funct7, funct3, rd)
      ▼
  ┌───────────────────────────────────────────────────────────┐
  │                    tt_rocc_accel                          │
  │                      HART_ID = i                         │
  │                                                           │
  │  ┌──────────────────────────────────┐                    │
  │  │         tt_rocc_cmd_buf           │                    │
  │  │  - decodes CUSTOM_0–3 opcode      │                    │
  │  │  - buffers up to N cmds           │                    │
  │  │  - generates req_head_flit        │                    │
  │  │    (NoC header for DMA)           │                    │
  │  │  - scatter_list_magic_num check   │                    │
  │  └───────────────┬──────────────────┘                    │
  │                  │ decoded command                        │
  │                  ▼                                        │
  │  ┌────────────────────────────────────────┐              │
  │  │   tt_rocc_address_gen  ×PARALLEL=2     │              │
  │  │  - 2D src/dst address iteration        │              │
  │  │  - stride/size: from descriptor        │              │
  │  │  - outputs: src_addr, dst_addr         │              │
  │  └────────────────┬───────────────────────┘              │
  │                   │                                       │
  │  ┌────────────────▼───────────────────────┐              │
  │  │   tt_rocc_context_switch               │              │
  │  │  - saves/restores hart state to L1     │              │
  │  │  - CONTEXT_SWITCH_HART = HART_ID/      │              │
  │  │      NUM_CS_HARTS formula              │              │
  │  │  - uses D-cache store for state save   │              │
  │  └────────────────┬───────────────────────┘              │
  │                   │                                       │
  │  ┌────────────────▼───────────────────────┐              │
  │  │   tt_rocc_interrupt_event              │              │
  │  │  - transfer-complete IRQ to hart       │              │
  │  │  - rocc_ext_bits_o[hart_id]            │              │
  │  └────────────────────────────────────────┘              │
  │                                                           │
  │  D-cache memory interface:                               │
  │  o_src_dcache_req / i_src_dcache_resp                    │
  │  (SRC_DCACHE_REQ_TAG_BITS = 2)                           │
  └───────────────────────────────────────────────────────────┘
```

#### ROCC Opcode Map

| Opcode | Encoding | Group | Operation |
|--------|----------|-------|-----------|
| CUSTOM_0 | `7'b000_1011` (0x0B) | Misc | System control, fence, status |
| CUSTOM_1 | `7'b010_1011` (0x2B) | iDMA | DMA descriptor issue, poll |
| CUSTOM_2 | `7'b101_1011` (0x5B) | Address gen | Stride/size programming |
| CUSTOM_3 | `7'b111_1011` (0x7B) | Context switch | State save/restore to L1 |

**funct7 field** selects the specific sub-operation within each group. See `tt_rocc_pkg.sv` `INSTR_*` constants.

**Context switch hart formula:**
```systemverilog
localparam int CONTEXT_SWITCH_HART = HART_ID / NUM_CS_HARTS;
// Groups of NUM_CS_HARTS share a context switch L1 region
```

---

### 6.7 LLK (Low-Latency Kernel) Interface

**Hardware:** `tt_overlay_tile_counters_with_comparators`

LLK provides hardware remote counter channels used by the Tensix kernel scheduler to synchronize across tiles without issuing NoC messages.

```
  Tensix kernel (hart or FPU tile)
        │
        ▼ (increment local counter)
  ┌─────────────────────────────────────────────────┐
  │  tt_overlay_tile_counters_with_comparators       │
  │                                                  │
  │  Channel [0..3] per Tensix core:                │
  │  ┌──────────────────────────────────────────┐   │
  │  │  local_counter[CH]  ←── o_remote_rts[CH] │   │
  │  │  compare[CH]        ──► match_irq[CH]     │   │
  │  └──────────────────────────────────────────┘   │
  │                                                  │
  │  o_remote_counter_sel[3:0]  → selects which      │
  │    counter value to broadcast to LLK bus         │
  └─────────────────────────────────────────────────┘
        │
        ▼ (sideband to Tensix instrn_engine_wrapper)
  LLK interface:
  o_llk_remote_counter_sel [NUM_TENSIX_CORES][NUM_CLUSTER_CPUS+1]
  o_llk_remote_rts         [NUM_TENSIX_CORES][NUM_CLUSTER_CPUS+1]
```

- `NUM_TENSIX_CORES = 4` (one per FPU tile)
- `NUM_CLUSTER_CPUS+1 = 9` (8 harts + 1 shared channel)

---

### 6.8 Dispatch Engine

**Hardware:** `tt_dispatch_engine` → `disp_eng_overlay_wrapper` (Dispatch variant: `DISPATCH_INST=1`, `HAS_SMN_INST=0`)

The Dispatch Engine occupies Y=0, X=1 (West) and Y=0, X=2 (East). It acts as the primary clock distribution root for the Tensix array and manages the global event broadcast network.

#### Block Diagram

```
  External straps / SMN
  i_smn_strap.orientation
  i_phys_x, i_phys_y
            │
            ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │                  tt_dispatch_engine                              │
  │                   (IS_DISPATCH=1)                               │
  │                                                                  │
  │  ┌────────────────────────────────────────────────────────┐    │
  │  │         Quasar RISC-V management CPU (cluster)          │    │
  │  │  (same core as Tensix overlay, but DISPATCH_INST=1)    │    │
  │  │   + L1 partition (tt_disp_eng_l1_partition)            │    │
  │  └────────────────────┬───────────────────────────────────┘    │
  │                        │                                         │
  │  ┌─────────────────────▼──────────────────────────────────┐    │
  │  │           Clock Distribution Tree Root                   │    │
  │  │                                                          │    │
  │  │  i_noc_clk (input from PLL)                             │    │
  │  │       │                                                  │    │
  │  │       ├─► o_noc_clk_south[0..NumTensixX-1]             │    │
  │  │       │     (drives clock spine into Tensix rows Y=1–4) │    │
  │  │       │                                                  │    │
  │  │       ├─► io_noc_clk_east (to Dispatch E neighbor)      │    │
  │  │       │                                                  │    │
  │  │       └─► o_dm_clk_south  (debug clock to S neighbor)   │    │
  │  └─────────────────────────────────────────────────────────┘    │
  │                                                                  │
  │  ┌─────────────────────────────────────────────────────────┐    │
  │  │           Global Control / Event Bus                     │    │
  │  │                                                          │    │
  │  │  o_global_ctrl_south[X]  → tile enable, run/halt        │    │
  │  │  o_global_event_south[X] → tile_event broadcast         │    │
  │  │  o_global_event_east     → east tile broadcast          │    │
  │  │  o_tile_event[X]         → per-column events            │    │
  │  │  i_droop_event_east      ← droop from FDS (E tile)      │    │
  │  └─────────────────────────────────────────────────────────┘    │
  │                                                                  │
  │  ┌─────────────────────────────────────────────────────────┐    │
  │  │            FDS IS_DISPATCH=1 Wiring                      │    │
  │  │                                                          │    │
  │  │  Input bus:  fds_input_bus  ← input_t6_to_de (12 bits)  │    │
  │  │  Output bus: fds_output_bus → o_de_to_t6[0][0]          │    │
  │  │                                                          │    │
  │  │  o_t6_to_de  passes through (no FDS modification)       │    │
  │  │  o_de_to_t6[1][0]: orientation-dependent feedthrough    │    │
  │  │    (NOC_ORIENT_FLIP_EAST_WEST_0 strap)                  │    │
  │  └─────────────────────────────────────────────────────────┘    │
  │                                                                  │
  │  SMN ports:                                                      │
  │    i_smn_req_e_s / o_smn_req_e_s   (East↔South, not N↔S)       │
  │    HAS_SMN_INST = 0  (no SMN node in Dispatch overlay)          │
  └─────────────────────────────────────────────────────────────────┘
```

#### Dispatch vs. Tensix Overlay Comparison

| Feature | Tensix Overlay | Dispatch Overlay |
|---------|---------------|-----------------|
| `IS_DISPATCH` | 0 | 1 |
| `HAS_SMN_INST` | 1 | 0 |
| SMN direction | N↔S (`i_smn_req_n_s`) | E↔S (`i_smn_req_e_s`) |
| Clock output | None (receives clock) | `o_noc_clk_south[]` (distributes) |
| FDS input bus | `input_de_to_t6` (from DE) | `input_t6_to_de` (from T6) |
| FDS output assignment | `o_t6_to_de[0].tensix_to_dispatch_sync[local_y]` | `o_de_to_t6[0][0]` |
| L1 partition | `tt_t6_l1_partition` | `tt_disp_eng_l1_partition` |
| NoC ports | N/S/E/W all active | `NO_NOC_WEST_PORTS=1`/`NO_NOC_EAST_PORTS=1` |

#### Clock Distribution Detail

The Dispatch Engine contains the clock tree root for `noc_clk` in the entire Tensix array:

```
PLL output
   │
   ▼  i_noc_clk → Dispatch Engine clock input
                       │
           ┌───────────┼───────────────────┐
           │           │                   │
           ▼           ▼                   ▼
  o_noc_clk_south[0]  o_noc_clk_south[1] ... o_noc_clk_south[NumTensixX-1]
  (to Y=1,X=0)        (to Y=1,X=1)           (to Y=1,X=3)
         │                   │                       │
  (spine down          (spine down              (spine down
   Y=1→Y=4)             Y=1→Y=4)                Y=1→Y=4)
```

---

### 6.9 SMN (System Maintenance Network)

**Hardware:** `tt_overlay_smn_wrapper` → `tt_smn` (when `HAS_SMN_INST=1`)

#### Physical Topology

```
  Trinity grid (Y=0..4):

  Y=0  [NOC2AXI W]──E──[DISPATCH W]──S──(no SMN inst)
                                 │
                                 S (E↔S port)
                                 │
  Y=1  [TENSIX X=0]──N──[SMN node]──S──...──[TENSIX X=3]
  (SMN ring: N↔S per column)
                                 │
  Y=2  [TENSIX X=0]──N──[SMN node]──S──...
                                 │
  Y=3  ...
  Y=4  ...──[chain terminates or loops back at bottom]

  Per-column SMN daisy-chain:
    i_smn_req_n_s (from North neighbor or DE)
         │
         ▼
    tt_smn node (register decode, clock/reset control)
         │
         ▼
    o_smn_req_n_s (to South neighbor)
```

#### AXI4-Lite Transport and APB Conversion

```
  ┌─────────────────────────────────────────────────────┐
  │              tt_overlay_smn_wrapper                  │
  │                                                      │
  │  i_smn_req_n_s  (AXI4-Lite request, serialized)    │
  │       │                                              │
  │       ▼                                              │
  │  ┌──────────────────────────────────────────────┐   │
  │  │            tt_smn                             │   │
  │  │                                              │   │
  │  │  AXI4-Lite slave interface                  │   │
  │  │       │                                      │   │
  │  │       ▼                                      │   │
  │  │  smn_apb_req_t / smn_apb_resp_t              │   │
  │  │  APB master output:                          │   │
  │  │  ┌──────────────────────────────────────┐   │   │
  │  │  │ o_smn_apb_req → overlay APB slave    │   │   │
  │  │  │ o_smn_apb_req → t6_pll_pvt_apb slave │   │   │
  │  │  └──────────────────────────────────────┘   │   │
  │  │                                              │   │
  │  │  Control outputs:                            │   │
  │  │  o_smn_core_clk_en  → clock_reset_ctrl       │   │
  │  │  o_smn_ai_clk_en    → clock_reset_ctrl       │   │
  │  │  o_smn_noc_clk_en   → clock_reset_ctrl       │   │
  │  │  o_smn_reset_n[7:0] → per-hart reset         │   │
  │  │                                              │   │
  │  │  Interrupts:                                 │   │
  │  │  o_smn_wakeup_irq   → CPU hart 0 IRQ        │   │
  │  │  o_smn_done_irq     → CPU hart 0 IRQ        │   │
  │  │  o_smn_error_irq    → CPU hart 0 IRQ        │   │
  │  └──────────────────────────────────────────────┘   │
  │                                                      │
  │  JTAG override:                                     │
  │  i_jtag_smn_req → o_jtag_ctrl_ovrd                  │
  │  (overrides SMN commands during JTAG session)        │
  │                                                      │
  │  o_smn_req_n_s → South neighbor's i_smn_req_n_s    │
  └─────────────────────────────────────────────────────┘
```

#### SMN-Controlled Outputs Summary

| Output Signal | Target | Effect |
|--------------|--------|--------|
| `o_smn_core_clk_en` | `clock_reset_ctrl` | Gate/ungate CPU core clock |
| `o_smn_ai_clk_en` | `clock_reset_ctrl` | Gate/ungate AI/Tensix clock |
| `o_smn_noc_clk_en` | `clock_reset_ctrl` | Gate/ungate NoC clock |
| `o_smn_reset_n[7:0]` | Per-hart reset sync | Assert/release individual hart reset |
| `o_smn_apb_req` | `overlay_mst_apb` slave | Program overlay registers |
| `o_smn_apb_req` | `t6_pll_pvt_apb` slave | Program PLL/PVT registers |

#### SW 4-Step Init via SMN

1. Send SMN `WRITE` command to tile's `SMN_CLK_EN_REG`: set `core_clk_en=1`, `noc_clk_en=1`
2. Send SMN `WRITE` to `SMN_RESET_REG[7:0]`: deassert hart resets
3. Poll SMN `READ` from `SMN_STATUS_REG` until `clk_stable=1`
4. Write `SMN_DONE_REG` to trigger `o_smn_done_irq` to hart 0

---

### 6.10 EDC (Error Detection and Correction)

**Hardware:** `tt_overlay_edc_wrapper` → `tt_edc1_serial_bus_repeater` + `tt_edc1_serial_bus_demux` + `tt_edc1_noc_sec_controller`

#### EDC Ring and Harvest Bypass

```
  EDC1 serial ring enters from tile above:
  i_edc_ingress[EDC_IN_REP_NUM-1:0]   (serial bits, one per repeater)
        │
        ▼
  ┌─────────────────────────────────────────────────────┐
  │           tt_overlay_edc_wrapper                    │
  │                                                     │
  │   if HAS_EDC_INST==1:                               │
  │   ┌─────────────────────────────────────────────┐  │
  │   │  tt_edc1_serial_bus_repeater  ×EDC_IN_REP_NUM│  │
  │   │  (receive, check, re-drive serial bit)       │  │
  │   └─────────────────┬───────────────────────────┘  │
  │                     │                               │
  │   ┌─────────────────▼───────────────────────────┐  │
  │   │  tt_edc1_serial_bus_demux                   │  │
  │   │  (harvest bypass mux)                       │  │
  │   │                                             │  │
  │   │  i_overlay_harvested = 0:                   │  │
  │   │    pass EDC data through this tile          │  │
  │   │                                             │  │
  │   │  i_overlay_harvested = 1:                   │  │
  │   │    bypass this tile, connect                │  │
  │   │    ingress directly to egress               │  │
  │   └─────────────────┬───────────────────────────┘  │
  │                     │                               │
  │   ┌─────────────────▼───────────────────────────┐  │
  │   │  tt_edc1_serial_bus_repeater  ×EDC_OUT_REP_NUM│ │
  │   │  (output re-drive)                          │  │
  │   └─────────────────┬───────────────────────────┘  │
  │                     │                               │
  │   ┌─────────────────▼───────────────────────────┐  │
  │   │  tt_edc1_noc_sec_controller                 │  │
  │   │  (NoC security: allows/blocks flit inject   │  │
  │   │   based on EDC security state)              │  │
  │   └─────────────────────────────────────────────┘  │
  └─────────────────────┬───────────────────────────────┘
                        │
                        ▼
  o_edc_egress[EDC_OUT_REP_NUM-1:0]  → tile below (or loopback)
```

**EDC loopback port** (`i_edc_loopback` / `o_edc_loopback`): allows ring to be short-circuited during test or when the ring has not yet been closed.

**WDT integration:** `i_wdt_reset` — watchdog timer can assert reset into the EDC wrapper independently of normal reset hierarchy.

---

### 6.11 FDS (Frequency / Droop Sensor)

**Hardware:** `tt_fds_wrapper` → `tt_fds_delay_model` + `tt_fds`

#### Purpose

FDS monitors the chip's supply voltage droop by measuring ring-oscillator delay. When droop is detected it signals the Dispatch Engine, which can lower clock frequency or assert a pause to prevent timing failures. It is the hardware mechanism enabling autonomous DVFS without software latency.

#### Architecture Block Diagram

```
  ┌──────────────────────────────────────────────────────────────────┐
  │                     tt_fds_wrapper                               │
  │                                                                  │
  │  Sensor inputs (3 sources, BUS_IN_W=12 bits total):              │
  │  ┌──────────────────────────────────────────────────────────┐   │
  │  │   tt_fds_delay_model                                      │   │
  │  │                                                           │   │
  │  │  Tensix tile:  i_t6_to_de  ──► filtered t6_to_de bus     │   │
  │  │  Dispatch:     i_de_to_t6  ──► filtered de_to_t6 bus     │   │
  │  │  (IS_DISPATCH=0: input_bus = input_de_to_t6)             │   │
  │  │  (IS_DISPATCH=1: input_bus = input_t6_to_de)             │   │
  │  └─────────────────────────────────────────────────────────┘    │
  │                        │ fds_input_bus[BUS_IN_W-1:0]             │
  │                        ▼                                         │
  │  ┌──────────────────────────────────────────────────────────┐   │
  │  │                       tt_fds                              │   │
  │  │                                                           │   │
  │  │  Filter stage (noc_clk domain):                          │   │
  │  │  ┌────────────────────────────────────────────────┐      │   │
  │  │  │  filter_count[AD_COUNTER_WIDTH=32]             │      │   │
  │  │  │  stable_data / pause_count logic               │      │   │
  │  │  │  → asserts "droop detected" flag               │      │   │
  │  │  └──────────────────┬─────────────────────────────┘      │   │
  │  │                     │ noc_clk → core_clk CDC FIFO         │   │
  │  │  ┌──────────────────▼─────────────────────────────┐      │   │
  │  │  │  Async FIFO (depth: IS_DISPATCH ? 4 : 2)       │      │   │
  │  │  │  (domain crossing: noc_clk → core_clk)         │      │   │
  │  │  └──────────────────┬─────────────────────────────┘      │   │
  │  │                     │ core_clk domain                     │   │
  │  │  ┌──────────────────▼─────────────────────────────┐      │   │
  │  │  │  tt_fds_regfile (APB register access)          │      │   │
  │  │  │                                                │      │   │
  │  │  │  Round-robin arbiter (8 CPUs):                 │      │   │
  │  │  │  i_reg_cs[NUM_CLUSTER_CPUS-1:0]               │      │   │
  │  │  │  i_reg_wr_en[NUM_CLUSTER_CPUS-1:0]            │      │   │
  │  │  │  → serialized to single regfile port          │      │   │
  │  │  │                                                │      │   │
  │  │  │  Interrupt generation:                         │      │   │
  │  │  │  o_interrupts[NUM_GROUP_IDS-1:0]               │      │   │
  │  │  │  (16 interrupt groups, one per droop level)    │      │   │
  │  │  └──────────────────────────────────────────────┘      │   │
  │  └──────────────────────────────────────────────────────────┘   │
  │                        │                                         │
  │       fds_output_bus[BUS_OUT_W-1:0] → DE sideband / T6 sync    │
  └──────────────────────────────────────────────────────────────────┘
```

#### FDS IS_DISPATCH Wiring Inversion

| Parameter | Tensix tile (IS_DISPATCH=0) | Dispatch tile (IS_DISPATCH=1) |
|-----------|----------------------------|-------------------------------|
| `fds_input_bus` | `input_de_to_t6` (signal from DE) | `input_t6_to_de` (signal from T6 array) |
| `o_de_to_t6[0]` | `input_de_to_t6` passthrough | `fds_output_bus` (FDS drives DE output) |
| `o_t6_to_de[0].tensix_to_dispatch_sync[local_y]` | `fds_output_bus` (FDS drives T6 output) | `input_t6_to_de` passthrough |

#### Key Parameters

```systemverilog
IS_DISPATCH      = 0/1
HAS_ORIENTATION  = 1        // enables orientation strap check
BUNDLE_W         = 4        // bundle size in bits
NUM_SOURCES      = 3        // number of droop sensor sources
BUS_IN_W         = 12       // total input bus width (3 × BUNDLE_W)
BUS_OUT_W        = 4        // output bus width (1 × BUNDLE_W)
NUM_GROUP_IDS    = 16       // interrupt groups
COUNTER_WIDTH    = 8        // per-source filter counter
AD_COUNTER_WIDTH = 32       // droop accumulate/detect counter
```

#### CDC Architecture Detail

The droop detection logic runs in `noc_clk` domain (faster, more responsive), but CPU interrupt delivery requires `core_clk` domain. The async FIFO handles this:

```
noc_clk domain:
  droop_detected_flag → async FIFO write (depth 2 or 4)

core_clk domain:
  async FIFO read → interrupt_pending flag → o_interrupts[group_id]
```

#### SW Guide (3 steps)

1. **Program threshold:** Write `FDS_THRESHOLD_REG` via APB to set droop detection sensitivity (maps to `filter_count` counter limit)
2. **Enable interrupt group:** Write `FDS_IRQ_EN_REG[group_id]` to arm the desired interrupt group
3. **Handle interrupt:** In ISR, read `FDS_STATUS_REG` to determine which group fired, clear by writing `FDS_IRQ_CLR_REG[group_id]`

---

### 6.12 Tensix and L1 Access from the Overlay

#### Overlay → Tensix Control Interface

```
  tt_overlay_wrapper
         │
         │  o_de_to_t6[1:0][NumDispatchCorners-1:0]   (dispatch_enable_t struct)
         │    - Contains: tensix_dispatch_sync bits
         │    - Source: FDS output (Tensix tile) or Dispatch Engine (DE tile)
         │
         │  i_t6_to_de[NumTensixX-1:0]                (t6_to_dispatch_t struct)
         │    - Contains: tensix_to_dispatch_sync bits
         │    - Source: FDS input from each Tensix column
         │
         ▼
  tt_tensix_tile  (instrn_engine_wrapper + gen_gtile[*])
         │
         ├── instrn_engine_wrapper
         │     ├── 3× TRISC cores (RISC-V, kernel execution)
         │     ├── icache (instruction cache per TRISC)
         │     └── local_mem (scratchpad SRAM per TRISC)
         │
         └── gen_gtile[0..GTILE_CNT-1]  (u_fpu_gtile)
               ├── FPU matrix engine (8×16 systolic)
               ├── SRCA regfile (source A accumulator)
               ├── SRCB regfile (source B weight)
               ├── DEST regfile (output accumulator)
               └── SFPU (special function unit: exp, log, sqrt)
```

#### All L1 Requestors (7 paths)

```
┌────────────────────────────────────────────────────────────────────────┐
│                    L1 Requestor Summary                                │
│                                                                        │
│  1. CPU hart D-cache (×8 harts, 4 sub-ports each)                     │
│     → RISC-V load/store → L1 D-cache controller → RW flex-client      │
│                                                                        │
│  2. CPU hart I-cache (×8 harts, separate icache port)                  │
│     → instruction fetch → L1 I-cache controller → RD flex-client      │
│                                                                        │
│  3. iDMA back-end read (×IDMA_NUM_BE=2)                                │
│     → OBI read request → L1 RD flex-client port                       │
│                                                                        │
│  4. NoC inbound write (snoop / remote DMA write)                       │
│     → NIU eject → TileLink snoop master → L1 WR flex-client           │
│                                                                        │
│  5. NoC atomic read-modify-write                                       │
│     → NIU eject → atomic handler → L1 RW flex-client (atomic port)    │
│                                                                        │
│  6. APB debug (T6L1 debug slave)                                       │
│     → tt_overlay_apb_to_l1_if → L1 RW flex-client                     │
│                                                                        │
│  7. AXI inbound (from JTAG/NOC2AXI)                                   │
│     → tt_overlay_axi_to_l1_if → L1 WR flex-client                     │
└────────────────────────────────────────────────────────────────────────┘
```

#### NoC Snoop Interface (RTL-level detail)

```
  NoC flit arrives at local NIU (eject path)
         │
         ▼
  tt_overlay_noc_snoop_tl_master
         │
  Determines flit type:
  ├── TileLink PutFull / PutPartial → write to L1 WR port
  │     i_noc_mem_port_snoop_valid[port]
  │     i_noc_mem_port_snoop_addr[port]
  │     i_noc_mem_port_snoop_data[port]
  │     i_noc_mem_port_snoop_strb[port]   (byte-enable)
  │
  ├── TileLink Get → read from L1, inject response flit
  │     → L1 RD port → o_mem_rdata → NoC inject
  │
  └── TileLink ArithmeticData / LogicalData → atomic RMW
        → L1 RW atomic port → operation → response flit
```

---

### 6.13 Harvest Support

**Hardware:** `tt_overlay_wrapper_harvest_trinity`

```
  Per-tile harvest signal:
  i_overlay_harvested  (1 = this tile is disabled/harvested)
  i_remap_x_size       (reduced mesh width after harvest)
  i_remap_y_size       (reduced mesh height after harvest)

  ┌──────────────────────────────────────────────────────────┐
  │          tt_overlay_wrapper_harvest_trinity              │
  │                                                          │
  │  if i_overlay_harvested == 1:                            │
  │    - assert all output clocks = 0                        │
  │    - assert all hart_reset_n = 0                         │
  │    - EDC demux: bypass this tile (i_edc_ingress          │
  │        routed directly to o_edc_egress via               │
  │        tt_edc1_serial_bus_demux)                         │
  │    - NoC router: use remap_x/y_size for                  │
  │        modified DOR routing to avoid harvested col/row   │
  │    - SMN: no-op all SMN commands to this tile            │
  └──────────────────────────────────────────────────────────┘
```

Harvest enables the chip to ship with defective tiles disabled while the remaining tiles form a functional (smaller) mesh.

---

### 6.14 Register Access via APB / EDC Bridge

#### APB Bus Topology Inside Overlay

```
  CPU (via D-cache store to APB-mapped addr)
         │
         ▼
  tt_overlay_wrapper_reg_logic   (APB crossbar)
         │
         ├── cluster_ctrl_apb  → CPU cluster configuration
         ├── smn_mst_apb       → SMN master (outbound to ring)
         ├── edc_mst_apb       → EDC master (outbound to ring)
         ├── overlay_mst_apb   → overlay-internal registers
         ├── t6l1_slv_apb      → L1 flex-client CSR slave
         ├── t6_pll_pvt_slv    → PLL / PVT sensor slave
         └── flex_client_csr_slv → flex-client config

  APB parameters:
    REG_APB_PORT_ADDR_WIDTH = 26
    REG_DATA_WIDTH          = 32
    NUM_CLUSTER_CPUS        = 8   (per-CPU CS, WR_EN, ADDR, DATA)
```

#### EDC → APB Bridge

```
  EDC ring (serial bus)
         │
         ▼
  tt_overlay_edc_apb_bridge
         │
         ▼
  APB master → overlay_mst_apb slave
  (allows remote chip management via EDC without NoC)
```

---

### 6.15 iJTAG / DFD Interface

```
  External JTAG TAP
         │
  i_ijtag_tck_to_dfd    ─────────────────────────────────►
  i_ijtag_trstn_to_dfd  ─────────────────────────────────►
  i_ijtag_si_to_dfd     ─────────────────────────────────►   Scan chain
  i_ijtag_sel_to_dfd    ─────────────────────────────────►   passthrough
  i_ijtag_capturedr     ─────────────────────────────────►   (no logic
  i_ijtag_shiftdr       ─────────────────────────────────►   modification)
  i_ijtag_updatedr      ─────────────────────────────────►
         ◄─────────────────────────────────────────────────
  o_ijtag_so_from_dfd
```

The overlay contains no JTAG logic of its own; it is a pass-through to the DFD (Design For Debug) infrastructure inside the Tensix tile. SMN can override iJTAG activity via `o_jtag_ctrl_ovrd`.

---

## 7. Control Path: Processor to Data Bus

This section traces the complete hardware path from a CPU instruction to a NoC flit on the mesh.

### Path 1: CPU Local L1 Load

```
  RISC-V hart  LW x1, 0(x2)         (core_clk domain)
       │
       ▼  Physical address
  D-cache tag lookup → miss/hit decision
       │  (hit)
       ▼
  L1 flex-client RW port arbitration (pre_sbank → arb)
       │
       ▼
  tt_mem_wrap_1024x128_sp   SRAM read (1 cycle)
       │
       ▼
  D-cache fill → CPU pipeline (data available 2–3 cycles from request)
```

### Path 2: CPU Remote Write via NoC

```
  RISC-V hart  SW x1, REMOTE_ADDR(x0)     (core_clk domain)
       │
       ▼  TLB lookup → physical address → off-tile (NoC address)
  TileLink Put request → L2 frontend bus (l2_frontend_bus_tl_req_t)
       │
       ▼  noc_clk domain (CDC crossing via TileLink adapter)
  tt_overlay_flit_vc_arb
       │  builds NoC flit header: {dst_x, dst_y, vc, msg_type, addr}
       ▼
  NIU inject port → router → West/East/North/South output port
       │
       ▼  (travels through NoC mesh DOR X-first routing)
  Remote tile NIU eject → tt_overlay_noc_snoop_tl_master
       │
       ▼
  Remote L1 WR flex-client → tt_mem_wrap_1024x128_sp write
```

### Path 3: iDMA Bulk Transfer

```
  RISC-V hart  CUSTOM_1 (funct7=DMA_CMD, rs1=desc_ptr)    (core_clk domain)
       │
       ▼
  tt_rocc_cmd_buf decodes: src_addr, dst_addr, length, 2D params
       │
       ▼  idma_flit_t{trid, vc, payload}
  tt_idma_cmd_buffer_frontend (24:2 arbiter, FIFO depth=42)
       │  CDC: core_clk → noc_clk
       ▼
  tt_idma_backend_r_init_rw_obi_top (back-end 0 or 1)
       │  address iteration (2D outer/inner loop)
       ▼
  OBI read request → o_t6_l1_arb_rd_intf → L1 RD bank read
       │
       ▼  read data
  NoC inject: write flit → dst_x, dst_y address → mesh
       │
       ▼  at destination tile
  NIU eject → snoop WR port → remote L1 write
       │
       ▼  completion
  o_transfer_done_irq[trid] → CPU hart (via PLIC)
```

---

## 8. Key Parameters

| Parameter | Value | Source | Description |
|-----------|-------|--------|-------------|
| `NUM_CLUSTER_CPUS` | 8 | `tt_overlay_pkg.sv` | RISC-V harts per overlay |
| `NUM_INTERRUPTS` | 64 | `tt_overlay_pkg.sv` | Total IRQ lines per hart |
| `VERSION_W` | 6 | `tt_overlay_pkg.sv` | Overlay version field width |
| `REG_APB_PORT_ADDR_WIDTH` | 26 | `tt_overlay_pkg.sv` | APB address width |
| `REG_DATA_WIDTH` | 32 | `tt_overlay_pkg.sv` | APB data width |
| `IDMA_NUM_MEM_PORTS` | 2 | `tt_idma_pkg.sv` | iDMA L1 RD back-ends |
| `IDMA_NUM_TRANSACTION_ID` | 32 | `tt_idma_pkg.sv` | Outstanding DMA TIDs |
| `IDMA_FIFO_DEPTH` | 42 | `tt_idma_pkg.sv` | Command FIFO entries |
| `IDMA_CMD_BUF_NUM_CLIENTS` | 24 | `tt_idma_pkg.sv` | DMA frontend clients |
| `NumDim` | 2 | `tt_idma_pkg.sv` | Scatter/gather dimensions |
| `IDMA_L1_ACC_ATOMIC` | 16 | `tt_idma_pkg.sv` | Atomic accumulate channels |
| `PARALLEL_ADDRESS_GEN` | 2 | `tt_rocc_pkg.sv` | Parallel ROCC addr gen units |
| `SRC_DCACHE_REQ_TAG_BITS` | 2 | `tt_rocc_pkg.sv` | D-cache tag bits for ROCC |
| `FDS_NUM_SOURCES` | 3 | `tt_fds_wrapper.sv` | Droop sensor sources |
| `FDS_NUM_GROUP_IDS` | 16 | `tt_fds_wrapper.sv` | FDS interrupt groups |
| `FDS_AD_COUNTER_WIDTH` | 32 | `tt_fds_wrapper.sv` | FDS accumulate counter |
| `L1_SRAM_DEPTH` | 1024 | hierarchy CSV | Entries per L1 sub-bank |
| `L1_SRAM_WIDTH` | 128 | hierarchy CSV | Bits per L1 sub-bank entry |
| `ROUTER_VC_DEPTH` | 64 | hierarchy CSV | VC buffer entries |
| `ROUTER_VC_WIDTH` | 2048 | hierarchy CSV | VC buffer flit width (bits) |

---

## 9. Clock and Reset Summary

```
                    ┌───────────────────────────────────────┐
                    │    Clock Domain Boundaries             │
                    │                                       │
   ref_clk ─────────┼────────── reset sync counters        │
                    │           (16-cycle synchronizers)    │
   core_clk ────────┼────────── CPU pipeline               │
   (gated by SMN)   │           L1 D-cache                  │
                    │           ROCC cmd/resp                │
                    │           iDMA frontend                │
                    │           FDS regfile + IRQ            │
                    │           APB register buses           │
                    │                                       │
   ai_clk ──────────┼────────── Tensix FPU tiles            │
   (gated by SMN)   │           SFPU / matrix engine        │
                    │                                       │
   ai_aon_clk ──────┼────────── Always-on uncore regs       │
   (not gated)      │                                       │
                    │                                       │
   noc_clk ─────────┼────────── NoC router / NIU            │
   (gated by SMN)   │           iDMA back-end               │
                    │           FDS filter stage             │
                    │                                       │
   CDC crossings:   │                                       │
   noc→core:        │  iDMA cmd buffer FIFO (depth=42)      │
                    │  FDS async FIFO (depth=2 or 4)        │
   core→noc:        │  TileLink/OBI adapter (NoC inject)    │
                    └───────────────────────────────────────┘

Reset hierarchy:
  i_powergood
    └─► i_core_clk_reset_n_pre_sync[7:0]  (per-hart, from POR)
          │
          ▼  (16-cycle sync in ref_clk domain)
        o_hart_reset_n[7:0]  (released to CPU pipeline)

SMN reset override:
  i_smn_reset_n[7:0] → can hold any hart in reset independently
```

---

## 10. APB Register Interfaces

The overlay exposes 7 APB sub-buses from the register crossbar:

| Bus Name | Direction | Target | Width |
|----------|-----------|--------|-------|
| `cluster_ctrl_apb` | M→S | CPU cluster registers | 26b addr / 32b data |
| `smn_mst_apb` | M→S | SMN ring outbound | 26b / 32b |
| `edc_mst_apb` | M→S | EDC ring outbound | 26b / 32b |
| `overlay_mst_apb` | M→S | Overlay internal regs | 26b / 32b |
| `t6l1_slv_apb` | S←M | L1 flex-client CSR | 26b / 32b |
| `t6_pll_pvt_slv` | S←M | PLL / PVT sensors | 26b / 32b |
| `flex_client_csr_slv` | S←M | L1 flex-client config | 26b / 32b |

Register struct types (from `tt_overlay_pkg.sv`):
```systemverilog
typedef struct packed {
  logic [REG_APB_PORT_ADDR_WIDTH-1:0] paddr;
  logic [REG_DATA_WIDTH-1:0]          pwdata;
  logic                               pwrite;
  logic                               psel;
  logic                               penable;
} apb_req_t;

typedef struct packed {
  logic [REG_DATA_WIDTH-1:0] prdata;
  logic                      pready;
  logic                      pslverr;
} apb_resp_t;
```

---

## 11. Worked Example: CPU Issues a NoC Write

**Scenario:** Hart 0 on tile (X=1, Y=1) writes 64 bytes to address `0x00020000` (which maps to tile X=2, Y=1, L1 offset 0x0).

```
Step 1: Hart 0 executes  SD x5, 0(x6)  where x6 = 0x00020000
  → physical address lookup: X=2, Y=1 via NoC address decoder
  → TileLink PutFull request generated in core_clk domain

Step 2: TileLink adapter (core_clk → noc_clk CDC)
  → l2_frontend_bus_tl_req_t built with:
      address = 0x00020000
      data    = [64-byte payload]
      source  = hart_id=0, TID=0

Step 3: tt_overlay_flit_vc_arb
  → selects VC=0 (write channel)
  → builds NoC flit header:
      {dst_x=2, dst_y=1, vc=0, msg_type=WRITE, addr=0x0000}
  → injects into NIU local port

Step 4: Router at (X=1, Y=1)
  → DOR: dst_x=2 > src_x=1, route East
  → flit departs on East output port

Step 5: Router at (X=2, Y=1)
  → dst_x=2 = local_x, dst_y=1 = local_y → eject to local NIU

Step 6: tt_overlay_noc_snoop_tl_master at (X=2, Y=1)
  → receives TileLink PutFull
  → drives i_noc_mem_port_snoop_valid, _addr, _data, _strb
  → L1 WR flex-client → tt_mem_wrap_1024x128_sp write
  → TileLink AccessAck response → NIU inject → back to (X=1,Y=1)

Step 7: Hart 0 at (X=1,Y=1) receives AccessAck
  → store instruction retires
```

---

## 12. Verification Checklist

- [ ] All 5 clock domains present and independently gatable via SMN
- [ ] Per-hart reset: assert/deassert individually, verify no cross-hart interference
- [ ] L1 scrub: all banks written before first read, ECC clean
- [ ] iDMA 1D transfer: single back-end, all 32 TIDs exercised
- [ ] iDMA 2D transfer: outer/inner loop, stride=0 (contiguous) and stride≠0 (strided)
- [ ] iDMA multi-client: ≥4 simultaneous clients, verify round-robin arbitration
- [ ] ROCC CUSTOM_0: misc system ops, verify no side-effect on other harts
- [ ] ROCC CUSTOM_1: DMA issue, verify completion IRQ on correct hart
- [ ] ROCC CUSTOM_2: address gen programming, verify 2D address sequence
- [ ] ROCC CUSTOM_3: context switch, verify state saved/restored correctly
- [ ] NoC write: CPU → NIU inject → remote tile → L1 WR port, verify data integrity
- [ ] NoC read: CPU → NIU inject → remote tile → NIU eject → L1 RD → response
- [ ] NoC atomic: AMO operation, verify atomicity (no interleaving)
- [ ] SMN clock enable/disable: verify tile power-gating, no clock glitches
- [ ] SMN reset: per-hart, verify other harts unaffected
- [ ] EDC ring: full-ring continuity test, verify loopback and normal path
- [ ] EDC harvest bypass: set i_overlay_harvested=1, verify EDC ring skips tile
- [ ] FDS: inject droop pulse, verify interrupt fires in correct group
- [ ] FDS CDC: verify no metastability in noc→core FIFO crossing
- [ ] Dispatch clock distribution: verify o_noc_clk_south drives all columns
- [ ] Dispatch global event: broadcast from DE reaches all Tensix tiles
- [ ] Harvest: harvested tile quiesced, NoC routes around it, EDC bypassed
- [ ] APB register access: read/write all 7 sub-buses, verify decode
- [ ] iJTAG: scan chain continuity, SMN override functional

---

## 13. Key RTL File Index

| File | Module | Location |
|------|--------|----------|
| `tt_overlay_wrapper.sv` | `tt_overlay_wrapper` | `tt_rtl/overlay/rtl/` |
| `tt_overlay_pkg.sv` | package | `tt_rtl/overlay/rtl/` |
| `tt_overlay_noc_wrap.sv` | `tt_overlay_noc_wrap` | `tt_rtl/overlay/rtl/` |
| `tt_overlay_noc_niu_router.sv` | `tt_overlay_noc_niu_router` | `tt_rtl/overlay/rtl/` |
| `tt_overlay_smn_wrapper.sv` | `tt_overlay_smn_wrapper` | `tt_rtl/overlay/rtl/` |
| `tt_overlay_clock_reset_ctrl.sv` | `tt_overlay_clock_reset_ctrl` | `tt_rtl/overlay/rtl/` |
| `tt_overlay_edc_wrapper.sv` | `tt_overlay_edc_wrapper` | `tt_rtl/overlay/rtl/` |
| `tt_idma_wrapper.sv` | `tt_idma_wrapper` | `tt_rtl/overlay/rtl/idma/` |
| `tt_idma_pkg.sv` | package | `tt_rtl/overlay/rtl/idma/` |
| `tt_idma_cmd_buffer_frontend.sv` | `tt_idma_cmd_buffer_frontend` | `tt_rtl/overlay/rtl/idma/` |
| `tt_rocc_accel.sv` | `tt_rocc_accel` | `tt_rtl/overlay/rtl/accelerators/` |
| `tt_rocc_pkg.sv` | package | `tt_rtl/overlay/rtl/accelerators/` |
| `tt_rocc_cmd_buf.sv` | `tt_rocc_cmd_buf` | `tt_rtl/overlay/rtl/accelerators/` |
| `tt_dispatch_engine.sv` | `tt_dispatch_engine` | `tt_rtl/overlay/rtl/quasar_dispatch/` |
| `tt_disp_eng_overlay_wrapper.sv` | `tt_disp_eng_overlay_wrapper` | `tt_rtl/overlay/rtl/quasar_dispatch/` |
| `tt_disp_eng_l1_partition.sv` | `tt_disp_eng_l1_partition` | `tt_rtl/overlay/rtl/quasar_dispatch/` |
| `tt_fds_wrapper.sv` | `tt_fds_wrapper` | `tt_rtl/overlay/rtl/fds/` |
| `tt_fds.sv` | `tt_fds` | `tt_rtl/overlay/rtl/fds/` |
| `trinity_hierarchy.csv` | — (instantiation DB) | `20260221/rtl/` |
