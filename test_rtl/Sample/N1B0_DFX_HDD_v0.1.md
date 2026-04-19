# N1B0 DFX (Design For eXtensibility/Test) Hierarchy HDD v0.1

**RTL directory:** `used_in_n1/rtl/dfx/`
**Files:** 4 modules

---

## 1. Overview

The DFX modules in N1B0 are **clock distribution wrappers** that sit between the global clock network and the functional logic inside each tile. In a full DFX-enabled flow (e.g., with Tessent IJTAG), these modules would contain clock gating cells (`tt_clkbuf`, `tt_libcell_clkbuf`) and IJTAG network switches (SIBs) for scan/BIST access.

In N1B0 (`used_in_n1`), the DFX modules are **simplified pass-throughs**:
- All clock outputs are wire-assigned from clock inputs (no clock buffers instantiated)
- IJTAG network instantiations are replaced with wire assigns
- The IJTAG network itself is conditionally compiled via `` `ifdef INCLUDE_TENSIX_NEO_IJTAG_NETWORK ``
- In N1B0, `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` is **not defined** → IJTAG ports and logic are absent

This simplification is typical for early RTL/simulation flows where DFX infrastructure has not yet been inserted.

---

## 2. DFX Module Summary

| Module | File | Clocks in | Clocks out | IJTAG supported | Used in |
|--------|------|-----------|-----------|----------------|---------|
| `tt_noc_niu_router_dfx` | `tt_noc_niu_router_dfx.sv` | 5 | 5 | yes (ifdef) | NIU/Router tiles (Y=3,Y=4) |
| `tt_overlay_wrapper_dfx` | `tt_overlay_wrapper_dfx.sv` | 5 | 5 | no | Tensix overlay wrapper |
| `tt_instrn_engine_wrapper_dfx` | `tt_instrn_engine_wrapper_dfx.sv` | 1 | 1 | yes (ifdef) | Tensix instruction engine |
| `tt_t6_l1_partition_dfx` | `tt_t6_l1_partition_dfx.sv` | 2 | 3 | yes (ifdef) | Tensix L1 partition |

---

## 3. Module Details

### 3.1 `tt_noc_niu_router_dfx`

**File:** `used_in_n1/rtl/dfx/tt_noc_niu_router_dfx.sv` (112 lines)
**Used in:** Tensix NIU/Router DFX wrapper — sits above `tt_overlay_noc_niu_router` or equivalent tile

**Clocks:**

| Input | Output | Description |
|-------|--------|-------------|
| `i_aon_clk` | `o_postdfx_aon_clk` | Always-on clock (AON domain) |
| `i_clk` | `o_postdfx_clk` | Main clock (noc_clk domain) |
| `i_ovl_core_clk` | `o_postdfx_ovl_core_clk` | Overlay core clock |
| `i_ai_clk` | `o_postdfx_ai_clk` | AI (compute) clock |
| `i_ref_clk` | `o_postdfx_ref_clk` | Reference clock |

All 5 outputs are direct wire assigns in N1B0:
```systemverilog
assign o_postdfx_aon_clk      = i_aon_clk;
assign o_postdfx_clk          = i_clk;
assign o_postdfx_ovl_core_clk = i_ovl_core_clk;
assign o_postdfx_ai_clk       = i_ai_clk;
assign o_postdfx_ref_clk      = i_ref_clk;
```

**IJTAG (under `INCLUDE_TENSIX_NEO_IJTAG_NETWORK`):**
When enabled, adds an IJTAG network connecting this NIU/Router tile to the IJTAG scan chain. Ports added:
- `i_ijtag_si`, `i_ijtag_sel`, `i_ijtag_tck`, `i_ijtag_ue`, `i_ijtag_trstn`, `i_ijtag_se`, `i_ijtag_ce`: IJTAG inputs from chain predecessor
- `o_ijtag_so`: IJTAG serial output to chain successor
- `ijtag_*_to_dfd`, `ijtag_so_from_dfd`: connections to DFD (design for debug) logic

In N1B0: absent (not compiled in).

---

### 3.2 `tt_overlay_wrapper_dfx`

**File:** `used_in_n1/rtl/dfx/tt_overlay_wrapper_dfx.sv` (61 lines)
**Used in:** `tt_overlay_wrapper` top of each Tensix tile — the outermost DFX wrapper for the entire Tensix overlay logic

**Clocks:**

| Input | Output | Description |
|-------|--------|-------------|
| `i_core_clk` | `o_postdfx_core_clk` | Core/uncore combined clock |
| `i_uncore_clk` | `o_postdfx_uncore_clk` | Uncore clock |
| `i_aiclk` | `o_postdfx_aiclk` | AI clock |
| `i_nocclk_aon` | `o_postdfx_nocclk_aon` | NoC clock (AON-qualified) |
| `i_ref_clk` | `o_postdfx_ref_clk` | Reference clock |

All direct wire assigns in N1B0:
```systemverilog
assign o_postdfx_core_clk    = i_core_clk;
assign o_postdfx_uncore_clk  = i_uncore_clk;
assign o_postdfx_aiclk       = i_aiclk;
assign o_postdfx_nocclk_aon  = i_nocclk_aon;
assign o_postdfx_ref_clk     = i_ref_clk;
```

**IJTAG:** Not supported in this module (no `ifdef INCLUDE_TENSIX_NEO_IJTAG_NETWORK` block).

---

### 3.3 `tt_instrn_engine_wrapper_dfx`

**File:** `used_in_n1/rtl/dfx/tt_instrn_engine_wrapper_dfx.sv` (96 lines)
**Used in:** Tensix instruction engine wrapper — sits in the Tensix core's TRISC/BRISC instruction engine hierarchy

**Clocks:**

| Input | Output | Description |
|-------|--------|-------------|
| `i_clk` | `o_postdfx_clk` | Single instruction engine clock |

```systemverilog
assign o_postdfx_clk = i_clk;
```

**IJTAG (under `INCLUDE_TENSIX_NEO_IJTAG_NETWORK`):**
When enabled, connects two FPU G-tile IJTAG chains and the instruction engine's own DFD:

| IJTAG port | Source |
|-----------|--------|
| `i_ijtag_si_from_tt_t6_l1_partition` | Serial in from L1 partition (chain predecessor) |
| `i_ijtag_so_from_tt_fpu_gtile_0` | Serial out from FPU G-Tile 0 |
| `i_ijtag_so_from_tt_fpu_gtile_1` | Serial out from FPU G-Tile 1 |
| `tt_instrn_engine_wrapper_rtl_dfd_tessent_sib_tt_fpu_gtile_0_tc_inst_to_select` | Select to FPU G-Tile 0 (=`i_ijtag_sel_from_tt_t6_l1_partition`) |
| `tt_instrn_engine_wrapper_rtl_dfd_tessent_sib_tt_fpu_gtile_1_tc_inst_to_select` | Select to FPU G-Tile 1 (=same select, chained) |
| `ijtag_*_to_dfd` | IJTAG signals routed to instruction engine DFD logic |
| `ijtag_so_from_dfd` | DFD serial out → top-level chain SO |

IJTAG chain order (when enabled): `tt_t6_l1_partition` → `tt_instrn_engine_wrapper` (SIB) → FPU G-Tile 0 → FPU G-Tile 1 → DFD

In N1B0: absent (not compiled in).

---

### 3.4 `tt_t6_l1_partition_dfx`

**File:** `used_in_n1/rtl/dfx/tt_t6_l1_partition_dfx.sv` (119 lines)
**Used in:** T6 L1 partition — the L1 cache + dispatch L1 DFX wrapper; sits above L1 SRAM arrays

**Clocks:**

| Input | Output | Description |
|-------|--------|-------------|
| `i_clk` | `o_predfx_clk` | Clock before DFX gating (for internal use) |
| `i_clk` | `o_postdfx_clk` | Clock after DFX gating (main functional output) |
| `i_nocclk` | `o_postdfx_nocclk` | NoC clock passthrough |

Note: both `o_predfx_clk` and `o_postdfx_clk` come from the same `i_clk` in N1B0:
```systemverilog
assign o_predfx_clk   = i_clk;
assign o_postdfx_clk  = i_clk;
assign o_postdfx_nocclk = i_nocclk;
```

The `pre-dfx` output is used in testing scenarios where the clock needs to be observed before any DFX gating would have applied.

**IJTAG (under `INCLUDE_TENSIX_NEO_IJTAG_NETWORK`):**
Connects 4 T6 core groups (ts0, ts1, ts2, ts3) and the DFD:

| IJTAG port | Source/Destination |
|-----------|-------------------|
| `i_ijtag_si_from_tt_noc_niu_router` | Serial in from NIU/Router (chain entry point) |
| `i_ijtag_sel_from_tt_noc_niu_router` | Select from NIU/Router |
| `i_ijtag_tck/ue/trstn/se/ce_from_tt_noc_niu_router` | Control from NIU/Router |
| `ijtag_to_sel/si` (ts0) | → T6 core group 0 |
| `i_ijtag_so_from_t6cores_0` | ← T6 core group 0 SO → ts1 SI |
| `ijtag_to_sel_ts1/si_ts1` | → T6 core group 1 |
| `i_ijtag_so_from_t6cores_1` | ← T6 core group 1 SO → ts2 SI |
| `ijtag_to_sel_ts2/si_ts2` | → T6 core group 2 |
| `i_ijtag_so_from_t6cores_2` | ← T6 core group 2 SO → ts3 SI |
| `ijtag_to_sel_ts3/si_ts3` | → T6 core group 3 |
| `ijtag_*_to_dfd` | → L1 partition DFD |
| `ijtag_so_from_dfd` | ← DFD SO → ring output |
| `tt_t6_l1_partition_rtl_dfd_tessent_sib_*_so` | SIB serial out (to next segment) |

IJTAG chain order (when enabled): NIU/Router → L1_partition SIB → ts0 → ts1 → ts2 → ts3 → DFD → chain output

In N1B0: absent (not compiled in).

---

## 4. DFX Hierarchy Within Tensix Tile

```
tt_tensix_with_l1
└── tt_overlay_noc_wrap
    └── tt_overlay_noc_niu_router
        └── tt_noc_niu_router_dfx          ← NIU/Router DFX (5 clocks)
        └── tt_neo_overlay_wrapper
            └── tt_overlay_wrapper
                └── tt_overlay_wrapper_dfx ← Overlay DFX (5 clocks)
                    ├── clock_reset_ctrl
                    ├── tt_overlay_cpu_wrapper
                    │   └── ... (TTTrinityConfig_DigitalTop)
                    ├── tt_overlay_memory_wrapper
                    │   └── tt_t6_l1_partition_dfx ← L1 DFX (2→3 clocks)
                    │       └── ... (SRAM arrays, 4×T6 core groups)
                    └── tt_instrn_engine_wrapper_dfx ← IE DFX (1 clock)
                        └── ... (FPU G-Tile 0, G-Tile 1, DFD)
```

---

## 5. IJTAG Network (When `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` Defined)

Full IJTAG chain topology per Tensix tile (when enabled):

```
External IJTAG tap
  → tt_noc_niu_router_dfx (entry)
      → tt_t6_l1_partition_dfx (SIB)
          → T6 core group 0 (ts0)
          → T6 core group 1 (ts1, SI = SO from ts0)
          → T6 core group 2 (ts2, SI = SO from ts1)
          → T6 core group 3 (ts3, SI = SO from ts2)
          → L1 partition DFD
      → tt_instrn_engine_wrapper_dfx (SIB)
          → FPU G-Tile 0
          → FPU G-Tile 1
          → instruction engine DFD
  → output SO
```

Control signals (`tck`, `trstn`, `sel`, `ce`, `se`, `ue`, `si`) enter at NIU/Router DFX and propagate to all downstream DFX modules.

---

## 6. N1B0 Status: DFX Not Active

In N1B0 (`used_in_n1/`):
- `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` is **not defined** → no IJTAG ports or logic compiled in
- All DFX modules reduce to combinational wire assigns
- No clock buffers (`tt_clkbuf`, `tt_libcell_clkbuf`) are instantiated
- The RTL comments state: "Simple pass-through assignments instead of [dfx module] instantiations"

This is the pre-DFX-insertion RTL state. DFX infrastructure (clock gating cells, IJTAG SIBs) will be inserted in a later flow step (typically Tessent insertion flow).

---

## 7. SW / Test Programming

DFX modules in N1B0 have no programmable registers or SW-visible interfaces. They are structural only.

When `INCLUDE_TENSIX_NEO_IJTAG_NETWORK` is defined (future flow):
- IJTAG access is via the IEEE 1149.1-compatible TAP at the chip top
- Scan chain is navigated using Tessent iJTAG protocol
- No MMIO or APB access to DFX logic

---

*RTL sources:*
- *`used_in_n1/rtl/dfx/tt_noc_niu_router_dfx.sv` (112 lines)*
- *`used_in_n1/rtl/dfx/tt_overlay_wrapper_dfx.sv` (61 lines)*
- *`used_in_n1/rtl/dfx/tt_instrn_engine_wrapper_dfx.sv` (96 lines)*
- *`used_in_n1/rtl/dfx/tt_t6_l1_partition_dfx.sv` (119 lines)*
*Author: N1B0 HDD project, 2026-03-18*
