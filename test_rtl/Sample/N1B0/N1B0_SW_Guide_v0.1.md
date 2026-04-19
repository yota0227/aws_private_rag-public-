# Trinity N1B0 — Software Engineer's Guide

## Version Table

| Version | Date       | Author     | Changes                          |
|---------|------------|------------|----------------------------------|
| v0.1    | 2026-03-24 | SW Team    | Initial release — all sections   |

---

## Table of Contents

1. [Overview — Trinity N1B0 Architecture for SW Engineers](#1-overview)
2. [Memory Map and Address Space](#2-memory-map-and-address-space)
3. [RISC-V Cores — Overview and Programming Model](#3-risc-v-cores)
4. [Tensor DMA (TDMA) — Unpack and Pack Engine](#4-tensor-dma-tdma)
5. [FPU and Math Engine](#5-fpu-and-math-engine)
6. [LLK (Low-Latency Kernel) API](#6-llk-api)
7. [iDMA Engine (Overlay)](#7-idma-engine)
8. [NoC and NIU](#8-noc-and-niu)
9. [NOC2AXI and DRAM Access](#9-noc2axi-and-dram-access)
10. [LLM Inference Guide — LLaMA 3.1 8B](#10-llm-inference-guide)
11. [INT8 Guide](#11-int8-guide)
12. [VC Channel Guide](#12-vc-channel-guide)
13. [DRAM Address Access Guide](#13-dram-address-access-guide)
14. [Performance Guide](#14-performance-guide)
15. [Appendix: Quick Reference](#15-appendix-quick-reference)

---

## 1. Overview

### 1.1 Chip Overview — 4×5 Grid and Tile Types

Trinity N1B0 is a 4-column × 5-row mesh NPU chip. The grid is indexed as (X, Y) where X
is the column (0–3, left to right) and Y is the row (0–4, bottom to top in NoC
coordinates). The physical layout is:

```
     X=0              X=1                   X=2                   X=3
Y=4  NOC2AXI_NE_OPT   NOC2AXI_ROUTER_NE    NOC2AXI_ROUTER_NW    NOC2AXI_NW_OPT
Y=3  DISPATCH_E        ROUTER (placeholder) ROUTER (placeholder)  DISPATCH_W
Y=2  TENSIX            TENSIX               TENSIX                TENSIX
Y=1  TENSIX            TENSIX               TENSIX                TENSIX
Y=0  TENSIX            TENSIX               TENSIX                TENSIX
```

**Tile count summary:**
- 16 Tensix compute tiles: X=0–3, Y=0–2 (all four rows Y=0,1,2,3 — see note)
- 2 Dispatch tiles: (X=0,Y=3) and (X=3,Y=3)
- 4 NOC2AXI bridge tiles: X=0–3, Y=4  (DRAM/AXI interface, SI0–SI3)
- 2 Router-only placeholder tiles: (X=1,Y=3) and (X=2,Y=3) — no Tensix logic

> Note: Tensix compute tiles occupy Y=0–3 for X=0 and X=3 (sharing with Dispatch) and
> Y=0–2 for X=1 and X=2. For N1B0, all 16 Tensix tiles at Y=0–3 are compute-capable.
> The N1B0 grid is actually 4 columns × 5 rows = 20 grid positions, with Tensix tiles
> at Y=1–4 (rows 1 through 4) per the N1B0 HDD (EndpointIndex = X*5+Y).

**Correct N1B0 placement (from N1B0_HDD_v0.1, EndpointIndex = X*5+Y):**

```
     X=0    X=1    X=2    X=3
Y=4  NIU    NIUR   NIUR   NIU     ← NOC2AXI (DRAM, SI0–SI3)
Y=3  DISP   RTRP   RTRP   DISP   ← Dispatch / Router placeholder
Y=2  T6     T6     T6     T6     ← Tensix row C
Y=1  T6     T6     T6     T6     ← Tensix row B
Y=0  T6     T6     T6     T6     ← Tensix row A
```

EndpointIndex table (column-major, stride=5):

| (X,Y) | EP | Tile Type             |
|-------|----|-----------------------|
| (0,0) |  0 | TENSIX                |
| (0,1) |  1 | TENSIX                |
| (0,2) |  2 | TENSIX                |
| (0,3) |  3 | DISPATCH_E            |
| (0,4) |  4 | NOC2AXI_NE_OPT (SI0) |
| (1,0) |  5 | TENSIX                |
| (1,1) |  6 | TENSIX                |
| (1,2) |  7 | TENSIX                |
| (1,3) |  8 | ROUTER (placeholder)  |
| (1,4) |  9 | NOC2AXI_ROUTER_NE    |
| (2,0) | 10 | TENSIX                |
| (2,1) | 11 | TENSIX                |
| (2,2) | 12 | TENSIX                |
| (2,3) | 13 | ROUTER (placeholder)  |
| (2,4) | 14 | NOC2AXI_ROUTER_NW    |
| (3,0) | 15 | TENSIX                |
| (3,1) | 16 | TENSIX                |
| (3,2) | 17 | TENSIX                |
| (3,3) | 18 | DISPATCH_W            |
| (3,4) | 19 | NOC2AXI_NW_OPT (SI3) |

### 1.2 Per-Tile Execution Model

Each Tensix tile (Y=0–2, all X) contains four independent compute threads and a separate
overlay CPU:

```
┌─────────────────────────────────────────────────────────────────┐
│  Tensix Tile  (tt_tensix_with_l1)                               │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  4 × T6 Tensix Cores  (ai_clk ≈ 1 GHz)                  │   │
│  │                                                          │   │
│  │  TRISC0 ─── Unpack  (L1 → SRCA/SRCB, TDMA unpackers)    │   │
│  │  TRISC1 ─── Math    (SRCA/SRCB → DEST via FPU/MAC/SFPU) │   │
│  │  TRISC2 ─── Pack    (DEST → L1, TDMA packers)           │   │
│  │  BRISC  ─── DMA     (L1 ↔ DRAM or peer tile via NoC)    │   │
│  │                                                          │   │
│  │  2 × G-Tile FPU  (16 FP Lane columns each)              │   │
│  │  SFPU  (4 DEST rows/cycle, 16 columns)                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  L1 SRAM  768 KB  (16 banks × 3072×128b, ai_clk)               │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Overlay CPU  (8 Rocket RISC-V harts, dm_clk ≈ 500 MHz)│     │
│  │  iDMA engine, L1/L2 cache, SMN, ATT programming        │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                 │
│  NoC Router + NIU  (noc_clk ≈ 1 GHz, 5 VCs)                   │
└─────────────────────────────────────────────────────────────────┘
```

**Thread roles:**

| Thread | Clock   | Role                                              |
|--------|---------|---------------------------------------------------|
| TRISC0 | ai_clk  | Unpacker: drives TDMA unpackers, loads L1→SRCA/SRCB |
| TRISC1 | ai_clk  | Math: issues MOP (MVMUL/DOTPV) and SFPU ops        |
| TRISC2 | ai_clk  | Packer: drives TDMA packers, stores DEST→L1         |
| BRISC  | ai_clk  | DMA: manages NoC reads/writes and iDMA for DRAM     |
| Overlay CPU (8 harts) | dm_clk | Config, kernel dispatch, ATT setup, host I/F |

All four TRISC/BRISC threads run **concurrently**. Synchronization is done exclusively via
hardware semaphores (1-cycle cost). The Overlay CPU is the control plane and must not be
on the hot compute path.

### 1.3 Memory Hierarchy

```
Registers (per T6, zero-latency):
  DEST latch-array  32 KB   (1024×16b rows or 512×32b rows in INT32 mode)
  SRCA latch-array   ~2 KB  (48 rows × 16 cols × 19b)
  SFPU lregs         8×32b  (FP32 only, flip-flop)

Per-tile SRAMs (all ai_clk):
  L1 SRAM          768 KB   (N1B0 trin config: 16 banks × 48 KB each)
  TRISC local mem  3.3–6.6 KB per TRISC (private to each thread)
  TRISC I-cache    2.25–4.5 KB per TRISC

Overlay CPU (dm_clk):
  L1 D-cache        ~L1 backed
  L2 cache          shared, backed by L1

NoC fabric (noc_clk):
  Per-tile VC FIFOs  5 × 64×2048b = ~1.3 MB (N/E/S/W/NIU)

External DRAM (via NOC2AXI):
  4 × 128 MB = 512 MB total (SI0–SI3, AXI 512-bit, ~100 ns latency)
```

### 1.4 Key Design Principles for SW

1. **All tensor compute happens in TRISC/FPU/SFPU on ai_clk.** The Overlay CPU is for
   setup only. Never write inner-loop CSRs from the Overlay CPU — the dm→ai CDC costs
   4–8 cycles per write.

2. **Three-thread pipeline is mandatory for peak throughput.** TRISC0, TRISC1, and TRISC2
   must overlap. Design kernels so unpack time ≈ math time ≈ pack time.

3. **L1 is the critical shared resource.** All four T6 cores share one 768 KB L1. Bank
   conflicts stall unpacking. Stagger weight and activation base addresses by ≥128 B.

4. **K_tile = 48 is a hard hardware limit.** SRCA holds at most 48 rows. Every GEMM
   kernel must loop over K in steps of 48.

5. **NoC is point-to-point, not shared bus.** Each tile has an independent NIU. Latency
   is deterministic (hop count × flit time). Use VC separation to prevent head-of-line
   blocking between traffic classes.

6. **iDMA (Overlay) and TDMA (Tensix) are separate engines.** Use iDMA for bulk DRAM
   prefetch and inter-tile data movement. Use TDMA only for tensor pack/unpack tightly
   coupled to FPU.

---

## 2. Memory Map and Address Space

### 2.1 Tile-Local Address Map

The following map applies to every Tensix tile (as seen from TRISC/BRISC firmware):

```
Address Range               Size     Description
─────────────────────────────────────────────────────────────────────
0x0000_0000 – 0x000B_FFFF   768 KB   L1 SRAM (tile-local)
0x0080_0000 – 0x017F_FFFF   ~16 MB   LOCAL_TENSIX registers
0x0180_0000 – 0x01FF_FFFF   ~8 MB    TENSIX registers (CFG, THCON)
0x0200_0000 – 0x02FF_FFFF   ~16 MB   NOC registers (ATT, NIU config)
  0x0201_0000               12 KB    ATT base (size 0x3000)
0x0300_0000 – 0x03FF_FFFF   ~16 MB   OVERLAY registers
  0x0300_0000               0x1E4    CLUSTER_CTRL (reset vectors, scratch, clock gating)
  0x0300_0200               0x16C    T6_L1_CSR
  0x0300_3000               0x1000   LLK tile counters (4 interfaces × 16 counters)
  0x0300_4000               0x5D78   ROCC accel registers
  0x0301_0000               0x9050   SMN registers
  0x0302_0000               0xB0C    AWM registers
  0x0300_A000               0x104    Debug module
0x0380_0000 – 0x06FF_FFFF           T6 L1 slave (APB access to L1 from overlay)
0x0400_0000 – 0x0BFF_FFFF           LOCAL_OVERLAY registers
  0x0401_0000               0x348    Cache controller
```

### 2.2 System Memory Map — DRAM Regions (SI0–SI3)

The four NOC2AXI tiles at Y=4 each provide access to one 128 MB DRAM bank:

```
SI0: 0x6000_0000 – 0x67FF_FFFF   128 MB   NOC2AXI at (X=0, Y=4)
SI1: 0x6800_0000 – 0x6FFF_FFFF   128 MB   NOC2AXI at (X=1, Y=4)
SI2: 0x7000_0000 – 0x77FF_FFFF   128 MB   NOC2AXI at (X=2, Y=4)
SI3: 0x7800_0000 – 0x7FFF_FFFF   128 MB   NOC2AXI at (X=3, Y=4)
```

To access SI0 from a Tensix tile, address a NoC packet to (X=0, Y=4) with the local
byte address set to `physical_dram_addr - 0x6000_0000`.

### 2.3 Register Region Map — Overlay, Tensix, NOC

**Overlay / Cluster Control (base 0x0300_0000):**

| Offset  | Size   | Register Block         | Key Fields                        |
|---------|--------|------------------------|-----------------------------------|
| 0x000   | 0x040  | RESET_VECTOR_0..7      | Hart reset vectors [57:0]         |
| 0x040   | 0x07C  | SCRATCH_0..31          | General-purpose 32-bit scratch    |
| 0x0CC   | 0x004  | CLOCK_GATING           | Per-unit clock gate enables       |
| 0x0D0   | 0x004  | CLOCK_GATING_HYST      | Hysteresis count [6:0]            |
| 0x0D8   | 0x040  | WB_PC_REG_C0..7        | Per-hart writeback PC (RO)        |

**LLK Tile Counters (base 0x0300_3000):**

4 interfaces × 16 counters. Interface stride = 0x400, counter stride = 0x40.

Per-counter registers at `base + iface*0x400 + counter*0x40`:

| Offset | Register         | Description                          |
|--------|------------------|--------------------------------------|
| +0x04  | RESET            | Write 1 to reset counter             |
| +0x08  | POSTED           | Tiles posted (producer writes)       |
| +0x0C  | ACKED            | Tiles acked (consumer writes)        |
| +0x10  | BUFFER_CAPACITY  | Maximum tiles in circular buffer     |
| +0x14  | READ_POSTED      | Read current posted count            |
| +0x18  | READ_ACKED       | Read current acked count             |
| +0x1C  | ERROR_STATUS     | Error flag                           |
| +0x38  | TILES_AVAIL_THRESHOLD | Consumer IRQ threshold          |
| +0x3C  | TILES_FREE_THRESHOLD  | Producer IRQ threshold          |

### 2.4 NoC Address Encoding for Remote Tiles

To address a remote tile via the NoC, the 96-bit NoC header address field encodes:

```
Bits [95:88]  : reserved (set to 0)
Bits [87:82]  : broadcast_start_y (6-bit, for broadcast packets)
Bits [81:76]  : broadcast_start_x (6-bit, for broadcast packets)
Bits [75:70]  : y_coord (6-bit, destination tile Y)
Bits [69:64]  : x_coord (6-bit, destination tile X)
Bits [63:0]   : local byte address at destination tile
```

For unicast, set broadcast fields to 0. For broadcast, set start_x/start_y to the
upper-left corner of the rectangle; the NoC router delivers to all tiles in the
rectangle defined by (start_x..x_coord, start_y..y_coord).

**Example: addressing L1 at offset 0x1000 in tile (X=2, Y=1):**
```c
uint64_t noc_addr_lo = 0x0000_0000_0000_1000ULL;  // local address
uint32_t noc_addr_hi = (1 << 6) | (2 << 0);       // y=1 [11:6], x=2 [5:0]
```

### 2.5 DRAM Access via NOC2AXI

Each NOC2AXI tile accepts NoC flit packets and converts them to AXI4 bursts to external
DRAM. The AXI data bus is 512 bits (64 bytes per beat). The AXI address uses a 56-bit
gasket format derived from the NoC 64-bit address field.

**56-bit AXI gasket address layout (from router_decode_HDD_v0.5):**
```
Bits [55:52]  : 4-bit reserved (set 0)
Bits [51:48]  : command/flit_type encoding
Bits [47:0]   : 48-bit physical DRAM byte address
```

In practice, SW constructs the NoC packet with the full 64-bit DRAM physical address in
the lower 48 bits of the addr field. The NOC2AXI gasket strips the upper fields and
issues the AXI transaction to the DRAM controller.

---

## 3. RISC-V Cores — Overview and Programming Model

### 3.1 Core Types

| Core     | ISA     | Clock   | Count/tile | Role                              |
|----------|---------|---------|------------|-----------------------------------|
| TRISC0   | RV32IM  | ai_clk  | 4 (one per T6) | Unpack — drives TDMA unpackers |
| TRISC1   | RV32IM  | ai_clk  | 4          | Math — issues MOP/SFPU instructions |
| TRISC2   | RV32IM  | ai_clk  | 4          | Pack — drives TDMA packers      |
| BRISC    | RV32IM  | ai_clk  | 4          | DMA — manages NoC and iDMA      |
| Overlay CPU | RV64GC | dm_clk | 8 harts   | Control plane, iDMA, dispatch   |

TRISC0/1/2 and BRISC are lightweight RISC-V processors implementing a custom subset
(RV32IM, no floating-point hardware — FP is done in the FPU, not in the RISC-V core).
The Overlay CPU is a full RV64GC Rocket core with FPU, MMU, and ROCC interface.

### 3.2 TRISC Thread Roles

**TRISC0 — Unpacker:**
- Configures THCON UNPACKER0 and UNPACKER1 registers
- Calls `UNPACR` (Unpack Row) instructions to load L1 data into SRCA and SRCB
- Handles format conversion on the fly (e.g., INT8 in L1 → FP16 in SRCA)
- Signals TRISC1 via semaphore when SRCA/SRCB is ready
- Inner loop: for each K_tile, unpack weight slice and activation slice

**TRISC1 — Math:**
- Configures ALU CSRs (ALU_FORMAT_SPEC_REG, ALU_ACC_CTRL, MOP_CFG)
- Issues MOP (`DOTPV`, `MVMUL`) to trigger the FPU MAC array
- Issues SFPU instructions for element-wise activation functions
- Manages DEST double-buffer: writes to buffer A while TRISC2 drains buffer B
- Signals TRISC2 via semaphore when a DEST half-buffer is full

**TRISC2 — Packer:**
- Configures THCON PACKER0 and PACKER1 registers
- Calls `PACR` (Pack Row) instructions to drain DEST → L1
- Applies descale (INT_DESCALE) for INT16/INT8 accumulator outputs
- Applies ReLU, edge masking, stochastic rounding in hardware
- Signals TRISC0 via semaphore when L1 output buffer has room

**BRISC — DMA:**
- Runs entirely independently of TRISC0/1/2
- Issues NoC read/write commands via CSR writes to the NIU
- Initiates DRAM prefetch for next tile's weights while current tile computes
- Signals TRISC0 via semaphore when L1 weight buffer is filled

### 3.3 BRISC Data Movement Role

BRISC manages all data movement between tiles and between L1 and DRAM. It communicates
with TRISC threads only through semaphores and shared L1 mailbox locations.

```c
// Typical BRISC main loop for pipeline-parallel inference:
void brisc_main(void) {
    uint32_t tile_id;
    while (1) {
        // Read next tile descriptor from overlay mailbox
        tile_desc_t *desc = read_mailbox(L1_BRISC_MAILBOX);

        // Prefetch next weight block from DRAM to L1 double-buffer B
        noc_dma_load(desc->weight_dram_addr, L1_WEIGHT_BUF_B, desc->weight_bytes);

        // Wait for TRISC2 to finish consuming weight buffer A
        sem_wait(SEM_WEIGHT_BUF_A_FREE);

        // Swap buffers
        swap(&L1_WEIGHT_BUF_A, &L1_WEIGHT_BUF_B);

        // Signal TRISC0 that new weights are in buffer A
        sem_post(SEM_WEIGHT_BUF_A_READY);
    }
}
```

### 3.4 Overlay CPU Role

The Overlay CPU (8 Rocket harts, RV64GC, dm_clk ≈ 500 MHz) is the configuration and
dispatch controller. Its typical responsibilities:

1. **Boot sequence:** Load TRISC/BRISC binaries into L1 via iDMA. Set reset vectors.
   Release hart resets in order.
2. **ATT programming:** Write tile coordinate-to-NoC address mappings into the ATT
   before any NoC traffic starts.
3. **Kernel dispatch:** Write tile descriptors (tensor shapes, L1 addresses, loop counts)
   to L1 mailbox regions readable by BRISC.
4. **SMN configuration:** Set security fence ranges to protect tile address regions.
5. **Completion monitoring:** Poll LLK counter registers or wait for IRQs to know when
   a kernel phase completes.

**CDC penalty:** Every write from the Overlay CPU to the Tensix register space crosses
a dm_clk → ai_clk CDC FIFO (depth 8). Cost: 4–8 ai_clk cycles per write. Do not place
Overlay CPU writes on the compute hot path.

### 3.5 Register Map per Core Type

**TRISC instruction set (CSR-mapped):**
TRISC threads write to FPU/TDMA configuration through `wrcfg` (write config register)
custom instructions. The config registers live in the LOCAL_TENSIX space:

```
0x01800000 + offset  ← TENSIX CFG registers (THCON, ALU, MOP, ADDR_MOD)
```

Key TRISC CSRs are not standard RISC-V CSRs — they are memory-mapped and accessed via
load/store instructions in the TRISC custom ABI.

**Overlay CPU standard RISC-V CSRs:**

| CSR     | Addr  | Description                    |
|---------|-------|--------------------------------|
| mstatus | 0x300 | Machine status (MIE, MPIE)     |
| mie     | 0x304 | Interrupt enable (MSIE/MTIE/MEIE) |
| mtvec   | 0x305 | Trap vector base address       |
| mepc    | 0x341 | Exception program counter      |
| mcause  | 0x342 | Trap cause                     |
| mhartid | 0xF14 | Hart ID (0–7 within tile)      |
| mcycle  | 0xB00 | Cycle counter [31:0]           |
| mcycleh | 0xB80 | Cycle counter [63:32]          |

### 3.6 Semaphore System

Hardware semaphores are the **only** supported synchronization mechanism between TRISC
threads. Software mutexes and spinlocks on L1 are not supported in the TRISC programming
model.

Each semaphore is a small hardware counter. `sem_post` increments; `sem_wait` decrements
(blocking if count is 0). Both operations are single-cycle.

**Semaphore map (canonical kernel assignment):**

| Semaphore ID | Symbol                  | Direction         | Semantics                        |
|-------------|-------------------------|-------------------|----------------------------------|
| 1           | SEM_MATH                | TRISC1 ↔ TRISC1   | Math internal sync               |
| 2           | SEM_PERF                | Any               | Performance measurement gate     |
| 4           | SEM_UNPACK_TO_DEST_UNPACK | TRISC0 → TRISC1 | SRCA ready for math              |
| 5           | SEM_STREAM              | TRISC0 unpack sync | Unpack stream control           |
| 6           | SEM_PACK_STREAM         | TRISC2 → BRISC    | Pack output ready for DMA        |
| 7           | SEM_UNPACK_TO_DEST_PACK | TRISC0 → TRISC2   | DEST buffer ready for packing    |

**Initialization:** The Overlay CPU must set initial semaphore values in the L1 mailbox
before releasing TRISC resets. If TRISC1 starts before TRISC0 has posted SEM_SRCA_FULL,
TRISC1 will stall permanently.

**Example — canonical 3-stage pipeline:**
```c
// TRISC0 (Unpack)         TRISC1 (Math)            TRISC2 (Pack)
loop {                     loop {                   loop {
  sem_wait(SEM_SRCA_FREE)    sem_wait(SEM_SRCA_FULL)  sem_wait(SEM_DEST_FULL)
  unpack_to_srca(...)        math_mop(...)             pack_to_l1(...)
  sem_post(SEM_SRCA_FULL)    sem_post(SEM_DEST_FULL)  sem_post(SEM_SRCA_FREE)
                             sem_post(SEM_DEST_FREE)  sem_post(SEM_DEST_FREE)
}                          }                        }
```

### 3.7 Mailbox System

The mailbox is a software convention using fixed L1 addresses known to both the Overlay
CPU and BRISC/TRISC firmware. There is no dedicated hardware mailbox; it is simply a
region of L1 SRAM.

**Typical mailbox layout (example, not hardware-fixed):**

```
L1 offset 0x0000  [128 B]  BRISC kernel descriptor (weights addr, tile shape, loop counts)
L1 offset 0x0080  [64 B]   TRISC0 config (THCON values, format codes)
L1 offset 0x00C0  [64 B]   TRISC1 config (ALU format, MOP parameters)
L1 offset 0x0100  [64 B]   TRISC2 config (packer format, descale amount)
L1 offset 0x0140  [32 B]   Semaphore init values (written by Overlay CPU)
L1 offset 0x0160  [32 B]   Status/completion flags (written by BRISC, read by Overlay CPU)
```

The Overlay CPU writes this region via iDMA or direct APB-to-L1 access before releasing
TRISC resets. BRISC reads the descriptor at startup and re-reads on each kernel iteration.

---

## 4. Tensor DMA (TDMA) — Unpack and Pack Engine

### 4.1 Overview

The TDMA is a hardware engine tightly coupled to the FPU datapath inside the Tensix core.
It is **distinct from iDMA** (the Overlay DMA engine). TDMA implements the data path
between L1 SRAM and the FPU register files (SRCA, SRCB for input; DEST for output).

```
L1 SRAM
   │                     ┌──────────────────────────┐
   ├──[Unpacker 0]───────►│  SRCA (48×16×19b)        │
   │   format convert     │  Weight input            │
   ├──[Unpacker 1]───────►│  SRCB (48×16×19b)        │
   │   format convert     │  Activation input        │
   │                      └──────────┬───────────────┘
   │                                 │ FPU MAC array
   │                      ┌──────────▼───────────────┐
   │                      │  DEST  (1024×16×16b or   │
   │◄─[Packer 0]──────────│         512×16×32b)       │
   │   format convert     │  Accumulator output      │
   └──[Packer 1]──────────┘                          │
       format convert                                │
```

**Key TDMA features:**
- 2 unpackers (UNPACKER0 for weights → SRCA, UNPACKER1 for activations → SRCB)
- 2 packers (PACKER0 for primary output, PACKER1 for secondary)
- Inline format conversion on all paths (14 formats supported)
- Zero-mask skipping (zmask): skip zero-valued tiles without loading them
- Exponent-based sparsity: skip tiles whose exponent is below a threshold
- Edge masking (EDGE_MASK0–3): mask partial tiles at tensor boundaries
- Tilize and untilize: convert between row-major and tile-major layout
- L1 accumulation in packer: add DEST output into existing L1 partial sum

### 4.2 Unpacker — From L1 to SRCA/SRCB

The unpacker reads a tile (K_tile rows × N_tile columns of weights, or M_tile rows ×
K_tile columns of activations) from L1, converts the element format, and fills the
target register file.

**Unpacker pipeline stages:**
1. Address generation (`tt_tdma_xy_address_controller`): computes L1 byte address from
   tile base, row stride, and current row/column index.
2. L1 fetch: reads 128-bit words from L1 banks.
3. Word assembly (`tt_unpacker_word_assembler`): packs or unpacks elements from the
   128-bit L1 word to match the source element width.
4. Format conversion (`tt_unpacker_gasket_fmt_conv`): converts elements from the source
   format (e.g., INT8 from L1) to the destination format (e.g., FP16 for SRCA).
5. SRCA/SRCB write: deposits converted elements into the latch-array register file.

**Throughput:** 1 L1 word (128 bits) per cycle. At INT16 (16b/element), that is 8
elements per cycle. Filling SRCA (48 rows × 16 columns = 768 elements) takes 96 cycles.

### 4.3 Packer — From DEST to L1

The packer reads rows from the DEST register file, applies transformations, and writes
to L1.

**Packer pipeline stages:**
1. DEST read (`tt_dstac_to_mem`): reads a row (16 elements × 32b or 16b) from DEST.
2. Integer descale: arithmetic right-shift for INT32 accumulator output (INT_DESCALE).
3. Format conversion: converts to the output format (e.g., INT32 → INT8 for L1 storage).
4. Misc ops (`tt_packer_gasket_misc_ops`): applies ReLU, stochastic rounding,
   exponent threshold pruning, edge masking.
5. L1 write or L1 accumulate: writes packed data to L1, or adds to existing L1 partial sum.

**Throughput:** 1 DEST row per cycle (16 elements). Draining full DEST (1024 rows) takes
1024 cycles in FP16 mode; 512 rows in INT32 mode takes 512 cycles.

### 4.4 THCON Configuration Registers

THCON (Thread Configuration) registers are written by TRISC0 (unpacker config) and
TRISC2 (packer config) before issuing UNPACR/PACR instructions.

**UNPACKER0 REG0:**

| Bits    | Field           | Description                                      |
|---------|-----------------|--------------------------------------------------|
| [3:0]   | out_data_format | Output format into SRCA (see §4.6 format codes)  |
| [7:4]   | in_data_format  | Input format from L1                             |
| [15:8]  | tilize_mode     | 0=tile-major, 1=untilize (row-major output)      |
| [19:16] | transpose       | Enable matrix transpose during unpack            |

**UNPACKER0 REG1:**

| Bits    | Field       | Description                      |
|---------|-------------|----------------------------------|
| [31:0]  | src_z_stride | Z-plane stride (3D tensors)     |
| [15:0]  | y_stride    | Row stride in elements           |

**PACKER0 REG0:**

| Bits    | Field            | Description                                       |
|---------|------------------|---------------------------------------------------|
| [3:0]   | out_data_format  | Output format to L1                               |
| [7:4]   | in_data_format   | DEST element format                               |
| [8]     | l1_acc           | 1 = enable L1 accumulate (add to existing value)  |
| [9]     | zero_write       | 1 = write zeros (INIT/zero-fill path)             |
| [10]    | stoch_rnd_en     | 1 = enable stochastic rounding on output          |
| [15:12] | relu_mode        | 0=none, 1=zero-neg, 2=compare, 3=clamp           |
| [24:16] | exp_threshold    | Sparsity exponent threshold                       |
| [25]    | exp_threshold_en | 1 = enable exponent-threshold pruning             |

**PACKER0 REG1:**

| Bits    | Field       | Description                      |
|---------|-------------|----------------------------------|
| [31:0]  | edge_mask0..3 | Per-element edge masking bits  |

### 4.5 Address Modifier (ADDR_MOD) Configuration

The address modifier controls how the L1 source address advances after each UNPACR or
PACR instruction. There are 8 address modifier slots (ADDR_MOD_0..7), selected per
UNPACR/PACR issue.

```c
// Example: configure ADDR_MOD_0 for K-loop inner step (advance by one K_tile row)
wrcfg(ADDR_MOD_0_SRC, {
    .src_y_incr  = K_TILE * ELEM_BYTES,  // advance Y address by K_tile elements
    .src_z_incr  = 0,                    // no Z advance (2D tile)
});
wrcfg(ADDR_MOD_0_DST, {
    .dst_y_incr  = 0,                    // DEST address does not advance per UNPACR
});
```

Typical kernel uses 2–3 address modifier slots:
- Slot 0: inner K_tile loop step (advance source by K_tile rows)
- Slot 1: outer M_tile loop step (reset source to new activation row)
- Slot 2: N-column advance for weight tiles

### 4.6 Format Conversion Table (14 Formats)

| Code | Format       | Bits/element | Description                              |
|------|--------------|-------------|-------------------------------------------|
| 0x0  | FLOAT32      | 32          | IEEE 754 single precision                 |
| 0x1  | FLOAT16      | 16          | IEEE 754 half precision (E5M10)           |
| 0x2  | FLOAT16_B    | 16          | BFloat16 (E8M7)                           |
| 0x3  | TF32         | 19          | TensorFloat32 (E8M10, 19-bit internal)    |
| 0x4  | FP8E4M3      | 8           | 8-bit float, E4M3                         |
| 0x5  | FP8E5M2      | 8           | 8-bit float, E5M2                         |
| 0x6  | INT8         | 8           | Signed 8-bit integer                      |
| 0x7  | INT16        | 16          | Signed 16-bit integer                     |
| 0x8  | INT32        | 32          | Signed 32-bit integer (accumulator)       |
| 0x9  | UINT8        | 8           | Unsigned 8-bit integer                    |
| 0xA  | MXFP8R       | 8           | Microscaling FP8 (block-float, E4M3)      |
| 0xB  | MXFP8C       | 8           | Microscaling FP8 (E5M2)                   |
| 0xC  | MXFP4        | 4           | Microscaling FP4                          |
| 0xF  | RAW16        | 16          | Raw 16-bit (no format conversion)         |

Format conversion rules:
- Widening (e.g., INT8 → FP16): always supported in unpacker; zero-extend or sign-extend.
- Narrowing (e.g., FP32 → INT8): supported in packer with optional stochastic rounding.
- Mixed-precision GEMM: weights in INT8 (code 0x6), activations in INT16 (code 0x7),
  accumulator in INT32 (code 0x8) — set DEST to INT32 mode via ALU_ACC_CTRL.

### 4.7 Tilize and Untilize

TDMA supports hardware tilize (row-major L1 → tile-major SRCA) and untilize (tile-major
DEST → row-major L1).

- **Tilize** (unpacker): set `tilize_mode=1` in UNPACKER0 REG0. The unpacker reads
  consecutive elements along the row dimension and fills SRCA columns in tile order.
  Use this when activations arrive from DRAM in row-major order.
- **Untilize** (packer): set `untilize_mode=1` in PACKER0 REG0. The packer reorders
  DEST output from tile-major to row-major for writing to L1.
  Use this when output must be forwarded to the next layer as row-major.

Tilize/untilize have no throughput penalty — they happen inside the TDMA pipeline.

### 4.8 Zero-Skip (zmask), Sparsity, Edge Masking

**zmask (zero-mask):** A 16-bit bitmask supplied per UNPACR instruction, one bit per
tile column. If a bit is 0, the corresponding tile column is skipped entirely (no L1
read, no SRCA write). Use for structured sparsity (e.g., pruned weight rows).

**Exponent threshold:** PACKER0 REG0 field `exp_threshold` (9-bit). If the exponent of
an output element is below this threshold, the element is forced to zero before writing
to L1. Enables hardware BFP (block floating point) zero pruning. Enable by setting
`exp_threshold_en=1`.

**Edge masking:** PACKER0 REG1 fields `edge_mask0..3` provide per-element write-enable
masks for the four quadrants of a tile. Use for partial tiles at tensor boundaries where
the tensor dimension is not a multiple of the tile size.

### 4.9 L1 Accumulation in Packer

Setting `PACKER0_REG0.l1_acc=1` enables zero-copy in-place accumulation: instead of
overwriting the destination L1 address, the packer adds the DEST output to the existing
L1 value. This implements partial-sum accumulation across K-loop iterations without
allocating a separate DEST buffer per K-chunk.

**When to use L1 accumulate:**
- K is split across multiple tiles that run sequentially (K-parallel split).
- First tile sets `l1_acc=0` (write, not accumulate) to initialize.
- Subsequent tiles set `l1_acc=1` to accumulate.
- Last tile packs with descale and format conversion to produce final output.

### 4.10 Programming Example: Unpack → Math → Pack Flow

```c
// ---------------------------------------------------------------
// TRISC0 kernel: unpack one K_tile of weights and activations
// Assumes: weight at L1_WEIGHT_BASE, activation at L1_ACT_BASE
//          output accumulates in DEST (must be cleared first)
// ---------------------------------------------------------------

void trisc0_unpack_ktile(int k_idx) {
    // Configure unpacker 0 (weights → SRCA): INT16 from L1, FP16 to SRCA
    wrcfg(THCON_UNPACKER0_REG0, {
        .in_data_format  = FMT_INT16,
        .out_data_format = FMT_FP16,
        .tilize_mode     = 0,
    });
    wrcfg(THCON_UNPACKER0_REG1, {
        .y_stride = K_TILE,  // weight matrix K stride
    });

    // Configure unpacker 1 (activations → SRCB): INT16 from L1, FP16 to SRCB
    wrcfg(THCON_UNPACKER1_REG0, {
        .in_data_format  = FMT_INT16,
        .out_data_format = FMT_FP16,
        .tilize_mode     = 0,
    });

    // Wait for TRISC1 to finish using current SRCA
    sem_wait(SEM_SRCA_FREE);

    // Issue UNPACR for weights (K_TILE rows → SRCA)
    uint32_t weight_addr = L1_WEIGHT_BASE + k_idx * K_TILE * N_TILE * sizeof(int16_t);
    issue_unpacr(UNPACKER0, weight_addr, K_TILE, ADDR_MOD_0);

    // Issue UNPACR for activations (M_TILE rows × K_TILE cols → SRCB)
    uint32_t act_addr = L1_ACT_BASE + k_idx * K_TILE * sizeof(int16_t);
    issue_unpacr(UNPACKER1, act_addr, M_TILE, ADDR_MOD_1);

    // Signal TRISC1 that SRCA/SRCB are ready
    sem_post(SEM_SRCA_FULL);
}

// ---------------------------------------------------------------
// TRISC1 kernel: matrix multiply K_tile
// ---------------------------------------------------------------
void trisc1_math_ktile(void) {
    sem_wait(SEM_SRCA_FULL);

    // Set ALU format: INT16 inputs, INT32 accumulator
    wrcfg(ALU_FORMAT_SPEC_REG0, FMT_INT16);
    wrcfg(ALU_ACC_CTRL, {.INT32_mode = 1});

    // Issue MOP: DOTPV over K_TILE rows
    wrcfg(MOP_CFG_LOOP0_LEN, K_TILE - 1);
    wrcfg(MOP_CFG_LOOP1_LEN, M_TILE - 1);
    issue_instrn(MOP, DOTPV);

    sem_post(SEM_SRCA_FREE);
    // Post DEST full only after all K_tiles are done (outside this function)
}

// ---------------------------------------------------------------
// TRISC2 kernel: pack DEST to L1 with INT descale
// ---------------------------------------------------------------
void trisc2_pack(void) {
    sem_wait(SEM_DEST_FULL);

    // Configure packer: INT32 from DEST, INT8 to L1, with descale >>8
    wrcfg(THCON_PACKER0_REG0, {
        .in_data_format   = FMT_INT32,
        .out_data_format  = FMT_INT8,
        .stoch_rnd_en     = 1,
        .relu_mode        = 0,
        .INT_DESCALE_ENABLE = 1,
        .INT_DESCALE_AMOUNT = 8,
    });

    // Issue PACR for M_TILE rows to L1 output buffer
    issue_pacr(PACKER0, L1_OUTPUT_BASE, M_TILE, ADDR_MOD_0);

    sem_post(SEM_DEST_FREE);
}
```

---

## 5. FPU and Math Engine

### 5.1 FPU Architecture

The FPU is organized as two G-Tiles, each containing 16 FP Lane columns. Each FP Lane
column contains one M-Tile and the DEST register bank for that column. The full tile
provides 16 MAC columns simultaneously.

```
tt_fpu_v2 (per T6 core)
├── tt_fpu_gtile [0]  (G-Tile 0)
│   ├── tt_fpu_mtile [0..15]  (16 M-Tiles)
│   │   └── tt_fpu_tile [0]   (per M-Tile)
│   │       └── tt_fp_lane [0..15]  (16 FP Lane columns)
│   │           ├── tt_fp_mul_raw   (Booth multiplier)
│   │           ├── tt_exp_path_v4  (exponent path)
│   │           ├── tt_dual_align   (alignment shifter)
│   │           └── tt_multiop_adder (4:2 compressor tree)
│   └── DEST latch-array [0..511 rows or 0..1023 rows]
└── tt_fpu_gtile [1]  (G-Tile 1, same structure)
```

Each FP Lane processes **MULT_PAIRS=8 products per cycle** (8 Booth multiplier pairs
accumulate per lane per clock). With 16 lanes, one T6 core achieves 128 MACs/cycle.
With 4 T6 cores per tile, the tile achieves **512 MACs/cycle** for FP32/FP16/INT16.
For INT8 (packed 2-per-cell), the effective rate doubles to **1024 MACs/cycle**.

### 5.2 Matrix Multiply (INT16, FP16, FP32)

The FPU computes GEMM via MVMUL (matrix-vector multiply) or DOTPV (dot-product vector)
MOP instructions, controlled by TRISC1.

**MVMUL:** Multiplies the SRCA weight matrix (K_tile rows × N_tile columns) by each row
of SRCB (one M_tile row of activations) and accumulates into DEST.

**DOTPV:** Used for dot-product accumulation when K dimension is the primary loop.

**Format selection via ALU CSRs:**

| ALU_FORMAT_SPEC_REG | ALU_ACC_CTRL         | Meaning                      |
|---------------------|----------------------|------------------------------|
| FMT_FP16 (0x1)      | INT32_mode=0         | FP16 → FP32 accumulation     |
| FMT_FP16_B (0x2)    | INT32_mode=0         | BF16 → FP32 accumulation     |
| FMT_INT16 (0x7)     | INT32_mode=1         | INT16 × INT16 → INT32 accum  |
| FMT_INT8 (0x6)      | INT8_math_enabled=1  | INT8 packed → INT32 accum    |

**MOP configuration (TRISC1):**

```c
// Configure MOP for K-loop over 86 K_tile iterations (K=4096/48)
wrcfg(MOP_CFG_LOOP0_LEN, K_TILES - 1);   // inner loop: K reduction (hardware-accelerated)
wrcfg(MOP_CFG_LOOP1_LEN, M_TILES - 1);   // outer loop: M rows
issue_instrn(MOP, DOTPV);                 // fire — hardware loops automatically
// TRISC1 is now free; MOP runs autonomously. Do not issue second MOP until done.
sem_wait(SEM_MATH_DONE);                  // wait for MOP completion
```

### 5.3 SFPU Operations

The SFPU (Special Function Processing Unit) operates directly on DEST register content
via 8 scalar FP32 local registers (lregs). It supports the following operations:

| SFPU Op       | Description                                 |
|---------------|---------------------------------------------|
| EXP           | e^x (exponential)                           |
| LOG           | ln(x)                                       |
| RSQRT         | 1/sqrt(x)                                   |
| SIGMOID       | 1/(1+e^(-x))                                |
| RELU          | max(0, x)                                   |
| RELU_MAX      | min(max(0, x), threshold)                   |
| GELU_APPROX   | x * Φ(x) approximated via polynomial        |
| SILU          | x * sigmoid(x)                              |
| SOFTMAX       | exp(xi) / sum(exp(xj)) — requires K passes  |
| SQRT          | sqrt(x)                                     |
| RECIP         | 1/x                                         |
| ABS           | |x|                                         |
| LRELU         | max(alpha*x, x)                             |

**SFPU throughput:** 4 DEST rows per cycle, all 16 columns in parallel. Full DEST drain
(1024 rows FP16) completes in 256 cycles = 256 ns at 1 GHz.

**SFPU with INT32 DEST:** SFPU cannot operate directly on INT32 DEST values. For
INT16/INT8 GEMM followed by GELU or SiLU:
1. Pack INT32 DEST to FP16B in L1 (TRISC2, one PACR pass).
2. Reload FP16B from L1 back into DEST via UNPACR.
3. Run SFPU on the FP16B DEST.
4. Pack FP16B result to L1 output.

This costs two extra L1 round-trips (≈96 cycles for full DEST). Consider using FP16B
accumulation (`ALU_ACC_CTRL.INT32_mode=0`) for layers that require SFPU activation.

### 5.4 Math Fidelity Modes

| Mode   | ALU_FORMAT_SPEC | MULT_PAIRS | Throughput | Use Case                      |
|--------|-----------------|------------|------------|-------------------------------|
| LoFi   | FMT_FP16_B      | 4          | 2× slower  | Low-accuracy fast inference   |
| HiFi2  | FMT_FP16        | 4          | standard   | FP16 inference                |
| HiFi3  | FMT_FP16        | 8          | standard   | Higher-quality FP16           |
| HiFi4  | FMT_FP32        | 8          | standard   | FP32 training/fine-tuning     |

**Recommendation for INT16 LLM inference:** use HiFi2 (FMT_FP16, INT32 accumulator).
Provides best throughput with sufficient numeric precision for INT16 weight quantization.

### 5.5 DEST Register File

DEST is a latch-array (not SRAM) providing zero-latency access to the FPU.

```
INT32 / FP32 mode:  512 rows × 16 columns × 32 bits = 32 KB
FP16 / INT16 mode: 1024 rows × 16 columns × 16 bits = 32 KB
```

DEST is logically split into two half-buffers for double-buffering:

| Mode    | Buffer A    | Buffer B     |
|---------|-------------|--------------|
| INT32   | rows 0–255  | rows 256–511 |
| FP16    | rows 0–511  | rows 512–1023|

TRISC1 writes to one half while TRISC2 reads from the other, then they swap.

### 5.6 SRCA / SRCB Register Files

SRCA and SRCB are latch-arrays holding the FPU inputs:

```
SRCA: 48 rows × 16 columns × 19 bits (TF32 internal width)
SRCB: 48 rows × 16 columns × 19 bits
```

These are filled by TDMA unpackers with inline format conversion. The 48-row limit is the
hardware K_tile limit: K_tile = 48 is fixed.

### 5.7 Stochastic Rounding

When narrowing conversions are applied in the packer (e.g., FP32 → INT8), stochastic
rounding can be enabled via `PACKER0_REG0.stoch_rnd_en=1`. The PRNG embedded in the
packer generates a random low-order bias before rounding, reducing systematic quantization
error in fine-tuning workloads.

**Cost:** Zero throughput penalty. The PRNG runs in parallel with the packer pipeline.
**Use case:** Enable for fine-tuning and quantization-aware training. Disable for
inference (deterministic results required for debugging).

### 5.8 Programming Example: INT16 Matmul

```c
// Complete TRISC1 INT16 matmul kernel fragment
// Inputs: SRCA = weights (K_TILE × N_TILE, INT16→FP16 converted by TRISC0)
//         SRCB = activations (M_TILE × K_TILE, INT16→FP16 converted by TRISC0)
// Output: DEST = accumulated INT32 partial sums

void trisc1_int16_gemm(int k_tiles, int m_tiles) {
    // One-time ALU setup (done before entering K-loop)
    wrcfg(ALU_FORMAT_SPEC_REG0, FMT_INT16);
    wrcfg(ALU_ACC_CTRL, ALU_ACC_CTRL_INT32_MODE);  // INT32 accumulator

    // Clear DEST buffer A before starting accumulation
    issue_instrn(ZEROSRC, DEST_A);

    for (int m = 0; m < m_tiles; m++) {
        sem_wait(SEM_SRCA_FULL);   // wait for TRISC0 to load SRCA/SRCB

        // Configure MOP: K_TILE inner loop, 1 M row outer
        wrcfg(MOP_CFG_LOOP0_LEN, k_tiles - 1);
        wrcfg(MOP_CFG_LOOP1_LEN, 0);  // single M row per MOP issue
        issue_instrn(MOP, DOTPV);

        sem_post(SEM_SRCA_FREE);   // TRISC0 can reload SRCA for next M row

        // After all K_tiles done, DEST row m has the full dot product
    }

    // Signal TRISC2 that DEST buffer A is full
    sem_post(SEM_DEST_FULL);
}
```

---

## 6. LLK (Low-Latency Kernel) API

### 6.1 LLK Overview

The LLK (Low-Latency Kernel) API is the standard software interface for writing compute
kernels on Trinity Tensix tiles. LLK provides:

- **Primitive functions** mapping directly to TDMA/FPU hardware operations
- **Circular buffer management** for producer-consumer pipelines
- **Hardware counter interface** for tile-to-tile synchronization (LLK counters)
- **ROCC instruction wrappers** for iDMA and custom accelerator ops

LLK is organized in three namespaces corresponding to the three TRISC threads:

```
llk_unpack_*   → TRISC0 (unpacker)
llk_math_*     → TRISC1 (math)
llk_pack_*     → TRISC2 (packer)
```

### 6.2 llk_unpack_* — Tile Loading Functions

```c
// Initialize unpacker for a given format pair
void llk_unpack_init(uint32_t unpack_src_format,   // format code from L1
                     uint32_t unpack_dst_format,   // format code to SRCA
                     uint32_t transpose);           // 0=normal, 1=transpose

// Unpack one tile of weights from L1 into SRCA
// operand_id: which L1 circular buffer slot
// tile_index: which tile within the buffer
void llk_unpack_A(uint32_t operand_id, uint32_t tile_index);

// Unpack one tile of activations from L1 into SRCB
void llk_unpack_B(uint32_t operand_id, uint32_t tile_index);

// Unpack two tiles simultaneously (SRCA and SRCB in one call)
void llk_unpack_AB(uint32_t operand_id_A, uint32_t tile_index_A,
                   uint32_t operand_id_B, uint32_t tile_index_B);

// Wait for unpack to complete (blocks until TDMA pipeline drains)
void llk_unpack_wait_for_math_done(void);

// Tell LLK counter system that one tile has been consumed from input buffer
void llk_unpack_tile_pop(uint32_t operand_id, uint32_t ntiles);
```

### 6.3 llk_math_* — Compute Functions

```c
// Initialize math engine for given operation and format
void llk_math_eltwise_unary_init(uint32_t sfpu_op);
void llk_math_matmul_init(uint32_t dst_index, uint32_t transpose);

// Matrix multiply: SRCA × SRCB → DEST
// dst_index: which DEST double-buffer slot (0 or 1)
void llk_math_matmul(uint32_t dst_index);

// Element-wise operation using SFPU
void llk_math_eltwise_unary_sfpu_relu(uint32_t dst_index);
void llk_math_eltwise_unary_sfpu_gelu(uint32_t dst_index);
void llk_math_eltwise_unary_sfpu_exp(uint32_t dst_index);
void llk_math_eltwise_unary_sfpu_sigmoid(uint32_t dst_index);

// Wait for all pending MOP and SFPU ops to drain
void llk_math_wait_for_dest_available(void);

// Signal TRISC2 that DEST buffer dst_index is ready to pack
void llk_math_dest_section_done(void);
```

### 6.4 llk_pack_* — Tile Storing Functions

```c
// Initialize packer for given format and destination
void llk_pack_init(uint32_t pack_src_format,   // DEST format
                   uint32_t pack_dst_format,   // output format to L1
                   uint32_t output_operand_id);

// Pack one tile from DEST to L1
void llk_pack(uint32_t tile_index, uint32_t output_operand_id);

// Pack with L1 accumulation (add to existing value in L1)
void llk_pack_l1_acc(uint32_t tile_index, uint32_t output_operand_id);

// Notify that one packed tile is available (increments LLK output counter)
void llk_pack_dest_section_done(void);

// Wait for downstream consumer to have space in output buffer
void llk_pack_wait_for_output_space(uint32_t output_operand_id);
```

### 6.5 LLK Interface Counters

LLK interface counters implement the circular buffer protocol between producer and
consumer. They are memory-mapped at base address `0x0300_3000`.

**Layout:** 4 interfaces × 16 counters per interface.
- Interface stride: 0x400 bytes
- Counter stride: 0x40 bytes
- Counter N of interface I: base address = `0x03003000 + I*0x400 + N*0x40`

**Per-counter registers:**

| Offset | Name              | RW  | Description                          |
|--------|-------------------|-----|--------------------------------------|
| +0x04  | RESET             | WO  | Write 1 to reset counter to 0        |
| +0x08  | POSTED            | RW  | Producer increment (posted tile count)|
| +0x0C  | ACKED             | RW  | Consumer increment (acked tile count) |
| +0x10  | BUFFER_CAPACITY   | RW  | Maximum tiles in circular buffer      |
| +0x14  | READ_POSTED       | RO  | Read current posted value             |
| +0x18  | READ_ACKED        | RO  | Read current acked value              |
| +0x1C  | ERROR_STATUS      | RO  | Overflow/underflow error flag         |
| +0x38  | TILES_AVAIL_THRESHOLD | RW | Consumer IRQ threshold            |
| +0x3C  | TILES_FREE_THRESHOLD  | RW | Producer IRQ threshold            |

**Buffer fullness:** `tiles_available = POSTED - ACKED`. Producer must check
`tiles_available < BUFFER_CAPACITY` before posting. Consumer checks
`tiles_available > 0` before consuming.

### 6.6 ROCC Custom Instructions for LLK

TRISC cores can issue ROCC custom instructions to directly control the iDMA engine
via the CUSTOM_1 opcode (funct7=0x2B):

| Mnemonic | funct3 | Operands          | Description                                  |
|----------|--------|-------------------|----------------------------------------------|
| DMSRC    | 0x0    | rs1               | Set iDMA source address register             |
| DMDST    | 0x1    | rs1               | Set iDMA destination address register        |
| DMCPYI   | 0x2    | rs1, imm          | Immediate copy: transfer imm bytes           |
| DMCPY    | 0x3    | rs1, rs2          | Register copy: transfer rs2 bytes from rs1   |
| DMSTATI  | 0x4    | imm               | Read status of TID=imm (returns count)       |
| DMSTAT   | 0x5    | rs1               | Read status of TID in rs1                    |
| DMSTR    | 0x6    | rs1, rs2          | Set 2D strides: src_stride=rs1, dst_stride=rs2|
| DMREP    | 0x7    | rs1               | Set 2D repetition count (num_reps = rs1)     |

**Example — BRISC issuing a 4 KB DRAM→L1 transfer via ROCC:**

```c
// BRISC DMA from SI0 DRAM (0x60001000) to L1 (0x00010000), 4096 bytes, TID=3
asm volatile (
    "li    t0, 0x60001000       \n"  // source address
    "li    t1, 0x00010000       \n"  // destination address
    "li    t2, 4096             \n"  // length
    "li    t3, 3                \n"  // TID
    ".insn r CUSTOM_1, 0, 0x2B, x0, t0, x0   \n"  // DMSRC t0
    ".insn r CUSTOM_1, 1, 0x2B, x0, t1, x0   \n"  // DMDST t1
    ".insn r CUSTOM_1, 3, 0x2B, x0, t2, t3   \n"  // DMCPY t2, t3
    : : : "t0","t1","t2","t3"
);
// Poll for completion
uint32_t status;
do {
    asm volatile (".insn r CUSTOM_1, 4, 0x2B, %0, x0, x0" : "=r"(status));
} while (status == 0);
```

### 6.7 Circular Buffer Pattern (io_unpack / io_pack)

LLK implements a standard circular buffer pattern for streaming tensor tiles between
tiles (via NoC) or from DRAM (via iDMA):

```
DRAM / remote tile
      │
      │  iDMA or NoC PUT
      ▼
  L1 input circular buffer  (capacity = N_buffers × tile_size)
      │
      │  llk_unpack_A / llk_unpack_B
      ▼
  SRCA / SRCB
      │
      │  MOP DOTPV
      ▼
  DEST
      │
      │  llk_pack
      ▼
  L1 output circular buffer
      │
      │  BRISC NoC PUT or iDMA to DRAM
      ▼
  Remote tile / DRAM
```

**Buffer sizing rule:** Allocate at least 2 slots in both input and output buffers to
allow compute-DMA overlap. Slot size = K_TILE × N_TILE × bytes_per_element (for weight
buffer) or M_TILE × K_TILE × bytes_per_element (for activation buffer).

### 6.8 Synchronization: MOP, Semaphores, dvalid

- **MOP completion:** TRISC1 polls a hardware status bit (`MOP_STATUS.done`) after
  issuing a MOP instruction. LLK wraps this in `llk_math_wait_for_dest_available()`.
  After the wait, DEST contains the final accumulated result.

- **dvalid:** Each SRCA/SRCB row has a valid bit set by the TDMA unpacker and cleared
  by the FPU MAC array. TRISC1 must not issue MOP until dvalid bits are set — LLK
  handles this automatically via the semaphore protocol.

- **Semaphores:** LLK internally uses semaphores 4 and 7 (UNPACK_TO_DEST_UNPACK and
  UNPACK_TO_DEST_PACK). Kernels that add custom synchronization must use a different
  semaphore ID range to avoid conflict.

### 6.9 Full Example: INT16 Matmul Kernel

```c
// ───────────────────────────────────────────────────────
// Complete INT16 matmul LLK kernel
// Weight:     operand 0 (K × N, INT16, pre-loaded in L1)
// Activation: operand 1 (M × K, INT16, filled by BRISC)
// Output:     operand 2 (M × N, INT8, drained by BRISC)
// ───────────────────────────────────────────────────────

// TRISC0 kernel:
void trisc0_kernel(void) {
    llk_unpack_init(FMT_INT16, FMT_FP16, /*transpose=*/0);
    for (int n = 0; n < N_SUBTILE_PASSES; n++) {
        for (int m = 0; m < M_TILES; m++) {
            for (int k = 0; k < K_TILES; k++) {
                // Wait for weight tile to be available
                llk_unpack_tile_wait(/*operand=*/0, /*tiles_needed=*/1);
                llk_unpack_A(/*operand=*/0, /*tile_index=*/k % WEIGHT_BUF_DEPTH);

                // Wait for activation tile
                llk_unpack_tile_wait(/*operand=*/1, /*tiles_needed=*/1);
                llk_unpack_B(/*operand=*/1, /*tile_index=*/k % ACT_BUF_DEPTH);

                llk_unpack_tile_pop(/*operand=*/0, 1);
                llk_unpack_tile_pop(/*operand=*/1, 1);
            }
        }
    }
}

// TRISC1 kernel:
void trisc1_kernel(void) {
    llk_math_matmul_init(/*dst_index=*/0, /*transpose=*/0);
    for (int n = 0; n < N_SUBTILE_PASSES; n++) {
        for (int m = 0; m < M_TILES; m++) {
            llk_math_wait_for_dest_available();
            for (int k = 0; k < K_TILES; k++) {
                llk_math_matmul(/*dst_index=*/0);
            }
            llk_math_dest_section_done();
        }
    }
}

// TRISC2 kernel:
void trisc2_kernel(void) {
    llk_pack_init(FMT_INT32, FMT_INT8, /*output_operand=*/2);
    for (int n = 0; n < N_SUBTILE_PASSES; n++) {
        for (int m = 0; m < M_TILES; m++) {
            llk_pack_wait_for_output_space(/*output_operand=*/2);
            llk_pack(/*tile_index=*/0, /*output_operand=*/2);
            llk_pack_dest_section_done();
        }
    }
}
```

---

## 7. iDMA Engine (Overlay)

### 7.1 Overview

Each Tensix tile contains one `tt_idma_wrapper` instance inside `tt_overlay_wrapper`.
The iDMA engine is the bulk data movement engine for:
- DRAM → L1 weight prefetch (AXI backend via NOC2AXI)
- L1 → Remote tile L1 (NoC PUT via OBI backend)
- L1 → DRAM writeback (AXI backend)
- In-tile L1 → L1 copy (OBI backend)

**iDMA vs TDMA — when to use each:**

| Capability                      | iDMA | TDMA |
|---------------------------------|------|------|
| DRAM AXI access                 | YES  | NO   |
| 24-client arbitration           | YES  | NO   |
| Decoupled read/write            | YES  | NO   |
| 2D scatter-gather               | YES  | NO   |
| Data Format Conversion (bulk)   | YES  | NO   |
| L1 accumulate                   | YES  | YES  |
| Zero-mask skipping (zmask)      | NO   | YES  |
| Tilize/untilize layout          | NO   | YES  |
| FPU-coupled pack/unpack         | NO   | YES  |
| Edge masking                    | NO   | YES  |
| Exponent threshold sparsity     | NO   | YES  |

### 7.2 Descriptor Format (idma_flit_t)

The iDMA descriptor is a struct passed to the iDMA frontend, either via ROCC custom
instruction (CPU harts) or via the Dispatch Engine sideband port.

```
idma_flit_t layout:
  [MSB ─────────────────────────────────────────────────────── LSB]
  | l1_accum_cfg_reg | trid[4:0] | vc[1:0] | payload (idma_req_t) |

idma_req_t fields:
  src_addr[63:0]    — source byte address
  dst_addr[63:0]    — destination byte address
  length[21:0]      — transfer size in bytes (max 4 MB)
  src_stride[63:0]  — outer dimension source stride (2D mode)
  dst_stride[63:0]  — outer dimension destination stride (2D mode)
  num_reps[63:0]    — outer loop count (1 = 1D transfer)
  decouple_rw       — 1 = decouple read and write phases for throughput
  serialize         — 1 = force in-order (use when ordering required)
```

**trid:** 5-bit transaction ID (0–31). Used to track completion via IRQ or polling.

**vc:** 2-bit virtual channel selector. This VC is inserted into the NoC packet header
for inter-tile transfers.

### 7.3 1D and 2D Scatter-Gather

**1D transfer:** Set `num_reps=1`. iDMA copies `length` bytes from `src_addr` to
`dst_addr`.

**2D transfer:** Set `num_reps=N`, `src_stride`, `dst_stride`. iDMA executes N inner
transfers of `length` bytes, advancing source by `src_stride` and destination by
`dst_stride` after each inner transfer. Used for strided matrix access (e.g., loading
one row of a column-major matrix).

```c
// 2D example: load 4 rows of a 4096-element row, stride = full row bytes
idma_req_t req = {
    .src_addr    = dram_weight_base + col * sizeof(int16_t),
    .dst_addr    = l1_weight_buf,
    .length      = N_TILE * sizeof(int16_t),   // 16 elements per inner transfer
    .src_stride  = K * sizeof(int16_t),        // advance by one full row
    .dst_stride  = N_TILE * sizeof(int16_t),   // pack contiguously in L1
    .num_reps    = K_TILE,                     // 48 rows
    .decouple_rw = 1,
};
```

### 7.4 DRAM → L1 Transfer (AXI Backend)

When `IDMA_BE_TYPE_AXI=1` (compile-time), the iDMA backend routes AXI transactions
to the NOC2AXI tile. The iDMA legalizer automatically splits transfers at 4KB page
boundaries to comply with AXI burst rules.

**Programming sequence:**

```c
void idma_load_from_dram(uint64_t dram_addr, uint32_t l1_dst, uint32_t bytes, uint8_t tid) {
    idma_flit_t desc = {
        .trid        = tid,
        .vc          = VC_DRAM_DMA,       // VC0 for weight DMA
        .src_addr    = dram_addr,
        .dst_addr    = l1_dst,
        .length      = bytes,
        .num_reps    = 1,
        .decouple_rw = 1,                 // read ahead of write for max throughput
        .serialize   = 0,
    };

    // Set completion threshold: fire IRQ when 1 transfer with this TID completes
    IDMA_THRESHOLD[tid] = 1;

    // Submit descriptor via ROCC
    submit_idma_flit(&desc);

    // Wait for completion (polling — or use IRQ for overlap)
    while (read32(IDMA_TR_COUNT(tid)) == 0);
    write32(IDMA_CLR, 1 << tid);  // clear counter and IRQ
}
```

### 7.5 L1 → Remote Tile (NoC PUT)

To send data from local L1 to a remote tile's L1, set `dst_addr` to the NoC-formatted
remote address (X/Y coordinates encoded in the upper bits, local L1 offset in lower bits).

```c
void idma_send_to_tile(uint32_t dst_x, uint32_t dst_y,
                       uint32_t local_l1, uint32_t remote_l1,
                       uint32_t bytes, uint8_t tid) {
    // Encode remote address: [y_coord:75:70][x_coord:69:64][local_addr:63:0]
    uint64_t remote_addr = ((uint64_t)dst_y << 70) |
                           ((uint64_t)dst_x << 64) |
                           (uint64_t)remote_l1;
    idma_flit_t desc = {
        .trid     = tid,
        .vc       = VC_ACTIVATION,    // VC1 for activation unicast
        .src_addr = (uint64_t)local_l1,
        .dst_addr = remote_addr,
        .length   = bytes,
        .num_reps = 1,
    };
    submit_idma_flit(&desc);
}
```

### 7.6 Data Format Conversion (DFC) During Transfer

When the iDMA backend has `DFCEnable=1`, the `tt_idma_dfc_wrapper` module performs
in-flight format conversion. Specify source and destination formats in the descriptor's
`l1_accum_cfg_reg` field.

**Supported DFC pairs (common cases):**

| Source Format | Destination Format | Use Case                          |
|---------------|--------------------|-----------------------------------|
| FLOAT32       | FLOAT16_B          | FP32 parameter → BF16 L1 storage  |
| FLOAT32       | FP8E4M3            | FP32 to FP8 compressed storage    |
| INT16         | INT8               | 16-bit activation → 8-bit storage |
| MXFP8R        | FLOAT16            | Decompress MX → FP16              |

Note: iDMA DFC is a bulk memory conversion only. It does not perform arithmetic scaling,
normalization, or sparsity pruning. Use TDMA packer for per-channel descale.

### 7.7 L1 Accumulate Channel

Setting `l1_accum_cfg_reg.enable=1` redirects the iDMA write path to the L1 atomic
accumulate channels (0–15). The transport layer adds the incoming data to the existing
L1 value without a read-modify-write (zero-copy).

**Use case:** Partial-sum reduction across tiles. Each tile sends its partial result to
a designated accumulator tile, which accumulates all inputs in L1. This avoids storing
intermediate partial sums in registers.

### 7.8 Completion Tracking (TID, Threshold, IRQ)

iDMA supports 32 independent transaction IDs (TID 0–31). Each TID has:
- `IDMA_TR_COUNT[TID]`: incremented by 1 per completed transfer
- `IDMA_THRESHOLD[TID]`: when count reaches threshold, IRQ fires
- `IDMA_CLR[TID]`: write 1 to clear count and IRQ atomically

**Polling pattern:**
```c
// After submitting transfer with TID=N:
while (IDMA_TR_COUNT[N] < expected_completions);
IDMA_CLR[N] = 1;
```

**IRQ pattern (for Overlay CPU):**
```c
// In interrupt handler:
void idma_irq_handler(void) {
    uint32_t irq_mask = read_irq_pending();    // o_idma_tiles_to_process_irq
    for (int tid = 0; tid < 32; tid++) {
        if (irq_mask & (1 << tid)) {
            process_completion(tid);
            IDMA_CLR[tid] = 1;                 // clear this TID
        }
    }
}
```

### 7.9 Clock Gating

The iDMA backend (`gated_l1_clk` domain) is clock-gated when idle. Enable clock gating
via the CLOCK_GATING register at offset 0x0CC:

```c
// Enable clock gating for iDMA (saves power, ~10-15% dynamic power reduction)
CLUSTER_CTRL.CLOCK_GATING |= (1 << 1);        // IDMA bit
CLUSTER_CTRL.CLOCK_GATING_HYST = 64;          // stay on for 2^6 = 64 cycles after activity
```

**Warning:** Do NOT enable clock gating during bring-up or debug — premature gating can
cause DMA stalls that are difficult to diagnose.

### 7.10 Programming Example: Full DRAM Prefetch with Double-Buffering

```c
// Double-buffered weight prefetch: while kernel computes on buffer A, DMA fills buffer B
#define L1_WEIGHT_BUF_A  0x00010000   // 48 KB for one weight block
#define L1_WEIGHT_BUF_B  0x0001C000   // 48 KB for next weight block
#define WEIGHT_BLOCK_SZ  (K_TILE * N_SUBTILE * sizeof(int16_t))  // 48×256×2 = 24 KB

void brisc_prefetch_loop(uint64_t weight_dram_base, int n_subtile_passes) {
    uint32_t buf[2] = {L1_WEIGHT_BUF_A, L1_WEIGHT_BUF_B};
    int cur = 0;

    // Prefetch first block into buffer 0
    idma_load_from_dram(weight_dram_base, buf[cur], WEIGHT_BLOCK_SZ, /*tid=*/0);
    idma_wait_tid(0);
    sem_post(SEM_WEIGHT_BUF_READY);

    for (int n = 1; n < n_subtile_passes; n++) {
        int next = 1 - cur;
        // Start prefetch of block n+1 into the alternate buffer
        idma_load_from_dram(weight_dram_base + n * WEIGHT_BLOCK_SZ,
                            buf[next], WEIGHT_BLOCK_SZ, /*tid=*/1);

        // Wait for compute to finish with current buffer
        sem_wait(SEM_WEIGHT_BUF_FREE);

        // Wait for prefetch of next buffer to complete
        idma_wait_tid(1);

        // Signal compute that next buffer is ready
        sem_post(SEM_WEIGHT_BUF_READY);
        cur = next;
    }
}
```

---
## 8. NoC and NIU

### 8.1 NoC Topology

Trinity N1B0 uses a 4×5 2D mesh NoC with Dimension-Order Routing (DOR): X first, then Y.
Every tile has a full-crossbar router connecting its four cardinal directions plus the
local NIU (inject/eject port).

```
     X=0     X=1     X=2     X=3
Y=4  [NIU]──[NIUR]──[NIUR]──[NIU]    ← NOC2AXI (DRAM)
       │       │       │       │
Y=3  [DISP]──[RTR]──[RTR]──[DISP]   ← Dispatch / Router
       │       │       │       │
Y=2  [T6]───[T6]───[T6]───[T6]      ← Tensix row C
       │       │       │       │
Y=1  [T6]───[T6]───[T6]───[T6]      ← Tensix row B
       │       │       │       │
Y=0  [T6]───[T6]───[T6]───[T6]      ← Tensix row A
```

Each link carries 2048-bit flits (256 bytes payload). The head flit contains a 512-bit
header encoding destination coordinates, address, command, VC, and routing mode.

**DOR routing rule:** The router always routes in X direction first (toward target X),
then in Y direction. This guarantees deadlock-free routing for unicast packets.

### 8.2 Virtual Channels (VC0–VC4)

Each router port has 5 independent virtual channels. Flits on different VCs never block
each other within a single physical link, preventing head-of-line blocking between
traffic classes.

**VC definitions and per-tile FIFO sizes:**
- Each Tensix tile VC FIFO: 64 flits × 2048 bits = 16 KB per VC per port direction
- Each Router tile VC FIFO: 256 flits × 2048 bits = 64 KB per VC per port direction

| VC | Canonical Use                              | Notes                              |
|----|--------------------------------------------|------------------------------------|
| 0  | Tensor data — weight DMA, primary payload  | Highest priority; large transfers  |
| 1  | Read responses / completions               | Short messages, return traffic     |
| 2  | Secondary tensor / activation transfer     | Separate from weight to avoid HOL  |
| 3  | Control plane — config, APB, management    | Low bandwidth, low latency         |
| 4  | Dispatch / Broadcast — LLK counter updates | Broadcast-capable                  |

### 8.3 Flit Structure and Packet Types

Every flit is 2083 bits: 2048b payload + 3b flit_type + 32b parity.

**flit_type (3 bits):**

| Value | Type         | Description                                     |
|-------|--------------|-------------------------------------------------|
| 0b000 | HEAD         | First flit; carries 512-bit NoC header          |
| 0b001 | BODY         | Intermediate data flit                          |
| 0b010 | TAIL         | Last flit; signals end of packet                |
| 0b011 | HEAD_TAIL    | Single-flit packet (header + data in one flit)  |
| 0b100 | PATH_SQUASH  | Dynamic routing: carries next-hop override list |

**NoC common header fields (noc_common_hdr_t, first 512 bits of HEAD flit):**

| Field               | Bits | Description                           |
|---------------------|------|---------------------------------------|
| x_coord             | 6    | Destination X coordinate              |
| y_coord             | 6    | Destination Y coordinate              |
| addr[63:0]          | 64   | Local byte address at destination     |
| vc_id               | 3    | Virtual channel selector              |
| cmd_type            | 4    | Read / write / atomic                 |
| cmd_len             | 20   | Payload length in bytes               |
| broadcast           | 1    | 1 = broadcast packet                  |
| broadcast_start_x   | 6    | Broadcast rectangle start X           |
| broadcast_start_y   | 6    | Broadcast rectangle start Y           |
| dynamic_routing_en  | 1    | 1 = use dynamic routing (carried list)|
| force_dim           | 1    | 1 = force_dim_routing mode            |
| security_attr       | 8    | SMN security attribute                |

### 8.4 NIU Inject and Eject

The NIU (Network Interface Unit) is the interface between the tile's internal AXI bus
and the NoC fabric. The NIU has two paths:

- **Inject (AXI2NOC):** Takes AXI write or read transactions from the tile, converts them
  to NoC packets, and injects into the mesh.
- **Eject (NOC2AXI):** Receives NoC packets addressed to this tile, converts to AXI
  transactions, and delivers to the local AXI slave (L1 or DRAM controller).

BRISC firmware does not talk to the NIU directly using AXI protocol. Instead, it writes
to NIU control registers (memory-mapped in the NOC region at `0x0200_0000`) to configure
and submit NoC transactions.

### 8.5 ATT (Address Translation Table)

The ATT translates software virtual addresses to NoC physical coordinates + endpoint IDs.
It lives at `0x0201_0000` (size 12 KB) and has three sub-tables:

**Mask Table (16 entries):** Each entry defines an address range:
```
entry[i].base_addr  — base address of region
entry[i].mask       — bit mask (1 = match this bit)
entry[i].table_idx  — index into endpoint table
```

**Endpoint Table (1024 entries):** Each entry defines the target NoC node:
```
entry[j].x_coord    — destination X
entry[j].y_coord    — destination Y
entry[j].endpoint_id — local endpoint at destination
```

**Dynamic Routing Table (32 entries):** Used when `dynamic_routing_en=1`.

**ATT programming sequence (Overlay CPU):**
```c
// Map virtual address 0x6000_0000–0x63FF_FFFF to NOC2AXI at (0,4)
att_mask_table[0].base_addr = 0x60000000;
att_mask_table[0].mask      = 0xFC000000;  // 64 MB range
att_mask_table[0].table_idx = 0;

att_endpoint_table[0].x_coord    = 0;
att_endpoint_table[0].y_coord    = 4;
att_endpoint_table[0].endpoint_id = 4;     // EndpointIndex for (0,4)
```

### 8.6 Remote L1 Write Pattern

```c
// BRISC: write 4KB tile from local L1 to remote tile (2,1) starting at L1 offset 0x5000
void noc_write_to_tile(void) {
    uint32_t dst_x = 2, dst_y = 1;
    uint32_t src_l1   = 0x00004000;  // local L1 source
    uint32_t dst_l1   = 0x00005000;  // remote L1 destination offset
    uint32_t bytes    = 4096;

    // Write to NIU registers:
    wr32(NOC_TARGET_X,      dst_x);
    wr32(NOC_TARGET_Y,      dst_y);
    wr32(NOC_TARGET_ADDR_LO, dst_l1);
    wr32(NOC_TARGET_ADDR_HI, 0);
    wr32(NOC_RET_ADDR_LO,    src_l1);  // source for read
    wr32(NOC_AT_LEN,         bytes);
    wr32(NOC_CMD_CTRL,       NOC_CMD_WR | (VC_ACTIVATION << 14));
    wr32(NOC_CMD_GO,         1);       // submit

    // Poll for completion
    while (rd32(NOC_CMD_STATUS) & NOC_STATUS_BUSY);
}
```

### 8.7 Broadcast / Multicast

Broadcast sends the same data to all tiles within a rectangular region of the mesh.
Set `broadcast=1` and fill `broadcast_start_x/y` in the header.

```c
// Broadcast weight shard from (0,4) to all tiles in row Y=1 (X=0..3)
wr32(NOC_BRCST_START_X,    3);   // start at X=3
wr32(NOC_BRCST_START_Y,    1);   // same Y row
wr32(NOC_TARGET_X,         0);   // end at X=0
wr32(NOC_TARGET_Y,         1);   // same Y
wr32(NOC_CMD_CTRL,  NOC_CMD_WR | NOC_CMD_BRCST | (VC_BCAST_WEIGHT << 14));
```

All tiles with X in [0..3] and Y=1 receive the packet simultaneously.

### 8.8 VC Channel Selection Guide for SW

| Traffic Type                        | Recommended VC | Rationale                          |
|-------------------------------------|---------------|-------------------------------------|
| DRAM weight DMA (large, bulk)       | VC0           | Highest priority, large FIFO        |
| Read response / ACK                 | VC1           | Separates from request traffic      |
| Activation tile-to-tile             | VC2           | Isolated from weight DMA HOL        |
| Config/CSR writes (Overlay CPU)     | VC3           | Low-bandwidth control traffic       |
| Broadcast weight / all-reduce msg   | VC4           | Broadcast-capable channel           |

**Never share VC between long-latency DRAM traffic and short tile-to-tile messages.**
A single 4 KB DRAM response occupies 16 flits in the VC buffer; a subsequent fast
control message queues behind all 16 flits if sent on the same VC.

### 8.9 NoC Flow Control and Back-Pressure

The NoC uses credit-based flow control. Each VC FIFO has a fixed credit count equal to
its depth (64 flits for Tensix tiles, 256 for Router tiles). A sender can only inject
flits if it has credits for the downstream VC.

**SW implication:** If a tile attempts to inject too many flits before the receiver
drains them, the NIU stalls the BRISC write to the NIU command register. The BRISC
will block at `wr32(NOC_CMD_GO, 1)` until credits are available.

**Practical limit:** Keep individual DMA transfers ≤ 4 KB (16 flits) to stay within
one VC quota and avoid stalling the NIU for extended periods.

---

## 9. NOC2AXI and DRAM Access

### 9.1 NOC2AXI Overview

Four NOC2AXI tiles (Y=4, X=0–3) bridge the NoC mesh to external DRAM via AXI4. Each
tile connects to one DRAM channel (SI0–SI3). The AXI data width is 512 bits (64 bytes
per beat). Maximum in-flight AXI transactions: 64 reads, 32 writes per NOC2AXI tile.

N1B0 uses two composite variants at X=1 and X=2:
- `NOC2AXI_ROUTER_NE_OPT` (X=1, spans Y=4+Y=3): NOC2AXI + router in one physical tile
- `NOC2AXI_ROUTER_NW_OPT` (X=2, spans Y=4+Y=3): same structure, NW corner

The composite tiles have internal cross-row flit wires connecting the Y=4 NOC2AXI logic
to the Y=3 router logic. From SW's perspective, they behave identically to the
corner tiles at X=0 and X=3.

### 9.2 DRAM Address Mapping (SI0–SI3)

| Channel | NoC Target     | Physical Address Range                  |
|---------|----------------|-----------------------------------------|
| SI0     | (X=0, Y=4)     | 0x6000_0000 – 0x67FF_FFFF (128 MB)     |
| SI1     | (X=1, Y=4)     | 0x6800_0000 – 0x6FFF_FFFF (128 MB)     |
| SI2     | (X=2, Y=4)     | 0x7000_0000 – 0x77FF_FFFF (128 MB)     |
| SI3     | (X=3, Y=4)     | 0x7800_0000 – 0x7FFF_FFFF (128 MB)     |

To access DRAM, a Tensix tile sends a NoC packet with destination coordinates
(X=0–3, Y=4) and the local AXI address in the lower 48 bits of the address field.

### 9.3 AXI Burst Programming Guide

AXI4 burst rules enforced by the iDMA legalizer:
- Maximum burst length: 256 beats × 64 bytes = 16 KB per burst
- Burst cannot cross a 4 KB page boundary (legalizer splits automatically)
- Address must be aligned to the AXI data width (64-byte alignment for 512-bit bus)

**Optimal DMA size for DRAM bandwidth:** Use 4 KB or 8 KB transfers. Smaller transfers
(< 512 B) have high overhead from AXI handshake latency. Larger transfers (> 16 KB) are
split by the legalizer into multiple bursts with no SW intervention required.

**AXI RDATA FIFO depth:** The NOC2AXI tile has an internal RDATA FIFO of depth 512
(N1B0 default). This means up to 512 read beats can be in-flight before the FIFO stalls.
At 64 bytes/beat, that is 32 KB in-flight read data buffered at the NOC2AXI tile.

### 9.4 DRAM Performance: Bandwidth and Latency

| Metric                 | Value                      | Notes                              |
|------------------------|----------------------------|------------------------------------|
| AXI bus width          | 512 bits (64 B/beat)       | Per channel                        |
| DRAM frequency         | ~1600 MHz DDR (TBD)        | System-dependent                   |
| Peak read bandwidth    | ~50 GB/s per channel       | 4 channels × ~12.5 GB/s theoretical|
| DRAM read latency      | ~100–150 ns                | First beat; includes NoC hops      |
| NoC hop latency        | ~1–2 ns per hop at 1 GHz  | 5 hops max (diagonal across mesh)  |
| Max outstanding reads  | 64 per NOC2AXI tile        | AXI AR channel depth               |

**Bandwidth utilization tip:** To approach peak bandwidth, issue 4–8 outstanding DMA
requests in parallel (one per TID or two per NOC2AXI channel). Sequential single-request
DMA achieves only ~40% peak due to latency stalls.

### 9.5 Multi-Channel Striping Pattern

To maximize aggregate DRAM bandwidth, distribute tensor data across all four SI channels
(striping). For a weight matrix of size K×N:

```c
// Stripe weight columns across 4 DRAM channels in 64-byte (one AXI beat) units
#define STRIPE_UNIT  64   // bytes per stripe chunk

uint64_t weight_addr_si(int col_byte_offset) {
    int channel    = (col_byte_offset / STRIPE_UNIT) % 4;
    int local_off  = (col_byte_offset / (STRIPE_UNIT * 4)) * STRIPE_UNIT
                   + (col_byte_offset % STRIPE_UNIT);
    uint64_t base[4] = {0x60000000ULL, 0x68000000ULL,
                        0x70000000ULL, 0x78000000ULL};
    return base[channel] + local_off;
}
```

With 4-channel striping, four iDMA engines (one per tile at X=0–3) can each prefetch
from a different SI channel simultaneously, yielding 4× the single-channel bandwidth.

### 9.6 Cache Coherency with DRAM

Trinity N1B0 does not have a coherent hardware cache between the Overlay CPU L2 cache
and DRAM. If the Overlay CPU writes data to its L2 cache (backed by L1 SRAM) and then
a BRISC DMA reads from DRAM at the same physical address, the DMA may see stale data.

**SW rules:**
1. The host must flush data to DRAM before starting any DMA-based transfer.
2. After a BRISC DMA writes to DRAM, any Overlay CPU access to that range must
   invalidate the L2/L1 cache lines first.
3. TRISC firmware running on ai_clk has no cache — L1 accesses are always coherent with
   TDMA and iDMA writes to L1.

### 9.7 Full Example: DRAM Weight Prefetch

```c
// Prefetch one weight block (K_TILE × N_SUBTILE × 2 bytes = 24 KB)
// from SI0 DRAM to L1 using 4KB chunks for maximum pipeline overlap

#define WEIGHT_BLOCK_BYTES  (K_TILE * N_SUBTILE * sizeof(int16_t))
#define CHUNK_SIZE          4096
#define N_CHUNKS            (WEIGHT_BLOCK_BYTES / CHUNK_SIZE)

void prefetch_weight_block(uint64_t dram_src, uint32_t l1_dst) {
    for (int i = 0; i < N_CHUNKS; i++) {
        idma_flit_t desc = {
            .trid        = i,                          // use separate TID per chunk
            .vc          = 0,                          // VC0 for weight DMA
            .src_addr    = dram_src + i * CHUNK_SIZE,
            .dst_addr    = l1_dst  + i * CHUNK_SIZE,
            .length      = CHUNK_SIZE,
            .num_reps    = 1,
            .decouple_rw = 1,
        };
        IDMA_THRESHOLD[i] = 1;
        submit_idma_flit(&desc);
    }

    // Wait for all chunks
    for (int i = 0; i < N_CHUNKS; i++) {
        while (IDMA_TR_COUNT[i] == 0);
        IDMA_CLR[i] = 1;
    }
}
```

---

## 10. LLM Inference Guide — LLaMA 3.1 8B

### 10.1 Model Parameters and Tile Assignment

**LLaMA 3.1 8B key dimensions:**

| Parameter   | Value  | Notes                              |
|-------------|--------|------------------------------------|
| d_model     | 4096   | Hidden dimension                   |
| d_ffn       | 14336  | FFN intermediate dimension         |
| d_k / d_v   | 128    | Per-head attention dimension       |
| n_heads     | 32     | Attention heads                    |
| n_kv_heads  | 8      | KV heads (GQA)                     |
| n_layers    | 32     | Transformer layers                 |
| vocab_size  | 128256 | LM head output dimension           |
| seq_len     | 2048   | Typical inference context          |

**Recommended mapping for 16-tile N1B0 (Hybrid TP+PP):**

```
Y=2 row (X=0..3):  Layer group 0  (layers 0–10,  TP degree=4)
Y=1 row (X=0..3):  Layer group 1  (layers 11–21, TP degree=4)
Y=0 row (X=0..3):  Layer group 2  (layers 22–31, TP degree=4)
```

Each row handles ≈10–11 layers. Within each row, tensor parallelism (TP) splits the
weight N-dimension across the 4 X-column tiles.

**Weight storage per tile (TP degree=4):**
- QKV projection: W_Q [4096×1024] + W_K [4096×256] + W_V [4096×256] = ~11 MB
- FFN gate+up: [4096×3584] × 2 ≈ 50 MB total per layer-group (too large for L1)

**Conclusion:** Weights must be streamed from DRAM per layer. L1 holds one N_subtile
block at a time. BRISC prefetches the next block while TRISC computes on the current block.

### 10.2 INT16 GEMM: Weight × Activation

For a single transformer projection layer (e.g., Q projection, shape [4096×4096]):

**Tiling plan:**

```
Full GEMM:  M×K×N  =  seq × d_model × d_model
              128 × 4096 × 4096

Per tile (TP-split N by 4):
  N_local   = 4096 / 4 = 1024
  K         = 4096
  M         = 128 (all token rows on one tile)

Loop structure:
  N_subtile_passes = N_local / N_subtile = 1024 / 256 = 4
  K_tiles          = ceil(K / K_tile)   = ceil(4096/48) = 86
  M_tiles          = M / M_tile         = 128 / 16 = 8
```

**L1 budget per tile:**
```
Weight block  (K_TILE × N_SUBTILE × 2B): 48 × 256 × 2 = 24 KB  (double-buffered: 48 KB)
Activation    (M × K × 2B):              128 × 4096 × 2 = 1024 KB
Output        (M × N_SUBTILE × 2B):      128 × 256 × 2 = 64 KB
Code + stack:                            ~32 KB
Total:                                   ~1168 KB  → fits in 768 KB with reduced M
```

With M=64 (half batch) or K_TILE streaming, the fit is tighter. Practical recommendation:
use M_tile=16, stream activations from DRAM if M > 32 (activation matrix > 256 KB).

### 10.3 INT8 GEMM: KV-Cache and FFN

For the FFN down projection [14336×4096] in INT8:

```
N_local   = 4096 / 4 = 1024 (TP-split)
K         = 14336
M         = 128

K_tiles   = ceil(14336/48) = 299
N_subtile = 256
N_subtile_passes = 4
M_tiles   = 8
```

INT8 weight storage: 14336×1024×1B = 14.7 MB per tile — exceeds L1. Stream weights
from DRAM in N_subtile blocks of 14336×256×1B = 3.5 MB per pass. Each pass fits in L1
with double-buffering (2 × 3.5 MB chunks → requires streaming; use 1D pass at a time).

Actually with only 768KB L1, fit N_subtile to K_TILE × N_SUBTILE × 1B ≤ 384 KB:
`N_subtile ≤ 384 KB / 48 = 8192` → N_subtile=64 (64 columns per block × 4B L1 word).

Adjust: N_subtile=64 for INT8 FFN down: 48×64×1B = 3 KB per weight block — very small.
Increase to N_subtile=4096 using streaming DRAM: prefetch one full column shard
(48×4096×1B = 192 KB) fitting in L1 alongside activation and output.

### 10.4 KV-Cache Management

KV-cache stores keys and values for previously seen tokens. For LLaMA 3.1 8B:
- K cache: [n_kv_heads × seq × d_k] = [8 × 2048 × 128] × 2B = 4 MB per layer
- V cache: same size = 4 MB per layer
- 32 layers × 8 MB = 256 MB total — stored in DRAM

**Access pattern:** At each new token, each attention head reads K[0..t-1] and V[0..t-1]
from DRAM. This is a sequential read of increasing length — bandwidth grows linearly with
sequence length.

**KV-cache placement:** Stripe across SI0–SI3 with 64-byte granularity. Each head's
K-cache is stored in a separate SI channel to maximize read bandwidth.

```c
// KV-cache address for layer l, head h, token position t, dimension d:
uint64_t kv_addr(int l, int h, int t, int d, bool is_key) {
    uint64_t offset = (uint64_t)l * n_kv_heads * seq_len * d_k * sizeof(float16_t)
                    + (uint64_t)h * seq_len * d_k * sizeof(float16_t)
                    + (uint64_t)t * d_k * sizeof(float16_t)
                    + (uint64_t)d * sizeof(float16_t);
    if (!is_key) offset += total_k_cache_bytes;
    return weight_addr_si(offset);  // striped across SI0-SI3
}
```

### 10.5 Attention Layer: QK^T and AV

Attention computation involves two GEMMs:
1. **QK^T:** [H×seq × d_k] × [H×d_k × seq] → [H×seq × seq] (attention scores)
2. **AV:** [H×seq × seq] × [H×seq × d_k] → [H×seq × d_k] (attended values)

For LLaMA 3.1 8B with seq=2048, d_k=128, H=32:
- QK^T shape: 32×2048×128 × 32×128×2048 — K=128 (fits in K_tile=48×3 passes)
- AV shape: 32×2048×2048 × 32×2048×128 — K=2048 (ceil(2048/48) = 43 K_tiles)

**Tile assignment for QK^T (TP across heads):**
Each X-column handles 8 heads (32/4). Each tile computes [8×2048×128] × [8×128×2048].

**Softmax between QK^T and AV:**
Softmax cannot be computed in-tile if the full seq=2048 row is split across columns.
Options:
1. Compute full QK^T on a single tile (no TP) — 2048×2048×128 matmul fits in ~1 K_tile
   pass with K=128.
2. Use all-reduce after QK^T to gather per-head scores, compute softmax in-tile,
   then proceed to AV.

Recommended: option 1 for short sequences (seq ≤ 512). For seq=2048, use option 2.

### 10.6 FFN Layer: Gate and Up Projections

FFN uses SwiGLU activation: output = (gate_proj × SiLU(x)) ⊙ up_proj

```
gate_proj:  [d_model × d_ffn] = [4096 × 14336]  (TP → each tile: [4096×3584])
up_proj:    [d_model × d_ffn] = [4096 × 14336]  (TP → each tile: [4096×3584])
down_proj:  [d_ffn × d_model] = [14336 × 4096]  (TP → each tile: [3584×4096])
```

**Kernel sequence per tile (gate + up + SiLU + element-wise multiply):**
1. BRISC prefetches gate_proj shard from DRAM into L1 double-buffer.
2. TRISC0/1/2 run INT16 GEMM on gate_proj: output → L1_gate.
3. BRISC prefetches up_proj shard.
4. TRISC0/1/2 run INT16 GEMM on up_proj: output → L1_up.
5. TRISC1 runs SFPU SiLU on L1_gate (after repacking to DEST as FP16).
6. TRISC2 packs element-wise product (L1_gate × L1_up) → L1_ffn_out.
7. BRISC sends L1_ffn_out to accumulation tile for TP all-reduce.
8. After all-reduce, BRISC prefetches down_proj and runs down_proj GEMM.

### 10.7 All-Reduce Across Tiles

After tensor-parallel GEMM, partial outputs from all 4 X-column tiles must be summed
(all-reduce). The standard pattern for 4 tiles in one Y-row:

```
Phase 1 (reduce-scatter):
  Tile X=0: send partial[0] to X=1; X=1 sends partial[1] to X=2; etc.
  Each tile accumulates one quarter of the output.

Phase 2 (all-gather):
  Each tile broadcasts its accumulated quarter to all others.
  All tiles end with the full reduced output.
```

**NoC implementation:**

```c
// Phase 1: send partial output slice to next tile (ring reduce-scatter)
void all_reduce_scatter(uint32_t my_x, uint32_t y, uint32_t l1_partial,
                        uint32_t l1_recv, uint32_t slice_bytes) {
    uint32_t next_x = (my_x + 1) % 4;
    // Send our slice to next tile
    noc_write(next_x, y, l1_partial + my_x * slice_bytes,
              l1_recv, slice_bytes, VC_ALL_REDUCE);
    // Wait to receive from previous tile
    sem_wait(SEM_RECV_DONE);
    // In-place accumulate received data into our partial
    vector_add_int16(l1_partial + my_x * slice_bytes, l1_recv, slice_bytes);
}
```

### 10.8 NoC Traffic Pattern

For one transformer layer at seq=128, TP=4:

| Traffic Type         | Source → Destination | Size per Op   | VC  |
|----------------------|----------------------|---------------|-----|
| Weight prefetch      | DRAM SI → Tensix     | 48 KB/block   | VC0 |
| Activation forward   | Y-row N → Y-row N+1  | 128×4096×2B=1MB | VC2 |
| All-reduce scatter   | X → X+1 (ring)       | 128×1024×2B=256KB | VC4 |
| All-reduce gather    | All X tiles          | 128×4096×2B=1MB broadcast | VC4 |
| KV-cache read        | DRAM SI → Tensix     | 2048×128×2B=512KB | VC0 |

**Key bottleneck:** Activation forward between Y-rows (1 MB per layer boundary) on VC2.
At 2048 bits/flit, 1 MB = 512 flits = 8× the 64-flit Tensix VC FIFO capacity. Issue
in 4 KB chunks to avoid VC stalls.

### 10.9 End-to-End Token Latency Estimate

For a single new token with seq=128, LLaMA 3.1 8B on N1B0 (3 Y-rows, TP=4):

| Phase                     | Cycles (at 1 GHz ai_clk) | Notes                              |
|---------------------------|-------------------------|------------------------------------|
| Weight prefetch (DRAM)    | ~150,000                | 32 layers × ~50 MB / ~50 GB/s      |
| QKV GEMM (INT16)          | ~350,000                | 86 K_tiles × 8 M_tiles × 3 layers |
| Attention QK^T + AV       | ~80,000                 | K=128/48=3 K_tiles, seq-limited    |
| FFN gate+up (INT16)       | ~800,000                | K=299 K_tiles × 8 M_tiles          |
| FFN down (INT16)          | ~400,000                | K=299 K_tiles, N=1024/tile         |
| All-reduce (NoC)          | ~50,000                 | 4× ring, 256 KB per layer          |
| Activation forward (NoC)  | ~30,000                 | 1 MB per Y-row boundary × 2       |
| **Total (estimated)**     | **~1.9 M cycles**       | **~1.9 ms at 1 GHz**              |

These are order-of-magnitude estimates. Actual latency depends on DRAM configuration,
NoC congestion, and pipeline overlap efficiency. With full double-buffering (DMA + compute
overlap), DRAM prefetch hides behind compute, reducing effective latency to ~1.2 ms.

---

## 11. INT8 Guide

### 11.1 INT8 vs INT16 Trade-offs

| Metric               | INT8                  | INT16                 | FP16B (BF16)          |
|----------------------|-----------------------|-----------------------|-----------------------|
| Weight storage       | 1 B/elem              | 2 B/elem              | 2 B/elem              |
| Activation storage   | 1 B/elem              | 2 B/elem              | 2 B/elem              |
| DEST accumulator     | INT32 (32b)           | INT32 (32b)           | FP32 (32b)            |
| MACs/cycle/tile      | 2048 (packed)         | 1024                  | 1024                  |
| DRAM bandwidth req.  | 0.5×                  | 1×                    | 1×                    |
| Quantization error   | High (±0.5 LSB)       | Low (±0.5 LSB × 256)  | Minimal               |
| SFPU input           | Must convert to FP first | Must convert         | Direct                |
| Use case             | FFN down, KV-cache    | QKV, FFN gate/up      | Attention scores, norm|

**Rule:** Use INT8 when:
- DRAM bandwidth is the bottleneck (weight streaming for large N)
- Numeric precision is not critical (FFN, dense layers, post-softmax)

Use INT16 when:
- Precision matters (attention scores, residual additions, normalization)
- Compute is the bottleneck (K is large, DRAM already saturated)

### 11.2 INT8 Quantization and Descale

INT8 quantization: each weight element `w` is stored as `round(w / scale)` where `scale`
is a per-channel or per-tensor scale factor.

After INT8 GEMM, the INT32 accumulator holds the sum of products of quantized values.
To recover the original floating-point output:
```
output[i,j] = (acc[i,j] / (act_scale × weight_scale[j])) + bias[j]
```

**Hardware descale (PACKER0 REG0.INT_DESCALE):** The packer can perform an arithmetic
right shift of the INT32 accumulator before writing to L1:
```
output_int8[i,j] = acc[i,j] >> INT_DESCALE_AMOUNT
```

For per-channel scale factors that vary per output column j, the SFPU must be used to
apply the scale after packing to FP16:

```c
// After INT8 GEMM: DEST contains INT32 partial sums
// Step 1: Pack INT32 → FP16B to L1 (using fixed descale >>8 as first normalization)
wrcfg(PACKER0_REG0, {.in_fmt=INT32, .out_fmt=FP16B, .INT_DESCALE_AMOUNT=8});
issue_pacr(PACKER0, L1_TEMP, M_TILE, ADDR_MOD_0);

// Step 2: Reload FP16B from L1 into SRCA
issue_unpacr(UNPACKER0, L1_TEMP, M_TILE, ADDR_MOD_0);

// Step 3: SFPU per-channel scale using preloaded scale factors in SRCA
// (scale factor vector loaded into SRCB by TRISC0)
issue_instrn(SFPU, SFPU_MUL_LREG);  // multiply DEST × lreg (scale factor)
```

### 11.3 INT8 Matmul Programming

```c
// TRISC1 INT8 matmul: enable packed INT8 mode
void trisc1_int8_gemm(int k_tiles, int m_tiles) {
    // Enable INT8 packed mode: 2 INT8 elements per MAC cell
    wrcfg(ALU_FORMAT_SPEC_REG0, FMT_INT8);
    wrcfg(ALU_ACC_CTRL, ALU_ACC_CTRL_INT32_MODE | ALU_ACC_CTRL_INT8_MATH_EN);

    for (int m = 0; m < m_tiles; m++) {
        sem_wait(SEM_SRCA_FULL);
        wrcfg(MOP_CFG_LOOP0_LEN, k_tiles - 1);
        wrcfg(MOP_CFG_LOOP1_LEN, 0);
        issue_instrn(MOP, DOTPV);
        sem_post(SEM_SRCA_FREE);
    }
    sem_post(SEM_DEST_FULL);
}
```

**Critical:** Always set `ALU_ACC_CTRL.INT8_math_enabled=1` when running INT8. Omitting
this bit halves throughput (the hardware uses single-precision mode instead of packed).

### 11.4 Accumulation in INT32 DEST

INT8 GEMM always accumulates into a 32-bit DEST (INT32 mode, 512 rows). After all K
tiles are accumulated:
- DEST row i contains a 32-bit integer for each of the 16 output columns.
- The dynamic range is ±(128 × 128 × K) = ±(128 × 128 × 4096) ≈ ±67 M, well within INT32.
- Apply `INT_DESCALE_AMOUNT = ceil(log2(K)) - 7` = ceil(log2(4096)) - 7 = 5 to normalize
  back to INT8 range before writing L1.

### 11.5 INT8 DFC in iDMA

iDMA DFC can convert INT16 activations to INT8 in-flight during a tile-to-tile transfer,
saving L1 bandwidth for the receiving tile:

```c
idma_flit_t desc = {
    .trid                  = 0,
    .vc                    = VC_ACTIVATION,
    .src_addr              = local_l1_int16_activation,
    .dst_addr              = remote_l1_int8_buffer,
    .length                = M * K * sizeof(int16_t),  // source size
    .num_reps              = 1,
    .l1_accum_cfg_reg = {
        .enable     = 0,
        .src_format = FMT_INT16,  // source is INT16
        .dst_format = FMT_INT8,   // destination is INT8
    },
};
```

Note: The DFC divides the effective transfer size by 2 (INT16→INT8 = 0.5×). The
`length` field specifies source bytes; the legalizer adjusts destination byte count.

### 11.6 INT8 Performance Numbers

| Operation              | Format  | MACs/cycle/tile | Cycles for 4096×4096×128 GEMM |
|------------------------|---------|-----------------|-------------------------------|
| Dense GEMM             | INT8    | 2048            | ~4.3 M                        |
| Dense GEMM             | INT16   | 1024            | ~8.6 M                        |
| Dense GEMM             | FP16B   | 1024            | ~8.6 M                        |
| SFPU activation (SiLU) | FP16B   | 4 rows/cycle    | ~256 (per 1024-row DEST)      |

For the complete LLaMA 3.1 8B FFN (K=14336, N=4096, M=128) per tile with TP=4
(N_local=1024, K=14336):
- INT8: ceil(14336/48) × 8 M_tiles × ~5 cycles/K_tile = ~12,000 cycles
- INT16: same loop, 2× cycles/K_tile → ~24,000 cycles

---

## 12. VC Channel Guide

### 12.1 VC Definitions and Priorities

The 5 NoC virtual channels are differentiated by buffer depth and priority in the router
arbitration. All VCs have equal physical bandwidth; priority affects only the arbitration
order when multiple VCs have flits ready.

| VC | Priority | Buffer (Tensix) | Buffer (Router) | Primary Traffic Class     |
|----|----------|-----------------|-----------------|---------------------------|
| 0  | Highest  | 64 flits (16KB) | 256 flits (64KB)| Weight DMA, primary data  |
| 1  | High     | 64 flits        | 256 flits       | Read responses / ACKs     |
| 2  | Medium   | 64 flits        | 256 flits       | Activation tile-to-tile   |
| 3  | Low      | 64 flits        | 256 flits       | Control / config          |
| 4  | Low      | 64 flits        | 256 flits       | Broadcast / all-reduce    |

### 12.2 When to Use Which VC

| Use Case                                    | VC | Reasoning                                 |
|---------------------------------------------|----|-------------------------------------------|
| DRAM weight prefetch (DRAM→L1)              | 0  | Largest transfers; highest priority       |
| DRAM read response (data returning from SI) | 1  | Separate response traffic from requests  |
| Layer output forward (tile row N → N+1)     | 2  | Medium; separate from weight traffic      |
| All-reduce message (ring reduce-scatter)    | 4  | Broadcast-capable; low bandwidth          |
| Config write (ATT programming)              | 3  | Low bandwidth, latency-insensitive        |
| KV-cache read (DRAM→L1, growing context)    | 0  | Treat as weight DMA (bulk, bandwidth)     |
| Dispatch descriptor injection               | 3  | Control traffic, infrequent               |

### 12.3 VC for iDMA vs CPU vs Dispatch

**iDMA transfers:** Set `vc` field in `idma_flit_t.vc[1:0]`. The iDMA frontend passes
this VC to the NoC packet header for every flit in the transfer.

```c
idma_flit_t desc = {
    .vc = 0,      // VC0 for weight DMA
    // ... other fields
};
```

**BRISC NoC writes via NIU registers:** Set the VC in the CMD_BRCST register:
```c
// VC field at bits [15:13] of the CMD_BRCST register (check RTL for exact bit position)
wr32(NOC_CMD_BRCST, NOC_CMD_WR | (vc_id << 13));
```

**Overlay CPU via iDMA:** Overlay CPU harts issue iDMA commands via ROCC. The VC is
encoded in the descriptor passed to the ROCC interface:
```c
// BRISC/CPU: set VC in the DMCPY descriptor word
// trid[4:0] at bits [4:0], vc[1:0] at bits [6:5] of the descriptor header word
uint32_t desc_hdr = (TID_CONFIG << 0) | (VC_CONTROL << 5);
```

**Dispatch engine:** The dispatch engine sideband DMA clients (clients 8–9) use the same
idma_flit_t format. Assign VC3 for dispatch operations.

### 12.4 VC Space Monitoring

The iDMA APB register `IDMA_VC_SPACE[0/1]` returns the number of available VC slots
in each backend. Read this before issuing large DMA batches to ensure the VC FIFO has
enough room:

```c
// Check VC space before issuing a new DMA
uint32_t vc_space = read32(IDMA_VC_SPACE_BASE + backend * 4);
if (vc_space < REQUIRED_FLITS) {
    // Wait or yield; VC FIFO is close to full
}
```

A value of 0 means the VC FIFO is full and any new transfer will stall until the
downstream tile drains its receive buffer.

---

## 13. DRAM Address Access Guide

### 13.1 Physical Address Decoding

DRAM physical addresses are distributed across 4 channels (SI0–SI3):

```
Given a DRAM byte address PA:

  channel  = (PA >> 27) & 0x3       // bits [28:27] select channel 0-3
  local_PA = PA & 0x07FFFFFF         // bits [26:0] = offset within 128MB channel

SI0: PA bits [28:27] = 0b00 → channel 0, base 0x60000000
SI1: PA bits [28:27] = 0b01 → channel 1, base 0x68000000
SI2: PA bits [28:27] = 0b10 → channel 2, base 0x70000000
SI3: PA bits [28:27] = 0b11 → channel 3, base 0x78000000
```

This is the contiguous linear layout. For striped allocation, use the
`weight_addr_si()` function from §9.5.

### 13.2 SW Address Construction for NOC2AXI

To construct the NoC address for a DRAM access:

```c
// Given DRAM physical address PA (in SI0–SI3 range):
uint32_t channel  = (PA - 0x60000000) >> 27;
uint32_t local_PA = (PA - (0x60000000 + channel * 0x08000000));

uint32_t noc_target_x = channel;   // X=0..3 matches SI0..SI3
uint32_t noc_target_y = 4;         // Y=4 is the NOC2AXI row

// NoC local address = local_PA (48-bit field, upper bits zero)
uint64_t noc_local_addr = (uint64_t)local_PA;
```

This 3-tuple (noc_target_x, noc_target_y, noc_local_addr) fully specifies the NoC
packet destination for any DRAM access.

### 13.3 ATT-Based DRAM Mapping

For software that uses virtual addresses (runtime managed), configure the ATT to map
a virtual region to a DRAM NOC2AXI endpoint:

```c
// Map virtual region 0xA000_0000 (size 64MB) → SI2 (physical 0x7000_0000)
void att_map_dram_region(void) {
    // ATT Mask Table entry 3: match 0xA000_0000 – 0xA3FF_FFFF
    ATT_MASK_BASE[3] = 0xA0000000;
    ATT_MASK_MASK[3] = 0xFC000000;  // 64MB mask
    ATT_MASK_IDX[3]  = 20;          // endpoint table index 20

    // ATT Endpoint Table entry 20: NOC2AXI at (X=2, Y=4)
    ATT_EP_X[20]    = 2;
    ATT_EP_Y[20]    = 4;
    ATT_EP_ID[20]   = 14;           // EndpointIndex for (2,4)

    // ATT local address offset: virtual - physical delta
    // The router strips the base and uses local_addr[47:0] directly
    ATT_EP_OFFSET[20] = 0x7000_0000 - 0xA000_0000;  // signed offset
}

// After ATT setup, software can use virtual address 0xA0001000 in iDMA descriptors
// and the NoC router will automatically translate to SI2 at physical 0x7000_1000
```

### 13.4 Page Boundary Handling

The iDMA legalizer automatically splits transfers at 4 KB page boundaries. SW does not
need to manually align transfers. However, for maximum efficiency:

- Align tensor base addresses to 64 bytes (one AXI beat) to avoid partial-beat
  transactions at the start and end of each transfer.
- Align transfer sizes to multiples of 64 bytes for the same reason.

```c
// Force 64-byte alignment for L1 DMA buffer
#define L1_ALIGN  64
uint32_t l1_buf = ALIGN_UP(L1_WEIGHT_BASE, L1_ALIGN);
uint32_t len    = ALIGN_UP(weight_bytes, L1_ALIGN);
```

### 13.5 DMA Descriptor for DRAM Access

A complete iDMA descriptor for DRAM-to-L1 transfer with proper alignment:

```c
// Load K_TILE rows × N_SUBTILE columns of INT16 weights from DRAM SI0
void load_weight_block(uint64_t dram_pa, uint32_t l1_dst,
                       int k_tile, int n_subtile, uint8_t tid) {
    uint32_t bytes = k_tile * n_subtile * sizeof(int16_t);  // 48×256×2 = 24KB

    assert((dram_pa & 63) == 0);  // must be 64-byte aligned
    assert((l1_dst  & 63) == 0);

    idma_flit_t desc = {
        .trid        = tid,
        .vc          = 0,            // VC0 for weight DMA
        .src_addr    = dram_pa,      // NOC2AXI will decode to SI channel
        .dst_addr    = l1_dst,       // L1 destination (local address space)
        .length      = bytes,
        .num_reps    = 1,
        .decouple_rw = 1,            // read ahead for max throughput
        .serialize   = 0,
    };
    IDMA_THRESHOLD[tid] = 1;
    submit_idma_flit(&desc);
}
```

### 13.6 Code Examples

**Example 1: Load full weight matrix column-shard from SI0**

```c
// Load W[K=4096, N_local=1024] = 8 MB from SI0 (0x60100000)
// Tile: X=0, L1 has 768 KB — must stream in N_subtile=64 blocks

#define N_SUBTILE  64
#define K          4096
#define N_LOCAL    1024
#define WEIGHT_BASE_DRAM  0x60100000ULL

for (int n = 0; n < N_LOCAL / N_SUBTILE; n++) {  // 16 passes
    uint64_t dram_src = WEIGHT_BASE_DRAM
                      + (uint64_t)n * N_SUBTILE * K * sizeof(int16_t);
    uint32_t l1_dst   = L1_WEIGHT_BUF;
    uint32_t bytes    = K * N_SUBTILE * sizeof(int16_t);  // 512 KB per pass

    // This 512 KB transfer will be split into 128 × 4KB bursts by legalizer
    load_weight_block(dram_src, l1_dst, K, N_SUBTILE, /*tid=*/0);
    idma_wait_tid(0);

    // Now compute GEMM on this shard...
    run_gemm_on_shard(n);
}
```

**Example 2: DRAM write-back of output tile**

```c
// Write M×N_LOCAL INT8 output (128×1024 = 128 KB) back to SI0
void write_output_to_dram(uint32_t l1_src, uint64_t dram_dst,
                          int m, int n_local) {
    uint32_t bytes = m * n_local * sizeof(int8_t);  // 128 KB
    idma_flit_t desc = {
        .trid        = 2,
        .vc          = 1,            // VC1 for write-back (response channel)
        .src_addr    = l1_src,
        .dst_addr    = dram_dst,
        .length      = bytes,
        .num_reps    = 1,
        .decouple_rw = 1,
    };
    IDMA_THRESHOLD[2] = 1;
    submit_idma_flit(&desc);
    idma_wait_tid(2);
}
```

---

## 14. Performance Guide

### 14.1 Compute Throughput (TOPS Estimates)

| Format  | MACs/cycle/tile | Tiles | ai_clk  | TOPS (peak)       |
|---------|-----------------|-------|---------|-------------------|
| FP32    | 512             | 12    | 1 GHz   | 12.3 TFLOPS       |
| FP16    | 1024            | 12    | 1 GHz   | 24.6 TFLOPS       |
| BF16    | 1024            | 12    | 1 GHz   | 24.6 TFLOPS       |
| INT16   | 1024            | 12    | 1 GHz   | 24.6 TOPS         |
| INT8    | 2048            | 12    | 1 GHz   | 49.2 TOPS         |

Note: 12 Tensix tiles (Y=0–2, X=0–3) for N1B0. Tiles at Y=3 are Dispatch tiles.
Peak TOPS assumes 100% MAC utilization, which requires K_tile=48 fully occupied and
no stalls.

**Practical efficiency factors:**
- K_tile=48 boundary waste: ceil(K/48)/K_tiles × K_tile = K_tile overhead per K-loop
  For K=4096: ceil(4096/48)×48 = 4128 vs 4096 → 0.8% overhead (negligible)
- L1 bank conflict reduction: 95% utilization typical
- DMA overlap: with perfect double-buffering, DMA hides behind compute → 95%+ efficiency
- **Practical efficiency: ~70–85% for typical LLM workloads**

### 14.2 Memory Bandwidth Budget

| Resource           | Bandwidth            | Primary Consumer        |
|--------------------|----------------------|-------------------------|
| L1 (per tile)      | 256 B/cycle (16 banks× 16B) | TDMA unpackers + packer |
| L1 TDMA unpacker 0 | 16 B/cycle           | Weight load (SRCA)      |
| L1 TDMA unpacker 1 | 16 B/cycle           | Activation load (SRCB)  |
| L1 TDMA packer     | 16 B/cycle           | Output store (DEST→L1)  |
| NoC per port       | 256 B/cycle (2048 bits) | Tile-to-tile DMA     |
| DRAM per channel   | ~12.5 GB/s           | Weight prefetch         |
| DRAM total (4 ch)  | ~50 GB/s             | All tiles combined      |

**L1 bandwidth bottleneck check (INT16 GEMM):**
- Unpacker 0 (weights): 16 elements/cycle × 2 B = 32 B/cycle
- Unpacker 1 (activations): 32 B/cycle
- Packer (output): 16 B/cycle
- Total L1 read/write: 80 B/cycle per T6 × 4 T6 = 320 B/cycle
- L1 provides 256 B/cycle → marginal; bank staggering is essential

### 14.3 Bottleneck Diagnosis

**Symptom: TRISC1 spending > 50% cycles in sem_wait(SEM_SRCA_FULL)**
- Cause: TRISC0 is slower than TRISC1 (unpack-bound)
- Fix: Check L1 bank conflicts (stagger weight/activation base addresses by 128 B).
  Verify TRISC0 I-cache fits kernel (< 512 instructions).

**Symptom: TRISC2 spending > 50% cycles in sem_wait(SEM_DEST_FULL)**
- Cause: TRISC1 is slower than TRISC2 (compute-bound — good)
- Action: This is the desired steady state. TRISC2 should be slightly slower than TRISC1.

**Symptom: BRISC spending > 50% cycles waiting on CMD_CTRL**
- Cause: NoC VC FIFO full — downstream tile not draining fast enough
- Fix: Reduce transfer size to 4 KB chunks. Increase NoC VC for this traffic class.

**Symptom: Low DRAM bandwidth (< 40% of peak)**
- Cause: Single-request DMA serializing latency
- Fix: Issue 4–8 concurrent iDMA requests per NOC2AXI tile using separate TIDs.

**Profiling tool:** Read `mcycle` CSR at start and end of each kernel phase:
```c
uint64_t t0 = (((uint64_t)read_csr(mcycleh)) << 32) | read_csr(mcycle);
// ... kernel code ...
uint64_t t1 = (((uint64_t)read_csr(mcycleh)) << 32) | read_csr(mcycle);
uint64_t elapsed = t1 - t0;
```

### 14.4 Double-Buffer Pattern (DMA + Compute Overlap)

The canonical pattern for hiding DRAM latency behind compute is double-buffering:

```
Timeline:
  Cycle    0: DMA fills buffer A (from DRAM, ~150 K cycles)
  Cycle 150K: Compute on A | DMA fills buffer B
  Cycle 300K: Compute on B | DMA fills buffer A (next block)
  ...

Steady state: Compute and DMA overlap → effective rate = max(compute, DMA)
```

For this to work:
1. L1 must have room for two weight blocks simultaneously (2 × 24 KB = 48 KB for
   K_TILE=48, N_SUBTILE=256 INT16 — easily fits).
2. BRISC must issue the next DMA immediately after signaling TRISC0, not after waiting.
3. TRISC0 must not start unpacking from a buffer until BRISC has posted completion.

```c
// Correct double-buffer coordination (BRISC side):
int cur = 0;
dma_load(dram + 0*block_sz, l1_buf[cur], block_sz, TID_A);  // fill buffer 0
wait_tid(TID_A);
sem_post(SEM_BUF_READY);          // signal TRISC0: buffer 0 ready

for (int n = 1; n < N_PASSES; n++) {
    int nxt = 1 - cur;
    dma_load(dram + n*block_sz, l1_buf[nxt], block_sz, TID_B);  // prefetch buffer 1
    sem_wait(SEM_BUF_FREE);        // wait for TRISC2 to finish with buffer 0
    wait_tid(TID_B);               // ensure prefetch of buffer 1 is done
    sem_post(SEM_BUF_READY);       // signal TRISC0: buffer 1 ready
    cur = nxt;
}
```

### 14.5 Fidelity Mode Selection

| Fidelity | ALU Config            | Precision | Throughput | Use Case                       |
|----------|-----------------------|-----------|------------|--------------------------------|
| LoFi     | FP16B, MULT_PAIRS=4   | ~3 sig dec| 2× slower  | Draft inference, fast preview  |
| HiFi2    | FP16, MULT_PAIRS=4    | ~3 sig dec| standard   | FP16 inference                 |
| HiFi3    | FP16, MULT_PAIRS=8    | ~4 sig dec| standard   | Quality FP16                   |
| HiFi4    | FP32, MULT_PAIRS=8    | ~7 sig dec| standard   | Training, fine-tuning          |

For INT16/INT8 inference, HiFi2 (`ALU_FORMAT_SPEC=FMT_FP16`, `ALU_ACC_CTRL=INT32_mode`)
is the recommended setting. It provides enough precision for quantized inference while
maximizing throughput.

### 14.6 Format Selection Table

| Layer Type         | Recommended Format | Descale         | Notes                            |
|--------------------|--------------------|-----------------|----------------------------------|
| QKV projection     | INT16 → INT32      | >>8 + FP scale  | Balance of precision/bandwidth   |
| FFN gate/up        | INT16 → INT32      | >>8             | Large N, bandwidth-bound         |
| FFN down           | INT8 → INT32       | >>5             | Largest K, bandwidth critical    |
| Attention scores   | FP16B → FP32       | N/A             | Requires mantissa precision      |
| Softmax            | FP16B (SFPU)       | N/A             | SFPU EXP/RECIP                  |
| RMSNorm scale      | FP16B (SFPU)       | N/A             | Per-channel multiply in SFPU    |
| Residual add       | FP16B              | N/A             | Element-wise add in SFPU        |
| KV cache read      | INT8 → FP16        | via DFC         | Compressed storage, FP compute  |
| LM head            | INT8 → INT32       | >>5             | Very large N=128K, INT8 needed  |

---

## 15. Appendix: Quick Reference

### A. Semaphore Map

| ID | Symbol                  | Direction         | When to Post               | When to Wait               |
|----|-------------------------|-------------------|----------------------------|----------------------------|
| 1  | SEM_MATH                | TRISC1↔TRISC1     | Internal math sync         | Internal math sync         |
| 2  | SEM_PERF                | Any               | Perf measurement start     | Perf measurement end       |
| 4  | SEM_UNPACK_TO_DEST_UNPACK | TRISC0→TRISC1  | SRCA/SRCB filled           | Before issuing MOP         |
| 5  | SEM_STREAM              | TRISC0 internal   | Stream buffer ready        | Stream buffer drain        |
| 6  | SEM_PACK_STREAM         | TRISC2→BRISC      | DEST packed to L1          | BRISC waiting for output   |
| 7  | SEM_UNPACK_TO_DEST_PACK | TRISC0→TRISC2     | DEST ready for packing     | TRISC2 start of pack       |

### B. Address Map Quick Reference

```
0x0000_0000  L1 SRAM base (768 KB)
0x0001_0000  Typical weight buffer A
0x0001_C000  Typical weight buffer B
0x0002_0000  Typical activation buffer
0x000A_0000  Typical output buffer

0x0180_0000  TENSIX CFG base (THCON, ALU, MOP registers)
0x0200_0000  NOC registers base
0x0201_0000  ATT base (size 0x3000)
0x0300_0000  CLUSTER_CTRL base
0x0300_0200  T6_L1_CSR
0x0300_3000  LLK tile counters
0x0300_4000  ROCC accel registers
0x0301_0000  SMN registers
0x0302_0000  AWM registers

0x6000_0000  SI0 DRAM base (128 MB)
0x6800_0000  SI1 DRAM base (128 MB)
0x7000_0000  SI2 DRAM base (128 MB)
0x7800_0000  SI3 DRAM base (128 MB)
```

### C. THCON Register Quick Reference

**Unpacker format registers:**

```
THCON_UNPACKER0_REG0:
  [3:0]   out_data_format   FMT_* code for SRCA output
  [7:4]   in_data_format    FMT_* code for L1 input
  [15:8]  tilize_mode       0=tile-major, 1=row-major
  [19:16] transpose         1=transpose during unpack

THCON_UNPACKER0_REG1:
  [31:0]  src_z_stride      Z-plane stride in bytes
  [15:0]  y_stride          Row stride in elements

THCON_PACKER0_REG0:
  [3:0]   out_data_format   FMT_* code for L1 output
  [7:4]   in_data_format    FMT_* code for DEST input
  [8]     l1_acc            1=L1 accumulate mode
  [9]     zero_write        1=zero-fill mode
  [10]    stoch_rnd_en      1=stochastic rounding
  [15:12] relu_mode         0=none, 1=zero-neg, 2=compare, 3=clamp
  [24:16] exp_threshold     Sparsity pruning exponent
  [25]    exp_threshold_en  1=enable sparsity pruning

THCON_PACKER0_REG1:
  [31:0]  edge_mask0..3     Per-element edge masking
```

**Format code constants:**
```c
#define FMT_FLOAT32    0x0
#define FMT_FLOAT16    0x1   // E5M10 IEEE half
#define FMT_FLOAT16_B  0x2   // BFloat16 E8M7
#define FMT_TF32       0x3   // TensorFloat32
#define FMT_FP8E4M3    0x4
#define FMT_FP8E5M2    0x5
#define FMT_INT8       0x6
#define FMT_INT16      0x7
#define FMT_INT32      0x8
#define FMT_UINT8      0x9
#define FMT_MXFP8R     0xA
#define FMT_MXFP8C     0xB
#define FMT_MXFP4      0xC
#define FMT_RAW16      0xF
```

### D. LLK Function Index

| Function                          | Thread  | Description                        |
|-----------------------------------|---------|------------------------------------|
| llk_unpack_init()                 | TRISC0  | Initialize unpacker format/mode    |
| llk_unpack_A()                    | TRISC0  | Unpack tile from L1 to SRCA        |
| llk_unpack_B()                    | TRISC0  | Unpack tile from L1 to SRCB        |
| llk_unpack_AB()                   | TRISC0  | Unpack both SRCA and SRCB          |
| llk_unpack_wait_for_math_done()   | TRISC0  | Wait for TDMA unpack pipeline      |
| llk_unpack_tile_pop()             | TRISC0  | Acknowledge tile from input buffer |
| llk_math_matmul_init()            | TRISC1  | Initialize matmul format/mode      |
| llk_math_matmul()                 | TRISC1  | Issue DOTPV/MVMUL MOP              |
| llk_math_eltwise_unary_sfpu_*()   | TRISC1  | SFPU element-wise ops              |
| llk_math_wait_for_dest_available()| TRISC1  | Wait for MOP and SFPU completion   |
| llk_math_dest_section_done()      | TRISC1  | Signal DEST half-buffer full       |
| llk_pack_init()                   | TRISC2  | Initialize packer format           |
| llk_pack()                        | TRISC2  | Pack DEST tile to L1               |
| llk_pack_l1_acc()                 | TRISC2  | Pack with L1 accumulation          |
| llk_pack_dest_section_done()      | TRISC2  | Signal packed tile available       |
| llk_pack_wait_for_output_space()  | TRISC2  | Wait for output buffer space       |

### E. ROCC Instruction Reference

ROCC custom instructions use opcode CUSTOM_1 (major opcode 0x2B in RISC-V encoding).
All instructions are R-type: `funct7=0x2B, funct3=<op>, rd, rs1, rs2`.

| Mnemonic | funct3 | rs1          | rs2       | rd     | Description                       |
|----------|--------|--------------|-----------|--------|-----------------------------------|
| DMSRC    | 0x0    | src_address  | —         | —      | Load source address register      |
| DMDST    | 0x1    | dst_address  | —         | —      | Load destination address register |
| DMCPYI   | 0x2    | descriptor   | imm       | status | Immediate copy (imm = length)     |
| DMCPY    | 0x3    | descriptor   | length    | status | Register copy (length from rs2)   |
| DMSTATI  | 0x4    | —            | imm (TID) | count  | Immediate TID status read         |
| DMSTAT   | 0x5    | tid_reg      | —         | count  | Register TID status read          |
| DMSTR    | 0x6    | src_stride   | dst_stride| —      | Set 2D strides                    |
| DMREP    | 0x7    | num_reps     | —         | —      | Set 2D repetition count           |

**Assembly macros:**
```c
// Convenience macros using GCC inline assembly
#define ROCC_DMSRC(src)    asm volatile(".insn r 0x2B, 0x0, 0x2B, x0, %0, x0" :: "r"(src))
#define ROCC_DMDST(dst)    asm volatile(".insn r 0x2B, 0x1, 0x2B, x0, %0, x0" :: "r"(dst))
#define ROCC_DMCPY(len, tid, ret) \
    asm volatile(".insn r 0x2B, 0x3, 0x2B, %0, %1, %2" : "=r"(ret) : "r"(len), "r"(tid))
#define ROCC_DMSTATI(tid, ret) \
    asm volatile(".insn r 0x2B, 0x4, 0x2B, %0, x0, x0" : "=r"(ret) : "i"(tid))
```

---

*Document: Trinity N1B0 — Software Engineer's Guide v0.1*
*Date: 2026-03-24*
*Sources: tensix_core_HDD.md v0.3, INT16_Guide_HDD_V0.2, overlay_dma_HDD_v0.4.md,*
*NIU_HDD_v0.1.md, router_decode_HDD_v0.5.md, SW_Performance_Guide_HDD_V0.1.md,*
*N1B0_HDD_v0.1.md, RTL snapshot 20260221*
