# Trinity SoC — SW Performance Improvement Guide
**Document:** SW_Performance_Guide_HDD_V0.1
**Date:** 2026-03-18
**Audience:** SW engineers writing kernels for Trinity Tensix (TRISC0/1/2, BRISC, Overlay CPU)
**Sources:** trinity_full_hierarchy.md, INT16_Guide_HDD_V0.1 §15-16, tensix_core_HDD.md,
            NIU_HDD_v0.1.md, router_decode_HDD_v0.5.md, RTL 20260221

---

## Table of Contents

1. [Trinity Execution Model — What SW Must Know](#1-trinity-execution-model--what-sw-must-know)
2. [Compute Throughput — TRISC1 / FPU / SFPU](#2-compute-throughput--trisc1--fpu--sfpu)
3. [Memory Hierarchy — Access Cost Table](#3-memory-hierarchy--access-cost-table)
4. [TRISC Thread Model — Latency Hiding](#4-trisc-thread-model--latency-hiding)
5. [DMA and NoC Patterns — BRISC](#5-dma-and-noc-patterns--brisc)
6. [Overlay CPU — Kernel Dispatch and Configuration](#6-overlay-cpu--kernel-dispatch-and-configuration)
7. [Multi-Tile Parallelism — Grid Mapping](#7-multi-tile-parallelism--grid-mapping)
8. [Common Bottlenecks and Diagnosis](#8-common-bottlenecks-and-diagnosis)
9. [Format Selection Quick Guide](#9-format-selection-quick-guide)
10. [Performance Recipes by Workload Type](#10-performance-recipes-by-workload-type)

---

## 1. Trinity Execution Model — What SW Must Know

### 1.1 Tile Structure (per tile, 12 tiles total)

```
tt_tensix_with_l1  (one tile, X=0..3, Y=0..2)
│
├── 4 × T6 Tensix Core  (t6[0..3], all share one L1)
│   ├── 2 × G-Tile  (FPU array: 2×16 FP Lane columns)
│   │   └── 16 FP Lane columns × M-Tile + DEST
│   │       ├── SRCA register: 48 rows × 16 cols × 19b  (latch-array, ai_clk)
│   │       └── DEST register: 1024 rows × 16 cols × 16b or 512×32b (latch-array, ai_clk)
│   ├── 3 × TRISC thread  (TRISC0/1/2, ai_clk, RISC-V)
│   ├── 1 × BRISC thread  (ai_clk, RISC-V, runs NoC DMA)
│   └── SFPU  (4 rows/cycle, 16 cols, operates on DEST via lregs, ai_clk)
│
├── L1 SRAM  (1.5 MB, 64 macros × 16 KB, ai_clk, shared by all 4 T6s)
│   └── 16 banks × 128-bit/cycle per bank
│
├── NIU / Router  (noc_clk)
│   └── 5 VC FIFOs: N/E/S/W/NIU, each 64×2048b
│
└── Overlay CPU  (Rocket RISC-V, dm_clk, separate domain from ai_clk)
    ├── L1 D/I-Cache (16+8 SRAM macros, dm_clk)
    ├── L2 banks (16 SRAM macros, dm_clk)
    └── Context Switch SRAMs (32×1024b + 8×1024b, dm_clk)
```

**Key insight:** T6[0..3] are 4 **independent** Tensix cores inside one tile, all clocked at
`ai_clk` and all sharing the same L1 partition. The Overlay CPU runs independently at `dm_clk`
and is used only for setup, dispatch, and ATT/SMN configuration.

### 1.2 The Three-Thread Pipeline

Every compute kernel runs as a **three-thread pipeline** mapped to TRISC0, TRISC1, TRISC2:

```
TRISC0 (Unpacker):   L1 → SRCA / SRCB
                     Reads tensor data from L1, converts format, fills FPU input regs
                     Bottleneck: L1 bandwidth (128-bit/cycle per channel × 2 channels)

TRISC1 (Math):       SRCA × SRCB → DEST  via FPU MOP
                     Issues MOP (MVMUL / DOTPV) and SFPU instructions
                     Bottleneck: DEST capacity, FPU MAC rate

TRISC2 (Packer):     DEST → L1 output buffer
                     Reads DEST, applies format conversion + descale, writes to L1
                     Bottleneck: DEST read rate, L1 write bandwidth

BRISC  (DMA):        L1 ↔ DRAM or L1 ↔ peer tile (NoC)
                     Runs independently; issues NoC reads/writes
                     Bottleneck: NoC VC buffer (64 flits/port), AXI MO (64 read / 32 write)
```

All four threads execute **concurrently** with semaphore synchronization between them.
Perfect performance = all four threads busy simultaneously.

### 1.3 Clock Domain Map

| Domain | Clock | Typical Freq | Runs |
|--------|-------|-------------|------|
| `ai_clk` | PLL output | ~1 GHz | TRISC, BRISC, FPU, SFPU, L1, NIU→L1 |
| `noc_clk` | Mesh clock | ~1 GHz | NoC router, VC FIFOs, NIU TX/RX |
| `dm_clk (core)` | Overlay CPU | ~500 MHz | Rocket RISC-V tiles |
| `dm_clk (uncore)` | Overlay CPU | ~500 MHz | L2 banks, SMN, context switch |

**CDC penalty:** Overlay CPU → TRISC CSR write crosses `dm_clk → ai_clk` CDC FIFO
(depth 8, `overlay_ext_reg_cdc`): 4–8 cycles overhead per write.
TRISC firmware writing to its own CSR space: 1 cycle, no CDC.
**Always use TRISC firmware for hot-path CSR writes, not Overlay CPU.**

---

## 2. Compute Throughput — TRISC1 / FPU / SFPU

### 2.1 FPU MAC Array Throughput

```
Physical MAC array per tile:
  4 T6 cores × 2 G-Tiles × 16 FP Lane columns × M-Tile rows

Format            MAC type      MACs/cycle/tile   Notes
─────────────────────────────────────────────────────────────────
FP32              fp_mul_raw    4×256 = 1024       4 T6 × 256
FP16B (BF16)      fp_mul_raw    4×256 = 1024
INT16             mul16         4×256 = 1024       16×16 → 32b
INT8 (packed)     mul8          4×512 = 2048       2 INT8/Booth cell
TF32              fp_mul_raw    4×256 = 1024
```

**Rule:** Always enable INT8 packed mode (`ALU_ACC_CTRL.INT8_math_enabled=1`) when
input format is INT8. Failure to set this halves effective throughput to 1024 MACs/cycle.

### 2.2 FPU MOP — TRISC1 Programming

TRISC1 drives the FPU exclusively via MOP (Macro-Op) instructions.
The MOP hardware unrolls inner loops automatically.

```c
// Optimal inner-loop structure for GEMM (TRISC1):
wrcfg(MOP_CFG_LOOP0_LEN, k_tiles - 1);    // inner loop: K reduction
wrcfg(MOP_CFG_LOOP1_LEN, m_tiles - 1);    // outer loop: M rows
issue_instrn(MOP, {DOTPV});                // fire — hardware loops automatically

// DO NOT poll or issue extra instructions inside the MOP loop.
// MOP is self-sustaining; TRISC1 is free to pre-configure the next kernel.
```

**Critical:** TRISC1 must not issue a second MOP before the first completes.
Use `sem_wait(SEM_MATH_DONE)` before reconfiguring MOP parameters.

### 2.3 SFPU Throughput and Constraints

SFPU operates on DEST register content via local float registers (lregs, flip-flop, NOT SRAM).

```
SFPU rate:        4 DEST rows/cycle, 16 columns parallel
Full DEST drain:  1024 rows FP16 → 256 SFPU cycles = 256 ns at 1 GHz

SFPU lreg count:  8 lregs (FF only, 32-bit each)
→ Polynomial evaluation depth limited to 8 intermediate values.
  For higher-degree polynomials: split into two SFPU passes with L1 intermediate.

Format rules:
  • SFPU always operates in FP32 internally.
  • Input from DEST: FP16B or FP32 → direct load (SFPU LOAD)
  • Input from DEST: INT32 (after INT16/INT8 GEMM) → must convert to FP16B first
    via packer (tt_dstac_to_mem) → L1 → SFPU LOAD
    Cost: 2 extra L1 round-trips ≈ 96 extra cycles for full 1024-row DEST
```

**Rule:** For layers with non-linear activations (SiLU, GELU, RMSNorm), prefer **FP16B
accumulator** for that layer — avoids INT→FP conversion overhead for SFPU.

### 2.4 DEST Double-Buffer Strategy

DEST has two halves, switchable via `DEST_REGW_BASE` / `DEST_SP_BASE`.

```
INT32/FP32 mode (512 rows):
  Buffer A: rows 0..255   (DEST_REGW_BASE = 0)
  Buffer B: rows 256..511 (DEST_SP_BASE = 256)

FP16 mode (1024 rows):
  Buffer A: rows 0..511
  Buffer B: rows 512..1023

Pipeline pattern:
  Cycle 0: TRISC1 writes to buffer A  |  TRISC2 reads from buffer B
  Cycle N: TRISC1 switches to buffer B |  TRISC2 switches to buffer A
```

```c
// TRISC1: switch to buffer B after filling A
wrcfg(DEST_REGW_BASE, 256);   // now writing to B
sem_post(SEM_PACK_BUF_A);     // release A to TRISC2

// TRISC2: switch to reading A while TRISC1 fills B
sem_wait(SEM_PACK_BUF_A);
wrcfg(DEST_RDPTR_BASE, 0);    // read from A
issue_instrn(MOP, {PACR});
```

**If TRISC2 cannot keep up with TRISC1:** the DEST buffer fills and TRISC1 stalls.
Profile with `sem_wait` cycle counters on both sides.

---

## 3. Memory Hierarchy — Access Cost Table

Understanding which memory is accessed and at what cost is the most impactful
optimization lever for SW engineers.

### 3.1 Memory Inventory per Tile

| Memory | Size/tile | Clock | Bandwidth | Latency | Shared? |
|--------|----------|-------|-----------|---------|---------|
| DEST register (latch-array) | 32 KB | ai_clk | 16 cols × 32b / cycle | 0 cycles | per T6 |
| SRCA register (latch-array) | ~2 KB | ai_clk | 48 rows × 16 × 19b | 0 cycles | per T6 |
| SFPU lregs (flip-flop) | 8 × 32b | ai_clk | 8 values | 0 cycles | per T6 |
| TRISC0/1 local mem (SRAM) | 512×52b ≈ 3.3 KB | ai_clk | 32b/cycle (52b word) | 1 cycle | per T6 |
| TRISC2/BRISC local mem (SRAM) | 1024×52b ≈ 6.6 KB | ai_clk | 32b/cycle | 1 cycle | per T6 |
| TRISC vector local mem (SRAM) | 2 × 256×104b ≈ 6.5 KB | ai_clk | 64b/cycle (104b word) | 1 cycle | per T6 |
| TRISC I-cache (SRAM) | 512/256×72b | ai_clk | 64b/cycle | 1–4 cycles | per T6 |
| L1 SRAM | 1.5 MB (64×16KB) | ai_clk | 128b/bank/cycle, 16 banks | 4–6 cycles | all 4 T6 |
| Overlay L1 D-Cache | dm_clk | dm_clk | — | dm_clk domain | Overlay CPU only |
| NoC VC FIFO (Tensix) | 5 × 64×2048b = 1.3 MB | noc_clk | 2048b/cycle | noc_clk | per tile |
| Router VC FIFO (Router tile) | 4 × 256×2048b = 26 MB | noc_clk | 2048b/cycle | noc_clk | per router tile |
| DRAM (via NIU AXI) | external | noc→axi | 64 B/beat | ~100 ns | all tiles |

### 3.2 L1 Access Cost and Bandwidth

L1 is the critical shared resource for all 4 T6 cores in a tile.

```
L1 structure:
  64 macros: 4 sbank × 4 bank × 4 sub_bank, each 1024×128b = 16 KB
  16 banks addressable per cycle (bank = addr[7:4] in 128-bit word addressing)
  Bandwidth: 16 banks × 128b = 256 B/cycle peak (ai_clk)

Per-client bandwidth:
  TDMA unpacker CH0: 128b/cycle (one L1 word per cycle)
  TDMA unpacker CH1: 128b/cycle (simultaneous, different bank)
  Packer output:     128b/cycle (L1 write)
  BRISC DMA write:   128b/cycle (NoC→L1 delivery)
  Overlay flex port: 128b/cycle (separate client)

Total concurrent clients: up to 4 active simultaneously.
With 16 banks, bank conflict is rare IF base addresses are staggered (see §5).
```

**L1 access latency:** 4–6 ai_clk cycles from TDMA read request to SRCA availability.
The TDMA pipeline hides this — the unpacker prefetches ahead. Do NOT insert software
delays between TDMA configuration and MOP issue.

### 3.3 TRISC Local Memory vs L1

TRISC local memory (512×52b = 3.3 KB per TRISC) is **faster than L1** (1 cycle vs 4–6 cycles)
but only accessible by that TRISC thread, not by the FPU or other threads.

**Use cases for TRISC local memory:**
- Loop counters and tiling metadata (m_tile, k_tile, n_tile values)
- Temporary accumulation of scalar parameters (scale factors, descale amounts)
- Small LUT tables for address computation (< 3.3 KB)

**Do NOT store:** tensor data in TRISC local memory — it is too small and not reachable
by the TDMA unpacker.

### 3.4 TRISC I-Cache Size and Code Size Constraints

```
TRISC0 I-Cache: 512×72b  (512 instructions = 512 × 9B ≈ 4.5 KB)
TRISC1 I-Cache: 256×72b  (256 instructions ≈ 2.25 KB)
TRISC2 I-Cache: 256×72b  (256 instructions ≈ 2.25 KB)
BRISC  I-Cache: 512×72b  (512 instructions ≈ 4.5 KB)
```

**Rule:** If TRISC kernel binary exceeds I-cache size, the TRISC fetches from L1 (slow path,
4–6 cycle miss penalty). Keep inner loop body < 256 instructions for TRISC1.
Move initialization code to TRISC local memory via overlay CPU pre-load.

---

## 4. TRISC Thread Model — Latency Hiding

### 4.1 Semaphore Synchronization Pattern

All synchronization between TRISC threads uses hardware semaphores (fast path, 1 cycle).

```
Canonical 3-stage pipeline semaphores:

TRISC0 (Unpack):                TRISC1 (Math):           TRISC2 (Pack):
  loop:                           loop:                    loop:
    sem_wait(SEM_SRCA_FREE)         sem_wait(SEM_SRCA_FULL)  sem_wait(SEM_DEST_FULL)
    unpack_to_srca(...)             math_mop(...)            pack_to_l1(...)
    sem_post(SEM_SRCA_FULL)         sem_post(SEM_DEST_FULL)  sem_post(SEM_SRCA_FREE)
                                    sem_post(SEM_DEST_FREE)  sem_post(SEM_DEST_FREE)
```

**Critical:** Initial semaphore values must be set before releasing TRISC resets.
If TRISC1 starts before TRISC0 posts `SEM_SRCA_FULL`, TRISC1 stalls immediately.
The overlay CPU sets initial semaphore values in the L1 mailbox before
calling `set_tensix_reset_n()`.

### 4.2 Pipelining Unpack and Math

The goal is to make TRISC0 and TRISC1 run concurrently at all times.

```
Overlapping unpack and math (ideal timeline):

Cycle:  0          N         2N        3N
TRISC0: [unpack A] [unpack B] [unpack C] [unpack D]
TRISC1: [wait]     [math A]   [math B]   [math C]
TRISC2:                        [pack A]  [pack B]

The "wait" bubble at cycle 0 is unavoidable (first unpack must complete first).
After that: N-cycle steady state with all threads busy.
```

**To maximize overlap:**
1. Make `unpack_time ≈ math_time` — if unpack is much faster, TRISC1 spends time idle.
   For INT8: SRCA fills in 24 cycles; for FP16B: 48 cycles. Size k_tile to match.
2. Use `MOP_CFG_LOOP0_LEN > 1` — let TRISC1 run K iterations autonomously while
   TRISC0 prepares the next batch.

### 4.3 Avoiding TRISC1 Starvation

TRISC1 starvation (waiting on `SEM_SRCA_FULL`) is the most common performance bug.

**Symptoms:** TRISC1 cycle counters show > 50% time in `sem_wait`.

**Causes and fixes:**

| Cause | Fix |
|-------|-----|
| L1 bank conflict during unpack | Stagger weight/activation base by 128 B (Rule 7, §16.7) |
| TRISC0 I-cache miss (kernel > 4.5 KB) | Reduce kernel binary size; move setup code to overlay CPU |
| TDMA configuration per tile too slow | Pre-configure all wrcfg in TRISC0 init, not inside loop |
| NoC delivery to L1 not complete | BRISC must post semaphore only after CMD_CTRL=0 |

### 4.4 TRISC2 Descale Overhead

For INT16/INT8 GEMM, TRISC2 must apply `INT_DESCALE` before writing to L1.

```c
// ONE-TIME setup (in kernel init, not inside loop):
wrcfg(THCON_PACKER0_2, {
    .INT_DESCALE_ENABLE = 1,
    .INT_DESCALE_MODE   = 1,    // arithmetic right shift
    .INT_DESCALE_AMOUNT = 8,    // >> 8: maps INT32 product range → INT8
});
// This is 2 CSR writes amortized over thousands of MOP iterations.
// Cost: negligible (2 cycles, done once per kernel launch).
```

If `INT_DESCALE_AMOUNT` must change per tile (e.g. per-channel quantization):
update only `INT_DESCALE_AMOUNT` field between tile iterations, not the full struct.
Use `wrcfg` with field-mask, not full-register write.

---

## 5. DMA and NoC Patterns — BRISC

### 5.1 NoC VC FIFO Sizes — BRISC Must Respect

```
Tensix tile router VC FIFO: 64 × 2048b per direction (N/E/S/W/NIU)
  64 flits × 256 B/flit = 16 KB buffer per port direction

Router tile VC FIFO:        256 × 2048b per direction
  256 flits × 256 B/flit = 64 KB buffer per port direction
```

**Rule:** A single NoC write from BRISC must not exceed the target tile's VC FIFO capacity.
Maximum safe single DMA = **16 KB** (64 flits) for Tensix→Tensix.
If the write exceeds this, the router must stall and back-pressure the sender.

Practical maximum for tile-to-tile: **4 KB per DMA transaction** (matches AXI burst cap and
one VC quota of 16 flits). Issue multiple 4 KB transactions sequentially if needed.

### 5.2 BRISC DMA Issue Pattern

```c
// Correct BRISC DMA to DRAM (NOC→AXI slave direction):
// Issue in groups of 4 to saturate 4 response VCs simultaneously

void brisc_dma_load_weights(uint64_t dram_src, uint32_t l1_dst, uint32_t bytes) {
    int n_chunks = bytes / 4096;

    for (int g = 0; g < n_chunks; g += 4) {
        int batch = (n_chunks - g) < 4 ? (n_chunks - g) : 4;
        for (int i = 0; i < batch; i++) {
            wr32(TARGET_ADDR_LO,  (dram_src + (g+i)*4096) & 0xFFFFFFFF);
            wr32(TARGET_ADDR_HI,  (dram_src + (g+i)*4096) >> 32);
            wr32(RET_ADDR_LO,     l1_dst + (g+i)*4096);
            wr32(AT_LEN,          4096);
            wr32(CMD_BRCST,       CMD_RW_READ | (VC_WEIGHT_DMA << 14));
            wr32(CMD_CTRL,        1);           // submit (non-blocking)
        }
        // Wait for this batch of 4
        for (int i = 0; i < batch; i++) {
            while (rd32(CMD_CTRL_STATUS(g+i)) != 0);
        }
    }
    // Signal TRISC0 that weights are ready
    sem_post(SEM_DMA_WEIGHT_DONE);
}
```

### 5.3 VC Selection Rules

```c
// VC assignments for each traffic type:
#define VC_WEIGHT_DMA   0    // unicast VC 0:  long DRAM→L1 weight streaming
#define VC_ACT_UNICAST  1    // unicast VC 1:  activation tile-to-tile transfer
#define VC_ALL_REDUCE   2    // unicast VC 2:  all-reduce synchronization messages
#define VC_KV_CACHE     3    // unicast VC 3:  KV-cache reads (long context)
#define VC_BCAST_WEIGHT 8    // bcast VC 8:    weight broadcast to column
```

**Never share a VC between long-latency DRAM traffic and short tile-to-tile messages.**
A single 4 KB DRAM response (16 flits) occupies the full per-VC buffer slot.
If activation sends use the same VC, they queue behind the 16-flit burst — adding 16×
flit transmission latency to what should be a 1-flit fast path.

### 5.4 Tile-to-Tile Activation Transfer

```c
// BRISC: send INT8 output tile to next Y-row (pipeline parallelism)
void brisc_send_activation(uint32_t dst_x, uint32_t dst_y,
                            uint32_t src_l1, uint32_t dst_l1,
                            uint32_t bytes) {
    wr32(TARGET_ADDR_LO,  dst_l1 & 0xFFFFFFFF);
    wr32(TARGET_ADDR_MID, dst_l1 >> 32);
    wr32(TARGET_ADDR_HI,  (dst_y << 8) | (dst_x << 2));
    wr32(RET_ADDR_LO,     src_l1);             // local address for response routing
    wr32(AT_LEN,          bytes);
    wr32(CMD_BRCST,       CMD_RW_BIT | (VC_ACT_UNICAST << 14));
    wr32(CMD_CTRL,        1);
    // Do NOT wait here if overlap with TRISC1 compute is possible
    // Wait only when L1 output buffer must be reused
}

// Wait at next output buffer reuse point:
while (rd32(CMD_CTRL) != 0);
```

**Overlap rule:** BRISC issues the send, then immediately starts the next DMA prefetch
(weight load for the next layer). The NoC delivers asynchronously. Only poll `CMD_CTRL`
when the L1 output buffer is needed again.

### 5.5 Weight Broadcast vs. Unicast

When the same weight data is needed by all 4 X-column tiles in the same Y-row:

```c
// BRISC on NIU (Y=4): broadcast weight shard to all 4 X columns in row Y
// One DRAM read → 4 tiles receive simultaneously → 4× bandwidth saving

wr32(TARGET_ADDR_HI,
    (Y_ROW << 8) | (0 << 2));             // end: (X=0, Y=Y_ROW)
wr32(TARG_ADDR_HI_BC_START,
    (Y_ROW << 20) | (3 << 14));           // start: (X=3, same row) — or use noc_x_size-1
wr32(CMD_BRCST,
    CMD_RW_BIT | CMD_BRCST_BIT | (VC_BCAST_WEIGHT << 14));
wr32(AT_LEN, weight_shard_bytes);
wr32(CMD_CTRL, 1);
```

Use broadcast for:
- Shared attention mask (same for all heads in a row)
- Shared norm scale vectors (RMSNorm scale applied to all tokens in a row)
- First-layer weight when all tiles process different token batches with the same weight

---

## 6. Overlay CPU — Kernel Dispatch and Configuration

### 6.1 Overlay CPU Role and Clock Penalty

The Overlay CPU (Rocket RISC-V, `dm_clk ≈ 500 MHz`) is a **control plane only**.
It should **not** be on the critical path of the compute loop.

```
Overlay CPU operations and their costs:
  Operation                       Clock        Latency to Tensix
  ──────────────────────────────────────────────────────────────
  Write TRISC CSR (via ext_reg_cdc) dm→ai CDC   4–8 cycles (ai_clk)
  Program ATT entry (via niu_reg_cdc) dm→noc CDC ~10 cycles (noc_clk)
  Load kernel binary to L1          AXI→L1 CDC  ~20 cycles/word (dm→ai)
  Release TRISC reset               dm→ai CDC   4–8 cycles (ai_clk)
  Read TRISC status (poll)          ai→dm CDC   4–8 cycles
```

**Rule:** Do ALL kernel setup (ATT programming, format CSR writes, tensor descriptor) before
releasing the TRISC reset. Once TRISC is running, the Overlay CPU should be idle or
pre-fetching the next kernel's configuration.

### 6.2 Kernel Launch Sequence

```c
// Overlay CPU kernel launch (correct order):

// Step 1: Load kernel binary into L1 (AXI→L1, uncore_clk → ai_clk CDC)
memcpy_to_l1(L1_TRISC0_BASE, &trisc0_bin, trisc0_size);
memcpy_to_l1(L1_TRISC1_BASE, &trisc1_bin, trisc1_size);
memcpy_to_l1(L1_TRISC2_BASE, &trisc2_bin, trisc2_size);
memcpy_to_l1(L1_BRISC_BASE,  &brisc_bin,  brisc_size);

// Step 2: Write tensor descriptor to BRISC mailbox (L1 address known to BRISC firmware)
write_mailbox(L1_MAILBOX_ADDR, &tensor_desc);
// tensor_desc = {dram_src, l1_weight_base, l1_act_base, m_tiles, k_tiles,
//                format_code, descale_amount, output_addr, semaphore_init_values}

// Step 3: Configure ATT entries for this kernel's address translations
att_config(entry=0, mask=22, ep=DRAM_WEIGHT_BASE + layer_offset, bar=L1_WEIGHT_BASE);
att_enable();

// Step 4: Configure SMN security ranges (write-protect output buffer from stray writes)
smn_config(range=0, start=L1_OUTPUT_BASE, end=L1_OUTPUT_BASE+output_size,
           wr_sec=2, rd_sec=0, enable=1);

// Step 5: Initialize semaphores in L1 (TRISC reads these at startup)
write_l1_word(L1_SEM_SRCA_FREE,   1);   // TRISC0 can start
write_l1_word(L1_SEM_SRCA_FULL,   0);
write_l1_word(L1_SEM_DEST_FULL,   0);
write_l1_word(L1_SEM_DMA_WEIGHT,  0);

// Step 6: Release TRISC reset (all 4 TRISCs + BRISC start executing simultaneously)
set_tensix_reset_n(tile_x, tile_y, ALL_TRISC_MASK);
```

### 6.3 CDC FIFO Overflow Avoidance

`overlay_ext_reg_cdc` has **depth 8** FIFOs for both directions (Overlay→T6 and T6→Overlay).

**Rule:** Never issue more than 8 consecutive `wrcfg` from the Overlay CPU without
checking for a response. If the CDC FIFO fills, subsequent writes are dropped silently.

```c
// Safe Overlay CPU → TRISC CSR batch write:
#define CDC_FIFO_DEPTH 8

void overlay_write_csr_batch(uint32_t *addrs, uint32_t *values, int n) {
    for (int i = 0; i < n; i++) {
        if ((i % CDC_FIFO_DEPTH) == 0 && i > 0)
            overlay_wait_csr_ack();    // drain FIFO before next batch
        overlay_write_csr(addrs[i], values[i]);
    }
}
```

### 6.4 Context Switch — Multi-Kernel Scheduling

When two kernels must run in sequence (e.g. GEMM then RMSNorm):

```c
// TRISC1 register context is saved to SRAM before kernel switch:
// overlay_context_switch saves MOP config, format CSRs, loop counters
// to gen_cs_32x1024 SRAM (32 entries × 1024 bits each)

context_switch_save(TRISC1_CTX,  gen_cs_32x1024[0]);
context_switch_save(TRISC2_CTX,  gen_cs_32x1024[1]);

load_kernel(L1_TRISC1_BASE, &norm_trisc1_bin);
load_kernel(L1_TRISC2_BASE, &norm_trisc2_bin);

// After norm kernel completes:
context_switch_restore(TRISC1_CTX, gen_cs_32x1024[0]);
context_switch_restore(TRISC2_CTX, gen_cs_32x1024[1]);
// TRISC1 resumes GEMM from saved MOP state
```

**Context switch SRAM capacity:** 32 entries × 1024b = 4 KB — sufficient for 32 simultaneous
kernel contexts. The 8-entry SRAM (gen_cs_8x1024) is a second bank for overflow.

---

## 7. Multi-Tile Parallelism — Grid Mapping

### 7.1 Grid Layout and Compute Resources

```
      X=0        X=1        X=2        X=3
Y=0   TENSIX(0)  TENSIX(5)  TENSIX(10) TENSIX(15)   ← Row A
Y=1   TENSIX(1)  TENSIX(6)  TENSIX(11) TENSIX(16)   ← Row B
Y=2   TENSIX(2)  TENSIX(7)  TENSIX(12) TENSIX(17)   ← Row C
Y=3   DISPATCH_E ROUTER     ROUTER     DISPATCH_W
Y=4   NIU_NE     NIU_N      NIU_N      NIU_NW        ← DRAM bridges

Total compute: 12 tiles × 4 T6 cores = 48 T6 cores
FPU array: 12 × 4 × 256 MACs = 12,288 MACs/cycle (INT16/FP16B)
           12 × 4 × 512 MACs = 24,576 MACs/cycle (INT8 packed)
```

### 7.2 Parallelism Strategies

**Tensor Parallelism (X-axis):** Partition the N (output column) dimension across X=0..3.
Each tile computes N/4 output columns. Requires all-reduce at layer end.

```
X=0: computes output columns 0..N/4-1
X=1: computes output columns N/4..N/2-1
X=2: computes output columns N/2..3N/4-1
X=3: computes output columns 3N/4..N-1

All-reduce: 3 unicast hops (ring) + 1 broadcast = 4 NoC hops ≈ 40 ns
Keep partial sums as INT32 during reduce; descale to INT8 at final step.
```

**Pipeline Parallelism (Y-axis):** Assign different layers to different Y-rows.

```
Y=0 row (4 tiles): Layers 0..L/3    — processes token batch
Y=1 row (4 tiles): Layers L/3..2L/3 — processes previous row's output
Y=2 row (4 tiles): Layers 2L/3..L   — processes previous row's output

Activation transfer: NoC unicast from (X, Y=m) to (X, Y=m+1) — 1 Y-hop
Latency: 1 flit-cycle per hop ≈ 1 ns
```

**Data Parallelism (across all tiles):** Each tile processes a different batch element.
No inter-tile communication required. Best for batch > 1 inference.

### 7.3 NIU-to-Tile Assignment

```
NIU_NE (0,4): feeds compute column X=0 — weight streaming + KV-cache for Y=0..2
NIU_N  (1,4): feeds compute column X=1 — weight streaming
NIU_N  (2,4): feeds compute column X=2 — weight streaming
NIU_NW (3,4): feeds compute column X=3 — weight streaming + activation output

Rule: assign KV-cache traffic to the NIU in the same X-column as the
attention tiles consuming it. X-hops add latency and congest unrelated tiles.
```

### 7.4 Dispatch Tile Role

Dispatch tiles (Y=3, X=0 and X=3) contain their own L1, overlay wrapper, and NIU router.
They are used for:
- Token dispatch to compute rows (sequence scatter)
- All-reduce coordination (sum partial results from X=0..3)
- Synchronization barriers across the grid

**Do NOT use Dispatch tiles for GEMM** — they lack the T6 FPU array.

---

## 8. Common Bottlenecks and Diagnosis

### 8.1 Bottleneck Priority Order

For LLM inference on Trinity, performance bottlenecks occur in this order (most common first):

```
1. DRAM bandwidth          — weight streaming to L1 (esp. INT16/FP16B large K)
2. NoC resp VC buffer      — 4 concurrent 4 KB reads max per NIU
3. TRISC1 FPU starvation   — TRISC0 too slow to feed SRCA
4. DEST double-buffer stall — TRISC2 too slow to drain DEST
5. L1 bank conflict        — misaligned base addresses causing serialization
6. I-cache miss            — kernel binary too large for TRISC cache
7. Overlay CPU overhead    — CSR writes on critical path via CDC
8. Power droop throttling  — INT8 packed 2× switching power
```

### 8.2 Profiling via Cycle Counters

Hardware cycle counters are available via `overlay_tile_counters_with_comparators`
(in `tt_overlay_wrapper`, dm_clk domain):

```c
// Read TRISC thread stall cycles (overlay CPU polling):
uint32_t trisc1_sem_wait_cycles = rd_overlay_counter(TRISC1_SEM_WAIT_CTR);
uint32_t trisc0_l1_stall_cycles = rd_overlay_counter(TRISC0_L1_STALL_CTR);
uint32_t brisc_noc_stall_cycles = rd_overlay_counter(BRISC_NOC_STALL_CTR);

// Interpret:
if (trisc1_sem_wait_cycles > 0.5 * total_cycles)
    // TRISC1 starvation — fix: Rule 4.3
if (trisc0_l1_stall_cycles > 0.2 * total_cycles)
    // L1 bank conflict or NoC delivery not overlapping — fix: §5.4, §3.2
if (brisc_noc_stall_cycles > 0.3 * total_cycles)
    // NoC VC credit stall — fix: §5.2, §5.3
```

### 8.3 NoC Performance Monitor

`noc2axi_perf_monitor.sv` tracks AXI outstanding transaction count:

```c
// Check via NIU register map (base 0x02000000 + perf offset):
uint32_t max_outstanding = rd32(NIU_BASE + PERF_MAX_OUTSTANDING_TXN);
uint32_t cur_outstanding = rd32(NIU_BASE + PERF_CUR_OUTSTANDING_TXN);

// Diagnosis:
if (max_outstanding < 4)
    // SW not issuing enough concurrent DMAs — fix: §5.2 group-of-4
if (max_outstanding == 4 && bandwidth < expected)
    // NoC resp VC buffer is the bottleneck (4 × 16 flits = 64 max) — fix: smaller reads
if (max_outstanding > 16 && write_stalls > 0)
    // AXI master write buffer overflow (only 4 txns) — fix: §16.4
```

### 8.4 L1 Bank Conflict Detection

No hardware counter for L1 bank conflicts. Detect via inference:

```
If TRISC0 stall cycles > expected L1 read time:
  Expected L1 read time for SRCA fill (INT16) = 48 × (128b / 128b per cycle) = 48 cycles
  If actual TRISC0 stall >> 48 cycles → bank conflict likely

Fix: check L1 base addresses for weight and activation buffers.
     Apply 128 B stagger between CH0 and CH1 bases (§16.7).
     Also verify BRISC DMA write address is not aliasing TDMA read address.
```

### 8.5 TRISC I-Cache Miss

```
Symptom: kernel execution time much longer than instruction count predicts.
Diagnosis: count instructions in kernel binary; compare to I-cache size.
  TRISC0/BRISC: 512 instructions max before cache thrash
  TRISC1/TRISC2: 256 instructions max

Fix:
  1. Move CSR initialization code out of hot loop → into overlay CPU launch sequence
  2. Use MOP inner loop (hardware loop unroll) instead of software loop
  3. Split kernel: slow-path initialization in separate binary, hot-path in tight binary
```

---

## 9. Format Selection Quick Guide

### 9.1 Decision Matrix

| Workload | Recommended Format | Rationale |
|----------|-------------------|-----------|
| FFN weights (inference) | **INT8** | 512 MACs/cycle, 2× density vs INT16 |
| FFN weights (fine-tune) | **FP16B** | Gradient range requires float |
| Attention QKV projection | **INT16** | Preserves outlier sign+magnitude |
| KV-cache (seq ≤ 1024) | **INT16** | Fits in L1 entirely |
| KV-cache (seq > 2048) | **INT8 + scale** | 2× DRAM BW saving, < 5% compute overhead |
| Attention score (QK^T) | **FP16B → SFPU softmax** | Needs float range for softmax stability |
| RMSNorm / LayerNorm | **FP16B in SFPU** | SFPU always FP32 internally; FP16B avoids INT→FP round-trip |
| Residual add | **FP16B** | Same — SFPU MAD with no extra round-trip |
| Output projection (final) | **FP16B** | Quantization error accumulates at output |
| Embedding lookup | **INT8** | 1 B/element, dominant in large vocabulary |

### 9.2 Format Code Reference

| Format | Code | DEST Mode | MACs/cycle | SFPU path |
|--------|------|-----------|-----------|-----------|
| FP32 | 4'h0 | FP32 (512 rows) | 256 | Direct LOAD |
| FP16B (BF16) | 4'h5 | FP16 (1024 rows) | 256 | Direct LOAD |
| INT32 | 4'h8 | INT32 (512 rows) | 256 | INT→FP16B→L1→SFPU |
| INT16 | 4'h9 | INT32 (512 rows) | 256 | INT→FP16B→L1→SFPU |
| INT8 | 4'he | INT32 (512 rows) | **512** (packed) | INT→FP16B→L1→SFPU |
| TF32 | 4'h4 | FP32 (512 rows) | 256 | Direct LOAD |

### 9.3 DEST Capacity Limits

```
FP16B input  → FP16 DEST:  1024 rows × 16 cols × 16b = 32 KB
INT16/INT8   → INT32 DEST:  512 rows × 16 cols × 32b = 32 KB

M-tile practical limit:
  FP16B:  512 rows per buffer half → tile M in 512-row chunks
  INT16:  256 rows per buffer half → tile M in 256-row chunks
  INT8:   256 rows per buffer half → same as INT16
```

---

## 10. Performance Recipes by Workload Type

### 10.1 Recipe: Large GEMM (FFN, INT8)

```
Preconditions: K=4096, M=512, N_local=256 (per tile, tensor-parallel across X=0..3)

Step 1: Overlay CPU (before kernel launch)
  - Load INT8 kernel binary to L1
  - Configure ATT: DRAM_WEIGHT → L1_WEIGHT_BASE
  - Set semaphores: SEM_DMA_WEIGHT_DONE=0, SEM_SRCA_FREE=1, etc.
  - Release TRISC reset

Step 2: BRISC (runs concurrently with TRISC pipeline)
  - Load INT8 weights from DRAM: 4096×256×1B = 1 MB
  - Issue in groups of 4 × 4KB: 256 groups → 4 at a time
  - Post SEM_DMA_WEIGHT_DONE after all loads complete

Step 3: TRISC0 (waits for SEM_DMA_WEIGHT_DONE first time only)
  - wrcfg(THCON_UNPACKER0, {INT8, INT8, L1_WEIGHT_BASE})
  - wrcfg(THCON_UNPACKER1, {INT8, INT8, L1_ACT_BASE})
  - Loop: unpack weight tile → SRCA; unpack act tile → SRCB; sem_post(SEM_SRCA_FULL)

Step 4: TRISC1 (pure MOP loop)
  - wrcfg(ALU_FORMAT_SPEC_REG, {INT8, INT8, INT32})
  - wrcfg(ALU_ACC_CTRL, {Fp32=1, INT8_packed=1})
  - wrcfg(MOP_CFG_LOOP0_LEN, k_tiles-1)
  - Loop: sem_wait(SEM_SRCA_FULL); issue_mop(DOTPV); sem_post(SEM_DEST_FULL)

Step 5: TRISC2
  - wrcfg(THCON_PACKER0, {INT32→INT8, L1_OUTPUT_BASE})
  - wrcfg(THCON_PACKER0_2, {DESCALE=1, shift=8})
  - Loop: sem_wait(SEM_DEST_FULL); issue_mop(PACR); sem_post(SEM_SRCA_FREE)
  - After all M-tiles done: sem_post(SEM_OUTPUT_READY)

Step 6: BRISC (after SEM_OUTPUT_READY)
  - Send INT8 output to next Y-row tile via NoC unicast (VC_ACT_UNICAST)
  - Concurrently prefetch next layer's weights into L1_BANK_B
```

### 10.2 Recipe: Attention Computation (INT16 QKV, FP16B Score)

```
Preconditions: seq=2048, d_k=128, 4 heads per tile (tensor-parallel)

L1 layout:
  0x000000 – 0x07FFFF  (512 KB): K-cache INT16 [2048 × 128]
  0x080000 – 0x0FFFFF  (512 KB): V-cache INT16 [2048 × 128]
  0x100000 – 0x10FFFF  (64 KB):  Q buffer  INT16 [256 × 128] (one token tile)
  0x110000 – 0x17FFFF  (448 KB): Score buffer FP16B [256 × 2048]
  0x180000 – 0x1FFFFF  (512 KB): Output AV FP16B [256 × 128]

Compute flow:
  Pass 1 (QK^T, INT16 GEMM):
    TRISC0: unpack Q[seq_t] → SRCB; unpack K[k_t] → SRCA
    TRISC1: DOTPV INT16×INT16 → INT32 DEST
    TRISC2: descale INT32 → FP16B → score[k_t]

  Pass 2 (softmax, SFPU):
    TRISC1: SFPU LOAD score[seq_t] → lreg; SFPMAD (exp/recip polynomial)
    TRISC2: pack lreg → FP16B score

  Pass 3 (AV product, FP16B):
    TRISC0: unpack softmax[k_t] → SRCB; unpack V[k_t] → SRCA
    TRISC1: MVMUL FP16B×INT16 → FP16B DEST
    TRISC2: pack DEST FP16B → L1 output
```

### 10.3 Recipe: All-Reduce After Tensor-Parallel GEMM

```
4 tiles (X=0..3) each hold partial sum in L1 output buffer.
Format: INT32 during reduce, descale to INT8 at final step.

// BRISC on each tile runs this concurrently:
void ring_all_reduce_int32(uint32_t *l1_partial, uint32_t *l1_accum, uint32_t bytes) {

    // Step 1: X=0 sends partial[0] → X=1
    if (my_x == 0) brisc_send(dst_x=1, dst_y=my_y, l1_partial, bytes, VC_ALL_REDUCE);
    if (my_x == 1) { wait_recv(); add_to_accum(l1_accum, recv_buf, bytes); }

    // Step 2: X=1 sends accumulated sum → X=2
    if (my_x == 1) brisc_send(dst_x=2, dst_y=my_y, l1_accum, bytes, VC_ALL_REDUCE);
    if (my_x == 2) { wait_recv(); add_to_accum(l1_accum, recv_buf, bytes); }

    // Step 3: X=2 sends accumulated sum → X=3
    if (my_x == 2) brisc_send(dst_x=3, dst_y=my_y, l1_accum, bytes, VC_ALL_REDUCE);
    if (my_x == 3) { wait_recv(); add_to_accum(l1_accum, recv_buf, bytes); }

    // Step 4: X=3 broadcasts final sum to X=0,1,2
    if (my_x == 3) {
        wr32(CMD_BRCST, CMD_RW_BIT | CMD_BRCST_BIT | (VC_BCAST_WEIGHT << 14));
        // broadcast rectangle: (X=0..2, Y=my_y)
    }
    if (my_x != 3) wait_bcast_recv();

    // Step 5: descale INT32 sum → INT8 output (TRISC2)
    sem_post(SEM_REDUCE_DONE);
}
// Total latency: 3 unicasts + 1 bcast × ~10 ns/hop = ~40 ns
```

---

*End of Document — SW_Performance_Guide_HDD_V0.1 — 2026-03-18*
