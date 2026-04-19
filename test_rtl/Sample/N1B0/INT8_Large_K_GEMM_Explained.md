# INT8 Large-K GEMM — K=8192 Hardware Architecture

**Date:** 2026-04-04  
**Source:** N1B0 HDD v1.00, §2.3.7  
**Purpose:** Explain how unlimited K dimension GEMM is achieved for INT8 workloads

---

## Executive Summary

Trinity N1B0 supports **arbitrarily large K dimension** for INT8 GEMM through a clever combination of three hardware mechanisms:

1. **INT8_2x Packing**: Two INT8 values per 16-bit datum → 2× K throughput
2. **DEST INT32 Accumulate-in-Place**: Persistent partial sums across K passes
3. **Firmware-Controlled Multi-Pass K Loop**: No hardware K counter or limit

For K=8192 specifically: **86 firmware passes × 48 MOP cycles = 4,128 MAC cycles per G-Tile**

---

## Part 1: The Hardware Mechanisms

### 1.1 INT8_2x Packing — 2× K Throughput

#### What It Is

Two INT8 values packed into one 16-bit SRCA/SRCB datum:

```
16-bit SRCA/SRCB datum (INT8_2x format):
┌─────────────────────┬─────────────────────┐
│  int8_b [15:8]      │  int8_a [7:0]       │
│ (K position k+1)    │ (K position k)      │
└──────────┬──────────┴──────────┬──────────┘
           │                     │
           │ Both processed      │
           │ simultaneously      │
           ▼                     ▼
    Booth multiplier       Booth multiplier
    (upper half)           (lower half)
    int8_b × srcb_b        int8_a × srcb_a
    result_b               result_a
           │                     │
           ▼                     ▼
   DEST[dstacc_idx+2]    DEST[dstacc_idx]
```

#### Why the Booth Multiplier Can Process Both

The Booth multiplier is a **bit-level structure**. A 16-bit datum holding two INT8 values presents:
- Lower 8 bits (int8_a) → Lower half of Booth columns
- Upper 8 bits (int8_b) → Upper half of Booth columns

Both halves:
- Evaluate in the same gate-delay cycle
- Produce 16-bit partial products (8-bit × 8-bit)
- Feed independent compressor trees
- Complete in parallel with **zero area overhead**

#### RTL Evidence

```systemverilog
// tt_tensix_pkg.sv
format_encodings_e:
  INT8_2x  = 8'd26  ← signed INT8, 2 values per 16-bit datum

// tt_t6_proj_params_pkg.sv
ENABLE_INT8_PACKING = 1  ← always enabled in N1B0

// tt_fpu_tile_srca.sv, tt_fpu_tile_srcb.sv
wire is_int8_2x_format = (srcb_fmt_spec == INT8_2x);
if (is_int8_2x_format) begin
  // Split 16-bit datum into two 8-bit operands
  int8_a = srca_datum[7:0];
  int8_b = srca_datum[15:8];
  // Both feed Booth simultaneously
end
```

#### Effective K Throughput

| Mode | Input Width | K Positions per Datum | K Throughput |
|------|-------------|----------------------|--------------|
| FP16B | 16-bit | 1 | 1 INT8 position/cycle |
| INT8_2x | 16-bit | 2 | **2 INT8 positions/cycle** |

**2× advantage comes at ZERO cost** — same hardware, just reinterpreted.

---

### 1.2 SRCA Bank Depth and K_tile

#### Physical SRCA Bank Depth

```
SRCA register file (per FPU column):
  SRCS_NUM_ROWS_16B = 48 rows (6-bit address, 0-47)
  Per row: 4 sets × 16 datums = 64 datums read simultaneously
```

#### K_tile Calculation

```
FP16B mode:
  K_tile_FP16B = 48 rows × 1 K position/row
              = 48 positions per SRCA pass

INT8_2x mode:
  K_tile_INT8 = 48 rows × 2 K positions/row (INT8_2x packing)
             = 96 INT8 positions per SRCA pass
```

#### Why 48 Rows?

The 3MB L1 SRAM and register file depths are optimized for LLM workloads:
- Large attention heads (K up to 4096 in 16-bit format)
- Multi-head attention with limited on-tile buffer
- 48 rows × 128 bytes/row = 6KB per SRCA bank sufficient for weight tiles
- Allows double-buffering (two SRCA banks) without capacity waste

---

### 1.3 DEST INT32 Accumulate-in-Place — The K-Pass Mechanism

#### The Hardware Mechanism

When `int8_op=1` tag bit is set:

```
FPU executes READ-MODIFY-WRITE on DEST in ONE cycle:

  Step 1: Read   DEST[dstacc_idx] = old_INT32_value
  Step 2: Compute new_product = INT8_a × INT8_b (sign-extended to INT32)
  Step 3: Add    accumulated = old_INT32_value + new_product
  Step 4: Write  DEST[dstacc_idx] = accumulated
```

#### RTL Control

```systemverilog
// tt_fpu_tile.sv
wire fpu_tag_32b_acc = fpu_tag_instr_tag.fp32_acc
                     | fpu_tag_instr_tag.int8_op    // ← int8_op forces 32b accumulate
                     | i_tag.dest_lo_en;

// DEST accumulation address (10-bit, range 0-1023)
wire [DEST_ADDR_WIDTH-1:0] dest_addr = i_tag.dstacc_idx;

// When int8_op=1:
// - FPU reads prior INT32 at DEST[dstacc_idx]
// - Adds new product (INT8×INT8 → INT32)
// - Writes sum back to same address
// - TRISC2 increments dstacc_idx by +2 (for INT8_2x offset)
```

#### Zero-Overhead Accumulation

This is **free** in hardware:
- No TRISC3 involvement
- No L1 read-back
- No intermediate storage (temporary TRISC register)
- The latch-based DEST supports simultaneous read and write
- Latency is the same as non-accumulating operations

#### DEST Capacity for K=8192

```
Per DEST column slice:
  Physical rows: 1024
  In INT32 mode: 512 INT32 entries (2 × 16-bit datums)

For 4 output rows × 16 output cols:
  Active slots: 4 rows × 16 column slices = 64 INT32 entries
  Available:    512 rows × 16 slices = 8,192 INT32 entries per bank
  Margin:       ✓ 64 << 8,192 (ample capacity)
```

---

### 1.4 Per-Cycle MAC Throughput (INT8_2x Mode)

```
Per G-Tile per cycle:
  Columns per G-Tile: 8
  Rows per column: 4 (FP_ROWS)
  INT8 positions per cycle: 2 (due to INT8_2x packing)
  ─────────────────────────
  Total: 8 cols × 4 rows × 2 INT8 = 128 INT8 MACs per cycle per G-Tile

Per Tensix (2 G-Tiles):
  2 G-Tiles × 128 = 256 INT8 MACs per cycle

Per cluster (4 Tensix):
  4 Tensix × 256 = 1,024 INT8 MACs per cycle (single phase)
  With HALF_FP_BW=1 (two-phase): 2,048 INT8 MACs per cycle (single pass)

Wait, actually per the HDD:
Per G-Tile throughput for K loop: 48 MOP cycles
  Per MOP: 128 INT8 MACs (4 rows × 16 cols × 2 packed INT8)
  Per pass: 48 MOPs × 128 = 6,144 INT8 MACs per pass
```

---

## Part 2: K=8192 Execution Model

### 2.1 K=8192 Setup

```
Given:
  K = 8,192 INT8 elements
  K_tile = 96 INT8 per SRCA pass (48 rows × 2 INT8/row)

Passes required:
  ⌈8192 / 96⌉ = ⌈85.33⌉ = 86 passes
  
Last pass:
  Remainder = 8192 - (85 × 96) = 8192 - 8160 = 32 INT8 elements
```

### 2.2 Hardware Execution Flow Per Pass

#### Phase 1: L1 → SRCA (TRISC0 unpack)

```
Pass p (0 ≤ p < 86):
  Load 96 INT8 weight values from L1:
    L1[weight_base + p × 96 : p × 96 + 95] → SRCA bank 0
  
  Pack into INT8_2x format:
    int8_a | int8_b → 48 SRCA rows
    (each row holds 2 INT8 values)
  
  Simultaneously prefetch next pass into SRCA bank 1 (double-buffer)
```

#### Phase 2: SRCA × SRCB → DEST INT32 (TRISC1 math)

```
For srca_rd_addr in 0..47:  ← 48 MOP instructions per pass
  
  Issue one MOP word:
    MOP_MVMUL:
      tag.int8_op       = 1         ← INT32 accumulate mode
      tag.srcb_fmt_spec = INT8_2x   ← Two packed INT8 values
      tag.srca_rd_addr  = srca_rd_addr
      tag.dstacc_idx    = output_row_base
  
  FPU hardware:
    reads SRCA[srca_rd_addr]  = {int8_b, int8_a}
    reads SRCB[current_row]   = {srcb_b, srcb_a}
    
    Booth multiplier (lower):
      int8_a × srcb_a → product_a (16-bit, sign-extend to INT32)
      prior_DEST[dstacc_idx] += product_a
    
    Booth multiplier (upper):
      int8_b × srcb_b → product_b (16-bit, sign-extend to INT32)
      prior_DEST[dstacc_idx+2] += product_b
    
    Both write back in SAME cycle (latch RMW)
    TRISC2 firmware advances dstacc_idx by +2 next MOP
```

#### Phase 3: Synchronization

```
After 48 MOPs (all SRCA rows processed):
  TRISC1 executes: SEMPOST sem1
  TRISC0 (unpack) waits at barrier until TRISC2 signals (SEMGET)
  
Loop back to Phase 1 for next pass (p+1)
```

### 2.3 Complete Data Flow for K=8192

```
         L1 Partition (3MB)
    ┌─────────────────────────┐
    │ Weight: K=8192 × M=4    │
    │ Activation: K=8192 × N=16│
    └──────────┬──────────────┘
               │ TRISC0 unpack (86 iterations, 96 INT8 per pass)
               ▼
    ┌─────────────────────────────────────────────┐
    │ SRCA register file (48 rows × 2 banks)     │
    │ Bank 0: K-slice [p×96 .. p×96+95]          │
    │ Bank 1: Next pass (prefetch, double-buffer) │
    │ srca_rd_addr: 0→47 (increments per MOP)     │
    └──────────┬──────────────────────────────────┘
               │
               │ INT8_2x packing: 2 INT8 → both Booth halves per cycle
               ▼
    ┌─────────────────────────────────────────────┐
    │ FPU (2 G-Tiles × 8 cols × 4 rows)           │
    │ Per cycle: 128 INT8 MACs                    │
    │ Per pass:  48 cycles (srca_rd_addr loop)    │
    │ Per pass MACs: 6,144 = 48 × 128             │
    │                                              │
    │ int8_op=1 → INT32 accumulate-in-place       │
    │ dstacc_idx += 2 per MOP (INT8_2x offset)    │
    └──────────┬──────────────────────────────────┘
               │
               │ 86 passes × 48 MOPs = 4,128 MAC cycles
               ▼
    ┌──────────────────────────────────────────────┐
    │ DEST register file (16 column slices)        │
    │ 512 rows × 32b per slice (INT32 mode)        │
    │                                               │
    │ After all 86 passes:                          │
    │   DEST[m][n] = C[m][n] = Σ(A[m][k] × B[k][n])│
    │   = INT32 GEMM dot product                    │
    │                                               │
    │ Max value: 8192 × 127² = 132M << INT32 max 2.1B │
    │ Status: ✓ No overflow                         │
    └──────────┬──────────────────────────────────┘
               │ TRISC0 pack (after SEMGET unblocks)
               ▼
    ┌──────────────────────────────────┐
    │ FP-Lane descale:                 │
    │ INT32 × scale → FP32 → FP16B     │
    │ (in-place in DEST latch)         │
    └──────────┬───────────────────────┘
               │
               ▼
    ┌────────────────────────────┐
    │ L1: FP16B output           │
    │ (4 rows × 16 cols = 64 vals)│
    └────────────────────────────┘
```

---

## Part 3: Overflow Analysis

### INT32 Safe Range

```
Signed INT8:
  Max per-product: 127 × 127 = 16,129
  Max accumulation for K=8192: 8,192 × 16,129 = 132,128,768
  INT32 signed range: -2,147,483,648 to +2,147,483,647
  Status: ✓ 132M << 2.1B (margin: 16× safe)

Unsigned INT8:
  Max per-product: 255 × 255 = 65,025
  Max accumulation for K=8192: 8,192 × 65,025 = 532,684,800
  INT32 unsigned range: 0 to 4,294,967,295
  Status: ✓ 532M << 4.3B (margin: 8× safe)

Maximum K before overflow:
  K_max = 2,147,483,647 / (127²) = 2,147,483,647 / 16,129 ≈ 133,143
  For K=8192: margin = 133,143 / 8,192 ≈ 16.3× safety
```

**Conclusion:** INT32 accumulation is **unconditionally safe** for K=8192 and far beyond.

---

## Part 4: Why This Works — Hardware Philosophy

### No Hardware K Counter

Trinity does NOT have:
- A hardware K-dimension counter
- A K-loop sequencer
- A maximum K limit enforcer

**Why?** Firmware already knows K and can loop. Adding hardware K tracking would:
- Add area and complexity
- Introduce timing hazards (counter overflow)
- Limit K to predefined boundaries (hardware counter width)

**Result:** Unlimited K via firmware loop + simple accumulation hardware.

### Firmware K-Loop (TRISC2)

```c
// Pseudocode: K=8192 INT8 GEMM
void int8_gemm_k8192(void) {
  int32_t output[4][16] = {0};  // DEST accumulator
  
  for (int pass = 0; pass < 86; pass++) {
    // Phase 1: TRISC0 loads K-slice into SRCA
    load_srca_from_l1(weights, pass * 96, 96);
    
    // Phase 2: TRISC1 issues 48 MOPs (one per SRCA row)
    for (int srca_row = 0; srca_row < 48; srca_row++) {
      MOP_MVMUL(
        int8_op=1,         // INT32 accumulate-in-place
        srca_rd_addr=srca_row,
        dstacc_idx+=2      // Increment by 2 for INT8_2x offset
      );
    }
    
    // Phase 3: Sync before next pass
    SEMPOST sem0;
  }
  
  // After loop: DEST holds final INT32 GEMM results
  // TRISC0 pack: INT32 → descale → FP16B → L1
}
```

**No hardware K loop needed** — firmware controls everything.

---

## Part 5: Summary Table

| Parameter | Value | Note |
|-----------|-------|------|
| **K dimension** | Unlimited | No hardware limit |
| **K=8192 specifically** | ✓ Supported | Common in LLM attention |
| **INT8_2x packing** | 2 INT8/datum | 2× K throughput vs FP16B |
| **SRCA K_tile** | 96 INT8 per pass | 48 rows × 2 INT8/row |
| **Passes for K=8192** | 86 | ⌈8192/96⌉ |
| **MOP cycles per pass** | 48 | One per SRCA row |
| **Total MAC cycles** | 4,128 | 86 passes × 48 cycles |
| **Per-cycle MACs** | 128 (per G-Tile) | 8 cols × 4 rows × 2 INT8 |
| **DEST accumulation** | INT32 RMW | Read old, add product, write new |
| **Max INT32 value** | 132,128,768 | 8192 × 127² |
| **INT32 overflow risk** | **None** | 132M << 2.1B (16× margin) |
| **Double-buffering** | SRCA banks | Load next pass while computing current |
| **DEST capacity** | 8,192 INT32 entries | 512 rows per bank × 16 slices |

---

## Conclusion

**Trinity achieves arbitrarily large K for INT8 GEMM through:**

1. **Hardware packing** (INT8_2x): 2× K throughput for free
2. **Firmware loops**: K is a parameter, not a hardware limit
3. **Accumulation-in-place** (DEST INT32 RMW): Partial sums persist across passes
4. **Safe overflow analysis**: 16× margin for K=8192

This design philosophy prioritizes **simplicity and efficiency** over exhaustive hardware sequencing:
- Firmware controls K loop (flexible, no size limit)
- Hardware provides primitive operations (accumulate, multiply)
- Result: unlimited K with minimal hardware complexity
