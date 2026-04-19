# Step 2.4.2 Implementation Verification Checklist

**Purpose:** Verify Step 2.4.2 RTL implementation is correct before compilation

---

## Pre-Implementation Checklist

### File Location
- [ ] Located `tt_tensix_with_l1.sv` at `/tt_rtl/tt_tensix_neo/src/hardware/tensix/rtl/`
- [ ] Located register block module `tt_register_blocks.sv`
- [ ] Located IP module headers: `tt_sparsity24_decode_engine.sv`, `tt_turboquant_decode_engine.sv`

### Understanding Requirements
- [ ] Read Step 2.4.2 Explained (conceptual understanding)
- [ ] Read Tensix_Cluster_IP_Integration_Implementation (detailed implementation)
- [ ] Read Template vs Real Implementation (common mistakes to avoid)

---

## Signal Declaration Verification

### Location: BEFORE generate block (cluster level)

#### Sparsity Engine Signals
- [ ] `logic [NUM_TENSIX_NEO-1:0] sparsity_ctrl_t sparsity_ctrl;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0] sparsity_zmask_t sparsity_zmask;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0] sparsity_config_t sparsity_config;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0] sparsity_status_t sparsity_status;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0][31:0] sparsity_result_data;` declared

#### Sparsity L1 Interface Signals
- [ ] `logic [NUM_TENSIX_NEO-1:0][15:0] l1_sparsity_addr;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0] l1_sparsity_rd_valid;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0][127:0] sparsity_output_data;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0] sparsity_output_valid;` declared

#### TurboQuant Engine Signals
- [ ] `logic [NUM_TENSIX_NEO-1:0] turboquant_ctrl_t turboquant_ctrl;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0] turboquant_config_t turboquant_config;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0] turboquant_status_t turboquant_status;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0][31:0] turboquant_result_data;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0][31:0] turboquant_scale_output;` declared (scale factor)

#### TurboQuant L1 Interface Signals
- [ ] `logic [NUM_TENSIX_NEO-1:0][15:0] l1_turboquant_addr;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0] l1_turboquant_rd_valid;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0][127:0] turboquant_output_data;` declared
- [ ] `logic [NUM_TENSIX_NEO-1:0] turboquant_output_valid;` declared

---

## Instantiation Verification (Sparsity Engine)

### Location: Inside generate block, after tt_tensix (line ~1234 for i==0)

#### Port Connections - Clock & Reset
- [ ] `.i_clk(i_dm_clk)` — **CRITICAL: NOT i_ai_clk**
- [ ] `.i_rst_n(i_rst_n)` — correct reset signal

#### Port Connections - CSR Interface
- [ ] `.i_ctrl(sparsity_ctrl[i])` — indexed, from register block
- [ ] `.i_zmask(sparsity_zmask[i])` — indexed
- [ ] `.i_config(sparsity_config[i])` — indexed
- [ ] `.o_status(sparsity_status[i])` — indexed, output to register block
- [ ] `.o_result_data(sparsity_result_data[i])` — indexed

#### Port Connections - L1 Memory Interface
- [ ] `.i_l1_data(l1_rd_data[i])` — existing L1 read data signal
- [ ] `.o_l1_addr(l1_sparsity_addr[i])` — request address (indexed)
- [ ] `.o_l1_rd_valid(l1_sparsity_rd_valid[i])` — read strobe (indexed)

#### Port Connections - Output Path
- [ ] `.o_output_data(sparsity_output_data[i])` — indexed
- [ ] `.o_output_valid(sparsity_output_valid[i])` — indexed

#### Module Instantiation Details
- [ ] Module name is `tt_sparsity24_decode_engine` (correct)
- [ ] Instance name is `u_sparsity24_decode_engine_0` for i==0 block
- [ ] Parameters set: `.DATA_WIDTH(128)`, `.NUM_STREAMS(4)`, `.VECTOR_WIDTH(256)`
- [ ] **REPEATED for else block (i >= 1)** with same structure but different instance name

---

## Instantiation Verification (TurboQuant Engine)

### Location: Inside generate block, after Sparsity Engine

#### Port Connections - Clock & Reset
- [ ] `.i_clk(i_dm_clk)` — **CRITICAL: dm_clk, NOT i_ai_clk**
- [ ] `.i_rst_n(i_rst_n)` — correct reset

#### Port Connections - CSR Interface
- [ ] `.i_ctrl(turboquant_ctrl[i])` — indexed
- [ ] `.i_config(turboquant_config[i])` — indexed
- [ ] `.o_status(turboquant_status[i])` — indexed, to register block
- [ ] `.o_result_data(turboquant_result_data[i])` — indexed
- [ ] `.o_scale_output(turboquant_scale_output[i])` — **CRITICAL: Scale factor output**

#### Port Connections - L1 Memory Interface
- [ ] `.i_l1_data(l1_rd_data[i])` — same source as Sparsity
- [ ] `.o_l1_addr(l1_turboquant_addr[i])` — indexed request
- [ ] `.o_l1_rd_valid(l1_turboquant_rd_valid[i])` — indexed strobe

#### Port Connections - Output Path
- [ ] `.o_output_data(turboquant_output_data[i])` — compressed 48-byte data
- [ ] `.o_output_valid(turboquant_output_valid[i])` — indexed valid strobe

#### Module Instantiation Details
- [ ] Module name is `tt_turboquant_decode_engine` (correct)
- [ ] Instance name is `u_turboquant_decode_engine_0` for i==0 block
- [ ] Parameters set: `.DATA_WIDTH(128)`, `.VECTOR_WIDTH(256)`, `.OUTPUT_WIDTH(64)`
- [ ] **REPEATED for else block** with same structure

---

## Port Arbitration Verification

### Location: After both IP instantiations, still inside generate block

#### Arbitration Logic Structure
- [ ] Signal declarations: `logic [15:0] l1_rd_addr_final;` and `logic l1_rd_valid_final;`
- [ ] `always_comb` block for combinational logic (no latency)
- [ ] **Priority order is correct:**
  ```
  if (sparsity_output_valid[i])         // Sparsity priority 1
  else if (turboquant_output_valid[i])  // TurboQuant priority 2
  else                                  // TRISC priority 3
  ```

#### Arbitration Assignments
- [ ] If Sparsity active: 
  - `l1_rd_addr_final = l1_sparsity_addr[i];`
  - `l1_rd_valid_final = l1_sparsity_rd_valid[i];`
- [ ] Else if TurboQuant active:
  - `l1_rd_addr_final = l1_turboquant_addr[i];`
  - `l1_rd_valid_final = l1_turboquant_rd_valid[i];`
- [ ] Else (default TRISC):
  - `l1_rd_addr_final = trisc_l1_rd_addr[i];`
  - `l1_rd_valid_final = trisc_l1_rd_valid[i];`

#### Final Port Assignment
- [ ] `assign l1_rd_addr[i] = l1_rd_addr_final;` — drives L1 port
- [ ] `assign l1_rd_valid[i] = l1_rd_valid_final;` — drives L1 strobe

---

## Register Block Connection Verification

### Location: tt_register_blocks instantiation (in tt_tensix_with_l1.sv)

#### Sparsity CSR Outputs
- [ ] `.o_sparsity_ctrl(sparsity_ctrl)` — output to cluster
- [ ] `.o_sparsity_zmask(sparsity_zmask)` — output to cluster
- [ ] `.o_sparsity_config(sparsity_config)` — output to cluster
- [ ] `.i_sparsity_status(sparsity_status)` — input from cluster
- [ ] `.i_sparsity_result_data(sparsity_result_data)` — input from cluster

#### TurboQuant CSR Outputs
- [ ] `.o_turboquant_ctrl(turboquant_ctrl)` — output to cluster
- [ ] `.o_turboquant_config(turboquant_config)` — output to cluster
- [ ] `.i_turboquant_status(turboquant_status)` — input from cluster
- [ ] `.i_turboquant_result_data(turboquant_result_data)` — input from cluster
- [ ] `.i_turboquant_scale_output(turboquant_scale_output)` — input from cluster

---

## Code Quality Checks

### Clock Domain Compliance
- [ ] IP modules use `i_dm_clk` (NOT `i_ai_clk`)
- [ ] Reason: L1 SRAM operates on dm_clk; TRISC/overlay also use dm_clk for L1
- [ ] CSR signals are stable (set once by firmware), no CDC needed

### Array Indexing Consistency
- [ ] All cluster-level signals in instantiations use `[i]` index
- [ ] No hardcoded array indices (e.g., `[0]`) used for IP signals
- [ ] Enables NUM_TENSIX_NEO scaling (2+ tiles)

### Signal Naming Conventions
- [ ] CSR signals: `sparsity_ctrl`, `turboquant_ctrl` (lowercase, descriptive)
- [ ] L1 interface: `l1_sparsity_addr`, `l1_turboquant_addr` (descriptive)
- [ ] Output signals: `sparsity_output_data`, `turboquant_output_data` (clear)
- [ ] Arbitration: `l1_rd_addr_final`, `l1_rd_valid_final` (indicates arbitration)

### Parameter Values
- [ ] Sparsity: `DATA_WIDTH=128`, `NUM_STREAMS=4`, `VECTOR_WIDTH=256`
- [ ] TurboQuant: `DATA_WIDTH=128`, `VECTOR_WIDTH=256`, `OUTPUT_WIDTH=64`
- [ ] Match documented specifications

---

## Compilation Verification

### Syntax Check
- [ ] RTL compiles without syntax errors
- [ ] No undefined signal errors (all signals declared)
- [ ] No mismatched port widths

### Hierarchical Check
- [ ] IP module definitions found in library
- [ ] Package types exist: `sparsity_ctrl_t`, `sparsity_zmask_t`, `turboquant_ctrl_t`
- [ ] `NUM_TENSIX_NEO` parameter defined and used consistently

### Timing Check
- [ ] L1 arbitration path is combinational (no added latency)
- [ ] CSR to IP path timing verified (ai_clk to dm_clk domain)
- [ ] No timing violations introduced

---

## Functional Verification Checklist

### Firmware-level Tests (Post-Compilation)

#### Sparsity Engine Test
- [ ] TRISC can write sparsity_ctrl (CSR write)
- [ ] TRISC can poll sparsity_status (CSR read)
- [ ] L1 read port arbitrates correctly (Sparsity wins when valid)
- [ ] Zero-mask register controls plane skipping

#### TurboQuant Engine Test
- [ ] TRISC can write turboquant_ctrl (CSR write)
- [ ] TRISC can read turboquant_scale_output (scale factor)
- [ ] L1 read port arbitrates correctly (TurboQuant priority when active)
- [ ] Compressed output validated against expected 48-byte payload

#### Port Arbitration Test
- [ ] When sparsity_output_valid=1: L1 reads from sparsity_addr
- [ ] When turboquant_output_valid=1 (sparsity_output_valid=0): L1 reads from turboquant_addr
- [ ] When both valid=0: TRISC has L1 access
- [ ] No simultaneous L1 address drivers (arbitration works)

#### Integration Test
- [ ] Both Sparsity and TurboQuant instantiated for all tiles
- [ ] Register block connects all CSR signals correctly
- [ ] L1 arbitration mux doesn't create timing violations
- [ ] End-to-end sparsity/TurboQuant operation with firmware

---

## Common Mistakes to Avoid

### ❌ Wrong Clock Domain
```systemverilog
.i_clk(i_ai_clk),  // WRONG! Should be i_dm_clk
```
**Fix:** Always use `i_dm_clk` for IP modules accessing L1

### ❌ Missing Array Indexing
```systemverilog
.i_ctrl(sparsity_ctrl),  // WRONG! Missing [i]
```
**Fix:** Use `sparsity_ctrl[i]` for per-tile indexing

### ❌ Wrong L1 Data Signal
```systemverilog
.i_l1_data(l1_data_out),  // WRONG! Signal name incorrect
```
**Fix:** Use `l1_rd_data[i]` (actual signal in cluster)

### ❌ No Arbitration
```systemverilog
always_comb begin
  l1_rd_addr[i] = l1_sparsity_addr[i];   // From Sparsity
  l1_rd_addr[i] = trisc_l1_rd_addr[i];   // From TRISC (ERROR!)
end
```
**Fix:** Use if/else-if/else to prioritize masters

### ❌ Forgot CSR Connections
```systemverilog
tt_sparsity24_decode_engine u_sparsity (
  .i_clk(i_dm_clk),
  // Missing .i_ctrl, .i_zmask, .i_config (CSR signals!)
  .i_l1_data(l1_rd_data[i]),
  ...
);
```
**Fix:** Always connect all CSR signals from register block

### ❌ Undeclared Signals
```systemverilog
.i_ctrl(sparsity_ctrl[i])  // ERROR: sparsity_ctrl never declared!
```
**Fix:** Declare all cluster-level signals before generate block

---

## Sign-Off Criteria

- [ ] All signal declarations verified
- [ ] Sparsity Engine instantiation correct
- [ ] TurboQuant Engine instantiation correct
- [ ] Port arbitration logic correct
- [ ] Register block CSR connections correct
- [ ] RTL compiles without errors
- [ ] No timing violations (arbitration path combinational)
- [ ] Firmware can access CSR and L1 via IP modules
- [ ] Integration testing passes (Sparsity + TurboQuant + TRISC)
- [ ] Documentation updated with actual implementation

---

## Implementation Timeline

**Estimated effort:** 2–4 hours

1. **Signal Declaration** (30 min): Add cluster-level signals
2. **Sparsity Instantiation** (45 min): Add for i==0 block
3. **Sparsity Repeat** (15 min): Copy to else block
4. **TurboQuant Instantiation** (45 min): Add both blocks
5. **Port Arbitration** (30 min): Add mux logic
6. **Register Block Connection** (30 min): Connect CSR outputs
7. **Compilation & Debug** (30–90 min): Resolve any errors

**Total: 3.5–5 hours (including debug)**

---

## Next Steps After Implementation

1. **Step 2.4.3 — Firmware Integration**
   - Create CSR access code in TRISC firmware
   - Implement polling/handshake protocol for overlay
   - Test compressed data operations

2. **Verification**
   - Testbench: verify size calculation (compressed_data_tracker)
   - Testbench: verify port arbitration behavior
   - Firmware: test end-to-end Sparsity + TurboQuant

3. **Documentation**
   - Update synthesis/place-and-route timing constraints
   - Update design review documentation
   - Create firmware programming guide for new IP

---

## References

- **Tensix_Cluster_IP_Integration_Implementation.md** — detailed RTL patterns
- **Step_2_4_2_Explained.md** — conceptual understanding
- **Step_2_4_2_Template_vs_Implementation.md** — common mistakes
- **Step_2_4_2_RTL_Implementation_Code.sv** — copy-paste ready code
- **Compressed_Data_RTL_Requirements.md** — hardware modules required

---
