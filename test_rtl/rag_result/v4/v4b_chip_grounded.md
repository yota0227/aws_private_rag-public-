# N1B0 Consolidated Hardware Design Document (HDD)

**Pipeline ID:** `tt_20260221`  
**Generated:** 2026-04-24  
**Source:** RTL Knowledge Base (search_rtl, query="HDD", pipeline_id="tt_20260221")  
**Sections Found:** 5 — SFPU, Clock_Reset, SMN, NoC, FPU

> ⚠ **Integrity Rule:** Only content retrieved from the KB is included. Missing information is marked `[NOT IN KB]`. RTL signal/module names are preserved verbatim. `trinity_router` is **not** instantiated in N1B0 (EMPTY by design) and is excluded from all hierarchies.

---

## Table of Contents

1. [SFPU (Scalar Floating-Point Unit)](#1-sfpu-scalar-floating-point-unit)
2. [Clock & Reset](#2-clock--reset)
3. [SMN (System Management Network)](#3-smn-system-management-network)
4. [NoC (Network-on-Chip)](#4-noc-network-on-chip)
5. [FPU (Floating-Point Unit)](#5-fpu-floating-point-unit)
6. [Package Constants](#6-package-constants)
7. [EDC Topology](#7-edc-topology)
8. [Overlay Deep-Dive](#8-overlay-deep-dive)
9. [SRAM Inventory](#9-sram-inventory)

---

## 1. SFPU (Scalar Floating-Point Unit)

### 1.1 Overview

The SFPU is a key component of the N1B0 pipeline design. It is responsible for performing floating-point operations on scalar data.

### 1.2 Sub-module Hierarchy

[NOT IN KB] — full hierarchy was truncated in search results.

### 1.3 Functional Description

[NOT IN KB] — detailed functional description beyond the overview was not returned.

### 1.4 Key Signals

[NOT IN KB]

---

## 2. Clock & Reset

### 2.1 Overview

The Clock_Reset module resides within the `BDAed_trinity_noc2axi_router_nw_opt_trinity_noc2axi_router_nw_opt_tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest` pipeline path.

> **Note:** Despite the path containing `trinity_noc2axi_router_nw_opt`, the top-level `trinity_router` is **EMPTY by design** in N1B0. The clock/reset logic services the remaining active sub-blocks only.

### 2.2 Sub-module Hierarchy

[NOT IN KB] — hierarchy snippet was truncated ("The C…").

### 2.3 Functional Description

[NOT IN KB]

### 2.4 Key Signals

[NOT IN KB]

---

## 3. SMN (System Management Network)

### 3.1 Overview

The SMN module is responsible for routing and translation of NoC (Network-on-Chip) traffic within N1B0. It handles system management plane communication.

### 3.2 Sub-module Hierarchy

[NOT IN KB]

### 3.3 Functional Description

- Routing of NoC traffic for system management
- Translation layer for NoC protocol to internal management bus

[NOT IN KB] — further detail truncated.

### 3.4 Key Signals

[NOT IN KB]

---

## 4. NoC (Network-on-Chip)

### 4.1 Overview

The NoC module handles communication between various sub-modules in N1B0. It provides the on-chip interconnect fabric.

### 4.2 Sub-module Hierarchy

[NOT IN KB]

### 4.3 Functional Description

- Handles inter-module communication
- Control plane and data plane routing

[NOT IN KB] — full control/functional details truncated.

### 4.4 Routing Algorithms (3-way Comparison)

[NOT IN KB] — routing algorithm comparison (e.g., XY, YX, adaptive) was not present in the returned content.

### 4.5 Flit Structure

[NOT IN KB] — flit format/fields were not present in the returned content.

### 4.6 Key Signals

[NOT IN KB]

---

## 5. FPU (Floating-Point Unit)

### 5.1 Overview

The FPU performs various arithmetic operations on floating-point data. It is a key computational block in the N1B0 datapath.

### 5.2 Sub-module Hierarchy

[NOT IN KB]

### 5.3 Functional Description

- Floating-point arithmetic (add, multiply, fused multiply-add, etc.)

[NOT IN KB] — comprehensive details truncated.

### 5.4 Key Signals

[NOT IN KB]

---

## 6. Package Constants

> **Requested fields:** `SizeX`, `SizeY`, `NumTensix`, `tile_t` enum

| Constant     | Value         |
|-------------|---------------|
| `SizeX`     | [NOT IN KB]   |
| `SizeY`     | [NOT IN KB]   |
| `NumTensix` | [NOT IN KB]   |
| `tile_t`    | [NOT IN KB]   |

Package constants were not returned by the HDD search. A dedicated search with `query="package constants"` or `topic="Package"` may be needed.

---

## 7. EDC Topology

> **Requested fields:** Ring structure, serial bus, harvest bypass

| Aspect            | Detail        |
|-------------------|---------------|
| Ring structure    | [NOT IN KB]   |
| Serial bus        | [NOT IN KB]   |
| Harvest bypass    | [NOT IN KB]   |

EDC topology was not among the 5 HDD sections returned. A dedicated search with `topic="EDC"` may be needed.

---

## 8. Overlay Deep-Dive

> **Requested fields:** CPU cluster, L1 cache, APB slave

| Aspect        | Detail        |
|---------------|---------------|
| CPU cluster   | [NOT IN KB]   |
| L1 cache      | [NOT IN KB]   |
| APB slave map | [NOT IN KB]   |

Overlay section was not among the 5 HDD sections returned. A dedicated search with `topic="Overlay"` may be needed.

---

## 9. SRAM Inventory

> **Requested field:** Memory type quantity table

| Memory Type | Instances | Size     | Total Capacity |
|-------------|-----------|----------|----------------|
| —           | [NOT IN KB] | [NOT IN KB] | [NOT IN KB] |

SRAM inventory was not among the 5 HDD sections returned. A dedicated search with `query="SRAM"` may be needed.

---

## Appendix A — Sections NOT Found in This Search

The following topics were **requested but not present** in the 5 results returned:

| Topic                  | Status      | Suggested Follow-up Query              |
|------------------------|-------------|----------------------------------------|
| Package Constants      | NOT IN KB   | `query="package constants SizeX SizeY"` |
| EDC Topology           | NOT IN KB   | `topic="EDC"`                          |
| NoC Routing Algorithms | NOT IN KB   | `topic="NoC"`, `query="routing flit"`  |
| Overlay (CPU/L1/APB)   | NOT IN KB   | `topic="Overlay"`                      |
| SRAM Inventory         | NOT IN KB   | `query="SRAM inventory"`               |

---

## Appendix B — Design Notes

- **`trinity_router`**: Not instantiated in N1B0 (EMPTY by design). Excluded from all hierarchies per design rule.
- All RTL signal and module names are preserved verbatim from KB results.
- Search was limited to `max_results=20` but only 5 HDD sections exist in the KB for this pipeline.
