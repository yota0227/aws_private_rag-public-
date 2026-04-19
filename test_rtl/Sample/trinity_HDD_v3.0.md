# Trinity SoC Hardware Design Document v3.0

**Document:** trinity_HDD_v3.0.md
**Date:** 2026-03-20
**Scope:** Trinity SoC — baseline + N1B0 silicon variant
**Revision history:**
- v1.x: Initial EDC/Ring topology (M1–M4)
- v2.x: NIU, Overlay, Router address decoding, INT16 guide, SRAM inventory (M5–M17)
- **v3.0:** Full rebuild from official docs + N1B0 archive; adds PD ref guide, register maps, testbench, EDC timing closure, performance guide, register-level sub-chapters

---

## Table of Contents

1. [Trinity Overview](#1-trinity-overview)
2. [Grid Architecture & Tile Map](#2-grid-architecture--tile-map)
3. [Clock & Reset Architecture](#3-clock--reset-architecture)
4. [Tensix NEO Cluster](#4-tensix-neo-cluster)
   - 4.1 FPU (G-Tile / M-Tile)
   - 4.2 Instruction Engine (TRISC/BRISC)
   - 4.3 TDMA Pack/Unpack
   - 4.4 SFPU
   - 4.5 L1 Memory
   - 4.6 Register Files (DEST / SRCA / SRCB)
   - 4.7 Data Formats & MAC Throughput
5. [Dispatch Engine](#5-dispatch-engine)
6. [NoC Fabric & Router](#6-noc-fabric--router)
   - 6.1 Flit & Address Encoding
   - 6.2 Routing Modes
   - 6.3 Virtual Channels
   - 6.4 ATT (Address Translation Table)
   - 6.5 Security Fence (SMN)
7. [NoC2AXI Interface (NIU)](#7-noc2axi-interface-niu)
   - 7.1 AXI↔NoC Bridge
   - 7.2 N1B0 NOC2AXI_ROUTER_OPT Composite Tile
8. [EDC System](#8-edc-system)
   - 8.1 EDC1 Ring Protocol
   - 8.2 Node ID Structure
   - 8.3 Ring Traversal Order
   - 8.4 EDC Timing Closure (Pipe Stages & Synchronizers)
   - 8.5 BIU Registers
   - 8.6 EDC Node Inventory
9. [Harvest Architecture](#9-harvest-architecture)
   - 9.1 Row Harvesting
   - 9.2 Column Harvesting
   - 9.3 N1B0 ISO_EN Mechanism
10. [Overlay Wrapper & Context Switch](#10-overlay-wrapper--context-switch)
11. [Physical Design Notes](#11-physical-design-notes)
    - 11.1 Partitions & Floorplan
    - 11.2 NoC→L1 Side Channel
    - 11.3 Repeater Strategy
    - 11.4 SRAM Inventory
12. [Register Maps](#12-register-maps)
    - 12.1 NOC2AXI Registers
    - 12.2 Tensix NoC Registers
    - 12.3 Overlay/Cluster Control Registers
    - 12.4 EDC BIU Registers
    - 12.5 Address Translation Table
13. [Verification & Testbench Infrastructure](#13-verification--testbench-infrastructure)
    - 13.1 Testbench Overview
    - 13.2 TTX Binary Format
    - 13.3 Performance Test (trinity_performance)
    - 13.4 noc2axi_perf_monitor (N1B0 sim-only)
    - 13.5 axi_dynamic_delay_buffer
14. [N1B0 Silicon Variant — Delta from Baseline](#14-n1b0-silicon-variant--delta-from-baseline)
15. [INT16/FP16B/INT8 LLM Mapping Guide](#15-int16fp16bint8-llm-mapping-guide)
16. [Release History & EDA Versions](#16-release-history--eda-versions)

---

## 1. Trinity Overview

Trinity is a compute SoC integrating a 2-D mesh of AI/ML processing tiles (Tensix NEO clusters), data-movement dispatch engines, and NoC2AXI AXI bridge tiles interconnected by a 256-byte bidirectional Network-on-Chip.

### 1.1 Top-Level Block Diagram

```
                        External AXI Manager/Subordinate ports
                              ↑↑↑↑   ↓↓↓↓
 ┌────────────────────────────────────────────────────────────┐
 │                       TRINITY SoC                          │
 │                                                            │
 │  Y=4  ┌──────────┬───────────────────┬──────────┐         │
 │       │NOC2AXI   │NOC2AXI+ROUTER_OPT │NOC2AXI   │  ← AXI │
 │       │NW_OPT    │  NW_OPT  NE_OPT   │NE_OPT    │         │
 │  Y=3  ├──────────┼────────┬──────────┼──────────┤         │
 │       │DISPATCH_W│ROUTER  │ROUTER    │DISPATCH_E│         │
 │       │(empty N1B0 placeholder)                  │         │
 │  Y=2  ├──────────┼────────┼──────────┼──────────┤         │
 │       │ TENSIX   │ TENSIX │ TENSIX   │ TENSIX   │         │
 │  Y=1  ├──────────┼────────┼──────────┼──────────┤         │
 │       │ TENSIX   │ TENSIX │ TENSIX   │ TENSIX   │         │
 │  Y=0  ├──────────┼────────┼──────────┼──────────┤         │
 │       │ TENSIX   │ TENSIX │ TENSIX   │ TENSIX   │         │
 │       └──────────┴────────┴──────────┴──────────┘         │
 │        X=0       X=1      X=2        X=3                  │
 │                                                            │
 │  EDC Ring: column-by-column serial ring (BIU in NOC2AXI)  │
 │  AON Strip: top/bottom power-always-on domain             │
 └────────────────────────────────────────────────────────────┘
```

### 1.2 Tile Count Summary (N1B0: 4×5 grid)

| Tile Type        | Count | Position              | Function                        |
|------------------|-------|-----------------------|---------------------------------|
| Tensix NEO       | 12    | X=0–3, Y=0–2         | AI/ML compute (MAC + SFPU)      |
| Dispatch Engine  | 2     | X=0 Y=3, X=3 Y=3     | Kernel dispatch + DMA           |
| Router (placeholder) | 2 | X=1 Y=3, X=2 Y=3    | Mesh routing only (N1B0: empty) |
| NOC2AXI_NE_OPT   | 1     | X=3, Y=4             | Corner AXI bridge (east)        |
| NOC2AXI_NW_OPT   | 1     | X=0, Y=4             | Corner AXI bridge (west)        |
| NOC2AXI_ROUTER_NE_OPT | 1 | X=2, Y=4+Y=3        | Composite: AXI + Router (N1B0)  |
| NOC2AXI_ROUTER_NW_OPT | 1 | X=1, Y=4+Y=3        | Composite: AXI + Router (N1B0)  |

### 1.3 Key Parameters (trinity_pkg.sv)

| Constant           | Baseline | N1B0   | Description                     |
|--------------------|----------|--------|---------------------------------|
| `NOC_X_SIZE`       | 4        | 4      | Grid width                      |
| `NOC_Y_SIZE`       | 5        | 5      | Grid height                     |
| `NOC_DATA_WIDTH`   | 256      | 256    | NoC flit data width (bits)      |
| `AXI_DATA_WIDTH`   | 512/64   | 512    | Internal / external AXI width   |
| `L1_SIZE`          | 192 KB   | 768 KB | Per-tile L1 capacity (N1B0 4×)  |
| `NUM_TENSIX`       | 12       | 12     | Compute tiles                   |
| `EDC_NODES_PER_TILE` | ~78   | ~78    | EDC nodes per Tensix tile       |

---

## 2. Grid Architecture & Tile Map

### 2.1 N1B0 EndpointIndex Table

EndpointIndex = X × NOC_Y_SIZE + Y (with NOC_Y_SIZE = 5):

```
         X=0   X=1   X=2   X=3
  Y=4     4     9    14    19   ← NOC2AXI row
  Y=3     3     8    13    18   ← Dispatch/Router row
  Y=2     2     7    12    17   ← Tensix row
  Y=1     1     6    11    16   ← Tensix row
  Y=0     0     5    10    15   ← Tensix row
```

**N1B0 composite tiles:**
- NOC2AXI_ROUTER_NW_OPT: spans EndpointIndex 9 (Y=4) + 8 (Y=3) at X=1
- NOC2AXI_ROUTER_NE_OPT: spans EndpointIndex 14 (Y=4) + 13 (Y=3) at X=2
- Router placeholder X=1,Y=3 (EP=8) and X=2,Y=3 (EP=13): internal to composite; no standalone instantiation

### 2.2 Tile Type Enum (tile_t)

```systemverilog
typedef enum logic [2:0] {
  TILE_TENSIX    = 3'd0,
  TILE_DISPATCH  = 3'd1,
  TILE_ROUTER    = 3'd2,
  TILE_NOC2AXI   = 3'd3,
  TILE_NOC2AXI_ROUTER = 3'd4,   // N1B0 composite
  TILE_EMPTY     = 3'd7
} tile_t;
```

### 2.3 NoC Mesh Connectivity

Each tile has 4 cardinal NoC ports (North/South/East/West). The 256-bit bidirectional ring carries full-width 32-byte flits. X-axis wires between columns use explicit repeater stages in N1B0:

```
Repeater stages (N1B0):
  Y=4: 4 stages east↔west (between X=1↔2, X=2↔3, X=0↔1)
  Y=3: 6 stages east↔west
  Y=0-2: direct wire assign (no repeaters)
```

---

## 3. Clock & Reset Architecture

### 3.1 Clock Domains

| Clock     | Range           | Domain Name | Modules                                   |
|-----------|-----------------|-------------|-------------------------------------------|
| `ai_clk`  | 1.0–1.5 GHz     | AICLK       | Tensix math, SRCA, SRCB, DEST, L1, TRISC |
| `noc_clk` | 1.0–1.5 GHz     | NOCCLK      | NoC fabric, VC buffers, router            |
| `dm_clk`  | 1.5–2.2 GHz     | DMCLK       | Data movement CPUs (FDS FSM), dispatch    |
| `axi_clk` | 0.75–1.5 GHz    | AXICLK      | External AXI interface                    |
| `ref_clk` | fixed           | REFCLK      | EDC ring, PLL reference                   |
| `aon_clk` | always-on       | AONCLK      | Power-good, AON strip logic               |

### 3.2 N1B0 Per-Column Clock Distribution

N1B0 introduces per-column `i_ai_clk[3:0]` and `i_dm_clk[3:0]` arrays instead of a single global input:

```
trinity.sv top ports (N1B0):
  input  logic [NOC_X_SIZE-1:0]  i_ai_clk    // [3:0] one per column
  input  logic [NOC_X_SIZE-1:0]  i_dm_clk    // [3:0] one per column
  input  logic                   i_noc_clk   // global single clock

Clock routing struct per tile (trinity_clock_routing_t):
  {ai_clk, noc_clk, dm_clk, ai_reset_n, noc_reset_n, dm_reset_n,
   edc_reset_n, power_good, iso_en}  // 9 fields

Propagation: clock_routing_in[x][y] → tile → clock_routing_out[x][y-1]
  NOC2AXI_ROUTER_OPT (Y=4): drives clock_routing_out[x][3] for Y=3 row
```

### 3.3 Clock Routing — NOC Partition as Hub (v0.8+)

```
i_noc_clk → NOC partition hub
             ├── Direct to router VC buffers
             └── o_noc_clk_feedthrough_to_l1 → L1 partition (abutment, no buffer)
```

### 3.4 Reset Signals

| Reset Signal            | Scope                         | Notes                          |
|-------------------------|-------------------------------|--------------------------------|
| `i_noc_reset_n`         | All NoC logic                 | Common NoC reset               |
| `i_ai_reset_n`          | L1 + Tensix shared logic      | Combined reset                 |
| `i_edc_reset_n`         | EDC ring                      | Power-good signal equivalent   |
| `i_tensix_reset_n[11:0]`| Individual Tensix cores       | Per-tile: bit[3×col+row]       |
| `i_dm_core_reset_n`     | DM CPU core logic             | FDS runtime reset              |
| `i_dm_uncore_reset_n`   | DM uncore/bus                 | Bus matrix reset               |

**Reset sequencing recommendation:**
1. Assert all resets low simultaneously
2. Release `i_noc_reset_n` first
3. Release `i_ai_reset_n` after NoC stable
4. Release `i_tensix_reset_n[*]` per tile as needed
5. `i_edc_reset_n` released after all power domains stable

### 3.5 PRTN Chain (N1B0)

N1B0 adds a daisy-chain partition retention (PRTN) signal per column:

```
PRTN propagation per column X:
  prtn_in[X][2] → Tensix Y=2 → prtn_out → prtn_in[X][1]
                → Tensix Y=1 → prtn_out → prtn_in[X][0]
                → Tensix Y=0 → prtn_out (tail)
```

---

## 4. Tensix NEO Cluster

The Tensix NEO cluster is the primary AI/ML compute element. Each cluster contains 4 sub-cores (T0–T3) sharing an L1 memory.

### 4.1 Tensix NEO Cluster Architecture

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                    TENSIX NEO CLUSTER                            │
 │                                                                  │
 │  ┌─────────────────────────────────────────────────────────────┐ │
 │  │ OVERLAY (Data Movement CPUs: 8×64b RISC-V dm_cores)         │ │
 │  │  Context Switch | NoC Copy Cmd | Pattern Addr Gen | Shuffle  │ │
 │  └────────────────────────────┬────────────────────────────────┘ │
 │                               │ instructions                     │
 │  ┌────────────────────────────▼────────────────────────────────┐ │
 │  │ INSTRUCTION ENGINE (per sub-core T0-T3)                     │ │
 │  │  TRISC0 (unpacker)  TRISC1 (math)  TRISC2 (packer)         │ │
 │  │  MOP Decoder  |  Replay Unit  |  BRISC (kernel init)        │ │
 │  └──────┬───────────────────────────────────────┬─────────────┘ │
 │         │ SRCA/SRCB                              │ results       │
 │  ┌──────▼──────────────────────────────────────▼─────────────┐  │
 │  │                    FPU (G-TILE)                            │  │
 │  │  G-Tile[0] ┌─M-Tile×4─┐   G-Tile[1] ┌─M-Tile×4─┐       │  │
 │  │            │FP_LANE×8 │              │FP_LANE×8 │       │  │
 │  │            │DEST[0..7]│              │DEST[8..15]│       │  │
 │  │            └──────────┘              └──────────┘       │  │
 │  │  SFPU (vector activations, exp, sqrt, gelu, etc.)         │  │
 │  └──────────────────────────────────────────────────────────┘  │
 │                               │                                  │
 │  ┌────────────────────────────▼────────────────────────────────┐ │
 │  │ TDMA (Tiled DMA)                                            │ │
 │  │  Unpackers × 2  (src A/B → SRCA/SRCB, format convert)      │ │
 │  │  Packers   × 1  (DEST → L1, activation/compress)           │ │
 │  └────────────────────────────┬────────────────────────────────┘ │
 │                               │ 512-bit bus                      │
 │  ┌────────────────────────────▼────────────────────────────────┐ │
 │  │ L1 MEMORY (shared by all sub-cores)                         │ │
 │  │  N1B0: 768 KB  (16 banks × 3072×128-bit)                   │ │
 │  │  Baseline: 192 KB (16 banks × 768×128-bit)                  │ │
 │  │  SECDED ECC @ 128-bit, Atomic ops, addr 0x0000_0000–0x2F_FFFF│ │
 │  └─────────────────────────────────────────────────────────────┘ │
 │                               ↕                                  │
 │  ┌────────────────────────────▼────────────────────────────────┐ │
 │  │ NoC ROUTER  (mesh connectivity, 256-bit flit)               │ │
 │  └─────────────────────────────────────────────────────────────┘ │
 └──────────────────────────────────────────────────────────────────┘
```

### 4.2 FPU — G-Tile / M-Tile Architecture

The FPU implements matrix multiplication via two G-Tiles, each containing 8 M-Tiles and 8 DEST latch-array sub-banks.

```
G-Tile Structure (×2 per cluster):
  G-Tile
  ├── M-Tile[0..7]  (8 multiplier-array tiles)
  │    Each M-Tile:
  │      ├── FP_LANE[0..7] (8 parallel FP multiply paths)
  │      │    Each FP_LANE:
  │      │      ├── fp_mul_raw  (Booth radix-4 mantissa multiply)
  │      │      ├── exp_path    (exponent add + bias)
  │      │      ├── align       (barrel shifter, 4-stage FP16)
  │      │      ├── compress    (Wallace 4:2 tree)
  │      │      └── add         (carry-propagate adder + stochastic rounding)
  │      └── Feeds DEST sub-bank[tile_idx]
  └── SRCA broadcast bus → all M-Tiles
```

**Pipeline stages per MAC:**
1. `mul` — Mantissa multiply + exponent add (8 M-Tiles parallel)
2. `exp_max` — Tree-reduce to find max exponent across M-Tiles
3. `align` — Barrel shift to align mantissas
4. `compress` — Wallace tree 4:2 reduction
5. `add` — Final carry-propagate add + optional stochastic rounding output

**Total MAC parallelism per cluster:**
- 2 G-Tiles × 8 M-Tiles × 8 FP_Lanes = **128 multipliers**
- With pipelining: 256–8192 MACs/cycle depending on data format (see §4.7)

### 4.3 Instruction Engine — TRISC/BRISC

Each of the 4 sub-cores (T0–T3) has its own Instruction Engine:

| Core   | Role                  | Notes                                   |
|--------|-----------------------|-----------------------------------------|
| BRISC  | Kernel initialization | RISC-V; initializes sub-cores, sets up TDMA |
| TRISC0 | Unpack control        | Programs TDMA unpackers (src A/B)        |
| TRISC1 | Math control          | Issues FPU commands (MOP loops)          |
| TRISC2 | Pack control          | Programs TDMA packers (DEST → L1)        |

**MOP Decoder (loop accelerator):**
Converts high-level matrix operation (MOP) instructions into streams of FPU microops. Reduces TRISC1 instruction bandwidth for long K_tile loops.

**Replay Unit:**
Re-issues FPU instruction sequences without TRISC1 involvement for pipelined tiling.

**TRISC Memory Map (local RISC-V perspective):**

| Address Range         | Region              |
|-----------------------|---------------------|
| `0x0000_0000–0x007F_FFFF` | L1 (8 MB window)  |
| `0x0080_0000–0x0080_A0E3` | Local debug regs   |
| `0x0080_0000–0x0080_03A3` | TRISC debug regs   |
| `0x0184_0000–0x0184_10FF` | Global Tensix regs |

**TRISC Debug Registers (external NoC access):**

| Address (NoC)          | Region                     |
|------------------------|----------------------------|
| `0x0000_0000–0x007F_FFFF` | tensix_l1 (8 MB)         |
| `0x0180_0000–0x0180_03A3` | neo_regs[0] — Tensix T0  |
| `0x0181_0000–0x0181_03A3` | neo_regs[1] — Tensix T1  |
| `0x0182_0000–0x0182_03A3` | neo_regs[2] — Tensix T2  |
| `0x0183_0000–0x0183_03A3` | neo_regs[3] — Tensix T3  |
| `0x0184_0000–0x0184_10FF` | tensix_global_regs         |

Address translation: external = local_offset + `0x0180_0000` + (Tensix_idx × `0x1_0000`)

### 4.4 TDMA (Tiled DMA)

The TDMA engine moves data between L1 and the FPU register files:

**Unpackers (×2, one each for SrcA and SrcB):**
- DMA from L1 → SRCA/SRCB register file
- On-the-fly format conversion (e.g., INT8→INT16, FP8→FP16)
- Transpose support
- Bank initialization (zeroing accumulator banks)

**Packers (×1):**
- DMA from DEST register file → L1
- Format conversion during pack (e.g., FP32→FP16, INT32→INT8)
- Activation functions: ReLU, CReLU applied inline

### 4.5 SFPU (Special Function Processing Unit)

The SFPU performs per-element vector operations on DEST register file values:

- **Transcendentals:** exp, log, sqrt, rsqrt, recip
- **Activations:** gelu, silu, tanh, sigmoid, softmax (partial)
- **Misc:** abs, clamp, LReLU, dropout (stochastic)
- **Data format:** Operates on FP16/FP32 elements in DEST
- **SFPU overhead (INT16 path):** +2 L1 round-trips for inv-sqrt and exp computation

### 4.6 L1 Memory

| Parameter     | Baseline     | N1B0         |
|---------------|--------------|--------------|
| Capacity      | 192 KB/tile  | 768 KB/tile  |
| Total (12 tiles) | 2.304 MB | 9.216 MB     |
| Banks         | 16           | 16           |
| Bank depth    | 768 rows     | 3072 rows    |
| Bank width    | 128 bits     | 128 bits     |
| ECC           | SECDED @ 128b | SECDED @ 128b |
| Atomic ops    | Yes          | Yes          |
| Address range | `0x0000_0000–0x002F_FFFF` | `0x0000_0000–0x00BF_FFFF` |
| NoC access    | 256-bit/cycle read/write | same |

**L1 clients and arbitration:**

| Client     | Port Width | Clock   | Priority |
|------------|-----------|---------|----------|
| TDMA (unpack) | 256-bit | AICLK  | High      |
| TDMA (pack)   | 256-bit | AICLK  | High      |
| NoC (write)   | 512-bit | NOCCLK | Medium    |
| Overlay (DM)  | 256-bit | DMCLK  | Low       |
| T6 cores (4)  | 64-bit each | AICLK | Low     |

**NoC→L1 write path:** 512-bit wide; CDC FIFO (NOCCLK write / AICLK read), 8 entries deep. Routes on left-edge channel ~82 µm wide (M3+ layers, no cells in M1/M2 under channel).

### 4.7 Register Files (DEST / SRCA / SRCB)

**DEST Register File (accumulator):**

| Mode   | Rows | Element Width | Total Size |
|--------|------|---------------|-----------|
| FP32 / INT32 | 512 | 32-bit | 32 KB    |
| FP16B / FP16A | 1024 (packed 2 per word) | 16-bit | 32 KB |
| FP8 / INT8  | 1024 | 8-bit (2/word)  | 16 KB    |

- 12,288 latch-array cells total across all tiles
- 2 DEST halves (double-buffered): DEST[0..7] and DEST[8..15] in two G-Tiles

**SRCA Register File:**
- 2048 rows × 16 columns × 16 bits = 64 KB
- Double-banked (ping-pong)
- Max K_tile = 48 rows (hardware constraint per MOP pass)
- Latch-array cells: 1,536 total

**SRCB Register File:**
- 2048 rows, same organization as SRCA
- Shared across G-Tile pair (broadcast)
- Located in Instruction Engine above FPU

### 4.8 Data Formats & MAC Throughput

**Supported Data Formats:**

| Format   | Code | Exp | Man | Notes                          |
|----------|------|-----|-----|-------------------------------|
| FP32     | 0x0  | 8   | 23  | IEEE 754 single                |
| FP16A    | 0x1  | 5   | 10  | IEEE half-precision            |
| FP16B    | 0x5  | 8   | 7   | BF16 (recommended)             |
| TF32     | 0x4  | 8   | 10  | TensorFloat-32                 |
| FP8R     | 0x2  | 4   | 3   | FP8 round-to-nearest           |
| FP8P     | 0x3  | 4   | 3   | FP8 round-to-plus              |
| MXFP8    | —    | —   | —   | Microscaling FP8               |
| INT8     | 0xe  | —   | —   | 8-bit signed integer           |
| UINT8    | 0xf  | —   | —   | 8-bit unsigned integer         |
| INT16    | 0x9  | —   | —   | 16-bit signed integer          |
| INT32    | 0x8  | —   | —   | 32-bit integer accumulator     |
| INT4     | 0xd  | —   | —   | 4-bit integer (packed)         |

**MAC Throughput per Tensix NEO cluster:**

| Data Format     | Hi-Fi (MACs/cycle) | Lo-Fi (MACs/cycle) |
|-----------------|--------------------|--------------------|
| FP32            | —                  | —                  |
| TF32            | 512                | 2048               |
| Float16 (FP16A) | 512                | 2048               |
| Float16B (BF16) | **1024**           | 2048               |
| FP8R/P          | 2048               | —                  |
| MXFP8 variants  | 2048               | —                  |
| MXINT variants  | 2048               | —                  |
| INT8 / UINT8    | **8192**           | 8192               |

> Hi-Fi = highest accuracy; Lo-Fi = reduced precision mode for throughput

---

## 5. Dispatch Engine

The Dispatch Engine (DE) resides at Y=3, X=0 (west) and X=3 (east). It provides kernel scheduling and DMA for Tensix clusters.

### 5.1 Dispatch Engine Components

```
 ┌──────────────────────────────────────────────────────┐
 │              DISPATCH ENGINE                         │
 │                                                      │
 │  ┌──────────────────────────────────────────────┐   │
 │  │ OVERLAY (Data Movement CPUs: 8× dm_cores)    │   │
 │  │  FDS (Fast Dispatch Scheduler FSM)           │   │
 │  └──────────────────┬───────────────────────────┘   │
 │                     │                               │
 │  ┌──────────────────▼───────────────────────────┐   │
 │  │ L1 Memory (dispatch)                         │   │
 │  │  Clock: i_noc_clk (NOT ai_clk)              │   │
 │  │  128 macros per tile                         │   │
 │  └──────────────────────────────────────────────┘   │
 │                     │                               │
 │  ┌──────────────────▼───────────────────────────┐   │
 │  │ NoC Router (East & West variants)            │   │
 │  │  tt_trin_disp_eng_noc_niu_router_west/east   │   │
 │  └──────────────────────────────────────────────┘   │
 └──────────────────────────────────────────────────────┘
```

### 5.2 Dispatch Engine Clock Note

The Dispatch L1 runs on `i_noc_clk` (not `ai_clk`). This differs from Tensix tiles and requires special CDC handling for data movement between dispatch and Tensix L1.

### 5.3 Dispatch Engine Feedthrough

Horizontal data channels exist for kernel distribution:
- `de_to_t6[x]`: dispatch → Tensix kernel push
- `t6_to_de[x]`: Tensix → dispatch completion feedback

In N1B0, the NOC2AXI_ROUTER_OPT composite tiles carry east/west feedthroughs internally.

---

## 6. NoC Fabric & Router

### 6.1 Flit & Address Encoding

Each NoC flit is 256 bits wide. The header contains routing and endpoint information:

**noc_header_address_t bit-map (56 bits for AXI gasket):**

```
Bits [55:52]  flit_type  [2:0] + reserved
Bits [51:46]  x_coord    [5:0]   destination X
Bits [45:40]  y_coord    [5:0]   destination Y
Bits [39:34]  src_x      [5:0]   source X
Bits [33:28]  src_y      [5:0]   source Y
Bits [27:24]  vc_id      [3:0]   virtual channel
Bits [23:0]   addr_lo    [23:0]  lower address bits
```

**Full 96-bit target address:**
- `TARG_ADDR_LO[31:0]` — lowest 32 bits
- `TARG_ADDR_MID[31:0]` — middle 32 bits
- `TARG_ADDR_HI[31:0]` — highest 32 bits

**AXI gasket 56-bit address layout (RTL-verified):**

```
[55:52] reserved (4 bits)
[51:32] address[39:20] (20 bits, upper)
[31:28] VC / routing flags
[27:0]  address[19:0] (lower 20 bits + AxUSER)
```

### 6.2 Flit Types

```
flit_type[2:0]:
  3'b000 = Normal data flit
  3'b001 = Header flit
  3'b010 = Path squash flit
  3'b011 = Dynamic routing flit (928-bit carried list appended)
  3'b100 = Atomic operation
  3'b101–3'b111 = Reserved
```

**Path squash flit:** Used to abort an in-progress path reservation (tendril routing). Sent upstream to release held VC resources.

### 6.3 Routing Modes

| Mode             | Description                                          | When Used               |
|------------------|------------------------------------------------------|-------------------------|
| DOR X→Y          | Dimension-order routing, X-first then Y             | Default unicast          |
| DOR Y→X          | Y-first then X                                       | VC_DIM_ORDER register    |
| Tendril          | Source-routed path via path bits in header           | Long-distance           |
| Dynamic          | Per-hop routing table lookup; 928-bit carried list   | Congestion avoidance     |
| Broadcast        | Multicast to row/column mask                         | Param broadcast         |

**Dynamic routing 928-bit carried list structure:**
- 29 entries × 32 bits = 928 bits
- Each entry: x[5:0], y[5:0], vc[3:0], force_dim[1:0] + reserved
- Each router reads its slot, decides next hop, NIU overwrites with return path
- `force_dim` overrides DOR direction

**Routing mode priority:**
1. Path squash (highest)
2. Dynamic routing (if `en_dynamic_routing` set in ATT)
3. Tendril (if path bits nonzero)
4. DOR (default)

**Orientation table (NOC_ORIENT_* values):**

| NOC_ORIENT | X rot | Y rot | Usage                    |
|------------|-------|-------|--------------------------|
| 0 (default) | +X→E | +Y→N | Standard orientation     |
| 1           | +X→N | +Y→W | 90° CCW                  |
| 2           | +X→W | +Y→S | 180°                     |
| 3           | +X→S | +Y→E | 90° CW                   |
| 4–7         | Mirrored variants | —  | Non-standard             |

### 6.4 Virtual Channels

| VC Range  | Type      | Notes                               |
|-----------|-----------|-------------------------------------|
| VC 0–11   | Unicast   | Standard point-to-point traffic     |
| VC 12–15  | Broadcast | Multicast/row-column broadcast      |

VC routing order configurable per-VC via `VC_DIM_ORDER` register (0xAAAAAAAA default = all X→Y).

### 6.5 ATT (Address Translation Table)

The ATT translates incoming AXI addresses to NoC destination (x,y) + endpoint ID.

**ATT organization:**
- 16 mask table entries (MASK_TABLE_ENTRY_0–15)
- 16 endpoint entries (MASK_TABLE_EP_LO/HI)
- 16 BAR entries (MASK_TABLE_BAR_LO/HI)
- 1024 endpoint entries (ENDPOINT_TABLE_ENTRY_0–1023)
- 32 dynamic routing match entries (ROUTING_TABLE_MATCH_0–31)
- 32 dynamic routing part entries (ROUTING_TABLE_PART_ENTRY_0–31)

**ATT lookup flow:**
```
Incoming AXI address
  → Test each MASK_TABLE_ENTRY[i]:
      masked_addr = addr & mask[5:0]
      if masked_addr matches ep_id_idx → hit
  → Apply BAR translation: translated_addr = addr - BAR + ENDPOINT_BASE
  → Look up ENDPOINT_TABLE for (x,y) coordinates
  → Assemble NoC flit header
```

**Enable registers:**
- `ENABLE_TABLES[0]` = en_address_translation
- `ENABLE_TABLES[1]` = en_dynamic_routing

### 6.6 Security Fence (SMN)

8 programmable address ranges with per-range security levels:

| Register                   | Function                              |
|----------------------------|---------------------------------------|
| `SEC_FENCE_RANGE_0–7_START/END` | 64-bit address range boundaries  |
| `SEC_FENCE_ATTRIBUTE_0–7`  | RANGE_ENABLE[8], RD_SEC[7:4], WR_SEC[3:0] |
| `SEC_FENCE_MASTER_LEVEL`   | Master security level [3:0]           |
| `SEC_FENCE_VIOLATION_FIFO` | Logs violations (readable by SW)      |

Security rules:
- Transaction blocked if master_level < range required level
- Violations logged to FIFO; interrupt optionally generated
- 4 invalid-access fence ranges additionally available (INVALID_FENCE_*)

---

## 7. NoC2AXI Interface (NIU)

### 7.1 NIU Overview

The NIU (Network Interface Unit) bridges between the 256-bit NoC and external 512-bit AXI4 interconnect.

**Trinity has 3 baseline NIU variants:**
- `trinity_noc2axi_n_opt` — North-facing (row Y=4, center)
- `trinity_noc2axi_ne_opt` — Northeast corner (X=3, Y=4)
- `trinity_noc2axi_nw_opt` — Northwest corner (X=0, Y=4)

**N1B0 adds 2 composite variants (see §7.2).**

### 7.2 NIU AXI Interfaces

| Interface        | Direction | Width | Description                      |
|------------------|-----------|-------|----------------------------------|
| AXI Subordinate  | In        | 512b  | Host → NoC (write/read commands) |
| AXI Manager      | Out       | 512b  | NoC → external memory (data)     |
| APB Config       | In        | 32b   | Register access (ATT, security)  |
| NoC flits        | Bidirec.  | 256b  | East/West/South (corner: 2 dirs) |

**AXI→NoC path:**
- AWADDR/ARADDR decoded by ATT → NoC (x,y) + VC + endpoint
- Data buffered in MST_WR/RD memory
- Timeout tracked per transaction (CNT_POSTED_TIME_OUT_LIMIT)

**Outbound AXI AxUSER bits** encode security level and transaction type.

### 7.3 N1B0 NOC2AXI_ROUTER_OPT Composite Tile

N1B0 replaces separate NOC2AXI + standalone router tiles at X=1,2 with dual-row composite modules:

```
NOC2AXI_ROUTER_NE_OPT (X=2):
  Y=4 sub-module: trinity_noc2axi_n_opt (AXI bridge)
  Y=3 sub-module: trinity_router (mesh router)

  Internal cross-row wires:
    noc2axi.south_out → router.north_in  (flit flow downward)
    router.north_out  → noc2axi.south_in (flit flow upward)

  Clock chain:
    noc2axi_o_ai_clk → router_i_ai_clk (clock pass through Y=4→Y=3)
    router_o_ai_clk  → clock_routing_out[2][3] (drives Tensix Y=2 column 2)

  EDC chain:
    Forward:  noc2axi_edc_egress → router_edc_ingress
    Loopback: router_edc_loopback_egress → noc2axi_edc_loopback_ingress
    External EDC ports exported at Y=3 boundary
```

**NOC2AXI_ROUTER_OPT key parameters:**

| Parameter              | Value | Purpose                               |
|------------------------|-------|---------------------------------------|
| REP_DEPTH_LOOPBACK     | 6     | Loopback register-slice (N1B0 timing) |
| REP_DEPTH_OUTPUT       | 4     | Output register-slice depth           |
| NUM_REPEATERS_W_IN/OUT | 4     | Inter-column West repeater stages     |
| NUM_REPEATERS_S_IN/OUT | 5     | South-to-Y=2 Tensix repeater stages   |

**Node ID offsets in composite:**
- NOC2AXI sub-module (Y=4): nodeid_y = actual_y (= 4)
- Router sub-module (Y=3): nodeid_y = actual_y − 1 (= 3; offset −1)
- EndpointIndex similarly shifted: NE composite = EP 14 (Y=4) + EP 13 (Y=3)

**RDATA FIFO depth (configurable via `define):**

| Define                | Depth |
|-----------------------|-------|
| RDATA_FIFO_32         | 32    |
| RDATA_FIFO_64         | 64    |
| RDATA_FIFO_128        | 128   |
| RDATA_FIFO_256        | 256   |
| RDATA_FIFO_512        | 512 (default) |
| RDATA_FIFO_1024       | 1024  |

---

## 8. EDC System

### 8.1 EDC1 Ring Protocol Overview

The Error Detection and Correction (EDC) system forms a serial ring per column, connecting all tiles for configuration, error reporting, and harvest control.

```
BIU (in NOC2AXI, Y=4)
  ↓ ring_egress
Dispatch (Y=3) or NOC2AXI_ROUTER_OPT composite (N1B0)
  ↓
Tensix Y=2
  ↓
Tensix Y=1
  ↓
Tensix Y=0
  ↑ ring_loopback
BIU (receives loopback)
```

**Ring signals per link:**
- `req_tgl` — toggle handshake (request)
- `ack_tgl` — toggle handshake (acknowledge)
- `data[7:0]` — 8-bit serial payload
- `parity` — odd parity over data
- `sideband[1:0]` — packet type/framing

### 8.2 EDC Node ID Structure

**16-bit Node ID encoding:**

```
[15:11]  block_id[4:0]  = 5'b1_1110 (0x1E for all tiles)
[10:8]   y_coord[2:0]   = tile row (0–4)
[7:0]    local_id[7:0]  = node function within tile
```

**Standard local IDs:**

| local_id | Node function                            |
|----------|------------------------------------------|
| 0xC0     | Configuration node (harvest registers)   |
| 0x80     | L1 ECC node                              |
| 0x40–0x7F| Sub-core specific (T0–T3)               |
| 0x00–0x3F| NoC / router nodes                       |

**Pre-computed node IDs by tile row:**

| Tile             | Node ID  |
|------------------|----------|
| NOC2AXI (Y=4)    | 0xF4C0   |
| Dispatch (Y=3)   | 0xF3C0   |
| Tensix row 2 (Y=2) | 0xF2C0 |
| Tensix row 1 (Y=1) | 0xF1C0 |
| Tensix row 0 (Y=0) | 0xF0C0 |
| Broadcast (all)  | 0xFFFF   |

### 8.3 Ring Traversal Order

**Per Tensix tile segment (ring order within tile):**
1. NOC subsegment: sec_conf → VC_buf_N → VC_buf_E → VC_buf_S → VC_buf_W → NIU
2. L1 partition: T6_MISC → L1W2 ECC nodes
3. Sub-core T0: IE → SRCB → UNPACK → PACK → SFPU → GPR → CFG → THCON (13 nodes)
4. Sub-core T1: (same 13 nodes)
5. Sub-core T2: (same 13 nodes)
6. Sub-core T3: (same 13 nodes)
7. FPU: G-Tile[0] → G-Tile[1] nodes
8. Overlay EDC loopback node

**N1B0 composite tile EDC chain:**

```
NOC2AXI_ROUTER_OPT internal EDC:
  NOC2AXI (Y=4) nodes → forward link → Router (Y=3) nodes
  Router (Y=3) loopback → NOC2AXI (Y=4) loopback
  External ring ports exported at Y=3 (not Y=4)
```

### 8.4 EDC Timing Closure (Pipe Stages & Synchronizers)

All parameters are compile-time on each `tt_edc1_node` instance:

**Problem → Solution quick reference:**

| Problem                          | Parameter              | Effect                                     |
|----------------------------------|------------------------|--------------------------------------------|
| Event/capture path critical      | EVENT_PIPE_STAGES      | Flop pipeline on i_event + i_capture into node |
| Config/pulse output path critical| CONTROL_PIPE_STAGES    | Flop pipeline on o_config + o_pulse out     |
| Long serial link between nodes   | INGRESS_PIPE_STAGES    | Flops on incoming serial bus signals        |
| Long serial link between nodes   | EGRESS_PIPE_STAGES     | Flops on outgoing serial bus signals        |
| CDC boundary or very long req/ack| ENABLE_INGRESS_SYNC    | Synchronizer on incoming req_tgl            |
| CDC boundary or very long req/ack| ENABLE_EGRESS_SYNC     | Synchronizer on incoming ack_tgl            |

**Port functions:**

| Port          | Direction | Description                                       |
|---------------|-----------|---------------------------------------------------|
| `ingress_intf`| In        | Incoming ring traffic (add INGRESS_PIPE_STAGES here) |
| `egress_intf` | Out       | Outgoing ring traffic (add EGRESS_PIPE_STAGES here)  |
| `i_event`     | In        | Pulse triggers → ring packet to BIU               |
| `i_capture`   | In        | Payload captured when event fires                 |
| `o_pulse`     | Out       | SW-triggered one-shot pulses (from BIU writes)    |
| `o_config`    | Out       | Level controls (config register outputs)          |

**Synchronizer notes:**
- Synchronizers sit on req/ack toggle signals ONLY (not data/parity)
- For CDC: enable both INGRESS_SYNC (req side) and EGRESS_SYNC (ack side)

**Example instantiation:**
```systemverilog
tt_edc1_node #(
  .INGRESS_PIPE_STAGES (1),
  .EGRESS_PIPE_STAGES  (0),
  .EVENT_PIPE_STAGES   (1),
  .CONTROL_PIPE_STAGES (0),
  .ENABLE_INGRESS_SYNC (1),
  .ENABLE_EGRESS_SYNC  (1)
) u_edc1_node (...);
```

**MCPDLY derivation (P&R guide):**
- MCPDLY = 7 = 3 repeater stages + 3-stage synchronizer + 1 setup margin
- SDC: `set_multicycle_path -setup 2 -hold 1` on toggle req/ack lines

### 8.5 BIU (Bus Interface Unit) Registers

The BIU resides in each NOC2AXI tile and is the EDC ring master controller.

**EDC BIU Register Map (base: per-tile EDC APB offset):**

| Register         | Offset | Access | Reset  | Description                                       |
|------------------|--------|--------|--------|---------------------------------------------------|
| EDC_BIU_ID       | 0x00   | RO     | 0x0    | EDC_VERSION[31:16], EDC_BIU_ID[7:0]              |
| EDC_BIU_STAT     | 0x04   | RW     | 0x0    | FATAL_ERR[18], CRIT_ERR[17], COR_ERR[16], REQ_PKT_SENT[8], RSP_PKT_RCVD[0] |
| EDC_BIU_CTRL     | 0x08   | RW     | 0x0    | INIT[31] (clears all ring nodes), RSVD[0]         |
| EDC_BIU_IRQ_EN   | 0x0C   | RW     | 0x0    | FATAL_ERR_IEN[11], CRIT_ERR_IEN[10], COR_ERR_IEN[9], REQ_PKT_SENT_IEN[4], RSP_PKT_RCVD_IEN[0] |
| EDC_BIU_RSP_HDR0 | 0x10   | RW     | 0x0    | TGT_ID[31:16], CMD[15:12], PYLD_LEN[11:8], CMD_OPT[7:0] |
| EDC_BIU_RSP_HDR1 | 0x14   | RW     | 0x0    | DATA1[31:24], DATA0[23:16], SRC_ID[15:0]          |
| EDC_BIU_RSP_DATA[0–3] | 0x18–0x24 | RW | 0x0 | Response data (4 × 32-bit)                     |
| EDC_BIU_REQ_HDR0 | 0x28   | RW     | 0x0    | Same format as RSP_HDR0                           |
| EDC_BIU_REQ_HDR1 | 0x2C   | RW     | 0x0    | Same format as RSP_HDR1                           |
| EDC_BIU_REQ_DATA[0–3] | 0x30–0x3C | RW | 0x0 | Request data (4 × 32-bit)                      |

**Status bits:**

| Bit       | Name          | Description                              |
|-----------|---------------|------------------------------------------|
| [18]      | FATAL_ERR     | Internal EDC ring error                  |
| [17]      | CRIT_ERR      | Uncorrectable data error detected        |
| [16]      | COR_ERR       | Correctable data error detected          |
| [8]       | REQ_PKT_SENT  | Request packet written to REQ CSRs sent  |
| [0]       | RSP_PKT_RCVD  | Response packet ready to read            |

**Payload length encoding:** value 0–15 maps to 1–16 bytes.

**BIU interrupt monitoring (v0.10+):**
- Monitors: REQ_PKT_SENT, RSP_PKT_RCVD, COR_ERR, LAT_ERR, UNC_ERR, OVERFLOW, FATAL_ERR
- Control env: `BIU_CHECKING` (enable/disable globally)
- Per-test: `set_biu_checking_disabled()`
- EDC utility: `tests/utils/edc_util.py`

### 8.6 EDC Node Instance Inventory

**Total EDC instances across Trinity: 5,586**

| Subsystem               | Instance Count | Pattern Types |
|-------------------------|----------------|---------------|
| Tensix tiles (×12)      | 5,172          | 47 patterns   |
| Dispatch engine west    | 159            | 27 patterns   |
| Dispatch engine east    | 159            | 27 patterns   |
| NOC2AXI_n_opt           | 36             | 18 patterns   |
| NOC2AXI_ne_opt          | 15             | 15 patterns   |
| NOC2AXI_nw_opt          | 15             | 15 patterns   |
| Router (standalone)     | 30             | 15 patterns   |

**Instance path categories per Tensix tile:**
- Overlay wrapper: EDC APB bridge + EDC wrapper
- Memory wrapper: L1 SRAM EDC wrappers (per bank), L2 banks, directory
- Instruction engine: TRISC caches, SRCB, CFG/THCON, SFPU
- Router: VC buffer EDC wrappers (E/W/N/S/NIU)
- T6 core EDC: FPU G-Tile, M-Tile, latch-array nodes

---

## 9. Harvest Architecture

Harvesting is a yield-recovery mechanism that disables faulty tiles while maintaining system functionality through mesh reconfiguration.

### 9.1 Row Harvesting

**Non-harvestable components (must-yield blocks):**
- NoC router and repeaters
- EDC network itself
- Logic required to configure NEO cluster
- Output control logic

**When a NEO cluster is harvested:**
- Overlay block becomes unavailable
- L1 memory becomes unavailable
- All 4 Tensix sub-cores become unavailable
- NoC mesh remains operational (routing continues through tile)

**5 baseline harvest mechanisms:**

| # | Mechanism       | Description                                      |
|---|-----------------|--------------------------------------------------|
| 1 | mesh_start      | Y-coordinate origin remapping for NoC routing    |
| 2 | dynamic_routing | NoC skips harvested row via routing table        |
| 3 | reset_isolation | Harvested tile held in reset                     |
| 4 | edc_bypass      | EDC ring bypass wire routes around harvested tile|
| 5 | noc_y_size      | NOC_Y_SIZE register decremented to hide row     |

**Configuration requirement:** All harvest registers must be programmed via EDC ring BEFORE normal NoC traffic begins.

**Harvest sequence:**
1. Program EDC configuration node of each tile (via BIU INIT)
2. Set mesh_start to first valid row
3. Program dynamic routing table to skip harvested rows
4. Enable reset isolation (power-gate or hold in reset)
5. Configure EDC bypass wire routing
6. Update NOC_Y_SIZE in all NIU NODE_ID registers

### 9.2 Column Harvesting

Column harvesting disables a full X column. Added in Rev 1.4 of harvest guide.

**Additional steps for column harvest:**
- Update NOC_X_SIZE in all NIU NODE_ID registers
- Program broadcast exclusion masks (BRCST_EXCLUDE)
- Reconfigure ATT endpoint table to remove harvested column entries
- EDC ring: bypass entire column segment

### 9.3 N1B0 ISO_EN Mechanism (6th Mechanism)

N1B0 adds a 6th harvest mechanism: `ISO_EN[11:0]` isolation enable signals.

**ISO_EN bit map:**

```
ISO_EN[11:0] — 2 bits per column × 6 column positions
  Bit [2×x + 0]: Dispatch isolation at column x
  Bit [2×x + 1]: Router isolation at column x

  ISO_EN[1:0]  → column X=0 (Dispatch)
  ISO_EN[3:2]  → column X=1 (Router/composite Y=3)
  ISO_EN[5:4]  → column X=2 (Router/composite Y=3)
  ISO_EN[7:6]  → column X=3 (Dispatch)
  ISO_EN[11:8] → additional composite tile isolation
```

**ISO_EN behavior:**
- Assertion isolates the tile from data lines (AND-gate all outputs to 0)
- Clock chain in composite tiles passes through even when ISO_EN asserted
- Required for harvest of composite NOC2AXI_ROUTER_OPT tiles

**Physical implementation:**
- 11 signal groups use AND-type isolation cells
- Placement at tile boundary, inside power domain
- SDC: `set_false_path` from ISO_EN to isolated flop data pins

---

## 10. Overlay Wrapper & Context Switch

### 10.1 Overlay Wrapper Hierarchy

The overlay wrapper (`tt_overlay_wrapper`) encapsulates the data-movement CPU subsystem:

```
tt_overlay_wrapper (depth 1)
├── tt_neo_overlay_wrapper (depth 2)
│   ├── dm_cores[0..7] (8× 64-bit RISC-V, dm_clk domain)
│   ├── context_switch (SRAM-based, ping-pong buffers)
│   │   └── 2× 128-bit wide SRAMs (dm_clk)
│   ├── snoop_filter (L1 coherency)
│   ├── global_cmdbuf (NoC copy command buffer)
│   ├── niu_reg_cdc (NoC↔DM register CDC FIFO)
│   └── ext_reg_cdc (External register CDC FIFO)
├── smn_wrapper (security management, ai_clk)
└── edc_wrapper (EDC node for overlay, ai_clk)
```

### 10.2 Context Switch

Hardware context switch copies register state between Tensix cores:
- 8 context slots
- Each slot: TRISC register file + configuration state
- SRAM-backed: 2 SRAMs, each 256×128-bit (dm_clk)
- Triggered by overlay firmware via `context_switch` accelerator

### 10.3 Hardware Accelerators (Overlay)

| Accelerator              | Function                                          |
|--------------------------|---------------------------------------------------|
| NoC Copy Command         | DMA: L1→L1 across tiles, triggered via NoC packet |
| Patterned Address Gen    | Strided/tiled address generation for DMA         |
| Context Switch HW        | TRISC register save/restore                       |
| Local Data Shuffling     | In-tile data reorganization (transpose, pad)      |

### 10.4 N1B0 DFX Wrappers

N1B0 inserts 4 DFX clock-gating wrapper modules (pre-Tessent insertion):

| DFX Wrapper Module           | Wraps                            |
|------------------------------|----------------------------------|
| `tt_noc_niu_router_dfx`      | NoC/NIU/Router partition         |
| `tt_overlay_wrapper_dfx`     | Overlay wrapper                  |
| `tt_instrn_engine_wrapper_dfx`| Instruction engine wrapper      |
| `tt_t6_l1_partition_dfx`     | T6 L1 SRAM partition             |

All clock outputs in N1B0 are wire-assigns (no clock buffers inserted yet). IJTAG network conditionally compiled (`INCLUDE_TENSIX_NEO_IJTAG_NETWORK` not defined in N1B0).

---

## 11. Physical Design Notes

### 11.1 Synthesis Partitions

Synthesis must define the following macros:
```
`define SYNTHESIS
`define NEO_PD_PROTO
`define TDMA_NEW_L1
`define RAM_MODELS
`define USE_VERILOG_MEM_ARRAY
`define TT_CUSTOMER
`define TRINITY
```

**Top-level synthesis partitions and their SDC files:**

| # | Partition Module                          | Contents                                      |
|---|-------------------------------------------|-----------------------------------------------|
| 1 | `tt_fpu_gtile`                            | FPU G-Tile (M-Tiles, FP Lanes, DEST)          |
| 2 | `tt_overlay_wrapper`                      | Overlay DM CPUs, context switch, SMN          |
| 3 | `tt_noc_niu_router`                       | NoC fabric + NIU + Router                     |
| 4 | `tt_t6_l1_partition`                      | L1 SRAM (16 banks + ECC + super-arbiter)       |
| 5 | `tt_instrn_engine_wrapper`                | TRISC/BRISC + SRCB + SFPU + issue logic        |
| 6 | `tt_tensix_with_l1`                       | Tensix top (no SDC)                           |
| 7 | `tt_disp_eng_l1_partition`                | Dispatch L1 (noc_clk)                         |
| 8 | `tt_trin_disp_eng_noc_niu_router_west`    | West dispatch router partition                |
| 9 | `tt_trin_disp_eng_noc_niu_router_east`    | East dispatch router partition                |
| 10| `tt_disp_eng_overlay_wrapper`             | Dispatch overlay wrapper                      |
| 11| `tt_dispatch_engine`                      | Dispatch top-level (no SDC)                   |
| 12| `trinity_noc2axi_n_opt`                   | North NIU variant                             |
| 13| `trinity_noc2axi_ne_opt`                  | Northeast NIU corner                          |
| 14| `trinity_noc2axi_nw_opt`                  | Northwest NIU corner                          |
| 15| `trinity_router`                          | Standalone router (no SDC)                    |

**Process technology:** Samsung SF4X 4nm
**Floorplan depth:** 4 partition levels deep

### 11.2 Tensix NEO Floorplan

```
Tensix NEO Core: 2794 µm × 2121 µm (approximate)

 ┌──────────────────────────────────────────┐ ← top
 │  NoC ROUTER                              │
 ├──────────────────────────────────────────┤
 │  OVERLAY (DM CPUs + context switch)      │
 ├──────────────────────────────────────────┤
 │  INSTRUCTION ENGINE (TRISC + SFPU +SRCB) │
 ├──────────────────┬───────────────────────┤
 │  G-TILE[0]       │  G-TILE[1]            │
 │  (M-Tiles 0-7)   │  (M-Tiles 8-15)       │
 │  DEST[0..7]      │  DEST[8..15]          │
 ├──────────────────┴───────────────────────┤
 │  TDMA (Pack/Unpack)                      │
 ├──────────────────────────────────────────┤
 │  L1 MEMORY (16 banks × 768/3072 rows)    │  ← bottom
 └──────────────────────────────────────────┘

 Left edge: NoC→L1 512-bit write bus channel (~82 µm, M3+)
 Right edge: EDC ring bypass wire (full tile height)
```

### 11.3 NoC→L1 Side Channel

- **Bus width:** 512 bits (4 × 128-bit segments)
- **CDC FIFO:** 8 entries; NOCCLK write / AICLK read
- **Side-channel width:** ~82 µm routing reserved on left edge
- **Layer constraint:** M3 and above only; M1/M2 reserved (no cells)
- **Path:** NoC router output → left-edge channel → L1 bank write port

### 11.4 Repeater Placement Strategy (N1B0)

X-axis inter-column repeaters for NoC wires:

```
Y=4 row:  4 repeater stages between each column pair (E↔W)
Y=3 row:  6 repeater stages between each column pair (E↔W)
Y=0–2:    Direct wire assigns (no repeaters)
```

EDC ring repeaters:
- MCPDLY = 7 (3 repeater stages + 3-stage synchronizer + 1 margin)
- Placement: at harvest bypass wire segments and long inter-tile links

### 11.5 SRAM Inventory Summary

**Per-clock-domain SRAM counts:**

| Clock Domain | Memory Type                    | Count   | Notes                          |
|--------------|-------------------------------|---------|--------------------------------|
| ai_clk       | Tensix L1 (N1B0)              | 768 ×12 | 3072×128-bit per bank, 16 banks |
| ai_clk       | DEST latch-arrays             | 12,288  | All tiles combined             |
| ai_clk       | SRCA latch-arrays             | 1,536   | All tiles combined             |
| ai_clk       | TRISC icache/local mem        | 576     | 4 threads × 4 tiles × macro    |
| dm_clk       | Overlay L1/L2                 | 840     | D/I cache + L2 banks           |
| noc_clk      | Router VC FIFOs               | ≥62     | Per VC buffer per port         |
| noc_clk      | ATT + routing tables          | varies  | Per NIU tile                   |

**N1B0 L1 expansion (4×):**
- Baseline: 64 macros/tile × 12 tiles = 768 total
- N1B0: 256 macros/tile × 12 tiles = 3,072 total
- Macro type: `u_ln05lpe_a00_mc_rf1r_hdrw_lvt_768x69m4b1c1`

---

## 12. Register Maps

### 12.1 NOC2AXI Register Map

**Base address:** `0x2000_0000`

**Module: noc_niu_risc (base `0x2000_000`)**

| Register               | Offset | Bits    | Description                                  |
|------------------------|--------|---------|----------------------------------------------|
| TARGET_ADDR_LO         | 0x00   | [31:0]  | NoC target address bits [31:0]               |
| TARGET_ADDR_MID        | 0x04   | [31:0]  | NoC target address bits [63:32]              |
| TARGET_ADDR_HI         | 0x08   | [31:0]  | NoC target address bits [95:64]              |
| RET_ADDR_LO            | 0x0C   | [31:0]  | Return address bits [31:0]                   |
| RET_ADDR_MID           | 0x10   | [31:0]  | Return address bits [63:32]                  |
| RET_ADDR_HI            | 0x14   | [31:0]  | Return address bits [95:64]                  |
| PACKET_TAG             | 0x18   | [15:0]  | Transaction tag                              |
| CMD_BRCST              | 0x1C   | [31:0]  | Command + broadcast control                  |
| AT_LEN                 | 0x20   | [31:0]  | Atomic operation length                      |
| AT_DATA                | 0x28   | [31:0]  | Atomic operation data                        |
| BRCST_EXCLUDE          | 0x2C   | [23:0]  | Broadcast exclude coordinates                |
| L1_ACC_AT_INSTRN       | 0x30   | [15:0]  | L1 accumulator atomic instruction            |
| SECURITY_CTRL          | 0x34   | [3:0]   | Security fence master level                  |
| CMD_CTRL               | 0x40   | [0]     | Command pending                              |
| NODE_ID                | 0x44   | [28:0]  | NODE_ID_X[5:0], NODE_ID_Y[11:6], NOC_X_SIZE[18:12], NOC_Y_SIZE[25:19], ROUTING_DIM_ORDER_XY[28] |
| ENDPOINT_ID            | 0x48   | [31:0]  | Endpoint identifier                          |
| NUM_MEM_PARITY_ERR     | 0x50   | [15:0]  | Memory parity error counter                  |
| NUM_HEADER_1B_ERR      | 0x54   | [15:0]  | Header 1-bit error counter                   |
| NUM_HEADER_2B_ERR      | 0x58   | [15:0]  | Header 2-bit error counter                   |
| ECC_CTRL               | 0x5C   | [5:0]   | ECC_ERR_CLEAR[2:0], ECC_ERR_FORCE[5:3]       |
| CMD_BUF_AVAIL          | 0x64   | [28:0]  | BUF0[4:0], BUF1[12:8], BUF2[20:16], BUF3[28:24] |
| CMD_BUF_OVFL           | 0x68   | [3:0]   | Per-buffer overflow flags                    |

**Configuration registers (offset `0x100`):**

| Register                    | Offset | Key bits                                     |
|-----------------------------|--------|----------------------------------------------|
| NIU_CONFIG                  | 0x100  | CLK_GATING_DISABLED[0], AXI_ENABLE[15], CMD_BUFFER_FIFO_EN[16] |
| ROUTER_CONFIG               | 0x104  | CLK_GATING_DISABLED[0], ECC_HEADER_SECDED[18] |
| BROADCAST_CONFIG_0–3        | 0x108–0x114 | Broadcast row disable masks            |
| MEM_SHUTDOWN_CONTROL        | 0x118  | DSLPLV[2], DSLP[1], SD[0]                   |
| VC_DIM_ORDER                | 0x128  | Per-VC XY/YX [31:0] (default 0xAAAAAAAA)     |
| THROTTLER_CYCLES_PER_WINDOW | 0x12C  | Window cycle count [31:0]                    |
| NIU_TIMEOUT_VALUE_0/1       | 0x148–0x14C | Timeout cycles (2 instances)           |
| INVALID_FENCE_START/END_*   | 0x150–0x18C | 4× invalid access fences (64-bit addr) |
| VC_THROTTLER_*              | 0x1B0–0x1C0 | Per-VC handshake throttling            |

**Security fence registers (offset `0x400`):**

| Register                       | Offset     | Description                            |
|--------------------------------|------------|----------------------------------------|
| SEC_FENCE_RANGE_0–7_START      | 0x400+     | 64-bit start address (8 ranges)         |
| SEC_FENCE_RANGE_0–7_END        | 0x408+     | 64-bit end address (8 ranges)           |
| SEC_FENCE_ATTRIBUTE_0–7        | 0x480–0x49C | RANGE_ENABLE[8], RD_SEC[7:4], WR_SEC[3:0] |
| SEC_FENCE_MASTER_LEVEL         | 0x4A0      | Master level [3:0]                     |
| SEC_FENCE_VIOLATION_FIFO_STATUS| 0x4A4      | FIFO empty/full                        |
| SEC_FENCE_VIOLATION_FIFO_RDDATA| 0x4A8      | Violation record (address + source)    |

### 12.2 Tensix NoC Registers

**Base address:** `0x0200_0000`

**Module: noc_niu (base `0x0200_0000`)**

| Register         | Offset | Description                                  |
|------------------|--------|----------------------------------------------|
| TARG_ADDR_LO/MID/HI | 0x000–0x008 | 96-bit target address              |
| RET_ADDR_LO/MID/HI  | 0x00C–0x014 | 96-bit return address              |
| CMD_LO/HI        | 0x018–0x01C | Command word (split 32-bit)          |
| BRCST_LO/HI      | 0x020–0x024 | Broadcast control (split 32-bit)     |
| AT_LEN           | 0x028  | Atomic length [31:0]                         |
| L1_ACC_AT_INSTRN | 0x02C  | L1 accumulator atomic instruction [15:0]     |
| SEC_CTRL         | 0x030  | Security control                             |
| AT_DATA          | 0x034  | Atomic data [31:0]                           |
| INLINE_DATA_LO/HI| 0x038–0x03C | Inline data (split 32-bit)          |
| BYTE_ENABLE      | 0x040  | Byte enable mask [31:0]                      |
| CMD_CTRL         | 0x060  | Command control [31:0]                       |
| NODE_ID          | 0x064  | NODE_ID_X[5:0], NODE_ID_Y[11:6], NOC_X_SIZE[18:12], NOC_Y_SIZE[25:19] |
| ENDPOINT_ID      | 0x068  | 32-bit endpoint ID                           |
| ECC_CTRL         | 0x078  | ECC control bits                             |
| CMD_BUF_AVAIL    | 0x080  | Command buffer availability                  |
| CMD_BUF_OVFL     | 0x084  | Buffer overflow flags                        |

### 12.3 Overlay/Cluster Control Registers

**Base address:** `0x0300_0000`

**Module: tt_cluster_ctrl (base `0x0300_0000`)**

| Register            | Offset     | Description                                   |
|---------------------|------------|-----------------------------------------------|
| reset_vector_0–7    | 0x00–0x38  | 64-bit RISC-V reset vectors (8 cores)         |
| scratch_0–31        | 0x40–0xBC  | General purpose 32-bit registers              |
| clock_gating        | 0xCC       | rocc[0], idma[1], cluster_ctrl[2], context_switch[3], llk_intf[4], snoop[5], global_cmdbuf[6], l1_flex_client_idma[7], l1_flex_client_overlay[8], fds[9] |
| clock_gating_hyst   | 0xD0       | Hysteresis [6:0] (default 0x8)               |
| wb_pc_reg_c0–7      | 0xD4–0x10C | 64-bit PC capture per DM core                |
| ecc_parity_control  | 0x118      | en[0]                                         |
| asserts             | 0x124      | Hardware assertions [31:0] (read-only)        |
| overlay_info        | 0x1CC      | dispatch_inst[0], is_customer[1], tensix_version[9:4], noc_version[15:10], overlay_version[21:16] |
| global_counter_ctrl | 0x1D0      | global_counter_en[0], global_counter_clear[1]|

**L2 cache controller (base `0x0401_0000`):**

| Register     | Offset | Description                        |
|--------------|--------|------------------------------------|
| Configuration| 0x000  | banks[7:0], ways[15:8], lgSets[23:16], lgBlockBytes[31:24] |
| Flush64      | 0x200  | Flush cache line at 64-bit address |
| Flush32      | 0x240  | Flush at 32-bit address (shift 4)  |
| Invalidate64 | 0x280  | Invalidate at 64-bit address       |
| FullInvalidate| 0x300 | Invalidate all L2                  |

**Watchdog Timer (per DM core, base `0x0400_8000 + N×0x1000`):**

| Register | Offset | Description                                        |
|----------|--------|----------------------------------------------------|
| CTRL     | 0x00   | wdogscale[3:0], wdogrsten[8], wdogenalways[12], wdogip0[28] |
| COUNT    | 0x08   | wdogcount[30:0]                                    |
| FEED     | 0x18   | Write 0xD09F00D to reset watchdog                  |
| KEY      | 0x1C   | Write 0x51F15E to unlock                           |
| CMP      | 0x20   | wdogcmp0[15:0] (default 0x1000)                   |

### 12.4 EDC BIU Registers

See §8.5 for the complete EDC BIU register table.

### 12.5 Address Translation Table (ATT)

**Base address:** `0x2010_000` (within NOC2AXI APB space)

| Register              | Offset       | Description                              |
|-----------------------|--------------|------------------------------------------|
| ENABLE_TABLES         | 0x00         | en_address_translation[0], en_dynamic_routing[1] |
| CLK_GATING            | 0x04         | clk_gating_enable[0], hysteresis[7:1]    |
| DEBUG_LAST_SRC/DEST   | 0x08–0x18    | Last translation source/dest debug       |
| MASK_TABLE_ENTRY_0–15 | 0x30–0x198   | mask[5:0], ep_id_idx[11:6], ep_id_size[17:12], table_offset[27:18], translate_addr[28] |
| MASK_TABLE_EP_LO/HI   | 0x38–0x1A4   | 64-bit endpoint addresses (16 entries)   |
| MASK_TABLE_BAR_LO/HI  | 0x40–0x1AC   | 64-bit BAR for translation (16 entries)  |
| ROUTING_TABLE_MATCH   | 0x200–0x27C  | 32 dynamic routing match entries [15:0]  |
| ROUTING_TABLE_PART    | 0x300–0x37C  | 32 partial routing entries [31:0]        |
| ENDPOINT_TABLE_0–1023 | 0x2000–0x2FFC| x[5:0], y[11:6] per endpoint (1024 entries) |

---

## 13. Verification & Testbench Infrastructure

### 13.1 Testbench Overview

**Environment:**
- Python 3.9+, Synopsys VCS V-2023.12-SP1-1
- cocotb 1.9.0 + cocotbext-axi + cocotbext-apb + pyyaml
- Setup: `source $TENSIX_ROOT/tb/setup.sourceme`
- Run: `make` in `$TENSIX_ROOT/tb/`

**Test categories (v0.10):**

| Category            | Tests                                                   |
|---------------------|---------------------------------------------------------|
| Basic sanity        | NoC send/receive, address pinger                        |
| EDC verification    | Error injection, BIU interrupt monitoring, COR/UNC test |
| Security fence      | NoC2AXI security fence boundary test                    |
| Harvest             | Row/column harvest + clock gating                       |
| Matrix multiply     | FP16B, INT8, INT16 format tests (various sizes)         |
| Power stress        | `dm_traffic_with_local_matmul_test`                     |
| Broadcast/multicast | Strided multicast, broadcast                            |

### 13.2 TTX Binary Format

TTX packages Tensix test vectors (kernel binary + input data + YAML config).

**File structure:**
```
File Header (32 bytes):
  [3:0]   Magic number (4 bytes)
  [31:4]  7 reserved 32-bit fields

Chunks (variable):
  Chunk Header (16 bytes):
    [7:0]   Target L1 address (64-bit)
    [11:8]  Data size (32-bit)
    [15:12] Reserved (32-bit)
  Chunk Data: <size> bytes at target address
```

**TTX components:**
- `ckernels.bin` — TRISC kernel binaries
- `image.bin` — Input tensor data
- `test.yaml` — Operation descriptor

**test.yaml fields:**
```yaml
l1_output_fifo:
  output_fifo_address: 0x...  # where Tensix writes results
  output_fifo_size: N
expected_commands_pushed: N   # poll L1[0x4] until equals this
```

**Test execution flow:**
1. Load TTX chunks into L1 at specified addresses
2. Clear output FIFO (write 0x0)
3. Zero first 8 bytes of L1 (address 0x4 = outbound mailbox)
4. Poll L1[0x4] until == `expected_commands_pushed`
5. Validate output vs `dump.bin` golden vector

### 13.3 Performance Test (trinity_performance)

Tests NOC2AXI throughput and latency by transferring data between Tensix L1 and AXI memory.

**Test function:** `trinity_performance.py:120`
**Binary:** `$TENSIX_ROOT/firmware/data_movement/tests/trinity_performance/out/trinity_performance.bin`
**Note:** Test currently `skip=True`; must run explicitly:
```bash
cd $TT_DELIVERY/tb
make TESTCASE=trinity_performance_test
```

**Configuration parameters:**

| Parameter                | Default  | Description                             |
|--------------------------|----------|-----------------------------------------|
| TRANSFER_SIZE            | —        | Bytes per transfer                      |
| NUMBER_OF_TRANSFERS      | —        | Total transfers per core                |
| TARGET_MEMORY_START_ADDR | 0x0      | External DDR/AXI base address           |

**Data size constraint:** `8 cores × 3 buffers × TRANSFER_SIZE × NUM_TRANSFERS ≤ 512 KB`

**Valid configuration examples:**

| TRANSFER_SIZE | NUMBER_OF_TRANSFERS | Total Data |
|---------------|---------------------|-----------|
| 128           | 160                 | 480 KB    |
| 1024          | 20                  | 480 KB    |
| 4096          | 5                   | 480 KB    |

**Metrics measured:**
- Write throughput (bytes/cycle): AW→B response window
- Read throughput (bytes/cycle): AR→last R-beat window
- Round-trip latency: min/max observed
- Data integrity: verified against written pattern

**Command line options:**
```bash
make TESTCASE=trinity_performance_test WAVES=1
make TESTCASE=trinity_performance_test PERF_MONITOR_VERBOSITY=1
make TESTCASE=trinity_performance_test MONITOR_ROUND_TRIP_LATENCY=1
```

### 13.4 noc2axi_perf_monitor (N1B0 Simulation-Only)

Simulation-only module measuring AXI transaction latency in real-time.

**Parameters:**

| Parameter | Default | Description               |
|-----------|---------|---------------------------|
| MAX_DELAY | 256     | Maximum latency window    |
| HEADROOM  | 256     | FIFO headroom entries     |

**Output ports (type: `real`, non-synthesizable):**

| Port                | Description                                |
|---------------------|--------------------------------------------|
| `o_avg_rd_latency`  | Running average read first-beat latency    |
| `o_avg_wr_latency`  | Average write B-response latency           |
| `o_max_rd_latency`  | Maximum read latency observed              |
| `o_min_rd_latency`  | Minimum read latency observed              |
| `o_total_rd_txn`    | Total read transactions                    |
| `o_total_wr_txn`    | Total write transactions                   |

**Latency definitions:**
- Read latency: AR handshake → first R-beat (cycles)
- Write latency: AW handshake → B-beat (cycles)

**Plusarg control:**
```
+PERF_MONITOR_VERBOSITY=0   (silent, default)
+PERF_MONITOR_VERBOSITY=1   (summary at end)
+PERF_MONITOR_VERBOSITY=3   (verbose per-transaction)
+MONITOR_ROUND_TRIP_LATENCY=1  (enable per-ID tracking)
```

### 13.5 axi_dynamic_delay_buffer (N1B0 Synthesizable)

Programmable cycle-delay buffer for AXI R-channel latency emulation (synthesizable).

**Architecture:**
```
AXI R-channel in → [timestamp FIFO] → delay compare → AXI R-channel out
                         ↑
                   delay_cycles input (programmable)
```

**Parameters:**

| Parameter | Default | Description                    |
|-----------|---------|--------------------------------|
| MAX_DELAY | 256     | Maximum programmable delay     |
| HEADROOM  | 256     | FIFO extra capacity            |

**Operation:**
- Each incoming beat timestamped with current cycle count
- Beat released when: `current_cycle ≥ timestamp + delay_cycles`
- FIFO depth = MAX_DELAY + HEADROOM entries

**Assertion:** `delay_cycles` must not change while FIFO is non-empty.

---

## 14. N1B0 Silicon Variant — Delta from Baseline

### 14.1 N1B0 vs Baseline Comparison Table

| Feature                   | Baseline Trinity     | N1B0                                |
|---------------------------|---------------------|-------------------------------------|
| Grid size                 | 4×5                 | 4×5 (same)                          |
| L1 per tile               | 192 KB (64 macros)  | **768 KB (256 macros, 4×)**         |
| Total L1                  | 2.304 MB            | **9.216 MB**                        |
| NOC2AXI + Router          | Separate modules    | **Composite dual-row tile**         |
| Clock inputs              | Single ai/dm_clk    | **Per-column i_ai_clk[3:0]/i_dm_clk[3:0]** |
| X-axis NoC routing        | Generate loop       | **Manual assigns with repeaters**   |
| Repeaters Y=4             | None                | **4 stages east↔west**              |
| Repeaters Y=3             | None                | **6 stages east↔west**              |
| PRTN chain                | Absent              | **4-column daisy chain**            |
| ISO_EN                    | Absent              | **ISO_EN[11:0] (6th harvest mech)** |
| Router tile (X=1,2 Y=3)   | Instantiated        | **Empty placeholder (internal)**    |
| REP_DEPTH_LOOPBACK        | 0                   | **6**                               |
| REP_DEPTH_OUTPUT          | 0                   | **4**                               |
| DFX wrappers              | Absent              | **4 clock pass-through wrappers**   |
| RDATA FIFO depth          | Fixed               | **Configurable (32–1024 via define)** |

### 14.2 N1B0 RTL File Scope

Primary RTL path: `$TENSIX_ROOT/used_in_n1/`

Key files:

| File                                          | Module                             |
|-----------------------------------------------|------------------------------------|
| `targets/4x5/trinity.sv`                      | Top-level SoC                      |
| `targets/4x5/trinity_pkg.sv`                  | Package constants                  |
| `trinity_noc2axi_router_ne_opt.sv`            | Composite NE tile                  |
| `trinity_noc2axi_router_nw_opt.sv`            | Composite NW tile                  |
| `trinity_noc2axi_ne_opt.sv`                   | Corner NE NIU                      |
| `trinity_noc2axi_nw_opt.sv`                   | Corner NW NIU                      |
| `dfx/tt_noc_niu_router_dfx.sv`                | DFX wrapper — NoC/NIU/Router       |
| `dfx/tt_overlay_wrapper_dfx.sv`               | DFX wrapper — Overlay              |
| `dfx/tt_instrn_engine_wrapper_dfx.sv`         | DFX wrapper — Instruction Engine   |
| `dfx/tt_t6_l1_partition_dfx.sv`               | DFX wrapper — L1                   |
| `tb/noc2axi_perf_monitor.sv`                  | Sim-only AXI latency monitor       |
| `tb/axi_dynamic_delay_buffer.sv`              | Synthesizable AXI delay buffer     |

### 14.3 N1B0 Composite Tile Port Prefixes

```
NOC2AXI_ROUTER_NE/NW_OPT top-level port naming:
  noc2axi_i_* / noc2axi_o_*  → Y=4 AXI bridge interface
  router_i_*  / router_o_*   → Y=3 router interface

  Example clock ports:
    noc2axi_i_ai_clk      ← per-column ai_clk for Y=4
    router_o_ai_clk       → drives clock_routing_out[x][y-1]
    noc2axi_o_dm_clk      ← pass-through for Y=3
```

---

## 15. INT16/FP16B/INT8 LLM Mapping Guide

### 15.1 Dimension Glossary

| Symbol  | Full Name         | LLaMA 3.1 8B | HW Mapping                         |
|---------|-------------------|--------------|-------------------------------------|
| M       | Batch × sequence  | 128 tokens   | DEST rows (512 INT32 / 1024 FP16)  |
| K       | Hidden dim (reduction) | 4096    | SRCA depth; max 48/pass            |
| N       | Output features   | 4096–14336   | FPU width = 16 fixed; TP split      |
| K_tile  | K per MOP iter    | 48           | Hardware max = 48 rows             |
| N_tile  | N per FPU cycle   | 16           | Fixed = 16 FPU columns             |
| M_tile  | M per DEST pass   | 16–256       | SW choice; INT32 mode ≤ 256        |
| d_model | Model hidden dim  | 4096         | K=N=d_model for most layers        |
| d_ffn   | FFN intermediate  | 14336        | K=d_model, N=d_ffn for FFN up-proj |
| d_k     | Attention head dim| 128          | K_tile=d_k (fits in SRCA)          |

### 15.2 Tiling Loop (INT16 GEMM)

```
# Outer loops (software)
for m_start in range(0, M, M_tile):
  for n_start in range(0, N, N_tile):      # N_tile=16 fixed
    # Clear DEST accumulator
    clear_dest()
    # K reduction loop (MOP-accelerated)
    for k_start in range(0, K, K_tile):     # K_tile=48 hardware max
      # Load A[m_start:m_start+M_tile, k_start:k_start+K_tile] → SRCA
      # Load B[k_start:k_start+K_tile, n_start:n_start+N_tile] → SRCB
      # Issue MOP → FPU computes partial sums into DEST
    # Pack DEST[m_start:, n_start:] → L1 output buffer
```

### 15.3 L1 Fit Formula

For INT16 GEMM with M_tile × K_tile × N_tile tile:

```
L1 required:
  A_buffer  = M_tile × K_tile × 2 bytes (INT16)
  B_buffer  = K_tile × N_tile × 2 bytes (INT16)
  C_buffer  = M_tile × N_tile × 4 bytes (INT32 accumulator)
  Overhead  = ~16 KB (kernel, stack, SFPU buffers)

Total ≤ L1_SIZE (192 KB baseline / 768 KB N1B0)

N1B0 allows much larger tiles:
  M_tile=256, K_tile=48, N_tile=16: 256×48×2 + 48×16×2 + 256×16×4 = 42,496 bytes → fits easily
```

### 15.4 Key Register Programming Sequence

**TDMA unpacker setup (TRISC0):**
```
1. Set src_format = input data format (e.g., INT16 = 0x9)
2. Set dst_format = SRCA accumulation format (INT32 = 0x8 for accumulation)
3. Set l1_src_addr, l1_size, matrix_dims
4. Issue UNPACK command → TDMA loads SRCA from L1
```

**FPU MOP loop (TRISC1):**
```
1. Set DEST format (INT32 for accumulation)
2. Issue MATMUL MOP: specifies K_tile depth, SRCA/SRCB start rows
3. MOP decoder generates sub-ops at full FPU rate
```

**TDMA packer setup (TRISC2):**
```
1. Set pack_format = output format (INT16 or FP16B for post-GEMM)
2. Set l1_dst_addr, activation function (none / relu / crelu)
3. Issue PACK command → DEST → L1
```

### 15.5 LLaMA 3.1 8B Mapping

| Layer Type        | M    | K    | N     | K_tile | M_tile | Recommended Format |
|-------------------|------|------|-------|--------|--------|--------------------|
| Attention QKV     | 128  | 4096 | 4096  | 48     | 128    | INT8 (weights), INT16 (activations) |
| Attention output  | 128  | 4096 | 4096  | 48     | 128    | FP16B              |
| FFN up-proj       | 128  | 4096 | 14336 | 48     | 128    | INT8               |
| FFN gate-proj     | 128  | 4096 | 14336 | 48     | 128    | INT8               |
| FFN down-proj     | 128  | 14336| 4096  | 48     | 128    | INT8               |
| KV-cache update   | seq  | d_k  | d_k   | d_k    | seq    | INT16 (long context) |

**K_tile loop count for d_model=4096:**
- K_tile = 48 → ceiling(4096/48) = **86 MOP passes per (M_tile, N_tile) block**

**N1B0 L1 advantage for KV-cache:**
- Baseline 192 KB: context window ~512 tokens before eviction
- N1B0 768 KB: context window ~2048 tokens before eviction (4× improvement)

---

## 16. Release History & EDA Versions

### 16.1 Version History Summary

| Version | Key Changes                                                                         |
|---------|-------------------------------------------------------------------------------------|
| v0.1    | Initial documentation, top-level wrapper, initial floorplanning                    |
| v0.2    | First RTL drop (partially encrypted), basic testbench, reference synthesis flow    |
| v0.21   | Memory + primitive lists, separate encryption for sim vs synthesis                  |
| v0.3    | Dispatch core included, updated NoC2AXI, Tensix clusters, cluster count → 12       |
| v0.4    | INT4 support, reduced FP16 capacity, preliminary ECC/Parity (not production)       |
| v0.4.1  | More tests, overlay memory reduction, multicast/strided multicast from NoC2AXI     |
| v0.5    | LDM/iCache 50% reduction (cores 1–2), EDC unit added to each NoC2AXI, area opt     |
| v0.6    | Partition split: east/west router; NoC2AXI n/ne/nw variants; updated SDC flow      |
| v0.7    | Palladium compat, timing loop fix, abutted design fixes, NEO error/fault connectivity |
| v0.8    | NOC clock rerouted through NOC partition; overlay interrupt; EDC bypass in overlay; L1-to-GTile clock fix; various abutment fixes |
| v0.9    | Clock gating fixes, abutment fixes, EDC CDC timing, expanded EDC coverage, harvest+clock gating test, power virus |
| **v0.10** | **Extra repeater stages, GTile 6.5% area reduction, BIU interrupt monitoring, security fence test, power stress test** |

### 16.2 EDA Tool Versions (v0.10)

| Tool                 | Version                 |
|----------------------|-------------------------|
| Synopsys VCS         | V-2023.12-SP1-1         |
| Synopsys Verdi       | V-2023.12-SP1-1         |
| Synopsys Synthesis   | T-2022.03-SP5           |
| Synopsys Formality   | T-2022.03-SP5           |
| Synopsys Spyglass    | U-2023.03-SP1-1         |
| Python               | 3.9.18                  |
| cocotb               | 1.9.0                   |

### 16.3 Open Source Dependencies

All sourced from https://github.com/pulp-platform and https://github.com/ucb-bar/chipyard:

| Library               | Source           |
|-----------------------|------------------|
| APB                   | pulp-platform    |
| AXI                   | pulp-platform    |
| AXI_STREAM            | pulp-platform    |
| COMMON_CELLS          | pulp-platform    |
| iDMA                  | pulp-platform    |
| REGISTER_INTERFACE    | pulp-platform    |
| TECH_CELLS_GENERIC    | pulp-platform    |
| OBI                   | pulp-platform    |
| Chipyard (Rocket core)| ucb-bar          |

---

## Appendix A: Related Documents

| Document                              | Location                                          | Contents                               |
|---------------------------------------|---------------------------------------------------|----------------------------------------|
| Trinity_PD_Ref_Guide_Rev1p0.pdf      | `docs/Trinity_PD_Ref_Guide_Rev1p0.pdf`           | PD floorplan, partition guidelines     |
| TT_Row_Column_Harvesting_with_Tests  | `docs/TT_Row_Column_Harvesting_with_Tests.pdf`   | Harvest firmware guide (Rev 1.4)       |
| TT_Trinity_Performance_Test          | `docs/TT_Trinity_Performance_Test.pdf`           | NOC2AXI performance test guide         |
| integration-guide.html               | `docs/integration-guide.html`                    | Full port list, clock sequencing       |
| tensix-user-manual.html              | `docs/tensix-user-manual.html`                   | Tensix NEO cluster user manual         |
| N1B0_HDD_v0.1.md                     | `DOC/N1B0/N1B0_HDD_v0.1.md`                     | N1B0 module hierarchy verification     |
| N1B0_NPU_HDD_v0.1.md                 | `DOC/N1B0/N1B0_NPU_HDD_v0.1.md`                 | N1B0 NPU-level architecture            |
| N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1    | `DOC/N1B0/N1B0_NOC2AXI_ROUTER_OPT_HDD_v0.1.md` | Composite tile internal architecture   |
| tensix_core_HDD.md v0.3              | `DOC/N1B0/tensix_core_HDD.md`                   | Full Tensix FPU/SFPU/TRISC detail      |
| EDC_HDD.md                           | `DOC/N1B0/EDC_HDD.md`                           | Full EDC ring protocol spec            |
| trinity_full_hierarchy.md            | `DOC/N1B0/trinity_full_hierarchy.md`             | SRAM inventory + hierarchy tree        |

## Appendix B: N1B0 Key Facts Quick Reference

```
Grid:          4×5 tiles (NOC_X_SIZE=4, NOC_Y_SIZE=5)
Compute:       12 Tensix NEO clusters (X=0–3, Y=0–2)
Dispatch:      2 tiles (X=0,3 at Y=3)
NIU corners:   NOC2AXI_NW_OPT (X=0,Y=4), NOC2AXI_NE_OPT (X=3,Y=4)
Composite:     NOC2AXI_ROUTER_NW_OPT (X=1), NOC2AXI_ROUTER_NE_OPT (X=2)
Router Y=3:    Empty placeholder (internal to composite, no standalone module)

L1/tile:       768 KB (16 banks × 3072 rows × 128 bits)
Total L1:      9.216 MB (12 tiles)

Clock:         per-column i_ai_clk[3:0], i_dm_clk[3:0]; global i_noc_clk
PRTN:          daisy-chain per column (Y=2→1→0)
ISO_EN:        [11:0] — bit 2x+0=dispatch, 2x+1=router per column x
Harvest mechs: 6 total (5 baseline + ISO_EN)

REP_DEPTH_LOOPBACK = 6   (N1B0 timing fix for Y=3 composite)
REP_DEPTH_OUTPUT   = 4
X-axis repeaters:  4 stages at Y=4, 6 stages at Y=3

Max INT8 MACs/cycle/tile: 8192
Max BF16 MACs/cycle/tile: 1024
K_tile hardware max:      48 rows
DEST rows (INT32 mode):   512
```
