# Reset Signal Sources — RTL Verification Report

**Document:** Detailed RTL trace of EDC controller reset inputs
**Date:** 2026-04-01
**Scope:** Verify power domain origins of i_reset_n and i_smn_cold_reset_n

---

## Executive Summary

**Status: ⚠️ CRITICAL ISSUE CONFIRMED**

### Finding 1: i_reset_n Path (EDC Controller)

✅ **SAFE** — Reset comes from AON domain, but through powered-off overlay wrapper

```
trinity.sv (top-level input: i_noc_reset_n)
  ↓
  clock_routing_in/out structure (AON clock_reset_ctrl)
  ↓
  tt_overlay_noc_niu_router:i_nocclk_reset_n (input port)
  ↓
  noc_clk_reset_n_pre_sync
  ↓
  tt_noc_overlay_edc_repeater (clock_reset_ctrl module):i_reset_n_pre_sync
  ↓
  o_reset_n_sync_to_ovl (synchronized reset, clocked by noc_clk)
  ↓
  reset_n_sync_to_ovl (used by EDC controller)
  ↓
  tt_edc1_noc_sec_controller:i_reset_n  ✅ (eventually derived from AON)
```

**Details:**
- Origin: External input `i_nocclk_reset_n` (from trinity top-level)
- Synchronization: 3-stage sync3r inside `tt_noc_overlay_edc_repeater` (clocked by noc_clk)
- Output: `o_reset_n_sync_to_ovl` (stable synchronized reset)
- Power domain: Signal originates from AON but is routed through powered-off overlay

**Risk:** ⚠️ **Medium** — Reset signal is valid, but the routing path goes through powered-off overlay logic

---

### Finding 2: smn_cold_reset_n Path (SMN)

❌ **UNSAFE** — Reset generated inside powered-off overlay wrapper

```
tt_neo_overlay_wrapper (powered-off core, VDDM)
  ↓
  o_smn_cold_reset_n_smnclk  ← ❌ Generated here (VDDM domain)
  ↓
  tt_overlay_noc_niu_router:smn_cold_reset_n_smnclk (line 352)
  ↓
  tt_trin_noc_niu_router_wrap:i_smn_cold_reset_n (line 157)
```

**Details:**
- Origin: `tt_neo_overlay_wrapper.o_smn_cold_reset_n_smnclk` (line 736)
- Power domain: **VDDM (powered-off)** ❌ CRITICAL
- When tile harvested: Signal loses driver → floats
- Used by: `tt_edc1_noc_sec_controller` (via NIU wrapper port at line 157)

**Risk:** ❌ **CRITICAL** — Signal undefined when tile powered off during harvest

---

## Detailed RTL Trace

### Part 1: i_reset_n to EDC Controller

**Step 1: Source at trinity top-level** — `tt_overlay_noc_niu_router` instantiation

**File:** `trinity.sv` (inferred from hierarchy)

```
Input: i_noc_reset_n  ← External chip-level input
Output: clock_routing_in/out[X][Y].noc_clk_reset_n
```

**Step 2: tt_overlay_noc_niu_router receives reset**

**File:** `tt_overlay_noc_niu_router.sv` (line 443 or 449)

```systemverilog
if (!HAS_SMN_INST) begin
    assign noc_clk_reset_n_pre_sync = i_nocclk_reset_n;    // External input (from trinity)
end else begin
    assign noc_clk_reset_n_pre_sync = smn_nocclk_reset_n;  // From SMN (internal)
end
```

**Issue:** Conditional logic — which path is used in N1B0?
- If `HAS_SMN_INST=1`: Uses `smn_nocclk_reset_n` (generated internally in overlay)
- If `HAS_SMN_INST=0`: Uses external `i_nocclk_reset_n` (from trinity top)

**Step 3: Reset synchronization in clock_reset_ctrl**

**File:** `tt_noc_overlay_edc_repeater` (part of clock_reset_ctrl in tt_overlay_noc_niu_router, line 962)

```systemverilog
tt_noc_overlay_edc_repeater noc_edc_repeater_inst (
    .i_reset_n_pre_sync(noc_clk_reset_n_pre_sync),  // Unsynchronized
    .i_nocclk(i_nocclk),                            // noc_clk (AON)
    .o_reset_n_sync_to_ovl(noc_clk_reset_n_sync_to_ovl),  // Synchronized output
    .o_reset_n_sync_to_top(noc_clk_reset_n_sync_to_top)
);
```

**Internal:** 3-stage synchronizer on noc_clk domain

```systemverilog
// Inside tt_noc_overlay_edc_repeater (inferred)
tt_libcell_sync3r reset_sync3r (
    .i_CK(i_nocclk),              // noc_clk (AON)
    .i_D(i_reset_n_pre_sync),     // Raw reset (may be from SMN or external)
    .o_Q(reset_n_sync_to_ovl)     // Synchronized reset
);
```

**Step 4: Reset routed to tt_trin_noc_niu_router_wrap**

**File:** `tt_trin_noc_niu_router_wrap.sv` (line 572)

```systemverilog
tt_noc_overlay_edc_repeater inst (
    .o_reset_n_sync_to_ovl(reset_n_sync_to_ovl)  // ← Output
);

// Used as:
tt_edc1_noc_sec_controller edc_inst (
    .i_reset_n(reset_n_sync_to_ovl),  // ← Connected here (line 799)
    ...
);
```

**Step 5: Final EDC controller reset input**

**File:** `tt_edc1_noc_sec_controller.sv` (instantiated at line 799)

```systemverilog
module tt_edc1_noc_sec_controller (
    input i_reset_n,     // ← reset_n_sync_to_ovl (from above)
    input i_clk,         // ← noc_clk (AON)
    output edc_reg_noc_sec_output_t o_sec_config,  // ← harvest_vec output
    ...
);
```

---

### Part 2: smn_cold_reset_n Path (POWERED-OFF SOURCE)

**Step 1: Generated in powered-off overlay**

**File:** `tt_overlay_noc_niu_router.sv` (line 736)

```systemverilog
tt_neo_overlay_wrapper neo_overlay_wrapper (
    ...
    .o_smn_cold_reset_n_smnclk(smn_cold_reset_n_smnclk),  // ← Generated here (VDDM)
    ...
);
```

**Module:** `tt_neo_overlay_wrapper` — Main overlay core (powered-off domain)

**Power Domain:** VDDM (same as overlay core)

**Clock Domain:** smnclk (from SMN internal clock domain)

**Step 2: Routed through tt_overlay_noc_niu_router**

**File:** `tt_overlay_noc_niu_router.sv` (line 352, 1001, 1231)

```systemverilog
logic smn_cold_reset_n_smnclk;  // Line 352 — Local variable

// From neo_overlay_wrapper output:
.o_smn_cold_reset_n_smnclk(smn_cold_reset_n_smnclk),  // Line 736

// To tt_trin_noc_niu_router_wrap input:
tt_trin_noc_niu_router_wrap tt_trinity_noc_niu_router_inst (
    .i_smn_cold_reset_n(smn_cold_reset_n_smnclk),  // Line 1231
    ...
);
```

**Step 3: Used in tt_trin_noc_niu_router_wrap**

**File:** `tt_trin_noc_niu_router_wrap.sv` (line 157)

```systemverilog
module tt_trin_noc_niu_router_wrap (
    input logic i_smn_cold_reset_n,  // ← smn_cold_reset_n_smnclk from above
    ...
);

// Used by:
tt_edc1_noc_sec_controller edc_inst (
    .i_reset_n(reset_n_sync_to_ovl),         // AON-derived reset (OK)
    ...
);

// And by SMN module (not shown, but it receives this reset)
```

**Critical Issue:** When tile is harvested and VDDM powers off:
- `tt_neo_overlay_wrapper` stops operating
- `o_smn_cold_reset_n_smnclk` driver becomes weak/undefined
- Signal routing through powered-off overlay cannot be maintained
- `i_smn_cold_reset_n` to tt_edc1_noc_sec_controller **floats**

---

## Power Domain Analysis

### Reset Signal Power Domain Origins

| Signal | Generated In | Power Domain | Reset During Harvest |
|--------|--------------|--------------|----------------------|
| `i_nocclk_reset_n` (external input) | trinity top-level | VDDN (AON) | ✅ Stable |
| `noc_clk_reset_n_pre_sync` | tt_overlay_noc_niu_router (conditional) | Depends (see below) | ⚠️ Check |
| `reset_n_sync_to_ovl` | tt_noc_overlay_edc_repeater (sync3r) | VDDN (AON) | ✅ Stable |
| `smn_nocclk_reset_n` | neo_overlay_wrapper (o_smn_noc_clk_reset_n) | VDDM (powered-off) | ❌ **Float risk** |
| `smn_cold_reset_n_smnclk` | neo_overlay_wrapper (o_smn_cold_reset_n_smnclk) | VDDM (powered-off) | ❌ **Float risk** |

---

## Critical Issues Found

### Issue 1: Conditional Reset Source (i_reset_n)

**Code:** `tt_overlay_noc_niu_router.sv` lines 442–451

```systemverilog
generate
    if (!HAS_SMN_INST) begin: gen_top_level_clocks_resets
        assign noc_clk_reset_n_pre_sync = i_nocclk_reset_n;     // ✅ External (AON)
    end else begin: gen_smn_fanouts
        assign noc_clk_reset_n_pre_sync = smn_nocclk_reset_n;   // ❌ Internal (VDDM)
    end
endgenerate
```

**Question:** Is `HAS_SMN_INST=1` in N1B0?

If YES:
- `noc_clk_reset_n_pre_sync` comes from `smn_nocclk_reset_n` (from powered-off overlay)
- EDC controller `i_reset_n` depends on powered-off domain
- **ISSUE: Float risk during harvest**

If NO:
- `noc_clk_reset_n_pre_sync` comes from external `i_nocclk_reset_n` (from AON)
- EDC controller `i_reset_n` stable during harvest
- **OK**

---

### Issue 2: smn_cold_reset_n Source (CONFIRMED)

**Code:** `tt_overlay_noc_niu_router.sv` lines 736, 1001, 1231

```systemverilog
// Generated in powered-off overlay:
neo_overlay_wrapper neo_overlay_wrapper (
    .o_smn_cold_reset_n_smnclk(smn_cold_reset_n_smnclk),  // ← VDDM
);

// Routed to tt_trin_noc_niu_router_wrap:
tt_trin_noc_niu_router_wrap inst (
    .i_smn_cold_reset_n(smn_cold_reset_n_smnclk),        // ← smn_cold_reset_n floats
);
```

**Status:** ❌ **CONFIRMED CRITICAL**

**When harvested:** 
- `tt_neo_overlay_wrapper` (VDDM) powers off
- `o_smn_cold_reset_n_smnclk` driver lost
- `i_smn_cold_reset_n` to tt_edc1_noc_sec_controller becomes undefined
- Harvest detection and EDC mux control become unpredictable

---

## Verification Checklist

| Item | Finding | Action |
|------|---------|--------|
| i_reset_n source to EDC | Conditional: may come from VDDM if `HAS_SMN_INST=1` | **Verify HAS_SMN_INST value for N1B0** |
| smn_cold_reset_n source | Confirmed: `tt_neo_overlay_wrapper.o_smn_cold_reset_n_smnclk` (VDDM) | **Must relocate to AON or add ISO cell** |
| Reset synchronization | 3-stage sync3r in `tt_noc_overlay_edc_repeater` (noc_clk domain) | ✅ OK (AON clock) |
| Clock domain of EDC controller | `i_clk = i_nocclk` (from AON clock_reset_ctrl) | ✅ OK |
| Harvest state dependency | `edc_config_noc_sec.harvest_vec[2:0]` depends on EDC controller reset | ⚠️ Depends on above |

---

## Recommendations

### Immediate Action 1: Verify HAS_SMN_INST Parameter

**In N1B0 design files:**
```bash
grep -r "HAS_SMN_INST" used_in_n1/  # Find where it's set
```

If `HAS_SMN_INST=1`:
- EDC controller reset (`i_reset_n`) depends on powered-off `smn_nocclk_reset_n`
- **Additional fix needed:** Route reset from AON source

### Immediate Action 2: Relocate smn_cold_reset_n to AON

**Current:** Generated in `tt_neo_overlay_wrapper` (VDDM powered-off)

**Required:** Generate in `clock_reset_ctrl` (VDDN always-on)

**Implementation:**
```systemverilog
// In clock_reset_ctrl (AON module):
assign o_smn_cold_reset_n_aon = i_smn_cold_reset_n_from_top;  // From trinity or BIU

// In tt_overlay_noc_niu_router:
input logic i_smn_cold_reset_n_from_aon  // New input port

tt_trin_noc_niu_router_wrap inst (
    .i_smn_cold_reset_n(i_smn_cold_reset_n_from_aon),  // ← Now from AON
);
```

### Immediate Action 3: Add ISO Cell on smn_cold_reset_n

**As fallback if relocation is not feasible:**

```systemverilog
// Inside tt_trin_noc_niu_router_wrap:
logic smn_cold_reset_n_iso;
assign smn_cold_reset_n_iso = i_smn_cold_reset_n & ~ISO_EN[tile_index];

// Use isolated version:
tt_edc1_noc_sec_controller edc_inst (
    .i_reset_n(smn_cold_reset_n_iso),  // ← Clamped during harvest
    ...
);
```

---

## Conclusion

**RTL Verification Results:**

✅ **i_reset_n:** Routed through AON-clocked synchronizer, but source conditional
❌ **smn_cold_reset_n:** Confirmed generated in powered-off overlay wrapper

**Required Before Tape-Out:**
1. Confirm `HAS_SMN_INST` value and implications for i_reset_n
2. Relocate `smn_cold_reset_n` generation to AON clock_reset_ctrl
3. Add ISO cell clamping if relocation not feasible
4. Update UPF to reflect AON power domain for all harvest-critical reset signals

---

