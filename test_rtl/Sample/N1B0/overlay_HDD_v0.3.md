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
| v0.4 | 2026-03-19 | (RTL-derived) | §6.5 iDMA full HW/SW view expanded (OBI vs AXI backend, clock gating, descriptor format, completion IRQ, tiles_to_process); §6.16 CPU target address map and access methods; §15 iDMA + CPU target reference table |

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
   - 6.16 [CPU and iDMA Target Address Map](#616-cpu-and-idma-target-address-map)
7. [Control Path: Processor to Data Bus](#7-control-path-processor-to-data-bus)
8. [Key Parameters](#8-key-parameters)
9. [Clock and Reset Summary](#9-clock-and-reset-summary)
10. [APB Register Interfaces](#10-apb-register-interfaces)
11. [Worked Example: CPU Issues a NoC Write](#11-worked-example-cpu-issues-a-noc-write)
12. [Verification Checklist](#12-verification-checklist)
13. [Key RTL File Index](#13-key-rtl-file-index)
14. [iDMA and CPU — Complete Access Target Reference](#14-idma-and-cpu--complete-access-target-reference)

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

**Hardware:** `tt_idma_wrapper` → `tt_idma_cmd_buffer_frontend` + `tt_idma_backend_r_init_rw_obi_top` (OBI) or `tt_idma_backend_r_init_rw_axi_top` (AXI)

---

#### 6.5.1 HW View — Complete Architecture

```
                   core_clk domain                     l1_clk / noc_clk domain

  CPU hart[i]
  ROCC CUSTOM_1 ──► idma_flit_t ─────────────────────────────────────────►
  (cmd + payload)

  Other clients
  [0..23]       ──► idma_flit_t
                         │
                         ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │                  tt_idma_wrapper                                      │
  │                                                                       │
  │  ┌─────────────────────────────────────────────────────────────────┐ │
  │  │               tt_idma_cmd_buffer_frontend                        │ │
  │  │                                                                  │ │
  │  │  i_req_head_flit[0..23]   i_req_head_flit_valid[0..23]          │ │
  │  │  ┌──────┐ ┌──────┐ ... ┌──────┐   ← per-client FIFO entries    │ │
  │  │  │ FIFO │ │ FIFO │     │ FIFO │     (IDMA_FIFO_DEPTH = 42 total)│ │
  │  │  └──┬───┘ └──┬───┘     └──┬───┘                                │ │
  │  │     └────────┴────────────┘                                     │ │
  │  │                  │                                               │ │
  │  │     24:2 weighted round-robin arbiter                            │ │
  │  │                  │                                               │ │
  │  │     trid[4:0] allocator (pool of 32 IDs)                        │ │
  │  │     payload FIFO staging (IDMA_PAYLOAD_FIFO_DEPTH = 8)          │ │
  │  │     l1_accum_cfg extraction                                      │ │
  │  │                  │                                               │ │
  │  │     ┌────────────▼──────────────────────────────────────────┐   │ │
  │  │     │  Async FIFO / CDC boundary (core_clk → l1_clk)        │   │ │
  │  │     │  ASYNC_BOUNDARY = 1                                    │   │ │
  │  │     └────────────┬──────────────────────────────────────────┘   │ │
  │  │                  │ cmd_buf_fe_req_head_flit[IDMA_NUM_BE-1:0]     │ │
  │  │                  │ cmd_buf_fe_req_head_flit_l1_acc[IDMA_NUM_BE]  │ │
  │  │                  │ cmd_buf_fe_req_head_flit_valid[IDMA_NUM_BE]   │ │
  │  └──────────────────┼──────────────────────────────────────────────┘ │
  │                     │                                                  │
  │  ┌──────────────────▼──────────────────────────────────────────────┐ │
  │  │                                                                  │ │
  │  │  [IDMA_BE_TYPE_AXI == 0]  gen_obi_backend                       │ │
  │  │  tt_idma_backend_r_init_rw_obi_top  ×IDMA_NUM_BE = 2            │ │
  │  │                  OR                                              │ │
  │  │  [IDMA_BE_TYPE_AXI == 1]  gen_axi_backend                       │ │
  │  │  tt_idma_backend_r_init_rw_axi_top  ×IDMA_NUM_BE = 2            │ │
  │  │                                                                  │ │
  │  │   Back-end 0                      Back-end 1                    │ │
  │  │  ┌────────────────────┐          ┌────────────────────┐         │ │
  │  │  │  idma_req_t decode │          │  idma_req_t decode │         │ │
  │  │  │  src_addr / length │          │  src_addr / length │         │ │
  │  │  │  dst_addr / stride │          │  dst_addr / stride │         │ │
  │  │  │  2D outer loop     │          │  2D outer loop     │         │ │
  │  │  │  2D inner loop     │          │  2D inner loop     │         │ │
  │  │  └────────┬───────────┘          └────────┬───────────┘         │ │
  │  │           │                               │                      │ │
  │  │    ┌──────▼───────────────────────────────▼──────┐              │ │
  │  │    │   OBI memory interface (to local L1 RD port) │             │ │
  │  │    │   o_mem_req[BE][port]                        │             │ │
  │  │    │   o_mem_addr[BE][port]                       │             │ │
  │  │    │   o_mem_wdata[BE][port]  o_mem_we[BE][port]  │             │ │
  │  │    │   o_mem_strb[BE][port]  o_mem_atop[BE][port] │             │ │
  │  │    │   i_mem_gnt[BE][port]   i_mem_rvalid[BE][port]│            │ │
  │  │    │   i_mem_rdata[BE][port]                      │             │ │
  │  │    └──────────────────────────────────────────────┘             │ │
  │  │                                                                  │ │
  │  │    o_l1_accum_cfg[BE]   ─► L1 accumulate config                 │ │
  │  │    o_l1_accum_en[BE]    ─► L1 accumulate enable                 │ │
  │  └──────────────────────────────────────────────────────────────────┘ │
  │                                                                        │
  │  ┌─────────────────────────────────────────────────────────────────┐  │
  │  │   tt_clk_gater (l1_clk hysteresis gate, HYST_WIDTH=7)           │  │
  │  │   i_kick = |{cmd_buf_fe_req_head_flit_valid, backend_resp_valid} │  │
  │  │   → gated_l1_clk: clock gated when idle for HYST cycles         │  │
  │  └─────────────────────────────────────────────────────────────────┘  │
  │                                                                        │
  │  Completion tracking ports:                                            │
  │  o_idma_tiles_to_process[32*TCOUNT_W-1:0]  ─► per-TID count           │
  │  o_idma_tiles_to_process_irq[31:0]         ─► IRQ when count≥threshold│
  │  i_tr_id_thresholds[32*TCOUNT_W-1:0]       ─► per-TID threshold config│
  │  i_tiles_to_process_clear[31:0]            ─► clear IRQ per TID        │
  └────────────────────────────────────────────────────────────────────────┘
```

#### 6.5.2 Backend Modes — OBI vs AXI

| Mode | Parameter | Backend Module | Memory Target | Protocol |
|------|-----------|----------------|---------------|----------|
| **OBI** (default) | `IDMA_BE_TYPE_AXI=0` | `tt_idma_backend_r_init_rw_obi_top` | Local L1 SRAM | OBI (Open Bus Interface) |
| **AXI** | `IDMA_BE_TYPE_AXI=1` | `tt_idma_backend_r_init_rw_axi_top` | AXI bus (DRAM, NOC2AXI) | AXI4 full |

**OBI backend** connects directly to `o_t6_l1_arb_rd_intf` L1 RD flex-client ports — no NoC hop for source reads. Read data is retrieved from local L1 and then injected into NoC as write packets toward the destination.

**AXI backend** issues AXI transactions to the system bus. Used when either the source or destination is DRAM. The AXI address is mapped to the NOC2AXI tile's AXI slave interface.

#### 6.5.3 Clock Gating Architecture

```
  i_l1_clk ──────────────────────────────────────────────────────►
                                                                   │
  l1_clkgt_kick signal:                                           │
    = |{cmd_buf_fe_req_head_flit_valid[BE], backend_resp_valid[BE]}│
         (any pending request or response → kick clock on)        │
                                                                   ▼
  ┌────────────────────────────────────────────────────────────┐
  │   tt_clk_gater                                             │
  │   .i_enable (from SMN via i_l1_clkgt_en register)         │
  │   .i_kick   (from request/response activity)               │
  │   .i_busy   (from o_l1_clkgt_busy in backend)             │
  │   .i_histeresys (i_l1_clkgt_hyst, 7-bit)                 │
  │   → o_gated_clk: active during transfer, gated when idle  │
  └────────────────────────────────────────────────────────────┘
         │
         ▼ gated_l1_clk → backends
```

**Hysteresis behavior:** After the last kick, the clock stays active for `2^i_l1_clkgt_hyst` cycles before gating. The `o_l1_clkgt_busy` signal from the backend prevents premature gating when a multi-cycle operation is in progress.

#### 6.5.4 idma_flit_t Descriptor Structure

```systemverilog
// Top-level flit carries command + payload
typedef struct packed {
  l1_atomic_compute_instr_t  l1_accum_cfg_reg;  // L1 accumulate instruction
  logic [4:0]                trid;               // transaction ID (0–31)
  logic [1:0]                vc;                 // virtual channel selector
  idma_req_t                 payload;            // DMA transfer descriptor
} idma_flit_t;

// DMA transfer descriptor (idma_req_t, from iDMA IP typedef.svh)
typedef struct packed {
  logic [63:0]  src_addr;           // source byte address
  logic [63:0]  dst_addr;           // destination byte address
  logic [21:0]  length;             // transfer size in bytes (IDMA_TRANSFER_LENGTH_WIDTH=22)
  logic [63:0]  src_stride;         // outer dimension source stride (2D mode)
  logic [63:0]  dst_stride;         // outer dimension destination stride (2D mode)
  logic [63:0]  num_reps;           // outer loop repetition count (2D mode)
  logic         decouple_rw;        // decouple read and write phases
  logic         deburst;            // disable burst mode
  logic         serialize;          // force serialization
  // ... protocol/option bits
} idma_req_t;
```

**Transfer length width:** `IDMA_TRANSFER_LENGTH_WIDTH = 22` → max single transfer = 4 MB.

#### 6.5.5 Complete Data Flow — Local L1 Read → Remote Write

```
Step 1: SW issues descriptor (core_clk domain)
  CPU executes CUSTOM_1  → idma_flit_t submitted to client port

Step 2: Frontend queues (core_clk domain)
  cmd_buffer_frontend FIFO[client]  → arbiter selects → TID assigned

Step 3: CDC crossing (core_clk → l1_clk)
  Async FIFO (ASYNC_BOUNDARY=1)

Step 4: Backend read from local L1 (l1_clk domain)
  idma_req_t.src_addr → 2D address gen → OBI request
  o_mem_req=1, o_mem_addr=src_addr[i], o_mem_we=0
  i_mem_rvalid ─► read data captured

Step 5: Build NoC write packet (l1_clk domain)
  dst_addr ─► NoC header: x_coord=dst_x, y_coord=dst_y
  data ─► flit payload (2048-bit)
  flit injected via tt_overlay_flit_vc_arb → NIU inject port

Step 6: NoC mesh routing
  DOR: route X-first to destination tile

Step 7: Remote tile receive
  Remote NIU eject → tt_overlay_noc_snoop_tl_master
  → TileLink PutFull → L1 WR flex-client → L1 SRAM write

Step 8: Completion (l1_clk → core_clk CDC back)
  backend_resp_flit_valid ─► frontend resp FIFO
  trid cleared from pending pool
  o_idma_tiles_to_process[trid] incremented
  if count >= i_tr_id_thresholds[trid]:  o_idma_tiles_to_process_irq[trid] = 1
```

#### 6.5.6 Complete Data Flow — DRAM Write (AXI backend)

```
Step 1–3: Same as above (frontend → CDC)

Step 4: Backend AXI issue (l1_clk domain)
  idma_req_t.dst_addr → AXI AW channel
  AXI address = DRAM physical address (0x6000_0000 – 0x7FFF_FFFF range)
  AXI AW/W channels → NOC2AXI tile's AXI slave input

Step 5: NOC2AXI tile processing
  AXI2NOC path: AXI write → NoC packet
  ATT lookup (or direct) → target: NOC2AXI (X=0–3, Y=0)
  NoC packet injected into mesh from NOC2AXI tile

Step 6: DRAM controller
  NOC2AXI ejects packet → AXI master transaction → DRAM

Step 7: Completion
  AXI B-channel response → NOC2AXI → NoC response flit → back to source tile
  completion interrupt fired
```

#### 6.5.7 Tiles-to-Process Tracking (Group-completion IRQ)

```
i_tr_id_thresholds[(1<<5)*TCOUNT_W - 1:0]  (32 TIDs × TCOUNT_W bits each)
    ─► per-TID threshold: "fire IRQ when this TID completes N times"

o_idma_tiles_to_process[(1<<5)*TCOUNT_W - 1:0]
    ─► per-TID accumulated count (SW-readable)

o_idma_tiles_to_process_irq[(1<<5)-1:0]
    ─► per-TID IRQ flag (set when count >= threshold)

i_tiles_to_process_clear[(1<<5)-1:0]
    ─► write 1 to clear a specific TID's count and IRQ
```

**Use case:** "fire interrupt when all 16 Tensix tiles have completed their iDMA transfers." SW programs each TID's threshold to the expected completion count, then waits for a single IRQ instead of polling 16 individual transfer-done flags.

#### 6.5.8 idma_flit_t Input Clients Table

| Client [i] | Source | Interface Type | Description |
|-----------|--------|----------------|-------------|
| 0–7 | CPU harts | `idma_flit_t` via ROCC CUSTOM_1 | Per-hart DMA issue |
| 8–9 | Dispatch Engine sideband | `de_to_t6_t` → flit adapter | DE-initiated tile-wide DMA |
| 10–23 | Tile-internal / reserved | `idma_flit_t` port | Future / system use |

#### 6.5.9 Source and Destination Memory Matrix

| Source Memory | iDMA Access Method | Hardware Path |
|--------------|-------------------|---------------|
| **Local L1** | OBI backend read | `o_t6_l1_arb_rd_intf` → L1 RD flex-client |
| **Remote L1** | NoC read request | backend injects NoC Get → remote NIU → remote L1 RD |
| **DRAM (SI0–SI3)** | AXI backend read | AXI AR channel → NOC2AXI slave → AXI master → DRAM |

| Destination Memory | iDMA Access Method | Hardware Path |
|-------------------|-------------------|---------------|
| **Local L1** | NoC write packet → snoop | flit inject → NIU eject local → L1 WR port |
| **Remote L1** | NoC write packet | flit inject → mesh → remote NIU eject → remote L1 WR |
| **DRAM (SI0–SI3)** | AXI backend write or NoC write → NOC2AXI | AXI AW+W → NOC2AXI slave → DRAM |

#### 6.5.10 SW View — Step-by-Step Programming Guide

**1D Transfer (basic):**
```
// Step 1: Allocate client slot (one per hart, static assignment)
client_id = hart_id;   // 0–7

// Step 2: Build descriptor in memory (or in registers)
struct idma_req {
    src_addr = 0x10000;        // source L1 byte address on this tile
    dst_addr = 0x20000;        // destination L1 on same or remote tile
    length   = 1024;           // bytes
    num_reps = 1;              // 1D: outer loop = 1
    src_stride = 0;
    dst_stride = 0;
};

// Step 3: Issue via ROCC CUSTOM_1
// Assembly: .insn r CUSTOM_1, 0, DMA_CMD_FUNCT7, rd, rs1, rs2
// rs1 = pointer to descriptor, rs2 = client_id
// rd receives assigned trid

// Step 4: Wait for completion
// Option A — interrupt:
//   When o_idma_tiles_to_process_irq[trid] fires, DMA is done
//   ISR: write i_tiles_to_process_clear[trid] = 1 to clear

// Option B — poll:
//   Read IDMA_STATUS register, check trid bit cleared from pending_bitmap

// Step 5: (Optional) Check transferred count
//   o_idma_tiles_to_process[trid * TCOUNT_W +: TCOUNT_W]  = completed count
```

**2D Transfer (matrix row copy):**
```
// Example: copy 16×64-byte matrix rows from L1 at src_base to dst_base
// Each row is at stride ROW_BYTES (e.g. 256 bytes = row + padding)
struct idma_req {
    src_addr   = src_base;
    dst_addr   = dst_base;
    length     = 64;          // bytes per row (inner)
    num_reps   = 16;          // number of rows (outer)
    src_stride = 256;         // source row stride (bytes)
    dst_stride = 256;         // destination row stride (bytes)
};
// iDMA iterates: for (i=0; i<16; i++) copy src+i*256 → dst+i*256, length=64
```

**L1 Accumulate (partial-sum reduction):**
```
// Set l1_accum_cfg_reg in idma_flit_t before submission:
flit.l1_accum_cfg_reg.enable  = 1;
flit.l1_accum_cfg_reg.channel = 3;   // channel 0–15
// iDMA back-end accumulates read data into L1 accumulate register
// o_l1_accum_cfg + o_l1_accum_en forwarded to L1 bank
```

**SW Register Map (iDMA registers via APB, 9-bit address):**

| Address | Register | Description |
|---------|----------|-------------|
| TBD | `IDMA_STATUS` | `[31:0]` pending TID bitmap |
| TBD | `IDMA_VC_SPACE[BE]` | available VC slots per back-end |
| TBD | `IDMA_TR_COUNT[trid]` | transaction count per TID |
| TBD | `IDMA_THRESHOLD[trid]` | completion threshold per TID |
| TBD | `IDMA_CLR[trid]` | write 1 to clear TID count+IRQ |
| TBD | `IDMA_CLK_EN` | `[0]` L1 clock gate enable |
| TBD | `IDMA_CLK_HYST` | `[6:0]` hysteresis count |

> Note: exact APB offsets defined in `tt_idma_pkg.sv` register typedef. The 9-bit `reg_addr_t` provides 512 byte-addressed register locations.

**Clock gating SW control:**
```
// Enable iDMA clock gating (power saving when idle):
APB_WRITE(IDMA_CLK_EN,   1);        // allow clock gate
APB_WRITE(IDMA_CLK_HYST, 0x10);     // 16-cycle hysteresis

// Disable clock gating (keep clock always on, e.g. low-latency burst mode):
APB_WRITE(IDMA_CLK_EN, 0);
```

**Multi-client pipelining pattern:**
```
// Each hart can have ~4 in-flight TIDs (32 TIDs / 8 harts)
// Submit multiple descriptors before waiting:
for (i = 0; i < 4; i++) {
    trid[i] = issue_dma(client_id, &desc[i]);
}
wait_for_all_irq(trid, 4);   // poll or interrupt-based
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

### 6.16 CPU and iDMA Target Address Map

This section defines what memory targets exist in the Trinity address space, how each target is addressed, and which initiators (RISC-V CPU or iDMA) can reach each target.

#### 6.16.1 Trinity System Memory Map

The Trinity 4×5 NoC mesh exposes the following memory regions to software running on the Tensix cluster CPUs.

```
Physical Address Space (64-bit, but 56-bit meaningful in NoC)

┌──────────────────────────────────────────────────────────────────────┐
│  Region             │  Address Range              │  Target           │
├──────────────────────────────────────────────────────────────────────┤
│  Local L1           │  0x0000_0000 – 0x0007_FFFF  │  This tile's L1  │
│                     │  (512 KB window, tile-local)│  (direct)         │
├──────────────────────────────────────────────────────────────────────┤
│  Remote L1          │  Encoded in NoC header      │  Any Tensix tile  │
│                     │  x_coord[5:0] y_coord[5:0]  │  via NoC mesh     │
│                     │  + local L1 offset addr     │                   │
├──────────────────────────────────────────────────────────────────────┤
│  NPU AXI SI0        │  0x6000_0000 – 0x67FF_FFFF  │  NOC2AXI (0, 0)  │
│  (128 MB)           │                             │  → DRAM / PCIe   │
├──────────────────────────────────────────────────────────────────────┤
│  NPU AXI SI1        │  0x6800_0000 – 0x6FFF_FFFF  │  NOC2AXI (1, 0)  │
│  (128 MB)           │                             │  → DRAM / PCIe   │
├──────────────────────────────────────────────────────────────────────┤
│  NPU AXI SI2        │  0x7000_0000 – 0x77FF_FFFF  │  NOC2AXI (2, 0)  │
│  (128 MB)           │                             │  → DRAM / PCIe   │
├──────────────────────────────────────────────────────────────────────┤
│  NPU AXI SI3        │  0x7800_0000 – 0x7FFF_FFFF  │  NOC2AXI (3, 0)  │
│  (128 MB)           │                             │  → DRAM / PCIe   │
├──────────────────────────────────────────────────────────────────────┤
│  Overlay registers  │  APB address space          │  Local APB slave  │
│  (per tile)         │  26-bit, REG_DATA_WIDTH=32  │  (direct via APB) │
├──────────────────────────────────────────────────────────────────────┤
│  ATT base           │  0x0201_0000                │  Local NIU ATT    │
│  (translation tbl)  │  size: 0x3000               │  (APB)            │
└──────────────────────────────────────────────────────────────────────┘

Note: DRAM address ranges (SI0–SI3) are from the system-level platform
memory map and are not encoded in RTL. Verify against SoC integration
spec. The NOC2AXI tiles are at y=0 in the Trinity grid (North row).
```

#### 6.16.2 NoC Address Encoding for Remote Targets

When a CPU or iDMA accesses a non-local target, the address must be encoded as a NoC header `noc_header_address_t` (96-bit struct):

```
 95      88 87    82 81    76 75    70 69    64 63                   0
 +--------+---------+---------+---------+---------+------------------+
 | rsvd   |bc_start |bc_start |  y_coord|  x_coord|   addr (64-bit)  |
 |  (8b)  |  _y (6b)|  _x (6b)|   (6b)  |  (6b)  |  local byte addr │
 +--------+---------+---------+---------+---------+------------------+

x_coord  = destination tile's X index (0–3 for Trinity 4×5)
y_coord  = destination tile's Y index (0–4 for Trinity 4×5)
addr     = 64-bit byte address within the destination tile's memory
```

**Remote L1 address formula:**
```
noc_x_coord = target_tile_x          (0–3)
noc_y_coord = target_tile_y          (1–4 for Tensix)
noc_addr    = L1_base + L1_offset    (local to destination tile)
```

**DRAM address formula (via NOC2AXI tile):**
```
noc_x_coord = NOC2AXI tile X         (0–3, matches SI0–SI3 column)
noc_y_coord = NOC2AXI tile Y         (0 = North row)
noc_addr    = DRAM_physical_addr     (full 64-bit, but only 56-bit meaningful)

The AXI address leaving NOC2AXI = noc_addr[55:0] (bits [63:56] dropped)
```

**ATT alternative:** Instead of pre-computing coordinates, SW can program the **Address Translation Table (ATT)** in the NIU to automatically map a logical address prefix to a target (x_coord, y_coord). This is used for virtual memory regions that span multiple tiles.

#### 6.16.3 RISC-V CPU Access Methods per Target

```
┌──────────────────────────────────────────────────────────────────────┐
│               RISC-V CPU Access Method Matrix                        │
│                                                                      │
│  Target            │ Access Method         │ Path                   │
│  ──────────────────│───────────────────────│──────────────────────  │
│  Local L1          │ Load/Store (LW/SW)    │ D-cache → L1 RW port  │
│  (this tile)       │ All widths supported  │ 1–3 cycle latency      │
│                    │                       │ core_clk domain        │
│  ──────────────────│───────────────────────│──────────────────────  │
│  Remote L1         │ Store → NoC write     │ D-cache miss → TL Put  │
│  (other Tensix)    │ SW/SH/SB, 64B writes  │ → NIU inject → mesh   │
│                    │ Load → NoC read       │ → remote NIU eject     │
│                    │ (LW/LD via PTW)       │ → remote L1 RD port   │
│  ──────────────────│───────────────────────│──────────────────────  │
│  DRAM (SI0–SI3)    │ Store → NoC write     │ D-cache miss → TL Put  │
│  0x6000_0000–      │ to NOC2AXI address    │ → NIU inject → NoC   │
│  0x7FFF_FFFF       │ Load → NoC read       │ → NOC2AXI tile (y=0) │
│                    │                       │ → AXI master → DRAM   │
│  ──────────────────│───────────────────────│──────────────────────  │
│  Overlay registers │ Store/Load to APB-    │ D-cache → APB adapter │
│  (local tile)      │ mapped address        │ → APB crossbar        │
│                    │                       │ → target APB slave    │
│  ──────────────────│───────────────────────│──────────────────────  │
│  Remote tile regs  │ NoC write to          │ CPU → NoC → remote    │
│  (other tile's APB)│ remote APB address    │ NIU → APB snoop       │
│  ──────────────────│───────────────────────│──────────────────────  │
│  SMN ring          │ CPU writes APB        │ CPU → smn_mst_apb     │
│  (management)      │ smn_mst bus           │ → tt_smn → ring       │
└──────────────────────────────────────────────────────────────────────┘
```

#### 6.16.4 iDMA Access Methods per Target

```
┌──────────────────────────────────────────────────────────────────────┐
│               iDMA Access Method Matrix                              │
│                                                                      │
│  Target         │ iDMA Source?  │ iDMA Dest?  │ Backend Used        │
│  ───────────────│───────────────│─────────────│───────────────────  │
│  Local L1       │ YES           │ YES         │ OBI backend (read)  │
│  (this tile)    │ OBI RD port   │ NoC snoop   │ NoC inject (write)  │
│  ───────────────│───────────────│─────────────│───────────────────  │
│  Remote L1      │ YES           │ YES         │ NoC Get (read)      │
│  (other tile)   │ NoC Get flit  │ NoC Put     │ NoC Put flit(write) │
│  ───────────────│───────────────│─────────────│───────────────────  │
│  DRAM (SI0–SI3) │ YES (AXI BE)  │ YES         │ AXI backend (read)  │
│                 │ AXI AR chan.  │ AXI AW/W    │ AXI backend (write) │
│  ───────────────│───────────────│─────────────│───────────────────  │
│  Overlay regs   │ NO            │ NO          │ N/A                 │
│  SMN ring       │ NO            │ NO          │ N/A                 │
└──────────────────────────────────────────────────────────────────────┘
```

**Key answer to the example question "Can DRAM be accessed by iDMA and RISC-V in the Overlay?"**

**YES — both can access DRAM:**
- **RISC-V CPU:** issues a load/store to address `0x6000_0000–0x7FFF_FFFF` → D-cache miss → TileLink → NoC write packet → NOC2AXI tile (Y=0) → AXI master → DRAM
- **iDMA (AXI backend):** descriptor with `dst_addr` in DRAM range → AXI backend issues AXI AW+W → NOC2AXI slave → converted to AXI master → DRAM. For DMA source from DRAM: AXI AR → read data → construct NoC write to destination L1.

#### 6.16.5 Address Routing Diagram

```
  CPU at Tensix (X=1, Y=2)  iDMA at Tensix (X=1, Y=2)
         │                            │
         │ load/store                 │ OBI RD / NoC inject
         ▼                            ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  Local L1 (this tile, direct)                                  │
  │  Addr: tile-local base + offset (no NoC hop)                   │
  └────────────────────────────────────────────────────────────────┘
         │ (cache miss or explicit remote addr)
         ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  NIU inject port → NoC mesh (DOR X-first routing)              │
  │                                                                │
  │  x_coord=0–3,  y_coord=1–4  ──► Tensix L1 (remote tile)       │
  │  x_coord=0–3,  y_coord=0    ──► NOC2AXI tile  → DRAM/PCIe    │
  └────────────────────────────────────────────────────────────────┘
         │
         ▼
  Destination tile NIU eject
  → L1 WR port (write)
  → L1 RD + response flit (read)
  → AXI master → DRAM (when destination is NOC2AXI tile)
```

#### 6.16.6 Tile-Local Register Address Map (APB, per tile)

```
Overlay APB base: programmable (from SMN or CPU)
Bit width: 26-bit address, 32-bit data

Sub-bus            │ Offset       │ Purpose
───────────────────│──────────────│──────────────────────────────
cluster_ctrl_apb   │ TBD          │ CPU cluster config, IRQ mask
smn_mst_apb        │ TBD          │ SMN ring outbound commands
edc_mst_apb        │ TBD          │ EDC ring outbound commands
overlay_mst_apb    │ TBD          │ Overlay-internal CSRs
t6l1_slv_apb       │ TBD          │ L1 flex-client CSR (read/scrub)
t6_pll_pvt_slv     │ TBD          │ PLL + PVT sensor registers
flex_client_csr_slv│ TBD          │ L1 port configuration

ATT base address:  0x0201_0000    │ NoC ATT (mask, endpoint, dynamic)
ATT size:          0x3000 bytes   │ 16-entry mask + 1024-entry endpoint
                                  │ + 32-entry dynamic routing tables
```

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

---

## 14. iDMA and CPU — Complete Access Target Reference

This section consolidates all access relationships between initiators (RISC-V CPU / iDMA) and memory targets in the Trinity SoC.

### 14.1 Initiator × Target Matrix

```
                    ┌──────────────────────────────────────────────────────────────────┐
                    │                  MEMORY TARGET                                   │
                    ├───────────┬──────────────┬──────────────┬────────────┬──────────┤
  INITIATOR         │ Local L1  │ Remote L1    │ DRAM SI0–SI3 │ Local regs │ SMN ring │
                    │(this tile)│(other Tensix)│(0x6000_0000  │(APB slave) │(APB mst) │
                    │           │              │–0x7FFF_FFFF) │            │          │
  ──────────────────┼───────────┼──────────────┼──────────────┼────────────┼──────────┤
  RISC-V CPU        │  YES      │  YES         │  YES         │  YES       │  YES     │
  (Load/Store)      │ direct    │ NoC RW       │ NoC → AXI    │ APB        │ smn_mst  │
                    │ L1 port   │              │              │            │          │
  ──────────────────┼───────────┼──────────────┼──────────────┼────────────┼──────────┤
  iDMA (source)     │  YES      │  YES         │  YES (AXI BE)│  NO        │  NO      │
                    │ OBI RD    │ NoC Get flit │ AXI AR chan  │            │          │
  ──────────────────┼───────────┼──────────────┼──────────────┼────────────┼──────────┤
  iDMA (dest)       │  YES      │  YES         │  YES (AXI BE)│  NO        │  NO      │
                    │ NoC WR    │ NoC Put flit │ AXI AW+W     │            │          │
                    │ snoop port│              │              │            │          │
  ──────────────────┴───────────┴──────────────┴──────────────┴────────────┴──────────┘
```

### 14.2 Detailed Paths per Initiator–Target Pair

#### RISC-V CPU → Local L1

```
  CPU Load/Store (core_clk domain)
    → D-cache controller (tag + data SRAM lookup)
    → On hit: data returned in 1–3 cycles
    → On miss: fill request to L1
         → tt_overlay_memory_wrapper → tt_t6_l1_partition
         → RW flex-client arbitration (pre_sbank → arb)
         → tt_mem_wrap_1024x128_sp SRAM (1-cycle access)
         → fill data returned to D-cache → CPU pipeline
```

#### RISC-V CPU → Remote L1

```
  CPU Store (SW/SH/SB) to remote L1 address
    → D-cache TLB: physical addr = {noc_x, noc_y, l1_offset}
    → D-cache miss (non-cacheable or uncached map)
    → TileLink PutFull request built
    → tt_overlay_flit_vc_arb: select VC
    → NoC head flit: x_coord=noc_x, y_coord=noc_y, cmd_rw=1
    → NIU inject → mesh router (DOR X-first)
    → Remote NIU eject
    → tt_overlay_noc_snoop_tl_master → L1 WR flex-client
    → remote L1 SRAM write

  CPU Load (LW/LD) from remote L1
    → same path as Store up to NoC inject
    → NoC Get (read) flit
    → Remote NIU: L1 RD port → read data
    → response flit injected back to source tile
    → source NIU eject → TileLink AccessAckData
    → D-cache fill → CPU
```

#### RISC-V CPU → DRAM (SI0–SI3)

```
  CPU Store to 0x6000_0000 – 0x7FFF_FFFF
    → D-cache TLB maps to NOC2AXI tile address
    → TileLink PutFull → NoC head flit:
         x_coord = column of NOC2AXI tile (SI0→X=0, SI1→X=1, SI2→X=2, SI3→X=3)
         y_coord = 0   (North row = NOC2AXI row)
         addr    = DRAM physical address [63:0]
    → Mesh DOR: route Y-north until y=0
    → NOC2AXI tile NIU: reconstruct AXI AW+W transaction
         AXI addr = noc_addr[55:0]   (56-bit, bits[63:56] dropped)
    → AXI master → external DRAM controller

  CPU Load from DRAM
    → NoC Get flit to NOC2AXI tile
    → NOC2AXI tile: AXI AR transaction → DRAM read
    → AXI R data → NoC response flit → back to source CPU
    → D-cache fill → CPU pipeline
```

#### iDMA → Local L1 (source read)

```
  Backend selects: IDMA_BE_TYPE_AXI = 0 (OBI mode)
  Descriptor: src_addr = tile-local L1 offset

  iDMA backend: OBI request
    o_mem_req[BE][port] = 1
    o_mem_addr[BE][port] = src_addr + 2D_offset
    o_mem_we = 0 (read)
    → tt_t6_l1_partition RD flex-client
    → SRAM read → i_mem_rdata → backend data buffer
    → data staged for NoC inject toward destination
```

#### iDMA → Remote L1 (destination write)

```
  Data from source (local L1 or DRAM)
    → iDMA backend assembles 2048-bit NoC payload
    → Builds NoC head flit:
         x_coord = dst_tile_x
         y_coord = dst_tile_y
         addr    = dst_l1_offset
         cmd_rw  = 1 (write)
         vc      = flit.vc field from descriptor
    → tt_overlay_flit_vc_arb → NIU inject port
    → Mesh routing → destination tile NIU eject
    → tt_overlay_noc_snoop_tl_master
    → TileLink PutFull → L1 WR flex-client → SRAM write
    → completion response flit → back to iDMA engine
    → trid freed, o_idma_tiles_to_process[trid] updated
```

#### iDMA → DRAM (AXI backend)

```
  Backend selects: IDMA_BE_TYPE_AXI = 1 (AXI mode)
  Descriptor: dst_addr = DRAM physical address (0x6000_0000+)

  iDMA AXI backend:
    AXI AW channel: addr = dst_addr[55:0]
    AXI W  channel: data = source data
    → NOC2AXI tile's AXI slave interface (mapped to SI0–SI3)
    → NOC2AXI: AXI2NOC path
         ATT lookup: maps addr prefix → NoC endpoint (x=0–3, y=0)
         Constructs NoC write packet
    → Mesh: route to NOC2AXI tile at y=0
    → NOC2AXI NOC2AXI path: NoC flit → AXI master transaction → DRAM
    → B-channel response → NoC response → iDMA completion
```

### 14.3 Latency and Bandwidth Notes

| Path | Latency (typical) | Bandwidth | Notes |
|------|-------------------|-----------|-------|
| CPU → Local L1 (hit) | 1–3 cycles | Full cache width / cycle | core_clk domain |
| CPU → Local L1 (miss) | ~10 cycles | L1 bank bandwidth | L1 arbitration + SRAM |
| CPU → Remote L1 | ~20–40 cycles | NoC link bandwidth | NoC hop latency |
| CPU → DRAM | 100–300 cycles | DRAM bandwidth | Multiple NoC hops + DRAM latency |
| iDMA → Local L1 (read) | 1–3 cycles / beat | 2× L1 RD port bandwidth | OBI back-end, 2 ports |
| iDMA → Remote L1 (write) | NoC latency | Full NoC flit per beat | 2048-bit payload / flit |
| iDMA 2D | same per beat | 2 parallel back-ends | Outer loop overlap possible |
| iDMA → DRAM | 100–300 cycles | DRAM bandwidth | AXI backend + DRAM |

### 14.4 Access Constraint Summary

| Rule | Details |
|------|---------|
| CPU cannot directly access iDMA registers via ROCC | Must use ROCC CUSTOM_1 opcode (not APB) |
| iDMA cannot access overlay APB | iDMA is data-path only; register programming must be done by CPU |
| iDMA cannot access SMN ring | SMN is a management network; only CPU/SMN master can access it |
| Remote L1 must be live | Destination tile must have L1 clock enabled and L1 scrubbed |
| DRAM access requires NOC2AXI tile alive | Clock and reset for NOC2AXI tile must be enabled via SMN |
| ATT must be programmed for ATT-based addressing | CPU must write ATT via APB before using virtual NoC addresses |
| DRAM address range [63:56] dropped | 56-bit effective physical address; upper 8 bits are discarded |
| iDMA 2D max transfer | outer_count × inner_count × length ≤ 4 MB per back-end submission |
