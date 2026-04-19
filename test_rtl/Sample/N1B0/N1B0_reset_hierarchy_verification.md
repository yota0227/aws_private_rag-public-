# N1B0_reset_hierarchy.md Verification Report

**Date:** 2026-04-01
**Verification Status:** ✅ CORRECTED (3 Critical Errors Fixed)

---

## Errors Found and Corrected

### ❌ Error 1: i_dm_core_reset_n Signal Width

**Original (INCORRECT):** `[3:0][3:0]` (4×4 = 16 signals)
**Corrected (RTL-VERIFIED):** `[13:0][7:0]` (14×8 = 112 signals)
**Root Cause:** Confused per-column scope with actual DM complex indexing
**RTL Source:** trinity.sv line 59; trinity_pkg.sv lines 48, 54
```systemverilog
// Trinity_pkg defines:
localparam int unsigned NumDmComplexes = 14;
localparam int unsigned DMCoresPerCluster = 8;

// Trinity.sv declares:
input logic [trinity_pkg::NumDmComplexes-1:0][trinity_pkg::DMCoresPerCluster-1:0] i_dm_core_reset_n,
```
**Corrected Sections:** 2.1 (table), 2.1 (notes), 4.3, 9.1 (table)

---

### ❌ Error 2: i_dm_uncore_reset_n Signal Width

**Original (INCORRECT):** `[3:0]` (4 signals, one per column)
**Corrected (RTL-VERIFIED):** `[13:0]` (14 signals, one per DM complex)
**Root Cause:** Same as Error 1 — incorrect assumption about per-column reset granularity
**RTL Source:** trinity.sv line 60; trinity_pkg.sv line 48
```systemverilog
input logic [trinity_pkg::NumDmComplexes-1:0] i_dm_uncore_reset_n,
```
**Corrected Sections:** 2.1 (table), 2.1 (notes), 4.3, 9.1 (table)

---

### ❌ Error 3: Misleading "Per-Column" Classification

**Original (MISLEADING):** Sections 2.1 notes and 4.3 suggested DM resets were "per-column"
**Corrected (ACCURATE):** DM resets are **per-DM-complex** (14 total), not per-column
**Key Insight:** While `i_ai_clk[x]` and `i_dm_clk[x]` are per-column (4 signals), the DM reset signals are per-complex (14 signals). Each tile's complex is indexed via `getDmIndex(x, y)` helper function.
**Impact:** Clarifies that fine-grained reset control (per DM complex) is independent of per-column clock distribution.
**Corrected Sections:** 2.1 (notes), 4.3, 9.3 (complete rewrite with per-complex emphasis)

---

## Verifications ✅

| Claim | RTL Source | Status |
|-------|-----------|--------|
| NumDmComplexes = 14 | trinity_pkg.sv:48 | ✅ Verified |
| 14 = 12 Tensix + 2 Dispatch | trinity_pkg.sv:37-40 GridConfig | ✅ Verified |
| DMCoresPerCluster = 8 | trinity_pkg.sv:54 | ✅ Verified |
| i_ai_reset_n[3:0] per-column | trinity.sv:51 (SizeX-1:0) | ✅ Verified |
| i_tensix_reset_n[11:0] | trinity.sv:52 (NumTensix-1:0); trinity_pkg.sv:44 | ✅ Verified |
| SizeX=4, SizeY=5 mesh | trinity_pkg.sv:11-12 | ✅ Verified |
| Reset distribution via clock routing structure | trinity.sv:465-500 | ✅ Verified |
| DM reset conditional assignment (TENSIX/DISPATCH only) | trinity.sv:475-482 | ✅ Verified |
| Tensix reset tied off for non-Tensix tiles | trinity.sv:485-489 | ✅ Verified |

---

## Document Quality After Corrections

**Accurate Sections:**
- §1 Overview ✅
- §2 Top-Level Reset Inputs (CORRECTED)
- §3 Reset Distribution Architecture ✅
- §4 Per-Domain Reset Hierarchy (CORRECTED)
- §5 Per-Tile Reset Connections ✅
- §6 Clock Routing Reset Structure ✅
- §7 EDC and PRTN Reset Integration ✅
- §8 Reset Timing and CDC Considerations ✅
- §9 Summary Tables (CORRECTED)
- §10 Harvest Mechanism and Reset Integration ✅ (NEW - ADDED 2026-04-01)

**Ready for:** HDD v0.99 integration as reference document

---

## Lessons Learned

1. **Signal width != scope:** Just because `i_ai_clk[x]` is per-column doesn't mean related reset signals follow the same pattern. `i_dm_reset_n[*]` has a different indexing scheme based on actual tile placement via helper functions.

2. **Helper function importance:** `getDmIndex(x, y)` and `getTensixIndex(x, y)` must be understood to correctly map grid coordinates to reset signal indices. A simple per-column assumption misses this mapping layer.

3. **SystemVerilog 2D arrays:** Reset arrays like `[13:0][7:0]` require careful tracking of which index is accessed at each hierarchy level (top-level input, clock routing structure, per-tile instantiation).

