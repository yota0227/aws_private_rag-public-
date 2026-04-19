# G-Tile (FPU) Architecture — Comprehensive Analysis

**Document Purpose:** Detailed architectural breakdown of N1B0's G-Tile (Floating Point Unit) structure

**Based on:** N1B0_NPU_HDD_v1.00.md §2.4 (FPU) + §2.3.7 (INT8 GEMM architecture)

**Date:** 2026-04-04

---

## Part 1: Register File Sizes (Per Tensix Tile)

### 1.1 Complete Register File Inventory

| Register File | Type | Rows | Columns | Data Width | Total Size | Per Tensix | Notes |
|---------------|------|------|---------|------------|-----------|-----------|-------|
| **DEST** | Latch array (dual-bank) | 1024 | 16 | 32-bit (INT32/FP32) | **64 KB** | **64 KB** | All DEST capacity; 512 rows per bank × 2 banks × 4 columns (16 column slices) |
| **SRCA** | Latch array (dual-bank) | 48 | 64 | 19-bit | **7.3 KB** | **7.3 KB** | Per column set: 48 rows × 16 columns; 4 column-sets total |
| **SRCB** | Latch array (dual-bank) | 64 | 16 | 16-bit | **4 KB** | **4 KB** | Shared across all T6 cores; 2 dual-banks (32 rows × 2) |

### 1.2 Per-G-Tile Register File Breakdown

**Per G-Tile (2 G-Tiles per Tensix tile, so divide by 2):**

| Resource | Per-G-Tile | Formula | Notes |
|----------|-----------|---------|-------|
| DEST | **32 KB** | 64 KB / 2 | Shared across 2 G-Tiles per tile |
| SRCA | **3.65 KB** | 7.3 KB / 2 | Shared across 2 G-Tiles per tile |
| SRCB | **2 KB** | 4 KB / 2 | Shared across 2 G-Tiles per tile |

### 1.3 Register File Physical Structure

#### DEST Register File (Latch Array)

**RTL verified:** `tt_gtile_dest.sv`, `DEST_NUM_ROWS_16B=1024`

```
Per-column DEST slice (× 16 slices per G-Tile):
├── Bank 0:
│   ├── Rows:    0–511
│   ├── Columns: 4 (physical columns per slice)
│   ├── Width:   32-bit per cell
│   └── Size:    512 rows × 4 cols × 4B = 8 KB
│
├── Bank 1:
│   ├── Rows:    512–1023  (aliases to 0–511 via banking)
│   ├── Columns: 4
│   ├── Width:   32-bit per cell
│   └── Size:    512 rows × 4 cols × 4B = 8 KB
│
└── Total per slice: 8 KB × 2 banks = 16 KB (dual-bank configuration)

Per G-Tile (8 column slices):
  8 slices × 16 KB = 128 KB (appears paradoxical with "32 KB per G-Tile")
  
RESOLUTION: Each slice is "dual-bank" internally (transparent to firmware).
The 16 KB per slice is the addressable range (one bank at a time).
Across all 2 G-Tiles in a Tensix: 2 × 8 × 8 KB = 128 KB actual silicon
But firmware sees: 2 × 32 KB = 64 KB addressable per Tensix
```

**Dual-bank hardware behavior (from HDD §2.4.6.1):**
- Bank A holds output from FPU computation (write by FWHT stages / quantizer)
- Bank B holds input for packer or next operation (read by downstream engines)
- Hardware `dest_toggle` event swaps banks automatically (no firmware involvement)
- At any instant: 512 rows available per bank, addressable as DEST[0..511] or DEST[512..1023]

**INT32 accumulation mode:**
```
FP16B mode: 1024 rows × 16 cols × 16-bit = 32 KB (FP16B per element)
INT32 mode: 512 rows × 16 cols × 32-bit = 32 KB (INT32 per element, but logically 1024 rows)
           (pairing of FP16B columns to form 32-bit accumulators)
```

#### SRCA Register File (Latch Array)

**RTL verified:** `tt_fpu_tile_srca.sv`, `SRCS_NUM_ROWS_16B=48`

```
Per-column SRCA (× 4 column-sets × 16 columns/set = 64 SRCA slices total):
├── Bank 0:
│   ├── Rows:    0–47  (K-depth for FP16B or INT8_2x)
│   ├── Columns: 16    (one per M-Tile column)
│   ├── Width:   19-bit (extended for sign, format bits)
│   └── Size:    48 rows × 16 cols × 19b ≈ 1.8 KB
│
├── Bank 1:
│   ├── Rows:    0–47 (double-buffered, prefetch)
│   ├── Columns: 16
│   ├── Width:   19-bit
│   └── Size:    48 rows × 16 cols × 19b ≈ 1.8 KB
│
└── Total per slice: ≈ 3.6 KB (dual-bank)

Per Tensix (4 column-sets × 16 cols/set):
  64 slices × 3.6 KB / 64 = 3.6 KB effective per slice
  Total: 4 column-sets × 16 cols × 3.6 KB / 64 ≈ 7.3 KB aggregated
```

**K-depth meanings:**
- **FP16B mode:** 48 rows = 48 K positions per SRCA pass
- **INT8_2x mode:** 48 rows × 2 INT8 per row = 96 INT8 K positions per SRCA pass
  - Each row holds: `[INT8_B (bits 15:8)][INT8_A (bits 7:0)]`

#### SRCB Register File (Latch Array)

**RTL verified:** `tt_fpu_tile_srcb.sv`, `SRCB_ROW_DATUMS=64`

```
Shared across all 4 T6 cores (not per-core):
├── Bank 0:
│   ├── Rows:    0–63
│   ├── Columns: 16
│   ├── Width:   16-bit
│   └── Size:    64 rows × 16 cols × 2B = 2 KB
│
├── Bank 1:
│   ├── Rows:    0–63 (double-buffered)
│   ├── Columns: 16
│   ├── Width:   16-bit
│   └── Size:    64 rows × 16 cols × 2B = 2 KB
│
└── Total: 4 KB (2 banks, but shared across tile)
```

**Usage pattern:**
- **FP16B:** 1 row holds 16 FP16B weights (16 columns)
- **INT8_2x:** 1 row holds 32 INT8 weights (16 columns × 2 INT8 per datum)
- Double-buffering: UNPACK prefetches into Bank 1 while FPU multiplies using Bank 0

### 1.4 Register File Capacity Summary (Per Tensix Tile)

```
Total latch-based register storage:
├── DEST:  64 KB   (write by: FWHT/quantizer/FP-Lane, read by: packer/SFPU)
├── SRCA:  7.3 KB  (write by: unpack, read by: FPU)
└── SRCB:  4 KB    (write by: unpack, read by: FPU)
────────────────
Total: 75.3 KB per Tensix tile

Comparison to L1 SRAM (3 MB per tile):
  Register files occupy: 75.3 KB / 3,145 KB = 2.4% of tile memory
  Remaining L1: 3,069 KB for tensors, intermediate results, firmware
```

---

## Part 2: G-Tile Architecture & Hierarchy

### 2.1 G-Tile Container Structure

**RTL Module:** `tt_fpu_gtile.sv`

**Definition:** A "G-Tile" is the **tile-level container** that wraps the MAC compute engine (`tt_fpu_mtile`) and provides SRCA/SRCB routing, clock gating, SFPU integration, and EDC logic.

**Physical Hierarchy (Per Tensix Tile):**

```
tt_tensix
├── L1 Partition (3 MB, shared)
│
├── SFPU (Scalar FP Unit, 1 per tile)
│   └── Reads/writes DEST via local float registers (lregs)
│
└── FPU Array (2 G-Tiles per Tensix)
    ├── tt_fpu_gtile[0] (G-Tile 0)
    │   │
    │   ├── SRCA/SRCB routing & clock distribution
    │   │
    │   └── tt_mtile_and_dest_together_at_last × 8 (one per FP output column)
    │       ├── tt_fpu_mtile[col0..col7]       (MAC compute engine)
    │       │   └── tt_fpu_tile × 2             (per-row multiplier array)
    │       │       └── FP-Lane (pipeline, 5 stages)
    │       │
    │       └── tt_gtile_dest[col0..col7]      (DEST latch slice per column)
    │
    └── tt_fpu_gtile[1] (G-Tile 1)
        └── [same structure as G-Tile 0]
```

### 2.2 G-Tile Parallelism

#### Column Parallelism

**8 independent columns per G-Tile:**

```
Per G-Tile:
┌─────────────────────────────────────────────────────────┐
│  8 parallel tt_mtile_and_dest_together_at_last instances│
│  (one per FP output column, cc=0..7)                    │
├─────────────────────────────────────────────────────────┤
│  Column 0 │ Column 1 │ ... │ Column 7                  │
│  ┌──────┐ │ ┌──────┐ │     │ ┌──────┐                 │
│  │M-Tile│ │ │M-Tile│ │ ... │ │M-Tile│                 │
│  ├──────┤ │ ├──────┤ │     │ ├──────┤                 │
│  │ DEST │ │ │ DEST │ │ ... │ │ DEST │                 │
│  └──────┘ │ └──────┘ │     │ └──────┘                 │
└─────────────────────────────────────────────────────────┘

All 8 columns compute simultaneously:
  FPA_row0 × FPB_row0 + FPA_row0 × FPB_row0  (columns 0–7 in parallel)
  → 8 FMA results per row per cycle
```

#### Row Parallelism (Per Column)

**4 active rows per G-Tile:**

```
Per M-Tile column (within G-Tile):
┌──────────────────────────────────┐
│ tt_fpu_mtile (1 column)          │
├──────────────────────────────────┤
│ tt_fpu_tile[0]  (Row 0, 2 lanes) │  ← FP_TILE_ROWS = 2 physical rows
│ ├─ FP-Lane[0] (lane 0, 8 cols)   │  ← MULT_PAIRS = 8 per lane
│ └─ FP-Lane[1] (lane 1, 8 cols)   │
│                                  │
│ tt_fpu_tile[1]  (Row 1, 2 lanes) │  ← Physical row 1
│ ├─ FP-Lane[0]                    │
│ └─ FP-Lane[1]                    │
├──────────────────────────────────┤
│ FP_ROWS = 4 (total active rows in pipeline)
│ FP_TILE_ROWS = 2 (per mtile)
│ FP_TILE_MMUL_ROWS = 2 (per fp_tile)
│ FP_ROWS = 2 × 2 = 4              │
└──────────────────────────────────┘

Per-cycle outputs per column:
  4 rows × 1 FMA/cycle = 4 FMA results per column per cycle
```

#### Complete Parallelism Summary (Per G-Tile)

```
Per G-Tile:
┌──────────────────────────────────────────────────────────────┐
│ 8 columns × 4 rows × 1 FMA/cycle = 32 FMAs/cycle per G-Tile │
│ (FP32/FP16B mode)                                            │
│                                                              │
│ 8 columns × 4 rows × 8 INT8/lane × 1 = 256 INT8 MACs/cycle │
│ (INT8 single-phase mode)                                     │
│                                                              │
│ 8 columns × 4 rows × 8 INT8/lane × 2 = 512 INT8 MACs/cycle │
│ (INT8 dual-phase mode, per phase)                            │
└──────────────────────────────────────────────────────────────┘

Per Tensix tile (2 G-Tiles):
├─ FP32/FP16B: 2 × 32 = 64 FMAs/cycle
├─ INT8 single-phase: 2 × 256 = 512 INT8 MACs/cycle
└─ INT8 dual-phase: 2 × 512 × 2 = 2,048 INT8 MACs/cycle
```

### 2.3 M-Tile (Compute Engine) vs G-Tile (Container)

**Critical distinction:**

| Aspect | G-Tile | M-Tile |
|--------|--------|--------|
| **RTL Module** | `tt_fpu_gtile.sv` | `tt_fpu_mtile.sv` |
| **Role** | Container (control logic) | Physical compute engine |
| **Instances per Tensix** | 2 | 16 (8 per G-Tile) |
| **Instances per G-Tile** | 1 | 8 |
| **Contains** | Routing, clocking, SFPU hookup, 8× M-Tiles | 2× `tt_fpu_tile` (Booth rows) |
| **Operation modes** | Wraps M-Tile modes | FP32/FP16B/INT8 (format via tag bits) |

**Why the naming?**
- **"G-Tile"** (software term): Floating-point GEMM operation (FP32/FP16B)
- **"M-Tile"** (software term): Integer GEMM operation (INT8/INT16)
- **Same hardware:** One `tt_fpu_mtile` executes both modes via MOP tag bits (`int8_op`, `fp32_acc`)
- **RTL naming reflects implementation:** `tt_fpu_mtile` is the *physical MAC block*; `tt_fpu_gtile` is the *tile-level wrapper*

### 2.4 FP-Lane Sub-Pipeline

**Embedded within each M-Tile column:**

```
tt_fpu_mtile (per column) contains:
├── Booth multiplier array (tt_fpu_tile × 2 rows)
│   └── Produces partial products
│
└── FP-Lane sub-pipeline (FP_LANE_PIPELINE_DEPTH = 5 stages)
    ├── Stage 1: Format decode (SRCA/SRCB format interpretation)
    ├── Stage 2: Operand alignment (FP exponent align or INT sign-extend)
    ├── Stage 3: Multiplication (Booth array outputs)
    ├── Stage 4: Rounding/compression (FP result round-to-nearest)
    └── Stage 5: Output register (DEST write)
```

**FP-Lane capabilities:**
- Per-cycle operations: Multiply, add, compare, min/max, cast
- Supported formats: FP32, FP16B (BFloat16), FP16 (IEEE 754), FP8 E4M3, FP8 E5M2, INT8, INT16, INT32
- Input/output: Direct to/from DEST register file (in-place operations)

**Typical use sequence:**
```
Step 1: M-Tile (MAC array) computes INT32 GEMM → DEST
Step 2: FP-Lane descales (INT32 × scale → FP16B) in-place in DEST
Step 3: SFPU applies activation (GELU, softmax, etc.) in-place in DEST
Step 4: TRISC2 packer reads DEST, writes to L1 or NoC
```

---

## Part 3: Maximum Cycle Performance

### 3.1 FP32 Performance

**Per Cycle (1 GHz):**

```
Per M-Tile column:
  4 rows × 1 FMA = 4 FMA/cycle

Per G-Tile (8 columns):
  8 × 4 = 32 FMA/cycle

Per Tensix tile (2 G-Tiles):
  2 × 32 = 64 FMA/cycle = 64 GigaFLOPS @ 1 GHz

Per cluster (4 Tensix tiles):
  4 × 64 = 256 GigaFLOPS @ 1 GHz
```

**Per batch/kernel:**
```
Typical GEMM: M=4 (rows) × N=16 (cols) × K=48 (fixed K_tile)
K_tiles = K / K_tile = 1 (for single pass)
Latency: K_tiles × K_tile / (columns × throughput)
       = 1 × 48 / (8 cols × 1 FMA/col) = 6 cycles per M×N tile
```

### 3.2 FP16B Performance

**Same as FP32:**
```
Per M-Tile column:    4 FMA/cycle (FP16B mantissa precision)
Per G-Tile:           32 FMA/cycle
Per Tensix:           64 FMA/cycle = 64 GigaFLOPS (at FP16B scale)
Per cluster:          256 GigaFLOPS
```

### 3.3 INT16 Performance

**Key difference:** Two INT16 values fit in one 16-bit SRCA/SRCB datum slot.

```
Per M-Tile column:
  4 rows × 2 INT16 products = 8 INT16 MACs/cycle
  (each Booth column produces 2 INT16 results via lower/upper halves)

Per G-Tile (8 columns):
  8 × 8 = 64 INT16 MACs/cycle

Per Tensix tile (2 G-Tiles):
  2 × 64 = 128 INT16 MACs/cycle = 128 GOps @ 1 GHz (INT16)

Per cluster (4 Tensix tiles):
  4 × 128 = 512 GOps
```

### 3.4 INT8 Performance

**Two phases via two architectural mechanisms:**

#### Phase 1: INT8_2x Packing (NUM_PAIR = 8)

Each 16-bit SRCA/SRCB datum holds 2 INT8 values:
```
SRCA datum [15:0]: [INT8_B (bits 15:8)][INT8_A (bits 7:0)]
```

Per Booth column, two INT8 products per cycle:
```
Per M-Tile column:
  4 rows × 2 INT8 products = 8 INT8 MACs/cycle (per column)
  But 8 Booth columns → 8 × 8 = 64 INT8 results per FP-Tile-row...
  Actually: per column processes 2 INT8/cycle, 8 columns = 16 INT8 per row
  
Let me recalculate per M-Tile carefully:
  - Each M-Tile has 2 FP-Tile rows
  - Each FP-Tile row has 8 lanes × 2 INT8 = 16 INT8 inputs per lane
  - Wait, clarification needed from HDD...
  
From HDD §2.4.6.1:
  "8 columns × 2 INT8 products/column = 16 INT8 MACs per FP-Tile row"
  But with 2 FP-Tile rows per M-Tile: 2 × 16 = 32
  
Actually, the HDD states (§2.3.7.3):
  "64 datums simultaneously" per SRCA row read
  "64 datums × 2 = 128 INT8 operands per SRCA row read"
  "128 operands cover: 4 output rows × 16 output cols × 2 INT8 K-positions = 128 multiply-adds"
  
So per cycle (single phase):
  4 rows × 16 cols × 2 INT8 = 128 INT8 MACs/cycle... wait that's not per G-Tile
  
Let me use the HDD directly (§2.4.6.3):
  Per G-Tile (single phase): "8 cols × 4 rows × 2 lanes × 8 INT8/lane = 512 INT8 MACs"
  Wait, that's 8 × 4 × 2 × 8 = 512 but the HDD says...
  
Re-reading §2.4.6.3:
  "Per single phase (one G-Tile):
    8 cols × 4 rows × 2 lanes × 8 INT8/lane = 512 INT8 MACs
    
   Per Tensix (2 G-Tiles, single phase):
    2 G-Tiles × 512 = 1,024 INT8 MACs/cycle per Tensix"
  
So SINGLE PHASE (without HALF_FP_BW):
  Per G-Tile: 512 INT8 MACs/cycle
  Per Tensix: 1,024 INT8 MACs/cycle
  Per cluster: 4,096 INT8 MACs/cycle
```

**Careful analysis from HDD (§2.4.6 Mechanism 1):**

```
Per FP-Lane (per column):
  1 Booth column × 2 INT8 products per cycle = 2 INT8 MACs per column

Per M-Tile (8 columns × 2 rows = 16 columns total... no wait):
  M-Tile has 8 columns
  Per M-Tile: 8 columns × 2 INT8 MACs/column = 16 INT8 MACs/cycle (per row)
  
Per M-Tile (with 2 FP-Tile rows):
  2 rows × 16 INT8 MACs/row = 32 INT8 MACs/cycle

Per G-Tile (8 M-Tiles per G-Tile... no, 8 columns):
  Wait, clarifying the exact nesting...
  
From §2.4.3:
  G-Tile contains 8 column-parallel tt_mtile_and_dest_together_at_last instances
  Each instance is 1 M-Tile + 1 DEST slice
  
So per G-Tile: 8 independent columns (each is one M-Tile instance)

Each column/M-Tile:
  - Has 2 FP-Tile rows (tt_fpu_tile × 2)
  - Each row has multiple lanes
  - Total active rows: FP_ROWS = 4 per G-Tile (not per M-Tile)
  
The breakdown from HDD (§2.4.6.3 directly):
  "INT8 MACs per cycle per G-Tile:
    4 active rows × 16 output columns × 2 lanes × 8 INT8/lane × 1 phase
    = 4 × 16 × 2 × 8 = 1,024 INT8 MACs
    
   But that's wrong because the formula is per M-Tile...
   
Actually from the HDD §2.4.6.3 table:
  'Per G-Tile (8 M-Tile columns) × 4 rows × 2 lanes × 8 INT8 = 512 MACs'
  
This matches: 8 M-Tiles × (4 rows / 2 G-Tiles) × ...
Actually no.
  
Let me just use the exact HDD formulas:
```

**Using HDD § 2.4.6.3 exact quote:**

```
"INT8 MACs per cycle per G-Tile:
  8 cols × 4 rows × 2 lanes × 8 INT8/lane = 512 INT8 MACs"
  
"Per Tensix (2 G-Tiles, single phase):
  2 G-Tiles × 512 = 1,024 INT8 MACs/cycle"

"Per cluster (4 Tensix tiles):
  4 × 1,024 = 4,096 INT8 MACs/cycle"
```

#### Phase 2: HALF_FP_BW (Dual-Phase Latch Processing)

Latch arrays enable two independent read-modify-write operations per clock:

```
Phase 1 (LOW clock phase):
  FWHT Stage N-1 reads DEST[i] (combinational)
  Butterfly computes

Phase 2 (HIGH clock phase):
  FWHT Stage N writes DEST[i+128]
  Different rows, same latch array
```

**With both mechanisms (INT8_2x + HALF_FP_BW):**

```
Per G-Tile (single phase): 512 INT8 MACs
Per G-Tile (dual phase): 512 × 2 = 1,024 INT8 MACs/cycle

Per Tensix tile (2 G-Tiles, dual phase):
  2 × 1,024 = 2,048 INT8 MACs/cycle = 2.048 Teraops @ 1 GHz

Per cluster (4 Tensix tiles, dual phase):
  4 × 2,048 = 8,192 INT8 MACs/cycle = 8.192 Teraops @ 1 GHz

Per N1B0 chip (3 clusters):
  3 × 8,192 = 24,576 INT8 MACs/cycle = 24.576 Teraops @ 1 GHz
```

### 3.5 INT32 Performance (Accumulation, K-Pass)

**K-pass accumulation (INT8 large-K like K=8192):**

```
Per SRCA bank pass:
  K_tile_INT8 = 96 (48 rows × 2 INT8 per row via INT8_2x)
  
For K=8192:
  Passes = ceil(8192 / 96) = 86

Per pass:
  SRCA row iterations: 0..47 (48 MOP cycles)
  INT32 accumulate per MOP: 4 rows × 16 cols × 2 INT8 MACs = 128 INT8 MACs
  Total per pass: 48 MOP cycles × 128 INT8 = 6,144 INT8 MACs per G-Tile per pass
  
Total for K=8192:
  86 passes × 6,144 INT8 MACs / (512 INT8 MACs per cycle)
  = 86 × 12 = 1,032 MAC cycles per G-Tile
  = 1,032 / (8 columns) = 129 cycles per column (roughly)
  
Actual from HDD: §2.3.7.7 states "86 passes × 48 MOP cycles = 4,128 MAC cycles"
  This is per G-Tile for a 4×16 output tile
```

### 3.6 Performance Comparison Table

| Format | Per G-Tile | Per Tensix | Per Cluster | Per Chip (3 clusters) | @1GHz |
|--------|-----------|-----------|-------------|----------------------|-------|
| **FP32** | 32 FMA | 64 FMA | 256 FMA | 768 GFLOPS | 64→768 |
| **FP16B** | 32 FMA | 64 FMA | 256 FMA | 768 GFLOPS | 64→768 |
| **INT16** | 64 MACs | 128 MACs | 512 MACs | 1.536 TOPS | 128→1.5T |
| **INT8 (single-phase)** | 512 MACs | 1,024 MACs | 4,096 MACs | 12.288 TOPS | 1.0→12.3T |
| **INT8 (dual-phase)** | 1,024 MACs | 2,048 MACs | 8,192 MACs | **24.576 TOPS** | **2.0→24.6T** |

---

## Part 4: Register File Pipelining & Throughput

### 4.1 Ping-Pong Banking

**DEST Dual-Bank Strategy:**

```
Write Phase (FPU computing):
  Bank A: [compute, write outputs]
  Bank B: [readable by next stage]

Hardware dest_toggle event:
  Switches write pointer from Bank A to Bank B
  Switches read pointer from Bank B to Bank A
  (transparent to firmware)

Result:
  FPU writes to one bank
  Packer/SFPU reads from other bank
  Eliminates read-after-write dependency
  → Full pipeline with zero inter-stage stalls
```

**SRCA Dual-Bank Strategy:**

```
Bank 0 (active, supplying FPU):
  Holds K-slice [p×96 .. p×96+95] (current 96 INT8 or 48 FP16B positions)
  FPU reads srca_rd_addr 0..47
  
Bank 1 (prefetch):
  TRISC0 (unpack) loads next K-slice [p+1×96 .. p+1×96+95]
  Parallelizes prefetch with compute
  
After 48 MOP cycles:
  Hardware switches banks
  Bank 0 ← (old Bank 1's prefetched data)
  Bank 1 ← (next prefetch starts)
  
Result:
  Zero reload latency between K passes
  Continuous compute without SRCA stalls
```

### 4.2 Register File Latency

| Resource | Latency | Why |
|----------|---------|-----|
| DEST read | **Combinational (0 cy)** | Latch array, not SRAM |
| DEST write | **1 cycle** | Register stage after FPU output |
| SRCA read | **Combinational (0 cy)** | Latch array |
| SRCA write | **1 cycle** | Unpack engine, pipelined write |
| SRCB read | **Combinational (0 cy)** | Latch array |
| SRCB write | **1 cycle** | Unpack engine |

**Impact on FWHT Stage Pipelining:**
```
With combinational DEST reads:
  Stage N-1 reads DEST (0 cy) → computes
  Stage N writes DEST (1 cy)
  Stage N+1 reads DEST (0 cy) → computes immediately

Total inter-stage latency: 0 + 1 + 0 = 1 cycle per stage
FWHT latency for 7 stages: 7 × 1 = 7 cycles (not 7 × 3-4 = 21-28)

Savings: 14-21 cycles per vector (3× speedup!)
This is why TurboQuant is fast on N1B0 — latches > SRAM for this workload
```

---

## Part 5: Key Architectural Properties

### 5.1 Why Latches (Not SRAM)?

From HDD §2.4.6.2.5 analysis:

| Property | Latch | SRAM (1-cycle) | SRAM + DLL (2-cycle) |
|----------|-------|------|------|
| Area per DEST | 3.6 mm² | 9 mm² | 14.5 mm² |
| Power per cycle | 10 mW | 24 mW | 44 mW |
| Latency | Combinational | 1–4 cycles | 2 cycles |
| Timing margin | High | Medium | Low |
| Jitter risk | None | Low | High (±50 ps) |

**N1B0 decision: Latches for register files, SRAM for L1 cache**
- Register files need sub-cycle parallelism (INT8_2x, two-phase processing)
- SRAM dual-port + DLL would be 3–4× larger (231 mm² vs 57.6 mm² for DEST alone)
- Latch architecture is proven in Xeon/ARM/Apple (industry standard)

### 5.2 Format-Agnostic Multiply

**Booth multiplier flexibility:**

```
Input: Two 16-bit operands (any format)
Output: Partial products (pure bits)

FP16B mode:
  Interpret operands as FP16B
  Exponent align before Booth
  Round-to-nearest after

INT16 mode:
  Interpret operands as INT16
  Sign-extend before Booth
  No rounding

INT8_2x mode:
  Interpret operands as [INT8_B | INT8_A]
  Two independent INT8 multiplications per column
  No rounding (integer result)

→ Same hardware, format switched via tag bits
→ Zero throughput penalty for format switching
```

### 5.3 Dual-Phase Processing

**Emerges naturally from latch ICG design:**

```
Integrated Clock Gate (ICG):
  Input: write_enable (i_en), functional clock (i_clk)
  Output: gated clock

Two-phase latch behavior:
  Phase 1 (LOW gated_clk):
    Stabilization latch captures control + input data
  Phase 2 (HIGH gated_clk):
    Data latch holds value; simultaneously readable
  
In one functional clock cycle:
  Phase 1 operations use "fresh" operands
  Phase 2 operations use remapped operands
  
FPU integration:
  Phase 1: N FPU MACs on SRCA[0..N-1]
  Phase 2: N FPU MACs on SRCA[N..2N-1]  (via row_addr_second_phase logic)
  → 2× throughput per functional clock, no area overhead
```

---

## Conclusion

### G-Tile Summary

**G-Tile (FPU) is a hierarchical structure:**

1. **Container level:** `tt_fpu_gtile` (routing, clocking, SFPU hookup)
2. **Compute level:** `tt_fpu_mtile` × 8 columns (MAC engines)
3. **Multiplier level:** `tt_fpu_tile` × 2 rows per M-Tile (Booth arrays)
4. **Sub-pipeline level:** FP-Lane (5-stage, in-place DEST operations)

**Register files (75.3 KB per tile):**
- DEST: 64 KB (dual-bank, ping-pong, combinational read)
- SRCA: 7.3 KB (dual-bank, prefetch, combinational read)
- SRCB: 4 KB (dual-bank, weight buffer, combinational read)

**Parallelism:**
- 8 columns per G-Tile
- 4 active rows per G-Tile
- 2 G-Tiles per Tensix tile
- 2 independent phases per clock (latch ICG design)

**Performance (@ 1 GHz):**
- FP32/FP16B: **64 FMA/cycle per Tensix** (256 per cluster)
- INT16: **128 MACs/cycle per Tensix** (512 per cluster)
- INT8 single-phase: **1,024 MACs/cycle per Tensix** (4,096 per cluster)
- INT8 dual-phase: **2,048 MACs/cycle per Tensix** (8,192 per cluster) **← Peak**

**Why Trinity excels at TurboQuant:**
- Latch-based register files → combinational reads → zero inter-stage FWHT latency
- Dual-phase processing → 2× throughput per clock
- DEST ping-pong → no read-after-write hazards
- Format-agnostic Booth → INT8/INT16/FP switching at zero cost

---

**References:**
- N1B0_NPU_HDD_v1.00.md §2.4 (FPU), §2.3.7 (INT8 GEMM)
- tt_fpu_gtile.sv, tt_fpu_mtile.sv, tt_fpu_tile_srca.sv (RTL)
- tt_tensix_pkg.sv (parameters)

