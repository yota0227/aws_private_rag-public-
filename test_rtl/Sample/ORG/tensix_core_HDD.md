# Tensix Core Hardware Design Document
**Version:** 0.3
**Date:** 2026-03-18
**Source:** RTL-derived from `/secure_data_from_tt/20260221/rtl/enc/tt_rtl/tt_tensix_neo/`

---

## Table of Contents

1. [Overview & Design Philosophy](#1-overview--design-philosophy)
2. [Architecture Block Diagram](#2-architecture-block-diagram)
3. [Top-Level Hierarchy](#3-top-level-hierarchy)
4. [Instruction Engine & Thread Model](#4-instruction-engine--thread-model)
   - 4.1 Thread Model (BRISC + TRISC×3)
   - 4.2 Instruction Buffer & Thread Context
   - 4.3 MOP (Macro-Operation) Engine
   - 4.4 Stall Scoreboard & Replay Unit
   - 4.5 TRISC Processor
   - 4.6 Atomic Operations & Semaphores
5. [Tensor DMA Controller (TDMA)](#5-tensor-dma-controller-tdma)
   - 5.1 Unpacker
   - 5.2 Packer
   - 5.3 Address Generation (`tt_tdma_xy_address_controller`)
   - 5.4 Word Assembler & Unpack Row
   - 5.5 Format Conversion (`tt_unpacker_gasket_fmt_conv`)
   - 5.6 Packer Misc Ops (`tt_packer_gasket_misc_ops`)
   - 5.7 TDMA Configuration Registers (`tt_thcon_cfg_regs`)
   - 5.8 Throttle & Flow Control
6. [Floating-Point Unit (FPU)](#6-floating-point-unit-fpu)
   - 6.1 FPU v2 Top (`tt_fpu_v2`)
   - 6.2 FPU G-Tile (`tt_fpu_gtile`)
   - 6.3 FPU M-Tile (`tt_fpu_mtile`)
   - 6.4 FPU Tile (`tt_fpu_tile`) — Pipeline & Control
   - 6.5 FP Lane (`tt_fp_lane`) — Core MAC Datapath
   - 6.6 FP Multiplier (`tt_fp_mul_raw`)
   - 6.7 Exponent Path (`tt_exp_path_v4`)
   - 6.8 Alignment (`tt_dual_align`, `tt_barrel_rshift`)
   - 6.9 Compressor Trees (`tt_three_two_compressor`, `tt_four_two_compressor`)
   - 6.10 Multi-Operand Adder (`tt_multiop_adder`)
   - 6.11 Integer Multipliers (`tt_mul8/16/32`)
   - 6.12 Source Register Interfaces (SRCA / SRCB)
   - 6.13 ALU Configuration Registers (`tt_alu_cfg_regs`)
7. [Special Function Unit (SFPU)](#7-special-function-unit-sfpu)
   - 7.1 SFPU Architecture
   - 7.2 SFPU MAD Pipeline (`tt_t6_com_sfpu_mad`)
   - 7.3 SFPU Local Registers (`tt_sfpu_lregs`)
   - 7.4 SFPU Instruction Dispatch & SW Usage
8. [L1 Shared Memory](#8-l1-shared-memory)
   - 8.1 Bank Structure
   - 8.2 Client Arbitration
   - 8.3 ECC & Error Handling
9. [Destination Register File](#9-destination-register-file)
   - 9.1 Structure & Addressing
   - 9.2 Format Conversion (`tt_dstac_to_mem`)
   - 9.3 Double-Buffering & SW Management
10. [Stochastic Rounding & PRNG](#10-stochastic-rounding--prng)
11. [Element-to-MX Format Converter (`tt_t6_com_elem_to_mx_convert`)](#11-element-to-mx-format-converter)
12. [Power Management](#12-power-management)
    - 12.1 Droop Trigger Detector
    - 12.2 Power Ramp FSM & Ballasting
13. [FPU Safety Controller](#13-fpu-safety-controller)
14. [Error Aggregation & Reporting](#14-error-aggregation--reporting)
15. [CSR / Register Space](#15-csr--register-space)
16. [Numeric Format Reference](#16-numeric-format-reference)
17. [Clock & Reset Structure](#17-clock--reset-structure)
18. [Key Parameters Summary](#18-key-parameters-summary)
19. [Software Usage Guide](#19-software-usage-guide)

---

## 1. Overview & Design Philosophy

The **Tensix** tile is the primary AI-compute unit of the Trinity SoC. Twelve tiles are arranged in a 4×3 sub-grid (rows 2–4 of the 4×5 mesh). Each tile is a self-contained, multi-threaded processor combining:

- A **multi-threaded RISC control plane** (BRISC + TRISC×3) that orchestrates data movement and math operations.
- A **purpose-built Tensor DMA (TDMA)** that streams tiled data between L1 SRAM and the FPU register files with inline format conversion.
- A **16-column × N-row floating-point MAC array** (FPU G-Tiles → M-Tiles → FP Lanes) that delivers the compute throughput for GEMM, convolution, and element-wise operations.
- An **iterative scalar SFPU** for activation functions (GeLU, sigmoid, exp, log, rsqrt, etc.) that operates directly on the destination register file.
- A **large banked L1 SRAM** (≈1.5 MB per tile) that holds activations, weights, and intermediate tensors.

**Design philosophy:** The tile is designed around a "compute-near-memory" principle — instead of sending data over a NoC for each operation, large tensors are pre-staged in L1 by the dispatch engine, and the TRISC/TDMA/FPU pipeline executes entire tiled-GEMM kernels entirely within the tile with minimal NoC traffic. The NoC is used only to fill/drain the L1 buffer between kernel launches.

---

## 2. Architecture Block Diagram

### 2.1 Full Tile Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         tt_tensix_with_l1                                │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        tt_tensix                                  │  │
│  │                                                                   │  │
│  │  ┌──────────────────────────────────────────────────────────────┐ │  │
│  │  │                 tt_instrn_engine_wrapper                     │ │  │
│  │  │                                                              │ │  │
│  │  │  BRISC         TRISC0 (Unpack)  TRISC1 (Math)  TRISC2 (Pack)│ │  │
│  │  │  [RISC-V]      [RISC-V]         [RISC-V]        [RISC-V]   │ │  │
│  │  │     │               │                │               │      │ │  │
│  │  │     └───────────────┴────────────────┴───────────────┘      │ │  │
│  │  │                     instruction dispatch bus                 │ │  │
│  │  │                            │                                 │ │  │
│  │  │  ┌─────────────────────────▼──────────────────────────────┐ │ │  │
│  │  │  │                  tt_tdma                                │ │ │  │
│  │  │  │                                                         │ │ │  │
│  │  │  │  Unpack CH0 ─── L1 READ ──►  SRCA reg write ──►       │ │ │  │
│  │  │  │  Unpack CH1 ─── L1 READ ──►  SRCB reg write ──►       │ │ │  │
│  │  │  │  Pack   CH0 ◄── L1 WRITE ─── DEST reg read  ◄──       │ │ │  │
│  │  │  │  Pack   CH1 ◄── L1 WRITE ─── DEST reg read  ◄──       │ │ │  │
│  │  │  │                                                         │ │ │  │
│  │  │  └─────────────────────────────────────────────────────────┘ │ │  │
│  │  │                                                              │ │  │
│  │  └──────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  │  ┌───────────────────────────────────────────────────────────┐   │  │
│  │  │              FPU (tt_fpu_v2 / tt_fpu_gtile × 4)          │   │  │
│  │  │                                                           │   │  │
│  │  │  SRCA reg [48 rows × 16 cols × 16-bit]                   │   │  │
│  │  │  SRCB reg [48 rows × 16 cols × 16-bit]                   │   │  │
│  │  │                     │                                     │   │  │
│  │  │  ┌──────────────────▼──────────────────────────────────┐ │   │  │
│  │  │  │         FP Lane × 16 columns (parallel)             │ │   │  │
│  │  │  │  each lane: mul → exp_align → compress → accumulate │ │   │  │
│  │  │  └──────────────────┬──────────────────────────────────┘ │   │  │
│  │  │                     │                                     │   │  │
│  │  │  DEST reg [1024 rows × 16 cols × 16-bit]  ◄─────────────  │   │  │
│  │  │                     │                                     │   │  │
│  │  │  ┌──────────────────▼──────────────────────────────────┐ │   │  │
│  │  │  │               tt_sfpu                               │ │   │  │
│  │  │  │   4 local regs × 32-bit, 4-row parallel LOAD/MAD/  │ │   │  │
│  │  │  │   STORE, polynomial activation evaluation           │ │   │  │
│  │  │  └─────────────────────────────────────────────────────┘ │   │  │
│  │  └───────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │              tt_t6_l1  (L1 SRAM)                                  │  │
│  │  16 banks × 128-bit ECC, multi-client superarb                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Module Instantiation Hierarchy

```
tt_tensix_with_l1
├── tt_tensix
│   ├── tt_instrn_engine_wrapper
│   │   ├── tt_instrn_engine
│   │   │   ├── tt_brisc  (BRISC thread — general control)
│   │   │   ├── tt_trisc [0]  (Unpack thread)
│   │   │   │   └── tt_trisc_cache  (I-cache, SECDED ECC)
│   │   │   ├── tt_trisc [1]  (Math thread)
│   │   │   ├── tt_trisc [2]  (Pack thread)
│   │   │   ├── tt_instruction_buffer [×4]
│   │   │   ├── tt_instruction_thread [×4]
│   │   │   ├── tt_stall_scoreboard
│   │   │   ├── tt_replay_unit → tt_replay_buffer
│   │   │   ├── tt_mop_config
│   │   │   ├── tt_mop_decode
│   │   │   │   ├── tt_mop_decode_math_loop
│   │   │   │   └── tt_mop_decode_unpack_loop
│   │   │   ├── tt_compute_decoder_v1
│   │   │   ├── tt_sync_exu
│   │   │   ├── tt_dest_sync
│   │   │   ├── tt_cluster_sync  (semaphores)
│   │   │   │   └── tt_cluster_sync_semaphore [×16]
│   │   │   ├── tt_mutex + tt_semaphore_reg
│   │   │   ├── tt_droop_trigger_detector
│   │   │   ├── tt_power_ramp_fsm
│   │   │   └── tt_err_aggregate
│   │   └── tt_tdma
│   │       ├── tt_tdma_instrn_decoder
│   │       ├── tt_tdma_xy_address_controller [×2 unpack, ×2 pack]
│   │       ├── tt_unpack_row [×2]
│   │       │   └── tt_word_assembler
│   │       ├── tt_uncompress [×2]
│   │       ├── tt_unpacker_gasket_fmt_conv [×2]
│   │       ├── tt_pack_row [×2]
│   │       ├── tt_packer_gasket_misc_ops [×2]
│   │       ├── tt_dstac_to_mem [×2]
│   │       └── tt_tdma_rr_interface_arbiter
│   ├── tt_fpu_gtile [0..3]          (4 G-Tiles in parallel)
│   │   ├── tt_fpu_v2
│   │   │   ├── tt_srca_reformat
│   │   │   └── tt_fpu_mtile [×N]
│   │   │       ├── tt_fpu_tile [×cols]
│   │   │       │   ├── tt_fpu_tile_srca
│   │   │       │   │   └── tt_srca_lane_sel [×rows]
│   │   │       │   ├── tt_fpu_tile_srcb
│   │   │       │   │   └── tt_srcb_lane_sel [×rows]
│   │   │       │   └── tt_fp_lane [×FP_TILE_MMUL_ROWS]
│   │   │       │       ├── tt_fp_mul_raw [×MULT_PAIRS]
│   │   │       │       ├── tt_exp_path_v4
│   │   │       │       │   ├── tt_parallel_max_exp3
│   │   │       │       │   └── tt_max_exp_9
│   │   │       │       ├── tt_dual_align [×MULT_PAIRS]
│   │   │       │       │   └── tt_barrel_rshift
│   │   │       │       ├── tt_four_two_compressor (tree)
│   │   │       │       ├── tt_three_two_compressor
│   │   │       │       ├── tt_multiop_adder
│   │   │       │       ├── tt_fp_sop_normalize
│   │   │       │       └── tt_t6_com_stoch_rnd
│   │   │       └── tt_reg_bank  (SRCA/SRCB register file)
│   │   ├── tt_sfpu
│   │   │   ├── tt_sfpu_wrapper
│   │   │   ├── tt_sfpu_lregs
│   │   │   └── tt_t6_com_sfpu_mad
│   │   │       └── (uses tt_t6_com_sfpu_comp_adder, lzeroes32)
│   │   ├── tt_reg_bank  (DEST register file)
│   │   ├── tt_fpu_safety_ctrl
│   │   ├── tt_t6_com_prng [×per-column]
│   │   └── tt_t6_com_elem_to_mx_convert  (MX format packer path)
│   ├── tt_t6_global_regs
│   │   └── tt_t6_csr_arbiter
│   ├── tt_t6_debug_regs
│   └── tt_err_aggregate  (tile-level)
└── tt_t6_l1  (L1 SRAM — outside tt_tensix)
    ├── tt_t6_l1_superarb
    │   ├── tt_t6_l1_arb [×banks]
    │   └── tt_t6_l1_rr_arb_tree
    ├── tt_t6_l1_superbank [×bank-groups]
    │   ├── tt_t6_l1_bank [×banks]
    │   │   └── tt_t6_l1_sub_bank_atomic
    │   └── tt_t6_l1_pipe / tt_t6_l1_gated_pipe
    └── tt_t6_l1_flex_client_port [×clients]
```

### 2.3 Data-Flow Diagram (Tensor Operation)

```
                    NoC (i_flit_in / o_flit_out)
                            │
                    ┌───────▼───────┐
                    │  Dispatch Eng │  (row 1 of grid — fills L1)
                    └───────┬───────┘
                            │ L1 WRITE via NoC2L1
                            ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │                     tt_t6_l1  (16 banks × 128-bit)                  │
 │                                                                      │
 │  weights[BFP/FP16B/INT8]  │  activations[FP16B/FP32]  │  output buf │
 └──────┬──────────────────────────────┬────────────────────────┬───────┘
        │ L1 RD (Unpacker CH0)         │ L1 RD (Unpacker CH1)   │ L1 WR (Packer)
        ▼                              ▼                         ▲
 ┌──────────────┐              ┌───────────────┐        ┌────────────────┐
 │  tt_unpack_  │  fmt_conv    │  tt_unpack_   │        │  tt_pack_row   │
 │  row [CH0]   │ ──────────►  │  row [CH1]    │        │  + misc_ops    │
 │ (word_asm)   │              │  (word_asm)   │        │  (ReLU, scale) │
 └──────┬───────┘              └───────┬───────┘        └────────▲───────┘
        │ SRCA write                   │ SRCB write              │ DEST read
        ▼                              ▼                         │
 ┌────────────────────────────────────────────────────────────┐  │
 │              FPU G-Tile × 4  (tt_fpu_gtile)                │  │
 │                                                            │  │
 │  SRCA reg file [48 rows × 16 cols × 16b]                  │  │
 │  SRCB reg file [48 rows × 16 cols × 16b]                  │  │
 │         │                     │                            │  │
 │    ┌────▼─────────────────────▼──────────────────────┐    │  │
 │    │  FP Lane × 16 (one per column, parallel)        │    │  │
 │    │  8 pairs/cycle: mul→exp_max→align→compress→add  │    │  │
 │    └────────────────────────────────┬────────────────┘    │  │
 │                                     │ 16 × 16-bit results  │  │
 │  DEST reg file [1024 rows × 16 cols × 16b]  ◄─────────────┘  │
 │                     │                                         │
 │  ┌──────────────────▼──────────────────┐                     │
 │  │  tt_sfpu  (4 local regs, 4-row)     │  activations        │
 │  │  LOAD → MAD(×N) → STORE            │ ────────────────────►│
 │  │  GeLU / sigmoid / exp / ReLU        │                      │
 │  └─────────────────────────────────────┘                      │
 └────────────────────────────────────────────────────────────────┘
```

#### 2.3.1 Diagram Annotation — "L1 WRITE via NoC2L1"

The label **"L1 WRITE via NoC2L1"** describes the **ingress path** by which remote tensor data enters the local Tensix tile before any computation.

**What is NoC2L1?**

In Trinity, the network-on-chip (NoC) fabric connects all tiles in a 2D mesh. When a **Dispatch Engine** tile sends a tensor tile to a compute Tensix, the packet travels over the NoC as a sequence of 32-byte flits on the `i_flit_in_req` port of `tt_tensix_with_l1`. Inside the receiving tile, the NoC interface logic converts the flit stream into a 128-bit wide write transaction directed at the local **L1 SRAM** (`tt_t6_l1`).

---

**Why the Dispatch Engine — not the Router — handles L1 writes**

This is a key architectural decision. The Trinity 4×5 grid has three tile types in its top two rows:

```
  Row 0:  NOC2AXI_NE  │  NOC2AXI_N  │  NOC2AXI_N  │  NOC2AXI_NW   (external AXI gateway)
  Row 1:  DISPATCH_E  │   ROUTER    │   ROUTER    │  DISPATCH_W   (dispatch + config row)
  Row 2:  TENSIX      │   TENSIX    │   TENSIX    │  TENSIX       ┐
  Row 3:  TENSIX      │   TENSIX    │   TENSIX    │  TENSIX       ├ compute sub-grid
  Row 4:  TENSIX      │   TENSIX    │   TENSIX    │  TENSIX       ┘
```

The **Router** tile (`trinity_router.sv`) instantiates `tt_noc2axi` but with:
- `ADDR_TRANSLATION_ON = 0`
- `MASTER_ENABLE = 0` / `SLAVE_ENABLE = 0`
- All AXI write ports tied to `'0`

The router is **configuration-only** — it handles EDC ring traffic and APB register access. It does **not** participate in tensor data movement at all.

---

#### 2.3.1a Router Tile — SW Programming Guide

Although the router carries no tensor data, a SW engineer must program it at chip bring-up, kernel launch, and mesh reconfiguration. Everything goes through the **EDC ring** — there is no direct APB path from the host to the router registers.

---

##### What the Router Exposes to SW

The router tile instantiates three SW-accessible subsystems:

```
trinity_router.sv
  ├── tt_noc2axi                         (NoC2AXI register block)
  │     └── tt_noc2axi_local_reg         (APB register file, via EDC APB bridge)
  │           ├── AXI2NOC TLB (16 entries) — address translation
  │           ├── Memory flow thresholds
  │           ├── Timeout/error control
  │           └── Scratch registers
  ├── tt_edc1_noc_sec_controller         (Mesh geometry + node ID CSRs)
  │     └── local_node_id_x/y, mesh_start/stop_x/y, noc_x/y_size, orientation
  └── tt_edc1_apb4_bridge  (EDC node 193)
        └── translates EDC ring tokens → APB read/write to the register block above
```

All register access from the host goes through this chain:

```
Host CPU
    │  write EDC token to EDC ring
    ▼
EDC ring (serial, traverses all tiles in ring order)
    │  arrives at Router tile node_id
    ▼
tt_edc1_apb4_bridge  (EDC node 193 for APB, 192 for mesh CSRs)
    │  state machine: IDLE → SETUP → ACCESS
    ▼
APB bus (internal to router tile)
    │  PADDR, PWDATA, PWRITE, PENABLE, PSEL
    ▼
tt_noc2axi_local_reg  OR  tt_edc1_noc_sec_controller
    │  register written or read
    ▼
EDC ring returns read data back to host
```

---

##### Subsystem 1 — Mesh Geometry (`tt_edc1_noc_sec_controller`, EDC node 192)

These registers define the router's position in the NoC grid and the active mesh boundary. They are set once at chip power-on and not changed during normal operation.

| Register | Width | Default | When to set | Description |
|---|---|---|---|---|
| `local_node_id_x` + `_sel` | 6b | HW strap | Power-on | Override X coordinate of this router tile |
| `local_node_id_y` + `_sel` | 6b | HW strap | Power-on | Override Y coordinate of this router tile |
| `noc_x_size` + `_sel` | 7b | HW strap | Power-on | Total mesh X dimension (number of columns) |
| `noc_y_size` + `_sel` | 7b | HW strap | Power-on | Total mesh Y dimension; also controls harvest column removal |
| `mesh_start_x` + `_sel` | 6b | 0 | Harvest / partition | Lower-left X boundary of active mesh region |
| `mesh_start_y` + `_sel` | 6b | 0 | Harvest / partition | Lower-left Y boundary |
| `mesh_stop_x` + `_sel` | 6b | `noc_x_size−1` | Harvest / partition | Upper-right X boundary of active mesh region |
| `mesh_stop_y` + `_sel` | 6b | `noc_y_size−1` | Harvest / partition | Upper-right Y boundary |
| `node_orientation` | 3b | `NOC_ORIENT_0` | Power-on | Physical orientation of this tile in silicon |
| `endpoint_id` | 32b | HW strap | Rarely | Endpoint identifier for address-based routing |

Each register has a corresponding `_sel` bit. When `_sel=0`, the hardware strap value is used. When `_sel=1`, the SW-written value overrides the strap. This allows post-silicon override of fuse-programmed coordinates.

**EDC write sequence (pseudo-code):**

```c
// EDC node IDs for Router at grid position (col=1, row=1):
#define EDC_NODE_MESH_CFG  make_node_id(NODE_ID_PART_NOC, local_y=1, node_idx=192)
#define EDC_NODE_APB_REG   make_node_id(NODE_ID_PART_NOC, local_y=1, node_idx=193)

// [SW] Set mesh geometry (called once at chip init):
edc_write(EDC_NODE_MESH_CFG, {
    .local_node_id_x_sel = 1,  .local_node_id_x = ROUTER_COL,
    .local_node_id_y_sel = 1,  .local_node_id_y = ROUTER_ROW,
    .noc_x_size_sel      = 1,  .noc_x_size      = GRID_COLS,
    .noc_y_size_sel      = 1,  .noc_y_size      = GRID_ROWS,
    .mesh_start_x_sel    = 1,  .mesh_start_x    = 0,
    .mesh_start_y_sel    = 1,  .mesh_start_y    = 0,
    .mesh_stop_x_sel     = 1,  .mesh_stop_x     = GRID_COLS - 1,
    .mesh_stop_y_sel     = 1,  .mesh_stop_y     = GRID_ROWS - 1,
});
// [HW] EDC ring delivers token to node 192 → noc_sec_controller latches values
```

**Harvest use-case:** To disable a defective column (e.g., col 2), set:
```c
.mesh_stop_x = GRID_COLS - 2   // shrink active mesh to exclude col 2
// NoC DOR routing now treats col 2 as outside mesh — no packets routed there
```

---

##### Subsystem 2 — Address Translation Table (`tt_noc2axi_local_reg`, via APB)

The TLB maps 64-bit host addresses to NoC destinations. The router's NoC2AXI block uses this to translate AXI master transactions into addressed NoC packets. It has **16 entries**, each covering a contiguous address range.

**Register map** (APB base `0x2001000`, accessed via EDC node 193):

| Offset | Register | Width | Description |
|---|---|---|---|
| `0x00` | `MST_WR_MEM_FULL_THRESH` | 12b | AXI AWREADY/WREADY deassertion level — stall AXI master when NoC write buffer has fewer than N free slots |
| `0x04` | `MST_RD_MEM_FULL_THRESH` | 12b | AXI ARREADY deassertion level — stall AXI read when NoC read buffer fills |
| `0x08` | `MST_WR_DISABLE_BYTE_ENABLE` | 1b | 1 = ignore AXI WSTRB, always write full 128-bit word; 0 = honour byte-enable mask |
| `0x10–0x1C` | `SCRATCH[0–3]` | 32b × 4 | Firmware scratch — no HW function; used by SW to leave notes or version stamps |
| `0x20 + n×16` | `TLB_START_ADDR_LO[n]` | 32b | Lower 32 bits of AXI address range start for TLB entry n (n = 0..15) |
| `0x24 + n×16` | `TLB_START_ADDR_HI[n]` | 32b | Upper 32 bits of AXI address range start |
| `0x28 + n×16` | `TLB_END_ADDR_LO[n]` | 32b | Lower 32 bits of AXI address range end |
| `0x2C + n×16` | `TLB_END_ADDR_HI[n]` | 32b | Upper 32 bits of AXI address range end |
| `0x120` | `CHICKEN_REG` | 1b | Debug: disable AXI response generation |
| `0x124` | `DISABLE_AUTOINLINE` | 2b | `[0]` = disable write autoinline; `[1]` = disable read autoinline |
| `0x13C` | `ENABLE_AXI_ERR` | 1b | 1 = generate AXI SLVERR for out-of-range addresses |
| `0x140` | `CNT_POSTED_TIME_OUT_LIMIT` | 16b | Cycles before a posted (fire-and-forget) transaction is flagged as timed out |

**ATT (Address Translation Table)** is a separate block at base `0x2010000`:

| Offset | Register | Description |
|---|---|---|
| `0x00` | `ENABLE_TABLES` | 1b — master enable for ATT lookups |
| `0x04` | `CLK_GATING` | Enable clock gating on ATT SRAM |
| `0x30` | `MASK_TABLE_ENTRY` | Select which mask-table entry to configure |
| `0x38/0x3C` | `MASK_TABLE_EP_LO/HI` | 64-bit endpoint mask for selected entry |
| `0x40/0x44` | `MASK_TABLE_BAR_LO/HI` | 64-bit base address register for endpoint mapping |
| `0x200` | `ROUTING_TABLE_MATCH` | Address pattern for routing lookup hit |
| `0x300–0x37C` | `ROUTING_TABLE_PART_ENTRY[0–31]` | 32 routing partition entries: each maps an address range to an (x,y) NoC coordinate |
| `0x2000–0x207C` | `ENDPOINT_TABLE_ENTRY[0–31]` | 32 endpoint entries: each maps an endpoint ID to an AXI target address |
| `0x08/0x0C` | `DEBUG_LAST_SRC_ADDR_LO/HI` | RO: last source address seen by ATT |
| `0x10/0x14` | `DEBUG_LAST_DEST_ADDR_LO/HI` | RO: last destination address after translation |

**TLB + ATT programming (pseudo-code):**

```c
// [SW] Access via EDC APB bridge (EDC node 193)
// 3-step per register: write EDC cfg → pulse write_trigger → poll completion

// Step 1: Configure memory backpressure thresholds
apb_write(0x2001000, 0x00, 64);   // MST_WR_MEM_FULL_THRESH = 64 (stall at 64 free slots)
apb_write(0x2001000, 0x04, 32);   // MST_RD_MEM_FULL_THRESH = 32

// Step 2: Program TLB entry 0 → covers Tensix L1 region (example: 0x0000_0000 – 0x0FFF_FFFF)
apb_write(0x2001020, 0x00, 0x00000000);  // TLB_START_ADDR_LO[0]
apb_write(0x2001024, 0x00, 0x00000000);  // TLB_START_ADDR_HI[0]
apb_write(0x2001028, 0x00, 0x0FFFFFFF);  // TLB_END_ADDR_LO[0]
apb_write(0x200102C, 0x00, 0x00000000);  // TLB_END_ADDR_HI[0]

// Step 3: Enable ATT
apb_write(0x2010000, 0x00, 0x1);         // ENABLE_TABLES = 1

// Step 4: Program routing table entry 0 → address 0x0000_0000 → NoC (x=2, y=2)
apb_write(0x2010200, 0x00, 0x00000000);  // ROUTING_TABLE_MATCH address
apb_write(0x2010300, 0x00,               // ROUTING_TABLE_PART_ENTRY[0]
    (2 << NOC_X_SHIFT) | (2 << NOC_Y_SHIFT));

// Step 5: Leave scratch register for debug
apb_write(0x2001010, 0x00, 0xDEAD_CAFE); // SCRATCH[0] = SW version stamp
```

---

##### Subsystem 3 — EDC APB Bridge (`tt_edc1_apb4_bridge`, EDC node 193)

The bridge itself is programmed by the act of sending EDC tokens to node 193. Its internal FSM translates each incoming EDC token into one APB transaction:

```
Bridge FSM states:
  IDLE ──(edc_pulse_write_trigger)──► SETUP
  SETUP ──(1 cycle)──────────────────► ACCESS
  ACCESS ──(PREADY from slave)────────► IDLE
                                        │ (read: return data on EDC ring)

EDC token structure to node 193:
  edc_config_out[0]     = transaction type  (0=read, 1=write)
  edc_config_out[1..3]  = APB address       (16-bit, 3 EDC config regs)
  edc_config_out[4..6]  = APB write data    (32-bit, across 3 regs)
  edc_pulse_out[0]      = write_trigger     (fires IDLE→SETUP)
  edc_pulse_out[1]      = read_trigger      (fires IDLE→SETUP, read mode)

Read completion:
  edc_capture_event[0]  = 1 when PREADY received and read data available
  edc_config_in[0..1]   = APB read data returned (32-bit across 2 regs)
```

In practice, the host firmware wraps this as:

```c
// [SW] Generic APB write through EDC bridge:
void apb_write(uint32_t router_y, uint32_t apb_addr, uint32_t data) {
    uint32_t edc_node = make_edc_node(NODE_ID_PART_NOC, router_y, 193);
    edc_write_cfg(edc_node, CFG_REG_0, 1);           // [0] = write
    edc_write_cfg(edc_node, CFG_REG_1, apb_addr & 0xFFFF);  // address LO
    edc_write_cfg(edc_node, CFG_REG_2, apb_addr >> 16);     // address HI
    edc_write_cfg(edc_node, CFG_REG_3, data & 0xFFFF);      // data LO
    edc_write_cfg(edc_node, CFG_REG_4, data >> 16);         // data HI
    edc_pulse(edc_node, PULSE_WRITE_TRIGGER);         // fires FSM
    // [HW] bridge executes APB write, IDLE→SETUP→ACCESS
}

// [SW] Generic APB read through EDC bridge:
uint32_t apb_read(uint32_t router_y, uint32_t apb_addr) {
    uint32_t edc_node = make_edc_node(NODE_ID_PART_NOC, router_y, 193);
    edc_write_cfg(edc_node, CFG_REG_0, 0);           // [0] = read
    edc_write_cfg(edc_node, CFG_REG_1, apb_addr & 0xFFFF);
    edc_write_cfg(edc_node, CFG_REG_2, apb_addr >> 16);
    edc_pulse(edc_node, PULSE_READ_TRIGGER);          // fires FSM
    // [HW] bridge executes APB read, waits for PREADY
    while (!edc_capture(edc_node, CAPTURE_READ_DONE)); // poll completion
    uint32_t data_lo = edc_read_cfg(edc_node, CFG_REG_0);
    uint32_t data_hi = edc_read_cfg(edc_node, CFG_REG_1);
    return (data_hi << 16) | data_lo;
}
```

---

##### Full Router Programming Sequence (chip init to kernel launch)

```
[SW] 1. EDC ring init (done by EDC subsystem init code, not kernel SW):
         edc_init_all_nodes();   // sends INIT tokens around ring, establishes node_id table

[SW] 2. Mesh geometry — one write per router tile (2 routers: col=1,row=1 and col=2,row=1):
         edc_write(node_mesh_col1, { node_id_x=1, node_id_y=1,
                                     noc_x_size=4, noc_y_size=5,
                                     mesh_start=0,0, mesh_stop=3,4 });
         edc_write(node_mesh_col2, { node_id_x=2, node_id_y=1, ... });
         // [HW] Routers now know their position; DOR routing tables implicit from coordinates

[SW] 3. Address translation — program TLB for host→NoC address mapping:
         apb_write(router_y=1, TLB_START_LO_0, TENSIX_L1_HOST_BASE);
         apb_write(router_y=1, TLB_END_LO_0,   TENSIX_L1_HOST_BASE + TOTAL_L1_WINDOW);
         apb_write(router_y=1, ROUTING_ENTRY_0, {noc_x=TENSIX_X, noc_y=TENSIX_Y});
         apb_write(router_y=1, ENABLE_TABLES,   1);
         // [HW] Any AXI transaction to TENSIX_L1_HOST_BASE window is now
         //      routed to Tensix[TENSIX_X, TENSIX_Y] via NoC

[SW] 4. Memory backpressure config:
         apb_write(router_y=1, MST_WR_MEM_FULL_THRESH, 64);
         apb_write(router_y=1, MST_RD_MEM_FULL_THRESH, 32);
         apb_write(router_y=1, CNT_POSTED_TIME_OUT_LIMIT, 10000);
         // [HW] Router will stall AXI AWREADY/ARREADY if NoC buffer nearly full

[SW] 5. Kernel launch: (router is no longer touched — all further traffic is NoC data)
         dispatch_kernel(brisc_bin, trisc_bins, tensor_tiles);
         // Tensor data bypasses the router entirely (Dispatch Engine injects directly)
         // Router only carries any future APB config reads if SW polls debug registers

[SW] 6. Debug (optional, post-launch):
         uint32_t last_src  = apb_read(router_y=1, DEBUG_LAST_SRC_ADDR_LO);
         uint32_t last_dest = apb_read(router_y=1, DEBUG_LAST_DEST_ADDR_LO);
         // See last address translation that went through ATT
```

**Key rule for SW engineers:** After step 4, the router is invisible to the kernel. The kernel firmware (BRISC/TRISC) never writes to router registers. The router's job is done at init time. If a routing problem occurs mid-kernel, the only diagnostic path is through the EDC ring debug registers — which are read-only and reflect the last transaction the router saw.

---

The **Dispatch Engine** (`tt_dispatch_top_east` / `tt_dispatch_top_west`) is a dedicated tile with its own NoC injection ports (`i_flit_in_req_south`, `i_flit_in_req_x`, `i_flit_in_req_north`) and a private L1 partition (`tt_disp_eng_l1_partition`). Its responsibilities split cleanly into two independent channels:

| Channel | Transport | Purpose |
|---------|-----------|---------|
| **Data plane** | NoC flit injection (`i_flit_in_req_*`) | Streams tensor tiles as NoC packets addressed to specific Tensix L1 regions |
| **Control plane** | Direct wires (`de_to_t6_t` struct) | Sends 4-bit synchronization signals (`dispatch_to_tensix_sync[3:0]`) per column per clock — zero-latency handshake |

The router tiles in row 1 **pass these control signals through** as feedthroughs (`o_de_west_to_t6_south` ← `i_de_to_t6_east_feedthrough`) so the dispatch engine can reach Tensix columns that are not directly adjacent.

**Why not let the router handle L1 writes?**

1. **Bandwidth mismatch.** The router is designed for low-bandwidth control traffic (APB register reads, EDC ring tokens). A tensor tile is 16×16×2 bytes = 512 bytes — hundreds of flit-beats. Routing this through the NoC2AXI block would serialize config and data on the same path, stalling EDC and config traffic during tensor injection.

2. **Address targeting.** Dispatch tiles know which Tensix L1 address to target for each tensor operand (weight tile, activation tile, output buffer). This is part of the kernel dispatch protocol — a concern entirely separate from mesh routing. Merging it into the router would require the router to maintain kernel state.

3. **Dedicated synchronization signals.** The `de_to_t6_t` / `t6_to_de_t` wires are physical point-to-point connections — not NoC packets. They bypass the NoC entirely for zero-latency semaphore-style control. A router-centric design cannot provide this because the router only forwards NoC flits.

4. **Decoupled control and data rates.** Dispatch can inject data at full NoC bandwidth while the control wires simultaneously negotiate the next kernel launch. Separating the two planes means neither blocks the other.

**Full NoC → L1 data flow:**

```
  tt_dispatch_top_east / west
        │  tensor tile as NoC flit stream
        │  (i_flit_in_req_south → NoC mesh injection)
        ▼
  NoC mesh (rows 2-4, east/west routing)
        │  flit arrives at target Tensix
        │  (i_flit_in_req_north on tt_tensix_with_l1)
        ▼
  NoC Rx interface (inside tt_tensix_with_l1)
        │  flit stream → 128-bit aligned write beat
        ▼
  tt_t6_l1  bank[addr[5:2]]  i_wr_data[127:0], i_wr_en
        │  data stored in L1
        ▼
  BRISC detects semaphore via de_to_t6 sync wire → "L1 tile ready"
        ▼
  TDMA unpacker begins L1 → SRCA/SRCB transfer
```

**Synchronization signal path (control plane):**

```
  tt_dispatch_top_east
        │  o_de_to_t6_south  (dispatch_to_tensix_sync[3:0])
        ▼
  tt_noc_router (row 1)         ← passes through as feedthrough
        │  o_de_east_to_t6_south
        ▼
  tt_tensix_with_l1 (rows 2-4)
        │  i_de_to_t6_north   → BRISC semaphore input
        │
  Feedback: o_t6_to_de_north  → dispatch engine
            (tensix_to_dispatch_sync[3:0][3:0])
```

**Why this architecture (summary):**

1. **Decoupled production and consumption.** The Dispatch Engine fills L1 while the previous tile is still being computed; BRISC uses semaphores to signal when L1 is ready, so the TDMA unpacker never stalls.

2. **128-bit aligned burst width.** L1 is 16 banks × 128 bits. One NoC flit beat maps directly to one L1 bank write — no reassembly needed on ingress.

3. **Separation of I/O and compute bandwidth.** The NoC → L1 path (dispatch) is independent of the TDMA → SRCA path. Both run in parallel: dispatch loads the *next* tile over NoC while the FPU consumes the *current* tile.

4. **Zero-latency control.** The dedicated `de_to_t6` wires provide sub-cycle synchronization between dispatch and BRISC — impossible if control had to traverse the NoC as packets.

---

#### 2.3.2 Diagram Annotation — `word_asm` (`tt_word_assembler`)

**What is `word_asm`?**

`tt_word_assembler` (`tdma/rtl/tt_word_assembler.sv`) is a **width-adaptation shift register** that sits between the 128-bit L1 read bus and the element-width-aware unpacker row logic (`tt_unpack_row`). Its job: take a continuous stream of 128-bit L1 words and deliver elements one-by-one (or two-at-a-time) at the natural element width of the current data format.

**Why is it needed?**

L1 always returns exactly 128 bits per read, but tensor elements have different widths:

| Format | Element width | Elements per 128-bit word |
|--------|--------------|--------------------------|
| FP32   | 32 bits      | 4                        |
| FP16B  | 16 bits      | 8                        |
| FP8    | 8 bits       | 16                       |
| INT8   | 8 bits       | 16                       |
| BFP4   | 4 bits       | 32 (mantissa only)       |
| MXFP4  | 4 bits       | 32                       |

Without `word_asm`, the unpacker would receive a 128-bit blob and need to individually extract each sub-word. `word_asm` absorbs the format-specific unpacking into a single shared module, keeping `tt_unpack_row` format-agnostic.

**How it works:**

```
  L1 read data [127:0]
        │
  ┌─────▼──────────────────────────────────────────┐
  │  tt_word_assembler                              │
  │                                                 │
  │  128-bit shift register + write pointer         │
  │  elem_width config (4/8/16/32)                  │
  │                                                 │
  │  Each cycle: shift out elem_width bits           │
  │  from the LSB of the register                   │
  │  Reload from L1 when pointer exhausted           │
  └─────────────────┬───────────────────────────────┘
                    │ elem_width bits per cycle
                    ▼
           tt_unpack_row (element pipeline)
```

**Why this is architecturally optimal:**
- Single module handles all formats — the unpacker pipeline above and below does not need format-specific mux trees.
- The shift register is purely combinational on the output side (barrel mux), so there is no latency penalty for format switching.
- On the **packer** side, the same module works in reverse: it collects variable-width converted output elements and assembles them back into 128-bit words for the L1 write bus, ensuring aligned burst writes regardless of output element size.

---

#### 2.3.3 Diagram Annotation — "8 pairs/cycle: mul→exp_max→align→compress→add"

This label describes the **FP Lane inner pipeline** — the core MAC engine inside each of the 16 FP Lane columns (`tt_fp_lane.sv`).

**What does "8 pairs/cycle" mean?**

Each FP Lane simultaneously accepts **8 SRCA × SRCB element pairs** per clock cycle — these are 8 consecutive rows from the same column. The 8-way parallelism gives each FP Lane an **8× throughput multiplier** compared to a simple 1-pair-per-cycle MAC.

With 16 FP Lanes (one per column) × 8 pairs = **128 multiply-accumulate operations per cycle per G-Tile**, and with 4 G-Tiles active: **512 MACs/cycle per Tensix tile**.

**What is the pipeline: `mul → exp_max → align → compress → add`?**

This is a pipelined floating-point MAC that keeps all 8 products live simultaneously:

| Stage | Module | What happens |
|-------|--------|-------------|
| **mul** | `tt_fp_mul_raw` × 8 | Each pair: compute `mantissa_A × mantissa_B` → double-width raw mantissa product (20 bits for FP16); compute `exp_A + exp_B` → product exponent (9 bits). Runs 8 instances in parallel. |
| **exp_max** | `tt_exp_path_v4` | Tree-reduce all 8 product exponents plus the accumulator exponent to find the global maximum. Generate `small_shift[i]` flag for exponents far below the max (these products are negligible and the aligner can skip them). |
| **align** | `tt_dual_align` + `tt_barrel_rshift` × 8 | Each product mantissa is right-shifted by `max_exp − prod_exp[i]` so all 8 mantissas are aligned to the same exponent. The barrel shifter is 4-stage (log₂16 bits for FP16). Guard and sticky bits are preserved for correct rounding. |
| **compress** | `tt_four_two_compressor` (Wallace tree) | All 8 aligned mantissas plus the existing accumulator are reduced in two levels of 4:2 compressors (see §6.9), converting 9 numbers into a carry+sum pair. No carry propagation yet — this keeps the adder input to 2 operands. |
| **add** | `tt_multiop_adder` | Final carry-propagate addition of the carry+sum pair → new accumulator value. Optionally applies stochastic rounding from PRNG before writing back to DEST. |

**Why is this structure needed / optimal?**

1. **Multiply first, then align:** Floating-point multiply is a critical path (mantissa multiplier is the widest circuit). By keeping it in the first stage and decoupling it from the exponent normalization, the pipeline can be clocked at the multiply's speed without a combined multiply+align critical path.

2. **exp_max tree before alignment:** Rather than aligning each product relative to the accumulator, the hardware first finds the global max over *all 8 products + accumulator*. This single extra step means every product only needs one shift (not two), halving the alignment hardware.

3. **Wallace tree compressor instead of sequential adds:** Adding 8 numbers sequentially requires 7 carry-propagate adders in series — O(7 × log₂(width)) gate delays. A 2-level Wallace tree reduces 8 inputs to 2 in O(2 × FA-depth) — far fewer gate levels. The final adder is only a single carry-propagate adder.

4. **Dual-output alignment (RNE):** `tt_dual_align` produces two aligned values differing by 1 ULP. When stochastic rounding is off, the standard (unrounded) path is used; when on, the PRNG selects between the two values. This requires zero extra cycles — rounding is baked into the alignment stage.

5. **16-column parallelism:** Each column is independent with its own SRCA/SRCB slice and its own accumulator slice in DEST. There is no cross-column communication in the MAC path, making the datapath linearly scalable.

---

#### 2.3.4 Diagram Annotation — `tt_sfpu  (4 local regs, 4-row)`

**What is the SFPU?**

The **Special Function Processing Unit** (`tt_sfpu.sv`) is a scalar post-processing engine that operates *on the destination register file after the FPU has accumulated results*. It is not part of the main FPU pipeline — it reads from and writes back to DEST, running concurrently with the next FPU tile when pipelined correctly.

**What are the "4 local regs"?**

The SFPU has **4 private 19-bit registers** (`tt_sfpu_lregs`), indexed `lreg[0..3]`. These hold intermediate scalar constants — e.g., the polynomial coefficients for a GELU approximation (`lreg[0] = 0.044715`, `lreg[1] = √(2/π)`, etc.). They are invisible to the main FPU and persist across SFPU instructions within a kernel, so the SW does not need to reload them for every row.

**What is "4-row"?**

The SFPU processes **4 destination register rows simultaneously** per instruction. For a 16-row tile:
- It takes `16 / 4 = 4` SFPU instruction iterations to cover one full tile.
- The 4-row width matches the number of DEST rows accessed per cycle in the FPU's accumulation datapath (the FPU writes 2 rows/cycle from 2 M-Tiles, so SFPU running at 4 rows/iteration keeps pace).

**Why is the SFPU a separate unit and not part of the FPU lane?**

| Concern | FP Lane MAC | SFPU |
|---------|-------------|------|
| Operation type | Multiply-accumulate, fixed | Arbitrary function (exp, tanh, recip, etc.) |
| Critical path | Multiplier width | Iterative Newton-Raphson |
| Data dependency | SRCA/SRCB → DEST (forward) | DEST → DEST (in-place) |
| Parallelism grain | 16 columns × 8 rows | 4 rows, shared across all 16 columns |
| Timing overlap | FPU computing tile N+1 | SFPU post-processing tile N |

The SFPU's computation model — iterative polynomial evaluation with intermediate scalar temporaries — is fundamentally different from the systolic multiply-accumulate pattern. Merging them into one unit would either make the FPU lane critical path longer (iterative loops in the MAC path) or waste area replicating 16 copies of the polynomial evaluation hardware.

**Why "optimal" as a separate post-process stage?**

1. **Overlap with FPU.** While the SFPU runs GELU on DEST buffer A (tile N), the FPU is already accumulating into DEST buffer B (tile N+1). Zero idle cycles when double-buffering is properly orchestrated.

2. **Scalar cost for non-linear functions.** Non-linear activations need only one SFPU unit per tile — not one per column — because the output of each MAC column is an independent scalar. A single 4-row-wide SFPU sweeps through all 16 columns sequentially, amortizing the hardware across all columns.

3. **LOAD/MAD/STORE ISA.** The SFPU ISA is a 3-instruction RISC subset designed for polynomial evaluation loops. `LOAD` brings a DEST row into the internal accumulator; `MAD` performs `acc = acc * src + lreg[k]` (Horner scheme); `STORE` writes back. This minimal ISA is sufficient for all standard activation functions (ReLU, GELU, sigmoid, tanh, softmax normalizer, layernorm reciprocal) without a general-purpose ALU.

4. **lreg persistence.** The 4 local registers hold polynomial coefficients loaded once at kernel launch. For a GELU loop over 32 tiles, coefficients are loaded 1 time and the `MAD` loop body runs 32 × 4 iterations — coefficient reload overhead is negligible.

---

#### 2.3.5 Dispatch Engine → L1: Data Content, HW Traffic Control, and SW Control

This section details exactly **what** the Dispatch Engine sends to Tensix L1, **how** the hardware manages that traffic, and **how** software controls the process.

---

##### Data Content: What Goes into L1

The Dispatch Engine sends two categories of data, distinguished by the destination address in the NoC packet header:

| Category | Content | Destination |
|----------|---------|-------------|
| **Tensor tiles** | Raw numeric data in storage format (FP16B, BFP8, INT8, MXFP4, …) | Tensix L1 weight / activation / output regions |
| **Kernel binaries** | RISC-V instruction words for BRISC / TRISC0/1/2 | Tensix L1 instruction region (loaded into TRISC LDM / I-cache) |

Both arrive as **NoC flit packets** — there is no separate transport mechanism. The packet header address field determines whether the payload lands in the data region or the instruction region of L1.

**NoC packet structure:**

```
Packet = [ HEAD flit ] [ DATA flit × N ] [ TAIL flit ]

HEAD flit  (2048 bits):
  ┌────────────────────────────────────────────────────────┐
  │  dst_x[5:0]  dst_y[5:0]  dst_addr[31:0]               │
  │  src_x[5:0]  src_y[5:0]                                │
  │  flit_type[2:0] = 3'b001  (NOC_HEAD_FLIT)              │
  │  vc[3:0]                  (virtual circuit 0-15)        │
  │  payload[remaining bits]: first bytes of tensor data   │
  └────────────────────────────────────────────────────────┘

DATA flit  (2048 bits):
  ┌────────────────────────────────────────────────────────┐
  │  flit_type[2:0] = 3'b010  (NOC_DATA_FLIT)              │
  │  payload[2045 bits]: raw tensor / instruction bytes    │
  └────────────────────────────────────────────────────────┘

TAIL flit  (2048 bits):
  ┌────────────────────────────────────────────────────────┐
  │  flit_type[2:0] = 3'b100  (NOC_TAIL_FLIT)              │
  │  payload: last bytes                                   │
  └────────────────────────────────────────────────────────┘

Max packet size: 256 flits × 256 bytes/flit = 64 KB
Typical tensor tile: 16×16×2B = 512B → 2 DATA flits
```

**Dispatch Engine private L1** (`tt_disp_eng_l1_partition`): Before injecting packets into the mesh NoC, the dispatch engine first assembles tensor data in its own private L1 SRAM (separate from Tensix L1). This acts as a **staging buffer**: the host fills the dispatch L1 over AXI, and the dispatch engine then re-packages that data as NoC packets targeted to specific Tensix L1 addresses.

---

##### HW Traffic Control — How the Hardware Manages the Data Flow

**1. Credit-based virtual-circuit flow control**

The NoC uses a **per-VC credit** system with 16 virtual circuits (VCs):

```
Sender (Dispatch Engine):
  tracks credits[vc] per output port
  only sends a flit when credits[vc] > 0
  decrements credits[vc] on each flit sent

Receiver (Tensix NoC Rx / router hop):
  increments credits[vc] in noc_resp_t.chan_credit[vc]
    when an ingress buffer slot becomes free
  asserts noc_resp_t.chan_stall if all VCs are congested
  asserts noc_resp_t.chan_backoff[vc] for per-VC congestion
```

This prevents any flit from being injected unless the downstream buffer has space, eliminating dropped packets entirely. Tensor data VCs and control-traffic VCs are separated, so congestion on the compute path never stalls config writes.

**2. Address decoding inside `tt_disp_eng_noc_niu_router`**

When a packet arrives at a Tensix tile, the NIU (NoC Interface Unit) inside `tt_disp_eng_noc_niu_router` decodes the `dst_addr[31:0]` field from the HEAD flit to produce an L1 bank transaction:

```
dst_addr[31:0]
  [5:0]   → L1 superbank select
  [11:6]  → bank within superbank
  [17:12] → row address
  [23:18] → lane (sub-bank) address

decoded → t6_l1_sbank_wr_intf  (L1 write port interface)
        → t6_l1_arb_intf       (L1 superarbitrator)
```

The arbitrator (`tt_t6_l1_superarb`) then schedules the write against concurrent L1 clients (TDMA unpacker, TDMA packer, BRISC load/store).

**3. Phase-based bank scheduling**

Inside the dispatch engine's own L1 wrapper (`tt_disp_eng_l1_wrap2`), a free-running 2-bit phase counter controls bank access timing:

```
l1_phase_root[1:0]  cycles 0→1→2→3→0 every clock

→ o_l1_phase_root_to_ovl   (overlay/host AXI port)
→ o_l1_phase_root_to_noc   (NoC injection port)
```

Even-phase cycles serve one bank group; odd-phase cycles serve another. This prevents read-after-write bank conflicts when the host is writing new tensor data into dispatch L1 at the same time the dispatch engine is reading to inject it into the NoC.

**4. `de_to_t6` / `t6_to_de` synchronization wires**

These are **physical point-to-point wires** (not NoC traffic), providing zero-latency hardware handshake between the dispatch tile and each Tensix column:

```
de_to_t6_t.dispatch_to_tensix_sync[3:0]  (dispatch → Tensix)
  [0]: data_valid  — dispatch has finished writing tensor tile to Tensix L1
  [1]: ready       — dispatch ready to accept next ack
  [2]: fence_req   — dispatch requests a synchronization fence
  [3]: status/err  — error or extended status

t6_to_de_t.tensix_to_dispatch_sync[3:0][NumTensixY]  (Tensix → dispatch, per row)
  [0]: ack         — Tensix BRISC has read the tile from L1
  [1..3]: status   — BRISC kernel progress feedback
```

The signal path through the grid (dispatch tile → router feedthrough → Tensix column):

```
tt_dispatch_top_east
  └── o_de_to_t6_south
        │
  tt_noc_router (row 1)   ← passes through as feedthrough
  o_de_east_to_t6_south = i_de_to_t6_west_feedthrough
        │
  tt_tensix_with_l1 (rows 2-4)
  i_de_to_t6_north  →  BRISC sync input
```

**5. FIFOs and buffers in the path**

| Buffer | Location | Depth | Purpose |
|--------|----------|-------|---------|
| Ingress VC FIFO (N/W/E ports) | Tensix NoC Rx | `ROUTER_REMOTE_INPUT_BUF_SIZE` flits | Absorbs burst traffic per virtual circuit |
| Packet reassembly buffer | NIU router | 1 packet | Holds head flit until tail arrives before issuing L1 write |
| L1 write queue | `tt_t6_l1_superarb` | 4 entries | Queues L1 write requests from all clients (NoC, TDMA, BRISC) |
| Dispatch L1 staging | `tt_disp_eng_l1_partition` | per-config | Holds tensor data before NoC injection |

---

##### SW Control — How Software Programs the Dispatch

---

###### A. What is "FDS"?

**FDS = Fast Dispatch System.** It is the hardware subsystem that manages automated, periodic tensor-tile distribution from the Dispatch Engine to Tensix tiles. FDS is not a protocol — it is a named block inside the Dispatch tile, consisting of:

| Component | File | Role |
|-----------|------|------|
| `tt_fds.sv` | `overlay/rtl/fds/` | Core FSM: auto-dispatch counter, FIFO pop, CDC |
| `tt_fds_wrapper.sv` | `overlay/rtl/fds/` | Wires FDS to the dispatch/tensix sync bus |
| `tt_fds_regfile.sv` | `overlay/rtl/fds/` | Instantiates the register file |
| `tt_fds_dispatch_reg.sv` | `overlay/meta/fds_registers/rtl/` | Top-level register wrapper (APB interface) |
| `tt_fds_dispatch_reg_pkg.sv` | same | Types and constants for all FDS registers |

**FDS register map** (base `0x0`, total size `0x19C` = 412 bytes, 32-bit data bus):

| Offset | Register | Width | Access | Description |
|--------|----------|-------|--------|-------------|
| `0x000` | `dispatch_to_tensix` | 4b | `swwe` | SW writes a 4-bit value; hardware strobes the `de_to_t6` sync wires on the write event (write-enable strobe, not a level) |
| `0x004–0x07F` | `tensix_to_dispatch[32]` | 4b×32 | HW-write | HW updates this when each of 32 Tensix sources toggles its `t6_to_de` wire; SW polls here to detect tile-computation completion |
| `0x084` | `filter_count_threshold` | 32b | `swmod` | Rate-limiter: dispatch packets below this count threshold are dropped |
| `0x088–0x0B7` | `groupID_status[16]` | 32b×16 | RO | Bitmap: bit N = group N has in-flight packets |
| `0x0C8–0x0F7` | `groupID_enable[16]` | 32b×16 | RW | Enable mask: which sources belong to group N |
| `0x108–0x137` | `groupID_count_threshold[16]` | 8b×16 | RW | Saturation limit per group |
| `0x148–0x177` | `groupID_count[16]` | 8b×16 | RO | Current packet count per group (saturating 8-bit) |
| `0x188` | `interrupt_enable` | 16b | RW | Per-group interrupt enable (bit N = group N) |
| `0x18C` | `auto_dispatch_en` | 1b | RW | 1 = FDS auto-dispatch active |
| `0x190` | `auto_dispatch_cycle_count` | 32b | RW | Period in clock cycles between automatic dispatch pulses |
| `0x194` | `auto_dispatch_outbox_address` | 32b | RW | Address in dispatch L1 of the command FIFO outbox |
| `0x198` | `auto_dispatch_fifo_full` | 1b | RO | 1 = internal 4-entry command FIFO is full |

The `swwe` access type on `dispatch_to_tensix` means: **the register has a software-write-enable strobe** — the act of writing to the register (regardless of value) fires a one-cycle pulse on the `de_to_t6` wires. Writing it again fires another pulse. It is not a sticky level.

---

###### B. What is "descriptor FIFO" / auto-dispatch mode?

The term "descriptor FIFO" in the earlier text was imprecise. Here is what actually exists in RTL:

**The hardware FIFO inside FDS** (`tt_fds.sv`) is a **4-entry, 4-bit-wide command opcode FIFO**:

```
tt_fifo #(
  .WIDTH(4),          // BUS_OUT_W = 4 bits per entry
  .DEPTH(4)           // 4 entries (IS_DISPATCH=1 case)
)  auto_dispatch_fifo
```

Each 4-bit entry is a **command opcode** — a tiny token that points to a full dispatch descriptor stored in **dispatch L1 SRAM**. The FIFO does not hold tensor data, addresses, or sizes — only the 4-bit opcode that selects which descriptor in L1 to execute next.

**How auto-dispatch works (RTL-verified FSM):**

```
SW programs:
  auto_dispatch_cycle_count ← N   (period in clocks, e.g. 8)
  auto_dispatch_outbox_address ← L1 address of descriptor table
  auto_dispatch_en ← 1

SW pushes command opcode into FIFO by writing to outbox_address register:
  reg_write(auto_dispatch_outbox_address, opcode)
  → ad_outbox_wr_req asserted
  → ad_push_fifo pulses (rising edge of wr_req & ~fifo_full)
  → opcode enters auto_dispatch_fifo

FDS counter FSM (every clock):
  if (count == 0) and (fifo not empty) and (output CDC ready):
    ad_pop_fifo pulses → 4-bit opcode read from FIFO → sent to output CDC FIFO
    opcode arrives at dispatch engine → triggers L1 read of full descriptor
    (descriptor in dispatch L1 contains: dst_xy, dst_addr, tensor_size, group_id)
    → dispatch injects NoC packets for that descriptor
    count ← 1
  else if (count == auto_dispatch_cycle_count):
    count ← 0   (ready to pop next opcode)
  else:
    count ← count + 1
```

**Visualization:**

```
Host CPU (once, at kernel launch)
  │  reg_write(outbox_addr, opcode_0)  ─────►  4-entry FIFO: [op0]
  │  reg_write(outbox_addr, opcode_1)  ─────►  4-entry FIFO: [op0, op1]
  │  reg_write(outbox_addr, opcode_2)  ─────►  4-entry FIFO: [op0, op1, op2]
  │  reg_write(auto_dispatch_en, 1)

  FDS counter runs:
  every N clocks: pop opcode → dispatch engine reads full descriptor from L1
                            → injects tensor tile as NoC packets to Tensix
  host CPU is NOT involved in each tile dispatch
  host only receives interrupt when groupID_count[N] saturates or interrupt_enable fires
```

The "descriptor" is the **full entry in dispatch L1** (dst_xy, dst_addr, tensor size, group ID). The FIFO holds only the 4-bit token that selects it. The host "pre-fills the descriptor FIFO" by writing those 4-bit opcodes before enabling auto-dispatch.

---

###### C. What is `de_to_t6_sync`, `SEM_L1_READY`, and how does the handshake work exactly?

**Is it hardware or software?** The answer is: **both, in distinct layers.** Here is the exact breakdown:

**Layer 1 — Hardware: NoC write and wire assertion (fully automatic, no firmware)**

```
Dispatch Engine (HW)
  └── injects NoC packet → Tensix receives flit → L1 SRAM write completes
        │  (this is pure hardware, no firmware involved)
        ▼
  Dispatch HW asserts de_to_t6.dispatch_to_tensix_sync[0] = 1
  (the physical wire from dispatch tile to Tensix tile)
  This is also reflected in the FDS register tensix_to_dispatch[N] by HW
```

The `dispatch_to_tensix_sync` wires are **level signals driven by dispatch HW logic** in `tt_fds_wrapper.sv`. They go high when the dispatch HW decides the L1 write is complete. No CPU instruction triggers this — it happens automatically when the NoC packet tail flit is acknowledged.

**Layer 2 — Firmware: BRISC busy-wait poll (software loop, not a hardware stall)**

BRISC (the RISC-V CPU in the Tensix tile) runs a firmware spin loop. It reads the CSR register that mirrors the `dispatch_to_tensix_sync` wire:

```c
// BRISC firmware — busy-wait loop (SW control)
while (read_csr(DE_TO_T6_SYNC_CSR) == 0) {
    // spin — no hardware stall, BRISC executes NOP/branch each cycle
}
// de_to_t6_sync[0] is now 1 → dispatch has finished writing tensor tile to L1
```

This is **not** a hardware stall (the CPU is not frozen by hardware). BRISC actively executes the loop body each cycle, reading the CSR. The hardware only provides the register that BRISC reads; the waiting behavior is a firmware decision.

**Layer 3 — Firmware: `SEM_L1_READY` semaphore post (SW control via HW atomic operation)**

Once BRISC detects the sync wire, it posts a semaphore to wake TRISC0:

```c
// BRISC firmware — posts semaphore to unblock TRISC0
sem_post(SEM_L1_READY);
```

**What is `SEM_L1_READY`?** It is a **software-named slot in the `tt_cluster_sync` hardware semaphore block** (`tt_tensix_common/rtl/tt_cluster_sync.sv`). The hardware provides 16 semaphore slots, each with a 16-bit atomic counter. `SEM_L1_READY` is the firmware's name for one of those 16 slots.

```
tt_cluster_sync (hardware):
  sem[0..15]: 16-bit atomic counters
  Operations: GET (decrement, block if 0), POST (increment), INIT (set value)

BRISC firmware: sem_post(SEM_L1_READY)
  → issues ATINCGET instruction targeting sem[SEM_L1_READY_INDEX]
  → tt_cluster_sync atomically increments sem[N] by 1
  → if TRISC0 was blocked on sem_wait(SEM_L1_READY), it unblocks
```

`sem_post` is **one RISC-V instruction** (`ATINCGET` or similar custom atomic). It is implemented in hardware by `tt_cluster_sync` — not a software spinlock. It is:
- **SW in terms of control** — firmware decides when to call it
- **HW in terms of execution** — the increment and wake-up is atomic hardware

**Layer 4 — TRISC0 unblocks (hardware wake-up)**

TRISC0 executes `sem_wait(SEM_L1_READY)` which issues an `ATGETM` or `ATDECGET` instruction to `tt_cluster_sync`. If the counter is 0, the instruction stalls the TRISC0 CPU in hardware until the counter becomes non-zero. When BRISC's `sem_post` increments it, TRISC0's stall is released by hardware logic inside `tt_cluster_sync` — no firmware polling needed on the TRISC0 side.

**Complete layer-by-layer flow:**

```
┌─ LAYER 1: HARDWARE (automatic) ─────────────────────────────────────────────┐
│  Dispatch HW injects NoC packets → Tensix L1 SRAM write completes           │
│  Dispatch HW asserts dispatch_to_tensix_sync[0] wire                        │
└──────────────────────────────────────────────────────────────────────────────┘
        │ physical wire to Tensix, reflected in FDS CSR
        ▼
┌─ LAYER 2: FIRMWARE (BRISC busy-wait poll — SW control) ─────────────────────┐
│  BRISC: while (read_csr(DE_TO_T6_SYNC_CSR) == 0) { spin; }                  │
│  BRISC exits loop when sync wire goes high                                   │
└──────────────────────────────────────────────────────────────────────────────┘
        │ BRISC decides data is in L1
        ▼
┌─ LAYER 3: FIRMWARE + HW ATOMIC (BRISC sem_post — SW call, HW execution) ───┐
│  BRISC: sem_post(SEM_L1_READY)                                               │
│  → ATINCGET instruction → tt_cluster_sync increments sem[N]                 │
└──────────────────────────────────────────────────────────────────────────────┘
        │ counter goes 0→1
        ▼
┌─ LAYER 4: HARDWARE (TRISC0 stall release — automatic) ──────────────────────┐
│  TRISC0 was stalled at ATGETM on sem[N]                                      │
│  tt_cluster_sync detects count > 0 → releases TRISC0 CPU stall              │
│  TRISC0 proceeds to execute UNPACR / TDMA unpack sequence                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Summary table — what is HW vs SW for each step:**

| Step | Mechanism | HW or SW? |
|------|-----------|-----------|
| NoC L1 write | NoC flit transport → SRAM write | **HW automatic** |
| `de_to_t6` wire assertion | FDS wrapper drives level signal | **HW automatic** |
| BRISC detects sync | Firmware spin loop reading CSR | **SW (busy-wait)** |
| `sem_post(SEM_L1_READY)` | Firmware calls ATINCGET instruction | **SW call, HW execution** |
| TRISC0 unblocks | `tt_cluster_sync` stall release | **HW automatic** |
| `t6_to_de` ack | Firmware writes result sync CSR | **SW call, HW drives wire** |
| `tensix_to_dispatch` register update | FDS HW samples wire | **HW automatic** |

---

**SW dispatch sequence (host-side, corrected):**

```c
// 1. Load tensor tile into dispatch L1 via AXI (host fills dispatch L1 staging)
axi_write(DISPATCH_L1_BASE + tile_offset, tensor_data, tile_size_bytes);

// 2. Push 4-bit command opcode into FDS auto-dispatch FIFO
//    (full descriptor—dst_xy, dst_addr, size—already in dispatch L1 at tile_offset)
reg_write(FDS_AUTO_DISPATCH_OUTBOX_ADDR, opcode);   // pushes opcode into 4-entry FIFO

// 3. Set repeat period and enable auto-dispatch
reg_write(FDS_AUTO_DISPATCH_CYCLE_COUNT, N_CLOCKS);
reg_write(FDS_AUTO_DISPATCH_EN, 1);
// → FDS now automatically pops opcode, reads descriptor from L1, injects NoC packets
//   every N_CLOCKS — no host intervention needed per tile

// 4. Optionally enable interrupt on group completion instead of polling
reg_write(FDS_INTERRUPT_ENABLE, 1 << group_id);
// → interrupt fires when tensix_to_dispatch[N] is set by HW after BRISC acks
```

---

#### 2.3.6 Auto-Dispatch FSM — Full Diagram and Explanation

`tt_fds.sv` contains **three cooperating implicit state machines** plus a CDC FIFO. There is no explicit `enum` — the states are encoded in counter values and edge-detector flip-flops.

---

##### FSM 1 — Input Stability Filter (per source, NOC clock domain)

**Purpose:** Debounce and validate each incoming `t6_to_de` or `de_to_t6` wire. A signal must remain stable for `filter_count_threshold` consecutive cycles before it is accepted as a valid input event.

**Parameters:** `NUM_SOURCES = 3`, `AD_COUNTER_WIDTH = 32`; default threshold = 8 cycles.

**State:** `filter_count_q[src]` — 32-bit saturation counter per source.

```
                          stable_data[src] = 0
              ┌─────────────────────────────────────┐
              │  (input changed → reset counter)    │
              ▼                                     │
        ┌──────────┐   stable_data[src]=1           │
        │  IDLE    │   & !pause_count[src]          │
  reset │  count=0 ├───────────────────────────────►│
  ──────►          │                                │
        └──────────┘                                │
              ▲  stable_data[src]=1                 │
              │  & pause_count[src]     ┌───────────┴──────────────┐
              │  (hold)                 │  COUNTING (count=1..N-1) │
              │                        │  count++ each cycle       │
              └────────────────────────┤  stable_data=1 & !pause   │
                                       └───────────┬───────────────┘
                                                   │ count == filter_count_threshold
                                                   ▼
                                        ┌──────────────────────┐
                                        │  VALID               │
                                        │  count == threshold  │
                                        │  filter_valid[src]=1 │
                                        │  → push to input CDC │
                                        └──────────────────────┘
                                                   │ pause_count[src]=1
                                                   │ (saturate, hold here)
                                                   └──────────────────────┘
```

**Signal definitions:**
- `stable_data[src]` = `i_bus[src] == input_bus_q[src]` (current == 1-cycle-delayed)
- `filter_valid[src]` = `filter_count_q[src] == filter_count_threshold_noc_clk_q`
- `pause_count[src]` = `(count == threshold+1)` OR `input_bus_cdc_wr_ready[src] == 0`

**Why it exists:** The `t6_to_de` wires are routed across physical tile boundaries. Without filtering, a glitch or metastability event on any of the 4 wires per column would be interpreted as a completion signal, causing the dispatch engine to re-fire prematurely.

---

##### FSM 2 — Auto-Dispatch Cycle Timer (core clock domain)

**Purpose:** After a command opcode is popped from the FIFO and sent through the CDC, this counter enforces a minimum inter-dispatch interval of `auto_dispatch_cycle_count` clocks. This prevents the dispatch engine from flooding the NoC with back-to-back tile injections.

**Parameters:** `AD_COUNTER_WIDTH = 32`; `ad_cycle_count` = value of `auto_dispatch_cycle_count` register.

**State:** `ad_count_q` — 32-bit counter. Three implicit states:

```
                         reset
                           │
                           ▼
                   ┌──────────────┐
                   │  IDLE        │◄──────────────────────────────────────┐
                   │  count == 0  │                                        │
                   └──────┬───────┘                                        │
                          │  ad_pop_fifo == 1                              │
                          │  (FIFO not empty & CDC ready)                  │
                          │  → pop opcode from FIFO                        │
                          │  → write opcode to output_bus_cdc              │
                          ▼                                                 │
                   ┌──────────────┐   count < ad_cycle_count               │
                   │  COUNTING    ├───────────────────────────────┐        │
                   │  1 ≤ count   │   (increment count each cycle)│        │
                   │  < N         │◄──────────────────────────────┘        │
                   └──────┬───────┘                                         │
                          │  count == ad_cycle_count                        │
                          │  → count_d = 0  (timeout)                      │
                          └────────────────────────────────────────────────►┘
                                               AT_THRESHOLD → back to IDLE
```

**Transition table:**

| Current state | Condition | Next state | Action |
|---|---|---|---|
| IDLE (`count==0`) | `ad_pop_fifo == 0` | IDLE | stay |
| IDLE (`count==0`) | `ad_pop_fifo == 1` | COUNTING (`count=1`) | pop FIFO, send to CDC |
| COUNTING (`0 < count < N`) | always | COUNTING (`count+1`) | increment |
| AT_THRESHOLD (`count==N`) | always | IDLE (`count=0`) | reset, ready for next pop |

**ad_pop_fifo condition** (all must be true simultaneously):
```
ad_pop_fifo = (ad_count_q == 0)        // FSM is in IDLE
            & (~ad_fifo_empty)          // FIFO has an opcode
            & (output_bus_cdc_wr_ready) // CDC FIFO can accept write
```

---

##### FSM 3 — FIFO Push Edge Detector (core clock domain)

**Purpose:** Convert the level signal `ad_outbox_wr_req` (a register write) into a single-cycle pulse `ad_push_fifo`. Without edge detection, holding the register write high would push the same opcode into the FIFO every clock.

**State:** `ad_push_fifo_ed_q` — 1-bit flip-flop.

```
          reset
            │
            ▼
      ┌──────────┐   ad_outbox_wr_req=1 & !ad_fifo_full
      │  LOW     ├─────────────────────────────────────────►  push pulse fires
      │  (ed_q=0)│   ad_push_fifo = ed_d & ~ed_q = 1       (one cycle only)
      └──────────┘
            ▲
            │  (ed_q latches to 1 on next cycle)
            │
      ┌──────────┐   ad_outbox_wr_req deasserts
      │  HIGH    ├──────────────────────────────────────────► no push
      │  (ed_q=1)│   (ed_d = 0, ~ed_q = 0, pulse = 0)
      └──────────┘
```

**Signals:**
```
ad_push_fifo_ed_d = ad_outbox_wr_req & ~ad_fifo_full      // combinational
ad_push_fifo      = ad_push_fifo_ed_d & ~ad_push_fifo_ed_q // rising edge only
ad_outbox_wr_req  = ad_en & arb_reg_cs & arb_reg_wr_en
                  & (arb_reg_addr == ad_outbox_addr)        // write to outbox register
```

---

##### CDC FIFO — Core Clock → NOC Clock Domain Crossing

The output of the auto-dispatch FIFO runs in `core_clk` domain, but the `o_bus` output that drives the `de_to_t6` / `t6_to_de` wires runs in `noc_clk` domain. A `tt_async_fifo_wrapper` (depth 4, width 4) bridges the two:

```
  core_clk domain                    noc_clk domain
  ──────────────────────             ──────────────────────────
  ad_pop_fifo ──► wr_valid           rd_valid ──► o_bus latch
  ad_output_bus ► wr_data  [4b FIFO] rd_data  ──► output_bus_noc_clk
  wr_ready ◄───── wr_ready           (auto-read internally)
```

`wr_valid` is muxed:
- `ad_en == 1`: `wr_valid = ad_pop_fifo` (auto-dispatch path)
- `ad_en == 0`: `wr_valid = output_bus_swmod[1]` (manual SW write to output register)

---

##### Full System Diagram — All Three FSMs Together

```
  HOST CPU (AXI/APB writes)
        │
        │ reg_write(auto_dispatch_outbox_address, opcode)
        │           ──────────┬────────────────────────────────
        │                     │ ad_outbox_wr_req (level)
        │                     ▼
        │            ┌────────────────────┐
        │            │  FSM 3             │
        │            │  Push Edge Detect  │──► ad_push_fifo (1-cycle pulse)
        │            │  (core_clk)        │
        │            └────────────────────┘
        │                     │
        │                     ▼
        │            ┌──────────────────┐
        │            │  4-entry FIFO    │  (4b opcodes, core_clk)
        │            │  tt_fifo         │◄── ad_push_fifo
        │            └────────┬─────────┘
        │                     │ ad_output_bus (4b)
        │                     │ ad_fifo_empty
        │                     ▼
        │            ┌────────────────────┐
        │            │  FSM 2             │
        │            │  Cycle Timer       │──► ad_pop_fifo (when IDLE+!empty+CDC_ready)
        │            │  (core_clk)        │
        │            │  0 → count → N → 0 │
        │            └────────────────────┘
        │                     │ ad_pop_fifo
        │                     ▼
        │            ┌─────────────────────────────┐
        │            │  CDC FIFO  (tt_async_fifo)  │
        │            │  wr_clk: core_clk           │
        │            │  rd_clk: noc_clk            │
        │            │  depth: 4, width: 4         │
        │            └────────────┬────────────────┘
        │                         │ output_bus_cdc_rd_valid
        │                         ▼
        │            ┌────────────────────┐
        │            │  o_bus register    │  (noc_clk)
        │            │  i_harvest_en→0    │
        │            └────────┬───────────┘
        │                     │ o_bus[3:0]
        │                     ▼
        │         tt_fds_wrapper
        │         (IS_DISPATCH=1 mode)
        │                     │
        │       de_to_t6.dispatch_to_tensix_sync[3:0]
        │                     │ (physical wire to Tensix column)
        │                     ▼
        │         Tensix BRISC (CSR read in firmware spin loop)
        │
        │ reg_read(tensix_to_dispatch[N]) ◄─────────────────────┐
        │  (or wait for interrupt)                               │
        │                                                        │
  TENSIX side:                                                   │
        │                                                        │
        │  FSM 1 (per t6_to_de wire, noc_clk)                   │
        │  Stability filter:                                     │
        │  IDLE → COUNTING → VALID                              │
        │  (must be stable for filter_count_threshold cycles)    │
        │         ↓ filter_valid[src]                           │
        │  input_bus_cdc (core_clk domain)                      │
        │         ↓                                             │
        │  FDS regfile: tensix_to_dispatch[N] updated ──────────┘
        │  (host sees completion)
```

---

##### Timing Example: Single Tile Dispatch with auto_dispatch_cycle_count = 4

```
cycle:   0    1    2    3    4    5    6    7    8    9   10   11
         │    │    │    │    │    │    │    │    │    │    │    │
         ├────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤────┤

SW:      │ write outbox │
         │ reg (opcode) │

ed_d:    │    1    │
ed_q:    │         1   │
push:    │    1    │         (one cycle pulse, rising edge)

FIFO:    │ [op0]───────────────────────────────────────────────┐
         │                                                      │

ad_count:│  0  │  0  │  1  │  2  │  3  │  4  │  0  │  0  │  0 │
         │IDLE │POP  │COUNTING────────────────│IDLE │IDLE │    │

ad_pop:  │         1  │         (fires at count==0, FIFO not empty)

CDC wr:  │         1  │  (writes opcode to CDC FIFO)
CDC rd:  │              (noc_clk, 1-2 cycle async lag)
                   ─1─►│ (output_bus_cdc_rd_valid)

o_bus:   │              │──── opcode[3:0] stable ────────────────►
                   (de_to_t6 wire driven to Tensix)

Tensix:  │              │── BRISC detects sync wire high ───────►
                              (after filter_count_threshold cycles)
         │              │    │── sem_post(SEM_L1_READY) ────────►
         │              │    │   │── TRISC0 unblocks, unpack ──►
```

---

##### Why This FSM Architecture?

| Design choice | Reason |
|---|---|
| **Counter-based timer (not token ring)** | Simplest hardware for rate-limiting; no state table needed. `cycle_count` is a SW-programmable register so the rate adapts to any NoC congestion level. |
| **4-entry FIFO, not a ring buffer** | The latency between two consecutive tile dispatches is dominated by the NoC flight time (~10s of cycles), not the SW write. Four entries are enough to keep the pipeline full for one kernel launch without wasting area. |
| **Edge detector on push** | Prevents a single SW register write from continuously pushing the same opcode if the register stays written. The strobe model is safer for a dispatch trigger. |
| **Stability filter on inputs** | `t6_to_de` wires cross tile boundaries in silicon. Filtering for `N` stable cycles prevents metastability events from being interpreted as valid completion signals — directly protecting against false re-dispatch. |
| **CDC FIFO for clock crossing** | `auto_dispatch_cycle_count` and FIFO logic run in `core_clk`; the output bus driving the NoC mesh runs in `noc_clk`. The async FIFO decouples the two without requiring synchronous domain bridging at every output. |
| **`harvest_en` override to zero** | When a column is harvested (disabled due to defects), its `de_to_t6` wires must not carry spurious sync pulses. Hard-zeroing `o_bus` on `harvest_en` ensures no ghost completions reach the dispatch logic from dead columns. |

---

#### 2.3.7 Pseudo-Code: Full Dispatch → L1 → Compute Flow

This section gives annotated pseudo-code for every actor in the system. Each line is tagged:

- `[SW]` — firmware or host software executing a CPU instruction
- `[HW]` — hardware acting automatically, no software instruction needed
- `[SW→HW]` — software writes a register that causes hardware to act

---

##### Actor map

```
HOST CPU          — runs on Arm/x86 host; programs the Dispatch Engine over AXI/APB
DISPATCH ENGINE   — hardware block (tt_dispatch_top, tt_fds); no CPU inside
TENSIX BRISC      — RV32I CPU inside each Tensix tile; runs kernel firmware
TENSIX TRISC0     — RV32I thread; runs unpack (TDMA) firmware
TENSIX TRISC1     — RV32I thread; runs math (FPU/MOP) firmware
TENSIX TRISC2     — RV32I thread; runs pack (TDMA) firmware
NoC FABRIC        — hardware mesh router; moves flits between tiles
L1 SRAM           — shared SRAM inside each Tensix tile (tt_t6_l1)
```

---

##### Phase 0 — One-time kernel load (happens once per kernel, not per tile)

```
// ─── HOST CPU ─────────────────────────────────────────────────────────────

[SW]  axi_write(DISPATCH_L1_BASE + KERNEL_BIN_OFFSET,
                brisc_firmware_binary, sizeof(brisc_bin));
// Loads BRISC firmware image into Dispatch Engine's private L1 staging area.
// Dispatch Engine will later send this to Tensix L1 instruction region.

[SW]  axi_write(DISPATCH_L1_BASE + TRISC0_BIN_OFFSET,
                trisc0_unpack_binary, sizeof(trisc0_bin));
[SW]  axi_write(DISPATCH_L1_BASE + TRISC1_BIN_OFFSET,
                trisc1_math_binary,   sizeof(trisc1_bin));
[SW]  axi_write(DISPATCH_L1_BASE + TRISC2_BIN_OFFSET,
                trisc2_pack_binary,   sizeof(trisc2_bin));
// All four CPU binaries are staged. Dispatch Engine will distribute them.

[SW]  reg_write(FDS_AUTO_DISPATCH_CYCLE_COUNT, 32);
// Set minimum inter-dispatch interval to 32 core_clk cycles.
// This prevents back-to-back NoC injections from overflowing Tensix NoC RX buffers.

[SW]  reg_write(FDS_INTERRUPT_ENABLE, 1 << GROUP_KERNEL_DONE);
// Enable interrupt on group GROUP_KERNEL_DONE so host wakes up when all tiles finish.
```

---

##### Phase 1 — Descriptor setup (once per tile batch)

A "descriptor" is a record stored in Dispatch L1 that describes one dispatch operation. The host writes these records directly into Dispatch L1 over AXI, then pushes a 4-bit opcode token into the FDS FIFO to reference each one.

```
// ─── HOST CPU ─────────────────────────────────────────────────────────────

// Descriptor format (in Dispatch L1, SW-defined structure):
struct dispatch_descriptor_t {
    uint8_t  dst_x, dst_y;     // target Tensix tile grid coordinate
    uint32_t dst_l1_addr;      // byte address in target Tensix L1
    uint32_t byte_count;       // number of bytes to send
    uint8_t  group_id;         // which FDS group to count this under
    uint8_t  opcode;           // 4-bit token that references this descriptor
};

[SW]  // Write descriptor for weight tile → Tensix[2,2]
      axi_write(DISPATCH_L1_DESC_BASE + 0*sizeof(desc), {
          .dst_x       = 2,
          .dst_y       = 2,
          .dst_l1_addr = TENSIX_L1_WEIGHT_BASE,   // e.g. 0x1000
          .byte_count  = TILE_BYTES,               // 512 bytes (16×16×FP16B)
          .group_id    = GROUP_WEIGHT,
          .opcode      = 0x1
      });

[SW]  // Write descriptor for activation tile → Tensix[2,2]
      axi_write(DISPATCH_L1_DESC_BASE + 1*sizeof(desc), {
          .dst_x       = 2,
          .dst_y       = 2,
          .dst_l1_addr = TENSIX_L1_ACT_BASE,      // e.g. 0x2000
          .byte_count  = TILE_BYTES,
          .group_id    = GROUP_ACT,
          .opcode      = 0x2
      });
// (Repeat for all 12 Tensix tiles in the grid.)

[SW]  // Write tensor data for all tiles into Dispatch L1 data region
      axi_write(DISPATCH_L1_DATA_BASE + 0*TILE_BYTES, weight_tile_data, TILE_BYTES);
      axi_write(DISPATCH_L1_DATA_BASE + 1*TILE_BYTES, act_tile_data,    TILE_BYTES);
```

---

##### Phase 2 — Enable FDS auto-dispatch and push opcodes

```
// ─── HOST CPU ─────────────────────────────────────────────────────────────

[SW→HW]  reg_write(FDS_AUTO_DISPATCH_EN, 1);
// Enables FDS FSM. From this point, FDS cycle timer starts running.
// HW: FDS FSM 2 (cycle timer) begins watching ad_fifo_empty.

[SW→HW]  reg_write(FDS_AUTO_DISPATCH_OUTBOX_ADDR, 0x1);
// Push opcode 0x1 (weight descriptor) into 4-entry FDS FIFO.
// HW: FSM 3 (edge detector) fires ad_push_fifo for one cycle.
// HW: 4-bit opcode 0x1 enters tt_fifo. FIFO: [0x1]

[SW→HW]  reg_write(FDS_AUTO_DISPATCH_OUTBOX_ADDR, 0x2);
// Push opcode 0x2 (activation descriptor). FIFO: [0x1, 0x2]

// Host CPU is now done for this batch. FDS runs autonomously.
```

---

##### Phase 3 — FDS hardware auto-dispatch (no CPU)

```
// ─── DISPATCH ENGINE HARDWARE ─────────────────────────────────────────────

[HW]  // FSM 2 (cycle timer): ad_count_q == 0, FIFO not empty, CDC ready
      // → ad_pop_fifo fires
      opcode = fifo_pop();          // pops 0x1
      // ad_count_q transitions: 0 → 1 (starts COUNTING)

[HW]  // Opcode 0x1 written to output_bus_cdc (core_clk side)
      // CDC FIFO crosses to noc_clk domain (1-2 cycle async latency)

[HW]  // noc_clk: output_bus_cdc_rd_valid asserted
      // o_bus[3:0] ← 0x1
      // de_to_t6.dispatch_to_tensix_sync[3:0] ← 0x1 (physical wire driven)

[HW]  // FDS reads full descriptor from Dispatch L1 using opcode 0x1 as index:
      desc = dispatch_l1_read(DISPATCH_L1_DESC_BASE + opcode_to_offset(0x1));
      // desc = {dst_x=2, dst_y=2, dst_l1_addr=0x1000, byte_count=512, group_id=GROUP_WEIGHT}

[HW]  // NIU router formats NoC HEAD flit:
      head_flit = {
          flit_type : NOC_HEAD_FLIT,   // 3'b001
          dst_x     : 2,
          dst_y     : 2,
          dst_addr  : 0x1000,          // Tensix L1 target address
          vc        : VC_DATA          // data virtual circuit
      };

[HW]  // Inject HEAD flit + DATA flits into NoC mesh
      // 512 bytes / 256 bytes-per-flit = 2 DATA flits
      noc_inject(head_flit);
      noc_inject(data_flit_0);   // bytes [0..255] of weight tile
      noc_inject(data_flit_1);   // bytes [256..511] of weight tile
      noc_inject(tail_flit);     // NOC_TAIL_FLIT, signals end of packet

[HW]  // Credit check every flit:
      //   if credits[VC_DATA] == 0: stall injection until receiver returns credit
      //   credits[VC_DATA] decrements by 1 per flit sent
      //   Tensix NoC RX returns credit in noc_resp_t.chan_credit[VC_DATA]
      //   when its ingress VC buffer frees a slot

[HW]  // FSM 2 counts: 1 → 2 → ... → 32 (ad_cycle_count)
      // At count==32: ad_count_d = 0, FSM returns to IDLE
      // → ready to pop next opcode (0x2)

[HW]  // (Same process repeats for opcode 0x2 → activation tile → Tensix L1 0x2000)
```

---

##### Phase 4 — NoC fabric routes packet to Tensix

```
// ─── NoC FABRIC ───────────────────────────────────────────────────────────

[HW]  // DOR (Dimension-Order Routing): route in X first, then Y
      // Dispatch tile at (0,1), target Tensix at (2,2):
      //   X hops: 0→1→2 (east)
      //   Y hop:  1→2   (south)

[HW]  // Each router hop:
      //   check VC credits on output port
      //   forward flit if credit available
      //   return credit to upstream when local buffer slot frees

[HW]  // Packet arrives at Tensix[2,2] NoC RX port i_flit_in_req_north
      // HEAD flit decoded: dst_addr=0x1000 → L1 write target

[HW]  // NIU inside tt_tensix_with_l1:
      //   HEAD flit: decode dst_addr[5:0]=superbank, [11:6]=bank, [17:12]=row
      //   DATA flits: buffer in ingress VC FIFO
      //   TAIL flit received → issue L1 write transaction

[HW]  // tt_t6_l1_superarb: arbitrate L1 write against any concurrent TDMA/BRISC access
      // Write 128 bits (one L1 beat) at a time:
      //   i_addr   ← decoded bank address
      //   i_wr_data[127:0] ← 128b from flit payload
      //   i_wr_en  ← 1
      // Repeat for each 128-bit chunk of the 512-byte tile (4 beats per bank row)

[HW]  // Return NoC credit to Dispatch Engine after each ingress buffer slot freed
```

---

##### Phase 5 — Tensix BRISC detects data ready

```
// ─── TENSIX BRISC FIRMWARE ────────────────────────────────────────────────

[SW]  // BRISC spin-loop: poll de_to_t6 sync CSR
      while (csr_read(CSR_DE_TO_T6_SYNC) == 0) { /* busy wait */ }
      // [HW] de_to_t6.dispatch_to_tensix_sync[0] was asserted by Dispatch Engine
      //      after the last NoC TAIL flit was acknowledged by Tensix NoC RX.
      //      That wire is reflected into CSR_DE_TO_T6_SYNC by hardware.
      // BRISC exits loop when bit goes high.

[SW]  // Optionally verify data integrity (CRC, size check)
      uint32_t actual = l1_read_word(TENSIX_L1_WEIGHT_BASE + HEADER_OFFSET);
      assert(actual == EXPECTED_MAGIC);

[SW→HW]  sem_post(SEM_L1_WEIGHT_READY);
// [SW]  BRISC decides weight tile is in L1 → posts semaphore.
// [HW]  Executes as ATINCGET instruction on tt_cluster_sync slot SEM_L1_WEIGHT_READY.
//       Hardware atomically increments sem[SEM_L1_WEIGHT_READY] from 0 → 1.

[SW→HW]  sem_post(SEM_L1_ACT_READY);
// Same for activation tile (BRISC received second de_to_t6 pulse for opcode 0x2).

[SW]  // BRISC writes ack back to Dispatch Engine
      csr_write(CSR_T6_TO_DE_SYNC, 0x1);
// [HW]  Drives t6_to_de.tensix_to_dispatch_sync[0] wire.
//       FDS FSM 1 (stability filter) samples this wire for filter_count_threshold cycles.
//       Once stable, FDS updates tensix_to_dispatch[tile_index] register.
//       If interrupt_enable[GROUP_WEIGHT] == 1, interrupt fires to host CPU.
```

---

##### Phase 6 — TRISC0/1/2 execute the tile computation

```
// ─── TENSIX TRISC0 (unpack thread) ────────────────────────────────────────

[SW]  sem_wait(SEM_L1_WEIGHT_READY);
// [HW]  Executes as ATGETM on tt_cluster_sync slot SEM_L1_WEIGHT_READY.
//       If sem == 0: TRISC0 CPU stalls in hardware until BRISC posts it.
//       If sem > 0: TRISC0 continues, sem decrements to 0.

[SW]  sem_wait(SEM_L1_ACT_READY);
// Same for activation.

[SW→HW]  // Program TDMA unpacker for weight tile (CH0)
          wrcfg(THCON_UNPACKER0_0, {
              .IN_DATA_FORMAT  = FP16B,
              .OUT_DATA_FORMAT = FP16B,
              .BASE_ADDRESS    = TENSIX_L1_WEIGHT_BASE >> 4,
          });
          wrcfg(THCON_UNPACKER0_1, {
              .TILE_ROWS = 16,
              .TILE_COLS = 16,
          });
// [HW]  Writes configuration registers in tt_thcon_cfg_regs.
//       These control tt_unpack_row address generation and format conversion.

[SW→HW]  // Program TDMA unpacker for activation tile (CH1)
          wrcfg(THCON_UNPACKER1_0, {
              .IN_DATA_FORMAT  = FP16B,
              .OUT_DATA_FORMAT = FP16B,
              .BASE_ADDRESS    = TENSIX_L1_ACT_BASE >> 4,
          });

[SW→HW]  // Issue MOP (hardware loop): unpack 16 rows × both channels
          issue_instrn(MOP_UNPACK, {
              .loop_count = 15,    // 0..15 = 16 rows
              .instrn     = UNPACR // unpack both SRCA and SRCB
          });
// [HW]  tt_mop_config FSM fires UNPACR 16 times.
//       Each UNPACR cycle:
//         tt_tdma_xy_address_controller increments (x,y) address
//         L1 read request issued (128-bit burst)
//         tt_word_assembler extracts elements from 128-bit word
//         tt_unpacker_gasket_fmt_conv converts FP16B → 19-bit extended
//         Result written to SRCA[row] or SRCB[row]

[SW]  sem_post(SEM_UNPACK_DONE);
// TRISC0 signals TRISC1: SRCA/SRCB are loaded.


// ─── TENSIX TRISC1 (math thread) ──────────────────────────────────────────

[SW]  sem_wait(SEM_UNPACK_DONE);
// [HW]  Hardware stall until TRISC0 posts semaphore.

[SW→HW]  // Configure FPU: FP16B multiply-accumulate
          wrcfg(ALU_FORMAT_SPEC_REG, {
              .SrcA   = FP16B,
              .SrcB   = FP16B,
              .Dstacc = FP16B,
          });

[SW→HW]  // Issue math MOP: matrix-vector multiply (MVMUL), 16 rows
          issue_instrn(MOP_MATH, {
              .loop_count = 15,
              .instrn     = MVMUL
          });
// [HW]  FPU G-Tile × 4 executes:
//       Each cycle: 16 FP Lanes × 8 pairs = 128 MACs
//       Pipeline: mul → exp_max → align → compress → add (5 stages)
//       After 16 cycles: DEST reg file rows 0..15 contain accumulated products.

[SW]  sem_post(SEM_MATH_DONE);


// ─── TENSIX TRISC1 (SFPU activation, inline with math) ────────────────────

[SW→HW]  // Load GELU polynomial coefficients into SFPU lregs
          sfpu_load(LREG0, GELU_COEFF_0);   // 0.044715
          sfpu_load(LREG1, GELU_COEFF_1);   // sqrt(2/π)
// [HW]  Each sfpu_load writes 19-bit extended value into tt_sfpu_lregs[N].

[SW→HW]  // SFPU loop over DEST rows, 4 rows per instruction, 4 iterations = 16 rows
          for (int row = 0; row < 16; row += 4) {
              sfpu_load_dest(row);            // LOAD: dest[row..row+3] → sfpu acc
              sfpu_mad(LREG1, LREG0);         // MAD: acc = acc*lreg1 + lreg0 (Horner step 1)
              sfpu_mad(LREG1, LREG0);         // MAD: Horner step 2
              sfpu_store_dest(row);           // STORE: sfpu acc → dest[row..row+3]
          }
// [HW]  tt_sfpu processes 4 rows per instruction cycle.
//       tt_t6_com_sfpu_mad: acc = acc * src + lreg[k] in one FMA cycle.
//       Result written back to DEST via sfpu_dest_intf to tt_fpu_gtile.


// ─── TENSIX TRISC2 (pack thread) ──────────────────────────────────────────

[SW]  sem_wait(SEM_MATH_DONE);

[SW→HW]  // Configure packer CH0: DEST → L1 output buffer, FP16B output
          wrcfg(THCON_PACKER0_0, {
              .OUT_DATA_FORMAT = FP16B,
              .BASE_ADDRESS    = TENSIX_L1_OUTPUT_BASE >> 4,
          });
          wrcfg(THCON_PACKER0_RELU, { .MODE = RELU_ZERO_NEG });
// [HW]  tt_packer_gasket_misc_ops will apply ReLU: replace negative values with 0.

[SW→HW]  // Issue pack MOP: pack 16 rows from DEST → L1
          issue_instrn(MOP_PACK, {
              .loop_count = 15,
              .instrn     = PACR
          });
// [HW]  Each PACR cycle:
//         DEST row[N] read (16 × 16-bit values)
//         tt_packer_gasket_misc_ops: apply ReLU, edge masking
//         tt_dstac_to_mem: convert FP16B → output format
//         tt_word_assembler: assemble 128-bit words
//         L1 write: i_wr_data[127:0] → TENSIX_L1_OUTPUT_BASE + offset

[SW]  sem_post(SEM_PACK_DONE);


// ─── TENSIX BRISC (drain L1 output) ──────────────────────────────────────

[SW]  sem_wait(SEM_PACK_DONE);

[SW→HW]  // Send packed result tile from L1 to next tile or DRAM over NoC
          noc_write(
              dst_x        = NEXT_TILE_X,
              dst_y        = NEXT_TILE_Y,
              dst_l1_addr  = NEXT_TILE_L1_INPUT_BASE,
              src_l1_addr  = TENSIX_L1_OUTPUT_BASE,
              byte_count   = TILE_BYTES
          );
// [HW]  BRISC issues NoC write: Tensix itself becomes a NoC master.
//       Injects HEAD + DATA + TAIL flits targeting the next tile.
//       This reuses the same NoC mesh used by the Dispatch Engine.

[SW→HW]  // Ack back to Dispatch Engine: this tile is complete
          csr_write(CSR_T6_TO_DE_SYNC, 0x1);
// [HW]  Drives t6_to_de wire → FDS updates tensix_to_dispatch register → host interrupt.
```

---

##### Phase 7 — Host CPU receives completion interrupt

```
// ─── HOST CPU ─────────────────────────────────────────────────────────────

[HW]  // Interrupt fires when all 12 tiles have written t6_to_de
      // (FDS groupID_count[GROUP_KERNEL_DONE] reaches threshold)

[SW]  // Interrupt handler: read result from Tensix L1 or DRAM
      axi_read(RESULT_DRAM_BASE, output_tensor, output_size);

[SW]  // Optionally reset FDS for next kernel
      reg_write(FDS_AUTO_DISPATCH_EN, 0);
```

---

##### Example Case: 16×16 FP16B Matrix-Vector Multiply with GELU (one tile, one Tensix)

This is the minimal case — one weight tile (matrix W) × one activation tile (vector x) on one Tensix tile, producing output y = GELU(W × x).

```
Data:
  W = 16×16 matrix, FP16B, 512 bytes, stored at Dispatch L1 offset 0x0000
  x = 16×1  vector, FP16B,  32 bytes, stored at Dispatch L1 offset 0x0200
  y = 16×1  result, FP16B,  32 bytes, output to Tensix L1 at 0x3000

Timeline (cycle-approximate):

Cycle    Event                                          [SW/HW]
────────────────────────────────────────────────────────────────────
  0      Host writes W to Dispatch L1 (AXI burst)      [SW]
  1      Host writes x to Dispatch L1 (AXI burst)      [SW]
  2      Host writes descriptor[0x1]: W→Tensix[2,2]    [SW]
  3      Host writes descriptor[0x2]: x→Tensix[2,2]    [SW]
  4      Host pushes opcode 0x1 to FDS FIFO             [SW→HW]
  5      Host pushes opcode 0x2 to FDS FIFO             [SW→HW]
  6      Host sets auto_dispatch_en = 1                 [SW→HW]

  7      FDS pops opcode 0x1, timer starts              [HW]
  7–10   FDS reads W descriptor from Dispatch L1        [HW]
  10–14  FDS formats NoC HEAD + 2 DATA + TAIL flits     [HW]
  14–20  NoC routes flits to Tensix[2,2] (DOR: 2 hops)  [HW]
  20–24  Tensix L1 SRAM write: 4 × 128-bit beats        [HW]
  24     de_to_t6 sync wire asserted (W in L1)          [HW]

  25     FDS timer reaches N=32, returns to IDLE        [HW]
  25     FDS pops opcode 0x2, timer starts              [HW]
  25–45  Same flow for activation tile x                [HW]
  45     de_to_t6 sync wire asserted again (x in L1)    [HW]

  46     BRISC: csr_read(DE_TO_T6_SYNC) == 1, exits loop [SW]
  46     BRISC: sem_post(SEM_L1_WEIGHT_READY)           [SW→HW]
  46     BRISC: sem_post(SEM_L1_ACT_READY)              [SW→HW]

  47     TRISC0: sem_wait unblocks                      [HW]
  47–48  TRISC0: wrcfg (configure unpacker CH0 + CH1)  [SW→HW]
  49     TRISC0: issue_instrn(MOP_UNPACK, 16 rows)      [SW→HW]
  49–64  HW: 16× UNPACR, L1→SRCA (W) and L1→SRCB (x)  [HW]
         (each UNPACR: L1 read + word_asm + fmt_conv + reg write)
  65     TRISC0: sem_post(SEM_UNPACK_DONE)              [SW→HW]

  66     TRISC1: sem_wait unblocks                      [HW]
  66–67  TRISC1: wrcfg (ALU format = FP16B)             [SW→HW]
  68     TRISC1: issue_instrn(MOP_MATH MVMUL, 16 rows)  [SW→HW]
  68–84  HW: 16× MVMUL                                 [HW]
         (each cycle: 16 FP Lanes × 8 pairs → 128 MACs)
         (5-stage pipeline: mul→exp_max→align→compress→add)
  85     TRISC1: SFPU GELU loop (4 instr × 4 rows)     [SW→HW]
  85–88  HW: 4× (LOAD+MAD+MAD+STORE) on DEST rows 0-15 [HW]
  89     TRISC1: sem_post(SEM_MATH_DONE)                [SW→HW]

  90     TRISC2: sem_wait unblocks                      [HW]
  90–91  TRISC2: wrcfg (packer: FP16B, ReLU=NONE)      [SW→HW]
         (GELU already applied by SFPU — no additional ReLU)
  92     TRISC2: issue_instrn(MOP_PACK, 16 rows)        [SW→HW]
  92–107 HW: 16× PACR, DEST→tt_word_asm→L1[0x3000]     [HW]
  108    TRISC2: sem_post(SEM_PACK_DONE)                [SW→HW]

  109    BRISC: sem_wait(SEM_PACK_DONE) unblocks        [HW]
  109    BRISC: noc_write(y → DRAM or next tile)        [SW→HW]
  109–130 HW: NoC transmits output tile                 [HW]
  131    BRISC: csr_write(T6_TO_DE_SYNC, 0x1)           [SW→HW]
  131    HW: t6_to_de wire driven, FDS updates register [HW]

  132    HOST: interrupt fires, reads result             [SW]

Total compute latency (this tile): ~130 cycles from W in Dispatch L1 to result in DRAM
  → dominated by unpack (16c) + MVMUL (16c) + SFPU (4c) + pack (16c) + NoC drain
  → overlaps with next tile: while TRISC1 is doing MVMUL, Dispatch can be sending
    the next tile's data to the same or another Tensix tile
```

---

##### Overlap: how pipelining works across tiles

```
Tensix[2,2] timeline (3 tiles, double-buffer):

Tile N:  [Dispatch→L1] [TRISC0 unpack] [TRISC1 math] [TRISC2 pack] [NoC drain]
Tile N+1:              [Dispatch→L1]   [TRISC0 unpack] [TRISC1 math]  ...
Tile N+2:                              [Dispatch→L1]   ...

Overlap key:
  [HW] Dispatch fills L1 for tile N+1 while TRISC1 is computing tile N.
  DEST register is double-buffered (bank A / bank B):
    TRISC1 writes into bank A for tile N
    TRISC2 packs from bank A; TRISC1 simultaneously writes into bank B for tile N+1
  → zero stall between tiles if dispatch keeps up with compute.
```

---

### 2.4 Signal Width Summary at Key Interfaces

```
                      ┌─────────────────────┐
  L1 (128b bus)  ────►│  TDMA Unpacker      │
                      │  tt_unpack_row      │
  L1_addr [20:0] ────►│  + fmt_conv         │──► SRCA write:  19b × 16 cols × 2 rows
  L1_data [127:0]────►│  (tt_unpacker_      │    (ext format: 1 sign + 8 exp + 10 man)
                      │   gasket_fmt_conv)  │──► zero_flags:   1b × 16 cols × 2 rows
                      └─────────────────────┘

                      ┌─────────────────────────────────────────┐
  SRCA [19b × 16] ───►│  FP Lane (one column shown)             │
  SRCB [19b × 16] ───►│                                         │
                      │  tt_fp_mul_raw × 8:  exp_sum[8:0]       │
                      │                      man_prod[19:0]      │
                      │  tt_exp_path_v4:     max_exp[8:0]        │
                      │                      shift_amt[4:0] × 8  │
                      │  tt_dual_align × 8:  aligned_man[10:0]   │
                      │  compressor tree:    sum[10:0]            │
                      │                      carry[10:0]          │
                      │  tt_multiop_adder:   result[10:0]         │
                      │  normalize + round:  out[15:0] (FP16)     │
                      └──────────────────────────────────────────┘
                                                │ 16b per column
                      ┌─────────────────────────▼───────────────┐
                      │  DEST reg file:  [1023:0] rows           │
                      │  each row:  16 × 16-bit half-float       │
                      │  total:  1024 × 16 × 16b = 256 KB        │
                      └─────────────────────────────────────────┘
```

---

### 2.5 Additional Architecture Diagrams

---

#### 2.5.1 Trinity 4×5 Grid — NoC Topology & Tile Types

Shows the physical tile layout, the two Dispatch Engine positions, and a representative NoC packet path from dispatch to a compute Tensix.

```
  col:       0            1            2            3
         ┌────────────┬────────────┬────────────┬────────────┐
row 0:   │ NOC2AXI_NE │ NOC2AXI_N  │ NOC2AXI_N  │ NOC2AXI_NW │  ← external AXI gateway
         │ (off-chip) │            │            │ (off-chip) │
         ├────────────┼────────────┼────────────┼────────────┤
row 1:   │ DISPATCH_E │   ROUTER   │   ROUTER   │ DISPATCH_W │  ← dispatch + EDC/config
         │tt_disp_top │tt_noc_rtr  │tt_noc_rtr  │tt_disp_top │
         │ (FDS, L1)  │ (APB only) │ (APB only) │ (FDS, L1)  │
         ├────────────┼────────────┼────────────┼────────────┤
row 2:   │ TENSIX[0,2]│ TENSIX[1,2]│ TENSIX[2,2]│ TENSIX[3,2]│
         │            │            │     ▲      │            │
         ├────────────┼────────────┼─────│──────┼────────────┤
row 3:   │ TENSIX[0,3]│ TENSIX[1,3]│ TENSIX[2,3]│ TENSIX[3,3]│
         │            │            │            │            │
         ├────────────┼────────────┼────────────┼────────────┤
row 4:   │ TENSIX[0,4]│ TENSIX[1,4]│ TENSIX[2,4]│ TENSIX[3,4]│
         └────────────┴────────────┴────────────┴────────────┘

NoC packet path: DISPATCH_E → Tensix[2,2]  (DOR: X first, then Y)

  DISPATCH_E (0,1)
      │  inject flit east on row 1
      ▼
  ROUTER (1,1) ──east──► ROUTER (2,1) ──east──► arrives at col 2
                                                      │ south
                                                      ▼
                                                 TENSIX[2,2]
                                                 i_flit_in_req_north

  de_to_t6 control wires (point-to-point, NOT NoC):
  DISPATCH_E
      │  o_de_to_t6_south  (4 wires per column, direct)
      ▼
  ROUTER (feedthrough only, no processing)
      │  o_de_east_to_t6_south
      ▼
  TENSIX rows 2-4  i_de_to_t6_north  → BRISC CSR

  Key:
  ──► NoC flit hop (routed, credit-controlled)
  ──→ de_to_t6 wire (direct, zero latency)
  APB only = Router has no tensor data path, config registers only
```

---

#### 2.5.2 Thread Timing Diagram — 4-Thread Pipeline (Gantt)

Shows how BRISC, TRISC0, TRISC1, TRISC2 overlap across two consecutive tiles. Semaphore post/wait events are the synchronization points.

```
Tile N:
Thread     0    5   10   15   20   25   30   35   40   45   50   55   60 (cycles)
────────────────────────────────────────────────────────────────────────────────
BRISC    [═══ NoC recv / dispatch wait ════════════════][═ noc_write out ═]
              │                                         ▲
              │ sem_post(L1_READY)×2                    │ sem_wait(PACK_DONE)
              ▼                                         │
TRISC0   [▒▒▒▒wait][══════ UNPACR × 16 ══════]
                                │ sem_post(UNPACK_DONE)
                                ▼
TRISC1          [▒wait][══ MVMUL × 16 ═══][═ SFPU ═]
                                           │ sem_post(MATH_DONE)
                                           ▼
TRISC2               [▒▒▒wait][═══════ PACR × 16 ═══════]
                                                   │
                                                   └─► sem_post(PACK_DONE)

Tile N+1 (overlapping — Dispatch fills L1 while Tile N math runs):
Thread     0    5   10   15   20   25   30   35   40   45   50   55   60
────────────────────────────────────────────────────────────────────────────────
Dispatch [══════════ NoC inject tile N+1 → L1 ════════]
BRISC                                [══ wait N+1 ══][═ noc_write N+1 ═]
TRISC0                                    [▒][═ UNPACR N+1 ═]
TRISC1                                          [▒][═ MVMUL N+1 ══][SFPU]
TRISC2                                                [▒][═══ PACR N+1 ═══]

Legend:
[═══] active execution   [▒▒▒] waiting on semaphore
      sem_post ──►              sem_wait ◄──
```

---

#### 2.5.3 Semaphore Synchronization Topology

Shows all 4 threads, which semaphores connect them, and the direction of post/wait for a standard GEMM tile.

```
  ┌──────────────────────────────────────────────────────────────────────┐
  │                 tt_cluster_sync  (16 semaphore slots)                │
  │                                                                      │
  │  SEM_L1_WEIGHT_READY [0]   SEM_L1_ACT_READY [1]                     │
  │  SEM_UNPACK_DONE     [2]   SEM_MATH_DONE     [3]                     │
  │  SEM_PACK_DONE       [4]   SEM_DEST_BUF_A    [5]  SEM_DEST_BUF_B [6]│
  └──┬──────────────┬──────────────┬──────────────┬────────────────┬────┘
     │              │              │              │                │
  POST[0,1]      WAIT[0,1]      WAIT[2]        WAIT[3]         WAIT[4]
  WAIT[4]        POST[2]        POST[3]         POST[4]         (drain)
     │           POST[5,6]      WAIT[5,6]      WAIT[5,6]           │
     ▼              ▼              ▼              ▼                 ▼
  ┌──────┐     ┌──────────┐  ┌──────────┐  ┌──────────┐     ┌──────────┐
  │BRISC │     │ TRISC0   │  │ TRISC1   │  │ TRISC1   │     │ TRISC2   │
  │      │     │ (unpack) │  │ (math)   │  │ (SFPU)   │     │ (pack)   │
  │NoC   │     │UNPACR×16 │  │MVMUL×16  │  │GELU×4    │     │PACR×16   │
  │recv  │     │          │  │          │  │          │     │          │
  └──────┘     └──────────┘  └──────────┘  └──────────┘     └──────────┘
     │                │              │                              │
     │                │              │  DEST double-buffer:         │
     │                │              │  POST(SEM_DEST_BUF_A) when   │
     │                │              │  writing bank A is done      │
     │                │              │  TRISC2 WAIT(SEM_DEST_BUF_A) │
     │                │              │  before packing bank A       │
     │                │              │                              │
     └── de_to_t6 ───►│              └──────────────────────────────┘
      (HW wire)   BRISC polls CSR          ← no direct HW connection;
                                              all sync via tt_cluster_sync

  POST = sem_post (ATINCGET): atomically increment counter → unblocks any waiter
  WAIT = sem_wait (ATGETM):   atomically decrement; CPU stalls in HW if count == 0
```

---

#### 2.5.4 Single-Element Format Conversion Lifecycle

Traces one FP16B element from L1 storage through every conversion stage to DEST and back to L1.

```
L1 SRAM
  stored as FP16B (16 bits: E8M7 + 1 sign)
  l1_data[127:0]  (128-bit bus, element at bits [15:0])
        │
        ▼
  tt_word_assembler  (128b → 16b element extraction)
  shift_reg[127:0] >> (elem_index × 16) → elem[15:0]
        │
        ▼
  tt_unpack_row  (double-buffer staging, exponent split)
  exponent[7:0]  ← elem[14:7]
  mantissa[6:0]  ← elem[6:0]
  sign[0]        ← elem[15]
        │
        ▼
  tt_unpacker_gasket_fmt_conv  (FP16B → 19-bit extended internal)
  FP16B:  E8M7  →  E8M10  (zero-pad mantissa from 7 to 10 bits)
  output: {sign[0], exp[7:0], mantissa[9:0]}  = 19 bits
  zero_flag: (exp==0 && mantissa==0)
        │
        ▼ SRCA write:  19b per column × 16 columns × 2 rows
  SRCA register file  (tt_fpu_gtile, 48 rows × 16 cols × 19b)
  srca[row][col][18:0] ← 19-bit extended value
        │
        ▼ (paired with SRCB)
  tt_fp_mul_raw  (mantissa multiply + exponent add)
  exp_sum[8:0]   = {1'b0, srca_exp} + {1'b0, srcb_exp}  (9-bit)
  man_prod[19:0] = srca_man[9:0] × srcb_man[9:0]         (20-bit raw)
        │
        ▼
  tt_exp_path_v4  (max-exponent tree over 8 products)
  max_exp[8:0] = max(exp_sum[0..7], acc_exp)
  shift_amt[i] = max_exp − exp_sum[i]   (per product)
        │
        ▼
  tt_barrel_rshift  (4-stage, align mantissa to max_exp)
  aligned_man[i] = man_prod[i] >> shift_amt[i]
  guard_bit, sticky_bit preserved for rounding
        │
        ▼
  tt_four_two_compressor (Wallace tree, 2 levels)
  Level 1: 8 products → {sum0, carry0}, {sum1, carry1}
  Level 2: {sum0,carry0,sum1,carry1} → {sum2, carry2}
  + accumulator from DEST
  Final: {sum_final, carry_final}  (2 values, 11 bits each)
        │
        ▼
  tt_multiop_adder  (carry-propagate, normalize, round)
  result[10:0] = sum_final + carry_final
  normalize:   shift result and adjust exponent
  stochastic rounding:  PRNG[9:0] added to guard bits
  output: FP16B  {sign, exp[7:0], man[6:0]}  = 16 bits
        │
        ▼ DEST write: 16b per column × 16 columns
  DEST register file  (tt_reg_bank, 1024 rows × 16 cols × 16b)
  dest[row][col][15:0] ← FP16B result
        │
        ▼ (after all rows accumulated — SFPU optional)
  tt_packer_gasket_misc_ops  (ReLU, edge mask, threshold)
  if (value < 0 && relu_mode): value ← 0
        │
        ▼
  tt_dstac_to_mem  (DEST format → output storage format)
  FP16B → FP16B:  pass through
  FP16B → INT8:   round + saturate
  FP16B → FP32:   mantissa zero-extend + rebias exp
        │
        ▼
  tt_word_assembler (pack)
  collect 16b elements into 128-bit aligned words
  word[127:0] ← {elem[7],elem[6],...,elem[0]}  (8 × 16b)
        │
        ▼
  L1 SRAM write  (128-bit burst)
  i_wr_data[127:0] ← assembled word
  i_addr ← TENSIX_L1_OUTPUT_BASE + row_offset
```

---

#### 2.5.5 TDMA XY Address Traversal Pattern

Shows how `tt_tdma_xy_address_controller` scans a 2D tile in L1 and handles stride, z-planes, and broadcast.

```
  Tile layout in L1 (16 rows × 16 cols, row-major, FP16B = 2B/elem):

  L1 base address: 0x1000
  Row stride: 16 cols × 2B = 32 bytes = 0x20

  Address sequence for one tile (no z-stride):
  ┌─────────────────────────────────────────────┐
  │  row 0: 0x1000 → 0x101F  (32 bytes, 1 read) │
  │  row 1: 0x1020 → 0x103F                      │
  │  ...                                          │
  │  row15: 0x11E0 → 0x11FF                      │
  └─────────────────────────────────────────────┘
  Total: 16 × 32B = 512B = 4 × 128-bit L1 reads per row = 64 reads total

  XY Controller state per read:
  ┌─────────────────────────────────────────────────────┐
  │  xy_addr = base + y × row_stride + x × elem_width   │
  │  x: 0 → (TILE_COLS/elements_per_read) − 1           │
  │  y: 0 → TILE_ROWS − 1                               │
  │                                                     │
  │  After x wraps: y++                                 │
  │  After y wraps: z++ (next z-plane or done)          │
  └─────────────────────────────────────────────────────┘

  Z-plane traversal (3D tensor, e.g. K=4 z-planes):
  z=0: scan full 16×16 tile at base + 0×z_stride
  z=1: scan full 16×16 tile at base + 1×z_stride
  z=2: scan full 16×16 tile at base + 2×z_stride
  z=3: scan full 16×16 tile at base + 3×z_stride

  Zmask plane skip (sparse):
  zmask[z] == 0 → controller enters SKIP_A/SKIP_B state:
  ┌───────────────────────────────────────────┐
  │  no L1 read issued                        │
  │  SRCA/SRCB zero_flag injected into FPU    │
  │  FP Lane: if zero_flag then result = acc  │
  │           (skip multiply entirely)        │
  └───────────────────────────────────────────┘

  Row-broadcast mode (bias add):
  y is held at 0 for all 16 destination rows:
  row 0..15 in SRCA ← same L1 row (bias vector)
  → single L1 read reused 16× → 16× bandwidth savings

  Address controller outputs per cycle:
  o_l1_addr[20:0]    → L1 read request
  o_dest_row[9:0]    → which DEST row to write result into
  o_z_count[7:0]     → current z-plane index
  o_last             → high on final address of tile
```

---

#### 2.5.6 Stall / Replay Sequence Diagram

Shows the cycle-by-cycle behavior when TRISC1 issues a MVMUL that hits an FPU-busy stall, then recovers via replay.

```
Cycle:  0    1    2    3    4    5    6    7    8    9   10   11
        │    │    │    │    │    │    │    │    │    │    │    │

TRISC1 fetch/decode:
        │issue MVMUL_0│    │    │    │    │    │    │    │    │

tt_stall_scoreboard:
        │             │FPU_BUSY=1 (previous MVMUL still in pipeline)
        │             │stall → TRISC1 issue blocked

tt_instruction_issue:
        │             │hold MVMUL_0 at issue stage (not dispatched)
        │             │TRISC0, TRISC2, BRISC continue unaffected (other threads)

FPU pipeline:
        │[prev MVMUL completes: G-Tile result → DEST write]│
        │                                    FPU_BUSY → 0   │

tt_stall_scoreboard:
        │                                         │ FPU_BUSY=0
        │                                         │ stall released

TRISC1 issue:
        │                                         │ MVMUL_0 dispatched
        │                                         │ → FPU_BUSY set again

tt_replay_unit (L1 bank conflict example):
        │    │    │    │    │    │    │    │    │    │    │    │
TRISC0:  │issue UNPACR_0│   │    │    │    │    │    │    │    │
         │              │L1 bank conflict (BRISC load hit same bank)
         │              │conflict detected by tt_t6_l1_superarb
         │              │UNPACR_0 stalled mid-flight
         │              │
         │      tt_replay_buffer saves UNPACR_0 instruction
         │              │
         │              │ BRISC load completes (1-cycle priority)
         │              │ bank free
         │              │
         │              │ tt_replay_unit re-issues UNPACR_0 automatically
         │              │ [SW firmware does NOT see this — no branch needed]
         │              │ UNPACR_0 completes normally

  State flow in tt_replay_unit:

  NORMAL ──► (conflict detected) ──► STALL
     ▲                                  │
     │  (resource free, re-issue done)  │
     └────────── REPLAY ◄───────────────┘

  What tt_replay_buffer stores per entry:
  ┌──────────────────────────────────────────────────────────┐
  │  instruction opcode  [31:0]                              │
  │  thread ID           [1:0]   (which TRISC)               │
  │  destination reg ID  [4:0]                               │
  │  resource mask        [N:0]  (which resource was wanted) │
  └──────────────────────────────────────────────────────────┘
```

---

#### 2.5.7 Clock Domain Boundary Diagram

Shows which modules run in which clock domain and where the CDC (clock domain crossing) points are.

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                    tt_tensix_with_l1                                │
 │                                                                     │
 │  ┌─────────────────────────────────────────────────────────────┐   │
 │  │              i_ai_clk  (AI compute clock — highest freq)    │   │
 │  │                                                             │   │
 │  │  TRISC × 3      (RV32I fetch/decode/execute)                │   │
 │  │  BRISC × 1      (RV32I)                                     │   │
 │  │  tt_mop_config  (MOP FSM)                                   │   │
 │  │  tt_stall_scoreboard                                        │   │
 │  │  tt_replay_unit                                             │   │
 │  │  tt_tdma        (UNPACR/PACR address generation)            │   │
 │  │  tt_fpu_v2      (G-Tile × 4, M-Tile, FP Lane × 16)         │   │
 │  │  tt_sfpu                                                    │   │
 │  │  tt_reg_bank    (DEST register file)                        │   │
 │  │  tt_t6_l1       (L1 SRAM read/write from TDMA, BRISC)       │   │
 │  │  tt_cluster_sync (semaphore block)                          │   │
 │  │  tt_t6_com_prng  (stochastic rounding PRNG)                 │   │
 │  │  tt_droop_trigger_detector                                  │   │
 │  │  tt_power_ramp_fsm                                          │   │
 │  └─────────────────────────────────────────────────────────────┘   │
 │                         │         ▲                                 │
 │              CDC FIFO ──┘         └── CDC FIFO                     │
 │           (async FIFO, 4-entry)    (async FIFO, 4-entry)           │
 │                         │         │                                 │
 │  ┌─────────────────────────────────────────────────────────────┐   │
 │  │              i_noc_clk  (NoC mesh clock — lower freq)       │   │
 │  │                                                             │   │
 │  │  NoC endpoint   (flit Rx/Tx, VC buffers, credit tracking)   │   │
 │  │  tt_fds o_bus   (FDS output bus, drives de_to_t6 wire)      │   │
 │  │  L1 write path  (NoC → L1 write, 128b per beat)             │   │
 │  └─────────────────────────────────────────────────────────────┘   │
 │                                                                     │
 └─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────┐
  │  i_dm_clk  (DM complex clock)       │  ← Dispatch Engine only
  │                                     │     (outside Tensix tile)
  │  tt_fds.sv  (auto-dispatch FSM)     │
  │  tt_fds_dispatch_reg (FDS regfile)  │
  │  ad_count_q  (cycle timer)          │
  │  auto_dispatch_fifo (4-entry)       │
  └────────────────┬────────────────────┘
                   │ tt_async_fifo_wrapper (dm_clk → noc_clk)
                   ▼
  NoC flit injection port (noc_clk)

  CDC points summary:
  ┌──────────────────────┬─────────────────────┬──────────────────┐
  │ From domain          │ To domain           │ Mechanism        │
  ├──────────────────────┼─────────────────────┼──────────────────┤
  │ i_ai_clk (TDMA)      │ i_noc_clk (NoC RX)  │ async FIFO 4-ent │
  │ i_noc_clk (NoC TX)   │ i_ai_clk (L1 write) │ async FIFO 4-ent │
  │ i_dm_clk (FDS timer) │ i_noc_clk (flit inj)│ tt_async_fifo    │
  │ i_noc_clk (FDS in)   │ i_ai_clk (regfile)  │ tt_async_fifo    │
  └──────────────────────┴─────────────────────┴──────────────────┘
```

---

#### 2.5.8 Reset Hierarchy Diagram

Shows which reset signal controls which hardware block and the dependency ordering on power-up.

```
  Power-good / POR
        │
        ▼
  tensix_reset_n  (from trinity.sv, per-tile)
  ├── driven by harvest fuse: if tile harvested → held 0 permanently
  └── else: released by chip-level power-on sequence
        │
        ├── i_nocclk_reset_n ──────────────────────────────────────────┐
        │      │                                                        │
        │      ├── NoC endpoint (flit Rx/Tx, VC buffers)               │
        │      ├── tt_fds o_bus register                               │
        │      └── L1 NoC write path                                   │
        │                                                              │
        │   ┌──────────────────────── (released after noc_reset) ──────┘
        │   │
        ├── i_uncore_reset_n ──────────────────────────────────────────┐
        │      │                                                        │
        │      ├── tt_t6_l1 (L1 control, bank arbitrator)              │
        │      │    NOTE: L1 SRAM data is NOT cleared on uncore reset   │
        │      ├── tt_tdma  (TDMA address gen, channel FIFOs)          │
        │      ├── tt_fpu_v2 (FPU pipeline registers)                  │
        │      ├── tt_sfpu   (SFPU accumulator, lregs)                 │
        │      ├── tt_reg_bank (DEST register file)                    │
        │      ├── tt_cluster_sync (semaphore counters → all 0)        │
        │      ├── tt_stall_scoreboard                                  │
        │      ├── tt_replay_unit                                       │
        │      └── tt_droop_trigger_detector, tt_power_ramp_fsm        │
        │                                                              │
        │   ┌──────────────────────── (released after uncore_reset) ───┘
        │   │
        └── i_core_reset_n[N]  (per-TRISC, N=0,1,2 for TRISC0/1/2; BRISC has own)
               │
               ├── tt_trisc[N] (PC reset to boot vector)
               │     ├── tt_riscv_core (pipeline registers → 0)
               │     ├── tt_trisc_cache (I-cache valid bits → 0)
               │     ├── tt_gpr_file[N] (GPR values undefined after reset)
               │     └── tt_trisc_secded_* (ECC syndrome registers)
               │
               └── Independent per-thread: resetting TRISC0 does NOT affect
                   TRISC1, TRISC2, or BRISC pipelines or register files.

  Reset ordering at chip power-on:
  1. tensix_reset_n = 0  (all Tensix tiles in reset)
  2. NOC2AXI tiles released first (noc_reset_n = 1 → NoC mesh active)
  3. Dispatch Engine released (dm_reset_n = 1 → FDS can accept commands)
  4. tensix_reset_n = 1  (compute tiles released; TRISC PCs jump to boot vector)
  5. Dispatch Engine sends kernel binaries via NoC → BRISC/TRISC load firmware
  6. BRISC releases individual i_core_reset_n[N] for TRISC0/1/2 when firmware ready

  Warm reset (kernel error recovery):
  → Assert i_core_reset_n[N] = 0 for the faulting TRISC only
  → TRISC restarts from boot vector; L1 data and semaphore state preserved
  → Other threads continue if they do not depend on the faulting thread's semaphores
```

---

### 2.4 Signal Width Summary at Key Interfaces

### `tt_tensix_with_l1`
**File:** `tensix/rtl/tt_tensix_with_l1.sv`

Top-level tile wrapper. Connects `tt_tensix` (compute) and `tt_t6_l1` (SRAM) through the multi-client L1 arbiter.

| Port Group | Key Signals | Description |
|---|---|---|
| Clocks | `i_ai_clk`, `i_noc_clk` | AI compute, NoC mesh |
| Resets | `i_core_reset_n[N]`, `i_uncore_reset_n` | Per-TRISC and tile-level |
| NoC ID | `i_local_nodeid_x/y`, `i_noc_endpoint_id` | Tile grid coordinates |
| Harvest | `i_mesh_start_x/y`, `i_mesh_end_x/y` | Active mesh boundary |
| SMN | `i_smn_in_req_north`, `o_smn_out_req_south` | EDC supervisory ring pass-through |

**Design rationale:** The wrapper allows the L1 configuration (`L1_CFG`) to vary per chip variant (e.g., deeper banks, more ports) without modifying the compute RTL. The arbiter instantiation here isolates the priority policy from the core logic.

---

### `tt_tensix`
**File:** `tensix/rtl/tt_tensix.sv`

Core compute engine. Instantiates:
- `tt_instrn_engine_wrapper` — instruction engine with RISC threads and TDMA
- `tt_fpu_gtile[3:0]` — 4 FPU G-Tiles in parallel

| Parameter | Value | Meaning |
|---|---|---|
| `NEO_INSTANCE` | 0–11 | Tile instance ID for debug identification |
| `L1_CFG` | `L1_CFG_DEFAULT` | Bank depth, port count |
| `NUM_GTILES` | 4 | FPU G-Tiles per tile |

**Clock gating:** `o_cg_retmux_en` and `o_cg_l1bank_en` are exported to the clock gate cells in the physical hierarchy, allowing fine-grained power management per compute domain.

---

## 4. Instruction Engine & Thread Model

### 4.0 Instruction Engine Block Diagram

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                   tt_instrn_engine_wrapper                           │
 │                                                                      │
 │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐        │
 │  │  BRISC    │  │  TRISC0   │  │  TRISC1   │  │  TRISC2   │        │
 │  │  (ctrl)   │  │  (unpack) │  │  (math)   │  │  (pack)   │        │
 │  │  I-cache  │  │  I-cache  │  │  I-cache  │  │  I-cache  │        │
 │  │  LDM 4KB  │  │  LDM 4KB  │  │  LDM 4KB  │  │  LDM 4KB  │        │
 │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘        │
 │        │              │              │              │               │
 │        └──────────────┴──────────────┴──────────────┘               │
 │                              │                                       │
 │        ┌─────────────────────▼──────────────────────┐               │
 │        │         tt_instruction_buffer [×4]          │               │
 │        │         tt_instruction_thread [×4]          │               │
 │        │         tt_thread_context     [×4]          │               │
 │        └─────────────────────┬──────────────────────┘               │
 │                              │                                       │
 │        ┌─────────────────────▼──────────────────────┐               │
 │        │           tt_compute_decoder_v1             │               │
 │        │           tt_compute_predecode              │               │
 │        └──────┬──────────────────┬──────────────────┘               │
 │               │ math instns      │ DMA instns                        │
 │       ┌───────▼───────┐  ┌───────▼───────┐                          │
 │       │  tt_mop_decode│  │tt_tdma_instrn_│                          │
 │       │  ┌──────────┐ │  │   decoder     │                          │
 │       │  │math_loop │ │  └───────┬───────┘                          │
 │       │  │unpack_   │ │          │                                   │
 │       │  │loop FSMs │ │          ▼  to tt_tdma                      │
 │       │  └──────────┘ │                                              │
 │       └───────┬───────┘                                              │
 │               │ decoded ops                                          │
 │       ┌───────▼───────────────────────┐                             │
 │       │  tt_instruction_issue          │                             │
 │       │  tt_stall_scoreboard           │◄── resource busy signals    │
 │       │  tt_replay_unit+buffer         │    (FPU busy, TDMA busy)    │
 │       └───────┬───────────────────────┘                             │
 │               │                                                      │
 │    ┌──────────▼────────────────────────────────────────┐            │
 │    │  Synchronization & Semaphores                      │            │
 │    │  tt_cluster_sync (SEM×16)  tt_mutex               │            │
 │    │  tt_dest_sync  tt_sync_exu                        │            │
 │    └────────────────────────────────────────────────────┘            │
 │                                                                      │
 │  ┌──────────────────────┐   ┌──────────────────────────────────┐   │
 │  │  tt_droop_trigger    │   │  tt_power_ramp_fsm               │   │
 │  │  _detector           │──►│  (ballast, dummy ops, col mask)  │   │
 │  └──────────────────────┘   └──────────────────────────────────┘   │
 └──────────────────────────────────────────────────────────────────────┘
```

### 4.1 Thread Model (BRISC + TRISC×3)

The Tensix instruction engine has **4 independent hardware threads**, each mapped to a specific role in the compute pipeline:

| Thread | Name | Primary Role | Key Instructions Used |
|---|---|---|---|
| T0 | **BRISC** | Kernel orchestration, NOC messaging, data prefetch scheduling | ADDGPR, ATCAS, ATINCGET, ATGETM, mailbox reads |
| T1 | **TRISC0** | Unpack (L1 → SRCA/SRCB) | UNPACR, UNPACR_NOP, RDCFG, WRCFG |
| T2 | **TRISC1** | Math (trigger FPU compute) | MOP, MOP_CFG, MVMUL, MULADD, DOTP, ELWADD |
| T3 | **TRISC2** | Pack (DEST → L1) | PACR, PACRNL, SETDMAREG |

**Advantage:** The 4-thread model decouples the three pipeline stages (unpack, math, pack) into independent software-controlled pipelines. Thread synchronization is explicit (via semaphores), so there are no hardware pipeline hazards between stages — each thread runs as fast as its resources allow, independent of the others.

**SW perspective:** The firmware / kernel compiler assigns code sections to threads. The most common pattern is:
```
BRISC:  fill L1 from NoC, post semaphore N times to TRISC0
TRISC0: wait semaphore → UNPACR loop → post semaphore to TRISC1
TRISC1: wait semaphore → MOP loop (MVMUL/ELWADD) → post semaphore to TRISC2
TRISC2: wait semaphore → PACR loop → drain L1 to NoC via BRISC
```

---

### 4.2 Instruction Buffer & Thread Context

**Files:** `tt_instruction_buffer.sv`, `tt_instruction_thread.sv`, `tt_thread_context.sv`

Each thread has a dedicated instruction queue (`tt_instruction_buffer`) that decouples the fetch stage from the execute stage. The instruction buffer holds up to 16 instructions. The `tt_thread_context` stores the per-thread PC, status, and configuration state.

`tt_pc_buffer` tracks the in-flight PC for each issued instruction, enabling precise exception handling.

**`tt_compute_predecode` / `tt_thread_predecode`:** A fast pre-decode step runs before full decode to determine instruction type (math vs. DMA vs. config), execution latency, and resource consumption. This is used by the issue logic (`tt_instruction_issue`) to schedule instructions across threads without full decode overhead.

---

### 4.3 MOP (Macro-Operation) Engine

**Files:** `tt_mop_config.sv`, `tt_mop_decode.sv`, `tt_mop_decode_math_loop.sv`, `tt_mop_decode_unpack_loop.sv`

#### MOP Engine Block Diagram

```
   TRISC1 issues one MOP_CFG then one MOP instruction
          │
          ▼
 ┌─────────────────────────────────────────────────────────┐
 │  tt_mop_config  (dual-bank A/B for back-to-back loads)  │
 │                                                         │
 │  bank_A / bank_B:                                       │
 │    loop0_len[15:0]   ─ outer iteration count            │
 │    loop1_len[15:0]   ─ inner iteration count            │
 │    loop_start_instrn ─ instruction at loop entry        │
 │    loop_end_instrn   ─ instruction at loop exit         │
 │    zmask_hi[31:0]    ─ upper 32 Z-plane skip bits       │
 │    zmask_lo[31:0]    ─ lower 32 Z-plane skip bits       │
 └────────────────────┬────────────────────────────────────┘
                      │ config signals
          ┌───────────▼──────────────────────────────────┐
          │              tt_mop_decode                   │
          │                                              │
          │  ┌────────────────────┐  ┌────────────────┐  │
          │  │ tt_mop_decode_     │  │ tt_mop_decode_ │  │
          │  │ math_loop FSM      │  │ unpack_loop FSM│  │
          │  │                    │  │                │  │
          │  │  IDLE              │  │  IDLE          │  │
          │  │  LOOP_START_OP0    │  │  UNPACK_A0..A3 │  │
          │  │  IN_LOOP ◄──┐      │  │  UNPACK_B      │  │
          │  │  LOOP_END   │cnt   │  │  SKIP_A  ◄zmask│  │
          │  │  FINAL_END  └─dec  │  │  SKIP_B  ◄zmask│  │
          │  └──────────┬─────────┘  └────────┬───────┘  │
          │             │                     │           │
          │             └──────────┬──────────┘           │
          │                        │ issued instruction    │
          └────────────────────────┼──────────────────────┘
                                   │
                     ┌─────────────▼─────────────────┐
                     │  instruction dispatch bus       │
                     │  → TDMA (unpack/pack ops)       │
                     │  → FPU  (MVMUL/ELWADD/DOTP)    │
                     └────────────────────────────────┘
```

The MOP engine implements **hardware loop execution** — a compact loop construct that repeatedly issues a pre-programmed instruction sequence without re-fetching from the instruction cache.

#### MOP Config (`tt_mop_config`)

Two register banks (A/B) allow double-buffering of MOP configurations while one is executing:

| Register Field | Description |
|---|---|
| `loop0_len`, `loop1_len` | Iteration count for outer/inner loop |
| `loop_start_instrn[N]` | Instruction to issue at loop start |
| `loop_end_instrn[N]` | Instruction to issue at loop end |
| `zmask_high`, `zmask_low` | 64-bit Z-plane mask for conditional unpack skipping |

#### MOP Decode FSM (`tt_mop_decode_math_loop`)

8-state FSM controlling the math loop:

| State | Action |
|---|---|
| `IDLE` | Wait for MOP instruction |
| `LOOP_START_OP0` | Issue loop-start instruction type 0 |
| `IN_LOOP` | Issue body instructions on every cycle |
| `LOOP_END_OP0/OP1` | Issue loop-end instructions (two-phase) |
| `FINAL_LOOP_END_OP0/OP1` | Final iteration end sequence |

The loop counter is decremented each iteration. NOP cycles are injected to match FPU pipeline latency when the instruction stream is shorter than the pipeline depth.

#### MOP Unpack Loop FSM (`tt_mop_decode_unpack_loop`)

8-state FSM for TDMA unpack loops with Z-plane (depth) iteration:

| State | Action |
|---|---|
| `IDLE` | Idle |
| `UNPACK_A0/A1/A2/A3` | Unpack 4 A-matrix planes |
| `UNPACK_B` | Unpack B-matrix plane |
| `SKIP_A` | Skip A-plane (zmask bit = 0) |
| `SKIP_B` | Skip B-plane (zmask bit = 0) |

**Zmask:** A 64-bit per-loop Z-plane mask. When a bit is 0, the corresponding Z-plane of matrix A (or B) is skipped entirely. This implements sparse tensor computation — if a block of activations is known to be zero, the unpacker skips the L1 read and the FPU lane multiplies by zero (which is also skipped via zero-flags). Zmask is set by software before loop start based on sparsity metadata computed on the host.

**SW usage:** The kernel compiler emits one `MOP_CFG` instruction to program the loop counts and inner instructions, then one `MOP` instruction to execute. The hardware loop runs thousands of iterations without any instruction fetch traffic. A typical 512×512×512 GEMM requires only ≈10 `MOP_CFG` + `MOP` instruction pairs for the entire inner loop nest.

---

### 4.4 Stall Scoreboard & Replay Unit

**Files:** `tt_stall_scoreboard.sv`, `tt_replay_unit.sv`, `tt_replay_buffer.sv`, `tt_replay_instr_decode.sv`

The stall scoreboard (`tt_stall_scoreboard`) tracks resource availability across threads:
- FPU busy (M-Tile compute in progress)
- TDMA channel busy
- Destination register write hazards
- SRCA/SRCB write-after-read hazards

When a hazard is detected, the instruction issue logic (`tt_instruction_issue`) stalls the affected thread. Other threads continue unaffected.

The **replay unit** handles recoverable stalls (e.g., L1 bank conflicts, FPU backpressure) by re-issuing an instruction without software intervention. `tt_replay_buffer` holds the most recent issued instructions. `tt_replay_instr_decode` decodes the replayed instruction to restore the correct resource request. This eliminates the need for a branch-predictor or explicit retry loops in the kernel firmware.

---

### 4.5 TRISC Processor — Detailed CPU Specification

**Files:** `tensix/rtl/tt_trisc.sv`, `tt_briscv/rtl/tt_trisc_cache.sv`, `tt_risc_wrapper.sv`, `tt_risc_addr_check.sv`

---

#### 4.5.1 CPU Architecture Overview

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                  tt_trisc  (one instance = one thread role)         │
 │                                                                     │
 │  ┌────────────────────────────────────────────────────────────┐    │
 │  │               tt_risc_wrapper                              │    │
 │  │                                                            │    │
 │  │   ┌──────────────────────────────────────────────────┐    │    │
 │  │   │            tt_riscv_core  (CPU core)             │    │    │
 │  │   │                                                  │    │    │
 │  │   │  Fetch ──► Decode ──► Execute ──► Mem ──► WB    │    │    │
 │  │   │   (PC)    (32b inst) (ALU/BR)   (L1/LDM) (GPR) │    │    │
 │  │   │                                                  │    │    │
 │  │   │   ISA: RV32I + custom tensor extensions          │    │    │
 │  │   │   GPR: 16 × 128-bit registers per thread         │    │    │
 │  │   │   Threads: 2 hardware thread contexts            │    │    │
 │  │   └──────────────────────────────────────────────────┘    │    │
 │  │                                                            │    │
 │  │   ┌──────────────┐   ┌────────────────────────────────┐  │    │
 │  │   │ tt_trisc_    │   │  tt_gpr_file                   │  │    │
 │  │   │ cache        │   │  16 regs × 128-bit × 3 threads │  │    │
 │  │   │ (I-cache)    │   │  P0: RD (THCON/CFG clients)    │  │    │
 │  │   │ 32 entries   │   │  P1: WR (L1 ret, RISC-V WB)   │  │    │
 │  │   │ 96-bit line  │   └────────────────────────────────┘  │    │
 │  │   │ CAM lookup   │                                        │    │
 │  │   └──────────────┘   ┌────────────────────────────────┐  │    │
 │  │                      │  LDM (Local Data Memory)       │  │    │
 │  │                      │  4 KB private SRAM per thread   │  │    │
 │  │                      │  SECDED ECC (52-bit codeword)   │  │    │
 │  │                      └────────────────────────────────┘  │    │
 │  │                                                            │    │
 │  │   ┌──────────────────────────────────────────────────┐    │    │
 │  │   │  tt_risc_addr_check  (memory protection)         │    │    │
 │  │   │  18 address regions, combinational compare       │    │    │
 │  │   └──────────────────────────────────────────────────┘    │    │
 │  └────────────────────────────────────────────────────────────┘    │
 │                                                                     │
 │  Interfaces out:                                                    │
 │  ├── L1 RD/WR [128b] + atomic_instrn[15:0]                        │
 │  ├── TDMA cfg regs (addr + 32b data)                               │
 │  ├── ALU cfg regs  (addr + 32b data)                               │
 │  ├── Global regs   (addr + 32b data)                               │
 │  ├── Mailbox RD [4 × 32b]                                          │
 │  ├── Semaphore POST/GET [32b each]                                 │
 │  ├── DEST reg RD/WR [addr + 128b data]                             │
 │  └── Error out → tt_err_aggregate                                  │
 └─────────────────────────────────────────────────────────────────────┘
```

---

#### 4.5.2 CPU Specifications

| Attribute | TRISC0/1/2 | BRISC |
|---|---|---|
| **ISA** | RV32I + custom tensor extensions | RV32I + tensor + NoC extensions |
| **GPR count** | 16 registers | 16 registers |
| **GPR width** | 128 bits | 128 bits |
| **Thread contexts** | 2 per TRISC instance | 1 |
| **Pipeline depth** | ~5–7 stages (fetch/decode/exec/mem/wb) | same |
| **Clock domain** | `i_ai_clk` | `i_ai_clk` |
| **Max MIPS** | ~100–500 MIPS at AI clock frequency | same |
| **I-cache entries** | 32 (256×72 SRAM) | — |
| **I-cache line width** | 96 bits (3 × 32-bit instructions) | — |
| **I-cache type** | CAM (content-addressable) | — |
| **I-cache ECC** | SECDED (72 bits = 64b data + 8 ECC) | — |
| **LDM size** | 4 KB private per thread | 4 KB |
| **LDM depth** | 256×104b or 512×52b or 1024×52b | same |
| **LDM ECC** | SECDED (52→32b or 104→64b) | SECDED |
| **L1 bus width** | 128 bits | 128 bits |
| **L1 address space** | 32-bit (8 MB mapped) | 32-bit |
| **Atomic ops** | CAS, INCGET, SWAP, GETM, RELM | all |
| **Mailboxes** | 4 × 32-bit RD | 5 × 32-bit RD/WR |
| **Semaphores** | 32 hardware sem (via cluster_sync) | 32 |

**Note on MIPS:** The AI clock frequency for Trinity is not published in the RTL. At a typical 1 GHz AI clock with a 5-stage pipeline, each TRISC achieves ~200 MIPS for scalar integer. In practice, TRISC execution is **latency-dominated** by L1 memory accesses (~4–8 cycles) and MOP hardware loops (which achieve near-1-instruction/cycle throughput for the inner loop body). The TRISC cores are not general-purpose high-performance CPUs — they are control processors whose throughput is measured by **how quickly they can configure and trigger the FPU/TDMA**, not raw MIPS.

---

#### 4.5.3 Instruction Cache (`tt_trisc_cache`)

**File:** `tt_briscv/rtl/tt_trisc_cache.sv`

```
 PC[31:0] (fetch request)
      │
      ▼
 ┌────────────────────────────────────────────────────────────┐
 │           tt_trisc_cache  (CAM-based, 32 entries)          │
 │                                                            │
 │  Entry layout (96 bits + 3 validity bits):                 │
 │  ┌──────────┬────────────────────────────────────────────┐ │
 │  │ tag[30:2]│ instr[0][31:0] │ instr[1][31:0] │ instr[2] │ │
 │  │ (PC tag) │ (instrn at PC) │ (PC+4)         │ (PC+8)   │ │
 │  └──────────┴────────────────────────────────────────────┘ │
 │                                                            │
 │  CAM lookup (2 ports):                                     │
 │  Port A: check next_pc → hit/miss                          │
 │  Port B: write-pending check → avoid duplicate fill        │
 │                                                            │
 │  On HIT:  return up to 3 instructions this cycle           │
 │  On MISS: fetch from LDM/L1, fill cache entry             │
 │                                                            │
 │  Non-gatherable instructions (NOT cached):                 │
 │    RESOURCEDECL, REPLAY, MOP_CFG                           │
 │    (these have side effects on execution context)          │
 │                                                            │
 │  Eviction:  5-bit countdown timer per entry                │
 │             entry evicted when countdown reaches 0        │
 │             (not LRU — time-based eviction for HW loops)  │
 │                                                            │
 │  Instruction bundling:                                     │
 │    Detects consecutive TRISC instructions → coalesces      │
 │    into a 3-instruction bundle for single fetch            │
 └────────────────────────────────────────────────────────────┘
```

**I-cache SRAM options:**

| Variant | Depth | Width | Total | ECC |
|---|---|---|---|---|
| `tt_mem_wrap_256x72` | 256 entries | 72 bits | 2.25 KB | 8 ECC bits per 64b word |
| `tt_mem_wrap_512x72` | 512 entries | 72 bits | 4.5 KB | 8 ECC bits per 64b word |

ECC encoding: `tt_trisc_secded_52_32_enc_ldm` — Hamming code with 5 parity bits per byte:
```
p0 = D[0]^D[1]^D[2]^D[4]^D[6]
p1 = D[0]^D[1]^D[3]^D[5]^D[7]
p2 = D[0]^D[2]^D[3]^D[4]^D[5]
p3 = D[1]^D[2]^D[3]^D[6]^D[7]
p4 = D[4]^D[5]^D[6]^D[7]
```
Syndrome detects: SBE (single bit error → corrected), DBE (double bit error → reported).

**Why CAM instead of direct-mapped?** TRISC instruction sequences for inner loops (MOP body instructions) repeat at the same PCs continuously. A CAM cache hits immediately without index-computation, allowing back-to-back instruction issue from the cache with no stall. The time-based eviction ensures loop-resident entries stay alive for the entire MOP duration without being displaced by infrequent instructions.

---

#### 4.5.4 Local Data Memory (LDM)

**SRAM options:**

| Variant | Entries | Data width | ECC codeword | Total data | Use case |
|---|---|---|---|---|---|
| `256×104` | 256 | 64-bit | 104-bit (13b×8 bytes) | 2 KB | Large word, low depth |
| `512×52` | 512 | 32-bit | 52-bit (13b×4 bytes) | 2 KB | Balanced |
| `1024×52` | 1024 | 32-bit | 52-bit | 4 KB | Default — 4 KB target |

**ECC structure per memory word:**

```
  For 1024×52 (32-bit data):
  ┌──────────────────────────────────────────────────────────────┐
  │  52-bit stored word = 4 bytes × 13 bits each                │
  │                                                              │
  │  Byte 0 [12:0]:  data[7:0]  + p0 + p1 + p2 + p3 + p4       │
  │  Byte 1 [12:0]:  data[15:8] + p0 + p1 + p2 + p3 + p4       │
  │  Byte 2 [12:0]:  data[23:16]+ p0 + p1 + p2 + p3 + p4       │
  │  Byte 3 [12:0]:  data[31:24]+ p0 + p1 + p2 + p3 + p4       │
  │                                                              │
  │  On read:  4 decoders run in parallel                        │
  │  SBE per byte → correct in-flight, no pipeline stall        │
  │  DBE per byte → assert error to tt_err_aggregate            │
  └──────────────────────────────────────────────────────────────┘
```

**Write masking:** 4-bit byte-enable mask allows partial 32-bit word writes (e.g., updating only byte 2 of a struct field). Hardware re-reads the full word, merges with new bytes, then writes back atomically.

**LDM address map per TRISC thread (from `tt_t6_trisc_regs_pkg`):**

| Region | Address | Size | Use |
|---|---|---|---|
| LDM[0] | `0x00002000` | 8 KB | TRISC0 stack + firmware data |
| LDM[1] | `0x00004000` | 8 KB | TRISC1 stack + firmware data |
| LDM[2] | `0x00006000` | 8 KB | TRISC2 stack + firmware data |
| LDM[3] | `0x00008000` | 8 KB | BRISC stack + firmware data |

**SW usage:** LDM holds:
- C call stack (local variables, function arguments, return addresses)
- Kernel descriptor tables (tile address arrays, stride tables)
- Loop counters and temporary accumulators for address arithmetic
- Spill area for GPR values during context switches

---

#### 4.5.5 General Purpose Register File (`tt_gpr_file`)

**File:** `instrn_path/rtl/tt_gpr_file.sv`

```
 ┌────────────────────────────────────────────────────────────────────┐
 │                     tt_gpr_file                                    │
 │                                                                    │
 │  Capacity:  16 registers × 128-bit × 3 threads  = 6144 bits       │
 │  Addr width:  4 bits (reg 0..15 per thread)                       │
 │  Data width:  128 bits                                             │
 │  Byte enable: 16 bits (per-byte update granularity)               │
 │                                                                    │
 │  Port P0 (Read, 2 clients with arbitration):                      │
 │   Client 0: THCON (TDMA thread controller reads GPR for address)  │
 │   Client 1: CFG   (config unit reads GPR for WRCFG indirect)      │
 │                                                                    │
 │  Port P1 (Write + Read):                                          │
 │   Write sources:                                                   │
 │     L1 return data (load result)  ── 128-bit                      │
 │     RISC-V ALU result             ── 128-bit                      │
 │     Config write-back             ── 32-bit → byte-enable         │
 │   Read sources:                                                    │
 │     Data request (for store addr) ── GPR[addr_reg]                │
 │     Offset register               ── GPR[off_reg]                 │
 │     RISC-V source operands        ── GPR[rs1], GPR[rs2]           │
 │                                                                    │
 │  Parity (TRINITY mode):                                            │
 │     gpr_file_parity_t: per-word, per-bit failure tracking         │
 │     TFD (Thorough Functional Diagnostic) patterns                 │
 │     Self-check: read-back comparison on every write               │
 └────────────────────────────────────────────────────────────────────┘
```

**128-bit register usage:** Although the RISC-V core processes 32-bit instructions, the GPR is 128-bit wide to allow a single GPR read to deliver a full L1 bus word (128 bits = 16 bytes) directly to TDMA address generation or to a store instruction targeting a 128-bit L1 write. This eliminates the need for register packing/unpacking logic for tensor address descriptors that span multiple 32-bit fields.

---

#### 4.5.6 TRISC ISA — Instruction Set

The TRISC implements **RV32I** (base 32-bit integer) plus a set of **custom tensor extensions**. All instructions are 32-bit fixed-width.

**Standard RV32I subset used:**
- Integer arithmetic: ADD, SUB, AND, OR, XOR, SLT, SLL, SRL, SRA
- Branches: BEQ, BNE, BLT, BGE, BLTU, BGEU
- Load/Store: LW, LH, LB, SW, SH, SB (to LDM and MMIO)
- Immediate: ADDI, ANDI, ORI, XORI, LUI, AUIPC
- Jump: JAL, JALR (call/return for firmware functions)

**Custom tensor extensions (from `tt_t6_opcode_pkg.sv`):**

| Mnemonic | Format | Operation | Bit fields |
|---|---|---|---|
| `ADDGPR` | ALU | `GPR[result] = GPR[opA] + GPR[opB]` (or + const) | `opbisconst[0], result[10:0], opb[5:0], opa[5:0]` |
| `CMPGPR` | ALU | Compare two GPRs, set condition | `opsel[4:0], dst[5:0], opb[5:0], opa[5:0]` |
| `BITWOPGPR` | ALU | Bitwise op (AND/OR/XOR/NOT/NAND/NOR) | `opsel[4:0], result[5:0], opb[5:0], opa[5:0]` |
| `LOADIND` | MEM | Indexed load with optional auto-increment | `data_gpr[5:0], addr_gpr[5:0], offset[7:0], autoinc` |
| `LOADREG` | MEM | Load from absolute 18-bit MMIO address | `addr[17:0]` |
| `RDCFG` | CFG | Read TDMA/ALU config register → GPR | `dest_gpr[5:0], cfg_addr[11:0]` |
| `WRCFG` | CFG | Write GPR → config register | `src_gpr[5:0], cfg_addr[11:0]` |
| `CFGSHIFTMASK` | CFG | Read-modify-write config reg (shift+mask) | `cfgregaddr[7:0], mask_width[4:0], cshift[4:0], op[2:0]` |
| `SEMGET` | SYNC | Decrement semaphore; stall if zero | `sem_id[4:0]` |
| `SEMPOST` | SYNC | Increment semaphore | `sem_id[4:0]` |
| `STALLWAIT` | SYNC | Stall until resource condition | `wait_resource_t` fields |
| `ATCAS` | ATOMIC | Compare-and-swap to L1 | `memhiersel, swapval[4:0], cmpval[3:0], sel32b[1:0], data_gpr[5:0], addr_gpr[5:0]` |
| `ATINCGET` | ATOMIC | Fetch-and-increment from L1 | `memhiersel, wrapval[8:0], sel32b[1:0], data_gpr[5:0], addr_gpr[5:0]` |
| `ATINCGETPTR` | ATOMIC | Fetch-and-inc with pointer semantics | same + `ptr_gpr` |
| `ATSWAP` | ATOMIC | Atomic swap (exchange) | `swapmask[8:0], swapdata[7:0], addr_gpr[5:0]` |
| `ATGETM` | ATOMIC | Acquire mutex (spin until acquired) | `mutex_index[23:0]` |
| `ATRELM` | ATOMIC | Release mutex | `mutex_index[23:0]` |
| `SETDMAREG` | DMA | Set DMA register from GPR/immediate | `gpr[5:0], target[7:0]` |
| `MOVA2D` | MOV | Copy SRCA register → DEST register | `dstacc_idx[9:0], srca_addr[5:0]` |
| `MOVB2A` | MOV | Copy SRCB → SRCA | `srca_addr[5:0], srcb_addr[5:0]` |
| `MOVB2D` | MOV | Copy SRCB → DEST | `dstacc_idx[9:0], srcb_addr[5:0]` |
| `MOVD2A` | MOV | Copy DEST → SRCA (recurrence) | `dstacc_idx[9:0], srca_addr[5:0]` |
| `MOVD2B` | MOV | Copy DEST → SRCB | `dstacc_idx[9:0], srcb_addr[5:0]` |
| `UNPACR` | TDMA | Trigger unpacker (L1→SRCA/SRCB) | `clear_dvalid[1:0], instr_mod[4:0], addr_mode[4:0], dst[13:0]` |
| `PACR` | TDMA | Trigger packer (DEST→L1) | `clear_dvalid[1:0], instr_mod[4:0], addr_mode[4:0], dst[13:0]` |
| `PACRNL` | TDMA | Packer non-last (continues burst) | same |
| `MOP` | LOOP | Execute pre-programmed loop sequence | `loop_type[1:0]` |
| `MOP_CFG` | LOOP | Program MOP loop config (A or B bank) | `bank_sel, loop_data[...]` |
| `UNPACR_NOP` | TDMA | No-op cycle in unpacker pipeline | `nop_ctrl_t` fields |
| `MVMUL` | FPU | Matrix-vector multiply | `fpu_tag_t` |
| `ELWADD` | FPU | Element-wise add | `fpu_tag_t` |
| `DOTP` | FPU | Dot product | `fpu_tag_t` |
| `MULADD` | FPU | Multiply-accumulate | `fpu_tag_t` |

---

#### 4.5.7 Address Space & Memory Protection (`tt_risc_addr_check`)

**File:** `tensix/rtl/tt_risc_addr_check.sv`

The address checker validates every TRISC load/store against 18 defined regions before the transaction is issued. An address that falls outside all regions asserts `o_addr_fail_check` → exception / error report.

**Full address map (from `tt_t6_trisc_regs_pkg.sv`):**

| Region | Base address | Size | Access | Description |
|---|---|---|---|---|
| **L1 data** | `0x0000_0000` | 8 MB | RW | Main tensor storage |
| **Local regs** | `0x0080_0000` | 45 KB | RW | TDMA/ALU/MOP config registers |
| **Tile counters** | `0x0080_C000` | 1 KB | RW | 32 × 16-bit hardware loop counters |
| **GPRs** | `0x0080_D000` | 4 KB | RW | GPR file MMIO access |
| **MOP config** | `0x0080_E000` | 132 B | WR | MOP inner-loop programming |
| **IBuffer** | `0x0080_F000` | 4 KB | RD | Instruction buffer read-back |
| **PCBuffer** | `0x0081_0000` | 4 KB | RD | PC buffer read-back (debug) |
| **TRISC MB[0]** | `0x0081_1000` | 1 KB | RD | Mailbox from BRISC/NoC |
| **TRISC MB[1]** | `0x0081_1400` | 1 KB | RD | Mailbox |
| **TRISC MB[2]** | `0x0081_1800` | 1 KB | RD | Mailbox |
| **TRISC MB[3]** | `0x0081_1C00` | 1 KB | RD | Mailbox |
| **Unpack MB[0]** | `0x0081_2000` | 1 KB | RD | Unpacker argument mailbox 0 |
| **Unpack MB[1]** | `0x0081_2400` | 1 KB | RD | Unpacker argument mailbox 1 |
| **Unpack MB[2]** | `0x0081_2800` | 1 KB | RD | Unpacker argument mailbox 2 |
| **DEST regs** | `0x0081_8000` | 32 KB | RW | Destination register file direct access |
| **Config regs** | `0x0082_0000` | 3.5 KB | RW | ALU/FPU config registers |
| **Global regs** | `0x0184_0000` | 8.5 KB | RW | Tile-global registers (sem, EDC, NoC overlay) |
| **Overlay regs** | `0x0200_0000` | 32 MB | RW | NoC overlay address space |

**Protection behavior:**
- `o_addr_pass_check` = 1 → issue the transaction normally
- `o_addr_pass_check` = 0 → suppress transaction, raise error via `tt_err_aggregate`
- No hardware page tables or TLB — protection is compile-time region bounds only

---

#### 4.5.8 TRISC Role in Trinity Tile — Per-Thread Responsibilities

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                  Trinity Tensix Tile                                │
 │                                                                     │
 │   BRISC  ──────────────────────────────────────────────────────    │
 │   • Kernel launch orchestration                                    │
 │   • NoC message send/receive (ATCAS on remote tiles)              │
 │   • Tensor descriptor passing via mailbox to TRISC0/1/2           │
 │   • Cross-tile synchronization (ATGETM on shared mutexes)         │
 │   • Error recovery and exception handling                          │
 │   • Tile counter management for multi-tile dispatch               │
 │   • Clock/power mode programming                                   │
 │                                                                     │
 │   TRISC0 (Unpack thread) ─────────────────────────────────────    │
 │   • Programs THCON_UNPACKER config registers via WRCFG            │
 │   • Issues UNPACR / MOP(UNPACR) to stream L1→SRCA/SRCB           │
 │   • Manages tile loop (outer K dimension in GEMM)                 │
 │   • Reads tile addresses from TRISC mailbox (written by BRISC)    │
 │   • Posts semaphore to TRISC1 after each SRCA/SRCB tile loaded    │
 │   • Waits semaphore from BRISC to confirm L1 tile is ready        │
 │                                                                     │
 │   TRISC1 (Math thread) ────────────────────────────────────────    │
 │   • Programs ALU_FORMAT_SPEC, ALU_ACC_CTRL, ROUNDING_MODE         │
 │   • Issues MVMUL / DOTP / ELWADD via MOP hardware loop           │
 │   • Issues SFPU instruction sequences (GeLU, sigmoid, etc.)      │
 │   • Manages destination buffer pointer swap (ping/pong)           │
 │   • Posts semaphore to TRISC2 after each tile computed            │
 │   • Waits semaphore from TRISC0 before each compute tile         │
 │                                                                     │
 │   TRISC2 (Pack thread) ────────────────────────────────────────    │
 │   • Programs THCON_PACKER config registers via WRCFG              │
 │   • Issues PACR / PACRNL / MOP(PACR) to drain DEST→L1            │
 │   • Controls output format conversion (FP16→FP8/INT8/BFP)        │
 │   • Manages L1 output tile FIFO (FIFO_SIZE, LIMIT_ADDR)          │
 │   • Posts semaphore to BRISC after L1 output tile written         │
 │   • Waits semaphore from TRISC1 before each pack pass             │
 └─────────────────────────────────────────────────────────────────────┘
```

**Trinity grid context:** Each of the 12 Tensix tiles runs 4 independent TRISC programs. The dispatch engine (row 1) loads all 12 tiles' firmware before releasing reset. The firmware is tile-specific (each tile operates on a different partition of the tensor) but structurally identical — differentiated by the tile coordinates written into the mailboxes by BRISC.

---

#### 4.5.9 TRISC Timing & Performance Model

```
  Instruction type           Latency (cycles)    Notes
  ─────────────────────────────────────────────────────────────────
  GPR ALU (ADDGPR, BITWOPGPR)      1             no memory
  Branch (BEQ, BNE)                1–2           branch delay slot
  WRCFG / RDCFG                    1–2           MMIO register path
  SEMGET (sem available)            1             semaphore hit
  SEMGET (sem = 0)                  N             stall until POST
  SEMPOST                           1             increment + notify
  ATCAS (L1 local)                  4–8           L1 access latency
  ATGETM (mutex free)              4–8            L1 access
  ATGETM (mutex held)              N              spin until free
  LW to LDM                        2–3           private SRAM
  LW to L1                         4–8           shared SRAM + arb
  SW to L1                         1 (pipelined) write returns early
  MOP (inner loop body)             1/iter        hardware loop, no fetch
  UNPACR (first of burst)           1             TDMA pipeline starts
  PACR (first of burst)             1             packer pipeline starts
  MVMUL (FPU trigger)               1             FPU pipeline starts (result after 7 cycles)
  SFPU MAD                          2             two-cycle pipeline
  ─────────────────────────────────────────────────────────────────

  Steady-state GEMM throughput (TRISC1 perspective):
  ─────────────────────────────────────────────────
  1 MOP(MVMUL) issues → FPU processes 16-col × N-row per cycle
  TRISC1 is idle during FPU execution (waiting semaphore from TRISC0)
  Bottleneck: typically L1 bandwidth (TDMA unpacker fill rate)

  Effective TRISC compute rate ≈ 2–5 MMIO writes per kernel tile
  (configure → trigger → wait → post semaphore)
  TRISC is NOT the compute bottleneck — the FPU is.
```

---

#### 4.5.10 TRISC ECC Summary

```
 Memory region          ECC type              Action on error
 ─────────────────────────────────────────────────────────────────
 I-cache (SRAM)         SECDED 72/64          SBE: correct in-flight
                        8 check bits           DBE: tt_err_aggregate (code 0x0002)
                                               + suppress instruction issue

 LDM 1024×52            SECDED 52/32          SBE: correct + continue
                        5 bits per byte        DBE: tt_err_aggregate (code 0x0003)
                        (4 bytes × 13b = 52b)  + data returned as 0x00

 LDM 256×104            SECDED 104/64         SBE: correct
                        5 bits per byte        DBE: error + suppress
                        (8 bytes × 13b = 104b)

 GPR file               Optional parity       Parity error → error aggregate
                        (TRINITY mode)         TFD diagnostic mode

 L1 (external)          SECDED per 128b       See §8.3
 ─────────────────────────────────────────────────────────────────
```

---

#### 4.5.11 SW Usage — TRISC Firmware Programming

**Firmware compilation:** TRISC programs are written in C with intrinsics and compiled with an LLVM-based toolchain targeting RV32I. The linker script places code in the LDM execute-in-place region or in L1 (loaded by the dispatch engine).

**Typical TRISC0 firmware (pseudo-C for unpack thread):**
```c
// Startup: read tile descriptor from BRISC mailbox
uint32_t l1_base    = read_mailbox(MB_L1_BASE);
uint32_t tile_rows  = read_mailbox(MB_TILE_ROWS);
uint32_t tile_cols  = read_mailbox(MB_TILE_COLS);
uint32_t k_tiles    = read_mailbox(MB_K_TILES);

// Configure unpacker (written once before loop)
wrcfg(THCON_UNPACKER0_OUT_DATA_FORMAT, FP16B);
wrcfg(THCON_UNPACKER0_TILIZE_SRC_ADDR, l1_base);
wrcfg(THCON_UNPACKER0_STRIDE_SRC_Z,    tile_rows * tile_cols * sizeof(fp16));
wrcfg(THCON_UNPACKER1_OUT_DATA_FORMAT, FP16B);   // SRCB
wrcfg(THCON_UNPACKER1_TILIZE_SRC_ADDR, l1_base + weights_offset);

// Program MOP unpack loop
mop_cfg(LOOP0_LEN, k_tiles - 1);
mop_cfg(LOOP_ZMASK_HI, zmask >> 32);
mop_cfg(LOOP_ZMASK_LO, zmask & 0xFFFFFFFF);
mop_cfg(LOOP_START_INSTR, UNPACR_encode(CH0, SRCA));

for (uint32_t tile = 0; tile < num_output_tiles; tile++) {
    sem_wait(SEM_L1_READY);         // wait BRISC confirms tile in L1

    // Execute hardware loop: k_tiles iterations, each issues UNPACR
    issue(MOP);                     // TRISC1 stalls in hardware loop
    sem_post(SEM_UNPACK_DONE);      // signal TRISC1 to start math

    // Advance base address to next output tile
    addgpr(GPR_L1_BASE, GPR_L1_BASE, tile_stride);
    wrcfg(THCON_UNPACKER0_TILIZE_SRC_ADDR, GPR_L1_BASE);
}
```

**Typical TRISC1 firmware (pseudo-C for math thread):**
```c
uint32_t dest_base = 0;            // ping buffer

// Configure ALU once
wrcfg(ALU_FORMAT_SPEC_REG,  SRCA_FP16B | SRCB_FP16B | DEST_FP16B);
wrcfg(ALU_ACC_CTRL,         FP32_DISABLE | INT8_DISABLE);
wrcfg(ALU_ROUNDING_MODE,    STOCHASTIC_RND_ENABLE);
wrcfg(DEST_REGW_BASE,       0);
wrcfg(DEST_SP_BASE,         512);   // pong buffer

// Program MOP math loop
mop_cfg(LOOP0_LEN, M_tiles - 1);
mop_cfg(LOOP_START_INSTR, MVMUL_encode(ACCUM_EN, dest_base));

for (uint32_t tile = 0; tile < num_output_tiles; tile++) {
    sem_wait(SEM_UNPACK_DONE);      // wait for SRCA/SRCB filled

    issue(MOP);                     // FPU executes M_tiles MVMUL operations

    // SFPU activation (4 rows per instruction × 256 = 1024 rows)
    for (int row = 0; row < 256; row++) {
        issue(SFPLOAD, LREG0, dest_base + row*4);
        issue(SFPMAD,  LREG1, LREG0, LREG0, CONST0);  // x^2
        issue(SFPMAD,  LREG1, LREG1, LREG0, CONST0);  // x^3
        issue(SFPMAD,  LREG1, LREG1, COEFF, CONST0);  // poly term
        // ... more MAD terms
        issue(SFPSTORE, LREG1, dest_base + row*4);
    }

    sem_post(SEM_MATH_DONE);
    dest_base ^= 512;               // swap ping/pong
    wrcfg(DEST_REGW_BASE, dest_base);
    wrcfg(DEST_SP_BASE,   dest_base ^ 512);
}
```

---

### 4.6 Atomic Operations & Semaphores

**Files:** `tt_mutex.sv`, `tt_semaphore_reg.sv`, `tt_cluster_sync.sv`

**Hardware semaphores (`tt_cluster_sync`):**

| Parameter | Value |
|---|---|
| `SEM_COUNT` | 16 per cluster sync block |
| `SEM_VAL_BITS` | 16 (0–65535 per semaphore) |

Operations:
| Op | Action | Usage |
|---|---|---|
| `GET` | Decrement; stall if 0 | Consumer waits for data |
| `POST` | Increment | Producer signals data ready |
| `INIT` | Write absolute value | Initialize before kernel |
| `POST_WR` | Add specified value | Batch post (e.g., N tiles at once) |

Overflow detection (`POST` beyond max) raises an error through the error aggregate.

**Mutex (`tt_mutex`):** Hardware mutual exclusion for multi-tile atomic region access. `ATGETM` instruction blocks until the mutex index is acquired. Used by the NoC overlay kernel for message-passing to shared queues.

**TRISC semaphore access:** `o_trisc_sempost[31:0]` / `o_trisc_semget[31:0]` are direct hardware signals — posting/getting a semaphore takes a single cycle with no memory transaction overhead.

**SW usage:** Semaphore IDs are assigned by the kernel framework. The canonical 4-thread pipeline uses 3 semaphores (N=0: BRISC→TRISC0, N=1: TRISC0→TRISC1, N=2: TRISC1→TRISC2). Typical initialization:
```c
sem_init(0, num_tiles);   // BRISC fills N tiles into L1 first
sem_init(1, 0);           // TRISC1 waits for TRISC0
sem_init(2, 0);           // TRISC2 waits for TRISC1
```

---

## 5. Tensor DMA Controller (TDMA)

**File:** `tdma/rtl/tt_tdma.sv`

#### TDMA Block Diagram

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                           tt_tdma                                    │
 │                                                                      │
 │  TRISC MMIO ──► tt_tdma_instrn_decoder                               │
 │                         │                                            │
 │         ┌───────────────┼───────────────────┐                        │
 │         │ UNPACR        │ PACR/PACRNL        │ XMOV/THCON             │
 │         ▼               ▼                   ▼                        │
 │  ┌──────────────┐ ┌──────────────┐  ┌──────────────┐                │
 │  │  Unpacker    │ │  Packer      │  │  Mover       │                │
 │  │  CH0 / CH1   │ │  CH0 / CH1   │  │  CH0         │                │
 │  │              │ │              │  │              │                │
 │  │ xy_addr_ctrl │ │ xy_addr_ctrl │  │ src→dst      │                │
 │  │  (y,z cntrs) │ │  (y,z cntrs) │  │ L1→L1/CCM   │                │
 │  │     │        │ │     │        │  └──────┬───────┘                │
 │  │  L1 RD req   │ │  DEST RD     │         │                         │
 │  │  [128b]      │ │  [16×16b]    │         │                         │
 │  │     │        │ │     │        │         │                         │
 │  │  word_asm    │ │  packer_misc │         │                         │
 │  │  +unpack_row │ │  (ReLU,mask, │         │                         │
 │  │  (dbl-buffer)│ │   exp_thresh)│         │                         │
 │  │     │        │ │     │        │         │                         │
 │  │  uncompress  │ │  dstac_to_   │         │                         │
 │  │  (BFP 4:1)   │ │  mem (cvt)   │         │                         │
 │  │     │        │ │     │        │         │                         │
 │  │  fmt_conv    │ │  elem_to_mx  │         │                         │
 │  │  (→19b ext)  │ │  (MX fmt)    │         │                         │
 │  │     │        │ │     │        │         │                         │
 │  │  SRCA write  │ │  L1 WR req   │         │                         │
 │  │  SRCB write  │ │  [128b]      │         │                         │
 │  └──────────────┘ └──────────────┘         │                         │
 │                                            │                         │
 │   tt_tdma_rr_interface_arbiter ◄───────────┘                         │
 │   (round-robin across all L1 port requests)                          │
 └──────────────────────────────────────────────────────────────────────┘
           │ L1 RD                       │ L1 WR
           ▼                             ▼
  ┌────────────────────────────────────────────┐
  │         tt_t6_l1  (16 banks, 128b ECC)     │
  └────────────────────────────────────────────┘
```

#### Unpacker Datapath Detail

```
 L1 RD [128-bit] ──► tt_word_assembler ──► tt_unpack_row
                       │  assemble 128b       │  double-buffer
                       │  from narrow units   │  exponent extract
                       │  (4b/8b/16b elem)    │
                       └──────────────────────┘
                                 │
              ┌──────────────────▼───────────────────┐
              │  tt_uncompress  (optional, BFP only)  │
              │  4:1 expansion: shared exp + 4 man    │
              └──────────────────┬───────────────────┘
                                 │
              ┌──────────────────▼────────────────────┐
              │  tt_unpacker_gasket_fmt_conv           │
              │                                        │
              │  storage format → 19-bit extended:     │
              │  MXFP4  ─ E2M1 → E8M10                │
              │  MXFP8  ─ E4M3/E5M2 → E8M10 rebias    │
              │  FP16A  ─ E5M10 → E8M10 rebias         │
              │  FP16B  ─ E8M7 → E8M10 zero-pad        │
              │  INT8   ─ sign-mag → E8M10 fixed-exp   │
              │  BFP    ─ shared_exp + 7b man → 19b    │
              └──────────────────┬────────────────────┘
                                 │ 19b × 16 cols
                                 ▼
                          SRCA / SRCB reg file
```

#### Packer Datapath Detail

```
 DEST reg [16×16b row] ──► tt_packer_gasket_misc_ops
                              │  ReLU (4 modes)
                              │  exp_threshold filter
                              │  edge_mask (boundary)
                              │
                              ▼
                         tt_dstac_to_mem
                              │  FP16B → INT8/FP8/FP32/BF16
                              │  extract block exponent
                              │
                              ▼
                         tt_t6_com_elem_to_mx_convert  (if MX output)
                              │  find block max_exp (tree)
                              │  scale all mantissas
                              │  stochastic round per datum
                              │
                              ▼
                         tt_word_assembler  (pack to 128b words)
                              │
                              ▼
                         L1 WR [128-bit]
```

The TDMA is a **fixed-function 2D/3D DMA** engineered specifically for tensor tile access patterns. It is not a general-purpose DMA. All control is through configuration registers (`tt_thcon_cfg_regs`) set by the TRISC threads.

### 5.1 Unpacker

The unpacker (`UNPACK_COUNT = 2`) reads tensor tile data from L1 and writes it to the FPU source register files (SRCA for matrix A, SRCB for matrix B).

**Pipeline stages:**

```
L1 READ request (128-bit burst)
    ↓
tt_tdma_xy_address_controller  (generate next (x,y,z) address)
    ↓
L1 data returned
    ↓
tt_word_assembler               (assemble 128-bit words from variable-width units)
    ↓
tt_unpack_row                   (double-buffered row staging, exponent extraction)
    ↓
tt_uncompress (if BFP)          (expand 4:1 compressed blocks)
    ↓
tt_unpacker_gasket_fmt_conv     (convert storage format → internal 19-bit extended)
    ↓
SRCA / SRCB register file write
```

**Exponent section handling (BFP):** For block floating-point formats, the exponent block is stored separately in L1. The unpacker reads the `exp_section_l1_limit_addr` first, then reads mantissa data and reconstructs full-precision values. The exponent is broadcast to all elements in the block.

**Row broadcast mode (`tile_misc_row_bcast`):** A single row (e.g., a bias vector) can be broadcast to all SRCA rows. The hardware repeats the single L1 read without additional fetch cycles, saving L1 bandwidth for bias-add operations.

**Zmask-based plane skipping:** When the zmask bit for a Z-plane is 0, the TDMA unpack FSM enters the `SKIP_A` / `SKIP_B` state and does not issue an L1 read request. The FPU automatically receives a zero operand (via zero-flag injection in the SRCA/SRCB interface), short-circuiting the multiply without explicit software branching.

**SW configuration (key `THCON_UNPACKER0` register fields):**

| Field | Description | Example |
|---|---|---|
| `OUT_DATA_FORMAT` | Output format to SRCA/SRCB | `FP16B` |
| `TILIZE_SRC_ADDR_OFFSET` | Tile base address in L1 | `0x1000` |
| `TRANSPOSE` | Enable 90° transpose during unpack | `1` for weight matrix transpose |
| `ENABLE_ARG_FIFO` | Enable argument FIFO for streaming | `1` for streaming loads |
| `UNPACK_STRIDE_ROW_MASK[N]` | Row skip mask for strided access | `0xFF` (all rows) |
| `SRC_Z_STRIDE` | Stride between Z-planes | `tile_rows × tile_cols × sizeof(elem)` |
| `DST_Z_STRIDE` | Destination Z offset stride | depends on SRCB layout |
| `BCAST_WRAP_TILE_DIM` | Broadcast wrap dimension | `16` for 16-col broadcast |

---

### 5.2 Packer

The packer (`PACK_COUNT = 2`) reads result data from the destination register file and writes it back to L1, applying output format conversion.

**Pipeline stages:**

```
DEST register read (16 columns × 16-bit each)
    ↓
tt_packer_gasket_misc_ops       (ReLU, edge masking, threshold filtering)
    ↓
tt_dstac_to_mem                 (format conversion: FP16 → output format)
    ↓
tt_t6_com_elem_to_mx_convert    (FP32/INT32 → MXFP4/MXINT8/BFP if requested)
    ↓
tt_word_assembler               (pack output words to 128-bit L1 write width)
    ↓
L1 WRITE (128-bit burst)
```

**ReLU modes (in `tt_packer_gasket_misc_ops`):**

| Mode | Encoding | Behavior |
|---|---|---|
| None | 0 | Pass through |
| Zero-negative | 1 | Replace negative values with 0 |
| Compare + threshold | 2 | Replace values below threshold with 0 |
| Clamp to threshold | 3 | Clamp negative values to −threshold |

These hardware ReLU modes eliminate the need for a separate SFPU pass for the common activation case, saving one full pipeline cycle per tile.

**Edge masking:** `EDGE_MASK0-3` registers define which elements at the tile boundary are written to L1. This enables non-power-of-2 tensor dimensions without zero-padding overhead.

**Exponent threshold filtering (`EXP_THRESHOLD_EN/VAL`):** Values with exponent below `EXP_THRESHOLD_VAL` are forced to zero before writing. This implements a hardware sparsification step that prunes small activations and improves compression ratio for subsequent BFP packing.

**Integer descale (`INT_DESCALE_ENABLE/MODE`):** After INT8 matrix multiply, the result is a 32-bit integer. The hardware descale right-shifts the result by a programmable amount (`INT_DESCALE_ENABLE=1`) to convert back to INT8 range before L1 write, avoiding an explicit SFPU descale step.

**SW configuration (key `THCON_PACKER0` register fields):**

| Field | Description |
|---|---|
| `IN_DATA_FORMAT` | Format of destination register data (e.g., FP16B) |
| `READ_MODE` | Dest read order (normal, transposed, untilized) |
| `DEST_REG_WRAP_MODE` | Double-buffer ping/pong control |
| `L1_ACC` | Accumulate into existing L1 data (add rather than overwrite) |
| `ZERO_WRITE` | Write zero instead of data (L1 clear) |
| `STOCH_RND_EN` | Enable stochastic rounding during format conversion |
| `UNTILIZE_DST_ADDR_OFFSET` | Convert tile order → row-major for subsequent DRAM DMA |
| `PACK_STRIDE_*` | Strided L1 write for scatter-gather patterns |

---

### 5.3 Address Generation (`tt_tdma_xy_address_controller`)

**File:** `tdma/rtl/tt_tdma_xy_address_controller.sv`

Generates the sequence of L1 addresses for the current tensor tile traversal.

| Parameter | Value | Description |
|---|---|---|
| `BYTE_ADDR_WIDTH` | 15 | L1 address bits |
| `Z_CNT_WIDTH` | 8 | Z (depth) dimension counter |
| `Y_CNT_WIDTH` | 12 | Y (row) dimension counter |
| `CHAN_ID` | 2-bit | Identifies which unpack/pack channel |

The controller maintains Y and Z counters. Each valid instruction pulse advances the (y,z) pointer according to the configured `y_dim` and `z_dim`. The output address is:

```
address = base_addr + z * z_stride + y * y_stride + x_offset
```

`i_INC_TILE_FACE_ROW_IDX_decoded` increments the row pointer (face index) within a tile. `i_SET_TILE_FACE_ROW_IDX_decoded` resets it to a programmed value, supporting random-access into a pre-loaded tile.

**State readback:** `o_state_for_readback[127:0]` exports the full (y, z, address) counter state as a 128-bit word readable by TRISC, enabling software-driven restart after error recovery.

---

### 5.4 Word Assembler & Unpack Row

**`tt_word_assembler` (`tdma/rtl/tt_word_assembler.sv`):**

Assembles narrow input units (e.g., 4-bit FP4 elements, 8-bit INT8 elements) into 128-bit L1 write words.

| Parameter | Value | Description |
|---|---|---|
| `INPUT_UNIT_BIT_WIDTH` | 4–16 | Width of input element |
| `UNITS_IN_INPUT_BUS` | 16–32 | Elements per input bus cycle |
| `DATA_WIDTH` | 128 | Output word width |
| `HAS_SHARED_EXP_LOGIC` | 0/1 | Track shared exponent section |
| `HAS_SKIP_ONE_STRIDE_LOGIC` | 1 | Optimize single-element stride patterns |

The assembler uses a `word_pointer` to track how many units have been packed into the current output word. When the pointer wraps (word complete), `o_last_word` is asserted and `o_wrvalid` writes the assembled word to L1.

**`tt_unpack_row` (`tdma/rtl/tt_unpack_row.sv`):**

Double-buffers incoming L1 data words, extracting mantissa and exponent sections for BFP formats. The double-buffer (`gen_new_buffer()` / `gen_new_exp_buffer()`) allows the next L1 read to overlap with the current row's transfer to the FPU register file.

`zero_mask_output()` — a combinational function that generates the valid-mask output when the entire row is zeros (sparsity shortcut).

---

### 5.5 Format Conversion — Unpacker (`tt_unpacker_gasket_fmt_conv`)

**File:** `registers/rtl/tt_unpacker_gasket_fmt_conv.sv`

Converts storage-format elements to the FPU internal format (1 sign + 8 exp + 10 mantissa = 19 bits extended).

**Supported input formats with conversion logic:**

| Format | Conversion Steps |
|---|---|
| `MXINT8` | Reinterpret INT8 as sign+magnitude; set exponent from shared block exp |
| `MXINT4` | 4-bit → INT8 extend + block exp inject |
| `MXINT2` | 2-bit → INT8 extend + block exp inject |
| `MXFP8R` | Rebias exponent (E4M3 or E5M2 → E8M10 extended); subnormal expand |
| `MXFP8P` | Positive-only FP8; rebias + sign=0 |
| `MXFP6R/6P` | 6-bit FP; mantissa zero-pad to 10 bits |
| `MXFP4` | E2M1 decode; 2-bit exp rebias; 1-bit mantissa → 10-bit zero-padded |
| `FP16A` (E5M10) | Direct pass-through with exp rebias 15→127 |
| `FP16B` / BFloat16 | 7-bit man → 10-bit zero-padded; 8-bit exp direct |
| `FP32` | Truncate mantissa 23→10; direct exponent |
| `INT8` | 2's complement → sign+magnitude; fixed exponent 127+6 |

For all subnormal detection: if `exp==0 && man!=0`, the subnormal is either flushed to zero (configurable `FLUSH_SUBNORMS`) or converted via leading-zero normalization.

Saturation detection raises `o_sat_flag` which can be read by software to detect range overflow during quantization.

---

### 5.6 Packer Misc Ops (`tt_packer_gasket_misc_ops`)

**File:** `registers/rtl/tt_packer_gasket_misc_ops.sv`

Applied after FPU result read-back, before L1 write:

1. **ReLU** (4 modes — see §5.2).
2. **Exponent threshold filtering:** Values with `exp < EXP_THRESHOLD_VAL` → zero. Sparse activation pruning.
3. **Edge masking:** Per-element mask from `EDGE_MASK0-3` registers. Bits 0–15 map to columns 0–15. A mask bit of 0 suppresses the write for that column — used at tile boundaries for non-multiple-of-16 tensor widths.
4. **Format output assembly:** Selects final output encoding:
   - `FLOAT32` → 32-bit IEEE
   - `FLOAT16` → 16-bit half
   - `INT8` → 8-bit with sign extension
   - `INT32` → 32-bit integer
   - `INT16` → 16-bit integer

---

### 5.7 TDMA Configuration Registers (`tt_thcon_cfg_regs`)

The complete TDMA configuration is held in `tt_thcon_cfg_regs` registers, accessed by TRISC via MMIO. Key register groups:

| Group | Registers | Description |
|---|---|---|
| `THCON_UNPACKER0/1/2` | 18 registers (addrs 0–17) | Per-channel unpack configuration |
| `THCON_PACKER0/1` | 16 registers (addrs 18–33) | Per-channel pack configuration |
| `THCON_MOVER` | 4 registers | Data-move-only (no FPU) transfers |

**THCON_MOVER registers:**
- `SOURCE_ADDRESS` — L1 source base
- `DESTINATION_ADDRESS` — L1 destination base
- `BUFFER_SIZE` — Transfer length in 128-bit words
- `TRANSFER_DIRECTION` — L1-to-L1 or L1-to-CCM (RISC code memory)

The Mover engine (`MOVE_COUNT = 1`) handles intra-L1 data reorganization (e.g., transposing a tile in L1 before unpack) and L1-to-TRISC code memory transfers for dynamic code loading.

---

### 5.8 Throttle & Flow Control

Four throughput modes controlled by a 2-bit register:

| Mode | Encoding | Max L1 BW | Use Case |
|---|---|---|---|
| X1 | 2'b00 | 16 B/cycle | Low-power idle |
| X2 | 2'b01 | 32 B/cycle | Light inference |
| X4 | 2'b10 | 64 B/cycle | Normal operation |
| X8 | 2'b11 | 128 B/cycle | Full throughput |

The throttle interacts with the droop trigger detector (§12.1): when a voltage droop event is detected, the droop code is passed to the TDMA to reduce throughput within 1–2 cycles.

---

## 6. Floating-Point Unit (FPU)

### 6.0 FPU Hierarchy Diagram

```
 tt_fpu_v2  (manages 16 columns total)
 │
 │  fpu_tag_t (valid, mode, format, dest_addr, alu_tag)
 │  PRNG seed, stoch_rnd_mask, per-col valid[15:0]
 │
 ├── tt_srca_reformat  (format conversion for SRCA write path)
 │
 ├── tt_fpu_gtile [0]  cols 0..3          tt_fpu_gtile [1]  cols 4..7
 │   │                                    │
 │   ├── tt_fpu_v2 (sub-tile)             ├── (same structure)
 │   │   │                                │
 │   │   ├── tt_fpu_mtile [row_group_0]   │
 │   │   │   │                            │
 │   │   │   ├── tt_fpu_tile [col_0]      │
 │   │   │   │   ├── tt_fpu_tile_srca     │    SRCB rows broadcast
 │   │   │   │   │   └── tt_srca_lane_sel │    ─────────────────►
 │   │   │   │   ├── tt_fpu_tile_srcb     │
 │   │   │   │   │   └── tt_srcb_lane_sel │
 │   │   │   │   ├── tt_fp_lane [row 0]   │
 │   │   │   │   └── tt_fp_lane [row 1]   │
 │   │   │   ├── tt_fpu_tile [col_1]      │
 │   │   │   │   └── ...                  │
 │   │   │   └── tt_reg_bank (SRCA/SRCB)  │
 │   │   │                                │
 │   │   └── tt_fpu_mtile [row_group_1]   │
 │   │       └── ...                      │
 │   │                                    │
 │   ├── tt_sfpu                          │
 │   │   ├── tt_sfpu_lregs (4 × 32b)      │
 │   │   └── tt_t6_com_sfpu_mad           │
 │   │                                    │
 │   ├── tt_reg_bank  (DEST reg file)     │
 │   ├── tt_fpu_safety_ctrl               │
 │   └── tt_t6_com_prng [×cols]           │
 │                                        │
 ├── tt_fpu_gtile [2]  cols 8..11         tt_fpu_gtile [3]  cols 12..15
 │   └── (same structure)                 └── (same structure)
```

### 6.0b FPU Column Layout (16 parallel columns)

```
 Column:    0    1    2    3  │  4    5    6    7  │  8    9   10   11  │ 12   13   14   15
            ─────────────────│─────────────────────│────────────────────│─────────────────
 G-Tile:        G-Tile[0]    │     G-Tile[1]        │     G-Tile[2]      │    G-Tile[3]
                             │                      │                    │
 SRCA:     ←──── row broadcast (each row goes to all 16 FP Lanes) ─────────────────────►
 SRCB:     ←──── col-specific (each G-Tile has its own SRCB bank) ──────────────────────►
                             │                      │                    │
 FP Lane:  [L0][L1][L2][L3] │ [L4][L5][L6][L7]    │ [L8]...[L11]      │[L12]...[L15]
                             │                      │                    │
 DEST wr:  ←─── 16 × 16-bit results merged into one DEST row ─────────────────────────►
```

### 6.0c FP Lane Pipeline Timing (per column)

```
 Cycle:  S1          S2          S3          S4          S5          S6          S7
         │           │           │           │           │           │           │
 SRCB:   exp_phase───────────────►           │           │           │           │
         (exp read)  │           │           │           │           │           │
 SRCA:   │──fetch────►           │           │           │           │           │
         │           │           │           │           │           │           │
         │     tt_fp_mul_raw × 8 │           │           │           │           │
         │     sign, exp_sum,    │           │           │           │           │
         │     man_prod          │           │           │           │           │
         │           │           │           │           │           │           │
         │           tt_exp_path_v4          │           │           │           │
         │           │  max_exp, small_shift │           │           │           │
         │           │           │           │           │           │           │
         │           │     tt_dual_align × 8 │           │           │           │
         │           │     barrel_rshift     │           │           │           │
         │           │     aligned_man[10:0] │           │           │           │
         │           │           │           │           │           │           │
         │           │           │  4-2 compressor tree  │           │           │
         │           │           │  (L0: 8→2 vectors)    │           │           │
         │           │           │           │           │           │           │
         │           │           │     tt_multiop_adder  │           │           │
         │           │           │     (sum+carry+dest)  │           │           │
         │           │           │           │           │           │           │
         │           │           │           │  tt_fp_sop_normalize  │           │
         │           │           │           │  (LZC + left shift)   │           │
         │           │           │           │           │           │           │
         │           │           │           │           │  stoch_rnd│           │
         │           │           │           │           │  → FP16B  │           │
         │           │           │           │           │           │           │
         │           │           │           │           │           ▼           │
         │           │           │           │           │     DEST write [15:0] │
```

### 6.1 FPU v2 Top (`tt_fpu_v2`)

**File:** `fpu/rtl/tt_fpu_v2.sv`

Top-level FPU module. Manages 16 columns across 4 G-Tiles.

| Port | Width | Description |
|---|---|---|
| `i_valid` | 1 | FPU operation valid |
| `i_tag` | `fpu_tag_t` | Operation tag with format, address, mode |
| `i_valid_col[15:0]` | 16 | Per-column validity mask |
| `i_stoch_rnd_mask` | 32 | PRNG mask for stochastic rounding |
| `o_dest_rd_data[15:0][N][2][16]` | — | Read-back data from destination register |
| `o_fpu_sticky_bits[3:0]` | 4 | Accumulated exception flags |
| `o_parity_error` | `fpu_v2_parity_t` | Per-gtile parity error flags |

**`fpu_tag_t` fields** (from `tt_tensix_pkg.sv`):

| Field | Width | Description |
|---|---|---|
| `dstacc_idx` | 10 | Destination register row base address |
| `dst_fmt_spec` | 4 | Output format specifier |
| `dest_wr_type` | 3 | Write type: `ALU_INSTR`, `MOVA2D`, `MOVB2D`, `MOVD2X` |
| `output_mode` | — | `fpu_mode_e`: MVMUL/ELWADD/DOTP/ELWMUL/MOV_N_ROWS |
| `src_fmt` | — | INT8 / SPEC format select |
| `alu_tag` | `alu_tag_t` | ALU sub-fields (see below) |

**`alu_tag_t` fields** (18 bits):

| Field | Description |
|---|---|
| `is_elwise` | Element-wise operation (not matrix multiply) |
| `elwadd_accum_en` | Accumulate into destination |
| `tf32_en` | Use TF32 precision |
| `max_index_en` | Output argmax index |
| `gs_lf` | Use global-scale local-format (BFP8 HF mode) |
| `rnd_mode[1:0]` | Rounding mode select |
| `int8_op` | INT8 operation mode |
| `fi_phase[1:0]` | Face-index phase (which 4-row block of the 16-row tile) |
| `dotpv_inst` | Dot-product vector mode |
| `fpu_bias` | Add bias from SRCB during accumulate |
| `fp32_acc` | Accumulate in FP32 mode |
| `sop_en` | Enable sum-of-products |
| `elwadd_en` | Element-wise add enable |
| `srca/srcb_unsigned` | Treat operands as unsigned INT8 |
| `mxfp4` | MXFP4 format selected |

**Clock gating:** `i_cg_hyst_fpu` sets the clock gate hysteresis depth. When the FPU has been idle for `cg_hyst_fpu` cycles, `o_cg_l1bank_en` is deasserted to power gate the FPU clock domain. `i_fpu_gtile_kick[3:0]` re-enables each G-Tile clock independently.

---

### 6.2 FPU G-Tile (`tt_fpu_gtile`)

**File:** `fpu/rtl/tt_fpu_gtile.sv`

One G-Tile manages `FP_TILE_COLS / NUM_GTILES = 4` columns. Key responsibilities:

**Two-phase SRCB pipeline:**
- **Phase 1 (exp phase):** SRCB exponent values are read and forwarded to `tt_exp_path_v4`. The M-Tile begins computing alignment shifts.
- **Phase 2 (man phase):** SRCB mantissa values arrive one cycle later and enter the multiplier.

By splitting exponent and mantissa reads, the critical path through `max_exp_tree → shift_amount → barrel_shifter` is separated from the mantissa multiply, allowing higher clock frequency. The exponent path runs one cycle ahead of the mantissa path.

**SRCB metadata (`srcb_meta_rows_exp_s2`, `srcb_meta_rows_exp_one_hot_s3`):** Tracks which SRCB rows are valid in pipeline stage 2 and stage 3. The one-hot encoding at stage 3 gates the individual M-Tile row computations, preventing stale SRCB data from entering active multipliers when fewer than the maximum rows are valid.

**Destination FP32 mode:** `mtile_dest_wr_fp32` extends destination write to 32-bit, halving the row count but enabling higher-precision accumulation. Used for training operations or situations requiring >3 decimal digits of intermediate precision.

**SFPU access:** The G-Tile mediates SFPU reads/writes to the destination register file. `sfpu_dest_intf` carries SFPU read/write transactions from `tt_sfpu`, which shares the destination register file with the FPU.

---

### 6.3 FPU M-Tile (`tt_fpu_mtile`)

**File:** `fpu/rtl/tt_fpu_mtile.sv`

The M-Tile contains `FP_TILE_ROWS` FP Tiles (each computing 2 output rows, `FP_TILE_MMUL_ROWS=2`) arranged in a column.

| Port | Description |
|---|---|
| `i_srca_wr_tran` | SRCA write interface from TDMA unpacker |
| `i_srcb_row` | SRCB data bus (broadcast from G-Tile) |
| `i_srcb_meta_exp_row/man_row` | SRCB metadata for phase-split pipeline |
| `o_mtile_dest_wr_data[FP_ROWS-1:0][1:0][15:0]` | Destination register write data (16-bit per element) |
| `i_prng_seed`, `i_stoch_rnd_mask` | Stochastic rounding inputs |

**Self-test mode:** When `i_is_fault_checking_mode = 1`, the M-Tile injects LFSR-generated pseudo-random operands into the FP Tiles and compares results against a golden-value MISR signature (`tt_t6_com_misr`). A mismatch indicates a permanent fault and is reported via the safety controller.

**Bank switching:** SRCA has two banks (A and B). While bank A is being read by the FPU, bank B is being written by the TDMA unpacker. The switch signal allows back-to-back tile processing without a pipeline bubble between the last row of one tile and the first row of the next.

---

### 6.4 FPU Tile (`tt_fpu_tile`)

**File:** `fpu/rtl/tt_fpu_tile.sv`

The FPU Tile is one column of `FP_TILE_MMUL_ROWS = 2` FP Lanes. It manages the instruction tag pipeline and destination register write-back.

| Parameter | Value | Description |
|---|---|---|
| `INSTANTIATE_MAX_ARRAY` | 1 | Include max-exponent hardware |
| `FP_TILE_ROW_ID` | 0..N | Row ID for destination addressing |
| `FP_LANE_PIPELINE_DEPTH` | 5 | FP lane latency in cycles |

**Instruction tag FIFO:** A shift-register FIFO propagates the `fpu_tag_t` through `FP_LANE_PIPELINE_DEPTH` stages, so the destination write address is correctly aligned with the FP Lane output latency. Tag decoding:
- `mov_a2d_decoded` — MOVA2D: copy SRCA directly to destination (format conversion only, no multiply)
- `mov_b2d_decoded` — MOVB2D: copy SRCB to destination
- `mov_d2a_decoded` — MOVD2A: copy destination to SRCA (feed-forward for RNN recurrence)
- `alu_instr_decoded` — Normal FPU math (MVMUL, ELWADD, DOTP, etc.)

**Dummy operation tracking:** `mov_instr_noop` detects MOV instructions targeting a "dummy" destination (all-zeros address), which are used as pipeline flush stalls. This prevents false destination writes during flush cycles.

---

### 6.5 FP Lane (`tt_fp_lane`) — Core MAC Datapath

**File:** `fpu/rtl/tt_fp_lane.sv`

#### FP Lane Internal Block Diagram

```
  SRCA[19b] × 8 pairs          SRCB[19b] × 8 pairs
  (sign, exp[7:0], man[9:0])   (sign, exp[7:0], man[9:0])
         │                              │
         └──────────────┬───────────────┘
                        │  8 pairs (A₀B₀ .. A₇B₇)
          ┌─────────────▼──────────────────────┐
          │   tt_fp_mul_raw × 8                 │
          │   ┌──────────────────────────────┐  │
          │   │ sign_i = sA XOR sB           │  │
          │   │ exp_i  = expA + expB  [8:0]  │  │
          │   │ man_i  = manA × manB  [19:0] │  │
          │   │  (raw, no normalize)         │  │
          │   └──────────────────────────────┘  │
          │   output: sign[7:0], exp[8:0]×8,    │
          │           man[19:0]×8               │
          └───────────┬────────────────────────┘
                      │
          ┌───────────▼────────────────────────┐
          │   tt_exp_path_v4                    │
          │   max_exp = MAX(exp₀..exp₇)  [8:0] │
          │   small_shift[i] = exp[i] far below │
          │     max  (skip alignment)           │
          └───────────┬────────────────────────┘
                      │ max_exp, shift_amts[7:0]
          ┌───────────▼────────────────────────┐
          │   tt_dual_align × 8                 │
          │   (tt_barrel_rshift inside)         │
          │   man_i >> (max_exp - exp_i)        │
          │   aligned[10:0] × 8                 │
          │   guard/sticky bits (for RNE)       │
          └───────────┬────────────────────────┘
                      │ 8 aligned mantissas
          ┌───────────▼────────────────────────┐
          │   Compressor Tree                   │
          │                                     │
          │   Level A: tt_four_two_compressor   │
          │     (man₀,man₁,man₂,man₃) → s0,c0  │
          │     (man₄,man₅,man₆,man₇) → s1,c1  │
          │                                     │
          │   Level B: tt_four_two_compressor   │
          │     (s0,c0,s1,c1) → sum[10:0]       │
          │                      carry[10:0]    │
          └───────────┬────────────────────────┘
                      │
          ┌───────────▼────────────────────────┐
          │   tt_multiop_adder                  │
          │   result = sum + carry + dest_acc   │
          │   (dest_acc = 0 if first tile)      │
          │   (dest_acc = prev DEST if accum)   │
          └───────────┬────────────────────────┘
                      │
          ┌───────────▼────────────────────────┐
          │   tt_fp_sop_normalize               │
          │   LZC → left-shift → normalize      │
          │   rebias exponent                   │
          └───────────┬────────────────────────┘
                      │
          ┌───────────▼────────────────────────┐
          │   tt_t6_com_stoch_rnd               │
          │   guard+sticky+PRNG → rnd_up/down  │
          │   clip to output format             │
          │   (FP16A / FP16B / FP8 / INT8 …)  │
          └───────────┬────────────────────────┘
                      │ 16-bit FP result
                      ▼
               DEST reg write
               (row = dstacc_idx + fi_phase)
```

The FP Lane is the fundamental compute unit. One FP Lane computes one element of the output matrix (one column of the inner product). It receives `MULT_PAIRS = 8` A×B product pairs per cycle and accumulates them.

**Datapath (enabled by compile-time defines):**

```
[SRCA_EXP, SRCA_MAN] × [SRCB_EXP, SRCB_MAN]   (8 pairs per cycle)
            │
    ┌───────▼──────────────────────────────┐
    │  tt_fp_mul_raw × 8                   │  stage 1: raw multiply
    │  (mantissa products + exp sums)       │
    └───────┬──────────────────────────────┘
            │
    ┌───────▼──────────────────────────────┐
    │  tt_exp_path_v4                       │  stage 2: max exponent
    │  (find max across 8 products)         │
    └───────┬──────────────────────────────┘
            │
    ┌───────▼──────────────────────────────┐
    │  tt_dual_align × 8                   │  stage 3: right-shift alignment
    │  (barrel shift to max exp)            │
    └───────┬──────────────────────────────┘
            │
    ┌───────▼──────────────────────────────┐
    │  tt_four_two_compressor tree         │  stage 4: compress 8 → 2
    │  (3-2 then 4-2 cascaded)             │
    └───────┬──────────────────────────────┘
            │
    ┌───────▼──────────────────────────────┐
    │  tt_multiop_adder                    │  stage 5: final add
    │  (sum + carry + optional dest accum) │
    └───────┬──────────────────────────────┘
            │
    ┌───────▼──────────────────────────────┐
    │  tt_fp_sop_normalize                 │  stage 6: normalize result
    │  (leading-zero detect + shift)        │
    └───────┬──────────────────────────────┘
            │
    ┌───────▼──────────────────────────────┐
    │  tt_t6_com_stoch_rnd                 │  stage 7: round to output format
    └───────┬──────────────────────────────┘
            │
        Output → Destination register
```

**`DEST_ADD_WITH_SOP` / `DEST_ADD_IN_PIPE_2`:** When the destination accumulation flag is set (accumulate mode), the existing destination register value is added to the sum-of-products result within the pipeline. Two placement options allow trading latency for timing closure.

**`SPLIT_SOPS`:** When enabled, the 8 product pairs are split into two groups of 4 and accumulated in two separate SOP trees, then merged. This shortens the compression tree depth at the cost of one extra adder level.

**`MXFP4_SUPPORT`:** Enables the FP4 mantissa expand path. MXFP4 elements (1 sign + 2 exp + 1 mantissa) are multiplied with a reduced-precision multiplier before entering the same accumulation tree.

**INT8 2× mode (`tt_auto_signed_mul8x8`):** Two INT8 multiplications are packed into a single 16×16 signed multiplier using the Karatsuba trick — SRCA_hi and SRCA_lo × SRCB. Result is a 32-bit integer that enters the integer accumulator path (`tt_int8_int16_int32_acc`).

**Sum-of-products SOP16 (`tt_sop16_1`):** When 16 products are available (FP_TILE_MMUL_ROWS=2 × 8 pairs), two groups of 8 are combined through an extended compressor tree.

---

### 6.6 FP Multiplier (`tt_fp_mul_raw`)

**File:** `fpu/rtl/tt_fp_mul_raw.sv`

| Parameter | Range | Description |
|---|---|---|
| `MAN_A_PREC` | 2–10 | Mantissa A bits (excluding hidden bit) |
| `MAN_B_PREC` | 2–10 | Mantissa B bits |
| `EXP_PREC` | 5–8 | Exponent bits |
| `SKIP_HIDDEN_BIT` | 1 | Prepend implicit 1 to each mantissa |
| `PARTITIONED_MULS` | 0/1 | Split multiply for timing (FP32) |

**Operation:**
```
result_sign = sign_A XOR sign_B
result_exp  = {1'b0, exp_A} + {1'b0, exp_B}   // +1 bit for overflow
result_man  = (1 ++ man_A) × (1 ++ man_B)     // double-width product
```

**Partitioned mode** (for `MAN_PREC ≥ 11`, used in FP32 path): Splits as:
```
A = A_hi × 2^K + A_lo
B = B_hi × 2^K + B_lo
A×B = A_hi×B_hi×2^(2K) + (A_hi×B_lo + A_lo×B_hi)×2^K + A_lo×B_lo
```
The four sub-products are 11×11 bits, which fit within standard cell array multiplier sizes available in the cell library. The partitioned adder runs at higher frequency because the carry chain is shorter.

**Why no normalization:** The multiplier outputs a raw double-width product. Normalization (left-shift to align leading 1) happens once at the end of the accumulation tree — not per partial product. This avoids N×normalize overhead (where N=8 pairs) at the cost of slightly wider compressor-tree inputs.

---

### 6.7 Exponent Path (`tt_exp_path_v4`)

**File:** `fpu/rtl/tt_exp_path_v4.sv`

| Parameter | Value | Description |
|---|---|---|
| `NUM_PAIR` | 9 | Number of A×B exponent pairs |
| `SPECIAL_NUMBER_SUPPORT` | 0/1 | INF/NAN detection |
| `MXFP4_SPECIAL_NUMBER_SUPPORT` | 0/1 | MXFP4 E0M3 special values |

**Operation:**
1. Expand each 8-bit exponent to 9-bit: `{1'b0, exp}` (prevents sign confusion).
2. Compute 9-bit product exponent: `prod_exp[i] = exp_A[i] + exp_B[i]`.
3. Tree-reduce all `NUM_PAIR` product exponents using `tt_parallel_max_exp3` (3-input) and `tt_max_exp_9` (9-input) to find `max_exp[8:0]`.
4. Generate `small_shift[i]` flag: `= (prod_exp[i][8:7] != max_exp[8:7])`. When true, this product is more than 128× smaller than the maximum and can be treated as zero (its contribution is in the guard-bit range). The barrel shifter in `tt_dual_align` uses this flag to skip the full alignment computation for negligible terms.

**Global max pool mode (`i_gmpool`):** Bypasses the product exponent computation and instead uses the raw SRCA exponent as the alignment reference. Used for max-pooling operations where the "multiply" is conceptually a comparison.

---

### 6.8 Alignment (`tt_dual_align`, `tt_barrel_rshift`)

**`tt_barrel_rshift`:**

| Stage | Shift Amount | Mux Width |
|---|---|---|
| Stage 1 (bit 0) | 0 or 1 | Full width |
| Stage 2 (bit 1) | 0 or 2 | Full width |
| Stage 3 (bit 2) | 0 or 4 | Full width |
| Stage 4 (bit 3) | 0 or 8 | Full width |
| Stage 5 (bit 4, 5×5 mode) | 0 or 16 | Masked width |

Each stage is a row of 2:1 muxes. The `LG2_SHAMT` parameter enables only as many stages as needed for the precision. For FP16 (max shift = 30), 5 stages suffice. For INT8 (max shift = 8), 4 stages suffice.

**5×5 mode optimization:** For small shift amounts (lower 4 bits only), the 5th stage passes through unchanged. For large shift amounts (bit 4 = 1), the lower bits of the output are masked to zero, preventing subnormal residuals that would corrupt the accumulation.

**`tt_dual_align`:**

Parameters:
| Parameter | Value | Description |
|---|---|---|
| `PREC` | 10–23 | Input mantissa precision |
| `ARITHMETIC_SHIFT` | 0/1 | Preserve sign bit during shift |
| `RNE_ENABLED` | 0/1 | Generate guard/sticky bits |

Outputs two aligned values (`val0`, `val1`) differing by 1 ULP for round-to-nearest-even tie-breaking. The `o_rnd_bit` and `o_rnd_bit_alt` bits are passed to the stochastic rounding module.

**SW impact:** The alignment stage is what enables mixed-format MAC — SRCA and SRCB can be in different precisions (e.g., SRCA=FP32, SRCB=FP16B). The alignment always normalizes to the maximum exponent regardless of input format.

---

### 6.9 Compressor Trees

**`tt_three_two_compressor` (3:2):**
- `PREC` parallel full adders: `{carry[i+1], sum[i]} = A[i] + B[i] + C[i]`
- Output: `PREC`-bit sum + `(PREC+1)`-bit carry (one position left of sum)
- Depth: 1 FA level

**`tt_four_two_compressor` (4:2):**
- Two cascaded FA stages
- `BALANCED=1`: stage-1 critical path = stage-2 critical path → reduces setup time in PAR
- `BALANCED=0`: fast path for delay-insensitive contexts
- Depth: 2 FA levels

**Compression tree for 8 products (Wallace tree):**

```
 Input:  man₀  man₁  man₂  man₃  man₄  man₅  man₆  man₇   dest_acc
         [10b] [10b] [10b] [10b] [10b] [10b] [10b] [10b]   [10b]

 Level 1 (two 4:2 compressors in parallel):
  ┌─────────────────────────┐   ┌─────────────────────────┐
  │  tt_four_two_compressor │   │  tt_four_two_compressor │
  │  (man₀, man₁, man₂,    │   │  (man₄, man₅, man₆,    │
  │         man₃)           │   │         man₇)           │
  │       BALANCED=1        │   │       BALANCED=1        │
  └──────┬──────┬───────────┘   └──────┬──────┬───────────┘
         │sum0  │carry0                │sum1  │carry1
         [10b]  [10b]                  [10b]  [10b]

 Level 2 (one 4:2 compressor):
         ┌──────────────────────────────┐
         │   tt_four_two_compressor     │
         │   (sum0, carry0, sum1, carry1)│
         └──────────┬──────┬────────────┘
                    │sum2  │carry2
                    [11b]  [11b]

 Level 3 (tt_multiop_adder — carry-propagate):
         ┌───────────────────────────────┐
         │  result = sum2 + carry2       │
         │         + dest_acc (if accum) │
         └───────────────┬───────────────┘
                         │ final_sum [11b]
                         ▼
                  tt_fp_sop_normalize
```

Total logic depth: 3 FA levels = O(log₂8) as expected.

---

### 6.10 Multi-Operand Adder (`tt_multiop_adder`)

**File:** `fpu/rtl/tt_multiop_adder.sv`

```verilog
module tt_multiop_adder #(parameter WIDTH = 9);
  o_sum = i_op0 + i_op1 + i_op2;
```

Three operands: `op0` = carry-save sum, `op1` = carry-save carry, `op2` = (optional) previous destination accumulator value. The final carry-propagate adder runs only once after all partial products are compressed, minimizing the total carry-chain length.

**Destination accumulation path:** When `DEST_ADD_WITH_SOP=1`, the existing destination register value (`op2`) is read back and added here. This implements `dest += A × B` (accumulate mode for multi-tile GEMM) with zero overhead compared to `dest = A × B`.

---

### 6.11 Integer Multipliers (`tt_mul8`, `tt_mul16`, `tt_mul32`)

**Files:** `tt_soc_common/rtl/tensix/tt_mul8.sv`, `tt_mul16.sv`, `tt_mul32.sv`

All three use **Radix-4 Modified Booth Encoding (MBE)** with a Wallace carry-save tree.

**Radix-4 Booth recoding:**
```
For each 2-bit group j of multiplier B:
  sel[j] = {B[2j+2], B[2j+1], B[2j]}
  case(sel):
    3'b000: PP[j] = 0
    3'b001: PP[j] = +A
    3'b010: PP[j] = +A
    3'b011: PP[j] = +2A
    3'b100: PP[j] = -2A
    3'b101: PP[j] = -A
    3'b110: PP[j] = -A
    3'b111: PP[j] = 0
```
Negative multiples use 2's complement inversion + 1 (carries injected at partial product boundaries).

**CSA tree reduction:**
| Module | Input bits | Partial products | CSA stages | Output |
|---|---|---|---|---|
| `tt_mul8` | 8×8 | 5 | 2 | 16-bit (S+R pair) |
| `tt_mul16` | 16×16 | 9 | 3 | 32-bit (S+R pair) |
| `tt_mul32` | 32×32 | 17 | 6 | 64-bit (S+R pair) |

Outputs are two vectors `o_s6_1a` (partial sum) and `o_r6_1a` (partial carry), to be combined by a carry-propagate adder at the instantiating level. The split-sum output allows the final adder to be shared across multiple multipliers in a parallel accumulation tree.

**SW usage:** These are used in RISC (integer ADDGPR / MULADD) computations, not in the FPU MAC array. The FPU MAC uses `tt_fp_mul_raw` for floating-point. `tt_mul8` is also used for INT8 sparse-attention scoring computations in the SFPU path.

---

### 6.12 Source Register Interfaces (SRCA / SRCB)

#### SRCA (`tt_fpu_tile_srca`)

**File:** `fpu/rtl/tt_fpu_tile_srca.sv`

| Port | Width | Description |
|---|---|---|
| `i_srca_rd_tran` | `srca_rd_tran_t` | Read transaction (row address, format) |
| `o_srca_fpu_data_ext` | `[MMUL_ROWS][COLS][EXT_DATUM_WIDTH]` | Extended format output to FP Lane |
| `o_srca_fpu_zf_exp/man` | 1 per datum | Zero flags (separate for exp and man paths) |
| `o_srca_fpu_sman_fp4` | — | FP4 sign+mantissa packed path |
| `o_srca_fpu_exp_fp4` | — | FP4 exponent packed path |

`EXT_DATUM_WIDTH = 1 + EXT_EXP_WIDTH + EXT_MAN_WIDTH = 1 + 8 + 10 = 19 bits`

**Zero flag generation:** Zero flags are computed from the **storage format** (narrow representation) before expansion. This keeps the NOR gate fan-in at ≤8 bits rather than 19, reducing the critical path through the zero-flag → multiply-bypass logic.

**Lane selection (`tt_srca_lane_sel`):** For non-unit-stride access patterns, a lane selector mux routes any physical SRCA row to any logical FP Lane input. This enables in-place SRCA row permutation, used for implementing convolution where filter rows are systematically reused across output positions.

#### SRCB (`tt_fpu_tile_srcb`, `tt_srcb_registers`)

**Files:** `fpu/rtl/tt_fpu_tile_srcb.sv`, `fpu/rtl/tt_srcb_registers.sv`, `fpu/rtl/tt_fpu_v2.sv`

---

##### RTL Correction — Where SRCB Actually Lives

The SRCB register file is **not per-G-Tile**. It is a **single centralized instance** at the `tt_fpu_v2` top level, instantiated as `srcb_regs` (`tt_srcb_registers`). Its output bus `srcb_rd_tran` is **broadcast identically to both G-Tile instances** (`gen_gtile[0]` and `gen_gtile[1]`):

```systemverilog
// tt_fpu_v2.sv (lines 848-932, 1259-1260)
tt_srcb_registers srcb_regs ( .o_srcb_out_rows(srcb_rd_tran), ... );

for (genvar g = 0; g < NUM_GTILES; g++) begin : gen_gtile
    fpu_gtile_tran[g].srcb_rd_tran   = srcb_rd_tran;   // same bus → both tiles
    fpu_gtile_tran[g].srcb_rd_params = srcb_rd_params;  // same params
end
```

There is no per-G-Tile SRCB register file. `tt_fpu_tile_srcb` is a **pipeline stage** (buffer + format decode) inside each FP Tile, not a register storage block.

---

##### P&R View — Physical Placement of `srcb_regs`

In a place-and-route floorplan, the SRCB register file sits at the **bottom center** of the FPU block, equidistant between `gen_gtile[0]` (left half) and `gen_gtile[1]` (right half). This placement is dictated by the broadcast fan-out geometry.

```
  FPU block floorplan (tt_fpu_v2)
  ════════════════════════════════════════════════════════════════════
  │                                                                  │
  │   gen_gtile[0]  (cols 0–7)      │   gen_gtile[1]  (cols 8–15)  │
  │   ┌──────────────────────────┐  │  ┌──────────────────────────┐ │
  │   │  M-Tile                  │  │  │  M-Tile                  │ │
  │   │  FP Tile [0..FP_ROWS-1]  │  │  │  FP Tile [0..FP_ROWS-1]  │ │
  │   │  DEST slice (rows 0–511) │  │  │  DEST slice (rows 0–511) │ │
  │   │  SRCA regs (per-column)  │  │  │  SRCA regs (per-column)  │ │
  │   └────────────┬─────────────┘  │  └────────────┬─────────────┘ │
  │                │                │                │               │
  │           srcb_rd_tran          │           srcb_rd_tran         │
  │           (left half)◄──────────┼──────────►(right half)        │
  │                │                │                │               │
  │                └────────────────┼────────────────┘               │
  │                                 │                                │
  │                   ┌─────────────▼─────────────┐                 │
  │                   │   tt_srcb_registers        │  ← BOTTOM CENTER│
  │                   │   instance: srcb_regs      │                 │
  │                   │                            │                 │
  │                   │  BANK_DEPTH × SRCB_DATUMS  │                 │
  │                   │  latch array (ICG-gated)   │                 │
  │                   │                            │                 │
  │                   │  Write port ◄──────────────┼──── TDMA CH1   │
  │                   │  (from unpacker srcb_wr_tran)               │
  │                   └────────────────────────────┘                 │
  │                                 ▲                                │
  │                                 │ NoC / L1 read                  │
  │              i_srcb_wr_tran (from tt_tdma unpack CH1)            │
  │                                                                  │
  ════════════════════════════════════════════════════════════════════

  Physical rationale for bottom-center placement:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Signal          │ Direction            │ Reason               │
  ├─────────────────────────────────────────────────────────────────┤
  │  srcb_wr_tran    │ bottom-in (from TDMA)│ TDMA is below FPU    │
  │                  │                      │ in tile floorplan     │
  │  srcb_rd_tran    │ center-out → left    │ equal wire length to  │
  │  (broadcast)     │ center-out → right   │ both G-Tile halves   │
  │                  │                      │ minimizes clock skew  │
  │  srcb_rd_params  │ same broadcast       │ control accompanies  │
  │                  │                      │ data (same path)     │
  └─────────────────────────────────────────────────────────────────┘
```

**Why bottom-center is optimal for P&R:**

1. **Symmetric wire length to both G-Tiles.** `gen_gtile[0]` covers the left 8 columns; `gen_gtile[1]` covers the right 8. A center placement minimizes the max wire length from `srcb_regs` to the farthest column in either half, reducing RC delay and holding timing margin equal on both sides.

2. **Write port proximity to TDMA.** The TDMA unpacker CH1 feeds SRCB. In the Tensix tile floorplan, TDMA sits below the FPU block (closer to L1). A bottom placement keeps the `srcb_wr_tran` wire short, reducing the critical path from L1 read → SRCB write.

3. **No SRCB per-G-Tile → area saving.** Because both G-Tiles read the same SRCB row simultaneously (SRCB is broadcast, not addressed), there is no reason to replicate the register file. One central instance eliminates 50% of SRCB storage area compared to a per-G-Tile design.

4. **Two-phase broadcast.** The G-Tile captures SRCB in two pipeline phases: `i_srcb_valid[EXPS]` opens the exp pipeline latch; `i_srcb_valid[MANS]` (one cycle later) opens the man latch. Both phases receive the same broadcast wire from `srcb_regs` — the phase-split timing is controlled by the enable signals, not by separate data paths.

---

##### Signal flow (corrected):

```
  TDMA unpacker CH1
        │  srcb_wr_tran  (write address + data)
        ▼
  tt_srcb_registers  (srcb_regs, bottom-center of FPU)
        │  latch array — ICG per datum, same structure as DEST reg_bank
        │
        │  srcb_rd_tran  (read data: SRCB_OUTPUT_ROWS × SRCB_OUTPUT_COLS × datum)
        │  srcb_rd_params (format, exp/man phase control)
        │
        ├──────────────────────────────────────────┐
        │                                          │
        ▼  (left half)                             ▼  (right half)
  gen_gtile[0] / fpu_gtile_tran[0]          gen_gtile[1] / fpu_gtile_tran[1]
        │  srcb_rd_tran = srcb_regs output         │  identical data
        ▼                                          ▼
  tt_srcb_pipe_stage  (u_srcb_rows_ff)      tt_srcb_pipe_stage
        │  latch on i_srcb_valid edge              │
        ▼                                          ▼
  Per-column tt_fpu_tile_srcb                Per-column tt_fpu_tile_srcb
  (buffer + INT8 lane sel + metadata)        (same)
        │                                          │
        ▼                                          ▼
  FP Lane × 8 columns (left)                FP Lane × 8 columns (right)
  SRCB operand to tt_fp_mul_raw              SRCB operand to tt_fp_mul_raw
```

---

SRCB differs from SRCA in the following ways:

1. **Broadcast topology:** One SRCB row is driven to all `FP_TILE_ROWS` FP Tiles in a column. A single L1 read feeds all rows simultaneously — the `FP_TILE_ROWS × SRCB_ROW_DATUMS` fan-out is implemented as a wire broadcast (no mux overhead).
2. **Two-phase split:** SRCB exponent is available at pipeline stage S2; mantissa at S3 (one cycle later). The G-Tile orchestrates this timing split via `i_srcb_valid[EXPS]` / `i_srcb_valid[MANS]` enable signals — not separate data paths.
3. **INT8 2× packing:** Two INT8 values are packed per 16-bit SRCB slot. `tt_srcb_lane_sel` extracts the upper and lower bytes and routes them to the two `tt_auto_signed_mul8x8` instances in the FP Lane.
4. **Metadata tracking:** `tt_srcb_metadata` holds per-row valid and format state. The metadata propagates through the pipeline stages independently of data, allowing the control path to stay ahead of the data path.
5. **Centralized, not replicated:** Unlike SRCA (which has per-column storage), SRCB is a single register file at FPU top level. The matrix B operand (e.g., weight vector) is the same across all output rows — centralization reflects this mathematical property directly in silicon topology.

---

### 6.13 ALU Configuration Registers (`tt_alu_cfg_regs`)

Key configuration registers and their HW effect:

| Register | Field | HW Effect |
|---|---|---|
| `ALU_FORMAT_SPEC_REG` | `SrcA_val_format` | Sets SRCA format decode path |
| | `SrcB_val_format` | Sets SRCB format decode path |
| | `Dstacc_override` | Forces destination accumulation format |
| `ALU_ACC_CTRL` | `Fp32_enabled` | Enable FP32 accumulation mode (512 dest rows) |
| | `SFPU_Fp32_enabled` | SFPU operates in FP32 |
| | `INT8_math_enabled` | Switch FP Lane to INT8 2× mode |
| | `Zero_Flag_disabled` | Disable zero-flag bypass (debug/test) |
| `ALU_ROUNDING_MODE` | `Fpu_srnd_en` | Enable stochastic rounding |
| | `GS_LF` | Global-scale local-format (BFP8 mode) |
| | `Bfp8_HF` | BFP8 half-float variant |
| `RISC_DEST_ACCESS_CTRL` | `SRC0-3_swizzle` | Re-order DEST rows for RISC access |
| | `unsigned` | Unsigned INT8 mode |
| `DEST_REGW_BASE` | — | Base row address for destination writes |
| `DEST_SP_BASE` | — | Secondary (ping-pong) destination base |
| `STATE_RESET_EN` | — | Auto-clear DEST on tile transition |

**SW usage:** The ALU configuration is set by TRISC1 before issuing the MOP (math) loop. The format spec registers must be consistent with the TDMA unpacker output format. A typical sequence:
```c
cfg_reg_write(ALU_FORMAT_SPEC_REG, {.SrcA=FP16B, .SrcB=FP16B, .Dstacc=FP16B});
cfg_reg_write(ALU_ACC_CTRL, {.Fp32=0, .INT8=0, .ZF_dis=0});
cfg_reg_write(ALU_ROUNDING_MODE, {.srnd_en=1});
issue_mop(MVMUL, loop_count=M/4);
```

---

## 7. Special Function Unit (SFPU)

### 7.0 SFPU Block Diagram

```
 TRISC1 issues SFPU instructions (SFPLOAD/MAD/STORE)
        │
        ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │                       tt_sfpu                                   │
 │                                                                 │
 │  instrn[31:0] ──► decode ──► op_type: LOAD/SIMPLE/MAD/STORE    │
 │  dst_fmt_8bit, dst_fmt_fp32 ─► format select                   │
 │                                                                 │
 │  DEST reg read (4 rows × 16 cols)     ← i_dst_reg_s3           │
 │         │                                                       │
 │  ┌──────▼──────────────────────────────────────────────────┐   │
 │  │  tt_sfpu_lregs  (4 × 19-bit extended per row elem)      │   │
 │  │                                                          │   │
 │  │  lreg[0] ┬── writable from MAD s3/s4                    │   │
 │  │  lreg[1] ┤   writable from LOAD                         │   │
 │  │  lreg[2] ┤   readable as MAD operands                   │   │
 │  │  lreg[3] ┘   transpose: cyclic rotate (Horner eval)     │   │
 │  └──────┬───────────────────────────────────────────────────┘  │
 │         │ lreg[a], lreg[b], lreg[c]                            │
 │  ┌──────▼──────────────────────────────────────────────────┐   │
 │  │  tt_t6_com_sfpu_mad                                     │   │
 │  │                                                          │   │
 │  │  Stage S3:   mul_mant = man_A × man_B  [47:0]           │   │
 │  │              exp_prod = exp_A + exp_B - bias             │   │
 │  │              zero/inf/nan detection                      │   │
 │  │                   │                                      │   │
 │  │  Stage S4:   align C to prod_exp                        │   │
 │  │              result = prod + C                           │   │
 │  │              normalize + round                           │   │
 │  │              flags: overflow, nan, inf, denorm           │   │
 │  └──────┬───────────────────────────────────────────────────┘  │
 │         │ result [FP32 or FP16]                                 │
 │         ▼                                                       │
 │  condition code (SFPU_CC_BITS=2): SFPSETCC / SFPCOMPC           │
 │         │                                                       │
 │  STORE predicated by CC ──► DEST reg write (4 rows × 16 cols)  │
 │                              o_dst_wren_s3, o_dst_reg_addr_s3  │
 └─────────────────────────────────────────────────────────────────┘

 Connection to FPU G-Tile:
 ┌────────────────┐    sfpu_dest_intf    ┌──────────────────┐
 │  tt_sfpu       │◄───────────────────►│  tt_fpu_gtile    │
 │  (reads/writes │                     │  (DEST reg owner) │
 │   DEST regs)   │                     │                  │
 └────────────────┘                     └──────────────────┘

 Processing model (4 rows per instruction):
 ┌────────────────────────────────────────────────────────┐
 │  DEST[  0.. 3] × 16 cols  ← pass 0  (SFPU_ROWS = 4)  │
 │  DEST[  4.. 7] × 16 cols  ← pass 1                    │
 │  DEST[  8..11] × 16 cols  ← pass 2                    │
 │  ...                                                   │
 │  DEST[1020..1023] × 16 cols ← pass 255 (for 1024 rows)│
 └────────────────────────────────────────────────────────┘
```

### 7.1 SFPU Architecture

**File:** `fpu/rtl/tt_sfpu.sv`

The SFPU is a **scalar iterative processor** dedicated to non-linear activation functions. It reads and writes the **destination register file** after the FPU completes matrix accumulation.

| Parameter | Value | Description |
|---|---|---|
| `DATUM_WIDTH_HF` | 16 | Half-float storage in destination |
| `LREG_WIDTH` | 32 | Local register precision (FP32) |
| `NUM_REGS` | 4 | Local registers (lreg0–lreg3) |
| `DEST_ADDR_WIDTH` | 10 | Destination address width |
| `SFPU_ROWS` | 4 | Rows processed per instruction cycle |
| `FP_TILE_COLS` | 1 | (1 SFPU serves 1 G-Tile column group) |
| `SFPU_CC_BITS` | 2 | Condition code bits |

**Processing model:** The SFPU processes 4 rows of the destination register file per instruction. For a 16-row tile (typical), 4 SFPU instruction sequences process the full tile (one `SFPU_ROWS`-wide strip per pass). The TRISC1 thread issues repeated SFPU instructions in a software loop.

**Instruction set (`tt_sfpu.sv` ISA):**

| Type | Instructions | Description |
|---|---|---|
| `LOAD` | SFPLOAD, SFPLOADI | Load destination row into lreg[d] |
| `SIMPLE` | SFPABS, SFPNEG, SFPNOT, SFPSETCC, SFPCOMPC | Unary ops and condition code ops |
| `MAD` | SFPMAD | `lreg[d] = lreg[a] × lreg[b] + lreg[c]` |
| `ROUND` | SFPROUND | Apply precision reduction to lreg |
| `STORE` | SFPSTORE | Write lreg[d] back to destination |
| `READ` | SFPIADD (integer mode), SFPSHFT | Shift and integer operations |
| `NOP` | SFPNOP | Pipeline advance without compute |

**Condition codes (SFPU_CC_BITS=2):** SFPU supports predicated execution via `SFPSETCC` (set from comparison) and `SFPCOMPC` (complement). This enables branching without a RISC branch instruction, e.g., for max(x,0) with a condition-code-gated SFPSTORE.

---

### 7.2 SFPU MAD Pipeline (`tt_t6_com_sfpu_mad`)

**File:** `tt_tensix_common/rtl/tt_t6_com_sfpu_mad.sv`

Two-cycle pipelined FMA: `result = A × B + C`

**Stage S3 (multiply):**
- Multiplier: `i_mul_mant_s3[47:0]` (48-bit mantissa product, pre-computed)
- Format select: `i_sp_mad` (FP32), `i_fp16a_mad` (FP16A E5M10), `i_fp16b_mad` (FP16B BF16)
- Exponent: `exp_A + exp_B - bias`
- Special case detection: zero, INF, NaN for A, B, C

**Stage S4 (add + normalize):**
- Alignment: align C to product exponent
- Addition: product mantissa + aligned C mantissa
- Normalization: leading-zero detect + left-shift
- Rounding: guard/sticky/round bits → RNE
- Status flags: `o_overflow_s4`, `o_nan_s4`, `o_inf_s4`, `o_denorm_s4`

**Format-specific exponent biases:**
| Format | Exponent bits | Bias |
|---|---|---|
| FP32 | 8 | 127 |
| FP16A | 5 | 15 |
| FP16B | 8 | 127 |

**`TWO_CYCLE=1`:** The multiply-then-add pipeline is split across two clock cycles. The intermediate product is registered in `o_partial_results_s3`. This allows the SFPU to accept a new operand every cycle (fully pipelined), so 4 rows × `N_poly_terms` MAD operations run at 1 result/cycle throughput.

---

### 7.3 SFPU Local Registers (`tt_sfpu_lregs`)

**File:** `fpu/rtl/tt_sfpu_lregs.sv`

| Parameter | Value | Description |
|---|---|---|
| `NUM_REGS` | 4 | Local register count |
| `DATA_WIDTH` | 19 | Extended format (1+8+10) |

Four write ports (s3, s3s4, s4, transpose):
- **s3:** Write from MAD stage 3 (intermediate result)
- **s3s4:** Write from combined stage 3/4 result
- **s4:** Write from MAD stage 4 (final result)
- **transpose:** Shift register across all 4 regs (for polynomial evaluation reuse)

**Parity:** Each 9.5-bit half of each register carries an odd-parity bit. A parity error (`o_parity_err`) asserts if any register is corrupted, reported through the error aggregate chain.

**Transpose mode:** `i_transpose_or_shift_s3` enables cyclic rotation of the 4 local registers. This is used in polynomial evaluation to efficiently compute `p(x) = a0 + x*(a1 + x*(a2 + x*a3))` in Horner form: lreg[0] holds accumulated result, lreg[1..3] hold polynomial coefficients. Transpose rotates the coefficient register into lreg[0] without explicit LOAD/STORE.

---

### 7.4 SFPU Instruction Dispatch & SW Usage

SFPU instructions are issued by TRISC1 as part of the math MOP sequence. The SFPU runs in parallel with the main FPU M-Tile when the instruction tag includes SFPU-type opcodes (`sfpu_tag_t.fp32_en`, `sfpu_tag_t.dst_fmt_spec`).

**Typical activation function implementation (GeLU approximation):**
```
// GeLU(x) ≈ 0.5 * x * (1 + tanh(√(2/π) * (x + 0.044715x³)))
// SW sequence on SFPU (4 rows per pass):
SFPLOAD  lreg0, dest_row          // load x from destination
SFPMAD   lreg1 = lreg0 * lreg0 * lreg0  // x^3 (2 MADs)
SFPMAD   lreg1 = 0.044715 * lreg1 + lreg0  // x + 0.044715*x^3
SFPMAD   lreg1 = √(2/π) * lreg1   // scale
// tanh via polynomial: 5-7 MAD iterations
SFPMAD   lreg2 = c5 * lreg1 + c4
SFPMAD   lreg2 = lreg2 * lreg1 + c3
...
SFPMAD   lreg1 = 0.5 * lreg0 * (1.0 + lreg2)  // final scale
SFPSTORE dest_row, lreg1           // write back
```

The TRISC1 kernel loops this sequence over all 1024 destination rows (256 passes of 4 rows each). The SFPU sustains ~1 MAD output per cycle, so a 7-term polynomial over 1024 rows completes in ≈7168 cycles.

---

## 8. L1 Shared Memory

**Files:** `rtl/enc/tt_rtl/tt_tensix_neo/src/hardware/tensix/l1/tt_t6_l1.sv`

### 8.0 L1 Architecture Diagram

```
 Clients (16 total):
 ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
 │  BRISC   │ │ TRISC0   │ │ TRISC1   │ │ TRISC2   │ │ Dispatch │
 │  RW port │ │ RW port  │ │ RW port  │ │ RW port  │ │ WR port  │
 └─────┬────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
       │           │            │             │            │
 ┌─────┴───────────┴────────────┴─────────────┴────────────┴──────────┐
 │                                                                     │
 │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐     │
 │  │  TDMA    │    │  TDMA    │    │  TDMA    │    │  TDMA    │     │
 │  │ Unpack   │    │ Unpack   │    │  Pack    │    │  Pack    │     │
 │  │  CH0 RD  │    │  CH1 RD  │    │  CH0 WR  │    │  CH1 WR  │     │
 │  └─────┬────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘     │
 │        │              │               │               │            │
 │        └──────────────┴───────────────┴───────────────┘            │
 │                                 │                                  │
 │  ┌──────────────────────────────▼──────────────────────────────┐  │
 │  │               tt_t6_l1_superarb                              │  │
 │  │                                                              │  │
 │  │   Priority:  TDMA > TRISC/BRISC > Dispatch                  │  │
 │  │   Per-bank:  tt_t6_l1_arb (round-robin, PHASE_CNT=4)        │  │
 │  │   Burst:     tt_t6_l1_sticky_mux (hold N cycles)            │  │
 │  │   Tree:      tt_t6_l1_rr_arb_tree                           │  │
 │  └──────────┬─────────────────────────────────────────────────┘  │
 │             │  bank select + addr + data                          │
 │    ┌────────┴──────────────────────────────────────────────────┐  │
 │    │ Bank 0    Bank 1    Bank 2  ...  Bank 14   Bank 15        │  │
 │    │                                                            │  │
 │    │  Each bank:  tt_t6_l1_bank                                │  │
 │    │    └── tt_t6_l1_sub_bank_atomic  (CAS, fetch-add)        │  │
 │    │         128-bit data + 8-bit SECDED ECC                   │  │
 │    │         depth: configurable (L1_CFG)                      │  │
 │    └────────────────────────────────────────────────────────────┘  │
 │                                                                     │
 │   Address interleaving:  addr[3:0] → bank select                   │
 │   Sequential access hits all 16 banks in rotation                  │
 └─────────────────────────────────────────────────────────────────────┘

 ECC per 128-bit word:
 ┌──────────────────────────────────────────────────┐
 │  128-bit data  +  8-bit SECDED check bits        │
 │  on read:  syndrome computed → 1-bit correct,   │
 │            2-bit error → tt_err_aggregate        │
 └──────────────────────────────────────────────────┘
```

### 8.1 Bank Structure

| Attribute | Value |
|---|---|
| Bus width | 128 bits (16 bytes) per access |
| Bank count | 16 (from `tt_t6_l1_arb`: `BANK_CNT=16`) |
| ECC | SECDED per 128-bit word |
| Phase count | 4 (pipeline stages in L1 bank) |
| Client count | 16 (`CLIENT_CNT=16`) |

**Interleaving:** Addresses are bank-interleaved so that consecutive 16-byte words map to consecutive banks. This means a sequential 256-byte read (16 words) hits all 16 banks simultaneously — full L1 bandwidth from a single stream.

**Sub-bank atomics (`tt_t6_l1_sub_bank_atomic`):** Each bank has an atomic pipeline that executes read–modify–write as a single indivisible operation. Supported atomics: fetch-add, compare-and-swap. The sub-bank serializes conflicting atomic requests from different clients.

---

### 8.2 Client Arbitration

**`tt_t6_l1_superarb` / `tt_t6_l1_arb`:**

The super-arbiter manages 16 clients across 16 banks. The arbiter uses a per-bank round-robin with **phase-based priority rotation** (`PHASE_CNT=4`) — priority cycles through 4 phases each clock:

- Phase 0: TDMA channels (highest priority — prevents SFPU stalls)
- Phase 1: TRISC loads/stores
- Phase 2: BRISC loads/stores
- Phase 3: NoC2L1 streaming (dispatch engine writes)

**Sticky mux:** `tt_t6_l1_sticky_mux` holds the bank-client connection for `N` cycles when a burst is in progress. This avoids re-arbitrating every cycle for long sequential accesses (e.g., TDMA reading a full tile row of 256 bytes = 2 back-to-back 128-bit reads). The burst hold-time is configurable per client type.

**`tt_t6_l1_flex_client_port`:** Adapter modules convert between the L1's internal `RW` (read-write combined) interface and client-specific `RD`-only or `WR`-only interfaces:
- `tt_t6_l1_flex_client_rd_port` — TRISC read-only (e.g., instruction fetch)
- `tt_t6_l1_flex_client_wr_port` — TDMA packer write-only

This reduces port width for clients that only need one direction, saving mux area.

**`tt_t6_l1_fifo_v3`:** FIFO buffers inserted between clients and the arbiter to absorb latency mismatches. A client can issue multiple outstanding requests without stalling on L1 access latency. FIFO depth is tuned per client type based on expected burst size.

---

### 8.3 ECC & Error Handling

Each 128-bit L1 word uses SECDED (single-error-correct, double-error-detect):
- 8 check bits per 128-bit word (= [128,120,8] Hamming code)
- Single-bit error: silently corrected before data delivery
- Double-bit error: asserts error interrupt through `tt_err_aggregate`

L1 ECC errors are reported with the faulty address in `o_err_data[31:0]` and error code `o_err_code[15:0]` from `tt_err_aggregate`. The error travels through the EDC ring to the host.

**`tt_t6_l1_latch_reg_array`:** Implements the read-data pipeline registers using latch-based arrays for area efficiency. Each stage's valid signal gates the latch to prevent meta-stability.

---

## 9. Destination Register File

**Files:** `registers/rtl/tt_reg_bank.sv`, `tensix/instrn_path/rtl/tt_dstac_to_mem.sv`

### 9.0 Destination Register File Diagram

```
 Writers:                                    Readers:
 FP Lane × 16 ──────────────────────────►   TDMA Packer CH0 / CH1
 (one 16-bit value per col per cycle)        SFPU (LOAD/STORE)
                                             TRISC (RISC_DEST_ACCESS)
              ┌──────────────────────────────────────────────────────┐
              │   tt_reg_bank  (DEST register file)                  │
              │                                                       │
              │  FP16 mode:  1024 rows × 16 cols × 16-bit           │
              │  FP32 mode:   512 rows × 16 cols × 32-bit           │
              │                                                       │
              │  ┌─────────────────┐  ┌──────────────────┐          │
              │  │  Buffer A       │  │  Buffer B         │          │
              │  │  rows 0..511    │  │  rows 512..1023   │          │
              │  │  ← FPU writes   │  │  ← FPU writes     │          │
              │  │    (tile N)     │  │    (tile N+1)     │          │
              │  │  → Packer reads │  │  → Packer reads   │          │
              │  │    (tile N)     │  │    (tile N+1)     │          │
              │  └─────────────────┘  └──────────────────┘          │
              │       DEST_REGW_BASE ──►       DEST_SP_BASE ──►     │
              │                                                       │
              │  SETS=4 banks, DEPTH=64 rows/bank                   │
              │  DATUMS_IN_LINE=16, datum=16b                        │
              │  ENABLE_TRANSPOSE=1 (for packed col-major output)   │
              │  ENABLE_PARITY=0/1 (configurable)                   │
              │  ADJUST_FMT=1 (format adjust on write)              │
              └───────────────────────┬──────────────────────────────┘
                                      │ read [16 × 16b per row]
                                      ▼
              ┌───────────────────────────────────────────────────────┐
              │  tt_dstac_to_mem  (format conversion for packer)      │
              │                                                        │
              │  FP16B ──────────────────────────────► FP16B (pass)   │
              │  FP16B ──► truncate man → INT8/UINT8                  │
              │  FP16B ──► rebias exp → FP8 E4M3 / E5M2              │
              │  FP16B ──► sign-extend → INT16                        │
              │  FP16B ──► sign-extend → FP32 / INT32                 │
              │  Block exp extraction ──► separate exp section in L1  │
              └───────────────────────┬──────────────────────────────┘
                                      │ [128b word to L1 WR]
                                      ▼
                              tt_t6_l1 WR port

 Double-buffer ping-pong:
 ┌───────────┐   sem_post(MATH_DONE)   ┌───────────┐
 │  TRISC1   │ ───────────────────────► │  TRISC2   │
 │  (math)   │                         │  (pack)   │
 │           │ ◄─────────────────────── │           │
 │  swap     │   sem_post(PACK_DONE)    │           │
 │  buf ptr  │                         │           │
 └───────────┘                         └───────────┘
 Tile N → Buffer A                     Pack Buffer A → L1
 Tile N+1 → Buffer B  (concurrent)     Pack Buffer B → L1  (next)
```

### 9.1 Structure & Addressing

| Parameter | Value | Description |
|---|---|---|
| `DEPTH` | 64 (per bank) | Rows per register bank |
| `SETS` | 4 | Banks (double-buffer = 2 active buffers × 2 ping-pong) |
| `DATUMS_IN_LINE` | 16 | Elements per row (one per FP Lane column) |
| Total rows (FP16 mode) | `64 × 4 / 2 = 512 per buffer × 2 = 1024` | Total accessible rows |
| Element width | 16-bit (FP16) or 32-bit (FP32) | Per datum |
| `DEST_ADDR_WIDTH` | 10 bits | 1024 row addresses |
| `ADJUST_FMT` | 1 | Enable format adjustment on write |
| `ENABLE_TRANSPOSE` | 1 | Transpose output for packer |
| `ENABLE_PARITY` | 0/1 | Optional parity per element |

**Bank/set organization:** 4 sets allow:
- Set 0+1: Ping-pong buffer for FPU writes (`DEST_REGW_BASE` → Set 0, `DEST_SP_BASE` → Set 1)
- Set 2+3: Reserved for SFPU pass accumulation or secondary tile buffering

**Zero-flag output:** `o_zflags` provides per-column zero indicators for SRCA/SRCB register bypass. Used by the instruction engine to skip FPU operations when an entire row of the source matrix is zero.

---

### 9.2 Format Conversion (`tt_dstac_to_mem`)

**File:** `instrn_path/rtl/tt_dstac_to_mem.sv`

Converts destination register data from internal FP16 representation to packer output format:

```verilog
function assemble_data_word(i_pack_out_format, data_word, exp_word, data_ext_word, block_exp);
```

| Output Format | Conversion |
|---|---|
| `MXINT8` | FP16 → INT8 with block exponent normalization |
| `FP8R` (E4M3) | FP16 → E4M3 with bias adjustment |
| `FP8P` (E5M2) | FP16 → E5M2 with bias adjustment |
| `FLOAT16_B` | FP16 → BFloat16 (truncate mantissa) |
| `FLOAT32` | FP16 → FP32 (sign-extend mantissa) |
| `INT16` | FP16 → INT16 (scale by block exp) |
| `INT32` | FP16 → INT32 (full descale) |

`assemble_exp_word()` extracts the shared block exponent for BFP output formats, which is written to the L1 exponent section separately from the mantissa data.

**L1 container mode (`ENABLE_L1_CONTAINER=1`):** An alternative packing that stores both exponent and mantissa in a single contiguous L1 region, used for direct DMA to DRAM without further reorganization.

---

### 9.3 Double-Buffering & SW Management

The destination register file is logically partitioned into two ping-pong buffers:

- **Buffer A (rows 0–511):** FPU writes to rows `[DEST_REGW_BASE, DEST_REGW_BASE + tile_rows - 1]`
- **Buffer B (rows 512–1023):** `DEST_SP_BASE` points here (secondary pointer)

The TRISC2 packer reads from whichever buffer the FPU last completed writing to. TRISC1 (math) and TRISC2 (pack) synchronize via a semaphore:
```c
// TRISC1 after completing MOP math loop:
sem_post(SEM_MATH_DONE);    // signal TRISC2 to start packing
// swap dest buffer pointer:
swap(DEST_REGW_BASE, DEST_SP_BASE);
// immediately start next tile math
issue_mop(MVMUL, ...);     // writes to new buffer while TRISC2 drains old one
```

This overlap of pack and math stages is the key latency-hiding mechanism. For back-to-back 512×512 GEMM tiles, the effective throughput approaches the FPU compute rate with pack overhead hidden.

**`STATE_RESET_EN`:** When set, the destination register is automatically cleared to zero at the start of a new tile (between math loops). This eliminates an explicit software clear step and ensures correct accumulation semantics for sparse or partial tiles.

---

### 9.4 Why Latches, Not SRAM — `tt_reg_bank` Implementation Choice

**File:** `registers/rtl/tt_reg_bank.sv`

The DEST register file (`tt_reg_bank`) is implemented as a **latch array with per-datum ICG (Integrated Clock Gate) cells**, not as a standard foundry SRAM macro. This is a deliberate design choice visible in the RTL:

```
`ifdef VERILATOR
    localparam LATCH_ARRAY = 0;    // simulation: flops (simpler model)
`elsif DEST_BANKS_USE_FLOPS
    localparam LATCH_ARRAY = 0;    // PPA experiment override
`else
    localparam LATCH_ARRAY = 1;    // production silicon: latches (default)
`endif
```

The existence of `DEST_BANKS_USE_FLOPS` shows that flops were explicitly evaluated as an alternative, and latches were chosen for production.

---

**Why SRAM is not used:**

The core constraint is **simultaneous per-datum write-enable across the entire array**. The DEST array has:

| Parameter | Value | Consequence |
|---|---|---|
| `DEPTH` | 64 rows per bank | — |
| `SETS` | 4 banks | — |
| `DATUMS_IN_LINE` | 16 datums per row | — |
| Total datums | 64 × 4 × 16 = **4,096** | Each needs independent write-enable |
| Datum width | 19-bit extended (TF19) | — |

A standard foundry SRAM macro has **1–2 write ports** — it writes one address per cycle. To support per-datum write-enables (e.g., `wren[row][col]` with `transpose_write`, `strided_write`, `zero_out` modes all acting on different subsets of the 4,096 datums in one cycle), you would need a **4,096-write-port SRAM** — which does not exist.

**The latch implementation:**

```
// Per-datum pattern — 4,096 individual instances like this:
// (simplified; actual RTL uses generate loops over [row][datum])

tt_clkgater icg_row0_dat0 (
    .i_en  ( zf_masked_wren[0][0] ),   // write-enable for row 0, datum 0
    .i_clk ( i_clk ),
    .o_clk ( gated_clk[0][0] )
);

always_latch begin
    if (gated_clk[0][0]) begin
        regs0.row[0].datum[0] <= d_regs0.row[0].datum[0];
    end
end
```

Each datum has its own ICG cell. When `wren[row][datum]` is asserted, only that datum's latch opens; all others hold their value. This gives the full 4,096-entry independent write-enable matrix that SRAM cannot provide.

**Zero-latency combinational read:**

```
// Read path — purely combinational, no address decode, no cycle latency:
assign reg_intf.rd_data = regs0;    // direct wire assignment
```

The FPU needs to read any row from DEST on every cycle with zero latency for the accumulation pipeline. SRAM read requires a registered address and a clock cycle of latency. The latch array provides:
- **Combinational read**: the entire register file is continuously visible as wires
- **Zero read latency**: no address register, no read clock edge required
- **All rows readable simultaneously**: the packer and SFPU can both observe DEST in the same cycle

**Write control stabilization (setup time guard):**

```
if (LATCH_ARRAY && !DISABLE_WR_CTRL_LATCH) begin : stabilization_latch_cg
    always_latch begin
        if (!cgated_clk) begin          // latch on LOW phase of clock
            wr_ctrl  <= internal_wr_ctrl;
            i_wrdata <= chosen_data;
        end
    end
end
```

Write control and write data are captured in a **stabilization latch** on the LOW phase of the clock. The data latch itself opens on the HIGH phase. This is the standard two-phase latch register-file timing technique: ensures data and enables have settled before the latch becomes transparent, equivalent to setup/hold time management in SRAM bit-cells.

**Design tradeoff summary:**

| Property | Standard SRAM macro | DEST latch array |
|---|---|---|
| Write ports | 1–2 | 4,096 (per-datum ICG) |
| Write granularity | per address (whole row) | per datum (19 bits) |
| Read latency | 1 cycle (registered output) | 0 cycles (combinational) |
| Simultaneous readers | 1–2 | unlimited (wires) |
| Area | compact (bit-cell) | larger (standard cells + ICG per datum) |
| `transpose_write` support | no | yes |
| `strided_write` support | no | yes |
| `zero_out` per-datum | no | yes |
| Low-power idle | SRAM power gating | ICG gates hold state at zero dynamic |

**Why latches beat flops here:**

Flops also support per-datum write-enables (via clock-enable), but each flop requires:
- A D flip-flop (≈ 2× the area of a latch)
- An AND gate for CE (or an integrated CE flop)

For 4,096 × 19 bits = 77,824 storage bits, the area savings of latches + ICG vs. CE-flops is significant in silicon area. Additionally, the two-phase latch timing naturally fits the existing pipeline where the FPU accumulation writes during the HIGH phase and the packer can read combinationally during either phase.

---

## 10. Stochastic Rounding & PRNG

**Files:** `tt_t6_com_prng.sv`, `tt_t6_com_stoch_rnd.sv`, `tt_t6_com_stoch_rnd_w_prng.sv`

### Stochastic Rounding Block Diagram

```
 Per-column seed management:
 ┌────────────────────────────────────────────────────────────┐
 │  tt_t6_com_prng_seeder                                     │
 │  global_seed XOR col_index → per-column seed              │
 │  ensures statistically independent columns                 │
 └──────────────┬─────────────────────────────────────────────┘
                │ seed[31:0] (one per column)
                ▼
 ┌────────────────────────────────────────────────────────────┐
 │  tt_t6_com_prng  (one per FPU column)                      │
 │                                                            │
 │  curr_lfsr ──► next_lfsr = LFSR_POLY(curr_lfsr)           │
 │                                                            │
 │  o_rand[31:0] = next_lfsr  (combinational, zero latency)  │
 │  registered on i_next pulse                                │
 └──────────────┬─────────────────────────────────────────────┘
                │ rand[31:0]
                ▼  (also called stoch_rnd_mask)
 ┌────────────────────────────────────────────────────────────┐
 │  tt_t6_com_stoch_rnd  (at FP Lane output stage)            │
 │                                                            │
 │  Input: result_man[29:0]  (full-precision mantissa)        │
 │         result_exp[8:0]                                    │
 │         target format (EXP_WIDTH, MAN_WIDTH)               │
 │                                                            │
 │  Step 1: determine truncation boundary                     │
 │     lsb_pos = (IN_MAN_WIDTH - OUT_MAN_WIDTH)               │
 │                                                            │
 │  Step 2: extract guard/sticky bits                         │
 │     G = result_man[lsb_pos]       (first dropped bit)     │
 │     T = |result_man[lsb_pos-1:0]  (any remaining bits)    │
 │     L = result_man[lsb_pos+1]     (LSB of kept part)      │
 │                                                            │
 │  Step 3: rounding mode select                              │
 │     RNTE: round_up = G & (T | L)      (IEEE tie-to-even)  │
 │     RTZ:  round_up = 0                (truncate)          │
 │     SRND: round_up = ({G,T} > rand[STOCH_WIDTH-1:0])      │
 │                                                            │
 │  Step 4: add round_up to truncated mantissa                │
 │  Step 5: handle mantissa overflow (increment exponent)     │
 │  Step 6: flush subnormals if FLUSH_SUBNORMS=1              │
 │                                                            │
 │  Output: rounded value in target format                    │
 └────────────────────────────────────────────────────────────┘
```

### PRNG (`tt_t6_com_prng`)

32-bit Galois LFSR:

| Parameter | Value | Description |
|---|---|---|
| `NUM_LFSR_BITS` | 32 | Register width |
| `ENABLE_SEED_CHECKS` | 1 | Simulation check for degenerate seeds |

The LFSR advances one step per `i_next` pulse using the polynomial in `lfsr_function.vh`. Output `o_rand[31:0]` is the **next state** (combinationally derived from current state), ensuring zero-latency output.

**Seeding (`tt_t6_com_prng_seeder`):** Each FPU column receives a distinct seed derived from a global seed XORed with the column index. This ensures column-independent random sequences — otherwise all 16 columns would make the same rounding decisions, producing systematic quantization error rather than random noise.

### Stochastic Rounding (`tt_t6_com_stoch_rnd`)

| Parameter | Value |
|---|---|
| `EXP_WIDTH` | 5 (FP16A) or 8 (FP32/BF16) |
| `MAN_WIDTH` | 10 (FP16) or 23 (FP32) |
| `IN_MAN_WIDTH` | 30 (accumulator width) |
| `STOCH_WIDTH` | 32 (PRNG bits) |
| `FLUSH_SUBNORMS` | 1 (flush subnormals to zero by default) |

**Rounding algorithm:**
1. Extract truncation residual: `R = in_man[(IN_MAN_WIDTH-1):(IN_MAN_WIDTH-STOCH_WIDTH)]`
2. Compare with PRNG sample: `round_up = (R > prng_mask[STOCH_WIDTH-1:0])`
3. Increment mantissa if `round_up`

This is equivalent to adding a uniform random variable `U ∈ [0, 1 ULP)` before truncation — the standard stochastic rounding formulation. The expected value is preserved exactly.

**Why stochastic rounding matters for training:**
- Standard round-to-nearest creates accumulation bias when many weight updates are smaller than 1 ULP of FP16.
- Stochastic rounding ensures that `E[round(x)] = x`, so tiny gradients accumulate correctly over many steps.
- This allows FP16B training to converge where standard RNE rounding diverges.

**Supported rounding modes:**

| Signal | Mode | Use Case |
|---|---|---|
| `i_rnte` | Round-to-nearest ties-to-even | IEEE default inference |
| `i_rtz` | Round toward zero (truncate) | Fast, deterministic |
| PRNG mask active | Stochastic | Low-precision training |
| `i_prec1/2/3` | Reduced precision | Mixed-precision experiments |
| `i_mxint_format` | MXINT-specific saturation | MXINT8 packing |

---

## 11. Element-to-MX Format Converter

**File:** `tensix/rtl/tt_t6_com_elem_to_mx_convert.sv`

This module converts a block of `MX_BLOCK_SIZE` elements from FP32/INT32 to a Microscaling (MX) shared-exponent format.

### Architecture

```
Input: MX_BLOCK_SIZE × FP32 (or INT32)
    │
    ├─ tt_t6_com_stoch_rnd_w_prng × MX_BLOCK_SIZE  (per-datum stochastic rounding)
    │
    ├─ Exponent tree (4-way max × 4 levels → max_exp, min_exp)
    │      o_mx_block_exp = max_exp
    │
    ├─ Mantissa scale: each mantissa right-shifted by (max_exp - datum_exp)
    │
    └─ Output: MX_BLOCK_SIZE × scaled_mantissa + shared block exponent
```

**Exponent tree:**
- `parallel_max_exp4()` — 4-input max via two 2-input comparators in parallel
- 4 levels handle up to `MX_BLOCK_SIZE = 16` elements
- Also computes `min_exp` to check for underflow risk

**Special value handling:**
- `i_inf[i]` → block exponent not dominated by INF datum (configurable via `i_sat_to_inf_mode`)
- `i_nan[i]` → propagated to output datum as quiet NaN
- `i_in_sat` → clamp output to representable range
- `i_mx_block_exp_rnd_to_inf` → if block exponent overflows target format, output INF

**Output formats supported:**
- `MXFP4` (E2M1): block_exp + 1 mantissa bit per element
- `MXFP6` (E3M2 or E2M3): block_exp + 2–3 mantissa bits
- `MXFP8` (E4M3 or E5M2): block_exp + 3–4 mantissa bits
- `MXINT8`: block_exp + 7-bit integer mantissa

**`INT_DESCALE`:** For INT32 inputs (post-INT8 matrix multiply result), `i_int32_descale[i][4:0]` provides a per-datum right-shift amount to normalize INT32 → target range before MX conversion. This avoids a separate TRISC descale loop.

**SW usage:** Called from the packer path when `PACK_OUT_FORMAT ∈ {MXFP4, MXFP6, MXFP8, MXINT8}`. Software sets the target format in `THCON_PACKER0.OUT_DATA_FORMAT` and enables `STOCH_RND_EN=1` for training. The hardware handles the entire block-exponent computation and per-datum mantissa scaling transparently.

---

## 12. Power Management

### 12.0 Power Management Block Diagram

```
  Voltage sensors (×8)           Clock gating controls
       │                                │
  ┌────▼────────────────────┐   ┌───────▼────────────────────────────┐
  │ tt_droop_trigger_       │   │  tt_tensix                          │
  │ detector                │   │  o_cg_retmux_en ──► retmux CG cell │
  │                         │   │  o_cg_l1bank_en ──► L1 bank CG     │
  │ 8 trigger inputs        │   │  i_fpu_gtile_kick[3:0] ◄── power   │
  │ debounce counter        │   │    re-enable per G-Tile             │
  │ 5-state FSM per trigger │   └────────────────────────────────────┘
  │                         │
  │ o_droop_code[2:0] ──────┼──────────────────────────────────────►
  │ o_droop_ready      ─────┼──────┐
  │ o_voltage_droop_mask ───┼──►  │  stall new FPU issues immediately
  └─────────────────────────┘     │
                                  ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │                  tt_power_ramp_fsm                                │
  │                                                                   │
  │  i_droop_code ──► adjust ramp parameters                         │
  │  i_fp_lane_op_available ── FPU instruction in flight              │
  │  i_op_stalled ── current op stalled                              │
  │                                                                   │
  │  7-state FSM:                                                     │
  │                                                                   │
  │  IDLE ──(kick)──► RAMPUP_DELAY ──(delay)──► RAMPUP               │
  │                                                 │                 │
  │                                         enable 1 ballast/cycle   │
  │                                         (HIP rotation order)     │
  │                                                 │                 │
  │                                              ACTIVE ◄──────────  │
  │                                                 │                 │
  │                               ┌────────────────►│                 │
  │                               │         PERMISSIBLE_             │
  │                               │         ACTIVITY_GAP             │
  │                               │                │                 │
  │                    (gap expires)        RAMPDOWN_DELAY            │
  │                               │                │                 │
  │  IDLE ◄──(done)─── RAMPDOWN ◄──────────────────┘                │
  │                   disable ballasts                                │
  │                   at rampdown_rate_4i4f                           │
  │                                                                   │
  │  Outputs:                                                         │
  │  o_stall_fpu_inst ──► block new FPU issues during ramp           │
  │  o_send_dummy     ──► inject zero ops to maintain switching       │
  │  o_dummy_fp_col_en[15:0] ──► which columns get dummy ops         │
  │  o_dummy_fidelity_counter[1:0] ──► fraction of dummy rate        │
  └───────────────────────────────────────────────────────────────────┘

  Ballast column enable pattern (HIP rotation, 16 columns):
  Step 0: enable col  0  (1/16 power)
  Step 1: enable col  8  (2/16 power — opposite hemisphere)
  Step 2: enable col  4  (3/16 power)
  Step 3: enable col 12  (4/16 power)
  ...
  Step 15: all 16 columns active (16/16 = full power)
```

### 12.1 Droop Trigger Detector (`tt_droop_trigger_detector`)

**File:** `instrn_path/rtl/tt_droop_trigger_detector.sv`

Detects voltage droop events from 8 independent hardware droop sensors.

| Parameter | Value | Description |
|---|---|---|
| `NO_OF_TRIG` | 8 | Number of droop trigger inputs |
| `CONSECUTIVE_COUNTER_WIDTH` | 12 | Debounce counter width |
| `MIN_HOLD_VALUE` | 4 | Minimum hold cycles |

**5-state FSM per trigger:**

| State | Transition | Action |
|---|---|---|
| `IDLE` | `droop_trigger` asserted | → ACTIVE_HIGH |
| `ACTIVE_HIGH` | Hold for `droop_trigger_hold` cycles | Assert droop response |
| `HOLD_HIGH` | Counter expires | → ACTIVE_LOW or IDLE |
| `ACTIVE_LOW` | Recovery | Deassert response |
| `HOLD_LOW` | Minimum recovery hold | → IDLE |

**Output `o_droop_code[2:0]`:** Encodes the severity level (0 = nominal, 7 = maximum droop). The droop code is consumed by the power ramp FSM to select the appropriate throttle response.

**`o_voltage_droop_mask`:** When asserted, blocks new FPU instructions from issuing, immediately throttling power consumption without waiting for a full FSM state transition.

**Debounce:** `i_droop_consc_trigger_disable[11:0]` programs a consecutive-trigger disqualification window. If two triggers arrive within this window, the second is ignored (prevents oscillation-induced false triggers at low voltage).

---

### 12.2 Power Ramp FSM & Ballasting (`tt_power_ramp_fsm`)

**File:** `instrn_path/rtl/tt_power_ramp_fsm.sv`

Controls FPU power envelope during ramp-up and ramp-down transitions. The FPU draws peak power instantaneously (all 256 multipliers switching simultaneously), causing di/dt spikes that can trigger droop detectors. The power ramp FSM prevents this.

| Parameter | Value | Description |
|---|---|---|
| `NUM_BALLASTS` | 7 | Number of ballast (power-shaping) units |
| `DISABLE_HIP_ROTATION` | 0 | Enable hardware column rotation |

**7-state FSM:**

| State | Action |
|---|---|
| `IDLE` | No active compute; minimal power |
| `RAMPUP_DELAY` | Wait `rampup_delay_cycles` after first instruction |
| `RAMPUP` | Incrementally enable FPU columns at `rampup_rate_4i4f` per cycle |
| `ACTIVE` | Full compute throughput; monitor for gaps |
| `PERMISSIBLE_ACTIVITY_GAP` | Short idle allowed before rampdown (hysteresis) |
| `RAMPDOWN_DELAY` | Wait `rampdown_delay_cycles` before power reduction |
| `RAMPDOWN` | Gradually disable FPU columns at `rampdown_rate_4i4f` rate |

**Ballasting:** When transitioning from a lower-power state to `ACTIVE`, instead of all 16 FP Lanes switching simultaneously, the FSM enables columns in groups (ballasts). `o_dummy_fp_col_en[15:0]` enables/disables individual columns. `o_send_dummy` sends a synthetic (all-zero) instruction to keep active columns toggling at a controlled rate during ramp-up.

**HIP rotation (`DISABLE_HIP_ROTATION=0`):** Columns are enabled/disabled in a rotating order (round-robin across the 16 columns) rather than left-to-right. This spreads the switching activity across the PDN inductance network, reducing simultaneous switching noise.

**Rate encoding (4i4f fixed-point):** `rampup_rate_4i4f[7:0]` is a 4-integer + 4-fraction fixed-point number representing columns to enable per cycle (e.g., `0x28` = 2.5 columns/cycle → enables 2 or 3 columns alternately). This allows fractional rates for precise power slope control.

**SW configuration:** The ramp rates and delays are set via CSR registers accessible through the global register space. The power management firmware initializes these during boot based on the current voltage-frequency operating point.

---

## 13. FPU Safety Controller

**File:** `fpu/rtl/tt_fpu_safety_ctrl.sv`

Hardware-assisted in-field self-test for ISO 26262 automotive safety or other functional safety profiles.

| Parameter | Value |
|---|---|
| `COMPARATOR_WIDTH` | 32 |
| `NUM_COMPARATORS` | 8 |
| `SELF_TEST_COUNTER_WIDTH` | 18 |

**4-state FSM:**

| State | Description |
|---|---|
| `FUNC_MODE` | Normal operation — no self-test |
| `DIAG_EQ_0` | Inject all-zero pattern; verify all comparators produce 0 |
| `DIAG_NOT_EQ_0` | Inject known non-zero pattern; verify non-zero output |
| `SELF_TEST_ON` | Continuous: inject LFSR-generated vectors; verify MISR signature |

**Coverage tracking:** In `SELF_TEST_ON`, the 18-bit counter increments each test vector. At `2^18 = 262144` vectors, the self-test declares completion. A CRC/MISR comparison at completion determines pass/fail. The coverage target of 262144 vectors provides >99% fault coverage for stuck-at and transition faults in the 8 comparators.

**Diagnostic patterns:** The DIAG states use deterministic patterns (all-0 and all-1) to verify that the comparator circuits themselves are functional. This guards against the self-test mechanism being faulty (meta-testing).

**Error signaling chain:**
```
FPU safety ctrl → tt_fpu_safety_ctrl.o_safety_err
                → tt_err_aggregate (error code 0x0F)
                → EDC ring node
                → APB/CSR status register
                → Host interrupt
```

**SW usage:** The host safety software schedules self-test runs during idle periods (no inference workload). A typical schedule runs a self-test for 1 ms every 100 ms (1% overhead). The self-test result is readable from the Tensix global CSR space.

---

## 14. Error Aggregation & Reporting

**File:** `tensix/rtl/tt_err_aggregate.sv`

### Error Reporting Diagram

```
 Error Sources (up to 16):
                                         i_err_mask[15:0]
 L1 ECC dbl-bit ──[0]──►┐               (software masking)
 TRISC I-cache ECC──[1]──►│                    │
 TRISC LDM ECC ─── [2]──►│                    ▼
 FPU parity ──────[3]──►│  ┌──────────────────────────────────┐
 SFPU lreg parity─[4]──►│  │      tt_err_aggregate             │
 DEST reg parity ─[5]──►│  │                                  │
 FPU safety ctrl ─[6]──►│  │  i_err_in[15:0]                 │
 Sem overflow ────[7]──►├──►  i_err_code[15:0][15:0]          │
 TDMA timeout ────[8]──►│  │  i_err_data[15:0][31:0]          │
 ...              ─...──►│  │                                  │
                         │  │  tt_t6_com_rr_arb               │
                         │  │  (round-robin priority,          │
                         │  │   prevents starvation)           │
                         │  │                                  │
                         │  │  o_err_valid                     │
                         │  │  o_err_code[15:0]   ─────────────┼──► EDC ring node
                         │  │  o_err_data[31:0]   ─────────────┼──► (error info)
                         │  └──────────────────────────────────┘
                                        │
                               ┌────────▼────────┐
                               │  EDC ring       │
                               │  (Section M1)   │──► APB/CSR
                               └─────────────────┘    Host interrupt
```

Central error collection point for all Tensix tile error sources.

| Parameter | Value |
|---|---|
| `ERR_NUM` | 16 error inputs |
| `ERR_CODE_W` | 16 bits per error code |

**Error sources (typical assignments):**

| Error ID | Source | Error Code |
|---|---|---|
| 0 | L1 ECC double-bit error | 0x0001 + address |
| 1 | TRISC I-cache ECC error | 0x0002 + PC |
| 2 | TRISC LDM ECC error | 0x0003 + address |
| 3 | FPU parity error | 0x0004 + G-Tile ID |
| 4 | SFPU local reg parity | 0x0005 |
| 5 | Dest reg parity | 0x0006 + row |
| 6 | FPU safety controller | 0x000F |
| 7 | Semaphore overflow | 0x0010 + SEM ID |
| 8–15 | TDMA timeout / address violation | 0x0020+ |

**Priority arbitration:** `tt_t6_com_rr_arb` round-robins across all 16 error inputs so that a continuously-asserting low-priority error does not block a high-priority error from being reported.

**Error masking:** `i_err_mask[15:0]` allows software to suppress known-benign errors (e.g., mask ECC single-bit correctable errors during burn-in testing). Masked errors do not propagate to the EDC ring.

---

## 15. CSR / Register Space

### CSR Access Path Diagram

```
 Host (NoC APB)                          TRISC threads (MMIO)
       │                                        │
       ▼                                        ▼
 ┌──────────────────────┐             ┌──────────────────────┐
 │  tt_t6_global_regs   │             │  tt_t6_local_regs    │
 │  (host-visible CSR)  │             │  (per-thread MMIO)   │
 │  semaphores          │             │  debug, PIC          │
 │  NOC_overlay regs    │             │  LDM region          │
 │  EDC regs            │             │  L1 client regs      │
 └──────────┬───────────┘             └──────────┬───────────┘
            │                                     │
            └──────────────┬──────────────────────┘
                           │
            ┌──────────────▼──────────────────────────────────┐
            │             tt_t6_csr_arbiter                    │
            │  2 clients → 1 downstream bus                   │
            │  FIFO depth 8, RR arbitration                   │
            │  200-cycle timeout → error if no ack            │
            └──────────────┬──────────────────────────────────┘
                           │
         ┌─────────────────┼──────────────────────────────┐
         │                 │                              │
         ▼                 ▼                              ▼
  ALU cfg regs      THCON cfg regs               MOP cfg regs
  (format,rnd,      (TDMA unpacker/packer         (loop count,
   acc_ctrl)         address/stride/format)        inner instns,
                                                   zmask)

 tt_t6_csr_repeater: bridges CSR signals across ai_clk ↔ noc_clk domains
```

### Semaphore / Synchronization Connection

```
 TRISC0 ──► SFPPOST (sem_id=1) ──► tt_cluster_sync
                                        │
              sem[1].val++              │
                                        ├── sem[1].val > 0 ──► TRISC1 unblocks
                                        │
 TRISC1 ──► SFPGET  (sem_id=1) ──► tt_cluster_sync
              sem[1].val--              │
                                        │
 TRISC1 ──► SFPPOST (sem_id=2) ──► tt_cluster_sync
              sem[2].val++              │
                                        ├── sem[2].val > 0 ──► TRISC2 unblocks
 TRISC2 ──► SFPGET  (sem_id=2) ──► tt_cluster_sync

 Hardware implementation (tt_cluster_sync_semaphore):
 ┌───────────────────────────────────────────────────────────┐
 │  sem_val[15:0]  ← init value from host                   │
 │                                                           │
 │  GET:  if val > 0 → val--; grant                         │
 │        if val = 0 → stall TRISC (no grant)               │
 │                                                           │
 │  POST: val++ (saturating at 2^16-1)                       │
 │        overflow → tt_err_aggregate error                 │
 │                                                           │
 │  INIT: val = write_data (reset for next kernel)          │
 └───────────────────────────────────────────────────────────┘
```

### Address Map

**Global register space** (accessible via NoC APB — host visible):

| Range | Module | Description |
|---|---|---|
| `0x00000000–0x000007FF` | Semaphore regs | 2 KB — 32 semaphores × 64 bytes |
| `0x00001000–0x00001FFF` | NOC overlay regs | 4 KB — NoC endpoint and routing config |
| `0x00002000–0x00002FFF` | EDC regs | 4 KB — EDC ring node CSRs |

**Local register space** (TRISC MMIO — per-thread, not host visible):

| Range | Module | Description |
|---|---|---|
| `0x00000000–0x000002AB` | Debug regs | Per-thread debug state |
| `0x00000400–0x000007FF` | PIC regs | Programmable interrupt controller |
| `0x00002000–0x00008000` | LDM (per RISC) | Local data memory (4 KB each, 4 threads) |
| `0x0000A000–0x0000A05B` | L1 client regs | L1 arbiter config per client |

**Configuration registers** (TRISC MMIO, TDMA):

| Register Group | Base | Size | Description |
|---|---|---|---|
| `ALU_FORMAT_SPEC_REG` | 0x1E0 | 4B | SRCA/SRCB/Dstacc format |
| `ALU_ACC_CTRL` | 0x1E4 | 4B | FP32/INT8 mode, zero-flag control |
| `ALU_ROUNDING_MODE` | 0x1E8 | 4B | Stochastic rounding enable |
| `DEST_REGW_BASE` | 0x1F0 | 4B | Destination write base row |
| `DEST_SP_BASE` | 0x1F4 | 4B | Secondary (ping-pong) base row |
| `THCON_UNPACKER0_0..17` | 0x200–0x24C | 72B | Unpacker 0 configuration |
| `THCON_UNPACKER1_0..17` | 0x250–0x29C | 72B | Unpacker 1 configuration |
| `THCON_PACKER0_0..15` | 0x300–0x33C | 64B | Packer 0 configuration |
| `THCON_PACKER1_0..15` | 0x340–0x37C | 64B | Packer 1 configuration |
| `THCON_MOVER_*` | 0x380–0x38C | 16B | Data mover configuration |
| `MOP_CFG_*` | 0x400–0x4FF | 256B | MOP loop configuration (A bank) |
| `MOP_CFG_*` | 0x500–0x5FF | 256B | MOP loop configuration (B bank) |

**CSR arbiter (`tt_t6_csr_arbiter`):** Serializes 2+ clients (TRISC × 2 threads) into a single downstream CSR bus. FIFO depth 8, round-robin with 200-cycle timeout. Timeout fires an error interrupt if a transaction is not acknowledged within 200 cycles (indicates a missing or hung hardware block).

---

## 16. Numeric Format Reference

**File:** `tt_tensix_common/rtl/fpu_formats_pkg.sv`

### Floating-Point Formats

| Code | Name | S | Exp bits | Man bits | Total | Bias | Use Case |
|---|---|---|---|---|---|---|---|
| 4'h0 | FP32 | 1 | 8 | 23 | 32 | 127 | Training, reference |
| 4'h4 | TF32 | 1 | 8 | 10 | 19 | 127 | NVIDIA TF32 compat |
| 4'h5 | FP16B / BF16 | 1 | 8 | 7 | 16 | 127 | Mixed-precision training |
| 4'h1 | FP16A / FP16 | 1 | 5 | 10 | 16 | 15 | Standard half-float |
| 4'h2 | FP7\_5 | 1 | 5 | 7 | 13 | 15 | Reduced precision |
| 4'ha | FP2\_5 | 1 | 5 | 2 | 8 | 15 | Ultra-low precision |
| — | FP8 (E4M3) | 1 | 4 | 3 | 8 | 7 | Inference, training |
| — | FP8 (E5M2) | 1 | 5 | 2 | 8 | 15 | Wide-range FP8 |
| — | MXFP4 (E2M1) | 1 | 2 | 1 | 4 | 1 | Extreme compression |
| — | MXFP6 (E3M2) | 1 | 3 | 2 | 6 | 3 | Balanced FP6 |

### Block Floating-Point Formats

| Code | Name | Block Size | Man bits | Exp | Storage Overhead |
|---|---|---|---|---|---|
| 4'h3 | BFP4\_7\_5 | 4 elem | 7 | 5 | +1 byte per 4 elems |
| 4'h6 | BFP\_7\_8 | 8 elem | 7 | 8 | +1 byte per 8 elems |
| 4'h7 | BFP4\_7\_8 | 4 elem | 7 | 8 | +1 byte per 4 elems |
| 4'hb | BFP2\_7\_5 | 2 elem | 7 | 5 | +1 byte per 2 elems |
| 4'hf | BFP2\_7\_8 | 2 elem | 7 | 8 | +1 byte per 2 elems |

In BFP, the shared exponent is stored in the L1 exponent section. The mantissa section stores 7-bit values. The effective precision is 7 mantissa bits for all elements in the block, but the dynamic range equals that of the format's exponent width.

### Integer Formats

| Code | Name | Bits | Signed | Use Case |
|---|---|---|---|---|
| 4'h8 | INT32 | 32 | Yes | Accumulator for INT8 GEMM |
| 4'h9 | INT16 | 16 | Yes | Intermediate precision |
| 4'he | INT8 | 8 | Yes | Inference (quantized) |
| — | UINT8 | 8 | No | `srca_unsigned=1` mode |
| — | MXINT8 | 8+exp | Signed | Microscaling INT8 |
| — | MXINT4 | 4+exp | Signed | Extreme quantization |

### FPU Internal Format

All formats are converted to the FPU extended internal representation before entering the MAC array:

```
[18:18] Sign (1 bit)
[17:10] Extended exponent (8 bits, bias=127)
[9:0]   Extended mantissa (10 bits, no hidden bit)
```

This 19-bit extended format can represent FP16A, FP16B, TF32, and BF16 natively without precision loss in the MAC unit.

---

## 17. Clock & Reset Structure

### Clock Domains

| Clock | Domain | Tiles/Modules | Freq |
|---|---|---|---|
| `i_ai_clk` | AI compute | All FPU, SFPU, TRISC, TDMA, L1 | Highest |
| `i_noc_clk` | NoC mesh | NoC endpoint, overlay | Lower |
| `i_dm_clk` | DM complex | Dispatch engine (outside tile) | Medium |

All tile-internal logic runs on `i_ai_clk`. The NoC endpoint inside `tt_tensix_with_l1` runs on `i_noc_clk`, with FIFOs providing CDC at the L1 ↔ NoC boundary.

### Reset Hierarchy

| Reset Signal | Scope | Assertion Condition |
|---|---|---|
| `i_core_reset_n[N]` | Individual TRISC | Kernel exception recovery, per-thread restart |
| `i_uncore_reset_n` | L1 control, TDMA, FPU | Tile-level warm reset (preserves L1 data) |
| `i_nocclk_reset_n` | NoC endpoint | NoC reconfiguration |
| `tensix_reset_n` | Full tile (from trinity.sv) | Harvest bypass or cold boot |

**Per-TRISC reset** allows individual thread restart without affecting:
- L1 contents (data preserved)
- FPU in-progress operations (may complete or be abandoned depending on uncore state)
- Other TRISC threads

**`tensix_reset_n` (harvest):** Driven from `trinity.sv` based on the harvest fuse map. A harvested tile receives `tensix_reset_n=0` continuously, keeping the tile in reset and preventing L1 access from causing indeterminate values on shared buses. See Harvest HDD (M5) for full details.

---

## 18. Key Parameters Summary

| Parameter | Value | Source | Impact |
|---|---|---|---|
| `FP_TILE_COLS` | 16 | `tt_tensix_pkg.sv` | Matrix width per compute cycle |
| `NUM_GTILES` | 4 | `tt_tensix.sv` | G-Tiles per core |
| `FP_TILE_MMUL_ROWS` | 2 | Package | Rows per M-Tile lane group |
| `MULT_PAIRS` | 8 | `tt_fpu_tile.sv` | Products accumulated per lane per cycle |
| `EXT_MAN_WIDTH` | 10 | Package | Internal mantissa bits |
| `EXT_EXP_WIDTH` | 8 | Package | Internal exponent bits |
| `DEST_NUM_ROWS_16B` | 1024 | Package | FP16 destination rows total |
| `DEST_ADDR_WIDTH` | 10 | Package | Destination address bits |
| `SRCS_NUM_ROWS_16B` | 48 | Package | SRCA/SRCB register rows |
| `NUM_TILE_COUNTERS` | 32 | Package | Hardware tile loop counters |
| `TILE_COUNTER_WIDTH` | 16 | Package | Loop count max = 65535 |
| `THREAD_COUNT (TDMA)` | 4 | `tt_tdma.sv` | DMA thread contexts |
| `UNPACK_COUNT` | 2 | TDMA | Simultaneous unpacker channels |
| `PACK_COUNT` | 2 | TDMA | Simultaneous packer channels |
| `LOCAL_MEM_SIZE_BYTES` | 4096 | `tt_trisc.sv` | TRISC private SRAM |
| `DMEM_ECC_ENABLE` | 1 | TRISC | SECDED on local data memory |
| `SEM_COUNT` | 32 | TRISC | Total hardware semaphores |
| `MAILBOX_COUNT` | 4 | TRISC | Cross-tile mailboxes |
| `L1 bus width` | 128 bits | `tt_t6_l1` | 16 bytes per L1 transaction |
| `L1 bank count` | 16 | `tt_t6_l1_arb` | Max concurrent clients |
| `PRNG_WIDTH` | 32 | Common | Stochastic rounding bits |
| `MX_BLOCK_SIZE` | 16 | `elem_to_mx` | MX block for shared exponent |
| `NO_OF_TRIG` | 8 | `droop_detector` | Voltage sensors |
| `NUM_BALLASTS` | 7 | `power_ramp_fsm` | Power-shaping units |
| `SFPU_ROWS` | 4 | `tt_sfpu.sv` | Rows per SFPU instruction |
| `NUM_REGS (SFPU)` | 4 | `tt_sfpu_lregs` | SFPU local register count |
| `LREG_WIDTH` | 32 | SFPU | Local register precision |

---

## 19. Software Usage Guide

This section describes how the software stack (kernel firmware + compiler) programs each hardware unit.

### 19.1 Kernel Execution Model

A Tensix kernel is a triple of programs: `(brisc_program, trisc0_program, trisc1_program, trisc2_program)`. Each program binary is loaded into the respective TRISC I-cache via the dispatch engine before execution begins.

**Startup sequence:**
1. Dispatch engine (from row 1 of the grid) writes kernel binaries to L1 via the NoC.
2. Host sets `DEST_REGW_BASE`, `DEST_SP_BASE`, mesh config in global registers.
3. Host releases `tensix_reset_n` → all 4 threads start executing from their reset PCs.
4. BRISC loads tensor descriptors from a mailbox written by the dispatch engine.
5. The 4 threads run concurrently, synchronized via semaphores.

### 19.2 Tensor Format Programming

Before the compute loop, TRISC0 and TRISC2 configure the TDMA format:

```c
// TRISC0: configure unpacker for BF16 input
wrcfg(THCON_UNPACKER0_0, {
    .OUT_DATA_FORMAT = FP16B,    // BFloat16
    .TILIZE_SRC_ADDR_OFFSET = l1_base_addr,
    .TRANSPOSE = 0,
    .ENABLE_ARG_FIFO = 1
});
wrcfg(THCON_UNPACKER0_4, {       // stride registers
    .SRC_Z_STRIDE = K * C * sizeof(bf16),
    .DST_Z_STRIDE = 1
});

// TRISC1: configure math format
wrcfg(ALU_FORMAT_SPEC_REG, {
    .SrcA_val_format = FP16B,
    .SrcB_val_format = FP16B,
    .Dstacc = FP16B
});
wrcfg(ALU_ACC_CTRL, {.Fp32_enabled = 0, .INT8 = 0});
wrcfg(ALU_ROUNDING_MODE, {.Fpu_srnd_en = 1});

// TRISC2: configure packer for FP8 output
wrcfg(THCON_PACKER0_0, {
    .IN_DATA_FORMAT  = FP16B,
    .OUT_DATA_FORMAT = FP8_E4M3,
    .STOCH_RND_EN = 1,
    .EXP_THRESHOLD_EN = 1, .EXP_THRESHOLD_VAL = -8  // prune tiny values
});
```

### 19.3 MOP Programming

The innermost GEMM loop is programmed as a MOP:

```c
// TRISC1: program MOP config for MVMUL loop
wrcfg(MOP_CFG_LOOP0_LEN, K_tiles - 1);    // K/tile_K iterations
wrcfg(MOP_CFG_LOOP1_LEN, M_tiles - 1);    // M/tile_M iterations
wrcfg(MOP_CFG_LOOP_START_INSTRN0, MVMUL_instrn({
    .dstacc_idx = DEST_REGW_BASE,
    .mode = FPU_PRIM_MVMUL,
    .accum_en = 1
}));
wrcfg(MOP_CFG_LOOP_END_INSTRN0, MVMUL_instrn({...}));  // last row

// Execute: hardware loop runs K_tiles × M_tiles iterations
issue_instrn(MOP);
```

### 19.4 SFPU Activation Programming

After math MOP completes, TRISC1 issues SFPU instructions:

```c
// Apply ReLU (simple case — use packer hardware ReLU instead of SFPU for speed)
wrcfg(THCON_PACKER0_3, {.RELU_MODE = 1});  // zero-negative mode

// Apply GELU (requires SFPU):
for (row_batch = 0; row_batch < 256; row_batch++) {   // 256 × 4 = 1024 rows
    issue_instrn(SFPLOAD, {.lreg = 0, .dest_row = row_batch * 4});
    issue_instrn(SFPMAD,  {.d=1, .a=0, .b=0, .c=LREG_CONST_0});  // x^2
    issue_instrn(SFPMAD,  {.d=1, .a=1, .b=0, .c=LREG_CONST_0});  // x^3
    issue_instrn(SFPMAD,  {.d=1, .a=1, .b=COEFF_0044715, .c=0}); // 0.044715*x^3
    issue_instrn(SFPMAD,  {.d=1, .a=1, .b=SQRT2PI, .c=0});        // scale
    // ... 4 more MADs for tanh polynomial ...
    issue_instrn(SFPMAD,  {.d=0, .a=0, .b=0_5, .c=1}); // 0.5*x*(1+tanh)
    issue_instrn(SFPSTORE, {.lreg = 0, .dest_row = row_batch * 4});
}
```

### 19.5 Double-Buffer Orchestration

```c
// TRISC1 (math thread):
while (tiles_remaining > 0) {
    sem_wait(SEM_TRISC0_DONE);        // wait for TRISC0 to fill SRCA/SRCB
    issue_mop(MVMUL, loop_count);     // compute into buffer A
    sem_post(SEM_TRISC1_DONE);        // signal TRISC2 to pack buffer A
    swap_dest_buffers();              // point to buffer B for next tile
    tiles_remaining--;
}

// TRISC2 (pack thread):
while (tiles_packed < total_tiles) {
    sem_wait(SEM_TRISC1_DONE);        // wait for math to complete
    issue_mop(PACR, pack_count);      // pack buffer A to L1
    sem_post(SEM_PACK_DONE);          // signal BRISC to drain L1
    tiles_packed++;
}

// BRISC:
for each tile:
    sem_wait(SEM_PACK_DONE);          // wait for packed data in L1
    noc_write(remote_addr, l1_packed_base, tile_size);  // send to next tile
    sem_post(SEM_BRISC_DONE);
```

### 19.6 Sparsity (Zmask) Programming

For sparse tensor operations where some Z-planes are zero:

```c
// TRISC0: set zmask based on sparsity metadata
uint64_t zmask = compute_zmask(activation_sparsity_map, z_start, z_count);
wrcfg(MOP_CFG_ZMASK_HI, zmask >> 32);
wrcfg(MOP_CFG_ZMASK_LO, zmask & 0xFFFFFFFF);
// Hardware unpack loop now skips zero planes automatically
issue_instrn(MOP, {UNPACR});
```

### 19.7 INT8 Quantized Inference

```c
// Configure for INT8 math
wrcfg(ALU_FORMAT_SPEC_REG, {.SrcA=INT8, .SrcB=INT8, .Dstacc=INT32});
wrcfg(ALU_ACC_CTRL, {.INT8_math_enabled = 1, .Fp32_enabled = 0});

// Configure packer: descale INT32 result → INT8
wrcfg(THCON_PACKER0_2, {
    .INT_DESCALE_ENABLE = 1,
    .INT_DESCALE_MODE = 1,  // right-shift
    .INT_DESCALE_AMOUNT = 8  // >> 8 to scale INT32 → INT8 range
});
wrcfg(THCON_PACKER0_0, {.OUT_DATA_FORMAT = INT8});

// Execute INT8 GEMM
wrcfg(MOP_CFG_LOOP0_LEN, K_tiles - 1);
issue_instrn(MOP, {DOTPV});
```

---

*End of Document — Version 0.3 (2026-03-18)*
