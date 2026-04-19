# Verification Report: edc_mux_demux_sel AON Register Requirement

**Document:** N1B0 NPU ISO Guide Critical Requirement Verification
**Date:** 2026-03-31
**Requirement:** (from N1B0_NPU_ISO_Guide.md §3.1, Group 3, lines 84-87)

> ⚠️ **Critical:** The `i_edc_mux_demux_sel` control driving `edc_muxing_when_harvested` must come from an AON register inside `clock_reset_ctrl`. If it is driven from the powered-off overlay SFR it will float when the tile is off, corrupting the EDC ring for all remaining active tiles.

---

## 1. Current RTL Implementation — Signal Flow

### 1.1 edc_mux_demux_sel Generation Path

**File:** `tt_trin_noc_niu_router_wrap.sv` (line 893)
```systemverilog
assign edc_mux_demux_sel = edc_config_noc_sec.edc_mux_demux_sel;
```

**Source of edc_config_noc_sec (line 806):**
```systemverilog
tt_edc1_noc_sec_controller edc_noc_sec_controller_inst (
    .i_clk            (i_clk),              // noc_clk
    .i_reset_n        (i_reset_n),
    .ingress_intf     (edc_ingress_intf),   // EDC ring input
    .egress_intf      (noc_sec_controller_egress_intf),
    .i_sec_status     (edc_status_noc_sec),
    .o_sec_config     (edc_config_noc_sec)  // ← edc_mux_demux_sel output
);
```

**Module Architecture:**
- `tt_edc1_noc_sec_controller` is a **message parser** — receives EDC ring packets and decodes control register values
- Clocked by `i_clk` (noc_clk domain)
- Output `edc_config_noc_sec` is a combinational decode of received EDC ring message fields
- **No AON register involved** in current implementation

### 1.2 edc_mux_demux_sel Usage

**File:** `tt_trin_noc_niu_router_wrap.sv` (line 773)
```systemverilog
tt_edc1_serial_bus_demux edc_demuxing_when_harvested (
    .i_demux_sel(edc_mux_demux_sel),        // ← control input
    .ingress_intf(noc_niu_router_egress_intf),
    .egress_intf_out0(edc_egress_intf),
    .egress_intf_out1(edc_egress_t6_byp_intf)
);
```

The signal routes the EDC serial bus to either the main overlay core (out0) or the T6 L1 bypass path (out1) during harvest mode.

---

## 2. Module Hierarchy — Power Domain Context

```
trinity (SoC top) [VDDM/VDDN mixed]
  └─ gen_tensix[Y][X] :: tt_tensix_with_l1 [VDDM powered-off core]
      └─ tt_overlay_noc_niu_router [INSIDE overlay — powered-off when tile harvested]
          └─ tt_trin_noc_niu_router_wrap [inside overlay NIU wrapper]
              └─ tt_edc1_noc_sec_controller [noc_clk-clocked EDC message parser]
                  └─ o_sec_config.edc_mux_demux_sel
              └─ tt_edc1_serial_bus_demux [uses edc_mux_demux_sel]
```

**Critical Issue:** `tt_overlay_noc_niu_router` is part of the `tt_overlay_wrapper` overlay core logic. When the Tensix tile is harvested (ISO_EN=1 for that tile), **the entire overlay is powered off (VDDM domain switches off)**. Therefore:

- ✅ ISO cells guard the EDC serial bus inputs (`edc_serial_data`, `edc_serial_valid`, feedback) before `edc_muxing_when_harvested`
- ❌ **BUT:** The `edc_mux_demux_sel` control signal driving the demultiplexer logic **is generated inside the powered-off overlay** (inside `tt_edc1_noc_sec_controller`)
- ❌ **When the tile is harvested, `edc_mux_demux_sel` will float** (no longer driven by the powered-off tt_edc1_noc_sec_controller)

---

## 3. Required Fix — AON Register for edc_mux_demux_sel

### 3.1 Requirement Statement

`edc_mux_demux_sel` **must** be registered in the **always-on (AON/VDDN) domain**, specifically inside `clock_reset_ctrl` or an equivalent AON module. The register should be programmed via the **BIU (Bus Interface Unit)** or **EDC ring** during initialization, **not** read combinationally from the powered-off overlay.

### 3.2 Proposed Implementation

**Option A: Static Register in clock_reset_ctrl (AON)**

Create a persistent AON register in the `clock_reset_ctrl` module:

```systemverilog
// Inside clock_reset_ctrl (always-on, clocked by noc_clk from AON supply VDDN)
always_ff @(posedge i_noc_clk) begin
    if (!i_noc_clk_reset_n) begin
        edc_mux_demux_sel_aon_reg <= 1'b0;  // Default: route to overlay core (non-harvested)
    end else if (biu_wr_en && biu_addr == ADDR_EDC_MUX_DEMUX_SEL) begin
        edc_mux_demux_sel_aon_reg <= biu_wr_data[0];
    end
end

assign o_edc_mux_demux_sel = edc_mux_demux_sel_aon_reg;
```

**Option B: EDC Ring Command to AON Register**

Extend the EDC message protocol to send `edc_mux_demux_sel` updates to a dedicated AON receiver module, bypassing the powered-off overlay entirely.

---

## 4. Clock / Reset Input Verification

### 4.1 EDC Demux Clock / Reset Inputs

**File:** `tt_edc1_serial_bus_demux.sv` (internal module)

The demultiplexer itself is **combinational logic** — no clock input. The mux select (`i_demux_sel`) routes signals based on combinational logic:

```systemverilog
assign egress_intf_out0 = i_demux_sel ? '0 : ingress_intf;  // Route based on sel
assign egress_intf_out1 = i_demux_sel ? ingress_intf : '0;
```

**Issue:** If `i_demux_sel` (the `edc_mux_demux_sel` signal) floats due to powered-off domain:
- Demux behavior becomes unpredictable
- EDC ring packets may be dropped or misrouted
- All downstream EDC nodes lose synchronization

### 4.2 Clock Feedthrough from Powered-Off Domain

**File:** `tt_trin_noc_niu_router_wrap.sv` (line 607–612, clock feedthrough logic)

Currently, the wrapper contains combinational feedthrough for clocks:

```systemverilog
assign o_noc_clk_feedthrough = i_noc_clk;
assign o_ai_clk_feedthrough  = i_ai_clk_feedthrough;
```

These are **NOT isolated by ISO cells** and are **combinational assigns**, so they work even during harvest. However, **control signals like `edc_mux_demux_sel` that depend on powered-off logic must be explicitly protected.**

---

## 5. Verification Checklist

| # | Check | Status | Evidence | Action |
|---|-------|--------|----------|--------|
| 1 | `edc_mux_demux_sel` registered in clock_reset_ctrl (AON) | ❌ FAIL | `tt_edc1_noc_sec_controller` in powered-off overlay | **Implement AON register** |
| 2 | AON register clocked by noc_clk (from AON clock_reset_ctrl) | ⚠️ VERIFY | `i_clk` input to tt_edc1_noc_sec_controller needs trace | **Verify clock source** |
| 3 | AON register reset by noc_clk_reset_n (from AON) | ⚠️ VERIFY | No explicit reset control visible | **Add reset sequencing** |
| 4 | edc_mux_demux_sel input to demux isolated by ISO cell | ✅ PASS | Demux is combinational; sel drives routing logic | — |
| 5 | Harvest activation sequence: ISO_EN first, then overlay power off | ❓ UNKNOWN | UPF/power sequencing not inspected | **Review UPF power domain** |
| 6 | Fallback: edc_mux_demux_sel forced to safe default (0) when harvested | ❌ FAIL | No ISO cell clamping edc_mux_demux_sel itself | **Add ISO cell on control input** |

---

## 6. Recommendations

### 6.1 Immediate (Critical Path)

1. **Create AON register** for `edc_mux_demux_sel` in `clock_reset_ctrl` module:
   - Register location: Always-on supply (VDDN)
   - Register clock: `noc_clk` from AON clock_reset_ctrl
   - Register reset: `noc_clk_reset_n` from AON
   - Write path: BIU APB interface or EDC ring command

2. **Route AON register output** to `tt_overlay_noc_niu_router`:
   - Input port: `i_edc_mux_demux_sel_from_aon`
   - Connect to `tt_trin_noc_niu_router_wrap.i_edc_mux_demux_sel`
   - Remove internal EDC controller decode

3. **Add ISO cell** on the demux select input:
   - Type: AND-type isolation (clamp-to-0)
   - Input: `edc_mux_demux_sel` from AON register (via internal wire)
   - Output: to `tt_edc1_serial_bus_demux.i_demux_sel`
   - ISO_EN: Same as other Tensix tile ISO cells

### 6.2 Secondary (Verification)

1. Review **UPF (Unified Power Format)** to confirm:
   - `clock_reset_ctrl` is in VDDN always-on domain
   - `tt_overlay_noc_niu_router` is in VDDM powered-off domain
   - Power sequencing: VDDN remains on when VDDM powers off

2. Update **SFR register map** to include `EDC_MUX_DEMUX_SEL` control register in clock_reset_ctrl:
   - Address: TBD (consult SFR guide)
   - Type: RW, sticky across harvest
   - Default: 0 (route to overlay core, non-harvested behavior)

3. Add **SDC/UPF assertions** to catch:
   - `edc_mux_demux_sel` driven from powered-off domain → error
   - ISO cell missing on demux select → lint warning

---

## 7. Conclusion

**Current State:** ❌ **DOES NOT MEET REQUIREMENT**

The `edc_mux_demux_sel` signal is currently generated **inside the powered-off overlay wrapper** by the EDC message controller (`tt_edc1_noc_sec_controller`). When the Tensix tile is harvested, this signal will lose its driver and float, violating the ISO_Guide requirement that it must come from an AON register in `clock_reset_ctrl`.

**Required Changes:**
- Implement AON register for `edc_mux_demux_sel` in `clock_reset_ctrl` (VDDN always-on)
- Route the AON register output to the demux inside the powered-off overlay
- Add ISO cell to clamp the select input when the tile is harvested

**Before Sign-Off:** Verify UPF power domain assignments and update hierarchy documentation.

---

