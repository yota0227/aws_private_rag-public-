# Trinity N1B0 — Overlay (RISC-V Subsystem) Block-Level HDD

> **Pipeline:** `tt_20260221`
> **Search:** topic = `Overlay`, type = `hdd_section`, 5 of 39 results returned
> **Grounding Rule:** Only information present in the search results is stated as fact.
> Content not found is marked **[NOT IN KB]**.

---

## 1. Overview

| Attribute | Value (from KB) |
|-----------|----------------|
| Module name | `trinity_noc2axi_router_ne_opt_FBLC` |
| Pipeline | `tt_20260221` |
| Topic tag | Overlay |
| HDD level | Block-level |

**What the KB says:**

- The Overlay module is a key component in the Trinity NoC2AXI Router pipeline. ([3])
- It serves as a **router**, managing the data flow between the **Network-on-Chip (NoC)** and the **AXI bus interface**. ([3])
- Responsible for handling the **overlay functionality** of the system. ([1][2][4][5])
- All 5 results consistently identify the same module `trinity_noc2axi_router_ne_opt_FBLC` as the Overlay block.

**What the KB does NOT say:**

- The term "RISC-V" does not appear anywhere in the results.
- No mention of CPU cluster, cores, or `NUM_CLUSTER_CPUS`.
- The connection between "Overlay" (as a RISC-V subsystem) and this NoC2AXI router module is not explained in the returned data.

> ⚠ **Interpretation Note:** The RTL pipeline tags this NIU router variant under the "Overlay" topic. It likely provides the NoC-to-AXI bridge that the Overlay tile uses, rather than being the Overlay CPU subsystem itself.

---

## 2. Position in Grid

**[NOT IN KB]** — No grid coordinates, tile mapping, or mesh position information was returned for the Overlay block.

---

## 3. Feature Summary

Based strictly on KB content:

| # | Feature | Source | Detail |
|---|---------|--------|--------|
| 1 | NoC-to-AXI routing | [3] | Manages data flow between NoC and AXI bus |
| 2 | NE-optimized variant | Module name | `ne_opt` indicates North-East corner optimization |
| 3 | FBLC configuration | Module name | `FBLC` — specific configuration/variant identifier |
| 4 | Overlay functionality | [1]–[5] | All results state "overlay functionality" without further elaboration |

Features **NOT found** in KB:
- CPU Cluster (8× RISC-V cores) → **[NOT IN KB]**
- L1 Cache (banks, ECC) → **[NOT IN KB]**
- iDMA Engine → **[NOT IN KB]**
- ROCC Accelerator → **[NOT IN KB]**
- LLK (Low-Latency Kernel) → **[NOT IN KB]**
- SMN (System Maintenance Network) → **[NOT IN KB]**
- FDS (Frequency/Droop Sensor) → **[NOT IN KB]**
- Dispatch Engine (within Overlay) → **[NOT IN KB]**

---

## 4. Block Diagram

```
┌─────────────────────────────────────────────────────┐
│        trinity_noc2axi_router_ne_opt_FBLC           │
│                   (Overlay topic)                    │
│                                                     │
│   ┌──────────┐                    ┌──────────┐      │
│   │   NoC    │◄──── data flow ───►│   AXI    │      │
│   │ Network  │                    │   Bus    │      │
│   │Interface │                    │Interface │      │
│   └──────────┘                    └──────────┘      │
│                                                     │
│   [Sub-modules: NONE per KB — see §5]               │
│                                                     │
└─────────────────────────────────────────────────────┘
```

> This diagram reflects only what the KB states. The module routes data between NoC and AXI. Internal sub-blocks are not described.

---

## 5. Sub-module Hierarchy

Results [1], [4], and [5] explicitly state:

> *"The `trinity_noc2axi_router_ne_opt_FBLC` module does not have any sub-modules."*

```
trinity_noc2axi_router_ne_opt_FBLC    (Overlay, block-level)
└── (no child sub-modules reported)
```

> ⚠ This is a surprising finding — a block-level Overlay HDD with zero sub-modules. This may mean:
> 1. The RTL auto-parser did not descend into encrypted/obfuscated children, or
> 2. This module is a leaf-level wrapper with inlined logic, or
> 3. The `hdd_section` generation did not include hierarchy details for this variant.

**`tt_overlay_wrapper` hierarchy:** **[NOT IN KB]** — No results mention `tt_overlay_wrapper` or any `tt_overlay_*` modules.

---

## 6. Feature Details

### 6.1 CPU Cluster
**[NOT IN KB]** — No mention of RISC-V cores, `NUM_CLUSTER_CPUS`, or any CPU-related content.

### 6.2 L1 Cache
**[NOT IN KB]** — No mention of cache banks, bank width, ECC type, or SRAM type.

### 6.3 iDMA Engine
**[NOT IN KB]**

### 6.4 ROCC Accelerator
**[NOT IN KB]**

### 6.5 LLK (Low-Latency Kernel)
**[NOT IN KB]**

### 6.6 SMN (System Maintenance Network)
**[NOT IN KB]**

### 6.7 FDS (Frequency/Droop Sensor)
**[NOT IN KB]**

### 6.8 Dispatch Engine
**[NOT IN KB]**

---

## 7. Control Path

From result [3]:
> The module manages the **data flow between the NoC and the AXI bus interface**.

Detailed control path (CPU-to-NoC write/read sequence): **[NOT IN KB]**

---

## 8. Key Parameters

**[NOT IN KB]** — No parameters from `tt_overlay_pkg.sv` or any other package file were returned. No `localparam`, `parameter`, or constant definitions appear in the search results.

---

## 9. Clock / Reset Summary

Result [2] mentions that the HDD "provides a detailed description of the … clock/reset structure" but the **actual clock/reset details were truncated** in the returned snippet.

| Item | Status |
|------|--------|
| Clock domain names | **[NOT IN KB]** |
| Clock relationships | **[NOT IN KB]** |
| Reset type / polarity | **[NOT IN KB]** |
| CDC crossings | **[NOT IN KB]** |

---

## 10. APB Register Interfaces

**[NOT IN KB]** — No APB slave list, address map, or register descriptions were returned.

---

## 11. Verification Checklist

**[NOT IN KB]** — Result [2] mentions "verification" in the overview blurb, but no checklist, assertions, coverage items, or testbench details were returned.

---

## 12. Key RTL File Index

| # | File / Path | Source |
|---|-------------|--------|
| 1 | Module: `trinity_noc2axi_router_ne_opt_FBLC` | All 5 results |
| 2 | Pipeline path: `tt_20260221` | All 5 results |
| 3 | `tt_overlay_wrapper` or `tt_overlay_pkg.sv` | **[NOT IN KB]** |
| 4 | Specific RTL file paths | **[NOT IN KB]** — no file paths returned in hdd_section results |

---

## Appendix A — Raw Search Result Summary

| # | Topic | Type | Key Statement |
|---|-------|------|---------------|
| [1] | Overlay | hdd_section | "responsible for implementing the overlay functionality" / **no sub-modules** |
| [2] | Overlay | hdd_section | "detailed description of the sub-module hierarchy, functional details, control path, clock/reset" (content truncated) |
| [3] | Overlay | hdd_section | "serves as a router, managing the data flow between the NoC and the AXI bus interface" |
| [4] | Overlay | hdd_section | "handling the overlay functionality" / **no sub-modules** |
| [5] | Overlay | hdd_section | "implementing the overlay functionality" / **no sub-modules** |

---

## Appendix B — Coverage Gap Analysis

| Requested Section | Grounded? | Gap Reason |
|-------------------|-----------|------------|
| 1. Overview | ✅ Partial | Module identified; role as NoC↔AXI router confirmed; RISC-V context missing |
| 2. Position in Grid | ❌ | No grid/tile data in results |
| 3. Feature Summary | ✅ Minimal | Only NoC↔AXI routing confirmed |
| 4. Block Diagram | ✅ Minimal | NoC↔AXI flow only |
| 5. Sub-module Hierarchy | ✅ | Explicitly stated: no sub-modules |
| 6. Feature Details (8 items) | ❌ All 8 | None of the requested features appear |
| 7. Control Path | ✅ Minimal | "data flow between NoC and AXI" |
| 8. Key Parameters | ❌ | No package constants |
| 9. Clock/Reset | ❌ | Mentioned but truncated |
| 10. APB Registers | ❌ | Not present |
| 11. Verification | ❌ | Not present |
| 12. RTL Files | ✅ Minimal | Module name + pipeline only |

**Overall grounding rate: ~25% (3 of 12 sections have substantive KB content)**

---

## Appendix C — Recommended Follow-up Searches

| Priority | Search Parameters | Expected Yield |
|----------|-------------------|----------------|
| 🔴 High | `analysis_type: "module_parse"`, `query: "tt_overlay_wrapper"` | Sub-module hierarchy, ports, instances |
| 🔴 High | `analysis_type: "module_parse"`, `query: "tt_overlay_pkg"` | Package parameters, constants |
| 🔴 High | `analysis_type: "claim"`, `topic: "Overlay"` | Feature claims, CPU cluster, L1 cache details |
| 🟡 Med | `analysis_type: "hierarchy"`, `query: "overlay"` | Full hierarchy tree |
| 🟡 Med | `analysis_type: "clock_domain"`, `topic: "Overlay"` | Clock/reset structure |
| 🟢 Low | `query: "ROCC iDMA LLK"`, `topic: "Overlay"` | Accelerator/DMA details |
