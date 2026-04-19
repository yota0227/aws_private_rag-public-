# SDC Constraint Comparison: CSV Files Guide
**Date:** 2026-04-08  
**Comparison Scope:** BOS_ORG vs V10_TT_ORG  
**Total Constraints Analyzed:** 151,170 → 151,635

---

## CSV File Overview

### 1. **[sdc_constraint_comparison.csv](sdc_constraint_comparison.csv)** — Master Constraint Type Summary
**Purpose:** High-level overview of all constraint types and their counts  
**Structure:** 12 rows (constraint types) + header  
**Key Columns:**
- `No.`: Ranking (1–12)
- `Check`: `O` (unchanged) or `X` (changed)
- `Constraint Type`: create_clock, set_output_delay, set_multicycle_path, etc.
- `BOS_ORG Count`: Exact count in BOS_ORG
- `V10_TT_ORG Count`: Exact count in V10_TT_ORG
- `Delta`: Numerical change
- `Δ%`: Percentage change
- `Status`: CRITICAL, CHANGED, STABLE, NEW, REMOVED, REDUCED
- `Difference Summary`: Concise description of what changed
- `BOS_ORG Example`: Sample constraint from BOS_ORG files
- `V10_TT_ORG Example`: Sample constraint from V10_TT_ORG files

**Quick Facts:**
```
✅ STABLE (Check=O):
  - create_generated_clock: 3 → 3 (0%)
  
❌ CRITICAL (Check=X):
  - create_clock: 133 → 113 (-15%) [PRTNUN removed]
  - set_input_delay: 70,495 → 70,572 (+77) [+76 test]
  - set_output_delay: 79,827 → 80,103 (+276) [tri-domain]
  - set_multicycle_path: 176 → 165 (-11) [+165 dispatch, −132 core]
  - set_false_path: 185 → 211 (+26) [+205 dispatch, −174 old]
  
🆕 NEW (Check=X):
  - set_clock_uncertainty: 1 → 464 (+463) [dispatch skew]
  - set_propagated_clock: 0 → 1 [dispatch]
```

---

### 2. **[sdc_detailed_examples.csv](sdc_detailed_examples.csv)** — Detailed Value-Level Changes
**Purpose:** Line-by-line constraint examples showing actual timing values  
**Structure:** 35 rows covering all constraint categories  
**Key Columns:**
- `No.`: Row number (1–35)
- `Check`: `O` or `X`
- `Category`: CLOCK DEFINITIONS, OUTPUT_DELAY, INPUT_DELAY, MULTICYCLE_PATH, FALSE_PATH, CRITICAL_FINDING, etc.
- `Constraint Pattern`: Specific constraint type/variant
- `BOS_ORG Files`: Which files contain this constraint in BOS_ORG
- `V10_TT_ORG Files`: Which files contain this constraint in V10_TT_ORG
- `Value Example BOS_ORG`: Actual value from SDC file (e.g., "70%", "50% ck_feedthru")
- `Value Example V10_TT_ORG`: Actual value from SDC file (e.g., "80%", "60% feedthru + 50% NOC")
- `Delta`: Change in value or count
- `Severity`: LOW, MEDIUM, HIGH, CRITICAL
- `Notes`: Additional context

**Critical Findings Section:**
- Row 32: Tri-Domain Dispatch Timing (147 paths across 3 clocks)
- Row 33: L1 Timing Divergence (60/50% vs 70/70% timing)
- Row 34: Partition Clock Consolidation (7 clocks removed)
- Row 35: Summary (overall +465, +0.31%)

---

### 3. **[sdc_command_patterns.csv](sdc_command_patterns.csv)** — Exact SDC Command Patterns
**Purpose:** Detailed command syntax comparison for technical review  
**Structure:** 30 rows showing actual SDC commands from both versions  
**Key Columns:**
- `No.`: Row number (1–30)
- `Check`: `O` or `X`
- `Command Category`: create_clock, set_output_delay, set_multicycle_path, etc.
- `Sub-Pattern`: Specific variant (e.g., "Primary Clock", "Test Input", "Routing")
- `BOS_ORG Pattern`: Actual TCL command from BOS_ORG files
- `V10_TT_ORG Pattern`: Actual TCL command from V10_TT_ORG files
- `Files Modified`: Which SDC files include this pattern
- `Value Changes`: Specific timing/parameter changes
- `Status`: STABLE, CHANGED, CRITICAL, REMOVED, NEW
- `Notes`: Technical implications

**Useful Patterns:**
- Rows 1–8: Clock definitions (stable core, new test clocks)
- Rows 9–15: Input/output delay patterns (tri-domain, test signals)
- Rows 16–23: Multi-cycle, false path, transition, uncertainty patterns
- Rows 24–30: Group patterns and high-level architecture changes

---

## How to Use These CSVs

### For Quick Status Review (5 min)
→ **Use:** `sdc_constraint_comparison.csv`
1. Open CSV in Excel/LibreOffice
2. Sort by `Status` column (CRITICAL first)
3. Review `Delta` and `Δ%` columns for major changes
4. Read `Difference Summary` for context

**Key Rows to Review:**
- Row 4: set_output_delay (CRITICAL — tri-domain)
- Row 5: set_multicycle_path (CRITICAL — +165 dispatch)
- Row 6: set_false_path (CRITICAL — +205 dispatch)
- Row 8: set_clock_uncertainty (NEW — +463 dispatch)

---

### For Detailed Engineering Review (30 min)
→ **Use:** `sdc_detailed_examples.csv`
1. Filter by `Severity` = CRITICAL or HIGH
2. Compare `Value Example BOS_ORG` vs `Value Example V10_TT_ORG`
3. Review `Category` column to group related changes
4. Pay special attention to rows 32–34 (critical findings)

**Critical Analysis Points:**
- Row 7–11: Output delay value progression
- Row 14–15: L1 memory timing divergence (60% vs 70%)
- Row 20–21: Dispatch overlay async path explosion
- Row 30: Dispatch L1 vs Tensix L1 timing

---

### For RTL/SDC Integration Review (45 min)
→ **Use:** `sdc_command_patterns.csv`
1. For each changed command, compare `BOS_ORG Pattern` vs `V10_TT_ORG Pattern`
2. Look at `Files Modified` to identify affected RTL modules
3. Trace `Sub-Pattern` to understand constraint purpose
4. Review `Notes` for implications

**Integration Verification Points:**
- Row 6–7: TCK and Tessent clock routing (dispatch engine IJTAG)
- Row 12a–12c: Tri-domain constraint implementation (3 rows)
- Row 24: Dispatch signal naming changes (`o_de_to_t6_*__dispatch_to_tensix_sync_*_`)
- Row 25: Partition clock consolidation method
- Row 29–30: Pattern changes and new conventions

---

## Severity Legend

| Check | Severity | Color | Meaning | Action |
|---|---|---|---|---|
| **O** | GREEN (✅) | Low | Unchanged or minor change | Monitor only |
| **X** | YELLOW (⚠️) | Medium | Moderate change | Review & verify |
| **X** | ORANGE (🔴) | High | Significant change | Deep review required |
| **X** | RED (🔴) | Critical | Architectural change | RTL validation mandatory |

---

## Top 10 Changes to Review (Ranked by Impact)

| Rank | Change | Constraint | Count | File | Severity | CSV Location |
|---|---|---|---|---|---|---|
| 1 | Tri-domain dispatch_to_tensix timing | set_output_delay | +147 paths | dispatch_*.sdc | 🔴 CRITICAL | comparison:4, detailed:7-11, patterns:12a–12c |
| 2 | Dispatch multicycle explosion | set_multicycle_path | +165 paths | dispatch_*.sdc | 🔴 CRITICAL | comparison:5, detailed:16 |
| 3 | Dispatch false path explosion | set_false_path | +205 paths | dispatch_overlay.sdc | 🔴 CRITICAL | comparison:6, detailed:20–21 |
| 4 | Clock uncertainty NEW | set_clock_uncertainty | +463 instances | dispatch_*.sdc | 🔴 CRITICAL | comparison:8, patterns:19 |
| 5 | L1 timing divergence | set_output_delay | 60% vs 70% | disp_eng_l1.sdc | 🔴 CRITICAL | detailed:14–15, patterns:30 |
| 6 | Partition clock removal | create_clock | −7 clocks | removed | 🔴 CRITICAL | comparison:1, detailed:26, patterns:4–5 |
| 7 | Zero-delay test inputs | set_input_delay | +76 signals | disp_eng_l1.sdc | 🟠 HIGH | comparison:3, detailed:13, patterns:10 |
| 8 | Router consolidation | various | −24 variants | n_opt added | 🟠 HIGH | comparison:all, detailed:1–35 |
| 9 | Dispatch file restructuring | all types | +6 new files | dispatch_*.sdc | 🟠 HIGH | detailed:28–29, patterns:26 |
| 10 | NOC/OVLCLK routing timing | set_output_delay | +38 paths @ 65% | dispatch_*.sdc | 🟠 HIGH | detailed:10–11, patterns:13 |

---

## CSV Merge Instructions (For Full Analysis)

To combine all three CSVs into one master analysis:

```bash
# 1. Extract No. and Status from comparison.csv
# 2. Join with detailed_examples.csv on matching constraint type
# 3. Append command_patterns.csv as reference rows
# 4. Sort by Severity (CRITICAL, HIGH, MEDIUM, LOW)
# 5. Export as master_sdc_analysis.csv
```

---

## Verification Checklist Using CSVs

### Pre-RTL Validation (Use comparison.csv)
- [ ] Review all X rows (changed constraints)
- [ ] Identify which files are new (dispatch_*.sdc)
- [ ] Confirm file removals (dispatch_top_*/router_opt)
- [ ] Validate clock count changes (−20 clocks)

### RTL Integration (Use patterns.csv + comparison.csv)
- [ ] Verify TCK routing (dispatch_engine → IJTAG)
- [ ] Check tri-domain dispatch_to_tensix paths (rows 12a–12c)
- [ ] Validate L1 timing changes (60%/50% feasible in RTL)
- [ ] Confirm PRTNUN clock consolidation method

### STA Validation (Use detailed_examples.csv)
- [ ] Run STA with both SDC sets
- [ ] Compare timing reports (expect dispatch paths critical)
- [ ] Validate 147 tri-domain paths
- [ ] Confirm L1 timing divergence in reports

---

## Files Analyzed

**BOS_ORG Files (13 total):**
- trinity_noc2axi_ne_opt.final.sdc
- trinity_noc2axi_nw_opt.final.sdc
- trinity_noc2axi_router_ne_opt.final.sdc (REMOVED in V10_TT)
- trinity_noc2axi_router_nw_opt.final.sdc (REMOVED in V10_TT)
- tt_dispatch_top_east.final.sdc (REMOVED in V10_TT)
- tt_dispatch_top_west.final.sdc (REMOVED in V10_TT)
- tt_fpu_gtile.final.sdc
- tt_instrn_engine_wrapper.final.sdc
- tt_neo_overlay_wrapper.final.sdc
- tt_t6_l1_partition.final.sdc
- tt_tensix_with_l1.etm.sdc (REMOVED in V10_TT)
- tt_tensix_with_l1.final.sdc
- tt_trin_noc_niu_router_wrap.final.sdc

**V10_TT_ORG Files (14 total):**
- All BOS_ORG files (minus 5 removed) + 7 NEW dispatch files + 1 NEW router

---

## Document Cross-References

| Document | Purpose | Link |
|---|---|---|
| SDC Constraint Comparison CSV | Master constraint summary | sdc_constraint_comparison.csv |
| SDC Detailed Examples CSV | Value-level changes | sdc_detailed_examples.csv |
| SDC Command Patterns CSV | Exact SDC syntax | sdc_command_patterns.csv |
| Timing Analysis Report | Full detailed analysis | timing_constraint_diff_detail.md |
| Executive Summary | High-level overview | TIMING_ANALYSIS_EXECUTIVE_SUMMARY.md |
| Architecture Comparison | File inventory changes | compare_report.md |

---

## Quick Reference: Critical Constraint Changes

### Dispatch_to_Tensix Handshake (CRITICAL)
```
BOS_ORG:  50% ck_feedthru only (single clock)
V10_TT:   80% ck_feedthru + 80% vir_NOCCLK + 80% vir_OVLCLK (3 clocks)
Impact:   Timing margin tightened +60%; CDC complexity increased
Files:    tt_disp_eng_noc_niu_router.final.sdc + 3 dispatch routers
Count:    147 new constraints across 3 clock domains
CSV:      comparison.csv row 4, detailed.csv rows 7–11, patterns.csv rows 12a–12c
```

### Dispatch L1 Memory Timing (CRITICAL)
```
Tensix L1:    70% feedthru, 70% NOC
Dispatch L1:  60% feedthru, 50% NOC (tighter)
Impact:       NOT interchangeable; different access latency
Files:        tt_disp_eng_l1_partition.final.sdc
Count:        6 output delays @ 60% feedthru, 50% NOC
CSV:          detailed.csv rows 14–15, patterns.csv row 30
```

### Partition Clocks Removed (CRITICAL)
```
Removed:  PRTNUN_CLK_0/1/2/3, PRTNUN_CLK_FPU_L/R, PRTNUN_CLK_L1, PRTNUN_CLK_NOC_L1
Method:   Consolidated into dispatch_engine hierarchy (implicit)
Impact:   Clock distribution redesigned; verify PRTNUN removal in trinity.sv
CSV:      comparison.csv row 1, patterns.csv rows 4–5, detailed.csv row 26
```

---

**Status:** ✅ **All 3 CSV files ready for review**  
**Recommended Review Order:** comparison → detailed → patterns  
**Total Analysis Time:** 5 min (quick) → 45 min (full engineering review)

