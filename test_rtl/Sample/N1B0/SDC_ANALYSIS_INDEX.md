# SDC Timing Constraint Analysis — File Index
**Date:** 2026-04-08  
**Organization:** All SDC analysis files consolidated into 20260221/DOC/N1B0/  
**Scope:** BOS_ORG vs V10_TT_ORG comparison (both from 20260221 snapshot)

---

## Analysis Files (7 documents)

### 1. **Executive Summary**
📄 [TIMING_ANALYSIS_EXECUTIVE_SUMMARY.md](TIMING_ANALYSIS_EXECUTIVE_SUMMARY.md) (11.4 KB)
- One-page summary of all constraint changes
- 4 CRITICAL findings with value-level detail
- Verification checklist (RED/YELLOW/GREEN priorities)
- File-level removal/addition summary

### 2. **Master Comparison Report**
📄 [compare_report.md](compare_report.md) (20.6 KB)
- High-level overview of file architecture changes
- Dispatch hierarchy refactoring (west/east → consolidated engine)
- Router consolidation analysis
- Execution checklist and recommendations

### 3. **Detailed Timing Analysis**
📄 [timing_constraint_diff_detail.md](timing_constraint_diff_detail.md) (38.6 KB)
- 14 major sections covering all constraint types
- Output delay distribution by file & value
- Input delay breakdown (+76 zero-delay test signals)
- Multicycle path and false path ranking
- File-by-file constraint inventory (master summary table)

### 4. **CSV Files Guide & Usage**
📄 [SDC_COMPARISON_README.md](SDC_COMPARISON_README.md) (11.3 KB)
- How to use the three CSV files
- Quick reference (5 min), detailed review (30 min), full engineering review (45 min)
- Severity legend and verification checklists
- Top 10 changes ranked by impact

---

## Data Files (4 CSV exports)

### Constraint Type Summary
📊 [sdc_constraint_comparison.csv](sdc_constraint_comparison.csv) (3.5 KB)
- **12 rows** (constraint types) + header
- Check column (O=unchanged, X=changed)
- BOS_ORG count, V10_TT count, Delta, Δ%, Status
- Example constraints and difference summary

**Key metrics:**
- set_output_delay: +276 (CRITICAL)
- set_multicycle_path: -11 (CRITICAL)
- set_clock_uncertainty: +463 (NEW)

### Detailed Examples by Category
📊 [sdc_detailed_examples.csv](sdc_detailed_examples.csv) (5.4 KB)
- **35 rows** covering all constraint categories
- Value-level changes with actual constraint examples
- Categories: CLOCK DEFINITIONS, INPUT_DELAY, OUTPUT_DELAY, MULTICYCLE_PATH, FALSE_PATH, CRITICAL_FINDING, FILE_CHANGES, SUMMARY

**Critical rows:**
- Row 32: Tri-domain dispatch timing (+147 paths)
- Row 33: L1 timing divergence (60%/50% vs 70%/70%)
- Row 34: Partition clock removal (-7 clocks)

### Exact SDC Command Patterns
📊 [sdc_command_patterns.csv](sdc_command_patterns.csv) (7.9 KB)
- **30 rows** with exact SDC command syntax comparison
- BOS_ORG Pattern vs V10_TT_ORG Pattern (actual Tcl commands)
- Files Modified, Value Changes, Status
- Sub-patterns for clock definitions, timing constraints, removed constraints

**Example rows:**
- Row 12a-12c: Tri-domain dispatch_to_tensix (ck_feedthru + NOC + OVL @ 80%)
- Row 6-7: New test clocks (TCK, Tessent)

---

## How to Use This Collection

### For Quick Status (5 min)
→ Read **TIMING_ANALYSIS_EXECUTIVE_SUMMARY.md**  
→ Review **sdc_constraint_comparison.csv** (sorted by Status column)

### For Engineering Review (30 min)
→ Read **compare_report.md**  
→ Filter **sdc_detailed_examples.csv** by Severity = CRITICAL or HIGH  
→ Cross-reference with **timing_constraint_diff_detail.md** §2-5

### For RTL/SDC Integration (45 min)
→ Use **sdc_command_patterns.csv** for each changed command  
→ Cross-reference patterns with RTL files  
→ Verify clock distribution and constraint coupling

### For STA Validation
→ Collect all +CRITICAL rows from CSVs  
→ Focus on:
  - dispatch_to_tensix tri-domain timing (147 paths)
  - Dispatch L1 vs Tensix L1 timing divergence
  - New set_clock_uncertainty constraints (+463 instances)

---

## File Statistics

| File | Type | Size | Rows/Sections | Last Updated |
|------|------|------|---------------|--------------|
| TIMING_ANALYSIS_EXECUTIVE_SUMMARY | MD | 11.4 KB | 10 sections | 2026-04-08 |
| compare_report | MD | 20.6 KB | 6 sections | 2026-04-07 |
| timing_constraint_diff_detail | MD | 38.6 KB | 14 sections | 2026-04-08 |
| SDC_COMPARISON_README | MD | 11.3 KB | Guide + checklists | 2026-04-08 |
| sdc_constraint_comparison | CSV | 3.5 KB | 12 constraint types | 2026-04-08 |
| sdc_detailed_examples | CSV | 5.4 KB | 35 examples | 2026-04-08 |
| sdc_command_patterns | CSV | 7.9 KB | 30 command patterns | 2026-04-08 |
| **TOTAL** | — | **98.7 KB** | — | 2026-04-08 |

---

## Key Findings Summary

### CRITICAL Findings (RTL Validation Required)
1. **Tri-domain dispatch_to_tensix timing** — 147 new paths across 3 clock domains (ck_feedthru + NOC + OVL @ 80%)
2. **Dispatch L1 timing divergence** — 60%/50% vs Tensix L1 @ 70%/70% (NOT interchangeable)
3. **Partition clock consolidation** — 7 PRTNUN_CLK_* removed (consolidated into dispatch)
4. **Clock uncertainty explosion** — +463 instances (dispatch skew enforcement)

### Dispatch Engine Architecture Shift
- **Old model:** 2 files (dispatch_top_west/east), 280 constraints each, single-clock feedthru
- **New model:** 6 files (engine + L1 + overlay + 3 NOC routers), 882 total constraints, tri-domain enforcement

### File Changes
- **Removed:** 5 files (dispatch_top_*, router_*_opt variants, ETM variant)
- **Added:** 7 files (dispatch_engine ecosystem + router_n_opt)
- **Net:** +1 file (13 → 14), +465 constraints (+0.31%)

---

## Next Steps

### Pre-RTL Validation (Immediate)
- [ ] Verify V10_TT_ORG SDC scope matches RTL snapshot
- [ ] Identify RTL baseline for dispatch_engine and L1 partition
- [ ] Confirm PRTNUN clock removal in trinity.sv vs trinity_pkg.sv

### RTL Cross-Reference (Week 1)
- [ ] Validate dispatch_to_tensix signal naming matches SDC patterns
- [ ] Verify tri-domain CDC logic at NOC/OVL transitions
- [ ] Characterize dispatch L1 access latency vs Tensix L1

### STA Validation (Week 1–2)
- [ ] Run STA with V10_TT_ORG files against RTL
- [ ] Compare critical paths and slack reports (BOS_ORG vs V10_TT_ORG)
- [ ] Flag any setup/hold violations in dispatch region

### Physical Sign-Off (Week 2–3)
- [ ] P&R closure with new 80% timing margins (vs 50% baseline)
- [ ] Tessent test clock routing verification
- [ ] IJTAG clock distribution from dispatch engine
- [ ] Final STA with parasitics

---

**Status:** ✅ Analysis Complete  
**Location:** `/secure_data_from_tt/20260221/DOC/N1B0/`  
**Total Analysis Time:** 5 min (quick) → 45 min (full engineering review)

---

*All SDC analysis files for BOS_ORG vs V10_TT_ORG (20260221 snapshot) consolidated in this directory on 2026-04-08.*
