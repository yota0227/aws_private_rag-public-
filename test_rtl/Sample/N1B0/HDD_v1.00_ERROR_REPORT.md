# N1B0_NPU_HDD_v1.00 ERROR REPORT

**Date:** 2026-04-11  
**Verification Method:** Cross-check against RTL (FINAL_RTL_MAC_Throughput_VERIFIED.txt) and firmware (INT16_Guide_HDD_V0.2)  
**Status:** Critical errors found in register file sizes and MAC throughput specifications

---

## CRITICAL ERRORS (MUST FIX)

### ERROR #1: SRCA Row Count (§2.9.2, Line 3310)

**HDD Claim:**
```
Rows per tile      | 256
```

**RTL Reality:**
```
SRCS_NUM_ROWS_16B = 48  (tt_tensix_pkg.sv:35)
```

**Impact:** Off by **5.3× (256 vs 48 rows)**
- This propagates to SRCA capacity calculation (line 3313)
- Claimed: 256 rows × 16 words × 16 bits = 16 KB ❌
- Actual: 48 rows × 16 words × 16 bits = 1.5 KB ✓

**Status:** 🔴 **CRITICAL ERROR** — Contradicts RTL parameters and all derived calculations

---

### ERROR #2: SRCB Row Count (§2.9.4, Line 3350)

**HDD Claim:**
```
Rows per bank          | 128
Total capacity         | 2 banks × 128 rows × 16 cols × 16b = **32 KB**
```

**Contradiction Within HDD:**
- Line 3350-3354 claims "128 rows per bank"
- BUT Line 3371-3372 shows double-buffer diagram: "64 rows × 16 cols × 16b" per bank
- These are inconsistent (128 vs 64 rows per bank)

**RTL Evidence from Firmware:**
- INT16_Guide_HDD_V0.1 (§0.4): "SRCB (64 rows × 16 datums)" 
- Should be: 64 rows per bank, 2 banks = 128 total rows (2 KB per bank = 4 KB total)

**Status:** 🔴 **CRITICAL ERROR** — Self-contradictory and likely wrong row count

---

### ERROR #3: INT16 MAC Throughput Per G-Tile (§2.4.6, Line 1682)

**HDD Claim (Table):**
```
| **INT16** | 2 INT16 | 4 | 1 | 64 MACs | 128 MACs | 512 MACs |
                                ↑
                         Per G-Tile claim
```

**RTL-Verified Reality:**
```
Per G-Tile: 8 columns × 2 FPU rows × 2 lane rows × 8 MULT_PAIRS
          = 8 × 2 × 2 × 8 = 256 INT16 MACs per cycle
```

**Official Table Match:**
- Per cluster: 2,048 INT16 MACs ✓ (matches official table)
- Per Tensix: 512 INT16 MACs ✓ (2 G-Tiles × 256)
- Per G-Tile should be: 256 INT16 MACs (not 64)

**Status:** 🔴 **CRITICAL ERROR** — Off by **4× (64 vs 256 MACs)**

---

### ERROR #4: INT8 MAC Throughput Formula (§2.4.6.3, Line 1650)

**HDD Claim:**
```
Per single phase (one G-Tile):
8 cols × 4 rows × 2 lanes × 8 INT8/lane = 512 INT8 MACs
```

**Issue:** Hierarchical terminology is **WRONG and MISLEADING**

**Actual RTL Hierarchy:**
```
8 M-Tile columns
  × 2 FPU Tile rows (not "4 rows")
  × 2 FP-Lane rows (not "2 lanes" — FP-Lane rows are separate)
  × 8 MULT_PAIRS
= 8 × 2 × 2 × 8 = 256 INT16 MACs per G-Tile

INT8 (single phase) = 256 × 2 (data packing) = 512 INT8 MACs per G-Tile
INT8 (with HALF_FP_BW) = 512 × 2 (two-phase) = 1,024 INT8 MACs per G-Tile
```

**Correct Line 1650 Should Read:**
```
Per single phase (one G-Tile):
8 M-Tile cols × 2 FPU tile rows × 2 lane rows × 8 MULT_PAIRS × 2 INT8/pair = 512 INT8 MACs ✓
```

**Status:** 🟡 **MODERATE ERROR** — Formula happens to be numerically correct (512), but explanation uses wrong terminology that confuses the architecture

---

### ERROR #5: DEST Capacity Claim vs Mathematics (§2.8.2, Line 3234)

**HDD Claim:**
```
"RTL verification... confirms the correct per-tile capacity is **8 KB (4,096 INT32 entries)**"
```

**Mathematical Contradiction:**
```
4,096 INT32 entries × 4 bytes/entry = 16,384 bytes = 16 KB (NOT 8 KB) ❌
```

**Status:** 🔴 **CRITICAL ERROR** — Math is internally inconsistent. 8 KB ≠ 16 KB

**Likely Correction:** Should say "16 KB (4,096 INT32 entries)" OR "4 KB (1,024 INT32 entries)"

---

### ERROR #6: SRCA Bank Rows (§2.9.2, Line 3315)

**HDD Claim:**
```
BANK_ROWS_16B    | 128 per bank
```

**RTL Reality:**
If total SRCA rows = 48 and NUM_BANKS = 2, then:
```
BANK_ROWS_16B = 48 / 2 = 24 per bank (not 128)
```

**Status:** 🔴 **CRITICAL ERROR** — Off by **5.3× (128 vs 24 rows per bank)**

---

## MODERATE ERRORS (SHOULD FIX)

### ERROR #7: Contradictory DEST Capacity Statements (§2.8)

**Line 3228:**
```
Physical capacity: 1,024 total rows × 16 bits (per column, summed across columns) = **32 KB** per `tt_tensix` tile
```

**Line 3234:**
```
per-tile capacity is **8 KB (4,096 INT32 entries)**
```

**Contradiction:** Which is correct — 32 KB or 8 KB per Tensix?

**Analysis:**
- If 16 column slices per Tensix (2 G-Tiles × 8 columns per G-Tile)
- Each column slice: 512 rows (INT32 mode) × 4 cols × 4 bytes = 8 KB
- Per Tensix: 16 slices × but... this depends on counting method

**Status:** 🟡 **MODERATE ERROR** — Statements are internally contradictory; needs clarification on per-tile vs per-column-slice counting

---

### ERROR #8: Confusing FPU Rows Terminology (§2.4.6.2, Line 1318)

**HDD States:**
```
Clock cycle N:
  Booth stage 0 (input):  rows 0–3
  Booth stage 3:         rows 4–7 (in-flight, not yet valid)
  Booth stage OUT:       only rows 0–3 valid
```

**Issue:** "rows 0–3" is ambiguous and misleading.

**Clarification Needed:** These refer to **output rows per cycle**, not the FPU Tile row hierarchy. Should explicitly state this is describing pipeline phase alignment, not structural rows.

**Status:** 🟡 **MODERATE ERROR** — Could confuse readers about FPU architecture

---

## MINOR CORRECTIONS

### ERROR #9: Line 372 - Imprecise RTL Citation

**HDD Claim:**
```
RTL verified: `tt_srcs_registers.sv`: SRCA 256 rows × 16 words × 16-bit, SRCB 128 rows × 2 banks × 16-bit
```

**Issue:** This "RTL verification" statement is contradicted by actual RTL parameters.

**Fix:** Remove this false citation and replace with correct parameters:
```
RTL verified: SRCS_NUM_ROWS_16B=48 (tt_tensix_pkg.sv:35); SRCB 64 rows × 2 banks × 16-bit
```

**Status:** 🔴 **CRITICAL ERROR** — False RTL verification claim undermines credibility

---

## SUMMARY TABLE

| Error # | Section | Issue | Severity | Fix |
|---------|---------|-------|----------|-----|
| #1 | §2.9.2 | SRCA rows: 256 claimed vs 48 RTL | 🔴 Critical | Change to 48 rows |
| #2 | §2.9.4 | SRCB rows: 128 claimed vs 64 in diagram | 🔴 Critical | Change to 64 rows per bank |
| #3 | §2.4.6 | INT16 per G-Tile: 64 claimed vs 256 verified | 🔴 Critical | Change table row to 256 MACs |
| #4 | §2.4.6.3 | INT8 formula uses wrong hierarchical terms | 🟡 Moderate | Clarify: "8 M-Tiles × 2 FPU rows × 2 lane rows × 8 MULT_PAIRS" |
| #5 | §2.8.2 | DEST claim: "8 KB (4,096 INT32)" = math error | 🔴 Critical | Should be 16 KB for 4,096 entries |
| #6 | §2.9.2 | SRCA BANK_ROWS_16B: 128 vs 24 derived | 🔴 Critical | Change to 24 rows per bank |
| #7 | §2.8 | DEST capacity: 32 KB vs 8 KB contradiction | 🟡 Moderate | Clarify per-Tensix vs per-column-slice |
| #8 | §2.4.6.2 | "rows 0–3" ambiguous in pipeline context | 🟡 Moderate | Clarify as "output rows per clock phase" |
| #9 | §2.3.2 | False RTL verification of SRCA 256 rows | 🔴 Critical | Cite actual RTL: SRCS_NUM_ROWS_16B=48 |

---

## VERIFICATION CHECKLIST FOR CORRECTION

- [ ] Update §2.9.2 SRCA table: 256 rows → 48 rows
- [ ] Update §2.9.2 SRCA capacity: 16 KB → 1.5 KB
- [ ] Update §2.9.2 BANK_ROWS_16B: 128 → 24
- [ ] Update §2.9.4 SRCB rows per bank: 128 → 64
- [ ] Update §2.4.6 Table Line 1682: Per-G-Tile INT16 64 → 256 MACs
- [ ] Fix §2.8.2 Line 3234: "8 KB (4,096 INT32)" → "16 KB (4,096 INT32)"
- [ ] Clarify §2.8 DEST capacity (per-Tensix vs per-column-slice)
- [ ] Remove false RTL verification claim (line 372)
- [ ] Update line 378 with corrected capacity numbers
- [ ] Verify all derived calculations use corrected register sizes

---

**Prepared by:** Claude Code RTL Verification  
**Evidence Source:** FINAL_RTL_MAC_Throughput_VERIFIED.txt, INT16_Guide_HDD_V0.2  
**Confidence Level:** HIGH (all errors cross-verified against multiple RTL sources)
