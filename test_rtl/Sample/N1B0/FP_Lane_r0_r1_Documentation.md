# FP-Lane r0 vs r1: Exact Meaning and Architecture

**Date:** 2026-04-04  
**Purpose:** Clarify the semantic meaning of r0 and r1 in FP-Lane instantiation

---

## What Are r0 and r1?

### Direct Answer from RTL

In `tt_fpu_tile.sv`:

```systemverilog
u_fp_lane_r0 #(.LANE_ID(0)) (...)    // Line 1139
u_fp_lane_r1 #(.LANE_ID(1)) (...)    // Line 1214
```

Each FP-Tile row instantiates TWO independent FP-Lane units:
- **r0**: FP-Lane with LANE_ID = 0 (first lane)
- **r1**: FP-Lane with LANE_ID = 1 (second lane)

### Naming Convention

**r0 and r1 are NOT "negative latch" and "positive latch"**

Instead:
- **r** likely stands for "row" (as in FP-Tile row)
- **0 and 1** are the two lane indices within each row
- The actual latch phases (negative/positive) are handled by ICG (Integrated Clock Gate) internal to the latches, NOT by these lane instances

---

## Architecture: Two FP-Lanes per FP-Tile Row

### Hierarchical Structure

```
┌──────────────────────────────────────────────────────────┐
│                    FP-Tile (Row, Column)                 │
│                                                          │
│  Shared Register Files (Latch Arrays)                    │
│  ┌──────────────────────────────────────────────────┐   │
│  │  SRCA[rr][col]     SRCB[rr][col]   DEST[rr][col]│   │
│  │  (8 columns)       (8 columns)     (8 columns)  │   │
│  │                                                  │   │
│  │  ICG Latch Phases:                              │   │
│  │  • Phase 1 (Clock LOW):  Transparent            │   │
│  │  • Phase 2 (Clock HIGH): Opaque/Hold            │   │
│  └────────┬─────────────────────────────┬──────────┘   │
│           │                             │               │
│           ├─→ Row Remapping Logic      │               │
│           │   (Phase 2: rr + 256)       │               │
│           │                             │               │
│  ┌────────▼────────┐          ┌────────▼────────┐     │
│  │ FP-Lane r0      │          │ FP-Lane r1      │     │
│  │ (LANE_ID=0)     │          │ (LANE_ID=1)     │     │
│  │                 │          │                 │     │
│  │ ┌─────────────┐ │          │ ┌─────────────┐ │     │
│  │ │Booth Mult   │ │          │ │Booth Mult   │ │     │
│  │ │(NUM_PAIR=8) │ │          │ │(NUM_PAIR=8) │ │     │
│  │ │8 partial    │ │          │ │8 partial    │ │     │
│  │ │products     │ │          │ │products     │ │     │
│  │ └─────────────┘ │          │ └─────────────┘ │     │
│  │        ↓        │          │        ↓        │     │
│  │ ┌─────────────┐ │          │ ┌─────────────┐ │     │
│  │ │SOP Compress │ │          │ │SOP Compress │ │     │
│  │ │+ FPA(8cy)   │ │          │ │+ FPA(8cy)   │ │     │
│  │ └─────────────┘ │          │ └─────────────┘ │     │
│  │        ↓        │          │        ↓        │     │
│  │ ┌─────────────┐ │          │ ┌─────────────┐ │     │
│  │ │Accumulator  │ │          │ │Accumulator  │ │     │
│  │ │(FP32)       │ │          │ │(FP32)       │ │     │
│  │ └─────────────┘ │          │ └─────────────┘ │     │
│  │        ↓        │          │        ↓        │     │
│  │ valid_r0 ──→ DEST[rr][col] (shared write)    │     │
│  │                 │          │        ↓        │     │
│  │                 │          │ valid_r1 ──→ DEST    │
│  │                 │          │        ↓        │     │
│  │ Input: exp_r0   │          │ Input: exp_r1   │     │
│  │        sman_r0  │          │        sman_r1  │     │
│  └─────────────────┘          └─────────────────┘     │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**Key Point:** Both r0 and r1 access the SAME shared register file (SRCA/SRCB/DEST), but with **independent valid signals** and **separate input data paths**.

---

## Two-Phase Processing (NOT r0/r1 Phases)

The "two-phase processing" occurs WITHIN each FP-Lane due to **ICG latch transparency**:

### Clock Cycle Timeline (INT8 Mode with HALF_FP_BW=1)

```
                  ONE Clock Cycle
        ┌──────────────────────────────┐
        │                              │
     PHASE 1                        PHASE 2
   (Clock LOW)                   (Clock HIGH)
        │                              │
        ├─ Latch Transparent          ├─ Latch Opaque (Holds)
        ├─ SRCA[rr][col] →Booth       ├─ SRCA[rr+256][col] →Booth
        ├─ SRCB[rr][col] →Booth       ├─ SRCB[rr+256][col] →Booth (via remap)
        ├─ Process INT8[0]            ├─ Process INT8[1]
        ├─ 8 partial products (PP0-7) ├─ 8 partial products (PP0-7)
        ├─ SOP compress & FPA (6cy)   ├─ Different data path (row remap active)
        ├─ DEST capturing Phase 1     ├─ DEST holding Phase 1 + capturing Phase 2
        │
        └──────────────────────────────┘
             ↓                    ↓
         One INT8 MAC         One INT8 MAC
         (independent)        (independent)
         ─────────────────────────────────
         Total: 2 INT8 MACs per cycle per lane
```

### Phase Behavior (within ONE clock cycle):

| Phase | Clock State | Latch State | SRCA/SRCB Row | Booth Input | DEST State |
|-------|------------|-------------|---------------|-------------|-----------|
| **Phase 1** | LOW | **Transparent** | rr (original) | SRCA[rr], SRCB[rr] | Capturing Phase 1 results |
| **Phase 2** | HIGH | **Opaque/Hold** | rr + 256 (remapped) | SRCA[rr+256], SRCB[rr+256] | Holding Phase 1; accepting Phase 2 results |

### ICG Latch Mechanism (Two-Level Latch)

```
┌─────────────────────────────────────────────────────┐
│            ICG (Integrated Clock Gate)              │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Clock LOW (Phase 1 - Transparent):                │
│  ┌──────────────────────────────────────────┐     │
│  │  Input ──→ Stabilization Latch ──────┐   │     │
│  │                                       │   │     │
│  │  Data Latch (TRANSPARENT):            │   │     │
│  │  ┌─────────────────────────────────┐  │   │     │
│  │  │ Input flows through to output   │  │   │     │
│  │  │ (combinational path visible)    │  │   │     │
│  │  └──────────────────┬──────────────┘  │   │     │
│  │                     │ Output (valid)  │   │     │
│  └─────────────────────┼──────────────────┘   │     │
│                        │                       │     │
│  ═════════════════════════════════════════════     │     │
│  Clock transitions LOW → HIGH                     │     │
│  ═════════════════════════════════════════════     │     │
│                        │                       │     │
│  Clock HIGH (Phase 2 - Opaque/Hold):              │     │
│  ┌──────────────────────────────────────────┐     │     │
│  │  Data Latch (OPAQUE/HOLD):                │     │     │
│  │  ┌─────────────────────────────────┐     │     │     │
│  │  │ Cross-coupled nor gates         │     │     │     │
│  │  │ Hold previous state (latched)   │     │     │     │
│  │  │ Input change ignored            │     │     │     │
│  │  └──────────────────┬──────────────┘     │     │     │
│  │                     │ Output (stable)    │     │     │
│  │                     │ (holds phase 1 val)│     │     │
│  └─────────────────────┼──────────────────┘     │     │
│                        │                       │     │
│                    Output (1)                  │     │
│                    (stable, phase 1 data)     │     │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Row Remapping Logic (INT8 with HALF_FP_BW=1)

#### RTL Code (tt_fpu_mtile.sv:1163-1167)

```systemverilog
// Phase 2 row mapping for INT8 mode
wire row_addr_second_phase = 
    ((HALF_FP_BW != 0) && second_fp_phase && (rr < FP_TILE_ROWS/2))
    ? (rr + FP_TILE_ROWS/2)      // Phase 2: map row 0→2, row 1→3, etc.
    : rr;                         // Phase 1: use row as-is

assign srca_operand[col] = SRCA[row_addr_second_phase][col];
```

#### Row Remapping Diagram (FP_TILE_ROWS=2)

```
SRCA Register File (Latch Array)
┌────────────────────────────────────────────┐
│  Row 0: INT8[0] INT8[1] ... INT8[7]        │
│  Row 1: INT8[0] INT8[1] ... INT8[7]        │
│  Row 2: INT8[8] INT8[9] ... INT8[15]       │
│  Row 3: INT8[16] INT8[17] ... INT8[23]     │
│                                             │
│  (Each row holds 8 INT8 values per column) │
└────────────────────────────────────────────┘
         ↑        ↑         ↑        ↑
         │        │         │        │
      PHASE 1  PHASE 1   PHASE 2  PHASE 2
      ┌────────────┐    ┌────────────┐
      │   rr=0:    │    │  rr=0:     │
      │ SRCA[0]    │    │ SRCA[2]    │  (0+2)
      │            │    │ (remapped) │
      │   rr=1:    │    │  rr=1:     │
      │ SRCA[1]    │    │ SRCA[3]    │  (1+2)
      │            │    │ (remapped) │
      └────────────┘    └────────────┘
      
      Booth → INT8 MAC[0]    Booth → INT8 MAC[1]
           ↓                       ↓
        Phase 1 INT8           Phase 2 INT8
        (independent)          (independent)
```

#### Multiplexer Logic for Row Selection

```
                 Phase 2?  HALF_FP_BW?  rr < 1?
                    │          │          │
                    ├──────────┼──────────┤
                    │    0     │    X     │    X    → row_addr = rr
                    │    1     │    0     │    X    → row_addr = rr
                    │    1     │    1     │    0    → row_addr = rr + 2 ✓
                    │    1     │    1     │    1    → row_addr = rr + 2 ✓
                    └──────────┴──────────┴────────

For FP_TILE_ROWS=2:
  Phase 1 (Clock LOW):  rr=0 → SRCA[0], rr=1 → SRCA[1]
  Phase 2 (Clock HIGH): rr=0 → SRCA[2], rr=1 → SRCA[3]
```

#### Operand Processing Timeline (One Clock Cycle)

```
Clock Cycle N
┌────────────────────────────────────────────────────────────┐
│                                                             │
│  Cycle[0-7ns] ─ Clock LOW (Phase 1) ─ Cycle[7-10ns]       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Latch Transparent:                                   │  │
│  │ • SRCA[rr][col] → Operand path 1                    │  │
│  │ • SRCB[rr][col] → Operand path 1                    │  │
│  │ • Booth: INT8[0] × INT8[0] → 8 PPs (Phase 1)        │  │
│  │ • SOP compress + FPA (latency=6)                    │  │
│  │ • Result feeds DEST input                           │  │
│  └──────────────────────────────────────────────────────┘  │
│                         ↓                                   │
│  Cycle[10-20ns] ─ Clock HIGH (Phase 2) ─ Cycle[20ns]      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Latch Opaque (Hold), Row Remapping Active:           │  │
│  │ • SRCA[rr+2][col] → Operand path 2 (via mux)       │  │
│  │ • SRCB[rr+2][col] → Operand path 2 (via mux)       │  │
│  │ • Booth: INT8[1] × INT8[1] → 8 PPs (Phase 2)        │  │
│  │ • SOP compress + FPA (latency=6)                    │  │
│  │ • DEST holds Phase 1 result on Q pins               │  │
│  │ • DEST D pins accept Phase 2 result                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                         ↓                                   │
│  Next Cycle (C+1):                                         │
│  • Both INT8 MACs complete (one from each phase)          │
│  • DEST latch captures Phase 2 result                     │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

**Key Insight:**
- **Phase 1** processes row 0 and 1 (even rows)
- **Phase 2** processes row 2 and 3 (odd rows, via +2 offset)
- Both within **one clock cycle** due to ICG latch transparency
- **Result**: 2 independent INT8 multiplications per cycle per lane

---

## Latch Phases vs FP-Lane Indices

### Common Confusion: Negative/Positive Latch Phases

**ICG latch structure uses:**
- Negative latch (on clock LOW)
- Positive latch (on clock HIGH)

**These ARE NOT the same as r0/r1!**

**Mapping:**
```
r0 and r1 are TWO independent FP-Lane instances
                    ↓
They both use the SAME shared SRCA/SRCB/DEST latches
                    ↓
Those latches have INTERNAL negative/positive phases
(handled by ICG, not exposed as r0/r1)
                    ↓
Two-phase transparency allows Phase 1 + Phase 2
processing in ONE cycle
```

---

## Why Two FP-Lanes per Row?

### Purpose: Parallel Integer Computation

Each FP-Tile row can process:
- **FP32/FP16B Mode**: One operation per cycle (64 FMA total per FP-Tile)
- **INT8 Mode with NUM_PAIR=8**: Two independent INT8 multiplications per cycle
  - Each FP-Lane processes 8 INT8 MACs per cycle
  - r0 and r1 operate in parallel (different valid signals)
  - When HALF_FP_BW=1, each lane also does two-phase within-cycle processing

### Throughput Example (INT8, HALF_FP_BW=1):

```
Per Tensix = 2 G-Tiles × 4 rows × 2 lanes × 8 INT8 MACs × 2 phases
           = 2 × 4 × 2 × 8 × 2
           = 512 × 4
           = 2,048 INT8 MACs per Tensix per cycle

Per cluster (4 Tensix) = 2,048 × 4 = 8,192 INT8 MACs per cycle
```

---

## Parallel Execution: r0 and r1 Operating Independently

### Dual-Path Operation (INT16 or INT8 Mode)

```
                    One Clock Cycle
        ┌───────────────────────────────────┐
        │  FP-Tile Row (shared SRCA/SRCB)   │
        │                                   │
        │  Input Path 1     Input Path 2    │
        │  (from r0)        (from r1)       │
        │       │                │          │
        ├───────┴────────────────┴──────┐   │
        │                               │   │
    ┌───▼────────┐          ┌──────────▼──┐│
    │ FP-Lane r0 │          │ FP-Lane r1  ││
    │ LANE_ID=0  │          │ LANE_ID=1   ││
    │            │          │             ││
    │ if (valid_ │          │ if (valid_  ││
    │    r0):    │          │    r1):     ││
    │ └──────┐   │          │    └──┐     ││
    │        │   │          │       │     ││
    │   ┌────▼───────────┐  │  ┌────▼────┐││
    │   │Booth Mult[0-7] │  │  │Booth    ││
    │   │ × SRCA[rr]     │  │  │Mult[0-7]││
    │   │ × SRCB[rr]     │  │  │× SRCA   ││
    │   │(Phase 1 operand)│  │  │× SRCB  ││
    │   └────┬───────────┘  │  │(Phase 1)││
    │        │              │  │ ││
    │   8 PPs (exp path)     │  │ 8 PPs  ││
    │        │              │  │ ││
    │   SOP+FPA(6-8 cy)      │  │SOP+FPA ││
    │        │              │  │ ││
    │   ┌────▼──────────┐   │  │┌▼─────┐││
    │   │ result_r0 ───┼───────┤├─ → DEST│
    │   │              │   │  ││         │
    │   │valid_r0 ─────┼───────┤┼─ → DEST│
    │   └────────────┘   │  │└─────────┘│
    │                    │  └───────────┘│
    │                    │               │
    └────────────────────┴───────────────┘
         ↓                    ↓
      INT16 MAC[0]        INT16 MAC[1]
      (per cycle)         (per cycle)
      
      In INT8 mode with HALF_FP_BW=1:
      └─ Each lane: 8 INT8 MACs/cycle
      └─ Both lanes in parallel: 16 INT8 MACs/cycle per FP-Tile row
```

### Register File Sharing Architecture

```
Shared SRCA Latch Array (8 columns, dual-read-port per column)
┌────────────────────────────────────────────────────────┐
│        Col 0    Col 1   ...   Col 7                    │
│      ┌──────┬──────┐   ┌──────┬──────┐                 │
│ Rows │ Port │ Port │   │ Port │ Port │  ← 2 read ports│
│      │  r0  │  r1  │   │  r0  │  r1  │    per column  │
│ ┌────┼──────┼──────┼───┼──────┼──────┤                 │
│ │ 0  │ Val0 │ Val0 │   │ Val0 │ Val0 │                 │
│ │ 1  │ Val1 │ Val1 │   │ Val1 │ Val1 │                 │
│ │ 2  │ Val2 │ Val2 │   │ Val2 │ Val2 │  (for Phase 2)  │
│ │ 3  │ Val3 │ Val3 │   │ Val3 │ Val3 │                 │
│ └────┴──────┴──────┴───┴──────┴──────┘                 │
│        ↑        ↑        ↑       ↑                      │
│        │        │        │       │                      │
└────────┼────────┼────────┼───────┼──────────────────────┘
         │        │        │       │
      r0 r1    r0 r1   ...r0 r1  r0 r1
      Phase1   Phase1      Phase1 Phase1
      reads    reads       reads  reads


Shared SRCB Latch Array (8 columns, dual-read-port per column)
┌────────────────────────────────────────────────────────┐
│        Col 0    Col 1   ...   Col 7                    │
│      ┌──────┬──────┐   ┌──────┬──────┐                 │
│ Rows │ Port │ Port │   │ Port │ Port │  ← 2 read ports│
│      │  r0  │  r1  │   │  r0  │  r1  │    per column  │
│ ┌────┼──────┼──────┼───┼──────┼──────┤                 │
│ │ 0  │ Val0 │ Val0 │   │ Val0 │ Val0 │ Phase 1: rr     │
│ │ 1  │ Val1 │ Val1 │   │ Val1 │ Val1 │ (direct)        │
│ │ 2  │ Val2 │ Val2 │   │ Val2 │ Val2 │ Phase 2:        │
│ │ 3  │ Val3 │ Val3 │   │ Val3 │ Val3 │ rr+ROWS/2       │
│ │... │      │      │   │      │      │ (remapped)      │
│ └────┴──────┴──────┴───┴──────┴──────┘                 │
│        ↑        ↑        ↑       ↑                      │
└────────┼────────┼────────┼───────┼──────────────────────┘
      Phase1   Phase1   Phase2  Phase2
      reads    reads    reads   reads


Shared DEST Latch Array (4 columns per G-Tile, 2-write-port per column)
┌────────────────────────────────────────────────────────┐
│        Col 0    Col 1   ...   Col 3                    │
│      ┌──────┬──────┐   ┌──────┬──────┐                 │
│ Rows │WPort │WPort │   │WPort │WPort │  ← 2 write     │
│      │  r0  │  r1  │   │  r0  │  r1  │    ports per   │
│ ┌────┼──────┼──────┼───┼──────┼──────┤    column      │
│ │ 0  │ [rr] │ [rr] │   │ [rr] │ [rr] │                 │
│ │ 1  │      │      │   │      │      │                 │
│ │... │      │      │   │      │      │                 │
│ │rr  │  ◆   │  ◆   │   │  ◆   │  ◆   │ ← Both r0/r1   │
│ │    │(valid)      │   │(valid)      │    write same   │
│ └────┴──────┴──────┴───┴──────┴──────┘    address      │
│        ↑        ↑        ↑       ↑                      │
└────────┼────────┼────────┼───────┼──────────────────────┘
      r0        r1      r0      r1
    writes    writes   writes writes
    (when   (when    (when  (when
    valid)  valid)   valid) valid)
```

**Key Properties:**
1. **SRCA/SRCB:** Independent read ports for r0 and r1 (dual-port per column)
2. **DEST:** Both r0 and r1 write to the **same address** (rr) but can operate independently
3. **ICG Transparency:** Clock LOW (Phase 1) and HIGH (Phase 2) enable row remapping without separate storage

---

## RTL Instantiation Details

### Signal Mapping (tt_fpu_tile.sv):

```systemverilog
// r0 instantiation (Line 1139)
tt_fp_lane #(.LANE_ID(0), .ROW_ID(ROW_ID)) u_fp_lane_r0 (
  .i_clk(i_clk),
  .i_valid(alu_instr_valid_r0),      // ← Independent valid for r0
  .i_data_exp(fp_lane_data_exp_r0[r]),
  .i_data_sman(fp_lane_data_sman_r0[r]),
  // ... shared SRCA/SRCB/DEST ports ...
  .o_result(fp_lane_result[r]),
  .o_result_valid(fp_lane_valid[r])
);

// r1 instantiation (Line 1214)
tt_fp_lane #(.LANE_ID(1), .ROW_ID(ROW_ID)) u_fp_lane_r1 (
  .i_clk(i_clk),
  .i_valid(alu_instr_valid_r1),      // ← Independent valid for r1
  .i_data_exp(fp_lane_data_exp_r1[r]),
  .i_data_sman(fp_lane_data_sman_r1[r]),
  // ... shared SRCA/SRCB/DEST ports ...
  .o_result(fp_lane_result[r]),
  .o_result_valid(fp_lane_valid[r])
);
```

### Data Path Splitting:

```
fp_lane_data_exp_r0[r]     ← r0's input exponent
fp_lane_data_exp_r1[r]     ← r1's input exponent
fp_lane_data_sman_r0[r]    ← r0's input significand
fp_lane_data_sman_r1[r]    ← r1's input significand
```

Both r0 and r1 receive data from the SAME shared latch, but can process different values when HALF_FP_BW=1 (Phase 1 vs Phase 2 remapping).

---

## Concrete Example: INT8 Processing (FP-Tile Row 0, Column 0)

### Data Flow Through r0 and r1

```
Input Data (SRCA/SRCB Latches):
┌─────────────────────────────────────────────────────────┐
│  SRCA Latch Array, Col 0:                               │
│  Row 0: [INT8_0a | INT8_0b] (16-bit packed)            │
│  Row 1: [INT8_1a | INT8_1b] (16-bit packed)            │
│  Row 2: [INT8_2a | INT8_2b] (16-bit packed)            │
│  Row 3: [INT8_3a | INT8_3b] (16-bit packed)            │
│                                                         │
│  SRCB Latch Array, Col 0:                               │
│  Row 0: [INT8_w0 | INT8_w1] (weight)                   │
│  Row 1: [INT8_w2 | INT8_w3]                            │
│  Row 2: [INT8_w4 | INT8_w5]                            │
│  Row 3: [INT8_w6 | INT8_w7]                            │
└─────────────────────────────────────────────────────────┘
         ↑                                    ↑
         │                                    │
    Phase 1 (Clock LOW)        Phase 2 (Clock HIGH)
    row_addr = 0                row_addr = 0+2 = 2
    row_addr = 1                row_addr = 1+2 = 3


Execution Timeline:
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  Clock Cycle N:                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ PHASE 1 (Clock LOW, 0-7ns)                         │ │
│  ├────────────────────────────────────────────────────┤ │
│  │                                                    │ │
│  │ FP-Lane r0:                  FP-Lane r1:          │ │
│  │ • Valid = 1                  • Valid = 1          │ │
│  │ • Read SRCA[0][0] = A0       • Read SRCA[0][0]=A0 │ │
│  │ • Read SRCB[0][0] = W0       • Read SRCB[0][0]=W0 │ │
│  │ • Booth: A0 × W0 = PP0-7     • Booth: A1 × W2 =   │ │
│  │ • 8 partial products           PP0-7             │ │
│  │ • SOP compress (Phase 1)     • SOP compress (Ph1) │ │
│  │                                                    │ │
│  │ OUTPUT (end of Phase 1):                          │ │
│  │ • result_r0 = INT8 MAC[0]    • result_r1 = I8 MAC│ │
│  │ • valid_r0 = 1               • valid_r1 = 1      │ │
│  │ • → feeds DEST[0][0] input   • → feeds DEST[0][0]│ │
│  │                                                    │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ PHASE 2 (Clock HIGH, 7-14ns)                       │ │
│  ├────────────────────────────────────────────────────┤ │
│  │                                                    │ │
│  │ Row Remapping Active (rr+2 for Phase 2):         │ │
│  │                                                    │ │
│  │ FP-Lane r0:                  FP-Lane r1:          │ │
│  │ • Valid = 1                  • Valid = 1          │ │
│  │ • Read SRCA[2][0] = A2       • Read SRCA[2][0]=A2 │ │
│  │ • Read SRCB[2][0] = W4       • Read SRCB[2][0]=W4 │ │
│  │ • Booth: A2 × W4 = PP0-7     • Booth: A3 × W6 =   │ │
│  │ • 8 partial products           PP0-7             │ │
│  │ • SOP compress (Phase 2)     • SOP compress (Ph2) │ │
│  │                                                    │ │
│  │ DEST Latch State:                                 │ │
│  │ • Q (output) = Phase 1 result (valid)             │ │
│  │ • D (input) accepts Phase 2 result                │ │
│  │                                                    │ │
│  │ OUTPUT (end of Phase 2):                          │ │
│  │ • result_r0 = INT8 MAC[2]    • result_r1 = I8 MAC│ │
│  │ • valid_r0 = 1               • valid_r1 = 1      │ │
│  │ • → triggers DEST[0][0] write • → triggers DEST  │ │
│  │                                                    │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│ Clock Cycle N+1:                                        │
│ ┌────────────────────────────────────────────────────┐ │
│ │ DEST[0][0] captures Phase 2 result (INT8 MAC[2])  │ │
│ │ Both MACs (Phase 1 & Phase 2) complete in one     │ │
│ │ clock cycle:                                       │ │
│ │ • INT8 MAC[0] = A0 × W0 + ... (from Phase 1)      │ │
│ │ • INT8 MAC[2] = A2 × W4 + ... (from Phase 2)      │ │
│ │                                                    │ │
│ │ Effective throughput: 2 INT8 MACs per lane/cycle  │ │
│ └────────────────────────────────────────────────────┘ │
│                                                          │
└──────────────────────────────────────────────────────────┘

Per FP-Tile Row (r0 + r1 in parallel):
  Phase 1: r0 processes row 0, r1 processes row 0 → 2 MACs
  Phase 2: r0 processes row 2, r1 processes row 2 → 2 MACs
  Total per cycle: 4 INT8 MACs (2 lanes × 2 phases)

Per Column (8 FP-Tiles):
  8 rows/column × 4 MACs = 32 INT8 MACs per column per cycle

Per FP-Tile (8 columns):
  8 columns × 32 = 256 INT8 MACs per FP-Tile per cycle
```

### Key Takeaways

1. **r0 and r1 are independent lanes** within each FP-Tile row
2. **Both operate in parallel** with separate valid signals
3. **Phase 1 and Phase 2** are clock-driven states (not separate physical datapaths)
4. **Row remapping** (rr → rr+2) leverages ICG latch transparency to access different register file rows within one cycle
5. **Result:** 2× throughput for INT8 mode without doubling hardware area

---

## Summary Table

| Aspect | r0 | r1 |
|--------|-----|-----|
| **What it is** | Lane 0 instance | Lane 1 instance |
| **LANE_ID** | 0 | 1 |
| **Valid signal** | `alu_instr_valid_r0` | `alu_instr_valid_r1` |
| **Share register files?** | Yes (SRCA/SRCB/DEST) | Yes (SRCA/SRCB/DEST) |
| **Parallel execution?** | Can run independently | Can run independently |
| **Related to latch phases?** | No (indirect via ICG) | No (indirect via ICG) |
| **Related to negative/positive latches?** | No (those are internal) | No (those are internal) |
| **Purpose** | INT8/INT16 compute | INT8/INT16 compute |
| **Throughput (INT8)** | 8 INT8 MACs/cycle | 8 INT8 MACs/cycle |
| **Throughput (FP32)** | 1 FMA/cycle | 1 FMA/cycle |

---

## Architecture Summary Diagram

### Hierarchical Grid Layout: G-Tile → M-Tile → FP-Tile → FP-Lane

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           G-TILE (Logical Unit)                          │
│                     1,024 INT16 MACs/cycle sustained                     │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  M-TILE 0                              M-TILE 1                         │
│  512 MACs/cycle                        512 MACs/cycle                   │
│  ┌──────────────────────────────────┐ ┌─────────────────────────────┐  │
│  │ FP-TILE Grid (8 rows × 8 cols)   │ │ FP-TILE Grid (8 rows × 8   │  │
│  │                                  │ │ cols)                       │  │
│  │ Row 0: ┌─┐ ┌─┐ ... ┌─┐ (8 tiles)│ │ Row 8: ┌─┐ ┌─┐ ... ┌─┐      │  │
│  │        │F│ │F│     │F│          │ │        │F│ │F│     │F│      │  │
│  │        │P│ │P│     │P│          │ │        │P│ │P│     │P│      │  │
│  │        │0│ │1│     │7│          │ │        │8│ │9│     │F│      │  │
│  │        └─┘ └─┘ ... └─┘          │ │        └─┘ └─┘ ... └─┘      │  │
│  │        ↓   ↓       ↓            │ │        ↓   ↓       ↓         │  │
│  │        r0  r0      r0           │ │        r0  r0      r0        │  │
│  │        r1  r1      r1           │ │        r1  r1      r1        │  │
│  │                                  │ │                              │  │
│  │ Row 1: [Similar 8 FP-Tiles]     │ │ Row 9: [Similar 8 FP-Tiles] │  │
│  │ Row 2: [Similar 8 FP-Tiles]     │ │ Row 10:[Similar 8 FP-Tiles] │  │
│  │ Row 3: [Similar 8 FP-Tiles]     │ │ Row 11:[Similar 8 FP-Tiles] │  │
│  │ Row 4: [INACTIVE (toggled)]     │ │ Row 12:[INACTIVE (toggled)]  │  │
│  │ Row 5: [INACTIVE (toggled)]     │ │ Row 13:[INACTIVE (toggled)]  │  │
│  │ Row 6: [INACTIVE (toggled)]     │ │ Row 14:[INACTIVE (toggled)]  │  │
│  │ Row 7: [INACTIVE (toggled)]     │ │ Row 15:[INACTIVE (toggled)]  │  │
│  │                                  │ │                              │  │
│  │ Active Rows: 0-3 (per cycle)    │ │ Active Rows: 8-11 (per cy)  │  │
│  │ (rows 4-7 toggle via hardware)  │ │ (rows 12-15 toggle)         │  │
│  └──────────────────────────────────┘ └─────────────────────────────┘  │
│                                                                           │
│  Shared Resources (per G-Tile):                                         │
│  • SRCA Latch Array: 8 columns × 4 rows (toggled) × 2 lanes            │
│  • SRCB Latch Array: 8 columns × 4 rows (toggled) × 2 lanes            │
│  • DEST Latch Array: 8 columns × 4 rows (toggled) × 2 lanes            │
│                                                                           │
└──────────────────────────────────────────────────────────────────────────┘
         ↓                                            ↓
    (G-Tile 0)                                  (G-Tile 1)
    1,024 MACs                                  1,024 MACs
    ╓───────────────────────────────────────────────────╖
    ║     2,048 MACs/cycle (One Tensix Tile)          ║
    ╚───────────────────────────────────────────────────╝


FP-TILE DETAILED VIEW (One grid element):
┌────────────────────────────────────────────┐
│       FP-TILE (Row i, Column j)            │
│     128 INT16 MACs/cycle per active row    │
│                                            │
│  Shared Latches (8 columns, 4 active rows)│
│  ┌──────────────────────────────────────┐ │
│  │ SRCA[0-3][j]  SRCB[0-3][j]           │ │
│  │                                      │ │
│  │ Phase 1 (CLK LOW):   Row i           │ │
│  │ Phase 2 (CLK HIGH):  Row i+2         │ │
│  └────┬─────────────────┬────────────────┤ │
│       │                 │                │ │
│   ┌───▼────┐        ┌───▼────┐         │ │
│   │r0 Input│        │r1 Input│         │ │
│   └───┬────┘        └───┬────┘         │ │
│       │                 │              │ │
│   ┌───▼──────────────────▼──────┐      │ │
│   │  Column j (8 Booth Multipliers)   │ │
│   │                                  │ │
│   │ ┌─────────────┐  ┌────────────┐  │ │
│   │ │ FP-Lane r0  │  │ FP-Lane r1 │  │ │
│   │ │ (LANE_ID=0) │  │(LANE_ID=1) │  │ │
│   │ │             │  │            │  │ │
│   │ │Booth×8 PPs  │  │Booth×8 PPs │  │ │
│   │ │SOP+FPA(8cy) │  │SOP+FPA(8cy)│  │ │
│   │ │             │  │            │  │ │
│   │ │ Result[32b] │  │Result[32b] │  │ │
│   │ └────┬────────┘  └────┬───────┘  │ │
│   │      │valid_r0        │valid_r1  │ │
│   │      └────┬───────────┘          │ │
│   │           │                      │ │
│   │      DEST[i][j] write            │ │
│   │      (dual write via r0+r1)      │ │
│   │                                  │ │
│   └──────────────────────────────────┘ │
│                                        │
│ Per Row (8 FP-Tiles per row):          │
│ • 8 columns × 16 MACs/col = 128        │
│                                        │
│ Per FP-Tile (all 4 rows):              │
│ • 4 rows × 128 = 512 INT16 MACs       │
│                                        │
└────────────────────────────────────────┘
         ↓                        ↓
   16 INT16 MACs/col    (per active row)
   (r0 lane + r1 lane)
   ═════════════════════════════════════════
   Total per FP-Tile:
   • 8 columns active per row
   • 4 rows active per cycle
   • 2 lanes per column (r0 + r1)
   • 8 MACs per lane per cycle (INT16)
   
   Calculation: 8 cols × 4 rows × 2 lanes × 8 MACs
              = 512 MACs per FP-Tile per cycle
```

### Single FP-Tile Atomic View

```
                    FP-TILE (Row, Column)
        ┌────────────────────────────────────────────┐
        │                                            │
        │  ┌────────────────────────────────────┐   │
        │  │  Shared Register Files (Latches)   │   │
        │  │  • SRCA[0-3][col] (8 columns)      │   │
        │  │  • SRCB[0-3][col] (8 columns)      │   │
        │  │  • DEST[rr][col]  (8 columns)      │   │
        │  │                                    │   │
        │  │  ICG Transparency:                 │   │
        │  │  Phase 1 (CLK LOW): Row rr         │   │
        │  │  Phase 2 (CLK HIGH): Row rr+2      │   │
        │  └────┬───────────────────┬───────────┘   │
        │       │                   │               │
        │       ├──────────┬────────┤               │
        │       │          │        │               │
        │  ┌────▼──────────▼─┐  ┌──▼───────────┐   │
        │  │ FP-Lane r0      │  │ FP-Lane r1   │   │
        │  │ (LANE_ID=0)     │  │ (LANE_ID=1)  │   │
        │  │ ┌────────────┐  │  │ ┌──────────┐ │   │
        │  │ │ Booth[0-7] │  │  │ │Booth[0-7]│ │   │
        │  │ │ × 8 PPs    │  │  │ │ × 8 PPs  │ │   │
        │  │ └────────────┘  │  │ └──────────┘ │   │
        │  │ ┌────────────┐  │  │ ┌──────────┐ │   │
        │  │ │ SOP+FPA    │  │  │ │SOP+FPA   │ │   │
        │  │ │ (8 cycles) │  │  │ │(8 cycles)│ │   │
        │  │ └────────────┘  │  │ └──────────┘ │   │
        │  │ ┌────────────┐  │  │ ┌──────────┐ │   │
        │  │ │ Result FP32│  │  │ │Result FP │ │   │
        │  │ └────┬───────┘  │  │ └────┬─────┘ │   │
        │  │      │valid_r0  │  │      │valid_ │   │
        │  │      └────┬─────┴──┴──────┘ r1   │   │
        │  │           │                      │   │
        │  │      (Both write DEST[rr][col])  │   │
        │  └──────────────────────────────────┘   │
        │                                          │
        │ Throughput:                             │
        │ • FP32 Mode: 1 FMA/cycle per lane      │
        │ • INT8 Mode: 8 INT8 MACs/cycle/lane   │
        │   (2× via Phase 1+2 in same clock)    │
        │                                          │
        └────────────────────────────────────────────┘
              ↓                                ↓
          INT16 MAC[0]                  INT16 MAC[1]
          per cycle                     per cycle
          ────────────────────────────────────────
          Per FP-Tile: 2 lanes × 16 MACs = 32 (INT16)
          Per FP-Tile: 2 lanes × 8×4 = 64 (INT8)
```

## Key Clarification

**r0 and r1 are NOT "negative latch" and "positive latch"**

Rather:
1. **r0 and r1** = Two independent FP-Lane instances per FP-Tile row
2. **Negative/positive latches** = Internal structure of the shared SRCA/SRCB/DEST arrays (handled by ICG)
3. **Two-phase processing** = Latch transparency during ONE clock cycle (Phase 1 on LOW, Phase 2 on HIGH)
4. **Row remapping** = How Phase 2 selects different SRCA/SRCB rows (rr + 2) while using same physical latches

The architecture achieves **2× throughput** by combining:
- Two independent FP-Lanes (r0, r1) with separate valid signals
- ICG-based latch transparency enabling two operations per cycle
- Row-remapping logic for Phase 2 to access different register file rows

### Misconception Clarification Chart

```
❌ WRONG:                          ✅ CORRECT:
┌──────────────────────────┐      ┌──────────────────────────┐
│ r0 = Negative Latch      │      │ r0 = FP-Lane instance    │
│ r1 = Positive Latch      │      │      (LANE_ID=0)         │
└──────────────────────────┘      └──────────────────────────┘

┌──────────────────────────┐      ┌──────────────────────────┐
│ r0/r1 phases = Clock     │      │ Clock phases = Clock     │
│ transparency phases      │      │ (LOW = Phase 1)          │
│                          │      │ (HIGH = Phase 2)         │
│                          │      │                          │
│                          │      │ r0/r1 = Parallel lanes   │
│                          │      │ (operate on same phases) │
└──────────────────────────┘      └──────────────────────────┘

┌──────────────────────────┐      ┌──────────────────────────┐
│ One FP-Lane does 2 MACs  │      │ Two FP-Lanes do 2 MACs   │
│ via r0/r1 latch toggle   │      │ via Phase 1+2 access to  │
│                          │      │ different register rows  │
└──────────────────────────┘      └──────────────────────────┘
```

---

**Document Updated:** 2026-04-13 with comprehensive diagrams
**RTL Release:** 20260221
