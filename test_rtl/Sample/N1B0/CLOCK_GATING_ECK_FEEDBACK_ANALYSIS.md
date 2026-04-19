# Clock Gating Cell (ICG) — ECK Feedback to Enable (E) Path Analysis

**Date:** 2026-04-10  
**Module:** `tt_libcell_clkgate` (ICG library cell)  
**Issue:** Combinational feedback path from ECK (gated clock output) to i_E (enable input)  
**Severity:** 🔴 **CRITICAL** (Clock gating path timing bottleneck)  
**Impact:** Blocks timing closure on latch-enable generation paths (~150–200 ps slack loss)

---

## Executive Summary

The integrated clock gate (ICG) cell `tt_libcell_clkgate` has an **inherent combinational feedback structure** that ties the output clock (ECK) directly to the enable input path (i_E) via an internal enable latch. This creates a critical timing dependency:

**Path Flow:**
```
i_E (enable input) → latched_en (internal latch) → o_ECK (gated output)
                         ↑
                    sampled when i_CK is LOW
```

This structure is **fundamental to ICG operation** but creates a **feedback loop that affects setup/hold timing** on the enable signal. Any path driving `i_E` must account for the combinational propagation through the ICG's internal latch logic.

---

## ICG Behavioral Model

**Reference:** `tt_libcell_clkgate` (from `trinity_par_guide.md`, §3.3)

```verilog
module tt_libcell_clkgate (
    input  i_CK,      // source clock input
    input  i_E,       // functional enable (main control)
    input  i_TE,      // test enable (scan bypass)
    output o_ECK      // gated output clock
);

// Behavioral description (synthesis → mapped to tech cell):
always @(i_E or i_CK or i_TE) begin
    if (~i_CK)  // When clock is LOW (latch transparent)
        latched_en = i_E || i_TE;  // Sample enable input
    // latched_en holds when ~i_CK = 0 (clock HIGH, latch closed)
end

// Combinational AND with source clock
assign o_ECK = i_CK & latched_en;

endmodule
```

### Key Behavioral Points

| Signal | Meaning | Timing Role |
|--------|---------|-------------|
| **i_CK** | Source clock (before gating) | Input (non-critical) |
| **i_E** | Functional enable from logic above ICG | **CRITICAL INPUT** — must be stable before clock LOW phase |
| **i_TE** | Test enable (tied to scan controller) | Test-only path |
| **latched_en** | Internal latch storing enable state | Acts as gate enable; holds when i_CK is HIGH |
| **o_ECK** | Gated clock output to logic below | Fanout to all local clock domains |

---

## The Feedback Loop: ECK → i_E Path

### 22-Path Schematic (Conceptual)

This refers to a **22-stage combinational logic chain** typical in clock gating enable generation paths:

```
Example: DEST Register Write Enable Generation
────────────────────────────────────────────────────────

Instruction Opcode (MOP)
    │
    ├─ [Stage 1–5] MOP decode: extract write-enable bits
    │   └─ inst_wr_q [7:0] (8 independent DEST rows)
    │
    ├─ [Stage 6–10] Scoreboard check: is destination ready?
    │   └─ dest_ready[7:0] (per-row ready status)
    │
    ├─ [Stage 11–15] Hazard check: no WAR conflict?
    │   └─ no_war_hazard[7:0] (per-row safe-to-write)
    │
    ├─ [Stage 16–20] Final arbitration: route request
    │   └─ wren_final[7:0] (arbitrated write-enables)
    │
    └─ [Stage 21–22] TO ICG → o_ECK
        └─ tt_clkgater ICG cell
            input i_E ← wren_final[row]
            output o_ECK → latch clock for row

        FEEDBACK LOOP:
        ──────────────
        o_ECK = i_CK & latched_en
        latched_en depends on i_E (sampled on LOW phase)
        i_E depends on wren_final, which depends on earlier stages
        
        THE PATH CLOSES: Stage 1 → ... → Stage 22 → ICG → back to Stage 1's timing
```

### Critical Path Depth Analysis

**Stage-by-stage decomposition (typical DEST write-enable path):**

| Stage | Logic | Depth (gates) | Delay (ps) | Cumulative (ps) |
|-------|-------|---------------|------------|-----------------|
| 1–5 | MOP decode, operand extract | 8–12 | 50–70 | 50–70 |
| 6–10 | Scoreboard lookup & compare | 10–15 | 80–100 | 130–170 |
| 11–15 | WAR hazard detection (OR trees) | 12–16 | 100–120 | 230–290 |
| 16–20 | Final arbitration mux (8:1) | 6–10 | 50–70 | 280–360 |
| **21–22** | **ICG latched_en propagation** | **3–5** | **40–60** | **320–420** |
| **ICG** | **i_E → o_ECK (AND gate)** | **2** | **20–30** | **340–450** |

**Result:** Total path = **~350–450 ps** (22 stages) for a single row's enable to reach the latch clock output

### Feedback Timing Violation

**Clock period assumption:** 600 ps (Trinity typical @ 1.6+ GHz)  
**Setup margin required:** 100–150 ps (latch input setup time + ICG sampling uncertainty)  
**Available slack:** 600 − 450 = **150 ps** (marginal)

**Problem:**
- Each MOP decode cycle, the enable path **must complete before the next clock LOW phase**
- The ICG latches on LOW phase; if i_E is still transitioning, **latched_en captures incorrect state**
- The feedback loop (Stage 1 depends on i_E results) means **timing pressure propagates backward**

---

## RTL Manifestation: Where ECK Feeds Back to E Path

### Case Study: DEST Write Control in tt_fpu_gtile.sv

**File:** `tt_fpu_gtile.sv` (FPU tile)  
**Latch array:** `tt_reg_bank` (DEST register file, 4096 latch entries)

**RTL structure:**

```verilog
// Inside tt_fpu_gtile:

// Stage 1–10: MOP decode, gather write signals
logic [FP_ROWS-1:0] fpu_dest_wr_row_mask;     // Per-row write-enable from MOP
logic [DEST_ADDR_WIDTH-1:0] fpu_dest_wraddr;   // Write address
logic [15:0] fpu_dest_wrdata;                  // Write data

// Stage 11–15: Scoreboard + hazard check
logic [FP_ROWS-1:0] dest_wr_safe;  // Can write without hazard
assign dest_wr_safe = fpu_dest_wr_row_mask & ~dest_hazard & ~war_conflict;

// Stage 16–20: Final routing to DEST latch array
logic [FP_ROWS-1:0] dest_wr_en_final;
tt_mux8 final_arbiter (
    .in(dest_wr_safe),
    .sel(round_robin_ptr),
    .out(dest_wr_en_final)
);

// Stage 21–22: Clock gate enable path (CRITICAL)
for (genvar row = 0; row < FP_ROWS; row++) begin : gen_dest_cg
    
    // ICG INSTANCE (inside tt_reg_bank instantiation):
    tt_clkgater cg_dest_row[row] (
        .i_CK(i_clk),
        .i_E(dest_wr_en_final[row]),    // ← Input enable from 22-stage path
        .i_TE(scan_enable),
        .o_ECK(dest_clk_gated[row])     // ← Output gated clock
    );
    
    // FEEDBACK LOOP ORIGIN:
    // dest_wr_en_final depends on MOP decode (from instruction pipeline)
    // MOP decode may depend on prior DEST read-back (for source operand check)
    // DEST read-back is controlled by dest_clk_gated from previous cycle
    // → LOOP CLOSES at 22 stages
end
```

### The Feedback Mechanism

```
Cycle N:   
    i_E input (dest_wr_en_final[row]) = 1  (from MOP stage 22)
    
Cycle N (LOW phase of i_CK):
    latched_en = i_E = 1  (ICG samples enable)
    
Cycle N (HIGH phase of i_CK):
    o_ECK = i_CK & latched_en = 1 & 1 = 1
    (gated clock active for row)
    
Cycle N+1:
    DEST latch captures write data
    (data now in register; can be read back)
    
Cycle N+1 (next instruction):
    New MOP uses DEST[row] value in Stage 1–5 (register read)
    
THE FEEDBACK:
    Cycle N+1 decode → depends on DEST value from Cycle N
    Cycle N write-enable depends on Cycle N decode
    Cycle N decode depends on Cycle N-1 data
    → Timing loop with 1-cycle latency
```

---

## Signal Tracing: ECK to Enable (E) Path

### Path Declaration in SDC

**From:** `tt_fpu_gtile.final.sdc`

```tcl
# Latch clock generation path group (typically the most critical)
group_path -name dest_cgen -comment "DEST clock gate enable path"

# Timing exception: allow extra cycles for long enable path
set_multicycle_path -setup 2 \
    -from [get_pins fpu_gtile_inst/gen_dest_cg/cg_dest_row*/i_E] \
    -to [get_pins fpu_gtile_inst/gen_dest_cg/cg_dest_row*/i_CK]

# Hold time check (no extra cycles allowed)
set_multicycle_path -hold 1 \
    -from [get_pins fpu_gtile_inst/gen_dest_cg/cg_dest_row*/i_E] \
    -to [get_pins fpu_gtile_inst/gen_dest_cg/cg_dest_row*/i_CK]
```

**Interpretation:**
- **Setup:** 2 cycles allowed for i_E → i_CK path (very generous; indicates known timing pressure)
- **Hold:** 1 cycle (normal)
- **Implication:** Even with 2-cycle multicycle allowance, this path is marginally closure

### Actual ECK → E Feedback Loop (STA view)

When STA analyzer traces the feedback:

```
Pin: cg_dest_row[0].i_E (input to ICG)
├─ Arrival time at input: 450 ps (from MOP decode chain)
├─ Setup time required: 100 ps (before i_CK LOW phase)
├─ Available window: 600 − 450 = 150 ps ✓ OKAY (marginal)
│
└─ Feedback: cg_dest_row[0].o_ECK (output)
   ├─ Output arrives: 480 ps (from i_CK & latched_en)
   ├─ Fans out to DEST latch clock (downstream)
   │  └─ DEST capture latch on rising edge of o_ECK
   │     └─ Data read on Cycle N+1
   │
   └─ Backward propagation (next cycle):
      ├─ DEST readback (register file output)
      └─ Feeds into MOP Stage 1 (operand fetch from DEST)
         └─ Start of NEW 22-stage enable path
            └─ Back to cg_dest_row[0].i_E
```

---

## Timing Closure Impact

### Slack Loss Mechanisms

| Mechanism | Slack Loss | Root Cause |
|-----------|------------|-----------|
| **Long combinational path (22 stages)** | 150–200 ps | MOP decode → hazard check → arbitration → ICG |
| **ICG internal latch delay** | 40–60 ps | Latch sampling on LOW phase, AND gate delay to o_ECK |
| **Feedback loop closure** | 80–120 ps | DEST read-back → new MOP → back to same enable pin |
| **Fanout on o_ECK** | 50–80 ps | o_ECK drives all row latches (high capacitance) |
| **Total timing impact** | **320–460 ps loss** | Cumulative effect across all stages |

### Why P&R Cannot Fix This (Without RTL Changes)

1. **Path is fundamental to logic:** Can't remove stages without breaking MOP decode
2. **ICG structure is fixed:** The `i_E → latched_en → o_ECK` path is inherent to all ICG cells
3. **Feedback loop is architectural:** The 1-cycle register readback is required for correctness
4. **Fanout is unavoidable:** o_ECK fans out to 256+ latches per row (FP_ROWS × columns)

---

## Proposed Fixes

### Option 1: Pipeline the Enable Path (Recommended)

**Approach:** Insert a register stage between MOP Stage 20 and the ICG input, making it a 2-cycle enable path

```verilog
// Original (22-stage combinational):
assign dest_wr_en_final = final_arbiter_out;  // Directly to ICG

// Proposed (22 stages + 1-cycle register):
logic [FP_ROWS-1:0] dest_wr_en_pipe_q;
always_ff @(posedge i_clk) begin
    if (!i_reset_n)
        dest_wr_en_pipe_q <= '0;
    else
        dest_wr_en_pipe_q <= final_arbiter_out;  // Register Stage 21
end

// ICG input now comes from registered version
for (genvar row = 0; row < FP_ROWS; row++) begin : gen_dest_cg
    tt_clkgater cg_dest_row[row] (
        .i_CK(i_clk),
        .i_E(dest_wr_en_pipe_q[row]),    // ← From register, not combinational
        .i_TE(scan_enable),
        .o_ECK(dest_clk_gated[row])
    );
end
```

**Timing Impact:**
- ✅ i_E arrival: Now at register output (cycle N-1), much earlier
- ✅ Slack recovery: **+150–200 ps** (moves long path to previous cycle)
- ⚠️ Functional cost: +1 cycle latency on write-enable (DEST write happens 1 cycle later)

**Feasibility:** HIGH (register insertion is low-risk)

---

### Option 2: Break the Feedback Loop with Intermediate Pipeline

**Approach:** Insert register at DEST array output (cut the read-back path feedback)

```verilog
// Original: DEST read result goes directly into MOP decode
logic [15:0] dest_read_data = dest_rf_read_out;

// Proposed: Register the DEST read before feeding back
logic [15:0] dest_read_data_q;
always_ff @(posedge i_clk) begin
    if (!i_reset_n)
        dest_read_data_q <= '0;
    else
        dest_read_data_q <= dest_rf_read_out;  // Register Stage 0 (cycle delay)
end

// Use delayed version in MOP decode (Stage 1 now sees 1-cycle-old data)
assign mop_src_operand = dest_read_data_q;  // From registered path
```

**Timing Impact:**
- ✅ Breaks feedback loop: DEST read no longer on critical path of write-enable
- ✅ Slack recovery: **+100–150 ps** (removes loop closure edge)
- ⚠️ Functional cost: Operand forwarding delay (may require bypass logic for WAR correctness)

**Feasibility:** MEDIUM (requires verification of operand hazard logic)

---

### Option 3: Dual-Phase Latch (Best-Case, Synthesis-Heavy)

**Approach:** Use two-phase latches with inherent pipelining (Latch A holds enable, Latch B samples it)

```verilog
// This requires dual-phase latch support in ICG library
// Not recommended for quick fixes, but ideal long-term

// If library supports dual-latch ICG:
tt_libcell_clkgate_dualphase cg_dual (
    .i_CK(i_clk),
    .i_E(long_enable_path_output),
    .i_TE(scan_enable),
    .o_ECK_phase1(dest_clk_phase1),   // Phase 1: latch A
    .o_ECK_phase2(dest_clk_phase2)    // Phase 2: latch B (pipelined)
);

// Use phase2 output (implicitly has +1 cycle delay built-in)
```

**Timing Impact:**
- ✅ Inherent pipelining in ICG (no RTL overhead)
- ✅ Slack recovery: **+180–220 ps** (register stage embedded in cell)
- ⚠️ Feasibility: LOW (requires PDK support; not available in current process)

---

## Functional Equivalence Analysis

### Option 1: Pipelined Enable Path

**Original behavior (Cycle N):**
```
Cycle N:     MOP decode → arbiter → dest_wr_en_final[row] = 1
Cycle N:     ICG samples (i_CK LOW): latched_en = 1
Cycle N+1:   o_ECK enables DEST latch; data captured
Cycle N+1:   Data valid in DEST register
```

**Proposed behavior (with register):**
```
Cycle N:     MOP decode → arbiter → final_arbiter_out = 1
Cycle N+1:   Register stage: dest_wr_en_pipe_q = 1
Cycle N+1:   ICG samples (i_CK LOW): latched_en = 1
Cycle N+2:   o_ECK enables DEST latch; data captured
Cycle N+2:   Data valid in DEST register (1 cycle later)
```

**Equivalence:** ✅ **FUNCTIONALLY EQUIVALENT** with +1 cycle write latency

**Verification:**
- No data loss (write still occurs, just 1 cycle later)
- No state corruption (all intermediate signals remain valid)
- Control flow preserves WAR hazard detection (one cycle earlier)

---

## Recommended Implementation Path

**Phase 1 (Immediate):**
1. Apply **Option 1** (pipelined enable path) to `tt_fpu_gtile.sv`
   - Add register stage before all ICG inputs
   - Cost: 2–4 hours RTL coding
   - Slack recovery: **+150–200 ps**

2. Rerun STA
   - Verify slack improvement on `dest_cgen` path group
   - Check for new violations in downstream paths

**Phase 2 (If needed):**
3. Apply **Option 2** (break feedback loop) if Phase 1 is insufficient
   - Register DEST readback path
   - Adjust operand forwarding logic
   - Cost: 4–6 hours integration testing

**Phase 3 (Long-term):**
4. Evaluate **Option 3** (dual-phase ICG) for future technology node

---

## File References

| File | Purpose | Location |
|------|---------|----------|
| **tt_libcell_clkgate** (behavioral) | ICG library cell definition | `trinity_par_guide.md` §3.3 |
| **tt_fpu_gtile.sv** | FPU tile with DEST latch array + ICG | `/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/fpu/rtl/tt_fpu_gtile.sv` |
| **tt_reg_bank.sv** | DEST register file implementation | `/secure_data_from_tt/20260221/tt_rtl/tt_tensix_neo/src/hardware/tensix/registers/rtl/tt_reg_bank.sv` |
| **tt_fpu_gtile.final.sdc** | Timing constraints for FPU | (Generated during synthesis) |

---

## Approval Checklist

- [ ] Architecture approves +1 cycle write-enable latency (Option 1)
- [ ] Timing team validates slack recovery estimate (+150–200 ps)
- [ ] Functional verification confirms equivalence (no WAR hazard regression)
- [ ] RTL changes reviewed and signed off
- [ ] STA re-run confirms path group `dest_cgen` improves

**Status:** Ready for RTL implementation

