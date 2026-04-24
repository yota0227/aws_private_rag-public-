# EDC1 Subsystem — Hardware Design Document (HDD)

> **Pipeline:** `tt_20260221`
> **Source:** RTL search — topic `EDC`, 5 of 74 results retrieved
> **Grounding rule:** Only information present in search results is included. Missing items marked `[NOT IN KB]`.
> **Date:** 2026-04-22

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Serial Bus Interface](#3-serial-bus-interface)
4. [Packet Format](#4-packet-format)
5. [Node ID Structure](#5-node-id-structure)
6. [Module Hierarchy](#6-module-hierarchy)
7. [Ring Topology](#7-ring-topology)
8. [Harvest Bypass](#8-harvest-bypass)
9. [BIU (Bus Interface Unit)](#9-biu-bus-interface-unit)
10. [CDC / Synchronization](#10-cdc--synchronization)
11. [Instance Paths](#11-instance-paths)

---

## 1. Overview

### 1.1 What the Search Results Tell Us

All five search results describe the module **`trinity_noc2axi_router_ne_opt_FBLC`** tagged under topic **EDC** within the `tt_20260221` pipeline. The results provide slightly varying descriptions of the EDC acronym:

| Result | EDC Expansion | Description |
|--------|---------------|-------------|
| [1] | Embedded Debug Connectivity | Critical component in the NoC2AXI Router architecture |
| [2] | Embedded Data Controller | Implements NoC-to-AXI router functionality; optimizes performance and resource utilization |
| [3] | Embedded Data Concentrator | Routes and manages communication between NoC and AXI |
| [4] | Embedded Device Controller | Block-level component; connects NoC to AXI |
| [5] | Embedded Distributed Controller | NoC-to-AXI router optimization for the North-East direction |

**Key observations from search results:**
- The EDC-tagged module in this pipeline is `trinity_noc2axi_router_ne_opt_FBLC`
- It sits at the interface between NoC (Network-on-Chip) and AXI (Advanced eXtensible Interface)
- It is optimized for the **North-East (NE)** direction
- The suffix `FBLC` indicates a specific optimization variant
- The module is described as "block-level" in the Trinity SoC design

### 1.2 EDC1 Specifics Requested but Not Found

The following EDC1-specific characteristics were requested but are **not present** in the search results:

| Item | Status |
|------|--------|
| EDC1 version identifier | `[NOT IN KB]` |
| Toggle-handshake protocol (req_tgl / ack_tgl) | `[NOT IN KB]` — These signals were found in a *separate* `module_parse` search of `tt_edc_pkg.sv` (not in this search) |
| 16-bit data + parity bus width | `[NOT IN KB]` |

---

## 2. Architecture

### 2.1 System-Level Block Context (from search results)

Based on the search results, the EDC-related block sits in the following architectural position:

```
┌─────────────────────────────────────────────┐
│              Trinity SoC                     │
│                                              │
│   ┌──────────┐     ┌─────────────────────┐  │
│   │   NoC    │◄───►│ trinity_noc2axi_    │  │
│   │ Fabric   │     │ router_ne_opt_FBLC  │  │
│   └──────────┘     │   (EDC topic)       │  │
│                    │                     │  │
│                    │  • NE direction opt  │  │
│                    │  • FBLC variant      │  │
│                    └──────────┬──────────┘  │
│                               │              │
│                          AXI Interface       │
│                               │              │
│                    ┌──────────▼──────────┐  │
│                    │  AXI Subordinates    │  │
│                    └─────────────────────┘  │
└─────────────────────────────────────────────┘
```

### 2.2 Detailed Internal Block Diagram

`[NOT IN KB]` — The search results describe the module's role but do not provide internal block-level decomposition.

---

## 3. Serial Bus Interface

### 3.1 Signals from Search Results

The current search (topic: EDC) did **not** return signal-level detail for the serial bus interface.

| Signal | Description | Status |
|--------|-------------|--------|
| `req_tgl` | Toggle-based request | `[NOT IN KB]` in this search (found in prior `tt_edc_pkg.sv` module_parse) |
| `ack_tgl` | Toggle-based acknowledge | `[NOT IN KB]` in this search (found in prior `tt_edc_pkg.sv` module_parse) |
| `data` | Serial data bus | `[NOT IN KB]` |
| `data_p` | Parity for data bus | `[NOT IN KB]` |
| `async_init` | Asynchronous initialization | `[NOT IN KB]` |

### 3.2 Known from Prior Searches (Cross-Reference Only)

> ⚠️ The following is **not** from this search but from a prior `module_parse` result for `tt_edc_pkg.sv`. Included for cross-reference only.

The `tt_edc_pkg.sv` file defines modports: `ingress`, `egress`, `edc_node`, `sram` with ports `req_tgl`, `ack_tgl`, `cor_err`, `err_inj_vec`.

---

## 4. Packet Format

| Item | Status |
|------|--------|
| Fragment structure | `[NOT IN KB]` |
| `MAX_FRGS` constant | `[NOT IN KB]` |
| Packet header fields | `[NOT IN KB]` |
| CRC / ECC coverage | `[NOT IN KB]` |

---

## 5. Node ID Structure

| Field | Description | Status |
|-------|-------------|--------|
| `node_id_part` | Partition ID | `[NOT IN KB]` |
| `node_id_subp` | Sub-partition ID | `[NOT IN KB]` |
| `node_id_inst` | Instance ID | `[NOT IN KB]` |

---

## 6. Module Hierarchy

### 6.1 What the Search Results Confirm

The only module confirmed across all 5 results:

```
trinity_noc2axi_router_ne_opt_FBLC    (EDC topic, block-level)
```

### 6.2 Expected tt_edc1_* Hierarchy

`[NOT IN KB]` — No `tt_edc1_*` sub-module names appear in the search results.

---

## 7. Ring Topology

### 7.1 U-Shape Ring Structure

`[NOT IN KB]` — The search results do not describe the ring topology, U-turn routing, or segment A/B structure.

```
Expected (not confirmed):

  Segment A (Downward)        Segment B (Upward)
  ┌──────────┐                ┌──────────┐
  │ Node 0   │                │ Node 0   │
  │    ↓     │                │    ↑     │
  │ Node 1   │                │ Node 1   │
  │    ↓     │                │    ↑     │
  │ Node 2   │                │ Node 2   │
  │    ↓     │                │    ↑     │
  │ Node 3   │     U-turn     │ Node 3   │
  └────┬─────┘  ◄──────────►  └──────────┘

  ⚠️ This diagram is illustrative only — [NOT IN KB]
```

---

## 8. Harvest Bypass

| Item | Status |
|------|--------|
| Mux/demux bypass mechanism | `[NOT IN KB]` |
| `edc_mux_demux_sel` signal | `[NOT IN KB]` |
| Harvested-tile skip logic | `[NOT IN KB]` |

---

## 9. BIU (Bus Interface Unit)

| Item | Status |
|------|--------|
| Register access path | `[NOT IN KB]` |
| APB / AXI subordinate mapping | Implied by module role (NoC-to-AXI bridge) but no register map in results |
| Address decode logic | `[NOT IN KB]` |

---

## 10. CDC / Synchronization

| Item | Status |
|------|--------|
| Clock domain crossing strategy | `[NOT IN KB]` |
| Synchronizer type (2FF / handshake / async FIFO) | `[NOT IN KB]` |
| Clock domains involved | `[NOT IN KB]` |

---

## 11. Instance Paths

### 11.1 Confirmed Module Name

```
trinity_noc2axi_router_ne_opt_FBLC
```

- Pipeline: `tt_20260221`
- Direction: North-East (NE) optimized
- Variant: FBLC

### 11.2 Full Hierarchical Paths within Trinity

`[NOT IN KB]` — The search results identify the module name but do not provide full instance paths (e.g., `trinity.u_xxx.u_yyy.u_edc_*`).

---

## Appendix A — Search Result Summary

| # | Topic | Type | Module | Key Description |
|---|-------|------|--------|-----------------|
| 1 | EDC | hdd_section | `trinity_noc2axi_router_ne_opt_FBLC` | Embedded Debug Connectivity; critical NoC2AXI Router component |
| 2 | EDC | hdd_section | `trinity_noc2axi_router_ne_opt_FBLC` | Embedded Data Controller; optimizes performance and resources |
| 3 | EDC | hdd_section | `trinity_noc2axi_router_ne_opt_FBLC` | Embedded Data Concentrator; manages NoC ↔ AXI communication |
| 4 | EDC | hdd_section | `trinity_noc2axi_router_ne_opt_FBLC` | Embedded Device Controller; NoC-to-AXI connection |
| 5 | EDC | hdd_section | `trinity_noc2axi_router_ne_opt_FBLC` | Embedded Distributed Controller; NE direction optimization |

**Total in KB:** 74 results available, 5 returned.

---

## Appendix B — Gap Analysis & Recommended Next Searches

| Priority | Missing Section | Recommended Search |
|----------|----------------|--------------------|
| 🔴 Critical | Serial Bus Interface signals | `query: "req_tgl ack_tgl data_p"`, `analysis_type: "module_parse"` |
| 🔴 Critical | Ring Topology / U-shape | `query: "edc ring segment u-turn"`, `topic: "EDC"` |
| 🔴 Critical | Module Hierarchy (tt_edc1_*) | `query: "tt_edc1"`, `analysis_type: "hierarchy"` |
| 🟡 Medium | Packet Format / MAX_FRGS | `query: "MAX_FRGS fragment edc"`, `analysis_type: "claim"` |
| 🟡 Medium | Node ID decoding | `query: "node_id_part node_id_subp"`, `analysis_type: "claim"` |
| 🟡 Medium | Harvest Bypass mux/demux | `query: "edc_mux_demux_sel harvest bypass"` |
| 🟢 Low | CDC / Synchronization | `query: "edc cdc synchronizer async"` |
| 🟢 Low | BIU register map | `query: "edc biu register apb"` |

---

*Document generated from a single RTL search call. Sections marked `[NOT IN KB]` require additional targeted searches to populate.*
