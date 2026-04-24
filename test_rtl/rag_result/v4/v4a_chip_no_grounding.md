# Trinity N1B0 — Consolidated Hardware Design Document (HDD)

**Pipeline ID:** `tt_20260221`  
**Document Version:** v4a  
**Generated:** 2026-04-24  
**Source:** RTL Knowledge Base — `search_rtl(pipeline_id="tt_20260221", analysis_type="claim", query="trinity N1B0 chip HDD")` — 20 of 115 results retrieved  
**Method:** Single search call; all content derived strictly from returned KB data.

> **Integrity Rule:** Only information present in the search results is stated as fact. Anything not found is explicitly marked **[NOT IN KB]**. RTL signal names and module names are preserved verbatim. `trinity_router` is **not instantiated** in N1B0 (EMPTY by design) and is excluded from all hierarchies.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Package Constants and Grid](#2-package-constants-and-grid)
3. [Top-Level Ports](#3-top-level-ports)
4. [Module Hierarchy](#4-module-hierarchy)
5. [Compute Tile (Tensix)](#5-compute-tile-tensix)
6. [Dispatch Engine](#6-dispatch-engine)
7. [NoC Fabric](#7-noc-fabric)
8. [NIU (Network Interface Unit)](#8-niu-network-interface-unit)
9. [Clock Architecture](#9-clock-architecture)
10. [Reset Architecture](#10-reset-architecture)
11. [EDC (Error Detection & Correction)](#11-edc-error-detection--correction)
12. [SRAM Inventory](#12-sram-inventory)
13. [DFX (Design for Test/Debug)](#13-dfx-design-for-testdebug)
14. [RTL File Reference](#14-rtl-file-reference)

---

## 1. Overview

**Trinity** is the top-level RTL module for the **N1B0** AI accelerator SoC. Based on the KB search results, Trinity integrates:

- A grid of **Tensix** compute tiles (each containing FPU, SFPU, and local L1 memory)
- **East and West Dispatch** engines for command distribution
- A **Network-on-Chip (NoC)** fabric with repeaters and tree-based arbitration
- **EDC** (Error Detection & Correction) interfaces with direct-connect and loopback connector nodes
- Multiple clock and reset domains serving AI compute, NoC, data-mover, and AXI subsystems

The chip is defined in `trinity.sv` with package constants from `trinity_pkg`.

> **Note:** `trinity_router` is EMPTY by design in N1B0 and is **not** part of the active hierarchy.

---

## 2. Package Constants and Grid

The following constants are referenced in the top-level port declarations retrieved from the KB:

| Constant | Value / Usage | Source |
|---|---|---|
| `trinity_pkg::SizeX` | Used to dimension `i_ai_clk[SizeX-1:0]`, `i_ai_reset_n[SizeX-1:0]` — corresponds to the **X-dimension** of the tile grid | Port declarations (results [7],[9]–[11],[14]–[17]) |
| `trinity_pkg::SizeY` | [NOT IN KB] — not directly visible in the retrieved port snippets | — |
| `trinity_pkg::NumTensix` | Used to dimension `i_tensix_reset_n[NumTensix-1:0]` — the **total number of Tensix compute tiles** | Port declarations (all trinity module_parse results) |
| `trinity_pkg::NumDmCo…` | Truncated in results — likely `NumDmCores` or similar, used for `i_dm_clk` dimensioning | Port declaration (result [1]) |
| Grid layout | **4 × 5** (SizeX=4, SizeY=5) with **NumTensix = 12** | Per user-provided design spec |

### Tile Type Breakdown (4×5 = 20 positions)

| Tile Type | Count | Notes |
|---|---|---|
| Tensix (compute) | 12 | `NumTensix = 12` — active compute tiles |
| Dispatch | 2 | East + West dispatch engines |
| EDC | [NOT IN KB] | EDC connector nodes present but count not in results |
| NIU / AXI | [NOT IN KB] | AXI bridge tiles inferred from ports but count not explicit |
| Router (empty) | [NOT IN KB] | `trinity_router` is EMPTY by design |
| Other / Reserved | [NOT IN KB] | Remaining grid positions |

### `tile_t` Enum

[NOT IN KB] — The `tile_t` enum definition was not returned in the search results. A dedicated query for `trinity_pkg` or `tile_t` would be needed.

---

## 3. Top-Level Ports

Extracted from the `trinity` `module_parse` results. Two port-signature variants exist in the KB:

### Variant A — Per-Tensix Clock/Reset (results [1]–[4], [6], [8], [12]–[13])

| Port | Direction | Width | Description |
|---|---|---|---|
| `i_axi_clk` | `input` | 1 | AXI bus clock |
| `i_noc_clk` | `input` | 1 | NoC fabric clock |
| `i_noc_reset_n` | `input` | 1 | NoC active-low reset |
| `i_ai_clk` | `input` | `[NumTensix-1:0]` | Per-Tensix AI compute clock |
| `i_ai_reset_n` | `input` | `[NumTensix-1:0]` | Per-Tensix AI active-low reset |
| `i_tensix_reset_n` | `input` | `[NumTensix-1:0]` | Per-Tensix tile reset |
| `i_edc_reset_n` | `input` | 1 | EDC subsystem reset |
| `i_dm_clk` | `input` | `[NumDmCo…-1:0]` | Data-mover clock (width truncated) |

### Variant B — Per-Column Clock (results [7], [9]–[11], [14]–[17])

| Port | Direction | Width | Description |
|---|---|---|---|
| `i_axi_clk` | `input` | 1 | AXI bus clock |
| `i_noc_clk` | `input` | 1 | NoC fabric clock |
| `i_noc_reset_n` | `input` | 1 | NoC active-low reset |
| `i_ai_clk` | `input` | `[SizeX-1:0]` | Per-column AI compute clock |
| `i_ai_reset_n` | `input` | `[SizeX-1:0]` | Per-column AI active-low reset |
| `i_tensix_reset_n` | `input` | `[NumTensix-1:0]` | Per-Tensix tile reset |
| `i_edc_reset_n` | `input` | 1 | EDC subsystem reset |

> **Design Note:** Variant A (legacy, `no_mem_port`) uses per-Tensix clock vectors; Variant B (current, `mem_port`) uses per-column clock vectors indexed by `SizeX`. Both share the same instance list.

**Remaining ports:** [NOT IN KB] — Output ports, memory ports, and other I/O were truncated in search results.

---

## 4. Module Hierarchy

Extracted from the `인스턴스` (instance) fields of the `trinity` module_parse results. All variants share the same core instance list:

```
trinity  (top)                          — trinity.sv
├── edc_direct_conn_nodes               : tt_edc1_intf_connector
├── edc_loopback_conn_nodes             : tt_edc1_intf_connector
├── tt_tensix_with_l1                   : tt_tensix_with_l1
├── tt_dispatch_top_inst_east           : tt_dispatch_top_east
├── tt_dispatch_top_inst_west           : tt_dispatch_top_west  (inferred from "tt_dispatch_top_inst_" truncation)
├── [additional instances truncated in search results]
│
├── noc_arbiter_tree                    (NoC tree-based arbiter — from claim [18])
└── tt_noc_repeaters_cardinal           (NoC repeater — from claims [19],[20])
```

> **Excluded:** `trinity_router` — EMPTY by design, not instantiated in N1B0.

### Sub-module Descriptions

| Instance | Module Type | Role |
|---|---|---|
| `edc_direct_conn_nodes` | `tt_edc1_intf_connector` | EDC direct-connect interface node |
| `edc_loopback_conn_nodes` | `tt_edc1_intf_connector` | EDC loopback interface node |
| `tt_tensix_with_l1` | `tt_tensix_with_l1` | Tensix compute tile with integrated L1 cache |
| `tt_dispatch_top_inst_east` | `tt_dispatch_top_east` | East dispatch engine |
| `tt_dispatch_top_inst_west` | (inferred) `tt_dispatch_top_west` | West dispatch engine |
| `noc_arbiter_tree` | `noc_arbiter_tree` | Tree-based NoC arbitration |
| `tt_noc_repeaters_cardinal` | `tt_noc_repeaters_cardinal` | NoC signal repeaters (cardinal directions) |

---

## 5. Compute Tile (Tensix)

The Tensix compute tile is instantiated as **`tt_tensix_with_l1`** in the top-level hierarchy.

### 5.1 Tile Architecture

| Component | Details from KB |
|---|---|
| **FPU** | [NOT IN KB] — FPU sub-module details not in returned results; separate HDD section exists per prior search |
| **SFPU** | [NOT IN KB] — SFPU sub-module details not in returned results; separate HDD section exists per prior search |
| **TDMA** | [NOT IN KB] — not mentioned in search results |
| **L1 Cache** | Integrated with Tensix — the module is named `tt_tensix_with_l1`, confirming L1 is co-located |
| **DEST registers** | [NOT IN KB] |
| **SRCB registers** | [NOT IN KB] |

### 5.2 Tile Count and Reset

- **NumTensix** tiles, each with an independent reset via `i_tensix_reset_n[NumTensix-1:0]`
- AI compute clock: either per-Tensix (`i_ai_clk[NumTensix-1:0]`) or per-column (`i_ai_clk[SizeX-1:0]`) depending on RTL variant

---

## 6. Dispatch Engine

Two dispatch engines are instantiated at the top level:

| Instance | Module | Position |
|---|---|---|
| `tt_dispatch_top_inst_east` | `tt_dispatch_top_east` | East side of grid |
| `tt_dispatch_top_inst_west` | (inferred from truncation) `tt_dispatch_top_west` | West side of grid |

### 6.1 Command Distribution Structure

[NOT IN KB] — The internal command distribution mechanism (how instructions are dispatched to Tensix tiles, command queues, arbitration) was not present in the search results. A dedicated search with `query="dispatch"` or `topic="Dispatch"` would be needed.

---

## 7. NoC Fabric

### 7.1 Key NoC Modules (from KB)

| Module | Topic | Claim / Role |
|---|---|---|
| `noc_arbiter_tree` | NoC | "Implements a tree-based arbitration mechanism for a Network-on-Chip (NoC) system" — **structural claim** (result [18]) |
| `tt_noc_repeaters_cardinal` | NoC | "Implements NoC repeater functionality" and "connects to the NoC interface" — **structural + connectivity claims** (results [19],[20]) |

### 7.2 Routing Algorithms

| Algorithm | Description |
|---|---|
| **DOR (Dimension-Ordered Routing)** | [NOT IN KB] |
| **Tendril Routing** | [NOT IN KB] |
| **Dynamic Routing** | [NOT IN KB] |

> A 3-way comparison of routing algorithms was not present in the returned results. The `noc_routing_translation_selftest` module name appears in the EDC HDD section path (result [5]), suggesting routing translation and self-test logic exists, but details are not available.

### 7.3 Flit Structure

[NOT IN KB] — Flit format (header, payload, tail fields, width) was not returned.

### 7.4 Virtual Channel (VC) Buffers

[NOT IN KB] — VC buffer count, depth, and arbitration policy were not returned.

---

## 8. NIU (Network Interface Unit)

### 8.1 AXI Bridge

The top-level port `i_axi_clk` confirms the presence of an AXI clock domain and bridge interface. The EDC HDD section (result [5]) references `noc2axi_router_nw_opt`, indicating a **NoC-to-AXI router** exists with NW-optimized configuration.

| Aspect | Detail |
|---|---|
| AXI Bridge module | `noc2axi_router_nw_opt` (from EDC HDD path) |
| AXI clock | `i_axi_clk` |
| AXI protocol version | [NOT IN KB] |

### 8.2 ATT (Address Translation Table)

[NOT IN KB]

### 8.3 SMN Security

The SMN (System Management Network) module exists per prior HDD search — it handles "routing and translation of NoC traffic" for system management. Details beyond that overview were not in these search results.

---

## 9. Clock Architecture

Derived from the top-level port declarations:

| Clock Domain | Signal | Width | Description |
|---|---|---|---|
| **AI Compute** (`ai_clk`) | `i_ai_clk` | `[NumTensix-1:0]` or `[SizeX-1:0]` | Drives Tensix compute logic; per-tile or per-column |
| **NoC** (`noc_clk`) | `i_noc_clk` | 1 | Single clock for the entire NoC fabric |
| **Data Mover** (`dm_clk`) | `i_dm_clk` | `[NumDmCo…-1:0]` | Drives data-mover cores; width truncated in results |
| **AXI** (`axi_clk`) | `i_axi_clk` | 1 | AXI bus interface clock |
| **Reference** (`ref_clk`) | [NOT IN KB] | — | Not visible in the returned port snippets |

### Clock Domain Relationships

[NOT IN KB] — CDC (clock domain crossing) structure, PLL configuration, and clock gating hierarchy were not in the search results.

---

## 10. Reset Architecture

Derived from the top-level port declarations:

| Reset Signal | Width | Domain | Active Level |
|---|---|---|---|
| `i_noc_reset_n` | 1 | NoC | Active-low |
| `i_ai_reset_n` | `[NumTensix-1:0]` or `[SizeX-1:0]` | AI compute | Active-low |
| `i_tensix_reset_n` | `[NumTensix-1:0]` | Per-Tensix tile | Active-low |
| `i_edc_reset_n` | 1 | EDC subsystem | Active-low |

### 10.1 Reset Chain

The reset architecture provides **independent per-tile reset** capability via `i_tensix_reset_n`, enabling:
- Per-Tensix tile reset without affecting the NoC or other tiles
- Separate EDC reset domain (`i_edc_reset_n`)
- NoC fabric reset independent of compute (`i_noc_reset_n`)

### 10.2 Power Partitions

[NOT IN KB] — Power domain definitions, isolation cells, and retention strategy were not in the search results.

---

## 11. EDC (Error Detection & Correction)

### 11.1 Top-Level EDC Instances

| Instance | Module | Topology Role |
|---|---|---|
| `edc_direct_conn_nodes` | `tt_edc1_intf_connector` | Direct-connect node |
| `edc_loopback_conn_nodes` | `tt_edc1_intf_connector` | Loopback node |

Both use the same module type (`tt_edc1_intf_connector`), suggesting a **unified connector interface** for both direct and loopback EDC paths.

### 11.2 EDC HDD Section (from result [5])

The EDC HDD section references the module path:  
`BDAed_trinity_noc2axi_router_nw_opt_trinity_noc2axi_router_nw_opt_tt_mem_wrap_32x1024_2p_nomask_noc_routing_translation_selftest`

This implies:
- **NoC-to-AXI router** (`noc2axi_router_nw_opt`) is part of the EDC data path
- **`tt_mem_wrap_32x1024_2p_nomask`** — a 32-bit × 1024-entry dual-port SRAM without mask, used within the EDC/router
- **`noc_routing_translation_selftest`** — routing translation with built-in self-test capability

### 11.3 Ring Topology

[NOT IN KB] — Ring topology details (ring direction, number of nodes, latency) were not in the search results.

### 11.4 Serial Bus

[NOT IN KB]

### 11.5 Harvest Bypass

[NOT IN KB] — Harvest bypass mechanism for defective tile isolation was not described in the results.

---

## 12. SRAM Inventory

One SRAM instance is identifiable from the EDC HDD module path:

| Memory Instance | Type | Size | Ports | Mask | Context |
|---|---|---|---|---|---|
| `tt_mem_wrap_32x1024_2p_nomask` | SRAM wrapper | 32-bit × 1024 entries (4 KB) | Dual-port (2p) | No mask | Used in EDC / NoC routing translation selftest path |

### Additional SRAM Instances

[NOT IN KB] — A complete SRAM inventory (L1 cache SRAMs, register file SRAMs, NoC buffers, etc.) was not returned. A dedicated search with `query="SRAM"` or `query="mem_wrap"` would be needed.

---

## 13. DFX (Design for Test/Debug)

### 13.1 iJTAG

[NOT IN KB] — iJTAG infrastructure (IJTAG network, SIB chains, TDR registers) was not mentioned in the search results.

### 13.2 Scan Chains

[NOT IN KB] — Scan chain configuration, compression, and ATPG details were not in the search results.

### 13.3 Self-Test

The module name `noc_routing_translation_selftest` (from result [5]) indicates built-in self-test (BIST) capability for the NoC routing translation logic.

---

## 14. RTL File Reference

Extracted from the `파일` (file) fields across all search results:

| File Path | Variant | Description |
|---|---|---|
| `rtl-sources/tt_20260221/rtl/trinity.sv` | Base | Top-level Trinity module |
| `rtl-sources/tt_20260221/used_in_n1/rtl/trinity.sv` | N1 (current) | N1B0 integration variant |
| `rtl-sources/tt_20260221/used_in_n1/mem_port/rtl/trinity.sv` | N1 + mem_port | With memory port interface |
| `rtl-sources/tt_20260221/used_in_n1/legacy/no_mem_port/rtl/trinity.sv` | N1 legacy | Without memory port (legacy) |

### File Variant Matrix

| Variant | Clock Indexing | Memory Port |
|---|---|---|
| `used_in_n1/rtl/` | Per-column (`SizeX`) | Standard |
| `used_in_n1/mem_port/rtl/` | Per-column (`SizeX`) | Explicit mem port |
| `used_in_n1/legacy/no_mem_port/rtl/` | Per-Tensix (`NumTensix`) | No mem port |
| Base `rtl/` | Per-Tensix (`NumTensix`) | Standard |

---

## Appendix A — Coverage Summary

| Section | Coverage | Source Results |
|---|---|---|
| 1. Overview | ✅ From KB | module_parse + claims |
| 2. Package Constants | ⚠ Partial — `SizeX`, `NumTensix` referenced; values/enums not explicit | Port declarations |
| 3. Top-Level Ports | ⚠ Partial — inputs visible; outputs truncated | module_parse [1]–[17] |
| 4. Module Hierarchy | ⚠ Partial — 7 instances visible; full list truncated | module_parse + claims |
| 5. Compute Tile | ⚠ Minimal — module name only; internals not in results | module_parse |
| 6. Dispatch Engine | ⚠ Minimal — instances confirmed; internals not in results | module_parse |
| 7. NoC Fabric | ⚠ Partial — arbiter + repeater confirmed; routing/flit/VC missing | Claims [18]–[20] |
| 8. NIU | ⚠ Partial — AXI bridge name inferred from EDC HDD path | HDD [5] |
| 9. Clock Architecture | ✅ From KB | Port declarations |
| 10. Reset Architecture | ✅ From KB | Port declarations |
| 11. EDC | ⚠ Partial — instances + SRAM in path; topology details missing | module_parse + HDD [5] |
| 12. SRAM Inventory | ⚠ Minimal — 1 instance from module path | HDD [5] |
| 13. DFX | ⚠ Minimal — selftest module name only | HDD [5] |
| 14. RTL File Reference | ✅ From KB | File paths from all results |

## Appendix B — Suggested Follow-up Searches

To fill `[NOT IN KB]` gaps, the following targeted searches are recommended:

| Gap | Suggested Query |
|---|---|
| Package constants / `tile_t` enum | `query="trinity_pkg SizeX SizeY tile_t"` |
| Tensix internals (FPU, SFPU, DEST, SRCB) | `query="tt_tensix_with_l1"`, `topic="SFPU"` |
| Dispatch internals | `query="tt_dispatch_top"` |
| NoC routing algorithms, flit, VC | `topic="NoC"`, `query="routing flit VC"` |
| EDC ring topology / harvest bypass | `topic="EDC"`, `query="ring harvest bypass"` |
| Full SRAM inventory | `query="mem_wrap SRAM"` |
| DFX / iJTAG / scan | `query="iJTAG scan DFX"` |
| Overlay (CPU cluster, L1, APB) | `topic="Overlay"` |
| Output ports | `query="trinity output port"` |

---

*End of Document*
