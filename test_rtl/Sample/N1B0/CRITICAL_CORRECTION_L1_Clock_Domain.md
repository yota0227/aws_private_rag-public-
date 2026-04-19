# CRITICAL CORRECTION: L1 Clock Domain for Sparsity24

**Date:** 2026-04-04  
**Severity:** CRITICAL 🚨  
**Status:** Documentation correction required

---

## The Problem

The Comprehensive Guide states:

> "Sparsity24 should use **dm_clk** for L1 access"

**This is INCORRECT** based on RTL-based clock trace analysis.

---

## The Correction

Based on the **N1B0_Clock_Chain_Trace.txt** (RTL-verified):

> **Sparsity24 MUST use ai_clk (NOT dm_clk) for T6 L1 access**

### Evidence

**N1B0_Clock_Chain_Trace.txt, Line 577:**
```
ai_clk(i_ai_clk[x])| T6 L1 bank | rf1r_hdrw_lvt_768x69m4b1c1(_high/low)| Tensix Y=0..2
```

**Clock chain path (traced from RTL):**
```
i_ai_clk[0] 
  → tt_tensix_with_l1.u_l1part (tt_t6_l1_partition)
    → tt_t6_l1_flex_client_port (ai_clk)
      → tt_t6_l1_mem_wrap
        → SRAM macros: rf1r_hdrw_lvt_768x69m4b1c1 (ai_clk)
```

---

## Why the HDD Was Wrong

**N1B0_NPU_HDD_v0.1.md, Line 905:** Claims "L1 banks | ... | dm_clk"

This statement conflates THREE DIFFERENT L1s:
1. **T6 L1 bank** (Tensix) → **ai_clk** (NOT dm_clk!)
2. **Dispatch L1 bank** → **ai_clk**
3. **Overlay L1 dcache** (CPU cache) → **dm_clk**

The HDD document incorrectly listed all as "dm_clk" without distinguishing between the Tensix T6 L1 and the Overlay CPU L1.

---

## The Three L1s in N1B0

| L1 Type | Clock | Location | Users |
|---------|-------|----------|-------|
| **T6 L1 bank** | **ai_clk** | Tensix Y=0..2 | TRISC, FPU, SFPU, TDMA, **Sparsity24**, **TurboQuant** |
| **Dispatch L1 bank** | **ai_clk** | Dispatch Y=3 | Dispatch engine |
| **Overlay L1 dcache** | **dm_clk** | Overlay subsystem | CPU pipeline (overlay wrapper) |
| **Overlay L2 dcache** | **dm_clk** | Overlay subsystem | CPU pipeline |

---

## What Must Be Corrected

### 1. Comprehensive Guide - Section 2.2

**Current:**
```
| Domain | Frequency | Source | Purpose | Users |
| **dm_clk** | Data memory clock | Clock tree | **L1/L2 access, overlay** | L1 SRAM, overlay stream, **Sparsity24**, **TurboQuant** |
```

**Correction:**
```
| Domain | Frequency | Source | Purpose | Users |
| **ai_clk** | Application clock | Clock tree | **Tensix compute & T6 L1** | TRISC, FPU, SFPU, T6 L1, **Sparsity24**, **TurboQuant** |
| **dm_clk** | Data memory clock | Clock tree | **Overlay CPU cache & L2** | Overlay L1 dcache, Overlay L2, ATT SRAM |
```

### 2. Comprehensive Guide - Section 5 (Sparsity24)

**Current:**
```
| i_clk | 1 | IN | dm_clk | Operating clock |
```

**Correction:**
```
| i_clk | 1 | IN | **ai_clk** | Operating clock (T6 L1 access) |
```

### 3. Comprehensive Guide - Section 7.2 (Architecture)

**Current:**
```
**Clock Domain:** `dm_clk` (NOT `ai_clk`)
```

**Correction:**
```
**Clock Domain:** `ai_clk` (same as TRISC, T6 L1)
```

### 4. RTL Code Examples - All Sections

**Current:**
```systemverilog
.i_clk(i_dm_clk),  // dm_clk domain for L1 access
```

**Correction:**
```systemverilog
.i_clk(i_ai_clk[i]),  // ai_clk domain for T6 L1 access
```

### 5. Firmware Programming - Section 11

**Current Section 11.2:**
```c
TRISC_WRITE_CSR(CSR_SPARSITY24_CTRL, 0x00000001);  // Note: TRISC in ai_clk
```

**This is ALREADY CORRECT** — TRISC is ai_clk, so Sparsity24 should also be ai_clk for synchronous operation.

---

## Clock Domain Architecture (CORRECTED)

```
Tensix Tile Clock Domains (CORRECTED):
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  AI_CLK Domain (Application/Compute)                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  • TRISC (CPU) — Master of L1                    │  │
│  │  • FPU (Floating Point)                          │  │
│  │  • SFPU (Scalar FP)                              │  │
│  │  • TDMA (DMA engine)                             │  │
│  │  • T6 L1 SRAM ← Direct access, NO CDC           │  │
│  │  • Sparsity24 ← Direct L1 access, ai_clk        │  │
│  │  • TurboQuant ← Direct L1 access, ai_clk        │  │
│  │                                                   │  │
│  │  All in same clock domain — synchronized!        │  │
│  └──────────────────────────────────────────────────┘  │
│                     │ (Optional CDC to dm_clk)         │
│  DM_CLK Domain (Memory/Overlay)                        │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │  • Overlay wrapper (CPU L1/L2 cache)            │  │
│  │  • ATT (address translation)                     │  │
│  │  • NOC side-channel memory writes                │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  NOC_CLK Domain (Network)                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │  • Router, NIU, flit datapaths                   │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Why This Makes Sense

### **ai_clk is the Correct Choice**

1. **No CDC needed** — Sparsity24, TurboQuant, and TRISC all in ai_clk
2. **Direct L1 arbitration** — Same clock domain as other Tensix masters
3. **Simplified design** — No clock domain crossing latency for L1 reads
4. **Matches TRISC pattern** — Both are compute engines in same domain

### **dm_clk is ONLY for Overlay CPU**

- Overlay wrapper (CPU cache) is a separate subsystem
- Overlay runs at different frequency (dm_clk, not ai_clk)
- Has its own L1/L2 cache hierarchy separate from T6 L1
- Requires CDC FIFOs to cross to/from ai_clk domain

---

## Files to Update

| File | Section | Change |
|------|---------|--------|
| `IP_Design_and_Integration_Comprehensive_Guide.md` | 2.2, 5, 7.2, 7.4, 9 | Replace dm_clk with ai_clk for Sparsity24 |
| `Sparsity_vs_Sparsity24_Classification.md` | 4.2 | Update "Clock Domain Clarification Table" |
| `Clock_Domain_Verification_Report.md` | All | Mark as SUPERSEDED by RTL trace |
| `Step_2_4_2_RTL_Implementation_Code.sv` | Section 9 | Update `.i_clk(i_ai_clk[i])` |
| `Step_2_4_2_Patch_Guide.md` | Section 7 | Update clock domain references |

---

## Authority Level

🔴 **RTL-based clock chain trace is MORE authoritative than HDD documentation**

- **Source:** N1B0_Clock_Chain_Trace.txt (RTL-extracted, verified from trinity.sv)
- **Overrides:** N1B0_NPU_HDD_v0.1.md (human-written design doc)

---

## Summary

**OLD (WRONG):**
- Sparsity24 uses dm_clk
- Same as Overlay CPU L1 cache
- Requires CDC from TRISC

**NEW (CORRECT):**
- Sparsity24 uses ai_clk  
- Same as TRISC and T6 L1
- NO CDC needed, direct sync

---

**Status:** Ready to correct all documentation  
**Test:** Verify in RTL that Sparsity24 port connects to ai_clk[i]  
**Timeline:** Update Comprehensive Guide before implementation

