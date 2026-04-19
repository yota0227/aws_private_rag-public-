# Clock Domain Verification Report: L1 Access and Sparsity24 Decode Engine

**Date:** 2026-04-04  
**Status:** 🚨 **SUPERSEDED BY CRITICAL_CORRECTION_L1_Clock_Domain.md**
**Reason:** RTL-based clock trace (N1B0_Clock_Chain_Trace.txt) provides authoritative evidence that contradicts HDD documentation
**Source:** N1B0_Clock_Chain_Trace.txt (RTL-verified, line 577)

---

## Executive Summary

**Claim:** "Sparsity24 Decode Engine should use **dm_clk** for L1 access"

**Verification Result:** ✅ **CORRECT** — But requires clarification of L1 clock domain architecture

---

## L1 Clock Domain Architecture

N1B0 Tensix tile has a **two-layer L1 architecture** with clock domain separation:

### Layer 1: L1 Client Port (ai_clk domain)
- **Component:** `tt_t6_l1_flex_client_port`
- **Clock:** `ai_clk` (application clock, compute domain)
- **Users:** TRISC/BRISC CPUs
- **Purpose:** Provides TRISC/BRISC access to L1
- **N1B0 HDD Reference:** Lines 302, 331

### Layer 2: L1 SRAM Banks (dm_clk domain)
- **Component:** `tt_t6_l1_partition` (contains 16 SRAM banks)
- **Clock:** `dm_clk` (data memory clock)
- **Configuration:** 16 banks × 3072×128 bits (RA1_UHD SRAM)
- **Purpose:** Actual data storage
- **N1B0 HDD Reference:** Line 905

```
┌─────────────────────────────────────────┐
│        TRISC / BRISC CPUs               │
│         (ai_clk domain)                 │
└────────────────┬────────────────────────┘
                 │
         ┌───────▼────────┐
         │ CDC / Crossing │ (Clock domain boundary)
         └───────┬────────┘
                 │
    ┌────────────▼────────────┐
    │  tt_t6_l1_flex_client   │
    │       (ai_clk)          │
    └────────────┬────────────┘
                 │
    ┌────────────▼──────────────────┐
    │  tt_t6_l1_partition           │
    │  (16 SRAM banks, dm_clk)      │
    │  (3072×128 RA1_UHD SRAM)      │
    └───────────────────────────────┘
```

### Layer 3: L1 Arbitration (dm_clk domain)
- **Component:** `tt_t6_l1_superarb`
- **Clock:** `dm_clk`
- **Purpose:** Arbitrate multiple L1 masters
- **Priority:** TDMA > NoC write > BRISC
- **N1B0 HDD Reference:** Lines 371, 456, 471

---

## Why Sparsity24 Decode Engine Uses dm_clk

### Sparsity24 Decode Engine's L1 Access Path

Sparsity24 Decode Engine Engine is an **autonomous hardware accelerator** (like TDMA), not a CPU:

1. **Direct SRAM Access:** Sparsity24 Decode Engine accesses L1 SRAM **directly** (not through the ai_clk wrapper)
2. **Hardware Arbitration:** Competes with TDMA and other masters via `tt_t6_l1_superarb`
3. **Clock Domain:** Must be in **dm_clk** to match the SRAM and arbitrator clock
4. **Purpose:** Avoid CDC (clock domain crossing) latency; direct access to actual SRAM

### TRISC's L1 Access Path (for comparison)

TRISC uses a **different path** with CDC:

1. **Via ai_clk Wrapper:** `tt_t6_l1_flex_client_port` (ai_clk domain)
2. **CDC Crossing:** Clock domain boundary crossing inside the wrapper
3. **Then to dm_clk SRAM:** Actual SRAM access via arbitrator

---

## Verification Details

### N1B0 HDD Evidence

**Quote 1 (Line 302):**
```
tt_t6_l1_flex_client_port (ai_clk domain)
```
→ Client port for CPU access is ai_clk

**Quote 2 (Line 371):**
```
Both CPUs share the L1 through the `tt_t6_l1_superarb` arbitrator.
```
→ CPUs go through TRISC ai_clk client port, then to dm_clk arbitrator

**Quote 3 (Line 905):**
```
| L1 banks | 16 | 3072×128 | RA1_UHD | dm_clk | 192 |
```
→ L1 SRAM banks are **explicitly in dm_clk domain**

**Quote 4 (Line 456):**
```
**Module:** `tt_t6_l1_partition` (inside `tt_overlay_memory_wrapper`)
```
→ L1 partition contains both SRAM (dm_clk) and arbitration (dm_clk)

---

## Clock Domain Clarification Table

| Component | Clock Domain | Reason | Access Type |
|-----------|--------------|--------|-------------|
| **TRISC CPU** | ai_clk | Compute core | Direct T6 L1 access (synchronized) |
| **BRISC CPU** | ai_clk | Control processor | Direct T6 L1 access (synchronized) |
| **T6 L1 Arbitrator** | **ai_clk** | T6 L1 master selection | Direct arbitration (RTL-verified) |
| **T6 L1 SRAM Banks** | **ai_clk** | Tensix L1 clock (NOT dm_clk) | Actual storage (3MB/tile, RTL-verified) |
| **Sparsity24 Decode Engine** | **ai_clk** | Hardware accelerator (NEW) | Direct T6 SRAM access (synchronized, no CDC) |
| **TurboQuant** | **ai_clk** | Hardware accelerator (NEW) | Direct T6 SRAM access (synchronized, no CDC) |
| **Dispatch L1 bank** | ai_clk | Dispatch engine | Separate from T6 L1 |
| **Overlay L1 dcache** | dm_clk | CPU cache (separate subsystem) | Via CDC from ai_clk |

---

## System Architecture Diagram

```
Tensix Tile Clock Domains:
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  AI_CLK Domain (Compute)                               │
│  ┌──────────────────────────────────────────────────┐  │
│  │  • TRISC (CPU)                                   │  │
│  │  • BRISC (CPU)                                   │  │
│  │  • FPU (Floating Point)                          │  │
│  │  • SFPU (Scalar FP)                              │  │
│  │  • TDMA (DMA control, ai_clk portion)            │  │
│  │                                                   │  │
│  │  L1 Access: Via tt_t6_l1_flex_client_port (CDC) │  │
│  └──────────────────┬───────────────────────────────┘  │
│                     │ (Clock Domain Crossing)           │
│  DM_CLK Domain (Memory)                                 │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │  • TDMA (dm_clk portion)                         │  │
│  │  • NOC (L1 write port)                           │  │
│  │  • Overlay Streams                               │  │
│  │  • Sparsity24 Decode Engine (NEW) ← Direct SRAM access        │  │
│  │  • TurboQuant (NEW) ← Direct SRAM access        │  │
│  │                                                   │  │
│  │  L1 Arbitrator: tt_t6_l1_superarb (dm_clk)      │  │
│  │  L1 SRAM Banks: 16×3072×128 (RA1_UHD, dm_clk)  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  NOC_CLK Domain (Network)                              │
│  ┌──────────────────────────────────────────────────┐  │
│  │  • NoC flit datapath                             │  │
│  │  • Router                                         │  │
│  │  • NIU                                            │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Conclusion

### Is "dm_clk for L1 access" Correct?

**YES ✅** — with important caveat:

- **For Hardware Accelerators (Sparsity24 Decode Engine, TurboQuant):** ✅ CORRECT
  - Direct SRAM access requires dm_clk
  - No CDC needed
  - Arbitrates via tt_t6_l1_superarb (dm_clk)

- **For TRISC/BRISC CPUs:** ⚠️ PARTIALLY CORRECT
  - CPUs use ai_clk domain
  - Access L1 through ai_clk wrapper (`tt_t6_l1_flex_client_port`)
  - CDC (clock domain crossing) happens internally
  - Final SRAM access is dm_clk, but via synchronization layer

### Recommendation for Documentation

Update the statement to clarify:

**Old Statement:**
> "Sparsity24 Decode Engine uses dm_clk for L1 access"

**Improved Statement:**
> "Sparsity24 Decode Engine instantiates in dm_clk domain and accesses L1 SRAM directly via the dm_clk arbitrator (tt_t6_l1_superarb). This is consistent with other hardware accelerators (TDMA, overlay streams) and avoids CDC latency. TRISC/BRISC CPUs access L1 through an ai_clk wrapper with internal CDC."

---

## N1B0 HDD References

| Line | Quote | Relevance |
|------|-------|-----------|
| 302, 331 | `tt_t6_l1_flex_client_port (ai_clk domain)` | CPU L1 access path |
| 344 | `Clock domains: ai_clk (compute), noc_clk (NoC endpoint), dm_clk (L2/mem pipeline)` | Overall tile clock domains |
| 371 | `Both CPUs share the L1 through the tt_t6_l1_superarb arbitrator` | L1 arbitration |
| 456 | `tt_t6_l1_partition (inside tt_overlay_memory_wrapper)` | L1 partition module |
| 471 | `Arbitration: tt_t6_l1_superarb (priority: TDMA > NoC write > BRISC)` | Arbitration priority |
| 905 | `L1 banks \| 16 \| 3072×128 \| RA1_UHD \| dm_clk \| 192` | **L1 SRAM clock domain** |

---

## Summary

✅ **Verification Complete**

The statement "Sparsity24 Decode Engine uses dm_clk for L1 access" is **VERIFIED CORRECT** based on N1B0 HDD documentation. L1 SRAM banks are explicitly documented as dm_clk domain (Line 905), making it appropriate for hardware accelerators to be in the same clock domain for direct, low-latency access.

