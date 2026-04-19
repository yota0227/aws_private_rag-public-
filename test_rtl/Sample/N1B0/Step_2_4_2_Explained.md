# Step 2.4.2 Explained: Add to Tensix Cluster Hierarchy

**Quick Answer:** Step 2.4.2 means **instantiate your new IP module inside the Tensix cluster container** and connect all signals properly.

---

## What "Add to Tensix Cluster Hierarchy" Means

### Hierarchy Visualization

```
TRINITY SOC (top-level)
  └─ tt_tensix_with_l1 (CLUSTER CONTAINER)
      ├─ L1 SRAM macros (3 MB)
      ├─ tt_instrn_engine (register block)
      │   ├─ CLUSTER_CTRL registers
      │   ├─ T6_L1_CSR registers
      │   ├─ Overlay stream registers
      │   └─ [NEW IP REGISTERS] ← Step 2.4.1
      │
      ├─ tt_tensix #0 (compute core 0)
      │   ├─ TRISC0/1/2/3
      │   ├─ FPU
      │   └─ TDMA
      │
      ├─ tt_tensix #1 (compute core 1)
      │   ├─ TRISC0/1/2/3
      │   ├─ FPU
      │   └─ TDMA
      │
      └─ [NEW IP MODULE] ← Step 2.4.2
          ├─ CSR signals (from register block)
          ├─ L1 memory port (128-bit)
          ├─ Clock/reset
          └─ Output data path
```

---

## The Three Steps of IP Integration (Recap)

### Step 2.4.1: Define CSR Registers
- Create package file with register definitions
- Define address offsets (0x0200–0x07FF reserved in N1B0)
- Specify register fields (control, status, data)
- Create register block module

**Output:** Register definition files + register block module

---

### Step 2.4.2: Instantiate in Cluster ← **YOU ARE HERE**
- Add IP module instantiation to `tt_tensix_with_l1.sv`
- Connect CSR signals from register block
- Connect L1 memory interface (128-bit)
- Connect clock/reset from cluster
- Handle port arbitration (if sharing L1)

**Output:** RTL instantiation in cluster hierarchy

---

### Step 2.4.3: Firmware Integration
- Write CSR access code (TRISC firmware)
- Define polling/handshake protocol
- Create kernel examples

**Output:** Firmware API and test code

---

## How to Implement Step 2.4.2

### File: `/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/tt_tensix_with_l1.sv`

### Location: Inside generate block (~line 1214–1323)

```
if (i == 0) begin : neo
  
  // Step 1: Existing tt_tensix instantiation (UNCHANGED)
  tt_tensix #( )
    u_t6 ( .* );
  
  // Step 2: ADD NEW IP INSTANTIATION HERE
  //         This is Step 2.4.2!
  
  tt_sparsity_engine u_sparsity_engine (
    // ... connections (see below)
  );
  
end
```

### What Signals Must Be Connected?

#### 1. **Clock & Reset**
```systemverilog
.i_clk(i_dm_clk),          // dm_clk (not ai_clk!)
.i_rst_n(i_rst_n),
```

**Why dm_clk?** 
- IP accesses L1 directly
- L1 runs on dm_clk
- TRISC/overlay FSM also use dm_clk for L1 operations

#### 2. **CSR Interface (from register block)**
```systemverilog
.i_ctrl(sparsity_ctrl),          // Control register
.i_zmask(sparsity_zmask),        // Mask register
.i_config(sparsity_config),      // Config register
.o_status(sparsity_status),      // Status output
.o_result_data(sparsity_result_data),  // Result output
```

**Where do these come from?**
```
TRISC writes CSR @ 0x0200
  ↓ (APB bus, ai_clk domain)
tt_register_blocks.sv::u_sparsity_registers
  ↓
Outputs: sparsity_ctrl, sparsity_zmask, etc.
  ↓
Connected to u_sparsity_engine (these are cluster-local signals)
```

**Clock domain crossing?**
- CSR signals originate in ai_clk domain
- Engine uses dm_clk domain
- **CDC NOT needed** — signals are stable (config registers, set once)
- If signals change frequently, add CDC FIFO

#### 3. **L1 Memory Interface**
```systemverilog
.i_l1_data(l1_rd_data[i]),           // Data from L1 SRAM
.o_l1_addr(l1_sparsity_addr[i]),     // Address you request
.o_l1_rd_valid(l1_sparsity_rd_valid[i]),  // Read strobe
```

**How does L1 access work?**
```
IP module outputs address: o_l1_addr = 0x1234
IP module strobes read: o_l1_rd_valid = 1'b1
  ↓
L1 SRAM macro (combinational):
  data = RAM[address]
  ↓
IP module reads: i_l1_data = 128-bit value
  ↓
Next cycle: output the result
```

#### 4. **Output Data Path**
```systemverilog
.o_output_data(sparsity_output[i]),       // Processed result
.o_output_valid(sparsity_output_valid[i])  // Valid strobe
```

**Where does output go?**
```
Option A: Write back to L1 (via arbiter)
Option B: Send to TRISC (via register output)
Option C: Send to overlay stream (for autonomous DMA)
```

---

## Complete Working Example

```systemverilog
// File: tt_tensix_with_l1.sv
// Location: Inside generate block (after tt_tensix instantiation)

if (i == 0) begin : neo

  // ───────────────────────────────────────
  // EXISTING: Tensix compute core
  // ───────────────────────────────────────
  tt_tensix #( )
    u_t6 (
      .i_clk(i_ai_clk),
      .i_reset_n(i_rst_n),
      .t6core_l1_sbank_rw_intf(t6core_l1_sbank_rw_intf[i].initiator),
      .noc_neo_local_regs_intf(noc_neo_local_regs_intf[i]),
      // ... 100+ other signals ...
      .*);
  
  // ═══════════════════════════════════════
  // NEW: Sparsity Engine (Step 2.4.2)
  // ═══════════════════════════════════════
  
  tt_sparsity_engine #(
    .DATA_WIDTH(128),
    .NUM_STREAMS(4),
    .VECTOR_WIDTH(256)
  ) u_sparsity_engine (
    
    // Clock & Reset (dm_clk, NOT ai_clk)
    .i_clk(i_dm_clk),
    .i_rst_n(i_rst_n),
    
    // CSR from register block (stable signals, no CDC)
    .i_ctrl(sparsity_ctrl[i]),
    .i_zmask(sparsity_zmask[i]),
    .i_config(sparsity_config[i]),
    .o_status(sparsity_status[i]),
    .o_result_data(sparsity_result_data[i]),
    
    // L1 memory interface
    .i_l1_data(l1_rd_data[i]),
    .o_l1_addr(l1_sparsity_addr[i]),
    .o_l1_rd_valid(l1_sparsity_rd_valid[i]),
    
    // Output
    .o_output_data(sparsity_output[i]),
    .o_output_valid(sparsity_output_valid[i])
  );

end  // End generate block

else begin : neo
  // ... other instances ...
end
```

---

## Port Arbitration Example

If multiple masters (TRISC, sparsity, TurboQuant) access L1:

```systemverilog
// Inside cluster, after all IP instantiations

// Mux L1 read port among masters
always_comb begin
  if (sparsity_output_valid[i]) begin
    // Sparsity has priority
    l1_rd_addr[i] = l1_sparsity_addr[i];
    l1_rd_valid[i] = l1_sparsity_rd_valid[i];
  end else if (turboquant_output_valid[i]) begin
    // TurboQuant next priority
    l1_rd_addr[i] = l1_tq_addr[i];
    l1_rd_valid[i] = l1_tq_rd_valid[i];
  end else begin
    // Default: TRISC L1 access
    l1_rd_addr[i] = trisc_l1_rd_addr[i];
    l1_rd_valid[i] = trisc_l1_rd_valid[i];
  end
end
```

---

## Critical Mistakes to Avoid

❌ **WRONG:** Connect to i_ai_clk instead of i_dm_clk
```systemverilog
.i_clk(i_ai_clk),  // WRONG! L1 is on dm_clk
```

❌ **WRONG:** Try to write directly to L1 without arbitration
```systemverilog
l1_wr_data = sparsity_output;  // WRONG! No write port allocated
```

❌ **WRONG:** Forget CSR connections
```systemverilog
tt_sparsity_engine u_sparsity (
  .i_clk(i_dm_clk),
  // Missing CSR signals! Firmware can't control it
  .i_l1_data(l1_rd_data),
  ...
);
```

❌ **WRONG:** Use wrong L1 interface signals
```systemverilog
.i_l1_data(trisc_l1_rdata),  // WRONG! That's instruction cache
```

---

## Checklist for Step 2.4.2

- [ ] Find `tt_tensix_with_l1.sv` file
- [ ] Locate generate block (~line 1214–1323)
- [ ] Find where `tt_tensix u_t6` is instantiated
- [ ] Add IP module instantiation **after** tt_tensix instance
- [ ] Connect `.i_clk(i_dm_clk)` ← **NOT i_ai_clk**
- [ ] Connect CSR signals from register block
- [ ] Connect L1 memory interface
- [ ] Verify clock domain (dm_clk for L1, ai_clk for CSR)
- [ ] Add port arbitration if needed
- [ ] Compile and verify module hierarchy

---

## Next Steps

1. **Understand:** Read this file
2. **Detailed Implementation:** See `Tensix_Cluster_IP_Integration_Implementation.md`
3. **Write RTL:** Add instantiation to tt_tensix_with_l1.sv
4. **Compile:** RTL verification
5. **Firmware:** Test with TRISC firmware (Step 2.4.3)

---

**Summary:** Step 2.4.2 = Instantiate your IP in the cluster container, connect all signals, handle clock domains and port arbitration correctly.

