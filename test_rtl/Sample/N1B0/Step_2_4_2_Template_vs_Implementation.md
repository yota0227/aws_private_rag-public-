# Step 2.4.2: Template vs Real Implementation

**Purpose:** Show the difference between the simplified template in IP_Design_Guide.md and what actually needs to be done in RTL.

---

## Side-by-Side Comparison

### TEMPLATE (from IP_Design_Guide.md Section 2.4.2)

```systemverilog
// Simple template - shows concept only
tt_sparsity_engine #(
  .DATA_WIDTH(128),
  .NUM_STREAMS(4),
  .VECTOR_WIDTH(256)
) u_sparsity_engine (
  .i_clk(i_dm_clk),
  .i_rst_n(i_rst_n),
  
  .i_ctrl(sparsity_ctrl),
  .i_zmask(sparsity_zmask),
  .i_config(sparsity_config),
  .o_status(sparsity_status),
  .o_result_data(sparsity_result_data),
  
  .i_l1_data(l1_data_out),
  .o_l1_addr(l1_addr_sparsity),
  .o_l1_rd_valid(l1_rd_valid_sparsity),
  
  .o_output_data(sparsity_output),
  .o_output_valid(sparsity_output_valid)
);
```

**Problems with template:**
- ❓ Where do `sparsity_ctrl`, `sparsity_zmask` come from?
- ❓ Where is `l1_data_out` in the cluster?
- ❓ How does L1 arbitration work?
- ❓ Where do we put this code?
- ❓ How are signals declared at cluster level?

---

## REAL IMPLEMENTATION (what actually goes in tt_tensix_with_l1.sv)

### Prerequisite: Signal Declarations at Cluster Level

```systemverilog
// File: tt_tensix_with_l1.sv
// Location: Inside module, before generate blocks

// ═══════════════════════════════════════════════════════
// Step 2.4.1: Register block signals (from CSR)
// ═══════════════════════════════════════════════════════

// These are OUTPUT signals from tt_register_blocks.sv
// Must be declared at cluster level to be accessible to IP

logic [NUM_TENSIX_NEO-1:0]                sparsity_ctrl_t   sparsity_ctrl;
logic [NUM_TENSIX_NEO-1:0]                sparsity_zmask_t  sparsity_zmask;
logic [NUM_TENSIX_NEO-1:0]                sparsity_config_t sparsity_config;
logic [NUM_TENSIX_NEO-1:0]                sparsity_status_t sparsity_status;
logic [NUM_TENSIX_NEO-1:0][31:0]          sparsity_result_data;

// ═══════════════════════════════════════════════════════
// Step 2.4.2: IP module interface signals
// ═══════════════════════════════════════════════════════

// L1 read interface (from IP to L1)
logic [NUM_TENSIX_NEO-1:0][15:0]          l1_sparsity_addr;
logic [NUM_TENSIX_NEO-1:0]                l1_sparsity_rd_valid;

// Output from sparsity engine
logic [NUM_TENSIX_NEO-1:0][127:0]         sparsity_output_data;
logic [NUM_TENSIX_NEO-1:0]                sparsity_output_valid;

// L1 data (already declared for TRISC use)
// logic [NUM_TENSIX_NEO-1:0][127:0]      l1_rd_data;  // From L1 SRAM

// ═══════════════════════════════════════════════════════
// Sparsity output register (if writing back to L1)
// ═══════════════════════════════════════════════════════

logic [NUM_TENSIX_NEO-1:0][127:0]         sparsity_l1_wr_data;
logic [NUM_TENSIX_NEO-1:0]                sparsity_l1_wr_valid;
```

### Inside Generate Block

```systemverilog
// Location: tt_tensix_with_l1.sv, lines ~1214–1323

generate
  for (int unsigned i = 0; i < NUM_TENSIX_NEO; i++) begin : gen_tensix_neo
  
    if (i == 0) begin : neo
      
      // ─────────────────────────────────────────────────────
      // EXISTING: tt_tensix instantiation (UNCHANGED)
      // ─────────────────────────────────────────────────────
      
      tt_tensix #(
        // ... parameters ...
      ) u_t6 (
        .i_neo_instance(neo_instance[i]),
        .i_clk(ai_clk_gated_l1[0]),
        .i_risc_reset_n(t6_risc_reset_n[0]),
        .i_reset_n(ai_clk_reset_n[i]),
        .i_tensix_id(static_tensix_id[i]),
        
        // L1 interfaces (to cluster-level L1)
        .t6core_l1_sbank_rw_intf(t6core_l1_sbank_rw_intf.initiator),
        .t6core_l1_arb_rw_intf(t6core_l1_arb_rw_intf.initiator),
        .t6core_l1_sbank_rd_intf(t6core_l1_sbank_rd_intf.initiator),
        .t6core_l1_arb_rd_intf(t6core_l1_arb_rd_intf.initiator),
        .t6core_l1_sbank_wr_intf(t6core_l1_sbank_wr_intf.initiator),
        .t6core_l1_arb_wr_intf(t6core_l1_arb_wr_intf.initiator),
        
        // Register block interface (CSR)
        .noc_neo_local_regs_intf(noc_neo_local_regs_intf[i]),
        
        // ... other signals (unchanged) ...
        .*
      );
      
      // ═════════════════════════════════════════════════════
      // NEW: Sparsity Engine Instantiation
      // ═════════════════════════════════════════════════════
      
      tt_sparsity_engine #(
        .DATA_WIDTH(128),
        .NUM_STREAMS(4),
        .VECTOR_WIDTH(256)
      ) u_sparsity_engine_0 (
        
        // ─────────────────────────────────────────────────
        // Clock & Reset
        // ─────────────────────────────────────────────────
        .i_clk(i_dm_clk),                   // dm_clk (L1 clock)
        .i_rst_n(i_rst_n),
        
        // ─────────────────────────────────────────────────
        // CSR Interface
        // From register block (output at cluster level)
        // ─────────────────────────────────────────────────
        .i_ctrl(sparsity_ctrl[i]),          // From register block
        .i_zmask(sparsity_zmask[i]),
        .i_config(sparsity_config[i]),
        .o_status(sparsity_status[i]),      // Back to register block
        .o_result_data(sparsity_result_data[i]),
        
        // ─────────────────────────────────────────────────
        // L1 Memory Interface (128-bit)
        // ─────────────────────────────────────────────────
        .i_l1_data(l1_rd_data[i]),          // From L1 SRAM
        .o_l1_addr(l1_sparsity_addr[i]),    // Address request
        .o_l1_rd_valid(l1_sparsity_rd_valid[i]),  // Read strobe
        
        // ─────────────────────────────────────────────────
        // Output Data Path
        // ─────────────────────────────────────────────────
        .o_output_data(sparsity_output_data[i]),
        .o_output_valid(sparsity_output_valid[i])
      );
      
      // ═════════════════════════════════════════════════════
      // PORT ARBITRATION: Mux L1 read port
      // ═════════════════════════════════════════════════════
      // If multiple masters access L1 read port, need arbitration
      
      logic [15:0]  l1_rd_addr_final;
      logic         l1_rd_valid_final;
      
      always_comb begin
        // Priority: Sparsity > TurboQuant > TRISC
        
        if (sparsity_output_valid[i]) begin
          // Sparsity engine is active
          l1_rd_addr_final = l1_sparsity_addr[i];
          l1_rd_valid_final = l1_sparsity_rd_valid[i];
        end else begin
          // TRISC has L1 access
          l1_rd_addr_final = trisc_l1_rd_addr[i];
          l1_rd_valid_final = trisc_l1_rd_valid[i];
        end
      end
      
      // ═════════════════════════════════════════════════════
      // L1 Read Port Assignment
      // ═════════════════════════════════════════════════════
      assign l1_rd_addr[i] = l1_rd_addr_final;
      assign l1_rd_valid[i] = l1_rd_valid_final;
      
    end  // if (i == 0)
    
    else begin : neo
      // ... other tensix instances (unchanged) ...
    end
    
  end  // for loop
  
endgenerate
```

### Connect CSR Outputs (in tt_register_blocks.sv instantiation)

```systemverilog
// Inside tt_register_blocks instantiation (still in tt_tensix_with_l1.sv)

tt_register_blocks u_register_blocks (
  .i_cfg_clk(i_ai_clk),
  .i_cfg_reset_n(i_rst_n),
  
  // ... existing signals ...
  
  // ═════════════════════════════════════════════════════
  // Sparsity Register Block Outputs
  // Connect these to the signals declared above
  // ═════════════════════════════════════════════════════
  
  .o_sparsity_ctrl(sparsity_ctrl),
  .o_sparsity_zmask(sparsity_zmask),
  .o_sparsity_config(sparsity_config),
  .i_sparsity_status(sparsity_status),
  .i_sparsity_result_data(sparsity_result_data),
  
  // ... other register outputs ...
);
```

---

## What's Different from Template?

| Aspect | Template | Real Implementation |
|--------|----------|-------------------|
| **Signal Declaration** | Assumed to exist | Must declare at cluster level |
| **Register Block Signals** | Just shows i_ctrl/i_zmask | Shows where they come from (register block outputs) |
| **L1 Data Source** | "l1_data_out" | "l1_rd_data[i]" (actual signal in cluster) |
| **Arbitration** | Not shown | Implemented mux logic |
| **Placement** | Just "in cluster" | Exact location: inside generate loop, after tt_tensix |
| **Clock Domain** | Listed | Explained: dm_clk for L1, ai_clk for CSR |
| **Port Connection** | Simplified | Shows array indexing [i] |

---

## Common Integration Mistakes & Fixes

### ❌ MISTAKE 1: Signal doesn't exist
```systemverilog
// Template shows:
.i_ctrl(sparsity_ctrl),

// But sparsity_ctrl is never declared!
```

**Fix:**
```systemverilog
// At cluster level (before generate blocks):
logic [NUM_TENSIX_NEO-1:0] sparsity_ctrl_t sparsity_ctrl;

// In register block instantiation:
.o_sparsity_ctrl(sparsity_ctrl),
```

---

### ❌ MISTAKE 2: Wrong clock domain
```systemverilog
// Template shows dm_clk, but CSR signals are ai_clk!
.i_clk(i_dm_clk),  // IP clock
.i_ctrl(sparsity_ctrl),  // CSR comes from ai_clk domain

// Problem: Cross-domain signals without CDC
```

**Fix:**
```systemverilog
// CSR signals are stable (set once), so no CDC needed
// OR add CDC FIFO if signals change frequently:

tt_cdc_fifo #(...) u_cdc_ctrl (
  .i_wr_clk(i_ai_clk),
  .i_wr_data(sparsity_ctrl_ai),
  .i_rd_clk(i_dm_clk),
  .o_rd_data(sparsity_ctrl_dm),
  ...
);
```

---

### ❌ MISTAKE 3: L1 signal name wrong
```systemverilog
// Wrong:
.i_l1_data(l1_data_out),  // This signal doesn't exist!

// Correct:
.i_l1_data(l1_rd_data[i]),  // Actual L1 read data signal
```

---

### ❌ MISTAKE 4: No arbitration
```systemverilog
// Two masters try to write l1_rd_addr at same time:

always_comb begin
  l1_rd_addr[i] = l1_sparsity_addr[i];  // From sparsity
  l1_rd_addr[i] = trisc_l1_rd_addr[i];  // From TRISC (ERROR!)
end

// Result: Last assignment wins, inconsistent behavior
```

**Fix:**
```systemverilog
// Use if-else to prioritize:
always_comb begin
  if (sparsity_output_valid[i]) begin
    l1_rd_addr[i] = l1_sparsity_addr[i];
  end else begin
    l1_rd_addr[i] = trisc_l1_rd_addr[i];
  end
end
```

---

## Verification Checklist

Use this to verify your implementation:

- [ ] **Signal Declaration:** All signals used in instantiation are declared
- [ ] **Clock Domain:** `.i_clk` connected to `i_dm_clk` (NOT `i_ai_clk`)
- [ ] **CSR Source:** CSR signals come from `u_register_blocks` outputs
- [ ] **L1 Source:** L1 data comes from `l1_rd_data[i]` (existing signal)
- [ ] **Port Arbitration:** If multiple masters, have if-else mux logic
- [ ] **Array Indexing:** All signals use [i] index for per-tile arrays
- [ ] **Compile Test:** RTL compiles without undefined signal errors
- [ ] **Functional Test:** Firmware can read/write CSR via TRISC

---

## Summary

**Template:** Shows the concept and what signals are needed.

**Real Implementation:** Adds signal declarations, connects to actual cluster signals, implements arbitration, places code at correct location in hierarchy, and handles clock domains properly.

Use the template to understand the concept, then follow the real implementation pattern for actual RTL.

