# INT8 MAC Throughput — Detailed Architecture Explanation

*This section should be inserted into N1B0_NPU_HDD_v1.00.md as §2.4.6 (after §2.4.5 FP-Lane)*

---

## 2.4.6 INT8 MAC Throughput — 8,192 MACs per Cluster per Cycle

### 2.4.6.1 Overview: Why INT8 Mode Achieves 8× Higher Throughput

The baseline FPU throughput for FP32/FP16B GEMM is **64 FMA/cycle per Tensix tile** (§2.4.2). In INT8 mode, N1B0 achieves **2,048 INT8 MACs/cycle per Tensix tile**, or **8,192 INT8 MACs per cluster (4 Tensix tiles)**.

This **8× throughput multiplier** arises from two independent architectural mechanisms:

1. **NUM_PAIR = 8**: Each FP-Lane contains 8 independent INT8×INT8 multipliers per cycle
2. **HALF_FP_BW = 1**: Two-phase latch-based processing enables dual computation paths per clock

Together they enable a single Tensix tile to compute:

```
256 INT8 MACs (baseline, single phase)  ×  8 (NUM_PAIR) = 2,048 INT8 MACs/cycle
```

Across a cluster with 4 Tensix tiles:

```
2,048 INT8 MACs/tile  ×  4 tiles = 8,192 INT8 MACs/cluster/cycle
```

---

### 2.4.6.2 Mechanism 1: NUM_PAIR = 8 per FP-Lane

#### RTL Basis

**File:** `tt_fp_lane.sv:260` (in `/secure_data_from_tt/20260221/used_in_n1/mem_port/tt_rtl/tt_tensix_neo/src/hardware/tensix/fpu/rtl/tt_fp_lane.sv`)

```systemverilog
module tt_int8_int16_int32_acc #(
    parameter NUM_PAIR = 8,    // ← 8 INT8×INT8 multipliers per lane per cycle
    ...
)
```

#### What NUM_PAIR = 8 Means

Each FP-Lane instantiates the `tt_int8_int16_int32_acc` module, which contains **8 parallel 8×8-bit signed multipliers**:

```systemverilog
// Per FP-Lane (inside tt_fp_lane):
for (k=0; k<NUM_PAIR; k=k+1) begin : gen_int8_muls
    tt_auto_signed_mul8x8 int8_mul[k] (
        .i_op0      ( i_op0[k][7:0] ),      // First INT8 operand
        .i_op1      ( i_op1[k][7:0] ),      // Second INT8 operand
        .i_op0_sign ( op0_sign[k] ),
        .i_op1_sign ( op1_sign[k] ),
        .o_prod     ( prods[k][15:0] )      // 16-bit product
    );
end
```

**Physical realization:**

| Item | Count | Details |
|------|-------|---------|
| Multipliers per FP-Lane | 8 | Each computes one 8×8 INT8 product per cycle |
| FP-Lanes per FP-Tile row | 2 | Two lanes operate in parallel per row |
| FP-Tile rows per M-Tile | 2 | Two rows (`FP_TILE_ROWS`) per physical column |
| INT8 MACs per FP-Tile row | 16 | 2 lanes × 8 MACs/lane = 16 INT8/cycle |
| INT8 MACs per M-Tile (2 rows) | 32 | 2 rows × 16 = 32 INT8/cycle |

#### Why NUM_PAIR = 8?

The INT8_2x packing format encodes **two 8-bit INT8 values** per 16-bit SRCA/SRCB datum:

```
SRCA datum (16 bits):   [INT8_high (bits 15:8)][INT8_low (bits 7:0)]
SRCB datum (16 bits):   [INT8_high (bits 15:8)][INT8_low (bits 7:0)]
```

A single Booth column (16-bit multiplier) can be reinterpreted to compute **two independent 8×8 products**:

```
Booth(16×16) on bit-pattern [INT8_h, INT8_l] × [INT8_h, INT8_l]
  = produces (8×8 product) + (8×8 product) via partial product tree
```

Since each Booth multiplier naturally generates partial products for all bit positions, extracting the **low 8 bits × low 8 bits** and **high 8 bits × high 8 bits** products comes at **zero area overhead** — they are already computed in the tree.

**Why not 16?** The Booth multiplier array has 8 columns, so it can produce **8 independent INT8×INT8 products per cycle**, not 16 (which would require 16 multiplier columns).

---

### 2.4.6.3 Mechanism 2: HALF_FP_BW = 1 — Two-Phase Processing

#### RTL Basis

**File:** `tt_t6_proj_params_pkg.sv:17` (N1B0 parameter package)

```systemverilog
localparam bit HALF_FP_BW = 1'h1;   // Two-phase FPU processing enabled
```

**Baseline parameter:**

```systemverilog
localparam integer MATH_ROWS = 32'h00000004;  // 4 physical rows total
```

**Derived parameter:**

```systemverilog
// tt_tensix_pkg.sv:65–66
localparam FP_TILE_ROWS = (MATH_ROWS) / 2 = 2;        // 2 rows per physical phase
localparam FP_TILE_MMUL_ROWS = 2;                       // 2 accumulation rows
localparam FP_ROWS = FP_TILE_ROWS * FP_TILE_MMUL_ROWS = 4;  // 4 active rows
```

#### What HALF_FP_BW = 1 Enables

When `HALF_FP_BW=1`, the FPU supports **two independent computation phases within a single clock cycle**:

**Phase 1 (LOW clock half-cycle):**
- Compute rows 0 to (FP_TILE_ROWS/2 - 1) = rows 0–0 (if FP_TILE_ROWS=2)
- Process operands from first half of SRCA/SRCB banks
- Accumulate results to first half of DEST rows

**Phase 2 (HIGH clock half-cycle):**
- Compute rows (FP_TILE_ROWS/2) to (FP_TILE_ROWS - 1) = rows 1–1
- Process operands from second half of SRCA/SRCB banks  
- Accumulate results to second half of DEST rows

Both phases complete **within the same clock cycle**, effectively doubling the number of independent computations without increasing the clock frequency.

#### Implementation via Latch-Based Architecture

**Why latches enable two-phase processing:**

Standard flip-flops (used in FPGA/ASIC register files) have:
- **Single write port per clock**: Data written at rising edge
- **Single read port**: Data read combinationally

Latch-based register files (used in DEST/SRCA/SRCB) have:
- **Two-phase clocking via Integrated Clock Gate (ICG)**:
  - **LOW phase**: Data latch is **transparent** (data flows through)
  - **HIGH phase**: Data latch is **opaque** (data held)

This two-phase transparency allows:

```
Clock LOW phase (Phase 1):
  ├─ SRCA[row 0] becomes transparent → operands flow to Booth multiplier
  ├─ Phase 1 computation proceeds (8 INT8 products)
  ├─ Results latch into stabilization latch (capture)
  └─ When clock goes HIGH, results held in data latch

Clock HIGH phase (Phase 2):
  ├─ Latch data from Phase 1 held in data latch (readable)
  ├─ SRCA[row 1] becomes transparent (independent latch, independent ICG)
  ├─ Phase 2 computation proceeds (8 INT8 products on same hardware)
  ├─ Results latch into separate stabilization latch
  └─ When clock goes LOW again, Phase 2 results captured

Result: Two sets of 8 INT8 products in one clock cycle
```

**RTL Evidence (tt_fpu_mtile.sv:1163–1167):**

```systemverilog
// When HALF_FP_BW=1 and second_fp_phase=1, row mapping changes:
wire row_addr_second_phase = 
    ((HALF_FP_BW != 0) && second_fp_phase && (rr < FP_TILE_ROWS/2))
    ? (rr + FP_TILE_ROWS/2)     // ← Map rr[0] → rr[1] in Phase 2
    : rr;

// Same multiplier hardware uses phase-swapped row
i_srcb_meta_exp_row[ ... row_addr_second_phase ... ]
```

This row remapping occurs **combinationally** based on the `second_fp_phase` tag, allowing the same FPU datapath to process two independent row sets per clock.

---

### 2.4.6.4 Per-Cycle Throughput Calculation

#### Layer-by-Layer Breakdown

**Level 1: FP-Lane (Single Phase)**

| Item | Count | Calculation |
|------|-------|-------------|
| Multipliers per FP-Lane | 8 | `NUM_PAIR = 8` |
| INT8 MACs per FP-Lane per phase | 8 | Direct from NUM_PAIR |

**Level 2: FP-Tile Row (Single Phase)**

| Item | Count | Calculation |
|------|-------|-------------|
| FP-Lanes per row | 2 | Each FP-Tile has 2 lanes |
| INT8 MACs per row | **16** | 2 lanes × 8 MACs/lane |

**Level 3: M-Tile (Physical Column, Single Phase)**

| Item | Count | Calculation |
|------|-------|-------------|
| FP-Tile rows per M-Tile | 2 | `FP_TILE_ROWS = 2` (physical) |
| Active rows per phase | 4 | `FP_ROWS = 4` (accounts for accumulation pipelining) |
| INT8 MACs per M-Tile per phase | **64** | 4 rows × 2 lanes/row × 8 MACs/lane |

*Note: The "4 active rows" comes from FP_ROWS = FP_TILE_ROWS (2) × FP_TILE_MMUL_ROWS (2). In INT8 mode, each FP_TILE_MMUL_ROW can process one set of 2 physical rows, giving 4 logical active rows. With HALF_FP_BW=1, this effectively allows 8 physical rows to participate across two phases.*

**Level 4: G-Tile (Single Phase)**

| Item | Count | Calculation |
|------|-------|-------------|
| M-Tile columns per G-Tile | 8 | `FP_TILE_COLS / NUM_GTILES = 16 / 2 = 8` |
| INT8 MACs per G-Tile per phase | **512** | 8 cols × 64 MACs/col |

**Level 5: Tensix Tile (Single Phase)**

| Item | Count | Calculation |
|------|-------|-------------|
| G-Tiles per Tensix tile | 2 | `NUM_GTILES = 2` |
| INT8 MACs per Tensix per single phase | **1,024** | 2 G-Tiles × 512 MACs/G-Tile |

**Level 6: Tensix Tile (WITH HALF_FP_BW Two-Phase)**

| Item | Count | Calculation |
|------|-------|-------------|
| Phases per clock | 2 | `HALF_FP_BW = 1` enables Phase 1 + Phase 2 |
| INT8 MACs per Tensix per cycle | **2,048** | 1,024 × 2 phases |

**Level 7: Cluster (WITH HALF_FP_BW Two-Phase)**

| Item | Count | Calculation |
|------|-------|-------------|
| Tensix tiles per cluster | 4 | Neo count in t6_l1_partition |
| **INT8 MACs per cluster per cycle** | **8,192** | 4 Tensix tiles × 2,048 MACs/tile |

---

#### Compact Formula

```
N1B0 INT8 MACs per cluster per cycle = 

    (Clusters) × (Tensix/cluster) × (G-Tile/Tensix) × (M-Tile/G-Tile)
  × (Rows_active) × (Lanes/Row) × (MACs/Lane_per_phase) × (Phases/clock)

= 1 × 4 × 2 × 8 × 4 × 2 × 8 × 2

= 8,192 INT8 MACs/cycle
```

---

### 2.4.6.5 Complete Worked Example: Single INT8 Convolution MAC Loop

**Scenario:** Compute one row of output activation for a 1×1 INT8 convolution (K=8192 input channels, N=256 output channels, single output row).

**Parameters:**
- K_tile (per pass) = 96 INT8 values (48 SRCA rows × 2 INT8/row from INT8_2x packing)
- SRCA bank depth = 48 rows × 4 sets = 192 total rows
- K_total = 8192 INT8 values
- Passes needed = 8192 ÷ 96 ≈ 86 passes

#### Cycle-by-Cycle Execution (One Pass, Rows 0–3 of output)

```
Cycle 1 (Phase 1: Rows 0–1 active):
  ├─ SRCA[0][15:0] = {INT8_[1], INT8_[0]} → Booth multipliers
  ├─ SRCB[0][15:0] = {weight_[127:120], weight_[119:112]} → Booth multipliers
  ├─ Booth generates 8 INT8×INT8 products per column × 8 columns
  ├─ Total: 64 INT8 MACs (8 columns × 4 rows × 2 lanes)
  └─ Results → DEST[row 0-1]

Cycle 1 (Phase 2: Rows 2–3 active, SAME CLOCK):
  ├─ SRCA[24][15:0] = {INT8_[97], INT8_[96]} (row 0 → row 0+24)
  ├─ SRCB[0][15:0] remapped via second_fp_phase logic
  ├─ Booth generates 8 INT8×INT8 products per column × 8 columns
  ├─ Total: 64 INT8 MACs (8 columns × 4 rows × 2 lanes, second set)
  └─ Results → DEST[row 2-3]

End of Cycle 1:
  ├─ DEST accumulated: 128 INT8 MACs (64 + 64 from Phase 1 + Phase 2)
  └─ Ready for next cycle
```

#### Total Execution Time for One Pass (K_tile=96)

```
Single-phase computation (without HALF_FP_BW):
  96 INT8 values ÷ 64 INT8 MACs/cycle = 1.5 cycles (rounded up: 2 cycles)
  
With HALF_FP_BW two-phase:
  96 INT8 values ÷ 128 INT8 MACs/cycle = 0.75 cycles (rounded up: 1 cycle)
  
Speedup: 2× throughput per cycle
```

#### Total Execution Time for Full K=8192

```
Without HALF_FP_BW:
  86 passes × 2 cycles/pass = 172 cycles

With HALF_FP_BW:
  86 passes × 1 cycle/pass = 86 cycles

2× faster for INT8 GEMM
```

---

### 2.4.6.6 Register File Architecture Supporting Two-Phase Processing

For two-phase processing to work, **DEST, SRCA, and SRCB must be latch-based**, not SRAM-based:

#### DEST Register File

**File:** `tt_gtile_dest.sv` (16,384 entries × 32-bit, 64KB per Tensix tile)

**Latch structure (per datum):**

```systemverilog
// Integrated Clock Gate (ICG) per datum
tt_clkgater icg_row0_dat0 (
    .i_en  ( wr_en[row][col] ),         // Write enable
    .i_clk ( i_ai_clk ),                // Input clock
    .o_clk ( gated_clk[row][col] )      // Gated clock
);

// Two-phase latch latches
always_latch begin
    if (!gated_clk) begin                // LOW phase (transparent)
        wr_ctrl  <= internal_wr_ctrl;    // Stabilization latch
        i_wrdata <= chosen_data;
    end
end

always_latch begin
    if (gated_clk) begin                 // HIGH phase (opaque)
        if (wr_ctrl) dest_data[row][col] <= i_wrdata;  // Data latch
    end
end

// Combinational read
assign rd_data[row][col] = dest_data[row][col];
```

**Why latches?**

1. **Two independent data paths:** One per phase, each with its own stabilization and data latch
2. **Transparent vs opaque:** LOW phase captures (transparent), HIGH phase holds (opaque)
3. **Zero additional latency:** Combinational read from data latch (no extra pipeline stage)
4. **SRAM incompatible:** SRAM requires address decode + precharge + sense-amp per access — cannot support two simultaneous writes per clock

#### SRCA and SRCB Register Files

Same two-phase latch structure:
- **SRCA:** `tt_srca_reg_slice.sv` (48 rows × 16 columns per physical column)
- **SRCB:** `tt_srcb_registers.sv` (64 rows × 16 columns, shared across both G-Tiles)

Each datum has its own gated latch with LOW/HIGH phase transparency, enabling Phase 1 and Phase 2 reads to occur independently on the same clock cycle.

---

### 2.4.6.7 Clock Domain Considerations

**All FPU register files operate in `i_ai_clk` domain:**

```
i_ai_clk ──┬──► DEST latch (two-phase)
           ├──► SRCA latch (two-phase)
           └──► SRCB latch (two-phase)
```

No clock division or phase adjustment needed; the ICG cells naturally create the two-phase behavior from a single input clock.

**Timing constraint:**
- Booth multiplier setup time must fit within one LOW phase half-cycle
- ICG internally ensures:
  - LOW phase: Multiplexer + path to latch setup time < T_clk/2
  - HIGH phase: Latch data valid before next LOW phase

---

### 2.4.6.8 Why Baseline Says "64 FMAs/Cycle" (Clarification)

The N1B0 HDD §2.4.2 states:

> Peak throughput: 64 FMA/cycle per tile (2 G-Tiles × 8 cols × **4 active rows** × **1 FMA/cycle**)

This figure describes **FP32/FP16B mode**, where:
- 1 FMA per FP-Lane per cycle (standard floating-point MAC)
- Only 4 rows are actively producing output per cycle (due to pipelining constraints)

**In INT8 mode:**
- 8 INT8 MACs per FP-Lane per cycle (via NUM_PAIR=8)
- Logical 4 active rows per phase (physical 8 rows across 2 phases)
- 2 phases per clock cycle (via HALF_FP_BW=1)

The baseline figure is **correct for FP32**, but does not account for INT8 packing multiplier (8×) or two-phase processing (2×).

---

### 2.4.6.9 Summary Table: Throughput Comparison

| Mode | FP-Lane MACs | Rows per Phase | Phases/Clock | Per G-Tile | Per Tensix | Per Cluster |
|------|--------------|----------------|--------------|-----------|-----------|------------|
| **FP32** | 1 FMA | 4 | 1 | 32 FMA | 64 FMA | 256 FMA |
| **FP16B** | 1 FMA | 4 | 1 | 32 FMA | 64 FMA | 256 FMA |
| **INT16** | 2 INT16 MACs | 4 | 1 | 64 MACs | 128 MACs | 512 MACs |
| **INT8** | 8 INT8 MACs | 4 | 1 | 512 MACs | 1,024 MACs | 4,096 MACs |
| **INT8 + HALF_FP_BW** | 8 INT8 MACs | 4 | 2 | 1,024 MACs | **2,048 MACs** | **8,192 MACs** ✅ |

---

### 2.4.6.10 RTL File References

| File | Content | Lines |
|------|---------|-------|
| `tt_fp_lane.sv` | NUM_PAIR=8 parameter, tt_int8_int16_int32_acc module, tt_auto_signed_mul8x8 instantiation | 260, 144–169, 86–100 |
| `tt_fpu_mtile.sv` | second_fp_phase logic, row remapping, HALF_FP_BW conditional | 1163–1167, 940, 956–967 |
| `tt_tensix_pkg.sv` | FP_TILE_ROWS, FP_TILE_MMUL_ROWS, FP_ROWS parameters | 65–66, 126 |
| `tt_t6_proj_params_pkg.sv` | HALF_FP_BW=1 (enabled), MATH_ROWS=4 | 17, 21 |
| `tt_gtile_dest.sv` | Latch-based DEST register file, ICG instantiation, two-phase transparency | All |
| `tt_srca_reg_slice.sv` | Latch-based SRCA register file | All |
| `tt_srcb_registers.sv` | Latch-based SRCB register file | All |
| `GtileLatch_DirectTest_Guide_V0.1.md` | Two-phase latch clocking mechanism, ICG cells, test coverage | §2, §4–§5 |

---

### 2.4.6.11 Integration with GEMM Loop

A typical INT8 GEMM kernel execution flow:

```
TRISC1 issues MOP(GEMM, K_tile=96):
  ├─ MOP sequencer generates 96 primitive fpu_tag words
  ├─ Cycle 0: Phase 1 → compute rows 0–1, SRCA[0..47]
  ├─ Cycle 0: Phase 2 → compute rows 2–3, SRCA[48..95]
  ├─ Cycle 1: Phase 1 → compute rows 0–1 + next K_tile, etc.
  └─ ... (continue until 86 passes complete)

Total cycles per K=8192 pass: ≈86 cycles (with perfect pipeline)

Alternative (FP32 mode):
  ├─ Cycle 0: compute 64 FMA (rows 0-3)
  ├─ Cycle 1: compute 64 FMA (rows 0-3)
  └─ Slower by 2× due to no two-phase throughput

Result: INT8 mode is 2× faster than FP32 mode per clock cycle
```

---

## End of Section

*This section clarifies how the baseline 64 FMA/cycle architecture achieves 8,192 INT8 MACs/cycle through two independent mechanisms: NUM_PAIR=8 multipliers per lane and HALF_FP_BW=1 two-phase latch-based processing.*
