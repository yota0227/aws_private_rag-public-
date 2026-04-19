# Hardware Design Document: EDC1 (Error Detection & Control / Event Diagnostic Channel)

**Project:** Trinity (Tenstorrent AI SoC)
**Version:** EDC1 v1.1.0 (SUPER=1, MAJOR=1, MINOR=0) — Document V0.9
**Document Status:** V0.9
**Date:** 2026-03-27

**Changes from V0.7:**
- §20 (new): SDC False Path Guide — four complete copy-paste TCL scripts,
  one per compile top: `tt_neo_overlay_wrapper`, `tt_tensix_with_l1`,
  `tt_trin_noc_niu_router_wrap`, `trinity_noc2axi_router_ne/nw_opt`;
  RTL cell-name → SDC pattern mapping table; verification checklist
- Note: scripts are scoped to partition-level compile tops only —
  `trinity` (full SoC top) is excluded by design; run per-partition
- V0.8, V0.9 (PNG only): figure updates only (no text changes vs V0.7)

> **Base document:** Sections §1–§19 and Appendices A–C are unchanged from V0.7.
> Read `EDC_HDD_V0.7.md` for full EDC architecture, protocol, node tables,
> instance paths, and firmware interface. This file documents the V0.9 delta only.

---

> **N1B0 Adaptation Note:**
> - **NIU tiles (Y=4):** 4 variants: NE_OPT (X=0), NOC2AXI_ROUTER_NE_OPT (X=1,
>   composite dual-row), NOC2AXI_ROUTER_NW_OPT (X=2, composite dual-row), NW_OPT (X=3)
> - **Ring traversal:** Composite tiles (X=1,2) internal ring exits Y=4, exits at Y=3
> - **ROUTER at Y=3, X=1,2:** Empty placeholder — EDC nodes inside composite modules
> - **4 independent per-column rings**

---

## Table of Contents — V0.9 Delta

20. [SDC False Path Guide](#20-sdc-false-path-guide)
    - 20.1 [Background — Why False Paths Are Needed](#201-background--why-false-paths-are-needed)
    - 20.2 [Signal Classification and RTL Cell Names](#202-signal-classification-and-rtl-cell-names)
    - 20.3 [Full Script — `tt_neo_overlay_wrapper` Top](#203-full-script--tt_neo_overlay_wrapper-top)
    - 20.4 [Full Script — `tt_tensix_with_l1` Top](#204-full-script--tt_tensix_with_l1-top)
    - 20.5 [Full Script — `tt_trin_noc_niu_router_wrap` Top](#205-full-script--tt_trin_noc_niu_router_wrap-top)
    - 20.6 [Full Script — `trinity_noc2axi_router_ne/nw_opt` Top (N1B0 Composite)](#206-full-script--trinity_noc2axi_router_nenw_opt-top-n1b0-composite)
    - 20.7 [How to Apply — Step-by-Step Procedure](#207-how-to-apply--step-by-step-procedure)
    - 20.8 [Verification Checklist](#208-verification-checklist)

---

## 20. SDC False Path Guide

### 20.1 Background — Why False Paths Are Needed

The EDC ring carries three signal classes that must be excluded from
setup/hold analysis. Leaving them unconstrained causes false STA violations
or silent over-constraining.

#### 20.1.1 Toggle Handshake (`req_tgl[1:0]`, `ack_tgl[1:0]`)

The EDC protocol uses a 2-bit toggle handshake between adjacent ring nodes
(§3.3, V0.7). The transmitting node holds `req_tgl` stable until the
downstream node acknowledges — there is no setup/hold relationship between
the two node clocks.

**N1B0 Samsung 5nm:** `DISABLE_SYNC_FLOPS = 1` — no RTL synchronizer on the
toggle path (see §3.3.4, V0.7). The toggle wires run purely combinationally
between node flip-flops. The STA tool must be told to ignore them.

Net pattern: `*req_tgl[*]`, `*ack_tgl[*]`

#### 20.1.2 EDC Data Bus (`data[15:0]`, `data_p`)

Data is captured by each node only after the toggle handshake completes —
protocol guarantees it is stable before the sampling edge. No timing
relationship exists between driver clock and capture clock.

Net patterns: `*edc*data[*]`, `*edc*data_p*`

#### 20.1.3 Asynchronous Init (`async_init`)

Driven by the BIU's `CTRL.INIT` register flip-flop (APB clock), propagates
combinationally through every ring node, and is sampled by each node's own
3-stage synchronizer (`init_sync3r`, type `tt_libcell_sync3r`, pin `i_D`).
BIU APB clock is unrelated to all node clocks.

Source cell pattern: `*field_storage*CTRL*INIT*value*`
Sink pin pattern:    `*/init_sync3r/i_D`

---

### 20.2 Signal Classification and RTL Cell Names

| Signal | Width | Net pattern | Driving FF | Capturing FF | SDC form |
|--------|-------|------------|-----------|-------------|---------|
| `req_tgl` | 2-bit | `*req_tgl[*]` | SM req drive FF | Next-node SM (no sync3r, N1B0) | `-through net` |
| `ack_tgl` | 2-bit | `*ack_tgl[*]` | SM ack drive FF | Prev-node SM (no sync3r, N1B0) | `-through net` |
| `data[15:0]` | 16-bit | `*edc*data[*]` | Node data reg | Next-node data reg | `-through net` |
| `data_p` | 1-bit | `*edc*data_p*` | Node parity reg | Next-node reg | `-through net` |
| `async_init` | 1-bit | `*async_init*` | `field_storage*CTRL*INIT*value` (APB FF) | `*/init_sync3r/i_D` in every node SM | `-from cell -to pin` |

**N1B0 sync3r note:**
`DISABLE_SYNC_FLOPS = 1` → generate blocks `gen_with_ingress_sync` and
`gen_with_egress_sync` in `tt_edc1_state_machine.sv` (lines 1086–1124) are
**not elaborated**. Instances `ingress_req0_tgl_sync3`, `ingress_req1_tgl_sync3`,
`egress_ack0_tgl_sync3`, `egress_ack1_tgl_sync3` **do not exist** in the
N1B0 netlist. Use net-based false paths only for `req_tgl`/`ack_tgl`.

`init_sync3r` (for `async_init`) **is always instantiated** regardless of
`DISABLE_SYNC_FLOPS` and must appear as an explicit `-to` endpoint.

---

### 20.3 Full Script — `tt_neo_overlay_wrapper` Top

**What this module contains:**
- OVL_AI_CLK domain EDC nodes (ai_clk)
- `edc_muxing_when_harvested` bypass mux
- `overlay_loopback_repeater` (noc_clk)
- BIU is **outside** this module (in `tt_trin_noc_niu_router_wrap`); `async_init`
  enters from the port and is already a routed net — full net false path suffices

**Clocks at this top:** `i_aiclk` (ai_clk), `i_nocclk` (noc_clk), `i_dmclk` (dm_clk)

```tcl
##############################################################################
# EDC false-path SDC — tt_neo_overlay_wrapper
# Copy and paste this entire block into the SDC for this compile top.
# Run AFTER create_clock definitions are in place.
##############################################################################

# ─── Clock definitions (adjust periods to match your frequency plan) ─────────
create_clock -name i_aiclk  -period 1.00 [get_ports i_aiclk]
create_clock -name i_nocclk -period 1.25 [get_ports i_nocclk]
create_clock -name i_dmclk  -period 4.00 [get_ports i_dmclk]

# ─── 1. Toggle handshake signals ─────────────────────────────────────────────
# No sync3r in N1B0 (DISABLE_SYNC_FLOPS=1) — false path on raw nets.
set_false_path -through [get_nets -hierarchical {*req_tgl[0]}]
set_false_path -through [get_nets -hierarchical {*req_tgl[1]}]
set_false_path -through [get_nets -hierarchical {*ack_tgl[0]}]
set_false_path -through [get_nets -hierarchical {*ack_tgl[1]}]

# ─── 2. EDC data bus (protocol-stable before capture) ─────────────────────────
set_false_path -through [get_nets -hierarchical {*edc*data[*]}]
set_false_path -through [get_nets -hierarchical {*edc*data_p*}]

# ─── 3. async_init (BIU CTRL.INIT → ring nodes; BIU is outside this module) ──
# async_init arrives as a port/net — declare full net as false path.
set_false_path -through [get_nets -hierarchical {*async_init*}]
# Also cover the sync3r D-input inside any OVL EDC node state machines:
set_false_path \
    -to [get_pins -hierarchical -filter {NAME =~ */init_sync3r/i_D}]

# ─── 4. ai_clk ↔ noc_clk CDC on EDC ring (OVL node → NOC node boundary) ──────
set_false_path \
    -from [get_clocks {i_aiclk}] \
    -through [get_nets -hierarchical {*req_tgl[*]}] \
    -to   [get_clocks {i_nocclk}]
set_false_path \
    -from [get_clocks {i_nocclk}] \
    -through [get_nets -hierarchical {*ack_tgl[*]}] \
    -to   [get_clocks {i_aiclk}]

# ─── 5. ai_clk ↔ dm_clk CDC on EDC ring ──────────────────────────────────────
set_false_path \
    -from [get_clocks {i_aiclk}] \
    -through [get_nets -hierarchical {*req_tgl[*]}] \
    -to   [get_clocks {i_dmclk}]
set_false_path \
    -from [get_clocks {i_dmclk}] \
    -through [get_nets -hierarchical {*ack_tgl[*]}] \
    -to   [get_clocks {i_aiclk}]

# ─── Verify (run interactively to confirm patterns resolve) ───────────────────
# get_nets -hierarchical {*req_tgl[0]}          ;# must be non-empty
# get_nets -hierarchical {*async_init*}          ;# must be non-empty
# get_pins -hier -filter {NAME =~ */init_sync3r/i_D}  ;# must be non-empty
##############################################################################
```

---

### 20.4 Full Script — `tt_tensix_with_l1` Top

**What this module contains:**
- `tt_neo_overlay_wrapper` (OVL EDC nodes, ai_clk)
- `tt_t6_l1_partition` (L1 / Tensix cores)
- `tt_trin_noc_niu_router_wrap` (NIU/Router EDC nodes + BIU, noc_clk)
- **BIU is inside this compile top** → use precise `-from cell -to pin` for `async_init`
- **CDC crossing present:** ai_clk → noc_clk (req_tgl at NORTH_VC_BUF, row 3a §3.5.2)
  and noc_clk → ai_clk (ack_tgl, row 3c §3.5.2)

**Clocks at this top:** `i_ai_clk` (ai_clk), `i_noc_clk` (noc_clk), `i_dm_clk` (dm_clk)

```tcl
##############################################################################
# EDC false-path SDC — tt_tensix_with_l1
# Copy and paste this entire block into the SDC for this compile top.
# Run AFTER create_clock definitions are in place.
##############################################################################

# ─── Clock definitions (adjust periods to match your frequency plan) ─────────
create_clock -name i_ai_clk  -period 1.00 [get_ports i_ai_clk]
create_clock -name i_noc_clk -period 1.25 [get_ports i_noc_clk]
create_clock -name i_dm_clk  -period 4.00 [get_ports i_dm_clk]

# ─── 1. Toggle handshake signals — all crossings ──────────────────────────────
# Covers same-domain (noc→noc) and cross-domain (ai→noc, noc→ai, ai→dm) paths.
# N1B0: DISABLE_SYNC_FLOPS=1 — no sync3r on toggle; constraint on raw nets.
set_false_path -through [get_nets -hierarchical {*req_tgl[0]}]
set_false_path -through [get_nets -hierarchical {*req_tgl[1]}]
set_false_path -through [get_nets -hierarchical {*ack_tgl[0]}]
set_false_path -through [get_nets -hierarchical {*ack_tgl[1]}]

# Explicit CDC direction — ai_clk ↔ noc_clk (rows 3a, 3c in §3.5.2 V0.7)
set_false_path \
    -from [get_clocks {i_ai_clk}] \
    -through [get_nets -hierarchical {*req_tgl[*]}] \
    -to   [get_clocks {i_noc_clk}]
set_false_path \
    -from [get_clocks {i_noc_clk}] \
    -through [get_nets -hierarchical {*ack_tgl[*]}] \
    -to   [get_clocks {i_ai_clk}]

# Explicit CDC direction — ai_clk ↔ dm_clk (OVL dm-domain nodes)
set_false_path \
    -from [get_clocks {i_ai_clk}] \
    -through [get_nets -hierarchical {*req_tgl[*]}] \
    -to   [get_clocks {i_dm_clk}]
set_false_path \
    -from [get_clocks {i_dm_clk}] \
    -through [get_nets -hierarchical {*ack_tgl[*]}] \
    -to   [get_clocks {i_ai_clk}]

# ─── 2. EDC data bus (protocol-stable before capture) ─────────────────────────
set_false_path -through [get_nets -hierarchical {*edc*data[*]}]
set_false_path -through [get_nets -hierarchical {*edc*data_p*}]

# ─── 3. async_init — BIU CTRL.INIT FF → every init_sync3r/i_D ────────────────
# RTL: edc1_biu_soc_apb4_inner.sv — field_storage.edc_biu.CTRL.INIT.value (APB FF)
# RTL: tt_edc1_bus_interface_unit.sv line 149 — assigns async_init from CTRL.INIT
# RTL: tt_edc1_state_machine.sv line 1132 — tt_libcell_sync3r init_sync3r (.i_D(...))
#
# Precise form (source FF → sink sync3r pin):
set_false_path \
    -from [get_cells -hierarchical \
               -filter {NAME =~ *field_storage*CTRL*INIT*value*}] \
    -to   [get_pins  -hierarchical \
               -filter {NAME =~ */init_sync3r/i_D}]
#
# Broad form (full combinational net chain — belt-and-suspenders):
set_false_path -through [get_nets -hierarchical {*async_init*}]

# ─── 4. APB ↔ noc_clk on BIU register interface ──────────────────────────────
# BIU CTRL register is written on i_axi_clk; EDC serial logic runs on i_noc_clk.
set_false_path -from [get_clocks {i_ai_clk}]  -to [get_clocks {i_noc_clk}]
set_false_path -from [get_clocks {i_noc_clk}] -to [get_clocks {i_ai_clk}]

# ─── Verify (run interactively to confirm patterns resolve) ───────────────────
# get_nets -hierarchical {*req_tgl[0]}                       ;# must be non-empty
# get_nets -hierarchical {*async_init*}                       ;# must be non-empty
# get_pins -hier -filter {NAME =~ */init_sync3r/i_D}          ;# must be non-empty
# get_cells -hier -filter {NAME =~ *field_storage*CTRL*INIT*} ;# must be non-empty
# get_cells -hier -filter {NAME =~ *ingress_req*_tgl_sync3*}  ;# must be EMPTY (N1B0)
##############################################################################
```

---

### 20.5 Full Script — `tt_trin_noc_niu_router_wrap` Top

**What this module contains:**
- 12 NOC EDC nodes: NORTH/EAST/SOUTH/WEST × {VC_BUF, HEADER_ECC, DATA_PARITY}
  (inst IDs 0x00–0x0B, all `i_nocclk`)
- 1 SEC_FENCE node (inst 0xC0, `i_nocclk`)
- EDC BIU + `tt_edc1_noc_sec_controller` with `CTRL.INIT` register
  (written on APB/AXI clock; EDC serial logic on `i_nocclk`)
- `edc_demuxing_when_harvested` demux, `noc_loopback_repeater`
- **All EDC nodes are on `i_nocclk`** — no ai_clk CDC inside this module

**Clocks at this top:** `i_nocclk` (noc_clk), `i_axi_clk` (APB/AXI for BIU registers)

```tcl
##############################################################################
# EDC false-path SDC — tt_trin_noc_niu_router_wrap
# Copy and paste this entire block into the SDC for this compile top.
# Run AFTER create_clock definitions are in place.
##############################################################################

# ─── Clock definitions (adjust periods to match your frequency plan) ─────────
create_clock -name i_nocclk  -period 1.25 [get_ports i_nocclk]
create_clock -name i_axi_clk -period 4.00 [get_ports i_axi_clk]

# ─── 1. Toggle handshake signals ─────────────────────────────────────────────
# All 13 EDC nodes are on i_nocclk (same domain).
# Same-clock toggle paths are still false paths: protocol is self-throttling
# with no setup/hold guarantee relative to the ring cycle period.
# N1B0: DISABLE_SYNC_FLOPS=1 — no sync3r on toggle path.
set_false_path -through [get_nets -hierarchical {*req_tgl[0]}]
set_false_path -through [get_nets -hierarchical {*req_tgl[1]}]
set_false_path -through [get_nets -hierarchical {*ack_tgl[0]}]
set_false_path -through [get_nets -hierarchical {*ack_tgl[1]}]

# ─── 2. EDC data bus (protocol-stable before capture) ─────────────────────────
set_false_path -through [get_nets -hierarchical {*edc*data[*]}]
set_false_path -through [get_nets -hierarchical {*edc*data_p*}]

# ─── 3. async_init — BIU CTRL.INIT FF → all node init_sync3r/i_D ─────────────
# BIU RTL path:
#   edc1_biu_soc_apb4_inner.sv  → field_storage.edc_biu.CTRL.INIT.value (i_axi_clk FF)
#   tt_edc1_bus_interface_unit.sv line 149:
#       assign src_ingress_intf.async_init = csr_cfg.CTRL.INIT.value;
# Sink RTL path (in every node's tt_edc1_state_machine, line 1132):
#       tt_libcell_sync3r init_sync3r (.i_CK(i_clk), .i_D(ingress_intf.async_init), ...)
#
# Precise form (source FF → sink sync3r pin):
set_false_path \
    -from [get_cells -hierarchical \
               -filter {NAME =~ *field_storage*CTRL*INIT*value*}] \
    -to   [get_pins  -hierarchical \
               -filter {NAME =~ */init_sync3r/i_D}]
#
# Broad form (full combinational chain — belt-and-suspenders):
set_false_path -through [get_nets -hierarchical {*async_init*}]

# ─── 4. APB/AXI clock ↔ noc_clk (BIU register interface) ────────────────────
# CTRL.INIT is written on i_axi_clk; BIU outputs EDC traffic on i_nocclk.
# async_init path above already covers the critical crossing;
# these cover any status-readback and handshake paths.
set_false_path -from [get_clocks {i_axi_clk}] -to [get_clocks {i_nocclk}]
set_false_path -from [get_clocks {i_nocclk}]  -to [get_clocks {i_axi_clk}]

# ─── Verify (run interactively to confirm patterns resolve) ───────────────────
# get_nets -hierarchical {*req_tgl[0]}                       ;# must be non-empty
# get_nets -hierarchical {*async_init*}                       ;# must be non-empty
# get_pins -hier -filter {NAME =~ */init_sync3r/i_D}          ;# must be non-empty
# get_cells -hier -filter {NAME =~ *field_storage*CTRL*INIT*} ;# must be non-empty
# get_cells -hier -filter {NAME =~ *ingress_req*_tgl_sync3*}  ;# must be EMPTY (N1B0)
##############################################################################
```

---

### 20.6 Full Script — `trinity_noc2axi_router_ne/nw_opt` Top (N1B0 Composite)

**What this module contains:**
- N1B0-specific composite module spanning Y=4 (NIU/noc2axi) + Y=3 (router)
- Used at X=1 (`_ne_opt`) and X=2 (`_nw_opt`)
- Y=4 NIU EDC nodes (noc_clk) — identical set to `tt_trin_noc_niu_router_wrap`
- Y=3 Router EDC nodes (noc_clk) — additional nodes inside composite module
- Single BIU for both rows (instantiated in Y=4 portion)
- Cross-row EDC flit wires: purely combinational `assign` (no F/F, same noc_clk)
- `REP_DEPTH_LOOPBACK = 6` on loopback path — 6 combinational buffer stages,
  **not** clocked flip-flops; `async_init` uses forward path (not loopback)

**Clocks at this top:** `i_noc_clk` (single noc_clk for both Y=4 and Y=3), `i_axi_clk`

```tcl
##############################################################################
# EDC false-path SDC — trinity_noc2axi_router_ne_opt  (identical for _nw_opt)
# Copy and paste this entire block into the SDC for this compile top.
# Run AFTER create_clock definitions are in place.
##############################################################################

# ─── Clock definitions (adjust periods to match your frequency plan) ─────────
create_clock -name i_noc_clk -period 1.25 [get_ports i_noc_clk]
create_clock -name i_axi_clk -period 4.00 [get_ports i_axi_clk]

# ─── 1. Toggle handshake signals ─────────────────────────────────────────────
# All EDC nodes (Y=4 NIU + Y=3 router) share i_noc_clk.
# Cross-row wires (Y=4→Y=3) are combinational assign — still false path.
# N1B0: DISABLE_SYNC_FLOPS=1 — no sync3r on toggle path.
set_false_path -through [get_nets -hierarchical {*req_tgl[0]}]
set_false_path -through [get_nets -hierarchical {*req_tgl[1]}]
set_false_path -through [get_nets -hierarchical {*ack_tgl[0]}]
set_false_path -through [get_nets -hierarchical {*ack_tgl[1]}]

# ─── 2. EDC data bus (protocol-stable before capture) ─────────────────────────
set_false_path -through [get_nets -hierarchical {*edc*data[*]}]
set_false_path -through [get_nets -hierarchical {*edc*data_p*}]

# ─── 3. async_init — BIU CTRL.INIT FF → all node init_sync3r/i_D ─────────────
# BIU is in Y=4 portion; async_init fans out combinationally to both Y=4 and Y=3
# node state machines.  REP_DEPTH_LOOPBACK=6 adds 6 combinational stages on
# the loopback path — async_init uses the FORWARD path only (not loopback).
# MCPDLY=7 remains adequate (see §3.4.4, V0.7).
#
# Precise form (source FF → sink sync3r pin):
set_false_path \
    -from [get_cells -hierarchical \
               -filter {NAME =~ *field_storage*CTRL*INIT*value*}] \
    -to   [get_pins  -hierarchical \
               -filter {NAME =~ */init_sync3r/i_D}]
#
# Broad form (full combinational chain):
set_false_path -through [get_nets -hierarchical {*async_init*}]

# ─── 4. APB/AXI clock ↔ noc_clk (BIU register interface) ────────────────────
set_false_path -from [get_clocks {i_axi_clk}] -to [get_clocks {i_noc_clk}]
set_false_path -from [get_clocks {i_noc_clk}] -to [get_clocks {i_axi_clk}]

# ─── 5. Cross-row combinational flit wires (Y=4 → Y=3, same noc_clk) ─────────
# These are intra-module assign wires in the same clock domain and normally
# do not generate timing issues.  Enable the line below only if the tool
# reports spurious cross-row setup violations:
# set_false_path -through [get_nets -hierarchical {*cross_row*flit*}]

# ─── Verify (run interactively to confirm patterns resolve) ───────────────────
# get_nets -hierarchical {*req_tgl[0]}                       ;# must be non-empty
# get_nets -hierarchical {*async_init*}                       ;# must be non-empty
# get_pins -hier -filter {NAME =~ */init_sync3r/i_D}          ;# must be non-empty
# get_cells -hier -filter {NAME =~ *field_storage*CTRL*INIT*} ;# must be non-empty
# get_cells -hier -filter {NAME =~ *ingress_req*_tgl_sync3*}  ;# must be EMPTY (N1B0)
##############################################################################
```

---

### 20.7 How to Apply — Step-by-Step Procedure

#### Step 1 — Identify Your Compile Top

| Compile top | SDC script |
|-------------|-----------|
| `tt_neo_overlay_wrapper` | §20.3 |
| `tt_tensix_with_l1` | §20.4 |
| `tt_trin_noc_niu_router_wrap` | §20.5 |
| `trinity_noc2axi_router_ne_opt` (N1B0, X=1) | §20.6 |
| `trinity_noc2axi_router_nw_opt` (N1B0, X=2) | §20.6 (same script) |

> **Note:** These scripts are written for **partition-level** STA runs.
> The `trinity` SoC top is not supported as a single SDC target — run
> per-partition instead.

#### Step 2 — Copy the Full Script Block

Each section §20.3–§20.6 contains one self-contained TCL block marked
`##########...`. Copy everything between the first and last `####` line
and paste it into your SDC file.

#### Step 3 — Adjust Clock Periods

The `create_clock` lines at the top of each script use placeholder periods.
Replace with your actual frequency plan values before running STA.

#### Step 4 — Source in Your Main SDC

```tcl
# In your top-level SDC, after all create_clock / create_generated_clock:
source edc_false_paths_tt_tensix_with_l1.sdc        ;# example
```

Or paste the block directly inline — it is self-contained.

#### Step 5 — If Net Patterns Return Empty

If `get_nets -hierarchical {*req_tgl[0]}` returns empty after synthesis,
the net was renamed. Use these fallback searches:

```tcl
# Find by driving module:
get_nets -of [get_cells -hier -filter {REF_NAME =~ tt_edc1_state_machine}]

# Find by pin name:
get_nets -of [get_pins -hier -filter {NAME =~ *edc_node_inst*egress*req*}]

# Broaden wildcard (if tool uses flat naming):
get_nets {*edc*req_tgl*}
get_nets {*edc*ack_tgl*}
```

Once you find the actual net name, replace the wildcard in the `set_false_path`
command with the exact name or an adjusted wildcard.

---

### 20.8 Verification Checklist

Run the following checks after applying the SDC at any compile top:

```tcl
# ── Pattern resolution ─────────────────────────────────────────────────────
get_nets -hierarchical {*req_tgl[0]}
# Expected: non-empty

get_nets -hierarchical {*ack_tgl[0]}
# Expected: non-empty

get_nets -hierarchical {*async_init*}
# Expected: non-empty

get_pins -hierarchical -filter {NAME =~ */init_sync3r/i_D}
# Expected: non-empty (one per EDC node state machine)

get_cells -hierarchical -filter {NAME =~ *field_storage*CTRL*INIT*value*}
# Expected: non-empty  (only at tops that contain the BIU: §20.4, §20.5, §20.6)
# Expected: empty      (at tt_neo_overlay_wrapper top — BIU is outside)

# ── N1B0 DISABLE_SYNC_FLOPS=1 confirmation ────────────────────────────────
get_cells -hierarchical -filter {NAME =~ *ingress_req*_tgl_sync3*}
# Expected: EMPTY  (N1B0 — sync3r not instantiated for toggle)

get_cells -hierarchical -filter {NAME =~ *egress_ack*_tgl_sync3*}
# Expected: EMPTY  (N1B0)

get_cells -hierarchical -filter {NAME =~ *init_sync3r*}
# Expected: non-empty  (always instantiated for async_init)

# ── False-path coverage ────────────────────────────────────────────────────
report_exceptions -path_type false_path
# Expected: EDC toggle, data, and async_init paths appear in the list

check_timing -include {no_clock unconstrained_endpoint}
# Expected: zero unconstrained endpoints on EDC ring nets

report_cdc
# Expected: zero CDC violations on EDC ring paths

# ── REP_DEPTH_LOOPBACK=6 (composite tile §20.6 only) ──────────────────────
report_timing -through [get_nets -hierarchical {*loopback*rep*}]
# Expected: no failing setup paths (loopback repeaters are combinational)
```

**Common failure modes and fixes:**

| Symptom | Cause | Fix |
|---------|-------|-----|
| `get_nets {*req_tgl*}` returns empty | Synthesis renamed the net | Use `get_nets -of [get_cells -hier -filter {REF_NAME =~ tt_edc1_state_machine}]` to find actual name |
| `get_cells {*CTRL*INIT*value*}` returns empty | BIU is outside this compile top (e.g., overlay-only run) | Use net-based form: `set_false_path -through [get_nets -hier {*async_init*}]` |
| `report_cdc` shows toggle CDC violations | Tool not honouring net-based false path | Add explicit `-from clock -to clock` form as shown in §20.4 step 1 |
| `ingress_req*_tgl_sync3*` is non-empty | Design compiled with `DISABLE_SYNC_FLOPS=0` | Add pin-based constraints: `set_false_path -to [get_pins -hier -filter {NAME =~ */ingress_req*_tgl_sync3/i_D}]` |

---

*End of V0.9 delta. All sections §1–§19 are unchanged from EDC_HDD_V0.7.md.*
