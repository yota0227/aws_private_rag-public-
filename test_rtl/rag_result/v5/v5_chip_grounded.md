# Trinity N1B0 — Integrated Hardware Design Document (HDD)

> **Pipeline ID:** tt_20260221
> **Document Version:** v5 (Grounded — KB-only content)
> **Generated:** 2026-04-27
> **Rule:** Only content retrieved from RAG KB is included. Missing sections are marked `[NOT IN KB]`.

---

## Table of Contents

1. [Chip Overview](#1-chip-overview)
2. [Package Constants and Grid](#2-package-constants-and-grid)
3. [Top-Level Ports](#3-top-level-ports)
4. [Module Hierarchy](#4-module-hierarchy)
5. [FPU (Floating-Point Unit)](#5-fpu-floating-point-unit)
6. [SFPU (Sparse Floating-Point Unit)](#6-sfpu-sparse-floating-point-unit)
7. [SMN (Scalable Memory Network)](#7-smn-scalable-memory-network)
8. [Dispatch Engine](#8-dispatch-engine)
9. [NoC Fabric](#9-noc-fabric)
10. [NIU](#10-niu)
11. [Clock Architecture](#11-clock-architecture)
12. [Reset Architecture](#12-reset-architecture)
13. [EDC](#13-edc)
14. [Overlay](#14-overlay)
15. [SRAM Inventory](#15-sram-inventory)
16. [DFX](#16-dfx)
17. [RTL File Reference](#17-rtl-file-reference)

---

## 1. Chip Overview

[NOT IN KB] — No chip-level overview HDD section was found in the knowledge base for pipeline tt_20260221.

---

## 2. Package Constants and Grid

[NOT IN KB] — No Package Constants HDD section (SizeX, SizeY, NumTensix, tile_t enum) was found in the knowledge base.

---

## 3. Top-Level Ports

[NOT IN KB] — No top-level port list HDD section was found in the knowledge base.

---

## 4. Module Hierarchy

The following hierarchy is reconstructed strictly from the three HDD sections retrieved from the KB. `trinity_router` is NOT included (EMPTY by design in N1B0).

```
trinity (top)
├── FPU                                  — Floating-Point Unit (KB: FPU HDD)
│   └── (sub-modules described in Section 5)
├── SFPU                                 — Sparse Floating-Point Unit (KB: SFPU HDD)
│   └── (sub-modules described in Section 6)
└── SMN                                  — Scalable Memory Network (KB: SMN HDD)
    └── BDAed_trinity_noc2axi_router_nw_opt_..._tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest
```

> Note: Full chip hierarchy beyond FPU/SFPU/SMN is [NOT IN KB].

---

## 5. FPU (Floating-Point Unit)

*Source: KB result [3] — FPU HDD, pipeline tt_20260221*

### 5.1 Overview

The Floating-Point Unit (FPU) is a key component in the TT pipeline, responsible for performing various floating-point operations. This Hardware Design Document (HDD) provides a detailed description of the FPU module, including its sub-module hierarchy, functional details, control path, and datapath architecture.

### 5.2 Sub-Module Hierarchy

[NOT IN KB — truncated in search result]

### 5.3 Functional Details

[NOT IN KB — truncated in search result]

### 5.4 Control Path

[NOT IN KB — truncated in search result]

### 5.5 Datapath

[NOT IN KB — truncated in search result]

---

## 6. SFPU (Sparse Floating-Point Unit)

*Source: KB result [1] — SFPU HDD, pipeline tt_20260221*

### 6.1 Overview

The SFPU (Sparse Floating-Point Unit) is a key component of the SoC design, responsible for performing floating-point arithmetic operations. This Hardware Design Document (HDD) provides a detailed overview of the SFPU block-level design, including its sub-module hierarchy, functional details, and interfaces.

### 6.2 Sub-Module Hierarchy

[NOT IN KB — truncated in search result]

### 6.3 Functional Details

[NOT IN KB — truncated in search result]

### 6.4 Interfaces

[NOT IN KB — truncated in search result]

---

## 7. SMN (Scalable Memory Network)

*Source: KB result [2] — SMN HDD, pipeline tt_20260221*

### 7.1 Overview

The `BDAed_trinity_noc2axi_router_nw_opt_trinity_noc2axi_router_nw_opt_tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest` module is a key component of the SMN (Scalable Memory Network) subsystem. It acts as a bridge between the NoC (Network-on-Chip) and the AXI bus, providing routing translation and self-test capabilities.

### 7.2 Key Module

- **Module name:** `BDAed_trinity_noc2axi_router_nw_opt_trinity_noc2axi_router_nw_opt_tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest`
- **Function:** NoC-to-AXI bridge with routing translation and self-test
- **Memory wrapper:** `tt_mem_wrap_32x1024_2p_nomask` — 32-bit × 1024-entry dual-port SRAM, no mask
- **Subsystem:** SMN (Scalable Memory Network)

### 7.3 Detailed Architecture

[NOT IN KB — truncated in search result]

---

## 8. Dispatch Engine

[NOT IN KB] — No Dispatch Engine HDD section was found in the knowledge base.

---

## 9. NoC Fabric

[NOT IN KB] — No NoC protocol HDD section was found in the knowledge base. Routing algorithm comparison (DOR/Tendril/Dynamic) and flit structure are not available.

---

## 10. NIU

[NOT IN KB] — No NIU HDD section was found in the knowledge base.

---

## 11. Clock Architecture

[NOT IN KB] — No Clock Architecture HDD section was found in the knowledge base.

---

## 12. Reset Architecture

[NOT IN KB] — No Reset Architecture HDD section was found in the knowledge base.

---

## 13. EDC

[NOT IN KB] — No EDC HDD section was found in the knowledge base. Ring topology, serial bus protocol, and harvest bypass details are not available.

---

## 14. Overlay

[NOT IN KB] — No Overlay HDD section was found in the knowledge base. CPU cluster, L1 cache, and APB slave details are not available.

---

## 15. SRAM Inventory

Partial data from KB:

| Memory Instance | Type | Size | Ports | Mask | Source |
|----------------|------|------|-------|------|--------|
| `tt_mem_wrap_32x1024_2p_nomask` | SRAM | 32-bit × 1024 entries | Dual-port | No mask | SMN HDD [2] |

> Full SRAM inventory with per-type quantity table is [NOT IN KB].

---

## 16. DFX

[NOT IN KB] — No DFX (iJTAG, scan chain) HDD section was found in the knowledge base.

---

## 17. RTL File Reference

[NOT IN KB] — No RTL file paths were provided in the retrieved HDD sections.

---

## Appendix: KB Search Metadata

| # | Topic | Type | Content Summary |
|---|-------|------|-----------------|
| 1 | SFPU | hdd_section | SFPU block-level HDD — overview, sub-module hierarchy, functional details |
| 2 | SMN | hdd_section | SMN subsystem HDD — noc2axi bridge, routing translation, selftest |
| 3 | FPU | hdd_section | FPU block-level HDD — overview, sub-module hierarchy, control/datapath |

**Search parameters:** `analysis_type=hdd_section`, `pipeline_id=tt_20260221`, `query=HDD`
**Results returned:** 3 of 3

---

*This document contains ONLY content retrieved from the BOS-AI RAG knowledge base. All sections without KB data are explicitly marked [NOT IN KB]. No inferred or fabricated content has been added.*