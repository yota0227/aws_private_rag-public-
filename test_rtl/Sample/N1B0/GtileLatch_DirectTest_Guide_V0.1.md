# G-Tile Latch Array Direct Test Path — Design Guide

**Version:** 0.1
**Date:** 2026-03-20
**Author:** N1B0 Design / DFX Team
**Target:** N1B0 Tensix tile — `tt_reg_bank` (DEST), `tt_srcb_registers` (SRCB), `tt_srca_reg_slice` (SRCA)

---

## Table of Contents

1. [Motivation — Why Latch Arrays Are Hard to Test](#1-motivation)
2. [Target Arrays](#2-target-arrays)
3. [Coverage Gap Analysis](#3-coverage-gap-analysis)
4. [Direct Test Path — What It Means](#4-direct-test-path--what-it-means)
5. [Implementation Strategy](#5-implementation-strategy)
   - 5.1 Scan Enable Bypass of ICG cells
   - 5.2 Functional Write Port Override (Scan-Write Mode)
   - 5.3 BIST Controller for Latch Arrays
   - 5.4 Loopback Data Path Verification
   - 5.5 LBIST Integration via IJTAG
6. [Where to Insert in RTL](#6-where-to-insert-in-rtl)
7. [Expected Coverage Improvement](#7-expected-coverage-improvement)
8. [Careful Things — Pitfalls and Constraints](#8-careful-things--pitfalls-and-constraints)
9. [Integration with Existing IJTAG Chain](#9-integration-with-existing-ijtag-chain)
10. [Test Content Guide (SW-Level)](#10-test-content-guide-sw-level)
11. [Verification Plan](#11-verification-plan)
12. [Work Summary & Next Steps](#12-work-summary--next-steps)

---

## 1. Motivation

### Why This Matters

The G-Tile latch arrays (DEST, SRCA, SRCB) represent a **large fraction of the functional silicon area** in each Tensix tile yet are essentially invisible to standard scan test:

| Register file | Instances per tile | Total instances (×12 tiles) | Bits per instance | Total bits |
|---------------|-------------------|---------------------------|--------------------|-----------|
| DEST (`tt_reg_bank`) | 16 | 192 | 4,096 × 19b = 77,824b | ~14.9 Mbits |
| SRCA (`tt_srca_reg_slice`) | 64 (8/G-Tile × 2 G-Tile × 4 T6) | 768 | 48 × 19b = 912b | ~703 Kbits |
| SRCB (`tt_srcb_registers`) | 4 (1 per T6) | 48 | 48×16×19b = 14,592b | ~700 Kbits |

> SRCA datum width: 48 rows × 1 column × 19 bits per instance (one column of the K-strip).
> SRCB datum width: 48 rows × 16 columns × 19 bits per instance (full-width, broadcast to both G-Tiles).

**Total latch storage at risk:** ≈ **16.3 Mbits** per chip — excluded from standard scan.

Without direct test paths, these arrays have the following defect coverage problem:
- **Stuck-at faults on bit-cells** — not observable through scan, only through functional patterns
- **ICG cell defects** — a stuck-open ICG cell holds a bit transparent forever; a stuck-closed cell freezes it
- **Write enable bridging faults** — datum[N] write enable leaks into datum[N+1]; extremely hard to detect functionally
- **Bit-line / word-line shorts** — only detectable with MARCH or checkerboard patterns, not random logic test
- **Stabilization latch failures** — the LOW-phase data capture latch at the ICG output is not in the scan chain

### Current State (N1B0 baseline)

The existing DFX structure in `tt_instrn_engine_wrapper_dfx.sv` provides an IJTAG entry point into FPU G-Tile 0 and FPU G-Tile 1 (under `INCLUDE_TENSIX_NEO_IJTAG_NETWORK`), but these connections currently reach the **instruction engine DFD** — not the G-Tile latch arrays themselves. The latch arrays have no dedicated test path.

---

## 2. Target Arrays

### 2.1 DEST Register File — `tt_reg_bank`

**Location (per T6 core, ×4 T6 per tile, ×2 G-Tile per T6):**
```
tt_tensix_with_l1
└── t6[0..3].neo.u_t6
    ├── gen_gtile[0].u_fpu_gtile
    │   └── gen_fp_cols[0..7].mtile_and_dest
    │       └── dest_slice.dest_reg_bank[2][4]   ← DEST latch array
    └── gen_gtile[1].u_fpu_gtile
        └── gen_fp_cols[8..15].mtile_and_dest
            └── dest_slice.dest_reg_bank[2][4]   ← DEST latch array
```

**Structure per instance:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| SETS | 4 banks | Ping-pong: {0,1} = FPU buf, {2,3} = SFPU/secondary |
| DEPTH | 64 rows/bank | 256 rows total (1024 with double-buffer = effective 512×2) |
| DATUMS_IN_LINE | 16 | = FPU column width |
| Datum width | 19 bits | TF19 (extended float) |
| Write enable | Per datum | 4,096 independent ICG cells per instance |
| Read type | Combinational | Zero latency, all rows visible as wires |
| Clock | i_ai_clk (gated per datum) | Two-phase: stabilization latch on LOW, data latch on HIGH |

**Total per tile:** 4 T6 × 2 G-Tile × (2 DEST slices [ping+pong]) = **16 `tt_reg_bank` instances**
- Total instances chip-wide: 16 × 12 tiles = **192**
- Total bits: 4,096 × 19 = **77,824 bits per instance** → 192 × 77,824 = **~14.9 Mbits**

### 2.2 SRCA Register File — `tt_srca_reg_slice`

**Location:** Inside each `u_fpu_mtile` — one slice per physical FP column, 8 columns per G-Tile:
```
gen_gtile[0].u_fpu_gtile → gen_fp_cols[0..7].mtile_and_dest.u_fpu_mtile.u_srca_reg_slice   (cols 0–7)
gen_gtile[1].u_fpu_gtile → gen_fp_cols[8..15].mtile_and_dest.u_fpu_mtile.u_srca_reg_slice  (cols 8–15)
```

> **Note on hierarchy tree notation:** The hierarchy CSV shows `gen_fp_cols[0..15]` nested under `gen_gtile[0..1]`, which looks like 16 instances per G-Tile. This is a formatting ambiguity — `[0..15]` is the **global column index across the whole T6**, and each G-Tile owns only half the range (8 columns). The FPU floorplan confirms: G-Tile[0] = cols 0–7, G-Tile[1] = cols 8–15.

**Structure per instance:**

| Parameter | Value | Notes |
|-----------|-------|-------|
| Rows (K-depth) | 48 | = K_tile max — stores one full K strip |
| Columns | 1 | One FP column's SRCA data |
| Datum width | 19 bits | TF19 (same as DEST) |
| Write enable | Per-datum ICG | One ICG cell per row |
| Write source | TDMA unpacker CH0 | |
| Read type | Combinational | Broadcast to FP Tile pipeline |

**Total per tile:** 4 T6 × 16 columns (8 per G-Tile × 2 G-Tiles) = **64 `tt_srca_reg_slice` instances**
- Total chip-wide: 64 × 12 tiles = **768**

### 2.3 SRCB Register File — `tt_srcb_registers`

**Location:** `u_fpu_v2` → `srcb_regs` (one per T6 core, bottom-center)
```
t6[0..3].neo.u_t6.u_fpu_v2.srcb_regs
```

**Structure:** Same ICG-latch structure as SRCA; 48 rows × 16 cols × 19b.
One instance per T6 → broadcast to both G-Tiles symmetrically.
**Total per tile:** 4 T6 → **4 instances**

---

## 3. Coverage Gap Analysis

### 3.1 Standard Scan Test — What It Misses

Standard stuck-at (ATPG) scan test covers flip-flop-based logic by capturing state at scan cells. Latch arrays using ICG gating are excluded because:

1. **No scan flip-flop in the data path.** The `always_latch` construct with `gated_clk[i][j]` does not insert a scan cell. Data and clock both bypass the scan chain.

2. **ICG cell test gap.** The `tt_clkgater` ICG has:
   - `i_en` (functional write enable)
   - `i_clk` (functional clock)
   - `o_clk` (gated clock → latch clock port)
   - **None of these are in the scan chain.** ICG enable stuck-at-0 (bit never writes) and stuck-at-1 (bit always transparent) are both untested.

3. **Stabilization latch unobservability.** The LOW-phase stabilization latch (write-data and write-control capture):
   ```systemverilog
   always_latch begin
       if (!cgated_clk) begin  // LOW phase
           wr_ctrl  <= internal_wr_ctrl;
           i_wrdata <= chosen_data;
       end
   end
   ```
   Both the data path and enable are invisible to scan.

4. **Write-enable bridging.** A bridge between `wren[row][datum]` and `wren[row][datum+1]` would cause one datum's write to corrupt the adjacent datum. Standard ATPG cannot distinguish this with high confidence.

### 3.2 Estimated Current Coverage (Before Fix)

| Fault class | DEST/SRCA/SRCB coverage | Root cause |
|-------------|------------------------|------------|
| Standard logic faults (mux, comparator, control) | ~95% | Covered by ATPG on surrounding logic |
| Stuck-at faults inside latch bit-cells | **~0%** | No scan observation |
| ICG enable stuck-at | **~10–20%** | Some ICG enables are driven from testable control, most are per-datum |
| Write enable bridging | **< 5%** | Requires write-specific patterns |
| Read multiplexing faults | **~60%** | Packer ATPG patterns exercise some read paths |
| **Effective DEST+SRCA fault coverage** | **~35–45%** (estimated) | — |

This coverage gap directly impacts **defect-per-million (DPM)** targets for AI compute workloads, where bit-cell defects in DEST produce silent data corruption.

---

## 4. Direct Test Path — What It Means

A **direct test path** for a latch array is a hardware mechanism that allows:

1. **Write:** An external test controller (scan, BIST, or functional loopback) to drive known data into any address without depending on the functional write datapath (TDMA/FPU).

2. **Read:** The written data to be read back to an observable point (scan chain output, BIST comparator, or dedicated test output) independent of the functional read path (FPU pipeline, packer).

3. **Enable control:** The ICG `i_en` signal to be overridden by a scan-enable or test-mode signal so that all latches become transparent during test, enabling shift-register-style access.

There are four practical implementations, in increasing complexity and coverage:

| Method | Coverage gain | RTL complexity | Area overhead | Test time |
|--------|--------------|----------------|---------------|-----------|
| **A: ICG scan override** | +25% | Low | < 0.1% | Moderate |
| **B: Functional loopback test** | +30% | Medium | 0% | Low (SW) |
| **C: Dedicated BIST controller** | +55% | High | ~0.3–0.5% | Low (HW) |
| **D: Full scan chain insertion** | +60% | Very high | ~2–3% | High |

Methods A+B together provide practical coverage of ~65–70% with acceptable overhead. A+B+C reaches ~85–90%.

---

## 5. Implementation Strategy

### 5.1 Method A — ICG Scan Enable Override

**Principle:** Add a `scan_enable` signal to every `tt_clkgater` ICG cell instance inside `tt_reg_bank`. When asserted, the ICG output is forced transparent (always-open) regardless of `i_en`. This converts the latch from ICG-gated to unconditionally transparent — making it a simple D latch that ATPG can drive and observe through surrounding scan cells.

**RTL change in `tt_reg_bank.sv`:**

```systemverilog
// BEFORE (current):
tt_clkgater icg_row0_dat0 (
    .i_en  ( zf_masked_wren[0][0] ),
    .i_clk ( i_clk ),
    .o_clk ( gated_clk[0][0] )
);

// AFTER (with scan override):
tt_clkgater icg_row0_dat0 (
    .i_en  ( zf_masked_wren[0][0] | i_scan_enable ),  // override when scan
    .i_clk ( i_clk ),
    .o_clk ( gated_clk[0][0] )
);
```

**New port added to `tt_reg_bank`:**
```systemverilog
input wire i_scan_enable,   // from DFX wrapper, driven high during scan shift
```

**Propagation path:**
```
tt_instrn_engine_wrapper_dfx
  └── IJTAG chain provides scan_enable signal
      → tt_fpu_gtile (new port: i_scan_enable)
          → gen_fp_cols[0..15].mtile_and_dest
              → dest_slice
                  → dest_reg_bank[*][*].i_scan_enable
              → u_fpu_mtile
                  → u_srca_reg_slice.i_scan_enable
```

**For SRCB** (`tt_srcb_registers`, located in `u_fpu_v2`):
```
t6[*].u_fpu_v2.srcb_regs.i_scan_enable
```
This requires a separate path from `tt_t6_l1_partition_dfx` since `tt_srcb_registers` is one level above `tt_fpu_gtile`.

**ATPG tool guidance:**
- Annotate `i_scan_enable` as a `test_point` in the ATPG TCL.
- Specify the latch as `set_attribute -name scan_cell_type -value level_sensitive_latch`.
- With ICG override, ATPG can now treat the latches as transparent storage — fault coverage increases significantly for stuck-at models.

**Careful things for Method A:**
- The ICG OR gate adds a small gate in the clock tree. Verify **CTS re-analysis** does not create hold violations on the latch clock port (ICG → latch) during functional mode.
- Add `set_false_path -from [get_ports i_scan_enable]` in the functional STA run to prevent the override path from affecting timing closure.
- Do NOT use a simple OR gate without a library-characterized ICG test-mode cell — use the `tt_clkgater` variant that natively supports a `test_enable` pin if one exists in the standard cell library.

---

### 5.2 Method B — Functional Write Port Override (Loopback Test)

**Principle:** Use the existing functional write path (TDMA unpacker → `srcb_wr_tran` / TDMA unpacker CH0 → SRCA) combined with the existing functional read path (packer / SFPU read), driven by TRISC software, to implement a **read-after-write loopback test** without any RTL changes.

This is **RTL-zero-cost** and available today.

**SW test kernel (TRISC0 / BRISC):**

```c
// Step 1: Write known pattern to DEST via MATH (MVMUL with identity)
// Write pattern: DEST[row] = {0xAAAA, 0x5555, 0x0000, 0xFFFF, ...} repeating
wrcfg(DEST_REGW_BASE, 0);
issue_sfpu(LOAD_IMM, row=0, data=0xAAAA_AAAA);   // SFPU writes to DEST directly
issue_sfpu(LOAD_IMM, row=1, data=0x5555_5555);
...for all 512 rows (ping buffer)...

// Step 2: Pack DEST to L1 via TDMA packer
wrcfg(PACK_CONFIG, { .src=DEST, .dst=L1_BASE, .format=INT16 });
issue_pack(all_rows);

// Step 3: Read L1 back via BRISC
for (int row = 0; row < 512; row++) {
    uint32_t expected = get_test_pattern(row);
    uint32_t actual   = L1_READ(L1_BASE + row * 32);
    if (actual != expected) report_error(row, actual, expected);
}
```

**Test patterns to use:**

| Pattern name | Pattern (per datum, 19-bit) | Fault detected |
|--------------|---------------------------|----------------|
| Checkerboard | `0b101...01 / 0b010...10` | Bit-line coupling |
| March C- | Write 0, verify 0, write 1, verify 1 (in order) | Stuck-at, transition |
| Diagonal | Datum[i] = 1 only at bit position (row+col) mod 19 | Address decoder faults |
| All-zeros | All bits 0 | Stuck-at-1 |
| All-ones | All bits 1 (`0x7FFFF`) | Stuck-at-0 |

**Coverage:** This loopback covers:
- ✅ Stuck-at faults in DEST bit-cells (all bits exercised)
- ✅ ICG fault: stuck-open ICG (bit never updates) → wrong read-back
- ✅ Row-address decoder faults (writing row N, reading back via packer verifies N)
- ✅ Datum-level write-enable bridging (adjacent columns cross-write → verified per-datum)
- ❌ Does NOT cover TDMA itself (but TDMA is in scan chain)
- ❌ Cannot isolate whether fault is in bit-cell vs. read path (need Method A for isolation)

**Extension for SRCA loopback:**
```c
// Load known pattern into SRCA via TDMA unpacker CH0
configure_tdma_src(CH0, pattern_src=L1_BASE, format=INT16);
issue_unpack(dest=SRCA, rows=48);           // writes SRCA[0..47]

// Trigger a NOP math operation so TRISC1 can wait for MATH_DONE
issue_mop(DOTPV, A=SRCA, B=SRCB_zero, C=DEST_zero, accum=0);

// Pack DEST (which absorbed SRCA×0 = 0) and verify DEST is all-zero
// Then compare SRCA input via trace or EDC counter-based detection
```

Note: SRCA read-back to an observable point requires a dummy multiply (SRCA × 0 = 0, read DEST) or the SFPU passthrough path. A direct SRCA read from TRISC is not available in the ISA — this is a **coverage gap for SRCA** that Method A (scan override) addresses.

---

### 5.3 Method C — Dedicated BIST Controller for Latch Arrays

**Principle:** Insert a small finite-state machine (BIST FSM) that autonomously writes and verifies patterns across the full DEST/SRCA array without TRISC involvement. The BIST FSM is accessible via the IJTAG chain.

**Architecture:**

```
IJTAG chain entry (tt_t6_l1_partition_dfx)
   │
   └─► [NEW] tt_latch_array_bist  (one per T6 or per G-Tile)
             │
             ├── bist_mode  (from IJTAG instruction register)
             ├── bist_start (from IJTAG DR)
             ├── bist_done  (to IJTAG DR, read back)
             ├── bist_fail  (to IJTAG DR)
             ├── fail_addr  (to IJTAG DR, first failing address)
             │
             ├── Override mux → tt_reg_bank.i_wr_data[*][*]
             ├── Override mux → tt_reg_bank.i_wren[*][*]
             ├── Override mux → tt_reg_bank.i_scan_enable (ICG override)
             └── Comparator ← tt_reg_bank.rd_data[*][*]  (combinational)
```

**BIST FSM states:**

```
IDLE
  │  bist_start (from IJTAG)
  ▼
WRITE_MARCH_0: write 0 to all addresses (row 0→255)
  │
  ▼
READ_MARCH_0:  read all addresses, compare = 0 (row 0→255)
  │  any mismatch → latch fail_addr, goto FAIL_LATCH
  ▼
WRITE_MARCH_1: write 1 to all addresses (row 0→255)
  │
  ▼
READ_MARCH_1:  read all addresses, compare = 0x7FFFF (row 0→255)
  │
  ▼
WRITE_CHKBRD:  write checkerboard (even rows = 0xAAAAA, odd = 0x55555)
  │
  ▼
READ_CHKBRD:   verify checkerboard
  │
  ▼
DONE: set bist_done, bist_fail=0
  │
FAIL_LATCH: set bist_done, bist_fail=1, fail_addr = address
```

**RTL module interface (new file: `tt_latch_array_bist.sv`):**

```systemverilog
module tt_latch_array_bist #(
    parameter DEPTH       = 256,   // rows to test (SETS * DEPTH per set)
    parameter DATUMS      = 16,
    parameter DATUM_WIDTH = 19
) (
    input  wire                                   i_clk,
    input  wire                                   i_rst_n,
    // IJTAG control (from DFX chain)
    input  wire                                   i_bist_start,
    output wire                                   o_bist_done,
    output wire                                   o_bist_fail,
    output wire [$clog2(DEPTH)-1:0]               o_fail_row,
    output wire [$clog2(DATUMS)-1:0]              o_fail_datum,
    // Override ports to tt_reg_bank (mux select + data + enables)
    output wire                                   o_bist_override,    // high = BIST drives reg_bank
    output wire [DATUM_WIDTH-1:0]                 o_bist_wrdata,
    output wire [DEPTH-1:0][DATUMS-1:0]           o_bist_wren,
    output wire                                   o_bist_scan_enable, // ICG override
    // Read data from reg_bank (combinational)
    input  wire [DEPTH-1:0][DATUMS-1:0][DATUM_WIDTH-1:0]  i_rd_data
);
```

**Mux insertion in `tt_reg_bank.sv`:**

```systemverilog
// AFTER adding BIST ports:
wire [DATUM_WIDTH-1:0] wr_data_mux = bist_override ? bist_wrdata  : i_wrdata;
wire [DATUMS-1:0]      wren_mux    = bist_override ? bist_wren[r] : zf_masked_wren[r];

tt_clkgater icg_r0_d0 (
    .i_en  ( wren_mux[0] | i_scan_enable | bist_scan_enable ),
    .i_clk ( i_clk ),
    .o_clk ( gated_clk[0][0] )
);
```

**Area estimate for BIST FSM:**
- Address counter: $clog2(256) = 8 bits → 8 flops
- Pattern generator: 19-bit LFSR or counter → ~25 flops
- Comparator: 19-bit XOR + OR reduction → ~25 gates
- FSM: 4-bit state → ~8 flops + transition logic
- **Estimated: ~500 standard cells per BIST instance** — negligible vs. reg_bank

For 12 tiles × 4 T6 = 48 BIST instances: ~24,000 cells total — less than 0.1% of tile area.

---

### 5.4 Loopback Data Path Verification

Even without a BIST FSM, a **minimal RTL addition** can create a loopback observable path:

**Add a dedicated test readout port** to `tt_reg_bank`:

```systemverilog
// New port (test_mode gated):
output wire [DATUM_WIDTH-1:0]  o_test_rdout,   // single datum readout
input  wire [$clog2(DEPTH*SETS)-1:0]   i_test_rdaddr,  // row address
input  wire [$clog2(DATUMS)-1:0]       i_test_rdcol,   // column
input  wire                             i_test_mode,    // gate: only active in test
```

```systemverilog
assign o_test_rdout = i_test_mode ?
    regs_flat[i_test_rdaddr][i_test_rdcol] :  // direct combinational read
    '0;
```

**Connected to IJTAG DR (test data register):**
```
tt_instrn_engine_wrapper_dfx
  → tt_fpu_gtile IJTAG DR
      [test_rdaddr[7:0] | test_rdcol[3:0] | o_test_rdout[18:0]]  ← 31-bit IJTAG DR
```

This allows **IJTAG-level read of any individual datum** from any row of DEST, with:
- Write: driven through existing IJTAG-controlled scan-write (Method A)
- Read: serialized out through IJTAG DR

Test throughput: 31 bits per TCK cycle × ~100 MHz TCK = read 1 datum per ~310 ns.
Full DEST readout: 4,096 datums × 310 ns ≈ 1.27 ms per instance — acceptable for production test.

---

### 5.5 LBIST Integration via IJTAG

For the highest coverage with minimum test time, integrate with **Tessent LBIST** using the existing IJTAG entry point:

**Proposed IJTAG DR extensions in `tt_instrn_engine_wrapper_dfx`:**

| DR bit field | Width | Function |
|-------------|-------|----------|
| `lbist_start` | 1 | Trigger LBIST run |
| `lbist_done` | 1 | Readback: LBIST finished |
| `lbist_fail` | 1 | Readback: any mismatch |
| `fail_syndrome` | 32 | Readback: MISR signature or fail address |
| `bist_mode` | 3 | Pattern select (March-C, checkerboard, all-0, all-1, PRPG) |
| `scan_enable` | 1 | ICG override enable (for ATPG shift) |

**IJTAG chain modification (in `tt_instrn_engine_wrapper_dfx.sv`, under `INCLUDE_TENSIX_NEO_IJTAG_NETWORK`):**

Current chain:
```
L1_partition → instrn_engine_wrapper (SIB) → G-Tile 0 → G-Tile 1 → DFD
```

Proposed extended chain:
```
L1_partition → instrn_engine_wrapper (SIB)
    ├── [NEW] latch_bist_ctrl (DR: start/done/fail/syndrome/mode/scan_en)
    ├── G-Tile 0
    │   ├── [NEW] dest_bist[0..7]  (8 DEST instances in G-Tile 0)
    │   └── [NEW] srca_bist[0..7]  (8 SRCA instances in G-Tile 0)
    ├── G-Tile 1
    │   ├── [NEW] dest_bist[8..15]
    │   └── [NEW] srca_bist[8..15]
    └── DFD
```

---

## 6. Where to Insert in RTL

### 6.1 Summary of RTL Files to Modify or Create

| File | Action | Change |
|------|--------|--------|
| `registers/rtl/tt_reg_bank.sv` | **Modify** | Add `i_scan_enable`, `i_bist_override`, `i_bist_wrdata`, `i_bist_wren`, `o_test_rdout`, `i_test_rdaddr/col`, `i_test_mode` ports; ICG enable OR logic |
| `tensix/fpu/rtl/tt_srca_reg_slice.sv` | **Modify** | Same ICG override additions as tt_reg_bank |
| `registers/rtl/tt_srcb_registers.sv` | **Modify** | Same ICG override additions |
| `dfx/tt_instrn_engine_wrapper_dfx.sv` | **Modify** | Add `latch_bist_ctrl` DR; route `scan_enable` to G-Tile 0/1 |
| `dfx/tt_t6_l1_partition_dfx.sv` | **Modify** | Route SRCB `scan_enable` and BIST start/done through T6-level chain |
| **NEW** `dfx/tt_latch_array_bist.sv` | **Create** | BIST FSM for March-C, checkerboard, all-0/1 patterns (one per T6) |
| `tensix/fpu/rtl/tt_fpu_gtile.sv` | **Modify** | Add `i_scan_enable`, `i_bist_*` ports; pass to `mtile_and_dest` |
| `tensix/fpu/rtl/tt_fpu_mtile.sv` | **Modify** | Pass through `i_scan_enable` to `u_srca_reg_slice`, `dest_slice` |
| `tensix/fpu/rtl/tt_fpu_v2.sv` | **Modify** | Route SRCB `scan_enable` to `srcb_regs` |

### 6.2 Port Addition Hierarchy

```
tt_instrn_engine_wrapper_dfx  [NEW port: o_scan_enable, o_bist_start, i_bist_done, i_bist_fail]
    │
    ▼  (to both G-Tiles)
tt_fpu_gtile  [NEW port: i_scan_enable, i_bist_start, o_bist_done, o_bist_fail]
    │
    ├─► gen_fp_cols[*].mtile_and_dest
    │       ├─► dest_slice
    │       │       └─► dest_reg_bank[*][*]  [NEW: i_scan_enable, i_bist_*]
    │       └─► u_fpu_mtile
    │               └─► u_srca_reg_slice     [NEW: i_scan_enable, i_bist_*]
    │
    └─► [NEW] tt_latch_array_bist  (BIST FSM, drives dest_reg_bank + u_srca_reg_slice)

tt_t6_l1_partition_dfx
    │
    ▼  (per T6 group)
t6[*].neo.u_t6.u_fpu_v2
    └─► srcb_regs  [NEW: i_scan_enable driven from tt_t6_l1_partition_dfx]
```

---

## 7. Expected Coverage Improvement

### 7.1 Per-Method Coverage Estimate

| Fault class | Baseline | +Method A (ICG scan override) | +Method B (SW loopback) | +Method C (BIST) |
|-------------|----------|-------------------------------|------------------------|-----------------|
| Bit-cell stuck-at | ~0% | +45% (ATPG can observe through transparent latch) | +30% (direct pattern) | +55% (full March-C) |
| ICG enable stuck-at-0 | ~10% | +70% (ICG forced transparent, en tested separately) | +20% | +85% |
| ICG enable stuck-at-1 | ~5% | +50% | +15% | +75% |
| Write-enable bridging | ~5% | +30% (ATPG patterns exercise enable signals) | +40% (diagonal pattern) | +60% |
| Stabilization latch faults | ~0% | +35% | +10% | +55% |
| Address decoder faults | ~60% | +70% | +80% (MARCH row-by-row) | +90% |
| **Overall DEST+SRCA coverage** | **~35–45%** | **~65–70%** | **~55–60%** | **~85–90%** |

**Combined Methods A+B:** ~75–80% (best practical baseline, zero hardware cost for B)
**Combined Methods A+B+C:** ~88–92%

### 7.2 DPM Impact Estimate

For a 12-tile N1B0 device with ~1.29 Mbits of latch storage:
- Defect density assumption: 0.1 defects/cm² (mature node)
- Latch array area: ~4 mm² total across all tiles (estimated from 12,288 reg_bank instances)
- Probability of at least one latch defect per die: `1 - e^{-d×A}` ≈ 1 - e^{-0.1×0.04} ≈ **0.4%** per die

At 35% current coverage: escaped defects = 0.4% × 65% = **~2,600 DPM**
At 90% coverage (A+B+C): escaped defects = 0.4% × 10% = **~400 DPM**
→ **~6× DPM reduction** for latch array faults.

---

## 8. Careful Things — Pitfalls and Constraints

### 8.1 Clock Safety — ICG Override Glitch Risk

**Problem:** Adding `i_scan_enable` to the ICG `i_en` input creates a new combinational path. If `scan_enable` transitions while `i_clk` is HIGH (when the latch is already transparent), the ICG output can glitch — causing an unintended write to the latch at a random data value.

**Mitigation:**
- Use a **library-qualified test-enable ICG cell** (`tt_clkgater_te`) that internally synchronizes the test-enable with the clock LOW phase before combining with `i_en`. Most standard cell libraries include this.
- In the DFX flow: assert `scan_enable` only when the clock is quiescent (scan shift clock, not functional clock). The IJTAG protocol guarantees this — TCK is separate from `i_ai_clk`.
- Add a formal check: `assert property (@(posedge i_ai_clk) !$rose(i_scan_enable) throughout (i_ai_clk ##0 1'b1))`.

### 8.2 Timing — Scan-Enable in Critical Clock Path

The ICG output clock is on the critical timing path for latch setup. Adding a gate before the ICG `i_en` port adds gate delay to the `i_en` → `o_clk` path. For `tt_clkgater`:

```
i_en ──[AND]── ICG latch ── o_clk ── latch clock port
                  ↑ new gate adds delay here
```

**Mitigation:**
- Insert the test-enable at the `scan_en_input` pin of `tt_clkgater_te` which is characterized separately from the `i_en` timing arc.
- If using a plain AND gate: mark `i_scan_enable → o_clk` as a `set_false_path` during functional STA (test_enable is deasserted in functional mode).

### 8.3 Multi-Cycle Write — BIST vs Functional Conflicts

The BIST FSM drives override muxes into `tt_reg_bank`. If BIST runs while the FPU is still active (e.g., during a soft-reset sequence), data corruption will occur.

**Mitigation:**
- Gate BIST start with a **tile-level reset qualifier**: `bist_start_gated = bist_start & !tensix_active`.
- In test silicon: assert BIST only after `tensix_reset_n` is asserted (tile fully reset).
- Formal assertion: `assume property (!bist_override || tensix_in_reset)`.

### 8.4 LATCH_ARRAY = 0 Path (Simulation / Flop Mode)

When `DEST_BANKS_USE_FLOPS` is defined or in Verilator simulation, `LATCH_ARRAY = 0` — the reg_bank uses flip-flops, not latches. The ICG-based override approach does not apply in flop mode.

**Mitigation:**
- Guard the ICG scan override logic with `if (LATCH_ARRAY)`:
  ```systemverilog
  if (LATCH_ARRAY) begin : gen_icg_te
      tt_clkgater_te icg_r0_d0 (
          .i_en  ( wren[0][0] ),
          .i_te  ( i_scan_enable ),   // test enable
          .i_clk ( i_clk ),
          .o_clk ( gated_clk[0][0] )
      );
  end else begin : gen_flop_path
      // flop path: CE = wren[0][0] — no ICG needed
      always_ff @(posedge i_clk)
          if (wren[0][0]) regs0.row[0].datum[0] <= d_regs0.row[0].datum[0];
  end
  ```
- The BIST FSM and test readout port should also be guarded or set to no-op in flop mode (ATPG covers flops natively).

### 8.5 Port Explosion — `i_scan_enable` Routing Overhead

Adding a `scan_enable` port through the deep hierarchy (FPU → G-Tile → M-Tile → reg_bank, ×192 instances) creates 192 new signal paths. P&R congestion is possible near the FPU block.

**Mitigation:**
- Route `scan_enable` as a **global tie-off signal** using a repeat tree (similar to scan_enable in standard cell scan chains). Use `tt_scan_enable_buf` (if available) inserted by the DFX tool.
- Alternatively, use a **IJTAG SIB-level register** that drives a per-G-Tile flop, which then drives all `tt_reg_bank` instances in that G-Tile. This reduces the routing to one signal per G-Tile (16 columns) rather than per-datum.
- Annotate in SDC: `set_dont_touch [get_nets scan_enable_*]` to prevent optimization from removing the buffer tree.

### 8.6 SRCB Special Case — Shared Instance, Two G-Tiles

`tt_srcb_registers` (SRCB) is a **single instance** shared between `gen_gtile[0]` and `gen_gtile[1]` via broadcast wires. The `scan_enable` for SRCB must therefore be driven from the **T6 level** (above both G-Tiles), not from within either G-Tile. This is different from DEST and SRCA which are per-column.

**Mitigation:**
- Drive SRCB `scan_enable` from `tt_t6_l1_partition_dfx` (which already has per-T6 IJTAG control), not from `tt_instrn_engine_wrapper_dfx`.
- BIST: add a separate SRCB BIST FSM instance inside `u_fpu_v2` or directly in `tt_t6_l1_partition_dfx`.

---

## 9. Integration with Existing IJTAG Chain

### Current Chain (when `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` defined)

```
External TAP
  → tt_noc_niu_router_dfx (entry: ijtag_si)
      → tt_t6_l1_partition_dfx (SIB)
          → T6 group 0 (ts0)
          → T6 group 1 (ts1)
          → T6 group 2 (ts2)
          → T6 group 3 (ts3)
          → L1 partition DFD
      → tt_instrn_engine_wrapper_dfx (SIB)
          → FPU G-Tile 0
          → FPU G-Tile 1
          → instruction engine DFD
  → output SO
```

### Proposed Extended Chain

```
External TAP
  → tt_noc_niu_router_dfx (entry)
      → tt_t6_l1_partition_dfx (SIB)
          → T6 group 0 (ts0)
          │   ├── [NEW] srcb_bist_ctrl DR (31 bits: start/done/fail/mode/scan_en)
          │   └── [NEW] srcb_test_rdout DR (31 bits: addr[7:0] + col[3:0] + data[18:0])
          → T6 group 1..3 (same)
          → L1 partition DFD
      → tt_instrn_engine_wrapper_dfx (SIB)
          ├── [NEW] latch_bist_ctrl DR (32 bits: start/done/fail/syndrome/mode)
          ├── [NEW] scan_enable DR (1 bit: drives all ICG overrides in this G-Tile)
          → FPU G-Tile 0
          │   ├── [NEW] dest_bist_result DR (done/fail/fail_row[7:0]/fail_col[3:0])
          │   └── [NEW] dest_test_rdout DR (row[7:0] + col[3:0] + data[18:0])
          → FPU G-Tile 1  (same additions)
          → instruction engine DFD
  → output SO
```

**IJTAG DR chain length for new additions:**
- latch_bist_ctrl: 32 bits
- scan_enable: 1 bit
- dest_bist_result (×2 G-Tiles): 2 × 24 = 48 bits
- dest_test_rdout (×2 G-Tiles): 2 × 31 = 62 bits
- srcb additions (×4 T6): 4 × 62 = 248 bits
- **Total new IJTAG bits per tile: ~391 bits** — adds ~5% to tile IJTAG chain length.

---

## 10. Test Content Guide (SW-Level)

For Method B (functional loopback, available without RTL changes):

### 10.1 DEST Full Coverage Test (BRISC SW)

```c
// ---- Write phase: SFPU LOAD_IMM to DEST all rows ----
// Use SFPU to write known pattern to DEST rows 0..511 (ping buffer)
void dest_march_c_write_zero(void) {
    for (int row = 0; row < 512; row++) {
        issue_sfpu_load_imm(row, 0x00000);  // 19-bit zero
    }
    wait_sfpu_done();
}

void dest_march_c_read_verify_zero(void) {
    // Pack DEST rows 0..511 to L1
    cfg_packer(src=DEST, dst=L1_DEST_BUF, format=INT16, rows=512);
    issue_pack_all();
    wait_pack_done();
    for (int row = 0; row < 512; row++) {
        uint16_t val = read_l1_word(L1_DEST_BUF + row*32);
        if (val != 0) log_fail(DEST, row, val, 0);
    }
}

// Same pattern for write-1, checkerboard, diagonal patterns
// Run MARCH-C sequence: W0, R0, W1, R1 in row-ascending and row-descending order
void dest_full_march_c_test(void) {
    dest_march_c_write_zero();   // W0 ascending
    dest_march_c_read_verify_zero();   // R0 ascending
    dest_march_c_write_ones();   // W1 ascending
    dest_march_c_read_verify_ones();   // R1 ascending
    dest_march_c_write_ones_descending();  // W1 descending
    dest_march_c_read_verify_ones_descending();
    dest_march_c_write_zero_descending();
    dest_march_c_read_verify_zero_descending();
}
```

### 10.2 SRCA Coverage Test (TDMA + MATH + Pack loopback)

```c
// Step 1: Load SRCA with checkerboard via unpacker CH0
cfg_unpacker(ch=0, src_l1=L1_CHKBRD, fmt=INT16, dst=SRCA, rows=48, cols=16);
issue_unpack_ch0();
wait_unpack_done();

// Step 2: Load SRCB with identity matrix (1 on diagonal) via unpacker CH1
// SRCB × identity = SRCA (so output to DEST = SRCA values)
cfg_unpacker(ch=1, src_l1=L1_IDENTITY, fmt=INT16, dst=SRCB, rows=48, cols=16);
issue_unpack_ch1();
wait_unpack_done();

// Step 3: Run MVMUL: DEST += SRCA × SRCB  (identity → DEST = SRCA)
cfg_mop(MVMUL, k_loop=48, m_rows=16);
issue_mop();
wait_math_done();

// Step 4: Pack DEST to L1 and compare against original SRCA pattern
cfg_packer(src=DEST, dst=L1_RESULT, fmt=INT16, rows=16);
issue_pack_all();
wait_pack_done();

compare_l1_buffers(L1_RESULT, L1_CHKBRD, rows=16*16);
```

---

## 11. Verification Plan

| Step | Item | Method | Pass criterion |
|------|------|--------|---------------|
| 1 | ICG scan override RTL simulation | UVM test with `scan_enable=1`, ATPG check | All DEST rows writeable and readable via ATPG session |
| 2 | Stabilization latch transparency | Formal (JasperGold): prove latch holds value when not writing | No counterexample in 20-cycle bounded proof |
| 3 | BIST FSM functional simulation | RTL sim with UVM driver | BIST done=1, fail=0 on clean memory model |
| 4 | BIST FSM fault injection | RTL sim with force/release of one datum stuck-at | BIST detects stuck-at within March-C |
| 5 | ICG bridging detection | Post-synthesis ATPG run with bridge fault model | >90% bridge fault coverage reported by Tessent |
| 6 | Loopback SW test on FPGA | Run Method B kernel on N1B0 emulation | All patterns pass with zero L1 compare failures |
| 7 | Full IJTAG chain integrity | IJTAG chain test (shift known pattern) | SI→SO shift passes with expected delay |
| 8 | Timing: ICG test-enable path | STA with test_mode=false_path exempt | No setup/hold violation in functional mode |
| 9 | Scan coverage reporting | Tessent ATPG coverage report after Method A | DEST+SRCA coverage ≥ 85% (stuck-at) |
| 10 | DPM correlation | Compare test escapes on silicon to pre-silicon estimate | Measured DPM ≤ 500 (target) |

---

## 12. Work Summary & Next Steps

### What Was Identified

1. **14.9 Mbits** of G-Tile latch storage (DEST + SRCA + SRCB, chip-wide) with **≈35–45% effective fault coverage** — a significant DPM risk.
2. Three root causes: ICG cells not in scan path, per-datum enables not ATPG-observable, stabilization latches invisible to scan.
3. The existing `tt_instrn_engine_wrapper_dfx` IJTAG chain provides the **correct entry point** for new test logic — the SIB chain already reaches G-Tile 0 and G-Tile 1.

### Recommended Implementation Path

| Priority | Method | RTL change | Coverage gain | Who |
|----------|--------|-----------|--------------|-----|
| **P0 (now)** | B: SW loopback test | None | +20–30% effective | SW / Arch team — run today |
| **P1 (next tape-out)** | A: ICG scan override | `tt_reg_bank.sv` + hierarchy ports | +25–35% | RTL + DFX team |
| **P2 (next tape-out)** | C: BIST FSM | New `tt_latch_array_bist.sv` + connections | +20–30% additional | DFX team |
| **P3 (future)** | D: Full scan insertion (Tessent) | Tessent insertion flow | +5–10% additional | DFX/CAD team |

**Target after P0+P1+P2:** ≥88% DEST+SRCA fault coverage, DPM ≤ 400.

### Open Questions

1. Does `tt_clkgater_te` (ICG with native test-enable pin) exist in the standard cell library? If not, Method A requires an AND gate — see §8.1 for mitigation.
2. Is there a per-column or per-G-Tile scan_enable distribution buffer already in the clock tree? Re-use it rather than routing new wires.
3. SFPU `tt_sfpu_lregs` (flip-flop, not latch) — currently excluded from this guide but should be included in standard scan chain. Verify ATPG covers it.
4. N1B0 `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` is not defined in production RTL — all new IJTAG additions require that this define be enabled. Confirm the define policy for N1B0 tape-out vs. bring-up RTL.

---

*RTL sources referenced:*
- *`used_in_n1/rtl/dfx/tt_instrn_engine_wrapper_dfx.sv`*
- *`used_in_n1/rtl/dfx/tt_t6_l1_partition_dfx.sv`*
- *`registers/rtl/tt_reg_bank.sv`*
- *`tensix/fpu/rtl/tt_fpu_gtile.sv`*
- *`tensix/fpu/rtl/tt_fpu_v2.sv`*
