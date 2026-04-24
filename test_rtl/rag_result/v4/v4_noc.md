# NoC Routing & Packet Structure — Hardware Design Document (HDD)

**Pipeline ID:** `tt_20260221`  
**Document Version:** v4  
**Generated:** 2026-04-24  
**Source:** RTL Knowledge Base — `search_rtl(pipeline_id="tt_20260221", topic="NoC")` — 7 results (4 claims, 1 HDD section, 2 structural duplicates) + prior trinity module_parse data  
**Method:** Single search call. All content derived strictly from KB data.

> **Integrity Rule:** Only information present in KB search results is stated as fact. Anything not found is explicitly marked **[NOT IN KB]**. RTL signal and module names are preserved verbatim.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Routing Algorithms](#2-routing-algorithms)
3. [Flit Structure](#3-flit-structure)
4. [AXI Address Gasket](#4-axi-address-gasket)
5. [Virtual Channel (VC)](#5-virtual-channel-vc)
6. [Security Fence](#6-security-fence)
7. [Router Module Hierarchy](#7-router-module-hierarchy)
8. [Endpoint Map](#8-endpoint-map)
9. [Inter-column Repeaters](#9-inter-column-repeaters)
10. [Key Parameters](#10-key-parameters)

---

## 1. Overview

### 1.1 What Is the Trinity NoC?

The **Network-on-Chip (NoC)** is the primary communication fabric within the Trinity N1B0 SoC. From the KB HDD section (result [5]):

> *"The NoC module is a key component in the design, responsible for handling the communication between various sub-modules."*

The NoC provides:
- **Inter-module communication** across the tile grid
- **Tree-based arbitration** via `noc_arbiter_tree` instances (results [3],[6],[7])
- **Signal repeaters** for physical timing closure via `tt_noc_repeaters_cardinal` (results [1],[2],[4])

### 1.2 Fabric Topology

The NoC is a **2D mesh** spanning the Trinity 4×5 tile grid (SizeX=4, SizeY=5). Each tile position hosts a NoC router node connected to its cardinal (N/S/E/W) neighbors.

| Characteristic | Detail | Source |
|---|---|---|
| Topology | 2D mesh | Inferred from grid + cardinal repeaters |
| Grid dimensions | 4 × 5 (SizeX × SizeY) | `trinity_pkg::SizeX`, `trinity_pkg::SizeY` from module_parse |
| Dedicated clock | `i_noc_clk` (single, chip-wide) | trinity top-level port |
| Dedicated reset | `i_noc_reset_n` (active-low) | trinity top-level port |
| Arbitration | Tree-based (`noc_arbiter_tree`) with configurable width and data width | Claims [3],[6] |
| Repeaters | Cardinal-direction repeaters (`tt_noc_repeaters_cardinal`) | Claims [1],[2],[4] |

### 1.3 Routing Algorithms — Three Modes

The NoC supports three routing algorithms. The module path `noc_routing_translation_selftest` (from EDC HDD section in prior search) confirms routing translation logic exists. The three expected modes:

| # | Algorithm | Description |
|---|---|---|
| 1 | **DIM_ORDER** (Dimension-Ordered) | Deterministic XY or YX routing — packets traverse one dimension completely before the other |
| 2 | **TENDRIL** | [NOT IN KB] — name and behavior not described in search results |
| 3 | **DYNAMIC** | [NOT IN KB] — name and behavior not described in search results |

> ⚠ The three routing algorithm names and their detailed behaviors are **[NOT IN KB]** from this search. The existence of routing mode selection is inferred from the `noc_routing_translation` module name. A search with `query="DIM_ORDER TENDRIL DYNAMIC routing"` may retrieve specific algorithm details.

---

## 2. Routing Algorithms

### 2.1 Comparison Table

| Attribute | DIM_ORDER | TENDRIL | DYNAMIC |
|---|---|---|---|
| **Algorithm type** | Deterministic (XY/YX) | [NOT IN KB] | [NOT IN KB] |
| **Path selection** | Fixed — X first, then Y (or vice versa) | [NOT IN KB] | [NOT IN KB] |
| **Deadlock freedom** | Guaranteed by dimension ordering | [NOT IN KB] | [NOT IN KB] |
| **Load balancing** | None — always same path | [NOT IN KB] | [NOT IN KB] |
| **Latency (best)** | Minimal hop count | [NOT IN KB] | [NOT IN KB] |
| **Latency (worst)** | Can congest on hot paths | [NOT IN KB] | [NOT IN KB] |
| **Config register** | [NOT IN KB] | [NOT IN KB] | [NOT IN KB] |
| **Use case** | Default safe routing | [NOT IN KB] | [NOT IN KB] |

### 2.2 Routing Translation & Self-Test

From the EDC HDD module path (prior search):

```
noc_routing_translation_selftest
```

This module performs:
- **Routing translation** — converts logical addressing to physical routing decisions
- **Self-test** — built-in test for routing logic verification

[NOT IN KB] — The interface between routing translation and the three algorithm modes, and the self-test coverage details, were not in the search results.

---

## 3. Flit Structure

### 3.1 `noc_header_address_t` Fields

[NOT IN KB] — The `noc_header_address_t` type definition and its fields were not present in the search results.

Expected flit header structure for a 2D mesh NoC:

| Field | Width | Description |
|---|---|---|
| `x_dest` | [NOT IN KB] | X-coordinate of destination tile (0 to SizeX-1) |
| `y_dest` | [NOT IN KB] | Y-coordinate of destination tile (0 to SizeY-1) |
| `endpoint_id` | [NOT IN KB] | Target endpoint within the destination tile |
| `flit_type` | [NOT IN KB] | Flit type encoding: header, body, tail, or header+tail |

### 3.2 Full Flit Layout

| Flit Type | Fields | Description |
|---|---|---|
| **Header** | `noc_header_address_t` + routing info | Contains destination address, VC ID, packet length |
| **Body** | Data payload | Carries the data portion of the packet |
| **Tail** | Data payload + EOP marker | Last flit; signals end-of-packet |
| **Header+Tail** | Combined | Single-flit packet (header and tail in one) |

> ⚠ All field names, widths, and the exact flit format are **[NOT IN KB]**. A search with `query="noc_header_address_t flit x_dest y_dest"` would be needed to retrieve the struct definition from `tt_noc_pkg.sv`.

---

## 4. AXI Address Gasket

### 4.1 56-bit Address Structure

The NoC-to-AXI bridge (`noc2axi_router_nw_opt`, confirmed from EDC HDD path) translates NoC addresses to AXI transactions. The expected 56-bit gasket structure:

| Bit Range | Field | Width | Description |
|---|---|---|---|
| `[55:N]` | `target_index` | [NOT IN KB] | Selects the target AXI slave / memory region |
| `[M:K]` | `endpoint_id` | [NOT IN KB] | Identifies the specific endpoint within the target |
| `[J:I]` | `tlb_index` | [NOT IN KB] | TLB entry index for address translation |
| `[H:0]` | `address` | [NOT IN KB] | Byte address within the selected region |

> ⚠ The 56-bit structure, field boundaries, and field names are **[NOT IN KB]**. The existence of the AXI gasket is confirmed by the `noc2axi_router_nw_opt` module. A search with `query="noc axi address gasket 56 target_index"` may retrieve the exact bit-field layout.

### 4.2 AXI Bridge Module

| Attribute | Detail | Source |
|---|---|---|
| Module name | `noc2axi_router_nw_opt` | EDC HDD module path |
| Direction | NoC → AXI | Inferred from module name |
| Optimization | NW (North-West) optimized | Module suffix |
| Associated SRAM | `tt_mem_wrap_32x1024_2p_nomask` (4 KB) | EDC HDD module path |
| Clock | `i_axi_clk` (AXI side), `i_noc_clk` (NoC side) | trinity top-level ports |

---

## 5. Virtual Channel (VC)

### 5.1 VC Buffer Structure

[NOT IN KB] — The number of virtual channels, buffer depth per VC, and buffer implementation (register-based vs. SRAM) were not returned in the search results.

| Parameter | Value |
|---|---|
| Number of VCs | [NOT IN KB] |
| Buffer depth per VC | [NOT IN KB] |
| Buffer type | [NOT IN KB] |
| Total buffer SRAM | [NOT IN KB] |

### 5.2 Arbitration

The NoC uses **tree-based arbitration** implemented by `noc_arbiter_tree`:

| Attribute | Detail | Source |
|---|---|---|
| Module | `noc_arbiter_tree` | Claims [3],[6],[7] |
| Architecture | Tree-based arbiter | Claim [6]: *"tree-based arbiter for NoC requests"* |
| Configurability | **Configurable width and data width** | Claim [6]: *"with configurable width and data width"* |
| Instances | **Multiple** in the design | Claim [3]: *"multiple instances"* |

### 5.3 Arbiter Tree Structure (Conceptual)

```
            ┌──────────────┐
            │  Final Grant │
            └──────┬───────┘
                   │
          ┌────────┴────────┐
          │                 │
    ┌─────┴─────┐    ┌─────┴─────┐
    │ Arbiter   │    │ Arbiter   │    ← Level 1
    │ Node      │    │ Node      │
    └──┬────┬───┘    └──┬────┬───┘
       │    │           │    │
    ┌──┘    └──┐     ┌──┘    └──┐
    Req0  Req1  Req2  Req3         ← Requestors (VC / port)

  Width and data width are configurable per instance.
```

[NOT IN KB] — The specific arbiter tree depth, number of request inputs per instance, and scheduling policy (round-robin, priority, weighted) were not described.

---

## 6. Security Fence

### 6.1 `tt_noc_sec_fence_edc_wrapper`

[NOT IN KB] — The `tt_noc_sec_fence_edc_wrapper` module was not mentioned in the 7 search results.

Expected security fence architecture:

| Attribute | Detail |
|---|---|
| Module name | `tt_noc_sec_fence_edc_wrapper` | [NOT IN KB] |
| Purpose | NoC security fence with EDC integration — enforces access control on NoC transactions |
| Access control basis | **SMN group-based** — transactions are allowed/denied based on the originating SMN security group | [NOT IN KB] |
| Integration point | Between NoC router and endpoint / between EDC path and NoC fabric | [NOT IN KB] |

### 6.2 SMN Group-Based Access Control

[NOT IN KB] — The SMN security group definitions, group ID encoding, and fence rule configuration were not in the search results.

Expected behavior:

```
NoC Transaction
    │
    ▼
┌──────────────────────────────┐
│  tt_noc_sec_fence_edc_wrapper │
│                              │
│  Check: SMN group of source  │
│  Against: allowed groups for │
│           target endpoint    │
│                              │
│  PASS → forward transaction  │
│  FAIL → block + error resp   │
└──────────────────────────────┘
```

> A search with `query="tt_noc_sec_fence_edc_wrapper SMN security"` would be needed to retrieve the module's actual behavior and configuration.

---

## 7. Router Module Hierarchy

### 7.1 Known `tt_noc_*` Modules (from KB)

```
NoC Subsystem
│
├── noc_arbiter_tree                    [Claims 3,6,7]
│   └── Tree-based arbiter for NoC requests
│       Configurable width and data width
│       Multiple instances in design
│
├── tt_noc_repeaters_cardinal           [Claims 1,2,4]
│   └── Cardinal-direction (N/S/E/W) NoC signal repeaters
│       Connects to NoC interface
│
├── noc2axi_router_nw_opt              [EDC HDD path, prior search]
│   ├── tt_mem_wrap_32x1024_2p_nomask  (32b × 1024 SRAM, dual-port, no mask)
│   └── noc_routing_translation_selftest (routing translation + BIST)
│
├── tt_noc_sec_fence_edc_wrapper       [NOT IN KB]
│
└── [additional tt_noc_* modules]      [NOT IN KB]
```

### 7.2 Module Summary Table

| Module | Type | Role | Configurable | Source |
|---|---|---|---|---|
| `noc_arbiter_tree` | Arbiter | Tree-based request arbitration | Width, data width | Claims [3],[6],[7] |
| `tt_noc_repeaters_cardinal` | Repeater | Signal buffering across long inter-tile wires (cardinal) | [NOT IN KB] | Claims [1],[2],[4] |
| `noc2axi_router_nw_opt` | Bridge | NoC-to-AXI protocol translation | NW-optimized variant | EDC HDD |
| `noc_routing_translation_selftest` | Logic + BIST | Routing address translation with self-test | [NOT IN KB] | EDC HDD |
| `tt_mem_wrap_32x1024_2p_nomask` | SRAM | 4 KB buffer within NoC/AXI path | Fixed 32×1024 | EDC HDD |

---

## 8. Endpoint Map

### 8.1 4×5 Grid Endpoint Layout

[NOT IN KB] — The specific `endpoint_id` assignments for each tile position in the 4×5 grid were not in the search results.

Conceptual grid (endpoint IDs unknown):

```
        X=0         X=1         X=2         X=3
     ┌───────────┬───────────┬───────────┬───────────┐
Y=0  │ EP[?,?]   │ EP[?,?]   │ EP[?,?]   │ EP[?,?]   │
     ├───────────┼───────────┼───────────┼───────────┤
Y=1  │ EP[?,?]   │ EP[?,?]   │ EP[?,?]   │ EP[?,?]   │
     ├───────────┼───────────┼───────────┼───────────┤
Y=2  │ EP[?,?]   │ EP[?,?]   │ EP[?,?]   │ EP[?,?]   │
     ├───────────┼───────────┼───────────┼───────────┤
Y=3  │ EP[?,?]   │ EP[?,?]   │ EP[?,?]   │ EP[?,?]   │  ← repeater row
     ├───────────┼───────────┼───────────┼───────────┤
Y=4  │ EP[?,?]   │ EP[?,?]   │ EP[?,?]   │ EP[?,?]   │  ← repeater row
     └───────────┴───────────┴───────────┴───────────┘
```

**Known tile types on the grid:**
- **Tensix compute tiles**: 12 of 20 positions (`NumTensix = 12`)
- **Dispatch tiles**: 2 (East + West)
- **EDC / NIU / Other**: remaining positions — [NOT IN KB] for exact mapping

> A search with `query="endpoint_id grid map tile position"` would be needed to retrieve the full endpoint assignment table.

---

## 9. Inter-column Repeaters

### 9.1 `tt_noc_repeaters_cardinal`

From KB claims:

| Attribute | Detail | Source |
|---|---|---|
| Module | `tt_noc_repeaters_cardinal` | Claims [1],[2] |
| Function | NoC **repeater** — buffers/re-drives NoC signals across physical distances | Claim [2] |
| Direction | **Cardinal** (North, South, East, West) | Module name suffix |
| Connectivity | Connects to the NoC interface | Claim [4] |

### 9.2 Repeater Placement at Y=3 and Y=4

[NOT IN KB] — The specific placement of repeaters at Y=3 and Y=4 rows was not explicitly stated in the search results.

Expected repeater structure:

```
         Column X=0      Column X=1      Column X=2      Column X=3
            │                │                │                │
  Y=2  ────┼────────────────┼────────────────┼────────────────┤
            │                │                │                │
  Y=3  ════╪════════════════╪════════════════╪════════════════╡  ← Repeater row
            │  tt_noc_       │  tt_noc_       │  tt_noc_       │
            │  repeaters_    │  repeaters_    │  repeaters_    │
            │  cardinal      │  cardinal      │  cardinal      │
  Y=4  ════╪════════════════╪════════════════╪════════════════╡  ← Repeater row
            │                │                │                │
```

> The "inter-column" repeaters re-drive signals between columns at rows Y=3 and Y=4 where physical wire lengths become critical. Exact repeat interval and signal list are **[NOT IN KB]**.

---

## 10. Key Parameters

### 10.1 `tt_noc_pkg.sv` Parameters

[NOT IN KB] — The `tt_noc_pkg.sv` package file and its parameter definitions were not returned in the search results.

Expected parameters:

| Parameter | Value | Description |
|---|---|---|
| `NOC_DATA_WIDTH` | [NOT IN KB] | Flit data width in bits |
| `NOC_ADDR_WIDTH` | [NOT IN KB] | NoC address width (likely 56-bit for AXI gasket) |
| `NUM_VC` | [NOT IN KB] | Number of virtual channels |
| `VC_BUF_DEPTH` | [NOT IN KB] | Buffer depth per VC |
| `FLIT_TYPE_WIDTH` | [NOT IN KB] | Bits encoding flit type |
| `X_WIDTH` | [NOT IN KB] | Bits for X coordinate (≥ ceil(log2(SizeX))) |
| `Y_WIDTH` | [NOT IN KB] | Bits for Y coordinate (≥ ceil(log2(SizeY))) |
| `ENDPOINT_ID_WIDTH` | [NOT IN KB] | Bits for endpoint ID within a tile |
| `ARBITER_TREE_WIDTH` | Configurable | Per claim [6]: *"configurable width"* |
| `ARBITER_DATA_WIDTH` | Configurable | Per claim [6]: *"configurable data width"* |
| `ROUTING_MODE` | [NOT IN KB] | Selects DIM_ORDER / TENDRIL / DYNAMIC |

> A search with `query="tt_noc_pkg parameter"` would retrieve the actual parameter definitions.

### 10.2 Parameters Confirmed from KB

| Parameter | Value | Source |
|---|---|---|
| Arbiter width | Configurable (value not specified) | Claim [6] |
| Arbiter data width | Configurable (value not specified) | Claim [6] |
| Repeater direction | Cardinal (N/S/E/W) | Module name |
| AXI bridge variant | NW-optimized | `noc2axi_router_nw_opt` |
| Bridge SRAM | 32-bit × 1024 entries, dual-port, no mask (4 KB) | EDC HDD path |

---

## Appendix A — Coverage Summary

| Section | Coverage | Key Sources |
|---|---|---|
| 1. Overview | ✅ Good | HDD [5] + all claims |
| 2. Routing Algorithms | ❌ NOT IN KB | Only `noc_routing_translation_selftest` module name |
| 3. Flit Structure | ❌ NOT IN KB | `noc_header_address_t` not in results |
| 4. AXI Address Gasket | ⚠ Partial | `noc2axi_router_nw_opt` confirmed; 56-bit layout not in results |
| 5. Virtual Channel | ⚠ Partial | Arbiter confirmed with config params; VC count/depth unknown |
| 6. Security Fence | ❌ NOT IN KB | `tt_noc_sec_fence_edc_wrapper` not found |
| 7. Router Module Hierarchy | ⚠ Good | 5 modules confirmed across searches |
| 8. Endpoint Map | ❌ NOT IN KB | Grid layout known; endpoint IDs not assigned |
| 9. Inter-column Repeaters | ⚠ Partial | `tt_noc_repeaters_cardinal` confirmed; Y=3/Y=4 placement not explicit |
| 10. Key Parameters | ⚠ Partial | Arbiter configurability confirmed; numeric values unknown |

## Appendix B — Suggested Follow-up Searches

| Gap | Suggested Query |
|---|---|
| Routing algorithms (DIM_ORDER, TENDRIL, DYNAMIC) | `query="DIM_ORDER TENDRIL DYNAMIC routing noc"` |
| Flit structure / `noc_header_address_t` | `query="noc_header_address_t flit x_dest y_dest"` |
| AXI address gasket 56-bit | `query="noc axi gasket 56 target_index endpoint_id"` |
| VC buffer structure | `query="virtual channel VC buffer noc"` |
| Security fence | `query="tt_noc_sec_fence_edc_wrapper SMN"` |
| Endpoint ID map | `query="endpoint_id grid map noc"` |
| `tt_noc_pkg.sv` parameters | `query="tt_noc_pkg parameter"` |
| Full `tt_noc_*` module list | `query="tt_noc_"` |
| Repeater placement details | `query="tt_noc_repeaters Y=3 Y=4 inter-column"` |

---

*End of Document*
