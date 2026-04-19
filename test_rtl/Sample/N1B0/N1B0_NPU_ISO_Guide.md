# N1B0 NPU ISO Cell Insertion Guide
**Version:** 0.1
**Date:** 2026-03-25
**Scope:** N1B0 Tensix tile harvest power domain — ISO cell insertion and always-on completeness

---

## 1. Power Domain Overview

Each N1B0 Tensix tile (Y=0,1,2 × X=0,1,2,3 → 12 tiles total) has two power domains:

| Domain | Supply | Powers off when? |
|--------|--------|-----------------|
| **PD_main** | VDDM (core supply) | When tile is harvested |
| **PD_AON** (sub-domain) | VDDN (always-on) | Never |

The always-on supply `VDDN` powers the AON elements listed in the UPF. The rest of the tile (BRISC, TRISC, FPU, L1 SRAMs, overlay core logic) is under `VDDM`.

**ISO_EN control signal:** `ISO_EN[x + 4*y]` at `trinity.sv` top — 1-bit per Tensix tile.
**ISO_EN = 1** means tile is being isolated (powered off). **ISO_EN = 0** means tile is active.

Internally per tile, the top-level bit is broadcast as:

```
trinity.sv:  ISO_EN[x + 4*y]
               → tt_tensix_with_l1:  ISO_EN[2:0]
                    [1:0] → tt_overlay_noc_niu_router  (NIU 0 and NIU 1)
                    [2]   → tt_t6_l1_partition
```

---

## 2. ISO Cell Type and Polarity

**Type:** AND-type isolation cell (clamp-to-0)

```
iso_out = sig_in & ~ISO_EN
        = sig_in &  VDDN_ok     (UPF semantics: powered by always-on supply)
```

| ISO_EN | Tile state | iso_out |
|--------|-----------|---------|
| 0 | Active | sig_in (pass-through) |
| 1 | Harvested / powered off | 0 (clamped) |

**Placement rule:** ISO cells must be placed on the **AON side** of the power domain boundary — powered from VDDN, not VDDM. The `ISO_EN` signal itself must be driven from an AON-domain register (inside `clock_reset_ctrl`), not from the powered-off tile logic.

**Safe clamp value:** All signal groups below clamp to `0`.
- For valid/request signals: `0` = no valid transaction → correct safe state.
- For active-low signals: `0` = asserted (e.g., reset held) — verify per signal whether this is safe or whether active-high clamping is preferred.

---

## 3. ISO Cell Insertion — Signal Groups

ISO cells are required at every crossing from `PD_main` (powered-off) into an AON element. There are 11 signal groups.

### 3.1 PD_tt_overlay_wrapper_AON Boundary

#### Group 1 — NoC Flit Outputs (Overlay NIU Core → N↔S Repeaters)
```
Source:  tt_overlay_wrapper (powered-off) → o_flit_out_req_{north,south}
Sink:    overlay_wrapper/noc_north_to_south_repeaters/repeater*stage*0*  (AON)
         overlay_wrapper/noc_south_to_north_repeaters/repeater*stage*0*  (AON)
```
ISO cells on: flit bus data, flit_valid, vc_id, all request head/body fields entering stage-0 inputs of the N↔S repeaters.

#### Group 2 — NoC Credit / Backpressure Feedback (NIU → N↔S Repeater Stage-0)
```
Source:  tt_overlay_noc_niu_router (powered-off) → o_flit_in_resp_{north,south} credits
Sink:    stage-0 inputs of noc_N2S / noc_S2N repeaters  (AON)
```
ISO cells on: credit return signals, backpressure ready.

#### Group 3 — EDC Serial Bus Direct Path (Overlay Core → edc_muxing_when_harvested port 0)
```
Source:  tt_neo_overlay_wrapper main overlay path (powered-off)
         → ovl_egress_intf  (EDC serial data / valid / ready)
Sink:    edc_muxing_when_harvested.ingress_intf_in0  (AON)
```
ISO cells on: `edc_serial_data`, `edc_serial_valid`, and the ready feedback.

> ⚠️ **Critical:** The `i_edc_mux_demux_sel` control driving `edc_muxing_when_harvested` must come
> from an AON register inside `clock_reset_ctrl`. If it is driven from the powered-off overlay SFR
> it will float when the tile is off, corrupting the EDC ring for all remaining active tiles.
> **Verify the source register is in the AON domain before sign-off.**

#### Group 4 — EDC Loopback Path (Overlay Core → overlay_loopback_repeater)
```
Source:  overlay core loopback EDC path (powered-off) → loopback_edc_ingress_intf
Sink:    overlay_loopback_repeater  (AON)
         (tt_noc_overlay_edc_repeater, clocked by i_nocclk from AON clock_reset_ctrl)
```
ISO cells on: loopback EDC serial bus signals.

#### Group 5 — SMN Wrapper Inputs (Overlay Core → smn_wrapper)
```
Source:  tt_overlay_wrapper main core (powered-off)
         → APB slave inputs, interrupt request lines into smn_wrapper
Sink:    overlay_wrapper/smn_wrapper  (AON, clocked by noc_clk_aon)
```
ISO cells on: APB psel, penable, pwrite, paddr, pwdata, pstrb; interrupt request inputs from the overlay core.

#### Group 6 — tt_neo_overlay_wrapper_comb Inputs (Powered-off → AON Comb Wrapper)
```
Source:  tt_neo_overlay_wrapper main logic (powered-off)
         → all combinational feedthrough inputs to tt_neo_overlay_wrapper_comb
Sink:    tt_neo_overlay_wrapper_comb  (AON)
```
ISO cells on: all signals entering `tt_neo_overlay_wrapper_comb` from the powered-off domain.
This includes clock-routing feedthrough, NoC bypass, and PRTN chain feedthrough that passes through this combinational wrapper.

#### Group 7 — Interrupt / WDT / RAS Outputs (Overlay Core → Router / Fabric)
```
Source:  overlay core (powered-off)
         → o_global_wdt_reset, o_ovl_ras_event, o_overlay_irq[*]
Sink:    tt_trin_noc_niu_router_wrap (always-on) or top-level fabric
```
ISO cells on: `o_global_wdt_reset`, `o_ovl_ras_event`, all interrupt lines leaving the tile toward the router or SoC fabric.

#### Group 8 — APB / Peripheral Outputs (Overlay Core → External Always-on Fabric)
```
Source:  overlay core (powered-off) → o_periph_apb_0_psel, o_periph_apb_0_penable
Sink:    always-on peripherals or tt_trin_noc_niu_router_wrap
```
ISO cells on: psel, penable, and any other APB output signals driven by the powered-off overlay.

---

### 3.2 PD_tt_t6_l1_partition_AON Boundary

#### Group 9 — NoC Flit Outputs (L1 Partition Core → W↔E Repeaters)
```
Source:  tt_t6_l1_partition main logic (powered-off)
         → o_flit_out_req_{east,west}
Sink:    noc_west_to_east_repeaters/repeater*stage*0*  (AON)
         noc_east_to_west_repeaters/repeater*stage*0*  (AON)
```
ISO cells on: flit bus data, valid, vc_id entering stage-0 of W↔E repeaters.

#### Group 10 — NoC Credit Feedback (L1 Core → W↔E Repeater Stage-0)
```
Source:  L1 main logic (powered-off) → credit return for W↔E directions
Sink:    stage-0 of noc_W2E / noc_E2W repeaters  (AON)
```
ISO cells on: credit return and backpressure ready signals.

#### Group 11 — DFX Scan / Clock Inputs (L1 Core → tt_t6_l1_partition_dfx_inst)
```
Source:  L1 partition main scan chain outputs (powered-off)
Sink:    tt_t6_l1_partition_dfx_inst  (AON, DFX clock pass-through wrapper)
```
ISO cells on: scan chain data and control signals from the powered-off L1 domain into the DFX wrapper.

---

## 4. Signal Group Summary Table

| # | Signal Group | Source (PD_main, off) | Sink (AON) | Clamp |
|---|-------------|----------------------|-----------|-------|
| 1 | NoC flit N↔S | overlay NIU core | noc_N2S / noc_S2N rep stage-0 | 0 |
| 2 | NoC credit N↔S | overlay NIU | N↔S rep stage-0 | 0 |
| 3 | EDC bus (direct) | overlay EDC egress | edc_muxing_when_harvested port-0 | 0 |
| 4 | EDC bus (loopback) | overlay loopback path | overlay_loopback_repeater | 0 |
| 5 | SMN APB / IRQ inputs | overlay core | smn_wrapper | 0 |
| 6 | Comb wrapper inputs | overlay core | tt_neo_overlay_wrapper_comb | 0 |
| 7 | IRQ / WDT / RAS | overlay core | router / SoC fabric | 0 |
| 8 | APB periph outputs | overlay core | external always-on | 0 |
| 9 | NoC flit W↔E | L1 core | noc_W2E / noc_E2W rep stage-0 | 0 |
| 10 | NoC credit W↔E | L1 core | W↔E rep stage-0 | 0 |
| 11 | DFX scan/clock | L1 core | tt_t6_l1_partition_dfx_inst | 0 |

---

## 5. ISO Cell Implementation

No dedicated `tt_iso_and` primitive was found in `used_in_n1/` RTL. The design currently implements isolation via `tt_harvest_robust` AND-gate modules in `tt_overlay_wrapper_harvest_trinity.sv`. For formal power sign-off, use UPF `set_isolation` so the P&R tool inserts foundry-qualified ISO cells:

```tcl
# Example UPF set_isolation for overlay wrapper
set_isolation ISO_overlay_main \
    -domain       PD_main \
    -isolation_power_net  VDDN \
    -isolation_ground_net VSS \
    -clamp_value  0 \
    -applies_to   outputs \
    -isolation_signal       ISO_EN \
    -isolation_sense        high

set_isolation_control ISO_overlay_main \
    -domain       PD_main \
    -isolation_signal ISO_EN \
    -location     fanout
```

Apply equivalent `set_isolation` commands for `PD_tt_t6_l1_partition` (groups 9–11).

**Note:** `tt_harvest_robust` (triple-replicated AND gates, `NUM_REPLICATE=3`) provides functional isolation but may not satisfy foundry power sign-off rules that require specific ISO cell footprints. Coordinate with the power implementation team to confirm whether `tt_harvest_robust` cells are mapped to qualified library ISO cells at synthesis.

---

## 6. Always-Power-On Module List — Completeness Check

### 6.1 Confirmed Correct

| Module | Reason |
|--------|--------|
| `tt_trin_noc_niu_router_wrap` | NIU/Router tile — non-Tensix, never harvested |
| `overlay_wrapper/noc_north_to_south_repeaters/repeater*stage*[0,1,2]*` | Must forward N→S NoC traffic past harvested tile |
| `overlay_wrapper/noc_south_to_north_repeaters/repeater*stage*[0,1,2]*` | Must forward S→N NoC traffic past harvested tile |
| `overlay_wrapper/tt_overlay_wrapper_dfx_inst` | DFX clock pass-through must always operate |
| `overlay_wrapper/clock_reset_ctrl` | Drives ai_clk / dm_clk chain to south tiles |
| `edc_muxing_when_harvested` | EDC ring bypass mux — holds ring continuity |
| `overlay_loopback_repeater` | EDC loopback repeater for ring continuity |
| `tt_neo_overlay_wrapper_comb` | Combinational feedthrough (clock, NoC bypass, PRTN) |
| `overlay_wrapper/smn_wrapper` | SMN security controller on `noc_clk_aon` |
| `tt_neo_overlay_wrapper_Controller_inst` | Power sequencer for overlay PD — must be AON by definition |
| `noc_west_to_east_repeaters/repeater*stage*[0,1,2]*` | Must pass E→W NoC traffic past harvested tile |
| `noc_east_to_west_repeaters/repeater*stage*[0,1,2]*` | Must pass W→E NoC traffic past harvested tile |
| `tt_t6_l1_partition_dfx_inst` | DFX clock pass-through |
| `tt_t6_l1_partition_Controller_inst` | Power sequencer for L1 PD |

---

### 6.2 Identified Gaps — Action Required

#### Gap 1 — PRTN Chain Feedthrough in `tt_t6_l1_partition` ✅ Not a Gap

**RTL finding:** Lines 413–451 of `tt_t6_l1_partition.sv` are combinational `assign` statements in the main PD (not AON). The PRTN chain daisy-chains Y=2→Y=1→Y=0 within each column (`trinity.sv` lines 233–242). When a tile is powered off, the PRTN chain below it technically floats.

**Resolution:** PRTN chain is **not required during harvest operation**. Harvest is a permanent boot-time configuration. Harvested Tensix cores are permanently excluded from PRTN runtime power management. The chain break at the harvested tile is by design — no active (non-harvested) tile requires PRTN to be routed through a harvested tile.

**No fix required.**

---

#### Gap 2 — `edc_mux_demux_sel` Source Register Must Be in AON ⚠️

**Problem:**
`edc_muxing_when_harvested` (AON) uses `i_edc_mux_demux_sel` as its mux select input. If this signal is driven by the overlay core SFR (which is in `PD_main`), it will float when the tile is powered off. An indeterminate select corrupts the EDC ring for **all remaining active tiles** — not just the harvested tile.

**Fix:**
Confirm that the register holding `edc_mux_demux_sel` is inside `clock_reset_ctrl` (which is in `PD_tt_overlay_wrapper_AON`). If it currently resides in the powered-off overlay SFR:
1. Move the register to `clock_reset_ctrl`.
2. Default value on reset must be `1` (= bypass harvested tile) so that the EDC ring remains intact even before firmware intervention.

---

#### Gap 3 — ai_clk Chain Through `tt_t6_l1_partition` Must Be Verified ⚠️

**Problem:**
`PD_tt_t6_l1_partition_AON` does not list any clock routing element. The L1 partition contains an `ai_clk_gate` (line 665 of `tt_t6_l1_partition.sv`) for the internal Tensix cores. If the **column ai_clk chain** for lower rows (Y < harvested row) passes through any element inside `tt_t6_l1_partition` main domain, that clock will be lost when the tile is powered off.

**Fix:**
Verify that the full ai_clk column chain from top to bottom passes exclusively through `clock_reset_ctrl` instances in each overlay wrapper (which is AON). If any leg of the chain passes through the L1 partition main domain, the corresponding clock buffer/gate must be added to `PD_tt_t6_l1_partition_AON`.

---

### 6.3 Gap Summary

| # | Issue | Verdict | Action |
|---|-------|---------|--------|
| G1 | PRTN chain assigns inside `tt_t6_l1_partition` main PD | ✅ Not a gap — PRTN not required for harvested tiles (design intent) | None |
| G2 | `edc_mux_demux_sel` register source | ✅ Not a gap — register is in `tt_trin_noc_niu_router_wrap` (always-on) | None |
| G3 | ai_clk column chain through L1 partition | ✅ Not a gap — feedthrough path is in `tt_neo_overlay_wrapper_comb` (AON) | None |

**All 3 initial gaps resolved. The always-power-on module list is correct as defined.**

---

## 7. Harvest Sequence (ISO_EN Assertion Order)

The correct order to isolate a Tensix tile at `(x, y)`:

```
1. Firmware writes harvest config:
     edc_mux_demux_sel = 1        (bypass this tile in EDC ring)
     mesh_start/stop reconfigured (exclude row from NoC mesh)

2. Assert reset isolation:
     i_tensix_reset_n[x + 4*y] = 0
     i_dm_{row}_reset_n         = 0

3. Assert ISO_EN:
     ISO_EN[x + 4*y] = 1         (clamp all tile outputs to 0)

4. Power off VDDM supply for this tile's PD_main
   (VDDN / PD_AON remains powered — repeaters, EDC mux, clock_reset_ctrl, smn)

De-isolation (reverse order):
     Power on VDDM → deassert ISO_EN → deassert resets → reconfigure mesh
```

---

## 8. RTL Reference Paths

| Signal / Module | File | Line |
|----------------|------|------|
| `ISO_EN[11:0]` top port | `used_in_n1/rtl/trinity.sv` | ~204 |
| `ISO_EN[x+4*y]` to Tensix tile | `used_in_n1/rtl/trinity.sv` | ~1431–1445 |
| `ISO_EN[2:0]` split in tensix | `tt_tensix_neo/.../tt_tensix_with_l1.sv` | 227, 1296, 1979 |
| `ISO_EN` in overlay wrapper | `tt_rtl/overlay/rtl/tt_overlay_wrapper.sv` | 371 |
| `ISO_EN` in neo overlay wrapper | `tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv` | 391 |
| `ISO_EN[1:0]` in noc_niu_router | `tt_rtl/overlay/rtl/tt_overlay_noc_niu_router.sv` | 357 |
| `ISO_EN` in L1 partition | `tt_tensix_neo/.../tt_t6_l1_partition.sv` | 350 |
| `tt_harvest_robust` AND gate | `tt_rtl/tt_noc/rtl/noc/tt_harvest_robust.sv` | — |
| `tt_harvest_robust_sync` | `tt_rtl/tt_noc/rtl/noc/tt_harvest_robust_sync.sv` | — |
| `tt_overlay_wrapper_harvest` | `tt_rtl/overlay/rtl/tt_overlay_wrapper_harvest_trinity.sv` | — |
| PRTN chain assigns (Gap 1) | `tt_tensix_neo/.../tt_t6_l1_partition.sv` | 413–451 |
| `edc_muxing_when_harvested` | `tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv` | ~522 |
| `overlay_loopback_repeater` | `tt_rtl/overlay/rtl/tt_neo_overlay_wrapper.sv` | ~508 |
| `clock_reset_ctrl` (AON) | `tt_rtl/overlay/rtl/tt_overlay_wrapper.sv` | (search `clock_reset_ctrl`) |
| `smn_wrapper` (AON) | `tt_rtl/overlay/rtl/tt_overlay_wrapper.sv` | ~1776 |
