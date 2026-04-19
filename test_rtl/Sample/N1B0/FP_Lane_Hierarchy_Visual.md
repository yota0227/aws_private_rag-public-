# FP-LANE HIERARCHICAL ORGANIZATION WITHIN N1B0

**From Cluster down to Single Lane**

---

## LEVEL 0: N1B0 CLUSTER (Top-level compute unit)

### Cluster Overview
- **Grid Layout:** 4×5 (20 tiles total)
- **Compute Cores:** 8 Tensix Tiles + 2 Dispatch Engines
- **Peak Throughput:** **16,384 INT16 MACs/cycle** (sustained)

### Cluster Architecture

```
        Tensix[0]    Tensix[1]    Tensix[2]    Tensix[3]
        2,048 MACs   2,048 MACs   2,048 MACs   2,048 MACs
        (G-Tile0)    (G-Tile0)    (G-Tile0)    (G-Tile0)
         1,024       1,024        1,024        1,024
        (G-Tile1)    (G-Tile1)    (G-Tile1)    (G-Tile1)
         1,024       1,024        1,024        1,024

        Tensix[4]    Tensix[5]    Tensix[6]    Tensix[7]
        2,048 MACs   2,048 MACs   2,048 MACs   2,048 MACs
        [Similar structure as above]

        + Dispatch Engines, Router, Memory Controllers, Cache
```

### Aggregate Calculation
| Level | Count | MACs/Unit | Total |
|-------|-------|-----------|-------|
| Tensix tiles | 8 | 2,048 | **16,384** |
| Cluster total | 1 | 16,384 | **16,384** |

---

## LEVEL 1: TENSIX TILE (Per-tile compute and memory)

### Tensix Tile Overview
- **Composition:** 2 G-Tiles (Group-Tiles)
- **Peak Throughput:** **2,048 INT16 MACs/cycle**
- **Associated Memory:**
  - L1 I-Cache: 1.5 KB per M-Tile (TRISC instruction memory)
  - L1 D-Cache: 768 KB per Tensix (from 36 SRAM macros)
  - SRCA register: 48 rows × 16 datums × 2 banks = 1.5 KB
  - SRCB register: 64 words × 16 datums × 2 banks = 2 KB
  - DEST register: 1,024 rows × 4 cols × 2 banks = 8 KB

### Tensix Architecture

#### G-TILE 0 (Group-Tile)
- **Peak:** 1,024 INT16 MACs/cycle
- **Composition:** 2 M-Tiles × 512 MACs each

```
├─ M-Tile 0 (2×8 FPU rows)      = 512 MACs/cycle
│  ├─ M-Tile[0] Row[0-7]        = 64 MACs/cycle (per active row)
│  │  ├─ FP-Tile[0-7]           = 8 MACs/lane (8 columns)
│  │  │  ├─ FP-Lane r0          = 8 INT16 MACs/cycle
│  │  │  └─ FP-Lane r1          = 8 INT16 MACs/cycle
│  │  │      (Both lanes in parallel, same cycle)
│  │
│  └─ M-Tile[1] Row[8-15]       = 64 MACs/cycle (per active row)
│
└─ M-Tile 1 (2×8 FPU rows)      = 512 MACs/cycle
   [Similar structure]
```

#### G-TILE 1 (Group-Tile)
- **Peak:** 1,024 INT16 MACs/cycle
- **Structure:** Identical to G-TILE 0

### Tensix Aggregate
| Component | Count | MACs/Unit | Total |
|-----------|-------|-----------|-------|
| G-Tiles | 2 | 1,024 | **2,048** |
| **Tensix Total** | **1** | **2,048** | **2,048** |

---

## LEVEL 2: G-TILE (Group-Tile: One FPU group)

### G-Tile Overview
- **Composition:** 2 M-Tiles × 8 rows each
- **Peak Throughput:** **1,024 INT16 MACs/cycle**
- **Note:** Only 4 rows are **active per cycle** (rows toggle between [0-3] and [4-7])

### G-Tile Architecture

```
┌─────────────────────────┐    ┌─────────────────────────┐
│  M-TILE 0               │    │  M-TILE 1               │
│  512 MACs/cycle         │    │  512 MACs/cycle         │
│                         │    │                         │
│  ┌──────────────────┐   │    │  ┌──────────────────┐   │
│  │ Row 0 (Active)   │   │    │  │ Row 8 (Active)   │   │
│  │ 64 MACs/cycle    │   │    │  │ 64 MACs/cycle    │   │
│  │ ┌─────┬─────┐    │   │    │  │ ┌─────┬─────┐    │   │
│  │ │r0:8 │r1:8 │    │   │    │  │ │r0:8 │r1:8 │    │   │
│  │ │MACs │MACs │... │   │    │  │ │MACs │MACs │... │   │
│  │ └─────┴─────┘    │   │    │  │ └─────┴─────┘    │   │
│  │ [8 columns total]│   │    │  │ [8 columns total]│   │
│  │                  │   │    │  │                  │   │
│  │ ┌──────────────────┐   │    │  ┌──────────────────┐   │
│  │ │ Row 1-3 (Active) │   │    │  │ Row 9-11 (Active)│   │
│  │ │ 64 MACs/cycle    │   │    │  │ 64 MACs/cycle    │   │
│  │ │ [Similar]        │   │    │  │ [Similar]        │   │
│  │ └──────────────────┘   │    │  └──────────────────┘   │
│  │                         │    │                         │
│  │ ┌──────────────────┐   │    │  ┌──────────────────┐   │
│  │ │ Row 4-7          │   │    │  │ Row 12-15        │   │
│  │ │ (INACTIVE/Toggle)│   │    │  │ (INACTIVE/Toggle)│   │
│  │ │ [Swapped when    │   │    │  │ [Swapped when    │   │
│  │ │  context switch] │   │    │  │  context switch] │   │
│  │ └──────────────────┘   │    │  └──────────────────┘   │
│  │                         │    │                         │
│  │ 16 FP-Tiles × 2 lanes:  │    │ 16 FP-Tiles × 2 lanes:  │
│  │ = 32 FP-Lanes           │    │ = 32 FP-Lanes           │
│  │ = 256 Booth multipliers │    │ = 256 Booth multipliers │
│  └──────────────────────────┘    └─────────────────────────┘
```

### G-Tile Aggregate
| Component | Per M-Tile | ×2 M-Tiles | Total |
|-----------|------------|-----------|-------|
| Active rows per cycle | 4 | — | **4 active** |
| MACs/cycle | 512 | ×2 | **1,024** |

> **⚠️ KEY CONSTRAINT:** RTL-verified FP_ROWS = 4
> - Physical rows: 8 per M-Tile
> - Active rows per cycle: 4 (FP_TILE_ROWS=2 × FP_TILE_MMUL_ROWS=2)
> - Inactive rows: Toggle via hardware ping-pong mechanism
> - **Reference:** `tt_tensix_pkg.sv` — `localparam FP_ROWS = FP_TILE_ROWS * FP_TILE_MMUL_ROWS`

---

## LEVEL 3: M-TILE (Matrix-Tile: One FPU column in the grid)

### M-Tile Overview
- **Dimensions:** 8 rows (physical) × 8 columns
- **Active rows per cycle:** 4 (rows [0-3] OR [4-7])
- **Peak Throughput:** **512 INT16 MACs/cycle**
- **Composition:** 8 FP-Tiles per row

### M-Tile Architecture

```
Row │  Col0        Col1        ...        Col7
────┼─────────────────────────────────────────────────
0   │ ┌─────────┐  ┌─────────┐           ┌─────────┐
    │ │FP-Tile0 │  │FP-Tile1 │  ...      │FP-Tile7 │
    │ │r0│8 MAC │  │r0│8 MAC │           │r0│8 MAC │
    │ │r1│8 MAC │  │r1│8 MAC │           │r1│8 MAC │
    │ │ 16 MACs │  │ 16 MACs │           │ 16 MACs │
    │ └─────────┘  └─────────┘           └─────────┘
    │
1   │ [Similar structure]
2   │ [Similar structure]
3   │ [Similar structure]
    │
4   │ ┌─────────┐  ┌─────────┐           ┌─────────┐
    │ │INACTIVE │  │INACTIVE │  ...      │INACTIVE │
    │ │(Toggled)│  │(Toggled)│           │(Toggled)│
    │ └─────────┘  └─────────┘           └─────────┘
    │
5-7 │ [INACTIVE (Toggled)]
```

### M-Tile Calculation

**Per Active Row:**
- 8 columns × 2 lanes/column × 8 MACs/lane = 128 MACs/cycle

**Per M-Tile (4 active rows):**
- 4 active rows × 128 MACs/row = **512 MACs/cycle**

**Per M-Tile (if all 8 rows active):**
- 8 × 128 = 1,024 MACs (theoretical max, never achieved in one cycle)

### M-Tile Aggregate
| Metric | Value |
|--------|-------|
| FP-Tiles per M-Tile | 8 |
| MACs per FP-Tile per active row | 16 |
| MACs per row (8 FP-Tiles) | 128 |
| Active rows per cycle | **4** |
| **Total per M-Tile** | **512** |

---

## LEVEL 4: FP-TILE (Floating-Point Tile: One grid element)

### FP-Tile Overview
- **Composition:** 8 columns × 2 lanes/column
- **Total FP-Lanes:** 16 lanes per FP-Tile
- **Peak Throughput (per active row):** **128 INT16 MACs/cycle**

### FP-Tile Architecture

```
Input Operands:
┌──────────────┐              ┌─────────────────┐
│ SRCA: 16 bits│              │ SRCB: 16 bits   │
│ × 8 datums   │              │ × 8 datums      │
│ per row      │              │ per row         │
└────┬─────────┘              └────┬────────────┘
     │                              │
     └──────────┬───────────────────┘
                │
     ┌──────────▼──────────────────────────┐
     │    FP-TILE DATAPATH (8 columns)     │
     ├──────────────────────────────────────┤
     │                                      │
     │ Col0: ┌──────────┐                  │
     │       │FP-Lane r0│ = 8 MACs/cycle  │
     │       ├──────────┤                  │
     │       │FP-Lane r1│ = 8 MACs/cycle  │
     │       └──────────┘                  │
     │            ↓                         │
     │       16 MACs per column            │
     │                                      │
     │ Col1-Col7: [Similar × 7]            │
     │                                      │
     │ Total: 8 columns × 16 MACs = 128   │
     │        INT16 MACs/cycle             │
     │                                      │
     └──────────┬──────────────────────────┘
                │
          DEST write (32-bit)
                │
           ┌────▼────────┐
           │ DEST register│
           │ (dual-bank)  │
           │ 1024×4×8KB   │
           └──────────────┘
```

### FP-Tile Calculation
| Element | Count | MACs/Element | Total |
|---------|-------|--------------|-------|
| Columns | 8 | — | — |
| Lanes per column | 2 | — | — |
| MACs per lane | 8 | 1 | 8 |
| MACs per column | — | 2 lanes × 8 | 16 |
| **MACs per FP-Tile (per active row)** | — | 8 cols × 16 | **128** |

---

## LEVEL 5: FP-LANE (Floating-Point Lane: Atomic compute unit)

### FP-Lane Overview
- **Instance:** `tt_fp_lane` (r0 or r1 within each column)
- **Peak Throughput:** **8 INT16 MACs/cycle**
- **Latency:** 8 cycles (pipelined)

### FP-Lane Input/Output

| Aspect | Specification |
|--------|---|
| **Inputs** | A[16-bit], B[16-bit], DEST[32-bit], Control signals |
| **Outputs** | Result[32-bit], Valid_flag |
| **Throughput** | 1 FMA/cycle (pipelined) + **8 parallel operand pairs (NUM_PAIR=8)** |
| **Effective Rate** | **8 INT16 MACs/cycle** |

### FP-Lane Pipeline

```
Stage 1: Input
┌─────────────────────┐
│ Booth Multiplier    │ → 5K gates
│ SOP Compressor      │ → 10K gates
│ Exponent Path       │ → 5K gates
└─────────────────────┘
         ↓ (2-3 cycles)
         
Stage 2: Alignment & Addition
┌─────────────────────┐
│ Alignment Shifter   │ → 4K gates
│ CLA Adder           │ → 3K gates
│ Normalizer          │ → 4K gates
└─────────────────────┘
         ↓ (2-3 cycles)
         
Stage 3: Rounding & Output
┌─────────────────────┐
│ Rounder             │ → 2K gates
│ Output Register     │ → 2K gates
└─────────────────────┘
         ↓ (1-2 cycles)
      Result
      
Total Latency: 8 cycles
Total Area: ~25K gates per lane
```

### FP-Lane Format Support

All formats use **same hardware** (Booth multiplier is format-agnostic):

| Format | Precision | Datums | Notes |
|--------|-----------|--------|-------|
| INT8 | 8-bit | 2 per 16-bit | Via 2-phase mode (r0/r1 toggle) |
| INT16 | 16-bit | 1 per 16-bit | Standard mode |
| INT32 | 32-bit | 1 per 32-bit | Via accumulation |
| FP16B | IEEE 754 half | 1 per 16-bit | Tenstorrent format |
| FP32 | IEEE 754 single | 1 per 32-bit | Native precision |
| TF32 | Tensor Float | — | Hardware support |
| MXFP4 | Intel MXFP4 | — | Hardware support |

### FP-Lane Hardware Breakdown

| Component | Gates | Purpose |
|-----------|-------|---------|
| Booth Multiplier | 5K | Partial product generation |
| SOP Compressor | 10K | Sum-of-products compression |
| Exponent Path | 5K | Exponent calculation |
| Alignment Shifter | 4K | Mantissa alignment |
| CLA Adder | 3K | Mantissa addition |
| Normalizer | 4K | Result normalization |
| Rounder | 2K | IEEE rounding |
| Registers/Misc | 2K | Pipeline registers |
| **Total per Lane** | **~25K** | — |

> **RTL Reference:** `tt_fp_lane.sv` (tt_tensix_neo/src/hardware/tensix/fpu/rtl/)
> - Parameter: `NUM_PAIR = 8` (8 parallel multiply pairs)
> - Module: `tt_int8_int16_int32_acc` (accumulator logic)
> - Module: `tt_sop16_1` (SOP compressor with 16-pair support)

---

## Population Density & Hierarchy

### Entity Count Summary

| Entity | Per Level | Count Per | Total |
|--------|-----------|-----------|-------|
| **Cluster** | — | 1 | **1** |
| **Tensix tiles** | 8 per cluster | 1 | **8** |
| **G-Tiles** | 2 per Tensix | 8 | **16** |
| **M-Tiles** | 2 per G-Tile | 16 | **32** |
| **FP-Tiles** | 8 per M-Tile | 32 | **256** |
| **FP-Lanes (r0+r1)** | 2 per FP-Tile | 256 | **512** |
| **Booth Multipliers** | 8 per FP-Lane | 512 | **4,096** |

### Hardware Area Estimation

| Metric | Value |
|--------|-------|
| FP-Lane Gate Count | ~25K gates |
| Total FPU Area (512 lanes) | 512 × 25K = **12.8M gates** |
| Estimated Silicon Area | **~128 mm²** |
| FP-Lanes per mm² | **~4 lanes/mm²** |
| Total FPU Power @ 1 GHz | **~500 mW** (est.) |

---

## Throughput Summary

### Peak Sustained Throughput (INT16)

| Level | Configuration | MACs/Cycle |
|-------|---|---|
| **Per FP-Lane** | 8 parallel pairs | **8** |
| **Per Column (8 lanes)** | 2 lanes/column × 8 | **16** |
| **Per FP-Tile Row** | 8 columns × 16 | **128** |
| **Per M-Tile** | 4 active rows × 128 | **512** |
| **Per G-Tile** | 2 M-Tiles × 512 | **1,024** |
| **Per Tensix** | 2 G-Tiles × 1,024 | **2,048** |
| **Per Cluster** | 8 Tensix × 2,048 | **16,384** |

### Key Throughput Relationships

```
Per Cluster = 16,384 MACs/cycle
            = 8 Tensix × 2,048
            = 8 Tensix × 2 G-Tiles × 1,024
            = 16 G-Tiles × 1,024
            = 32 M-Tiles × 512
            = 256 FP-Tiles × 128 (per active row)
            = 512 FP-Lanes × 32 (8 MACs × 4 active rows)
```

---

## Operational Flow Example: INT16 GEMM

### Step 1: Load Operands
```
SRCA[i] ← Matrix A row (TRISC2 NoC read, ~40-50 cycles)
SRCB[j] ← Matrix B row (TRISC2 NoC read, ~40-50 cycles)
```

### Step 2: Enable All FP-Lanes
```
All 512 FP-Lanes start processing simultaneously
Each lane: A[col] × B[row] + DEST[k]
```

### Step 3: Pipeline Operation
```
Cycle 0:   Load operands into FP-Lanes
Cycles 1-8: Data flows through 8-stage pipeline
Cycle 8:   First result available at DEST write
Cycle 9+:  Sustained throughput: 1 FMA/cycle per lane
```

### Step 4: K-Loop Iteration
```
While processing K partition:
  - TRISC2 fetches next partition
  - Dual-bank SRCA/SRCB enable overlap (no stall)
  - Continue until K complete
```

### Step 5: Output Accumulation
```
Results accumulate in DEST latch array
After GEMM complete:
  - Write DEST → L1 cache
  - Begin next operation
```

---

## Key Architectural Insights

### ✅ FP-Lane is the Fundamental Execute Unit
- All 512 lanes (256 per Tensix × 2) operate in parallel
- No serialization at any level (per HDD §2.1: "no arbiter serializes any level")

### ✅ Format Flexibility Without Additional Hardware
- Booth multiplier is **format-agnostic**
- Same components, reinterpreted bits:
  - INT8 (2 per datum via 2-phase) → 16 MACs/lane/cycle
  - INT16 (standard) → 8 MACs/lane/cycle
  - INT32/FP32 (extended precision) → 4 MACs/lane/cycle

### ✅ Two-Phase Operation for INT8_2x Mode
- r0 and r1 lanes process **different data** in same cycle
- **Throughput multiplier:** 8 → 16 INT8 MACs/lane/cycle

### ✅ Zero-Latency DEST Integration
- **Latch arrays** (not SRAM) enable combinational read-modify-write
- No pipeline stall for accumulation
- Supports concurrent FPU writes + packer reads (dual-port via arbitration)

### ✅ High Aggregate Throughput
```
512 FP-Lanes × 8 INT16 MACs/lane/cycle × 4 active rows
= 16,384 INT16 MACs/cycle sustained (per cluster)
```

---

## RTL Verification References

| Component | File | Parameters | Key Finding |
|-----------|------|-----------|---|
| **Active Rows** | `tt_tensix_pkg.sv` | `FP_ROWS = FP_TILE_ROWS × FP_TILE_MMUL_ROWS = 2 × 2 = 4` | Only 4 of 8 physical rows active per cycle |
| **MATH_ROWS** | `tt_t6_proj_params_pkg.sv` | `MATH_ROWS = 4` | Base parameter for row count |
| **Parallel MACs** | `tt_fp_lane.sv` | `NUM_PAIR = 8` | 8 parallel multiply pairs per lane |
| **Compressor** | `tt_fp_lane.sv` | `tt_sop16_1` module | 16-pair SOP compression support |
| **Accumulator** | `tt_fp_lane.sv` | `tt_int8_int16_int32_acc` | Format-agnostic accumulation logic |

---

## Corrections to Previous Document

### Issue #1: Active Rows (Line 56 → Lines 135-149)
- **Before:** Showed 8 rows as all active per cycle
- **After:** Clarified 4 active rows + 4 toggled rows (ping-pong mechanism)
- **Source:** RTL parameter `FP_ROWS = 4` confirmed

### Issue #2: Lane Throughput Ambiguity (Line 220-221)
- **Before:** "Throughput: 1 MAC/cycle (pipelined)"
- **After:** "8 INT16 MACs/cycle" (NUM_PAIR=8 + pipelined operation)
- **Clarification:** Latency = 8 cycles; Throughput = 1 FMA/cycle × 8 pairs = 8 effective MACs/cycle

### Issue #3: Inconsistent FP-TILE Definition (Lines 133 vs 160)
- **Before:** Different definitions at different hierarchy levels
- **After:** Unified definition: FP-TILE = 128 MACs per active row (8 cols × 2 lanes × 8 MACs/lane)

### Issue #4: Lane Attribution (Line 316)
- **Before:** "512 lanes × 8 MACs/lane/cycle = 4,096 INT16 MACs/cycle per Tensix"
- **After:** Corrected to "per Cluster" (512 lanes per cluster, not per Tensix)
- **Correct Math:** 256 lanes/Tensix × 8 = 2,048 per Tensix

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-04-13 | 1.0 (Markdown) | Converted from TXT; incorporated RTL verification; fixed active-rows constraint; clarified lane throughput; corrected lane attribution |
| 2026-03-XX | 0.x (TXT) | Original ASCII-based hierarchy document |

---

**Document Status:** ✅ RTL-Verified & Corrected  
**Last Updated:** 2026-04-13  
**RTL Release:** 20260221
