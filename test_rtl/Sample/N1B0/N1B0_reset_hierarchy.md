# N1B0 Reset Architecture and Hierarchy

**Document Version:** 1.0
**Date:** 2026-04-01
**Scope:** Complete reset signal distribution in N1B0 NPU (4×5 mesh)
**Source:** RTL verification from `used_in_n1/mem_port/rtl/trinity.sv`

---

## Table of Contents

1. Overview
2. Top-Level Reset Inputs
3. Reset Distribution Architecture
4. Per-Domain Reset Hierarchy
5. Per-Tile Reset Connections
6. Clock Routing Reset Structure
7. EDC and PRTN Reset Integration
8. Reset Timing and CDC Considerations
9. Summary Tables
10. Harvest Mechanism and Reset Integration

---

## 1. Overview

The N1B0 reset architecture is organized around **multiple reset domains**, each synchronized to a specific clock domain and distributed hierarchically from the top-level module (`trinity`) down through intermediate clock routing structures to individual tile modules.

**Key Reset Domains:**
- **noc_clk domain:** Global NoC fabric, router, NIU bridges
- **ai_clk domain:** Per-column AI compute (FPU, SFPU, TRISC, MOP sequencer) — 4 independent per-column resets
- **dm_clk domain:** Per-column data-move (TDMA, pack/unpack, L1 access) — separate core and uncore resets per column
- **edc_clk domain:** EDC ring timing (treated as power_good signal)
- **PRTN domain:** Partition control chain (independent reset input)

---

## 2. Top-Level Reset Inputs

### 2.1 Trinity Module Reset Port List

| Signal Name | Width | Type | Direction | Scope | Description |
|-------------|-------|------|-----------|-------|-------------|
| `i_noc_reset_n` | 1 | async_low | input | Global | NoC fabric, router, NIU reset. Synchronizes noc_clk domain. |
| `i_ai_reset_n` | [3:0] | async_low | input | Per-column (X) | AI compute reset. Index = column X. 4 independent resets for columns 0–3. |
| `i_tensix_reset_n` | [11:0] | async_low | input | Per-Tensix | Tensix-specific reset. 12 Tensix clusters (indices 0–11 per getTensixIndex mapping). |
| `i_edc_reset_n` | 1 | async_low | input | Global | EDC ring reset. Currently used as power_good signal in clock routing. |
| `i_dm_core_reset_n` | [13:0][7:0] | async_low | input | Per-DM complex, per-core | TDMA/FPU/SFPU core reset. Packed as [NumDmComplexes-1:0][DMCoresPerCluster-1:0] = [13:0][7:0]. 14 DM complexes × 8 cores/complex. |
| `i_dm_uncore_reset_n` | [13:0] | async_low | input | Per-DM complex | TDMA uncore logic reset (pack/unpack, L1 interface). 14 DM complexes (one per complex). |
| `PRTNUN_FC2UN_RSTN_IN` | 1 | async_low | input | PRTN chain | Partition control chain reset input. |

**Notes:**
- All resets are **asynchronous active-low** (`*_n` convention)
- `i_ai_reset_n[3:0]` and `i_dm_clk[3:0]` are per-column (X=0..3), allowing independent DVFS per column
- `i_dm_core_reset_n[13:0][7:0]` and `i_dm_uncore_reset_n[13:0]` are per-DM-complex (14 total complexes), not per-column. Each complex is mapped to a specific tile location via `getDmIndex(x, yy)` helper
- `i_tensix_reset_n[11:0]` is a pre-computed per-Tensix input; trinity maps it via `getTensixIndex(x, y)` helper function
- `i_edc_reset_n` serves dual purpose: EDC ring reset + global power_good indicator for clock gating/isolation

---

## 3. Reset Distribution Architecture

### 3.1 Clock Routing Reset Path

The trinity module uses an internal **clock routing structure** (`clock_routing_in` / `clock_routing_out`) to distribute resets hierarchically from the top row (Y=4) down to each tile at Y=0.

**Structure:**
```
clock_routing_in[X][Y]  → tile module → clock_routing_out[X][Y]
```

Each `clock_routing_in/out` carries:
- `ai_clk_reset_n` — AI clock reset
- `noc_clk_reset_n` — NoC clock reset
- `dm_core_clk_reset_n[4:0]` — DM core reset (per-row index, 5 rows Y=0..4)
- `dm_uncore_clk_reset_n[4:0]` — DM uncore reset (per-row index)
- `tensix_reset_n[4:0]` — Tensix-specific reset (per-row index)
- `power_good` — EDC reset (used for clock gating)

### 3.2 Top-Row Reset Injection (Y=4)

At the top row (Y=4), resets are **directly connected** to the external input ports:

```systemverilog
// From trinity.sv lines 465-471
if (y == (trinity_pkg::SizeY - 1)) begin : top_row_clock_connections
  assign clock_routing_in[x][y].ai_clk_reset_n      = i_ai_reset_n[x];
  assign clock_routing_in[x][y].noc_clk_reset_n     = i_noc_reset_n;
  assign clock_routing_in[x][y].dm_clk              = i_dm_clk[x];
  assign clock_routing_in[x][y].power_good          = i_edc_reset_n;

  // DM core/uncore resets per column
  for (genvar yy = 0; yy < trinity_pkg::SizeY; yy++) begin
    if (TENSIX || DISPATCH_E || DISPATCH_W) begin
      assign clock_routing_in[x][y].dm_core_clk_reset_n[SizeY-1-yy]
        = i_dm_core_reset_n[getDmIndex(x, yy)];
      assign clock_routing_in[x][y].dm_uncore_clk_reset_n[SizeY-1-yy]
        = i_dm_uncore_reset_n[getDmIndex(x, yy)];
    end else begin
      assign clock_routing_in[x][y].dm_core_clk_reset_n[SizeY-1-yy]   = 1'b0;
      assign clock_routing_in[x][y].dm_uncore_clk_reset_n[SizeY-1-yy] = 1'b0;
    end

    if (TENSIX) begin
      assign clock_routing_in[x][y].tensix_reset_n[SizeY-1-yy]
        = i_tensix_reset_n[getTensixIndex(x, yy)];
    end else begin
      assign clock_routing_in[x][y].tensix_reset_n[SizeY-1-yy] = 1'b0;
    end
  end
end
```

**Key observations:**
- DM resets are **conditionally assigned** based on tile type (TENSIX/DISPATCH → assign; NOC2AXI/ROUTER → tie off to 1'b0)
- Tensix resets are **only assigned** to TENSIX tiles; non-Tensix tiles have tensix_reset_n tied off
- This avoids applying DM/Tensix resets to tiles that don't have those components

### 3.3 Middle-Row Reset Propagation (Y=0..3)

Middle rows propagate resets downstream from the row above:

```systemverilog
// From trinity.sv lines 493-500
else begin : middle_rows_clock_connections
  assign clock_routing_in[x][y].ai_clk_reset_n      = clock_routing_out[x][y+1].ai_clk_reset_n;
  assign clock_routing_in[x][y].noc_clk_reset_n     = clock_routing_out[x][y+1].noc_clk_reset_n;
  assign clock_routing_in[x][y].dm_core_clk_reset_n = clock_routing_out[x][y+1].dm_core_clk_reset_n;
  assign clock_routing_in[x][y].dm_uncore_clk_reset_n = clock_routing_out[x][y+1].dm_uncore_clk_reset_n;
  assign clock_routing_in[x][y].tensix_reset_n      = clock_routing_out[x][y+1].tensix_reset_n;
end
```

**Propagation path:**
- Y=4 (top) → Y=3 → Y=2 → Y=1 → Y=0 (bottom)
- Each tile at row Y receives resets from the tile above it (Y+1)
- This hierarchical structure allows for clock/reset abutting between adjacent rows

---

## 4. Per-Domain Reset Hierarchy

### 4.1 noc_clk Domain Reset

**Source:** `i_noc_reset_n` (global)
**Scope:** All tiles (NOC2AXI, Router, Dispatch, Tensix)
**Distribution:** Direct pass-through via `clock_routing_in[x][y].noc_clk_reset_n`

**Affected components:**
- NoC router flit engines (tt_trinity_router)
- NOC2AXI/AXI2NOC bridges (all variants: standalone NW_OPT, NE_OPT, composite ROUTER_NW_OPT, ROUTER_NE_OPT)
- Overlay wrapper (context switch registers, NoC stream interface)
- EDC ring synchronizers (noc_clk domain CDC)

### 4.2 ai_clk Domain Reset

**Source:** `i_ai_reset_n[X]` — per-column, separate for X=0,1,2,3
**Scope:** All tiles in column X
**Distribution:** Via `clock_routing_in[x][y].ai_clk_reset_n`

**Affected components per Tensix cluster:**
- TRISC0/TRISC1/TRISC2 (instruction fetch, decoder, ALU)
- TRISC3 (tile management, NoC DMA control)
- FPU global fetch/dispatch (G-Tile level)
- SFPU (scalar floating point)
- MOP sequencer
- Overlay CPU (Rocket 8-core RISC-V cluster)
- Tessent scan infrastructure (DFX)

**Independent DVFS:** Each column can have independent ai_clk frequency and reset synchronization.

### 4.3 dm_clk Domain Reset

**Source:**
- `i_dm_core_reset_n[DmComplexIdx][CoreIdx]` — per-core DM reset (TDMA, FPU pipeline, L1 write-port sequencer)
  - 14 DM complexes (indexed 0–13) × 8 cores per complex = 112 independent core resets
- `i_dm_uncore_reset_n[DmComplexIdx]` — per-uncore DM reset (pack/unpack engines, L1 read-port sequencer, memory interface)
  - 14 DM complexes (indexed 0–13), one reset per complex

**Scope:** Per-DM-complex (distributed across grid). Each complex is mapped to a tile location via `getDmIndex(x, yy)` helper function.

**Affected components per Tensix cluster:**
- **dm_core:** TDMA sequencer (pack/unpack trigger, MOP fetch), L1 write-side, DEST latch-array write controller
- **dm_uncore:** Pack/unpack engines, L1 read-side (SRAM + CDC), SRCA latch-array, EDC loopback (dm_clk domain)

**Separate core/uncore:** Allows power gating of compute core while keeping memory interface active, or vice versa.

**Note:** Although `i_dm_clk` is per-column (X=0..3), the DM reset signals are per-complex, allowing fine-grained reset control within the shared dm_clk domain. This enables partial power gating of specific DM complexes while keeping others active on the same dm_clk.

### 4.4 edc_clk Domain Reset (Power Good)

**Source:** `i_edc_reset_n`
**Scope:** Global (all tiles)
**Current use:** Mapped to `power_good` in clock routing structure

**Function:**
- Not a dedicated EDC clock reset (EDC ring uses noc_clk and ai_clk domains)
- Serves as a **global power/health signal** for clock gating, isolation cell control
- When `i_edc_reset_n = 0`, chip is in reset/power-down state

**Note:** Future versions may separate EDC ring reset (noc_clk + ai_clk CDC) from global power_good signal.

### 4.5 tensix_reset_n Reset

**Source:** `i_tensix_reset_n[TensixIdx]` — 12 per-Tensix inputs
**Scope:** TENSIX tiles only (Y=0,1,2 at X=0,1,2,3)
**Indexing:** `getTensixIndex(x, y)` helper function maps (X,Y) grid position to linear index 0–11

**Affected components:**
- Tensix compute pipelines (distinct from ai_clk domain logic)
- Some per-Tensix state machines (if implemented as separate reset domain)

**Note:** Many designs may merge `tensix_reset_n` with `ai_clk_reset_n` in actual implementation; this port allows independent control if needed for DVFS.

---

## 5. Per-Tile Reset Connections

### 5.1 NOC2AXI Tile Reset Connections

**Standalone NIU (X=0 Y=4, X=3 Y=4):**
Module: `trinity_noc2axi_{nw,ne}_opt`

```systemverilog
// From trinity.sv lines 722–726
.noc2axi_i_ai_reset_n        (clock_routing_in[x][y].ai_clk_reset_n),
.noc2axi_i_noc_reset_n       (clock_routing_in[x][y].noc_clk_reset_n),
.noc2axi_i_dm_core_reset_n   (clock_routing_in[x][y].dm_core_clk_reset_n),
.noc2axi_i_dm_uncore_reset_n (clock_routing_in[x][y].dm_uncore_clk_reset_n),
.noc2axi_i_tensix_reset_n    (clock_routing_in[x][y].tensix_reset_n),
```

**Composite NIU (X=1 Y=3–4, X=2 Y=3–4):**
Module: `trinity_noc2axi_router_{nw,ne}_opt`

```systemverilog
// From trinity.sv lines 954–958 (NIU portion)
.noc2axi_i_ai_reset_n        (clock_routing_in[x][y].ai_clk_reset_n),
.noc2axi_i_noc_reset_n       (clock_routing_in[x][y].noc_clk_reset_n),
.noc2axi_i_dm_core_reset_n   (clock_routing_in[x][y].dm_core_clk_reset_n),
.noc2axi_i_dm_uncore_reset_n (clock_routing_in[x][y].dm_uncore_clk_reset_n),
.noc2axi_i_tensix_reset_n    (clock_routing_in[x][y].tensix_reset_n),
```

### 5.2 Router Tile Reset Connections

**Standalone Router:** N/A (no standalone router in N1B0; router placeholder at (1,3) and (2,3) is empty)

**Composite Router (X=1 Y=3–4, X=2 Y=3–4):**
Module: `trinity_noc2axi_router_{nw,ne}_opt` (internal router portion)

```systemverilog
// From trinity.sv lines 1113–1117 (Router portion)
.router_o_ai_reset_n         (clock_routing_out[x][y-1].ai_clk_reset_n),
.router_o_nocclk_reset_n     (clock_routing_out[x][y-1].noc_clk_reset_n),
.router_o_dm_core_reset_n    (clock_routing_out[x][y-1].dm_core_clk_reset_n),
.router_o_dm_uncore_reset_n  (clock_routing_out[x][y-1].dm_uncore_clk_reset_n),
.router_o_tensix_reset_n     (clock_routing_out[x][y-1].tensix_reset_n),
```

**Note:** Router feeds resets downstream to Y-1 (next row below).

### 5.3 Dispatch Tile Reset Connections

**Dispatch West (X=0 Y=3)** and **Dispatch East (X=3 Y=3):**
Module: `tt_dispatch_top_{west,east}`

```systemverilog
// From trinity.sv lines 1505–1509
.i_ai_reset_n        (clock_routing_in[x][y].ai_clk_reset_n),
.i_nocclk_reset_n    (clock_routing_in[x][y].noc_clk_reset_n),
.i_core_reset_n      (clock_routing_in[x][y].dm_core_clk_reset_n),
.i_uncore_reset_n    (clock_routing_in[x][y].dm_uncore_clk_reset_n),
.i_tensix_reset_n    (clock_routing_in[x][y].tensix_reset_n),
```

**Affected components:**
- iDMA engine (Rocket-attached accelerator)
- Rocket CPU cluster (8-core RISC-V)
- APB register interface

### 5.4 Tensix Tile Reset Connections

**Tensix Cluster (X=0–3, Y=0–2):**
Module: `tt_tensix_with_l1`

```systemverilog
// From trinity.sv lines 1505–1509 (mapped to tt_dispatch context; actual Tensix signals similar)
.i_ai_reset_n        (clock_routing_in[x][y].ai_clk_reset_n),
.i_nocclk_reset_n    (clock_routing_in[x][y].noc_clk_reset_n),
.i_core_reset_n      (clock_routing_in[x][y].dm_core_clk_reset_n),
.i_uncore_reset_n    (clock_routing_in[x][y].dm_uncore_clk_reset_n),
.i_tensix_reset_n    (clock_routing_in[x][y].tensix_reset_n),
```

**Affected components:**
- TRISC0/1/2/3 (instruction fetch, decoder, ALU, tile management)
- FPU (all G-Tiles, M-Tiles, FP-Lanes)
- SFPU
- MOP sequencer
- L1 SRAM partition (3MB, 512 macros per tile, 4 tiles per cluster = 2MB cluster)
- DEST latch-array (DEST registers for write destinations)
- SRCA latch-array (SRCA registers for read addresses)

---

## 6. Clock Routing Reset Structure

### 6.1 Clock Routing Interface

The internal `clock_routing_in` and `clock_routing_out` structures carry reset signals alongside clock signals for each tile:

**SystemVerilog struct-like organization:**
```
clock_routing_in[x][y] :
  - ai_clk                    (32-bit clock)
  - ai_clk_reset_n            (1-bit reset)
  - noc_clk                   (32-bit clock)
  - noc_clk_reset_n           (1-bit reset)
  - dm_clk                    (32-bit clock)
  - dm_core_clk_reset_n[4:0]  (5-bit reset array for rows)
  - dm_uncore_clk_reset_n[4:0](5-bit reset array for rows)
  - tensix_reset_n[4:0]       (5-bit reset array for rows)
  - power_good                (1-bit EDC reset)

clock_routing_out[x][y] :
  - Same structure (output from tile back to routing)
```

### 6.2 Reset Propagation Timing

**Abutted structure:** Each row's clock_routing_in connects to clock_routing_out from the row above:

```
              ┌─────────────────────┐
              │  trinity top ports  │
              │ i_ai_reset_n[x]     │
              │ i_noc_reset_n       │
              │ i_edc_reset_n       │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Y=4 tile          │
              │  (NOC2AXI/Router)   │
              │  clock_routing_out  │
              └──────────┬──────────┘
                         │ assignment to [x][3]
              ┌──────────▼──────────┐
              │  Y=3 tile          │
              │  (Dispatch/Router)  │
              │  clock_routing_out  │
              └──────────┬──────────┘
                         │ assignment to [x][2]
              ┌──────────▼──────────┐
              │  Y=2 tile          │
              │  (Tensix)           │
              │  clock_routing_out  │
              └──────────┬──────────┘
                         │ (Y=1 and Y=0 follow similarly)
```

**Reset assertion/deassertion:**
1. Top-level reset inputs are asserted asynchronously
2. Each tile receives reset via clock routing (combinational path)
3. Clock gating/isolation can be controlled via `power_good` signal
4. Reset deassertion is synchronized internally per tile (typically via 3-stage synchronizer)

---

## 7. EDC and PRTN Reset Integration

### 7.1 EDC Reset Distribution

**EDC Ring Clock Domains:** The EDC ring spans both noc_clk and ai_clk domains with CDC (Clock Domain Crossing) synchronizers at column Y=2 boundaries.

**EDC Reset Source:**
- Primary: `i_edc_reset_n` (global, mapped to `power_good`)
- Secondary: Inherited from per-domain resets (noc_clk_reset_n and ai_clk_reset_n) at CDC boundaries

**EDC Node Reset Connections:**
- Each EDC node (instantiated within tile modules) receives reset from its parent tile's reset domain
- Example: EDC node in Tensix tile receives both ai_clk_reset_n and noc_clk_reset_n depending on node location
- See §7 (EDC Ring) of N1B0_NPU_HDD_v0.99 for detailed EDC node paths

### 7.2 PRTN Chain Reset

**PRTN Reset Ports:**
- Input: `PRTNUN_FC2UN_RSTN_IN` (external partition control reset)
- Output: `PRTNUN_FC2UN_RSTN_OUT[3:0]` (per-column passthrough)

**PRTN Reset Distribution:**
```systemverilog
// From trinity.sv lines 224–231, 246–250
// Top-level connection (Y=2 cluster)
for (genvar x = 0; x < trinity_pkg::SizeX; x++) begin
  assign w_left_prtnun_fc2un_rstn_in[x][2]  = PRTNUN_FC2UN_RSTN_IN;
  assign PRTNUN_FC2UN_RSTN_OUT[x]           = w_right_prtnun_fc2un_rstn_out[x][0];
end

// Internal propagation (Y=1↔Y=2, Y=0↔Y=1)
for (genvar x = 0; x < trinity_pkg::SizeX; x++) begin
  for (genvar y = 0; y < 2; y++) begin
    assign w_left_prtnun_fc2un_rstn_in[x][y]    = w_right_prtnun_fc2un_rstn_out[x][y+1];
    assign w_right_prtnun_un2fc_intr_in[x][y+1] = w_left_prtnun_un2fc_intr_out[x][y];
  end
end
```

**PRTN Reset Scope:**
- Affects partition control registers and context-switch logic
- Independent from main reset domains (ai_clk, dm_clk, noc_clk)
- Allows dynamic context switching without full chip reset

---

## 8. Reset Timing and CDC Considerations

### 8.1 Asynchronous Reset Deassertion

All top-level resets are **asynchronous active-low**. Deassertion (transition 0→1) occurs asynchronously with respect to the clock domains.

**CDC Synchronizers:** Each clock domain (ai, dm, noc) must internally synchronize reset deassertion to avoid metastability:
- Typical implementation: **3-stage synchronizer chain** (sync3r) in each tile module
- Minimum deassertion time: 3 clock cycles per domain

### 8.2 Reset Synchronization per Domain

| Domain | Primary Reset Input | Sync Method | Expected Deassert Cycles |
|--------|---------------------|------------|--------------------------|
| noc_clk | i_noc_reset_n | sync3r in each tile | 3 × noc_clk |
| ai_clk[x] | i_ai_reset_n[x] | sync3r in each tile | 3 × ai_clk[x] |
| dm_clk[x] | i_dm_core/uncore_reset_n[x] | sync3r in each tile | 3 × dm_clk[x] |
| PRTN_clk | PRTNUN_FC2UN_RSTN_IN | sync3r in partition control | 3 × PRTN_clk |

### 8.3 EDC Ring CDC Boundaries

EDC ring crosses clock domains at Y=2 (ai_clk ↔ noc_clk). Reset synchronization at CDC boundaries:
- Forward path (ai→noc): Synchronized by noc_clk domain sync3r in destination node
- Return path (noc→ai): Synchronized by ai_clk domain sync3r in destination node

---

## 9. Summary Tables

### 9.1 Reset Signal Summary

| Signal | Width | Type | Scope | Clock Domain | Structure |
|--------|-------|------|-------|--------------|-----------|
| i_noc_reset_n | 1 | async_low | Global (all tiles) | noc_clk | Global (monolithic) |
| i_ai_reset_n | [3:0] | async_low | Per-column (X=0–3) | ai_clk | Per-column (4 signals) |
| i_tensix_reset_n | [11:0] | async_low | Per-Tensix cluster (12 total) | ai_clk | Per-Tensix (12 signals) |
| i_edc_reset_n | 1 | async_low | Global (power_good indicator) | All | Global (monolithic) |
| i_dm_core_reset_n | [13:0][7:0] | async_low | Per-DM complex, per-core (14 complexes × 8 cores) | dm_clk | Per-complex (112 signals) |
| i_dm_uncore_reset_n | [13:0] | async_low | Per-DM complex (14 complexes) | dm_clk | Per-complex (14 signals) |
| PRTNUN_FC2UN_RSTN_IN | 1 | async_low | Partition control chain | PRTN_clk | Global (monolithic) |

### 9.2 Reset Distribution by Tile Type

| Tile Type | Grid Position | Reset Signals Received | Comments |
|-----------|---------------|----------------------|----------|
| Tensix cluster | (0–3, 0–2) | ai_clk_reset_n, noc_clk_reset_n, dm_core_reset_n[y], dm_uncore_reset_n[y], tensix_reset_n[y] | Full reset set |
| Dispatch W/E | (0/3, 3) | ai_clk_reset_n, noc_clk_reset_n, dm_core_reset_n[y], dm_uncore_reset_n[y], tensix_reset_n[y] | Full reset set |
| NOC2AXI standalone | (0/3, 4) | ai_clk_reset_n, noc_clk_reset_n, dm_core_reset_n[y], dm_uncore_reset_n[y], tensix_reset_n[y] (tied to 0) | Tensix reset not used |
| NOC2AXI composite | (1/2, 3–4) | ai_clk_reset_n, noc_clk_reset_n, dm_core_reset_n[y], dm_uncore_reset_n[y], tensix_reset_n[y] (tied to 0) | Tensix reset not used |
| Router (composite) | (1/2, 3–4) | ai_clk_reset_n, noc_clk_reset_n, dm_core_reset_n[y], dm_uncore_reset_n[y], tensix_reset_n[y] | Internal to composite module |

### 9.3 Reset Structure Summary

**Per-Column vs Per-Complex Resets:**

| Reset Type | Structure | Count | Scope | DVFS-Independent? |
|-----------|-----------|-------|-------|-------------------|
| i_ai_reset_n | Per-column [3:0] | 4 | Each column X=0..3 | Yes (per-column) |
| i_dm_clk | Per-column [3:0] | 4 | Each column X=0..3 | Yes (per-column) |
| i_dm_core_reset_n | Per-DM-complex [13:0][7:0] | 14×8=112 | Each DM complex (indexed via getDmIndex) | Yes (per-complex) |
| i_dm_uncore_reset_n | Per-DM-complex [13:0] | 14 | Each DM complex (indexed via getDmIndex) | Yes (per-complex) |

**Key Insight:** While `i_ai_clk[x]` and `i_dm_clk[x]` are per-column (enabling per-column DVFS), the DM reset signals are per-DM-complex (14 complexes indexed 0–13). Each tile's DM complex index is computed via `getDmIndex(x, y)` helper function, which maps (X, Y) grid coordinates to a linear DM complex index. This enables fine-grained reset control of individual DM complexes across the grid, even within a shared dm_clk column.

**DVFS Capability:** Each column can independently adjust `i_ai_clk[x]` and `i_dm_clk[x]` frequency. Additionally, each DM complex can be independently reset via `i_dm_core_reset_n[DmIdx][*]` and `i_dm_uncore_reset_n[DmIdx]`, allowing selective power-gating of specific complexes.

---

## 10. Harvest Mechanism and Reset Integration

### 10.1 Harvest Overview

N1B0 implements a **six-mechanism harvest scheme** for manufacturing yield recovery. Mechanism 6 (ISO_EN) controls output isolation, clock gating, and EDC bypass for harvested (disabled) tiles. Reset distribution must account for harvested tiles to prevent uncontrolled reset injection into disabled circuitry.

**Harvest Mechanisms (1–5):** Baseline Trinity mechanisms (NoC mesh reconfiguration, EDC bypass, power domain gating, etc.)
**Harvest Mechanism 6 (ISO_EN):** Additional isolation for N1B0

### 10.2 ISO_EN Signal and Tile Mapping

**Signal:** `ISO_EN[11:0]` (12 bits, one per Tensix tile)

**Scope:** Only Tensix tiles (Y=0..2, all X columns)

**Bit Mapping Formula:** `ISO_EN[x + 4*y]` for tile at grid position (X=x, Y=y)

**Grid Layout:**
```
  Tensix tiles only (Y=0..2):
  ┌────────────────────────────┐
  │ Y=2: [11] [10] [9]  [8]   │  (X=3..0)
  │ Y=1: [7]  [6]  [5]  [4]   │  (X=3..0)
  │ Y=0: [3]  [2]  [1]  [0]   │  (X=3..0)
  └────────────────────────────┘
  
  Dispatch, NIU, Router tiles (Y=3..4): NO ISO_EN
```

**When ISO_EN[i] = 1 (tile harvested):**
1. Output signals driven to safe values via AND-type ISO cells
2. All EDC nodes within the tile bypassed from the ring chain
3. Tile's compute clocks gated (ai_clk[X] and dm_clk[X] at clock tree)
4. NoC mesh routing reconfigured to avoid harvested tile coordinates
5. Reset signals remain asserted or held in a known state

### 10.3 Reset Behavior for Harvested Tiles

#### 10.3.1 Reset Assertion During Harvest

When `ISO_EN[i]` is asserted to harvest a Tensix tile:

**Reset Signal State:**
- **Global resets** (`i_noc_reset_n`, `i_edc_reset_n`): Remain at normal operating state
- **Column resets** (`i_ai_reset_n[X]`, `i_dm_clk[X]` reset):
  - If entire column is harvested: Reset can be asserted or held de-asserted
  - If single tile in column is harvested: Reset remains de-asserted (other tiles in column active)
- **Per-tile reset signals** continue to propagate through clock routing, but:
  - Tile's internal flip-flops are isolated by power gating
  - Outputs gated by ISO cells, preventing reset-controlled logic from driving mesh

#### 10.3.2 Reset Deassertion with Harvested Tiles

When de-asserting resets with harvested tiles present:

**Sequence:**
1. Assertion of `ISO_EN[i]` for all harvested tiles (before reset assertion changes)
2. De-assertion of resets in normal sequence (global → per-domain → per-tile)
3. Harvested tiles remain isolated; reset deassertion does not affect their state
4. Active tiles receive reset deassertion and initialize normally

**Safety Guarantee:** Output isolation from `ISO_EN[i]` ensures harvested tiles cannot drive uncontrolled signals onto the NoC mesh or into EDC ring, even if resets are de-asserted while `ISO_EN[i]` is active.

#### 10.3.3 Reset Removal Order with Mixed Harvest

For designs with some harvested columns and some active columns:

```
Step 1: Assert ISO_EN for all harvested tiles (ISO_EN[harvested_set] = 1)
Step 2: Gate clocks to harvested tiles (handled by DFX wrapper clock gates)
Step 3: Assert global reset: i_noc_reset_n = 0, i_edc_reset_n = 0
Step 4: De-assert global reset (async deassertion)
Step 5: Synchronize per-domain resets (3-stage sync per domain in active tiles):
        - Active tiles: ai_clk[X] reset synchronized in parallel (if X is active)
        - Active tiles: dm_clk[X] reset synchronized in parallel (if X is active)
        - Active tiles: noc_clk reset synchronized globally
Step 6: Harvested tiles remain isolated via ISO_EN throughout sequence
Step 7: De-assert per-tile resets in active tiles only
Step 8: Harvested tiles in powered-down state; no reset-triggered initialization
```

### 10.4 EDC Ring Bypass and Reset Continuity

The EDC ring bypass mechanism ensures that harvested tiles are invisible to the ring chain. Reset distribution must respect this:

**EDC Node Reset in Harvested Tile:**
- Each Tensix tile contains EDC nodes that are part of the ring chain
- When `ISO_EN[i]` is asserted, a **bypass mux** routes around these nodes
- The bypass mux is controlled directly by `ISO_EN[i]`
- **Reset state of bypassed nodes:** Asynchronously held in reset via the bypass mux, preventing spurious EDC activity

**Reset Signal Path for Bypassed Nodes:**
```
(Simplified EDC node internal reset distribution)

Input reset from tile module → Mux select (ISO_EN) → Bypass mux
                              └─ Active path (ISO_EN = 0): reset feeds ring node
                              └─ Bypass path (ISO_EN = 1): bypass path drives ring, node held in reset
```

**Critical:** The bypass mux operates **combinationally** (zero delay). When `ISO_EN[i]` transitions high, the bypassed EDC node is immediately removed from the ring and the bypass path takes over. No reset synchronization delay occurs at the bypass transition.

### 10.5 Clock Gating and Reset Interaction

**Clock Gating Cells:**
- Placed in clock routing path at column boundaries (ai_clk[X] and dm_clk[X] trees)
- Controlled by `ISO_EN[x]` from all 3 Tensix tiles in column X (if all harvested: column gates; partial harvest: tile-level gating via output isolation)

**Reset Timing During Clock Gating:**

| Phase | State | ai_clk[X] | dm_clk[X] | Reset Signal | Tile Effect |
|-------|-------|-----------|-----------|---------------|---------
| Pre-Harvest | Active | Running | Running | De-asserted | Normal operation |
| Harvest Cmd | Harvest | Gated | Gated | De-asserted | Clocks stop; internal state frozen |
| Reset Assert | Reset | Gated | Gated | Asserted | Clocks held, resets asserted (latches hold old state) |
| Reset Deassert | Reboot | Running (after gate open) | Running (after gate open) | De-asserted (sync) | Clocks resume, resets sync, state initializes |

**Key Point:** Harvested tile's clocks are gated before reset deassertion. When clock gates are re-opened during reboot, reset synchronizers in the clock gate enable path ensure clock resumption is glitch-free and properly aligned with reset deassertion.

### 10.6 Per-Column Reset Independence with Harvest

N1B0's per-column reset architecture (Section 4) interacts with harvest as follows:

**Harvested Full Column (X=X_h, all Y=0..2 harvested):**
- `i_ai_reset_n[X_h]` can be independently asserted/de-asserted without affecting adjacent columns
- Active neighboring columns (X=X_h±1) maintain their own reset deassertion timing
- Enables staggered reboot: harvest unneeded columns, boot only needed columns

**Harvested Partial Column (e.g., X=1 Y=0 harvested, X=1 Y=1 and Y=2 active):**
- `i_ai_reset_n[1]` must de-assert for all tiles in column 1 (including harvested tile)
- Harvested tile (1,0) receives reset deassertion but remains isolated by `ISO_EN[1]`
- Active tiles (1,1) and (1,2) receive reset deassertion and initialize normally

### 10.7 Reset Initialization Sequence with Harvest

**Recommended Firmware Reset Initialization:**

```c
// Step 1: Load harvest configuration (which tiles to disable)
APB_WRITE(PRTN_HARVEST_MASK, harvest_bitmap);  // PRTN chain applies power gating

// Step 2: Immediately assert ISO_EN for all harvested tiles
APB_WRITE(ISO_EN_MASK, harvest_bitmap);  // Isolated outputs, bypass EDC nodes

// Step 3: Assert global reset
i_noc_reset_n = 0;
i_edc_reset_n = 0;

// Step 4: Wait for reset deassertion (async deassertion + synchronizer delay)
i_noc_reset_n = 1;  // Async de-assert (async_low active edge 0→1)
i_edc_reset_n = 1;
wait_for_reset_sync(3 * CLK_PERIOD);  // 3 cycles for sync3r

// Step 5: De-assert per-domain resets (in parallel for columns)
for (col = 0; col < 4; col++) {
  if (!(harvest_bitmap & (0xF << (col * 4)))) {  // If column has active tiles
    i_ai_reset_n[col] = 1;
    i_dm_core_reset_n[get_dm_index(col, *)] = 1;
    i_dm_uncore_reset_n[get_dm_index(col, *)] = 1;
  }
}
wait_for_reset_sync(3 * ai_clk_period);  // Wait for per-domain sync

// Step 6: Verify EDC ring healthy (skipping harvested tiles)
EDC_verify_ring_integrity(active_tile_set);  // Active tiles only

// Step 7: Begin normal operation
PRTN.enable_compute();  // Power up active tiles, keep harvested tiles off
```

---

## Summary

The N1B0 reset architecture provides:

1. **Global resets:** noc_clk (shared across all mesh), edc_clk (power_good signal)
2. **Per-column resets:** ai_clk[x], dm_clk[x], enabling independent DVFS per column
3. **Per-Tensix resets:** Granular control for dynamic power management
4. **Hierarchical distribution:** Top-row injection → middle-row propagation → per-tile synchronization
5. **CDC synchronizers:** 3-stage in each tile for metastability-safe reset deassertion
6. **Partition control:** PRTN chain with independent reset for dynamic context switching

This architecture balances global chip reset functionality with per-domain and per-column independence for power, thermal, and frequency management.
