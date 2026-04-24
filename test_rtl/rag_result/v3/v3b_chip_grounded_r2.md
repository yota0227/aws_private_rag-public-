# Trinity N1B0 — Integrated Chip-Level HDD (Grounded R2)

> **Pipeline:** `tt_20260221`
> **Module under analysis:** `trinity_noc2axi_router_ne_opt_FBLC`
> **Search:** query="HDD", pipeline_id="tt_20260221" → 5 results / 109 total
> **Grounding rule:** Only information present in search results is included. Missing data marked `[NOT IN KB]`.
> **Note:** `trinity_router` is NOT instantiated in N1B0 (EMPTY by design) and is excluded from hierarchy.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Topics Covered by KB](#2-topics-covered-by-kb)
3. [Overlay](#3-overlay)
4. [Dispatch Engine](#4-dispatch-engine)
5. [EDC](#5-edc)
6. [DFX](#6-dfx)
7. [Package Constants and Grid](#7-package-constants-and-grid)
8. [Top-Level Ports](#8-top-level-ports)
9. [Module Hierarchy](#9-module-hierarchy)
10. [Compute Tile (Tensix)](#10-compute-tile-tensix)
11. [NoC Fabric](#11-noc-fabric)
12. [NIU / AXI Bridge](#12-niu--axi-bridge)
13. [Clock Architecture](#13-clock-architecture)
14. [Reset Architecture](#14-reset-architecture)
15. [SRAM Inventory](#15-sram-inventory)
16. [RTL File Reference](#16-rtl-file-reference)
17. [KB Coverage Analysis](#17-kb-coverage-analysis)

---

## 1. Overview

**Source:** All 5 search results [1]–[5].

The sole module returned by the knowledge base for pipeline `tt_20260221` is:

```
trinity_noc2axi_router_ne_opt_FBLC
```

This module is described as a **block-level** component within the `tt_20260221` pipeline. It appears across **five distinct topics** — Overlay, DFX (×2), EDC, and Dispatch — suggesting it serves as a **NoC-to-AXI bridge/router** that is shared across multiple functional domains.

### Key Facts from KB

| Attribute | Value | Source |
|-----------|-------|--------|
| Module name | `trinity_noc2axi_router_ne_opt_FBLC` | All results |
| Pipeline ID | `tt_20260221` | All results |
| Document type | `hdd_section` | All results |
| Topics tagged | Overlay, DFX, EDC, Dispatch | Results [1]–[5] |
| Hierarchy level | Block-level | All results |
| Optimization variant | NE (North-East) direction, `opt_FBLC` | Inferred from module name |

---

## 2. Topics Covered by KB

The search returned HDD sections for the following topics, all referencing the same module:

| # | Topic | Result | HDD Title | Key Description |
|---|-------|--------|-----------|-----------------|
| 1 | **Overlay** | [1] | Overlay HDD | "responsible for the Overlay functionality" |
| 2 | **DFX** | [2] | DFX HDD | "responsible for the DFX (Design for Extensibility) functionality" |
| 3 | **EDC** | [3] | EDC HDD | "belongs to the EDC (Embedded Design Compiler) topic" |
| 4 | **DFX** | [4] | DFX HDD | "responsible for the DFX (Dynamic Functional eXchange) functionality" |
| 5 | **Dispatch** | [5] | Dispatch HDD | "specifically in the Dispatch topic" |

> ⚠ **Note:** DFX appears twice with different expansions — "Design for Extensibility" [2] vs "Dynamic Functional eXchange" [4]. This inconsistency is preserved as-is from the KB.

---

## 3. Overlay

**Source:** Result [1].

> "The `trinity_noc2axi_router_ne_opt_FBLC` module is a part of the `tt_20260221` pipeline and is responsible for the Overlay functionality. This block-level HDD provides a detailed overview of the module's design and implementation."

### Sub-module Hierarchy

The result mentions "### 2. Sub-module" but the content is truncated. No sub-module names were returned.

### Overlay-Specific Details

| Item | Status |
|------|--------|
| CPU Cluster (RISC-V cores, NUM_CLUSTER_CPUS) | `[NOT IN KB]` |
| L1 Cache (banks, width, ECC type, SRAM type) | `[NOT IN KB]` |
| APB Slave interfaces | `[NOT IN KB]` |
| iDMA Engine | `[NOT IN KB]` |
| ROCC Accelerator | `[NOT IN KB]` |
| LLK (Low-Latency Kernel) | `[NOT IN KB]` |

---

## 4. Dispatch Engine

**Source:** Result [5].

> "The `trinity_noc2axi_router_ne_opt_FBLC` module is a part of the `tt_20260221` pipeline, specifically in the Dispatch topic. This block-level Hardware Design Document (HDD) provides details about the module's sub-module hierarchy, functional details, control path, clock/reset structure."

### Dispatch-Specific Details

| Item | Status |
|------|--------|
| East/West dispatch structure | `[NOT IN KB]` |
| Command distribution mechanism | `[NOT IN KB]` |
| Feedthrough signals (de_to_t6 / t6_to_de) | `[NOT IN KB]` |

The HDD claims to cover "sub-module hierarchy, functional details, control path, clock/reset structure" but the returned content is truncated and no specifics were provided.

---

## 5. EDC

**Source:** Result [3].

> "The `trinity_noc2axi_router_ne_opt_FBLC` block is a part of the `tt_20260221` pipeline and belongs to the EDC (Embedded Design Compiler) topic. This block-level HDD provides a detailed description of the module's design, functionality, and verification."

### EDC-Specific Details

| Item | Status |
|------|--------|
| Ring topology (U-shape, Segment A/B) | `[NOT IN KB]` |
| Serial bus (req_tgl, ack_tgl, data, data_p) | `[NOT IN KB]` — *Note: confirmed in separate module_parse search of `tt_edc_pkg.sv`* |
| Harvest bypass (mux/demux) | `[NOT IN KB]` |
| Node ID structure | `[NOT IN KB]` |
| BIU register access | `[NOT IN KB]` |

> ⚠ **Note:** The EDC acronym is expanded as "Embedded Design Compiler" in this result. Other searches returned "Embedded Debug Connectivity", "Embedded Data Controller", "Embedded Data Concentrator", "Embedded Device Controller", and "Embedded Distributed Controller" — none of which match each other.

---

## 6. DFX

**Source:** Results [2] and [4].

### Result [2]
> "The `trinity_noc2axi_router_ne_opt_FBLC` block is a part of the `tt_20260221` pipeline and is responsible for the **DFX (Design for Extensibility)** functionality. This block-level HDD provides details on the sub-module hierarchy, functional details, control path..."

### Result [4]
> "The `trinity_noc2axi_router_ne_opt_FBLC` block is a part of the `tt_20260221` pipeline and is responsible for the **DFX (Dynamic Functional eXchange)** functionality. This block-level Hardware Design Document (HDD) provides a detailed overview of the sub-module hierarchy, functional details..."

### DFX-Specific Details

| Item | Status |
|------|--------|
| iJTAG controller | `[NOT IN KB]` |
| Scan chains | `[NOT IN KB]` |
| MBIST | `[NOT IN KB]` |
| FuseCtrl | `[NOT IN KB]` |

---

## 7. Package Constants and Grid

`[NOT IN KB]`

| Item | Status |
|------|--------|
| SizeX, SizeY | `[NOT IN KB]` |
| NumTensix | `[NOT IN KB]` |
| tile_t enum | `[NOT IN KB]` |
| Grid dimensions (4×5) | `[NOT IN KB]` |
| Tile type counts | `[NOT IN KB]` |

---

## 8. Top-Level Ports

`[NOT IN KB]`

No top-level port information for the `trinity` module was returned.

---

## 9. Module Hierarchy

Based solely on search results:

```
trinity (top) .................... [NOT IN KB — not returned]
  └─ trinity_noc2axi_router_ne_opt_FBLC ... [CONFIRMED — all 5 results]
       └─ (no sub-modules reported)
```

> **Exclusion:** `trinity_router` is **NOT instantiated** in N1B0 (EMPTY by design) and is intentionally excluded.

---

## 10. Compute Tile (Tensix)

`[NOT IN KB]`

| Item | Status |
|------|--------|
| FPU | `[NOT IN KB]` |
| SFPU | `[NOT IN KB]` |
| TDMA | `[NOT IN KB]` |
| L1 Cache | `[NOT IN KB]` |
| DEST / SRCB registers | `[NOT IN KB]` |

---

## 11. NoC Fabric

`[NOT IN KB]`

| Item | Status |
|------|--------|
| Routing algorithms (DOR / Tendril / Dynamic) | `[NOT IN KB]` |
| Flit structure (noc_header_address_t) | `[NOT IN KB]` |
| Virtual Channel buffers | `[NOT IN KB]` |
| Security Fence | `[NOT IN KB]` |

> The module name contains `noc2axi_router`, confirming NoC-to-AXI bridging exists, but no protocol details were returned.

---

## 12. NIU / AXI Bridge

**Source:** Inferred from module name `trinity_noc2axi_router_ne_opt_FBLC`.

The module name confirms:
- **NoC-to-AXI** protocol conversion exists
- **NE** (North-East) positional variant
- **opt_FBLC** optimization variant

| Item | Status |
|------|--------|
| ATT (Address Translation Table) | `[NOT IN KB]` |
| SMN security groups | `[NOT IN KB]` |
| AXI port width / protocol version | `[NOT IN KB]` |

---

## 13. Clock Architecture

`[NOT IN KB]`

| Item | Status |
|------|--------|
| ai_clk | `[NOT IN KB]` |
| noc_clk | `[NOT IN KB]` |
| dm_clk | `[NOT IN KB]` |
| ref_clk | `[NOT IN KB]` |

---

## 14. Reset Architecture

`[NOT IN KB]`

| Item | Status |
|------|--------|
| Reset chain | `[NOT IN KB]` |
| Power partition | `[NOT IN KB]` |
| ISO_EN daisy chain | `[NOT IN KB]` |

---

## 15. SRAM Inventory

`[NOT IN KB]`

No memory instance information was returned.

---

## 16. RTL File Reference

**Source:** Prior searches (module_parse results).

The only RTL file confirmed in the KB (from previous module_parse searches, not this search):

| File Path | Content |
|-----------|---------|
| `rtl-sources/tt_20260221/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | EDC package — modports: ingress, egress, edc_node, sram |
| `rtl-sources/tt_20260221/used_in_n1/mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | Same (mem_port variant) |
| `rtl-sources/tt_20260221/used_in_n1/legacy/no_mem_port/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | Same (legacy no_mem_port variant) |
| `rtl-sources/tt_20260221/used_in_n1/make_enc/260223_no_srun/org/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | Same (make_enc variant) |
| `rtl-sources/tt_20260221/used_in_n1/tt_rtl/tt_edc/rtl/tt_edc_pkg.sv` | Same (used_in_n1 variant) |

> ⚠ These file paths are from a **prior search session**, not the current one. The current search returned only `hdd_section` type results with no file paths.

---

## 17. KB Coverage Analysis

### Grounding Scorecard

| Section | Status | Data Source |
|---------|--------|------------|
| 1. Overview | ✅ GROUNDED | All 5 results |
| 2. Topics Covered | ✅ GROUNDED | All 5 results |
| 3. Overlay | ✅ PARTIAL | Result [1] — overview only, truncated |
| 4. Dispatch | ✅ PARTIAL | Result [5] — overview only, truncated |
| 5. EDC | ✅ PARTIAL | Result [3] — overview only, truncated |
| 6. DFX | ✅ PARTIAL | Results [2]+[4] — two variants, overview only |
| 7. Package Constants | ❌ NOT IN KB | — |
| 8. Top-Level Ports | ❌ NOT IN KB | — |
| 9. Module Hierarchy | ⚠️ MINIMAL | Module name only |
| 10. Compute Tile | ❌ NOT IN KB | — |
| 11. NoC Fabric | ❌ NOT IN KB | — |
| 12. NIU / AXI Bridge | ⚠️ MINIMAL | Module name inference only |
| 13. Clock Architecture | ❌ NOT IN KB | — |
| 14. Reset Architecture | ❌ NOT IN KB | — |
| 15. SRAM Inventory | ❌ NOT IN KB | — |
| 16. RTL File Reference | ⚠️ CROSS-SESSION | From prior module_parse search |

**Coverage: 4/16 sections grounded, 3/16 minimal, 9/16 NOT IN KB**

### Root Cause

The entire `tt_20260221` pipeline's HDD sections are generated for a **single module** (`trinity_noc2axi_router_ne_opt_FBLC`). This means the RTL analysis pipeline processed only this one module, or only this module's HDD was indexed into the knowledge base. All other chip-level modules (`trinity`, `tt_tensix_tile`, `tt_noc_router`, `tt_edc1_ring`, `tt_overlay_wrapper`, etc.) have **no HDD entries** in the current KB.

### Recommendations

| Priority | Action | Expected Outcome |
|----------|--------|-----------------|
| 🔴 Critical | Re-run RTL pipeline with full module list (trinity.sv, trinity_pkg.sv, all submodules) | Full chip HDD coverage |
| 🔴 Critical | Index `module_parse` + `claim` + `hierarchy` analysis types into HDD generation | Structural data for all sections |
| 🟡 Medium | Use RAG knowledge base (`rag_query`) for spec documents | Cross-reference with design specs |
| 🟢 Low | Manually upload existing HDD v0.1 baseline for comparison | Validation against engineer reference |
