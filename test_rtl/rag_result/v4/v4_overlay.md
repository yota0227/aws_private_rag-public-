# Overlay (RISC-V Subsystem) — Hardware Design Document (HDD)

**Pipeline ID:** `tt_20260221`  
**Document Version:** v4  
**Generated:** 2026-04-24  
**Source:** RTL Knowledge Base — `search_rtl(pipeline_id="tt_20260221", topic="Overlay", query="Overlay RISC-V CPU cluster tt_overlay")` — **0 results returned**  
**Supplementary Data:** Prior trinity `module_parse` results from the same pipeline (instances, ports, file paths)  
**Method:** Single search call. All content derived strictly from KB data.

> **Integrity Rule:** Only information present in KB search results is stated as fact. Anything not found is explicitly marked **[NOT IN KB]**. RTL signal and module names are preserved verbatim. The search for `topic="Overlay"` returned **zero results** — this document therefore relies solely on cross-references from prior trinity top-level searches and marks all Overlay-internal details as `[NOT IN KB]`.

---

## Table of Contents

1.  [Overview](#1-overview)
2.  [Position in Grid](#2-position-in-grid)
3.  [Feature Summary](#3-feature-summary)
4.  [Block Diagram](#4-block-diagram)
5.  [Sub-module Hierarchy](#5-sub-module-hierarchy)
6.  [Feature Details](#6-feature-details)
7.  [Control Path](#7-control-path)
8.  [Key Parameters](#8-key-parameters)
9.  [Clock / Reset Summary](#9-clock--reset-summary)
10. [APB Register Interfaces](#10-apb-register-interfaces)
11. [Verification Checklist](#11-verification-checklist)
12. [Key RTL File Index](#12-key-rtl-file-index)

---

## 1. Overview

### 1.1 Role of the Overlay Block

The **Overlay** is the RISC-V CPU subsystem within the Trinity N1B0 SoC. It serves as the **glue logic** that orchestrates:

- A **CPU cluster** of RISC-V cores for control-plane processing
- **L1 cache** for low-latency data access
- **NoC interface** for communication with the wider tile grid
- **DMA engine** for bulk data movement

> ⚠ **[NOT IN KB]** — The `topic="Overlay"` search returned **0 results** from the RTL Knowledge Base for pipeline `tt_20260221`. The Overlay block description above is based on the requested document structure. None of the internal details below could be confirmed from KB data.

### 1.2 Evidence from Trinity Top-Level

From prior `trinity` module_parse searches, the top-level instance list includes:

| Instance (from trinity) | Module | Relevance to Overlay |
|---|---|---|
| `tt_tensix_with_l1` | `tt_tensix_with_l1` | Tensix compute tile with L1 — may share L1 architecture with Overlay |
| `tt_dispatch_top_inst_east` | `tt_dispatch_top_east` | Dispatch engine (East) — Overlay may interact with dispatch |
| `tt_dispatch_top_inst_west` | `tt_dispatch_top_west` (inferred) | Dispatch engine (West) |

**No `tt_overlay_wrapper` or `tt_overlay_*` instance** was visible in the (truncated) trinity instance list from prior searches. This could mean:
1. The Overlay instance name was truncated in prior results, or
2. The Overlay is not instantiated at the trinity top level in this pipeline variant, or
3. The Overlay is instantiated under a different name

---

## 2. Position in Grid

### 2.1 Grid Placement

The Trinity N1B0 uses a **4×5 tile grid** (`SizeX=4`, `SizeY=5`) with `NumTensix=12` compute tiles.

```
        X=0         X=1         X=2         X=3
     ┌───────────┬───────────┬───────────┬───────────┐
Y=0  │           │           │           │           │
     ├───────────┼───────────┼───────────┼───────────┤
Y=1  │           │           │           │           │
     ├───────────┼───────────┼───────────┼───────────┤
Y=2  │           │           │           │           │
     ├───────────┼───────────┼───────────┼───────────┤
Y=3  │           │           │           │           │
     ├───────────┼───────────┼───────────┼───────────┤
Y=4  │           │           │           │           │
     └───────────┴───────────┴───────────┴───────────┘

  Overlay tile position(s): [NOT IN KB]
  Known: 12 × Tensix, 2 × Dispatch (East/West), EDC nodes
  Remaining 6 positions: Overlay, NIU, router(empty), other — assignment unknown
```

[NOT IN KB] — The specific (X,Y) coordinates occupied by the Overlay tile(s) were not returned.

---

## 3. Feature Summary

| Feature | Description | Status |
|---|---|---|
| CPU Cluster | 8× RISC-V cores (`NUM_CLUSTER_CPUS`) | [NOT IN KB] |
| L1 Cache | Multi-bank cache with ECC | [NOT IN KB] |
| iDMA Engine | Integrated DMA for bulk data movement | [NOT IN KB] |
| ROCC Accelerator | RISC-V Custom Coprocessor interface | [NOT IN KB] |
| LLK | Low-Latency Kernel support logic | [NOT IN KB] |
| SMN | System Maintenance Network interface | SMN module confirmed in prior HDD search |
| FDS | Frequency / Droop Sensor | [NOT IN KB] |
| Dispatch Interface | Connection to East/West dispatch engines | Dispatch instances confirmed at trinity top |
| NoC Interface | Connection to 2D mesh NoC fabric | `i_noc_clk`, `i_noc_reset_n` confirmed |
| APB Register Bus | Slave interfaces for configuration | [NOT IN KB] |

---

## 4. Block Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                     tt_overlay_wrapper [NOT IN KB]                │
│                                                                  │
│  ┌──────────────────┐    ┌─────────────┐    ┌────────────────┐  │
│  │   CPU Cluster    │    │   L1 Cache   │    │   iDMA Engine  │  │
│  │  8× RISC-V cores │◄──►│  [banks?]    │◄──►│   [NOT IN KB]  │  │
│  │  [NOT IN KB]     │    │  [NOT IN KB] │    │                │  │
│  └────────┬─────────┘    └──────┬───────┘    └───────┬────────┘  │
│           │                     │                     │          │
│           ▼                     ▼                     ▼          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    Internal Interconnect                    │  │
│  │                       [NOT IN KB]                          │  │
│  └───┬──────────┬──────────┬──────────┬──────────┬────────────┘  │
│      │          │          │          │          │                │
│      ▼          ▼          ▼          ▼          ▼                │
│  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌──────────┐          │
│  │ ROCC  │ │  LLK  │ │  SMN  │ │  FDS  │ │ Dispatch │          │
│  │[N.I.K]│ │[N.I.K]│ │ConfMd │ │[N.I.K]│ │Interface │          │
│  └───────┘ └───────┘ └───────┘ └───────┘ └──────────┘          │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                 APB Register Bus [NOT IN KB]               │  │
│  └────────────────────────────────────────────────────────────┘  │
│                          │                                       │
│                          ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              NoC Interface (to 2D mesh fabric)             │  │
│  │              i_noc_clk / i_noc_reset_n                     │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘

  [N.I.K] = [NOT IN KB]
  SMN ConfMd = SMN confirmed from prior HDD search (routing & translation of NoC traffic)
```

---

## 5. Sub-module Hierarchy

### 5.1 Expected `tt_overlay_wrapper` Tree

[NOT IN KB] — The `tt_overlay_wrapper` module and its sub-hierarchy were not returned by the search.

```
tt_overlay_wrapper                          [NOT IN KB]
├── cpu_cluster                             [NOT IN KB]
│   ├── riscv_core[0..7]                    [NOT IN KB]
│   ├── icache                              [NOT IN KB]
│   └── dcache                              [NOT IN KB]
├── l1_cache                                [NOT IN KB]
│   ├── l1_bank[0..N]                       [NOT IN KB]
│   └── l1_ecc                              [NOT IN KB]
├── idma_engine                             [NOT IN KB]
├── rocc_accelerator                        [NOT IN KB]
├── llk_block                               [NOT IN KB]
├── smn_interface                           Confirmed: SMN module exists (prior HDD search)
├── fds_sensor                              [NOT IN KB]
├── dispatch_interface                      Inferred: connects to tt_dispatch_top_east/west
├── apb_bus                                 [NOT IN KB]
│   └── apb_slave[0..M]                     [NOT IN KB]
└── noc_interface                           Inferred: NoC ports confirmed at trinity top
```

> ⚠ Every node marked `[NOT IN KB]` means the module name, instance name, and internal structure were not found in any KB search for this pipeline.

---

## 6. Feature Details

### 6.1 CPU Cluster

| Attribute | Detail |
|---|---|
| Core count | 8 (`NUM_CLUSTER_CPUS = 8`) — [NOT IN KB] |
| ISA | RISC-V (RV32/RV64) — [NOT IN KB] |
| ISA extensions | [NOT IN KB] |
| Pipeline depth | [NOT IN KB] |
| Branch predictor | [NOT IN KB] |
| Core module name | [NOT IN KB] |
| I-cache per core | [NOT IN KB] |
| D-cache per core | [NOT IN KB] |

### 6.2 L1 Cache

| Attribute | Detail |
|---|---|
| Number of banks | [NOT IN KB] |
| Bank width | [NOT IN KB] |
| Total capacity | [NOT IN KB] |
| ECC type | [NOT IN KB] (expected: SECDED or parity) |
| SRAM type | [NOT IN KB] (expected: single-port or dual-port) |
| SRAM module name | [NOT IN KB] (note: `tt_mem_wrap_32x1024_2p_nomask` exists in NoC/EDC path but is not confirmed as L1) |

### 6.3 iDMA Engine

| Attribute | Detail |
|---|---|
| Module name | [NOT IN KB] |
| Channel count | [NOT IN KB] |
| Max burst length | [NOT IN KB] |
| Descriptor format | [NOT IN KB] |
| NoC interface | [NOT IN KB] |

### 6.4 ROCC Accelerator

| Attribute | Detail |
|---|---|
| Module name | [NOT IN KB] |
| Custom instruction encoding | [NOT IN KB] |
| Data width | [NOT IN KB] |
| Attached to core(s) | [NOT IN KB] |

### 6.5 LLK (Low-Latency Kernel)

| Attribute | Detail |
|---|---|
| Module name | [NOT IN KB] |
| Purpose | Low-latency kernel execution support — [NOT IN KB] |
| Interface to CPU | [NOT IN KB] |
| Interface to NoC | [NOT IN KB] |

### 6.6 SMN (System Maintenance Network)

| Attribute | Detail |
|---|---|
| Confirmed | ✅ — SMN module exists per prior HDD search |
| Role | "Routing and translation of NoC traffic" for system management |
| Module name | [NOT IN KB] — specific instance name within Overlay unknown |
| Register space | [NOT IN KB] |

### 6.7 FDS (Frequency / Droop Sensor)

| Attribute | Detail |
|---|---|
| Module name | [NOT IN KB] |
| Sensor type | [NOT IN KB] |
| Output interface | [NOT IN KB] |
| Clock domain | [NOT IN KB] |

### 6.8 Dispatch Engine

| Attribute | Detail |
|---|---|
| Confirmed | ✅ — `tt_dispatch_top_inst_east` (`tt_dispatch_top_east`) and `tt_dispatch_top_inst_west` (inferred) at trinity top |
| Interface to Overlay | [NOT IN KB] — how Overlay connects to dispatch unknown |
| Command format | [NOT IN KB] |

---

## 7. Control Path

### 7.1 CPU-to-NoC Write Path (Expected)

[NOT IN KB] — The exact data path was not returned. Expected flow:

```
RISC-V Core
    │ (store instruction)
    ▼
D-Cache / L1 Cache                     [NOT IN KB]
    │ (cache miss or uncacheable)
    ▼
Internal Interconnect                   [NOT IN KB]
    │
    ▼
NoC Interface (Overlay → NoC)          Inferred from trinity ports
    │ (NoC write transaction)
    ▼
NoC Fabric (2D mesh)                   Confirmed: noc_arbiter_tree, tt_noc_repeaters_cardinal
    │
    ▼
Destination Tile Endpoint
```

### 7.2 CPU-to-NoC Read Path (Expected)

```
RISC-V Core
    │ (load instruction)
    ▼
D-Cache / L1 Cache                     [NOT IN KB]
    │ (cache miss)
    ▼
Internal Interconnect                   [NOT IN KB]
    │
    ▼
NoC Interface (Overlay → NoC)          Inferred
    │ (NoC read request)
    ▼
NoC Fabric → Destination Tile
    │ (NoC read response)
    ▼
NoC Interface (NoC → Overlay)
    │
    ▼
L1 Cache (fill) → D-Cache → Core
```

---

## 8. Key Parameters

### 8.1 `tt_overlay_pkg.sv` Parameters

[NOT IN KB] — The `tt_overlay_pkg.sv` file and its contents were not returned.

| Parameter | Expected Value | Status |
|---|---|---|
| `NUM_CLUSTER_CPUS` | 8 | [NOT IN KB] |
| `L1_NUM_BANKS` | [NOT IN KB] | — |
| `L1_BANK_WIDTH` | [NOT IN KB] | — |
| `L1_TOTAL_SIZE` | [NOT IN KB] | — |
| `IDMA_NUM_CHANNELS` | [NOT IN KB] | — |
| `ROCC_DATA_WIDTH` | [NOT IN KB] | — |
| `APB_ADDR_WIDTH` | [NOT IN KB] | — |
| `APB_DATA_WIDTH` | [NOT IN KB] | — |
| `NUM_APB_SLAVES` | [NOT IN KB] | — |

---

## 9. Clock / Reset Summary

### 9.1 Multi-Clock Domain Structure

From the trinity top-level port analysis:

| Clock Domain | Signal | Relevance to Overlay |
|---|---|---|
| AI Compute | `i_ai_clk` | May clock Overlay compute logic (RISC-V cores) |
| NoC | `i_noc_clk` | Clocks Overlay's NoC interface |
| Data Mover | `i_dm_clk` | May clock iDMA engine |
| AXI | `i_axi_clk` | May clock AXI bridge within Overlay |

### 9.2 Reset Signals

| Reset | Signal | Relevance to Overlay |
|---|---|---|
| NoC reset | `i_noc_reset_n` | Resets Overlay's NoC interface |
| AI reset | `i_ai_reset_n` | May reset Overlay compute logic |
| Tensix reset | `i_tensix_reset_n` | Per-Tensix — Overlay may have its own index |
| EDC reset | `i_edc_reset_n` | May reset Overlay's EDC node (if present) |

### 9.3 Overlay-Specific Clock

[NOT IN KB] — Whether Overlay has a dedicated clock (e.g., `i_overlay_clk`) or shares one of the above domains is unknown.

---

## 10. APB Register Interfaces

### 10.1 APB Slave List

[NOT IN KB] — The APB slave modules, their base addresses, and address ranges within the Overlay were not returned.

| Slave # | Module | Base Address | Size | Description |
|---|---|---|---|---|
| 0 | [NOT IN KB] | [NOT IN KB] | [NOT IN KB] | [NOT IN KB] |
| 1 | [NOT IN KB] | [NOT IN KB] | [NOT IN KB] | [NOT IN KB] |
| … | … | … | … | … |

### 10.2 APB Address Map

[NOT IN KB] — The full address map was not returned. Expected structure:

```
0x0000_0000 ┌──────────────────┐
            │  Slave 0 (CSR)   │  [NOT IN KB]
0x0000_XXXX ├──────────────────┤
            │  Slave 1 (L1)    │  [NOT IN KB]
0x0000_XXXX ├──────────────────┤
            │  Slave 2 (DMA)   │  [NOT IN KB]
            │       ...        │
0x0000_XXXX └──────────────────┘
```

---

## 11. Verification Checklist

Based on the Overlay features (all verification items are **[NOT IN KB]** — included as a structural template):

| # | Verification Item | Type | Status |
|---|---|---|---|
| 1 | CPU cluster boot sequence | Functional | [NOT IN KB] |
| 2 | L1 cache hit/miss paths | Functional | [NOT IN KB] |
| 3 | L1 ECC single-bit correct, double-bit detect | Functional | [NOT IN KB] |
| 4 | iDMA single-channel transfer | Functional | [NOT IN KB] |
| 5 | iDMA multi-channel arbitration | Functional | [NOT IN KB] |
| 6 | ROCC custom instruction execution | Functional | [NOT IN KB] |
| 7 | LLK low-latency path timing | Performance | [NOT IN KB] |
| 8 | SMN register read/write via EDC | Functional | Partially verifiable (SMN confirmed) |
| 9 | FDS droop detection and response | Functional | [NOT IN KB] |
| 10 | Dispatch command reception from East/West | Functional | Dispatch instances confirmed |
| 11 | NoC write/read transactions end-to-end | Functional | NoC fabric confirmed |
| 12 | APB slave address decode | Functional | [NOT IN KB] |
| 13 | Clock domain crossing (CDC) | Structural | Clock domains confirmed |
| 14 | Reset sequencing | Functional | Reset signals confirmed |
| 15 | Harvest bypass (if Overlay tile is harvestable) | Functional | [NOT IN KB] |

---

## 12. Key RTL File Index

### 12.1 Confirmed Files (from prior searches)

| File | Content |
|---|---|
| `rtl-sources/tt_20260221/rtl/trinity.sv` | Top-level — instantiates Overlay (if present) |
| `rtl-sources/tt_20260221/used_in_n1/rtl/trinity.sv` | N1 integration variant |
| `rtl-sources/tt_20260221/used_in_n1/mem_port/rtl/trinity.sv` | N1 + memory port variant |
| `rtl-sources/tt_20260221/used_in_n1/legacy/no_mem_port/rtl/trinity.sv` | N1 legacy variant |

### 12.2 Expected Overlay Files (NOT IN KB)

| Expected File | Content |
|---|---|
| `tt_overlay_wrapper.sv` | [NOT IN KB] — Overlay top-level wrapper |
| `tt_overlay_pkg.sv` | [NOT IN KB] — Overlay parameters and types |
| `tt_overlay_cpu_cluster.sv` | [NOT IN KB] — CPU cluster instantiation |
| `tt_overlay_l1_cache.sv` | [NOT IN KB] — L1 cache sub-block |
| `tt_overlay_idma.sv` | [NOT IN KB] — iDMA engine |
| `tt_overlay_rocc.sv` | [NOT IN KB] — ROCC accelerator interface |
| `tt_overlay_llk.sv` | [NOT IN KB] — Low-latency kernel block |
| `tt_overlay_smn.sv` | [NOT IN KB] — SMN interface |
| `tt_overlay_fds.sv` | [NOT IN KB] — Frequency/droop sensor |
| `tt_overlay_apb.sv` | [NOT IN KB] — APB bus and slave decoder |

---

## Appendix A — Coverage Summary

| Section | Coverage | Notes |
|---|---|---|
| 1. Overview | ❌ NOT IN KB | Zero Overlay results; description is structural template only |
| 2. Position in Grid | ❌ NOT IN KB | Grid dimensions known; Overlay position unknown |
| 3. Feature Summary | ❌ NOT IN KB | All features are expected but unconfirmed |
| 4. Block Diagram | ❌ NOT IN KB | Diagram is structural template; no confirmed internals |
| 5. Sub-module Hierarchy | ❌ NOT IN KB | `tt_overlay_wrapper` not found |
| 6. Feature Details | ⚠ Minimal | Only SMN and Dispatch cross-referenced from prior searches |
| 7. Control Path | ❌ NOT IN KB | Paths are expected flow; not confirmed |
| 8. Key Parameters | ❌ NOT IN KB | `tt_overlay_pkg.sv` not found |
| 9. Clock/Reset | ⚠ Partial | Top-level clock/reset domains confirmed; Overlay-specific unknown |
| 10. APB Interfaces | ❌ NOT IN KB | No APB slave data returned |
| 11. Verification Checklist | ❌ NOT IN KB | Template only; no test status available |
| 12. RTL File Index | ⚠ Partial | Top-level files confirmed; Overlay-specific files unknown |

**Overall: 0 out of 12 sections have substantive KB-confirmed Overlay data.**

## Appendix B — Suggested Follow-up Searches

The `topic="Overlay"` search returned zero results. The Overlay data may be indexed under different topics or keywords. Suggested queries:

| Gap | Suggested Query |
|---|---|
| Overlay wrapper module | `query="tt_overlay_wrapper"` |
| Overlay package | `query="tt_overlay_pkg"` |
| RISC-V CPU cluster | `query="riscv cpu cluster NUM_CLUSTER_CPUS"` |
| L1 cache banks | `query="l1_cache bank ECC overlay"` |
| iDMA engine | `query="idma DMA engine overlay"` |
| ROCC accelerator | `query="rocc accelerator riscv"` |
| LLK block | `query="llk low latency kernel"` |
| FDS sensor | `query="fds frequency droop sensor"` |
| APB slaves | `query="apb slave register overlay"` |
| Overlay in hierarchy | `query="trinity overlay instance"` (no topic filter) |
| All Overlay claims | `analysis_type="claim"`, `query="overlay"` |

---

*End of Document*
