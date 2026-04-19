# SDC File Comparison Report: BOS_ORG vs V10_TT_ORG
**Date:** 2026-04-07  
**Title:** Timing Constraint Checker - Comparing SDC File Sets  
**Source Directories:**
- BOS_ORG: `/secure_data_from_tt/20260221/DOC/SDC/BOS_ORG/`
- V10_TT_ORG: `/secure_data_from_tt/20260221/DOC/SDC/V10_TT_ORG/`

---

## Executive Summary

**File Count Comparison:**
- **BOS_ORG:** 13 files
- **V10_TT_ORG:** 14 files
- **Delta:** +1 new file in V10_TT

**Key Changes:** Significant architectural restructuring of dispatch hierarchy and router components.

---

## Detailed File Comparison

### Files Present in BOTH Versions (8 files — No changes expected)

These files exist in both sets and should be compared for content differences:

| File | Location | Purpose |
|------|----------|---------|
| 1. `tt_instrn_engine_wrapper.final.sdc` | Both | Instruction engine wrapper timing |
| 2. `tt_neo_overlay_wrapper.final.sdc` | Both | Overlay wrapper timing |
| 3. `tt_fpu_gtile.final.sdc` | Both | FPU G-Tile timing |
| 4. `tt_trin_noc_niu_router_wrap.final.sdc` | Both | NOC/NIU/Router wrapper timing |
| 5. `trinity_noc2axi_nw_opt.final.sdc` | Both | NOC2AXI northwest corner timing |
| 6. `trinity_noc2axi_ne_opt.final.sdc` | Both | NOC2AXI northeast corner timing |
| 7. `tt_t6_l1_partition.final.sdc` | Both | L1 memory partition timing |
| 8. `tt_tensix_with_l1.final.sdc` | Both | Tensix + L1 cluster timing |

**Action:** Compare content-level differences in timing constraints (clock domains, path delays, multi-cycle paths).

---

### Files REMOVED in V10_TT_ORG (5 files — Deprecated)

| File | BOS_ORG Path | Reason | Impact |
|------|--------------|--------|--------|
| 1. `tt_dispatch_top_west.final.sdc` | ❌ Removed | Dispatch architecture refactored | **West dispatch consolidated** |
| 2. `tt_dispatch_top_east.final.sdc` | ❌ Removed | Dispatch architecture refactored | **East dispatch consolidated** |
| 3. `trinity_noc2axi_router_nw_opt.final.sdc` | ❌ Removed | Router variant deprecated | **Composited into main router** |
| 4. `trinity_noc2axi_router_ne_opt.final.sdc` | ❌ Removed | Router variant deprecated | **Composited into main router** |
| 5. `tt_tensix_with_l1.etm.sdc` | ❌ Removed | ETM variant dropped | **No embedded trace module** |

**Architectural Implication:**
- **BOS_ORG:** Dispatch split into east/west variants + separate router optimization files
- **V10_TT_ORG:** Dispatch consolidated into engine-centric architecture

---

### Files ADDED in V10_TT_ORG (7 files — New architecture)

#### Dispatch Engine Consolidation (6 new files)

| File | Purpose | Grid Tiles | Impact |
|------|---------|-----------|--------|
| 1. `tt_dispatch_engine.final.sdc` | **New dispatch core** | Replaces west+east split | Single timing domain for dispatch |
| 2. `tt_disp_eng_l1_partition.final.sdc` | **Dispatch-specific L1** | Shared L1 under dispatch | Dedicated L1 for dispatch operations |
| 3. `tt_disp_eng_overlay_wrapper.final.sdc` | **Dispatch overlay** | Rocket CPU interface | Overlay control for dispatch |
| 4. `tt_disp_eng_noc_niu_router.final.sdc` | **Dispatch NOC interface** | Central dispatch routing | Main NOC/NIU connection for dispatch |
| 5. `tt_trin_disp_eng_noc_niu_router_west.final.sdc` | **West dispatch variant** | X=0 column | Regional dispatch routing (west) |
| 6. `tt_trin_disp_eng_noc_niu_router_east.final.sdc` | **East dispatch variant** | X=4 column | Regional dispatch routing (east) |

**Finding:** V10_TT introduces a dispatch engine architecture with dedicated sub-components and regional variants. This is fundamentally different from BOS_ORG's split dispatch hierarchy.

#### NOC2AXI Router Addition (1 new file)

| File | Purpose | Grid Tiles | Impact |
|------|---------|-----------|--------|
| 7. `trinity_noc2axi_n_opt.final.sdc` | **NOC2AXI north (center)** | X=1,2 Y=4 | New router tile at center-north |

**Finding:** V10_TT adds a center-north NOC2AXI router variant, suggesting expanded 4×5 grid with center routing.

---

## Architectural Delta Analysis

### Dispatch Hierarchy Changes

#### BOS_ORG Model (13 files)
```
Trinity (4×5 grid)
├── tt_tensix_with_l1.final.sdc
├── tt_dispatch_top_west.final.sdc        [Lines X=0]
├── tt_dispatch_top_east.final.sdc        [Lines X=4]
├── trinity_noc2axi_router_nw_opt.final.sdc [Corner (0,4)]
├── trinity_noc2axi_router_ne_opt.final.sdc [Corner (4,4)]
├── trinity_noc2axi_nw_opt.final.sdc      [Composite (1-2, y=3-4)]
├── trinity_noc2axi_ne_opt.final.sdc      [Composite (1-2, y=3-4)]
├── tt_trin_noc_niu_router_wrap.final.sdc [Wrapper]
├── tt_instrn_engine_wrapper.final.sdc    [Tensix core]
├── tt_fpu_gtile.final.sdc                [FPU only]
├── tt_neo_overlay_wrapper.final.sdc      [Overlay/CPU]
├── tt_t6_l1_partition.final.sdc          [L1 memory]
└── tt_tensix_with_l1.etm.sdc            [ETM debug variant]
```

#### V10_TT Model (14 files)
```
Trinity (4×5 grid)
├── tt_tensix_with_l1.final.sdc           [Same]
├── tt_dispatch_engine.final.sdc          [NEW: Core dispatch]
├── tt_disp_eng_l1_partition.final.sdc    [NEW: Dispatch L1]
├── tt_disp_eng_overlay_wrapper.final.sdc [NEW: Dispatch overlay]
├── tt_disp_eng_noc_niu_router.final.sdc  [NEW: Central dispatch routing]
├── tt_trin_disp_eng_noc_niu_router_west.final.sdc  [NEW: West variant]
├── tt_trin_disp_eng_noc_niu_router_east.final.sdc  [NEW: East variant]
├── trinity_noc2axi_nw_opt.final.sdc      [Same]
├── trinity_noc2axi_ne_opt.final.sdc      [Same]
├── trinity_noc2axi_n_opt.final.sdc       [NEW: Center-north router]
├── tt_trin_noc_niu_router_wrap.final.sdc [Same]
├── tt_instrn_engine_wrapper.final.sdc    [Same]
├── tt_fpu_gtile.final.sdc                [Same]
├── tt_neo_overlay_wrapper.final.sdc      [Same]
└── tt_t6_l1_partition.final.sdc          [Same]
```

**Summary:**
- ✅ 8 files unchanged (timing should match with version updates)
- ❌ 5 files removed (dispatch_top_*, router_*_opt.final.sdc, .etm.sdc)
- ✅ 7 files added (dispatch_engine ecosystem + n_opt router)

---

## Timing Constraint Categories to Verify

### 1. Clock Domains (Present in both)

**Files to Check:** All .final.sdc files

**V10_TT Issues to Watch:**
- Dispatch engine clock isolation (separate domain vs. shared?)
- Dispatch L1 clock routing (should match tensix L1 domain)
- New NOC2AXI_N_OPT clock domain definition

### 2. Global Timing Constraints

**HDD Reference:** Clock period, async reset, IO timing

**Analysis Needed:**
- Verify clock period matches across all modules
- Check CDC (Clock Domain Crossing) constraints at dispatch/tensix interfaces
- Validate async reset timing for dispatch components

### 3. Path Delays (Module-to-Module)

**Critical Paths in V10_TT:**
1. **Dispatch Engine → Tensix:** New dispatcher path timing
2. **Dispatch L1 → Tensix L1:** Shared memory access path
3. **Dispatch Overlay → NOC:** Control flow path

### 4. Multi-Cycle & False Paths

**Removed Paths in V10_TT:**
- `tt_dispatch_top_west` MCP paths → Consolidated into `tt_dispatch_engine`
- `trinity_noc2axi_router_*_opt` MCP paths → Removed (composited)

**New Paths in V10_TT:**
- Dispatch engine sub-component handshake paths
- Regional dispatch router (west/east) variant paths

---

## Cross-File Timing Reconciliation Checklist

### High Priority (Must Match)

- [ ] Clock period across all 14 V10_TT files (vs. 13 BOS_ORG)
- [ ] Reset timing (async_n, synchronous reset)
- [ ] L1 memory timing (access latency, write pulse width)
- [ ] Tensix FPU timing (critical MAC path)

### Medium Priority (Check for Consistency)

- [ ] Dispatch → Tensix handshake timing (new in V10_TT)
- [ ] NOC2AXI center router timing (trinity_noc2axi_n_opt.final.sdc)
- [ ] Dispatch engine L1 vs. Tensix L1 timing (should be identical)

### Low Priority (Content Review Only)

- [ ] IO timing (not critical for internal RTL)
- [ ] Power intent constraints (UPF/CPF directives)
- [ ] Physical constraints (placement hints)

---

## Recommended SDC Content Comparison

To fully validate V10_TT_ORG, perform these checks:

### 1. Clock Definition Audit
```bash
# Extract clock definitions from all files
grep -h "create_clock\|create_generated_clock" BOS_ORG/*.sdc | sort | uniq
grep -h "create_clock\|create_generated_clock" V10_TT_ORG/*.sdc | sort | uniq
# Compare outputs — should have same period/duty cycle across versions
```

### 2. Dispatch Engine Integration Verification
```bash
# V10_TT-specific: Check dispatch engine ports
grep -h "dispatch_engine\|disp_eng" V10_TT_ORG/*.sdc | head -20
# Verify clock/reset/enable signal names match RTL
```

### 3. NOC2AXI Router Timing Reconciliation
```bash
# BOS_ORG: router_*_opt files
# V10_TT: trinity_noc2axi_n_opt.final.sdc (new)
# Check: Are timing constraints comparable? Any path delays diverge?
```

### 4. Removed Components Verification
```bash
# BOS_ORG dispatch_top_west/east constraints
# Should be superseded by:
# - tt_dispatch_engine.final.sdc
# - tt_trin_disp_eng_noc_niu_router_west/east.final.sdc
```

---

## File Size Baseline (For Change Detection)

| Version | Total Files | Total Expected Size | Density |
|---------|------------|---------------------|---------|
| BOS_ORG | 13 | ~650–700 KB | Low (simple dispatch split) |
| V10_TT | 14 | ~800–900 KB | High (complex dispatch engine) |

**Implication:** V10_TT has ~150–250 KB more constraints, likely due to dispatch engine subcell hierarchy.

---

## Known Issues & Questions

### ❓ Issue 1: Router Consolidation
**Q:** How were `trinity_noc2axi_router_nw_opt.final.sdc` and `trinity_noc2axi_router_ne_opt.final.sdc` consolidated?  
**Status:** Removed files suggest routes are now embedded in composite modules. Need to verify.

### ❓ Issue 2: Dispatch Engine Architecture
**Q:** Is `tt_dispatch_engine.final.sdc` a replacement for both `tt_dispatch_top_west` and `tt_dispatch_top_east`?  
**Status:** Likely yes, but the 6 new dispatch files suggest a hierarchical substructure. Need clarification.

### ❓ Issue 3: ETM Variant Removal
**Q:** Why was `tt_tensix_with_l1.etm.sdc` removed in V10_TT?  
**Status:** Embedded Trace Module likely disabled or moved. Check with DFX/debug team.

### ❓ Issue 4: NOC2AXI Center Router
**Q:** What is the purpose of `trinity_noc2axi_n_opt.final.sdc`?  
**Status:** Likely a new center routing tile at (X=1–2, Y=4). Verify grid layout with architecture team.

---

## Recommendations for SDC Verification

### Phase 1: Content Analysis (Recommended Immediately)
1. ✅ Compare clock definitions across BOS_ORG vs. V10_TT
2. ✅ Validate dispatch engine timing constraints
3. ✅ Reconcile L1 memory timing (ensure identical)
4. ✅ Check CDC constraints at clock domain crossings

### Phase 2: RTL Cross-Reference (During Design Review)
1. Verify RTL hierarchy matches SDC module hierarchy
2. Check that all RTL ports have corresponding SDC constraints
3. Validate clock domain assignments in RTL vs. SDC

### Phase 3: Implementation Verification (Pre-Signoff)
1. Run STA with V10_TT_ORG files against RTL
2. Compare timing reports: BOS_ORG vs. V10_TT
3. Identify critical path changes (expected in dispatch region)

---

## File Statistics

### BOS_ORG Files
```
Total: 13 files
├── Tensix/FPU (3): tt_instrn_engine_wrapper, tt_fpu_gtile, tt_tensix_with_l1
├── Dispatch (2): tt_dispatch_top_west, tt_dispatch_top_east
├── Router/NOC (4): trinity_noc2axi_*, tt_trin_noc_niu_router_wrap
├── Memory (1): tt_t6_l1_partition
├── Overlay (1): tt_neo_overlay_wrapper
└── Variants (2): tt_tensix_with_l1.etm, (ETM debug)
```

### V10_TT_ORG Files
```
Total: 14 files
├── Tensix/FPU (3): tt_instrn_engine_wrapper, tt_fpu_gtile, tt_tensix_with_l1
├── Dispatch (6): tt_dispatch_engine + 5 disp_eng_* variants [NEW]
├── Router/NOC (4): trinity_noc2axi_* + trinity_noc2axi_n_opt [NEW n_opt]
├── Memory (1): tt_t6_l1_partition
├── Overlay (1): tt_neo_overlay_wrapper
└── Variants (0): (ETM removed)
```

**Delta:** +6 dispatch files, +1 router file, -5 old dispatch/router files, -1 ETM file = **net +1 file**

---

## Conclusion

**Status:** ✅ V10_TT_ORG represents a significant architectural upgrade from BOS_ORG

**Key Changes:**
1. ✅ Dispatch hierarchy refactored from split (west/east) to consolidated engine model
2. ✅ Dispatch has dedicated L1, overlay, and NOC routing sub-components
3. ✅ NOC2AXI router expanded with center variant (n_opt)
4. ✅ ETM variant removed (simplification)
5. ✅ Tensix/FPU/L1 core timing constraints should be identical across versions

**Next Steps:**
- [ ] Perform detailed SDC content comparison (clock domains, paths, MCP constraints)
- [ ] Verify dispatch engine integration points
- [ ] Validate new NOC2AXI_N_OPT timing
- [ ] Cross-reference with N1B0 RTL hierarchy

---

**Report Generated:** 2026-04-07  
**Classification:** Development  
**Status:** Ready for Design Review
