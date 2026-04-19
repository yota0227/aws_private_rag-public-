# FPU Latch Negative Phase Signal Handling - RTL Analysis
**Date:** 2026-04-14  
**RTL Release:** 20260221  
**Module:** tt_reg_bank.sv (Latch Array Implementation)

---

## Executive Summary

The FPU does **NOT use explicit "negative" and "positive" naming** for latch phase signals. Instead, it uses **Integrated Clock Gating (ICG) with always_latch** to automatically create two-phase transparency. The "negative phase" (clock LOW = transparent) behavior is inherent to the latch design, not exposed as separate signal names.

---

## How FPU Handles Latch Phases: RTL Implementation

### Architecture Overview

The latch arrays (DEST, SRCA, SRCB) in the FPU are implemented in `tt_reg_bank.sv` using:

1. **ICG (Integrated Clock Gate)** - `tt_clkgater` module
2. **SystemVerilog always_latch** - Creates transparent latches
3. **Gated Clock Signals** - Control when latches capture/hold data
4. **Indexed Latch Pairs** - Two latches per datum for packed formats (FP4, INT8)

### Key RTL Signals (from tt_reg_bank.sv, lines 812-1002)

```systemverilog
// Lines 812-815: Latch array structure
logic [DEPTH-1:0][DATUMS_IN_LINE-1:0][1:0] gated_clk, gated_clk_zflags;

generate
  if (LATCH_ARRAY) begin : gen_latch_array
    for (genvar row = 0; row < DEPTH; row++) begin : latch_row
      for (genvar i = 0; i < DATUMS_IN_LINE; i++) begin : datum_in_line
```

**Signal Breakdown:**
- `gated_clk[row][i][0]` → First latch pair (for packed formats, lower half)
- `gated_clk[row][i][1]` → Second latch pair (for packed formats, upper half)
- These are NOT named `_n` or `_p` - they're indexed as `[0]` and `[1]`

### The Two-Phase Mechanism: Without Explicit "NEG" Signals

#### Phase 1: Negative Phase (Clock LOW - Transparent)

```systemverilog
// Lines 908-929: Normal (non-packed) latch implementation
tt_clkgater icg(.i_clk(i_clk),
               .i_en(zf_masked_wren[row][i][0]),  // Write enable
               .i_te('0),
               .o_clk(gated_clk[row][i][0]));    // Output clock

always_latch begin                                 // Transparent when gated_clk is LOW
   if (gated_clk[row][i][0]) begin
       regs0.row[row].datum[i] <= d_regs0.row[row].datum[i];
       parity[row][i][0]       <= ^d_regs0.row[row].datum[i];
   end
end
```

**How It Works:**
1. When `i_en` (write enable) is LOW → `gated_clk` goes LOW
2. When `gated_clk` is LOW → `always_latch` condition becomes TRUE
3. When condition is TRUE → **Latch is TRANSPARENT** (passes input to output)
4. Data flows through and settles at outputs

#### Phase 2: Positive Phase (Clock HIGH - Opaque/Hold)

```systemverilog
// Continuation of same always_latch block
always_latch begin
   if (gated_clk[row][i][0]) begin                // Condition TRUE when clock HIGH
       // This block executes - captures data
       regs0.row[row].datum[i] <= d_regs0.row[row].datum[i];
   end
   // Implicit ELSE when gated_clk is LOW:
   // Latch HOLDS previous value (opaque phase)
end
```

**How It Works:**
1. When `i_en` (write enable) is HIGH → `gated_clk` goes HIGH
2. When `gated_clk` is HIGH → `always_latch` condition is FALSE
3. When condition is FALSE → **Latch HOLDS** previous value (opaque phase)
4. The non-blocking assignment (`<=`) captures data on the rising edge

---

## Key Insight: Why NO Explicit "NEG" Naming?

### The Standard Latch Behavior (ICG + always_latch)

```
SystemVerilog always_latch with ICG:
┌─────────────────────────────────────┐
│  always_latch begin                 │
│    if (gated_clk) begin             │
│      Q <= D;  // Non-blocking       │
│    end                              │
│  end                                │
└─────────────────────────────────────┘
         ↓
    When gated_clk LOW (write enabled):
    • Latch is transparent (Q follows D combinationally)
    • This is the "negative phase"

    When gated_clk HIGH (not writing):
    • Latch is opaque (Q holds value)
    • Non-blocking assignment captures data on rising edge
    • This is the "positive phase"
```

The **transparency** is **automatic** because:
1. The combinational logic inside `always_latch` executes whenever inputs change
2. When the condition is true AND the clock is low, data propagates through
3. The `<=` captures on rising edge when condition transitions

### Why Not Name Them "_n" and "_p"?

**Historical Context (Traditional Latch Design):**
- In older designs with explicit positive/negative latches, you'd have:
  ```systemverilog
  // OLD style - explicit phase signals
  always @(negedge clk) latch_n <= D;  // Negative phase input
  always @(posedge clk) latch_p <= D;  // Positive phase input
  ```

**Modern Design (ICG + always_latch):**
- One unified latch with automatic phase behavior
- The ICG handles clock gating; no need to expose phases separately
- Signal naming reflects the **functional role** (data storage), not the clock phases

---

## Two-Latch Pairs for Packed Formats (FP4, INT8)

When packing is enabled (`ENABLE_FP4_PACKING` or `ENABLE_INT8_PACKING`), each datum position gets **TWO independent latch pairs**:

```systemverilog
// Lines 817-901: Packed latches (INT8/FP4)
if ((ENABLE_FP4_PACKING != 0) | (ENABLE_INT8_PACKING != 0)) begin: packed_latches

  // Latch Pair 0 (Lower Half)
  tt_clkgater icg0(.i_clk(i_clk),
                  .i_en(zf_masked_wren[row][i][0]),
                  .i_te('0),
                  .o_clk(gated_clk[row][i][0]));

  always_latch begin
    if (gated_clk[row][i][0]) begin
        regs0.row[row].datum[i][0 +: PACKED_DATUM_WIDTH] <= 
            d_regs0.row[row].datum[i][0 +: PACKED_DATUM_WIDTH];
    end
  end

  // Latch Pair 1 (Upper Half)
  tt_clkgater icg1(.i_clk(i_clk),
                  .i_en(zf_masked_wren[row][i][1]),
                  .i_te('0),
                  .o_clk(gated_clk[row][i][1]));

  always_latch begin
    if (gated_clk[row][i][1]) begin
        regs0.row[row].datum[i][OUTPUT_DATUM_WIDTH-1:PACKED_DATUM_WIDTH] <= 
            d_regs0.row[row].datum[i][OUTPUT_DATUM_WIDTH-1:PACKED_DATUM_WIDTH];
    end
  end
end
```

**Why Two Pairs?**
- INT8/FP4 formats pack two values per datum location
- Two independent latches allow independent update timing for each half
- Enables **two-phase processing** within ONE clock cycle
- Phase 1: Capture lower half (gated_clk[0] pulse)
- Phase 2: Capture upper half (gated_clk[1] pulse, same cycle)

---

## Signal Naming Convention: The [0] and [1] Index

The `[0]` and `[1]` indices represent:

| Index | Meaning | When Used |
|-------|---------|-----------|
| `[0]` | **Lower latch pair** or **primary latch** | Always present; holds lower data bits |
| `[1]` | **Upper latch pair** | Only with packing enabled; holds upper data bits |

**NOT phase naming** — these are **logical positions** in the datum word.

---

## Complete Signal Flow Example: INT8 Write to DEST

### RTL Signals Involved

```systemverilog
// DEST Register Bank (tt_reg_bank.sv context):

// Input: User wants to write INT8 value to DEST[row][i]
i_fpu_wrdata[datum_idx] = some_int8_value;

// Latch Control Signals Generated:
gated_clk[row][i][0] = ICG output for lower half
gated_clk[row][i][1] = ICG output for upper half

// Data inside latches:
regs0.row[row].datum[i][7:0]   ← Lower 8 bits (INT8 value)
regs0.row[row].datum[i][15:8]  ← Upper 8 bits (sign extension or next value)
```

### Cycle-by-Cycle Behavior

```
Cycle N:
┌──────────────────────────────────────────────────────┐
│ Clock = HIGH (Positive Phase - Hold)                 │
│                                                      │
│ Latch State (BEFORE clock edge):                     │
│ • regs0[i][7:0]   = previous INT8 value (HELD)       │
│ • gated_clk[0]    = LOW (no update)                  │
│                                                      │
│ Input:                                               │
│ • d_regs0[i][7:0] = new INT8 value                   │
│                                                      │
│ Latch Condition: if (gated_clk[row][i][0]) → FALSE  │
│ Behavior: HOLD previous value                        │
└──────────────────────────────────────────────────────┘
         ↓ (rising edge)

Cycle N (Late):
┌──────────────────────────────────────────────────────┐
│ Clock = LOW (Negative Phase - Transparent)           │
│                                                      │
│ gated_clk[0] = LOW                                   │
│                                                      │
│ Latch Condition: if (gated_clk[row][i][0]) → TRUE   │
│ Behavior: **TRANSPARENT** - Q follows D              │
│                                                      │
│ Output (to FP-Lane inputs):                          │
│ • regs0[i][7:0] = d_regs0[i][7:0] (combinational)   │
│                                                      │
│ BUT: Non-blocking assignment triggers on FALLING     │
│ edge (implicit): regs0[i] <= d_regs0[i];            │
│                                                      │
│ Data begins PROPAGATING through latch latches        │
└──────────────────────────────────────────────────────┘
         ↓ (falling edge of gated_clk)

Cycle N+1:
┌──────────────────────────────────────────────────────┐
│ Clock = HIGH again (Positive Phase - Capture)        │
│                                                      │
│ Latch Condition: if (gated_clk[row][i][0]) → HIGH   │
│                                                      │
│ **Non-blocking assignment executes:**                │
│ regs0.row[row].datum[i][7:0] <= d_regs0[...][7:0]   │
│                                                      │
│ New data CAPTURED at rising edge                     │
│ Q now holds new INT8 value                           │
└──────────────────────────────────────────────────────┘
```

---

## No "NEG" Signal Anywhere - By Design

Searching the RTL for naming patterns:

```bash
# Search for "negative" or "_n" latch phase signals
grep -n "neg_\|_neg\|negative" tt_reg_bank.sv
# Result: Only matches like "NEGINF" (negative infinity) - NOT phase signals!

grep -n "latch_n\|latch_p\|_n_latch\|_p_latch" tt_reg_bank.sv
# Result: No matches - no explicit phase naming
```

The latch phases are:
1. **Implicit** in the `always_latch` transparency behavior
2. **Controlled by** the gated clock signal
3. **Not exposed** as separate named signals

---

## Key Differences: Documentation vs RTL

| Aspect | Documentation | RTL Implementation |
|--------|----------------|-------------------|
| **Phase Naming** | "Negative phase" (CLK LOW), "Positive phase" (CLK HIGH) | No explicit naming; phases are implicit in always_latch |
| **Latch Pairs** | Called "phase 1" and "phase 2" processing | Indexed as `gated_clk[..][0]` and `gated_clk[..][1]` |
| **r0 vs r1 lanes** | Two independent FP-Lane instances | Separate LANE_ID parameters, not latch phases |
| **Signal Names** | Would suggest _neg/_pos distinction | Uses indexed arrays and ICG outputs |

---

## Verification: Actual Signal Names in RTL

```systemverilog
// Line 812: Latch control signal declarations
logic [DEPTH-1:0][DATUMS_IN_LINE-1:0][1:0] gated_clk, gated_clk_zflags;

// Lines 819-822: ICG instantiation for [0] index
tt_clkgater icg0(.i_clk(i_clk),
                .i_en(zf_masked_wren[row][i][0]),
                .i_te('0),
                .o_clk(gated_clk[row][i][0]));  // ← No "_neg" suffix

// Lines 867-870: ICG instantiation for [1] index  
tt_clkgater icg1(.i_clk(i_clk),
                .i_en(zf_masked_wren[row][i][1]),
                .i_te('0),
                .o_clk(gated_clk[row][i][1]));  // ← No "_pos" suffix

// Lines 917-929: Latch transparency control
always_latch begin
  if (gated_clk[row][i][0]) begin              // ← Direct condition, no "_n"
      regs0.row[row].datum[i] <= d_regs0.row[row].datum[i];
      parity[row][i][0]       <= ^d_regs0.row[row].datum[i];
  end
end
```

---

## Summary: How "NEG" Naming is Handled

**Answer: It's NOT explicitly handled in RTL signal names.**

Instead:

1. **ICG Clock Gating** → Creates automatic clock edge for gating
2. **always_latch Transparency** → Inherent behavior when condition is true
3. **Indexed Latch Pairs** → `[0]` and `[1]` distinguish logical data positions, not phases
4. **Phase Control** → Implicit in the condition evaluation and clock transitions

The "negative phase" is the **natural behavior** of a transparent latch when its enable condition is true (clock LOW). The "positive phase" is the **capture behavior** when the condition transitions (rising edge of gated_clk).

**No separate signal needed** — the mechanism is unified in one `always_latch` block per latch position.

---

## Related RTL Files

- **tt_reg_bank.sv** - Register bank with latch array implementation (lines 812-1002)
- **tt_gtile_dest.sv** - DEST memory instantiation (uses tt_reg_bank with LATCH_ARRAY=1)
- **tt_clkgater.sv** - ICG module (controls gated clock signals)
- **tt_fpu_tile.sv** - FP-Tile instantiation (uses GTile with DEST)

---

**Document Version:** 1.0  
**Last Updated:** 2026-04-14  
**RTL Release Analyzed:** 20260221
