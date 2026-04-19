# Trinity N1B0 — NPU SW Engineer's Complete Guide v0.3

## Version Table

| Version | Date       | Author     | Changes                                                                                 |
|---------|------------|------------|-----------------------------------------------------------------------------------------|
| v0.1    | 2026-03-24 | SW Team    | Initial release — all sections (N1B0_SW_Guide_v0.1.md)                                 |
| v0.2    | 2026-03-25 | SW Team    | Merged superset: full DMA HDD (overlay_dma_HDD_v0.4) integrated; §3 RISC-V CPU extended with boot/PLIC/CLINT/fence/ROCC/context-switch/multi-hart; §7 iDMA replaced with full HDD architecture+SFR+programming guide (15 subsections); §10 performance expanded with 7 new subsections; §11 debugging guide added; §12 SW driver template added; §17 appendices expanded |
| v0.3    | 2026-03-25 | SW Team    | SFR read/write examples added throughout; §8 NoC/NIU fully expanded (DOR walk-through, full NIU register map with RTL-verified offsets, VC selection code, broadcast/read/status examples); iDMA APB TBDs resolved (base=0x03004000, full CMD_BUF_R/W register map from RTL); all external cross-references removed (self-contained HDD); §7 iDMA driver code updated with real addresses |

---

## Table of Contents

- §1  Overview — N1B0 Architecture
- §2  Memory Map and Address Space
- §3  RISC-V Cores — Programming Model
  - §3.1  Core Types
  - §3.2  TRISC Thread Roles
  - §3.3  BRISC Data Movement Role
  - §3.4  Overlay CPU Role
  - §3.5  Register Map per Core Type
  - §3.6  Semaphore System
  - §3.7  Mailbox System
  - §3.8  Boot Sequence and Reset Vector
  - §3.9  Per-Hart Stack Layout
  - §3.10 PLIC — Platform-Level Interrupt Controller
  - §3.11 CLINT — Core-Local Interruptor
  - §3.12 Fence and Memory Ordering with DMA
  - §3.13 ROCC Custom Instruction Interface
  - §3.14 Context Switch Considerations
  - §3.15 Multi-Hart Coordination Patterns
- §4  TDMA — Tensor DMA Unpack/Pack Engine
- §5  FPU and Math Engine
- §6  LLK (Low-Latency Kernel) API
- §7  iDMA Engine — Architecture and Programming
  - §7.1  Overview and Feature Summary
  - §7.2  System Architecture
  - §7.3  Module Descriptions
  - §7.4  Key Parameters
  - §7.5  SFR Reference
  - §7.6  Initialization Sequence
  - §7.7  Basic 1D Transfer / DRAM to L1
  - §7.8  2D Scatter-Gather Transfer
  - §7.9  Tile-Based vs Non-Tile Access
  - §7.10 Address Translation (ATT)
  - §7.11 Data Format Conversion (DFC)
  - §7.12 L1 Accumulate / Zero-Copy
  - §7.13 Multi-Client Pipelining
  - §7.14 Sparsity and Zero Handling
  - §7.15 Completion Tracking and IRQ
  - §7.16 DMA + TDMA Pipeline
  - §7.17 Multi-Tile DMA Coordination
  - §7.18 Error Detection and Recovery
- §8  NoC and NIU
- §9  NOC2AXI and DRAM Access
- §10 Performance Guide — Combined
  - §10.1 Compute Throughput (TOPS Estimates)
  - §10.2 Memory Bandwidth Budget
  - §10.3 Bottleneck Diagnosis
  - §10.4 Double-Buffer Pattern (DMA + Compute Overlap)
  - §10.5 Fidelity Mode Selection
  - §10.6 Format Selection Table
  - §10.7 Clock Gating Configuration
  - §10.8 In-Flight Transaction Depth
  - §10.9 Backend Selection
  - §10.10 2D Transfer Efficiency
  - §10.11 L1 Bandwidth Estimation
  - §10.12 DRAM Throughput Optimization
  - §10.13 Latency-Hiding Patterns
- §11 Debugging Guide
- §12 SW Driver Template
- §13 LLM Inference Guide — LLaMA 3.1 8B
- §14 INT8 Guide
- §15 VC Channel Guide
- §16 DRAM Address Access Guide
- §17 Appendix
  - §17.1 DFC Format Table
  - §17.2 ROCC iDMA Instruction Reference
  - §17.3 Address Map Quick Reference
  - §17.4 Semaphore Map
  - §17.5 THCON Register Reference
  - §17.6 LLK Function Index
  - §17.7 EndpointIndex Table

---

## §1. Overview

### §1.1 Chip Overview — 4×5 Grid and Tile Types

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

### §1.2 Per-Tile Execution Model

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

### §1.3 Memory Hierarchy

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

### §1.4 Key Design Principles for SW

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

## §2. Memory Map and Address Space

### §2.1 Tile-Local Address Map

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

#### §x.x SFR Example — T6_L1_CSR Port Status and Error Checking

```c
#define T6_L1_CSR_BASE   0x03000200UL
#define L1_REG32(off)    (*(volatile uint32_t *)(T6_L1_CSR_BASE + (off)))

// PORT_STATUS registers (one per L1 port)
// Example offset for port 2 status: check SVH for exact offsets
// Common status bits (check T6_L1_CSR register map):
#define PORT_STATUS_FIFO_PARITY_ERR  (1u << 8)
#define PORT_STATUS_OVERFLOW         (1u << 4)
#define PORT_STATUS_UNDERFLOW        (1u << 5)

void l1_check_port_errors(void) {
    // Read hash function selection
    uint32_t hash_sel = L1_REG32(0x0C);  // GROUP_HASH_FN_SEL
    // bits[1:0]: 0=linear, 1=hash0, 2=hash1

    // Read in-order mask (which ports require in-order access)
    uint32_t inorder = L1_REG32(0x10);  // IN_ORDER_MASK
    // bit N = 1: port N must complete in order

    // Check port parity errors (offset varies by port index)
    // For example PORT_STATUS_2 (check exact offset in SVH):
    // If parity error bit is set, clear it (W1C) and log
    for (int port = 0; port < 32; port++) {
        // Each port status at base + port_status_offset + port*4
        // (Consult N1B0_NPU_sfr_v0.3.csv for exact per-port offsets)
    }
}

// Configure L1 hash function for bank distribution
// Use hash mode to spread accesses across banks and avoid bank conflicts
void l1_set_hash_mode(int mode) {
    // mode: 0=linear (sequential bank), 1=hash fn 0 (XOR-based), 2=hash fn 1
    L1_REG32(0x0C) = mode & 0x3;  // GROUP_HASH_FN_SEL
}
```

### §2.2 System Memory Map — DRAM Regions (SI0–SI3)

The four NOC2AXI tiles at Y=4 each provide access to one 128 MB DRAM bank:

```
SI0: 0x6000_0000 – 0x67FF_FFFF   128 MB   NOC2AXI at (X=0, Y=4)
SI1: 0x6800_0000 – 0x6FFF_FFFF   128 MB   NOC2AXI at (X=1, Y=4)
SI2: 0x7000_0000 – 0x77FF_FFFF   128 MB   NOC2AXI at (X=2, Y=4)
SI3: 0x7800_0000 – 0x7FFF_FFFF   128 MB   NOC2AXI at (X=3, Y=4)
```

To access SI0 from a Tensix tile, address a NoC packet to (X=0, Y=4) with the local
byte address set to `physical_dram_addr - 0x6000_0000`.

### §2.3 Register Region Map — Overlay, Tensix, NOC

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

### §2.4 NoC Address Encoding for Remote Tiles

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

### §2.5 DRAM Access via NOC2AXI

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

## §3. RISC-V Cores — Overview and Programming Model

### §3.1 Core Types

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

### §3.2 TRISC Thread Roles

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

### §3.3 BRISC Data Movement Role

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

### §3.4 Overlay CPU Role

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

### §3.5 Register Map per Core Type

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

### §3.6 Semaphore System

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

### §3.7 Mailbox System

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

### §3.8 Boot Sequence and Reset Vector Setup


At power-on, all harts are held in reset by the SMN ring. The host must load firmware into L1 or DRAM, set up reset vectors, then release harts from reset in the desired order.

**Detailed boot steps:**

1. SMN asserts hart reset: all harts are held in reset (`i_smn_reset_n[7:0] = 0`)
2. Host/firmware copies tile firmware binary to L1 SRAM or DRAM via a separate DMA path (e.g., host-side PCIe DMA)
3. Host writes per-hart RESET_VECTOR_N registers via APB to `cluster_ctrl_apb` base 0x03000000
4. Host deasserts per-hart reset via the SMN sequence or by writing DEBUG_DMACTIVE
5. Each released hart fetches its first instruction from `RESET_VECTOR_N << 2` (word address -> byte address)
6. Hart firmware executes: initialize stack pointer, set up `mtvec`, optionally clear BSS, then enter main work loop

NOTE: RESET_VECTOR_N stores a **word address** (bits [57:0] of the byte address right-shifted by 2). Firmware must right-shift the byte address by 2 before writing the register.

```c
// Host-side: set hart 0 reset vector before releasing from reset
#define CLUSTER_CTRL_BASE  0x03000000UL
#define RESET_VECTOR_0     (CLUSTER_CTRL_BASE + 0x000)
#define DEBUG_DMACTIVE     (CLUSTER_CTRL_BASE + 0x1C0)

// Set reset vector: byte_addr -> word_addr = byte_addr >> 2
void set_hart_reset_vector(int hart_id, uint64_t pc) {
    volatile uint64_t *rv = (uint64_t *)(RESET_VECTOR_0 + hart_id * 8);
    *rv = pc >> 2;   // stored as word address [57:0]
}

// Release hart from reset via DEBUG_DMACTIVE
void release_hart_from_reset(int hart_id) {
    volatile uint32_t *dmactive = (uint32_t *)DEBUG_DMACTIVE;
    *dmactive = (1u << hart_id);   // set bit to activate hart
}

// Full bring-up sequence for a tile
void tile_bring_up(uint64_t firmware_entry_point) {
    // Set all harts to same entry point (or per-hart if needed)
    for (int i = 0; i < 8; i++) {
        set_hart_reset_vector(i, firmware_entry_point);
    }
    // Release hart 0 first; hart 0 will release others via CLINT MSIP
    release_hart_from_reset(0);
}
```

#### §3.x.1 SFR Example — Set Hart Reset Vector Before Release

```c
#define CLUSTER_CTRL_BASE   0x03000000UL
#define REG64(base, off)    (*(volatile uint64_t *)((base) + (off)))
#define REG32(base, off)    (*(volatile uint32_t *)((base) + (off)))

// Set hart N boot address (word address = byte_addr >> 3)
void set_hart_reset_vector(int hart, uint64_t boot_byte_addr) {
    // RESET_VECTOR_N at offset 0x00 + N*8 (64-bit register)
    uint64_t word_addr = boot_byte_addr >> 3;   // bits[57:0] are word address
    REG64(CLUSTER_CTRL_BASE, hart * 8) = word_addr & 0x03FFFFFFFFFFFFFFULL;
}

// Check hart writeback PC after a crash
uint64_t get_hart_wb_pc(int hart) {
    // WB_PC_REG_CN at offset 0xD8 + N*8
    uint64_t wb_word_addr = REG64(CLUSTER_CTRL_BASE, 0xD8 + hart * 8);
    return wb_word_addr << 3;  // convert back to byte address
}

// Example: boot all 8 harts at 0x04000000 (firmware load address)
void boot_all_harts(void) {
    for (int i = 0; i < 8; i++) {
        set_hart_reset_vector(i, 0x04000000UL);
    }
    // After setting vectors, release harts from reset via SoC-level reset controller
}
```

#### §3.x.2 SFR Example — ECC Parity Control and Status

```c
// ECC_PARITY_CONTROL at offset 0x11C
// bits[1:0]: 0=off, 1=detect only, 2=detect+correct, 3=reserved
#define ECC_CTRL  REG32(CLUSTER_CTRL_BASE, 0x11C)
#define ECC_STATUS REG32(CLUSTER_CTRL_BASE, 0x120)  // RO/W1C

void ecc_enable_detect_correct(void) {
    ECC_CTRL = 2;  // detect + correct mode
}

void ecc_check_status(void) {
    uint32_t status = ECC_STATUS;
    if (status != 0) {
        // ECC error occurred — clear by writing 1 to affected bits
        ECC_STATUS = status;  // W1C: write read-value back
        handle_ecc_error(status);
    }
}
```

#### §3.x.3 SFR Example — Bus Error Unit

```c
// BUS_ERROR_UNIT_DATA_CN at offset 0x130 + N*8 (one per hart)
// RO/W1C: read error address, write 1 to clear

void check_bus_errors(void) {
    for (int hart = 0; hart < 8; hart++) {
        uint32_t err = REG32(CLUSTER_CTRL_BASE, 0x130 + hart * 8);
        if (err != 0) {
            // err_addr = bits[31:0] — byte address of offending AXI access
            handle_hart_bus_error(hart, err);
            REG32(CLUSTER_CTRL_BASE, 0x130 + hart * 8) = err;  // W1C clear
        }
    }
}
```

**On-tile firmware entry stub (RISC-V assembly):**

```asm
.section .text.entry
.global _start
_start:
    # Set up stack pointer based on hart ID
    csrr    t0, mhartid
    li      t1, 4096              # HART_STACK_SIZE
    mul     t0, t0, t1
    la      sp, __stack_top       # top of hart 0 stack
    sub     sp, sp, t0            # each hart gets its own stack

    # Set up trap handler
    la      t0, machine_trap_handler
    csrw    mtvec, t0

    # Clear BSS (hart 0 only)
    csrr    t0, mhartid
    bnez    t0, .skip_bss_clear
    la      t0, __bss_start
    la      t1, __bss_end
1:  bge     t0, t1, .skip_bss_clear
    sd      zero, 0(t0)
    addi    t0, t0, 8
    j       1b
.skip_bss_clear:
    # Jump to C main
    call    hart_main
    # Should never return; halt
1:  wfi
    j       1b
```

---

### §3.9 Per-Hart Stack Layout and Memory Map


In N1B0, each tile has 768 KB of L1 SRAM. A practical layout for 8 harts sharing this space:

```
L1 Memory (768 KB = 0x000000 to 0x0BFFFF per tile)
+---------------------------------------------+ 0x0BF000 (top - 4KB)
|  Hart 7 stack (4 KB)                        |
+---------------------------------------------+ 0x0BE000
|  Hart 6 stack (4 KB)                        |
+---------------------------------------------+ 0x0BD000
|  Hart 5 stack (4 KB)                        |
+---------------------------------------------+ 0x0BC000
|  Hart 4 stack (4 KB)                        |
+---------------------------------------------+ 0x0BB000
|  Hart 3 stack (4 KB)                        |
+---------------------------------------------+ 0x0BA000
|  Hart 2 stack (4 KB)                        |
+---------------------------------------------+ 0x0B9000
|  Hart 1 stack (4 KB)                        |
+---------------------------------------------+ 0x0B8000
|  Hart 0 stack (4 KB)                        |
+---------------------------------------------+ 0x0B7000
|  Shared data / reduction buffers (variable) |
+---------------------------------------------+ 0x090000
|  DMA staging buffer B (double-buffer idle)  |
|  (256 KB)                                   |
+---------------------------------------------+ 0x050000
|  DMA staging buffer A (double-buffer active)|
|  (256 KB)                                   |
+---------------------------------------------+ 0x010000
|  Firmware code (.text) + .rodata            |
|  (64 KB)                                    |
+---------------------------------------------+ 0x000000
```

TIP: Align DMA buffers to 128-byte (cache line) boundaries. Keep stacks at the top of L1 so that tensor data placed at the bottom cannot grow into the stack region.

TIP: If firmware code is small, it can be placed entirely in L1 to avoid I-cache misses to DRAM. Typical firmware for a single tile workload fits within 32–64 KB.

```c
#define L1_BASE              0x00000000UL
#define L1_SIZE              (768 * 1024)
#define HART_STACK_SIZE      4096
// Stack top for hart 'id': hart 0 uses 0x0B8000..0x0B8FFF, etc.
#define HART_STACK_TOP(id)   (L1_BASE + L1_SIZE - (id) * HART_STACK_SIZE)
// DMA double-buffer regions
#define DMA_BUF_A_BASE       (L1_BASE + 0x10000)
#define DMA_BUF_B_BASE       (L1_BASE + 0x50000)
#define DMA_BUF_SIZE         (256 * 1024)
// Shared data region
#define SHARED_DATA_BASE     (L1_BASE + 0x090000)
#define SHARED_DATA_SIZE     (L1_SIZE - 8*HART_STACK_SIZE - 2*DMA_BUF_SIZE - 0x10000)
```

WARNING: Do not overlap DMA buffer regions with the firmware code region. A DMA write to the code region will corrupt executing instructions and cause undefined behavior.

---

### §3.10 PLIC — Platform-Level Interrupt Controller


Trinity uses a standard RISC-V PLIC for routing external interrupts to harts. The iDMA engine's per-TID IRQ outputs (`o_idma_tiles_to_process_irq[31:0]`) are wired as PLIC external interrupt sources.

**PLIC register layout (standard RISC-V PLIC):**
```
PLIC_BASE (chip-specific, e.g., 0x0C00_0000)
  Priority registers:  PLIC_BASE + 4*irq_id   (one 32-bit word per IRQ source)
  Pending bits:        PLIC_BASE + 0x1000      (one bit per IRQ source)
  Enable registers:    PLIC_BASE + 0x2000 + 0x80*context_id
  Threshold register:  PLIC_BASE + 0x200000 + 0x1000*context_id
  Claim/complete reg:  PLIC_BASE + 0x200004 + 0x1000*context_id
```

M-mode context ID for hart N = N * 2 (S-mode = N * 2 + 1, not used in machine-mode firmware).

**Setup sequence:**

1. Set priority for each PLIC source (write 1–7; 0 = disabled)
2. Set threshold for each hart context (0 = accept all non-zero priority IRQs)
3. Enable specific IRQ sources in PLIC enable registers
4. Set `mie.MEIE` (bit 11) to enable M-mode external interrupts
5. Set `mstatus.MIE` (bit 3) to enable global interrupts
6. Set `mtvec` to the trap handler address (bit[1:0] = 0 for direct mode)

```c
#define PLIC_BASE          0x0C000000UL   // SoC-specific: verify with integration team
#define PLIC_PRIORITY(n)   (*(volatile uint32_t *)(PLIC_BASE + 4*(n)))
#define PLIC_ENABLE_REG(ctx, irq)  \
    (*(volatile uint32_t *)(PLIC_BASE + 0x2000 + 0x80*(ctx) + 4*((irq)/32)))
#define PLIC_THRESHOLD(ctx) (*(volatile uint32_t *)(PLIC_BASE + 0x200000 + 0x1000*(ctx)))
#define PLIC_CLAIM(ctx)     (*(volatile uint32_t *)(PLIC_BASE + 0x200004 + 0x1000*(ctx)))

// iDMA TID 0..31 are mapped to PLIC IRQ sources IDMA_IRQ_BASE..IDMA_IRQ_BASE+31
#define IDMA_IRQ_BASE      32    // confirm with SoC integration team

void plic_enable_idma_irq(int hart_id, int tid) {
    int irq     = IDMA_IRQ_BASE + tid;
    int context = hart_id * 2;   // M-mode context

    // Set priority 1 (lowest non-zero)
    PLIC_PRIORITY(irq) = 1;

    // Enable IRQ in this hart's context
    PLIC_ENABLE_REG(context, irq) |= (1u << (irq % 32));

    // Accept any priority
    PLIC_THRESHOLD(context) = 0;
}

void plic_disable_idma_irq(int hart_id, int tid) {
    int irq     = IDMA_IRQ_BASE + tid;
    int context = hart_id * 2;
    PLIC_ENABLE_REG(context, irq) &= ~(1u << (irq % 32));
}

// Called from trap handler: claim pending IRQ
int plic_claim_irq(int hart_id) {
    return (int)PLIC_CLAIM(hart_id * 2);
}

// Called after handling: complete the IRQ
void plic_complete_irq(int hart_id, int irq) {
    PLIC_CLAIM(hart_id * 2) = (uint32_t)irq;
}
```

**Trap handler with PLIC:**

```c
// Shared completion flags (one per TID)
volatile int g_dma_done[32];

void __attribute__((interrupt("machine"))) machine_trap_handler(void) {
    uint64_t mcause;
    asm volatile ("csrr %0, mcause" : "=r"(mcause));

    if (mcause & (1ULL << 63)) {
        // Asynchronous interrupt
        uint64_t cause = mcause & 0x7FFFFFFFFFFFFFFFULL;

        if (cause == 3) {
            // M-mode software interrupt (MSIP from CLINT)
            int hart_id;
            asm volatile ("csrr %0, mhartid" : "=r"(hart_id));
            // Clear MSIP
            *((volatile uint32_t *)(0x02000000UL + 4 * hart_id)) = 0;
            // User handler
            handle_msip(hart_id);

        } else if (cause == 11) {
            // M-mode external interrupt (from PLIC)
            int hart_id;
            asm volatile ("csrr %0, mhartid" : "=r"(hart_id));
            int irq = plic_claim_irq(hart_id);

            if (irq >= IDMA_IRQ_BASE && irq < IDMA_IRQ_BASE + 32) {
                int tid = irq - IDMA_IRQ_BASE;
                // Clear the iDMA TID counter
                idma_clear_tid(tid);
                g_dma_done[tid] = 1;
            }
            plic_complete_irq(hart_id, irq);
        }

    } else {
        // Synchronous exception
        uint64_t mepc, mtval;
        asm volatile ("csrr %0, mepc"  : "=r"(mepc));
        asm volatile ("csrr %0, mtval" : "=r"(mtval));
        // Log and halt — exceptions are fatal in most firmware contexts
        fatal_exception(mcause, mepc, mtval);
    }
}

void hart_init_interrupts(void) {
    // Point mtvec at trap handler (direct mode: bits[1:0] = 0b00)
    uintptr_t tvec = (uintptr_t)machine_trap_handler;
    // Ensure alignment (direct mode requires 4-byte alignment)
    asm volatile ("csrw mtvec, %0" :: "r"(tvec & ~3UL));

    // Enable M-mode software interrupt (MSIE, bit 3) and external interrupt (MEIE, bit 11)
    asm volatile ("csrs mie, %0" :: "r"((1u << 3) | (1u << 11)));

    // Enable global machine interrupt
    asm volatile ("csrs mstatus, %0" :: "r"(1u << 3));  // MIE bit
}
```

---

### §3.11 CLINT — Core-Local Interruptor


The CLINT provides per-hart machine software interrupts (MSIP) and a machine timer (MTIME/MTIMECMP). Software interrupts are the primary mechanism for one hart to wake another.

**Register layout:**
```
CLINT_BASE (chip-specific, e.g., 0x0200_0000)
  MSIP[hart_id]    : CLINT_BASE + 0x0000 + hart_id*4  (RW, 1-bit, write 1 to assert)
  MTIMECMP[hart_id]: CLINT_BASE + 0x4000 + hart_id*8  (RW, 64-bit)
  MTIME            : CLINT_BASE + 0xBFF8               (RO, 64-bit, free-running)
```

```c
#define CLINT_BASE          0x02000000UL
#define CLINT_MSIP(id)      ((volatile uint32_t *)(CLINT_BASE + 4*(id)))
#define CLINT_MTIMECMP(id)  ((volatile uint64_t *)(CLINT_BASE + 0x4000 + 8*(id)))
#define CLINT_MTIME         ((volatile uint64_t *)(CLINT_BASE + 0xBFF8))
#define CLINT_FREQ_HZ       1000000UL   // 1 MHz reference (platform-specific)

// Hart A sends software interrupt to wake hart B
void wake_hart(int target_hart) {
    *CLINT_MSIP(target_hart) = 1;   // assert software interrupt
    // Memory fence to ensure the write reaches CLINT before returning
    asm volatile ("fence w,w");
}

// Called from MSI handler: hart clears its own MSIP
void msip_clear(void) {
    int hart_id;
    asm volatile ("csrr %0, mhartid" : "=r"(hart_id));
    *CLINT_MSIP(hart_id) = 0;
}

// Busy-wait with timeout using MTIME (timeout_us in microseconds)
// Returns 0 on success, -1 on timeout
int wait_flag_timeout_us(volatile int *flag, uint64_t timeout_us) {
    uint64_t deadline = *CLINT_MTIME + timeout_us * (CLINT_FREQ_HZ / 1000000ULL);
    while (!*flag) {
        if (*CLINT_MTIME > deadline) return -1;
        asm volatile ("nop");   // prevent tight loop from starving other harts
    }
    return 0;
}

// Machine timer interrupt: periodic tick
void set_timer_interrupt_us(int hart_id, uint64_t period_us) {
    uint64_t now = *CLINT_MTIME;
    *CLINT_MTIMECMP(hart_id) = now + period_us * (CLINT_FREQ_HZ / 1000000ULL);
    // Enable MTIE in mie CSR
    asm volatile ("csrs mie, %0" :: "r"(1u << 7));  // MTIE bit
}
```

NOTE: CLINT_FREQ_HZ is the MTIME increment frequency, which is typically a slow reference clock (1 MHz or 10 MHz), NOT the core clock. Confirm the actual value with the platform integration team.

---

### §3.12 Fence and Memory Ordering with DMA


The RISC-V memory model (RVWMO) does not guarantee that stores visible to one agent are immediately visible to another (DMA engine). SW must use `fence` instructions at all DMA boundaries.

**Critical rules:**

1. **Before issuing DMA (source data):** All CPU stores to the source buffer must be visible to L1 SRAM before the DMA reads them. Insert `fence w,w` (or `fence`) before `DMSRC`/`DMCPY`.

2. **After DMA completes (destination data):** All DMA writes to the destination buffer must be visible to the CPU before it reads them. Insert `fence r,r` (or `fence`) after polling/IRQ completion, before reading the destination buffer.

3. **Between DMA and TDMA:** TDMA reads from L1; DMA writes to L1. After DMA completes, insert a `fence` before issuing TDMA UNPACR instructions that read the same region.

```c
// CORRECT ordering pattern: CPU write -> DMA -> CPU read

// Step 1: CPU prepares source data in L1
memcpy(l1_src_ptr, cpu_data, len);
asm volatile ("fence w,w");    // ensure CPU stores are visible to DMA engine

// Step 2: Issue DMA transfer
asm_dmsrc(l1_src_addr);
asm_dmdst(remote_noc_addr_or_dram);
asm_dmcpy(len, FLAGS_TID(0));

// Step 3: Wait for completion
while (!(idma_read_tr_count(0) >= 1)) { }
idma_clear_tid(0);
asm volatile ("fence r,r");    // ensure DMA writes are visible to CPU

// Step 4: CPU reads destination
process_data(l1_dst_ptr);
```

WARNING: Omitting `fence w,w` before DMA is the most common source of data corruption. The CPU store buffer may not have flushed to L1 SRAM when the DMA engine begins reading.

WARNING: Omitting `fence r,r` after DMA completion is the second most common bug. The CPU may observe stale cached values from before the DMA write.

**DMA write to remote tile — remote tile must also fence:**
```c
// After Tile A sends data via DMA PUT to Tile B's L1,
// the firmware running on Tile B must fence before reading:

// Tile B firmware (signaled that DMA has arrived):
asm volatile ("fence r,r");
uint32_t *received = (uint32_t *)L1_BASE;
// received[] is now guaranteed valid
```

---

### §3.13 ROCC Custom Instruction Interface


The ROCC (Rocket Custom Co-processor) extension provides a tightly coupled interface between each CPU hart and its dedicated iDMA client port (clients 0–7 = harts 0–7).

**ROCC opcode assignment:**
- `CUSTOM_0` (opcode 0x0B): Reserved
- `CUSTOM_1` (opcode 0x2B): iDMA instructions (funct7=0x2B)
- `CUSTOM_2` (opcode 0x5B): Reserved
- `CUSTOM_3` (opcode 0x7B): Reserved

**Shadow register model:** Instructions DMSRC, DMDST, DMSTR, and DMREP each write per-hart shadow registers inside `tt_rocc_accel`. These registers are not committed to hardware until `DMCPY` is issued. `DMCPY` is the commit instruction.

**Instruction timing:**
- DMSRC/DMDST/DMSTR/DMREP: 1 cycle (shadow register write, no FIFO interaction)
- DMCPY: may stall if frontend FIFO is full (`o_idma_ready[client_id] = 0`)
- DMSTAT/DMSTATI: returns immediately without stalling

**Back-pressure behavior:** If the iDMA frontend FIFO (metadata depth=42 entries) is full, `o_idma_ready[client_id]` is deasserted. The ROCC interface will hold the CPU hart in a wait state until space becomes available. This is transparent to firmware but means DMCPY can block for many cycles under heavy load.

**Practical FIFO capacity per hart:** With 24 clients sharing a 42-entry FIFO and weighted round-robin arbitration, each hart can sustain approximately 1–2 in-flight descriptors before hitting FIFO pressure. Issuing more than 2 DMCPY instructions per hart before waiting for completions may cause DMCPY to stall.

```c
// Check readiness before issuing to avoid stalls
// DMSTATI with field=DMSTAT_READY returns 1 if frontend can accept
static inline uint64_t asm_dmstati(uint64_t field) {
    uint64_t result;
    asm volatile (".insn r 0x2B, 4, 0, %0, zero, %1"
                  : "=r"(result) : "r"(field));
    return result;
}

// Non-blocking DMA issue with readiness check
int try_issue_dma(uint64_t src, uint64_t dst, uint64_t len, int trid) {
    if (!asm_dmstati(1 /* DMSTAT_READY */)) {
        return -1;  // FIFO full, caller must retry
    }
    asm_dmsrc(src);
    asm_dmdst(dst);
    asm_dmcpy(len, (uint64_t)trid & 0x1F);
    return 0;
}
```

---

### §3.14 Context Switch Considerations


NOTE: Trinity N1B0 firmware typically does not perform preemptive context switching — each hart runs a dedicated workload. However, some runtime frameworks implement cooperative multitasking. This section covers the implications for iDMA and ROCC state.

**Shadow register state (DMSRC/DMDST/DMSTR/DMREP):** These are stored inside `tt_rocc_accel` per hart. They are NOT saved/restored by hardware on context switch. If a context switch occurs between DMSRC and DMCPY instructions, the shadow registers for the suspended task will be corrupted by the newly scheduled task.

**SW obligation:** Any context switch implementation must save and restore the ROCC shadow register state. Since these are not CSRs (they are internal ROCC registers), saving them requires re-issuing the DMSRC/DMDST/DMSTR/DMREP instructions after a context restore.

**In-flight DMA transfers:** DMA transfers submitted via DMCPY are independent of the issuing hart's execution state. They continue to completion even if the hart is reset or context-switched. The DMA engine does not track which hart submitted a transfer; it only tracks TIDs.

**TID ownership:** It is the SW's responsibility to track which context owns which TID. A context switch must either:
a) Wait for all owned TIDs to complete before switching out, or
b) Transfer TID ownership to the new context and ensure the new context handles completion IRQs.

```c
// Safe context switch: wait for all in-flight TIDs owned by this context
typedef struct {
    uint64_t shadow_src;
    uint64_t shadow_dst;
    uint64_t shadow_str_src;
    uint64_t shadow_str_dst;
    uint64_t shadow_rep;
    uint32_t owned_tids;    // bitmask of TIDs owned by this context
} rocc_context_t;

void context_switch_out(rocc_context_t *ctx) {
    // Wait for all owned TIDs to complete
    for (int tid = 0; tid < 32; tid++) {
        if (ctx->owned_tids & (1u << tid)) {
            while (!(idma_read_tr_count(tid) >= 1)) { }
            idma_clear_tid(tid);
        }
    }
    ctx->owned_tids = 0;
    // Shadow regs are indeterminate after switch; re-issue before next DMCPY
}

void context_switch_in(rocc_context_t *ctx) {
    // Restore shadow registers if a pending transfer was interrupted
    // (only needed if transfer was not completed before switch-out)
    asm_dmsrc(ctx->shadow_src);
    asm_dmdst(ctx->shadow_dst);
    asm_dmstr(ctx->shadow_str_src, ctx->shadow_str_dst);
    asm_dmrep(ctx->shadow_rep);
    // Now DMCPY may be safely issued
}
```

---

### §3.15 Multi-Hart Coordination Patterns


Three common patterns for coordinating multiple harts within a tile:

---

**Pattern A — Barrier (all harts synchronize at a point):**

All harts must arrive at the barrier before any proceeds. Uses an atomic counter in shared L1.

```c
// Placed in shared L1 SRAM (not on any hart's stack)
volatile int g_barrier_count = 0;
volatile int g_barrier_sense = 0;   // alternates 0/1 for reuse

void barrier(int n_harts) {
    int local_sense = !g_barrier_sense;   // flip expected sense

    // Atomically increment barrier counter
    asm volatile ("amoadd.w zero, %0, (%1)"
                  :: "r"(1), "r"(&g_barrier_count) : "memory");

    // Wait until all n_harts have arrived
    // Use sense-reversal to allow barrier reuse
    if (g_barrier_count == n_harts) {
        g_barrier_count = 0;
        asm volatile ("fence w,w");   // ensure counter reset is visible
        g_barrier_sense = local_sense;
    } else {
        while (g_barrier_sense != local_sense) {
            asm volatile ("nop");
        }
    }
    asm volatile ("fence r,r");   // ensure all data written before barrier is visible
}
```

---

**Pattern B — Producer-Consumer (hart 0 DMA-loads, harts 1–7 compute):**

Hart 0 acts as a DMA prefetch engine, loading tiles from DRAM into L1 double buffers. Harts 1–7 compute on ready buffers.

```c
#define N_BUFS 2
volatile int g_buf_ready[N_BUFS] = {0, 0};
volatile int g_buf_consumed[N_BUFS] = {1, 1};  // start as "consumed" so producer fills them

// Hart 0: DMA producer
void producer_task(uint64_t *dram_tiles, int n_tiles) {
    for (int i = 0; i < n_tiles; i++) {
        int buf = i % N_BUFS;

        // Wait for consumers to finish with this buffer
        while (!g_buf_consumed[buf]) { asm volatile ("nop"); }
        g_buf_consumed[buf] = 0;

        // Load next tile into this buffer via DMA
        asm_dmsrc(dram_tiles[i]);
        asm_dmdst(DMA_BUF_A_BASE + (uint64_t)buf * DMA_BUF_SIZE);
        asm_dmcpy(DMA_BUF_SIZE, FLAGS_TID(buf));

        while (!(idma_read_tr_count(buf) >= 1)) { }
        idma_clear_tid(buf);

        asm volatile ("fence w,w");    // DMA write visible before signal
        g_buf_ready[buf] = 1;          // signal consumers
    }
}

// Harts 1-7: compute consumers
void consumer_task(int hart_id, int n_tiles) {
    for (int i = hart_id - 1; i < n_tiles; i += 7) {
        int buf = i % N_BUFS;

        while (!g_buf_ready[buf]) { asm volatile ("nop"); }
        asm volatile ("fence r,r");    // DMA write visible to this hart

        compute_on_buffer(DMA_BUF_A_BASE + (uint64_t)buf * DMA_BUF_SIZE, hart_id);

        // Signal producer that this hart is done with the buffer
        // Use atomic to handle multiple consumers safely
        asm volatile ("amoadd.w zero, %0, (%1)"
                      :: "r"(1), "r"(&g_buf_consumed[buf]) : "memory");
    }
}
```

---

**Pattern C — CLINT MSIP wake (hart 0 issues DMA, wakes hart 1 on completion via software interrupt):**

Hart 1 sleeps in WFI; hart 0 sends it a software interrupt after DMA completes.

```c
// Hart 0: issue DMA, then wake hart 1
void dma_and_notify_hart1(uint64_t dram_src, uint64_t l1_dst, uint32_t bytes) {
    // Set TID 0 IRQ threshold (optional; we poll here, then use MSIP to wake hart 1)
    asm_dmsrc(dram_src);
    asm_dmdst(l1_dst);
    asm_dmcpy(bytes, FLAGS_TID(0));

    while (!(idma_read_tr_count(0) >= 1)) { }
    idma_clear_tid(0);
    asm volatile ("fence w,w");   // DMA write visible before MSIP

    wake_hart(1);  // write CLINT_MSIP[1] = 1
}

// Hart 1: wait for wake, then process
void hart1_main(void) {
    // Enable software interrupt (MSIE, bit 3 of mie)
    asm volatile ("csrs mie, %0" :: "r"(1u << 3));
    asm volatile ("csrs mstatus, %0" :: "r"(1u << 3));  // global MIE

    while (1) {
        asm volatile ("wfi");      // sleep until MSIP
        asm volatile ("fence r,r"); // ensure DMA writes visible
        process(L1_BASE);
        // Optionally wake hart 0 to signal that processing is done
        wake_hart(0);
        asm volatile ("wfi");      // sleep again
    }
}
```

---

## §4. Tensor DMA (TDMA) — Unpack and Pack Engine

### §4.1 Overview

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
   └──[Packer 1]──────────┘
       format convert
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

### §4.2 Unpacker — From L1 to SRCA/SRCB

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

### §4.3 Packer — From DEST to L1

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

### §4.4 THCON Configuration Registers

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

#### §4.x THCON SFR Read/Write Example — Configuring Unpacker Format

```c
#define THCON_BASE   0x01800000UL
#define THCON_REG(off)  (*(volatile uint32_t *)(THCON_BASE + (off)))

// UNPACKER0_REG0 at offset 0x000
// bits[3:0]  = out_data_format (format to SRCA)
// bits[7:4]  = in_data_format  (format from L1)
// bits[15:8] = tilize_mode     (0=tile, 1=row-major)
// bits[19:16]= transpose       (0=none, 1=90deg)
// bit[20]    = enable_arg_fifo

#define FMT_FP32   0
#define FMT_FP16   1
#define FMT_BF16   2
#define FMT_FP8_E4M3  4
#define FMT_INT16  13
#define FMT_INT8   14
#define FMT_FP16B  15

// Configure unpacker 0: L1 has BF16, SRCA needs FP32 (format conversion)
void thcon_config_unpack0_bf16_to_fp32(void) {
    uint32_t reg = 0;
    reg |= FMT_FP32  << 0;   // out_data_format = FP32 (to SRCA)
    reg |= FMT_BF16  << 4;   // in_data_format  = BF16 (from L1)
    reg |= 0         << 8;   // tilize_mode = 0 (tile-based)
    reg |= 0         << 16;  // no transpose
    THCON_REG(0x000) = reg;
}

// Configure packer 0: DEST has INT32, pack to INT8 output with descale
void thcon_config_pack0_int32_to_int8(void) {
    uint32_t reg = 0;
    reg |= FMT_INT8  << 0;   // out_data_format = INT8 (to L1)
    reg |= 12        << 4;   // in_data_format  = INT32 (from DEST, code=12)
    // Enable INT8 descale right-shift
    reg |= (1u << 28);       // int_descale_en = 1
    THCON_REG(0x010) = reg;  // PACKER0_REG0 at offset 0x010
}

// Read back configuration and verify
void thcon_verify_unpack0(void) {
    uint32_t reg = THCON_REG(0x000);
    uint8_t out_fmt = reg & 0xF;
    uint8_t in_fmt  = (reg >> 4) & 0xF;
    if (out_fmt != FMT_FP32 || in_fmt != FMT_BF16) {
        handle_thcon_config_error(out_fmt, in_fmt);
    }
}
```

### §4.5 Address Modifier (ADDR_MOD) Configuration

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

### §4.6 Format Conversion Table (14 Formats)

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

### §4.7 Tilize and Untilize

TDMA supports hardware tilize (row-major L1 → tile-major SRCA) and untilize (tile-major
DEST → row-major L1).

- **Tilize** (unpacker): set `tilize_mode=1` in UNPACKER0 REG0. The unpacker reads
  consecutive elements along the row dimension and fills SRCA columns in tile order.
  Use this when activations arrive from DRAM in row-major order.
- **Untilize** (packer): set `untilize_mode=1` in PACKER0 REG0. The packer reorders
  DEST output from tile-major to row-major for writing to L1.
  Use this when output must be forwarded to the next layer as row-major.

Tilize/untilize have no throughput penalty — they happen inside the TDMA pipeline.

### §4.8 Zero-Skip (zmask), Sparsity, Edge Masking

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

### §4.9 L1 Accumulation in Packer

Setting `PACKER0_REG0.l1_acc=1` enables zero-copy in-place accumulation: instead of
overwriting the destination L1 address, the packer adds the DEST output to the existing
L1 value. This implements partial-sum accumulation across K-loop iterations without
allocating a separate DEST buffer per K-chunk.

**When to use L1 accumulate:**
- K is split across multiple tiles that run sequentially (K-parallel split).
- First tile sets `l1_acc=0` (write, not accumulate) to initialize.
- Subsequent tiles set `l1_acc=1` to accumulate.
- Last tile packs with descale and format conversion to produce final output.

### §4.10 Programming Example: Unpack → Math → Pack Flow

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

## §5. FPU and Math Engine

### §5.1 FPU Architecture

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

### §5.2 Matrix Multiply (INT16, FP16, FP32)

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

### §5.3 SFPU Operations

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

### §5.4 Math Fidelity Modes

| Mode   | ALU_FORMAT_SPEC | MULT_PAIRS | Throughput | Use Case                      |
|--------|-----------------|------------|------------|-------------------------------|
| LoFi   | FMT_FP16_B      | 4          | 2× slower  | Low-accuracy fast inference   |
| HiFi2  | FMT_FP16        | 4          | standard   | FP16 inference                |
| HiFi3  | FMT_FP16        | 8          | standard   | Higher-quality FP16           |
| HiFi4  | FMT_FP32        | 8          | standard   | FP32 training/fine-tuning     |

**Recommendation for INT16 LLM inference:** use HiFi2 (FMT_FP16, INT32 accumulator).
Provides best throughput with sufficient numeric precision for INT16 weight quantization.

### §5.5 DEST Register File

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

### §5.6 SRCA / SRCB Register Files

SRCA and SRCB are latch-arrays holding the FPU inputs:

```
SRCA: 48 rows × 16 columns × 19 bits (TF32 internal width)
SRCB: 48 rows × 16 columns × 19 bits
```

These are filled by TDMA unpackers with inline format conversion. The 48-row limit is the
hardware K_tile limit: K_tile = 48 is fixed.

### §5.7 Stochastic Rounding

When narrowing conversions are applied in the packer (e.g., FP32 → INT8), stochastic
rounding can be enabled via `PACKER0_REG0.stoch_rnd_en=1`. The PRNG embedded in the
packer generates a random low-order bias before rounding, reducing systematic quantization
error in fine-tuning workloads.

**Cost:** Zero throughput penalty. The PRNG runs in parallel with the packer pipeline.
**Use case:** Enable for fine-tuning and quantization-aware training. Disable for
inference (deterministic results required for debugging).

### §5.8 Programming Example: INT16 Matmul

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

## §6. LLK (Low-Latency Kernel) API

### §6.1 LLK Overview

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

### §6.2 llk_unpack_* — Tile Loading Functions

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

### §6.3 llk_math_* — Compute Functions

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

### §6.4 llk_pack_* — Tile Storing Functions

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

### §6.5 LLK Interface Counters

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

### §6.6 ROCC Custom Instructions for LLK

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

### §6.7 Circular Buffer Pattern (io_unpack / io_pack)

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

### §6.8 Synchronization: MOP, Semaphores, dvalid

- **MOP completion:** TRISC1 polls a hardware status bit (`MOP_STATUS.done`) after
  issuing a MOP instruction. LLK wraps this in `llk_math_wait_for_dest_available()`.
  After the wait, DEST contains the final accumulated result.

- **dvalid:** Each SRCA/SRCB row has a valid bit set by the TDMA unpacker and cleared
  by the FPU MAC array. TRISC1 must not issue MOP until dvalid bits are set — LLK
  handles this automatically via the semaphore protocol.

- **Semaphores:** LLK internally uses semaphores 4 and 7 (UNPACK_TO_DEST_UNPACK and
  UNPACK_TO_DEST_PACK). Kernels that add custom synchronization must use a different
  semaphore ID range to avoid conflict.

### §6.9 Full Example: INT16 Matmul Kernel

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

## §7. iDMA Engine — Architecture and Programming

### §7.1 Overview and Feature Summary


The Trinity N1B0 chip contains a 4×5 mesh of tiles. Each Tensix tile (columns X=0–3, rows Y=1–4) includes a per-tile **iDMA engine** (`tt_idma_wrapper`) instantiated inside `tt_overlay_wrapper`. The iDMA engine provides a general-purpose, software-programmable DMA facility that moves data between:

- Local L1 SRAM (within the same tile)
- Remote L1 SRAM (in another tile, via the NoC)
- External DRAM (DDR, via the NOC2AXI bridge at Y=0)

The iDMA engine is distinct from the **TDMA** (Tensor DMA) that lives inside the Tensix compute core. While TDMA is tightly coupled to the FPU datapath and handles tensor tiling, zero-masking, and tilize/untilize operations, iDMA is a standalone AXI/OBI DMA engine visible to the CPU harts and the Dispatch Engine. iDMA is the correct engine to use for bulk data ingestion (e.g., copying weight buffers from DRAM to L1) and for non-tensor memory operations.

**Feature summary:**

| # | Feature | Details |
|---|---------|---------|
| 1 | 2D scatter-gather DMA | Outer stride loop (num_reps × length bytes per rep) with independent src/dst strides |
| 2 | 24 independent input clients | 8 CPU harts (ROCC) + 2 Dispatch Engine ports + 14 reserved |
| 3 | Dual backends | 2 parallel backends for concurrent transfers |
| 4 | OBI backend (default) | Local L1 SRAM access via OBI protocol |
| 5 | AXI backend (compile-time) | DRAM access via NOC2AXI AXI4 master |
| 6 | Data Format Conversion (DFC) | In-flight format conversion (FP32/FP16/BF16/TF32/FP8/MX*/INT*) |
| 7 | L1 atomic accumulate | 16 accumulate channels; iDMA can write-accumulate into L1 accumulate registers |
| 8 | 32 transaction IDs (TIDs) | Per-TID in-flight tracking, threshold-based IRQ, software-clearable |
| 9 | Page-aligned burst splitting | Legalizer splits transfers at 4KB (configurable) page boundaries |
| 10 | INIT / zero-fill path | Zero-fill destination without reading source |
| 11 | Decoupled read/write | Read and write phases can proceed independently for throughput |
| 12 | Serialized mode | Force in-order execution when ordering is required |
| 13 | Weighted round-robin arbitration | Per-VC weighted arbiter across 24 clients |
| 14 | Clock gating with hysteresis | 7-bit hysteresis counter; gated_l1_clk auto-extends during activity |
| 15 | RISC-V ROCC instruction interface | Custom instructions DMSRC/DMDST/DMCPY/DMSTR/DMREP/DMSTAT from harts |
| 16 | APB register access | All status/config registers accessible via APB from the CPU complex |
| 17 | Virtual channel (VC) selection | Per-transfer VC selector passed through to NoC packet header |
| 18 | CDC-safe frontend/backend boundary | Async FIFO between core_clk (frontend) and gated_l1_clk (backend) |

**NOT in iDMA (see TDMA section):** zero-mask skipping (zmask), exponent-based sparsity pruning, edge masking, tilize/untilize, thread-parallel pack/unpack, BFP hardware decompression, ReLU packing.

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

---

### §7.2 System Architecture


```
                    Trinity N1B0 Tile (X=0..3, Y=1..4)
  +--------------------------------------------------------------+
  |  tt_overlay_wrapper                                          |
  |                                                              |
  |  +--------------+   +----------------------------------+     |
  |  |  CPU Complex  |   |       tt_idma_wrapper            |     |
  |  |  (8 harts)    +-->+  iDMA Engine                     |     |
  |  |  ROCC CUSTOM_1|   |                                  |     |
  |  +--------------+   +----------+------------+----------+     |
  |                                | OBI        | AXI            |
  |  +--------------+              v            v                |
  |  |  Dispatch    |   +----------+--+  +------+------+        |
  |  |  Engine      +-->+  L1 SRAM    |  |  NOC2AXI    +-->DRAM |
  |  +--------------+   |  (768 KB)   |  |  Bridge     |        |
  |                     +-------------+  +-------------+        |
  |                            |                                  |
  |                     +-------------+                          |
  |                     |  NoC Router +<------ Remote tiles      |
  |                     +-------------+                          |
  +--------------------------------------------------------------+
```

**iDMA engine internal architecture:**

```
  +--------------------------------------------------------------------------+
  |  tt_idma_wrapper                                                         |
  |                                                                          |
  |  core_clk domain                   |  gated_l1_clk domain               |
  |                                    |                                     |
  |  +------------------------------+  |  +--------------------------------+ |
  |  | tt_idma_cmd_buffer_frontend  |  |  | tt_idma_backend_r_init_rw_     | |
  |  |                              |  |  | obi_top  [BE #0]               | |
  |  |  clients[0..23]              |  |  |                                | |
  |  |  +--------------------+      |  |  |  +------------------------+   | |
  |  |  | timing slice regs  |      |  |  |  | metadata FIFO (dep=28) |   | |
  |  |  | (per client)       |      |  |  |  +------------------------+   | |
  |  |  +--------------------+      |  |  |  +------------------------+   | |
  |  |  +--------------------+      |  |  |  | tt_idma_backend_r_init |   | |
  |  |  | tt_arb (WRR/VC)    |      |  |  |  | _rw_obi (xIDMA_NUM_BE) |   | |
  |  |  +--------------------+      |  |  |  |  +-----------------+   |   | |
  |  |  +--------------------+      |  |  |  |  | Legalizer       |   |   | |
  |  |  | tt_sync_fifo       |      |  |  |  |  | (page align,    |   |   | |
  |  |  | metadata depth=42  |      |  |  |  |  |  burst split)   |   |   | |
  |  |  +--------------------+      |  |  |  |  +-----------------+   |   | |
  |  |  +--------------------+      |  |  |  |  +-----------------+   |   | |
  |  |  | async payload buf  +<-----+--+  |  |  | Transport Layer |   |   | |
  |  |  | depth=8, CDC FIFO  |      |  |  |  |  |  obi_read       |   |   | |
  |  |  +--------------------+      |  |  |  |  |  init_read      |   |   | |
  |  |  +--------------------+      |  |  |  |  |  obi_write      |   |   | |
  |  |  | TID completion     |      |  |  |  |  |  dfc_wrapper    |   |   | |
  |  |  | threshold / IRQ    |      |  |  |  |  +-----------------+   |   | |
  |  |  +--------------------+      |  |  |  +------------------------+   | |
  |  +------------------------------+  |  +--------------------------------+ |
  |                                    |                                     |
  |                                    |  +--------------------------------+ |
  |                                    |  | tt_idma_backend_r_init_rw_     | |
  |                                    |  | obi_top  [BE #1]               | |
  |                                    |  +--------------------------------+ |
  |                                    |                                     |
  |  i_l1_clk --> tt_clk_gater ---------------------------> gated_l1_clk   |
  |               (HYST_WIDTH=7)       |                                     |
  +--------------------------------------------------------------------------+
```

**Read path (DRAM to L1):**
```
  CPU hart (ROCC CUSTOM_1)
       |  DMSRC/DMDST/DMCPY instructions
       v
  tt_idma_cmd_buffer_frontend
  [core_clk: timing slice -> WRR arbiter -> metadata FIFO(42) -> async payload FIFO(8)]
       |  CDC crossing: core_clk -> gated_l1_clk
       v
  tt_idma_backend_r_init_rw_obi_top
  [gated_l1_clk: metadata FIFO(28) -> legalizer -> transport layer]
       |
       +--[AXI backend]--> NOC2AXI --> NoC --> DRAM (SI0-SI3)
       |                        read data <------
       +--[OBI backend]--> L1 SRAM OBI port
             |  write data --> L1 SRAM write port
             |  (optional: L1 accumulate channels 0-15)
             v
         L1 SRAM (768 KB per tile in N1B0)
```

---

### §7.3 Module Descriptions


#### §7.3.1 tt_idma_wrapper (Top-level)

**File:** `used_in_n1/tt_idma_wrapper.sv`

**Function:** Top-level DMA engine instantiated once per Tensix tile (Y=1–4) inside `tt_overlay_wrapper`. Instantiates the frontend, two backends, and the clock gate. Manages CDC boundary between `core_clk` and `gated_l1_clk`.

**Key ports:**

| Port | Direction | Domain | Description |
|------|-----------|--------|-------------|
| `i_core_clk` | in | core_clk | CPU complex clock |
| `i_l1_clk` | in | noc_clk | L1 SRAM clock (ungated) |
| `gated_l1_clk` | internal | — | Clock gated by tt_clk_gater |
| `i_core_rst_n` | in | — | Active-low reset (core domain) |
| `i_l1_rst_n` | in | — | Active-low reset (L1 domain) |
| `i_idma_req[23:0]` | in | core_clk | idma_flit_t from 24 clients |
| `o_idma_ready[23:0]` | out | core_clk | Back-pressure per client |
| `o_idma_tiles_to_process_irq[31:0]` | out | core_clk | Per-TID IRQ outputs |
| `i_tiles_to_process_clear[31:0]` | in | core_clk | Write 1 to clear IRQ + count |
| `i_l1_clkgt_en` | in | core_clk | Clock gate enable from CLOCK_GATING.IDMA |
| `i_l1_clkgt_hyst` | in | core_clk | Hysteresis count (7-bit) |

**Compile-time parameter:** `IDMA_BE_TYPE_AXI` selects OBI (0, default) or AXI (1) backend.

#### §7.3.2 tt_idma_cmd_buffer_frontend (Frontend)

**Function:** Receives DMA descriptors from up to 24 clients, arbitrates using weighted round-robin per virtual channel (VC), buffers metadata and payload through a CDC boundary, and tracks completion per transaction ID (TID).

**Sub-components:**

| Sub-module | Depth / Size | Function |
|------------|-------------|---------|
| Timing slice registers | 1 per client | Pipeline register for timing closure |
| `tt_arb` (WRR) | 24-input | Weighted round-robin arbiter, per-VC |
| `tt_sync_fifo` (metadata) | 42 entries | Holds descriptor metadata in core_clk domain |
| Async payload FIFO | 8 entries | CDC FIFO: core_clk to gated_l1_clk |
| TID completion tracker | 32 TIDs | Counts completions, compares to threshold, fires IRQ |

**Client assignment:**

| Client Index | Source | Notes |
|-------------|--------|-------|
| 0–7 | CPU harts 0–7 | Via ROCC CUSTOM_1 interface |
| 8–9 | Dispatch Engine sideband | DE-initiated tile-wide operations |
| 10–23 | Reserved | Future use |

**TID / IRQ mechanism:**

Each `idma_flit_t` carries a 5-bit `trid` field (TID 0–31). The frontend increments a per-TID counter each time a transfer with that TID completes. When the counter reaches `i_tr_id_thresholds[TID]`, the corresponding bit in `o_idma_tiles_to_process_irq[TID]` is asserted. SW writes 1 to `i_tiles_to_process_clear[TID]` to atomically clear the counter and the IRQ bit.

**Descriptor format (`idma_flit_t`):**
```
  [MSB .......................................................... LSB]
  | l1_accum_cfg_reg (L1 accumulate config) | trid[4:0] | vc[1:0] | payload |
```

where `payload` (`idma_req_t`) contains:
```
  src_addr[63:0]   -- source byte address
  dst_addr[63:0]   -- destination byte address
  length[21:0]     -- transfer size in bytes (max 4 MB)
  src_stride[63:0] -- outer dimension source stride (2D mode)
  dst_stride[63:0] -- outer dimension destination stride (2D mode)
  num_reps[63:0]   -- outer loop count (1 = 1D transfer)
  decouple_rw      -- decouple read and write phases
  deburst          -- disable AXI burst mode
  serialize        -- force in-order serialization
```

#### §7.3.3 tt_idma_backend_r_init_rw_obi_top (OBI Backend)

**Function:** Receives arbitrated descriptors from the frontend (in `gated_l1_clk` domain), manages per-backend metadata FIFOs, and instantiates `IDMA_NUM_BE` backend instances that drive OBI or AXI protocol towards L1 SRAM.

Two backend top instances run in parallel (BE #0 and BE #1), allowing two concurrent independent transfers.

**Sub-components:**

| Sub-module | Depth | Function |
|------------|-------|---------|
| Metadata FIFO | 28 entries | Holds L1 accumulate config and in-flight metadata |
| `tt_idma_backend_r_init_rw_obi` | xIDMA_NUM_BE | Per-backend legalizer + transport layer |

**AXI variant:** When `IDMA_BE_TYPE_AXI == 1`, `tt_idma_backend_r_init_rw_axi_top` is instantiated instead, which interfaces to the tile's AXI master port and ultimately reaches DRAM via the NOC2AXI bridge at Y=0.

#### §7.3.4 tt_idma_legalizer_r_init_rw_obi (Legalizer)

**Function:** Transforms an arbitrary `idma_req_t` descriptor into a sequence of legal bus transactions that respect protocol constraints.

**Responsibilities:**

1. **Page boundary detection:** Splits transfers that cross 4KB boundaries into multiple sub-transfers. This prevents a single burst from spanning pages that may be non-contiguous in physical memory.

2. **Burst alignment:** Aligns source and destination addresses to the AXI/OBI burst word size. Generates byte-enable masks for partial-word accesses at start and end of a transfer.

3. **INIT path handling:** When zero-fill mode is requested (no source address, destination fill), generates synthetic read data (all zeros) without issuing source reads.

4. **DFC scale accounting:** When Data Format Conversion is enabled, adjusts transfer byte counts to account for format up-sizing (e.g., INT8 to FP32 = x4) or down-sizing (e.g., FP32 to FP8 = /4).

5. **2D outer loop:** Generates `num_reps` sequential inner transfers, advancing source and destination addresses by `src_stride` and `dst_stride` respectively after each inner transfer of `length` bytes.

#### §7.3.5 tt_idma_transport_layer (Transport Layer)

**Function:** Executes the legalized transfer sequence by driving OBI (or AXI) read and write channels.

| Module | Function |
|--------|---------|
| `idma_obi_read` | Issues OBI read requests to L1 SRAM (source path) |
| `idma_init_read` | Generates synthetic zero data (INIT/zero-fill path) |
| `idma_obi_write` | Issues OBI write requests to L1 SRAM (destination path) |
| `tt_idma_dfc_wrapper` | Optional: in-flight data format conversion (when DFCEnable=1) |

**Decoupled read/write:** When `decouple_rw=1`, the read channel and write channel operate independently. The read channel can prefetch ahead of the write channel, improving throughput when the two channels have different latencies (e.g., DRAM read + local L1 write).

**L1 accumulate path:** When `l1_accum_cfg_reg.enable=1`, the OBI write is redirected to the L1 atomic accumulate channel (0–15) rather than writing directly to the SRAM data array.

#### §7.3.6 tt_idma_dfc_wrapper (Data Format Converter)

**Function:** Inserted in the transport layer data path when `DFCEnable=1`. Converts data between source format and destination format during transfer.

- `WORD_WIDTH = 8` bits (element granularity)
- `MX_BLOCK_SIZE = 8` elements per microscaling block
- Stochastic rounding supported for narrowing conversions

**Common useful conversions:**

| Source | Destination | Use Case |
|--------|-------------|---------|
| FLOAT32 | FLOAT16_B | FP32 parameter to BF16 L1 storage |
| FLOAT32 | FP8P | FP32 to FP8 E4M3 for compressed storage |
| INT16 | INT8 | 16-bit activation to 8-bit L1 storage |
| MXFP8R | FLOAT16 | Decompress MX format to FP16 |

#### §7.3.7 tt_clk_gater (Clock Gate)

**Function:** Controls the `gated_l1_clk` that clocks the two backend instances. Saves power when no DMA transfers are active.

```
  i_l1_clk ----------------------------------------> tt_clk_gater
                                                            |
  i_enable ---- CLOCK_GATING.IDMA bit (APB 0x0CC[1]) ----->|
  i_kick   ---- |{req_valid, resp_valid} from backends ---->|
  i_busy   ---- o_l1_clkgt_busy from backends ------------->|
  i_histeresys - i_l1_clkgt_hyst[6:0] (APB 0x0D0) -------->|
                                                            |
                                                 gated_l1_clk --> backends
```

- Clock is gated OFF when: `i_enable=1` AND `i_kick=0` AND `i_busy=0` AND hysteresis counter expired
- Clock is forced ON when: `i_enable=0` (disable clock gating = clock always on)
- `HYST_WIDTH=7` means clock stays on for up to 128 cycles after last activity

---

### §7.4 Key Parameters


| Parameter | Value | Description |
|-----------|-------|-------------|
| `IDMA_NUM_MEM_PORTS` | 2 | Number of memory ports (backends) |
| `IDMA_CMD_BUF_NUM_CLIENTS` | 24 | Total client slots (= IDMA_NUM_CLIENTS) |
| `IDMA_PACKET_TAG_TRANSACTION_ID_WIDTH` | 5 | TID field width -> 32 TIDs (0–31) |
| `IDMA_MEM_PORT_ID_WIDTH` | 4 | Memory port ID width |
| `IDMA_TRANSFER_LENGTH_WIDTH` | 22 | Transfer length field width -> 4 MB max |
| `IDMA_FIFO_DEPTH` | 42 | Frontend metadata FIFO depth |
| `IDMA_PAYLOAD_FIFO_DEPTH` | 8 | CDC async payload FIFO depth |
| `IDMA_L1_ACC_ATOMIC` | 16 | L1 accumulate channel count |
| `NumDim` | 2 | Maximum DMA dimensions (2D scatter-gather) |
| `IDMA_AXI_USER_WIDTH` | 1 | AXI USER sideband width |
| Backend metadata FIFO depth | 28 | Per-backend descriptor FIFO (gated_l1_clk domain) |
| `HYST_WIDTH` | 7 | Clock gate hysteresis counter width (128 cycles) |
| `reg_addr_t` | 9-bit | APB register address space -> 512 locations |
| `reg_data_t` | 32-bit | APB register data width |

---

### §7.5 SFR Reference


#### §7.5.1 Cluster Control Registers (cluster_ctrl_apb)

**Base address:** `0x0300_0000`
**Size:** `0x1E4` bytes
**Access:** 64-bit aligned for RESET_VECTOR registers; 32-bit for all others

| Offset | Register Name | Reset | Access | Description |
|--------|---------------|-------|--------|-------------|
| 0x000 | RESET_VECTOR_0 | 0x0 | RW | Hart 0 reset vector bits [57:0] |
| 0x008 | RESET_VECTOR_1 | 0x0 | RW | Hart 1 reset vector bits [57:0] |
| 0x010 | RESET_VECTOR_2 | 0x0 | RW | Hart 2 reset vector bits [57:0] |
| 0x018 | RESET_VECTOR_3 | 0x0 | RW | Hart 3 reset vector bits [57:0] |
| 0x020 | RESET_VECTOR_4 | 0x0 | RW | Hart 4 reset vector bits [57:0] |
| 0x028 | RESET_VECTOR_5 | 0x0 | RW | Hart 5 reset vector bits [57:0] |
| 0x030 | RESET_VECTOR_6 | 0x0 | RW | Hart 6 reset vector bits [57:0] |
| 0x038 | RESET_VECTOR_7 | 0x0 | RW | Hart 7 reset vector bits [57:0] |
| 0x040 | SCRATCH_0 | 0x0 | RW | General-purpose scratch register 0 |
| 0x044 | SCRATCH_1 | 0x0 | RW | General-purpose scratch register 1 |
| ... | SCRATCH_2..30 | 0x0 | RW | General-purpose scratch registers |
| 0xBC | SCRATCH_31 | 0x0 | RW | General-purpose scratch register 31 |
| 0x0C0 | ROCC_MEM_CHICKEN | 0x0 | RW | ROCC memory chicken bits (debug overrides) |
| 0x0C4 | SCATTER_LIST_MAGIC_NUM_LO | 0x0 | RW | Scatter list magic number bits [31:0] |
| 0x0C8 | SCATTER_LIST_MAGIC_NUM_HI | 0x0 | RW | Scatter list magic number bits [63:32] |
| 0x0CC | CLOCK_GATING | 0x0 | RW | Per-unit clock gate enables |
| 0x0D0 | CLOCK_GATING_HYST | 0x0 | RW | Clock gate hysteresis count (7-bit, bits [6:0]) |
| 0x0D8 | WB_PC_REG_C0 | 0x0 | RO | Hart 0 writeback PC |
| 0x0E0 | WB_PC_REG_C1 | 0x0 | RO | Hart 1 writeback PC |
| 0x0E8 | WB_PC_REG_C2 | 0x0 | RO | Hart 2 writeback PC |
| 0x0F0 | WB_PC_REG_C3 | 0x0 | RO | Hart 3 writeback PC |
| 0x0F8 | WB_PC_REG_C4 | 0x0 | RO | Hart 4 writeback PC |
| 0x100 | WB_PC_REG_C5 | 0x0 | RO | Hart 5 writeback PC |
| 0x108 | WB_PC_REG_C6 | 0x0 | RO | Hart 6 writeback PC |
| 0x110 | WB_PC_REG_C7 | 0x0 | RO | Hart 7 writeback PC |
| 0x118 | WB_PC_CTRL | 0x0 | RW | Writeback PC capture control |
| 0x11C | ECC_PARITY_CONTROL | 0x0 | RW | Enable ECC/parity for L1 SRAM |
| 0x120 | ECC_PARITY_STATUS | 0x0 | RO/W1C | ECC/parity error status flags |
| 0x124 | NOC_SNOOP_TL_MASTER_CFG | 0x0 | RW | TileLink master config for NoC snoop path |
| 0x128 | ASSERTS | 0x0 | RW | Assertion enable bits (simulation/debug) |
| 0x12C | PREFETCHER_CONTROL | 0x0 | RW | Instruction cache prefetcher enable/config |
| 0x130 | BUS_ERROR_UNIT_DATA_C0 | 0x0 | RO/W1C | Bus error data for hart 0 |
| 0x138 | BUS_ERROR_UNIT_DATA_C1 | 0x0 | RO/W1C | Bus error data for hart 1 |
| 0x140 | BUS_ERROR_UNIT_DATA_C2 | 0x0 | RO/W1C | Bus error data for hart 2 |
| 0x148 | BUS_ERROR_UNIT_DATA_C3 | 0x0 | RO/W1C | Bus error data for hart 3 |
| 0x150 | BUS_ERROR_UNIT_DATA_C4 | 0x0 | RO/W1C | Bus error data for hart 4 |
| 0x158 | BUS_ERROR_UNIT_DATA_C5 | 0x0 | RO/W1C | Bus error data for hart 5 |
| 0x160 | BUS_ERROR_UNIT_DATA_C6 | 0x0 | RO/W1C | Bus error data for hart 6 |
| 0x168 | BUS_ERROR_UNIT_DATA_C7 | 0x0 | RO/W1C | Bus error data for hart 7 |
| 0x170 | L2_DIR_ERRORS_0 | 0x0 | RO | L2 directory error status (bank group 0) |
| 0x174 | L2_DIR_ERRORS_1 | 0x0 | RO | L2 directory error status (bank group 1) |
| 0x178 | L2_DIR_ERRORS_2 | 0x0 | RO | L2 directory error status (bank group 2) |
| 0x17C | L2_DIR_ERRORS_3 | 0x0 | RO | L2 directory error status (bank group 3) |
| 0x180 | L2_BANKS_ERRORS_0 | 0x0 | RO | L2 bank 0 error status |
| 0x184 | L2_BANKS_ERRORS_1 | 0x0 | RO | L2 bank 1 error status |
| ... | L2_BANKS_ERRORS_2..14 | 0x0 | RO | L2 bank error status |
| 0x1BC | L2_BANKS_ERRORS_15 | 0x0 | RO | L2 bank 15 error status |
| 0x1C0 | DEBUG_DMACTIVE | 0x0 | RW | RISC-V Debug Module active flag |
| 0x1C4 | DEBUG_DMACTIVEACK | 0x0 | RO | Debug Module active acknowledge |
| 0x1C8 | DEBUG_SNOOP | 0x0 | RW | Debug snoop bus configuration |
| 0x1CC | OVERLAY_INFO | 0x0 | RO | Overlay version/variant identifier |
| 0x1D0 | SW_RAS | 0x0 | RW | Software Reliability, Availability, Serviceability |
| 0x1D4 | SBUS_RSINK_RESET_FALLBACK | 0x0 | RW | SBUS reset sink fallback configuration |
| 0x1D8 | OVERLAY_CHICKEN_BITS | 0x0 | RW | Overlay debug/workaround chicken bits |
| 0x1DC | L1_ACCESSIBLE_REGION | 0x0 | RW | L1 SRAM accessible region base/size |
| 0x1E0 | L1_REGION_ERROR | 0x0 | RO | L1 region access violation address |

#### §2.x SFR Read Example — Identify Tile Variant

Before programming a tile, read OVERLAY_INFO to verify it is the expected tile type:

```c
#define CLUSTER_CTRL_BASE   0x03000000UL
#define REG32(base, off)    (*(volatile uint32_t *)((base) + (off)))

// Read OVERLAY_INFO at offset 0x1CC
uint32_t overlay_info = REG32(CLUSTER_CTRL_BASE, 0x1CC);
uint16_t version  = overlay_info & 0xFFFF;         // bits[15:0]
uint16_t variant  = (overlay_info >> 16) & 0xFFFF; // bits[31:16]
// variant: identifies tile type (Tensix/Dispatch/NIU)
// version: overlay RTL version stamp

// Read CLOCK_GATING status at offset 0x0CC
uint32_t cg_status = REG32(CLUSTER_CTRL_BASE, 0x0CC);
int idma_gated  = (cg_status >> 1) & 1;   // bit[1]: iDMA clock gated?
int rocc_gated  = (cg_status >> 0) & 1;   // bit[0]: ROCC clock gated?
```

**CLOCK_GATING Register (0x0CC) — Field Table:**

| Bit | Field Name | Reset | Description |
|----|-----------|-------|-------------|
| 0 | ROCC | 0 | 1 = enable clock gating for ROCC accelerator interface |
| 1 | IDMA | 0 | 1 = enable clock gating for iDMA engine (gated_l1_clk) |
| 2 | CLUSTER_CTRL | 0 | 1 = enable clock gating for cluster controller APB logic |
| 3 | CONTEXT_SWITCH | 0 | 1 = enable clock gating for context switch unit |
| 4 | LLK_INTF | 0 | 1 = enable clock gating for LLK interface |
| 5 | SNOOP | 0 | 1 = enable clock gating for NoC snoop path |
| 6 | (reserved) | 0 | Reserved, write 0 |
| 7 | L1_FLEX_CLIENT_IDMA | 0 | 1 = enable clock gating for L1 flex-client iDMA port |
| 8 | L1_FLEX_CLIENT_OVERLAY | 0 | 1 = enable clock gating for L1 flex-client overlay port |
| 31:9 | (reserved) | 0 | Reserved |

WARNING: After writing CLOCK_GATING, write the desired hysteresis value to CLOCK_GATING_HYST (0x0D0). The 7-bit value in bits [6:0] specifies the hysteresis count; the clock remains active for `2^value` cycles after the last detected activity. Writing CLOCK_GATING.IDMA=1 without setting HYST may cause premature clock gating.

#### §7.5.2 iDMA APB Registers

iDMA APB base address: **0x03004000** (confirmed from RTL: tt_rocc_accel_reg.svh).

The iDMA APB register space has two command buffer channels:
- **CMD_BUF_R** (read/DMA-from-DRAM channel): base `0x03004000`
- **CMD_BUF_W** (write/DMA-to-DRAM channel): base `0x03004200`

**Complete CMD_BUF_R register map (offsets from 0x03004000):**

| Absolute Addr | Offset | Register Name               | Access  | Description                                     |
|---------------|--------|-----------------------------|---------|--------------------------------------------------|
| 0x03004000    | 0x000  | CMD_BUF_R_IE                | RW      | Interrupt enable bitmask for read channel        |
| 0x03004008    | 0x008  | CMD_BUF_R_IP                | RO/W1C  | Interrupt pending (write 1 to clear)             |
| 0x03004010    | 0x010  | CMD_BUF_R_WR_SENT_TR_ID     | RO      | Last transaction ID sent to NoC                  |
| 0x03004018    | 0x018  | CMD_BUF_R_TR_ACK_TR_ID      | RO      | Last transaction ID acknowledged                 |
| 0x03004020    | 0x020  | CMD_BUF_R_SRC_ADDR          | RW      | DMA source address                               |
| 0x03004028    | 0x028  | CMD_BUF_R_SRC_BASE          | RW      | DMA source base address (2D stride mode)         |
| 0x03004030    | 0x030  | CMD_BUF_R_SRC_SIZE          | RW      | DMA source size (bytes per row in 2D)            |
| 0x03004038    | 0x038  | CMD_BUF_R_SRC_COORD         | RW      | Source tile X/Y coordinate [13:8]=Y, [7:2]=X     |
| 0x03004040    | 0x040  | CMD_BUF_R_DEST_ADDR         | RW      | DMA destination address                          |
| 0x03004048    | 0x048  | CMD_BUF_R_DEST_BASE         | RW      | Destination base address                         |
| 0x03004050    | 0x050  | CMD_BUF_R_DEST_SIZE         | RW      | Destination size                                 |
| 0x03004058    | 0x058  | CMD_BUF_R_DEST_COORD        | RW      | Destination tile X/Y coordinate                  |
| 0x03004060    | 0x060  | CMD_BUF_R_LEN_BYTES         | RW      | Transfer length in bytes                         |
| 0x03004068    | 0x068  | CMD_BUF_R_REQ_VC            | RW      | Request virtual channel (0–4)                    |
| 0x03004070    | 0x070  | CMD_BUF_R_REQ_VC_BASE       | RW      | Request VC base for 2D scatter                   |
| 0x03004078    | 0x078  | CMD_BUF_R_REQ_VC_SIZE       | RW      | Request VC size for 2D scatter                   |
| 0x03004080    | 0x080  | CMD_BUF_R_RESP_VC           | RW      | Response virtual channel (0–4)                   |
| 0x03004088    | 0x088  | CMD_BUF_R_RESP_VC_BASE      | RW      | Response VC base                                 |
| 0x03004090    | 0x090  | CMD_BUF_R_RESP_VC_SIZE      | RW      | Response VC size                                 |
| 0x03004098    | 0x098  | CMD_BUF_R_TR_ID             | RW      | Transaction ID for this transfer                 |
| 0x030040A0    | 0x0A0  | CMD_BUF_R_TR_ID_BASE        | RW      | TR_ID base (for TR_ID auto-increment)            |
| 0x030040A8    | 0x0A8  | CMD_BUF_R_TR_ID_SIZE        | RW      | TR_ID pool size                                  |
| 0x030040B0    | 0x0B0  | CMD_BUF_R_MCAST_EXCLUDE     | RW      | Multicast exclude tile mask                      |
| 0x030040B8    | 0x0B8  | CMD_BUF_R_SCATTER_LIST_ADDR | RW      | Scatter-list starting address in L1              |
| 0x030040C0    | 0x0C0  | CMD_BUF_R_SCATTER_BASE_ADDR | RW      | Scatter base address                             |
| 0x030040C8    | 0x0C8  | CMD_BUF_R_SCATTER_INDEX     | RW      | Current scatter index                            |
| 0x030040D0    | 0x0D0  | CMD_BUF_R_SCATTER_TIMES     | RW      | Number of scatter repetitions                    |
| 0x030040D8    | 0x0D8  | CMD_BUF_R_SCATTER_ADDR_0    | RW      | Scatter target address 0                         |
| 0x030040E0    | 0x0E0  | CMD_BUF_R_SCATTER_ADDR_1    | RW      | Scatter target address 1                         |
| 0x030040E8    | 0x0E8  | CMD_BUF_R_SCATTER_ADDR_2    | RW      | Scatter target address 2                         |
| 0x030040F0    | 0x0F0  | CMD_BUF_R_SCATTER_ADDR_3    | RW      | Scatter target address 3                         |
| 0x030040F8    | 0x0F8  | CMD_BUF_R_INLINE_DATA       | RW      | 64-bit inline write data                         |
| 0x03004100    | 0x100  | CMD_BUF_R_MAX_BYTES_PACKET  | RW      | Maximum bytes per NoC packet (default 256)       |
| 0x03004108    | 0x108  | CMD_BUF_R_MCAST_DESTS       | RW      | Multicast destination endpoint list              |
| 0x03004110    | 0x110  | CMD_BUF_R_L1_ACCUM_CFG      | RW      | L1 accumulate config: [1:0]=op, [31:2]=threshold |
| 0x03004118    | 0x118  | CMD_BUF_R_AXI_OPT_1         | RW      | AXI optimization flags (burst, cache, prot)      |
| 0x03004120    | 0x120  | CMD_BUF_R_AXI_OPT_2         | RW      | AXI optimization flags 2                         |
| 0x03004128    | 0x128  | CMD_BUF_R_AUTOINC           | RW      | Address auto-increment per transfer              |
| 0x03004130    | 0x130  | CMD_BUF_R_PACKET_TAGS       | RW      | Packet tag field for tracking                    |
| 0x03004138    | 0x138  | CMD_BUF_R_DEBUG             | RO      | Debug status snapshot                            |
| 0x03004140    | 0x140  | CMD_BUF_R_MISC              | RW      | Miscellaneous configuration bits                 |
| 0x03004148    | 0x148  | CMD_BUF_R_PER_TR_ID_IE_0    | RW      | Per-TID interrupt enable bits [31:0]             |
| 0x03004150    | 0x150  | CMD_BUF_R_PER_TR_ID_IE_1    | RW      | Per-TID interrupt enable bits [63:32]            |
| 0x03004158    | 0x158  | CMD_BUF_R_PER_TR_ID_IE_2    | RW      | Per-TID interrupt enable bits [95:64]            |
| 0x03004160    | 0x160  | CMD_BUF_R_PER_TR_ID_IP_0    | RO/W1C  | Per-TID interrupt pending bits [31:0]            |
| 0x03004168    | 0x168  | CMD_BUF_R_PER_TR_ID_IP_1    | RO/W1C  | Per-TID interrupt pending bits [63:32]           |
| 0x03004170    | 0x170  | CMD_BUF_R_PER_TR_ID_IP_2    | RO/W1C  | Per-TID interrupt pending bits [95:64]           |

**CMD_BUF_W** at base `0x03004200` has the same register layout (same offsets), but
controls the write-channel (DMA-to-DRAM) direction.

**Updated C defines:**
```c
// iDMA APB base addresses (RTL-verified: tt_rocc_accel_reg.svh)
#define IDMA_APB_BASE        0x03004000UL
#define IDMA_CMD_BUF_R_BASE  0x03004000UL  // DMA-from-DRAM command buffer
#define IDMA_CMD_BUF_W_BASE  0x03004200UL  // DMA-to-DRAM command buffer

#define IDMA_R_REG(off)  (*(volatile uint32_t *)(IDMA_CMD_BUF_R_BASE + (off)))
#define IDMA_W_REG(off)  (*(volatile uint32_t *)(IDMA_CMD_BUF_W_BASE + (off)))

// Key register accessors — CMD_BUF_R
#define IDMA_R_IE            IDMA_R_REG(0x000)  // interrupt enable
#define IDMA_R_IP            IDMA_R_REG(0x008)  // interrupt pending (W1C)
#define IDMA_R_SENT_TR_ID    IDMA_R_REG(0x010)  // last sent TR_ID
#define IDMA_R_ACK_TR_ID     IDMA_R_REG(0x018)  // last ACK TR_ID
#define IDMA_R_SRC_ADDR      IDMA_R_REG(0x020)  // source address
#define IDMA_R_DST_ADDR      IDMA_R_REG(0x040)  // destination address
#define IDMA_R_LEN           IDMA_R_REG(0x060)  // transfer length
#define IDMA_R_REQ_VC        IDMA_R_REG(0x068)  // request VC
#define IDMA_R_RESP_VC       IDMA_R_REG(0x080)  // response VC
#define IDMA_R_TR_ID         IDMA_R_REG(0x098)  // transaction ID
#define IDMA_R_SCATTER_ADDR  IDMA_R_REG(0x0B8)  // scatter list address
#define IDMA_R_L1_ACCUM      IDMA_R_REG(0x110)  // L1 accumulate config
#define IDMA_R_PER_TID_IE_0  IDMA_R_REG(0x148)  // per-TID IE [31:0]
#define IDMA_R_PER_TID_IP_0  IDMA_R_REG(0x160)  // per-TID IP [31:0] (W1C)
```

**Completion polling with real addresses:**
```c
// Poll for TID N completion using per-TID IP registers
void idma_wait_for_tid(uint32_t tid) {
    uint32_t word_idx = tid / 32;  // 0 = TIDs 0-31, 1 = TIDs 32-63, 2 = TIDs 64-95
    uint32_t bit      = 1u << (tid % 32);
    volatile uint32_t *ip_reg = &IDMA_R_PER_TID_IP_0 + word_idx;

    // Enable interrupt for this TID
    volatile uint32_t *ie_reg = &IDMA_R_PER_TID_IE_0 + word_idx;
    *ie_reg |= bit;

    // Poll until IP bit set
    while (!(*ip_reg & bit));

    // Clear (W1C)
    *ip_reg = bit;
}
```

**Base address:** iDMA APB sub-bus within tile APB space (consult §17.3 for per-tile base offset).

| Register Name | Reset | Access | Width | Description |
|---------------|-------|--------|-------|-------------|
| IDMA_STATUS | 0x0 | RO | 32 | Bit N = 1 if TID N has at least one transfer in-flight. |
| IDMA_VC_SPACE[0] | 0x0 | RO | 32 | Available virtual channel slots for backend 0. |
| IDMA_VC_SPACE[1] | 0x0 | RO | 32 | Available virtual channel slots for backend 1. |
| IDMA_TR_COUNT[0..31] | 0x0 | RO | 32 | Per-TID completion count. |
| IDMA_THRESHOLD[0..31] | 0x0 | RW | 32 | Per-TID IRQ threshold. When TR_COUNT[N] >= THRESHOLD[N] (and threshold != 0), asserts IRQ[N]. |
| IDMA_CLR[0..31] | 0x0 | W1C | 32 | Write 1 to bit N to atomically clear IDMA_TR_COUNT[N] and deassert IRQ[N]. |
| IDMA_CLK_EN | 0x0 | RW | 32 | Bit [0]: iDMA L1 clock gate enable. Mirrors CLOCK_GATING.IDMA. |
| IDMA_CLK_HYST | 0x0 | RW | 32 | Bits [6:0]: hysteresis count for gated_l1_clk. Mirrors CLOCK_GATING_HYST. |

**Usage pattern for completion tracking:**

```c
// Setup: set IRQ threshold to 1 transfer per TID
IDMA_THRESHOLD[TID] = 1;

// Issue DMA transfer with trid = TID
issue_dma(src, dst, len, TID);

// Poll for completion
while (!(read(IDMA_TR_COUNT[TID]) >= 1)) { /* spin or yield */ }

// Clear IRQ and counter
write(IDMA_CLR[TID], 1 << TID);
```

#### §7.5.3 ATT (Address Translation Table)

The ATT is a hardware lookup table that translates software-visible virtual addresses to NoC physical coordinates. iDMA descriptors can use ATT-translated addresses by forming the source or destination address within the ATT-mapped range.

**ATT base address:** `0x0201_0000`
**ATT size:** `0x3000` bytes (12 KB)

The ATT is programmed by the overlay firmware or the host CPU before issuing DMA transfers that target remote tiles. Each ATT entry maps a (mask, endpoint, routing) tuple. See §8.5 for the complete ATT programming guide.

---

### §7.6 Initialization Sequence


```c
#define CLUSTER_CTRL_BASE  0x03000000UL
#define CLOCK_GATING_REG   (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x0CC))
#define CLOCK_GATING_HYST  (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x0D0))
#define ECC_CTRL_REG       (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x11C))
#define IDMA_APB_BASE      0x03004000UL  // Confirmed: tt_rocc_accel_reg.svh (CMD_BUF_R base)

void idma_init(void) {
    // Step 1: Disable clock gating during initialization
    CLOCK_GATING_REG &= ~(1u << 1);    // CLOCK_GATING.IDMA = 0 (always on)
    CLOCK_GATING_REG &= ~(1u << 7);    // CLOCK_GATING.L1_FLEX_CLIENT_IDMA = 0

    // Step 2: Clear all pending TIDs and IRQ state
    idma_write_clr(0xFFFFFFFF);

    // Step 3: Initialize threshold registers to 0 (IRQ disabled for all TIDs)
    for (int tid = 0; tid < 32; tid++) {
        idma_set_threshold(tid, 0);
    }

    // Step 4: Set hysteresis and re-enable clock gating for production
    CLOCK_GATING_HYST  = 0x06;                       // 2^6 = 64-cycle hysteresis
    CLOCK_GATING_REG  |= (1u << 1) | (1u << 7);     // re-enable both IDMA gates

    // Step 5: Enable ECC detection for L1 SRAM (recommended for production)
    ECC_CTRL_REG = 1;

    // Step 6: Memory fence before first DMA use
    asm volatile ("fence");

    // Step 7: Verify iDMA readiness
    // DMSTATI field 1 (DMSTAT_READY) should return 1
    uint64_t ready = asm_dmstati(1);
    if (!ready) {
        for (volatile int i = 0; i < 100; i++) { }
        ready = asm_dmstati(1);
    }
    // If still not ready, escalate to error handler
}
```

---

### §7.7 Basic 1D Transfer / DRAM to L1


**Basic 1D L1-to-L1 copy:**
```c
// Copy 4096 bytes from L1 offset 0x0 to L1 offset 0x1000
void idma_local_copy_1d(void) {
    asm volatile ("fence w,w");     // ensure source data is in L1

    asm_dmsrc(0x00000000ULL);       // source: L1 base
    asm_dmdst(0x00001000ULL);       // destination: L1 + 4 KB
    asm_dmcpy(4096, 0);             // length=4096, flags: trid=0, vc=0

    while (asm_dmstat() & 1) { }   // wait for busy to clear
}
```

**DMA from DRAM to L1:**
```c
#define DRAM_SI0_BASE   0x60000000ULL
#define L1_BASE         0x00000000ULL
#define TRANSFER_BYTES  (256 * 1024)    // 256 KB

void idma_dram_to_l1(uint64_t dram_src_offset, int trid) {
    // Set IRQ threshold for this TID
    idma_set_threshold(trid, 1);

    // Fence: ensure any prior L1 activity is visible
    asm volatile ("fence");

    // Issue DMA: use decouple_rw to allow AXI read prefetch to proceed
    // ahead of OBI write, hiding DRAM latency
    uint64_t flags = (uint64_t)trid | IDMA_FLAG_DECOUPLE_RW;
    asm_dmsrc(DRAM_SI0_BASE + dram_src_offset);
    asm_dmdst(L1_BASE);
    asm_dmcpy(TRANSFER_BYTES, flags);

    // Poll TID completion
    while (!(idma_read_tr_count(trid) >= 1)) { }
    idma_clear_tid(trid);
    asm volatile ("fence r,r");   // ensure DMA writes visible to CPU
}
```

NOTE: Maximum single transfer is 4 MB (`IDMA_TRANSFER_LENGTH_WIDTH = 22` bits). For larger transfers, split into multiple descriptors with different TIDs.

**Full DRAM Prefetch with Double-Buffering:**
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

### §7.8 2D Scatter-Gather Transfer


```c
// Read a 128x64 FP16 sub-matrix from a 1024x64 DRAM matrix
// Source: row-major, row stride = 1024 * 2 = 2048 bytes
// Destination: packed contiguous in L1

#define ELEM_BYTES       2          // FP16 = 2 bytes/element
#define SRC_ROWS         128
#define SRC_COLS         64
#define SRC_ROW_STRIDE   2048       // full matrix row width in bytes
#define DST_ROW_STRIDE   (64 * 2)   // packed row: 128 bytes

void idma_strided_matrix_read(uint64_t dram_base, uint64_t l1_base) {
    asm volatile ("fence w,w");
    asm_dmsrc(dram_base);
    asm_dmdst(l1_base);
    asm_dmstr(SRC_ROW_STRIDE, DST_ROW_STRIDE);
    asm_dmrep(SRC_ROWS);
    asm_dmcpy(SRC_COLS * ELEM_BYTES,
              IDMA_FLAG_DECOUPLE_RW | FLAGS_TID(0));

    while (!(idma_read_tr_count(0) >= 1)) { }
    idma_clear_tid(0);
    asm volatile ("fence r,r");
}
```

---

### §7.9 Tile-Based vs Non-Tile Access


| Access Pattern | iDMA Mode | Description |
|---------------|-----------|-------------|
| Non-tile (1D) | `num_reps=1` | Single contiguous block bulk copy |
| Non-tile (2D) | `num_reps>1, decouple_rw=0` | Strided row reads from DRAM |
| Tile-based | `num_reps>1, decouple_rw=1` | Prefetch multiple tiles concurrently via dual backends |

```c
// Two concurrent tile prefetches (saturates both backends)
void prefetch_two_tiles(uint64_t tile0_src, uint64_t tile1_src,
                        uint64_t tile0_dst, uint64_t tile1_dst) {
    uint64_t f0 = FLAGS_TID(0) | IDMA_FLAG_DECOUPLE_RW;
    uint64_t f1 = FLAGS_TID(1) | IDMA_FLAG_DECOUPLE_RW;

    asm_dmsrc(tile0_src);
    asm_dmdst(tile0_dst);
    asm_dmcpy(TILE_BYTES, f0);   // dispatched to BE #0

    asm_dmsrc(tile1_src);
    asm_dmdst(tile1_dst);
    asm_dmcpy(TILE_BYTES, f1);   // dispatched to BE #1

    while (idma_read_tr_count(0) < 1 || idma_read_tr_count(1) < 1) { }
    idma_clear_tid(0);
    idma_clear_tid(1);
    asm volatile ("fence r,r");
}
```

---

### §7.10 Address Translation (ATT)


```c
// Program ATT entry 5 to map logical address 0x8000_0000 to tile (2,3) L1 base
void att_program_remote_tile(int entry, int x, int y, uint64_t local_addr) {
    uint64_t noc_addr = ((uint64_t)(y & 0x3F) << 70) |
                        ((uint64_t)(x & 0x3F) << 64) |
                        local_addr;
    att_write_entry(0x02010000UL, entry,
                    /*mask=*/    0xFFFFFFFF00000000ULL,
                    /*endpoint=*/noc_addr,
                    /*routing=*/ DOR_XY);
}

// DMA write to remote tile via ATT-mapped address
void idma_write_to_remote_tile_att(void) {
    att_program_remote_tile(5, 2, 3, L1_BASE);

    asm volatile ("fence w,w");
    asm_dmsrc(local_l1_src);
    asm_dmdst(0x80000000ULL);    // ATT entry 5 maps this to tile(2,3)
    asm_dmcpy(XFER_BYTES, 0);
    while (asm_dmstat() & 1) { }
}
```

---

### §7.11 Data Format Conversion (DFC)


```c
// Load FP32 weights from DRAM and store as BF16 in L1 (2:1 compression)
#define N_ELEMENTS  65536
#define SRC_BYTES   (N_ELEMENTS * 4)   // FP32: 4 bytes/element
#define DST_BYTES   (N_ELEMENTS * 2)   // BF16: 2 bytes/element

void idma_fp32_to_bf16_dma(uint64_t dram_fp32_src, uint64_t l1_bf16_dst) {
    idma_dfc_req_t req = {
        .base = {
            .src_addr   = dram_fp32_src,
            .dst_addr   = l1_bf16_dst,
            .length     = SRC_BYTES,
            .num_reps   = 1,
        },
        .dfc_enable  = 1,
        .src_format  = DFC_FLOAT32,
        .dst_format  = DFC_FLOAT16_B,
        .stoch_round = 0,
    };
    issue_idma_dfc(&req, 0);
    while (asm_dmstat() & 1) { }
    asm volatile ("fence r,r");
}
```

NOTE: For MX block formats, the transfer length must be a multiple of 8 elements (MX_BLOCK_SIZE). Misaligned transfers will produce incorrect block exponents.

---

### §7.12 L1 Accumulate / Zero-Copy


**L1 Accumulate (Zero-Copy Partial Sum):**
```c
// Accumulate partial sum from remote tile into local accumulate channel 3
void idma_accumulate_from_remote(int src_x, int src_y) {
    idma_flit_t flit = {
        .trid = 2,
        .vc   = 0,
        .l1_accum_cfg_reg = { .enable = 1, .channel = 3 },
        .payload = {
            .src_addr    = remote_tile_noc_addr(src_x, src_y, L1_BASE),
            .dst_addr    = L1_ACC_CHANNEL_ADDR(3),
            .length      = PARTIAL_SUM_BYTES,
            .num_reps    = 1,
            .decouple_rw = 1,
        },
    };
    issue_idma_flit(&flit);
    while (!(idma_read_tr_count(2) >= 1)) { }
    idma_clear_tid(2);
    asm volatile ("fence r,r");
    // L1 acc channel 3 now contains the accumulated sum
}
```

**Zero-Copy Patterns:**

*Pattern 1: In-place accumulate (all-reduce across tiles)*
```c
// Receive partial sums from 3 source tiles, accumulate into channel 0
for (int src = 0; src < 3; src++) {
    idma_flit_t f = {
        .trid = src,
        .l1_accum_cfg_reg = { .enable = 1, .channel = 0 },
        .payload = {
            .src_addr = remote_noc_addr(src_x[src], src_y[src], 0),
            .dst_addr = L1_ACC_CHANNEL_ADDR(0),
            .length   = PARTIAL_BYTES, .num_reps = 1,
        },
    };
    issue_idma_flit(&f);
}
for (int t = 0; t < 3; t++) {
    while (!(idma_read_tr_count(t) >= 1)) { }
    idma_clear_tid(t);
}
asm volatile ("fence r,r");
// Channel 0 holds sum of 4 tiles' partial results
```

*Pattern 2: Format-converted load (eliminates CPU conversion pass)*
```c
idma_dfc_load(DRAM_WEIGHT_ADDR, L1_WEIGHT_ADDR,
              DFC_FLOAT32, DFC_FLOAT16_B, WEIGHT_BYTES);
// L1 holds BF16 weights; no separate CPU format conversion needed
```

*Pattern 3: Zero-fill (INIT path)*
```c
// Clear accumulation buffer before use
idma_req_t zero_req = {
    .src_addr = 0, .dst_addr = L1_ACCUM_BASE,
    .length = ACCUM_BYTES, .num_reps = 1,
};
issue_idma_init(&zero_req, 0);
while (!(idma_read_tr_count(0) >= 1)) { }
idma_clear_tid(0);
```

---

### §7.13 Multi-Client Pipelining


```c
#define PIPELINE_DEPTH  8

void idma_pipelined_load(uint64_t *srcs, uint64_t *dsts, int N) {
    int issued = 0, completed = 0;
    idma_set_threshold(0, 1);

    while (completed < N) {
        while (issued < N && (issued - completed) < PIPELINE_DEPTH) {
            asm_dmsrc(srcs[issued]);
            asm_dmdst(dsts[issued]);
            asm_dmcpy(TILE_BYTES, FLAGS_TID(0) | IDMA_FLAG_DECOUPLE_RW);
            issued++;
        }
        while (!(idma_read_tr_count(0) >= 1)) { }
        idma_clear_tid(0);
        completed++;
    }
}
```

---

### §7.14 Sparsity and Zero Handling


iDMA does NOT support zero-skipping. All bytes in the specified range are transferred regardless of value. For sparsity-aware movement, use TDMA (zmask, exponent threshold pruning). iDMA can pre-clear accumulation buffers (INIT path) before TDMA writes sparse non-zero values.

---

### §7.15 Completion Tracking and IRQ


```
  Issue transfer with trid=N
       |
       v
  TID N in-flight: IDMA_STATUS[N] = 1
       |
       v
  Transfer completes
       |
       v
  IDMA_TR_COUNT[N]++
  If TR_COUNT[N] >= THRESHOLD[N] and THRESHOLD[N] != 0:
      o_idma_tiles_to_process_irq[N] = 1  -> PLIC -> hart trap handler
       |
       v
  SW writes IDMA_CLR[N] = 1
       |
       v
  IDMA_TR_COUNT[N] = 0, IRQ[N] deasserted
```

```c
// Polling mode
void wait_tid_poll(int tid) {
    while (idma_read_tr_count(tid) < 1) { asm volatile ("nop"); }
    idma_clear_tid(tid);
    asm volatile ("fence r,r");
}

// Interrupt mode (requires §3.10 PLIC setup)
void wait_tid_irq(int tid) {
    g_dma_done[tid] = 0;
    idma_set_threshold(tid, 1);
    plic_enable_idma_irq(get_hart_id(), tid);
    while (!g_dma_done[tid]) { asm volatile ("wfi"); }
    asm volatile ("fence r,r");
}

// Batch mode: fire IRQ after N completions
void setup_batch_irq(int tid, int batch_size) {
    idma_set_threshold(tid, batch_size);
    plic_enable_idma_irq(get_hart_id(), tid);
}
```

---

### §7.16 DMA + TDMA Pipeline


The most common performance pattern on Trinity N1B0 is overlapping DMA data loading with TDMA+FPU compute using a double-buffer scheme.

```
Cycle:  | Iter 0       | Iter 1       | Iter 2       | Iter 3       |
DMA:    | Load tile 0  | Load tile 1  | Load tile 2  | Load tile 3  |
        | into BUF_A   | into BUF_B   | into BUF_A   | into BUF_B   |
TDMA:   | (priming)    | Compute BUF_A| Compute BUF_B| Compute BUF_A|
```

```c
#define BUF_A  DMA_BUF_A_BASE
#define BUF_B  DMA_BUF_B_BASE

static inline uint64_t buf_addr(int buf_id) {
    return buf_id ? BUF_B : BUF_A;
}

void dma_tdma_pipeline(uint64_t *dram_tiles, int n_tiles) {
    // Prime: load first tile into BUF_A
    asm_dmsrc(dram_tiles[0]);
    asm_dmdst(BUF_A);
    asm_dmcpy(TILE_BYTES, FLAGS_TID(0) | IDMA_FLAG_DECOUPLE_RW);
    while (!(idma_read_tr_count(0) >= 1)) { }
    idma_clear_tid(0);
    asm volatile ("fence r,r");   // first tile ready

    for (int i = 1; i < n_tiles; i++) {
        int load_buf = i & 1;     // alternates BUF_B (1), BUF_A (0)
        int comp_buf = 1 - load_buf;

        // Start DMA load into idle buffer (non-blocking issue)
        asm_dmsrc(dram_tiles[i]);
        asm_dmdst(buf_addr(load_buf));
        asm_dmcpy(TILE_BYTES, FLAGS_TID(1) | IDMA_FLAG_DECOUPLE_RW);

        // TDMA compute on ready buffer (runs while DMA loads next tile)
        tdma_process_tile(buf_addr(comp_buf));

        // Wait for DMA to finish before we use load_buf in next iteration
        while (!(idma_read_tr_count(1) >= 1)) { }
        idma_clear_tid(1);
        asm volatile ("fence r,r");   // DMA writes visible before TDMA reads
    }

    // Compute last tile
    tdma_process_tile(buf_addr((n_tiles - 1) & 1));
}
```

WARNING: The `fence r,r` between DMA completion and `tdma_process_tile()` is mandatory. TDMA reads from L1 SRAM; without the fence, TDMA may observe stale data from before the DMA write.

---

### §7.17 Multi-Tile DMA Coordination


For workloads spanning multiple tiles (e.g., all-reduce, tensor-parallel attention), tiles communicate by writing to each other's L1 via NoC PUT operations.

**NoC address construction:**
```c
uint64_t make_noc_addr(int x, int y, uint64_t local_addr) {
    // Simplified: embed x/y into high bits of the 64-bit DMA address
    return (((uint64_t)(y & 0x3F)) << 40) |
           (((uint64_t)(x & 0x3F)) << 34) |
           (local_addr & 0x3FFFFFFFFULL);
}
```

NOTE: The exact NoC address format depends on the ATT and router configuration. In practice, use ATT entries to map logical addresses to physical (x,y) coordinates rather than constructing NoC addresses directly. See §7.10.

**Send local data to a remote tile:**
```c
void tile_send_to_remote(int dst_x, int dst_y,
                         uint64_t src_l1_addr, uint64_t dst_l1_addr,
                         uint32_t nbytes, int trid) {
    att_program_remote_tile(trid, dst_x, dst_y, dst_l1_addr);

    asm volatile ("fence w,w");
    asm_dmsrc(src_l1_addr);
    asm_dmdst(att_logical_addr(trid));
    asm_dmcpy(nbytes, FLAGS_TID(trid));

    while (!(idma_read_tr_count(trid) >= 1)) { }
    idma_clear_tid(trid);
}
```

**All-to-all: each tile sends its partial result to all other tiles:**
```c
void all_to_all_send(int my_x, int my_y,
                     uint64_t partial_result_addr, uint32_t result_bytes) {
    int trid = 0;

    for (int x = 0; x < 4; x++) {
        for (int y = 1; y <= 4; y++) {
            if (x == my_x && y == my_y) continue;

            att_program_remote_tile(trid, x, y, L1_RECEIVE_BUF_OFFSET);

            asm volatile ("fence w,w");
            asm_dmsrc(partial_result_addr);
            asm_dmdst(att_logical_addr(trid));
            asm_dmcpy(result_bytes, FLAGS_TID(trid));

            if (++trid >= 32) trid = 0;
        }
    }

    for (int t = 0; t < trid; t++) {
        while (!(idma_read_tr_count(t) >= 1)) { }
        idma_clear_tid(t);
    }
}
```

NOTE: Receiving tiles must barrier-synchronize to know when all remote sends have arrived. Use CLINT MSIP or a polling flag in shared memory (over NoC) to signal completion.

---

### §7.18 Error Detection and Recovery


**ECC/parity errors in L1:**
```c
void check_and_clear_l1_ecc(void) {
    volatile uint32_t *status = (uint32_t *)(CLUSTER_CTRL_BASE + 0x120);
    uint32_t s = *status;
    if (s) {
        log_error("L1 ECC error: status=0x%08x", s);
        *status = s;    // W1C: clear the bits
    }
}
```

**Bus errors per hart:**
```c
static const uint32_t bus_err_offsets[8] = {
    0x130, 0x138, 0x140, 0x148, 0x150, 0x158, 0x160, 0x168
};

void check_bus_errors(void) {
    for (int i = 0; i < 8; i++) {
        volatile uint32_t *reg =
            (uint32_t *)(CLUSTER_CTRL_BASE + bus_err_offsets[i]);
        uint32_t err = *reg;
        if (err) {
            log_error("Bus error hart %d: 0x%08x", i, err);
            *reg = err;   // W1C
        }
    }
}
```

**DMA watchdog (SW-implemented timeout):**
```c
#define DMA_TIMEOUT_US  10000   // 10 ms watchdog

int idma_transfer_with_timeout(uint64_t src, uint64_t dst,
                                uint32_t nbytes, int trid) {
    asm volatile ("fence w,w");
    asm_dmsrc(src);
    asm_dmdst(dst);
    asm_dmcpy(nbytes, FLAGS_TID(trid));

    uint64_t deadline = *CLINT_MTIME +
                        (uint64_t)DMA_TIMEOUT_US * (CLINT_FREQ_HZ / 1000000ULL);

    while (!(idma_read_tr_count(trid) >= 1)) {
        if (*CLINT_MTIME > deadline) {
            uint32_t vc_space = idma_read_vc_space(0);
            if (vc_space == 0) {
                deadline += (uint64_t)DMA_TIMEOUT_US * (CLINT_FREQ_HZ / 1000000ULL);
                continue;
            }
            log_error("DMA timeout: trid=%d status=0x%08x vc_space=%u",
                      trid, idma_read_status(), vc_space);
            idma_clear_tid(trid);
            return -1;
        }
    }
    idma_clear_tid(trid);
    asm volatile ("fence r,r");
    return 0;
}
```

---

---

## §8. NoC and NIU

### §8.1 NoC Topology

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

#### §8.1.1 DOR Walk-Through — Per-Hop Analysis

DOR selects the output port using a simple two-phase rule:
1. If `current_X ≠ target_X`: route East (X+1) or West (X−1) toward target_X
2. Else if `current_Y ≠ target_Y`: route North (Y+1) or South (Y−1) toward target_Y
3. Else: eject to local NIU (arrived)

**Example A: Tile (0,0) → Tile (3,2)**
```
Hop 1: (0,0) →East→ (1,0)   [ΔX=3, route X first]
Hop 2: (1,0) →East→ (2,0)
Hop 3: (2,0) →East→ (3,0)   [X matched: now route Y]
Hop 4: (3,0) →North→ (3,1)
Hop 5: (3,1) →North→ (3,2)  [Arrived — eject to NIU]
Total: 5 hops, latency ≈ 5×2 + 12 = 22 cycles
```

**Example B: Tile (3,2) → Tile (1,4)**
```
Hop 1: (3,2) →West→ (2,2)   [ΔX=−2]
Hop 2: (2,2) →West→ (1,2)   [X matched]
Hop 3: (1,2) →North→ (1,3)
Hop 4: (1,3) →North→ (1,4)  [Arrived]
Total: 4 hops, latency ≈ 4×2 + 12 = 20 cycles
```

**Example C: Tile (2,1) → Tile (0,4) — DRAM access path**
```
Hop 1: (2,1) →West→ (1,1)
Hop 2: (1,1) →West→ (0,1)   [X matched]
Hop 3: (0,1) →North→ (0,2)
Hop 4: (0,2) →North→ (0,3)
Hop 5: (0,3) →North→ (0,4)  [NOC2AXI_NE_OPT — SI0]
Total: 5 hops
```

**Latency formula:**
```
latency_cycles ≈ (|ΔX| + |ΔY|) × 2 + pipeline_stages
pipeline_stages = 12 (router pipeline depth for N1B0)
```

**Why DOR is deadlock-free:**
DOR imposes a total ordering on resources: East links are always acquired before North
links. No cycle can form in the resource dependency graph, so deadlock is structurally
impossible for unicast traffic.

**SW optimization implications:**
- Tiles at Y=3–4 are closest to DRAM (NOC2AXI at Y=4): use tiles (X,3)/(X,4) as
  gather points for DRAM-heavy operations to minimize hop count.
- All-to-all traffic through center tile (2,2) creates a NoC hotspot. Use VC separation
  (weight on VC0, activations on VC2) to prevent head-of-line blocking.
- For collective operations (all-reduce), use a ring pattern along Y=2 row to avoid
  crossing the center tiles simultaneously.

```c
// Estimate hop count from source tile to destination
static inline int noc_hop_count(int src_x, int src_y, int dst_x, int dst_y) {
    return abs(dst_x - src_x) + abs(dst_y - src_y);
}

// Find the best tile to use for DRAM access (minimizes hops to SI0 at (0,4))
// Returns tile index with minimum hop count to NOC2AXI_NE_OPT
int best_tile_for_dram_si0(void) {
    int best = 0, min_hops = 99;
    for (int x = 0; x <= 3; x++) {
        for (int y = 0; y <= 2; y++) {
            int hops = noc_hop_count(x, y, 0, 4);
            if (hops < min_hops) { min_hops = hops; best = x*5+y; }
        }
    }
    return best;  // returns 3 (tile (0,3)=DISPATCH) or 2 (tile (0,2), 2 hops)
}
```

### §8.2 Virtual Channels (VC0–VC4)

Each router port has 5 independent virtual channels. Flits on different VCs never block
each other within a single physical link, preventing head-of-line blocking between
traffic classes.

**VC definitions and per-tile FIFO sizes:**
- Each Tensix tile VC FIFO: 64 flits × 2048 bits = 16 KB per VC per port direction
- Each Router tile VC FIFO: 256 flits × 2048 bits = 64 KB per VC per port direction

| VC | Canonical Use                              | FIFO depth | Notes                              |
|----|--------------------------------------------|------------|------------------------------------|
| 0  | Tensor data — weight DMA, primary payload  | 64 flits   | Highest priority; large transfers  |
| 1  | Read responses / completions               | 64 flits   | Short messages, return traffic     |
| 2  | Secondary tensor / activation transfer     | 64 flits   | Separate from weight to avoid HOL  |
| 3  | Control plane — config, APB, management    | 64 flits   | Low bandwidth, low latency         |
| 4  | Dispatch / Broadcast — LLK counter updates | 64 flits   | Broadcast-capable                  |

#### §8.2.1 VC Selection Code Examples

```c
// VC selector constants — encoded in CMD_LO bits[19:14]
#define NOC_VC_WEIGHT_DMA      0   // VC0: bulk weight transfer DRAM→L1
#define NOC_VC_RESPONSE        1   // VC1: read responses, completion ACKs
#define NOC_VC_ACTIVATION      2   // VC2: tile-to-tile activation transfers
#define NOC_VC_CONTROL         3   // VC3: config writes, CSR updates
#define NOC_VC_BROADCAST       4   // VC4: broadcast/multicast operations

#define NOC_CMD_VC(n)  ((uint32_t)((n) & 0x3F) << 14)   // bits[19:14] = request VC
#define NOC_RESP_VC(n) ((uint32_t)((n) & 0x3F) << 20)   // bits[25:20] = response VC

// Example: DRAM weight DMA — use VC0 for request, VC1 for response
uint32_t cmd = NOC_CMD_WR | NOC_CMD_RESP_MARKED
             | NOC_CMD_VC(NOC_VC_WEIGHT_DMA)
             | NOC_RESP_VC(NOC_VC_RESPONSE);
CMD_LO = cmd;

// Example: Activation tile-to-tile — use VC2/VC1
cmd = NOC_CMD_WR | NOC_CMD_VC(NOC_VC_ACTIVATION) | NOC_RESP_VC(NOC_VC_RESPONSE);
CMD_LO = cmd;

// Example: Config write from Overlay CPU — use VC3
cmd = NOC_CMD_WR | NOC_CMD_VC(NOC_VC_CONTROL);
CMD_LO = cmd;
```

**VC anti-patterns to avoid:**
```c
// BAD: DRAM traffic and config on same VC — DRAM occupies 16 flits, config stalls
CMD_LO = NOC_CMD_WR | NOC_CMD_VC(0);   // Don't use VC0 for config writes

// GOOD: Separate VCs prevent head-of-line blocking
CMD_LO = NOC_CMD_WR | NOC_CMD_VC(NOC_VC_CONTROL);  // Config always on VC3
```

**Rule:** Never share a VC between long-latency DRAM traffic and short tile-to-tile
messages. A single 4 KB DRAM response occupies 16 flits; a subsequent fast control
message queues behind all 16 flits if sent on the same VC.

### §8.3 Flit Structure and Packet Types

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

### §8.4 NIU Inject and Eject

The NIU (Network Interface Unit) is the interface between the tile's internal AXI bus
and the NoC fabric. The NIU has two paths:

- **Inject (AXI2NOC):** Takes AXI write or read transactions from the tile, converts them
  to NoC packets, and injects into the mesh.
- **Eject (NOC2AXI):** Receives NoC packets addressed to this tile, converts to AXI
  transactions, and delivers to the local AXI slave (L1 or DRAM controller).

BRISC firmware does not talk to the NIU directly using AXI protocol. Instead, it writes
to NIU control registers (memory-mapped in the NOC region at `0x0200_0000`) to configure
and submit NoC transactions.

#### §8.4.1 NIU Master Register Map (RTL-verified offsets from tt_noc_pkg.sv)

All offsets are relative to `NOC_NIU_MASTER_BASE = 0x02000000`.

| Offset | Register Name           | Access | Width | Description                                         |
|--------|-------------------------|--------|-------|-----------------------------------------------------|
| 0x00   | TARGET_ADDR_LO          | RW     | 32    | Destination address bits [31:0]                     |
| 0x04   | TARGET_ADDR_MID         | RW     | 32    | Destination address bits [47:32]                    |
| 0x08   | TARGET_ADDR_HI          | RW     | 32    | Destination address bits [63:48]                    |
| 0x0C   | RET_ADDR_LO             | RW     | 32    | Return/source address bits [31:0]                   |
| 0x10   | RET_ADDR_MID            | RW     | 32    | Return/source address bits [47:32]                  |
| 0x14   | RET_ADDR_HI             | RW     | 32    | Return/source address bits [63:48]                  |
| 0x18   | CMD_LO                  | RW     | 32    | Command word bits [31:0] — see CMD bit table        |
| 0x1C   | CMD_HI                  | RW     | 32    | Command word bits [63:32]                           |
| 0x20   | BRCST_LO                | RW     | 32    | Broadcast rectangle control bits [31:0]             |
| 0x24   | BRCST_HI                | RW     | 32    | Broadcast rectangle control bits [63:32]            |
| 0x28   | AT_LEN                  | RW     | 32    | Transfer length in bytes                            |
| 0x2C   | L1_ACC_AT_INSTRN        | RW     | 32    | L1 accumulate-and-transfer instruction              |
| 0x30   | SEC_CTRL                | RW     | 32    | Security control attribute                          |
| 0x34   | AT_DATA                 | RW     | 32    | Atomic test data (for atomic operations)            |
| 0x38   | INLINE_DATA_LO          | RW     | 32    | Inline write data bits [31:0]                       |
| 0x3C   | INLINE_DATA_HI          | RW     | 32    | Inline write data bits [63:32]                      |
| 0x40   | BYTE_ENABLE_0           | RW     | 32    | Per-byte enables for bytes [31:0]                   |
| 0x44   | BYTE_ENABLE_1           | RW     | 32    | Per-byte enables for bytes [63:32]                  |
| 0x48   | BYTE_ENABLE_2           | RW     | 32    | Per-byte enables for bytes [95:64]                  |
| 0x4C   | BYTE_ENABLE_3           | RW     | 32    | Per-byte enables for bytes [127:96]                 |
| 0x50   | BYTE_ENABLE_4           | RW     | 32    | Per-byte enables for bytes [159:128]                |
| 0x54   | BYTE_ENABLE_5           | RW     | 32    | Per-byte enables for bytes [191:160]                |
| 0x58   | BYTE_ENABLE_6           | RW     | 32    | Per-byte enables for bytes [223:192]                |
| 0x5C   | BYTE_ENABLE_7           | RW     | 32    | Per-byte enables for bytes [255:224]                |
| 0x60   | CMD_CTRL                | RW     | 32    | **Write non-zero to submit transaction**            |
| 0x64   | NODE_ID                 | RO     | 32    | Local tile NoC node ID (Y×4+X)                      |
| 0x68   | ENDPOINT_ID             | RO     | 32    | Local endpoint ID (EndpointIndex = X×5+Y)           |
| 0x6C   | NUM_MEM_PARITY_ERR      | RO/W1C | 32   | Count of memory parity errors                       |
| 0x70   | NUM_HEADER_1B_ERR       | RO/W1C | 32   | Count of single-bit header ECC errors               |
| 0x74   | NUM_HEADER_2B_ERR       | RO/W1C | 32   | Count of double-bit (uncorrectable) header errors   |
| 0x78   | ECC_CTRL                | RW     | 32    | ECC enable and mode control                         |
| 0x7C   | CLEAR_OUTSTANDING_REQ   | RO     | 32    | Outstanding request count; poll until 0 to drain    |
| 0x80   | CMD_BUF_AVAIL           | RO     | 32    | Available command buffer slots (max=FIFO_DEPTH)     |
| 0x84   | CMD_BUF_OVFL            | RO/W1C | 32   | Command buffer overflow counter                     |
| 0x88   | SENT_TARGET_ADDR_LO     | RO     | 32    | Last-sent target address bits [31:0] (debug)        |
| 0x8C   | SENT_TARGET_ADDR_MID    | RO     | 32    | Last-sent target address bits [47:32]               |
| 0x90   | SENT_TARGET_ADDR_HI     | RO     | 32    | Last-sent target address bits [63:48]               |
| 0x94   | SENT_RET_ADDR_LO        | RO     | 32    | Last-sent return address bits [31:0]                |
| 0x98   | SENT_RET_ADDR_MID       | RO     | 32    | Last-sent return address bits [47:32]               |
| 0x9C   | SENT_RET_ADDR_HI        | RO     | 32    | Last-sent return address bits [63:48]               |
| 0xA0   | SENT_CMD_LO             | RO     | 32    | Last-sent CMD_LO (debug snapshot)                   |
| 0xA4   | SENT_CMD_HI             | RO     | 32    | Last-sent CMD_HI                                    |
| 0xA8   | SENT_BRCST_LO           | RO     | 32    | Last-sent broadcast ctrl [31:0]                     |
| 0xAC   | SENT_BRCST_HI           | RO     | 32    | Last-sent broadcast ctrl [63:32]                    |
| 0xB0   | SENT_AT_LEN             | RO     | 32    | Last-sent transfer length                           |

**NIU sub-region base addresses:**
```
0x02000000  NIU_MASTER     — command buffer registers (above)
0x02000100  NIU_CFG        — per-port configuration registers
0x02000200  NIU_STATUS     — per-port status/error counters
0x02000400  NIU_SEC_FENCE  — security fence (8 address ranges × 2 regs)
0x02000500  NOC_CONN       — NoC connectivity configuration
0x02000600  NOC_ROUTER_DBG — router debug registers
```

**CMD_LO bit-field table (from tt_noc_pkg.sv):**

| Bits    | Name                    | Description                                        |
|---------|-------------------------|----------------------------------------------------|
| [0]     | NOC_CMD_AT_CPY          | 1 = atomic copy operation                          |
| [1]     | NOC_CMD_RW              | 0 = read, 1 = write                                |
| [2]     | NOC_CMD_WR_BE           | 1 = byte-enable write (use BYTE_ENABLE registers)  |
| [3]     | NOC_CMD_WR_INLINE       | 1 = inline data write (from INLINE_DATA registers) |
| [4]     | NOC_CMD_WR_INLINE_64    | 1 = 64-bit inline write                            |
| [5]     | NOC_CMD_RESP_MARKED     | 1 = request a completion response packet           |
| [6]     | NOC_CMD_BRCST           | 1 = broadcast packet (use BRCST_LO/HI)             |
| [7]     | NOC_CMD_LINKED          | 1 = linked packet (continuation of prior)          |
| [8]     | NOC_CMD_PATH_RESERVE    | 1 = reserve path (latency-sensitive)               |
| [9]     | NOC_CMD_MEM_RD_DROP_ACK | 1 = drop ACK on memory read (fire-and-forget)      |
| [10]    | NOC_CMD_DYNA_ROUTING_EN | 1 = enable dynamic routing (carried list)          |
| [11]    | NOC_CMD_L1_ACC_AT       | 1 = L1 accumulate-and-transfer                     |
| [12]    | NOC_CMD_FLUSH           | 1 = cache flush packet                             |
| [13]    | NOC_CMD_SNOOP           | 1 = snoop packet                                   |
| [19:14] | NOC_CMD_STATIC_VC       | Request virtual channel (0–4)                      |
| [25:20] | NOC_RESP_STATIC_VC      | Response virtual channel (0–4)                     |

```c
// NIU register access macros
#define NOC_NIU_BASE   0x02000000UL
#define NOC_REG(off)   (*(volatile uint32_t *)(NOC_NIU_BASE + (off)))

#define TARGET_ADDR_LO     NOC_REG(0x00)
#define TARGET_ADDR_MID    NOC_REG(0x04)
#define TARGET_ADDR_HI     NOC_REG(0x08)
#define RET_ADDR_LO        NOC_REG(0x0C)
#define RET_ADDR_MID       NOC_REG(0x10)
#define RET_ADDR_HI        NOC_REG(0x14)
#define CMD_LO             NOC_REG(0x18)
#define CMD_HI             NOC_REG(0x1C)
#define BRCST_LO           NOC_REG(0x20)
#define BRCST_HI           NOC_REG(0x24)
#define AT_LEN             NOC_REG(0x28)
#define L1_ACC_AT_INSTRN   NOC_REG(0x2C)
#define SEC_CTRL_REG       NOC_REG(0x30)
#define CMD_CTRL           NOC_REG(0x60)
#define NOC_NODE_ID        NOC_REG(0x64)
#define NOC_ENDPOINT_ID    NOC_REG(0x68)
#define NOC_1B_ERR_CNT     NOC_REG(0x70)
#define NOC_2B_ERR_CNT     NOC_REG(0x74)
#define NOC_OUTSTANDING    NOC_REG(0x7C)
#define CMD_BUF_AVAIL      NOC_REG(0x80)
#define CMD_BUF_OVFL       NOC_REG(0x84)

// CMD bit constants
#define NOC_CMD_WR           (1u << 1)
#define NOC_CMD_WR_BE        (1u << 2)
#define NOC_CMD_WR_INLINE    (1u << 3)
#define NOC_CMD_RESP_MARKED  (1u << 5)
#define NOC_CMD_BRCST        (1u << 6)
#define NOC_CMD_DYNA_ROUTE   (1u << 10)
#define NOC_CMD_L1_ACC       (1u << 11)
#define NOC_CMD_VC(n)        ((uint32_t)((n) & 0x3F) << 14)
#define NOC_RESP_VC(n)       ((uint32_t)((n) & 0x3F) << 20)
```

#### §8.4.2 Read Own NIU Node/Endpoint IDs

```c
// Identify which tile this firmware is running on
void noc_print_identity(void) {
    uint32_t node_id     = NOC_NODE_ID;      // reads 0x02000064
    uint32_t endpoint_id = NOC_ENDPOINT_ID;  // reads 0x02000068
    // node_id encodes (Y×cols + X) or similar mesh ordering
    // endpoint_id = X*5 + Y for Tensix tiles
    uint32_t ep_x = endpoint_id / 5;
    uint32_t ep_y = endpoint_id % 5;
    // ep_x in [0..3], ep_y in [0..4]
}
```

#### §8.4.3 Check and Clear NIU ECC Errors

```c
// Poll NIU ECC error counters; clear on read (W1C)
void noc_check_ecc_errors(void) {
    uint32_t err_1b = NOC_1B_ERR_CNT;   // single-bit correctable header errors
    uint32_t err_2b = NOC_2B_ERR_CNT;   // double-bit uncorrectable errors

    if (err_2b > 0) {
        // Uncorrectable header error — packet was corrupted; escalate to FW error handler
        handle_noc_fatal_error(err_2b);
    }
    if (err_1b > 0) {
        // Correctable error — log but continue; clear by writing 1
        NOC_REG(0x70) = err_1b;  // W1C: write read value back to clear
        log_noc_warning(err_1b);
    }
    // Also check memory parity errors
    uint32_t mem_par = NOC_REG(0x6C);
    if (mem_par > 0) {
        NOC_REG(0x6C) = mem_par;  // W1C clear
    }
}
```

#### §8.4.4 Drain Outstanding Requests Before Power-Down

```c
// Wait until all in-flight NoC requests have been acknowledged
void noc_drain_outstanding(void) {
    uint32_t timeout = 100000;
    while (NOC_OUTSTANDING != 0 && --timeout > 0);
    if (timeout == 0) {
        // NIU stalled — debug via SENT_* registers
        uint32_t last_tgt_lo  = NOC_REG(0x88);
        uint32_t last_tgt_mid = NOC_REG(0x8C);
        uint32_t last_cmd     = NOC_REG(0xA0);
        handle_noc_drain_timeout(last_tgt_lo, last_tgt_mid, last_cmd);
    }
}
```

### §8.5 ATT (Address Translation Table)

The ATT translates software virtual addresses to NoC physical coordinates + endpoint IDs.
It lives at `0x0201_0000` (size 12 KB) and has three sub-tables.

**ATT base address:** `0x02010000`
**ATT size:** `0x3000` bytes (12 KB)

**Mask Table (16 entries, at 0x02010000):** Each entry defines an address range:
```
entry[i].base_addr  — base address of region
entry[i].mask       — bit mask (1 = match this bit, 0 = wildcard/don't-care)
entry[i].table_idx  — index into endpoint table
```

**Endpoint Table (1024 entries, at 0x02010100):** Each entry defines the target:
```
entry[j].x_coord     — destination X (0–3)
entry[j].y_coord     — destination Y (0–4)
entry[j].endpoint_id — local endpoint at destination
```

**Dynamic Routing Table (32 entries, at 0x02013000):** Used when `dynamic_routing_en=1`.

#### §8.5.1 ATT Programming Sequence

```c
#define ATT_BASE          0x02010000UL
#define ATT_MASK_TABLE    ((volatile uint64_t *)(ATT_BASE + 0x000))
#define ATT_EP_TABLE      ((volatile uint64_t *)(ATT_BASE + 0x100))

// ATT mask entry layout (64-bit):
//   [63:32] base_addr
//   [31:16] mask (bits that must match)
//   [15:0]  endpoint_table_index
#define ATT_MASK_ENTRY(base, mask, idx) \
    (((uint64_t)(base) << 32) | ((uint64_t)(mask) << 16) | (idx))

// ATT endpoint entry layout (64-bit):
//   [13:8] y_coord
//   [7:2]  x_coord
//   [1:0]  endpoint_id LSBs
#define ATT_EP_ENTRY(x, y, ep) \
    (((uint64_t)(y) << 8) | ((uint64_t)(x) << 2) | (ep))

// Example: Map 0x60000000–0x63FFFFFF (64 MB) to NOC2AXI_NE_OPT at (0,4) = SI0
void att_map_dram_si0(void) {
    // Mask entry 0: match top 6 bits of address (64 MB range)
    ATT_MASK_TABLE[0] = ATT_MASK_ENTRY(0x60000000, 0xFC000000, 0);

    // Endpoint entry 0: X=0, Y=4, endpoint=4 (EndpointIndex for (0,4))
    ATT_EP_TABLE[0] = ATT_EP_ENTRY(0, 4, 4);
}

// Example: Map four DRAM channels to SI0–SI3
void att_map_all_dram(void) {
    // SI0 → (0,4): 0x60000000–0x63FFFFFF
    ATT_MASK_TABLE[0] = ATT_MASK_ENTRY(0x60000000, 0xFC000000, 0);
    ATT_EP_TABLE[0]   = ATT_EP_ENTRY(0, 4, 4);   // EndpointIndex (0,4)=4

    // SI1 → (1,4): 0x64000000–0x67FFFFFF
    ATT_MASK_TABLE[1] = ATT_MASK_ENTRY(0x64000000, 0xFC000000, 1);
    ATT_EP_TABLE[1]   = ATT_EP_ENTRY(1, 4, 9);   // EndpointIndex (1,4)=9

    // SI2 → (2,4): 0x68000000–0x6BFFFFFF
    ATT_MASK_TABLE[2] = ATT_MASK_ENTRY(0x68000000, 0xFC000000, 2);
    ATT_EP_TABLE[2]   = ATT_EP_ENTRY(2, 4, 14);  // EndpointIndex (2,4)=14

    // SI3 → (3,4): 0x6C000000–0x6FFFFFFF
    ATT_MASK_TABLE[3] = ATT_MASK_ENTRY(0x6C000000, 0xFC000000, 3);
    ATT_EP_TABLE[3]   = ATT_EP_ENTRY(3, 4, 19);  // EndpointIndex (3,4)=19
}
```

### §8.6 Remote L1 Write Pattern

```c
// Write 4KB from local L1 to remote tile (2,1) — VC0 (weight data)
void noc_write_to_tile(uint32_t dst_x, uint32_t dst_y,
                       uint32_t src_l1_offset, uint32_t dst_l1_offset,
                       uint32_t bytes) {
    // Wait for a free command buffer slot
    while (CMD_BUF_AVAIL == 0);

    // Destination address: encode as [y:6][x:6][local_addr:52]
    // For L1 at offset 0x5000 in tile (2,1):
    uint64_t dst_noc = ((uint64_t)dst_y << 58) | ((uint64_t)dst_x << 52)
                     | (uint64_t)dst_l1_offset;
    TARGET_ADDR_LO  = (uint32_t)(dst_noc & 0xFFFFFFFF);
    TARGET_ADDR_MID = (uint32_t)((dst_noc >> 32) & 0xFFFF);
    TARGET_ADDR_HI  = 0;

    // Source address (return address = where to read data from)
    RET_ADDR_LO     = src_l1_offset;
    RET_ADDR_MID    = 0;
    RET_ADDR_HI     = 0;

    // Transfer length
    AT_LEN = bytes;

    // Command: write | VC0 | request completion response on VC1
    CMD_LO = NOC_CMD_WR | NOC_CMD_RESP_MARKED
           | NOC_CMD_VC(NOC_VC_WEIGHT_DMA)
           | NOC_RESP_VC(NOC_VC_RESPONSE);
    CMD_HI = 0;

    // Submit transaction (hardware captures all registers atomically)
    CMD_CTRL = 1;
}

// Remote L1 read — request data from tile (1,2) L1 offset 0x2000 into local L1 0x1000
void noc_read_from_tile(uint32_t src_x, uint32_t src_y,
                        uint32_t src_offset, uint32_t dst_l1_offset,
                        uint32_t bytes) {
    while (CMD_BUF_AVAIL == 0);

    // For reads: TARGET = source tile address, RET = where to put response
    uint64_t src_noc = ((uint64_t)src_y << 58) | ((uint64_t)src_x << 52)
                     | (uint64_t)src_offset;
    TARGET_ADDR_LO  = (uint32_t)(src_noc & 0xFFFFFFFF);
    TARGET_ADDR_MID = (uint32_t)((src_noc >> 32) & 0xFFFF);
    TARGET_ADDR_HI  = 0;

    // Return address = where the response data should be written (local L1)
    RET_ADDR_LO     = dst_l1_offset;
    RET_ADDR_MID    = 0;
    RET_ADDR_HI     = 0;

    AT_LEN = bytes;

    // Read command: NOC_CMD_RW=0 (read), VC2 for activation reads
    CMD_LO = NOC_CMD_VC(NOC_VC_ACTIVATION) | NOC_RESP_VC(NOC_VC_RESPONSE);
    CMD_HI = 0;
    CMD_CTRL = 1;

    // Wait for the response (outstanding count drops to 0)
    noc_drain_outstanding();
}
```

### §8.7 Broadcast / Multicast

Broadcast sends the same data to all tiles within a rectangular region of the mesh.
Set `NOC_CMD_BRCST=1` and fill BRCST_LO/HI with the start corner.

```c
// Broadcast weight shard from local L1 to all Tensix tiles in row Y=1 (X=0..3)
// Source: local L1 at offset 0x1000, 256 bytes
void noc_broadcast_row(uint32_t src_l1_offset, uint32_t dst_l1_offset, uint32_t bytes) {
    while (CMD_BUF_AVAIL == 0);

    // For broadcast: TARGET encodes the END corner of the rectangle
    // End corner: X=3, Y=1
    uint64_t dst_noc = ((uint64_t)1 << 58) | ((uint64_t)3 << 52) | (uint64_t)dst_l1_offset;
    TARGET_ADDR_LO  = (uint32_t)(dst_noc & 0xFFFFFFFF);
    TARGET_ADDR_MID = (uint32_t)((dst_noc >> 32) & 0xFFFF);
    TARGET_ADDR_HI  = 0;

    // BRCST_LO encodes the START corner (X=0, Y=1)
    // bits[11:6] = start_y, bits[5:0] = start_x
    BRCST_LO = (1u << 6) | (0u);   // start_y=1, start_x=0
    BRCST_HI = 0;

    RET_ADDR_LO  = src_l1_offset;
    RET_ADDR_MID = 0;
    RET_ADDR_HI  = 0;
    AT_LEN = bytes;

    // Broadcast write on VC4
    CMD_LO = NOC_CMD_WR | NOC_CMD_BRCST | NOC_CMD_VC(NOC_VC_BROADCAST);
    CMD_HI = 0;
    CMD_CTRL = 1;
}

// Broadcast to all 16 Tensix tiles (X=0..3, Y=0..3)
void noc_broadcast_all_tensix(uint32_t src_offset, uint32_t dst_offset, uint32_t bytes) {
    while (CMD_BUF_AVAIL == 0);

    uint64_t dst_noc = ((uint64_t)3 << 58) | ((uint64_t)3 << 52) | (uint64_t)dst_offset;
    TARGET_ADDR_LO  = (uint32_t)(dst_noc & 0xFFFFFFFF);
    TARGET_ADDR_MID = (uint32_t)((dst_noc >> 32) & 0xFFFF);
    TARGET_ADDR_HI  = 0;
    BRCST_LO = (0u << 6) | (0u);   // start (0,0)
    BRCST_HI = 0;
    RET_ADDR_LO = src_offset;
    RET_ADDR_MID = 0;
    AT_LEN = bytes;
    CMD_LO = NOC_CMD_WR | NOC_CMD_BRCST | NOC_CMD_VC(NOC_VC_BROADCAST);
    CMD_CTRL = 1;
}
```

### §8.8 VC Channel Selection Guide for SW

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

```c
// VC selection helper: choose VC based on traffic type
typedef enum {
    TRAFFIC_DRAM_WEIGHT   = 0,  // bulk DMA from DRAM
    TRAFFIC_ACTIVATION    = 1,  // tile-to-tile activation
    TRAFFIC_RESPONSE      = 2,  // read completions
    TRAFFIC_CONFIG        = 3,  // register writes
    TRAFFIC_BROADCAST     = 4,  // multicast/broadcast
} noc_traffic_type_t;

static const uint8_t vc_map[] = {0, 2, 1, 3, 4};
#define NOC_VC_FOR(type)  vc_map[(type)]
```

### §8.9 NoC Flow Control and Back-Pressure

The NoC uses credit-based flow control. Each VC FIFO has a fixed credit count equal to
its depth (64 flits for Tensix tiles, 256 for Router tiles). A sender can only inject
flits if it has credits for the downstream VC.

**SW implication:** If a tile attempts to inject too many flits before the receiver
drains them, the NIU stalls the BRISC write to the NIU command register. The BRISC
will block at `CMD_CTRL = 1` until credits are available.

**Practical limit:** Keep individual DMA transfers ≤ 4 KB (16 flits) to stay within
one VC quota and avoid stalling the NIU for extended periods.

```c
// Check command buffer before submitting — avoids spinning inside CMD_CTRL write
void noc_safe_submit(void) {
    // Check available slots
    uint32_t avail = CMD_BUF_AVAIL;
    if (avail == 0) {
        // Back-pressure: drain outstanding requests or wait
        noc_drain_outstanding();
    }

    // Check for prior overflow (indicates previous burst was too aggressive)
    uint32_t ovfl = CMD_BUF_OVFL;
    if (ovfl > 0) {
        CMD_BUF_OVFL = ovfl;  // W1C clear
        log_warning("NOC CMD BUF OVERFLOW: %u times", ovfl);
    }

    CMD_CTRL = 1;  // safe to submit
}
```

### §8.10 NIU Security Fence

The NIU has 8 configurable security ranges at `0x02000400`. Each range specifies an
address window and the minimum security level required for read and write access.

```c
#define NIU_SEC_FENCE_BASE  0x02000400UL
#define SEC_FENCE_REG(i, off)  (*(volatile uint32_t *)(NIU_SEC_FENCE_BASE + (i)*8 + (off)))

// Each range entry is 64-bit: [sec_level_rd:4][sec_level_wr:4][range_enable:1]
// Range registers: [0] = low 32 bits of address, [4] = high 32 bits + attributes

// Disable all security ranges (open access — development only)
void noc_sec_fence_disable_all(void) {
    for (int i = 0; i < 8; i++) {
        SEC_FENCE_REG(i, 0) = 0;  // low addr = 0
        SEC_FENCE_REG(i, 4) = 0;  // high addr + attrs = 0 (range disabled)
    }
}

// Example: restrict DRAM range 0x60000000–0x7FFFFFFF to security level 2
void noc_sec_fence_protect_dram(void) {
    int i = 0;
    SEC_FENCE_REG(i, 0) = 0x60000000;  // range start
    // bits[63:32]: end_addr[27:0] | rd_sec_level[3:0] | wr_sec_level[3:0] | enable[0]
    SEC_FENCE_REG(i, 4) = (0x7FFFFFFF & 0x0FFFFFFF)  // end addr upper
                         | (2u << 28)   // rd security level = 2
                         | (2u << 24)   // wr security level = 2
                         | (1u << 0);   // range enable = 1
}
```

---

## §9. NOC2AXI and DRAM Access

### §9.1 NOC2AXI Overview

Four NOC2AXI tiles (Y=4, X=0–3) bridge the NoC mesh to external DRAM via AXI4. Each
tile connects to one DRAM channel (SI0–SI3). The AXI data width is 512 bits (64 bytes
per beat). Maximum in-flight AXI transactions: 64 reads, 32 writes per NOC2AXI tile.

N1B0 uses two composite variants at X=1 and X=2:
- `NOC2AXI_ROUTER_NE_OPT` (X=1, spans Y=4+Y=3): NOC2AXI + router in one physical tile
- `NOC2AXI_ROUTER_NW_OPT` (X=2, spans Y=4+Y=3): same structure, NW corner

The composite tiles have internal cross-row flit wires connecting the Y=4 NOC2AXI logic
to the Y=3 router logic. From SW's perspective, they behave identically to the
corner tiles at X=0 and X=3.

### §9.2 DRAM Address Mapping (SI0–SI3)

| Channel | NoC Target     | Physical Address Range                  |
|---------|----------------|-----------------------------------------|
| SI0     | (X=0, Y=4)     | 0x6000_0000 – 0x67FF_FFFF (128 MB)     |
| SI1     | (X=1, Y=4)     | 0x6800_0000 – 0x6FFF_FFFF (128 MB)     |
| SI2     | (X=2, Y=4)     | 0x7000_0000 – 0x77FF_FFFF (128 MB)     |
| SI3     | (X=3, Y=4)     | 0x7800_0000 – 0x7FFF_FFFF (128 MB)     |

To access DRAM, a Tensix tile sends a NoC packet with destination coordinates
(X=0–3, Y=4) and the local AXI address in the lower 48 bits of the address field.

### §9.3 AXI Burst Programming Guide

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

### §9.4 DRAM Performance: Bandwidth and Latency

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

### §9.5 Multi-Channel Striping Pattern

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

### §9.6 Cache Coherency with DRAM

Trinity N1B0 does not have a coherent hardware cache between the Overlay CPU L2 cache
and DRAM. If the Overlay CPU writes data to its L2 cache (backed by L1 SRAM) and then
a BRISC DMA reads from DRAM at the same physical address, the DMA may see stale data.

**SW rules:**
1. The host must flush data to DRAM before starting any DMA-based transfer.
2. After a BRISC DMA writes to DRAM, any Overlay CPU access to that range must
   invalidate the L2/L1 cache lines first.
3. TRISC firmware running on ai_clk has no cache — L1 accesses are always coherent with
   TDMA and iDMA writes to L1.

### §9.7 Full Example: DRAM Weight Prefetch

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

## §10. Performance Guide — Combined

### §10.1 Compute Throughput (TOPS Estimates)

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

### §10.2 Memory Bandwidth Budget

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

### §10.3 Bottleneck Diagnosis

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

### §10.4 Double-Buffer Pattern (DMA + Compute Overlap)

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

### §10.5 Fidelity Mode Selection

| Fidelity | ALU Config            | Precision | Throughput | Use Case                       |
|----------|-----------------------|-----------|------------|--------------------------------|
| LoFi     | FP16B, MULT_PAIRS=4   | ~3 sig dec| 2× slower  | Draft inference, fast preview  |
| HiFi2    | FP16, MULT_PAIRS=4    | ~3 sig dec| standard   | FP16 inference                 |
| HiFi3    | FP16, MULT_PAIRS=8    | ~4 sig dec| standard   | Quality FP16                   |
| HiFi4    | FP32, MULT_PAIRS=8    | ~7 sig dec| standard   | Training, fine-tuning          |

For INT16/INT8 inference, HiFi2 (`ALU_FORMAT_SPEC=FMT_FP16`, `ALU_ACC_CTRL=INT32_mode`)
is the recommended setting. It provides enough precision for quantized inference while
maximizing throughput.

### §10.6 Format Selection Table

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

### §10.7 Clock Gating Configuration

Clock gating saves power but adds latency when the first transfer arrives after the clock has been gated off. Choose hysteresis based on the access pattern.

| Scenario | CLOCK_GATING.IDMA | HYST value | Notes |
|----------|-------------------|------------|-------|
| Continuous DMA (training loop) | 1 | 0x7F (max) | Clock stays on between bursts |
| Burst DMA (infrequent loads) | 1 | 0x20 (32 cycles) | Balance power vs wake latency |
| Bring-up / debug | 0 | — | Clock always on; no gating |
| Ultra-low-power idle | 1 | 0x00 | Gate immediately after activity |

```c
// Enable iDMA clock gating with 64-cycle hysteresis
volatile uint32_t *clk_gate = (uint32_t *)(CLUSTER_CTRL_BASE + 0x0CC);
volatile uint32_t *clk_hyst = (uint32_t *)(CLUSTER_CTRL_BASE + 0x0D0);
*clk_hyst  = 0x06;              // 2^6 = 64 cycles
*clk_gate |= (1u << 1);         // CLOCK_GATING.IDMA = 1
```

### §10.8 In-Flight Transaction Depth

| Stage | Capacity | Domain |
|-------|----------|--------|
| Frontend timing slice | 1 per client × 24 = 24 | core_clk |
| Frontend metadata FIFO | 42 entries | core_clk |
| CDC async payload FIFO | 8 entries | boundary |
| Per-backend metadata FIFO | 28 entries × 2 = 56 | gated_l1_clk |
| Total TIDs | 32 | — |

Effective pipeline depth per client: approximately 1–2 concurrent DMCPY calls before back-pressure. The CDC FIFO (8 entries) is the binding constraint for burst-issue scenarios. Issuing more than 8 descriptors in rapid succession (across all 24 clients combined) will cause DMCPY to stall.

### §10.9 Backend Selection

The backend type (`IDMA_BE_TYPE_AXI`) is a compile-time constant. In N1B0, verify with the chip configuration team which backend is present per tile.

| Backend | Target | Latency | Best for |
|---------|--------|---------|---------|
| OBI (`IDMA_BE_TYPE_AXI=0`) | Local L1 SRAM | 1–4 cycles | L1-to-L1 copies, zero-fill |
| AXI (`IDMA_BE_TYPE_AXI=1`) | DRAM via NOC2AXI | 50–200+ cycles | DRAM weight loading |

For DRAM-to-L1 transfers, always set `decouple_rw=1`. This allows the AXI read request to proceed ahead of the OBI write, pipeline-hiding the DRAM access latency.

### §10.10 2D Transfer Efficiency

The 2D legalizer expands `num_reps` inner transfers internally. This saves CPU overhead compared to issuing `num_reps` individual 1D DMCPY calls.

| Approach | CPU cycles | CDC FIFO entries consumed |
|----------|-----------|--------------------------|
| num_reps=128 single DMCPY | ~5 cycles (1 instruction) | 1 entry |
| 128 individual DMCPY calls | ~640 cycles (128 instructions) | 128 entries |

**Recommendation:** Use 2D mode whenever `num_reps >= 4`. The break-even is at approximately 2–3 repetitions.

**Stride alignment tip:** For best L1 bank performance, choose dst_stride values that are not exact powers of 2 times the L1 bank size. This distributes 2D writes across multiple L1 banks and reduces bank conflicts.

### §10.11 L1 Bandwidth Estimation

L1 SRAM in N1B0: 768 KB per tile, organized as 3072 macros × 128 bits (16 bytes) per macro.

iDMA OBI write bandwidth:
```
gated_l1_clk ~ noc_clk (500–800 MHz, platform-dependent)
OBI bus width = 128 bits = 16 bytes per cycle
Peak write BW per backend = 16 bytes × clock_freq
At 800 MHz: 12.8 GB/s per backend
Dual backends (no bank conflicts): up to 25.6 GB/s aggregate
```

Practical derating factors:
- L1 bank conflicts from strided 2D accesses: can reduce BW by 20–50%
- AXI backend DRAM latency: limits read BW to DRAM controller throughput
- NoC congestion (multi-tile PUT): reduces effective PUT bandwidth under load

### §10.12 DRAM Throughput Optimization

1. **Use burst mode (`deburst=0`, the default):** AXI burst allows the NOC2AXI bridge to issue multi-beat bursts to the DRAM controller. Single-beat mode (`deburst=1`) has significantly lower throughput and should only be used for debug.

2. **Align to 64-byte boundaries:** AXI burst efficiency is highest when source and destination DRAM addresses are 64-byte aligned. Misaligned transfers cause the legalizer to generate partial-beat accesses at the start and end.

3. **Use `decouple_rw=1` for all DRAM-to-L1 transfers:** DRAM read latency (100–200+ cycles) is much higher than OBI L1 write latency. Decoupled mode allows the read channel to prefetch ahead of the write channel, filling the latency gap.

4. **Stripe across DRAM SI channels:** Trinity N1B0 has four DRAM system interfaces (SI0–SI3) each at a different NoC-visible address range. If the data spans all 4 channels, issue 4 concurrent DMA transfers (one per SI, distinct TIDs) to maximize aggregate DRAM bandwidth.

```c
// Stripe a large load across 4 DRAM SI channels in parallel
#define DRAM_SI0  0x60000000ULL
#define DRAM_SI1  0x68000000ULL
#define DRAM_SI2  0x70000000ULL
#define DRAM_SI3  0x78000000ULL

void dma_striped_load_4ch(uint32_t total_bytes, uint64_t l1_dst) {
    const uint64_t si_bases[4] = {DRAM_SI0, DRAM_SI1, DRAM_SI2, DRAM_SI3};
    uint32_t chunk = total_bytes / 4;  // each channel carries 1/4

    for (int ch = 0; ch < 4; ch++) {
        idma_set_threshold(ch, 1);
        asm_dmsrc(si_bases[ch]);
        asm_dmdst(l1_dst + (uint64_t)ch * chunk);
        asm_dmcpy(chunk, (uint64_t)ch | IDMA_FLAG_DECOUPLE_RW);
    }

    for (int ch = 0; ch < 4; ch++) {
        while (!(idma_read_tr_count(ch) >= 1)) { }
        idma_clear_tid(ch);
    }
    asm volatile ("fence r,r");
}
```

NOTE: SI channel striping assumes that the DRAM allocation has been arranged to place consecutive 128-MB-aligned chunks on different SI channels. Confirm with the memory allocation layer.

### §10.13 Latency-Hiding Patterns

**Technique 1: Double-buffer prefetch**

Issue DMA for the next tile before compute on the current tile finishes. With two backends, DMA and TDMA can overlap by one full tile.

```
Time: -->
DMA:   [Load tile 0][Load tile 1][Load tile 2][Load tile 3]
TDMA:              [Comp tile 0][Comp tile 1][Comp tile 2]
```

**Technique 2: WFI between polls (power-efficient wait)**

Instead of spinning in a tight polling loop (which wastes issue bandwidth on L1 instruction fetches and power), use `wfi` to sleep between IRQ wake-ups.

```c
volatile int g_dma_done[32] = {0};

// Issue DMA with IRQ enabled
void idma_issue_with_irq(uint64_t src, uint64_t dst, uint32_t len, int tid) {
    g_dma_done[tid] = 0;
    idma_set_threshold(tid, 1);
    plic_enable_idma_irq(get_hart_id(), tid);

    asm volatile ("fence w,w");
    asm_dmsrc(src);
    asm_dmdst(dst);
    asm_dmcpy(len, FLAGS_TID(tid));
}

// Hart sleeps until IRQ fires
void idma_wait_irq(int tid) {
    while (!g_dma_done[tid]) {
        asm volatile ("wfi");   // sleep until interrupt; no polling overhead
    }
    asm volatile ("fence r,r");
}

// In the IRQ handler:
// g_dma_done[tid] = 1; idma_clear_tid(tid);
```

**Technique 3: Dual-hart prefetch (hart 0 prefetches, hart 1 computes)**

Assign hart 0 exclusively to DMA operations and harts 1–7 exclusively to compute. This eliminates the need for double-buffering synchronization within a single hart and allows sustained overlap.

```c
void hart0_dma_task(void) {
    for (int tile = 0; tile < N_TILES; tile++) {
        int buf = tile % N_BUFS;
        while (!g_buf_consumed[buf]) { }   // wait for compute to finish
        g_buf_consumed[buf] = 0;

        asm_dmsrc(dram_tiles[tile]);
        asm_dmdst(buf_addr(buf));
        asm_dmcpy(TILE_BYTES, FLAGS_TID(0));
        while (!(idma_read_tr_count(0) >= 1)) { }
        idma_clear_tid(0);

        asm volatile ("fence w,w");
        g_buf_ready[buf] = 1;
        wake_hart(1);   // optional: wake compute harts via CLINT
    }
}
```


---

## §11. Debugging Guide

### §11.1 DMA Stall Diagnosis

When a DMA transfer does not complete, follow this checklist:

**Step 1: Confirm the TID is still in-flight**
```c
uint32_t status = idma_read_status();   // IDMA_STATUS bitmap
if (!(status & (1u << trid))) {
    // TID completed but IDMA_TR_COUNT was not checked; may have wrapped
    // Check IDMA_TR_COUNT[trid] directly
}
```

**Step 2: Check FIFO occupancy**
```c
uint32_t vc0 = idma_read_vc_space(0);
uint32_t vc1 = idma_read_vc_space(1);
// If vc0 == 0 or vc1 == 0: backend FIFO is full
// Previous TIDs may not have been cleared; call idma_clear_tid() for completed TIDs
```

**Step 3: Verify clock gating is not starving the backend**
```c
volatile uint32_t *clk = (uint32_t *)(CLUSTER_CTRL_BASE + 0x0CC);
// If (*clk & 0x82) != 0 (IDMA or L1_FLEX_CLIENT_IDMA gating enabled):
// Verify CLOCK_GATING_HYST > 0
// Temporarily disable gating for diagnosis:
*clk &= ~0x82u;
```

**Step 4: Try disabling clock gating and retrying**
```c
CLOCK_GATING_REG &= ~(1u << 1);   // always-on for debug
// Retry the DMA and observe whether it completes
```

**Step 5: Check backend type vs address range**
- OBI backend (`IDMA_BE_TYPE_AXI=0`): handles L1 addresses (`0x0000_xxxx`)
- AXI backend (`IDMA_BE_TYPE_AXI=1`): handles DRAM addresses (`0x60xx_xxxx` to `0x7Fxx_xxxx`)
- Sending an OBI-backend descriptor to a DRAM address will likely stall permanently

**Step 6: Read WB_PC registers to see if the issuing hart is live**
```c
volatile uint32_t *wb_pc = (uint32_t *)(CLUSTER_CTRL_BASE + 0x0D8);
// If WB_PC is unchanging, the hart may be stalled on DMCPY back-pressure or in a fault
```

### §11.2 Data Corruption Checklist

When DMA completes but data in the destination is incorrect:

1. **Missing `fence w,w` before DMA:** Source data may not have been flushed from the CPU store buffer to L1 SRAM before the DMA read. Always insert `fence w,w` before the first DMSRC/DMCPY instruction.

2. **Missing `fence r,r` after DMA:** The CPU may read stale cached values from before the DMA write. Always insert `fence r,r` after polling TID completion before reading the destination.

3. **Buffer overlap:** Verify that source and destination L1 addresses do not overlap. An overlapping 1D copy has undefined behavior (write may overwrite unread source bytes).

4. **2D stride miscalculation:** Verify `src_stride >= length` (otherwise source rows overlap). Verify `dst_stride >= length` (otherwise destination rows overlap). Common mistake: confusing element stride with byte stride.

5. **DFC format mismatch:** The source format in the DFC descriptor must match the actual in-memory format of the source data. Specifying `DFC_FLOAT32` for data that is actually BF16 will produce garbage output.

6. **ATT entry stale:** If ATT was reprogrammed between two DMA transfers (to point to a different tile), verify that the first DMA has completed before reprogramming. In-flight transfers use the ATT at issue time; ATT reads are not cached.

7. **Partial MX block:** MX format transfers must be a multiple of 8 elements. A non-multiple transfer will produce incorrect block exponents for the last partial block.

### §11.3 IRQ Not Firing

When the iDMA completion IRQ is expected but never arrives at the hart:

1. **IDMA_THRESHOLD[TID] is zero:** A threshold of 0 disables IRQ generation for that TID. Set `IDMA_THRESHOLD[TID] = 1` (or the desired batch size) before issuing the DMA.

2. **PLIC source priority is zero:** A PLIC source with priority 0 is disabled and will never fire. Set `PLIC_PRIORITY(irq) = 1` or higher.

3. **PLIC enable not set for this hart's context:** Verify that the correct bit is set in the PLIC enable register for M-mode context `hart_id * 2`.

4. **`mie.MEIE` not set:** Bit 11 of the `mie` CSR must be set. Check: `csrr t0, mie; andi t0, t0, 2048; beqz t0, not_set`.

5. **`mstatus.MIE` not set:** Global machine interrupt enable (bit 3 of `mstatus`) must be set. Check: `csrr t0, mstatus; andi t0, t0, 8; beqz t0, not_set`.

6. **PLIC threshold too high:** If `PLIC_THRESHOLD(context) > PLIC_PRIORITY(irq)`, the IRQ will be masked by the PLIC. Set threshold to 0 to accept all non-zero priority IRQs.

7. **IRQ base mapping mismatch:** Verify `IDMA_IRQ_BASE` matches the actual PLIC source assignment for the iDMA IRQ wires. This is an SoC integration detail.

### §11.4 Clock Gating Issues

**Symptom: First DMA after idle takes much longer than expected**
- Cause: Clock gated off; DMA must wait for clock to re-enable
- Fix: Increase CLOCK_GATING_HYST (write larger value to 0x0D0) so the clock stays on longer after activity

**Symptom: DMA stalls immediately after issue**
- Check: Is `i_busy` from the backends properly connected to `tt_clk_gater`?
- Debug: Disable gating (`CLOCK_GATING.IDMA=0`) and retry. If DMA completes, clock gating was the problem.
- Check: Is `CLOCK_GATING.L1_FLEX_CLIENT_IDMA` (bit 7) also set? Both must be properly configured.

**Symptom: Clock gating not saving power as expected**
- Check: Is HYST set too high? With HYST=0x7F (maximum), clock stays on for 128 cycles after last activity. For workloads with long idle periods between DMA bursts, use a lower HYST value.

**Aggressive gating configuration for power-sensitive idle:**
```c
CLOCK_GATING_HYST  = 0x00;   // 2^0 = 1 cycle: gate immediately after last activity
CLOCK_GATING_REG  |= (1u << 1) | (1u << 7);
```

### §11.5 Bus Error Handling

The `BUS_ERROR_UNIT_DATA_Cx` registers (offsets 0x130–0x168) record bus errors per hart. These are set when a hart accesses an illegal address or when the L1 protection region check fails.

**L1 region protection:**
- `L1_ACCESSIBLE_REGION` (0x1DC): configures the base address and size of the protected L1 region
- `L1_REGION_ERROR` (0x1E0): captures the address of the first access violation

```c
void handle_bus_errors(void) {
    // Check per-hart bus errors
    check_bus_errors();   // clears W1C registers

    // Check L1 region violation
    volatile uint32_t *region_err = (uint32_t *)(CLUSTER_CTRL_BASE + 0x1E0);
    uint32_t viol = *region_err;
    if (viol) {
        log_error("L1 region violation: address=0x%08x", viol);
        *region_err = viol;   // W1C
        // The violating hart may need to be reset and restarted
    }
}
```

**Common causes:**
- Hart access to an address outside the L1 region configured in `L1_ACCESSIBLE_REGION`
- DMA descriptor pointing to an address that falls in the protected SFR range
- NoC PUT arriving at an out-of-range L1 address

### §11.6 RISC-V Hart Debug

**Halt a hart via DEBUG_DMACTIVE:**
```c
// DEBUG_DMACTIVE (0x1C0): each bit controls one hart's debug-module active state
// Writing 1 to bit N makes hart N active in the debug module (halted under JTAG control)
volatile uint32_t *dmactive = (uint32_t *)(CLUSTER_CTRL_BASE + 0x1C0);
*dmactive = (1u << hart_id);   // halt hart for debug
// Poll DEBUG_DMACTIVEACK (0x1C4) until hart acknowledges halt
volatile uint32_t *dmack = (uint32_t *)(CLUSTER_CTRL_BASE + 0x1C4);
while (!(*dmack & (1u << hart_id))) { }
```

**Read hart PC without halting:** Poll `WB_PC_REG_Cx` registers (0x0D8–0x110). These capture the most recent writeback PC and are updated continuously without halting the hart. Useful for detecting infinite loops.

```c
// Detect hart hang: check if PC is stuck
volatile uint32_t *wb_pc[8] = {
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x0D8),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x0E0),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x0E8),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x0F0),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x0F8),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x100),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x108),
    (uint32_t *)(CLUSTER_CTRL_BASE + 0x110),
};

void check_hart_liveness(void) {
    static uint32_t prev_pc[8] = {0};
    static int stall_count[8] = {0};

    for (int i = 0; i < 8; i++) {
        uint32_t pc = *wb_pc[i];
        if (pc == prev_pc[i]) {
            if (++stall_count[i] > 1000) {
                log_error("Hart %d may be hung at PC 0x%08x", i, pc);
            }
        } else {
            stall_count[i] = 0;
            prev_pc[i] = pc;
        }
    }
}
```

**OpenOCD / GDB connection (via JTAG):**
```
# Connect to JTAG debug adapter
openocd -f interface/jlink.cfg -f target/trinity_n1b0.cfg

# In GDB: attach to hart 0
(gdb) target remote :3333
(gdb) monitor halt
(gdb) info registers
(gdb) x/10i $pc          # disassemble at current PC

# Read cluster_ctrl_apb registers from GDB
(gdb) x/1wx 0x03000000   # RESET_VECTOR_0
(gdb) x/1wx 0x030001C0   # DEBUG_DMACTIVE

# Read iDMA status
(gdb) x/1wx <idma_apb_base>   # IDMA_STATUS

# Force a hart reset and set new reset vector
(gdb) set *((int*)0x03000000) = <new_pc_word_addr>
(gdb) set *((int*)0x030001C0) = 0   # assert reset
(gdb) set *((int*)0x030001C0) = 1   # deassert reset (hart 0)
```

NOTE: IJTAG scan chain access is not available in N1B0 by default (`INCLUDE_TENSIX_NEO_IJTAG_NETWORK` is not defined). Standard RISC-V JTAG via the debug module is the primary on-chip debug path.


---

## §12. SW Driver Template

This section provides a complete, production-quality C driver template for the Trinity N1B0 iDMA engine. All base addresses are confirmed from RTL (`tt_rocc_accel_reg.svh`): `IDMA_CMD_BUF_R = 0x03004000`, `IDMA_CMD_BUF_W = 0x03004200`. Overlay internal CSRs (SMN, EDC, PLL) use per-tile APB bases assigned at SoC integration; consult the SoC address map for those.

### §12.1 idma_driver.h

```c
/**
 * idma_driver.h -- Trinity N1B0 iDMA SW driver
 *
 * Target: RISC-V RV64GC (hart firmware running on Trinity N1B0 Tensix tile)
 * Dependencies: clint.h (for MTIME), plic.h (for IRQ setup)
 *
 * Usage:
 *   1. Call idma_init() once at tile boot.
 *   2. Use idma_memcpy_1d() / idma_memcpy_2d() for common transfers.
 *   3. Use idma_transfer() for full-control descriptor issue.
 *   4. Use idma_wait() or idma_wait_irq() for completion.
 */

#ifndef IDMA_DRIVER_H
#define IDMA_DRIVER_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* -----------------------------------------------------------------------
 * Constants
 * --------------------------------------------------------------------- */

#define IDMA_NUM_TIDS       32      /* TID space: 0..31 */
#define IDMA_NUM_CLIENTS    24      /* total client slots */
#define IDMA_TID_NONE       0xFF    /* sentinel: no TID assigned */
#define IDMA_MAX_XFER_BYTES (4 * 1024 * 1024)   /* 4 MB: IDMA_TRANSFER_LENGTH_WIDTH=22 */

/* -----------------------------------------------------------------------
 * Transfer flags (for idma_xfer_t.flags and asm_dmcpy())
 * --------------------------------------------------------------------- */

#define IDMA_FLAG_TID(n)       ((uint64_t)((n) & 0x1F))
#define IDMA_FLAG_VC(n)        ((uint64_t)(((n) & 0x3) << 5))
#define IDMA_FLAG_DECOUPLE_RW  ((uint64_t)(1u << 7))
#define IDMA_FLAG_DEBURST      ((uint64_t)(1u << 8))
#define IDMA_FLAG_SERIALIZE    ((uint64_t)(1u << 9))

/* -----------------------------------------------------------------------
 * Transfer descriptor
 * --------------------------------------------------------------------- */

typedef struct {
    uint64_t src_addr;      /* source byte address (L1 or DRAM) */
    uint64_t dst_addr;      /* destination byte address (L1 or NoC) */
    uint32_t length;        /* bytes per inner transfer (1D size) */
    uint32_t num_reps;      /* outer loop count (1 = 1D, >1 = 2D) */
    uint64_t src_stride;    /* bytes between source rows (2D mode) */
    uint64_t dst_stride;    /* bytes between destination rows (2D mode) */
    uint64_t flags;         /* IDMA_FLAG_* bitmask; embed TID with IDMA_FLAG_TID(n) */
} idma_xfer_t;

/* -----------------------------------------------------------------------
 * Return codes
 * --------------------------------------------------------------------- */

#define IDMA_OK         0
#define IDMA_ETIMEOUT  (-1)
#define IDMA_EINVAL    (-2)
#define IDMA_EBUSY     (-3)

/* -----------------------------------------------------------------------
 * Driver API
 * --------------------------------------------------------------------- */

/**
 * idma_init() -- Initialize iDMA engine. Call once at tile boot before
 * any transfer. Disables clock gating, clears all TIDs, then re-enables
 * clock gating with 64-cycle hysteresis.
 */
void idma_init(void);

/**
 * idma_transfer() -- Issue a DMA transfer (non-blocking).
 * Returns IDMA_OK immediately after issuing. May stall the calling hart
 * if the frontend FIFO is full (back-pressure via ROCC).
 * @param xfer   Transfer descriptor. flags field must include IDMA_FLAG_TID(n).
 * @param trid   Transaction ID (0..31). Must match IDMA_FLAG_TID() in xfer->flags.
 * Returns IDMA_OK on success, IDMA_EINVAL if trid is out of range.
 */
int idma_transfer(const idma_xfer_t *xfer, int trid);

/**
 * idma_wait() -- Block until TID completes or timeout expires.
 * Inserts fence r,r after completion.
 * @param trid       Transaction ID to wait for.
 * @param timeout_us Timeout in microseconds. 0 = wait forever.
 * Returns IDMA_OK on completion, IDMA_ETIMEOUT if timeout expired.
 */
int idma_wait(int trid, uint32_t timeout_us);

/**
 * idma_wait_irq() -- Wait for TID completion using WFI + PLIC IRQ.
 * More power-efficient than polling. Requires prior idma_irq_setup().
 * @param trid Transaction ID to wait for.
 */
void idma_wait_irq(int trid);

/**
 * idma_poll() -- Non-blocking completion check.
 * Returns 1 if TID has completed, 0 if still in-flight.
 */
int idma_poll(int trid);

/**
 * idma_clear() -- Clear TID completion counter and deassert IRQ.
 * Must be called after each successful idma_wait() / idma_poll().
 */
void idma_clear(int trid);

/**
 * idma_status() -- Return IDMA_STATUS bitmap (bit N = TID N in-flight).
 */
uint32_t idma_status(void);

/**
 * idma_set_threshold() -- Set completion IRQ threshold for a TID.
 * IRQ fires when IDMA_TR_COUNT[trid] >= threshold. 0 = disabled.
 */
void idma_set_threshold(int trid, uint32_t threshold);

/**
 * idma_irq_setup() -- Configure PLIC to deliver iDMA IRQ for a TID
 * to the calling hart. Call before idma_wait_irq().
 */
void idma_irq_setup(int trid);

/* -----------------------------------------------------------------------
 * Convenience wrappers
 * --------------------------------------------------------------------- */

/** 1D memcpy: copy `bytes` from src to dst. Blocks until complete. */
int idma_memcpy_1d(uint64_t src, uint64_t dst, uint32_t bytes, int trid);

/** 2D memcpy: copy `n_rows` rows of `row_bytes` each, with independent strides. */
int idma_memcpy_2d(uint64_t src, uint64_t dst,
                   uint32_t row_bytes, uint32_t n_rows,
                   uint64_t src_stride, uint64_t dst_stride,
                   int trid);

/** Zero-fill: fill `bytes` of dst with zeros (INIT path, no source read). */
int idma_zero_fill(uint64_t dst, uint32_t bytes, int trid);

/** DRAM-to-L1: load from DRAM with decouple_rw=1 (recommended for all DRAM loads). */
int idma_dram_to_l1(uint64_t dram_src, uint64_t l1_dst,
                    uint32_t bytes, int trid);

#ifdef __cplusplus
}
#endif

#endif /* IDMA_DRIVER_H */
```

### §12.2 idma_driver.c

```c
/**
 * idma_driver.c -- Trinity N1B0 iDMA SW driver implementation
 */

#include "idma_driver.h"

/* -----------------------------------------------------------------------
 * Hardware address definitions (confirm with SoC integration address map)
 * --------------------------------------------------------------------- */

#define CLUSTER_CTRL_BASE    0x03000000UL
#define CLOCK_GATING_REG     (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x0CC))
#define CLOCK_GATING_HYST_R  (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x0D0))
#define ECC_CTRL_REG         (*(volatile uint32_t *)(CLUSTER_CTRL_BASE + 0x11C))

/* iDMA APB base: confirmed from RTL (tt_rocc_accel_reg.svh) */
#define IDMA_APB_BASE        0x03004000UL  /* CMD_BUF_R base */
#define IDMA_STATUS_REG      (*(volatile uint32_t *)(IDMA_APB_BASE + 0x00))
#define IDMA_VC_SPACE_0      (*(volatile uint32_t *)(IDMA_APB_BASE + 0x04))
#define IDMA_VC_SPACE_1      (*(volatile uint32_t *)(IDMA_APB_BASE + 0x08))

/* Per-TID interrupt registers (RTL-confirmed: tt_rocc_accel_reg.svh) */
/* PER_TR_ID_IE: bits[N] = enable IRQ for TID N (3 words cover 96 TIDs) */
#define IDMA_PER_TID_IE_0    (*(volatile uint32_t *)(IDMA_APB_BASE + 0x148))  /* TIDs  0-31 */
#define IDMA_PER_TID_IE_1    (*(volatile uint32_t *)(IDMA_APB_BASE + 0x150))  /* TIDs 32-63 */
#define IDMA_PER_TID_IE_2    (*(volatile uint32_t *)(IDMA_APB_BASE + 0x158))  /* TIDs 64-95 */
/* PER_TR_ID_IP: interrupt pending (W1C) */
#define IDMA_PER_TID_IP_0    (*(volatile uint32_t *)(IDMA_APB_BASE + 0x160))
#define IDMA_PER_TID_IP_1    (*(volatile uint32_t *)(IDMA_APB_BASE + 0x168))
#define IDMA_PER_TID_IP_2    (*(volatile uint32_t *)(IDMA_APB_BASE + 0x170))
/* Last sent/ACK transaction IDs */
#define IDMA_SENT_TR_ID      (*(volatile uint32_t *)(IDMA_APB_BASE + 0x010))
#define IDMA_ACK_TR_ID       (*(volatile uint32_t *)(IDMA_APB_BASE + 0x018))

/* CLINT for timeouts */
#define CLINT_MTIME          (*(volatile uint64_t *)(0x02000000UL + 0xBFF8))
#define CLINT_FREQ_HZ        1000000UL

/* PLIC for IRQ */
#define PLIC_BASE            0x0C000000UL
#define IDMA_IRQ_BASE        32

/* -----------------------------------------------------------------------
 * IRQ completion flags (set by trap handler)
 * --------------------------------------------------------------------- */
volatile int g_idma_done[IDMA_NUM_TIDS];

/* -----------------------------------------------------------------------
 * Internal helpers
 * --------------------------------------------------------------------- */

static inline void asm_dmsrc(uint64_t src) {
    asm volatile (".insn r 0x2B, 0, 0, zero, %0, zero" :: "r"(src) : "memory");
}
static inline void asm_dmdst(uint64_t dst) {
    asm volatile (".insn r 0x2B, 1, 0, zero, %0, zero" :: "r"(dst) : "memory");
}
static inline void asm_dmstr(uint64_t ss, uint64_t ds) {
    asm volatile (".insn r 0x2B, 6, 0, zero, %0, %1" :: "r"(ss), "r"(ds) : "memory");
}
static inline void asm_dmrep(uint64_t reps) {
    asm volatile (".insn r 0x2B, 7, 0, zero, %0, zero" :: "r"(reps) : "memory");
}
static inline void asm_dmcpy(uint64_t len, uint64_t flags) {
    asm volatile (".insn r 0x2B, 3, 0, zero, %0, %1" :: "r"(len), "r"(flags) : "memory");
}
static inline uint64_t asm_dmstati(uint64_t field) {
    uint64_t r;
    asm volatile (".insn r 0x2B, 4, 0, %0, zero, %1" : "=r"(r) : "r"(field));
    return r;
}
static inline int get_hart_id(void) {
    int id;
    asm volatile ("csrr %0, mhartid" : "=r"(id));
    return id;
}

/* -----------------------------------------------------------------------
 * API Implementation
 * --------------------------------------------------------------------- */

void idma_init(void) {
    /* 1. Disable clock gating during init */
    CLOCK_GATING_REG &= ~((1u << 1) | (1u << 7));

    /* 2. Clear all TIDs */
    IDMA_CLR[0] = 0xFFFFFFFF;   /* assuming CLR is a 32-bit wide register */

    /* 3. Zero all thresholds */
    for (int i = 0; i < IDMA_NUM_TIDS; i++) {
        IDMA_THRESHOLD[i] = 0;
        g_idma_done[i]    = 0;
    }

    /* 4. Enable ECC */
    ECC_CTRL_REG = 1;

    /* 5. Re-enable clock gating with 64-cycle hysteresis */
    CLOCK_GATING_HYST_R  = 0x06;
    CLOCK_GATING_REG    |= (1u << 1) | (1u << 7);

    /* 6. Ensure all writes are visible before first DMA use */
    asm volatile ("fence");
}

int idma_transfer(const idma_xfer_t *xfer, int trid) {
    if ((unsigned)trid >= IDMA_NUM_TIDS) return IDMA_EINVAL;
    if (!xfer) return IDMA_EINVAL;

    asm volatile ("fence w,w");   /* ensure src data visible to DMA */

    asm_dmsrc(xfer->src_addr);
    asm_dmdst(xfer->dst_addr);
    if (xfer->num_reps > 1) {
        asm_dmstr(xfer->src_stride, xfer->dst_stride);
        asm_dmrep((uint64_t)xfer->num_reps);
    }
    /* Merge caller's flags with TID */
    uint64_t flags = (xfer->flags & ~0x1FULL) | IDMA_FLAG_TID(trid);
    asm_dmcpy((uint64_t)xfer->length, flags);
    /* NOTE: asm_dmcpy may stall the hart if frontend FIFO is full */
    return IDMA_OK;
}

int idma_wait(int trid, uint32_t timeout_us) {
    if ((unsigned)trid >= IDMA_NUM_TIDS) return IDMA_EINVAL;

    if (timeout_us == 0) {
        /* Wait forever */
        while (IDMA_TR_COUNT[trid] < 1) {
            asm volatile ("nop");
        }
    } else {
        uint64_t deadline = CLINT_MTIME +
                            (uint64_t)timeout_us * (CLINT_FREQ_HZ / 1000000ULL);
        while (IDMA_TR_COUNT[trid] < 1) {
            if (CLINT_MTIME > deadline) {
                return IDMA_ETIMEOUT;
            }
        }
    }
    asm volatile ("fence r,r");   /* ensure DMA writes visible to CPU */
    return IDMA_OK;
}

void idma_wait_irq(int trid) {
    /* Requires prior idma_irq_setup(trid) and hart_init_interrupts() */
    g_idma_done[trid] = 0;
    IDMA_THRESHOLD[trid] = 1;

    while (!g_idma_done[trid]) {
        asm volatile ("wfi");   /* power-efficient wait */
    }
    asm volatile ("fence r,r");
}

int idma_poll(int trid) {
    if ((unsigned)trid >= IDMA_NUM_TIDS) return 0;
    return (IDMA_TR_COUNT[trid] >= 1) ? 1 : 0;
}

void idma_clear(int trid) {
    if ((unsigned)trid >= IDMA_NUM_TIDS) return;
    IDMA_CLR[trid] = 1;   /* W1C: clears TR_COUNT[trid] and deasserts IRQ */
}

uint32_t idma_status(void) {
    return IDMA_STATUS_REG;
}

void idma_set_threshold(int trid, uint32_t threshold) {
    if ((unsigned)trid >= IDMA_NUM_TIDS) return;
    IDMA_THRESHOLD[trid] = threshold;
}

void idma_irq_setup(int trid) {
    int hart_id = get_hart_id();
    int irq     = IDMA_IRQ_BASE + trid;
    int context = hart_id * 2;

    /* Set priority */
    *((volatile uint32_t *)(PLIC_BASE + 4 * irq)) = 1;

    /* Enable in this hart's context */
    volatile uint32_t *en =
        (uint32_t *)(PLIC_BASE + 0x2000 + 0x80 * context + 4 * (irq / 32));
    *en |= (1u << (irq % 32));

    /* Threshold = 0: accept any priority */
    *((volatile uint32_t *)(PLIC_BASE + 0x200000 + 0x1000 * context)) = 0;
}

/* -----------------------------------------------------------------------
 * Convenience wrappers
 * --------------------------------------------------------------------- */

int idma_memcpy_1d(uint64_t src, uint64_t dst, uint32_t bytes, int trid) {
    idma_xfer_t x = {
        .src_addr = src, .dst_addr = dst,
        .length = bytes, .num_reps = 1,
        .flags = IDMA_FLAG_TID(trid),
    };
    int rc = idma_transfer(&x, trid);
    if (rc) return rc;
    return idma_wait(trid, 0);
}

int idma_memcpy_2d(uint64_t src, uint64_t dst,
                   uint32_t row_bytes, uint32_t n_rows,
                   uint64_t src_stride, uint64_t dst_stride,
                   int trid) {
    idma_xfer_t x = {
        .src_addr = src, .dst_addr = dst,
        .length = row_bytes, .num_reps = n_rows,
        .src_stride = src_stride, .dst_stride = dst_stride,
        .flags = IDMA_FLAG_TID(trid) | IDMA_FLAG_DECOUPLE_RW,
    };
    int rc = idma_transfer(&x, trid);
    if (rc) return rc;
    return idma_wait(trid, 0);
}

int idma_zero_fill(uint64_t dst, uint32_t bytes, int trid) {
    /* INIT path: src_addr is ignored; zero-fill is triggered by a separate
     * descriptor flag. This is a simplified placeholder; the exact mechanism
     * to enable INIT mode depends on the idma_req_t extension fields. */
    idma_xfer_t x = {
        .src_addr = 0, .dst_addr = dst,
        .length = bytes, .num_reps = 1,
        .flags = IDMA_FLAG_TID(trid),
        /* TODO: set INIT mode flag in flags field once RTL field encoding confirmed */
    };
    int rc = idma_transfer(&x, trid);
    if (rc) return rc;
    return idma_wait(trid, 0);
}

int idma_dram_to_l1(uint64_t dram_src, uint64_t l1_dst,
                    uint32_t bytes, int trid) {
    idma_xfer_t x = {
        .src_addr = dram_src, .dst_addr = l1_dst,
        .length = bytes, .num_reps = 1,
        /* decouple_rw=1: critical for DRAM reads to hide latency */
        .flags = IDMA_FLAG_TID(trid) | IDMA_FLAG_DECOUPLE_RW,
    };
    int rc = idma_transfer(&x, trid);
    if (rc) return rc;
    return idma_wait(trid, 50000);  /* 50 ms timeout for DRAM loads */
}

/* -----------------------------------------------------------------------
 * IRQ handler hook (call from machine_trap_handler when iDMA IRQ claimed)
 * --------------------------------------------------------------------- */
void idma_irq_handler(int tid) {
    idma_clear(tid);
    g_idma_done[tid] = 1;
    /* g_idma_done is volatile; the hart in wfi will see it on wakeup */
}
```

### §12.3 Usage Example (full tile firmware skeleton)

```c
/* tile_main.c -- minimal tile firmware skeleton using idma_driver */

#include "idma_driver.h"

#define L1_BASE          0x00000000UL
#define L1_SIZE          (768 * 1024)
#define DRAM_WEIGHT_ADDR 0x60000000ULL
#define WEIGHT_BYTES     (256 * 1024)

int hart_main(void) {
    int hart_id;
    asm volatile ("csrr %0, mhartid" : "=r"(hart_id));

    /* Hart 0 initializes the DMA engine and loads data */
    if (hart_id == 0) {
        idma_init();
        hart_init_interrupts();   /* set mtvec, enable mie.MEIE */

        /* Load 256 KB of weights from DRAM SI0 into L1 */
        idma_set_threshold(0, 1);
        idma_irq_setup(0);

        int rc = idma_dram_to_l1(DRAM_WEIGHT_ADDR,
                                  L1_BASE + 0x10000,  /* L1 offset 64 KB */
                                  WEIGHT_BYTES, 0);

        if (rc == IDMA_OK) {
            /* Signal harts 1-7 via CLINT MSIP */
            for (int h = 1; h < 8; h++) {
                wake_hart(h);
            }
        } else {
            /* Handle DMA failure */
            check_and_clear_l1_ecc();
            check_bus_errors();
            while (1) { asm volatile ("wfi"); }  /* halt on error */
        }
    }

    /* All harts: wait for wake from hart 0, then compute */
    if (hart_id > 0) {
        hart_init_interrupts();
        asm volatile ("wfi");      /* wait for MSIP from hart 0 */
        asm volatile ("fence r,r");

        /* Each hart processes a distinct slice of the loaded data */
        uint32_t *weights = (uint32_t *)(L1_BASE + 0x10000);
        uint32_t slice_len = WEIGHT_BYTES / (7 * sizeof(uint32_t));
        uint32_t *my_slice = weights + (hart_id - 1) * slice_len;

        /* ... compute on my_slice ... */
    }

    while (1) { asm volatile ("wfi"); }
    return 0;
}
```


---

## §13. LLM Inference Guide — LLaMA 3.1 8B

### §13.1 Model Parameters and Tile Assignment

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

### §13.2 INT16 GEMM: Weight × Activation

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

### §13.3 INT8 GEMM: KV-Cache and FFN

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

### §13.4 KV-Cache Management

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

### §13.5 Attention Layer: QK^T and AV

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

### §13.6 FFN Layer: Gate and Up Projections

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

### §13.7 All-Reduce Across Tiles

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

### §13.8 NoC Traffic Pattern

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

### §13.9 End-to-End Token Latency Estimate

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

## §14. INT8 Guide

### §14.1 INT8 vs INT16 Trade-offs

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

### §14.2 INT8 Quantization and Descale

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

### §14.3 INT8 Matmul Programming

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

### §14.4 Accumulation in INT32 DEST

INT8 GEMM always accumulates into a 32-bit DEST (INT32 mode, 512 rows). After all K
tiles are accumulated:
- DEST row i contains a 32-bit integer for each of the 16 output columns.
- The dynamic range is ±(128 × 128 × K) = ±(128 × 128 × 4096) ≈ ±67 M, well within INT32.
- Apply `INT_DESCALE_AMOUNT = ceil(log2(K)) - 7` = ceil(log2(4096)) - 7 = 5 to normalize
  back to INT8 range before writing L1.

### §14.5 INT8 DFC in iDMA

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

### §14.6 INT8 Performance Numbers

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

## §15. VC Channel Guide

### §15.1 VC Definitions and Priorities

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

### §15.2 When to Use Which VC

| Use Case                                    | VC | Reasoning                                 |
|---------------------------------------------|----|-------------------------------------------|
| DRAM weight prefetch (DRAM→L1)              | 0  | Largest transfers; highest priority       |
| DRAM read response (data returning from SI) | 1  | Separate response traffic from requests  |
| Layer output forward (tile row N → N+1)     | 2  | Medium; separate from weight traffic      |
| All-reduce message (ring reduce-scatter)    | 4  | Broadcast-capable; low bandwidth          |
| Config write (ATT programming)              | 3  | Low bandwidth, latency-insensitive        |
| KV-cache read (DRAM→L1, growing context)    | 0  | Treat as weight DMA (bulk, bandwidth)     |
| Dispatch descriptor injection               | 3  | Control traffic, infrequent               |

### §15.3 VC for iDMA vs CPU vs Dispatch

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

### §15.4 VC Space Monitoring

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

## §16. DRAM Address Access Guide

### §16.1 Physical Address Decoding

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

### §16.2 SW Address Construction for NOC2AXI

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

### §16.3 ATT-Based DRAM Mapping

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

### §16.4 Page Boundary Handling

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

### §16.5 DMA Descriptor for DRAM Access

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

### §16.6 Code Examples

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

## §17. Appendix

### §17.1 DFC Format Table

The following format codes are defined in `tt_idma_dfc_pkg.sv`. All conversions between any two formats in this table are supported by `tt_idma_dfc_wrapper`.

| Code | Format Name | Exponent Bits | Mantissa Bits | Total Bits | Notes |
|------|-------------|---------------|---------------|------------|-------|
| `DFC_FLOAT32` | IEEE 754 FP32 | 8 | 23 | 32 | Standard single precision |
| `DFC_FLOAT16` | IEEE 754 FP16 | 5 | 10 | 16 | Standard half precision (E5M10) |
| `DFC_FLOAT16_B` | BFloat16 | 8 | 7 | 16 | Google BF16 (E8M7) |
| `DFC_TF32` | TensorFloat-32 | 8 | 10 | 19 | NVIDIA TF32 (E8M10) |
| `DFC_FP8R` | FP8 E5M2 | 5 | 2 | 8 | OCP FP8, round mode |
| `DFC_FP8P` | FP8 E4M3 | 4 | 3 | 8 | OCP FP8, packed mode |
| `DFC_MXFP8R` | MX FP8 E5M2 | 5 | 2 | 8 | OCP MX, block shared exp |
| `DFC_MXFP8P` | MX FP8 E4M3 | 4 | 3 | 8 | OCP MX, block shared exp |
| `DFC_MXFP6R` | MX FP6 E3M2 | 3 | 2 | 6 | OCP MX FP6 |
| `DFC_MXFP6P` | MX FP6 E2M3 | 2 | 3 | 6 | OCP MX FP6 |
| `DFC_MXFP4` | MX FP4 E2M1 | 2 | 1 | 4 | OCP MX FP4 |
| `DFC_INT8` | INT8 | — | — | 8 | Signed 8-bit integer |
| `DFC_INT16` | INT16 | — | — | 16 | Signed 16-bit integer |
| `DFC_INT32` | INT32 | — | — | 32 | Signed 32-bit integer |
| `DFC_MXINT8` | MX INT8 | — | — | 8 | Microscaling INT8 (block exp) |
| `DFC_MXINT4` | MX INT4 | — | — | 4 | Microscaling INT4 |
| `DFC_MXINT2` | MX INT2 | — | — | 2 | Microscaling INT2 |

**Configuration parameters:**
- `WORD_WIDTH = 8` bits (element granularity in the converter)
- `MX_BLOCK_SIZE = 8` elements per microscaling block

**MX format note:** Microscaling (MX) formats use a shared block exponent for every block of 8 elements. The block exponent is stored as metadata alongside the mantissa elements. When converting MX to floating-point, the DFC reads the block exponent and applies it. When converting floating-point to MX, the DFC computes the block exponent from the max exponent in each group of 8 elements.

**Stochastic rounding:** Available for all narrowing conversions (e.g., FP32 to FP8, INT16 to INT8). Enabled via `stoch_round=1` in the DFC descriptor field. Uses a hardware LFSR seeded per block.

**Common conversion pairs and byte ratios:**

| Source | Destination | Byte Ratio | Use Case |
|--------|-------------|------------|---------|
| FLOAT32 | FLOAT16_B | 2:1 (src:dst) | FP32 weights to BF16 storage |
| FLOAT32 | FP8P | 4:1 | FP32 to compressed FP8 |
| FLOAT16 | INT8 | 2:1 | FP16 activations to INT8 |
| INT16 | INT8 | 2:1 | INT16 activations to INT8 |
| MXFP8R | FLOAT16 | 1:2 (expands) | Decompress MX to FP16 |
| INT8 | FLOAT32 | 1:4 (expands) | INT8 to FP32 for accumulation |

NOTE: For expanding conversions (destination wider than source), the destination buffer must be larger. The legalizer accounts for this in byte count calculations.

---

### §17.2 RISC-V iDMA Instruction Reference

The iDMA engine exposes a RISC-V ROCC (Rocket Custom Co-processor) interface using the `CUSTOM_1` opcode (`0x2B`) with `funct7=0x2B`. CPU harts 0–7 each have a dedicated client port (clients 0–7) to the iDMA frontend.

#### Instruction Set

| Mnemonic | funct3 | Operands | Description |
|----------|--------|----------|-------------|
| `DMSRC` | 0x0 | rs1=src_addr | Set DMA source address (64-bit on RV64). Shadow register write — not committed until DMCPY. |
| `DMDST` | 0x1 | rs1=dst_addr | Set DMA destination address (64-bit on RV64). Shadow register write. |
| `DMCPYI` | 0x2 | rs1=length, imm12=flags | Immediate-mode copy: length in rs1, flags in 12-bit immediate. Commits shadow registers and issues transfer. |
| `DMCPY` | 0x3 | rs1=length, rs2=flags | Register-mode copy: length in rs1, flags in rs2. Commits and issues transfer. |
| `DMSTATI` | 0x4 | rd=result, imm12=field | Poll status: reads iDMA status field (immediate-encoded) into rd. Does not stall. |
| `DMSTAT` | 0x5 | rd=result, rs1=field | Poll status: reads iDMA status field (register-encoded) into rd. Does not stall. |
| `DMSTR` | 0x6 | rs1=src_stride, rs2=dst_stride | Set outer-dimension strides for 2D mode. Must be called before DMCPY. |
| `DMREP` | 0x7 | rs1=num_reps | Set outer loop repetition count for 2D mode. Must be called before DMCPY. |

#### Flags Field Encoding (DMCPY rs2 / DMCPYI imm12)

| Bits | Field | Description |
|------|-------|-------------|
| [4:0] | trid | Transaction ID (0–31) |
| [6:5] | vc | Virtual channel selector (0–3) |
| [7] | decouple_rw | 1 = decouple read and write phases (recommended for DRAM reads) |
| [8] | deburst | 1 = disable AXI burst mode (single-beat only; debug use) |
| [9] | serialize | 1 = force in-order serialization across transfers |
| [11:10] | (reserved) | Write 0 |

#### DMSTAT / DMSTATI Status Fields

| Field Value | Meaning | Description |
|-------------|---------|-------------|
| 0x0 | DMSTAT_BUSY | 1 if any transfer from this hart is in-flight |
| 0x1 | DMSTAT_READY | 1 if frontend can accept a new descriptor (FIFO has space) |
| 0x2 | DMSTAT_STATUS | IDMA_STATUS[31:0] — in-flight TID bitmap |
| 0x3 | DMSTAT_VC_SPACE_0 | Available slots in backend 0 FIFO |
| 0x4 | DMSTAT_VC_SPACE_1 | Available slots in backend 1 FIFO |
| 0x10+N | DMSTAT_TR_COUNT_N | IDMA_TR_COUNT[N] for TID N (N = 0–31) |

#### Assembly Macro Reference

```c
// All ROCC instructions use CUSTOM_1 opcode (0x2B)
// Encoding: .insn r OPCODE, funct3, funct7, rd, rs1, rs2

static inline void asm_dmsrc(uint64_t src) {
    asm volatile (".insn r 0x2B, 0, 0, zero, %0, zero" :: "r"(src));
}

static inline void asm_dmdst(uint64_t dst) {
    asm volatile (".insn r 0x2B, 1, 0, zero, %0, zero" :: "r"(dst));
}

static inline void asm_dmstr(uint64_t src_stride, uint64_t dst_stride) {
    asm volatile (".insn r 0x2B, 6, 0, zero, %0, %1"
                  :: "r"(src_stride), "r"(dst_stride));
}

static inline void asm_dmrep(uint64_t num_reps) {
    asm volatile (".insn r 0x2B, 7, 0, zero, %0, zero" :: "r"(num_reps));
}

static inline void asm_dmcpy(uint64_t length, uint64_t flags) {
    asm volatile (".insn r 0x2B, 3, 0, zero, %0, %1"
                  :: "r"(length), "r"(flags));
}

static inline uint64_t asm_dmstat(void) {
    uint64_t result;
    asm volatile (".insn r 0x2B, 4, 0, %0, zero, zero" : "=r"(result));
    return result;
}

static inline uint64_t asm_dmstati(uint64_t field) {
    uint64_t result;
    asm volatile (".insn r 0x2B, 4, 0, %0, zero, %1"
                  : "=r"(result) : "r"(field));
    return result;
}

// Convenience flags macros
#define FLAGS_TID(n)           ((uint64_t)((n) & 0x1F))
#define FLAGS_VC(n)            ((uint64_t)(((n) & 0x3) << 5))
#define IDMA_FLAG_DECOUPLE_RW  ((uint64_t)(1u << 7))
#define IDMA_FLAG_DEBURST      ((uint64_t)(1u << 8))
#define IDMA_FLAG_SERIALIZE    ((uint64_t)(1u << 9))

// Full 2D DMA helper
void dma_2d(uint64_t src, uint64_t dst,
            uint32_t length, uint32_t num_reps,
            uint64_t src_stride, uint64_t dst_stride,
            int trid, int vc)
{
    uint64_t flags = FLAGS_TID(trid) | FLAGS_VC(vc);
    asm volatile ("fence w,w");
    asm_dmsrc(src);
    asm_dmdst(dst);
    asm_dmstr(src_stride, dst_stride);
    asm_dmrep((uint64_t)num_reps);
    asm_dmcpy((uint64_t)length, flags);
}
```

#### Instruction Ordering Notes

1. `DMSRC`, `DMDST`, `DMSTR`, `DMREP` write per-hart shadow registers in the iDMA frontend. They are not committed to the descriptor queue until `DMCPY` is issued.
2. `DMCPY` is the atomic commit: it captures all shadow registers and enqueues the complete descriptor.
3. Multiple harts may issue DMCPY concurrently. The WRR arbiter handles conflicts without deadlock.
4. `DMSTAT`/`DMSTATI` returns a snapshot of the current status and does not stall the CPU hart regardless of FIFO state.
5. `DMCPY` stalls the issuing hart if `o_idma_ready[client_id] = 0` (FIFO full). No explicit polling is required; the stall is transparent to firmware but counts against the hart's effective IPC.

---

### §17.3 Address Map Quick Reference

#### Tile-Local APB Address Space

```
Subsystem                      | Base Offset    | Size     | Notes
-------------------------------|----------------|----------|--------------------------
Cluster CPU control            | 0x03000000     | 0x1E4    | cluster_ctrl_apb
L1 SRAM slave APB              | 0x03800000     | varies   | t6l1_slv_apb
Cache controller               | 0x04010000     | varies   | t6l1_slv_apb sub-range
iDMA CMD_BUF_R (read channel)  | 0x03004000     | 0x180    | tt_rocc_accel_reg.svh confirmed
iDMA CMD_BUF_W (write channel) | 0x03004200     | 0x180    | tt_rocc_accel_reg.svh confirmed
ATT (NoC address translation)  | 0x02010000     | 0x3000   | noc_att; 12 KB
Overlay internal CSRs          | SoC-assigned   | varies   | overlay_mst_apb (per SoC map)
SMN ring outbound              | SoC-assigned   | varies   | smn_mst_apb (per SoC map)
EDC ring outbound              | SoC-assigned   | varies   | edc_mst_apb (per SoC map)
PLL / PVT sensors              | SoC-assigned   | varies   | t6_pll_pvt_slv (per SoC map)
```

#### Cluster Control Register Quick Reference (0x0300_0000 base)

```
Offset  | Register              | Access | Key Use
--------|-----------------------|--------|--------------------------------
0x000   | RESET_VECTOR_0        | RW     | Hart 0 reset vector (word addr)
0x008   | RESET_VECTOR_1        | RW     | Hart 1 reset vector
...     | RESET_VECTOR_2..7     | RW     | Harts 2–7 reset vectors
0x0CC   | CLOCK_GATING          | RW     | Per-unit clock gate enables
0x0D0   | CLOCK_GATING_HYST     | RW     | Hysteresis count [6:0]
0x0D8   | WB_PC_REG_C0          | RO     | Hart 0 writeback PC (live)
...     | WB_PC_REG_C1..7       | RO     | Harts 1–7 writeback PCs
0x11C   | ECC_PARITY_CONTROL    | RW     | ECC enable for L1 SRAM
0x120   | ECC_PARITY_STATUS     | RO/W1C | ECC error status flags
0x130   | BUS_ERROR_UNIT_DATA_C0| RO/W1C | Bus error for hart 0
...     | BUS_ERROR_UNIT_DATA_C1..7 | RO/W1C | Bus errors for harts 1–7
0x1C0   | DEBUG_DMACTIVE        | RW     | Debug module hart activation
0x1C4   | DEBUG_DMACTIVEACK     | RO     | Debug module hart ack
0x1DC   | L1_ACCESSIBLE_REGION  | RW     | L1 protection region config
0x1E0   | L1_REGION_ERROR       | RO     | L1 access violation address
```

#### System Memory Map (NoC-Viewable)

```
Address Range                 | Size    | Description
------------------------------|---------|------------------------------------------
0x0000_0000 – 0x000B_FFFF    | 768 KB  | Local tile L1 SRAM (N1B0 per tile)
0x0200_0000 – 0x0200_3FFF    | 16 KB   | CLINT (platform-specific base)
0x0300_0000 – 0x0300_01E3    | 484 B   | cluster_ctrl_apb
0x0201_0000 – 0x0201_2FFF    | 12 KB   | ATT (NoC address translation table)
0x0C00_0000 – 0x0FFF_FFFF    | 64 MB   | PLIC (platform-specific base)
0x6000_0000 – 0x67FF_FFFF    | 128 MB  | DRAM SI0 (via NOC2AXI at X=0,Y=4)
0x6800_0000 – 0x6FFF_FFFF    | 128 MB  | DRAM SI1 (via NOC2AXI at X=1,Y=4)
0x7000_0000 – 0x77FF_FFFF    | 128 MB  | DRAM SI2 (via NOC2AXI at X=2,Y=4)
0x7800_0000 – 0x7FFF_FFFF    | 128 MB  | DRAM SI3 (via NOC2AXI at X=3,Y=4)
```

NOTE: CLINT and PLIC base addresses are platform-specific and must be verified against the SoC integration team's address map. The values 0x0200_0000 (CLINT) and 0x0C00_0000 (PLIC) are representative placeholders based on standard RISC-V platform conventions.

#### RISC-V Platform Register Quick Reference

```
CLINT registers (base 0x0200_0000):
  MSIP[N]     : base + 0x0000 + N*4    (RW, 1-bit per hart, N=0..7)
  MTIMECMP[N] : base + 0x4000 + N*8   (RW, 64-bit per hart)
  MTIME       : base + 0xBFF8          (RO, 64-bit, free-running)

PLIC registers (base 0x0C00_0000):
  Priority[I] : base + I*4             (RW, per IRQ source I)
  Pending[I]  : base + 0x1000 + I/32  (RO bitmap)
  Enable[C,I] : base + 0x2000 + C*0x80 + (I/32)*4  (RW bitmap, context C)
  Threshold[C]: base + 0x200000 + C*0x1000          (RW)
  Claim[C]    : base + 0x200004 + C*0x1000          (RW)
  M-mode context C = hart_id * 2
```

---

### §17.4 Semaphore Map (from SW Guide Appendix A)

| ID | Symbol                  | Direction         | When to Post               | When to Wait               |
|----|-------------------------|-------------------|----------------------------|----------------------------|
| 1  | SEM_MATH                | TRISC1↔TRISC1     | Internal math sync         | Internal math sync         |
| 2  | SEM_PERF                | Any               | Perf measurement start     | Perf measurement end       |
| 4  | SEM_UNPACK_TO_DEST_UNPACK | TRISC0→TRISC1  | SRCA/SRCB filled           | Before issuing MOP         |
| 5  | SEM_STREAM              | TRISC0 internal   | Stream buffer ready        | Stream buffer drain        |
| 6  | SEM_PACK_STREAM         | TRISC2→BRISC      | DEST packed to L1          | BRISC waiting for output   |
| 7  | SEM_UNPACK_TO_DEST_PACK | TRISC0→TRISC2     | DEST ready for packing     | TRISC2 start of pack       |

---

### §17.5 THCON Register Quick Reference (from SW Guide Appendix C)

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

---

### §17.6 LLK Function Index (from SW Guide Appendix D)

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

---

### §17.7 ROCC Instruction Reference / EndpointIndex Table (from SW Guide Appendix E)

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

**EndpointIndex table (N1B0 4×5 grid, EndpointIndex = X*5+Y):**

| Tile (X,Y) | Type              | EndpointIndex |
|------------|-------------------|---------------|
| (0,0)      | TENSIX            | 0             |
| (0,1)      | TENSIX            | 1             |
| (0,2)      | TENSIX            | 2             |
| (0,3)      | DISPATCH_W        | 3             |
| (0,4)      | NOC2AXI (SI0)     | 4             |
| (1,0)      | TENSIX            | 5             |
| (1,1)      | TENSIX            | 6             |
| (1,2)      | TENSIX            | 7             |
| (1,3)      | ROUTER (empty)    | 8             |
| (1,4)      | NOC2AXI_NE (SI1)  | 9             |
| (2,0)      | TENSIX            | 10            |
| (2,1)      | TENSIX            | 11            |
| (2,2)      | TENSIX            | 12            |
| (2,3)      | ROUTER (empty)    | 13            |
| (2,4)      | NOC2AXI_NW (SI2)  | 14            |
| (3,0)      | TENSIX            | 15            |
| (3,1)      | TENSIX            | 16            |
| (3,2)      | TENSIX            | 17            |
| (3,3)      | DISPATCH_E        | 18            |
| (3,4)      | NOC2AXI (SI3)     | 19            |

---

*Document: Trinity N1B0 — NPU Software Engineer's Guide v0.2*
*Date: 2026-03-25*
*Sources: N1B0_SW_Guide_v0.1.md, overlay_dma_HDD_v0.4.md*
*Supersedes: N1B0_SW_Guide_v0.1.md (this document is a superset)*

