# How to Generate gated_clk[row][i][1] Signal in RTL
**Date:** 2026-04-14  
**RTL Release:** 20260221  
**Context:** DEST/SRCA/SRCB latch array implementation (tt_reg_bank.sv)

---

## Overview

The `gated_clk[row][i][1]` signal controls the second latch pair (upper half) in packed INT8/FP4 formats. It's generated through a 4-step process:

1. **Generate base write enable** (`wren`)
2. **Generate zero-flag write enable** (`zf_wren`) 
3. **Mask based on format** (`zf_masked_wren`)
4. **Gate the clock with ICG** (produces `gated_clk`)

---

## Step 1: Generate Base Write Enable Signal (`wren`)

The base write enable determines which rows/columns can be written:

```systemverilog
// Lines 418-426 (tt_reg_bank.sv)
always_comb begin
  wren = '0;
  unique0 case(write_causes)
     ZERO_OUT         : wren = (wr_ctrl.zero_out || wr_ctrl.clr) 
                               ? {SET_DATUMS{1'b1}} 
                               : {SET_DATUMS{1'b1}} << (zero_bank * SET_DATUMS);
     TRANSPOSE_WRITE  : wren = transposed_wren;
     STRIDED_WRITE    : wren = strided_wren;
     WRITE            : wren = aligned_wren;     // ← Normal write path
  endcase
end
```

**Output:**
```systemverilog
logic [DEPTH-1:0][DATUMS_IN_LINE-1:0] wren;
// wren[row][i] = 1 if this datum location can be written
//               = 0 if this datum location is protected
```

---

## Step 2: Generate Zero-Flag Write Enable (`zf_wren`)

Zero-flags track which data is valid. For packed formats, each half has its own zero-flag:

```systemverilog
// Lines 462-479 (tt_reg_bank.sv)
generate
  if (LATCH_ARRAY) begin : gen_zf_wren
    for (genvar row = 0; row < DEPTH; row++) begin : zf_latch_row
      for (genvar i = 0; i < DATUMS_IN_LINE; i++) begin : zf_datum_in_line
        always_comb begin
          if (zero_out) begin
              // Both halves get written (zero all)
              zf_wren[row][i] = {2{wren[row][i]}};
              //                 ↑ [1]  ↑ [0]
          end
          else if (write_upper_datum_fp4 || write_upper_datum_int8) begin
              // Only upper half [1] gets written
              zf_wren[row][i] = {wren[row][i], 1'b0};
              //                 ↑ upper [1]  ↑ lower [0] disabled
          end
          else begin
              // Only lower half [0] gets written (default)
              zf_wren[row][i] = {1'b0, wren[row][i]};
              //                 ↑ [1] disabled  ↑ [0]
          end
        end
      end
    end
  end
endgenerate
```

**Output:**
```systemverilog
logic [DEPTH-1:0][DATUMS_IN_LINE-1:0][1:0] zf_wren;
// zf_wren[row][i][1] = 1 if upper half zero-flag should update
// zf_wren[row][i][0] = 1 if lower half zero-flag should update
```

**Key Insight:** The `[1:0]` index already exists here - index [0] for lower, [1] for upper!

---

## Step 3: Mask Write Enable Based on Format (`zf_masked_wren`)

For packed formats, mask the write enable to control which latch pair gets the clock gate:

```systemverilog
// Lines 441-458 (tt_reg_bank.sv)
generate
  if (LATCH_ARRAY) begin : gen_masked_wren
    for (genvar row = 0; row < DEPTH; row++) begin : zf_masked_latch_row
      for (genvar i = 0; i < DATUMS_IN_LINE; i++) begin : zf_masked_datum_in_line
        always_comb begin
          // Check format - this determines which latch gets enabled
          if (write_upper_datum_fp4 || write_upper_datum_int8) begin
              // UPPER HALF ONLY: Only [1] latch gets clock gate
              zf_masked_wren[row][i] = {wren_zflags[row][i], 1'b0};
              //                         ↑ [1] enabled     ↑ [0] disabled
          end
          else if (write_lower_datum_fp4 || write_lower_datum_int8) begin
              // LOWER HALF ONLY: Only [0] latch gets clock gate
              zf_masked_wren[row][i] = {1'b0, wren_zflags[row][i]};
              //                         ↑ [1] disabled    ↑ [0] enabled
          end
          else begin
              // NORMAL (non-packed): Both halves get same enable
              zf_masked_wren[row][i] = {2{wren_zflags[row][i]}};
              //                         ↑ [1] and [0] both enabled
          end
        end
      end
    end
  end
endgenerate
```

**Output:**
```systemverilog
logic [DEPTH-1:0][DATUMS_IN_LINE-1:0][1:0] zf_masked_wren;
// zf_masked_wren[row][i][1] → Used as enable for ICG of second latch pair
// zf_masked_wren[row][i][0] → Used as enable for ICG of first latch pair
```

**Critical:** This is where the format-specific logic lives:
- **write_upper_datum_fp4/int8**: Only [1] latch gets clocked
- **write_lower_datum_fp4/int8**: Only [0] latch gets clocked  
- **Normal mode**: Both latches get same clock

---

## Step 4: Instantiate ICG and Generate Gated Clock

Now use the masked enable to gate the clock with an Integrated Clock Gate (ICG) module:

```systemverilog
// Lines 867-870 (tt_reg_bank.sv) - For UPPER latch pair [1]
tt_clkgater icg1(
    .i_clk(i_clk),                           // Main clock input
    .i_en(zf_masked_wren[row][i][1]),        // Enable signal (upper half)
    .i_te('0),                               // Test enable (disabled)
    .o_clk(gated_clk[row][i][1])             // ← GATED CLOCK OUTPUT
);
```

**What ICG Does:**
```
Internal behavior of tt_clkgater:
┌─────────────────────────────────┐
│  When i_en = 1:                 │
│  o_clk = i_clk (clock passes)   │
│                                 │
│  When i_en = 0:                 │
│  o_clk = 0 (clock is stopped)   │
└─────────────────────────────────┘
```

**Output:**
```systemverilog
logic gated_clk[row][i][1];
// = i_clk when zf_masked_wren[row][i][1] = 1
// = 0 when zf_masked_wren[row][i][1] = 0
```

---

## Step 5: Use Gated Clock in Always_Latch

Finally, use the gated clock to control the second latch pair:

```systemverilog
// Lines 873-885 (tt_reg_bank.sv)
always_latch begin                                             
  if (gated_clk[row][i][1]) begin
      // UPPER HALF: Write to bits [OUTPUT_DATUM_WIDTH-1:PACKED_DATUM_WIDTH]
      regs0.row[row].datum[i][OUTPUT_DATUM_WIDTH-1:PACKED_DATUM_WIDTH] <= 
          d_regs0.row[row].datum[i][OUTPUT_DATUM_WIDTH-1:PACKED_DATUM_WIDTH];
      
      // Update parity for upper half
      parity[row][i][1] <= 
          ^d_regs0.row[row].datum[i][OUTPUT_DATUM_WIDTH-1:PACKED_DATUM_WIDTH];
  end
end
```

**How It Works:**
1. **When gated_clk[row][i][1] is LOW** (no write):
   - Latch is **transparent** (data passes through combinationally)
   - Output Q = D (input flows to output)

2. **When gated_clk[row][i][1] is HIGH** (write enabled):
   - Latch becomes **opaque** (captures data)
   - Non-blocking assignment triggers on rising edge
   - Output Q holds the captured value

---

## Complete Signal Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Base Write Enable (per row/col)                     │
│                                                             │
│  write_causes ──→ [WRITE/ZERO_OUT/...] ──→ wren[row][i]    │
│                                           = 1 or 0         │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Zero-Flag Write Enable (for [0] and [1])            │
│                                                             │
│  wren[row][i] ──→ [Check zero-out condition] ──→ zf_wren[row][i]
│                                                  [1:0] both enabled
│                   [or] [both disabled]            or one enabled
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Format-Specific Masking                              │
│                                                             │
│  zf_wren[row][i] ──→ [Check write_upper/write_lower] ──→ zf_masked_wren[row][i]
│                                                           Selects [0] or [1]
│                     [write_upper_int8?]
│                     [yes] → {data, 1'b0}  ← Only [1] enabled
│                     [no]  → {1'b0, data}  ← Only [0] enabled
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 4: ICG Clock Gating (for [1])                          │
│                                                             │
│  tt_clkgater icg1 (                                        │
│    .i_clk(i_clk),                                          │
│    .i_en(zf_masked_wren[row][i][1]),  ← Enable for [1]    │
│    .o_clk(gated_clk[row][i][1])       ← Output [1]        │
│  );                                                        │
│                                                             │
│  gated_clk[row][i][1] = i_clk when enable=1               │
│                       = 0     when enable=0               │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Always_Latch with Gated Clock [1]                   │
│                                                             │
│  always_latch begin                                        │
│    if (gated_clk[row][i][1]) begin                        │
│      regs0.row[row].datum[i][UPPER_BITS] <= data;        │
│    end                                                     │
│  end                                                       │
│                                                             │
│  When gated_clk[1] LOW  → latch TRANSPARENT                │
│  When gated_clk[1] HIGH → latch CAPTURES data             │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Signal Relationships

```systemverilog
// Signal hierarchy showing how [1] comes from each layer:

wren[row][i]                    // Base enable (1 bit)
    ↓
zf_wren[row][i][1:0]           // Two-bit vector (one per latch pair)
    ├─ [0] = lower half enable
    └─ [1] = upper half enable  ← Used for [1]
    ↓
zf_masked_wren[row][i][1:0]    // Masked based on format
    ├─ [0] = final enable for latch pair 0
    └─ [1] = final enable for latch pair 1  ← Used for ICG
    ↓
tt_clkgater icg1(
    .i_en(zf_masked_wren[row][i][1]),  ← Index [1]
    .o_clk(gated_clk[row][i][1])       ← Index [1]
)
    ↓
always_latch begin
    if (gated_clk[row][i][1]) begin    ← Index [1]
        // UPPER half gets written
    end
end
```

---

## Why Two Latches [0] and [1]?

For **packed INT8/FP4 formats**, each datum location stores TWO values:

```
One Datum (16 bits)
┌─────────────────────┐
│  Bits [15:8]        │ ← Upper half (8 or 10 bits after packing)
│  Latch Pair [1]     │
├─────────────────────┤
│  Bits [7:0]         │ ← Lower half (8 or 10 bits after packing)
│  Latch Pair [0]     │
└─────────────────────┘
```

**Independent Clock Control:**
- Write INT8[0] → Clock gated_clk[0] only
- Write INT8[1] → Clock gated_clk[1] only
- Write normal FP32 → Clock both gated_clk[0] and gated_clk[1]

This allows **two-phase processing** within one cycle:
- Phase 1: Update lower half with gated_clk[0] pulse
- Phase 2: Update upper half with gated_clk[1] pulse

---

## RTL Implementation Checklist

To generate `gated_clk[row][i][1]` in your own RTL:

- [ ] **Declare signals:**
  ```systemverilog
  logic [DEPTH-1:0][DATUMS_IN_LINE-1:0][1:0] zf_wren;
  logic [DEPTH-1:0][DATUMS_IN_LINE-1:0][1:0] zf_masked_wren;
  logic [DEPTH-1:0][DATUMS_IN_LINE-1:0][1:0] gated_clk;
  ```

- [ ] **Generate zf_wren based on write format:**
  - Check `write_upper_datum_fp4 || write_upper_datum_int8`
  - Check `write_lower_datum_fp4 || write_lower_datum_int8`
  - Route to [1] or [0] or both accordingly

- [ ] **Generate zf_masked_wren from zf_wren:**
  - Apply format-specific masking
  - Result: Only enable the latch pair being written

- [ ] **Instantiate ICG for each latch pair:**
  ```systemverilog
  tt_clkgater icg0(.i_clk(i_clk),
                  .i_en(zf_masked_wren[row][i][0]),
                  .o_clk(gated_clk[row][i][0]));

  tt_clkgater icg1(.i_clk(i_clk),
                  .i_en(zf_masked_wren[row][i][1]),
                  .o_clk(gated_clk[row][i][1]));
  ```

- [ ] **Use in always_latch:**
  ```systemverilog
  always_latch begin
    if (gated_clk[row][i][1]) begin
      regs0[row][i][UPPER_BITS] <= d_regs0[row][i][UPPER_BITS];
    end
  end
  ```

---

## Common Mistakes to Avoid

❌ **Mistake 1: Forgetting the index [1]**
```systemverilog
// WRONG - missing [1] index
tt_clkgater icg1(.i_en(zf_masked_wren[row][i]), ...);

// RIGHT - include [1] index
tt_clkgater icg1(.i_en(zf_masked_wren[row][i][1]), ...);
```

❌ **Mistake 2: Using wrong bit range in always_latch**
```systemverilog
// WRONG - writing lower bits with [1] gated_clk
if (gated_clk[row][i][1]) begin
  regs0[row][i][7:0] <= d_regs0[row][i][7:0];  // Should use [0]
end

// RIGHT - use corresponding bit range
if (gated_clk[row][i][1]) begin
  regs0[row][i][15:8] <= d_regs0[row][i][15:8];  // Upper bits
end
```

❌ **Mistake 3: Enabling both latches in packed mode**
```systemverilog
// WRONG - enables both [0] and [1] for upper write
if (write_upper_datum_int8) begin
  zf_masked_wren[row][i] = {2{wren[row][i]}};  // Both enabled
end

// RIGHT - enable only [1] for upper write
if (write_upper_datum_int8) begin
  zf_masked_wren[row][i] = {wren[row][i], 1'b0};  // Only [1]
end
```

---

## Related RTL Files

| File | Purpose | Key Lines |
|------|---------|-----------|
| `tt_reg_bank.sv` | Register bank with latch logic | 441-458, 462-479, 867-870, 873-885 |
| `tt_clkgater.sv` | ICG module (clock gating cell) | N/A (standard cell) |
| `tt_gtile_dest.sv` | DEST instantiation | 575-595 (instantiates tt_reg_bank) |
| `tt_fpu_tile_srca.sv` | SRCA instantiation | Similar pattern to DEST |
| `tt_fpu_tile_srcb.sv` | SRCB instantiation | Similar pattern to DEST |

---

## Example: Minimal Complete Implementation

```systemverilog
// Minimal example: Single row, single datum
parameter DEPTH = 4;
parameter DATUMS_IN_LINE = 8;
parameter OUTPUT_DATUM_WIDTH = 16;
parameter PACKED_DATUM_WIDTH = 8;

// Step 1-3: Generate masked write enables
logic [DATUMS_IN_LINE-1:0][1:0] zf_masked_wren;

always_comb begin
  for (int i = 0; i < DATUMS_IN_LINE; i++) begin
    if (write_upper_int8) begin
      zf_masked_wren[i] = {write_enable, 1'b0};  // Only [1]
    end
    else if (write_lower_int8) begin
      zf_masked_wren[i] = {1'b0, write_enable};  // Only [0]
    end
    else begin
      zf_masked_wren[i] = {2{write_enable}};     // Both
    end
  end
end

// Step 4: Instantiate ICG and create gated clocks
logic [DATUMS_IN_LINE-1:0][1:0] gated_clk;

for (genvar i = 0; i < DATUMS_IN_LINE; i++) begin : gen_icg
  // ICG for lower half [0]
  tt_clkgater icg0(
    .i_clk(i_clk),
    .i_en(zf_masked_wren[i][0]),
    .i_te('0),
    .o_clk(gated_clk[i][0])
  );

  // ICG for upper half [1]
  tt_clkgater icg1(
    .i_clk(i_clk),
    .i_en(zf_masked_wren[i][1]),
    .i_te('0),
    .o_clk(gated_clk[i][1])
  );
end

// Step 5: Use in latch logic
logic [DATUMS_IN_LINE-1:0][OUTPUT_DATUM_WIDTH-1:0] reg_data;

always_latch begin
  for (int i = 0; i < DATUMS_IN_LINE; i++) begin
    // Lower half [0]
    if (gated_clk[i][0]) begin
      reg_data[i][PACKED_DATUM_WIDTH-1:0] <= input_data[i][PACKED_DATUM_WIDTH-1:0];
    end
    // Upper half [1]
    if (gated_clk[i][1]) begin
      reg_data[i][OUTPUT_DATUM_WIDTH-1:PACKED_DATUM_WIDTH] <= 
        input_data[i][OUTPUT_DATUM_WIDTH-1:PACKED_DATUM_WIDTH];
    end
  end
end
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-04-14  
**RTL Release Analyzed:** 20260221
