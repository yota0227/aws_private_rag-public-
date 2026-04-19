# N1B0 Harvest Reset/Clock Signal Source Verification Guide

**Document:** Harvest Logic Reset and Clock Domain Analysis
**Date:** 2026-04-01
**Issue:** NOC Router harvest logic relies on reset signals that may originate from powered-off L1 hub during tile harvest

---

## Executive Summary

**Critical Risk:** ⚠️ **FOUND**

The NOC router's harvest detection and EDC demultiplexing logic depend on several reset signals that **originate from the powered-off overlay wrapper**. When a Tensix tile is harvested (powered off via ISO_EN), these reset signals become undefined, potentially:
- Disrupting harvest state machine transitions
- Leaving EDC demux select (edc_mux_demux_sel) in an unpredictable state  
- Causing harvest sequence failures or EDC ring instability

---

## 1. Reset Signal Flow Analysis

### 1.1 NOC Router Reset Inputs

**File:** `tt_trin_noc_niu_router_wrap.sv`

```systemverilog
module tt_trin_noc_niu_router_wrap (
    input logic                       i_ai_reset_n,           // Line 106
    ...
    input logic                       i_smn_cold_reset_n,     // Line 157
    ...
);
```

**These are connected from:**

**File:** `tt_overlay_noc_niu_router.sv` (lines 1173, 1231)

```systemverilog
tt_trin_noc_niu_router_wrap tt_trinity_noc_niu_router_inst (
    .i_ai_reset_n                     (i_aiclk_reset_n_noc_ovl),     // Line 1173
    ...
    .i_smn_cold_reset_n               (smn_cold_reset_n_smnclk),    // Line 1231
    ...
);
```

### 1.2 Source of smn_cold_reset_n_smnclk

**File:** `tt_overlay_noc_niu_router.sv` (line 736)

```systemverilog
neo_overlay_wrapper neo_overlay_wrapper (
    ...
    .o_smn_cold_reset_n_smnclk        (smn_cold_reset_n_smnclk),     // ← Generated inside overlay
    ...
);
```

**Problem:** `smn_cold_reset_n_smnclk` is **generated inside `tt_neo_overlay_wrapper`**, which:
- Is part of the powered-off VDDM domain
- Powers down when tile is harvested
- Stops driving the signal → float/undefined

### 1.3 i_aiclk_reset_n_noc_ovl Source

**File:** `tt_overlay_noc_niu_router.sv` (input port, line 66)

```systemverilog
input  logic i_aiclk_reset_n_noc_ovl,
```

**Trace to parent:** This must come from the overlay wrapper or from trinity top-level clock routing structure.

---

## 2. Harvest Logic Dependencies on Reset Signals

### 2.1 EDC Controller (tt_edc1_noc_sec_controller)

**File:** `tt_trin_noc_niu_router_wrap.sv` (lines 799-807)

```systemverilog
tt_edc1_noc_sec_controller edc_noc_sec_controller_inst (
    .i_clk            (i_clk),              // noc_clk from AON clock_reset_ctrl
    .i_reset_n        (i_reset_n),          // noc_clk_reset_n from AON? ⚠️ CHECK
    .ingress_intf     (edc_ingress_intf),
    .egress_intf      (noc_sec_controller_egress_intf),
    .i_sec_status     (edc_status_noc_sec),
    .o_sec_config     (edc_config_noc_sec)  // ← harvest_vec[0:2] output
);
```

**Reset Input Status:**
- ✅ Clocked by `i_clk` (noc_clk from AON clock_reset_ctrl)
- ⚠️ **BUT:** `i_reset_n` source unclear — must verify it's from **AON** clock_reset_ctrl, NOT from overlay

### 2.2 Harvest State Vector (edc_config_noc_sec.harvest_vec[2:0])

**File:** `tt_trin_noc_niu_router_wrap.sv` (lines 889-891)

```systemverilog
assign o_overlay_harvested   = edc_config_noc_sec.harvest_vec[0];
assign noc_harvested         = edc_config_noc_sec.harvest_vec[1];
assign o_tensix_harvested    = edc_config_noc_sec.harvest_vec[2];
```

These harvest outputs **depend on edc_config_noc_sec**, which depends on:
1. `i_reset_n` to the EDC controller
2. `i_clk` (noc_clk) to the EDC controller
3. **Both must be stable and driven from AON during harvest**

### 2.3 EDC Demux Control (edc_mux_demux_sel)

**File:** `tt_trin_noc_niu_router_wrap.sv` (lines 773, 893)

```systemverilog
tt_edc1_serial_bus_demux edc_demuxing_when_harvested (
    .i_demux_sel(edc_mux_demux_sel),   // ← depends on reset state above
    ...
);

assign edc_mux_demux_sel = edc_config_noc_sec.edc_mux_demux_sel;
```

**Dependency chain:**
```
i_reset_n (reset of EDC controller)
    ↓
edc_config_noc_sec (output state)
    ↓
edc_mux_demux_sel (combinational assign)
    ↓
edc_demux routing decision
```

If `i_reset_n` is NOT held stable from AON, the demux behavior becomes unpredictable during harvest.

---

## 3. Risk Analysis: Reset Sources

### 3.1 Reset Input to tt_edc1_noc_sec_controller

| Signal | Source | Power Domain | Status | Risk |
|--------|--------|--------------|--------|------|
| `i_clk` | noc_clk from AON clock_reset_ctrl | VDDN (AON) | ✅ Safe | None |
| `i_reset_n` | **? (needs verification)** | ? | ⚠️ UNKNOWN | **CRITICAL** |
| `edc_ingress_intf` (from ring) | EDC ring (AON repeaters) | VDDN (AON) | ✅ Safe | None |

**Critical Question:** Where does `i_reset_n` come from in `tt_trin_noc_niu_router_wrap.sv`?

**File:** `tt_trin_noc_niu_router_wrap.sv` (module definition)

```systemverilog
module tt_trin_noc_niu_router_wrap (
    input logic                       i_reset_n,              // ← Source?
    input logic                       i_clk,                  // noc_clk (AON)
    ...
);
```

This input must be traced through:
1. `tt_overlay_noc_niu_router` → instantiation of tt_trin_noc_niu_router_wrap
2. `tt_overlay_noc_niu_router` → input port definition
3. Trinity top-level → clock_routing_in/out structure

### 3.2 smn_cold_reset_n_smnclk Source

**File:** `tt_overlay_noc_niu_router.sv` (line 736)

```systemverilog
.o_smn_cold_reset_n_smnclk(smn_cold_reset_n_smnclk),
```

**Source:** Generated inside `tt_neo_overlay_wrapper` (powered-off overlay)

**Power Domain:** VDDM (same as overlay core, powers off during harvest)

**Risk:** ❌ **CRITICAL** — This signal loses its driver when overlay powers off

---

## 4. Harvest Sequence Timing Problem

### 4.1 Intended Harvest Sequence

```
Time 0:   Boot complete, all tiles powered (VDDM on)
Time T1:  Software requests harvest of tile (X, Y)
Time T2:  Hardware sets ISO_EN[index] = 1
          ↓
          ISO cells clamp outputs of powered-off tile to 0
          ↓
Time T3:  After ISO stabilizes, turn off VDDM supply (or tri-state VDDM)
```

### 4.2 Current Problem

**Scenario:** Harvesting tile at (X=0, Y=2)

```
Time T2:  ISO_EN[0+4*2] = ISO_EN[8] = 1
          ↓
          EDC serial bus to edc_muxing_when_harvested gets ISO-clamped (✅ OK)
          
          BUT: smn_cold_reset_n_smnclk driver (in powered-off overlay) 
               becomes weak/undefined
          ↓
Time T3:  VDDM powers off
          ↓
          smn_cold_reset_n_smnclk floats completely
          ↓
          EDC controller reset input becomes undefined
          ↓
          edc_config_noc_sec output becomes metastable
          ↓
          edc_mux_demux_sel routing unpredictable → EDC ring corruption
```

---

## 5. Verification Checklist

### Part 1: Reset Input Sources

**Action:** Trace each reset input to tt_trin_noc_niu_router_wrap

| Reset Signal | Current Source | Expected Source | Verification Status |
|--------------|-----------------|-----------------|---------------------|
| `i_reset_n` | ? | `noc_clk_reset_n` from AON clock_reset_ctrl | ❌ **NOT VERIFIED** |
| `i_ai_reset_n` | ? (line 106) | Per-column ai_reset_n or feedthrough from AON | ❌ **NOT VERIFIED** |
| `i_smn_cold_reset_n` | neo_overlay_wrapper (line 736) | **Should be from AON** | ❌ **FAIL — Powered-off source** |

### Part 2: Harvest-Critical Signals

| Signal | Clock Domain | Reset Source | Status | Issue |
|--------|--------------|--------------|--------|-------|
| `edc_config_noc_sec` (harvest_vec) | noc_clk (AON) | ? | ⚠️ Check | Reset source unclear |
| `edc_mux_demux_sel` | combinational | depends on edc_config_noc_sec | ⚠️ Check | Float risk |
| `smn_cold_reset_n` (used by demux) | from overlay | VDDM (powered-off) | ❌ FAIL | **Not AON** |

### Part 3: Clock Feedthrough

| Clock Signal | Source | Domain | Status |
|--------------|--------|--------|--------|
| `i_clk` to edc_controller | noc_clk from AON | VDDN | ✅ OK |
| `i_nocclk` feedthrough | AON clock_reset_ctrl | VDDN | ✅ OK |
| `ai_clk` feedthrough | Per-column? | ⚠️ Check | **Verify AON origin** |

---

## 6. Recommended Fixes

### Fix 1: Relocate smn_cold_reset_n Generation to AON

**Current:** Generated in powered-off overlay wrapper
**Target:** Generate in AON clock_reset_ctrl module

```systemverilog
// Inside clock_reset_ctrl (always-on, VDDN)
assign o_smn_cold_reset_n_aon = i_smn_cold_reset_n;  // Register or latch in AON

// Inside tt_overlay_noc_niu_router
tt_trin_noc_niu_router_wrap inst (
    .i_smn_cold_reset_n(i_smn_cold_reset_n_from_aon),  // From AON, not overlay
    ...
);
```

**Rationale:**
- SMN (Security Monitor Network) is always-on and must have a stable reset during harvest
- Reset signal must originate from VDDN AON domain, not from powered-off VDDM

### Fix 2: Add ISO Cell on smn_cold_reset_n Input

If relocation is not feasible, add an isolation cell to clamp the signal during harvest:

```systemverilog
// Inside tt_trin_noc_niu_router_wrap or parent
logic smn_cold_reset_n_iso;
assign smn_cold_reset_n_iso = i_smn_cold_reset_n & ~ISO_EN[x + 4*y];

tt_edc1_noc_sec_controller inst (
    .i_reset_n(smn_cold_reset_n_iso),  // Clamped to 0 when harvested
    ...
);
```

### Fix 3: Verify i_reset_n Input Path

**Action:** Trace `i_reset_n` to tt_trin_noc_niu_router_wrap through the call stack:

```
trinity.sv 
  ↓ (clock_routing_in/out)
tt_tensix_with_l1.sv
  ↓ (instantiation of tt_overlay_noc_niu_router)
tt_overlay_noc_niu_router.sv
  ↓ (instantiation of tt_trin_noc_niu_router_wrap)
tt_trin_noc_niu_router_wrap.sv
  .i_reset_n(?) ← VERIFY THIS SOURCE
```

**Verify:** 
- Source must be `noc_clk_reset_n` from AON (e.g., from trinity top clock routing)
- NOT from powered-off overlay
- Must be **static/always-on** throughout harvest sequence

### Fix 4: Add AON Register for Harvest Status

Create an AON-domain register that mirrors the harvest_vec output:

```systemverilog
// Inside clock_reset_ctrl (AON)
logic [2:0] harvest_vec_aon;
always_ff @(posedge i_noc_clk)
    if (!i_noc_clk_reset_n)
        harvest_vec_aon <= 3'b0;
    else
        harvest_vec_aon <= edc_controller_harvest_vec;  // From EDC ring decode

assign o_overlay_harvested = harvest_vec_aon[0];
assign o_noc_harvested     = harvest_vec_aon[1];
assign o_tensix_harvested  = harvest_vec_aon[2];
```

This creates a **second copy of harvest status in AON** that cannot float.

---

## 7. Testing & Verification Plan

### Test 1: Reset Stability During Harvest

**Objective:** Verify all reset signals remain stable when tile is harvested

```tcl
# In simulation, at time T when harvest is initiated:
at_time T:
    set ISO_EN[tile_index] = 1
    # Monitor reset signals
    wait_for smn_cold_reset_n stable for 10 cycles  # ← Should NOT float
    wait_for edc_config_noc_sec stable for 10 cycles # ← Should NOT change
    verify edc_mux_demux_sel == expected_value
    # If any signal becomes 'x' or 'z', test FAILS
```

### Test 2: EDC Ring Stability with Harvested Tile

**Objective:** Verify EDC ring continues operating with N-1 active nodes

```tcl
# Inject harvest command into EDC ring
edc_send_harvest_command(tile_x, tile_y, harvest=1)

# Monitor EDC ring
check_edc_ring_health()  # All remaining nodes in READY state
verify o_overlay_harvested == 1
verify o_tensix_harvested == 1

# Send packets through EDC ring (avoid harvested node)
edc_send_test_packet(source=tile_1, dest=tile_3)  # Skip harvested tile
verify packet_received correctly
```

### Test 3: Clock Feedthrough Isolation

**Objective:** Verify clocks are isolated when harvest is active

```tcl
# Apply harvest
set ISO_EN[tile_index] = 1

# Verify clock feedthrough behavior
check ai_clk_feedthrough status  # Should be isolated or guarded
check noc_clk_feedthrough status # Should be isolated or guarded
check dm_clk_feedthrough status  # Should be isolated or guarded
```

---

## 8. Sign-Off Checklist

- [ ] **i_reset_n source to tt_trin_noc_niu_router_wrap verified to be from AON**
- [ ] **smn_cold_reset_n relocated to AON clock_reset_ctrl (or ISO cell added)**
- [ ] **UPF power domain assignments confirmed: smn_cold_reset_n in VDDN domain**
- [ ] **Reset sequencing verified: reset active during harvest, stable after harvest**
- [ ] **EDC controller reset path verified: no powered-off domain dependencies**
- [ ] **Harvest state machine reset verified to work with all reset inputs**
- [ ] **Simulation test: harvest of single tile, verify EDC ring stability**
- [ ] **Simulation test: multi-tile harvest, verify no cross-tile reset corruption**
- [ ] **RTL lint check: no powered-off domain signals driving harvest logic**
- [ ] **Documentation updated: reset hierarchy includes AON requirements for harvest**

---

## Conclusion

**Current Status:** ⚠️ **REQUIRES FIXES**

The NOC router's harvest and EDC logic depend on reset signals that **may not be stable or available from AON domains** during tile harvest. Specifically:

1. **smn_cold_reset_n** is generated in powered-off overlay — must be relocated to AON
2. **i_reset_n** source to EDC controller — must be verified to come from AON clock_reset_ctrl
3. **harvest_vec** decoding — depends on stable reset inputs

**Recommended Action:** Implement Fix 1 (relocate smn_cold_reset_n) + Fix 3 (verify i_reset_n source) before tape-out.

---

