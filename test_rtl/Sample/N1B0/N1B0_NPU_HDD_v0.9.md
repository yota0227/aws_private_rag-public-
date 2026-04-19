# N1B0 NPU Hardware Design Document v0.9

## Document History

| Version | Date       | Author    | Changes                                                                 |
|---------|------------|-----------|-------------------------------------------------------------------------|
| v0.1    | 2026-01-10 | HW Team   | Initial draft — SoC overview, grid, tile types                         |
| v0.2    | 2026-01-24 | HW Team   | Tensix tile detail added; L1 SRAM 4× expansion confirmed               |
| v0.3    | 2026-02-07 | HW Team   | NOC2AXI composite tile architecture; cross-row flit wires              |
| v0.4    | 2026-02-18 | HW Team   | Dispatch tile, iDMA engine detail; SFR memory map §2.1                 |
| v0.5    | 2026-02-28 | HW Team   | NoC router virtual channels, ATT, dynamic routing 928-bit carried list |
| v0.6    | 2026-03-07 | HW Team   | EDC ring, severity model, MCPDLY=7 derivation                          |
| v0.7    | 2026-03-14 | HW Team   | Harvest mechanism 6 (ISO_EN), PRTN chain, DFX wrappers                 |
| v0.8    | 2026-03-20 | HW Team   | §15.2 floorplan correction (NoC→L1 side channel); P&R notes            |
| v0.9    | 2026-03-26 | HW Team   | Full restructure: §1–§14 outline, all RTL-verified facts incorporated  |

---

## Table of Contents

- §1  SoC Overview
- §2  Tensix Compute Tile
- §3  NOC2AXI Composite Tiles (§3.7 NIU DMA Operation)
- §4  Dispatch Tiles
- §5  NoC Router
- §6  iDMA Engine
- §7  EDC Ring
- §8  Clock, Reset, and CDC Architecture (§8.4 ISO_EN Harvest Isolation, §8.7 DFX Clock Gating)
- §9  Security Monitor Network (SMN)
- §10 Debug Module (RISC-V External Debug)
- §11 Adaptive Workload Manager (AWM)
- §12 Memory Architecture
- §13 SFR Summary
- §14 Verification Checklist

---

## §1 SoC Overview

### 1.1 Product Description

Trinity N1B0 is a neural processing unit (NPU) implemented as a 4×5 2D NoC mesh. It is designed for inference and training workloads using INT16, FP16B, and INT8 numeric formats, with optional FP32 accumulation. The chip targets LLM inference use cases such as LLaMA-class models and provides dedicated tensor DMA, programmable RISC-V host processors, and a coherent NoC fabric.

### 1.2 Grid Topology

The N1B0 mesh is indexed as X=0..3 (columns) × Y=0..4 (rows), giving 20 tiles total. X increases left-to-right; Y increases bottom-to-top.

```
         X=0              X=1                  X=2                  X=3
       ┌──────────────┬──────────────────┬──────────────────┬──────────────┐
  Y=4  │ NOC2AXI_     │ NOC2AXI_ROUTER_  │ NOC2AXI_ROUTER_  │ NOC2AXI_     │
       │ NE_OPT       │ NE_OPT           │ NW_OPT           │ NW_OPT       │
       │ (0,4) EP=4   │ (1,4) EP=9       │ (2,4) EP=14      │ (3,4) EP=19  │
       │ standalone   │ composite Y=4    │ composite Y=4    │ standalone   │
       │ NIU only     │ NIU portion      │ NIU portion      │ NIU only     │
       ├──────────────┼──────────────────┼──────────────────┼──────────────┤
  Y=3  │ DISPATCH_E   │ ROUTER           │ ROUTER           │ DISPATCH_W   │
       │ (0,3) EP=3   │ (1,3) EP=8       │ (2,3) EP=13      │ (3,3) EP=18  │
       │              │ composite Y=3    │ composite Y=3    │              │
       │              │ router portion   │ router portion   │              │
       │              │ of NE_OPT        │ of NW_OPT        │              │
       ├──────────────┼──────────────────┼──────────────────┼──────────────┤
  Y=2  │ Tensix       │ Tensix           │ Tensix           │ Tensix       │
       │ (0,2) EP=2   │ (1,2) EP=7       │ (2,2) EP=12      │ (3,2) EP=17  │
       ├──────────────┼──────────────────┼──────────────────┼──────────────┤
  Y=1  │ Tensix       │ Tensix           │ Tensix           │ Tensix       │
       │ (0,1) EP=1   │ (1,1) EP=6       │ (2,1) EP=11      │ (3,1) EP=16  │
       ├──────────────┼──────────────────┼──────────────────┼──────────────┤
  Y=0  │ Tensix       │ Tensix           │ Tensix           │ Tensix       │
       │ (0,0) EP=0   │ (1,0) EP=5       │ (2,0) EP=10      │ (3,0) EP=15  │
       └──────────────┴──────────────────┴──────────────────┴──────────────┘
```

**Notes (RTL-verified from `used_in_n1/mem_port/rtl/targets/4x5/trinity_pkg.sv`):**
- `GridConfig[4]` (Y=4) = `'{NOC2AXI_NE_OPT, NOC2AXI_ROUTER_NE_OPT, NOC2AXI_ROUTER_NW_OPT, NOC2AXI_NW_OPT}` for X=0..3
- `GridConfig[3]` (Y=3) = `'{DISPATCH_E, ROUTER, ROUTER, DISPATCH_W}` for X=0..3
- **Y=4 X=0 and X=3 are NOT Tensix** — they are standalone NIU-only tiles (`NOC2AXI_NE_OPT` / `NOC2AXI_NW_OPT`), distinct from the composite router tiles at X=1/X=2.
- **NE_OPT is at X=0 (standalone) and X=1 (composite)**; **NW_OPT is at X=2 (composite) and X=3 (standalone)**.
- **DISPATCH_E is at X=0 (Y=3)**; **DISPATCH_W is at X=3 (Y=3)** — East/West labels refer to NoC orientation, not physical left/right.
- Total Tensix: 12 tiles at Y=0–2 (all X=0..3). Y=3 and Y=4 contain no Tensix tiles.

### 1.3 Tile Type Summary

| Tile Type                   | Count | Grid Positions          | RTL Module                              | tile_t enum value |
|-----------------------------|-------|-------------------------|-----------------------------------------|-------------------|
| Tensix compute              | 12    | (0–3, Y=0–2)            | tt_tensix_with_l1                       | `TENSIX` = 3'd0   |
| NOC2AXI_ROUTER_NE_OPT       | 1     | (1, 3–4) composite      | trinity_noc2axi_router_ne_opt           | `NOC2AXI_ROUTER_NE_OPT` = 3'd2 |
| NOC2AXI_ROUTER_NW_OPT       | 1     | (2, 3–4) composite      | trinity_noc2axi_router_nw_opt           | `NOC2AXI_ROUTER_NW_OPT` = 3'd3 |
| NOC2AXI_NE_OPT (standalone) | 1     | (0, 4)                  | trinity_noc2axi_ne_opt                  | `NOC2AXI_NE_OPT` = 3'd1  |
| NOC2AXI_NW_OPT (standalone) | 1     | (3, 4)                  | trinity_noc2axi_nw_opt                  | `NOC2AXI_NW_OPT` = 3'd4  |
| DISPATCH_E                  | 1     | (0, 3)                  | tt_dispatch_top_east                    | `DISPATCH_E` = 3'd5 |
| DISPATCH_W                  | 1     | (3, 3)                  | tt_dispatch_top_west                    | `DISPATCH_W` = 3'd6 |

### 1.4 EndpointIndex Encoding

Every tile that connects to the NoC fabric is assigned an EndpointIndex used in ATT lookups and flit routing:

```
EndpointIndex = X * 5 + Y
```

| (X, Y)  | EndpointIndex | Tile Type                              | RTL tile_t            |
|---------|---------------|----------------------------------------|-----------------------|
| (0, 0)  | 0             | Tensix                                 | TENSIX                |
| (0, 1)  | 1             | Tensix                                 | TENSIX                |
| (0, 2)  | 2             | Tensix                                 | TENSIX                |
| (0, 3)  | 3             | DISPATCH_E                             | DISPATCH_E            |
| (0, 4)  | 4             | NOC2AXI_NE_OPT (standalone NIU)        | NOC2AXI_NE_OPT        |
| (1, 0)  | 5             | Tensix                                 | TENSIX                |
| (1, 1)  | 6             | Tensix                                 | TENSIX                |
| (1, 2)  | 7             | Tensix                                 | TENSIX                |
| (1, 3)  | 8             | ROUTER (composite NE_OPT Y=3 portion)  | ROUTER                |
| (1, 4)  | 9             | NOC2AXI_ROUTER_NE_OPT (composite NIU)  | NOC2AXI_ROUTER_NE_OPT |
| (2, 0)  | 10            | Tensix                                 | TENSIX                |
| (2, 1)  | 11            | Tensix                                 | TENSIX                |
| (2, 2)  | 12            | Tensix                                 | TENSIX                |
| (2, 3)  | 13            | ROUTER (composite NW_OPT Y=3 portion)  | ROUTER                |
| (2, 4)  | 14            | NOC2AXI_ROUTER_NW_OPT (composite NIU)  | NOC2AXI_ROUTER_NW_OPT |
| (3, 0)  | 15            | Tensix                                 | TENSIX                |
| (3, 1)  | 16            | Tensix                                 | TENSIX                |
| (3, 2)  | 17            | Tensix                                 | TENSIX                |
| (3, 3)  | 18            | DISPATCH_W                             | DISPATCH_W            |
| (3, 4)  | 19            | NOC2AXI_NW_OPT (standalone NIU)        | NOC2AXI_NW_OPT        |

### 1.5 Clock Domains

| Clock Signal           | Scope           | Description                                                    |
|------------------------|-----------------|----------------------------------------------------------------|
| `i_axi_clk`            | Global          | AXI master/slave interfaces, host-facing logic                 |
| `i_noc_clk`            | Global          | NoC fabric, router ports, flit transport                       |
| `i_ai_clk[3:0]`        | Per-column      | Tensix compute (FPU, SFPU, TRISC, BRISC); index = X column     |
| `i_dm_clk[3:0]`        | Per-column      | Tensix data-move (TDMA, pack/unpack, L1 access); index = X     |
| `PRTNUN_FC2UN_CLK_IN`  | PRTN chain      | Separate clock for partition control chain                     |

Per-column separation of `ai_clk` and `dm_clk` allows independent DVFS per column. The Dispatch tiles receive `i_noc_clk` for their NoC interface and `i_ai_clk[col]` for their Rocket core.

### 1.6 Reset Architecture

| Reset Signal      | Type       | Scope                                  |
|-------------------|------------|----------------------------------------|
| `i_reset_n`       | Async low  | Global; all flip-flops                 |
| `i_axi_reset_n`   | Async low  | AXI domain registers and bridges       |
| Per-domain synced | Sync       | Each clock domain synchronizes reset internally using 3-stage synchronizer |

### 1.7 Top-Level Module

**File:** `rtl/trinity.sv`
**Module:** `trinity`

Key port groups:
- NoC flit I/O: north/south/east/west per-tile flit buses (512-bit)
- AXI master ports: 512-bit data, 56-bit address (NE and NW composite tiles)
- APB slave: register access for SFR space
- EDC ring: `edc_fwd_in/out`, `edc_loopback_in/out` per chain segment
- Harvest: `ISO_EN[11:0]`, `noc_y_size`, `mesh_start_x/y`
- PRTN chain: `PRTNUN_FC2UN_*` ports

---

## §2 Tensix Compute Tile

### 2.1 Overview

The Tensix compute tile is the primary matrix-math processing element of the N1B0 NPU. Each of the 12 Tensix tiles contains:

- A **BRISC** (Base RISC-V Scalar Core) for tile management and NoC DMA control
- Three **TRISC** cores (TRISC0/1/2) for specialized data-movement and math sequencing
- An **FPU** (Floating Point Unit) — 2× `tt_fpu_tile` instances (G-Tiles), each a unified multiplier array supporting FP32/INT8 GEMM modes and FP-Lane element-wise sub-pipeline
- An **SFPU** (Scalar Floating Point Unit)
- An **L1 SRAM** partition (768KB per tile, N1B0 4× expanded)
- A **TDMA** (Tile DMA) engine with pack/unpack and MOP sequencer
- Destination and source register files (latch arrays)
- An **Overlay wrapper** (`tt_neo_overlay_wrapper`) for context switching and orchestration

```
┌──────────────────────────────────────────────────────────────────┐
│                       tt_tensix_with_l1                          │
│                                                                  │
│  ┌─────────────────────────────────────────┐  ┌──────────────┐  │
│  │           tt_tensix_neo                  │  │ tt_t6_l1_    │  │
│  │                                          │  │ partition    │  │
│  │  ┌──────┐  ┌───────┐  ┌───────────────┐ │  │              │  │
│  │  │BRISC │  │TRISC0 │  │     FPU       │ │  │ 256 macros   │  │
│  │  │RV32  │  │(pack) │  │ ┌───────────┐ │ │  │ ×32KB        │  │
│  │  └──────┘  ├───────┤  │ │ G-Tile    │ │ │  │ = 768KB      │  │
│  │            │TRISC1 │  │ │ 32×FP32   │ │ │  │              │  │
│  │  ┌──────┐  │(unpack│  │ │ MACs      │ │ │  │ 512-bit side │  │
│  │  │SFPU  │  ├───────┤  │ ├───────────┤ │ │  │ channel to   │  │
│  │  │(scal.│  │TRISC2 │  │ │ M-Tile    │ │ │  │ NoC port     │  │
│  │  │ FP)  │  │(math) │  │ │ INT16/8   │ │ │  └──────────────┘  │
│  │  └──────┘  └───────┘  │ │ MACs      │ │ │                    │
│  │                        │ ├───────────┤ │ │                    │
│  │  ┌────────────────┐    │ │ FP-Lane   │ │ │                    │
│  │  │     TDMA       │    │ │ vector FP │ │ │                    │
│  │  │ pack/unpack    │    │ └───────────┘ │ │                    │
│  │  │ MOP sequencer  │    └───────────────┘ │                    │
│  │  └────────────────┘                      │                    │
│  │  ┌───────────┐  ┌────────────────────┐   │                    │
│  │  │ DEST RF   │  │  SRCA RF           │   │                    │
│  │  │ 12,288    │  │  1,536 entries     │   │                    │
│  │  │ (latch)   │  │  (latch)           │   │                    │
│  │  └───────────┘  └────────────────────┘   │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              tt_neo_overlay_wrapper                       │   │
│  │  (context switch, L1/L2 cache, CDC FIFOs, SMN wrapper,  │   │
│  │   EDC wrapper, CPU wrapper, reg_logic, niu_reg_cdc)      │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 BRISC — Base RISC-V Core

#### 2.2.1 Architecture Overview

The BRISC (`tt_risc_wrapper`, ISA: RV32I) is the main control processor of each Tensix tile. Unlike the three TRISC cores which are dedicated to datapath sequencing, BRISC is a general-purpose scalar core that manages the entire tile lifecycle: boot, configuration, DMA, and interrupt dispatch.

**Why a separate BRISC exists:**
The three TRISC cores run tight, cycle-counted inner loops (pack/unpack/math). They have no OS, no interrupt logic, and minimal instruction sets. A separate general-purpose core (BRISC) is needed to handle asynchronous events (interrupts, errors), NoC DMA transactions, and tile-level state machines without interrupting the real-time TRISC pipelines. This separation also allows BRISC firmware to be updated independently of the TRISC LLK (Low-Level Kernel) programs.

```
         ┌──────────────────────────────────────────────┐
         │                BRISC Core (RV32I)             │
         │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
         │  │  ICache  │  │  IMEM    │  │  Data Mem  │  │
         │  │(from L1) │  │(scratchpad)│  │(local 8KB) │  │
         │  └────┬─────┘  └────┬─────┘  └─────┬──────┘  │
         │       └──────────────┴──────────────┘         │
         │                    ALU / LSU                   │
         │  ┌──────────────────────────────────────────┐  │
         │  │         Interrupt Controller (PIC)        │  │
         │  │  SW_INTS=4, HW_INTS=12+NUM_SMN_INTS      │  │
         │  └──────────────────────────────────────────┘  │
         └──────────┬───────────────────────┬─────────────┘
                    │ L1 access (32-bit bus) │ NoC DMA (512-bit side channel)
                    ▼                        ▼
             tt_t6_l1_partition         NoC local port
```

#### 2.2.2 Responsibilities

| Responsibility | Detail |
|---------------|--------|
| **Boot** | On reset, BRISC fetches its firmware from L1 (loaded by Dispatch/iDMA before tile start). Loads TRISC0/1/2 programs into their instruction memories at fixed L1 offsets: TRISC0=`0x6000`, TRISC1=`0x16000`, TRISC2=`0x26000`, TRISC3=`0x36000`. |
| **Tile configuration** | Writes SFR registers (CLUSTER_CTRL, T6_L1_CSR, LLK_TILE_COUNTERS) to configure FPU mode, L1 bank hash function, port enable/disable before kernel execution. |
| **NoC DMA control** | Issues NoC read/write packets via the 512-bit local port to transfer tensor data between this tile's L1 and remote tiles or external DRAM through the NIU. Max outstanding reads: `MAX_TENSIX_DATA_RD_OUTSTANDING=4` (8 in large TRISC mode). |
| **Interrupt dispatch** | Receives hardware interrupts from PIC (see §2.2.3) and calls appropriate firmware ISRs. |
| **TRISC lifecycle** | Sets TRISC reset-PC override, starts/stops TRISCs, monitors TRISC watchdog and PC-buffer timeout. |
| **Error reporting** | On fatal error, BRISC logs the error code and asserts `o_report_safety_valid` to the safety controller, which escalates to EDC ring. |

#### 2.2.3 Interrupt Architecture

BRISC has a Programmed Interrupt Controller (PIC) with:
- **4 software interrupts** (`SW_INTS=4`): firmware-triggered via SFR write
- **12 + NUM_SMN_INTERRUPTS hardware interrupts** (`HW_INTS`): from hardware blocks

Hardware interrupt sources (from RTL `hw_int` assignment, in priority order):

| Source | Signal | Trigger |
|--------|--------|---------|
| PC buffer timeout | `pc_buff_timeout[i]` | TRISC instruction fetch stalled beyond threshold |
| SMN security violation | `i_t6_smn_interrupts` | Address range check failure in NIU |
| Safety controller | `report_safety_valid_intr[i]` | Hardware error detected (ECC, parity) |
| TRISC watchpoint | `trisc_wpi[i]` | TRISC hit a debug watchpoint address |
| Watchdog timer | `wdt_expired_intr` | Tile-level watchdog timer expired |
| DEST register toggle | `dest_toggle` | DEST register file double-buffer flip (signals TRISC2 compute complete) |
| SRCS register toggle | `srcs_toggle` | SRCA/SRCB register file ready (pack/unpack complete) |
| SRCB register toggle | `srcb_toggle` | SRCB buffer available |
| SRCA register toggle | `srca_toggle` | SRCA buffer available |
| Error valid | `err_valid` | General error from error bus (TDMA, SFPU, etc.) |
| Halt | `halt[i]` | TRISC halted (debug or end-of-kernel) |
| IBuffer timeout | `ibuffer_timeout[i]` | Instruction buffer not drained in time |
| IBuffer read enable | `ibuffer_rden[i]` | Instruction buffer ready for next instruction |

The DEST/SRCS toggle interrupts are the critical performance path: BRISC uses these to implement a double-buffering protocol where it overlaps TRISC compute (writing to one DEST buffer) with BRISC-managed data movement (reading from the other DEST buffer via NoC DMA).

#### 2.2.4 Memory Interface

BRISC has three memory interfaces inside the tile:

| Interface | Width | Target | Purpose |
|-----------|-------|--------|---------|
| Instruction fetch | 32-bit | L1 partition (ICACHE region) | BRISC program instructions |
| Data load/store | 32-bit | L1 partition (local 8KB data mem) | Stack, heap, local variables |
| NoC DMA | 512-bit | NoC local port → NIU → DRAM | Tensor bulk transfer |

The 512-bit NoC side channel bypasses the 32-bit data bus entirely, allowing BRISC to initiate full-bandwidth tensor transfers without tying up its scalar pipeline. DMA requests are non-blocking: BRISC issues the NoC write/read packet and the hardware handles burst framing (up to `MAX_L1_REQ=16` outstanding L1 requests, or 32 in large TRISC mode).

#### 2.2.5 Key RTL Parameters

| Parameter | Value (N1B0) | Effect |
|-----------|-------------|--------|
| `DISABLE_SYNC_FLOPS` | 1 | EDC/CDC synchronizer flip-flops bypassed inside Tensix — all cores share `ai_clk`, no clock-domain crossing within the tile |
| `MAX_TENSIX_DATA_RD_OUTSTANDING` | 4 (8 in large mode) | Max in-flight NoC read requests from BRISC |
| `MAX_L1_REQ` | 16 (32 in large mode) | Max outstanding L1 read/write requests |
| `INSN_REQ_FIFO_DEPTH` | 8 (16 large) | Instruction fetch request FIFO depth |
| `ICACHE_REQ_FIFO_DEPTH` | 2 (4 large) | ICache miss request FIFO depth |
| `LOCAL_MEM_SIZE_BYTES` | 8192 (8KB) | BRISC local data memory size |
| `THREAD_COUNT` | 4 | Number of TRISC threads (TRISC0..3; TRISC3 optional) |
| `TRISC_VECTOR_ENABLE` | `4'b0001` | TRISC0 has vector extension enabled |
| `TRISC_FP_ENABLE` | `4'b1111` | All TRISCs have FP extension enabled |

### 2.3 TRISC Cores

#### 2.3.1 Overview and Rationale

N1B0 contains **four TRISC threads** (`THREAD_COUNT=4`): TRISC0, TRISC1, TRISC2, and TRISC3. Each TRISC is a lightweight, fixed-ISA processor — **not** a general-purpose RV32I core like BRISC. The TRISC ISA is purpose-built for tensor data movement and FPU sequencing, with a highly compressed instruction encoding (MOP micro-ops) that achieves roughly 10× instruction density versus raw RISC-V equivalents.

**Why separate TRISCs rather than one core?**
Pack, unpack, and math are three parallel, independent pipelines that must interleave with cycle-accurate timing — e.g., while TRISC2 is computing tile N, TRISC1 must simultaneously be prefetching tile N+1 from L1 and TRISC0 must be writing tile N−1 to the NoC. Merging these onto a single core would require a complex scheduler and introduce pipeline hazards. Separate lightweight cores allow each pipeline stage to run at its own pace, controlled by hardware semaphore (sync barrier) handshakes rather than OS-level scheduling.

#### 2.3.2 Per-Thread Role Assignment

| Thread  | Primary Role            | Key Operation                                          | Clock Domain |
|---------|-------------------------|--------------------------------------------------------|--------------|
| TRISC0  | Pack engine             | Read DEST RF → format-convert → write L1 or NoC flit  | `i_ai_clk`   |
| TRISC1  | Unpack engine           | Read L1 or NoC flit → unpack → load SRCA/SRCB          | `i_ai_clk`   |
| TRISC2  | Math / FPU control      | Issue MOP sequences → G-Tile (with mode: fp32/int8/fp-lane) | `i_ai_clk`   |
| TRISC3  | Optional 4th thread     | Auxiliary control (SW-defined); shares L1 IMEM region | `i_ai_clk`   |

TRISC3 is present but its IRAM enable is controlled by `TRISC_IRAM_ENABLE[3]`. With `TRISC_IRAM_ENABLE=4'b0000` (default), no separate IRAM is allocated and the thread shares the L1 tensor workspace.

#### 2.3.3 RTL Parameters

| Parameter              | Value      | Effect                                                                |
|------------------------|------------|-----------------------------------------------------------------------|
| `THREAD_COUNT`         | `4`        | Instantiates TRISC0–TRISC3                                            |
| `TRISC_IRAM_ENABLE`    | `4'b0000`  | Each bit enables a private IRAM for the corresponding TRISC; 0=shared |
| `TRISC_VECTOR_ENABLE`  | `4'b0001`  | Bit 0 set: TRISC0 has vector extension; bits 1–3 scalar-only          |
| `TRISC_FP_ENABLE`      | `4'b1111`  | All four TRISCs have FP extension enabled                             |

RTL files: `tt_trisc.sv` (one instance per thread), `tt_instrn_engine.sv` (orchestrates all TRISCs, contains MOP sequencer).

#### 2.3.4 Instruction Memory Layout (within L1 partition)

TRISC programs are loaded from L1 at fixed offsets before tile execution begins. BRISC is responsible for copying the firmware images into L1 before releasing the TRISC reset.

```
L1 Address Map (per tile)
─────────────────────────────────────────────────
0x00000  BRISC data / tensor workspace (start)
0x06000  TRISC0 IMEM  (pack LLK)
0x16000  TRISC1 IMEM  (unpack LLK)
0x26000  TRISC2 IMEM  (math LLK)
0x36000  TRISC3 IMEM  (optional aux)
  ...    tensor workspace continues above
─────────────────────────────────────────────────
```

Programs written for TRISCs are called **LLK (Low-Level Kernels)** — hand-written micro-assembly files maintained by the firmware team. Each LLK corresponds to one compute kernel (e.g., INT16 GEMM, FP16B elementwise multiply).

#### 2.3.5 Synchronization and Watchdog

TRISCs coordinate pipeline stages through **hardware sync barriers** — a set of global semaphore registers accessible by all threads. The standard handshake is:

1. TRISC1 (unpack) signals "tile ready in SRCA/SRCB"
2. TRISC2 (math) waits on that barrier, then fires the FPU MOP, then signals "DEST ready"
3. TRISC0 (pack) waits on DEST-ready barrier, then reads DEST and writes output

This eliminates pipeline stalls that would occur with software polling on a single core.

**Watchdog / timeout:** Each TRISC has two independent watchdog counters:
- `pc_buff_timeout` — fires if the instruction fetch PC does not advance within N cycles
- `ibuffer_timeout` — fires if the instruction buffer stalls (e.g., waiting on L1 read)

On timeout expiry, an interrupt is raised to BRISC (via `o_trisc_timeout_intp`), allowing firmware to detect and recover from a hung kernel without a full chip reset.

**BRISC-controlled reset PC:** BRISC can override the reset-entry PC for each TRISC independently via `o_trisc0_reset_pc` / `o_trisc1_reset_pc` / `o_trisc2_reset_pc` / `o_trisc3_reset_pc` registers, enabling dynamic kernel dispatch without re-flashing the IMEM.

### 2.4 FPU — Floating Point Unit

#### 2.4.1 Architecture Rationale

**RTL-verified (tt_fpu_tile.sv, tt_tensix_pkg.sv):**

The FPU is **2 instances of `tt_fpu_tile`** (referred to as G-Tiles, `NUM_GTILES=2`). Each G-Tile is a **single unified multiplier array** that supports multiple operation modes selected by instruction tag bits — there are **no physically separate M-Tile or G-Tile sub-units**:

| Mode name | Instruction tag bit | Physical hardware |
|-----------|-------------------|-------------------|
| G-Tile (FP32 GEMM) | `fp32_acc=1` | `tt_fpu_tile` multiplier array |
| M-Tile (INT8 GEMM) | `int8_op=1` | Same `tt_fpu_tile`, different operand interpretation |
| FP-Lane (element-wise) | separate `fp_lane` path | Sub-pipeline **inside** `tt_fpu_tile` (`FP_LANE_PIPELINE_DEPTH=5`) |

"G-Tile" and "M-Tile" are **software-level names for operation modes** of the same hardware. A single G-Tile instance executes one mode per clock cycle based on the MOP instruction tag (`int8_op`, `fp32_acc`, `fidelity_phase`). They cannot run simultaneously in different modes.

**Why one unified array instead of separate units:** Separate FP32 and INT8 multiplier arrays would double the FPU area for workloads that use only one mode at a time. A unified multiplier array with mode bits reuses the same Booth multiplier columns for both FP and INT operand encodings, saving significant area with no throughput loss for single-mode kernels.

```
Per Tensix tile: 2 × tt_fpu_tile (G-Tile[0], G-Tile[1])

Each tt_fpu_tile:
┌────────────────────────────────────────────────────────┐
│  SRCA input (from SRCA register file)                  │
│  SRCB input (from L1 via unpack engine)                │
│                                                        │
│  Unified multiplier array (MULT_PAIRS=8 per row)       │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Mode: fp32_acc=1  → FP32/FP16B GEMM            │  │
│  │  Mode: int8_op=1   → INT8×INT8→INT32 GEMM       │  │
│  │  Mode: fp32_acc=0, int8_op=0 → INT16 GEMM       │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  FP-Lane sub-pipeline (FP_LANE_PIPELINE_DEPTH=5)       │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Element-wise: mul, add, cmp, cast               │  │
│  │  Formats: FP32/FP16B/FP16/FP8 E4M3/E5M2         │  │
│  │  Outputs: fp_lane_result / fp_lane_valid         │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  → writes to DEST register file (12,288 × 32b)         │
└────────────────────────────────────────────────────────┘
```

TRISC2 sequences MOP instructions → MOP decoder → dispatches to the G-Tile with appropriate mode bits. Each MOP cycle activates one mode; consecutive MOPs can switch modes freely (e.g., INT8 GEMM MOP followed by FP-Lane descale MOP).

#### 2.4.2 RTL Parameters

| Parameter        | Value | Verification Note                                                  |
|------------------|-------|--------------------------------------------------------------------|
| `FP_TILE_COLS`   | `16`  | `localparam` in `tt_tensix_pkg.sv`; `FP_TILE_COLS=16` is fixed for Trinity N4 project |
| `NUM_GTILES`     | `2`   | `localparam NUM_GTILES = 2` in `tt_tensix_pkg.sv` line 79           |
| `MULT_PAIRS`     | `8`   | `localparam MULT_PAIRS = 8` in `tt_fpu_tile.sv` line 118            |
| `FP_LANE_PIPELINE_DEPTH` | `5` | `tt_fpu_tile.sv` parameter default line 51                |
| RISC data bus    | 128b  | `FP_TILE_COLS=16` with 8-bit elements = 128-bit RISC register bus   |

#### 2.4.3 G-Tile (`tt_fpu_tile`) — Physical Hardware Instance

The G-Tile is the actual physical hardware (`tt_fpu_tile`). `NUM_GTILES=2` instances exist per Tensix tile. Each instance is a unified multiplier array operating in one of three modes per MOP cycle:

| Attribute             | Detail                                                    |
|-----------------------|-----------------------------------------------------------|
| MAC count             | 32 FMA units in parallel                                  |
| Accumulation format   | FP32                                                      |
| Multiplier type       | Booth-encoded (radix-4 Booth recoding)                    |
| Reduction structure   | Wallace/Dadda compressor trees before the adder stage     |
| Input operands        | SRCA (one row of the A matrix), SRCB (one column of B)    |
| Output                | Accumulated FP32 into DEST register file                  |
| Typical use           | FP32 training GEMM, FP16B weight GEMM                     |

The compressor tree design reduces the partial-product summation to a two-operand addition in the last stage, achieving single-cycle throughput per MAC tile row at the `i_ai_clk` frequency.

#### 2.4.4 INT8/INT16 Mode ("M-Tile") — Operation Mode of G-Tile

"M-Tile" is a software name for the G-Tile running with `int8_op=1`. No separate physical M-Tile block exists. This mode targets quantized inference workloads:

| Attribute             | Detail                                                         |
|-----------------------|----------------------------------------------------------------|
| Mode A                | INT16 × INT16 → INT32 (full INT16 throughput)                  |
| Mode B                | INT8 × INT8 → INT32 (4× element throughput vs Mode A)          |
| Accumulation format   | INT32 (in DEST register file)                                  |
| Stochastic rounding   | LFSR-based noise added to INT32 before truncation to FP16B/INT8 on writeback |
| Typical use           | Quantized LLM weight-matrix multiply (INT16 or INT8 weights × INT8/INT16 activations) |

The 4× INT8 throughput comes from packing two INT8 values into each INT16 input lane and computing two MAC results per cycle per lane.

#### 2.4.5 FP-Lane — Sub-Pipeline Inside `tt_fpu_tile`

FP-Lane is a sub-pipeline embedded within each `tt_fpu_tile` (`FP_LANE_PIPELINE_DEPTH=5` stages, outputs `fp_lane_result`/`fp_lane_valid`). It handles element-wise vector operations at mixed precision:

| Attribute             | Detail                                                    |
|-----------------------|-----------------------------------------------------------|
| Vector width          | 16 or 32 elements per cycle (mode-dependent)              |
| Supported operations  | Multiply, add, compare, min/max, format cast              |
| Supported formats     | FP32, FP16B (BFloat16), FP16 (IEEE 754), FP8 E4M3, FP8 E5M2 |
| Input source          | DEST register file (reads elements in-place)              |
| Output destination    | DEST register file (writes results back in-place)         |
| Typical use           | Scale (descale), bias add, ReLU/Leaky-ReLU, format conversion before NoC output |

FP-Lane operates independently of G-Tile/M-Tile. A common kernel pattern is:
1. M-Tile computes INT32 GEMM into DEST
2. FP-Lane descales (INT32 × scale → FP16B) in-place on DEST
3. SFPU applies activation (e.g., GELU) in-place on DEST
4. TRISC0 (pack) reads DEST and writes FP16B results to L1 or NoC

### 2.5 SFPU — Scalar Floating Point Unit

#### 2.5.1 Architecture Rationale

The SFPU is a **scalar coprocessor** attached to the FPU datapath, operating directly on entries in the DEST register file. It is separate from G-Tile/M-Tile/FP-Lane because transcendental functions (exp, log, sqrt, tanh) require **iterative multi-cycle computation** — adding these to the main MAC array would stall the entire datapath pipeline. By running the SFPU as an asynchronous coprocessor on DEST data, the MAC array can be simultaneously reloaded with the next tile while the SFPU processes the current tile's results.

A typical softmax kernel illustrates this:
1. M-Tile computes raw logit scores → DEST (INT32)
2. FP-Lane descales INT32 → FP32 in-place
3. **SFPU exp** computes e^x for each element in DEST
4. FP-Lane sums all exp values (reduce), then SFPU computes recip of the sum
5. FP-Lane multiplies each exp value by the recip → normalized softmax probabilities

Without SFPU, step 3 would require firmware to read DEST into L1, call a software exp table lookup per element, and write back — orders of magnitude slower.

#### 2.5.2 Supported Operations

| Operation | Algorithm                                              | Primary Use Case                         |
|-----------|--------------------------------------------------------|------------------------------------------|
| `exp`     | Range reduction + Taylor series polynomial approx     | Softmax, attention score normalization   |
| `log`     | Exponent-field extraction + polynomial correction     | Cross-entropy loss, log-softmax          |
| `sqrt`    | Newton-Raphson iteration (2–3 rounds)                 | Layer norm, RMS norm                     |
| `recip`   | Newton-Raphson iteration (1/x)                        | Normalization, division                  |
| `gelu`    | Approx: x·Φ(x) using tanh(√(2/π)(x+0.044715x³))     | GELU activation (BERT, GPT-style models) |
| `tanh`    | Rational polynomial approximation                     | LSTM gates, GELU sub-expression          |
| `lrelu`   | max(αx, x) with programmable α                        | Leaky ReLU activation                    |
| `cast`    | Format-convert with optional stochastic rounding      | FP32↔FP16B↔FP16↔INT8 conversion         |

#### 2.5.3 Operational Details

- **Operand source/destination:** DEST register file (in-place read-modify-write)
- **Throughput:** One element per cycle for most operations; multi-cycle ops (sqrt, recip, exp) pipeline to ~1 element/cycle once the first result is ready
- **MOP burst:** TRISC2 issues a single MOP opcode specifying the operation and a range of DEST entries; the SFPU processes up to 32 elements per MOP burst
- **Native format:** FP32; FP16B and FP16 inputs are silently promoted to FP32 before SFPU processing and demoted on writeback
- **Clock domain:** `i_ai_clk` (same as DEST register file)

#### 2.5.4 Integration with FPU Pipeline

```
DEST Register File
      │          ▲
      │ (read)   │ (write back)
      ▼          │
   ┌──────────────────┐
   │       SFPU       │
   │  exp / log / ... │
   └──────────────────┘

  TRISC2 issues MOP → SFPU operates on DEST range
  independently of MAC array (G/M-Tile idle or loading next tile)
```

The SFPU has no direct connection to SRCA/SRCB — it only sees DEST. For operations that require two operands (e.g., fused multiply-add on activation), FP-Lane is used instead.

### 2.6 L1 SRAM — tt_t6_l1_partition

#### 2.6.1 Architecture Rationale

The L1 SRAM is the **central on-tile data memory** — shared by BRISC, all four TRISCs, the FPU pack/unpack engines, and the NoC DMA path. In N1B0 the L1 is expanded to **256 macros per tile (768KB/tile, 9.216MB total across 12 tiles)**, a 4× increase versus the 64-macro/192KB baseline.

**Why 4× expansion?** LLM inference requires storing large K_tile weight slices and KV-cache activations on-tile without off-chip spill. With 192KB, the maximum K_tile for a 4096-dimensional attention layer is limited to ≈384 elements (FP16B); with 768KB the same layer can hold a K_tile of up to 4096, enabling the full attention head in a single pass. The larger L1 also allows the unpack engine to double-buffer weight tiles — loading tile N+1 while tile N is being computed — eliminating load stalls at the FPU.

#### 2.6.2 Physical Parameters

| Parameter            | N1B0 Value                        | Baseline Value        |
|----------------------|-----------------------------------|-----------------------|
| Module name          | `tt_t6_l1_partition`              | same                  |
| Macros per tile      | 256                               | 64                    |
| Macro geometry       | 128 rows × 256 bits               | same                  |
| Macro capacity       | 3KB per macro (128 × 256b / 8)    | same                  |
| **Total per tile**   | **768KB**                         | 192KB                 |
| Total (12 tiles)     | **9.216MB**                       | 2.304MB               |
| Bus width to NoC     | 512-bit (dedicated side channel)  | 512-bit               |
| Bus width to FPU     | 512-bit (SRCA/SRCB load path)     | 512-bit               |
| ECC                  | SECDED per macro                  | same                  |

#### 2.6.3 Port Structure

The L1 partition exposes multiple independently addressable ports to support concurrent access from different agents:

| Port Class        | Count | Users                                               |
|-------------------|-------|-----------------------------------------------------|
| `RD_PORT`         | 8     | BRISC reads, TRISC reads, unpack engine input ports |
| `RW_PORT`         | 6     | Pack engine write-back, general TDMA read-modify    |
| `WR_PORT`         | 8     | NoC DMA write, pack engine output                   |

Bank selection is determined by address hashing. The hash function is configurable via `GROUP_HASH_FN0` / `GROUP_HASH_FN1` CSRs to allow tile programmers to tune bank conflict rates for specific tensor shapes.

#### 2.6.4 Address Map (Logical Layout within L1)

```
L1 Logical Layout (768KB total per tile)
────────────────────────────────────────────────────
0x00000 – 0x05FFF   BRISC data region (24KB)
0x06000 – 0x15FFF   TRISC0 IMEM — pack LLK code (64KB)
0x16000 – 0x25FFF   TRISC1 IMEM — unpack LLK code (64KB)
0x26000 – 0x35FFF   TRISC2 IMEM — math LLK code (64KB)
0x36000 – 0x45FFF   TRISC3 IMEM — optional aux (64KB)
0x46000 – 0xBFFFF   Tensor workspace (~488KB)
────────────────────────────────────────────────────
  ↑ TDMA uses tensor workspace for weight tiles,
    activation buffers, and KV-cache storage.
```

BRISC copies TRISC firmware images into the IMEM regions before releasing TRISC resets.

#### 2.6.5 Datapath Connections

```
                   ┌──────────────────────────────────┐
                   │       tt_t6_l1_partition          │
                   │         (256 macros, 768KB)       │
                   └──┬─────┬──────┬──────┬───────────┘
                      │     │      │      │
               BRISC  │  TRISC  Unpack  Pack
               data   │  IMEM   engine  engine
               bus    │         │       │
                      │         ▼       │
                      │    SRCA/SRCB RF │
                      │         │       │
                      │         ▼       │
                      │       FPU       │
                      │         │       │
                      │         ▼       │
                      │       DEST RF   │
                      │                 │
                      ▼                 ▼
               NoC side channel     Pack writes
               (512-bit DMA)        back to L1
```

#### 2.6.6 512-Bit NoC Side Channel

A dedicated 512-bit bus connects the L1 directly to the NoC local port, **bypassing the BRISC data path entirely**. This enables:
- Zero-overhead DMA: TDMA engine initiates a transfer; L1 data flows directly into NoC flits at one 512-bit flit per `noc_clk` cycle
- BRISC CPU is not involved in data movement, freeing it for control tasks
- Sustained NoC bandwidth equal to the full flit width

#### 2.6.7 ECC

Each SRAM macro implements **SECDED (Single-Error Correct, Double-Error Detect)** ECC. A single-bit error is silently corrected on read; a double-bit error sets a sticky error flag and optionally triggers an interrupt to BRISC. ECC scrubbing is managed by firmware using the `T6_L1_CSR` register set.

#### 2.6.8 Clock Domains

| Operation                    | Clock domain  |
|------------------------------|---------------|
| Tensor data move (TDMA)      | `dm_clk`      |
| Register-file access (FPU path) | `ai_clk`   |
| NoC side channel DMA         | `noc_clk`     |

CDC crossings between `ai_clk` and `dm_clk` within the L1 partition use registered boundary cells. The `noc_clk` side channel uses a synchronizer FIFO at the L1→NIU interface.

### 2.7 TDMA Engine

#### 2.7.1 Overview and Rationale

The **Tile DMA (TDMA)** engine is the data-movement fabric of the Tensix tile. It is the hardware that connects L1 memory, the FPU register files (SRCA/SRCB/DEST), and the NoC, handling all bulk tensor transfers without BRISC involvement.

TDMA operates entirely under TRISC control. TRISC2 (math) programs the MOP sequencer; TRISC1 (unpack) drives the unpack engine; TRISC0 (pack) drives the pack engine. Each is an independent pipeline stage, enabling the double-buffered compute loop described in §2.3.

**Why MOP encoding?** A single raw RISC-V instruction operates on one register or one memory word. Loading a 16×16 INT16 tensor tile from L1 into SRCA would require hundreds of load instructions. A single MOP — encoded as one or two 32-bit words — can express "load a 16×16 INT16 tile starting at L1 base address X with row stride Y into SRCA bank 0." This achieves roughly **10× instruction density** compared to raw RISC-V equivalents.

#### 2.7.2 Sub-block Description

| Sub-block       | Controlling TRISC | Function                                                                |
|-----------------|--------------------|-------------------------------------------------------------------------|
| MOP sequencer   | TRISC2             | Decodes MOP instructions; dispatches to G/M-Tile, FP-Lane, or SFPU     |
| Unpack engine   | TRISC1             | Reads L1 tensor data or incoming NoC flit; applies format conversion; loads SRCA/SRCB |
| Pack engine     | TRISC0             | Reads DEST register file; applies format conversion; writes to L1 or NoC flit |
| Address gen     | TRISC1/TRISC0      | Multi-dimensional stride/offset computation for tensor addressing (up to 4 dimensions) |

RTL file: `tt_instrn_engine.sv` (contains MOP sequencer and TDMA logic); `tt_trisc.sv` (per-thread cores).

#### 2.7.3 MOP Sequencer

The MOP sequencer receives compressed MOP instruction words from TRISC2 and expands them into a sequence of primitive datapath operations. One MOP can encode:
- Target sub-unit (G-Tile / M-Tile / FP-Lane / SFPU)
- Operand source (SRCA bank 0 or 1, SRCB row index)
- DEST target row range
- Accumulate or overwrite mode
- Loop repeat count (inner loop for tile accumulation)

The sequencer executes the expanded sequence autonomously; TRISC2 can issue the next MOP before the previous one completes, keeping the FPU continuously occupied.

#### 2.7.4 Pack Engine (TRISC0)

The pack engine reads DEST register file entries and writes formatted data to either L1 or the NoC output path:

```
DEST RF ──(read)──► Format Converter ──► [ L1 write port ]
                          │
                          └──────────────► [ NoC output flit ]
```

Format conversion options on pack path:
- INT32 → FP16B (with optional stochastic rounding)
- INT32 → INT8 (with optional stochastic rounding)
- FP32 → FP16B
- Identity (no conversion — pass through as-is)

The pack engine uses the **address generator** to compute the L1 destination address for each output element using a stride/offset model, allowing non-contiguous writes (e.g., writing rows of a transposed tile into a strided L1 region).

#### 2.7.5 Unpack Engine (TRISC1)

The unpack engine is the reverse path: reads tensor data from L1 or an incoming NoC flit and loads it into SRCA/SRCB for FPU consumption:

```
[ L1 read port ] ──► Format Converter ──► SRCA register file
[ NoC input flit ] ──────────────────────► SRCB (direct from L1 via 512-bit path)
```

Format conversion options on unpack path:
- FP16B → FP32 (for G-Tile)
- INT16 → INT16 (pass-through for M-Tile)
- INT8 → INT16 (for M-Tile INT8 mode, packing two INT8 per lane)
- FP8 (E4M3/E5M2) → FP16 (for FP-Lane)

#### 2.7.6 Address Generator

The address generator supports **up to 4 dimensions** of tensor addressing, matching the iDMA address generation structure. Each dimension has:
- `base`: starting address
- `stride`: byte increment per element in this dimension
- `size`: number of elements in this dimension

This allows a single MOP to traverse a row, column, or arbitrary slice of a multi-dimensional tensor stored in L1 without software looping overhead.

#### 2.7.7 Double-Buffered Pipeline

The canonical double-buffered compute loop enabled by TDMA:

```
Cycle epoch N:
  TRISC1 (unpack):  L1[tile N+1] → SRCA bank 1   (prefetch next)
  TRISC2 (math):    SRCA bank 0 + SRCB → DEST     (compute current)
  TRISC0 (pack):    DEST → L1[output N-1]          (drain previous)

Cycle epoch N+1:
  TRISC1 (unpack):  L1[tile N+2] → SRCA bank 0   (prefetch next)
  TRISC2 (math):    SRCA bank 1 + SRCB → DEST     (compute current)
  TRISC0 (pack):    DEST → L1[output N]            (drain previous)
```

Sync barriers (hardware semaphores) gate each transition: TRISC1 signals "bank filled," TRISC2 waits on that signal before firing its MOP, TRISC2 signals "DEST ready," TRISC0 waits before reading DEST.

### 2.8 Destination Register File

#### 2.8.1 Architecture Rationale

The DEST register file is the **accumulation buffer** for all FPU outputs. It is implemented as a **latch array** rather than an SRAM macro for two reasons:
1. **Read latency:** Latch arrays have lower read latency than SRAM macros (no precharge cycle), which is critical when the pack engine reads DEST on every clock cycle.
2. **Access pattern:** DEST is read and written at single-element granularity by the FPU MAC array, which favors a register-file-style implementation over block-access SRAM.

#### 2.8.2 Physical Parameters

| Parameter          | Value                              |
|--------------------|------------------------------------|
| Entries per tile   | 12,288                             |
| Width per entry    | 32 bits                            |
| Total per tile     | 393,216 bits ≈ 48KB (latch array)  |
| Implementation     | Latch array (not SRAM)             |
| Clock domain       | `i_ai_clk`                         |

#### 2.8.3 Double-Buffer Operation

DEST is **hardware double-buffered**: the register file is logically split into two equal halves (Buffer A and Buffer B), each holding 6,144 × 32-bit entries.

```
          FPU write path          Pack-engine read path
               │                         │
               ▼                         ▼
  ┌────────────────────────────────────────┐
  │  DEST Buffer A  (6,144 × 32b)         │◄── FPU writes (current tile)
  │  DEST Buffer B  (6,144 × 32b)         │◄── Pack reads (previous tile)
  └────────────────────────────────────────┘
              │
              ▼
     dest_toggle interrupt → BRISC
     (signals buffer swap is complete)
```

While the FPU writes results for tile N into Buffer B, the pack engine simultaneously reads Buffer A (containing results for tile N−1) and writes them to L1 or the NoC. When tile N compute is complete, a **dest_toggle** hardware event fires, signaling BRISC (and TRISC0) to swap which buffer is the "read" buffer and which is the "write" buffer.

This eliminates all stalls between the compute and pack stages of the pipeline: the FPU never waits for DEST to be drained, and the pack engine never waits for new data to arrive.

#### 2.8.4 Stochastic Rounding on Write-Back

When the pack engine converts INT32 DEST entries to lower-precision output formats (FP16B or INT8), **stochastic rounding** is applied to reduce systematic quantization bias:

1. An **LFSR** (Linear Feedback Shift Register) inside the FPU generates a pseudo-random bit pattern
2. The low-order bits of the INT32 DEST value are XOR'd with the LFSR output before truncation
3. This adds a uniform random dither in the range [0, 1 LSB) of the output format
4. Over many values, the rounding error has zero mean — eliminating the systematic downward bias of truncation

Stochastic rounding is enabled/disabled per-format via firmware MOP control words. It is always disabled for FP32 output (no precision loss).

#### 2.8.5 Address Space

DEST entries are addressed by the FPU as a two-dimensional structure matching the FPU tile output layout:
- **Row index:** selects a row of the output tile (0 to tile_rows−1)
- **Column index:** selects a column within the row (0 to `FP_TILE_COLS−1` = 15)
- **Format width:** when writing FP32, each entry is 32 bits; INT16 mode packs two results per entry

TRISC0 pack engine and TRISC2 math engine both address DEST using this two-dimensional scheme, coordinated by the double-buffer toggle.

### 2.9 SRCA Register File

#### 2.9.1 Architecture Rationale

SRCA holds the **A-operand** (typically the weight matrix tile) presented to G-Tile and M-Tile for each compute cycle. It is a latch array — same reasoning as DEST: low read latency, single-element access pattern, and tight timing integration with the FPU MAC array.

SRCB is **not** an independent register file. Instead, SRCB is sourced directly from L1 via a dedicated 512-bit read path in the unpack engine. This asymmetry reflects the typical GEMM access pattern: the A-matrix (weights) is re-used across multiple output rows (loaded once into SRCA, used many times), while the B-matrix (activations) streams through one row at a time and does not benefit from a large staging register.

#### 2.9.2 Physical Parameters

| Parameter          | Value                              |
|--------------------|------------------------------------|
| Entries per tile   | 1,536                              |
| Width per entry    | 32 bits                            |
| Total per tile     | 49,152 bits = 6KB (latch array)    |
| Implementation     | Latch array (not SRAM)             |
| Clock domain       | `i_ai_clk`                         |
| Loaded by          | TRISC1 unpack engine               |
| Consumed by        | TRISC2 → G-Tile / M-Tile           |

#### 2.9.3 Double-Buffer Operation

SRCA is **hardware double-buffered** with two equal halves (Bank 0 and Bank 1), each holding 768 × 32-bit entries:

```
          Unpack-engine write path        FPU read path
               │                               │
               ▼                               ▼
  ┌────────────────────────────────────────────┐
  │  SRCA Bank 0  (768 × 32b)                  │◄── Unpack fills (next tile)
  │  SRCA Bank 1  (768 × 32b)                  │◄── FPU reads   (current tile)
  └────────────────────────────────────────────┘
              │
              ▼
     srca_toggle interrupt → BRISC
     (signals bank swap is complete)
```

While the FPU consumes Bank 1 (current tile), TRISC1 fills Bank 0 (next tile) from L1. On completion, the **srca_toggle** hardware event fires, swapping the roles of the two banks. This eliminates all unpack stalls in the compute pipeline.

#### 2.9.4 SRCA vs SRCB Summary

| Attribute        | SRCA                                  | SRCB                                     |
|------------------|---------------------------------------|------------------------------------------|
| Implementation   | Latch array (dedicated RF)            | L1 SRAM read path (no separate RF)       |
| Capacity         | 1,536 × 32b (6KB)                     | Full L1 tensor workspace (up to 768KB)   |
| Double-buffer    | Yes (Bank 0 / Bank 1, HW toggle)      | SW-managed via L1 address aliasing       |
| Typical content  | Weight matrix tile (reused)           | Activation matrix tile (streaming)       |
| Loaded by        | TRISC1 unpack engine                  | TRISC1 unpack engine (different path)    |

### 2.10 Clock Domain Summary (Tensix Tile)

#### 2.10.1 Per-Column Clock Architecture

In N1B0, the `ai_clk` and `dm_clk` inputs to each Tensix tile are **per-column** — column X receives `i_ai_clk[X]` and `i_dm_clk[X]` independently. The `noc_clk` is shared across all tiles (single global `i_noc_clk`). This per-column architecture allows harvest isolation: a harvested column has its clock gated at the column boundary without disturbing the clock network of adjacent columns.

#### 2.10.2 Clock Domain Table

| Domain     | Source wire     | Frequency relationship | Covers in Tensix tile                               |
|------------|-----------------|------------------------|------------------------------------------------------|
| `ai_clk`   | `i_ai_clk[X]`  | Fastest (compute)      | BRISC, TRISC0–3, FPU (G/M/FP-Lane/SFPU), DEST RF, SRCA RF |
| `dm_clk`   | `i_dm_clk[X]`  | May be lower than ai   | TDMA MOP sequencer, pack/unpack engines, L1 SRAM array clocking |
| `noc_clk`  | `i_noc_clk`    | Global, fixed          | NoC local port, flit FIFOs (VC buffers), overlay NIU, EDC ring segment |

In a typical N1B0 operating point, `ai_clk` and `dm_clk` may be driven at the same frequency from the same PLL output, or at different ratios depending on power/performance mode.

#### 2.10.3 CDC Crossings within the Tensix Tile

Three CDC crossings exist inside the Tensix tile hierarchy (confirmed at Y=2 tiles per §M19):

| Crossing          | Source domain | Dest domain | Mechanism                              | Location              |
|-------------------|---------------|-------------|----------------------------------------|-----------------------|
| AI → NoC          | `ai_clk`      | `noc_clk`   | Synchronizer FIFO in overlay wrapper   | Overlay NIU interface |
| NoC → AI          | `noc_clk`     | `ai_clk`    | Synchronizer FIFO in overlay wrapper   | Overlay NIU interface |
| AI → DM           | `ai_clk`      | `dm_clk`    | Registered boundary cells in L1 partition | L1 register-file path |

`DISABLE_SYNC_FLOPS=1` is a module parameter that bypasses intra-domain synchronizers when the source and destination are known to share the same clock (e.g., when `ai_clk` and `dm_clk` are driven from the same source). This is set at integration time by the top-level and must not be applied across genuine asynchronous domain boundaries.

#### 2.10.4 Clock Gating and Harvest Interaction

The overlay wrapper (`tt_neo_overlay_wrapper`) contains clock gate cells for each sub-domain within the tile. During harvest, a harvested tile's `i_ai_clk[X]` and `i_dm_clk[X]` are gated at the column clock tree, and the isolation cells (`ISO_EN[X+4*Y]`) hold all output signals at safe values (see §5 Harvest). The `noc_clk` domain for a harvested tile is also gated at the NIU level to prevent spurious flit activity.

#### 2.10.5 EDC Clock Allocation

Each EDC node within the Tensix tile receives its own clock independently from the ring traversal path (see §M1, §M19). The EDC clock is derived from the same `i_ai_clk[X]` / `i_noc_clk` source depending on which clock domain the EDC node monitors. Repeaters on the EDC ring path are combinational (no registered stages in the inter-node path); all flip-flops are inside `tt_edc1_node` instances.

---

## §3 NOC2AXI Composite Tiles

### 3.1 Overview

Two composite tiles provide the bridge between the internal NoC fabric and the external AXI host interface:

| Instance    | Grid Span  | RTL Module                          |
|-------------|------------|--------------------------------------|
| NE_OPT      | X=1, Y=3–4 | `trinity_noc2axi_router_ne_opt.sv`  |
| NW_OPT      | X=2, Y=3–4 | `trinity_noc2axi_router_nw_opt.sv`  |

Each composite tile physically spans two rows. The Y=4 portion contains the NIU (NOC-to-AXI bridge) and the Y=3 portion contains the router row. Internal cross-row flit wires connect the two portions without going through the top-level NoC mesh.

```
┌─────────────────────────────────────────────┐
│     NOC2AXI_ROUTER_NW_OPT / NE_OPT          │
│     (Composite tile spanning Y=3 and Y=4)   │
│                                              │
│  Y=4  ┌──────────────────────────────────┐  │
│       │         NIU (tt_noc2axi)          │  │
│       │  ┌─────────────┐ ┌─────────────┐ │  │
│       │  │ NOC→AXI     │ │ AXI→NOC     │ │  │
│       │  │ Bridge      │ │ Bridge      │ │  │
│       │  └─────────────┘ └─────────────┘ │  │
│       │  ┌──────┐ ┌─────┐ ┌───────────┐ │  │
│       │  │ ATT  │ │ SMN │ │ EDC node  │ │  │
│       │  │ 64e  │ │ 8rng│ │ (BIU)     │ │  │
│       │  └──────┘ └─────┘ └───────────┘ │  │
│       │       AXI Master (512b/56b)      │  │
│       └────────────┬─────────────────────┘  │
│         cross-row flit wires (north↔south)   │
│       ┌────────────┴─────────────────────┐  │
│  Y=3  │       Router (tt_trinity_router)  │  │
│       │  ┌──────────────────────────────┐│  │
│       │  │ 5-port DOR/dynamic router    ││  │
│       │  │ 4 virtual channels           ││  │
│       │  │ REP_DEPTH_LOOPBACK=6         ││  │
│       │  │ EDC node (Y=3)               ││  │
│       │  └──────────────────────────────┘│  │
│       └──────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### 3.2 NIU — NOC-to-AXI Bridge (Y=4 portion)

The NIU (`tt_noc2axi`) translates between the internal 512-bit NoC flit protocol and the external 512-bit AXI4 master bus.

#### 3.2.1 NOC2AXI Path (inbound: chip→DRAM)

1. NoC flit arrives at local port (512 bits, includes header with destination address)
2. Header decoded: flit_type, x_coord, y_coord, EndpointIndex extracted
3. ATT lookup: 56-bit AXI address computed from 32-bit NoC address using mask/endpoint table
4. AXI write transaction issued: AWADDR (56-bit), WDATA (512-bit), WSTRB

#### 3.2.2 AXI2NOC Path (outbound: DRAM→chip)

1. AXI read response data (512-bit) arrives from external memory
2. Return address from original NoC request header used to construct response flit
3. Flit injected back into NoC at local port, routed to requesting tile

#### 3.2.3 ATT — Address Translation Table

| Parameter   | Value           |
|-------------|-----------------|
| Entries     | 64              |
| Fields      | mask, endpoint, routing |
| Purpose     | Maps 32-bit NoC address → 56-bit AXI address |
| Access      | APB register interface (SMN-controlled)     |

The ATT enables flexible memory-mapped address remapping. Each entry provides:
- **mask**: which bits of the incoming address are matched
- **endpoint**: target EndpointIndex or AXI region
- **routing**: override routing flags for the translated address

#### 3.2.4 SMN — Security Manager (8-range checker)

The SMN (Secure Memory Node) enforces access control on all AXI transactions issued by the NIU.

| Parameter      | Value                                      |
|----------------|--------------------------------------------|
| Number of ranges | 8                                        |
| Granularity    | Configurable base/size per range           |
| Actions        | Allow, block (return slave error), log     |
| Configuration  | APB registers at 0x03010000 (325 regs)     |

Each range can independently restrict read/write access. Violations generate a `slv_ext_error` signal that propagates to the overlay error logic.

#### 3.2.5 AXI Interface Parameters

| Parameter     | Value                                     |
|---------------|-------------------------------------------|
| Data width    | 512 bits                                  |
| Address width | 56 bits (physical) mapped via gasket to 64-bit AXI |
| ID width      | As configured per instance               |
| Protocol      | AXI4 (full)                               |
| AxUSER        | Carries security/routing metadata         |

The 56-bit address gasket layout:

```
Bits [55:48] — 8-bit region/endpoint tag
Bits [47:32] — 16-bit upper address
Bits [31: 0] — 32-bit lower address (NoC address field)
```

### 3.3 Router (Y=3 portion)

The router row within the composite tile instantiates `tt_trinity_router` with parameters specific to its position at Y=3.

**Key router parameters for composite tiles:**

| Parameter                     | NE_OPT (X=1) | NW_OPT (X=2) |
|-------------------------------|--------------|--------------|
| `REP_DEPTH_LOOPBACK`          | 6            | 6            |
| `OUTPUT`                      | 4            | 4            |
| West port repeaters (in+out)  | 4            | 1            |
| South port repeaters (in+out) | 5            | —(default)   |
| East port repeaters (in+out)  | 1            | 3            |
| North port repeaters (in+out) | 1            | 1            |

> RTL-verified: `trinity_noc2axi_router_ne_opt.sv` (West=4, South=5, East=1, North=1); `trinity_noc2axi_router_nw_opt.sv` (West=1, East=3, North=1). NE/NW have asymmetric repeater counts because they sit at opposite ends of the X-axis with different wire lengths to their neighbors.

See §5 for full router architecture description.

### 3.4 Cross-Row Flit Wires

The NIU at Y=4 and the router at Y=3 are not connected via the top-level NoC mesh wires. Instead, dedicated cross-row flit buses pass through the composite module boundary:

- **South→North**: flit data + valid from Y=3 router local port to Y=4 NIU input
- **North→South**: flit data + valid from Y=4 NIU output to Y=3 router local port

These wires are 512 bits wide (one full NoC flit). They bypass the standard mesh routing and are only visible inside `trinity_noc2axi_router_ne/nw_opt.sv`.

### 3.5 Clock Routing in Composite Tiles

The composite tile propagates clocks from the Y=4 entry point down to Y=3 via a clock routing chain. Nine fields are routed:

1. `i_ai_clk[col]` — passed from Y=4 to Y=3
2. `i_dm_clk[col]` — passed from Y=4 to Y=3
3. `i_noc_clk` — available at both Y levels
4. `i_axi_clk` — for AXI interface (NIU at Y=4 primarily)
5. `i_reset_n` — global reset
6. `i_axi_reset_n` — AXI domain reset
7. PRTN chain clock
8. EDC forward chain enable
9. EDC loopback chain enable

Repeaters are inserted at Y=3 (depth=6) and Y=4 (depth=4) within the clock distribution paths of the composite tile to meet setup timing across the physical distance.

### 3.6 Router Node ID and EP Offset

Within the composite tiles, router and NIU node IDs are computed with an offset of −1 relative to the tile's nominal EndpointIndex:

- EndpointIndex for (X=1, Y=4) = 9; NIU nodeid = 8
- EndpointIndex for (X=2, Y=4) = 14; NIU nodeid = 13
- The router at Y=3 similarly uses (EndpointIndex − 1) for its local ID

This offset is a design-level convention in the N1B0 implementation to align with the baseline router node ID allocation scheme.

---

### 3.7 NIU DMA Operation

The NIU (Network Interface Unit, `tt_noc2axi`) is not a passive bridge — it acts as a **DMA engine** that autonomously drives AXI bursts in response to incoming NoC packets and vice versa. There is no CPU involvement once a NoC packet enters the NIU; the NIU hardware handles all burst framing, address translation, and response routing.

#### 3.7.1 NoC Packet → AXI Burst (Write DMA)

A write transaction is initiated when a Tensix BRISC (or iDMA) injects a header flit into the NoC addressed to an external AXI endpoint. The NIU receives the full packet and converts it to an AXI write burst:

```
NoC Packet (received by NIU)
┌─────────────────────────────────────────────┐
│ Header flit: x_coord, y_coord, EndpointIdx  │
│              mcast=0, flit_type=HDR          │
│              payload: AXI target address     │
├─────────────────────────────────────────────┤
│ Data flit 0: 512-bit payload (64 bytes)      │
│ Data flit 1: 512-bit payload                 │
│  ...                                         │
│ Tail flit:   final 512-bit payload + EOP     │
└─────────────────────────────────────────────┘
         │
         ▼  NIU write DMA engine
┌─────────────────────────────────────────────┐
│ 1. Extract AXI address from header payload  │
│ 2. Run address through ATT (§3.2.3)         │
│    → translate NoC logical addr → AXI phys │
│ 3. Compute burst length = num data flits    │
│    AWLEN = (payload_bytes / 64) - 1         │
│    AWSIZE = 3'b110 (64-byte beat)           │
│ 4. Assert AWVALID with translated address   │
│ 5. Stream WDATA beats from flit buffer      │
│    (one 512-bit flit = one AXI beat)        │
│ 6. Assert WLAST on tail flit beat           │
│ 7. Wait for BVALID (write response)         │
│ 8. On BRESP error → slv_ext_error → CRIT   │
└─────────────────────────────────────────────┘
```

Key parameters:
- **Max burst**: 256 beats × 64 bytes = 16 KB per NoC packet
- **AXI data width**: 512 bits (64 bytes per beat)
- **AXI address width**: 56-bit (mapped to 64-bit via gasket, upper bits zero-extended)
- **AWCACHE**: configurable (bufferable/cacheable per ATT entry)
- **AWPROT/AxUSER**: propagated from NoC header security level

#### 3.7.2 AXI Read Response → NoC Packet (Read DMA)

A read transaction is initiated by a NoC read-request packet. The NIU issues an AXI read burst and converts the returning AXI data beats back into a NoC response packet addressed to the original requester:

```
Step 1: NIU receives NoC READ REQUEST packet
  Header flit contains:
    - AXI read address (logical)
    - Return path: src_x, src_y, src_endpoint (requester's address)
    - Byte count / burst length

Step 2: NIU issues AXI read burst
  ARADDR  = ATT-translated address
  ARLEN   = (requested_bytes / 64) - 1
  ARSIZE  = 3'b110 (64 bytes/beat)
  ARVALID = 1

Step 3: NIU collects RDATA beats
  Each RDATA beat (512 bits) is stored in the NIU read-data FIFO
  (RDATA FIFO depth: 512 entries in N1B0, configurable 32–1024)

Step 4: NIU constructs NoC RESPONSE packet
  Header flit: src_x/y/endpoint from original request (reversed)
  Data flits:  RDATA beats converted 1:1 to 512-bit NoC flits
  Tail flit:   last RDATA beat + RLAST marker

Step 5: NIU injects response packet into NoC
  Router at Y=3 routes packet back to requester tile
```

The RDATA FIFO depth (default 512 in N1B0) determines how many outstanding read beats the NIU can absorb before applying back-pressure on RREADY. This is critical for latency-hiding: with depth=512, the NIU can tolerate up to 512 × 64B = 32 KB of in-flight read data.

#### 3.7.3 Address Translation (ATT)

Before any AXI transaction is issued, the NIU passes the NoC logical address through the ATT (Address Translation Table):

```
ATT entry format (64 entries per NIU):
  ┌──────────┬──────────┬────────────────┬──────────┐
  │  MASK    │  MATCH   │  OFFSET/BASE   │  ATTR    │
  │ [55:0]   │ [55:0]   │ [55:0]         │ [7:0]    │
  └──────────┴──────────┴────────────────┴──────────┘

Translation:
  if (addr & MASK) == MATCH:
      axi_addr = (addr & ~MASK) | OFFSET
      apply ATTR (cacheable, bufferable, security level)
```

- 64 entries scanned in priority order (entry 0 = highest priority)
- No match → transaction blocked, `slv_ext_error` asserted → CRIT interrupt
- ATT is programmed by firmware at boot via APB slave registers on the NIU

#### 3.7.4 Descriptor Flow (Firmware Perspective)

Unlike iDMA (which has explicit SW-managed descriptor rings), NIU DMA is **implicit** — it is driven directly by NoC packet injection. Firmware controls NIU DMA by:

1. **Configuring ATT** (once at boot): map logical NoC addresses to physical AXI addresses
2. **Configuring SMN ranges** (once at boot): set access permissions per address range
3. **Issuing NoC packets** (at runtime): BRISC or iDMA injects NoC packets addressed to the NIU endpoint; the NIU autonomously drives the AXI burst

There is no explicit descriptor ring or doorbell register for NIU DMA. The NoC packet header encodes all necessary information (address, length, direction).

```c
// Example: BRISC firmware initiating a 4KB write to DRAM via NIU
// (conceptual — actual write uses BRISC NOC write instructions)

// ATT must be pre-configured:
//   Entry 0: MASK=0xFFFFF000, MATCH=0x80000000, OFFSET=0x80000000

// BRISC issues NOC write:
//   dst_x=1 (NIU NW_OPT), dst_y=4
//   address=0x80001000   (4KB-aligned DRAM target)
//   data=<64 × 512-bit flits>  (4096 bytes)

// NIU hardware:
//   1. Receives 65 flits (1 header + 64 data)
//   2. Translates 0x80001000 via ATT → AXI addr 0x80001000
//   3. Issues AWADDR=0x80001000, AWLEN=63 (64 beats), AWSIZE=6
//   4. Streams 64 × 512-bit WDATA beats
//   5. Asserts WLAST on beat 63
//   6. Waits for BRESP → done (no interrupt to BRISC)
```

#### 3.7.5 Error Handling

| Error Condition | NIU Response | System Effect |
|----------------|--------------|---------------|
| ATT miss (no matching entry) | Block transaction, assert `slv_ext_error` | CRIT interrupt via EDC ring |
| SMN range violation | Block transaction, log in SMN registers | CRIT interrupt |
| AXI BRESP=SLVERR/DECERR | Assert `slv_ext_error` | CRIT interrupt |
| AXI RRESP=SLVERR/DECERR | Drop response, assert error flag | CRIT interrupt |
| RDATA FIFO overflow | Back-pressure RREADY (hardware flow control) | No error — stalls AXI read |
| NoC flit CRC error | EDC ring detects, marks packet bad | Severity per EDC node config |

### 3.8 Standalone NIU Tiles — NOC2AXI_NE_OPT / NOC2AXI_NW_OPT (X=0,X=3 at Y=4)

#### 3.8.1 Overview

In addition to the two composite NOC2AXI_ROUTER tiles (X=1/X=2, spanning Y=3–4), the N1B0 grid includes two **standalone NIU tiles** at the corners of row Y=4:

| Instance        | Grid Position | RTL Module                      | EndpointIndex |
|-----------------|---------------|---------------------------------|---------------|
| NOC2AXI_NE_OPT  | (X=0, Y=4)    | `trinity_noc2axi_ne_opt.sv`     | 4             |
| NOC2AXI_NW_OPT  | (X=3, Y=4)    | `trinity_noc2axi_nw_opt.sv`     | 19            |

RTL-verified: `GridConfig[Y=4][X=0] = NOC2AXI_NE_OPT`, `GridConfig[Y=4][X=3] = NOC2AXI_NW_OPT`.

These are **single-row tiles** — they occupy Y=4 only and have no Y=3 router row. They provide a full NIU (NOC-to-AXI bridge) with ATT, SMN, and an AXI master interface, but are architecturally simpler than the composite tiles.

```
  Grid row Y=4 overview:

  X=0                X=1               X=2               X=3
  ┌────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐
  │  NE_OPT    │  │ ROUTER_NW_  │  │ ROUTER_NE_  │  │  NW_OPT    │
  │ (standalone│  │ OPT Y=4 NIU │  │ OPT Y=4 NIU │  │ (standalone│
  │  NIU only) │  │ (composite) │  │ (composite) │  │  NIU only) │
  └────────────┘  └─────────────┘  └─────────────┘  └────────────┘
      EP=4            EP=8 (−1)        EP=13 (−1)        EP=19
  (no offset)     (nodeid_y−1)     (nodeid_y−1)      (no offset)

  Row Y=3 (below):
  ┌────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐
  │  Dispatch  │  │ ROUTER_NW_  │  │ ROUTER_NE_  │  │  Dispatch  │
  │   West     │  │ OPT Y=3 Rtr │  │ OPT Y=3 Rtr │  │   East     │
  └────────────┘  └─────────────┘  └─────────────┘  └────────────┘
```

#### 3.8.2 Why Standalone at X=0 and X=3

The 4×5 mesh requires NIU connectivity at all four X columns in row Y=4. The choice of standalone vs. composite depends on whether the tile at Y=3 in the same column needs an integrated router:

- **X=1, X=2 (composite)**: Y=3 positions are used by the ROUTER_NW_OPT and ROUTER_NE_OPT composite modules. Dispatch tiles need routing capability into the mesh, so X=1/X=2 composite modules integrate both NIU (Y=4) and router (Y=3) into a single module with cross-row flit wires. The router at Y=3 bridges Dispatch traffic onto the NoC mesh and funnels it up to the NIU at Y=4.
- **X=0, X=3 (standalone)**: Y=3 positions are occupied by Dispatch tiles (`tt_dispatch_top_east` at X=0 and `tt_dispatch_top_west` at X=3), which contain their own integrated NIU and NoC interface. No dedicated router tile is required at Y=3 for these columns. Therefore, the Y=4 position for X=0 and X=3 only needs a standalone NIU with no router component.

This results in a clean separation: standalone NIU tiles handle Y=4-only AXI bridging, while composite tiles handle the dual-row case where the router must physically span Y=3 to serve the Dispatch row.

#### 3.8.3 Internal Architecture

The standalone NIU tile contains the same core NIU sub-blocks as the composite tile's Y=4 portion, but without any router logic or cross-row wiring:

```
  trinity_noc2axi_ne_opt / trinity_noc2axi_nw_opt (single-row, Y=4 only)
  ┌─────────────────────────────────────────────────────────┐
  │                   Standalone NIU Tile                    │
  │                                                          │
  │    NoC mesh local port (at mesh position X, Y=4)         │
  │         │  (512-bit flit in/out, standard mesh port)     │
  │         ▼                           ▲                    │
  │  ┌──────────────────────────────────────────────────┐   │
  │  │               tt_noc2axi (NIU core)               │   │
  │  │  ┌──────────────────┐  ┌────────────────────┐    │   │
  │  │  │  NOC2AXI Bridge  │  │  AXI2NOC Bridge    │    │   │
  │  │  │  (chip→DRAM)     │  │  (DRAM→chip resp.) │    │   │
  │  │  └──────────────────┘  └────────────────────┘    │   │
  │  │  ┌──────────────┐  ┌──────────┐  ┌──────────┐   │   │
  │  │  │ ATT (64 entry│  │ SMN      │  │ RDATA    │   │   │
  │  │  │ mask/endpoint│  │ 8-range  │  │ FIFO 512 │   │   │
  │  │  └──────────────┘  └──────────┘  └──────────┘   │   │
  │  └──────────────────────────────────────────────────┘   │
  │                          │                               │
  │            AXI Master Interface (512-bit / 56-bit addr)  │
  │                      to external memory                  │
  │                                                          │
  │  EDC node — connected to main EDC ring at Y=4 (on-ring)  │
  │  APB slave — register access via noc_clk APB bus         │
  └─────────────────────────────────────────────────────────┘
```

**Key differences from composite tiles:**

| Attribute                  | Standalone (X=0, X=3)               | Composite (X=1, X=2)                      |
|----------------------------|-------------------------------------|-------------------------------------------|
| Row span                   | Y=4 only                            | Y=3 and Y=4                               |
| Router present             | No                                  | Yes — `tt_trinity_router` at Y=3          |
| Cross-row flit wires       | None                                | Yes — 512-bit South↔North internal bus    |
| nodeid / EP offset         | None — EP used directly             | nodeid_y −1 (composite ID convention)     |
| EndpointIndex              | (X=0,Y=4)=4; (X=3,Y=4)=19          | (X=1,Y=4)→nodeid=8; (X=2,Y=4)→nodeid=13  |
| EDC ring position          | Y=4 only, directly on main ring     | Y=4 BIU is off-ring (open-port issue)     |
| REP_DEPTH_LOOPBACK         | 2 (standard)                        | 6 (N1B0 composite-specific)               |
| Clock routing chain        | Short (single row, no passthrough)  | Long — passes through both Y=4 and Y=3    |

#### 3.8.4 NoC Connectivity

The standalone NIU tiles connect to the NoC mesh at their Y=4 grid position exactly like any standard mesh node. There are no cross-row wires, no internal router instance, and no special port prefix renaming. The tile's local port attaches directly to the NoC mesh at (X, Y=4):

```
  NoC mesh at Y=4 (West→East):

  (X=0,Y=4)    (X=1,Y=4)    (X=2,Y=4)    (X=3,Y=4)
  NE_OPT       ROUTER_NW    ROUTER_NE    NW_OPT
  [local port] [local port] [local port] [local port]
       │              │             │            │
       └──────────────┴─────────────┴────────────┘
          Standard 5-port DOR mesh interconnect
          (East/West/North/South/Local)
          4 virtual channels per port
```

The standalone NIU tiles are leaf nodes at Y=4: they have no router row that could serve as a relay. NoC packets destined for external DRAM via NE_OPT or NW_OPT must be addressed with `dst_x=0/3, dst_y=4` and the correct EndpointIndex (4 or 19). No offset correction is needed in firmware because there is no composite span or nodeid_y−1 convention.

#### 3.8.5 ATT, SMN, and AXI Interface

The ATT, SMN, and AXI master interface are functionally identical to the composite tile NIU at Y=4:

- **ATT**: 64-entry mask/match/offset/attribute table. Programmed at boot via APB. Maps 32-bit NoC logical addresses to 56-bit AXI physical addresses using the same gasket format as the composite tiles (bits [55:48] = region/endpoint tag, [47:32] = upper address, [31:0] = lower address).
- **SMN**: 8 independently programmable address ranges with allow/block/log actions. Violations assert `slv_ext_error` → CRIT interrupt via overlay error aggregator.
- **AXI master**: 512-bit data, 56-bit address, AXI4 full protocol, AxUSER carries security/routing metadata. Identical to composite tile AXI port.
- **RDATA FIFO**: 512-entry depth by default (define-selectable 32–1024, same as composite tiles). Provides 32 KB of in-flight read data latency hiding.

APB register access is via the standard overlay APB bus, at base addresses consistent with the tile's position in the APB address map.

#### 3.8.6 EDC Ring Integration

The standalone NIU tiles connect their EDC node directly to the main EDC ring at Y=4. This is the **correct, fully on-ring** configuration with no off-ring connectivity issue:

- EDC node at (X=0, Y=4): on-ring; covers NIU BIU logic, ATT SRAM parity, and SMN register state
- EDC node at (X=3, Y=4): on-ring; covers same set of resources

This is in contrast to the composite tiles (X=1, X=2) at Y=4, where the NIU BIU EDC node is **off-ring** due to the open-port connectivity issue documented in the N1B0 open-signal report Rev.5 (EDC ring connectivity correction: NOC2AXI BIU at Y=4 for X=1/X=2 is not connected to the main ring forward chain in certain N1B0 configurations). The standalone tiles do not have this problem because there is no composite module boundary complicating the ring signal routing — the EDC ring enters and exits the tile through standard tile boundary ports at Y=4.

No −1 offset is applied to the standalone NIU EDC node ID. The ring visits the tile at its nominal EndpointIndex position.

#### 3.8.7 Firmware Programming Notes

Firmware initializes NE_OPT and NW_OPT standalone tiles at boot using the same APB sequence as the composite tile NIU:

1. **ATT programming**: Write 64 entries (mask, match, offset, attr) for all expected DRAM address regions. Use the same logical-to-physical address mapping scheme as composite tile ATTs to maintain a consistent NoC address space.
2. **SMN range programming**: Write 8 range entries (base, size, read-permission, write-permission) to enforce security boundaries. These are typically configured to mirror the composite tile SMN configuration.
3. **EDC verification**: During EDC ring initialization, confirm that nodes at (X=0,Y=4) and (X=3,Y=4) respond with PASS status. Unlike composite tile Y=4 EDC nodes (which are off-ring), standalone tile EDC nodes participate directly in the ring self-test.
4. **RDATA FIFO tuning**: Optionally override the RDATA FIFO depth if the workload presents particularly high read latency or high read bandwidth requirements.

The standalone NIU tiles share the same APB register layout as the composite tile NIU, so a single firmware driver can initialize all four NIU instances (NE_OPT X=0, ROUTER_NW_OPT X=1, ROUTER_NE_OPT X=2, NW_OPT X=3) with only the APB base address varying.

---

## §4 Dispatch Tiles

### 4.1 Overview

Two Dispatch tiles provide the RISC-V host processor interface for the N1B0 NPU. They are placed at opposite corners of the Y=3 row, ensuring symmetric NoC coverage over all Tensix columns:

| Instance   | tile_t enum | Position | RTL Module               |
|------------|-------------|----------|--------------------------|
| DISPATCH_E | `DISPATCH_E` = 3'd5 | (0, 3) | `tt_dispatch_top_east` |
| DISPATCH_W | `DISPATCH_W` = 3'd6 | (3, 3) | `tt_dispatch_top_west` |

> RTL-verified: `GridConfig[3][0]=DISPATCH_E` → instantiates `tt_dispatch_top_east`; `GridConfig[3][3]=DISPATCH_W` → instantiates `tt_dispatch_top_west` (`trinity.sv` lines 1447/1493 and 1572/1618). The East/West labels reflect NoC topology orientation, not physical left/right position.

**Why two Dispatch tiles?**

Two independent Dispatch tiles serve two complementary purposes:

1. **East/West NoC coverage for tensor-parallel workloads.** In tensor-parallel execution, each Dispatch tile manages programming and DMA for its half of the Tensix array. DISPATCH_E at (0,3) has the shortest NoC path to the left two Tensix columns (X=0, X=1); DISPATCH_W at (3,3) serves the right two columns (X=2, X=3). This halves the average NoC hop count from the dispatch controller to the compute tiles, reducing DMA command injection latency by up to 2 router hops.

2. **Two independent iDMA engines for parallel data loading.** Each Dispatch tile contains its own iDMA engine with 8 DMA CPUs, giving 16 total concurrent DMA channels across the chip. This enables simultaneous pre-loading of distinct weight tensor tiles to opposite halves of the Tensix array while the other half is computing, effectively hiding DRAM access latency behind Tensix compute — a key throughput enabler for LLM inference workloads.

Each Dispatch tile contains a Rocket RISC-V 64-bit core with L1/L2 caches, an iDMA engine (accessed via RoCC accelerator interface), an APB slave interface, and a NoC interface via NIU.

```
┌─────────────────────────────────────────────────────┐
│                  tt_dispatch_top_east/west           │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │           Rocket Core (RV64GC, 5-stage)       │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────┐  │  │
│  │  │ L1 ICache│  │ L1 DCache│  │    L2      │  │  │
│  │  │ (SRAM)   │  │ (SRAM)   │  │  Cache     │  │  │
│  │  └──────────┘  └──────────┘  │  (SRAM)    │  │  │
│  │                               └────────────┘  │  │
│  │  ┌────────────────────────────────────────┐   │  │
│  │  │    RoCC Interface (custom-3, 0x77)     │   │  │
│  │  │  cmd.valid / inst / rs1 / rs2          │   │  │
│  │  │  resp.valid / resp.bits / busy         │   │  │
│  │  │  ┌──────────────────────────────────┐  │   │  │
│  │  │  │          iDMA Engine             │  │   │  │
│  │  │  │  8 independent DMA CPU cores     │  │   │  │
│  │  │  │  CMD_BUF_R/W, ADDR_GEN_R/W,      │  │   │  │
│  │  │  │  SIMPLE_CMD_BUF per CPU          │  │   │  │
│  │  │  └──────────────────────────────────┘  │   │  │
│  │  └────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────┘  │
│        │ ai_clk domain ↕ CDC FIFO ↕ noc_clk domain │
│  ┌──────────────┐  ┌────────────────────────────┐  │
│  │  APB Slave   │  │    NIU (NoC interface)      │  │
│  │  (SFR access)│  │  NoC↔AXI, ATT, SMN         │  │
│  └──────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 4.2 Rocket Core

The Rocket core is a 64-bit RISC-V (RV64GC) in-order scalar processor sourced from the UC Berkeley open-source Rocket Chip generator.

| Parameter          | Value                                              |
|--------------------|----------------------------------------------------|
| ISA                | RV64GC (I + M + A + F + D + C extensions)          |
| Pipeline stages    | 5 (IF / ID / EX / MEM / WB — classic in-order)    |
| L1 I-cache         | SRAM-based, direct-mapped                          |
| L1 D-cache         | SRAM-based, write-back, direct-mapped              |
| L2 cache           | SRAM-based, set-associative, unified               |
| Clock domain       | `ai_clk` sourced from `i_ai_clk[col]`             |
| Data width         | 64-bit integer + 64-bit FP (D extension)           |

**ISA extension breakdown:**
- **I** — base 64-bit integer instruction set
- **M** — hardware integer multiply/divide
- **A** — atomic memory operations (LR/SC, AMO); used for firmware spinlocks and completion flags shared between the two Dispatch tiles
- **F/D** — single/double-precision floating point (G = IMAFD combined)
- **C** — 16-bit compressed instructions, reducing I-cache pressure for tight firmware dispatch loops

**Why in-order (not out-of-order)?**

Dispatch and DMA control is fundamentally latency-tolerant. The firmware workload consists of DMA descriptor writes, SFR configuration sequences, and polling loops — not tight floating-point compute kernels. An out-of-order processor would add significant area (reorder buffer, register rename, multiple issue ports) for negligible performance gain on this workload class. The 5-stage in-order Rocket pipeline provides sufficient throughput at much lower area and power. Rocket is the control plane; Tensix is the compute plane — the design deliberately keeps the control plane lean.

**Rocket origin and validation:** Rocket is a well-validated, widely taped-out open-source design from UC Berkeley. Its integration with the RoCC coprocessor extension interface is a standard, well-understood pattern used in numerous prior Rocket-based accelerator designs, making the iDMA engine connection low-risk from a verification standpoint.

**Firmware running on Rocket:**
The NPU runtime firmware executing on Rocket orchestrates the full NPU execution lifecycle:
1. Load Tensix firmware (BRISC kernel programs, TRISC LLK programs) from DRAM into Tensix L1s via iDMA
2. Program per-tile SFRs (CLUSTER_CTRL, T6_L1_CSR, router ATT entries) via the NoC APB path
3. Issue iDMA commands to pre-load weight tiles from DRAM into Tensix L1s
4. Release TRISC reset: write TRISC reset program counters, then deassert TRISC reset via SFR write
5. Poll `LLK_TILE_COUNTERS` or await completion interrupt for kernel finish
6. Post-process: issue iDMA commands to drain activation outputs from Tensix L1 back to DRAM

**SFR access path:** Rocket issues a load/store to a non-cacheable SFR address → L1 D-cache miss → NoC packet injected via NIU → routed to target tile APB slave → APB register write/read → response flit returns → Rocket load completes. Round-trip latency is approximately 50–100 noc_clk cycles depending on mesh distance and NoC congestion.

**Boot sequence:** At reset, Rocket fetches from a reset vector address held in a fabric SFR (configurable via APB before reset release). Firmware is pre-loaded into L2 by the host CPU before NPU power-on, or bootstrapped from external DRAM via an early iDMA sequence triggered from on-chip ROM.

### 4.3 RoCC — Rocket Custom Coprocessor Interface

The RoCC (Rocket Custom Coprocessor) interface is the standard RISC-V extension mechanism built into the Rocket pipeline. It exposes decoded custom instruction slots that route directly to an attached hardware coprocessor — in this case, the iDMA engine.

**Custom opcode space:** RoCC uses RISC-V opcode encoding `custom-3` (`0x77`). Rocket decodes these instructions in its ID stage and forwards them to the attached coprocessor without disturbing normal integer pipeline flow.

**RoCC interface signals:**

| Signal group     | Direction       | Description                                                   |
|------------------|-----------------|---------------------------------------------------------------|
| `cmd.valid`      | Rocket → iDMA   | New instruction available                                     |
| `cmd.bits.inst`  | Rocket → iDMA   | Decoded instruction (funct7, funct3, rd, rs1/rs2 indices)     |
| `cmd.bits.rs1`   | Rocket → iDMA   | Value of rs1 (e.g., descriptor address in L2 cache or DRAM)   |
| `cmd.bits.rs2`   | Rocket → iDMA   | Value of rs2 (e.g., transfer control word / target CPU index) |
| `resp.valid`     | iDMA → Rocket   | Coprocessor response ready (completion or error notification) |
| `resp.bits`      | iDMA → Rocket   | Response payload: DMA CPU index, completion status, error flags|
| `busy`           | iDMA → Rocket   | Queue full — Rocket pipeline stalls on next custom instruction |
| `mem.req.*`      | iDMA → Rocket   | Coprocessor-initiated memory load (for descriptor auto-fetch)  |
| `mem.resp.*`     | Rocket → iDMA   | Memory response data returned to coprocessor                  |

**DMA descriptor enqueue via RoCC:**
Firmware writes `rs1 = descriptor_address` (pointer to a DMA descriptor struct resident in L2 cache) and `rs2 = descriptor_control` (target DMA CPU index, interrupt-on-complete flag). The iDMA engine receives the custom instruction, fetches the full descriptor from memory via the `mem` port, and enqueues the transfer into the selected DMA CPU's command buffer. A complete multi-dimensional DMA transfer — with source address, destination address, strides, and per-dimension sizes — is thus initiated with a single RISC-V instruction.

**Completion signaling:** When the DMA CPU finishes its transfer, it asserts `resp.valid` with the CPU index and status. Firmware can poll `resp.valid` after each issued instruction, or configure iDMA to raise a Rocket interrupt when a specific CPU or batch completes.

**Why RoCC instead of MMIO?**

RoCC integration offers key advantages over a memory-mapped I/O doorbell register for DMA dispatch:

- **Zero pipeline overhead.** RoCC instruction dispatch occupies the same 1-cycle ID slot as any RISC-V instruction. MMIO requires a dedicated store instruction plus a non-cacheable miss penalty of approximately 5–10 cycles per command.
- **Fire-and-forget issuing.** Firmware issues one custom instruction per DMA descriptor with no separate doorbell write. The `busy` signal provides automatic flow-control: Rocket stalls in the ID stage when the iDMA queue is full, requiring no firmware polling loop for backpressure.
- **Register-sourced operands.** `rs1`/`rs2` deliver the descriptor address and control word in a single instruction, avoiding the two-instruction sequence (write pointer register, write doorbell) required by MMIO.
- **Tight firmware loop efficiency.** DMA-intensive scatter-load loops achieve near-1-instruction-per-transfer throughput. No extraneous memory-mapped register writes are interspersed in the hot path, keeping the I-cache loop footprint minimal.

### 4.4 Clock Domains in Dispatch Tile

The Dispatch tile spans two primary clock domains with an explicit CDC FIFO boundary at the Rocket/NIU interface:

| Domain      | Source                        | Covers                                              |
|-------------|-------------------------------|-----------------------------------------------------|
| `ai_clk`    | `i_ai_clk[col]` (per-column)  | Rocket core, L1/L2 caches, iDMA engine logic        |
| `noc_clk`   | `i_noc_clk` (chip-global)     | NoC local port, flit input/output FIFOs, NIU        |
| `axi_clk`   | `i_axi_clk`                   | APB slave register interface (SFR domain)           |

**Column-specific ai_clk:** DISPATCH_E at X=0 receives `i_ai_clk[0]`; DISPATCH_W at X=3 receives `i_ai_clk[3]`. The two Dispatch tiles may therefore operate at different frequencies under per-column DVFS, allowing one Dispatch tile to throttle independently without affecting the other or the shared noc_clk domain.

**CDC FIFO sizing:** The `ai_clk`→`noc_clk` async FIFOs at the Rocket/NIU boundary are sized to absorb burst command sequences from Rocket firmware without stalls during normal operation. Typical sizing is 8–16 entries on the command path and 4–8 entries on the response path, consistent with the 8-deep iDMA CPU command queue depth.

**noc_clk sharing:** Both DISPATCH_W and DISPATCH_E share the same chip-global `i_noc_clk`. This ensures consistent NoC arbitration timing across all tiles regardless of per-column ai_clk DVFS state, and that wormhole packet forwarding operates at a single well-defined rate across the mesh.

### 4.5 Dispatch Tile Integration — Firmware Usage Model

The following describes the complete firmware-driven NPU execution lifecycle from one Dispatch tile. Both Dispatch tiles execute this sequence in parallel, each managing its assigned half of the Tensix array.

**Step 1 — Boot and runtime load:**
Rocket comes out of reset and fetches from the programmed boot vector. If the NPU runtime image is not already resident in L2, Rocket programs iDMA CPU0 to perform a DRAM→L2 bulk transfer, then jumps to the runtime entry point once the transfer completes.

**Step 2 — Tensix firmware delivery:**
The NPU runtime uses iDMA CPUs 0–7 in parallel to load BRISC kernel programs and TRISC LLK programs from DRAM into the L1 memories of 8 assigned Tensix tiles. Each iDMA CPU handles one Tensix tile's L1 load independently (source: DRAM, destination: Tensix L1 via NoC write packet). With 8 CPUs active concurrently, all 8 tiles are programmed in a single parallel phase rather than sequentially, reducing firmware delivery time by up to 8×.

**Step 3 — Per-tile SFR configuration:**
Rocket traverses a firmware configuration table and issues APB writes via NoC to each Tensix tile:
- `CLUSTER_CTRL`: operating mode, kernel type, tensor dimensions
- `T6_L1_CSR`: L1 cache partitioning, base addressing, bank enable
- Router ATT entries: NoC address translation for tensor operand routing

**Step 4 — Weight pre-load:**
Rocket issues iDMA commands via RoCC custom instructions to pre-load weight tensor tiles from DRAM into Tensix L1s. The ADDRESS_GEN hardware handles strided extraction of weight sub-tiles from the DRAM weight matrix layout (e.g., loading every K_tile-sized row block with an outer stride equal to the full matrix row width) without a firmware loop per row.

**Step 5 — Kernel launch:**
Rocket writes the TRISC reset program counter (start address of the LLK program in Tensix L1) to each Tensix tile's TRISC_PC SFR, then deasserts the TRISC reset. TRISCs begin executing their LLK programs autonomously. Rocket immediately proceeds to issue the next batch of DMA commands for the subsequent weight tile while the current tile is computing — overlapping DMA with compute.

**Step 6 — Completion and output drain:**
Rocket polls `LLK_TILE_COUNTERS` via NoC APB reads, or waits for a completion interrupt, to detect when the kernel has finished writing output activations to Tensix L1. Once all tiles signal completion, Rocket issues iDMA commands to drain the L1 activation outputs back to DRAM, then prepares the next kernel launch cycle.

---

## §5 NoC Router

### 5.1 Overview

Every tile in the N1B0 mesh includes a NoC router instance (`tt_trinity_router`). Routers implement a 5-port wormhole-switched fabric with two routing modes: deterministic Dimension-Order Routing (DOR) and dynamic routing using a per-flit carried path list.

**Why wormhole switching?**

Wormhole switching forwards flit-by-flit as soon as the header is decoded, without buffering the full packet at each router. This gives near-wire latency for large payloads: a 64-flit (32 KB) packet that would require 64-cycle store-and-forward buffering at each hop instead traverses each router in 1 cycle (header decode) with the body pipelined behind it. At 512 bits per flit and ~1 GHz noc_clk, each port delivers 512 Gbit/s peak throughput, and end-to-end latency for short control packets is bounded by hop count rather than packet size.

**5-port meaning:** 4 cardinal ports (North/South/East/West) connect to neighboring tiles in the 4×5 mesh. The 5th Local port connects to the tile's own endpoint (Tensix, Dispatch NIU, or standalone NIU). Each port is an independent 512-bit datapath with its own VC arbitration.

### 5.2 Router Port Map

```
                      North port
                         ↑
                         │
  West port ←──── [ROUTER] ────→ East port
                         │
                         ↓
                      South port
                         │
                      Local port (tile endpoint)
```

Each port is 512 bits wide (one full NoC flit per cycle). All five ports operate simultaneously with independent virtual channel arbitration. The router pipelines header decode, output port selection, and VC credit check in parallel with flit forwarding, so the effective per-hop latency for a fully pipelined wormhole packet is 1 cycle after the header is placed.

### 5.3 Virtual Channels

| Parameter        | Value                                     |
|------------------|-------------------------------------------|
| Number of VCs    | 4 per port                                |
| VC buffer depth  | Configurable (SRAM-backed FIFOs per VC)   |
| Arbitration      | Round-robin per port with priority override |

**Virtual channel assignment by traffic class:**

| VC  | Traffic class       | Use case                                                          |
|-----|---------------------|-------------------------------------------------------------------|
| VC0 | Request             | Tensix→NIU writes, Tensix→Tensix activation reads                 |
| VC1 | Response            | NIU→Tensix read responses, Tensix→Tensix read return data         |
| VC2 | Control / config    | BRISC config writes to remote tiles, SFR programming from Rocket  |
| VC3 | Multicast / priority| Broadcast weight loads to multiple Tensix tiles simultaneously    |

**Why 4 VCs?**

Deadlock avoidance in a bidirectional 2D mesh requires a minimum of 2 VCs (one for requests, one for responses), since a request flit holding a VC while waiting for a response would otherwise create a cyclic dependency. 4 VCs adds meaningful priority differentiation: control traffic on VC2 cannot be head-of-line blocked by large data transfers on VC0/VC1, and multicast on VC3 is isolated from unicast congestion. More than 4 VCs would increase SRAM area for the VC FIFOs without significant benefit in a 4×5 mesh where the maximum path length is 7 hops.

**VC credit mechanism:** Each output port maintains a per-VC credit counter tracking available buffer slots in the downstream router's input VC. A sender decrements its local credit counter when forwarding a flit; the receiver returns a credit token on each flit consumed from the buffer. Senders stall when the credit count reaches zero, preventing FIFO overflow without dropping flits.

### 5.4 Flit Format

#### 5.4.1 flit_type Field (3 bits)

| Code | Name         | Description                                        |
|------|--------------|----------------------------------------------------|
| 3'b001 | header     | First flit of a packet; contains routing header    |
| 3'b010 | data       | Payload flit; no routing information               |
| 3'b100 | tail       | Last flit of a packet                              |
| 3'b110 | path_squash | Special header for dynamic routing path pre-emption|

#### 5.4.2 noc_header_address_t Bit Map

The header flit contains a structured address field `noc_header_address_t`:

| Field            | Bits  | Description                                         |
|------------------|-------|-----------------------------------------------------|
| `x_coord`        | [5:0] | Destination X coordinate in the mesh               |
| `y_coord`        | [5:0] | Destination Y coordinate in the mesh               |
| `endpoint_index` | [4:0] | EndpointIndex (= X×5+Y) of destination tile         |
| `mcast_en`       | [0]   | Multicast enable                                    |
| `mcast_mask`     | [N:0] | Bitmask of multicast destination tiles              |
| `vc_sel`         | [1:0] | Virtual channel selection                           |
| `flit_type`      | [2:0] | Flit type (see §5.4.1)                              |

### 5.5 Dimension-Order Routing (DOR)

DOR is the default deterministic routing mode:

1. **X-phase**: Route along X-axis toward destination `x_coord`
2. **Y-phase**: When X matches, route along Y-axis toward destination `y_coord`

DOR is deadlock-free in a 2D mesh because it establishes a total order on dimensions. All flits using DOR travel strictly in X-first, Y-second order with no backtracking.

**Routing pseudo-code (DOR mode):**
```
if (current_x < dest_x)  → East
if (current_x > dest_x)  → West
if (current_x == dest_x and current_y < dest_y) → North
if (current_x == dest_x and current_y > dest_y) → South
if (current_x == dest_x and current_y == dest_y) → Local
```

**Worked example — routing from (0,0) to (3,4):**

```
Step 1 (X-phase): X=0 < X_dest=3, route East at each hop
  (0,0) →East→ (1,0) →East→ (2,0) →East→ (3,0)   [3 hops]

Step 2 (Y-phase): X matches X_dest=3, route North at each hop
  (3,0) →North→ (3,1) →North→ (3,2) →North→ (3,3) →North→ (3,4)   [4 hops]

Total: 7 hops  (= |Δx| + |Δy| = 3 + 4, the Manhattan minimum)
```

DOR guarantees the minimum-hop-count path for any source-destination pair in the mesh, since X-then-Y traversal is always the shortest path in a 2D grid under L1 distance.

### 5.6 Dynamic Routing

Dynamic routing uses a pre-computed explicit path embedded in the flit itself as a 928-bit carried list. Each router reads one slot from the list to determine its output port, then passes the remaining list forward.

| Parameter          | Value                                         |
|--------------------|-----------------------------------------------|
| Carried list width | 928 bits                                      |
| Path encoding      | Per-hop slot: 3-bit direction + metadata      |
| Read rule          | Each router reads its slot, forwards remainder|
| NIU write rule     | NIU may overwrite path slots at injection     |

**Per-hop operation:**
1. Router reads the current hop's slot from the carried list
2. Extracts the output port direction for this hop (3-bit: N/S/E/W/Local)
3. Forwards the remaining slots to the next router (slot index advances per hop)
4. NIU at injection point may rewrite slots based on ATT lookup before injecting the packet

**Why dynamic routing exists alongside DOR:**

DOR creates structural congestion hotspots in the N1B0 mesh: all traffic destined for the two NIUs at X=1, X=2 must traverse the central columns, creating a bottleneck when Tensix tiles in multiple rows simultaneously issue DRAM-bound traffic. Dynamic routing allows alternative paths that bypass congested links. The 928-bit carried list enables a fully pre-computed route decided at the injection point (by Dispatch firmware or the NIU ATT), without requiring per-hop routing table lookups that would add per-router latency.

For weight broadcast to all 12 Tensix tiles, dynamic routing enables a multicast tree traversal order that distributes fanout across multiple router hops, rather than funneling all traffic through a single X-column bottleneck as DOR would impose.

### 5.7 Path Squash Flit

The `path_squash` flit type (3'b110) is a control flit that preempts an in-flight wormhole packet:

- Injected into the NoC when a routing error or timeout is detected
- Travels along the same physical path as the packet being cancelled
- Each router receiving a path_squash flit releases the associated VC credits and buffer slots
- Used by the EDC error recovery flow to drain erroneous packets without deadlocking the VC

The path_squash mechanism is necessary for wormhole networks because a partially-transmitted packet that cannot complete (e.g., due to a detected error at the destination) would otherwise hold VC credits hostage across all intermediate routers, causing a VC stall cascade. The path_squash flit travels ahead and clears each router's held credit before the stall propagates.

### 5.8 ATT — Address Translation Table (in Router)

The router-side ATT is distinct from the NIU ATT (§3.2.3). It provides:

- 64 entries, each with mask/endpoint/routing fields
- Used for address-based routing decisions at the local port injection point
- Enables NoC address aliasing and endpoint redirection (e.g., redirecting a logical broadcast address to a physical multicast group bitmask)
- Programmed by Rocket firmware via APB at boot, before any NoC traffic is injected

### 5.9 Repeater Placement

Long wire segments in the mesh require repeater insertion to maintain signal integrity and meet setup timing. Physical tile pitch in N1B0 is approximately 100 µm. Signal integrity requires repeater insertion roughly every 500 µm, implying 2–5 repeater stages for typical inter-tile wire lengths. N1B0 repeater depths by segment:

| Segment                      | REP_DEPTH | Physical rationale                                         |
|------------------------------|-----------|------------------------------------------------------------|
| Y=3 loopback (composite)     | 6         | Spans two tile rows inside one module; `REP_DEPTH_LOOPBACK=6` |
| Y=4 output (composite NIU)   | 4         | NIU output to Y=3 router; `OUTPUT=4`                       |
| X-axis inter-tile (standard) | 2         | One tile pitch ~100 µm; 2 repeater stages sufficient       |
| Y=3 composite (West port)    | 4         | Longer cardinal West segment                               |
| Y=3 composite (South port)   | 5         | Longest cardinal South segment in composite                |
| Y=3 composite (East/North)   | 1         | Short segments — 1 stage sufficient                        |

The REP_DEPTH_LOOPBACK=6 value for the composite Y=3 internal loopback is the highest in the design: the loopback wire must traverse the full vertical extent of the composite NOC2AXI_ROUTER tile (spanning Y=4 down to Y=3 and back), equivalent to approximately 3× the standard inter-tile pitch, requiring 6 repeater stages to meet timing.

### 5.10 MCPDLY Derivation

The EDC ring uses a multi-cycle path delay parameter `MCPDLY` to correctly sample toggle signals across repeater chains. For the N1B0 Y=3 segment with `REP_DEPTH_LOOPBACK=6`:

```
MCPDLY = ceil(REP_DEPTH / clock_ratio) + margin
       = ceil(6 / 1) + 1
       = 7
```

This value is programmed into the EDC CSR at initialization. See §7 for EDC ring details.

### 5.11 Multicast

The NoC supports hardware-assisted multicast via the `mcast_en` bit and `mcast_mask` bitmask in the header flit.

**Mechanism:** When `mcast_en=1`, the router replicates the packet to all ports whose destination tiles are included in `mcast_mask`. Each bit of `mcast_mask` corresponds to one EndpointIndex in the mesh. The router checks the mask against the set of reachable endpoints in each direction and forwards a copy to each matching port.

**Primary use case — weight broadcast:** In LLM inference, the same weight tile must be delivered to all Tensix tiles participating in a matrix multiply (up to all 12 Tensix tiles for a full-chip GEMM). With unicast, this requires 12 separate NoC injections from the Dispatch tile, consuming 12× the injection bandwidth and 12× the DRAM-to-NoC data movement. With multicast to all 12 Tensix tiles via a single injection:
- NoC injection bandwidth required: 1× (one packet injected at source)
- Effective bandwidth amplification: 12× at destination tiles
- Source-to-first-hop link traffic: reduced by approximately 11× vs. 12 separate unicast packets

**VC3 assignment:** Weight broadcasts use VC3 to isolate multicast traffic from unicast data and response traffic on VC0/VC1, preventing a large broadcast from starving unicast responses and creating head-of-line blocking or deadlock conditions.

---

## §6 iDMA Engine

### 6.1 Overview

The iDMA (integrated DMA) engine resides inside each Dispatch tile and is the primary mechanism for high-bandwidth tensor data movement between external DRAM and on-chip Tensix L1 memories. It is accessible via two interfaces:

1. **RoCC coprocessor interface** — from the Rocket core pipeline (see §4.3); zero-overhead instruction-level dispatch
2. **APB slave at base address `0x03004000`** — for debug, external SoC programming, or firmware fallback when RoCC is not appropriate

The iDMA engine contains **8 independent DMA CPU cores**. Each CPU is capable of autonomous multi-dimensional address generation, NoC packet injection, and completion signaling without per-flit Rocket involvement.

**Why 8 CPUs?**

N1B0 has 12 Tensix tiles total, but practical simultaneous DMA targets per Dispatch tile are at most 6 (the Tensix tiles on its side of the mesh). 8 CPUs exceeds this maximum, providing slack for:
- Overlapping weight load for the next layer while the current layer is computing (double-buffering)
- One CPU dedicated to firmware delivery (L1 program load) while others handle weight data
- One CPU available for activation drain while others pre-load the next weight tile

Each CPU runs independently with no inter-CPU synchronization hardware. For simple broadcast or scatter patterns, all 8 CPUs can operate in parallel without any firmware-managed ordering.

### 6.2 DMA CPU Architecture

Each of the 8 DMA CPUs contains 5 independent register blocks:

```
DMA CPU[n] (n = 0..7)
  ┌─────────────────────────────────────────────┐
  │  CMD_BUF_R      (47 regs)                   │
  │  Source addr, strides, sizes, ctrl, status  │
  ├─────────────────────────────────────────────┤
  │  CMD_BUF_W      (47 regs)                   │
  │  Dest addr, strides, sizes, ctrl, status    │
  ├─────────────────────────────────────────────┤
  │  ADDRESS_GEN_R  (25 regs)                   │
  │  Multi-dim loop counter for read addresses  │
  ├─────────────────────────────────────────────┤
  │  ADDRESS_GEN_W  (25 regs)                   │
  │  Multi-dim loop counter for write addresses │
  ├─────────────────────────────────────────────┤
  │  SIMPLE_CMD_BUF (47 regs)                   │
  │  1D/2D simplified transfer path             │
  └─────────────────────────────────────────────┘
```

CMD_BUF_R configures the source side of a read-then-write (DRAM-to-L1) or read-only operation. CMD_BUF_W configures the destination side. ADDRESS_GEN provides autonomous hardware looping over the address space according to programmed strides and limits, freeing the Rocket CPU from per-transfer address arithmetic.

### 6.3 CMD_BUF_R / CMD_BUF_W

Each CMD_BUF block (47 registers) configures a full DMA transfer descriptor:

| Register Group      | Count | Description                                          |
|---------------------|-------|------------------------------------------------------|
| Source address      | 4     | Base address (64-bit across two 32-bit regs)         |
| Destination address | 4     | Base address (64-bit)                                |
| Stride config       | 8     | Per-dimension stride values (up to 4 dimensions)     |
| Size config         | 8     | Per-dimension transfer size                          |
| Control             | 8     | Enable, interrupt on completion, VC select, etc.     |
| Status / misc       | 15    | Transfer status, error flags, completion count       |

The CMD_BUF supports up to 4-dimensional tensor transfers with independent stride and size per dimension, enabling efficient mapping of arbitrary tensor layouts without software scatter/gather overhead.

**Register programming example — 16 KB DRAM→Tensix(0,0) L1 transfer:**

```c
// Program iDMA CPU0 to read 16KB from DRAM to Tensix (0,0) L1
// Tensix (0,0): EndpointIndex = 0*5+0 = 0

idma[0].CMD_BUF_R.SRC_ADDR_LO = 0x80001000;  // DRAM source, lower 32 bits
idma[0].CMD_BUF_R.SRC_ADDR_HI = 0x00000000;  // DRAM source, upper 32 bits
idma[0].CMD_BUF_R.DST_EP      = 0;           // EndpointIndex = 0 → Tensix(0,0)
idma[0].CMD_BUF_R.BYTE_COUNT  = 16384;        // 16 KB transfer size
idma[0].CMD_BUF_R.VC_SEL      = 0;           // VC0 (request traffic)
idma[0].CMD_BUF_R.CTRL        = 0x1;         // enable bit: start transfer
// Poll idma[0].CMD_BUF_R.STATUS until done bit is set
```

### 6.4 ADDRESS_GEN_R / ADDRESS_GEN_W

The address generator (25 registers) implements an autonomous multi-dimensional hardware loop counter:

| Register Group  | Count | Description                                           |
|-----------------|-------|-------------------------------------------------------|
| Base address    | 2     | Starting address for the address sequence             |
| Dimension count | 1     | Number of active dimensions (1–4)                     |
| Stride[0..3]    | 8     | Stride per dimension (signed 32-bit, in bytes)        |
| Limit[0..3]     | 8     | Iteration count per dimension                         |
| Control         | 6     | Loop enable, wrap mode, saturation                    |

The ADDRESS_GEN operates as a hardware loop counter, automatically incrementing addresses and wrapping at boundaries. This allows the DMA to traverse complex tensor sub-views (e.g., rows of a matrix stored in column-major order) without CPU intervention.

**Multi-dimensional strided access example:**

To load every 4th row of a weight matrix stored in row-major DRAM layout (e.g., extracting K_tile=48 rows with a row stride of 4× the row size, from a matrix with 1024 columns of INT16 = 2048 bytes/row):

```
ADDRESS_GEN_R config:
  Base       = DRAM_weight_base
  Dim0 size  = 2048        // bytes per selected row (1024 × INT16)
  Dim0 stride = 1          // byte stride within row: contiguous
  Dim1 size  = 48          // number of rows to load
  Dim1 stride = 4 * 2048   // skip 4 rows per iteration (every 4th row)
  Dim count  = 2           // 2 active dimensions
```

The ADDRESS_GEN hardware automatically generates all 48 × 2048-byte source address sequences without any Rocket intervention. This allows complex strided sub-tensor extraction in a single DMA command, equivalent to what would otherwise require a firmware loop of 48 separate DMA transfers.

### 6.5 SIMPLE_CMD_BUF

The SIMPLE_CMD_BUF (47 registers) provides a simplified programming interface for common 1D or 2D transfers where the full 4D CMD_BUF generality is not required. It uses the same register layout but with a reduced maximum dimensionality configuration, making firmware programming faster for straightforward bulk transfers (e.g., loading a contiguous L1-sized block from a sequential DRAM address).

### 6.6 Register Map

The iDMA APB register space spans `0x03004000` to `0x03009FFF`:

```
Base: 0x03004000
Size: 0x6000 (24KB = 1,528 registers × 4 bytes, padded to 24KB)

Per-CPU stride: 0x0C00 (3KB per CPU)

CPU 0: 0x03004000 – 0x03004BFF
  CMD_BUF_R:      0x03004000 + 0x000  (base = 0x03004000, size = 0x178)
  CMD_BUF_W:      0x03004000 + 0x200  (base = 0x03004200, size = 0x178)
  ADDRESS_GEN_R:  0x03004000 + 0x400  (base = 0x03004400)
  ADDRESS_GEN_W:  0x03004000 + 0x600  (base = 0x03004600)
  SIMPLE_CMD_BUF: 0x03004000 + 0x800  (base = 0x03004800)

> RTL-verified from `tt_rocc_accel_reg.svh`: CPU0 CMD_BUF_W base = 0x03004200, ADDRESS_GEN_R = 0x03004400, ADDRESS_GEN_W = 0x03004600, SIMPLE_CMD_BUF = 0x03004800. Sub-blocks are 0x200-spaced, not 0x100.

CPU 1: 0x03004C00 – 0x030057FF
  (same layout, base + 0x0C00)

CPU 2: 0x03005800 – 0x030063FF
CPU 3: 0x03006400 – 0x03006FFF
CPU 4: 0x03007000 – 0x03007BFF
CPU 5: 0x03007C00 – 0x030087FF
CPU 6: 0x03008800 – 0x030093FF
CPU 7: 0x03009400 – 0x03009FFF
```

### 6.7 DMA Operation Flow

A complete tensor DMA operation proceeds as follows:

1. **Descriptor programming:** Rocket writes source/destination addresses, strides, and sizes to a CPU's CMD_BUF registers via APB (or via RoCC by pointing to a pre-built descriptor in L2 cache)
2. **Enable:** Rocket sets the enable bit in CMD_BUF_R.CTRL; ADDRESS_GEN immediately begins generating address sequences
3. **NoC injection:** DMA CPU issues NoC read-request packets addressed to the source endpoint (DRAM via NIU, or remote Tensix L1)
4. **NIU bridging:** NIU at X=1 or X=2 receives the NoC read request, translates via ATT to AXI address, and issues AXI read bursts to DRAM
5. **Data return:** DRAM returns AXI read data; NIU packs read data into 512-bit NoC response flits and routes them to the destination Tensix L1
6. **L1 write:** Response flits arrive at the destination Tensix router local port and are written into the Tensix L1 SRAM by the local NoC injection logic
7. **Completion:** DMA CPU detects end of transfer (all address iterations exhausted), sets completion status in CMD_BUF_R.STATUS, and optionally asserts `resp.valid` to Rocket via RoCC

### 6.8 Integration with Tensix

The iDMA engine is the exclusive mechanism for loading weight tensors from external DRAM into Tensix L1 before a compute kernel, and for draining activation results from Tensix L1 to DRAM after kernel completion. The NoC-based DMA path decouples data movement from the Tensix compute pipeline: a Tensix tile executing a GEMM kernel on one set of weights in one L1 partition can simultaneously receive the next weight tile into a different L1 partition via iDMA, enabling true double-buffered overlap of DMA and compute.

### 6.9 Performance Model

**Peak bandwidth per NIU:**
At 512-bit AXI data width operating at ~1 GHz noc_clk: 512 bits × 1 GHz = 64 GB/s per NIU (theoretical peak with 100% bus utilization and no AXI handshake overhead).

**Total peak DRAM bandwidth:**
N1B0 has 2 NIU-capable tiles (the two composite NOC2AXI_ROUTER tiles at X=1, X=2), plus 2 standalone NIU tiles (NE_OPT at X=0, NW_OPT at X=3). With all 4 NIU AXI ports active simultaneously:
- 4 × 64 GB/s = **256 GB/s total theoretical peak** (if all 4 NIUs drive simultaneous AXI bursts)
- With 2 primary NIUs: **128 GB/s** is the practical dual-NIU peak

**Practical bandwidth:**
Achievable bandwidth is limited by:

1. **DRAM latency and outstanding request count.** AXI read latency to external DRAM is typically 100–300 ns. To sustain 64 GB/s at 64-byte AXI beats, the iDMA must keep approximately (64 GB/s × 200 ns) / 64 B ≈ 200 outstanding AXI read beats in flight. The RDATA FIFO depth (default 512 entries in N1B0) and 8 concurrent DMA CPUs per Dispatch tile provide sufficient outstanding-request depth to approach this level.

2. **NoC congestion.** All 8 DMA CPUs injecting read requests simultaneously share the East-output port toward the NIU column. VC arbitration handles this, but peak injection rate is bounded by the single 512-bit/cycle output port of the source router.

3. **Tensor layout.** Non-contiguous strided access patterns (large outer-dimension strides) fragment AXI bursts, reducing effective AXI bus utilization below the 256-beat maximum burst length.

**Practical rule of thumb:** For large contiguous tensor loads (≥16 KB per DMA transfer), iDMA achieves approximately 60–80% of peak NIU AXI bandwidth, yielding approximately 38–51 GB/s per NIU or 76–102 GB/s aggregate for both NIUs active simultaneously.

---

## §7 EDC Ring

### 7.1 Overview

The Error Detection and Correction (EDC) ring is a single serial ring that traverses every tile in the N1B0 chip. It provides continuous built-in self-test (BIST) and error monitoring for all critical on-chip memories, logic, and interconnect paths.

#### 7.1.1 Motivation

Modern SoCs are subject to several classes of runtime hardware faults that cannot be detected by standard manufacturing test:

- **Cosmic-ray induced soft errors (SEUs)**: High-energy particles flip bits in SRAM and register files even in correctly manufactured devices. Error rates scale with altitude and technology node.
- **Aging and wearout**: Hot-carrier injection (HCI) and negative-bias temperature instability (NBTI) degrade transistor threshold voltages over time, causing timing violations that appear as logic errors.
- **Voltage droop**: Simultaneous switching of thousands of compute elements causes instantaneous Vdd droop, which can cause setup-time violations in dense logic such as the FPU datapath.
- **Manufacturing marginality**: Borderline devices may pass static test but fail under dynamic workload stress.

Unlike ECC (which is per-memory and only protects storage elements), the EDC ring monitors **inter-block communication paths and register state** on a periodic basis. Every node in the ring samples its local state on each ring traversal cycle, generates a CRC over its local data, and reports any mismatch back to the initiator. This provides coverage for both storage faults (SRAM, register files) and logic faults (datapath parity, control state corruption).

The ring is designed to add minimal area overhead: the serial protocol means only two wires (req_tgl, ack_tgl) plus a 32-bit data bus traverse tile boundaries. All check logic is inside `tt_edc1_node.sv` instances distributed throughout the tile hierarchy.

#### 7.1.2 Ring Protocol Module

The ring protocol is defined in `tt_edc1_node.sv`. Each node instance performs:
- **Periodic error injection and detection** via toggle-based handshake
- **Local state sampling**: register file parity, SRAM ECC syndrome, control-path parity
- **CRC generation**: 32-bit CRC over the sampled local data
- **Error reporting** with severity classification (FATAL / CRIT / n-crt / ECC+ / ECC−)
- **Interrupt generation** to the host on detected faults via the overlay error aggregator
- **Bypass mux**: allows harvested tiles to be skipped in the ring chain without breaking continuity

### 7.2 Ring Protocol

The EDC ring uses a toggle-based request/acknowledge handshake. Toggle-based (XOR-based) signaling is used instead of level-based signaling because it is inherently immune to the initial state after reset — a rising or falling edge on the toggle wire always means "a new event has occurred," regardless of the starting value.

#### 7.2.1 Signal Interface

| Signal      | Width  | Direction  | Description                                          |
|-------------|--------|------------|------------------------------------------------------|
| `req_tgl`   | 1      | Forward    | Request toggle — XOR-edge triggers each new request  |
| `ack_tgl`   | 1      | Backward   | Acknowledge toggle — node asserts after processing   |
| `data[31:0]`| 32     | Forward    | 32-bit CRC / error status payload                    |

#### 7.2.2 Ring Traversal Timing

The ring operates as a pipeline: the initiator node (at the head of the ring) drives `req_tgl`, and the signal propagates forward through every node in sequence. Each node samples local state, computes a CRC, and forwards `req_tgl` to the next node. After all nodes have processed the toggle, `ack_tgl` propagates back through the loopback path to the initiator.

```
  Timing (simplified, single traversal):

  Cycle 0:  Initiator toggles req_tgl
            │
  Cycle 1:  Node 0 samples local state, generates CRC, forwards req_tgl
            │   (combinational propagation through repeaters: MCPDLY cycles)
  Cycle M:  Node 1 receives req_tgl (after repeater delay M = MCPDLY)
            Node 1 samples, generates CRC, forwards
            │
            ...
  Cycle N×M: Last node (node N−1) has processed req_tgl
             ack_tgl begins propagating back on loopback wire
             │
  Cycle N×M + L: Initiator receives ack_tgl (loopback delay L cycles)
                 Initiator reads back aggregated data[31:0] from all nodes
                 Compares against expected CRC
                 If mismatch → generate interrupt at appropriate severity
```

The total ring traversal time is approximately `N_nodes × (node_latency + MCPDLY)` clock cycles, where `MCPDLY=7` is the worst-case inter-node repeater delay. With ~200 nodes and MCPDLY=7, a full traversal takes on the order of ~1,400–2,000 noc_clk cycles per sweep.

#### 7.2.3 Per-Node Operation

Each `tt_edc1_node` instance executes the following on each incoming `req_tgl` edge:

1. Detect edge: compare `req_tgl` against locally stored previous value; if XOR=1, a new request has arrived
2. Sample local state: read parity bits from assigned register file entries or SRAM ECC syndrome registers
3. Compute 32-bit CRC over sampled data using the configured polynomial
4. XOR the local CRC into the forwarded `data[31:0]` field (cumulative across the ring)
5. Toggle `req_tgl` forward to the next node
6. Toggle `ack_tgl` backward to the previous node (one cycle after forwarding)

The initiator receives the final `data[31:0]` which is the XOR-accumulation of all node CRCs. A mismatch against the expected all-zero (or expected reference) value indicates that one or more nodes have detected a local error.

#### 7.2.4 CDC-Safe Toggle Protocol

Because `req_tgl` and `ack_tgl` are single-bit toggle signals, they are safe for synchronization by a standard 2-FF or 3-FF synchronizer (sync3r) at clock-domain boundaries. Only one bit must be synchronized per crossing, and the toggle protocol guarantees that no new toggle arrives before the previous one has been acknowledged — providing the minimum pulse width guarantee required by a synchronizer.

This is the fundamental reason the EDC ring uses a toggle (not a pulse or level) protocol: it allows correct multi-clock-domain operation with minimal synchronizer overhead.

### 7.3 DISABLE_SYNC_FLOPS

#### 7.3.1 Background

In the baseline Trinity design (non-N1B0), the EDC ring traverses tiles that may belong to different clock domains within the same ring segment. For example, a Tensix tile contains nodes in the `ai_clk` domain and nodes in the `noc_clk` domain. When `req_tgl` crosses from an `ai_clk` node to a `noc_clk` node within the same tile, a 3-stage synchronizer (sync3r) is required to safely re-time the toggle signal.

These intra-tile CDC synchronizers add:
- **Latency**: 3 clock cycles per crossing (at the destination clock frequency)
- **Area**: 3 flip-flops per synchronizer, plus clock-domain crossing handshake logic
- **Hold-violation risk**: If source and destination clocks happen to be synchronous (e.g., same PLL output), synchronizers can cause spurious hold violations

#### 7.3.2 N1B0 DISABLE_SYNC_FLOPS=1

In N1B0, `DISABLE_SYNC_FLOPS=1` is set as a compile-time parameter applied globally to all `tt_edc1_node` instances. The rationale is:

- Within each N1B0 ring **segment**, all EDC-connected nodes share the same physical clock. A ring segment is defined as the subset of nodes traversed between the two CDC crossing points at Y=2 Tensix tiles.
- Because nodes within a segment are all clocked by the same `ai_clk[col]` (or `noc_clk` for router/NIU nodes), the synchronizers would operate in same-clock mode — which creates false hold violations and adds unnecessary latency.
- Disabling the synchronizers within same-clock segments eliminates latency and removes the area cost, at the cost of requiring that clocks within each segment remain synchronous.

```
  DISABLE_SYNC_FLOPS effect (within one ring segment):

  DISABLE_SYNC_FLOPS=0 (baseline):              DISABLE_SYNC_FLOPS=1 (N1B0):
  Node N → [sync3r, 3 cycles] → Node N+1        Node N → [wire] → Node N+1
  Latency = 3 cycles per crossing               Latency = combinational only
  Area    = 6 FFs per intra-segment CDC         Area    = 0 extra FFs
```

#### 7.3.3 Where Synchronizers Are Still Used

DISABLE_SYNC_FLOPS=1 does NOT remove synchronizers at actual inter-domain boundaries. The three intra-tile CDC crossings at Y=2 Tensix tiles (ai_clk→noc_clk, noc_clk→ai_clk, ai_clk→dm_clk) continue to use sync3r synchronizers for the EDC toggle signals, because at those points the source and destination clocks genuinely belong to different domains.

Additionally, the `async_init` path uses sync3r per node at reset de-assertion to safely establish initial toggle state from the asynchronous reset domain into each node's clock domain, regardless of DISABLE_SYNC_FLOPS.

### 7.4 Ring Traversal Order

The EDC ring is a single chain starting and ending at the AXI host interface. It traverses tiles in a defined order by column and row segment. The high-level column traversal for N1B0 is:

```
AXI host
  │
  ├─→ Column X=0: Y=0 → Y=1 → Y=2 → Y=3(Dispatch W) → Y=4
  ├─→ Column X=1: Y=4(NIU) → [cross-row] → Y=3(Router) → Y=2 → Y=1 → Y=0
  ├─→ Column X=2: Y=0 → Y=1 → Y=2 → Y=3(Router) → [cross-row] → Y=4(NIU)
  ├─→ Column X=3: Y=4 → Y=3(Dispatch E) → Y=2 → Y=1 → Y=0
  │
AXI host (loopback)
```

Within each Tensix tile, the ring visits multiple sub-nodes in order: NOC node, OVL node, then per-SRAM-bank nodes for the L1 partition.

### 7.5 EDC Node Assignments

The N1B0 ring contains multiple EDC nodes per tile. The node ID space is divided by subsystem and tile type.

#### 7.5.1 Node ID Table

| Node ID Range | Tile Location              | Tile Type        | What Each Node Monitors                                |
|---------------|----------------------------|------------------|--------------------------------------------------------|
| 0–15          | (X=0, Y=0) Tensix          | T6               | NOC flit input buffer, overlay state, L1 bank 0–3 ECC  |
| 16–31         | (X=1, Y=0) Tensix          | T6               | NOC flit input buffer, overlay state, L1 bank 0–3 ECC  |
| 32–47         | (X=2, Y=0) Tensix          | T6               | NOC flit input buffer, overlay state, L1 bank 0–3 ECC  |
| 48–63         | (X=3, Y=0) Tensix          | T6               | NOC flit input buffer, overlay state, L1 bank 0–3 ECC  |
| 64–79         | (X=0, Y=1) Tensix          | T6               | NOC flit buffers, DEST register file parity, L1 ECC    |
| 80–95         | (X=1, Y=1) Tensix          | T6               | NOC flit buffers, DEST register file parity, L1 ECC    |
| 96–111        | (X=2, Y=1) Tensix          | T6               | NOC flit buffers, DEST register file parity, L1 ECC    |
| 112–127       | (X=3, Y=1) Tensix          | T6               | NOC flit buffers, DEST register file parity, L1 ECC    |
| 128–143       | (X=0, Y=2) Tensix          | T6               | NOC flit buffers, SRCA register file, L1 ECC, FPU parity |
| 144–159       | (X=1, Y=2) Tensix          | T6               | NOC flit buffers, SRCA register file, L1 ECC, FPU parity |
| 160–175       | (X=2, Y=2) Tensix          | T6               | NOC flit buffers, SRCA register file, L1 ECC, FPU parity |
| 176–191       | (X=3, Y=2) Tensix          | T6               | NOC flit buffers, SRCA register file, L1 ECC, FPU parity |
| 192           | NIU / NOC2AXI BIU          | Composite Y=4    | NIU BIU request/response state, ATT SRAM parity        |
| 193           | Router (X=1, Y=3)          | Composite router | Router VC FIFO contents, flit header parity            |
| 194           | Router (X=2, Y=3)          | Composite router | Router VC FIFO contents, flit header parity            |
| 195           | DISPATCH_E (X=0, Y=3)      | Dispatch         | Rocket core instruction buffer, L1 cache ECC           |
| 196           | DISPATCH_W (X=3, Y=3)      | Dispatch         | Rocket core instruction buffer, L1 cache ECC           |
| 197           | NE_OPT NIU (X=0, Y=4)      | Standalone NIU   | NIU BIU state, ATT SRAM parity (on-ring)               |
| 198           | NW_OPT NIU (X=3, Y=4)      | Standalone NIU   | NIU BIU state, ATT SRAM parity (on-ring)               |

Within each Tensix tile, the ring visits sub-nodes in order: NOC flit node → OVL (overlay) node → per-SRAM-bank L1 nodes. The 16-ID allocation per Tensix tile reflects one NOC node + one OVL node + up to 14 L1 bank nodes (N1B0 L1 has 256 macros per tile; bank nodes are grouped).

#### 7.5.2 N1B0 Composite Tile EDC Connectivity (Off-Ring Issue)

A known architectural issue affects the NIU BIU EDC nodes for the composite tiles (X=1, X=2) at Y=4:

- The NIU BIU EDC node at Y=4 for X=1 and X=2 is **off-ring** in the current N1B0 implementation. It does not participate directly in the main forward EDC chain.
- The Y=3 router node at each composite tile provides on-ring coverage for the router VC FIFOs and flit state in that column segment.
- The Y=4 BIU EDC node's error signals are routed through the `o_niu_timeout_intp` interrupt path rather than the main ring chain. This means BIU errors at composite tile Y=4 generate a CRIT interrupt via the timeout interrupt line, but are not visible as ring-detected errors.
- This issue is documented in the N1B0 open-signal report Rev.5 under the EDC ring connectivity correction section. The fix options include: (a) routing the composite Y=4 BIU EDC chain port through the composite module boundary to connect to the main ring at Y=4, or (b) accepting the `o_niu_timeout_intp` path as the sole error reporting mechanism for that node.

The standalone NIU tiles (X=0, X=3 at Y=4) do **not** have this issue — their EDC nodes are directly on-ring at Y=4 and participate fully in the ring traversal.

### 7.6 Severity Model

Each EDC node classifies detected errors into one of four severity levels:

| Level  | Code    | Action                                              | IRQ Line         |
|--------|---------|-----------------------------------------------------|------------------|
| FATAL  | FATAL   | Chip halt, assert fatal interrupt to host           | FATAL_IRQ        |
| CRIT   | CRIT    | Recoverable error; log + interrupt, continue        | CRIT_IRQ         |
| n-crt  | n-crt   | Non-critical; log only, no interrupt                | (masked/logged)  |
| ECC+   | ECC+    | ECC single-bit corrected (corrected successfully)   | ECC_CORR_IRQ     |
| ECC−   | ECC−    | ECC double-bit or uncorrectable error               | ECC_UNCORR_IRQ   |

**Per-tile rationale:**

| Coverage Area        | Severity on Failure |
|----------------------|---------------------|
| L1 SRAM (single-bit) | ECC+                |
| L1 SRAM (double-bit) | ECC− → CRIT         |
| DEST register file   | CRIT                |
| SRCA register file   | CRIT                |
| FPU datapath         | FATAL               |
| NoC VC FIFO          | CRIT                |
| Router logic         | FATAL               |
| NIU ATT              | CRIT                |

### 7.7 MCPDLY — Multi-Cycle Path Delay

The EDC ring timing depends on the number of pipeline stages (repeaters) in each inter-node segment. The MCPDLY CSR tells each node how many cycles to wait for the toggle to propagate through repeaters before declaring a timeout.

**N1B0 MCPDLY derivation:**

For the longest segment (Y=3 loopback with `REP_DEPTH_LOOPBACK=6`):

```
MCPDLY = REP_DEPTH_LOOPBACK + 1 (safety margin)
       = 6 + 1
       = 7 cycles
```

This value (7) is programmed into the EDC CSR during chip initialization by firmware. Other segments with smaller repeater depth (REP_DEPTH=2 standard, OUTPUT=4) use the same MCPDLY=7 value since it represents the worst-case segment; no per-segment override is required.

### 7.8 Repeater Placement in EDC Ring

The EDC ring forward and loopback wires share the same physical routing channels as the NoC flit wires. Repeaters are inserted at the same locations:

| Segment Type           | Repeater Depth | Notes                           |
|------------------------|----------------|---------------------------------|
| Standard X-axis inter-tile | 2 (REP×2)  | Baseline mesh spacing           |
| Y=3 composite loopback | 6 (REP×6)      | Long composite span; N1B0 specific |
| Y=4 composite output   | 4 (REP×4)      | NIU to Y=3 router path          |

Repeaters in the EDC path are combinational buffers only — they add propagation delay but no flip-flop stages. The MCPDLY setting accounts for this combinational delay across the worst-case path.

### 7.9 Initialization Sequence

EDC ring initialization is a required firmware step at chip bring-up. The ring must be correctly initialized before the first EDC check can be performed; an uninitialized ring will produce false timeouts or spurious error reports.

#### Step 1 — Program MCPDLY

Firmware writes `MCPDLY=7` to the EDC CSR via APB:

```
// APB write to CLUSTER_CTRL base (0x03000000)
// EDC_MCPDLY register offset: per HDD EDC CSR map
APB_WRITE(EDC_BASE + EDC_MCPDLY_OFFSET, 7);
```

MCPDLY=7 is the worst-case inter-node delay for the N1B0 ring (Y=3 composite loopback, REP_DEPTH_LOOPBACK=6, plus 1 safety cycle). This value must be set before releasing ring reset, because nodes use MCPDLY to determine how long to wait for `req_tgl` to arrive from the previous node before declaring a timeout error.

#### Step 2 — Release EDC Ring Reset (async_init)

Firmware releases the EDC ring reset. Internally, each node performs an `async_init` sequence:

```
  async_init flow per node:
  1. Ring reset is asserted (all nodes in reset, toggle state = 0)
  2. Firmware de-asserts ring reset
  3. Each node's sync3r (3-register synchronizer) synchronizes the reset de-assertion
     into the local clock domain (ai_clk or noc_clk depending on node type)
  4. Once synced, the node initializes its internal toggle state from the
     synchronized reset signal
  5. Node is now ready to participate in ring handshake
```

The sync3r ensures that all nodes start from a known toggle state (0) regardless of when reset de-asserts relative to the local clock edge. Without this, different nodes could initialize with different toggle states, causing immediate false mismatches.

#### Step 3 — Ring Self-Test

After reset de-assertion and MCPDLY programming, firmware triggers a ring self-test by sending a test toggle:

```
// Enable ring
APB_WRITE(EDC_BASE + EDC_ENABLE_OFFSET, 1);

// Trigger test sweep
APB_WRITE(EDC_BASE + EDC_TRIGGER_OFFSET, 1);

// Wait for completion (poll status or wait for interrupt)
while (!APB_READ(EDC_BASE + EDC_STATUS_OFFSET) & EDC_SWEEP_DONE_BIT) {
    // wait approximately N_nodes × MCPDLY × noc_clk_period
}
```

During the self-test sweep:
- The initiator sends `req_tgl` down the ring
- Each node samples its local state (all-zero or known pattern in test mode) and computes a CRC
- The accumulated `data[31:0]` is compared against the expected reference value
- Nodes with harvest bypass asserted are skipped automatically

#### Step 4 — Read Back Status and Confirm PASS

Firmware reads the EDC status register to confirm all nodes responded correctly:

```
uint32_t status = APB_READ(EDC_BASE + EDC_STATUS_OFFSET);

if (status & EDC_ERROR_BIT) {
    // One or more nodes failed the self-test
    // Read EDC_NODE_ID register to identify which node
    uint32_t failed_node = APB_READ(EDC_BASE + EDC_NODE_ID_OFFSET);
    // Report FATAL error — ring self-test failure is unrecoverable
    raise_fatal_interrupt(FATAL_EDC_SELFTEST_FAIL, failed_node);
} else {
    // PASS — all nodes responded with correct CRC
    // EDC ring is operational; begin periodic monitoring
    APB_WRITE(EDC_BASE + EDC_PERIODIC_ENABLE_OFFSET, 1);
}
```

If all nodes return PASS, the ring is confirmed operational and periodic monitoring is enabled. Periodic sweeps run autonomously in hardware; firmware is only interrupted if a subsequent sweep detects a mismatch.

### 7.10 Harvest Bypass in EDC Ring

When a tile is harvested (disabled due to manufacturing yield), the tile's compute logic is powered down or isolated. If the EDC ring simply omitted the node, the ring chain would be broken at that point and the entire ring would stall, preventing error monitoring for all remaining active tiles. The bypass mechanism solves this problem.

#### 7.10.1 Bypass Mechanism

Each `tt_edc1_node` instance includes a **bypass mux** that can route the ring signal around the node:

```
  Normal operation (tile active):
  ring_in (req_tgl) ──────────────────────────→ [EDC node logic] ──→ ring_out

  Bypass operation (tile harvested):
  ring_in (req_tgl) ──→ [2:1 mux, sel=bypass] ──────────────────→ ring_out
                              │
                         bypass=1: wire ring_in directly to ring_out
                         (skip node logic entirely)
```

The bypass is purely combinational — `ring_out` follows `ring_in` with only wire delay when bypass is asserted. This means:
- The ring traversal time decreases when tiles are bypassed (fewer effective nodes)
- No MCPDLY adjustment is needed — the bypass shortens the path, so the existing MCPDLY=7 is still a valid worst-case upper bound
- The bypassed node generates no ack_tgl, so the initiator does not expect a response from it

#### 7.10.2 Bypass Control Signal

The bypass is controlled by the `ISO_EN` signal — mechanism 6 in the N1B0 harvest scheme. `ISO_EN[x + 4*y]` being asserted for a tile directly drives the bypass mux select for all EDC nodes within that tile:

```
  ISO_EN bit mapping for Tensix tiles (X=0..3, Y=0..2):
  ISO_EN[0]  → tile (X=0, Y=0) → bypass all EDC nodes at (0,0)
  ISO_EN[1]  → tile (X=1, Y=0) → bypass all EDC nodes at (1,0)
  ...
  ISO_EN[11] → tile (X=3, Y=2) → bypass all EDC nodes at (3,2)
```

The same `ISO_EN` signal that gates the tile's compute clocks (via DFX wrappers) and isolates its output signals (via AND-type ISO cells) also bypasses its EDC nodes. This ensures that a harvested tile is consistently invisible to the EDC ring — it contributes no CRC, receives no toggle, and its output isolation prevents it from driving the ring in an uncontrolled state.

#### 7.10.3 Consequence of Not Bypassing

If a harvested tile's EDC node is not bypassed, the following failure modes occur:

1. **Ring stall**: The node's compute clock is gated, so `req_tgl` arriving at the node will never be forwarded. The initiator waits indefinitely for `ack_tgl` and eventually declares a timeout — generating a false FATAL interrupt even though no real error exists.
2. **Incorrect CRC**: If the node is partially powered (e.g., ISO cells block outputs but node logic is still active), the node may generate a CRC over garbage state, causing a false CRIT error.
3. **Ring deadlock**: In the worst case, the ring permanently stalls and all subsequent EDC monitoring is disabled for the entire chip.

The bypass mechanism ensures none of these failure modes can occur. Bypass assertion is part of the standard harvest initialization sequence and must be applied before the EDC ring is enabled.

### 7.11 EDC CSR Base Addresses

| Block          | Base Address | Registers |
|----------------|--------------|-----------|
| EDC per-node   | Via tile APB | Per-node status, MCPDLY, enable |
| CLUSTER_CTRL   | 0x03000000   | 96 regs — includes global EDC enable |
| SMN            | 0x03010000   | 325 regs — security/error routing    |

EDC interrupts are routed through the overlay error aggregator to the `CRIT_IRQ` or `FATAL_IRQ` lines, which connect to the Dispatch tile interrupt controllers and ultimately to the Rocket RISC-V core for software handling.

---

## §8 Clock, Reset, and CDC Architecture

### 8.1 Clock Domain Overview

#### 8.1.1 Architecture Rationale

N1B0 uses **five functionally distinct clock domains** (plus ref_clk and aon_clk for infrastructure) because different subsystems have fundamentally incompatible frequency and power requirements:

1. **noc_clk — Fixed-frequency NoC fabric**: The NoC interconnect must run at a stable, predictable frequency to meet timing closure across the full mesh. All four NIU tiles and all router tiles share the same noc_clk. Because every inter-tile communication traverses the NoC, noc_clk jitter directly impacts worst-case end-to-end latency. NoC timing is determined at tape-out and does not change at runtime.

2. **ai_clk[3:0] — Per-column Tensix compute, DVFS-capable**: The Tensix FPU is the dominant power consumer. N1B0 allows each column to run at an independently controlled frequency via the AWM (Adaptive Waveform Manager) PLL. This enables per-column DVFS (Dynamic Voltage and Frequency Scaling): columns running low-priority background compute can be throttled to save power, while columns running critical-path inference keep full frequency. Separating ai_clk per-column also enables partial-chip operation when columns are harvested — the harvested column's clock can be eliminated entirely.

3. **dm_clk[3:0] — Per-column data-move, independent of FPU**: The TDMA engine (pack/unpack) and L1 SRAM arrays run on dm_clk, which is independent from ai_clk within the same column. This separation is critical for the DMA-compute overlap pattern: when the FPU is busy accumulating into DEST (ai_clk domain), the TDMA engine can simultaneously be loading the next weight tile from DRAM into L1 (dm_clk domain) without any clock-domain coupling. If ai_clk were gated to save power during a DMA-only phase, dm_clk would continue running — keeping L1 accessible for NoC-driven DMA without waking up the FPU.

4. **axi_clk — Host bus interface, tracks host frequency**: The AXI master interface (NIU) and APB fabric must be synchronous to the host system bus. The host may run a completely different PLL than the NPU's internal PLLs. axi_clk is provided by the host SoC and is independent of all internal clocks. This isolation means the host can change its bus frequency (e.g., dynamic frequency scaling at the SoC level) without affecting the NPU's internal timing.

5. **PRTN/aon_clk — Always-on power sequencing**: Power-domain enable/disable requires a clock that is active even when all functional clocks are gated. The aon_clk (always-on) provides this. It runs at very low frequency (32 kHz–1 MHz range) and drives only the power sequencing logic and wake handshake. Its low frequency minimizes leakage from the always-on domain.

#### 8.1.2 Clock Domain Diagram

```
                        ┌─────────────────────────────────────────────────────────────────┐
                        │                     N1B0 NPU Clock Tree                         │
                        └─────────────────────────────────────────────────────────────────┘

  External PLL / AWM
  ┌──────────────────────────────────────────────────────────────────────────────────────┐
  │  axi_clk   ──────────────────────────────────── AXI/APB fabric, SMN, AWM, iDMA CSR  │
  │  noc_clk   ──────────────────────────────────── NoC router, NIU, VC FIFOs, EDC ring │
  │  ref_clk   ──────────────────────────────────── AWM PLL reference, frequency meas.  │
  │  aon_clk   ──────────────────────────────────── Always-on domain (power management) │
  │                                                                                      │
  │  i_ai_clk[3:0]   per-column  X=0→col0, X=1→col1, X=2→col2, X=3→col3               │
  │  i_dm_clk[3:0]   per-column  X=0→col0, X=1→col1, X=2→col2, X=3→col3               │
  └──────────────────────────────────────────────────────────────────────────────────────┘

  CDC crossings (async FIFOs or sync3r at each boundary arrow below):

    ai_clk[col] ──CDC──► noc_clk    (Tensix → NoC local port, write path)
    noc_clk     ──CDC──► ai_clk[col](NoC local port → Tensix, read path)
    ai_clk[col] ──CDC──► dm_clk[col](FPU → TDMA/L1 boundary, control signals)
    noc_clk     ──CDC──► axi_clk    (NIU NoC → AXI interface)
    EDC req_tgl ──CDC──► (sync3r at Y=2 intra-tile boundaries only)
```

#### 8.1.3 Clock Domain Summary Table

| Clock       | Source       | Scope                          | Typical Frequency | DVFS? |
|-------------|--------------|--------------------------------|-------------------|-------|
| axi_clk     | Host PLL     | AXI bus, APB, SMN, iDMA CSR   | 400–800 MHz       | No    |
| noc_clk     | External PLL | NoC fabric, NIU, VC FIFO, EDC | 1.0–1.2 GHz       | No    |
| ai_clk[3:0] | AWM PLL      | Tensix FPU, DEST/SRCA regfile | 1.0–1.5 GHz       | Yes   |
| dm_clk[3:0] | AWM PLL      | Overlay data-move, L1 SRAM    | 1.0–1.2 GHz       | Yes   |
| ref_clk     | Crystal / IO | AWM reference / freq measure  | 50–100 MHz        | No    |
| aon_clk     | Always-on    | PRTN power sequencing         | ~32 kHz–1 MHz     | No    |

### 8.2 Per-Column Clock Architecture

Unlike the baseline Trinity design which uses a single ai_clk and single dm_clk for all columns, N1B0 distributes clocks per-column. This enables fine-grained power management and per-column frequency scaling.

```
  Column assignment:
  ┌──────┬──────────┬────────────────────┬────────────────────┬────────────────┐
  │  Col │  X index │  ai_clk input      │  dm_clk input      │ Tile types     │
  ├──────┼──────────┼────────────────────┼────────────────────┼────────────────┤
  │  0   │  X=0     │  i_ai_clk[0]       │  i_dm_clk[0]       │ NW_OPT, T6    │
  │  1   │  X=1     │  i_ai_clk[1]       │  i_dm_clk[1]       │ ROUTER_NW_OPT │
  │  2   │  X=2     │  i_ai_clk[2]       │  i_dm_clk[2]       │ ROUTER_NE_OPT │
  │  3   │  X=3     │  i_ai_clk[3]       │  i_dm_clk[3]       │ NE_OPT, T6    │
  └──────┴──────────┴────────────────────┴────────────────────┴────────────────┘
```

The top-level `trinity.sv` port list includes all eight per-column clock inputs. Inside each tile, `i_ai_clk` and `i_dm_clk` connect to the Tensix FPU and overlay data-move subsystems respectively.

### 8.3 PRTN Chain (Power Partition Sequencing)

#### 8.3.1 Purpose and Motivation

PRTN stands for **Partition**. The PRTN chain is the hardware mechanism for sequencing power-domain enable and disable across the N1B0 tile array. Its primary purposes are:

1. **Inrush current limiting**: If all tiles simultaneously receive their power-enable signal, the combined inrush current from charging decoupling capacitors and activating power switches can exceed the package PDN (Power Delivery Network) current rating and cause Vdd droop. The chain sequences enables tile-by-tile, inserting guaranteed inter-tile delay so that no two tiles switch simultaneously.
2. **Ordered reset release**: After power is stable, tiles must come out of reset in a defined order so that upstream tiles (e.g., Dispatch, NIU) are fully reset before downstream tiles (Tensix compute) start issuing NoC transactions. Out-of-order reset release can cause bus contention or deadlock in the NoC.
3. **Selective tile power-gating**: In low-power modes, individual columns or tiles can be power-gated when idle. The PRTN chain provides the controlled enable/disable sequence for transitioning tiles in and out of the power-gated state without affecting neighboring active tiles.

#### 8.3.2 Chain Structure

The PRTN chain is a daisy-chained handshake that traverses all tiles in a fixed order:

```
  PRTN Chain — full tile traversal order (N1B0):

  PRTN_INPUT (from host/firmware)
       │
       ▼
  ┌──────────┐  PRTN_REQ  ┌──────────┐  PRTN_REQ  ┌──────────┐
  │ Tile     │───────────►│ Tile     │───────────►│ Tile     │
  │ (X=0,Y=0)│◄───────────│ (X=0,Y=1)│◄───────────│ (X=0,Y=2)│
  │          │  PRTN_ACK  │          │  PRTN_ACK  │          │
  └──────────┘            └──────────┘            └──────────┘
       │  (continues through all tiles in column-row order)
       ▼
  PRTN_OUTPUT (to firmware — indicates all tiles powered and reset)

  Clock: PRTNUN_FC2UN_CLK_IN — dedicated, separate from all functional clocks
```

Each tile in the chain:
1. Receives `PRTN_REQ` from the previous tile (or from the chain input for the first tile)
2. Applies local power-enable or reset-release to its internal power domain
3. Waits for local power/reset to stabilize (measured by internal power-on-reset detector)
4. Asserts `PRTN_ACK` back to the previous tile and passes `PRTN_REQ` forward to the next tile
5. The chain advances only after acknowledgment — no tile is enabled until its predecessor is stable

#### 8.3.3 Firmware Interface

Firmware controls the PRTN chain through `PRTNUN_FC2UN` registers in the CLUSTER_CTRL block:

```
// Power-up sequence (typical):
// 1. Configure which tiles to enable (harvest map)
APB_WRITE(CLUSTER_CTRL + PRTN_HARVEST_MASK, harvest_config);

// 2. Trigger PRTN chain to run power-up sequence
APB_WRITE(CLUSTER_CTRL + PRTN_CMD, PRTN_CMD_POWERUP);

// 3. Poll for completion (or wait for PRTN_DONE interrupt)
while (!(APB_READ(CLUSTER_CTRL + PRTN_STATUS) & PRTN_ALL_DONE)) {}

// 4. All tiles in the non-harvested set are now powered and reset-released
```

For selective power-gating (e.g., gating columns 1 and 2 during idle):

```
// Power-gate columns X=1 and X=2:
APB_WRITE(CLUSTER_CTRL + PRTN_GATE_MASK, (1<<1)|(1<<2));  // columns 1 and 2
APB_WRITE(CLUSTER_CTRL + PRTN_CMD, PRTN_CMD_POWERGATE);
// PRTN chain sequences the gate in controlled order
```

#### 8.3.4 Composite Tile PRTN Pass-Through

The composite tiles (NOC2AXI_ROUTER_NE/NW_OPT) span two physical rows (Y=4 and Y=3). The PRTN chain passes through both internal rows in order: the NIU portion at Y=4 is enabled first, then the router portion at Y=3 is enabled. The composite tile module instantiates two PRTN stages internally and presents a single PRTN_REQ/PRTN_ACK interface at the tile boundary.

### 8.4 ISO_EN Harvest Isolation Enable

`ISO_EN[11:0]` is the sixth harvest mechanism in N1B0 (in addition to the five baseline mechanisms). Each bit corresponds to one tile in the 4×3 core grid.

```
  Bit mapping: ISO_EN[x + 4*y]

  ┌──────────────────────────────────────────────────────────────────────┐
  │ Y=0: ISO_EN[3]  ISO_EN[2]  ISO_EN[1]  ISO_EN[0]   (X=3..0)         │
  │ Y=1: ISO_EN[7]  ISO_EN[6]  ISO_EN[5]  ISO_EN[4]   (X=3..0)         │
  │ Y=2: ISO_EN[11] ISO_EN[10] ISO_EN[9]  ISO_EN[8]   (X=3..0)         │
  └──────────────────────────────────────────────────────────────────────┘
```

When `ISO_EN[i]` is asserted:
1. All output signals from tile `i` are driven to safe (inactive) values via AND-type ISO cells
2. The EDC ring bypass mux routes around the harvested tile's EDC node
3. The tile's clock may be gated (handled by DFX wrappers)
4. NoC mesh routing re-configures to avoid the harvested tile's coordinates

### 8.5 Reset Architecture

```
  Reset signals:
  ┌───────────────────────────────────────────────────────────────────┐
  │  i_reset_n        — async global active-low reset                 │
  │                     De-asserted synchronously inside each tile    │
  │                     Controls: all flip-flops in all domains       │
  │                                                                   │
  │  i_axi_reset_n    — AXI domain active-low reset                  │
  │                     Synchronous to axi_clk                       │
  │                     Controls: AXI bus logic, APB, SMN, AWM       │
  └───────────────────────────────────────────────────────────────────┘
```

Each tile contains reset synchronizers for each clock domain it uses:

| Reset synchronizer | Clock domain | Destination |
|--------------------|--------------|-------------|
| ai_clk reset sync  | ai_clk[col]  | FPU, DEST/SRCA, L1 SRAM |
| dm_clk reset sync  | dm_clk[col]  | Overlay, L2 cache       |
| noc_clk reset sync | noc_clk      | NoC router, NIU, EDC    |
| axi_clk reset sync | axi_clk      | APB slave, SFR          |

### 8.6 CDC Crossings

The N1B0 design has five classes of clock-domain crossing. Each uses the mechanism appropriate for the signal type and frequency relationship between source and destination clocks.

#### 8.6.1 ai_clk → noc_clk (Tensix NoC Write Path)

**Location**: Inside the overlay wrapper at the NoC local port, within each Tensix tile.
**Usage**: BRISC NoC DMA write path — when BRISC issues a NoC write command, the write data travels from ai_clk domain (where BRISC and L1 reside) to noc_clk domain (where the NoC local port and VC FIFOs reside).

```
  ai_clk domain                    noc_clk domain
  ┌─────────────────┐               ┌──────────────────────┐
  │  BRISC DMA      │               │  NoC local port       │
  │  write buffer   │               │  VC FIFO              │
  │  (512-bit flits)│──[Async FIFO]─►  (512-bit, 4-deep)   │
  └─────────────────┘               └──────────────────────┘

  Mechanism: Async FIFO
  Width:     512 bits (one full NoC flit)
  Depth:     4 entries
  Empty/Full: Gray-coded pointers, synchronized via 2-FF synchronizers
```

The 4-deep FIFO provides sufficient buffering to absorb one burst of 4 consecutive NoC write flits without back-pressure. With noc_clk ≥ ai_clk in typical operation, the FIFO rarely fills.

#### 8.6.2 noc_clk → ai_clk (Tensix NoC Read Response / Receive Path)

**Location**: Inside the overlay wrapper, receive side, within each Tensix tile.
**Usage**: Incoming NoC data to BRISC/TRISC — when a NoC response flit (e.g., DRAM read data returned from NIU) arrives at the tile's local port, it must cross from noc_clk to ai_clk before being written into L1.

```
  noc_clk domain                   ai_clk domain
  ┌──────────────────┐              ┌─────────────────────┐
  │  NoC local port  │              │  BRISC/TRISC RX buf │
  │  receive FIFO    │──[Async FIFO]►  (feeds L1 write)   │
  │  (512-bit)       │              │                     │
  └──────────────────┘              └─────────────────────┘

  Mechanism: Async FIFO
  Width:     512 bits
  Depth:     4 entries
```

This crossing is the critical path for NoC receive latency. The async FIFO adds a minimum of 2 noc_clk cycles (for write) + 2 ai_clk cycles (for read pointer synchronization) = ~4 cycles of latency at the crossing.

#### 8.6.3 ai_clk → dm_clk (FPU/TDMA Boundary)

**Location**: Inside the overlay wrapper at the TDMA/L1 boundary.
**Usage**: Control signals from the FPU sequencer (ai_clk) to the TDMA pack/unpack engine and L1 SRAM (dm_clk). This crossing allows L1 DMA operations to continue independently while the FPU is running in a different clock domain.

```
  ai_clk domain                    dm_clk domain
  ┌─────────────────┐               ┌──────────────────────┐
  │  FPU sequencer  │               │  TDMA pack/unpack    │
  │  (control sigs) │──[2-FF sync]─►│  (control enables)   │
  │                 │               │                       │
  │  DEST writeback │──[Async FIFO]─►  L1 write path       │
  │  data (32b×N)   │               │  (512-bit)           │
  └─────────────────┘               └──────────────────────┘

  Mechanism (control): 2-FF synchronizer for single-bit enable/valid signals
  Mechanism (data):    Async FIFO for multi-bit data paths
```

The 2-FF synchronizer is sufficient for control signals because they are guaranteed to be stable for multiple cycles by the FPU sequencer protocol (no single-cycle pulses cross this boundary).

#### 8.6.4 noc_clk → axi_clk (NIU AXI Interface)

**Location**: Inside the NIU (`tt_noc2axi`), at the boundary between the NoC flit processing logic and the AXI bus interface.
**Usage**: NoC-to-AXI translation — when a NoC request is converted to an AXI transaction, the address and data must cross from noc_clk (where NoC flit decoding happens) to axi_clk (where AXI channel handshake happens). The reverse path (AXI read response → NoC response flit) also has a crossing in the opposite direction.

```
  noc_clk domain                    axi_clk domain
  ┌──────────────────┐               ┌───────────────────────┐
  │  AW channel buf  │──[Async FIFO]─►  AXI AW channel       │
  │  W data buffer   │──[Async FIFO]─►  AXI W channel        │
  │  AR channel buf  │──[Async FIFO]─►  AXI AR channel       │
  └──────────────────┘               └───────────────────────┘

  axi_clk domain                    noc_clk domain
  ┌──────────────────┐               ┌───────────────────────┐
  │  R data (RDATA)  │──[Async FIFO]─►  NoC flit assembly    │
  │  B resp (BRESP)  │──[Async FIFO]─►  NoC ack packet       │
  └──────────────────┘               └───────────────────────┘

  Mechanism: Async FIFO per AXI channel (AW, W, AR, R, B)
  Width: per-channel: AW=56+misc, W=512+strb, R=512+resp, etc.
```

This is the most complex CDC in the chip because it covers five AXI channels, each with different widths. The RDATA FIFO at the axi_clk→noc_clk boundary is the 512-entry configurable FIFO discussed in §3.7.2.

#### 8.6.5 EDC Ring Toggle CDC

**Location**: At the three intra-tile CDC boundaries in Y=2 Tensix tiles where the EDC ring traverses clock-domain boundaries (ai_clk→noc_clk, noc_clk→ai_clk, ai_clk→dm_clk).
**Usage**: Synchronizing the single-bit `req_tgl` and `ack_tgl` toggle signals as the EDC ring crosses between ai_clk, noc_clk, and dm_clk domains within a Tensix tile.

```
  Domain A (e.g., ai_clk)          Domain B (e.g., noc_clk)
  ┌─────────────────┐               ┌──────────────────────┐
  │  EDC node N     │               │  EDC node N+1        │
  │  req_tgl output │──[sync3r]────►│  req_tgl input       │
  │                 │               │                       │
  │  ack_tgl input  │◄──[sync3r]───│  ack_tgl output      │
  └─────────────────┘               └──────────────────────┘

  Mechanism: sync3r — 3-register synchronizer (3 flip-flop chain)
  Width:     1 bit (req_tgl), 1 bit (ack_tgl)
  Latency:   3 destination clock cycles per crossing
```

**D/C path classification** (per EDC HDD §3.5):
- `req_tgl`, `ack_tgl`: **Control** signals — must pass through synchronizer at domain boundaries
- `data[31:0]`: **Data** signals — captured combinationally only after the control toggle handshake is complete; no separate synchronizer required for data (the toggle protocol guarantees data stability)

As noted in §7.3, `DISABLE_SYNC_FLOPS=1` bypasses these synchronizers for same-clock-domain segments, reducing latency for the majority of the ring. The sync3r is only active at the three genuine inter-domain crossings at Y=2.

### 8.7 DFX Clock Gating Wrappers

#### 8.7.1 Purpose

N1B0 uses four DFX (Design for Test / Design for X) clock gating wrapper modules. Each wrapper serves two orthogonal purposes:

1. **Fine-grained clock gating for power management**: Clock gating at the sub-tile level allows individual functional blocks within a tile to be powered down independently. This is more efficient than gating the entire tile clock because, for example, the L1 SRAM can remain active for DMA while the FPU is gated.
2. **Scan-chain connectivity for ATPG test mode**: DFX wrappers contain the logic to multiplex between functional clock and test clock (scan enable), and to thread the scan chain through each gated block. This allows ATPG patterns to shift test data through even into normally-gated regions.

#### 8.7.2 ICG (Integrated Clock Gate) Cell

All DFX wrappers use **ICG cells** (Integrated Clock Gate, also called latch-based clock gate):

```
  ICG cell structure:
  ┌─────────────────────────────────┐
  │  Latch (active-low)             │
  │    D = EN (clock gate enable)   │
  │    CLK = clock (inverted)       │
  │    Q = latched enable           │
  │                                 │
  │  AND gate:                      │
  │    IN0 = clock                  │
  │    IN1 = latched enable (Q)     │
  │    OUT = gated_clock            │
  └─────────────────────────────────┘

  Timing:
    EN must be stable while clock is HIGH (setup/hold around falling edge)
    Output gated_clock = clock AND latched_enable
    No glitches possible: latch samples EN only when clock is HIGH
```

The latch ensures that the enable signal is sampled only at the correct phase of the clock, preventing any glitch on the gated clock output that could cause spurious state changes in the gated logic.

#### 8.7.3 Wrapper 1 — noc_niu_router_dfx

| Attribute         | Detail                                                    |
|-------------------|-----------------------------------------------------------|
| RTL module        | `noc_niu_router_dfx`                                      |
| Wraps             | NIU (`tt_noc2axi`) + Router (`tt_trinity_router`)          |
| Clock gated       | `noc_clk`                                                 |
| Enable condition  | Tile active (not harvested) AND at least one NoC transaction pending |
| Scan chain        | Threads through NIU VC FIFOs, ATT SRAM, router state FFs  |

**Functional significance**: The NoC is the primary inter-tile communication fabric. When a tile is idle (no incoming or outgoing NoC transactions), gating noc_clk to the NIU and router eliminates the largest single contributor to tile-level dynamic power after the FPU. Because noc_clk runs at 1.0–1.2 GHz, even modest gating efficiency (e.g., 50% duty cycle) provides significant power savings.

**DMA interaction**: When `noc_niu_router_dfx` gates `noc_clk`, no NoC transactions can be initiated or received for that tile. Firmware must ensure that no DMA is outstanding before asserting the gate enable. The NIU RDATA FIFO must be drained first.

#### 8.7.4 Wrapper 2 — overlay_wrapper_dfx

| Attribute         | Detail                                                    |
|-------------------|-----------------------------------------------------------|
| RTL module        | `overlay_wrapper_dfx`                                     |
| Wraps             | Overlay data-move logic (`neo_overlay_wrapper`)           |
| Clock gated       | `ai_clk[col]` and `dm_clk[col]`                           |
| Enable condition  | Tile active AND overlay control path active               |
| Scan chain        | Threads through overlay CDC FIFOs, context-switch logic   |

**Functional significance**: The overlay wrapper contains the CDC FIFOs between ai_clk, noc_clk, and dm_clk domains, the context-switch SRAMs, and the L1/L2 cache control logic. Gating both `ai_clk` and `dm_clk` via this wrapper effectively suspends all data-move operations for the tile. This is the appropriate state when the tile is in deep idle (no compute, no DMA in progress).

#### 8.7.5 Wrapper 3 — instrn_engine_wrapper_dfx

| Attribute         | Detail                                                    |
|-------------------|-----------------------------------------------------------|
| RTL module        | `instrn_engine_wrapper_dfx`                               |
| Wraps             | Instruction engine — TRISC0/1/2 and BRISC processors      |
| Clock gated       | `ai_clk[col]`                                             |
| Enable condition  | Tile active AND a compute kernel is executing             |
| Scan chain        | Threads through TRISC/BRISC instruction fetch FFs, CSRs   |

**Functional significance**: The instruction engines (BRISC for NoC DMA control, TRISC0/1/2 for pack/unpack/SFPU) are clock-intensive blocks that burn power even when stalled waiting for data. Gating `ai_clk` to the instruction engines via this wrapper allows the FPU (if separately active) to continue computing while the processors are held quiescent. This is useful during the tail of a GEMM tile — the FPU finishes draining the accumulator while BRISC is idle.

**Key design choice — separate from L1**: The instruction engine wrapper is separate from the L1 partition wrapper (§8.7.6), because the L1 must remain accessible for DMA even when the instruction engines are gated. If both were in the same wrapper, gating compute would also block DMA access to L1.

#### 8.7.6 Wrapper 4 — t6_l1_partition_dfx

| Attribute         | Detail                                                    |
|-------------------|-----------------------------------------------------------|
| RTL module        | `t6_l1_partition_dfx`                                     |
| Wraps             | T6 L1 SRAM partition (`tt_t6_l1_partition`)               |
| Clock gated       | `dm_clk[col]`                                             |
| Enable condition  | L1 is being accessed (DMA read/write or FPU load active)  |
| Scan chain        | Threads through L1 SRAM address/data path FFs             |

**Functional significance**: The L1 partition contains 256 SRAM macros per tile (N1B0 4× expansion). Even with clock gating at the SRAM macro level, the surrounding address decode and read/write control logic continues to consume power if `dm_clk` runs. The `t6_l1_partition_dfx` wrapper gates `dm_clk` to the entire L1 partition when no L1 access is pending. This is the most energy-efficient state for a tile that is between kernel invocations: instruction engines are gated (§8.7.5), FPU is idle, and L1 is gated.

**N1B0 L1 size impact**: With 256 macros × 768KB per tile, L1 is physically large. The power savings from gating dm_clk to L1 between kernels is proportionally larger in N1B0 than in baseline Trinity (64 macros/tile), making this wrapper particularly important for N1B0 power management.

#### 8.7.7 Wrapper Summary and Interaction Matrix

The four wrappers provide independent control, enabling a hierarchy of power states within each tile:

```
  Power state           noc_niu_router  overlay  instrn_engine  t6_l1_partition
  ─────────────────────────────────────────────────────────────────────────────
  Full active           ENABLED         ENABLED  ENABLED        ENABLED
  Compute only          ENABLED         ENABLED  ENABLED        ENABLED (FPU)
  DMA only (no compute) ENABLED         ENABLED  GATED          ENABLED
  Standby (L1 active)   GATED           ENABLED  GATED          ENABLED
  Deep idle             GATED           GATED    GATED          GATED
  Harvested             GATED           GATED    GATED          GATED
```

During ATPG scan test, all four wrappers switch from ICG (gated) mode to scan-pass-through mode, allowing the scan enable signal to override the clock gate and feed the full-rate test clock to all flip-flops inside each wrapper.

### 8.8 MCPDLY=7 Derivation

```
  Worst-case EDC segment: Y=3 loopback in NOC2AXI_ROUTER composite tile

  REP_DEPTH_LOOPBACK = 6  (repeaters in the loopback path, N1B0 specific)
  +1 safety margin        (additional cycle for EDC node combinational logic)
  ─────────────────────
  MCPDLY = 7 cycles       (programmed into EDC CSR at chip initialization)
```

All ring segments use the same MCPDLY=7 since it covers the worst case. No per-segment MCPDLY override is needed.

---

## §9 Security Monitor Network (SMN)

### 9.1 Overview

The Security Monitor Network (SMN) enforces memory protection and access control for all transactions in the N1B0 NPU. It sits between the NoC/AXI interconnect and the protected resources, checking every incoming transaction against a set of programmed address ranges and access permissions.

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                         SMN Block Diagram                           │
  │                                                                     │
  │  NoC/AXI Masters ──► MST_COMMON ──► MST_MAIN ──► ADDR_TRANS       │
  │                                          │                          │
  │                                     MST_CMD_BUF                    │
  │                                          │                          │
  │                          ┌───────────────┴──────────────┐          │
  │                          ▼                              ▼           │
  │                   SLV_BLOCK                      SLV_NOC_SEC       │
  │                          │                              │           │
  │                   SLV_D2D              SLAVE_MAILBOX_0/1            │
  │                          │                                          │
  │                  Address Range Checker (8 ranges/NIU)              │
  │                          │                                          │
  │              PASS ───────┴─────────── FAIL → slv_ext_error         │
  │                │                               → CRIT_IRQ          │
  │           Protected Resource                                        │
  └─────────────────────────────────────────────────────────────────────┘
```

**Base address:** `0x03010000`
**Total registers:** 325

### 9.2 Sub-Block Map

| Sub-Block          | Offset    | Description                                               |
|--------------------|-----------|-----------------------------------------------------------|
| MST_COMMON         | +0x0000   | Global SMN enable, clock/reset control                   |
| MST_MAIN           | +0x0100   | Master security configuration, security level per master |
| ADDR_TRANS         | +0x0200   | Address translation rules (up to 16 entries)             |
| MST_CMD_BUF        | +0x0300   | Command buffer security assignment                       |
| SLAVE_MAILBOX_0    | +0x0400   | Inter-processor mailbox 0 (host ↔ Dispatch)              |
| SLAVE_MAILBOX_1    | +0x0500   | Inter-processor mailbox 1 (Dispatch ↔ firmware)          |
| SLV_BLOCK          | +0x0600   | Per-slave block access control                           |
| SLV_NOC_SEC        | +0x0700   | NoC slave security registers                             |
| SLV_D2D            | +0x0800   | Die-to-die security control                              |

### 9.3 Address Range Checker

Each NIU contains 8 independent address range checkers. Each range entry is fully programmable:

```
  Per-Range Register Set (for range N, N=0..7):
  ┌──────────────────────────────────────────────────────────────────────┐
  │  RANGE_BASE_N    [31:0]  — start address of protected region        │
  │  RANGE_SIZE_N    [31:0]  — size of region (in bytes, power-of-2)    │
  │  RANGE_PERM_N    [3:0]   — permissions: [3]=exec, [2]=read,        │
  │                             [1]=write, [0]=enable                   │
  │  RANGE_TARGET_N  [7:0]   — target endpoint index for this range     │
  └──────────────────────────────────────────────────────────────────────┘

  Permission encoding:
  4'b0001 = range enabled, no access (block all)
  4'b0101 = Read-only
  4'b0011 = Write-only
  4'b0111 = Read-Write
  4'b1111 = Read-Write-Execute
  4'b0000 = range disabled (pass-through, no check)
```

### 9.4 Firewall Violation Handling

When a transaction violates a range rule (address within a range but permission not granted):

1. Transaction is **blocked** — not forwarded to the target
2. `slv_ext_error` signal is asserted in the offending NIU
3. Error is logged in the SMN status register (`SLV_BLOCK_STATUS`)
4. A **CRIT interrupt** (`CRIT_IRQ`) is raised to the Dispatch tile interrupt controller
5. The interrupt handler (firmware) reads the violation log: offending master ID, address, access type

### 9.5 Mailbox Operation

The two slave mailboxes (`SLAVE_MAILBOX_0` and `SLAVE_MAILBOX_1`) provide hardware-assisted inter-processor communication:

```
  Mailbox Register Set:
  ┌─────────────────────────────────────────────────────────────────┐
  │  MBOX_WRITE_DATA  [31:0]  — write to post a message             │
  │  MBOX_READ_DATA   [31:0]  — read to consume a message           │
  │  MBOX_STATUS      [31:0]  — [0]=full, [1]=empty, [7:4]=count    │
  │  MBOX_INT_EN      [31:0]  — interrupt enable on full/empty      │
  └─────────────────────────────────────────────────────────────────┘

  Usage:
  - Host writes command to SLAVE_MAILBOX_0 → firmware reads and executes
  - Firmware writes result to SLAVE_MAILBOX_1 → host reads
  - Each mailbox generates an interrupt on write (to wake receiver)
```

### 9.6 SMN Programming Example

Configure range 0 to allow Tensix read-write access to DRAM region `0x80000000`–`0x8FFFFFFF`; all other ranges blocked:

```
  # Step 1: Enable SMN
  write 0x03010000 = 0x00000001   # MST_COMMON: global enable

  # Step 2: Program range 0 (Tensix DRAM window)
  write 0x03010600 = 0x80000000   # SLV_BLOCK RANGE_BASE_0
  write 0x03010604 = 0x10000000   # RANGE_SIZE_0 = 256 MB
  write 0x03010608 = 0x00000007   # RANGE_PERM_0 = RW enabled

  # Step 3: Block all other ranges (ranges 1..7 set to block-all)
  write 0x03010610 = 0x00000000   # RANGE_BASE_1 = 0
  write 0x03010618 = 0x00000001   # RANGE_PERM_1 = enabled, no access
  ... (repeat for ranges 2..7)

  # Step 4: Enable interrupt on violation
  write 0x03010700 = 0x00000001   # SLV_NOC_SEC: enable CRIT_IRQ on violation
```

---

## §10 Debug Module (RISC-V External Debug)

### 10.1 Overview

The Debug Module (DM) implements the RISC-V External Debug Support specification v0.13.2. It provides hardware-level debug capabilities including halt/resume control, register read/write, memory access, and arbitrary code execution on any halted hart.

**Base address:** `0x0300A000`
**Total registers:** 17
**Standard:** RISC-V Debug Specification v0.13.2
**Transport:** APB slave, connected to Dispatch tile APB bus

### 10.2 Supported Harts

```
  Hart configuration in N1B0:

  Per Tensix tile:
  ┌────────────────────────────────────────┐
  │  BRISC    — hart 0 (bulk RISC-V core)  │
  │  TRISC0   — hart 1 (thread 0)          │
  │  TRISC1   — hart 2 (thread 1)          │
  │  TRISC2   — hart 3 (thread 2)          │
  └────────────────────────────────────────┘

  12 Tensix tiles × 4 harts/tile = 48 harts total
  Hart ID = tile_index * 4 + hart_within_tile
  tile_index = x * 5 + y  (EndpointIndex encoding)
```

### 10.3 Register Map

| Offset | Register     | Width | Access | Description                                          |
|--------|--------------|-------|--------|------------------------------------------------------|
| 0x000  | DMCONTROL    | 32    | RW     | Halt/resume/reset control for selected harts         |
| 0x004  | DMSTATUS     | 32    | RO     | Per-hart halted/running/unavailable status           |
| 0x008  | HARTINFO     | 32    | RO     | Hart information (data register count, CSR access)   |
| 0x00C  | HALTSUM1     | 32    | RO     | Halt summary for harts 32–63                         |
| 0x010  | HAWINDOWSEL  | 32    | RW     | Hart array window select                             |
| 0x014  | HAWINDOW     | 32    | RW     | Hart array window (enable/select target harts)       |
| 0x018  | ABSTRACTCS   | 32    | RW     | Abstract command status and control                  |
| 0x01C  | COMMAND      | 32    | WO     | Abstract command register                            |
| 0x020  | ABSTRACTAUTO | 32    | RW     | Automatic abstract command execution trigger         |
| 0x040  | PROGBUF0     | 32    | RW     | Program buffer word 0                                |
| 0x044  | PROGBUF1     | 32    | RW     | Program buffer word 1                                |
| 0x048  | PROGBUF2     | 32    | RW     | Program buffer word 2                                |
| 0x04C  | PROGBUF3     | 32    | RW     | Program buffer word 3                                |
| 0x050  | PROGBUF4     | 32    | RW     | Program buffer word 4                                |
| 0x054  | PROGBUF5     | 32    | RW     | Program buffer word 5                                |
| 0x058  | PROGBUF6     | 32    | RW     | Program buffer word 6                                |
| 0x05C  | PROGBUF7     | 32    | RW     | Program buffer word 7                                |
| 0x060  | SBCS         | 32    | RW     | System bus access control and status                 |
| 0x064  | SBADDRESS0   | 32    | RW     | System bus address bits [31:0]                       |
| 0x068  | SBADDRESS1   | 32    | RW     | System bus address bits [63:32]                      |
| 0x06C  | SBDATA0      | 32    | RW     | System bus data bits [31:0]                          |
| 0x070  | SBDATA1      | 32    | RW     | System bus data bits [63:32]                         |

### 10.4 DMCONTROL Register Detail

```
  DMCONTROL [31:0]:
  ┌─────────────────────────────────────────────────────────────────────┐
  │ [31]    haltreq         — 1=request halt for selected harts         │
  │ [30]    resumereq       — 1=request resume for selected harts       │
  │ [29]    hartreset       — 1=assert hart reset                       │
  │ [28]    ackhavereset    — 1=acknowledge hart has been reset         │
  │ [27]    reserved                                                    │
  │ [26]    hasel           — 0=single hart (hartsel), 1=hart array     │
  │ [25:16] hartsello       — lower 10 bits of hart index               │
  │ [15:6]  hartselhi       — upper 10 bits of hart index               │
  │ [5:4]   reserved                                                    │
  │ [3]     setresethaltreq — set halt-on-reset for selected hart       │
  │ [2]     clrresethaltreq — clear halt-on-reset                       │
  │ [1]     ndmreset        — 1=assert non-debug module reset           │
  │ [0]     dmactive        — 1=activate debug module (must be set first)│
  └─────────────────────────────────────────────────────────────────────┘
```

### 10.5 Abstract Commands (COMMAND Register)

The COMMAND register supports three command types:

```
  Command type encoding [31:24]:
  0x00 = Access Register   — read/write GPR, CSR, FPR
  0x01 = Quick Access      — halt, execute PROGBUF, resume in one step
  0x02 = Access Memory     — read/write memory without halting

  Access Register command [23:0]:
  ┌──────────────────────────────────────────────────────────────────┐
  │ [23]    reserved                                                 │
  │ [22:20] aarsize   — 0=8-bit, 1=16-bit, 2=32-bit, 3=64-bit      │
  │ [19]    aarpostincrement — auto-increment address after access   │
  │ [18]    postexec  — 1=execute PROGBUF after register access      │
  │ [17]    transfer  — 1=perform the register access                │
  │ [16]    write     — 0=read (DM←hart), 1=write (DM→hart)         │
  │ [15:0]  regno     — register number (0x1000=CSR base, 0x0=x0)   │
  └──────────────────────────────────────────────────────────────────┘
```

### 10.6 Program Buffer Execution

The 8-word (256-bit) program buffer allows arbitrary instruction execution on a halted hart:

```
  Typical flow to read a memory-mapped register:

  1. Halt the target hart:
       DMCONTROL.haltreq=1, DMCONTROL.hartsel=<hart_id>
       Poll DMSTATUS.allhalted=1

  2. Load address into x1 via abstract command:
       COMMAND = {type=0x00, aarsize=2, transfer=1, write=1, regno=0x1001}
       DATA0 = <target_address>

  3. Write PROGBUF with LW + EBREAK:
       PROGBUF0 = 0x0000A083   # lw x1, 0(x1)
       PROGBUF1 = 0x00100073   # ebreak

  4. Execute PROGBUF:
       COMMAND = {type=0x00, aarsize=2, transfer=0, postexec=1, regno=0x1001}

  5. Read result from x1 via abstract command:
       COMMAND = {type=0x00, aarsize=2, transfer=1, write=0, regno=0x1001}
       result = DATA0

  6. Resume hart:
       DMCONTROL.resumereq=1
       Poll DMSTATUS.allrunning=1
```

### 10.7 System Bus Access (SBCS / SBADDRESS / SBDATA)

The system bus access path allows the debugger to read/write memory without halting any hart. This is useful for monitoring running state:

```
  SBCS register configuration for 32-bit read:
  write SBCS = 0x00040000    # sbaccess=2 (32-bit), sbautoread=0

  # Read a single 32-bit word from address 0x80001234:
  write SBADDRESS0 = 0x80001234
  read  SBDATA0                  # triggers bus read; poll SBCS.sbbusy=0 first

  # Auto-increment read (sequential burst):
  write SBCS = 0x00060000    # sbaccess=2, sbautoincrement=1, sbautoread=1
  write SBADDRESS0 = 0x80001234   # starts first read automatically
  read  SBDATA0                   # data[0]; triggers read of next address
  read  SBDATA0                   # data[1]
  ... (continue for burst length)
```

---

## §11 Adaptive Workload Manager (AWM)

### 11.1 Overview

The Adaptive Workload Manager (AWM) is the power and frequency management subsystem of the N1B0 NPU. It controls PLL settings, monitors voltage droop and temperature, manages clock gating, and exposes a register interface for firmware-driven DVFS (Dynamic Voltage and Frequency Scaling).

**Base address:** `0x03020000`
**Total registers:** 479
**Sub-blocks:** 7

### 11.2 Sub-Block Map

```
  AWM Address Map:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  0x03020000  AWM_GLOBAL     — global enable, IRQ status, error regs  │
  │  0x03020100  FREQUENCY0     — frequency domain 0 (noc_clk)           │
  │  0x03020200  FREQUENCY1     — frequency domain 1 (ai_clk[0])         │
  │  0x03020300  FREQUENCY2     — frequency domain 2 (ai_clk[1])         │
  │  0x03020400  FREQUENCY3     — frequency domain 3 (ai_clk[2])         │
  │  0x03020500  FREQUENCY4     — frequency domain 4 (ai_clk[3])         │
  │  0x03020600  FREQUENCY5     — frequency domain 5 (dm_clk shared)     │
  │  0x03020700  CGM0           — clock gating management block 0        │
  │  0x03020800  CGM1           — clock gating management block 1        │
  │  0x03020900  CGM2           — clock gating management block 2        │
  │  0x03020A00  DROOP_0        — voltage droop detector 0               │
  │  0x03020B00  DROOP_1        — voltage droop detector 1               │
  │  0x03020C00  DROOP_2        — voltage droop detector 2               │
  │  0x03020D00  DROOP_3        — voltage droop detector 3               │
  │  0x03020E00  TEMP_SENSOR    — on-chip temperature sensor             │
  │  0x03020F00  TT_PLL_PVT     — PLL/PVT sensor control and calibration │
  │  0x03021000  CLK_OBSERVE    — clock frequency measurement            │
  └──────────────────────────────────────────────────────────────────────┘
```

### 11.3 AWM_GLOBAL Register Set

| Offset | Register       | Description                                              |
|--------|----------------|----------------------------------------------------------|
| +0x00  | AWM_CTRL       | [0]=global enable, [1]=DVFS enable, [2]=droop_en         |
| +0x04  | AWM_STATUS     | [0]=freq_change_in_progress, [1]=droop_active            |
| +0x08  | AWM_IRQ_STATUS | Interrupt status bits (W1C)                              |
| +0x0C  | AWM_IRQ_EN     | Interrupt enable bits                                    |
| +0x10  | AWM_ERROR_CODE | Last error code from AWM state machine                   |
| +0x14  | AWM_VERSION    | AWM IP version register (RO)                            |

### 11.4 Frequency Domain Control

Each of the 6 FREQUENCY sub-blocks controls one clock frequency domain:

| Domain | Sub-block   | Clock output     | Controls                        |
|--------|-------------|------------------|---------------------------------|
| 0      | FREQUENCY0  | noc_clk          | NoC fabric, NIU, EDC ring       |
| 1      | FREQUENCY1  | ai_clk[0]        | Column 0 Tensix compute         |
| 2      | FREQUENCY2  | ai_clk[1]        | Column 1 Tensix compute         |
| 3      | FREQUENCY3  | ai_clk[2]        | Column 2 Tensix compute         |
| 4      | FREQUENCY4  | ai_clk[3]        | Column 3 Tensix compute         |
| 5      | FREQUENCY5  | dm_clk (shared)  | Data-move overlay, all columns  |

Per-domain registers (offset within each FREQUENCYn block):

```
  ┌──────────────────────────────────────────────────────────────────┐
  │  +0x00  FREQ_TARGET   [15:0]  — target frequency code           │
  │  +0x04  FREQ_CURRENT  [15:0]  — current operating frequency     │
  │  +0x08  FREQ_MIN      [15:0]  — minimum allowed frequency       │
  │  +0x0C  FREQ_MAX      [15:0]  — maximum allowed frequency       │
  │  +0x10  PLL_DIVIDER   [7:0]   — PLL output divider setting      │
  │  +0x14  FREQ_STATUS   [3:0]   — [0]=locked, [1]=changing,       │
  │                                  [2]=droop_limited               │
  │  +0x18  FREQ_CTRL     [3:0]   — [0]=enable, [1]=bypass_pll      │
  └──────────────────────────────────────────────────────────────────┘
```

### 11.5 Frequency Scaling Flow

```
  Firmware DVFS flow (increase ai_clk[0] frequency):
  ┌──────────────────────────────────────────────────────────────────────┐
  │  1. Verify no active transitions:                                    │
  │       poll FREQUENCY1.FREQ_STATUS[1] == 0 (not changing)            │
  │                                                                      │
  │  2. Set new target frequency:                                        │
  │       write 0x03020100 + 0x00 = <new_freq_code>                     │
  │                                                                      │
  │  3. Trigger frequency change:                                        │
  │       write FREQUENCY1.FREQ_CTRL[0] = 1                             │
  │                                                                      │
  │  4. Poll for completion:                                             │
  │       poll FREQUENCY1.FREQ_STATUS[0] == 1 (PLL locked)              │
  │       poll FREQUENCY1.FREQ_STATUS[1] == 0 (not changing)            │
  │                                                                      │
  │  5. Verify actual frequency:                                         │
  │       read FREQUENCY1.FREQ_CURRENT — should match FREQ_TARGET        │
  └──────────────────────────────────────────────────────────────────────┘
```

### 11.6 CGM (Clock Gating Management)

Three CGM blocks manage autonomous clock gating based on activity monitoring:

| CGM Block | Scope          | Gating Granularity       |
|-----------|----------------|--------------------------|
| CGM0      | noc_clk domain | Per-row NoC router gating |
| CGM1      | ai_clk domain  | Per-tile Tensix FPU gating |
| CGM2      | dm_clk domain  | Per-tile overlay gating   |

CGM registers (per block):

```
  +0x00  CGM_ENABLE    — bit-per-tile autonomous gating enable
  +0x04  CGM_IDLE_CNT  — idle cycle threshold before gating
  +0x08  CGM_STATUS    — current gating state per tile (1=gated)
  +0x0C  CGM_FORCE_ON  — force clocks on (overrides autonomous gating)
  +0x10  CGM_WAKEUP_LAT — wakeup latency in cycles (for scheduler use)
```

### 11.7 Voltage Droop Detectors

Four droop detectors monitor supply voltage across the die. When voltage droops (typically during a sudden load increase), the detectors automatically trigger a frequency reduction to prevent timing failures.

```
  Droop Detector Architecture:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Ring oscillator → frequency counter → compare against threshold     │
  │                                                                      │
  │  On droop detected:                                                  │
  │  1. Hardware immediately reduces PLL output (frequency step-down)    │
  │  2. DROOP_STATUS register updated                                    │
  │  3. AWM_IRQ_STATUS[DROOP_IRQ] asserted                               │
  │  4. Firmware ISR reads cause, logs event, optionally adjusts voltage │
  │  5. When voltage recovers: auto frequency restore (if configured)    │
  └──────────────────────────────────────────────────────────────────────┘
```

Per-droop-detector registers:

| Offset | Register         | Description                                        |
|--------|------------------|----------------------------------------------------|
| +0x00  | DROOP_CTRL       | [0]=enable, [1]=auto_restore, [2]=irq_en           |
| +0x04  | DROOP_THRESHOLD  | Ring oscillator count threshold for droop detect   |
| +0x08  | DROOP_FREQ_STEP  | Frequency step-down amount on droop event          |
| +0x0C  | DROOP_STATUS     | [0]=droop_active, [1]=freq_reduced, [15:8]=count   |
| +0x10  | DROOP_LOG        | Timestamp of last droop event                      |

### 11.8 Temperature Sensor

The on-chip temperature sensor provides continuous die temperature monitoring with configurable threshold interrupts.

```
  TEMP_SENSOR registers:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  +0x00  TEMP_CTRL       — [0]=enable sensor, [1]=continuous_mode     │
  │  +0x04  TEMP_STATUS     — [0]=conversion_done, [1]=high_alert        │
  │  +0x08  TEMP_DATA       — [15:0] current temperature (°C, signed)    │
  │  +0x0C  TEMP_HIGH_THR   — high temperature threshold (°C)            │
  │  +0x10  TEMP_LOW_THR    — low temperature threshold (°C)             │
  │  +0x14  TEMP_IRQ_EN     — [0]=high_thr_en, [1]=low_thr_en           │
  │  +0x18  TEMP_CALIB      — calibration offset (factory programmed)    │
  └──────────────────────────────────────────────────────────────────────┘

  Reading temperature:
    poll TEMP_STATUS[0] == 1   (conversion done)
    temp_celsius = (signed16) TEMP_DATA[15:0]  (LSB = 0.1°C resolution)
```

### 11.9 PLL/PVT Sensor (TT_PLL_PVT)

```
  TT_PLL_PVT sub-block controls and calibrates the on-chip PLLs:
  ┌───────────────────────────────────────────────────────────────────┐
  │  +0x00  PLL_CTRL        — PLL enable/bypass/lock control          │
  │  +0x04  PLL_CFG0        — PLL multiplication factor (M divider)   │
  │  +0x08  PLL_CFG1        — PLL input/output dividers (N/OD)        │
  │  +0x0C  PLL_STATUS      — [0]=locked, [1]=loss_of_lock            │
  │  +0x10  PVT_CTRL        — PVT sensor enable                       │
  │  +0x14  PVT_DATA        — PVT sensor reading (voltage/process)    │
  │  +0x18  PVT_CALIB       — factory calibration value               │
  └───────────────────────────────────────────────────────────────────┘
```

### 11.10 Clock Observation (CLK_OBSERVE)

The CLK_OBSERVE sub-block measures the frequency of any internal clock by counting cycles over a fixed ref_clk window:

```
  +0x00  CLKOBS_SEL    — clock select mux (which clock to observe)
  +0x04  CLKOBS_CTRL   — [0]=start measurement, [1]=continuous mode
  +0x08  CLKOBS_WINDOW — measurement window in ref_clk cycles
  +0x0C  CLKOBS_COUNT  — measured target clock cycles in window
  +0x10  CLKOBS_STATUS — [0]=done, [1]=overflow

  Computed frequency = CLKOBS_COUNT * (ref_clk_freq / CLKOBS_WINDOW)
```

---

## §12 Memory Architecture

### 12.1 Overview

The N1B0 NPU memory hierarchy spans multiple SRAM types across three clock domains. The L1 SRAM capacity is 4× the baseline Trinity design, enabling larger intermediate tensor buffers for LLM and other workloads.

```
  N1B0 Memory Hierarchy:
  ┌─────────────────────────────────────────────────────────────────────────┐
  │  Level      │ Type          │ Domain   │ Per-tile   │ Total (12 tiles)  │
  │  ───────────────────────────────────────────────────────────────────── │
  │  DEST RF    │ Latch array   │ ai_clk   │ 12,288 e   │ 147,456 entries   │
  │  SRCA RF    │ Latch array   │ ai_clk   │  1,536 e   │  18,432 entries   │
  │  L1 SRAM    │ SRAM macro    │ ai_clk   │ 768 KB     │  9.216 MB         │
  │  TRISC I$   │ SRAM macro    │ ai_clk   │ per-TRISC  │  ~576 macros      │
  │  TRISC LM   │ SRAM macro    │ ai_clk   │ per-TRISC  │  local scratch    │
  │  L2 cache   │ SRAM macro    │ dm_clk   │ Dispatch   │  ~256 KB/Dispatch │
  │  OVL cache  │ SRAM macro    │ dm_clk   │ global     │  ~840 macros      │
  │  NoC VC     │ SRAM macro    │ noc_clk  │ router     │  ≥62 macros       │
  │  ATT SRAM   │ SRAM macro    │ noc_clk  │ per NIU    │  64 entries/NIU   │
  └─────────────────────────────────────────────────────────────────────────┘
```

### 12.2 L1 SRAM (T6 L1 — N1B0 Expanded)

The T6 L1 SRAM is the primary scratchpad for Tensix compute tiles.

```
  N1B0 L1 Configuration vs Baseline:
  ┌─────────────────────┬────────────────────┬──────────────────────┐
  │  Parameter          │  Baseline Trinity   │  N1B0               │
  ├─────────────────────┼────────────────────┼──────────────────────┤
  │  Macros per tile    │  64                 │  256                 │
  │  Macro size         │  3 KB (128×192b)    │  3 KB (128×192b)     │
  │  Total per tile     │  192 KB             │  768 KB              │
  │  Total (12 tiles)   │  2.304 MB           │  9.216 MB            │
  │  Read ports         │  4                  │  4                   │
  │  Write ports        │  2                  │  2                   │
  │  ECC                │  Yes (SECDED)       │  Yes (SECDED)        │
  │  DFX wrapper        │  None               │  t6_l1_partition_dfx │
  └─────────────────────┴────────────────────┴──────────────────────┘
```

L1 bank arbitration policy: priority given to TDMA (DMA engine) over CPU accesses to minimize stall cycles during matrix operations.

### 12.3 L1 CSR (T6_L1_CSR, base 0x03000200)

Key L1 control registers:

| Offset | Register       | Description                                         |
|--------|----------------|-----------------------------------------------------|
| +0x00  | RD_PORT_CTRL   | Read port enable mask [3:0]                         |
| +0x04  | WR_PORT_CTRL   | Write port enable mask [1:0]                        |
| +0x08  | GROUP_HASH_FN0 | Bank interleaving hash function 0 configuration     |
| +0x0C  | GROUP_HASH_FN1 | Bank interleaving hash function 1 configuration     |
| +0x10  | ECC_STATUS     | [0]=correctable error, [1]=uncorrectable error      |
| +0x14  | ECC_ADDR       | Address of last ECC error                           |
| +0x18  | CONFLICT_CNT   | Bank conflict counter (performance monitoring)      |
| +0x1C  | BW_THROTTLE    | Bandwidth throttle control (max requests/cycle)     |

### 12.4 DEST Register File

The destination register file stores MAC accumulation results in Tensix tiles:

```
  DEST RF Specifications:
  ┌──────────────────────────────────────────────────────────────────┐
  │  Type:        Latch array (not SRAM macro)                       │
  │  Entries:     12,288 per tile                                    │
  │  Width:       32 bits per entry (FP32 accumulation)              │
  │  Domain:      ai_clk                                            │
  │  Read ports:  1 (to FPU output mux)                              │
  │  Write ports: 1 (from FPU accumulator)                           │
  │  ECC:         Not present (protected by FPU result checking)     │
  │  EDC:         Included in EDC ring coverage (CRIT on fault)      │
  └──────────────────────────────────────────────────────────────────┘
```

### 12.5 SRCA Register File

SRCA holds source operands for the Tensix FPU (matrix A side):

```
  SRCA RF Specifications:
  ┌──────────────────────────────────────────────────────────────────┐
  │  Type:        Latch array (not SRAM macro)                       │
  │  Entries:     1,536 per tile                                     │
  │  Width:       16 bits per entry (FP16/BF16/INT16 operands)       │
  │  Domain:      ai_clk                                            │
  │  Feed path:   L1 → TDMA unpacker → SRCA → FPU M-Tile            │
  │  EDC:         Covered (CRIT on fault)                            │
  └──────────────────────────────────────────────────────────────────┘
```

### 12.6 NoC VC FIFOs

Each NoC router contains per-virtual-channel FIFOs for flow control:

```
  VC FIFO Configuration:
  ┌──────────────────────────────────────────────────────────────────┐
  │  Virtual channels: 2 per port direction                          │
  │  Port directions:  North, South, East, West, Local               │
  │  FIFO depth:       4–16 flits per VC (design-specific)          │
  │  FIFO width:       512 bits (full flit width)                   │
  │  Total macros:     ≥62 across all router instances              │
  │  Domain:           noc_clk                                      │
  │  ECC:              Yes (for in-flight flit protection)          │
  └──────────────────────────────────────────────────────────────────┘
```

For the NOC2AXI_ROUTER_OPT variants, the RDATA FIFO depth is configurable via a Verilog define:

- Default: 512 entries
- Range: 32–1024 entries
- DK path: `used_in_n1/` scope

### 12.7 ATT SRAM (Address Translation Table)

Each NIU contains a 64-entry ATT SRAM for address routing:

```
  ATT Entry Format [63:0]:
  ┌──────────────────────────────────────────────────────────────────┐
  │  [63:32]  MASK      — address mask bits                         │
  │  [31:16]  ENDPOINT  — target endpoint index                     │
  │  [15:8]   ROUTING   — routing mode flags                        │
  │  [7:0]    VALID     — entry valid bit and priority              │
  └──────────────────────────────────────────────────────────────────┘

  ATT lookup: incoming AXI address is compared against all valid entries
  (masked comparison). First hit determines routing endpoint.
  On miss: default route used (programmed in NIU_DEFAULT_ROUTE register).
```

### 12.8 Full SRAM Count Summary

| Clock Domain | Memory Type           | Count (N1B0)            |
|--------------|-----------------------|-------------------------|
| ai_clk       | T6 L1 SRAM            | 3,072 macros            |
| ai_clk       | DEST register file    | 12,288 latch entries    |
| ai_clk       | SRCA register file    | 1,536 latch entries     |
| ai_clk       | TRISC instruction $   | ~576 macros             |
| ai_clk       | TRISC local memory    | per-TRISC scratchpad    |
| dm_clk       | Overlay L1/L2 cache   | ~840 macros             |
| noc_clk      | Router VC FIFOs       | ≥62 macros              |
| noc_clk      | NIU ATT SRAM          | 64 entries per NIU      |
| axi_clk      | iDMA command buffer   | per-iDMA instance       |

---

## §13 SFR Summary

### 13.1 Complete SFR Memory Map

All software-visible registers are mapped into a contiguous region starting at `0x03000000`. The table below covers all 8 subsystems.

```
  N1B0 NPU SFR Map (0x03000000 – 0x0302FFFF):
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  0x03000000 ─────────────────────────────────── 0x030001FF                   │
  │  CLUSTER_CTRL (96 registers)                                                 │
  │  Clock enable, soft reset, core configuration, tile enable mask              │
  │  Key: CLK_EN[15:0], SOFT_RESET[15:0], CORE_CONFIG, TILE_EN_MASK             │
  │       EDC_GLOBAL_EN, EDC_BYPASS_MASK, ISO_EN[11:0], CHIP_ID, VERSION        │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03000200 ─────────────────────────────────── 0x030003FF                   │
  │  T6_L1_CSR (91 registers)                                                    │
  │  L1 SRAM port config, ECC, bank hash function, bandwidth throttle           │
  │  Key: RD_PORT_CTRL, WR_PORT_CTRL, GROUP_HASH_FN0/1, ECC_STATUS/ADDR        │
  │       CONFLICT_CNT, BW_THROTTLE                                             │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03000400 ─────────────────────────────────── 0x030005FF                   │
  │  CACHE_CTRL (7 registers)                                                    │
  │  L2 cache enable, flush, invalidate, hit/miss performance counters          │
  │  Key: CACHE_ENABLE, CACHE_FLUSH, CACHE_INVALIDATE, HIT_CNT, MISS_CNT       │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03000600 ─────────────────────────────────── 0x030041FF                   │
  │  LLK_TILE_COUNTERS (576 registers)                                           │
  │  Per-tile operation counters and stall counters (N=0..11 per tile)          │
  │  Key: TILE_OP_CNT[N], TILE_STALL_CNT[N], TILE_IDLE_CNT[N]                  │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03004000 ─────────────────────────────────── 0x03009FFF                   │
  │  IDMA_APB (1,528 registers)                                                  │
  │  8 iDMA engine register sets; command buffer, address generator, DMA ctrl   │
  │  Key: CMD_BUF[0..7], ADDR_GEN[0..7], SIMPLE_CMD, DMA_STATUS, DMA_CTRL     │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x0300A000 ─────────────────────────────────── 0x0300AFFF                   │
  │  DEBUG_MODULE (17 registers — RISC-V Debug v0.13.2)                          │
  │  Hart halt/resume/reset, abstract commands, program buffer, sys bus access  │
  │  Key: DMCONTROL, DMSTATUS, ABSTRACTCS, COMMAND, PROGBUF0..7, SBCS          │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03010000 ─────────────────────────────────── 0x0301FFFF                   │
  │  SMN (325 registers)                                                         │
  │  Address range checkers, firewall, inter-processor mailboxes, master sec.   │
  │  Key: RANGE_BASE/SIZE/PERM[0..7], MBOX_WRITE/READ/STATUS, MST_MAIN_CTRL    │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  0x03020000 ─────────────────────────────────── 0x0302FFFF                   │
  │  AWM (479 registers)                                                         │
  │  PLL/frequency control, clock gating, droop detection, temperature sensor   │
  │  Key: FREQ_TARGET/CURRENT[0..5], CGM_ENABLE, DROOP_CFG, TEMP_DATA, PLL_CFG │
  └──────────────────────────────────────────────────────────────────────────────┘
```

### 13.2 Subsystem Register Count Table

| Subsystem         | Base Address | End Address  | Reg Count | Access  | Notes                           |
|-------------------|-------------|--------------|-----------|---------|----------------------------------|
| CLUSTER_CTRL      | 0x03000000  | 0x030001FF   | 96        | RW/RO   | CLK_EN, SOFT_RESET, ISO_EN       |
| T6_L1_CSR         | 0x03000200  | 0x030003FF   | 91        | RW/RO   | Port ctrl, ECC, bank hash        |
| CACHE_CTRL        | 0x03000400  | 0x030005FF   | 7         | RW/WO   | L2 enable, flush, invalidate     |
| LLK_TILE_COUNTERS | 0x03000600  | 0x030041FF   | 576       | RO/RW   | Per-tile performance counters    |
| IDMA_APB          | 0x03004000  | 0x03009FFF   | 1,528     | RW      | 8 DMA engines                    |
| DEBUG_MODULE      | 0x0300A000  | 0x0300AFFF   | 17        | RW/RO   | RISC-V Debug v0.13.2             |
| SMN               | 0x03010000  | 0x0301FFFF   | 325       | RW/RO   | Security, firewall, mailbox      |
| AWM               | 0x03020000  | 0x0302FFFF   | 479       | RW/RO   | DVFS, droop, temp, PLL           |
| **Total**         |             |              | **3,119** |         |                                  |

### 13.3 CLUSTER_CTRL Key Registers

| Offset | Register         | Bits   | Description                                           |
|--------|------------------|--------|-------------------------------------------------------|
| +0x000 | CLK_EN           | [15:0] | Per-tile clock enable (tile index = x*5+y)            |
| +0x004 | SOFT_RESET       | [15:0] | Per-tile soft reset (write 1 to assert reset)         |
| +0x008 | CORE_CONFIG      | [31:0] | Global: endianness, debug mode, boot address          |
| +0x00C | TILE_EN_MASK     | [15:0] | Tile enable mask (harvested tiles masked off)         |
| +0x010 | NOC_MESH_CONFIG  | [31:0] | NoC mesh size override (for harvest routing)          |
| +0x014 | EDC_GLOBAL_EN    | [0]    | Global EDC ring enable                                |
| +0x018 | EDC_BYPASS_MASK  | [15:0] | Per-tile EDC bypass (for harvested tiles)             |
| +0x01C | ISO_EN           | [11:0] | Harvest isolation enable (bit[x+4*y] per tile)        |
| +0x020 | CHIP_ID          | [31:0] | Chip identification register (RO, factory set)        |
| +0x024 | VERSION          | [31:0] | RTL version register (RO)                             |

### 13.4 IDMA_APB Key Registers

The iDMA APB block contains 8 independent DMA engine register sets. Each engine is at base offset `E * 0x1000` (E=0..7):

```
  Per-engine register set:
  ┌──────────────────────────────────────────────────────────────────────┐
  │  +0x000  CMD_BUF_CTRL    — command buffer: write_ptr, read_ptr, depth│
  │  +0x004  CMD_BUF_STATUS  — [0]=empty, [1]=full, [3:2]=error_code     │
  │  +0x008  SIMPLE_CMD_SRC  — simple command: source address            │
  │  +0x00C  SIMPLE_CMD_DST  — simple command: destination address       │
  │  +0x010  SIMPLE_CMD_LEN  — simple command: transfer length (bytes)   │
  │  +0x014  SIMPLE_CMD_GO   — write 1 to launch simple command          │
  │  +0x018  ADDR_GEN_SRC    — address generator source: base, stride    │
  │  +0x01C  ADDR_GEN_DST    — address generator dest: base, stride      │
  │  +0x020  ADDR_GEN_DIM    — multi-dimensional stride config (4D)      │
  │  +0x024  DMA_STATUS      — running/idle/error status bits            │
  │  +0x028  DMA_IRQ_EN      — interrupt enable (done, error, overflow)  │
  │  +0x02C  DMA_CHAIN_PTR   — pointer to next chained command descriptor│
  └──────────────────────────────────────────────────────────────────────┘
```

### 13.5 SFR Access Protocol

All SFR registers are accessed via the APB (Advanced Peripheral Bus) slave interface in the Dispatch tile. Access rules:

- **Width**: 32-bit aligned accesses only; byte/halfword accesses not supported
- **Read-only registers**: writes are silently ignored (no error response)
- **W1C registers**: write 1 to clear (e.g., interrupt status registers)
- **Read-to-clear registers**: some status registers clear on read (RTC, noted in register description)
- **Write-once registers**: can only be written once after reset (e.g., security configuration)

---

## §14 Verification Checklist

### 14.1 Overview

This section defines the hardware verification (HW DV) checklist for the N1B0 NPU. Each sub-block has a set of required test scenarios that must pass before tape-out sign-off.

```
  Verification sign-off status legend:
  [ ] — Not started
  [P] — In progress
  [D] — Done / passing
  [W] — Waived with documented rationale
```

### 14.2 Tensix FPU Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | INT16 MAC accumulation: all input ranges including max/min/overflow | 100% format pairs | FPU G-Tile |
| 2 | FP16B × FP16B matrix multiply, compare vs golden reference model | <1 ULP error | FPU M-Tile |
| 3 | Stochastic rounding: verify probabilistic distribution over 10K samples | SR probability within ±5% | FP Lane |
| 4 | Format conversion: FP32→FP16B, FP32→BF16, INT16→FP32 | all conversion paths | FPU |
| 5 | SRCA/SRCB register file: concurrent read/write, no data corruption | 100% bank combinations | SRCA/SRCB |
| 6 | DEST register file: accumulate 512 back-to-back MACs, verify final value | no saturation error | DEST |
| 7 | SFPU transcendental functions: exp, log, sqrt, reciprocal vs IEEE reference | <2 ULP error | SFPU |
| 8 | Booth multiplier: corner cases (max_neg × max_neg, 0×X, X×1, X×-1) | boundary inputs | Booth |
| 9 | Compressor tree: multi-cycle accumulation with carry chain wrap-around | no carry loss | Compressor |
| 10 | Safety controller: inject single FPU fault, verify FATAL interrupt path | fault → FATAL_IRQ | Safety |

### 14.3 L1 SRAM Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Bank conflict resolution: simultaneous 4-read + 2-write to same bank | no deadlock, correct arbitration | L1 arbiter |
| 2 | ECC single-bit error injection and correction | 100% ECC code words exercised | SRAM ECC |
| 3 | ECC double-bit error injection → CRIT interrupt | uncorrectable → CRIT_IRQ | SRAM ECC |
| 4 | All four read ports simultaneous (4-port stress) | no data corruption | L1 read ports |
| 5 | TDMA vs CPU port arbitration: verify TDMA priority under contention | TDMA wins under contention | L1 arbiter |
| 6 | Bank interleaving: verify GROUP_HASH_FN0/1 distributes accesses evenly | even bank utilization | L1 hash |
| 7 | DFX clock gating: gate and un-gate L1 clock, verify state retention | no data loss on gate/ungate | t6_l1_partition_dfx |
| 8 | L1 post-reset: verify all entries are initialized after reset de-assertion | deterministic post-reset state | L1 |

### 14.4 NoC Router Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | DOR routing: XY dimension-order route across full 4×5 grid | all src/dst pairs | Router |
| 2 | Dynamic routing: 928-bit carried list propagation across 5 hops | list correct at NIU | Router |
| 3 | Path squash: inject path_squash flit, verify route re-direction | flit delivered via new path | Router |
| 4 | Multicast: send to all-Tensix endpoint group | all 12 tiles receive, no duplicates | Router |
| 5 | VC deadlock avoidance: create conflicting routes, verify no deadlock | 1000-cycle stress test | VC arbiter |
| 6 | VC FIFO full: fill all VCs to capacity, verify backpressure propagation | no flit loss under backpressure | VC FIFO |
| 7 | ECC on VC FIFO: inject single-bit error, verify in-flight correction | ECC corrected | VC FIFO ECC |
| 8 | force_dim_routing: set force_dim=EAST, verify routing ignores Y coordinate | Y-axis not used for routing | Router |
| 9 | tendril routing: configure tendril, send flit, verify out-of-mesh delivery | flit exits via tendril port | Tendril |
| 10 | ATT lookup: program all 64 entries, stress with 64 simultaneous lookups | no collision, correct hit | ATT |

### 14.5 iDMA Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Simple 1D transfer: L1→L1 across tiles via NoC | correct data delivery | iDMA |
| 2 | Multi-dimensional stride: 4D tensor with non-contiguous strides | correct address generation | ADDR_GEN |
| 3 | Chain command: 8-descriptor chain, each with different src/dst/length | all descriptors execute in order | CMD_BUF |
| 4 | Mid-chain error: inject error at descriptor 4, verify error interrupt | error → DMA_IRQ, chain halted | iDMA |
| 5 | Concurrent 8-engine operation: all 8 iDMA engines running simultaneously | no bus contention or starvation | iDMA × 8 |
| 6 | Interrupt on completion: verify done IRQ fires exactly once per transfer | exactly 1 IRQ per transfer | iDMA IRQ |
| 7 | Boundary conditions: transfer length=0, length=1, length=max | correct handling in all cases | iDMA |
| 8 | AXI outstanding limit: issue 256 outstanding AXI transactions | no deadlock, all complete | AXI arbiter |

### 14.6 EDC Ring Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Ring initialization: full ring startup from reset, all nodes reach READY state | all nodes ready within timeout | EDC ring |
| 2 | FATAL fault injection: force toggle mismatch in one node → FATAL_IRQ | FATAL detected within 10 cycles | EDC node |
| 3 | CRIT fault injection: inject DEST RF parity error → CRIT_IRQ | CRIT escalation path complete | EDC/DEST |
| 4 | n-crt fault: inject non-critical event, verify logged but no interrupt | log entry in CSR, no IRQ | EDC CSR |
| 5 | ECC+ correction: inject correctable L1 ECC error, verify silent correction | no interrupt, correction logged | L1/EDC |
| 6 | ECC− uncorrectable: inject 2-bit L1 ECC error → CRIT interrupt | CRIT_IRQ fires correctly | L1/EDC |
| 7 | Harvest bypass: disable tile (0,0) via ISO_EN, verify ring continues uninterrupted | ring stable with bypass active | EDC bypass |
| 8 | MCPDLY check: measure toggle round-trip latency, confirm ≤7 cycles worst-case | max latency ≤ MCPDLY | EDC ring |
| 9 | async_init recovery: reset one node mid-operation, verify ring restores | ring restores in <100 cycles | sync3r |
| 10 | Multi-fault: inject faults in 3 nodes simultaneously | all 3 faults detected and reported | EDC ring |

### 14.7 SMN Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Range violation detection: send transaction outside permitted range | slv_ext_error asserted correctly | SMN range |
| 2 | Firewall logging: verify violation entry written to SLV_BLOCK_STATUS | log readable by firmware ISR | SMN log |
| 3 | Mailbox 0 operation: host writes, firmware reads, verify no message loss | write/read handshake correct | MBOX_0 |
| 4 | Mailbox 1 operation: firmware writes, host reads, interrupt on write | IRQ fires on every write | MBOX_1 |
| 5 | All 8 ranges simultaneously active: 8 parallel transactions | correct routing for all 8 | Range checker |
| 6 | Security level escalation: low-security master attempts high-security access | access blocked, CRIT_IRQ | MST_MAIN |
| 7 | Address translation: verify ADDR_TRANS maps addresses to correct endpoints | translated address correct | ADDR_TRANS |
| 8 | SMN reset: reset SMN, verify all ranges cleared, no spurious interrupts | clean post-reset state | SMN |

### 14.8 Debug Module Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Halt single hart: halt BRISC on tile (0,0), verify DMSTATUS.allhalted | halt within 10 cycles | DM |
| 2 | Resume from halt: resume halted hart, verify PC execution continues | PC increments after resume | DM |
| 3 | GPR read/write via abstract command: read x1, write x5=0xDEAD_BEEF | all GPRs accessible | DM |
| 4 | CSR read/write: read/write mstatus, mtvec via abstract command | key CSRs accessible | DM |
| 5 | PROGBUF execution: load target address in x1, execute lw+ebreak, read result | correct memory value returned | DM PROGBUF |
| 6 | System bus read: read memory at 0x80001234 without halting any hart | correct data, hart stays running | DM SBA |
| 7 | System bus write: write to uncached memory region via SBA | memory updated correctly | DM SBA |
| 8 | Multi-hart halt: halt all 48 harts simultaneously via HAWINDOW | all harts halt within 20 cycles | DM |
| 9 | Halt-on-reset: set DMCONTROL.setresethaltreq, toggle reset, verify halt at PC=0 | hart halted immediately at reset exit | DM |
| 10 | PROGBUF exception: execute invalid instruction in PROGBUF, verify cmderr=3 | cmderr[2:0]=3 (exception flag set) | DM |

### 14.9 AWM Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | Frequency scaling up: increase ai_clk[0] in 100 MHz steps to maximum | PLL locks at each step | AWM FREQ |
| 2 | Frequency scaling down: decrease ai_clk[0] to minimum, verify no glitch | clean step-down, no glitch | AWM FREQ |
| 3 | Droop response: simulate voltage droop (ring oscillator period increase) | auto frequency reduction triggered | AWM DROOP |
| 4 | Droop recovery: voltage recovers, verify auto frequency restore | frequency restored to pre-droop level | AWM DROOP |
| 5 | Temperature threshold interrupt: set high threshold 5°C above ambient | TEMP_IRQ fires when threshold crossed | AWM TEMP |
| 6 | CGM autonomous gating: idle all Tensix tiles, verify clocks gate after idle_cnt | clocks gated within idle_cnt+2 cycles | CGM |
| 7 | CGM force-on: assert CGM_FORCE_ON, verify clocks remain on when idle | clocks stay on regardless of idle state | CGM |
| 8 | PLL lock loss: remove ref_clk briefly, verify LOSS_OF_LOCK IRQ | IRQ fires within 10 ref_clk cycles | TT_PLL_PVT |
| 9 | Clock observation: measure noc_clk via CLK_OBSERVE, compare to expected | measured frequency within ±2% | CLK_OBSERVE |
| 10 | All 6 frequency domains independent: change each domain independently | no inter-domain coupling observed | FREQ0..5 |

### 14.10 Clock Gating and DFX Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | noc_niu_router_dfx gate/ungate: gate NoC clock mid-operation (drain FIFOs first) | no flit loss on gate/ungate | DFX wrapper |
| 2 | overlay_wrapper_dfx: gate dm_clk, verify SRAM state retained on resume | L2 contents intact after un-gate | DFX wrapper |
| 3 | instrn_engine_wrapper_dfx: gate ai_clk during TRISC stall, resume | TRISC PC preserved on resume | DFX wrapper |
| 4 | t6_l1_partition_dfx: gate L1 clock, verify SRAM content on resume | L1 data intact after clock restore | DFX wrapper |
| 5 | Scan chain connectivity: shift scan chain full length (when DFX enabled) | all flops captured correctly | Scan chain |
| 6 | Clock gating glitch check: verify no glitch on gated clock waveform | zero glitches in simulation | ICG cells |

### 14.11 Harvest Verification

| # | Test Scenario | Coverage Goal | Block |
|---|---------------|---------------|-------|
| 1 | ISO_EN[0] assertion: harvest tile (0,0), verify 11 signal groups driven safe | all 11 groups isolated via AND cells | ISO cells |
| 2 | Mesh routing reconfiguration: harvest tile (0,0), verify NoC routes around it | no packets sent to (0,0) | NoC mesh |
| 3 | Reset isolation: reset harvested tile independently, verify neighbor tiles unaffected | no reset glitch propagation | Reset ISO |
| 4 | EDC ring bypass: harvest tile (2,1), verify EDC ring completes without that node | ring completes with N-1 active nodes | EDC bypass |
| 5 | Multi-harvest: harvest 3 tiles simultaneously, verify 9-tile system operation | full functionality on remaining tiles | Harvest |
| 6 | Clock bypass: DFX clock pass-through for harvested composite tile | clock chain unbroken in ring | Clock bypass |
| 7 | PRTN chain bypass: harvested tile skipped in power-up sequence | PRTN completes with skip | PRTN bypass |
| 8 | noc_y_size update: verify NOC_MESH_CONFIG reflects harvested row exclusion | routing table excludes harvested row | mesh_config |

### 14.12 End-to-End System Tests

Beyond block-level tests, the following system-level tests verify cross-block integration:

| # | Test | Blocks Exercised |
|---|------|-----------------|
| 1 | INT16 GEMM (128×48×256): full matrix multiply, L1→FPU→L1, compare golden | FPU + L1 + TDMA + iDMA |
| 2 | All-to-all NoC stress: every tile sends to every other tile simultaneously | NoC + NIU + ATT |
| 3 | Firmware boot: load firmware via iDMA, BRISC executes, verifies EDC/SMN init | iDMA + DM + EDC + SMN |
| 4 | Harvest + compute: harvest 2 tiles, run GEMM on remaining 10 tiles | Harvest + FPU + NoC |
| 5 | Security fence: Tensix attempts out-of-bounds memory access, verify firewall blocks | SMN + NoC + iDMA |
| 6 | ECC scrubbing under load: background L1 ECC scrub while GEMM is running | L1 ECC + FPU |
| 7 | DVFS during compute: change ai_clk frequency mid-GEMM, verify result correctness | AWM + FPU + NoC |
| 8 | Debug while running: set watchpoint on Tensix, halt on trigger, inspect register state | DM + BRISC + TRISC |

---

*End of document. §1–§14 complete.*
