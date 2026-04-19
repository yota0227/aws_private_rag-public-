# Step 2.4.2 Patch Guide: Exact Line-by-Line Modifications

**File:** `tt_tensix_with_l1.sv`  
**Location:** `/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_tensix_with_l1.sv`

**Purpose:** This document shows EXACTLY what to add and where, using line numbers from the current RTL.

---

## MODIFICATION 1: Add Signal Declarations at Cluster Level

**Location:** ~Line 1110 (after line 1119: `wire [NUM_TENSIX_NEO-1:0][11+$clog2(THREAD_COUNT):0] report_safety_position;`)

**ADD:**
```systemverilog
// ═════════════════════════════════════════════════════════════════════
// Step 2.4.2: Sparsity Engine and TurboQuant Engine Signals
// ═════════════════════════════════════════════════════════════════════

// CSR signals from register block (from Step 2.4.1)
logic [NUM_TENSIX_NEO-1:0]                sparsity_ctrl_t   sparsity_ctrl;
logic [NUM_TENSIX_NEO-1:0]                sparsity_zmask_t  sparsity_zmask;
logic [NUM_TENSIX_NEO-1:0]                sparsity_config_t sparsity_config;
logic [NUM_TENSIX_NEO-1:0]                sparsity_status_t sparsity_status;
logic [NUM_TENSIX_NEO-1:0][31:0]          sparsity_result_data;

// TurboQuant CSR signals
logic [NUM_TENSIX_NEO-1:0]                turboquant_ctrl_t   turboquant_ctrl;
logic [NUM_TENSIX_NEO-1:0]                turboquant_config_t turboquant_config;
logic [NUM_TENSIX_NEO-1:0]                turboquant_status_t turboquant_status;
logic [NUM_TENSIX_NEO-1:0][31:0]          turboquant_result_data;
logic [NUM_TENSIX_NEO-1:0][31:0]          turboquant_scale_output;

// Sparsity Engine L1 interface
logic [NUM_TENSIX_NEO-1:0][15:0]          l1_sparsity_addr;
logic [NUM_TENSIX_NEO-1:0]                l1_sparsity_rd_valid;
logic [NUM_TENSIX_NEO-1:0][127:0]         sparsity_output_data;
logic [NUM_TENSIX_NEO-1:0]                sparsity_output_valid;

// TurboQuant Engine L1 interface
logic [NUM_TENSIX_NEO-1:0][15:0]          l1_turboquant_addr;
logic [NUM_TENSIX_NEO-1:0]                l1_turboquant_rd_valid;
logic [NUM_TENSIX_NEO-1:0][127:0]         turboquant_output_data;
logic [NUM_TENSIX_NEO-1:0]                turboquant_output_valid;

// ═════════════════════════════════════════════════════════════════════
```

**Before line:** `generate`

---

## MODIFICATION 2: Add Sparsity + TurboQuant Engines for i==0 Block

**Location:** Lines 1233–1235 (AFTER tt_tensix instantiation closes)

**CURRENT CODE (lines 1233–1235):**
```systemverilog
    .*,     // Line 1229 (end of tt_tensix ports)
    
    .SFR_RA1_HS_MCS(SFR_RA1_HS_MCS_ts1[i * 2 + 1 : i * 2]), ...);  // Line 1233

end  // Line 1235: Closes if (i == 0) block
```

**REPLACE with:**
```systemverilog
    .*,     // Line 1229 (unchanged)
    
    .SFR_RA1_HS_MCS(SFR_RA1_HS_MCS_ts1[i * 2 + 1 : i * 2]), ...);  // Line 1233

      // ═════════════════════════════════════════════════════════════════
      // Step 2.4.2: Sparsity24 Encode Engine Instantiation
      // ═════════════════════════════════════════════════════════════════

      tt_sparsity24_encode_engine #(
        .DATA_WIDTH(128),
        .NUM_STREAMS(4),
        .VECTOR_WIDTH(256)
      ) u_sparsity24_encode_engine_0 (
        .i_clk(i_ai_clk[i]),    // ai_clk (T6 L1 access, same as TRISC)
        .i_rst_n(i_rst_n),
        .i_ctrl(sparsity_ctrl[i]),
        .i_zmask(sparsity_zmask[i]),
        .i_config(sparsity_config[i]),
        .o_status(sparsity_status[i]),
        .o_result_data(sparsity_result_data[i]),
        .i_l1_data(l1_rd_data[i]),
        .o_l1_addr(l1_sparsity_addr[i]),
        .o_l1_rd_valid(l1_sparsity_rd_valid[i]),
        .o_output_data(sparsity_output_data[i]),
        .o_output_valid(sparsity_output_valid[i])
      );

      // ═════════════════════════════════════════════════════════════════
      // Step 2.4.2: TurboQuant Decode Engine Instantiation
      // ═════════════════════════════════════════════════════════════════

      tt_turboquant_decode_engine #(
        .DATA_WIDTH(128),
        .VECTOR_WIDTH(256),
        .OUTPUT_WIDTH(64)
      ) u_turboquant_decode_engine_0 (
        .i_clk(i_ai_clk[i]),    // ai_clk (T6 L1 access, same as TRISC)
        .i_rst_n(i_rst_n),
        .i_ctrl(turboquant_ctrl[i]),
        .i_config(turboquant_config[i]),
        .o_status(turboquant_status[i]),
        .o_result_data(turboquant_result_data[i]),
        .o_scale_output(turboquant_scale_output[i]),
        .i_l1_data(l1_rd_data[i]),
        .o_l1_addr(l1_turboquant_addr[i]),
        .o_l1_rd_valid(l1_turboquant_rd_valid[i]),
        .o_output_data(turboquant_output_data[i]),
        .o_output_valid(turboquant_output_valid[i])
      );

      // ═════════════════════════════════════════════════════════════════
      // Port Arbitration: L1 Read Port
      // ═════════════════════════════════════════════════════════════════

      logic [15:0]  l1_rd_addr_final;
      logic         l1_rd_valid_final;

      always_comb begin
        if (sparsity_output_valid[i]) begin
          l1_rd_addr_final = l1_sparsity_addr[i];
          l1_rd_valid_final = l1_sparsity_rd_valid[i];
        end else if (turboquant_output_valid[i]) begin
          l1_rd_addr_final = l1_turboquant_addr[i];
          l1_rd_valid_final = l1_turboquant_rd_valid[i];
        end else begin
          l1_rd_addr_final = trisc_l1_rd_addr[i];
          l1_rd_valid_final = trisc_l1_rd_valid[i];
        end
      end

      assign l1_rd_addr[i] = l1_rd_addr_final;
      assign l1_rd_valid[i] = l1_rd_valid_final;

end  // Line 1235: Closes if (i == 0) block
```

---

## MODIFICATION 3: Add Same Engines to else Block

**Location:** Lines 1353–1355 (AFTER second tt_tensix instantiation closes)

**CURRENT CODE (lines 1353–1355):**
```systemverilog
    .SFR_RF1_HS_MCSW(SFR_RF1_HS_MCSW_ts2[i * 1]), ...);  // Line 1353

end  // Line 1355: Closes else block
```

**ADD (SAME as MODIFICATION 2):**
```systemverilog
    .SFR_RF1_HS_MCSW(SFR_RF1_HS_MCSW_ts2[i * 1]), ...);  // Line 1353

      // ═════════════════════════════════════════════════════════════════
      // Step 2.4.2: Sparsity24 Encode Engine Instantiation
      // ═════════════════════════════════════════════════════════════════

      tt_sparsity24_encode_engine #(
        .DATA_WIDTH(128),
        .NUM_STREAMS(4),
        .VECTOR_WIDTH(256)
      ) u_sparsity24_encode_engine (
        .i_clk(i_ai_clk[i]),    // ai_clk (T6 L1 access, same as TRISC)
        .i_rst_n(i_rst_n),
        .i_ctrl(sparsity_ctrl[i]),
        .i_zmask(sparsity_zmask[i]),
        .i_config(sparsity_config[i]),
        .o_status(sparsity_status[i]),
        .o_result_data(sparsity_result_data[i]),
        .i_l1_data(l1_rd_data[i]),
        .o_l1_addr(l1_sparsity_addr[i]),
        .o_l1_rd_valid(l1_sparsity_rd_valid[i]),
        .o_output_data(sparsity_output_data[i]),
        .o_output_valid(sparsity_output_valid[i])
      );

      // ═════════════════════════════════════════════════════════════════
      // Step 2.4.2: TurboQuant Decode Engine Instantiation
      // ═════════════════════════════════════════════════════════════════

      tt_turboquant_decode_engine #(
        .DATA_WIDTH(128),
        .VECTOR_WIDTH(256),
        .OUTPUT_WIDTH(64)
      ) u_turboquant_decode_engine (
        .i_clk(i_ai_clk[i]),    // ai_clk (T6 L1 access, same as TRISC)
        .i_rst_n(i_rst_n),
        .i_ctrl(turboquant_ctrl[i]),
        .i_config(turboquant_config[i]),
        .o_status(turboquant_status[i]),
        .o_result_data(turboquant_result_data[i]),
        .o_scale_output(turboquant_scale_output[i]),
        .i_l1_data(l1_rd_data[i]),
        .o_l1_addr(l1_turboquant_addr[i]),
        .o_l1_rd_valid(l1_turboquant_rd_valid[i]),
        .o_output_data(turboquant_output_data[i]),
        .o_output_valid(turboquant_output_valid[i])
      );

      // ═════════════════════════════════════════════════════════════════
      // Port Arbitration: L1 Read Port
      // ═════════════════════════════════════════════════════════════════

      logic [15:0]  l1_rd_addr_final;
      logic         l1_rd_valid_final;

      always_comb begin
        if (sparsity_output_valid[i]) begin
          l1_rd_addr_final = l1_sparsity_addr[i];
          l1_rd_valid_final = l1_sparsity_rd_valid[i];
        end else if (turboquant_output_valid[i]) begin
          l1_rd_addr_final = l1_turboquant_addr[i];
          l1_rd_valid_final = l1_turboquant_rd_valid[i];
        end else begin
          l1_rd_addr_final = trisc_l1_rd_addr[i];
          l1_rd_valid_final = trisc_l1_rd_valid[i];
        end
      end

      assign l1_rd_addr[i] = l1_rd_addr_final;
      assign l1_rd_valid[i] = l1_rd_valid_final;

end  // Line 1355: Closes else block
```

**Note:** Instance names changed from `u_sparsity24_encode_engine_0`/`u_turboquant_decode_engine_0` to `u_sparsity24_encode_engine`/`u_turboquant_decode_engine` (without _0 suffix) since this is the else block.

---

## MODIFICATION 4: Update Register Block Instantiation

**Location:** Find `tt_register_blocks u_register_blocks (` instantiation (around line ~1600–1800)

**ADD these port connections:**

```systemverilog
  // ═════════════════════════════════════════════════════════════════
  // Step 2.4.1 Sparsity Register Block Outputs
  // ═════════════════════════════════════════════════════════════════
  .o_sparsity_ctrl(sparsity_ctrl),
  .o_sparsity_zmask(sparsity_zmask),
  .o_sparsity_config(sparsity_config),
  .i_sparsity_status(sparsity_status),
  .i_sparsity_result_data(sparsity_result_data),

  // ═════════════════════════════════════════════════════════════════
  // Step 2.4.1 TurboQuant Register Block Outputs
  // ═════════════════════════════════════════════════════════════════
  .o_turboquant_ctrl(turboquant_ctrl),
  .o_turboquant_config(turboquant_config),
  .i_turboquant_status(turboquant_status),
  .i_turboquant_result_data(turboquant_result_data),
  .i_turboquant_scale_output(turboquant_scale_output),
```

**Where to add:** Inside the `tt_register_blocks` instantiation, after existing connections (find a good spot with similar comment blocks).

---

## Summary of Changes

| Item | Count | Location |
|------|-------|----------|
| Signal declarations | 24 signals | ~Line 1120 (cluster level) |
| Sparsity Engine instantiation (i==0) | 1 instance | ~Line 1234 |
| TurboQuant Engine instantiation (i==0) | 1 instance | ~Line 1234 |
| Port arbitration mux (i==0) | 1 block | ~Line 1234 |
| Sparsity Engine instantiation (else) | 1 instance | ~Line 1354 |
| TurboQuant Engine instantiation (else) | 1 instance | ~Line 1354 |
| Port arbitration mux (else) | 1 block | ~Line 1354 |
| Register block CSR connections | 10 ports | Register block instantiation |
| **Total new lines** | **~200 lines** | Across 4 locations |

---

## Verification After Patching

```bash
# 1. Check syntax
verilator --cc tt_tensix_with_l1.sv

# 2. Check for undefined signals
grep -n "sparsity_ctrl\|turboquant_ctrl\|l1_sparsity" tt_tensix_with_l1.sv

# 3. Verify generate block structure
grep -n "generate\|for\|if\|else\|end\|endgenerate" tt_tensix_with_l1.sv | grep -E "1121|1122|1124|1235|1237|1355|1357|1359"

# 4. Check clock domain usage
grep -n "i_dm_clk\|i_ai_clk" tt_tensix_with_l1.sv | grep -E "sparsity_engine|turboquant_engine"
```

---

## Rollback Instructions

If implementation needs to be reverted:

```bash
# 1. Remove signal declarations (lines ~1120–1145)
# 2. Remove Sparsity/TurboQuant from i==0 block (lines ~1234–1293)
# 3. Remove Sparsity/TurboQuant from else block (lines ~1354–1413)
# 4. Remove CSR connections from register block instantiation
# 5. Verify generate block structure is intact
```

---

## Next Steps

1. Apply patches in order: MODIFICATION 1 → 2 → 3 → 4
2. Compile RTL: `verilator --cc tt_tensix_with_l1.sv`
3. Fix any undefined signal errors
4. Run synthesis tool to check timing
5. Proceed to Step 2.4.3 (Firmware Integration)

---

## References

- **Complete code:** `Step_2_4_2_RTL_Implementation_Code.sv`
- **Verification checklist:** `Step_2_4_2_Implementation_Verification.md`
- **Conceptual guide:** `Step_2_4_2_Explained.md`

---
