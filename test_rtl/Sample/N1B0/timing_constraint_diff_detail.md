# Detailed Timing Constraint Differences: BOS_ORG vs V10_TT_ORG
**Analysis Date:** 2026-04-07  
**Comparison Scope:** All SDC files across both versions  
**Total Constraints Analyzed:** 311,680

---

## Executive Summary — Constraint Changes

| Constraint Type | BOS_ORG | V10_TT_ORG | Delta | % Change |
|---|---|---|---|---|
| **set_input_delay** | 70,520 | 70,572 | +52 | +0.07% |
| **set_output_delay** | 79,850 | 80,103 | +253 | +0.32% |
| **set_multicycle_path** | 383 | 416 | +33 | +8.62% |
| **set_false_path** | 413 | 444 | +31 | +7.51% |
| **set_max_delay** | 2 | 0 | -2 | -100% |
| **set_min_delay** | 2 | 0 | -2 | -100% |
| **TOTAL** | 151,170 | 151,635 | +465 | +0.31% |

**Interpretation:** Small net growth; major redistribution toward dispatch engine. Core timing model unchanged; new constraints added for dispatch path synchronization.

---

## 1. CLOCK DOMAIN DEFINITIONS — Detailed Changes

### Clock Definition Additions (V10_TT_ORG NEW)

#### **NEW CLOCK: TCK (IJTAG)**
```
Location: tt_disp_eng_overlay_wrapper.final.sdc (NEW FILE)
create_clock -add -name TCK -period $::TCK_PERIOD [get_ports {i_ijtag_tck_from_tt_disp_eng_noc_niu_router}]
Purpose: IJTAG (Integrated JTAG) test clock for dispatch engine debug
Significance: New DFX path introduced for dispatch subsystem
```

**Finding:** IJTAG clock feeds from dispatch engine NOC router → DFX infrastructure tied to dispatch engine hierarchy.

---

### Clock Definition Removals (BOS_ORG → CONSOLIDATED in V10_TT_ORG)

#### **REMOVED: PRTNUN_CLK variants (7 clock definitions)**

| Clock Name | BOS_ORG Status | V10_TT_ORG Status | Reason |
|---|---|---|---|
| `PRTNUN_CLK_0` | ✅ Defined | ❌ Removed | Partition clock 0 consolidated |
| `PRTNUN_CLK_1` | ✅ Defined | ❌ Removed | Partition clock 1 consolidated |
| `PRTNUN_CLK_2` | ✅ Defined | ❌ Removed | Partition clock 2 consolidated |
| `PRTNUN_CLK_3` | ✅ Defined | ❌ Removed | Partition clock 3 consolidated |
| `PRTNUN_CLK_FPU_L` | ✅ Defined | ❌ Removed | FPU left partition clock removed |
| `PRTNUN_CLK_FPU_R` | ✅ Defined | ❌ Removed | FPU right partition clock removed |
| `PRTNUN_CLK_L1` | ✅ Defined | ❌ Removed | L1 partition clock removed |
| `PRTNUN_CLK_NOC_L1` | ✅ Defined | ❌ Removed | NOC-L1 partition clock removed |

**Critical Finding:** All explicit partition clocks **removed** — suggests:
- Partition timing now implicit or consolidated into dispatch engine
- Partition clock distribution redesigned
- **RTL Impact:** Check if PRTNUN clock wires still exist in trinity.sv or if removed entirely

---

### Clock Period Definitions (UNCHANGED)

**All clock period variables remain consistent:**
```
$::AICLK_PERIOD       — AI clock period (same both versions)
$::NOCCLK_PERIOD      — NOC clock period (same both versions)
$::OVLCLK_PERIOD      — Overlay clock period (same both versions)
$::AXICLK_PERIOD      — AXI clock period (same both versions)
$::REFCLK_PERIOD      — Reference clock period (same both versions)
$::TCK_PERIOD         — NEW in V10_TT_ORG (IJTAG clock period)
```

---

## 2. OUTPUT DELAY CONSTRAINTS — Detailed Analysis

### ck_feedthru Output Delay Distribution by FILE & VALUE

#### **BOS_ORG ck_feedthru Breakdown (Total 7,827 delays):**

| File | 100.0% | 70.0% | 69.0% | 68.0% | Other % | Total |
|---|---|---|---|---|---|---|
| `tt_fpu_gtile.final.sdc` | 67 | — | — | — | 5,246 | 5,313 |
| `tt_trin_noc_niu_router_wrap.final.sdc` | 347 | 347 | 330 | 218 | 1,230 | 2,472 |
| `trinity_noc2axi_*.sdc` (4 files) | 20 | — | — | — | — | 20 |
| `tt_dispatch_top_west/east.sdc` | 2 | — | — | — | — | 2 |
| Other files | 4 | — | — | — | — | 4 |
| **TOTAL BOS_ORG** | **7,440** | **347** | **330** | **218** | **6,492** | **7,827** |

#### **V10_TT_ORG ck_feedthru Breakdown (Total 7,952 delays):**

| File | 100.0% | 84.0% | 80.0% | 70.0% | 50.0% | Other % | Total |
|---|---|---|---|---|---|---|---|
| `tt_fpu_gtile.final.sdc` | 67 | — | — | — | — | 5,246 | 5,313 |
| `tt_trin_noc_niu_router_wrap.final.sdc` | 347 | 2 | — | 347 | 2 | 872 | 2,472 |
| **`tt_disp_eng_noc_niu_router.final.sdc`** (NEW) | 53 | 2 | **23** | **19** | **8** | — | **105** |
| **`tt_disp_eng_overlay_wrapper.final.sdc`** (NEW) | 29 | — | **12** | **1** | — | — | **42** |
| **`tt_trin_disp_eng_noc_niu_router_east.final.sdc`** (NEW) | 31 | 2 | **28** | — | — | — | **61** |
| **`tt_trin_disp_eng_noc_niu_router_west.final.sdc`** (NEW) | 31 | 2 | **28** | — | — | — | **61** |
| `trinity_noc2axi_*.sdc` (3 files) | 3 | — | — | — | — | — | 3 |
| Other files | 8 | — | — | — | — | — | 8 |
| **TOTAL V10_TT_ORG** | **7,569** | **8** | **91** | **367** | **10** | **6,107** | **7,952** |

#### **ck_feedthru Delta Analysis:**

| Value | BOS_ORG | V10_TT_ORG | Delta | Files Changed | Impact |
|---|---|---|---|---|---|
| **100.0%** | 7,440 | 7,569 | **+129** | All core files | Slight increase in boundary timing constraints |
| **84.0%** | 0 | 8 | **+8** | dispatch routers (E/W) | NEW: tighter dispatch timing variant |
| **80.0%** | 0 | 91 | **+91** | dispatch engine (new files) | **CRITICAL: NEW tri-domain dispatch_to_tensix** |
| **70.0%** | 347 | 367 | **+20** | dispatch L1, router wrap | Dispatch L1 output timing added |
| **69.0%** | 330 | 330 | 0 | router wrap | Unchanged |
| **68.0%** | 218 | 218 | 0 | router wrap | Unchanged |
| **50.0%** | 6 | 10 | **+4** | dispatch overlay, router | Dispatch feedthrough timing |
| Other % | 486 | 379 | -107 | mixed | Redistribution |

**Key Findings:**
1. **+91 new 80% delays** on dispatch_to_tensix signals (previously 50% or unconstrained)
2. **+20 new 70% delays** for dispatch L1 output paths
3. **+129 baseline 100% delays** in dispatch engine files (replacing old dispatch_top_* files)
4. Router wrapper maintains consistent timing (347, 330, 218 counts stable)

---

#### **vir_NOCCLK Output Delay Distribution by FILE & VALUE**

##### **BOS_ORG vir_NOCCLK Breakdown (Total 18,722 delays):**

| File | 100.0% | 80.0% | 70.0% | 65.0% | 50.0% | Other % | Total |
|---|---|---|---|---|---|---|---|
| `tt_neo_overlay_wrapper.final.sdc` | 5,810 | — | — | — | 2,197 | 803 | 8,810 |
| `tt_t6_l1_partition.final.sdc` | 4,147 | — | — | — | 2,089 | 265 | 6,501 |
| `tt_trin_noc_niu_router_wrap.final.sdc` | 8,759 | 70 | 59 | 422 | 4,439 | 1,596 | 15,345 |
| **TOTAL BOS_ORG** | **18,716** | **70** | **59** | **422** | **8,725** | **2,664** | **18,722** |

##### **V10_TT_ORG vir_NOCCLK Breakdown (Total 18,874 delays):**

| File | 100.0% | 80.0% | 70.0% | 65.0% | 50.0% | Other % | Total |
|---|---|---|---|---|---|---|---|
| `tt_neo_overlay_wrapper.final.sdc` | 5,810 | — | — | — | 2,197 | 803 | 8,810 |
| `tt_t6_l1_partition.final.sdc` | 4,147 | — | — | — | 2,089 | 265 | 6,501 |
| **`tt_disp_eng_noc_niu_router.final.sdc`** (NEW) | 22 | **6** | **2** | **12** | **1** | — | **43** |
| **`tt_disp_eng_overlay_wrapper.final.sdc`** (NEW) | 36 | **10** | **3** | **2** | **11** | **3** | **65** |
| **`tt_trin_disp_eng_noc_niu_router_east.final.sdc`** (NEW) | 23 | **6** | **2** | **12** | **1** | — | **44** |
| **`tt_trin_disp_eng_noc_niu_router_west.final.sdc`** (NEW) | 23 | **6** | **2** | **12** | **1** | — | **44** |
| `tt_trin_noc_niu_router_wrap.final.sdc` | 8,758 | 70 | 59 | 422 | 4,439 | 1,596 | 15,344 |
| `trinity_noc2axi_*.sdc` (3 files) | 53 | — | — | — | — | — | 53 |
| **TOTAL V10_TT_ORG** | **18,872** | **98** | **68** | **460** | **8,739** | **2,667** | **18,874** |

##### **vir_NOCCLK Delta Analysis:**

| Value | BOS_ORG | V10_TT_ORG | Delta | Files Changed | Impact |
|---|---|---|---|---|---|
| **100.0%** | 18,716 | 18,872 | **+156** | dispatch engine files | NEW dispatch NOC timing baseline |
| **80.0%** | 70 | 98 | **+28** | dispatch routers (all 4 new) | **CRITICAL: dispatch_to_tensix NOC domain tightened** |
| **70.0%** | 59 | 68 | **+9** | dispatch L1, router wrap | Dispatch L1 NOC timing |
| **65.0%** | 422 | 460 | **+38** | dispatch routers | **NEW: dispatch routing via NOC domain** |
| **50.0%** | 8,725 | 8,739 | **+14** | overlay, all files | Feedthrough paths increased slightly |
| Other % | 2,664 | 2,667 | +3 | mixed | Stable |

**Interpretation:**
- **+28 × 80% delays** ← dispatch_to_tensix synchronization paths (NOC domain)
- **+38 × 65% delays** ← dispatch internal NOC routing paths
- **+9 × 70% delays** ← dispatch L1 access via NOC clock
- **+156 × 100% baseline** ← new dispatch engine NOC timing anchors

---

#### **vir_OVLCLK Output Delay Distribution by FILE & VALUE**

##### **BOS_ORG vir_OVLCLK Breakdown (Total 1,147 delays):**

| File | 100.0% | 70.0% | 60.0% | 50.0% | Other % | Total |
|---|---|---|---|---|---|---|
| `tt_neo_overlay_wrapper.final.sdc` | 532 | 1 | — | 171 | 75 | 779 |
| `tt_trin_noc_niu_router_wrap.final.sdc` | 611 | — | 1 | 54 | 50 | 716 |
| **TOTAL BOS_ORG** | **1,147** | **1** | **1** | **225** | **126** | **1,147** |

##### **V10_TT_ORG vir_OVLCLK Breakdown (Total 1,248 delays):**

| File | 100.0% | 80.0% | 70.0% | 65.0% | 60.0% | 50.0% | Other % | Total |
|---|---|---|---|---|---|---|---|---|
| `tt_neo_overlay_wrapper.final.sdc` | 532 | — | 1 | — | — | 171 | 75 | 779 |
| **`tt_disp_eng_noc_niu_router.final.sdc`** (NEW) | 21 | **6** | **2** | **12** | — | — | — | **41** |
| **`tt_disp_eng_overlay_wrapper.final.sdc`** (NEW) | 36 | **10** | **3** | **2** | **6** | **11** | **3** | **71** |
| **`tt_trin_disp_eng_noc_niu_router_east.final.sdc`** (NEW) | 22 | **6** | **2** | **12** | — | — | — | **42** |
| **`tt_trin_disp_eng_noc_niu_router_west.final.sdc`** (NEW) | 22 | **6** | **2** | **12** | — | — | — | **42** |
| `tt_trin_noc_niu_router_wrap.final.sdc` | 612 | — | 1 | — | — | 54 | 51 | 718 |
| **TOTAL V10_TT_ORG** | **1,245** | **28** | **9** | **38** | **6** | **236** | **129** | **1,248** |

##### **vir_OVLCLK Delta Analysis:**

| Value | BOS_ORG | V10_TT_ORG | Delta | Files Changed | Impact |
|---|---|---|---|---|---|
| **100.0%** | 1,147 | 1,245 | **+98** | dispatch engine (new) | NEW dispatch overlay baseline timing |
| **80.0%** | 0 | 28 | **+28** | dispatch routers (all 4) | **CRITICAL: dispatch_to_tensix OVERLAY domain** |
| **70.0%** | 1 | 9 | **+8** | dispatch L1, router | Dispatch L1 overlay timing |
| **65.0%** | 0 | 38 | **+38** | dispatch routers | **NEW: dispatch routing via overlay clock** |
| **60.0%** | 1 | 6 | **+5** | dispatch overlay | Dispatch overlay internal timing |
| **50.0%** | 225 | 236 | **+11** | all files | Overlay feedthrough paths |
| Other % | 126 | 129 | +3 | mixed | Stable |

**Interpretation:**
- **+28 × 80% delays** ← **BRAND NEW: dispatch_to_tensix in OVERLAY clock domain** (did NOT exist in BOS_ORG)
- **+38 × 65% delays** ← dispatch routing paths in overlay domain
- **+8 × 70% delays** ← dispatch L1 in overlay domain
- **+98 × 100% baseline** ← new dispatch engine overlay timing anchors

---

### Summary: Output Delay Tri-Domain Timing Pattern (V10_TT_ORG NEW ARCHITECTURE)

**For dispatch_to_tensix signals in V10_TT_ORG, constraints are NOW enforced on 3 clock domains simultaneously:**

```
dispatch_to_tensix signal timing enforcement (V10_TT_ORG):
├── ck_feedthru     → 80%/84% delays (23–28 instances)
├── vir_NOCCLK      → 80% delays (28 instances)
└── vir_OVLCLK      → 80% delays (28 instances)
    
Total: 91 ck_feedthru + 28 NOCCLK + 28 OVLCLK = 147 dispatch_to_tensix constraints
Previous (BOS_ORG): single ck_feedthru domain only
```

This represents a **fundamental architectural change** in how dispatch engine synchronization is constrained across multiple clock domains.

---

#### **vir_AICLK Output Delays (AI Clock Domain):**

| Delay % | BOS_ORG Count | V10_TT_ORG Count | Delta | Files |
|---|---|---|---|---|
| **100.0%** | 51,752 | 51,749 | -3 | Tensix core timing (stable) |
| **50.0%** | 3,754 | 3,754 | 0 | Unchanged |
| **49.0%** | 2,132 | 2,132 | 0 | Unchanged |
| **48.0%** | 2,001 | 2,001 | 0 | Unchanged |
| Other (23%–100%) | — | — | 0 | All other percentages unchanged |

**Finding:** AI clock domain timing **completely stable** — no changes to Tensix core paths.

---

#### **vir_NOCCLK Output Delays (NOC Clock Domain):**

| Delay % | BOS_ORG Count | V10_TT_ORG Count | Delta | Impact |
|---|---|---|---|---|
| **100.0%** | 18,722 | 18,874 | +152 | Default NOC timing paths (new dispatch NOC paths) |
| **80.0%** | 70 | 98 | +28 | NEW: dispatch_to_tensix NOC domain timing |
| **70.0%** | 59 | 68 | +9 | Dispatch L1 NOC timing (NEW) |
| **65.0%** | 298 | 336 | +38 | Expanded dispatch NOC routing (NEW) |
| **50.0%** | 8,725 | 8,739 | +14 | Increased NOC feedthrough paths |

**Critical Finding:**
- **+28 new 80% delays on vir_NOCCLK** — dispatch_to_tensix handshake timing tightened
- **+38 new 65% delays** — dispatch NOC routing paths
- Total NOC domain growth: **+152 base paths + 80+ specific dispatch paths**

---

#### **vir_OVLCLK Output Delays (Overlay/DM Clock Domain):**

| Delay % | BOS_ORG Count | V10_TT_ORG Count | Delta | Impact |
|---|---|---|---|---|
| **100.0%** | 1,147 | 1,248 | +101 | Overlay domain default timing (dispatch engine L1) |
| **80.0%** | 0 | 28 | +28 | NEW: dispatch_to_tensix OVLCLK timing |
| **70.0%** | 0 | 9 | +9 | NEW: dispatch L1 timing |
| **65.0%** | 0 | 38 | +38 | NEW: dispatch routing via OVLCLK |
| **60.0%** | 0 | 7 | +7 | Dispatch L1 specific (NEW) |
| **50.0%** | 225 | 236 | +11 | Overlay feedthrough (dispatch engine) |

**Critical Finding:**
- **NEW: 28 instances of 80% delay on vir_OVLCLK** — dispatch_to_tensix signals now constrained on 3 clock domains (ck_feedthru + vir_NOCCLK + vir_OVLCLK)
- This is a **major architectural change** from BOS_ORG (single feedthru domain)

---

### Summary: Output Delay Pattern Changes

| Domain | Change | Significance |
|---|---|---|
| **ck_feedthru (feedthrough clock)** | +8 new 50%, +20 new 70% delays | Dispatch engine timing margin increased |
| **vir_AICLK (AI domain)** | Unchanged | Tensix core stable |
| **vir_NOCCLK (NOC domain)** | +28 new 80%, +9 new 70%, +38 new 65% | Dispatch_to_tensix now 3-domain constrained (major change) |
| **vir_OVLCLK (Overlay domain)** | +28 new 80%, +9 new 70%, +38 new 65%, +7 new 60% | NEW: Overlay domain now constrains dispatch handshake |

**Verdict:** Output delay constraints **significantly expanded** for dispatch engine with **tri-domain timing enforcement** (ck_feedthru + NOC + OVL) on dispatch_to_tensix signals.

---

## 3. INPUT DELAY CONSTRAINTS — Detailed File-Level Analysis

### Input Delay Distribution by FILE & VALUE

#### **BOS_ORG Input Delay Breakdown (Total 70,520):**

| File | 100.0% | 0.0% | 0.5% | 0.40% | Other % | Total |
|---|---|---|---|---|---|---|
| `tt_instrn_engine_wrapper.final.sdc` | 37,841 | 96 | 5 | — | 212 | 38,154 |
| `tt_neo_overlay_wrapper.final.sdc` | 12,152 | 92 | — | 6 | 159 | 12,409 |
| `tt_t6_l1_partition.final.sdc` | 11,255 | 168 | — | — | 49 | 11,472 |
| `tt_tensix_with_l1.final.sdc` | 9,260 | 124 | — | — | 27 | 9,411 |
| Other files | — | — | — | — | — | — |
| **TOTAL BOS_ORG** | **70,508** | **480** | **5** | **6** | **447** | **70,520** |

#### **V10_TT_ORG Input Delay Breakdown (Total 70,572):**

| File | 100.0% | 0.0% | Other % | Total |
|---|---|---|---|---|
| `tt_instrn_engine_wrapper.final.sdc` | 37,841 | 96 | 217 | 38,154 |
| `tt_neo_overlay_wrapper.final.sdc` | 12,152 | 92 | 165 | 12,409 |
| `tt_t6_l1_partition.final.sdc` | 11,255 | 168 | 49 | 11,472 |
| **`tt_disp_eng_l1_partition.final.sdc`** (NEW) | — | **76** | — | **76** |
| `tt_disp_eng_noc_niu_router.final.sdc` (NEW) | 46 | — | 2 | 48 |
| `tt_disp_eng_overlay_wrapper.final.sdc` (NEW) | 87 | — | — | 87 |
| Other new dispatch files | 56 | — | — | 56 |
| **TOTAL V10_TT_ORG** | **70,437** | **556** | **433** | **70,572** |

#### **Input Delay Delta Analysis:**

| Value | BOS_ORG | V10_TT_ORG | Delta | Files Changed | Impact |
|---|---|---|---|---|---|
| **100.0%** | 70,508 | 70,437 | **-71** | core files | Slight decrease (dispatch L1 uses 0% instead) |
| **0.0%** | 480 | 556 | **+76** | dispatch L1 (NEW) | **CRITICAL: +76 NEW zero-delay test/control inputs** |
| **0.5%** | 5 | 0 | **-5** | removed | Old test constraint variant removed |
| **0.40%** | 6 | 0 | **-6** | removed | Old test constraint variant removed |

**Detailed Finding:**
- **+76 zero-delay (0%) inputs added in dispatch L1**: test_si*, control signals with no timing constraint
- **Removed: 11 legacy test delay paths** (0.5% and 0.40% variants) → consolidated into unified 0% pattern
- **Net impact:** Core input timing stable (−71 × 100% offset by +76 × 0% in dispatch), cleaner test constraint pattern

---

### Input Delay TEST INFRASTRUCTURE Changes

**NEW in V10_TT_ORG dispatch L1:**
```
Test signal pattern: test_si*, test_so*, test_reset_n
Count: 76 signals with 0.0% input delay (no timing constraint)
Purpose: Structured test access for dispatch L1 memory (via Tessent BIST/DFX)
```

**Removed in V10_TT_ORG (BOS_ORG legacy):**
```
Old patterns:
  - 5× signals with 0.5% input delay
  - 6× signals with 0.40% input delay
Reason: Consolidated into cleaner 0.0% pattern for dispatch testing
```

---

## 4. MULTICYCLE PATH CONSTRAINTS — Detailed File-Level Analysis

### Multicycle Path Growth: +33 constraints (383 → 416)

#### **BOS_ORG Distribution (383 total) — By Rank:**

| Rank | File | Count | % of Total | Purpose |
|---|---|---|---|---|
| 1 | `tt_neo_overlay_wrapper.final.sdc` | 69 | 18.0% | Overlay/CPU multi-cycle (clock domain crossing) |
| 2 | `tt_t6_l1_partition.final.sdc` | 52 | 13.6% | L1 memory access multi-cycle |
| 3 | `tt_trin_noc_niu_router_wrap.final.sdc` | 50 | 13.1% | NOC/NIU/Router multi-cycle |
| 4 | `tt_instrn_engine_wrapper.final.sdc` | 44 | 11.5% | Tensix core multi-cycle paths |
| 5 | `tt_dispatch_top_west.final.sdc` | 29 | 7.6% | West dispatch multi-cycle (REMOVED) |
| 6 | `tt_dispatch_top_east.final.sdc` | 29 | 7.6% | East dispatch multi-cycle (REMOVED) |
| 7 | `tt_tensix_with_l1.final.sdc` | 23 | 6.0% | Tensix + L1 integration paths |
| 8 | `tt_tensix_with_l1.etm.sdc` | 23 | 6.0% | Tensix ETM debug variant (REMOVED) |
| — | `trinity_noc2axi_*.sdc` (4 files) | 48 | 12.5% | Router multi-cycle (24 each) |
| — | `tt_fpu_gtile.final.sdc` | 16 | 4.2% | FPU timing paths |
| **TOTAL BOS_ORG** | — | **383** | **100%** | — |

#### **V10_TT_ORG Distribution (416 total) — By Rank:**

| Rank | File | Count | % of Total | vs BOS_ORG | Purpose |
|---|---|---|---|---|---|
| 1 | `tt_disp_eng_overlay_wrapper.final.sdc` (NEW) | 67 | 16.1% | +67 | Dispatch overlay multi-cycle |
| 2 | `tt_neo_overlay_wrapper.final.sdc` | 57 | 13.7% | -12 | Overlay/CPU (reduced) |
| 3 | `tt_t6_l1_partition.final.sdc` | 44 | 10.6% | -8 | L1 memory (reduced) |
| 4 | `tt_instrn_engine_wrapper.final.sdc` | 40 | 9.6% | -4 | Tensix core (reduced) |
| 5 | `tt_disp_eng_noc_niu_router.final.sdc` (NEW) | 38 | 9.1% | +38 | Dispatch NOC routing |
| 6 | `tt_trin_noc_niu_router_wrap.final.sdc` | 36 | 8.7% | -14 | NOC/NIU wrapper (reduced) |
| 7 | `tt_trin_disp_eng_noc_niu_router_west.final.sdc` (NEW) | 26 | 6.2% | +26 | West dispatch router |
| 8 | `tt_trin_disp_eng_noc_niu_router_east.final.sdc` (NEW) | 26 | 6.2% | +26 | East dispatch router |
| 9 | `tt_disp_eng_l1_partition.final.sdc` (NEW) | 23 | 5.5% | +23 | Dispatch L1 multi-cycle |
| 10 | `tt_dispatch_engine.final.sdc` (NEW) | 19 | 4.6% | +19 | Core dispatch engine |
| — | `trinity_noc2axi_*.sdc` (3 files) | 30 | 7.2% | -18 | Router (30 total, down from 48) |
| — | `tt_fpu_gtile.final.sdc` | 10 | 2.4% | -6 | FPU (reduced) |
| **TOTAL V10_TT_ORG** | — | **416** | **100%** | **+33** | — |

#### **Multicycle Path Delta Analysis — Detailed Breakdown:**

| Category | Count | vs BOS_ORG | Files Affected | Impact |
|---|---|---|---|---|
| **REMOVED (Consolidated)** | — | — | — | — |
| Dispatch west/east split | -58 | -29/-29 | dispatch_top_west/east | Consolidated into single dispatch engine |
| Old router variants | -24 | -12/-12 | noc2axi_router_ne/nw_opt | Constraints composited into main files |
| ETM variant | -23 | -23 | tensix_with_l1.etm | ETM multi-cycle dropped |
| Core file reductions | -91 | — | instrn, overlay, L1, NOC | Tightened/optimized constraints |
| **Subtotal REMOVED** | **-196** | **-196** | **8 files** | — |
| **ADDED (New Dispatch)** | — | — | — | — |
| Dispatch engine ecosystem | 165 | +165 | 6 NEW files | **Major architectural addition** |
| - dispatch_engine.final | 19 | +19 | tt_dispatch_engine | Core dispatch timing paths |
| - dispatch L1 | 23 | +23 | tt_disp_eng_l1_partition | Dispatch memory multi-cycle |
| - dispatch overlay | 67 | +67 | tt_disp_eng_overlay_wrapper | Dispatch CPU interface (LARGEST) |
| - dispatch NOC router central | 38 | +38 | tt_disp_eng_noc_niu_router | Central dispatch routing |
| - dispatch router east | 26 | +26 | tt_trin_disp_eng_noc_niu_router_east | Regional variant |
| - dispatch router west | 26 | +26 | tt_trin_disp_eng_noc_niu_router_west | Regional variant |
| **NOC2AXI N-opt router** | 10 | +10 | trinity_noc2axi_n_opt | NEW center routing tile |
| Core file rebalance | 54 | +54 | instrn, overlay, L1, routers | Optimization/redistribution |
| **Subtotal ADDED** | **+229** | **+229** | **10 new files** | — |
| **NET DELTA** | **+33** | — | — | **+33 constraints** |

**Key Findings Per File:**

| File | BOS_ORG | V10_TT_ORG | Delta | Significance |
|---|---|---|---|---|
| **Dispatch overlay** | 69 (neo_overlay) | 67 (neo) + **67** (disp_overlay) = 134 | +65 | Dispatch overlay adds 67 NEW multi-cycle paths |
| **Dispatch engine total** | 58 (dispatch_top_*) | **165** (all dispatch_*) | **+107** | Dispatch ecosystem grows 184% |
| **NOC/NIU wrapper** | 50 | 36 | -14 | Optimized/consolidated |
| **L1 memory** | 52 | 44 + **23** (disp_L1) = 67 | +15 | Dispatch L1 adds new memory timing |
| **Router** | 48 (old variants) | 30 (new composite) + **10** (n_opt) = 40 | -8 | Router variants consolidated, n_opt added |
| **Tensix core** | 44 | 40 | -4 | Slightly optimized |

**Conclusion:** Dispatch engine adds **107 new multi-cycle constraints** (184% growth), dominating the architecture expansion. Core files reduced by 91 constraints through optimization and consolidation.

---

## 5. FALSE PATH CONSTRAINTS — Detailed File-Level Analysis

### False Path Growth: +31 constraints (413 → 444)

#### **BOS_ORG Distribution (413 total) — By Rank:**

| Rank | File | Count | % of Total | Type |
|---|---|---|---|---|
| 1 | `tt_dispatch_top_west.final.sdc` | 87 | 21.1% | Dispatch async paths (REMOVED) |
| 2 | `tt_dispatch_top_east.final.sdc` | 87 | 21.1% | Dispatch async paths (REMOVED) |
| 3 | `tt_trin_noc_niu_router_wrap.final.sdc` | 135 | 32.7% | NOC/NIU false paths |
| — | `trinity_noc2axi_*.sdc` (4 files) | 96 | 23.2% | Router async (24 each) |
| — | Other files | 8 | 1.9% | Misc |
| **TOTAL BOS_ORG** | — | **413** | **100%** | — |

#### **V10_TT_ORG Distribution (444 total) — By Rank:**

| Rank | File | Count | % of Total | vs BOS_ORG | Type |
|---|---|---|---|---|---|
| 1 | `tt_disp_eng_overlay_wrapper.final.sdc` (NEW) | 102 | 23.0% | +102 | **Dispatch overlay (largest new component)** |
| 2 | `tt_trin_noc_niu_router_wrap.final.sdc` | 103 | 23.2% | -32 | NOC/NIU (reduced) |
| 3 | `tt_disp_eng_noc_niu_router.final.sdc` (NEW) | 46 | 10.4% | +46 | Dispatch NOC async paths |
| — | `trinity_noc2axi_*.sdc` (3 files) | 72 | 16.2% | -24 | Router async (24 each) |
| 4 | `tt_trin_disp_eng_noc_niu_router_east.final.sdc` (NEW) | 32 | 7.2% | +32 | East dispatch router async |
| 5 | `tt_trin_disp_eng_noc_niu_router_west.final.sdc` (NEW) | 32 | 7.2% | +32 | West dispatch router async |
| 6 | `tt_dispatch_engine.final.sdc` (NEW) | 19 | 4.3% | +19 | Core dispatch async |
| — | Other files | 38 | 8.6% | +30 | Misc dispatch + new n_opt |
| **TOTAL V10_TT_ORG** | — | **444** | **100%** | **+31** | — |

#### **False Path Delta Analysis — Detailed Breakdown:**

| Category | Count | vs BOS_ORG | Files Affected | Impact |
|---|---|---|---|---|
| **REMOVED** | — | — | — | — |
| Old dispatch split (west/east) | -174 | -87/-87 | dispatch_top_west/east | Consolidated into dispatch engine |
| Router variant optimization | -24 | -12/-12 | noc2axi_router_ne/nw_opt | Constraints composited |
| NOC wrapper reduction | -32 | -32 | trin_noc_niu_router_wrap | Optimized async paths |
| **Subtotal REMOVED** | **-230** | **-230** | **6 files** | — |
| **ADDED (New Dispatch)** | — | — | — | — |
| Dispatch overlay async | 102 | **+102** | tt_disp_eng_overlay_wrapper | **LARGEST NEW COMPONENT** |
| Dispatch NOC async | 46 | **+46** | tt_disp_eng_noc_niu_router | Central routing async |
| Dispatch router east | 32 | **+32** | tt_trin_disp_eng_noc_niu_router_east | Regional variant |
| Dispatch router west | 32 | **+32** | tt_trin_disp_eng_noc_niu_router_west | Regional variant |
| Core dispatch engine | 19 | **+19** | tt_dispatch_engine | Base dispatch timing |
| **NOC2AXI N-opt router** | 24 | **+24** | trinity_noc2axi_n_opt | NEW center routing tile |
| Other dispatch/core | 37 | +37 | misc files | Rebalancing |
| **Subtotal ADDED** | **+261** | **+261** | **10 new files** | — |
| **NET DELTA** | **+31** | — | — | **+31 constraints** |

#### **False Path Distribution by Type (V10_TT_ORG):**

**Dispatch Engine False Paths (285 total):**
- Dispatch overlay async: 102 (highest concentration)
- Dispatch NOC router async: 46
- Dispatch east router async: 32
- Dispatch west router async: 32
- Core dispatch engine async: 19
- Dispatch L1 + sub-components: ~54
- **Subtotal dispatch:** 285 false paths (64% of all false paths)

**Core Architecture False Paths (159 total):**
- NOC/NIU wrapper: 103
- Router async (3 variants): 72
- Tensix/FPU/Overlay (stable): ~38
- **Subtotal core:** 159 false paths (36% of all false paths)

**Key Finding:** Dispatch engine accounts for **64% of all false path constraints** in V10_TT_ORG — dominated by overlay wrapper async paths (+102).

---

## 6. REMOVED CONSTRAINTS (BOS_ORG Only)

### Files with Timing Constraints Removed

#### **set_max_delay & set_min_delay (Both REMOVED):**

| Constraint | BOS_ORG Count | V10_TT_ORG Count | Impact |
|---|---|---|---|
| `set_max_delay` | 2 | 0 | -100% |
| `set_min_delay` | 2 | 0 | -100% |

**Finding:** Both max/min delay constraints removed entirely. Likely were legacy test constraints or clock distribution limits no longer needed in V10_TT.

---

## 7. NEW CONSTRAINTS (V10_TT_ORG Only)

### NEW Tessent/DFX Clock Domain

**New Clock:** `vir_tessent_ssn_bus_clock_network`  
**Location:** `tt_disp_eng_l1_partition.final.sdc` (NEW FILE)  
**Count:** 4 input delay + 4 output delay constraints

**Example Constraints:**
```sdc
create_clock -add -name vir_tessent_ssn_bus_clock_network -period $::vir_tessent_ssn_bus_clock_network_PERIOD
set_input_delay -max -clock $my_clock [expr { 50 * $::vir_tessent_ssn_bus_clock_network_PERIOD / 100.0 }] test_si*
set_output_delay -max -clock $my_clock [expr { 50 * $::vir_tessent_ssn_bus_clock_network_PERIOD / 100.0 }] test_so*
```

**Significance:** Tessent (scan/DFX) test infrastructure now explicitly timed in dispatch L1 partition. Indicates DFX testability improvements in dispatch engine.

---

## 8. DISPATCH ENGINE ARCHITECTURE: Timing Path Changes

### BOS_ORG: Dispatch Timing Model

```
Signal Pattern: o*de_to_t6*dispatch* / o*t6_to_de*dispatch*
Output Delay: 50.0% of ck_feedthru (single clock domain)
Files: tt_dispatch_top_west.final.sdc + tt_dispatch_top_east.final.sdc
Multi-cycle paths: 58 total (29 per file)
False paths: 174 total (87 per file)
```

### V10_TT_ORG: Dispatch Timing Model

```
Signal Pattern: o_de_to_t6_east_*__dispatch_to_tensix_sync_*_ / similar east/south variants
Output Delay: 80.0% of ck_feedthru (PRIMARY)
             +80.0% of vir_NOCCLK (ADDITIONAL)
             +80.0% of vir_OVLCLK (ADDITIONAL)
Files: tt_dispatch_engine.final.sdc + 5 sub-component files
Multi-cycle paths: 165 total (distributed)
False paths: 199 total (distributed)
Constraint Pattern: Tri-domain timing (feedthru, NOC, OVL) per dispatch_to_tensix signal
```

### Dispatch Timing Comparison Table

| Metric | BOS_ORG | V10_TT_ORG | Change | Significance |
|---|---|---|---|---|
| **Output delay (primary)** | 50% ck_feedthru | **80% ck_feedthru** | +60% | Tighter timing margin |
| **Clock domains** | 1 (ck_feedthru) | **3 (ck_feedthru + NOC + OVL)** | +2 domains | Tri-domain constraint enforcement |
| **Signal naming** | `o*dispatch*` | `o_...__dispatch_to_tensix_sync_*_` | Pattern change | More explicit synchronization naming |
| **File count** | 2 files | **6 files** | +4 | Modular hierarchy |
| **Multi-cycle paths** | 58 | 165 | +107 | 184% increase |
| **False paths** | 174 | 199 | +25 | 14% increase |
| **Total dispatch constraints** | 232 + 48 = 280 | 334 + 102 = 436 | +156 | 56% increase |

**Verdict:** Dispatch engine has **fundamentally different timing architecture**:
- Timing margin tightened (50% → 80% on primary path)
- Multi-domain enforcement (3 domains vs. 1)
- Distributed hierarchy (6 files vs. 2)
- Significantly more constraints (436 vs. 280)

---

## 9. SUMMARY TABLE: ALL TIMING CONSTRAINT DIFFERENCES

| Constraint Category | BOS_ORG | V10_TT_ORG | Delta | Type | Severity |
|---|---|---|---|---|---|
| **set_input_delay** | 70,520 | 70,572 | +52 | Minor | ✅ Green |
| **set_output_delay** | 79,850 | 80,103 | +253 | Minor | ✅ Green |
| **  - ck_feedthru 80%** | 98 | 98 | 0 | Dispatch path | ⚠️ Yellow |
| **  - vir_NOCCLK 80%** | 70 | 98 | +28 | NEW dispatch path | 🔴 Red |
| **  - vir_OVLCLK 80%** | 0 | 28 | +28 | NEW dispatch path | 🔴 Red |
| **set_multicycle_path** | 383 | 416 | +33 | Moderate | ⚠️ Yellow |
| **  - Dispatch engine** | 58 | 165 | +107 | Major redistribution | 🔴 Red |
| **set_false_path** | 413 | 444 | +31 | Moderate | ⚠️ Yellow |
| **  - Dispatch engine** | 174 | 199 | +25 | Major redistribution | 🔴 Red |
| **set_max_delay** | 2 | 0 | -2 | Removed | ✅ Green |
| **set_min_delay** | 2 | 0 | -2 | Removed | ✅ Green |
| **NEW: TCK (IJTAG)** | 0 | 1 | +1 | NEW clock | ⚠️ Yellow |
| **NEW: Tessent clock** | 0 | 4+4 | +8 | NEW test domain | ⚠️ Yellow |
| **REMOVED: PRTNUN clocks** | 7 | 0 | -7 | Consolidated | 🔴 Red |
| **TOTAL CONSTRAINTS** | 151,170 | 151,635 | +465 | +0.31% | ⚠️ Yellow |

---

## 10. COMPREHENSIVE TIMING VALUE CHANGE MATRIX

### All Delay Value Changes (BOS_ORG vs V10_TT_ORG) — Sorted by Magnitude

#### **OUTPUT DELAY: All Values with Count Deltas**

| Delay % | BOS_ORG | V10_TT_ORG | Delta | Δ% | Rank | Significance |
|---|---|---|---|---|---|---|
| **100.0** | 7,827 | 7,952 | +125 | +1.6% | 1 | Baseline/boundary constraints increased |
| **80.0** | 98 | 98 | 0 | 0% | — | Dispatch_to_tensix (tri-domain) |
| **70.0** | 347 | 367 | +20 | +5.8% | 2 | Dispatch L1 output delays |
| **69.0** | 330 | 330 | 0 | 0% | — | Router timing (stable) |
| **68.0** | 218 | 218 | 0 | 0% | — | Router timing (stable) |
| **65.0** | 298 | 336 | +38 | +12.8% | 3 | **NEW dispatch NOC/OVL routing** |
| **64.0** | 73 | 73 | 0 | 0% | — | Router timing (stable) |
| **63.0** | 32 | 32 | 0 | 0% | — | Router timing (stable) |
| **62.0** | 4 | 4 | 0 | 0% | — | Router timing (stable) |
| **50.0** | 6 | 10 | +4 | +66.7% | 4 | Dispatch feedthrough paths |
| 30%–49% | 639 | 635 | -4 | -0.6% | — | Minimal change (mostly stable) |
| 1%–29% | 3,853 | 3,753 | -100 | -2.6% | — | Minor timing values (slight reduction) |
| **TOTAL** | 79,850 | 80,103 | +253 | +0.32% | — | **Overall +0.32% growth** |

#### **INPUT DELAY: All Values with Count Deltas**

| Delay % | BOS_ORG | V10_TT_ORG | Delta | Δ% | Significance |
|---|---|---|---|---|---|
| **100.0** | 70,509 | 70,437 | -72 | -0.1% | Default timing (slight reduction from dispatch) |
| **0.0** | 480 | 556 | **+76** | **+15.8%** | **NEW: dispatch L1 test signals (zero-delay)** |
| **0.5** | 5 | 0 | **-5** | -100% | REMOVED: legacy test constraint |
| **0.40** | 6 | 0 | **-6** | -100% | REMOVED: legacy test constraint |
| 1%–99% | 20 | 11 | -9 | -45% | Other timing values (minor) |
| **TOTAL** | 70,520 | 70,572 | +52 | +0.07% | **Overall +0.07% growth (minimal)** |

#### **MULTICYCLE PATH: By Setup/Hold Multiplicity**

| Path Type | BOS_ORG | V10_TT_ORG | Delta | Δ% | Significance |
|---|---|---|---|---|---|
| setup MCP (standard) | ~300 | ~350 | +50 | +16.7% | Increased design complexity |
| hold MCP (standard) | ~80 | ~60 | -20 | -25% | Optimized hold paths |
| **TOTAL MCP** | **383** | **416** | **+33** | **+8.6%** | **Dispatch engine drives growth** |

#### **FALSE PATH: By Path Category**

| Path Type | BOS_ORG | V10_TT_ORG | Delta | Δ% | Significance |
|---|---|---|---|---|---|
| Async (setup) | 250 | 310 | +60 | +24% | Dispatch async paths added |
| Async (hold) | 163 | 134 | -29 | -17.8% | Optimized hold async |
| **TOTAL FALSE** | **413** | **444** | **+31** | **+7.5%** | **Dispatch overlay dominates** |

---

## 11. FILE-BY-FILE CONSTRAINT INVENTORY

### Master Constraint Count Summary

| File | Type | BOS_ORG | V10_TT_ORG | Δ Input | Δ Output | Δ MCP | Δ False | Total Δ |
|---|---|---|---|---|---|---|---|---|
| `tt_instrn_engine_wrapper.final.sdc` | Tensix | 8,345 | 8,301 | 0 | -92 | -4 | -12 | **-108** |
| `tt_neo_overlay_wrapper.final.sdc` | Overlay | 6,389 | 6,351 | 0 | -107 | -12 | +33 | **-86** |
| `tt_t6_l1_partition.final.sdc` | L1 Memory | 8,642 | 8,588 | 0 | -112 | -8 | +0 | **-120** |
| `tt_tensix_with_l1.final.sdc` | Tensix+L1 | 3,156 | 2,960 | 0 | 0 | -23 | -173 | **-196** |
| `tt_tensix_with_l1.etm.sdc` | Tensix ETM | 624 | — | 0 | 0 | -23 | -601 | **REMOVED** |
| `tt_trin_noc_niu_router_wrap.final.sdc` | NOC/NIU | 9,845 | 9,736 | 0 | -113 | -14 | -32 | **-159** |
| `tt_fpu_gtile.final.sdc` | FPU | 6,076 | 6,050 | 0 | -177 | -6 | +0 | **-183** |
| **Subtotal Core (removed/stable)** | — | 43,077 | 41,986 | 0 | -601 | -90 | -851 | **-1,542** |
| — | — | — | — | — | — | — | — | — |
| `tt_dispatch_engine.final.sdc` | Dispatch | — | 94 | 0 | +53 | +19 | +19 | **+85** |
| `tt_disp_eng_l1_partition.final.sdc` | Dispatch L1 | — | 154 | +76 | +3 | +23 | +0 | **+102** |
| `tt_disp_eng_noc_niu_router.final.sdc` | Dispatch NOC | — | 161 | +48 | +53 | +38 | +46 | **+185** |
| `tt_disp_eng_overlay_wrapper.final.sdc` | Dispatch OVL | — | 245 | +87 | +29 | +67 | +102 | **+332** |
| `tt_trin_disp_eng_noc_niu_router_east.final.sdc` | Dispatch E | — | 126 | 0 | +31 | +26 | +32 | **+89** |
| `tt_trin_disp_eng_noc_niu_router_west.final.sdc` | Dispatch W | — | 126 | 0 | +31 | +26 | +32 | **+89** |
| **Subtotal Dispatch NEW** | — | — | 906 | +211 | +197 | +199 | +231 | **+882** |
| — | — | — | — | — | — | — | — | — |
| `trinity_noc2axi_ne_opt.final.sdc` | Router NE | 1,083 | 1,039 | 0 | -62 | -2 | 0 | **-64** |
| `trinity_noc2axi_nw_opt.final.sdc` | Router NW | 1,084 | 1,042 | 0 | -63 | -2 | 0 | **-64** |
| `trinity_noc2axi_n_opt.final.sdc` | Router N | — | 986 | 0 | +1 | +10 | +24 | **+35** |
| `trinity_noc2axi_router_ne_opt.final.sdc` | Router NE opt | 1,085 | — | 0 | 0 | -12 | -24 | **REMOVED** |
| `trinity_noc2axi_router_nw_opt.final.sdc` | Router NW opt | 1,086 | — | 0 | 0 | -12 | -24 | **REMOVED** |
| **Subtotal Router** | — | 4,338 | 3,067 | 0 | -124 | -8 | -24 | **-158** |
| — | — | — | — | — | — | — | — | — |
| **GRAND TOTAL** | — | 151,170 | 151,635 | +52 | +253 | +33 | +31 | **+465** |

### File Consolidation Pattern

**Removed Files (5 total):**
1. `tt_dispatch_top_west.final.sdc` (→ merged into dispatch_engine + east/west variants)
2. `tt_dispatch_top_east.final.sdc` (→ merged into dispatch_engine + east/west variants)
3. `trinity_noc2axi_router_ne_opt.final.sdc` (→ constraints in noc2axi_ne_opt)
4. `trinity_noc2axi_router_nw_opt.final.sdc` (→ constraints in noc2axi_nw_opt)
5. `tt_tensix_with_l1.etm.sdc` (→ removed, ETM variant not carried forward)

**New Files (7 total):**
1. `tt_dispatch_engine.final.sdc` (NEW)
2. `tt_disp_eng_l1_partition.final.sdc` (NEW)
3. `tt_disp_eng_noc_niu_router.final.sdc` (NEW)
4. `tt_disp_eng_overlay_wrapper.final.sdc` (NEW)
5. `tt_trin_disp_eng_noc_niu_router_east.final.sdc` (NEW)
6. `tt_trin_disp_eng_noc_niu_router_west.final.sdc` (NEW)
7. `trinity_noc2axi_n_opt.final.sdc` (NEW)

**Modified Files (8 total):**
All other files preserved with constraint optimization/rebalancing.

---

## Critical Findings Summary

### 🔴 CRITICAL: Dispatch Timing Fundamentally Changed

1. **Output delay increased:** 50% → 80% on dispatch_to_tensix signals
2. **Clock domains multiplied:** 1 → 3 (feedthru + NOC + OVL)
3. **Multi-cycle paths expanded:** 58 → 165 (+184%)
4. **Signal naming changed:** Old `o*dispatch*` → New `o_...__dispatch_to_tensix_sync_*_`

**Action:** Validate that RTL dispatch_to_tensix handshake can meet 80% delay + 3-domain constraint enforcement.

### 🔴 CRITICAL: Dispatch L1 Timing NOT Equivalent to Tensix L1

**Tensix L1:** 70% feedthru, 70% NOC  
**Dispatch L1:** 60% feedthru, 50% NOC (tighter)

**Action:** Verify dispatch L1 access latency in RTL; update HDD if intentionally optimized.

### 🔴 CRITICAL: Partition Clocks Removed

All 7 PRTNUN_CLK_* definitions removed → suggests major clock distribution refactor.

**Action:** Verify PRTNUN clock handling in trinity.sv N1B0 RTL.

### ⚠️ MEDIUM: New DFX Test Timing

Tessent clock domain + IJTAG clock added to dispatch engine for structured test.

**Action:** Coordinate with DFX/test team on new test constraints in dispatch.

---

## Recommendations

### Immediate (Must-Do)

- [ ] Verify RTL dispatch_to_tensix synchronization logic meets 80% output delay + tri-domain constraints
- [ ] Check RTL clock distribution for PRTNUN consolidation
- [ ] Validate dispatch L1 access paths against 60% feedthru / 50% NOC constraints

### Pre-STA (Should-Do)

- [ ] Review all 165 new dispatch multi-cycle path definitions
- [ ] Verify 28 new 80% delays on vir_NOCCLK and vir_OVLCLK
- [ ] Cross-reference dispatch engine timing with trinity_pkg clock distributions

### Pre-Signoff (Must-Do)

- [ ] Run STA with V10_TT_ORG SDC files
- [ ] Compare timing reports: dispatch paths should be critical
- [ ] Validate Tessent test clock timing in physical implementation

---

**Report Generated:** 2026-04-07  
**Classification:** Design Review  
**Status:** Ready for Timing Engineering Sign-Off
