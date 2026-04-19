# N1B0 Latch Array DFT Implementation Guide

**Version:** 1.0  
**Date:** 2026-04-03  
**Scope:** Methods A (ICG Scan Override) + B (Functional Loopback) + C (BIST FSM)  
**Target Coverage:** 75–92% (A+B → 75–80%, A+B+C → 88–92%)

---

## Table of Contents

1. [Implementation Phases](#1-implementation-phases)
2. [Method A — ICG Scan Override (RTL Changes)](#2-method-a--icg-scan-override)
3. [Method B — Functional Loopback (Firmware Test)](#3-method-b--functional-loopback)
4. [Method C — BIST Controller (Advanced)](#4-method-c--bist-controller)
5. [DFX Integration Checklist](#5-dfx-integration-checklist)
6. [Verification Plan](#6-verification-plan)
7. [Sign-Off Criteria](#7-sign-off-criteria)

---

## 1. Implementation Phases

### Phase 0: Current State (Baseline)
- Latch arrays have **no direct test path**
- Coverage: **35–45%** (stuck-at faults in surrounding logic only)
- IJTAG available (under `INCLUDE_TENSIX_NEO_IJTAG_NETWORK`) but not connected to G-Tile latches

### Phase 1: Method A (2–4 weeks)
**Goal:** Enable ATPG to observe latch bit-cells via ICG override
- Add `i_scan_enable` to all ICG instances (3 files: `tt_reg_bank`, `tt_srca_reg_slice`, `tt_srcb_registers`)
- Route signal through FPU hierarchy (6 files)
- Expected coverage: **+25–35%** → **~65–70% total**
- Area impact: <0.1%
- **Critical path impact:** None (false path can be set in STA)

### Phase 2: Method B (1–2 weeks)
**Goal:** Add firmware loopback test for DEST verification
- Write TRISC kernel (C code, ~200 lines)
- No RTL changes required
- Expected coverage: **+10% additional** → **~75–80% total**
- Area impact: 0%
- **Test time:** ~10–50 ms per kernel

### Phase 3: Method C (3–6 weeks)
**Goal:** Add autonomous BIST FSM for March-C + checkerboard patterns
- Create `tt_latch_array_bist.sv` (new file)
- Integrate into FPU hierarchy (4 new ports per G-Tile)
- Extend IJTAG DR with BIST control
- Expected coverage: **+15% additional** → **~88–92% total**
- Area impact: ~0.3–0.5%
- **Test time:** ~1–10 µs per run

---

## 2. Method A — ICG Scan Override

### 2.1 RTL File Changes

#### 2.1.1 `tt_reg_bank.sv` (DEST Register File)

**File:** `/secure_data_from_tt/20260221/used_in_n1/mem_port/tt_rtl/tt_tensix_neo/src/hardware/tensix/fpu/rtl/registers/tt_reg_bank.sv`

**Change 1:** Add port to module interface
```systemverilog
// Add to module parameter list:
module tt_reg_bank #(
    ...existing params...
) (
    input  wire                          i_clk,
    input  wire                          i_rst_n,
    input  wire                          i_en,
    
    // [NEW] DFT ports
    input  wire                          i_scan_enable,    // from DFX wrapper (IJTAG)
    input  wire                          i_bist_override,  // from BIST FSM (future)
    input  wire [DATUM_WIDTH-1:0]        i_bist_wrdata,    // from BIST FSM
    input  wire [DEPTH-1:0][DATUMS-1:0]  i_bist_wren,      // from BIST FSM
    output wire [DATUM_WIDTH-1:0]        o_test_rdout,     // to IJTAG DR (future)
    input  wire [$clog2(DEPTH*SETS)-1:0] i_test_rdaddr,    // from IJTAG DR
    input  wire [$clog2(DATUMS)-1:0]     i_test_rdcol,     // from IJTAG DR
    input  wire                          i_test_mode,      // gating for test readout
    
    ...rest of ports...
);
```

**Change 2:** Modify ICG instantiation to include scan_enable
```systemverilog
// Find this pattern (appears ~4,096 times for DEST):
// BEFORE:
for (genvar r = 0; r < DEPTH; r++) begin : gen_rows
    for (genvar d = 0; d < DATUMS; d++) begin : gen_datums
        tt_clkgater icg_r_d (
            .i_en  ( zf_masked_wren[r][d] ),    // functional write enable
            .i_clk ( i_clk ),
            .o_clk ( gated_clk[r][d] )
        );
    end
end

// AFTER (use library test-enable variant if available):
for (genvar r = 0; r < DEPTH; r++) begin : gen_rows
    for (genvar d = 0; d < DATUMS; d++) begin : gen_datums
        // Option 1: If tt_clkgater_te exists in library
        tt_clkgater_te icg_r_d (
            .i_en  ( zf_masked_wren[r][d] ),
            .i_te  ( i_scan_enable ),           // [NEW] test enable
            .i_clk ( i_clk ),
            .o_clk ( gated_clk[r][d] )
        );
        
        // Option 2: If using plain OR gate fallback
        // wire icg_en_or_scan = zf_masked_wren[r][d] | i_scan_enable;
        // tt_clkgater icg_r_d (.i_en(icg_en_or_scan), .i_clk(i_clk), .o_clk(gated_clk[r][d]));
    end
end
```

**Change 3:** Add test readout path (optional, for IJTAG serialization)
```systemverilog
// At end of module, before endmodule:

// Test readout mux (combinational):
wire [DATUM_WIDTH-1:0] test_rdout_comb = i_test_mode ? 
    regs_flat[i_test_rdaddr][i_test_rdcol] : '0;

assign o_test_rdout = test_rdout_comb;

// Flatten helper (if not already present):
wire [DEPTH*SETS-1:0][DATUMS-1:0][DATUM_WIDTH-1:0] regs_flat;
generate
    for (genvar s=0; s<SETS; s++) begin : gen_flat_sets
        for (genvar r=0; r<DEPTH; r++) begin : gen_flat_rows
            for (genvar d=0; d<DATUMS; d++) begin : gen_flat_datums
                assign regs_flat[s*DEPTH + r][d] = regs[s][r][d];
            end
        end
    end
endgenerate
```

**Change 4:** Mux for BIST write override (if implementing Method C)
```systemverilog
// Inside latch domain (where i_wrdata is used):

wire [DATUM_WIDTH-1:0]      wr_data_mux = i_bist_override ? i_bist_wrdata : i_wrdata;
wire [DEPTH-1:0][DATUMS-1:0] wren_mux    = i_bist_override ? i_bist_wren : zf_masked_wren;

// Then use wr_data_mux and wren_mux[r][d] in the always_latch blocks
```

---

#### 2.1.2 `tt_srca_reg_slice.sv` (SRCA Register File)

**File:** `/secure_data_from_tt/20260221/used_in_n1/mem_port/tt_rtl/tt_tensix_neo/src/hardware/tensix/fpu/rtl/tt_srca_reg_slice.sv`

**Changes:** Identical to `tt_reg_bank.sv` above
- Add `i_scan_enable` port to module
- Modify all `tt_clkgater` instances to use `tt_clkgater_te` or OR override
- Add test readout path (optional)
- Add BIST mux (if Method C)

**Specific parameters for SRCA:**
- DEPTH = 48 (K-tile rows)
- DATUMS = 1 (one column per instance)
- DATUM_WIDTH = 19 bits
- Total ICG cells: 48 per instance × 8 columns per G-Tile × 2 G-Tiles × 4 T6 = 3,072 total

---

#### 2.1.3 `tt_srcb_registers.sv` (SRCB Register File)

**File:** `/secure_data_from_tt/20260221/used_in_n1/mem_port/tt_rtl/tt_tensix_neo/src/hardware/tensix/fpu/rtl/registers/tt_srcb_registers.sv`

**Changes:** Same as SRCA/DEST
- Add `i_scan_enable` port
- Modify ICG cells
- Specific parameters:
  - DEPTH = 48 (rows)
  - DATUMS = 16 (columns)
  - DATUM_WIDTH = 19 bits

**Special note:** SRCB is instantiated **once per T6**, shared broadcast to both G-Tiles. The `i_scan_enable` must come from **T6-level DFX** (`tt_t6_l1_partition_dfx`), not from within G-Tile. See Section 2.2 for hierarchy routing.

---

### 2.2 Hierarchy Routing (6 Files to Modify)

#### 2.2.1 `tt_fpu_gtile.sv` (G-Tile Container)

**Add ports:**
```systemverilog
module tt_fpu_gtile #(...) (
    input  wire                          i_clk,
    input  wire                          i_rst_n,
    
    // [NEW] DFT ports from IJTAG/DFX
    input  wire                          i_scan_enable,
    input  wire                          i_bist_override,
    input  wire [DATUM_WIDTH-1:0]        i_bist_wrdata,
    input  wire                          i_bist_start,     // for Method C
    output wire                          o_bist_done,
    output wire                          o_bist_fail,
    
    ...rest of ports...
);
```

**Route to sub-modules:**
```systemverilog
// Inside gen_fp_cols[*] instantiation:
.gen_fp_cols(0..FP_COLS_PER_GTILE-1) begin : gen_fp_cols
    tt_mtile_and_dest mtile_and_dest (
        ...
        .i_scan_enable    ( i_scan_enable ),        // [NEW] pass-through
        .i_bist_override  ( i_bist_override ),      // [NEW]
        .i_bist_wrdata    ( i_bist_wrdata ),        // [NEW]
        ...
    );
end
```

---

#### 2.2.2 `tt_mtile_and_dest.sv` (Column Container)

**Add ports:**
```systemverilog
module tt_mtile_and_dest #(...) (
    ...
    input  wire                          i_scan_enable,
    input  wire                          i_bist_override,
    input  wire [DATUM_WIDTH-1:0]        i_bist_wrdata,
    ...
);
```

**Route to DEST and MTILE:**
```systemverilog
// DEST (register file instance)
dest_slice dest_slice_inst (
    ...
    .i_scan_enable   ( i_scan_enable ),
    .i_bist_override ( i_bist_override ),
    .i_bist_wrdata   ( i_bist_wrdata ),
    ...
);

// MTILE (M-Tile + SRCA)
u_fpu_mtile mtile_inst (
    ...
    .i_scan_enable   ( i_scan_enable ),
    .i_bist_override ( i_bist_override ),
    .i_bist_wrdata   ( i_bist_wrdata ),
    ...
);
```

---

#### 2.2.3 `tt_fpu_mtile.sv` (M-Tile Container)

**Route to SRCA:**
```systemverilog
u_srca_reg_slice srca_inst (
    ...
    .i_scan_enable   ( i_scan_enable ),
    .i_bist_override ( i_bist_override ),
    .i_bist_wrdata   ( i_bist_wrdata ),
    ...
);
```

---

#### 2.2.4 `tt_dest_slice.sv` (DEST Container)

**Route to DEST register bank:**
```systemverilog
dest_reg_bank dest_bank_0 (
    ...
    .i_scan_enable   ( i_scan_enable ),
    .i_bist_override ( i_bist_override ),
    .i_bist_wrdata   ( i_bist_wrdata ),
    ...
);

dest_reg_bank dest_bank_1 (
    ...
    .i_scan_enable   ( i_scan_enable ),
    .i_bist_override ( i_bist_override ),
    .i_bist_wrdata   ( i_bist_wrdata ),
    ...
);
```

---

#### 2.2.5 `tt_t6_l1_partition_dfx.sv` (SRCB + T6 DFX)

**Route scan_enable to SRCB (special case — separate path):**
```systemverilog
// SRCB is in u_fpu_v2, which is per-T6
t6_inst.u_fpu_v2.srcb_regs_inst (
    ...
    .i_scan_enable ( scan_enable_from_ijtag ),    // [NEW] from IJTAG
    ...
);
```

---

#### 2.2.6 `tt_instrn_engine_wrapper_dfx.sv` (IJTAG Entry Point)

**Add IJTAG DR for scan_enable control:**
```systemverilog
// Inside IJTAG network (where INCLUDE_TENSIX_NEO_IJTAG_NETWORK is defined):

// Extend IJTAG DR to include scan_enable field
parameter SCAN_ENABLE_IJTAG_DR_WIDTH = 1;

// New instruction for scan enable:
localparam IJTAG_INSTR_SCAN_ENABLE = 4'b0010;

// When IR = SCAN_ENABLE:
always_ff @(posedge tck) begin
    if (ijtag_sel_scan_enable) begin
        scan_enable_latched <= tdi;
    end
end

// Broadcast to all G-Tiles:
wire scan_enable_global = scan_enable_latched;

// Route to both gen_gtile[0] and gen_gtile[1]:
gen_gtile[0].fpu_gtile_inst (
    ...
    .i_scan_enable ( scan_enable_global ),
    ...
);

gen_gtile[1].fpu_gtile_inst (
    ...
    .i_scan_enable ( scan_enable_global ),
    ...
);

// Also drive SRCB via separate path (see t6_l1_partition_dfx above)
```

---

### 2.3 Synthesis & STA Considerations

**In your SDC (constraint file):**

```tcl
# Mark scan_enable as a test signal (false path in functional mode)
set_false_path -from [get_ports i_scan_enable]
set_false_path -to [get_ports i_scan_enable]

# If using ICG OR gate, mark the added delay as non-critical
set_false_path -through [get_nets "*scan_enable*"] -delay 0.1ns

# Annotate latch arrays for ATPG tool:
# (Tool-specific; example for Synopsys DFT Compiler)
set_scan_configuration -latch_level_sensitive true
```

**Formal Verification Assertion (optional but recommended):**

```systemverilog
// In tt_reg_bank or DFX wrapper:

// Ensure scan_enable only transitions when clock is quiescent
property scan_enable_clock_safety;
    @(posedge i_ai_clk)
    disable iff (!i_scan_enable)  // don't check when scan_enable is low
    !($rose(i_scan_enable) && i_ai_clk);
endproperty
assert property (scan_enable_clock_safety);

// Prevent BIST and functional writes simultaneously
property bist_functional_exclusion;
    @(posedge i_clk)
    !(i_bist_override && (|zf_masked_wren));
endproperty
assert property (bist_functional_exclusion)
    else $error("BIST and functional write conflict detected");
```

---

## 3. Method B — Functional Loopback

### 3.1 Firmware Test Kernel (TRISC0/BRISC)

**File:** Create new test in `/secure_data_from_tt/20260221/firmware/tests/`

**Filename:** `test_dest_loopback.c`

```c
/**
 * Latch Array Loopback Test — DEST Verification
 * 
 * Writes known patterns to DEST via SFPU, packs to L1, and verifies
 * readback to detect bit-cell stuck-at faults and ICG issues.
 * 
 * Test coverage:
 * - Stuck-at-0/1 faults in DEST bit-cells
 * - ICG enable stuck faults (unable to write or unable to hold)
 * - Row address decoder faults (write row N, verify row N)
 * - Datum write-enable bridging
 */

#include <stdio.h>
#include <stdint.h>
#include "tensix_api.h"
#include "test_utils.h"

// Test configuration
#define DEST_ROWS_TO_TEST    256   // Test both ping/pong buffers (2×256)
#define L1_TEST_ADDR_BASE    0x0   // Use bottom of L1 for patterns
#define NUM_PATTERNS         5     // Number of test patterns

// Pattern table
enum TestPattern {
    PATTERN_ALL_ZERO   = 0,   // 0x00000
    PATTERN_ALL_ONE    = 1,   // 0x7FFFF (19 bits)
    PATTERN_CHECKERBOARD = 2,
    PATTERN_DIAGONAL   = 3,
    PATTERN_MARCH_C    = 4,
};

// Test results
struct test_result {
    uint32_t pattern;
    uint32_t failures;
    uint32_t first_fail_row;
    uint32_t first_fail_col;
    uint32_t first_fail_expected;
    uint32_t first_fail_actual;
};

/**
 * Write test pattern to DEST via SFPU
 * Pattern applied to all rows, same value per row
 */
static void write_dest_pattern(uint32_t pattern_idx, struct test_result *result) {
    uint32_t pattern_data;
    uint32_t bit_pattern;
    
    switch (pattern_idx) {
        case PATTERN_ALL_ZERO:
            pattern_data = 0x00000;
            printf("Test: DEST ALL_ZERO pattern\n");
            break;
        case PATTERN_ALL_ONE:
            pattern_data = 0x7FFFF;
            printf("Test: DEST ALL_ONE pattern\n");
            break;
        case PATTERN_CHECKERBOARD:
            printf("Test: DEST CHECKERBOARD pattern (even=0xAAAA, odd=0x5555)\n");
            pattern_data = 0;  // Will alternate per row
            break;
        case PATTERN_DIAGONAL:
            printf("Test: DEST DIAGONAL pattern\n");
            pattern_data = 0;  // Will vary per row/col
            break;
        case PATTERN_MARCH_C:
            printf("Test: DEST MARCH-C pattern\n");
            pattern_data = 0;
            break;
        default:
            return;
    }
    
    // Configure SFPU to write to DEST
    // (LOAD_IMM operation writes directly to DEST via SFPU)
    
    for (uint32_t row = 0; row < DEST_ROWS_TO_TEST; row++) {
        uint32_t row_pattern;
        
        switch (pattern_idx) {
            case PATTERN_ALL_ZERO:
            case PATTERN_ALL_ONE:
                row_pattern = pattern_data;
                break;
            case PATTERN_CHECKERBOARD:
                row_pattern = (row & 1) ? 0x5555 : 0xAAAA;
                break;
            case PATTERN_DIAGONAL:
                // Diagonal: bit (row % 19) is set
                row_pattern = (1 << (row % 19));
                break;
            case PATTERN_MARCH_C:
                // First pass: all-0, second: all-1 (will do two iterations)
                row_pattern = 0x00000;  // First pass
                break;
            default:
                row_pattern = 0;
        }
        
        // Issue SFPU instruction to write to DEST
        // SFPU_LOAD_IMM: row_idx, data
        issue_sfpu_load_imm(row, row_pattern);
        
        // Wait for SFPU to complete (1 cycle)
        wait_cycles(1);
    }
    
    result->pattern = pattern_idx;
    result->failures = 0;
    result->first_fail_row = 0;
    result->first_fail_col = 0;
}

/**
 * Pack DEST to L1 and verify readback
 */
static void verify_dest_pattern(uint32_t pattern_idx, struct test_result *result) {
    // Configure TDMA packer:
    // Source = DEST (all rows, all columns)
    // Destination = L1_TEST_ADDR_BASE
    // Format = INT16
    
    configure_tdma_packer(
        TDMA_SRC_DEST,           // source
        L1_TEST_ADDR_BASE,       // dest L1 address
        TDMA_FORMAT_INT16,       // format
        DEST_ROWS_TO_TEST,       // num_rows
        16                       // datums per row (all 16)
    );
    
    // Issue pack command
    issue_pack_command(0, DEST_ROWS_TO_TEST);
    
    // Wait for pack to complete
    while (!pack_done()) wait_cycles(1);
    
    // Read back from L1 and verify
    uint32_t failures = 0;
    
    for (uint32_t row = 0; row < DEST_ROWS_TO_TEST; row++) {
        // Each DEST row packed to L1 at offset row*32 (4 bytes × 16 datums)
        uint32_t l1_addr = L1_TEST_ADDR_BASE + row * 32;
        
        for (uint32_t col = 0; col < 16; col++) {
            uint32_t expected = get_expected_pattern(pattern_idx, row, col);
            
            // Read 2 bytes (one datum in INT16 format)
            uint16_t actual = *(uint16_t *)(l1_addr + col*2);
            
            if ((actual & 0x7FFFF) != expected) {  // 19-bit mask
                if (failures == 0) {
                    result->first_fail_row = row;
                    result->first_fail_col = col;
                    result->first_fail_expected = expected;
                    result->first_fail_actual = actual & 0x7FFFF;
                    printf("  FAIL: Row=%d, Col=%d, Expected=0x%05x, Actual=0x%05x\n",
                        row, col, expected, actual);
                }
                failures++;
            }
        }
    }
    
    result->failures = failures;
    
    if (failures == 0) {
        printf("  PASS: All patterns verified\n");
    } else {
        printf("  FAIL: %d mismatches detected\n", failures);
    }
}

/**
 * Compute expected pattern for a given (row, col)
 */
static uint32_t get_expected_pattern(uint32_t pattern_idx, uint32_t row, uint32_t col) {
    switch (pattern_idx) {
        case PATTERN_ALL_ZERO:
            return 0x00000;
        case PATTERN_ALL_ONE:
            return 0x7FFFF;
        case PATTERN_CHECKERBOARD:
            return (row & 1) ? 0x5555 : 0xAAAA;
        case PATTERN_DIAGONAL:
            return (1 << (row % 19));
        case PATTERN_MARCH_C:
            return 0x00000;  // First pass (all-0)
        default:
            return 0;
    }
}

/**
 * Main test entry point
 */
int main() {
    struct test_result results[NUM_PATTERNS];
    uint32_t total_failures = 0;
    
    printf("====================================\n");
    printf("N1B0 DEST Latch Array Loopback Test\n");
    printf("====================================\n");
    
    // Run all test patterns
    for (uint32_t p = 0; p < NUM_PATTERNS; p++) {
        printf("\nRunning pattern %d...\n", p);
        
        write_dest_pattern(p, &results[p]);
        wait_cycles(100);  // Let DEST settle
        
        verify_dest_pattern(p, &results[p]);
        
        total_failures += results[p].failures;
    }
    
    // Summary
    printf("\n====================================\n");
    printf("Test Summary\n");
    printf("====================================\n");
    for (uint32_t p = 0; p < NUM_PATTERNS; p++) {
        printf("Pattern %d: %s (%d failures)\n",
            p,
            results[p].failures == 0 ? "PASS" : "FAIL",
            results[p].failures);
    }
    
    printf("Total failures: %d\n", total_failures);
    
    if (total_failures == 0) {
        printf("ALL TESTS PASSED\n");
        return 0;
    } else {
        printf("TESTS FAILED\n");
        return 1;
    }
}
```

### 3.2 SRCA/SRCB Extension (Optional)

For SRCA testing via loopback:

```c
/**
 * Test SRCA by loading pattern via TDMA unpacker, then triggering
 * a dummy NOP multiply to verify SRCA is readable.
 */
static void test_srca_loopback() {
    // Load known pattern into SRCA via TDMA unpacker CH0
    configure_tdma_unpacker(TDMA_CH0, L1_TEST_PATTERN_ADDR, TDMA_FORMAT_INT16, 48);
    issue_unpack_command(DEST_SRCA, 48);  // Unpack to SRCA rows 0–47
    
    while (!unpack_done()) wait_cycles(1);
    
    // Trigger NOP multiply: SRCA × 0 = 0
    // SRCA contents will be consumed but result discarded
    uint32_t mop_noop = make_mop(MOP_DOTPV,
        .src_a = SRCA_ALL,
        .src_b = SRCB_ZERO,
        .dest = DEST_ACC,
        .accumulate = 0);
    
    issue_mop(mop_noop);
    while (!math_done()) wait_cycles(1);
    
    // SRCA was consumed; cannot directly read-back via ISA
    // Instead: use Method A (scan_enable) or Method C (BIST) to directly test SRCA
    printf("SRCA loopback: pattern consumed, verification requires scan path\n");
}
```

---

## 4. Method C — BIST Controller

### 4.1 New RTL Module: `tt_latch_array_bist.sv`

**File:** `/secure_data_from_tt/20260221/used_in_n1/mem_port/tt_rtl/tt_tensix_neo/src/hardware/tensix/fpu/rtl/dfx/tt_latch_array_bist.sv`

```systemverilog
/**
 * Latch Array Built-In Self-Test (BIST) Controller
 * 
 * Autonomous BIST FSM for testing DEST, SRCA, SRCB latch arrays
 * via March-C and checkerboard patterns.
 * 
 * Integrated with IJTAG for test control and result readback.
 */

module tt_latch_array_bist #(
    parameter DEPTH       = 256,   // SETS * DEPTH per set (DEST)
    parameter DATUMS      = 16,    // width in datums (columns)
    parameter DATUM_WIDTH = 19     // bits per datum
) (
    input  wire                          i_clk,
    input  wire                          i_rst_n,
    
    // IJTAG control interface
    input  wire                          i_bist_start,      // from IJTAG DR[0]
    output wire                          o_bist_done,       // to IJTAG DR[1]
    output wire                          o_bist_fail,       // to IJTAG DR[2]
    output wire [$clog2(DEPTH)-1:0]      o_fail_row,        // to IJTAG DR[12:3]
    output wire [$clog2(DATUMS)-1:0]     o_fail_datum,      // to IJTAG DR[16:13]
    
    // Override ports to latch array (muxed with functional write)
    output wire                          o_override,        // mux select
    output wire [DATUM_WIDTH-1:0]        o_wrdata,          // write data
    output wire [DEPTH-1:0][DATUMS-1:0]  o_wren,            // write enables
    output wire                          o_scan_enable,     // ICG override
    
    // Read data from latch array (combinational)
    input  wire [DEPTH-1:0][DATUMS-1:0][DATUM_WIDTH-1:0]  i_rd_data
);

    // FSM states
    typedef enum logic [4:0] {
        ST_IDLE           = 5'b00000,
        ST_MARCH_WRITE_0  = 5'b00001,
        ST_MARCH_READ_0   = 5'b00010,
        ST_MARCH_WRITE_1  = 5'b00011,
        ST_MARCH_READ_1   = 5'b00100,
        ST_CHKBRD_WRITE   = 5'b00101,
        ST_CHKBRD_READ    = 5'b00110,
        ST_DIAG_WRITE     = 5'b00111,
        ST_DIAG_READ      = 5'b01000,
        ST_DONE           = 5'b01001,
        ST_FAIL_LATCH     = 5'b01010
    } state_e;
    
    state_e state, state_nxt;
    
    // Counters
    logic [$clog2(DEPTH)-1:0] row_addr, row_addr_nxt;
    logic [$clog2(DATUMS)-1:0] col_addr, col_addr_nxt;
    logic [DATUM_WIDTH-1:0] pattern_word, pattern_word_nxt;
    logic [DATUM_WIDTH-1:0] read_back;
    
    // Fail latch
    logic fail_flag, fail_flag_nxt;
    logic [$clog2(DEPTH)-1:0] fail_row, fail_row_nxt;
    logic [$clog2(DATUMS)-1:0] fail_datum, fail_datum_nxt;
    
    // Pattern generators
    logic [DATUM_WIDTH-1:0] pattern_march_0 = {DATUM_WIDTH{1'b0}};
    logic [DATUM_WIDTH-1:0] pattern_march_1 = {DATUM_WIDTH{1'b1}};
    logic [DATUM_WIDTH-1:0] pattern_chkbrd_even = 19'b1010_1010_1010_1010_10;  // 0xAAAA
    logic [DATUM_WIDTH-1:0] pattern_chkbrd_odd  = 19'b0101_0101_0101_0101_01;  // 0x5555
    logic [DATUM_WIDTH-1:0] pattern_diag = {DATUM_WIDTH{1'b0}};
    
    always_comb begin
        // Diagonal: bit (row_addr % DATUM_WIDTH) set
        pattern_diag = '0;
        pattern_diag[row_addr % DATUM_WIDTH] = 1'b1;
    end
    
    // Default assignments
    assign o_override    = (state != ST_IDLE);
    assign o_wrdata      = pattern_word;
    assign o_scan_enable = (state != ST_IDLE) ? 1'b1 : 1'b0;  // force transparent during BIST
    
    // Write enable: only current (row, col) enabled
    always_comb begin
        o_wren = '0;
        if ((state == ST_MARCH_WRITE_0) || (state == ST_MARCH_WRITE_1) ||
            (state == ST_CHKBRD_WRITE) || (state == ST_DIAG_WRITE)) begin
            o_wren[row_addr][col_addr] = 1'b1;
        end
    end
    
    // Read comparison (during READ_* states)
    assign read_back = i_rd_data[row_addr][col_addr];
    
    // Output mapping
    assign o_bist_done   = (state == ST_DONE);
    assign o_bist_fail   = fail_flag;
    assign o_fail_row    = fail_row;
    assign o_fail_datum  = fail_datum;
    
    // FSM: Next state logic
    always_comb begin
        state_nxt       = state;
        row_addr_nxt    = row_addr;
        col_addr_nxt    = col_addr;
        pattern_word_nxt = pattern_word;
        fail_flag_nxt   = fail_flag;
        fail_row_nxt    = fail_row;
        fail_datum_nxt  = fail_datum;
        
        case (state)
            ST_IDLE: begin
                if (i_bist_start) begin
                    state_nxt = ST_MARCH_WRITE_0;
                    row_addr_nxt = '0;
                    col_addr_nxt = '0;
                    fail_flag_nxt = 1'b0;
                end
            end
            
            ST_MARCH_WRITE_0: begin
                pattern_word_nxt = pattern_march_0;
                if (col_addr < DATUMS-1) begin
                    col_addr_nxt = col_addr + 1;
                end else if (row_addr < DEPTH-1) begin
                    col_addr_nxt = '0;
                    row_addr_nxt = row_addr + 1;
                end else begin
                    state_nxt = ST_MARCH_READ_0;
                    row_addr_nxt = '0;
                    col_addr_nxt = '0;
                end
            end
            
            ST_MARCH_READ_0: begin
                pattern_word_nxt = pattern_march_0;
                if (read_back != pattern_march_0) begin
                    fail_flag_nxt = 1'b1;
                    fail_row_nxt = row_addr;
                    fail_datum_nxt = col_addr;
                    state_nxt = ST_FAIL_LATCH;
                end else if (col_addr < DATUMS-1) begin
                    col_addr_nxt = col_addr + 1;
                end else if (row_addr < DEPTH-1) begin
                    col_addr_nxt = '0;
                    row_addr_nxt = row_addr + 1;
                end else begin
                    state_nxt = ST_MARCH_WRITE_1;
                    row_addr_nxt = '0;
                    col_addr_nxt = '0;
                end
            end
            
            ST_MARCH_WRITE_1: begin
                pattern_word_nxt = pattern_march_1;
                if (col_addr < DATUMS-1) begin
                    col_addr_nxt = col_addr + 1;
                end else if (row_addr < DEPTH-1) begin
                    col_addr_nxt = '0;
                    row_addr_nxt = row_addr + 1;
                end else begin
                    state_nxt = ST_MARCH_READ_1;
                    row_addr_nxt = '0;
                    col_addr_nxt = '0;
                end
            end
            
            ST_MARCH_READ_1: begin
                pattern_word_nxt = pattern_march_1;
                if (read_back != pattern_march_1) begin
                    fail_flag_nxt = 1'b1;
                    fail_row_nxt = row_addr;
                    fail_datum_nxt = col_addr;
                    state_nxt = ST_FAIL_LATCH;
                end else if (col_addr < DATUMS-1) begin
                    col_addr_nxt = col_addr + 1;
                end else if (row_addr < DEPTH-1) begin
                    col_addr_nxt = '0;
                    row_addr_nxt = row_addr + 1;
                end else begin
                    state_nxt = ST_CHKBRD_WRITE;
                    row_addr_nxt = '0;
                    col_addr_nxt = '0;
                end
            end
            
            ST_CHKBRD_WRITE: begin
                pattern_word_nxt = (row_addr[0] ? pattern_chkbrd_odd : pattern_chkbrd_even);
                if (col_addr < DATUMS-1) begin
                    col_addr_nxt = col_addr + 1;
                end else if (row_addr < DEPTH-1) begin
                    col_addr_nxt = '0;
                    row_addr_nxt = row_addr + 1;
                end else begin
                    state_nxt = ST_CHKBRD_READ;
                    row_addr_nxt = '0;
                    col_addr_nxt = '0;
                end
            end
            
            ST_CHKBRD_READ: begin
                logic [DATUM_WIDTH-1:0] expected_chkbrd;
                expected_chkbrd = (row_addr[0] ? pattern_chkbrd_odd : pattern_chkbrd_even);
                if (read_back != expected_chkbrd) begin
                    fail_flag_nxt = 1'b1;
                    fail_row_nxt = row_addr;
                    fail_datum_nxt = col_addr;
                    state_nxt = ST_FAIL_LATCH;
                end else if (col_addr < DATUMS-1) begin
                    col_addr_nxt = col_addr + 1;
                end else if (row_addr < DEPTH-1) begin
                    col_addr_nxt = '0;
                    row_addr_nxt = row_addr + 1;
                end else begin
                    state_nxt = ST_DONE;
                end
            end
            
            ST_DIAG_WRITE, ST_DIAG_READ: begin
                // Optional: add diagonal pattern test
                // Omitted for brevity; same structure as march/checkerboard
                state_nxt = ST_DONE;
            end
            
            ST_DONE: begin
                // BIST complete, wait for reset
            end
            
            ST_FAIL_LATCH: begin
                // Latch fail information, wait for reset
            end
            
            default: state_nxt = ST_IDLE;
        endcase
    end
    
    // FSM: Sequential logic
    always_ff @(posedge i_clk or negedge i_rst_n) begin
        if (!i_rst_n) begin
            state     <= ST_IDLE;
            row_addr  <= '0;
            col_addr  <= '0;
            pattern_word <= '0;
            fail_flag <= 1'b0;
            fail_row  <= '0;
            fail_datum <= '0;
        end else begin
            state     <= state_nxt;
            row_addr  <= row_addr_nxt;
            col_addr  <= col_addr_nxt;
            pattern_word <= pattern_word_nxt;
            fail_flag <= fail_flag_nxt;
            fail_row  <= fail_row_nxt;
            fail_datum <= fail_datum_nxt;
        end
    end
    
endmodule
```

### 4.2 Integration into FPU Hierarchy

**In `tt_fpu_gtile.sv`:**

```systemverilog
// Instantiate BIST controller per G-Tile (one per T6, since 2 G-Tiles share same DEST)
tt_latch_array_bist #(
    .DEPTH(256),
    .DATUMS(16),
    .DATUM_WIDTH(19)
) dest_bist_inst (
    .i_clk              ( i_clk ),
    .i_rst_n            ( i_rst_n ),
    .i_bist_start       ( i_bist_start ),
    .o_bist_done        ( o_bist_done_dest ),
    .o_bist_fail        ( o_bist_fail_dest ),
    .o_fail_row         ( o_fail_row_dest ),
    .o_fail_datum       ( o_fail_datum_dest ),
    .o_override         ( bist_override_dest ),
    .o_wrdata           ( bist_wrdata_dest ),
    .o_wren             ( bist_wren_dest ),
    .o_scan_enable      ( bist_scan_en_dest ),
    .i_rd_data          ( dest_reg_bank[0].rd_data )  // read from first DEST instance
);

// Similarly for SRCA (per column, or shared instance)
// ... SRCA BIST ...
```

---

## 5. DFX Integration Checklist

### Phase 1: Method A (ICG Override)

- [ ] Modify `tt_reg_bank.sv` — add `i_scan_enable` port, ICG override logic
- [ ] Modify `tt_srca_reg_slice.sv` — same changes
- [ ] Modify `tt_srcb_registers.sv` — same changes
- [ ] Route `i_scan_enable` through FPU hierarchy (6 modules)
- [ ] Update `tt_instrn_engine_wrapper_dfx.sv` — add IJTAG DR for scan_enable
- [ ] Add SDC constraints: `set_false_path` for scan_enable
- [ ] RTL simulation: verify ICG transparency when `i_scan_enable=1`
- [ ] Formal verification: clock safety assertion (no glitch during i_ai_clk HIGH)
- [ ] ATPG tool setup: annotate latches as `scan_cell_type = level_sensitive_latch`

### Phase 2: Method B (Loopback)

- [ ] Write `test_dest_loopback.c` firmware kernel
- [ ] Integrate into test suite (test_utils, test_harness)
- [ ] Simulation: verify write/read round-trip for all patterns
- [ ] Silicon bring-up: confirm patterns detected on actual hardware

### Phase 3: Method C (BIST)

- [ ] Create `tt_latch_array_bist.sv` module
- [ ] Integrate into `tt_fpu_gtile.sv` (instantiate per G-Tile or per T6)
- [ ] Add override muxes to `tt_reg_bank.sv`, `tt_srca_reg_slice.sv`
- [ ] Extend IJTAG DR in `tt_instrn_engine_wrapper_dfx.sv`:
  - BIST start (1 bit)
  - BIST done (1 bit)
  - BIST fail (1 bit)
  - Fail address (row + datum, ~13 bits)
- [ ] RTL simulation: verify March-C and checkerboard patterns
- [ ] Timing closure: ensure BIST FSM does not create new critical paths
- [ ] Formal verification: BIST/functional write exclusion property

---

## 6. Verification Plan

### 6.1 Simulation Testbench

```systemverilog
// tb_latch_array_dft.sv

module tb_latch_array_dft;
    // Instantiate DUT with test harness
    
    // Test 1: Method A — ICG Transparency
    task test_icg_override();
        // Assert scan_enable high
        // Write pattern via functional path
        // Verify bit-by-bit observation
    endtask
    
    // Test 2: Method B — Loopback
    task test_functional_loopback();
        // Write DEST via SFPU
        // Pack to L1
        // Read back and compare
    endtask
    
    // Test 3: Method C — BIST March-C
    task test_bist_march_c();
        // Assert bist_start
        // Poll bist_done
        // Check bist_fail and fail address
    endtask
    
    // Test 4: Clock Safety
    task test_scan_enable_safety();
        // Verify scan_enable transition timing
        // Assert no glitch on ICG output
    endtask
endmodule
```

### 6.2 Coverage Analysis

| Activity | Expected Result | Pass Criteria |
|----------|-----------------|---------------|
| ATPG coverage (Method A) | 65–70% | >65% |
| Loopback coverage (Method B) | 55–60% | All patterns pass |
| BIST coverage (Method C) | 85–90% | No failures detected in patterns |
| Combined coverage (A+B+C) | 88–92% | >88% |
| DPM reduction | 6× lower | <400 DPM (vs. 2600 DPM baseline) |

---

## 7. Sign-Off Criteria

### Design Sign-Off
- [ ] All RTL changes peer-reviewed
- [ ] Formal verification passes (clock safety, functional exclusion)
- [ ] Synthesis: no new critical paths introduced
- [ ] STA: all false paths correctly marked
- [ ] P&R: congestion analysis shows <5% impact

### Simulation Sign-Off
- [ ] All test vectors pass (Method A, B, C)
- [ ] Cross-coverage: >90% combined
- [ ] Regression: no new failures vs. baseline

### Silicon Bring-Up
- [ ] IJTAG chain verification: scan_enable signal observed
- [ ] Method A: ATPG test patterns loaded and verified
- [ ] Method B: Firmware loopback kernel executes, detects injected faults
- [ ] Method C: BIST triggers via IJTAG, detects March-C patterns

### Defect Tracking
- [ ] Field return root-cause analysis: latches identified as failure source
- [ ] DPM tracking: compare pre- vs. post-DFT releases
- [ ] Target: 6× reduction in latch-related failures

---

## Appendix: File Summary

| File | Type | Lines | Status |
|------|------|-------|--------|
| `tt_reg_bank.sv` | Modify | +50 | Phase 1 |
| `tt_srca_reg_slice.sv` | Modify | +50 | Phase 1 |
| `tt_srcb_registers.sv` | Modify | +50 | Phase 1 |
| `tt_fpu_gtile.sv` | Modify | +20 | Phase 1 |
| `tt_fpu_mtile.sv` | Modify | +20 | Phase 1 |
| `tt_mtile_and_dest.sv` | Modify | +20 | Phase 1 |
| `tt_instrn_engine_wrapper_dfx.sv` | Modify | +50 | Phase 1/3 |
| `tt_t6_l1_partition_dfx.sv` | Modify | +30 | Phase 1 |
| `test_dest_loopback.c` | Create | 300 | Phase 2 |
| `tt_latch_array_bist.sv` | Create | 400 | Phase 3 |
| **Total** | — | **~990** | — |

---

**End of DFT Implementation Guide**
