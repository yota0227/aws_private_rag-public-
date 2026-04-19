# Trinity SoC Hardware Design Document v3.0 — N1B0 Edition

**Document:** trinity_HDD_v3.0.md (N1B0)
**Date:** 2026-03-20
**Scope:** N1B0 silicon variant (4×5 grid) — all specifications N1B0-correct
**Source:** Official docs (integration-guide, PD_Ref_Guide, HTML register maps, PDFs) + N1B0_HDD_v0.1 + N1B0_NPU_HDD_v0.1 + N1B0_NOC2AXI_ROUTER_OPT_HDD + n1b0_memory_list + trinity_memory_list + N1B0_DFX_HDD
**Revision history:**
- v3.0 (2026-03-20): Full rebuild from official docs + N1B0 archives; N1B0-verified numbers throughout

**Corrections vs. baseline HDD (v3.0 at DOC/):**
- §2.2 tile_t enum: corrected to N1B0 values (TENSIX=0 … ROUTER=7)
- §7.3 router repeater table: added E=1, N=1 directions
- §10.4 DFX: corrected clock port names and directions per N1B0_DFX_HDD
- §10.5 added: full Tensix hierarchy with DFX insertion depth
- §11.4 SRAM inventory: replaced with exact N1B0 numbers (730/tile, 512 L1 macros, ~9,606 chip total); added physical cell names and clock paths
- §14 delta table: expanded with precise SRAM and hierarchy details

---

## Table of Contents

1. [Trinity Overview](#1-trinity-overview)
2. [Grid Architecture & Tile Map](#2-grid-architecture--tile-map)
3. [Clock & Reset Architecture](#3-clock--reset-architecture)
4. [Tensix NEO Cluster](#4-tensix-neo-cluster)
5. [Dispatch Engine](#5-dispatch-engine)
6. [NoC Fabric & Router](#6-noc-fabric--router)
7. [NoC2AXI Interface (NIU)](#7-noc2axi-interface-niu)
8. [EDC System](#8-edc-system)
9. [Harvest Architecture](#9-harvest-architecture)
10. [Overlay Wrapper, Context Switch & DFX](#10-overlay-wrapper-context-switch--dfx)
11. [Physical Design Notes](#11-physical-design-notes)
12. [Register Maps](#12-register-maps)
13. [Verification & Testbench Infrastructure](#13-verification--testbench-infrastructure)
14. [N1B0 Silicon Variant — Delta from Baseline](#14-n1b0-silicon-variant--delta-from-baseline)
15. [INT16/FP16B/INT8 LLM Mapping Guide](#15-int16fp16bint8-llm-mapping-guide)
16. [Release History & EDA Versions](#16-release-history--eda-versions)

---

## 1. Trinity Overview

Trinity is an AI/ML compute SoC integrating a 2-D mesh of Tensix NEO clusters, data-movement dispatch engines, and NoC2AXI AXI bridge tiles interconnected by a 256-bit bidirectional Network-on-Chip (NoC).

### 1.1 N1B0 Top-Level Block Diagram

```
                       External AXI ports (4× slave + 4× master)
                         ↑↑↑↑↑↑↑↑   ↓↓↓↓↓↓↓↓
 ┌────────────────────────────────────────────────────────────────┐
 │                        TRINITY N1B0                            │
 │                                                                │
 │  Y=4  ┌──────────┬─────────────────────────┬──────────┐       │
 │       │NW_OPT    │   NW_OPT_R   NE_OPT_R   │NE_OPT    │ ←AXI │
 │       │(X=0,Y=4) │   (X=1,Y=4) (X=2,Y=4)  │(X=3,Y=4) │       │
 │       │          │ ╔══════════╗╔══════════╗ │          │       │
 │  Y=3  │          │ ║NW_OPT_R ║║NE_OPT_R  ║ │          │       │
 │       │DISPATCH_W│ ║internal ║║internal  ║ │DISPATCH_E│       │
 │       │(X=0,Y=3) │ ║ROUTER  ║║ROUTER   ║ │(X=3,Y=3) │       │
 │       │          │ ╚══Y=3════╝╚══Y=3════╝ │          │       │
 │  Y=2  ├──────────┼─────────────────────────┼──────────┤       │
 │       │TENSIX    │TENSIX       TENSIX       │TENSIX    │       │
 │  Y=1  ├──────────┼─────────────────────────┼──────────┤       │
 │       │TENSIX    │TENSIX       TENSIX       │TENSIX    │       │
 │  Y=0  ├──────────┼─────────────────────────┼──────────┤       │
 │       │TENSIX    │TENSIX       TENSIX       │TENSIX    │       │
 │       └──────────┴─────────────────────────┴──────────┘       │
 │        X=0          X=1           X=2          X=3             │
 │                                                                │
 │  Clocks: i_axi_clk, i_noc_clk, i_ai_clk[3:0], i_dm_clk[3:0] │
 │  EDC ring: 4 columns × 1 ring each; BIU in each NIU tile      │
 │  PRTN chain: per column Y=2→Y=1→Y=0                           │
 │  ISO_EN[11:0]: harvest isolation (N1B0 6th mechanism)         │
 └────────────────────────────────────────────────────────────────┘

  NW_OPT_R = NOC2AXI_ROUTER_NW_OPT  (composite, spans Y=4 + Y=3)
  NE_OPT_R = NOC2AXI_ROUTER_NE_OPT  (composite, spans Y=4 + Y=3)
```

### 1.2 N1B0 Tile Inventory (4×5 grid, 20 positions)

| Tile Module                       | Count | Grid Position    | trinity.sv gen-block         |
|-----------------------------------|-------|------------------|------------------------------|
| `tt_tensix_with_l1`               | 12    | X=0–3, Y=0–2    | `gen_tensix_neo[x][y]`       |
| `tt_dispatch_top_west`            | 1     | X=0, Y=3        | `gen_dispatch_w`             |
| `tt_dispatch_top_east`            | 1     | X=3, Y=3        | `gen_dispatch_e`             |
| `trinity_noc2axi_nw_opt`          | 1     | X=0, Y=4        | `gen_noc2axi_nw_opt`         |
| `trinity_noc2axi_ne_opt`          | 1     | X=3, Y=4        | `gen_noc2axi_ne_opt`         |
| `trinity_noc2axi_router_nw_opt`   | 1     | X=1, Y=4+Y=3    | `gen_noc2axi_router_nw_opt`  |
| `trinity_noc2axi_router_ne_opt`   | 1     | X=2, Y=4+Y=3    | `gen_noc2axi_router_ne_opt`  |
| Router placeholder (empty)        | 2     | X=1,2 Y=3       | (internal to composites)     |
| `tt_noc_repeaters`                | —     | inter-column     | manual assigns               |
| `tt_edc1_intf_connector`          | —     | ring stitching   | per column                   |

### 1.3 N1B0 Package Constants (trinity_pkg.sv)

| Constant               | Value | Description                            |
|------------------------|-------|----------------------------------------|
| `SizeX`                | 4     | Grid X dimension                       |
| `SizeY`                | 5     | Grid Y dimension                       |
| `NumNodes`             | 20    | Total tile positions                   |
| `NumTensix`            | 12    | Compute tiles                          |
| `NumNoc2Axi`           | 4     | AXI bridge tiles (corners + composites)|
| `NumDispatch`          | 2     | Dispatch tiles                         |
| `NumApbNodes`          | 4     | APB config node columns                |
| `NumDmComplexes`       | 14    | DM CPU complexes (12 Tensix + 2 Disp)  |
| `EnableDynamicRouting` | 1     | Dynamic routing enabled by default     |
| `NOC_DATA_WIDTH`       | 256   | NoC flit width (bits)                  |
| `AXI_DATA_WIDTH`       | 512   | Internal AXI data width                |

---

## 2. Grid Architecture & Tile Map

### 2.1 N1B0 EndpointIndex Table

`EndpointIndex = X × SizeY + Y` (SizeY = 5):

```
         X=0    X=1    X=2    X=3
  Y=4  [  4 ] [  9 ] [ 14 ] [ 19 ]   ← NOC2AXI row
  Y=3  [  3 ] [  8 ] [ 13 ] [ 18 ]   ← Dispatch/Router row
  Y=2  [  2 ] [  7 ] [ 12 ] [ 17 ]   ← Tensix row
  Y=1  [  1 ] [  6 ] [ 11 ] [ 16 ]   ← Tensix row
  Y=0  [  0 ] [  5 ] [ 10 ] [ 15 ]   ← Tensix row

Composite tile occupancy:
  NOC2AXI_ROUTER_NW_OPT (X=1): EP 9 (Y=4, NOC2AXI part) + EP 8 (Y=3, Router part)
  NOC2AXI_ROUTER_NE_OPT (X=2): EP 14 (Y=4, NOC2AXI part) + EP 13 (Y=3, Router part)
  → Router sub-module receives nodeid_y = Y−1, endpoint_id = EP−1 (internal offset)
```

### 2.2 Tile Type Enum (N1B0-correct)

```systemverilog
// From trinity_pkg.sv (N1B0 / used_in_n1)
typedef enum logic [2:0] {
  TILE_TENSIX               = 3'd0,   // X=0..3, Y=0..2
  TILE_NOC2AXI_NE_OPT       = 3'd1,   // X=3, Y=4 (corner east)
  TILE_NOC2AXI_ROUTER_NE_OPT= 3'd2,   // X=2, Y=4+Y=3 (composite east-center)
  TILE_NOC2AXI_ROUTER_NW_OPT= 3'd3,   // X=1, Y=4+Y=3 (composite west-center)
  TILE_NOC2AXI_NW_OPT       = 3'd4,   // X=0, Y=4 (corner west)
  TILE_DISPATCH_E            = 3'd5,   // X=3, Y=3
  TILE_DISPATCH_W            = 3'd6,   // X=0, Y=3
  TILE_ROUTER                = 3'd7    // placeholder — NOT instantiated in N1B0
} tile_t;
```

### 2.3 N1B0 NoC Mesh — X-Axis Repeater Strategy

N1B0 uses **manual wire assigns** (not generate loops) for the X-axis NoC, with explicit repeater stages:

```
X-axis repeater configuration (N1B0):
  Y=4 row: 4 repeater stages between each column pair
             X=0↔X=1: 4-stage; X=1↔X=2: 4-stage; X=2↔X=3: 4-stage
  Y=3 row: 6 repeater stages between each column pair
             X=0↔X=1: 6-stage; X=1↔X=2: 6-stage; X=2↔X=3: 6-stage
  Y=0–2:   direct wire assigns (no inter-column repeaters)

Y-axis (N/S): repeaters embedded within trinity_router parameters
  NUM_REPEATERS_INBOUND_SOUTH  = 5  (Y=3→Y=2 distance)
  NUM_REPEATERS_OUTBOUND_SOUTH = 5
```

---

## 3. Clock & Reset Architecture

### 3.1 Clock Domains

| Clock     | Port (N1B0)         | Freq Range      | Modules                                        |
|-----------|---------------------|-----------------|------------------------------------------------|
| `axi_clk` | `i_axi_clk` (scalar)| 0.75–1.5 GHz   | External AXI slave/master                      |
| `noc_clk` | `i_noc_clk` (scalar)| 1.0–1.5 GHz    | NoC fabric, VC FIFOs, router, Dispatch L1      |
| `ai_clk`  | `i_ai_clk[3:0]`     | 1.0–1.5 GHz    | Tensix FPU, SRCA/SRCB, DEST, L1 SRAM, TRISC   |
| `dm_clk`  | `i_dm_clk[3:0]`     | 1.5–2.2 GHz    | DM CPUs (overlay), FDS FSM, dispatch overlay   |
| `ref_clk` | `i_ref_clk`         | fixed           | EDC ring synchronizer reference, PLL           |
| `aon_clk` | (internal)          | always-on       | AON strip, power-good logic                    |

> **N1B0 key change:** `i_ai_clk` and `i_dm_clk` are **per-column arrays** `[NOC_X_SIZE-1:0]` = `[3:0]`.
> Baseline Trinity uses single scalar inputs.

### 3.2 N1B0 Clock Routing Struct

Each tile-to-tile boundary uses a `trinity_clock_routing_t` struct (9 fields):

```
trinity_clock_routing_t:
  .ai_clk       — compute clock
  .noc_clk      — mesh clock
  .dm_clk       — data-movement CPU clock
  .ai_reset_n   — AI domain reset
  .noc_reset_n  — NoC domain reset
  .dm_reset_n   — DM domain reset
  .edc_reset_n  — EDC ring reset (power-good equivalent)
  .power_good   — tile power status
  .iso_en       — isolation enable (harvest mechanism #6)

Propagation direction: Y decreasing
  clock_routing_in[x][y]  → (tile at x,y) → clock_routing_out[x][y-1]

N1B0 composite tile:
  NOC2AXI_ROUTER_OPT at Y=4 accepts clock_routing_in[x][4]
  drives internal router at Y=3
  exports clock_routing_out[x][3] → Tensix column (Y=2)
```

### 3.3 NOC Clock Hub (v0.8+)

```
i_noc_clk (global)
  → NOC partition (clock hub within each tile)
       ├── Router VC buffers (direct)
       └── o_noc_clk_feedthrough_to_l1  →  L1 partition (abutment, no buffer)
```

### 3.4 Reset Signals

| Reset Signal              | Scope                       | Notes                          |
|---------------------------|----------------------------|--------------------------------|
| `i_noc_reset_n`           | All NoC logic               | Release first                  |
| `i_ai_reset_n`            | L1 + Tensix shared          | Release after NoC stable       |
| `i_edc_reset_n`           | EDC ring                    | Power-good signal equivalent   |
| `i_tensix_reset_n[11:0]`  | Individual Tensix tiles     | bit = 3×col + row              |
| `i_dm_core_reset_n`       | DM CPU core domain          | FDS runtime                    |
| `i_dm_uncore_reset_n`     | DM CPU uncore / bus matrix  |                                |

### 3.5 PRTN Daisy-Chain (N1B0)

N1B0 adds a per-column partition-retention (PRTN) chain, propagating Y=2→Y=1→Y=0:

```
Per column X:
  prtn_in[X][2] → Tensix(X,2) → prtn_out[X][2]
                → prtn_in[X][1] → Tensix(X,1) → prtn_out[X][1]
                → prtn_in[X][0] → Tensix(X,0) → prtn_out[X][0]  (tail)
```

---

## 4. Tensix NEO Cluster

The Tensix NEO cluster is the primary AI/ML compute element. Each tile contains 4 sub-cores (T0–T3) sharing one L1 memory.

### 4.1 Tensix NEO Cluster — Block Diagram

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                    TENSIX NEO CLUSTER (tt_tensix_with_l1)        │
 │                                                                  │
 │  ┌─────────────────────────────────────────────────────────────┐ │
 │  │ OVERLAY (tt_neo_overlay_wrapper)                            │ │
 │  │  8× RISC-V dm_cores  |  Context Switch  |  NoC Copy Cmd    │ │
 │  │  Pattern Addr Gen    |  Local Shuffle   |  SMN security     │ │
 │  └────────────────────────────┬────────────────────────────────┘ │
 │                               │ DM  ←→  Tensix control           │
 │  ┌────────────────────────────▼────────────────────────────────┐ │
 │  │ INSTRUCTION ENGINE (per sub-core T0–T3, 4 instances)        │ │
 │  │  BRISC (kernel init)   TRISC0 (unpack)                      │ │
 │  │  TRISC1 (math/MOP)     TRISC2 (pack)                        │ │
 │  │  MOP Decoder  |  Replay Unit                                 │ │
 │  └──────┬───────────────────────────────────────┬──────────────┘ │
 │         │ SRCA feed             SRCB broadcast  │                │
 │  ┌──────▼──────────────────────────────────────▼──────────────┐  │
 │  │  FPU — G-TILE[0] (M-Tile×8, FP_Lane×8, DEST sub-bank 0..7)│  │
 │  │       G-TILE[1] (M-Tile×8, FP_Lane×8, DEST sub-bank 8..15)│  │
 │  │  SFPU (exp, sqrt, gelu, silu, tanh, clamp …)               │  │
 │  └──────────────────────────────────────────────────────────────┘ │
 │                               │                                   │
 │  ┌────────────────────────────▼────────────────────────────────┐  │
 │  │ TDMA  (Unpack×2: L1→SRCA/SRCB) (Pack×1: DEST→L1)           │  │
 │  └────────────────────────────┬────────────────────────────────┘  │
 │                       512-bit bus                                 │
 │  ┌────────────────────────────▼────────────────────────────────┐  │
 │  │ L1 MEMORY (tt_t6_l1_partition)  — N1B0: 768 KB/tile         │  │
 │  │  16 banks × 3072 rows × 128 bits                            │  │
 │  │  512 physical SRAM macros (u_ln05lpe_*_768x69m4b1c1)       │  │
 │  │  SECDED ECC @ 128-bit granularity; atomic ops               │  │
 │  └──────────────────────────────────────────────────────────────┘ │
 │                               ↕ 256-bit                           │
 │  ┌────────────────────────────▼────────────────────────────────┐  │
 │  │ NoC ROUTER (tt_noc_niu_router, 256-bit flit)                │  │
 │  └──────────────────────────────────────────────────────────────┘ │
 └──────────────────────────────────────────────────────────────────┘
```

### 4.2 Tensix Hierarchy (N1B0, with DFX wrappers)

```
tt_tensix_with_l1
└── tt_overlay_noc_wrap
    └── tt_overlay_noc_niu_router
        ├── tt_noc_niu_router_dfx          ← DFX clock pass-through (N1B0)
        │   └── [NOC/NIU/Router logic]
        └── tt_neo_overlay_wrapper
            └── tt_overlay_wrapper
                ├── tt_overlay_wrapper_dfx  ← DFX clock pass-through (N1B0)
                │   ├── clock_reset_ctrl
                │   ├── cpu_cluster_wrapper (8× RocketTile: BRISC+TRISC0/1/2)
                │   └── memory_wrapper
                │       ├── tt_t6_l1_partition_dfx  ← DFX clock pass-through (N1B0)
                │       │   └── [L1 SRAM banks]
                │       ├── [Overlay L1/L2 caches]
                │       └── [Context switch SRAMs]
                ├── t6_l1_flex_client_port  (×4 T6 cores)
                ├── noc_snoop_tl_master
                └── [per sub-core T0–T3]:
                    └── instrn_engine_wrapper
                        └── tt_instrn_engine_wrapper_dfx  ← DFX (N1B0)
                            └── [TRISC/BRISC, SRCB, SFPU, MOP, Replay]
```

### 4.3 FPU — G-Tile / M-Tile

```
G-Tile (×2 per cluster):
└── M-Tile[0..7]  (8 multiplier tiles)
    └── FP_LANE[0..7]  (8 parallel multiply paths)
        ├── fp_mul_raw   (Booth radix-4 mantissa multiply)
        ├── exp_path     (exponent add + bias correction)
        ├── align        (4-stage barrel shifter, FP16 mode)
        ├── compress     (Wallace 4:2 compressor tree)
        └── add          (carry-propagate adder + stochastic rounding)
        └── feeds DEST sub-bank[tile_index]
    SRCA broadcast bus → all M-Tiles

Total: 2 G-Tiles × 8 M-Tiles × 8 FP_Lanes = 128 parallel multipliers
MACs/cycle: 256–8192 depending on data format (§4.7)
```

### 4.4 Instruction Engine — TRISC/BRISC

Each of the 4 sub-cores (T0–T3) has its own Instruction Engine:

| Core   | Role                   | Notes                                     |
|--------|------------------------|-------------------------------------------|
| BRISC  | Kernel initialization  | RISC-V; sets up TDMA descriptors           |
| TRISC0 | Unpack control         | Programs TDMA unpackers (SrcA/SrcB)        |
| TRISC1 | Math control           | Issues MOP loop commands to FPU            |
| TRISC2 | Pack control           | Programs TDMA packers (DEST→L1)            |

**MOP Decoder:** Expands matrix-op instructions into FPU microop streams (reduces TRISC1 bandwidth).
**Replay Unit:** Repeats FPU sequences without TRISC1 for pipelined tiling.

**TRISC memory map (local RISC-V view):**

| Address Range              | Region                              |
|----------------------------|-------------------------------------|
| `0x0000_0000–0x007F_FFFF`  | L1 shared (8 MB view)              |
| `0x0080_0000–0x0080_03A3`  | TRISC debug registers               |
| `0x0080_0000–0x0080_A0E3`  | Full local register space           |
| `0x0184_0000–0x0184_10FF`  | Global Tensix registers             |

**TRISC debug registers (external NoC access):**

| Address (NoC)              | Region                              |
|----------------------------|-------------------------------------|
| `0x0000_0000–0x007F_FFFF`  | tensix_l1 (8 MB)                   |
| `0x0180_0000–0x0180_03A3`  | neo_regs[0] — sub-core T0          |
| `0x0181_0000–0x0181_03A3`  | neo_regs[1] — sub-core T1          |
| `0x0182_0000–0x0182_03A3`  | neo_regs[2] — sub-core T2          |
| `0x0183_0000–0x0183_03A3`  | neo_regs[3] — sub-core T3          |
| `0x0184_0000–0x0184_10FF`  | tensix_global_regs                 |

Address translation: `external = local_offset + 0x0180_0000 + (T_idx × 0x1_0000)`

### 4.5 TDMA (Tiled DMA)

**Unpackers (×2, SrcA and SrcB):**
- DMA: L1 → SRCA/SRCB register file
- On-the-fly format conversion (INT8→INT16, FP8→FP16, etc.)
- Transpose and bank initialization support

**Packers (×1):**
- DMA: DEST register file → L1
- Format conversion (FP32→FP16, INT32→INT8, etc.)
- Inline activation: ReLU, CReLU

### 4.6 SFPU (Special Function Processing Unit)

Operates on DEST register file elements, vector-style:

- **Transcendentals:** exp, log, sqrt, rsqrt, recip
- **Activations:** gelu, silu, tanh, sigmoid, softmax (partial)
- **Misc:** abs, clamp, LReLU, stochastic dropout
- **INT16 overhead:** +2 L1 round-trips (inv-sqrt + exp subpath)

### 4.7 L1 Memory (N1B0 4× expanded)

| Parameter          | Baseline Trinity | N1B0             |
|--------------------|-----------------|------------------|
| Capacity           | 192 KB/tile     | **768 KB/tile**  |
| Total (12 tiles)   | 2.304 MB        | **9.216 MB**     |
| Banks              | 16              | 16               |
| Bank depth         | 768 rows        | **3072 rows**    |
| Bank width         | 128 bits        | 128 bits         |
| Physical macros    | 128/tile        | **512/tile**     |
| Raw area/tile      | ~828 KB         | **~3,312 KB**    |
| Physical cell      | `u_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1` | same |
| L1 config header   | `tt_mimir_l1_cfg.svh` | `tt_trin_l1_cfg.svh` (BANK_IN_SBANK=16) |
| ECC                | SECDED @ 128-bit | SECDED @ 128-bit |
| Atomic ops         | Yes             | Yes              |
| Address range      | `0x0000_0000–0x002F_FFFF` | `0x0000_0000–0x00BF_FFFF` |

> Raw area (3,312 KB) includes ECC/parity storage. User-visible data capacity = 768 KB.
> Physical macro: 768 words × 69 bits each half (high + low = 128-bit effective width).

**L1 clients (shared by all 4 sub-cores):**

| Client          | Port Width | Clock   | Priority |
|-----------------|-----------|---------|----------|
| TDMA (unpack)   | 256-bit   | AICLK   | High     |
| TDMA (pack)     | 256-bit   | AICLK   | High     |
| NoC write       | 512-bit   | NOCCLK  | Medium   |
| Overlay DM      | 256-bit   | DMCLK   | Low      |
| T6 cores (×4)   | 64-bit    | AICLK   | Low      |

**NoC→L1 write path:** 512-bit; CDC FIFO (8 entries, NOCCLK write / AICLK read); routes on left-edge channel ~82 µm wide (M3+ layers; M1/M2 reserved).

### 4.8 Register Files (DEST / SRCA / SRCB)

**DEST (accumulator latch-array):**

| Mode          | Rows | Element Width | Effective Size |
|---------------|------|---------------|----------------|
| FP32 / INT32  | 512  | 32-bit        | 32 KB          |
| FP16B / FP16A | 1024 | 16-bit (×2/word) | 32 KB       |
| FP8 / INT8    | 1024 | 8-bit (×2/word)  | 16 KB        |

- 12,288 latch-array cells total (all 12 Tensix tiles)
- Double-buffered: G-Tile[0] holds DEST[0..7], G-Tile[1] holds DEST[8..15]

**SRCA:** 2048 rows × 16 cols × 16-bit; double-banked; max K_tile = 48 rows; 1,536 latch-array cells
**SRCB:** same organization as SRCA; shared broadcast to both G-Tiles; in Instruction Engine

### 4.9 Data Formats & MAC Throughput

**Supported formats:**

| Format | Code | Exp | Man | Notes                         |
|--------|------|-----|-----|-------------------------------|
| FP32   | 0x0  | 8   | 23  | IEEE 754 single               |
| FP16A  | 0x1  | 5   | 10  | IEEE half-precision           |
| FP16B  | 0x5  | 8   | 7   | BF16 (recommended)            |
| TF32   | 0x4  | 8   | 10  | TensorFloat-32                |
| FP8R   | 0x2  | 4   | 3   | FP8 round-nearest             |
| FP8P   | 0x3  | 4   | 3   | FP8 round-plus                |
| MXFP8  | —    | —   | —   | Microscaling FP8              |
| INT8   | 0xe  | —   | —   | 8-bit signed                  |
| UINT8  | 0xf  | —   | —   | 8-bit unsigned                |
| INT16  | 0x9  | —   | —   | 16-bit signed                 |
| INT32  | 0x8  | —   | —   | 32-bit accumulator            |
| INT4   | 0xd  | —   | —   | 4-bit (packed)                |

**MAC throughput per Tensix NEO cluster:**

| Data Format       | Hi-Fi (MACs/cycle) | Lo-Fi (MACs/cycle) |
|-------------------|--------------------|--------------------|
| TF32              | 512                | 2048               |
| Float16 (FP16A)   | 512                | 2048               |
| Float16B (BF16)   | **1024**           | 2048               |
| FP8R / FP8P       | 2048               | —                  |
| MXFP8 variants    | 2048               | —                  |
| MXINT variants    | 2048               | —                  |
| INT8 / UINT8      | **8192**           | 8192               |

> Hi-Fi = highest precision; Lo-Fi = reduced-precision throughput mode.

---

## 5. Dispatch Engine

### 5.1 Architecture

Dispatch tiles at X=0 (west) and X=3 (east), Y=3:

```
 ┌─────────────────────────────────────────────────┐
 │             DISPATCH ENGINE                      │
 │  ┌─────────────────────────────────────────┐    │
 │  │ OVERLAY (8× dm_cores, dm_clk domain)   │    │
 │  │   FDS (Fast Dispatch Scheduler FSM)     │    │
 │  └───────────────────┬─────────────────────┘    │
 │  ┌───────────────────▼─────────────────────┐    │
 │  │ L1 Memory (dispatch)                    │    │
 │  │  Clock domain: i_noc_clk (not ai_clk)  │    │
 │  │  128 physical SRAM macros/tile          │    │
 │  │  Same macro type as Tensix L1          │    │
 │  └───────────────────┬─────────────────────┘    │
 │  ┌───────────────────▼─────────────────────┐    │
 │  │ NoC Router (east or west variant)       │    │
 │  │  tt_trin_disp_eng_noc_niu_router_{W/E}  │    │
 │  └─────────────────────────────────────────┘    │
 └─────────────────────────────────────────────────┘
```

### 5.2 Dispatch Feedthrough Channels

| Channel         | Direction             | Description                        |
|-----------------|-----------------------|------------------------------------|
| `de_to_t6[x]`   | Dispatch → Tensix     | Kernel command push                |
| `t6_to_de[x]`   | Tensix → Dispatch     | Completion feedback                |

In N1B0 the `NOC2AXI_ROUTER_OPT` composite tiles carry these feedthroughs internally (east/west pass-through inside Y=4+Y=3 combined module).

### 5.3 Dispatch L1 Clock Domain

Dispatch L1 runs on `i_noc_clk`, NOT `ai_clk`. This requires CDC at the boundary when dispatch L1 communicates with Tensix (AICLK domain).

---

## 6. NoC Fabric & Router

### 6.1 Flit & Address Encoding

Each NoC flit is **256 bits** wide.

**noc_header_address_t bit-map:**

```
Bits [55:52]  flit_type [2:0] + 1b reserved
Bits [51:46]  x_coord   [5:0]   destination X
Bits [45:40]  y_coord   [5:0]   destination Y
Bits [39:34]  src_x     [5:0]   source X
Bits [33:28]  src_y     [5:0]   source Y
Bits [27:24]  vc_id     [3:0]   virtual channel
Bits [23:0]   addr_lo   [23:0]  lower address
```

**Full 96-bit target address:**
`TARG_ADDR_LO[31:0]` | `TARG_ADDR_MID[31:0]` | `TARG_ADDR_HI[31:0]`

**AXI gasket 56-bit layout (RTL-verified):**
```
[55:52] reserved (4 bits)
[51:32] address[39:20] (20-bit upper)
[31:28] VC / routing flags
[27:0]  address[19:0] (lower) + AxUSER
```

### 6.2 Flit Types

```
flit_type[2:0]:
  3'b000 = Normal data flit
  3'b001 = Header flit
  3'b010 = Path squash flit  (abort tendril reservation, release upstream VC)
  3'b011 = Dynamic routing flit  (928-bit carried list appended to packet)
  3'b100 = Atomic operation
  3'b101–3'b111 = Reserved
```

### 6.3 Routing Modes

| Mode        | Description                                    | Selection                     |
|-------------|------------------------------------------------|-------------------------------|
| DOR X→Y     | Dimension-order: X-axis first, then Y          | Default (VC_DIM_ORDER bit=0)  |
| DOR Y→X     | Dimension-order: Y-axis first, then X          | VC_DIM_ORDER bit=1            |
| Tendril     | Source-routed via path bits in header          | Non-zero path bits            |
| Dynamic     | Per-hop routing table; 928-bit carried list    | `en_dynamic_routing` in ATT   |
| Broadcast   | Multicast to row/column masks                  | VC 12–15                      |

**Priority order:** Path squash > Dynamic > Tendril > DOR

**Dynamic routing 928-bit carried list:**
- 29 entries × 32 bits
- Each entry: `x[5:0], y[5:0], vc[3:0], force_dim[1:0]` + reserved
- Each router reads its slot; NIU overwrites with return path info
- `force_dim` overrides DOR direction for that hop

**NOC_ORIENT rotation table:**

| Value | +X dir | +Y dir | Use                  |
|-------|--------|--------|----------------------|
| 0     | East   | North  | Default orientation  |
| 1     | North  | West   | 90° CCW              |
| 2     | West   | South  | 180°                 |
| 3     | South  | East   | 90° CW               |
| 4–7   | Mirrored variants    | Non-standard         |

### 6.4 Virtual Channels

| VC Range | Type      | Notes                                  |
|----------|-----------|----------------------------------------|
| 0–11     | Unicast   | Standard point-to-point traffic        |
| 12–15    | Broadcast | Row/column multicast                   |

Per-VC routing direction configurable via `VC_DIM_ORDER` register (default `0xAAAAAAAA` = all X→Y).

### 6.5 ATT (Address Translation Table)

ATT translates incoming AXI addresses to NoC destination `(x,y)` + endpoint ID.

**Table organization per NIU:**
- 16 mask entries (MASK_TABLE_ENTRY_0–15): `mask[5:0]`, `ep_id_idx`, `ep_id_size`, `table_offset`, `translate_addr`
- 16 EP address entries (MASK_TABLE_EP_LO/HI): 64-bit endpoint addresses
- 16 BAR entries (MASK_TABLE_BAR_LO/HI): base address registers
- 1024 endpoint entries (ENDPOINT_TABLE_0–1023): `x[5:0], y[11:6]`
- 32 dynamic routing match entries (ROUTING_TABLE_MATCH_0–31)
- 32 dynamic routing partial entries (ROUTING_TABLE_PART_ENTRY_0–31)

**Enable:** `ENABLE_TABLES[0]` = address translation; `[1]` = dynamic routing

### 6.6 Security Fence (SMN)

8 programmable ranges × 2 levels (read/write) per range:

| Register                    | Function                                   |
|-----------------------------|--------------------------------------------|
| SEC_FENCE_RANGE_0–7_START/END | 64-bit address boundaries                |
| SEC_FENCE_ATTRIBUTE_0–7     | RANGE_ENABLE[8], RD_SEC[7:4], WR_SEC[3:0] |
| SEC_FENCE_MASTER_LEVEL      | Master security level [3:0]               |
| SEC_FENCE_VIOLATION_FIFO    | Logs blocked transactions                 |

Transaction blocked if `master_level < range_required_level`.

---

## 7. NoC2AXI Interface (NIU)

### 7.1 NIU Variants in N1B0

| Module                           | Location     | Cardinal NoC ports  |
|----------------------------------|--------------|---------------------|
| `trinity_noc2axi_nw_opt`         | X=0, Y=4     | East, South (2 VC)  |
| `trinity_noc2axi_ne_opt`         | X=3, Y=4     | West, South (2 VC)  |
| `trinity_noc2axi_router_nw_opt`  | X=1, Y=4+Y=3 | N,E,S,W (4 VC)     |
| `trinity_noc2axi_router_ne_opt`  | X=2, Y=4+Y=3 | N,E,S,W (4 VC)     |

> N1B0 eliminates standalone `trinity_noc2axi_n_opt`. The two center columns (X=1,2) use the **composite** module that embeds both the AXI bridge (Y=4) and router (Y=3) in a single RTL module.

### 7.2 NIU External Interfaces

| Interface       | Dir  | Width | Description                       |
|-----------------|------|-------|-----------------------------------|
| AXI Subordinate | In   | 512b  | Host → NoC (AW/W/B + AR/R)       |
| AXI Manager     | Out  | 512b  | NoC → external memory             |
| APB Config      | In   | 32b   | ATT, security, timeout registers  |
| EDC APB         | In   | 32b   | EDC BIU register access           |
| NoC flits       | Bi   | 256b  | Cardinal port connections         |

### 7.3 N1B0 NOC2AXI_ROUTER_OPT Composite Tile

The composite tile embeds `trinity_noc2axi_n_opt` (Y=4) + `trinity_router` (Y=3) as one module.

**Internal cross-row connections:**

```
Y=4 NOC2AXI sub-module
  noc2axi_o_flit_out_req_south  →  router_i_flit_in_req_north   (4 handshake wires)
  noc2axi_i_flit_in_req_south   ←  router_o_flit_out_req_north

  Clock chain (9 fields, passes Y=4→Y=3):
    noc2axi_clock_routing_out → router_clock_routing_in

  EDC forward path:  noc2axi_edc_egress      → router_edc_ingress
  EDC loopback:      router_edc_lb_egress     → noc2axi_edc_lb_ingress
  External EDC ports exported at Y=3 boundary (not Y=4)

Y=3 Router sub-module
  Receives: i_local_nodeid_y    = external_y − 1   (Y=3 offset)
  Receives: i_noc_endpoint_id  = external_ep − 1  (EP=8 for NW, EP=13 for NE)
  Drives:   clock_routing_out[x][3]  → Tensix Y=2 column clock feed
```

**trinity_router parameters inside composite (N1B0, hard-coded):**

| Parameter                    | Value | Description                           |
|------------------------------|-------|---------------------------------------|
| REP_DEPTH_LOOPBACK           | 6     | Loopback register-slice stages (new N1B0) |
| REP_DEPTH_OUTPUT             | 4     | Output register-slice stages          |
| NUM_REPEATERS_INBOUND_NORTH  | 1     | From north (internal NOC2AXI)         |
| NUM_REPEATERS_OUTBOUND_NORTH | 1     | To north                              |
| NUM_REPEATERS_INBOUND_EAST   | 1     | From east column                      |
| NUM_REPEATERS_OUTBOUND_EAST  | 1     | To east column                        |
| NUM_REPEATERS_INBOUND_WEST   | 4     | From west column (inter-column dist.) |
| NUM_REPEATERS_OUTBOUND_WEST  | 4     | To west column                        |
| NUM_REPEATERS_INBOUND_SOUTH  | 5     | From south (Tensix Y=2 distance)      |
| NUM_REPEATERS_OUTBOUND_SOUTH | 5     | To south                              |

**Port prefix conventions:**

| Prefix         | Sub-module   | Row |
|----------------|-------------|-----|
| `noc2axi_i_*` / `noc2axi_o_*` | NOC2AXI bridge | Y=4 |
| `router_i_*`  / `router_o_*`  | Router         | Y=3 |
| `i_noc_*`     / `i_local_*`   | Shared config  | both |

**RDATA FIFO depth (`define selectable, default=512):**

| Define         | Depth |
|----------------|-------|
| RDATA_FIFO_32  | 32    |
| RDATA_FIFO_64  | 64    |
| RDATA_FIFO_128 | 128   |
| RDATA_FIFO_256 | 256   |
| RDATA_FIFO_512 | **512 (default)** |
| RDATA_FIFO_1024| 1024  |

---

## 8. EDC System

### 8.1 EDC1 Ring Protocol

The EDC system forms a serial ring per column. The BIU (master controller) resides in each NOC2AXI tile.

```
Column ring (per column X):

  BIU in NOC2AXI (Y=4)
    │ ring_egress (req_tgl, ack_tgl, data[7:0], parity, sideband[1:0])
  N1B0 composite (NOC2AXI_ROUTER_OPT):
    │ → NOC2AXI sub-nodes (Y=4) → internal forward link → Router sub-nodes (Y=3)
    │ Router loopback → NOC2AXI loopback
    │ external ring exit at Y=3
  Tensix Y=2 → Tensix Y=1 → Tensix Y=0
    │
    └─── ring_loopback ──────────────────────────────── BIU (loopback input)
```

**N1B0 composite EDC chaining (important):**
- Two EDC sub-chains inside each composite module (NOC2AXI nodes at Y=4 + Router nodes at Y=3)
- Forward path: NOC2AXI `edc_egress` → Router `edc_ingress`
- Loopback path: Router `edc_loopback_egress` → NOC2AXI `edc_loopback_ingress`
- External ring ports exported at **Y=3** (not Y=4)

### 8.2 EDC Node ID Structure

**16-bit Node ID:**

```
[15:11]  block_id[4:0]  = 5'b1_1110  (0x1E, same for all tiles)
[10:8]   y_coord[2:0]   = tile row (0 = Y=0, 4 = Y=4)
[7:0]    local_id[7:0]  = function within tile
```

**Standard local IDs:**

| local_id | Function                              |
|----------|---------------------------------------|
| 0xC0     | Configuration node (harvest control)  |
| 0x80     | L1 ECC monitor node                   |
| 0x40–0x7F| Sub-core nodes (T0–T3)               |
| 0x00–0x3F| NoC / router nodes                    |

**Pre-computed configuration node IDs:**

| Tile           | Node ID | Derivation              |
|----------------|---------|-------------------------|
| NOC2AXI (Y=4)  | 0xF4C0  | 0x1E<<11 \| 4<<8 \| 0xC0 |
| Dispatch (Y=3) | 0xF3C0  | 0x1E<<11 \| 3<<8 \| 0xC0 |
| Tensix Y=2     | 0xF2C0  | 0x1E<<11 \| 2<<8 \| 0xC0 |
| Tensix Y=1     | 0xF1C0  | 0x1E<<11 \| 1<<8 \| 0xC0 |
| Tensix Y=0     | 0xF0C0  | 0x1E<<11 \| 0<<8 \| 0xC0 |
| Broadcast      | 0xFFFF  | All nodes               |

### 8.3 Ring Traversal Order (per Tensix tile segment)

1. NoC subsegment: `sec_conf` → `VC_buf_N` → `VC_buf_E` → `VC_buf_S` → `VC_buf_W` → `NIU`
2. L1 partition: `T6_MISC` → `L1W2` ECC nodes
3. Sub-core T0: `IE` → `SRCB` → `UNPACK` → `PACK` → `SFPU` → `GPR` → `CFG` → `THCON` (13 nodes)
4. Sub-core T1: (same 13 nodes)
5. Sub-core T2: (same 13 nodes)
6. Sub-core T3: (same 13 nodes)
7. FPU: `G-Tile[0]` nodes → `G-Tile[1]` nodes
8. Overlay loopback node

### 8.4 EDC Timing Closure Parameters

All parameters are compile-time on each `tt_edc1_node` instance:

| Problem                             | Parameter              | Effect                                          |
|-------------------------------------|------------------------|-------------------------------------------------|
| Event/capture path critical         | `EVENT_PIPE_STAGES`    | Pipeline on `i_event` + `i_capture` into node  |
| Config/pulse output path critical   | `CONTROL_PIPE_STAGES`  | Pipeline on `o_config` + `o_pulse` out of node |
| Long serial link (physically far)   | `INGRESS_PIPE_STAGES`  | Flops on incoming serial bus signals            |
| Long serial link                    | `EGRESS_PIPE_STAGES`   | Flops on outgoing serial bus signals            |
| CDC boundary or very long req/ack   | `ENABLE_INGRESS_SYNC`  | Synchronizer on `req_tgl` (incoming)            |
| CDC boundary or very long req/ack   | `ENABLE_EGRESS_SYNC`   | Synchronizer on `ack_tgl` (incoming)            |

> Synchronizers sit on req/ack **toggle signals only** (not data/parity). For CDC: enable both sides.

**MCPDLY = 7 derivation (from P&R guide):**
3 repeater stages + 3-stage synchronizer + 1 setup margin = 7
SDC: `set_multicycle_path -setup 2 -hold 1` on all toggle req/ack lines

**Example instantiation:**
```systemverilog
tt_edc1_node #(
  .INGRESS_PIPE_STAGES (1),
  .EGRESS_PIPE_STAGES  (0),
  .EVENT_PIPE_STAGES   (1),
  .CONTROL_PIPE_STAGES (0),
  .ENABLE_INGRESS_SYNC (1),
  .ENABLE_EGRESS_SYNC  (1)
) u_edc1_node (.i_clk(clk), .i_reset_n(reset_n), ...);
```

### 8.5 BIU Registers

**EDC BIU Register Map (per-tile EDC APB offset):**

| Register              | Offset | Acc | Reset | Description                                            |
|-----------------------|--------|-----|-------|--------------------------------------------------------|
| EDC_BIU_ID            | 0x00   | RO  | 0x0   | `EDC_VERSION[31:16]`, `EDC_BIU_ID[7:0]`               |
| EDC_BIU_STAT          | 0x04   | RW  | 0x0   | `FATAL_ERR[18]`, `CRIT_ERR[17]`, `COR_ERR[16]`, `REQ_PKT_SENT[8]`, `RSP_PKT_RCVD[0]` |
| EDC_BIU_CTRL          | 0x08   | RW  | 0x0   | `INIT[31]` — clears all ring nodes                    |
| EDC_BIU_IRQ_EN        | 0x0C   | RW  | 0x0   | Per-event interrupt enables                           |
| EDC_BIU_RSP_HDR0      | 0x10   | RW  | 0x0   | `TGT_ID[31:16]`, `CMD[15:12]`, `PYLD_LEN[11:8]`, `CMD_OPT[7:0]` |
| EDC_BIU_RSP_HDR1      | 0x14   | RW  | 0x0   | `DATA1[31:24]`, `DATA0[23:16]`, `SRC_ID[15:0]`        |
| EDC_BIU_RSP_DATA[0–3] | 0x18–0x24 | RW | 0x0 | Response payload (4 × 32-bit)                        |
| EDC_BIU_REQ_HDR0      | 0x28   | RW  | 0x0   | Same format as RSP_HDR0                               |
| EDC_BIU_REQ_HDR1      | 0x2C   | RW  | 0x0   | Same format as RSP_HDR1                               |
| EDC_BIU_REQ_DATA[0–3] | 0x30–0x3C | RW | 0x0 | Request payload (4 × 32-bit)                         |

Payload length encoding: register value 0–15 → actual bytes 1–16.

### 8.6 EDC Node Instance Counts (N1B0 chip-wide)

| Subsystem                  | Instance Count | Pattern Types |
|----------------------------|----------------|---------------|
| Tensix tiles (×12)         | 5,172          | 47 patterns   |
| Dispatch engine west       | 159            | 27 patterns   |
| Dispatch engine east       | 159            | 27 patterns   |
| NOC2AXI_n_opt (composite)  | 36             | 18 patterns   |
| NOC2AXI_ne_opt (corner)    | 15             | 15 patterns   |
| NOC2AXI_nw_opt (corner)    | 15             | 15 patterns   |
| Router                     | 30             | 15 patterns   |
| **Total**                  | **5,586**      |               |

---

## 9. Harvest Architecture

### 9.1 Non-Harvestable Components

- NoC router and its repeaters
- EDC ring network itself
- Logic required to configure NEO cluster
- Output control logic

When a Tensix tile is harvested: overlay, L1, all 4 sub-cores become unavailable. NoC mesh remains operational (routing through tile continues).

### 9.2 Row Harvesting — 5 Baseline Mechanisms

| # | Mechanism         | Description                                                  |
|---|-------------------|--------------------------------------------------------------|
| 1 | `mesh_start`      | Y-coordinate origin remapping in NoC routing tables          |
| 2 | `dynamic_routing` | NoC routing table skips harvested row                       |
| 3 | `reset_isolation` | Harvested tile held in reset (power-gated or reset asserted) |
| 4 | `edc_bypass`      | EDC ring bypass wire routes around harvested tile            |
| 5 | `noc_y_size`      | `NOC_Y_SIZE` in all NIU `NODE_ID` registers decremented     |

**Critical:** All harvest registers must be programmed via EDC **before** normal NoC traffic starts.

**Harvest configuration sequence:**
1. BIU INIT: initialize all EDC ring nodes
2. Write mesh_start to EDC config node of affected column
3. Program dynamic routing tables to skip harvested rows
4. Enable reset_isolation (assert harvest tile resets)
5. Configure EDC bypass wire routing
6. Update `NOC_Y_SIZE` in all NIU `NODE_ID` registers

### 9.3 Column Harvesting (Rev 1.4)

Additional steps for column harvest:
- Update `NOC_X_SIZE` in all NIU `NODE_ID` registers
- Program `BRCST_EXCLUDE` masks (exclude harvested column from broadcasts)
- Remove harvested column endpoints from ATT endpoint table
- Bypass entire column in EDC ring

### 9.4 N1B0 ISO_EN — 6th Harvest Mechanism

N1B0 adds `ISO_EN[11:0]` isolation enable, propagated via `trinity_clock_routing_t`.

**Bit map:**

```
ISO_EN[11:0]:
  Bit [2×x + 0]: Dispatch isolation, column X=x
  Bit [2×x + 1]: Router/composite isolation, column X=x

  ISO_EN[1:0]  → column X=0 (dispatch west)
  ISO_EN[3:2]  → column X=1 (composite NW router)
  ISO_EN[5:4]  → column X=2 (composite NE router)
  ISO_EN[7:6]  → column X=3 (dispatch east)
  ISO_EN[11:8] → additional composite tile isolation (per HDD)
```

**ISO_EN behavior:**
- Assertion drives tile output signals to 0 via AND-gate isolation cells (AND-type ISO)
- Clock chain passes through clock routing struct regardless of ISO_EN state
- 11 signal groups require AND-type isolation cells at tile boundary
- SDC: `set_false_path` from ISO_EN to isolated flop data pins

---

## 10. Overlay Wrapper, Context Switch & DFX

### 10.1 Overlay Wrapper Hierarchy

```
tt_overlay_wrapper  (depth 2 inside tt_overlay_noc_wrap)
├── tt_overlay_wrapper_dfx         ← N1B0 DFX clock pass-through
│   ├── clock_reset_ctrl
│   ├── cpu_cluster_wrapper
│   │   └── RocketTile[0..7] (8× 64-bit RISC-V dm_cores, dm_clk)
│   └── memory_wrapper
│       ├── tt_t6_l1_partition_dfx ← N1B0 DFX clock pass-through
│       ├── Overlay L1 D-cache data (×16), tag (×8)   — dm_clk
│       ├── Overlay L1 I-cache data (×16), tag (×8)   — dm_clk
│       ├── Overlay L2 banks (×32), directory (×4)    — dm_clk
│       └── Context switch SRAMs (×2)                 — dm_clk
├── smn_wrapper (security management, ai_clk)
├── edc_wrapper (EDC overlay node, ai_clk)
└── t6_l1_flex_client_port (×4 T6 cores)
```

### 10.2 Hardware Accelerators

| Accelerator           | Function                                          | Clock   |
|-----------------------|---------------------------------------------------|---------|
| NoC Copy Command      | DMA L1→L1 across tiles via NoC packet             | DMCLK   |
| Patterned Address Gen | Strided/tiled address generation for DMA          | DMCLK   |
| Context Switch HW     | TRISC register file save/restore (8 slots)        | DMCLK   |
| Local Data Shuffling  | In-tile data reorganization (transpose, pad)      | DMCLK   |

### 10.3 Context Switch SRAMs

- 2 SRAMs per tile: `tt_mem_wrap_32x1024_sp` + `tt_mem_wrap_8x1024_sp`
- Clock: `dm_clk` domain (via `core_clk_gate → aon_core_clk`)
- 8 context slots; each saves TRISC register file + config state

### 10.4 N1B0 DFX Wrapper Modules

N1B0 inserts 4 DFX clock pass-through wrappers (pre-Tessent state: all `ifdef` blocks inactive; all outputs are wire-assigns).

**`tt_noc_niu_router_dfx`**

| Direction | Port name         | Mapped to              |
|-----------|-------------------|------------------------|
| In        | `i_aon_clk`       | `o_postdfx_aon_clk`    |
| In        | `i_clk`           | `o_postdfx_clk`        |
| In        | `i_ovl_core_clk`  | `o_postdfx_ovl_core_clk` |
| In        | `i_ai_clk`        | `o_postdfx_ai_clk`     |
| In        | `i_ref_clk`       | `o_postdfx_ref_clk`    |
| (ifdef)   | IJTAG control + DFD connections | — (not active in N1B0) |

**`tt_overlay_wrapper_dfx`**

| Direction | Port name          | Mapped to                  |
|-----------|--------------------|----------------------------|
| In        | `i_core_clk`       | `o_postdfx_core_clk`       |
| In        | `i_uncore_clk`     | `o_postdfx_uncore_clk`     |
| In        | `i_aiclk`          | `o_postdfx_aiclk`          |
| In        | `i_nocclk_aon`     | `o_postdfx_nocclk_aon`     |
| In        | `i_ref_clk`        | `o_postdfx_ref_clk`        |
| Note      | No IJTAG support (no ifdef block) | —               |

**`tt_instrn_engine_wrapper_dfx`**

| Direction | Port name | Mapped to          |
|-----------|-----------|--------------------|
| In        | `i_clk`   | `o_postdfx_clk`    |
| (ifdef)   | 2× FPU G-Tile IJTAG chains + IE DFD | — (not active) |

**`tt_t6_l1_partition_dfx`**

| Direction | Port name   | Mapped to            | Notes                          |
|-----------|-------------|----------------------|--------------------------------|
| In        | `i_clk`     | `o_predfx_clk`       | Pre-DFX output (for scan)      |
| In        | `i_clk`     | `o_postdfx_clk`      | Post-DFX output (functional)   |
| In        | `i_nocclk`  | `o_postdfx_nocclk`   |                                |
| (ifdef)   | 4× T6 core IJTAG groups (ts0–ts3) + L1 DFD | — (not active) |

**N1B0 DFX status summary:**
- `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` **not defined** → all IJTAG ifdef blocks inactive
- All DFX clock outputs are **wire assigns** (no clock buffers)
- DFX insertion deferred (Tessent flow not yet applied)

### 10.5 IJTAG Chain Topology (when `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` defined)

```
External TAP
  → tt_noc_niu_router_dfx (IJTAG ctrl)
  → tt_t6_l1_partition_dfx
      → T6 group ts0 → ts1 → ts2 → ts3
      → L1 DFD
  → tt_instrn_engine_wrapper_dfx
      → FPU G-Tile[0] IJTAG chain
      → FPU G-Tile[1] IJTAG chain
      → IE DFD
  → TAP SO output
```

---

## 11. Physical Design Notes

### 11.1 Synthesis — Required Defines

```
`define SYNTHESIS
`define NEO_PD_PROTO
`define TDMA_NEW_L1
`define RAM_MODELS
`define USE_VERILOG_MEM_ARRAY
`define TT_CUSTOMER
`define TRINITY
```

### 11.2 Synthesis Partitions (N1B0)

| # | Partition Module                           | Contents                               |
|---|--------------------------------------------|----------------------------------------|
| 1 | `tt_fpu_gtile`                             | FPU G-Tile (M-Tiles, FP Lanes, DEST)  |
| 2 | `tt_overlay_wrapper`                       | Overlay DM CPUs, L1/L2 cache, SMN     |
| 3 | `tt_noc_niu_router`                        | NoC fabric + NIU + Router              |
| 4 | `tt_t6_l1_partition`                       | L1 SRAM (16 banks, ECC, super-arb)    |
| 5 | `tt_instrn_engine_wrapper`                 | TRISC/BRISC + SRCB + SFPU + issue      |
| 6 | `tt_tensix_with_l1`                        | Tensix top (no SDC)                    |
| 7 | `tt_disp_eng_l1_partition`                 | Dispatch L1 (noc_clk domain)           |
| 8 | `tt_trin_disp_eng_noc_niu_router_west`     | West dispatch router                   |
| 9 | `tt_trin_disp_eng_noc_niu_router_east`     | East dispatch router                   |
| 10| `tt_disp_eng_overlay_wrapper`              | Dispatch overlay wrapper               |
| 11| `tt_dispatch_engine`                       | Dispatch top (no SDC)                  |
| 12| `trinity_noc2axi_nw_opt`                   | NW corner NIU                          |
| 13| `trinity_noc2axi_ne_opt`                   | NE corner NIU                          |
| 14| `trinity_noc2axi_router_nw_opt`            | NW composite tile                      |
| 15| `trinity_noc2axi_router_ne_opt`            | NE composite tile                      |

Process: **Samsung SF4X 4nm**. Floorplan depth: 4 partition levels.

### 11.3 Tensix NEO Floorplan (PD Ref Guide §1)

Dimensions: **~2794 µm × ~2121 µm**

```
 ┌────────────────────────────────────────────────────────┐  ← top
 │  NoC ROUTER (VC FIFOs, NIU, mesh flit ports)           │
 ├────────────────────────────────────────────────────────┤
 │  OVERLAY (DM CPUs + context switch + SMN + EDC)        │
 ├────────────────────────────────────────────────────────┤
 │  INSTRUCTION ENGINE  (TRISC0/1/2 + BRISC + SFPU + SRCB)│
 ├──────────────────────────┬─────────────────────────────┤
 │  G-TILE[0]               │  G-TILE[1]                  │
 │  M-Tile[0..7]            │  M-Tile[8..15]              │
 │  DEST sub-bank [0..7]    │  DEST sub-bank [8..15]      │
 ├──────────────────────────┴─────────────────────────────┤
 │  TDMA  (Pack × 1 + Unpack × 2)                         │
 ├────────────────────────────────────────────────────────┤
 │  L1 SRAM PARTITION (16 banks × 3072 rows × 128 bits)   │  ← bottom
 └────────────────────────────────────────────────────────┘

Left edge channel (~82 µm, M3+ only):  NoC→L1 512-bit write bus
Right edge:  EDC ring bypass wire (full tile height, toggle protocol)
```

**Critical placement rules:**
| Block   | Position     | Reason                                          |
|---------|--------------|-------------------------------------------------|
| L1      | Bottom       | TDMA is highest-BW client; L1 adjacent to TDMA |
| TDMA    | Above L1     | Widest bus (512-bit pack/unpack) kept short     |
| SRCB    | Above TDMA, center | Symmetric broadcast to both G-Tiles       |
| G-Tile[0,1] | Above SRCB | DEST→SRCA feedback (MOVD2A) path kept short |
| TRISC/IE | Above FPU  | MOP→FPU path kept short                         |
| Overlay | Above IE    | Context-switch SRAM + BIU/EDC                   |
| Router  | Top (below AON) | Mesh flit N/S/E/W at tile edge              |

### 11.4 N1B0 SRAM Inventory — Complete

#### Tensix Compute Tile (×12, X=0–3, Y=0–2)

| # | Clock    | Category                  | Qty/tile | Raw KB/tile | Physical cell (macro)                                           |
|---|----------|---------------------------|----------|-------------|------------------------------------------------------------------|
| 1 | ai_clk[x]| T6 L1 SRAM                | **512**  | 3,312       | `u_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1_0_{high,low}`     |
| 2 | ai_clk[x]| TRISC I-Cache (4 T6 × 4 threads) | 16 | 72        | `u_ln05lpe_*_512x72 / 256x72` (full/half)                      |
| 3 | ai_clk[x]| TRISC Local Memory (3 banks/T6) | 12 | 48         | `u_ln05lpe_*_512x52 / 1024x52`                                  |
| 4 | ai_clk[x]| TRISC Vec Local Memory (2/T6)  | 8  | 26          | `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x104m2b1c1`                  |
| 5 | dm_clk[x]| Overlay L1 D-cache data   | 16       | 36          | `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_128x144m2b1c1`                  |
| 6 | dm_clk[x]| Overlay L1 D-cache tag    | 8        | 3           | `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_32x100m2b1c1`                   |
| 7 | dm_clk[x]| Overlay L1 I-cache data   | 16       | 34          | `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x68m2b1c1`                   |
| 8 | dm_clk[x]| Overlay L1 I-cache tag    | 8        | 17          | `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_256x68m2b1c1`                   |
| 9 | dm_clk[x]| Overlay L2 banks (32×2 physical) | 32 | 136       | `u_ln05lpe_a00_mc_rf1r_hsr_lvt_256x136m2b1c1`                   |
| 10| dm_clk[x]| Overlay L2 directory      | 4        | 5           | `u_ln05lpe_a00_mc_rf1rw_hsr_lvt_64x160m2b1c1`                   |
| 11| noc_clk  | Router VC FIFOs (N/E/S/W × 17 cells) | 68 | 153    | `u_rf_wp_hsc_lvt_64x128m1fb1wm0_{0..16}`                        |
| 12| noc_clk  | NIU VC FIFO (17 cells)    | 17       | 38          | `u_rf_wp_hsc_lvt_72x128m2fb2wm0_{0..16}`                        |
| 13| noc_clk  | NOC tables (EP + Routing + ROCC) | 13 | 29        | `u_rf_2p_hsc_lvt_1024x13m4fb4wm0`                               |
| **SUM** | | **Per Tensix tile** | **730** | **~3,909** | |

Clock paths:
- ai_clk: `i_ai_clk[x]` → SMN → `ai_clk_gated` → DFX → `postdfx_clk` → L1/TRISC/FPU
- dm_clk: `i_dm_clk[x]` → `core_clk_gate` → `aon_core_clk` / `uncore_clk_gate` → `aon_uncore_clk`
- noc_clk: `i_noc_clk` → `postdfx_aon_clk` → router/NIU

#### Dispatch Tile (×2, X=0/3, Y=3)

| # | Clock    | Category                       | Qty/tile | Notes                          |
|---|----------|--------------------------------|----------|--------------------------------|
| 1 | noc_clk  | Dispatch L1 SRAM               | **128**  | Same wrapper as Tensix L1; 64 logical × 2 physical |
| 2–7| dm_clk | Overlay caches (D/I ×data/tag, L2 banks/dir) | 84 | Same macros as Tensix overlay |
| 8 | noc_clk  | ATT EP table                   | 4        | `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` |
| 9 | noc_clk  | ATT routing + ROCC             | 8        | `u_rf_2p_hsc_lvt_1024x13m4fb4wm0` |
| 10| dm_clk   | Context switch SRAMs           | 2        | `tt_mem_wrap_32x1024_sp` + `tt_mem_wrap_8x1024_sp` |
| **SUM** | | **Per Dispatch tile** | **~226** | |

#### NOC2AXI_ROUTER_OPT Composite (×2, X=1/2, Y=4+Y=3)

| # | Clock   | Category                      | Qty/tile |
|---|---------|-------------------------------|----------|
| 1–4 | noc_clk | Router VC N/E/S/W (64-deep, 17 cells each) | 68 |
| 5  | noc_clk | NOC EP table + routing + ROCC | 13       |
| 6  | noc_clk/axi_clk | AXI RD/WR data FIFOs | ~26   |
| **SUM** | | **Per composite tile** | **~107** |

#### NOC2AXI Corner (×2, X=0/3, Y=4)

| # | Clock   | Category                      | Qty/tile |
|---|---------|-------------------------------|----------|
| 1–2 | noc_clk | VC E + S (64-deep, 17 cells each) | 34   |
| 3  | noc_clk | NOC EP table + routing + ROCC | 13       |
| 4  | noc_clk/axi_clk | AXI RD/WR FIFOs (larger; no router sharing) | ~43 |
| **SUM** | | **Per corner tile** | **~90** |

#### N1B0 Chip-Wide SRAM Summary

| Tile Type              | Module                       | # Tiles | SRAMs/tile | Chip Total |
|------------------------|------------------------------|---------|------------|------------|
| Tensix                 | `tt_tensix_with_l1`          | 12      | **730**    | **8,760**  |
| Dispatch               | `tt_dispatch_top_{e/w}`      | 2       | ~226       | ~452       |
| NOC2AXI_ROUTER_OPT     | `trinity_noc2axi_router_*`   | 2       | ~107       | ~214       |
| NOC2AXI corner         | `trinity_noc2axi_{ne/nw}_opt`| 2       | ~90        | ~180       |
| Router standalone      | `trinity_router`             | **0**   | —          | 0 (N1B0)  |
| **N1B0 Chip Total**    |                              | **18**  |            | **≈9,606** |

**By clock domain (chip-wide):**

| Domain     | Macros (×12 Tensix) | + Dispatch | + NIU | Chip total |
|------------|---------------------|------------|-------|------------|
| ai_clk     | 548 × 12 = 6,576    | —          | —     | **6,576**  |
| dm_clk     | 84 × 12 = 1,008     | 84 × 2 = 168 | —   | **1,176**  |
| noc_clk    | 98 × 12 = 1,176     | ~58 × 2    | ~394  | **≈1,854** |

**By category (T6 L1 dominates):**
- T6 L1 SRAM: 512/tile × 12 = **6,144 macros** (physical cell `*_768x69m4b1c1_{high,low}`)
- TRISC memories: (16+12+8)/tile × 12 = **432 macros**
- Overlay caches: 84/tile × 14 tiles = **1,176 macros**
- Router VC FIFOs: 85/tile × 12 Tensix + 68 × 2 NOC2AXI-R + 34 × 2 corner = **1,284 macros**
- NOC tables: 13/tile × 18 active tiles = **234 macros**
- AXI FIFOs (NIU): ~26 × 2 + ~43 × 2 = **~138 macros**
- Dispatch L1: 128 × 2 = **256 macros**
- Context switch: 2 × 14 = **28 macros**

---

## 12. Register Maps

### 12.1 NOC2AXI Register Map

**Base address:** `0x2000_0000`  Module: `noc_niu_risc`

| Register            | Offset | Bits   | Description                                    |
|---------------------|--------|--------|------------------------------------------------|
| TARGET_ADDR_LO/MID/HI | 0x00–0x08 | [31:0] | 96-bit NoC target address                 |
| RET_ADDR_LO/MID/HI  | 0x0C–0x14 | [31:0] | 96-bit return address                      |
| PACKET_TAG          | 0x18   | [15:0] | Transaction tag                               |
| CMD_BRCST           | 0x1C   | [31:0] | Command + broadcast control                   |
| AT_LEN / AT_LEN_1   | 0x20–0x24 | [31:0] | Atomic op length                           |
| AT_DATA             | 0x28   | [31:0] | Atomic data                                   |
| BRCST_EXCLUDE       | 0x2C   | [23:0] | Broadcast exclude coordinates                 |
| L1_ACC_AT_INSTRN    | 0x30   | [15:0] | L1 accumulator atomic instruction             |
| SECURITY_CTRL       | 0x34   | [3:0]  | Security master level                         |
| CMD_CTRL            | 0x40   | [0]    | Command pending                               |
| NODE_ID             | 0x44   | [28:0] | NODE_ID_X[5:0], NODE_ID_Y[11:6], NOC_X_SIZE[18:12], NOC_Y_SIZE[25:19], ROUTING_DIM_ORDER_XY[28] |
| ENDPOINT_ID         | 0x48   | [31:0] | Endpoint identifier                           |
| NUM_MEM_PARITY_ERR  | 0x50   | [15:0] | Memory parity error counter                   |
| NUM_HEADER_1/2B_ERR | 0x54–0x58 | [15:0] | Header ECC error counters                 |
| ECC_CTRL            | 0x5C   | [5:0]  | ECC_ERR_CLEAR[2:0], ECC_ERR_FORCE[5:3]       |
| CMD_BUF_AVAIL       | 0x64   | [28:0] | BUF0[4:0], BUF1[12:8], BUF2[20:16], BUF3[28:24] |
| CMD_BUF_OVFL        | 0x68   | [3:0]  | Per-buffer overflow flags                     |

**Configuration registers (`0x100` offset):**

| Register                  | Offset | Key bits                                                |
|---------------------------|--------|----------------------------------------------------------|
| NIU_CONFIG                | 0x100  | CLK_GATING_DISABLED[0], AXI_ENABLE[15], CMD_BUFFER_FIFO_EN[16] |
| ROUTER_CONFIG             | 0x104  | CLK_GATING_DISABLED[0], ECC_HEADER_SECDED_CHK_CORRECT[18] |
| BROADCAST_CONFIG_0–3      | 0x108–0x114 | Row disable masks [31:0]                         |
| MEM_SHUTDOWN_CONTROL      | 0x118  | DSLPLV[2], DSLP[1], SD[0]                              |
| VC_DIM_ORDER              | 0x128  | Per-VC XY/YX order [31:0] (default 0xAAAAAAAA)          |
| THROTTLER_CYCLES_PER_WINDOW| 0x12C | Window cycle count [31:0]                               |
| NIU_TIMEOUT_VALUE_0/1     | 0x148–0x14C | Timeout cycles (2 instances)                     |
| INVALID_FENCE_* (×4)      | 0x150–0x18C | 4 invalid-access fence ranges (64-bit addr each) |
| VC_THROTTLER_*            | 0x1B0–0x1C0 | Per-VC handshake throttling                      |

**Security fence (`0x400` offset):**

| Register                       | Offset   | Description                             |
|--------------------------------|----------|-----------------------------------------|
| SEC_FENCE_RANGE_0–7_START/END  | 0x400+   | 64-bit address boundaries (8 ranges)   |
| SEC_FENCE_ATTRIBUTE_0–7        | 0x480–0x49C | RANGE_ENABLE[8], RD_SEC[7:4], WR_SEC[3:0] |
| SEC_FENCE_MASTER_LEVEL         | 0x4A0    | Master security level [3:0]            |
| SEC_FENCE_VIOLATION_FIFO_STATUS| 0x4A4    | FIFO status                             |
| SEC_FENCE_VIOLATION_FIFO_RDDATA| 0x4A8    | Violation record                        |

### 12.2 Tensix NoC Registers

**Base address:** `0x0200_0000`  Module: `noc_niu`

| Register        | Offset      | Description                                    |
|-----------------|-------------|------------------------------------------------|
| TARG_ADDR_LO/MID/HI | 0x000–0x008 | 96-bit target address                    |
| RET_ADDR_LO/MID/HI  | 0x00C–0x014 | 96-bit return address                    |
| CMD_LO/HI       | 0x018–0x01C | Command word                                   |
| BRCST_LO/HI     | 0x020–0x024 | Broadcast control                              |
| AT_LEN          | 0x028       | Atomic length                                  |
| L1_ACC_AT_INSTRN| 0x02C       | L1 accumulator atomic instruction [15:0]       |
| SEC_CTRL        | 0x030       | Security control                               |
| AT_DATA         | 0x034       | Atomic data                                    |
| INLINE_DATA_LO/HI| 0x038–0x03C| Inline data                                    |
| BYTE_ENABLE     | 0x040       | Byte enable mask [31:0]                        |
| CMD_CTRL        | 0x060       | Command control                                |
| NODE_ID         | 0x064       | NODE_ID_X[5:0], NODE_ID_Y[11:6], NOC_X_SIZE[18:12], NOC_Y_SIZE[25:19] |
| ENDPOINT_ID     | 0x068       | Endpoint ID                                    |
| CMD_BUF_AVAIL   | 0x080       | Command buffer availability                    |
| CMD_BUF_OVFL    | 0x084       | Buffer overflow flags                          |

### 12.3 Overlay / Cluster Control Registers

**Base address:** `0x0300_0000`  Module: `tt_cluster_ctrl`

| Register             | Offset     | Description                                             |
|----------------------|------------|---------------------------------------------------------|
| reset_vector_0–7     | 0x00–0x38  | 64-bit RISC-V reset vectors (8 DM cores)               |
| scratch_0–31         | 0x40–0xBC  | General purpose 32-bit registers                        |
| clock_gating         | 0xCC       | rocc[0], idma[1], cluster_ctrl[2], context_switch[3], llk_intf[4], snoop[5], global_cmdbuf[6], l1_flex[7:8], fds[9] |
| clock_gating_hyst    | 0xD0       | Hysteresis [6:0] (default 0x8)                          |
| wb_pc_reg_c0–7       | 0xD4–0x10C | 64-bit PC capture per DM core                           |
| ecc_parity_control   | 0x118      | ECC parity enable [0]                                   |
| asserts              | 0x124      | Hardware assertions [31:0] (read-only)                  |
| overlay_info         | 0x1CC      | dispatch_inst[0], is_customer[1], tensix_version[9:4], noc_version[15:10], overlay_version[21:16] |
| global_counter_ctrl  | 0x1D0      | global_counter_en[0] (default 1), clear[1]              |

**L2 cache controller** (base `0x0401_0000`):

| Register      | Offset | Description                          |
|---------------|--------|--------------------------------------|
| Configuration | 0x000  | banks[7:0], ways[15:8], lgSets[23:16], lgBlockBytes[31:24] |
| Flush64       | 0x200  | Flush at 64-bit address              |
| Flush32       | 0x240  | Flush at 32-bit address (shift 4)    |
| Invalidate64  | 0x280  | Invalidate at 64-bit address         |
| FullInvalidate| 0x300  | Invalidate all L2                    |

**Watchdog timer** (per DM core, base `0x0400_8000 + N×0x1000`):

| Register | Offset | Description                                    |
|----------|--------|------------------------------------------------|
| CTRL     | 0x00   | wdogscale[3:0], wdogrsten[8], wdogenalways[12] |
| COUNT    | 0x08   | wdogcount[30:0]                                |
| FEED     | 0x18   | Write 0xD09F00D to reset watchdog              |
| KEY      | 0x1C   | Write 0x51F15E to unlock                       |
| CMP      | 0x20   | wdogcmp0[15:0] (default 0x1000)               |

### 12.4 EDC BIU Registers

See §8.5 complete register table.

### 12.5 Address Translation Table (ATT)

**Base:** `0x2010_000` (within NOC2AXI APB space)

| Register              | Offset       | Description                              |
|-----------------------|--------------|------------------------------------------|
| ENABLE_TABLES         | 0x00         | en_address_translation[0], en_dynamic_routing[1] |
| CLK_GATING            | 0x04         | clk_gating_enable[0], hysteresis[7:1]    |
| MASK_TABLE_ENTRY_0–15 | 0x30–0x198   | mask[5:0], ep_id_idx[11:6], ep_id_size[17:12], table_offset[27:18], translate_addr[28] |
| MASK_TABLE_EP_LO/HI   | 0x38–0x1A4   | 64-bit endpoint addresses (16 entries)   |
| MASK_TABLE_BAR_LO/HI  | 0x40–0x1AC   | 64-bit BARs (16 entries)                 |
| ROUTING_TABLE_MATCH   | 0x200–0x27C  | 32 dynamic routing match entries         |
| ROUTING_TABLE_PART    | 0x300–0x37C  | 32 partial routing entries               |
| ENDPOINT_TABLE_0–1023 | 0x2000–0x2FFC| x[5:0], y[11:6] per endpoint            |

---

## 13. Verification & Testbench Infrastructure

### 13.1 Testbench Overview

**Environment:**
- Python 3.9.18, Synopsys VCS V-2023.12-SP1-1, Verdi V-2023.12-SP1-1
- cocotb 1.9.0 + cocotbext-axi + cocotbext-apb + pyyaml
- Setup: `source $TENSIX_ROOT/tb/setup.sourceme`; run: `make` in `$TENSIX_ROOT/tb/`

**Test categories (v0.10):**

| Category        | Tests                                                         |
|-----------------|---------------------------------------------------------------|
| Basic sanity    | NoC send/receive, address pinger                              |
| EDC             | Error injection, BIU interrupt monitoring, COR/UNC            |
| Security fence  | NOC2AXI security fence boundary                               |
| Harvest         | Row/column harvest + clock gating combinations                |
| Matrix multiply | FP16B, INT8, INT16 formats (multiple sizes)                   |
| Power stress    | `dm_traffic_with_local_matmul_test`                           |
| Broadcast       | Strided multicast, broadcast                                  |

### 13.2 TTX Binary Format

TTX packages test vectors: kernel binary + input data + YAML descriptor.

```
File Header (32 bytes):
  [3:0]   Magic number
  [31:4]  7 reserved 32-bit fields

Chunks (repeating):
  Chunk Header (16 bytes):
    [7:0]   Target L1 address (64-bit)
    [11:8]  Data size (32-bit)
    [15:12] Reserved
  Chunk Data: <size> bytes

test.yaml:
  l1_output_fifo:
    output_fifo_address: 0x...
    output_fifo_size: N
  expected_commands_pushed: N  ← poll L1[0x4] until matches
```

**Test execution:**
1. Load all TTX chunks into L1
2. Clear output FIFO; zero L1[0x0–0x7] (0x4 = outbound mailbox)
3. Poll L1[0x4] until == `expected_commands_pushed`
4. Validate output vs `dump.bin` golden

### 13.3 Performance Test (trinity_performance)

```bash
cd $TT_DELIVERY/tb
make TESTCASE=trinity_performance_test              # basic
make TESTCASE=trinity_performance_test WAVES=1      # with waveforms
make TESTCASE=trinity_performance_test PERF_MONITOR_VERBOSITY=1
make TESTCASE=trinity_performance_test MONITOR_ROUND_TRIP_LATENCY=1
```

**Data size constraint:** `8 cores × 3 buffers × TRANSFER_SIZE × NUM_TRANSFERS ≤ 512 KB`

| TRANSFER_SIZE | NUM_TRANSFERS | Total     |
|---------------|---------------|-----------|
| 128           | 160           | 480 KB    |
| 1024          | 20            | 480 KB    |
| 4096          | 5             | 480 KB    |

### 13.4 noc2axi_perf_monitor (N1B0 Simulation-Only)

Measures AXI transaction latency in simulation. **Not synthesizable** (uses `real` ports).

**Output ports:**

| Port               | Description                                |
|--------------------|--------------------------------------------|
| `o_avg_rd_latency` | Running average: AR→first-R-beat (cycles)  |
| `o_avg_wr_latency` | Average: AW→B-beat (cycles)               |
| `o_max_rd_latency` | Maximum read latency observed              |
| `o_min_rd_latency` | Minimum read latency observed              |
| `o_total_rd_txn`   | Total read transactions                    |
| `o_total_wr_txn`   | Total write transactions                   |

**Plusargs:**
```
+PERF_MONITOR_VERBOSITY=0  (silent, default)
+PERF_MONITOR_VERBOSITY=1  (summary at end)
+PERF_MONITOR_VERBOSITY=3  (verbose per-transaction)
+MONITOR_ROUND_TRIP_LATENCY=1  (per-ID tracking)
```

### 13.5 axi_dynamic_delay_buffer (N1B0 Synthesizable)

Programmable AXI R-channel cycle-delay (timestamp FIFO, `delay_cycles` input).

| Parameter | Default | Description              |
|-----------|---------|--------------------------|
| MAX_DELAY | 256     | Maximum programmable delay |
| HEADROOM  | 256     | Extra FIFO capacity      |

**Operation:** Beat released when `current_cycle ≥ entry_timestamp + delay_cycles`.
**Assertion:** `delay_cycles` must not change while FIFO is non-empty.

---

## 14. N1B0 Silicon Variant — Delta from Baseline

### 14.1 Architecture Delta Table

| Feature                    | Baseline Trinity        | N1B0                                                |
|----------------------------|-------------------------|-----------------------------------------------------|
| Grid                       | 4×5 (20 tiles)          | 4×5 (same)                                          |
| L1 per Tensix tile         | 192 KB (128 macros)     | **768 KB (512 macros, 4× depth)**                   |
| Total L1 (12 tiles)        | 2.304 MB                | **9.216 MB**                                        |
| L1 config                  | `tt_mimir_l1_cfg.svh`   | **`tt_trin_l1_cfg.svh`** (BANK_IN_SBANK=16)         |
| NOC2AXI + Router           | Separate modules        | **Composite dual-row (Y=4+Y=3)**                    |
| Tile enum (tile_t)         | Different values        | **TENSIX=0, NE=1, NE_R=2, NW_R=3, NW=4, DE=5, DW=6, ROUTER=7** |
| `ai_clk` / `dm_clk`       | Scalar inputs           | **Per-column `i_ai_clk[3:0]`, `i_dm_clk[3:0]`**    |
| `i_axi_clk`                | N/A                     | **Scalar; added for AXI domain**                    |
| X-axis NoC                 | Generate loop           | **Manual assigns + explicit repeater instances**    |
| Repeaters Y=4              | None                    | **4 stages (E↔W per column pair)**                  |
| Repeaters Y=3              | None                    | **6 stages (E↔W per column pair)**                  |
| S-direction repeaters      | 0                       | **5 stages (Y=3→Y=2)**                              |
| PRTN chain                 | Absent                  | **Per-column, Y=2→Y=1→Y=0**                         |
| ISO_EN                     | Absent                  | **`ISO_EN[11:0]` (6th harvest mechanism)**          |
| Router tiles X=1,2 Y=3     | Standalone `trinity_router` | **Empty placeholder (inside composite)**        |
| DFX wrappers               | Absent                  | **4 clock pass-through wrappers**                   |
| IJTAG                      | Present (ifdef)         | **Not compiled (`INCLUDE_TENSIX_NEO_IJTAG_NETWORK` undef)** |
| REP_DEPTH_LOOPBACK         | 0                       | **6**                                               |
| REP_DEPTH_OUTPUT           | 0                       | **4**                                               |
| RDATA FIFO depth           | Fixed                   | **Configurable 32–1024 via `define`**               |
| Total chip SRAMs           | ~6,136                  | **~9,606**                                          |
| Chip SRAM / Tensix tile    | 326                     | **730**                                             |

### 14.2 N1B0 RTL File Locations

All under `$TENSIX_ROOT/used_in_n1/`:

| File                                      | Module                             |
|-------------------------------------------|------------------------------------|
| `targets/4x5/trinity.sv`                  | Top-level SoC                      |
| `targets/4x5/trinity_pkg.sv`              | Package constants                  |
| `trinity_noc2axi_router_ne_opt.sv`        | Composite NE tile (X=2)            |
| `trinity_noc2axi_router_nw_opt.sv`        | Composite NW tile (X=1)            |
| `trinity_noc2axi_ne_opt.sv`               | Corner NE NIU (X=3)                |
| `trinity_noc2axi_nw_opt.sv`               | Corner NW NIU (X=0)                |
| `dfx/tt_noc_niu_router_dfx.sv`            | DFX — NoC/NIU/Router               |
| `dfx/tt_overlay_wrapper_dfx.sv`           | DFX — Overlay                      |
| `dfx/tt_instrn_engine_wrapper_dfx.sv`     | DFX — Instruction Engine           |
| `dfx/tt_t6_l1_partition_dfx.sv`           | DFX — L1 Partition                 |
| `tb/noc2axi_perf_monitor.sv`              | Sim-only AXI latency monitor       |
| `tb/axi_dynamic_delay_buffer.sv`          | Synthesizable AXI delay buffer     |
| `inc/tt_trin_l1_cfg.svh`                  | N1B0 L1 config (BANK_IN_SBANK=16)  |

### 14.3 N1B0 Quick Reference Card

```
Grid:       SizeX=4, SizeY=5 (20 tile positions)
Compute:    12 Tensix (X=0–3, Y=0–2)
Dispatch:   2 tiles (X=0 W, X=3 E at Y=3)
NIU:        NOC2AXI_NW_OPT (X=0,Y=4), NOC2AXI_NE_OPT (X=3,Y=4)
            NOC2AXI_ROUTER_NW_OPT (X=1, Y=4+3), NOC2AXI_ROUTER_NE_OPT (X=2, Y=4+3)
Router Y=3: EMPTY placeholder (no standalone instantiation)

L1/tile:    768 KB usable; 512 physical macros; 3,312 KB raw area
Total L1:   9.216 MB (12 tiles × 768 KB)
Total SRAM: ≈9,606 macros (chip-wide)

Clock:      i_axi_clk, i_noc_clk (scalars); i_ai_clk[3:0], i_dm_clk[3:0] (per-column)
PRTN:       Y=2→Y=1→Y=0 per column
ISO_EN:     [11:0], bit 2x+0=dispatch col-x, 2x+1=router col-x
Harvest:    6 mechanisms (5 baseline + ISO_EN)

Repeaters:  Y=4 E↔W = 4 stages; Y=3 E↔W = 6 stages; Y=3→Y=2 S/N = 5 stages
REP_DEPTH_LOOPBACK=6, REP_DEPTH_OUTPUT=4, E/N=1 stage, W=4 stages, S=5 stages

MAX INT8 MACs/cycle/tile:  8192
MAX BF16 MACs/cycle/tile:  1024
K_tile hardware max:       48 rows (SRCA constraint)
DEST rows (INT32 mode):    512
```

---

## 15. INT16/FP16B/INT8 LLM Mapping Guide

### 15.1 Dimension Glossary

| Symbol   | Meaning            | LLaMA 3.1 8B | HW Constraint                        |
|----------|--------------------|--------------|---------------------------------------|
| M        | Batch × seq tokens | 128          | DEST rows (512 INT32 / 1024 FP16)    |
| K        | Reduction dim      | 4096         | SRCA depth; max 48/pass              |
| N        | Output features    | 4096–14336   | FPU width = 16 fixed                 |
| K_tile   | K per MOP pass     | 48           | Hardware max = 48 rows               |
| N_tile   | N per FPU cycle    | 16           | Fixed = 16 FPU columns               |
| M_tile   | M per DEST pass    | 16–256       | SW choice; INT32: ≤ 256              |
| d_model  | Hidden dim         | 4096         | K=N=d_model for attention layers     |
| d_ffn    | FFN intermediate   | 14336        | N=d_ffn for FFN up/gate projections  |
| d_k      | Attention head dim | 128          | K_tile = d_k (fits in SRCA at once)  |

### 15.2 GEMM Tiling Loop

```python
for m_start in range(0, M, M_tile):
    for n_start in range(0, N, N_tile):   # N_tile=16 fixed
        clear_dest()
        for k_start in range(0, K, K_tile):  # K_tile=48 max
            # TRISC0: unpack A[m:m+M_tile, k:k+K_tile] → SRCA
            # TRISC0: unpack B[k:k+K_tile, n:n+N_tile] → SRCB
            # TRISC1: issue MOP → FPU accumulates into DEST
        # TRISC2: pack DEST → L1 output buffer
```

### 15.3 L1 Fit (N1B0 768 KB)

```
A buffer = M_tile × K_tile × 2B (INT16)
B buffer = K_tile × N_tile × 2B (INT16)
C buffer = M_tile × N_tile × 4B (INT32 accum)
Overhead ≈ 16 KB (kernel, stack, SFPU)

Example: M_tile=256, K_tile=48, N_tile=16:
  A = 256×48×2 = 24,576 B
  B = 48×16×2  =  1,536 B
  C = 256×16×4 = 16,384 B
  Total ≈ 58 KB  ← fits easily in 768 KB (N1B0)
```

N1B0 768 KB L1 advantage: KV-cache context window ≈ 4× larger than baseline (192 KB).

### 15.4 LLaMA 3.1 8B Layer Mapping

| Layer           | M   | K     | N     | K passes | Recommended format |
|-----------------|-----|-------|-------|----------|--------------------|
| QKV projection  | 128 | 4096  | 4096  | 86       | INT8 W + INT16 A   |
| Attention output| 128 | 4096  | 4096  | 86       | FP16B              |
| FFN up/gate     | 128 | 4096  | 14336 | 86       | INT8               |
| FFN down        | 128 | 14336 | 4096  | 299      | INT8               |
| KV-cache update | seq | 128   | 128   | 3        | INT16 (long ctx)   |

K_tile = 48 → passes = ceil(K / 48): d_model=4096 → 86 passes; d_ffn=14336 → 299 passes.

---

## 16. Release History & EDA Versions

### 16.1 Version History

| Version | Key RTL/Verification Changes                                                                    |
|---------|------------------------------------------------------------------------------------------------|
| v0.1    | Initial docs, top-level wrapper, initial floorplan                                              |
| v0.2    | First RTL (partial encrypt), basic testbench, reference synthesis                              |
| v0.3    | Dispatch core, updated NoC2AXI, 12 clusters                                                    |
| v0.4    | INT4 support, FP16 capacity reduced, preliminary ECC/parity                                    |
| v0.4.1  | Overlay memory reduction, multicast/strided multicast from NoC2AXI                             |
| v0.5    | LDM/iCache 50% reduction (cores 1–2), EDC unit in each NoC2AXI, area optimization             |
| v0.6    | Partition split: east/west router; NoC2AXI n/ne/nw variants; updated SDC flow                  |
| v0.7    | Palladium compat, timing loop fix, abutted design fixes, NEO error/fault connectivity          |
| v0.8    | NOC clock rerouted through NOC partition; overlay interrupt; EDC bypass in overlay; abutment fixes |
| v0.9    | Clock gating fixes, EDC CDC timing, expanded EDC coverage, harvest+clock-gating test           |
| **v0.10** | **Extra repeater stages, GTile 6.5% area reduction, BIU interrupt monitoring, security fence test, dm_traffic_with_local_matmul_test** |

### 16.2 EDA Tool Versions (v0.10)

| Tool               | Version           |
|--------------------|-------------------|
| Synopsys VCS       | V-2023.12-SP1-1   |
| Synopsys Verdi     | V-2023.12-SP1-1   |
| Synopsys Synthesis | T-2022.03-SP5     |
| Synopsys Formality | T-2022.03-SP5     |
| Synopsys Spyglass  | U-2023.03-SP1-1   |
| Python             | 3.9.18            |
| cocotb             | 1.9.0             |

### 16.3 Open Source Dependencies

From https://github.com/pulp-platform: APB, AXI, AXI_STREAM, COMMON_CELLS, iDMA, REGISTER_INTERFACE, TECH_CELLS_GENERIC, OBI
From https://github.com/ucb-bar/chipyard: Chipyard / Rocket core

---

## Appendix A: Related Documents

| Document                                  | Location                                          |
|-------------------------------------------|---------------------------------------------------|
| N1B0_HDD_v0.1.md                          | `DOC/N1B0/N1B0_HDD_v0.1.md`                      |
| N1B0_NPU_HDD_v0.1.md                      | `DOC/N1B0/N1B0_NPU_HDD_v0.1.md`                  |
| N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1         | `DOC/N1B0/N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md`  |
| N1B0_DFX_HDD_v0.1                         | `DOC/N1B0/N1B0_DFX_HDD_v0.1.md`                  |
| N1B0_PerfMonitor_HDD_v0.1                 | `DOC/N1B0/N1B0_PerfMonitor_HDD_v0.1.md`          |
| N1B0_AXI_Dynamic_Delay_HDD_v0.1          | `DOC/N1B0/N1B0_AXI_Dynamic_Delay_HDD_v0.1.md`   |
| n1b0_memory_list.md                       | `DOC/N1B0/n1b0_memory_list.md`                    |
| trinity_memory_list.md                    | `DOC/N1B0/trinity_memory_list.md`                 |
| Trinity_PD_Ref_Guide_Rev1p0.pdf           | `docs/Trinity_PD_Ref_Guide_Rev1p0.pdf`            |
| TT_Row_Column_Harvesting_with_Tests.pdf   | `docs/TT_Row_Column_Harvesting_with_Tests.pdf`    |
| TT_Trinity_Performance_Test.pdf           | `docs/TT_Trinity_Performance_Test.pdf`            |
| tensix-user-manual.html                   | `docs/tensix-user-manual.html`                    |
| integration-guide.html                    | `docs/integration-guide.html`                     |
| edc-node-instances.html                   | `docs/edc-node-instances.html`                    |
| edc-timing-closure.html                   | `docs/edc-timing-closure.html`                    |
