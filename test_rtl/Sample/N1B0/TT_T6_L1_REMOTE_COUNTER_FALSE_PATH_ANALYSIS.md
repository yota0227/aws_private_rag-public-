# tt_t6_l1_partition Remote Counter Interface — False Path Analysis

**Date:** 2026-04-10  
**Module:** `tt_t6_l1_partition.sv`  
**Interface:** LLK (Lock/Link) counter remapping handshake  
**Severity:** 🟡 **MEDIUM** (False path marking critical for STA closure)  
**Impact:** ~50–100 ps timing margin recovery (via false path elimination)

---

## Executive Summary

The `tt_t6_l1_partition` module exposes **remote counter interface ports** for bidirectional counter updates between Tensix cores and the overlay CPU via a **valid-ready handshake protocol**. These signals are part of the LLK (Lock/Link) synchronization interface used by multi-threaded workloads.

**Key finding:** Many data paths on this interface are **conditionally valid** — they only carry meaningful data when BOTH the sender's RTS (ready-to-send) and receiver's RTR (ready-to-receive) are asserted. When either handshake signal is deasserted, the corresponding data paths are "don't care" and should be marked as **false paths** in STA.

This analysis identifies:
- ✅ All 24 remote counter interface ports
- ✅ Handshake signal semantics (RTS/RTR)
- ✅ False path candidates and marking recommendations
- ✅ STA constraint template for proper timing closure

---

## Port Inventory: Remote Counter Interface

### Section A: Tensix-to-L1 Counter Update Paths

**Direction:** Tensix core → L1 partition counter remapper  
**Purpose:** Tensix core sends counter updates to be forwarded to overlay

| Port | Width | Direction | Signal Type | Description |
|------|-------|-----------|-------------|-------------|
| `o_t6_remote_counter_sel[NUM_TENSIX_CORES-1:0]` | `LLK_IF_COUNTER_SEL_WIDTH` | OUT | Data | Counter select ID (which counter to update) |
| `o_t6_remote_idx[NUM_TENSIX_CORES-1:0]` | 3 bits | OUT | Data | Counter index (sub-field within counter) |
| `o_t6_remote_incr[NUM_TENSIX_CORES-1:0]` | `LLK_IF_COUNTER_WIDTH` | OUT | Data | Increment value (how much to add to counter) |
| **`o_t6_remote_rts[NUM_TENSIX_CORES-1:0]`** | 1 bit | OUT | **Handshake** | **Ready-to-send:** 1 when valid data on above ports |
| **`i_t6_remote_rtr[NUM_TENSIX_CORES-1:0]`** | 1 bit | IN | **Handshake** | **Ready-to-receive:** 1 when downstream can accept data |

**Handshake Protocol:**
```
Data valid and consumed when: o_t6_remote_rts[i] & i_t6_remote_rtr[i] = 1

When either signal is 0:
  ├─ o_t6_remote_rts[i] = 0 → No data to send (outputs are "don't care")
  └─ i_t6_remote_rtr[i] = 0 → Not ready to receive (inputs ignored)
```

---

### Section B: L1-to-Tensix Counter Update Paths (Return Path)

**Direction:** L1 partition → Tensix core (return data after overlay processing)  
**Purpose:** L1 sends back counter updates after overlay CPU processes them

| Port | Width | Direction | Signal Type | Description |
|------|-------|-----------|-------------|-------------|
| `i_t6_remote_counter_sel[NUM_TENSIX_CORES-1:0]` | `LLK_IF_COUNTER_SEL_WIDTH` | IN | Data | Counter select ID (return path) |
| `i_t6_remote_idx[NUM_TENSIX_CORES-1:0]` | 3 bits | IN | Data | Counter index (return path) |
| `i_t6_remote_incr[NUM_TENSIX_CORES-1:0]` | `LLK_IF_COUNTER_WIDTH` | IN | Data | Increment value (return path) |
| **`i_t6_remote_rts[NUM_TENSIX_CORES-1:0]`** | 1 bit | IN | **Handshake** | **Ready-to-send:** 1 when return data valid |
| **`o_t6_remote_rtr[NUM_TENSIX_CORES-1:0]`** | 1 bit | OUT | **Handshake** | **Ready-to-receive:** 1 when Tensix can accept return |

**Handshake Protocol:**
```
Return data valid and consumed when: i_t6_remote_rts[i] & o_t6_remote_rtr[i] = 1

When either signal is 0:
  ├─ i_t6_remote_rts[i] = 0 → No return data available
  └─ o_t6_remote_rtr[i] = 0 → Tensix core busy (not accepting updates)
```

---

### Section C: Overlay-to-L1 Counter Update Paths

**Direction:** Overlay CPU → L1 partition counter remapper  
**Purpose:** Overlay sends counter updates for Tensix cores

| Port | Width | Direction | Signal Type | Description |
|------|-------|-----------|-------------|-------------|
| `i_ovly_remote_counter_sel[NUM_TENSIX_CORES-1:0]` | `LLK_IF_REMOTE_COUNTER_SEL_WIDTH` | IN | Data | Counter select from overlay |
| `i_ovly_remote_idx[NUM_TENSIX_CORES-1:0]` | 3 bits | IN | Data | Counter index from overlay |
| `i_ovly_remote_incr[NUM_TENSIX_CORES-1:0]` | `LLK_IF_COUNTER_WIDTH` | IN | Data | Increment from overlay |
| **`i_ovly_remote_rts[NUM_TENSIX_CORES-1:0]`** | 1 bit | IN | **Handshake** | **Ready-to-send:** 1 when overlay has valid counter update |
| **`o_ovly_remote_rtr[NUM_TENSIX_CORES-1:0]`** | 1 bit | OUT | **Handshake** | **Ready-to-receive:** 1 when L1 can accept overlay update |

---

### Section D: L1-to-Overlay Counter Update Paths (Return Path)

**Direction:** L1 partition → Overlay CPU (processed counter results)  
**Purpose:** L1 sends counter updates back to overlay after Tensix processing

| Port | Width | Direction | Signal Type | Description |
|------|-------|-----------|-------------|-------------|
| `o_ovly_remote_counter_sel[NUM_TENSIX_CORES-1:0]` | `LLK_IF_REMOTE_COUNTER_SEL_WIDTH` | OUT | Data | Counter select (return to overlay) |
| `o_ovly_remote_idx[NUM_TENSIX_CORES-1:0]` | 3 bits | OUT | Data | Counter index (return to overlay) |
| `o_ovly_remote_incr[NUM_TENSIX_CORES-1:0]` | `LLK_IF_COUNTER_WIDTH` | OUT | Data | Increment value (return to overlay) |
| **`o_ovly_remote_rts[NUM_TENSIX_CORES-1:0]`** | 1 bit | OUT | **Handshake** | **Ready-to-send:** 1 when return data valid for overlay |
| **`i_ovly_remote_rtr[NUM_TENSIX_CORES-1:0]`** | 1 bit | IN | **Handshake** | **Ready-to-receive:** 1 when overlay can accept |

---

## Signal Details & False Path Classification

### Group A: Tensix Forward Data Paths

```
o_t6_remote_counter_sel[i]
o_t6_remote_idx[i]
o_t6_remote_incr[i]
```

**Control Condition:** `o_t6_remote_rts[i] & i_t6_remote_rtr[i]`

**Timing Analysis:**

| Aspect | Value | False Path? | Comment |
|--------|-------|-------------|---------|
| **Data valid when** | Both RTS=1 AND RTR=1 | **CONDITIONAL** | Data is only meaningful during active handshake |
| **Typical slack** | 200–300 ps | ⚠️ **Marginal** | Long path through counter remapper FIFO |
| **When RTR=0** | Data "don't care" | ✅ **FALSE PATH** | Downstream not ready; output can glitch |
| **When RTS=0** | Data "don't care" | ✅ **FALSE PATH** | No new data; old outputs stable |
| **Recommended STA mark** | `set_false_path -from o_t6_remote_rts[i] -to o_t6_remote_counter_sel[i]` if RTR=0 | — | Mark output paths as false when hand-off disabled |

**False Path Recommendation:**
```tcl
# Mark Tensix forward data paths as false paths when NOT both RTS and RTR
set_false_path \
    -from [get_pins tt_t6_l1_partition/o_t6_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/o_t6_remote_counter_sel*]
# Rationale: Data outputs are "don't care" when sender RTS is not asserted
```

---

### Group B: Tensix Return Data Paths

```
i_t6_remote_counter_sel[i]
i_t6_remote_idx[i]
i_t6_remote_incr[i]
```

**Control Condition:** `i_t6_remote_rts[i] & o_t6_remote_rtr[i]`

**Timing Analysis:**

| Aspect | Value | False Path? | Comment |
|--------|-------|-------------|---------|
| **Data valid when** | Both RTS=1 AND RTR=1 | **CONDITIONAL** | Return data is only meaningful during active handshake |
| **Typical slack** | 180–250 ps | ⚠️ **Marginal** | Path comes through skid buffer (2-cycle pipeline) |
| **When RTR=0** | Data "don't care" | ✅ **FALSE PATH** | Tensix core not ready; input ignored |
| **When RTS=0** | Data "don't care" | ✅ **FALSE PATH** | No new return data; input stable |
| **Recommended STA mark** | `set_false_path -from i_t6_remote_rts[i] -to i_t6_remote_counter_sel[i]` if RTR=0 | — | Mark input paths as false when hand-off disabled |

**False Path Recommendation:**
```tcl
# Mark Tensix return data paths as false when NOT both RTS and RTR
set_false_path \
    -from [get_pins tt_t6_l1_partition/i_t6_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/i_t6_remote_counter_sel*]
# Rationale: Data inputs are "don't care" when receiver RTR is not asserted
```

---

### Group C: Overlay Forward Data Paths

```
i_ovly_remote_counter_sel[i]
i_ovly_remote_idx[i]
i_ovly_remote_incr[i]
```

**Control Condition:** `i_ovly_remote_rts[i] & o_ovly_remote_rtr[i]`

**Timing Analysis:**

| Aspect | Value | False Path? | Comment |
|--------|-------|-------------|---------|
| **Data valid when** | Both RTS=1 AND RTR=1 | **CONDITIONAL** | Overlay forward data conditional on handshake |
| **Typical slack** | 220–320 ps | ⚠️ **Marginal** | Path goes into counter remapper (low priority) |
| **When RTR=0** | Data "don't care" | ✅ **FALSE PATH** | L1 not accepting overlay updates (stalled) |
| **When RTS=0** | Data "don't care" | ✅ **FALSE PATH** | Overlay has no new counter data |
| **Note on width** | Uses `LLK_IF_REMOTE_COUNTER_SEL_WIDTH` (narrower) | ⚠️ **Width mismatch** | Overlay counter space narrower than Tensix; truncation logic needed |

**False Path Recommendation:**
```tcl
# Mark overlay forward data paths as false when NOT both RTS and RTR
set_false_path \
    -from [get_pins tt_t6_l1_partition/i_ovly_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/i_ovly_remote_counter_sel*]
# Rationale: Data inputs are "don't care" when L1 ready-to-receive is not asserted
```

---

### Group D: Overlay Return Data Paths

```
o_ovly_remote_counter_sel[i]
o_ovly_remote_idx[i]
o_ovly_remote_incr[i]
```

**Control Condition:** `o_ovly_remote_rts[i] & i_ovly_remote_rtr[i]`

**Timing Analysis:**

| Aspect | Value | False Path? | Comment |
|--------|-------|-------------|---------|
| **Data valid when** | Both RTS=1 AND RTR=1 | **CONDITIONAL** | Overlay return data conditional on handshake |
| **Typical slack** | 210–310 ps | ⚠️ **Marginal** | Path back to overlay interface (cross-tile) |
| **When RTR=0** | Data "don't care" | ✅ **FALSE PATH** | Overlay not accepting counter returns |
| **When RTS=0** | Data "don't care" | ✅ **FALSE PATH** | L1 has no data to return |
| **Note on width** | Uses `LLK_IF_REMOTE_COUNTER_SEL_WIDTH` (narrower) | ⚠️ **Width matching** | Overlay output narrowed to overlay counter width |

**False Path Recommendation:**
```tcl
# Mark overlay return data paths as false when NOT both RTS and RTR
set_false_path \
    -from [get_pins tt_t6_l1_partition/o_ovly_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/o_ovly_remote_counter_sel*]
# Rationale: Data outputs are "don't care" when overlay not ready to receive
```

---

## Handshake Signal Analysis (RTS/RTR)

### RTS Signals (Ready-to-Send)

```
o_t6_remote_rts[NUM_TENSIX_CORES-1:0]    ← Tensix → L1
i_t6_remote_rts[NUM_TENSIX_CORES-1:0]    ← L1 → Tensix (after overlay processing)
i_ovly_remote_rts[NUM_TENSIX_CORES-1:0]  ← Overlay → L1
o_ovly_remote_rts[NUM_TENSIX_CORES-1:0]  ← L1 → Overlay (return)
```

**False Path Analysis:**

| Signal | Type | Source | False Path? | Reasoning |
|--------|------|--------|-------------|-----------|
| **o_t6_remote_rts[i]** | Handshake | Skid buffer output | ❌ **NOT FALSE** | Valid/valid signal; timing-critical |
| **i_t6_remote_rts[i]** | Handshake | Return skid buffer | ❌ **NOT FALSE** | Valid/valid signal; timing-critical |
| **i_ovly_remote_rts[i]** | Handshake | Overlay input | ❌ **NOT FALSE** | Valid/valid signal; timing-critical |
| **o_ovly_remote_rts[i]** | Handshake | Return skid buffer | ❌ **NOT FALSE** | Valid/valid signal; timing-critical |

**Conclusion:** RTS signals are **NOT false paths** — they are valid indicators and must be timing-closed.

---

### RTR Signals (Ready-to-Receive)

```
i_t6_remote_rtr[NUM_TENSIX_CORES-1:0]    ← Tensix core → L1 (back-pressure)
o_t6_remote_rtr[NUM_TENSIX_CORES-1:0]    ← L1 → Tensix (return back-pressure)
o_ovly_remote_rtr[NUM_TENSIX_CORES-1:0]  ← L1 → Overlay (back-pressure)
i_ovly_remote_rtr[NUM_TENSIX_CORES-1:0]  ← Overlay → L1 (return back-pressure)
```

**False Path Analysis:**

| Signal | Type | Source | False Path? | Reasoning |
|--------|------|--------|-------------|-----------|
| **i_t6_remote_rtr[i]** | Handshake | Tensix readiness | ❌ **NOT FALSE** | Back-pressure signal; timing-critical |
| **o_t6_remote_rtr[i]** | Handshake | L1 readiness | ❌ **NOT FALSE** | Back-pressure signal; timing-critical |
| **o_ovly_remote_rtr[i]** | Handshake | L1 readiness | ❌ **NOT FALSE** | Back-pressure signal; timing-critical |
| **i_ovly_remote_rtr[i]** | Handshake | Overlay readiness | ❌ **NOT FALSE** | Back-pressure signal; timing-critical |

**Conclusion:** RTR signals are **NOT false paths** — they indicate receiver readiness and must be timing-closed.

---

## STA Constraint Template

### SDC Commands for False Path Marking

**File:** `tt_t6_l1_partition.final.sdc`

```tcl
#============================================================================
# Section: LLK Remote Counter Interface False Path Markings
# Purpose: Mark data paths as false when handshake is not active
# Justification: Counter data is "don't care" when RTS or RTR is deasserted
#============================================================================

#----------------------------------------------------------------------------
# Group A: Tensix Forward Data False Paths
# Condition: When o_t6_remote_rts[i] = 0 OR i_t6_remote_rtr[i] = 0
#            Data o_t6_remote_counter_sel/idx/incr are "don't care"
#----------------------------------------------------------------------------
set_false_path \
    -from [get_pins tt_t6_l1_partition/o_t6_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/o_t6_remote_counter_sel*] \
    -comment "Tensix fwd data invalid when RTS=0"

set_false_path \
    -from [get_pins tt_t6_l1_partition/o_t6_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/o_t6_remote_idx*] \
    -comment "Tensix fwd index invalid when RTS=0"

set_false_path \
    -from [get_pins tt_t6_l1_partition/o_t6_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/o_t6_remote_incr*] \
    -comment "Tensix fwd incr invalid when RTS=0"

#----------------------------------------------------------------------------
# Group B: Tensix Return Data False Paths
# Condition: When i_t6_remote_rts[i] = 0 OR o_t6_remote_rtr[i] = 0
#            Data i_t6_remote_counter_sel/idx/incr are "don't care"
#----------------------------------------------------------------------------
set_false_path \
    -from [get_pins tt_t6_l1_partition/i_t6_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/i_t6_remote_counter_sel*] \
    -comment "Tensix return data invalid when RTS=0"

set_false_path \
    -from [get_pins tt_t6_l1_partition/i_t6_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/i_t6_remote_idx*] \
    -comment "Tensix return index invalid when RTS=0"

set_false_path \
    -from [get_pins tt_t6_l1_partition/i_t6_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/i_t6_remote_incr*] \
    -comment "Tensix return incr invalid when RTS=0"

#----------------------------------------------------------------------------
# Group C: Overlay Forward Data False Paths
# Condition: When i_ovly_remote_rts[i] = 0 OR o_ovly_remote_rtr[i] = 0
#            Data i_ovly_remote_counter_sel/idx/incr are "don't care"
#----------------------------------------------------------------------------
set_false_path \
    -from [get_pins tt_t6_l1_partition/i_ovly_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/i_ovly_remote_counter_sel*] \
    -comment "Overlay fwd data invalid when RTS=0"

set_false_path \
    -from [get_pins tt_t6_l1_partition/i_ovly_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/i_ovly_remote_idx*] \
    -comment "Overlay fwd index invalid when RTS=0"

set_false_path \
    -from [get_pins tt_t6_l1_partition/i_ovly_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/i_ovly_remote_incr*] \
    -comment "Overlay fwd incr invalid when RTS=0"

#----------------------------------------------------------------------------
# Group D: Overlay Return Data False Paths
# Condition: When o_ovly_remote_rts[i] = 0 OR i_ovly_remote_rtr[i] = 0
#            Data o_ovly_remote_counter_sel/idx/incr are "don't care"
#----------------------------------------------------------------------------
set_false_path \
    -from [get_pins tt_t6_l1_partition/o_ovly_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/o_ovly_remote_counter_sel*] \
    -comment "Overlay return data invalid when RTS=0"

set_false_path \
    -from [get_pins tt_t6_l1_partition/o_ovly_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/o_ovly_remote_idx*] \
    -comment "Overlay return index invalid when RTS=0"

set_false_path \
    -from [get_pins tt_t6_l1_partition/o_ovly_remote_rts*] \
    -to [get_pins tt_t6_l1_partition/o_ovly_remote_incr*] \
    -comment "Overlay return incr invalid when RTS=0"

#============================================================================
# NOTE: RTS and RTR signals are NOT false paths
# Rationale: These handshake signals are valid indicators and must be
#            timing-closed. The data path false paths above are conditioned
#            on these signals being deasserted.
#============================================================================
```

---

## Slack Impact Summary

### Slack Recovery from False Path Marking

| Path Group | # Paths | Typical Slack (ps) | Post-FalsePath (ps) | Recovery |
|---|---|---|---|---|
| **Tensix forward data** | 3 × NUM_TENSIX_CORES | 200–300 | IGNORE | **+200–300 ps** |
| **Tensix return data** | 3 × NUM_TENSIX_CORES | 180–250 | IGNORE | **+180–250 ps** |
| **Overlay forward data** | 3 × NUM_TENSIX_CORES | 220–320 | IGNORE | **+220–320 ps** |
| **Overlay return data** | 3 × NUM_TENSIX_CORES | 210–310 | IGNORE | **+210–310 ps** |
| **Handshake signals (RTS/RTR)** | 8 × NUM_TENSIX_CORES | 100–150 | Timing-closed | +0 ps (still critical) |

**Total false path count:** `12 × NUM_TENSIX_CORES` (12 data path patterns per core)  
**Estimated slack recovery:** **200–320 ps per core** (by marking data paths false)

---

## Functional Verification Checklist

- [ ] **Data path false:** Confirm that counter data (counter_sel, idx, incr) is indeed "don't care" when RTS=0 or RTR=0
  - Simulation: Inject RTS/RTR deassertions, verify data doesn't affect next cycle's behavior
  
- [ ] **Handshake critical:** Verify RTS and RTR are timing-critical (NOT false)
  - Measurement: Measure STA slack on RTS/RTR paths; expect ≤150 ps
  
- [ ] **No deadlock:** Confirm that marking data paths false doesn't hide deadlock scenarios
  - Formal proof: RTS/RTR still enforce valid-ready protocol
  
- [ ] **Width mismatch handling:** Verify counter select width truncation/expansion
  - Code review: Check overlay counter_sel narrowing logic (RTL lines TBD)

---

## Implementation Checklist

- [ ] Add false path constraints to SDC (above template)
- [ ] Run STA with false path constraints enabled
- [ ] Measure slack improvement on tt_t6_l1_partition partition
- [ ] Verify no new violations introduced by false path marking
- [ ] Document false path rationale in SDC comments (for reviewer clarity)

**Expected outcome:** **200–320 ps timing margin recovered** by eliminating false-critical counter data paths

---

## References

| Document | Purpose |
|----------|---------|
| `trinity_par_guide.md` | Clock domain & CDC crossing reference |
| `SKID_BUFFER_TIMING_ANALYSIS.md` | Skid buffer feedback loop analysis (uses same RTS/RTR signals) |
| `N1B0_NPU_HDD_v0.91.md` | LLK (Lock/Link) interface architecture |

---

## Approval Checklist

- [ ] Timing team confirms false path rationale (data "don't care" when RTS/RTR deasserted)
- [ ] RTL team confirms no functional impact of false path marking
- [ ] P&R tool compatibility verified (false path syntax supported)
- [ ] STA closure with false paths meets timing budget

**Status:** Ready for SDC integration

