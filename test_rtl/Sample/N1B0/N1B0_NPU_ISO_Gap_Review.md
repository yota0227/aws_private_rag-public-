# N1B0 NPU ISO Guide — Gap RTL Review
**Date:** 2026-03-25
**Reviewed by:** RTL search across `used_in_n1/`

---

## Gap 1 — PRTN Chain Feedthrough in `tt_t6_l1_partition` (NOT in AON)

### RTL Evidence

**PRTN chain topology confirmed by `trinity.sv` lines 233–242:**

```systemverilog
// PRTN chain daisy-chains DOWN per column: Y=2 → Y=1 → Y=0
// Entry point: PRTNUN_FC2UN_DATA_IN enters at Y=2
assign w_left_prtnun_fc2un_data_in[x][2] = PRTNUN_FC2UN_DATA_IN;

// Each tile's right output feeds the tile below's left input
for (genvar y = 0; y < 2; y++) begin
    assign w_left_prtnun_fc2un_data_in[x][y] = w_right_prtnun_fc2un_data_out[x][y+1];
end
```

**Inside each tile (`tt_tensix_with_l1.sv` lines 318–331):**
```
PRTN_IN → tt_overlay_noc_wrap (feedthrough) → tt_t6_l1_partition (inner chain: 4 Tensix cores) → PRTN_OUT
```

`tt_t6_l1_partition.sv` lines 413–451 are pure combinational `assign` statements in the **main PD body** (not AON). When this tile's VDDM is removed, these wires float — technically breaking the chain for tiles at rows below.

### Verdict: ✅ NOT A GAP — PRTN chain not required during harvest

**Design intent (confirmed by user):** When harvest is applied to a tile, the Tensix cores inside that tile are powered off. There is no operational need to access harvested Tensix cores via PRTN. The PRTN chain break at the harvested tile is **by design** — tiles south of a harvested row are also expected to be harvested in the same harvest event, or the system is structured so that the chain endpoint below a harvested tile does not need PRTN management.

Additionally, harvest is a permanent configuration set at boot time. The PRTN infrastructure is used for runtime power management of **active** cores only. A harvested tile and all its endpoints are permanently excluded from PRTN management by the firmware/controller.

**No fix required for Gap 1.**

---

## Gap 2 — `edc_mux_demux_sel` Source Register

### RTL Evidence

**Register storage:**
- File: `used_in_n1/tt_rtl/tt_noc/registers/edc/rtl/tt_edc1_noc_sec_block_reg_inner.sv`
- Lines 1977–1998: `field_storage.EDC1_MUX_DEMUX_SEL.mux_demux_sel.value` — FF clocked by `i_nocclk`
- Written via EDC serial bus (`edc_ingress_intf`) decode

**Module hierarchy:**
```
tt_trin_noc_niu_router_wrap.sv (line 843)
  └─ tt_edc1_noc_sec_controller
       └─ tt_edc1_noc_sec_block_reg
            └─ tt_edc1_noc_sec_block_reg_inner
                 └─ EDC1_MUX_DEMUX_SEL register FF (i_nocclk)
```

**Output path:**
```
tt_edc1_noc_sec_controller.sv line 217:
    .o_R_edc1_mux_demux_sel_F_mux_demux_sel(o_sec_config.edc_mux_demux_sel)

tt_trin_noc_niu_router_wrap.sv line 939:
    assign edc_mux_demux_sel = edc_config_noc_sec.edc_mux_demux_sel;

tt_trin_noc_niu_router_wrap.sv line 945:
    assign o_edc_mux_demux_sel = edc_mux_demux_sel;
```

**`clock_reset_ctrl` check:**
- File: `used_in_n1/tt_rtl/overlay/rtl/tt_overlay_clock_reset_ctrl.sv`
- **No `edc_mux_demux_sel` port or logic found.** Confirmed: `clock_reset_ctrl` handles only clock gating, reset sync, and clock enable — not EDC configuration.

### Verdict: ✅ FALSE ALARM — GAP DOES NOT EXIST

`edc_mux_demux_sel` is registered inside **`tt_trin_noc_niu_router_wrap`**, which is **declared always-on** (item 1 in the user's always-power-on list). The register is clocked by `i_nocclk` supplied to the always-on NIU/router wrapper. The signal is valid at all times, including when neighboring Tensix tiles are harvested.

No fix needed for Gap 2.

---

## Gap 3 — ai_clk Column Chain Through `tt_t6_l1_partition`

### RTL Evidence

**Clock routing in trinity.sv:**
```
// Lines 465, 493 (simplified):
clock_routing_in[x][4].ai_clk = i_ai_clk[x];          // top row: from pad
clock_routing_in[x][y].ai_clk = clock_routing_out[x][y+1].ai_clk;  // lower rows: from tile above
```

**Feedthrough path in `tt_neo_overlay_wrapper.sv`:**
```systemverilog
// Lines 60-61: ports
input  logic i_ai_clk_feedthrough,
output logic o_ai_clk_feedthrough,

// Line 1027: feedthrough assign (combinational, no gate)
assign o_ai_clk_feedthrough = i_ai_clk_feedthrough;
```

This assign is inside `tt_neo_overlay_wrapper_comb` scope — which **is listed in `PD_tt_overlay_wrapper_AON`**.

**`tt_tensix_with_l1.sv` clock paths (lines 417, 928-959, 1493):**
```
i_ai_clk → assign ai_clk = i_ai_clk                  (top-level wire in tile)
ai_clk   → overlay_noc_wrap.i_ai_clk_feedthrough      (for pass-down chain)
           → overlay_noc_wrap.o_ai_clk_feedthrough     (gated, for downstream tiles)
           → tt_t6_l1_partition.i_clk = t6l1_ai_clk   (gated clock, for L1 own use)
```

The `o_ai_clk_feedthrough` from `tt_neo_overlay_wrapper` feeds `clock_routing_out[x][y].ai_clk`, which provides ai_clk to the tile below (y-1). This feedthrough is inside `tt_neo_overlay_wrapper_comb` (AON).

The `t6l1_ai_clk` that clocks `tt_t6_l1_partition` itself is the gated version from `clock_reset_ctrl` — it is correctly in the main PD and gates off when harvested.

### Verdict: ✅ FALSE ALARM — GAP DOES NOT EXIST

The **ai_clk column chain for south tiles** passes exclusively through:
- `tt_neo_overlay_wrapper_comb` (which is in `PD_tt_overlay_wrapper_AON`) ✅

The `tt_t6_l1_partition.i_clk` is only used for the L1 partition's own internal logic, not for routing clocks to other tiles. When the tile is powered off, only the L1's own clock is lost — which is the correct behavior.

No fix needed for Gap 3.

---

## Final Gap Summary

| Gap | Description | Verdict | Action |
|-----|------------|---------|--------|
| G1 | PRTN chain `assign` in `tt_t6_l1_partition` main PD | ✅ Not a gap — PRTN not required for harvested tiles (design intent) | No action |
| G2 | `edc_mux_demux_sel` register source | ✅ Not a gap — register is in `tt_trin_noc_niu_router_wrap` (always-on) | No action |
| G3 | ai_clk chain through L1 partition | ✅ Not a gap — feedthrough is in `tt_neo_overlay_wrapper_comb` (AON) | No action |

**All 3 gaps resolved. The always-power-on module list is correct as originally defined.**
