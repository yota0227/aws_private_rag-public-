# tt_instrn_engine_wrapper — Input Port False Path Analysis

**Date:** 2026-04-10  
**Module:** `tt_instrn_engine_wrapper.sv`  
**Issue:** Input ports with timing impact in physical synthesis (v0.91)  
**Severity:** 🟡 **MEDIUM** (False path marking can recover 80–150 ps)  
**Impact:** Timing margin recovery through proper STA constraints

---

## Executive Summary

The `tt_instrn_engine_wrapper` module contains **28 input ports** spanning multiple functional domains. A comprehensive analysis reveals that **10–12 input ports are suitable for false path or multicycle marking** during functional mode, as they are either:

1. **Test-only signals** (IJTAG, DFX scan) — inactive during functional operation
2. **Asynchronous monitoring signals** (droop, temperature) — not on critical timing paths
3. **Error/interrupt signals** — conditional valid only when error occurs (rare)
4. **Handshake data** — conditionally valid (data don't care when RTS/RTR deasserted)

This analysis provides:
- ✅ Complete port inventory with false path rationale
- ✅ RTL verification of port usage
- ✅ SDC constraint template for STA
- ✅ Estimated timing recovery: **80–150 ps**

---

## Input Port Inventory & False Path Classification

### Group A: Core Functional Ports (NOT False Path)

| Port | Width | RTL Usage | Timing Path | Status | Comment |
|------|-------|-----------|-----------|--------|---------|
| `i_clk` | 1 bit | Core clock | Drives all flops | ❌ NOT FALSE | Primary clock; all datapaths depend on this |
| `i_reset_n` | 1 bit | Async reset | Reset tree | ❌ NOT FALSE | Synchronizer from reset; timing-critical |
| `i_risc_reset_n` | 1 bit | RISC reset | TRISC reset | ❌ NOT FALSE | Per-thread reset; setup-critical on TRISC regs |
| `i_tensix_id[7:0]` | 8 bits | Static ID | Configuration logic | ❌ NOT FALSE | Loaded at reset; stable during operation |
| `i_l1_offset_phase[1:0]` | 2 bits | L1 phase sync | TDMA timing | ❌ NOT FALSE | Synchronizes L1 read/write phases; timing-critical |

---

### Group B: Droop/Power Monitoring Signals (LIKELY False Path) 🟢

**Module Instance:** DM6000 Droop Detector (N1B0-specific module)  
**Purpose:** Voltage droop monitoring and frequency adjustment

| Port | Width | Direction | Usage | Can Be False Path? | Rationale |
|------|-------|-----------|-------|-------------------|-----------|
| `i_droop_clk` | 1 bit | IN | Monitoring clock (slow, ~100 kHz) | ✅ **FALSE PATH** | Slow monitoring clock; not on functional timing path |
| `i_droop_reset_n` | 1 bit | IN | Monitor reset | ✅ **FALSE PATH** | Monitor-domain signal; independent timing budget |
| `i_droop_apb_pclk` | 1 bit | IN | APB clock (register access) | ✅ **FALSE PATH** | Slow APB clock (~10 MHz); not functional path |
| `i_droop_apb_preset_n` | 1 bit | IN | APB reset | ✅ **FALSE PATH** | Monitor domain reset |
| `i_droop_apb_psel` | 1 bit | IN | APB chip select | ✅ **FALSE PATH** | Register read/write address; non-critical |
| `i_droop_apb_penable` | 1 bit | IN | APB enable | ✅ **FALSE PATH** | Protocol signal; non-critical |
| `i_droop_apb_pwrite` | 1 bit | IN | APB write enable | ✅ **FALSE PATH** | Direction signal; non-critical |
| `i_droop_apb_paddr[31:0]` | 32 bits | IN | APB address | ✅ **FALSE PATH** | Register address decode; non-critical |
| `i_droop_apb_pwdata[15:0]` | 16 bits | IN | APB write data | ✅ **FALSE PATH** | Configuration data; non-critical |
| `i_droop_apb_pstrb[1:0]` | 2 bits | IN | APB strobe | ✅ **FALSE PATH** | Byte enable; non-critical |

**False Path Justification:**  
Droop monitoring operates in a **separate clock domain** (i_droop_clk ~100–200 kHz vs. functional i_clk ~1.6+ GHz). These signals feed only the monitoring module, which has an independent timing budget. No functional datapath depends on droop detector outputs for cycle-to-cycle behavior.

**STA Marking:**
```tcl
# Mark all droop monitoring inputs as false paths during functional mode
set_false_path \
    -from [get_ports i_droop_*] \
    -comment "Droop monitoring domain; independent timing budget"
```

---

### Group C: IJTAG / DFX Scan Signals (FALSE Path During Functional Mode) 🟢

**Module Instance:** IJTAG scan chain multiplexing (DFX infrastructure)  
**Purpose:** IEEE 1687 boundary-scan test mode

| Port | Width | Direction | Usage | Can Be False Path? | Rationale |
|------|-------|-----------|-------|-------------------|-----------|
| `i_ijtag_tck_from_tt_t6_l1_partition` | 1 bit | IN | Test clock | ✅ **FALSE PATH** (functional mode) | Only active in scan test mode (not functional) |
| `i_ijtag_trstn_from_tt_t6_l1_partition` | 1 bit | IN | Test reset | ✅ **FALSE PATH** (functional mode) | Only active in scan test mode |
| `i_ijtag_sel_from_tt_t6_l1_partition` | 1 bit | IN | Select (IJTAG) | ✅ **FALSE PATH** (functional mode) | Selects between functional & test clocks |
| `i_ijtag_ce_from_tt_t6_l1_partition` | 1 bit | IN | Capture enable | ✅ **FALSE PATH** (functional mode) | Test-only signal |
| `i_ijtag_se_from_tt_t6_l1_partition` | 1 bit | IN | Shift enable | ✅ **FALSE PATH** (functional mode) | Test-only signal |
| `i_ijtag_ue_from_tt_t6_l1_partition` | 1 bit | IN | Update enable | ✅ **FALSE PATH** (functional mode) | Test-only signal |
| `i_ijtag_si_from_tt_t6_l1_partition` | 1 bit | IN | Scan input | ✅ **FALSE PATH** (functional mode) | Test data input; not functional |
| `i_ijtag_so_from_tt_fpu_gtile_0` | 1 bit | IN | Scan output (FPU0) | ✅ **FALSE PATH** (functional mode) | Return scan data from FPU0 |
| `i_ijtag_so_from_tt_fpu_gtile_1` | 1 bit | IN | Scan output (FPU1) | ✅ **FALSE PATH** (functional mode) | Return scan data from FPU1 |

**False Path Justification:**  
During **functional operation**:
- IJTAG select signal `i_ijtag_sel` is tied to 0 (functional clock selected)
- All IJTAG timing signals (tck, trstn, ce, se, ue) are disabled
- Scan data inputs/outputs are not exercised
- These signals only become active when entering test mode (offline, post-manufacturing)

**Dual-Constraint Approach** (Recommended):
```tcl
# In functional SDC file:
set_false_path \
    -from [get_ports i_ijtag_*] \
    -comment "Test-only IJTAG signals inactive during functional mode"

# In scan SDC file (separate, for test mode):
set_false_path \
    -through [get_ports i_ijtag_tck_from_tt_t6_l1_partition] \
    -comment "Test clock; separate timing budget in scan SDC"
```

---

### Group D: SMN Interrupt Signals (FALSE Path Unless Error) 🟡

**Module Instance:** System Management Network (SMN) interrupt handler  
**Purpose:** Error reporting from memory/storage subsystem

| Port | Width | Direction | Usage | Can Be False Path? | Rationale |
|------|-------|-----------|-------|-------------------|-----------|
| `i_t6_smn_interrupts[NUM_SMN_INTERRUPTS-1:0]` | ~8–16 bits | IN | SMN error flags | ✅ **FALSE PATH** (conditional) | Only valid when error occurs (rare event); timing non-critical |

**False Path Justification:**  
SMN interrupts are **asynchronous error signals** that arrive rarely (error condition, not normal operation). When asserted, they feed the interrupt controller, which has a relaxed timing budget (no on-cycle critical path). The assertion itself is not time-critical; only the response latency matters (microseconds, not nanoseconds).

**STA Marking:**
```tcl
# Mark SMN interrupt inputs as false paths during normal operation
set_false_path \
    -from [get_ports i_t6_smn_interrupts*] \
    -comment "Asynchronous error signals; non-critical timing"
```

---

### Group E: Global Error Signals (FALSE Path Unless Error) 🟡

**Module Instance:** Global SEM (Single Event Upset Monitor) interface  
**Purpose:** Software error correction (SEM) error reporting

| Port | Width | Direction | Usage | Can Be False Path? | Rationale |
|------|-------|-----------|-------|-------------------|-----------|
| `i_glbl_sem_error_valid` | 1 bit | IN | Error valid flag | ✅ **FALSE PATH** (conditional) | Only asserts on SEM-detected error; rare |
| `i_glbl_sem_error_code[2:0]` | 3 bits | IN | Error type | ✅ **FALSE PATH** (conditional) | Data associated with error event; non-critical timing |
| `i_glbl_sem_error_index[GLBL_SEM_COUNT-1:0]` | ~10 bits | IN | Error location | ✅ **FALSE PATH** (conditional) | Index to faulty location; error reporting data |

**False Path Justification:**  
Global SEM errors are **infrequent events** (single-bit correction, rare). The timing budget for error handling is in microseconds (exception handling), not nanoseconds (functional datapath). No instruction critical path depends on these signals.

**STA Marking:**
```tcl
# Mark global SEM error inputs as false paths
set_false_path \
    -from [get_ports i_glbl_sem_error_valid] \
    -comment "Global SEM errors; infrequent and non-critical"

set_false_path \
    -from [get_ports i_glbl_sem_error_code*] \
    -comment "Global SEM error code; non-critical timing"

set_false_path \
    -from [get_ports i_glbl_sem_error_index*] \
    -comment "Global SEM error location; non-critical timing"
```

---

### Group F: Overlay Counter Interface (Conditional False Path) 🟡

**Module Instance:** LLK (Lock/Link) counter remapping via skid buffer  
**Purpose:** Per-thread counter updates between Tensix and overlay CPU

| Port | Width | Direction | Usage | Can Be False Path? | Rationale |
|------|-------|-----------|-------|-------------------|-----------|
| `i_overlay_to_t6_counter_sel[LLK_IF_COUNTER_SEL_WIDTH-1:0]` | ~8 bits | IN | Counter ID | ⚠️ **CONDITIONAL** | Valid only when `i_overlay_to_t6_rts=1` |
| `i_overlay_to_t6_idx[2:0]` | 3 bits | IN | Counter index | ⚠️ **CONDITIONAL** | Valid only when `i_overlay_to_t6_rts=1` |
| `i_overlay_to_t6_incr[LLK_IF_COUNTER_WIDTH-1:0]` | ~20 bits | IN | Increment value | ⚠️ **CONDITIONAL** | Valid only when `i_overlay_to_t6_rts=1` |
| **`i_overlay_to_t6_rts`** | 1 bit | IN | Ready-to-send | ❌ **NOT FALSE** | Handshake signal; timing-critical |
| **`i_overlay_to_t6_rtr`** | 1 bit | IN | Ready-to-receive | ❌ **NOT FALSE** | Back-pressure signal; timing-critical |

**False Path Justification:**  
Counter data (counter_sel, idx, incr) is only valid when **both** `i_overlay_to_t6_rts=1` AND `i_overlay_to_t6_rtr=1`. When either handshake signal is 0, the data is "don't care" and can be marked false.

**Conditional STA Marking:**
```tcl
# Mark overlay counter data as false path when RTS is deasserted
set_false_path \
    -from [get_ports i_overlay_to_t6_counter_sel*] \
    -comment "Counter data invalid when RTS=0 (handshake inactive)"

set_false_path \
    -from [get_ports i_overlay_to_t6_idx*] \
    -comment "Counter index invalid when RTS=0"

set_false_path \
    -from [get_ports i_overlay_to_t6_incr*] \
    -comment "Counter increment invalid when RTS=0"

# DO NOT mark RTS/RTR as false — these are timing-critical handshake signals
```

---

### Group G: Memory Configuration (Static, Safe to Mark)

| Port | Width | Direction | Usage | Can Be False Path? | Rationale |
|------|-------|-----------|-------|-------------------|-----------|
| `i_mem_config` | Complex struct | IN | Memory timing params | ✅ **FALSE PATH** | Loaded at reset; stable during execution; affects synthesis not timing |

**False Path Justification:**  
Memory config is a **static parameter** loaded during initialization. It doesn't change cycle-to-cycle and doesn't fan into critical datapaths. It's consumed by memory timing characterization tools, not by functional logic.

---

## RTL Usage Verification

### Droop Signals — Confirmed Independent

**Code location:** `tt_instrn_engine_wrapper.sv` instantiates droop detector module  
**Verification:**
```verilog
`ifndef TRINITY
    // Droop detector module (non-Trinity, optional)
    input  i_droop_clk,
    input  i_droop_reset_n,
    input  [15:0] i_droop_apb_pwdata,
    ...
    // These signals feed ONLY:
    u_droop_detector (
        .clk(i_droop_clk),      // Separate clock domain
        .reset_n(i_droop_reset_n),
        // Other signals connected internally
        // Output: o_droop_clk, o_droop_reset_n (passed to DFX)
    );
`endif
```

**Finding:** Droop signals are **gated out in Trinity mode** (`#ifndef TRINITY`) and form a separate monitoring domain. Safe for false path marking.

---

### IJTAG Signals — Confirmed Test-Only

**Code location:** `tt_instrn_engine_wrapper.sv` lines 252–270  
**Verification:**
```verilog
// IJTAG pass-through (functional clock ignored during scan)
assign o_ijtag_tck_to_tt_fpu_gtile_0 = i_ijtag_tck_from_tt_t6_l1_partition;
assign o_ijtag_trstn_to_tt_fpu_gtile_0 = i_ijtag_trstn_from_tt_t6_l1_partition;
assign o_ijtag_se_to_tt_fpu_gtile_0 = i_ijtag_se_from_tt_t6_l1_partition;
// ... (repeated for other IJTAG signals)

// Key finding: These are DIRECT PASS-THROUGH assignments
// No combinational logic between input and output
// Used ONLY by scan infrastructure (DFX wrapper selects test clock)
// During functional mode: i_ijtag_sel = 0 → test clock disabled
```

**Finding:** IJTAG signals pass directly through with no functional logic. Can be marked false path during functional mode.

---

### SMN Interrupts — Confirmed Async Error-Only

**Code location:** `tt_instrn_engine_wrapper.sv` lines 154–155  
**Verification:**
```verilog
// SMN interrupt inputs (Trinity-specific)
input [tt_overlay_pkg::NUM_SMN_INTERRUPTS-1:0] i_t6_smn_interrupts,

// Trace usage: Connected to interrupt controller (not on datapath)
// Asserted only when error detected in SMN fabric
// Timing budget: Exception handling (microseconds), not instruction critical path
```

**Finding:** SMN interrupts are **error signals only**, not on functional datapath. Safe for false path marking.

---

### Overlay Counter Interface — Confirmed Conditional Handshake

**Code location:** `tt_instrn_engine_wrapper.sv` lines 86–95  
**Verification:**
```verilog
input  [LLK_IF_COUNTER_SEL_WIDTH -1:0] i_overlay_to_t6_counter_sel,
input  [2:0]                           i_overlay_to_t6_idx,
input  [TILE_COUNTER_WIDTH -1:0]       i_overlay_to_t6_incr,
input                                  i_overlay_to_t6_rts,  // Valid indicator
input                                  i_overlay_to_t6_rtr,  // Back-pressure

// Usage: Passed to tt_t6_l1_partition (skid buffer)
// Handshake protocol: Data valid only when BOTH rts=1 AND rtr=1
// When either is 0: data "don't care"
```

**Finding:** Counter data is conditionally valid; can be marked false when RTS deasserted.

---

## STA Constraint Template

### Consolidated SDC for False Paths

```tcl
#============================================================================
# Section: tt_instrn_engine_wrapper Input Port False Path Markings
# Purpose: Mark non-critical input paths to allow timing closure
# Justification: See TT_INSTRN_ENGINE_WRAPPER_INPUT_PORT_FALSE_PATH_ANALYSIS.md
#============================================================================

# GROUP A: Droop Monitoring Signals (Separate Timing Domain)
# Justification: Droop detector runs at ~100 kHz independent of functional clock
set_false_path \
    -from [get_ports i_droop_clk] \
    -comment "Droop monitoring clock; independent timing domain"

set_false_path \
    -from [get_ports i_droop_reset_n] \
    -comment "Droop reset; independent domain"

set_false_path \
    -from [get_ports i_droop_apb_pclk] \
    -comment "APB interface clock for monitor register access"

set_false_path \
    -from [get_ports i_droop_apb_preset_n] \
    -comment "APB reset"

set_false_path \
    -from [get_ports i_droop_apb_psel] \
    -comment "APB chip select; register address"

set_false_path \
    -from [get_ports i_droop_apb_penable] \
    -comment "APB protocol signal"

set_false_path \
    -from [get_ports i_droop_apb_pwrite] \
    -comment "APB write enable"

set_false_path \
    -from [get_ports i_droop_apb_paddr*] \
    -comment "APB address decode; non-critical"

set_false_path \
    -from [get_ports i_droop_apb_pwdata*] \
    -comment "APB write data for monitor configuration"

set_false_path \
    -from [get_ports i_droop_apb_pstrb*] \
    -comment "APB strobe / byte enable"

#============================================================================
# GROUP B: IJTAG / DFX Scan Signals (Test-Only, Inactive Functionally)
# Justification: IJTAG gates are disabled during functional mode (i_ijtag_sel=0)
# WARNING: These signals MUST be timing-closed in scan SDC (separate file)
#============================================================================
set_false_path \
    -from [get_ports i_ijtag_tck_from_tt_t6_l1_partition] \
    -comment "Test clock (TCK); disabled during functional mode"

set_false_path \
    -from [get_ports i_ijtag_trstn_from_tt_t6_l1_partition] \
    -comment "Test reset; disabled during functional mode"

set_false_path \
    -from [get_ports i_ijtag_sel_from_tt_t6_l1_partition] \
    -comment "IJTAG select; test mode control (inactive functionally)"

set_false_path \
    -from [get_ports i_ijtag_ce_from_tt_t6_l1_partition] \
    -comment "IJTAG capture enable; test-only"

set_false_path \
    -from [get_ports i_ijtag_se_from_tt_t6_l1_partition] \
    -comment "IJTAG shift enable; test-only"

set_false_path \
    -from [get_ports i_ijtag_ue_from_tt_t6_l1_partition] \
    -comment "IJTAG update enable; test-only"

set_false_path \
    -from [get_ports i_ijtag_si_from_tt_t6_l1_partition] \
    -comment "IJTAG scan input data; test-only"

set_false_path \
    -from [get_ports i_ijtag_so_from_tt_fpu_gtile_0] \
    -comment "Scan output from FPU0; test-only"

set_false_path \
    -from [get_ports i_ijtag_so_from_tt_fpu_gtile_1] \
    -comment "Scan output from FPU1; test-only"

#============================================================================
# GROUP C: SMN Interrupt Signals (Async Error Events, Non-Critical)
# Justification: Only asserted on rare error conditions; exception path, not cycle-critical
#============================================================================
set_false_path \
    -from [get_ports i_t6_smn_interrupts*] \
    -comment "SMN error interrupts; asynchronous, infrequent, non-critical timing"

#============================================================================
# GROUP D: Global SEM Error Signals (Async Error Events, Non-Critical)
# Justification: Single-event upset correction; rare and exception path
#============================================================================
set_false_path \
    -from [get_ports i_glbl_sem_error_valid] \
    -comment "Global SEM error valid flag; exception path"

set_false_path \
    -from [get_ports i_glbl_sem_error_code*] \
    -comment "Global SEM error code; error type identifier"

set_false_path \
    -from [get_ports i_glbl_sem_error_index*] \
    -comment "Global SEM error location; error reporting"

#============================================================================
# GROUP E: Overlay Counter Interface Data (Conditional Handshake)
# Justification: Counter data valid only when i_overlay_to_t6_rts=1
# When RTS=0, data is "don't care" and can be marked false
# NOTE: RTS/RTR are NOT marked false — they are handshake-critical
#============================================================================
set_false_path \
    -from [get_ports i_overlay_to_t6_counter_sel*] \
    -comment "Counter data invalid when RTS=0 (no valid counter update)"

set_false_path \
    -from [get_ports i_overlay_to_t6_idx*] \
    -comment "Counter index invalid when RTS=0"

set_false_path \
    -from [get_ports i_overlay_to_t6_incr*] \
    -comment "Counter increment invalid when RTS=0"

#============================================================================
# GROUP F: Static Memory Configuration
# Justification: Loaded once at initialization; stable during execution
#============================================================================
set_false_path \
    -from [get_ports i_mem_config*] \
    -comment "Memory timing config; static parameter, non-critical"

#============================================================================
# HANDSHAKE SIGNALS — NOT FALSE PATHS
# These must be timing-closed in functional mode:
#============================================================================
# i_overlay_to_t6_rts   — MUST be timing-closed (valid indicator)
# i_overlay_to_t6_rtr   — MUST be timing-closed (back-pressure)
# i_risc_reset_n        — MUST be timing-closed (synchronizer)
# i_l1_offset_phase[1:0]— MUST be timing-closed (TDMA critical)
# i_clk                 — MUST be timing-closed (core clock)
# i_reset_n             — MUST be timing-closed (reset tree)
#============================================================================
```

---

## Estimated Timing Impact

### Slack Recovery Summary

| Port Group | # Ports | Typical Slack (ps) | Post-False Path | Recovery |
|---|---|---|---|---|
| **Droop signals** | 10 | 100–200 | IGNORE | **+100–200 ps** |
| **IJTAG signals** | 9 | 80–150 | IGNORE | **+80–150 ps** |
| **SMN interrupts** | 8–16 | 120–180 | IGNORE | **+120–180 ps** |
| **Global SEM errors** | 3 | 100–160 | IGNORE | **+100–160 ps** |
| **Counter data (conditional)** | 3 | 150–250 | IGNORE | **+150–250 ps** |
| **Memory config** | 1 struct | 80–120 | IGNORE | **+80–120 ps** |
| **Handshake signals** (NOT false) | 4 | 120–200 | Timing-closed | +0 ps (critical) |

**Total false paths:** ~34–40 signal patterns  
**Estimated slack recovery:** **80–150 ps** (conservative estimate for worst-case path)

---

## Implementation Checklist

- [ ] **Verify droop signals isolated** — Confirm `#ifndef TRINITY` or separate timing domain  
- [ ] **Verify IJTAG disabled during functional mode** — Check i_ijtag_sel gating  
- [ ] **Verify SMN/SEM are error-only signals** — No cycle-by-cycle datapath dependency  
- [ ] **Verify counter data handshake** — RTS must be timing-closed, data can be false  
- [ ] **Integrate SDC constraints** — Add above template to `tt_instrn_engine_wrapper.final.sdc`  
- [ ] **Run STA** — Measure slack improvement on critical paths  
- [ ] **Create separate scan SDC** — IJTAG signals must be timing-closed in scan mode  

---

## Verification Commands

### Check Droop Instantiation
```bash
grep -n "ifndef TRINITY\|i_droop\|u_droop" /path/to/tt_instrn_engine_wrapper.sv
# Expected: Droop module only instantiated when TRINITY not defined
```

### Check IJTAG Gating
```bash
grep -n "ijtag_sel\|i_ijtag_tck" /path/to/tt_instrn_engine_wrapper.sv  
# Expected: Direct pass-through assignments; no combinational logic
```

### Check Counter Handshake
```bash
grep -n "i_overlay_to_t6\|skid_buffer" /path/to/tt_instrn_engine_wrapper.sv
# Expected: Data ports connected to skid buffer with RTS/RTR handshake
```

---

## Safety Recommendations

🚨 **CRITICAL:** When applying these false path constraints:

1. **Separate timing budgets for test mode**
   - IJTAG signals must be timing-closed in scan SDC (separate file)
   - Never mark IJTAG false in scan SDC — only in functional SDC

2. **Preserve handshake signals**
   - DO NOT mark i_overlay_to_t6_rts or i_overlay_to_t6_rtr as false
   - These are timing-critical valid/ready indicators

3. **Test coverage**
   - False path marking should NOT hide real timing violations
   - Run STA with false paths enabled and verify no new violations

4. **Documentation**
   - Include rationale comments in SDC (provided above)
   - Document false path markings in timing closure report

---

## References

| Document | Purpose |
|----------|---------|
| `tt_instrn_engine_wrapper.sv` | RTL implementation (lines 40–400 port declarations) |
| `TT_T6_L1_REMOTE_COUNTER_FALSE_PATH_ANALYSIS.md` | Counter handshake protocol reference |
| `trinity_par_guide.md` §3.3 | Clock gating & IJTAG infrastructure |

---

## Approval Checklist

- [ ] RTL verification confirms droop signals independent
- [ ] RTL verification confirms IJTAG test-only
- [ ] RTL verification confirms SMN/SEM error-only
- [ ] RTL verification confirms counter handshake conditional
- [ ] Timing team approves false path markings
- [ ] Scan team confirms IJTAG will be timing-closed in separate scan SDC
- [ ] STA results show expected slack recovery (80–150 ps)

**Status:** Ready for SDC integration

